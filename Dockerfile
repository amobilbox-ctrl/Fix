# Use an official PHP image with Apache
FROM php:8.2-apache

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libcurl4-openssl-dev \
    pkg-config \
    libssl-dev \
    git \
    unzip

# Install PHP extensions
RUN docker-php-ext-install curl

# Enable Apache mod_rewrite
RUN a2enmod rewrite

# Set the working directory
WORKDIR /var/www/html

# Copy application code
COPY . .

# Set permissions for the cookie file
RUN touch cookie.txt && chmod 777 cookie.txt && chmod 777 .

# Expose port 80 (Railway will map this)
EXPOSE 80

# Start Apache
CMD ["apache2-foreground"]
