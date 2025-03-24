# Use Node.js base image
FROM node:18-alpine

COPY ./web /app

# Set working directory
WORKDIR /app

# Install dependencies
RUN npm install

# Expose port 80
EXPOSE 80
