# Legal Case Management & Precedent Tracker System

A comprehensive database management system for tracking legal cases, precedents, clients, lawyers, and court hearings.

## 🎯 Features

- **Case Management**: Track cases with complete details, status, and priority
- **Precedent Tracking**: Database of legal precedents with citation analysis
- **Client Management**: Manage individual and corporate clients
- **Lawyer Directory**: Track legal team with specializations and caseload
- **Hearing Scheduler**: Calendar for court hearings and appointments
- **Advanced Database**: Fully normalized (3NF) with ACID transactions and concurrency control

## 🛠️ Technology Stack

- **Backend**: Python Flask
- **Database**: MySQL
- **Frontend**: HTML5, CSS3, Bootstrap 5, JavaScript
- **Database Connector**: mysql-connector-python

## 📋 Prerequisites

Before running this project, make sure you have:

- Python 3.8 or higher
- MySQL Server 8.0 or higher
- pip (Python package manager)
- Git

## 🚀 Installation & Setup

### 1. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/legal-case-management.git
cd legal-case-management
```

### 2. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 3. Setup MySQL Database

**Option A: Using MySQL Command Line**

```bash
# Login to MySQL
mysql -u root -p

# Create database
CREATE DATABASE legal_case_management;

# Exit MySQL
exit;

# Import database schema
mysql -u root -p legal_case_management < database/database_creation_script.sql

# Import sample data (optional)
mysql -u root -p legal_case_management < database/data_insertion_script.sql
```

**Option B: Using MySQL Workbench**
1. Open MySQL Workbench
2. Create new schema: `legal_case_management`
3. Run the SQL scripts from `database/` folder

### 4. Configure Database Connection

Edit `database.py` and update your MySQL credentials:

```python
connection = mysql.connector.connect(
    host='localhost',
    database='legal_case_management',
    user='YOUR_MYSQL_USERNAME',      # Change this
    password='YOUR_MYSQL_PASSWORD'   # Change this
)
```

### 5. Run the Application

```bash
python app.py
```

The application will start on `http://localhost:5000`

## 📂 Project Structure
