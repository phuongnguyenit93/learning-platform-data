# Audit Logging, Sensitive Data Masking, and Log Retention

## 1. Why Must Integration Observability Address Both Privacy and Auditing?

A Spring Boot integration application typically spans multiple steps without a single shared transaction boundary: receiving HTTP requests, calling payment services, writing databases, reading caches, publishing JMS/Kafka events, and running Spring Integration adapters. When an order updates incorrectly or an event processes twice, operations needs to answer:

- **Who or what component** requested the change?
- **Which action** was accepted, rejected, completed, or failed?
- **Which business entity** was affected, and at what timestamp?
- **Which sends, retries, and replays** belong to the same business operation?
- What evidence remains once the HTTP request ended, the message was ACKed, and traces expired?

Answering those requires **operational logs**, **audit trails**, and **metric/trace observability**. Still, logging more data does not automatically make systems safer. Logs can capture tokens, passwords, customer profiles, payment details, or third-party payloads. Once logs flow through collectors, search indexes, dashboards, alerts, and backups, sensitive data spreads across many systems.

Therefore, two goals must be designed together: **retaining sufficient evidence to explain and reconcile integration flows**, while **minimizing what data is collected, who can read it, and how long it is kept**.

In the **SPRING_BOOT_INTEGRATION** module, this ties directly to configuration, data contracts, transactions, retries, idempotency, HTTP clients, databases, caches, message brokers, and Spring Integration adapters. **Integration Observability** pays special attention to cross-system evidence and failure windows that no single log line can capture alone.

### Learning Outcomes

After this lesson, you will be able to:

1. Distinguish **operational logs**, **audit events**, **security events**, **metrics**, and **distributed traces**.
2. Design an audit schema with business identifiers, outcomes, timestamps, and trustworthy actor sources.
3. Persist audits alongside business transactions or via outboxes, understanding guarantees across crashes and retries.
4. Minimize sensitive data using **allowlists**, masking, tokenization, RBAC, and untrusted-input sanitization.
5. Specify retention, legal holds, archiving, and deletion across the **entire lifecycle** of logs.
6. Test audit completeness, data confidentiality, and post-incident traceability.

## 2. Distinguishing Types of System Evidence

| Data type | Question answered | Examples | Limits to remember |
| --- | --- | --- | --- |
| **Operational log** | What is each component doing and where did an error occur? | HTTP 502, broker timeout, retry #3, SQL pool exhausted. | May be sampled, rotated, or lost on process crash; not automatically long-term business proof. |
| **Audit event** | Who/what acted on a business entity, and with what outcome? | Order 1042 moved from `PENDING` to `PAID` on `paymentId X`. | Must define semantics, read access, durability, and integrity; avoid dumping full payloads. |
| **Security event** | Was there a notable access attempt or permission change? | Failed login, role change, access denied. | May need recording even when business transactions roll back; risks leaking identities/secrets. |
| **Metric** | What are the overall trends and blast radius? | Error rate, p95 latency, DLQ depth, outbox backlog. | Aggregated numbers; cannot prove individual order state. |
| **Distributed trace** | Which hops did one request cross and how long did each take? | Span HTTP → DB → JMS producer → consumer. | May be sampled or expire; `traceId` never replaces audit IDs or transaction IDs. |

For example, a trace shows a delivery API call took 2 seconds, yet does not prove **the order was delivered**. Likewise, an audit event **`ShipmentRequested`** only proves the system recorded an intent to request shipment; it does not prove the carrier accepted it without matching confirmation evidence.

### 2.1. Distinguish Intent Events from Outcome Events

These names carry different meanings:

- **`PaymentCaptureRequested`:** the system initiated a capture request.
- **`PaymentCaptureAccepted`:** the partner reported accepting the request for processing.
- **`PaymentCaptured`:** an authoritative source confirmed funds were captured.
- **`PaymentCaptureFailed`:** the operation failed based on verifiable evidence.

Never record **`PaymentCaptured`** merely because a network-level HTTP call succeeded if the partner returned status **`PENDING`**. Audit events must reflect **verified truth**, not merely that Java execution passed a line of code.

Similarly, **message consumed** differs from **business operation committed**; **producer send invoked** differs from **message durably accepted by broker**; **database transaction committed** differs from **downstream projection synchronized**.

## 3. Designing a Traceable Audit Event

An audit event needs a **stable, versioned schema**. Minimal fields:

| Field | Meaning |
| --- | --- |
| **auditEventId** | Unique audit record ID (typically UUID) for deduplication during writes/delivery. |
| **eventType / action** | Action category: `ORDER_CONFIRMED`, `PAYMENT_CAPTURE_FAILED`, `ROLE_CHANGED`. |
| **actorType / actorRef** | User, service, or scheduled job requesting the action; controlled identifier. |
| **resourceType / resourceRef** | Target entity, e.g., `ORDER/1042`; scoped by tenant in multi-tenant systems. |
| **outcome** | `REQUESTED`, `COMMITTED`, `REJECTED`, `FAILED`, `COMPENSATED`... with explicit semantics. |
| **occurredAt** | Timestamp when the event occurred at the source. |
| **recordedAt** | Timestamp when the audit store accepted the record. |
| **sourceSystem / schemaVersion** | Emitting component and audit contract version. |
| **correlationId / traceId** | Links steps of a flow for investigation; never used as the unique business key. |
| **businessOperationId / messageId** | Stable business key or upstream `eventId` to track retries and duplicates. |
| **details** | Approved minimal attributes needed to explain the outcome. |

`auditEventId` identifies only the audit record; `businessOperationId` links retries of one action; `messageId` identifies a message; `traceId` links spans in one execution path. One business action can span multiple traces across retries or restarts. Never assume any one of these IDs replaces the others.

### 3.1. PostgreSQL Schema Example

An append-only business audit table can be defined as:

~~~sql
CREATE TABLE integration_audit_events (
    audit_event_id UUID PRIMARY KEY,
    tenant_ref     VARCHAR(100) NOT NULL,
    event_type     VARCHAR(100) NOT NULL,
    outcome        VARCHAR(32) NOT NULL,
    actor_type     VARCHAR(32) NOT NULL,
    actor_ref      VARCHAR(150) NOT NULL,
    resource_type  VARCHAR(64) NOT NULL,
    resource_ref   VARCHAR(150) NOT NULL,
    operation_ref  VARCHAR(150),
    correlation_id VARCHAR(128),
    source_system  VARCHAR(100) NOT NULL,
    schema_version INTEGER NOT NULL,
    occurred_at    TIMESTAMPTZ NOT NULL,
    recorded_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    details        JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX idx_integration_audit_resource
    ON integration_audit_events (
        tenant_ref, resource_type, resource_ref, occurred_at
    );

CREATE INDEX idx_integration_audit_time
    ON integration_audit_events (recorded_at);
~~~

This is an illustrative model: ID types, partitioning/indexing, and permissions must match workload scale and data policies. **`details`** should store only approved fields such as **`oldStatus`**, **`newStatus`**, and **`upstreamEventId`**—never raw HTTP bodies or whole serialized JPA entities.

In multi-tenant applications, every query must enforce tenant and resource access checks. Simply having a **`tenant_ref`** column in the schema does not enforce authorization.

### 3.2. Audits Are Not Arbitrary Mutable Tables

Useful audit trails restrict history modification:

- Application accounts typically hold only **INSERT** privileges via an audit writer interface, without `UPDATE`/`DELETE` on historical rows.
- Readers are authorized by role, data classification, and tenant scope; reading audits may itself be audited.
- When an erroneous audit entry is discovered, append a **correction event** referencing the original `auditEventId` rather than silently editing old rows.
- Implement tamper/loss detection: least privilege, isolated replica stores, cryptographic signing/hashing by design, access controls, and count reconciliation.

A **hash chain** detects tampering only if keys, anchor references, or verification digests live in a sufficiently independent trust domain. If an attacker can alter logs, hashes, and root anchors together, local hashing creates no immutability guarantee. For strong compliance, consider WORM/append-only storage, digital signatures, off-host logging, and admin-access auditing.

## 4. Writing Audits at the Right Transaction Boundary

### 4.1. Success Audits Must Bind to Business Commits

Suppose **Order Service** updates an order from **`PENDING`** to **`CONFIRMED`**. If the app records **`ORDER_CONFIRMED`** before the database commits and the transaction later rolls back, the audit states a falsehood.

When business state and the audit table live in the same database, write both inside **one JDBC/JPA transaction**:

~~~java
@Service
class OrderConfirmationService {
    private final JdbcTemplate jdbc;

    OrderConfirmationService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void confirm(long orderId, String tenantRef,
                        String actorRef, String operationRef) {
        int changed = jdbc.update("""
            UPDATE orders
               SET status = 'CONFIRMED'
             WHERE id = ? AND status = 'PENDING'
            """, orderId);

        if (changed != 1) {
            throw new IllegalStateException(
                "Order missing or unexpected state");
        }

        jdbc.update("""
            INSERT INTO integration_audit_events (
                audit_event_id, tenant_ref, event_type, outcome,
                actor_type, actor_ref, resource_type, resource_ref,
                operation_ref, source_system, schema_version,
                occurred_at, details
            )
            VALUES (
                ?, ?, 'ORDER_CONFIRMED', 'COMMITTED',
                'USER', ?, 'ORDER', ?, ?,
                'order-service', 1,
                ?, jsonb_build_object('newStatus', 'CONFIRMED')
            )
            """,
            UUID.randomUUID(), tenantRef, actorRef,
            Long.toString(orderId), operationRef,
            Timestamp.from(Instant.now()));
    }
}
~~~

This snippet illustrates **`JdbcTemplate`** on PostgreSQL (requiring standard Java/Spring imports). **`@Transactional`** must bind to the matching database transaction manager, assuming one database transaction spans both statements. Production systems must also verify **tenant ownership**, authenticated actor identity, concurrency, `operationRef` idempotency, business validation, and valid state transitions.

If the audit `INSERT` fails, the transaction rolls back order confirmation too. This is **fail-closed** behavior, appropriate when business state must never commit without an audit record. Because it trades availability and latency, choose it deliberately per risk requirements; ordinary operational logs rarely require this strictness.

**Note:** if the event records `COMMITTED` while the system still awaits an HTTP partner response, label the outcome clearly as **internal commit**. Never misinterpret it as partner completion.

### 4.2. Failures and Rejections Need a Separate Path

When a business transaction rolls back, any audit row inserted **inside that same transaction** rolls back too. Therefore, the pattern above cannot durably record **`LOGIN_FAILED`**, **`ACCESS_DENIED`**, or rejected business validations.

Design an independent, controlled **security audit** path able to persist durably after request failures—such as a dedicated security log pipeline, durable queue, or deliberate separate transaction recording **`REJECTED`/`FAILED`** without faking success commits.

Never scatter **`REQUIRES_NEW`** across every audit write without checking semantics: it could commit a "success" audit even when the parent transaction rolls back. In separate transactions, events should describe **attempts** or **rejections**, paired with final outcome tracking if needed.

### 4.3. Shipping Audits to a Centralized System

A local **database commit** does not atomically commit delivery to a broker, OpenSearch, or SIEM. Calling an HTTP/log collector after transaction commit leaves a crash window where the process can die between steps and drop centralized audit records.

One solution is a **transactional outbox**:

~~~mermaid
flowchart LR
    A[Business service] -->|Single DB transaction| B[(Business state)]
    A -->|Single DB transaction| C[(Audit / outbox record)]
    C -->|Relay with retries| D[Broker or audit collector]
    D --> E[(Centralized audit store)]
    E --> F[Authorized lookup]
~~~

Inside one database transaction, persist both business state and the audit/outbox record. A relay ships events and marks them sent. If the relay crashes after the destination stored the event yet before updating local state, it may send a **duplicate**. The centralized store must deduplicate by **`auditEventId`** and track delivery state.

Remember that an outbox yields **controlled replay**, not automatic "exactly-once physical delivery". Monitor outbox backlog, oldest unsent event age, and destination ingestion counts.

## 5. Classifying Sensitive Data Before Logging

A practical rule is **logging only data genuinely required for a defined purpose**. Sensitive data can sneak in through HTTP bodies, headers, URL query parameters, message payloads, exceptions, stack traces, MDC, baggage, or objects serialized directly by loggers.

| Data class | Examples | Default handling |
| --- | --- | --- |
| **Authentication secrets** | Passwords, API keys, `Authorization` headers, refresh/access tokens, session cookies, private keys. | **Never log**; if leaked, treat as a secret-exposure incident rather than just masking dashboards. |
| **Payment or highly sensitive identity data** | Card details, national IDs, bank accounts, health records. | Never log raw values; use reference IDs and aggregates only when strictly required. |
| **Personal data** | Full names, emails, phone numbers, addresses, contextual IPs. | Minimize; use controlled reference IDs/pseudonyms; enforce RBAC and retention. |
| **Business identifiers** | `orderId`, `correlationId`, `eventId`, `tenantRef`. | Usually helpful for tracing; still assess user linkability and read permissions. |
| **Technical metadata** | Route templates, status codes, error codes, durations. | Prefer standardized fields, bounded cardinality, zero embedded sensitive payloads. |

Never assume any field is "completely safe" just because it ends in **`ID`**. An `orderId` can identify a customer; a plain unsalted hash of an email can be reversed via dictionary attacks. Classify data by re-identification risk and context.

### 5.1. Field Allowlists Beat Blocklists

Suppose a request contains:

~~~json
{
  "orderId": "1042",
  "customerEmail": "alice@example.org",
  "cardToken": "tok_example_secret",
  "authorization": "Bearer sample-secret",
  "amountMinor": 125000,
  "currency": "VND"
}
~~~

**Never** log the whole object and try to replace `"password"` or `"token"` keys with asterisks. Secrets show up in newly added fields, nested objects, headers, or exception messages.

Instead, construct a **log event allowlist**:

~~~json
{
  "event": "order_payment_request_completed",
  "orderRef": "1042",
  "amountMinor": 125000,
  "currency": "VND",
  "outcome": "ACCEPTED",
  "dependency": "payment-provider",
  "durationMs": 86,
  "correlationId": "req-8f3c"
}
~~~

If **`amountMinor`** is unnecessary for troubleshooting, omit it or bucket it. Sample values above are synthetic placeholders, not templates for copying sensitive fields into production logs.

### 5.2. Masking, Tokenization, and Pseudonymization

| Technique | How it works | Caveats |
| --- | --- | --- |
| **Omission** | Never emit the sensitive field in the first place. | Most effective whenever raw values are not needed. |
| **Masking** | Show partial values like `****1234` for permitted fields. | Can still identify individuals; never apply casually to secrets. |
| **Tokenization** | Replace values with random tokens backed by an isolated mapping vault. | Protect mapping store, control detokenization access, manage token lifecycle. |
| **HMAC pseudonymization** | Derive consistent pseudonyms using a secret key and input. | Requires key management/rotation; identical values remain linkable across events. |
| **Plain hashing** | Keyless one-way hash. | **Insecure** for emails/phone numbers with guessable domains; vulnerable to dictionary lookups. |

For example, with phone numbers, logging **`lookupOutcome=FOUND`** and `correlationId` often beats logging a masked phone number when diagnosing integration errors. When investigating a specific entity is required, store a controlled reference key and query the authorized source system.

### 5.3. Where Data Leaks Outside Logger Statements

Audit these integration surfaces:

- **HTTP request/response logging:** filters, interceptors, client wire logs, URL queries, headers, and bodies.
- **Spring `WebClient`/`RestClient`/Feign or Apache/Netty wire logging:** enabling `DEBUG`/`TRACE` can dump credentials and payloads.
- **JDBC/JPA SQL bind parameter logging:** SQL statements may look harmless while bind parameters carry personal data or secrets.
- **JMS/Kafka/Spring Integration adapters:** printing entire **`Message<?>`** objects, all headers, payloads, DLQ messages, or deserializer exceptions.
- **Stack traces / error bodies:** SDK or HTTP client exception messages can embed URLs, tokens, form fields, and sample payloads.
- **MDC, trace attributes, and baggage:** cross-service context exported to multiple collector sinks.
- **Cache debugging:** logging cache keys or serialized values can indirectly expose sensitive data.

**Masking at the dashboard UI is too late** if collectors, log files, container stdout, or storage already captured raw data. Enforce controls at event creation and before writing to sinks, while keeping collector-side scrubbing as defense in depth.

## 6. Structured Logging in Spring Boot

Structured logs allow querying by **`event`**, **`outcome`**, **`dependency`**, **`correlationId`**, and **`durationMs`** instead of parsing free-form text.

Java example using **SLF4J 2.x** fluent API and selected fields:

~~~java
private static final Logger log =
        LoggerFactory.getLogger(PaymentGatewayAdapter.class);

void recordDependencyResult(
        String operationRef,
        String outcome,
        long durationMs) {
    log.atInfo()
        .addKeyValue("event", "dependency_call_completed")
        .addKeyValue("dependency", "payment-provider")
        .addKeyValue("operationRef", operationRef)
        .addKeyValue("outcome", outcome)
        .addKeyValue("durationMs", durationMs)
        .log("Payment dependency call finished");
}
~~~

**`operationRef`** and **`outcome`** must be contract-validated/normalized values—never pass raw bodies or error messages containing sensitive data. Calling **`addKeyValue`** requires a compatible JSON encoder/layout to emit true JSON; it does not automatically ensure JSON formatting or PII scrubbing at the collector.

At the Spring Boot level, **Actuator/Micrometer** supplies metrics and observations for HTTP, JDBC, and integration components per configuration. **Micrometer Tracing** injects trace context into logs via MDC when configured. Still, **audit events are business records with their own retention rules**, never replaced by collector-sampled traces.

### 6.1. Correlation IDs Across HTTP and JMS

Correlation IDs connect logs for one task across multiple services:

~~~mermaid
sequenceDiagram
    participant H as HTTP API
    participant O as Order Service
    participant J as JMS broker
    participant C as Consumer
    H->>O: X-Correlation-ID / trace context
    O->>O: Log + commit audit/outbox
    O->>J: OrderConfirmed + correlationId
    J->>C: Deliver / possible redelivery
    C->>C: Log + process with businessOperationId
~~~

Client-supplied correlation IDs are **untrusted input**: validate length, allowed character set, and header count; if missing or invalid, mint a safe new ID. Never let strings with newlines, control characters, or unbounded length enter logs or MDC.

Concise MDC scoping pattern:

~~~java
String correlationId = validatedCorrelationIdOrGenerated();

try (var ignored =
        MDC.putCloseable("correlationId", correlationId)) {
    processMessage();
}
~~~

**`validatedCorrelationIdOrGenerated()`** and **`processMessage()`** are illustrative app methods, not Spring APIs. The key is clearing MDC in **`finally`/try-with-resources** when processing ends so pooled threads never carry a prior request's ID.

Across **`@Async`**, `ExecutorChannel`, Reactor, or listener threads, MDC does not automatically propagate in all setups. Use framework-supported **context propagation** or re-establish validated context at message boundaries. Over JMS/Kafka, forward correlation/business IDs in contracted headers and validate headers on the consumer before use.

### 6.2. Preventing Log Injection and Excessive Metric Cardinality

External strings can inject CR/LF, control characters, or giant payloads to forge log lines. Use escaping encoders, enforce length caps, validate IDs, and never interpolate untrusted input into free-text log templates.

For metrics, **never put `orderId`, email, `userId`, or `correlationId` into labels/tags**; every distinct value spawns a time series and explodes cardinality. Keep detailed IDs in access-controlled logs/audits/traces, and keep metric labels bounded such as **`dependency=payment-provider`**, **`operation=confirm`**, **`outcome=timeout`**.

## 7. Designing Retention: Keeping Data for the Right Duration and Places

**Retention** defines how long logs and audits are kept, when they move to archives, when they are purged, and what exceptions apply. Durations must derive from purpose, data classification, contracts, applicable laws, security, and real investigative needs.

No single retention period fits every data category or organization. Access logs, debug logs, security events, transaction audits, and dispute-evidence records often require very different lifetimes.

### 7.1. Illustrative Policy Matrix (Example Only)

| Data type | Purpose | Storage | Illustrative duration | End-of-life rule |
| --- | --- | --- | --- | --- |
| Debug/technical verbose logs | Short-term bug triage. | Fast-query log platform. | 7 days. | Delete via index lifecycle if no hold applies. |
| Standardized operational logs | Monitoring errors, latency, retries. | Fast-query log platform. | 30 days. | Purge indexed copies and related replicas per policy. |
| Security events | Investigating anomalous access. | Restricted, tamper-evident store. | 90 days. | Archive/delete per approved workflow. |
| Business audits | Proving state changes and reconciliation. | Dedicated append-only audit store + archive. | 365 days. | Delete or move to long-term archive per policy and legal hold. |
| Distributed traces | Flow and latency analysis. | Tracing backend. | 7 days. | Sample and expire per TTL; never sole audit source. |

**The figures 7/30/90/365 only illustrate the design exercise**—they are not mandatory durations or legal advice. Production policies require approval aligned with jurisdiction, industry, data types, evidentiary obligations, and data-subject rights.

### 7.2. Retention Must Cover Every Copy

An event can pass through:

~~~mermaid
flowchart LR
    A[Application / stdout] --> B[Node / container log]
    B --> C[Collector / buffer]
    C --> D[(Hot search index)]
    D --> E[(Cold archive)]
    C --> F[Alert / dashboard export]
    E --> G[Backup / replicated store]
~~~

Expiring an index TTL does not erase every copy. Account for **local files, log sidecars, collector buffers, dead-letter queues, hot indexes, archives, snapshots, backups, replicated clusters, exports, and ticket attachments**.

For stores that cannot delete individual events immediately (such as certain immutable archives or backups), policies must specify **periodic purge cycles**, restricted access while waiting, encryption key lifecycles, and how valid deletion requests are fulfilled. Never promise instant physical erasure from every copy if your architecture cannot deliver it.

### 7.3. Define When the Retention Clock Starts

Pick an explicit anchor timestamp:

- **`occurredAt`:** when the source generated the event.
- **`recordedAt`/`ingestedAt`:** when the store ingested the event.
- **`closedAt`/`resolvedAt`:** when a case or business workflow closed, if policies track case lifecycles.

If a relay redelivers an event days later, anchoring retention on **`ingestedAt`** diverges from **`occurredAt`**. Document the anchor in policy and enforce it consistently. Clocks across services can skew; never trust client-supplied timestamps to trigger deletion of sensitive records.

### 7.4. Legal Holds and Exceptions

When a valid evidence-preservation request applies, a **legal hold** suspends deletion for the defined scope. Record **`holdId`, reason, scope, approver, start/end times, and change history**. Only after the hold is lifted and retention expires should purge jobs remove affected data.

Do not retain every log forever "just in case of a dispute". Holds must have bounded scope, periodic review, and strict permission controls.

### 7.5. Retention Is Not Just YAML Configuration

Example application-defined keys:

~~~yaml
app:
  observability:
    retention:
      operational-days: 30
      security-days: 90
      audit-days: 365
~~~

These **`app.observability.retention.*`** keys are **illustrative application config**—Spring Boot does not read them to purge logs or archives. Enforcement must live in the real storage layer: index lifecycle policies, object-storage lifecycle rules, partition drop/purge jobs, or records-management systems.

Purging database audit rows must go through an authorized workflow accounting for holds, retention, and backups, and recording evidence of **which scopes were deleted**. Never give application service accounts unrestricted audit-delete privileges via unguarded cron jobs.

## 8. Security and Access Governance for Logs and Audits

Logs and audits hold sensitive data in their own right, not harmless operational exhaust. Enforce:

1. **Role-based access control:** operators view technical failures; security analysts view security events; auditors view scoped business audits; developers do not automatically read everything.
2. **Separation of write/read/delete:** apps are append-only writers, analysts are read-only, and lifecycle admins approve deletions under governance.
3. **Encryption in transit and at rest:** TLS between app/collector/backend, plus proper key management for archives and backups.
4. **Access auditing:** searches, bulk exports, retention edits, permission grants, hold releases, and deletions are themselves auditable events.
5. **Export controls:** masking or pseudonymization still applies to dashboards, alerts, tickets, email digests, and data exports.
6. **Log-source protection:** authenticate log producers, prevent event spoofing, rate-limit, and sanitize untrusted ingestion.

**Never treat passing a correlation ID or structured logging as identity authentication.** Audit `actorRef` values must come from verified identity mechanisms: trusted security contexts, authenticated service principals, or scheduled job identities—never blindly copied from client headers.

## 9. Connecting to HTTP, Databases, Caches, Brokers, and Spring Integration

### 9.1. HTTP Clients and Servers

At the HTTP layer, prefer logging **method, route template, status category, dependency name, `durationMs`, `retryCount`, and `correlationId`**. Never log raw URL query strings when they may hold emails, tokens, or IDs. Route templates like **`/orders/{id}`** suit metrics far better than raw URIs.

When calling a payment service:

- Assign a stable **`operationRef`** across retries for the same business request.
- Record request attempts and outcomes at distinct semantic levels: **`SENT`**, **`ACKNOWLEDGED`**, **`COMPLETED`**, **`UNKNOWN`** per contract.
- If a write times out after sending, never assume failure and immediately create a brand-new payment; use the idempotency key and partner status lookup if supported.
- Never put **`Authorization`**, cookies, request/response bodies, account numbers, or passwords in logs.

### 9.2. Databases and Transactions

SQL logs and business audits serve different needs. SQL traces help diagnose slow queries, yet fail to capture **actor**, change rationale, or workflow outcome.

For critical business mutations, emit audits when the local transaction commits. Whenever possible, insert audit records inside the **same transaction** as business state; across multiple databases or brokers, design outboxes/reconciliation around real boundaries.

Never allow full SQL bind parameter logging by default. An `UPDATE` statement's bind values can hold phone numbers, password hashes, access tokens, or sensitive documents.

### 9.3. Caches

Cache hits/misses, evictions, load failures, and TTLs are strong operational signals. Avoid logging full cached objects or cache keys containing emails, session tokens, or account numbers. When caches merely mirror authoritative records, audit mutations at the source of truth—never emit a business audit event on every cache hit.

When stale cache data causes wrong business decisions, rely on trace/correlation IDs and version/timestamp metadata to reconcile cache vs. source rather than logging raw objects on every lookup.

### 9.4. Message Brokers and Spring Integration Adapters

With **JMS/Kafka**, distinguish:

- **Broker `messageId`**, **`businessEventId`**, and **`correlationId`**.
- **`deliveryAttempt`**, **`redelivery`**, **`processingOutcome`**, and **`businessCommitOutcome`**.
- **DLQ/quarantine** is an error staging area for triage, not automatic proof of permanent business failure.
- **Outbox publish** and **downstream applied** are two separate milestones.

In Spring Integration, **channels, service activators, splitters, aggregators, resequencers, routers, and gateways** can switch threads or fan out child messages. Propagate correlation/group IDs, sequences, and `operationRef` per contract to link final outcomes back to origin events. Across asynchronous channels, never assume MDC propagates automatically across every thread.

Never log raw **`Message<?>`** at `DEBUG` just to inspect headers, because messages can carry tokens, personal payloads, or third-party fields. Emit a **sanitized message summary** containing event type, payload size, group ID, sequence, `retryCount`, and outcome where authorized.

## 10. Testing Data Masking and Audit Reliability

Log/audit testing must verify both correctness **and** absence of data leaks:

| Scenario | What to prove |
| --- | --- |
| Business operation commits cleanly | Audit event exists with accurate actor/resource/operation/outcome—no overwrites or omissions. |
| Database rolls back before commit | Zero fake **`COMMITTED`** audit; failed/attempt events follow a separate path with distinct semantics if required. |
| Audit `INSERT` fails in mandatory-audit tx | Business transaction rolls back per fail-closed policy; failure is observable. |
| Service crashes after DB commit before relay sends audit | Outbox preserves event; relay delivers upon recovery. |
| Relay sends successfully then crashes before marking sent | Collector receives retry and deduplicates by `auditEventId`; business evidence is not duplicated. |
| Consumer redelivers old JMS `eventId` | Business-commit audit is not duplicated when idempotency skips repeats; delivery attempts may still be logged operationally. |
| Request carries password, token, phone, nested payload | Zero secrets/raw PII appear in stdout, app logs, collector buffers, trace attributes, DLQs, or unauthorized audit details. |
| Exception and stack trace carry sensitive URL/query/payload | Logger/encoder/sanitizer blocks leakage. |
| Correlation ID contains newlines, control chars, or excessive length | Rejected/normalized without causing log injection or abnormal cardinality. |
| Async executor or consumer thread reused | No leaked `correlationId`/MDC from prior request; trace context connects when configured. |
| Retention expires without hold | Expired records are handled across hot index, archive, and replicas per policy. |
| Legal hold or investigation active | Held records are preserved from deletion; hold changes are audited. |
| Unauthorized user queries audits | Query/export denied; access attempt audited. |

### 10.1. How to Test Log Confidentiality

In tests, inject synthetic **canary secrets** (e.g., **`SECRET_TEST_MARKER_123`**), then trigger happy paths, error paths, retries, timeouts, and exceptions. Scan **every sink observable in the test environment**, not just controller responses:

~~~text
application log / stdout
structured log encoder output
collected events
trace attributes / baggage
audit details
DLQ / error payload
~~~

Assert the sensitive marker never appears in any unauthorized sink. Update tests whenever adding new HTTP clients, interceptors, tracing libraries, loggers, or schemas. Never put real secrets into test fixtures.

### 10.2. Retention Tests Must Cover Every Copy

Create events with deterministic timestamps and classifications, advancing time via a controlled `Clock` in component tests (without mutating OS clocks). Verify:

1. Unexpired records remain readable per permissions.
2. Expired records enter the intended lifecycle—and are not dropped prematurely.
3. Records under legal hold survive past normal expiration.
4. Archives, replicas, snapshots, and backups follow published deletion/access rules.
5. Lifecycle jobs emit audits of scope, record counts, and outcome without sensitive payloads.

Never let a test pass just because one table/index is clean while logs still linger in object storage or alerting systems.

## 11. Observing the Audit and Log Collection Pipeline Itself

Audit pipelines can also drop data when collectors go down, buffers fill, or configs break. Monitor:

| Indicator | Alerting focus |
| --- | --- |
| **`audit_created_total`** | Events created at source, broken down by finite event type/outcome. |
| **`audit_persisted_total`** | Events committed to durable storage. |
| **`audit_exported_total`** | Events reaching transit/collector per measurable semantics. |
| **`audit_ingested_total`** | Events confirmed stored by target warehouse. |
| **`audit_outbox_pending / oldest_age`** | Unsent audit records and age of oldest pending record. |
| **`audit_ingest_errors / retries`** | Transport, serialization, schema validation, or quota errors. |
| **`collector_dropped_events`** | Events dropped due to config, failures, backpressure, or sampling. |
| **`retention_deletion_lag`** | Delay between expiration and policy-driven purge completion. |
| **`unauthorized_audit_reads / exports`** | Suspicious read or export activity. |

Never assert **`audit_created_total = audit_ingested_total`** by naive subtraction when the two counters have different scopes, resets, or observation windows. For strict completeness proofs, reconcile **`auditEventId` sets** by watermark/partition/time window alongside pending/failed lists.

Critical audits deserve their own SLOs, such as max age of unshipped records or time to detect pipeline failure. Concrete targets must reflect business risk and architecture rather than treating example numbers as universal standards.

## 12. Runbook When Audits Are Missing or Sensitive Data Leaks into Logs

### Missing Audit Events

1. **Scope:** gather event type, resource, tenant, `operationRef`, and time window; identify the authoritative business state source.
2. **Inspect evidence:** check transaction commits, local audit tables, outboxes, brokers, collector errors, DLQs, and centralized stores by `auditEventId`.
3. **Classify the gap:** never created, created then rolled back, committed yet unsent, sent yet unindexed, or purged per lifecycle.
4. **Controlled recovery:** replay outboxes, process DLQs, rebuild indexes from durable stores, or append correction events citing verifiable evidence. Never fabricate historical timestamps pretending events were logged originally.
5. **Reconcile and prevent:** verify `auditEventId` sets match from source to destination, close the failure window, and add alerts/tests.

### Sensitive Data Detected in Logs

1. **Stop further emission** at the log source or logger/encoder config; for exposed secrets, evaluate revocation/rotation per impact severity.
2. **Determine blast radius:** app files, stdout, collector buffers, hot/cold indexes, traces, alerts, exports, backups, and who accessed them.
3. **Restrict access and preserve evidence** per incident-response procedures; avoid ad-hoc deletions that destroy forensic evidence.
4. **Remediate data per policy** and legal obligations, including revoking exports and purging/locking access compatible with legal holds.
5. **Add regression tests** for allowlists, masking, exception paths, and debug/wire logging so leaks never recur.

## 13. Misconceptions to Avoid

**"Turning on full `DEBUG` logging makes debugging easier."** `DEBUG`/wire logging can capture payloads, tokens, and personal data across clients and adapters. Increase verbosity selectively, time-boxed, on targeted components with strict data controls.

**"A `traceId` is good enough as an audit trail."** Traces undergo sampling, expire quickly, and omit complete business outcomes. Audits need dedicated schemas, transactions, and governance.

**"Writing an audit before calling the repository proves the operation succeeded."** The transaction may roll back. Bind outcomes accurately to commit boundaries.

**"If the collector received an event once, it won't arrive twice."** Relays/outboxes retry after timeouts or crashes. Use stable `auditEventId`s to deduplicate and separate delivery attempts.

**"Masking in the dashboard makes data safe."** Raw copies still sit in stdout, buffers, archives, snapshots, and exports. Eliminate sensitive fields at the source.

**"Hashing emails achieves full anonymization."** Emails occupy predictable spaces; unsalted hashes succumb to lookup attacks. Even HMAC/tokenization requires key management and strict linkability controls.

**"`retention-days` in YAML deletes every copy automatically."** False. Configure and verify lifecycle deletion across every real store, including archives, replicas, and backups.

**"Keeping logs as long as possible is always better."** Over-retention expands breach exposure and cost and may violate data-minimization obligations. Define and review retention against concrete requirements.

**"Append-only audits don't need a deletion plan."** Append-only protects against arbitrary edits; retention and legal holds still require governed purge mechanisms, even on immutable storage.

## 14. Pre-Production Checklist

- [ ] Clearly separated operational logs, security events, business audits, metrics, and traces.
- [ ] Versioned audit schema with `auditEventId`, actor, resource, outcome, timestamps, source, and correlation/business IDs.
- [ ] **`REQUESTED` / `ACCEPTED` / `COMMITTED` / `FAILED` / `REJECTED`** semantics never misrepresent business success.
- [ ] Audits for critical DB mutations commit consistently with business data or use durable outboxes and reconciliation.
- [ ] Audit retries and relays use stable IDs; collectors deduplicate with backlog/DLQ monitoring and alerts.
- [ ] All logs, traces, and audit details enforce allowlists—keeping secrets, passwords, tokens, and unnecessary personal payloads out of sinks.
- [ ] HTTP/JDBC/JMS debug and exception paths tested against sensitive-data leaks.
- [ ] External `correlationId` values validated; MDC cleaned at end of execution; async context propagation verified.
- [ ] Actors come from verified identities; audit reads follow role/tenant RBAC, with reads and exports audited.
- [ ] Retention policy defined per data type, anchor timestamp, storage tier, archive, legal hold, and deletion approval.
- [ ] Lifecycle verified across stdout, collectors, hot/cold indexes, exports, snapshots, and backups per real architecture.
- [ ] Tests cover crash between commit and relay, duplicates, secret leaks, access controls, and expiration/holds.
- [ ] Runbooks exist for missing audits, collector outages, count mismatches, and sensitive data discovered in logs.

## 15. Conclusion

**Audit logs are business evidence with their own contracts, transactions, and lifecycles; operational logs and traces offer technical explanations without replacing that evidence.** In Spring Boot, define what events qualify for auditing, trust only verified actor identities, link HTTP/JMS/database hops with stable identifiers, and protect audit transport across retries and crashes.

To observe integration flows without leaking secrets, **apply field allowlists, minimize data at the source, enforce access controls, and manage retention across every copy**. Finally, test both audit completeness and leak prevention while monitoring collection pipelines to catch gaps that isolated metrics or dashboards never show.
