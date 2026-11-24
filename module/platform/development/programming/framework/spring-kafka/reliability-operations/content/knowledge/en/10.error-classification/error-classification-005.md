# Business validation failure

A business validation failure occurs when a message is technically readable, yet its data or business state does not satisfy the receiving system's rules. Examples include an order with a negative quantity, an unsupported currency, a customer ineligible to purchase a product, or an invalid order state transition request.

In Spring Kafka, consumers must distinguish business errors that cannot be resolved by retrying from errors where processing conditions are only temporarily unmet. A message with permanently invalid data usually should not be retried continuously; a valid message that depends on unsynchronized data or an incomplete business step may need bounded retries. Database, network, or auxiliary service errors require their own policy.

Accurate classification prevents consumers from looping fruitlessly, preserves failed messages for investigation, avoids losing business audit trails, and enables replay once the cause is fixed. The key decision is determining whether the message was permanently rejected, is waiting on a temporary condition, or failed to process due to a system outage.

## 1. What is a business validation failure?

A message can pass deserialization and schema validation yet still violate business rules. For example, a JSON payload may be well-formed with valid field types, yet have `quantity` equal to 0 when an order requires a positive quantity. This is a semantic/business validation error.

Distinguishing validation layers:

| Validation layer | Question | Example error | Typical handling approach |
|---|---|---|---|
| Transport/format | Can the message be read and decoded? | Corrupted byte payload, invalid JSON | Do not retry undecodable payloads; quarantine/DLT for investigation. |
| Schema/structural validation | Does the payload have the right structure and field types? | Missing `orderId`, wrong type for `amount` | Usually do not retry the same payload; fix producer/schema and reprocess in a controlled way. |
| Business validation | Does the data satisfy business rules? | Negative quantity, prohibited currency, invalid state transition | Reject or quarantine; retry only if conditions can change over time. |
| Dependency/state precondition | Is prerequisite business data ready for immediate processing? | Customer not yet synchronized, aggregate not yet created | Can apply bounded retry or route to a waiting flow. |
| Technical/infrastructure | Can the system execute the operation? | Database timeout, network error, broker unavailable | Retry with backoff if temporary; alert if prolonged. |

Not every exception raised during business checks is a permanent validation failure. For instance, customer not found may be a permanent error if the ID does not exist in the source system, or merely a temporary state if the customer event was published alongside or behind the order creation event. Determine semantics based on the event contract and data consistency model.

## 2. Classifying permanent and transient business failures

### Permanent business errors

This is when data or requests cannot become valid merely by waiting for some period of time. Examples:

- `quantity` less than or equal to 0.
- Currency code not in the contract's supported list.
- Effective date outside the permitted range and immutable via state updates.
- A transition request from `CANCELLED` to `PAID` forbidden by the state machine.
- A product category prohibited from sale in the current channel.
- Payload has a malformed business identifier or cannot map to any valid entity.

Retrying the same message will not change the data on its own. For this group, you can record an explicit business rejection or route the message to a quarantine/DLT topic for retention and investigation. If the domain recognizes "rejected" as a valid outcome, persist the rejection result with an error code rather than treating it as an infrastructure failure.

### Temporary business errors

Some business conditions may change after another event is processed. Examples:

- An order references a newly created customer whose customer event has not yet been applied by another consumer.
- An aggregate lacks the required state because a preceding event is still in backlog.
- A quota has not been updated yet because a reconciliation job is running.
- An approval workflow is incomplete but expected to finish within a defined window.

This group requires bounded retry, backoff, and a deadline. If event ordering is mandatory, design keys/partitions or a waiting flow so later events do not overtake earlier ones. Blocking retry preserves partition order but stalls subsequent messages; retry topics allow later messages to proceed first, altering business order.

### Business errors due to stale data

Sometimes an event was valid when emitted but is no longer applicable when received by the consumer. For example, product prices changed, the aggregate version advanced, or an update request uses an outdated version. The system must explicitly define whether to:

- Accept the event using the snapshot at emission time.
- Reject the event if the version is no longer latest.
- Reconcile by reading current state and applying compensating rules.
- Route the event to an investigation queue when automated resolution is impossible.

Do not infinitely retry a stale event if current rules are guaranteed to keep rejecting it.

## 3. Validation at producer and consumer

Producers should validate data before publishing to reduce malformed messages entering Kafka. Checks such as required fields, ID formats, size limits, enums, and schema compatibility can run at the event-emission boundary.

Consumers must still validate independently. Producers may be older services, different clients, replayed data, or migration jobs. Never assume every message in a topic passed through the same validation version.

A sound workflow includes:

1. The producer validates the fields and rules it owns before creating the event.
2. A schema registry or serializer enforces payload structure and schema compatibility if used.
3. The consumer deserializes and validates structure before invoking business logic.
4. The domain service executes business validation against current data and business state.
5. The outcome is classified as accepted, rejected, retryable, or technical failure.

Do not place all business rules solely in the producer. The consumer is responsible for enforcing rules protecting the state it owns. Nor should you copy business rules arbitrarily across services without a clear contract and source of truth.

## 4. Expressing validation errors clearly

A validation failure should carry a stable error code and the details needed for investigation. Do not simply throw `RuntimeException("Invalid message")`, because logs and DLTs become hard to categorize.

Example custom exception:

```java
public class BusinessValidationException extends RuntimeException {

    private final String errorCode;
    private final String field;

    public BusinessValidationException(
            String errorCode, String field, String message) {
        super(message);
        this.errorCode = errorCode;
        this.field = field;
    }

    public String getErrorCode() {
        return errorCode;
    }

    public String getField() {
        return field;
    }
}
```

A service can throw this exception when a rule violation is detected:

```java
public void validate(OrderCreated event) {
    if (event.quantity() <= 0) {
        throw new BusinessValidationException(
                "ORDER_QUANTITY_INVALID",
                "quantity",
                "Quantity must be greater than zero");
    }

    if (!supportedCurrencies.contains(event.currency())) {
        throw new BusinessValidationException(
                "ORDER_CURRENCY_UNSUPPORTED",
                "currency",
                "Currency is not supported");
    }
}
```

Error codes should remain stable across application versions so dashboards, support runbooks, and replay tools can group them. Error messages must not contain passwords, tokens, card numbers, or full sensitive payloads. If field values are needed for investigation, apply masking and appropriate storage policies.

### Using Bean Validation

Jakarta Bean Validation can check structural constraints such as `@NotNull`, `@Positive`, `@Size`, and `@Pattern`:

```java
public record OrderCreated(
        @NotBlank String eventId,
        @NotBlank String orderId,
        @Positive int quantity,
        @NotBlank String currency) {
}
```

You can invoke `Validator` from a service or use Spring validation integration compatible with the listener signature. Translate violations into a business exception with an error code so the error handler classifies consistently. Not every Bean Validation constraint suffices to confirm business rules; for example, `@Positive` verifies a positive quantity but does not know whether the customer is permitted to order that product.

## 5. Choosing handling: reject, retry, or quarantine

Do not use a single policy for all validation failures. Base the decision on whether conditions can change, business impact, and recoverability.

| Scenario | Appropriate handling | Reason |
|---|---|---|
| Permanently invalid data | Reject with error code or route to quarantine/DLT | Retrying cannot fix the payload. |
| Dependent condition may appear later | Bounded retry or waiting flow | Processing may succeed once data is ready. |
| State/version conflict with compensation rule | Reconcile or reject per domain policy | Blind retry likely will not alter outcome. |
| Temporary database/network issue | Retry technical failure with backoff | Message may be valid but system could not process it yet. |
| Cannot determine validity because dependency is unresponsive | Treat as technical/transient failure | Do not conclude a message is invalid before state can be checked. |

### Rejecting as a business outcome

If rejection is a valid domain outcome, the service can record the rejected state and return normally. However, you must ensure the rejection outcome is durably persisted before the listener returns. For example, save `eventId`, `rejectionCode`, timestamp, and reference details to the database in a transaction. If saving the rejection fails due to a database timeout, a technical exception must be thrown so the container retries.

```java
@KafkaListener(topics = "orders.created")
public void onOrderCreated(OrderCreated event) {
    ValidationResult result = orderPolicy.validate(event);

    if (result.isRejected()) {
        rejectionService.recordRejectionIdempotently(
                event.eventId(), result.errorCode(), result.message());
        return; // Return only after the rejection has been durably saved.
    }

    orderService.createIdempotently(event);
}
```

Here, `recordRejectionIdempotently()` must use a transaction and a unique key on event ID or an equivalent mechanism. If the method throws when the database is unavailable, the listener must not swallow the error. When the listener returns normally, the container can commit the offset per AckMode.

### Quarantine or DLT

If a message needs investigation or data correction before replay, route it to a dedicated topic such as `orders.invalid` or a DLT. A DLT preserves the original record and source metadata, whereas a quarantine topic can be designed as a dedicated business flow for rejected messages.

Do not use a DLT as a place to sweep failed messages out of sight. You need an owner, retention, dashboards, handling procedures, and a replay policy. Sensitive messages must be protected similarly to the source topic.

## 6. Classifying BusinessValidationException in DefaultErrorHandler

From Spring Kafka 2.8 onward, `DefaultErrorHandler` can classify exceptions to determine retries. If `BusinessValidationException` represents a permanent error, you can mark this exception type as non-retryable and configure a recoverer to send records to a DLT.

```java
@Bean
DefaultErrorHandler businessErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(
                    kafkaTemplate,
                    (record, exception) -> new TopicPartition(
                            record.topic() + ".DLT",
                            record.partition()));

    DefaultErrorHandler handler = new DefaultErrorHandler(
            recoverer,
            new ExponentialBackOffWithMaxRetries(3));

    handler.addNotRetryableExceptions(
            BusinessValidationException.class);

    return handler;
}
```

In this example, permanent business errors go straight to recovery instead of being retried multiple times. Other exceptions can be retried according to the handler's default backoff or additional configuration. If you want to retry certain temporary business preconditions, use a separate exception type such as `BusinessStateNotReadyException` and do not mark it as non-retryable.

The DLT topic must exist and have matching partitions if the resolver routes records to the exact source partition. If the target topic has fewer partitions than the source, pick a valid partition in the resolver. The producer publishing to the DLT must have serializers compatible with the record's key/value.

### Classifying with specific exceptions

Avoid marking `IllegalArgumentException` as non-retryable across all listeners if the application also uses it for programming bugs or transient conversion issues. Dedicated exceptions express domain intent:

```java
public class BusinessStateNotReadyException extends RuntimeException {
    public BusinessStateNotReadyException(String message) {
        super(message);
    }
}

public class BusinessValidationException extends RuntimeException {
    public BusinessValidationException(String message) {
        super(message);
    }
}
```

For example, `BusinessValidationException` is permanent, whereas `BusinessStateNotReadyException` is retried for a bounded window. Once retries expire, the system can route state-not-ready records to a separate waiting topic instead of mixing them into the same stream as permanently invalid data.

## 7. Blocking retry and retry topics for business preconditions

### Blocking retry

`DefaultErrorHandler` can retry directly on the partition processing thread with backoff. This keeps the failed record in place before the consumer moves on, suitable when partition ordering is mandatory and wait times are not long.

The drawback is that the failing record blocks subsequent records in the same partition. If the error is "customer not yet created," downstream customer or order events queued behind it may be prevented from being processed to resolve the missing precondition. Verify dependency ordering before choosing blocking retry.

### Retry topic

Spring Kafka supports non-blocking retry via `@RetryableTopic` in compatible versions. Messages are moved to retry topics and reprocessed after a backoff delay. The original topic can proceed with subsequent records.

High-level example:

```java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 2_000, multiplier = 2.0),
        include = BusinessStateNotReadyException.class,
        exclude = BusinessValidationException.class)
@KafkaListener(topics = "orders.created")
public void onOrderCreated(OrderCreated event) {
    orderService.create(event);
}
```

This is an illustrative example; annotation attributes and exception filtering support depend on the Spring Kafka version. Check the corresponding API in your project. Non-blocking retry can allow later records to be processed ahead of retrying records, making it unsuitable for workflows requiring strict ordering. Do not apply retry topics to all exceptions when only specific business preconditions can recover.

### Choosing a deadline instead of infinite retries

Business preconditions usually have a reasonable deadline. For example, a customer event is expected to be applied within 30 seconds. Define a total retry window, attempt count, backoff, and post-deadline action. Once the deadline passes, move the message to an investigation-pending state or DLT with a clear error code.

Infinite retries inflate backlogs, stall partitions, raise costs, and mask producers emitting out-of-order events. Track message age in retry topics and attempt counts, not just record counts.

## 8. Preserving data and metadata when routing to DLT

When routing failed messages to a DLT/quarantine, preserve enough information to reproduce and investigate:

- Source topic, partition, and offset.
- Original key, timestamp, and headers.
- `eventId`, correlation ID, and aggregate ID if available.
- Validation error code, violated field, or rule.
- Exception class, failure timestamp, and attempt count.
- Application version, schema, or rule version if determinable.

Spring Kafka's `DeadLetterPublishingRecoverer` can add headers containing source topic/partition/offset and exception details. Specific header names are exposed via `KafkaHeaders`, such as `DLT_ORIGINAL_TOPIC`, `DLT_ORIGINAL_PARTITION`, `DLT_ORIGINAL_OFFSET`, `DLT_EXCEPTION_FQCN`, and `DLT_EXCEPTION_MESSAGE`. Verify the exact header API for the version in use.

If the exception message contains sensitive data, do not store it verbatim in headers or logs. Store sensitive details in an access-controlled store and put only a reference ID in the DLT message.

## 9. Replaying after fixing business rules or data

Replay is the operation of putting quarantined/DLT messages back into the processing flow. Before replaying, understand why the message was rejected and what changed:

- Payload fixed because the producer emitted bad data.
- Business rule updated so the old message is now valid.
- Dependency ready, e.g., the customer has now been created.
- A bug in validation code was fixed.
- The message requires compensation via a new event rather than replaying the original.

Not every DLT message should be replayed. Some messages were legitimately rejected under the policy at processing time; if business policy has not changed, replaying them only creates another rejection.

### Controlled replay procedure

1. Categorize the DLT by error code, source topic, and application version.
2. Confirm the root cause and decide whether payloads need editing.
3. Check whether the event ID was already processed or rejected earlier.
4. Test-replay a few messages in a controlled environment or small batch.
5. Rate-limit to avoid causing load spikes on consumers and downstream systems.
6. Monitor accepted/rejected outcomes, duplicates, and new errors.
7. Record the operator, timestamp, count, DLT source, and replay result.

Preserve the original `eventId` when replaying the same event so idempotency mechanisms recognize duplicates. If payload edits are needed, maintain a link between the original message and the corrected version; never silently overwrite original evidence.

### Idempotency in the consumer

Consumers should use `eventId` or a stable business key to avoid applying the same event multiple times. An inbox table with a unique constraint can record processed events in the same database transaction as business updates. On replay, duplicate inserts are detected and side effects are not repeated.

If rejection outcomes also need persistence, record rejections with event ID and error code idempotently. That way, replaying the same message does not create duplicate rejection records or duplicate notifications.

## 10. Observability for business validation failures

Operations must distinguish business rejection rates from technical failure rates. Tracking only total exceptions can cause a wave of bad producer data to be mistaken for a database outage or network incident.

| Metric | Grouping | Purpose |
|---|---|---|
| Validation failure count | `errorCode`, topic, producer/source, schema version | Identify which rule or source emits bad data. |
| Rejection rate | accepted/rejected by topic and time | Detect abnormal shifts in data quality. |
| Retry count | exception type, retry topic, attempt | Detect prolonged temporary preconditions or overly broad retry policies. |
| DLT/quarantine rate | source topic, error code, time | Track messages needing investigation and backlog growth. |
| Message age | time from event timestamp to processing/replay | Detect messages lingering in retry or quarantine. |
| Replay outcome | accepted, rejected, duplicate, failed | Measure remediation effectiveness and control impact. |
| Technical error rate | database, network, timeout, authentication | Separate infrastructure incidents from business errors. |

Structured logs should contain `eventId`, topic, partition, offset, error code, field/rule, exception type, attempt, and correlation ID. Do not use `eventId` or order ID as high-cardinality metric labels; keep those in logs/traces, while metric labels use bounded groups like error code or topic.

Dashboards should show rejection rate over time, top error codes, DLT message count, oldest message age, and replay success rate. Alert when rejection rate spikes suddenly, DLT backlog crosses thresholds, or a new error code appears in high volume.

## 11. Scenario-based runbook

### Validation failures spike suddenly after producer deployment

1. Group messages by `errorCode`, source topic, producer application, and schema version.
2. Identify start time and correlate with recently deployed producer versions.
3. Sample representative records from DLT/quarantine and inspect metadata and payloads per data policy.
4. Determine whether the producer violated the contract or the consumer changed a business rule.
5. Stop or throttle the bad data source if needed; avoid bulk retries.
6. Fix the producer/schema or coordinate a controlled rule change.
7. Replay a small batch after verifying valid data and monitor results.

### Consumer retries continuously because customer or aggregate does not exist yet

1. Determine whether this is a temporary dependency delay or a permanently invalid ID.
2. Compare event timestamps, partition/key, and publish order of related events.
3. Check whether the dependency's consumer group has lag or errors.
4. Choose blocking retry, retry topic, or a waiting flow based on ordering and deadline requirements.
5. Set attempt/time-window limits; after the deadline, route to quarantine or compensating handling.
6. Monitor message age and precondition resolution rate.

### Valid-looking messages routed to DLT

1. Inspect the exception type and classification in `DefaultErrorHandler`.
2. Determine whether an exception was marked non-retryable too broadly.
3. Check rule version, reference data, and dependency state at processing time.
4. Fix exception classification or rules to match intended semantics.
5. Verify replay capability, idempotency, and affected message count before re-running.

### DLT publish fails

1. Inspect exceptions from `DeadLetterPublishingRecoverer` and the DLT send future.
2. Verify the target topic exists, partition resolver is valid, and serializers are compatible.
3. Check ACLs, broker availability, producer timeout, and header size.
4. Verify the error handler does not treat failed recovery as success and commit the source offset.
5. Restore permissions/connectivity/configuration and let the record be reprocessed per policy.

### Replay produces duplicates or wrong state

1. Stop replay if duplicate business effects are detected.
2. Cross-check original event ID, modified event ID, and inbox/rejection state.
3. Verify whether the idempotency key was preserved across replay.
4. Determine whether the message was partially applied in external systems outside Kafka.
5. Add deduplication or compensating operations before resuming.
6. Test-replay a small batch and verify database/target state.

## 12. Business validation failure control table

| Control point | Question to answer | Operational evidence |
|---|---|---|
| Contract | Does the payload match schema and structure? | Schema version, deserialization result, and validation errors. |
| Business rule | Which rule was violated and can it change over time? | Error code, rule version, and reference data. |
| Classification | Is the error a permanent rejection, transient precondition, or technical failure? | Exception type and error handler classification. |
| Retry | Are only appropriate error groups retried, with deadline and backoff? | Attempt count, retry age, and retry topic metrics. |
| Recovery | Was the message durably persisted to DLT/quarantine? | DLT publish result, source metadata, and recovery exceptions. |
| Rejection | Is the rejection outcome recorded idempotently? | Event ID, rejection code, and database transaction. |
| Replay | Are replay criteria, rate limits, and audit trails in place? | Replay batch ID, operator, count, and outcome. |
| Observability | Are business rejections separated from technical errors? | Dashboards by error code, DLT backlog, and technical error rate. |
| Data protection | Do logs/DLT avoid exposing sensitive payloads? | Masking, ACLs, retention, and access audits. |

Business validation failure should be treated as a classified outcome of the message stream. Permanently invalid data should be rejected or quarantined with a clear error code; business conditions that can change should undergo bounded retries; technical incidents need a dedicated recovery policy. When consumers preserve source metadata, record rejections idempotently, and control replays, operations teams can remediate bad data while preserving business state correctness.
