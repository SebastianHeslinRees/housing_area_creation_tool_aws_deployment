"""Precompute Housing Market Area outputs with PySpark for AWS Glue.

This script lifts the compute-heavy parts of app.py out of the Dash request
cycle. Spark is used for ingesting and reducing the large flow inputs while
the iterative HMA merge logic runs in Python on the reduced LAD-level graph.
"""

from __future__ import annotations

# pyright: reportMissingImports=false

import argparse
import gzip
import itertools
import json
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

import boto3
import geopandas as gpd
import pandas as pd

if TYPE_CHECKING:
    from pyspark.sql import SparkSession as SparkSessionType
else:
    SparkSessionType = Any

try:
    from pyspark.sql import SparkSession, functions as F
except ImportError:  # pragma: no cover - pyspark is provided by Glue at runtime.
    SparkSession = Any
    F = None


SCRIPT_VERSION = "2026-04-17-v4"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Precompute HMA outputs for threshold permutations")
    parser.add_argument("--commuting-s3-uri", required=True)
    parser.add_argument("--migration-s3-uri", required=True)
    parser.add_argument("--geometry-s3-uri", required=True)
    parser.add_argument("--output-s3-prefix", required=True)
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--commuting-start", type=float, default=0.5)
    parser.add_argument("--commuting-stop", type=float, default=0.9)
    parser.add_argument("--commuting-step", type=float, default=0.025)
    parser.add_argument("--migration-start", type=float, default=0.3)
    parser.add_argument("--migration-stop", type=float, default=0.7)
    parser.add_argument("--migration-step", type=float, default=0.025)
    parser.add_argument("--map-simplify-tolerance", type=float, default=0.0008)
    parser.add_argument("--single-commuting-threshold", type=float)
    parser.add_argument("--single-migration-threshold", type=float)
    try:
        args, _unknown_args = parser.parse_known_args()
        if (args.single_commuting_threshold is None) != (args.single_migration_threshold is None):
            parser.error(
                "--single-commuting-threshold and --single-migration-threshold must be provided together"
            )
        return args
    except SystemExit:
        print(f"HMA_GLUE_SCRIPT_VERSION={SCRIPT_VERSION}")
        print(f"ARGV={sys.argv}")
        print(
            "Expected required args: --commuting-s3-uri, --migration-s3-uri, "
            "--geometry-s3-uri, --output-s3-prefix, --dataset-version"
        )
        raise


def parse_s3_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("s3://"):
        raise ValueError(f"Expected s3:// URI, got {uri}")
    bucket, _, key = uri[5:].partition("/")
    if not bucket or not key:
        raise ValueError(f"Invalid S3 URI: {uri}")
    return bucket, key


def normalise_s3_prefix(prefix: str) -> str:
    return prefix.rstrip("/")


def build_threshold_values(start: float, stop: float, step: float) -> list[float]:
    values: list[float] = []
    current = start
    while current <= stop + (step / 10):
        values.append(round(current, 3))
        current += step
    return values


def format_threshold(value: float) -> str:
    return f"{value:.3f}"


def download_s3_file(s3_client, uri: str, suffix: str) -> Path:
    bucket, key = parse_s3_uri(uri)
    temp_dir = Path(tempfile.mkdtemp(prefix="hma-glue-"))
    local_path = temp_dir / f"downloaded{suffix}"
    s3_client.download_file(bucket, key, str(local_path))
    return local_path


def load_base_geography(geometry_path: Path) -> gpd.GeoDataFrame:
    geography = gpd.read_file(geometry_path)
    if "LAD23CD" not in geography.columns:
        raise ValueError(f"Geometry file {geometry_path} does not contain LAD23CD")

    if "year" in geography.columns:
        geography = geography.sort_values("year").drop_duplicates(subset=["LAD23CD"], keep="last")

    lad_name_column = "LAD23NM" if "LAD23NM" in geography.columns else None
    selected_columns = ["LAD23CD", "geometry"]
    if lad_name_column:
        selected_columns.insert(1, lad_name_column)
    geography = geography[selected_columns].copy()

    if lad_name_column is None:
        geography["LAD23NM"] = geography["LAD23CD"]

    if geography.crs is None:
        geography = geography.set_crs("EPSG:4326", allow_override=True)
    else:
        geography = geography.to_crs(epsg=4326)

    geography = geography[geography["LAD23CD"].astype(str).str.startswith(("E", "W"))].copy()
    geography = geography[geography.geometry.notnull() & geography.is_valid].reset_index(drop=True)
    return geography


def load_flow_dataframe_spark(spark: SparkSessionType, path: str, flow_kind: str) -> pd.DataFrame:
    flow_df = spark.read.option("header", True).csv(path)
    if flow_kind == "migration":
        origin_col = "outla"
        destination_col = "inla"
        flow_col = "moves"
    else:
        origin_col = "RES_LAD23CD"
        destination_col = "WORK_LAD23CD"
        flow_col = "flow"

    if origin_col not in flow_df.columns or destination_col not in flow_df.columns:
        raise ValueError(f"{flow_kind.title()} flow file is missing origin/destination columns")

    flow_expression = F.lit(1.0)
    if flow_col in flow_df.columns:
        flow_expression = F.when(
            F.col(flow_col).isNotNull(),
            F.col(flow_col).cast("double"),
        ).otherwise(F.lit(1.0))

    reduced_df = (
        flow_df
        .withColumn("origin", F.col(origin_col).cast("string"))
        .withColumn("destination", F.col(destination_col).cast("string"))
        .withColumn("flow", flow_expression)
        .filter(F.col("origin").rlike("^[EW]"))
        .filter(F.col("destination").rlike("^[EW]"))
        .groupBy("origin", "destination")
        .agg(F.sum("flow").alias("flow"))
        .orderBy("origin", "destination")
    )
    return reduced_df.toPandas()


def create_flow_dict(flow_df: pd.DataFrame) -> dict[str, dict[str, float]]:
    flow_dict: dict[str, dict[str, float]] = {}
    for row in flow_df.itertuples(index=False):
        origin_bucket = flow_dict.setdefault(row.origin, {})
        origin_bucket[row.destination] = origin_bucket.get(row.destination, 0.0) + float(row.flow)
    return flow_dict


def build_neighbors_dict(geography: gpd.GeoDataFrame) -> dict[str, set[str]]:
    neighbors = {lad: set() for lad in geography["LAD23CD"]}
    sindex = geography.sindex
    codes = geography["LAD23CD"].tolist()
    geometries = geography.geometry.tolist()

    for index, geometry in enumerate(geometries):
        possible_matches = sindex.intersection(geometry.bounds)
        lad_code = codes[index]
        for candidate_index in possible_matches:
            if candidate_index == index:
                continue
            candidate_geometry = geometries[candidate_index]
            if geometry.touches(candidate_geometry) or geometry.intersects(candidate_geometry):
                neighbors[lad_code].add(codes[candidate_index])

    return neighbors


def self_containment(region_las: Iterable[str], flows_dict: dict[str, dict[str, float]]) -> float:
    internal_flow = 0.0
    total_flow = 0.0
    for origin in region_las:
        for destination, flow in flows_dict.get(origin, {}).items():
            total_flow += flow
            if destination in region_las:
                internal_flow += flow
    if total_flow == 0:
        return 0.0
    return internal_flow / total_flow


def bidirectional_flows(region_a: set[str], region_b: set[str], flows_dict: dict[str, dict[str, float]]) -> float:
    flow_total = 0.0
    for origin in region_a:
        for destination in region_b:
            flow_total += flows_dict.get(origin, {}).get(destination, 0.0)
    for origin in region_b:
        for destination in region_a:
            flow_total += flows_dict.get(origin, {}).get(destination, 0.0)
    return flow_total


def run_hma_algorithm(
    geography: gpd.GeoDataFrame,
    neighbors: dict[str, set[str]],
    commuting_flows: dict[str, dict[str, float]],
    migration_flows: dict[str, dict[str, float]],
    commuting_threshold: float,
    migration_threshold: float,
) -> tuple[pd.DataFrame, dict[str, object]]:
    commuting_regions = {lad: {lad} for lad in geography["LAD23CD"]}
    sc_cache_commuting = {
        lad: self_containment({lad}, commuting_flows)
        for lad in commuting_regions
    }

    iteration = 0
    max_iterations = 2000
    while iteration < max_iterations:
        iteration += 1
        failing_regions = [
            region_id
            for region_id, sc_value in sc_cache_commuting.items()
            if sc_value < commuting_threshold
        ]
        if not failing_regions:
            break

        best_pair = None
        best_flow = 0.0
        for region_id in failing_regions:
            region = commuting_regions[region_id]
            region_neighbors = set()
            for lad in region:
                region_neighbors.update(neighbors.get(lad, set()))
            region_neighbors -= region

            for other_id, other_region in commuting_regions.items():
                if other_id == region_id or not region_neighbors.intersection(other_region):
                    continue
                flow_value = bidirectional_flows(region, other_region, commuting_flows)
                if flow_value > best_flow:
                    best_flow = flow_value
                    best_pair = (region_id, other_id)

        if best_pair is None:
            break

        first_region, second_region = best_pair
        merged_region = commuting_regions[first_region] | commuting_regions[second_region]
        del commuting_regions[first_region]
        del commuting_regions[second_region]
        del sc_cache_commuting[first_region]
        del sc_cache_commuting[second_region]

        new_region_id = f"C_{iteration}"
        commuting_regions[new_region_id] = merged_region
        sc_cache_commuting[new_region_id] = self_containment(merged_region, commuting_flows)

    passed_regions: dict[str, set[str]] = {}
    failed_las: set[str] = set()
    for region_id, region_las in commuting_regions.items():
        migration_sc = self_containment(region_las, migration_flows)
        if migration_sc >= migration_threshold:
            passed_regions[region_id] = region_las
        else:
            failed_las.update(region_las)

    migration_regions = {lad: {lad} for lad in failed_las}
    sc_cache_migration = {
        lad: self_containment({lad}, migration_flows)
        for lad in migration_regions
    }

    iteration = 0
    while iteration < max_iterations and migration_regions:
        iteration += 1
        failing_regions = [
            region_id
            for region_id, sc_value in sc_cache_migration.items()
            if sc_value < migration_threshold
        ]
        if not failing_regions:
            break

        best_pair = None
        best_flow = 0.0
        for region_id in failing_regions:
            region = migration_regions[region_id]
            region_neighbors = set()
            for lad in region:
                region_neighbors.update(neighbors.get(lad, set()))
            region_neighbors -= region

            for other_id, other_region in migration_regions.items():
                if other_id == region_id or not region_neighbors.intersection(other_region):
                    continue
                flow_value = bidirectional_flows(region, other_region, migration_flows)
                if flow_value > best_flow:
                    best_flow = flow_value
                    best_pair = (region_id, other_id)

        if best_pair is None:
            break

        first_region, second_region = best_pair
        merged_region = migration_regions[first_region] | migration_regions[second_region]
        del migration_regions[first_region]
        del migration_regions[second_region]
        del sc_cache_migration[first_region]
        del sc_cache_migration[second_region]

        new_region_id = f"M_{iteration}"
        migration_regions[new_region_id] = merged_region
        sc_cache_migration[new_region_id] = self_containment(merged_region, migration_flows)

    final_regions: dict[str, set[str]] = {}
    final_regions.update(passed_regions)
    final_regions.update(migration_regions)

    records: list[dict[str, object]] = []
    hma_summary_rows: list[dict[str, object]] = []
    for hma_id, (region_name, region_las) in enumerate(final_regions.items(), start=1):
        commuting_sc = self_containment(region_las, commuting_flows)
        migration_sc = self_containment(region_las, migration_flows)
        anchor_name = geography.loc[
            geography["LAD23CD"].isin(region_las),
            "LAD23NM",
        ].sort_values().iloc[0]
        display_name = f"{anchor_name} HMA"
        region_stage = (
            "Passed commuting and migration"
            if region_name in passed_regions
            else "Re-grouped by migration"
        )

        hma_summary_rows.append(
            {
                "HMA_ID": hma_id,
                "HMA_Name": display_name,
                "HMA_Size": len(region_las),
                "Commuting_SC": commuting_sc,
                "Migration_SC": migration_sc,
                "Stage": region_stage,
            }
        )

        for lad in region_las:
            records.append(
                {
                    "LAD23CD": lad,
                    "HMA_ID": hma_id,
                    "HMA_Name": display_name,
                    "HMA_Size": len(region_las),
                    "Commuting_SC": commuting_sc,
                    "Migration_SC": migration_sc,
                    "Stage": region_stage,
                }
            )

    results_df = pd.DataFrame(records)
    summary_df = pd.DataFrame(hma_summary_rows).sort_values(
        ["HMA_Size", "HMA_Name"],
        ascending=[False, True],
    )
    meta = {
        "passed_regions": len(passed_regions),
        "migration_regions": len(migration_regions),
        "final_hmas": len(final_regions),
        "commuting_threshold": commuting_threshold,
        "migration_threshold": migration_threshold,
        "summary_df": summary_df,
    }
    return results_df, meta


def build_summary_payload(meta: dict[str, object], summary_df: pd.DataFrame, geometry_uri: str) -> dict[str, object]:
    mean_hma_size = float(summary_df["HMA_Size"].mean()) if not summary_df.empty else 0.0
    max_hma_size = int(summary_df["HMA_Size"].max()) if not summary_df.empty else 0
    return {
        "commuting_threshold": meta["commuting_threshold"],
        "migration_threshold": meta["migration_threshold"],
        "final_hmas": meta["final_hmas"],
        "passed_regions": meta["passed_regions"],
        "migration_regions": meta["migration_regions"],
        "mean_hma_size": mean_hma_size,
        "max_hma_size": max_hma_size,
        "geometry_s3_uri": geometry_uri,
    }


def dissolve_hma_boundaries(
    geography: gpd.GeoDataFrame,
    results_df: pd.DataFrame,
    simplify_tolerance: float,
) -> gpd.GeoDataFrame:
    dissolved = geography.merge(results_df, on="LAD23CD", how="inner")
    dissolved = dissolved.dissolve(by="HMA_ID", aggfunc="first").reset_index()
    if simplify_tolerance > 0:
        dissolved["geometry"] = dissolved.geometry.simplify(
            tolerance=simplify_tolerance,
            preserve_topology=True,
        )
    return dissolved


def write_json_to_s3(s3_client, uri: str, payload: dict[str, object]) -> None:
    bucket, key = parse_s3_uri(uri)
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(payload, indent=2).encode("utf-8"),
        ContentType="application/json",
    )


def write_csv_to_s3(s3_client, uri: str, frame: pd.DataFrame) -> None:
    bucket, key = parse_s3_uri(uri)
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=frame.to_csv(index=False).encode("utf-8"),
        ContentType="text/csv",
    )


def write_geojson_gz_to_s3(s3_client, uri: str, frame: gpd.GeoDataFrame) -> None:
    bucket, key = parse_s3_uri(uri)
    body = gzip.compress(frame.to_json().encode("utf-8"))
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=body,
        ContentType="application/geo+json",
        ContentEncoding="gzip",
    )


def write_assignments_parquet(spark: SparkSessionType, uri: str, frame: pd.DataFrame) -> None:
    target = normalise_s3_prefix(uri)
    spark.createDataFrame(frame).write.mode("overwrite").parquet(target)


def main() -> None:
    if F is None:
        raise RuntimeError("pyspark is required to run this script. Run it in AWS Glue or an environment with pyspark installed.")

    print(f"HMA_GLUE_SCRIPT_VERSION={SCRIPT_VERSION}")
    print(f"ARGV={sys.argv}")

    args = parse_args()
    spark = SparkSession.builder.appName("housing-market-areas-precompute").getOrCreate()
    s3_client = boto3.client("s3")

    geometry_path = download_s3_file(s3_client, args.geometry_s3_uri, suffix=".geojson")
    geography = load_base_geography(geometry_path)
    neighbors = build_neighbors_dict(geography)

    commuting_df = load_flow_dataframe_spark(spark, args.commuting_s3_uri, "commuting")
    migration_df = load_flow_dataframe_spark(spark, args.migration_s3_uri, "migration")
    commuting_flow_dict = create_flow_dict(commuting_df)
    migration_flow_dict = create_flow_dict(migration_df)

    if args.single_commuting_threshold is not None and args.single_migration_threshold is not None:
        threshold_pairs = [
            (
                round(args.single_commuting_threshold, 3),
                round(args.single_migration_threshold, 3),
            )
        ]
        print(
            "Running Glue precompute in single-pair validation mode for "
            f"commuting={threshold_pairs[0][0]:.3f}, migration={threshold_pairs[0][1]:.3f}"
        )
    else:
        threshold_pairs = list(
            itertools.product(
                build_threshold_values(args.commuting_start, args.commuting_stop, args.commuting_step),
                build_threshold_values(args.migration_start, args.migration_stop, args.migration_step),
            )
        )
        print(
            "Running Glue precompute for the full threshold grid: "
            f"{len(threshold_pairs)} combinations"
        )

    base_prefix = (
        f"{normalise_s3_prefix(args.output_s3_prefix)}/dataset_version={args.dataset_version}"
    )

    for commuting_threshold, migration_threshold in threshold_pairs:
        results_df, meta = run_hma_algorithm(
            geography=geography,
            neighbors=neighbors,
            commuting_flows=commuting_flow_dict,
            migration_flows=migration_flow_dict,
            commuting_threshold=commuting_threshold,
            migration_threshold=migration_threshold,
        )

        summary_df = meta["summary_df"]
        threshold_prefix = (
            f"{base_prefix}/commuting_threshold={format_threshold(commuting_threshold)}"
            f"/migration_threshold={format_threshold(migration_threshold)}"
        )
        assignments_uri = f"{threshold_prefix}/assignments.parquet"
        assignments_csv_uri = f"{threshold_prefix}/assignments.csv"
        geometry_uri = f"{threshold_prefix}/hma_boundaries.geojson.gz"
        summary_uri = f"{threshold_prefix}/summary.json"

        enriched_results = results_df.merge(
            geography[["LAD23CD", "LAD23NM"]],
            on="LAD23CD",
            how="left",
        )
        enriched_results["dataset_version"] = args.dataset_version
        enriched_results["commuting_threshold"] = commuting_threshold
        enriched_results["migration_threshold"] = migration_threshold

        write_assignments_parquet(spark, assignments_uri, enriched_results)
        write_csv_to_s3(s3_client, assignments_csv_uri, enriched_results)

        dissolved = dissolve_hma_boundaries(
            geography=geography,
            results_df=results_df,
            simplify_tolerance=args.map_simplify_tolerance,
        )
        write_geojson_gz_to_s3(s3_client, geometry_uri, dissolved)

        summary_payload = build_summary_payload(meta, summary_df, geometry_uri)
        summary_payload["dataset_version"] = args.dataset_version
        summary_payload["assignments_s3_uri"] = assignments_uri
        summary_payload["assignments_csv_s3_uri"] = assignments_csv_uri
        write_json_to_s3(s3_client, summary_uri, summary_payload)

    spark.stop()


if __name__ == "__main__":
    main()