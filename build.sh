#!/bin/bash

# Leave Tracker Build Script (No Ngrok - Socket Mode)
set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
APP_NAME="leave-tracker"
REGISTRY="docker.io/kubekoushik"  # Change to your registry
APP_IMAGE="$REGISTRY/$APP_NAME-app"
TAG="${1:-latest}"
NAMESPACE="leave-tracker"

print_status() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

check_dependencies() {
    print_status "Checking dependencies..."
    for cmd in docker kubectl minikube; do
        if ! command -v $cmd &> /dev/null; then
            print_error "Missing: $cmd"
            exit 1
        fi
    done
    print_success "All dependencies installed"
}

build_image() {
    print_status "Building Flask application image..."
    docker build -t $APP_IMAGE:$TAG ./app
    if [ $? -eq 0 ]; then
        print_success "Image built: $APP_IMAGE:$TAG"
    else
        print_error "Build failed"
        exit 1
    fi
}

run_tests() {
    print_status "Running tests..."
    docker run --rm -e SLACK_BOT_TOKEN=test -e SLACK_SIGNING_SECRET=test $APP_IMAGE:$TAG python -c "
import sys
try:
    from app import flask_app
    from supabase_client import SupabaseClient
    print('✓ All imports successful')
    sys.exit(0)
except Exception as e:
    print(f'✗ Import error: {e}')
    sys.exit(1)
"
    [ $? -eq 0 ] && print_success "Tests passed" || (print_error "Tests failed" && exit 1)
}

push_image() {
    print_status "Pushing image to registry..."
    docker push $APP_IMAGE:$TAG
    [ $? -eq 0 ] && print_success "Image pushed" || (print_error "Push failed" && exit 1)
}

deploy_to_kubernetes() {
    print_status "Deploying to Kubernetes..."
    
    # Create namespace if not exists
    kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -
    
    # Apply all manifests
    for file in k8s/*.yaml; do
        [ -f "$file" ] && kubectl apply -f $file
    done
    
    # Update deployment
    kubectl set image deployment/flask-app-deployment flask-app=$APP_IMAGE:$TAG -n $NAMESPACE
    
    # Wait for rollout
    kubectl rollout status deployment/flask-app-deployment -n $NAMESPACE --timeout=300s
    
    print_success "Deployment completed"
}

show_status() {
    print_status "Application status:"
    kubectl get pods,svc -n $NAMESPACE
    echo
    print_status "To view logs: kubectl logs -f deployment/flask-app-deployment -n $NAMESPACE"
}

main() {
    echo -e "${BLUE}"
    echo "╔══════════════════════════════════════╗"
    echo "║    Leave Tracker (Socket Mode)       ║"
    echo "╚══════════════════════════════════════╝"
    echo -e "${NC}"
    
    echo "Configuration:"
    echo "  Registry: $REGISTRY"
    echo "  Image:    $APP_IMAGE:$TAG"
    echo "  Namespace: $NAMESPACE"
    echo
    
    check_dependencies
    build_image
    run_tests
    
    read -p "Push image to registry? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        push_image
        
        read -p "Deploy to Kubernetes? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            deploy_to_kubernetes
            show_status
        fi
    fi
    
    print_success "Build process completed!"
}

main "$@"