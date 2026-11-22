# ERROR — Log Level for Serious Failures in Java

## 1. What Does ERROR Mean?

In a logging architecture, **ERROR** is the log level used to report that an operation or component has encountered a **failure that is significant to the system or business**, requiring recording for investigation, remediation, or service health monitoring. Examples include: failing to save an order after exhausting all retry attempts; aborting a critical transaction because the storage system is unavailable; or failing to process a request due to an unexpected fault.

When seeing an ERROR, operators typically need to answer:

- **What failed?** The operation, service, component, and a stable error code.
- **What is the impact?** Did a single request fail, did a background job not complete, or is an entire component disrupted?
- **When and in what context did the error occur?** Timestamp, environment, deployment version, and request/trace correlation IDs.
- **What can be done next?** Retry, inspect dependent systems, recover data, route to manual processing, or fix the code.

ERROR is **not a generic label for every occurrence of an `Exception` object**. A normally handled exception might only warrant `DEBUG` or `WARN`; conversely, a severe business failure outcome may require ERROR even if no Java exception was thrown.

Comparative examples:

| Scenario | Typical Level to Consider | Reason |
| --- | --- | --- |
| A request is rejected because the user entered a negative amount | `INFO` or `DEBUG`; sometimes `WARN` depending on policy | Validation is working properly and does not prove a system fault. |
| An external service call times out once, but retries automatically and eventually succeeds | `WARN` or `DEBUG` | An anomaly occurred, but the logical operation still recovered. |
| After exhausting retries, a payment transaction cannot complete | `ERROR` | An operation with real-world impact has failed. |
| Required configuration cannot be read and the application fails to start | `ERROR`, or a higher severity level if supported by the backend | Core functionality is unable to operate. |
| A background task fails, but the system successfully moves it to a manual-processing queue | `WARN` or `ERROR` depending on business SLA | The decision depends on whether the task was actually handled and the level of impact. |
| Receiving HTTP 404 because a resource does not exist, matching expected API behavior | Usually not ERROR | An HTTP 4xx status does not automatically equate to a server failure. |

A log level is an **event classification policy**, not an exception-handling mechanism: logging ERROR does not automatically roll back a transaction, return HTTP 500, trigger a retry, or guarantee an alert.

## 2. Where Does ERROR Sit in the Log Level Scale?

The Java ecosystem has multiple APIs and backends with different level names.

| API / Backend | Related Level | How to Emit |
| --- | --- | --- |
| SLF4J (`org.slf4j.Logger`) | `ERROR` | `logger.error("Không thể hoàn tất thanh toán")` |
| Logback (popular SLF4J backend) | `ERROR` | Can configure an `ERROR` threshold on a logger/appender. |
| Log4j 2 | `ERROR` and a separate `FATAL` level | `logger.error(...)`; `FATAL` is a backend-specific option. |
| `System.Logger` (JDK 9+) | `System.Logger.Level.ERROR` | `System.getLogger("...").log(System.Logger.Level.ERROR, "...")` |
| `java.util.logging` (JUL) | **`SEVERE`**, there is no `Level.ERROR` constant | `logger.log(Level.SEVERE, "...")` |

In many real-world systems, a logger has a level ordering similar to:

```text
TRACE < DEBUG < INFO < WARN < ERROR
```

A `WARN` threshold typically accepts both `WARN` and `ERROR` events; an `ERROR` threshold only accepts ERROR and higher levels if the backend supports them. This ordering describes SLF4J/Logback/Log4j 2 conceptually; **do not copy the names TRACE/DEBUG/ERROR verbatim into JUL**, because JUL uses `FINEST`, `FINER`, `FINE`, `INFO`, `WARNING`, `SEVERE`, and a few other levels.

### ERROR vs. WARN

You can ask: **"Has the operation exhausted all recovery mechanisms under the current policy, and does the failed outcome have real impact?"**

- **WARN:** a sign of an anomaly or risk of failure; the system may still deliver an acceptable result. For example, a fallback replica had to be used, but the result is still valid.
- **ERROR:** a failure requiring investigation or action under the service policy. For example, the fallback replica also failed and the request ultimately errored out.

Do not mechanically apply the rule "caught exception = WARN, uncaught = ERROR." A caught exception that causes a business operation to fail can still be ERROR. Conversely, an exception caught by a framework and translated into a contract-compliant 400 response is not necessarily ERROR.

### Is ERROR Different from FATAL?

Some backends, such as Log4j 2, have a `FATAL` level to represent an exceptionally severe error that may prevent the application from continuing. Popular SLF4J and Logback setups only have `ERROR` as the highest level in the standard scale. **Do not assume every Java application has FATAL.** If losing the database connection brings down the entire service, you can still log ERROR and let health metrics or process orchestration reflect the severity of the outage.

## 3. When Should You Log ERROR?

Clearly define **processing boundaries** and **responsibility for the outcome**:

1. **Requests:** when an operation ultimately cannot be completed due to a server error or a critical dependency failure, after appropriate exception handling, fallbacks, or retries have been applied.
2. **Background jobs:** when a logical job fails and can no longer be automatically completed within the normal processing flow.
3. **Startup/configuration:** when missing required resources or invalid configuration prevent a component from starting or functioning properly.
4. **Integrity:** when an invalid state is detected, writing critical data fails, or a system invariant is violated that requires intervention.
5. **External dependencies:** when an external system causes the final request to fail. Transient errors being retried can be logged at WARN, while the final failure is logged at ERROR.

Example of a three-step payment flow:

```text
Payment gateway call 1 -> timeout
    -> WARN: will retry
Call 2 -> timeout
    -> WARN: continuing to retry (if attempts remain)
Final call -> timeout, retries exhausted
    -> ERROR: payment.failed, business outcome failed
```

If you log ERROR on all three timeouts and then log another ERROR at the outer HTTP layer, a dashboard might count multiple ERRORs for **a single failed transaction**. While not inherently invalid as logging, this makes the signal noisy and confusing. Clearly distinguish between **a technical error per attempt** and **a failure per logical operation**, along with a rule for where the final event is emitted.

**Log the error where the consequence can be interpreted.** A repository layer might only throw an exception with added context; the transaction handler or API boundary knows the request has failed and emits a single ERROR event with the error code and context. If multiple layers all log and rethrow the same error, readers will see duplicate stack traces.

## 4. What Does a Useful ERROR Log Record Contain?

A message like "ERROR: something went wrong" does not tell anyone what action to take. Log **a clear event, a stable error code, and enough correlation data to trace the issue**.

Structured data example:

```json
{
  "timestamp": "2026-01-01T10:15:30Z",
  "level": "ERROR",
  "service": "checkout",
  "environment": "prod",
  "event": "payment.failed",
  "error_code": "PROVIDER_UNAVAILABLE",
  "order_id": "O-17",
  "trace_id": "trace-123",
  "request_id": "req-456",
  "attempt": 3,
  "outcome": "failed",
  "duration_ms": 1842
}
```

Meaning of key fields:

| Field | Purpose |
| --- | --- |
| `level` | Identifies the severity level of the event. |
| `event` | Stable action name used for aggregation and searching; avoid changing it with arbitrary phrasing. |
| `error_code` | Application-meaningful error code; keep stable across releases. |
| `service`, `environment`, `version` | Identifies the service, environment, and deployment version. |
| `trace_id`, `request_id` | Pivots from the error to related logs within a single processing flow. |
| `order_id` / `job_id` | Business identifier when permitted to log; requires a data protection policy. |
| `attempt` | Distinguishes a single retry attempt from the final outcome of the job/request. |
| `duration_ms` | Processing duration; always specify the unit and what is being measured. |
| `exception.type`, stack trace | Exception type and technical failure location (when present and appropriate). |

A log line should answer **"what failed, in which operation, and with what impact?"** For example:

```text
ERROR event=payment.failed service=checkout
error_code=PROVIDER_UNAVAILABLE order_id=O-17
trace_id=trace-123 outcome=failed attempts=3
```

This is a text-format illustration; in real deployments, use structured logging (JSON or typed fields) so log collectors can query fields without relying on fragile string splitting.

### Recording the Cause Without Leaking Secrets

When an exception aids diagnosis, pass the **Throwable object** to the logger API so the backend can output the stack trace. Avoid logging only `exception.getMessage()`, as this loses the exception type, nested causes, and origin. However, exception messages sometimes contain URLs with tokens, SQL statements with sensitive parameters, or user input; mask or strip them before sending to the logging system.

Do not put passwords, API keys, access tokens, card numbers, personal data, full request bodies, or credentials into logs. Even `order_id` or `user_id` must comply with access controls, retention policies, and intended use. You can log approved reference IDs or appropriate hashes instead of sensitive values.

## 5. How Do Java APIs Represent ERROR?

### 5.1. SLF4J: `ERROR` Level

For applications already using SLF4J with a backend (such as Logback), a common pattern is:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class PaymentService {
    private static final Logger LOG =
            LoggerFactory.getLogger(PaymentService.class);

    public void process(String orderId) {
        try {
            callProvider();
        } catch (ProviderException ex) {
            LOG.error("event=payment.failed orderId={} errorCode=PROVIDER_UNAVAILABLE",
                    orderId, ex);
            throw ex;
        }
    }

    // callProvider() and ProviderException belong to the real application.
}
```

This is an **illustrative snippet** and will not compile standalone because `callProvider()` and `ProviderException` are hypothetical application components. In SLF4J, when you pass a `Throwable` as the final argument matching the formatting overload, the backend can record the exception's stack trace. With SLF4J 2.x, you can also use the fluent API and `setCause(ex)`.

**Note on where to place the log:** the pattern above only makes sense when `PaymentService` is responsible for confirming the final failure. If an outer caller also logs ERROR for the same exception, decide on a single place to emit the failure event or distinguish two events with different purposes.

### 5.2. The JDK `System.Logger` API

Since Java 9, the JDK includes the `System.Logger` interface with a dedicated `ERROR` level:

```java
System.Logger log = System.getLogger("com.example.payment");
log.log(System.Logger.Level.ERROR, "payment.failed");
```

This API works without adding SLF4J. How records are output and configured depends on the `LoggerFinder`/selected logging provider; when using the default JDK provider, it delegates to JUL. **Do not assume console formatting or level mapping is identical across all providers.**

### 5.3. `java.util.logging`: Using `SEVERE`

JUL **does not have `Level.ERROR`**. The closest equivalent in typical meaning is `Level.SEVERE`:

```java
import java.util.logging.Level;
import java.util.logging.Logger;

Logger log = Logger.getLogger("com.example.payment");
log.log(Level.SEVERE, "event=payment.failed", failure);
```

This snippet assumes a context where a `failure` variable of type `Throwable` is already in scope. The signature that accepts a `Throwable` is the `log(Level, String, Throwable)` overload. Do not write `Level.ERROR` in JUL, as the code will not compile.

## 6. Standalone Java 17 Example: Distinguishing INFO, WARNING, and Final Failure

This lesson uses JUL so it runs **without external libraries**. Because JUL lacks an ERROR constant, the example uses `SEVERE` for the semantically equivalent scenario. A small handler prints a fixed format to make the output easy to compare. In production, a formatter/logger backend should preserve full stack traces and structured fields.

Save as `ErrorLevelDemo.java`:

```java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ErrorLevelDemo {
    public static void main(String[] args) {
        Logger log = Logger.getLogger("lesson.checkout");
        log.setUseParentHandlers(false);
        log.setLevel(Level.INFO);

        Handler output = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (!isLoggable(record)) {
                    return;
                }

                Throwable failure = record.getThrown();
                String cause = failure == null ? ""
                        : " cause=" + failure.getClass().getSimpleName()
                        + ":" + failure.getMessage();

                System.out.println(record.getLevel().getName() + " "
                        + record.getMessage() + cause);
            }

            @Override
            public void flush() {
                // No custom buffer is used in this example.
            }

            @Override
            public void close() {
                // Do not close System.out because this handler does not own the stream.
            }
        };

        output.setLevel(Level.ALL);
        log.addHandler(output);

        // Rejecting invalid input is normal behavior.
        log.info("event=request.rejected reason=INVALID_AMOUNT");

        // A transient error that will still be retried: not yet a final failure.
        log.warning("event=payment.retry order_id=O-17 attempt=1");

        try {
            charge();
        } catch (IllegalStateException failure) {
            // This is the boundary where the final payment failure is decided.
            log.log(Level.SEVERE,
                    "event=payment.failed order_id=O-17 "
                    + "error_code=PROVIDER_UNAVAILABLE",
                    failure);
            System.out.println("result=FAILED");
        }

        log.removeHandler(output);
        output.close();
    }

    private static void charge() {
        throw new IllegalStateException("provider unavailable");
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac ErrorLevelDemo.java
java ErrorLevelDemo
```

**Exact stdout of the example:**

```text
INFO event=request.rejected reason=INVALID_AMOUNT
WARNING event=payment.retry order_id=O-17 attempt=1
SEVERE event=payment.failed order_id=O-17 error_code=PROVIDER_UNAVAILABLE cause=IllegalStateException:provider unavailable
result=FAILED
```

**Why is each line at that level?**

1. Invalid input is rejected according to contract, so the example logs `INFO`.
2. The external call encountered an issue and is expected to retry; `WARNING` records the anomaly without concluding that the entire operation failed.
3. The `charge()` method throws `IllegalStateException`. The `catch` block represents the final outcome and therefore emits `SEVERE` — corresponding to the intent of logging ERROR in APIs that have an ERROR level.
4. When `failure` is passed to `log(Level.SEVERE, message, failure)`, `LogRecord` retains a reference to the Throwable. The demo handler only prints the class name and message to keep stdout deterministic; it **does not print the full stack trace**. A production formatter should output the exception and causes appropriately for investigation.
5. `log.setUseParentHandlers(false)` prevents lines from also being emitted by parent logger handlers, avoiding duplicate logs in the example. In a real project, check the shared collection configuration before disabling propagation.
6. `output.setLevel(Level.ALL)` ensures the handler does not drop records that already passed the logger's `INFO` threshold. If the handler level were set to `SEVERE`, the INFO and WARNING lines would not be printed.

**Note on the scenario:** the WARNING line is just a simulated retry event before the final call fails. The example does not build a full retry mechanism. The goal is to show that **log levels reflect operational outcomes and meaning**, not to teach retry algorithms or transaction control.

## 7. Configuring Visibility and Routing for ERROR

An application might emit ERROR properly, yet operators still cannot see it if the handler/appender or collection pipeline filters it out.

Example Logback configuration for an application using SLF4J + Logback:

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{ISO8601} %-5level [%thread] %logger - %msg%n%ex</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE" />
    </root>
</configuration>
```

Here, root `INFO` **still receives ERROR** because ERROR has higher severity than INFO. The `%ex` pattern outputs exception details when present, and `%logger` shows the source logger; exact formatting depends on the backend version and configuration.

If you want to view only ERROR in a dedicated channel, you can use an appender with a level filter, such as `ThresholdFilter` at `ERROR` in Logback. Be sure to distinguish:

- **Logger level:** determines whether an event is created and propagated.
- **Appender level/filter:** determines whether the destination accepts the event.
- **Propagation (additivity) config:** can forward an event to parent appenders or duplicate it across multiple destinations.
- **External pipeline:** collectors may also sample, drop, restructure, or route records.

Sending a single ERROR line to both the console and long-term storage can be valid fan-out. Seeing two identical records **in the same channel** due to appenders configured on both a child logger and a parent logger is usually a duplication bug to check.

In JUL, equivalent configuration uses `SEVERE` — for example, `java.util.logging.ConsoleHandler.level=SEVERE` in `logging.properties` if you want the console to receive only SEVERE and above. Do not mix Logback syntax into JUL configuration files.

## 8. ERROR, HTTP Statuses, and Incident Metrics

A common misconception is "every ERROR means HTTP 500" or "one HTTP 500 corresponds to one ERROR log line." In reality:

- A single request can emit multiple ERRORs across different layers, or emit no ERROR if a code path does not log.
- An ERROR in a background job is not tied to any HTTP status.
- HTTP 5xx responses can originate from a proxy, load balancer, or timeout before application code ever logs an ERROR event.
- A downstream failure might be handled with a fallback into a degraded-functionality success response; the log level depends on service semantics.
- An `IllegalArgumentException` does not automatically mean the request must return 500; if caused by invalid input, the application may properly translate it into a 400.

**Do not use ERROR log line counts as failed request counts without a guaranteed unique, complete event convention.** To compute HTTP error rates, use request-completion counters or defined metrics such as `http.server.requests` broken down by status. Use ERROR logs to investigate root causes, classify error codes, and correlate with traces.

Dashboard example: "5xx jumped from 0.2% to 3% in 5 minutes." Query ERROR logs filtered by `service`, `environment`, `version`, and the time window; then group by `error_code`, `route`, and `dependency`. If you see many `PROVIDER_UNAVAILABLE` entries, pick a `trace_id` to inspect the request and its calls to the dependent system.

### Retries and Multithreading

If a job has three attempts and emits an ERROR on each attempt, you need to know whether the count represents "failed attempts" or "jobs that ultimately failed." Use `attempt` and `job_id`, or distinct event names like `payment.attempt_failed` and `payment.failed`, to make interpretation unambiguous. High-cardinality fields like `trace_id` are suited for tracing individual events and should not be used as aggregated metric labels.

Multiple threads and multiple services can cause logs to arrive at the collector out of chronological order; do not rely on line position in a log UI to infer causality. Use timezone-aware timestamps, correlation IDs, and proper distributed tracing.

## 9. Choosing Content and Logging Exceptions Safely

A good ERROR event provides **just enough** diagnostic information. Key principles:

1. **Actionable messages:** `event=payment.failed error_code=PROVIDER_UNAVAILABLE` is far more useful than `ERROR!!!`.
2. **Log the Throwable when a stack trace is needed:** with SLF4J, call an overload that accepts a Throwable; with JUL, use `log(Level.SEVERE, message, throwable)`.
3. **Log at the responsible layer:** avoid `log + rethrow` of the same exception at every layer. Add context to the exception and let the API/job boundary emit a single ERROR.
4. **Preserve the cause:** when wrapping exceptions, use constructors that accept a `cause` whenever available to keep the cause chain intact. Do not flatten every exception into a contextless message.
5. **Use stable error codes:** so data can be counted, filtered, and alerted on without depending on message wording.
6. **Do not let logging cause new errors:** buggy handlers/appenders, expensive expressions in log calls, or heavy object serialization can impact the request path. Avoid executing costly operations inside log statement arguments.
7. **Strip secrets:** messages and stack traces can also contain connection strings, URLs with tokens, or sensitive parameters. Sanitize inputs and configure collectors carefully.
8. **Choose retention and read permissions:** ERROR logs are for incident investigation, which does not mean storing them indefinitely; apply appropriate security and retention policies.
9. **Distinguish logs from alerts:** the ERROR level is raw signal data. Alerts should consider failure rate, impact, sample size, and duration; not every isolated ERROR should page an on-call engineer.
10. **Know the limits of logging:** asynchronous logging can drop records when queues fill up or the JVM terminates abruptly; excessive synchronous logging can hurt latency. Events requiring guaranteed delivery need mechanisms more specialized than standard logging.

## 10. Common Mistakes When Using ERROR

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Logging ERROR in every `catch` block | Noisy logs; on-call engineers struggle to spot real incidents | Determine the final outcome and impact before choosing a level. |
| Logging ERROR for valid 400/404 responses | Increases false alarms | Distinguish client errors from server-side failures. |
| Retrying 3 times, logging ERROR 3 times, and logging again in the controller | A single operation is counted as multiple errors | Separate attempts from the final outcome; pick one place to emit the final event. |
| Logging only `exception.getMessage()` | Loses stack trace and root cause | Pass the Throwable object to the logger API. |
| Logging raw requests/responses and tokens | Leaks sensitive data into log storage | Log only approved fields; mask or omit sensitive data. |
| Using `Level.ERROR` with JUL | Does not compile | Use `Level.SEVERE` or `System.Logger.Level.ERROR` depending on the API. |
| Setting root to `INFO` and assuming ERROR is hidden | Misunderstanding thresholds | Check level ordering; `INFO` normally includes `ERROR` in SLF4J/Logback. |
| Not seeing ERROR after deployment | Handler/filter, collector, or config changed | Check the source logger, appender/handler, collection pipeline, and environment. |
| Using ERROR line counts to calculate SLOs | Double-counting, missing events, inaccurate metrics | Use defined request-completion metrics with verifiable coverage. |
| Logging without `trace_id` or error codes | Hard to isolate and group issues | Standardize event/error_code names and correlate requests where appropriate. |

## 11. Self-Check Exercises

Suppose a Java payment service processes requests in sequence:

1. A request sends a negative amount. The validator returns a 400 response as designed.
2. Another request calls the payment gateway, times out on the first try, and succeeds on retry.
3. A third request calls the payment gateway, fails three times, and returns a final failure.
4. A background task catches an exception and switches to a fallback result that still meets requirements.
5. The bootstrapper fails to load required configuration, forcing the process to stop.

**Questions:** Which cases warrant logging ERROR, and which should use INFO/WARN? In case 3, should ERROR be logged in the network client layer, the service layer, and the controller? In JUL, which constant represents the level equivalent to ERROR?

**Suggested answers:** Case 1 is usually INFO/DEBUG, or valid rejected requests may not need per-request logging. Case 2 can log WARN on the timeout and INFO on the successful outcome. Case 3 is ERROR at the layer that determines the final outcome; individual attempts can be WARN or a differently named event, avoiding three layers logging the same exception. Case 4 can be WARN if the fallback needs monitoring, or DEBUG if it is an expected, unremarkable branch; it depends on service degradation. Case 5 warrants ERROR because the component cannot operate. JUL uses `Level.SEVERE`, whereas the `System.Logger` API has `Level.ERROR`.

**Extension exercise:** Design a `payment.failed` event with `error_code`, `trace_id`, `attempts`, `outcome`, and `duration_ms`; explain why each field helps investigation. Then describe how to verify that the collector receives ERROR records and why the number of ERROR records does not automatically equal the number of failed requests.

Once you distinguish **the log level of an event**, **exception-handling responsibility**, **operation consequences**, and **how failure rates are measured**, you will use ERROR as a meaningful operational signal rather than a blanket tag for every exception.
