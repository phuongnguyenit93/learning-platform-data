# Hiding Sensitive Data in Logs, Query Parameters, and Monitoring Tools

## 1. Why Can a Working System Still Leak Data?

Neo4j stores information as a **property graph**: nodes, relationships, and properties. A single Cypher query can traverse multiple links and return customer profiles, employee details, accounts, medical records, transactions, or internal corporate structures.

For example, a Java application looks up a customer by email:

~~~cypher
MATCH (c:Customer {email: $email})
RETURN c.customerId AS customerId,
       c.status AS status;
~~~

Functionally, this query may be completely accurate. Yet if the application writes a log entry like the one below, it has copied the customer's email into the **logging pipeline**, which may have different user access, retention windows, and export workflows than the database:

~~~text
WARN  Neo4j query failed
query=MATCH (c:Customer {email: $email}) RETURN c
parameters={email: "customer.real@example.invalid"}
error=...
~~~

Even when logs are stored internally, consequences can include:

- Staff who lack privileges to read `Customer` nodes can still read emails via the log dashboard.
- Logs get forwarded to third parties or broader analytics environments.
- Log copies persist longer than the source data retention window.
- Alert notifications containing sensitive log snippets get sent to email, chat, or ticketing tools.
- Incident troubleshooting queries get pasted into screenshots or documentation.
- Deleting or anonymizing records in Neo4j does not automatically purge copies already sitting in logs.

**The goal of this lesson** is protecting sensitive data across the entire observability pipeline: **Cypher → Neo4j server → Java Driver/Spring Data Neo4j → logs/traces/metrics/APM → dashboards, alerts, and archives**.

> **Core principle:** Query parameterization separates data from Cypher syntax, but it **does not mean** parameter values are automatically masked across every log, trace, or monitoring tool. Data minimization, filtering, and access controls must be enforced at each layer.

## 2. Identifying Which Data Must Be Protected

Not every graph property carries the same sensitivity. Before configuring logging, classify fields by risk.

| Data Category | Graph Examples | Risk If Exposed in Logs |
|---|---|---|
| **Personally Identifiable Information (PII)** | `Person.email`, `phone`, `address`, names combined with context | Personal identification, spam, phishing |
| **Credentials / secrets** | API keys, OAuth tokens, passwords, connection secrets | Unauthorized access; requires emergency response |
| **Financial data** | Account numbers, payment details, detailed transactions | Transaction leakage, fraud |
| **Health / legal data** | Diagnoses, sensitive records, case relationships | Severe privacy impact |
| **Internal business data** | Org structure, topology, plans, internal system IDs | Corporate intelligence leakage |
| **Linkable identifiers** | `customerId`, `userId`, `orderId` | Can become personal data when joined with other datasets |
| **Low-sensitivity operational data** | Approved operation names, status, latency, aggregate row counts | Generally better suited for logs and metrics |

A `customerId` that looks like a technical code is still identifying data if an internal table maps it to a real person. Never automatically assume every non-email value is "harmless".

### 2.1. Classification Questions to Answer

- Can the data **directly or indirectly identify** an individual?
- Is the data used to **authenticate, sign requests, or grant access**?
- If a log reader lacks permission to read the corresponding node, should they be allowed to see this value?
- Is this data actually needed in logs to diagnose errors, or do an operation name and timestamp suffice?
- Are there distinct retention or deletion rules per data category?

Classification must produce an **explicit policy**: which fields are strictly forbidden from logs, which may be pseudonymized, and which are safe to log after verification.

### 2.2. Graphs Carry Exposure Risk Through Connections

Individual properties are not the only sensitive items. A path like:

~~~text
(:Employee)-[:WORKS_ON]->(:ConfidentialProject)
(:Customer)-[:HAS_CASE]->(:SensitiveCase)
(:Person)-[:MEMBER_OF]->(:PrivateGroup)
~~~

can leak sensitive facts simply by logging **which nodes and relationships appear together**.

Consequently, logging "dump full graph result" or printing `Path` lists can remain sensitive even after stripping emails and phone numbers. Restrict both **graph link structures and endpoint identities** emitted to monitoring backends.

## 3. Map of Data Leakage Pathways

A request traverses multiple layers, each with its own recording mechanisms:

~~~mermaid
flowchart TD
  A["HTTP/API request<br/>PII, token, request body"] --> B["Java Service"]
  B --> C["Cypher query + parameters"]
  C --> D["Neo4j Server"]
  D --> E["Result/Record/Graph values"]
  E --> B
  B --> F["Application log"]
  B --> G["APM / distributed tracing"]
  B --> H["Metrics"]
  D --> I["Neo4j query log / diagnostics"]
  D --> J["Administration / query inspection"]
  F --> K["Log platform / alerts"]
  G --> K
  H --> K
  I --> K
~~~

| Observation Surface | Data That May Appear | Priority Control |
|---|---|---|
| **Query text** | Cypher with literals, property names, labels, paths | Parameterize, avoid secrets in literals, restrict sharing |
| **Query parameters** | Emails, IDs, tokens, nested JSON/lists/maps | Disable unneeded parameter logging, allowlist |
| **Neo4j query log** | Query text, timing, and sometimes parameters per config | Reduce verbosity, configure version-supported redaction/obfuscation |
| **Server debug/diagnostic logs** | System state, exceptions, connection details | Access control, TTL, never enable casually |
| **Java Driver / framework logs** | Exceptions, queries, parameter maps, responses | Never log raw objects, bound log levels, sanitize |
| **APM / spans** | `db.statement` or query attributes, errors, baggage | Allowlist span attributes, disable parameter capture |
| **Metrics** | Labels/URLs/query text/IDs if mis-instrumented | Finite labels, aggregated counts/timings |
| **Monitoring UI / admin query lists** | Running queries, text, session stats | Least privilege and audit viewing actions |
| **Alerts / tickets / exports** | Log excerpts embedded into notifications | Alert with safe codes, control destination access |
| **Backups / heap dumps / support bundles** | Log contents, memory, configs, sometimes raw data | Restricted storage, encryption, retention, scrub before sharing |

Securing one point does not automatically secure the whole path. Disabling parameter logging in Neo4j **does not stop** a Spring controller from logging request bodies or an APM agent from capturing attributes containing emails.

## 4. Cypher Parameterization: Necessary but Not Sufficient

### 4.1. Avoid Concatenating User Input into Cypher

**Do not do this:**

~~~java
String cypher =
    "MATCH (c:Customer {email: '" + email + "'}) RETURN c";
~~~

String concatenation creates **Cypher injection** risk and embeds the email straight into query text, which can then be logged, shown in diagnostic tools, or included in exceptions.

**Do this instead:**

~~~cypher
MATCH (c:Customer {email: $email})
RETURN c.customerId AS customerId,
       c.status AS status;
~~~

and pass parameters from Java:

~~~java
Map<String, Object> parameters = Map.of("email", email);
tx.run(cypher, parameters);
~~~

Parameterization helps because it:

- Separates Cypher syntax from untrusted data.
- Mitigates injection risk in parameter-supported positions.
- Avoids spawning distinct query text variants per literal value.
- Allows separate logging policies for query text vs. parameters.

However, the `parameters` map **still holds the real email**. If a logger prints the entire map, data leaks anyway:

~~~java
// Wrong: broadcasts email values into logs.
logger.info("Cypher params = " + parameters);
~~~

**Never confuse "using parameters" with "parameters are encrypted or hidden everywhere".** The Driver must transmit real values to Neo4j so the query can run; protection means preventing those values from leaking into unnecessary observability channels.

### 4.2. Never Pass Secrets into Queries Even via Parameters

Poorly designed apps sometimes pass API keys, tokens, or passwords into a query merely for comparison or diagnostics. Even when parameterized, secrets pass through the database and risk appearing in tooling if configurations slip.

Send only data **genuinely needed for the business operation**. For user authentication, rely on dedicated identity/auth systems rather than storing or comparing raw passwords in Cypher.

### 4.3. Do Not Rely on Parameter Names for Safety Decisions

~~~cypher
MATCH (u:User)
WHERE u.email = $value
RETURN u.userId;
~~~

Naming a parameter `$value` does not make its contents less sensitive. Conversely, naming it `$email` hints at meaning, yet no simple parameter-name rule catches every nested field.

Example complex payload:

~~~json
{
  "profile": {
    "email": "sample.user@example.invalid",
    "phone": "+84-000-000-000"
  },
  "metadata": {
    "source": "mobile"
  }
}
~~~

If a logger dumps all of `profile` or `metadata` without filtering, any newly added future field will leak automatically. Policies should **explicitly allowlist safe fields**, rather than logging everything not on a denylist.

### 4.4. Dynamic Cypher Still Requires Structural Controls

When an app dynamically selects labels, relationship types, property names, or sort fields, parameterizing **values** alone does not automatically protect structural Cypher positions across all versions.

Prefer an **allowlist of approved structural identifiers**; never interpolate raw label/type names or `ORDER BY` clauses from requests. Beyond injection, dynamic query text risks leaking sensitive data mistakenly placed into schema names.

## 5. Neo4j Query Log: Separating Query Text from Parameter Values

Neo4j provides query logging mechanisms, though **setting names, modes, defaults, and obfuscation levels** vary by version and deployment configuration. Examples in this section target the **Neo4j 5.x** family—verify against your live configuration before applying.

### 5.1. What to Evaluate Before Enabling Query Logging

Query logs are valuable for:

- Tracing slow queries and timeouts.
- Analyzing durations, execution stats, and query families.
- Diagnosing bottlenecks across Cypher, indexes, and traversals.
- Spotting abnormal operational queries.

Yet they are also a replication path for:

- Query text containing **sensitive literals**.
- Parameter maps if parameter logging is enabled.
- Transaction/session metadata linking activity to users or tenants.
- Internal query patterns and label/relationship structures.

Never enable the most verbose mode in production simply "to have enough debug info". Define **purpose, access control, retention, and minimum required fields** first.

### 5.2. Example Configuration Following Data Minimization

In a Neo4j 5.x environment supporting these settings, a starting point can be:

~~~properties
# neo4j.conf — example to verify against your running version.
db.logs.query.enabled=INFO
db.logs.query.parameter_logging_enabled=false
~~~

Intended effect:

- Enable query logging at the version-supported `INFO` level.
- **Prevent writing parameter values** to the query log via the corresponding setting.

**This does not guarantee logs are completely harmless.** If Cypher text itself embeds sensitive literals, or another log/diagnostic channel records inputs, these settings will not scrub them.

In high-security environments, consider logging only slow queries or the minimal level supported by your Neo4j release; exact choices depend on operational and compliance needs. Some versions offer **literal obfuscation** and finer parameter controls—verify exact options rather than assuming they exist in every installation.

### 5.3. Inspect Effective Settings Instead of Guessing from Files

When authorized on a compatible Neo4j version:

~~~cypher
SHOW SETTINGS
YIELD name, value
WHERE name STARTS WITH 'db.logs.query.'
RETURN name, value
ORDER BY name;
~~~

This verifies which query logging settings actually exist and their active values. If you lack `SHOW SETTINGS` privileges, ask an administrator to check through standard channels.

Items to verify:

1. `db.logs.query.enabled` is set to the intended mode.
2. Parameter logging is **disabled or restricted** per policy.
3. Literal obfuscation (if supported) is enabled and tested.
4. No other log stream is capturing queries/parameters through a side channel.
5. Log files and log ingestion platforms enforce RBAC, retention, and export controls.

### 5.4. Obfuscation Does Not Replace Data Classification

Even when Neo4j masks certain secrets in specific syntactic constructs, never assume it automatically masks:

- Emails or phone numbers concatenated into arbitrary literals.
- Nested objects/lists inside parameters.
- Data embedded in custom expressions or user-defined procedures.
- Fields captured independently by an APM agent outside the query log.
- Data logged by the application before calling Neo4j.

**Practical verification:** send fake, uniquely tagged test values, then search authorized logs and traces. If the marker appears anywhere, fix the emitting component before going to production.

## 6. Query Logs and Data Visible to Administrators

Beyond query log files, administrative tools can expose active queries, transactions, sessions, or settings depending on granted roles.

Example admin command:

~~~cypher
SHOW TRANSACTIONS;
~~~

This supports operations; depending on version and privileges, output/UI views may expose transaction metadata or running query text helpful for triage. **Never paste raw output from an admin session** into tickets or chat without reviewing for sensitive data first.

### 6.1. Least Privilege Principle

- Engineers who only need **CPU, memory, latency, and transaction totals** do not inherently need access to raw queries or parameters.
- Incident responders can receive time-bounded, audited access when needed.
- Metrics collection agents do not automatically require full Neo4j admin roles.
- Authorization inside Neo4j and authorization inside the **log collection/viewing platform** must be reviewed separately.

An operator barred from reading sensitive graph properties must not have a backdoor to read that same data through the logging backend.

### 6.2. Handling EXPLAIN and PROFILE with Control

~~~cypher
EXPLAIN
MATCH (c:Customer {email: $email})
RETURN c.customerId;
~~~

`EXPLAIN` displays the query plan without executing the Cypher body. Even so, **query text and plan details** should still be reviewed before sharing externally.

`PROFILE` executes the query and collects runtime stats. For `CREATE`, `SET`, or `DELETE`, `PROFILE` also **performs real data writes**. Never run `PROFILE` on production write queries merely to capture figures for support docs.

When debugging, prefer **synthetic parameters and safe dataset copies**, rather than taking screenshots containing real customer emails.

## 7. Java Driver: Placing Logging at Controlled Boundaries

The Java Driver manages `Driver`, `Session`, transactions, and `Result`/`Record` objects. If a logger accidentally calls `toString()` on a parameter map, record, or exception, business data can spill into logs.

### 7.1. Anti-Pattern Logging to Avoid

~~~java
// Do not use on requests carrying sensitive data.
logger.info("Running query: " + cypher + " params: " + parameters);

// May print sensitive node/relationship properties from results.
logger.info("Result: " + record);

// Error messages may contain details unfit for disclosure.
logger.warning("Neo4j failed: " + exception.getMessage());
~~~

The issue is not `INFO` vs. `WARN`; it is **exporting raw values outside the database boundary**. Switching `INFO` to `DEBUG` is not a safe policy either if `DEBUG` can be toggled during troubleshooting.

### 7.2. Safer Logging Pattern: Operation, Outcome, and Duration

A service only needs to log that `customer.lookup` succeeded/not_found/failed along with elapsed time—**never email, customerId, or parameter maps**.

~~~java
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.TimeUnit;
import java.util.logging.Level;
import java.util.logging.Logger;

import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.exceptions.Neo4jException;

public final class CustomerLookupService {
    private static final Logger LOG =
        Logger.getLogger(CustomerLookupService.class.getName());

    public record CustomerSummary(
        String customerId,
        String status
    ) {}

    private final Driver driver;

    public CustomerLookupService(Driver driver) {
        this.driver = driver;
    }

    public Optional<CustomerSummary> findByEmail(String email) {
        if (email == null || email.isBlank()) {
            throw new IllegalArgumentException("email is required");
        }

        String cypher = """
            MATCH (c:Customer {email: $email})
            RETURN c.customerId AS customerId,
                   c.status AS status
            LIMIT 1
            """;

        long started = System.nanoTime();

        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {

            Optional<CustomerSummary> found = session.executeRead(tx -> {
                var result = tx.run(cypher, Map.of("email", email));
                if (!result.hasNext()) {
                    return Optional.<CustomerSummary>empty();
                }

                var row = result.next();
                return Optional.of(new CustomerSummary(
                    row.get("customerId").asString(),
                    row.get("status").asString()
                ));
            });

            long ms = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - started
            );
            LOG.log(Level.INFO,
                "operation=customer.lookup outcome={0} durationMs={1}",
                new Object[] {
                    found.isPresent() ? "found" : "not_found",
                    ms
                }
            );
            return found;

        } catch (Neo4jException ex) {
            long ms = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - started
            );
            LOG.log(Level.WARNING,
                "operation=customer.lookup outcome=failed durationMs={0}",
                ms
            );
            throw ex;
        }
    }
}
~~~

Key design choices in this example:

- Uses a `parameter` to pass the email into Cypher.
- **Never** logs the email value, parameter map, record, or `exception.getMessage()`.
- Timing and outcome metadata are **derived from application flow**, not from objects carrying PII.
- `executeRead` is a managed read transaction; the driver may retry the callback. The "request completed" log fires **after the callback**, avoiding counting each retry attempt as a final outcome.
- The DTO holding `customerId` is returned in memory for business use, yet **never passed directly to the logger**.
- `Driver` is reused; `Session` is short-lived.

**Scope of example:** production code must also handle null properties, target database config, authentication setup, and other exception types per application contract. Additionally, the rethrown exception may be caught and logged by an HTTP/telemetry layer; that layer needs its own sanitization policy too.

### 7.3. Never Pass Uncontrolled Raw Throwables to Loggers

The following can cause the logger to dump raw messages and stack traces:

~~~java
// Review security policy before using.
logger.log(Level.SEVERE, "Neo4j request failed", exception);
~~~

Stack traces help during development, yet error messages, suppressed exceptions, cause chains, or echoed inputs embedded in exceptions vary by library and scenario. On PII-bearing flows, error handlers must classify what is safe to attach.

One strategy is logging **allowlisted error codes and operation names**, while routing richer diagnostics to a tightly restricted system when truly required. Never push raw exception messages into metric labels or public API responses.

### 7.4. Controlling Driver-Level Logging

Enabling `DEBUG`/`TRACE` on Java Driver namespaces can emit extra protocol, connection, and query details depending on version and config. Never assume every version logs—or omits—the exact same fields.

Safety rules:

1. Keep normal log levels at tested defaults.
2. Enable `DEBUG`/`TRACE` only under approved time limits and narrow scope.
3. Verify **what actually gets emitted** using synthetic markers before enabling in production.
4. Never turn on "wire dumps" or raw traffic logging that captures payloads without strict necessity and protection.
5. After troubleshooting, revert verbose modes and manage generated logs per retention/incident policy.

If a framework logger intercepts every `tx.run(...)` call, safe Neo4j server settings **cannot block** that logger because it runs inside the application process.

## 8. Spring Data Neo4j: Query Logging Can Surface at Multiple Layers

In Spring Boot / Spring Data Neo4j, query execution passes through:

~~~text
HTTP controller
    |
Application service
    |
Repository / Neo4jClient
    |
Neo4j Java Driver
    |
Neo4j server
~~~

Each layer may introduce:

- HTTP request/response logging via filters/interceptors.
- Controller or service argument logging via annotations/AOP.
- Repository or `Neo4jClient` query logging.
- Driver and exception logging.
- Auto-instrumented APM/tracing.
- Log shippers forwarding to central backends.

### 8.1. Never Log All Method Arguments Blindly

An AOP interceptor configured to "log all arguments of every service method" easily prints emails, tokens, account numbers, JSON maps, or graph objects. Calling `findByEmail(email)` can leak arguments even when the service itself never logs them.

**Enforce an allowlist** covering operation names, coarse outcomes, durations, and system-generated correlation IDs. If debugging a specific field is required, follow an approval process with type-safe redaction.

### 8.2. Test Framework Logging Configurations Explicitly

Spring Boot allows tuning log levels for driver and Spring Data packages. However, **logger names and emitted details vary by framework version**. Never treat an arbitrary `logging.level...=INFO` line as proof that parameters are hidden.

Test with fake canary markers and inspect output from:

- Application logs.
- Repository/query logs.
- Driver logs.
- HTTP filter logs.
- Exception handlers.
- APM auto-instrumentation.

Never stop after verifying only that the Neo4j server log disabled parameters.

### 8.3. Entities and DTOs Can Leak Data Too

If a Java entity's auto-generated `toString()` includes `email`, `phone`, or relationship collections, logging the entity can expose an entire subgraph.

When using Lombok or Java records, watch generated methods and any direct or implicit `toString()` calls. A DTO designed for an API response is not automatically safe to write into logs.

## 9. Tracing / APM: Keep Parameters Out of Span Attributes

Distributed tracing is invaluable for locating slow requests, for example:

~~~text
HTTP POST /orders
    |
    +-- validate request
    |
    +-- Neo4j transaction
            |
            +-- MATCH Customer
            +-- CREATE Order
~~~

Spans can record operation names, timings, statuses, and errors. Yet if spans capture **full Cypher statements, parameter maps, URL query strings, or request bodies**, tracing becomes a leak channel.

### 9.1. Explicitly Allowlist Span Attributes

Example safer attribute set (illustrative names, not tied to a specific APM vendor schema):

~~~json
{
  "operation": "order.create",
  "component": "neo4j",
  "db.operation": "WRITE",
  "db.name": "commerce",
  "result": "success",
  "duration_ms": 24
}
~~~

Never include fields like these as default attributes:

~~~json
{
  "customer.email": "person@example.invalid",
  "cypher.parameters": {
    "email": "person@example.invalid",
    "phone": "+84-000-000-000"
  },
  "auth.token": "SECRET-CANARY-DO-NOT-LOG"
}
~~~

The second JSON block is an **anti-example**, never a configuration to deploy. Use clearly recognizable dummy values when testing log/tracing pipelines.

### 9.2. High-Variance Span Names Cause Two Problems

Never name a span:

~~~text
lookup-customer-person@example.invalid
~~~

It leaks an email address while causing span names to grow unboundedly with user data. Instead, use:

~~~text
customer.lookup
~~~

Keep status tags to small finite sets such as `read`, `write`, `success`, `error`, and approved operation names.

### 9.3. Baggage and Error Events

Distributed tracing baggage **propagates across multiple services**. Never put emails, session tokens, or secrets into baggage unless explicitly reviewed and designed for it; even if the final endpoint doesn't log baggage, an intermediate service might.

Some APM SDKs automatically attach exception messages and stack traces to span error events. Audit exception capture settings, attribute scrubbers, and downstream collectors. A dashboard-only redaction rule is **not enough** once raw spans have already been transmitted and stored.

## 10. Metrics: Safer in Aggregate, Yet Labels Can Leak PII

Neo4j metrics should focus on:

- Query/transaction counts.
- Execution durations and pool wait times.
- Errors, timeouts, and retries.
- CPU, heap, page cache, and I/O.
- Connection counts and read/write throughput.
- Response sizes or aggregate row counts.

Labels must come from **small, stable sets**, for example:

~~~text
neo4j_requests_total{operation="customer.lookup",outcome="success"}
neo4j_request_duration_seconds{operation="order.create"}
~~~

**Avoid:**

~~~text
neo4j_requests_total{email="person@example.invalid"}
neo4j_query_duration_seconds{customerId="C-123456"}
neo4j_requests_total{cypher="MATCH ... email literal ..."}
~~~

Beyond leaking data, `email` or `customerId` labels have **massive cardinality**, exploding time-series counts, storage costs, and monitoring system overload risk.

### 10.1. Keep User Identifiers Out of Metrics

Example metric design table:

| Metric | Labels to Use | Labels to Avoid |
|---|---|---|
| Query latency | operation, outcome | email, token, raw query text |
| Transaction retries | operation, error category | request body, raw exception |
| Pool wait | service, approved pool name | userId, sessionId |
| Neo4j error count | allowlisted error group | unscrubbed exception message |
| Graph import throughput | job type, outcome | CSV rows, sensitive keys |
| Cache hit/miss | cache type, service | customer/tenant ID if unneeded and unapproved |

If per-tenant breakdowns are required, weigh tenant count, sensitivity of tenant codes, data isolation rules, and cardinality budgets. Never assume tenant IDs are automatically safe in metrics.

## 11. Using Correlation IDs Without Printing Customer Identities

When tracing a request across Java services and Neo4j, engineers need to link logs belonging to **the same execution**. Rather than logging a customer's email, generate a **random correlation ID** per request and use it across logs and traces.

~~~text
requestId=8d62f6f7-...  operation=customer.lookup  outcome=success
requestId=8d62f6f7-...  component=neo4j        durationMs=24
~~~

Notes:

- Correlation IDs should be generated or validated by trusted systems; never blindly trust arbitrary/long client-supplied `X-Request-ID` strings.
- Never encode emails or phone numbers inside IDs like `customer-email-2026...`.
- Never treat a correlation ID as sole proof of caller identity.
- If requests must be traced back to business subjects, store the mapping in an appropriately access-controlled system with explicit retention.

Even if a request ID is not direct PII, it can still link user behavior across systems—so apply sensible retention limits to it as well.

## 12. Masking, Redaction, and Pseudonymization

These three techniques are often grouped as "data hiding", yet behave very differently.

| Technique | Example | Reversible / Identifiable? | When to Use |
|---|---|---|---|
| **Masking** | `a***@example.invalid` | May reveal partial identity | Support UIs when partial visibility is genuinely required |
| **Redaction** | `[REDACTED]` | Cannot recover original value from redacted log | Logs and alerts that do not need original values |
| **Pseudonymization** | HMAC yielding a stable surrogate ID | Linkable/reversible with key or auxiliary data | Correlating events for the same entity without storing raw IDs |
| **Aggregation** | `count=125` | Generally reduces identifiability | Operational metrics and statistics |

**Pseudonymization does not equal true anonymization.** A stable surrogate ID can still link actions together and remain personal data depending on context.

### 12.1. Why Not Hash Emails Directly with SHA-256?

Emails live in a guessable domain vulnerable to dictionary attacks. If logs store `SHA256(email)`, anyone holding a candidate email list can hash each address and match them.

When a stable surrogate is truly needed to group logs per subject, consider **HMAC-SHA-256 with a securely managed secret key**. Without the key, bulk guessing becomes substantially harder. Still, an HMAC token remains a **pseudonym** requiring:

- Key management/rotation and minimal key-read access.
- Consistent input canonicalization before computing HMAC.
- A policy addressing surrogate changes upon key rotation.
- Never logging the HMAC key itself.
- Legal/privacy compliance review within your organization.

If grouping per user isn't needed, **omitting the ID entirely** is simpler and safer.

### 12.2. Allowlist-Based Logging Instead of Regex-Matching Every PII Pattern

**Weak approach:** log the entire request map and regex-replace strings matching emails with `***`. This easily misses:

- Phone numbers, street addresses, names, and tokens.
- Unexpected email formats.
- Deeply nested JSON, URL-encoded values, and query parameters.
- Sensitive relationships and paths.
- New fields introduced in later API versions.

**Stronger approach:** construct log payloads solely from **explicitly approved fields**:

~~~json
{
  "operation": "customer.lookup",
  "outcome": "not_found",
  "durationMs": 18,
  "retryCount": 0
}
~~~

You can then add a **collector-side sanitizer/redactor** as defense-in-depth—never as an excuse to emit raw sensitive data at the source.

## 13. Audit Logs and Access Logs Differ from Detailed Query Logs

Some systems must audit "who performed what action" for security investigations or compliance. Auditing **differs** from query logging meant for performance tuning.

An audit event may require:

- Actor or service identity per approved policy.
- Business action code such as `order.cancel`.
- Timestamp, outcome, and correlation ID.
- Affected target as a protected identifier when strictly necessary.
- Administrative/privilege change trails within regulatory scope.

This **does not require** dumping entire parameter maps, query text with literals, or graph payloads.

### 13.1. Separating Access to Audit Logs vs. Query Logs

- Performance engineers may need **latency, operators, and error categories**, not personal data.
- Security investigators may need actor/action audit trails under separate authorization.
- Customer support may need partially masked UI views, not raw log access.
- Log collection agents need write/export permissions scoped narrowly, not broad Neo4j administrative privileges.

When an investigation genuinely requires inspecting detailed data, use **audited, controlled access** rather than enabling parameter logging across all traffic.

### 13.2. Distinguishing Operational Service Identity from End-User Identity

A single Neo4j service account like `app_service` may act on behalf of thousands of users. Server logs seeing only the service account **do not prove** which end user invoked the API.

When end-user auditing is required, the application service must emit dedicated audit events under a formal contract with privacy controls and verified actor identity. Never stuff end-user emails into query comments or transaction names as an unsafe shortcut.

## 14. Retention and Where Data Gets Replicated

Don't just ask "is the log leaking?"—also ask **where logs travel, how long they stay, and who can export them**.

~~~text
Java/Neo4j logs
      |
      v
Collector/Agent
      |
      +--> Central log storage
      +--> Alert notification
      +--> Ticket/incident attachment
      +--> Backup/archive
      +--> External observability vendor
~~~

A sensitive value can survive across many copies. Deleting data from Neo4j **does not automatically purge** copies sitting in monitoring platforms.

### 14.1. Log Data Governance Rules

1. Collect only fields genuinely needed for operations.
2. Encrypt log collector connections and storage at rest where appropriate.
3. Enforce RBAC for reading, querying, and exporting logs, and lock down machine accounts.
4. Define retention, archival, and deletion schedules per organizational/legal requirements.
5. Control exactly where alerts and log attachments may be sent.
6. Never leave debug bundles or raw logs in public storage buckets.
7. Restrict bulk downloads and audit log-access history.
8. Include logs and replicas in data-breach incident response plans.

### 14.2. Responding When PII or Secrets Are Found in Logs

If a real token or password accidentally hits logs, **merely patching code to stop future logging is not enough**. Trigger an incident response:

- Halt further emission of sensitive data immediately.
- Scope the affected time window and every downstream system that received copies.
- Rotate/revoke any potentially exposed secrets.
- Restrict unauthorized access and purge/handle copies per policy.
- Check alerts, tickets, exports, and backups containing copies.
- Document preventive controls and add regression tests.

For PII leaks, evaluate notification duties and follow applicable privacy/data policies; avoid sharing sensitive log excerpts further during investigation.

## 15. Debugging Neo4j Without Real Values

Engineers can diagnose slow queries without printing real customer emails or product payloads into logs.

### 15.1. Use Stable Operation Names

Name operations at the application layer:

~~~text
operation=customer.lookup
operation=order.create
operation=graph.followers.list
operation=product.recommend
~~~

This supports latency, error, retry, and throughput breakdowns. To track query revisions, use **managed template/version codes** such as `customer.lookup.v2`, rather than hashing raw queries containing sensitive literals and exposing everything.

### 15.2. EXPLAIN with Synthetic Data

~~~cypher
EXPLAIN
MATCH (c:Customer {email: $email})
RETURN c.customerId AS customerId
LIMIT 1;
~~~

The plan shows indexes, Filters, Estimated Rows, and operators. Before sharing with support, replace real inputs with **structurally equivalent dummy parameters**.

To evaluate real performance, a synthetic/anonymized dataset must still preserve selectivity, property distribution, relationship cardinality, and graph scale; testing on three nodes tells you nothing about production speed.

### 15.3. Increase Log Verbosity Only with Time Limits

When higher observability detail is unavoidable:

1. Record the reason, approver, and active time window.
2. Test first in staging with synthetic markers.
3. Scope tightly to the target service/instance/operation where supported.
4. Capture only approved fields; avoid parameters and raw results.
5. Restrict viewers and export destinations.
6. Disable verbose settings once the investigation finishes.
7. Handle/purge generated logs per retention and security rules.

Never raise logging levels across the board and forget to revert them; heavy logging also degrades Neo4j and application performance.

## 16. Test Suite to Detect Sensitive Data Written to Logs

This step turns a "no PII in logs" policy into **verifiable technical proof**.

### 16.1. Use Unique Fake Canary Markers

Example test request:

~~~json
{
  "email": "canary-neo4j-2026@example.invalid",
  "phone": "+84-000-111-222",
  "apiToken": "TEST-ONLY-CANARY-SECRET-2026",
  "nested": {
    "note": "NEO4J-PII-CANARY-2026"
  }
}
~~~

These values are **synthetic test markers** with no real authentication power. Make them distinctive enough to search easily without colliding with normal data.

Send requests through a **production-equivalent pipeline**: HTTP/filter → Java/Spring → Driver → Neo4j → logger/collector/APM → backend/alerts.

### 16.2. Mandatory Test Scenarios

| Scenario | Risk | Expected Outcome |
|---|---|---|
| Successful query | Debug logger prints request and parameters | Canary marker absent from logs/traces/metrics |
| Query returning 0 rows | Full parameters logged to explain `not_found` | Only `outcome=not_found` logged |
| Query syntax error | Exception embeds query text/literals | No leaked parameters/literals |
| Uniqueness violation | Framework prints failing object | Only safe error code and correlation ID |
| Transaction timeout | Auto-enabled debug dumps | No request body or parameters printed |
| Managed transaction retry | Callback logs repeatedly | No PII logged on any attempt |
| Nested JSON/list parameters | Sanitizer scrubs only top-level keys | Nested canary marker does not appear |
| Result returning nodes/paths | Logging response objects | No sensitive properties/relationships printed |
| APM auto-instrumentation | Spans capture DB statements/params | Only allowlisted attributes |
| Metric labels | User IDs pushed into labels | No IDs/PII and no cardinality explosion |
| Slow query alert | Full query pasted into chat/tickets | Alert contains only operation code and numbers |
| Support bundle | Raw logs copied | Exported only through approved scrubbing flow |

### 16.3. Asserting That Sensitive Data Never Appears

A verification workflow:

1. Clear or isolate test log/trace namespaces for clean inspection.
2. Send requests containing fake canary markers to representative endpoints.
3. Trigger controlled successes, failures, and timeouts.
4. Wait for the observability pipeline to ingest all events.
5. Search for exact canary markers across logs, traces, metrics, alerts, and permitted exports.
6. If a marker appears, trace and fix the **emitting source** (app, driver, server, collector, APM) rather than merely hiding it in a dashboard.
7. Re-run after config changes or driver/Neo4j/collector upgrades.

Checking local logs alone is insufficient if a separate **APM backend** or alert channel copies data elsewhere.

### 16.4. Test Both "No Data Leaks" and "No Lost Operability"

Sanitization must not strip logs and metrics of operational utility. After hardening, you should still retain:

- Operation name.
- Outcome and safe error category.
- Approved request/correlation ID.
- Duration, retries, and timeouts.
- Context to locate the relevant query template/index.

The goal is **useful diagnostics without private data**, not shutting off observability entirely.

## 17. Common Mistakes

| Mistake | Why Is It Dangerous? | Fix |
|---|---|---|
| "Cypher uses parameters, so logs are safe." | Loggers can still print the parameter map | Disable/control parameter logging at every layer |
| Concatenating emails into query literals | Exposes emails in query text and invites injection | Use parameters |
| Logging full `parameters` to debug | Maps may hold emails, tokens, nested objects | Log only operation, outcome, latency |
| Logging full nodes/relationships/paths | Graph payloads carry PII and sensitive links | Return DTOs; never log raw `Result`/`Record` |
| Filtering only emails via regex | Misses tokens, phones, encoded/nested data | Allowlist at source; use sanitizers as defense-in-depth |
| Hashing emails directly with SHA-256 | Vulnerable to dictionary matching on candidate lists | Omit IDs or use key-managed HMAC |
| Putting `userId` in metric labels | Leaks identity and explodes cardinality | Use finite labels by operation/status |
| Putting request bodies into spans | APM stores copies of sensitive payloads | Allowlist span attributes |
| Sending raw exceptions to alerts | Messages/stack traces may contain sensitive values | Alert using safe error categories |
| Leaving Driver `TRACE` on indefinitely in prod | Risk of capturing payloads and high log overhead | Enable only with approval and TTL |
| Assuming default obfuscation always suffices | Behavior varies by version and log channel | Inspect settings and run canary tests |
| Checking only Neo4j's own log files | PII may leak via Java, Spring, or APM | Test end-to-end |
| Deleting PII in Neo4j while forgetting logs | Copies survive in collectors/archives | Enforce log retention and copy cleanup |
| Granting identical log access to all staff | Creates a backdoor to PII | Enforce RBAC, least privilege, and audits |
| Pasting raw `SHOW TRANSACTIONS` into tickets | May expose query text/business context | Review and scrub before sharing |
| Using real customer data to test redaction | Causes real leaks inside test systems | Use fake markers and synthetic data |
| Assuming disabling server logs suffices | App-side interceptors keep logging | Control every layer independently |

## 18. Secure Implementation Checklist

### 18.1. Cypher and Data Model

- [ ] Pass user-supplied values via parameters in all Cypher-supported positions.
- [ ] Never concatenate emails, tokens, passwords, or sensitive data into query literals.
- [ ] Select dynamic labels/types/properties strictly from allowlists.
- [ ] Classify sensitive node properties and relationship patterns.
- [ ] Return only fields genuinely needed by APIs—avoid returning entire subgraphs unnecessarily.
- [ ] Never send secrets to Neo4j merely for debugging.

### 18.2. Neo4j Server and Admin Privileges

- [ ] Verify exact Neo4j version and effective query logging settings.
- [ ] Disable or restrict parameter logging per policy.
- [ ] Test literal obfuscation (if available) rather than trusting defaults blindly.
- [ ] Grant query/transaction/log viewing privileges on a least-privilege basis.
- [ ] Protect log files, collectors, and export targets with RBAC, retention, and transport encryption.
- [ ] Never use raw production queries/results in shared incident docs.

### 18.3. Java Driver and Spring Data Neo4j

- [ ] Services never log parameter maps or raw entities/`Record`/`Result` objects.
- [ ] Loggers record only approved operations, outcomes, durations, and error codes.
- [ ] Exception handlers and AOP/interceptors never capture sensitive request bodies.
- [ ] Verify Driver/framework `DEBUG`/`TRACE` behavior on the exact running versions.
- [ ] Correlation IDs contain no emails or secrets.
- [ ] Managed transaction retries do not emit sensitive logs across attempts.

### 18.4. Observability and Operations

- [ ] APM/spans use an attribute allowlist; no parameters, tokens, or raw queries.
- [ ] Metric labels have low cardinality and never identify individuals.
- [ ] Alerts/tickets/chat messages contain no raw queries or unscrubbed exceptions.
- [ ] Access control, retention, copy export, and deletion processes exist for logs.
- [ ] Synthetic canary markers tested across successes, failures, retries, and timeouts.
- [ ] Searched for canary markers across **every** log/trace/metric/alert backend.
- [ ] Incident response runbook exists for secrets/PII accidentally logged.
- [ ] Logging policy re-verified after upgrading Neo4j, Driver, Spring, or APM agents.

## 19. Self-Check Exercises and Scenarios

### Exercise 1 — Are Parameters Truly Secret?

An application executes:

~~~cypher
MATCH (u:User {email: $email})
RETURN u.userId;
~~~

yet the logger writes `parameters={email: ...}`.

**Question:** Did parameterization eliminate all exposure risk?

**Answer:** No. Parameterization separates values from Cypher syntax, yet the logger still leaked the parameter map. Strip values from logs at the source and verify server-side query logging as well.

### Exercise 2 — Dynamic Queries

An endpoint interpolates `$email` into a Cypher string and enables slow query logging to investigate performance.

**Question:** What are the two risks?

**Answer:** Uncontrolled string concatenation risks Cypher injection, and the email gets recorded inside logged query text. Switch to parameters and configure logging without parameter capture.

### Exercise 3 — Nested Data

A logger scrubs top-level keys named `email`, yet the API receives:

~~~json
{
  "payload": {
    "profile": {
      "email": "canary@example.invalid"
    }
  }
}
~~~

**Question:** Does the rule reliably hide all sensitive data?

**Answer:** No. Sensitive fields can sit deep inside nested objects, and JSON schemas evolve. Never log raw maps; use an allowlist of safe fields plus canary testing.

### Exercise 4 — Per-User Metrics

A developer adds `userId` as a metric label measuring latency of a friend-recommendation query.

**Question:** Why shouldn't you do this?

**Answer:** User IDs identify individuals and explode time-series counts per account. Measure latency by approved operation/cohort instead of personal IDs.

### Exercise 5 — Exception Messages

A handler logs:

~~~java
logger.warning(exception.getMessage());
~~~

**Question:** Is this safe in all situations?

**Answer:** Never guaranteed. Messages can embed queries, inputs, or library-echoed values. Log safe error categories/codes and store detailed diagnostics in access-controlled channels only when needed.

### Exercise 6 — Hashing Emails

Operations proposes replacing emails in logs with `SHA256(email)` to track repeat customers.

**Question:** Is there a risk?

**Answer:** Yes. Emails can be guessed from candidate lists and hashed to match. If a pseudonym is genuinely required, consider key-managed HMAC with strict retention; otherwise omit IDs entirely.

### Exercise 7 — SHOW TRANSACTIONS

An engineer screenshots a tool displaying running queries and posts it in a public project ticket.

**Question:** What data could leak?

**Answer:** Depending on version and privileges, query text, internal schema structure, session details, or business context. Review and scrub before sharing; tickets are themselves retained copies requiring governance.

### Exercise 8 — APM Still Sees Emails

Neo4j query logs are configured not to log parameters, yet the APM dashboard still shows emails inside spans.

**Question:** What is the likely cause?

**Answer:** The APM agent or a Java interceptor is capturing parameters, request bodies, or error details **independently** of the Neo4j server. Fix instrumentation/scrubbers at the source and re-test end-to-end.

### Exercise 9 — Slow Query in Production

A two-hop query on a massive graph is slow. Developers want to turn on Driver `TRACE` logging and print parameter maps for two days.

**Question:** What is a safer approach?

**Answer:** Start with per-operation metrics, `EXPLAIN` plans, and synthetic data. If detailed logging is strictly needed, narrow scope/duration, verify with canary markers, restrict access, and exclude raw parameters.

### Exercise 10 — A Token Already Hit the Logs

Someone spots a live API token inside an alert posted to team chat and log storage.

**Question:** Is disabling the logger to stop new occurrences enough?

**Answer:** Not enough. Activate incident response, revoke/rotate the token, locate all copies in chat/logs/backups, purge/restrict per policy, and add regression tests against token leakage.

## 20. Key Takeaways

In a Neo4j system, **effective monitoring does not require logging sensitive data**. Cypher parameterization is the baseline step separating data from syntax, yet parameter values, node/relationship results, exceptions, transaction inspections, Java Driver logs, and APM spans can all still leak data.

Enforce **data minimization and allowlists where logs are emitted**: record operation names, outcomes, durations, classified error codes, and safe correlation IDs—never raw query parameters, emails, tokens, or entire subgraphs. Govern query logging according to your **Neo4j version**, log permissions, retention, dashboards, alerts, and exported copies. Finally, run **fake canary marker tests end-to-end**, including errors, retries, and traces. Proper monitoring diagnoses performance and outages **without turning logs into a shadow copy of customer data**.
