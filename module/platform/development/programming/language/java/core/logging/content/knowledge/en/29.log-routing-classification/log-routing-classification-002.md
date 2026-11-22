# Error Log Separation in Java: Routing, Classification, and Operations

## 1. What Is Error Log Separation?

In a Java system, an application may emit millions of **INFO** records about normal operations, a smaller number of **WARN** records for recoverable risks, and **ERROR** or **SEVERE** records for incidents that require investigation. If every event is treated identically, operations teams can easily miss critical errors, while verbose records drive up storage and query costs.

**Error log separation** is the practice of **classifying and routing error events** according to deliberate rules—for example, writing errors to a dedicated sink, forwarding them to a separate index or stream in an observability platform, or feeding an alerting pipeline. Error data can still exist simultaneously in the general log if policy requires a complete processing timeline.

Example:

~~~text
Java Application
    |
    +-- INFO, WARN, ERROR --> general log --> collector --> logs-all
    |
    +-- ERROR -----------> error log ----------> logs-error / alert candidate
~~~

In the diagram, an **ERROR can appear in both the general stream and the error stream**. This is intentional multi-routing, not necessarily a duplicate-logging bug. You need to clearly understand each destination route and the query/counting rules so that a single incident is not counted twice.

Error log separation does not mean **catching every exception and logging ERROR**, nor does it automatically guarantee incident detection. Outcome quality depends on accurate classification, preserving sufficient context, exception management, collectors, and alerting policies.

## 2. Distinguishing ERROR, WARN, and Business Events

Before writing a filter, you must answer the question: **which events truly belong in the error stream?**

| Event | Typical Assessment | Points to Note |
| --- | --- | --- |
| Request processed successfully | INFO or not logged per request | Can be aggregated via access logs/metrics |
| User submits invalid input | INFO/WARN depending on policy, not ERROR by default | HTTP 400/422 can be an expected outcome |
| Dependency timeout that will be retried | WARN if the application can still recover | Only ERROR when the operation truly fails per contract |
| One attempt fails, but job retry succeeds | WARN for the failed attempt; INFO for the final outcome | Keep attemptId to distinguish attempts |
| Job fails after exhausting retries | ERROR | Include jobId, error type, and necessary stack trace |
| Configuration error preventing service startup | ERROR/SEVERE | Clearly state the config key; avoid printing secrets |
| Failed login due to wrong password | Security event per policy | Do not include passwords/tokens in logs |
| Mandatory audit event | Separate audit stream, not based solely on ERROR level | Has separate retention and integrity requirements |

**HTTP status does not directly determine the log level.** A routine 404 may be an expected event; an HTTP 200 that writes corrupted data can be a severe incident. Evaluate based on **impact, recoverability, and whether operator action is required**.

You must also distinguish **business errors** (for example, an order failing due to insufficient inventory under valid rules) from **technical errors** (database connection loss, inability to commit a transaction). The two categories typically have different severity levels, handling paths, and alerting policies.

## 3. Error Separation Strategies

There are three common classification dimensions:

1. **By severity level:** WARN and above, ERROR and above, or strictly ERROR/SEVERE.
2. **By event source:** package/logger, module, service, worker, or business domain such as payment, ingestion, or scheduled jobs.
3. **By semantic fields:** errorCode, exceptionType, eventName, outcome, retryable, tenant, or downstream dependency.

Destinations can be console stdout/stderr, a separate file, a queue/broker, a collector route, a dedicated index, or an alert pipeline. A sound separation strategy usually maintains a **general stream** to view the full story, alongside an **error stream** for rapid incident lookup and operations.

Comparison:

| Routing Style | Advantages | Risks |
| --- | --- | --- |
| Store only ERROR in a separate file | Easy to find errors, low volume | Loses before/after context if no general log exists |
| Store everything in general and mirror ERROR to an error sink | Full-path investigation and fast error filtering | Two copies exist; must account for ingestion/retention billing |
| Single JSON stream, collector splits by level/event | Centralized rules, easy to apply in containers | Depends on parser, schema, and collector routing |
| Split by logger/package | Isolates a library or feature group | May miss errors emitted from other loggers |
| Split by errorCode/exceptionType | Queries exact business incident groups | Requires standardized fields and checking unclassified exceptions |

Avoid enabling an overly broad filter just because you want to "see every error." **WARN does not mean ERROR**, and **auditable errors do not mean diagnostic errors**.

## 4. Understanding Routing Components in Java

### 4.1. Java Util Logging (JUL)

The JDK provides **java.util.logging**, consisting of Logger, Level, Handler, Formatter, and Filter. In JUL, an event passes through the logger's threshold and then reaches the attached handlers. Each handler has its own **level** and may have its own **Filter**.

For example, with a logger at INFO, a console handler at INFO, and a file handler at SEVERE, INFO/WARNING/SEVERE records can go to the console, while only SEVERE and above go to the file. This is threshold-based separation; depending on requirements, you can use a Filter to apply additional criteria to specific events.

### 4.2. SLF4J + Logback

SLF4J is a logging API; Logback is a common provider/implementation. In Logback, the **Logger** decides which event levels are created, the **Appender** decides where to write, and the **Filter** decides whether an event is accepted, denied, or passed along for further evaluation by an appender.

Two filters are frequently confused:

- **ThresholdFilter:** accepts events at or above a threshold, such as WARN + ERROR when the threshold is WARN.
- **LevelFilter:** checks for **an exact level**, such as ERROR only; its onMatch/onMismatch settings control ACCEPT/DENY/NEUTRAL.

**A root logger set to WARN will block INFO before INFO ever reaches any appender.** Adding an INFO appender cannot recover an event already discarded by the logger. Therefore, you must consider both **logger level** and **appender filters**.

### 4.3. Log4j 2 or Other Frameworks

Log4j 2 has its own appender/filter and routing structure; Spring Boot can orchestrate providers and configure levels from properties. The separation concepts remain the same, but **do not copy Logback XML into Log4j 2 or JUL**. Always verify which implementation is active at runtime.

## 5. Standalone Java 17 Example: JUL Writing SEVERE Separately

The following example uses only JDK 17. We create a Logger, a ConsoleHandler accepting INFO and above, and a FileHandler accepting only **SEVERE**. To make the output easy to inspect, the formatter prints only the level and message, and the file is created in the OS temporary directory.

Create the file **ErrorRoutingDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.logging.ConsoleHandler;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ErrorRoutingDemo {
    private static final Formatter FORMAT = new Formatter() {
        @Override
        public String format(LogRecord record) {
            return record.getLevel().getName()
                    + " " + formatMessage(record)
                    + System.lineSeparator();
        }
    };

    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("error-routing-");
        Path errorPath = dir.resolve("error.log");

        Logger logger = Logger.getLogger("example.error.routing");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        ConsoleHandler general = new ConsoleHandler();
        general.setLevel(Level.INFO);
        general.setFormatter(FORMAT);

        FileHandler errors = new FileHandler(errorPath.toString(), false);
        errors.setLevel(Level.SEVERE);
        errors.setFormatter(FORMAT);
        errors.setEncoding(StandardCharsets.UTF_8.name());

        logger.addHandler(general);
        logger.addHandler(errors);

        try {
            logger.info("application_started");
            logger.warning("retry_scheduled");
            logger.severe("payment_failed");
        } finally {
            logger.removeHandler(general);
            logger.removeHandler(errors);
            general.close();
            errors.close();
        }

        List<String> lines =
                Files.readAllLines(errorPath, StandardCharsets.UTF_8);
        System.out.println("error-file-records=" + lines.size());
        System.out.println("error-file-first=" + lines.get(0));
    }
}
~~~

Compile and run:

~~~bash
javac ErrorRoutingDemo.java
java ErrorRoutingDemo
~~~

**stderr** produced by ConsoleHandler:

~~~text
INFO application_started
WARNING retry_scheduled
SEVERE payment_failed
~~~

**stdout** produced by the two `System.out.println` calls at the end of the program:

~~~text
error-file-records=1
error-file-first=SEVERE payment_failed
~~~

The **error.log** file contains only the line:

~~~text
SEVERE payment_failed
~~~

How it works:

1. The Logger has level INFO, so INFO, WARNING, and SEVERE are all generated.
2. ConsoleHandler receives all three events and writes to **stderr** by default.
3. FileHandler has level SEVERE, so it discards INFO and WARNING, writing only `payment_failed`. **SEVERE is a JUL level corresponding semantically to a critical error, not the ERROR name used in SLF4J.**
4. **setUseParentHandlers(false)** prevents logs from propagating up to the parent logger, avoiding duplicate console output via the root handler.
5. Removing and closing handlers in `finally` flushes and closes the file before reading it. The temporary directory is kept so the file can be inspected after execution; in a real application, manage lifecycle and retention explicitly.
6. stdout and stderr are **two separate streams**; if a terminal or collection environment merges them, their relative display order is not guaranteed by the program.

This demonstrates JUL routing. In production, do not create a new FileHandler per request: initialize handlers in application configuration, reuse them across the application lifecycle, and manage shutdown, rotation, and permissions.

## 6. Logback: Keeping General Logs and Writing ERROR Separately to a File

In a real application using SLF4J + Logback, you can write INFO/WARN/ERROR to the console and **ERROR only** to a separate file. Example **logback.xml**:

~~~xml
<configuration>
    <appender name="GENERAL" class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%d{ISO8601} %-5level [%thread] %logger{36} trace=%X{traceId} - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ERROR_FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/error.log</file>
        <filter class="ch.qos.logback.classic.filter.LevelFilter">
            <level>ERROR</level>
            <onMatch>ACCEPT</onMatch>
            <onMismatch>DENY</onMismatch>
        </filter>
        <rollingPolicy
            class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>logs/error.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
            <maxHistory>14</maxHistory>
            <totalSizeCap>2GB</totalSizeCap>
        </rollingPolicy>
        <encoder>
            <pattern>%d{ISO8601} %-5level %logger{36} trace=%X{traceId} - %msg%n%ex</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="GENERAL"/>
        <appender-ref ref="ERROR_FILE"/>
    </root>
</configuration>
~~~

Prerequisites: Logback must be present at runtime, the `logs/` directory must be creatable/writable, and the application needs persistent file storage or a log-shipping mechanism. The appender and rolling policy syntax must match the Logback version in use.

**Routing results:**

| Level | GENERAL (console) | ERROR_FILE |
| --- | --- | --- |
| DEBUG | No | No |
| INFO | Yes | No |
| WARN | Yes | No |
| ERROR | Yes | Yes |

Explanation:

- **root=INFO** emits INFO and above.
- **GENERAL** has no filter, so it receives every event that passes the root logger.
- **LevelFilter(ERROR)** on ERROR_FILE accepts only exact ERROR events. If replaced with a **ThresholdFilter** at WARN, the file would receive both WARN **and** ERROR.
- ERROR has two copies in **two intentional sinks**. If a collector reads both console and file, tag the route or select a single ingestion source to avoid double counting.
- **%ex** prints the exception stack trace if present. When a pattern includes both `%msg%n` and `%ex`, test the actual output format to ensure stack traces render clearly and are not duplicated. Stack traces are only written when the log event actually carries a Throwable.
- This pattern outputs **plain text**, not JSON; the MDC **traceId** will be empty if a tracing context is not configured.
- **maxHistory=14** and **totalSizeCap=2GB** are illustrative values for local file storage. Cost and retention in a centralized backend are managed independently.

If you want only ERROR in the file without INFO/WARN, **LevelFilter** is the clear choice. If you want **WARN and above**, use the appropriate filter and update your retention/alerting contract accordingly.

### Calling the Logger Properly

With SLF4J, at an error-handling boundary:

~~~java
try {
    processPayment(jobId);
} catch (PaymentGatewayException e) {
    logger.error("event=payment_processing_failed jobId={}", jobId, e);
    throw e;
}
~~~

This is an **integration snippet** requiring an application-defined logger, exception, and business method. SLF4J accepts a `Throwable` as the final argument and passes the stack trace to the provider. When an upper or lower layer has already logged the error completely, other layers should avoid re-logging the same exception without new context. **Never log and swallow an exception** if business semantics require rollback or retry.

## 7. What If You Only Want to Separate WARN and ERROR?

Policies vary according to operational requirements:

- **ERROR-only:** use **LevelFilter(ERROR)**; focuses on real failures with low volume.
- **WARN+ERROR:** use **ThresholdFilter(WARN)**; captures retry/degradation warnings as well, but requires filtering duplicate alerts.
- **Security/authentication events:** separate by `eventCode`/logger or a dedicated event channel; many security-relevant events are logged at INFO/WARN rather than ERROR.
- **Audit events:** route to an audit mechanism with appropriate integrity and retention guarantees, independent of whether someone changes the root logger level to WARN.

If one package produces excessive WARN logs while critical business errors come from another package, level-based filtering is still too coarse. In that case, standardize an **event code**, **marker**, or JSON field and configure routing at the collector. Do not rely on checking whether the message contains the string `"error"`, because messages from different components are phrased inconsistently.

## 8. Split at the Console or at the Collector in Containers?

In container/Kubernetes environments, it is often cleaner for the application to emit **a single structured log stream** and let the collector split it based on **level** and **event** fields. Conceptual routing example:

~~~text
Java service stdout/stderr
    |
    v
Log collector
    |
    +-- every event with valid schema ------> general index
    |
    +-- level = ERROR ----------------------> error index/route
    |
    +-- security/audit policy event --------> dedicated channel per contract
~~~

A single JSON line from the application can be routed by the collector to multiple destinations. Routing policies should be versioned and tested; if the collector parses the level field incorrectly, errors may fail to reach the error index.

**stdout/stderr is not an automatic severity classifier.** JUL's ConsoleHandler writes even INFO to stderr by default. In Logback, ConsoleAppender can target `System.out` or `System.err` and filter by level, but sending INFO/WARN to stdout and ERROR to stderr requires explicitly configuring **both routes with mutually exclusive filters**—not merely creating two ConsoleAppenders and attaching both to root.

If the Kubernetes platform already collects both stdout and stderr and enriches them with service/pod metadata, consider classifying at the collector to avoid writing local files inside containers. If a separate error file is required by regulation or operations, design persistent storage, rotation, and log shipping rather than assuming container-local files will persist.

## 9. Understanding Additivity and Avoiding Unintended Log Duplication

In Logback, child loggers have **additivity=true** by default: an event handled by an appender attached directly to a child logger also propagates up to ancestor/root loggers. For example, attaching the same ConsoleAppender at both the package level and the root level can cause a single event to be written twice to the same console.

Symptom: two identical lines with the same timestamp/logger/message appearing back-to-back in **the same sink**. This differs from an intentional policy that writes ERROR to both **GENERAL and ERROR_FILE**.

How to fix:

1. Inspect the **logger hierarchy** and `appender-ref` entries at each level.
2. Prefer attaching shared appenders once at `root` when appropriate.
3. If a specific logger needs **additivity=false**, attach all required appenders to that logger. Setting `false` while forgetting the general appender can cause logs to disappear from the general stream.
4. Check whether the collector is simultaneously reading both stdout and a file that record the same event.
5. In JUL, remember that **setUseParentHandlers(false)** similarly controls propagation to parent handlers.

A useful verification test: emit a single ERROR and confirm **one** record in the general sink and **one** record in the error sink, with no unexpected duplicates in the same sink.

## 10. Designing a Schema for Error Querying

An ERROR record should contain enough information for responders to identify the root cause without dumping the entire request:

| Field | Purpose |
| --- | --- |
| timestamp | When the event occurred, with an explicit timezone |
| level | ERROR or normalized severity |
| service, environment, version, instanceId | Isolates deployment and JVM/container |
| logger | Where the event originated |
| event, errorCode, outcome | Stable error type identifier |
| message | Meaningful summary, avoiding sensitive data |
| exception.type, exception.stacktrace | Technical cause when a Throwable is present |
| traceId, spanId, requestId | Links to request and distributed trace |
| jobId, attemptNo | Links to job and retry attempt |
| dependency | Affected downstream system when relevant |

Illustrative JSON example:

~~~json
{
  "timestamp": "2026-11-10T02:40:00Z",
  "level": "ERROR",
  "service": "order-service",
  "environment": "production",
  "instanceId": "order-pod-4",
  "event": "order_persist_failed",
  "errorCode": "DB_WRITE_FAILED",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "jobId": "order-582",
  "attemptNo": 3,
  "exception": {
    "type": "java.sql.SQLTransientConnectionException",
    "message": "Connection unavailable"
  }
}
~~~

This JSON is **illustrative data**, not output automatically generated by the plain-text Logback configuration in Section 6. If you need to store stack traces as a JSON field, use a real JSON encoder/formatter and verify escaping and size limits on the collector.

**errorCode should be stable**; avoid using raw exception messages (which may contain random IDs or hostnames) as error type names. This enables aggregation by root error and reduces alert cardinality.

If text logs contain multi-line stack traces, the collector must support multiline parsing or proper framing. Otherwise, each line of the stack trace may become a separate event, skewing error counts and breaking query context.

## 11. Preserving Context Across Multithreaded Processing

In Java, thread pools reuse threads, and `CompletableFuture` or callbacks can switch between threads. Fields from **MDC** or `ThreadLocal` on the caller thread are not automatically carried over to other tasks or services.

The snippet below illustrates MDC scoping with SLF4J and is **not a standalone JDK program**:

~~~java
import org.slf4j.MDC;

void handleJob(String jobId) {
    try (MDC.MDCCloseable ignored =
                 MDC.putCloseable("jobId", jobId)) {
        processJob();
    }
}
~~~

MDC supplies fields to loggers within its scope. On exit, the exact keys must be restored or cleared so the next job on the same thread does not inherit a stale `jobId`. When crossing executor boundaries, use a **capture -> activate -> restore** mechanism suited to your framework and tracing SDK; avoid relying on `InheritableThreadLocal` inside thread pools.

**traceId does not appear automatically just because the pattern includes `%X{traceId}`.** You need tracing integration or code that populates MDC, and across HTTP/message brokers you must inject/extract context. Copying a `traceId` string only supports log correlation; building a span tree also requires a tracer and propagator.

Error log separation does not replace context propagation. If `ERROR_FILE` captures an error without `requestId` or `jobId`, investigating failures under high load remains very difficult.

## 12. Exception Handling and Log-Once Policy

A service call chain typically spans multiple layers:

~~~text
HTTP Controller -> Service -> Repository -> Database
~~~

When the Repository throws an exception, not every layer should log the full stack trace. If the Repository logs ERROR, then the Service logs ERROR, and then the Controller logs ERROR for the same root cause, the collector may count three errors even though a single request failed once.

A sound policy is:

- At lower layers, **add context by wrapping in an exception with a cause** when needed and rethrow; log there only if the event genuinely requires independent observation.
- At the **handling boundary** (HTTP error handler, consumer job boundary, scheduler job handler), log the final error once with `requestId`/`jobId`, `errorCode`, and the throwable.
- If an error is caught for retry, log WARN with `attemptNo` when appropriate; log ERROR only if the operation ultimately fails per contract.
- If an exception is fully handled and causes no unexpected behavior, consider INFO/WARN rather than defaulting to ERROR.
- Never swallow an exception just to avoid logging. Preserve rollback, retry, response, or dead-letter semantics.

**Do not equate ERROR line count with incident count.** One outage can fail thousands of requests, and the same error can be logged across multiple workers or retries. Alerting systems should group by `event`/`errorCode`, `service`, `dependency`, and time window rather than firing one alert per log line.

## 13. Async Logging, Backpressure, and Error Durability

Some deployments use **AsyncAppender** or a queue to reduce I/O on request threads. When the queue fills up, logs may be delayed, block application threads, or be dropped depending on the provider and configuration.

| State | What Can Happen | What to Check |
| --- | --- | --- |
| Queue empty/has capacity | Events are enqueued and written later | Latency, relative ordering, collector |
| Queue nearly full | Buffering grows, heap pressure increases | Queue metrics, logging rate |
| Queue full | Producers block or events are dropped | Drop policy and guarantees for ERROR |
| Process killed abruptly | Unflushed events may be lost | Graceful shutdown, crash scenarios |
| Remote sink disconnected | Retries/buffering may accumulate | Timeouts, memory limits, log loss |

A separate ERROR route alone does not guarantee durability if it sits behind an async queue that can drop events. For critical error events, define the queue policy and design the write path accordingly. **Mandatory audit or transactional data** should not rely solely on "best effort" diagnostic logging; use dedicated storage/acknowledgment mechanisms when integrity is required.

Do not send every ERROR synchronously over the network without safeguards: a degraded log backend can cause cascading request failures. Isolate the failure domain of the logging pipeline.

## 14. Security, Privacy, and Retention

**Separating ERROR logs into their own file does not automatically make them safer.** Exception messages can contain JDBC URLs, table names, query parameters, tokens, internal addresses, customer details, or user data.

Apply these principles:

1. **Never log passwords, API keys, access tokens, Authorization headers, cookies, or unfiltered payment data.**
2. **Do not dump entire requests/responses** just because an exception occurred; log an `errorCode` and minimal context.
3. **Validate/escape input data** before including it in log messages, especially newline characters that enable log injection.
4. **Restrict read permissions** on error files/indices and dashboard exports.
5. **Define retention** based on purpose, legal requirements, data type, and storage limits; enforce deletion policies for copies and archives.
6. **Do not use `traceId`, `requestId`, or `jobId` as high-cardinality metric labels**; those IDs belong in logs and traces.

If using **RollingFileAppender**, configure time/size limits for files and test disk-full behavior. If routing errors to an error index, set separate retention and quotas; an error spike can cause the error stream itself to grow abnormally fast.

## 15. How to Test Routing Before Going to Production

Define a test event matrix:

| Emitted Event | General Sink | Error Sink | Expectation |
| --- | --- | --- | --- |
| Internal DEBUG trace | No (root INFO) | No | Matches threshold |
| INFO application_started | 1 | 0 | Normal events are not pushed to error |
| WARN dependency_retry | 1 | 0 | Under an ERROR-only policy |
| ERROR order_persist_failed | 1 | 1 | One copy in each permitted sink |
| ERROR with Throwable | 1 | 1 | Stack trace/context intact, not truncated or over-counted |

Then verify these scenarios:

- **Provider/config:** confirm the right JUL/Logback/Log4j 2 implementation, loaded config file, and effective levels.
- **Additivity:** a single event does not appear multiple times in **the same sink** due to duplicate appender attachment.
- **Structured output:** if using JSON, verify the parser handles Unicode, quotes, newlines, and exceptions.
- **Concurrency:** multiple threads/workers trigger errors concurrently without mixing up `traceId`/`jobId`.
- **Collector failure:** when the collector/remote endpoint stops, the application behaves according to its queue/backpressure policy; measure dropped events.
- **Disk pressure:** if writing files, test rotation, cleanup, permissions, and quotas in staging.
- **Security:** inject fake tokens and control characters into test inputs to confirm no credentials leak.
- **Alerting:** multiple retries of the same incident do not trigger an unwanted alert storm; normal INFO/WARN events do not trigger ERROR-only alerts.
- **Shutdown:** verify handler/appender flush/close behavior and assess potential log loss on hard kill.

### Troubleshooting When ERROR Logs Do Not Appear in the Error Sink

1. Check whether the application **actually generates ERROR/SEVERE** at runtime.
2. Confirm the **effective logger level** is not blocking the event before it reaches the appender/handler.
3. Inspect the **filter**: does `LevelFilter` match `ERROR` accurately, or is `ThresholdFilter` excluding the intended event?
4. Verify the appender is referenced, the file path/write permissions/disk space are valid, and the handler was not closed prematurely.
5. If events appear in console/file but not on the dashboard, investigate **collector -> parser -> transport -> index**.
6. Check data schema and normalized level names; SLF4J's `ERROR` and JUL's `SEVERE` may need mapping when routed through a shared backend.

Do not rush to raise the entire application to DEBUG to fix a routing bug; those are two separate problems.

## 16. Design and Operations Checklist

| Item | Verification Criteria |
| --- | --- |
| Error definition | Distinguishes ERROR, WARN, retryable failure, business rejection, and audit |
| Logger level | Logger level allows routed events to reach handlers/appenders |
| Filter | ERROR-only or WARN+ rules are explicitly written and tested |
| General sink | Preserves enough timeline for investigation |
| Error sink | Contains only intended records, without excess INFO/WARN |
| Additivity | No unintended duplicates occur |
| Context | Includes service, instance, errorCode, traceId/jobId, and Throwable where appropriate |
| Production format | JSON or text chosen deliberately; compatible with parser/collector |
| Reliability | Queue/drop/block/flush policies are known |
| Security | No secrets leaked; permissions and retention are enforced |
| Capacity | Rotation, size cap, quota, collector rate, and alert cardinality are managed |
| Verification | Verified real data in both general and error sinks |

**Key takeaway:** error log separation is an **event classification and routing** problem. In Java it can be implemented at the logger/handler/appender layer or in the collector, but you must always ensure accurate levels, no over-counted events, intact exceptions and context, protected sensitive data, and an error pipeline that stays reliable under production load or failure.