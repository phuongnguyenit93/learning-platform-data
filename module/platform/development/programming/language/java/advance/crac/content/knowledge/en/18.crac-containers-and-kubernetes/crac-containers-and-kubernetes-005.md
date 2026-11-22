# PID Namespaces and Identity Collisions When Using CRIU

CRaC helps restore the state of a Java process, while CRIU (Checkpoint/Restore In Userspace) provides the process checkpoint and restore mechanism on Linux. When an application runs inside a container, a critical factor determining restore feasibility is the **PID namespace**: the same process can have multiple different PIDs depending on which namespace observes it. Therefore, a PID recorded in a checkpoint cannot simply be interpreted as the host PID, and two processes having the same PID number do not necessarily conflict.

A collision occurs when the runtime attempts to restore a process into a PID namespace where the required PID number is already occupied by another process, or when the process is restored into the wrong namespace relative to the process tree structure and container environment. Related issues also include PID 1, the namespace init process, stale PID files, PID reuse, which namespace `/proc` is mounted from, and external components holding references to the old process.

For reliable container checkpoint/restore, you must understand PID namespace boundaries, create the right target namespace before restore, coordinate with the container runtime, and never use numeric PIDs as durable identifiers across a process lifecycle.

## 1. What Is a PID Namespace?

A PID namespace is a Linux namespace that isolates the process ID space. A process inside a PID namespace can see processes belonging to that namespace and its child namespaces according to kernel rules, but cannot see processes in sibling or outer namespaces.

A process can have multiple PIDs simultaneously: one PID in its own namespace and another PID in each ancestor namespace. When calling `getpid()`, the process receives the PID within the namespace it is running in. A process on the host may observe a different PID for the exact same process.

Illustrative example:

```text
Host PID namespace
  PID 1     systemd
  PID 4200  container init
      |
      +-- Container PID namespace A
            PID 1   init/pause process
            PID 7   java application
            PID 9   helper process

  PID 5100  another process on host
      |
      +-- Container PID namespace B
            PID 1   init process
            PID 7   worker process
```

In the example, PID `7` appears in both namespace A and B without conflict because they belong to two independent PID spaces. The host sees the two processes as PID `4200` and `5100` (along with separate host PIDs for child processes as needed), whereas inside each container the process can see PID `7`.

This leads to an essential principle: **a PID is only meaningful together with its PID namespace**. A standalone PID is not sufficient to uniquely identify a process across the entire system.

## 2. Nested Namespaces and PID Mapping

PID namespaces are hierarchical. When one namespace is created inside another, a process in the child namespace still receives PIDs assigned in ancestor namespaces. A process in an ancestor namespace can observe the child process using its ancestor-namespace PID; the child process cannot see processes in ancestor namespaces merely by using its internal PID.

For example, a single process may be observed as follows:

| Perspective | PID of the Same Process |
| --- | ---: |
| Container PID namespace | 7 |
| Parent PID namespace | 4207 |
| Host PID namespace | 4207 |

The numbers above are illustrative only. Actual PIDs are assigned by the kernel and can differ on each launch/restore.

On Linux, `/proc/<pid>/status` may display the `NSpid` field, showing the process's PIDs across PID namespace levels visible from that procfs mount. Example:

```text
Name:   java
Pid:    4207
PPid:   4199
NSpid:  4207 7
```

If procfs is mounted from the host namespace, `NSpid` can display PIDs across ancestor and child namespaces. The exact output depends on where procfs is mounted and the namespace hierarchy. Do not assume every container shows the same number of columns or the same perspective.

The `Pid`, `PPid`, `NSpid` fields and the namespace inode help determine from where a process is being observed. They are far more useful than merely comparing raw PID numbers between `ps` output on the host and inside the container.

## 3. PID Namespaces and Process Identity Differ

Process identity consists of more than just a PID. For containers and CRIU, pay attention to at least:

- The PID within each PID namespace.
- The PID namespace to which the process belongs.
- Parent/child relationships and the process tree.
- Associated user, mount, network, IPC, UTS, and cgroup namespaces.
- Cgroup membership, capabilities, and security profile.
- File descriptors, sockets, mounts, and other kernel resources.

Two processes can share the same PID number while belonging to different namespaces. Conversely, two processes in the same PID namespace cannot simultaneously occupy the same PID. If CRIU needs to restore a process tree with specific PIDs into a namespace where a process already uses those numbers, the kernel cannot reassign an occupied ID and restore may fail.

A PID namespace is also a kernel object, not a string name or a PID number. You can inspect the namespace handle via `/proc/<pid>/ns/pid`; the symlink value typically contains an inode identifier, such as `pid:[4026533001]`. This inode lets you compare whether two live processes share the same namespace. It is not a stable identifier to store and expect the post-restore namespace to have the same inode.

## 4. Why Must CRIU Restore the Right PID Namespace?

CRIU stores the information needed to reconstruct the process tree and associated namespaces. On restore, the runtime must set up an appropriate namespace environment and then restore processes according to the required structure and PIDs in the target namespace.

If the target namespace is wrong, the following situations can occur:

1. The process is restored into the host PID namespace instead of the container's isolated PID namespace.
2. The process tree is restored into a namespace where other processes already occupy PIDs required by the checkpoint image.
3. The target PID namespace already exists, but its init process or background processes are no longer in the right state.
4. The process is restored in a new namespace, yet `/proc` remains mounted for another namespace, causing the application or monitoring tools to observe unexpected PIDs.
5. The container runtime creates namespaces or cgroups that do not match the metadata CRIU needs to reconstruct the process tree.

CRIU may need to create a new PID namespace for the restored process tree. Depending on the version and integration, CRIU has a `--pidns` option to request restoring into a new PID namespace; the container runtime typically orchestrates options and namespaces on behalf of the operator. Do not manually append CRIU flags to a runtime command if the runtime does not support them or already manages namespaces itself. Check `criu restore --help`, CRIU documentation, and your container runtime's documentation.

A notable Linux subtlety: `setns()` on a PID namespace affects only child processes created afterward; it does not move the calling process itself into the new namespace. Therefore, the runtime must create/enter the namespace at the right moment before launching the process tree to be restored.

## 5. PID Collisions When Restoring into a Namespace with Existing Processes

Suppose a checkpoint saves a process tree with internal PIDs `1`, `7`, and `9` in a PID namespace. If restored into a namespace where a process with PID `7` already exists, the kernel cannot create a new process with that PID in the same namespace. CRIU may fail while setting up PIDs or reconstructing the process tree.

```text
Checkpoint image requires:       Current target PID namespace:

PID 1  init                       PID 1  existing init
PID 7  java                       PID 7  unrelated process
PID 9  helper                     PID 12 another process
          |                                  |
          +---------------+------------------+
                          |
                          v
             Cannot allocate PID 7 again
```

This is a real collision because both processes belong to the same namespace. It differs from a process in namespace A and a process in namespace B both having PID `7`, which is completely valid.

Ways to reduce risk:

- Create a new, isolated PID namespace for the process tree to be restored when supported by the architecture/runtime.
- Ensure the target namespace contains no processes outside the checkpoint image occupying needed PIDs.
- Do not restore multiple copies of the same checkpoint concurrently into a shared namespace.
- Let the container runtime own creating the sandbox, namespaces, and process tree rather than assembling partial namespaces outside the runtime.
- If using a shared PID namespace across multiple containers/processes, explicitly map out the entire process tree and restore order.

Do not attempt to resolve collisions by manually editing PIDs in checkpoint files. PIDs are embedded in the process tree structure and kernel references; altering a few numbers can break parent/child relationships, process groups, sessions, or associated resources.

## 6. The Special Role of PID 1

The first process in a PID namespace receives PID `1` in that namespace. This process acts as the namespace init and carries critical responsibilities for signal handling, adopting orphan processes, and reaping zombies.

PID 1 has special semantics:

- When orphaned child processes are reparented to init, init must reap their exit statuses via `wait()`/`waitpid()` to prevent zombie accumulation.
- Default kernel signal handling differs for namespace init; the init program must install appropriate signal handlers.
- When the init process of a PID namespace terminates, the kernel sends `SIGKILL` to all remaining processes in that namespace, and the namespace cannot continue operating normally.
- New processes cannot normally be created in that namespace once its init has died.

Inside a container, PID 1 may be the Java application or an init/supervisor such as `tini` or a pause process depending on configuration. If init is a separate process, Java has a different PID. During checkpoint/restore, determine which process is namespace init and which process tree is managed by CRIU.

Do not assume Java is always PID 1. In Kubernetes with `shareProcessNamespace: true`, containers in a Pod share a PID namespace; the sandbox/pause process may hold PID 1 while Java in the application container has a different PID. In that case, restoring an individual container requires coordination with the sandbox and sibling containers in the same namespace.

## 7. PID Namespace Lifetime Follows Namespace Init

A PID namespace is a kernel object. It stays alive as long as processes belong to it or valid namespace references remain held. However, termination of the PID 1 init process has severe consequences: all other processes in the namespace are terminated, and the namespace can no longer serve as a normal execution environment for new processes.

This matters when structuring restores:

- Do not let a supervisor/container runtime accidentally kill namespace init before CRIU finishes.
- Do not reuse a namespace whose old init has terminated as a valid target namespace.
- Properly create a new namespace when restoring an entire process tree.
- Ensure the init process is restored or created according to the model expected by the runtime.
- Check whether auxiliary processes are sharing the PID namespace with the application.

Seeing a namespace inode still present in `/proc` does not prove the internal process tree is in a restorable state. Check init, process membership, and runtime status as well.

## 8. PID Reuse and Stale PID Files

The kernel can reuse a PID number after the previous process terminates. For example, an old Java process had PID `4207`; after it exits, another process may be assigned PID `4207`. If a script or application blindly reads `/run/myapp.pid` and sends a signal to that PID, it may inadvertently hit the new process.

Checkpoint/restore complicates this further:

- The container PID may match the pre-checkpoint PID, yet the post-restore host PID may differ.
- A PID file stored in the heap or filesystem may still contain the old host PID.
- An external supervisor may retain the old PID and assume the process has died.
- The old PID may already have been reused for an unrelated process.
- A PID in one namespace can numerically match a different process's PID in another namespace.

Do not treat a PID file as the source of truth after restore if it contains a PID written before the checkpoint. Update the PID file with the current PID in the appropriate namespace, or let the container runtime/supervisor manage process identity.

For Java applications, `ProcessHandle.current().pid()` returns the PID visible to the process inside its current PID namespace. This value may differ from the host PID. Do not write that value to a host control system and assume the host can use it directly to send signals.

When verifying whether a PID still points to the intended process, check start time, executable, command line, and PID namespace in addition to the PID. On Linux, native programs can use `pidfd` to hold a reference to process identity without risking confusion from PID reuse; a pidfd is a kernel handle, not a PID number that can be durably persisted across a checkpoint and arbitrarily reused after restore.

## 9. PID Files, Lock Files, and Unix Domain Sockets

Some servers write their PID to a file to prevent multiple instances from running or to help stop scripts locate the service. This file may linger in the container filesystem after an old process terminates or after a checkpoint is restored.

Common issues:

- A stale PID file points to a host PID that no longer belongs to the Java process.
- The PID file contains a container PID while the script runs on the host.
- A lock file remains even though the lock-holding process died; or the new process sees the file without verifying ownership.
- A Unix domain socket path still has a leftover socket file while the listener is gone.
- A supervisor checks the PID in a different namespace and mistakenly concludes the process does not exist.

Manage these files as resources requiring reconciliation:

1. Before checkpoint, stop listeners and release locks/sockets using application APIs.
2. Do not rely on PID files as the sole locking mechanism; use file locks/kernel locks or a registry with proper ownership checks.
3. After restore, determine the current PID from the process and new namespace.
4. Remove/recreate old PID files or socket paths only after verifying no live process is using them.
5. Update supervisor/health registrations to reflect the new identity.

Do not delete lock files based solely on file age. A file may still be in use by an active process; conversely, an old file does not guarantee a kernel lock is still held.

## 10. `/proc` Must Reflect the Correct PID Namespace

`/proc` is procfs, and how it is mounted dictates the view of processes. If procfs was mounted in a different PID namespace from that of the observing process, commands like `ps`, `top`, or code reading `/proc` may show a process list different from what the application expects.

In containers, the runtime typically mounts a procfs matching the container's PID namespace. On restore, preserve or recreate the mount namespace and procfs per runtime requirements. Do not mount a host procfs into a container and assume internal PIDs remain consistent.

Observable indicators:

- `getpid()` returns the PID in the current namespace.
- `/proc/self/status` provides `Pid`, `PPid`, and possibly `NSpid`.
- `/proc/<pid>/ns/pid` reveals the namespace handle of the observed process.
- Which namespace `/proc` was mounted in can alter the visible list of PIDs.

After restore, inspect from both the host and inside the container. Compare the PID namespace inode, `NSpid`, parent PID, and process list to confirm the mapping.

## 11. PID Namespaces in Container Runtimes

The container runtime typically creates namespaces and cgroups before launching the container. At checkpoint time, the runtime must coordinate CRIU with the initial container configuration. At restore time, the runtime must reconstruct a compatible environment, including the PID namespace, mount namespace, cgroups, and required resources.

Do not run CRIU directly against a host PID without knowing which namespace the process belongs to. When dumping a container process from the host, determine the exact host PID of the container init or target process as required by CRIU/the runtime—never take an internal PID from `ps` inside the container and pass it directly to a host command.

Information to retain in deployment metadata:

- Container ID and sandbox/pod identity.
- Host PID of container init at the time of the operation, solely to trace that specific attempt.
- PID namespace inode and namespace topology at dump time, solely for diagnostics.
- Runtime `--pid`/PID namespace mode configuration.
- Process tree and init process inside the container.
- Cgroup path, mount namespace, network namespace, and runtime version.
- Kernel, CRIU, and container runtime versions.

Host PIDs and namespace inodes are ephemeral information, not durable identities for subsequent restores. Upon restore, the runtime may assign a new host PID and create a new namespace; what matters is that the structure inside the target namespace matches the image.

## 12. Kubernetes and Pod PID Namespaces

In Kubernetes, containers within a Pod typically share a network namespace, whereas the PID namespace is not always shared by default. With `shareProcessNamespace: true`, containers in the Pod can see each other's processes in a shared PID namespace.

Example configuration:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: java-worker
spec:
  shareProcessNamespace: true
  containers:
    - name: app
      image: example/java-worker:1.0
    - name: sidecar
      image: example/diagnostics:1.0
```

When sharing a PID namespace:

- Processes in the app and sidecar containers reside in the same PID space.
- Both containers can observe and send signals to each other's processes depending on privileges.
- PID 1 may be the Pod's sandbox/pause process rather than Java.
- Restoring one container while other Pod processes remain alive can cause collisions if the process tree's required PIDs are already taken.
- Checkpoint/restore must be orchestrated at the runtime/Pod level per supported capabilities; each container cannot be treated as an independent PID namespace.

If PID namespace sharing is disabled, each container gets its own PID namespace per the runtime configuration. Two containers can then both have PID `1` or `7` without conflict.

The Kubernetes checkpoint API, if available in your version/feature set, still depends on the container runtime and CRIU; it does not mean Kubernetes can arbitrarily restore a process tree into any Pod. Check documentation for the exact Kubernetes, kubelet, container runtime, and CRIU versions. Do not assume a container checkpoint API automatically handles all sidecars or processes in a shared PID namespace.

## 13. Shared PID Namespaces and Sidecars

When a Pod shares its PID namespace, a sidecar can monitor or signal the application. This helps with debugging but complicates checkpoint/restore:

- A single container's checkpoint image may contain only part of the process tree in the shared namespace.
- Other processes still occupy PIDs in the target namespace.
- The namespace's PID 1 may belong to the sandbox or another process outside the image.
- Parent/child relationships may cross container boundaries.
- A sidecar may hold PID files, process handles, or sockets tied to the application.

Before choosing a checkpoint strategy, identify the scope of the process tree being dumped. If the runtime checkpoints only a single container while the PID namespace is shared, verify explicitly how CRIU/the runtime handles processes outside that container. Without documented support, do not assume restore is safe.

One architectural option is to avoid sharing the PID namespace if the application does not need to observe sidecar processes. Separate namespaces reduce collision risks between containers and keep process tree boundaries clean.

## 14. PID Namespaces, Cgroups, and Other Namespaces

A PID namespace only isolates process IDs. It does not isolate CPU/memory resources, filesystems, networking, or privileges. Container runtimes typically combine multiple namespaces and cgroups:

| Component | Scope Managed | Why It Affects Restore |
| --- | --- | --- |
| PID namespace | Process IDs and process visibility | Must assign the right PIDs and rebuild the process tree accurately. |
| Mount namespace | Mount table and filesystem view | Paths, procfs, and file descriptors must point to the right mounts. |
| User namespace | UID/GID mapping and privileges | Ownership/capabilities on restore may differ if mappings are wrong. |
| Network namespace | Interfaces, routes, sockets, and network stack | Sockets/endpoints may be invalid or require reconnection. |
| IPC namespace | SysV IPC and POSIX message queue namespaces | IPC identifiers/resources must be restored in the proper scope. |
| UTS namespace | Hostname and domain name | Hostname may differ in the restore environment. |
| Cgroup | Resource accounting/limits and membership | Processes must reside in the right cgroup and obey quotas/limits. |

Do not adjust the PID namespace in isolation while ignoring related namespaces/cgroups. A process with the right PID but incorrect mounts, user mappings, or cgroup placement can still malfunction or fail to restore.

## 15. Workflow for Preparing the PID Namespace Before Restore

A controlled container restore workflow typically consists of:

1. Select the checkpoint artifact and verify kernel, CRIU, runtime, CPU, and filesystem compatibility.
2. Identify the container's PID namespace topology at checkpoint time.
3. Stop or isolate the target instance so unrelated processes do not occupy PIDs in the namespace to be used.
4. Let the container runtime create the sandbox and namespaces per configuration; if CRIU requires a new namespace, let the runtime/CRIU handle it in a supported mode.
5. Inspect the init process and procfs mount inside the target namespace.
6. Restore the process tree via the container runtime/CRIU integration.
7. Verify PID mappings from the host and inside the container, parent/child relationships, and process count.
8. Verify cgroup, mount, user, and network namespaces.
9. Update PID files, supervisor registrations, and health monitoring if they stored old PIDs.
10. Open traffic only after CRaC callbacks finish and readiness passes.

Do not start a new application inside the same PID namespace prior to restoring an image if the new application might occupy PIDs needed by the image. Never run two restore attempts concurrently into the same target namespace.

## 16. Diagnosing PID Namespaces and Mappings

The following commands help inspect processes from the Linux host. Replace `<host-pid>` with the PID visible on the host:

```bash
# View the process's namespace inode
readlink /proc/<host-pid>/ns/pid

# View PID, parent PID, and namespace mapping
grep -E '^(Name|Pid|PPid|NSpid):' /proc/<host-pid>/status

# List existing PID namespaces
lsns -t pid

# View process from the host
ps -o pid,ppid,ns,pidns,comm -p <host-pid>
```

The `ns` or `pidns` columns of `ps` may not exist in every procps version; if the command does not support them, use `readlink` and `lsns`.

To observe from inside the container's PID namespace, you can use `nsenter` targeting a representative process:

```bash
nsenter -t <host-pid> -p -- ps -ef
```

This command launches a child process inside the target PID namespace; the `/proc` view still depends on the procfs mount in the current mount namespace. Inside a container, the simplest and most reliable method is usually running `ps` and reading `/proc/self/status` directly inside the container.

Example checking the current PID from Java:

```java
public class PidInfo {
    public static void main(String[] args) {
        System.out.println("PID visible to this process: "
                + ProcessHandle.current().pid());
    }
}
```

This value is the PID according to the namespace where the JVM is running, not necessarily the host PID. Cross-check against `NSpid` from the host to determine the mapping.

## 17. Reading PID-Related CRIU Errors

When restore fails, inspect CRIU logs and container runtime logs to distinguish:

- **PID already exists:** the target namespace has a process occupying a PID that needs to be restored.
- **Failed to create PID namespace:** kernel capabilities, user namespaces, runtime, or permissions do not meet requirements.
- **Namespace/init not found:** the namespace handle or init process has terminated or is no longer valid.
- **Incomplete process tree:** the checkpoint lacks required processes or the dump scope does not match.
- **Procfs/mount mismatch:** the process is restored, yet tools inside the container observe the wrong process list.
- **Cgroup/namespace restore failure:** PID setup may be valid, but the container environment is incomplete.

Do not assume every `EEXIST` error is a PID collision; identify the exact syscall and resource in the logs. Similarly, an `EPERM` error may relate to capabilities, namespaces, or security policies rather than an occupied PID.

Investigation procedure:

1. Record the host PID, container PID, PID namespace inode, and container ID.
2. Determine whether the runtime is restoring into a new namespace or an existing one.
3. List current processes in the target namespace before restore.
4. Cross-check PIDs in the checkpoint/process tree against currently occupied PIDs.
5. Check the PID 1 process, parent/child relationships, and shared PID namespace status.
6. Read CRIU, runtime, kubelet, and kernel logs around the time of failure.
7. After fixing configuration, create a clean target namespace via the runtime and retry restoring from an intact artifact.

## 18. Common Pitfalls

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| CRIU fails to create process with saved PID | That PID is already occupied by another process in the same namespace | Use a clean target namespace or a runtime-supported new-namespace mode. |
| Same PID number, yet the process is not the same instance | PID reuse after the previous process exited | Verify namespace, start time, and process identity; do not trust a standalone PID file. |
| Container PID differs from host PID | Two different namespace perspectives | Use `NSpid`, `/proc/<pid>/ns/pid`, and inspect from the right namespace. |
| Java process is not PID 1 | An init/pause/supervisor process leads the namespace | Identify the true namespace init and process tree before dump/restore. |
| Namespace stops working after init exits | PID 1 of the namespace terminated | Create a new namespace and restore via the runtime; never reuse a dead namespace. |
| `ps` inside container displays foreign/missing processes | Procfs mount belongs to another namespace or PID namespace is shared | Check mount namespace and procfs; check `shareProcessNamespace`. |
| PID file points to an unrelated process | Old PID was reused or PID file uses the wrong namespace | Reconcile the PID file after restore and verify process identity before signaling. |
| Restoring one container impacts a sidecar | Pod shares PID namespace or has a shared process tree | Define checkpoint scope; coordinate at Pod/runtime level or separate PID namespaces. |
| Restore runs, yet supervisor fails to manage the process | New host PID differs from old PID | Re-register the process with the supervisor using container/runtime identity and the new PID. |
| Permission error creating namespace | Missing capabilities, user mapping, or security policy restriction | Check runtime, user namespace, capabilities, and kernel policies. |

## 19. Design Principles to Avoid Collisions

- Treat PIDs as ephemeral, namespace-scoped, and reusable identifiers.
- Store container IDs, workload identities, and checkpoint artifact IDs as management identifiers; use PIDs only for point-in-time diagnostics.
- Prefer a dedicated PID namespace for the process tree undergoing checkpoint/restore when architecture permits.
- Let the container runtime manage namespace, cgroup, and init process creation.
- Do not restore into a namespace containing processes outside the image if they could occupy needed PIDs.
- Do not restore two copies concurrently into the same PID namespace.
- Know clearly which process is PID 1 and who is responsible for reaping zombies.
- Do not treat old PID files or pre-checkpoint host PIDs as valid references after restore.
- Rebuild process registration, monitoring, locks, and sockets for the new namespace/host.
- If using Kubernetes `shareProcessNamespace`, evaluate the entire Pod process tree and sidecars before choosing checkpoint scope.
- Verify procfs is mounted for the correct namespace.
- Verify PID, mount, user, network, IPC namespaces, and cgroups as a cohesive set.
- Validate via restore tests on the exact target container runtime and kernel.

## 20. Testing PID Namespaces Across Checkpoint–Restore

An integration test suite should include these cases:

1. **Two namespaces with the same PID number:** run a process with PID `7` in two separate namespaces and verify there is no collision.
2. **Same namespace with occupied PID:** spawn a process holding the required PID and attempt restore; verify the runtime reports a clear error without disrupting the existing process.
3. **Restore into a new namespace:** confirm the process tree is restored with expected internal PIDs while the host PID may differ.
4. **PID 1:** verify namespace init exists, handles signals, and reaps orphans/zombies as required.
5. **PID reuse:** stop a process, start another process, and verify management tools do not confuse processes just because the PID number matches.
6. **Stale PID file:** restore and verify the PID file is updated/reconciled before the supervisor sends any signals.
7. **Procfs mount:** confirm `ps`, `/proc/self/status`, and `NSpid` reflect the expected namespace.
8. **Shared PID namespace in a Pod:** test with `shareProcessNamespace` both enabled and disabled; verify process tree and sidecar scope.
9. **Namespace init termination:** confirm the runtime creates a new namespace rather than using an unusable namespace.
10. **Repeated restores:** confirm each attempt uses its own namespace/process context without overlapping PIDs.

Tests must observe both the host and inside the container. Checking only `ProcessHandle.current().pid()` is not sufficient to establish PID mapping or namespace identity.

## 21. Operational Checklist

- [ ] Know which PID namespace the process runs in.
- [ ] Distinguish host PID, container PID, and PIDs in parent/child namespaces.
- [ ] Record the PID namespace topology and process tree at checkpoint time.
- [ ] Identify the process holding PID 1 and init/reaping responsibilities.
- [ ] Ensure the target namespace is clean or properly prepared by the runtime before restore.
- [ ] Never restore two process trees into the same namespace if PID collisions could occur.
- [ ] Never modify PIDs directly inside the checkpoint image.
- [ ] Inspect `/proc/<pid>/ns/pid`, `NSpid`, and the procfs mount.
- [ ] Reconcile PID files, lock files, sockets, and supervisor registrations after restore.
- [ ] Never use an old host PID as a durable identifier.
- [ ] If Kubernetes shares the PID namespace, define Pod and sidecar boundaries.
- [ ] Verify cgroups, mounts, user, and network namespaces alongside the PID namespace.
- [ ] Use a properly supported container runtime/CRIU integration.
- [ ] Retain CRIU/runtime logs and compatibility metadata for investigation.
- [ ] Test restoring on the target kernel/runtime/container configuration.

## 22. Conclusion

PID namespaces create isolated, hierarchical process ID spaces. A process can have different PIDs inside a container and on the host; two processes with the same PID number in two different namespaces do not conflict. Actual collisions occur when CRIU must restore a PID already in use within the same namespace, or when the target namespace/init/process tree does not match the checkpoint image.

Identify the right namespace and PID 1, create the target namespace through the container runtime, avoid restoring into a namespace with processes occupying needed PIDs, and treat PID files/host PIDs as ephemeral data requiring reconciliation after restore. In Kubernetes, pay special attention to `shareProcessNamespace` and sidecar processes. Combining checks of `NSpid`, namespace inodes, procfs, cgroups, and CRIU logs helps distinguish PID collisions from namespace or permission errors, enabling safer Java container restores.
