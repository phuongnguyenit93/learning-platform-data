# Protecting Sensitive Data in MongoDB Logs, Profiler, and Monitoring Systems

When a MongoDB application runs slowly, operations teams often raise the log level, enable the profiler, capture `explain()`, enable command monitoring in the driver, or forward data to an APM system. These tools are extremely useful for identifying slow queries, connection errors, and resource bottlenecks. However, they can also inadvertently create **a copy of sensitive data outside the business database**.

For example, a query looking up a customer by email address may contain the email in `filter`; an aggregation may contain an identification number in `$match`; an authentication error may include the account name; a trace may carry the full connection string if the application attaches it to span attributes. If this data goes into centralized logs, dashboards, support tickets, or a third-party monitoring service, the number of people and systems able to read it is often much larger than those authorized to read the original collection.

This lesson belongs to the **System Observability** chapter in the **Database Engine Document MongoDB** module, focusing on how to **protect sensitive data in logs, the database profiler, and monitoring systems** while preserving performance and incident diagnostics.

After this lesson, you will be able to:

1. Identify data paths that can expose PII, credentials, query literals, and internal information.
2. Distinguish diagnostic server logs, `system.profile`, audit logs, metrics, traces, and application/driver logs.
3. Design logging around **data minimization**, using field allowlists, redaction, and sampling.
4. Understand the `security.redactClientLogData` mechanism and the limits of server-side log redaction.
5. Enable/observe/disable the profiler in a controlled lab environment and understand its performance and security impacts.
6. Use the MongoDB Java Sync Driver to log useful performance information without logging raw BSON commands.
7. Apply RBAC, TLS, encryption at rest, retention, deletion, and incident response procedures when logs are exposed.
8. Build an operational checklist and evaluate the trade-offs between observability and data exposure.

> **Safety note:** all emails, tenant IDs, tokens, and query examples in this lesson are synthetic data. Do not enable high-level profiling, increase debug logging, or export production logs for practice. MongoDB/Atlas features may vary by version, tier, and deployment type; verify the documentation for your specific system before configuring it.

## 1. Why must “debug-only data” still be protected?

A business document may be protected by database RBAC, firewalls, TLS, and encryption mechanisms, but once a log line repeats values from that document, that copy follows an entirely different lifecycle:

```text
MongoDB collection (with database RBAC)
                  |
                  | Query / Command / Error
                  v
        Mongod diagnostic log
        system.profile / APM event
        Java application log
                  |
                  v
          Fluent Bit / Agent
                  |
                  v
       Central log / tracing vendor
                  |
         +--------+--------+
         |        |        |
      Dashboard  Alert   Export CSV
         |        |        |
         +--------+--------+
                  |
                Readers
```

This path introduces several risks:

- **Secret duplication:** a connection URI containing a password gets written to logs and then propagates across multiple systems.
- **Broader permissions:** support teams can view dashboards even though they are not permitted to read customer data in MongoDB.
- **Longer retention:** the original collection deletes a document, while logs/traces retain a copy for months longer.
- **External storage:** data is sent to a log SaaS in an unapproved region or provider.
- **Hard to erase completely:** the same value may persist in search indexes, alerts, exports, and backups of the logging system.
- **False assumption of safety:** omitting the full document still leaks emails, addresses, recovery codes, or session tokens in the query predicate.

**Log access must be treated as a form of data access**, not a harmless operational privilege.

## 2. Classify data before deciding what to log

Not all observable information carries the same sensitivity.

| Data group | Examples | Recommended handling |
| --- | --- | --- |
| **Credentials and secrets** | Passwords, access tokens, API keys, JWTs, URIs with user:password, private keys | Do not write to logs; if exposed, revoke/rotate immediately |
| **PII and user identifiers** | Email, phone number, address, national ID/citizen ID, personal tax/ID numbers | Avoid logging raw values; only use aggregate metrics or controlled pseudonymous IDs |
| **Sensitive business data** | Account balances, health records, message contents, internal documents | Keep out of query logs/APM unless necessary |
| **Internal system info** | Hostname, private IP, namespace, tenant identifier, topology | Collect only when needed and restrict access |
| **Query shape info** | Collection name, command type, number of filtered fields, duration, docs examined | Usually helpful for performance, though still assess sensitivity of field names |
| **Aggregate metrics** | Connection count, CPU %, query latency histogram, replication lag | Preferred for routine monitoring |
| **Trace correlation** | Opaque request ID, service name, span duration | Useful provided the ID contains no sensitive data |

### Four-tier reference classification

```text
PUBLIC         public, non-identifying data
INTERNAL       system architecture and state
CONFIDENTIAL   restricted customer/business data
SECRET         passwords, tokens, keys, private credentials
```

This is an illustrative model; organizations may use different classification schemes. `SECRET` data should generally **never appear in logs in the first place**, rather than relying on regex to strip it out after transmission.

### An easily overlooked string: the MongoDB connection string

```text
mongodb+srv://app_user:<password>@cluster.example.mongodb.net/orders
```

If an exception or debug message prints the raw URI, account details, hostnames, and potentially the password are copied into logs. Do not print `MONGODB_URI`, do not attach raw URIs to trace attributes, and do not put secrets into MongoDB command `comment` fields.

## 3. How do observability sources in MongoDB differ?

| Source | Primary content | Sensitivity risk |
| --- | --- | --- |
| **MongoDB diagnostic log** | Startup, connections, errors, slow operations, server state | Query commands/fields/values depending on event and configuration |
| **Database profiler** `system.profile` | Profiled operation details, duration, plan, command | Can store **query literals, filters, pipelines, and identifiers** |
| **Audit log** | Auditable actions such as authentication/authorization/DDL per capability | Identity, namespace, event parameters |
| **Driver command monitoring** | Command started/succeeded/failed events in the application | Started events can contain command BSON with real values |
| **Application logs** | Requests, exceptions, business operations | Emails, tokens, payloads, query filters logged by developers |
| **Metrics** | Counts, gauges, latency, cache, locks, queue/replication | Metric labels can contain tenant/user IDs if poorly designed |
| **Distributed tracing/APM** | Spans, attributes, events, error details | Raw queries, database names, URLs, user metadata, or exceptions |
| **Query explain/current operations** | Query plan, operation state, statistics | Can expose filters/query values and namespaces |
| **Exports/backups/crash dumps** | Copies of the sources above or memory | Can contain all log data as well as secrets |

**Do not apply a single blanket policy like “allow logging everything at DEBUG for 7 days”** across these sources. Each source requires an owner, access level, retention period, controls, and an incident response plan.

## 4. Three often conflicting goals

When designing observability, you must balance:

1. **Good diagnostics:** enough context to identify slow queries, affected collections/indexes, clients, and timestamps.
2. **Sensitive data minimization:** avoiding collection of emails, passwords, tokens, or document contents unless needed.
3. **Cost/impact reduction:** keeping log volume, profiler overhead, and storage/egress costs within budget.

For example, to know that a query is slow because it scans too many documents, the operations team usually **does not need the specific email being queried**. More useful fields are:

```text
operation: find
collection: customers
duration_ms: 820
docs_examined: 210000
keys_examined: 0
plan_summary: COLLSCAN
app_component: customer-api
request_id: opaque-7a31
```

These indicators can be sufficient to spot a missing index. Meanwhile:

```text
filter: {email: "customer.real@example.com"}
access_token: "eyJ..."
```

are unnecessary for most performance monitoring and introduce new risks if written to logs.

## 5. Queries can leak PII even when the response contains no PII

Consider a `customers` collection with the document:

```javascript
{
  _id: "CUS-01",
  email: "demo-user@example.invalid",
  phone: "+00-000-000-000",
  status: "ACTIVE"
}
```

A backend looks up a customer:

```javascript
db.customers.findOne({
  email: "demo-user@example.invalid"
});
```

The response might only use `_id`, yet **the email value is already inside the command sent to the database**. If the profiler, debug driver, or tracing records BSON commands, the email can end up in telemetry.

Places where query literals can appear:

- Equality and range predicates such as `email`, `phone`, `accountNo`, `createdAt`.
- Aggregation `$match`, `$lookup`, `$project` stages containing literal values.
- Update `$set` operations carrying account contents or session metadata.
- Error messages returned from constraint/validation failures.
- Application-supplied `comment` values in commands.
- HTTP URLs, request bodies, or application debug statements.

### “Not logging the response” is not enough

If the application avoids logging returned documents yet logs:

```java
log.debug("Mongo filter: {}", filter.toBsonDocument());
```

then an email lookup still risks exposing the email. A sound policy must address **request-side query data**, not just responses or database rows.

## 6. Query shape and query literal are two different concepts

A **query literal** is a concrete value sent in a query:

```javascript
{ email: "demo-user@example.invalid", status: "ACTIVE" }
```

A **query shape** represents the structure/pattern of the query without needing to preserve all values:

```text
find customers
filter keys: email == ?, status == ?
sort: none
limit: 1
```

Measuring query shapes helps to:

- Group executions of the same query pattern.
- Compare p50/p95/p99 latency per pattern.
- Identify missing indexes or query plan changes.
- Reduce the need to store many PII values.

However, **shapes can still be sensitive**: field names, collections, tenant-specific namespaces, or queries touching health data can reveal internal structure. Access to shape metadata still needs restrictions even when the original email is gone.

### Do not invent unstable query fingerprints on your own

Replacing query values with `?` and arbitrarily hashing the entire string can yield unstable fingerprints across field ordering, BSON types, serialization, or driver versions. If the server or observability platform provides a supported query shape identifier, prefer using it. Even then, verify its semantics, stability, and viewing permissions for your version.

## 7. What can the MongoDB diagnostic log contain?

The MongoDB diagnostic log can record:

- Process startup, state transitions, and environment details.
- Connection open/close events, client metadata, and network errors.
- Replication, sharding, storage engine, and operational errors.
- Slow operations, depending on diagnostic verbosity, thresholds, and operation type.
- Troubleshooting information.

**Never assume server logs contain only harmless metadata.** Some log lines may contain command data or query-related details. Exact fields and detail levels vary by MongoDB server version, command, profiling/logging configuration, and supported redaction features.

### Minimalist log line example

```json
{
  "t": "2026-11-14T08:01:00.000Z",
  "s": "I",
  "c": "COMMAND",
  "msg": "Slow query",
  "attr": {
    "ns": "shop_app.orders",
    "durationMillis": 820,
    "planSummary": "COLLSCAN",
    "docsExamined": 210000
  }
}
```

This is an **illustrative information layout**, not an exact log template applicable identically across every version. Real logs may include commands, filters, or other attributes containing sensitive data.

### Higher verbosity is not always better

High diagnostic verbosity can:

- Increase log volume and I/O.
- Increase ingestion costs into centralized logging systems.
- Capture large amounts of unclassified context.
- Cause sensitive data to appear across more lines.
- Bury important signals in noise.

A better practice is to increase logging **only in a targeted manner, for a limited time, on an authorized system**, then revert to baseline and manage collected artifacts according to retention.

## 8. Server-side redaction: `security.redactClientLogData`

Certain MongoDB editions/deployments support security options such as `security.redactClientLogData` to **redact some data associated with client operations** before writing diagnostic server logs.

Illustrative configuration option example, **applicable only where supported by the deployment/version**:

```yaml
security:
  authorization: enabled
  redactClientLogData: true
```

The goal of this option is to reduce the likelihood that server-side logs contain sensitive values from operations. However, keep these distinctions clear:

1. **Limited scope:** does not guarantee that every message, stack trace, audit record, driver log, or exporter is redacted.
2. **Does not alter data stored in collections:** log options do not modify documents or actual queries.
3. **Does not automatically protect `system.profile` or all other telemetry sources:** each source must be controlled separately.
4. **Does not replace access controls:** users authorized to read logs can still see internal metadata.
5. **Can reduce debugging detail:** some verbatim details will no longer appear.

**Do not assume this option exists or behaves identically across MongoDB Community, Enterprise, or all Atlas tiers.** Before rolling out, check the exact documentation for your server/Atlas version and test in an environment with synthetic data.

### Redaction is not encryption

| Mechanism | Effect |
| --- | --- |
| Redaction | Removes/hides values before writing or displaying |
| Masking | Replaces part of a value so viewers cannot easily recognize it |
| Encryption in transit | Protects bytes over the network |
| Encryption at rest | Protects bytes on storage media |
| RBAC | Restricts who can access |
| Retention/deletion | Limits how long data persists |

A log encrypted at rest can still display raw emails to a user authorized to decrypt it. **Encryption does not make data less sensitive once read**.

## 9. What is the database profiler?

The MongoDB **database profiler** collects information about operations according to profiling settings, typically written to the system collection:

```text
<database>.system.profile
```

For example:

```text
shop_app.system.profile
```

The profiler helps inspect:

- Which command ran, and at what time.
- Operation latency.
- Number of documents/keys examined for applicable operation types.
- Plan summary and available query metrics.
- Namespace/command information and client metadata depending on version.

**Risk:** profile documents can contain **command BSON or literals** from queries. Therefore, `system.profile` must be classified and managed as a **data source that may contain sensitive content**, not merely a statistics table.

### Illustrative description of a profile record

```javascript
{
  ts: ISODate("2026-11-14T08:01:00Z"),
  ns: "shop_app.customers",
  op: "query",
  millis: 820,
  command: {
    find: "customers",
    filter: {
      email: "demo-user@example.invalid"
    }
  },
  docsExamined: 210000,
  planSummary: "COLLSCAN"
}
```

This is a **simplified conceptual sample**. Specific fields differ by operation type and MongoDB version. The key takeaway is that **query predicates can end up inside profile records**, even if you only enabled the profiler to measure timing.

## 10. Profiling levels and risks

The database profiler typically has three levels:

| Level | General meaning | Assessment |
| ---: | --- | --- |
| `0` | Does not write profile records for the database under normal profiling mode | Suitable baseline when the profiler is not needed |
| `1` | Profiles operations based on supported slow thresholds/filters and sampling | Use purposefully, time-bounded |
| `2` | Profiles all operations within the applied scope | **High overhead and data-exposure risk**, use only under strict control |

Some server versions support a **profile filter** and more selective options. Option names and how they interact with `slowms`/sampling must be checked against your actual release.

### Level 0 does not mean the server stops all slow-operation logging

When you turn off the database profiler with level 0, MongoDB may still write **diagnostic logs** for slow operations depending on server configuration. These are **two separate sources**:

- `system.profile`: database profiler.
- Diagnostic log: MongoDB process log, which may include slow-operation details.

Disabling one source neither disables nor deletes data already written to the other.

### What is concerning about profiling level 2?

At level 2, profile record volume grows with every operation. Under workloads of thousands of requests per second:

- The profiler can generate write/I/O overhead and impact latency.
- Many commands containing query values will be persisted.
- Anyone authorized to read `system.profile` can view unnecessary details.
- Dumps/exports or profiler snapshots easily capture sensitive data.

Never enable level 2 in production by default just to hunt down a slow query.

## 11. Inspecting profiling status with `mongosh`

On an **authorized lab database**, run:

```javascript
use mongo_observability_lab

db.getProfilingStatus();
```

This command reports the profiling parameters supported by the version/deployment. Some Atlas/managed environments restrict modification rights or have distinct collection mechanisms; do not assume every database user is allowed to run these commands.

### Enabling level 1 with sampling in a lab

Illustrative example:

```javascript
db.setProfilingLevel(1, {
  slowms: 100,
  sampleRate: 0.1
});
```

Meaning:

- `1`: profile according to slow-operation conditions.
- `slowms: 100`: 100 ms slow threshold in the supported configuration context.
- `sampleRate: 0.1`: capture only a fraction of operations per server/version behavior.

**Do not treat sampling as “never recording PII”.** Even when profiling only 10% of qualifying operations, a single record can still contain the exact sensitive value prohibited by policy.

### Do not alter production settings arbitrarily

Slow-operation logging/profiling parameters can affect other parts of the process, not just one collection. Record the environment baseline first, understand the blast radius, and prepare a rollback plan. After the lab exercise, turn profiling back to its initial lab state:

```javascript
db.setProfilingLevel(0);
```

In production, **do not blindly set level 0 if the managed baseline uses another level**, and do not forget to restore any modified `slowms`/sampling parameters. Follow approved operational configuration.

## 12. Reading `system.profile` to minimize exposure

In the lab:

```javascript
const lab = db.getSiblingDB("mongo_observability_lab");

lab.system.profile.find(
  {},
  {
    _id: 0,
    ts: 1,
    ns: 1,
    op: 1,
    millis: 1,
    planSummary: 1,
    docsExamined: 1,
    keysExamined: 1
  }
).sort({ ts: -1 }).limit(10);
```

This is a **projection allowlist**: displaying only the fields needed for performance analysis. Do not run:

```javascript
// Avoid printing full profile documents from production:
db.system.profile.find().forEach(printjson);
```

because it can print `command`, `filter`, or other sensitive fields into terminal history, tickets, shell captures, or log automation.

### Projection only reduces returned data; it does not delete stored data

This is a critical boundary:

```text
Profile record on disk:
  may contain command/filter with PII
             |
             v
Query projection
             |
             v
Screen shows only ts, millis, ns, docsExamined
```

Projection prevents **further propagation** of sensitive details through output, yet the underlying bytes may still sit inside `system.profile`. To protect stored data, you must control **collection, collection read permissions, retention, and backup/export locations**.

### `system.profile` is typically a capped collection

The profiler uses a system collection with capped mechanics depending on MongoDB design/version. A capped collection has a size limit and overwrites older records cyclically, **not a precise retention guarantee measured in days**. Do not rely on capped collection size to guarantee that documents containing PII are purged after exactly N hours.

Do not arbitrarily drop/recreate `system.profile` to “clear logs” in production: system collections have management rules and affect profiling state. Follow the official procedure for your server version.

## 13. The profiler and audit logs are not the same

The **profiler** serves performance/operation analysis, whereas the **audit log** tracks who performed which actions according to audit policy and supported features.

| Aspect | Database profiler | Audit log |
| --- | --- | --- |
| Primary goal | Performance/query diagnostics | Security behavior and compliance tracking |
| Collection scope | By level, filter, slowms, sampling | By audit configuration/filters |
| Contents | Operation timing, query/command/plan info | Auth, authz, DDL, and policy-defined events |
| PII risk | Query literals, namespaces | Identity, event parameters, potentially sensitive metadata |
| Access rights | Corresponding profiling read/control privileges | Usually restricted audit/security privileges |
| Retention | Profiling collection and operational policy | Dedicated audit policy, potentially long retention |

Audit log support, destinations, and configuration vary across MongoDB Enterprise, Atlas, and community deployments. **Do not promise that every MongoDB deployment offers identical audit capabilities**.

For security incidents, audit logs typically need tamper protection against unauthorized editing/deletion, whereas the profiler should be enabled selectively to avoid data exposure and performance overhead. Do not use the profiler as a substitute for a compliance audit system.

## 14. MongoDB diagnostic log redaction does not protect driver logs

Even when the server has log redaction configured, the application can still leak data **before sending the command**:

```java
Document filter = new Document(
    "email", "demo-user@example.invalid");

// Not suitable for production:
logger.debug("Mongo query = {}", filter.toJson());
```

This line is emitted by the **Java application logger**, outside the scope of `mongod` server-side redaction options.

Similarly, a MongoDB driver can provide **command monitoring events** for APM/debugging. If an application or custom library serializes the entire `CommandStartedEvent.getCommand()`, query literals can end up in logs.

### Practical rules

- Do not log full BSON queries or aggregation pipelines.
- Do not log raw request/response bodies if they contain user data.
- Do not log credentials, tokens, or connection strings.
- Allow only predefined **field names/metric names**.
- Replace user data with opaque correlation IDs when linking requests.
- Control logger categories and `DEBUG` levels in production.
- Do not rely on server redaction to fix logging at the application, driver, or tracing layers.

## 15. Java Sync Driver example: safer command monitoring

The MongoDB Java Sync Driver supports attaching a `CommandListener`. Below is an example logging only **an approved command name and execution duration**, rather than recording the contents of `command`.

```java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.event.CommandFailedEvent;
import com.mongodb.event.CommandListener;
import com.mongodb.event.CommandStartedEvent;
import com.mongodb.event.CommandSucceededEvent;

import java.util.Set;
import java.util.concurrent.TimeUnit;

public final class SafeMongoCommandMonitor {
    private static final Set<String> ALLOWED_COMMANDS =
        Set.of("find", "aggregate", "insert", "update",
               "delete", "count", "getMore");

    private static String safeCommandName(String name) {
        return ALLOWED_COMMANDS.contains(name) ? name : "other";
    }

    static final class SafeListener implements CommandListener {
        @Override
        public void commandStarted(CommandStartedEvent event) {
            // Do not call event.getCommand().toJson()
            // and do not send command BSON to APM/logs.
        }

        @Override
        public void commandSucceeded(CommandSucceededEvent event) {
            long millis =
                event.getElapsedTime(TimeUnit.MILLISECONDS);

            System.out.printf(
                "mongo_command status=ok kind=%s elapsed_ms=%d%n",
                safeCommandName(event.getCommandName()),
                millis
            );
        }

        @Override
        public void commandFailed(CommandFailedEvent event) {
            System.out.printf(
                "mongo_command status=error kind=%s%n",
                safeCommandName(event.getCommandName())
            );

            // Do not log raw Throwable/stack traces
            // if they may contain URIs or query values.
        }
    }

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Missing MONGODB_URI");
        }

        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(new ConnectionString(uri))
            .addCommandListener(new SafeListener())
            .build();

        try (MongoClient client = MongoClients.create(settings)) {
            client.getDatabase("mongo_observability_lab")
                .runCommand(new org.bson.Document("ping", 1));
        }
    }
}
```

**This is a minimal logging pattern.** Using `System.out` here is purely illustrative; production systems should use a properly configured and controlled metrics/logging library. If you only need duration histograms, a metrics collector that avoids emitting per-operation text may be a better fit.

### What the example intentionally avoids

Do not call:

```java
event.getCommand().toJson();
```

Do not log:

```text
MongoClientSettings containing the connection string
CommandStartedEvent BSON commands
Exception messages containing secrets/query values
Raw database documents
```

Even database/collection names can be sensitive if namespaces contain tenant identifiers. That is why the example uses an allowlist of command names and omits the database name.

### Be careful with errors and exception text

`CommandFailedEvent.getThrowable()`, stack traces, and exception messages can assist diagnostics, but they should never be treated as unconditionally safe. If an application requires error telemetry, use **approved error classes/categories** and store sensitive diagnostic details in a tightly restricted investigation channel, if policy allows.

## 16. Stop the problem at the source: never log full queries

Compare:

```java
// AVOID:
logger.info("Searching customer with filter={}",
    new Document("email", customerEmail).toJson());
```

With:

```java
// BETTER APPROACH:
logger.info(
    "customer_lookup outcome={} latency_ms={} request_id={}",
    found ? "found" : "not_found",
    elapsedMillis,
    safeRequestId
);
```

In the second pattern:

- The email never enters the log.
- Lookup outcome is represented as a category.
- Latency supports diagnostics.
- The Request ID is a **system-issued opaque token** for log correlation, containing no email, phone, access token, or user content.

### A Request ID can also become sensitive data

If a system uses:

```text
request_id = "user-email@example.com-2026-11-14"
```

then renaming the field to `request_id` does not protect PII. Use random/opaque IDs, enforce length bounds, and validate formats before logging.

## 17. MongoDB `comment`: good for correlation, never for PII

Several MongoDB commands support a `comment` field to attach context to an operation. Analysis tools can display that comment when inspecting queries or the profiler.

Lab example:

```javascript
db.orders.find(
  { status: "NEW" }
).comment("orders-list-v2");
```

This is a **fixed label by query type**, not customer data. Do not do:

```javascript
// AVOID: comment containing PII.
db.orders.find({
  customerEmail: "demo-user@example.invalid"
}).comment("customer=demo-user@example.invalid");
```

### How to use `comment` appropriately

- Approved query template IDs: `orders-list-v2`.
- Vetted service/component names.
- Correlation IDs containing no user information.
- No secrets, raw request inputs, JWTs, or session IDs.
- Never rely on `comment` to enforce authorization.

Exact `comment` support and placement vary by MongoDB driver and command. If attaching correlation metadata for APM, understand **which telemetry sinks can store it**.

## 18. Leverage metrics without document values

Many operational questions can be answered using **aggregate metrics** without raw profiler documents:

- How many connections are currently open?
- When did p95 query latency start rising?
- Are CPU, cache misses, and disk I/O increasing?
- Is replication lag exceeding SLA?
- Are failed operations rising by error category?
- Are the numbers of documents/keys examined per query shape abnormal?

Example fetching a few `serverStatus` fields in a lab with appropriate privileges:

```javascript
const status = db.getSiblingDB("admin")
  .runCommand({ serverStatus: 1 });

printjson({
  connectionsCurrent: status.connections?.current,
  connectionsAvailable: status.connections?.available,
  opcounters: status.opcounters
});
```

This snippet avoids printing all of `serverStatus`. Still, `serverStatus` remains operational data requiring proper privileges, and the `opcounters` object contains multiple subfields rather than a single metric. Select narrow fields as needed when exporting to monitoring systems.

### Metrics also require control

Not all metric labels are safe:

```text
BETTER:
  mongodb_query_duration_seconds{
    service="orders-api",
    operation="find",
    outcome="ok"
  }

AVOID:
  mongodb_query_duration_seconds{
    customer_email="demo-user@example.invalid",
    phone="+00-000-000-000"
  }
```

Adding email/userId as labels both **leaks identifiers** and causes **high cardinality**, driving up CPU/RAM/storage in the metrics backend. If per-tenant measurement is required, use only opaque tenant identifiers per policy and evaluate cardinality and access permissions.

## 19. Tracing and APM: a common leak vector

APM agents or distributed tracing libraries can automatically capture:

- HTTP route/method/status.
- Database system, operation name, and collection.
- Database statement/query/command.
- Exception class/message/stack trace.
- Request URL, headers, and custom app-attached attributes.

Do not enable **capture database statements** or **capture request bodies** without reviewing the actual data flowing through them.

### Example of a properly minimized span

```text
span.name = "MongoDB find"
db.system = "mongodb"
db.operation = "find"
app.component = "customer-api"
duration_ms = 95
status = "ok"
request_id = "opaque-7a31"
```

Avoid:

```text
db.statement = "{email:'demo-user@example.invalid'}"
http.url = "/customers?email=demo-user@example.invalid"
db.connection_string = "mongodb+srv://user:password@..."
exception.message = "full raw payload with secrets"
```

### Filters must run before data leaves the application

If an entire command is already sent to an APM vendor and the UI dashboard merely hides `db.statement`, the original data may still live in the backend, exporter queues, or replicas. **Prefer blocking/redacting at the agent or collector before export**, not merely hiding fields in the UI layer.

## 20. Turn a monitoring pipeline into multiple checkpoints

```text
Source: MongoDB / Application
           |
           v
  Local agent / instrumentation
  - do not capture raw payloads
  - allowlist attributes
           |
           v
  Collector / log processor
  - redact/drop sensitive fields
  - sampling and routing
           |
           v
  Central observability store
  - encryption
  - RBAC / separation of duties
  - retention
           |
           v
  Dashboard / query / export
  - row/field access controls
  - audit views/downloads
```

**Priority order:** never collect → redact before export → control access at rest → shorten retention → monitor exports. Waiting until the final step to redact means sensitive bytes may already reside in network buffers, collectors, and backups.

### How does a redaction pipeline fail?

A processor drops fields named `password`, yet misses:

```text
passwd
pwd
accessToken
authorization
api_key
credentials
mongo_uri
sessionCookie
```

Or a secret appears inside nested JSON, free-form strings, or exception stack traces. Regex rules targeting a few keywords **cannot guarantee** catching every occurrence. For known data structures, an **allowlist schema** is far more reliable than a generic blocklist.

## 21. Redaction, masking, tokenization, and hashing

Common mechanisms:

| Mechanism | Purpose | Example |
| --- | --- | --- |
| **Drop field** | Do not store the value | Remove `email` entirely from logs |
| **Redact** | Replace with a marker | `email: "[REDACTED]"` |
| **Mask** | Keep only non-sensitive portions | `phone: "***-***-1234"`, if policy allows |
| **Tokenize** | Replace with an opaque ID backed by a protected mapping table | `customer_ref: "tok-7a31"` |
| **Hash** | Create a one-way fingerprint | Policy-approved keyed hash if correlation is needed |
| **Aggregate** | Keep summary numbers instead of individual identities | 95th percentile latency |

### Hashing does not automatically make PII public data

Emails often occupy a relatively small guessable space. If logs contain unsalted `SHA256(email)`, someone with a list of common emails can precompute hashes to re-identify users. **Hashing alone does not guarantee anonymity**.

When correlating events by identity is required, consider:

- Opaque request/customer IDs carrying no direct meaning.
- Keyed HMAC with protected keys instead of plain hashes, if using fingerprints.
- Limited retention and restricted access rights.
- Avoiding reusing the same pseudonym beyond what is strictly necessary if individual tracking risks exist.

### Masking can still leak data

Retaining the last four digits of an account or phone number may be disallowed in certain contexts. Masking rules must follow classification/compliance policy rather than assuming safety merely because the full value is hidden.

## 22. Regex redaction is no substitute for data minimization

Suppose a log processor searches for `password=...`. It can easily miss:

```json
{
  "command": {
    "update": "profiles",
    "updates": [
      {
        "q": {"email": "demo-user@example.invalid"},
        "u": {"$set": {"sessionToken": "synthetic-do-not-use"}}
      }
    ]
  }
}
```

Even if the processor catches `sessionToken`, it must also handle the email inside the nested query. A logger that **never emits the `command` field** in the first place is usually safer than a pipeline trying to scrub serialized BSON command strings.

### Preferred approach

1. **Never log raw commands**.
2. Design **structured events** using approved fields.
3. If command text must be captured for an investigation, do so in a controlled environment with narrow sampling, very short retention, and explicit approval.
4. Perform structural redaction prior to export.
5. Monitor dropped/redacted event rates and processor errors.
6. Assess the risk of undetected new secrets.

Never claim that a generic regex set has “scrubbed 100% of PII from all logs”.

## 23. Access control for `system.profile` and diagnostic sources

Operators who need latency metrics **do not automatically need permission to read every profile document**. Separate roles cleanly:

- **Database app user:** read/write permissions limited to business namespaces.
- **Monitoring account:** permissions restricted to approved metrics/status commands.
- **Performance investigator:** temporary access to read profiler details during an incident.
- **Security/audit operator:** separate access to audit/access logs.
- **Backup/restore operator:** backup and recovery privileges per policy.

Configuring profiling or reading `system.profile` requires specific privileges depending on server/version. Never use `root` or `atlasAdmin` credentials by default for a simple exporter.

### Even a read operation can cause exposure

Even running `find()` on `system.profile` can return PII. You should:

1. Restrict who has `find` on this namespace.
2. Use projections/aggregations returning only necessary fields.
3. Avoid exporting full raw profile data into a secondary log store.
4. Use temporary sessions/roles if supported by your organization.
5. Audit who accesses and exports diagnostic data where auditing capabilities permit.

### Namespaces themselves can reveal information

If databases/collections are named after customers or confidential projects, `ns` itself may carry sensitive details. You may need to map namespaces to generic service identifiers in public/team-wide dashboards while restricting detailed visibility to DBAs.

## 24. Securing access to log and monitoring systems

A governance model:

| Role | Appropriate access | Avoid granting |
| --- | --- | --- |
| Developer | Metrics and dashboards for owned services | Full raw production profiler logs |
| On-call operator | Alerts, error categories, query shapes | Passwords/PII/raw commands |
| Investigating DBA | Temporary incident access to needed diagnostics | Permanent access to all secrets |
| Security team | Task-scoped audit events, controlled incident artifacts | Untracked exports or public sharing |
| Vendor/support | Metrics/sanitized support bundles | Raw memory dumps, production secrets |

Principles:

- SSO/MFA for observability platforms where appropriate.
- Role-based access scoped by team, environment, and namespace/data classification.
- Separation of production from staging/development.
- Auditing reads/exports of sensitive data when supported by the platform.
- Disabling public sharing links and reviewing dashboard permissions.
- Never pasting raw profiler output into broad-audience tickets or chats.

A dashboard displaying customer emails is a **customer data store**, even if it is titled “Performance Dashboard”.

## 25. Encryption in transit and at rest

**TLS:** protects network traffic from applications to MongoDB and from monitoring agents to collectors/backends.

**Encryption at rest:** mitigates unauthorized access to storage media, applied across database volumes, log files, backups, and observability storage per policy.

**Client-side Field Level Encryption / Queryable Encryption:** can help protect specific database fields according to their respective features and constraints, but **does not automatically protect logs generated prior to client-side encryption**, for example:

```text
Java app:
  has plaintext email
       |
       +--> logger.debug(plaintext email)  [LEAK]
       |
       v
  Client-side encryption
       |
       v
  MongoDB receives encrypted data
```

Therefore, encrypting data inside MongoDB **does not make it safe** for an application to write plaintext to logs.

### Backups and exports also need encryption

If `system.profile`/logs are included in backups, those backups may hold sensitive data longer than source retention. Manage encryption keys, access, lifecycle, and backup deletion under the same data classification. Never assume MongoDB backups always include or exclude `system.profile`: scope depends on the backup tool/type and configuration.

## 26. Retention: how long is long enough?

Each telemetry category serves a different purpose:

```text
Operational metrics:
  long enough for trend / capacity tracking

Diagnostic logs:
  incident investigation window, backed by a deletion policy

Raw profiler:
  short window, only during approved investigations

Security audit logs:
  per investigation and compliance requirements

Incident artifacts:
  per dedicated evidence retention procedures
```

There is no single retention period fitting every organization. Policy must define:

- **Processing purpose** and data owner.
- **Types of sensitive data** that may appear.
- **Time required** to detect/investigate issues.
- **Number of copies** across agents, buffers, queues, indexed stores, archives, exports, and backups.
- **Deletion workflow** upon expiration or legal request.
- **Controlled legal hold exceptions**.

### Log rotation does not equal deletion

Rotating `mongod.log` to `mongod.log.1` or compressed archives merely moves storage location; sensitive bytes may still remain. Coordinate **rotation + secure access + retention/deletion + backup policies**.

### Sampling does not lower security classification

An event containing a password remains **SECRET** even if sampled at 1 in 10,000. Sampling reduces volume; it does not turn a violation of “never log credentials” into an acceptable practice.

## 27. Log ingestion and data living outside the database

In a centralized system, a single event can exist in:

```text
1. Local mongod log
2. Local agent buffer
3. Message broker / spool directory
4. Collector memory/queue
5. Central log store
6. Log platform search index
7. Dashboard cache
8. Notification / alert message
9. Exported JSON/CSV
10. Log platform backup/archive
```

Deleting an event at point 5 does not necessarily remove copies at 1–4 and 6–10. That makes **data lineage** of diagnostic data essential.

### Never push raw data to broad alert channels

An alert like:

```text
MongoDB slow query exceeded 2s
service=orders-api
query_shape=find_by_customer
p95=2200ms
```

is usually sufficient to page on-call. There is no need to attach:

```text
email, session token, raw filter,
full command body, document payload
```

into email/chat alerts where recipients can forward/screenshot them and retention is hard to govern.

## 28. Information leak via logs incident: runbook

Suppose operations discovers a connection URI with a password inside centralized logs. Response should prioritize **containment and evidence protection**:

1. **Scope the exposure:** which events, services, timestamps, log sinks, and who had viewing access.
2. **Stop ongoing leaks:** disable or fix the logger emitting the URI/command, narrow export routes if needed.
3. **Revoke/rotate exposed secrets** per approved procedures; do not wait for log deletion before rotating.
4. **Check for unauthorized access:** authentication attempts, network access, and activity on the affected user/token.
5. **Restrict log access:** temporarily tighten viewers/exports on the affected log set.
6. **Preserve investigative info** in an authorized channel, avoiding copying secrets into public tickets.
7. **Delete or redact copies** across logs/alerts/exports/backups per policy and technical capability.
8. **Re-test instrumentation** with synthetic data and rules to prevent recurrence.
9. **Document the incident**: root cause, data scope, impact, and corrective actions.
10. **Notify/comply** with applicable policies and regulations if personal data was affected.

### Deleting logs does not replace rotating secrets

A token that appeared in a dashboard could already have been downloaded, screenshotted, or used before deletion. If it is a usable credential, **revocation** is what stops ongoing abuse.

### Do not “preserve evidence” by spreading it further

Investigators must not paste raw credentials into a ticket or group chat to “document the incident.” Use secret references, incident IDs, and controlled evidence stores; contents may require stricter security controls than ordinary logs.

## 29. Debugging slowness: prioritize metrics and query shapes before the profiler

A sound diagnostic workflow:

```text
Alert: p95 latency increasing
          |
          v
Metrics: CPU/I/O/cache/connections
          |
          v
Query shape / planSummary / index stats
          |
          v
Explain on synthetic or redacted query
          |
          v
Targeted profiler only when truly needed
          |
          v
Disable profiling / govern artifacts
```

This avoids turning on raw-data collection prematurely.

### Example showing missing indexes can be spotted without PII

A report shows:

```text
Operation: find
Collection: customers
Duration p95: 900 ms
Plan: COLLSCAN
Docs examined: 450000
Returned docs: 1
```

You do not need the concrete email to see that the query is scanning many documents and needs index/selectivity review.

### `explain()` must also be treated as diagnostic data

An `explain()` output can include:

- Filters/query shapes with literal values.
- Namespaces, index names, plan cache keys, and statistics.
- Aggregation pipelines.

When sharing `explain` with others, select only required fields or redact first. **Do not paste raw production explain output into public forums or vendor tickets without reviewing data classification.**

## 30. `currentOp` and in-flight operation details

In authorized environments, `$currentOp`/operation monitoring tools help spot long-running or lock-waiting operations. However, full operation details can also contain commands/filters.

One approach is selecting only **the necessary fields**:

```javascript
db.getSiblingDB("admin").aggregate([
  {
    $currentOp: {
      allUsers: false,
      localOps: true
    }
  },
  {
    $project: {
      _id: 0,
      type: 1,
      op: 1,
      secs_running: 1,
      waitingForLock: 1
    }
  }
]);
```

**Note:** `$currentOp` privileges and semantics differ by topology, server version, and Atlas tier. This example only illustrates **projecting out the `command` field**, not an API guaranteed to expose every field identically across all deployments.

Do not run:

```javascript
// Caution: can display raw command/query values.
db.currentOp();
```

and paste raw output into unrestricted logs or tickets.

## 31. Atlas observability: never confuse capabilities with default permissions

MongoDB Atlas provides monitoring, Query Profiler, Performance Advisor, logs, and integrations depending on cluster tier, edition, and version. Not every Atlas deployment permits configuring the profiler via `db.setProfilingLevel()` in the same way as self-managed deployments, nor supports identical log export levels.

Things to verify when using Atlas:

- **Who holds project/organization permissions to view logs, profiler, and query data?**
- **Which privileges does the database user** have on the MongoDB data plane?
- Does project monitoring forward data to external integrations?
- Which user/vendor accounts can view query details?
- Do log exports travel to another cloud storage bucket, SaaS, or region?
- What is the profiler/log/tracing retention for your tier/platform?
- Which redaction/diagnostic logging configurations apply, and what are their limits?

### Distinguish UI roles from collection privileges

Someone allowed to open the Atlas monitoring dashboard **does not necessarily** hold MongoDB `readWrite` on `ordersdb`; conversely, a database application user should not hold management rights over the entire Atlas project. Still, dashboards and logs may contain metadata or sensitive values. **Review both Atlas project permissions and database RBAC**.

### Do not treat screenshots as harmless data

Screenshots of Query Profiler, Performance Advisor, or the Logs page can expose namespaces, query filters, IDs, and literal values. Before sharing in tickets or wikis, apply redaction and access controls matching the underlying data.

## 32. Implementing with “privacy by design”

A design review for MongoDB observability should answer:

1. **What do we need to detect?** Latency, error rate, replication lag, index efficiency, or access violations?
2. **What is the minimum metric set needed?** Is full query text actually required?
3. **Which fields might contain PII/secrets?** Queries, comments, errors, labels, headers?
4. **Which systems does telemetry pass through?** Agents, collectors, brokers, SaaS, exports, backups?
5. **Who can read/export it?** Developers, DBAs, support, vendors, on-call?
6. **How long is it kept?** Does each telemetry type have its own policy?
7. **What is the deletion path?** Does deleting at the source purge every copy?
8. **Is access auditing needed?** Especially for raw profiler/audit artifacts.
9. **Is there an exception investigation channel?** When raw data is required, who approves it and how is time bounded?
10. **How do we prove controls work?** With synthetic data and controlled tests.

### Technical decision template

```text
Service: customer-api
Observability objective: query p95 + missing index detection
Primary data: aggregated latency, plan summary, docs examined
Prohibited in logs: email, phone, token, URI, raw BSON command
Command monitoring: allowlisted names and durations only
Profiler: normally disabled; short, approved investigation window
Access: on-call metrics; DBA restricted diagnostic access
Transport/storage: TLS and encryption at rest
Retention: per data-class policy
Third-party export: reviewed and approved
Owner: platform/database team
```

This is a **policy record template**, not a report claiming any real system is compliant. Every organization must populate its own policies and controls.

## 33. Testing redaction against synthetic data

A lab environment populated with synthetic values:

```javascript
use mongo_observability_lab

db.customers.insertMany([
  {
    _id: "CUS-DEMO-01",
    email: "demo-user@example.invalid",
    phone: "+00-000-000-000",
    status: "ACTIVE"
  },
  {
    _id: "CUS-DEMO-02",
    email: "another-user@example.invalid",
    phone: "+00-000-000-001",
    status: "INACTIVE"
  }
]);

db.customers.createIndex({ email: 1 });
```

**Policy test scenario**:

1. Execute a query by `email` in the lab.
2. Enable the logger/collector in a mode matching production policy, not necessarily the profiler.
3. Verify exported **events** contain no email, phone, or raw query literal.
4. Verify metrics still capture operation type and latency.
5. Inspect full exporter queues and event transforms if tooling permits.
6. Confirm the policy still holds when errors occur.

Never run these tests using real emails or passwords. Testing redaction solely with the literal string `password` can miss leaks inside query literals or nested BSON.

### Test failure modes along the exception path

A service may be safe on the happy path:

```java
logger.info("lookup ok request_id={}", requestId);
```

yet dangerous on the error path:

```java
// AVOID if throwable may contain raw queries/credentials:
logger.error("lookup failed for query={}", filter, exception);
```

Policy must cover error messages, wrapped exceptions, and error responses returned to frontends.

## 34. Level of detail during security incident investigations

Sometimes incident forensics require finer detail than routine metrics, such as tracing a malicious query by user/session ID. That is not a reason to leave all loggers on debug indefinitely.

An exception workflow:

1. Create an incident ID and define a specific investigation objective.
2. Obtain approval to collect raw diagnostic data.
3. Collect only within a **narrow window and tight scope**.
4. Use a destination/sink with restricted access.
5. Protect artifacts using encryption/controlled storage.
6. Keep secrets out of broad-audience chats or tickets.
7. Restore instrumentation to baseline when finished.
8. Handle artifacts under incident retention, legal hold, and deletion policies.

**Deep investigation capability is a controlled exception**, not a justification to collect every customer’s commands forever.

## 35. Multi-tenant systems: an extra risk

SaaS applications commonly have:

```text
tenant-01
tenant-02
tenant-03
```

A logger might record:

```json
{
  "operation": "find",
  "tenantId": "tenant-01",
  "customerEmail": "demo-user@example.invalid"
}
```

This creates a **cross-tenant data visibility** risk if dashboards expose the same log index across multiple support teams or tenant administrators.

Options:

- Avoid customer-level identifiers in logs.
- Use tenant grouping only when genuinely needed, with opaque IDs/approved labels.
- Segregate observability data by tenant or access scope if required.
- Never allow tenant users to access shared-cluster raw MongoDB profiler/log data.
- Enforce filters/permissions in the observability backend, not solely the frontend.
- Avoid placing tenant IDs in publicly shareable dashboard URLs.

**A system protecting business collections with tenant filters yet leaking that data through logs is an authorization breach**, even if database query logic is correct.

## 36. Avoid high-cardinality labels that are both costly and leaky

Metric cardinality can grow as the product of label sets:

```text
service (20 values)
 × operation (8 values)
 × customer_id (100,000 values)
 = up to 16,000,000 label combinations
```

This is a theoretical combinatorial upper bound, not necessarily the exact number of active time series in the backend.

If metrics only need to count latency by service/operation, using `customer_id` as a label wastes memory/cost and injects identifiers into the monitoring system. The same happens with `email`, `sessionId`, dynamic URL paths containing UUIDs/user IDs, or raw query strings.

### Reducing cardinality

- Use route templates instead of raw URLs, e.g., `/customers/{id}` rather than `/customers/CUS-123`.
- Use operation/query-shape categories instead of full query text.
- Use fixed error groups instead of exception messages.
- If per-tenant analysis is required, evaluate series counts and separate access controls.
- Route per-request detail into access-restricted tracing rather than stuffing it into metric labels.

## 37. Security audit logs and diagnostic logs have different retention

An abuse-of-privilege incident may require keeping audit trails long-term for compliance, while raw profiler output is only needed for a few hours to investigate a slow query. Mixing both into a single log index:

- Can retain unnecessary query literals far too long.
- Makes granting separate investigation access harder.
- Complicates setting retention per data class.
- Allows alerts and dashboards to accidentally expose event details.

Partition by **purpose and sensitivity**:

```text
Operational metrics
Diagnostic logs
Raw profiler / limited investigation data
Security audit trail
Incident evidence
```

Do not apply a single TTL policy to all data types. Where audit compliance applies, also account for integrity, immutability/edit permissions, storage location, and evidence retrieval.

## 38. Common misconceptions

| Misconception | Why is it wrong? | Better practice |
| --- | --- | --- |
| “Logs aren’t in the DB, so they hold no customer data” | Queries/filters/commands can carry PII | Classify logs as data |
| “Not logging the response is enough” | Query predicates and exceptions can still leak | Never log raw inputs/commands |
| “Server redaction protects every logger” | Drivers/apps/APM/audit have separate pipelines | Control every source |
| “Enabling `redactClientLogData` eliminates all secrets” | Redaction scope has limits | Data minimization + tests + RBAC |
| “The profiler only stores millis” | It can store commands/filters | Protect `system.profile` |
| “Profiler level 2 only adds disk usage, no other risk” | Captures many values and creates overhead | Choose minimal level/scope |
| “Level 0 turns off all slow query logs” | Diagnostic logs and profiler differ | Check each source |
| “1% sampling means PII is safe” | 1% of records still contain real PII | Never collect prohibited values |
| “Query projection deletes stored values” | It only limits output | Use collection/retention controls |
| “Encryption at rest makes dashboards harmless” | Authorized users still see plaintext after decryption | RBAC/data minimization |
| “Field encryption protects app logs” | The app has plaintext before encryption | Avoid logging at the client |
| “Hashing emails makes them anonymous” | Emails can be guessed/brute-forced | Opaque IDs/HMAC and policy |
| “Log rotation deletes logs” | Rotated files still persist | Retention/deletion |
| “Metrics are always non-sensitive” | Labels can contain IDs/emails | Low-cardinality approved labels |
| “Tracing query text is mandatory to measure latency” | Duration/shape is usually enough | Use minimal structured attributes |
| “Hiding a field in a dashboard deletes it” | Backends, exports, backups still keep it | Redact before export |
| “An Atlas monitoring role is a DB role” | UI permissions and data-plane privileges differ | Review both |
| “Permission to view the profiler means seeing all data” | Least privilege still applies | Limit scope |
| “Raw `explain()` is always safe to share publicly” | It can contain filters/literals | Sanitized output |
| “`comment` is never recorded” | It can appear in diagnostics | Keep PII out of comments |
| “After a secret-leak incident, deleting logs is enough” | Secrets may already be used/copied | Rotate/revoke + investigate |
| “One regex blocks all secrets” | Nested payloads/key variants slip through | Allowlist and avoid collecting |

## 39. Practice exercises and answers

### Exercise 1. Email leaked through filter

An application queries:

```javascript
db.customers.find({ email: "demo-user@example.invalid" });
```

The application does not log responses but logs `filter.toJson()`. Can the email be exposed?

**Answer:** Yes. The email value is inside the query literal. Do not log full BSON filters; log the operation/query shape, duration, and an opaque request ID.

### Exercise 2. Profiling level 2

A team leaves profiler level 2 on in production all week “to have enough data in case an incident happens.” What are the risks?

**Answer:** Increased overhead and capturing many commands that may contain PII; rely on baseline metrics, targeted profiling in short windows, and restricted access.

### Exercise 3. Projection

Querying `system.profile` returns only `millis` and `planSummary`. Does that mean command literals have been removed from the profile collection?

**Answer:** No. Projection only limits returned fields; stored data may still exist inside profile records.

### Exercise 4. Server redaction

`security.redactClientLogData` is enabled on the server. A Java logger prints raw `filter.toJson()`. Does the server option automatically redact the email in the Java log?

**Answer:** No. Server-side log redaction does not control logging performed by the application. Application instrumentation must be fixed.

### Exercise 5. URI

A developer adds `"Mongo URI=" + System.getenv("MONGODB_URI")` to logs for debugging. What is the issue?

**Answer:** The URI may contain username/password credentials and internal topology details. Never log raw URIs; log an approved endpoint/service label containing no secrets.

### Exercise 6. `comment`

Should you attach `comment: "user=demo-user@example.invalid"` to queries to look them up per request?

**Answer:** No. Comments can show up in diagnostics/profiler output; use a query-template ID or opaque correlation ID instead.

### Exercise 7. Histogram

A team wants to measure p95 query latency by `service` and `operation`. Should `email` be added as a metric label?

**Answer:** No. Email is unnecessary, leaks PII, and blows up label cardinality.

### Exercise 8. TLS

A central log store encrypts data at rest. Does that make it safe for dashboard users to view raw tokens in logs?

**Answer:** No. Encryption at rest protects storage, not authorized viewers reading decrypted plaintext; tokens should never enter logs in the first place.

### Exercise 9. Sampling

A log containing personal ID numbers is sampled at 0.1%. Is it still sensitive data?

**Answer:** Yes. Sampling reduces write frequency; it does not change the sensitivity of the recorded values.

### Exercise 10. Query shape

Between `filter.email="demo-user@example.invalid"` and `filterKeys=["email"]`, which is generally better suited for grouping query performance?

**Answer:** Query shape/field keys (if permitted by policy) are usually sufficient for grouping; storing literal emails is unnecessary.

### Exercise 11. Field encryption

An application uses client-side field encryption before sending data to MongoDB, yet logs plaintext email prior to encryption. Is the data protected?

**Answer:** Not on the logging path. Plaintext logging in the application must be blocked; encrypting data sent to the database does not fix the logger.

### Exercise 12. Profiler retention

`system.profile` has a capped structure. Can you guarantee all values are deleted after exactly 24 hours?

**Answer:** No. Capped size/ring-buffer behavior does not equate to an exact time-based TTL. Proper retention policies and profiler controls are needed.

### Exercise 13. Audit and profiler

Can the profiler replace security audit logs to prove all authorization operations in the system?

**Answer:** No. Both sources serve different purposes, coverage, and policies; audit capability also varies by edition/tier.

### Exercise 14. Tracing

An APM span includes `db.statement` containing a query with a customer’s phone number. Is hiding that field on the dashboard enough?

**Answer:** No. The value may already be stored in collectors/backends/backups. Drop/redact it before export and remediate copies already recorded.

### Exercise 15. Exception

An application avoids logging filters on successful queries, yet logs the raw `exception` and raw request on failure. What is the problem?

**Answer:** The error path can still leak credentials/query values. Use approved error categories and structured fields, and control exception text.

### Exercise 16. Multi-tenant metrics

A shared multi-tenant dashboard carries the label `customer_email`. What is the risk?

**Answer:** Cross-tenant data exposure and high cardinality; remove personal identifiers and scope dashboard access per policy.

### Exercise 17. Exposed secret

A password appeared in centralized logs and has been deleted from the dashboard. Should it still be rotated?

**Answer:** Yes. The secret may already have been copied or used; revoke/rotate it, audit access, and handle all log sinks/exports per incident procedure.

### Exercise 18. Slowness debugging

A query shows `docsExamined=450000`, `nReturned=1`, and `planSummary=COLLSCAN`. Do DBAs need the exact email value to know they should inspect indexes?

**Answer:** Usually no. Query shape, plan summary, and examined counts are enough to indicate investigating a missing index.

### Exercise 19. Never log raw commands

In a Java `CommandListener`, why should you avoid calling `event.getCommand().toJson()` by default and shipping it to a log platform?

**Answer:** Command BSON can carry sensitive filters, updates, pipelines, and literals. Collect only command name, outcome, duration, and approved fields.

### Exercise 20. Retention

Central log retention is 7 days, yet an alert sending raw error text over email is kept for 1 year. Is the 7-day deletion policy fully enforced?

**Answer:** No. Data persists in emails/alerts. Retention must cover all downstream copies.

### Exercise 21. Monitoring user

An exporter only needs connection counts, yet is granted the `root` database role to avoid permission errors. Is this least privilege?

**Answer:** No. Create a monitoring account with minimal permissions for approved metrics/status; never hand admin credentials to an exporter.

### Exercise 22. Diagnostic screenshot

An operator screenshots profiler output showing query literals and posts it to a large group chat. Can a screenshot be treated as harmless technical metadata?

**Answer:** No. Screenshots can expose customer or internal information; they require redaction and access controls matching the source data.

### Exercise 23. Hashing emails

A team uses SHA-256(email) as a metric label. Is absolute anonymity guaranteed?

**Answer:** No. Emails can be guessed against candidate lists; use aggregate metrics or policy-approved opaque IDs/HMACs, and evaluate cardinality.

### Exercise 24. Source deletion

A customer record has been deleted from MongoDB. Can you guarantee the email no longer exists anywhere else?

**Answer:** No. Diagnostic logs, profiler, APM, collectors, alerts, backups, and exports may still retain copies. Data lineage and lifecycle management across all systems are required.

## 40. Observability implementation checklist

### 40.1. Collection and instrumentation

- [ ] Inventory fields/commands that may contain PII, credentials, or sensitive business data.
- [ ] Do not log raw MongoDB commands, query filters, aggregation pipelines, or document payloads by default.
- [ ] Do not log connection strings, token-bearing headers, or environment variables containing secrets.
- [ ] Use a structured logging allowlist: operation, duration, outcome, approved query shape ID.
- [ ] Use opaque request IDs; never embed email/phone/user input into correlation IDs.
- [ ] Never place PII into `comment`, APM attributes, or metric labels.
- [ ] Verify both the happy path and error paths.

### 40.2. MongoDB server and profiler

- [ ] Verify server diagnostic logging configuration and available redaction capabilities.
- [ ] Do not confuse server redaction with application/driver log protection.
- [ ] Keep the profiler at minimal baseline per policy; enable detailed capture only when needed.
- [ ] Limit profiling scope/duration/sampling; never default to production level 2.
- [ ] Restrict read/control permissions on `system.profile`.
- [ ] Use projections to minimize diagnostic data emitted externally.
- [ ] After investigations, restore recorded profiling/logging configuration.
- [ ] Review access rights for Atlas Query Profiler/Logs/Performance Advisor by tier/project.

### 40.3. Log/metrics/tracing pipeline

- [ ] Redact/drop prior to shipping to collectors/vendors whenever possible.
- [ ] Keep metric labels low-cardinality without customer IDs/emails/tokens.
- [ ] Do not capture raw HTTP bodies, URL query params, or arbitrary `db.statement` strings.
- [ ] Enforce RBAC/MFA and audit exports on the observability platform.
- [ ] Enforce TLS on network paths and encryption at rest for logs/backups.
- [ ] Define clear retention across logs/profiler/traces/audit/incident artifacts.
- [ ] Establish policies covering vendors, regions, legal holds, exports, and backups.
- [ ] Monitor redaction pipeline errors, anomalous volume spikes, and secrets detection.

### 40.4. Operations and incident response

- [ ] Maintain a performance investigation runbook: metrics → shape → targeted profiling.
- [ ] Establish temporary approval workflows when raw diagnostic data is required.
- [ ] Maintain rotation/revocation procedures if secrets appear in logs.
- [ ] Never paste raw profiler/exception output into broad-audience tickets or chats.
- [ ] Test controls on synthetic data, including nested payloads and error paths.
- [ ] Maintain data lineage across agents, collectors, dashboards, alerts, exports, and backups.
- [ ] Periodically review log configuration, access rights, and retention drift.

## 41. Summary

**Logs, the profiler, and monitoring systems are data assets that must be protected**, not merely technical utilities. MongoDB diagnostic logs and `system.profile` can carry query, command, and namespace details, and sometimes **literal customer data values**. Java driver command monitoring, application logging, APM/tracing, and metric labels can further replicate those values outside MongoDB.

The most effective protection strategy begins by **not collecting unnecessary data**. For most performance issues, aggregate metrics, query shapes, latency, index/plan statistics, and opaque correlation IDs suffice. When detailed profiling is necessary, enable it only within an approved scope and window, restrict read access to `system.profile`, limit raw exports, and return settings to baseline.

Redaction measures such as `security.redactClientLogData` (where supported by the deployment), masking, TLS, encryption at rest, and RBAC are all valuable, yet **none replaces the others**. A server with redaction enabled cannot fix a Java logger emitting `filter.toJson()`. An encrypted log can still expose emails through an overly permissive dashboard. A secret deleted from logs still needs rotation if it was exposed.

A well-observable MongoDB system must ensure **enough signal to troubleshoot incidents, the least sensitive data possible, access restricted solely to authorized personnel, and data purged according to a defined lifecycle**.

### Official references to check by version

- [MongoDB Manual — Database Profiler](https://www.mongodb.com/docs/manual/tutorial/manage-the-database-profiler/)
- [MongoDB Manual — `db.setProfilingLevel()`](https://www.mongodb.com/docs/manual/reference/method/db.setProfilingLevel/)
- [MongoDB Manual — `db.getProfilingStatus()`](https://www.mongodb.com/docs/manual/reference/method/db.getProfilingStatus/)
- [MongoDB Manual — Log Messages](https://www.mongodb.com/docs/manual/reference/log-messages/)
- [MongoDB Manual — Configuration File Options](https://www.mongodb.com/docs/manual/reference/configuration-options/)
- [MongoDB Manual — Role-Based Access Control](https://www.mongodb.com/docs/manual/core/authorization/)
- [MongoDB Java Sync Driver — Monitor Commands](https://www.mongodb.com/docs/drivers/java/sync/current/monitoring-and-logging/monitoring/)
- [MongoDB Atlas — Monitoring and Alerts](https://www.mongodb.com/docs/atlas/monitoring-alerts/)
