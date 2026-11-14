#!/usr/bin/env bash
set -Eeuo pipefail

project_dir="/home/ec2-user/Financial-Assitant"
env_file="/home/ec2-user/.env"
repo_url="https://github.com/phanideepika540/Financial-Assitant.git"
container_name="ai-finance-assistant"
volume_name="finance-assistant-data"
deploy_tag="deploy-$(date -u +%Y%m%d%H%M%S)"
new_image="ai-finance-assistant:${deploy_tag}"

if [[ ! -f "$env_file" ]]; then
    echo "ERROR: $env_file is missing. Create it securely before deployment." >&2
    exit 1
fi

if [[ ! -s "$env_file" ]] || ! grep -q '^DATABASE_URL=.' "$env_file"; then
    echo "ERROR: $env_file must contain a non-empty DATABASE_URL entry." >&2
    exit 1
fi

sudo dnf install -y git docker
sudo systemctl enable --now docker

if [[ -d "$project_dir/.git" ]]; then
    if [[ -n "$(git -C "$project_dir" status --porcelain)" ]]; then
        echo "ERROR: The project has local changes. Commit, stash, or review them before deploying." >&2
        exit 1
    fi
    git -C "$project_dir" pull --ff-only
elif [[ ! -e "$project_dir" ]]; then
    git clone "$repo_url" "$project_dir"
else
    echo "ERROR: $project_dir exists but is not a Git checkout." >&2
    exit 1
fi

cd "$project_dir"
sudo docker build -t "$new_image" .

old_image=""
had_old_container=false
if sudo docker container inspect "$container_name" >/dev/null 2>&1; then
    old_image="$(sudo docker inspect --format '{{.Config.Image}}' "$container_name")"
    had_old_container=true
    sudo docker stop "$container_name"
    sudo docker rm "$container_name"
fi

start_container() {
    local image="$1"
    sudo docker run -d \
        --name "$container_name" \
        --restart unless-stopped \
        --env-file "$env_file" \
        -p 8000:8000 \
        -v "${volume_name}:/app/data" \
        "$image"
}

restore_previous() {
    if [[ "$had_old_container" == true ]]; then
        echo "Restoring the previous image: $old_image" >&2
        start_container "$old_image" >&2 || true
    fi
}

if ! start_container "$new_image"; then
    restore_previous
    exit 1
fi

healthy=false
for _ in {1..45}; do
    state="$(sudo docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_name" 2>/dev/null || true)"
    if [[ "$state" == "healthy" || "$state" == "running" ]]; then
        healthy=true
        break
    fi
    if [[ "$state" == "unhealthy" || "$state" == "exited" ]]; then
        break
    fi
    sleep 2
done

if [[ "$healthy" != true ]]; then
    echo "ERROR: New container did not become healthy. Recent logs:" >&2
    sudo docker logs --tail 50 "$container_name" >&2 || true
    sudo docker rm -f "$container_name" >/dev/null 2>&1 || true
    restore_previous
    exit 1
fi

echo "Deployment image: $new_image"
sudo docker ps --filter "name=^/${container_name}$"
echo "Recent application logs:"
sudo docker logs --tail 30 "$container_name"
