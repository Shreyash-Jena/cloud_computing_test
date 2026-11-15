# 🧺 IIIT BBSR Smart Laundry Management System

A serverless, cloud-based web application designed to streamline campus hostel laundry operations. It provides real-time washing machine status, live queue wait-time estimation, duplicate bucket submission prevention, and staff administrative controls.

---

## 🚀 Key Features

* **Live Washing Queue & Operational Machine Stats**: Real-time counter of buckets in queue, buckets currently washing, and operational machines out of total available.
* **Smart Wait-Time Forecasting**: Dynamically computes estimated wait time based on queue depth, active machines, and wash cycle duration.
* **Campus Maintenance & Alert Broadcasting**: Laundry staff can broadcast repair announcements (e.g. *"Machine #2 under repair"*) which renders an immediate alert banner on student interfaces.
* **Duplicate Submission Prevention**: Prevents students from hoarding washing slots—a student cannot submit a new bucket until their active laundry is washed and picked up.
* **Role-Based Screen Routing**: Single unified "Sign In / Sign Up" modal routing into dedicated Student or Staff dashboards.
* **Student Bucket Tracking**: Search by Roll Number or Email to view status (`REQUESTED`, `APPROVED_WAITING`, `WASHING`, `READY`, `COLLECTED`), queue position, and completion status.
* **100% Serverless & Free-Tier Eligible**: Runs on AWS Lambda, API Gateway, S3, and DynamoDB at zero cost under the AWS Free Tier.

---

## 💻 How to Set Up and Run Locally

You can test both the frontend and backend locally with **zero cloud setup** and **no external package installations** (pure Python standard library).

### Prerequisites
* Python 3.8 or higher installed on your computer.
* A modern web browser (Chrome, Edge, Firefox, Brave, Safari).

### Steps:

1. **Clone or navigate to the repository**:
   ```bash
   git clone https://github.com/Shreyash-Jena/cloud_computing_test.git
   cd cloud_computing_test
   ```

2. **Start the local development server**:
   ```bash
   python local_test_server.py
   ```
   *(This launches a lightweight local HTTP server with an embedded mock database).*

3. **Open the web application in your browser**:
   Navigate to:
   ```
   http://localhost:8000
   ```

4. **Test Accounts & Credentials**:
   * **Laundry Staff / PC Portal**:
     * **Email**: `pc@iiit-bh.ac.in`
     * **Password**: `LaundryAdmin123`
   * **Student Portal**:
     * Click **Sign In / Sign Up** &rarr; Select **👨‍🎓 Student** &rarr; Click **Sign Up & set PIN**.
     * Roll No: `B123128` (or any roll number)
     * Email: `b123128@iiit-bh.ac.in` (must end with `@iiit-bh.ac.in`)
     * PIN: Any 4-digit PIN (e.g. `1234`).

---

## 📁 Repository Structure

```
├── index.html              # React 18 & Tailwind CSS single-page frontend
├── lamba_fn.py             # Serverless Python backend deployed to AWS Lambda
├── local_test_server.py    # Zero-dependency local development server & mock DB
├── PROJECT_REPORT.md       # Comprehensive system architecture & cloud report
├── .gitignore              # Ignored cache and temporary files
└── README.md               # Project documentation & local setup guide
```

---

## ☁️ AWS Cloud Architecture & Deployment Overview

In production, the application runs on AWS:

```
[User Browser]
      │
      ▼
[Amazon S3] ──────► Static Website Hosting (index.html)
      │
      ▼ (HTTP POST /api)
[Amazon API Gateway] ─► HTTP API Routing & CORS Handlers
      │
      ▼
[AWS Lambda] ────────► Serverless Python Handler (lamba_fn.py)
      │
      ▼
[Amazon DynamoDB] ────► Tables: IIITBLaundry & StudentPins
```

* For detailed deployment instructions, NoSQL schema designs, sequence flows, and free-tier cost analysis, refer to [PROJECT_REPORT.md](PROJECT_REPORT.md).

---

## 📞 Support & Inquiries

For assistance or queries regarding the laundry system, contact: **6372702075**.
