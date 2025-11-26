#!/bin/bash
# Load Podman images into k3s containerd

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}Loading local Podman images into k3s...${NC}"

# Export from Podman
echo -e "\n${YELLOW}Step 1: Exporting images from Podman...${NC}"
podman save chatbot:latest -o /tmp/chatbot.tar
podman save thruk-mcp:latest -o /tmp/thruk-mcp.tar
echo -e "${GREEN}✓ Images exported${NC}"

# Import into k3s
echo -e "\n${YELLOW}Step 2: Importing images into k3s containerd...${NC}"
sudo k3s ctr images import /tmp/chatbot.tar
sudo k3s ctr images import /tmp/thruk-mcp.tar
echo -e "${GREEN}✓ Images imported${NC}"

# Cleanup
echo -e "\n${YELLOW}Step 3: Cleaning up temporary files...${NC}"
rm /tmp/chatbot.tar /tmp/thruk-mcp.tar
echo -e "${GREEN}✓ Cleanup complete${NC}"

# Verify
echo -e "\n${YELLOW}Verifying images in k3s:${NC}"
sudo k3s ctr images ls | grep -E "localhost/chatbot|localhost/thruk-mcp"

echo -e "\n${GREEN}✓ Done! Images are ready to use in k3s${NC}"
echo -e "\n${YELLOW}Images imported as:${NC}"
echo -e "  - localhost/chatbot:latest"
echo -e "  - localhost/thruk-mcp:latest"
echo -e "\n${YELLOW}Note: Make sure your deployment uses these image names${NC}"
