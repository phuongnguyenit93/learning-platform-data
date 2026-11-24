# TRACE, DEBUG, INFO, WARN, ERROR and Choosing the Right Log Level

In Spring Boot, logs are not merely lines of text appearing in a terminal. They are a vital source of information for understanding **what the application is doing, what happened, why an error occurred, and what its impact is**. When a service handles thousands of requests per minute, choosing the wrong log level can bury important signals in a "sea" of messages, drive up storage costs, slow down the system, or cause operations teams to mistake normal events for severe incidents.

Conversely, logging too little can make a production-only bug very difficult to investigate.

Spring Boot typically uses **SLF4J** as the logging API in Java code and, with common starters, uses **Logback** as the underlying implementation system. The five levels developers encounter most often are:

~~~text
TRACE < DEBUG < INFO < WARN < ERROR
~~~

This ordering expresses the **severity/priority level of a message**, not when it occurred or the application's speed.

This lesson belongs to **Spring Boot Fundamentals → Logging**, focusing on understanding each log level, threshold-based filtering, per-package/class configuration, and choosing reasonable levels based on **anomaly severity, impact, and recoverability**.

## 1. What is a log and what should a log entry answer?

A log entry is a readable and queryable event produced by the application or infrastructure.

Example:

~~~text
2026-11-13 09:20:11.306  INFO  14322 --- [http-nio-8080-exec-2]
c.e.orders.OrderService : Created order orderId=ORD-1052 items=3

2026-11-13 09:20:13.481  WARN  14322 --- [http-nio-8080-exec-4]
c.e.payment.PaymentClient : Payment gateway timed out; retry=1

2026-11-13 09:20:18.005 ERROR  14322 --- [http-nio-8080-exec-4]
c.e.payment.PaymentClient : Payment failed after retries; orderId=ORD-1052
~~~

Logs typically contain:

- **Timestamp**: when the event occurred.
- **Level**: priority/importance of the message.
- **Logger name**: class or group emitting the message.
- **Thread**: execution thread, useful when investigating concurrency.
- **Message**: event description and relevant context.
- **Exception**: stack trace if present and passed properly to the logger.
- **Correlation ID / trace ID** if the system is configured for cross-request observability.

A good log lets the reader identify **what happened, which entity was involved, what the outcome was, and whether action is required**, without immediately having to read source code.

However, a log does not have to contain all of the items above. The actual structure depends on logging configuration and purpose; for instance, console logs in development may be shorter than logs sent to a centralized system.

## 2. The five log levels: order and meaning

| Level | Primary purpose | Who typically reads it |
|---|---|---|
| **TRACE** | Extremely fine-grained execution details, intermediate steps, and values for deep investigation | Developers debugging a specific case |
| **DEBUG** | Technical information needed when analyzing behavior, branch choices, safe parameters, processing state | Developers, incident investigators |
| **INFO** | Normal operational events worth knowing at the operational level | Developers, operations, system observability |
| **WARN** | Abnormal condition or risk; the application can continue, yet it is worth monitoring | Operations and system owners |
| **ERROR** | Critical operation failed, feature did not complete, or an error needs handling | Operations, incident responders |

These are guidelines, not a rigid rulebook forced onto every application. The appropriate level depends on business contracts, event frequency, and recoverability.

For example, the same network error:

- An initial background request fails yet succeeds on retry: this could be **DEBUG** or **WARN**, depending on how useful it is to observe.
- An API must use a fallback yet still returns a valid response: this could be **WARN**.
- A payment transaction fails after exhausting all recovery options: this could be **ERROR**.

**The log level should describe the final impact on the system, not merely the exception class name.**

### 2.1. TRACE — the most detailed level

Use TRACE when you need to follow tiny steps that should normally stay out of logs:

~~~java
log.trace(
        "Matching rule id={} against candidate index={}",
        ruleId,
        candidateIndex
);
~~~

Suitable information:

- Loop iterations in an algorithm.
- Selected intermediate state.
- Match counts, cursor positions, conditional branches evaluated.
- Execution progression needing very deep investigation.

Do not log full request bodies, user data, tokens, or structures containing secrets simply because you are at TRACE. **TRACE is not exempt from data security rules**.

TRACE generally generates far more logs than DEBUG and should only be enabled on needed loggers for a limited time window.

### 2.2. DEBUG — information to understand code decisions

DEBUG focuses on **why the code chose a particular execution path**:

~~~java
log.debug(
        "Selected pricing strategy={} for orderId={}",
        strategyName,
        orderId
);
~~~

Another example:

~~~java
log.debug(
        "Cache lookup key={} hit={}",
        safeCacheKey,
        cacheHit
);
~~~

DEBUG is suitable for:

- Strategy/implementation selection.
- Important conditional branches.
- Cache lookup results or non-sensitive metadata.
- Additional context before calling an external service.
- Sanitized configuration values when investigating.

Avoid emitting a DEBUG line for every tiny step inside a large loop unless truly valuable; that belongs at TRACE or should be turned into an aggregated metric.

### 2.3. INFO — meaningful normal operational events

INFO is the level commonly used as the default threshold for the root logger in a typical Spring Boot application.

A good INFO log describes a meaningful milestone:

~~~java
log.info(
        "Imported file fileId={} records={} durationMs={}",
        fileId,
        recordCount,
        durationMs
);
~~~

You can use INFO for:

- Application starting, completing startup steps, or shutting down.
- An important batch completing.
- A data processing session starting/finishing.
- A significant business state transition.
- A non-sensitive operational configuration change taking effect.

Not every request or every method call belongs at INFO. In high-throughput applications, logging an INFO line for every small call can be very expensive. Consider metrics for aggregated quantitative data.

### 2.4. WARN — anomaly with a path forward

WARN denotes a **noteworthy** condition that has not necessarily caused the operation to fail completely.

~~~java
log.warn(
        "Primary inventory provider unavailable; using cached data ageSeconds={}",
        cacheAgeSeconds
);
~~~

Examples:

- Calling the primary source fails, yet a valid fallback succeeds.
- Configuration uses an option scheduled for deprecation.
- Queue nearing capacity or a resource approaching its threshold.
- Retries occurring unusually often.
- Data can still be processed yet has discrepancies worth tracking.

WARN does not mean "an arbitrary exception occurred". Invalid user input handled properly by the API with HTTP 400 can be a normal event that does not need WARN.

### 2.5. ERROR — functionality failed or impactful incident

ERROR is used when an important operation cannot complete or the system is in an error state requiring attention:

~~~java
log.error(
        "Failed to finalize invoice invoiceId={}",
        invoiceId,
        exception
);
~~~

Examples:

- Transaction failed after retries with no remaining fallback.
- Unexpected error causing a request to return HTTP 500.
- Mandatory job failed unrecoverably.
- Loss of data consistency or essential resource unavailable.

An ERROR message **does not necessarily stop the application**. It is simply a log level. Conversely, the absence of ERROR logs does not prove the application has no bugs.

## 3. Threshold-based filtering mechanism

A common point of confusion: configuring `INFO` does not mean the application **only logs INFO**. It means the logger accepts **INFO and higher-priority levels**.

With the five basic SLF4J levels:

~~~text
TRACE   DEBUG   INFO   WARN   ERROR
 1       2       3      4      5
                 ^
                 |
        Configured threshold: INFO
~~~

When the threshold is `INFO`, `TRACE` and `DEBUG` messages usually do not appear, while `INFO`, `WARN`, and `ERROR` are allowed to proceed through the logging pipeline.

| Configured threshold | TRACE | DEBUG | INFO | WARN | ERROR |
|---|---|---|---|---|---|
| TRACE | Yes | Yes | Yes | Yes | Yes |
| DEBUG | No | Yes | Yes | Yes | Yes |
| INFO | No | No | Yes | Yes | Yes |
| WARN | No | No | No | Yes | Yes |
| ERROR | No | No | No | No | Yes |

This table shows **minimum-level filtering** in standard configuration. The logging backend may still have custom filters, appenders, and conditions preventing some entries from being output even if they exceed the threshold.

### INFO threshold example

Code:

~~~java
log.trace("Step 1");
log.debug("Step 2");
log.info("Step 3");
log.warn("Step 4");
log.error("Step 5");
~~~

If the logger's effective level is INFO and there are no special filters, the visible output is:

~~~text
INFO  Step 3
WARN  Step 4
ERROR Step 5
~~~

If changed to an effective level of `DEBUG`:

~~~text
DEBUG Step 2
INFO  Step 3
WARN  Step 4
ERROR Step 5
~~~

If changed to `ERROR`, only the ERROR line remains.

### "Log level" is not "write everything at every level"

Some developers change every `log.debug(...)` call to `log.info(...)` just to see them appear in production. That destroys categorization. The proper approach is usually:

1. Keep meaningful log levels intact.
2. Temporarily adjust the specific logger configuration.
3. Investigate the issue.
4. Return the logger level to the appropriate operational setting.

That way code is not "polluted" with temporary logs at misleading levels.

## 4. SLF4J, loggers, and backends in Spring Boot

In code, you typically import:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
~~~

Create a per-class logger:

~~~java
private static final Logger log =
        LoggerFactory.getLogger(OrderService.class);
~~~

`Logger` here is the SLF4J API. The application invokes methods:

~~~java
log.trace("...");
log.debug("...");
log.info("...");
log.warn("...");
log.error("...");
~~~

The backend such as Logback decides how to apply filtering thresholds, formatting, console/file output, and forwarding logs to appenders or collection systems.

In projects using standard Spring Boot starters, the `spring-boot-starter-logging` dependency is usually present and provides Logback. Projects can also be configured to use another backend such as Log4j2. The principles of the five basic SLF4J levels still apply, though advanced backend configuration syntax may differ.

### Why shouldn't you write System.out.println for business logs?

~~~java
System.out.println("Order processed: " + orderId);
~~~

This approach may appear on the console, yet lacks many management capabilities:

- No standard log levels.
- Hard to disable per package.
- Does not automatically integrate with backend patterns or structured logging.
- Hard to standardize formatting and log forwarding.
- Hard to control sensitive data consistently.

Use instead:

~~~java
log.info("Order processed orderId={}", orderId);
~~~

This does not mean `System.out` is always forbidden; it remains useful for intentional CLI user output. However, for operational service logs, use a logging API.

## 5. Small Spring Boot example featuring all five log levels

The following example can be used in a Spring Boot application with SLF4J and a configured logging backend. We create a runner emitting demo events.

~~~java
package com.example.logging;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class LoggingDemoApplication {

    private static final Logger log =
            LoggerFactory.getLogger(LoggingDemoApplication.class);

    public static void main(String[] args) {
        SpringApplication.run(LoggingDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demoLoggingLevels() {
        return args -> {
            log.trace("TRACE: inspecting a tiny internal step");
            log.debug("DEBUG: selected mode={}", "SAMPLE");
            log.info("INFO: demo startup task completed");
            log.warn("WARN: using a fallback configuration");

            try {
                Integer.parseInt("not-a-number");
            } catch (NumberFormatException exception) {
                log.error("ERROR: demo data cannot be parsed", exception);
            }
        };
    }
}
~~~

Key points to note:

- TRACE and DEBUG lines may not display if the effective level is INFO.
- The WARN line here simulates a fallback; in a real application, only log when a fallback actually occurs.
- The ERROR line is solely to create a learning scenario, not a recommendation to log a fixed ERROR on every startup.
- Passing `exception` to the logger lets the backend print the stack trace, not just the message.

If the application is an HTTP API, a runner is not mandatory; the example uses a runner so learners can observe logs immediately on startup without making requests.

### Running with default levels

In a typical Boot project, the default root level is INFO. Thus you see INFO, WARN, and ERROR from the runner.

### Enabling DEBUG solely for the demo package

In `application.properties`:

~~~properties
logging.level.com.example.logging=DEBUG
~~~

Restarting the application shows DEBUG logs from loggers in this package, while TRACE is still filtered out.

### Enabling TRACE solely for the demo package

~~~properties
logging.level.com.example.logging=TRACE
~~~

Now all five levels from loggers in this package are allowed through the threshold.

**There is no need to set `logging.level.root=TRACE` across the entire application** just to observe one learning class. Setting root to TRACE usually generates huge amounts of messages from frameworks and libraries.

## 6. Configuring logging.level in application.properties

Spring Boot lets you set log levels by root, package, or logger name:

~~~properties
# General level
logging.level.root=INFO

# View details only from application code
logging.level.com.example.orders=DEBUG

# Reduce less important logs from a library
logging.level.org.springframework.web=WARN

# Track a specific logger in detail
logging.level.com.example.orders.OrderService=TRACE
~~~

In an actual file, lines starting with `#` are comments in the properties format.

### Root level

~~~properties
logging.level.root=INFO
~~~

The root logger is the default threshold for loggers without a more specific effective setting.

For example, when root is INFO, loggers with no override usually only emit INFO and above.

### Package-level configuration

~~~properties
logging.level.com.example.orders=DEBUG
~~~

This applies to loggers in namespace `com.example.orders` via the backend's logger name hierarchy. Because loggers created from classes typically carry the fully-qualified class name, package configuration adjusts many related classes at once.

Example:

~~~text
com.example.orders.OrderService        -> DEBUG
com.example.orders.OrderController     -> DEBUG
com.example.orders.internal.Validator  -> DEBUG
~~~

Other packages such as `com.example.payment` are not directly affected by the `com.example.orders` rule.

### Specific class/logger level

~~~properties
logging.level.com.example.orders.OrderService=TRACE
~~~

This is the full logger name when code uses:

~~~java
LoggerFactory.getLogger(OrderService.class)
~~~

If a specific class is set to TRACE while its parent package is DEBUG, the more specific configuration usually wins for that logger.

**Class-based logging configuration relies on logger names, not Spring bean names.** A class with multiple beans still uses the same logger if they all declare the logger for that class.

## 7. Equivalent configuration in application.yml

With YAML:

~~~yaml
logging:
  level:
    root: INFO
    com.example.orders: DEBUG
    org.springframework.web: WARN
    com.example.orders.OrderService: TRACE
~~~

You can read this structure as a map of logger name → log level.

When config is loaded into Spring's `Environment`, the corresponding properties are:

~~~text
logging.level.root = INFO
logging.level.com.example.orders = DEBUG
logging.level.org.springframework.web = WARN
logging.level.com.example.orders.OrderService = TRACE
~~~

Note: casing of a full logger name such as `OrderService` can matter. Do not arbitrarily lowercase class names in configuration assuming the backend will match them automatically.

### You can use log group names

If multiple related packages need to be adjusted together, Spring Boot supports logger groups:

~~~properties
logging.group.billing=com.example.billing,com.example.payments
logging.level.billing=DEBUG
~~~

This lets the `billing` group change the levels of all listed loggers together without typing each package every time.

Built-in logger groups and detailed configuration options may vary by Boot version; for custom application-defined groups like the example, choose meaningful names and scope them precisely to what needs observation.

## 8. Configuration via command line and environment variables

In deployment environments, editing `application.properties` and rebuilding the JAR is not always desirable just to raise a log level.

### Command-line arguments

Example:

~~~bash
java -jar app.jar --logging.level.com.example.orders=DEBUG
~~~

Or:

~~~bash
java -jar app.jar --logging.level.root=WARN
~~~

In a typical Spring Boot application, command-line arguments override corresponding values in application config files. This is convenient when restarting one instance for investigation.

### Environment variables

For all-lowercase packages, you can use:

~~~bash
export LOGGING_LEVEL_ROOT=INFO
export LOGGING_LEVEL_COM_EXAMPLE_ORDERS=DEBUG
java -jar app.jar
~~~

On PowerShell:

~~~powershell
$env:LOGGING_LEVEL_ROOT = "INFO"
$env:LOGGING_LEVEL_COM_EXAMPLE_ORDERS = "DEBUG"
java -jar app.jar
~~~

**Important note for class-level loggers:** when using system environment variables, logger names under `logging.level` may be lowercased by map binding mechanisms. This usually causes no issue for lowercase package names, yet may fail to configure a specific class logger containing uppercase letters such as `OrderService`.

When needing a log level for a case-sensitive logger/class, prefer `application.properties`, `application.yml`, command-line properties, or `SPRING_APPLICATION_JSON` instead of guessing an env variable name.

Example on Linux shell:

~~~bash
export SPRING_APPLICATION_JSON='{"logging":{"level":{"com.example.orders.OrderService":"TRACE"}}}'
java -jar app.jar
~~~

These approaches preserve exact logger names in configuration.

### External configuration does not mean immediate runtime change

If you edit a shell environment variable **after the Java process is already running**, the process usually does not automatically pick up the new value. Do not assume modifying a file or environment variable always updates effective levels immediately.

To change log levels in a running process, you need a dedicated runtime mechanism such as the Actuator loggers endpoint, JMX, or backend configuration capabilities.

## 9. Understanding effective level and inheritance

In many logging backends, loggers are organized in a hierarchical naming scheme. A logger without an explicit level usually inherits its effective level from the nearest parent logger, ultimately up to root.

Suppose:

~~~properties
logging.level.root=INFO
logging.level.com.example=DEBUG
logging.level.com.example.payment=WARN
~~~

The result can be understood as:

| Logger name | Effective level in example |
|---|---|
| `org.springframework.boot.StartupInfoLogger` | INFO, if no other override exists |
| `com.example.catalog.CatalogService` | DEBUG |
| `com.example.payment.PaymentService` | WARN |
| `com.example.payment.gateway.GatewayClient` | WARN |

If you write:

~~~java
log.debug("Attempting payment");
~~~

inside `PaymentService`, this message is normally filtered out at the WARN threshold, even though parent logger `com.example` has threshold DEBUG.

### Distinguishing logger threshold from appender

Whether a log appears does not depend solely on the threshold. For example, the backend might have:

- A console appender writing only INFO and above.
- A file appender writing only WARN/ERROR.
- Filters discarding a subset of messages.
- Sampling or forwarding policies in the collection system.

Therefore, when a message "disappears", inspect both the **effective logger level** and log destinations, not just `logging.level.*` properties.

## 10. How to choose a level: ask about impact first

A pragmatic approach is answering in order:

1. **Is this a failure preventing the operation from completing?** If yes and there is no remaining recovery path, it is usually ERROR at an appropriate boundary.
2. **Is there an anomaly affecting reliability or requiring a fallback?** Usually consider WARN.
3. **Is this a normal operational milestone worth observing?** If yes, consider INFO.
4. **Is this data to help developers understand a code decision?** Use DEBUG.
5. **Is this a tiny detail of processing?** Use TRACE.

You can visualize this as:

~~~text
Event to record
      |
      v
Critical operation failed, unrecoverable?
      | Yes
      +------------------------------> ERROR
      |
      | No
      v
Anomaly, fallback, or risk to monitor?
      | Yes
      +------------------------------> WARN
      |
      | No
      v
Normal operational milestone worth observing?
      | Yes
      +------------------------------> INFO
      |
      | No
      v
Helps understand decision or processing state?
      | Yes
      +------------------------------> DEBUG
      |
      | No
      v
Tiny detail for deep investigation?
      | Yes
      +------------------------------> TRACE
      |
      v
Do not log; use metric, trace, or omit event
~~~

Not every line of code has to emit a log. **Not logging** is also a valid choice when an event adds no new information or is already well observed through another mechanism.

### Matrix of common scenarios

| Scenario | Commonly considered level | Reason |
|---|---|---|
| Application started and ready | INFO | Operational milestone worth knowing |
| Scheduled job completes with processed record count | INFO | Outcome of a unit of work |
| Choosing pricing strategy by customer type | DEBUG | Technical decision detail |
| Cache hit/miss per item in a high-traffic flow | DEBUG/TRACE or metric | Can produce massive log volume |
| Stepping through each parser iteration | TRACE | Very deep detail |
| Using backup cache because primary provider is slow | WARN | Degraded quality or fallback |
| Deprecated configuration still functioning | WARN | Needs proactive remediation |
| HTTP 400 due to expected invalid user input | Usually not WARN/ERROR | Expected API behavior |
| Common retry that eventually succeeds | DEBUG or selective WARN | Depends on anomaly and frequency |
| Transaction fails with no fallback left | ERROR | Required outcome not achieved |
| Mandatory job fails and aborts | ERROR | Impactful incident |
| Exception caught and validly recovered | DEBUG/INFO or no log | No unhandled error remains |
| Code bug causing HTTP 500 | ERROR at boundary | System error needing investigation |
| Memory pressure approaching alert threshold | WARN | Risk worth watching |
| Saving a normal data row inside a large loop | Do not log or TRACE | Reduces noise and cost |

This table is a guide. A very low-volume operation with strict audit needs may require different detail than an API serving millions of requests. Standardize logging policies per system domain.

## 11. INFO does not mean "log every normal action"

A common anti-pattern:

~~~java
log.info("Enter createOrder");
log.info("Validating order");
log.info("Calling repository");
log.info("Repository returned");
log.info("Mapping DTO");
log.info("Leaving createOrder");
~~~

With many requests, these lines quickly bury valuable events. If you need method-flow visibility to debug an issue, they fit better at DEBUG/TRACE, or via distributed tracing.

Instead, log one meaningful outcome:

~~~java
log.info(
        "Order created orderId={} itemCount={} durationMs={}",
        orderId,
        itemCount,
        durationMs
);
~~~

If an application has very high throughput, even per-request INFO logs can be excessive. Choose batch milestones, sampling, or aggregated metrics depending on operational needs.

### Suitable INFO examples

- `"Catalog refresh completed items=2500 durationMs=1830"`
- `"Kafka consumer assigned partitions count=8"`
- `"Daily reconciliation finished matched=1200 mismatched=4"`
- `"Configuration reload completed version=7"`

Do not log sensitive values or arbitrary objects just to make logs look "complete".

## 12. WARN differs from ERROR by recoverability

Two nearly identical code blocks may require different log levels.

### Scenario A: valid fallback exists

~~~java
try {
    price = priceProvider.fetchLatestPrice(productId);
} catch (PriceProviderTimeoutException exception) {
    price = cachedPriceProvider.getValidPrice(productId);

    log.warn(
            "Price provider timed out; using valid cached price productId={}",
            productId
    );
}
~~~

The classes above are illustrative. Assume the fallback provides data still valid under business policy.

The user still receives a valid result, so WARN fits to report degraded operation. You do not necessarily need full stack traces for every retry/fallback repeating thousands of times; combine metrics with selective detailed logs.

### Scenario B: no fallback and request fails

~~~java
try {
    price = priceProvider.fetchLatestPrice(productId);
} catch (PriceProviderTimeoutException exception) {
    log.error(
            "Price lookup failed; no fallback productId=" + productId,
            exception
    );
    throw exception;
}
~~~

Here the operation cannot finish; ERROR makes more sense. However, the example also illustrates a risk: if the controller advice **also logs ERROR for the same exception**, the system ends up with two or more identical stack traces.

A production design should assign a clear **point responsible for logging ERROR**, typically at the request/job boundary; lower layers can preserve context in exceptions or use DEBUG instead of duplicating.

### Decide based on the final outcome

In a system with retries:

~~~text
Attempt 1 fails
       |
       v
Retry 2 succeeds ---> final outcome is success

=> May log DEBUG for retry;
   if retry rate is abnormal, use WARN/metric.
~~~

Conversely:

~~~text
Attempt 1 fails
       |
       v
Retry 2 fails
       |
       v
Retry 3 fails
       |
       v
No fallback ---> ERROR at boundary
~~~

Do not log ERROR on every attempt if each failure is merely an intermediate state handled by retries. Doing so causes an "ERROR storm" even when no request ultimately failed.

## 13. Logging exceptions and stack traces

A `Throwable` contains more information than `getMessage()`:

- Exception type.
- Message.
- Origin and propagation path via the stack trace.
- `getCause()` chain.
- Suppressed exceptions in certain resource-closing scenarios.

### Mistake: logging only the message

~~~java
catch (IOException exception) {
    log.error("Cannot import file: {}", exception.getMessage());
}
~~~

This line usually loses the stack trace and nested causes. The message might be short or empty, making investigation difficult.

### Better approach: pass the Throwable to the logger

~~~java
catch (IOException exception) {
    log.error("Cannot import file fileId=" + fileId, exception);
}
~~~

Or:

~~~java
log.error(
        "Cannot import file fileId={}",
        fileId,
        exception
);
~~~

Standard SLF4J backends recognize a trailing `Throwable` argument to log the exception. If you want an explicit form, use the `log.error(String, Throwable)` overload as in the first example.

### Not every WARN needs a stack trace

If a fallback situation is expected and occurs relatively often, logging a WARN with a full stack trace every time can be overly expensive. Log a concise message with event code, retry count, and duration, paired with a metric measuring frequency.

Conversely, for first-time or hard-to-reproduce errors, a stack trace is crucial information.

### Avoid "log then throw" at every layer

Anti-pattern example:

~~~java
public Result process() {
    try {
        return repository.load();
    } catch (Exception exception) {
        log.error("Repository failed", exception);
        throw exception;
    }
}
~~~

If the service, controller, and global exception handler all do the same thing, one failure creates multiple duplicate ERROR entries.

Separate responsibilities:

- Lower layers add context via meaningful exceptions and preserve the cause.
- The layer deciding on a fallback logs WARN/DEBUG if needed.
- The boundary layer deciding the final outcome logs ERROR once, if needed.
- Frameworks may already log uncaught errors; avoid duplicating built-in mechanisms.

Do not lose the original stack trace when wrapping exceptions:

~~~java
throw new IllegalStateException(
        "Cannot load catalog fileId=" + fileId,
        exception
);
~~~

Constructors accepting `cause` preserve root-cause information for upper-layer handlers to inspect.

## 14. Log messages should be structured and consistent

Compare:

~~~java
log.error("Error!");
~~~

with:

~~~java
log.error(
        "Payment reconciliation failed batchId={} processed={} rejected={}",
        batchId,
        processedCount,
        rejectedCount,
        exception
);
~~~

The second message helps you:

- Search by action.
- Match a specific unit of work.
- See how many items succeeded or failed.
- View the stack trace when needed.

Even so, only log fields **that genuinely help diagnostics**. Unnecessary fields clutter logs and increase storage costs.

### Prefer key=value or consistent structured fields

A simple convention:

~~~text
event=order_created orderId=ORD-1052 itemCount=3 durationMs=85
~~~

When using a backend supporting JSON/structured logging, these fields can become actual structured log event fields, letting systems query them without string parsing. How structured logging is configured depends on the stack and Spring Boot/backend version; do not assume writing `key=value` alone automatically produces JSON fields.

Keep field names consistent—such as `orderId`, `batchId`, and `durationMs`—rather than arbitrarily switching between `id`, `order_id`, and `orderNumber` across classes.

## 15. Parameterized logging to avoid unnecessary string concatenation

SLF4J supports `{}` placeholders:

~~~java
log.debug(
        "Calculating price orderId={} itemCount={}",
        orderId,
        itemCount
);
~~~

Advantages:

- Consistent, readable messages.
- Avoids building concatenated strings unnecessarily in many cases when DEBUG is disabled.
- Eliminates calling `String.format(...)` for simple logs.

Compare:

~~~java
// Less ideal if DEBUG is disabled most of the time:
log.debug("Calculating price for " + orderId);

// Preferred:
log.debug("Calculating price for {}", orderId);
~~~

**An important performance note:** Java still evaluates expressions passed as arguments **before invoking the method**. Placeholders do not automatically stop an expensive computation from running.

Example:

~~~java
log.debug(
        "Full diagnostic snapshot={}",
        expensiveSnapshot()
);
~~~

`expensiveSnapshot()` still runs even when DEBUG is disabled.

Appropriate approach:

~~~java
if (log.isDebugEnabled()) {
    log.debug(
            "Full diagnostic snapshot={}",
            expensiveSnapshot()
    );
}
~~~

Similarly, use `log.isTraceEnabled()` for expensive computations needed only at TRACE.

### Do not overuse isDebugEnabled() checks

When variables are already in hand:

~~~java
log.debug("Order id={} status={}", orderId, status);
~~~

wrapping in `if (log.isDebugEnabled())` is usually unnecessary. Explicit guards are mainly helpful when computing arguments, serializing objects, or building diagnostic payloads is genuinely expensive.

## 16. Practical service example: choosing levels across a task lifecycle

Suppose an application needs to import a text file, one record per line. We only simulate counting lines without logging individual records.

~~~java
package com.example.imports;

import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class TextImportService {

    private static final Logger log =
            LoggerFactory.getLogger(TextImportService.class);

    public long countRecords(Path source, String importId)
            throws IOException {

        long startedAt = System.nanoTime();

        log.info("Text import started importId={}", importId);

        long count = 0;

        try (BufferedReader reader = Files.newBufferedReader(
                source, StandardCharsets.UTF_8)) {

            while (reader.readLine() != null) {
                count++;

                if (log.isTraceEnabled()) {
                    log.trace(
                            "Text import progress importId={} line={}",
                            importId,
                            count
                    );
                }
            }

            long durationMs =
                    (System.nanoTime() - startedAt) / 1_000_000;

            log.info(
                    "Text import completed importId={} records={} durationMs={}",
                    importId,
                    count,
                    durationMs
            );

            return count;
        } catch (IOException exception) {
            log.debug(
                    "Text import failed before completion importId={}",
                    importId,
                    exception
            );
            throw exception;
        }
    }
}
~~~

In the example:

- **INFO** for import start and completion milestones.
- **TRACE** for per-line progress, normally hidden by default.
- **DEBUG** for technical context at the service layer when the exception will be propagated to the caller.
- The caller or boundary decides whether to log WARN/ERROR depending on recoverability.
- `try-with-resources` closes `BufferedReader` after reading or upon failure.

The code takes a `Path` as input for the import task and does not validate the source itself. In a real application, check permissions, size, and file format before reading, especially if the path originates from a request.

### What if per-line TRACE is not needed?

For very large files, even a TRACE check inside the loop may be unnecessary detail. You can replace it with metrics or batch progress logs:

~~~java
if (count % 10_000 == 0) {
    log.debug(
            "Text import progress importId={} records={}",
            importId,
            count
    );
}
~~~

Whether progress belongs at INFO or DEBUG depends on job duration and operational needs. If a job processes millions of lines, logging every 10,000 lines can still be noisy; pick a reasonable interval.

## 17. Avoid using ERROR for every HTTP 4xx

In a REST API, a common case is a request failing validation:

~~~text
POST /orders
HTTP 400 Bad Request
{"message":"quantity must be positive"}
~~~

If clients send invalid input as part of normal operation, do not automatically log:

~~~java
log.error("Invalid quantity", exception);
~~~

At high traffic, that produces many ERRORs that do not reflect server failures.

Instead:

- Return 400 with a safe user-facing message.
- Log DEBUG if details are needed for investigation.
- Measure 4xx rates with HTTP metrics.
- Use dedicated security/audit logging if abuse detection is needed.

Conversely, an HTTP 500 caused by a code bug or unrecoverable dependency is usually a signal to log ERROR at the request boundary, if the framework or monitoring system has not already logged sufficient detail.

### Do not mechanically map HTTP status to log level

Some examples:

| HTTP status | Must log ERROR? | Notes |
|---|---|---|
| 200 OK | No | Metrics alone may suffice |
| 400 Bad Request | No | Invalid input may be expected |
| 401 Unauthorized | No | Depends on audit/security policy |
| 404 Not Found | No | Often a valid outcome |
| 429 Too Many Requests | No | Usually tracked via metrics; possibly WARN on abnormal spikes |
| 500 Internal Server Error | Usually considered | Server error needing investigation |
| 503 Service Unavailable | Depends on cause | Could be maintenance, readiness, or dependency outage |

Choose levels based on impact and operational policy, not merely on the HTTP status code.

## 18. Which level should be enabled in production?

No single configuration fits every system. A manageable starting point is often:

~~~properties
logging.level.root=INFO
logging.level.com.example=INFO
~~~

When investigating a module:

~~~properties
logging.level.com.example.payments=DEBUG
~~~

If a library generates too many unnecessary lines:

~~~properties
logging.level.org.springframework.web=WARN
~~~

However, **do not lower a whole package's level just to hide an ongoing issue**. Before suppressing logs, understand which messages are being dropped and whether they carry valuable warnings.

### Environment-based configuration

You can use profile files:

~~~text
application.yml
application-dev.yml
application-prod.yml
~~~

Example `application-dev.yml`:

~~~yaml
logging:
  level:
    root: INFO
    com.example: DEBUG
~~~

Example `application-prod.yml`:

~~~yaml
logging:
  level:
    root: INFO
    com.example: INFO
~~~

When the corresponding profile is active, profile-specific configuration is loaded into externalized configuration. The actual level still depends on higher-precedence sources such as environment variables and command-line args.

### Do not leave root TRACE enabled long-term in production

Enabling TRACE system-wide can:

- Generate enormous logs from HTTP stacks, ORMs, databases, and libraries.
- Increase CPU, I/O, and collection costs.
- Make searching difficult due to noise.
- Expose sensitive metadata or data when libraries log details.
- Put pressure on collectors or storage systems.

If TRACE is needed, select a narrow logger, set a time limit, monitor log volume, and plan to turn it back off.

## 19. Changing log levels at runtime

When production has an incident, restarting the entire application just to enable DEBUG may not be ideal.

If the project includes Spring Boot Actuator and access is appropriately configured, the **loggers endpoint** allows inspecting or changing logger levels in a running process.

Example endpoints:

~~~text
GET /actuator/loggers
GET /actuator/loggers/com.example.payments
~~~

In configuration allowing HTTP exposure:

~~~properties
management.endpoints.web.exposure.include=health,info,loggers
~~~

Whether the endpoint can be accessed and levels modified depends on the Spring Boot version, endpoint access settings, and the application's Spring Security policy. Do not treat a single `exposure.include` line as guaranteeing every log modification operation is permitted.

If write operations are permitted and the endpoint is properly secured, an adjustment request typically looks like:

~~~http
POST /actuator/loggers/com.example.payments
Content-Type: application/json

{"configuredLevel":"DEBUG"}
~~~

To revert the logger to having no explicit configured level:

~~~http
POST /actuator/loggers/com.example.payments
Content-Type: application/json

{"configuredLevel":null}
~~~

Here `null` means removing the logger's individual level so it inherits according to the applicable effective configuration. It does not necessarily mean "back to INFO" if the parent package has a different level.

**Security warning:** an endpoint that changes logger levels is an administrative capability that can drastically increase log volume and expose information through detailed logs. Do not expose this endpoint publicly without authentication, authorization, and operational controls.

Remember that runtime changes may not persist across restarts, and instances in a cluster may need to be updated individually or through a centralized configuration management mechanism.

## 20. Log volume, performance, and cost

Choosing log levels is not just about content. It also affects data volume:

~~~text
10,000 requests/minute
       x
5 INFO lines/request
       =
50,000 INFO lines/minute

If each line averages 500 bytes:
50,000 x 500 = 25,000,000 bytes/minute
~~~

These numbers are purely illustrative and exclude additional metadata, indexing, replication, compression, or collector overhead.

Enabling DEBUG for an active library can inflate log volume far beyond expectations.

Control measures:

1. Log **meaningful milestones**, avoiding INFO for every minor operation.
2. Reserve DEBUG/TRACE for investigative detail and keep them off by default.
3. Use metrics for counts, rates, latency, and error percentages.
4. Use distributed traces to follow cross-service flows.
5. Apply sampling/aggregation where supported by collection tools.
6. Maintain retention and access policies per operational requirements.
7. Do not use logs as a substitute for business data that must be stored consistently.

### Logs do not replace metrics

If the question is "what was the 5xx error rate over the last 5 minutes?", metrics are usually much more efficient than scanning millions of logs.

If the question is "why did the request for a specific orderId fail?", logs with correlation IDs and stack traces are usually more useful.

If the question is "which services did the request visit and how long did each step take?", distributed tracing fits better.

These three tools complement each other; do not force every observability problem into a log level.

## 21. Logs must be safe with sensitive data

A severe mistake is logging entire requests or objects:

~~~java
log.debug("Login request={}", loginRequest);
~~~

If `loginRequest.toString()` includes a password or token, that value can leak into logs. Enabling DEBUG to investigate would inadvertently expose sensitive data.

Do not log:

- Passwords, refresh tokens, access tokens, API keys.
- Session cookies or `Authorization` headers.
- Payment card numbers, security codes, or private keys.
- Personal information beyond what is necessary.
- Full payloads when they contain sensitive data.
- Connection strings containing usernames/passwords.

Instead of logging the whole request:

~~~java
log.debug(
        "Authentication attempt method={} clientId={}",
        authMethod,
        safeClientId
);
~~~

Some identifier fields can still be personal or sensitive data depending on context, so apply system minimization, masking, or pseudonymization policies.

### TRACE has no special access privileges

Enabling TRACE does not alter data policies. Do not place secrets in TRACE assuming production is safe because TRACE is normally off. Log levels can be turned up during incidents, and logs can be shipped to multiple storage systems.

### Exception messages can also leak secrets

A library may embed URLs with sensitive query parameters or response bodies into an exception's message. When forwarding exceptions to observability systems, define trust boundaries and data protection mechanisms. Never record verbatim content that users are not permitted to see.

## 22. Correlation ID, trace ID, and log context

In systems with many concurrent requests, knowing only the timestamp and class name is often insufficient.

Example:

~~~text
INFO  Order validation started
INFO  Order validation started
ERROR Payment failed
INFO  Order validation completed
~~~

Without a request ID, it is hard to tell which line belongs to which request.

You can add a correlation ID to the logging context using **MDC**:

~~~java
import org.slf4j.MDC;

String correlationId = "req-7fd91";

try {
    MDC.put("correlationId", correlationId);

    log.info("Validating order orderId={}", orderId);
    // Processing on the same thread.
} finally {
    MDC.remove("correlationId");
}
~~~

In Logback, the console pattern can be configured to print this value, for example:

~~~properties
logging.pattern.console=%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] [%X{correlationId}] %logger{36} - %msg%n
~~~

Then logs include the correlation ID whenever the MDC key exists on the thread.

**Note:** thread-bound MDC does not automatically carry intact across every `@Async` call, thread pool, or reactive pipeline. For asynchronous processing, an appropriate context propagation mechanism is required. In systems already using Micrometer Tracing or OpenTelemetry, leverage the trace/span context supplied by the observability stack instead of inventing inconsistent ID mechanisms.

INFO/DEBUG/WARN/ERROR levels retain their original meaning; the correlation ID simply ties entries into a processing flow.

## 23. Logging in background tasks and startup

Not every log appearing during startup has the same level.

Example:

~~~java
@Component
public class CatalogWarmup implements ApplicationRunner {

    private static final Logger log =
            LoggerFactory.getLogger(CatalogWarmup.class);

    @Override
    public void run(ApplicationArguments args) {
        log.info("Catalog warmup started");

        int imported = loadRequiredData();

        log.info("Catalog warmup completed records={}", imported);
    }

    private int loadRequiredData() {
        return 100;
    }
}
~~~

The snippet uses Spring Boot's `ApplicationRunner` and `ApplicationArguments` types along with Spring's `@Component`, assuming appropriate imports are present.

The start and completion of a mandatory startup step usually fit INFO. If loading an optional config file fails yet a valid fallback exists, WARN may fit. If startup cannot proceed because required data is missing, throw an exception so Boot handles the startup failure and logs the error at the startup boundary.

**There is no need to log ERROR every time an exception is caught and immediately rethrown to another layer** if Spring Boot already has a full failure-logging mechanism. What matters is a clear root-cause message and preserving the stack trace.

For schedulers or batch jobs, choose levels based on the outcome of **a single run**:

~~~text
Job started             -> INFO or DEBUG
Job completed           -> INFO
One item skipped        -> DEBUG, WARN if notable anomaly
One retry               -> DEBUG or WARN
Job failed completely   -> ERROR at boundary
~~~

Include `jobId`, processed count, and duration for investigative context.

## 24. Logging conventions for multiple teams in a project

A project with controllers, services, repositories, and integration adapters can follow a consistent policy:

| Component | Useful log content | Suggested level |
|---|---|---|
| Controller/API boundary | Processing outcome, unexpected errors | Selective INFO, ERROR at boundary |
| Business service | Business milestones, job outcomes, key states | INFO |
| Business service | Branch choices, technical context | DEBUG |
| Repository/data access | Queries or technical operations during investigation | Controlled DEBUG/TRACE |
| External adapter | Fallbacks, abnormal timeouts | WARN |
| External adapter | Unrecoverable failure after all attempts | ERROR at appropriate boundary |
| Scheduler/runner | Start/end milestones, processed counts | INFO |
| Parser/algorithm | Very fine-grained processing steps | TRACE |
| Security/audit pipeline | Security events per dedicated policy | Do not decide solely from this table |

One way to stay consistent is designating **who is responsible for logging the final error**. For example, controller advice logs ERROR for unexpected HTTP 500s; lower layers add context and preserve the exception chain instead of everyone logging errors.

### Audit logs differ from regular application logs

Events such as permission changes, financial transactions, or sensitive data access may require a dedicated audit trail with strict integrity, retention, and access controls. They must not rely merely on whether the root logger is currently at INFO or WARN.

An audit record may need to be persisted regardless of technical logging configuration changes. **Do not use log levels as the sole mechanism guaranteeing retention of regulatory events.**

## 25. Anti-patterns when choosing log levels

### Anti-pattern 1: "Every exception is ERROR"

Incorrect. An exception may simply signal a valid fallback, an expected validation failure, or a retry step.

Ask instead: **what ultimately happened to the operation?**

### Anti-pattern 2: "Production bug? Turn on root TRACE forever"

Avoid this. It creates massive log volume and data exposure risks. Enable a specific logger for a limited time, investigate, and then turn it off.

### Anti-pattern 3: "INFO for every method call"

Bad for high-traffic systems. Method-level details belong at DEBUG/TRACE, while INFO is for meaningful milestones.

### Anti-pattern 4: "Log only exception.getMessage()"

This can lose the stack trace and cause. When investigating real errors, pass `Throwable` to the logger properly.

### Anti-pattern 5: "Unconditional string concatenation and object serialization"

Even with DEBUG/TRACE disabled, code may still evaluate expensive arguments before the call. Use placeholders and guards when needed.

### Anti-pattern 6: "Log whole objects to make debugging easy"

This can record sensitive data, huge objects, or unstable `toString()` output. Log only necessary safe fields.

### Anti-pattern 7: "Repository logged ERROR, so service and controller log ERROR too"

Leads to duplication, making it hard to identify distinct errors. Assign error logging responsibility to boundaries.

### Anti-pattern 8: "When DEBUG is enabled, code should change behavior"

Do not do this. Logging configuration exists solely for observation; it must never affect business correctness. Watch out for code performing side effects inside an `if (log.isDebugEnabled())` branch.

### Anti-pattern 9: "No ERROR means the system is healthy"

Code might not be logging properly, the collector could be down, or the application might be receiving no traffic. Combine health checks, metrics, tracing, and alerting.

### Anti-pattern 10: "An ERROR was logged, so restart the server"

No. ERROR is a message priority, not a lifecycle control command. Restart decisions depend on health state and operational policies.

## 26. Hands-on exercises

### Exercise 1: Observe threshold filtering

Write code:

~~~java
log.trace("trace-message");
log.debug("debug-message");
log.info("info-message");
log.warn("warn-message");
log.error("error-message");
~~~

Successively configure the class logger to TRACE, DEBUG, INFO, WARN, and ERROR. Record which messages appear.

Expected results under simple threshold filtering:

| Effective level | Messages that appear |
|---|---|
| TRACE | TRACE, DEBUG, INFO, WARN, ERROR |
| DEBUG | DEBUG, INFO, WARN, ERROR |
| INFO | INFO, WARN, ERROR |
| WARN | WARN, ERROR |
| ERROR | ERROR |

### Exercise 2: Scope DEBUG to one package

Suppose the application has:

~~~text
com.example.catalog.CatalogService
com.example.payment.PaymentService
com.example.payment.GatewayClient
~~~

Requirement: keep general INFO, yet view DEBUG in the payment module.

Hint:

~~~properties
logging.level.root=INFO
logging.level.com.example.payment=DEBUG
~~~

Then observe logs from `CatalogService` compared to `PaymentService`. Do not change all log calls to INFO.

### Exercise 3: Choose levels by impact

Pick TRACE/DEBUG/INFO/WARN/ERROR or no log for each case:

1. A data-loading job finishes 20,000 records.
2. A payment attempt fails, yet a retry succeeds.
3. A parser iterates through 500,000 characters.
4. A malformed request returns HTTP 400 per the contract.
5. Invoice creation fails with no fallback.
6. An external service is slow; the application uses a still-valid cache.
7. A service chooses implementation `RuleA` for an input type.

Hints:

- (1) INFO for job completion.
- (2) DEBUG; consider WARN if retries are abnormal and worth tracking.
- (3) Selective TRACE or no log; avoid per-character logging in production.
- (4) Usually not ERROR; metrics or selective DEBUG.
- (5) ERROR at boundary.
- (6) WARN for degraded mode with fallback.
- (7) DEBUG for technical decision.

### Exercise 4: Fix exception logging code

Suboptimal snippet:

~~~java
catch (IOException exception) {
    log.error("Read failed: " + exception.getMessage());
    throw new RuntimeException("Read failed");
}
~~~

Fix it to preserve the cause and avoid duplicating ERROR across multiple layers:

~~~java
catch (IOException exception) {
    throw new IllegalStateException(
            "Unable to read input fileId=" + fileId,
            exception
    );
}
~~~

Then choose an appropriate boundary to log:

~~~java
log.error("Import request failed", exception);
~~~

What matters is preserving the exception chain and avoiding multiple identical entries.

### Exercise 5: Optimize expensive DEBUG

What is wrong with this snippet?

~~~java
log.debug("Snapshot={}", objectMapper.writeValueAsString(hugeObject));
~~~

Even if the logger has DEBUG disabled, serialization still executes and consumes resources. You can use:

~~~java
if (log.isDebugEnabled()) {
    log.debug(
            "Snapshot={}",
            objectMapper.writeValueAsString(safeDiagnosticObject)
    );
}
~~~

Here `safeDiagnosticObject` must be reduced in size and stripped of sensitive fields. Do not turn DEBUG features into a backdoor data export bypassing security policy.

### Exercise 6: Class-level configuration via environment

Suppose you want TRACE specifically for:

~~~text
com.example.orders.OrderService
~~~

Explain why an all-uppercase environment variable with underscores may fail to preserve the exact casing of the class logger, then choose a more reliable configuration method, such as:

~~~properties
logging.level.com.example.orders.OrderService=TRACE
~~~

Or:

~~~bash
java -jar app.jar --logging.level.com.example.orders.OrderService=TRACE
~~~

If using the Actuator loggers endpoint, verify the effective level and endpoint access permissions.

## 27. Checklist for designing a project logging policy

Before finalizing logging guidelines, the development team should clarify:

1. **Which operational milestones deserve INFO?** E.g., startup ready, batch completed, config reload.
2. **Which anomaly signals require WARN?** E.g., fallbacks, high retries, resources nearing exhaustion.
3. **Which failures must be ERROR?** E.g., final request/job failures with no recovery path.
4. **Who is responsible for logging the final exception?** Avoid repeating stack traces at every layer.
5. **Are TRACE/DEBUG needed for any module?** Off by default, enabled when investigating.
6. **Which data must never be logged?** Define a sensitive-data list and masking policy.
7. **Which fields correlate logs?** E.g., safe requestId, traceId, orderId.
8. **How can log levels be changed?** Config files/profiles, command line, environment, secured Actuator.
9. **How are log volume and retention controlled?** Use metrics for repetitive quantities.
10. **Is logging coordinated with metrics, tracing, and auditing?** Do not treat logs as the sole tool.

A starting configuration might be:

~~~properties
# Typical application
logging.level.root=INFO

# Module under temporary investigation
logging.level.com.example.orders=DEBUG

# Optional: reduce unnecessary framework noise
logging.level.org.springframework.web=WARN
~~~

Adjust based on actual measurements and needs rather than copying every line verbatim across all services.

## Conclusion

The five basic log levels in Spring Boot/SLF4J follow the order:

~~~text
TRACE < DEBUG < INFO < WARN < ERROR
~~~

- **TRACE**: very deep execution-flow details.
- **DEBUG**: technical information to locate root causes and understand code decisions.
- **INFO**: meaningful normal operational milestones.
- **WARN**: abnormal, degraded, or risky situations that can still be handled.
- **ERROR**: critical operation failure or unrecoverable incident at an appropriate boundary.

Configuring a logger at `INFO` still allows `WARN` and `ERROR`, while filtering out `DEBUG` and `TRACE`. Spring Boot lets you adjust levels via `logging.level.root`, `logging.level.<package>`, or specific logger names, in config files, on the command line, and via other externalized configuration sources.

Most importantly, **choose log levels based on the event's meaning and impact**, not solely on whether the code threw an exception. Record sufficient context without duplicating errors, use parameterized logging sensibly, protect sensitive data, and combine logs with metrics/tracing so the application remains easy to operate at a reasonable observability cost.
