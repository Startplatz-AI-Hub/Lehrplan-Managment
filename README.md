# Lehrplan-Management System

A comprehensive web application for managing educational curricula and teaching plans.

## Overview

The Lehrplan-Management System helps educational institutions create, manage, and distribute curriculum documents. It streamlines the process of curriculum development, revision, and implementation while ensuring compliance with educational standards.

## Features

- **Curriculum Creation**: Design and format curriculum documents with an intuitive interface
- **Version Control**: Track changes and maintain a history of curriculum revisions
- **Collaborative Editing**: Allow multiple educators to work on curriculum documents simultaneously
- **Standards Alignment**: Map curriculum content to educational standards
- **Resource Management**: Attach and organize teaching resources related to curriculum components
- **Export Options**: Generate PDF documents, printable worksheets, and digital formats
- **User Management**: Role-based access control for administrators, curriculum designers, and teachers

## Installation

### Prerequisites

- Python 3.8+
- pip (Python package manager)
- Virtual environment (recommended)

### Setup Instructions

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/lehrplan-management.git
   cd lehrplan-management
   ```

2. Create and activate a virtual environment:
   ```
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # macOS/Linux
   source venv/bin/activate
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Set up environment variables:
   Create a `.env` file with the following variables:
   ```
   FLASK_APP=app
   FLASK_ENV=development
   SECRET_KEY=your_secret_key
   DATABASE_URI=sqlite:///lehrplan.db
   ```

5. Initialize the database:
   ```
   flask db init
   flask db migrate
   flask db upgrade
   ```

6. Run the application:
   ```
   flask run
   ```

7. Access the application at `http://127.0.0.1:5000`

## Project Structure

```
lehrplan-management/
├── app/                    # Application package
│   ├── __init__.py         # Initialize the app
│   ├── models/             # Database models
│   ├── routes/             # Route definitions
│   ├── static/             # Static files (CSS, JS, images)
│   ├── templates/          # HTML templates
│   └── utils/              # Utility functions
├── migrations/             # Database migrations
├── tests/                  # Test suite
├── .env                    # Environment variables
├── .gitignore              # Git ignore file
├── config.py               # Configuration settings
├── requirements.txt        # Project dependencies
└── run.py                  # Application entry point
```

## Usage

1. **Login**: Access the system using your credentials
2. **Dashboard**: View an overview of your curricula and recent activities
3. **Create Curriculum**: Start a new curriculum document from scratch or use templates
4. **Edit Curriculum**: Modify existing curriculum documents
5. **Share & Export**: Distribute curriculum documents to stakeholders

## Development

### Running Tests

```
pytest
```

### Code Formatting

```
black app tests
```

### Linting

```
flake8 app tests
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Contributors

- [Your Name](https://github.com/yourusername)

## Acknowledgments

- Thanks to all educators who provided feedback during the development process
- Special thanks to [Educational Standards Organization] for standards reference data 