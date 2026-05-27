# B61 K8s Compile

This example demonstrates the native Kubernetes compiler and the
`seedemu.k8spre` setup/running workflow with Kube-OVN/OVS as the secondary
network fabric.

It contains two runnable paths that consume the same compiled SeedEMU topology:

- `kvm_ovn_ovs/`: create KVM VMs, then build a K3s cluster with Kube-OVN/OVS.
- `physical_ovn_ovs/`: use existing machines, then build a K3s cluster with Kube-OVN/OVS.

Kube-OVN installs OVN and OVS components in Kubernetes. The compiler emits
portable Multus/macvlan-style NetworkAttachmentDefinitions; the generated
running stage rewrites them to Kube-OVN VPC/Subnet/NAD resources when
`configK3s.yaml` contains `fabric.type: ovn`.

## Quick Start

Choose one path.

KVM path:

```bash
cd examples/internet/b61_k8s_compile
python3 ./compileK8sMiniInternet.py
python3 ./kvm_ovn_ovs/writeKvmOvnExample.py

cd ./kvm_ovn_ovs/setup
bash ./installKvmVms.sh
bash ./buildK3sCluster.sh
bash ./ovn/validateKubeOvnFabric.sh ./configK3s.yaml

cd ../running
make preflight
make build
make up
make clean

cd ../setup
bash ./destroyKvmVms.sh
```

Physical-machine path:

```bash
cd examples/internet/b61_k8s_compile
python3 ./compileK8sMiniInternet.py
python3 ./physical_ovn_ovs/writeOvnExample.py

cd ./physical_ovn_ovs/setup
bash ./preparePhysicalNodes.sh ./configK3s.yaml
bash ./buildK3sCluster.sh
bash ./ovn/validateKubeOvnFabric.sh ./configK3s.yaml

cd ../running
make preflight
make build
make up
make clean

cd ../setup
bash ./destroyPhysicalCluster.sh ./configK3s.yaml
```

The setup commands create or modify real infrastructure. The KVM path creates
libvirt VMs. The physical-machine path can install or reinstall K3s on the
machines listed in `physical_ovn_ovs/configK3sOvn.yaml`.

## Prerequisites

Both paths require Python 3.10 or newer, Docker/buildx, `kubectl`,
`ansible-playbook`, `ssh`, `scp`, and `curl`.

The KVM path also requires libvirt/KVM tooling such as `virsh`, `virt-install`,
`qemu-img`, and a working libvirt `default` network.

The physical-machine path requires each configured node to be reachable from
the control host with SSH key authentication and non-interactive sudo
(`sudo -n`).

## SSH Key Setup

The `key` values in the YAML files are paths to private SSH keys on the control
host. These keys are used by the setup scripts to connect to KVM guests or
physical machines.

Generate a dedicated key pair on the control host:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/seedemu_k8s -C "seedemu-k8s"
chmod 600 ~/.ssh/seedemu_k8s
ssh-keygen -y -f ~/.ssh/seedemu_k8s > ~/.ssh/seedemu_k8s.pub
```

Update the example YAML to use the private key path:

```yaml
ssh:
  user: ubuntu
  key: ~/.ssh/seedemu_k8s
```

For physical machines, set each node's SSH user and key:

```yaml
nodes:
- name: worker1
  role: worker
  ip: 192.0.2.11
  ssh:
    user: seed
    key: ~/.ssh/seedemu_k8s
```

KVM key behavior:

- `kvm/createKvmVms.sh` reads `${ssh.key}.pub` when it exists.
- If `${ssh.key}.pub` is missing, it derives the public key with
  `ssh-keygen -y -f "${ssh.key}"`.
- The public key is injected into each VM through cloud-init
  `ssh_authorized_keys`.
- The generated `setup/configK3s.yaml` keeps the same private key path for the
  later K3s/Ansible stage.

Physical-machine key behavior:

- The scripts do not create user accounts or install public keys on existing
  machines.
- The public key must already be in each remote user's
  `~/.ssh/authorized_keys`.
- A node with `connection: local` is executed locally, but worker nodes still
  need reachable SSH keys.

Install the generated public key on a remote physical node:

```bash
ssh-copy-id -i ~/.ssh/seedemu_k8s.pub seed@192.0.2.11
ssh -i ~/.ssh/seedemu_k8s seed@192.0.2.11 'sudo -n true'
```

If `ssh-copy-id` is unavailable, append the public key manually:

```bash
cat ~/.ssh/seedemu_k8s.pub | ssh seed@192.0.2.11 \
  'mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys'
```

If `sudo -n true` fails, configure passwordless sudo on that node using an
administrator account:

```bash
echo 'seed ALL=(ALL) NOPASSWD:ALL' | sudo tee /etc/sudoers.d/seedemu-k8s
sudo chmod 440 /etc/sudoers.d/seedemu-k8s
```

## Workflow Details

Compile stage:

- Input: `compileK8sMiniInternet.py`.
- Command: `python3 ./compileK8sMiniInternet.py`.
- Output: `emulate/output/k8s.kube-ovn.yaml`,
  `emulate/output/images.yaml`, per-node Docker build contexts, and optional
  `base_images/` contexts.
- Consumer: generated `running/Makefile`.

KVM setup stage:

- Input: `kvm_ovn_ovs/configKvmOvn.yaml`.
- Generator: `kvm_ovn_ovs/writeKvmOvnExample.py`.
- Output: `kvm_ovn_ovs/setup/` and `kvm_ovn_ovs/running/`.
- `installKvmVms.sh` creates libvirt VMs, qcow2 disks, cloud-init files,
  `configK3s.yaml`, and `kvmState.yaml`.
- `buildK3sCluster.sh` installs K3s, starts the master registry, installs
  Multus and Kube-OVN/OVS, imports bootstrap images, and writes kubeconfig and
  inventory outputs.

Physical setup stage:

- Input: `physical_ovn_ovs/configK3sOvn.yaml`.
- Generator: `physical_ovn_ovs/writeOvnExample.py`.
- Output: `physical_ovn_ovs/setup/` and `physical_ovn_ovs/running/`.
- `preparePhysicalNodes.sh` validates SSH, `sudo -n`, and baseline commands.
- `buildK3sCluster.sh` installs or reinstalls K3s, starts the master registry,
  installs Multus and Kube-OVN/OVS, imports bootstrap images, and writes
  kubeconfig and inventory outputs.

Running stage:

- Input: generated `running/configRunning.yaml`, `setup/configK3s.yaml`, and
  `emulate/output/`.
- `make preflight` checks compile output, kubeconfig, registry, cluster health,
  and node registry reachability.
- `make build` builds SeedEMU workload images and pushes them to the generated
  registry.
- `make up` deploys the compiled namespace and workloads.

## YAML Fields

`kvm_ovn_ovs/configKvmOvn.yaml`:

| Field | Required | Default | Consumer |
| --- | --- | --- | --- |
| `clusterName` | Optional | `seedemu-b61-kvm` in this example | `K8sPre`, setup scripts |
| `defaults.masterName` | Optional | `seed-k3s-master` | KVM VM planning |
| `defaults.workerNamePrefix` | Optional | `seed-k3s-worker` | KVM VM planning |
| `defaults.ipPrefix` | Optional | `192.168.122` | KVM VM planning |
| `defaults.masterIpStart` | Optional | `110` | KVM VM planning |
| `defaults.workerIpStart` | Optional | `111` | KVM VM planning |
| `defaults.macPrefix` | Optional | `52:54:00:64:10` | KVM VM planning |
| `defaults.masterMacStart` | Optional | `16` | KVM VM planning |
| `defaults.workerMacStart` | Optional | `17` | KVM VM planning |
| `master.vcpus` | Optional | `12` | `kvm/createKvmVms.sh` |
| `master.memoryMb` | Optional | `10240` | `kvm/createKvmVms.sh` |
| `master.diskGb` | Optional | `80` | `kvm/createKvmVms.sh` |
| `workers.count` | Optional | `2` | `kvm/createKvmVms.sh` |
| `workers.vcpus` | Optional | `6` | `kvm/createKvmVms.sh` |
| `workers.memoryMb` | Optional | `10240` | `kvm/createKvmVms.sh` |
| `workers.diskGb` | Optional | `80` | `kvm/createKvmVms.sh` |
| `kvm.legacyBaseImagePath` | Optional | previous local output path | KVM base-image preparation |
| `kvm.baseImageSearchDirs` | Optional | `~/k8s/output` | KVM base-image preparation |
| `ssh.user` | Optional | `ubuntu` | KVM cloud-init and SSH access |
| `ssh.key` | Optional | `~/.ssh/id_ed25519` | KVM/K3s SSH access |

This example pins KVM names to `seedemu-b61-kvm-*`, IPs to
`192.168.122.200+`, and MACs to `52:54:00:61:10:c8+` so it does not collide
with an existing `seed-k3s-*` KVM cluster on the same libvirt network.
It also sets `kvm.legacyBaseImagePath: ""` and
`kvm.baseImageSearchDirs: []` so the first KVM setup run downloads the Ubuntu
cloud image from `kvm.baseImageUrl` instead of reusing an old local output
tree.

`writeKvmOvnExample.py` injects `fabric.type: ovn`, the K3s version required
by the bundled Kube-OVN installer, and `seedemu.dockerImagesDir` into the
generated `kvm.yaml`. When the generated setup directory is inside this source
tree, `seedemu.dockerImagesDir` is written as a relative path; otherwise it is
written as an absolute path so temporary generated directories still work.

`physical_ovn_ovs/configK3sOvn.yaml`:

| Field | Required | Default | Consumer |
| --- | --- | --- | --- |
| `clusterName` | Optional | `seedemu-b61-physical` in this example | `K8sPre`, setup scripts |
| `nodes[].name` | Optional | role-based generated names | K3s node-name and inventory |
| `nodes[].role` | Required | none | `manageK3sConfig.py` |
| `nodes[].ip` | Required | none | SSH, registry, kubeconfig |
| `nodes[].connection` | Optional | auto-detect local/ssh | setup/running scripts |
| `nodes[].ssh.user` | Required | top-level `ssh.user` if present | SSH access |
| `nodes[].ssh.key` | Required | top-level `ssh.key` if present | SSH access |

`writeOvnExample.py` injects `fabric.type: ovn`, the K3s version required by
the bundled Kube-OVN installer, and `seedemu.dockerImagesDir` into the
generated `configK3s.yaml`. When the generated setup directory is inside this
source tree, `seedemu.dockerImagesDir` is written as a relative path; otherwise
it is written as an absolute path.

## Files

| Path | Role |
| --- | --- |
| `compileK8sMiniInternet.py` | Executable compiler example. It writes compiler output under `emulate/output/`. |
| `kvm_ovn_ovs/configKvmOvn.yaml` | User input for the KVM path. It selects VM resources and SSH settings. |
| `kvm_ovn_ovs/writeKvmOvnExample.py` | Generator for KVM `setup/` and `running/` directories. |
| `physical_ovn_ovs/configK3sOvn.yaml` | User input for the physical-machine path. It lists master and worker nodes. |
| `physical_ovn_ovs/writeOvnExample.py` | Generator for physical-node `setup/` and `running/` directories. |
| `*/setup/` | Generated runtime directory. It is ignored by Git and regenerated by the writer scripts. |
| `*/running/` | Generated runtime directory. It is ignored by Git and regenerated by the writer scripts. |
| `emulate/output/` | Generated compiler output. It contains `k8s.kube-ovn.yaml`, `images.yaml`, and image build contexts. It is ignored by Git and regenerated by `compileK8sMiniInternet.py`. |

## Runtime Notes

- No `image-cache/` directory is committed. The first real setup run recreates
  `image-cache/` from network pulls or local Docker builds.
- Do not copy old image caches from previous experiments into this example.
- Generated `running/configRunning.yaml` uses relative paths when setup,
  running, and compile output live near each other in this source tree.
- `buildK3sCluster.sh` may reinstall K3s because generated configs default to
  `k3s.forceReinstall: true` unless overridden.
- The physical example currently points to `10.202.236.88` as the local master
  and `10.202.191.39` as a worker. Edit `physical_ovn_ovs/configK3sOvn.yaml`
  before running it on a different machine set.
- `make clean` removes the deployed SeedEMU resources and namespace.
- Use `destroyKvmVms.sh` for KVM VM cleanup or `destroyPhysicalCluster.sh` for
  physical K3s cleanup.
