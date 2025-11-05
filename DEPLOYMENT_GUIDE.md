# Fertility Dashboard Deployment Guide

## 📋 Deployment Checklist

### ✅ Step 1: Upload Data to S3
```bash
# Navigate to your project directory
cd /Users/user1/Documents/fertility_rates_app

# Upload GeoJSON files to S3
aws s3 cp asfr_merged.geojson s3://dpa-population-projection-data/dpa-apps/asfr_merged.geojson
aws s3 cp tfr_merged.geojson s3://dpa-population-projection-data/dpa-apps/tfr_merged.geojson

# Verify the uploads
aws s3 ls s3://dpa-population-projection-data/dpa-apps/ --human-readable
```

**Expected output:** You should see both .geojson files listed with their sizes.

---

### ✅ Step 2: Create IAM Role for App Runner

**Option A: Using AWS Console**
1. Go to **IAM Console** → **Roles** → **Create role**
2. Select **AWS service** → **App Runner**
3. Add permission policy: `AmazonS3ReadOnlyAccess` (or create custom policy below)
4. Name the role: `FertilityDashboard-AppRunner-Role`
5. Copy the **Role ARN** (you'll need this later)

**Option B: Using AWS CLI**
```bash
# Create trust policy file
cat > trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "tasks.apprunner.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# Create the role
aws iam create-role \
    --role-name FertilityDashboard-AppRunner-Role \
    --assume-role-policy-document file://trust-policy.json

# Attach S3 read policy (specific to your bucket)
cat > s3-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::dpa-population-projection-data",
        "arn:aws:s3:::dpa-population-projection-data/dpa-apps/*"
      ]
    }
  ]
}
EOF

aws iam put-role-policy \
    --role-name FertilityDashboard-AppRunner-Role \
    --policy-name S3ReadAccess \
    --policy-document file://s3-policy.json

# Get the Role ARN
aws iam get-role --role-name FertilityDashboard-AppRunner-Role --query 'Role.Arn' --output text
```

---

### ✅ Step 3: Push Code to GitHub

```bash
# Check git status
git status

# Add all changes
git add app.py requirements.txt apprunner.yaml

# Commit changes
git commit -m "Configure fertility dashboard for S3 deployment with App Runner"

# Push to GitHub
git push origin main
```

---

### ✅ Step 4: Create App Runner Service

**Using AWS Console:**

1. **Navigate to App Runner**
   - Go to AWS Console → App Runner → **Create service**

2. **Configure Source**
   - Repository type: **Source code repository**
   - Connect to GitHub (if not already connected)
   - Select repository: `SebastianHeslinRees/housing-dashboard`
   - Branch: `main`
   - Deployment trigger: **Automatic**

3. **Build Settings**
   - Configuration file: **Use a configuration file**
   - Configuration file location: `apprunner.yaml`

4. **Service Settings**
   - Service name: `fertility-dashboard`
   - Virtual CPU: **1 vCPU**
   - Virtual memory: **2 GB** (for large GeoJSON files)
   - Port: `8022`

5. **IAM Role**
   - Instance role: Select `FertilityDashboard-AppRunner-Role` (created in Step 2)

6. **Environment Variables** (Already in apprunner.yaml, but verify)
   - `PORT`: `8022`
   - `S3_BUCKET`: `dpa-population-projection-data`
   - `S3_PREFIX`: `dpa-apps/`
   - `AWS_REGION`: `eu-west-2`

7. **Review and Create**
   - Review all settings
   - Click **Create & deploy**

**Deployment will take 5-10 minutes.**

---

### ✅ Step 5: Test Your Deployment

Once deployment completes:

1. **Get your App Runner URL**
   - App Runner Console → Your service → **Default domain**
   - Example: `https://abc123.eu-west-2.awsapprunner.com`

2. **Test the application**
   - Open the URL in your browser
   - First load may take 15-30 seconds (downloading from S3)
   - Subsequent loads will be fast (cached)

3. **Check CloudWatch Logs**
   - App Runner Console → Your service → **Logs**
   - Look for:
     ```
     ⬇ Downloading s3://dpa-population-projection-data/dpa-apps/asfr_merged.geojson...
     ✓ Downloaded asfr_merged.geojson successfully
     ⬇ Downloading s3://dpa-population-projection-data/dpa-apps/tfr_merged.geojson...
     ✓ Downloaded tfr_merged.geojson successfully
     Loading fertility and geometry data...
     dashboard ready: 31 years, 35 ages, XXX LADs
     ```

4. **Test Dashboard Functions**
   - ✅ Select different years
   - ✅ Select different ages
   - ✅ Search for Local Authorities
   - ✅ Check TFR and ASFR maps load
   - ✅ Verify trend graphs work

---

## 🔧 Troubleshooting

### Issue: S3 Access Denied
**Solution:**
- Verify IAM role is attached to App Runner service
- Check S3 bucket policy allows access
- Ensure role has correct permissions

### Issue: Slow First Load
**Expected behavior:**
- First request: 15-30 seconds (downloading data from S3)
- Subsequent requests: <2 seconds (using cached data)

### Issue: Out of Memory
**Solution:**
- Increase App Runner memory to 3-4 GB
- Simplify geometries further in data preprocessing

### Issue: Files Not Found in S3
**Check:**
```bash
aws s3 ls s3://dpa-population-projection-data/dpa-apps/
```

---

## 📊 Expected Performance

| Metric | Value |
|--------|-------|
| First Load (Cold Start) | 15-30 seconds |
| Subsequent Loads | <2 seconds |
| Memory Usage | ~1.5-2 GB |
| S3 Storage Cost | ~$0.05/month |
| App Runner Cost | ~$25-35/month (with traffic) |

---

## 🔄 Updating Data

To update the GeoJSON files:

```bash
# Upload new versions
aws s3 cp asfr_merged.geojson s3://dpa-population-projection-data/dpa-apps/asfr_merged.geojson
aws s3 cp tfr_merged.geojson s3://dpa-population-projection-data/dpa-apps/tfr_merged.geojson

# Restart App Runner service (to download new files)
# AWS Console → App Runner → Your service → Actions → Deploy
```

---

## 📝 Configuration Summary

**S3 Location:**
```
s3://dpa-population-projection-data/dpa-apps/asfr_merged.geojson
s3://dpa-population-projection-data/dpa-apps/tfr_merged.geojson
```

**Environment Variables:**
- `S3_BUCKET`: `dpa-population-projection-data`
- `S3_PREFIX`: `dpa-apps/`
- `AWS_REGION`: `eu-west-2`
- `PORT`: `8022`

**Repository:**
- GitHub: `SebastianHeslinRees/housing-dashboard`
- Branch: `main`

---

## ✅ Success Criteria

Your deployment is successful when:
- [ ] App Runner service shows "Running" status
- [ ] Dashboard loads at the App Runner URL
- [ ] Maps display correctly for TFR and ASFR
- [ ] Dropdowns work for Year, Age, and Local Authority
- [ ] Trend graphs show data
- [ ] No errors in CloudWatch Logs

---

## 🎯 Next Steps

After successful deployment:
1. Share the App Runner URL with your team
2. Set up custom domain (optional)
3. Configure auto-scaling if needed
4. Set up CloudWatch alarms for monitoring
5. Consider upgrading to EFS if you need faster cold starts

---

**Need Help?** Check CloudWatch Logs in App Runner console for detailed error messages.
