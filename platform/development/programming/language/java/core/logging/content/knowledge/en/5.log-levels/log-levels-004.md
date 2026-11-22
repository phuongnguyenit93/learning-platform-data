# WARN — Warning Level in Java Logging

## 1. What Does WARN Mean?

**WARN (warning)** is a log level used for an **unexpected condition that poses a risk of causing issues or degrading operational quality**, but without sufficient evidence to conclude that the current operation has completely failed. A good WARN helps operators recognize risks, degradation, or situations where the system is compensating via a fallback mechanism.

For example, a service calls the primary payment gateway and encounters a timeout, but a backup route is available. If the system switches to the backup route and continues completing the order, a message stating "primary gateway unresponsive, switched to backup" is typically valuable at the WARN level. If both routes fail and the order cannot be completed, that failure is usually better suited for ERROR.

**WARN describes the severity and attention level of an event**, not a command instructing the application to stop, automatically retry, send a notification, or roll back. Calling `logger.warn(...)` itself only emits an event into the configured logging pipeline; it does not alter Java's control flow.

Across popular Java libraries:

- **SLF4J, Logback, Log4j 2:** provide a level named `WARN`; the typical call is `logger.warn(...)`.
- **JDK's `java.util.logging` (JUL):** the equivalent level by purpose is `java.util.logging.Level.WARNING`; the call is `logger.warning(...)` or `logger.log(Level.WARNING, ...)`. JUL does not declare a `Level.WARN` constant.
- **Common ordering** in backends using DEBUG/INFO/WARN/ERROR is `TRACE < DEBUG < INFO < WARN < ERROR`. When the threshold is WARN, logs at WARN and more severe levels are typically accepted; INFO and DEBUG are filtered out. JUL has its own set of names and levels, such as `INFO < WARNING < SEVERE`.

Therefore, "WARN" is a general concept, while **the exact API names, priority levels, filters, and log destinations depend on the framework/backend**.

## 2. When Should You Log WARN?

Use WARN when there is a **concrete, notable, and actionable or trackable signal**, such as:

1. **The system is operating in a degraded state:** a dependency is slower than the allowed threshold, and the system uses a fallback or backup data.
2. **There is a risk of an incident if the condition persists:** latency is rising abnormally, queues are nearly full, connections are close to exhaustion, or retry counts are climbing.
3. **Unexpected but still recoverable behavior:** configuration is suboptimal and the system must fall back to an approved default value.
4. **A condition that does not yet break business logic but requires verification:** auxiliary data is missing and the system applies a fallback rule that may affect output quality.
5. **Significant state transitions:** switching to degraded mode or a circuit breaker transitioning to OPEN; these state transitions are usually more useful than logging the same error on every single request.

Example of a contextual message:

```text
WARN payment-service orderId=O-17 correlationId=req-21 dependency=primary-gateway outcome=FALLBACK_SELECTED reason=TIMEOUT
```

Reading this message, an operator knows **which service, which transaction, which dependency encountered what condition, and how the system reacted**. It does not yet claim that the order ultimately succeeded, because the fallback can still fail. If the fallback actually succeeds, a subsequent event (typically INFO) is needed to report the final outcome.

There is no rule that "every `Exception` must be WARN" or "every retry must be WARN." You need to evaluate the actual impact, frequency, business expectations, and actionability.

## 3. Distinguishing WARN from Neighboring Levels

| Level | Practical Meaning | Example |
| --- | --- | --- |
| **DEBUG / TRACE / FINE** | Technical details for investigation, usually not needed in normal operations. | A normal cache miss before reading from the database. |
| **INFO** | Expected operations or states that have occurred. | An order is received or completed successfully. |
| **WARN / WARNING** | Anomaly, risk, or degradation needing attention; the operation may still complete. | Primary gateway timed out, switching to fallback. |
| **ERROR / SEVERE** | Significant failure: a critical operation or capability could not be fulfilled per its contract. | Payment failed because both primary and backup routes failed. |

This table reflects common design conventions, **not a rigid rule applicable to every project**. A similar event may belong at different levels if expectations and impact differ. A pre-designed retry that occurs regularly might only need DEBUG; a prolonged timeout wave leading to degraded mode should be WARN. A request legitimately rejected due to invalid input is usually not a system ERROR.

Three questions help choose the right level:

- **Is it unusual relative to the operational contract?** If not, usually use INFO/DEBUG or a metric.
- **Has the current action failed significantly?** If yes, consider ERROR; if not, yet it is degraded or poses a risk, consider WARN.
- **Is the signal useful for decision-making?** If WARN is emitted every second and nobody can distinguish or act on it, you need to change where it is logged, its structure, or its aggregation mechanism.

**A WARN event does not guarantee the entire request succeeded**; and an ERROR does not necessarily crash the whole process. They simply indicate severity according to your logging policy.

## 4. Placing WARN at the Right Moment in Business Flows

Example of a two-route payment flow:

```text
Start payment
        |
        v
Call primary gateway
        |
    +---+---+
    |       |
 Success   Timeout / unavailable
    |       |
    v       v
  INFO    WARN: primary route degraded,
success   selecting fallback
            |
            v
       Call backup gateway
            |
        +---+---+
        |       |
     Success  Failure
        |       |
        v       v
      INFO    ERROR:
   completed  payment failed
```

Explanation:

- WARN is emitted **when a meaningful anomaly is detected** (the primary gateway is unresponsive) and the decision is made to switch to the fallback.
- WARN must not inaccurately state "completed via fallback" before the fallback has actually finished.
- If the fallback succeeds, a log or metric confirms that the operation completed.
- If the fallback fails, log the error at the appropriate handling boundary. Avoid logging the exact same stack trace repeatedly in the gateway adapter, service, and controller unless new context is added.
- A retry does not always need a WARN. In a system performing thousands of retries, it is better to log on **state transitions**, threshold breaches, or behavior changes.

For background tasks such as sync jobs, "job is 2 minutes behind schedule" may be WARN if that delay is meaningful; "job could not complete and exhausted all recovery mechanisms" is usually ERROR. The 2-minute threshold is only an example: a project must define thresholds based on its SLOs and actual business needs.

## 5. Information Needed in a Useful WARN

A WARN message should provide enough detail to find the root cause and assess impact, while avoiding data exposure.

| Component | Purpose | Example |
| --- | --- | --- |
| Timestamp | Places the event on a timeline; prefer timestamps with offset/UTC. | `2026-11-09T08:00:00Z` |
| Service/component | Identifies where the event occurred. | `payment-service` |
| Event/operation code | Enables stable filtering and aggregation even when wording changes. | `PAYMENT_GATEWAY_TIMEOUT` |
| Level | Indicates this is a warning. | `WARN` |
| Related entity | Traces the operation while limiting sensitive data. | `orderId=O-17` |
| Correlation ID | Finds processing steps belonging to the same transaction. | `correlationId=req-21` |
| Impact/reaction | Shows the degree of degradation and the system's action. | `fallback=selected` |
| Cause or threshold | Helps categorize the issue. | `reason=TIMEOUT`, `elapsedMs=3000` |

A structured event might look like this:

```json
{
  "timestamp": "2026-11-09T08:00:00Z",
  "level": "WARN",
  "service": "payment-service",
  "event": "PAYMENT_GATEWAY_TIMEOUT",
  "orderId": "O-17",
  "correlationId": "req-21",
  "dependency": "primary-gateway",
  "elapsedMs": 3000,
  "action": "SELECT_FALLBACK"
}
```

The values above are sample data to illustrate the schema. Timestamps must be captured at actual processing time in implementation; `correlationId` must be propagated consistently from the request, not regenerated randomly at each layer.

**Do not include in WARN**: passwords, OTPs, cookies, access tokens, refresh tokens, private keys, full requests/responses containing sensitive data, emails/phone numbers when unnecessary, or unfiltered full domain objects. If a stack trace must be recorded, choose an appropriate level and timing so you do not generate thousands of duplicate copies or leak secrets inside exception messages.

## 6. How Does WARN Flow Through the Logging Pipeline?

Calling `logger.warn(...)`/`logger.warning(...)` does not directly guarantee that the record will appear where you query it. A simplified diagram:

```text
Code emits WARN
    |
Logger and level check
    |
Filter / enrichment / redaction
    |
Handler or appender
    |
Formatter/encoder (text, JSON ...)
    |
stdout / file / network
    |
Collector / storage (if any)
    |
Queries, dashboards, alerts
```

When an expected WARN does not appear, check:

1. **Logger threshold:** Does the logger allow WARNING/WARN?
2. **Handler/appender threshold and filters:** A logger may allow the event, yet a specific sink can still drop it.
3. **Parent/additivity:** Is it propagated to a parent logger or multiple appenders, causing duplicate WARNs?
4. **Queue/sink:** If async, is the queue full or not yet flushed? Are there I/O, rotation, or connection issues?
5. **Collector/search:** Has the data reached the collector and been parsed/indexed properly? Is the time range or retention policy misconfigured?

For instance, if the backend uses an ERROR threshold, WARN will typically not appear; if it uses INFO, WARN will usually appear alongside INFO and ERROR. However, **handler/appender-specific filters** can alter the outcome. Never look at a single level setting and conclude the pipeline is working.

## 7. Standalone Java 17+ Example with `java.util.logging`

The JDK includes `java.util.logging` (JUL), where `Level.WARNING` serves the same purpose as WARN. The following example illustrates **when to log WARNING** as the system switches to a backup payment route, and why INFO remains appropriate for normal milestones.

Create a file named **`WarnLevelDemo.java`** with the following content:

```java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class WarnLevelDemo {

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("example.warn");

        // Do not use parent logger handlers to avoid printing duplicate records.
        logger.setUseParentHandlers(false);
        for (Handler handler : logger.getHandlers()) {
            logger.removeHandler(handler);
        }

        // INFO, WARNING, and SEVERE are all allowed through the logger.
        // FINE is dropped right at the logger threshold.
        logger.setLevel(Level.INFO);

        Formatter lineFormatter = new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " | "
                        + formatMessage(record)
                        + "\n";
            }
        };

        // Use stdout and flush each record to make the example easy to verify.
        StreamHandler output = new StreamHandler(
                System.out, lineFormatter) {
            @Override
            public synchronized void publish(LogRecord record) {
                super.publish(record);
                flush();
            }
        };
        output.setLevel(Level.ALL);
        logger.addHandler(output);

        String orderId = "O-17";
        boolean primaryAvailable = false;
        boolean backupAvailable = true;

        logger.fine("orderId=" + orderId + " internal route probe");
        logger.info("orderId=" + orderId + " payment started");

        if (primaryAvailable) {
            logger.info("orderId=" + orderId
                    + " payment completed through primary");
        } else {
            logger.warning("orderId=" + orderId
                    + " primary unavailable; trying backup");

            if (backupAvailable) {
                logger.info("orderId=" + orderId
                        + " payment completed through backup");
            } else {
                logger.severe("orderId=" + orderId
                        + " payment failed: no available route");
            }
        }
    }
}
```

Compile and run with JDK 17 or later, from the directory containing the file:

```bash
javac -encoding UTF-8 WarnLevelDemo.java
java WarnLevelDemo
```

**Exact stdout** when keeping the variables as shown in the example:

```text
INFO | orderId=O-17 payment started
WARNING | orderId=O-17 primary unavailable; trying backup
INFO | orderId=O-17 payment completed through backup
```

Line-by-line explanation:

1. `logger.fine(...)` does not appear because `Logger.setLevel(Level.INFO)` blocks the FINE level.
2. The first `logger.info(...)` describes a normal milestone: payment started.
3. Because `primaryAvailable = false`, the program logs **WARNING**: the primary route encountered an issue and the system is trying the backup. It does not yet conclude that the transaction succeeded.
4. Because `backupAvailable = true`, the program logs INFO confirming the final result: the backup route completed the payment.
5. The `logger.severe(...)` branch only runs if the backup route is also unavailable; in the default run it **does not appear**. You can change `backupAvailable` to `false` to observe the failure condition, though stdout will differ from the sample above.

This is a **simulation of payment route availability**, and does not perform real HTTP requests, payments, retries, or transactions. Choosing WARNING/SEVERE messages represents a design decision; logging does not fix failures on its own.

**Why use `StreamHandler`?** JUL's `ConsoleHandler` typically outputs to `System.err`. The example intentionally uses `StreamHandler(System.out, formatter)` and flushes after every record so you see the exact output on stdout. `Formatter.format` deliberately omits the timestamp to ensure deterministic output for the lesson; in production, you should retain timestamps, component names, and correlation IDs.

**If you change the handler threshold** to `Level.SEVERE`, even a WARNING that passed the logger will not be emitted by this handler. That demonstrates how level gates can exist at multiple stages.

## 8. Using WARN in Applications with SLF4J

If a project uses SLF4J with a configured backend such as Logback or Log4j 2, code typically calls:

```java
// Illustrative snippet inside a service that already has an SLF4J logger.
// Not a standalone runnable Java SE program.
logger.warn(
        "Primary payment route unavailable: orderId={}, dependency={}, fallback={}",
        orderId, "primary-gateway", "selected");
```

This approach uses placeholders so the logging backend formats arguments according to the API. It can avoid unnecessary string concatenation overhead when WARN is disabled, and allows the backend to attach structured metadata depending on the tooling. However, **placeholders alone do not turn a message into separate JSON fields**: you need logging API/backend support for structured attributes or appropriate encoder/field-mapping configuration. Merely seeing `{}` does not prove that logs are structured.

When an exception is needed:

```java
// Illustration in a service class with logger, orderId, and caughtException.
// Choosing to log WARN once at a meaningful handling boundary.
logger.warn(
        "Primary gateway failed; fallback selected for orderId={}",
        orderId,
        caughtException);
```

By common SLF4J convention, the trailing `Throwable` is the exception cause, whose stack trace is printed by the backend when configuration allows. Avoid inadvertently placing error messages containing tokens or personal data inside exceptions. For frequent retries, consider logging WARN once on a state transition and using a metric to count retries, rather than printing a full stack trace every time.

**Note on dependencies:** The SLF4J snippets are illustrative code inside an application that already includes SLF4J and a backend; compiling them standalone requires the appropriate dependencies and logger declarations. The `WarnLevelDemo.java` program above uses pure JDK and needs no external libraries.

## 9. WARN, Retries, Fallbacks, and Circuit Breakers

These are the areas where the WARN level is most often overused.

### 9.1. Controlled Retries

Suppose an SDK automatically retries up to three times on transient network errors. If every request hits a first retry yet most complete quickly, printing WARN on every attempt can produce massive log volume. A practical policy:

- Log individual attempt details at DEBUG when investigation is needed.
- Use a `retry_total` metric or latency histogram to measure frequency and impact.
- Log WARN when consecutive thresholds are exceeded, when switching to a fallback, when latency breaches an SLO, or when operational action is required.
- If all mechanisms are exhausted and the operation fails, log the error once at the layer responsible for the outcome.

This does not mean **retries are always DEBUG**: a retry on a high-risk operation or one indicating dependency degradation may warrant WARN. The goal is to produce meaningful signals rather than noise.

### 9.2. Fallbacks

Fallbacks can keep a system running, but they usually come with trade-offs: staler results, lower accuracy, longer response times, or loss of secondary features. WARN should describe **that impact**, not just say "fallback invoked."

For example: `WARN catalog-service event=CACHE_STALE_SERVED ageSeconds=120 impact=stale_read reason=upstream_timeout`. If policy permits serving 120-second-old data and the condition is common/harmless, INFO or a metric may be more appropriate than WARN; the right level depends on the service contract.

### 9.3. Circuit Breakers

Circuit breakers typically have CLOSED, OPEN, and HALF_OPEN states. Logging WARN on a CLOSED -> OPEN transition caused by errors exceeding a threshold provides valuable information. Logging WARN on **every rejected request** while OPEN usually floods logs and obscures the state transition signal. It is better to log state changes with context, track blocked requests with a metric, and log recovery when the circuit breaker returns to normal.

### 9.4. Resource Limits

Memory, connections, thread pools, or queues approaching thresholds can be logged as WARN when they stay above a threshold for a defined duration. Avoid rapid flapping around the threshold by using hysteresis, confirmation windows, or periodic aggregation. If resource exhaustion causes business operations to fail, the incident log level may be ERROR. For system health, **metrics/alerts** are usually the primary channel; WARN serves as supporting context.

## 10. Operational Alerting: Do Not Treat Every WARN as an Incident

A WARN log **does not automatically mean waking up the on-call engineer**. A WARN line may represent a predictive indicator, a normal self-healing mechanism, or an event that has already been handled. Alerts should account for:

- **Frequency and trend:** the ratio of WARN to throughput, not just raw counts.
- **User impact:** latency, error rate, feature availability, and defined SLIs/SLOs.
- **Duration:** how long warnings repeat and whether recovery occurs.
- **Severity and actionability:** who needs to respond, and what is the first verification step?
- **Deduplication and grouping:** many WARNs from the same dependency may be a single issue, not thousands of independent incidents.

For example, a single successful fallback may just emit a WARN for observation. If 30% of payments fall back over 10 minutes and latency exceeds the target, the system may need a metric-based alert. The 30%/10-minute figures are illustrative only and must be determined from real traffic and product requirements.

If you use sampling or rate limiting to reduce WARN volume, understand which events may be dropped, how to measure drop counts, and the risk of hiding critical events. For **mandatory audit/security events**, do not rely on operational WARNs that might be filtered or dropped as your sole evidence; design a separate audit trail with appropriate retention and integrity guarantees.

## 11. WARN Message Quality and Common Mistakes

Comparing several ways to write messages:

| Message | Assessment |
| --- | --- |
| `WARN Something happened` | Too generic; lacks cause, scope, and impact. |
| `WARN Error processing request` | Ambiguous as to whether the request failed or a recovery mechanism is active. |
| `WARN orderId=O-17 dependency=primary-gateway reason=TIMEOUT action=TRY_BACKUP` | Includes specific cause, entity, and next step; easy to trace. |
| `WARN userPassword=... token=...` | **Wrong:** exposes sensitive data in logs. |
| `WARN Retry 1`, `WARN Retry 2`, `WARN Retry 3` for every request | Easily creates noise; review frequency, metrics, and logging policy. |

Common mistakes:

1. **WARN for normal operations:** e.g., routine `cache miss`, or requests missing a valid optional header. This keeps dashboards permanently yellow and destroys anomaly-detection value.
2. **WARN for business errors that have definitely failed:** if the operation's contract cannot be fulfilled, consider ERROR and the proper return result rather than simply lowering the log level.
3. **Logging WARN inside `catch` and rethrowing the exception, only for an upper layer to log the exact same ERROR:** creates duplicate stack traces. Pick one layer responsible for logging the outcome, and have other layers add context through appropriate mechanisms.
4. **Confusing logging with error handling:** calling `logger.warning(...)` does not retry, roll back, trip a circuit breaker, or notify the client; those actions must be explicitly implemented in code.
5. **Omitting service/operation/correlation IDs:** when multiple instances log concurrently, it becomes hard to correlate warnings with affected requests.
6. **Printing entire objects or uncontrolled exception messages:** leaks sensitive data and bloats log records.
7. **Using free-form strings without stable event codes:** changing wording breaks string-based queries and charts.
8. **Not monitoring dropped WARNs or ingest latency:** assuming no WARNs in storage means no problems exist.
9. **Looking only at ERROR logs during health checks:** missing WARNs that reflect prolonged degraded mode; conversely, not every WARN should be treated as a critical incident.

## 12. How to Test and Verify WARN Configuration

Practical test cases:

| Scenario | Expectation |
| --- | --- |
| Primary route works normally | No meaningless WARN generated; INFO or metric emitted as needed. |
| Primary route fails, fallback succeeds | WARN logged when degradation is detected; final outcome reflects success. |
| Both primary and fallback fail | Final failure trace logged at the proper level; no false success reported. |
| Backend threshold = ERROR | WARN may be filtered out by threshold; only more severe logs pass through. |
| Threshold = INFO, handler allows WARN | WARN is emitted, unless a filter or sink drops it specifically. |
| WARN contains quotes or newlines from input | Encoder escapes properly; no forged log lines and no leaked secrets. |
| Mass dependency failure | Useful WARN count, log-storm protection in place, dropped events measured if any. |
| Processing via thread pool/async | `correlationId` matches each request; no context leakage across thread reuse. |
| Collector or sink failure | Appropriate retry/metrics/alerting mechanisms; known durability and log-loss limits. |

When an expected WARN is missing, investigate in this order: **did code reach the warning branch? -> logger level -> filter -> handler/appender level -> sink/queue -> collector -> storage/query**. When seeing too many WARNs, check event creation conditions and frequency first before considering rate limiting or level adjustments.

## 13. Checklist Before Using WARN in Production

1. **Genuine anomalous condition:** warnings are emitted only when a clearly defined deviation, degradation, or risk occurs.
2. **Level chosen by impact:** INFO for expected progress, WARN for noteworthy anomalies that remain recoverable, ERROR for significant failures.
3. **Logged at the right time:** do not report fallback completion when it has only just started; do not claim request success before processing actually succeeds.
4. **Sufficient context included:** service, event code, dependency, permitted entity IDs, correlation ID, impact, and system reaction.
5. **No secrets exposed:** control fields, formatting, exceptions, and log access permissions.
6. **Noise controlled:** focus on meaningful state transitions/symptoms, combined with metrics and SLI/SLO-based alerting.
7. **Full pipeline verified:** levels/filters on both logger and appender, async buffers, collector, storage latency, and searchability.
8. **Repeatable tests:** exercise normal, degraded, fallback-success, and fallback-failure scenarios; verify outcomes and logs for each branch.

**Remember:** WARN is a signal that "a noteworthy condition has appeared that risks affecting the system." The value of WARN lies in **accuracy, context, and actionability**, not in writing a large volume of warning lines.