#!/bin/bash

echo "Setting up Bid Monitoring Platform..."

# Create necessary directories
mkdir -p .streamlit
mkdir -p data

# Create virtual environment
python -m venv venv

# Activate virtual environment
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

echo "Setup complete!"
echo ""
echo "To run the application:"
echo "1. Activate virtual environment: source venv/bin/activate"
echo "2. Run: streamlit run app.py"
echo ""
echo "Or use Docker:"
echo "docker-compose up --build"