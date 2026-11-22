# Collecting Error Evidence Without Exposing Data Inside Checkpoints

When a Java application using CRaC encounters a checkpoint or restore error, the operations team needs to collect enough evidence to determine whether the error comes from the JVM, CRIU, kernel, container runtime, application resources, or external dependencies. However, a checkpoint image is the memory state of the process. It can contain passwords, tokens, private keys, session cookies, personal data, request bodies, caches, and in-flight business information.

Therefore, **do not treat a checkpoint image, heap dump, or core dump as an ordinary diagnostic log**. An initial evidence package should prioritize controlled logs, callback timelines, runtime versions, resource status, error codes, metrics, and checksums. Access memory contents only when there is a specific investigative reason, proper approvers, and a separate controlled storage procedure.

The goal is to preserve the ability to reproduce the incident without copying sensitive data into tickets, chats, emails, or widely accessible logging systems.

## 1. Why Must a Checkpoint Be Treated as Sensitive Data?

A checkpoint can save heap state and other process components according to the capabilities of the JDK/CRaC and the platform. If the application holds sensitive data in memory at checkpoint time, that data may appear in the image.

Examples of contents that may reside in memory:

- Database passwords, access tokens, refresh tokens, and API keys.
- Private keys, TLS material, or decrypted credential objects.
- Session cookies, authorization headers, and user identity information.
- Request/response bodies, payment data, or business information.
- Caches containing personal data, customer profiles, or access permissions.
- Query parameters, SQL bind values, and message payloads.
- Objects containing internal URLs, hostnames, IPs, file paths, or infrastructure configurations.

Even if the application closed the connection pool before checkpoint, passwords or tokens may still remain in configuration objects, immutable strings, caches, or copies created by libraries. Calling `Arrays.fill()` on a `char[]` also does not prove that every copy of a secret has disappeared from the heap.

Other types of diagnostic artifacts can also contain sensitive data:

| Artifact | Possible Contents | Caution Level |
| --- | --- | --- |
| CRaC checkpoint image | Process state, heap, threads, native/process state, and application data | Very high; handle as sensitive application data. |
| JVM heap dump | Object graph, strings, byte arrays, credentials, and payloads | Very high; can directly expose data. |
| Core dump | Process memory, registers, stacks, and native regions | Very high; may contain secrets and payloads. |
| JFR recording | Runtime events, classes/methods, exceptions, threads, sockets, or custom events depending on config | High; must inspect events and contents before sharing. |
| Thread dump | Stack traces, thread names, locks/monitors, and sometimes information in exceptions or task names | Medium to high; review before sending externally. |
| JVM/CRIU log | PIDs, paths, mounts, commands, namespaces, system errors, and possibly configuration info | Medium to high; filter and restrict access. |
| Metrics/health output | Dependency names, endpoints, labels, errors, and operational status | Depends on labels and instrumentation; avoid putting identifiers/secrets in labels. |
| Manifest/checksum | Build, version, artifact id, paths, or hashes | Generally less sensitive, but can still reveal topology and artifact relationships. |

No artifact is automatically safe merely because it is not a checkpoint image. You must examine the actual contents, collection purpose, and audience scope.

## 2. Classifying Evidence Before Collection

Divide evidence into three groups to decide how to handle it:

**Group A — Low-sensitivity metadata and status:** JDK/CRaC/CRIU versions, kernel, architecture, timestamps, duration, exit code, exception types, retry counts, readiness status, filesystem space, and checksums. This is typically the first choice.

**Group B — Logs and diagnostic outputs requiring review:** JVM/CRIU logs, thread dumps, JFR, command line, system properties, process tree, mount table, DNS results, and endpoints. These may contain paths, hostnames, usernames, tokens, or payloads and must be filtered before sharing.

**Group C — Memory contents and raw artifacts:** checkpoint images, heap dumps, core dumps, raw packet captures, and files containing secrets. Collect only when necessary, store separately, encrypt, and restrict who is permitted access.

| Group | Examples | Typical Usage |
| --- | --- | --- |
| A | Runtime version, callback duration, error code, readiness transition | Can be included in the evidence package after checking metadata. |
| B | JVM/CRIU logs, thread dump, JFR, `/proc` output | Keep raw copy in a restricted area; create a redacted copy for sharing. |
| C | Checkpoint, heap/core dump, packet capture with payloads | Do not attach to tickets/chats; access only via special incident procedures. |

If you do not yet know whether a file contains secrets, classify it as high sensitivity until inspection is complete.

## 3. Starting with Timelines and Correlation IDs

An accurate timeline is often more useful than collecting many files. Record timestamps in UTC and attach them to a stable `checkpointAttemptId`/`restoreAttemptId`.

Milestones to include:

1. Application starts running and completes warm-up.
2. Readiness transitions to refusing traffic.
3. Resources start `beforeCheckpoint`.
4. Each Resource starts/finishes draining, flushing, closing sockets, or closing pools.
5. Checkpoint command is sent and finishes.
6. JVM/CRIU reports success or failure; the original process changes state.
7. Dependencies change state during the checkpoint window, if any.
8. Restore command starts.
9. JVM starts/completes `afterRestore`.
10. Each Resource reconnects, validates, and reports its outcome.
11. Readiness transitions to accepting traffic or remains `NOT_READY`.
12. First request/message after restore succeeds or fails.

Example structured log:

```text
timestamp=2026-11-13T09:00:00.120Z attempt=cp-7f2a event=readiness state=REFUSING_TRAFFIC
timestamp=2026-11-13T09:00:00.145Z attempt=cp-7f2a resource=db-pool event=beforeCheckpoint-start
timestamp=2026-11-13T09:00:00.390Z attempt=cp-7f2a resource=db-pool event=beforeCheckpoint-complete duration_ms=245
timestamp=2026-11-13T09:00:00.410Z attempt=cp-7f2a event=checkpoint-requested
timestamp=2026-11-13T09:00:01.900Z attempt=cp-7f2a event=checkpoint-failed error_type=DumpError
```

The example contains only synthetic identifiers and metadata. Do not write passwords, tokens, SQL bind values, payloads, Authorization headers, or secret contents into callback logs.

Host/container clocks can drift. Clearly record the timezone, time source, and estimated skew if known. When correlating logs from the JVM, CRIU, database, and orchestration, use both timestamps and the attempt id to avoid misinterpreting ordering due to clock skew.

## 4. Collecting Runtime Metadata Before Reading Memory

The following information often helps narrow the scope of an incident without dumping the heap:

- Application build/version and Git commit.
- JDK vendor, version, build, and filtered relevant JVM flags.
- CRaC library/runtime version.
- CRIU version and capability/runtime mode if CRIU is used.
- OS distribution, kernel version, and CPU architecture.
- Container runtime, container image digest, and Kubernetes/node version if applicable.
- Cgroup limits, memory pressure, OOM events, and filesystem capacity.
- Checkpoint path as a sanitized identifier; do not expose paths containing sensitive usernames or tenants.
- Filesystem/mount type and required access permissions.
- Dependency version/endpoint identity at the level approved for disclosure.

Example commands to gather basic information on Linux:

```bash
java -version
uname -srmo
criu --version
df -h /var/lib/myapp
```

The commands above are examples only; the `criu` command is only available if CRIU is installed on the host and in PATH. Filesystem paths can reveal infrastructure layout, so replace them with mount labels or sanitized paths in externally shared copies. Do not run commands that print all environment variables or system properties just to gather metadata.

If a JVM diagnostic summary is needed, prefer commands that return only approved version, uptime, or memory summaries. For example, `jcmd <pid> VM.version` and `jcmd <pid> VM.uptime` are generally lower risk than dumping the full command line or system properties. Still review output before attaching.

## 5. Selecting Appropriate JVM and CRIU Logs

JVM and CRIU logs are often critical evidence for determining whether an error occurred during preparation, dump, restore, or resource callbacks.

Collect:

- Application logs surrounding the checkpoint/restore attempt.
- JVM logs containing CRaC callback messages, exception types, and operation outcomes.
- CRIU or container runtime logs corresponding to the exact attempt.
- Kernel/system logs if there are syscall, permission, cgroup, or OOM errors.
- Orchestrator events related to container restarts, node pressure, mounts, or networking.

When reading logs, focus on:

- The time of the first error, not just the last line.
- PID and namespace context of the involved process.
- The type of operation being executed: prepare, dump, restore, or reconnect.
- Error code/errno, exception class, and originating component.
- The last Resource callback that completed.
- Process or container state changes around the time of the error.

CRIU logs may contain filesystem paths, PIDs, namespaces, mounts, socket endpoints, and configuration details. Some logs or wrappers may print commands/arguments; review before sending externally. Do not assume system logs are already redacted.

Keep the original copy in a restricted incident storage area. Create a working copy for redaction, keeping the original unmodified for audit and comparison purposes.

## 6. Diagnostic Commands That Risk Exposing Secrets

Some commands are very helpful during investigation but can output sensitive data. Do not put their raw output into tickets or chats.

| Command/Source | Risk |
| --- | --- |
| `jcmd <pid> GC.heap_dump ...` | A heap dump can contain passwords, tokens, payloads, and sensitive objects. |
| Core dump from kernel or debugger | Can contain all memory regions of the process. |
| `jcmd <pid> VM.system_properties` | System properties can contain credentials, URLs with tokens, or internal configs. |
| `jcmd <pid> VM.command_line` / JVM flags | Arguments can contain secrets passed directly on the command line or sensitive paths. |
| `cat /proc/<pid>/environ` or `ps eww` | Can print environment variables, including secrets. |
| Thread dump/JFR | Can contain classes, thread names, exceptions, endpoints, custom events, or application-supplied data. |
| Full-payload packet capture | Can contain tokens, cookies, request/response bodies, or personal data. |
| `strings` on checkpoint/core/heap dump | Can extract secret strings from binary memory artifacts. |

Do not run these commands routinely in production. If needed, there must be a specific investigative purpose, approval, secure storage location, and an owner responsible for handling the output. Do not paste output directly into general support channels.

## 7. When Are Thread Dumps, JFR, Heap Dumps, or Core Dumps Needed?

Choose artifacts based on the question that needs answering:

| Investigation Question | Preferred Evidence | Security Note |
| --- | --- | --- |
| Which callback is hung? | Callback timeline, reviewed thread dump, timeout logs | Thread names/stacks can reveal task names, paths, or endpoints. |
| Which lock is a thread waiting on? | Thread dump with lock information, lock wait logs | Share only relevant threads and redact unnecessary details. |
| Is JVM/GC under memory pressure? | GC logs, memory summary, container memory metrics | Avoid heap dumps if metrics/GC logs suffice. |
| What runtime events occurred before restore? | JFR recording with minimal event set | JFR can contain sensitive events depending on configuration and custom events. |
| Which object holds a reference or secret? | Heap dump in a restricted analysis environment | Extremely sensitive data; do not include in standard evidence packages. |
| Where did a native crash occur? | Core dump and native stack | Core dumps can contain all memory; access must be tightly restricted. |
| Which syscall/namespace error occurred? | CRIU logs, kernel logs, runtime events | Review PIDs, paths, mounts, and endpoints. |

The principle is to use the least sensitive evidence sufficient to answer the question. If thread dumps and callback logs already show `beforeCheckpoint` waiting indefinitely on `Future.get()`, a heap dump is usually not needed. If you only need to check memory pressure, GC logs and cgroup metrics may suffice.

### Thread Dump

Thread dumps are useful for finding deadlocks, blocked threads, or workers that failed to drain. However, stack traces and thread names can reveal internal classes, tenants, URLs, or job names. Review the contents before sharing and keep only relevant threads if possible.

### JFR

JFR can help analyze CPU, allocations, lock contention, GC, and socket events. Select only the required event set, limit recording duration, and inspect custom events. Do not assume JFR always contains only harmless metadata.

### Heap Dump and Core Dump

Create them only when the investigative question cannot be answered with less sensitive evidence. Store in a separate forensic area, encrypt, restrict permissions, log audit access, and do not attach to tickets/chats. Whenever possible, perform analysis in an isolated environment and do not copy raw dumps to personal machines.

## 8. Do Not Include Checkpoint Images in Ordinary Evidence Packages

An evidence package used for a ticket or operational report typically only needs:

- Timelines and correlation IDs.
- Reviewed JVM/CRIU/runtime logs.
- Version/build/platform metadata.
- Callback results and exception types.
- Readiness, dependency health, and resource metrics.
- Exit status/error code.
- Checksum of the checkpoint artifact, if needed to identify the exact artifact.
- Manifest describing package contents and redaction level.

Do not put the entire checkpoint directory into a log archive, do not attach heap/core dumps, and do not send images over email/chat. If a specialist needs to inspect the image, provide the artifact id or path in a restricted repository and grant access through a separate procedure. The recipient needs to know that this is sensitive memory data, along with the access purpose, retention period, and how to delete copies.

A checkpoint checksum can help identify an artifact without reading its contents. However, a hash is still metadata linking artifacts; avoid publishing it if it could reveal that two environments are using the same image or assist in correlating sensitive data. Include it in the package only when traceability is needed.

## 9. Redaction and Data Minimization

Redaction must be performed on a copy, keeping the original untouched in a restricted area. Do not edit original logs in place, as doing so can break the chain of custody.

Fields that typically need to be removed or replaced:

- `Authorization`, `Cookie`, `Set-Cookie`, API keys, and bearer tokens.
- Passwords, secrets, private keys, and connection strings containing credentials.
- Query parameters containing tokens or PII.
- Request/response bodies and SQL bind values.
- Emails, phone numbers, user ids, or tenant ids if not required for diagnosis.
- Hostnames, IPs, mount paths, and system usernames if considered restricted infrastructure information.
- PID/namespace ids if external reports do not need exact identifiers.

Redaction example:

```text
Before:
database_url=jdbc:postgresql://db-prod-17.internal:5432/orders
username=service_orders
password=SuperSecretValue
request_user=customer-918273

After:
database_endpoint=<DB_ENDPOINT_REDACTED>
username=<SERVICE_ID_REDACTED>
password=<REDACTED>
request_user=<SUBJECT_ID_REDACTED>
```

If you need to preserve the ability to correlate the same user/endpoint across multiple logs, use a controlled consistent pseudonym, such as `subject-<HMAC-prefix>`, with the HMAC key protected separately. Do not use an unkeyed hash for data with a small value space like email or user id if it can be reversed by dictionary attack.

Do not redact by blindly replacing every token-like string and thereby losing error codes or structures needed for diagnosis. Define the log schema, list of sensitive fields, and inspect samples after redaction. When unsure, keep the data in the restricted area and share only a summary.

## 10. Secure CRaC Callback Logging by Design

Structured logging reduces the need to extract raw memory. Each Resource should log events and metadata, not resource contents.

For example:

```java
logger.info(
    "crac_resource_before_checkpoint_complete resource={} durationMs={} status={}",
    "database-pool",
    durationMillis,
    "SUCCESS");
```

Avoid:

```java
logger.info("Database configuration: {}", databaseConfiguration);
logger.info("Request payload before checkpoint: {}", requestBody);
logger.info("Credential used by pool: {}", password);
```

Useful fields for callback logs:

- Stable attempt id and resource id containing no user data.
- Event name, phase, and result.
- Duration and timeout budget.
- Count of active requests/transactions/workers.
- Exception class and categorized error code.
- Dependency category and health status, not secrets/payloads.
- Readiness transition.

If an exception message might contain URLs, SQL, usernames, or payloads, log only the exception class and error code in shared logs. The full message can be stored separately with restricted permissions if genuinely required.

## 11. Selectively Collecting Process and Namespace Metadata

PIDs and namespaces help correlate JVM logs with CRIU/runtime logs, but they are ephemeral identifiers. A PID can be reused; the same process can have different PIDs in the host and container namespaces.

You may need to collect:

- Container PID and host PID if provided by the runtime.
- `NSpid`, `PPid`, and PID namespace mapping.
- Container ID, Pod UID, or workload identity.
- Namespace inodes and cgroup paths at the necessary level.
- Process start time and executable identity.

Do not store a standalone PID as a durable identity across restore. When sharing logs externally, you can replace PIDs with a label like `java-process-A` if actual numbers are unnecessary. Keep the full mapping in a controlled incident store so internal operations teams can still trace it.

Avoid collecting all of `/proc/<pid>/environ` or the command line if they may contain secrets. If you need to know whether a flag is enabled, extract only that flag name and strip sensitive values instead of sending the entire command line.

## 12. Collecting Dependency Evidence Without Exposing Payloads

When a dependency fails, usually only request/connection metadata is needed:

- Dependency logical name or pseudonym.
- Redacted host/port if necessary.
- Configured connect/read/query timeouts.
- Start/end times and duration.
- HTTP status, SQLState, broker error code, or exception class.
- Retry count, backoff, and circuit breaker state.
- Active/idle/pending connections in the pool and count of evicted connections.
- DNS lookup results at an approved disclosure level.
- TLS handshake outcome and certificate expiry metadata, not private keys.
- Readiness/health result.

You do not need to log raw SQL bind parameters, HTTP bodies, broker payloads, or secrets to prove a dependency timeout. For requests requiring correlation, use a random correlation id or HMAC pseudonym instead of real user identifiers.

## 13. Checksums, Manifests, and Chain of Custody

When retaining a checkpoint image or dump for forensic analysis, accurately identify which artifact was collected and whether it has been altered.

A manifest can record:

| Field | Purpose |
| --- | --- |
| Incident id | Links to the incident record. |
| Artifact id | Identifies the artifact in the restricted repository. |
| Source workload identity | Identifies the service/container without disclosing secrets. |
| Capture timestamp (UTC) | Time the evidence copy was created. |
| Original artifact timestamp | Time the checkpoint or dump was created. |
| SHA-256 | Verifies the integrity of the collected copy. |
| Collector identity | Service/personnel authorized to collect it. |
| Storage location/class | Storage location and data classification level. |
| Encryption key id | Reference to the encryption key, without containing the key itself. |
| Access/audit reference | Where reads/copies/restores are logged. |
| Redaction status | Original or redacted copy; applied tools/policies. |
| Retention/deletion date | Scheduled review and deletion time. |

Example creating a checksum for a packaged archive:

```bash
sha256sum checkpoint-evidence.tar > checkpoint-evidence.tar.sha256
sha256sum --check checkpoint-evidence.tar.sha256
```

The command only verifies the integrity of the archive file; it does not prove that the checkpoint is valid, safe, or compatible. Do not include private keys or encryption credentials in the same manifest.

The chain of custody should record which person/automation created, copied, decrypted, analyzed, or deleted the artifact, along with timestamp, reason, and storage location. When multiple copies exist, each copy must have a checksum and clear provenance relationship.

## 14. Storing Evidence Securely

The evidence store must have a level of protection commensurate with the data that may reside in the artifact:

- Encryption at rest and encryption in transit.
- Least-privilege access controls and dedicated service identities.
- MFA/approval for downloading raw checkpoints or dumps if supported by the system.
- Audit logs for reading, copying, downloading, decrypting, and deleting.
- Dedicated network boundary; no public buckets or broad shared folders.
- Shortest retention sufficient for incident investigation and legal requirements.
- Backup/replication of the evidence store under an approved policy.
- Encryption key management separated from artifact storage.
- Disallow automatic indexing of raw checkpoints/heap dumps into search systems or unapproved AI ingestion.

Do not use the same access permissions for ordinary logs and raw memory artifacts. Personnel needing to view timelines do not necessarily need permission to read heap dumps or checkpoint images.

## 15. Sharing Evidence in Tickets, Chats, and with Vendors

Before sending files out of the incident store, clearly identify what the recipient needs to know.

An ordinary technical ticket can receive:

- Error summary and redacted timeline.
- Filtered JVM/CRIU logs.
- JDK/CRaC/CRIU/kernel/runtime versions.
- Error codes, exception classes, and the last callback/resource.
- Metrics, readiness state, and checksums if needed.
- Reproduction steps without real data.

Do not send:

- The entire checkpoint directory.
- Raw heap dumps/core dumps.
- Unreviewed environment dumps, system properties, or command lines.
- Secrets, tokens, private keys, session cookies.
- Real request/message/database payloads unless necessary.

If a vendor requires a raw artifact, use an organization-approved secure upload channel, agree on usage scope and retention, restrict who can access it, and record the artifact id. Do not transfer files through personal email or ordinary chat.

## 16. Step-by-Step Evidence Collection Workflow

A workflow that can be applied to checkpoint/restore incidents:

### Step 1: Record the Incident and Preserve State

- Create an incident id and a checkpoint/restore attempt id.
- Record the UTC timestamp, workload identity, build, and environment.
- Record process/container state before restarting or cleaning up.
- Avoid deleting checkpoints, logs, or staging directories before knowing whether they relate to the incident.

### Step 2: Collect Group A Evidence

- JDK/CRaC/CRIU/kernel/container runtime versions.
- Exit code, error code, and exception class.
- Callback timeline, duration, timeout budget, and readiness transitions.
- Memory/cgroup/disk metrics and dependency health.
- Artifact id and checksum if needed.

### Step 3: Collect Group B Logs

- Copy JVM, CRIU, runtime, and application logs to the incident store.
- Keep the original read-only.
- Create a working copy and run redaction.
- Inspect output manually or with DLP tools before sharing.

### Step 4: Identify Remaining Questions

For example: which callback hung, which thread holds a lock, where did a native crash occur, or which object still holds an old credential? Choose the next artifact based on that question; do not dump full memory right at the start.

### Step 5: If a Raw Memory Artifact Is Needed

- Clearly document the reason and approver.
- Create the artifact in separate forensic storage.
- Encrypt immediately upon collection or before leaving the host.
- Hash and record the manifest/chain of custody.
- Restrict analysts and access duration.
- Do not copy to tickets/chats; share the artifact id or use a dedicated channel.

### Step 6: Create the Redacted Evidence Package

Include only necessary files, the manifest, checksums, and a description of the redaction level. Verify that no temporary files, secrets, or raw dumps leaked into the archive.

### Step 7: Closure and Cleanup

When the incident closes, review retention, revoke temporary permissions, and delete working copies and artifacts no longer needed per policy. Log audit events and confirm that staging copies have been handled.

## 17. Minimal Evidence Package Structure

An evidence package used for standard investigation can be organized as follows:

```text
incident-<id>/
├── README.txt                 # Incident summary and redaction level
├── manifest.json              # Artifact id, timestamp, version, checksum
├── timeline.csv               # UTC time, attempt id, event, result, duration
├── runtime-versions.txt       # JDK, CRaC, CRIU, kernel, container runtime
├── application-redacted.log   # Reviewed log copy
├── jvm-redacted.log           # Reviewed JVM log
├── criu-redacted.log          # Reviewed CRIU/runtime log
├── dependency-health.csv      # Status, latency, error class, retry count
├── resource-lifecycle.csv     # beforeCheckpoint/afterRestore outcomes
└── checksums.txt              # Checksums of files in the package
```

There are no `checkpoint/`, `heapdump/`, or `core/` directories in a standard package. If a raw artifact is collected, it resides in a separate forensic repository and the manifest only references the artifact id, checksum, and access permissions.

Example `timeline.csv`:

```csv
timestamp_utc,attempt_id,event,resource,result,duration_ms
2026-11-13T09:00:00.120Z,cp-7f2a,readiness,application,REFUSING_TRAFFIC,
2026-11-13T09:00:00.145Z,cp-7f2a,beforeCheckpoint,db-pool,STARTED,
2026-11-13T09:00:00.390Z,cp-7f2a,beforeCheckpoint,db-pool,SUCCESS,245
2026-11-13T09:00:01.900Z,cp-7f2a,checkpoint,process,FAILED,
```

The identifiers and timestamps in the example are synthetic data. Do not put real customer ids, tokens, or endpoints into CSV files unless necessary.

## 18. Handling Situations Requiring a Heap Dump or Core Dump

Some errors can only be identified by analyzing the object graph or native memory. In that case:

1. Clearly define the forensic question, such as which object retains a secret, which native allocation caused a crash, or which thread state cannot be observed from logs.
2. Assess the feasibility of collecting less sensitive evidence first.
3. Select the right process and timing; note the impact of taking a dump on latency, disk, and the process.
4. Ensure sufficient storage space and restricted permissions.
5. Generate the dump using the procedure of the JDK/debugger/platform in use.
6. Encrypt and hash the artifact; record the collector, timestamp, process identity, and tool version.
7. Analyze in an isolated environment; do not open the dump with tools or services that automatically upload data externally.
8. Extract only the necessary objects/stacks/fields, and redact before putting results into reports.
9. Delete working copies and temporary artifacts according to the retention policy.

A heap dump or core dump can be very large and cause pauses, I/O pressure, or process impact. Do not take dumps across all instances simultaneously just because one instance failed. Choose a representative instance or a reproduction environment if possible.

## 19. Do Not Alter Evidence During Investigation

Cleanup or restart operations can destroy necessary evidence:

- Deleting an incomplete checkpoint directory before saving logs.
- Restarting a container, losing `/proc` state, PID mappings, and transient runtime logs.
- Rotating logs before copying relevant files.
- Running automated cleanup that deletes staging artifacts during investigation.
- Opening/unpacking a checkpoint on an incompatible host and then overwriting or altering its contents.
- Redacting the original file directly and losing the ability to compare.

When preserving current state is needed, snapshot/copy using a platform-supported method, store the original read-only, and perform analysis on the copy. Do not keep a failing process in a dangerous state solely to preserve evidence; prioritize safety and service continuity per incident procedures while recording the actions taken.

## 20. Retention and Secure Deletion

Raw checkpoints, heap dumps, and core dumps should not be kept indefinitely. They may continue to contain secrets even after credentials have been rotated.

The retention policy should specify:

- Artifact type and classification level.
- Responsible incident/owner.
- Investigation purpose and duration.
- Personnel authorized to read or decrypt.
- Legal hold or preservation requirements, if any.
- Review date and deletion date.
- How to verify deletion of copies, archives, staging files, and replicas.

Deleting an object in versioned object storage may only create a delete marker; snapshots or replicas may also retain copies. If secure deletion is required, use storage-provided mechanisms such as version deletion, crypto-erasure, or key revocation per policy, and document the actual scope. Do not claim data has been physically erased if the storage system does not provide that guarantee.

## 21. Common Mistakes When Collecting Evidence

| Mistake | Risk | Proper Approach |
| --- | --- | --- |
| Attaching checkpoint to a ticket | Exposes tokens, passwords, sessions, and heap data | Send only artifact id/checksum; keep raw image in restricted forensic store. |
| Sending heap dump over chat | Recipients and storage systems may not be authorized to access the data | Use forensic procedures and approved transfer channels. |
| Printing all environment/system properties | Secrets may reside in variables or properties | Collect an allowlist of fields; do not dump everything. |
| Keeping only redacted logs, discarding originals | Loses ability to audit and verify redaction | Keep originals read-only in a restricted store. |
| Redacting the original file directly | Breaks chain of custody | Redact on a working copy. |
| Collecting only the last log line | Misses the first error and callback sequence | Collect timeline around the entire attempt. |
| Relying on a standalone PID | Confuses processes due to namespaces or PID reuse | Combine container identity, namespace, and process start time. |
| Hashing without recording provenance | Unknown which artifact/attempt the checksum belongs to | Tie hashes to manifest, timestamp, and artifact id. |
| Using unfiltered log messages containing full exceptions | Messages may contain URLs, SQL, or payloads | Record exception class/error code; store details separately if needed. |
| Keeping raw dumps indefinitely | Secrets remain long after the incident ends | Enforce retention, access reviews, and deletion procedures. |

## 22. Checklist Before Sharing an Evidence Package

- [ ] Each file serves a specific investigative purpose.
- [ ] Incident id, checkpoint/restore attempt id, and UTC timestamps are included.
- [ ] Necessary version/build/platform metadata has been collected.
- [ ] Callback timeline and dependency states are included.
- [ ] JVM/CRIU/runtime logs have been reviewed.
- [ ] No passwords, tokens, private keys, cookies, or connection strings containing secrets are present.
- [ ] No unnecessary request/response bodies, SQL bind values, or broker payloads are present.
- [ ] No raw checkpoints, heap dumps, or core dumps are in the standard package.
- [ ] Thread dumps/JFR/packet captures have been classified and redacted if used.
- [ ] PIDs, paths, hostnames, IPs, and tenant identifiers have been handled per policy.
- [ ] Originals are kept read-only in a restricted store.
- [ ] Shared copies were produced from a working copy with redaction documented.
- [ ] Checksums/manifests accurately link artifacts and attempts.
- [ ] Evidence archive is encrypted and accessible only to required recipients.
- [ ] Retention/deletion date and owner are recorded.
- [ ] Archive has been checked to ensure no temporary files or unintended dumps are included.

## 23. Conclusion

A CRaC checkpoint can contain sensitive data in memory; heap dumps and core dumps carry a similar level of risk. Incident investigation should begin with timelines, callback logs, runtime versions, error codes, dependency health, metrics, and checksums. This evidence is usually sufficient to determine whether the failure belongs to the prepare, dump, restore, or reconnect step without extracting memory contents.

Collect raw checkpoints or memory dumps only when there is a specific forensic question and an approved procedure. Keep originals read-only in a restricted repository, create redacted copies for sharing, encrypt data, record checksums/manifests and chain of custody, and apply retention/deletion per policy. Do not put raw checkpoints, heap dumps, core dumps, environment dumps, or system properties into ordinary tickets/chats. Allowlist-based collection and data minimization give engineering teams sufficient evidence without exposing secrets or user data.