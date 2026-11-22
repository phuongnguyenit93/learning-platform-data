# Operating system permissions and capabilities required by each mechanism

When practicing CRaC, one of the reasons checkpoint or restore fails is that the process does not have sufficient permissions at the operating system level. The application may run normally, and `org.crac.Resource` callbacks may be registered properly, yet the operation to capture or restore the process state is still rejected by the kernel, container runtime, or security policy.

To grant permissions accurately, you must first identify the checkpoint/restore mechanism being used and the operating system operations that the mechanism needs to perform. The CRaC API and operating system permissions are two different layers: the API helps the application prepare resources; the checkpoint/restore mechanism needs permissions to observe, save, and restore the process state. There is no fixed list of capabilities that works for every JDK, CRIU, kernel, container runtime, and resource type.

## 1. Distinguishing application permissions from checkpoint/restore permissions

In a Java deployment with CRaC, you may encounter the following permission layers:

| Permission layer | What does it control? | Examples |
|---|---|---|
| Process user and group | The identity used by the application and callbacks | UID/GID running the JVM, permission to read configuration, permission to write to the checkpoint directory |
| File and directory permissions (DAC) | Who is allowed to read, write, execute, or access a path | Owner/mode of the checkpoint directory, access permissions for configuration files |
| Linux capabilities | Privileged operations separated from traditional root privileges | Inspecting processes, manipulating namespaces, configuring network namespaces |
| Namespaces and cgroups | The scope of processes, mounts, network, IPC, and resources visible to the process | PID namespace, mount namespace, cgroup v2 |
| Additional security policies | Actions restricted even when the UID or capabilities appear sufficient | seccomp, SELinux, AppArmor, Yama ptrace policy |

The point to remember is that permission to create checkpoint files does not equate to permission to capture a process. Conversely, a process with checkpoint permission can still fail if it cannot write the image to the target directory. Check each layer separately.

### The CRaC API does not automatically grant root privileges

The application uses `org.crac.Core`, `Context`, and `Resource` to register callbacks such as `beforeCheckpoint` and `afterRestore`. These callbacks run within the application's context. Calling the Java API itself does not automatically grant `CAP_SYS_ADMIN`, `CAP_SYS_PTRACE`, or operating system administrative privileges.

For CRaC distributions on Linux that use CRIU to dump/restore processes, CRIU and the kernel perform the operating-system-level operations. The required permissions depend on how CRIU is run, the process being captured, namespace types, open resources, the kernel, and the security configuration. Another distribution or platform may package this mechanism differently; read the requirements of the exact runtime being used.

## 2. What are Linux capabilities?

Traditional Linux has a model distinguishing regular users from root. Root generally has permission to perform many administrative operations. Linux capabilities split a portion of special privileges into smaller groups, so that a process can be granted certain necessary operations without having to run entirely as root.

A capability can reside in different permission sets of a process:

- **Permitted:** the set of privileges that the process is allowed to activate.
- **Effective:** the set of privileges currently in effect when the kernel checks an operation.
- **Inheritable:** the set of privileges that can participate in inheritance when executing another program.
- **Bounding:** the upper limit on capabilities that a process can acquire via `execve`.
- **Ambient:** a set of privileges that can be preserved across certain `execve` calls for programs without special file capabilities.

Therefore, merely seeing a capability name in a container configuration is not enough to conclude that the operation will succeed. You need to check the process's actual permissions, how the runtime applies capabilities, the current namespaces, and other security policies.

### Capabilities that may be relevant

The table below describes capabilities commonly examined in certain CRIU mechanisms on Linux. This is a map for investigation, not a list to grant all at once.

| Capability | Mechanism or operation that may be involved | Notes in practice |
|---|---|---|
| `CAP_CHECKPOINT_RESTORE` | Certain operations specific to checkpoint/restore, such as setting PID in certain cases, reading certain process information via `/proc` | Added since Linux 5.9. Does not replace all permissions that CRIU may need. |
| `CAP_SYS_PTRACE` | Inspecting or accessing the state of another process via the ptrace mechanism | Also depends on UID relationship, Yama, namespaces, and security policies. |
| `CAP_SYS_ADMIN` | Certain broad administrative operations such as mounting or namespace operations in specific configurations | Very broad; do not grant out of habit. Identify the exact operation that requires it. |
| `CAP_NET_ADMIN` | Configuring interfaces, routes, or network components in a network namespace | Only consider when the restore process actually manages network configuration. |
| `CAP_SYS_RESOURCE` | Certain operations that exceed resource limits or restore process limits | Check specific limits; do not grant if you only need to adjust a valid ulimit configuration. |
| `CAP_SETUID`, `CAP_SETGID` | Switching user/group identity in certain restore workflows | Must match the UID/GID mapping and the isolation model of the environment. |
| `CAP_DAC_OVERRIDE`, `CAP_DAC_READ_SEARCH` | Bypassing part of normal file access permission checks | Usually you should fix the owner, group, mode, or mount before considering bypass permissions. |
| `CAP_MKNOD` | Creating device nodes in cases where the mechanism needs to restore this file type | Not a default requirement for every Java application. |

`CAP_CHECKPOINT_RESTORE` is a specialized capability, but its name does not mean that simply granting this capability allows CRIU to work. An operation may still require ptrace, mount, network, cgroup, or file access permissions. Similarly, if a capability is present in the container but restricted by seccomp, LSM, or namespaces, the operation can still fail.

### Root in a container is not necessarily root on the host

A container can run UID 0 inside while being mapped to an unprivileged UID on the host. When user namespaces or user namespace remapping are enabled, the process's capabilities are evaluated within the corresponding user namespace. A capability in a child namespace does not automatically allow administering host resources.

This explains why `id` inside a container may show `uid=0(root)`, yet CRIU still cannot access a host process, mount a host filesystem, or modify resources outside the container's namespace.

## 3. Identifying permissions by operating system mechanism

Instead of asking broadly “Which capabilities does CRaC need?”, break down the checkpoint/restore operation into the mechanisms it actually uses.

### 3.1. Observing and freezing process state

To dump a process, the checkpoint tool may need to inspect memory maps, threads, process state, and file descriptors. If the tool operates on another process, ptrace permissions and ptrace control policies may apply.

Factors to check:

- Whether the JVM and the checkpoint tool run as the same user.
- Whether the target process is in a PID namespace visible to the tool.
- Whether the ptrace capability is in the effective set and in the right user namespace.
- Whether the kernel has Yama enabled; whether the `ptrace_scope` value restricts the relationship between the tracer and target processes.
- Whether seccomp or an LSM blocks the syscall or process access action.

Do not disable system-wide ptrace controls just to make a lab exercise work. Narrow the process scope and grant permissions to the specific tool, container, or test environment according to the machine's policy.

### 3.2. PID, user, and other namespaces

Checkpoint may have to restore processes in their corresponding namespaces or set certain identity information. These operations are affected by the kernel, namespace types, and user namespace configuration.

Determine:

- Whether the checkpoint tool can see the JVM's PID.
- Whether the PID namespace is preserved or recreated in a way supported by the runtime.
- Whether the process's UID/GID has a valid mapping in the target user namespace.
- Whether the runtime allows the required namespace operations.
- Whether the restored process is granted the right identity and file access permissions after restoration.

Some namespace operations require administrative privileges in the corresponding namespace; others may be supported via user namespaces. Do not assume that `CAP_SYS_ADMIN` inside a container always takes effect on the host.

### 3.3. Mount namespace and filesystem

CRIU may need to recreate or check mounts that the process depends on. Mount permissions depend on the filesystem type, mount namespace, user namespace, kernel, and how the host permits operations. Bind mounts, special filesystems, or host-owned mounts may have their own restrictions.

In addition to mount permissions, the directory storing the checkpoint must meet standard requirements:

- The user running the checkpoint creation process has write permission and can traverse all parent directories.
- The user running restore has read permission on the checkpoint image and auxiliary files.
- Disk space and quota are sufficient for the entire image plus temporary files.
- The mount containing the checkpoint image has behavior compatible with the runtime; check options such as read-only, `noexec`, or mount security policies when related errors occur.
- The owner, group, mode, and SELinux labels of the directory/files allow the right process to access them.
- Paths referenced in the image still exist and are meaningful in the restore environment.

For example, if the JVM runs with UID `10001` but the directory `/var/lib/myapp/checkpoint` is owned by `root:root` with mode `0700`, the JVM cannot write the checkpoint itself. You can prepare the directory with the appropriate owner/group during the image build or volume initialization step, instead of granting `CAP_DAC_OVERRIDE` to the application.

A checkpoint may contain the heap, configuration, tokens, or sensitive data at the time of capture. Restrict read permissions, protect the storage location and transfer path of checkpoint images, set retention/deletion policies, and avoid putting images into public artifacts.

### 3.4. Network namespace and connections

If the checkpoint/restore workflow has to restore a network namespace or configure interfaces, routes, or firewalls, those operations may require `CAP_NET_ADMIN` in the appropriate network namespace. If the application closes sockets and re-establishes connections in `afterRestore`, the permission requirements can differ significantly from restoring sockets in place.

Not every socket can be safely resumed after restore. Connections to a database, broker, HTTP service, or DNS may have expired, been closed by the peer, or had their addresses changed. In a Java application, the common practice is to close resources before checkpoint and reconnect after restore via `Resource` callbacks. In that case, grant network permissions according to the application's normal needs; do not grant `CAP_NET_ADMIN` just because the application opens TCP connections.

### 3.5. Cgroups and resource limits

Cgroups limit and account for the resources of a group of processes. Container environments typically only allow a container to manage a delegated cgroup subtree, not write arbitrarily to the entire host cgroup tree.

When checkpoint/restore involves the freezer, cgroups, or resource limits, check:

- Whether the system uses cgroup v1 or v2.
- Whether the runtime supports checkpoint/restore operations on that cgroup version.
- Whether the tool has permission to access the right cgroup and delegated subtree.
- Whether CPU, memory, PID limits, and other limits are sufficient for both the dump and restore phases.
- Whether, after restore, the process resides in the target cgroup with the expected limits.

Do not grant write permission to all of `/sys/fs/cgroup` for the application just to bypass a permission error. If the platform does not delegate the needed cgroup, adjust the container runtime configuration or ask an administrator to prepare an appropriate test environment.

### 3.6. File descriptors, devices, and IPC

A Java process may hold files, pipes, Unix domain sockets, shared memory, semaphores, devices, or native resources created by libraries. Some types can be handled by CRIU under certain conditions; some need to be closed and recreated; some are not supported in the configuration being used.

Do not assume that keeping a Java object means the kernel-level handle is still usable. Inventory the application's resources and clearly identify which ones:

1. Can be kept across a checkpoint according to the runtime documentation.
2. Must be closed in `beforeCheckpoint` and reopened in `afterRestore`.
3. Must be drained or have their work completed before checkpoint.
4. Cannot be supported in the current deployment environment and require a design change.

Permissions to create device nodes or access devices should only be considered if the application actually uses those devices. A typical Spring Boot service should not receive device-related capabilities copied from another workload's sample configuration.

## 4. Security layers that can block operations even when capabilities are granted

Linux capabilities are only part of the authorization decision. When investigating errors, check these additional layers as well.

| Security layer | Possible impact | How to check |
|---|---|---|
| seccomp | Blocks syscalls that CRIU or the runtime needs to invoke | Check the container's seccomp profile and runtime logs |
| SELinux | Denies access to files, processes, or kernel operations based on security labels | Check AVC denials and file/process labels |
| AppArmor | Restricts paths, capabilities, or process actions | Check the attached profile and denial logs |
| Yama ptrace | Restricts which processes can attach to or inspect another process | Check `ptrace_scope` and the tracer/target relationship |
| User namespace | Restricts the scope of UID/GID and capabilities | Check mappings and the namespace the process is in |
| Capability bounding set | Removes capabilities from the process's maximum privilege set | Check container/systemd configuration and `/proc` |
| No-new-privileges | Prevents a process from gaining additional privileges through certain `execve` calls | Check how the checkpoint tool is launched and what capabilities are already present |

For example, a container configured with `cap_add` will still fail if the seccomp profile blocks a required syscall. Similarly, a checkpoint file may have a writable mode, yet SELinux does not allow the JVM's domain to write to that path. Find the exact layer denying the operation through logs and kernel messages instead of disabling all security policies one by one.

## 5. Configuring containers following the principle of least privilege

When running Java in Docker or Kubernetes, process permissions come from multiple sources: user/group in the image, capabilities granted by the runtime, namespaces, seccomp, LSM, mounts, and cgroups. `privileged: true` usually expands permissions vastly and significantly reduces container isolation.

An application configuration can start with an empty capability list, a non-root user, and an explicitly permitted checkpoint directory:

```yaml
services:
  crac-app:
    image: my-java-app:latest
    user: "10001:10001"
    volumes:
      - ./checkpoint:/var/lib/myapp/checkpoint
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true
    # Only add capabilities after verifying the exact CRIU mechanism,
    # kernel, runtime, and security policy of the target environment.
    # cap_add:
    #   - CHECKPOINT_RESTORE
    #   - SYS_PTRACE
```

This is a starting point for designing permissions, not a configuration guaranteed to make checkpoint/restore run. For some mechanisms, the container will need additional capabilities or policies; the example above intentionally does not guess a full set of permissions for every environment. If `SYS_ADMIN` is needed, identify the specific operation, namespace scope, and the possibility of replacing it with a lower-privilege design before adding it.

In Kubernetes, `runAsUser`, `runAsGroup`, `allowPrivilegeEscalation`, `capabilities`, `seccompProfile`, and Pod Security policies together determine whether it can work. Environments enforcing Pod Security Standards at the Restricted level typically do not allow arbitrarily adding capabilities. If CRIU needs permissions beyond those of normal workloads, prepare a dedicated node or lab environment with an administrator-approved configuration, rather than relaxing policies for the entire namespace.

### Rootless and rootful

**Rootful checkpoint/restore** typically runs the tool with higher administrative privileges to operate on processes and system resources. This approach may be easier to set up in an administrator-controlled lab, but you must limit the scope of the host, data, and workloads allowed to be captured.

**Rootless checkpoint/restore** runs under a regular user, usually relying on user namespaces and supporting kernel features. It can reduce the blast radius on the host, but not every type of namespace, mount, network, device, or process is supported in the same way as rootful. Success depends on the kernel, CRIU, UID/GID mapping, and the features the application uses.

Do not conclude that rootless never needs capabilities, or that rootful must always run the entire application as root. Separate the user running the JVM, the user running the checkpoint tool, and the administrative permissions needed for each operation. When the platform allows, a narrowly scoped helper can perform privileged operations instead of granting all those permissions to the long-lived application process.

## 6. Permissions when running under systemd

If the JVM runs as a service on a Linux host, systemd can restrict permissions through unit options:

- `User=` and `Group=` define the process identity.
- `CapabilityBoundingSet=` limits the maximum capabilities.
- `AmbientCapabilities=` can pass certain capabilities to the executed process.
- `NoNewPrivileges=` prevents privilege escalation via `execve` through the mechanisms controlled by this option.
- `RestrictNamespaces=` limits the types of namespaces that can be created.
- `SystemCallFilter=` restricts syscalls.
- `PrivateUsers=`, `PrivateNetwork=`, `ProtectProc=`, and other hardening options change what the service can see or access.

Hardening options can prevent CRIU from performing necessary operations even when capabilities are declared. When a service is protected by systemd, inspect the entire effective unit and its drop-ins; do not look only at a base unit file and ignore overrides. Capability configuration in the unit also needs to be checked alongside user namespaces, LSM, and host policies.

## 7. Process for determining minimal permissions in a lab environment

Follow a repeatable sequence of checks to know exactly which layer is denying the operation.

### Step 1: Record the platform

Collect the JDK/CRaC version, CRIU if present, kernel, CPU architecture, container runtime, Docker/Kubernetes or systemd, and cgroup type. Checkpoints should only be created and restored in an environment combination supported by the runtime.

```bash
uname -a
id
java -version
criu --version
```

If the `criu` command does not exist, the runtime may have packaged the mechanism differently or the tool may not be installed yet. Do not immediately conclude that the CRaC API does not work; first determine how the JDK distribution performs checkpointing.

### Step 2: Check the actual identity and capabilities

```bash
id
grep -E '^(Uid|Gid|CapInh|CapPrm|CapEff|CapBnd|CapAmb):' /proc/self/status
```

If the `capsh` tool is available, you can use `capsh --print` to read the interpretation of the capability sets. For another process, `getpcaps <PID>` can be useful if the tool is installed and the current user is allowed to access that process.

Compare the output against the container or systemd configuration. A capability declared in a manifest but not appearing in the process's effective set has not necessarily been granted successfully.

### Step 3: Check CRIU and kernel capabilities

For environments using CRIU, CRIU's check command can detect certain kernel features or required permissions:

```bash
criu check
```

Read the entire output, especially unsupported features and permission denied messages. This command is a baseline check and does not replace testing dump and restore with the actual application. An application with sockets, mounts, or special devices can still fail even if `criu check` succeeds.

### Step 4: Check paths and file policies

```bash
namei -l /var/lib/myapp/checkpoint
stat /var/lib/myapp/checkpoint
findmnt /var/lib/myapp/checkpoint
```

Check owner, group, mode, mount options, disk space, quota, and security labels if the system uses SELinux. Ensure both the user creating the image and the user restoring it can access the necessary files. Avoid granting DAC bypass permissions just to mask an owner or mount error.

### Step 5: Test each mechanism with minimal permissions

In a dedicated lab environment, perform dump and restore with a simple sample application. Start with basic permissions; if it fails, obtain the error message from CRIU, the container runtime, the kernel, or the LSM. Add the exact permission or adjust the exact policy identified as the cause, then re-run the test.

Do not add multiple capabilities and disable seccomp/SELinux/AppArmor all at once in a single attempt. If the operation succeeds, you will not know which change was actually necessary. Record the minimal permissions and re-verify from a newly created container/service to avoid relying on manual state from the lab session.

### Step 6: Verify restore and the application after restore

A successful checkpoint only confirms the dump phase. You need to restore the process in the target environment, check `afterRestore`, confirm that databases/brokers/clients reconnect, and only transition readiness to passing after essential resources are working. Check application and OS logs to distinguish restore errors from resource re-initialization errors.

## 8. Quick diagnostic table

| Symptom | Layer to check first | Investigation direction |
|---|---|---|
| `Permission denied` when writing image | DAC, owner/mode, mount, SELinux/AppArmor | Check path, UID/GID, file labels, and LSM logs |
| CRIU cannot inspect the JVM | ptrace, UID, PID namespace, Yama, seccomp | Verify target process, effective capabilities, and ptrace policy |
| Cannot create or restore namespace | User namespace, capability in namespace, seccomp | Identify the namespace type and denied syscall |
| Error when restoring mount | Mount namespace, filesystem, mount permissions, host paths | Check mount table, bind mounts, and runtime support |
| Network namespace or interface error | `CAP_NET_ADMIN`, network namespace, network policy | Determine whether network configuration actually needs restoring or sockets should reconnect |
| Cannot manipulate cgroup | Cgroup v1/v2, subtree delegation, runtime | Check target cgroup and write permission on the right subtree |
| `criu check` passes but application restore fails | File descriptors, sockets, devices, native resources, callbacks | Inventory application resources and read detailed restore logs |
| Capability declared but still denied | Bounding/effective set, namespace, seccomp, LSM | Check actual process permissions and which policy layer is blocking |

A single error message may not point to the root cause. Correlate the error timestamp with CRIU logs, container runtime logs, SELinux/AppArmor audit logs, and kernel logs that the administrator has access to. Do not enable broad debug or audit logging in production without evaluating storage impact and sensitive information in logs.

## 9. Checklist before putting the lab configuration into use

- [ ] Identified the exact CRaC/JDK distribution and actual checkpoint/restore mechanism.
- [ ] Recorded kernel, architecture, CRIU, container runtime, and cgroup version.
- [ ] JVM runs with a UID/GID that has the minimum necessary permissions.
- [ ] Checkpoint directory has appropriate owner, mode, mount, quota, and security labels.
- [ ] Capabilities are granted per operation proven to be necessary.
- [ ] `CAP_SYS_ADMIN` or `privileged: true` is not granted as a default solution.
- [ ] PID/user/mount/network namespaces and UID/GID mappings match the restore mechanism.
- [ ] seccomp, SELinux, AppArmor, Yama, and capability bounding set have been checked.
- [ ] Cgroups are delegated with the proper scope if the mechanism needs to manipulate cgroups.
- [ ] Native resources, sockets, file descriptors, and devices have a plan to be kept or recreated.
- [ ] Checkpoints are protected because they may contain in-memory data and secrets.
- [ ] Tested both dump and restore using the exact user, container profile, and systemd unit that will be used in deployment.
- [ ] Saved the minimal permission configuration along with verification results so the lab can be reproduced.

## 10. Conclusion

Operating system permissions for CRaC must be determined from the specific checkpoint/restore mechanism. Permission to write to the checkpoint directory, permission to inspect processes, and permissions to manipulate namespaces, mounts, networks, and cgroups are distinct requirements. Linux capabilities help break down certain special privileges, but actual effectiveness also depends on user namespaces, capability sets, seccomp, SELinux, AppArmor, Yama, and container or systemd configuration.

Start from a low-privilege identity, check kernel/CRIU capabilities, test dump and restore in a lab environment, and then add only the permissions proven necessary. This approach keeps the lab configuration explainable, reproducible, and able to maintain the application's security boundaries.
