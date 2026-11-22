# Verifying the Restore Environment on Target Nodes and CPU Architectures

A CRaC checkpoint can be created on one node and restored on another node, yet this capability depends on compatibility between the two environments. The fact that both nodes run Linux or carry the same `amd64` label is not enough to conclude that restore will succeed. The JVM may have used CPU instruction sets that the target node does not support; CRIU may require a kernel feature that is not enabled; the container may lack required capabilities, mounts, or permissions; and the JDK/CRIU on the target node may be incompatible with the image.

In Kubernetes, the default scheduler only knows node attributes published via labels and resources. It does not inspect a CRaC checkpoint to learn whether the image requires AVX2, AVX-512, a specific kernel version, or specific mounts. Therefore, the pipeline must verify the target environment beforehand, store a compatibility profile alongside the checkpoint, and then use node labels/affinity to restrict Pods to the verified group of nodes.

The proper process has three layers: **verify architecture and CPU**, **verify OS, CRIU, and runtime permissions**, and then **test restoring on the exact container image and node pool planned for deployment**. Static check commands catch differences early; a restore test is the final proof that the image set works in the real environment.

## 1. Compatibility Is More Than Just the CPU Architecture Name

A checkpoint contains the state of a running process, including registers, memory maps, JIT-compiled code, and runtime state. When restoring on another machine, these components must be supported by the target environment.

Factors to compare:

- Instruction set architecture: x86-64, AArch64/ARM64, or another architecture.
- CPU features used by the JVM: SSE, AVX, AVX2, AVX-512, AES, and related capabilities.
- FPU state and how the CPU supports XSAVE.
- JDK vendor, full version, build, architecture, and native libraries.
- Linux kernel, kernel configuration, and namespace/cgroup features.
- CRIU version and the engine used by the CRaC JDK.
- Container runtime, security context, and Linux capabilities.
- Filesystem, mount paths, referenced files, and access permissions.
- Available RAM, huge pages, cgroup limits, and other resources needed to remap memory.

Spring Boot describes restoring on another machine as a possibility when the operating system and CPU architecture are similar. That does not mean a checkpoint can be moved arbitrarily between any two nodes sharing an OS name or architecture. [Spring Boot: Checkpoint and Restore With the JVM](https://docs.spring.io/spring-boot/reference/packaging/checkpoint-restore.html)

### 1.1. Do Not Restore Across Architectures

A checkpoint created by a JVM on `x86_64` is not an image that can be transferred directly to `aarch64`. Register state, instruction set, JIT-compiled machine code, ABI, and JDK binaries depend on the architecture.

In Kubernetes, common values are:

| Where to check | x86-64 | ARM 64-bit |
|---|---|---|
| `uname -m` on Linux | `x86_64` | `aarch64` |
| Kubernetes `kubernetes.io/arch` | `amd64` | `arm64` |
| OCI image platform | `linux/amd64` | `linux/arm64` |
| Common JDK `os.arch` | `amd64` or `x86_64` | `aarch64` |

Names can differ across the kernel, JVM, and Kubernetes. Standardize them in the checkpoint manifest, such as `linux/amd64` or `linux/arm64`, and verify the exact image variant that the container runtime will pull.

If the application needs to run on both amd64 and arm64, create separate checkpoints for each architecture from the corresponding JDK and container image. A multi-architecture OCI image only selects the right binary/container layer; it does not convert the contents of a checkpoint already created on another architecture.

### 1.2. Even With the Same Architecture, CPU Instructions Can Still Be Missing

Two nodes can both be `amd64` while differing in CPU generation and supported instruction sets. For example, the checkpointing node has AVX-512 whereas the target node only has AVX2. A JVM started on the source CPU may already have used instructions that the target CPU cannot execute.

CRaC cannot reconfigure a restoring JVM on its own to stop using CPU features selected at JVM startup. This is a cause that can lead to CPU compatibility errors right during the restore process. [CRaC: CPU features](https://crac.org/reference/cpu-features/)

Therefore, the feature set must be verified, not just the architecture string.

## 2. Collecting Fingerprints on the Checkpointing Node

Before creating a checkpoint, record the environment in which the JVM ran. Collect information from both the host and the container, because a container may see different CPU features or filesystems than information an administrator reads from another machine.

### 2.1. Architecture, Kernel, and CPU Model

On the source Linux node:

~~~bash
uname -m
uname -r
cat /etc/os-release
lscpu
getconf LONG_BIT
getconf PAGE_SIZE
~~~

Meaning:

- `uname -m` reports the machine architecture the kernel is running on.
- `uname -r` records the kernel release.
- `/etc/os-release` records the distribution and version.
- `lscpu` reports the CPU model, vendor, topology, and some CPU flags.
- `getconf LONG_BIT` reports whether userspace is 32-bit or 64-bit.
- `getconf PAGE_SIZE` records the page size used by processes.

For `x86_64`, also check flags:

~~~bash
grep -m1 '^flags' /proc/cpuinfo
~~~

For ARM, the kernel typically exposes capabilities through the `Features` field:

~~~bash
grep -m1 '^Features' /proc/cpuinfo
~~~

Do not record only the CPU model name. A VM can present a virtual CPU model and mask out some host features. The flags actually seen by the process are the data that must be compared.

### 2.2. CPU Features Actually Used by the JVM

On a CRaC JDK that supports the option to display CPU features, run:

~~~bash
"$JAVA_HOME/bin/java" -XX:+ShowCPUFeatures --version
~~~

The output typically prints two important lines:

~~~text
This machine's CPU features are: -XX:CPUFeatures=...
CPU features being used are: -XX:CPUFeatures=...
~~~

The first line shows the feature set the JVM sees on the current machine. The second line shows the feature set the JVM uses. Save the exact verbatim output in the manifest alongside the checkpoint.

The command must run with the **exact JDK vendor/build and exact container image** used to create the checkpoint. Do not take results from a different JDK on the host and assume the JVM inside the Pod has the same feature set.

If the `-XX:+ShowCPUFeatures` option does not exist in the JDK in use, do not infer the feature mask yourself. Check vendor/runtime documentation and use appropriate CPU tools. Options related to CPU features can differ across JDK distributions.

### 2.3. Recording JDK and CRIU

~~~bash
"$JAVA_HOME/bin/java" -version
"$JAVA_HOME/bin/java" -XshowSettings:properties -version 2>&1 \
    | grep -E 'java.vendor|java.version|java.runtime.version|os.arch|os.name'
criu --version
~~~

If CRIU is bundled with the JDK instead of installed on PATH, check the binary the CRaC engine actually invokes. For example, in some OpenJDK CRaC builds, the helper resides under `$JAVA_HOME/lib/criu`. Do not assume the binary on PATH is the one used by the engine; confirm based on the JDK vendor and `-XX:CRaCEngine` configuration.

OpenJDK CRaC currently advises using a recent CRIU; the upstream README cites CRIU 4.0 or newer as the installation baseline. JDK vendors may have their own support matrices, so the CRIU version must follow the documentation of the deployed runtime. [OpenJDK CRaC README](https://github.com/openjdk/crac/blob/crac/README.md)

## 3. Collecting Fingerprints on the Target Node

Repeat the same set of commands on the node planned for restore. Use the same collection method to compare source and target results.

~~~bash
uname -m
uname -r
cat /etc/os-release
lscpu
getconf LONG_BIT
getconf PAGE_SIZE
grep -m1 '^flags' /proc/cpuinfo
"$JAVA_HOME/bin/java" -XX:+ShowCPUFeatures --version
"$JAVA_HOME/bin/java" -version
criu --version
~~~

If the target is ARM, replace the command reading `flags` with `Features` as shown earlier.

### 3.1. Comparing Two Fingerprints

The following table can be used in manifests or verification reports:

| Attribute | Checkpoint source | Restore target | Decision |
|---|---|---|---|
| OS | Linux | Linux | Verify detailed kernel/runtime |
| Architecture | amd64 | amd64 | Architecture must match |
| CPU features used by JVM | Feature set A | Feature set B | B must satisfy every mandatory feature of the image |
| JDK vendor/build | Vendor + build A | Vendor + build B | Prefer the same verified vendor/build |
| CRIU | Version A | Version B | Follow JDK support matrix; restore test confirms |
| Kernel | Release A | Release B | Check features with CRIU, not merely comparing version strings |
| Page size | 4 KiB | 4 KiB | Record and verify against real image |
| Container image | Digest A | Digest A | Prefer identical image digest |
| Mounts/security | Profile A | Profile B | Must meet requirements of process and CRIU |

Some attributes may differ while restore still works; others are hard requirements. Do not use a single version comparison to draw conclusions. For example, the target kernel does not necessarily need the exact same version string as the source, yet must provide the needed features and be supported by CRIU/runtime.

### 3.2. Reading Kernel Info via the Kubernetes API

From a cluster administration machine:

~~~bash
kubectl get nodes \
  -L kubernetes.io/arch,kubernetes.io/os,node.kubernetes.io/instance-type
~~~

To view details of one node:

~~~bash
kubectl get node <NODE_NAME> -o jsonpath='{.status.nodeInfo.architecture}{"\n"}{.status.nodeInfo.operatingSystem}{"\n"}{.status.nodeInfo.kernelVersion}{"\n"}{.status.nodeInfo.osImage}{"\n"}{.status.nodeInfo.containerRuntimeVersion}{"\n"}{.status.nodeInfo.kubeletVersion}{"\n"}'
~~~

Fields in `Node.status.nodeInfo` show the architecture, kernel, OS image, container runtime, and kubelet recorded by the cluster. They do not replace running `lscpu`, checking CRIU, or testing restore on the node.

## 4. Verifying CPU Feature Compatibility

This is an important step when a checkpoint is created on one node and restored on another node of the same architecture.

### 4.1. Comparing the JVM Feature Set

Suppose the source JVM uses the features:

~~~text
CPUFeatures used on source = FEATURE_SET_A
~~~

The target node must support the features required by the image. If the target lacks an instruction used by the JVM/JIT code, the process may not run safely.

CRaC may emit a restore message requesting `-XX:CPUFeatures=...` when a checkpoint was created with a feature set unsuitable for target nodes. Use the information provided by the runtime to configure **at checkpoint creation time**, rather than waiting until production restore to try skipping checks.

### 4.2. Using a Common Feature Baseline

If a checkpoint must run across multiple nodes of differing CPU generations, the image can be created with a lower common feature baseline. On supporting CRaC JDKs, the `-XX:CPUFeatures=generic` option selects a more conservative instruction set to improve compatibility within the same architecture.

Example:

~~~bash
"$JAVA_HOME/bin/java" \
    -XX:CRaCCheckpointTo=/var/lib/orders/checkpoint \
    -XX:CPUFeatures=generic \
    -jar orders-service.jar
~~~

This approach can reduce performance because the JVM avoids certain optimal instructions supported by the source CPU. In exchange, the image can run on a broader set of nodes. Confirm the option exists in the JDK vendor/build in use and run benchmarks to evaluate the trade-off.

If the target node pool is known in advance, the common feature set of that node group can be used instead of the generic baseline. CRaC documentation describes obtaining feature masks from machines and computing their bitwise AND (`&`) to form a common feature set. Use this method only when the mask format and option are supported by the current JDK. [CRaC: CPU features](https://crac.org/reference/cpu-features/)

### 4.3. Do Not Disable CPU Checks to Force a Restore

Do not use a mode that skips CPU feature checks as a production fix. Some runtimes have experimental options to bypass checks; skipping checks does not add missing instructions to the target CPU.

If an image requires AVX-512 while the target lacks AVX-512, forcing restore can lead to illegal instruction faults when code executes. Create a new checkpoint with an appropriate baseline or restrict the workload to nodes with compatible features.

### 4.4. CRIU Also Has Its Own CPU Check

CRIU has a CPU capability checking mechanism independent of JVM CPU feature options. The `criu cpuinfo dump` tool can save CPU capabilities to a `cpuinfo.img` image, and `criu cpuinfo check` compares that image against the current CPU. CRIU also has the `--cpu-cap` option to control check groups such as FPU, instruction compatibility, and CPU capabilities.

Example supplementary check using CRIU:

~~~bash
mkdir -p /tmp/source-cpu-profile
cd /tmp/source-cpu-profile
criu cpuinfo dump
~~~

Transfer the generated `cpuinfo.img` file to the target test environment, then run:

~~~bash
cd /tmp/source-cpu-profile
criu cpuinfo check
~~~

This is CRIU's CPU check, not an operation to create or modify a CRaC checkpoint. A separate CRIU CPU image passing verification does not replace the JVM's `-XX:+ShowCPUFeatures` nor prove the entire process image is restorable. Depending on CRIU version and how the JDK invokes the engine, CPU check strictness may vary. [CRIU: cpuinfo](https://www.criu.org/CLI/cmd/cpuinfo) · [CRIU: --cpu-cap](https://github.com/checkpoint-restore/criu/blob/criu-dev/Documentation/criu.txt)

## 5. Verifying the Kernel and Features Needed by CRIU

CRIU relies on Linux kernel functionality to dump and restore processes. Kernel version is important information, yet checking `uname -r` alone is insufficient because features may be disabled in kernel config or restricted by the container environment.

### 5.1. Running CRIU Check on the Target Node

On the target node or in an environment with the same permissions and namespaces as the restore Pod:

~~~bash
criu check
criu check --extra
~~~

`criu check` checks CRIU's basic kernel requirements. `criu check --extra` checks additional features that may be needed for processes using specialized resources. A `Looks good` result is a favorable condition to proceed, not proof that a specific checkpoint is guaranteed to restore.

If the application uses AIO, TUN devices inside network namespaces, or other special resources, verify the corresponding features. [CRIU: Check the kernel](https://criu.org/CLI/cmd/check)

### 5.2. Kernel Features to Note

CRIU may depend on features such as:

- Checkpoint/restore support.
- Process, network, IPC, and UTS namespaces.
- PID namespace and ability to recreate PIDs.
- File handles and related syscalls.
- Eventfd, epoll, and socket diagnostics.
- Cgroup and mount namespaces.
- Specific features depending on the types of resources the application uses.

The exact list depends on CRIU version, kernel config, and process tree. CRIU maintains documentation on required kernel options; do not draw conclusions from a single minimum kernel number alone. [CRIU: Linux kernel requirements](https://criu.org/Linux_kernel)

### 5.3. Recording Cgroups and Mounts

On the target node/Pod:

~~~bash
stat -fc %T /sys/fs/cgroup
mount | grep -E 'cgroup|overlay|tmpfs'
findmnt -R /
~~~

Output `cgroup2fs` usually indicates cgroup v2; other environments may use cgroup v1 or hybrid configurations. Record the cgroup version and mount layout on both source and target. Restorability also depends on CRIU, kernel, container runtime, and how cgroups are configured.

Do not treat cgroup v1 and v2 as equivalent merely because both display resource limits. Check the exact CRIU/runtime in use and test restoring on a node with the same configuration type.

## 6. Verifying Container Runtime and Permissions on the Target Node

Even when the host supports CRIU, a Pod may lack sufficient privileges to invoke necessary operations. CRaC engines based on CRIU typically require higher privileges than a normal Java application.

### 6.1. Checking CRIU Binary and Capabilities

Depending on the JDK/vendor, CRIU may be shipped with the JDK or installed on the host. Identify the binary actually invoked by the engine, then check:

~~~bash
criu --version
command -v criu
ls -l "$JAVA_HOME/lib/criu"
~~~

OpenJDK CRaC currently documents that the CRIU engine needs special privileges; inside containers, Linux capabilities such as `CHECKPOINT_RESTORE` and `SYS_PTRACE` may be required. Some builds instruct configuring SUID for the CRIU helper. Exact requirements depend on JDK build, CRIU version, container runtime, and deployment method. [CRaC: Checkpoint engines](https://crac.org/reference/engines/) · [OpenJDK CRaC runtime requirements](https://crac.org/use/crac-runtime/)

### 6.2. Checking Process Capabilities Inside the Pod

~~~bash
id
grep '^Cap' /proc/self/status
~~~

If the `capsh` tool is available:

~~~bash
capsh --print
~~~

Read the output from inside the actual container running Java. Checking on the host does not prove a Pod is granted the same capabilities. Beyond Linux capabilities, also inspect seccomp profiles, AppArmor/SELinux policies, user namespaces, and `/proc` access permissions.

Do not use `privileged: true` or grant all capabilities as a default workaround. Configure according to CRaC runtime requirements and cluster security policies; if the environment uses an SUID helper, verify the owner and permissions of the exact binary per vendor guidance.

### 6.3. Container Runtime and Node Runtime

Record:

- Container runtime name/version: containerd, CRI-O, or another runtime.
- RuntimeClass if the Pod uses a special runtime.
- Node kernel.
- Pod SecurityContext.
- PID namespace and user namespace.
- Seccomp, AppArmor, and SELinux policies.
- Cgroup driver and cgroup version.

Restore tests must run under the same runtime type and security profile as the production workload. A CRIU test run directly on the host may succeed while a Pod still fails due to missing capabilities or different namespaces.

## 7. Verifying Filesystems, Mounts, and Native Libraries

CRIU restores process state, which does not mean the entire filesystem outside the container image is automatically packaged with the checkpoint.

Paths and files the process depends on must be checked:

- JDK home and native libraries.
- Application JARs and dependencies.
- Memory-mapped files.
- Configuration files needed after restore.
- Volume mounts and secret mounts.
- Working directory, temp directory, and symlinks.
- File descriptors retained or handled via callbacks.
- File owner/group and mode permissions.

### 7.1. Prefer the Same Container Image Digest

A simple way to minimize differences is creating checkpoints and restoring with the same container image digest. This keeps the JDK, JARs, native libraries, paths, and files in image layers identical.

Example retrieving the running image digest:

~~~bash
kubectl get pod <POD_NAME> -o jsonpath='{.status.containerStatuses[?(@.name=="app")].imageID}{"\n"}'
~~~

Use pinned digests in Deployments rather than tags alone, which can be overwritten. If the image changes between checkpoint and restore, verify that mapped or referenced files still have identical content and ABI.

### 7.2. Comparing Mounts and Volumes

~~~bash
findmnt -R /
df -h
df -i
~~~

Compare source/target:

- Do mount paths exist?
- Do volumes have the right type and content?
- Do referenced files have appropriate read/write permissions?
- Does tmpfs have sufficient capacity?
- Do secret/config mounts have the right revision?
- Is the checkpoint directory accessible?

If a resource cannot be safely kept across a checkpoint, the application must close it before checkpoint and recreate it after restore via CRaC callbacks. Do not try to retain external sockets or file descriptors merely because mount paths look the same.

## 8. Verifying Memory Resources and Container Limits

A checkpoint can contain a large amount of memory. The target node must have enough resources for CRIU/JVM to remap memory and resume operation.

Check on the node:

~~~bash
free -h
grep -E 'MemTotal|MemAvailable|HugePages|Hugepagesize' /proc/meminfo
ulimit -a
~~~

Check in Kubernetes:

~~~bash
kubectl describe node <NODE_NAME>
kubectl describe pod <POD_NAME>
kubectl top nodes
kubectl top pod <POD_NAME>
~~~

Compare:

- Pod memory request/limit.
- Available memory on the node at restore time.
- Huge pages if used by the application/JVM.
- `ulimit` and file descriptor/process limits.
- Cgroup memory limits and memory accounting.
- CPU request/limit and throttling.
- Ephemeral storage for images/checkpoints if placed on local node storage.

A node with matching CPU features but insufficient RAM or ephemeral storage may still fail to restore. When multiple Pods restore concurrently, calculate total memory demand and prevent the scheduler from packing them onto a single node.

## 9. Using Node Feature Discovery to Classify Node CPUs

Kubernetes automatically attaches several standard labels to Nodes, including:

- `kubernetes.io/arch`
- `kubernetes.io/os`
- `kubernetes.io/hostname`
- `node.kubernetes.io/instance-type` if provided by the kubelet/cloud provider.

These labels help classify architecture and OS, yet **do not fully describe the CPU instruction set**. [Kubernetes: Node labels](https://kubernetes.io/docs/reference/node/node-labels/)

If a cluster has multiple CPU generations, Node Feature Discovery (NFD) can detect hardware features and publish them as Node labels. Example:

~~~text
feature.node.kubernetes.io/cpu-cpuid.AVX2=true
feature.node.kubernetes.io/cpu-cpuid.AVX512F=true
feature.node.kubernetes.io/cpu-cpuid.AESNI=true
~~~

Label names depend on feature sources and NFD configuration. NFD records supported CPU capabilities; a feature may be supported in hardware yet disabled or unused by the JVM. Thus, NFD helps the scheduler filter nodes, while JVM/CRIU still perform actual compatibility checks. [NFD: Feature labels](https://kubernetes-sigs.github.io/node-feature-discovery/master/usage/features.html)

### 9.1. Viewing Labels on Nodes

~~~bash
kubectl get nodes --show-labels
kubectl get nodes -L kubernetes.io/arch,kubernetes.io/os,feature.node.kubernetes.io/cpu-cpuid.AVX2,feature.node.kubernetes.io/cpu-cpuid.AVX512F
~~~

If NFD is not yet deployed, administrator-applied labels can be used after testing the node. Do not apply labels based solely on instance type names or CPU models advertised by a cloud provider.

Example verified profile label:

~~~bash
kubectl label node <NODE_NAME> \
    crac.example.com/restore-profile=orders-amd64-v2
~~~

Apply the profile only after the node passes the compatibility test suite. Admission policies or provisioning workflows can ensure labels are not misapplied.

### 9.2. Selecting Nodes with nodeSelector

For a checkpoint running only on amd64:

~~~yaml
spec:
  nodeSelector:
    kubernetes.io/os: linux
    kubernetes.io/arch: amd64
    crac.example.com/restore-profile: orders-amd64-v2
~~~

This approach is straightforward when a group of nodes has been tagged with a shared, verified profile.

### 9.3. Selecting Nodes with Node Affinity and CPU Features

To select based on NFD labels:

~~~yaml
spec:
  affinity:
    nodeAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        nodeSelectorTerms:
          - matchExpressions:
              - key: kubernetes.io/os
                operator: In
                values:
                  - linux
              - key: kubernetes.io/arch
                operator: In
                values:
                  - amd64
              - key: feature.node.kubernetes.io/cpu-cpuid.AVX2
                operator: In
                values:
                  - "true"
~~~

If the image requires AVX-512, add a condition matching the actually needed feature. Do not require AVX-512 just because the source node had it; what matters is the feature set used by the JVM image.

Kubernetes nodeSelector and node affinity only inspect labels. They do not run CRIU or analyze checkpoints themselves. Therefore, labels must come from a reliable discovery/verification process. [Kubernetes: Assigning Pods to Nodes](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/)

## 10. Creating a Compatibility Profile for Each Checkpoint

Instead of writing a generic "Linux amd64", create a profile describing the checkpoint's requirements.

Example pipeline-defined manifest:

~~~yaml
checkpoint:
  id: orders-service-2.4.0-amd64-001
  createdAt: "2026-11-13T07:00:00Z"
  imageDirectory: ./checkpoint
  checksumFile: ./checkpoint.sha256

application:
  name: orders-service
  version: 2.4.0
  artifactDigest: "sha256:<digest>"

runtime:
  javaVendor: "<vendor>"
  javaVersion: "<full version and build>"
  javaArchitecture: amd64
  javaImageDigest: "sha256:<container-image-digest>"
  criuVersion: "<version>"
  criuEngine: criuengine

sourceNode:
  architecture: x86_64
  kernelRelease: "<uname -r>"
  osImage: "<distribution and version>"
  pageSize: 4096
  cpuModel: "<vendor and model>"
  cpuFeaturesUsed: "<output from ShowCPUFeatures>"
  cpuFlags: ["sse4_2", "avx", "avx2"]

restoreRequirements:
  os: linux
  architecture: amd64
  cpuFeatureProfile: orders-amd64-v2
  kernelFeatures: "criu-check-and-restore-test-required"
  requiredMounts:
    - "/run/app-config"
    - "/run/secrets"
  requiredCapabilities:
    - CHECKPOINT_RESTORE
    - SYS_PTRACE
  restoreTested: false
~~~

This is an illustrative schema for pipelines, not an official CRaC/CRIU manifest. Capability and mount fields must reflect the actual runtime; do not copy verbatim into every cluster.

Manifests should be signed or protected alongside artifacts. Do not record secret values, passwords, tokens, or private keys in profiles. Store checksums of the checkpoint and container image to pinpoint the exact tested image set.

## 11. Target Node Verification Process Before Deployment

A practical verification workflow can follow these steps.

### Step 1: Identify the Exact Target Node Pool

Retrieve the list of nodes, architectures, OSes, and instance types:

~~~bash
kubectl get nodes -o wide
kubectl get nodes \
  -L kubernetes.io/arch,kubernetes.io/os,node.kubernetes.io/instance-type
~~~

Group nodes by architecture, CPU generation/feature profile, kernel baseline, and container runtime. Do not lump all amd64 nodes into one group if they have different feature sets.

### Step 2: Collect CPU Features from Node and Container

On each node type:

~~~bash
uname -m
lscpu
grep -m1 '^flags' /proc/cpuinfo
~~~

Then run the exact JDK/container image planned for restore:

~~~bash
java -XX:+ShowCPUFeatures --version
java -version
~~~

Compare the feature set the JVM will use. If the node runs in a VM, verify CPU features visible to the guest and container, not just physical features of the hypervisor host.

### Step 3: Check Kernel and CRIU

~~~bash
uname -r
criu --version
criu check
criu check --extra
~~~

Run in an environment with permissions equivalent to the production Pod. If `criu check --extra` reports missing features, examine the process resources used by the checkpoint and evaluate whether those missing features affect restore.

### Step 4: Check Permissions and Mounts

~~~bash
id
grep '^Cap' /proc/self/status
findmnt -R /
df -h
ulimit -a
~~~

Compare securityContext, mounts, secret/config paths, user IDs, group IDs, and runtime classes between the checkpoint creation environment and target environment.

### Step 5: Run Canary Restores on Each Node Profile

Use the exact checkpoint, exact image digest, and exact Pod configuration. Pick at least one node for each distinct CPU/kernel/runtime profile. Do not test on only one representative node and assume the entire cluster is compatible if the cluster has heterogeneous hardware.

### Step 6: Verify the Application After Restore

After restore:

- CRaC `afterRestore` callbacks complete.
- Databases/clients/brokers reconnect successfully.
- Readiness transitions to success only after required dependencies operate.
- Health endpoints respond.
- Representative requests succeed.
- No errors occur for CPU instructions, memory maps, file descriptors, permissions, or namespaces.
- Memory/CPU usage stays within Pod limits.

### Step 7: Apply Profile Labels and Deploy

Only after canary restore succeeds should you apply the profile label to the node pool and configure the Deployment to use `nodeSelector` or node affinity to target the right node group.

## 12. Verifying Restore with the Exact Command and Runtime

With a CRaC JDK, checkpoints are typically created with `-XX:CRaCCheckpointTo` and restored with `-XX:CRaCRestoreFrom`. [CRaC: Checkpoint and restore](https://crac.org/use/checkpoint-and-restore/)

Example:

~~~bash
"$JAVA_HOME/bin/java" \
    -XX:CRaCRestoreFrom=/opt/checkpoints/orders-service \
    -jar orders-service.jar
~~~

The exact invocation depends on the JDK/vendor and image layout. Some restore workflows launch directly from the image without re-passing the JAR as in a cold start; use the exact command line recorded when creating the checkpoint and follow runtime documentation.

Do not treat a checkpoint created by `simengine` as proof of CRIU restore compatibility. `simengine` simulates the callback cycle within the same process and does not dump and restore a real process image. To validate target nodes, use the same engine type that creates production checkpoints. [CRaC: Checkpoint engines](https://crac.org/reference/engines/)

### 12.1. Testing on the Same Container Image

When creating a canary Pod:

- Pin the container image by digest.
- Use the exact JDK vendor/build.
- Use the same RuntimeClass and securityContext.
- Mount the same volume types and paths.
- Use the same user/group.
- Set memory/CPU limits close to production configuration.
- Schedule the Pod onto a node belonging to the profile being verified.

A restore command run directly on the host with root privileges does not prove production Pods share the same conditions.

### 12.2. Inspecting CRIU and JVM Logs

When restore fails, collect:

- Application stdout/stderr.
- CRaC/JVM logs.
- CRIU logs produced by the runtime.
- Kubernetes Pod Events.
- Container exit code and restart count.
- Node kernel/runtime information.
- CPU feature output from the target node.

If application logs lack detail, check CRIU verbosity/log options per the JDK vendor. Do not assume log paths or engine options are identical across builds.

## 13. Common Compatibility Errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| Restore reports missing CPU features | Target CPU lacks instructions used by the JVM | Select a node with matching features or create checkpoint with a common baseline |
| Both are amd64 yet restore fails | CPU microarchitecture, FPU, or XSAVE differs | Compare JVM feature sets and CRIU CPU checks |
| Cross-restore between amd64/arm64 | Process image is architecture-incompatible | Create separate checkpoints per architecture |
| `criu check` fails | Kernel lacks features or CRIU lacks permissions | Check kernel config, capabilities, and runtime |
| `criu check` passes yet restore fails | Basic check does not test the specific image or specialized resources | Read CRIU logs and run a real restore test |
| `Operation not permitted` | Missing capabilities, SUID helper, or security policy blocking syscalls | Check securityContext, CRIU helper, seccomp, and LSM |
| Cannot recreate PID | PID namespace, permissions, or PID conflict | Check namespaces, `ns_last_pid`, and CRIU logs |
| File/native library not found | Container image or mounts differ from source | Use the exact image digest and mount layout |
| Memory mapping fails | Insufficient RAM, page/hugepage, or cgroup limits | Check memory availability, page size, huge pages, and Pod limits |
| Restore fails inside Pod yet succeeds on host | Container has different capabilities/namespaces/mounts | Test inside the exact Pod security profile |
| Pod scheduled onto unsuitable node | Scheduler only filters architecture or labels lack precision | Use NFD/custom profile labels and required node affinity |
| Checkpoint from simengine "passes" yet CRIU fails | Simengine does not create a real process image | Run canary with the real CRIU engine |

## 14. Handling CPU Feature Mismatches

When a target lacks CPU features, there are three options:

### 14.1. Keep the Checkpoint Within Nodes With Compatible CPUs

This is the simplest approach when a node pool has multiple CPU generations. Apply a profile label after verification and use node affinity so Pods are scheduled only onto suitable nodes.

The advantage is that the JVM keeps using optimizations already in the checkpoint. The drawback is that the number of nodes able to run the image is constrained.

### 14.2. Create a New Checkpoint With a Lower Feature Baseline

To run a checkpoint across multiple nodes of the same architecture, create a new checkpoint using a JDK supporting a common CPU feature baseline, such as `-XX:CPUFeatures=generic`. Check vendor options and evaluate performance impact before using.

This decision must be made **before checkpointing**. You cannot take an image already containing JIT code dependent on higher features and ask the JVM to automatically downgrade instructions at restore.

### 14.3. Split Checkpoints by CPU Profile

If a cluster has clear node groups, you can create one checkpoint per profile:

~~~text
checkpoint artifacts
├── orders-amd64-generic/
├── orders-amd64-avx2/
├── orders-amd64-avx512/
└── orders-arm64/
~~~

Each artifact must be built with the matching JDK, have its own manifest, and undergo its own restore tests. Do not rename an amd64 checkpoint to arm64 or share images across distinct profiles.

## 15. Integrating Verification into Pipelines and Kubernetes Rollouts

Do not wait until a production Pod is scheduled to discover an incompatible node. Build verification into the checkpoint-creation pipeline and deployment pipeline.

### 15.1. Checkpoint Creation Pipeline

~~~text
BUILD APPLICATION
      │
      ▼
SELECT JDK + CONTAINER IMAGE
      │
      ▼
COLLECT SOURCE FINGERPRINT
  - architecture
  - JVM CPU features
  - kernel / CRIU
  - image digest
  - mounts / runtime
      │
      ▼
CREATE CHECKPOINT
      │
      ▼
WRITE MANIFEST + CHECKSUM
      │
      ▼
RESTORE TEST ON SOURCE PROFILE
      │
      ▼
PUBLISH CHECKPOINT ARTIFACT
~~~

### 15.2. Deployment Pipeline

~~~text
DISCOVER TARGET NODE POOL
      │
      ▼
COMPARE TARGET FINGERPRINT
      │
      ▼
CRIU CHECK + CPU FEATURE CHECK
      │
      ▼
CANARY RESTORE ON EACH PROFILE
      │
      ▼
SMOKE TEST + HEALTH CHECK
      │
      ▼
APPLY VERIFIED NODE LABELS
      │
      ▼
DEPLOY WITH REQUIRED NODE AFFINITY
~~~

If a node pool changes kernel, firmware, CPU model, or container runtime, the profile must be re-evaluated. Do not retain compatibility labels indefinitely when underlying infrastructure has changed.

### 15.3. Deploying by Node Group

With multiple node pools, deploy a canary first on a verified group, then expand gradually. Keep Pod readiness false until restore and reconnect complete. If restore fails, halt the rollout and collect logs before moving to another node pool.

Do not automatically fall back to nodes with weaker CPUs by skipping checks. If a profile is incompatible, select another artifact or create a new checkpoint.

## 16. Verification Checklist Before Permitting Restore

Before marking a node pool eligible to run checkpoints, obtain evidence for the following items:

- [ ] Node architecture matches checkpoint architecture.
- [ ] Container image/JDK has the verified platform variant and digest.
- [ ] JDK vendor, version, and build are compatible.
- [ ] The CPU feature set used by the JVM is supported by the target node.
- [ ] FPU/XSAVE and related capabilities are not missing.
- [ ] CRIU version is supported by the JDK/vendor.
- [ ] `criu check` and `criu check --extra` have been executed in an environment with appropriate permissions.
- [ ] Kernel and namespace/cgroup features meet requirements.
- [ ] Container runtime, RuntimeClass, and securityContext have been verified.
- [ ] Capabilities, seccomp, AppArmor/SELinux, and user namespaces match.
- [ ] Required mounts, volumes, files, and native libraries are present.
- [ ] RAM, huge pages, file descriptors, and Pod resource limits are sufficient.
- [ ] Node labels accurately reflect verified CPU/kernel profiles.
- [ ] Required node affinity constrains Pods to compatible node groups.
- [ ] Canary restore from a real checkpoint succeeded.
- [ ] Application smoke tests and readiness checks succeeded.
- [ ] Manifests and verification logs are stored alongside the artifact.

This checklist serves as an operational gate to decide whether a node pool is permitted to accept checkpoints. Some items may vary by JDK vendor, CRIU engine, and application resources; explicitly document exceptions in the manifest.

## 17. Operational Principles

Treat a checkpoint as an artifact bound to a specific runtime profile. CPU architecture is the first requirement; CPU features, JDK builds, kernels, CRIU, container runtimes, permissions, and filesystems determine real restorability.

In Kubernetes, use `kubernetes.io/arch` to exclude wrong-architecture nodes, use Node Feature Discovery or custom profile labels to select suitable CPU nodes, and then apply required node affinity. The scheduler only uses labels; it does not replace CRIU and JVM verification.

Before releasing, collect source and target fingerprints, run CRIU kernel checks in the exact security context, confirm the CPU feature set used by the JVM, and test restoring on each node group. Only after restore tests and smoke tests succeed should a node pool be marked compatible and Deployments allowed to use that checkpoint.

## 18. References

- [CRaC: CPU features](https://crac.org/reference/cpu-features/): CPU feature mismatches, generic baselines, and determining feature sets.
- [CRaC: Runtimes with CRaC support](https://crac.org/use/crac-runtime/): CRaC JDKs and privileges required for the CRIU engine.
- [CRaC: Checkpoint engines](https://crac.org/reference/engines/): distinguishing the CRIU engine and simengine.
- [CRaC: Checkpoint and restore](https://crac.org/use/checkpoint-and-restore/): how to create and restore images.
- [CRIU: Check the kernel](https://criu.org/CLI/cmd/check): checking basic and extended kernel features.
- [CRIU: CPU info](https://www.criu.org/CLI/cmd/cpuinfo): saving and checking CPU capabilities.
- [OpenJDK CRaC README](https://github.com/openjdk/crac/blob/crac/README.md): CRIU and runtime privilege requirements.
- [Kubernetes: Node labels](https://kubernetes.io/docs/reference/node/node-labels/): standard architecture and OS labels.
- [Kubernetes: Assigning Pods to Nodes](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/): nodeSelector and node affinity.
- [Node Feature Discovery: Feature labels](https://kubernetes-sigs.github.io/node-feature-discovery/master/usage/features.html): publishing CPU features as node labels.
