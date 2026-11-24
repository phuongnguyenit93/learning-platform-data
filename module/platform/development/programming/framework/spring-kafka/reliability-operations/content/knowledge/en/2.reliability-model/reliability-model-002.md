# Producer Delivery Guarantees

In Spring Kafka, a producer delivery guarantee describes the level of certainty an application can achieve when sending a record to Kafka: whether a record can be lost, whether it can appear multiple times, and whether record ordering is preserved. These guarantees are formed by multiple cooperating layers: how the producer sends and retries, broker acknowledgement settings, topic replication, idempotence and transaction mechanisms, and how the application handles send results.

A successful send call from the application does not mean the consumer has processed the record. It only indicates that the producer received an acknowledgement according to its configured policy. To guarantee the entire business flow, you must consider the consumer, the database, and systems outside Kafka.

## 1. Record Send Flow and the Meaning of Acknowledgement

When the application calls KafkaTemplate.send(), Spring Kafka creates a ProducerRecord and hands it to the Apache Kafka producer. The producer serializes the key/value, determines the partition, batches records, and sends a request to the broker acting as the partition leader.

Overview of the flow:

~~~text
Application
   |
   | KafkaTemplate.send(record)
   v
Spring Kafka / KafkaProducer
   |
   | serialize, partition, batch
   v
Partition leader broker
   |
   | append record to log
   | replicate to replicas in ISR
   v
Acknowledgement per acks config
   |
   v
CompletableFuture completes / callback invoked
~~~

Producers typically send asynchronously. A send call may return before the broker acknowledges; the final result is exposed via a future or callback. Therefore, distinguish three moments:

1. Application called send: the record has been handed to the producer for processing.
2. Broker acknowledged: the producer received an acknowledgement satisfying the acks configuration.
3. Consumer processed: a consumer read the record and completed its business logic.

Producer delivery guarantees primarily govern the first two moments. They do not automatically guarantee the third.

### acks Values

The acks property determines how many broker acknowledgements the producer requires before considering a send successful.

| Value | What the producer waits for | Durability and risk |
|---|---|---|
| 0 | Does not wait for broker acknowledgement | Low latency, but the producer does not know if the broker received the record. Records can be lost without the application receiving a corresponding error. |
| 1 | Waits for the leader to write the record to its local log and acknowledge | If the leader fails before the record is replicated to other replicas, the record can be lost when a new replica is elected leader. |
| all or -1 | Waits for all replicas currently in the ISR to acknowledge | Stronger guarantee when combined with appropriate replication factor and min.insync.replicas. This is the typical choice for critical data. |

all does not mean waiting for every broker in the cluster. It means waiting for the replicas currently in the partition's In-Sync Replicas (ISR) at write time. The ISR is the set of replicas considered caught up with the leader according to Kafka's replication criteria.

For example, a topic has a replication factor of 3 and min.insync.replicas of 2. If all three replicas are in the ISR, a producer using acks=all waits for all three replicas in the ISR to acknowledge. If only two replicas remain in the ISR, writes can still succeed when both acknowledge. If the ISR drops below two, the broker rejects write requests to avoid accepting a write with lower replication than the minimum policy.

Therefore, acks=all must be configured together with min.insync.replicas. Setting acks=all alone on a topic with a low replication factor or improper min.insync.replicas does not achieve the desired durability.

## 2. Three Delivery Guarantee Models

The terms at-most-once, at-least-once, and exactly-once describe trade-offs regarding record loss and duplicate records. They are not three single configuration values. Actual guarantees depend on the producer, broker, application, and business scope.

| Guarantee type | Can records be lost? | Can duplicate records occur? | Common use cases |
|---|---|---|---|
| At-most-once | Yes | Not from producer retries | Prioritizing avoiding duplicate processing, accepting loss of some events |
| At-least-once | Minimized when retries and replication are configured properly | Possible | Prioritizing not missing events, accepting controlled duplicate processing |
| Exactly-once | Within a committed Kafka transaction, records are published atomically | Not from producer retries within idempotence/transaction scope | Needing to write multiple records or combine consume-transform-produce atomically in Kafka |

### 2.1. At-most-once

At-most-once means a record is sent at most once according to application logic. If sending fails or the outcome is uncertain, the application does not resend. This avoids retries creating duplicates, at the cost of possible record loss.

A configuration that does not wait for acknowledgements such as acks=0 can reduce wait time, but the producer also lacks reliable confirmation that the broker wrote the record. At-most-once at the application level usually comes from a policy of not retrying after a send attempt, rather than a single configuration flag.

For example, an application sends a low-value telemetry event. If the network drops right during the send, the application ignores that event and moves on. The system avoids duplicate sends while accepting a missing data sample.

At-most-once is appropriate when:

- Data can be lost without serious business inaccuracies.
- Speed and latency matter more than completeness.
- A duplicate record has worse consequences than a missed record.

Do not choose this approach for payments, order creation, balance changes, or auditable events.

### 2.2. At-least-once

At-least-once aims to ensure a record is written successfully at least once. The producer retries recoverable errors, and the broker acknowledges according to the acks policy. If the broker wrote the record but the acknowledgement was lost on the way back to the producer, the producer may not know whether the previous write succeeded. When resending, the broker may store an extra copy if idempotence is not enabled.

For example:

1. Producer sends an OrderCreated event.
2. The leader writes the record and replicas in the ISR also receive it.
3. The broker sends an acknowledgement, but the connection drops before the producer receives it.
4. The producer treats the send as unsuccessful and retries.
5. Without producer idempotence, the same business event can appear twice in the log.

At-least-once is a practical choice for many business systems because it prioritizes not dropping events. To control duplicates, the application should provide a stable event ID and the consumer should process idempotently. For instance, the consumer stores processed event IDs in the same transaction as business data changes; if it receives the same event ID again, it does not apply the change a second time.

Producer retries help recover from transient errors, but cannot turn a permanently failed send into a success. When record delivery times out or encounters a non-retriable error, the application still needs to record the failure and decide the next steps.

### 2.3. Exactly-once

Exactly-once must be interpreted within a specific scope. Kafka supports two related mechanisms:

- Idempotent producer: prevents duplicates caused by the producer retrying the same send within a producer session.
- Transactional producer: writes a group of records transactionally; records are either committed together or aborted together. A transaction can also include consumer offsets in a consume-transform-produce flow.

Idempotence and transactions do not automatically prevent an application from calling send twice for the same business event. If an application receives an HTTP request twice and intentionally creates two new ProducerRecords, Kafka sees them as two distinct sends. To deduplicate at the business level, you still need an event ID, idempotency key, or application-layer checks.

Exactly-once processing in Kafka typically means processing results are published exactly once within the scope of topics and offsets participating in the same Kafka transaction. This guarantee does not automatically extend to databases, emails, payment APIs, or external systems outside Kafka.

## 3. Idempotent Producer

When idempotence is enabled, Kafka assigns a producer ID and sequence numbers to batches per partition. Brokers use this metadata to detect and deduplicate retries from the same producer. This handles situations where an acknowledgement is lost and the producer has to resend a batch.

With modern Kafka clients, idempotence is supported directly. You should set enable.idempotence=true explicitly so the configuration clearly expresses the reliability requirement and avoids accidentally disabling the feature when other parameters change.

Configuration conditions to keep in mind:

- acks must be all.
- retries must be greater than 0; in practice, it is usually set to allow the producer to retry throughout the entire delivery timeout.
- max.in.flight.requests.per.connection must not exceed 5 with idempotence.
- Do not set conflicting values that cause the Kafka client to disable idempotence.

Kafka client 3.x enables idempotence by default in many standard configurations, yet declaring it explicitly helps readers recognize it as a reliability requirement rather than an accidental value.

Idempotence protects retries inside the Kafka producer. It does not protect against the following cases:

- The application restarts and resends the same business event as a new ProducerRecord.
- A client request is processed twice.
- The application retries manually by calling KafkaTemplate.send() again after the future reports an error.
- Two independent service instances both emit the same event.
- The consumer applies a side effect twice after rereading a record.

For those cases, generate a stable event ID at the business boundary and design the consumer to handle receiving the same event multiple times without corrupting data.

## 4. Retries, Timeouts, and Record Ordering

Retries are a mechanism for recovering from transient failures, such as a partition leader undergoing election or a brief network interruption. The producer does not retry indefinitely under all conditions: records have a delivery deadline, and some errors cannot be fixed by retrying, such as serialization errors or invalid configuration.

Related settings include:

| Property | Role |
|---|---|
| retries | Number of times the producer retries retriable errors. |
| request.timeout.ms | Time to wait for a response to a single request from the broker. |
| delivery.timeout.ms | Upper bound on total time the producer tries to deliver a record, including batching wait, requests, and retries. |
| max.in.flight.requests.per.connection | Number of unacknowledged requests the producer can send on a single connection. |
| linger.ms | Time the producer waits for more records to form a batch, which can improve throughput at the cost of some added latency. |

delivery.timeout.ms must be sufficiently larger than request.timeout.ms and linger.ms. If the delivery deadline is too short, records may expire before the producer can recover from a brief broker incident. If set too high, the application must accept slower failure detection.

Ordering is guaranteed within a partition. Kafka does not provide global ordering across partitions. If events for the same order must stay in sequence, use the order ID as the key so they are routed to the same partition.

When idempotence is disabled, multiple in-flight requests combined with retries can cause record ordering to change in certain failure scenarios. Enabling idempotence and keeping max.in.flight.requests.per.connection within the supported limit helps the producer preserve per-partition ordering even during retries.

Do not habitually set max.in.flight to 1 if idempotence is enabled and the client supports values up to 5. A value of 1 can reduce throughput; choose based on ordering requirements and load test measurements.

## 5. Producer Configuration in Spring Boot and Spring Kafka

The example below shows a producer configuration that prioritizes durability, enables idempotence, and allows retries within the delivery timeout window. Timeout values should be tuned according to latency, broker recovery time, and system SLOs.

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      retries: 2147483647
      properties:
        enable.idempotence: true
        max.in.flight.requests.per.connection: 5
        request.timeout.ms: 30000
        delivery.timeout.ms: 120000
        linger.ms: 5
~~~

In this example:

- acks=all requires acknowledgement from replicas currently in the ISR.
- enable.idempotence=true prevents duplicates generated by retries from the same producer.
- retries allows the client to keep retrying recoverable errors; delivery.timeout.ms still caps the total delivery duration.
- max.in.flight.requests.per.connection=5 allows multiple concurrent requests within the limit compatible with idempotence.
- request.timeout.ms caps how long to wait for one request; delivery.timeout.ms sets the overall cap.
- linger.ms gives the producer a short window to batch records. It can be set to 0 if latency is prioritized over waiting for batching.

Property names can be declared in application.yml or application.properties. If using application.properties, the corresponding properties look like spring.kafka.producer.acks=all and spring.kafka.producer.properties.enable.idempotence=true.

### Broker and Topic Configuration

For acks=all to provide meaningful durability, the topic needs a sufficient replication factor and min.insync.replicas set to the minimum number of replicas the system wants to maintain.

Example creating a topic with three replicas and requiring at least two replicas in the ISR:

~~~bash
kafka-topics.sh --bootstrap-server kafka-1:9092 \
  --create \
  --topic orders \
  --partitions 12 \
  --replication-factor 3 \
  --config min.insync.replicas=2
~~~

With the configuration above, a producer using acks=all can write when at least two replicas remain in the ISR. If only one replica remains in the ISR, the broker rejects writes until replication recovers or the policy is intentionally changed.

Operational points to consider:

- Replication factor determines the number of copies of a partition. RF=3 is a common starting point for critical data, though topology and resource budget must be considered.
- min.insync.replicas sets the minimum ISR threshold that allows writes when producers use acks=all.
- Monitor under-replicated partitions and ISR shrinks to spot risks of reduced fault tolerance.
- Consider disabling unclean leader election for topics requiring high durability. Electing a replica outside the ISR can lose previously acknowledged records.
- Replication within the same cluster does not replace backups, disaster recovery, or replicas in another geographic region.

If a topic already exists, verify the actual topic configuration rather than relying solely on broker defaults.

## 6. Sending Records and Handling Results with KafkaTemplate

In Spring Kafka 3.x, KafkaTemplate.send() returns a CompletableFuture<SendResult<K, V>>. The application should observe the future to know the send outcome, log errors, and extract metadata on success.

~~~java
@Service
public class OrderEventPublisher {

    private static final Logger log =
            LoggerFactory.getLogger(OrderEventPublisher.class);

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {

        return kafkaTemplate
                .send("orders", event.orderId(), event)
                .whenComplete((result, exception) -> {
                    if (exception != null) {
                        log.error(
                                "Cannot publish OrderCreated, eventId={}",
                                event.eventId(),
                                exception);
                        return;
                    }

                    RecordMetadata metadata = result.getRecordMetadata();
                    log.info(
                            "Published eventId={} topic={} partition={} offset={}",
                            event.eventId(),
                            metadata.topic(),
                            metadata.partition(),
                            metadata.offset());
                });
    }
}
~~~

When the future completes normally, the producer has received an acknowledgement according to the acks configuration. RecordMetadata provides the topic, partition, offset, and timestamp associated with the record. The offset helps trace the record's position in the partition, but does not prove that a consumer has processed it.

When the future completes exceptionally, log the error along with the event ID and enough business context to investigate. Do not swallow exceptions or log only a generic message, because during a broker incident the system will struggle to distinguish transient errors, configuration errors, and data errors.

Callbacks should be brief. Avoid performing blocking operations or slow API calls directly inside the callback because it may run on the producer's completion thread. If further processing is needed, offload the work to an executor or an appropriate internal queue.

There is no need to call flush after every send. Frequent flushing degrades batching efficiency and throughput. Let the producer manage batching normally; during application shutdown, allow the producer to close gracefully so pending records have a chance to finish within the shutdown timeout.

With Spring Kafka 2.x, send typically returns a ListenableFuture instead of a CompletableFuture. Use callback APIs matching your running Spring Kafka version; do not copy CompletableFuture examples into older project versions without checking API signatures.

### When to Wait Synchronously?

In some special flows, the application must proceed only after the broker has acknowledged the record. You can wait on the future with a timeout, though doing so blocks the calling thread and increases latency:

~~~java
SendResult<String, OrderCreated> result =
        kafkaTemplate.send("orders", event.orderId(), event)
                .get(5, TimeUnit.SECONDS);
~~~

You must handle InterruptedException, ExecutionException, and TimeoutException. If the application times out while waiting, the broker state may be ambiguous: the record might not have been written, or the broker wrote it but the response did not arrive in time. Immediately resending a new record can create a business duplicate. If application-level retries are needed, use a stable event ID and idempotency mechanisms.

## 7. Transactional Producer in Spring Kafka

Idempotence handles retries for an individual producer. Transactions extend guarantees to a group of send operations: records belonging to a transaction are committed together or remain invisible to consumers reading with read_committed.

Transactions are useful when a single business operation must publish multiple related records. For example, when creating an order, the application needs to write OrderCreated to the orders topic and OrderAuditCreated to the order-audit topic. If both records must appear together or neither should appear, send them within a Kafka transaction.

To enable transactions for a Spring Kafka producer, configure a transaction ID prefix. Each concurrently running application instance must have its own prefix to avoid transactional ID conflicts:

~~~yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: orders-node-a-
      acks: all
      properties:
        enable.idempotence: true
~~~

The prefix orders-node-a- only illustrates a single instance. In a multi-replica environment, derive the prefix from a unique instance identifier that remains stable for that instance's lifetime. Spring Kafka uses this prefix to generate transactional IDs for producers.

You can use KafkaTemplate.executeInTransaction() to group send calls into one transaction:

~~~java
kafkaTemplate.executeInTransaction(operations -> {
    operations.send("orders", event.orderId(), event);
    operations.send("order-audit", event.orderId(), auditEvent);
    return null;
});
~~~

When the callback completes normally, the transaction is committed. If the callback throws an exception, the transaction is aborted. Consumers that want to see only committed records must set isolation.level=read_committed. Consumers using read_uncommitted can read records belonging to uncommitted or aborted transactions.

### Consume-transform-produce

An important case is when a consumer reads a record, processes it, sends a result record to another topic, and commits the offset. If the offset is committed separately before the output is written, the application can lose results on a crash. If the output is written first but the offset is not committed, the input record can be reprocessed and produce duplicate output.

Spring Kafka supports Kafka transactions for consume-transform-produce flows. When the listener container is configured with a Kafka transaction manager, the container can coordinate sending outputs and committing input offsets in the same transaction. Downstream consumers read only committed outputs by setting isolation.level=read_committed. Exact configuration must match your Spring Kafka version and how the application manages transactions.

Kafka transactions only cover data and offsets inside Kafka. If the listener also updates a database or calls an external system, a Kafka transaction does not automatically commit or roll back those side effects. Do not call a payment API and assume it will roll back if the Kafka transaction aborts.

### Transactions with a Database: Transactional Outbox

Business logic often writes to a database and emits a Kafka event. Those two systems do not share an ACID transaction by default. If the database write succeeds but sending to Kafka fails, database state and events diverge. If sending to Kafka succeeds but the database rolls back, consumers receive an event for a change that does not exist.

Transactional outbox solves this dual-write problem as follows:

1. Within a single database transaction, update business data and insert a record into an outbox table.
2. A publisher or CDC connector reads outbox records and publishes them to Kafka.
3. Track published status and use event IDs to handle redelivery safely.
4. Consumers process idempotently to tolerate events being forwarded multiple times.

The outbox provides atomicity between business changes and the intent to emit an event in the database. Moving outbox records to Kafka still requires appropriate retries and deduplication.

## 8. Distinguishing Producer Retries and Application Retries

Two layers of retries are frequently confused:

| Retry type | Who performs it? | Characteristics |
|---|---|---|
| Producer retry | Kafka producer | Retries requests on retriable errors, using the same producer ID and sequence numbers when idempotence is enabled. |
| Application retry | Business code or error-handling layer | Calls send again, typically creating a new send; can create duplicate records if the previous send was actually written by the broker. |

Do not write callbacks that automatically call KafkaTemplate.send() indefinitely whenever a future fails. That can create an uncontrolled loop, increase broker load, and publish multiple copies of the same event.

An error-handling policy should classify failures:

- Transient errors: broker unavailable, leader election, or network errors. First let the producer retry within the delivery timeout.
- Data errors: serialization or invalid records. Fix the data or route to an error-handling flow; retrying the same data usually does not help.
- Authentication or authorization errors: check credentials and ACLs; continuous retries will not fix a misconfiguration.
- Delivery timeout exceeded: record the unconfirmed event and hand off to a controlled recovery workflow. Account for the possibility that the broker outcome is ambiguous.

If you must retry at the application layer, persist the event ID and payload in durable storage, use bounded backoff, cap the number of attempts, and establish a procedure for unsendable events. Design consumers to accept the same event ID multiple times without reapplying business effects.

## 9. Choosing Configuration by Business Requirements

Not every topic needs the same guarantee level. Configuration can be chosen based on the consequences of data loss or duplication:

| Data type | Configuration direction | Notes |
|---|---|---|
| Sampling-tolerant telemetry or metrics | Lower acks or dropping some records may be acceptable | Apply only when data loss is explicitly accepted. |
| Business event logs | acks=all, proper replication, idempotence enabled | Consumers must handle event IDs to tolerate application-level replays. |
| Orders, payments, balances | acks=all, proper min.insync.replicas, idempotence; transactions if atomicity across multiple Kafka records is required | Also design idempotency keys, outbox, and control external side effects outside Kafka. |
| Consume-transform-produce flows | Kafka transactions covering output and offsets | Downstream consumers use read_committed. |

Reliability also has a cost. acks=all and replication increase inter-broker data transfers; transactions add a commit step; large timeouts can delay failure detection. Measure throughput, p95/p99 latency, retry rates, and broker recovery times in an environment close to production.

## 10. Observability and Operations

A producer can still return errors even while brokers are healthy, for example due to serialization, full buffers, ACLs, or stale metadata. Conversely, a high send success rate is not enough to prove data has been processed by consumers. You must monitor producers, brokers, and consumers together.

Useful producer metrics:

- Record send rate and byte rate: rate and volume of records sent.
- Record error rate: rate of failed sends.
- Record retry rate: how often the producer has to retry.
- Request latency: time for brokers to respond to requests.
- Record queue time: time records sit in the producer before being sent.
- Buffer pool wait time: time waiting for buffer memory when the producer is under pressure.
- Batch size and compression rate: batching efficiency and compression effectiveness.

On the broker and topic side, monitor under-replicated partitions, offline partitions, ISR shrinks, request handler saturation, and disk capacity. When the ISR shrinks frequently, acks=all can increase write errors as brokers reject requests when the ISR count falls below min.insync.replicas.

Application logs should include event ID, topic, key, partition, and offset on successful sends. On failures, log the exception type, retry count if available, and necessary correlation info. Avoid logging full sensitive payloads.

During shutdown, configure sufficient graceful shutdown time so the producer can close and process buffered records. Do not terminate the process right after asynchronous sends unless the application has a mechanism ensuring pending sends complete or are persisted for recovery.

## 11. Common Misconceptions

**acks=all means every broker has a copy.** False. The producer waits for replicas in the ISR, not all brokers in the cluster. Replication factor and min.insync.replicas determine replica layout and minimum ISR thresholds.

**enable.idempotence=true prevents all duplicate events.** False. It removes duplicates from retries by the same producer. Two independent send calls for the same event can still produce two records.

**KafkaTemplate.send() returning means the record is stored.** False. send returns a future before the final outcome is known. You must observe the future or callback.

**A successful future means the consumer finished processing.** False. The future reflects broker acknowledgement per acks. Consumers might not be running, might be failing, or might be lagging.

**Kafka transactions roll back the database alongside Kafka.** False. Kafka transactions only manage operations inside the Kafka transaction. Use transactional outbox or an appropriate coordination design when a database is involved.

**More retries always make the system more reliable.** False. Retries cannot fix data errors, ACLs, or misconfigurations. Retries without bounds and backoff can worsen incidents. Producer retries also do not replace durable application-level recovery workflows.

**Kafka guarantees ordering across all partitions.** False. Ordering is maintained within each partition. Choose an appropriate key so records needing ordering go to the same partition.

## 12. Design Guidelines

When designing a producer for a new topic, determine the consequences of record loss and duplicate records upfront. From there, choose the delivery guarantee and matching broker configuration.

A common starting configuration for business events is:

1. Topic has a replication factor appropriate for the topology, commonly starting with RF=3.
2. min.insync.replicas is set to the minimum number of replicas acceptable to the business.
3. Producer uses acks=all and enable.idempotence=true.
4. delivery.timeout.ms and request.timeout.ms align with SLOs and recovery times.
5. Records carry a stable key to preserve ordering within the same business entity.
6. Application observes KafkaTemplate.send() results and logs by event ID.
7. Consumers implement idempotent processing to tolerate replays.
8. If committing multiple Kafka records or combining outputs with offsets is required, use Kafka transactions.
9. If writing to a database and emitting events is required, use transactional outbox or a dual-write solution with equivalent guarantees.
10. Monitor retries, send errors, ISR, and replication health in production.

Good delivery guarantees are the result of consistent configuration from application to broker and how business logic handles records once received. Clearly document the guarantee scope in system docs: what the producer guarantees, how consumers deduplicate, which operations transactions cover, and when recovery workflows apply. Precise wording avoids the misconception that a single producer parameter can guarantee an entire business workflow.
