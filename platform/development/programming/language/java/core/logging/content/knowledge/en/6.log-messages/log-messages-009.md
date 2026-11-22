# Event Codes in Java Logs: Naming, Stability, and Usage

## 1. What is an event code?

When reading a log line, humans usually pay attention to the message sentence such as "Unable to complete payment". However, wording can be edited for clarity, translated into Vietnamese/English, or supplemented with extra data. If charts, alerts, and analysis programs have to search for that exact message string, even a single wording change can cause the monitoring system to lose its ability to recognize the event.

An **event code** is a **stable identifier for the event type** that the application wants to record. For example:

- `checkout.started`: a checkout processing flow has started.
- `payment.retry_scheduled`: the system has scheduled a retry for a payment step.
- `payment.failed`: a payment operation has ended with a failed result.
- `order.created`: a new order has been created successfully.

This code answers **"what happened?"** at the *event type* level. The log message explains the event in natural language; context fields provide details of the *specific occurrence*.

Example of two records:

```text
INFO event_code=order.created order_id=O-18 trace_id=tr-42 message="Đã tạo đơn hàng"
INFO event_code=order.created order_id=O-19 trace_id=tr-57 message="Tạo đơn thành công"
```

The two lines have different message contents but the same event type `order.created`. You can count and group by `event_code` without depending on wording, while using `order_id` or `trace_id` to inspect details of each processing run.

An event code **does not automatically make logs structured**. The code must be recorded in a consistently named field (for example, `event_code`) that is parsed properly by the collector; ideally, use structured logging with typed data fields, such as JSON.

### Purpose of event codes

1. **Consistent classification:** know what behavior a log line is describing.
2. **Search and investigation:** filter `event_code=payment.failed` instead of searching for many variations of "payment error".
3. **Metric aggregation:** count order creations, failures, and retries by time window and by service.
4. **Semantic alerting:** combine event codes, outcomes, counts/rates, and time windows to detect anomalies.
5. **Link to operational documentation:** from a stable code, look up its definition, business meaning, owner, and remediation steps.
6. **Reduce language dependency:** descriptive sentences can be edited or translated while queries using the code still work.

## 2. Distinguishing event codes from easily confused information

A useful log record can contain multiple "codes", but they have different responsibilities:

| Component | Question it answers | Example | Stability |
| --- | --- | --- | --- |
| **Event code** (`event_code`) | Which event type occurred? | `payment.failed` | Stable across multiple occurrences of the same type. |
| **Message** (`message`) | What does the reader need to understand? | `Unable to complete payment` | Wording can be edited. |
| **Error code** (`error_code`) | Why did it fail or which error group does it belong to? | `UPSTREAM_TIMEOUT` | Stable by cause type; may be absent when there is no error. |
| **Log level** (`level`) | What level of attention is needed? | `INFO`, `WARN`, `ERROR` | Severity classification policy. |
| **Logger name** (`logger_name`) | Which component emitted the log? | `com.example.payment.Service` | Usually by package/class; may change during refactoring. |
| **Occurrence ID** (`event_id`) | Which distinct event record is this? | `evt-9a21` | Unique per occurrence if the system assigns an ID. |
| **Trace ID** (`trace_id`) | Which processing flow do these steps belong to? | `tr-42` | May be shared across multiple events of the same trace. |
| **Business ID** (`order_id`) | Which entity does the event relate to? | `O-18` | Distinguishes individual orders; requires logging permission control. |
| **Status/outcome** (`outcome`) | Did processing succeed or fail? | `success`, `failed` | Usually a bounded set of values. |

For example, `payment.failed` is the **event type**, while `UPSTREAM_TIMEOUT` is the **cause**. A timeout error can occur in many event types; conversely, `payment.failed` can be caused by a timeout, misconfiguration, or data error. These two fields should not be used interchangeably.

**Event code vs. event ID:** 1,000 created orders can emit 1,000 records carrying the same `event_code=order.created`. If you need to identify individual records for deduplication, use a separate `event_id` or a reliable event identifier key. `trace_id` helps link multiple steps, not inherently distinguish each log line uniquely.

An event code is also **not synonymous with an HTTP status**. `order.created` may correspond to a 201 response, but internal events are not required to map to HTTP. An HTTP 500 error can involve multiple technical events. Use a separate field if you want to analyze statuses.

## 3. Designing understandable and maintainable event code names

There is no single mandatory naming standard for all Java applications. The most important thing is that **the development team agrees on one convention and keeps its semantics stable**.

A readable convention is:

```text
<business_domain_or_component>.<action_or_outcome>
```

Examples:

```text
order.created
order.cancelled
payment.authorized
payment.retry_scheduled
payment.failed
inventory.reservation_failed
security.login_denied
job.completed
```

Practical recommendations:

- **Have a clear domain and action:** `order.created` is easier to understand than `SUCCESS_01`. Avoid names that only state severity like `common.error` because they do not describe what happened.
- **Consistent casing:** for example, lowercase, words separated by underscores within each segment, and a dot between domain and event. Choose one rule and apply it consistently.
- **Do not include dynamic data:** do not create `order.123.created` or `payment.failed.user_42`. IDs belong in separate fields.
- **Express the outcome at the right moment:** `payment.retry_scheduled` should only be emitted **after scheduling a retry succeeds**; `payment.failed` only when failure is confirmed by business definition.
- **Specific enough to query:** `order.created` differs from `order.creation_failed`; `request.completed` differs from `request.started`. If two situations have different denominators, owners, or handling procedures, they may need different codes.
- **Do not split endlessly:** if the causes differ but the event is still "payment failed", keep `payment.failed` and classify via `error_code`. Do not create hundreds of codes just to encode every error message.
- **Avoid UI-volatile names:** `button_blue_clicked` can quickly become outdated; name by business-meaningful behavior when it is a signal meant to be stored long term.

Codes can be **strings** or **numbers** depending on convention. For example, `PAY_0042` is also a valid code if there is a lookup table. However, semantic names are usually easier to read and investigate than a number that only makes sense when consulting reference documentation.

### "Started", "completed", and "failed" events

A group of events often reflects the lifecycle of an operation:

```text
checkout.started
    |
    +-- payment.retry_scheduled (may occur 0..n times)
    |
    +-- checkout.completed         (ended successfully)
    |
    +-- checkout.failed            (ended in failure)
```

This is **an illustrative model**; not every checkout must have these exact codes.

To avoid miscounting, clearly state the meaning of each code. For example, `checkout.started` counts started attempts, not completed ones; an in-flight or abnormally terminated request may have a start event without an end event. To calculate a success rate, you must define the denominator, completion criteria, time window, and how lost/duplicate events are handled.

In a system with retries, `payment.attempt_failed` can be emitted for each attempt, whereas `payment.failed` is emitted **only once when the logical operation finally fails**. When counting "number of failed transactions", query the right code and still account for possible duplication/loss in the pipeline.

## 4. What should an event record contain?

An event code is most valuable when accompanied by typed context and clear conventions:

```json
{
  "timestamp": "2026-01-01T10:15:30Z",
  "level": "ERROR",
  "service": "checkout",
  "environment": "prod",
  "event_code": "payment.failed",
  "message": "Không thể hoàn tất thanh toán",
  "error_code": "UPSTREAM_TIMEOUT",
  "outcome": "failed",
  "attempts": 3,
  "duration_ms": 1842,
  "trace_id": "tr-42",
  "order_id": "O-18"
}
```

Design rationale:

- `timestamp`: timestamp, preferring ISO 8601 with an explicit time zone; do not confuse occurrence time with collector ingestion time.
- `service`, `environment`, `version`: identify the service, environment, and release; support before/after deployment comparisons.
- `event_code`: stable identifier for filtering and aggregation.
- `message`: human-readable explanation; can be translated or rephrased without changing the code.
- `level`: severity level. A failure event is usually at a high level, but level policy depends on impact.
- `error_code`: specific cause when an error occurs; does not replace the event code.
- `outcome`: result to distinguish success/failure cases if one event type needs to carry multiple outcomes.
- `attempts` and `duration_ms`: numeric types, clearly defined as "number of attempts" and "milliseconds".
- `trace_id`, `order_id`: used for tracing; must comply with security and authorization policies.

**Use consistent field names.** If one place logs `event_code` and another logs `eventId` for the same meaning, dashboards will need hard-to-maintain transformation logic. If the system has already standardized on `event.name` or `event.type`, you can continue using that name; it does not have to be literally `event_code`. What matters is that the contract is clearly documented, stable, and properly collected by the backend.

At the Java application level, logger calls can write a string `event_code=...` for illustration. However, in production with multiple sources, **structured logging** avoids issues when messages contain spaces, equals signs, or newlines. Ensure the formatter/encoder produces valid JSON or a structure understood by the system.

## 5. Standalone Java 17 example: declaring event codes with an enum

Declaring codes with an `enum` avoids scattering identifier strings across many places and reduces typos. The example uses the JDK's `java.util.logging` (JUL), so **no external libraries are needed**. JUL uses `INFO`, `WARNING`, and `SEVERE`; systems using SLF4J typically call the corresponding levels `INFO`, `WARN`, and `ERROR`.

The example fixes input data so that stdout is always identical. In a real application, event codes are emitted at the exact state transition point, and IDs are taken from the actual processing context.

Save as **`EventCodeDemo.java`**:

```java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class EventCodeDemo {
    enum EventCode {
        CHECKOUT_STARTED("checkout.started", Level.INFO),
        PAYMENT_RETRY_SCHEDULED("payment.retry_scheduled", Level.WARNING),
        PAYMENT_FAILED("payment.failed", Level.SEVERE);

        private final String value;
        private final Level level;

        EventCode(String value, Level level) {
            this.value = value;
            this.level = level;
        }
    }

    private static void emit(
            Logger logger,
            EventCode code,
            String traceId,
            String orderId,
            String errorCode) {

        String message = "event_code=" + code.value
                + " trace_id=" + traceId
                + " order_id=" + orderId
                + (errorCode == null ? "" : " error_code=" + errorCode);

        logger.log(code.level, message);
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.checkout");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        Handler output = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (!isLoggable(record)) {
                    return;
                }
                System.out.println(record.getLevel().getName()
                        + " " + record.getMessage());
            }

            @Override
            public void flush() {
                // Example prints directly; no separate buffer.
            }

            @Override
            public void close() {
                // Does not own System.out, so do not close this stream.
            }
        };

        output.setLevel(Level.ALL);
        logger.addHandler(output);

        emit(logger, EventCode.CHECKOUT_STARTED,
                "tr-42", "O-18", null);
        emit(logger, EventCode.PAYMENT_RETRY_SCHEDULED,
                "tr-42", "O-18", "UPSTREAM_TIMEOUT");
        emit(logger, EventCode.PAYMENT_FAILED,
                "tr-42", "O-18", "UPSTREAM_TIMEOUT");

        logger.removeHandler(output);
        output.close();
    }
}
```

Compile and run from the directory containing the file using JDK 17 or later:

```bash
javac EventCodeDemo.java
java EventCodeDemo
```

**Exact stdout:**

```text
INFO event_code=checkout.started trace_id=tr-42 order_id=O-18
WARNING event_code=payment.retry_scheduled trace_id=tr-42 order_id=O-18 error_code=UPSTREAM_TIMEOUT
SEVERE event_code=payment.failed trace_id=tr-42 order_id=O-18 error_code=UPSTREAM_TIMEOUT
```

Explanation:

1. `EventCode` contains **a finite catalog** defining codes and example log levels. Instead of typing `payment.failed` in many places, the code references `EventCode.PAYMENT_FAILED` to reduce typos.
2. The `emit` method retrieves the code from the `enum`, assembling correlation fields and an optional cause. `trace_id=tr-42` is the same across all three lines, allowing you to find the entire processing flow; the event codes differ because the **event types** differ.
3. `error_code=UPSTREAM_TIMEOUT` can appear in both the retry-scheduled event and the final failure event. Having the same cause does not mean it is the same event.
4. `logger.setUseParentHandlers(false)` prevents extra lines from parent loggers; the custom handler prints to stdout so the output is easy to verify.
5. `output.setLevel(Level.ALL)` avoids filtering out additional records at the handler. The source logger at INFO allows both WARNING and SEVERE. If the handler were set to WARNING, the `checkout.started` line would not be printed.
6. The handler here is only an **illustrative tool**; it does not produce standard JSON, handle asynchronous processing, send logs over the network, or record stack traces. In production, use an appropriate backend/encoder and check for potential log loss.

**Limitations to remember:** the example builds strings from fixed data. When values come from a request or user, never insert unvalidated data directly into arbitrarily formatted messages: it may contain newlines or sensitive data. Use typed fields, validate data, and use a reliable encoder. Binding a fixed `Level` to each code in the enum is also just an illustrative policy; real systems may need to define levels contextually, as long as the code's meaning is not ambiguously altered.

## 6. Using event codes with structured logging

If the application uses **SLF4J 2.x** and the backend supports key-value fields, you can write the following example inside a Java method that already has `log` and `orderId`:

```java
log.atInfo()
        .addKeyValue("event_code", "order.created")
        .addKeyValue("order_id", orderId)
        .log("Đã tạo đơn hàng");
```

This is an **illustrative snippet**, not a standalone program: it requires the SLF4J 2.x library, a `log` logger, the `orderId` variable, and a backend configured to output these key-value fields. Not every pattern or encoder automatically displays extra fields; verify the actual output.

Another option is to use MDC (Mapped Diagnostic Context) for **shared context within a processing flow**, such as `trace_id` or `request_id`, when supported by the framework/backend. MDC does not automatically turn `event_code` into an event; the event code still needs to be attached at the exact moment the event occurs. In asynchronous processing or thread handoffs, verify that the MDC context is propagated and cleaned up properly to avoid mixing data between requests.

Choosing JUL, SLF4J + Logback, or Log4j2 does not change the principle: **codes must keep a stable meaning and be emitted as queryable fields**. Different API names only affect how loggers, formatters, appenders, and level configurations are declared.

## 7. Event code catalog as a contract

In multi-service projects, event codes should be managed with an **event catalog** or documentation checked whenever codes change. It is not necessary to create an overly large shared library; definitions can live alongside the module emitting the event while standardizing core fields.

Each code can have:

| Attribute | Example for `payment.failed` |
| --- | --- |
| Code | `payment.failed` |
| Description | A logical payment operation has ended in failure |
| Owner | Team responsible for the payment service |
| Emission point | After processing paths, fallbacks, and retries have concluded in failure |
| Default level | ERROR/SEVERE, per the actual API |
| Required fields | `trace_id`, `error_code`, `outcome`; `order_id` if permitted |
| Optional fields | `attempts`, `duration_ms`, `dependency` |
| Prohibited data | Tokens, passwords, payment payloads, sensitive information |
| Consumers | Log search, error dashboards, investigation workflows |
| Remediation | Check error code, trace, dependencies, retry status |
| Lifecycle | Active, deprecated, replaced |

### Changing codes without breaking consumers

Suppose the system already uses `payment.failed` in dashboards and alerts. Renaming it to `checkout.payment.error` simply because you prefer the new name can cause existing queries to stop seeing data. The recommended approach is:

1. Confirm whether the old and new semantics actually differ; if only the message sentence changed, **keep the code unchanged**.
2. If a code change is mandatory, update the catalog, emission sites, filters, alerts, dashboards, and operational documentation.
3. When a gradual transition is needed, implement a clear transition mechanism so consumers understand both codes during the migration period; be careful not to double-count if two events representing the same occurrence are emitted.
4. Only retire support for the old code after verifying consumers and the relevant log retention window.

**Do not reuse an old code for a new meaning.** For example, if `order.created` originally meant "order saved successfully", it must not later be changed to mean "just started the order creation process". That semantic shift makes historical statistics and alert logic wrong even though the field name did not change.

If you need to explain new emission behavior or major field changes, use versioned documentation and a compatibility policy. Only add a `v2` suffix when the change genuinely breaks the contract; avoid adding versions for minor changes to descriptive text.

## 8. From event codes to queries and dashboards

When logs are collected properly, you can ask semantically stable questions:

- In the last 15 minutes, how many times did `payment.failed` occur in `service=checkout`, `environment=prod`?
- How did the rate of `payment.retry_scheduled` change after deploying a new version?
- Which `error_code` values commonly accompany `payment.failed`?
- Taking `trace_id` from a failed event, what were the preceding events in the same processing flow?
- Was `order.created` emitted multiple times for the same logical operation due to retries or collection pipeline redelivery?

An **illustrative** SQL query (assuming the collector has ingested fields into a `logs` table):

```sql
SELECT event_code, COUNT(*) AS total
FROM logs
WHERE service = 'checkout'
  AND environment = 'prod'
  AND timestamp >= :from_time
  AND timestamp < :to_time
GROUP BY event_code
ORDER BY total DESC;
```

The `:from_time`/`:to_time` parameter syntax depends on the actual query engine; this is not a command that runs directly on every log system. To group by cause, add `error_code` to `SELECT` and `GROUP BY`. To inspect a specific processing flow, filter by `trace_id`.

**Counting logs does not inherently equal counting real business events.** Records can be lost when a process crashes, a log queue fills up, a collector is congested, or events are sampled; records can be duplicated when transport retries, multiple layers log the same outcome, or an operation retries multiple times. Key metrics used for SLIs/SLOs should have definitions and sufficiently reliable collection mechanisms. Event codes help **classify the captured data accurately**, but do not by themselves guarantee completeness or exactly-once delivery.

### Which fields to choose for grouping statistics?

`event_code`, `service`, `environment`, `status`, and `error_code` usually form a relatively controllable set of values if governed properly. In contrast, `trace_id`, `request_id`, and `order_id` can have millions of distinct values, making them suitable for **detailed search** rather than as metric labels on every measurement. Distinguish between **finding records** and **grouping for charts**.

For high-frequency events, balance full logging, sampling, and direct metrics. For example, all `request.completed` events can be used for investigation, while operational systems still need direct counters/histograms to compute RPS and latency percentiles when logs may be sampled.

## 9. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Searching by literal `message` text | Editing wording or changing language breaks queries | Query by a stable `event_code`. |
| Using `event_code` as a request ID | A different code for every request, losing grouping capability | Use a fixed code per type; put individual IDs in dedicated fields. |
| Using `error_code` instead of `event_code` | Cannot tell which operation the failure belonged to | Record the event type and cause in two separate fields. |
| Emitting `payment.failed` for every retry attempt | Counts one job as multiple final failures | Use separate codes for attempts and final outcome. |
| Using `generic.error` for every log | Cannot query the actual nature of the behavior | Define codes with a clear domain and action. |
| Including user info, raw URLs, or tokens in codes | Causes high cardinality and data leaks | Keep codes static; filter and protect context data. |
| Renaming codes arbitrarily | Dashboards and alerts lose data | Govern codes as a contract, with migration when needed. |
| Writing the code in free-form text without collector parsing | Filters cannot see the `event_code` field | Use a structured encoder and verify the output. |
| Emitting an event before completion is actual | Logs "success" for an operation that ultimately fails | Place emission points at confirmed outcome boundaries. |
| Counting lines without accounting for loss/duplication | Inaccurate metrics | Design appropriate collection, event IDs, deduplication, and metrics. |
| Logging sensitive data in messages or context fields | Expands exposure scope via log storage | Log only permitted data, mask/omit secrets, and enforce access control. |

## 10. Practice exercise

An order processing service performs the following steps:

1. Receives an order creation request.
2. Checks inventory successfully.
3. Calls payment, times out on the first attempt, and schedules a retry.
4. Succeeds on the next attempt.
5. Saves the order successfully.

**Prompt A:** Propose clear event codes for each step that needs tracking. Distinguish event code, error code, and trace ID.

**Hint:** You can choose `order.creation_started`, `inventory.checked`, `payment.retry_scheduled`, `payment.authorized`, and `order.created`. In step 3, `event_code=payment.retry_scheduled` and `error_code=UPSTREAM_TIMEOUT` describe two different aspects. All steps can carry the same `trace_id` to trace a single processing flow. The proposed codes are convention examples; a project may use different codes if the semantics and contract are clear.

**Prompt B:** Should `payment.failed` be emitted after step 3? When should that code be emitted?

**Hint:** If `payment.failed` is defined as the **final failure of the operation**, it should not be emitted yet because a retry path remains and step 4 succeeded. If you want visibility into each failed attempt, use `payment.attempt_failed` and record the attempt number. Only emit `payment.failed` when the final outcome truly fails according to business policy.

**Prompt C:** A system has 50 `order.created` records in 1 minute. Can you conclude with certainty that exactly 50 unique orders were created?

**Hint:** Not yet. There may be duplicate logs due to redelivery, multiple layers emitting, or an operation creating duplicates; logs may also be missing. You need emission rules, operation identification keys or event IDs, collection reliability, and business data sources before concluding.

**Self-check:** You have mastered this topic when you can explain why `event_code` must be stable, distinguish it from `message`/`error_code`/`trace_id`, design codes for milestones in a workflow, build a Java example with shared code names, and identify what can skew counts derived from logs.