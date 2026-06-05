# Phase 2: KVM + OVN + OVS E2E PR Check

This document records the intended second-stage native Kubernetes PR check. It
is not implemented yet. The first-stage workflow only compiles manifests and
builds workload images on GitHub-hosted runners.

## Goal

Phase 2 should prove that the generated B61 native Kubernetes example can run
end to end on a KVM-backed K3s cluster using Kube-OVN and OVS.

The check should cover:

- KVM VM creation from `kvm.yaml`.
- K3s installation on the generated master and worker VMs.
- Kube-OVN/OVS fabric installation and validation.
- Native SeedEMU image build and push to the cluster registry.
- Manifest deployment with `make up`.
- Runtime validation that deployments and pods become ready.
- Cleanup with `make clean` and VM destruction.

Real physical-machine E2E is intentionally out of scope because it is expensive
and needs lab-specific hosts and secrets.

## Runner Requirements

The job must run on a dedicated self-hosted GitHub Actions runner, not on
`ubuntu-latest`.

Required runner labels:

```yaml
runs-on: [self-hosted, linux, x64, kvm, seedemu-k8s]
```

Required host capabilities:

- `/dev/kvm` is available.
- libvirt and `virsh` are installed and usable by the runner.
- the default libvirt network or configured bridge is available.
- Docker with buildx is available.
- enough CPU, memory, and disk exist for the B61 KVM topology.
- outbound network access is available for image and package downloads.

The runner should be isolated from long-running user clusters. If the same host
must be shared, VM names, libvirt storage pools, namespace names, registry ports,
and working directories must be unique to the CI run.

## Trigger Conditions

The workflow should appear on PRs but only run automatically for PRs from this
repository, not from forks.

Recommended trigger:

```yaml
on:
  pull_request:
    branches:
      - master
      - development
    paths:
      - "seedemu/compiler/kubernetes.py"
      - "seedemu/compiler/__init__.py"
      - "seedemu/k8sTools/**"
      - "examples/internet/b61_k8s_compile/**"
      - "tests/k8s/**"
      - ".github/workflows/k8s-*.yaml"
      - "setup.py"
      - "MANIFEST.in"
  workflow_dispatch:
```

Recommended job guard:

```yaml
if: github.event_name == 'workflow_dispatch' || github.event.pull_request.head.repo.full_name == github.repository
```

Recommended concurrency:

```yaml
concurrency:
  group: seedemu-k8s-kvm-e2e
  cancel-in-progress: false
```

The KVM E2E check should start as optional. After repeated stable runs, the
repository can decide whether to mark it as required for K8s-related PRs.

## Expected Flow

The job should use a fresh working directory and generate all stage artifacts
from committed files:

```bash
source development.env
python examples/internet/b61_k8s_compile/mini_internet_k8s.py \
  --output-dir examples/internet/b61_k8s_compile/output

cd examples/internet/b61_k8s_compile
python ./k8sTools.py build \
  --input configKvmOvn.yaml \
  --config-k3s configK3s.yaml \
  --kubeconfig kubeconfig.yaml
python ./k8sTools.py up -f ./output -k kubeconfig.yaml -d configK3s.yaml
python ./k8sTools.py down -f ./output -k kubeconfig.yaml
python ./k8sTools.py destroy -d configK3s.yaml
```

The final implementation should use CI-specific names and directories so that
parallel or failed runs do not collide with developer experiments.

## Cleanup Contract

Cleanup must run with `if: always()` or shell traps.

Required cleanup steps:

- `make clean || true` for the SeedEMU namespace.
- `destroyKvmVms.sh || true` for all VMs created by the job.
- remove any temporary local registry container used by the job.
- collect diagnostics before destruction when a failure occurs.

Do not run broad destructive commands such as `docker system prune` on a shared
self-hosted runner unless the runner is dedicated to this workflow.

## Failure Artifacts

Upload these artifacts on failure:

- compiled `k8s.kube-ovn.yaml` and `images.yaml`.
- generated `setup/*.yaml` and `running/configRunning.yaml`.
- K3s kubeconfig and inventory if they do not contain secrets.
- `kubectl get pods -A -o wide`.
- `kubectl describe pods -n seedemu-k8s-b61`.
- recent Kubernetes events.
- Kube-OVN pod status and relevant logs.
- `virsh list --all`.
- generated `kvmState.yaml`.

Secrets such as private SSH keys must never be uploaded.

## Success Criteria

The Phase 2 job should pass only when:

- all VMs are created and reachable;
- K3s nodes are Ready;
- Kube-OVN validation passes;
- all images from `images.yaml` build and push to the registry;
- `make up` completes and all SeedEMU workloads become Ready;
- `make clean` succeeds;
- `destroyKvmVms.sh` succeeds or confirms no CI-owned VMs remain.
