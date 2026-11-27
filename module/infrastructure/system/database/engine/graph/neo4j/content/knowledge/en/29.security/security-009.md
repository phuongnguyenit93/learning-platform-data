# Audit Logging and Protecting Sensitive Data When Supported

In a Neo4j application, read/write access control is only half of security. When unauthorized access or suspected data tampering occurs, operations teams also need to answer: **who did what, when, from where, with what outcome, and is the evidence trustworthy?** Conversely, if logs record too much detail, the log files themselves can end up holding emails, national IDs, query contents, parameters, and private relationships that the system is trying to protect.

This lesson belongs to the **Security** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module, where Neo4j is used to model data as a **property graph**, query nodes and relationships via Cypher, manage indexes/constraints, integrate Java Driver and Spring Data Neo4j, and operate graph systems. The focus is **audit logging and protecting sensitive data when supported by the version, edition, or managed service**, combining database, application, and infrastructure controls.

After this lesson, you will be able to:

- Distinguish `security.log`, `query.log`, operational logs, and business audit logs.
- Identify which events Neo4j logs out of the box, which ones the application must log, and what **cannot be inferred** from logs.
- Configure query logging to limit exposing literals, parameters, errors, and sensitive metadata.
- Apply least privilege, property protection, and tenant boundaries while recognizing edition/version limits.
- Design an audit event bound to graph-mutating transactions and a log-forwarding pipeline to controlled storage.
- Test unauthorized access, data-leakage risks in logs, log loss, rollbacks, rotation, and post-incident recovery.

> **Feature limits:** Neo4j Community, Enterprise, AuraDB, and different Aura tiers do not share identical administration, logging, or authorization capabilities. Setting names can also change across release lines. Verify every administrative example against **the documentation and permissions of your actual running system**; never run directly on production without a change-control process.

## 1. Threat modeling before enabling logs

Suppose a system manages customer profiles and orders:

~~~text
(:SecDemoCustomer {
  tenantId, customerId,
  displayName, email, phone, nationalId
})
       |
       | [:SEC_DEMO_PLACED]
       v
(:SecDemoOrder {
  tenantId, orderId,
  amountMinor, status
})
~~~

Different fields carry different sensitivity levels:

| Information type | Examples | Risk if exposed |
| --- | --- | --- |
| Internal identifiers | `customerId`, `orderId` | Used to link and infer profiles when combined with other data. |
| PII / contact info | `email`, `phone`, `nationalId` | Privacy violation, phishing, or identity correlation. |
| Financial data | `amountMinor`, transaction status | Exposes behavior, transaction amounts, or business secrets. |
| Relationship structure | Who connects to whom, purchases, organizational ties | Can reveal sensitive facts even when names are hidden. |
| Operational metadata | Username, IP, query text, transaction metadata | Can leak identifiers and system details for further attacks. |
| System secrets | Passwords, access tokens, API keys, private keys | Can lead to full access takeover. **Never log raw secrets.** |

Graphs require special attention to **inference from relationships**. A response containing only node names or edge counts can still reveal that two people belong to the same sensitive group. Therefore, protecting **node properties** is necessary but insufficient; you must also control relationship traversal, discovery, and export.

### 1.1. Security and audit objectives

Objectives fall into four groups:

1. **Prevent unauthorized access:** authentication, authorization, and tenant/object/field scoping.
2. **Minimize operational data leakage:** keep sensitive data out of query logs, exceptions, traces, and gateway logs.
3. **Preserve traceable evidence:** capture actor, action, target, outcome, request ID, and timestamp.
4. **Protect the evidence itself:** restrict log modification/deletion, store durably, monitor log loss, and enforce retention/deletion policies.

**Logging does not replace authorization.** A system that merely records someone reading unauthorized data still leaked the data before an alert fired. Logging is the detection/investigation layer; privileges and query design form the prevention layer.

## 2. Do not call every log type an "audit log"

Neo4j and the application layer produce multiple telemetry streams, recording **different events**:

| Source | Primary purpose | What it helps investigate | What must not be inferred |
| --- | --- | --- | --- |
| **`security.log`** (when supported) | Record Neo4j security events. | Successful/failed logins, admin commands, authorization failures, and supported auth events. | Does not automatically log **every node/property a user viewed**. |
| **`query.log`** (when supported) | Observe queries and performance. | Executed queries, timing, client source, success/error status, and metadata per config. | Not automatically a full data-change log; does not log result payloads returned to clients. |
| **`neo4j.log` / `debug.log`** | Operations, errors, and diagnostics. | Database startup, service faults, errors needing investigation. | Does not guarantee recording business actors/actions. |
| **`http.log` / gateway logs** | HTTP-layer access. | Request source, endpoint, status, latency when enabled. | Cannot determine all Cypher/Bolt data returned. |
| **Application audit events** | Track business actions. | Who approved a profile, changed roles, exported data, edited an order. | Does not by itself prove DBAs/superusers could not edit logs in the same database. |
| **Infra / cloud / IdP logs** | Resource, connectivity, and identity admin. | Config changes, cloud permissions, login sessions, snapshot exports. | Does not replace application-layer data checks. |

In self-managed Neo4j Enterprise, Neo4j documentation describes `security.log` as recording security events including logins, `system` database admin commands, and authorization failures, while `query.log` records queries per configuration policy. These features are edition-constrained. In Neo4j Aura, certain tiers provide **query/security logs** in the console and an **activity feed** tracking org/project actions; do not assume host-level log file access as in self-managed deployments.

**Key point:** if an application connects to Neo4j via a shared service account, database-side `security.log` or `query.log` may show only the **service account**, not which end user opened a record. When end-user traceability is needed, the application must emit authenticated actor and correlation IDs under a protected logging policy.

## 3. Which events require auditing?

Not every system needs to log all reads identically. Prioritize by action type and business requirements:

| Action | Example | Suggested evidence source |
| --- | --- | --- |
| Login / failed login | User or service account logs into Neo4j. | Security log / IdP when supported and in scope. |
| Role/privilege changes | Granting a privilege to a user/role. | Security log and identity governance systems. |
| Reading sensitive records | Staff viewing customer details. | API/service audit event carrying end-user identity. |
| Bulk data export | Exporting a customer list. | Dedicated audit event, export job event, storage logs. |
| Modifying properties | Changing email, order status, contact info. | Business audit event tied to the committed transaction. |
| Modifying relationships | Linking an account to an org, adding member roles. | Audit event describing type and allowed target IDs. |
| Deletion / anonymization | Deleting per valid request. | Audit metadata on request, subject, completion status; avoid keeping PII in audit. |
| Backup / restore / config edits | Creating backups, restoring DB, or altering retention. | Infrastructure admin logs, activity feed, or platform mechanisms. |

A useful audit record typically needs:

- **Actor:** internal identifier of the authenticated person/service, distinguishing `onBehalfOf` and technical accounts where applicable.
- **Action:** stable semantic action code such as `CUSTOMER_PROFILE_READ` or `CUSTOMER_EMAIL_CHANGED`.
- **Target:** entity type and the **least sensitive identifier possible**.
- **Outcome:** `SUCCEEDED`, `DENIED`, `FAILED`, or `PENDING` with unambiguous semantics.
- **Time:** timestamp with explicit timezone, clock-synchronized across systems.
- **Context:** tenant, request ID/trace ID, origin, or access purpose when required.
- **Integrity:** unique event ID, audit record schema version, sink/source metadata, and durable forwarding status.

Do not record full before/after values of sensitive fields merely "for completeness." Often only the **names of changed fields**, action code, and protected record reference are needed; if before/after values are legally required, apply separate access controls and encryption.

## 4. Logging approach by deployment model

### 4.1. Self-managed Neo4j

In self-managed environments, operators configure logging according to what the Neo4j release supports:

- Verify edition, version, and security settings before expecting `security.log` or `query.log`.
- Configure Log4j settings, file paths, OS permissions, rotation, and forwarding per organizational standards.
- Restrict who can read log files and backups; the OS account running Neo4j must not be an over-privileged personal account.
- Monitor disk capacity, log write throughput, and log-shipper health to central observability.

Neo4j 2025/2026 documentation uses `server-logs.xml` for server logs such as `debug.log`, `query.log`, and `security.log`. Older versions may use different setting names and paths; **do not copy 4.x configs into 2025+ releases without checking**.

### 4.2. Neo4j Aura

In managed services like Aura, log infrastructure and viewing access are exposed **via console/API** depending on tier. Features like exporting query/security logs or activity feeds may be bounded by role, retention window, volume, and service tier. Never assume SSH access to Aura hosts or editing `neo4j.conf` as in self-managed setups.

When auditing is mandatory, verify which logs your **current tier** provides, whether SIEM export is supported, and what latency and retention apply. If platform logs do not capture end-user profile reads, implement auditing at the application layer.

### 4.3. Community Edition and fine-grained access

Basic user management exists in Neo4j Community, yet **role-based, property-based/fine-grained access control and Enterprise logs** must not be assumed present. When the environment lacks native controls:

- Place Neo4j in a private network accessible only to authorized services.
- Enforce authorization in the backend; never issue Neo4j accounts directly to untrusted clients.
- Restrict fields and traversal paths at the API; avoid `RETURN n` or `RETURN *` on sensitive entities.
- Use application/IdP/gateway logs for traceability and forward them to controlled storage.
- For strict isolation mandates, evaluate an edition/tier with DB-enforced controls or separate database environments.

Application-only authorization can be bypassed if any direct path to Neo4j exists. Thus, **strictly restricting network connectivity to the DB** is essential whenever relying on application-layer controls.

## 5. Configuring query logs to reduce leakage risk

Query logs are valuable for performance and debugging, yet the biggest risk is **query text and parameters containing PII or secrets**. Example:

~~~cypher
// DO NOT place sensitive information directly into literal queries.
MATCH (c:SecDemoCustomer {email: 'real-person@example.invalid'})
RETURN c;
~~~

If query text is logged without literal obfuscation, the email appears in `query.log`. Switching to parameters separates query structure from input data while avoiding Cypher string concatenation:

~~~cypher
MATCH (c:SecDemoCustomer {email: $email})
RETURN c.customerId AS id,
       c.displayName AS name;
~~~

However, **parameterization is not enough**: if parameter logging is enabled, `$email` values can still be logged. Furthermore, `RETURN c` at the API can expose unnecessary sensitive properties; use controlled field projections.

### 5.1. An illustrative data-aware configuration

The example below targets **self-managed releases supporting the corresponding settings**, using modern Neo4j setting names; this is not a universal safe default for every system:

~~~properties
# neo4j.conf - example selective query logging policy
db.logs.query.enabled=INFO
db.logs.query.threshold=500ms
db.logs.query.parameter_logging_enabled=false
db.logs.query.obfuscate_literals=true
db.logs.query.early_raw_logging_enabled=false
~~~

Meaning:

| Setting | Effect | Trade-offs to consider |
| --- | --- | --- |
| `db.logs.query.enabled=INFO` | Logs queries upon completion when exceeding threshold. | **Does not create a full history** of queries under the threshold. |
| `db.logs.query.threshold=500ms` | Focuses on slow queries. | Omits fast queries that may still be sensitive; not a complete audit. |
| `db.logs.query.parameter_logging_enabled=false` | Suppresses parameter values in query logs. | Reduces debugging detail; does **not** control application logs. |
| `db.logs.query.obfuscate_literals=true` | Masks many literals inside query text. | Does not mask all structural tokens; does not mask parameters if parameter logging is on. |
| `db.logs.query.early_raw_logging_enabled=false` | Avoids early raw query/parameter logging in this mode. | Verify other settings and full logging policies. |

Neo4j 2026 releases add `db.logs.query.obfuscate_errors` (introduced in 2026.01.x) to redact sensitive information from errors in query logs. **Enable only if supported by your running version** and verified in testing:

~~~properties
# Apply only on versions supporting this setting.
db.logs.query.obfuscate_errors=true
~~~

Notes:

- Enabling obfuscation alone does **not** guarantee all sensitive details vanish: label names, relationship types, property names, and certain syntax literals may still appear.
- `db.logs.query.max_parameter_length`, when set, only **truncates logged parameter length**—it is not a reliable redaction control.
- Turning on verbose/tracing modes during an incident increases data capture; enforce approval, time limits, and post-check log review.
- On some versions, toggling literal obfuscation does not affect already-cached queries; operational runbooks may need to clear query caches per version docs.
- Logging configs, sinks, and query capture in **Java/Spring apps, reverse proxies, and APM agents** must be audited separately.

**Never treat `query.log` as a complete audit trail.** `INFO` mode with thresholds skips fast queries; even logging every query does not automatically identify end users, actually read nodes/fields, response payloads, or business intent.

### 5.2. Verify settings instead of guessing

On versions supporting `SHOW SETTINGS` with an authorized account:

~~~cypher
SHOW SETTINGS
YIELD name, value
WHERE name IN [
  'db.logs.query.enabled',
  'db.logs.query.threshold',
  'db.logs.query.parameter_logging_enabled',
  'db.logs.query.obfuscate_literals',
  'db.logs.query.early_raw_logging_enabled',
  'db.logs.query.obfuscate_errors'
]
RETURN name, value
ORDER BY name;
~~~

If a setting does not exist in your version, do not force it into config. Dynamic setting changes may be **per-server** and not propagate cluster-wide; runtime changes may also disappear after restarts unless persisted to config files. On Aura, use platform-exposed controls rather than assuming `SHOW SETTINGS` implies permission to alter every setting.

## 6. What does security.log capture and what does it miss?

In self-managed Neo4j Enterprise with authentication enabled, `security.log` captures events such as:

- Successful and failed logins (logging successful logins may be configurable per policy).
- Administrative commands for users, roles, and privileges on the `system` database.
- RBAC authorization check failures.
- Certain events from external authentication providers such as LDAP, depending on configuration.

Illustrative example **with specific identifiers redacted**, not a fixed format contract:

~~~text
2026-11-25T08:00:01Z INFO  [svc-graph-read]: logged in
2026-11-25T08:01:10Z ERROR [unknown]: failed to log in
2026-11-25T08:03:00Z INFO  [admin-user]: GRANT ROLE ...
~~~

If an organization needs to prove "end user X viewed customer Y's phone number," a login entry for `svc-graph-read` **cannot answer that**. The application must extract the authenticated principal at the API, check privileges, and emit a `CUSTOMER_CONTACT_VIEWED` audit event referencing target Y and the access outcome.

### 6.1. Option to log successful authentication events

Supporting self-managed releases offer:

~~~properties
dbms.security.log_successful_authentication=true
~~~

Logging every successful login aids investigations, though it can generate high volume if services open connections or re-authenticate frequently. Before reducing logs when business policy allows, verify compliance rules and impact. **Disabling successful-login logs can eliminate evidence needed for audits**, so never disable it purely to save disk space.

### 6.2. From security logs to a SIEM

When forwarding events to a SIEM or centralized log platform:

1. Ship logs over encrypted channels using a collector account with minimal privileges.
2. Normalize UTC timestamps, event types, severity, source host/instance, user, and request ID if present.
3. Keep **raw data in restricted-access storage** for investigations while dashboards display reduced-sensitivity views.
4. Configure anomaly alerts: repeated login failures, out-of-window admin grants, bulk role edits, export spikes, or sensitive queries.
5. Monitor collector lag, sequence/time-window gaps, and parse failures, because **log loss** is itself a critical operational event.

Log formats and fields vary by version and JSON layout, so parsers must not depend on one single message sample. Never claim a forwarding pipeline is *tamper-proof* if privileged admins can alter both the source and the destination store.

## 7. Protecting sensitive data at the access-privilege layer

The application layer must enforce **least privilege**:

- APIs reading basic profiles do not need permission to read every property on `SecDemoCustomer`.
- Reporting services need aggregated metrics, not raw email, phone, or every personal relationship.
- Data-writer accounts need no user/role management or backup privileges.
- Log-collector accounts need read access to log sources, never graph mutation rights.
- Operators should not share one admin account across all jobs.

### 7.1. Neo4j fine-grained access control when supported

Neo4j Enterprise and certain Aura tiers provide fine-grained authorization to control **TRAVERSE** on nodes/relationships and **READ** on properties per role; some releases also support conditions based on property values (*property-based access control*).

Illustrative example for a **learning database** with sufficient admin privileges (role-management commands run against `system` or are routed appropriately by the driver):

~~~cypher
CREATE ROLE secDemoReader IF NOT EXISTS;
~~~

~~~cypher
GRANT ACCESS ON DATABASE neo4j TO secDemoReader;
~~~

~~~cypher
GRANT TRAVERSE ON GRAPH neo4j
NODES SecDemoCustomer TO secDemoReader;
~~~

~~~cypher
GRANT READ {displayName} ON GRAPH neo4j
NODES SecDemoCustomer TO secDemoReader;
~~~

This is a property-read **allowlist** example. The role cannot read `email`, `phone`, or `nationalId` unless other assigned roles grant them. However, users can hold **multiple roles**, so always verify effective merged privileges; never assume a narrow role revokes privileges granted by another role.

If the application filters or compares by `tenantId` or `customerId`, carefully review required `READ/MATCH/TRAVERSE` privileges, how queries use properties, and identifier-protection policies. **Granting `TRAVERSE` alone does not mean property-filtering queries will work as expected.**

Example role inspection by an authorized administrator:

~~~cypher
SHOW ROLE secDemoReader PRIVILEGES AS COMMANDS;
~~~

Test `GRANT/DENY` rules against synthetic data using a test account **holding no other powerful roles** before rollout. Depending on version, specific privileges may also be needed to execute procedures, manage indexes, or access databases.

### 7.2. Property-based access is not magic tenant isolation

Some versions/editions support `GRANT ... WHERE property = value` rules to restrict traversal/reads. Still, **never assume** you can write one rule referencing an arbitrary dynamic logged-in `tenantId` without corresponding privilege configuration. For multi-tenancy:

1. Define the identity source and list of authorized tenants.
2. Decide enforcement boundaries across Neo4j, APIs, or separate databases.
3. Constrain queries from start nodes to **every expanded endpoint** within the valid scope.
4. Test paths, aggregations, and functions that could infer links.
5. Run **tests with real user/role accounts** to catch conflicts across multiple `GRANT`/`DENY` rules.

With property-based rules, test **missing/null** properties, version rule semantics, write rights on the condition property, and `DENY` cases that might evaluate unexpectedly. Never rely on a single deny expression as a strong boundary if records can lack the guarded property.

### 7.3. Secure projections in Cypher

Query reading public profile info:

~~~cypher
MATCH (c:SecDemoCustomer {
  tenantId: $tenantId,
  customerId: $customerId
})
RETURN c.customerId AS id,
       c.displayName AS displayName;
~~~

Avoid patterns such as:

~~~cypher
// Unsuitable for APIs allowed to return only public information.
MATCH (c:SecDemoCustomer {customerId: $customerId})
RETURN c;
~~~

The second query omits tenant scoping and risks returning **every property** on the node, including fields added in the future. Even with database authorization, the API must still project only fields needed for the use case and disable debug serialization that dumps full entities.

**Never trust a client-sent `$tenantId` as proof of authorization.** The service must resolve the tenant from a verified principal/claim and reject cross-tenant requests.

## 8. Encryption, minimization, and data lifecycle

### 8.1. Encryption in transit

For connections from Java Driver / Spring Data Neo4j:

- Use encrypted connection schemes with trusted server certificate verification matching your Bolt/TLS deployment.
- Enforce HTTPS between clients and APIs; secure links across reverse proxies, backends, Neo4j, and log sinks.
- Never disable certificate checks or use trust-all configs in production just to "get connected."
- Restrict Bolt, HTTP, backup, and cluster ports via network segmentation and firewalls to required sources only.

Do not confuse **in-transit** encryption with protecting data stored on disk or in backups.

### 8.2. Encryption at rest

In self-managed environments, data-at-rest protection includes infrastructure-managed volume/disk encryption, filesystem permissions, restricted backup/dump access, key management, and tested restore plans. On managed services, verify encryption-at-rest and key-management features for your tier.

**Do not assume** Neo4j individually encrypts node properties when applications pass values in Cypher. When a specific field must remain confidential even from storage readers:

- Consider **application-layer encryption** using vetted key management—never invent custom ciphers.
- Design how search, sorting, uniqueness, and indexes work once values become ciphertext.
- Keep encryption keys out of graph properties, logged query parameters, committed configs, and audit records.
- Assess information leakage via **relationships, access frequency, and metadata** even when property payloads are encrypted.

For example, if `email` is encrypted with randomized encryption, exact matching `WHERE c.email = $email` will no longer work directly. You may need a separate lookup token/HMAC index designed under organizational security standards, paired with correlation-risk analysis. **Never use an unsalted/unkeyed hash of an email as safe anonymization**, since emails can be guessed from common value sets.

### 8.3. Data minimization and retention

Every sensitive property needs a clear purpose, access policy, and retention limit. Consider:

- Store `phone` only when a business feature requires it; avoid copying every source column by habit.
- Purge or detach expired data through approved workflows, including read replicas, caches, exports, and backups per policy.
- Keep raw payloads out of audit events when the goal is only proving an action occurred.
- When erasing personal data, retain **minimal audit metadata** without creating a shadow PII store kept indefinitely.

Retention policies depend on laws, regulations, and contracts; durations in exercises are illustrative, not legal advice.

## 9. Designing a business audit trail in a Neo4j application

A business API may need proof that the service updated a node and created an audit record **within the same transaction**.

Conceptual flow:

~~~text
API (authenticated principal)
        |
        v
Service checks tenant + field permissions
        |
        v
BEGIN Neo4j TRANSACTION
  - update (:SecDemoCustomer)
  - create (:SecDemoAuditEvent {auditId,...})
COMMIT
        |
        v
Collector/Exporter may forward audit events
    to an external append-only store
~~~

Inside the database, a minimal audit event can hold:

| Field | Role | Privacy note |
| --- | --- | --- |
| `auditId` | Unique key preventing duplicate audit events. | Never reuse after deleting business records. |
| `requestId` | Correlates an API request with logs/traces. | Must not contain tokens or arbitrary PII. |
| `actorRef` | Authenticated user/service identifier. | Can be a pseudonymous ID; restrict lookup of mappings. |
| `action` | Stable action code. | Use enums/codes; avoid descriptions containing user content. |
| `targetType` / `targetRef` | Type and identifier of affected target. | Can be sensitive if internal IDs are easily linked. |
| `tenantRef` | Data scope aiding investigations. | Control log access per tenant. |
| `result` | Whether the action applied. | In-transaction events prove success only after commit; failures need another path. |
| `occurredAt` | Event timestamp. | Verify UTC/timezone and clock skew. |
| `fieldsChanged` | List of changed **field names**. | Never include old/new email or phone values. |

### 9.1. Constraints and single-transaction writes

Run examples only on a **practice database** with schema permissions; never use real customer IDs:

~~~cypher
CREATE CONSTRAINT sec_demo_audit_id IF NOT EXISTS
FOR (a:SecDemoAuditEvent)
REQUIRE a.auditId IS UNIQUE;
~~~

A Cypher statement updating display name and creating an audit event:

~~~cypher
MATCH (c:SecDemoCustomer {
  tenantId: $tenantId,
  customerId: $customerId
})
SET c.displayName = $newDisplayName
CREATE (a:SecDemoAuditEvent {
  auditId: $auditId,
  requestId: $requestId,
  actorRef: $actorRef,
  action: 'CUSTOMER_DISPLAY_NAME_CHANGED',
  targetType: 'CUSTOMER',
  targetRef: $customerId,
  tenantRef: $tenantId,
  result: 'APPLIED',
  fieldsChanged: ['displayName'],
  occurredAt: datetime()
})
RETURN c.customerId AS customerId,
       a.auditId AS auditId;
~~~

**Mandatory conditions:**

1. The API already authenticated the actor, checked customer-update permissions, and bound tenant from security context before running the query; never accept an arbitrary `actorRef` from clients.
2. `$auditId` and `$requestId` are system-generated/validated and contain no secrets. For retries, enforce idempotency by action key to prevent duplicate business mutations.
3. `MATCH` might match nothing: then **neither the update nor the CREATE executes**, and the query returns 0 rows. The service must treat 0 rows as unsuccessful, never reporting success.
4. If creating the audit event or checking constraints fails, the entire transaction rolls back. Splitting them into separate auto-commit transactions loses this guarantee.
5. The example writes the new value to the business node while **omitting sensitive values from the audit event**. If auditing legally requires before/after values, use dedicated controls.

Integrating with Java Driver:

~~~java
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Record;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class CustomerAuditService {
    private final Driver driver;

    public CustomerAuditService(Driver driver) {
        this.driver = driver;
    }

    public String changeDisplayName(
            String tenantId, String customerId,
            String newName, String actorRef,
            String requestId, String auditId) {
        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            return session.executeWrite(tx -> {
                Record row = tx.run("""
                    MATCH (c:SecDemoCustomer {
                      tenantId: $tenantId,
                      customerId: $customerId
                    })
                    SET c.displayName = $newName
                    CREATE (a:SecDemoAuditEvent {
                      auditId: $auditId,
                      requestId: $requestId,
                      actorRef: $actorRef,
                      action: 'CUSTOMER_DISPLAY_NAME_CHANGED',
                      targetType: 'CUSTOMER',
                      targetRef: $customerId,
                      tenantRef: $tenantId,
                      result: 'APPLIED',
                      fieldsChanged: ['displayName'],
                      occurredAt: datetime()
                    })
                    RETURN a.auditId AS auditId
                    """, Map.of(
                    "tenantId", tenantId,
                    "customerId", customerId,
                    "newName", newName,
                    "actorRef", actorRef,
                    "requestId", requestId,
                    "auditId", auditId
                )).single();
                return row.get("auditId").asString();
            });
        }
    }
}
~~~

This is **persistence-layer illustrative code**, not a complete secure endpoint: enforce authorization, validation, exception handling, rate limiting, and idempotency before exposing it to callers. `Map.of` rejects null values; validate all inputs thoroughly. `executeWrite` may retry callbacks on transient errors, so **never send emails, call external APIs, or ack queues inside the callback**.

**Honest limitation:** writing audit nodes inside the same Neo4j transaction guarantees the mutation and audit node commit or roll back together, yet highly privileged admins could still edit or delete audit nodes. When tamper-resistant evidence is needed, ship events to an independent append-only audit store with separate retention, access control, and integrity verification.

### 9.2. Auditing sensitive reads

A `CUSTOMER_CONTACT_VIEWED` event **does not mutate nodes**, so it cannot piggyback on a `SET` mutation as above. Emit the event at the service/API layer **after authorization succeeds**, before disclosing data or following an appropriate durability policy.

Design decisions to settle:

- If the audit writer fails, should the sensitive read **fail closed (be rejected)** or proceed with missing logs? High-risk data usually demands explicit fail-closed durability.
- If the audit is written first and the data query fails, outcome records must reflect that **no data was actually returned**.
- If the audit is written after sending the response, a crash between steps creates an evidence gap.
- Bulk export jobs must audit *export initiated/completed*, row counts, and destination references—not just a single query log entry.

No single mechanism automatically guarantees "every read is logged exactly once" across Neo4j, HTTP responses, and external log stores without an explicit protocol. Define assurance levels to match business requirements.

### 9.3. Auditing failures and denied attempts

An audit event inside a business transaction **rolls back** if that transaction fails. That preserves atomicity for **applied events**, yet leaves no trace of denied access attempts.

`DENIED` / `FAILED` attempts should be recorded through a separate security/application audit channel with appropriate permissions, e.g.:

~~~json
{
  "eventId": "audit-attempt-007",
  "requestId": "req-204",
  "actorRef": "actor-17",
  "tenantRef": "tenant-demo",
  "action": "CUSTOMER_CONTACT_VIEWED",
  "targetRef": "customer-51",
  "outcome": "DENIED",
  "reasonCode": "INSUFFICIENT_PERMISSION",
  "occurredAt": "2026-11-25T08:05:00Z"
}
~~~

All values above are **fictitious**. Never log passwords, session tokens, real national IDs, or full profiles in events. `reasonCode` should be a standardized code; raw exception messages can leak PII or sensitive technical details.

## 10. Preserving trails across crashes, retries, and backups

### 10.1. Connection loss right at commit

If the Java Driver loses the response right as a Neo4j transaction commits, the client may not know whether the transaction persisted. Never blindly assume rollback and replay a non-idempotent side effect.

Use stable `auditId` / request IDs, check persisted state, and enforce business rules before retrying. A unique constraint on `auditId` stops duplicate audit nodes with the same ID, yet **by itself is insufficient** to make arbitrary business mutations idempotent. Balance adjustments or external dispatches require dedicated idempotency logic.

### 10.2. Log rotation, retention, and log loss

| Risk | Mitigation |
| --- | --- |
| Disk full from excessive query/security logs. | Rotation, retention policies, disk alerts, and forwarding. |
| Rotation deletes logs still needed for investigations. | Define retention, capacity, central storage, and legal requirements. |
| Collector disconnects and drops source lines. | Monitor lag, forwarding errors, bounded retries, and gap detection. |
| Server-local logs wiped alongside the database. | Ship critical logs to independent storage with separate permissions and backups. |
| Privileged actor alters logs or system clock. | Separate duties, sync clocks, lock down storage, consider immutability/hashing/signatures. |
| Support log bundles leak sensitive data. | Redact before sharing, control export permissions, encrypt bundles, track recipients. |

Default loggers may buffer writes for throughput; on sudden crashes, **not every trailing log line is guaranteed flushed to disk**. Strict audit mandates require durable logging infrastructure rather than merely enabling logs and declaring data unlosable.

### 10.3. Transaction logs are not a read-audit trail

Neo4j maintains transaction logs for recovery, replication, and database state management. They must not be treated as a business report showing which employee viewed which field. Protect transaction logs and backups as **sensitive data**, since they can contain payloads from write operations.

During backup/restore, verify:

- Access permissions on backup files, storage locations, encryption keys, and deletion lifecycles.
- How long logs/audits must be retained before and after a restore.
- Continuity of event IDs, request IDs, and log-shipping watermarks.
- Potential duplicate or divergent logs after restore/replay; never silently double-count business events.

## 11. Connecting with Spring Data Neo4j and GraphQL/REST APIs

When accessing Neo4j through **Spring Data Neo4j**, look at both layers:

~~~text
User -> API authentication/authorization
            |
            v
    Business service (@Transactional)
            |
       +----+----+
       |         |
       v         v
   Neo4j query  Audit event / outbox
       |
       v
Neo4j security/query logs (if supported)
~~~

A repository `findById()` or GraphQL resolver does not automatically understand end users, viewable data classes, or custom audit policies. They often run under a **service account** with broad rights; if the backend skips tenant checks, neither DB permissions nor logs may stop unauthorized reads.

A sensitive read flow should:

1. Authenticate the user and derive tenant/scope from a verified identity.
2. Verify the user holds `CUSTOMER_CONTACT_READ` for the specific target.
3. Select only needed properties in Cypher/DTO projections; never return raw full entities by default.
4. Record the audit event per policy (potentially requiring durable write before returning data).
5. Return the filtered response; never log response bodies or tokens.
6. Attach request ID/trace ID for investigation without embedding PII in metadata.

With GraphQL, protect sensitive fields in **field resolvers** and related traversal paths rather than relying on UI hiding. Aliased queries or alternate branches can still reach the same field; enforce authorization consistently on every fetch path.

**For write permissions:** place `@Transactional` on services using the proper transaction manager. Mutations and in-DB audit events roll back together before commit; external SLF4J log lines do not roll back and must never be used to claim a transaction committed.

## 12. Testing security and logging in isolated environments

A test suite must verify both **accurate enforcement and accurate evidence**, not merely that log files exist.

| ID | Test scenario | Expected outcome |
| --- | --- | --- |
| S01 | Valid login to self-managed Neo4j supporting security logs. | Trail recorded per enabled log config; user accurately identified. |
| S02 | Failed login. | Failure event logged and classified; password never exposed. |
| S03 | Role lacking read privilege on `email`. | Query/API does not return `email`; tested with real constrained role. |
| S04 | Tenant A user requests tenant B data. | Blocked by authorization; no nodes, properties, or relationships leaked. |
| S05 | Query uses literal containing sensitive test value. | Verify actual query log applies literal obfuscation as expected. |
| S06 | Query uses `$email` test parameter. | With parameter logging off, test value does not appear in `query.log`. |
| S07 | Query triggers error containing sensitive info. | Client error and query log details restricted; verify error-obfuscation setting separately. |
| S08 | Successful customer profile update. | Node and audit node commit together; `auditId`/actor/action accurate with no excess PII. |
| S09 | Error after node update before creating audit node. | Transaction rolls back; zero partial changes committed. |
| S10 | API denies profile read. | `DENIED` event emitted via proper audit channel; no data returned. |
| S11 | Connection lost right at commit. | Reconcilable via event ID/request ID; no duplicate audit or ledger writes. |
| S12 | Rotation, collector disconnect, or disk nearly full. | Alert fires; logs retained within SLA or log-loss incident detected. |
| S13 | Role/privilege change on `system` database. | On supporting editions/configs, admin event logged accurately with accountable actor. |
| S14 | Direct Neo4j access attempt bypassing API. | Network/authn/authz blocks unauthorized path; backend policy not bypassed. |
| S15 | Database restore from test backup. | Audit continuity checked, gaps classified, never assumed "complete" without verification. |

### 12.1. Testing for zero data leakage into logs

Using a dedicated **synthetic marker**, such as `TEST-SENSITIVE-MARKER-DO-NOT-USE`:

1. Run a parameterized query using the marker as a test value.
2. Trigger a controlled error to inspect error logs and responses.
3. Extract corresponding logs from an **appropriately restricted test sink**, never mixing with real user data.
4. Confirm the marker **never appears** in query logs, app logs, HTTP logs, traces, or error messages required to be redacted.
5. Verify valid events still retain investigative metadata: actor, action, request ID, and timestamp.

A "marker not found" test must check the **exact time window** and confirm logging and collectors are active and receiving events. Finding zero log lines because the collector is dead is an observability failure, not a redaction success.

### 12.2. Verifying audit nodes contain no PII

~~~cypher
MATCH (a:SecDemoAuditEvent {auditId: $auditId})
RETURN a.auditId AS auditId,
       a.action AS action,
       a.result AS result,
       a.fieldsChanged AS fieldsChanged,
       a.occurredAt AS occurredAt;
~~~

Also inspect the actual property keys on the audit node against the approved audit schema: there should be no `newEmail`, `oldPhone`, `accessToken`, or raw `requestBody`. If special requirements mandate storing PII in events, document the justification and apply separate permissions and retention.

### 12.3. Testing combined roles and admin privileges

Users can hold multiple roles. Test at least:

- Role reading only basic profile fields.
- Role permitted to read contact fields.
- A user assigned multiple roles simultaneously.
- A user lacking `TRAVERSE` while holding some `READ` property privileges.
- Service accounts running batches, exports, and audit writes.
- Admins authorized to modify roles and personnel managing log infrastructure.

Do not inspect only `SHOW ROLE ... PRIVILEGES`; execute queries using the **actual test accounts/roles**, inspecting both query outputs and API responses.

## 13. Handling a data-exposure or missing-audit incident

When sensitive data appears in query logs or log tampering is suspected:

1. **Isolate and preserve evidence:** restrict access to affected logs, files, and exports while preserving current state and timestamps; never delete logs immediately and destroy forensic trails.
2. **Stop further leakage:** adjust query/parameter logging, error masking, and app loggers via change control without disrupting the active investigation.
3. **Determine scope:** time range, tenants, field types, servers/instances, log collectors, export copies, and who had file-read access.
4. **Review actual access and actions:** cross-check security logs, query logs, app audits, gateway/IdP logs, and infra logs; note any gaps.
5. **Assess secret rotation:** if passwords, tokens, or keys leaked, run rotation/revocation workflows and monitor anomalous use.
6. **Remediate root cause:** fix field projections, tighten privileges, update log pipelines or debug modes, and add regression tests.
7. **Report and document:** follow incident-response, privacy, and legal/contractual notification rules.

If an audit log gap is discovered, never backfill synthetic events with past timestamps and present them as original records. Clearly distinguish **original evidence**, **reconstructed facts**, and **unverifiable gaps**.

### 13.1. Caution with logging changes during an incident

Some Neo4j settings are dynamic; others require restarts or admin privileges, and in clusters each server maintains its own config. A change applied to only one member can leave a leak active on peers. Before declaring remediation complete, verify effectiveness across **every instance capable of serving requests** and re-check after restarts/deployments.

## 14. Common misconceptions

| Misconception | Reality to remember |
| --- | --- |
| "Enabling `security.log` shows every node anyone viewed." | Security logs primarily capture supported auth/authorization/admin events, not every business data read. |
| "Having `query.log` gives full compliance auditing." | Query logs may filter by thresholds/modes and omit end actors, returned values, and business semantics. |
| "Using parameters guarantees zero PII in logs." | Parameter values can be logged if parameter logging is enabled; apps may also log values separately. |
| "Enabling literal obfuscation prevents any leakage." | Parameter values, metadata, error strings, and other logs still need independent controls. |
| "Disabling introspection or hiding UI fields is security." | Backends/databases must still enforce read rights on properties, nodes, and relationships. |
| "Disk encryption alone is enough." | Read privileges, transit, logs, exports, backups, and relationship structures can still expose data. |
| "Service account has broad rights, but the API has login so it is safe." | One API missing a tenant filter or a direct DB path can expose bulk data. |
| "Writing audit nodes in the same DB makes them immutable." | Privileged DB users can modify/delete them; ship to an independent store when immutability is required. |
| "Logged success before commit means the operation succeeded." | Transactions can roll back afterward; audit outcomes must align with commit boundaries. |
| "Auditing every read only takes adding one INSERT." | Event writing, response delivery, and failures span separate boundaries; assurance levels must be designed. |
| "One DENY rule suffices for every tenant." | Test combined roles, null/missing fields, property-based rules, and all traversal paths. |
| "Deleting a log file with PII removes all risk." | Copies, backups, SIEM indexes, and exports may remain; hasty deletion destroys forensic evidence. |

## 15. Practice exercises

**Exercise 1 — Log classification.** A Neo4j account `svc-api` serves 10,000 end users. Identify which data appears in `security.log` and `query.log`, and what API-level auditing is needed to prove an end user viewed a sensitive record. Explain why end actors cannot be inferred solely from the service username.

**Exercise 2 — Query log configuration.** Use a test environment with a logging-capable Neo4j build. Configure slow-query logging, disable parameter logging, and enable literal obfuscation; run a query with a synthetic marker and verify the marker is absent from query and error logs. Record the Neo4j version, edition, actually supported settings, and test evidence.

**Exercise 3 — Least privilege.** A role may read customer display names without seeing email, phone, or nationalId. Draft a DB-privilege strategy where supported, plus an API-layer enforcement plan for Community lacking property-level privileges. Design tests with a multi-role user.

**Exercise 4 — Update auditing.** Create a synthetic `SecDemoCustomer` and implement a transaction updating `displayName` alongside a `SecDemoAuditEvent`. Force an error mid-transaction to prove zero partial updates persist, then run successfully and verify the event holds `actorRef`/`action`/`requestId` without sensitive field values.

**Exercise 5 — Read auditing and fail-closed.** Policy requires recording audit evidence before returning a customer's phone number. Design handling for: slow audit writer, unreachable audit writer, service crash after audit before response, and service crash after response before audit ack. State business policy and achievable guarantees for each.

**Exercise 6 — Multi-tenant graph.** A customer node in tenant T1 has an erroneous relationship pointing to an order node in T2. Design API queries and tests verifying T1 cannot see T2's data or relationships even when starting from a T1 node.

**Exercise 7 — Log exposure incident.** An engineer enabled `VERBOSE` query logging with parameter values for one day; logs captured synthetic customer emails in a test environment. Write a runbook: containment, config change, checking collectors and copies, verifying log-read permissions, rotating secrets if needed, and preserving evidence.

**Exercise 8 — Auditing by edition.** Compare self-managed Community, self-managed Enterprise, and an Aura tier assigned to your team. For each, list audit/authorization capabilities you can **genuinely verify**, gaps that must be addressed in the API or infrastructure, and claims you cannot make without the right edition/privileges.

## 16. Pre-production checklist

1. **Know your data:** are sensitive nodes, relationships, properties, and metadata classified—not just a few PII columns?
2. **Know your product:** have edition, Aura/self-managed tier, version, and genuinely supported logging/authz features been verified?
3. **Least privilege:** does each service/user hold only required database, node, relationship, property, and admin rights?
4. **Tenant boundaries:** have all entry points, expanded branches, aggregates, and export paths been tested against cross-tenant leaks?
5. **No log leaks:** have query parameters, literals, error details, request/response bodies, traces, and debug logs been verified?
6. **Business auditing:** are end actor, action, target, outcome, and timestamp recorded—not just the service username?
7. **Transaction alignment:** do mutations and applied events commit/roll back together, with denied/failed audits routed separately?
8. **Tamper resistance:** are log permissions separated, collectors monitored, storage durable, and integrity controls in place?
9. **Encryption:** do transit, volumes/backups, exports, and secret management meet policy?
10. **Lifecycle management:** are retention, rotation, export/delete rights, data-subject requests, and backups consistent?
11. **Failure testing:** have log loss, rollbacks, ambiguous commit retries, overlapping roles, and shipping failures been tested?
12. **Operational readiness:** are dashboards/alerts, runbooks, owners, correlation IDs, and investigative traceability ready?

**Conclusion:** Neo4j security does not stop at turning on `security.log` or `query.log`. Database logs help observe **authentication, administration, and queries** within product capabilities, while **auditing end-user business actions** usually must be designed in the application. At the same time, sensitive data must be protected across nodes, relationships, query text, parameters, errors, logs, backups, and exports. Use capabilities **where supported by your edition and version**, enforce least privilege, verify settings in test environments, and build audit trails with clear transaction boundaries.

## References

- [Neo4j Operations Manual — Logging](https://neo4j.com/docs/operations-manual/current/monitoring/logging/): security/query log scope, logging config, literal/parameter obfuscation, and log formats.
- [Neo4j Operations Manual — Authentication and authorization](https://neo4j.com/docs/operations-manual/current/authentication-authorization/): roles, privileges, and edition limits.
- [Neo4j Operations Manual — Read privileges](https://neo4j.com/docs/operations-manual/current/authentication-authorization/privileges-reads/): granting property and traversal access.
- [Neo4j Operations Manual — Property-based access control](https://neo4j.com/docs/operations-manual/current/authentication-authorization/property-based-access-control/): property-based privilege conditions and boundary cases.
- [Neo4j Operations Manual — Security checklist](https://neo4j.com/docs/operations-manual/current/security/checklist/): protecting connections, files, backups, and infrastructure.
- [Neo4j Aura — Activity feed](https://neo4j.com/docs/aura/logging/activity-feed/) and [Download logs](https://neo4j.com/docs/aura/logging/log-downloads/): supported log observation/export features per service tier.
