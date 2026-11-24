# enable.idempotence

## 1. Purpose of the Idempotent Producer

In a Spring Kafka system, a producer may have to resend records when encountering network errors, timeouts, or temporary broker unavailability. A subtle failure occurs when the broker already wrote the record, yet the acknowledgement was lost on its way back to the client. The producer cannot be sure whether the broker wrote it, so it must retry.

If every retry is treated by the broker as a new record, the same event can appear multiple times in the topic. This forces consumers to process duplicates and can cause repeated business side effects, such as creating two shipping requests or adding inventory twice.

The `enable.idempotence` property enables idempotence on the Kafka producer. This mechanism lets the broker recognize and deduplicate retries of the same batch sent by the same producer within the same producer session. The producer can retry when an acknowledgement is lost without producing extra entries in the log for that send.

In Spring Kafka, `KafkaTemplate` uses the underlying Kafka producer. Therefore, idempotence is configured on the Kafka producer created by `ProducerFactory`. Spring Kafka does not replace this mechanism with a separate deduplication layer.

## 2. How It Works Internally in Kafka

Kafka uses a producer ID (PID), producer epoch, and sequence number to identify a producer's send order.

When the producer initializes, the broker assigns a PID. For each partition the producer sends to, the client maintains a monotonically increasing sequence number. Every outgoing batch carries the producer identity and corresponding sequence information. The broker stores sequence state per producer and partition to identify new batches, duplicate batches, or out-of-order batches.

A typical retry flow:

1. The producer sends a batch with sequence number N to the partition leader.
2. The broker writes the batch to the log and updates sequence state.
3. The acknowledgement is lost due to a dropped network connection.
4. Having received no result, the producer retries the exact same batch with the same sequence information.
5. The broker recognizes the batch was already written and does not append another copy.
6. The producer receives a success result or continues error handling per retry policy.

```text
Spring application
       |
       | send(event)
       v
KafkaProducer
       |
       | PID + partition + sequence N
       v
Partition leader
       |
       | append batch N
       | update producer sequence state
       v
Kafka log
       |
       | acknowledgement lost
       v
KafkaProducer
       |
       | retry batch N with same sequence
       v
Partition leader
       |
       | recognize duplicate batch
       | do not append another copy
       v
KafkaProducer receives result
```

The key point is that the broker identifies a retry using the producer and batch metadata. The producer does not send a new event with a new sequence for each internal retry.

### 2.1. Producer ID and Sequence Number

- **Producer ID:** a producer identifier used by the broker to track write state.
- **Producer epoch:** the version/epoch of the producer ID, helping detect stale producers or invalid producer state. Epoch is also part of the fencing mechanism in transactional producer scenarios.
- **Sequence number:** the batch sequence number per partition. The broker uses it to check for new, duplicate, and out-of-order batches.

Sequence numbers are managed per partition, so idempotence protects against duplicate writes within a producer-partition scope. It does not establish a global ordering across multiple partitions.

### 2.2. Why Ordinary Retries Can Create Duplicates

Suppose a producer sends a record and the broker appends it to the log. If the response is lost, the producer only observes a timeout. When idempotence is disabled, a retry can be appended as a new record because the broker lacks enough information to recognize it as a repeated send of the same producer sequence.

With idempotence enabled, the retry retains the original batch's producer identity and sequence. The broker can determine that the batch has already been processed.

This mechanism protects retries at the Kafka producer layer. If the application calls `kafkaTemplate.send()` a second time as a new operation, the producer initiates a new send. Kafka does not automatically know whether those two sends share the same `orderId`, `paymentId`, or business event.

## 3. Related Configurations and Mandatory Requirements

When enabling idempotence, producer settings must be compatible:

| Property | Requirement when idempotence is enabled | Role |
|---|---|---|
| `enable.idempotence` | `true` | Enables producer deduplication mechanism |
| `acks` | `all` | Waits for acknowledgement from replicas currently in the ISR |
| `retries` | Greater than 0 | Allows the producer to retry retriable errors |
| `max.in.flight.requests.per.connection` | Less than or equal to 5 | Limits pending requests per connection to preserve ordering compatible with idempotence |

Modern Kafka clients validate the compatibility of these settings. If idempotence is enabled alongside conflicting values, the producer may refuse to initialize with a configuration error.

### 3.1. `acks=all`

`acks=all` requires the leader to wait for replicas currently in the ISR to acknowledge before returning success. It increases durability of acknowledged records, though it does not mean every originally configured replica must always respond.

For example, a topic has replication factor 3 and `min.insync.replicas=2`. While at least two replicas remain in the ISR, the producer can write with `acks=all`. If the ISR drops below the minimum threshold, the broker rejects writes rather than silently accepting a replication level below policy.

Idempotence and replication address two related but distinct concerns:

- Idempotence prevents internal retries from creating duplicate entries in the log.
- Replication together with `acks` and `min.insync.replicas` determines acknowledgement conditions and data protection level.

### 3.2. `retries` and `delivery.timeout.ms`

`retries` defines the ability to retry retriable errors. Setting a very large retry count does not mean the producer retries forever. `delivery.timeout.ms` caps the total time the producer spends trying to complete a send, including batch wait, request, and retry times.

A common configuration leaves retries high and uses `delivery.timeout.ms` to cap the maximum time the application waits for a result. Choose a deadline aligned with the event flow's latency SLO and what downstream systems can tolerate.

`request.timeout.ms` limits how long to wait for a single request response. According to Kafka guidelines, `delivery.timeout.ms` should be greater than or equal to the sum of `request.timeout.ms` and `linger.ms`.

### 3.3. `max.in.flight.requests.per.connection`

This is the number of produce requests that can await acknowledgement on a single connection. When idempotence is enabled, Kafka supports a maximum value of 5.

There is no need to set this value to 1 just to get idempotence. A value of 5 still allows the producer to keep multiple requests in flight and can improve throughput, while client and broker coordinate sequences to maintain proper ordering. A value of 1 can reduce concurrency and throughput if there is no specific requirement.

### 3.4. Defaults by Kafka Client Version

Starting in Kafka 3.0, `enable.idempotence` defaults to `true`. Older client versions have different defaults. Spring Boot manages the `kafka-clients` version via dependency management, so verify the actual client version used by the application before relying on defaults.

Declaring it explicitly makes the reliability intent clear to readers of the configuration and prevents dependency upgrades or changes from making default behavior unpredictable. Even when the client enables it by default, still verify related settings to ensure the producer genuinely initializes with idempotence.

## 4. Configuration in Spring Boot and Spring Kafka

In a Spring Boot application, the simplest approach is configuring producer properties in `application.yml` or `application.properties`. Spring Boot passes these values to the Kafka producer used by `DefaultKafkaProducerFactory`.

### 4.1. application.yml Example

```yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        "[enable.idempotence]": true
        "[retries]": 2147483647
        "[max.in.flight.requests.per.connection]": 5
        "[delivery.timeout.ms]": 120000
        "[request.timeout.ms]": 30000
        "[linger.ms]": 5
```

Kafka keys containing dots are placed in square brackets so Spring Boot preserves the exact key names when binding the `properties` map. Time values in the example are in milliseconds.

The same configuration can be expressed in `application.properties`:

```properties
spring.kafka.producer.acks=all
spring.kafka.producer.properties[enable.idempotence]=true
spring.kafka.producer.properties[retries]=2147483647
spring.kafka.producer.properties[max.in.flight.requests.per.connection]=5
spring.kafka.producer.properties[delivery.timeout.ms]=120000
spring.kafka.producer.properties[request.timeout.ms]=30000
spring.kafka.producer.properties[linger.ms]=5
```

The example sets `delivery.timeout.ms=120000`, `request.timeout.ms=30000`, and `linger.ms=5`. A 120-second delivery deadline is illustrative; systems with tighter latency budgets may need a shorter deadline. If changing `request.timeout.ms` or `linger.ms`, re-check the constraint among the deadlines.

`retries=2147483647` is a large value commonly used so the producer keeps retrying within the delivery timeout budget. It does not cause a send to hold resources indefinitely because `delivery.timeout.ms` still bounds total completion time.

### 4.2. Configuration in Java

If the application creates `ProducerFactory` manually, the corresponding properties can be set using `ProducerConfig`:

```java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.support.serializer.JsonSerializer;

@Bean
public ProducerFactory<String, OrderCreated> producerFactory() {
    Map<String, Object> props = new HashMap<>();

    props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
    props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
    props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, JsonSerializer.class);

    props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
    props.put(ProducerConfig.ACKS_CONFIG, "all");
    props.put(ProducerConfig.RETRIES_CONFIG, Integer.MAX_VALUE);
    props.put(
        ProducerConfig.MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION,
        5
    );

    props.put(ProducerConfig.DELIVERY_TIMEOUT_MS_CONFIG, 120_000);
    props.put(ProducerConfig.REQUEST_TIMEOUT_MS_CONFIG, 30_000);
    props.put(ProducerConfig.LINGER_MS_CONFIG, 5);

    return new DefaultKafkaProducerFactory<>(props);
}

@Bean
public KafkaTemplate<String, OrderCreated> kafkaTemplate(
        ProducerFactory<String, OrderCreated> producerFactory) {
    return new KafkaTemplate<>(producerFactory);
}
```

This is an example for when the application actively owns `ProducerFactory` configuration. If using Spring Boot auto-configuration, prefer configuring via `spring.kafka.producer.*` to avoid creating an unnecessary extra factory or accidentally omitting shared settings such as security, serializers, and metrics.

## 5. Sending Events via KafkaTemplate

When `KafkaTemplate` sends a record, the Kafka producer handles batching, requests, acknowledgements, and retries. The application receives the outcome asynchronously via a future.

Example with modern Spring Kafka, where `send()` returns `CompletableFuture`:

```java
import java.util.concurrent.CompletableFuture;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;
    private static final Logger log = LoggerFactory.getLogger(OrderEventPublisher.class);

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {

        return kafkaTemplate.send(
            "orders.created",
            event.orderId(),
            event
        );
    }
}
```

Send outcomes can be observed without blocking the calling thread:

```java
public void publishAndObserve(OrderCreated event) {
    kafkaTemplate.send("orders.created", event.orderId(), event)
        .whenComplete((result, exception) -> {
            if (exception != null) {
                log.error(
                    "Could not publish OrderCreated, orderId={}",
                    event.orderId(),
                    exception
                );
                return;
            }

            var metadata = result.getRecordMetadata();
            log.info(
                "Published OrderCreated, topic={}, partition={}, offset={}",
                metadata.topic(),
                metadata.partition(),
                metadata.offset()
            );
        });
}
```

A successfully completed future means the Kafka producer received a successful acknowledgement according to the producer configuration. It does not prove a consumer has received or finished processing the event. If the service's SLO measures business processing time, a separate SLI is needed on the consumer or target system.

Do not ignore exceptions in callbacks. Idempotence makes internal retries safer, yet the producer can still hit delivery timeout or encounter non-retriable errors. The application must record failures, decide whether to retry at the business layer, and ensure that retry logic does not create logical duplicates.

## 6. What Does Idempotence Protect Against and Where Are Its Limits?

Distinguish three layers:

| Scenario | Handled by idempotent producer? | Explanation |
|---|---|---|
| Broker appended batch but acknowledgement was lost; producer retries same batch | Yes | Broker recognizes the same PID and sequence |
| Producer retries batch on retriable error within the same producer session | Yes | Internal retry uses the corresponding sequence metadata |
| Application calls `send()` a second time for the same business event | No | This is a new send operation from the producer's perspective |
| Application restarts and replays events from an external source | Not automatically | A new producer may have a new PID and new sequence |
| Consumer reprocesses a record after crashing before committing offset | No | This is a consumer-side delivery/offset issue |
| Consumer writes DB successfully but offset commit fails | No | Kafka may redeliver the record; requires an idempotent consumer or appropriate transaction |
| Writing simultaneously to Kafka and an external DB | Not automatically | Idempotence does not create a distributed transaction between Kafka and DB |

### 6.1. Application-Layer Duplicates

For example, an API receives an order creation request. The API calls the Kafka producer, but times out before receiving the result. The client retries the API and the application emits the same event again. The second send is a new publish operation, not an internal Kafka producer batch retry. Idempotence cannot infer that two records carry the same business meaning.

Common mitigation approaches:

- Assign a stable business event ID, such as `eventId` or `orderId + eventVersion`.
- Use transactional outbox to store the event in the same transaction as business data changes, then relay the outbox to Kafka.
- On the consumer, record processed keys in an inbox/deduplication table with a unique constraint.
- Design update operations to be idempotent, such as versioned state updates instead of blind increments.

The business ID can live in headers or payload for consumer lookup. Do not put individual IDs into metric labels as cardinality will grow rapidly.

### 6.2. Consumer-Side Duplicates

Kafka consumers by default typically operate under at-least-once processing when offsets are committed after processing. If a consumer completes a side effect and crashes before committing the offset, the record may be redelivered upon restart.

An idempotent producer does not prevent this reprocessing. Consumers need their own strategy:

- Record processed event IDs using a unique key.
- Use a database transaction to write the side effect and mark the event as processed together.
- Choose an offset commit timing aligned with processing semantics.
- If side effects lie outside Kafka, design retries and deduplication at system boundaries.

## 7. Idempotence and Kafka Transactions

Idempotent producers and Kafka transactions are related, not synonymous.

Idempotence focuses on preventing duplicates from internal producer retries. Kafka transactions extend that capability so multiple sends to multiple partitions can be committed or aborted as one atomic unit. In consume-transform-produce flows, an application can include input record offsets in the same transaction as output records.

In Spring Kafka, transactions are configured through a transactional producer factory and a transaction ID prefix. Spring Boot configuration example:

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: order-service-${INSTANCE_ID}-
```

The prefix must distinguish active instances running in the same cluster so instances do not inadvertently share a transactional identity. Spring Kafka manages creating transactional producers based on this prefix.

Example of sending inside a transaction:

```java
kafkaTemplate.executeInTransaction(operations -> {
    operations.send("orders.validated", orderId, validatedEvent);
    operations.send("orders.audit", orderId, auditEvent);
    return true;
});
```

When the callback completes normally, the transaction commits; on an eligible exception, the transaction aborts. Consumers wishing to read only committed data must configure `isolation.level=read_committed`.

For consume-transform-produce flows, Spring Kafka can coordinate container transactions and producer transactions to include output sends and processed offsets in one transaction. Specific setup depends on Spring Kafka version and listener container configuration.

Transactions still only provide atomicity within Kafka's scope. If the callback also writes to a relational database, a Kafka transaction does not automatically roll back the DB transaction. An outbox, inbox, or another coordination pattern is needed for the Kafka-DB boundary.

## 8. Impact on Ordering and Throughput

Idempotence allows the producer to retry while preserving proper batch ordering within each partition. This matters when multiple requests are in flight and an older request must be retried.

Kafka ordering is guaranteed within a single partition. If two events share the same key and are routed by the partitioner to the same partition, consumers can read them in that partition's log order. There is no global order across different partitions.

When idempotence is enabled:

- Keep `max.in.flight.requests.per.connection` at 5 or less.
- No need to drop to 1 unless there is a specific ordering or workload reason.
- Choose a stable key so events requiring order land in the same partition.
- Monitor batching and latency when tuning `linger.ms`, `batch.size`, or concurrency.

Idempotence carries some overhead for managing sequences and producer state, yet it is generally appropriate for producers needing reliability. Actual throughput impact depends on client version, brokers, batch size, partition count, network, and workload. Do not assume enabling idempotence alone will drastically hurt throughput; benchmark on a representative workload.

## 9. Error Handling and Diagnostics

Idempotence reduces duplicate risk from retries, but it does not eliminate all producer errors. Errors still require monitoring and classification before deciding to retry at the application layer.

| Symptom or error | Possible meaning | Handling direction |
|---|---|---|
| Increasing retry rate | Slow broker responses, flaky network, or throttling | Inspect broker request latency, network, quotas, and ISR |
| Delivery timeout | Producer did not complete send within configured deadline | Inspect load, batching, brokers, request timeout, and latency SLO |
| NotEnoughReplicasException | ISR does not satisfy `min.insync.replicas` for the write | Inspect replicas, broker health, and replication |
| OutOfOrderSequenceException | Broker received a sequence mismatching expected state | Inspect producer/broker errors, producer lifecycle, and client-version exception handling |
| Buffer exhaustion or long send waits | Producer not draining buffer fast enough or broker falling behind | Inspect throughput, buffer memory, batching, and block times |
| Business event duplicates still appear | Application re-emitted a new event or consumer reprocessed | Inspect business ID, API retries, outbox, and consumer deduplication |

Do not automatically retry every exception infinitely. Some errors are retriable, while configuration or serialization errors require fixing the root cause. For sequence or producer state errors, follow the semantics of your Kafka client version and avoid continuing to use a producer that entered a fatal state.

### 9.1. Metrics to Monitor

The Kafka producer emits useful metrics such as:

| Metric | Question to answer |
|---|---|
| `record-retry-rate` / `record-retry-total` | How frequently is the producer retrying? |
| `record-error-rate` / `record-error-total` | How many record sends are failing? |
| `record-send-rate` / `record-send-total` | What is the current send throughput? |
| `request-latency-avg` and latency percentiles | How fast or slow is the broker responding to the producer? |
| `record-queue-time-avg` | How long do records wait in the producer buffer/batch? |
| `buffer-available-bytes` | How much producer buffer remains available? |
| `batch-size-avg` | How effectively is the producer batching? |
| `produce-throttle-time-avg` | How long are broker/quotas throttling the producer? |

Exact metric names and exposure depend on the Kafka client, JMX exporter, Micrometer, and Spring Kafka version. Verify which metrics are actually exported in your environment before writing alert rules.

A durable producer dashboard should combine:

- Publish success rate and p95/p99 publish latency.
- Retry rate and error rate.
- Buffer availability and record queue time.
- Broker request latency, quota throttling, and ISR health.
- Number of business events emitted vs. events completed by consumers.

A rising retry rate may not create duplicates when idempotence works properly, yet it still signals degrading connection or broker quality. Watching only duplicate counts can cause operations teams to miss latency and delivery timeout issues.

## 10. Verifying Configuration in the Runtime Environment

When deploying, confirm the producer actually runs with the intended configuration:

1. Identify the `kafka-clients` version the application runs with, not just the Spring Boot version.
2. Inspect the final effective properties passed to `ProducerFactory`, especially if the application has multiple factories or multiple `KafkaTemplate` instances.
3. Verify `enable.idempotence=true`, `acks=all`, `retries>0`, and `max.in.flight.requests.per.connection<=5`.
4. Check `delivery.timeout.ms` aligns with request timeout, linger, and latency budget.
5. Observe retries, errors, latency, and broker replication under representative load.
6. Test scenarios with dropped connections or lost acknowledgements in a test environment to verify internal retries do not create extra log entries for the same batch.
7. Test separately what happens when the application replays the same business event or the consumer reprocesses a record; these two scenarios require application-layer deduplication.

Do not log the entire producer configuration if it contains passwords, tokens, or credentials. When debugging, display only necessary properties and mask sensitive values.

## 11. Practical Example: Producer Sending OrderCreated

Suppose the Order Service emits an `OrderCreated` event to topic `orders.created`. The event uses `orderId` as its key so changes for the same order route consistently to one partition.

```java
public record OrderCreated(
    String eventId,
    String orderId,
    Instant createdAt
) {}
```

Publisher:

```java
@Service
public class OrderPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {

        return kafkaTemplate.send(
            "orders.created",
            event.orderId(),
            event
        );
    }
}
```

The producer is configured with idempotence. If the broker appends a batch but the acknowledgement is lost, the Kafka producer can retry the same batch and the broker deduplicates it using PID/sequence.

Suppose the API gateway resends an order creation request due to a timeout. If Order Service produces a new publish event for that repeated request, the new event gets a new sequence. The idempotent producer does not automatically recognize that the two events mean the same thing. Order Service needs an API idempotency key or DB transaction to avoid creating two orders; an outbox can ensure the event is emitted consistently after the order is saved.

On the fulfillment consumer side, the event ID can be stored in an inbox table with a unique constraint. When a record is redelivered after a consumer restart, the consumer checks processed IDs and avoids applying the business side effect a second time.

This example shows that an idempotent producer is a critical protection layer on the send path, while end-to-end reliability still requires coordinating producer, Kafka, consumer, and storage systems.

## 12. Common Mistakes

**Assuming idempotence means system-wide exactly-once.** Idempotence protects internal producer retries. It does not automatically coordinate transactions with a DB or prevent consumers from reprocessing records.

**Enabling idempotence with incompatible `acks`.** An idempotent producer requires `acks=all`. Let the Kafka client validate configuration at startup and check startup logs.

**Setting `max.in.flight.requests.per.connection` greater than 5.** This value is incompatible with idempotence. Use 5 or lower.

**Setting a high `retries` value and thinking the producer will try forever.** `delivery.timeout.ms` still caps total send duration. Choose timeouts based on SLO and error-handling policy.

**Retrying with a fresh send call when the first outcome is unknown.** That is a separate logical publish operation and can create business duplicates. Use business IDs, outbox, or application-layer deduplication.

**Relying on defaults without checking client version.** Idempotence defaults vary by Kafka client version. Inspect actual dependencies and configure explicitly.

**Ignoring errors thinking idempotence handles everything.** Producers can still hit timeouts, serialization errors, insufficient ISR, or fatal errors. Log and classify exceptions.

**Using idempotence to solve consumer-side duplicates.** Consumer redelivery stems from offsets and commit timing. Handle it with consumer idempotency or appropriate transactions.

## 13. Rollout Procedure for a Durable Producer

When introducing idempotence into a Spring Kafka service, follow this sequence:

1. Identify the Kafka client version and how the application constructs `ProducerFactory`.
2. Enable `enable.idempotence=true` on all producers requiring protection.
3. Set `acks=all`, `retries>0`, and `max.in.flight.requests.per.connection<=5`.
4. Choose `delivery.timeout.ms`, `request.timeout.ms`, and `linger.ms` aligned with the latency SLO.
5. Confirm topics have replication factor and `min.insync.replicas` matching durability requirements.
6. Monitor retries, errors, latency, buffers, and replication health.
7. Add business event IDs, outbox, or consumer deduplication for duplicates outside producer retry scope.
8. If atomic consume-transform-produce inside Kafka is needed, evaluate Kafka transactions and matching Spring Kafka configuration.
9. Document guarantee boundaries clearly in operational runbooks so developers do not confuse idempotent producer with end-to-end exactly-once.

## 14. Key Takeaways

`enable.idempotence=true` makes Kafka producer retries safer by attaching a PID and sequence number to batches. Brokers use per-partition producer state to recognize repeated sends and avoid appending duplicates from internal retries.

In Spring Kafka, this setting lives on the producer created by `ProducerFactory` and used by `KafkaTemplate`. To operate properly, the producer needs `acks=all`, `retries>0`, and `max.in.flight.requests.per.connection<=5`.

Idempotence is a core foundation for a durable producer. To protect business logic across the entire event flow, systems still need to manage business identity, consumer processing, offset commits, outbox/inbox, or Kafka transactions as required.

