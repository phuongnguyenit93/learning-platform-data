# Capabilities, Seccomp, and Security Context by Checkpoint Engine

Checkpoint/restore in containers is not solely a JVM operation. The snapshot-creating engine must read process state, freeze threads, access information in /proc, work with namespaces, file descriptors, cgroups, and sometimes restore network state. Linux protects these operations with capabilities, seccomp, user namespaces, AppArmor, SELinux, and container runtime policies.

Therefore, there is no single permission set that applies to every CRaC application. Required privileges depend on which engine creates the checkpoint, where the engine runs, the kernel, the container runtime, and the types of resources used by the process. A Java application using the Warp engine has different requirements from one using CRIU; checkpointing a container via kubelet has different privilege boundaries from running CRIU directly inside the application container.

The first thing to determine is **who actually performs the checkpoint**:

- A JVM CRaC engine such as the CRIU engine or Warp.
- The container runtime and low-level runtime such as containerd/CRI-O and runc/crun, invoking CRIU on the node side.
- A CRIU process run directly by an operator or a checkpoint service.

Only after identifying the engine and execution boundary should you choose the appropriate capabilities, seccomp profile, and security context. Do not enable privileged mode or disable seccomp entirely just because a checkpoint attempt fails with Operation not permitted.

## 1. Distinguishing Checkpoint Engine Layers

The CRaC API is designed independently of the image-creation mechanism. The API notifies the application that checkpoint or restore is occurring; the specific engine decides how process state is saved and reconstructed. The same application can run with different engines depending on the JDK distribution.

### 1.1. Common Engines

| Engine | Mechanism | Linux Privileges | Usage Scope |
|---|---|---|---|
| OpenJDK CRaC criuengine | Invokes CRIU to dump/restore the process | Requires elevated privileges; inside containers typically needs CAP_CHECKPOINT_RESTORE and CAP_SYS_PTRACE; certain features need additional privileges | Creating real process snapshots on Linux |
| OpenJDK CRaC simengine | Invokes pre-checkpoint callbacks followed by post-restore callbacks within the same process | No CRIU privileges needed to create OS images | Developing and testing Resource logic; does not create a deployable image |
| Azul Zulu warp | Azul's proprietary engine, does not use CRIU | Does not require extra Linux capabilities for checkpoint/restore according to Azul documentation | Real checkpoint/restore on Azul-supported builds and platforms |
| Container checkpoint via Docker/containerd/CRI-O | Container runtime invokes low-level runtime, typically runc and CRIU | Privileges primarily belong to node-side runtime/helper; not granted to the application by default | Saving full container state and restoring the container |

OpenJDK CRaC currently provides criuengine and simengine. criuengine is the default engine on Linux in upstream OpenJDK CRaC and requires higher privileges; simengine only simulates the callback cycle and does not write a process image. Some vendor distributions may add their own engines.

Azul has the warp engine, which does not depend on CRIU and requires no extra capabilities for checkpoint/restore. According to Azul documentation, Warp became the default engine in the April 2026 Zulu release. Verify the exact JDK build being deployed; do not assume every CRaC-enabled JDK includes Warp.

### 1.2. Selecting an Engine

For OpenJDK CRaC using CRIU:

~~~bash
java -XX:CRaCEngine=criuengine \
     -XX:CRaCCheckpointTo=/opt/checkpoints \
     -jar app.jar
~~~

For Azul Zulu builds with Warp:

~~~bash
java -XX:CRaCEngine=warp \
     -XX:CRaCCheckpointTo=/opt/checkpoints \
     -jar app.jar
~~~

For callback simulation in a development environment:

~~~bash
java -XX:CRaCEngine=simengine \
     -XX:CRaCCheckpointTo=./checkpoint \
     -jar app.jar
~~~

Valid engine names depend on the JDK build. If you select an engine not present in the runtime, the JVM may fail immediately at startup. simengine helps detect misbehaving Resource callbacks, but cannot test kernel support, seccomp, file descriptors, sockets, or actual snapshot creation.

### 1.3. In-JVM CRaC and Container Checkpointing Have Different Boundaries

In JVM CRaC, the application asks the runtime to save JVM state. CRIU may be invoked by a JDK helper. In Kubernetes container checkpointing, kubelet calls a checkpoint API on the node; the container runtime such as containerd or CRI-O forwards the request to the low-level runtime such as runc, and runc invokes CRIU.

High-level Kubernetes flow:

~~~mermaid
flowchart TD
    A[Administrator or controller] --> B[Kubelet checkpoint API on the node]
    B --> C[Container runtime: containerd or CRI-O]
    C --> D[Low-level runtime: runc]
    D --> E[CRIU on the node]
    E --> F[Checkpoint archive]
~~~

In this model, the application inside the Pod does not necessarily need CAP_CHECKPOINT_RESTORE or CAP_SYS_PTRACE itself. Privileges can be granted to the node-side runtime/helper. Granting capabilities to the Pod simply because the node needs them widens privileges across the wrong boundary.

Kubernetes provides the kubelet checkpoint API at a node-local endpoint. CRIU documentation describes the path from kubelet through the container runtime to runc and CRIU; the checkpoint is saved as an archive in the node's checkpoint directory. This is a container runtime feature, not a Core.getGlobalContext().register() operation inside the Java application.

## 2. Linux Capabilities That CRIU May Require

Linux splits privileges traditionally tied to root into finer-grained capabilities. Capabilities are per-thread attributes; effective permissions also depend on effective, permitted, inheritable, and bounding sets, user namespaces, and how the runtime launches the helper.

### 2.1. CAP_CHECKPOINT_RESTORE

CAP_CHECKPOINT_RESTORE was added in Linux kernel 5.9 to separate certain checkpoint/restore privileges from the broad CAP_SYS_ADMIN capability. According to the Linux capabilities manual, it permits operations such as:

- Updating /proc/sys/kernel/ns_last_pid.
- Using the set_tid feature of clone3().
- Reading symlinks inside /proc/<pid>/map_files of another process.

This is a critical capability for CRIU. On Linux versions supporting it, CRIU can run non-root in certain configurations with CAP_CHECKPOINT_RESTORE, though that does not mean every CRIU feature works with only that privilege.

A noteworthy limitation: certain accesses to /proc/<pid>/map_files require the capability in the init user namespace. Having CAP_CHECKPOINT_RESTORE in a nested user namespace inside a container is not necessarily equivalent to having it in the host's init namespace.

### 2.2. CAP_SYS_PTRACE

CAP_SYS_PTRACE permits ptrace operations that bypass normal permission checks. CRIU uses tracing mechanisms to freeze and inspect the process to be dumped. When running CRIU non-root, CRIU documentation states it requires CAP_SYS_PTRACE or setting kernel.yama.ptrace_scope=0 to be able to interrupt processes.

Do not lower ptrace_scope node-wide just to avoid granting capabilities to a single workload. That change affects tracing scope across the entire host. Use narrowly scoped privileges on the proper helper and node when required by the engine.

### 2.3. CAP_SYS_ADMIN

CAP_SYS_ADMIN is a very broad capability covering numerous kernel administration operations such as mounts, namespaces, and certain cgroup actions. CRIU documentation allows running non-root with CAP_SYS_ADMIN or CAP_CHECKPOINT_RESTORE, yet CAP_SYS_ADMIN is not a safe default choice for every container.

Some CRIU code paths may still require CAP_SYS_ADMIN, such as handling mounts/cgroups or seccomp suspend. A CRIU issue opened on 21-10-2026 noted that CAP_CHECKPOINT_RESTORE is insufficient for the seccomp-suspend path using PTRACE_O_SUSPEND_SECCOMP; the kernel checks CAP_SYS_ADMIN in the init user namespace. Therefore, if checkpointing a process with a seccomp filter, verify the exact CRIU build and kernel rather than extrapolating from the minimal capability requirements of a non-seccomp case.

If a specific feature requires CAP_SYS_ADMIN, place CRIU inside an independently managed helper or node service with bounded privileges, nodes, target processes, and lifetime. Avoid granting long-lived CAP_SYS_ADMIN to the entire Java application solely to support checkpointing.

### 2.4. Additional Capabilities

Depending on checkpointed resources and enabled CRIU features, other capabilities may be required:

| Capability | When It May Be Needed | Notes |
|---|---|---|
| CAP_NET_ADMIN | Restoring or adjusting network namespaces, interfaces, and routes | Depends on network namespace handling; not needed by all applications |
| CAP_SYS_CHROOT | Root filesystem/chroot operations during certain restore workflows | Depends on mount namespace configuration |
| CAP_SETUID | Restoring UID or switching process identity | Requires checking user namespaces and UID/GID mappings |
| CAP_SYS_RESOURCE | Certain operations involving resource limits | Depends on the process and runtime |

This list is not a universal permission manifest. CRIU documentation enumerates additional capabilities CRIU can use in non-root mode; whether any is needed depends on logs, feature checks, and actual resources.

### 2.5. Quick Decision Table

| Model | Privileges to Check First |
|---|---|
| Azul Warp in container | No extra engine capabilities needed; still requires filesystem permissions and valid container configuration |
| OpenJDK CRaC criuengine in Docker | Typically start by checking CHECKPOINT_RESTORE and SYS_PTRACE |
| CRIU running directly inside container | CAP_CHECKPOINT_RESTORE, CAP_SYS_PTRACE, user namespaces, procfs, and additional resource-specific permissions |
| CRIU run by container runtime on node | Runtime/helper capability config on the node; not granted to the application Pod by default |
| Containerd/CRI-O checkpoint via kubelet | Node-side kubelet/runtime privileges and node CRIU capabilities |
| simengine | No OS image-creation privileges needed; used only for testing callbacks |

## 3. Seccomp and Checkpoint/Restore

Seccomp (secure computing mode) filters the system calls a process is allowed to invoke into the kernel. Container runtimes typically apply a default seccomp profile to reduce attack surface. Kubernetes allows selecting profiles at the Pod or container level.

Seccomp differs from Linux capabilities:

- Capabilities determine whether a process is permitted to perform a group of privileged operations.
- Seccomp determines which system calls are allowed across the userspace/kernel boundary, optionally based on system call arguments as well.
- A process that has a capability but whose required system call is blocked by seccomp will still receive an error.
- A system call permitted by seccomp does not automatically grant the capability required for that operation.

### 3.1. Two Seccomp Layers to Distinguish

When checkpointing a container, there can be at least two filters:

1. **Seccomp of the CRIU/helper environment:** determines whether CRIU can invoke the system calls needed to read state, create namespaces, or restore the process.
2. **Seccomp of the target process:** the filter the application was running under before checkpoint. CRIU must be able to handle and accurately restore this filter state.

These are two separate concerns. Relaxing seccomp for the helper does not mean removing the application's protective filter after restore. Conversely, keeping seccomp overly restrictive for the CRIU helper may cause dump/restore itself to fail before handling the target process.

### 3.2. CRIU and the Target Process's Seccomp Filter

CRIU can save and restore a process's seccomp state. However, to checkpoint a process running under a filter, CRIU may need to suspend or bypass the filter during certain inspection/code-injection steps. This capability depends on the kernel and CRIU.

Current Docker documentation notes that seccomp is only supported by CRIU on very recent kernels. In addition, CRIU issue #3244 (October 2026) describes the seccomp_suspend path: the kernel checks CAP_SYS_ADMIN in the init user namespace for PTRACE_O_SUSPEND_SECCOMP; CAP_CHECKPOINT_RESTORE alone does not satisfy that check. Because this detail depends on kernel/CRIU versions, run preflight checks on the exact target nodes.

Some test setups use unconfined seccomp to determine whether a failure originates from the filter. This is strictly a diagnostic step in an isolated environment. Do not use Unconfined or seccomp=unconfined as a default production configuration.

### 3.3. Seccomp Options in Kubernetes

Kubernetes supports three seccompProfile.type values:

| Type | Meaning | When to Use |
|---|---|---|
| RuntimeDefault | Uses the container runtime's default profile | Baseline choice for ordinary workloads; the profile may differ between containerd and CRI-O |
| Localhost | Uses a JSON profile pre-installed on the node, typically under /var/lib/kubelet/seccomp | When a custom syscall allowlist is needed for CRIU/helper or specialized workloads |
| Unconfined | No seccomp filter applied | Should only be used for controlled diagnostics or explicitly approved special cases |

Profiles can be set at the Pod level or container level. Container-specific settings override Pod-level settings; containers without an explicit setting inherit the Pod profile. A Localhost profile must exist on the node, otherwise the container may fail to create.

Example Pod using the default profile:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: java-service
spec:
  securityContext:
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: app
      image: example/java-service:latest
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        allowPrivilegeEscalation: false
        capabilities:
          drop:
            - ALL
~~~

This is a baseline configuration for a workload that does not run a CRIU helper inside the container. With Warp, this is usually a better fit because the engine requires no CRIU capabilities; the application still needs write permissions to the checkpoint volume and whatever permissions the workload itself requires.

### 3.4. Localhost Seccomp Profile for CRIU

When CRIU runs inside a container, the RuntimeDefault profile may block a system call required by the engine. In that case, you can deploy a Localhost profile built for the exact CRIU version, kernel, and types of resources being checkpointed.

Example of referencing the profile:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: criu-helper
spec:
  containers:
    - name: checkpoint-helper
      image: example/criu-helper:tested-version
      securityContext:
        seccompProfile:
          type: Localhost
          localhostProfile: crac/criu-helper.json
~~~

In this example, kubelet looks up the profile at /var/lib/kubelet/seccomp/crac/criu-helper.json. Profile contents cannot safely be copied from a generic online template because the syscall list depends on CRIU, the kernel, CPU architecture, the runtime, and the checkpoint features used.

Build the profile following the allowlist principle:

1. Start from the current runtime profile.
2. Run CRIU preflight and a representative workload in a test environment.
3. Collect denied syscalls from audit/logs.
4. Add only the syscalls required for the specific feature.
5. Test both dump and restore, including error and rollback paths.
6. Freeze the profile version alongside the tested kernel, CRIU, and runtime versions.

Do not copy a profile from one CRIU distribution to another without verification. A profile for an application without a network namespace, seccomp filter, or special mounts may not work for another process.

## 4. Security Context in Kubernetes

A security context is the set of privilege and isolation attributes applied to a Pod or container. It goes beyond capabilities. During checkpoint/restore, pay simultaneous attention to UID/GID, capability sets, no_new_privs, seccomp, AppArmor, SELinux, filesystems, and namespaces.

### 4.1. Key Fields

| Field | Effect | Relevance to Checkpoint/Restore |
|---|---|---|
| runAsUser, runAsGroup | Process UID/GID | CRIU must read/restore compatible identity and file permissions |
| runAsNonRoot | Requires container not to run as UID 0 | May affect how the helper runs and /proc access permissions |
| capabilities.add/drop | Adds or drops Linux capabilities | Determines whether CRIU has permission for tracing, checkpointing, or namespace operations |
| allowPrivilegeEscalation | Controls no_new_privs | Can block gaining additional privileges via setuid/file capabilities |
| seccompProfile | Filters system calls | May block CRIU or be saved/restored as part of process state |
| appArmorProfile | Restricts access via AppArmor profile | May block ptrace, procfs, checkpoint paths, or file operations |
| seLinuxOptions | Applies SELinux labels to process/volumes | May block access to processes, image files, or mounts |
| readOnlyRootFilesystem | Read-only root filesystem | Checkpoint paths and temp directories need separate writable volumes |
| privileged | Grants very broad privileges and bypasses several protection layers | Can disable seccomp/AppArmor/SELinux; avoid unless strictly required |

### 4.2. allowPrivilegeEscalation and no_new_privs

In Kubernetes, allowPrivilegeEscalation: false sets the no_new_privs flag on the container process. This flag prevents the process from gaining additional privileges through mechanisms such as executing setuid binaries. If CRIU is installed under a setuid helper model, no_new_privs can prevent that privilege-elevation path from working.

allowPrivilegeEscalation: false cannot be combined with a privileged container or one having CAP_SYS_ADMIN. If a specific CRIU feature requires CAP_SYS_ADMIN, re-evaluate the security context and move the privileged portion into an independently managed helper rather than forcing all attributes into a single Pod.

When capabilities are granted directly by the runtime, do not assume no_new_privs strips all granted capabilities. Inspect the helper's actual capability sets and how the JDK/CRIU is installed. What to avoid is relying on a setuid path while no_new_privs is blocking privilege gain.

### 4.3. AppArmor and SELinux

Capabilities and seccomp are not the entire security boundary. AppArmor and SELinux can still deny an operation even when the process holds the capability and seccomp allows the syscall.

Areas CRIU commonly needs to access include:

- /proc/<pid>/status, /proc/<pid>/fd, /proc/<pid>/fdinfo.
- /proc/<pid>/maps, /proc/<pid>/map_files, and memory mapping information.
- Checkpoint image directory and log/work directories.
- Cgroup filesystem and relevant namespaces.
- Files, mounts, sockets, or devices declared as external resources.

The AppArmor profile must permit the exact paths and operations required. SELinux requires appropriate labels for processes, checkpoint volumes, and mounts. Do not switch the entire workload to unconfined just to work around an AVC denial; read the audit logs and update the policy with a narrow scope.

CRIU has options to handle LSM profiles during restore, such as --lsm-profile for AppArmor or SELinux, along with mount context options. These are CRIU and runtime configurations; not every orchestrator lets the application pass these options directly.

### 4.4. User Namespaces and Privileges in the Init Namespace

A container may run in its own user namespace. UID 0 inside the container does not mean UID 0 on the host. Capabilities held in a nested user namespace do not automatically take effect for resources belonging to the init user namespace.

Some CRIU operations, such as reading map_files of another process or suspending seccomp, may require privileges in the init user namespace. Therefore:

- Identify which user namespace CRIU runs in.
- Verify UID/GID mappings.
- Verify effective/permitted capabilities of the CRIU helper.
- Check ptrace_scope and procfs access permissions.
- Do not assume adding a capability to a Pod suffices if the operation requires privileges in the host namespace.

## 5. Granting Privileges to CRIU Without Expanding Application Privileges

### 5.1. Prefer Non-CRIU Engines When Suitable

If the JDK build provides Warp and the application does not rely on preserving PID/TID values, this can reduce privilege requirements inside the container. According to Azul documentation, Warp does not use CRIU and needs no extra Linux capabilities for checkpoint/restore.

However, check the limits of the specific engine:

- Is the engine available in the JDK build being used?
- Are the operating system and CPU architecture supported?
- Do PID/TID values change after restore?
- Does the application or any library store PID/TID or use them as identity?
- Are checkpoint images compatible across runtime versions?

An engine that does not require CRIU does not exempt the application from filesystem, volume, network, identity, or secret controls.

### 5.2. When Using CRIU Inside a Container

In Docker, Azul documentation instructs adding:

~~~bash
docker run \
  --cap-add=CHECKPOINT_RESTORE \
  --cap-add=SYS_PTRACE \
  --name java-crac \
  my-java-crac-image
~~~

This is a starting configuration for the CRIU engine in Docker according to Azul documentation. It is not guaranteed to suffice for every CRIU feature, especially when checkpointing processes with seccomp filters, mount/cgroup operations, or external resources. Verify the exact kernel and CRIU version before deploying to production.

Docker CLI documentation contains an example using --security-opt=seccomp:unconfined for checkpointing. Understand that this is an example illustrating compatibility, not a recommended security configuration for production. Prefer a specialized seccomp profile and use unconfined only in isolated test environments to pinpoint failure causes.

### 5.3. When CRIU Is Run by the Runtime on the Node

With Kubernetes container checkpointing, kubelet and the container runtime run on the node. In this model:

- Node administrators are responsible for installing CRIU and configuring the runtime.
- Required capabilities are granted to the runtime/helper according to the node deployment setup.
- Application Pods retain standard workload security contexts.
- Callers invoking the kubelet checkpoint API need appropriate authentication/authorization permissions.
- Checkpoint archives must be stored in a protected location on the node.

Do not grant CAP_SYS_PTRACE, CAP_CHECKPOINT_RESTORE, or CAP_SYS_ADMIN to every Pod simply so the node can checkpoint containers. If the platform requires a privileged helper, restrict it by node, service account, API, and allowed operations.

## 6. Security Context Examples for Different Models

### 6.1. Java Application Using Warp or Not Running CRIU Inside the Pod

This is a reference baseline for workloads that do not require CRIU capabilities:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: java-crac-warp
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
    runAsGroup: 10001
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: app
      image: example/java-crac:latest
      args:
        - "-XX:CRaCEngine=warp"
        - "-XX:CRaCCheckpointTo=/var/lib/crac"
        - "-jar"
        - "/opt/app/app.jar"
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop:
            - ALL
      volumeMounts:
        - name: checkpoint
          mountPath: /var/lib/crac
  volumes:
    - name: checkpoint
      persistentVolumeClaim:
        claimName: java-crac-checkpoints
~~~

This is an illustrative configuration. The image must have permissions to read the JAR and write to the checkpoint volume; the volume must be mounted with proper ownership. If the engine or runtime has different requirements, adjust based on documentation for the exact version.

### 6.2. CRIU Running Inside a Dedicated Container

If CRIU actually runs inside a helper container, you can begin testing with dedicated capabilities:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: criu-helper
spec:
  containers:
    - name: helper
      image: example/criu-helper:tested-version
      securityContext:
        runAsUser: 10001
        runAsGroup: 10001
        runAsNonRoot: true
        allowPrivilegeEscalation: false
        capabilities:
          drop:
            - ALL
          add:
            - CHECKPOINT_RESTORE
            - SYS_PTRACE
        seccompProfile:
          type: Localhost
          localhostProfile: crac/criu-helper.json
      volumeMounts:
        - name: checkpoint
          mountPath: /var/lib/crac
  volumes:
    - name: checkpoint
      persistentVolumeClaim:
        claimName: criu-checkpoints
~~~

This is only an experimental configuration for a helper running CRIU inside a container. Verify that capabilities take effect in the right user namespace, CRIU has access to the target process, the seccomp profile permits required syscalls, and AppArmor/SELinux allow the relevant paths. If seccomp suspend or mount/cgroup operations are needed, those two capabilities alone may not be enough.

Do not add SYS_ADMIN or enable privileged: true via trial-and-error until the command runs. If logs indicate a feature requires CAP_SYS_ADMIN in the init user namespace, decide to place that function in a controlled node-side helper, or change engines if appropriate.

### 6.3. Kubernetes Restricted Pod Security

The Restricted level of Pod Security Standards requires seccomp to be RuntimeDefault or Localhost, drops all capabilities, and only permits adding back NET_BIND_SERVICE. Therefore, a Pod running CRIU directly with CHECKPOINT_RESTORE and SYS_PTRACE does not satisfy the default Restricted profile.

If the organization enforces a Restricted policy, run the checkpoint engine on an approved node/helper or create a narrowly scoped exception governed by admission policies and RBAC. Do not lower the protection level of an entire namespace just to let one workload checkpoint.

## 7. Kubernetes Container Checkpointing and Node-Side Privileges

### 7.1. Kubelet Checkpoint API

Kubernetes provides a checkpoint API on the node's kubelet. Requests are sent to a node-local endpoint; kubelet calls the CRI runtime, which invokes the low-level runtime and CRIU. This workflow can require node administrative privileges and client certificates to authenticate against the API.

Because the endpoint lives on kubelet, protect:

- Access to the node-local endpoint and kubelet port.
- Client certificates/keys or corresponding authentication mechanisms.
- RBAC, node administration permissions, and audit logs.
- The checkpoint directory on the node and archive read permissions.
- The workflow for copying checkpoints off the node.

Do not expose the checkpoint API to application users or ordinary service accounts. A checkpoint contains process state and may hold sensitive data in memory.

### 7.2. Pod Capabilities vs. Runtime Capabilities

Distinguish two questions:

1. Which capabilities does the process inside the Pod need to run the application?
2. Which capabilities do kubelet/container runtime/CRIU on the node need to checkpoint the Pod's process?

The two answers can differ. If CRIU runs on the node, adding capabilities to spec.containers[*].securityContext.capabilities may not help at all. Conversely, if CRIU runs inside the container, the runtime must grant privileges to the helper and seccomp/AppArmor/SELinux must permit the corresponding operations.

### 7.3. Cgroups, Mounts, and Namespaces

Container checkpointing may require saving or reconstructing cgroups, mount namespaces, PID namespaces, network namespaces, and external resources. CRIU has options for managing cgroups, mounts, and namespaces, though actual capability depends on the kernel, cgroup v1/v2, the runtime, and node configuration.

Common failure scenarios:

- CRIU cannot mount or access the cgroup hierarchy.
- A mount point in the checkpoint does not exist on the target node.
- An external volume is not mapped correctly on restore.
- The PID namespace or user namespace is incompatible.
- The network namespace changed and old sockets cannot be recovered.
- The checkpoint archive was created on a different kernel/CPU from the restore environment.

Do not resolve mount errors by granting CAP_SYS_ADMIN to a long-running workload. Check whether the runtime can provide a cgroup yard, mount mappings, or external resources through a node-side helper.

## 8. Protecting the Security Context When Restoring Checkpoints

A checkpoint archive does not contain application data alone. CRIU can store process credentials, capability sets, no_new_privs, seccomp filters, and other OS state. Therefore, a checkpoint from an untrusted source must be treated as an artifact capable of carrying process execution state and privileges.

### 8.1. Risk When Destination Security Context Is Not Enforced

On 21-09-2026, CRI-O published advisory CVE-2026-92574/GHSA-pgj4-7h26-2r47: in affected versions, restoring a container from a checkpoint could retain the UID, capabilities, no_new_privs, and seccomp state from the checkpoint instead of enforcing the destination container's security context. This could allow a crafted checkpoint to restore a process with higher privileges than the policy specified by the Kubernetes Pod.

The containerd advisory, CVE-2026-95837/GHSA-p7v4-vr35-mj6f, describes a similar issue in the restore path via CRI CreateContainer: the restored process could retain credentials, capabilities, no_new_privs, and seccomp state from the checkpoint instead of the target security context.

This is a critical reason to restore checkpoints only from trusted sources and keep container runtimes on patched versions. The target Pod manifest or status reported by the control plane does not prove by itself that the actual process is running with the intended UID, capabilities, and seccomp filter.

### 8.2. Patched Versions per November 2026 Advisories

According to currently published advisories:

| Component | Affected Versions | Patched Versions |
|---|---|---|
| CRI-O | <=1.36.5, <=1.35.8, <=1.34.13 | 1.37.0, 1.36.6, 1.35.9, 1.34.14 |
| containerd CRI plugin v2 | >=2.1.0 and <2.2.7; >=2.3.0 and <2.3.4 | 2.2.7, 2.3.4; restore via CreateContainer removed in 2.4.0 |

CRI-O introduced the container_level_enabled configuration to replace the legacy flag; the default value checkpoint_only blocks the affected restore path. The advisory also recommends disabling the restore path if upgrading is not yet possible.

Containerd 2.2.7 and 2.3.4 disable restore via CreateContainer by default. Re-enabling enable_experimental_restore_via_create leaves the risk described in the advisory intact. With containerd, use patched versions and do not re-enable the experimental restore path without full evaluation.

The versions above reflect advisories published in September and October 2026. Before deployment, check vendor advisories and downstream updates for your specific Kubernetes/OpenShift or runtime distribution.

### 8.3. Rules for Protecting Checkpoint Archives

- Restore only checkpoints created by trusted pipelines or trusted nodes.
- Verify source, signatures, digests, and provenance of archives/OCI images.
- Restrict who can upload, annotate, publish, or request checkpoint restores.
- Do not allow untrusted users to create Pods from images containing checkpoints.
- Protect checkpoint directories and registries as sensitive data.
- Encrypt archives at rest/in transit and limit retention periods.
- Upgrade containerd/CRI-O and CRIU according to security advisories.
- After restore, verify the real process in /proc rather than relying solely on the manifest or control plane status.

## 9. Checking Actual Privilege State

When encountering checkpoint errors, collect diagnostics in the exact location where the engine runs. If CRIU runs on the node, inspect the node/helper; if CRIU runs inside a container, inspect that container.

### 9.1. Checking Process Capabilities

On Linux:

~~~bash
grep -E '^(Uid|Gid|CapInh|CapPrm|CapEff|CapBnd|CapAmb|NoNewPrivs|Seccomp):' /proc/self/status
~~~

Key fields:

- CapEff: currently effective capabilities.
- CapPrm: capabilities permitted to be raised to effective.
- CapBnd: bounding set limiting capabilities that can be acquired.
- CapAmb: ambient capabilities preserved across exec under Linux rules.
- NoNewPrivs: state of no_new_privs.
- Seccomp: seccomp mode of the process.

You can use capsh --print or getpcaps <pid> if the tools are installed in the image. Do not just check UID with id; UID 0 inside a user namespace does not mean host-root-equivalent privileges.

### 9.2. Checking Seccomp and LSM

~~~bash
cat /proc/self/status | grep -E '^(Seccomp|NoNewPrivs):'
cat /proc/self/attr/current
~~~

The second command can show the current LSM label, such as an AppArmor profile. For SELinux, inspect audit logs on the node for AVC denials. Tool names and audit-reading capabilities depend on the Linux distribution.

### 9.3. CRIU Preflight

On the exact host/container where CRIU runs, run the check provided by the installed CRIU version. On versions supporting the seccomp suspend feature probe, you can check:

~~~bash
criu check --unprivileged --feature seccomp_suspend
~~~

This checks one specific feature; use the exact option supported by the installed CRIU version. Any non-zero exit status must be read together with stdout/stderr and detailed logs, as it could indicate missing capabilities, missing kernel features, or an incorrect check mode invocation.

Do not treat a passing criu check as proof that every kind of process can be checkpointed. Run a dump/restore test with the same namespaces, seccomp profile, cgroups, volumes, and resources that the production application uses.

## 10. Troubleshooting by Symptom

| Symptom | Possible Cause | How to Investigate |
|---|---|---|
| Operation not permitted when CRIU attaches to process | Missing CAP_SYS_PTRACE, ptrace_scope, or capability in wrong user namespace | Check CapEff, Yama ptrace_scope, and the helper's namespace |
| CRIU reports missing CAP_CHECKPOINT_RESTORE | Older kernel or capability missing from effective/permitted sets | Check kernel >= 5.9, bounding set, and user namespace |
| couldn't suspend seccomp: Operation not permitted | Kernel gate PTRACE_O_SUSPEND_SECCOMP requires CAP_SYS_ADMIN in init user namespace per current CRIU path | Check CRIU/kernel versions and feature probe; consider a node-side helper |
| Checkpoint fails under RuntimeDefault | Runtime seccomp profile blocks a required syscall | Check audit/logs, test a Localhost profile in a test environment |
| Checkpoint succeeds but restore fails on mounts | Mount point, cgroup, or external volume is unmapped | Check namespaces, mount table, cgroup hierarchy, and external resources |
| Cannot read /proc/<pid>/map_files | Insufficient permissions or capability absent from init user namespace | Check CAP_CHECKPOINT_RESTORE in the right namespace and procfs mount |
| SELinux AVC denial | Label or policy disallows access to process/image path | Read audit logs and create a narrowly scoped policy |
| AppArmor DENIED | Profile blocks ptrace, procfs, mounts, or checkpoint directory | Inspect audit logs and adjust the helper's profile |
| Helper has capabilities yet fails when exec'ing CRIU | no_new_privs, setuid/file capabilities, or bounding set prevents privilege gain | Check NoNewPrivs, CapBnd, and how CRIU is installed |
| Container runs locally but Pod is rejected by admission | Restricted Pod Security Standards prohibit CRIU capabilities | Move engine to node/helper or request a narrow exception |
| Checkpoint archive restores with privileges differing from manifest | Runtime restore fails to apply destination security context or has a vulnerability | Check CVE-2026-92574/CVE-2026-95837 and upgrade runtime |
| Restore succeeds but process cannot access volume | UID/GID, fsGroup, SELinux label, or mount permissions differ | Verify owner, label, mount, and actual permissions after restore |

## 11. Secure Implementation Workflow

### Engine Identification Phase

1. Identify the actual JDK vendor, version, and engine.
2. Distinguish JVM CRaC checkpointing from container checkpointing via CRI.
3. Determine whether CRIU runs inside the container or on the node.
4. Confirm the kernel, CRIU, container runtime, low-level runtime, and cgroup version.
5. Identify whether the process has a seccomp filter, network namespace, mount namespace, or external resources.

### Privilege Granting Phase

1. Start from the runtime's default privileges.
2. Grant only CHECKPOINT_RESTORE and SYS_PTRACE to the CRIU helper if needed by the engine.
3. Verify capabilities are effective in the namespace required by the operation.
4. Use a seccomp Localhost profile if RuntimeDefault blocks required syscalls.
5. Verify AppArmor and SELinux independently.
6. Use CAP_SYS_ADMIN only when a specific feature requires it and it is proven by logs/preflight.
7. Never enable privileged or unconfined across an entire workload to solve unexplained errors.

### Checkpoint/Restore Phase

1. Prepare the snapshot storage volume and ownership.
2. Quiesce the application and handle Resource callbacks.
3. Create the checkpoint on the exact target runtime/kernel.
4. Verify the archive, metadata, and CRIU logs.
5. Restore in a compatible environment.
6. Verify actual UID/GID, capabilities, NoNewPrivs, seccomp, and LSM labels.
7. Verify connectivity, volumes, readiness, and business functionality.
8. Publish the checkpoint image only after the pipeline verifies provenance and tests pass.

## 12. Security Context Testing Matrix

| Scenario | What to Verify |
|---|---|
| Warp + RuntimeDefault + non-root | Checkpoint/restore works without adding CRIU capabilities |
| CRIU + RuntimeDefault | Record which syscalls/capabilities are blocked |
| CRIU + Localhost profile | Helper receives only the required syscalls |
| CRIU + CHECKPOINT_RESTORE and SYS_PTRACE | Privileges are effective in the right user namespace |
| Target process has seccomp filter | Kernel/CRIU supports seccomp suspend and filter restore |
| no_new_privs=1 | Helper does not rely on a setuid path |
| AppArmor/SELinux enforcing | No denials outside approved policy |
| Restore under different UID/GID | Volume, file ownership, and process identity are correct |
| Restore untrusted checkpoint | Runtime rejects or pipeline blocks the artifact |
| Patched CRI-O/containerd version | Destination security context is protected per advisories |
| Kubernetes Restricted namespace | Application Pod does not need CRIU capabilities if engine runs node-side |

## 13. Key Principles to Remember

- Identify the engine before granting privileges: CRIU, Warp, and simengine have different requirements.
- OpenJDK CRaC criuengine uses CRIU; inside containers it usually requires CAP_CHECKPOINT_RESTORE and CAP_SYS_PTRACE.
- CAP_CHECKPOINT_RESTORE does not guarantee sufficient privileges for all CRIU features; seccomp suspend and namespaces may have extra requirements.
- Azul's Warp does not use CRIU and needs no extra checkpoint/restore capabilities, but depends on supported builds and platforms.
- simengine only simulates callbacks and does not produce a deployable process image.
- Seccomp, capabilities, no_new_privs, AppArmor, and SELinux are independent control layers.
- Kubernetes RuntimeDefault, Localhost, and Unconfined have different scopes; RuntimeDefault profiles also vary across runtimes.
- Do not use privileged or seccomp unconfined as a default configuration.
- When CRIU runs on the node, node-side privileges should not be granted to every application Pod.
- Checkpoint archives must come from trusted sources and be protected like sensitive data.
- Update containerd/CRI-O according to security advisories and verify the actual process after restore.

## 14. References

- [CRaC — Checkpoint engines](https://crac.org/reference/engines/): distinguishes criuengine, simengine, and vendor engines like Warp.
- [Azul — Running CRaC in a Container](https://docs.azul.com/crac/deployment/docker-container): Docker configuration and capabilities for the CRIU engine.
- [Azul — Anatomy of CRaC Processes](https://docs.azul.com/crac/detailed/anatomy): how the CRIU engine works with processes and PIDs.
- [Azul — CRaC Engines](https://docs.azul.com/crac/usage/crac-engines): Warp and CRIU engines across Azul distributions.
- [OpenJDK CRaC README](https://github.com/openjdk/crac/blob/crac/README.md): CRIU prerequisites and setting permissions on binaries.
- [CRIU documentation](https://github.com/checkpoint-restore/criu/blob/criu-dev/Documentation/criu.txt): non-root mode, capabilities, namespaces, cgroups, and external resources.
- [Linux capabilities manual](https://man7.org/linux/man-pages/man7/capabilities.7.html): definition of CAP_CHECKPOINT_RESTORE and other capabilities.
- [Kubernetes — Configure a Security Context](https://kubernetes.io/docs/tasks/configure-pod-container/security-context/): UID/GID, capabilities, allowPrivilegeEscalation, no_new_privs, and filesystems.
- [Kubernetes — Seccomp and Kubernetes](https://kubernetes.io/docs/reference/node/seccomp/): RuntimeDefault, Localhost, Unconfined, and JSON profiles.
- [Kubernetes — Linux kernel security constraints](https://kubernetes.io/docs/concepts/security/linux-kernel-security-constraints/): seccomp, AppArmor, SELinux, and privileged containers.
- [CRIU — Kubernetes checkpointing](https://criu.org/Kubernetes): kubelet checkpoint API and the path through container runtime, runc, and CRIU.
- [CRI-O GHSA-pgj4-7h26-2r47 / CVE-2026-92574](https://github.com/cri-o/cri-o/security/advisories/GHSA-pgj4-7h26-2r47): restore may ignore destination security context in affected versions.
- [containerd GHSA-p7v4-vr35-mj6f / CVE-2026-95837](https://github.com/advisories/GHSA-p7v4-vr35-mj6f): checkpoint restore via CRI CreateContainer and destination security context.
- [CRIU issue #3244](https://github.com/checkpoint-restore/criu/issues/3244): CAP_SYS_ADMIN requirement of the seccomp-suspend path in kernel/CRIU discussed in October 2026.

Kernel, CRIU, container runtime, and JDK versions evolve over time. Cross-check documentation for the exact versions being deployed, run preflight checks on target nodes, and test both checkpoint and restore before applying a security context to production.
