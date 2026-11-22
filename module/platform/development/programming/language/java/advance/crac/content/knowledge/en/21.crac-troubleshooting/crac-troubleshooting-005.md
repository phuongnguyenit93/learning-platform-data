# Reading JVM Logs, Checkpoint Engine Logs, and CRIU Logs

When checkpointing or restoring a Java application with CRaC fails, root-cause details often span multiple layers. The JVM may log stack traces from Java callbacks; the JDK's CRaC integration may log orchestration progress; CRIU logs OS-level process freezing and recovery details; and the kernel and container runtime may log errors regarding namespaces, cgroups, permissions, mounts, or system resources.

Reading a single log file alone is rarely sufficient. A `Checkpoint failed` line in the application log only indicates the operation failed without pointing to the cause. An `Error` line in a CRIU log may be the root cause or merely a downstream consequence of an earlier error. You must correlate logs from the same run, determine which stage failed, and trace the event chain from Java down to the operating system.

In this article, "checkpoint engine" refers to the JDK's CRaC runtime/integration layer that coordinates callbacks and the checkpoint backend. Log naming, file locations, and verbosity levels depend on the JDK distribution and version. There is no single universal CRaC log filename across all vendors.

## 1. Log Layers in a Checkpoint/Restore Run

A CRaC application can generate evidence across at least five layers:

| Layer | Log source | Typical contents |
|---|---|---|
| Java application | Logging framework, stdout/stderr | Business state, application-written callbacks, dependency errors |
| JVM | JVM startup, Unified Logging, exceptions/stack traces | JVM configuration, class loading, GC, threads, container detection, runtime errors |
| CRaC integration/checkpoint engine | JDK distribution or runtime wrapper | Checkpoint/restore start, resource orchestration, backend invocation, image path, and integration errors |
| CRIU | CRIU dump/restore logs | Process tree, tasks/threads, file descriptors, sockets, namespaces, mounts, memory mappings, and kernel features |
| Kernel/container/orchestrator | kernel journal, audit log, container runtime, systemd, Kubernetes events | Permission denials, seccomp, SELinux/AppArmor, OOM, cgroups, mounts, and container lifecycle |

These layers may write to the same destination. For example, the JDK may send CRaC messages to stderr while CRIU writes a separate file in the working or checkpoint directory. A service manager may capture both stdout and stderr into the journal. Determine your running environment's configuration rather than assuming logs always reside in a fixed directory.

### Relationships Between Layers

~~~mermaid
flowchart TD
    A[Java application] --> B[CRaC Resource callbacks]
    B --> C[JDK CRaC integration / checkpoint engine]
    C --> D[CRIU]
    D --> E[Kernel and filesystem]
    D --> F[Namespace, cgroup, socket]
    A --> G[Database, broker, HTTP client]
    E --> H[Kernel/audit/container logs]
    C --> I[JVM stdout/stderr or runtime log]
    D --> J[CRIU dump/restore log]
~~~

When reading an incident, start at the moment the operation was requested, then follow down through the layers in depth. If a Java callback throws an exception before the backend runs, hunting for kernel errors will not help. If callbacks finish yet CRIU fails while restoring a file descriptor, inspect CRIU and kernel logs.

## 2. Distinguishing Checkpoint Logs From Restore Logs

Checkpoint and restore are two separate phases. An image can be created successfully yet fail to restore in the target environment. Conversely, restore can succeed while the application fails when refreshing dependencies or opening readiness.

### Checkpoint phase

Conceptual flow:

1. The application closes admission or stops accepting requests per policy.
2. CRaC invokes `beforeCheckpoint(...)` on registered Resources.
3. The application and libraries stop or release resources needing handling.
4. JDK CRaC integration asks the backend to create a checkpoint.
5. CRIU captures process state and supported resources.
6. The runtime finishes the operation and reports checkpoint status.

Items to look for in logs:

- Timestamp when the checkpoint request began.
- Which Resources started and finished callbacks.
- Which Resource threw an exception or took too long.
- Whether the backend was invoked.
- Whether CRIU began dumping the process tree.
- First error appearing on files, sockets, namespaces, cgroups, or memory.
- Whether the runtime confirmed checkpoint completion and image path.

If `beforeCheckpoint` fails, the backend may never have been called or the checkpoint was aborted before producing a complete image. Do not treat the existence of a checkpoint directory as proof of a valid image.

### Restore phase

Conceptual flow:

1. The runtime reads configuration and the checkpoint image.
2. The backend verifies environment conditions and recreates the process.
3. The JVM resumes from the checkpointed state.
4. CRaC invokes `afterRestore(...)` on Resources.
5. The application refreshes identities, secrets, connections, and dependent resources.
6. The application runs health checks and opens readiness.

Items to look for:

- Image path and selected runtime metadata.
- Whether CRIU started restore and recreated processes/threads.
- Any errors regarding kernel features, mounts, file descriptors, sockets, or permissions.
- Whether the JVM resumed running after restore.
- Which Resource failed inside `afterRestore`.
- Which dependencies failed to reconnect.
- Whether readiness opened too early or failed to open.

### Do Not Collapse Three Outcomes Into One

| Outcome | Meaning |
|---|---|
| Checkpoint succeeded | Image was created as confirmed by the runtime |
| Restore succeeded | Runtime/JVM recovered the process and resumed execution |
| Application ready | Application resources, dependencies, and health checks met serving criteria |

A restore can succeed at the CRIU/JVM level while the application remains unready because database credentials rotated or the broker has not rejoined its group. Record all three outcomes separately.

## 3. Locating Where Logs Reside

Log locations depend on how the application is launched, the JDK distribution, CRaC configuration, CRIU, and the deployment platform.

### JVM stdout and stderr

JVM messages, callback exceptions, and some CRaC messages can appear on stdout/stderr. When running via systemd, a container runtime, or Kubernetes, these streams are usually collected by the platform's logging subsystem.

With systemd:

~~~bash
journalctl -u myapp.service --since "2026-11-13 08:00:00" --until "2026-11-13 09:00:00" -o short-iso-precise
~~~

With Docker:

~~~bash
docker logs --timestamps --since 2026-11-13T08:00:00Z myapp
~~~

With Kubernetes:

~~~bash
kubectl logs -n production myapp-pod --timestamps
kubectl logs -n production myapp-pod --previous --timestamps
~~~

The `--previous` flag helps when a container restarted and logs from the prior run are still retained by the runtime. Log access depends on RBAC and cluster retention.

### Checkpoint engine logs

Messages from the JDK CRaC integration can be written:

- Directly to JVM stdout/stderr.
- To a file configured by the runtime or launcher.
- To journal/container logs if the process is platform-managed.
- To the working/checkpoint directory depending on the implementation.

Read the documentation for your exact JDK distribution to learn how to increase verbosity, configure log files, and locate CRIU output. Do not infer filenames from a different JDK distribution. If the runtime uses a wrapper script, check where the wrapper redirects output and stores checkpoint metadata.

### CRIU logs

CRIU normally writes separate logs for dump and restore operations. Filenames and directories depend on how CRIU is invoked, logging arguments, image/work directories, and how the JDK integrates CRIU.

Some environments produce logs named after dump/restore or PID. Others route content to stderr or place files in a runtime-specified directory. Search by timestamp and PID inside the configured directory; do not assume all CRIU builds use the same filename.

### Kernel and container logs

If CRIU reports permission or resource errors, inspect the kernel journal as well:

~~~bash
journalctl -k --since "2026-11-13 08:00:00" --until "2026-11-13 09:00:00"
dmesg -T
~~~

Look for OOM kills, seccomp, audit denials, SELinux AVCs, AppArmor, cgroup events, and filesystem errors. In Kubernetes, inspect pod events, node events, and container runtime logs if authorized.

### Finding Logs Without Misreading Checkpoint Images

A checkpoint directory may contain binary images, metadata, and logs. Do not open or modify image files in an editor. Use `find` to list names, types, and timestamps; read only files identified as log/text per runtime configuration.

~~~bash
find /var/lib/myapp/crac -maxdepth 4 -type f -printf '%TY-%Tm-%TdT%TH:%TM:%TS %s %p\n'
file /var/lib/myapp/crac/release-001/*
~~~

Do not dump the entire checkpoint directory contents into log collectors or tickets. Images can contain sensitive data in the heap.

## 4. Collecting Metadata to Correlate Logs

Before analyzing, create a record for each checkpoint/restore attempt. The following fields help distinguish runs:

| Field | Why it is needed |
|---|---|
| Checkpoint ID | Identifies the image being created or restored |
| Restore attempt ID | Distinguishes multiple restores of the same image |
| Application build/version | Identifies code and dependencies |
| JDK vendor/version | Identifies the CRaC implementation |
| CRIU version | Cross-references backend behavior |
| Kernel version | Cross-references OS features and limits |
| Container/runtime version | Identifies namespaces, cgroups, and policies |
| PID and namespaces | Correlates logs of the exact process |
| Host/pod/container ID | Identifies the physical/virtual execution environment |
| Checkpoint/restore path | Pinpoints the exact image set |
| Start/end timestamps | Correlates logs within the same time window |
| User/UID/GID | Investigates permissions and ownership |
| Exit code and signal | Distinguishes process exit, runtime failure, and OOM |

Do not use PID alone as a correlation ID because PIDs can be reused or differ across namespaces. Pair PID with host/container, timestamp, and checkpoint ID.

### Timestamps and clock skew

Prefer timestamps with timezones or UTC in logs. When correlating logs across multiple nodes, verify clock synchronization. If node clocks drift apart, events can appear out of order when sorted by timestamp.

Inside the application, you can log both:

- Wall-clock timestamps for cross-machine correlation.
- Monotonic elapsed time to measure durations within the same process.

Do not subtract timestamps from two different machines without accounting for clock skew.

### Building a timeline

Example normalized timeline:

| UTC | Component | Event |
|---|---|---|
| 08:10:00.100 | Application | Received checkpoint request `cp-42` |
| 08:10:00.120 | CRaC Resource | Started `beforeCheckpoint` |
| 08:10:00.180 | CRaC Resource | All callbacks completed |
| 08:10:00.210 | Checkpoint engine | Started invoking backend |
| 08:10:00.250 | CRIU | Started dumping PID in namespace |
| 08:10:00.490 | CRIU | Reported error handling a socket |
| 08:10:00.510 | Checkpoint engine | Backend returned error |
| 08:10:00.520 | Application | Checkpoint failed |

This is illustrative data. In real investigations, record verbatim timestamps, messages, and log sources; do not fabricate missing events.

## 5. Reading JVM Logs

JVM logs help determine what configuration the runtime is running with, whether Java callbacks failed, and which stage the JVM reached.

### Verifying the Exact JDK and CRaC Options

Record:

~~~bash
java -version
java -XshowSettings:properties -version
~~~

If the process is still running and attach is permitted:

~~~bash
jcmd <pid> VM.version
jcmd <pid> VM.flags
~~~

Verify JDK distribution, version, build number, VM flags, and relevant properties. Do not assume a standard JDK has the same features or CRaC options as a specially packaged JDK build.

Startup errors such as `Unrecognized VM option`, `Could not create the Java Virtual Machine`, `NoClassDefFoundError`, or `ClassNotFoundException` can happen before the checkpoint engine is ever called. In those cases, inspect the JDK, classpath/module path, CRaC API, and launch configuration first.

### Exceptions in Resource Callbacks

Look for stack traces showing application or library methods inside:

- `beforeCheckpoint(...)`
- `afterRestore(...)`
- Prepare/refresh/reconnect methods invoked by the application from callbacks.

Illustrative error example:

~~~text
java.lang.IllegalStateException: database pool is still active
    at com.example.DatabaseResource.beforeCheckpoint(DatabaseResource.java:42)
    at ...
~~~

What to read:

1. Exception type and message.
2. First line belonging to application code.
3. Which Resource threw the error.
4. Which callback was executing.
5. Whether the exception has a cause or suppressed exceptions.
6. Whether the runtime reported the callback completed or checkpoint aborted.

Do not read only the bottom line of a stack trace. The root exception may lie inside `Caused by`, while the top exception is only a wrapper.

### JVM Unified Logging

The JVM can emit detailed logs using Unified Logging (`-Xlog`). Tags and output may vary by JDK build; inspect supported tags with:

~~~bash
java -Xlog:help
~~~

An example configuration logging container detection if the corresponding tag exists in your build:

~~~bash
-Xlog:os+container=info:file=/var/log/myapp/container.log:time,uptime,level,tags
~~~

Do not enable `all=trace` indiscriminately in production. Overly verbose logging can generate huge data volumes, add overhead, and expose internal details. Choose tags targeting your hypothesis, enable for a bounded time, then return to normal configuration.

### Threads and JVM State

If the JVM remains alive after restore yet the application makes no progress, capture a thread dump:

~~~bash
jcmd <pid> Thread.print
~~~

Look for:

- Threads waiting on network or file I/O.
- Threads blocked on monitors/locks.
- Stopped executor workers while queues remain populated.
- Duplicated or looping background threads.
- Client threads failing to reconnect.

If the process has already exited, `jcmd` cannot attach; rely on previously captured thread dumps, hs_err logs, or diagnostic artifacts. Do not assume you can take a thread dump after a process dies.

### GC and Memory

If restore finishes yet performance or readiness is abnormal, correlate GC logs, heap, non-heap, and native memory. GC data helps spot allocation bursts, heap pressure, or long pauses, though it does not by itself explain CRIU errors.

If Native Memory Tracking was enabled from JVM startup, you can inspect:

~~~bash
jcmd <pid> VM.native_memory summary
~~~

NMT cannot be enabled retroactively in full for an already running JVM if the required startup option was omitted. Explicitly note when a metric category is unavailable.

## 6. Reading Checkpoint Engine and CRaC Integration Logs

The checkpoint engine layer bridges Java's CRaC API and the OS backend. It can orchestrate resources, set up working directories, invoke CRIU, collect outcomes, and return errors to the JVM.

Logger names, verbosity options, log files, and messages depend on the JDK distribution. Use the documentation of your exact provider and record the version before comparing against online examples.

### Message Types to Look For

- Checkpoint or restore start.
- Image path and working directory.
- Number or names of Resources invoked if logged by the runtime.
- Which callbacks completed or failed.
- Backend invocation and exit status if recorded.
- CRIU log path.
- Duration of each phase.
- Errors reading metadata or preparing the environment.
- Final status: success, failure, cancelled, or timeout.

### Distinguishing Orchestration Errors From Backend Errors

**Orchestration errors** usually occur before CRIU runs: invalid options, image directory cannot be created, Resource throws an exception, runtime cannot find the backend, or incompatible configuration.

**Backend errors** occur after the engine invokes CRIU: CRIU cannot dump/restore the process, file descriptors, namespaces, mounts, memory mappings, or kernel state.

If the engine log reports only `CRIU failed`, locate the referenced CRIU log. If no CRIU log exists, verify whether the backend was actually called or the error happened beforehand.

### Watch Out for Duplicate or Missing Logs

Some launchers write the same messages to both stderr and a file. Some systems retain only logs of the current container and lose logs after a restart. Check timestamps, PIDs, and sources to avoid counting the same event twice.

If the runtime does not emit enough detail, enable diagnostic mode per your JDK distribution's documentation in a reproduction environment. Do not edit internal scripts or inject arbitrary CRIU flags unless supported by the provider.

## 7. Reading CRIU Logs

CRIU performs most of the Linux process-level checkpoint/restore work. CRIU logs usually contain deeper details about kernel resources than JVM logs.

A CRIU error line may look like:

~~~text
Error (criu/cr-restore.c:1234): failed to restore task: Operation not permitted
~~~

The filename and line number in the example illustrate format only. During analysis, preserve the actual lines along with surrounding lines and the CRIU version.

### Severity and Reading Order

CRIU can emit levels such as `Error`, `Warn`, `Info`, or debug depending on version/configuration. Not every `Warn` causes the operation to fail. Some warnings describe optional features or conditions handled via fallback.

When an error occurs:

1. Find the first occurrence of `Error` within the exact dump/restore attempt.
2. Read the lines immediately preceding it to see what operation was underway.
3. Look for matching PIDs, FDs, mount IDs, namespaces, or resource identifiers on related lines.
4. Check whether subsequent errors are cascading consequences of the first error.
5. Cross-check kernel logs and environment configuration.

Do not assume the final `Error` line is the root cause. After one step fails, dependent steps may emit multiple additional errors.

### Common Error Categories

| Category | Symptoms | Investigation direction |
|---|---|---|
| Kernel feature | Unsupported feature or syscall | Kernel version/configuration and CRIU compatibility |
| Permission/capability | `Operation not permitted`, `Permission denied` | UID/GID, capabilities, user namespaces, seccomp, and LSM |
| Cgroup | Cannot read/write or recreate cgroup | Cgroup v1/v2, mounts, and runtime permissions |
| Namespace | Unable to create or join namespace | User/PID/network/mount namespaces and container policies |
| File descriptor | File or FD cannot be restored | File path, owner, mount, socket, and file state |
| Network/socket | Unsupported TCP/Unix socket or missing endpoint | Socket type, peer state, port, network namespace |
| Mount/filesystem | Incompatible mount point or filesystem | Mount table, filesystem type, propagation, and permissions |
| Memory mapping | Mapping, shared memory, or file-backed mapping failure | Backing file, address mapping, kernel, and CRIU features |
| Process/thread | Task/thread cannot be restored | Thread state, ptrace, signals, and process tree |
| Resource limit | Insufficient memory, PIDs, file descriptors, or quota | ulimit, cgroup limits, host capacity |

### Permissions and Capabilities

`Operation not permitted` does not necessarily mean wrong file permissions. It can stem from capabilities, user namespaces, seccomp, SELinux/AppArmor, or a kernel-denied syscall.

Cross-check:

~~~bash
id
grep -E '^(Uid|Gid|Groups|Cap(Inh|Prm|Eff|Bnd|Amb)|NoNewPrivs|Seccomp):' /proc/<pid>/status
~~~

If the process has exited, `/proc/<pid>` entries may be gone. Collect this information before checkpoint or from container/runtime configuration during reproduction.

### File Descriptors and Mounts

If the error involves an FD, socket, or mount, identify which resource was open at checkpoint time and its state at restore time. An FD may point to a deleted file, a changed mount, or a socket that cannot be re-established in the new environment.

Do not fix by creating an empty file of the same name without understanding semantics. The runtime may require specific inodes, mounts, or file state.

### Sockets and TCP Connections

Not every socket can be checkpointed/restored in every configuration. TCP connections can depend on kernel features, network namespaces, peer state, and two-sided coordination. For database/broker clients, applications normally need to close and recreate connections via library lifecycles rather than relying on keeping sockets open across restore.

If CRIU logs mention an established TCP connection, check the socket type, TCP-support configuration, whether the peer still exists, and whether JDK/CRIU are configured per documentation. Do not enable an option allowing open sockets just to bypass an error; evaluate peer and application correctness after restore.

### Kernel Features and Version Mismatch

An image created on another kernel or environment may depend on features unsupported by the target host. Record:

~~~bash
uname -a
criu --version
criu check
~~~

`criu check` tests environment capabilities for the current CRIU version; it does not prove every specific resource used by an application can checkpoint/restore. Results also depend on permissions, configuration, and which features the check exercises.

## 8. Kernel, Audit, and Container Runtime Logs

CRIU may report a failed syscall while the policy cause lives inside the kernel or security subsystem. In that case, correlate host-layer logs.

### OOM and Memory Pressure

If the process vanishes or the container restarts, check for OOM:

~~~bash
journalctl -k --since "2026-11-13 08:00:00" | grep -i -E 'oom|out of memory|killed process'
~~~

In containers, check memory limits and cgroup events. An OOM kill can make the JVM disappear without a Java exception or stack trace. Distinguish host OOM from cgroup/container OOM.

### SELinux and AppArmor

Permission bits may be correct while an LSM still denies the operation. Search for audit denials and security contexts matching the process/path. Do not disable policies host-wide for testing. If changes are needed, create scoped rules and record the policy/version used in tests.

### Seccomp and Capabilities

A container profile may block required syscalls or drop capabilities required by CRIU. Compare security configurations between source and target containers. A pod may run regular Java fine yet lack permissions for checkpoint/restore operations.

### Cgroups and Namespaces

Record cgroup version, mount points, container runtime, PID namespace, user namespace, and network namespace. When restoring into another environment, namespaces or cgroups may differ from the image-creation environment.

### Pod and Container Events

In Kubernetes, inspect:

~~~bash
kubectl describe pod -n production myapp-pod
kubectl get events -n production --sort-by=.lastTimestamp
~~~

Look for restart reasons, OOMKilled, probe failures, mount errors, image pulls, or scheduling issues. Pod events can explain why a process was replaced while JVM logs show only abrupt termination.

## 9. Reading Logs by Symptom

Instead of hunting for a single log message, start from the symptom and inspect relevant layers.

### Checkpoint Fails Before Any CRIU Log Exists

Possibilities:

- CRaC JVM option unrecognized.
- Resource API unavailable on runtime.
- `beforeCheckpoint` throws an exception.
- Application did not drain requests or stop resources.
- Checkpoint directory cannot be created/written.
- Engine cannot locate or launch the backend.

Remediation direction:

1. Read JVM startup logs and full exceptions.
2. Confirm JDK distribution/version and flags.
3. Search callback logs by Resource name.
4. Check owner/mode and path of the checkpoint directory.
5. Determine whether the engine invoked CRIU.

### CRIU Dump Fails

Possibilities:

- Unsupported process resource.
- Missing capabilities or blocked by seccomp/LSM.
- File descriptor, socket, or mount cannot be handled.
- Missing kernel feature.
- Insufficient resources or PID/FD limit reached.

Remediation direction:

1. Locate the first CRIU `Error` and preceding lines.
2. Correlate PID, FD, mount, and namespaces.
3. Inspect kernel/audit logs at the same timestamp.
4. Compare kernel, CRIU, and container policies.
5. Reproduce in a test environment with the same configuration.

### Restore Fails Before the JVM Resumes

Possibilities:

- Incomplete image or invalid checksum.
- Incompatible runtime/JDK/CRIU.
- Mounts, paths, namespaces, or kernel differ from the source environment.
- OS resources cannot be recreated.

Remediation direction:

1. Verify the exact checkpoint ID and complete image tree.
2. Check checksums/manifests if present.
3. Read CRIU restore logs and engine logs.
4. Compare the image-creation environment with the target environment.
5. Do not edit binary images directly to bypass errors.

### Restore Succeeds but Callbacks Fail

Possibilities:

- `afterRestore` fails to obtain workload identity or secrets.
- Database/broker/HTTP client cannot reconnect.
- Old client still holds stale sockets or stale credentials.
- Threads/executors were not recreated.
- Resource dependency ordering was not preserved.

Remediation direction:

1. Confirm the JVM resumed running.
2. Locate the first exception inside `afterRestore`.
3. Identify which dependency is unready.
4. Keep readiness false and inspect retries/timeouts.
5. Confirm clients are newly created and health checks execute real operations.

### Application Ready Yet Requests Fail

Possibilities:

- Readiness opened too early.
- An optional dependency has not recovered.
- DNS, certificates, credentials, or endpoints changed.
- Background threads or schedulers are inactive.
- Application uses stale caches or stale runtime identity.

Remediation direction:

1. Correlate request ID/trace ID with incarnation ID.
2. Inspect application logs and dependency metrics.
3. Inspect thread dumps and connection pools.
4. Check secret versions, endpoints, and service discovery.
5. Fix readiness to reflect dependencies truly required for traffic.

## 10. Step-by-Step Investigation Workflow

A consistent workflow reduces time spent reading logs and avoids fixing the wrong layer.

### Step 1 — Pin Down the Run and Symptoms

Record checkpoint ID, restore attempt ID, PID/host/container, timestamp, exit code, signal, and observed symptoms. Determine whether failure occurred during checkpoint, during restore, or after the application became ready.

### Step 2 — Collect Verbatim Logs

Save copies of:

- JVM stdout/stderr.
- Application logs.
- CRaC integration/checkpoint engine logs.
- CRIU dump/restore logs.
- Kernel/audit logs.
- Container runtime/orchestrator events.

Preserve timestamps, timezones, PIDs, and line order. Do not copy only a few `Error` lines, as preceding lines usually explain the operation underway.

### Step 3 — Build a Timeline

Order events by normalized timestamp. Mark callback start/end, backend invocation time, first CRIU error line, process resume time, and readiness open time.

### Step 4 — Identify the First Failing Layer

Ask:

- Did the error appear before or after the engine called CRIU?
- Did CRIU begin dumping/restoring?
- Were there kernel denials/OOMs?
- Did the JVM run the corresponding callbacks?
- Did an external dependency return an error?

The first layer where failure originates is usually where investigation should start.

### Step 5 — Inspect Configuration and Environment

Record JDK/CRaC build, CRIU version, kernel, container runtime, UID/GID, capabilities, seccomp/LSM, cgroups, mounts, and checkpoint path. Compare against the image-creation environment.

### Step 6 — Controlled Reproduction

Test the same image, same JDK/CRIU, and configuration closely matching the failing environment. Change only one factor at a time. If increasing verbosity, do so for a bounded period and protect logs.

### Step 7 — Record Evidence-Based Conclusions

Report:

- Symptoms.
- Affected runs and images.
- First error line and its source.
- Confirmed root cause or open hypotheses.
- Supporting evidence.
- Reproduction conditions.
- Attempted changes and outcomes.
- Limitations/unknowns.

Do not conclude "CRIU failed" merely because the last log line says CRIU failed; identify the specific resource or syscall when evidence permits.

## 11. Commands Supporting Log Collection

The commands below are Linux examples. Adjust services, namespaces, paths, and time windows to your environment. Run as a user authorized to read the required logs.

### Version Information

~~~bash
java -version
criu --version
uname -a
~~~

### systemd journal

~~~bash
journalctl -u myapp.service --since "1 hour ago" -o short-iso-precise
journalctl -k --since "1 hour ago" -o short-iso-precise
~~~

### Filtering Errors in Collected Logs

~~~bash
grep -n -E 'Error|ERROR|Exception|Caused by|Warn|WARNING|CRIU|CRaC|checkpoint|restore' app.log
~~~

If `rg` is available, you can use:

~~~bash
rg -n -i 'error|exception|caused by|warn|criu|crac|checkpoint|restore' logs/
~~~

This finds starting points; once matching lines are found, read surrounding context to preserve narrative.

### CRIU preflight

~~~bash
criu check
~~~

This command checks several capabilities of the current CRIU environment. It does not replace a real application checkpoint/restore and does not fully verify every file descriptor, socket, or native resource used by the application.

### Process and cgroup

~~~bash
id
cat /proc/<pid>/status
cat /proc/<pid>/cgroup
~~~

`/proc/<pid>` files exist only while the process is alive and accessible. If the PID has exited, use previously collected data or container/orchestrator configuration.

### Viewing More Detailed CRIU Logs

The CRIU CLI has version-dependent logging options, typically including verbosity levels and log files. Verify syntax on your exact binary:

~~~bash
criu --help
criu dump --help
criu restore --help
~~~

For CRIU invoked internally by the JDK, configure verbosity or log paths only per your JDK distribution's documentation. Do not run a manual `criu dump` command against a JDK-managed JVM in place of the CRaC workflow; doing so bypasses callbacks and corrupts application state.

## 12. Example Analysis of an Illustrative Failure

Suppose the application reports checkpoint failure. Collected logs look like:

~~~text
08:10:00.100 app  INFO  checkpoint requested id=cp-42
08:10:00.120 app  INFO  beforeCheckpoint resource=DatabaseResource
08:10:00.180 app  INFO  beforeCheckpoint completed resource=DatabaseResource
08:10:00.210 engine INFO backend checkpoint started id=cp-42
08:10:00.250 criu  INFO  dumping process tree
08:10:00.490 criu  Error (criu/files.c:123): cannot open file descriptor: Permission denied
08:10:00.510 engine ERROR backend checkpoint failed
08:10:00.520 app  ERROR checkpoint failed id=cp-42
~~~

How to read it:

1. The application callback completed, so the error did not originate in `DatabaseResource.beforeCheckpoint`.
2. The engine invoked the backend and CRIU began dumping.
3. The first error in the CRIU log involves a file descriptor and `Permission denied`.
4. You must identify which FD was denied, the corresponding file/path/mount, and the process's user/capabilities.
5. Correlate kernel/audit logs to check for SELinux, AppArmor, seccomp, or permission denials.

From the lines above alone, you cannot conclude that you simply need to chmod a file. `Permission denied` can stem from permissions on the file, parent directories, namespaces, or security policies. Locate the FD and host evidence before making changes.

### Example Error in a Restore Callback

~~~text
09:05:10.100 engine INFO restore completed
09:05:10.130 app  INFO  afterRestore resource=SecretResource
09:05:10.210 app  ERROR java.net.SocketTimeoutException: secret manager timed out
09:05:10.220 app  WARN  readiness remains closed
~~~

In this case, logs show the backend completed restore and the error occurred while the application fetched secrets after restore. Investigation targets workload identity, network, DNS, the secret manager, and timeouts; do not start by changing the kernel or CRIU without evidence that the backend failed.

## 13. Enabling Verbosity Under Control

Detailed logs help when you need to know which resource CRIU is processing, yet they can:

- Produce massive log volumes.
- Increase operation duration or affect performance.
- Record paths, processes, users, network details, or sensitive data.
- Fill disks if rotation is absent.

Appropriate workflow:

1. Reproduce in a test or staging environment first.
2. Target only the component needing higher verbosity.
3. Verify options against the exact JDK/CRIU versions.
4. Bound duration and run count.
5. Place log paths under tight access controls with sufficient disk space.
6. Collect stdout/stderr, engine logs, and CRIU logs from the same run.
7. Disable extra verbosity once sufficient evidence is gathered.

Do not leave full JVM and CRIU tracing enabled long-term in production. If production capture is necessary, coordinate a maintenance window or an operations-approved diagnostic mechanism.

## 14. Protecting Logs and Checkpoints During Investigation

Logs may contain infrastructure details or sensitive data. Checkpoint images can additionally contain object graphs and secrets in the heap.

When sharing logs:

- Redact passwords, tokens, authorization headers, cookies, and private keys.
- Redact URLs containing credentials or secret query parameters.
- Retain timestamps, PIDs, exception types, source files, and necessary technical messages.
- Do not delete original error lines or context lines needed to understand sequence.
- Restrict access and set retention policies for raw logs.

When sharing checkpoints:

- Do not send images through regular tickets/chat.
- Use encrypted storage and restricted permissions.
- Grant image access only to investigators who need it.
- Do not edit binary images to scrub secrets.
- If an image contains exposed credentials, rotate/revoke those credentials and handle all artifact copies.

Produce a redacted log copy for sharing and keep originals in protected storage. Audit who accessed artifacts and when according to operational policy.

## 15. Common Log-Reading Mistakes

| Misreading pattern | Why it is wrong | Proper approach |
|---|---|---|
| Reading only application logs | The application usually receives only a generic backend failure notice | Correlate JVM, engine, CRIU, and kernel logs |
| Reading only the last `Error` line | It may be a downstream consequence of an earlier error | Locate the first error and read its context |
| Assuming `Warn` is always harmless | A warning may indicate a fallback or impact boundary | Cross-check against outcomes and version docs |
| Assuming every `Error` is a root cause | Some errors are cascading failures | Trace back to the first failing operation |
| Looking up CRIU logs by one fixed name | Name/path depends on runtime and config | Check the log path indicated by the engine |
| Mixing checkpoint and restore together | The two phases have distinct resources and errors | Tag each log with action and checkpoint ID |
| Correlating solely by PID | PIDs can be recycled or differ across namespaces | Use PID + host/container + timestamp + image ID |
| Looking only at CRIU version | Kernel, capabilities, and namespaces also govern behavior | Record the full environment |
| Running CRIU manually on the JVM to reproduce | Bypasses CRaC lifecycle and can corrupt process state | Use the supported CRaC JDK workflow |
| Leaving trace logging on continuously | Adds overhead, fills disks, and risks leaking data | Raise verbosity for a bounded time and scope |
| Sharing raw logs/checkpoints publicly | Can expose secrets and infrastructure details | Redact logs; protect artifacts |

## 16. Incident Investigation Checklist

### Identifying the Run

- [ ] Checkpoint ID and restore attempt ID recorded.
- [ ] Timestamp, timezone, PID, host/container, and application version recorded.
- [ ] JDK distribution/version, CRIU version, and kernel version recorded.
- [ ] Determined whether failure occurred during checkpoint, during restore, or after the application became ready.

### Collecting Logs

- [ ] Full application stdout/stderr and stack traces collected.
- [ ] Necessary JVM logs collected.
- [ ] CRaC integration/checkpoint engine logs collected.
- [ ] Corresponding CRIU dump/restore logs collected.
- [ ] Kernel/audit/container/orchestrator events collected.
- [ ] Logs preserved with original timestamps and ordering, including pre/post-error context.

### Analysis

- [ ] Verified whether Java callbacks completed.
- [ ] Verified whether the CRIU backend was invoked.
- [ ] Located the first CRIU error line and associated resource.
- [ ] Checked permissions, namespaces, cgroups, mounts, sockets, and kernel features as applicable.
- [ ] Checked dependencies, secrets, connections, and readiness if restore already succeeded.
- [ ] Assembled timeline and checked for clock skew.

### Conclusions and Sharing

- [ ] Root causes separated from unconfirmed hypotheses.
- [ ] Supporting log and environment evidence documented.
- [ ] Reproduction conditions and test outcomes documented.
- [ ] Shared logs redacted of secrets.
- [ ] Checkpoint images protected and never sent over insecure channels.
- [ ] Extra verbosity turned off after investigation.

Effective CRaC log reading requires tracing straight from Java callbacks down to the checkpoint engine, CRIU, and the kernel. First pinpoint the exact run and failing stage; next correlate logs by checkpoint ID, PID, host/container, and timestamp; finally locate the first failing operation and cross-check it against the environment. This layered reading approach separates application bugs, orchestration failures, CRIU errors, and operating system errors, while avoiding misdirected configuration tweaks or losing data needed to reproduce incidents.
