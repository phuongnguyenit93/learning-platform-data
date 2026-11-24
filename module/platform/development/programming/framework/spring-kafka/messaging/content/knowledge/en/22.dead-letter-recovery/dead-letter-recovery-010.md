# Avoiding Dead-Letter Loops

A Dead Letter Topic (DLT) stores records that have exhausted retries or cannot be processed under current policy. The DLT is normally the end of the automated flow so operations teams can inspect, repair data, or decide to redrive. If the DLT consumer keeps applying the same error policy and sends records right back into the same DLT, or if a listener accidentally subscribes to the DLT topic as well, a record can spin in a loop indefinitely.

A dead-letter loop does more than waste broker resources. It inflates the DLT rapidly, floods logs and alerts, obscures newly failed records among looping ones, and can bloat headers until producers can no longer send the record.

The design principle is defining a clear termination point for each flow. Retry topics are for bounded automatic retries; DLTs are for isolating records; quarantine is the final holding tier if DLT handling itself fails; and redrive is a controlled action after the root cause is fixed.

## Learning Objectives

After this lesson, you will be able to:

- Identify loop patterns arising across source topics, retry topics, and DLTs.
- Distinguish automatic retries, dead-letter recovery, and manual redrive.
- Configure listeners to consume only their intended business topics.
- Design a destination resolver with an allowlist that blocks invalid routes.
- Choose a failure-handling policy when a DLT handler fails.
- Use `DltStrategy.FAIL_ON_ERROR` with non-blocking retries when forwarding back to the DLT must be prevented.
- Separate error handlers across source listeners, DLT listeners, and quarantine listeners.
- Bound redrive attempts and maintain idempotency by `eventId`.
- Manage DLT headers to prevent record bloat across multiple forwards.
- Write tests proving a record cannot enter an infinite cycle.

## 1. How Does a Dead-Letter Loop Form?

A basic flow typically consists of a source topic, one or more retry topics, and a DLT:

~~~text
orders
  |
  | processing fails
  v
orders-retry-1000
  |
  | still fails
  v
orders-retry-5000
  |
  | attempts exhausted
  v
orders-dlt
~~~

This flow ends once the record reaches `orders-dlt`. A loop occurs when a record in the DLT is fed back into an automated policy without a clear stopping point.

Four scenarios commonly trigger loops.

### DLT listener fails and sends the record back to the DLT

~~~text
orders-dlt
    |
    v
DLT listener
    |
    | DLT processing fails
    v
Error handler
    |
    | republish to orders-dlt
    +----------------------> orders-dlt
~~~

With Spring Kafka non-blocking retries, the default DLT failure strategy is `ALWAYS_RETRY_ON_ERROR`. When the DLT handler fails, the record is forwarded back to the DLT so it does not block other DLT records. If the handler failure is deterministic, the record can bounce back to the DLT repeatedly.

### Business listener accidentally subscribes to the DLT too

~~~text
@KafkaListener(topicPattern = "orders.*")
        |
        +--> orders
        +--> orders-retry-1000
        +--> orders-dlt
        +--> orders-dlt-dlt
~~~

A broad pattern can match retry and DLT topics alike. The failed record gets consumed again as if it were a fresh business event, then goes straight back through the error handler.

### Destination resolver appends a suffix to the current topic

Suppose a resolver always builds the destination by appending `-dlt`:

~~~text
orders          -> orders-dlt
orders-dlt      -> orders-dlt-dlt
orders-dlt-dlt  -> orders-dlt-dlt-dlt
~~~

If a topic pattern keeps matching newly created topics, this chain can grow without bound. If the resolver always returns the same DLT topic based on original metadata, the record can be routed right back to the topic the listener is currently reading.

### Unbounded automatic redrive

A DLT consumer reads a record and sends it back to the source topic, then the source listener fails and sends it back to the DLT. If the DLT consumer automatically sends it back to the source again, the two topics form a cycle.

~~~text
orders -> orders-dlt -> orders -> orders-dlt -> ...
~~~

Redrive should only run after the root cause is fixed, and it must have a cap on attempts, event identity, and an audit trail.

## 2. Distinguishing Retry, DLT, Quarantine, and Redrive

These mechanisms play different roles. Merging all of them into one error handler makes it hard to tell whether a record has exhausted retries or is simply cycling around.

| Component | Purpose | Automatic retry? |
|---|---|---|
| Source topic | Main event stream | Listener's initial processing |
| Blocking retry | Retry inside the current consumer | Yes, per BackOff |
| Retry topic | Retry after a delay via a dedicated consumer | Yes, per configured attempts |
| DLT | Isolate records that exhausted retries or cannot be processed | Should not auto-redrive infinitely |
| Quarantine | Hold records when even DLT processing or recovery fails | No; usually requires investigation |
| Redrive | Reintroduce a fixed or approved record into processing | Possible, but must be bounded and audited |

A clean topology might look like:

~~~text
orders
  |
  +--> orders-retry-1000
  |
  +--> orders-retry-5000
  |
  +--> orders-dlt
           |
           +--> DLT processing succeeds -> incident store / archive
           |
           +--> DLT handler fails -> orders-quarantine
                                      |
                                      +--> manual investigation
                                      |
                                      +--> controlled redrive
~~~

Quarantine is the automated stopping point. Do not attach the same recoverer—routing records right back into quarantine—to the quarantine consumer itself.

## 3. Keep the Main Listener Off Retry and DLT Topics

The simplest way to prevent loops is restricting the business listener's subscription strictly to the topics it should process.

Prefer an explicit topic list:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders",
    groupId = "orders-service",
    containerFactory = "ordersListenerFactory"
)
public void consume(OrderEvent event) {
    orderService.process(event);
}
~~~

The listener subscribes only to `orders`. Retry topics and DLTs are managed by Spring Kafka's dedicated endpoints or separate operational listeners.

Avoid broad patterns like:

~~~java
@KafkaListener(
    topicPattern = "orders.*",
    groupId = "orders-service"
)
public void consume(OrderEvent event) {
    orderService.process(event);
}
~~~

This pattern can match `orders-dlt` and retry topics prefixed with `orders`. When a DLT record deserializes into the same `OrderEvent` type, the listener can process it like a new event and send it back to the DLT on failure.

### If you must use `topicPattern`

Exclude retry and DLT suffixes according to your system's naming convention. Illustrative pattern:

~~~java
@KafkaListener(
    topicPattern = "orders(?!-retry-.*|-dlt$|\\\\.DLT$).*",
    groupId = "orders-service"
)
public void consume(OrderEvent event) {
    orderService.process(event);
}
~~~

This expression excludes topics ending with illustrative suffixes `-retry-...`, `-dlt`, and `.DLT`. Default retry/DLT names vary by Spring Kafka version and configuration. Adjust the regex to your actual topic names and test which topics match.

Prefer explicit `topics` declarations whenever dynamic topic discovery is not required. A single-character typo in a regex can cause a listener to accidentally consume a DLT or miss a business topic.

## 4. Destination Resolvers Must Use an Allowlist

`DeadLetterPublishingRecoverer` lets you supply a destination resolver to choose the target topic and partition. Never build routes by unconditionally appending a suffix to `record.topic()`, because the record entering the recoverer might already come from a DLT.

Explicitly map source topics to their matching DLTs, and DLTs to quarantine if you want a final isolation tier.

Example:

~~~java
@Bean
public DeadLetterPublishingRecoverer ordersRecoverer(
        KafkaTemplate<Object, Object> dltKafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(
                    dltKafkaTemplate,
                    (record, exception) -> {
                        if ("orders".equals(record.topic())) {
                            // Failed event from source topic.
                            return new TopicPartition(
                                    "orders-dlt",
                                    record.partition()
                            );
                        }

                        if ("orders-dlt".equals(record.topic())) {
                            // DLT handler also failed: route to quarantine.
                            return new TopicPartition(
                                    "orders-quarantine",
                                    -1
                            );
                        }

                        // Fail closed if the topic is not in the routing table.
                        throw new IllegalStateException(
                                "No DLT route configured for topic "
                                        + record.topic()
                        );
                    }
            );

    // Wait for the send result and throw an exception if DLT publishing fails.
    recoverer.setFailIfSendResultIsError(true);

    return recoverer;
}
~~~

In this example:

- Records from `orders` go to `orders-dlt`, preserving the original partition.
- Records from `orders-dlt` that fail again go to `orders-quarantine`; a negative partition leaves partition selection to the producer.
- Records from an undeclared topic cause recovery to fail rather than spawning a chain of new topics.
- Quarantine has no automatic route in this resolver, requiring a separate operational policy.

With the default destination resolver, Spring Kafka currently uses a `-dlt`-suffixed topic and the same partition as the original record. Therefore, the DLT topic needs at least as many partitions as the source topic. Older versions may use a different default suffix; verify the version you are running.

### Do not route blindly using original metadata

DLT records carry headers describing the original source topic. Those headers are useful for auditing and analysis, but they do not mean every recovery step should send records back to the original topic or the same DLT.

If a resolver inspects `DLT_ORIGINAL_TOPIC` to choose a destination, also check the current topic, error type, and redrive state. Routing must be an intentional decision, not string concatenation from a header.

## 5. Configuring Error Handlers for Source and DLT

For record listeners using `DefaultErrorHandler`, configure the retry count and recoverer. The example below performs one initial attempt and two retries spaced one second apart.

~~~java
@Bean
public DefaultErrorHandler ordersErrorHandler(
        DeadLetterPublishingRecoverer ordersRecoverer) {

    DefaultErrorHandler errorHandler =
            new DefaultErrorHandler(
                    ordersRecoverer,
                    new FixedBackOff(1000L, 2L)
            );

    errorHandler.addNotRetryableExceptions(
            InvalidOrderException.class,
            UnsupportedEventVersionException.class
    );

    return errorHandler;
}
~~~

Attach the error handler to the source listener's factory:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        ordersListenerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory,
                DefaultErrorHandler ordersErrorHandler) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(ordersErrorHandler);

    return factory;
}
~~~

If the DLT listener also needs bounded retries before moving records to quarantine, it can share the resolver and error handler that route `orders-dlt` to `orders-quarantine`. The DLT listener must have its own consumer group to manage offsets independently:

~~~java
@KafkaListener(
    id = "orders-dlt-listener",
    topics = "orders-dlt",
    groupId = "orders-dlt-operations",
    containerFactory = "ordersDltListenerFactory"
)
public void inspectDlt(ConsumerRecord<String, OrderEvent> record) {
    incidentStore.record(
            record.value(),
            record.headers(),
            record.topic(),
            record.partition(),
            record.offset()
    );
}
~~~

If `incidentStore` persists successfully, the listener returns normally and the container commits the offset per `AckMode`. If persistence fails, the error handler can perform bounded retries and then route the record to `orders-quarantine` per the configured route.

Quarantine should never reuse the same error handler to send records back to itself. Leave quarantine for operator-only tooling, or use a dedicated container with `CommonContainerStoppingErrorHandler` to stop on failure and keep the record uncommitted until intervention occurs.

Separating group IDs isolates DLT consumer progress from the source consumer. It does not prevent loops on its own; routes and subscriptions must still be bounded.

## 6. Verifying the DLT Publish Result

Another failure mode often mistaken for a dead-letter loop happens when the recoverer calls `KafkaTemplate` to send to the DLT, yet the broker never receives the record. If the application marks recovery successful despite the publish failure, the source offset may be committed and the record lost from processing.

`DeadLetterPublishingRecoverer` supports:

- `setFailIfSendResultIsError(true)`: wait for the send result and throw an exception if publishing fails.
- `setWaitForSendResultTimeout(...)`: set how long to wait for the send result.
- `setThrowIfNoDestinationReturned(true)`: require the resolver to return a valid destination.

Example:

~~~java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(
                dltKafkaTemplate,
                destinationResolver
        );

recoverer.setFailIfSendResultIsError(true);
recoverer.setWaitForSendResultTimeout(Duration.ofSeconds(30));
recoverer.setThrowIfNoDestinationReturned(true);
~~~

These APIs were introduced in corresponding Spring Kafka versions, with send-result confirmation settings added in 2.7. Check the Javadoc for your project's dependency version.

If DLT publishing fails and the recoverer throws an exception, the source record is not yet considered recovered; the error handler can redeliver and retry recovery. This safeguard prevents committing offsets before the DLT write succeeds. It can repeat while the DLT broker or serializer is broken, so combine it with backoff, alerting, and recovery failure monitoring.

Never disable publish confirmation just to keep the consumer moving. Doing so can turn a DLT failure into silent data loss.

## 7. Using `DltStrategy.FAIL_ON_ERROR` with `@RetryableTopic`

Spring Kafka non-blocking retries can create retry topics and a DLT for listeners annotated with `@RetryableTopic`. The DLT handler is declared with `@DltHandler` or configured via `RetryTopicConfigurationBuilder`.

Important detail: the default DLT failure strategy is `ALWAYS_RETRY_ON_ERROR`. If the DLT handler throws an exception, the record is forwarded back to the DLT so it does not block other DLT records. For deterministic errors, this becomes a self-publishing DLT loop.

When you do not want failed records forwarded back to the DLT, configure `DltStrategy.FAIL_ON_ERROR`:

~~~java
@Component
public class OrderRetryListener {

    @RetryableTopic(
        attempts = "4",
        backoff = @Backoff(
                delay = 1000,
                multiplier = 2.0
        ),
        dltTopicSuffix = "-dlt",
        retryTopicSuffix = "-retry",
        dltProcessingFailureStrategy = DltStrategy.FAIL_ON_ERROR
    )
    @KafkaListener(
        topics = "orders",
        groupId = "orders-service"
    )
    public void consume(OrderEvent event) {
        orderService.process(event);
    }

    @DltHandler
    public void processDlt(
            OrderEvent event,
            @Header(KafkaHeaders.DLT_ORIGINAL_TOPIC) String originalTopic,
            @Header(KafkaHeaders.DLT_ORIGINAL_PARTITION) Integer originalPartition,
            @Header(KafkaHeaders.DLT_ORIGINAL_OFFSET) Long originalOffset,
            @Header(KafkaHeaders.DLT_EXCEPTION_FQCN) String exceptionType) {

        incidentStore.record(
                event,
                originalTopic,
                originalPartition,
                originalOffset,
                exceptionType
        );
    }
}
~~~

In this example, `attempts = 4` includes the initial attempt and subsequent retry-topic attempts. Once attempts are exhausted, the record moves to the DLT. If the DLT handler persists the incident and returns normally, the record advances according to the DLT listener's offset mechanism.

If the DLT handler throws an exception, `FAIL_ON_ERROR` prevents forwarding the record back to the DLT. The failed record is not marked handled; monitor the container and decide whether to stop, investigate, or recover according to operational policy.

With `ALWAYS_RETRY_ON_ERROR`, the default behavior forwards the record back to the DLT when DLT processing fails. With `NO_DLT`, the framework configures no DLT after retries finish; choose it only when the system accepts ending the flow without storing the record in a DLT.

If no `@DltHandler` is declared, Spring Kafka uses a default handler that only logs. When you need to store incidents, archive, or investigate, implement an idempotent DLT handler and monitor persistence outcomes.

## 8. The DLT Handler Must Be a Terminal Step, Not a Second Source Listener

A well-behaved DLT handler typically performs one or more of these actions:

- Persist an incident in a database or ticketing system.
- Store the payload, `eventId`, and Kafka metadata for investigation.
- Send controlled operational notifications.
- Mark the record status as needing repair or awaiting approval.
- Exit cleanly once durably persisted.

Never let a DLT handler directly call the exact same source processing service and rethrow if source processing fails. That easily creates a source-DLT-source cycle.

Example handler persisting an incident by `eventId`:

~~~java
@Service
public class DltIncidentService {

    private final IncidentRepository repository;

    public void record(
            OrderEvent event,
            String originalTopic,
            Integer originalPartition,
            Long originalOffset,
            String exceptionType) {

        Incident incident = new Incident(
                event.eventId(),
                originalTopic,
                originalPartition,
                originalOffset,
                exceptionType,
                "PENDING_REVIEW"
        );

        // eventId has a unique constraint so DLT redelivery does not create duplicate incidents.
        repository.saveIfAbsent(incident);
    }
}
~~~

If the DLT listener receives the same record again due to an uncommitted offset or consumer restart, a unique `eventId` prevents creating duplicate incidents.

If persisting the incident to the database fails, do not pretend success and commit the offset. Let the container retry or stop per configured policy, then fire an alert so operations knows the DLT consumer is blocked.

## 9. Never Apply the Same Retry Policy to Quarantine

Quarantine is the final tier for storing records needing intervention. If the quarantine consumer shares an error handler with the source and DLT, a quarantine processing failure can cause the resolver to route to yet another topic or back into quarantine.

Example topology to avoid:

~~~text
orders-quarantine
       |
       | fails
       v
orders-quarantine-dlt
       |
       | listener pattern still matches
       v
orders-quarantine-dlt-dlt
       |
       v
       ...
~~~

Safe alternatives:

1. Have no automated consumer for quarantine; use operational tools to read and export records.
2. If using a quarantine consumer, give it a dedicated factory with `CommonContainerStoppingErrorHandler`.
3. Log quarantine processing failures to an external system and stop the container when it cannot proceed.
4. Only redrive after explicit approval and with capped attempts.

Example factory that stops the container if the quarantine handler fails:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        quarantineListenerFactory(
                ConsumerFactory<String, OrderEvent> quarantineConsumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(quarantineConsumerFactory);
    factory.setCommonErrorHandler(
            new CommonContainerStoppingErrorHandler()
    );

    return factory;
}
~~~

This error handler does not publish records to another DLT. When the listener fails, the container stops per handler semantics; the uncommitted record can be read again when the container restarts. The system needs alerts and an intervention workflow before restarting.

## 10. Redrive Must Be Bounded and Audited

Redrive means returning a record from the DLT to the source topic after the root cause is fixed. It is an intentional operation, not part of automatic retries.

A redrive workflow should:

1. Identify `eventId` and original record location.
2. Read exception metadata and root cause.
3. Repair data or deploy a compatible fix.
4. Approve records eligible for redrive.
5. Increment `redriveCount` and generate a new `redriveId`.
6. Resend the record to the source or a dedicated redrive topic.
7. Record an audit entry with operator, timestamp, reason, and outcome.
8. Stop if the redrive limit is exceeded.

Example bounded flow:

~~~text
orders-dlt
    |
    v
Operator inspects incident
    |
    +--> root cause not fixed -> keep in DLT
    |
    +--> fixed, eligible
              |
              v
       redriveCount < 3 ?
          /          \
        Yes           No
        |               |
        v               v
   orders-redrive   orders-quarantine
        |
        v
   controlled processing
~~~

You can send records to a separate redrive topic to distinguish replay traffic from new events. The redrive consumer can run the same business logic while checking `redriveId`, `eventId`, and replay count.

### Redrive headers do not replace durable auditing

You can attach headers such as:

| Header | Purpose |
|---|---|
| `x-redrive-id` | Identifies a single redrive execution |
| `x-redrive-count` | Number of times the record has been redriven |
| `x-redrive-by` | Person or service requesting the redrive |
| `x-redrive-reason` | Reason for redrive |
| `x-original-event-id` | Original business event identifier |

Kafka headers can be lost or altered by producers, converters, or export/import tooling. For critical operational workflows, store redrive history in a database or audit system. Use `eventId` as the idempotency key to prevent duplicate side effects.

### Example checking the redrive count

~~~java
public void redrive(
        ConsumerRecord<String, OrderEvent> failedRecord,
        int currentRedriveCount) {

    if (currentRedriveCount >= 3) {
        throw new IllegalStateException(
                "Redrive limit reached for event "
                        + failedRecord.value().eventId()
        );
    }

    int nextCount = currentRedriveCount + 1;

    ProducerRecord<String, OrderEvent> replay =
            new ProducerRecord<>(
                    "orders-redrive",
                    failedRecord.key(),
                    failedRecord.value()
            );

    replay.headers().add(
            new RecordHeader(
                    "x-redrive-count",
                    ByteBuffer.allocate(Integer.BYTES)
                            .putInt(nextCount)
                            .array()
            )
    );

    replay.headers().add(
            new RecordHeader(
                    "x-redrive-id",
                    UUID.randomUUID().toString()
                            .getBytes(StandardCharsets.UTF_8)
            )
    );

    kafkaTemplate.send(replay);
}
~~~

This snippet illustrates sending to a dedicated redrive topic. In production, read `redriveCount` from headers or the incident store, verify approval permissions, write audit entries before/after sending, and confirm publish results. Never hardcode a default count of 0 across all redrives.

## 11. Maintain Idempotency When Records Return to Source

A record resent to source can be processed again by the consumer even if an earlier attempt partially applied side effects. This happens when a listener writes to a database and then fails to commit the offset, or when redrive resends an event that was already processed.

Use a stable `eventId` and an inbox/idempotency store:

~~~java
@Transactional
public void process(OrderEvent event) {
    if (inboxRepository.existsByEventId(event.eventId())) {
        return;
    }

    orderService.apply(event);

    inboxRepository.save(
            new InboxEntry(event.eventId(), Instant.now())
    );
}
~~~

In this example, the business update and inbox write must occur in the same database transaction. A unique constraint on `eventId` adds protection against concurrent processing.

If an event was already processed successfully, redrive must not charge a payment, send an email, or deduct inventory a second time. Redrive must preserve the original `eventId`; only `redriveId` identifies the replay execution.

## 12. Managing DLT Headers So Records Do Not Bloat

`DeadLetterPublishingRecoverer` preserves original headers and adds metadata such as:

- `DLT_EXCEPTION_FQCN`: exception class.
- `DLT_EXCEPTION_MESSAGE`: error message.
- `DLT_EXCEPTION_STACKTRACE`: stack trace.
- `DLT_ORIGINAL_TOPIC`: source topic.
- `DLT_ORIGINAL_PARTITION`: source partition.
- `DLT_ORIGINAL_OFFSET`: source offset.
- `DLT_ORIGINAL_TIMESTAMP`: source timestamp.
- `DLT_ORIGINAL_CONSUMER_GROUP`: consumer group that failed.

When a record is republished multiple times through retries or DLTs, Kafka can retain multiple headers with the same name. Stack traces and error metadata can steadily enlarge the record.

Spring Kafka provides options:

- `appendOriginalHeaders`: controls whether original headers are appended when already present; defaults to `true`.
- `stripPreviousExceptionHeaders`: strips old exception headers before adding new error details; defaults to `true` as of Spring Kafka 2.8.
- `excludeHeader(...)`: omits specific standard headers, such as stack traces, if they should not propagate across multiple hops.

Example:

~~~java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(dltKafkaTemplate);

recoverer.setAppendOriginalHeaders(false);
recoverer.setStripPreviousExceptionHeaders(true);

// If stack trace is not needed in the DLT:
recoverer.excludeHeader(
        DeadLetterPublishingRecoverer.HeaderNames.HeadersToAdd.EX_STACKTRACE
);
~~~

Verify API names and enums against your Spring Kafka version. With `appendOriginalHeaders=false`, only the first original header is kept rather than appending another value on every forward. If full history is needed, store it in an incident store instead of relying on an endlessly growing header chain.

Kafka supports multiple headers with the same name. When reading metadata, use `lastHeader()` for the latest value or iterate all headers for full history. Never assume `headers().lastHeader()` always reflects the very first occurrence of the event.

## 13. Do Not Confuse Retry Topics with DLTs

Non-blocking retries advance records across retry topics based on backoff timestamps. Once attempts are exhausted, the record goes to the DLT if configured.

Example:

~~~text
orders
  |
  +--> orders-retry-1000
  |
  +--> orders-retry-2000
  |
  +--> orders-retry-4000
  |
  +--> orders-dlt
~~~

This is a forward-only pipeline. It will not loop as long as:

- `attempts` is finite.
- Each retry topic has one deterministic next step.
- The DLT is excluded from source topic subscriptions.
- The DLT handler does not forward records back to the DLT infinitely.
- No listener pattern accidentally reads old retry topics.

Spring Kafka can automatically create retry topics and corresponding consumers when using `@RetryableTopic`. Consumer groups for retry topics/DLTs are derived from the group ID and topic suffix to separate progress from the source group. With custom setups, verify the actual group IDs and topic routing.

Non-blocking retries can break per-topic record ordering because a failed record moves to a retry topic while subsequent records keep advancing. If business ordering is critical, consider blocking retries or version guards.

## 14. Choosing Which Errors to Retry vs. Send Directly to DLT

Not every error warrants multiple retries. Transient errors can recover; data or schema errors usually do not heal on retry.

Examples:

| Error | Typical suitable strategy |
|---|---|
| Brief database timeout | Retry with backoff |
| HTTP 503 from dependency | Bounded retries with backoff |
| `ValidationException` | No retry; route to DLT |
| Unsupported event version | No retry; DLT for compatibility handling |
| Unparseable JSON | Do not waste retries; DLT or quarantine |
| DLT broker temporarily unavailable | Keep source record unrecovered and retry DLT publish |
| DLT incident store temporarily failing | Retry DLT processing or stop container per policy |

You can register non-retryable exceptions on `DefaultErrorHandler`:

~~~java
DefaultErrorHandler errorHandler =
        new DefaultErrorHandler(
                recoverer,
                new FixedBackOff(1000L, 2L)
        );

errorHandler.addNotRetryableExceptions(
        InvalidOrderException.class,
        UnsupportedEventVersionException.class
);
~~~

When an error cannot be solved by retrying the exact same payload, repeated retries just delay arrival at the DLT. Proper exception classification moves bad records to isolation quickly and reduces consumer pressure.

## 15. Verifying DLT Topics and Partitions

With the default `DeadLetterPublishingRecoverer` resolver, records are typically sent to a DLT topic with the same partition number as the source record. If the source has 12 partitions, the DLT needs at least 12 partitions to keep this mapping.

When using a custom resolver:

- If preserving partitions, ensure the DLT has matching partitions.
- If the destination partition is negative, the producer chooses the partition.
- If routing to quarantine, you can let the producer pick partitions or follow a dedicated rule.
- If the target topic does not exist, verify auto-create policies and ACLs.
- If the DLT producer lacks write permission, the recoverer must raise an error so the source record is not treated as recovered.

Never create a DLT with fewer partitions than the source and assume Kafka will magically remap partitions. Verify topic metadata and write permissions in integration tests.

## 16. Testing That No Loops Exist

Tests must trace an event's path across topics, not merely assert that the listener threw an exception.

Create an event with a unique `eventId`, send it to the source topic, and record topic, partition, offset, retry count, and DLT headers at each hop.

Key scenarios:

1. Source event succeeds: no records in retry or DLT.
2. Source event hits a transient error then succeeds: traverses only needed retries, never enters DLT.
3. Source event exhausts attempts: exactly one record appears in the DLT.
4. DLT handler succeeds: incident is persisted and nothing is republished to DLT.
5. DLT handler fails with `DltStrategy.FAIL_ON_ERROR`: record is not forwarded back to DLT.
6. DLT handler fails with `ALWAYS_RETRY_ON_ERROR`: confirms forwarding behavior back to DLT and demonstrates why it is unsuitable for permanent errors.
7. Main listener uses `topicPattern`: verify the pattern does not match retry, DLT, or quarantine.
8. Destination resolver receives a record from DLT: routes to quarantine, never creating unintended `orders-dlt-dlt`.
9. Destination resolver receives a topic outside the allowlist: recovery fails closed.
10. DLT publish fails: source record is not committed as recovered.
11. Redrive count hits limit: no further record is sent back to source.
12. Same `eventId` redriven multiple times: side effects apply only once thanks to idempotency.
13. Record passes through multiple DLT/retry hops: headers do not grow unbounded while retaining original metadata.
14. Restart DLT consumer while incident store is unavailable: record remains uncommitted and recoverable.
15. Quarantine listener fails: container stops or record is held per final policy without spawning endless topics.

Do not rely solely on sleeps to wait for results. Use Kafka test utilities, Awaitility, or latches with timeouts, then query records by `eventId` across each topic.

## 17. Monitoring and Alerting on Loops

A DLT can spike due to a schema error or a loop. Measure enough metrics to tell the two apart.

Metrics to monitor:

| Metric | What to detect |
|---|---|
| DLT publish rate | New records being routed to the DLT |
| DLT consumer lag | DLT handler processing slowly or stalled |
| DLT failure count | DLT handler failing repeatedly |
| Recovery failure count | Inability to publish records to the DLT |
| Retry topic lag | Records lingering in retry topics too long |
| Quarantine count | Records escaping automated handling |
| Redrive count | A single event replayed multiple times |
| Repeated `eventId` | Same event appearing across multiple processing cycles |
| DLT header size | Metadata growing abnormally across forwards |

Alerts to configure:

- A single `eventId` appears multiple times in the same DLT within a short window.
- DLT publish rate spikes abruptly relative to source traffic.
- DLT consumer lag grows continuously.
- Quarantine receives new records.
- A DLT handler fails consecutively.
- An event exceeds the redrive limit.

Logs should include `eventId`, source topic, partition, offset, DLT destination, exception type, and `redriveId`. Do not log full sensitive payloads or huge stack traces on every retry.

## 18. Operational Runbook When a DLT Loop Is Detected

When a looping record is spotted, stop the source generating further copies before deep investigation.

Reference procedure:

1. Identify the record's `eventId` and current topic.
2. Inspect DLT headers for the original source topic, partition, offset, and consumer group.
3. Check the `topicPattern` of listeners reading the DLT.
4. Check whether the destination resolver routes the DLT back to itself or appends suffixes endlessly.
5. Check `DltStrategy` if using `@RetryableTopic`.
6. Pause the DLT handler or looping listener pattern if necessary.
7. Save the incident and payload in a queryable store.
8. Fix routing, subscription, or DLT failure policy.
9. Verify with a new `eventId` in a test environment.
10. Redrive old records only after attempt limits and idempotency are in place.

Never delete a DLT topic to erase evidence of a loop. Records in the DLT are investigation artifacts; preserve or snapshot them per your system's retention process before cleaning up.

## 19. Common Design Mistakes

**Main listener subscribes to an overly broad pattern.** The listener consumes retry and DLT topics as new events. Use an explicit topic list or a regex excluding internal suffixes.

**Destination resolver appends `-dlt` to the current topic.** DLT records keep spawning new DLT topics. Use a source-to-DLT allowlist and route DLT failures to quarantine.

**Default `DltStrategy` left unexamined.** A failing DLT handler can forward records back to the DLT under `ALWAYS_RETRY_ON_ERROR`. Choose `FAIL_ON_ERROR` when forwarding must stop and design DLT error handling explicitly.

**DLT handler immediately resends to source on failure.** Source and DLT form an automated cycle. Only redrive after fixing the root cause, with approval and limits.

**Sharing the same error handler with quarantine.** Quarantine failures get sent to another topic or back to quarantine. Use a container-stopping handler or a dedicated operational workflow.

**Not confirming DLT publish results.** The source offset may be committed even though the record never reached the DLT. Enable `failIfSendResultIsError` and check timeouts.

**Unbounded redrive.** A poison event can cycle back to source repeatedly. Enforce `redriveCount`, `redriveId`, and an audit store.

**No idempotency.** Replayed events cause duplicate side effects. Use a stable `eventId` and an inbox/unique constraint.

**Keeping every exception header across many hops.** Records bloat and hit `RecordTooLargeException`. Manage `appendOriginalHeaders`, `stripPreviousExceptionHeaders`, and stack traces.

**Using DLT as an indefinite retry loop.** The DLT loses its isolation role and operations cannot tell active failures apart. Use retry topics for automatic retries, and DLT/quarantine for investigation.

## 20. Dead-Letter Loop Prevention Checklist

- [ ] Source listener subscribes only to the intended business topics.
- [ ] Topic patterns do not match retry, DLT, or quarantine topics.
- [ ] Retry attempts are finite and backoff is explicitly configured.
- [ ] The DLT is the termination point of automatic retries.
- [ ] The DLT failure strategy is chosen deliberately.
- [ ] The DLT handler never automatically sends back to source without redrive approval.
- [ ] Destination resolver uses an allowlist and handles unsupported topics explicitly.
- [ ] Failed DLT records route to quarantine or halt under a separate policy.
- [ ] Quarantine does not reuse the same recoverer to send back to itself.
- [ ] DLT publishing is confirmed before the source record is marked recovered.
- [ ] DLT topics have proper partitions and ACLs.
- [ ] DLT headers are managed so they do not grow indefinitely.
- [ ] Redrives are bounded, audited, and preserve a stable `eventId`.
- [ ] Consumers are idempotent for replayed records.
- [ ] Integration tests verify no source-retry-DLT cycle exists.
- [ ] Metrics and alerts cover DLT failures, quarantine, and repeated `eventId`s.

## Conclusion

Prevent dead-letter loops by treating the DLT as the final isolation boundary of the automated flow. Business listeners should only read source topics; destination resolvers need explicit allowlists; DLT handlers need their own failure strategy; and quarantine must never route records back to itself. With `@RetryableTopic`, consider `DltStrategy.FAIL_ON_ERROR` when a DLT handler fails to prevent forwarding back to the DLT under the default `ALWAYS_RETRY_ON_ERROR`. Redrive only after fixing the root cause, with bounded attempts and auditing. Combining `eventId`, idempotency, DLT publish confirmation, and header/lag monitoring ensures the recovery flow has a clear stopping point.

## References

- [Spring Kafka – Handling Exceptions and Publishing Dead-letter Records](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring Kafka – DLT Strategies](https://docs.spring.io/spring-kafka/reference/retrytopic/dlt-strategies.html)
- [Spring Kafka – How the Non-Blocking Retry Pattern Works](https://docs.spring.io/spring-kafka/reference/retrytopic/how-the-pattern-works.html)
- [Spring Kafka – Retry Topic Configuration](https://docs.spring.io/spring-kafka/reference/retrytopic/retry-config.html)

