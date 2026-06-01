#!/usr/bin/env bash
# Run the non-destructive native Kubernetes PR checks locally.
#
# Inputs:
# - optional --output-dir path for compiler output.
# - optional --build-images to also build/push images to a local registry.
# - optional --registry-prefix host:port for the image build check.
#
# Generated outputs:
# - compiler output under the selected output directory.
#
# Side effects:
# - without --build-images: none outside the output directory.
# - with --build-images: starts a temporary local Docker registry when the
#   registry prefix points at localhost, builds images, pushes them, and removes
#   the registry container before exit.
#
# Expected context:
# - repository checkout with Python 3.10+, PyYAML, and compile dependencies.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
OUTPUT_DIR=""
BUILD_IMAGES="false"
REGISTRY_PREFIX="127.0.0.1:5000"
IMAGE_REGISTRY_PREFIX="seedemu"
NAMESPACE="seedemu-k8s-b61"

usage() {
    cat <<EOF
Usage: $0 [--output-dir output] [--build-images] [--registry-prefix host:port]

Run the same native Kubernetes checks used by .github/workflows/k8s-check.yaml.
The default run compiles and validates output without creating VMs or a cluster.
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --build-images)
            BUILD_IMAGES="true"
            shift
            ;;
        --registry-prefix)
            REGISTRY_PREFIX="$2"
            shift 2
            ;;
        --image-registry-prefix)
            IMAGE_REGISTRY_PREFIX="$2"
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
    OUTPUT_DIR="$(mktemp -d)/seedemu-k8s-output"
fi

cd "${REPO_ROOT}"
source development.env

python3 tests/k8s/validateK8sStatic.py
python3 examples/internet/b61_k8s_compile/mini_internet_k8s.py \
    --output-dir "${OUTPUT_DIR}"
python3 tests/k8s/validateNativeK8sOutput.py \
    --output-dir "${OUTPUT_DIR}" \
    --expected-namespace "${NAMESPACE}" \
    --image-registry-prefix "${IMAGE_REGISTRY_PREFIX}"

if [ "${BUILD_IMAGES}" = "true" ]; then
    bash tests/k8s/buildNativeK8sImages.sh \
        --output-dir "${OUTPUT_DIR}" \
        --registry-prefix "${REGISTRY_PREFIX}" \
        --image-registry-prefix "${IMAGE_REGISTRY_PREFIX}"
fi

echo "Native K8s PR checks completed for ${OUTPUT_DIR}."
