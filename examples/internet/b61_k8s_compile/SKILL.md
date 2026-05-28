---
name: seedemu-k8s-native-workflow
description: Use when working with a SeedEMU repository that contains seedemu/k8spre or examples/internet/b61_k8s_compile, especially to understand, generate, modify, or validate native Kubernetes/K3s deployment workflows for SeedEMU emulations using K8sPre, KVM, physical nodes, Multus, Linux VXLAN, or Kube-OVN/OVS.
---

# SeedEMU Native Kubernetes Workflow

Use this skill when the task involves building or modifying a SeedEMU simulation that will run on Kubernetes/K3s through `seedemu.k8spre`, or when a user asks how the K8sPre examples should be used.

## First Steps

1. Find the repository root without assuming an absolute path.
   - Start from the current working directory.
   - Walk upward until a directory contains both `setup.py` and `seedemu/`.
   - Prefer a root that also contains `seedemu/k8spre/README.md`.
   - If the current directory is not inside the repo, search the workspace with `rg --files` and look for `seedemu/k8spre/README.md` or `examples/internet/b61_k8s_compile/README.md`.
   - Do not hardcode paths from a previous machine. Use paths relative to the discovered repository root or paths supplied by the user.

2. Read the local documentation before making architectural claims.
   - `seedemu/k8spre/README.md`
   - `seedemu/k8spre/resources/setup/README.md`
   - `examples/internet/b61_k8s_compile/README.md`

3. For example-driven work, also inspect the relevant example files.
   - `examples/internet/b61_k8s_compile/compileK8sMiniInternet.py`
   - `examples/internet/b61_k8s_compile/kvm_ovn_ovs/writeKvmOvnExample.py`
   - `examples/internet/b61_k8s_compile/kvm_ovn_ovs/configKvmOvn.yaml`
   - `examples/internet/b61_k8s_compile/physical_ovn_ovs/writeOvnExample.py`
   - `examples/internet/b61_k8s_compile/physical_ovn_ovs/configK3sOvn.yaml`

Use `sed -n` or targeted `rg` reads. Avoid loading generated output directories unless the task specifically concerns runtime artifacts.

## Architecture Model

Think of the workflow as four separate contracts:

1. Compile contract:
   - `NativeKubernetesCompiler` turns a rendered SeedEMU emulator into Kubernetes manifests and Docker build contexts.
   - Expected outputs are under a compile output directory, commonly `emulate/output/`.
   - Important files are `k8s.kube-ovn.yaml` or `k8s.yaml`, `images.yaml`, per-node Docker build contexts, and sometimes `base_images/`.
   - The compiler should not depend on a live cluster inventory.

2. Setup contract:
   - `K8sPre` writes a user-visible `setup/` directory by copying packaged resources and writing YAML.
   - It is a generator and wrapper, not a replacement for KVM, K3s, registry, or CNI logic.
   - Persistent user configuration is YAML. Do not add new required environment variables.

3. Cluster contract:
   - KVM flow starts from `kvm.yaml`.
   - KVM creation writes `configK3s.yaml` and internal `kvmState.yaml`.
   - Physical-node flow starts from `configK3s.yaml`.
   - K3s build always reads `configK3s.yaml`; it should not infer cluster membership from ambient state.

4. Running contract:
   - `writeRunningScripts()` writes `running/configRunning.yaml` and a `Makefile`.
   - The running stage reads compile output and `setup/configK3s.yaml`.
   - `make preflight` checks readiness, `make build` builds and pushes images, `make up` renders `kustomization.yaml` and applies the workload, and `make clean` removes deployed workload resources.

## Supported Deployment Paths

KVM + K3s:

```python
from seedemu.k8spre import K8sPre

k = K8sPre()
k.writeKvmInstallScripts(output_root, config=kvm_config, connection="ovn", overwrite=True)
k.writeK3sBuildScripts(output_root, overwrite=True)
k.writeRunningScripts(output_root, output_dir=compile_output, overwrite=True)
```

The generated runtime order is:

```bash
cd <output-root>/setup
bash ./installKvmVms.sh
bash ./buildK3sCluster.sh

cd ../running
make preflight
make build
make up
```

Physical nodes + K3s:

```python
from seedemu.k8spre import K8sPre

k = K8sPre()
k.writePhysicalNodeScripts(output_root, config=k3s_config, connection="ovn", overwrite=True)
k.writeK3sBuildScripts(output_root, overwrite=True)
k.writeRunningScripts(output_root, output_dir=compile_output, overwrite=True)
```

The generated runtime order for OVN is:

```bash
cd <output-root>/setup
bash ./preparePhysicalNodes.sh ./configK3s.yaml
bash ./buildK3sCluster.sh
bash ./ovn/validateKubeOvnFabric.sh ./configK3s.yaml

cd ../running
make preflight
make build
make up
```

For Linux VXLAN physical-node flow, run the generated `vxlan/configureLinuxVxlanFabric.sh` and `vxlan/validateLinuxVxlanFabric.sh` before `buildK3sCluster.sh`.

## Backend Semantics

- Default KVM behavior uses compiler macvlan NetworkAttachmentDefinitions with parent interface `ens2`.
- `connection="ovn"` writes or preserves `fabric.type: ovn`, installs Kube-OVN as a non-primary CNI after K3s and Multus are available, and makes the running stage prefer `k8s.kube-ovn.yaml`.
- `connection="vxlan"` for physical nodes writes `fabric.type: linux-vxlan` and uses Linux bridge/VXLAN resources such as `br-seedemu` and `vxseed0`.
- K3s primary pod networking remains flannel. SeedEMU simulated secondary interfaces are attached through Multus.
- OVN mode uses Kube-OVN `Vpc`, `Subnet`, and `NetworkAttachmentDefinition` resources. Static IPs are provider annotations rather than macvlan `ips` entries.

## Path Handling Rules

Path handling is a common failure mode. Follow these rules:

- Never write the developer's machine-specific absolute path into generated docs, examples, or skills.
- Use repository-relative paths in documentation whenever possible.
- In Python examples, use a `findRepoRoot(start: Path)` helper like the b61 example does.
- When generating runtime directories, use caller-provided `--output-root` and `--compile-output` values, or derive paths from the discovered example directory.
- If a generated YAML must reference a path outside the generated tree, resolve it from the user's local repository root at runtime.
- Treat `setup/`, `running/`, `emulate/output/`, `image-cache/`, `cloud-init/`, and `kvmState.yaml` as generated or runtime artifacts unless the user explicitly asks to inspect them.

## Editing Guidance

When modifying K8sPre code or examples:

- Prefer the existing staged model instead of merging compile, setup, cluster build, and running behavior.
- Keep `configK3s.yaml` as the K3s build contract.
- Keep `kvmState.yaml` internal to KVM cleanup and safety checks.
- Do not reintroduce legacy API aliases or old CLI compatibility commands unless the user explicitly requests compatibility.
- If adding a backend, update all backend decision points consistently: resource copying, `fabric.type` normalization, K3s version defaults if needed, running manifest selection, README docs, and examples.
- For generated shell scripts, keep YAML as the source of truth and use helper Python commands to print shell-safe values.
- Avoid destructive tests unless the user explicitly wants real infrastructure changes.

## Validation

Use non-destructive checks first:

```bash
python3 -m py_compile seedemu/k8spre/*.py seedemu/k8spre/resources/setup/*.py seedemu/k8spre/resources/setup/kvm/*.py seedemu/k8spre/resources/running/*.py
for f in $(rg --files seedemu/k8spre/resources -g '*.sh'); do bash -n "$f"; done
```

For example smoke tests, write outputs under a temporary directory:

```bash
tmp_root="$(mktemp -d)"
compile_out="${tmp_root}/emulate-output"
python3 examples/internet/b61_k8s_compile/compileK8sMiniInternet.py --output-dir "${compile_out}"
python3 examples/internet/b61_k8s_compile/kvm_ovn_ovs/writeKvmOvnExample.py --output-root "${tmp_root}/kvm_ovn" --compile-output "${compile_out}"
python3 examples/internet/b61_k8s_compile/physical_ovn_ovs/writeOvnExample.py --output-root "${tmp_root}/physical_ovn" --compile-output "${compile_out}"
make -C "${tmp_root}/kvm_ovn/running" check-output
make -C "${tmp_root}/kvm_ovn/running" render-kustomization
make -C "${tmp_root}/physical_ovn/running" check-output
make -C "${tmp_root}/physical_ovn/running" render-kustomization
```

This verifies compile output and generated running manifests without creating VMs, installing K3s, pushing images, or applying Kubernetes resources.

Before running real setup commands, state the side effects clearly:

- `installKvmVms.sh` creates libvirt VMs, disks, DHCP reservations, cloud-init files, and host image caches.
- `buildK3sCluster.sh` installs or reinstalls K3s, starts registry, imports images, and may install Kube-OVN.
- `make build` builds and pushes Docker images.
- `make up` applies Kubernetes resources to the configured cluster.
- `destroyKvmVms.sh` and `destroyPhysicalCluster.sh` are destructive cleanup commands.
