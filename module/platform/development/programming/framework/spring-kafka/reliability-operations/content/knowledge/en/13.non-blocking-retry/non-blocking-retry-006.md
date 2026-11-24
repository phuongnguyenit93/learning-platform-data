# DltStrategy

In **Spring Kafka Reliability Operations**, non-blocking retry forwards failed records through retry topics instead of blocking the main topic consumer during backoff. Once all allowed attempts are exhausted, the record is typically routed to a **Dead Letter Topic (DLT)** for investigation or separate processing. Yet the DLT consumer itself can also fail: unable to persist the failed record to a database, an admin API temporarily down, or an undeserializable payload.

**DltStrategy** defines what Spring Kafka does when the **DLT handler fails**, or whether to create a DLT for the retry flow at all. It is an enum in the **org.springframework.kafka.retrytopic** package. Understanding its three values—**ALWAYS_RETRY_ON_ERROR**, **FAIL_ON_ERROR**, and **NO_DLT**—helps prevent infinite DLT republish loops, mistakenly treating failed records as completed, or accidentally discarding a data source needed for recovery.

This lesson uses common Spring Kafka 3.x APIs; attribute names and certain behaviors may vary across versions. Always verify against the Javadoc matching your actual dependency before applying code to an application.

## 1. Where Does DltStrategy Sit in Non-Blocking Retry?

A listener configured with **@RetryableTopic** can create retry topics with different wait intervals. When the main topic or retry topic listener throws an exception, the non-blocking retry mechanism publishes the record to the appropriate topic for another consumer to process later.

Typical flow:

~~~text
orders                         Main topic
  |
  | processing error
  v
orders-retry-1000              Wait for next attempt
  |
  | still failing
  v
orders-retry-2000              Keep trying with backoff
  |
  | configured attempts exhausted
  v
orders-dlt                     Receives record for separate handling
  |
  v
@DltHandler                    Record/investigate/recover
  |
  +-- success                  DLT processing complete
  |
  +-- exception                Apply DltStrategy
~~~

Specific retry topic names, suffixes, topic counts, and wait intervals depend on configuration and Spring Kafka version. The diagram illustrates sequence only.

Two error boundaries must be kept separate:

1. **Main/retry listener fails:** the retry topic router decides whether to forward to the next retry topic or the DLT, based on attempt count, timeout, exception classification, and destinations.
2. **DLT handler fails:** DltStrategy decides whether to forward the record back to the DLT, report the error without reforwarding, or not configure a DLT in the first place.

Thus, DltStrategy does not replace attempts, backoff, include/exclude exceptions, or retry topic timeout settings. It primarily governs behavior at the end of the flow.

## 2. The Three Values of DltStrategy

| Value | When to use | Key behavior |
|---|---|---|
| **ALWAYS_RETRY_ON_ERROR** | Want the DLT to keep consuming other records even when one DLT record fails | When the DLT handler fails, typically publishes the record back to the DLT for a new consumption attempt; exceptions apply for fatal exceptions |
| **FAIL_ON_ERROR** | Want DLT handler errors reported without creating extra DLT copies | Does not automatically forward the failed record back to the DLT; the exception goes through the DLT consumer/container error path |
| **NO_DLT** | Accept ending the flow after retries are exhausted without creating a DLT | Does not configure a DLT for that retry chain |

**ALWAYS_RETRY_ON_ERROR is the default** in retry topic configurations with a DLT. This does not mean every exception is sent back to the DLT; the framework excludes errors considered fatal.

Example referencing the values in Java code:

~~~java
import org.springframework.kafka.retrytopic.DltStrategy;

DltStrategy defaultBehavior = DltStrategy.ALWAYS_RETRY_ON_ERROR;
DltStrategy failWithoutReforward = DltStrategy.FAIL_ON_ERROR;
DltStrategy omitDlt = DltStrategy.NO_DLT;
~~~

The enum name describes the behavior of Spring Kafka's **retry-topic/DLT mechanism**, not a Kafka broker configuration. Changing DltStrategy does not cause the Kafka broker to create a new kind of acknowledgment or guarantee database exactly-once semantics.

## 3. ALWAYS_RETRY_ON_ERROR: Resending the Record to the DLT

This is the default option. When the DLT handler throws an exception that the framework allows retrying via the DLT, the record is published **back to the DLT itself**. As a result, the consumer can keep fetching and processing other DLT records while the failed record gets another chance to be consumed.

Example with DLT records:

~~~text
orders-dlt
offset 70: event A    -> DLT processing failed
offset 71: event B    -> DLT processing succeeded
offset 72: event C    -> DLT processing succeeded

When event A fails:
  A is published back to orders-dlt at a new offset
  The DLT consumer can continue reading B and C
~~~

**This is a new publish**, not "rewinding the offset" or re-invoking the same listener call. The new offset of the republished record differs from the original offset. If the handler keeps failing, the flow can create more copies of the record on the DLT.

### 3.1. Benefits

- One failing DLT record does not necessarily block all records behind it.
- The system can automatically retry once a transient failure in the DLT processor ends.
- Isolates most DLT failures from processing on the main topic and retry topics.
- Suitable when the DLT handler hits only brief transient errors, such as a short timeout in an incident store.

### 3.2. Risk When a Record Has a Permanent Error

Suppose the DLT handler always throws an exception due to an invalid payload structure. If the framework keeps forwarding the record back to the DLT, the following can happen:

~~~text
DLT event A #1
      |
      v
Handler fails
      |
      v
DLT event A #2
      |
      v
Handler fails again
      |
      v
DLT event A #3
      |
      v
...
~~~

Consequences include growing topic size, increased producer/consumer traffic, multiple records for the same event, difficulty distinguishing original event counts from retry counts, and the risk of DLT growth outpacing investigation capacity.

Therefore, monitor **DLT reforward rate**, occurrences per eventId, record age, and DLT size. Set appropriate retention, quotas, and alerts. Do not leave republishing running indefinitely for errors that are clearly unrecoverable.

### 3.3. Exception for Fatal Exceptions

Starting in Spring Kafka **2.8.3**, ALWAYS_RETRY_ON_ERROR does not automatically forward records back to the DLT for exceptions the framework treats as fatal, because retrying the same payload would repeat the exact same error forever.

Typical groups in the fatal list from Spring Kafka documentation include:

- DeserializationException
- MessageConversionException
- ConversionException
- MethodArgumentResolutionException
- NoSuchMethodException
- ClassCastException

The list can be customized through APIs related to **DestinationTopicResolver** in the corresponding Spring Kafka version. Do not modify the list solely to force permanent deserialization errors to loop back to the DLT. When customizing, clearly understand exception wrappers, cause chains, and business goals.

**ALWAYS** in the enum name represents the default policy for DLT errors eligible for reforwarding; it is not a promise that every exception type will be republished unconditionally.

## 4. FAIL_ON_ERROR: Report the Error Without Reforwarding to DLT

With **FAIL_ON_ERROR**, when the DLT handler throws an exception, Spring Kafka does not automatically send the record back to the DLT via non-blocking retry's reforwarding mechanism.

Example:

~~~text
orders-dlt, offset 70: event A
            |
            v
        @DltHandler
            |
            v
        Database error
            |
            v
     FAIL_ON_ERROR
            |
            v
     Exception is surfaced
     No new event A created in DLT
~~~

This avoids generating extra DLT copies just because the DLT processor failed. It fits when operational procedures require keeping a single record copy for controlled handling, or when duplicating failed data is costly.

**Do not interpret FAIL_ON_ERROR as "skip the record" or "guaranteed to retry immediately."** The error continues interacting with the DLT's listener container configuration, acknowledgments, and error handler. Depending on those components, the record may be redelivered, consumed slowly, hold the partition, or be handled by another error policy. FAIL_ON_ERROR only states that this DLT strategy does not automatically reforward the record to the DLT like ALWAYS_RETRY_ON_ERROR.

Cases where FAIL_ON_ERROR should be considered:

- The DLT consumer writes to an investigation store and must not silently drop write failures.
- Monitoring or an operator must decide when to replay.
- You want to prevent a permanent error from creating many duplicates on the DLT.
- The DLT must process sequentially per key and you do not want failed records appended to the end of the log at a new offset.

The risk is that the DLT consumer may repeat the failure or stall if appropriate error handling is absent. Alerts and a runbook for records that cannot complete are therefore necessary.

## 5. NO_DLT: Do Not Configure a Dead-Letter Topic

**NO_DLT** differs completely from the two options above. It instructs the framework not to configure a DLT for the retry-topic flow. After exhausting attempts, processing through the retry chain ends without the framework creating a DLT to hold the final failed record.

Example:

~~~text
orders -> orders-retry-1000 -> orders-retry-2000
                                  |
                                  v
                            Retries exhausted
                                  |
                                  v
                        Retry flow ends
                        (no orders-dlt created)
~~~

NO_DLT does not mean Kafka immediately deletes all original records. Records remain subject to retention on the topics already written to. However, the system has **no central DLT point** to investigate, repair data, and re-drive via this retry-topic mechanism.

NO_DLT is only suitable when the business has a clear reason not to store final failures—for instance, data can be fully regenerated from another source, the outcome is non-critical, or an independent error-persistence flow has been intentionally designed.

For orders, payments, invoices, inventory, or auditable events, omitting a DLT without an alternative recovery mechanism can leave critical records unprocessed without easy detection. Before choosing NO_DLT, clarify who is responsible for tracking exhausted retries and how events are recovered.

## 6. Distinguishing NO_DLT from Disabling DLT Consumer Auto-Start

A very common requirement is **still storing records in the DLT, while preventing the application from automatically consuming the DLT**. For example, operations wants to handle the DLT manually after triaging and fixing data.

In that scenario, **do not use NO_DLT**. Still configure the DLT and disable auto-starting the DLT listener via **autoStartDltHandler**.

~~~java
@RetryableTopic(
    kafkaTemplate = "kafkaTemplate",
    attempts = "4",
    autoStartDltHandler = "false"
)
@KafkaListener(topics = "orders", groupId = "order-service")
public void process(OrderEvent event) {
    orderService.process(event);
}
~~~

In the @RetryableTopic API, **autoStartDltHandler is a String**, so the example uses the string value `"false"`. With the configuration builder, use the Boolean-accepting method **autoStartDltHandler(false)**.

Expected outcome: when a record exhausts retries, it is still sent to the DLT; the DLT-processing container does not start automatically. Later, the DLT container can be started via **KafkaListenerEndpointRegistry** through the application's lifecycle mechanism. The DLT holds records according to retention while waiting.

| Configuration | Has DLT? | DLT consumer auto-runs? | After retries exhausted |
|---|---|---|---|
| NO_DLT | No | No DLT consumer from this flow | Flow ends, not forwarded to DLT |
| Default DLT | Yes | Normally yes | Record is forwarded to DLT and handled by DLT listener |
| DLT + autoStartDltHandler="false" | Yes | Does not auto-run | Record is stored in DLT for later processing |

Disabling auto-start does not mean records are kept forever. Set DLT retention long enough to avoid losing investigability before an operator starts the handler.

## 7. Configuring DltStrategy with @RetryableTopic

In Spring Kafka 3.x, the annotation attribute used to choose the enum is **dltStrategy**.

Example using FAIL_ON_ERROR and an explicit DLT handler:

~~~java
import org.springframework.kafka.annotation.DltHandler;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.RetryableTopic;
import org.springframework.kafka.retrytopic.DltStrategy;
import org.springframework.retry.annotation.Backoff;

@Component
public class OrderConsumer {

    private final OrderService orderService;
    private final IncidentStore incidentStore;

    public OrderConsumer(
            OrderService orderService,
            IncidentStore incidentStore) {
        this.orderService = orderService;
        this.incidentStore = incidentStore;
    }

    @RetryableTopic(
        kafkaTemplate = "kafkaTemplate",
        attempts = "4",
        backoff = @Backoff(
            delay = 1_000,
            multiplier = 2.0,
            maxDelay = 8_000
        ),
        dltStrategy = DltStrategy.FAIL_ON_ERROR
    )
    @KafkaListener(
        topics = "orders",
        groupId = "order-service"
    )
    public void process(OrderEvent event) {
        orderService.process(event);
    }

    @DltHandler
    public void processDlt(OrderEvent event) {
        // Error persistence must be idempotent.
        // When persistence fails, throw an exception so the
        // framework applies FAIL_ON_ERROR.
        incidentStore.saveOnce(event.eventId(), event);
    }
}
~~~

This is a design example: **OrderEvent**, **OrderService**, and **IncidentStore** are application-defined business types. Configure the producer template, serializers, deserializers, and topics to match your actual payload types.

In the configuration above:

1. The main listener attempts to process the event.
2. On a retryable error, the framework forwards to the corresponding retry topic.
3. After exhausting attempts, the record moves to the DLT.
4. processDlt() attempts to persist the event to the investigation store.
5. If processDlt() throws an exception, FAIL_ON_ERROR prevents automatically reforwarding the record to the DLT.

@RetryableTopic's **attempts** count includes the initial processing attempt in the current API, unlike the retry-count parameter of many BackOff implementations. Do not mix the two counting conventions when estimating total service calls.

**Note:** A @DltHandler method in the same class can be used for other @RetryableTopic methods in that class. If multiple listeners handle different payloads or business flows, separate classes or design the DLT handler to handle each event type explicitly.

## 8. Configuring ALWAYS_RETRY_ON_ERROR with Annotations

To use the default, you can omit the dltStrategy attribute:

~~~java
@RetryableTopic(
    kafkaTemplate = "kafkaTemplate",
    attempts = "5"
)
@KafkaListener(topics = "notifications", groupId = "notification-worker")
public void process(NotificationEvent event) {
    notificationService.dispatch(event);
}

@DltHandler
public void processDlt(NotificationEvent event) {
    incidentStore.saveOnce(event.eventId(), event);
}
~~~

Equivalent to specifying it explicitly:

~~~java
@RetryableTopic(
    kafkaTemplate = "kafkaTemplate",
    attempts = "5",
    dltStrategy = DltStrategy.ALWAYS_RETRY_ON_ERROR
)
~~~

Use this policy only when the DLT handler can recover from transient errors and operations monitors the reforward count. If incidentStore consistently fails due to permanent validation errors, continuous republishing can cause the DLT to grow rapidly.

In Spring Kafka docs you may encounter older examples or naming such as **dltProcessingFailureStrategy**. Use the attribute name provided by the Javadoc of the dependency version you are running; in the current Spring Kafka 3.x API, it is **dltStrategy**.

## 9. Configuring NO_DLT with Annotations

When the business genuinely does not require a DLT:

~~~java
@RetryableTopic(
    kafkaTemplate = "kafkaTemplate",
    attempts = "3",
    dltStrategy = DltStrategy.NO_DLT
)
@KafkaListener(topics = "ephemeral-events", groupId = "ephemeral-worker")
public void process(EphemeralEvent event) {
    ephemeralService.process(event);
}
~~~

No @DltHandler is needed for this flow because Spring Kafka does not configure a DLT. Add a metric for retry-exhausted records so operators know how many events did not complete processing. If errors must be stored, use another storage mechanism with suitable durability.

NO_DLT can make sense for ephemeral events or reconstructible data, but should not be chosen merely to avoid operating a DLT. Not seeing an error backlog is not a sign of a healthy system.

## 10. Configuring via RetryTopicConfigurationBuilder

Besides annotations, Spring Kafka supports **RetryTopicConfigurationBuilder**. This works well when centralizing retry topic settings in a @Configuration class or applying policies by topic.

Example with FAIL_ON_ERROR:

~~~java
@Bean
RetryTopicConfiguration retryTopicConfiguration(
        KafkaTemplate<String, OrderEvent> template) {

    return RetryTopicConfigurationBuilder
            .newInstance()
            .maxAttempts(4)
            .fixedBackOff(1_000L)
            .doNotRetryOnDltFailure()
            .create(template);
}
~~~

The **doNotRetryOnDltFailure()** method sets DltStrategy to FAIL_ON_ERROR.

You can use the general method:

~~~java
RetryTopicConfigurationBuilder.newInstance()
    .dltProcessingFailureStrategy(DltStrategy.FAIL_ON_ERROR);
~~~

Or if you want **no DLT**:

~~~java
RetryTopicConfigurationBuilder.newInstance()
    .maxAttempts(4)
    .fixedBackOff(1_000L)
    .doNotConfigureDlt();
~~~

The **doNotConfigureDlt()** method selects NO_DLT. If you only want to keep the DLT but pause its consumer:

~~~java
RetryTopicConfigurationBuilder.newInstance()
    .maxAttempts(4)
    .autoStartDltHandler(false);
~~~

The trailing builder snippets illustrate individual options and must call **create(kafkaTemplate)** when wired into an actual RetryTopicConfiguration bean.

With global builder configurations, scope topics to actual needs; do not accidentally apply NO_DLT to a critical business listener. Avoid stacking annotation and bean configurations for the same listener without verifying how the framework selects RetryTopicConfiguration.

## 11. @DltHandler: Success, Failure, and Business Logic

A DLT handler is not just for logging. It can save records to an investigation system, send alerts, open tickets, or prepare info for a re-drive workflow.

Example of a handler writing to a database:

~~~java
@DltHandler
public void processDlt(OrderEvent event) {
    incidentService.recordFailure(event);
}
~~~

Crucially, **do not catch exceptions, merely log, and return normally** when the record was not actually saved:

~~~java
@DltHandler
public void unsafeDltHandler(OrderEvent event) {
    try {
        incidentService.recordFailure(event);
    }
    catch (RuntimeException exception) {
        log.error("Failed to persist DLT event", exception);
        // Listener returns normally even though the record was not saved.
    }
}
~~~

In this flawed example, Spring Kafka may consider the DLT handler completed successfully. DltStrategy then has no exception to act on. The DLT record remains in Kafka per retention, yet the committed offset can advance past it and operations may assume handling succeeded.

A safer pattern is to log and **rethrow the exception**:

~~~java
@DltHandler
public void processDlt(OrderEvent event) {
    try {
        incidentService.recordFailure(event);
    }
    catch (RuntimeException exception) {
        log.error(
            "Cannot persist failed eventId={}",
            event.eventId(),
            exception
        );
        throw exception;
    }
}
~~~

When @DltHandler returns normally, the container applies the appropriate acknowledgment/commit mechanism. When the handler throws an exception, DltStrategy can handle the failure per the chosen policy. Ensure the persistence method has clear transaction boundaries and can run repeatedly.

## 12. What If No @DltHandler Is Written?

When no @DltHandler method or builder-specified handler exists, the framework may create a default **logging DLT handler**. This handler logs receipt of the DLT record using its default behavior.

This is handy in simple demos, but has an operational consequence: **a successful log does not mean the failed record was persisted to an investigation store or fixed**. If the default DLT consumer is running, committed offsets can advance, making DLT consumer lag appear low even while many business events remain unresolved.

If the DLT is an important part of your reliability workflow, deliberately choose one of these options:

- Provide a @DltHandler that executes an idempotent task and saves processing state.
- Use the builder's dltHandlerMethod() to point to a dedicated bean/method.
- Disable autoStartDltHandler and delegate DLT handling to a separate service/operations team.

Never use "DLT lag equals 0" as proof that all business errors have been resolved.

## 13. Fatal Exceptions and the Limits of ALWAYS_RETRY_ON_ERROR

Some errors are permanent in nature: malformed payloads, a listener method unable to bind required arguments, or type conversion failures. If the DLT handler keeps hitting the exact same error, forwarding back to the DLT only inflates the log.

For that reason, the framework maintains a list of exceptions not reforwarded under ALWAYS_RETRY_ON_ERROR. Fatal exception classification can differ by version and extra configuration.

| Error group | Example | Handling direction |
|---|---|---|
| Undeserializable | Malformed JSON or serializer mismatch | Fix schema/deserializer config; handle raw record under control |
| Message unconvertible | Payload does not match listener's expected type | Check message converter and Java types |
| Argument unresolvable | Incompatible method signature or headers | Fix listener method/configuration |
| Invalid class cast | Wrong type mapping | Fix type info/consumer |
| Transient I/O error | Database or network timeout | Can retry with bounds |
| Permanent validation error | Missing required field | Fix data or route to investigation workflow |

Distinguish **exception classification for the main listener** (deciding when to send a record to retry topics/DLT) from **fatal exceptions when the DLT handler fails** (deciding whether to allow DLT reforwarding). These are two distinct stages.

Do not treat the absence of DLT reforwarding as a guarantee the record was handled. Inspect exceptions, offsets, and storage state to know where the record stands.

## 14. Behavior with Offsets, Duplicates, and Idempotency

DltStrategy does not create an atomic transaction between Kafka and an external database. Two critical scenarios exist:

**The DLT handler writes to the database successfully and then the app stops before committing the offset.** The DLT record may be redelivered upon consumer restart. If the handler creates a new ticket or incident record every time, one event can create multiple tickets.

**The DLT handler fails after a side effect occurred, and ALWAYS_RETRY_ON_ERROR forwards the record again.** A new DLT copy can be produced even though the side effect already completed. When the new copy is processed, the side effect risks running twice.

Safe design practices:

1. Attach a **stable eventId** from the start; keep it unchanged across the main topic, retry topics, and DLT.
2. Store eventId as a unique key when creating incidents, tickets, or inbox records.
3. Place the processed marker and business update in the same database transaction whenever possible.
4. For external APIs, pass an idempotency key if the target service supports it.
5. Record the DLT topic, partition, offset, and reforward count to aid investigation.
6. Never use the new offset of a DLT copy as the unique identifier for a business event.

Example of idempotent incident persistence:

~~~sql
BEGIN;

INSERT INTO failed_event(event_id, payload, received_at)
VALUES (:event_id, :payload, CURRENT_TIMESTAMP)
ON CONFLICT (event_id) DO NOTHING;

COMMIT;
~~~

The example uses PostgreSQL syntax. When business logic also needs to update status or attempt counts, perform the related changes in the same transaction and check the insert/upsert result rather than merely checking that the statement threw no error.

## 15. Choosing a Strategy by Business Requirement

| Requirement | Option to consider | Accompanying conditions |
|---|---|---|
| DLT handler hits only short I/O errors, want DLT to keep consuming | ALWAYS_RETRY_ON_ERROR | Monitor reforwards, idempotent handler, control retention |
| DLT handler must surface errors to operators without duplicating records | FAIL_ON_ERROR | DLT container error handling, alerts, and re-drive |
| Pause DLT processing for manual investigation | DLT enabled + autoStartDltHandler="false" | Monitor age/retention and have a startup procedure |
| Event can be skipped after retries, reconstructible from source | NO_DLT | Accept having no DLT and emit metrics for final failures |
| Payments, orders, or auditable workflows | DLT enabled, often with dedicated processing governance | Durable storage, idempotency, access control, and runbook |
| A DLT record has a permanent deserialization error | Check fatal exceptions, fix schema first | Avoid creating a reforward loop |
| DLT is usable but the incident store has a prolonged outage | FAIL_ON_ERROR or pause DLT consumer | Restore dependency before continuing processing |

You do not have to pick a single DltStrategy for every business flow. A system can use different policies for different listeners or topic groups, as long as configuration scopes are explicit.

## 16. Observing the DLT in Production

To operate DltStrategy safely, measure both **records entering the DLT** and **records processed successfully**, not just consumer lag.

Recommended metrics:

- Records sent to the DLT from retry topics per minute.
- Records **forwarded from the DLT back to the DLT** per minute.
- Unique eventIds in the DLT versus total record count.
- DLT handler successes, failures, and timeouts.
- Fatal exceptions not reforwarded.
- Consumer lag and oldest record age of the DLT group.
- DLT size, retention, and growth rate.
- Records re-driven by operators and post-re-drive outcomes.

Logs should include **eventId**, source topic, source partition/offset, DLT topic, DLT partition/offset, exception class, attempt, correlation ID, and storage status. You can use headers added by Spring Kafka to trace record origin and latest failure; do not assume every version exposes the exact same header set.

Do not log sensitive payloads. If payloads must be retained for investigation, apply access controls and retention aligned with data security requirements.

### Priority Alerts

- Sharp spike in DLT ingress when retry topics fail en masse.
- DLT reforward rate does not drop after a dependency recovers.
- The same eventId appears many times consecutively.
- DLT handler fails continuously with a single exception type.
- DLT retention is nearing expiration before backlog is cleared.
- DLT consumer is not running as planned or lag is climbing rapidly.

## 17. Operational Procedure When the DLT Fails

When alerted to DLT processing failures:

1. **Confirm the strategy:** whether ALWAYS_RETRY_ON_ERROR, FAIL_ON_ERROR, or NO_DLT is assigned to that listener.
2. **Identify the failure:** payload, schema, database, permissions, serializer, or timeout.
3. **Inspect eventId and headers:** separate new events from the same event forwarded repeatedly.
4. **Check volume:** DLT ingress, reforward rate, oldest age, and remaining retention window.
5. **Isolate blast radius:** a single event/partition or the entire DLT handler failing.
6. **Stop harmful loops:** fix the root error, throttle load, or stop the DLT container in a controlled manner if needed.
7. **Restore the dependency or fix code:** confirm the handler can process a sample record.
8. **Bounded re-drive:** preserve the old eventId and ensure idempotency.
9. **Monitor post-recovery:** error rate, reforwards, and backlog must return to normal levels.
10. **Document root cause:** refine classification, timeouts, DLT configuration, and alerts.

If using ALWAYS_RETRY_ON_ERROR and the DLT enters an infinite duplication loop, merely adding partitions or consumers can make the system spin the loop faster. Fix the handler error and reforward policy first.

## 18. Required Test Scenarios

The scenarios below verify behavior at real failure boundaries. Run them in an integration environment with Kafka and the exact Spring Kafka version deployed:

1. **Main listener retries exhausted:** record enters the DLT when a DLT is configured.
2. **ALWAYS_RETRY_ON_ERROR + transient error:** DLT handler throws an exception, record is republished to the DLT at a new offset per policy.
3. **ALWAYS_RETRY_ON_ERROR + fatal exception:** record is not reforwarded in a loop per the fatal list of the running version.
4. **FAIL_ON_ERROR:** DLT handler fails; no new copy is forwarded by DltStrategy; observe error handler and committed offset.
5. **NO_DLT:** retries exhaust without a target DLT; verify metrics and alternative recovery mechanisms.
6. **autoStartDltHandler="false":** record reaches DLT, yet the DLT listener does not run until started.
7. **DLT handler fails after database commit:** record is redelivered or reforwarded without creating duplicate side effects.
8. **DLT publisher fails:** do not treat reforward as succeeded when publishing fails.
9. **App restart/rebalance:** verify offsets and idempotency while the DLT handler is processing.
10. **Short DLT retention:** test alerts and archiving procedures for failed data before retention expires.

Checking only that an exception was thrown is insufficient; verify target topics, record counts, offsets, business state, and re-drive capability.

## 19. Common Misconceptions

| Misconception | Why it is wrong | Accurate understanding |
|---|---|---|
| DltStrategy controls main listener retries | Retry and DLT are two separate stages | Attempts/backoff control retries; DltStrategy controls DLT |
| ALWAYS_RETRY_ON_ERROR always retries every error | Fatal exceptions may not be reforwarded | Check fatal classification for your version |
| FAIL_ON_ERROR means the record is deleted | Not reforwarding does not delete Kafka logs | Inspect container error handling and committed offsets |
| NO_DLT equals disabling the DLT consumer | NO_DLT does not create a DLT | Use autoStartDltHandler="false" if you still need to store errors |
| Low DLT lag means errors are resolved | Default logging handler may just log and commit | Track business processing state and unique events |
| Catching exceptions and logging in @DltHandler is safe | Framework may consider the listener successful | Rethrow if business persistence is not durable |
| A new DLT record is a new business event | Reforward creates a different offset for the same event | Keep eventId stable, handle idempotently |
| More DLT consumers is always better | Can accelerate retry loops and cause overload | Rate-limit and fix the root cause |
| DLT replaces backups | Retention can delete records before investigation | Design retention and recovery according to SLA |

## 20. Connecting DltStrategy to the Reliability Strategy

A reliable system must answer three questions:

**Where is the failed record?** In the main topic, retry topic, DLT, or a separate incident store? Trace eventId and offsets to locate it.

**Who owns the next step?** Framework auto-retry, DLT handler auto-recording, or an operator investigating and re-driving? DltStrategy should accurately reflect that ownership model.

**Is repeated processing safe?** DLT reforwards, restarts, rebalances, and timeouts can all produce duplicates. Handlers and side effects must be idempotent before enabling automatic reforwarding policies.

For critical business systems, you generally want a DLT, metrics, alerts, durable error persistence, and manual procedures when automatic recovery is impossible. For ephemeral, reconstructible events, NO_DLT can sometimes make sense. DltStrategy is an operational decision about how final failed records are stored and handled, and should be chosen based on data-loss impact, ordering, load, and recoverability.

## 21. References

- Spring for Apache Kafka — DLT Strategies: https://docs.spring.io/spring-kafka/reference/retrytopic/dlt-strategies.html
- Spring for Apache Kafka — Retry Topic Configuration: https://docs.spring.io/spring-kafka/reference/retrytopic/retry-config.html
- API DltStrategy: https://docs.spring.io/spring-kafka/docs/3.3.8/api/org/springframework/kafka/retrytopic/DltStrategy.html
- API RetryableTopic: https://docs.spring.io/spring-kafka/docs/3.3.8/api/org/springframework/kafka/annotation/RetryableTopic.html

**Remember:** ALWAYS_RETRY_ON_ERROR keeps the DLT moving forward by allowing failed records to be forwarded back to the DLT; FAIL_ON_ERROR does not perform that reforward; NO_DLT configures no DLT for the flow. If you want to keep the DLT but pause automatic handling, use autoStartDltHandler instead of NO_DLT. Pair every choice with idempotency, monitoring, adequate retention, and a clear recovery procedure.
