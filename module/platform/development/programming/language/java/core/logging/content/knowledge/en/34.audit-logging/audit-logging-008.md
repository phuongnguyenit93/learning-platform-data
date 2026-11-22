# Audit Immutability in Java Logging

## 1. Audit logging and immutability requirements

**Audit logging** records actions that require accountability: who acted, what action they took, on which resource, when it happened, and what the outcome was. Unlike regular DEBUG/INFO diagnostic logs, audit logs can be used to investigate unauthorized access, inspect permission changes, reconcile business operations, support internal controls, and provide evidence under approved procedures.

An audit system can store every event yet still be untrustworthy if a privileged user can modify old records, delete history, fabricate a new history, or lose events during an incident. **Audit immutability** is the goal of preventing or controlling the modification or deletion of accepted events and establishing independent verification mechanisms to detect unauthorized changes.

It is important to distinguish:

| Property | Meaning |
| --- | --- |
| **Append-only** | Only new events are added on the supported write path; old events are never updated |
| **Immutability** | Committed data cannot be modified or deleted before a valid point under the permission and retention model |
| **Integrity** | Event contents and relationships between events still match the committed record |
| **Tamper evidence** | If unintended changes occur, the system has the ability to detect them |
| **Authenticity** | There is proof that an authorized source signed or emitted the data |
| **Completeness** | No expected events are missing and there are no unexplained gaps |
| **Durability** | Confirmed events are not lost on crash, restart, or single-component failure |
| **Confidentiality** | Only authorized parties can read sensitive audit data |

These properties are related but **do not substitute for one another**. A file that only allows appending can still be deleted by root. A hash chain can detect modification if an independent baseline is kept, but it cannot by itself prevent an attacker from recomputing the entire chain. A WORM object may be unmodifiable yet still contain false content from the start. An encrypted record can still be deleted or replaced.

The design goal is to **prove a trustworthy history within a specific threat model**, not to claim that "nobody in the world can alter the audit."

## 2. Threat model: protecting against whom and what?

Different actors hold different levels of privilege:

- **End users:** may try to avoid generating audit events or pass payloads that distort content.
- **Compromised applications:** may write forged events or skip auditing if no additional constraints exist.
- **Database administrator (DBA):** can modify tables even if the application role only has INSERT.
- **Cluster/root administrator:** can delete files/volumes or tamper with agents/collectors.
- **Cloud storage administrator:** can alter retention/lifecycle or bypass certain policies if the mode/permissions allow it.
- **Signing key holder:** can sign an alternate history if the key is abused.
- **Unintentional failures:** lost ACKs, retries, crashes mid-transaction, clock skew, backup restores, and full queues.

Therefore, specific attack capabilities must be enumerated:

| Scenario | Valuable control | What remains unsolved |
| --- | --- | --- |
| User API sends duplicate events | eventId + idempotency | Does not prevent an admin from modifying storage |
| Application role attempts UPDATE/DELETE | INSERT-only + least-privilege database permissions | Table owner/superuser can still bypass |
| Modifying one event in a chain | Hash chain and sequential verification | If an attacker recomputes the entire chain, an external anchor is needed |
| Deleting the tail of history | Head checkpoint + lastSequence in an independent store | Does not detect events that were never emitted without reconciliation |
| Deleting files or objects | WORM retention, replication, backup | Must verify actual permissions and storage regions |
| Forging event origin | HMAC/digital signature + key management | Does not prove the event accurately describes the business action |
| Losing logs during an outage | Durable outbox, queue/backpressure policy | Requires monitoring lag, retries, and recovery |

**Separation of duties** is a critical condition: if the same account is allowed to emit audit events, edit data, delete WORM copies, replace checkpoints, and manage keys, an attacker who compromises that account can produce a history that is hard to verify. Separate writer, auditor, verifier, key custodian, and storage admin privileges when the assurance level requires it.

## 3. Audit events must have a semantic contract

Not every INFO/ERROR line should be treated as an audit event. Audit events must be emitted at a boundary that knows the **actual action and confirmed outcome**, not merely in a helper method that runs before the transaction.

Typical event categories include:

- Authentication, MFA, password resets, and account status changes.
- Authorization: granting or revoking roles; access policy changes; security-relevant failed access.
- Critical business data changes, approvals/reversals, sensitive data exports.
- System configuration, secret policy, retention, or audit collector changes.
- Administrator operations and changes to audit store read or write permissions.
- Data access events required to be recorded by internal policy.

Reference schema:

| Field | Purpose |
| --- | --- |
| eventId | Unique ID per business event; used for deduplication |
| streamId + sequenceNo | Partitioning and accepted append order |
| schemaVersion | Structure/encoding version used for verification |
| eventType | Standardized event name; do not use raw input as the event name |
| occurredAt | Time of the action according to the source |
| recordedAt | Time the audit system accepted the event |
| actorType/actorRef | Person, service, or system performing the action |
| action, resourceType, resourceRef | Operation and target object |
| outcome, reasonCode | Success/failure and a stable encoded reason |
| requestId/traceId/jobId | Context for correlation, if available |
| previousHash/recordHash | Integrity link for the stream |
| keyId/checkpointRef | Key or verification anchor, if used |

Example structured audit event (illustrative values and schema):

~~~json
{
  "eventId": "evt-7f1",
  "streamId": "admin-audit",
  "sequenceNo": 103,
  "schemaVersion": 1,
  "eventType": "ROLE_REVOKED",
  "occurredAt": "2026-11-10T02:40:00Z",
  "recordedAt": "2026-11-10T02:40:01Z",
  "actorRef": "admin-7",
  "resourceRef": "member-8",
  "outcome": "SUCCESS",
  "requestId": "req-42"
}
~~~

**Audit data must be minimized before writing**: do not put raw passwords, access tokens, cookies, secrets, PAN/CVV, unnecessary request bodies, or excessive personal information into WORM storage. Making policy-violating data immutable can complicate privacy incident remediation.

## 4. Append-only at the application and database layers

An append-only system **never modifies history** to reflect a new state. Instead, a reversing decision creates a separate event:

~~~text
seq=101 event=ROLE_GRANTED principal=member-8 role=EDITOR
seq=102 event=ROLE_REVOKED principal=member-8 role=EDITOR
~~~

Event 101 remains true because it records that the role was once granted. Do not UPDATE event 101 to REVOKED; doing so erases the trace of the original action.

You can use an audit table with INSERT/SELECT privileges for the writer and no UPDATE/DELETE privileges. **Sketch** PostgreSQL example, not universal DDL for every database:

~~~sql
CREATE TABLE audit_events (
    stream_id       text NOT NULL,
    sequence_no     bigint NOT NULL,
    event_id        text NOT NULL UNIQUE,
    recorded_at     timestamptz NOT NULL,
    event_type      text NOT NULL,
    actor_ref       text NOT NULL,
    payload         jsonb NOT NULL,
    previous_hash   char(64) NOT NULL,
    record_hash     char(64) NOT NULL,
    PRIMARY KEY (stream_id, sequence_no)
);

GRANT SELECT, INSERT ON audit_events TO audit_writer;
REVOKE UPDATE, DELETE, TRUNCATE ON audit_events FROM audit_writer;
~~~

This is **access control on the application role**, not physical immutability. A superuser, owner, backup restore, or migration can still alter data or restore an older state. Table ownership, role inheritance, privileges, and out-of-band paths into the database must all be reviewed.

If the audit requires strong evidence, export a copy to a **retention/WORM store with separate administration** and an independent checkpoint. Merely forbidding UPDATE in service code is insufficient when the system has multiple write paths to the database.

## 5. WORM storage: locking committed versions

**WORM (Write Once, Read Many)** is a storage model in which a finalized object/version cannot be modified or deleted during a policy-defined retention period. Some object storage platforms provide retention locks, versioning, or legal holds. Never assume all WORM modes offer the same level of protection.

Before choosing one, verify:

1. Is the immutable unit **a specific version**, a file, or a logical key?
2. From what point is retention calculated, and how long is the retention period?
3. Can an administrator **shorten or bypass** the retention period in the mode being used?
4. Is there any permission that can delete the encryption key, making the data unreadable even though the object still exists?
5. Are versioning, replication, backup, and recovery in place for a region failure?
6. Are changes to retention, holds, policies, and admin permissions themselves audited?
7. Are rejected overwrite/delete API calls tested in staging?

**WORM does not prove that an event was accurate at the source.** A publisher that emits a false event can still have it stored immutably. You must authenticate writers, validate schemas, align with business transactions, and reconcile.

**WORM also does not mean storing forever.** "Cannot be modified/deleted before the retention period expires" and "never deleted permanently" are two different requirements, especially when personal data protection obligations apply.

## 6. How does a hash chain detect history modification?

A **hash chain** binds the hash of the previous record into the hashed input of the current record:

~~~text
genesisHash
    |
    v
event 1 -> hash1
            |
            v
         event 2 -> hash2
                     |
                     v
                  event 3 -> hash3
~~~

One way to model this:

~~~text
previousHash[1] = genesisHash
previousHash[i] = recordHash[i-1]

recordHash[i] = SHA-256(
    canonical(schemaVersion, streamId, sequenceNo, eventPayload,
              previousHash[i])
)
~~~

If an attacker modifies an old event while keeping the old hash, the verifier will recompute and see a mismatch. If a record in the middle of the chain is deleted, the sequence or previousHash link will no longer match. If events are reordered without recomputing the chain, that will also be detected.

However, be aware of the limitations:

- **SHA-256 is an unkeyed hash function**; anyone can recompute the digest after editing an event.
- An attacker who controls the entire store can **rewrite the whole history and all hashes**.
- **Tail truncation** can leave a valid prefix, so internal verification of that prefix still returns true.
- An event that was never created will not appear for hash verification to notice.
- A hash chain does not by itself prove that the event's actor is legitimate or that the outcome was committed by the business logic.

To detect **full rewrites or tail truncation**, you must check **headHash and lastSequence** against an **independently protected checkpoint/anchor**, or combine with signatures/HMAC, along with reconciliation from business sources.

## 7. Canonical encoding is required for accurate verification

If two systems serialize the same event into different bytes, the hashes will differ even though the logical data is identical. For example, a `Map` in Java cannot be assumed to have a fixed field order across every serializer or every version.

A canonical encoding must define:

- Fixed field order and schemaVersion.
- Representation of sequences, integers, floating-point numbers, and booleans.
- UTF-8, length prefixes, null representation, and Unicode normalization if applicable.
- UTC timestamps and the chosen precision.
- JSON key ordering/escaping if true canonical JSON is used.
- How previousHash, eventId, and streamId are represented.
- Rules when the schema is upgraded or new fields are added.

**Do not hash `Map.toString()`, log text formatters, or ad-hoc concatenated JSON without defining canonical bytes.** A library version upgrade, timezone change, whitespace difference, or key order change can cause false integrity failures.

You can use a contract-defined binary format with explicit byte lengths, or a serializer that supports deterministic/canonical encoding and is covered by tests. Verification code for older `schemaVersion` values must be retained to verify multi-year history.

## 8. Runnable Java 17 example: hash chain with canonical bytes

The following Java SE 17 example uses `SHA-256`, `DataOutputStream`, `UTF-8`, and `HexFormat`. The program simulates two audit events in memory, then modifies the first event without recomputing its hash to demonstrate that the verifier detects the mismatch.

Create the file **AuditIntegrityDemo.java**:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;

public class AuditIntegrityDemo {
    private static final String GENESIS = "0".repeat(64);

    record Entry(long sequence, String action, String actor,
                 String previousHash, String hash) {}

    private static void field(DataOutputStream out, String value)
            throws IOException {
        byte[] utf8 = value.getBytes(StandardCharsets.UTF_8);
        out.writeInt(utf8.length);
        out.write(utf8);
    }

    private static byte[] canonical(long sequence, String action,
                                    String actor, String previousHash) {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(buffer)) {
            out.writeInt(1);  // schema version
            out.writeLong(sequence);
            field(out, action);
            field(out, actor);
            field(out, previousHash);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
        return buffer.toByteArray();
    }

    private static String hash(long sequence, String action,
                               String actor, String previousHash) {
        try {
            MessageDigest sha = MessageDigest.getInstance("SHA-256");
            byte[] bytes = canonical(sequence, action, actor, previousHash);
            return HexFormat.of().formatHex(sha.digest(bytes));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }

    private static void append(List<Entry> entries,
                               String action, String actor) {
        long next = entries.size() + 1L;
        String prior = entries.isEmpty()
                ? GENESIS : entries.get(entries.size() - 1).hash();
        entries.add(new Entry(next, action, actor, prior,
                hash(next, action, actor, prior)));
    }

    private static boolean verify(List<Entry> entries) {
        String prior = GENESIS;
        long expected = 1L;
        for (Entry e : entries) {
            if (e.sequence() != expected
                    || !e.previousHash().equals(prior)
                    || !e.hash().equals(
                            hash(e.sequence(), e.action(),
                                 e.actor(), e.previousHash()))) {
                return false;
            }
            prior = e.hash();
            expected++;
        }
        return true;
    }

    public static void main(String[] args) {
        List<Entry> entries = new ArrayList<>();
        append(entries, "ROLE_GRANTED", "admin-7");
        append(entries, "ROLE_REVOKED", "admin-7");

        System.out.println("events=" + entries.size());
        System.out.println("chainValid=" + verify(entries));

        Entry first = entries.get(0);
        entries.set(0, new Entry(first.sequence(), "ROLE_CHANGED",
                first.actor(), first.previousHash(), first.hash()));

        System.out.println("tamperDetected=" + !verify(entries));
    }
}
~~~

Compile and run:

~~~bash
javac AuditIntegrityDemo.java
java AuditIntegrityDemo
~~~

Exact expected stdout when the program runs successfully:

~~~text
events=2
chainValid=true
tamperDetected=true
~~~

Explanation:

1. **DataOutputStream** writes the version as an `int`, the sequence as a `long`, and each UTF-8 `String` prefixed by its byte length. The hash is computed over bytes under an explicit convention.
2. **MessageDigest.getInstance("SHA-256")** computes the digest; **HexFormat** produces the hex string.
3. **verify** checks contiguous sequence numbers, matching `previousHash`, and matching recomputed hashes.
4. Changing `action` in the first event while keeping the old hash causes verification to fail; that is why `tamperDetected=true` is printed.
5. The program **does not use files, a database, WORM, signatures, or external checkpoints**. It only demonstrates the principle of tamper evidence for an in-memory chain, not storage immutability.
6. If an attacker modifies an event and recomputes all hashes, or deletes the last event, **verify can still return true**. Comparing the head hash and expected sequence against an independent checkpoint is what detects those cases.
7. In a real system, **streamId, eventId, actor/action/resource/outcome, timestamps, and schema version** must also be bound into the canonical payload. The example intentionally minimizes fields for ease of learning.

**Do not treat an unkeyed digest stored in the same table as strong immutability evidence.** If an actor can modify both the data and the stored digest, internal verification cannot distinguish the original history from a rewritten one.

## 9. Independent checkpoints, HMAC, and digital signatures

When stronger assurance is required, designs typically add:

| Component | Objective |
| --- | --- |
| **Head checkpoint** | Stores `streamId`, `lastSequence`, and `headHash` outside the writer's control |
| **HMAC-SHA-256** | Confirms data was created by a party holding the secret key |
| **Digital signature** | Signs records/checkpoints with a private key; others verify with the public key |
| **WORM archive** | Restricts modification/deletion of closed segments during the retention period |
| **Independent verifier** | Verifies from raw records up to the checkpoint without trusting self-reported writer results |

A checkpoint may carry the following fields (abbreviated placeholder values, **not a real digest or signature**):

~~~json
{
  "streamId": "audit-admin-prod",
  "lastSequence": 10425,
  "headHash": "<full-sha256-hex-in-real-system>",
  "schemaVersion": 1,
  "createdAt": "2026-11-10T03:00:00Z",
  "keyId": "audit-signer-v3"
}
~~~

In production, `headHash` must have the **full byte length and exact format**; the checkpoint needs a trustworthy storage channel, a signature/MAC where appropriate, and access controls separated from the writer.

**HMAC does not equate to non-repudiation among multiple parties sharing the secret.** Anyone holding the HMAC key can produce a MAC; digital signatures with private/public keys are better suited when verifiers must not have signing capability. Even then, a signature does not prove that the event content written by the application is truthful; the event creation path itself must be protected.

Key management requires KMS/HSM where appropriate, `keyId`/versioning, rotation, usage permissions, monitoring, and policy-based revocation. Never write private keys or HMAC keys to logs, and never store them in the same place where one principal can modify the audit, the checkpoint, and the key together.

## 10. Concurrent writers, sequences, and event ordering

Across multiple threads or instances, two writers can read the same old `headHash` and create **two forked branches** without synchronization. Therefore:

- Use a **transactional stream-head lock**, optimistic compare-and-swap, or a sequencer with an explicit contract.
- Do not simply run `SELECT MAX(sequence_no)+1` outside a transaction and hope there is no collision.
- Enforce unique constraints on `(streamId, sequenceNo)` and `eventId`.
- Atomically update the stream head together with appending the event in a transaction whenever possible.
- Clearly define the stream scope: per service, per tenant, or per aggregate.
- If global ordering across multiple regions is required, design a coordinator/consensus mechanism; sorting timestamps alone does not establish a reliable total order.

**occurredAt** recorded by the emitting node can differ from **recordedAt** when the audit store commits due to network delay and clock skew. UTC timestamps are useful for lookup, but are not sufficient on their own as proof of ordering.

Events in two separate streams are not necessarily comparable by `sequenceNo`. When causal relationships are needed, use `parentEventId`, `requestId`/`traceId`, or causal metadata per contract.

## 11. Auditing and business transactions: avoiding lost or false events

A system can suffer from two symmetric failures:

- The business transaction commits successfully, but the audit event is lost → **missing history**.
- The audit event is recorded as SUCCESS before the business transaction rolls back → **history states a false outcome**.

Therefore, you must define **when an event is considered complete** and its relationship to the transaction:

| Architecture | Strength | Caveats |
| --- | --- | --- |
| Same DB transaction: business + audit row | Can commit atomically when in the same database/transaction | DB tables are not necessarily immutable against a DBA |
| **Transactional outbox** | Writes business state and outbox in one transaction, publishes after commit | Needs retries, dedup, and lag management; the outbox is not WORM |
| Durable audit write before returning success | High assurance for sensitive actions | Increases latency and creates a dependency on the audit service |
| Async best-effort logger | Decouples the hot path | Can lose events; not suitable by default for mandatory audits |

**Transactional outbox does not automatically provide end-to-end exactly-once delivery.** A worker may finish publishing, lose the ACK, and publish again; you need a stable `eventId`, consumer-side deduplication, and a clear ledger write protocol. Accepted audit records must receive their `sequence`/`headHash` from the audit writer, rather than simply taking the order of application callbacks.

A retried job creates two **attempts**, which may correspond to one **logical business event** or two events if policy requires auditing each attempt. Distinguish `eventId`, `attemptId`, and `sequenceNo`.

## 12. Durable delivery and handling outages

Returning from **logger.info(...)** or an async publish call cannot be treated as proof that an event was durably stored. A logger queue or collector can lose data on crash, process kill, disk loss, or a full queue.

You must determine:

1. Is the event ACKed after entering memory, a WAL, a DB commit, or an immutable archive?
2. If the audit backend is unavailable, does the business service **fail-closed** or **fail-open with a durable buffer**?
3. Are queues bounded, and what backpressure or action rejection applies when full?
4. How are events remaining in the outbox after a crash replayed?
5. If an ACK is lost, does `eventId` prevent duplicates?
6. If an audit sink fails, are alerts and recovery/evidence-retrieval procedures in place?

**Fail-closed** may be appropriate for administrative privilege grants, highly sensitive data access, or actions where auditing is mandatory before proceeding. **Fail-open with a durable outbox** may fit high-availability systems if recovery and reconciliation commitments are in place. Best-effort diagnostic logs generally do not satisfy audit compliance.

There is no single policy for all actions. Classify events by risk level, compliance requirements, ACK point, and approved latency budgets.

## 13. Rotation, segments, and detecting truncation

High-volume audits are often stored across multiple segments:

~~~text
Segment A: sequence 1..1000, headHash=H1000
Segment B: sequence 1001..2000, initialPreviousHash=H1000
Segment C: sequence 2001..3000, initialPreviousHash=H2000
~~~

Each segment should describe `streamId`, start/end sequence, `schemaVersion`, first `previousHash`, last `headHash`, close time, storage object version, and checkpoint reference. Finalized segments and manifests must be protected from unauthorized modification or deletion.

A verifier must:

- Confirm the manifest contains all expected segments.
- Check for no sequence gaps, duplicates, forks, or invalid reordering.
- Recompute each record's hash using the right canonical version.
- Verify `previousHash` links across segment boundaries.
- Compare **headHash + lastSequence** against a signed or externally stored checkpoint.
- Check retention/lock settings and replication status across replicas.

**Truncation attack**: if segment C is deleted, the hash chain for A+B can still be internally valid. Comparing against an independent checkpoint with an expected `lastSequence=3000` is what reveals the missing history.

If an attacker can rehash all of A+B+C, comparing against a signed or independently held checkpoint will reveal a mismatch. Without an independent anchor, a `true` verification result does not mean history was never altered.

## 14. Reconciling completeness with business sources

Even when WORM, hash chains, and signatures work properly, **events that were never created will not be detected** by rehashing stored events. For example, a code bug that causes a role-granting action to bypass the audit publisher leaves no modified records, yet history is incomplete.

Complementary measures:

- Reconcile committed business transaction counts against audit/outbox record counts by category.
- Monitor outbox unprocessed count, age, retry count, and dead-letter queues.
- Check issued sequence numbers and uncommitted gaps.
- Compare `eventId` values recorded by the business subsystem against `eventId` values in the ledger.
- Alert on pipeline pauses, collector drops, key errors, or signing failures.
- Test backup restores and compare against independent checkpoints.
- Audit configuration changes that stop events from being emitted.

**Hash chains protect the relationships among existing records; reconciliation detects events that should have existed but never appeared.** These two layers complement each other.

## 15. Security and separation of duties

Suggested role model:

| Role | Allowed to do | Should not be allowed to do |
| --- | --- | --- |
| Business service | Create events per schema, send to audit writer | Modify/delete finalized events |
| Audit writer | Append, assign sequence, compute hash per contract | Change retention/keys of the independent store |
| Audit reader | Query within authorized scope | Rewrite history or alter checkpoints |
| Storage admin | Operate capacity, replication | Bypass WORM without controls |
| Key custodian | Manage key lifecycle and signing policies | Modify the audit database + checkpoints |
| Independent verifier | Read and verify hashes/signatures/sequences | Modify source data or trust anchors |

Security operations on the audit system itself should be logged: permission changes, disabling collectors, retention changes, legal holds, exports, key rotation, backup/restore, and access to sensitive data. Audit-of-audit channels also need proper permissions and retention; do not let everything depend on a single mechanism that can be turned off at once.

Verify **least privilege** with authorized tests in staging: the application writer cannot UPDATE/DELETE; the read-only verifier has no write permissions; attempts to overwrite or delete locked objects must be rejected under the active retention mode.

## 16. Fixing business errors with correction events, not overwrites

An old audit event should not be edited into a different event just because the current state has changed.

Example:

~~~text
seq=401 event=ROLE_GRANTED actor=admin-7 principal=member-8
seq=402 event=ROLE_REVOKED actor=admin-7 principal=member-8
seq=403 event=INCIDENT_REVIEWED actor=security-2 ref=case-19
~~~

If software recorded the wrong outcome due to a bug, design a **correction event** referencing the original `eventId`, reason, actor, and appropriate approval. The original record must be kept so auditors can see both the history and the correction process, rather than altering the old event without a trace.

However, a correction event does not fix an audit pipeline that dropped data. When you discover an event that was never recorded, reconcile against the business source, log an incident for the gap, and clearly mark the event as reconstructed after the incident rather than fabricating it as if it had been recorded at the original time.

## 17. Privacy, retention, and immutable stores

Audit logs can contain personal, financial, or business-secret data. Locking data in WORM for too long before classifying it makes handling erroneously emitted events much harder.

- **Data minimization:** record only event codes, `actorRef`/`resourceRef`, and necessary fields; never store raw passwords, tokens, private keys, authorization headers, or full payloads.
- **Privacy:** `actorRef` can sometimes still be linked to an identity; do not label every opaque ID as fully anonymized data.
- **Retention:** define retention periods by event type and applicable regulations; do not keep data forever by default.
- **Encryption:** protects data at rest and in transit, but encrypted data can be decrypted with the key; this is neither redaction nor immutability.
- **Legal hold:** control who can place or lift holds and record the decision trail.
- **Key erasure/crypto-shredding:** apply only when policy permits, as it can render data undecryptable while also affecting verification/recovery; do not automatically treat it as compliant data deletion in all cases.
- **Deletion workflows:** once valid retention expires, data can be destroyed under an approved lifecycle; understand the rules of the cloud mode in use.

If a credential is accidentally written to an immutable store, treat it as a **data exposure incident**: rotate/revoke the credential, restrict read access, identify all copies, and follow the appropriate legal/security procedures. Changing the log level afterward does not invalidate a secret that has already been written.

## 18. Running an independent verifier

A verifier should run under a different principal and failure domain than the audit writer; do not rely solely on reading an INFO line saying "write succeeded" emitted by the writer itself.

Suggested workflow:

1. Fetch `streamId`, the segment list, and checkpoint anchors from a verified location.
2. Read events with read-only permissions and validate `schemaVersion`/encoding version.
3. Recompute hashes from canonical bytes; compare stored hashes and `previousHash`.
4. Verify contiguous sequence numbers with no forks, gaps, or duplicates.
5. Compare `headHash` and `lastSequence` against the external checkpoint.
6. Verify HMACs or digital signatures using `keyId` and policy-verified keys.
7. Reconcile against business/outbox records to detect unemitted events.
8. Check retention locks, ingest lag, archival, replication, and permission-change history.
9. Record the result, timestamp, scope, executor, and evidence in a protected channel.

Example report (illustrative data, not real evidence):

~~~json
{
  "streamId": "admin-audit-prod",
  "range": "10401-10425",
  "hashChainValid": true,
  "headCheckpointValid": true,
  "sequenceComplete": true,
  "businessReconciliation": "matched",
  "verifiedAt": "2026-11-10T03:15:00Z"
}
~~~

**`hashChainValid=true` alone does not fully prove immutability.** You need independent anchors/keys, completeness checks, and storage policy evidence aligned with the threat model.

## 19. Testing under failures and attacks

| Category | Test scenario in an authorized environment | Expected result |
| --- | --- | --- |
| Append-only | Application role executes UPDATE/DELETE on records | Blocked |
| Hash chain | Modify action/actor while keeping the hash | Verifier detects mismatch |
| Rehash | Modify content and recompute all hashes | Trusted anchor/signature does not match |
| Truncation | Delete the last event | Head checkpoint/lastSequence detects it |
| Missing event | Publisher skips a mandatory event | Business reconciliation detects it |
| Concurrency | Multiple writers append to the same stream concurrently | Unique sequences, no invalid forks |
| Crash | Crash between commit and publish | Outbox/recovery preserves data per contract |
| Retry | Lost ACK and duplicate publish of `eventId` | Dedup/idempotency works correctly |
| Storage | Attempt to overwrite/delete a locked object | Storage rejects per retention policy |
| Key rotation | Verifier reads old events after key rotation | Verifies using `keyId` and key policy |
| Restore | Restore an older backup | Checkpoint comparison detects rollback |
| Outage | Collector/queue/WORM storage unavailable | Alerts fire, backpressure/fail mode behaves properly |
| Privacy | Test input containing tokens/PII | Raw secrets are not stored outside policy |
| Audit-of-audit | Change retention or signing permissions | Audit trail and approval recorded |

**Do not test deletion or retention bypass on real production data outside an authorized plan.** Use staging/test objects and separate configurations; confirm results via API and storage logs.

For the Java 17 program in section 8, the smoke test is: two initial events are valid, and modifying the first event's action while keeping its hash causes `verify` to return `false`. It tests **in-memory tamper detection**, not WORM, durable commits, key protection, or database permissions.

## 20. Common misconceptions

| Misconception | Issue | How to address |
| --- | --- | --- |
| "Having SHA-256 means it is immutable" | An attacker can rehash | Independent anchor, signing, storage controls |
| "Forbidding UPDATE stops all admins" | DBA/owner can still alter data | Separation of duties, external archive |
| "WORM guarantees events are truthful" | A writer can still store fake events | Source authentication and reconciliation |
| "Timestamps establish absolute order" | Clock skew and network delay | Stream sequences and causal metadata |
| "A successful log append is durable" | Async queues can lose events | ACK/commit contract, durable outbox |
| "Chain verify true means no events were lost" | Tail truncation and missing events | Checkpoints + reconciliation |
| "HMAC proves a specific individual signed it" | Anyone with the secret can compute a MAC | Digital signatures and key separation when needed |
| "Immutable audits must be kept forever" | Privacy/retention have lifecycles | Lock for the retention term, delete per policy |
| "We have backups, so verification is unnecessary" | Backups can also be wrong or stale | Restore drills + checkpoints |
| "Delete the wrong event and rewrite it" | Loses change history | Correction event with a reference |
| "No DELETE permission on the API is enough" | DB/storage paths exist outside the API | Review privileges and threat model |
| "The broker guarantees everything is exactly-once" | ACK loss/retries occur across boundaries | `eventId`, idempotency, outbox |

## 21. Audit immutability implementation checklist

| Component | Minimum requirement |
| --- | --- |
| Event semantics | Define actions that must be audited and when an outcome is considered real |
| Audit schema | `eventId`, `streamId`, sequence, actor/action/resource/outcome, and `schemaVersion` |
| Privacy | No unnecessary credentials/payloads; approved retention |
| Append-only write | Application role cannot UPDATE/DELETE history |
| Durable delivery | Clear ACK commitment; outbox/retry/backpressure/failure modes tested |
| Canonical bytes | Versioned, defined field order, encoding, and compatibility tests |
| Hash chain | `previousHash` linking and full-stream verification |
| Trusted checkpoint | `lastSequence` + `headHash` stored outside the writer's control |
| HMAC/signature | If used, manage `keyId`, rotation, and signer/verifier roles |
| WORM/retention | Locks/versioning/modes and bypass permissions verified |
| Concurrency | Atomic sequence/head updates, no unintended forks |
| Verification | Independent verifier checks content, chain, anchor, and completeness |
| Monitoring | Alerts on ingest gaps, mismatches, drops, signing failures, pipeline pauses |
| Restore | Backup/replication and checkpoint comparison on restore |
| Correction | New events record reversals/corrections instead of overwrites |
| Security operations | Changes to audit policy, permissions, and keys are also audited |

**Conclusion:** audit immutability is not just restricting `UPDATE` statements. A trustworthy audit trail requires **accurate and complete events, append-only/WORM storage with proper permissions and retention, a hash chain with canonical encoding, checkpoints or signatures in an independent trust zone, durable delivery, regular verification, and a privacy policy**. In Java, `MessageDigest` and database/transaction APIs are building blocks, but the final level of assurance comes from the entire architecture and its operations.
