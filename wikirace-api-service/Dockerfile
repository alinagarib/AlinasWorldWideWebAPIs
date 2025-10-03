# Use a standard Python 3.11 image.
FROM python:3.11

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file
COPY ./requirements.txt .

# Install the Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Expose the port where the application will run
EXPOSE 80

# Set the command to run the FastAPI application with uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80"]