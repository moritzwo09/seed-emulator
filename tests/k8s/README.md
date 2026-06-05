# Native Kubernetes PR Checks

This directory contains the first-stage GitHub PR checks for the
`seedemu.k8sTools` native Kubernetes workflow.

## PR Workflow

`.github/workflows/k8s-check.yaml` runs automatically on PRs that touch native
K8s compiler, k8sTools, B61 example, packaging, Docker image sources, or these
test helpers.

The workflow has three jobs:

- `K8s Static`: compiles Python sources, runs `bash -n` on shell resources,
  parses YAML files, and rejects checked-in host-local absolute paths.
- `K8s Compile`: compiles the B61 native K8s example and validates generated
  Kube-OVN manifests plus `images.yaml`.
- `K8s Build Images`: builds every image listed in `images.yaml`, pushes to a
  temporary local registry, then pulls the pushed images back for verification.
  This job recompiles the B61 output in its own runner so generated
  `base_images/` contexts are present before Docker builds start.

These jobs do not create KVM VMs, install K3s, or apply Kubernetes resources.
The destructive KVM/K3s E2E plan is documented separately in
`PHASE2_KVM_E2E.md`.

## Local Reproduction

Run the non-destructive checks:

```bash
bash tests/k8s/runNativeK8sPrCheck.sh
```

Also build and push workload images to a temporary local registry:

```bash
bash tests/k8s/runNativeK8sPrCheck.sh --build-images
```
