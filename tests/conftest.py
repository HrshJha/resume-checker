"""
Unit test fixtures and configuration.
"""

import pytest


@pytest.fixture
def sample_jd_text():
    """Sample job description for testing."""
    return """
    Senior Backend Engineer

    About the Role:
    We are looking for a Senior Backend Engineer to join our platform team.
    You will design and build scalable microservices that power our products.

    Requirements:
    - 5+ years of experience in backend development
    - Strong proficiency in Python, Go, or Java
    - Experience with PostgreSQL, Redis, and Kafka
    - Familiarity with Docker, Kubernetes, and CI/CD pipelines
    - Strong understanding of distributed systems and microservices architecture
    - Experience with REST APIs and GraphQL
    - Bachelor's degree in Computer Science or related field

    Preferred:
    - Experience with gRPC and Protocol Buffers
    - Knowledge of event-driven architecture
    - Contributions to open source projects
    - Experience with AWS or GCP

    Soft Skills:
    - Strong communication and collaboration skills
    - Ability to mentor junior developers
    - Self-motivated with attention to detail
    """


@pytest.fixture
def sample_resume_text():
    """Sample resume text for testing."""
    return """
    John Doe
    john.doe@email.com | github.com/johndoe | linkedin.com/in/johndoe

    Summary
    Experienced backend engineer with 6 years building scalable distributed systems.

    Experience
    Senior Software Engineer | TechCorp Inc. | Jan 2021 - Present
    - Designed and implemented microservices architecture serving 1M+ daily users
    - Built real-time data pipeline using Python, Kafka, and Redis
    - Reduced API latency by 40% through caching strategies and query optimization
    - Led team of 5 engineers in migrating monolith to microservices

    Software Engineer | StartupXYZ | Mar 2018 - Dec 2020
    - Developed REST APIs using Python/Django serving 100K users
    - Implemented CI/CD pipeline using Jenkins and Docker
    - Managed PostgreSQL databases with complex query optimization

    Education
    B.Tech in Computer Science | IIT Delhi | 2018
    CGPA: 8.5/10

    Skills
    Python, Go, Java, PostgreSQL, Redis, Kafka, Docker, Kubernetes,
    AWS, Terraform, GraphQL, REST API, Git, Linux

    Projects
    Distributed Task Queue
    Built a distributed task queue system using Python and Redis
    Handles 10K tasks/minute with fault tolerance and monitoring
    Technologies: Python, Redis, Docker, Prometheus

    Certifications
    AWS Solutions Architect Associate - Amazon Web Services, 2022
    """


@pytest.fixture
def sample_experience_text():
    """Sample experience section text."""
    return """
    Senior Software Engineer | TechCorp Inc. | Jan 2021 - Present
    - Designed and implemented microservices architecture serving 1M+ users
    - Built real-time data pipeline using Python, Kafka, and Redis
    - Reduced API latency by 40% through caching optimization

    Software Engineer | StartupXYZ | Mar 2018 - Dec 2020
    - Developed REST APIs using Python/Django serving 100K users
    - Implemented CI/CD pipeline using Jenkins and Docker
    """
