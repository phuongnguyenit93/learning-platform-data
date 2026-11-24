# Idempotent producer in Kafka and Spring Kafka

An idempotent producer helps Kafka avoid writing a duplicate batch when the producer has to resend a request due to a timeout, connection loss, or unclear broker response. Kafka recognizes the resend using a producer ID and sequence number, so internal retries from the same producer do not create extra duplicate records in the log.

In Spring Kafka, KafkaTemplate uses a Kafka producer from ProducerFactory. Therefore, idempotence is configured on the Kafka producer client; it is not a separate listener deduplication mode or a special method on KafkaTemplate.

Keep in mind that an idempotent producer protects internal retries within the same producer session. It does not automatically eliminate two independent `send()` calls for the same event, does not deduplicate across multiple producer instances, and does not make database/API side effects exactly-once.

## 1. The duplicate problem on producer retry

Suppose a producer sends a batch to a broker:

1. The broker writes the batch to the log.
2. The broker sends an acknowledgment response.
3. The response is lost on the network.
4. The producer does not know whether the broker succeeded in writing.
5. The producer resends the batch due to a request timeout.

If the broker cannot recognize that this is the same send, the batch may be appended a second time. This is a duplicate caused by transport-layer retry.

```text
Producer                    Broker
   |                           |
   |------ batch A ----------->|
   |                           | append A
   |<----- response -----------X  response lost
   |                           |
   |------ retry batch A ----->|
   |                           | recognizes PID + sequence
   |<----- response -----------|
```

With idempotence, the broker tracks the producer's sequence per partition. When it receives a batch with an already recorded sequence, the broker recognizes it as a retry of the earlier batch and does not append another copy.

If idempotence is not enabled, the producer can still retry according to the retries configuration, but in the situation where a response is lost after the broker appends, the application risks receiving duplicates in the topic.

## 2. Producer ID and sequence number

Kafka uses two main pieces of information to identify a batch sent from a producer:

- **Producer ID (PID):** producer identifier assigned by Kafka when the producer initializes the idempotence mechanism.
- **Sequence number:** the producer's batch sequence number per topic-partition.

The producer attaches the PID and sequence number to the ProduceRequest. The broker stores sequence state per producer and partition. Upon receiving the next batch, the broker checks the sequence to detect a new batch, a repeated batch, or an invalid sequence.

Illustrative example:

| Partition | Producer ID | Batch sequence | Result |
|---|---:|---:|---|
| orders-0 | 71 | 0 | Write first batch |
| orders-0 | 71 | 1 | Write next batch |
| orders-0 | 71 | 1 | Recognize retry of already-written batch |
| orders-0 | 71 | 2 | Write new batch |
| orders-1 | 71 | 0 | Sequence is managed per partition |

The numbers in the table are for illustration only. Actual sequences are managed by Kafka at the protocol level; the application does not assign PIDs or sequence numbers manually.

Sequences are tracked separately for each topic-partition. A single producer can send to multiple partitions and maintain independent sequence progress on each partition.

## 3. Enabling an idempotent producer

The main property is enable.idempotence. When enabled, the Kafka producer uses PID and sequence numbers to prevent duplicates from internal retries.

Key configuration conditions:

- enable.idempotence=true.
- acks=all.
- retries greater than 0.
- max.in.flight.requests.per.connection not exceeding 5.

If idempotence is explicitly enabled while other properties conflict with the conditions above, the Kafka producer may refuse to initialize with a configuration error. Inspect the effective configuration rather than looking only at the YAML file.

Minimal configuration example:

```yaml
spring:
  kafka:
    producer:
      acks: all
      retries: 2147483647
      properties:
        "[enable.idempotence]": true
        "[max.in.flight.requests.per.connection]": 5
```

acks=all requires the broker to acknowledge according to ISR conditions. retries allows the producer to retry retriable errors. Idempotence combines with sequence tracking so the broker recognizes retries of the same batch.

## 4. Configuring with Spring Boot application.yml

Spring Boot binds producer properties to the Kafka client. Additional timeouts and backoff can be configured so retries stay within the publish SLA:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      acks: all
      retries: 2147483647
      properties:
        "[enable.idempotence]": true
        "[max.in.flight.requests.per.connection]": 5
        "[request.timeout.ms]": 30000
        "[delivery.timeout.ms]": 120000
        "[retry.backoff.ms]": 200
```

In the example:

- enable.idempotence=true enables the idempotent producer mechanism.
- acks=all satisfies idempotence's acknowledgment requirement.
- retries allows retrying when the Kafka client classifies an error as retriable.
- max.in.flight.requests.per.connection=5 is within the limit compatible with idempotence.
- request.timeout.ms limits how long to wait for a single request's response.
- delivery.timeout.ms limits the total delivery time of a record, including batching, requests, and retries.
- retry.backoff.ms sets the wait interval between retries.

Dotted Kafka keys are enclosed in square brackets so Spring Boot preserves the exact property name when binding the map. Property names and defaults should be verified against the Spring Boot/Kafka client version used by the project.

Modern Kafka clients usually enable idempotence by default if there are no conflicting configurations. However, explicit declaration makes operational intent easy to review and avoids depending on version defaults. Since Kafka 3.0, enable.idempotence defaults to true; in older clients, verify the corresponding default.

## 5. Configuring via Java ProducerFactory

If creating ProducerFactory manually, declare properties directly:

```java
@Configuration
public class KafkaProducerConfiguration {

    @Bean
    public ProducerFactory<String, OrderCreated> orderProducerFactory() {
        Map<String, Object> properties = new HashMap<>();
        properties.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
        properties.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
        properties.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, JsonSerializer.class);

        properties.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
        properties.put(ProducerConfig.ACKS_CONFIG, "all");
        properties.put(ProducerConfig.RETRIES_CONFIG, Integer.MAX_VALUE);
        properties.put(
                ProducerConfig.MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION,
                5);

        properties.put(ProducerConfig.REQUEST_TIMEOUT_MS_CONFIG, 30_000);
        properties.put(ProducerConfig.DELIVERY_TIMEOUT_MS_CONFIG, 120_000);

        return new DefaultKafkaProducerFactory<>(properties);
    }

    @Bean
    public KafkaTemplate<String, OrderCreated> orderKafkaTemplate(
            ProducerFactory<String, OrderCreated> orderProducerFactory) {
        return new KafkaTemplate<>(orderProducerFactory);
    }
}
```

When creating a factory manually, the application is responsible for providing bootstrap servers, serializers, security, and required producer properties. Do not assume a manually declared ProducerFactory automatically inherits all Spring Boot configurations.

If multiple KafkaTemplates use different ProducerFactories, each factory may have its own idempotence policy. Check the exact template that the publisher actually injects.

## 6. KafkaTemplate does not deduplicate by event ID

After enabling idempotence, the producer can prevent duplicates from retrying the same batch. However, the following two calls are two independent logical sends:

```java
kafkaTemplate.send("orders", "order-42", event);
kafkaTemplate.send("orders", "order-42", event);
```

The Kafka producer assigns the next sequence to the second send. The broker treats this as a valid new batch, even though the key and payload are identical. As a result, the topic may contain two records.

Idempotence does not read eventId, does not compare payloads, and does not know that two `send()` calls represent the same business action. A Kafka key is also not a deduplication key: the same key can appear in multiple valid records.

If business requirements demand preventing duplicate sends caused by application retries, an application-layer mechanism is needed, such as:

- A stable Event ID generated once and preserved across retries.
- The Outbox pattern to write events in the same business transaction.
- An Inbox/deduplication table on the consumer with a unique constraint on event ID.
- An Idempotent API on the downstream service.

## 7. Scope of idempotence guarantees

An idempotent producer protects internal retries within the same producer session. It is not a permanent unique lock for an event.

| Scenario | Handled by idempotent producer? | Notes |
|---|---|---|
| Kafka client retries the same batch due to timeout | Yes | Broker recognizes PID and sequence |
| Response lost after broker append | Yes | Retrying the same batch does not create another append |
| Application calls send() twice | No | Two independent sends have different sequences |
| Two producer instances send the same event | No | Each producer has its own PID/session |
| Application restarts and resends an old event | Not automatically | New producer session does not dedupe by event ID |
| Consumer finishes processing but crashes before committing offset | No | This is a duplicate at the consumer processing layer |
| Database commits successfully, but consumer has not committed Kafka offset | No | Requires an idempotent consumer or appropriate transaction/outbox |

Therefore, this should be accurately described as "exactly-once within producer retry scope", not end-to-end exactly-once for the entire system.

## 8. Idempotence and record ordering

Retries can alter ordering if multiple requests are in-flight. Suppose a producer sends batch A then batch B:

1. A encounters a temporary error.
2. B is processed successfully by the broker.
3. A is resent afterward.

Without idempotence and with multiple in-flight requests, B's records could be written before A's. This can make the record order in a partition differ from the order the producer sent them.

When idempotence is enabled, Kafka supports preserving order for up to five in-flight requests per connection. Thus, a max.in.flight.requests.per.connection value not exceeding 5 still allows taking advantage of pipelining while preserving ordering by producer sequence.

Example:

```yaml
spring:
  kafka:
    producer:
      properties:
        "[enable.idempotence]": true
        "[max.in.flight.requests.per.connection]": 5
```

Kafka only guarantees ordering within a single partition. Idempotence does not create global ordering across multiple partitions. If events of the same aggregate must be strictly ordered, use the same message key so they are routed to the same partition.

## 9. acks=all and min.insync.replicas

Idempotence requires acks=all, but replication settings must also be understood to evaluate data durability.

- acks=all requires the leader to wait for replicas in the ISR to satisfy write conditions.
- min.insync.replicas sets the minimum number of replicas required in the ISR for the broker to accept writes with acks=all.
- Replication factor determines how many replicas are configured for a partition.

For example, a topic has replication factor 3 and min.insync.replicas=2. If the ISR drops to one replica, the producer may receive NotEnoughReplicasException or a related error and retry within the delivery timeout limit.

Idempotence does not create replicas and does not replace durability configuration. If the broker/ISR does not recover before the delivery timeout, the future can still fail. Design replication factor, min ISR, and recovery SLAs together.

## 10. Idempotent producer is not a transactional producer

The two mechanisms are related, but their scopes differ:

| Mechanism | Main guarantee | Scope |
|---|---|---|
| Idempotent producer | Retrying the same batch does not create duplicates in the log | Producer session |
| Transactional producer | Writes multiple records/partitions and commits or aborts as one Kafka transaction | Multiple partitions/topics within a transaction |
| Consume-process-produce transaction | Combines output records and consumer offsets in a Kafka transaction | Consume-transform-produce flow |

A transactional producer uses idempotence; when transactional.id is configured, the Kafka producer automatically enables idempotence and requires the related conditions. However, enabling idempotence alone does not create transactions or combine consumer offsets with output records.

For example, if an application reads a record, sends output, and commits consumer offsets as separate operations, a crash in between can still create duplicates or break the link between input and output. To guarantee exactly-once for Kafka-to-Kafka processing, transactions and appropriate listener/container configurations are required.

Kafka transactions also do not automatically cover databases or HTTP APIs. Side effects outside Kafka still need outbox, inbox, idempotency keys, or a separate transaction coordination mechanism.

## 11. Producer restarts and new producer instances

Idempotence relies on a producer's PID and sequence state. When a producer closes and a new instance is created, the new instance may receive a new PID. It does not automatically know that an event resent by the application had already been successfully written by the old producer before the process stopped.

Example:

```text
Producer instance A
  -> sends event evt-100
  -> broker writes successfully
  -> application loses response / process stops

Producer instance B after restart
  -> application resends evt-100
  -> producer B treats this as a new send
  -> topic may get an additional evt-100 record
```

This is why a business event ID remains important even when idempotence is enabled. If a producer must resend an event after a restart without creating duplicate effects, the consumer or downstream needs to deduplicate by event ID.

A transactional producer with a stable transactional.id adds a producer epoch/fencing mechanism to manage producer sessions with transactional identity. This is part of transactional semantics, not business deduplication behavior of a standard idempotent producer.

## 12. Handling send results with KafkaTemplate

KafkaTemplate.send(...) returns a future. Internal retries happen inside the Kafka producer before the future completes:

```java
public CompletableFuture<SendResult<String, OrderCreated>> publish(
        OrderCreated event) {

    return kafkaTemplate.send(
            "orders.created.v1",
            event.orderId(),
            event);
}
```

Observing the final result:

```java
publish(event).whenComplete((result, exception) -> {
    if (exception != null) {
        log.error(
                "Publish failed: eventId={}",
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
```

Since Spring Kafka 3.0, send() returns CompletableFuture; older versions used ListenableFuture. send() can also throw synchronous exceptions before returning a future, such as serialization errors or a closed producer. Final delivery failures after a record is accepted by the producer are typically reported through the future.

Do not treat send() returning a future as proof that the broker wrote the record. Only when the future completes successfully does the application receive SendResult and RecordMetadata.

## 13. Retriable and non-retriable errors

Idempotence does not turn every error into a retriable error. The Kafka producer classifies errors based on the exception and client/broker state.

| Error group | Examples | Resolution direction |
|---|---|---|
| Transient errors | Network exception, request timeout, leader not available | Producer can retry within delivery timeout |
| ISR not satisfied | NotEnoughReplicasException | Can retry once ISR recovers |
| Serialization | Object cannot be serialized | Fix serializer/payload; broker retry will not help |
| Authorization | ACL denies writing to topic | Fix permissions; retry will not grant permission |
| Invalid topic/partition | Wrong metadata or topic configuration | Fix configuration/metadata |
| Record too large | Exceeds producer/broker/topic limit | Reduce payload or adjust limits accordingly |

The exact list of retriable errors depends on the Kafka client version and specific exception. Do not classify based only on message text; when needed, inspect the cause chain and the exception type returned by Kafka.

## 14. Conflicting configurations and producer initialization errors

When enable.idempotence=true, related properties must be compatible. Example:

```yaml
spring:
  kafka:
    producer:
      acks: 1
      properties:
        "[enable.idempotence]": true
```

This is a conflicting configuration because idempotence requires acks=all. The Kafka producer may throw ConfigException upon initialization.

Another example is setting max.in.flight.requests.per.connection greater than 5 while idempotence is enabled. Check:

- Whether any property is set in application.yml, profiles, or environment variables.
- Whether a custom ProducerFactory overrides Boot properties.
- Whether multiple KafkaTemplates use different factories.
- Whether the Kafka client version has different defaults or limits.

When configuring idempotence explicitly, declare acks, retries, and max.in.flight.requests.per.connection together so an environment profile does not accidentally disable this mechanism.

## 15. Inspecting actual producer configuration

You can inspect ProducerFactory configuration after Spring initializes the bean:

```java
@Autowired
private ProducerFactory<String, OrderCreated> producerFactory;

@Test
void shouldEnableIdempotence() {
    Map<String, Object> properties =
            producerFactory.getConfigurationProperties();

    assertThat(properties.get(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG))
            .isEqualTo(true);
    assertThat(properties.get(ProducerConfig.ACKS_CONFIG))
            .isEqualTo("all");
    assertThat(properties.get(ProducerConfig.RETRIES_CONFIG))
            .isEqualTo(Integer.MAX_VALUE);
    assertThat(properties.get(
            ProducerConfig.MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION))
            .isEqualTo(5);
}
```

Checking the configuration map helps detect properties overridden by profiles or custom factories. However, it does not yet prove the broker handled retries properly; integration tests against a Kafka broker are still required.

Note that data types in the map may be String, Integer, Boolean, or other numeric types depending on how they are configured. When writing assertions, normalize types or inspect via actual ProducerConfig/Producer per your dependencies.

## 16. Testing an idempotent producer

Thorough testing needs to verify both configuration and behavior:

1. Producer sends a record normally; the future completes successfully.
2. Producer encounters a network error or brief broker interruption after the request is sent; the client retries within delivery timeout.
3. Broker recovers; retrying the same batch does not create duplicates from transport retry.
4. Delivery timeout expires; the future completes exceptionally.
5. Application calls send() twice for the same event; verify these are two separate logical sends.
6. Producer restarts and the application replays an old event; verify idempotent consumer/deduplication handles the duplicate event ID if business requires it.
7. Conflicting configuration; producer fails fast instead of running with unintended semantics.

With Testcontainers or a dedicated test broker, broker restarts/network interruptions can be simulated. The "broker appended but response lost" scenario is hard to reproduce reliably; use fault injection/proxy or controlled integration tests rather than merely stopping brokers randomly.

Do not use fixed Thread.sleep calls to conclude there are no duplicates. Wait for futures, consumer receipt of records, and test conditions using polling with timeouts; use separate topics and event IDs per test.

## 17. An idempotent consumer is still necessary

Producer idempotence does not prevent a consumer from reprocessing a record when the offset has not been committed. Example:

1. Consumer reads event evt-100.
2. Consumer writes data to the database successfully.
3. JVM crashes before committing the Kafka offset.
4. After restart, Kafka redelivers evt-100.
5. Consumer may write the same database change a second time.

An idempotent consumer can store the processed eventId in the same database transaction as the business logic:

```sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
```

Upon receiving an event, the consumer writes event_id into the table with a unique constraint. If the ID already exists, the consumer knows the event was already processed and can skip repeating side effects. Writing the marker and updating business data must occur within the same database transaction to avoid partial states.

For Kafka-to-Kafka systems, Kafka transactions can combine output records and input offsets. For databases or APIs outside Kafka, appropriate idempotency/outbox/inbox must be designed.

## 18. Observing idempotent producers in production

Idempotence operates inside the producer client. Applications usually do not receive a separate callback per retry; instead, monitor producer metrics and final future outcomes.

Useful metrics:

- record-retry-rate: rate of retried batches.
- record-error-rate: rate of failed batches.
- record-send-rate: rate of record sends.
- request-latency-avg and request-latency-max: request latency.
- record-queue-time-avg: time records spend in the accumulator.
- requests-in-flight: number of requests awaiting responses.
- buffer-available-bytes: remaining available buffer capacity.

Exact metric names depend on the Kafka client version and metrics reporter. Combine metrics with publish failure logs, event IDs, and topic/partition/offset metadata; avoid logging sensitive payloads.

If the retry rate rises high, check broker latency, ISR, network, request timeout, and buffer pressure. Idempotence reduces retry duplicates but does not remove the underlying cause of retries or improve broker capacity.

## 19. Common errors

**Enabled idempotence but producer fails to initialize:** check whether acks, retries, and max.in.flight.requests.per.connection meet the required conditions.

**Still getting duplicate events:** determine whether duplicates come from internal retries, the application calling send multiple times, producer restarts, or consumer reprocessing. Idempotence only solves internal retries within a producer session.

**Thinking the same message key automatically deduplicates:** key determines partitioning/compaction semantics per topic configuration, not a key to drop duplicate records during log append.

**Thinking idempotence is end-to-end exactly-once:** distinguish producer retries, consumer offsets, transactions, and side effects outside Kafka.

**Setting max.in.flight.requests.per.connection too high:** configuration may conflict with idempotence. Keep it at most 5 when idempotence is enabled.

**Using acks=1 with idempotence:** producer may fail to initialize because idempotence requires acks=all.

**Increasing retries without increasing delivery timeout:** records can still time out on delivery before exhausting retry attempts.

**Calling KafkaTemplate.send() again inside an error callback:** this is a new send and can create duplicates; event ID and application-layer deduplication are needed.

**Testing only properties, not broker behavior:** valid configuration alone does not prove actual retry handling and duplicate suppression.

## 20. Production checklist

- Kafka client version supports idempotent producer and its default behavior is verified.
- enable.idempotence=true is explicitly configured when this guarantee is needed.
- acks=all, retries>0, and max.in.flight.requests.per.connection<=5.
- request.timeout.ms, delivery.timeout.ms, and linger.ms have a valid relationship.
- Topics have replication factor and min.insync.replicas matching durability requirements.
- Every KafkaTemplate uses the proper ProducerFactory with idempotence enabled.
- Producer retries are not confused with application retries.
- A stable Event ID is used when business requires dedup across restarts or multiple producers.
- Consumers have idempotency/inbox if database side effects can be invoked again.
- Kafka transactions are used when exactly-once is needed for consume-process-produce within Kafka.
- Broker interruptions, delivery timeouts, application resends, and producer restarts are tested.
- Retry rate, request latency, buffer pressure, and future failures are monitored.

An idempotent producer uses producer ID and sequence numbers so the broker recognizes retries of the same batch, avoiding duplicates from transport errors within a producer session. Enable this mechanism alongside acks=all, retries, and compatible in-flight limits. For duplicates from application resends, producer restarts, or consumer replays, event IDs, idempotent consumers, outbox/inbox, or Kafka transactions are still needed according to the exact guarantee scope required by the system.

## References

- [Apache Kafka – Producer Configs](https://kafka.apache.org/documentation/#producerconfigs_enable.idempotence)
- [Apache Kafka – Design: Message Delivery Semantics](https://kafka.apache.org/documentation/#semantics)
- [Spring for Apache Kafka – Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html)
