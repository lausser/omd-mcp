#!/bin/bash
# Kubernetes deployment helper script for MCP Chatbot

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}==============================================================${NC}"
echo -e "${GREEN}  MCP Chatbot - Kubernetes Deployment${NC}"
echo -e "${GREEN}==============================================================${NC}"

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo -e "${RED}Error: kubectl not found. Please install kubectl first.${NC}"
    exit 1
fi

# Function to deploy
deploy() {
    echo -e "\n${YELLOW}Step 1: Verifying namespace exists...${NC}"
    if ! kubectl get namespace demodemo &> /dev/null; then
        echo -e "${RED}Error: Namespace 'demodemo' does not exist. Please create it first.${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ Namespace 'demodemo' exists${NC}"

    echo -e "\n${YELLOW}Step 2: Creating secret from .env file...${NC}"
    if [ ! -f .env ]; then
        echo -e "${RED}Error: .env file not found. Copy .env.example to .env and configure it.${NC}"
        exit 1
    fi

    # Delete existing secret if it exists
    kubectl delete secret chatbot-secrets -n demodemo 2>/dev/null || true

    # Create secret from .env file
    kubectl create secret generic chatbot-secrets \
        --from-env-file=.env \
        --namespace=demodemo

    echo -e "${GREEN}✓ Secret created from .env${NC}"

    echo -e "\n${YELLOW}Step 3: Applying all resources...${NC}"
    kubectl apply -f kubernetes-deployment.yaml

    echo -e "\n${YELLOW}Step 4: Waiting for deployment to be ready...${NC}"
    kubectl wait --for=condition=available --timeout=300s deployment/chatbot-deployment -n demodemo

    echo -e "\n${GREEN}✓ Deployment successful!${NC}"
    echo -e "\n${YELLOW}Deployment status:${NC}"
    kubectl get all -n demodemo

    echo -e "\n${YELLOW}Access information:${NC}"
    echo -e "  Web UI: http://localhost:30800"
    echo -e "  Or use: kubectl port-forward -n demodemo svc/chatbot-service 8000:8000"
    echo -e "\n${YELLOW}View logs:${NC}"
    echo -e "  Chatbot:   kubectl logs -n demodemo -l app=chatbot -c chatbot -f"
    echo -e "  Thruk MCP: kubectl logs -n demodemo -l app=chatbot -c thruk-mcp -f"
}

# Function to undeploy
undeploy() {
    echo -e "\n${YELLOW}Removing all resources...${NC}"
    kubectl delete -f kubernetes-deployment.yaml || true
    kubectl delete secret chatbot-secrets -n demodemo || true
    echo -e "${GREEN}✓ Resources removed${NC}"
}

# Function to update secrets
update_secrets() {
    echo -e "\n${YELLOW}Updating secrets from .env file...${NC}"
    if [ ! -f .env ]; then
        echo -e "${RED}Error: .env file not found.${NC}"
        exit 1
    fi

    # Delete existing secret
    kubectl delete secret chatbot-secrets -n demodemo 2>/dev/null || true

    # Create new secret from .env
    kubectl create secret generic chatbot-secrets \
        --from-env-file=.env \
        --namespace=demodemo

    echo -e "${GREEN}✓ Secret updated${NC}"
    echo -e "\n${YELLOW}Restarting deployment to pick up new secrets...${NC}"
    kubectl rollout restart deployment/chatbot-deployment -n demodemo
    kubectl rollout status deployment/chatbot-deployment -n demodemo
    echo -e "${GREEN}✓ Deployment restarted${NC}"
}

# Function to show logs
logs() {
    CONTAINER=${1:-chatbot}
    echo -e "${YELLOW}Showing logs for container: ${CONTAINER}${NC}"
    kubectl logs -n demodemo -l app=chatbot -c ${CONTAINER} -f
}

# Function to show status
status() {
    echo -e "${YELLOW}Deployment status:${NC}"
    kubectl get all -n demodemo
    echo -e "\n${YELLOW}ConfigMaps and Secrets:${NC}"
    kubectl get configmaps,secrets -n demodemo
    echo -e "\n${YELLOW}Pod details:${NC}"
    kubectl describe pod -n demodemo -l app=chatbot
}

# Function to port-forward
port_forward() {
    echo -e "${YELLOW}Starting port-forward to chatbot service...${NC}"
    echo -e "${GREEN}Access the chatbot at: http://localhost:8000${NC}"
    kubectl port-forward -n demodemo svc/chatbot-service 8000:8000
}

# Main menu
case "${1:-}" in
    deploy)
        deploy
        ;;
    undeploy|delete)
        undeploy
        ;;
    update-secrets)
        update_secrets
        ;;
    logs)
        logs ${2:-chatbot}
        ;;
    status)
        status
        ;;
    port-forward|pf)
        port_forward
        ;;
    restart)
        echo -e "${YELLOW}Restarting deployment...${NC}"
        kubectl rollout restart deployment/chatbot-deployment -n demodemo
        kubectl rollout status deployment/chatbot-deployment -n demodemo
        echo -e "${GREEN}✓ Deployment restarted${NC}"
        ;;
    *)
        echo "Usage: $0 {deploy|undeploy|update-secrets|logs|status|port-forward|restart}"
        echo ""
        echo "Commands:"
        echo "  deploy         - Deploy all resources to Kubernetes"
        echo "  undeploy       - Remove all resources from Kubernetes"
        echo "  update-secrets - Update secrets from .env and restart deployment"
        echo "  logs [name]    - Show logs (chatbot or thruk-mcp)"
        echo "  status         - Show deployment status"
        echo "  port-forward   - Port-forward to access the service locally"
        echo "  restart        - Restart the deployment"
        echo ""
        echo "Examples:"
        echo "  $0 deploy"
        echo "  $0 update-secrets"
        echo "  $0 logs chatbot"
        echo "  $0 logs thruk-mcp"
        echo "  $0 port-forward"
        exit 1
        ;;
esac
