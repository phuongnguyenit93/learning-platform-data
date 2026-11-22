# Separating Business Logs in Java: Routing and Log Classification

## 1. What is business log separation, and why do it?

In a Java application, many different messages can appear together in the logs:

~~~text
INFO  HTTP POST /orders returned 201 in 43 ms
INFO  ORDER_PLACED order_id=O-42 amount_minor=125000 currency=VND
WARN  Database connection pool utilization is high
INFO  ORDER_PAID order_id=O-42 payment_method=card
ERROR Payment provider timed out on retry attempt 2
~~~

The first, third, and fifth lines describe **technical operations**: HTTP, database, timeout, retry. The second and fourth lines describe **business events**: an order has been recorded, a payment has been confirmed. If every line goes into the same channel without classification, readers and monitoring systems can easily confuse business state with infrastructure symptoms.

**Business log separation** means intentionally tagging the event category, then controlling how logs are written, formatted, shipped, searched, and retained based on that category. The goal is not necessarily to create multiple files on disk. A system can still emit all logs to stdout as JSON while logically separating channels via a category field so that the collector or backend applies separate policies.

After this lesson, you should be able to distinguish between business logs, technical logs, and audit/security logs; choose an appropriate separation mechanism; configure routing without duplicate writes; and understand the reliability limits of logs for business state.

## 2. Classify before choosing an appender

| Category | Question answered | Examples | Characteristics |
| --- | --- | --- | --- |
| BUSINESS | What meaningful event in the business process just occurred? | ORDER_PLACED, PAYMENT_CONFIRMED, SHIPMENT_DISPATCHED | Stable event names with identifiers and outcomes, supporting business journey queries |
| TECHNICAL / APPLICATION | How is the application operating? | HTTP 500, retry, SQL timeout, cache miss, closed connection | Supports operations, debugging, performance measurement, and incident analysis |
| SECURITY | What notable security activity occurred? | LOGIN_FAILED, access denied, anomalous access detected | May require separate access control, monitoring, and retention |
| AUDIT | Who performed what change, when, and on which object? | POLICY_CHANGED, ROLE_ASSIGNED, MANUAL_APPROVAL | May have dedicated requirements for integrity, provenance, and history |
| ACCESS | Which request was served, and what was the HTTP outcome? | GET /orders/42 200 35ms | Usually emitted by the web server or gateway, useful for traffic analysis |

A single event can serve multiple purposes at the same time. For example, changing an account's permissions is both a business action and audit-relevant. Identify the **source of truth and retention policy** for each purpose; do not assume a single INFO log line is complete audit evidence.

### Log level is not log category

DEBUG, INFO, WARN, and ERROR express severity/verbosity, **not whether an event is business or technical**.

- A successful ORDER_PLACED is usually INFO and belongs to BUSINESS.
- An ORDER_REJECTED due to business rules may be INFO or WARN depending on policy, and still belongs to BUSINESS.
- A SQL timeout at ERROR is TECHNICAL, even though it affects the ordering flow.
- A permission change at INFO can belong to AUDIT/SECURITY even though no error occurred.

Do not route all INFO logs to business.log and all ERROR logs to technical.log: both categories span multiple log levels.

## 3. Defining criteria for a business event

A good business event describes an **established event** in the domain, not merely an action being attempted. Distinguish between:

~~~text
ORDER_PAYMENT_STARTED        # operation started, no final result yet
ORDER_PAYMENT_CONFIRMED      # system confirmed payment
ORDER_PAYMENT_REJECTED       # business rule rejected payment
PAYMENT_PROVIDER_TIMEOUT     # technical error in payment integration
~~~

Depending on the design, the first event may be a valid business step; what matters is that the event name does not give a false impression of committed state. For example, if a database transaction rolls back, an "ORDER_PAID" line written right before the commit call cannot be treated as proof that the payment definitely succeeded.

**Recommended data structure for business logs:**

~~~json
{
  "timestamp": "2026-11-10T02:30:00Z",
  "category": "BUSINESS",
  "event_type": "ORDER_CONFIRMED",
  "schema_version": 1,
  "event_id": "evt-7d6e",
  "order_id": "O-42",
  "outcome": "SUCCESS",
  "service": "order-service",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "message": "Order confirmed"
}
~~~

This is a **sample schema**, not the default output of Java/Logback. Meaning of each field:

| Field | Purpose | Notes |
| --- | --- | --- |
| timestamp / occurred_at | Time the event was determined | Use UTC with an explicit timezone; distinguish event time from log collection time |
| category | Group used for routing, e.g., BUSINESS | Use a finite, governed set of values |
| event_type | Stable event name used for metrics and queries | Prefer constants; do not generate new names per order or user |
| schema_version | Event structure version | Increment when field contract changes affect consumers |
| event_id | Unique identifier of the event | Useful for detecting duplicates in the pipeline if generated properly |
| entity_id / order_id | Related business entity | Only log identifiers permitted for exposure by data policy |
| outcome | SUCCESS, REJECTED, FAILED, etc. | Distinguish business rejections from technical failures |
| service | Emitting service | Must be consistent across replicas |
| trace_id / request_id | Links to technical logs for the same execution | Trace ID only represents a distributed trace when context is propagated properly |
| message | Human-readable text | Should not be the sole field used for classification |

Not every system needs all of these fields. Choose a schema that fits your requirements, but keep field names and data types consistent; when logging as JSON, represent amounts as numbers in explicit minor units and currencies as ISO codes rather than stuffing everything into a localized text string.

## 4. Ways to separate business logs

There are four common approaches; they can be combined.

### 4.1. By logger/category name

Create a dedicated logger for business events:

~~~java
// Snippet when SLF4J and a supported backend are already available.
private static final org.slf4j.Logger BUSINESS_LOG =
    org.slf4j.LoggerFactory.getLogger("com.example.business");

private static final org.slf4j.Logger APP_LOG =
    org.slf4j.LoggerFactory.getLogger(OrderService.class);
~~~

Call BUSINESS_LOG when the business logic produces a defined event. Call APP_LOG when explaining technical flow, handling exceptions, logging latency, or debugging. Then configure the backend so that the com.example.business logger routes to a dedicated appender.

Pros: easy to understand, relatively simple to configure, well-suited to a single application. Limitations: only events sent to that logger reach the right channel. A technical error line accidentally logged via BUSINESS_LOG will still be misclassified. Conventions and code reviews are required.

### 4.2. By marker

SLF4J provides Marker to tag events without creating a separate logger:

~~~java
// SLF4J snippet; not yet a standalone program.
org.slf4j.Marker marker =
    org.slf4j.MarkerFactory.getMarker("BUSINESS");

logger.info(marker, "event_type={} order_id={}",
    "ORDER_CONFIRMED", "O-42");
~~~

A Marker attaches semantic metadata to a log event. The logging backend must be configured with a filter or routing rule that reads the marker for separation to actually occur; merely declaring a Marker does not create a business.log file. One backend may support MarkerFilter, while another has a different API or filter mechanism.

### 4.3. By structured field/category

All events are emitted as JSON lines containing category=BUSINESS/TECHNICAL/AUDIT. The collector or backend splits streams, indexes, or retention policies based on this field.

~~~text
Java services
   └─ stdout JSON lines
         └─ container runtime
               └─ collector parses category
                      ├─ BUSINESS → index / stream business
                      ├─ TECHNICAL → index / stream application
                      └─ AUDIT → separate pipeline and permissions
~~~

This is often the easiest approach to operate in containers: it reduces the need for shared files and fits centralized search. However, if the collector is misconfigured, fails to parse, or receives an event without a category, you need a fallback/quarantine path along with metrics to avoid silent log loss.

### 4.4. By target appender/handler

An application can send BUSINESS logs to a dedicated file, broker, syslog, or appender, and TECHNICAL logs to another console or file. With Java Util Logging, use Logger + Handler; with Logback/Log4j 2, use logger configuration, additivity, and appender references. This approach fits when physical separation is required, but you must manage rotation, file permissions, shutdown, and sink failures.

**Never automatically create a separate file per order_id or user_id**: the number of targets grows with cardinality, causing excessive files/appenders, open file handles, and operational overhead. Logging the identifier inside the event and filtering in the backend is far more flexible.

## 5. Standalone Java 17 example: BUSINESS and TECHNICAL as two separate channels

The example below uses only **java.util.logging** built into the JDK. Two loggers with different names and two Handlers receive separate events. ByteArrayOutputStream represents two sinks for testing routing, making output deterministic and requiring no file write permissions.

**File: BusinessLogRoutingDemo.java**

~~~java
import java.io.ByteArrayOutputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class BusinessLogRoutingDemo {
    private static final Logger BUSINESS =
            Logger.getLogger("example.business");
    private static final Logger TECHNICAL =
            Logger.getLogger("example.technical");

    private static StreamHandler newHandler(OutputStream target) {
        StreamHandler handler = new StreamHandler(target, new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getMessage() + System.lineSeparator();
            }
        });
        handler.setLevel(Level.ALL);
        return handler;
    }

    private static void connect(Logger logger, Handler handler) {
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);
        logger.addHandler(handler);
    }

    public static void main(String[] args) {
        ByteArrayOutputStream businessBytes = new ByteArrayOutputStream();
        ByteArrayOutputStream technicalBytes = new ByteArrayOutputStream();

        StreamHandler businessHandler = newHandler(businessBytes);
        StreamHandler technicalHandler = newHandler(technicalBytes);
        connect(BUSINESS, businessHandler);
        connect(TECHNICAL, technicalHandler);

        try {
            TECHNICAL.info("GET /orders status=200");
            BUSINESS.info(
                    "event=ORDER_ACCEPTED order_id=O-42 result=SUCCESS");
            TECHNICAL.warning("payment latency_ms=45");
            BUSINESS.info(
                    "event=ORDER_PAID order_id=O-42 result=SUCCESS");
        } finally {
            businessHandler.flush();
            technicalHandler.flush();
            BUSINESS.removeHandler(businessHandler);
            TECHNICAL.removeHandler(technicalHandler);
            businessHandler.close();
            technicalHandler.close();
        }

        System.out.println("=== BUSINESS ===");
        System.out.print(
                businessBytes.toString(StandardCharsets.UTF_8));
        System.out.println("=== TECHNICAL ===");
        System.out.print(
                technicalBytes.toString(StandardCharsets.UTF_8));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 BusinessLogRoutingDemo.java
java BusinessLogRoutingDemo
~~~

**Exact stdout from the program:**

~~~text
=== BUSINESS ===
event=ORDER_ACCEPTED order_id=O-42 result=SUCCESS
event=ORDER_PAID order_id=O-42 result=SUCCESS
=== TECHNICAL ===
GET /orders status=200
payment latency_ms=45
~~~

### Example analysis

- BUSINESS and TECHNICAL are **two differently named loggers** with their own Handlers. There is no condition guessing the event category from the log level.
- setUseParentHandlers(false) stops events from propagating to parent logger Handlers, avoiding duplicate lines on the default console. In JUL, setUseParentHandlers controls whether a LogRecord is forwarded up to the parent.
- StreamHandler is buffered; flush() ensures buffered data in the handler is written to ByteArrayOutputStream before the program prints both sections. Thus no lines are missing even though Java's StreamHandler does not auto-flush after every record.
- Level.INFO allows INFO and WARNING events to be emitted on each logger; both Handlers at Level.ALL do not filter anything further.
- The Formatter prints only the message and a newline, with no variable timestamp or thread name, so the example output can be compared verbatim.
- ByteArrayOutputStream acts as a sink for learning and testing, **not a production log destination**. For real services, use a backend-supported Handler/Appender and manage rotation, collectors, and lifecycle.

If you omit setUseParentHandlers(false), JUL can forward events to parent/root Handlers and the log will appear **an extra time at another destination**. This is a common mistake when separating loggers without controlling propagation. The example does not prove that any distributed system can deliver both channels exactly once; exactly-once delivery depends on multiple transport and storage layers.

### Extension: routing based on event type

In exercises, you can create a BusinessEventType enum and an emitBusinessEvent(...) wrapper that validates inputs before logging. If business data validation is needed, perform it in the domain/application layer and pass an immutable record to the logger; do not put all business rules inside a custom Handler.

## 6. Logback: separating appenders by logger and additivity

For projects using SLF4J + Logback, create a logger with a fixed name com.example.business. Example configuration in **src/main/resources/logback.xml**:

~~~xml
<configuration>
    <appender name="BUSINESS_FILE"
              class="ch.qos.logback.core.FileAppender">
        <file>logs/business.log</file>
        <append>true</append>
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level category=BUSINESS %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="TECH_CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.business"
            level="INFO" additivity="false">
        <appender-ref ref="BUSINESS_FILE"/>
    </logger>

    <root level="INFO">
        <appender-ref ref="TECH_CONSOLE"/>
    </root>
</configuration>
~~~

**How it works:**

1. The com.example.business logger and its child loggers use BUSINESS_FILE according to hierarchy configuration.
2. additivity="false" stops events from propagating from the business branch up to root, preventing business events from also entering TECH_CONSOLE.
3. All other loggers continue using root and TECH_CONSOLE.
4. Level.INFO on the business logger does not mean every INFO log is business; the logger name is the routing criterion.

Corresponding SLF4J call example:

~~~java
// Snippet requires slf4j-api and a compatible Logback backend.
private static final org.slf4j.Logger BUSINESS_LOG =
    org.slf4j.LoggerFactory.getLogger("com.example.business");

BUSINESS_LOG.info("event_type={} order_id={} result={}",
    "ORDER_CONFIRMED", "O-42", "SUCCESS");
~~~

The XML snippet and SLF4J call are examples **for an application with the appropriate dependencies**, not a JDK-only Java program like in Section 5. If real code creates loggers by class, e.g., LoggerFactory.getLogger(OrderService.class), the logger name is the class/package name and **does not automatically route to the com.example.business branch**. You must call the right category logger or design package names accordingly.

### Is FileAppender mandatory?

No. FileAppender helps illustrate **physical separation**; in Docker/Kubernetes, writing logs/business.log inside an image/container can make collection harder or cause log loss when a Pod is deleted. You can choose multiple ConsoleAppenders tagged with separate categories or use a single JSON console appender and route at the collector. If you do write files, ensure the directory is writable and configure rotation, retention, and an appropriate forwarder.

### Additivity and logger naming pitfalls

If both a dedicated appender on the business logger and an appender on root are configured, default additivity can cause a single event to appear in both. Setting additivity="false" isolates it, but also means business events **do not pass through the root appender**. If you need both a copy in the general operational channel and a dedicated copy for business, configure two explicit AppenderRefs intentionally rather than duplicating by accident.

Additionally, a business-named logger is easy to misuse in code. For large systems, wrap it in an emitBusinessEvent API or enforce category conventions to reduce the chance of developers accidentally sending SQL errors to the business log.

## 7. Log4j 2: dedicated logger, Filter, and RoutingAppender

Log4j 2 provides LoggerConfig, AppenderRef, Filter, and routing mechanisms. When splitting into two fixed channels, a dedicated logger is usually simple enough.

Example **src/main/resources/log4j2.xml** for Log4j 2 Core:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <File name="BUSINESS_FILE"
              fileName="logs/business.log">
            <PatternLayout pattern="%d{ISO8601} %-5level category=BUSINESS %msg%n"/>
        </File>
        <Console name="TECH_CONSOLE" target="SYSTEM_OUT">
            <PatternLayout pattern="%d{ISO8601} %-5level %logger - %msg%n"/>
        </Console>
    </Appenders>

    <Loggers>
        <Logger name="com.example.business"
                level="info" additivity="false">
            <AppenderRef ref="BUSINESS_FILE"/>
        </Logger>
        <Root level="info">
            <AppenderRef ref="TECH_CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
~~~

This is a **Log4j 2** configuration, not for Logback. The idea is the same as in the Logback section: the business logger goes to a separate file, root sends the remaining loggers to the console, and additivity="false" prevents propagation to root.

If you need to separate by **Marker** or context attributes instead of logger name, Log4j 2 provides MarkerFilter and RoutingAppender. A Filter can return ACCEPT, DENY, or NEUTRAL depending on the stage. RoutingAppender dispatches events to target appenders based on a route key; check the exact configuration syntax for your version and test the case where a route key does not exist.

### When to use dynamic routing?

Routing by a finite set of categories such as BUSINESS/TECHNICAL/AUDIT can be reasonable. Dynamic routing by customer ID, order ID, or user ID is usually dangerous because it creates many targets or files: high cardinality consumes resources and complicates rotation. If you only need to filter by order_id, include that field in the log and filter in the centralized backend.

### Markers do not isolate data on their own

An event carrying a BUSINESS Marker can still be written by the root appender if filters and additivity do not restrict the destination. When storing sensitive data, merely attaching a marker is **not sufficient** to guarantee access isolation. Verify the full path to the sink, ACL/index, exporter, and retention.

## 8. Which approach should you choose in Spring Boot?

Spring Boot typically uses SLF4J; the backend is determined by dependencies (Logback by default when using starter logging). When advanced backend configuration is needed, use **logback-spring.xml** or **log4j2-spring.xml** matching the active backend.

Example of reducing noisy technical logs while keeping business logs:

**application.properties**

~~~properties
logging.level.root=WARN
logging.level.com.example.business=INFO
~~~

This is a **level** configuration, not a sink-separation configuration. It allows the business logger to emit INFO even while root is at WARN, provided the path to the appender and other filters allow it. If you want business logs to go to a separate destination, configure appenders/logger categories in XML or route at the collector.

If application.properties has:

~~~properties
logging.file.name=/var/log/app/application.log
~~~

this configures the output file name via Boot's built-in mechanism and **does not automatically split business logs into a separate file**. When defining custom appenders in XML, ensure any properties used by those appenders are wired correctly.

### Containers usually favor logical separation

With multiple replicas, you can emit console JSON logs containing category and event_type, then route via a collector:

~~~json
{"category":"BUSINESS","event_type":"ORDER_CONFIRMED","order_id":"O-42","service":"orders"}
{"category":"TECHNICAL","event_type":"HTTP_REQUEST_DONE","status":201,"service":"orders"}
~~~

The backend can apply different indexes/streams and retention policies—for example, keeping BUSINESS searchable longer than TECHNICAL if requirements justify it. Here, separation does not depend on multiple containers writing to the same logs/business.log file. Of course, the collector/backend must enforce access control and field parsing; a JSON line alone does not provide durability.

## 9. Do not confuse business logs with domain events or an audit ledger

This is the most important part when bringing business log separation into a real system.

### 9.1. Observational logs differ from the transactional source of truth

Suppose the application does:

~~~java
// Incorrect illustration of transactional guarantees: not a standalone program.
businessLogger.info("event_type=ORDER_PAID order_id={}", orderId);
repository.markPaid(orderId);
~~~

If markPaid fails or the transaction rolls back, the log line claiming the order was paid still exists. Reversing the order does not turn a log into a guaranteed record either:

~~~java
repository.markPaid(orderId);
businessLogger.info("event_type=ORDER_PAID order_id={}", orderId);
~~~

A crash can still occur between the two calls; the database write succeeds, but the log never reaches the sink. With asynchronous processing or collectors, a successful logger call still does not guarantee the event was persisted in the backend.

**If an event must be published/stored atomically with a transaction**, use a proper durability pattern such as the transactional outbox: save both the state and the outbox record in the same database transaction, then have a publisher forward outbox records to a broker with idempotent consumers. This is a business/durability mechanism, **not something a FileAppender or INFO logger can guarantee**.

### 9.2. Audit logs have their own requirements

An audit trail may require actor identity, action, target object, request origin, timestamp, outcome, tamper-resistance, and a retention policy. Simply splitting out an audit.log file does not satisfy all of these requirements. You must establish a trusted audit system and protect the data according to organizational policy.

If the system requires legal evidence, integrity guarantees, or critical financial records, build an audit/event store with dedicated durability, access control, and verification mechanisms. Do not reuse best-effort business logs as the sole source for financial settlement or reconciliation.

### 9.3. Detecting duplicate events

In systems with retries, redelivery, or multiple sinks, the same business event can be recorded more than once. event_id helps reconcile duplicate records. However, event_id is only useful if it is generated deterministically/stably **for the same event**, rather than generating a new ID on every retry and treating it as a different event. Downstream consumers should still apply deduplication/idempotency rules when needed.

In addition to event_id, you can use correlation_id/causation_id to link a business chain, but define each field's meaning and lifecycle clearly and avoid conflating them with trace_id.

## 10. Proposing a clear business log schema

Before implementing, design a minimal event contract:

~~~text
category       = BUSINESS
event_type     = ORDER_CONFIRMED
event_version  = 1
event_id       = evt-7d6e
entity_type    = ORDER
entity_id      = O-42
outcome        = SUCCESS
service        = order-service
occurred_at    = 2026-11-10T02:30:00Z
trace_id       = ...
attributes     = {currency: "VND", amount_minor: 125000}
~~~

These examples are for illustration only. When writing JSON, choose proper numeric/boolean/null types; do not coerce every field into a string if the backend needs numeric comparisons.

### Event names

Prefer stable past-tense names or achieved states, such as ORDER_CONFIRMED, PAYMENT_FAILED, SHIPMENT_CREATED. Avoid embedding IDs in event_type like ORDER_CONFIRMED_O-42, as that explodes cardinality and breaks aggregation.

### Success and failure events

A valid business rejection is not necessarily an exception:

~~~json
{"category":"BUSINESS","event_type":"ORDER_REJECTED","entity_id":"O-42","reason_code":"OUT_OF_STOCK","outcome":"REJECTED"}
~~~

Database connection errors or gateway timeouts are technical; you may record an additional business outcome once the system determines the business decision, but avoid emitting ORDER_REJECTED when the payment result is actually UNKNOWN. Setting outcome must follow the actual state machine rather than guessing from a network error.

### Log only permitted attributes

Never put full card numbers, passwords, access tokens, session cookies, government IDs, health information, or payloads containing PII into business logs. Even order_id, customer_id, and user_id can be indirect identifiers; control their purpose and access permissions. Use internal/pseudonymous IDs per policy and mask/redact sensitive data before it reaches the logger.

## 11. Log routing in a distributed environment

An order request may traverse an API gateway, order-service, payment-service, and inventory-service:

~~~text
HTTP request
    |
    v
order-service (BUSINESS: ORDER_PLACED)
    |             \
    |              \-- TECHNICAL: request latency / DB query
    v
payment-service (BUSINESS: PAYMENT_CONFIRMED)
    |             \
    |              \-- TECHNICAL: gateway retry / circuit breaker
    v
inventory-service (BUSINESS: STOCK_RESERVED)
                  \
                   \-- TECHNICAL: cache miss / API error
~~~

To correlate logs across services, use trace_id/span_id from a valid tracing context and business correlation_id when needed. **Trace ID does not replace entity_id**: a single order can span multiple traces, and a single trace can contain multiple business operations.

### MDC and context propagation

SLF4J's MDC can carry request_id, trace_id, and safe attributes for logging. However, MDC is typically thread-bound; when using ExecutorService, CompletableFuture, or reactive pipelines, propagate context across the appropriate scope and clean up/restore in finally. Do not assume MDC automatically crosses new threads or HTTP calls.

Similarly, if using Log4j 2 Thread Context, verify capture/restore mechanisms in async tasks. With OpenTelemetry, use proper instrumentation and context propagation so trace IDs in business and technical logs belong to the same trace.

### Separating retention and access control by category

Business logs may remain useful for journey analysis longer than technical DEBUG logs; security/audit logs may require stricter viewing permissions. Policies must stem from purpose and legal/operational requirements—there is no single retention period for all applications.

If you only separate files locally while still shipping everything into a single index without separate permissions, data isolation is incomplete. Check the entire path from code to appender, stdout/container runtime, collector, backend, and end users.

## 12. Performance, reliability, and routing risks

### 12.1. Cost of logging

Business events have high observability value, but synchronous logging and complex JSON formatting can impact latency. Parameterized logging reduces message-building cost when a level is disabled, but it does not snapshot mutable objects consistently and does not prevent an appender from blocking.

When using an async appender, understand queue capacity, queue-full policy (block/drop/fallback to synchronous depending on provider), flush, and shutdown behavior. Critical business events **should not rely solely on a non-durable log queue** for business guarantees.

### 12.2. Routing rules must have a fallback branch

When category is missing, misspelled, or a new event_type is undeclared, define whether to keep it in the technical/default stream, route to quarantine, or raise an error. Do not silently drop unmatched records without metrics or alerts, especially if teams rely on the business channel for incident detection.

### 12.3. Avoiding logging recursion

A custom Handler/Appender that logs back into the same sink can trigger infinite recursion and a stack overflow or queue overflow. Diagnose sink errors through the framework's status/error-handling mechanism rather than calling back into the failing pipeline without safeguards.

### 12.4. One event does not mean one copy

Duplicates caused by logger additivity are configuration bugs you can fix. However, async forwarding, collector retries, or broker delivery can create duplicate records in the backend even when the application called the logger only once. Do not claim end-to-end exactly-once delivery without transactional/deduplication mechanisms across the entire path.

## 13. Testing business log separation

A useful test suite should verify **correct destination, correct schema, and correct data** together:

| Test case | Generated data | Expectation |
| --- | --- | --- |
| Standard BUSINESS write | ORDER_CONFIRMED | Only business sink when intentionally isolated; required event_type/entity_id present |
| TECHNICAL write | HTTP_REQUEST_DONE or exception | Only technical sink; does not leak into business |
| Mixed levels | Business INFO, Technical WARN/ERROR | Routed by category/logger, not guessed from level |
| Parent logger | Business logger with own appender and root appender | No accidental duplicates from additivity |
| Missing category | Event without category | Observable default/quarantine behavior applied |
| Concurrency | Multiple requests and thread pools | No mixed correlation_id/MDC, no corrupted records |
| Business retry | Same operation retried | event_id convention and deduplication reflect logic accurately |
| Sink failure or full queue | Log backend temporarily unavailable | Observe retry/drop/backpressure; do not confuse with transaction |
| Security | Payload containing sensitive data | Redaction/allowlist strips disallowed data |
| Container restart | Pod/container recreated | Local logs may be lost; collector/backend retains per policy |

For the Java 17 example in Section 5, basic testing means compiling, running, and comparing full stdout. If TECHNICAL events leak into the BUSINESS section, or BUSINESS events appear twice, inspect Handlers, logger hierarchy, and propagation.

When using Logback/Log4j 2, run integration tests with the **exact configuration file and provider that will be deployed**. A test that only mocks the Logger API without loading real appenders cannot prove routing works. In particular, test environments may load logback-test.xml or log4j2-test.xml differently from production.

## 14. Common issues and troubleshooting

| Symptom | Possible cause | Remediation |
| --- | --- | --- |
| business.log full of SQL errors | Using INFO/ERROR as category criteria, or calling the wrong business logger | Separate categories in code/domain; use clear logger names/markers |
| BUSINESS appears in both dedicated file and console | additivity propagating events to root | Inspect logger hierarchy; set additivity=false when isolation is desired |
| No business logs while technical logs work | Wrong logger name, wrong config file, level/filter blocking, broken appender | Verify active runtime backend and trace the event path |
| Logs only exist locally inside container | File appender not collected | Use console/collector, volume + forwarder if needed, backend retention |
| Missing ORDER_CONFIRMED after crash | Log not flushed, emitted before/outside transaction, queue dropped | Distinguish observational logs from outbox/event store for durability |
| Multiple ORDER_CONFIRMED for same order | Retries, unclear dedup, duplicate appender/collector delivery | Check event_id, operation_id, delivery mechanics, and additivity |
| Business log missing trace_id | Context not propagated, no active span | Check instrumentation, MDC, and async boundaries |
| Logs expose customer data | Logging entire entity/payload/exception | Use field allowlists, mask data, and test redaction |
| JSON logs fail to parse | Improper newline/quote escaping, inconsistent schema | Use a standard JSON encoder and test with the parser |
| Business log storage explodes | One file per entity, duplicate logs, or overly verbose events | Reduce route cardinality, log meaningful events, configure retention |

### Practical diagnostic workflow

1. Locate the exact event in code and determine its category by business meaning.
2. Identify the actual runtime logger/backend (JUL, Logback, Log4j 2) rather than guessing from dependency names.
3. Trace the event through logger → level/filter → additivity → appender → collector → backend.
4. Check which destinations receive the event, whether duplicates or drops occur, and whether the backend parses the schema properly.
5. For business events tied to transactions, pinpoint exactly when state is committed and what durability is required.
6. Verify access permissions and sensitive data handling across **every** channel the event can traverse.

## 15. Practice exercises

**Exercise 1 – Changing JUL routing policy.** Starting from BusinessLogRoutingDemo.java, add a TECHNICAL.severe("database unavailable") call. Predict and confirm that it appears only under TECHNICAL. Then intentionally remove setUseParentHandlers(false), observe event propagation to parent handlers under your current JUL configuration, and explain why this is a propagation issue.

**Exercise 2 – Logback logger naming.** With the configuration in Section 6, use LoggerFactory.getLogger("com.example.business") and LoggerFactory.getLogger("com.example.OrderService") to emit two different events. Inspect business.log and the console. Try setting additivity=true and explain the unwanted duplicates.

**Exercise 3 – Structured logging.** Design three events—ORDER_PLACED, ORDER_REJECTED, and PAYMENT_CONFIRMED—as JSON lines with category, event_type, event_id, entity_id, outcome, and timestamp. Write a schema check verifying every event has all required fields and contains no tokens or sensitive payloads.

**Exercise 4 – Events and transactions.** Diagram a transaction updating ORDER_PAID, the logger call, the DB commit, and points where crashes can occur. Identify cases where the log appears despite a transaction rollback or where state commits without a log. Propose an outbox design when reliable event delivery is required.

**Exercise 5 – Kubernetes.** Given two Java replicas emitting console JSON logs with a collector splitting BUSINESS and TECHNICAL categories, simulate the BUSINESS backend becoming temporarily unavailable; identify where retry/buffer/drop behavior is configured, how to measure it, and how to trace event_id when duplicate deliveries arrive.

## 16. Key takeaways

Business log separation starts with **classifying event meaning** before choosing loggers, markers, fields, filters, and appenders. INFO/WARN/ERROR levels do not replace categories. A Java application can separate logs via logger names and additivity in Logback/Log4j 2, or via Logger/Handler in JUL; in containers, separating by JSON fields at the collector is usually easier to manage than managing multiple local files.

Business logs help observe business journeys, but they **do not guarantee transactions, exactly-once delivery, or durable storage**. For critical business flows, design an outbox/audit store matching your requirements, keep event_id and schemas stable, prevent sensitive data leaks, and test the full log pipeline from application to backend.

### References

- Oracle Java 17 – Logger (logger name, handler inheritance): https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html
- Oracle Java 17 – Handler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html
- Oracle Java 17 – StreamHandler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/StreamHandler.html
- SLF4J Marker API: https://www.slf4j.org/apidocs/org/slf4j/Marker.html
- Logback – Architecture, logger hierarchy, additivity: https://logback.qos.ch/manual/architecture.html
- Logback – Configuration: https://logback.qos.ch/manual/configuration.html
- Log4j 2 – Filters: https://logging.apache.org/log4j/2.x/manual/filters.html
- Log4j 2 – Delegating Appenders/Routing: https://logging.apache.org/log4j/2.x/manual/appenders/delegating.html
- Spring Boot – Logging: https://docs.spring.io/spring-boot/reference/features/logging.html
