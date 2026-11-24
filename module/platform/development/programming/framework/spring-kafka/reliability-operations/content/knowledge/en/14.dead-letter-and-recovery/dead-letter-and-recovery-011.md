# DltHandler

In a system using Spring Kafka, a record can fail even after multiple processing retries. For example, a consumer receives a payment event whose payload is invalid, or a downstream service keeps returning errors after the retry budget is exhausted. If retried indefinitely, the failing record can consume resources and increase latency for subsequent records. A common recovery option is moving the record to a **dead-letter topic (DLT)** to preserve evidence and handle it separately.

`@DltHandler` is a Spring Kafka annotation used to designate **the method that processes records consumed from the DLT** in the non-blocking retry mechanism managed by `@RetryableTopic`. This method is not what puts a record into the DLT in the first place; moving the record to the DLT is handled by the retry-topic infrastructure and recoverer. `DltHandler` is the intake point **after the record has arrived in the DLT**.

Distinguishing these two steps is critical when designing a reliable pipeline:

- **Publishing to the DLT:** Preserves failed records without blocking processing on the main topic, with metadata indicating origin and cause.
- **Consuming with DltHandler:** Records the incident, classifies it, saves state, raises notifications, or feeds the record into a controlled investigation/replay workflow.

A good `DltHandler` does not necessarily fix records itself or immediately send them back to the main topic. The goal is creating a controlled point for visibility and recovery, avoiding data loss and duplicate business side effects.

## 1. Where does the DLT sit in the retry flow?

In non-blocking retries, failed records are published to retry topics with appropriate wait intervals. When a record is no longer eligible for retry, it is routed to the DLT if the policy configures a DLT.

~~~text
Producer
   |
   v
orders.events
   |
   v
@KafkaListener processes business logic
   |
   +---- Succeeded -----------------> Commit/ack per container
   |
   +---- Exception
             |
             v
       Retry classification
             |
       +-----+-----------------------+
       |                             |
    Retryable                   Non-retryable
       |                             |
       v                             |
  Retry topic                        |
       |                             |
       +-- Succeeded --> Done        |
       |                             |
       +-- Attempts exhausted -------+
                                     |
                                     v
                                  DLT topic
                                     |
                                     v
                              DLT listener container
                                     |
                                     v
                                 @DltHandler
                                     |
                             Write audit / create ticket
                             / store recovery status
~~~

Topic names and retry steps depend on `@RetryableTopic` configuration or the retry-topology API. The diagram only illustrates the functional components.

### 1.1. Three concepts not to confuse

| Concept | Role | When does it run? |
|---|---|---|
| `@KafkaListener` | Processes records on the main topic and infrastructure-created retry endpoints | When the container receives a record |
| `DeadLetterPublishingRecoverer` | Publishes failed records to the target topic once error handling decides recovery | When a failed record needs recovery |
| `@DltHandler` | Consumes records already sitting in the DLT in a non-blocking topology | When the DLT consumer is started and polls records |

`@DltHandler` is not a generic name for any listener that subscribes to a DLT on its own. If an application defines its own `@KafkaListener(topics = "orders.events-dlt")`, that is a regular DLT listener, not necessarily an endpoint managed by the retry-topic infrastructure.

## 2. When is @DltHandler needed?

A system with a DLT must decide who is responsible for handling records that land there. `@DltHandler` fits when:

1. The application uses `@RetryableTopic` or retry-topic infrastructure.
2. You want to define the DLT record-intake method in the same class.
3. You want to record audits and failure-cause metadata.
4. You want to raise alerts/tickets or record a pending-investigation state.
5. You want to build an operator-approved or safely gated automated replay workflow.

If the goal is solely **retaining records on the DLT for operations to inspect with external tools**, you do not necessarily have to deploy a `DltHandler` that automatically reads and processes every record. Some systems deliberately do not run a default DLT consumer so data stays on the topic until an inspection workflow is ready.

### 2.1. What if there is no DltHandler?

In Spring Kafka's non-blocking retry setup, when no `@DltHandler` is declared, the framework can provide default DLT handling behavior, such as logging. This **is not equivalent** to a ticket-creation or business reconciliation workflow.

Do not rely on default logging to conclude that DLT records are adequately managed. Explicitly define DLT ownership, retention, alerting mechanisms, and how replay works.

## 3. Example combining @RetryableTopic and @DltHandler

Example billing application consuming order-created events. Transient dependency errors are retried; invalid business payloads route to recovery faster.

~~~java
@Component
public class BillingOrderListener {

    private final BillingService billingService;
    private final DltAuditService dltAuditService;

    public BillingOrderListener(
            BillingService billingService,
            DltAuditService dltAuditService) {
        this.billingService = billingService;
        this.dltAuditService = dltAuditService;
    }

    @RetryableTopic(
            attempts = "4",
            backoff = @Backoff(
                    delay = 1_000,
                    multiplier = 2.0,
                    maxDelay = 10_000),
            include = {
                    TemporaryPaymentGatewayException.class
            },
            exclude = {
                    InvalidOrderEventException.class
            },
            dltTopicSuffix = "-dlt")
    @KafkaListener(
            topics = "orders.events",
            groupId = "billing")
    public void onOrder(OrderEvent event) {
        billingService.processIdempotently(event);
    }

    @DltHandler
    public void onDlt(
            ConsumerRecord<String, OrderEvent> record) {
        dltAuditService.persistIfAbsent(
                record.topic(),
                record.partition(),
                record.offset(),
                record.key(),
                record.value());
    }
}
~~~

The example assumes domain classes and services are already defined. `DltAuditService.persistIfAbsent(...)` is an application business method, not a built-in Spring Kafka API. In production systems, use event IDs, record origin, and database constraints to guarantee idempotent audit writes.

In this illustrative configuration, `attempts = "4"` is the **total number of attempts under the non-blocking retry policy**, including the initial processing attempt. If a record keeps failing with a retryable exception, it can go through once on the main topic and up to three times across retry endpoints before entering the DLT. Exceptions listed in `exclude` can go straight to the DLT without consuming all retry attempts.

### 3.1. Why place @DltHandler in the same class?

`@DltHandler` operates bound to the endpoint established by `@RetryableTopic`. Placing it inside the same bean containing `@KafkaListener` and the retry configuration lets the framework resolve the corresponding DLT handler.

Do not create a standalone class containing only `@DltHandler` expecting the framework to auto-bind it to every listener. If you want a shared DLT service, invoke that service from each corresponding `DltHandler`, or design an independent DLT listener with explicit subscriptions and ownership.

If an application has multiple listeners and multiple retry topologies, verify exactly which `DltHandler` handles each DLT. Depending on version and registration style, constraints on the count/scope of `@DltHandler` methods can vary; never assume one handler applies globally.

## 4. What data does DltHandler receive?

`DltHandler` is a message listener. It can receive deserialized payloads or a `ConsumerRecord`, depending on method signature and container factory configuration.

Information typically needed during recovery:

- Current DLT topic.
- Partition and offset of the record in the DLT.
- Record key and payload.
- Headers holding origin, exception, and retry metadata.
- Event ID/correlation ID supplied by the producer.
- Timestamps when the error occurred and when the DLT consumer processed it.

`ConsumerRecord.topic()` inside `DltHandler` returns the **current DLT name**, not the original topic by default. Likewise, `record.offset()` is the offset in the DLT; it does not equal the source record's offset because each topic maintains its own log and offsets.

To find the original topic/partition/offset, read the corresponding DLT headers.

## 5. Common headers in the DLT

Spring Kafka uses headers to store source record details and failure causes when publishing to the DLT. Common constants live in `KafkaHeaders`.

| Header | Contents | Usage |
|---|---|---|
| `KafkaHeaders.DLT_ORIGINAL_TOPIC` | Original topic of the record | Trace back to source |
| `KafkaHeaders.DLT_ORIGINAL_PARTITION` | Original partition | Isolate failing partition |
| `KafkaHeaders.DLT_ORIGINAL_OFFSET` | Original offset | Reconciliation/replay |
| `KafkaHeaders.DLT_ORIGINAL_CONSUMER_GROUP` | Original consumer group if metadata is available | Identify responsible consumer |
| `KafkaHeaders.DLT_EXCEPTION_FQCN` | Fully qualified exception class name | Error grouping |
| `KafkaHeaders.DLT_EXCEPTION_MESSAGE` | Exception message | Root-cause diagnosis |
| `KafkaHeaders.DLT_EXCEPTION_STACKTRACE` | Stack trace | Deep investigation |

**Version note:** Header names and presence can change across Spring Kafka versions, exception types, and recoverer settings. A header may be missing, replaced, or duplicated across a retry chain. Operational code must handle nulls.

Do not store raw exception messages or long stack traces in metric tags. They have high cardinality and can contain sensitive data.

### 5.1. Safely reading string headers

Example logging the source topic and exception class inside `DltHandler`:

~~~java
@DltHandler
public void onDlt(ConsumerRecord<String, OrderEvent> record) {

    String originalTopic = utf8Header(
            record.headers(),
            KafkaHeaders.DLT_ORIGINAL_TOPIC);

    String exceptionClass = utf8Header(
            record.headers(),
            KafkaHeaders.DLT_EXCEPTION_FQCN);

    log.error(
            "DLT received: currentTopic={}, " +
            "dltPartition={}, dltOffset={}, " +
            "originalTopic={}, exceptionClass={}",
            record.topic(),
            record.partition(),
            record.offset(),
            originalTopic,
            exceptionClass);

    dltAuditService.persistIfAbsent(record, originalTopic);
}

private static String utf8Header(
        Headers headers, String headerName) {
    Header header = headers.lastHeader(headerName);
    if (header == null || header.value() == null) {
        return null;
    }
    return new String(
            header.value(), StandardCharsets.UTF_8);
}
~~~

In a complete Java class, the `utf8Header` helper must be placed in proper scope, and imports like `Headers`, `Header`, and `StandardCharsets` must be added. The snippet demonstrates reading string headers; **do not** use UTF-8 decoding for numeric headers.

### 5.2. Reading original offset/partition

Offsets and partitions are numeric data. Do not assume these headers contain UTF-8 digits. Read them according to the format used by your deployed Spring Kafka version, or use verified header mappers/argument conversion.

Example principle for reading raw bytes:

~~~java
private static Long originalOffset(Headers headers) {
    Header header = headers.lastHeader(
            KafkaHeaders.DLT_ORIGINAL_OFFSET);

    if (header == null ||
            header.value() == null ||
            header.value().length != Long.BYTES) {
        return null;
    }

    return ByteBuffer.wrap(header.value()).getLong();
}
~~~

This example assumes the original offset is encoded as an 8-byte `long` in the header protocol's byte order for that version. Verify the encoding before feeding this number into reconciliation systems, especially if custom serializers or recoverers are used.

### 5.3. Should you use @Header?

You can declare `@Header` parameters when Spring Messaging supports converting the corresponding header:

~~~java
@DltHandler
public void onDlt(
        OrderEvent event,
        @Header(
                name = KafkaHeaders.DLT_ORIGINAL_TOPIC,
                required = false)
        String originalTopic) {

    dltAuditService.persistEvent(event, originalTopic);
}
~~~

In some configurations, headers remain `byte[]` and conversion to `String` depends on the message converter. For critical DLTs, use reading logic tested on the real system and always handle missing or malformed headers.

## 6. Configuring DLT policy

`@RetryableTopic` allows tuning the strategy for handling failures in the DLT. Options in `DltStrategy` provided by Spring Kafka in supported versions typically include:

| Strategy | Operational meaning | Things to note |
|---|---|---|
| `ALWAYS_RETRY_ON_ERROR` | Can republish the record back to the DLT when DLT processing fails | Risk of DLT loops and load spikes if handler keeps failing |
| `FAIL_ON_ERROR` | Does not use the DLT republishing strategy above when the handler fails | Must check how the container handles errors and offsets to avoid dropping records |
| `NO_DLT` | Does not configure a DLT for the topology | No DLT endpoint to attach a DltHandler to in that flow |

Example selecting a strategy per operational needs:

~~~java
@RetryableTopic(
        attempts = "3",
        dltStrategy = DltStrategy.FAIL_ON_ERROR,
        dltTopicSuffix = "-dlt")
@KafkaListener(
        topics = "orders.events",
        groupId = "billing")
public void listen(OrderEvent event) {
    billingService.processIdempotently(event);
}
~~~

Default strategies and behavior on fatal exceptions can vary across versions. In newer Spring Kafka releases, certain exceptions classified as fatal might not be republished to the DLT even when using an auto-retry DLT strategy. Verify against your running version.

**Important:** `FAIL_ON_ERROR` does not automatically mean the record is permanently skipped or the container stops completely. Actual behavior depends on the error handler, acknowledgements, DLT configuration, and version. Test the error path before deploying to production.

## 7. What happens when DltHandler throws an exception?

`DltHandler` is itself a listener, so it can fail while writing to an audit database, calling a ticketing system, or sending a notification. If an exception is thrown, the DLT handling mechanism applies the configured error policy.

Example:

~~~text
DLT record arrives at DltHandler
         |
         +--- Audit commit succeeded
         |           |
         |           v
         |    Handler returns normally
         |           |
         |           v
         |    DLT offset is handled by container
         |    per ack policy
         |
         +--- Audit database timeout
                     |
                     v
                Exception
                     |
                     v
             DLT error policy
               /         \
       Republish to DLT  Other error handling
       (if configured)   (per strategy/version)
~~~

If defaults or configuration allow republishing back to the DLT itself, a persistent bug inside `DltHandler` can cause the same event to be re-emitted repeatedly. This creates extra DLT records and can rapidly drive up retention usage, lag, storage, and alerts.

To reduce risk:

- Keep `DltHandler` simple, brief, and idempotent.
- Avoid calling many complex dependencies inside `DltHandler` unless necessary.
- Configure explicit timeouts and retry limits on dependencies.
- Use a unique event ID or source identity to write audits once.
- Alert when the DLT handler throws exceptions repeatedly.
- Provide a manual recovery path if the audit/ticketing system is down.

## 8. What should DltHandler do?

A `DltHandler` can perform several tasks, though it should separate **safe recording** from **complex business recovery**.

### 8.1. Recording failed records

Audit records may include:

- Event ID and business key.
- Original topic/partition/offset.
- DLT topic/partition/offset.
- Exception class and root-cause category.
- Timestamp when the failure was observed.
- Attempt count if relevant metadata is present.
- Current status: `NEW`, `UNDER_REVIEW`, `READY_FOR_REPLAY`, `REPLAYED`, or `IGNORED_WITH_REASON`.
- Assignee or ticket link.

Do not stuff unbounded full stack traces into a short column or metric tag; store the full trace in a secured log store and link it via correlation ID.

### 8.2. Sending rate-limited alerts

`DltHandler` can emit an alert event or create a ticket. However, if every DLT record sends an email or pager alert, a schema bug across thousands of records can flood alerting channels.

Group alerts by:

- Service and listener.
- Exception class.
- Source topic.
- Time window.
- Business event severity.

For instance, sending one alert for "1,200 events in orders.events failed validation in 5 minutes" is far more actionable than 1,200 separate pages.

### 8.3. Routing to a review workflow

A common pattern:

1. `DltHandler` saves metadata with status `NEW`.
2. An internal job or dashboard lists records needing attention.
3. Operators investigate and classify the root cause.
4. If recoverable, record a `READY_FOR_REPLAY` decision.
5. An independent replay tool performs controlled replay.
6. The system reconciles outcomes and marks `REPLAYED`.

This design keeps `DltHandler` lightweight and avoids tangling incident handling with core business logic.

## 9. What should DltHandler NOT do?

### 9.1. Do not auto-replay infinitely

If the handler immediately republishes every incoming DLT record back to the main topic, an unchanged bad record can loop forever:

~~~text
Main topic -> retry -> DLT -> main topic -> retry -> DLT ...
~~~

Loops waste resources, inflate record counts, and can obscure the root cause. Only replay with evidence that data, code, or dependencies were fixed, with attempt caps and a controlled workflow.

### 9.2. Do not ack before durably persisting recovery state

If the design requires `DltHandler` to write an audit record to a database, the listener should return normally only after the database transaction commits. Merely submitting a task to an executor and returning can advance the DLT offset before the audit task runs.

Never treat "called `log.info`" as a durable transaction. Log shipping can fail or log retention may not satisfy data retention policies.

### 9.3. Do not mutate business outcomes arbitrarily

A record entering the DLT may already have executed partial side effects before failing. If `DltHandler` tries to "heal" it by firing compensating actions or retrying API calls without reconciliation, side effects can be duplicated.

For finance, payments, or inventory, inspect business state, idempotency keys, and reconciliation checks before repeating operations.

## 10. Designing idempotency for DltHandler

Kafka and DLTs normally run with at-least-once semantics. A DLT record can be redelivered after the handler wrote an audit yet before the offset committed; the DLT can also receive multiple copies of the same event if publishing/recovery ran more than once.

Therefore, `DltHandler` needs an idempotency key.

### 10.1. Using event ID

If producers attach a stable event ID, combine the event ID with consumer role or business operation as the key:

~~~sql
CREATE TABLE dlt_cases (
    event_id VARCHAR(120) NOT NULL,
    consumer_group VARCHAR(120) NOT NULL,
    original_topic VARCHAR(255),
    original_partition INTEGER,
    original_offset BIGINT,
    exception_class VARCHAR(255),
    status VARCHAR(40) NOT NULL,
    first_seen_at TIMESTAMP NOT NULL,
    last_seen_at TIMESTAMP NOT NULL,
    PRIMARY KEY (event_id, consumer_group)
);
~~~

This key makes sense when each event needs one DLT case per consumer group. If the same event can appear on multiple topics or independent business flows, extend the composite key to match the actual contract.

Do not key on **DLT offset** if the goal is deduplicating the same event republished multiple times: republished copies can receive different DLT offsets.

### 10.2. What if there is no event ID?

You can use a business-appropriate identity tuple, such as original topic + partition + offset **and** consumer group, provided source metadata is reliable and unique within the tracked scope.

However, in some replay or data-copy flows, source identity can change. Thus, a producer-generated event ID preserved across retries and DLTs is usually easier to manage.

## 11. Offset semantics in the DLT

Distinguish two offset groups:

1. **Source offset**: the record's position in the main topic or the topic where failure occurred.
2. **DLT offset**: the record's position after being published to the DLT.

A record might look like:

~~~text
Topic: orders.events, partition 2, offset 847
                    |
                    v
Retry topic: orders.events-retry-..., offset 58
                    |
                    v
DLT topic: orders.events-dlt, partition 2, offset 310
~~~

These offsets are examples; Kafka does not maintain identical offset numbers across topics. `DltHandler` is invoked with the DLT record, so `record.offset()` in this example will be 310, not 847.

Committing the DLT offset only confirms **consumption progress on the DLT** per container/ack policy. It does not "roll back" the consumer group's committed offset on the main topic. To re-run business processing, you normally must publish a new record to the proper topic or use a controlled replay workflow.

### 11.1. Avoid mistaking DLT consumption for deleting data

Kafka does not delete a record when a consumer commits an offset. DLT data stays until retention/compaction policies apply. However, the DLT consumer group will not re-read that record from its current offset.

Therefore, if `DltHandler` only logs and returns normally, the record may stay in Kafka yet never be read again by the DLT consumer on future polls. For long-term handling, maintain storage/indexing or a DLT retrieval workflow independent of committed offsets.

## 12. Serializers and deserializers when consuming the DLT

A DLT record may carry a payload that can no longer deserialize into a normal domain object. Specifically, the original error may have happened **before the main listener ran**, such as:

- Bytes invalid for JSON/Avro/Protobuf.
- Payload incompatible with the schema.
- Invalid type header or class mapping.
- Converter unable to instantiate the Java object.

If `DltHandler` declares `ConsumerRecord<String, OrderEvent>`, yet the DLT consumer cannot deserialize the value into `OrderEvent`, the handler may never receive the record. Instead, the DLT consumer hits a deserialization error of its own.

### 12.1. ErrorHandlingDeserializer

Spring Kafka provides `ErrorHandlingDeserializer` to handle errors at the deserializer layer and pass error details to recovery. Delegate serializer/deserializer configuration and the DLT publisher must support failing payload types.

Some DLT records may hold raw bytes instead of domain objects when the original failure was deserialization. Hence, never assume every DLT record shares the same payload type.

### 12.2. When raw bytes must be preserved

If an environment frequently receives schema-breaking payloads, build a dedicated DLT consumer or handler accepting `byte[]`, then store the raw payload (with security controls), schema metadata, and exception. Keep topics, converters, and serializers consistent.

Do not try to force an invalid payload into a domain object via endless retries. Preserve evidence and fix the producer/schema/consumer before replaying.

## 13. DLT data security

DLTs often hold hard-to-process failed records, which may include sensitive data, identifying keys, exception messages, and stack traces. Therefore:

- Grant DLT read permissions only to authorized services and personnel.
- Restrict publish or replay permissions.
- Do not log payloads containing sensitive information.
- Encrypt and apply retention per data policy.
- Avoid putting personal data into metric labels.
- Check whether stack traces expose secrets, internal URLs, or tokens.
- Log audits whenever a person executes a replay or marks a record ignored.

If data is restricted from leaving certain security zones, the DLT and audit/ticketing systems must obey the same data boundaries.

## 14. Configuring a DLT handler not to auto-start

Some systems want automatic publishing to the DLT while **not consuming the DLT immediately**, because records require operational review first. Supported Spring Kafka versions provide properties such as `autoStartDltHandler` on `@RetryableTopic` to control starting the DLT listener.

Example:

~~~java
@RetryableTopic(
        attempts = "4",
        autoStartDltHandler = "false")
@KafkaListener(
        topics = "orders.events",
        groupId = "billing")
public void handle(OrderEvent event) {
    billingService.processIdempotently(event);
}
~~~

In this style of configuration, the DLT remains the publish destination if the topology creates a DLT, yet the DLT endpoint does not consume automatically until started via proper lifecycle management.

Property names, string/boolean values, endpoint control methods, and support scope depend on Spring Kafka version. When applying this, verify the actual listener container registry rather than relying solely on annotations.

### 14.1. Consequences of not running a DLT consumer

- DLT backlog will grow as new records arrive.
- DLT consumer lag is not always an outage; it can reflect a review policy.
- Monitor record age and time remaining before retention deletes data.
- Maintain active tooling or schedules to process the DLT.
- Do not confuse "DLT handler not running" with "DLT publisher failed".

## 15. Does the DLT need the same partition count as the main topic?

When publishing to the DLT, the recoverer may attempt to preserve the source partition if topology and configuration support it. To do so, the DLT usually needs matching partitions. If the DLT has fewer partitions or incompatible naming, publishing may fail.

Some recoverer settings allow returning an unspecified partition so the producer picks a substitute partition. This makes publishing more flexible, though it can alter partition-level traceability.

Before production, verify:

1. DLT topic exists or has controlled provisioning.
2. DLT has enough partitions for the routing strategy.
3. Replication factor and `min.insync.replicas` match durability requirements.
4. Producer publishing to the DLT has proper ACLs and serializers.
5. DLT retention is long enough for the remediation workflow.
6. Alerts exist for DLT publish failures.

Do not blindly increase DLT partitions without considering consistency with routing and replay workflows.

## 16. What does recovery success mean?

Define the word "success" precisely in your system:

- **Published to DLT:** Record was confirmed by the DLT broker per producer config.
- **Consumed in DLT:** DLT listener received the record.
- **Audit recorded:** `DltHandler` persisted a durable record.
- **Investigated:** Human/software classified the root cause.
- **Replayed:** Record was republished per recovery decision.
- **Business completed:** Final side effect succeeded and was reconciled.

These states are not synonymous. A `DltHandler` returning normally may only prove "audit recorded", not that the event succeeded at the business layer.

Represent these states distinctly in databases or dashboards. Never use a single `success = true` field without specifying which step succeeded.

## 17. Replaying from the DLT

Replay is the process of reprocessing records moved to the DLT, usually after the failure cause is fixed.

Reference workflow:

1. Identify event, source topic, exception, and business state.
2. Check whether the record already produced partial side effects.
3. Confirm the code/schema/dependency fix is deployed.
4. Select the set of records to replay and enforce rate limits.
5. Preserve the original event ID and correlation ID.
6. Publish to the designed topic or recovery workflow.
7. Monitor for new retries or DLT re-entries.
8. Reconcile business outcomes.
9. Audit the person or automation that authorized the replay.

### 17.1. Do not replay every record verbatim

A schema-broken record may need transformation into the new schema. A payment event with an uncertain outcome may need reconciliation before calling the API again. An event already handled successfully via another path should be marked complete rather than blindly re-sent.

Uncontrolled replay can reproduce errors, break business ordering, or duplicate side effects.

### 17.2. Replay metadata

When replaying, you can attach metadata:

- Original event ID.
- Replay request ID.
- Replay timestamp.
- DLT source and replay reason.
- Code/schema version after the fix.
- Approving person or automation.

Old DLT headers from prior failures should not automatically be carried verbatim as the "current cause". Separate **origin** metadata from **new-attempt** metadata to avoid confusion if the record fails again.

## 18. Metrics and alerts for DltHandler

A recovery dashboard should not merely count DLT records. You need visibility into which steps records pass through and where they stall.

| Metric | Meaning |
|---|---|
| DLT incoming rate | Rate of new records entering the DLT |
| DLT consumer lag | DLT records not yet consumed by the listener |
| DltHandler processing duration | Time taken to process one DLT record |
| DltHandler failure rate | Failure rate of the handler |
| DLT republish rate | Sign of handler errors republishing inside the DLT |
| Recovery case backlog | Cases not yet investigated or replayed |
| Oldest unresolved case age | Age of the oldest unresolved case |
| DLT publish failure count | Failures moving records from retries to DLT |
| Replay success/failure | Outcome of the replay workflow |

### 18.1. Suggested alerts

- New records enter the DLT for critical business flows.
- DLT incoming rate spikes abnormally above baseline.
- `DltHandler` failure rate rises after a deployment.
- DLT repeatedly republishes the same event ID.
- Unresolved recovery cases breach SLA.
- Remaining DLT retention is shorter than investigation needs.
- Replays fail or continuously create new DLT entries.

Not every DLT record requires an immediate page. Define severity by topic, exception group, record age, and business impact. A single validation error might open a ticket; mass DLT failures or inability to store records can be a critical incident.

### 18.2. Cardinality

Appropriate metric tags usually include service, bounded topic set, grouped exception class, and recovery status. Do not put offset, event ID, customer ID, order ID, or raw exception messages into tags.

Use structured logging and traces to locate individual records; use metrics to observe trends.

## 19. Runbook: DLT has data yet DltHandler is not running

1. Confirm records were actually published to the expected DLT.
2. Check whether the DLT endpoint is managed by retry-topic infrastructure.
3. Check `autoStartDltHandler` or lifecycle settings to see if the DLT listener was intentionally stopped.
4. Verify the right class and method have `@DltHandler`.
5. Check consumer group, subscription, and partition assignment.
6. Check whether serializer/deserializer or message converter errors occur before the method runs.
7. Check consumer lag and DLT container logs.
8. If the DLT consumer is intentionally disabled by policy, confirm an alternate owner and handling schedule exist.

Never bulk-restart DLT listeners in production without first verifying whether they were deliberately disabled.

## 20. Runbook: DltHandler processes the same record repeatedly

1. Search logs by event ID and source identity.
2. Check whether the same DLT offset is redelivered or multiple DLT records exist with different offsets.
3. If same offset, inspect committed offsets, restarts, and error handling.
4. If multiple offsets, inspect the DLT republish strategy and `DltHandler` exceptions.
5. Check whether the audit database has unique constraints and idempotency.
6. Check downstream timeouts, as operations may have succeeded before the handler reported failure.
7. Adjust DLT strategy and timeouts under change control.
8. Reconcile real case counts against DLT record counts instead of assuming they always match.

If `DltHandler` errors cause repeated republishing to the DLT, fix the root cause and bound loops. Simply extending retention will not cure the issue.

## 21. Runbook: Malformed schema record breaks the DLT too

1. Identify whether the first exception was deserialization, conversion, or validation.
2. Check whether bytes/headers were published to the DLT.
3. Check whether the DLT producer's serializer accepts failing payloads.
4. Check whether the DLT consumer uses a domain-object deserializer or raw bytes.
5. Choose a compatible reader to retain data without failing conversion again.
6. Verify access control, retention, and masking for raw payloads.
7. Fix schema/consumer, test a representative record, and run controlled replay.

A DLT holding undeserializable records will not naturally work if the consumer only accepts `OrderEvent`. Recovery design must accommodate corrupted data.

## 22. Runbook: DLT publish fails

This occurs **before** `DltHandler` receives the record.

1. Check producer errors when publishing to the DLT.
2. Verify the DLT topic exists, leader/ISR are healthy, and partition routing is valid.
3. Check ACLs, bootstrap servers, serializers, and message size.
4. Check producer timeouts, retries, and `acks` configuration.
5. Verify the recoverer/error handler does not treat recovery as succeeded when publish fails.
6. Determine whether the source topic offset was committed.
7. After fixing the cause, verify the record is reprocessed or arrives in the DLT.

Do not increase `DltHandler` concurrency to fix DLT publish errors; the handler never received the record. Investigate the producer/recoverer side.

## 23. Integration testing DltHandler

A good test suite must verify both happy paths and failure paths at every stage. Use a test Kafka broker or Testcontainers per your project's tooling.

### 23.1. Retryable exception reaching DLT after exhausting attempts

1. Configure `@RetryableTopic(attempts = "3")` with short backoff.
2. Send a record with a stable event ID.
3. Have the listener throw a retryable exception every time.
4. Verify invocation count matches policy.
5. Verify the record lands in the DLT.
6. Verify `DltHandler` is invoked.
7. Verify the audit record saves event ID, source metadata, and exception.

### 23.2. Non-retryable exception

1. Send a record with an invalid business payload.
2. Have the listener throw an exception classified as non-retryable.
3. Verify the record routes to recovery per policy without pointless retries.
4. Verify `DltHandler` records the exact cause.

### 23.3. DltHandler fails and re-runs

1. Force the audit database to return a transient error.
2. Verify `DltHandler` throws an exception.
3. Observe the active `DltStrategy`.
4. Verify DLT republish or error-handling behavior matches config.
5. Restore the database.
6. Verify the audit creates only one case for the same event ID even across multiple deliveries.

### 23.4. Deserialization failure

1. Send a record incompatible with the serializer/schema.
2. Test error handling at the deserialization layer.
3. Verify the recoverer sends the payload in a format the DLT can store.
4. Verify the handler or DLT consumer can receive/record the raw record.

### 23.5. Idempotent replay

1. Process an event successfully in the database yet simulate a crash before offset commit.
2. Route the event through recovery/replay per test scenario.
3. Verify the event ID stays intact.
4. Verify business side effects are not executed twice.
5. Verify the DLT case transitions to the right state.

Tests should measure **actual committed offsets, receiving topics, handler invocation counts, and database state**. Checking only a `"DLT received"` log line is insufficient to guarantee reliable recovery.

## 24. Common implementation mistakes

**Confusing @DltHandler with the recoverer.** The handler is not responsible for initially publishing the record to the DLT; the recoverer or retry-topic infrastructure performs that step.

**Assuming a record entering the DLT is business-processed.** The record was only saved or routed for investigation; side effects may remain incomplete.

**DltHandler only logs and treats recovery as done.** For workflows needing audits/tickets, persist durable state before returning normally.

**Replaying directly inside DltHandler.** This can create infinite loops and break business ordering. Keep replay separate.

**Ignoring DltHandler exceptions.** An audit failure can cause continuous DLT republishing or stalling depending on strategy.

**Not distinguishing DLT offsets from source offsets.** Reconciliation and replay easily target the wrong record.

**Assuming every DLT value is a domain object.** Deserialization failures can leave records as raw bytes.

**Lacking idempotency.** Redelivered DLT records can create duplicate tickets or side effects.

**Lacking owners and retention policies.** DLT records may expire before being investigated.

**Using exception messages as metric tags.** High cardinality and data-leakage risk.

## 25. Pre-production checklist for DltHandler

### Retry topology

- [ ] `@RetryableTopic` or retry-topic configuration is declared properly.
- [ ] Attempt count, backoff, and exception classification match SLAs.
- [ ] DLT topic, partitions, replication, retention, and ACLs are provisioned properly.
- [ ] DLT publish failures are detected and do not trigger false source acknowledgements.
- [ ] `DltStrategy` is chosen deliberately and tested.

### DltHandler

- [ ] `@DltHandler` method sits in the proper bean/topology.
- [ ] Known whether the DLT endpoint auto-starts or is intentionally stopped.
- [ ] Handler receives payloads or raw bytes cleanly.
- [ ] Origin/exception headers are read safely when missing.
- [ ] Audits are durably persisted before the handler returns normally.
- [ ] Handler is idempotent when DLT records are redelivered.
- [ ] Handler dependencies have explicit timeouts and failure policies.

### Operations and replay

- [ ] Dashboards track DLT rate, lag, handler failures, and recovery backlog.
- [ ] Alerts reflect business criticality.
- [ ] An owner and investigation SLA exist for DLT cases.
- [ ] No infinite replay; approval and rate limiting exist.
- [ ] Replay preserves event IDs and supports outcome reconciliation.
- [ ] Logs/headers/payloads are protected under data policies.

### Testing

- [ ] Tested retries exhausted -> DLT -> DltHandler.
- [ ] Tested non-retryable exceptions.
- [ ] Tested handler failures and DLT republish strategies.
- [ ] Tested deserialization/conversion failures.
- [ ] Tested crashes, redeliveries, duplicates, and idempotency.
- [ ] Tested replay after fixing root cause.

## Conclusion

`@DltHandler` is the processing point for records from a dead-letter topic in Spring Kafka's non-blocking retry mechanism. It runs **after** the DLT publish step, typically to record errors, store audits, and support investigation or replay workflows. A reliable design distinguishes the recoverer from `DltHandler`, parses origin and exception headers safely, defines the DLT strategy when the handler fails, and enforces idempotency and durable state storage. Never treat `DltHandler` having run as proof of business completion. Combined with DLT lifecycle management, monitoring, retention, security, and controlled replay, the system can retain failed records and recover without creating infinite retry loops or losing reconciliation capability.
