# Data Retention, Deletion, and Classification Policies

Within **Governance and Compliance**, data retention, deletion, and classification policies define what data may be collected, who can access it, how long it must be kept, and how it must be handled once its purpose ends. In serverless applications, data does not reside solely in the primary database. A single request can create copies across queues, DLQs, event archives, logs, traces, caches, object storage, backups, and analytics platforms. Consequently, deleting a row does not mean deletion has completed across the entire system.

This lesson belongs to the **CLOUD_SERVERLESS** module, focusing on developing and deploying applications using the serverless model, especially Java functions triggered by HTTP, messages, or events. Learners work with triggers, state, access permissions, retries, idempotency, cold starts, scaling, and cost to determine when to use FaaS. Data governance must be designed alongside event flows, IAM, storage, observability, backups, and function operational workflows.

## 1. Objectives of a Data Policy

A sound data policy must answer these questions:

- What data is collected and for what purpose?
- Is the data public, internal, confidential, or sensitive?
- Who is the owner accountable for the data?
- Which system holds the primary record and which systems hold copies?
- Which event starts the retention clock?
- Upon expiration, is the data archived, anonymized, or deleted?
- Are there legal obligations, contractual requirements, or legal holds preventing deletion?
- How do we prove data was processed in accordance with policy?
- If data is replicated via events, logs, and backups, how does deletion propagate?

A policy should not be just a single TTL number. Retention periods must tie to business purpose, legal obligations, and data categories. Different data categories may have different retention start triggers, such as creation time, last activity, contract termination, or transaction completion.

## 2. Data Classification

Data classification guides how data is stored, encrypted, accessed, logged, shared, and deleted. A straightforward model can use four levels:

| Level | Examples | Typical Measures |
|---|---|---|
| Public | Published website content, marketing materials | Integrity control, version management |
| Internal | Operational metadata, standard internal documents | Internal IAM, sharing controls, and retention |
| Confidential | Customer data, contracts, business records | Least privilege, encryption, access auditing |
| Restricted / Sensitive | Sensitive PII, payment data, credentials, auth secrets | Strictly limited access, strong encryption, masking, monitoring, and tight retention |

Classification level names may vary across organizations. What matters is that each level carries concrete enforcement rules rather than acting as a mere label.

### 2.1. Field-Level Classification

A single record can contain fields of differing sensitivity. For example, an order contains an order ID, status, amount, shipping address, and phone number. Do not apply a generic label and then allow the entire payload to appear in logs.

You can classify by field:

- Public identifier: safe for logs if not directly linkable to an individual.
- Internal business metadata: visible only to staff with a need to know.
- Personal data: bounded by purpose and retention period.
- Sensitive personal data: requires heightened protection and processing only with a valid legal basis.
- Authentication secrets: never logged and never placed into event payloads if consumers do not need them.

When an object mixes multiple data types, default to applying the highest protection level to the entire object or split fields into storage/records with separate policies.

### 2.2. Classification Must Tie to Purpose

Just because data can be collected does not mean it should be. Before adding a field to a request, event, or log, determine:

- Processing purpose.
- Lawful/permitted basis under applicable policies and regulations.
- Which systems or consumers require that field.
- How long it must be retained.
- Whether aggregated data, a pseudonym, or a reference can replace raw data.

Data minimization reduces both risk and cost. If a consumer only needs a customer ID to call an authorized API, do not broadcast the full customer profile across an event bus.

## 3. Data Inventory and Data Ownership

You cannot manage retention without knowing where data lives. Maintain a traceable inventory:

| Attribute | Details to Record |
|---|---|
| Data domain | Customer, order, payment, telemetry |
| Data owner | Accountable team or role |
| Source of truth | System holding the primary record |
| Classification | Sensitivity level |
| Purpose | Processing purpose |
| Storage locations | Databases, buckets, queues, logs, archives |
| Consumers | Functions, services, analytics jobs |
| Retention rule | Anchor event and duration |
| Deletion method | Hard delete, anonymize, crypto erase, expiry |
| Legal hold | Conditions pausing deletion |
| Evidence | Audit records or verification reports |

The data owner defines business purpose and policy; platform/security teams provide enforcement mechanisms; application teams ensure code compliance. Never assign retention responsibility to a scheduled Lambda without an owner and an approved policy.

### 3.1. Tracing Data in Serverless

An HTTP request can generate multiple copies:

~~~mermaid
flowchart TD
    R["HTTP request"] --> F["Java Lambda"]
    F --> DB["Primary database"]
    F --> Q["Queue / Event bus"]
    F --> L["Logs and traces"]
    DB --> A["Analytics / warehouse"]
    Q --> C["Downstream consumers"]
    Q --> D["DLQ / archive"]
    DB --> B["Snapshots / backups"]
    C --> S["Search / cache / object store"]
~~~

The data inventory must include copies generated by integrations and operations. A single event can fan out to multiple consumers, each of which may build its own projection or index. Deleting at the source without notifying consumers leaves stale data behind.

## 4. Designing a Retention Schedule

A retention schedule defines which data is kept for how long, starting from which point, and what action occurs at expiry.

Example policy structure:

| Data Type | Retention Start Anchor | Action on Expiry |
|---|---|---|
| Temporary session | Creation time or last activity | Delete |
| Request staging | When workflow finishes | Delete or keep briefly for retries |
| Business transaction | When transaction closes | Archive per applicable obligations |
| Customer profile | When purpose ends or valid request received | Delete or anonymize per policy |
| Application logs | When log entry is created | Expire per log retention |
| DLQ | When message enters DLQ | Investigate, redrive, or audited delete |
| Event archive | When event is archived | Expire per archive retention |
| Backups | Snapshot timestamp | Delete per backup lifecycle |
| Security audit records | Event occurrence time | Retain per audit policy and applicable obligations |

The table above only illustrates how to model policies. No single retention period fits every data type or every jurisdiction. Legal, privacy, security, and business owners must confirm durations based on applicable regulations, contracts, and usage purposes.

### 4.1. Defining the Retention Clock

Specify clearly when the retention clock starts:

- `created_at`: when the record was created.
- `last_activity_at`: time of last activity.
- `transaction_closed_at`: when the transaction closed.
- `contract_ended_at`: when the contract expired/terminated.
- `request_completed_at`: when the request or workflow completed.
- `archived_at`: when data moved to archive.

Do not use one generic timestamp for every record type. For instance, payment record retention may start when a transaction settles, whereas session retention starts at last activity.

### 4.2. Multi-Tier Retention

Data may move through hot, warm, and cold storage tiers:

- Hot: actively serving the application, requiring fast access.
- Warm: infrequently accessed yet still queryable.
- Cold/archive: kept solely for audit or archival obligations.
- Expired: past its purpose and eligible for deletion.

Moving data to archive is not deletion. Archives still require classification, encryption, IAM controls, retention rules, and deletion policies. Data retained longer continues to carry risk if access is not controlled.

## 5. Legal Holds and Retention Exceptions

A legal hold is an instruction to suspend deletion of data related to litigation, investigations, or preservation mandates. It must specify scope, owner, start time, reason, and release conditions.

The process should:

1. Identify the exact data subjects, records, tenants, or time ranges affected.
2. Place holds across all copies within scope.
3. Record the approver and timestamp.
4. Prevent retention jobs from deleting held data.
5. Continue protecting held data with encryption and access controls.
6. Lift the hold upon valid authorization.
7. Return the data to the normal retention workflow.

Do not place a system-wide legal hold if the scope concerns only a small set of records. Overly broad holds inflate storage costs and retain data longer than necessary.

Retention jobs must check for holds at execution time, not only when compiling deletion candidates. A hold could be added after the job plans its batch and before deletion executes.

## 6. End-of-Lifecycle Handling Options

There are multiple ways to end a data lifecycle:

| Method | Meaning | When Appropriate |
|---|---|---|
| Hard delete | Remove records or objects from active storage | When data no longer needs to be kept |
| Soft delete | Mark as deleted and hide from business flows | When short recovery workflows or audits are needed |
| Anonymization | Transform so individuals can no longer be identified per applicable standards | When aggregate statistics are still needed |
| Pseudonymization | Replace direct identifiers with tokens while keeping controlled linkability via a separate key | When reducing exposure while preserving controlled linkage |
| Archive | Move to archival storage | When retention obligations or lookup needs remain |
| Cryptographic erasure | Destroy the relevant decryption keys so encrypted data becomes unreadable | When key architecture supports it and meets requirements |

Soft delete is not complete deletion. If a record merely carries `deleted=true` yet still appears in APIs, search indexes, exports, or backups, the data still exists. Pseudonymization is likewise not anonymization if re-identification remains possible through mapping tables or auxiliary data.

### 6.1. Hard Deletes and Cascading

Deleting a customer can involve orders, addresses, preferences, support tickets, search indexes, and analytics. Do not blindly cascade-delete every record if some records must be retained under other obligations.

Define domain-specific rules:

- Delete completely.
- Retain transactions while removing or separating identifying fields.
- Retain anonymized aggregate data.
- Retain a minimal reference to preserve referential integrity.
- Retain copies under active legal hold.

Rules must be approved and explainable. Never assume a customer deletion request automatically means wiping all transaction history.

## 7. Cross-System Data Deletion Workflow

A deletion workflow can be broken into these steps:

1. Receive a request or identify records past retention.
2. Verify the requester's authority and data scope.
3. Check legal holds and mandatory retention obligations.
4. Locate the source of truth and all copies.
5. Prevent new data generation within the deletion scope.
6. Delete, anonymize, or restrict access to the primary record per policy.
7. Emit a deletion event via a transactional outbox.
8. Consumers delete replicas, caches, search indexes, and projections.
9. Handle queues, DLQs, archives, and third-party processors.
10. Handle backups via lifecycle expiration or approved crypto erasure.
11. Reconcile results and record audit evidence.

Do not run a database deletion script and consider the job finished. You must know which consumers received the deletion event and which systems still hold copies.

~~~mermaid
flowchart TD
    REQ["Deletion request / retention expiry"] --> AUTH["Verify scope and authority"]
    AUTH --> HOLD{"Legal hold?"}
    HOLD -->|"Yes"| PAUSE["Pause deletion and record hold"]
    HOLD -->|"No"| MAP["Discover copies and processors"]
    MAP --> SOURCE["Delete / anonymize source data"]
    SOURCE --> OUTBOX["Commit deletion event via outbox"]
    OUTBOX --> FAN["Notify downstream consumers"]
    FAN --> VERIFY["Verify replicas, indexes and caches"]
    VERIFY --> BACKUP["Apply backup expiry / key policy"]
    BACKUP --> AUDIT["Record evidence and close request"]
~~~

## 8. Deletion Events and Idempotent Delete Handlers

A deletion event should contain the identifier needed for consumers to locate data, without broadcasting all the PII scheduled for deletion.

Example:

~~~json
{
  "eventId": "evt-delete-901",
  "eventType": "CustomerDataDeletionRequested",
  "schemaVersion": 1,
  "requestId": "del-2026-0042",
  "subjectRef": "subject-token-7f21",
  "scope": [
    "profile",
    "preferences",
    "search-index"
  ],
  "policyVersion": "customer-retention-v3",
  "requestedAt": "2026-11-17T10:00:00Z"
}
~~~

`subjectRef` should be an opaque reference, avoiding raw emails or direct national/account identifiers. Consumers must verify authority and scope from an authenticated workflow rather than trusting an arbitrary event to delete data on demand.

Delete handlers must be idempotent: running multiple times converges to the same final state. For instance, deleting a cache key that is already absent can be treated as success, while still distinguishing "not found" from "access denied."

~~~java
public final class CustomerDeletionHandler {
    private final DeletionRepository deletions;
    private final SearchIndex searchIndex;
    private final CacheStore cache;

    public CustomerDeletionHandler(
            DeletionRepository deletions,
            SearchIndex searchIndex,
            CacheStore cache) {
        this.deletions = deletions;
        this.searchIndex = searchIndex;
        this.cache = cache;
    }

    public void handle(CustomerDeletionRequested event) {
        deletions.deleteProfileIfPresent(event.subjectRef());
        searchIndex.deleteBySubject(event.subjectRef());
        cache.evictSubject(event.subjectRef());
        deletions.markConsumerComplete(
                "customer-projection",
                event.eventId());
    }
}
~~~

This is a simplified example. In production, each step needs independent state tracking and retries. Never mark a consumer complete if a mandatory step fails. When multiple systems must mutate together, use workflow orchestration or a deletion task ledger to track progress.

## 9. Tombstones to Prevent Deleted Data from Returning

In an event-driven system, an older event can be retried or replayed after data has been deleted. If a consumer merely deletes the current row, a late `OrderUpdated` or `CustomerProfileChanged` event could recreate the record.

A tombstone records that an entity was deleted or blocked from recreation. A tombstone may include:

- Opaque subject/entity ID.
- Deletion timestamp.
- Policy version.
- Deletion request ID.
- Completion status.
- Scope of processed systems.

When an older event arrives, the consumer checks the tombstone before creating or updating a projection. If the entity was deleted, the stale event is ignored or routed to an investigation flow per policy.

Tombstones must be retained long enough to span queue, archive, replay, and backup restore horizons. Deleting tombstones too early risks resurrecting deleted data.

## 10. Deletion in Queues, DLQs, and Event Archives

Message queues and event archives have their own lifecycles:

- Messages in queues can persist up to the service's retention limit.
- DLQs can hold copies of failed messages.
- Event archives can allow replaying historical events.
- Streams can retain records across a retention window.
- Consumer retries can keep events alive for extended periods.

When a deletion request arrives, assess whether payloads containing PII can be deleted directly, allowed to expire via retention, or must be encrypted with a dedicated key so decryption capability can be destroyed.

Some services do not support selectively deleting a single appended event from an archive or stream by event ID. In those cases, use an approved approach: restrict access, exclude the event from replay, crypto-erase where appropriate, or wait out retention expiration. Never claim complete deletion while copies remain.

### 10.1. Preventing Replay of Deleted Data

Replay controllers and consumers must consult the deletion ledger/tombstones. If an event sits in the archive for a deleted subject, the consumer must not recreate the profile or projection.

If an archive may contain sensitive data, restrict replay permissions. Replay is not a read-only privilege; it can regenerate data and trigger side effects in production.

## 11. Logs and Traces Are Data Too

Logs, traces, and metrics can capture personal data or secrets:

- Request and response bodies.
- Emails, phone numbers, addresses, or access tokens.
- URLs with sensitive query parameters.
- Exception messages containing SQL or payloads.
- Trace attributes containing customer IDs.
- Custom metric dimensions holding identifying values.

Logging rules:

- Log only fields needed for operations.
- Mask or redact PII and secrets before writing.
- Never log `Authorization` headers, passwords, tokens, or raw payment data.
- Use opaque correlation IDs for tracing.
- Set explicit retention on every log group.
- Restrict log read permissions and audit log access.
- Do not use PII as high-cardinality metric dimensions.

Log retention does not replace business record retention. Conversely, data inside logs still requires classification and its own retention period.

### 11.1. Safe Java Logging

Example logging metadata rather than the entire request:

~~~java
public void handle(CreateOrderRequest request) {
    logger.info(
            "CreateOrder received: correlationId={}, itemCount={}",
            request.correlationId(),
            request.items().size());

    orderService.create(request);
}
~~~

Never log the raw request object, as it may contain addresses, customer details, or tokens. If payload inspection is needed for investigations, store it in a separate access-controlled, retention-bounded store with encryption and auditing.

With logging frameworks, you can build a redaction filter or structured logging encoder to filter sensitive fields centrally. However, filters do not replace the responsibility of keeping secrets out of log messages in the first place.

## 12. CloudWatch Logs and Explicit Retention

Without explicit retention, log groups can retain data longer than intended under service defaults. With CloudWatch Logs, declare retention in IaC so every environment stays consistent.

CloudFormation example:

~~~yaml
Resources:
  OrdersFunctionLogGroup:
    Type: AWS::Logs::LogGroup
    Properties:
      LogGroupName: /aws/lambda/orders-function
      RetentionInDays: 90
~~~

90 days is an illustrative value only, not a universal recommendation. Choose retention based on operational needs, security investigations, and approved retention obligations. Ensure permissions and log group retention are configured properly even when functions auto-create log groups.

If logs are exported to S3, a SIEM, or a data lake, export retention must be managed separately. Deleting the log group does not automatically delete exports or copies inside other observability tools.

## 13. DynamoDB TTL and Limits of Automatic Expiration

DynamoDB TTL can remove items once a TTL attribute holds a past Unix epoch timestamp, such as an `expiresAtEpochSeconds` field.

~~~json
{
  "PK": "SESSION#session-123",
  "expiresAtEpochSeconds": 1794916800,
  "status": "EXPIRED"
}
~~~

TTL cleans up temporary data without needing scheduled scans and deletes per item. However:

- TTL deletion is asynchronous and does not happen at the exact timestamp.
- Expired items can still be read before the service removes them.
- TTL does not replace authorization or expiry checks in application code.
- TTL does not automatically remove copies in search indexes, caches, queues, or backups.
- TTL is not a mechanism for strict deletion deadlines that require immediate confirmation.

If a session expires at 12:00, the application must reject the session based on `expiresAt` even if TTL has not deleted the item yet. TTL is cleanup only.

## 14. S3 Lifecycle, Versioning, and Object Deletion

S3 Lifecycle can transition objects to other storage classes or expire them according to rules. However, check:

- Is versioning enabled on the bucket?
- Are delete markers created instead of removing older versions?
- Do noncurrent versions have their own retention rules?
- Is Object Lock or a legal hold enabled?
- Do replication destinations still hold copies?
- Have objects been exported or copied to other buckets?
- Do incomplete multipart uploads need cleanup?

In a versioned bucket, deleting the current object may simply add a delete marker; prior object versions remain intact. True deletion requires handling versions per policy and checking Object Lock/legal holds.

Lifecycle actions are lifecycle management mechanisms, not synchronous, second-accurate deletion operations. If proof of completed deletion is required, establish proper verification and auditing procedures.

## 15. Backups, Snapshots, and Post-Restore Handling

Backups create an independent copy of data. A record deleted from the live database may still exist in an earlier snapshot or backup.

Policies must specify:

- How long backups are retained.
- Who is permitted to restore.
- Whether backups are encrypted with dedicated keys.
- During a restore, how deletion requests received after the snapshot timestamp are reapplied.
- Which backups may fall under legal hold.
- When backups expire or are destroyed.

A common approach is maintaining a durable deletion ledger/tombstone store. After restoring an older backup, replay the ledger to reapply deletions completed after the backup timestamp. Otherwise, deleted data can reappear.

Never promise instant removal from every backup if the architecture only deletes backups on their scheduled expiry cycle. Document exact retention timelines and exceptions accurately in policy.

## 16. Cryptographic Erasure and Key Management

Cryptographic erasure renders data unreadable by destroying the encryption keys required to decrypt it. This approach is meaningful only when:

- Data was encrypted with appropriate keys.
- No usable copies of the keys or data encryption keys remain.
- Backups do not hold plaintext copies or uncontrolled key copies.
- The key hierarchy is designed to destroy keys at the exact scope of data to be deleted.
- Destroying a key does not wipe out other data that must be kept.

If multiple customers share a single KMS key, destroying that key renders all customers' data unreadable. Per-subject erasure requires appropriate key granularity, such as per-tenant or per-object data keys backed by securely managed wrapping keys.

Destroying a KMS key can involve waiting periods and a scheduled deletion state; do not describe it as instantaneous. Crypto-erasure also does not replace deleting metadata, indexes, and plaintext copies.

## 17. Event Sourcing and Append-Only Data

In an event-sourced system, current state is rebuilt from an event log. Deleting an event can break replay and auditing. Define handling according to requirements:

- Strip or encrypt identifying fields from event payloads if the architecture permits.
- Separate PII from immutable events, storing references only.
- Use subject-specific encryption keys to enable crypto-erasure.
- Emit redaction events or tombstones so projections stop displaying the data.
- Rebuild projections after applying deletion policies.
- Retain minimal records if legally required, under dedicated access controls and retention.

A redaction event does not erase PII from historical events by itself. If original payloads remain readable, the data still exists. Design event contracts upfront to avoid embedding unnecessary personal data into long-lived events.

## 18. Retention and Deletion in Serverless Workflows

Workflows can span multiple functions and outlive a single invocation. Each step may produce execution history, payloads, retry records, or outputs.

Inspect:

- Whether Step Functions execution histories and inputs/outputs contain PII.
- How long SQS messages and DLQs hold payloads.
- Whether EventBridge archives store sensitive events.
- Whether Kinesis/Kafka retention covers retry/replay needs without over-retaining.
- Whether Lambda `/tmp` holds sensitive files across warm invocations.
- Whether extensions, layers, or container images accidentally contain test data or secrets.
- Whether X-Ray traces and logs capture request fields.
- Whether database snapshots and object storage have independent lifecycles.

Lambda execution environments can be reused. Files in `/tmp` may persist across invocations on the same environment. Avoid writing sensitive data there unless necessary; if unavoidable, scope filenames per request, restrict permissions, delete after processing on a best-effort basis, and do not rely on the environment being destroyed immediately.

Do not hold personal data in Java static caches without a clear purpose and bounded TTL/size. An execution environment can serve subsequent requests; caches must prevent cross-tenant or cross-user leakage.

## 19. Data Retention in Caches and Search Indexes

Caches are often overlooked in deletion workflows. When source data is deleted, caches may keep serving stale values until TTL expires.

Recommended practices:

- Scope cache keys by tenant/subject.
- Emit invalidation events when records are deleted or updated.
- Use appropriate TTLs, but never rely on TTL alone for urgent deletion requests.
- Provide mechanisms to delete by subject or namespace.
- Avoid caching raw PII when caching a reference suffices.
- Verify that search indexes and materialized views are updated.

Search indexes may retain document copies, tokenized fields, and metadata. Deleting a database row does not automatically delete the index entry. Deletion consumers must know which indexes hold the entity and confirm successful removal.

## 20. Third-Party Processors and Data Sharing

Data may be sent to email providers, analytics tools, payment processors, CRMs, or support platforms. The data inventory must clearly document:

- Which data types each processor receives.
- Sharing purpose.
- Transmission and encryption mechanisms.
- Processor retention periods.
- How deletion/correction requests are submitted.
- Response SLAs and completion evidence.
- Subprocessors or copies managed by the processor.

Internal deletion workflows do not automatically remove data held by third parties. You need APIs or operational procedures supported by the processor, tracking request IDs and statuses. If a processor does not support selective deletion, document the limitation and address it under applicable contracts and regulations.

## 21. Automating Retention with Policy as Code

Retention policies should be expressed as versioned, owned configuration rather than hard-coded numbers scattered across Lambdas.

Conceptual configuration example:

~~~yaml
dataPolicies:
  - category: temporary-session
    classification: internal
    retention:
      anchor: lastActivityAt
      duration: P30D
    action: delete

  - category: application-log
    classification: confidential
    retention:
      anchor: createdAt
      duration: P90D
    action: expire

  - category: customer-profile
    classification: restricted
    retention:
      anchor: purposeEndedAt
      duration: APPROVED_DURATION
    action: review-and-delete
~~~

The durations `P30D` and `P90D` illustrate ISO-8601 formatting only, not recommended legal retention periods. `APPROVED_DURATION` is a placeholder to be replaced with a duration approved by the data owner and responsible teams. Legal holds are checked independently at retention/deletion execution time and should not be modeled as a flag indicating whether a data category supports holds.

A policy engine or retention service can read this configuration and generate deletion tasks. Policies must be versioned so you know which rules governed each record. Retention changes require review and auditing because mistakes can cause premature deletion or over-retention.

### 21.1. Safe Scheduled Cleanup

A scheduled Lambda can locate expired records:

~~~sql
SELECT record_id, tenant_id
FROM temporary_session
WHERE expires_at <= CURRENT_TIMESTAMP
  AND deletion_status = 'ACTIVE'
ORDER BY expires_at
LIMIT :batch_size;
~~~

Each record should then be processed with race-condition safeguards:

- Check legal holds at deletion time.
- Claim the record or use a conditional update.
- Delete/anonymize within an appropriate transaction.
- Write a deletion audit entry.
- Emit downstream events via an outbox.
- Retry failures without accidentally deleting a newly extended record.

Never run a massive table-wide `DELETE` if it causes locking, load spikes, or replication lag. Use small batches, rate limits, and database monitoring.

## 22. Java Model for Retention Policies

Retention rules can be modeled in code while sourcing durations from approved policy configuration:

~~~java
import java.time.Duration;
import java.time.Instant;

public record RetentionRule(
        String category,
        Duration duration,
        Anchor anchor,
        ExpiryAction action) {

    public Instant expiresAt(Instant anchorTime) {
        return anchorTime.plus(duration);
    }

    public enum Anchor {
        CREATED_AT,
        LAST_ACTIVITY_AT,
        PURPOSE_ENDED_AT
    }

    public enum ExpiryAction {
        DELETE,
        ANONYMIZE,
        ARCHIVE,
        REVIEW
    }
}
~~~

This example represents a simple rule. Production systems must support legal holds, policy versioning, timezone semantics, jurisdiction-specific exceptions, and auditing. Never take retention durations from user requests; only governed policy may determine retention timelines.

### 22.1. Never Delete Based Solely on Client Timestamps

Clients can send inaccurate or tampered timestamps. Retention anchors must be recorded by a trusted system, such as database commit time or a verified workflow completion timestamp. When using `lastActivityAt`, control timestamp updates so users cannot extend retention against policy.

## 23. Audit Evidence and Deletion Verification

Each deletion request should maintain a tracking record:

- Request ID.
- Subject reference or record scope.
- Policy version.
- Initiating user/system.
- Verification and approval timestamps.
- Legal hold check result.
- Systems that received the deletion event.
- Per-consumer status.
- Backup/archive handling outcome.
- Completion timestamp or reason for incomplete status.

Do not store the deleted sensitive data itself in the audit log. Audit records should keep enough metadata to prove the process ran without recreating the data slated for deletion.

A deletion workflow can use states like:

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> VERIFIED
    VERIFIED --> ON_HOLD
    VERIFIED --> IN_PROGRESS
    ON_HOLD --> VERIFIED
    IN_PROGRESS --> PARTIAL
    PARTIAL --> IN_PROGRESS
    IN_PROGRESS --> COMPLETED
    COMPLETED --> [*]
~~~

`COMPLETED` should be set only once all mandatory systems in scope have confirmed deletion or reached a policy-accepted state, such as backup copies scheduled to expire per a published schedule. Never mark complete merely because a deletion event was published.

## 24. Testing Retention and Deletion

Scenarios to test:

- Expired records are processed per policy.
- Unexpired records are not deleted.
- Legal holds block deletion jobs.
- Holds added after candidate selection but before deletion still block execution.
- Duplicate deletion events cause no errors or unintended side effects.
- Consumers failing mid-way can safely retry.
- Search indexes, caches, and projections are cleared.
- Older events do not resurrect tombstoned entities.
- Backup restores replay the deletion ledger.
- S3 versioning and delete markers are handled properly.
- DynamoDB TTL is not mistaken for immediate deletion.
- Logs and traces contain no out-of-policy PII.
- `/tmp` or Java caches do not leak data across invocations.
- Third-party processors receive and confirm deletion requests.

Integration tests should verify actual state in databases, queues, object storage, and indexes in an isolated environment. Mocks only verify method calls; they do not prove data vanished from every copy.

## 25. Common Mistakes

**Deleting only the primary database:** Copies remain in queues, logs, caches, search indexes, or backups. Use a data inventory and cross-system deletion workflow.

**Treating soft delete as full deletion:** Records still exist and can surface in exports or APIs. Define explicit states and hard-delete deadlines.

**Using TTL as a hard deletion deadline:** Cleanup is usually asynchronous. Applications must enforce expiry checks and maintain separate verification.

**Ignoring S3 object versions:** Delete markers do not remove prior versions. Verify versioning, lifecycle rules, and Object Lock.

**Ignoring logs and traces:** PII lingers inside the observability platform. Redact before writing and configure dedicated retention.

**Forgetting DLQs and event archives:** Old payloads can be replayed. Control replay permissions, retention, and tombstones.

**Purging tombstones too early:** Late events can resurrect deleted records. Retain tombstones across the entire replay horizon.

**Restoring backups and bringing data back:** Old backups contain deleted records. Reapply the deletion ledger after restore.

**Not checking legal holds at deletion time:** Jobs can delete recently held records. Re-check inside the transaction or immediately before final execution.

**Sending PII inside deletion events:** Adds another sensitive copy to the broker. Use opaque references and minimal scope.

**Keeping data in Lambda `/tmp` or static caches:** Reused execution environments can retain data across invocations. Bound, isolate, and clean up temporary data.

**Lacking owners and policy versions:** Unclear who approved durations and which rules applied. Track owners, versions, and audits.

## 26. Production Checklist

- [ ] A data inventory exists covering databases, queues, DLQs, archives, logs, traces, caches, backups, and third-party processors.
- [ ] Every data category has an owner, purpose, and classification.
- [ ] Every data type has an approved retention anchor and duration.
- [ ] Legal holds have scope, owners, audits, and pre-deletion checks.
- [ ] Hard delete, soft delete, anonymization, and pseudonymization are clearly distinguished.
- [ ] Deletion workflows enforce request verification and idempotency.
- [ ] Deletion events carry no unnecessary PII.
- [ ] An outbox guarantees deletion requests are emitted after commit.
- [ ] Downstream consumers purge caches, indexes, and projections.
- [ ] Tombstones prevent old events from recreating deleted data.
- [ ] Queues, DLQs, streams, and archives have retention/replay policies.
- [ ] CloudWatch Logs have explicit retention configured.
- [ ] DynamoDB TTL is not used as a substitute for expiry enforcement.
- [ ] S3 versioning, lifecycle rules, and Object Lock are verified.
- [ ] Backup restores include a step to replay the deletion ledger.
- [ ] Crypto-erasure is used only when the key architecture matches deletion scope.
- [ ] Lambda `/tmp`, static caches, and logs do not retain out-of-policy PII.
- [ ] Third-party processors have deletion procedures and completion evidence.
- [ ] Audit evidence does not retain deleted sensitive data.
- [ ] Metrics track deletion backlog, partial failures, and oldest pending requests.
- [ ] Integration tests cover holds, retries, replays, backup restores, and downstream copies.

## Conclusion

Data retention, deletion, and classification policies must cover the entire lifecycle and every copy of data. Classification determines protection levels; retention schedules define durations and start anchors; legal holds govern exceptions; and deletion workflows propagate requests across databases, queues, archives, logs, caches, backups, and external processors.

In serverless, pay close attention to event payloads, DLQs, replays, CloudWatch Logs, DynamoDB TTL, S3 versioning, Lambda `/tmp`, and reused execution environments. TTLs and lifecycle rules are cleanup helpers, not substitutes for policies or verification. Java functions should use idempotent deletion events, transactional outboxes, tombstones, and audit ledgers to delete data under control without allowing old records to reappear.
