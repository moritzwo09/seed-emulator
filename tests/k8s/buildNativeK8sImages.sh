#!/usr/bin/env bash
# Build native SeedEMU Kubernetes workload images for PR checks.
#
# Inputs:
# - --output-dir: compile output containing k8s.kube-ovn.yaml, images.yaml,
#   base_images/, and per-node Docker build contexts.
# - --registry-prefix: local registry host:port used for image pushes.
# - --image-registry-prefix: logical compiler image prefix to rewrite.
#
# Generated outputs:
# - Docker images tagged under the selected registry prefix.
#
# Side effects:
# - starts a temporary local Docker registry when the registry host is
#   127.0.0.1 or localhost;
# - builds images with docker buildx;
# - pushes workload images to the local registry;
# - removes the temporary registry before exit.
#
# Expected context:
# - GitHub-hosted Ubuntu runner or local developer machine with Docker,
#   buildx, Python 3, and PyYAML.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
OUTPUT_DIR=""
REGISTRY_PREFIX="127.0.0.1:5000"
IMAGE_REGISTRY_PREFIX="seedemu"
REGISTRY_NAME="seedemu-native-k8s-ci-registry"
STARTED_REGISTRY=""
ORIGINAL_BUILDER=""
if command -v docker >/dev/null 2>&1; then
    ORIGINAL_BUILDER="$(
        docker buildx ls 2>/dev/null |
        awk 'NR > 1 && $1 ~ /\*$/ {gsub(/\*/, "", $1); builder=$1} END {print builder}' ||
        true
    )"
fi

usage() {
    cat <<EOF
Usage: $0 --output-dir output [--registry-prefix host:port] [--image-registry-prefix seedemu]

Build every image listed in images.yaml and push the rewritten tags to a local
registry. This does not create a Kubernetes cluster or KVM virtual machines.
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --registry-prefix)
            REGISTRY_PREFIX="$2"
            shift 2
            ;;
        --image-registry-prefix)
            IMAGE_REGISTRY_PREFIX="$2"
            shift 2
            ;;
        --registry-name)
            REGISTRY_NAME="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

if [ -z "${OUTPUT_DIR}" ]; then
    echo "--output-dir is required" >&2
    usage >&2
    exit 1
fi

OUTPUT_DIR="$(cd "${OUTPUT_DIR}" && pwd)"
RUNNING_DIR="${REPO_ROOT}/seedemu/k8sTools/resources/running"
MANIFEST_HELPER="${RUNNING_DIR}/manageK8sManifest.py"
BUILD_SCRIPT="${RUNNING_DIR}/buildRegistryImages.py"
IMAGES_YAML="${OUTPUT_DIR}/images.yaml"

cleanup() {
    if [ -n "${STARTED_REGISTRY}" ]; then
        docker rm -f "${STARTED_REGISTRY}" >/dev/null 2>&1 || true
    fi
    if [ -n "${ORIGINAL_BUILDER}" ]; then
        docker buildx use "${ORIGINAL_BUILDER}" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

requireFile() {
    # Args:
    #   $1: file path that must exist.
    local path="$1"
    if [ ! -f "${path}" ]; then
        echo "Required file not found: ${path}" >&2
        exit 1
    fi
}

startLocalRegistryIfNeeded() {
    # Args:
    #   $1: registry prefix in host:port form.
    local prefix="$1"
    local host="${prefix%%:*}"
    local port="${prefix##*:}"
    if [ "${host}" != "127.0.0.1" ] && [ "${host}" != "localhost" ]; then
        return 0
    fi
    if [ "${port}" = "${prefix}" ]; then
        echo "Local registry prefix must include a port: ${prefix}" >&2
        exit 1
    fi
    docker rm -f "${REGISTRY_NAME}" >/dev/null 2>&1 || true
    docker run -d --name "${REGISTRY_NAME}" -p "${port}:5000" registry:2 >/dev/null
    STARTED_REGISTRY="${REGISTRY_NAME}"
}

selectDockerDriverBuilder() {
    # Use a docker driver builder so --load images are visible as local FROM
    # dependencies to later builds in the same check.
    local default_driver
    default_driver="$(docker buildx inspect default 2>/dev/null | awk -F: '$1 == "Driver" {driver=$2} END {gsub(/^[ \t]+|[ \t]+$/, "", driver); print driver}')"
    if [ "${default_driver}" != "docker" ]; then
        echo "Docker buildx default builder must use the docker driver for native K8s image checks." >&2
        exit 1
    fi
    docker buildx use default >/dev/null
}

verifyPushedImages() {
    # Args:
    #   $1: images.yaml path.
    #   $2: logical compiler image prefix.
    #   $3: pushed registry prefix.
    local images_yaml="$1"
    local image_registry_prefix="$2"
    local registry_prefix="$3"
    python3 "${MANIFEST_HELPER}" mapped-images \
        --images-yaml "${images_yaml}" \
        --image-registry-prefix "${image_registry_prefix}" \
        --registry-prefix "${registry_prefix}" |
    while IFS=$'\t' read -r image _context; do
        [ -n "${image}" ] || continue
        echo "+ docker pull ${image}"
        docker pull "${image}" >/dev/null
    done
}

requireFile "${IMAGES_YAML}"
requireFile "${MANIFEST_HELPER}"
requireFile "${BUILD_SCRIPT}"

docker info >/dev/null
docker buildx version >/dev/null

selectDockerDriverBuilder
startLocalRegistryIfNeeded "${REGISTRY_PREFIX}"

python3 "${BUILD_SCRIPT}" \
    --output-dir "${OUTPUT_DIR}" \
    --registry-prefix "${REGISTRY_PREFIX}" \
    --image-registry-prefix "${IMAGE_REGISTRY_PREFIX}"

verifyPushedImages "${IMAGES_YAML}" "${IMAGE_REGISTRY_PREFIX}" "${REGISTRY_PREFIX}"

echo "Native K8s image build check completed for ${OUTPUT_DIR}."
