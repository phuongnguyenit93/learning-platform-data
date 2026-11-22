# Log Deletion on Request — Privacy in Java Logging

## 1. What Is Log Deletion on Request?

Java application logs contain operational events, errors, request traces, security information, and sometimes **personal data**. “Log deletion on request” is the process of receiving a data request, verifying authorization, locating relevant records across the entire logging system, evaluating which data must be deleted or legitimately retained, executing technical measures, and then **verifying and responding within the accurate scope**.

Some examples:

~~~text
INFO  orderId=42 userId=user-7 outcome=SUCCESS
ERROR request failed email=person@example.invalid
INFO  healthcheck status=OK
AUDIT userId=user-7 action=ROLE_CHANGED result=SUCCESS
~~~

You cannot simply delete lines containing `userId=user-7` and declare completion: the same subject may appear via email, IP, `deviceId`, or transaction ID. An audit line for a role change may fall under data that must be retained due to legal obligations or appropriate investigations. And even after deleting application files, a copy may already exist in a log collector, search index, archive, backup, or export file.

**The right goal:** protect personal data without accidentally deleting another subject's events, without destroying evidence that must be preserved, and without reporting “all deleted” when only part of the pipeline has been processed.

**Not a built-in SLF4J feature:** `logger.info()`, `logger.error()` calls, or Logback/Log4j 2 Appenders do not have a generic method to selectively delete an event already written to every sink. This is a data lifecycle management problem across the entire pipeline.

## 2. Identifying Personal Data That May Appear in Logs

| Data Type | Examples | Scoping Notes |
| --- | --- | --- |
| Direct identifiers | email, userId, phone number, name | Usually linkable to a specific subject |
| Indirect identifiers | IP, deviceId, sessionId, correlationId | Can re-identify when combined with other systems |
| Business metadata | orderId, documentId, accountId | Depends on linkability through business data tables |
| Error content | exception message, request URL, query string | Easy to accidentally log PII in free-form message fields |
| Security/audit data | login attempts, role changes, access denied | May require justified retention and restricted access |
| Log copies | stdout, rotating files, search index, snapshot, archive | The same event exists in multiple places |

**Hashing `userId` does not automatically make it anonymous.** If a mapping table or linking key still exists, or if the identifier can be guessed and combined with other data, re-identification risk remains. Pseudonymization reduces direct identifiability, but does not always satisfy full erasure/anonymization requirements.

Do not log passwords, access tokens, API keys, session cookies, full payment data, or raw request bodies containing sensitive information in the first place. Once information has been collected or exported externally, deleting it later cannot prevent someone who already read it from remembering or keeping their own copy.

## 3. Legal Basis and Cases Requiring Retention

The right to request deletion **does not mean the right to delete all evidence in every situation**. Deciding whether to delete, restrict processing, or retain records must be based on applicable law, processing purpose, retention obligations, incident history, and approved policies.

**Vietnam, as of 2026:** The Law on Personal Data Protection **91/2025/QH15**, effective **01/01/2026**, recognizes rights related to personal data, including the right to request deletion. Article 14 addresses deletion, destruction, and de-identification of data; when applying it, relevant cases and limitations must be reviewed, including Article 19. **Decree 356/2025/NĐ-CP**, effective on the same date, details several articles and implementation measures. Organizations must review specific responsibilities, procedures, and timelines under applicable law rather than setting a single fixed period for all log types.

**If GDPR applies:** **GDPR Article 17** establishes the right to erasure when grounds apply, but it is not an absolute right; exceptions may include processing necessary for compliance with a legal obligation or for the establishment, exercise, or defense of legal claims. Article 19 also relates to notifying recipients of the data where applicable.

This is technical knowledge on system design and **does not replace decisions by legal counsel**. In particular, do not use “audit” as a blanket exemption for all logs: you must determine **which fields must be kept, for how long, and on what basis**.

### Sample Decision Matrix

| Log Set | Handling Approach After Assessment |
| --- | --- |
| DEBUG/INFO containing PII whose purpose has expired | Verified deletion or de-identification |
| Technical errors still needed for time-bounded investigation | Restrict access, retain minimally, delete on schedule |
| Audit/security under valid retention obligation | Keep only what is genuinely needed, protect it, and set a review milestone |
| Another person's data in the same record | Do not blindly delete the whole record if it causes out-of-scope data loss |
| Copies already shipped to collector/index | Process at the destination, not only in the source file |
| Backups that cannot be safely modified | Apply lifecycle policy and a mechanism to prevent data resurrection after restore |

When only partially completed, the status must be **PARTIAL_RESTRICTED** or an equivalent status—never COMPLETED.

## 4. Business Workflow from Request to Confirmation

~~~text
Receive deletion request (requestId)
         |
         v
Verify requester / authorization to act on behalf
         |
         v
Identify subject, tenant, time range, data map
         |
         v
Classify records: delete / legitimately retain / restrict
         |
         v
Approve plan and dry-run
         |
         +----> files and rotated files
         +----> collector / index / dashboard copies
         +----> archive / object versions
         +----> backup / restore process
         +----> processors / data recipients (if any)
         |
         v
Scoped execution + job tracking
         |
         v
Readback, reconciliation, deletion ledger
         |
         v
Respond with accurate result; track remaining items
~~~

A complete workflow typically includes:

1. **Intake:** generate a unique `requestId`, record the timestamp and type of right requested, and do not put raw PII content into privilege-escalation tickets.
2. **Verification:** verify the identity of the subject or authorized representative through a trusted channel. Do not use a client-supplied `userId` value as proof of ownership.
3. **Scoping:** find related direct and indirect IDs; use tenant scope, service, event type, and time range.
4. **Classification:** decide whether to delete, restrict, legitimately retain, or escalate to legal for review. Do not let clients self-declare `legalHold`.
5. **Mapping:** identify every store and copy containing the information, their owners, and actual API/deletion capabilities.
6. **Dry-run and approval:** estimate record counts, validate filter accuracy, assess impact on others, backups, and audit integrity.
7. **Execution:** run tasks with least privilege, resource limits, and idempotency, monitoring per-destination errors.
8. **Verification:** confirm logs no longer exist within the deleted scope, processing jobs are complete, and data is not re-ingested from old sources.
9. **Response:** distinguish between completed, legitimately retained records, or still pending; do not disclose another person's information.

You can use statuses `RECEIVED → VERIFIED → APPROVED → IN_PROGRESS → COMPLETED/PARTIAL_RESTRICTED/FAILED`. Every status must clearly record the reason and access permissions for the report.

## 5. Why Must the Entire Storage Chain Be Managed?

~~~text
Java Application
   |
   +--> ConsoleAppender / stdout
   +--> FileAppender / RollingFileAppender
   +--> AsyncAppender / in-RAM queue
                   |
                   v
             Log shipper / collector
                   |
             +-----+------+
             |            |
             v            v
         Search index   Object storage
             |            |
             v            v
         Dashboard     Archive / snapshot
                          |
                          v
                       Backup
~~~

Once written, an event may exist in multiple places:

- **Local:** container stdout, active log file, rotated files, compressed archives, temporary logs in support directories.
- **Transport:** agents, buffers, or queues in the log shipping system; some records may still be waiting for retry.
- **Central:** Elasticsearch/OpenSearch, log search systems, or queryable databases.
- **Long-term:** object storage, snapshots, WORM/immutable archives, export files, and backups.
- **Third parties:** observability or technical support tools that received data under contract.

**Deleting at one stage does not mean all stages are deleted.** For example, delete-by-query in a search backend does not delete source files, and an old backup can bring just-deleted data back into the index after a restore.

You need a **data inventory** listing store name, owner, data type, retention policy, per-event deletion capability, confirmation type, backup schedule, restore procedure, and point of contact. Do not map only the single path that a developer happens to remember.

## 6. Challenges of Append-Only Logs and Framework Limitations

Logback `RollingFileAppender`, Log4j 2 `FileAppender`, and JUL `FileHandler` normally **append events to a file**, and do not provide a CRUD API by `userId` to delete previously written lines. If a file contains:

~~~text
evt-101 user-A login
evt-102 user-B purchase
evt-103 user-A profile-view
~~~

Deleting the entire file for `user-A` would mistakenly delete `evt-102` belonging to `user-B`. Replacing the text `user-A` with `"anonymous"` may still not remove all identifying information if timestamps, IPs, emails, or transaction IDs remain elsewhere.

Technical options to consider:

1. **Segment-based lifecycle:** suitable when all logs in a segment share the same retention period and can expire over time; does not solve all cases of deleting an individual ahead of schedule.
2. **Controlled file rewriting:** pause/coordinate the writer, read the source file, remove or de-identify the exact records, verify the retained event count, and safely replace the file according to filesystem/backend semantics. Must handle rotation, open file handles, and downstream copies.
3. **Record-level storage:** structured logs in a backend that supports deletion by document ID or query, along with job and snapshot verification.
4. **True de-identification:** remove attributes that can re-link to an individual where lawful; do not only strip the email field.
5. **Crypto-erasure:** destroying a separate encryption key can render data undecryptable under proper design; must verify key scope, key backups, replicas, and potential impact on others.

Do not run `rm`/`truncate`/`sed` directly on an actively written production file to prove deletion. Such actions can lose other users' logs, destroy evidence, corrupt files, or leave the appender writing to the old inode after a rename. A dedicated file-replacement and verification procedure is required if the backend does not support structured deletion.

If records are signed, hash-chained, or stored in immutable mode for tamper-evidence, partial deletion can break verification mechanisms. Never bypass integrity controls; apply an approved procedure or design a different storage model that satisfies both audit requirements and data rights.

## 7. Standalone Java 17+ Example: Scoped Deletion and Legitimate Retention

The following example illustrates **decision logic** using an in-memory `ArrayList` of synthetic events. It tests an unverified case, deletes the exact two eligible events, retains one `onLegalHold` event under control, and leaves another subject's data untouched.

**This is not a production deletion function.** The `verified` and `onLegalHold` values only simulate results already checked by a trusted system; they must never be taken directly from HTTP input and trusted as-is. This code also does not delete data on disk, collectors, indexes, heap memory, or backups.

Create **LogErasureDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.stream.Collectors;

public class LogErasureDemo {
    record LogEvent(String eventId, String subjectRef,
                    String details, boolean onLegalHold) {}

    record ErasureResult(int deleted, int restricted) {}

    static ErasureResult erase(List<LogEvent> events,
                               String subjectRef,
                               boolean verified) {
        if (!verified) {
            throw new SecurityException("Identity not verified");
        }

        int deleted = 0;
        int restricted = 0;
        for (Iterator<LogEvent> it = events.iterator(); it.hasNext();) {
            LogEvent event = it.next();
            if (!event.subjectRef().equals(subjectRef)) {
                continue;
            }
            if (event.onLegalHold()) {
                restricted++;
            } else {
                it.remove();
                deleted++;
            }
        }
        return new ErasureResult(deleted, restricted);
    }

    public static void main(String[] args) {
        List<LogEvent> events = new ArrayList<>(List.of(
            new LogEvent("evt-1", "subject-A", "profile-view", false),
            new LogEvent("evt-2", "subject-A", "login-fail", false),
            new LogEvent("evt-3", "subject-A", "case-123", true),
            new LogEvent("evt-4", "subject-B", "purchase", false)
        ));

        System.out.println("before=" + events.size());

        try {
            erase(events, "subject-A", false);
        } catch (SecurityException ex) {
            System.out.println("unauthorized=REJECTED");
        }

        ErasureResult result = erase(events, "subject-A", true);
        System.out.println("deleted=" + result.deleted());
        System.out.println("restricted=" + result.restricted());
        System.out.println("after=" + events.size());

        String ids = events.stream().map(LogEvent::eventId)
                .collect(Collectors.joining(","));
        System.out.println("remaining=" + ids);
        System.out.println("status=" +
                (result.restricted() > 0
                    ? "PARTIAL_RESTRICTED"
                    : "COMPLETED"));
    }
}
~~~

Compile and run commands:

~~~bash
javac LogErasureDemo.java
java LogErasureDemo
~~~

Deterministic stdout of the example:

~~~text
before=4
unauthorized=REJECTED
deleted=2
restricted=1
after=2
remaining=evt-3,evt-4
status=PARTIAL_RESTRICTED
~~~

Explanation:

- The unverified request is blocked, and no records are modified.
- `evt-1` and `evt-2` belong to `subject-A` with no retention flag, so they are removed from the list.
- `evt-3` belongs to `subject-A` with `onLegalHold=true`, so it is temporarily retained under control; **legal hold must be a justified decision** from the system/legal team, not an arbitrary flag.
- `evt-4` belongs to `subject-B` and is unaffected.
- The `PARTIAL_RESTRICTED` result indicates that full deletion of all related data cannot be confirmed.

`List.remove()` only removes an element from a list; it does not immediately scrub heap memory, delete files, or serve as a real multi-threaded or multi-replica log deletion API. This snippet is meant to teach **verification – scoping – classification – result recording**, not a complete security solution.

An event may involve multiple subjects; a model with only a single `subjectRef` does not handle that case. In real usage, you need a schema, mappings, and checks for PII across multiple fields.

## 8. Deleting in Elasticsearch/OpenSearch or Indexed Log Stores

Many log stores allow deletion by document ID, query, or time range; however, syntax, permissions, and execution states vary by version. A safe workflow:

1. Define a query constrained by **tenant, verified subject ID, index allowlist, and time range**.
2. Run a dry-run/count or appropriate metadata query; review the expected document count before allowing deletion.
3. Approve and execute bounded batches; do not allow requests to build wildcards across all indexes.
4. Record the task/job ID; wait for completion and check for errors, shard failures, timeouts, and retries.
5. Read back using the same criteria, compare remaining IDs, and verify legitimately retained events.
6. Block **re-ingest/replay** sources from old files/queues/archives so deleted logs do not return.
7. Evaluate replicas, snapshots, exports, and physical reclamation timing according to backend semantics.

**HTTP 200 or “task submitted” does not equal deletion completed across all replicas.** In some engines, deletion is asynchronous and physical segments are reclaimed later. The system must clearly report what kind of completion it is confirming.

Do not provide a generic delete-by-query command to copy-paste into production, because index structures, identifier fields, versions, and policies may differ.

## 9. Archives, WORM, and Object Storage

For archives and object storage, distinguish between:

- **Delete object:** removes an object according to API capabilities and storage policies.
- **Versioning:** a delete marker does not necessarily remove all previous versions.
- **Object lock/WORM/legal hold:** may intentionally prevent modification or premature deletion.
- **Multi-subject objects:** deleting an entire object can cause loss of valid data belonging to other people.
- **Third-party copies:** may lie outside the Java service's direct deletion authority.

If selective deletion is needed within an object containing multiple events, you need an appropriate partitioned storage strategy, safe read/rewrite, or a storage model supporting record-level operations. Do not intentionally bypass WORM protection just to complete a request; evaluate retention grounds, access restrictions, and processing timing according to policy.

Crypto-erasure is only reliable if the target data's key is managed separately, all unauthorized key copies are eliminated, other people's data is not lost, and recovery testing has been performed. **Deleting an encryption key shared across an entire bucket is not selective deletion for one user.**

## 10. Backups and the Risk of Data “Resurrection”

Backups are easily overlooked when handling deletion requests. Deleting from the primary index and later restoring an old snapshot can recreate the deleted data.

A design must answer:

- Which log sets do backups/snapshots contain, and until when are they kept?
- Can objects/versions be processed selectively, or must we wait for lifecycle expiration?
- Who has restore permissions, and is restored data immediately exposed to traffic?
- Is a **deletion ledger/tombstone** stored independently and re-applied before the restored system serves traffic?
- Has restoring from a backup predating the deletion request been tested?

If backups cannot be individually edited/deleted by design or due to retention obligations, you need dedicated policies for access control, restore handling, lifespan, and requester communication. **Do not claim “all copies deleted”** without evidence of this state.

A safe restore step is: restore into an isolated environment → read the deletion ledger → re-apply still-valid deletion requests → verify → then open appropriate access. Exact techniques depend on the backend, law, and data policy.

## 11. Deletion Ledger and Deletion Result Auditing

To handle retries, partial failures, and multiple stores, store minimal state per `requestId`:

~~~json
{
  "requestId": "dsr-0042",
  "receivedAt": "2026-11-10T02:00:00Z",
  "scopeVersion": "privacy-map-v3",
  "status": "PARTIAL_RESTRICTED",
  "processedStores": ["logs-index", "rotated-logs"],
  "pendingStores": ["backup-lifecycle"],
  "deletedEventCount": 120,
  "restrictedEventCount": 3,
  "policyDecisionRef": "approval-007"
}
~~~

Values are illustrative only. The ledger must not copy messages containing the PII that was just deleted. If mapping `requestId` to a specific person is required, store it in a separately protected store following an appropriate data lifecycle.

Technical requirements:

- **Idempotent:** re-running the same `requestId` does not automatically delete unrelated data.
- **Tracked:** per-store progress, job ID, errors, record counts, timestamps, and verification method.
- **Access-controlled:** deleting and viewing the ledger are sensitive operations.
- **Honest status:** errors or justified retentions are never marked completed.
- **No excess PII:** auditing the deletion action does not store the deleted content.
- **Recovery-ready:** the ledger prevents re-ingestion/restore from resurrecting records.

An audit record containing only `requestId`, policy version, `jobId`, result, and minimal counts can suffice to prove the action occurred without storing the subject's email/address/real ID in a broader-access location.

## 12. Partial Record Deletion and De-Identification

Deleting the entire record is not always the only or right approach: an event may involve subjects A and B, or serve as valid evidence for B's transaction. In that case, evaluate:

1. Can the entire record be deleted?
2. Can direct and indirect fields related to A be removed while keeping the part with a legitimate purpose?
3. Can the remaining fields be combined to re-identify A?
4. Is there any mapping table or key that still links an “anonymous ID” back to A?
5. Does modifying the record break audit evidence, signatures, or integrity verification?
6. Is the retained portion subject to appropriate access restrictions and a deletion schedule?

**UI masking** is not deletion or anonymization: hiding the email column on a dashboard does not remove the email from indexes, files, and backups. Replacing `userId` with a fixed value may not be de-identification if `timestamp + IP + orderId` can still single out the person.

For logs requiring tamper-evident records, design a mechanism to keep **minimal metadata** separate from optional personal information, rather than writing everything into an unprocessable text line.

## 13. Preventing Deletion Needs via Data Minimization

The most effective approach is **not writing unnecessary personal data into `LogEvent` in the first place**.

### 13.1. Structured Event Design

Prefer stable fields such as `eventId`, `service`, `eventCode`, `status`, `latencyMs`, and `requestId`, instead of logging entire objects or request bodies. When a subject reference is needed, use a controlled mapping and evaluate the lifecycle of that mapping itself.

### 13.2. Do Not Log Secrets

Do not log passwords, tokens, session cookies, API keys, private keys, payment card data, or raw `Authorization` headers. For errors, avoid putting emails or user input into exception messages unless necessary. Do not capture full URL query strings when they may contain personal data.

### 13.3. Classify Log Sources

Separate application/debug logs from security/audit logs so each has appropriate retention, ACLs, and access/deletion policies. Do not use `DEBUG`/`INFO` logger levels as the legal criterion for whether data may be retained.

### 13.4. Purpose-Based Retention

Choose retention limits by data type, operational need, and legal obligations—do not keep all logs indefinitely just because disk space is available. Verify whether rotation/lifecycle actually deletes files or merely moves them to another archive directory.

### 13.5. Audit Libraries and Environment

Logs from HTTP clients, JDBC, frameworks, reverse proxies, background jobs, and containers can emit PII independently of application loggers. Do not review only `log.info` calls in your own code.

## 14. Least Privilege and Safeguards Against Accidental Deletion

A deletion service can become an evidence-destruction tool if permissions are too broad. You need:

- **Requester verification:** authorization for the exact subject, tenant, and representative role.
- **Fixed deletion criteria:** do not let callers supply arbitrary index names or uncontrolled regexes.
- **Allowlists:** restrict stores, namespaces, event types, and operations.
- **Dry-run:** estimate record counts and impact without exposing raw PII in previews.
- **Approvals:** require independent review for large-scale actions or those involving critical evidence.
- **Idempotency and per-request locking:** prevent races between duplicate jobs and ingestion batches.
- **Rate limits and batch caps:** prevent overwhelming collectors or accidentally deleting millions of records.
- **Independent audit:** do not write job audit logs into the very file being deleted.
- **Alerts:** trigger on job failures, abnormal counts, or cross-tenant query attempts.

An HTTP parameter like `userId=someone-else` is not proof that the caller is authorized to delete `someone-else`'s data. Never let `role`/`legalHold` be decided by a client-supplied boolean.

## 15. Testing and Acceptance Criteria

Use a test environment with **synthetic data**; never test deletion on logs containing real users.

### Test Matrix

| Case | Expected Outcome |
| --- | --- |
| Unverified identity | Rejected, no data modified |
| Request for subject A only | B's separate events are not deleted |
| A has email in message and userId in metadata | Found completely via schema/mapping, not just a single string |
| A's event is under justified retention | Not mistakenly deleted; restricted and reported as PARTIAL_RESTRICTED |
| Event involves both A and B | Decision applied per field/record, not blindly deleted |
| Running job interrupted | Retrying the same requestId does not cause inconsistent deletion |
| File rotating or events in queue | Other users' events not lost, events to delete not re-ingested |
| Asynchronous index deletion | Wait for job completion and re-verify |
| Backup predating deletion request | Restore does not cause deleted data to reappear |
| Object versioning/WORM | Delete marker not mistaken for removing all versions |
| Insufficient operator permissions | Operation rejected, safely logged |

### Verification Criteria

A request is considered complete within the approved scope only when:

1. Authorization and processing policy have been verified.
2. Data inventory covers all relevant locations.
3. All jobs at deletable stores have completed with no unresolved errors.
4. Re-querying by ID/tenant and all related keys confirms no data requiring deletion remains.
5. No ingest/replay pipeline can bring the events back.
6. Archives/versions/backups are handled per policy; restore gate is tested when needed.
7. Legitimately retained portions record the reason, access restrictions, and review date.
8. Responses do not conflate **completed**, **partial**, and **failed**.

Suggested metrics: `pending_deletion_requests`, `deletion_failures`, `deleted_event_count`, `restricted_event_count`, `oldest_pending_request_age`, `restore_replay_pending`. Do not put email/`userId` directly into metric labels.

## 16. Common Mistakes

**“Deleting `application.log` means we're done.”** Wrong if the file contains logs from multiple users and copies exist in collectors/indexes/backups. Deleting a shared file can cause loss of other people's data.

**“We configured 7-day retention, so we don't need to handle deletion requests.”** Periodic expiration is valuable, but must be checked against the request and applicable law; it is not automatically sufficient for every case.

**“Email isn't visible in the dashboard, so it's deleted.”** The dashboard may only be hiding the field while indexes, files, and copies still contain the data.

**“Hashing `userId` makes it anonymous.”** If the hash can be linked, reversed/guessed, or has a mapping table, re-identification risk remains.

**“Backups don't need handling because they're read-only.”** Backups can bring data back after a restore; retention and anti-resurrection controls are required.

**“All audit logs are always exempt from deletion.”** You must examine the specific purpose and retention basis, minimal data, and retention period.

**“The delete command returned 200, so all replicas/snapshots are deleted.”** Many backends process asynchronously or keep other versions; you must check the job and target scope.

**“We only need to search for the exact `userId`.”** Events may contain email, IP, `correlationId`, `orderId`, and other links. Structured data and a data inventory are required.

**“Replacing the message with `[REDACTED]` removes all PII.”** Other metadata may still re-identify the user, and the original may still exist in files/segments, caches, or backups.

**“We can roll back by restoring the just-deleted data.”** Uncontrolled restoration can violate the committed privacy state; a restore gate and deletion ledger are required.

## 17. Implementation Checklist

- [ ] Intake and verification channel exists for valid deletion requests.
- [ ] Process exists to evaluate legal basis and retained event types.
- [ ] Direct/indirect PII fields and corresponding mapping sources are known.
- [ ] Inventory covers local files, rotated logs, collectors, indexes, archives, snapshots, backups, and exports.
- [ ] All deletion jobs are scoped by tenant, subject, time range, and least privilege.
- [ ] Dry-run, approval, and abnormal-count alerts are in place.
- [ ] Multi-subject events are handled without mistakenly deleting other users' data.
- [ ] Idempotent deletion ledger/tombstone and minimal operation auditing exist.
- [ ] Post-deletion readback and full tracking of async tasks/ingest/retries are implemented.
- [ ] Backup lifecycle and post-restore anti-resurrection controls exist.
- [ ] Completed, legitimately retained, failed, and pending statuses are clearly separated.
- [ ] Retention and data minimization are designed from the log source.
- [ ] Dedicated tests cover append-only files, WORM, versioning, async pipelines, and snapshots.

**Conclusion:** Log deletion on request is a **privacy and data lifecycle governance process**, not a built-in logger delete feature. Handling it properly requires understanding subject rights, retention grounds, event structure, copies, sink characteristics, and verification methods. The best prevention is **not logging unnecessary PII**, setting appropriate retention, and designing controlled deletion paths from the start.

## 18. References

- [Law on Personal Data Protection 91/2025/QH15 — Government Portal](https://vanban.chinhphu.vn/?classid=1&docid=214590&pageid=27160&typegroup=): subject rights, provisions on deletion, destruction, and de-identification; effective 01/01/2026.
- [Decree 356/2025/NĐ-CP — Government Portal](https://vanban.chinhphu.vn/?classid=1&docid=216387&pageid=27160): detailed regulations and implementation of the Law on Personal Data Protection.
- [GDPR, Regulation (EU) 2016/679 — Articles 17, 19](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32016R0679): right to erasure, exceptions, and related obligations.
- [Irish Data Protection Commission — The Right to Erasure](https://www.dataprotection.ie/en/individuals/know-your-rights/right-erasure-articles-17-19-gdpr): interpretation of the right to erasure and its limits under GDPR.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): data to exclude from logs, retention management, copy handling, and disposal.
- [OWASP Logging Vocabulary Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Vocabulary_Cheat_Sheet.html): recording sensitive data deletion events without copying the content.
- [Logback Manual — Appenders](https://logback.qos.ch/manual/appenders.html): file/rolling appenders and output path limitations.
- [Apache Log4j 2 — Appenders](https://logging.apache.org/log4j/2.x/manual/appenders.html): outputting logs to different destinations.
- [Java SE 17 — java.util.logging](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/package-summary.html): logging API and Handler, with no API to delete records across all sinks.
