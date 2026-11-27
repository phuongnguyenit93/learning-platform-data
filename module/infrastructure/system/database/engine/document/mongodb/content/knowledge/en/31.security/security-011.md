# Auditing, Sensitive Log Redaction, and Backup Access Control in MongoDB

## 1. The Problem: Having Backups and Logs Is Not Enough

An e-commerce platform stores shipping addresses in `orders`, phone numbers in `customers`, and settlement details in `payments`. The Java API connects to MongoDB with a service account; operations staff use Atlas or admin tools; data is backed up daily.

Consider three scenarios:

1. A MongoDB admin account is compromised. The attacker grants privileges to a new identity, extracts data, and tries covering their tracks. **Are there audit events recording that privilege grant, and who can alter or delete the logs?**
2. The application logs every request and MongoDB driver command to observability tools. Some commands contain emails, phone numbers, or tokens. **Are logs becoming an unguarded duplicate of sensitive data outside database security policies?**
3. A staff member assigned only to “verify backups” holds rights to export every snapshot to a personal machine or restore over production. **Are privileges to check, create, export, restore, and delete backups separated?**

These three problems form the three pillars of this lesson:

- **Auditing:** recording evidence of actions and identities under a verifiable policy.
- **Log redaction / data minimization:** keeping secrets out of diagnostic logs, audit streams, application logs, and SIEM systems.
- **Backup authorization:** protecting data copies from unauthorized reads, tampering/deletion, erroneous restores, and recovery failures.

They are related yet **do not replace one another**. Complete auditing cannot rescue an unencrypted snapshot shared publicly. Encrypting logs will not stop a service account granted `root`. Immutable backups will not tell you who altered a document.

### 1.1. Objectives

After this lesson, you will be able to:

- Distinguish **MongoDB database audits**, **diagnostic/server logs**, **Atlas Activity Feed**, **application logs**, and **backup access logs**.
- Identify audit event categories, understand `atype`, `param`, `users`, `roles`, `result`, and audit guarantees/limits.
- Configure audit destinations and filters on **self-managed MongoDB Enterprise** appropriately; understand Atlas requirements.
- Explain risks of auditing every successful query, overly narrow audit filters, and inadequate log protection.
- Use `security.redactClientLogData` within its true scope; implement **intentional logging, masking, pseudonymization, and access control**.
- Separate backup privileges across **MongoDB database**, **Atlas control plane**, **object storage**, **KMS**, and **restore targets**.
- Design secure backups with encryption, retention, immutable copies, PITR, RPO/RTO, and restore drills.
- Build audit/backup runbooks, alerts, threat scenarios, and safe hands-on checks.

## 2. Data Flows to Evaluate

```text
                        Users
                          |
                     HTTPS / API
                          |
                   +-------------+
                   | Java service|
                   +-------------+
                     |         |
             TLS/DB AuthN    App logs / Traces
                     |         |
                     v         v
            +----------------+   +------------------+
            | MongoDB cluster|   | Log pipeline/SIEM|
            +----------------+   +------------------+
              |         |               ^
              |         +-- Audit log --+
              |
          Backup / Snapshot
              |
              v
     +-----------------------+
     | Backup storage        |
     | encryption, IAM, WORM |
     +-----------------------+
              |
       Restore workflow
              |
              v
     Isolated target / Production

               KMS / Secrets
              ↗        ↖
      app encryption   backup encryption
```

This is a conceptual diagram. With Atlas, the provider manages certain platform components; with self-managed, operations owns more pieces. In both cases, **database access does not equate to Atlas project, backup bucket, or KMS access**.

### 2.1. Three Cross-Cutting Security Properties

| Objective | Auditing | Log Redaction | Backup Controls |
|---|---|---|---|
| **Confidentiality** | Detects anomalous access | Reduces PII/secrets in logs | Restricts viewing/exporting snapshots |
| **Integrity** | Records evidence of changes | Reduces log tampering when access-controlled | Protects snapshots from tampering/deletion |
| **Availability** | Detects early incident signals | Prevents leaks disrupting response | Restores within RPO/RTO |

A backup matters only when **the right data at the right point in time is readable and authorized staff can restore it**. An audit event holds forensic value only when logs remain untampered with clear timestamps, identities, and coverage.

## 3. Distinguishing Five Sources of “Logs”

### 3.1. MongoDB Diagnostic / Server Logs

Record process health, connections, errors, warnings, slow operations, and operational activity. They serve **diagnostics and observability**, and do not automatically guarantee capturing every user action for compliance.

Examples:

```text
Connection accepted
Slow query
Replication lag warning
Index build progress
Authentication failure message
```

### 3.2. MongoDB Database Audit

The audit subsystem records **system events, authentication, authorization, and configured auditable actions**. It has its own event schema, filters, and write guarantees.

Examples:

```text
authenticate
authCheck
createUser
grantRolesToUser
dropCollection
```

**Never assume database auditing is enabled merely because diagnostic logs show connection lines.**

### 3.3. Atlas Activity Feed / Control-Plane Events

Records Atlas management-plane actions such as project/cluster/backup policy changes per product capabilities. It does not log every CRUD query inside the database.

“User updated IP access list” is a control-plane event; “service ran `find`” is a database-plane event.

### 3.4. Application Audits and Application Logs

APIs may need to record:

```text
actorId=staff-17
action=APPROVE_REFUND
resourceRef=refund-938
result=APPROVED
requestId=...
```

MongoDB database audits **do not inherently know** why a document update means “refund approved”. Business-level audits require application events carrying business actors and semantics.

### 3.5. Backup / Storage / KMS Access Logs

Record who listed, downloaded, exported, restored, modified retention, accessed object storage, or used decryption keys.

These logs are critical when the database itself behaves normally while data is exfiltrated via backups.

### 3.6. Comparison Table

| Source | Control Purpose | Do Not Expect |
|---|---|---|
| Diagnostic log | Operations, errors, slow operations | Full log of every successful CRUD |
| Database audit | Selected access and admin events | Business meaning of transactions |
| Atlas control-plane log | Atlas management changes | Every driver command |
| Application audit | Business actor/action/decision | Full visibility into MongoDB host state |
| Backup access log | Reads/exports/deletes/restores of copies | Details of every source document edit |

## 4. MongoDB Database Auditing: Editions and Deployments

### 4.1. Self-Managed MongoDB Enterprise

MongoDB Enterprise includes built-in database auditing. It can be configured on `mongod` and `mongos` targeting JSON/BSON files, console, or syslog (syslog is unsupported on Windows).

A complete solution must cover **every relevant node and router**, not only the primary.

### 4.2. MongoDB Community

Never assume Community includes the full **Enterprise audit subsystem** and `auditLog.*` options. On Community, you still have diagnostic logging, application audits, OS/network/storage logs, and monitoring solutions, **but never treat them as equivalent substitutes for native database auditing**.

If compliance requires specific database audit events, choose an edition/deployment and architecture that supports them.

### 4.3. MongoDB Atlas

Per MongoDB Atlas documentation, database auditing is available on **dedicated M10+ clusters** and unsupported on Free/Flex. Configure via Atlas UI/API/CLI with appropriate project permissions, using the audit filter builder or custom JSON filters.

Distinguish:

- **Atlas project/organization activity:** control-plane changes.
- **MongoDB database audit:** database access audit events.
- **Application logs:** emitted by your own services.

Never confuse a role like `Project Backup Manager` with the database role `backup`.

## 5. What Fields Does an Audit Event Contain?

A typical audit event includes fields whose exact structure varies by event and version:

| Field | Meaning |
|---|---|
| `atype` | Action type: `authenticate`, `authCheck`, `createUser`, etc. |
| `ts` | Timestamp of the recorded event |
| `local` | Local endpoint involved |
| `remote` | Client endpoint involved |
| `users` | Recorded user identities |
| `roles` | Associated roles |
| `param` | Event-specific parameters |
| `result` | Event-specific result code (e.g., `0` usually means success) |

**Simplified illustrative example (not a real event to copy verbatim for tests):**

```json
{
  "atype": "authenticate",
  "ts": { "$date": "2026-11-14T03:20:00Z" },
  "remote": { "ip": "10.10.1.22", "port": 49210 },
  "users": [{ "user": "orders_reader", "db": "admin" }],
  "param": {
    "user": "orders_reader",
    "db": "admin",
    "mechanism": "SCRAM-SHA-256"
  },
  "result": 0
}
```

Never hardcode expectations for every field across every `atype`. DDL or privilege events have different `param` fields, and addresses/usernames may render differently across contexts.

### 5.1. `result` Is Not an HTTP Status

`result: 0` generally indicates success across many events; non-zero codes represent errors. Never build a rule saying “anything other than 200 failed” as if parsing HTTP.

### 5.2. `users` and Application Identity

If all microservices share one database user:

```text
database user = shared_app
```

audits struggle to distinguish requests from `OrderService`, `BillingService`, or `InventoryService`. Use **separate service identities** where appropriate alongside application request/correlation IDs to correlate sources.

### 5.3. Values Inside `param` Can Be Sensitive

Audit events can include namespaces, query arguments, or other metadata depending on event, filter, and configuration. Never assume audit logs **cannot** hold PII just because they are security logs. **Access restrictions, retention, and redaction policies** remain necessary for audits.

## 6. Actions Worth Including in Audit Scope

### 6.1. Authentication and Authorization

- Authentication successes/failures per policy.
- Authorization failures (`authCheck`).
- User creation/deletion.
- Role grants/revocations.
- Changes to roles or authentication config.

Goal: detect credential abuse, role escalation, and unexpected new privileges.

### 6.2. Data Administration Actions

- Dropping databases/collections.
- Renaming collections or major structural changes.
- Modifying system-level roles/privileges.
- Administrative operations deemed high risk by the organization.

Check exact supported `atype` names for your MongoDB version—never invent event names expecting filters to match.

### 6.3. Sensitive Data Access

Some compliance mandates require logging successful reads/writes on PII namespaces. Balance **cost, log volume, privacy, and audit limits**.

Key point:

> **By default, `authCheck` auditing typically logs authorization failures only. To audit CRUD authorization successes as well, configure `auditAuthorizationSuccess` explicitly and benchmark performance impact.**

Never claim “auditing is enabled” means every successful `find`/`update` is logged.

## 7. `authCheck` and `auditAuthorizationSuccess`

### 7.1. Authorization Checks Differ from Authentication

- `authenticate`: identity login/verification.
- `authCheck`: server checking authorization for a specific operation.

A user can authenticate successfully yet be denied `dropCollection` or reading another namespace.

### 7.2. By Default, `authCheck` Focuses on Failures

When `auditAuthorizationSuccess` is off, filtering for `authCheck` does not automatically emit audit events for **every successful read/write**.

Example:

```text
Service logs in successfully         -> authenticate
Service reads permitted collection   -> not every read success is audited by default
Service reads unauthorized namespace -> authCheck failure can be audited
```

### 7.3. Weigh Auditing Successes Carefully

On high-throughput workloads, auditing every read/write generates massive audit load. Per MongoDB documentation, logging authorization successes can **severely degrade cluster performance**.

Before enabling broadly:

1. Identify exact namespaces and actions that truly need auditing.
2. Verify filters and features for your version.
3. Measure throughput, p95 latency, log volume, disk, and network impact.
4. Size storage, SIEM ingestion, and retention.
5. Plan handling if the audit sink fills up or fails.

Audit logging is not free, and “log everything and figure it out later” is poor policy in most environments.

## 8. Filtering Audits: Enough to Investigate Without a Log Storm

### 8.1. Policy Example

An organization prioritizes:

- Authentication events.
- User/role administration operations.
- Dropping collections/databases.
- Authorization failures.

This is a **directional policy** that must be mapped accurately to the `atype` catalog of your deployed version.

### 8.2. Illustrative Filter

```javascript
{
  atype: {
    $in: [
      "authenticate",
      "authCheck",
      "createUser",
      "dropUser",
      "grantRolesToUser",
      "revokeRolesFromUser",
      "dropCollection",
      "dropDatabase"
    ]
  }
}
```

**Never use this filter to claim 100% coverage.** Actions like `updateRole`, renames, config edits, or platform events fall outside this list. Verify exact event catalogs against compliance mandates.

### 8.3. Overly Broad vs. Overly Narrow Filters

| Policy | Pros | Risks |
|---|---|---|
| Audit every event | Wide coverage | High resource cost, holds sensitive data |
| Audit login failures only | Easy to deploy | Blind to privilege escalation and DDL |
| Audit admin + auth failures | High investigative value | May miss successful data reads |
| Audit selected sensitive namespaces | Tied to specific risks | Easy to miss new paths/namespaces |
| Audit successes with tight filters | Improves forensic coverage | Requires load and retention testing |

### 8.4. Never Filter by Existing Usernames Alone

If you audit only:

```text
users.user = "admin_a"
```

actions by a new admin or a rogue created credential will be omitted from logs.

Policies typically need **event categories independent of current identities**, adding user/namespace filters only with justification.

## 9. Configuring Auditing on Self-Managed MongoDB Enterprise

**Illustrative** configuration example:

```yaml
# mongod.conf (Enterprise, adjust for your specific deployment)
security:
  authorization: enabled
  redactClientLogData: true

auditLog:
  destination: file
  format: JSON
  path: /var/log/mongodb/audit.json
  filter: '{"atype":{"$in":["authenticate","authCheck","createUser","dropUser","grantRolesToUser","revokeRolesFromUser","dropCollection","dropDatabase"]}}'
```

**Prerequisites:**

- Use an edition/version supporting auditing.
- Audit path exists and the `mongod` service user has minimal write rights.
- File permissions, rotation, disk monitoring, and log shipping are designed.
- RBAC, internal cluster auth, and TLS are configured separately.
- For replica sets/sharded clusters, roll configuration out across all `mongod` and `mongos` processes per policy.
- Config changes may require restarts/rolling updates; plan impact and maintenance windows.

### 9.1. JSON vs. BSON

File-based audit output supports **JSON** and **BSON**. JSON integrates easily with text pipelines; BSON often lowers logging overhead compared to JSON.

Do not confuse:

```text
format: BSON
```

with **encryption**: BSON is a binary serialization format, not encryption.

### 9.2. Console and Syslog

Audit destinations include:

- `file`: JSON/BSON.
- `console`: writes to stdout.
- `syslog`: sends to syslog (unavailable on Windows).

Destination choice affects durability, permissions, rotation, SIEM pipelines, and exposure risk. Writing audit logs to stdout in containers routes them through shared platform log collectors; verify permissions and retention at the collection sink.

### 9.3. Dynamic Audit Configuration

MongoDB versions support runtime audit configuration under specific conditions, such as distributed audit configuration with `auditLog.runtimeConfiguration` and matching commands.

Never arbitrarily mix:

```text
auditLog.runtimeConfiguration = true
auditLog.filter = ...
auditAuthorizationSuccess = ...
```

at startup when version documentation specifies they conflict. Choose either **startup configuration** or **runtime/distributed configuration** consistently.

In production, filter edits require **change records, review, staging tests, and post-deploy coverage verification**.

## 10. Auditing on MongoDB Atlas

### 10.1. Two Event Categories

**Database auditing:** audits database activity by filter/role/identity on supported clusters.

**Project/organization activity:** Atlas admin actions such as config edits and control-plane permissions.

A snapshot export involves the Atlas control plane and cloud storage access; never look only at database audits when investigating backup exfiltration.

### 10.2. Access Requirements

Per Atlas documentation, configuring database auditing requires **Project Owner** or **Organization Owner** within the appropriate scope; product role policies govern exact permissions.

Permissions to toggle auditing, read audit logs, create database users, and manage backups **must not all be handed out together to the same identity**.

### 10.3. Audit Filter Options

Atlas supports filtering by action type, user/role, and custom JSON filters. When writing custom filters:

- Specify exact event types and commands/namespaces.
- Document whether authorization successes are enabled.
- Test that events emit on both success and failure.
- Monitor audit workload impact and storage cost.

### 10.4. Do Not Assume All Atlas Tiers Are Equal

Free/Flex tiers do not provide database auditing like dedicated M10+ clusters. Backup options, log downloads, retention, and roles also vary by deployment type and current product features.

## 11. Audit System Guarantees and Limits

MongoDB Enterprise's audit subsystem provides **ordering and durability guarantees** tied to connections and operations affecting persistent state.

However, do not interpret that as “audits can never lose an event”:

- Audit events can be buffered in memory before flushing to disk.
- If the server terminates before flushing, un-flushed events can be lost.
- MongoDB enforces rules for writing audit events before journaling certain persistent-state changes.
- If the server cannot write to the audit destination, **the server may terminate** to preserve audit guarantees.

### 11.1. Availability Implications

A full audit disk does not merely drop logs; it can threaten **MongoDB availability**. Thus:

```text
Audit policy
  -> disk capacity
  -> log rotation
  -> off-host shipping
  -> alerts
  -> sink-failure runbook
```

is a mandatory part of design.

### 11.2. Do Not Use Audits as a Business Event Store

Audit events can appear even for operations inside an **aborted** transaction; never assume an audit CRUD event proves a **business transaction committed**.

If the business needs replayable order-state history, build an **application audit/outbox/ledger** tied to transactions rather than relying on database audits alone.

## 12. Protecting Audit Logs Against Tampering and Loss

### 12.1. Threats

1. A local DB host admin deletes local audit files.
2. Log agents disconnect, fill queues, or duplicate events.
3. Audit logs are altered before reaching SIEM.
4. Retention expires before an incident is discovered.
5. Users reading logs access embedded PII or credentials.

### 12.2. Recommended Design

```text
mongod/mongos
   |
   v
Local audit file (OS permissions)
   |
   v
Agent/collector (mTLS, bounded spool)
   |
   v
Central audit storage / SIEM
   |
   +-- Retention + immutable/tamper-evident copy
   +-- Role-based access
   +-- Encryption/KMS
   +-- Alerting, parsing, search
```

### 12.3. Forensic Integrity Requirements

- Synchronized timestamps with explicit timezones.
- Node/router and environment identifiers.
- Event source, `atype`, actor, namespace, and result.
- Collector ingestion timestamps and correlation IDs where possible.
- Off-host shipping out of potentially compromised hosts promptly.
- Checksums/signatures/immutable storage if required.
- Restricted authority to modify retention.
- Periodic tests confirming shipping and alerts work.

**Never promise audit logs are immutable just because they sit in a JSON file.**

## 13. What Sensitive Data Can Leak into Diagnostic Logs?

Across MongoDB server, drivers, and applications, logs can accidentally capture:

- Document/filter arguments containing emails, phone numbers, or IDs.
- Connection strings containing usernames/passwords.
- Query literals inside slow-operation messages.
- Exceptions containing namespaces, statements, or failing payloads.
- Auth token headers when loggers dump HTTP requests.
- MongoDB command payloads exposed by driver `CommandListener`s.
- Aggregation pipelines carrying internal values.
- Usernames, hosts, IPs, tenant IDs, and trace contexts.

Even data that is **not a plaintext password** can be sensitive. A tenant ID or collection name can reveal customer identities.

### 13.1. Consequences of Data Copied into Logs

A PII field with a 30-day retention in MongoDB can persist for **365 days** in an external logging system.

```text
MongoDB source retention: 30 days
          |
          v
Diagnostic log containing PII
          |
          v
Central logging retention: 365 days
```

Deleting source records **does not guarantee** deletion from logs or backups. Align data classification and retention across systems.

## 14. `security.redactClientLogData`: Masking Content in Diagnostic Logs

### 14.1. Effect

MongoDB Enterprise offers:

```yaml
security:
  redactClientLogData: true
```

This is an **Enterprise log redaction** feature; MongoDB docs also describe corresponding capabilities on Atlas. When enabled, MongoDB redacts **message content** that may contain sensitive info in diagnostic/server logs while keeping metadata such as error codes, source files, and line numbers.

### 14.2. Does Not “Erase Every Sensitive Field Everywhere”

**Scope limits are critical:**

- Does not replace **redaction in application logs**.
- Does not govern access to **audit files** or backups.
- Does not guarantee every event across **all collectors, drivers, and SIEMs** is scrubbed.
- Can reduce detail needed during debugging.
- Does not replace TLS, encryption at rest, or RBAC.

Before enabling, know which log fields remain, what gets redacted, and how to troubleshoot with redaction on.

### 14.3. Enabling at Startup or Runtime

Startup configuration example:

```yaml
security:
  authorization: enabled
  redactClientLogData: true
```

On Enterprise with proper privileges, MongoDB docs also describe runtime toggling via parameter:

```javascript
db.adminCommand({
  setParameter: 1,
  redactClientLogData: true
});
```

**Run only after confirming edition/version and on authorized environments.** Runtime changes must still be persisted in config files consistently across nodes so restarts do not revert them.

### 14.4. Investigation Trade-Offs

```text
Redaction OFF:
  + Easy to inspect query literals when debugging
  - Risk of PII in slow-query/error logs

Redaction ON:
  + Reduces PII in log messages
  - Removes some troubleshooting detail
```

The answer is not turning redaction off on every production bug. Pair it with **safe structured metadata**, request IDs, query shapes, metrics, synthetic reproducers, and controlled break-glass workflows.

## 15. Log Redaction and Audit Filters Solve Different Problems

| Control | Primary Effect | Does Not Guarantee |
|---|---|---|
| `auditLog.filter` | Selects which **audit event** types are logged | Stripping PII from selected events |
| `auditAuthorizationSuccess` | Controls logging authorization successes on `authCheck` | Automatic performance safety |
| `redactClientLogData` | Masks message payloads in **diagnostic logs** | Redacting app/backup/all audit logs |
| Application redaction | Reduces PII/secrets in service logs | Blocking reads by DB-privileged users |
| SIEM ingest filtering | Masks/drops fields on ingestion | Protecting raw data stored upstream |
| KMS/encryption | Protects stored logs/backups at rest | Replacing access controls or retention |

A serious mistake is enabling `redactClientLogData` and writing in compliance docs: “All audits, driver logs, app logs, and snapshots are redacted.” **That claim is baseless.**

## 16. Designing Logging Around Data Classification

### 16.1. Classification

Minimal model:

| Level | Examples | Logging Rule |
|---|---|---|
| Public | Generic operation names | May log per policy |
| Internal | Service name, namespace, correlation ID | Scope access appropriately |
| Confidential | User email, order details, tenant business ID | Avoid raw logging; mask/tokenize |
| Restricted | Passwords, API keys, access tokens, private keys, card data | **Never log** |

Classify **in context**: IP addresses, tenant IDs, or query patterns can also be confidential in certain systems.

### 16.2. Allowlist Logging Beats Blocklists

Never log entire requests and try “stripping known sensitive fields”:

```javascript
logger.info("request={}", req.body);
```

A new field `personalId` added tomorrow slips straight past a blocklist.

Build explicit structured events:

```text
event=ORDER_UPDATE_ATTEMPT
requestId=...
actorRef=...
resourceRef=...
operation=updateStatus
durationMs=...
outcome=DENIED
```

### 16.3. Data Values vs. Metadata

Example query:

```javascript
db.customers.find({
  email: "customer@example.test"
});
```

Routine observability only needs:

```text
operation=find
collection=customers
queryShape=email_eq
durationMs=8
resultCount=1
```

You rarely need the literal email. For deep investigations, follow approved procedures against safely handled data/environments.

## 17. Masking, Tokenization, and HMAC Pseudonymization

### 17.1. Masking

Example:

```text
original email: alice@example.test
log:            a***@example.test

original phone: +84xxxxxxxxx
log:            +84******123
```

Masking helps when partial recognition aids support, **yet does not guarantee non-reidentification**.

### 17.2. Tokenization

Replace real values with securely generated/managed surrogate identifiers:

```text
customerId = C-123456
log token  = tok_7e4a...
```

Logging services never need the token → real-data mapping. Wherever that mapping exists, protect access to it separately.

### 17.3. HMAC Instead of Raw Hashing

To correlate one user across logs without recording PII:

```text
fingerprint = HMAC_SHA256(secret, normalizedIdentifier)
```

HMAC with a strong secret is far stronger than:

```text
SHA256(email)
```

because emails and phone numbers have small, guessable domains vulnerable to dictionary attacks against unsalted hashes. Even so, **HMAC fingerprints can still qualify as personal/pseudonymous data**, requiring retention and access controls.

### 17.4. Avoid Randomness That Breaks Investigation

If every request generates an unrelated random token without a correlation ID, correlating actions by the same actor fails. Balance:

- Minimal logging.
- Stable correlation needed for investigations.
- Preventing pseudonyms from becoming unbounded tracking identifiers.
- Separating access to salts, secrets, and mappings.

## 18. Java: Safe Logging with the MongoDB Driver

### 18.1. Intentional Application Events

SLF4J example:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class OrderAuditLogger {
    private static final Logger log =
        LoggerFactory.getLogger(OrderAuditLogger.class);

    public void orderViewed(
        String requestId,
        String actorReference,
        String orderReference,
        long durationMs,
        boolean allowed
    ) {
        // References are already identifiers containing no direct PII,
        // or pseudonymized per organizational policy.
        log.info(
            "event=ORDER_VIEW requestId={} actorRef={} orderRef={} " +
            "durationMs={} result={}",
            requestId,
            actorReference,
            orderReference,
            durationMs,
            allowed ? "ALLOWED" : "DENIED"
        );
    }
}
```

**Never pass passwords, JWTs, raw documents, or emails directly into those arguments.** Naming a variable `actorReference` does not magically strip PII; validate values against your logging contract.

### 18.2. Never Log Full MongoDB URIs

```java
// Not recommended:
log.info("Mongo URI = {}", mongoUriWithPassword);

// Recommended:
log.info("MongoDB connection initialized; service={}", serviceName);
```

Exceptions can embed rich context, so production loggers need exception/stack-trace sanitization preventing raw queries or connection strings from leaking.

### 18.3. `CommandListener` Is Highly Sensitive

The MongoDB driver provides command monitoring. Logging:

```java
// Contraindicated in production without redaction:
log.debug("Mongo command: {}", event.getCommand());
```

dumps raw BSON commands containing query literals, update payloads, and internal metadata unsuitable for logs.

For metrics, you normally only need:

```text
commandName=find
database=shop
requestId=...
durationMs=...
success=true
```

Use safe metadata APIs for your driver version rather than serializing entire command objects. Never assume drivers automatically redact commands your code explicitly logs.

### 18.4. Correlation IDs

An HTTP request can flow through:

```text
API Gateway -> OrderService -> MongoDB -> Event publisher
       requestId = R-abc123
```

When every component logs the shared request ID, SIEM correlates events without stuffing full payloads into logs.

**Never blindly trust client-supplied `requestId` headers**; normalize, bound length, and sanitize against log injection at the gateway/backend.

## 19. Log Ingestion, SIEM, and Retention

### 19.1. Redact at the Source Before Emitting

Optimal security pipeline:

```text
Sensitive operation
    |
    v
Create safe structured log at source
    |
    v
Collector with mTLS
    |
    v
SIEM with scoped access
    |
    v
Retention / archival / deletion
```

If PII reaches the collector before redaction, raw copies can linger in buffers, crash dumps, or side pipelines. Always **redact as close to the source as possible**.

### 19.2. Log Access Permissions

Suggested roles:

- Developer: view metrics and sanitized service app logs.
- On-call SRE: view operational logs with secrets restricted.
- Security analyst: view audit alerts and investigate per policy.
- Compliance: view filtered reports and evidence.
- Break-glass: deeper access with approval, time bounds, and auditing.

Never allow every developer to download all production audit logs containing user identities and query details.

### 19.3. Purpose-Driven Retention

Directional example:

```text
App debug logs:    shorter retention per operational need
Security audits:   retention per legal/compliance mandates
Backup snapshots:  retention per RPO/PITR/recovery needs
```

**Never apply one arbitrary retention period across every organization.** Overly long retention expands sensitive-data exposure; overly short retention breaks investigations and recovery.

### 19.4. Tamper-Evident Logs

Controls may include:

- Immutable object storage or WORM.
- Per-batch hash chains or cryptographic signatures.
- Fast off-host shipping.
- Restricted delete/overwrite permissions.
- Independent KMS key governance.
- Monitoring sequence gaps and ingestion drops.

Hashing a file on **the same compromised host** cannot prevent tampering if the attacker can rewrite both the file and the hash.

## 20. Monitoring for Auditing and Redaction

| Signal | Why It Matters |
|---|---|
| Sudden drop in audit event rate | Misconfigured filter, broken collector, or coverage gap |
| Spike in authentication failures | Brute force, bad credentials, or broken deploy |
| Unusual user/role creation | Privilege escalation |
| Audit config modified | Potential attempt to blind investigations |
| Audit destination nearly full | Risk of server outage |
| Log shipping lag | Loss of near-real-time visibility |
| Parse errors / unknown event types | Version upgrade or event schema drift |
| DLP detects PII/secrets in logs | Violation of redaction policy |
| Unusual volume of read/export operations | Potential exfiltration |
| Spike in KMS access | Risk of unauthorized key usage |

### 20.1. Do Not Confuse Absence of Alerts with Absence of Incidents

If the system does not audit successful CRUD operations, it cannot detect certain data-reading patterns **solely from unconfigured audit events**. Combine application audits, egress monitoring, and service behavioral telemetry.

### 20.2. Periodic Verification Drills

A valid lab check can:

1. Log in using a test identity.
2. Execute a permitted action.
3. Attempt a forbidden action on a test namespace.
4. Verify audit events emit per policy.
5. Confirm logs arrive in SIEM with accurate identity/timestamp.
6. Confirm no plaintext test passwords or PII appear in redacted log streams.

Never run simulated malicious tests in production without formal approval and procedures.

## 21. Backups Are Production Data Too

A snapshot can contain:

- PII, transaction history, and business data.
- Database user/role metadata depending on backup scope.
- Index definitions, schemas, and collection options.
- Encrypted field ciphertexts and Key Vault metadata depending on backup type.
- Topology/cluster metadata on full backups.

If a snapshot lands on an unmanaged device, an attacker can analyze it offline without ever passing through MongoDB RBAC again.

### 21.1. Impact of Backup Leakage

```text
MongoDB production:
  TLS = enabled
  RBAC = correct
  Network = private
  Audit = enabled

Yet:
  backup.zip uploaded to public storage
             |
             v
     attacker reads offline
```

**Strong controls on the live database are insufficient if backups have weaker access controls.**

### 21.2. CIA for Backups

| Property | Requirement |
|---|---|
| Confidentiality | Encryption, key management, strict export/download limits |
| Integrity | Checksums, immutable copies, protection from edits/deletion |
| Availability | Scheduled snapshots, PITR, restore drills, multi-region where required |
| Accountability | Audit access, restores, exports, deletions, and policy edits |

## 22. Permission Layers in a Backup System

Backup workflows span at least **five permission planes**:

1. **Database RBAC:** identity reading from MongoDB.
2. **Backup orchestration:** who can trigger or schedule snapshots?
3. **Backup storage:** who can list/get/put/delete objects?
4. **KMS:** who can encrypt/decrypt/unwrap keys?
5. **Restore target:** who can overwrite data and alter the target cluster?

Auditing only the DB username while ignoring the remaining four planes is incomplete.

### 22.1. Example Identity Separation

```text
backup_reader_db:
  reads source data for backup, no app write privileges.

backup_writer_storage:
  writes backup objects, cannot delete retention-locked objects.

restore_operator:
  restores only to approved targets.

backup_exporter:
  downloads/exports snapshots; high-risk role requiring dedicated approval.
```

Many platforms cannot isolate every single sub-action purely via RBAC; compensate using **approval workflows, environment separation, time-bound privileges, and logging**.

## 23. Self-Managed MongoDB: Built-In `backup` and `restore` Roles

In the `admin` database, MongoDB includes built-in roles such as:

- `backup`: privileges needed by backup tools within role scope.
- `restore`: privileges needed for restore operations per granted scope.

These are **database roles**, not Atlas project roles.

### 23.1. Creating a Dedicated Lab Backup Identity

In an environment **you administer**, after setting up an admin user and authentication:

```javascript
const admin = db.getSiblingDB("admin");

admin.createUser({
  user: "backup_lab_337",
  pwd: passwordPrompt(),
  roles: [
    { role: "backup", db: "admin" }
  ]
});
```

`passwordPrompt()` keeps literal passwords out of scripts. The `backup` role allows reading broad data for backups: **it grants access to massive data volumes** and must be tightly provisioned and monitored.

### 23.2. Never Grant `root` Just to Run `mongodump`

A backup cronjob does not need user administration, sharding administration, or business document write privileges just to read a snapshot.

Avoid:

```text
application_root_user -> mongodump
```

for “convenience”; if the job or secret leaks, privileges are vastly excessive.

### 23.3. Restores Often Need Different Privileges Than Backups

Permission to read the source does not mean permission to overwrite a target. Certain `mongorestore` options such as `--oplogReplay` carry documented requirements broader than standard `restore` privileges.

Therefore:

- Separate backup and restore identities.
- Grant restore privileges only under approved changes or incidents.
- Distinguish full-instance, database, collection, and oplog-replay restores.
- Test roles in staging first.

Never assume “holding the built-in `restore` role covers every restore mode”.

## 24. Practicing Backups with `mongodump`: Read, Not Write

### 24.1. Illustrative Command on a Lab Replica Set

On a secured host with MongoDB Database Tools and the backup user:

```bash
# Example on a lab replica set with TLS and backup account.
# Do not run this command inside mongosh.
mongodump \
  --uri="mongodb://db1.internal.example:27017/?replicaSet=rsLab&tls=true" \
  --tlsCAFile="/secure/path/ca.pem" \
  --username="backup_lab_337" \
  --authenticationDatabase="admin" \
  --archive="/secure/backups/rsLab-20261114.archive.gz" \
  --gzip \
  --oplog
```

This command **omits any embedded password**; configure secure credential/identity input per environment. Hostnames and paths are placeholders. `--oplog` applies to **full replica set dumps** where supported, not arbitrarily across all topologies.

**Important:** `--gzip` only compresses—it **does not encrypt** the backup.

### 24.2. Limits of `--oplog`

Per MongoDB Database Tools documentation:

- `mongodump --oplog` captures concurrent changes during a replica set dump for consistent recovery.
- Do not use `--oplog` with `--db` or `--collection` partial dumps.
- Do not treat `--oplog` as a mechanism for **backing up an entire sharded cluster through `mongos`**.
- Certain DDL or user/role changes during the dump can cause failures.
- `mongodump` is a logical backup with I/O and cache impact; large clusters often require dedicated snapshot/backup architectures.

### 24.3. Safety Checks

Avoid:

```text
Backup created -> upload straight to public bucket -> delete local copy
```

Prefer:

```text
AuthN + TLS -> Backup -> Encrypt -> Restricted storage
                                 -> Checksum/catalog
                                 -> Retention/immutability
                                 -> Restore drill
```

### 24.4. Practice Restoring Only Against an Isolated Target

Illustrative example:

```bash
# Restore ONLY to a separate lab MongoDB; never target production.
mongorestore \
  --uri="mongodb://restore-lab.internal.example:27017/?tls=true" \
  --tlsCAFile="/secure/path/ca.pem" \
  --archive="/secure/backups/rsLab-20261114.archive.gz" \
  --gzip
```

In real environments, restores require dedicated identities/permissions, archive verification, and possibly metadata/oplog replay flags. The command above **does not** automatically replay oplogs or guarantee a consistent cluster restore on its own.

**Never use `--drop`, `--oplogReplay`, or target production without an explicit plan and approval**; misdirected overwrites cause data loss.

## 25. Atlas: Fine-Grained Backup Roles

Atlas provides dedicated **Project Roles** for backups; verify exact role names and capabilities against current documentation.

| Atlas Project Role | Primary Scope |
|---|---|
| **Project Read Only** | View certain metadata/project/backup policies within scope; cannot create/export/restore |
| **Project Backup Creator** | List snapshots and take on-demand snapshots |
| **Project Backup Recovery Operator** | List and restore snapshots, **without** export/download rights |
| **Project Backup Export Operator** | List and export/download snapshots |
| **Project Backup Manager** | Combines creator, recovery, and export; manages backup policies within scope |
| **Project Owner** | Broad project administration, including many backup and governance actions |

These are **Atlas control-plane permissions**, not MongoDB database `readWrite`/`backup` roles.

### 25.1. Why Is Export Operator Highly Sensitive?

```text
No find() permission in the database
              |
              v
Holds backup snapshot export/download permission
              |
              v
Can obtain an offline copy of data for analysis
```

**Never grant Export Operator just to let someone check “did today's backup run?”.** For status checks, grant the lowest metadata read role that suffices.

### 25.2. Recovery Operator Differs from Export Operator

- **Recovery Operator:** restores snapshots to targets per product rules without gaining export/download privileges.
- **Export Operator:** downloads/exports snapshots without default restore privileges.
- **Backup Manager:** much stronger because it bundles multiple capabilities.

Splitting these privileges shrinks blast radius if an identity is compromised.

### 25.3. Limit Project Owner Too

Project Owner carries broad admin powers. Never give automation Project Owner just to trigger scheduled snapshots when a specialized role works.

### 25.4. Cross-Project / Cross-Organization Restores

Restoring across projects or organizations requires permissions on **both source and destination** per Atlas rules. Encryption-at-rest/KMS workflows add key and target constraints.

**Never assume restore permission on a destination project grants access to pull every snapshot from a source project.**

## 26. Separation-of-Duties Model for Backups

### 26.1. Responsibility Matrix

| Action | Suggested Person / Role |
|---|---|
| View backup status | On-call / read-only monitoring |
| Trigger on-demand snapshot | Backup Creator / dedicated job |
| Modify retention/policy | Backup Manager via change approval |
| Export/download snapshot | Export Operator with explicit approval |
| Restore to staging | Target-restricted Recovery Operator |
| Restore over production | Break-glass workflow with two-person approval |
| Delete snapshot | Strict separate policy / retention lock |
| Decrypt data via KMS | Independent, scoped key-use principal |
| Manage KMS key policies | Security / KMS administrators |
| View backup audit trails | Security / SOC with independent retention |

This is a reference model; Atlas roles alone do not enforce every two-person workflow. Approvals and just-in-time access often live in **IAM, control planes, and operational processes**.

### 26.2. Prevent Cross-Plane Privilege Abuse

Never let one identity hold all of:

```text
DB root
AND Atlas Project Owner
AND Backup Export
AND Object Storage Delete
AND KMS Key Admin
AND Audit Log Delete
```

If that identity is compromised, an attacker can read/destroy live data, wipe backups, and erase forensic logs together.

### 26.3. Break-Glass Access

When broad privileges are unavoidable:

- Enforce strict time bounds.
- Record justification/ticket and approver.
- Require MFA/conditional access at the identity provider where supported.
- Audit both elevation and subsequent actions.
- Revoke and review post-incident.

## 27. Protecting Backup Storage

### 27.1. Object Storage / IAM

Backups in S3/GCS/Azure Blob or equivalent require:

- Only the backup writer can write to the designated prefix/bucket.
- Only the restore identity can read recovery objects.
- No public anonymous reads.
- Restrict bucket listing where unnecessary.
- Block or tightly govern delete/overwrite actions.
- Cloud audit logs for `GetObject`/`PutObject`/`DeleteObject`.
- Network restrictions/private endpoints where supported.

### 27.2. Encrypt at Rest + Encrypt in Transit

Backups require encryption at rest, TLS in transit, and clear key management.

```text
Dump/snapshot
  |
  +-- TLS on transfer
  |
  +-- KMS-managed encryption at rest
  |
  +-- IAM limits access to encrypted object
  |
  +-- KMS policy limits decrypt capability
```

A user able to read an object without permission to decrypt adds defense, provided KMS policies still let authorized recovery services restore during incidents.

### 27.3. Multi-Region / Multi-Account

Copying backups to an isolated region/account reduces risk from regional disasters or single-account ransomware.

**Never call it multi-region protection if copies live in the same account under credentials able to delete every copy.** Compromising that account still wipes everything.

### 27.4. Versioning and WORM

Object versioning and Write Once Read Many / retention locks restrict identities from deleting or altering backups before retention expires.

Keep in mind:

- Versioning alone does not block sufficiently privileged users from deleting all versions.
- WORM/retention locks carry strict configuration rules.
- Immutability increases storage costs and complicates lawful deletion requests.
- Permissions to alter retention or compliance locks become a critical attack point.

## 28. Atlas Backup Compliance Policy

MongoDB Atlas offers **Backup Compliance Policy** on supported clusters/tiers to enforce strict retention and recovery rules.

Per Atlas docs, once active, it can prevent:

- Deleting backup snapshots.
- Shortening retention below policy floors.
- Disabling Cloud Backup against policy.
- Weakening certain PITR/continuous backup settings.
- Deleting projects while protected snapshots remain.

Disabling the policy requires special verification/support procedures with MongoDB; **it is not a toggle any Project Owner can turn off at will**.

### 28.1. Do Not Enable Compliance Policy Just Because It “Sounds Safe”

Before enabling, evaluate:

- Legal and retention mandates.
- Storage costs that cannot be lowered arbitrarily.
- Procedures for lawful data-deletion requests.
- Process for requesting retention reductions.
- Impact on project lifecycle.
- Approvers and support contacts.

In production, this is a **governance and compliance commitment**, not a lab switch.

### 28.2. Immutability Does Not Stop Harmful Exports

WORM snapshots prevent deletion/modification, yet **do not stop an identity holding Export Operator from copying data elsewhere**. Still govern export/download rights and log every export.

## 29. Backup Retention, RPO, RTO, and PITR

### 29.1. Retention

Directional example:

```text
Hourly snapshots: retain 7 days
Daily snapshots:  retain 30 days
Monthly snapshots: retain 12 months
```

Exact windows are illustrative. Align with:

- Risk of late-discovered data corruption.
- Point-in-time recovery requirements.
- Privacy/data-deletion obligations.
- Cost and backup immutability.
- Cross-region copy security.

### 29.2. RPO and RTO

**RPO (Recovery Point Objective)** is the maximum acceptable data loss.

**RTO (Recovery Time Objective)** is the maximum acceptable service recovery time.

Example:

```text
Business requirement:
  RPO <= 15 minutes
  RTO <= 2 hours
```

A single snapshot every 24 hours **cannot meet a 15-minute RPO**. You need continuous backup/PITR or an equivalent strategy supporting fine-grained recovery points.

### 29.3. PITR Is Not Forever Second-by-Second History

Point-in-Time Restore operates **only within the supported restore window and constraints**. Never treat PITR as an unbounded event store.

Snapshots and oplog segments used for PITR must be retained and restored coherently per system design.

### 29.4. Sharded Cluster Snapshot Consistency

A sharded cluster spans multiple replica sets plus the balancer. Uncoordinated per-shard backups can yield a **cluster-wide inconsistent backup**.

For self-managed clusters, use MongoDB-supported backup methods accounting for DDL, cross-shard transactions, and the balancer. Never run `mongodump --oplog` via `mongos` expecting consistent PITR across an entire sharded cluster.

## 30. Restoring Is More Than Downloading Files and Running a Command

### 30.1. Pre-Restore Controls

1. Verify justification and target environment.
2. Confirm exact snapshot/timepoint.
3. Verify backup integrity and key availability.
4. Confirm requester permissions and approvals.
5. Assess impact on existing data at the target.
6. Verify topology, MongoDB version, and encryption mode.
7. Prepare a rollback/recovery plan if the restore fails.
8. Prepare post-restore application validation.

### 30.2. Atlas Cluster-Level Restores Can Overwrite Target Data

Per Atlas docs, a cluster-level restore can **erase existing data on the target cluster before restoring**. Thus an operator holding restore permissions is a sensitive identity even without snapshot export/download rights.

**Always double-check source/target and prefer restoring into a new/isolated cluster for testing whenever the use case allows.**

### 30.3. Restore Drills in an Isolated Environment

```text
Select snapshot
      |
      v
Restore to isolated cluster
      |
      v
Check key/cert/network access
      |
      v
Validate collections/indexes/counts
      |
      v
Run business invariants / app smoke tests
      |
      v
Record elapsed time vs RTO
      |
      v
Destroy/retain test target under approved policy
```

A restore drill can materialize a **copy of production PII** inside a test environment. Never expose full production data to staging without formal protections and justification.

### 30.4. Key Availability

With customer-managed encryption and CSFLE/Queryable Encryption:

- Master keys, DEKs, Key Vaults, and decryption privileges may all be required.
- Revoked or lost keys can render restored snapshots unusable.
- Restoring ciphertext documents does not prove apps can read plaintext.

Key lifecycle verification is **part of backup testing**, not an isolated security-team chore.

## 31. Auditing Backup Actions

Events to monitor:

- Changes to backup policies, retention, or PITR windows.
- On-demand snapshot creation.
- Export/download initiation and completion.
- Restore job initiation, target, and actor.
- Snapshot deletions or deletion attempts.
- IAM role changes tied to backups.
- KMS grants or key policy modifications.
- Anomalous object-storage reads/deletes.
- Backup job failures and snapshot age exceeding thresholds.

### 31.1. Audit Logs Do Not Live in One Place

```text
Backup policy changed   -> Atlas Activity Feed / control plane
Snapshot exported       -> Atlas backup activity + storage logs
Object downloaded       -> Cloud object storage access logs
KMS Decrypt called      -> KMS audit logs
Restore writes database -> Restore job logs + database/application checks
```

Never rely solely on MongoDB database `authCheck` to monitor snapshot exports.

### 31.2. Actionable Alerts

| Scenario | Suggested Alert |
|---|---|
| Snapshot export outside change window | High-severity notification |
| Spike in download counts | Investigate potential exfiltration |
| Unusual retention reduction | Require approval/review |
| Production restore without ticket | Block/escalate per process |
| KMS Decrypt from unfamiliar identity | Security alert |
| Missing fresh backup snapshot | Availability alert |
| Failed restore drill | RTO/recoverability risk |
| Audit collector outage | Detection coverage gap |

## 32. Scenario 1: Exposed Backup Credential

### 32.1. Context

A CI secret containing `backup_lab_337`'s credential leaks into logs. The user holds the `backup` role in `admin`.

### 32.2. Risk

If an attacker reaches the network and uses that credential, they can read massive data within the `backup` role's scope, causing large-scale exfiltration even though ordinary app users lack such wide access.

### 32.3. Protection Layers

- Private networking / mTLS or server-verified TLS.
- Separating `backup` role from `root`.
- Secret manager and rotation.
- Egress restrictions.
- Authentication/access auditing and anomaly detection.
- KMS encryption on created snapshots.

### 32.4. Runbook

1. Confirm the secret genuinely leaked and assess exposure scope.
2. Restrict network/access per incident policy.
3. Issue a new credential and migrate the backup job.
4. Revoke/rotate the leaked credential.
5. Correlate audit logs, source IPs, dump/export jobs, and egress.
6. Confirm no backups were modified or deleted.
7. Fix the leak source in CI/repos/logs.
8. Update secret scanning and preventive controls.

**Never delete a log line and assume the credential is safe.**

## 33. Scenario 2: Logs Containing PII

### 33.1. Context

A Java app's `CommandListener` logs full BSON commands. Customer lookup queries include phone numbers; logs ship to an observability platform readable by every developer.

### 33.2. Impact

- Creates a duplicate copy of PII.
- Retention differs from the source collection.
- Broadens who can read sensitive data.
- Logs may be exported to third parties.

### 33.3. Remediation

1. Stop/update raw command logging cleanly without disrupting service.
2. Replace with allowlisted structured fields.
3. Verify MongoDB diagnostic redaction where supported.
4. Assess the scope of stored/replicated logs.
5. Apply sensitive-data deletion/retention procedures.
6. Tighten log access permissions and evaluate security/compliance notification.
7. Add regression tests ensuring raw phones, emails, and passwords never reappear.

### 33.4. Never Rely on One Regex as Your Entire Policy

Redaction like “replace any string containing `@` with `***`” misses phone numbers, nested JSON, binary payloads, tokens, and new fields. Prioritize **not logging raw data in the first place**.

## 34. Scenario 3: Unauthorized Snapshot Export

### 34.1. Context

A contractor hired only to check backup status was granted `Project Backup Manager`, which includes export/download rights. They export a customer snapshot to an unmanaged environment.

### 34.2. Prevention

- Grant read-only or the minimal role needed for the job.
- Separate Backup Export Operator from backup schedule managers.
- Require explicit approvals for exports/downloads.
- Enforce IAM/mTLS/conditional access and logging.
- Govern approved export destinations/devices.

### 34.3. Detection

Monitor Atlas backup activities and cloud storage access logs, cross-referencing change tickets, usual hours, byte volumes, and destinations.

### 34.4. Limits of Immutability

WORM snapshots can still be **copied** by an identity holding read/export rights. Immutability protects **integrity and availability**, not **confidentiality** on its own.

## 35. Scenario 4: Ransomware Wiping Source and Backups

### 35.1. Context

An attacker compromises an overly broad account:

```text
MongoDB admin + Backup Manager + Storage Delete + KMS Admin
```

They wipe live data, try deleting snapshots, and attempt disabling keys.

### 35.2. Reducing Blast Radius

- Separate DB, backup, cloud storage, and KMS identities.
- Enforce immutable backups/retention locks and cross-account/region copies where needed.
- Audit and alert on drops, user role edits, snapshot policy changes, and key changes.
- Enforce JIT/break-glass for dangerous privileges.
- Maintain verified restore drills and proven RPO/RTO.

### 35.3. Never Treat a Replica Set as a Backup

A valid delete on the primary replicates to secondaries. Replica sets improve availability against node hardware faults, not against **accidental deletion, bad writes, or ransomware**.

## 36. Scenario 5: Audit Destination Fills Disk

### 36.1. Context

Security enables `auditAuthorizationSuccess` across all workloads. Log volume multiplies, nearly filling the audit disk.

### 36.2. Two Simultaneous Risks

1. **Confidentiality:** excessive audit events may capture sensitive metadata or queries.
2. **Availability:** failing to write to the audit destination can severely disrupt the MongoDB server.

### 36.3. Response

- Alert early on disk usage and audit event rates.
- Verify approved filters and policies.
- Expand capacity, log shipping, and rotation per process.
- Adjust audit coverage only after security review.
- Benchmark performance and update log ingestion budgets.

**Never simply disable auditing in production without incident/change approval** just to free disk space.

## 37. Hands-On Exercises

### Exercise 1 — Identify Log Sources

Assign the right source for each:

1. A user fails MongoDB login.
2. An admin changes backup retention in Atlas.
3. An operator downloads a snapshot from object storage.
4. A Java service denies a refund due to insufficient business role.
5. MongoDB logs a slow query.

Why can no single log source answer all five?

### Exercise 2 — Reading an Audit Event

Given an illustrative event:

```json
{
  "atype": "authenticate",
  "users": [{ "user": "orders_reader", "db": "admin" }],
  "remote": { "ip": "10.10.1.22", "port": 49210 },
  "result": 0
}
```

Identify the action, actor, endpoint, and outcome. If `result` were non-zero, why must you check the `atype` code table instead of treating it as an HTTP status?

### Exercise 3 — Audit Coverage

A company enables database auditing while `auditAuthorizationSuccess` stays off. The CEO asks: “Are we logging every time an employee successfully reads PII?”. How do you answer, and which settings must you verify?

### Exercise 4 — Writing an Audit Filter

Design a filter covering `authenticate`, `authCheck`, `createUser`, `grantRolesToUser`, `revokeRolesFromUser`, and `dropCollection`. Name at least three critical event classes still missed and how to verify coverage.

### Exercise 5 — Audit Overhead

A cluster serves 25,000 reads/second. Security wants to audit all read successes. List metrics to benchmark beforehand and a plan to prevent audit disk/collector overload.

### Exercise 6 — Diagnostic vs. Database Audit

A developer sees `"connection accepted"` in server logs and concludes “all CRUD operations are audited”. Why is that wrong?

### Exercise 7 — `redactClientLogData`

Explain:

1. Which edition/deployments include it?
2. What content does it redact?
3. What is the debugging trade-off?
4. Why is application log redaction still required?
5. Can you assume audit logs and backups are automatically redacted?

### Exercise 8 — Allowlist Logging

An API currently logs raw `req.body`. Design an event with at most eight fields supporting investigations without logging raw emails, phones, passwords, or request tokens.

### Exercise 9 — HMAC vs. Hash

Why is `SHA256(email)` weak for protecting emails in logs? When should you use HMAC, and when should you omit identifiers completely?

### Exercise 10 — Driver Command Monitoring

A Java `CommandListener` logs `event.getCommand()` at `DEBUG`. Explain the risk and propose a safe metadata set for measuring latency and query types.

### Exercise 11 — Protecting Audit Files

An audit JSON file sits on the DB host writable by the MongoDB user, and an attacker gains OS admin. Propose an architecture with off-host shipping, immutability, retention, and tamper evidence.

### Exercise 12 — MongoDB Backup Role

Why is granting built-in `backup` on `admin` better than granting `root` to a backup job? Why is `backup` still highly sensitive despite lacking user-admin privileges?

### Exercise 13 — Atlas Backup Roles

Staff members need to:

- Only monitor backup health.
- Trigger snapshots during deployments.
- Restore to staging.
- Export snapshots for legal requests.

Map each task to the least-privileged project role and explain why not to give everyone `Project Backup Manager`.

### Exercise 14 — Production Restore

An Atlas `Project Backup Recovery Operator` needs to restore a snapshot over production. List approval steps, target verification, rollback planning, and why restores can wipe target data.

### Exercise 15 — Multi-Plane Backup Permissions

Build a permission matrix covering database reads, backup creation, object gets, object deletes, KMS decrypt, and target restores. Why should no single user hold all of them?

### Exercise 16 — Immutable Backups

Compare object versioning, retention locks/WORM, and Atlas Backup Compliance Policy. What does each protect? Does any of them stop data exports?

### Exercise 17 — Logical Backups

A team runs `mongodump --oplog` through `mongos` and claims “the entire sharded cluster backup is definitely consistent”. What is wrong, and how should backups be verified per MongoDB docs?

### Exercise 18 — RPO/RTO

Requirements specify RPO 15 minutes and RTO 2 hours, yet the team takes one daily snapshot and has never run a restore test. Explain why targets are unproven and design a test that also verifies key availability.

### Exercise 19 — PITR and Retention

Data corruption is discovered after 20 days; the PITR window is only 7 days, and the latest monthly snapshot is 30 days old. Can current PITR restore straight to 20 days ago? How should retention align with incident detection times?

### Exercise 20 — Snapshot Leak

A contractor with export permissions downloads a snapshot onto an unmanaged device. Even though the source database used TLS and RBAC, why is this still an incident? Which log sources help investigate?

### Exercise 21 — Threat Modeling Workshop

Diagram:

```text
Java API -> MongoDB -> Atlas Cloud Backup
              |
              +-> Audit / SIEM
              +-> KMS
```

Identify at least six trust boundaries and assess Confidentiality/Integrity/Availability risks across each.

### Exercise 22 — Tabletop Incident Response

You detect:

- A leaked backup credential.
- A sudden drop in audit event rates.
- An unscheduled snapshot export.

Draft an incident runbook covering containment, evidence preservation, rotation, access review, storage/KMS logs, integrity checks, and executive reporting.

### Exercise 23 — Testing Log Redaction Limits

Design a lab test using **synthetic data** containing `demo-secret-337`, fake phone numbers, and fake tokens. Verify:

1. Server logs before and after enabling redaction.
2. Application logs with and without allowlists.
3. Whether audit events include `param`.
4. Whether the log collector retains raw copies.

Never use real PII or alter production configs for tests.

### Exercise 24 — Unified Retention Policy

MongoDB source data is retained 30 days, app logs 180 days, audit logs 2 years, and backups 12 months. List privacy/legal questions to resolve and risks when a user is deleted from the database while PII persists in copies.

### Exercise 25 — Complete Design

Create a production MongoDB security design covering:

- Auditing authentication, admin actions, and selected sensitive reads.
- Log redaction in server and Java application.
- SIEM with tamper-evident archiving.
- Dedicated backup service identity.
- Atlas roles separating create/recovery/export.
- Backup encryption/KMS, immutable retention, PITR, and restore drills.
- Alerts for audit gaps, backup exports, role changes, and production restores.

Specify **owner**, **evidence**, **residual risk**, and **verification method** for each control group.

## 38. Step-by-Step Implementation Process

### Phase A — Define Requirements

1. Define mandatory auditable events: auth failures, role changes, DDL, sensitive data access.
2. Classify PII/secrets across databases, commands, diagnostic logs, audit logs, and backups.
3. Separate compliance requirements from temporary debugging needs.
4. Confirm Atlas/Enterprise/Community capabilities in your actual deployment.
5. Assign owners for database auditing, app logging, backups, SIEM, and KMS.

### Phase B — Design and Test

1. Build audit filters with explicit coverage and benchmark overhead.
2. Configure audit destinations, disk sizing, and off-host shipping.
3. Enable supported redaction and test with synthetic data.
4. Replace raw logging with structured allowlists and trace IDs.
5. Configure log RBAC and immutable/archive retention.
6. Select database `backup` roles or Atlas backup project roles appropriately.
7. Define permissions across backup storage, KMS, and restore targets.
8. Configure encryption, immutability, and backup policies.
9. Verify RPO/RTO and PITR via restore drills.

### Phase C — Controlled Go-Live

1. Execute change review and roll out across topology.
2. Confirm audit events arrive from all required components.
3. Confirm collectors/SIEM ingest cleanly and alerts fire.
4. Verify unnecessary privileges are denied.
5. Confirm backup snapshots enforce proper retention and encryption.
6. Test read/export/restore with authorized and unauthorized identities in lab.
7. Collect evidence and update runbooks.

### Phase D — Continuous Operations

1. Review identities and privileges periodically.
2. Monitor audit volume, dropped/late events, disk usage, and alert coverage.
3. Scan logs for leaked PII/secrets via approved mechanisms.
4. Control changes to audit filters and backup policies.
5. Monitor exports, downloads, restores, and KMS usage.
6. Run credential rotations and restore drills.
7. Keep retention, topology, compliance, and version compatibility current.

## 39. Summary

**MongoDB auditing, log redaction, and backup permissions are three independent controls that must work together.** Database audits track configured identities and event types; diagnostic logs serve operations; application audits capture business intent; and Atlas control-plane plus cloud storage logs complete the trail for backups and exports.

**Log redaction requires multiple layers.** `security.redactClientLogData` on Enterprise/Atlas reduces sensitive values in diagnostic messages, but does not automatically scrub every driver, application, audit, or backup log. Prefer never logging raw payloads/URIs/commands, using structured allowlists, correlation IDs, controlled masking/HMAC, and strict SIEM permissions/retention.

**Backups are production data requiring equivalent security.** MongoDB's database `backup` role differs from Atlas `Project Backup Creator`, `Recovery Operator`, `Export Operator`, and `Backup Manager`. Separate view/create/export/restore rights, storage and KMS permissions, enforce encryption and immutable retention where suitable, and monitor backup actions. Replica sets do not replace backups; backups without keys and restore drills do not prove recoverability.

**Done is not “checking a box”.** You need clear policy goals, test evidence, accountable owners, alerts, sensitive-data controls, and runbooks. When all three layers are designed properly, an organization can investigate incidents reliably without turning logs or backups into the next data leak.

## 40. References

- [MongoDB Manual — Auditing](https://www.mongodb.com/docs/manual/core/auditing/): auditable actions, guarantees, and limits.
- [MongoDB Manual — Configure Auditing](https://www.mongodb.com/docs/manual/tutorial/configure-auditing/): JSON/BSON files, console, and syslog.
- [MongoDB Manual — Configure Audit Filters](https://www.mongodb.com/docs/manual/tutorial/configure-audit-filters/): event filters and runtime configuration.
- [MongoDB Manual — Audit Messages](https://www.mongodb.com/docs/manual/reference/audit-message/mongo/): `atype`, `param`, `result`, and actions.
- [MongoDB Manual — Configuration File Options](https://www.mongodb.com/docs/manual/reference/configuration-options/): `auditLog` and `redactClientLogData`.
- [MongoDB Manual — Log Messages](https://www.mongodb.com/docs/manual/reference/log-messages/): diagnostic logs and Enterprise redaction.
- [MongoDB Atlas — Database Auditing](https://www.mongodb.com/docs/atlas/database-auditing/): Atlas support, audit filters, and permissions.
- [MongoDB Atlas — Project Roles](https://www.mongodb.com/docs/atlas/reference/user-roles/): distinguishing backup creator, recovery, export, and manager.
- [MongoDB Atlas — Cloud Backup](https://www.mongodb.com/docs/atlas/backup/cloud-backup/overview/): backup mechanisms and prerequisites.
- [MongoDB Atlas — Backup Compliance Policy](https://www.mongodb.com/docs/atlas/backup/cloud-backup/backup-compliance-policy/): retention enforcement and snapshot deletion prevention.
- [MongoDB Atlas — Restore from Backup](https://www.mongodb.com/docs/atlas/backup/cloud-backup/restore-overview/): permissions, prerequisites, and target impacts.
- [MongoDB Manual — Built-In Backup and Restoration Roles](https://www.mongodb.com/docs/manual/reference/built-in-roles/): `backup` and `restore`.
- [MongoDB Database Tools — mongodump](https://www.mongodb.com/docs/database-tools/mongodump/): logical dumps, `--oplog`, and sharded cluster limits.
- [MongoDB Manual — Back Up and Restore with Database Tools](https://www.mongodb.com/docs/manual/tutorial/backup-and-restore-tools/): verifying backups and restore permissions.
