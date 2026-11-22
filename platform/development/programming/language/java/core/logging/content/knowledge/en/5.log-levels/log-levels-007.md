# Choosing the Right Level in Java Logging

A **log level** is a classification of the importance or purpose of a log event. Choosing the right level helps operators distinguish normal behavior, abnormal signs, and actual failures, while also controlling log volume in each environment. An event assigned the wrong level can cause errors to be missed because DEBUG is disabled, or trigger constant alerts even though every request is still succeeding.

In Java, level names differ between `java.util.logging` (**JUL**) and APIs/backends such as SLF4J, Logback, and Log4j 2. However, the general principle is to **evaluate the actual outcome, impact, and investigation needs** before choosing a logging level.

## 1. What Questions Does a Level Answer?

Before writing a logging statement, determine:

1. **Is the event expected in the normal flow?** For example, a user entering an incorrect password or requesting a non-existent resource are situations the application can handle proactively.
2. **Did the operation achieve the desired outcome?** A single API call attempt that times out but succeeds on retry is different from a request that ultimately fails.
3. **Is there service degradation or a risk signal that operators need to notice?** For example, falling back to an alternative, a queue nearing capacity, or resources running low.
4. **Does this data need to appear during normal production operation?** Intermediate variable checks are usually only needed when diagnostics are enabled.
5. **Who will take action when reading this log line?** The level should help the responsible person decide when to investigate, rather than merely expressing the author's emotion.

**Do not choose a level based solely on wording** in the message or the Java exception type. An `IllegalArgumentException` thrown from invalid input may be an expected error; a return value that throws no exception can still indicate a serious business failure.

## 2. Common Log Levels

| Purpose | Common SLF4J / Logback | Nearest JUL Equivalent | Selection Guideline |
| --- | --- | --- | --- |
| Very detailed step-by-step tracing | `TRACE` | `FINER` / `FINEST` | Only for deep investigation of execution flow; high volume, usually disabled in production. |
| Logic and technical state diagnostics | `DEBUG` | `FINE` | Intermediate values, branch decisions, individual retries; can be disabled during normal operation. |
| Important normal milestones | `INFO` | `INFO` | Startup complete, important job succeeded, state changes useful for operations. |
| Abnormalities still handled or needing observation | `WARN` | `WARNING` | Fallbacks, degraded state, approaching resource thresholds, repeated retries; requires context to evaluate. |
| An operation or component truly failed | `ERROR` | `SEVERE` | Critical request did not complete, system failed to start, dependency failure affecting the final outcome. |

This is only an **approximate semantic mapping**. JUL has the levels `SEVERE`, `WARNING`, `INFO`, `CONFIG`, `FINE`, `FINER`, and `FINEST`; `ALL` and `OFF` are used primarily for threshold configuration. `CONFIG` is for configuration information and has no one-to-one equivalent in SLF4J. Log4j 2 may provide `FATAL`; the standard SLF4J API does not define a corresponding `fatal()` method. Do not copy level names from one backend to another without checking the API.

In JUL, levels have priority values from highest to lowest: `SEVERE (1000)`, `WARNING (900)`, `INFO (800)`, `CONFIG (700)`, `FINE (500)`, `FINER (400)`, `FINEST (300)`. A typical `INFO` threshold accepts `INFO`, `WARNING`, and `SEVERE`, while excluding `CONFIG`/`FINE`/`FINER`/`FINEST`. Custom levels can exist, so this should not be treated as the exhaustive list for every application.

## 3. Decision Process for Choosing an Event's Level

The following decision tree can be used for discussion during code reviews. Suggested levels should be adjusted according to system conventions and operational requirements.

```text
An event just occurred
  |
  +-- Only intermediate state for diagnostics?
  |       +-- Yes -> DEBUG/FINE; ultra-detailed -> TRACE/FINER/FINEST
  |
  +-- Expected behavior, handled per contract?
  |       +-- Yes -> Logging not required; INFO if an important milestone,
  |                or DEBUG/FINE/access log if routine detail
  |
  +-- Abnormality, fallback, or degradation needing attention?
  |       +-- Yes, operation still succeeded -> WARN/WARNING when observation is needed
  |                (or INFO/DEBUG if fallback is routine behavior)
  |
  +-- Unexpected final failure?
          +-- Yes -> ERROR/SEVERE if it affects the operation/component
          +-- No -> INFO for noteworthy operational outcomes,
                       or do not log if it adds no value
```

This tree is not a mechanical rule: a security event may require a separate audit channel regardless of level, while a user error may be a valid rejection under the contract. **Impact must be evaluated at the business boundary**, where it is known whether the request succeeded, recovered, or failed.

### 3.1. Choosing INFO for Noteworthy Milestones

`INFO` is appropriate when an operation proceeds as expected and recording the event aids operations, for example:

- The service has finished starting up and is ready to serve traffic.
- An important batch job completed with the count of processed records.
- An authorized administrative action changed configuration state.
- An important request completed and requires business-level traceability.

It is not necessary to log `INFO` for every method call, every field check, or every successful HTTP request. For high-traffic services, detailed request logs may belong in a separately managed access log, metrics, or traces. An `INFO` line for every minor event can drown useful logs in noise.

**Good example:** `event=batch.completed jobId=job-9 processed=1200 failed=0 durationMs=2400`. This is a final outcome with clear context.

### 3.2. Choosing WARN/WARNING for Abnormalities That Have Not Caused Final Failure

`WARN`/`WARNING` indicates a situation that is not completely normal, poses a risk, or needs observation, even though the program can still serve requests:

- Having to switch to a standby replica when the primary data store is temporarily unavailable.
- A dependency call was too slow, was retried and succeeded, but total retry count increased significantly.
- A queue or memory usage is approaching a threshold identified as noteworthy.
- Received suboptimal configuration but a valid fallback value is available.

If a fallback is a normal mechanism occurring continuously by design without impacting the service, logging WARN on every occurrence can cause false alerts. You can choose INFO/DEBUG alongside aggregated metrics and emit a WARN when the degradation rate exceeds a threshold. Level names do not replace alert threshold definitions and system observability policies.

**Good example:** `event=inventory.fallback requestId=req-12 strategy=cache reason=upstream_timeout outcome=recovered`.

### 3.3. Choosing ERROR/SEVERE for Failures With Real Impact

`ERROR`/`SEVERE` is appropriate when **the final unit of work cannot complete** or a component cannot provide a required capability:

- The application cannot start due to missing essential configuration.
- A job terminates in failure after the allowed number of retries.
- A payment transaction cannot complete because a downstream dependency stopped responding.
- The service loses the ability to process a required feature and has no valid fallback.

Log errors where there is sufficient context about `operation`, `outcome`, `errorCode`, and `requestId`. For unexpected Java exceptions, pass the `Throwable` to capture the stack trace rather than only `ex.getMessage()`. A recovered error may fit WARN or DEBUG better than ERROR, because the overall outcome is still a success.

**Good example:** `event=payment.failed requestId=req-12 paymentId=pay-8 errorCode=UPSTREAM_TIMEOUT attempts=3 outcome=failed` (with `Throwable` when appropriate).

### 3.4. Choosing DEBUG/FINE and TRACE/FINER/FINEST for Diagnostics

`DEBUG/FINE` is meant for information needed when investigating a specific execution flow: deciding between cache and database, mapping a state, input element count after validation, or the chosen algorithm branch.

`TRACE/FINER/FINEST` is useful when a higher level of detail is needed: sequential steps in a parser, each small phase of an algorithm, or deep diagnostic details. Do not put full payloads or sensitive data at these levels under the assumption that "since it is off by default, it is safe."

**Example:** `event=pricing.rule_selected ruleId=rule-3 branch=member_discount` at FINE; enable selectively only for the component under investigation.

## 4. Practical Scenarios: The Same Technical Error May Need Different Levels

| Scenario | Final Outcome | Suggested Level | Reason |
| --- | --- | --- | --- |
| Server starts up successfully | Ready to serve | `INFO` | Lifecycle milestone worth recording. |
| Important order state change event | Processed successfully | `INFO`, depending on traffic | Useful for investigating business flows, if not overly frequent. |
| Checking each JSON field during parsing | Normal | `DEBUG/FINE` or do not log | Implementation detail, high frequency. |
| User submits malformed data, API returns 400 per contract | Rejected as expected | Access log, `DEBUG`, or `INFO` depending on policy | Do not automatically turn client errors into server incidents. |
| A request receives 404 due to non-existent path | Rejected per contract | Access log/`DEBUG` depending on policy | Not necessarily a system error. |
| Inventory call times out, subsequent retry succeeds | Request succeeds | `DEBUG` per attempt; `WARN` when abnormality is noteworthy | Distinguish a single attempt's failure from the overall request outcome. |
| Must use fallback cache because primary service failed | Recovered, but degraded | `WARN/WARNING` if observation is needed | Fallback available, not a final failure. |
| Job fails after all retries | Job failed | `ERROR/SEVERE` | Requires investigation and remediation. |
| Database connection cannot be established at startup | Service unavailable | `ERROR/SEVERE` | Blocks ability to serve. |
| Single login with wrong password | Expected rejection | Security event/audit per policy, `INFO`/`DEBUG` in app log as needed | Do not default to `ERROR` for every wrong entry; avoid exposing identities/secrets. |
| Unusually many failed login attempts | Potential security risk | Dedicated security event + alert per detection rules | Evaluate by pattern and context, not just per-request severity. |
| Latency increases across many requests | Service degraded | Metrics and alerts; optionally `WARN` for threshold-crossing state transitions | Logging each slow request does not replace SLOs/metrics. |
| An exception is caught and a valid fallback is returned | Handled successfully | `DEBUG`, or `WARN` if attention is needed | Do not log `ERROR` just because a stack trace exists. |

This table is a **selection guide**, not a mandatory rulebook. Teams should set their own criteria based on feature impact, target audience, frequency, audit requirements, and operational cost.

## 5. Retries, Fallbacks, and Exceptions: Avoid Confusing the Level of an "Attempt" With the "Outcome"

Consider calling a payment service with up to three attempts:

```text
attempt=1 -> timeout
attempt=2 -> timeout
attempt=3 -> success
final outcome -> payment succeeded
```

If every timeout is logged as ERROR with a full stack trace, the alerting system might report three critical errors even though the request ultimately succeeded. Instead, you can:

- Log each attempt at `DEBUG/FINE` with `attempt`, `maxAttempts`, and a categorized reason.
- Log `WARNING` if repeated retries are a noteworthy abnormality or increase latency.
- Log `INFO` for the successful business outcome if this event type has operational value.
- Log `ERROR/SEVERE` when **all attempts fail** and the final operation does not meet its contract.

However, if retries cause duplicate transactions, data loss, or SLA violations, the severity may be higher even if one attempt succeeded; evaluate the actual consequences.

### Logging a Throwable at the Responsible Boundary

With JUL, an example of handling a final failure:

```java
// Illustrative snippet inside a method; assume LOG and requestId already exist.
try {
    performPayment();
} catch (RuntimeException error) {
    LOG.log(
        java.util.logging.Level.SEVERE,
        "event=payment.failed requestId=" + requestId,
        error
    );
    throw error;
}
```

The example above is **not a standalone program**: `performPayment()` is an application method. Passing `Throwable` to the `log(Level, String, Throwable)` overload preserves the exception information in the record so an appropriate handler/formatter can output the stack trace. Using `error.getMessage()` alone easily loses the error origin and stack trace.

Only log and rethrow here if this layer is responsible for recording the error. If a controller or exception handler also logs the same exception, duplicate ERROR records will appear. Define a primary responsibility boundary and use error codes and correlation IDs to link events across layers.

## 6. Levels in JUL: Both Logger Threshold and Handler Threshold Apply

The **record level** (attached to each event) and the **logging output threshold** (configuration) are two distinct concepts. Simply writing `logger.fine(...)` does not guarantee a FINE line will appear in the console.

In JUL, an event must pass at least two control checks:

```text
Call logger.log(Level, message)
             |
    Does Logger allow the level?
          /       \
         no       yes
         |          |
      ignored   LogRecord reaches handler
                    |
          Does Handler allow the level?
                /       \
               no       yes
               |          |
            ignored   format -> output
```

Per-logger or per-handler filter configurations can add further filtering steps. Records can also be forwarded to a parent logger's handlers, depending on `useParentHandlers`, but **the parent logger's level is not necessarily used to re-filter a record already accepted by a child logger on its way to a parent handler**. Therefore, it is important to understand which level controls the threshold and what the handlers are actually doing.

For example:

- Logger `INFO`, handler `ALL`: `FINE` records are rejected by the logger; `INFO/WARNING/SEVERE` can reach the handler.
- Logger `FINE`, handler `INFO`: the logger allows FINE, but the handler rejects FINE.
- Logger `FINE`, handler `ALL`: FINE can appear if not blocked by another filter.
- Logger with `level=null`: inherits the effective level from the nearest ancestor logger with a defined level; it does not mean all levels are allowed.

In SLF4J, enabling levels and output destinations depends on the backend/provider, because the `LoggerFactory` facade is only an API entry point. JUL's `logging.properties` configuration does not automatically control loggers served by Logback or Log4j 2.

## 7. Complete Java 17 Example: Selecting Levels and Observing Filtering Thresholds

This example uses JUL and requires no libraries outside the JDK. For consistent stdout across machines, the program configures a handler writing to `System.out`, omits the default timestamp formatter, and disables parent handlers.

Save to **`LogLevelSelectionDemo.java`**:

```java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class LogLevelSelectionDemo {
    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.checkout");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        Handler output = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " "
                        + formatMessage(record) + System.lineSeparator();
            }
        });
        output.setLevel(Level.ALL);
        logger.addHandler(output);

        try {
            // Logger level is currently INFO, so FINE is dropped.
            logger.fine("event=diagnostic.dropped_by_logger");

            // The following events simulate independent scenarios.
            logger.info("event=service.ready");
            logger.log(
                    Level.WARNING,
                    "event=inventory.fallback requestId={0}",
                    "req-12"
            );
            logger.log(
                    Level.SEVERE,
                    "event=job.failed jobId={0} reason={1}",
                    new Object[]{"job-9", "timeout"}
            );

            // Enable FINE on the logger, but the handler still blocks it.
            logger.setLevel(Level.FINE);
            output.setLevel(Level.INFO);
            logger.fine("event=diagnostic.dropped_by_handler");

            // When both thresholds allow it, FINE is output.
            output.setLevel(Level.ALL);
            logger.fine("event=diagnostic.visible");
            output.flush();
        } finally {
            logger.removeHandler(output);
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac LogLevelSelectionDemo.java
java LogLevelSelectionDemo
```

**Exact standard output** (excluding the command prompt):

```text
INFO event=service.ready
WARNING event=inventory.fallback requestId=req-12
SEVERE event=job.failed jobId=job-9 reason=timeout
FINE event=diagnostic.visible
```

Why does this output make sense?

1. `event=diagnostic.dropped_by_logger` has level `FINE`, which is lower than `INFO`, so the logger does not accept it.
2. `service.ready` is a normal milestone so it uses `INFO`; it appears because both the logger and the handler allow it.
3. `inventory.fallback` uses `WARNING` because the service can still continue using a fallback solution, but it needs attention.
4. `job.failed` uses `SEVERE` because it is the final failure of a job; this event simulates a different job from the earlier lines, not a consequence of `service.ready`.
5. After `logger.setLevel(Level.FINE)`, a FINE event can reach the handler, but it is still rejected by the handler whose threshold is `INFO`.
6. After `output.setLevel(Level.ALL)`, `event=diagnostic.visible` appears. `formatMessage(record)` handles JUL-style parameters `{0}`, `{1}`; `output.flush()` ensures buffered content is flushed before `main` exits.
7. `setUseParentHandlers(false)` prevents records from being forwarded to parent logger handlers and avoids duplicate log lines from other JUL console configurations.

This is a teaching example, not a recommendation to manually construct handlers in every business operation. Real applications typically configure log levels and appenders/handlers at startup.

## 8. Configuring Levels in Development and Operations

### Centralized Configuration by Component

Suppose the code uses loggers named after classes such as `com.example.orders.OrderService`. To investigate the orders area, you can enable more detail on the package prefix instead of having the entire application output FINE.

Example `logging.properties` file for JUL:

```properties
# Root logger level.
.level=INFO

# Increase verbosity only for the orders area.
com.example.orders.level=FINE

# Console must be permissive enough to print FINE.
handlers=java.util.logging.ConsoleHandler
java.util.logging.ConsoleHandler.level=FINE
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
```

Once the `com.example.Main` class is compiled, you can launch it using the pattern:

```bash
java -Djava.util.logging.config.file=logging.properties com.example.Main
```

This command **illustrates configuration loading**, not running the demo in Section 7 (which configures levels and handlers programmatically). When observing the results, verify that the program is using JUL, the logger name matches the configured prefix, the configuration was loaded, the handler is not re-filtering `FINE`, and no code is overriding the level elsewhere. Across different backends, configuration syntax and precedence rules vary.

### Choosing Defaults by Environment

| Environment / Purpose | Sensible Starting Point | Additional Conditions |
| --- | --- | --- |
| Local development | `INFO`, enable `DEBUG/FINE` for the module under development | Ensure logs do not expose tokens or real data. |
| Test/CI | `INFO` and enable diagnostics per test when investigating | Do not let meaningless logs drown out test results. |
| Normal production | `INFO` or higher in most components; controlled verbosity | Depends on traffic, system regulations, and log retention policies. |
| Time-boxed production investigation | Enable `DEBUG/FINE` for the needed package or instance | Limit scope, duration, volume, and access permissions. |
| Noisy dependencies | Raise the threshold specifically for that namespace | Avoid suppressing warnings/errors that truly need to be seen. |

Do not set `OFF` system-wide as a fix for excessive logs: critical incidents could be missed. Similarly, do not enable `ALL` broadly in production without knowing the data volume, cost, and information exposure risk.

### Levels Do Not Replace Metrics, Traces, or Alert Rules

A `WARN` log does not automatically mean "wake up the on-call engineer immediately." Alerts should consider occurrence counts, error rates, latency, blast radius, or service health. Rare critical errors may trigger immediate alerts, whereas repeated alerts for a controlled fallback need appropriate thresholds.

Changing a level can cause dashboards and alerts to miss an event type if they depend on `ERROR` or `WARN`. When adjusting levels in code review, also evaluate collector configs, retention, filters, and monitoring rules.

## 9. Avoiding Common Mistakes When Choosing Levels

### Mistake 1: Every Exception Is an ERROR

A `catch` block might handle invalid input, complete a successful retry, or recover with a fallback. If the business operation achieved a valid outcome, logging ERROR usually misrepresents the situation. Distinguish **technical exceptions** from **the impact of the final outcome**.

### Mistake 2: Logging Major Failures at DEBUG

If an important job ultimately fails but is only logged at `FINE/DEBUG`, the information may be dropped in production. Log an event at `ERROR/SEVERE` at the responsible boundary, with an error code and enough context for investigation.

### Mistake 3: Logging the Same Exception Multiple Times

An exception passing through repository, service, and controller layers can generate three ERROR stack traces. Identify the primary error-logging boundary, and rely on exception propagation and request/correlation IDs so you do not need to repeat full logs at every layer.

### Mistake 4: Logging WARN for Routine Operations

If cache misses, user typos, and single retries are normal operations, logging a `WARN` each time will cause operators to stop trusting warning logs. Log DEBUG/INFO as needed, and use metrics to detect abnormal frequencies.

### Mistake 5: Mechanically Choosing Levels Based on HTTP Status

Not every 4xx is `WARN/ERROR`, nor is every 5xx the same severity for the current system. Look at responsibility and business state. For example, a 404 caused by a user requesting a non-existent URL differs from a 404 from an internal service when required data should exist.

### Mistake 6: Confusing "Logger Enabled" With "Log Guaranteed to Appear"

JUL has levels on both loggers and handlers; other backends have their own loggers, appenders, and filters. When an expected log does not appear, check the effective threshold, handler, propagation, formatting, and output destination before changing the event's severity.

### Mistake 7: Using DEBUG to Hold Prohibited Data

Tokens, passwords, session cookies, private keys, and unnecessary personal data must be excluded from logs at **all levels**. A log level that is off by default is not a security control; the level can be enabled during diagnostics or retained by a collector.

### Mistake 8: Choosing a Level Based on Wording Without Outcome

`"Cannot connect"` could be an attempt being retried, a successful fallback, or a service-halting outage. Text content alone is not enough to decide between WARN and ERROR. Logs should state `attempt`, `outcome`, `errorCode`, and the final result when needed.

## 10. Checklist for Reviewing a Log Line

Before merging a logging statement or changing a level, check:

- **Outcome:** did the operation succeed, degrade, or ultimately fail? Does the level accurately reflect that state?
- **Expectedness:** is the situation a valid part of the contract, such as a validation failure?
- **Actionability:** when reading INFO/WARN/ERROR, will operators know what to do and where to look?
- **Information:** are the event code, component, correlation ID, cause, and appropriate exception details included?
- **Frequency:** how many events will this level generate under load? Will it cause alert fatigue or excessive cost?
- **Consistency:** do other teams, services, and dependencies use levels with the same meaning?
- **Observability:** do the logger and handler/appender actually allow that level to appear in the target environment?
- **Security:** does the event contain secrets, sensitive data, or unsanitized input?
- **Monitoring:** will changing the level affect alert rules, dashboards, the logging pipeline, or retention?

**Rule of thumb:** Choose a level based on *the impact that occurred* and *the operational value of the event*. `INFO` explains normal milestones, `WARN/WARNING` highlights abnormalities needing attention, `ERROR/SEVERE` marks impactful failures, and `DEBUG/FINE` and `TRACE/FINER/FINEST` are for investigative details. Then verify the logger and output destination configuration so important events are actually recorded.