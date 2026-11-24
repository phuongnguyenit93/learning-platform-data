# Choosing Filter or Routing Logic

In a Kafka system, not every record received by a consumer needs to enter a business listener. Some records should be skipped because they are out of processing scope, expired, or fail a condition. Other records need to be forwarded to another flow depending on event type, tenant, data region, or business status. These two needs look similar in that both can stop a record from continuing into the current listener, yet they have different purposes and consequences.

Filtering decides whether a record is processed by the current listener or excluded from that listener's flow. Routing decides where a record is sent or which listener/processing branch will receive it. If you use filtering in place of routing, records may be dropped and lost from the business workflow with no downstream receiver. If you use routing when you simply need to discard records, the application may introduce unnecessary topics, producers, and complexity.

In Spring Kafka, RecordFilterStrategy is the record-filtering mechanism at the listener container. RecordInterceptor is a pre-listener hook to observe or transform records, and can skip the listener by returning null. Routing is typically done by choosing the topic directly at the producer, branching inside a listener/router, or using separate listeners per topic. This lesson helps you choose the right mechanism, configure it, and test the behavior of each option.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish filtering, interceptors, and routing.
- Determine when to discard a record and when to route it to another branch.
- Configure RecordFilterStrategy on a listener container factory.
- Understand the meaning of filter boolean return values and how discarded records are handled.
- Choose filters based on payload, headers, key, or Kafka metadata.
- Distinguish record filtering from batch filtering.
- Use RecordInterceptor for cross-cutting logic before the listener.
- Choose routing at the producer, listener, or a dedicated router.
- Preserve keys, partition ordering, and metadata when forwarding records.
- Handle unknown routes, retries, DLTs, and publish failures.
- Avoid using filters as an idempotency or security mechanism.
- Test to guarantee records are neither silently dropped nor processed twice.

## 1. Distinguishing filtering and routing

Filtering answers the question: does this record need to be processed by the current listener?

Routing answers the question: which branch or topic should this record go to?

For example, an orders topic contains these events:

- OrderCreated: handle order creation.
- OrderCancelled: handle order cancellation.
- OrderArchived: move to archive storage.
- InternalHeartbeat: not business data for the listener.

If a listener only cares about OrderCreated and OrderCancelled, it can filter out-of-scope records. But if OrderArchived must be sent to an archive topic, that record must be routed; discarding it would lose the chance to archive it.

| Need | Appropriate mechanism | Result |
|---|---|---|
| Skip records irrelevant to the listener | Filter | Listener is not invoked for the record |
| Forward events by eventType to another topic | Routing | Record is sent to the appropriate destination |
| Select a handler by payload type within the same app | Dispatch/handler selection | An appropriate handler is invoked |
| Log, measure time, add context before the listener | Interceptor | Record is observed or transformed |
| Exclude records due to data errors needing investigation | Reject/quarantine route | Record is saved in an error-handling stream |

A record filtered in one consumer group still exists in Kafka, and other consumer groups can still read it. Filtering does not delete records from the topic and does not affect subscriptions of other services.

## 2. Where filters and routers sit in the Kafka flow

Filtering usually happens on the consumer side, after the Kafka consumer polls records and before the business listener is invoked.

~~~mermaid
flowchart TD
    A["Kafka topic"] --> B["KafkaConsumer.poll()"]
    B --> C["Listener container"]
    C --> D["RecordInterceptor"]
    D --> E["Filtering adapter / RecordFilterStrategy"]
    E -->|Discard| F["Skip listener"]
    E -->|Keep| G["@KafkaListener"]
    G --> H["Business logic"]
    H --> I{"Needs branching?"}
    I -->|Yes| J["Router / KafkaTemplate"]
    I -->|No| K["Complete"]
    J --> L["Destination topic"]
~~~

For record listeners, the container invokes RecordInterceptor before invoking the listener adapter; the adapter may be FilteringMessageListenerAdapter. Thus, the interceptor sits ahead of the filter adapter in this call path. Even so, the two mechanisms have different responsibilities: RecordFilterStrategy decides discards per filtering policy, while RecordInterceptor serves cross-cutting hooks. Do not move the same domain rule into an interceptor just to avoid configuring a filter.

Routing can happen earlier, right at the producer:

~~~text
Producer
   |
   +-- OrderCreated  -> orders.created
   +-- OrderCancelled -> orders.cancelled
   +-- OrderArchived -> orders.archive
~~~

Or routing happens on the consumer after reading a shared topic:

~~~text
orders.events
      |
      v
Order router
      |
      +-- OrderCreated   -> orders.created
      +-- OrderCancelled -> orders.cancelled
      +-- OrderArchived  -> orders.archive
~~~

Choose the routing point based on where enough information exists to decide and who owns topic topology. If the producer already knows the event type and destination, producer-side routing is usually simpler. If the destination depends on data enriched or validated on the consumer, routing after consumption may fit better.

## 3. When should you use a filter?

Use a filter when the record does not need to produce any side effect in the current listener and skipping is an intentional business decision.

Common situations:

- The listener only processes a subset of event types in a shared topic.
- The record has an enabled=false flag and is explicitly outside this processing flow.
- The event has expired and business policy allows skipping it.
- The record is a heartbeat or control event that the business listener ignores.
- A listener only accepts an assigned group of tenants or data types.
- The record is a tombstone that a specific listener does not need to process, after confirming compacted topic semantics.
- A duplicate record has already been confirmed as processed in a durable idempotency store and this listener does not need to repeat side effects.

Before filtering, answer three questions:

1. Does anyone else or any other flow need to process this record?
2. Should the skip reason be saved for auditing or investigation?
3. If the filter condition changes in the future, will old records need to be replayed?

If the answer to the first question is yes, or if the record needs to be fixed and reprocessed, consider routing to another topic instead of discarding.

Do not use filters to hide schema errors, deserialization failures, or business errors needing retry. Records that fail deserialization may not even reach RecordFilterStrategy; those errors belong to the deserialization layer and need ErrorHandlingDeserializer or a suitable error-handling mechanism.

## 4. When should you use routing?

Use routing when the record still has value and must be forwarded to another consumer or destination.

Examples:

- Events by geographic region must go to separate topics.
- Events by business category must be processed by specialized services.
- High-priority events must go to a priority stream.
- Validated events must be forwarded to a downstream topic.
- Invalid events must be quarantined for investigation.
- An input topic contains multiple event types and a router must fan them out.

Routing usually must produce an observable action: publishing the record to a target topic, selecting a handler, or passing into a workflow. Therefore, routing must define destination, key, headers, and the policy when no destination exists.

If no route is found, do not silently drop the record. Explicitly pick one of these behaviors: throw an exception for retry, send to quarantine, record a rejected event, or stop the container depending on severity.

## 5. Configuring RecordFilterStrategy

Spring Kafka provides RecordFilterStrategy to decide whether to exclude a ConsumerRecord. Returning true from filter() means the record is excluded; returning false means it is forwarded to the listener.

Example factory that only accepts active order events:

~~~java
@Bean
public RecordFilterStrategy<String, OrderEvent> inactiveOrderFilter() {
    return record -> {
        OrderEvent event = record.value();

        return event == null || !event.isActive();
    };
}
~~~

Attach the strategy to ConcurrentKafkaListenerContainerFactory:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        ordersListenerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory,
                RecordFilterStrategy<String, OrderEvent> inactiveOrderFilter) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setRecordFilterStrategy(inactiveOrderFilter);

    return factory;
}
~~~

Listener using the factory:

~~~java
@KafkaListener(
    id = "active-orders-listener",
    topics = "orders",
    groupId = "active-orders-service",
    containerFactory = "ordersListenerFactory"
)
public void consume(OrderEvent event) {
    orderService.process(event);
}
~~~

In this example, events with active=false are not passed into consume(). The events remain in the orders topic and other consumer groups are unaffected.

The example also excludes null payloads. Only do this if tombstones carry no business meaning for this listener; in compacted topics, tombstones usually represent key deletions and may need dedicated handling.

Filter and factory bean names should reflect business scope. If multiple listeners have different criteria, create separate strategies/factories so a shared filter does not accidentally drop records needed by another listener.

Since Spring Kafka 2.8.4, you can select a dedicated filter per `@KafkaListener` using the filter attribute with the RecordFilterStrategy bean name. This is useful when endpoints share one factory but have different filtering criteria:

~~~java
@KafkaListener(
    id = "active-orders-listener",
    topics = "orders",
    groupId = "active-orders-service",
    filter = "inactiveOrderFilter"
)
public void consume(OrderEvent event) {
    orderService.process(event);
}
~~~

## 6. Reading metadata when filtering

Filters receive a ConsumerRecord, so they can inspect payload, key, topic, partition, offset, timestamp, and headers.

Example excluding heartbeat events by header:

~~~java
@Bean
public RecordFilterStrategy<String, OrderEvent> heartbeatFilter() {
    return record -> {
        Header header = record.headers().lastHeader("event-kind");

        if (header == null) {
            return false;
        }

        String eventKind = new String(
                header.value(),
                StandardCharsets.UTF_8
        );

        return "heartbeat".equals(eventKind);
    };
}
~~~

The filter only excludes heartbeats. Records missing the header are still passed to the listener so the listener or validator decides how to handle them. If a missing header is a data contract error, route to quarantine or throw an exception instead of automatically discarding.

Do not read headers assuming they always exist. Kafka headers may be missing, duplicated by name, or contain invalid bytes. If multiple headers share the same name, choosing lastHeader() or iterating all must follow the producer contract.

You can use topic or key in filters:

~~~java
@Bean
public RecordFilterStrategy<String, OrderEvent> topicScopeFilter() {
    return record ->
            !"orders".equals(record.topic())
                    || record.key() == null
                    || record.key().trim().isEmpty();
}
~~~

This example excludes records outside the orders topic or missing a key. Apply this only if a key is mandatory in the topic contract. If a null key has valid meaning, this filter would drop records.

## 7. Handling discarded records and offsets

Filtering excludes records from listener invocation. The consumer still polled those records, so the application must understand how offsets are acknowledged per AckMode and container configuration.

Spring Kafka provides ackDiscarded on the listener container factory. The default value is false. When set to true, the filtering adapter acknowledges discarded records; actual commit timing still follows AckMode, transactions, and container commit mechanisms:

~~~java
factory.setAckDiscarded(true);
~~~

AckMode, auto commit, and transactions affect when offsets are committed. Do not enable ackDiscarded without understanding its impact on retries and redelivery. If left false, the adapter does not proactively acknowledge discarded records; test offset behavior under your active AckMode, especially after restarts or rebalances.

Operational principles:

- Explicitly define the listener's AckMode.
- Verify ackDiscarded behavior for your Spring Kafka version.
- Test restart/rebalance after filters discard records.
- Do not treat discarding as a successful business execution if the record requires auditing.
- If rejection reasons must be saved, route or durably record them before acknowledging offsets.

Filtering does not invoke the listener, so logic inside the listener such as business metrics, auditing, or outbox writes will not run. If skipped records must be recorded, use appropriate metrics/filter observability or choose a reject route.

## 8. Filtering for batch listeners

When the container runs in batch mode, the listener receives multiple records in one invocation. RecordFilterStrategy supports filterBatch() to decide which records remain after filtering.

Example keeping only active events:

~~~java
@Bean
public RecordFilterStrategy<String, OrderEvent> activeOrderBatchFilter() {
    return new RecordFilterStrategy<>() {

        @Override
        public boolean filter(
                ConsumerRecord<String, OrderEvent> record) {
            return record.value() == null || !record.value().isActive();
        }

        @Override
        public List<ConsumerRecord<String, OrderEvent>> filterBatch(
                List<ConsumerRecord<String, OrderEvent>> records) {

            return records.stream()
                    .filter(record -> !filter(record))
                    .collect(Collectors.toList());
        }
    };
}
~~~

Attach the strategy to a batch factory:

~~~java
factory.setBatchListener(true);
factory.setRecordFilterStrategy(activeOrderBatchFilter);
~~~

Listener receiving the filtered list:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "active-orders-batch",
    containerFactory = "ordersBatchListenerFactory"
)
public void consumeBatch(List<OrderEvent> events) {
    orderService.processBatch(events);
}
~~~

Batch filters should preserve the relative order of remaining records. If business logic needs per-record metadata, accept `List<ConsumerRecord<K,V>>` or appropriate batch headers rather than only a payload List. FilteringBatchMessageListenerAdapter does not apply to listeners accepting `ConsumerRecords<?, ?>` because that type is immutable; to filter batches, use `List<ConsumerRecord<K,V>>` or a payload List.

Since Spring Kafka 3.3, RecordFilterStrategy has ignoreEmptyBatch(). Defaulting to false means the listener is still invoked with an empty batch if all records are filtered out. If returning true, the listener is not invoked when the batch is empty, though the container still commits per its mechanism. Versions older than 3.3 lack this option; verify the corresponding behavior of the running version.

## 9. How do filters and RecordInterceptor differ?

Since Spring Kafka 2.2.7, RecordInterceptor is a hook running before a record is passed to a record listener. It suits cross-cutting logic such as logging, tracing, timing, context checking, or common record transformations.

Example interceptor attaching log context based on topic and key:

~~~java
@Bean
public RecordInterceptor<String, OrderEvent> orderRecordInterceptor() {
    return (record, consumer) -> {
        log.debug(
                "Before listener: topic={}, partition={}, offset={}, key={}",
                record.topic(),
                record.partition(),
                record.offset(),
                record.key()
        );

        return record;
    };
}
~~~

Attach to the factory:

~~~java
factory.setRecordInterceptor(orderRecordInterceptor);
~~~

RecordInterceptor can return a transformed ConsumerRecord or return null to skip the listener. Returning null does not go through RecordFilterStrategy's ackDiscarded mechanism; offset behavior must be tested carefully and can cause lag if skipped records are not acknowledged as intended. Therefore, if the goal is filtering by a business condition, RecordFilterStrategy expresses intent more clearly and has its own ackDiscarded mechanism.

If an interceptor creates a new ConsumerRecord, preserve the original record's topic, partition, and offset to avoid altering the position managed by the container. Do not call seek(), commitSync(), or operations changing consumer position/offsets from an interceptor; the container must manage progress.

Do not use interceptors for heavy business work, synchronous HTTP calls, or per-record database writes. Interceptors run on the consumer processing path and can increase poll processing time, affecting max.poll.interval.ms and consumer lag.

### BatchInterceptor

RecordInterceptor only applies to record listeners. Since Spring Kafka 2.7, Spring Kafka provides BatchInterceptor to observe or transform an entire batch before the listener runs. Do not use RecordInterceptor for a batch if signatures and container modes are incompatible.

If you only need to exclude certain records from a batch, use batch filtering. If you need tracing or shared context for a batch, consider BatchInterceptor.

## 10. Kafka client ConsumerInterceptor vs Spring RecordInterceptor

These two interceptor types have similar names but sit at two different layers:

| Type | API | Location | Scope |
|---|---|---|---|
| Kafka ConsumerInterceptor | org.apache.kafka.clients.consumer.ConsumerInterceptor | Inside KafkaConsumer, around poll | Kafka client level |
| Spring RecordInterceptor | org.springframework.kafka.listener.RecordInterceptor | Before listener invocation | Listener container level |
| Spring BatchInterceptor | org.springframework.kafka.listener.BatchInterceptor | Before batch listener | Batch listener container level |

Kafka ConsumerInterceptor is configured via the consumer property interceptor.classes. It operates at the Kafka client layer and can affect every listener using that consumer factory. The interceptor can observe or modify the ConsumerRecords returned from poll, yet altering the record set at the client layer has its own implications for offset progress; do not use it as a simple domain filter. If you only want to filter for a specific Spring endpoint, RecordFilterStrategy is usually clearer and easier to manage.

Spring RecordInterceptor attaches to the container factory, so it can be configured differently per listener. Pick the API at the right layer instead of creating a global ConsumerInterceptor to enforce business rules specific to one listener.

## 11. Routing at the producer

If the producer knows the event type and destination when creating the event, route at the producer. This lets consumers subscribe only to the topics they actually need to process.

Example:

~~~java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public void publish(OrderEvent event) throws Exception {
        String destination;
        switch (event.getType()) {
            case CREATED:
                destination = "orders.created";
                break;
            case CANCELLED:
                destination = "orders.cancelled";
                break;
            case ARCHIVED:
                destination = "orders.archive";
                break;
            default:
                throw new IllegalArgumentException(
                        "Unsupported order event type: " + event.getType()
                );
        }

        kafkaTemplate.send(
                destination,
                event.getOrderId(),
                event
        ).get(10, TimeUnit.SECONDS);
    }
}
~~~

The producer selects the topic before publishing. The key is orderId so events for the same order can land in the same partition within each topic, depending on the partitioner and partition count.

The producer also needs to observe the send future result and handle publish failures per the application contract. Picking the right topic does not guarantee the broker confirmed writing the record successfully.

Producer-side routing fits when:

- Event type is known at the source.
- The producer owns the destination contract.
- You want to reduce the number of consumers reading a shared topic.
- You want each downstream service to have its own topic and ACLs.

If multiple producers repeat the same routing rule, place the rule in a shared component or standardize the topic contract. Do not let each producer name topics differently.

## 12. Routing in the consumer with KafkaTemplate

Sometimes the producer cannot decide the destination because routing depends on data enriched or validated at the consumer. In that case, the listener can invoke a router and publish to the target topic.

Example:

~~~java
@Component
public class OrderEventRouter {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public void route(OrderEvent event) throws Exception {
        String destination;
        switch (event.getRegion()) {
            case "VN":
                destination = "orders.vn";
                break;
            case "SG":
                destination = "orders.sg";
                break;
            case "TH":
                destination = "orders.th";
                break;
            default:
                throw new UnsupportedOrderRegionException(event.getRegion());
        }

        kafkaTemplate.send(
                destination,
                event.getOrderId(),
                event
        ).get(10, TimeUnit.SECONDS);
    }
}
~~~

Listener:

~~~java
@KafkaListener(
    topics = "orders.events",
    groupId = "orders-router"
)
public void consume(OrderEvent event) throws Exception {
    orderEventRouter.route(event);
}
~~~

In this example, routing is not done by discarding records. The router waits up to 10 seconds for the send result; if publishing fails or times out, the exception propagates to the listener so the error handler handles it per retry/DLT policy. Synchronous waiting holds the consumer thread during the send; choose an appropriate timeout and consider Kafka transactions if publishing must be coordinated with source offsets.

If destination publishing fails, the listener must not return normally and commit the source offset. Handle the send future and acknowledge the source record only after publishing is confirmed according to the reliability policy.

## 13. Ensuring reliable consume-and-route

When a consumer reads a source and publishes to another topic, there are two independent operations:

1. Reading and acknowledging the source offset.
2. Publishing the record to the destination.

If publishing succeeds but committing the source offset fails, the record may be re-read and published again. If the source offset commits before publishing succeeds, the record may be lost from the target stream.

Options:

- Use a Kafka transaction to combine output publishing and input offset commit in a single Kafka transaction when configuring the listener container and KafkaTemplate with a matching transaction manager.
- Use idempotency on the target consumer to tolerate duplicates.
- Use an outbox if the routing decision depends on database changes and must coordinate the database with Kafka.
- Persistently record routing state so recovery is possible after failures.

With a transactional listener container, Spring Kafka can start a Kafka transaction per record or batch; KafkaTemplate using the same transactional ProducerFactory sends output within that transaction. When the listener completes, the input offset is sent into the transaction. If the transaction aborts, output is not committed and the offset is not confirmed in that transaction.

Kafka transactions do not automatically encompass ordinary database transactions. If a listener both writes to a database and publishes to Kafka, an outbox or suitable coordination mechanism is required to avoid state divergence between the two systems.

## 14. Choosing keys and preserving ordering when routing

Routing to another topic can alter partition mapping. Kafka only guarantees ordering within a single partition of a single topic, not global ordering across topics.

If orderId is the source record's key, preserve that key when routing if events for the same order should continue landing in the same partition at the destination:

~~~java
        kafkaTemplate.send(
                destination,
                record.key(),
                routedEvent
        );
~~~

However, keeping the same key does not guarantee the same partition number as the source if partition counts or partitioners differ. If strict ordering is required by the business, explicitly ensure:

- All events of an aggregate share the same key.
- The destination topic has compatible partitioning.
- The router does not publish asynchronously with differing completion orders.
- The target consumer processes sequentially per partition.
- A version/sequence guard exists in case events can arrive late.

Do not route events of the same aggregate to multiple topics and assume consumers will see a single global order across topics.

## 15. Route by topic or dispatch by payload?

A single topic can contain multiple event types. Two common organization patterns exist:

**One topic for multiple event types:** consumers read a shared topic and dispatch by eventType or payload type. This reduces topic count, but listeners must understand multiple event types and manage a shared schema.

**Separate topics per event type:** producers route events into the appropriate topic. Consumers subscribe to the exact topic, simplifying access control and ownership, though increasing topic count and configuration.

You can use multiple methods in one listener class with @KafkaHandler so Spring Kafka dispatches by payload type when a class has @KafkaListener at the class level:

~~~java
@Component
@KafkaListener(
    id = "order-events",
    topics = "orders.events",
    groupId = "order-event-handlers"
)
public class OrderEventHandlers {

    @KafkaHandler
    public void onCreated(OrderCreated event) {
        orderService.create(event);
    }

    @KafkaHandler
    public void onCancelled(OrderCancelled event) {
        orderService.cancel(event);
    }

    @KafkaHandler(isDefault = true)
    public void onUnknown(Object event) {
        log.warn("Unsupported event type: {}", event.getClass().getName());
    }
}
~~~

This dispatches to methods within the same listener endpoint, not publishing to another topic. If you need to route to a destination topic, use a router/KafkaTemplate or decide the topic at the producer.

With JSON, type-based dispatching requires proper type mapping/deserializer configuration. Do not let arbitrary class names from headers control type resolution if the message source is untrusted.

## 16. Unknown routes and rejected events

A router must define behavior when no destination is found. Three common policies exist:

| Policy | When appropriate | Consequence |
|---|---|---|
| Throw exception | Missing route is a configuration error or fixable data issue | Retries then DLT per error handler |
| Quarantine/rejected topic | Event needs investigation or later repair | Record is kept for operations |
| Discard | Event is explicitly determined not to need processing | No downstream flow |

Do not use an arbitrary default route like "send every unknown route to orders.created". That can send wrong event types into inappropriate business logic.

Destinations should be validated against an allowlist:

~~~java
private static final Map<String, String> DESTINATIONS = createDestinations();

private static Map<String, String> createDestinations() {
    Map<String, String> destinations = new HashMap<>();
    destinations.put("VN", "orders.vn");
    destinations.put("SG", "orders.sg");
    destinations.put("TH", "orders.th");
    return Collections.unmodifiableMap(destinations);
}

private String destinationFor(String region) {
    String destination = DESTINATIONS.get(region);

    if (destination == null) {
        throw new UnsupportedOrderRegionException(region);
    }

    return destination;
}
~~~

An allowlist restricts the topics a router can publish to. Do not construct topic names directly from user data or unverified headers.

## 17. Do not use filters as idempotency

A filter can check whether eventId already exists in a database and discard duplicates. However, this is usually not the right place to guarantee idempotency.

If a filter marks an event as processed before the listener executes business logic, a failure between the two steps can cause the record to be discarded on redelivery even though side effects never completed. If the filter only checks and the listener processes, two concurrent consumers can both pass the check.

Idempotency should be enforced at the business boundary using transactions and a unique constraint/inbox:

~~~java
@Transactional
public void process(OrderEvent event) {
    if (inboxRepository.existsByEventId(event.getEventId())) {
        return;
    }

    orderService.apply(event);
    inboxRepository.save(new InboxEntry(event.getEventId()));
}
~~~

In production, you need a unique constraint on eventId and conflict handling when two deliveries of the same event run concurrently. Check and write the inbox entry within the same transaction as the database side effect.

Filters can exclude records definitely outside the listener's scope, while idempotency protects business execution against duplicate delivery.

## 18. Do not use filters in place of security

Filtering is not an authorization mechanism. Filtered records are simply not processed by the current listener; they remain in Kafka and can be read by another consumer group.

If a service is not permitted to read a topic, use Kafka ACLs and proper identities. If a tenant is not permitted to access data, check authorization in the service and protect data before publishing.

Do not rely on tenant-based filtering to protect sensitive data if the service still has permission to read the entire topic. Filters can have bugs, be misconfigured, or be absent on another listener.

## 19. Do retry and DLT apply to filtered records?

Filtered records do not cause the listener to throw an exception. Therefore, they do not automatically flow through retry/DLT like a normal listener processing failure.

If a record is discarded by a business condition yet needs investigation, route it to a rejected/quarantine topic instead of filtering. If a filter skips a record due to a transient condition, such as reference data not being ready yet, filtering can forfeit the chance to retry. When retries are needed, let the listener process it and throw an appropriate exception or use retry topics.

Distinction:

- Filter: record does not need listener processing.
- Exception: listener attempted processing and failed.
- Reject route: record is rejected but still needs to be saved.
- Retry: record needs to be retried after a delay.

Do not use filters to bypass a deserialization or validation error. Those errors require error handling at their respective layers.

## 20. Observing filtering and routing in production

Filtering can make the number of records received by the listener lower than the number polled by the consumer. Observe excluded record counts to detect overly broad filters or input data changes.

Suggested metrics:

| Metric | Meaning |
|---|---|
| records_polled_total | Number of records polled by the consumer |
| records_filtered_total | Number of records excluded by filters |
| records_listener_invoked_total | Number of records forwarded to the listener |
| records_routed_total | Number of records published to a destination |
| route_unknown_total | Number of records where no route was found |
| route_publish_failure_total | Number of failed destination publishes |
| rejected_records_total | Number of records sent to reject/quarantine |
| filter_rate_by_reason | Filter rate by reason |
| listener_processing_latency | Listener processing duration |

Include the following fields in logs:

- eventId.
- topic, partition, offset.
- key.
- filter reason or route decision.
- destination topic.
- correlation/trace ID.
- exception type if routing/publishing failed.

Do not log full sensitive payloads. Record stable reason codes such as OUT_OF_SCOPE, EXPIRED, or INTERNAL_EVENT so dashboards and alerts do not depend on message contents.

If the filter rate spikes suddenly, inspect producer version, schema, header mappings, and filter predicates. If route failures increase, inspect topic metadata, ACLs, serializers, brokers, and producer send results.

## 21. Testing filtering and routing

Tests must verify retained records, filtered records, and routed records.

Important scenarios:

1. Filter returns false: listener is invoked.
2. Filter returns true: listener is not invoked.
3. Record missing optional header: behavior matches defined policy.
4. Tombstone/null payload: not mistakenly excluded if a compacted topic needs tombstone handling.
5. Filtering by key: null or blank keys have clear behavior.
6. Batch filter: only qualifying records remain in the batch.
7. Empty batch after filter: verify listener behavior per Spring Kafka version.
8. ackDiscarded and AckMode: offsets are properly acknowledged after restart/rebalance.
9. RecordInterceptor: records are properly observed/transformed and null skipping is well understood.
10. Producer routing: event types map to the right destination.
11. Consumer router: routes by region/event type to the right topic.
12. Unknown route: throws exception or goes to quarantine per policy.
13. Destination publish failure: source offset is not acknowledged prematurely.
14. Duplicate delivery: idempotency protects side effects.
15. Ordering: same key is processed per designed partition rules.
16. Security: a consumer without ACLs cannot read the topic even if a filter would discard records.
17. Metrics: filter counts, route counts, and reject counts accurately reflect record counts.

Use EmbeddedKafka or Testcontainers for integration tests. Use latches/Awaitility to wait for listeners and assert by eventId; do not use fixed sleeps to conclude a listener skipped or routed a record.

## 22. Common design mistakes

**Using a filter to move a record to another topic.** Filters only discard records from the current listener. Use a router and KafkaTemplate to publish to a destination.

**Discarding records that need auditing.** Excluded records do not automatically go to a DLT. Route them to a rejected/quarantine topic or record them durably.

**Using an overly broad topicPattern.** The listener may pick up retry, DLT, or internal topics. Use explicit topics or tested regexes.

**Filter calling HTTP/database per record.** Blocks the consumer thread, increases lag, and risks exceeding max.poll.interval.ms. Use lightweight, deterministic, local predicates.

**Using filters in place of idempotency.** Pre-processing checks have race conditions. Use an inbox/unique constraint in the business transaction.

**Not checking ackDiscarded.** Offsets of excluded records may not be acknowledged as expected depending on AckMode and container config. Test commits after restart/rebalance.

**Dropping tombstones on compacted topics.** Tombstones may represent key deletions. Filter only if the listener truly does not need these semantics.

**Routing without preserving the key.** Events for the same aggregate may land in different partitions and lose intended ordering. Preserve keys and design compatible partitioning.

**Publishing to destination then committing source too early.** Failures between the two operations can lose or duplicate records. Use Kafka transactions or idempotent downstream consumers.

**Using interceptors for domain business logic.** Cross-cutting hooks become hard-to-test logic containers. Put business decisions in an explicit router/service.

**Not defining a default/unknown route policy.** Unknown event types get sent to the wrong topic. Use an allowlist and explicit unknown-route behavior.

## 23. Checklist for choosing filter or routing

- [ ] Determined whether records should be skipped or forwarded to another branch.
- [ ] Filter only excludes records the current listener does not need to process.
- [ ] Records needing audit/replay are routed to rejected/quarantine.
- [ ] RecordFilterStrategy returns true when discarding.
- [ ] Filter calls no remote dependencies and performs no heavy side effects.
- [ ] Semantics of tombstones and null payloads are defined.
- [ ] ackDiscarded is configured to match AckMode.
- [ ] Batch filter preserves relative ordering of remaining records.
- [ ] RecordInterceptor is used only for cross-cutting logic.
- [ ] Routing has a destination allowlist and unknown-route policy.
- [ ] Producer-side routing is preferred when the destination is known at the source.
- [ ] Consumer-side routing handles send results and offsets safely.
- [ ] Keys are preserved when aggregate ordering is required.
- [ ] Consume-and-route uses appropriate transactions or idempotency.
- [ ] Filters are not used in place of authorization or idempotency.
- [ ] Metrics exist for filtered, routed, rejected, and route failures.
- [ ] Integration tests cover discard, route, retry, offsets, and ordering.

## Conclusion

Choose filtering when a record truly does not need processing by the current listener; choose routing when the record still has value and must be forwarded to another branch or topic. In Spring Kafka, RecordFilterStrategy is the clear choice for filtering, RecordInterceptor is for cross-cutting pre-listener hooks, and routing belongs at the producer or in a router/service with a destination allowlist. Clarify offset behavior for discarded records, do not use filters in place of retries, DLTs, idempotency, or authorization, and ensure consume-and-route never commits the source before safely publishing to the destination.

## References

- [Spring Kafka – Filtering Messages](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/filtering.html)
- [Spring Kafka – Message Listener Containers and Interceptors](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring Kafka – Sending Messages](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html)
- [Spring Kafka – Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)

