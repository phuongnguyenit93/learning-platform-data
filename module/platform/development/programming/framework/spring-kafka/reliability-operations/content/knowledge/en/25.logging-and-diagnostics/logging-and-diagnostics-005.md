# Log topic, partition, and offset

In Spring Kafka, a log line like “Processed OrderCreated” is usually insufficient for incident investigation. A topic can hold millions of records, multiple partitions are processed concurrently by multiple consumer instances, and the same business event can reappear after a retry or DLT replay. To locate the exact record, verify processing order, and measure consumer progress, logs need three fundamental Kafka coordinates: **topic, partition, and offset**.

- **Topic** identifies which data stream the record belongs to.
- **Partition** identifies the partitioned log where the record is stored and order is preserved.
- **Offset** identifies the record's position within that partition.

In Spring Kafka, these details are available on `ConsumerRecord` when the listener receives a record. They can be logged with SLF4J, emitted in structured JSON logs, attached to MDC so every log within the same invocation shares context, and paired with producer metadata to trace where outputs were written. This lesson focuses on writing useful logs, interpreting offsets accurately, and preserving record lineage across retries/recovery.

## 1. The three basic coordinates of a Kafka record

A Kafka record is physically located by the tuple:

~~~text
(topic, partition, offset)
~~~

Example:

~~~text
topic=orders.created
partition=3
offset=1842
~~~

This means the record resides in partition 3 of topic `orders.created` at offset 1842.

| Attribute | Meaning | Scope |
|---|---|---|
| Topic | Kafka data stream | Topic name |
| Partition | An ordered log inside the topic | Meaningful only alongside topic |
| Offset | Record position in the partition | Monotonic within that partition's log |

A record can be logged as:

~~~text
event=consumed topic=orders.created partition=3 offset=1842
~~~

This tuple represents the **physical record coordinates in Kafka**. It is invaluable for locating records, comparing consumer logs, and inspecting offsets in Kafka tooling. However, it is not a business identity: if the same event is republished, the new record may have a different partition/offset even though `eventId` remains unchanged.

## 2. Topic is not consumer group

A topic describes where records are stored. A consumer group describes a group of consumers coordinating partition splits and maintaining reading progress.

Example:

~~~text
Topic: orders.created
  partition 0
  partition 1
  partition 2

Consumer group: order-projection
  consumer A -> partition 0
  consumer B -> partition 1, 2
~~~

One topic can be read by multiple independent consumer groups. Each group maintains its own committed offsets, so logs also need the group ID when diagnosing progress.

| Value | Answers the question |
|---|---|
| Topic | Which stream does the record belong to? |
| Partition | Which partition holds the record? |
| Offset | What is the record's position in the partition? |
| Consumer group | Which group is reading and committing progress? |
| Consumer/client ID | Which instance/client is executing the work? |
| Event ID | Which business event is this? |

`ConsumerRecord` provides topic, partition, and offset, but **does not always provide the consumer group ID**. Group ID normally comes from listener/container configuration or application metadata. Never take client ID and write it into the group ID field; they are distinct concepts.

## 3. Offsets are scoped to a partition

An offset is a record's position within a single partition. It is not a global sequence number across the topic.

~~~text
orders.created partition 0:
  offset 0 -> event A
  offset 1 -> event B
  offset 2 -> event C

orders.created partition 1:
  offset 0 -> event D
  offset 1 -> event E
  offset 2 -> event F
~~~

Offset 2 in partition 0 and offset 2 in partition 1 are two completely different records. Hence, a log with only `offset=2` cannot identify a record.

Nor can you compare offsets across partitions to determine which record happened earlier topic-wide. Kafka guarantees order within a single partition; if business ordering is needed per aggregate, producers typically use a stable key so records for the same aggregate land in the same partition.

## 4. Offsets seen by consumers are not always contiguous

Offsets increment monotonically in a partition log, yet consumers must not assume the records they read always have consecutive offsets. Reasons include:

- Log compaction retains the latest record per key and removes older versions.
- Aborted transactional records are hidden from `read_committed` consumers.
- Retention deletes older records.
- Consumers start reading from another offset per committed position or reset policy.

Example:

~~~text
Physical log offsets:
  100, 101, 102, 103, 104, 105

read_committed consumer sees:
  100, 101,      103,      105
~~~

Offset gaps alone do not prove the consumer lost data. When investigating, check isolation level, compaction, retention, and transaction state.

## 5. Reading metadata directly from ConsumerRecord

For a record listener, the clearest approach is accepting `ConsumerRecord<K,V>` instead of only the payload:

~~~java
@Component
public class OrderListener {

    private static final Logger log =
            LoggerFactory.getLogger(OrderListener.class);

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
        id = "orders-listener",
        topics = "orders.created",
        groupId = "order-projection")
    public void onMessage(
            ConsumerRecord<String, OrderCreated> record) {

        log.info(
            "Kafka record received topic={} partition={} offset={} key={} timestamp={}",
            record.topic(),
            record.partition(),
            record.offset(),
            record.key(),
            record.timestamp()
        );

        orderService.apply(record.value());
    }
}
~~~

Common methods:

| Method | Value |
|---|---|
| `record.topic()` | Topic name |
| `record.partition()` | Partition number |
| `record.offset()` | Record offset |
| `record.key()` | Kafka key |
| `record.value()` | Deserialized payload |
| `record.timestamp()` | Kafka record timestamp |
| `record.timestampType()` | Timestamp type |
| `record.headers()` | Kafka headers |
| `record.serializedKeySize()` | Serialized key size |
| `record.serializedValueSize()` | Serialized value size |

Not every field is safe to log. Keys may contain customer IDs or sensitive data; values may contain personal data. Usually log topic/partition/offset/timestamp and an approved business correlation ID rather than full payloads.

## 6. Logging metadata using Spring Message headers

If a listener accepts the payload instead of ConsumerRecord, Spring Kafka can map metadata into message headers:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders.created",
    groupId = "order-projection")
public void onMessage(
        OrderCreated event,
        @Header(KafkaHeaders.RECEIVED_TOPIC) String topic,
        @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
        @Header(KafkaHeaders.OFFSET) long offset) {

    log.info(
        "Order event received topic={} partition={} offset={} eventId={}",
        topic,
        partition,
        offset,
        event.eventId()
    );

    orderService.apply(event);
}
~~~

Constants `KafkaHeaders.RECEIVED_TOPIC`, `RECEIVED_PARTITION`, and `OFFSET` avoid hardcoding header names. Depending on your Spring Kafka version, the import normally lives in `org.springframework.kafka.support.KafkaHeaders`.

Use header mapping when the listener only needs the payload plus a few metadata fields. Use `ConsumerRecord` when you also need the key, timestamp, headers, serialized sizes, or full record context.

If a header is missing or the method signature is incompatible with the listener type, Spring may fail to resolve the argument. Check mapped data types and your Spring Kafka version's API.

## 7. Distinguishing record offset from committed consumer offset

This is one of the most common confusions when reading logs.

Suppose the listener just received record offset 42:

~~~text
ConsumerRecord.offset() = 42
~~~

When the consumer group acknowledges processing this record, the committed offset is normally **43**, meaning the next position the consumer group will read. Thus:

- Record offset is the position of the current record.
- Consumer position is where the consumer will read next in the current session.
- Committed group offset is the durably stored progress for the group.
- These three values are related, not identical.

Example:

~~~text
Just-processed record: offset 42
Committed offset:      43
Next record:           offset 43 (if a record exists there)
~~~

If a log reads `record offset=42`, do not call it “committed offset 42” unless you are genuinely logging the commit value. Depending on `AckMode.RECORD`, `BATCH`, `MANUAL`, or transactions, commit timing varies.

## 8. Logging at record receipt vs. processing completion

Distinguish at least two events:

~~~text
event=record_received topic=orders.created partition=3 offset=1842
event=record_processed topic=orders.created partition=3 offset=1842 result=success
~~~

Example:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders.created",
    groupId = "order-projection")
public void onMessage(
        ConsumerRecord<String, OrderCreated> record) {

    log.info(
        "Kafka record received topic={} partition={} offset={}",
        record.topic(),
        record.partition(),
        record.offset()
    );

    orderService.apply(record.value());

    log.info(
        "Kafka record processing completed topic={} partition={} offset={} result=success",
        record.topic(),
        record.partition(),
        record.offset()
    );
}
~~~

When `orderService.apply` returns normally, the completed log may reflect that the DB service transaction committed if called through a Spring proxy and the transaction ended before returning.

However, with a Kafka transactional listener, **the listener method returning does not mean the container committed the Kafka transaction**. The container still has to add the offset to the transaction and commit. Therefore, use accurate phrasing like `listener_processing_completed` instead of claiming `kafka_transaction_committed` before observing the commit outcome.

## 9. Error logs must retain topic, partition, and offset

When a listener throws an exception, logs must let operators identify the failing record without printing payloads.

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders.created",
    groupId = "order-projection")
public void onMessage(
        ConsumerRecord<String, OrderCreated> record) {

    try {
        orderService.apply(record.value());
    } catch (RuntimeException ex) {
        log.error(
            "Kafka record processing failed topic={} partition={} offset={} exceptionType={}",
            record.topic(),
            record.partition(),
            record.offset(),
            ex.getClass().getSimpleName(),
            ex
        );
        throw ex;
    }
}
~~~

Rethrowing the exception lets the container error handler perform retries/recovery per configuration. If you only log and return normally, the listener may be treated as successful and offsets advance despite the failed business write.

Do not log the exact same stack trace at every layer unintentionally. If the listener logs an error, the error handler logs too, and the DLT recoverer logs again, one error produces redundant entries. Pick one layer to own full logging and keep other layers to concise metadata.

## 10. Using MDC to attach record context to all logs in an invocation

MDC (Mapped Diagnostic Context) adds fields like topic, partition, offset, and event ID to every log emitted within the current scope.

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders.created",
    groupId = "order-projection")
public void onMessage(
        ConsumerRecord<String, OrderCreated> record) {

    try (MDC.MDCCloseable topic =
                 MDC.putCloseable("kafka.topic", record.topic());
         MDC.MDCCloseable partition =
                 MDC.putCloseable("kafka.partition",
                                  Integer.toString(record.partition()));
         MDC.MDCCloseable offset =
                 MDC.putCloseable("kafka.offset",
                                  Long.toString(record.offset()));
         MDC.MDCCloseable eventId =
                 MDC.putCloseable("event.id",
                                  record.value().eventId().toString())) {

        log.info("Processing order event");
        orderService.apply(record.value());
        log.info("Order event processing completed");
    }
}
~~~

`MDC.putCloseable` exists in SLF4J 2.x. If your application uses an older SLF4J version, use `MDC.put` and `MDC.remove` inside `try/finally`.

Fallback example:

~~~java
MDC.put("kafka.topic", record.topic());
MDC.put("kafka.partition", Integer.toString(record.partition()));
MDC.put("kafka.offset", Long.toString(record.offset()));

try {
    orderService.apply(record.value());
} finally {
    MDC.remove("kafka.topic");
    MDC.remove("kafka.partition");
    MDC.remove("kafka.offset");
}
~~~

**Always remove MDC after the invocation.** Consumer threads are reused across many records. Without cleanup, the next record can log with the previous record's topic/offset.

## 11. MDC and asynchronous processing

MDC is normally bound to the current thread. If a listener submits work to another executor:

~~~java
@KafkaListener(topics = "orders.created")
public void onMessage(ConsumerRecord<String, OrderCreated> record) {
    MDC.put("kafka.offset", Long.toString(record.offset()));

    CompletableFuture.runAsync(() -> {
        log.info("Applying order projection");
        orderService.apply(record.value());
    });

    MDC.remove("kafka.offset");
}
~~~

Logs inside the async task may **lack MDC** because it executes on another thread. Furthermore, returning from the listener before the task completes can let the container commit the offset prematurely, risking lost work.

If using async processing:

- Define clearly whether the listener awaits task completion.
- Use proper executor/context propagation if MDC or trace context must carry over.
- Never pass the Kafka `Consumer` to another thread.
- Ensure async errors translate into outcomes the container understands.
- Never ack/commit offsets before mandatory side effects finish.

MDC is a log correlation tool, not a transaction context, and provides no thread-safety guarantees.

## 12. Structured logging instead of free-form string concatenation

Good text logs use consistent key-value fields:

~~~text
event=record_processed
listener=orders-listener
group=order-projection
topic=orders.created
partition=3
offset=1842
event_id=evt-91fe
result=success
duration_ms=27
~~~

With JSON logging, a record might look like:

~~~json
{
  "timestamp": "2026-11-15T10:20:30.120Z",
  "level": "INFO",
  "message": "Kafka record processing completed",
  "event": "record_processed",
  "listener": "orders-listener",
  "consumer_group": "order-projection",
  "topic": "orders.created",
  "partition": 3,
  "offset": 1842,
  "event_id": "evt-91fe",
  "result": "success",
  "duration_ms": 27
}
~~~

Benefits:

- Log searches can filter by topic, partition, and offset.
- Operators can join logs across producers, consumers, and DLTs.
- Dashboards can aggregate error events by listener or topic.
- Metadata fields have consistent types, avoiding brittle free-text parsing.

Never put per-record fields into metric labels. Structured logs can store event IDs/offsets for searching; Prometheus labels need much lower cardinality.

## 13. Which fields should be logged?

A suggested schema:

| Field | Source | Purpose |
|---|---|---|
| event | Application-defined | record_received, record_processed, record_failed |
| listener | Listener/container ID | Identify handler |
| consumer_group | Container config | Identify group progress |
| topic | ConsumerRecord.topic() | Data stream |
| partition | ConsumerRecord.partition() | Partition |
| record_offset | ConsumerRecord.offset() | Record position |
| key | ConsumerRecord.key() | Log only if permitted |
| event_id | Business payload/header | Correlation across retries/replays |
| trace_id | Tracing context | Link spans/logs |
| result | Application | success, failure, recovered |
| duration_ms | Timer/Stopwatch | Invocation duration |
| attempt | Retry metadata | Attempt count if backed by a reliable source |
| exception_type | Exception classifier | Error classification |
| instance | Deployment metadata | Processing pod/host |

Not every log needs all fields. A receipt log can include topic/partition/offset/event ID; an error log adds exception type; a recovery log includes original coordinates and destination topic.

## 14. Do not log payloads and sensitive data by default

Kafka values can contain emails, phone numbers, addresses, financial records, tokens, or customer data. Logging full `record.value()` can push sensitive data into log systems with different retention and access controls than databases.

Instead:

- Log topic, partition, offset, and event type.
- Use an approved business event ID.
- If keys are needed, verify whether keys contain PII.
- Avoid logging raw headers since they can carry authorization or trace baggage.
- For failing payloads, log schema/version and exception class; keep raw bytes in quarantine/DLT under separate policy.
- Redact fields before logging if specific attributes are genuinely needed for investigation.

An unsafe example:

~~~java
log.error("Failed to process record: {}", record, exception);
~~~

`ConsumerRecord.toString()` can expose keys/values/headers depending on implementation. Explicitly select safe metadata:

~~~java
log.error(
    "Record failed topic={} partition={} offset={} exceptionType={}",
    record.topic(),
    record.partition(),
    record.offset(),
    exception.getClass().getSimpleName(),
    exception
);
~~~

## 15. Logging producer metadata to know where records were written

On the producer side, the topic is chosen in the send call, yet the actual partition and offset only exist after the broker acknowledges the write.

In Spring Kafka 3.x, `KafkaTemplate.send` returns `CompletableFuture<SendResult<K,V>>`:

~~~java
public void publish(OrderCreated event) {
    kafkaTemplate.send(
        "orders.created",
        event.orderId(),
        event
    ).whenComplete((result, exception) -> {
        if (exception != null) {
            log.error(
                "Kafka publish failed topic={} eventId={}",
                "orders.created",
                event.eventId(),
                exception
            );
            return;
        }

        RecordMetadata metadata = result.getRecordMetadata();

        log.info(
            "Kafka publish acknowledged topic={} partition={} offset={} eventId={}",
            metadata.topic(),
            metadata.partition(),
            metadata.offset(),
            event.eventId()
        );
    });
}
~~~

`RecordMetadata` provides topic, partition, offset, and related information about the broker-acknowledged record.

In older Spring Kafka versions, send APIs returned `ListenableFuture` with different callback syntax. Check your version rather than copying `CompletableFuture` snippets into an older API codebase.

**Do not block the consumer thread with `future.get()` solely to log an offset** without clear justification. Asynchronous callbacks are usually preferable. If the producer send sits inside a Kafka transaction, a broker ack log on send does not prove the overall transaction committed.

## 16. Keys and partition routing

The producer key normally determines the partition under the default partitioner when no explicit partition is given. Using `orderId` as the key routes records for the same order into the same partition, preserving relative order for that aggregate.

~~~java
kafkaTemplate.send(
    "orders.created",
    event.orderId(),
    event
);
~~~

When logging from producers, distinguish:

- **Requested topic:** the topic the application asked to send to.
- **Requested partition:** explicit partition if specified by the producer.
- **Acknowledged partition:** actual partition in `RecordMetadata`.
- **Key:** routing/business key value.
- **Offset:** position assigned by the broker within the partition.

If partition count changes or partitioner/config changes, key-to-partition mapping can shift over time. Do not use a past record's partition log to assume all records with that key will always stay on that partition after a migration.

## 17. Retries can create new coordinates

When a failing record is forwarded to a retry topic, it becomes a record at a different topic/partition/offset:

~~~text
Original:
  orders.created-3@1842

Forwarded retry:
  orders.created-retry-1000-1@205

DLT:
  orders.created.DLT-0@71
~~~

These are **different physical coordinates** that can still carry the same business event ID. Therefore, retry logs should capture both:

- Current topic/partition/offset.
- Original topic/partition/offset if metadata is present.
- Stable business event ID.
- Retry attempt or delivery metadata if supplied.
- Destination topic when forwarding.

Spring Kafka provides DLT headers such as `KafkaHeaders.DLT_ORIGINAL_TOPIC`, `DLT_ORIGINAL_PARTITION`, and `DLT_ORIGINAL_OFFSET` in supported versions. Check header constants/APIs in your running version when using a recoverer.

Never log the DLT's current offset as if it were the original offset. Keep two distinct field names in structured logs.

## 18. Logging in error handlers and DLT recoverers

`DefaultErrorHandler` orchestrates retries and recovery. You can wrap or add a recoverer to log record coordinates when a record enters recovery:

~~~java
ConsumerRecordRecoverer loggingRecoverer = (record, exception) -> {
    log.error(
        "Kafka record recovery invoked topic={} partition={} offset={} exceptionType={}",
        record.topic(),
        record.partition(),
        record.offset(),
        exception.getClass().getSimpleName(),
        exception
    );

    deadLetterPublishingRecoverer.accept(record, exception);
};

DefaultErrorHandler errorHandler = new DefaultErrorHandler(
    loggingRecoverer,
    new FixedBackOff(1_000L, 2L)
);
~~~

`deadLetterPublishingRecoverer` is a separately configured `DeadLetterPublishingRecoverer`. This example shows where to log when the recoverer is invoked; it does not replace verifying the DLT publish succeeded. Observe send/recovery outcomes per your policy.

Depending on Spring Kafka version, factories attach error handlers via `setCommonErrorHandler` or older APIs. For transactional listeners, after-rollback processors and recovery transactions have separate semantics; do not mechanically apply non-transactional examples.

## 19. Logging offsets in batch listeners

A batch listener receives multiple records per invocation. A log with only one offset can be misleading if the batch spans multiple partitions.

Example:

~~~java
@KafkaListener(
    id = "orders-batch-listener",
    topics = "orders.created",
    groupId = "order-batch-projection",
    containerFactory = "batchListenerFactory")
public void onBatch(
        List<ConsumerRecord<String, OrderCreated>> records) {

    log.info(
        "Kafka batch received listener={} recordCount={}",
        "orders-batch-listener",
        records.size()
    );

    for (ConsumerRecord<String, OrderCreated> record : records) {
        log.debug(
            "Batch record topic={} partition={} offset={}",
            record.topic(),
            record.partition(),
            record.offset()
        );
    }

    orderBatchService.apply(records);
}
~~~

A batch can contain records from multiple partitions. To summarize, group by `topic + partition` and log:

- Record count per partition.
- Lowest and highest offset in the batch.
- Event IDs or correlation IDs per policy.
- Batch invocation ID to link related logs.

Never log just `minOffset=10, maxOffset=50` and assume every offset 10–50 was inside the batch. Compaction, transaction visibility, and batch composition can create gaps.

## 20. Partition order vs. log sequence

Kafka guarantees reading order within a partition by offset. If a consumer logs:

~~~text
orders.created-2@100
orders.created-2@101
orders.created-2@102
~~~

that is a sequence of records by log position. However, log lines can appear out of offset order when:

- Multiple consumer threads write concurrently to one log sink.
- Async logging/buffer flushes alter display ordering.
- The application processes asynchronously after the listener returns.
- A record retries and finishes later than a higher-offset record.
- A log aggregator ingests events from multiple pods with varying latency.

When investigating ordering, rely on topic/partition/offset as the source order rather than line display order in Kibana/Splunk/Loki. If business ordering per aggregate matters, include an event sequence/version.

## 21. Correlation between Kafka coordinates and business event IDs

Log both identifiers side by side:

~~~text
topic=orders.created
partition=3
offset=1842
event_id=evt-91fe
order_id=ord-913
~~~

- Kafka coordinates locate the specific record.
- `event_id` locates the same business event across retries, DLTs, republishes, and multiple topics.
- `order_id` identifies the aggregate, which can legitimately have many events.

If the same event ID appears at two different offsets, it could be a producer duplicate or an intentional replay. Do not jump to conclusions solely because offsets differ.

Trace ID is another form of correlation. An event can be replayed under a new trace; trace ID does not replace event ID as an idempotency key.

## 22. Consumer group and committed offset in logs

When logging commit progress, explicitly label it as **committed offset** along with the consumer group:

~~~text
event=offset_commit
consumer_group=order-projection
topic=orders.created
partition=3
committed_offset=1843
~~~

Do not reuse the same `offset` field for both record offset and committed offset. Use explicit names:

| Field | Meaning |
|---|---|
| record_offset | Offset of the record the listener is processing |
| committed_offset | Offset acknowledged for the consumer group |
| consumer_position | Next position the consumer will read in the current session |
| original_offset | Source record offset before retry/DLT |
| destination_offset | Offset of record written to another topic |

With auto-commit, record/batch ack modes, manual ack, and Kafka transactions, commit timing differs. When logging commit callbacks or container events, verify which API emitted the data and which offset value it represents.

Do not log `record.offset() + 1` as committed offset unless you are accurately describing a committed record under container semantics with no prior unprocessed records. In batch or out-of-order processing, naive addition can be wrong.

## 23. Offsets and AckMode

`AckMode` governs how the container acknowledges offsets. Common modes:

| Ack mode | General meaning |
|---|---|
| `RECORD` | Commit when each record listener finishes |
| `BATCH` | Commit after all records in the poll batch are processed |
| `TIME` | Commit based on elapsed time and eligible records |
| `COUNT` | Commit after a threshold number of processed records |
| `MANUAL` | Application calls acknowledge; committed per batch semantics |
| `MANUAL_IMMEDIATE` | Acknowledge can commit immediately depending on thread and config |

When reading a record offset log, you cannot infer the committed offset at the moment the record was received. If the listener finishes a record while the batch is still running, the offset may not be committed yet.

With manual acknowledgment, never call `acknowledge()` before business work finishes. If a DB commit succeeds while the Kafka offset fails to commit due to a crash, the record may be redelivered; the database needs idempotency.

## 24. Kafka transactions and commit logs

In a transactional listener container, Kafka output records and input offsets can share the same Kafka transaction. A listener log:

~~~text
event=listener_processing_completed
topic=orders.created partition=3 offset=1842
~~~

only indicates the method returned normally from the application's viewpoint. It **does not necessarily prove the Kafka transaction committed**. Afterward, the container must still send offsets to the transaction and commit.

Distinguish log events:

~~~text
record_received
listener_processing_completed
kafka_transaction_commit_succeeded
kafka_transaction_rollback
record_recovered
~~~

Emit commit/rollback events from a layer with actual transaction outcome visibility rather than guessing at the end of the listener.

For downstream consumers using `read_committed`, outputs become visible only after transaction commit. A successful producer send callback before commit does not mean downstream can read the output yet.

## 25. How can producer RecordMetadata and consumer ConsumerRecord be joined?

The producer receives `RecordMetadata` after broker acknowledgement:

~~~java
RecordMetadata metadata = sendResult.getRecordMetadata();

log.info(
    "Kafka output acknowledged topic={} partition={} offset={}",
    metadata.topic(),
    metadata.partition(),
    metadata.offset()
);
~~~

The consumer receives `ConsumerRecord`:

~~~java
log.info(
    "Kafka input received topic={} partition={} offset={}",
    record.topic(),
    record.partition(),
    record.offset()
);
~~~

If both logs share the same topic/partition/offset in the same cluster and record, operators can join them. However, do not use offset to correlate across two different topics. When a service transforms input topic A into output topic B, the output offset is a new position; retain `eventId`/correlation ID to link the business flow.

## 26. Logging when a producer send fails

A producer send can fail before receiving broker metadata. In that case, there is no reliable acknowledged partition/offset to log as success.

~~~java
kafkaTemplate.send("orders.created", event.orderId(), event)
    .whenComplete((result, exception) -> {
        if (exception != null) {
            log.error(
                "Kafka send failed topic={} eventId={}",
                "orders.created",
                event.eventId(),
                exception
            );
            return;
        }

        RecordMetadata metadata = result.getRecordMetadata();

        log.info(
            "Kafka send acknowledged topic={} partition={} offset={} eventId={}",
            metadata.topic(),
            metadata.partition(),
            metadata.offset(),
            event.eventId()
        );
    });
~~~

Do not log partition/offset as `0` on send failures just to avoid null. Leave them absent or record status `not_acknowledged`. If the producer retried internally before the callback failed, callback failure is the final send outcome; check producer metrics/logs to investigate internal client attempts.

## 27. Logging when forwarding to a retry topic or DLT

When recovering a record, separate source and destination:

~~~text
event=record_forwarded
original_topic=orders.created
original_partition=3
original_offset=1842
destination_topic=orders.created.DLT
destination_partition=0
destination_offset=71
event_id=evt-91fe
reason=non_retryable
~~~

The destination offset exists only after the DLT publish is broker-acknowledged. If DLT publishing is asynchronous, log `forward_requested` before send and `forward_acknowledged` after the callback; do not record a destination offset before receiving metadata.

For retry topics, retain original coordinates in headers if supported by the framework/recoverer. When reading back from a retry topic, log both current coordinates and original coordinates. That lets operators find the first record and the event's full lineage.

## 28. Logging metadata from DLT headers

Spring Kafka provides DLT headers to preserve source details, commonly including:

- `KafkaHeaders.DLT_ORIGINAL_TOPIC`.
- `KafkaHeaders.DLT_ORIGINAL_PARTITION`.
- `KafkaHeaders.DLT_ORIGINAL_OFFSET`.
- `KafkaHeaders.DLT_ORIGINAL_CONSUMER_GROUP` in supported versions.
- Exception metadata headers configured by the recoverer.

A DLT listener can inspect headers:

~~~java
@KafkaListener(
    topics = "orders.created.DLT",
    groupId = "orders-dlt-inspector")
public void inspect(
        ConsumerRecord<String, OrderCreated> record) {

    Header originalTopic =
            record.headers().lastHeader(KafkaHeaders.DLT_ORIGINAL_TOPIC);

    Header originalPartition =
            record.headers().lastHeader(KafkaHeaders.DLT_ORIGINAL_PARTITION);

    Header originalOffset =
            record.headers().lastHeader(KafkaHeaders.DLT_ORIGINAL_OFFSET);

    log.error(
        "DLT record currentTopic={} currentPartition={} currentOffset={} originalTopicHeaderPresent={} originalPartitionHeaderPresent={} originalOffsetHeaderPresent={}",
        record.topic(),
        record.partition(),
        record.offset(),
        originalTopic != null,
        originalPartition != null,
        originalOffset != null
    );
}
~~~

This example only logs header presence to avoid assuming header value encoding/deserialization. To extract actual values, decode byte arrays per your API/version and handle missing or malformed headers. Never blindly cast header values to `String` or `Integer` when Kafka headers store raw bytes.

## 29. Logging assignments and rebalances to place record context on the right consumer

Topic/partition/offset tells where a record lives, while investigating “which consumer holds the partition” also needs group membership/assignment info. Spring Kafka provides rebalance listeners and container events to observe assignments/revocations.

An assignment log may look like:

~~~text
event=partitions_assigned
listener=orders-listener
consumer_group=order-projection
partitions=[orders.created-0, orders.created-1]
instance=orders-pod-2
~~~

Do not confuse an assignment log with record processing. A consumer can be assigned partitions without receiving records yet; the topic may be empty or committed offsets already at the end of the log.

When partitions are revoked, log the prior assignment and lifecycle event to analyze rebalances. Never put a partition list into a dynamic string metric label if assignments churn continuously.

## 30. Never use offset as a metric label

Offsets change on every record. Attaching `offset` as a Micrometer tag or Prometheus label creates a new time series for almost every record.

Avoid:

~~~java
Timer.builder("kafka.record.processing")
    .tag("topic", record.topic())
    .tag("partition", Integer.toString(record.partition()))
    .tag("offset", Long.toString(record.offset()))
    .register(registry);
~~~

Use low-cardinality metric dimensions instead:

~~~java
Timer.builder("kafka.record.processing")
    .tag("topic", record.topic())
    .tag("listener", "orders-listener")
    .tag("result", "success")
    .register(registry);
~~~

Offsets belong in **logs/traces**, where you search for a specific record. Metrics aggregate latency/counts by topic, listener, partition (if partition count is finite and controlled), and result.

## 31. Log volume and sampling

A consumer processing 50,000 records/second that emits an INFO log per record generates millions of log entries per minute. That drives up storage and network costs and makes operators more likely to miss real errors.

A common strategy:

| Log type | Suggested level | Content |
|---|---|---|
| Listener lifecycle/start/stop | INFO | Listener ID, group, instance |
| Every received record | DEBUG or controlled INFO | Topic/partition/offset/event ID |
| Successful processing | DEBUG or sampled INFO | Coordinates + duration |
| Record error | ERROR/WARN per policy | Coordinates + exception |
| Retry attempt | Rate-limited WARN/INFO | Coordinates + attempt |
| DLT recovery | ERROR or WARN | Original + destination coordinates |
| Offset/commit lifecycle | DEBUG/INFO as needed | Group, partition, committed offset |

Do not sample or rate-limit errors in a way that drops all details of critical incidents. Reduce success logs while keeping failure logs, DLT logs, and structured metrics.

If using asynchronous logging, check queue-full/discard policies; at peak load, error logs might be dropped right when needed most.

## 32. Creating a helper for consistent record context logging

To avoid repeating formatting strings across listeners, create a small value object:

~~~java
public record KafkaRecordCoordinates(
        String topic,
        int partition,
        long offset) {

    public static KafkaRecordCoordinates from(
            ConsumerRecord<?, ?> record) {
        return new KafkaRecordCoordinates(
            record.topic(),
            record.partition(),
            record.offset()
        );
    }
}
~~~

Usage:

~~~java
KafkaRecordCoordinates coordinates =
        KafkaRecordCoordinates.from(record);

log.info(
    "Kafka record failed topic={} partition={} offset={}",
    coordinates.topic(),
    coordinates.partition(),
    coordinates.offset(),
    exception
);
~~~

This helper only wraps physical metadata; it holds no payload, does not replace event ID, and does not represent committed group offsets. You can add a helper method returning a map for structured logging, while keeping dynamic fields out of metric tags.

If the application needs to log source coordinates for retries/DLT, create a separate type for `originalCoordinates` so it is never confused with current coordinates.

## 33. Checking logs with Kafka command-line tools

Once topic/partition/offset are in logs, operators can use Kafka tools to inspect the log at that position. Depending on Kafka version, common commands include:

~~~bash
kafka-console-consumer.sh \
  --bootstrap-server kafka.example:9092 \
  --topic orders.created \
  --partition 3 \
  --offset 1842 \
  --max-messages 1
~~~

This command illustrates reading from partition 3, offset 1842. Depending on Kafka CLI version, extra consumer properties, isolation level, or other flags may be needed. For transactional topics, the consumer needs matching isolation settings to see records as the production app does.

To inspect committed group offsets, use the consumer groups tool:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka.example:9092 \
  --group order-projection \
  --describe
~~~

Group describe normally reports current offset, log-end offset, and lag per partition. This shows group progress, not the record payload at a given offset.

Never run offset reset commands in production merely for investigation. `--reset-offsets` alters consumer group progress; execute it only under approved, audited runbooks.

## 34. Checking logs in compacted and transactional environments

If an operator cannot find a record at a logged offset, check:

- Does the topic have `cleanup.policy=compact`?
- Was the record key overwritten by a newer record?
- Did retention already delete the segment holding the old record?
- Is the consumer using `read_committed` while the record belonged to an aborted transaction?
- Was the topic deleted/recreated since the log was written?
- Are the cluster/bootstrap endpoints correct?
- Did partition counts or topic names change during a migration?

Logged coordinates prove position **at the time the record existed**, not that the record stays in the log forever. For long-term auditing, store business event IDs and audit data in a suitable durable store rather than treating Kafka retention as an immutable archive.

## 35. Distinguishing timestamp from offset

`ConsumerRecord.timestamp()` returns the Kafka timestamp attached to the record. Depending on topic config, timestamps reflect producer creation time or broker log append time.

Offset is not a timestamp and cannot be converted into wall-clock time by inference.

~~~text
topic=orders.created
partition=3
offset=1842
timestamp=1763202000123
timestampType=CREATE_TIME
~~~

Timestamps help investigate event age, provided you know the source:

- `CreateTime`: timestamp set by the producer.
- `LogAppendTime`: timestamp written by the broker on append, if configured on the topic.
- Producer clock skew can keep create time from matching exact wall time.
- Timestamps do not replace offsets for partition ordering.

Log the timestamp type as well when event timing matters.

## 36. Security and consistency of log fields

Practical rules:

1. Use consistent field names: `topic`, `partition`, `offset`, `consumer_group`.
2. Distinguish `record_offset` from `committed_offset`.
3. Keep partition/offset as integers in JSON logs rather than strings if your backend supports numeric types.
4. Never log raw payloads, secrets, or authorization headers.
5. Log keys only after verifying they contain no PII.
6. Use event IDs for correlation while enforcing proper access control and retention.
7. Log exception types/causes, not just free-form exception messages.
8. Never turn offsets/event IDs into metric labels.
9. Keep current and original coordinates separate in retry/DLT logs.
10. Maintain a log schema/version if downstream searches depend on field names.

When changing a log schema, preserve compatibility for dashboards and runbooks or update them in the same release.

## 37. End-to-end log example for one record

A flow can emit the following logs:

~~~text
event=producer_send_requested
topic=orders.created
event_id=evt-91fe
order_id=ord-913

event=producer_send_acknowledged
topic=orders.created
partition=3
offset=1842
event_id=evt-91fe

event=consumer_record_received
listener=orders-listener
consumer_group=order-projection
topic=orders.created
partition=3
offset=1842
event_id=evt-91fe

event=listener_processing_completed
listener=orders-listener
topic=orders.created
partition=3
offset=1842
event_id=evt-91fe
duration_ms=27
result=success

event=record_forwarded
original_topic=orders.created
original_partition=3
original_offset=1842
destination_topic=orders.created.DLT
destination_partition=0
destination_offset=71
event_id=evt-91fe
reason=non_retryable
~~~

These log events represent different scenarios; a single record does not both succeed and route to DLT. Each entry illustrates a different lifecycle branch or stage. In production, the log schema must ensure events join cleanly via event ID and trace context.

## 38. Runbook: finding a record from log coordinates

When receiving a ticket containing `topic=orders.created partition=3 offset=1842`:

1. Verify the cluster/environment and topic name.
2. Verify the partition exists and the topic was not recreated.
3. Check retention/compaction and isolation level.
4. Locate the record at that partition/offset using authorized Kafka tooling.
5. Search structured logs sharing the same topic/partition/offset.
6. Search by event ID in logs to follow retries/DLT/outputs.
7. Identify which consumer group and instance processed the record.
8. Compare the record offset against the group's committed offset.
9. Inspect error handler/retry logs and DLT metadata.
10. If DB side effects duplicated, check the idempotency key in the database.
11. If Kafka output is missing, inspect producer metadata and transaction commit/rollback.
12. Document investigation findings using source coordinates and business event ID.

Never reset offsets before confirming whether the record was committed or side effects executed; replaying can create duplicates if the DB is not idempotent.

## 39. Runbook: repeated or strangely jumping log offsets

**Same topic/partition/offset appears multiple times:** may be due to logging at different layers, listener retries, aggregator duplication, or reprocessing of the same record. Check event types and attempt metadata before blaming the broker for duplicates.

**Offsets increase with gaps:** check compaction, aborted transactions, retention, and consumer isolation. Gaps do not prove lost records.

**Two pods log the same record coordinates:** may result from redelivery after a rebalance or logging one record across multiple stages. Inspect consumer group assignments, commit timing, and instance IDs.

**Offsets decrease:** may indicate consumer seek/replay, group offset reset, or reading another topic/cluster. Check audit logs for offset resets, retry/DLT, and bootstrap config.

**Same offset yet different event IDs:** you may be comparing two different topics/partitions or logs were tagged with wrong metadata. Verify the entire topic/partition/offset tuple.

## 40. Runbook: producer logs an offset yet consumer does not see the record

1. Confirm producer and consumer point to the same Kafka cluster.
2. Confirm topic name and partition.
3. Check whether the send log reflects acknowledged success or just pre-send intent.
4. If transactional, check transaction commit/abort; `read_committed` consumers only see committed outputs.
5. Check consumer group assignment and committed offset.
6. Check whether the consumer sought past that offset.
7. Check topic retention/compaction.
8. Check ACLs and deserialization errors.
9. Check whether the consumer is paused or experiencing abnormal lag/assignment.
10. Use Kafka CLI with matching isolation level to verify the record.
11. Search retry/DLT topics by trace/event ID in case the record was already forwarded.
12. Do not conclude the producer log is wrong just because the current consumer group already moved past that offset.

Producer acknowledgement confirms the broker accepted the write per producer semantics; it does not prove every consumer group will see the record at every moment.

## 41. Common mistakes

### Logging offset without topic/partition

Offsets only have meaning within a partition. Always log all three coordinates.

### Treating offset as event ID

Republishing the same business event produces a new offset. Use a stable event ID for correlation/dedup.

### Treating record offset as committed offset

Record offset is the record's position; committed offset is normally the next position to read. Use clear field names.

### Logging success before processing finishes

If logged at the start of the listener, that line cannot prove the business operation succeeded.

### Equating listener success logs with Kafka transaction commits

Listener method return and transaction commit are two separate milestones. Log commit outcomes from a layer with actual visibility.

### Logging the entire ConsumerRecord

This can leak payloads, PII, and sensitive headers. Select safe metadata explicitly.

### Putting offset into a Prometheus tag

Every record creates a new time series, exploding cardinality. Offsets belong in logs/traces.

### Inferring Kafka order from log line order

Async logging and multiple consumer threads can reorder displayed lines relative to offset order. Rely on coordinates.

### Dropping original coordinates during retry/DLT

You cannot link the new record back to the source record if you log only the destination offset.

### Forgetting to clear MDC

Consumer threads are reused; subsequent record logs can carry the previous record's metadata.

## 42. Implementation checklist

- [ ] Log full topic, partition, and record offset.
- [ ] Add listener ID, consumer group, and instance ID as needed for investigation.
- [ ] Use ConsumerRecord when full record metadata is needed.
- [ ] Use KafkaHeaders constants if the listener receives Spring Message/payload.
- [ ] Distinguish record offset, consumer position, and committed offset.
- [ ] Log received, processing completed, failed, and recovered separately.
- [ ] Do not log success before business work finishes.
- [ ] Do not claim Kafka transaction committed from the end of the listener method.
- [ ] Log producer topic/partition/offset from RecordMetadata after acknowledgement.
- [ ] Keep current and original coordinates separate in retry/DLT.
- [ ] Use MDC with cleanup in finally/try-with-resources.
- [ ] Use context propagation if async tasks need correlation.
- [ ] Keep structured log field names and types consistent.
- [ ] Do not log payloads, secrets, or PII by default.
- [ ] Do not use offset/event ID as metric labels.
- [ ] Keep log volume within budget while preserving critical errors.
- [ ] Maintain runbooks using coordinates to find records and cross-check committed offsets.
- [ ] Check retention, compaction, and transaction isolation when records are missing.

## 43. References

- [Apache Kafka — ConsumerRecord API](https://kafka.apache.org/40/javadoc/org/apache/kafka/clients/consumer/ConsumerRecord.html)
- [Apache Kafka — RecordMetadata API](https://kafka.apache.org/40/javadoc/org/apache/kafka/clients/producer/RecordMetadata.html)
- [Spring for Apache Kafka — Listener Annotation](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/listener-annotation.html)
- [Spring for Apache Kafka — Message Headers](https://docs.spring.io/spring-kafka/reference/kafka/headers.html)
- [Spring for Apache Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring for Apache Kafka — Sending Messages](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html)

**Conclusion:** Logging topic, partition, and offset provides a verifiable address for every Kafka record. In Spring Kafka, obtain metadata directly from `ConsumerRecord` or `KafkaHeaders`, write structured logs with listener/group/event context, and clearly distinguish record offset from committed group offset. On the producer side, log partition/offset only after receiving `RecordMetadata`; in retry/DLT flows, preserve both current and original coordinates. Combined with event IDs, trace context, error handling, and consumer lag, these logs help operators locate exact records, understand redeliveries, and track processing progress without logging entire payloads or guessing from log line order.
