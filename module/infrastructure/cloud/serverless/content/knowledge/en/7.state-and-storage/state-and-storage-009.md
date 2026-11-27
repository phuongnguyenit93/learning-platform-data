# TTL, Data Lifecycle, and Temporary Resource Cleanup

Serverless applications frequently generate time-bounded data and resources: cache entries, idempotency keys, sessions, locks, temporary files, intermediate objects, job results, access tokens, retry records, and staging data. Without defining when they lose validity and how to reclaim them, systems accumulate stale data, inflate storage costs, retain sensitive information longer than necessary, or let temporary resources occupy space.

**Time to live (TTL)** is the duration for which a piece of data or resource is considered valid. When the TTL expires, the data is considered expired under application policy. However, the moment of logical expiration and the moment of physical deletion can differ. Many services perform deletions asynchronously, in batches, or lazily upon access.

Data lifecycle design must answer three questions: how long does data remain valid, how must the system behave once it expires, and which component is responsible for cleanup? In Java serverless, you must also account for execution environments being reused or reclaimed at any time. Function memory and temporary disk are not durable storage, and in-code cleanup cannot be the sole mechanism for data that must be guaranteed deleted.

## 1. TTL, expiration, retention, and deletion

These terms are related yet express distinct policies:

- **TTL:** the duration a record, key, or resource is permitted to exist or remain valid.
- **Expiration:** the moment data is no longer considered valid under application rules.
- **Retention:** the duration an organization or system keeps data before it is permitted or required to be deleted.
- **Deletion:** the action of removing data from a specific storage system.
- **Purge:** the policy-driven process of removing data across all covered locations and copies, potentially including indexes, replicas, backups, or archives as required.

For example, a report download link might have a 15-minute TTL. After that point, the API must reject the link even if the object still sits in object storage. A lifecycle rule might delete the object after 7 days. Thus, link expiration and object deletion are two distinct events.

Similarly, audit data might require multi-year retention even when the application rarely accesses it anymore. Do not attach a short TTL to data merely because it no longer appears on a user screen.

| Concept | Primary question | Example |
|---|---|---|
| TTL | How long before data loses validity? | Cache key has a 10-minute TTL |
| Expiration | Past what point must the app reject data? | Token expires at 12:00 UTC |
| Retention | How long must data be kept? | Audit records retained for 3 years |
| Deletion | When and where is data removed? | Deleting expired objects |
| Purge | Which copies are within deletion scope? | Deleting a record and its policy-governed copies |

Never assume that once TTL lapses, data vanishes immediately from disk. Check the semantics of the service you use: some caches make keys inaccessible immediately upon expiration; some databases mark items expired and delete them in the background; object storage lifecycle rules typically run asynchronously; backups may retain copies until the backup cycle ends.

## 2. Classifying data before setting TTLs

Never apply a single blanket TTL across the entire application. Each data type has different purposes, sensitivity levels, recovery needs, and costs.

| Data type | Purpose | Typical lifecycle policy |
|---|---|---|
| Cache | Reduce repeated queries or computation | Short TTL; regenerable |
| Session or token | Maintain session and access rights | Time-bounded expiration, revoke when needed |
| Idempotency record | Prevent duplicate execution of business actions | Retain at least across the retry/replay window |
| Distributed lock or lease | Coordinate temporary execution ownership | Time-bounded with renewal mechanism |
| Job state | Track asynchronous work | Keep long enough for client lookup and ops |
| Temporary file/object | Intermediate processing or download artifact | Delete after completion and download window closes |
| Logs and traces | Diagnostics, auditing | Governed by retention and data protection rules |
| Audit/business records | Business history | Governed by retention, legal, and business policies |
| DLQ messages | Error investigation and recovery | Retain long enough for handling; include redrive workflow |
| Backups/archives | Recovery or long-term archival | Governed by backup schedule, retention, and purge workflow |

A record may no longer be needed for online flows yet remain required for reconciliation or auditing. Identify data ownership, usage purpose, sensitivity level, creation source, replication targets, and deletion conditions before setting a TTL.

Model lifecycles using business states rather than a single timestamp. For instance, a report might transition through `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `EXPIRED`, and `DELETED`. Each state defines who can read, download, or cancel outputs; the TTL for job metadata can differ from the TTL for the report file.

## 3. Representing expiration timestamps consistently

For data living beyond a single invocation, store an absolute expiration timestamp rather than a remaining-seconds counter in memory. An absolute timestamp lets multiple functions, workers, and cleanup jobs share a single rule.

Key principles:

- Store timestamps in UTC to avoid host timezone dependencies.
- Use a time type with appropriate precision, such as `Instant` in Java.
- Define the TTL start anchor clearly: creation, last access, completion, or issuance.
- Never accept an arbitrary `expiresAt` from clients for security-sensitive data; the server must compute it from policy.
- Define the comparison rule: data is expired when `expiresAt <= now`.
- Keep system clocks synchronized; avoid relying on untrusted local clocks for distributed decisions.
- Never overload a timestamp field for multiple meanings.

Example record:

~~~json
{
  "id": "job-91ac",
  "status": "SUCCEEDED",
  "createdAt": "2026-11-17T10:00:00Z",
  "completedAt": "2026-11-17T10:03:12Z",
  "expiresAt": "2026-11-24T10:03:12Z"
}
~~~

In this example, the job is retained for 7 days after completion. Expiration is computed from `completedAt` because users need time to download outputs after the job succeeds. If computed from creation time, a long-running job could expire the moment it finishes.

TTLs can be fixed or sliding:

- **Fixed TTL:** the expiration timestamp is determined at creation and never shifts on access. Fits tokens, time-limited download links, and temporary data needing a hard max age.
- **Sliding TTL:** on each valid access, the expiration timestamp extends. Fits certain activity-based sessions or caches, yet still needs a maximum lifetime cap to prevent indefinite extension.

With sliding TTL, updating expiration must be atomic or concurrency-controlled. If two concurrent requests write different timestamps, the older request could inadvertently shorten the newer TTL. Use conditional updates so expiration extends only when the new value exceeds the current one and stays within maximum lifetime.

## 4. TTL expiration does not mean immediate deletion

Many systems decouple expiration checks from physical data cleanup. This avoids scanning and deleting every record on the exact second it expires, while creating a lag between the two events.

A typical lifecycle:

~~~mermaid
flowchart TD
    A["Create data"] --> B["Set expiresAt / TTL"]
    B --> C["Data still valid"]
    C --> D{"Expired yet?"}
    D -->|"No"| C
    D -->|"Yes"| E["App rejects or marks expired"]
    E --> F["Cleanup worker / lifecycle service"]
    F --> G{"Delete succeeded?"}
    G -->|"Yes"| H["Removed from target store"]
    G -->|"No"| I["Retry or route to error queue"]
    I --> F
~~~

Two moments must be tracked:

1. **Logical expiration:** the application no longer permits using the data.
2. **Physical deletion:** the storage service actually removes the data via its own mechanism.

If access must end the moment TTL expires, you cannot rely solely on background cleanup. APIs and domain services must check `expiresAt` before returning or using data. Physical cleanup can follow later.

For instance, a signed URL naturally loses validity via its signature and expiration timestamp even before the object is deleted. Conversely, if you only attach TTL metadata while an endpoint serves the object without checking expiration, the data remains accessible past its intended expiration.

Never use TTL as a precision timer to trigger business logic at an exact moment. When you need scheduled notifications or timed actions, use a scheduler, delayed queue, or workflow timer. Those mechanisms can still deliver events late or twice, so handlers must remain idempotent.

## 5. TTL in databases and key-value stores

There are several ways to implement TTL in databases. Some services support a TTL attribute and automatically delete expired items; some databases use TTL indexes; some key-value stores support expiration directly on keys; other systems require a scheduled cleanup worker.

### Storing expiration timestamps in records

A general approach is adding an `expiresAt` field:

~~~json
{
  "id": "idem-4e9f",
  "tenantId": "tenant-42",
  "eventId": "evt-8f31",
  "status": "COMPLETED",
  "expiresAt": "2026-11-24T10:15:30Z"
}
~~~

On read, the application checks expiration:

~~~java
public boolean isExpired(Instant expiresAt, Instant now) {
    return expiresAt != null && !expiresAt.isAfter(now);
}
~~~

The condition above means a record is expired when `expiresAt` is equal to or before `now`. Checking at the application layer guarantees expired records are not used simply because physical deletion has not run yet.

### Database TTL or TTL indexes

If the database supports native TTL, the application writes an expiration field and lets the service purge items in the background. Verify:

- Required data type and unit for the field (seconds, milliseconds, or timestamp).
- How frequently the service scans for expirations.
- Whether expired items remain readable during a lag window.
- How TTL interacts with compound indexes or partition keys.
- Whether deletions emit events, and whether those events can arrive late or duplicate.
- Whether TTL applies to replicas, backups, and exports.

TTL indexes are usually asynchronous cleanup mechanisms and should not be treated as authorization checks or transaction constraints. If expired data must not be used, application-level checks remain mandatory.

### TTL in caches

Caches typically support per-key TTL directly. TTL bounds how long stale data survives and prevents unbounded cache growth. However, cache expiration can expire many popular keys simultaneously and trigger a cache stampede as concurrent requests reload data at once.

Add small jitter to TTLs to stagger expirations, and use request coalescing or stale-while-revalidate if business rules allow. Never cache sensitive or tenant-specific data under inadequately scoped keys. Caches are not the single source of truth; if a cache is wiped, the application must be able to reload from durable storage.

## 6. TTL for idempotency keys, sessions, and distributed leases

Some data carries expiration because it protects a distributed process.

### Idempotency records

Idempotency records prevent the same business intent from executing multiple times. TTL must span at least the full window during which clients, gateways, brokers, or operators can retry/replay. If records expire too early, a retried old request can create a duplicate order or transaction.

Distinguish API request timeouts from idempotency record retention. For example, an API may have a 30-second timeout while clients can retry for 24 hours; idempotency records must be retained across that 24-hour retry window or longer depending on business risk.

### Sessions and tokens

Tokens carry an `exp` claim defining when they lose validity. Servers must validate expiration and relevant claims on every request. Session records may be purged in the background after expiring, yet authorization must never depend on whether cleanup has run yet.

With sliding sessions, updating last-access or expiry must enforce a hard maximum lifetime. On logout or permission revocation, use explicit revocation or versioning; waiting for TTL expiration is often too slow.

### Distributed locks and leases

Locks coordinate work across multiple workers. A lock TTL lets the system recover if a worker crashes without releasing the lock. However, an old worker may keep running after its lease expires and a new worker has already acquired the lock.

Checking whether a lock is still valid is insufficient to stop an old worker from overwriting results. For protected resources, use fencing tokens or monotonically increasing versions. Each new lease issuance hands out a higher token; the data store rejects writes carrying an older token. This stops a worker whose lease lapsed from overwriting a newer worker's updates.

Lease renewals must use compare-and-set or conditional updates bound to the owner token. Never renew solely by lock name, or an old worker could accidentally extend a lock now held by a different worker.

## 7. Object and file lifecycles in object storage

Files created during serverless processing often need distinct lifecycles. Examples include unverified uploads, resized images, exported reports, import staging files, or intermediate workflow objects.

One organization pattern separates prefixes by purpose:

~~~text
uploads/quarantine/{tenantId}/{uploadId}
processing/{jobId}/input
processing/{jobId}/intermediate
reports/{tenantId}/{jobId}/result
archive/{year}/{month}/...
~~~

Prefix naming makes lifecycle rules, access policies, and observability easier. However, prefixes are not security boundaries; IAM and authorization by bucket, object, and tenant are still required.

A file lifecycle might look like:

1. Client uploads to `quarantine` with size caps and restricted write permissions.
2. Function verifies file type, content, size, and ownership.
3. Validated files are moved or written to `processing`.
4. Workers produce intermediate and output objects.
5. Job metadata updates upon completion.
6. Temporary files are deleted once no remaining steps need them.
7. Outputs are retained for the download window or business policy duration.
8. Lifecycle rules purge leftover objects and incomplete multipart uploads.

Object storage lifecycle rules typically execute asynchronously. When versioning is enabled, deleting an object may create only a delete marker while older versions remain. Configure separate rules to purge noncurrent versions or delete markers per policy. Incomplete multipart uploads also hold data and accrue charges; configure automatic abort of incomplete multipart uploads if supported by the service.

For sensitive objects, never rely solely on lifecycle rules to block access. Once expired, APIs must deny downloads, revoke access, or stop issuing signed URLs. Lifecycle rules handle physical cleanup on the service's schedule.

## 8. Temporary resources inside Java functions

Java functions may create temporary files, buffers, streams, archives, or intermediate artifacts. Some platforms provide a local temporary directory such as `/tmp`. Data stored there can persist across reused execution environments, yet vanish when the environment is reclaimed.

Therefore:

- Never store unique business data solely in a temporary directory.
- Never assume the temporary directory is wiped clean after each invocation.
- Generate unique filenames or subdirectories per invocation.
- Restrict permissions appropriately; avoid exposing sensitive payloads to unrelated processes.
- Close streams and delete files in `finally` blocks or try-with-resources.
- Have a strategy for orphaned files if an invocation is killed before cleanup runs.
- Monitor temporary disk usage and cap input sizes.

Example creating and deleting a temporary file:

~~~java
Path tempFile = Files.createTempFile("report-", ".csv");

try {
    try (BufferedWriter writer = Files.newBufferedWriter(
            tempFile, StandardCharsets.UTF_8)) {
        reportWriter.writeCsv(writer);
    }

    objectStorage.upload(tempFile, destinationKey);
} finally {
    try {
        Files.deleteIfExists(tempFile);
    } catch (IOException cleanupError) {
        logger.warn("Could not remove temporary report file", cleanupError);
    }
}
~~~

This example assumes `reportWriter`, `objectStorage`, `destinationKey`, and `logger` are provided by the application. The `finally` block executes during normal Java control flow, but is not guaranteed to run if the runtime is killed abruptly, the host fails, or the environment is forcibly reclaimed.

When creating multiple files for one invocation, create a dedicated directory with `Files.createTempDirectory`, place all child files inside it, and recursively delete it on completion. When cleaning orphaned files, scan only the application-owned namespace and remove directories older than a safety threshold; take care never to delete files belonging to concurrent invocations. A timed lease or marker can distinguish active directories from abandoned ones.

Never use a fixed filename like `/tmp/report.csv` across requests. If the environment allows concurrency, invocations can overwrite each other's files. Even with sequential execution, reused environments can retain old content if the next run fails to overwrite the entire file.

## 9. Cleanup must be fault-tolerant and safe to re-run

Cleanup is distributed work and can fail just like any business task. An object-delete API call can time out after the object was already removed; a worker can be retried; a record may already have been cleaned by another process.

Therefore, cleanup workers must be idempotent:

- Deleting an already-absent resource should count as complete if service semantics permit.
- Record cleanup status via conditional updates or versions so newer state is not overwritten.
- Use small batches, bounded retries, and backoff for transient errors.
- Classify permanent errors such as permission denied or resource ownership mismatch to raise alerts.
- Never delete a resource if owner, tenant, or version mismatches.
- Record last attempt timestamp, retry count, and last error.
- Route unrecoverable cleanup failures to a DLQ or investigation queue.

For example, a cleanup worker reads a record's `expiresAt`, then re-checks right before deleting. If a user just extended the resource, the older worker must not delete the renewed data. Use conditional deletes requiring `expiresAt` to still equal the read value and `version` to be unchanged.

A safe deletion flow:

~~~mermaid
flowchart TD
    A["Find records with expiresAt <= now"] --> B["Read owner and version"]
    B --> C["Re-check policy and status"]
    C --> D{"Still expired and matching owner?"}
    D -->|"No"| E["Skip; data renewed or modified"]
    D -->|"Yes"| F["Conditional delete / purge"]
    F --> G{"Outcome?"}
    G -->|"Succeeded or already gone"| H["Record completion"]
    G -->|"Transient error"| I["Retry with backoff"]
    G -->|"Permission / invalid error"| J["Quarantine and alert"]
~~~

For multi-step cleanup, persist progress state so work can resume after a crash. For instance, deleting an object, removing metadata, revoking a signed URL, or updating job status may not share a single transaction. Make every step safely re-runnable without harmful side effects.

## 10. Scheduling cleanup: TTL engines, sweepers, and event triggers

Three common patterns clean up expired data.

### Native service TTL engines

Databases, caches, or object storage may provide built-in expiration or lifecycle rules. The upside is minimal code and no manual full-data scans. The downside is deletion timing is rarely exact to the second, and event emission and semantics vary across services.

Use a native TTL engine when expired data can be purged within an acceptable lag window and the application still enforces logical expiration.

### Scheduled sweepers

A scheduled function runs periodically, queries records where `expiresAt <= now`, and deletes them in batches. This is flexible when multiple steps, auditing, or business conditions are needed. It requires an index on expiration timestamp, batch limits, checkpoints, and concurrency control to avoid full table scans or multiple sweepers processing the same record.

If a sweeper runs every 5 minutes, data may remain physically stored for roughly 5 minutes or longer during backlogs. Never advertise second-accurate TTL if physical cleanup runs only periodically.

### Event-driven cleanup

A scheduler or workflow can emit an event at expiration time to trigger cleanup. This fits smaller resource volumes or processes with explicit workflows. However, timers/events can arrive late, repeat, or fail. Handlers must check current state and be idempotent before deleting.

For large resource volumes, emitting one event per item can generate substantial cost and load. Prefer native TTL engines or batched sweepers instead.

### Combining mechanisms

A common design uses a native TTL engine to purge the bulk of data alongside a periodic sweeper to catch missed items, failed cleanups, or resources outside automatic TTL scope. Avoid letting two deletion mechanisms race without conditional checks.

## 11. Backups, replicas, logs, and data deletion requirements

Deleting a record from the primary table does not mean every copy of the data has disappeared. Data may still reside in:

- Read replicas or cross-region copies.
- Backup snapshots and point-in-time recovery logs.
- Exports, data lakes, or analytics stores.
- Logs, traces, metric labels, or error reports.
- Caches and CDNs.
- DLQs, event streams, or archives.
- Temporary files and old object versions.

Retention policies must specify retention windows and handling for each copy. Some backups remain until their backup cycle expires; some systems support crypto-shredding by destroying encryption keys by design. These are architectural and data-governance decisions that cannot be inferred solely from a primary table's TTL.

Avoid writing sensitive payloads to logs unnecessarily. Use reference IDs, redact fields, or minimize logged data. When a deletion request spans multiple systems, build a deletion workflow tracking target systems, per-step status, retries, and completion proof. Where legal holds or mandatory retention apply, policies must define exception handling before purging.

Nor does TTL replace minimum retention policies. Data required for contracts, accounting, or audits may not be deleted immediately when the application stops using it. Conversely, unnecessary personal data should not be retained indefinitely merely because storage is cheap.

## 12. Cost and operational impact of data lifecycles

Storage costs typically depend on capacity, retention duration, access counts, cleanup requests, replication, backups, and data transfer. Forgotten temporary data can accrue ongoing charges long after losing business value.

When designing TTLs, evaluate:

- Average size per record or object.
- Volume of newly created data per day.
- Average TTL and retention distribution.
- Index query costs to locate expired data.
- Delete request and lifecycle operation costs.
- Replica, version, and backup footprint.
- DLQ, log, and archive storage costs.
- Recompute or recovery costs if TTL is too short.

A shorter TTL is not always cheaper. If data must be regenerated repeatedly, compute and dependency costs can rise. An overly short cache TTL can cause cache stampedes; an overly short job TTL prevents users from downloading results; an overly short idempotency TTL can allow duplicate side effects.

An overly long TTL also carries impact: accumulating storage, wider data exposure windows, bloated indexes, and larger cleanup backlogs. Measure both storage costs and regeneration/operational costs.

## 13. Testing TTL and cleanup

TTLs are hard to test if tests must wait in real time. Separate expiration calculation from the system clock and inject `Clock` in Java to test with fixed timestamps.

Example:

~~~java
public final class ExpirationPolicy {
    private final Clock clock;

    public ExpirationPolicy(Clock clock) {
        this.clock = clock;
    }

    public Instant expiresAfter(Duration ttl) {
        if (ttl.isNegative() || ttl.isZero()) {
            throw new IllegalArgumentException("TTL must be positive");
        }
        return clock.instant().plus(ttl);
    }

    public boolean isExpired(Instant expiresAt) {
        return expiresAt != null
                && !expiresAt.isAfter(clock.instant());
    }
}
~~~

In tests, use `Clock.fixed` to verify behavior before expiration, right at expiration, and after expiration without waiting. Scenarios to test:

1. Unexpired data is read normally.
2. Data right at `expiresAt` is treated as expired.
3. Expired data is never returned even if cleanup has not run yet.
4. Running cleanup twice causes no errors or duplicate side effects.
5. Stale cleanup never deletes a recently renewed resource.
6. Transient delete errors retry; permission errors trigger alerts.
7. Invocations killed mid-cleanup can still resume cleanly.
8. Temporary files are removed both on success and on exceptions.
9. Orphaned files are never deleted while another invocation still uses them.
10. Backups, object versions, DLQs, and logs honor their own retention rules.

Do not test only `expiresAt` logic. Run integration tests against real services or compatible emulators to verify TTL units, cleanup lag, version handling, and batch limits.

## 14. TTL and data lifecycle design checklist

Before deploying, answer:

1. Why is the data created and who owns it?
2. When does the data expire? Does TTL start from creation, completion, or last access?
3. Is it a fixed TTL or sliding TTL? Is there a maximum lifetime cap?
4. Are UTC timestamps and TTL units aligned with the service contract?
5. Does the application check logical expiration before reading or using data?
6. Does the service delete physically immediately or asynchronously? How much cleanup lag is acceptable?
7. Does TTL accommodate retries, replays, idempotency, and recovery windows?
8. Is cleanup idempotent, using conditional deletes and protecting against renewal races?
9. Do temporary files/objects have clear prefixes, owners, retention, and lifecycle rules?
10. Does the Java function delete files in `finally` and handle orphaned files?
11. Do backups, replicas, logs, caches, DLQs, and object versions have dedicated policies?
12. Are there legal holds or minimum retention obligations that override TTL?
13. Are metrics tracked for expired data, cleanup lag, cleanup failures, and accumulated storage?
14. Are alerts configured when cleanup backlogs grow or temporary resources cross thresholds?
15. Have concurrency, retries, killed invocations, and repeated cleanup runs been tested?

## Conclusion

TTL defines how long data or resources remain valid; retention defines how long the system keeps data; expiration and physical deletion can occur at different times. Because many services purge data asynchronously, applications must reject expired data themselves and rely on cleanup workers or lifecycle rules for policy-driven physical deletion.

In Java serverless, store absolute expiration timestamps, choose TTLs by data purpose, keep idempotency records long enough for retries/replays, use fenced leases when coordination is required, and clean up temporary files within invocation scope. Cleanup must be safely re-runnable, with retries, conditional deletes, and observability. A clear data lifecycle lowers costs, limits how long sensitive data persists, and ensures functions can recover whenever execution environments are reclaimed.
