# Avoiding Duplicate Logs in Java Logging: Proper Routing Without Recording Events Twice

## 1. What Is a Duplicate Log?

A **duplicate log** occurs when *the same log event* unexpectedly appears multiple times at the same observation destination. For example, there is only **a single call** to `log.info("Đã tạo đơn hàng id={}", 42)`, yet the console prints two identical lines; or the application emits a single log event, while the centralized logging system stores it as two separate records.

In Java, duplicates can occur across multiple layers:

- **At the application layer:** an event is forwarded to the same appender/handler twice through the logger hierarchy.
- **At the appender configuration layer:** two different paths lead to the same sink, such as a file referenced both directly and via an `AsyncAppender`.
- **At the bridge/provider layer:** a forwarding bridge or logging initialization lifecycle is configured multiple times, creating unintended routing paths.
- **At the collection/export layer:** the same event is ingested through two independent pipelines, such as collecting stdout while also receiving an OTLP copy.
- **At the storage/query layer:** retries, re-reading files, duplicate ingestion, or queries merging multiple sources can cause a single event to appear multiple times.

**Not every event present in two places is a bug.** An `ERROR` appearing **once in the console** and **once in a file** may be completely aligned with operational requirements. A problem arises when the same destination receives two unintended copies, or when the centralized backend treats two copies of the same event as two independent events.

Examples to distinguish:

| Scenario | Is It a Duplicate? | Why |
| --- | --- | --- |
| One `log.info`, terminal displays two identical lines | Very likely | The same sink receives the event twice |
| One event written once to console, once to rolling file | Not necessarily | Two different destinations may be intentional |
| Two independent requests both log `GET /health 200` | Insufficient evidence | Identical text, but they may be two real events |
| One event from stdout and the same event from OTLP go into one index | Yes, if unintentional | Two collection paths create two records for the same logical event |
| One exception logs a message and multiple stack trace lines | No | A multi-line stack trace can still be **one** log event |
| Same message in two different spans/requests | Not automatically | Must correlate event identity, timestamp, and context |

Consequences can include increased storage costs, alert noise, inaccurate error/transaction counts, difficulty finding root causes, as well as misleading operators into thinking a business operation ran twice.

## 2. Path Model of a Log Event

```text
                    [One logger.info() call]
                                |
                       Logger effective level
                                |
                  (allowed to create LogEvent)
                                |
                        Logger routing
                    /           |           \
           Child logger   Parent logger   Other bridge?
                    \           |
                      additivity
                         |
                  Appender references
                    /             \
                Console        AsyncAppender
                                |      |
                              Queue   FileAppender
                                        |
                               File/stdout/network
                                        |
                        Collector / log shipper
                              /        \
                          exporter A  exporter B
                                \       /
                                 Backend
```

There are two separate questions to answer:

1. **How many times was the same log event sent to each appender/sink?** This is a question at the Java logging framework layer.
2. **How many times was the same log event recorded by the collector/backend?** This is a question at the observability pipeline layer.

Simply seeing two lines in a dashboard is not enough to conclude a bug in the Java logger: Java might have written only once, while two collectors are reading the same file. Conversely, adding filters/dedup at the backend can mask a real routing bug in the application.

A sound diagnosis goes **from the source of emission to the destination**: determine the number of log calls, the number of times each appender receives the event, the number of stdout/file lines, and the number of ingested records.

## 3. Most Common Cause: Logger Hierarchy and Additivity

In Logback and Log4j 2, loggers are organized in a **name tree**. For example:

```text
ROOT
  └─ com
      └─ example
          └─ orders
              └─ OrderService
```

For the logger `com.example.orders.OrderService`, an enabled event can traverse appenders attached to the matching logger **and its ancestors**. This mechanism is called **appender additivity** and defaults to `true`.

Suppose both `com.example.orders` and `ROOT` reference the `STDOUT` appender:

```text
OrderService.info("created")
   |
   +--> com.example.orders  --[STDOUT]--> one line
   |
   +--> ROOT                --[STDOUT]--> second line
```

In this case, **a single log call can cause the same appender to write twice**. This behavior is directly documented in the official Logback and Log4j 2 documentation.

Two common fixes:

- **Prefer routing through root:** if the child logger does not need a separate destination, **remove the duplicate appender reference from the child logger** and keep `additivity=true`.
- **Route separately at the child logger:** if the child logger has a different output policy, attach the required appenders to that logger and set `additivity=false` so it does not propagate to ancestors.

Setting `additivity=false` indiscriminately can cause **lost logs** in console/file/audit appenders attached to root. Understand the intended final destinations before making changes.

### 3.1. Logger Level Is Not an Anti-Duplicate Tool

`root level="INFO"`, `logger level="DEBUG"`, or an appender `ThresholdFilter` control which events are created/written. They do not fix the root cause of a route being referenced twice. Lowering the level to WARN may reduce duplicate lines, but it also drops valuable INFO logs.

Similarly, adding a message-based filter to swallow the second record is not guaranteed to be correct: a standard filter does not know whether the event was already sent through another path. Fix the **routing graph** first, then consider filters if needed.

## 4. Logback: Configurations That Cause Duplicates and How to Fix Them

Suppose a Spring Boot application uses **SLF4J + Logback** with `logback-spring.xml`.

### 4.1. Misconfiguration: Attaching STDOUT to Both Root and Child Logger

```xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <!-- Child logger attaches STDOUT; additivity defaults to true -->
    <logger name="com.example.orders" level="INFO">
        <appender-ref ref="STDOUT"/>
    </logger>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

Illustrative call in a class inside the `com.example.orders` package:

```java
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(OrderService.class);

public void createOrder(long id) {
    LOG.info("Đã tạo đơn hàng id={}", id);
}
```

This is a **class member snippet in a project that already has SLF4J/Logback**, not a standalone program run directly with `javac`. If `createOrder(42)` is called only once, the console can print two lines as shown below (timestamps are illustrative):

```text
10:15:00.100 INFO com.example.orders.OrderService - Đã tạo đơn hàng id=42
10:15:00.100 INFO com.example.orders.OrderService - Đã tạo đơn hàng id=42
```

These two lines can share **the same original event timestamp**, because they do not necessarily come from two separate event-creating calls.

### 4.2. Fix A: Remove the Duplicate Reference on the Child Logger

If logs only need to flow through root, the simplest configuration is:

```xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <!-- This logger only changes level; inherits STDOUT from root -->
    <logger name="com.example.orders" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

`com.example.orders` is permitted to create DEBUG events and forward them to root's STDOUT appender. **Root INFO does not re-filter** a DEBUG event already enabled at the child logger in Logback's appender propagation model. With no repeated STDOUT reference on the child logger, the event takes a single path to STDOUT.

### 4.3. Fix B: Dedicated Route and additivity=false

If you want the orders namespace to use its own console and file appenders (without propagating to root), declare it explicitly:

```xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ORDER_FILE" class="ch.qos.logback.core.FileAppender">
        <file>logs/orders.log</file>
        <append>true</append>
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.orders"
            level="INFO" additivity="false">
        <appender-ref ref="STDOUT"/>
        <appender-ref ref="ORDER_FILE"/>
    </logger>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

Events from `com.example.orders` are written once to the console and once to `orders.log` — **these are two distinct outputs by design**. Because `additivity=false`, they do not propagate up to root to be written to the console a second time.

This snippet uses a simple `FileAppender` to explain routing. Production files require rolling/retention policies, permissions, and disk space monitoring. If the dedicated configuration has a bad file path or the appender fails to initialize, `additivity=false` can cause orders logs to lose even the fallback path from root; check startup status logs.

**Do not apply `additivity=false` to every logger by default.** Apply it only to namespaces with clearly defined dedicated destinations, and test logs from their child loggers as well.

## 5. Log4j 2: Duplicates from LoggerConfig and AppenderRef

Log4j 2 also has additivity on `LoggerConfig`. Example of a misconfiguration in `log4j2.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <PatternLayout pattern="%level %logger - %msg%n"/>
        </Console>
    </Appenders>

    <Loggers>
        <Logger name="com.example.orders" level="info">
            <AppenderRef ref="CONSOLE"/>
        </Logger>
        <Root level="info">
            <AppenderRef ref="CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
```

Because `Logger` does not set `additivity=false`, events from `com.example.orders` can reach `CONSOLE` from both the child and root configurations.

**Fix when a single route through root is needed:** remove `AppenderRef` from the child logger:

```xml
<Loggers>
    <Logger name="com.example.orders" level="debug"/>
    <Root level="info">
        <AppenderRef ref="CONSOLE"/>
    </Root>
</Loggers>
```

This is a **replacement `<Loggers>` section** inside a configuration that already declares `CONSOLE`, not a standalone XML file.

**Fix when the child logger truly needs its own appender:** keep `AppenderRef` and declare:

```xml
<Logger name="com.example.orders" level="info" additivity="false">
    <AppenderRef ref="CONSOLE"/>
</Logger>
```

When `additivity=false`, this logger stops forwarding to ancestor appenders. If root also attaches a file or OTLP exporter, you must decide whether to attach those destinations explicitly to the child logger; otherwise they will **not receive events** from the orders namespace.

Remember: Log4j 2 can place filters/levels on Logger, Appender, or AppenderRef. Those filters control event acceptance, whereas the duplicate cause discussed here is **overlapping appender reference paths**.

## 6. Java 17+ Without External Libraries: Reproducing and Fixing with JUL

`java.util.logging` (JUL) calls its output component a **Handler**, not an Appender. It also forwards `LogRecord`s to the handlers of the current logger and its parent loggers when `useParentHandlers=true`.

The following example intentionally attaches **the same ConsoleHandler** to both a child logger and a parent logger to create a duplicate. It then removes the handler from the child so logs flow through the parent and the duplication stops. This is a standalone program runnable on JDK 17.

Create `DuplicateLogDemo.java`:

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class DuplicateLogDemo {
    private static final class CompactFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            return record.getLevel().getName() + " "
                    + formatMessage(record) + "\n";
        }
    }

    public static void main(String[] args) {
        Logger parent = Logger.getLogger("demo.routing");
        Logger child = Logger.getLogger("demo.routing.OrderService");

        parent.setUseParentHandlers(false);
        parent.setLevel(Level.ALL);
        child.setLevel(Level.ALL);
        child.setUseParentHandlers(true);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.ALL);
        console.setFormatter(new CompactFormatter());

        parent.addHandler(console);
        child.addHandler(console); // Same Handler at two levels.

        try {
            System.err.println("BEFORE");
            child.info("order=42");

            child.removeHandler(console); // Inherit only through parent.
            System.err.println("AFTER");
            child.info("order=43");
        } finally {
            child.removeHandler(console);
            parent.removeHandler(console);
            console.close();
        }
    }
}
```

Run:

```bash
javac --release 17 DuplicateLogDemo.java
java DuplicateLogDemo
```

JUL's `ConsoleHandler` writes to **stderr** by default. Stdout of `java DuplicateLogDemo` is empty; stderr has the exact output:

```text
BEFORE
INFO order=42
INFO order=42
AFTER
INFO order=43
```

Explanation:

1. `child.info("order=42")` creates only **one LogRecord**.
2. `child` sends the record to its own handler.
3. Because `useParentHandlers=true`, the record continues to the handler on `parent`; the same `console` instance is invoked a second time.
4. `child.removeHandler(console)` removes the child's direct write path. The `order=43` call only goes through the handler on `parent`.
5. `parent.setUseParentHandlers(false)` stops propagation to the root logger, preventing JUL's default console handler from printing an extra copy.

The example closes the handler in `finally` to avoid resource leaks. In production applications, manage handlers/`LoggerContext` according to the application lifecycle rather than mutating global loggers per request.

### 6.1. How Does Fixing with setUseParentHandlers(false) Differ?

In JUL, you can keep the handler directly on the child and call:

```java
child.setUseParentHandlers(false);
```

Then the child does not send records to the parent; the route consists only of the child's handler. This mirrors the **routing intent** of `additivity=false` in Logback/Log4j 2. Which approach is right depends on your intent: inheriting the parent's output or having dedicated output at the child.

### 6.2. What If Two Different Handlers Both Write to stderr?

Even without re-attaching the same `ConsoleHandler` object, two different handlers both writing to stderr can produce **two identical lines**. Therefore, when checking for duplicates, compare **physical destinations**, not just appender/handler names or object identities.

## 7. One Event, Multiple Appenders: Avoiding Misunderstandings

Suppose root defines:

```xml
<root level="INFO">
    <appender-ref ref="CONSOLE"/>
    <appender-ref ref="ROLLING_FILE"/>
</root>
```

This is a **Logback configuration snippet inside a file that already declares CONSOLE and ROLLING_FILE**. When `log.info` is called once:

- CONSOLE writes one copy to stdout.
- ROLLING_FILE writes one copy to the file.

This is **intentional fan-out**. It only becomes a duplicate in the backend if the pipeline ingests both copies into the same stream/index as two distinct events without an appropriate design.

Two copies can have the same timestamp and message while differing in pattern, MDC, or encoding. A deduplication method that only compares verbatim strings will miss them. Therefore, when defining "duplicate" for a system, specify the scope: **once per sink**, or **one logical event in the final index**.

### 7.1. Attaching a File Both Directly and via AsyncAppender

Misconfigured routing when `ASYNC_FILE` wraps `FILE` while root references both:

```xml
<appender name="ASYNC_FILE"
          class="ch.qos.logback.classic.AsyncAppender">
    <queueSize>1024</queueSize>
    <appender-ref ref="FILE"/>
</appender>

<root level="INFO">
    <appender-ref ref="FILE"/>
    <appender-ref ref="ASYNC_FILE"/>
</root>
```

This is a **snippet inside a Logback configuration where the FILE appender is already declared**. An event is sent directly to FILE and also passes through ASYNC_FILE's queue to be **written again by the same FILE**. The two copies may arrive some time apart, so looking at output timestamps alone is not enough to confirm the source.

If the goal is asynchronous file logging, root should reference only `ASYNC_FILE`:

```xml
<root level="INFO">
    <appender-ref ref="ASYNC_FILE"/>
</root>
```

Avoid stacking multiple async layers around the same sink without a measured need. Queues and retries can alter display order, but they do not eliminate duplicates on their own.

### 7.2. Appenders with Different Names Can Still Share a Destination

`CONSOLE_A` and `CONSOLE_B` can both write to `System.out`; `FILE_A` and `FILE_B` can point to the same file path; two exporters can send the same event to the same backend. **Different names do not prove different destinations.**

Design documentation should include a routing table mapping logger → appender → physical sink → collector → backend. When you see two log copies, check whether they converge on the same sink via two paths.

## 8. Spring Boot: Avoiding Overlap Between Default and Custom Configuration

Spring Boot comes with built-in logging configuration, typically using Logback when the default starter is kept. Key items to verify:

- **Actual backend:** Logback or Log4j 2, and which SLF4J provider is selected on the classpath? Do not assume that placing `log4j2.xml` means the application is actually using Log4j 2.
- **Effective configuration file:** which of `logback-spring.xml`, `logback.xml`, `logging.config`, or external config is actually loaded? Avoid keeping multiple files and editing the wrong one.
- **Active appender references:** does root include both a default console and a custom console you added? Do child loggers duplicate references?
- **Profiles/environments:** `springProfile` in `logback-spring.xml` or config overlays can activate multiple appenders under a specific profile.
- **Context re-initialization:** test suites, containers, or programmatic configuration code may re-attach handlers/appenders on each init if the lifecycle does not clean up old ones.
- **Library loggers:** a library attaching its own handler alongside a root that also has its own sink can create duplicates.

For example, in an application already using Spring Boot-managed Logback, the simplest way to raise a package's log level is:

```properties
logging.level.com.example.orders=DEBUG
```

If you only need to change the level, **do not create another console appender** for that package. Per-package level and output routing are two independent decisions.

Note: warnings like "multiple SLF4J providers/bindings" indicate a dependency issue that should be resolved, but **do not automatically prove that a single log call is written twice**. SLF4J normally selects one provider according to the version's resolution rules; duplicates must be verified along the actual execution path. At the same time, configuring a JUL ↔ SLF4J bridge or cross-framework forwarding into a loop can cause recursion or severe errors, not just an extra duplicate line. Enable forwarding only in intended directions.

## 9. Duplicates Caused by Logging Multiple Times in Business Code

Not all duplicates come from the framework. Distinguish between **the same LogEvent routed twice** and **two different LogEvents created by two log calls**.

Example:

```java
try {
    paymentGateway.charge(orderId);
} catch (RuntimeException ex) {
    log.error("Payment failed, order={}", orderId, ex);
    throw ex;
}
```

If a controller or global exception handler also calls:

```java
log.error("Payment failed, order={}", orderId, exception);
```

then there are **two logger calls**. This is not an additivity bug. Both can be valid if one adds context at another layer, but usually you should pick one place to log ERROR with the full stack trace, while other layers rely on trace context or log at a different level if diagnostically useful.

Common patterns:

- A filter/interceptor logs the request and the controller also logs the same message.
- A retry client logs "failed" on each attempt, then logs "failed" for the overall request; these may be **different events**, so include `attemptNumber` to distinguish them.
- An exception is caught, logged, and rethrown across multiple layers: each layer prints the same stack trace.
- A message listener receives the same message again due to at-least-once delivery; the business handler actually ran multiple times, which **cannot be fixed with appender additivity**.
- A scheduled job runs on multiple instances and each logs the same milestone; these may be multiple real executions.

Fix this by defining the **owner** of each business log type, distinguishing "attempt", "request", and "final outcome", and attaching appropriate request/trace/event IDs. If business processing is genuinely repeating, examine idempotency, retries, and consumer semantics rather than just filtering logs.

## 10. Duplicates in the Collector and Observability System

Even when Java writes only a single line to stdout, the backend can still see two records. For example:

```text
                  Java application
                    /          \
        Logback stdout       OTel log appender
              |                    |
       Filelog/agent tail          OTLP
              |                    |
            Collector A         Collector B
                  \               /
                    Same log index
                     -> 2 records
```

Two common workflows when integrating OpenTelemetry:

1. **Via stdout/file:** the logging framework writes to stdout/file; an agent/Collector reads, parses, adds resource attributes, and sends to the backend.
2. **Direct to Collector:** a logging appender/bridge converts events into OTel LogRecords and an SDK/exporter sends them over OTLP.

Both are valid. However, if **the same logical event** is configured to enter the same backend through **both**, the backend can store two copies. In that case, choose one primary ingestion path for that event type or design explicit routing/dedup. You do not necessarily have to disable traces: log export and trace export are separate signals.

Other causes at the collection layer:

- Two log collectors/sidecars reading the same file or the same stdout source.
- A DaemonSet agent and a standalone forwarder both pushing container logs to the same system.
- A file being re-tailed from an old offset when checkpoint/position state is lost, or when file rotation/renaming is mishandled.
- Collector exporter retries on ambiguous ACK status; the backend may receive the same record again depending on delivery and idempotency semantics.
- One receiver feeding two pipelines/exporters whose outputs merge into the same sink. **Fan-out to two separate backends** is valid; fan-out converging back into **the same index** easily creates duplicates.
- Queries/dashboards combining multiple indices/data sources that hold copies of the same event.

Therefore, inspect both **exporter/receiver configurations** and **queries/data sources**, not just `logback-spring.xml`.

### 10.1. Symptoms Pointing to the Layer Causing Duplication

| Symptom | Where to Check First |
| --- | --- |
| Console of a single JVM already has two lines | Logger/additivity, appenders, handlers, log call sites |
| Console has one line, file has two lines | Direct file appender reference + async/dual route; multiple writers |
| stdout and file each have one line, dashboard has two records | Two collection paths reading stdout and file |
| stdout has only one line, dashboard has two records with same resource | Collector, exporter retry, tailing/checkpoint, or merged query |
| Two records share `trace_id` but have different `span_id` | Likely **two different events/spans**; insufficient evidence of duplicate |
| Two records have same message but different instance | Check two pods/processes/requests or business retries |
| Duplicates appear after rolling restart | Collector re-reading file/offset, or multiple instances running concurrently |

Do not treat matching `trace_id` alone as proof of duplication: a single request can emit dozens of valid log events with the same trace ID.

## 11. How to Identify and Measure Duplicates

To diagnose, distinguish these identity layers:

- **Log statement identity:** code location/logger name and message template; the same statement can execute many times.
- **Event identity:** a specific LogEvent emission on a thread at a timestamp.
- **Execution identity:** `trace_id`, `span_id`, `request_id`, `attempt_no`, `message_id`, or `job_run_id`.
- **Source identity:** `service.name`, instance/pod ID, process ID, host, stream/file path.
- **Ingestion identity:** collector instance, receiver, exporter, index, pipeline, and retry attempt.

If business requirements demand strict deduplication (e.g., audit events), generate a **stable event ID** at the source for each logical business event and preserve that ID across retries/forwards. Regular logs do not necessarily need a new UUID for every line; weigh the cost and uniqueness guarantees of event IDs.

Avoid deduplicating with a key of only **message + timestamp rounded to the second**: two valid events can have the same text within the same second and be wrongly dropped. Nor should you deduplicate by `trace_id` alone: a single trace contains many log events.

When measuring in practice, compare:

```text
One (enabled) log call
    -> number of events received by each appender
    -> number of physical lines/records at source
    -> number of records received by collector
    -> number of records stored by backend
```

If duplication begins before the collector, prioritize fixing the Java route; if it only appears after the collector, focus on the pipeline/ingestion layer. Do not mask source bugs with downstream dedup when they can be fixed directly.

## 12. Step-by-Step Diagnostic Procedure

### Step 1: Use an Easily Distinguishable Probe Event

In a test environment, have the application log an event with a unique marker and controlled request ID:

```java
log.info("ROUTING_CHECK requestId={} stage={}", "probe-42", "single-call");
```

This is a call **inside an application with an SLF4J logger**, not standalone. Ensure it is invoked **only once** from one request/one instance during the test. Do not include sensitive data in the marker.

### Step 2: Check Emission Sites

Search for semantically identical logger calls in controllers, services, exception handlers, filters, interceptors, and retry listeners. If the source already invokes the logger twice, fix event ownership before changing appenders.

### Step 3: Map the Logger Tree and References

For example:

```text
ROOT                   -> CONSOLE, APP_FILE
com.example.orders     -> CONSOLE        (additivity=true)
com.example.audit      -> AUDIT_FILE     (additivity=false)
```

In this configuration, orders has a duplicate CONSOLE path, while audit uses a dedicated route. Verify the **runtime-loaded configuration**, not just files in source control. With multiple profiles, check the active profile.

### Step 4: Inspect Sinks and Pipelines

Identify stdout, stderr, active/archive files, OTLP, and log shippers. If the same event travels through two routes, check whether they reconverge at the same backend. Pay special attention to wrapper appenders (`AsyncAppender`, routing/sifting) and a single sink referenced twice.

### Step 5: Re-run and Compare

After fixing, repeat with a new test ID to avoid confusing results with old records. Count outputs at **each layer** and check other loggers as well to ensure `additivity` changes did not drop valid logs.

### Step 6: Test Under Load, Retries, and Restarts

A fix that works for a single request may not prevent duplicates during restarts/log rolling or collector retries. Run tests with bursts, multiple instances, and collector restarts with checkpoints matching the real system.

## 13. Recommended Configuration Patterns

| Need | Configuration Pattern | Reason |
| --- | --- | --- |
| Most loggers write to console | Attach console to root; child loggers only adjust level | Avoids repeated AppenderRef |
| One namespace needs a dedicated file and not root | Namespace has dedicated appender + `additivity=false` | Clear route, prevents ancestors from receiving extra copies |
| One event needs console and rolling file | Root attaches **two appenders with different sinks** | Intentional fan-out |
| File needs async | Root attaches **AsyncAppender**; wrapper attaches FileAppender | Avoids sending both directly and via queue to the same file |
| Centralized logs via stdout/file shipper | Export logs via a single stdout/file route with one properly scoped collector | Avoids ingesting the same log from both OTLP and filelog |
| Centralized logs via direct OTLP | Bridge/appender + SDK exporter along one clear log route | Avoids re-shipping stdout when pipeline already receives OTLP |
| Retried messages/transactions | Log attempt ID, event ID; business logic ensures idempotency | Duplicate execution is not a logger bug |
| Audit requiring anti-duplication | Records carry event ID with appropriate durable storage/unique constraint | Business-semantic dedup, distinct from text matching |

**There is no global "disable duplicate log" flag** that solves every layer. The right approach is to design and verify the routing flow from logger to ingestion.

## 14. Testing Against Duplicates in a Project

A useful checklist for learning and verification:

| Case | Setup | Expected |
| --- | --- | --- |
| Normal INFO | Child logger inherits root console | One event on console |
| Normal ERROR | Root console + file | One event per sink, two intentional destinations total |
| Child logger with dedicated appender | `additivity=false` | Does not propagate to ancestors |
| Child logger only changes DEBUG level | No dedicated appender attached | DEBUG event traverses root route once |
| Async file | Root references only the wrapper | File receives one copy per accepted event |
| Graceful restart | Stop/start logging context | No accumulation of duplicate handlers/appenders |
| Two instances | Each instance has an instance ID | Distinguishes two real events |
| Collector reading stdout | Only one receiver/tailer with clear ownership | Backend receives one record per source event |
| Direct OTLP and stdout | Inspect route of the same event | Does not unintentionally ingest two copies into the same index |
| Multi-layer exception | Catch–log–rethrow | Logged according to ownership rules or with clear additional info |

Do not assert only **"the message appears exactly once everywhere"**: an application may intentionally write the same event to both console and file. Tests should assert **the count per destination**.

For Logback integration tests, you can attach an observing appender to the target logger and count how many times an event traverses the route. However, if the test appender itself is attached to both child and parent, the test can create false duplicates. Pick a single observation point and reset/close the logging context after the test to prevent configuration leakage into other tests.

### 14.1. Pre-Production Configuration Checklist

1. Identified the actual logging backend/provider and the active configuration file.
2. Child loggers do not duplicate ancestor appenders while additivity is enabled.
3. Each wrapper appender and target appender is referenced only along its intended route.
4. `additivity=false` is set only where all required outputs are explicitly configured.
5. No bridge loops exist between logging frameworks.
6. One logical log event is not ingested twice via stdout/file/OTLP into the same backend.
7. Collector tailing, retries, restarts, and log rotation have tested checkpointing/ownership.
8. Appropriate service/instance/trace/request/event ID metadata is present to investigate real duplicates.
9. Alerts and dashboards count from the right pipeline without merging overlapping indices uncontrollably.
10. Logs are emitted at the right levels, with no lost ERROR/audit logs after routing changes.

## 15. Common Pitfalls When Fixing Duplicates

**Mistake 1 – setting `additivity=false` on every namespace.** A logger configured only with a level and no dedicated appender will stop writing logs anywhere. To keep a single route through root, usually you just **remove the child's AppenderRef**.

**Mistake 2 – deleting the console appender after seeing two console lines.** If the cause is an interceptor logging twice or duplicate collector ingestion, removing console can destroy your primary observation path.

**Mistake 3 – raising the level from INFO to ERROR.** This reduces visible lines without fixing the number of routes, while also losing valid INFO information.

**Mistake 4 – using regex to drop identical messages.** Two valid requests with the same message must still be recorded. Text-based dedup can hide real retry bugs or drop audit data.

**Mistake 5 – adding both sync and async to the same file.** `AsyncAppender` does not automatically replace the old route; remove the direct reference if you want the wrapper to be the sole path.

**Mistake 6 – inferring from the dashboard while ignoring the source.** The collector can duplicate records after Java writes a single copy. Verify stdout/file first.

**Mistake 7 – attaching the same handler repeatedly during init.** Some APIs/frameworks handle adding the same object differently, whereas creating **a new handler object on each init** usually accumulates write paths. Manage lifecycle and avoid adding new handlers per request or per config refresh.

**Mistake 8 – disabling all log export when you need to keep traces.** Exporting logs, metrics, and traces are separate channels in many systems. Decide the policy for the **logs signal** and monitor the impact on correlation.

## 16. A Real-World Scenario: One ERROR, Two Rows in the Dashboard

Suppose a payment service has a Logback root console appender and an OTLP logging appender. At the same time, the cluster runs a collector reading container stdout. The dashboard reports two `ERROR Payment timeout` records with the same `trace_id` and nearly identical timestamps.

How to handle it:

1. Verify stdout of the **exact container instance**: there is only one ERROR line.
2. Check the application's log bridge/appender: the same LogEvent may have been exported directly over OTLP.
3. Check the collector: whether both the stdout receiver and OTLP receiver send to the same logs backend/index.
4. Decide the intended architecture: keep either stdout → collector or direct OTLP for that event; avoid two paths feeding one index.
5. Apply the change, trigger a new test request, and verify only one logical record in the backend.
6. Verify that traces are still exported, logs still carry trace context if needed, and dropping one log pipeline did not lose critical ERRORs.

If stdout itself already has two copies, go back and check `root`/child loggers, config files, and duplicate log calls in code. **Disabling an exporter in the Collector alone will not fix an application-level bug.**

## 17. Self-Check Questions

1. When is having the same event in both the console and a rolling file correct behavior?
2. Why can a single `logger.info()` call produce two lines when the same appender is attached to both a child logger and root?
3. If you want a child logger to use only its own appender, what does `additivity=false` do and what outputs might it drop?
4. With Logback's `AsyncAppender` wrapping a file appender, why shouldn't root reference both the wrapper and the file?
5. Console has only one copy, but the backend has two: which layer should you investigate first?
6. Why can deduplicating by `message` or `trace_id` alone delete valid logs?
7. In what cases is a duplicate actually a symptom of business logic being executed/retried twice rather than a logging framework bug?

**Principle to remember:** every logical event must have a **clear path to each intended sink**. Inspect the logger hierarchy, appender/handler references, wrappers, and ingestion pipeline in order; fix where the duplicate path originates rather than dropping logs with semantics-free filters.

## References

- [Logback – Architecture and appender additivity](https://logback.qos.ch/manual/architecture.html).
- [Logback – Configuration: duplicate appender reference example](https://logback.qos.ch/manual/configuration-xml.html).
- [Logback – AsyncAppender](https://logback.qos.ch/manual/appenders-async-sift.html).
- [Apache Log4j 2 – Architecture, Appender Additivity](https://logging.apache.org/log4j/2.x/manual/architecture.html).
- [Apache Log4j 2 – Configuration](https://logging.apache.org/log4j/2.x/manual/configuration.html).
- [Java Platform – java.util.logging.Logger](https://docs.oracle.com/en/java/javase/21/docs/api/java.logging/java/util/logging/Logger.html).
- [Java Platform – java.util.logging.ConsoleHandler](https://docs.oracle.com/en/java/javase/21/docs/api/java.logging/java/util/logging/ConsoleHandler.html).
- [OpenTelemetry – Java log instrumentation](https://opentelemetry.io/docs/languages/java/instrumentation/).
- [OpenTelemetry – Logs overview, stdout/file and direct collector](https://opentelemetry.io/docs/specs/otel/logs/).