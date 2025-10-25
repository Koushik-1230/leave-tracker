#!/bin/bash

# Leave Tracker Application Build Script
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
APP_NAME="leave-tracker"
REGISTRY="docker.io/kubekoushik"  # Change this to your registry (e.g., docker.io/yourusername, gcr.io/your-project, etc.)
APP_IMAGE="$REGISTRY/$APP_NAME-app"
NGROK_IMAGE="$REGISTRY/$APP_NAME-ngrok"
TAG="${1:-latest}"
NAMESPACE="leave-tracker"

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if required tools are installed
check_dependencies() {
    print_status "Checking dependencies..."
    
    local missing_deps=()
    
    for cmd in docker kubectl minikube; do
        if ! command -v $cmd &> /dev/null; then
            missing_deps+=("$cmd")
        fi
    done
    
    if [ ${#missing_deps[@]} -ne 0 ]; then
        print_error "Missing dependencies: ${missing_deps[*]}"
        exit 1
    fi
    
    print_success "All dependencies are installed"
}

# Function to build Docker images
build_images() {
    print_status "Building Docker images..."
    
    # Build Flask application image
    print_status "Building Flask application image..."
    docker build -t $APP_IMAGE:$TAG ./app
    if [ $? -eq 0 ]; then
        print_success "Flask application image built successfully: $APP_IMAGE:$TAG"
    else
        print_error "Failed to build Flask application image"
        exit 1
    fi
    
    # Build Ngrok image
    print_status "Building Ngrok image..."
    docker build -t $NGROK_IMAGE:$TAG ./ngrok
    if [ $? -eq 0 ]; then
        print_success "Ngrok image built successfully: $NGROK_IMAGE:$TAG"
    else
        print_error "Failed to build Ngrok image"
        exit 1
    fi
}

# Function to run tests
run_tests() {
    print_status "Running tests..."
    
    # Test Flask application image
    print_status "Testing Flask application image..."
    docker run --rm -e SLACK_BOT_TOKEN=test -e SLACK_SIGNING_SECRET=test -e SLACK_APP_TOKEN=test $APP_IMAGE:$TAG python -c "
import sys
try:
    from app import flask_app
    from supabase_client import SupabaseClient
    print('✓ Flask app imports successfully')
    sys.exit(0)
except Exception as e:
    print(f'✗ Import error: {e}')
    sys.exit(1)
"
    
    if [ $? -eq 0 ]; then
        print_success "Flask application tests passed"
    else
        print_error "Flask application tests failed"
        exit 1
    fi
    
    # Test Ngrok image
    print_status "Testing Ngrok image..."
    docker run --rm $NGROK_IMAGE:$TAG --version
    if [ $? -eq 0 ]; then
        print_success "Ngrok image tests passed"
    else
        print_error "Ngrok image tests failed"
        exit 1
    fi
}

# Function to push images to registry
push_images() {
    print_status "Pushing images to registry..."
    
    # Check if we're logged in to the registry
    if ! docker info | grep -q "Registry: $REGISTRY"; then
        print_warning "Not logged in to registry $REGISTRY"
        print_status "Please make sure you're logged in to your container registry"
        print_status "Example: docker login $REGISTRY"
    fi
    
    # Push Flask application image
    print_status "Pushing Flask application image..."
    docker push $APP_IMAGE:$TAG
    if [ $? -eq 0 ]; then
        print_success "Flask application image pushed successfully"
    else
        print_error "Failed to push Flask application image"
        exit 1
    fi
    
    # Push Ngrok image
    print_status "Pushing Ngrok image..."
    docker push $NGROK_IMAGE:$TAG
    if [ $? -eq 0 ]; then
        print_success "Ngrok image pushed successfully"
    else
        print_error "Failed to push Ngrok image"
        exit 1
    fi
}

# Function to update Kubernetes deployments
update_deployments() {
    print_status "Updating Kubernetes deployments..."
    
    # Check if minikube is running
    if ! minikube status | grep -q "Running"; then
        print_error "Minikube is not running. Please start minikube first: minikube start"
        exit 1
    fi
    
    # Update image in deployment
    kubectl set image deployment/flask-app-deployment flask-app=$APP_IMAGE:$TAG -n $NAMESPACE
    if [ $? -eq 0 ]; then
        print_success "Flask app deployment updated"
    else
        print_error "Failed to update Flask app deployment"
        exit 1
    fi
    
    kubectl set image deployment/ngrok-deployment ngrok=$NGROK_IMAGE:$TAG -n $NAMESPACE
    if [ $? -eq 0 ]; then
        print_success "Ngrok deployment updated"
    else
        print_error "Failed to update Ngrok deployment"
        exit 1
    fi
    
    # Wait for rollout to complete
    print_status "Waiting for deployments to complete..."
    kubectl rollout status deployment/flask-app-deployment -n $NAMESPACE --timeout=300s
    kubectl rollout status deployment/ngrok-deployment -n $NAMESPACE --timeout=300s
    
    print_success "All deployments updated successfully"
}

# Function to run security scan (if trivy is available)
security_scan() {
    if command -v trivy &> /dev/null; then
        print_status "Running security scan on images..."
        
        print_status "Scanning Flask application image..."
        trivy image --severity HIGH,CRITICAL $APP_IMAGE:$TAG
        
        print_status "Scanning Ngrok image..."
        trivy image --severity HIGH,CRITICAL $NGROK_IMAGE:$TAG
        
        print_success "Security scans completed"
    else
        print_warning "Trivy not installed, skipping security scans"
        print_status "Install trivy: https://aquasecurity.github.io/trivy/v0.18.3/getting-started/installation/"
    fi
}

# Function to show image sizes
show_image_sizes() {
    print_status "Image sizes:"
    docker images | grep "$REGISTRY/$APP_NAME" | awk '{print $1 ":" $2 " - " $7}'
}

# Function to clean up old images
cleanup_images() {
    print_status "Cleaning up unused images..."
    
    # Remove dangling images
    docker image prune -f
    
    # Remove images older than 24 hours (optional)
    # docker images --filter "dangling=true" -q | xargs -r docker rmi
    
    print_success "Cleanup completed"
}

# Function to deploy to minikube
deploy_to_minikube() {
    print_status "Deploying to Minikube..."
    
    # Check if namespace exists, if not create it
    if ! kubectl get namespace $NAMESPACE &> /dev/null; then
        print_status "Creating namespace $NAMESPACE..."
        kubectl apply -f k8s/namespace.yaml
    fi
    
    # Apply all Kubernetes manifests
    for file in k8s/*.yaml; do
        if [ -f "$file" ]; then
            print_status "Applying $(basename $file)..."
            kubectl apply -f $file
        fi
    done
    
    # Wait for services to be ready
    print_status "Waiting for services to be ready..."
    kubectl wait --for=condition=available --timeout=300s deployment/flask-app-deployment -n $NAMESPACE
    kubectl wait --for=condition=available --timeout=300s deployment/ngrok-deployment -n $NAMESPACE
    
    # Show service URLs
    print_success "Deployment completed!"
    echo
    print_status "Service URLs:"
    minikube service list -n $NAMESPACE
}

# Function to show usage
usage() {
    echo "Leave Tracker Build Script"
    echo ""
    echo "Usage: $0 [TAG]"
    echo "  TAG: Docker image tag (default: latest)"
    echo ""
    echo "Examples:"
    echo "  $0              # Build with 'latest' tag"
    echo "  $0 v1.0.0       # Build with 'v1.0.0' tag"
    echo "  $0 test         # Build with 'test' tag"
    echo ""
    echo "Environment variables:"
    echo "  REGISTRY: Docker registry (default: your-registry)"
    echo "  NAMESPACE: Kubernetes namespace (default: leave-tracker)"
}

# Main execution
main() {
    echo -e "${BLUE}"
    echo "╔══════════════════════════════════════╗"
    echo "║    Leave Tracker Build Script        ║"
    echo "╚══════════════════════════════════════╝"
    echo -e "${NC}"
    
    # Show configuration
    print_status "Configuration:"
    echo "  Registry:    $REGISTRY"
    echo "  App Image:   $APP_IMAGE:$TAG"
    echo "  Ngrok Image: $NGROK_IMAGE:$TAG"
    echo "  Namespace:   $NAMESPACE"
    echo ""
    
    # Check if help is requested
    if [ "$1" == "-h" ] || [ "$1" == "--help" ]; then
        usage
        exit 0
    fi
    
    # Execute build steps
    check_dependencies
    build_images
    run_tests
    security_scan
    show_image_sizes
    
    # Ask for push confirmation
    echo
    read -p "Do you want to push images to registry? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        push_images
        
        # Ask for deployment confirmation
        echo
        read -p "Do you want to deploy to Minikube? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            update_deployments
        else
            print_status "Skipping deployment to Minikube"
        fi
    else
        print_status "Skipping push to registry"
    fi
    
    # Cleanup
    cleanup_images
    
    echo
    print_success "Build process completed successfully!"
    echo
    print_status "Next steps:"
    echo "  1. Check pod status: kubectl get pods -n $NAMESPACE"
    echo "  2. View logs: kubectl logs -f deployment/flask-app-deployment -n $NAMESPACE"
    echo "  3. Access ngrok dashboard: minikube service ngrok-service -n $NAMESPACE"
    echo "  4. Test Slack commands in your workspace"
}

# Run main function with all arguments
main "$@"