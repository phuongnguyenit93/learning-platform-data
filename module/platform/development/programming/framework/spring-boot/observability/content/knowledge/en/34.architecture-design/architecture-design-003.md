# Choosing Logs for Business Details

In a Spring Boot application, metrics show trends, distributed tracing reveals which components a request traversed, and logs explain what specific event happened and why it happened. When investigating an unconfirmed rental booking, for example, you typically need to know the before-and-after status, which business rule was applied, the outcome of calling the payment service, and the failure reason code. Those are the details that should be recorded as structured logs.

The goal is not to log every line of code executed. The goal is to select the right events with investigative value, define stable event names and data fields, and correlate them with traces so on-call operators can go from an anomaly directly to the exact execution.

After this lesson, you will be able to:

- Distinguish the role of logs from metrics and distributed tracing.
- Choose logging points aligned with business events and state transitions.
- Design structured logs with stable event names, outcome codes, and correlation context.
- Combine logs with Micrometer Observation and trace context in Spring Boot.
- Avoid duplicate logs, sensitive data exposure, and high-cardinality metric tags.

## 1. What Questions Do Logs Answer?

Consider the flow of confirming a rental booking. A request enters the API, loads the booking from the database, checks its status, calls the payment service, and updates the booking. The three observability signals answer three distinct sets of questions:

| Signal | Primary Question | Example |
|---|---|---|
| Metrics | What is happening across the system at scale? | Confirmation success rate dropped from 98% to 82%; p95 latency increased. |
| Distributed tracing | Where did a single execution travel and where did it slow down? | The span calling the payment service took 1.8 seconds out of a 2-second total. |
| Logs | What specific event occurred and what data explains it? | Booking rejected because current status is `CANCELLED`; payment gateway returned code `INSUFFICIENT_FUNDS`. |

Good logs supply details that metrics and traces should not try to carry. Metrics need bounded tag sets to aggregate efficiently. Traces represent timing and dependency relationships between spans. Logs can carry event-level details, such as a booking ID or external error code, provided data policies and storage budgets permit.

Do not turn logs into dumps of entire requests, responses, or object states. Oversized records increase costs, hinder querying, and risk exposing private information.

## 2. Selecting Business Events Worth Logging

Start from the questions that operations, support, or development teams need to answer. An event worth logging usually falls into one of the following categories.

### 2.1. Meaningful State Transitions

Log when a business entity transitions through a significant state:

- A rental booking is created, confirmed, canceled, or completed.
- A payment is authorized, declined, or refunded.
- A request passes eligibility checks or is rejected.

A state transition event should capture the previous and new states, the entity identifier needed for investigation, the outcome, and the timestamp. If a state update fails, the log must describe the failed attempt rather than logging as if the state changed successfully.

### 2.2. Business Decisions

Log when the system makes a decision that may need explanation later: accepting or rejecting a request, choosing a fallback path, applying a pricing rule, or flagging a transaction for further review.

Prefer stable reason codes such as `INVALID_STATE`, `POLICY_NOT_MET`, or `PAYMENT_DECLINED`. Reason codes enable more consistent querying and aggregation than free-form prose. If additional human-readable explanation is needed, put it in the message.

Not every rejection decision is a technical error. A request rejected properly under business rules can be a normal outcome. Choose log levels based on operational meaning, not merely on whether the result is `success`.

### 2.3. Interactions with External Systems

Record key outcomes at integration boundaries: request sent, successful response, rejected response, timeout, or connection error. Logs should include the target system name, operation, outcome, standardized error code, and processing duration if relevant.

Do not log full payloads or headers. Usually only the partner-issued transaction ID, result code, and a few approved fields are needed. Authentication secrets, tokens, card data, and personal information must never appear in logs.

### 2.4. Errors and Abnormal Execution Paths

Log when the application requires investigation or action: unexpected errors, timeouts, data inconsistencies, exhausted retries, or triggered fallbacks. The log must state which operation failed, error type, error code, correlation identifiers, and whether the system can continue.

Avoid logging the same exception at every layer. An exception logged at the repository, service, controller, and global handler layers produces multiple duplicate entries without adding context. Pick the layer that actually handles the exception or translates it into a business outcome, and log it once with the fullest context.

## 3. Designing a Structured Log Record

Structured logs store data in discrete fields rather than concatenating everything into a prose sentence. Backends can index, filter, and aggregate individual fields without re-parsing messages.

A booking confirmation event might look like the following illustration:

```json
{
  "timestamp": "2026-11-22T07:15:30.412Z",
  "level": "INFO",
  "service.name": "rental-api",
  "event.name": "rental.booking.confirmed",
  "event.version": 1,
  "booking.id": "bkg_7f31",
  "state.from": "PENDING",
  "state.to": "CONFIRMED",
  "result": "SUCCESS",
  "traceId": "4f2c...",
  "spanId": "91ad..."
}
```

Commonly useful fields:

| Field | Purpose |
|---|---|
| `timestamp` | Event time; timezone and format should be standardized. |
| `level` | Severity level following logging conventions. |
| `service.name`, `service.version`, `deployment.environment` | Identifies the service and version that emitted the log. |
| `event.name`, `event.version` | Stable identifier and schema version of the event. |
| `result`, `reason.code` | Standardized outcome or reason. |
| `booking.id` or corresponding business identifier | Finds logs related to an entity, if data policy allows. |
| `traceId`, `spanId` | Opens the corresponding trace and identifies the span that emitted the log. |
| `error.type`, `error.code` | Categorizes errors without relying solely on the message. |
| `duration.ms` | Processing duration of the operation when useful for investigation. |

Field names must remain consistent across services. Do not mix `bookingId` in one place, `booking_id` in another, and embedding the ID in the message elsewhere. Pick one shared schema and maintain it across changes.

`event.name` should describe what happened, such as `rental.booking.confirmed` or `rental.payment.authorization.failed`. Do not name events after Java class names, method names, or message prose, as those details change frequently during refactoring.

Messages are for humans to read; fields are for machines to query. You can keep the message concise like `Booking confirmed`, while placing status, outcome, and booking ID in separate key-values.

## 4. Choosing Log Levels by Operational Meaning

| Level | Use When | Example |
|---|---|---|
| `ERROR` | A critical operation fails unexpectedly or requires intervention. | Unable to persist data after exhausting retries. |
| `WARN` | An abnormal situation warrants attention, though the app still handles it. | Partner times out on first attempt and system falls back to retry. |
| `INFO` | Significant operational event or state transition. | Booking is confirmed after transaction commits. |
| `DEBUG` | Diagnostic details enabled in a controlled manner when needed. | Which rule branch was chosen in a fee calculator. |
| `TRACE` | Very fine-grained data, typically high volume. | Step-by-step internal progression of an algorithm. |

Do not log every business rejection at `ERROR`. If a client submits an invalid request and the system rejects it according to rules, that may be `INFO` or `WARN` depending on operational impact. Conversely, if an internal error prevents a booking from transitioning state, `ERROR` may be appropriate.

Log levels are also part of your data budget. Enabling `DEBUG` or `TRACE` across all of production can spike volume rapidly. Restrict them by package, time window, sampling, or controlled configuration.

## 5. Logging at the Right Time in Spring Boot

For success events tied to transactional data, logging timing is critical. If you log `Booking confirmed` immediately after calling `save()`, but the transaction subsequently rolls back, the log claims a state that was never committed.

A sound approach is publishing an application event inside the transaction and logging during the `AFTER_COMMIT` phase:

```java
public record BookingConfirmedEvent(
        UUID bookingId,
        BookingStatus previousStatus,
        BookingStatus currentStatus
) {}
```

In the service, publish the event only after applying the changes:

```java
@Service
public class BookingService {

    private final BookingRepository repository;
    private final ApplicationEventPublisher eventPublisher;

    public BookingService(
            BookingRepository repository,
            ApplicationEventPublisher eventPublisher
    ) {
        this.repository = repository;
        this.eventPublisher = eventPublisher;
    }

    @Transactional
    public Booking confirm(UUID bookingId) {
        Booking booking = repository.findById(bookingId)
                .orElseThrow(() -> new BookingNotFoundException(bookingId));

        BookingStatus previousStatus = booking.getStatus();

        if (previousStatus != BookingStatus.PENDING) {
            throw new InvalidBookingStateException(bookingId, previousStatus);
        }

        booking.confirm();
        Booking saved = repository.save(booking);

        eventPublisher.publishEvent(new BookingConfirmedEvent(
                saved.getId(),
                previousStatus,
                saved.getStatus()
        ));

        return saved;
    }
}
```

The listener logs after the transaction commits:

```java
@Component
public class BookingLogListener {

    private static final Logger log =
            LoggerFactory.getLogger(BookingLogListener.class);

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onBookingConfirmed(BookingConfirmedEvent event) {
        log.atInfo()
                .addKeyValue("event.name", "rental.booking.confirmed")
                .addKeyValue("event.version", 1)
                .addKeyValue("booking.id", event.bookingId())
                .addKeyValue("state.from", event.previousStatus())
                .addKeyValue("state.to", event.currentStatus())
                .addKeyValue("result", "SUCCESS")
                .log("Booking confirmed");
    }
}
```

This example uses SLF4J 2.x's fluent logging API. Key-values only become queryable fields if the logging backend is configured to emit them; the default console format is not necessarily JSON. Configure Logback, Log4j2, or your active encoder to preserve these fields in structured output.

By default, the listener above runs synchronously on the committing thread. If you switch the listener to asynchronous execution, verify trace context and MDC propagation across thread boundaries. Also understand the limitation of in-memory application events: if the requirement is guaranteeing every business event is preserved even if the process crashes suddenly, use a transactional outbox or appropriate durable persistence. Operational logs do not replace business data sources or audit trails.

For a rejected decision, you can log directly where the system makes the decision because the rejection attempt itself is an event worth investigating:

```java
log.atWarn()
        .addKeyValue("event.name", "rental.booking.confirm.rejected")
        .addKeyValue("booking.id", bookingId)
        .addKeyValue("booking.status", previousStatus)
        .addKeyValue("reason.code", "INVALID_STATE")
        .log("Booking confirmation rejected");
```

The message here describes a rejected attempt, without asserting that the booking changed state.

## 6. Combining Logs with Micrometer Observation and Tracing

Micrometer Observation provides a single integration point to observe operations in an application. When the registry is configured with appropriate handlers, an Observation can contribute data to both metrics and tracing. Logs supplement event details without turning individual identifier values into metric labels.

For example, you can wrap the confirmation operation in an Observation:

```java
public Booking confirm(UUID bookingId, BookingType bookingType) {
    return Observation.createNotStarted(
                    "rental.booking.confirm",
                    observationRegistry
            )
            .lowCardinalityKeyValue("booking.type", bookingType.name())
            .observe(() -> bookingService.confirm(bookingId));
}
```

Observation names and low-cardinality key-values must be stable, with a bounded number of values. `booking.type` is suitable if there is only a controlled set of booking types. Never put `booking.id`, `customer.id`, email, or URLs containing identifiers into low-cardinality key-values, as each distinct value can create a new metric time series.

When Micrometer Tracing is configured, trace context can be placed into MDC so the logging backend appends `traceId` and `spanId` to logs. That allows opening the corresponding trace from a log entry. Verify that your actual pattern or encoder outputs these fields; do not assume every logging configuration does so automatically.

Some correlation principles:

- Use the `traceId` and `spanId` provided by the tracing context. Do not generate a new trace ID per log line.
- For work running outside HTTP requests, such as schedulers or consumers, ensure the task gets its own correlation context and that context propagates across async boundaries.
- If you need an identifier for a business workflow spanning multiple requests, use a clearly defined correlation ID or workflow ID.
- Never use trace ID, booking ID, or customer ID as a metric tag.
- Trace sampling may cause some traces not to be stored. If logs for an important event still need to be retained, set log retention policies independently of whether the trace is sampled.

Not every log line needs its own Observation. Create Observations around operations meaningful for latency or outcome; write logs at event points requiring explanation. The two signals should complement each other.

## 7. Distinguishing Operational Logs from Audit Logs

Operational logs serve system observability: investigating errors, latency, retries, and significant state transitions. Audit logs serve compliance and accountability: proving who performed which action, at what time, on which object, and under what authority. The two data types may share some fields, but they have different requirements.

If the business requires legally binding change history or tamper resistance, do not rely solely on SLF4J and log aggregation systems. Use an audit trail or history table designed for retention, access control, traceability, and integrity. Operational logs can be filtered, sampled, rotated, or expired under retention policies.

## 8. Controlling Cardinality, Privacy, and Cost

Logs can carry finer-grained identifiers than metrics, but that does not mean everything should be logged.

**Metric cardinality:** use only labels with bounded, predictable value sets, such as `result=success|rejected|failed`, `booking.type=short|long`, or `payment.provider=provider_a|provider_b`. Avoid `booking.id`, `user.id`, emails, request IDs, and full URLs. These values cause time series counts to grow rapidly, driving up memory and storage costs.

**Data in logs:** include business identifiers only when there is a clear investigative need, appropriate access control, and a defined retention period. Never log:

- Passwords, access tokens, refresh tokens, API keys, cookies, or authorization headers.
- Card numbers, security codes, bank details, or sensitive payment data.
- Emails, phone numbers, addresses, identity documents, or unnecessary personal data.
- Unfiltered full requests/responses, file contents, query strings, or partner payloads.
- Unbounded and unsanitized direct user input.

Use approved reference codes or masked/tokenized data when linking records. Never put sensitive data into log messages, exception messages, or MDC fields, as all of these paths can be exported to the logging backend.

**Cost and volume:** log key events at appropriate levels, throttle repeated logs inside retry loops, and avoid logging every iteration or every record in large batch jobs. For high-volume operations, consider batch summary logs or logging only abnormal cases. Do not drop logs of critical events just because traces are being sampled.

## 9. Avoiding Logging Anti-Patterns That Hinder Investigation

| Anti-Pattern | Problem | Improvement |
|---|---|---|
| `log.info("confirm booking " + booking)` | May dump the entire object and sensitive data; hard to query individual fields. | Log `event.name`, `booking.id`, status, and result as key-values. |
| `log.error("Invalid request", ex)` for every valid rejection | Triggers noisy alerts and inflates false error rates. | Use level and `reason.code` matching business semantics. |
| Logging `Booking confirmed` before transaction commit | Log may assert success even if data rolls back. | Log after commit or use durable event mechanisms. |
| Logging the same exception at every layer | Creates duplicate records, obscuring where it was handled. | Log once at the handling layer or error translation boundary. |
| Putting `booking.id` in a metric tag | Creates extremely high cardinality. | Keep IDs in logs; metrics should only use bounded outcome or type groups. |
| Manually concatenating `traceId` into messages | Hard to query and error-prone when context changes. | Use MDC/context provided by tracing and export as separate fields. |
| Logging full partner payloads | Increases volume and risks data exposure. | Extract transaction IDs, result codes, and approved fields only. |

## 10. Investigation Workflow from Logs to Traces

When receiving a report of an unconfirmed rental booking, you can investigate in this sequence:

1. Start from metrics to determine whether the error is widespread or affects only a subset of requests. Check failure rate, latency, and breakdown by service version or partner.
2. Search logs by an authorized booking ID, time range, and `event.name`. Read events in chronological order to identify before/after state and `reason.code`.
3. Grab `traceId` from the relevant log entry and open the distributed trace. Inspect spans calling the database, payment service, or external systems to find slow segments or failures.
4. Cross-check standardized error codes with logs at integration boundaries. There is no need to load full payloads if result codes already explain the failure.
5. After remediation, verify that metrics return to normal and check that new events reflect the expected outcomes.

This workflow works best when timestamps, event names, correlation identifiers, and schemas stay consistent across services. Machine clocks must also be synchronized so log and trace ordering remains meaningful.

## 11. Pre-Logging Checklist

Before adding a log statement for an operation, ask yourself:

- What concrete operational question does this log line answer?
- Does it describe an event that already happened, an attempt, or a rejected decision?
- Is `event.name` stable and easy to query?
- Do fields have consistent data types and names?
- Is the log emitted at the right time, especially around transactions?
- Does the log level reflect the actual level of attention required?
- Can the log be linked to traces via existing context?
- Do any fields introduce high cardinality in metrics?
- Does it contain personal data, secrets, or unnecessary payloads?
- Are volume and retention aligned with investigative value?

A well-designed set of business logs helps quickly answer what happened, to which entity, why, and in what execution context. By logging by event, keeping schemas stable, and linking logs with Observations and trace context, teams can investigate deeply while keeping costs and data risks under control.
