# Retention, Access Control, and Integrity Policies for Audit Records

A Spring Security system can record permission denials, role changes, sensitive resource accesses, or administrative privilege usage. Yet **merely having logs** is not enough to call it a trustworthy audit system. After an incident, the organization must still be able to locate the evidence; unauthorized personnel must not read or export it; privileged application users must not quietly alter or erase their tracks. At the same time, records containing personal data must not be retained indefinitely.

This lesson belongs to the **Events and Auditing** group of **Spring Security - authorization**, focusing on three pillars: **retention (timely storage and disposal), access (access control), and integrity (tamper-resistance and tamper detection)**. Examples use Java 17+, connecting to how Spring Security protects audit administration APIs and integrates with Spring Boot Actuator. Illustrative retention durations in this lesson are **not legal mandates applicable to every system**.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain why audit records must be protected across their entire lifecycle: creation, transit, storage, querying, export, hold, restoration, and disposal.
- Design a policy matrix for each event class, defining clock start, fast-searchable duration, total retention duration, legal hold exceptions, and approval responsibilities.
- Separate permissions for **writing audits**, **reading**, **exporting**, **placing holds**, **modifying retention**, **policy-driven purging**, **key management**, and **integrity verification**.
- Distinguish confidentiality, integrity, availability, authenticity, and completeness; understand the limits of checksums, SHA-256, HMAC, digital signatures, hash chains, and immutable/WORM storage.
- Write and run a Java 17 example creating an HMAC chain that detects modified records, while recognizing that tail truncation requires an independent checkpoint.
- Apply guards in Spring Security and storage layers, and test unauthorized access, retention expiry, legal holds, collector failures, and investigative workflows.

## 2. What Kind of Data Is an Audit Record?

An audit record is structured evidence documenting **an event significant to accountability**. It can originate from `AuthorizationDeniedEvent`, `AuthenticationFailureEvent`, user-management actions, policy updates, audit queries/exports, or data-disposal jobs.

A record should help answer *when, where, who or which system, which action was requested, on which resource, what outcome, and which correlation trail*. However, not every field is always known. For example, `AuthorizationDeniedEvent` reports a denied authorization decision, yet does not inherently contain the final HTTP status or full business reason.

Example of a **normalized and data-minimized** record:

```json
{
  "schemaVersion": 1,
  "eventId": "e61f8637-b614-4f1d-936c-a37a85267d95",
  "eventType": "AUTHORIZATION_DENIED",
  "occurredAt": "2026-11-05T08:10:11Z",
  "receivedAt": "2026-11-05T08:10:12Z",
  "service": "order-api",
  "environment": "production",
  "actorRef": "actor-17",
  "tenantRef": "tenant-a",
  "requestId": "req-56c",
  "resourceType": "ORDER",
  "action": "READ",
  "decision": "DENY",
  "policyRef": "order.read.v3",
  "classification": "SECURITY_AUDIT"
}
```

This is an **application-designed schema**, not a payload Spring Security generates automatically. Fields follow an explicit contract: `eventId` prevents duplicate writes; `occurredAt` is when the event occurred; `receivedAt` is when the collector received it; `requestId`/trace ID links logs; `actorRef`/`tenantRef` are protected references rather than raw credentials.

Never record passwords, OTPs, Bearer tokens, session cookies, full URLs with personal data, request bodies, or full `Authentication`/`Principal` objects by default. **Hashing an email or phone number does not automatically make it anonymous**: over small value spaces, hashes can be guessed; pseudonymized identifiers typically still require protection as linkable personal data.

### 2.1. Five Properties to Distinguish

| Property | Question | Common controls |
| --- | --- | --- |
| **Confidentiality** | Can unauthorized users view the records? | RBAC/ABAC, tenant scoping, encryption, field redaction, export controls |
| **Integrity** | Can a record be altered undetected? | Properly configured WORM/append-only, HMAC/signatures, independent checkpoints |
| **Authenticity** | Can the origin producing the evidence be verified? | Workload identity, mTLS, signatures, or ingest source authentication |
| **Completeness** | Are events missing, segments lost, duplicated, or out of order? | Sequences/checkpoints, reconciliation sources, heartbeats, ingestion monitoring |
| **Availability** | During an investigation, can old records still be read and understood? | Replication, backup/restore, schema versioning, preserving interpretation docs, retrieval RTO |

Disk encryption mainly addresses confidentiality; **it does not by itself prove a record was never deleted**. Plain SHA-256 detects differences against a trusted hash, yet anyone able to modify both record and hash can recompute it. Conversely, WORM blocks storage-level edits/deletes, yet does not verify that the producer sent accurate data in the first place.

## 3. Threat Model and Protection Architecture

Identify actors capable of distorting evidence:

1. **End users** trying to inject malicious text into logged fields (log injection), probe permissions, or halt logging via oversized payloads.
2. **Compromised applications** holding DB or collector credentials and attempting to alter or erase tracks within the same infrastructure.
3. **Operations staff** with privileges to read private data, bulk-export, shorten retention, or turn off logging.
4. **Storage/KMS administrators** able to alter retention, encryption keys, or access policies if duties are not separated.
5. **Accidental failures** including dropped events on full queues, clock skew, duplicate records, premature deletion, unrecoverable backups, and unreadable legacy formats.

Reference architecture:

```text
Spring Security / domain policies
      |
      | structured event (ID, UTC, schema, minimal fields)
      v
collector / queue with authentication + TLS
      |
      +--> alert/metrics on missing events, lag, invalid schema
      |
      v
canonicalization + classification + retention policy
      |
      +--> searchable index (HOT; read scope restricted)
      |
      +--> immutable/archive store (WARM/COLD)
      |       + encrypted + retention lock + separate admin
      |       + manifest/cryptographic checkpoint
      |
      +--> audit of access/export/policy/hold/deletion
      |
      v
investigation/authorized export -> evidence package + manifest
      |
      v
policy expiry + no active hold -> verified purge + disposal evidence
```

No single component alone creates an "unmodifiable" guarantee. Combine **least privilege, separated admin domains, time-locked immutable storage, cryptographic seals, ingestion monitoring, and restore testing**. A JSON row in an ordinary SQL table—even one whose API only calls `INSERT`—can still be altered if the same credential holds `UPDATE/DELETE` or DB admin privileges.

## 4. Retention Policy: Classify First, Set Durations Second

Retention durations must stem from **processing purpose, investigative needs, risk, contractual/legal requirements, data-protection duties, and cost**. No single "90 days" or "1 year" figure fits every event type or jurisdiction. NIST SP 800-53 AU-11 leaves organizations to define periods matching policy and investigative needs; OWASP recommends neither destroying before required retention nor keeping beyond necessary duration.

For each record class, the policy should specify:

- **Class and purpose**: e.g., `AUTHENTICATION_FAILURE`, `AUTHORIZATION_DENIED`, `ROLE_CHANGED`, `AUDIT_EXPORTED`, `POLICY_CHANGED`.
- **Data owner and policy owner**: unit accountable for retention purpose, change approver, and DPO/legal/security where applicable.
- **Retention clock**: measured from `occurredAt`, `receivedAt`, case closure, or obligation start; rules for late-arriving events.
- **Hot/searchable duration** and **total retention**: direct-query window differs from total archive lifetime.
- **Exception states**: legal holds, active investigations, disputes, evidence preservation orders, and who may lift them.
- **Storage locations and copies**: indexes, object archives, log aggregators, backups, replicas, snapshots, and external exports.
- **Deletion/disposal**: how deletion executes, where disposal is recorded, and how lingering unauthorized copies are prevented.
- **Recoverability**: archive restore time, format/schema versions, and keys that must be retained for reading.
- **Effective date and version**: retention policy changes must be reviewed and audited, never silently applied retroactively to existing data.

### 4.1. Illustrative Matrix, Not Mandatory Durations

| Event class | Fast search (example) | Total retention (example) | Reason to retain |
| --- | --- | --- | --- |
| Routine denials / failed logins | 30 days | 180 days | Probing detection and short-term investigations |
| Role/authority changes, admin actions | 90 days | 365 days | Permission and policy change traceability |
| Audit exports, retention/hold changes | 90 days | 730 days | Accountability for the audit store itself |
| Debug logs without audit events | 7 days | 14 days | Short-term troubleshooting; avoid over-retention |

The day counts above are **for design practice only**. Real systems must substitute durations validated for their legal context, data types, industry, and processing purposes. A single record may fall under multiple classes; precedence rules must be transparent and approved. Never let a developer-editable `application.yml` file serve as the sole authoritative source for legally binding retention periods.

### 4.2. Calculating Expiry and Handling Late-Arriving Data

Sample convention:

```text
retentionStart = occurredAt (UTC, if trusted and defined by policy)
retentionUntil = retentionStart + totalRetention
eligibleForPurge = now >= retentionUntil
                   AND legalHold = false
                   AND preservationCase = none
                   AND all required approvals/checks passed
```

Late-arriving data poses a challenge: an event occurred yesterday, yet the collector received it today. If policy counts from `occurredAt`, do not automatically extend retention upon re-ingestion; if source clocks are untrusted, define a fallback rule and store `receivedAt` for investigation. Use UTC time with explicit offsets/epochs in schemas; avoid timezone-less local timestamps in evidentiary data.

Clarify whether "keep 180 days" means 180 calendar days or six calendar months, and whether it runs from event time or case closure. A typical TTL job may purge **later** than the exact boundary due to asynchronous scanning; never advertise second-level deletion precision without supporting SLAs, independent verification, and backlog monitoring.

### 4.3. Hot, Warm/Cold, Archive, and Backup

- **Hot**: searchable index by actor/tenant/time/requestId; restrict fields, quotas, query permissions, and full-text searches over sensitive data.
- **Warm/cold**: lower-cost storage; retrieval may take longer, yet must have tested restore procedures and RTO/RPO targets.
- **Immutable archive**: normalized originals, manifests, checksums/HMACs or checkpoints, schema versions, and key ID metadata; restrict delete/modify rights.
- **Backups/snapshots**: carry their own retention and legal-hold rules; deleting from the index does not delete every copy. Track lifecycle, restore capability, and secure disposal.

Retention is not synonymous with **searchability**. When the hot index expires, it can be pruned quickly while originals stay in the archive until total expiry. Conversely, keeping an archive for years without its decoder, schema, or keys leaves unusable evidence in practice.

### 4.4. Legal Hold / Preservation Hold

A **legal hold** or **preservation hold** preserves a set of records needed for investigation/litigation even after normal expiry arrives. Control flow:

1. Receive a justified request identifying case ID, record scope, purpose, and approval authority.
2. Freeze deletion **before** the next purge run; apply across archives, indexes, and managed replicas as appropriate.
3. Record who requested, who approved, when, selection criteria, and storage location; avoid putting unnecessary sensitive contents into hold logs.
4. Bound and periodically review hold scope; once no longer needed, obtain release approval and audit the release action.
5. After release, **re-evaluate eligibility against active retention policy** and purge expired records if no other preservation duty remains.

Holds are not an excuse to keep all data forever. Nor should holds be implemented solely as a `legalHold=true` flag inside a deletable index: protect both the hold mechanism and the underlying storage enforcing it.

## 5. Access Control: Who Can Do What with Evidence?

Audit permissions must be treated as **high-sensitivity privileges**. Someone able to read all audits sees cross-user activity, tenants, network addresses, and investigative details. Someone able to delete or alter retention can erase tracks. Split permissions by **action**, **data scope**, and **sensitivity**, denying by default.

### 5.1. Reference Permission Matrix

| Role/identity | Write | Read/query | Export | Change policy/hold | Purge | Verify integrity |
| --- | --- | --- | --- | --- | --- | --- |
| Service producer | Emit new events via collector | No | No | No | No | No |
| Ingest service | Append to assigned stream | Only metadata needed for processing | No | No | No | Can check at ingest |
| SOC/incident investigator | Cannot edit records | Scoped to case/tenant/time | With approval | Propose hold | No | Yes |
| Independent auditor | No | Authorized scope only, read-only | Controlled | No | No | Yes |
| Retention policy administrator | No | Policy metadata | Not by default | Propose changes | Not directly | Can view reports |
| Hold approver | No | Needed case/metadata | Not by default | Approve hold/release | Not directly | Can view reports |
| Purge automation | No | Minimal metadata | No | No | Only eligible records | Records disposal proof |
| KMS/storage administrator | Not by default | Does not read business payloads | No | No | Not by default | Manages keys/anchors per policy |

This is a **design template**, not a fixed Spring Security role table. In practice, one person holding multiple roles can defeat separation of duties; enforce conflict-of-interest checks and two-person approval for high-risk actions.

Boundaries to protect simultaneously:

- **Application/API**: verified JWT/session/SSO, `SecurityFilterChain`, and method authorization; enforce tenant, case, and field-level visibility.
- **Database/index**: write-only credentials for collectors, appropriate read-only accounts for query services; never grant `UPDATE/DELETE` on archives to the main application.
- **Object storage**: retention locks, bucket policies, versioning/immutability where used; application accounts cannot shorten retention or delete evidence.
- **KMS/HSM**: separate key administration from decrypt/sign/verify operations; key changes must be audited and lifecycle-controlled.
- **SIEM/dashboards and exports**: SSO/MFA, ticket-backed JIT access, short sessions, rate limits, watermarks, query and export monitoring.
- **External copies**: analyst workstations, email attachments, support tickets, and exported files are also audit data requiring separate retention and access controls.

**Reading audits must itself be audited.** Record who queried/exported, purpose, scope, timestamp, returned record count, tool, and destination; avoid logging full sensitive query contents or results unnecessarily. Store audit-of-audit records in an appropriate stream, avoiding infinite loops if a sink reads its own internal logs.

### 5.2. Authorization Example in Spring Security

The snippet below is an **illustrative configuration integrated into an existing Servlet app with security**, not a standalone program. It protects an internal namespace; handlers/controllers and identity providers are supplied by the system:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(1)
SecurityFilterChain auditChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/internal/audit/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/internal/audit/**")
                .hasAuthority("AUDIT_READ")
            .requestMatchers(HttpMethod.POST, "/internal/audit/exports")
                .hasAuthority("AUDIT_EXPORT")
            .anyRequest().denyAll())
        .build();
}
```

Important notes:

- `securityMatcher` selects which chain applies. An application must also have a general chain protecting URLs outside `/internal/audit/**`. If no chain matches, requests may go unprotected by Spring Security.
- This is only the **initial HTTP layer**. Holding `AUDIT_READ` does not grant access to every tenant, actor, and case. The service/query layer must enforce authorized scopes, field filtering, pagination, and volume caps.
- `AUDIT_EXPORT` is separate from `AUDIT_READ`. Sensitive export requests typically require extra approval, justification, expiry, rate limits, and monitoring. Never turn a GET endpoint into a bulk downloader bypassing export controls.
- Authentication entry points, CSRF, sessions, CORS, TLS, and mTLS must match your real authentication mechanism. This chain alone **does not** configure authentication; cookie/session-based POSTs may also require CSRF tokens.
- `AUDIT_POLICY_ADMIN`, `AUDIT_HOLD_APPROVE`, and `AUDIT_PURGE_EXECUTE` (if present) must be checked independently and never lumped under `AUDIT_READ`. API permissions do not replace storage/KMS guards.

Service-layer enforcement example, also an **illustrative snippet**:

```java
@PreAuthorize("hasAuthority('AUDIT_READ')")
public AuditPage query(AuditQuery criteria, Authentication caller) {
    authorizedScope.check(caller, criteria.tenantId(), criteria.caseId());
    queryLimits.check(criteria);
    auditOfAudit.recordSearch(caller, criteria.safeSummary());
    return auditRepository.findRestricted(criteria);
}
```

Types like `AuditPage`, `AuditQuery`, `authorizedScope`, and `auditRepository` are **contracts the application must implement**. `@PreAuthorize` requires `@EnableMethodSecurity` and invocation through a Spring-managed bean (proxy). Scope checks must run server-side before querying; never trust client-supplied `tenantId` or filters. Field filtering/redaction must occur before serializing responses.

### 5.3. Operational Access Principles

- **Least privilege**: scope by tenant, case, time range, event type, environment, and fields. Deny cross-tenant access by default.
- **Separation of duties**: whoever edits retention cannot self-approve purges; key holders cannot also delete archives; the main app has no log-store admin rights.
- **MFA and JIT**: sensitive actions require strong authentication and time-bounded/case-scoped grants.
- **Break-glass**: requires justification, time limits, full logging, near-real-time alerting, and post-use review.
- **Exports**: produce encrypted packages, time-limited signed URLs, checksums/manifests, and recipient controls; log record/byte counts, approver, and expiry.
- **Periodic access reviews**: reconcile active staff/groups and service accounts; revoke rights upon role changes; audit actual permissions on indexes, archives, and backups.
- **Query abuse protection**: cap record counts, time windows, and export rates; enforce safe filtering/formatting and query monitoring; never render raw payloads containing tokens in UIs.

## 6. Integrity: "Unmodifiable" vs. "Tamper-Evident" Are Different

A trustworthy audit pipeline must deter unauthorized edits **and** detect signs of tampering. Complementary layers:

| Mechanism | What it addresses | Limitations |
| --- | --- | --- |
| Append-only / write-only credentials | Reduces edit risk from the app | Storage admins or escalated accounts can still modify |
| Object retention lock / WORM | Blocks edits/deletes during lock period | Does not ensure the sender emitted true events or didn't drop before ingest |
| TLS/mTLS in transit | Protects transit, can authenticate sender | Does not protect records once stored |
| SHA-256 stored alongside record | Detects bit flips against a trusted checksum | Anyone able to edit the record can recompute the hash if they control both |
| HMAC-SHA256 with protected key | Detects edits by adversaries lacking the key | Anyone holding the key can forge tags; requires role/anchor separation |
| Digital signatures + controlled keys | Verifies signing origin and integrity | Requires key management, rotation, and certificate/trust validation |
| Sequence-linked hash chain | Chains each record to the previous; detects edits/gaps inside verified slice | Tail truncation can evade local checks without an external checkpoint/expected count |
| Independently stored signed checkpoint/anchor | Detects post-anchor tampering and tail truncation | Depends on checkpoint cadence, key protection, and isolated storage |
| Ingestion monitoring, reconciliation sources | Detects lost data or anomalous streams | Cannot prove individual events occurred if the source itself was compromised |

**Tamper-evident** means unauthorized edits leave detectable evidence as long as verification mechanisms and trust in keys/checkpoints remain intact. Avoid claiming absolute "tamper-proof" immutability when most systems still have administrators, break-glass powers, deployment bugs, and ingestion boundaries.

### 6.1. Canonicalization Before Hashing/Signing

An audit record must serialize to bytes under **deterministic rules**: schema version, field order, UTF-8, length encoding, timestamp format, and number formatting. If two processes serialize JSON with different key order or whitespace before signing directly, identical business events can produce different hashes.

Recommended steps:

1. Validate schema, enforce length caps, strip forbidden fields, and normalize IDs/timestamps.
2. Use a versioned canonical byte format. For JSON, adopt an explicit canonical JSON scheme; never rely on any object's `toString()`.
3. Record sequence numbers and previous-record references **per defined stream/partition**.
4. Compute hash/HMAC/signature with keys stored and authorized outside application logs.
5. Write record + tag + key ID/storage metadata to an append-only/WORM store.
6. Periodically sign a checkpoint containing stream ID, last sequence, head digest, timestamp, and schema version; send checkpoints to an independent control domain.
7. Verifiers read originals, recompute from genesis or a trusted checkpoint, and check sequence/gaps, key version, tags, counts, and anchors.

In multi-instance systems, **do not assume a single global total order**. Partition by tenant/shard, maintaining per-stream sequences and checkpoints; explicitly define rules for concurrent appends, retries, and duplicate `eventId`s.

## 7. Standalone Java 17 Example: HMAC Chain and Truncation Detection

The following example illustrates cryptographic evidence. It uses Java 17's `javax.crypto.Mac`, `HmacSHA256`, `HexFormat`, and `record` **without Spring or external libraries**. Small dataset, single stream, single process, and a hard-coded demo key are for learning only; production systems require key management, immutable storage, out-of-domain signed checkpoints, access controls, and monitoring.

Create **`AuditChainDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class AuditChainDemo {

    // Demo only. NEVER store real keys in source or log files.
    private static final byte[] DEMO_KEY =
            "local-example-key-not-for-production"
                    .getBytes(StandardCharsets.UTF_8);

    record Event(
            String eventId, String occurredAt, String actorRef,
            String resource, String action, String decision) {}

    record Sealed(Event event, String previousTagHex, String tagHex) {}

    public static void main(String[] args) throws Exception {
        List<Sealed> records = new ArrayList<>();
        append(records, new Event(
                "event-1", "2026-11-05T08:00:00Z",
                "actor-17", "ORDER", "READ", "DENY"));
        append(records, new Event(
                "event-2", "2026-11-05T08:00:01Z",
                "actor-18", "AUDIT", "EXPORT", "ALLOW"));

        // Simulates a trusted anchor stored independently.
        String trustedHead = records.get(records.size() - 1).tagHex();

        System.out.println("original=" + verifyWithAnchor(records, trustedHead));

        List<Sealed> truncated = List.of(records.get(0));
        System.out.println("truncatedLocal=" + verifyChain(truncated));
        System.out.println("truncatedAnchor="
                + verifyWithAnchor(truncated, trustedHead));

        Sealed first = records.get(0);
        Event old = first.event();
        Event tampered = new Event(
                old.eventId(), old.occurredAt(), old.actorRef(),
                old.resource(), "DELETE", old.decision());
        records.set(0, new Sealed(
                tampered, first.previousTagHex(), first.tagHex()));
        System.out.println("tampered=" + verifyWithAnchor(records, trustedHead));
    }

    private static void append(List<Sealed> records, Event event)
            throws Exception {
        byte[] previous = records.isEmpty()
                ? new byte[32]
                : HexFormat.of().parseHex(
                        records.get(records.size() - 1).tagHex());
        byte[] tag = hmac(previous, event);
        records.add(new Sealed(
                event,
                HexFormat.of().formatHex(previous),
                HexFormat.of().formatHex(tag)));
    }

    private static byte[] hmac(byte[] previous, Event event)
            throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(DEMO_KEY, "HmacSHA256"));
        mac.update(previous);
        return mac.doFinal(canonicalBytes(event));
    }

    // Minimal canonical byte format, with version and length prefix.
    private static byte[] canonicalBytes(Event event) throws Exception {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (DataOutputStream output = new DataOutputStream(buffer)) {
            output.writeInt(1); // schema version
            for (String field : List.of(
                    event.eventId(), event.occurredAt(),
                    event.actorRef(), event.resource(),
                    event.action(), event.decision())) {
                byte[] utf8 = field.getBytes(StandardCharsets.UTF_8);
                output.writeInt(utf8.length);
                output.write(utf8);
            }
        }
        return buffer.toByteArray();
    }

    private static boolean verifyChain(List<Sealed> records)
            throws Exception {
        byte[] previous = new byte[32];
        for (Sealed record : records) {
            byte[] declaredPrevious;
            byte[] storedTag;
            try {
                declaredPrevious = HexFormat.of()
                        .parseHex(record.previousTagHex());
                storedTag = HexFormat.of().parseHex(record.tagHex());
            } catch (IllegalArgumentException malformedHex) {
                return false;
            }
            if (!MessageDigest.isEqual(previous, declaredPrevious)) {
                return false;
            }
            if (!MessageDigest.isEqual(
                    hmac(previous, record.event()), storedTag)) {
                return false;
            }
            previous = storedTag;
        }
        return true;
    }

    private static boolean verifyWithAnchor(
            List<Sealed> records, String trustedHead) throws Exception {
        if (records.isEmpty() || !verifyChain(records)) {
            return false;
        }
        byte[] actual = HexFormat.of().parseHex(
                records.get(records.size() - 1).tagHex());
        byte[] expected = HexFormat.of().parseHex(trustedHead);
        return MessageDigest.isEqual(actual, expected);
    }
}
```

Run in the file's directory (JDK 17+):

```bash
javac --release 17 AuditChainDemo.java
java AuditChainDemo
```

**Exact stdout** of the program, independent of external clocks:

```text
original=true
truncatedLocal=true
truncatedAnchor=false
tampered=false
```

Explanation of each outcome:

- `original=true`: both records and the current head match the HMAC chain and anchor.
- `truncatedLocal=true`: keeping only the first record still forms a **locally valid chain**. Therefore, an HMAC/hash chain alone **does not detect tail truncation**.
- `truncatedAnchor=false`: the truncated head no longer matches the independently stored head.
- `tampered=false`: changing `READ` to `DELETE` while keeping the old tag fails HMAC verification.

In the demo, `trustedHead` is only an in-process variable for illustration. **It is not yet an independent anchor**. In production, checkpoints must be signed and written to a separate system with segregated privileges, storing timestamp/sequence/key ID and undergoing verification; a compromised application must not be able to alter both records and checkpoints. This example also does not solve deleting an entire stream before the first checkpoint, forged events by a key holder, gaps from a silent producer, or recovering a deleted HMAC key.

### 7.1. Notes on Keys, Rotation, and Real Integrity

- Use strong random keys issued by KMS/HSM/secret managers; never store keys in repos, config logs, or responses. Restrict `MAC/sign` permissions to the required process; verifiers hold appropriate verification rights and trust anchors.
- With symmetric HMAC sharing one key, anyone holding the key can forge valid tags. To defend against privileged operators/apps with write access, isolate keys and anchors in an independent admin domain, or use asymmetric digital signatures where the signing key is inaccessible to archive editors.
- Record `keyId` and `algorithmVersion` with records/checkpoints. Rotation must not break verification of older records before retention expires; old keys need proper lifecycle, verify/decrypt access, and retirement plans.
- Canonicalization needs size limits, null handling, normalization, and explicit schema migration. Never use `event.toString()` or raw JSON with unspecified key order as evidence.
- With multiple partitions, verify each stream and checkpoint; add controls for **event completeness** such as expected sequences, counters, heartbeats, and backlog/ingestion alerts.
- HMAC **does not replace** retention policies, access controls, or secret protection. HMAC guarantees integrity only within the key's trust model.

## 8. Integrating with Spring Boot / Spring Security Properly

**Spring Security** is a source of events such as authentication and authorization denials. **Spring Boot Actuator** provides `AuditEvent`, `AuditEventRepository`, and listeners; `InMemoryAuditEventRepository` is convenient in development but should never be treated as a durable production audit archive. For real systems, pick storage/ingestion with backups, retention, access controls, integrity verification, and recovery capability.

Recommended flow:

1. Use appropriate Security/domain events to capture activities needing audit; normalize to a shared schema without dumping raw objects.
2. Record `eventId`, `requestId`/trace ID, UTC timestamp, actor/resource/action/decision, and sensitivity classification.
3. Deliver records to an authenticated collector with retries/idempotency and missing-event detection; decide whether **best effort** or **durable audit** is required.
4. Enforce retention/access rules in the policy service or controlled pipeline; never let producers set arbitrary expiry dates.
5. Write to query indexes and archives; generate tags/checkpoints, monitor ingestion, and alert on verification failures.
6. Query/export via separately authorized APIs; audit every search, export, hold, and purge action.
7. Upon expiry, purge per policy after checking holds, preserving needed manifests/checkpoints and reconciling copies.

One critical detail: `@EventListener` callbacks often run on the request thread; if a listener performs synchronous network or archive writes and the sink fails, it can add latency or disrupt requests. Use queues with load shedding and clear SLAs; **never** silently drop critical events when queues fill. Decide fail-open vs. fail-closed behavior per business criticality and monitor errors at every hop.

**Do not confuse an "audit trail" with application debug logs.** A plain `INFO` logger may rotate away after days, be disabled by config, or be cleared by operators. When audits serve as reliable evidence, design dedicated sinks, immutability, lifecycles, and independent access controls.

## 9. Timely Disposal and Proof of Destruction

A complete retention policy includes a **deletion lifecycle**. Saying "retain 365 days" without deletion jobs/monitoring easily leads to indefinite retention; conversely, `DELETE FROM audit_events WHERE created_at < ...` can destroy evidence under a legal hold.

Conceptual safe purge flow:

```text
Locate expired record/partition
  |
  +-- active hold / preservation case? --> KEEP and record hold reason
  |
  +-- unknown policy / missing metadata? --> QUARANTINE for review
  |
  +-- no hold, policy valid --> authorize purge batch
                                  |
                                  +--> archive/index/replica lifecycle
                                  +--> backups/exports per documented schedule
                                  +--> record disposal evidence
                                  +--> verify/alert on incomplete deletion
```

Disposal evidence should capture batch ID, selection criteria, policy version, time window, object/record counts, outcome, exceptions, approvals, and verification results. Never copy deleted payloads into the disposal log itself.

If a WORM object is still within its lock period, do not promise deletion before the lock expires; if legal deletion requests conflict with evidence-preservation duties, evaluate legally and design data minimization/retention upfront. **Cryptographic erasure** (destroying data encryption keys) can help in some architectures, yet requires examining key granularity, replicas, caches, backups, recoverability, and proof obligations; never assume it automatically satisfies every deletion requirement.

When shortening a retention policy from 365 to 180 days, evaluate its impact on existing data and active holds. A cron job reading a new policy file and immediately bulk-deleting everything is risky; require dry-runs, projected counts, approvals, batch limits, monitoring, and pre-commit abort controls under a governed workflow.

## 10. Investigation and Chain of Custody

**Scenario:** on November 5, an employee alleges that audit read access was abused last month. A usable system must prove records exist, their timestamps and origins, retrievability, integrity, and who accessed evidence after the incident opened.

Recommended workflow:

1. **Scope the case:** case ID, UTC window, actor/tenant/resource, and involved systems; use the least sensitive data sufficient for investigation.
2. **Preserve:** request and approve a preservation hold when warranted, record scope, and apply it at the storage layer before large queries/exports; verify the hold is enforced.
3. **Locate and reconcile:** fetch events by `requestId`/`traceId`, `eventId`, sequence, `actorRef`, action, and policy version; cross-check gateway, IAM, app, KMS, and object-access logs as needed.
4. **Verify integrity:** read independently stored manifests/checkpoints, verify signatures/HMACs/hash chains, record counts, time windows, sequences, and missing/gap status; never trust only a checksum sitting beside the file.
5. **Export evidence:** export only the approved dataset, generating a manifest with query scope, schema version, record count, file/package hashes, timestamp, tool, operator, and signatures/receipts if required.
6. **Hand off:** record recipient, time, purpose, and copy location; encrypt the package, grant time-limited access, track opens, and perform analysis on a copy.
7. **State bounded conclusions:** if an event is absent, distinguish "did not happen" from "not collected / expired / not found"; even when checksums pass, verify origin and completeness.
8. **Close the case:** review hold release with approval, re-apply retention, destroy exported copies per policy, and store the chain-of-custody record under proper classification.

Illustrative manifest example:

```json
{
  "evidencePackageId": "case-2026-17-export-02",
  "caseId": "case-2026-17",
  "createdAt": "2026-11-05T12:00:00Z",
  "rangeStart": "2026-10-01T00:00:00Z",
  "rangeEndExclusive": "2026-11-01T00:00:00Z",
  "recordCount": 184,
  "schemaVersion": 1,
  "files": [
    {
      "name": "audit.ndjson",
      "sha256": "value-calculated-during-export"
    }
  ],
  "checkpointReference": "independently-stored-signed-checkpoint-id"
}
```

The `value-calculated-during-export` and checkpoint reference values in the JSON are **schema illustrations**, not real signatures/hashes; never treat the example itself as an evidence record. Package SHA-256 checks whether the package changed after creation, while origin authenticity still relies on signatures/receipts and key/anchor protection.

## 11. Monitoring, Alerting, and Operational Ownership

Establish policy-driven telemetry signals, for example:

| Signal | Why it matters | Response |
| --- | --- | --- |
| Collector misses expected heartbeats/events | Signal loss or disabled logging | Alert, verify producers/queues |
| Rising ingest lag, retries, or dead-letter counts | Risk of missing audits after incidents | Investigate queues and backpressure |
| Sequence gaps / duplicate `eventId`s | Missing or replayed records | Reconcile with source, quarantine batch |
| HMAC/signature/checkpoint verification failure | Sign of tampering, key/schema bug, or corruption | Isolate copy, preserve evidence, investigate |
| Retention/hold/key or bucket policy changes | Can break verifiability or retention | Require change approval, audit, and alert |
| Unusual or cross-tenant queries/exports | Risk of audit data exposure | Rate-limit, investigate permissions and case |
| Archive restore failures | Logs exist but cannot be used | Fix backups/keys/schemas, run restore drills |
| Growing purge backlog or premature deletion | Fails retention compliance or over-retains | Halt faulty job, inspect policy/holds |
| Sudden disk/quota/cost spike | Risk of denial of service via logging | Bound inputs, scale, declare incident |

Assign clear owners: event schema owner, retention owner, security operations, privacy/legal, storage/platform, KMS, and incident manager. Conduct periodic reviews of read access and policy versions. Audits serve as reliable evidence only when **monitoring of the audit pipeline itself** is operated and tested.

## 12. Mandatory Pre-Production Test Matrix

| Test | How to trigger | Outcome to verify |
| --- | --- | --- |
| Insufficient read permission | User without `AUDIT_READ` calls query API | Denied; zero records or sensitive metadata leaked |
| Read-only permission | User with `AUDIT_READ` attempts export | Blocked or routed through separate approval; no bulk download |
| Wrong tenant/case scope | Investigator queries another tenant | Blocked at domain/query layer despite broad authority |
| Ingest account attempts UPDATE/DELETE | Use producer/collector credentials | Storage denies modifying/deleting originals |
| Modified record | Alter test content after sealing | HMAC/signature verification fails |
| Tail truncation / missing segment | Drop last record or omit sequence | Checkpoint/expected count detects gap |
| Collector down / queue full | Fault injection in test environment | Alerts, retry/DLQ, controlled handling; no silent loss |
| Retention just expired | Advance mock clock past cutoff | Purged per policy, reporting counts and metadata; no early delete |
| Active hold | Place hold on expired record before job | Record kept; evidence shows purge skipped it |
| Hold released | Approve release and re-run policy | Only eligible records deleted; action audited |
| Old backups / cold archive | Restore long-stored records | Schema readable and tags/checkpoints verify |
| Key rotation | Switch to new key for subsequent records | Old records remain verifiable until retention expiry |
| Audit query/export | Authorized staff retrieves records | Generates audit-of-audit with actor, scope, time, outcome |
| Export/manifest | Modify exported file after creation | Checksum/receipt verification fails |
| Log injection / oversized input | Send newlines, control chars, huge payloads | Format intact, no secret leak or storage exhaustion |

Also test recovery from prolonged disconnects, retry duplicates, clock skew, policy rollbacks, revoked service accounts, and security events dropped due to misconfigured filters/controllers. A single "API returns 403" test never proves audits are durable or tamper-evident.

## 13. Common Mistakes and Fixes

1. **Keeping logs only in RAM or pod stdout:** lost on restart; move to collectors and retention-backed stores, and test restores before claiming durability.
2. **One global TTL for all audit types:** events have different risks, laws, and needs; classify with explicit policy versions, owners, and holds.
3. **Confusing index lifetime with total retention:** pruning the hot index does not delete archives; keeping archives does not ensure fast search; publish both durations clearly.
4. **Granting `ROLE_ADMIN` full read/delete over audits:** app admins can erase their own tracks; apply least privilege, separate query/export/purge, and isolate storage/KMS.
5. **Hashing files with SHA-256 and storing the hash beside the file:** anyone able to edit both recomputes the hash; use independently signed/sealed anchors, keys, and permissions.
6. **Assuming hash chains catch every deletion:** deleting the tail can leave a valid prefix chain; verify head checkpoints/record counts externally.
7. **Logging raw data "just in case for investigation":** increases privacy risk and secret leaks; stick to minimal fields, route templates, pseudonymization, and schema allowlists.
8. **Losing old keys right after rotation:** restored archives become unverifiable/unreadable; manage key versions and retain them for the data's lifetime.
9. **Disabling logging silently when the sink fails:** creates evidence blind spots; implement queues, retries, backpressure, alerts, and approved failure rules.
10. **Purging on expiry while forgetting holds, backups, and exports:** risks premature deletion or over-retention; keep a copy inventory and coordinate deletions/exceptions across copies.
11. **Trusting raw `X-Forwarded-For` or user-supplied actorId:** attackers can spoof them; rely only on verified context and trusted proxies.
12. **Not auditing audit reads:** impossible to trace who mined the audit store; run independent audit-of-audit logging and anomaly alerts.
13. **Keeping archives without schemas/docs/decoders:** old evidence becomes uninterpretable; version schemas and run restore drills.
14. **Policies existing on a wiki without enforcing jobs:** build expiry/hold tests, monitor backlogs, and reconcile live config with approved policies.

## 14. Design Exercise

Suppose an ordering system uses Spring Security with three event groups: `AUTHORIZATION_DENIED`, `ADMIN_ROLE_CHANGED`, and `AUDIT_EXPORT_CREATED`. Operations wants 30-day fast search, investigators may need older records, some cases are under hold, and auditors may view only assigned cases.

Draft your own:

1. **Retention matrix** for the three classes, including owner, retention start, hot/archive durations, legal hold rules, archive restore targets, and policy version. Clearly mark all day counts as exercise assumptions.
2. **Access matrix** for producer, SOC, auditor, retention admin, hold approver, purge automation, and KMS admin. Specify who can view, export, edit policies, purge, and sign checkpoints.
3. **Integrity plan**: choose canonical format, sequence scope, HMAC or signatures, independent checkpoints, missing/truncated stream detection, and key rotation handling.
4. **Incident workflow**: someone detects an unauthorized audit export. Specify request/trace IDs, audit-of-audit, hold placement, checksum/signature verification, chain of custody, and hold release.
5. **Validation**: at least one wrong-tenant access test, one delete-under-hold test, one tail-truncation test, and one archive-restore test.

Self-check question: if an NDJSON file and its SHA-256 checksum sit in the same bucket where one admin account can modify both, do you have trustworthy integrity yet? **No**: an adversary can modify the file and recompute the checksum. You need restricted permissions, storage immutability, or anchors/seals in a separate trust domain, alongside event-completeness checks and governed ingestion.

## 15. Official Documentation and Reference Guides

- OWASP, [Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) — fields to exclude, access limits, transit/storage protection, tamper checks, disposal, and logging failure tests.
- NIST, [SP 800-92 — Guide to Computer Security Log Management](https://csrc.nist.gov/pubs/sp/800/92/final) — structuring log management infrastructure and processes across systems.
- NIST SP 800-53 Rev. 5, **AU-9 Protection of Audit Information**, **AU-11 Audit Record Retention**, **AU-12 Audit Record Generation** — control families for protecting audits, setting organizational retention, and generating records; consult the current standard when assessing compliance.
- Spring Boot, [Auditing](https://docs.spring.io/spring-boot/3.5/reference/actuator/auditing.html) — `AuditEventRepository`, audit listeners, and limits of in-memory stores.
- Spring Security, [Authorization Events](https://docs.spring.io/spring-security/reference/servlet/authorization/events.html) — receiving authorization events to feed a controlled audit pipeline.
- OWASP, [Developer Guide: Logging and Monitoring](https://devguide.owasp.org/en/04-design/02-web-app-checklist/09-logging-monitoring/) — security logging, access control, and integrity protection.

**Remember:** Trustworthy auditing requires **retaining long enough yet not past expiry**, **letting only authorized people access their authorized scope**, and **proving integrity as well as detecting missing data**. These three requirements must be enforced by permissions, storage, keys, approval workflows, and tests—never by a mere `logger.info(...)` call.