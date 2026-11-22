# Differences in Kernel, System Libraries, and Native Environment

CRaC (Coordinated Restore at Checkpoint) allows saving the state of a Java process and then restoring that process in a compatible environment. Because a checkpoint contains process state at the JVM and operating system levels, restore capability depends on many factors outside Java bytecode: the kernel, CPU architecture, native libraries, dynamic linker, filesystem, namespaces, security configuration, and container runtime.

An application may run normally on two Linux machines, yet a checkpoint created on the first machine still cannot be safely restored on the second machine. The two machines may differ in kernel features, library ABIs, CPU instruction sets, mounts, network namespaces, or system permissions. These differences affect the resources the process is using at image creation time.

Therefore, when deploying CRaC, you need to clearly define the **compatibility boundary of a checkpoint**. Treat a checkpoint as an artifact tied to a specific runtime platform, describe the verified conditions, and restore in an environment that satisfies those conditions. Using the same JAR file or the same Java version is not enough to prove two environments are compatible.

## 1. Why Do the Kernel and Native Environment Matter?

A Java program does not run solely on bytecode. The JVM is a native process built for a specific operating system and CPU architecture. The JVM uses system calls, memory mappings, threads, signals, file descriptors, sockets, and native libraries.

During checkpoint, an operating-system-level mechanism needs to save and restore process state. On Linux, CRaC solutions typically coordinate with CRIU (Checkpoint/Restore In Userspace) to handle process state. CRIU interacts with the kernel to save and restore components such as:

- Processes and relationships between processes.
- Threads, CPU state, and signals.
- Memory regions and memory mappings.
- File descriptors and certain types of kernel resources.
- Sockets and network state under supported conditions.
- Namespaces and resources related to the runtime environment.

A CRaC JDK adds coordination at the Java layer so that the application can prepare resources before checkpoint and recover them after restore through callbacks such as `beforeCheckpoint()` and `afterRestore()`.

~~~mermaid
flowchart TD
    A["Java application"] --> B["JVM runtime"]
    B --> C["Native libraries and JNI"]
    B --> D["Linux system calls"]
    D --> E["Kernel process state"]
    D --> F["Filesystem and file descriptors"]
    D --> G["Network stack and namespaces"]
    H["CRaC integration"] --> I["CRIU checkpoint/restore"]
    I --> E
    I --> F
    I --> G
    H --> B
~~~

The diagram shows that checkpointing spans multiple layers. If one layer does not meet the restore conditions, the process may fail to restore or restore but behave incorrectly when using that resource.

### 1.1. Java Bytecode Is Portable; a Checkpoint Is Not Equivalent to a JAR

Java bytecode can generally run on many operating systems and architectures if a suitable JVM is available. A checkpoint, on the other hand, contains the state of a specific process, including native and kernel information.

| Artifact | Main Content | Portability Scope |
|---|---|---|
| JAR / class files | Application bytecode and resources | Can be used on multiple platforms with a suitable JDK |
| Native library | Machine code per ABI and architecture | Depends on OS, CPU, linker, and system libraries |
| JVM process | Heap, threads, runtime, and native state | Tied to the running runtime and environment |
| CRaC checkpoint | Process state at save time | Strongly depends on checkpoint/restore conditions |

A JAR may run on both hosts while a process checkpoint from host A cannot be directly restored on host B. This is why the checkpoint release process needs to verify the environment at both ends.

## 2. Role of the Linux Kernel

The kernel provides the mechanisms that the JVM and CRIU need to manage processes. The kernel version is an important part of a compatible environment, but comparing only the kernel version number is not enough.

Two machines with the same kernel version string can still differ in:

- Kernel configuration.
- Loaded modules.
- Enabled or restricted namespaces.
- Cgroup mode and controllers.
- System call access permissions.
- Security modules and policies.
- Filesystem drivers and mount options.
- Network stack, routes, and interfaces.
- Features enabled or disabled by the kernel distribution.

Conversely, kernels with different versions can sometimes still be compatible for a specific workload if the required features and CRIU conditions are satisfied. Do not infer this from the version number alone; check the documentation and test actual restore.

### 2.1. Kernel Features and CRIU

CRIU requires appropriate kernel capabilities to dump and restore a process. The specific capabilities depend on the types of resources the process uses and the CRIU version.

For example, an application may use:

- Thread and process state.
- Memory mappings and shared memory.
- Unix domain sockets.
- TCP connections.
- File descriptors.
- Namespaces.
- Mounts and file locks.
- Certain types of IPC or devices.

Not every resource type is supported in every configuration. Some features require special privileges or a newer kernel. Some resources must be closed by the application before checkpoint because they cannot be reliably restored.

Check the support matrix of the CRIU and CRaC JDK in use. When a dump or restore error occurs, CRIU and kernel logs usually provide more detailed information than Java errors on the application side.

### 2.2. Kernel Version Is Not the Only Criterion

For example, two containers may run on the same host kernel, yet container A has appropriate permissions and namespaces while container B is restricted by seccomp or capabilities. Checkpoint/restore results can differ even though `uname -r` is identical.

An environment needs to be described by multiple factors:

- Kernel release and build.
- CRIU version.
- JDK distribution and version.
- Container runtime and configuration.
- Namespaces and capabilities.
- Seccomp, AppArmor, or SELinux policy.
- Cgroup version and resource limits.
- Filesystem and mount layout.
- CPU architecture and feature set.

### 2.3. Checking the Kernel and CRIU

The Linux commands below help collect environment information:

~~~bash
uname -a
uname -r
cat /proc/version
criu --version
criu check
~~~

`criu check` is a step to check CRIU's capabilities in the current environment. The result does not replace testing dump/restore on a real workload, but it helps detect certain kernel or system permission deficiencies early.

If CRIU is not present in the application image, run the check on the host environment or a tool image with appropriate privileges. An application container is not necessarily allowed to inspect all kernel capabilities itself.

## 3. Differences Between Host and Container

Containers share the host kernel but can have their own namespaces, cgroups, filesystems, and security policies. Therefore, the same container image can behave differently on two hosts or under two runtime configurations.

Components to consider:

- PID namespace.
- Mount namespace.
- Network namespace.
- User namespace.
- IPC namespace.
- UTS namespace.
- Cgroup namespace and resource controllers.
- Bind mounts and volumes.
- Capabilities and seccomp profiles.
- Runtimes such as containerd or CRI-O.
- Orchestration policies such as Kubernetes.

### 3.1. PID Namespace

A PID namespace creates an isolated process view for a container. CRIU needs to restore the process with a PID relationship compatible with the target namespace and environment.

If a checkpoint is created in one namespace configuration but restored in another, the PID mapping or process relationships may not match. Follow how CRIU and the runtime manage container checkpoint/restore.

Do not assume that simply running the same container image again will preserve all process IDs and process relationships.

### 3.2. User Namespace and System Permissions

A user namespace can map UIDs/GIDs inside the container to different UIDs/GIDs on the host. This affects file ownership, capabilities, and resource access permissions.

A process may be able to open a file when creating a checkpoint but lack the corresponding permissions in the restore environment. Or the file may be restored with unsuitable ownership.

You need to check:

- UID/GID mapping.
- Linux capabilities.
- Permissions on files and directories.
- Device access permissions.
- Permissions to perform checkpoint/restore operations.
- Security policies applied to the process.

### 3.3. Mount Namespace and Volumes

A container can view the filesystem through its own mount namespace. A path inside the container may point to different bind mounts or volumes across two hosts.

For example, the application opens `/var/lib/app/data.db` before checkpoint. Upon restore, that path may:

- No longer be mounted.
- Point to a different volume.
- Have different ownership or permissions.
- Have modified contents.
- Be mounted with different options.
- Reside on a filesystem that does not support the required behavior.

If a file descriptor is kept across the checkpoint, usability after restore depends on checkpoint mechanism support and mount/file compatibility. For critical files, check their state and contents after restore rather than relying solely on the descriptor existing.

### 3.4. Network Namespace

A network namespace contains the container's interfaces, IP addresses, routes, and networking components. The restore environment may have different addresses or routes.

A socket opened before checkpoint may depend on the old local address, port, route, or network namespace. For outbound connections to a database, broker, or HTTP service, the application should generally close and recreate connections using CRaC callbacks. For listening sockets, check how the runtime restores the port and avoid blindly rebinding.

### 3.5. Cgroups and Resource Limits

Cgroups manage limits on CPU, memory, processes, and several other resources. Restoring inside a cgroup with different limits can cause the application to:

- Lack sufficient memory to restore the heap or native allocations.
- Lack sufficient PID/thread quota to create workers.
- Experience CPU throttling during JIT or warm-up.
- Hit I/O or file descriptor limits.
- Fail to start required background threads.

Check the cgroup version, controllers, and actual limits in the restore environment. Do not only compare manifest configuration; inspect the values the process actually receives.

## 4. Native Libraries and ABI

A Java application can invoke native code via JNI, the Foreign Function & Memory API, or libraries that transitively depend on native libraries. These components expand the compatibility boundary.

An ABI (Application Binary Interface) defines how machine code interacts at the binary level, including calling conventions, symbols, data types, and linking rules. A native library built for a specific ABI does not necessarily work on another environment.

### 4.1. JNI Libraries

An application may load a native library:

~~~java
public final class NativeCrypto {
    static {
        System.loadLibrary("nativecrypto");
    }

    public native byte[] digest(byte[] input);
}
~~~

The `libnativecrypto.so` file must match:

- CPU architecture.
- Operating system ABI.
- Dynamic linker.
- Dependent libraries.
- Symbol versions required by the binary.
- Process runtime configuration.

If the library was already loaded before checkpoint, its native state may reside in the process. Restore requires an environment compatible with those native mappings and resources. If the library depends on devices, internal threads, or separate daemons, verify its specific checkpoint/restore capabilities.

### 4.2. glibc and musl

A Linux distribution can use glibc or musl as its C library. A binary built for one environment does not necessarily run in the other.

For example, a native library built in a glibc-based image may depend on symbol versions not present in the restore image. A binary built for musl may require the corresponding musl dynamic linker and runtime.

You should not assume that both environments being Linux is sufficient. You need to check:

- libc type.
- libc version.
- Dynamic loader path.
- Symbol versions.
- Dependent C/C++ libraries.
- Library search configuration.

Commonly used commands:

~~~bash
file libnativecrypto.so
ldd libnativecrypto.so
readelf -h libnativecrypto.so
readelf -d libnativecrypto.so
readelf --version-info libnativecrypto.so
~~~

`ldd` can be useful for inspecting dependencies in a trusted environment. For untrusted binaries, prefer ELF analysis tools that do not execute the binary. Results should be checked inside the exact container image and runtime.

### 4.3. C++ Runtime and Dependent Libraries

Native components written in C++ may depend on:

- `libstdc++`.
- `libgcc_s`.
- OpenSSL.
- zlib.
- libcurl.
- Compression or image processing libraries.
- Database client libraries.
- Vendor drivers or SDKs.

Version differences can cause missing symbols, ABI changes, or behavioral changes. Do not inspect only the main library file; check the entire dependency chain.

### 4.4. Native Libraries with Internal State

A native library may create its own threads, hold mutexes, file descriptors, shared memory, timers, or device handles. These resources have a lifecycle independent of the Java objects that invoke them.

Before checkpoint, determine whether the library supports checkpoint/restore. If not, call the library's shutdown/close API and recreate the instance after restore. Do not assume garbage collection or keeping the Java wrapper intact will restore native state.

## 5. CPU Architecture and Instruction Set Differences

A checkpoint contains the state of a process that ran on a specific CPU architecture. Restoring on a different architecture is generally not a simple conversion.

Factors include:

- x86-64, AArch64, or another architecture.
- Endianness.
- Page size and memory layout.
- CPU feature flags.
- SIMD instruction sets such as SSE, AVX, AVX2, or AVX-512.
- CPU extensions used by the JVM or native libraries.
- Machine code already generated by the JIT compiler.

### 5.1. Same Architecture Does Not Mean Identical CPU Features

Two hosts may both be x86-64 yet differ in AVX2 or AVX-512. Native libraries or JIT code may use an instruction set present on the checkpoint machine but absent on the restore machine.

Some JVMs have mechanisms to select an appropriate instruction set and can control which CPU features are used. However, checkpoint/restore must still adhere to JDK and platform support. Do not assume that JIT code will be fully recompiled or automatically adapt in all cases.

The safe approach is to create and restore checkpoints on a group of hosts with compatible CPU features, or use a confirmed common CPU baseline.

### 5.2. Checking the CPU

On Linux:

~~~bash
uname -m
lscpu
grep -m1 '^flags' /proc/cpuinfo
~~~

Record the architecture and CPU flags on both the checkpoint creation environment and the restore environment. When running on cloud or Kubernetes, also check the instance/node pool type and the CPU model configuration provided by the hypervisor.

### 5.3. JIT and Native Code Generated at Runtime

HotSpot can compile methods into machine code according to detected CPU features. A checkpoint may contain runtime state related to the compiled code. Therefore, CPU differences affect not only JNI libraries packaged with the application, but can also affect code generated by the JVM.

Refer to the CRaC JDK documentation for the exact version and check CPU constraints. If multiple host types must be supported, create separate checkpoints for each platform group confirmed compatible.

## 6. Dynamic Linker and Library Loading Order

The dynamic linker locates and loads shared libraries when the process starts or when the application requests loading a library. The result depends on:

- ELF interpreter recorded in the binary.
- `LD_LIBRARY_PATH`.
- `RPATH` or `RUNPATH`.
- `ld.so.cache` configuration.
- System library directories.
- Symbol versions and dependency chain.

A checkpoint created after a library has been mapped into the process may preserve those mappings. However, subsequent library loads after restore, creation of new native components, or reopening of resources still depend on the current filesystem and linker environment.

Do not replace libraries inside the container image after a checkpoint is created and still expect the old native state to remain compatible. Treat the base image, native packages, and JDK as part of the checkpoint identity.

## 7. Filesystem, File Descriptors, and Memory Mappings

Java applications frequently use files through streams, channels, memory mappings, or native libraries. Some state can be checkpointed, but recoverability depends on the file type and filesystem.

Notable differences:

- ext4, XFS, overlayfs, tmpfs, or network filesystems.
- Mount options.
- Bind mounts and volume identity.
- Open file descriptors.
- File locks and advisory locks.
- Memory-mapped files.
- Files that have been renamed or replaced.
- File contents modified during checkpoint.
- Permissions, ownership, and SELinux labels.

### 7.1. A File Descriptor Is Not Just an Integer

Inside a process, a file descriptor is a handle to an open file description or kernel resource. A numeric value such as 17 is not enough to describe a resource usable in another environment.

If the application holds file descriptors across a checkpoint, verify whether that resource type is supported by CRIU and whether the target filesystem is compatible. For temporary files, file locks, or application-managed files, it is usually safer to close them before checkpoint and reopen them after restore.

### 7.2. Memory-Mapped Files

A memory mapping links a process memory region to a backing file or resource. If the file is modified, replaced, or mounted differently after checkpoint, the mapping may no longer carry the meaning the application expects.

Applications using mapped files for indexes, databases, or caches need a policy to check versions and reopen mappings after restore if the source data may have changed.

### 7.3. File Locks

A file lock may be managed by the kernel or the filesystem. Do not assume the lock still belongs to the application after the process is checkpointed and restored in a different environment.

For locks used to protect data, verify ownership and lock status after restore. If the lock is a distributed lock or lease, check the expiration and fencing token in the lock management system.

## 8. Network Stack and System Libraries

Network connections depend on the kernel, network namespace, interfaces, routes, firewall, NAT, and remote peers. The same Java client may behave differently when restored on a different host.

Differences may include:

- Local IP address.
- Routes and gateways.
- DNS resolver.
- Network namespace.
- Port allocation.
- Firewalls and network policies.
- NAT mappings.
- Proxies and load balancers.
- TLS libraries and trust stores.
- Kernel TCP behavior.

For outbound connections to a database, Redis, Kafka, or HTTP service, the application should typically drain and close connections before checkpoint, then create new connections after restore using the current configuration.

For listening sockets, determine whether the socket is supported for restore by CRIU/runtime in that environment. If the listener was already restored and the port is still held, rebinding may cause an "address already in use" error. If the listener was not restored, the application must open a new listener before reporting readiness.

### 8.1. DNS and Resolvers

DNS can change during the lifetime of a checkpoint. An established TCP connection does not automatically switch to a new address when DNS records change. After restore, creating a new connection will use the resolver and cache under the current configuration, but the JVM or a library may hold a DNS cache.

Check TTL, resolver configuration, and the JVM's DNS caching policy. For services using service discovery, refresh endpoints before reconnecting.

### 8.2. OpenSSL and TLS

A native TLS library may depend on the OpenSSL version, providers, certificate store, and cipher configuration. If the restore environment differs, new handshakes may fail or negotiate different algorithms.

After restore, recreate connections and perform handshakes using the current trust configuration. Do not retain TLS sessions or credentials in the heap without checking expiry and security policies.

## 9. Security Policy: seccomp, AppArmor, and SELinux

Checkpoint/restore requires certain system operations that can be restricted by security policies. In containers, a seccomp profile can block system calls. Linux capabilities determine whether a process can perform certain administrative operations. AppArmor and SELinux can restrict access to files, sockets, or processes.

Two environments with the same kernel but different policies can yield different results.

Things to consider:

- Seccomp profile and allowed system calls.
- Granted Linux capabilities.
- AppArmor profile.
- SELinux mode, type, and labels.
- Access permissions to /proc and /sys.
- Access permissions to the CRIU image directory.
- Access permissions for mounts and file descriptors.
- User namespace mapping.

Do not resolve errors by disabling all security mechanisms. Identify the specific blocked operation, then apply the minimal policy that meets the requirements of CRaC/CRIU and the platform.

## 10. Locale, Timezone, Environment, and Runtime Configuration

Some environment state is read at JVM startup or when native libraries are loaded. After restore, the process may still hold the old values even if the external environment has changed.

Values to pay attention to:

- `TZ` and timezone database.
- Locale and character encoding.
- `LANG` and `LC_*`.
- `PATH` and `LD_LIBRARY_PATH`.
- Proxy environment variables.
- Trust store and certificate paths.
- Secret mounts.
- JVM system properties.
- Native library configuration.
- Configuration files and feature flags.

Not every environment variable is re-read after restore. Some libraries cache values in static fields or native state. If configuration can change between runs, an explicit refresh mechanism is needed rather than assuming the process picks up new values automatically.

## 11. JDK Distribution and Native Runtime

The CRaC JDK is part of the checkpoint environment. Two JDKs reporting the same Java version number but built differently can differ in:

- Vendor and build.
- CRaC patches or integration.
- JVM implementation.
- GC and compiler.
- Packaged native libraries.
- Default JVM flags.
- Modules and security providers.
- How CRIU is integrated.

Checkpoints should be created and restored using a JDK distribution/version confirmed compatible. Avoid swapping the JDK image or updating native packages between the two stages without creating and testing a new checkpoint.

### 11.1. Inspecting the Java Runtime

You can record:

~~~bash
java -version
java -XshowSettings:properties -version
~~~

Information to save alongside the checkpoint manifest:

- JDK vendor.
- Java runtime version and build.
- JVM flags.
- GC configuration.
- CRaC support/version.
- Native library paths.
- Important modules or providers.

### 11.2. Do Not Substitute JDKs Based Only on the Same Major Version

For example, two images may both report Java 21 yet differ in vendor build, CRaC patches, or native libraries. That does not prove a checkpoint created by one image can be restored by the other.

Keep the image digest unchanged or create a new build and repeat the warm-up/checkpoint process when upgrading the runtime. For security patch changes, evaluate both security requirements and compatibility, and release a newly tested checkpoint.

## 12. Compatibility Matrix Between Image Creation and Restore Environments

Not every aspect needs to be strictly identical in all cases. What matters is identifying which factors must be compatible, which factors are allowed to differ, and the test evidence for each combination.

| Component | Should Be Kept Compatible | When Can It Change? |
|---|---|---|
| CPU architecture | Same supported architecture | Only when CRaC/runtime confirms support |
| CPU features | Feature set compatible with native/JIT code | When using a tested common baseline |
| JDK distribution/build | Same confirmed build | When creating and testing a new checkpoint |
| Kernel | Sufficient kernel features required by CRIU | When supported by CRIU/JDK and restore has been tested |
| CRIU | Compatible version and image format | According to the CRIU compatibility matrix |
| libc/dynamic linker | Matching ABI and symbol dependencies | When binaries are built compatibly |
| Native libraries | Same ABI and dependency chain | When the library is proven compatible |
| Filesystem/mount | Required resources and mounts remain valid | When not dependent on old files/mappings |
| Namespace | Compatible process and resource mappings | According to runtime and CRIU support |
| Security policy | Allows required operations | When the new policy has been tested |
| Network | Endpoints and routes can be re-established | Usually changeable if the app reconnects |
| Secret/configuration | Must be valid in the target environment | Can be refreshed via a provider after restore |

This table is a design guide, not an official compatibility commitment for all CRaC builds. The final matrix must be based on JDK, CRIU, and kernel documentation and test results.

## 13. Building a Checkpoint Manifest

Create a manifest alongside each checkpoint to know which environment the image was created in. A manifest does not make the image portable, but it helps detect discrepancies before restore.

Example manifest contents:

~~~yaml
checkpoint:
  applicationVersion: "2026.11.13"
  imageDigest: "sha256:..."
  createdAt: "2026-11-13T08:00:00Z"

runtime:
  jdkVendor: "Example JDK distribution"
  javaVersion: "21"
  jdkBuild: "record-exact-build"
  jvmFlags:
    - "-Xms512m"
    - "-Xmx512m"

platform:
  os: "Linux"
  architecture: "x86_64"
  kernelRelease: "record-exact-kernel"
  libc: "glibc"
  libcVersion: "record-version"
  criuVersion: "record-version"
  containerRuntime: "containerd"
  cgroupMode: "v2"

native:
  libraries:
    - "libexample.so"
    - "libssl.so"
  cpuBaseline: "record-supported-feature-set"

security:
  seccompProfile: "record-profile-version"
  capabilities:
    - "record-required-capability"

restorePolicy:
  allowedNodePool: "crac-compatible-pool"
  requiresNetworkReconnect: true
  requiresNativeResourceReinitialization: true
~~~

The values in the example are placeholders. Fill in actual data from the build pipeline and the host/container where the checkpoint is created. Do not write passwords, tokens, private keys, or secrets into the manifest.

### 13.1. Manifest and Image Digest

Bind the checkpoint to an image digest rather than only a tag like `latest`. A tag can be repointed to another image after the checkpoint is created. A digest uniquely identifies the container image containing the JDK, libc, and native packages.

If the image is updated, create a new checkpoint following the verified process. Do not modify library files inside the image and continue using an old checkpoint.

## 14. Build and Environment Verification Workflow

A workflow can be divided into stages:

~~~mermaid
flowchart TD
    A["Build application image"] --> B["Pin JDK and native dependencies"]
    B --> C["Record OS, CPU and CRIU baseline"]
    C --> D["Run CRIU capability checks"]
    D --> E["Start application and warm up"]
    E --> F["Prepare resources through CRaC"]
    F --> G["Create checkpoint"]
    G --> H["Store checkpoint with manifest"]
    H --> I["Select compatible restore node"]
    I --> J["Compare environment with manifest"]
    J --> K{"Compatibility checks pass?"}
    K -->|No| L["Reject restore or rebuild checkpoint"]
    K -->|Yes| M["Restore and run smoke checks"]
    M --> N["Open readiness"]
~~~

### Step 1: Pin the Platform

Select the JDK distribution, base image, libc, native libraries, and architecture. Avoid using floating-version packages in the checkpoint-creating image.

### Step 2: Record Host and Container Details

Collect kernel release, CRIU version, CPU architecture, CPU features, cgroup mode, namespaces, mounts, and security policies.

### Step 3: Check CRIU

Run CRIU capability checks in the actual environment. Confirm required permissions and kernel features.

### Step 4: Run the Application and Warm Up

Start the application inside the pinned image. Warm up a representative workload and prepare caches according to policy.

### Step 5: Prepare Native Resources

Close or refresh connections, file descriptors, threads, native handles, and resources that libraries do not support restoring. Use CRaC Resources or library integrations.

### Step 6: Create Checkpoint and Manifest

Create the image using a procedure supported by the CRaC JDK. Save the manifest and image digest alongside the artifact.

### Step 7: Select the Restore Environment

Deliver the image only to node pools or hosts with compatible kernel, CPU, JDK, native dependencies, and policies.

### Step 8: Pre-Restore Checks

Compare the manifest against the target environment. If mandatory conditions are missing, reject the restore and create a new checkpoint on the target platform.

### Step 9: Post-Restore Smoke Tests

Check the application, native libraries, database, Redis, broker, filesystem, and essential endpoints. Open readiness only after these checks pass.

## 15. Checking Differences with System Commands

The following commands help collect evidence. Run them on both the checkpoint creation environment and the restore environment, then save the results alongside the manifest.

### 15.1. Kernel and OS

~~~bash
uname -a
cat /etc/os-release
cat /proc/version
~~~

### 15.2. CPU Architecture and Features

~~~bash
uname -m
lscpu
grep -m1 '^flags' /proc/cpuinfo
~~~

### 15.3. JDK and CRIU

~~~bash
java -version
criu --version
criu check
~~~

### 15.4. Cgroup

On systems using cgroup v2, you can check:

~~~bash
stat -fc %T /sys/fs/cgroup
cat /proc/self/cgroup
~~~

A `cgroup2fs` output typically indicates that the cgroup v2 filesystem is mounted at the checked location. Also inspect the controller configuration and limits applied to the container.

### 15.5. Namespace

You can inspect the namespaces of the current process:

~~~bash
ls -l /proc/self/ns
readlink /proc/self/ns/pid
readlink /proc/self/ns/mnt
readlink /proc/self/ns/net
readlink /proc/self/ns/user
~~~

Different namespace inodes across hosts do not automatically prove incompatibility. The goal is to understand which types of namespaces the process is running in and how the runtime will restore them.

### 15.6. Native Libraries

~~~bash
file /opt/app/lib/libexample.so
ldd /opt/app/lib/libexample.so
readelf -h /opt/app/lib/libexample.so
readelf -d /opt/app/lib/libexample.so
~~~

The path is an example. Replace it with the actual library location. Compare dependencies and ABIs in both images.

## 16. Common Compatibility Errors and How to Analyze Them

| Symptom | Possible Cause | Investigation Direction |
|---|---|---|
| CRIU rejects dump/restore | Unsupported kernel feature or resource | Read CRIU logs, run capability check |
| Operation not permitted | Missing capability or blocked by security policy | Check capabilities, seccomp, AppArmor/SELinux |
| File not found after restore | Different mount or volume | Compare mount namespaces and paths |
| Native library load failure | Missing .so or wrong dynamic linker | Check ELF interpreter, ldd, symbol versions |
| Undefined symbol | Different ABI or dependent library version | Check readelf and package versions |
| Illegal instruction | CPU lacks instruction set used by binary/JIT | Compare architecture and CPU flags |
| Cannot create thread | PID/thread limit or resource limit | Check cgroups and ulimit |
| Cannot bind port | Listener already restored or port already taken | Check sockets, processes, and port mappings |
| Connection timeout | Network namespace, route, or peer changed | Resolve DNS, check routes, and reconnect |
| TLS handshake error | Different OpenSSL, trust store, or certificates | Check TLS config and certificates |
| Permission denied on file | UID/GID mapping or security label | Check ownership, mode, SELinux/AppArmor |
| App restores but native error occurs | Native handle or internal thread not restored | Check vendor support and lifecycle callbacks |

Do not modify multiple components at once while investigating. Identify the first failing layer in the logs, compare the checkpoint/restore environments, and change one factor in a controlled manner.

## 17. How Should Checkpoints Be Packaged by Platform Group?

For systems deployed across multiple node types, you can create separate checkpoints for each verified platform group.

For example:

| Checkpoint profile | Target platform | Rule |
|---|---|---|
| linux-x86-baseline | Linux x86-64 with a defined CPU baseline | Restore only onto the corresponding node pool |
| linux-arm64 | Linux AArch64 | Create a separate image for ARM64 architecture |
| linux-x86-native-v2 | x86-64 with specialized native dependencies | Bind to the pinned image and ABI |
| linux-kernel-pool-a | Node group with tested compatible kernel/runtime | Distribute only within the confirmed pool |

These are illustrative names. Do not create too many profiles if the differences do not affect compatibility. Conversely, do not merge hosts with incompatible native ABIs or CPU features into the same group just to reduce the number of artifacts.

### 17.1. Compatible Node Pools

In Kubernetes, you can use node labels and scheduling rules to constrain checkpoint restore to a suitable node group. Label naming should reflect meaningful characteristics such as architecture, CRaC baseline, or native runtime profile.

Do not use only a generic label such as `linux=true`. Linux is too broad to describe compatibility boundaries.

### 17.2. When Upgrading the Kernel or Base Image

Upgrading the kernel, CRIU, container runtime, libc, OpenSSL, or JDK can alter restore conditions. Before rolling out:

1. Create a new checkpoint on the upgraded platform.
2. Restore on a target node.
3. Run smoke tests and verify native dependencies.
4. Measure restore time and readiness.
5. Distribute the new checkpoint only when criteria are met.
6. Retain old artifacts for the rollback window if policy permits.

Do not continue using an old checkpoint simply because the application JAR did not change.

## 18. Resources That Should Be Re-established via CRaC Callbacks

Some resources depend heavily on the environment and generally need to be closed before checkpoint and recreated after restore:

| Resource | Before checkpoint | After restore |
|---|---|---|
| JDBC connection/pool | Drain and close per library | Create new pool/connections |
| Redis client | Stop commands, listeners, and pool | Reconnect, refresh topology |
| HTTP client/socket | Drain requests and close connections as needed | Create new client/connections |
| File watcher | Stop watcher | Re-register watcher |
| Native device handle | Call release API if supported | Reopen and verify device |
| Native library worker | Stop internal threads per vendor API | Reinitialize worker |
| DNS/service discovery | Stop refresh tasks if needed | Resolve current endpoints |
| Scheduler | Pause and drain tasks | Recalculate schedules and create scheduler |
| Client-side cache listener | Stop listener | Resubscribe and reconcile cache |

Not every resource needs to be closed. Consult the CRaC JDK and library documentation to determine which resources support checkpoint/restore. Redundantly closing a resource already managed by a framework can cause lifecycle errors.

## 19. Strategy When the Restore Environment Differs from the Creation Environment

If the target environment differs, classify the discrepancies.

### 19.1. Discrepancies Handled by the Application

For example:

- Service hostname or IP.
- Credentials or secrets.
- DNS records.
- Feature flags.
- Database endpoints.
- Cache entries and tokens.

These values can usually be refreshed after restore if the application is designed appropriately.

### 19.2. Discrepancies Requiring Runtime-Level Compatibility

For example:

- JDK build and CRaC integration.
- Kernel/CRIU support.
- CPU architecture and features.
- Native library ABI.
- Dynamic linker and libc.
- Memory mappings and native runtime.

These differences cannot be fixed merely by invoking a Java callback. It may be necessary to rebuild the image, native libraries, or checkpoint on the target environment.

### 19.3. Discrepancies That Should Not Be Recovered at Runtime

If a checkpoint requires an incompatible CPU architecture or ABI, or the kernel does not support a required resource, reject the restore and create a new checkpoint. Trying to proceed may cause crashes or hard-to-diagnose data errors.

## 20. Pre-Release Checkpoint Compatibility Checklist

### Kernel and CRIU

- [ ] Kernel release and build are recorded.
- [ ] CRIU version is recorded and supports the environment.
- [ ] Capability check has been run on the target host.
- [ ] Namespaces and cgroup mode have been identified.
- [ ] Sufficient system permissions and appropriate security policy are in place.

### CPU and Native ABI

- [ ] Build/restore CPU architectures are compatible.
- [ ] CPU feature baseline has been defined.
- [ ] JDK and JVM build are pinned.
- [ ] libc and dynamic linker have been checked.
- [ ] JNI/native library dependency chain has been checked.
- [ ] No instruction sets or symbol dependencies are missing in the target environment.

### Filesystem and Network

- [ ] Critical mounts, volumes, and paths are compatible.
- [ ] File descriptors, locks, and memory mappings have been evaluated.
- [ ] Network namespace, routes, and DNS are verified.
- [ ] Outbound connections have a reconnect procedure.
- [ ] Listening sockets are handled per confirmed restore mechanism.

### Container and Security

- [ ] Container runtime and image digest are recorded.
- [ ] UID/GID mapping and capabilities have been verified.
- [ ] Seccomp, AppArmor, or SELinux policies allow required operations.
- [ ] Cgroup memory, CPU, and PID limits are sufficient for restore.
- [ ] Disabling all security policies is not required for checkpoint/restore to work.

### Restore and Operations

- [ ] Checkpoint manifest accompanies the artifact.
- [ ] Restore environment is compared against the manifest.
- [ ] Restore has been tested on each target node group.
- [ ] Native libraries and external dependencies have been smoke-tested.
- [ ] Readiness opens only after essential resources are ready.
- [ ] A process exists to create a new checkpoint when the platform changes.

## 21. Frequently Asked Questions

### Is Running Linux on Both Machines Enough to Restore a Checkpoint?

No. Linux varies widely across kernel versions, configurations, architectures, namespaces, filesystems, security policies, and native runtimes. You must check the features required by CRIU/JDK and test restore in the target environment.

### Are Two Machines with the Same Kernel Version Guaranteed to Be Compatible?

No. They can still differ in kernel configuration, modules, capabilities, cgroups, security policies, mounts, CPU features, or native libraries. Kernel version is one data point in the matrix, not a certification of compatibility.

### Can an x86-64 Checkpoint Be Restored on ARM64?

You should not assume it can. A checkpoint contains CPU and native process state tied to the architecture. Create separate checkpoints for each supported architecture and follow the JDK/CRIU documentation.

### Can glibc or OpenSSL Be Changed After Creating a Checkpoint?

Changing native libraries can alter ABIs, symbols, or process mapping state. Do not replace packages inside the image and continue using an old checkpoint without support confirmation. Build and test a new checkpoint with the new dependencies.

### Does the Same Container Image Guarantee Restore on Any Host?

No. A container image does not package the host kernel. Hosts can still differ in kernel, CPU, CRIU, cgroups, namespaces, and security policies. Both the image and the host must be verified.

### Why Does CRIU Check Succeed Yet Restore Still Fail?

Capability checks only verify certain capabilities of the environment. An actual workload may use special resources, native libraries, sockets, mounts, or namespaces not covered by a generic check. Read the logs of the dump/restore run and test the actual workload.

### Should Every Native Library Be Closed Before Checkpoint?

No. Close only the resources that the library requires closing or that do not support checkpoint/restore. Some native libraries can preserve state safely; others need shutdown and reinitialization. Follow vendor documentation and test in practice.

### Must a New Checkpoint Be Created When the Kernel Is Upgraded?

You should retest. If the change affects kernel features, CRIU, container runtime, or resource management, the old checkpoint may no longer be compatible. For production platforms, creating a new checkpoint and test-restoring it before rollout is the safe management practice.

### Can All Discrepancies Be Fixed Using afterRestore()?

No. Java callbacks are suited for refreshing configuration, recreating connections, opening files, or starting workers. They cannot turn machine code of the wrong architecture into compatible code, supply missing kernel features, or fix an incompatible native ABI.

## Conclusion

CRaC restore capability depends on many native layers underneath the Java application: kernel, CRIU, namespaces, cgroups, CPU architecture, instruction sets, dynamic linker, libc, JNI libraries, filesystem, network stack, and security policies. The same JAR or container image is not enough to prove a checkpoint can run on every Linux host.

Pin the JDK and native dependencies, record the kernel/CRIU/CPU baseline, close or re-establish environment-dependent resources via CRaC callbacks, create a manifest for each checkpoint, and restrict restore to tested platform groups. When the kernel, CPU, ABI, or native runtime changes, verify compatibility and create a new checkpoint if necessary.