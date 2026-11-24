# Durability and Acknowledgements

The producer is responsible for sending records to Kafka brokers. A successful send call must be understood accurately: to what level did the broker accept the record, which replicas copied the record, and does the producer know the outcome for certain if the network is disrupted. In Kafka, the **acks** property determines the acknowledgement level the producer waits for from the broker.

In Spring Kafka, these options are configured on the underlying Kafka Producer beneath KafkaTemplate. Choosing acks, replication factor, and min.insync.replicas together helps balance data durability, write availability, and latency. Producer retries and idempotence further handle transient failures and prevent duplicate records caused by internal producer retries.

## Learning objectives

After this lesson, you can:

- Distinguish acks=0, acks=1, and acks=all.
- Explain the relationship between acknowledgements, leader/follower replicas, and ISR.
- Choose replication factor and min.insync.replicas matching the criticality of the data.
- Configure producer acknowledgements in Spring Boot and ProducerFactory.
- Handle asynchronous results from KafkaTemplate.send().
- Understand retries, timeouts, and situations where the producer is uncertain whether the broker wrote the record.
- Explain producer idempotence, record ordering, and the boundaries of Kafka transactions.
- Test and monitor send errors, retries, latency, and replica health.

## 1. What problem do acknowledgements solve?

The producer sends a record to the partition's leader. The broker can respond immediately, respond after the leader accepts the record, or wait for in-sync replicas to acknowledge. This waiting level is controlled by acks.

For example, a producer sends an OrderCreated event to partition 2:

~~~text
Producer
   |
   |  produce record
   v
Partition 2 - Leader
   |
   +----> Follower replica 1
   |
   +----> Follower replica 2
   |
   v
Produce response per acks configuration
~~~

Acknowledgements tell the producer how far the broker processed the write request. They do not confirm that a consumer has read the record, a listener has executed, or database business logic has completed.

Three properties must be kept distinct:

| Property | Question answered |
|---|---|
| acks | What level of broker acknowledgement must the producer wait for? |
| Replication factor and ISR | How many synchronized copies does the partition maintain to protect data? |
| Consumer offset | How far has the consumer group recorded its next read position? |

No single acks value in isolation guarantees that the entire business flow loses no data or produces no duplicates. You must examine topic/broker, producer, consumer, and target system configurations together.

## 2. Three acknowledgement levels

### acks=0: do not wait for acknowledgement

The producer sends the record without waiting for the broker to return an acknowledgement response.

~~~text
Producer  -------- record -------->  Broker
Producer  <--- continue sending ----
                 do not wait for ack
~~~

Characteristics:

- Low producer-side latency because it does not wait for broker responses.
- The producer does not know for certain whether the broker received and wrote the record.
- Broker errors after sending may not be fully observed by the producer.
- Not suitable for data requiring high reliability.

You can consider acks=0 for very high-frequency telemetry data where loss is acceptable and separate aggregation/compensation mechanisms exist. Do not use it for payment commands, order states, or critical business events just to shave off a few milliseconds.

### acks=1: leader acknowledges

The producer waits for the leader to acknowledge after the leader receives and appends the record to its local log. The producer does not wait for followers to confirm they have replicated the record.

~~~text
Producer  ---- record ---->  Leader
Producer  <--- ack --------  Leader

                           Follower 1 (may not have replicated yet)
                           Follower 2 (may not have replicated yet)
~~~

Advantages:

- Latency is usually lower than acks=all.
- The producer knows the leader received the record and responded with success.

Risks:

- If the leader fails after acknowledging but before followers replicate the record, the new leader may lack that record.
- If an out-of-ISR replica is permitted to become leader, data-loss risk can be even higher.

acks=1 can fit when the application accepts a certain level of data-loss risk and needs to balance latency with durability. For critical events, carefully evaluate the chance of losing records during the incomplete replication window.

### acks=all or acks=-1: wait for ISR acknowledgement

With acks=all, the producer waits for all replicas currently in the ISR to acknowledge the record. The ISR (in-sync replicas) is the set of replicas keeping up with the leader according to Kafka's synchronization criteria.

~~~text
Producer  ---- record ---->  Leader
                               |
                 +-------------+-------------+
                 |                           |
                 v                           v
             Follower 1                  Follower 2
                 |                           |
                 +------ replicated --------+
                               |
Producer  <------ ack=all ------+
~~~

Advantages:

- Increases the likelihood of retaining records when the leader experiences an outage.
- Reduces the risk of records existing only on the leader and being lost during a leader change.
- Suitable for business data requiring high durability when paired with appropriate min.insync.replicas and replication factor.

Trade-offs:

- Write latency may be higher because it waits for replicas in the ISR.
- If the number of replicas in the ISR drops below the minimum threshold, the broker rejects writes rather than downgrading the acknowledgement level.
- A cluster experiencing replica issues may lose write availability until the ISR recovers.

acks=all is the standard choice for critical producers, though actual protection depends on how many replicas are currently in the ISR and the leader election policy.

## 3. Replication factor, ISR, and min.insync.replicas

acks=all only provides the intended protection when the topic is configured with appropriate replication.

Suppose a topic has:

- replication.factor=3: each partition has one leader and two followers.
- min.insync.replicas=2: the broker requires at least two replicas remaining in the ISR to accept an acks=all write.

Illustrative states:

| Current ISR | Write with acks=all and min ISR = 2 |
|---|---|
| Leader + Follower 1 + Follower 2 | Accepted; waits for replicas in ISR to acknowledge |
| Leader + Follower 1 | Accepted; waits for these two replicas to acknowledge |
| Leader only | Write rejected because ISR is below the minimum threshold |
| No active leader | Cannot write until the partition has a valid leader |

min.insync.replicas does not create extra copies by itself. It is the minimum threshold for the broker to accept writes at acks=all. Replication factor defines the target number of copies; ISR indicates which replicas are currently caught up.

If you use replication factor 3 yet leave min.insync.replicas=1, when both followers drop out of the ISR, the lone leader can still accept acks=all writes. At that moment "all" merely means all replicas currently in the ISR (just the leader) acknowledged. Therefore, configure min.insync.replicas to express the true minimum number of replicas the system requires.

### Topic and broker configuration

You can set the threshold at the broker level as a default or override it per topic. Topic configuration example:

~~~properties
min.insync.replicas=2
~~~

Replication factor is not a topic setting changeable via alter config; it is chosen when creating the topic (or taken from the broker's default.replication.factor on default creation). min.insync.replicas can be configured at the broker or topic level per governance policy.

Example creating a topic with the Kafka CLI:

~~~bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create \
  --topic order-events \
  --partitions 6 \
  --replication-factor 3 \
  --config min.insync.replicas=2
~~~

Inspecting topic configuration:

~~~bash
bin/kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name order-events \
  --describe
~~~

Ensure enough brokers exist and replicas are properly distributed across brokers/failure domains. A topic with replication factor 3 on a cluster with only two brokers cannot achieve three independent replicas.

### When the ISR drops below the threshold

When the ISR falls below min.insync.replicas, the broker returns an error to producers sending with acks=all (such as NotEnoughReplicas or an error related to ISR replica count). The producer can retry per its configuration and timeout, yet retries cannot restore replicas on their own. Operations must resolve the broker, network, or replication lag issue.

This is a deliberate trade-off: the system rejects writes to uphold durability requirements. Applications must handle send errors, perform bounded retries per the delivery timeout, and alert when errors persist.

## 4. Acknowledgement does not mean disk flush

Kafka writes logs through the operating system's filesystem and page cache. Replica acknowledgement reflects that replicas received/appended the record per the replication protocol; do not interpret acks=all as a promise that every copy has fsynced data to physical storage media at response time.

Kafka relies on replication, log recovery, and broker storage mechanisms to achieve durability. If business requirements demand long-term storage guarantees or disaster recovery, also evaluate:

- Replication factor and replica placement across brokers/racks/availability zones.
- Clean leader election policy and behavior when multiple replicas are lost.
- Backups, snapshots, or suitable long-term storage mechanisms.
- Monitoring disk health, under-replicated partitions, and broker failures.

With clean leader election, Kafka prefers electing a new leader from the ISR to avoid discarding records acknowledged by in-sync replicas. Allowing unclean leader election can improve availability at the risk of losing records absent on the newly elected leader. Understand this trade-off thoroughly before changing broker settings.

## 5. Producer configuration in Spring Boot

Spring Boot lets you configure acknowledgements via spring.kafka.producer.acks. Additional producer properties can be set under spring.kafka.producer.properties.

Example for a producer requiring high durability:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        "[enable.idempotence]": true
        "[max.in.flight.requests.per.connection]": 5
        "[delivery.timeout.ms]": 120000
        "[request.timeout.ms]": 30000
~~~

Meaning:

- acks: all: wait for ISR acknowledgement.
- enable.idempotence: true: enable producer idempotence to eliminate duplicates from internal producer retries.
- max.in.flight.requests.per.connection: 5: cap uncompleted requests per connection; this value is compatible with producer idempotence in modern Kafka clients.
- delivery.timeout.ms: cap total time the producer tries to complete one send, including request waiting and retries.
- request.timeout.ms: time the producer waits for a response to a request sent to the broker.

This is a configuration example, not an optimal preset for every system. delivery.timeout.ms must be large enough relative to request timeout and batching/retry duration. If timeouts are too short, the producer may report failures before the cluster has time to recover.

If using an older Kafka client version, defaults and compatibility rules may differ. Check documentation matching the exact dependency version running.

## 6. Configuring via ProducerFactory

If creating ProducerFactory manually, you can declare properties via ProducerConfig:

~~~java
@Bean
public ProducerFactory<String, OrderEvent> orderProducerFactory() {
    Map<String, Object> props = new HashMap<>();

    props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
    props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class);
    props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            JsonSerializer.class);

    props.put(ProducerConfig.ACKS_CONFIG, "all");
    props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
    props.put(ProducerConfig.MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION, 5);
    props.put(ProducerConfig.REQUEST_TIMEOUT_MS_CONFIG, 30_000);
    props.put(ProducerConfig.DELIVERY_TIMEOUT_MS_CONFIG, 120_000);

    return new DefaultKafkaProducerFactory<>(props);
}
~~~

The example focuses on acknowledgement and producer reliability. Real applications need compatible serializer, type mapping, trusted package, and connection properties configured.

If the application has multiple ProducerFactory beans for different purposes or clusters, verify which factory KafkaTemplate injects. spring.kafka.producer settings do not automatically apply to a factory manually constructed from a standalone map unless the application passes those properties into the factory.

## 7. Sending records with KafkaTemplate and handling acknowledgements

KafkaTemplate.send() sends records asynchronously. In Spring Kafka 3.x, the method returns CompletableFuture<SendResult<K, V>>. The future completes when the producer receives the result per acks configuration or when the send fails.

Example:

~~~java
public void publishOrder(String orderId, OrderCreated event) {
    kafkaTemplate.send("order-events", orderId, event)
        .whenComplete((result, exception) -> {
            if (exception != null) {
                log.error("Cannot publish order {}", orderId, exception);
                return;
            }

            RecordMetadata metadata = result.getRecordMetadata();

            log.info(
                "Published order {} to partition {} at offset {}",
                orderId,
                metadata.partition(),
                metadata.offset()
            );
        });
}
~~~

On success, RecordMetadata provides topic, partition, offset, and details of the record accepted by the broker. This is valuable evidence for logging and observability.

On failure, the future completes with an exception. The application should classify the error, record the event ID, emit metrics, and apply appropriate retries. Do not ignore exceptions inside callbacks, as doing so can blind the system to send failures.

In Spring Kafka 2.x, older APIs may return ListenableFuture; check your library version before copying examples.

### Synchronous sending when truly necessary

You can wait for the result with get():

~~~java
SendResult<String, OrderCreated> result =
        kafkaTemplate.send("order-events", orderId, event)
                .get(10, TimeUnit.SECONDS);
~~~

This blocks the calling thread until sending completes or times out. It can be useful in administrative flows or tasks needing immediate confirmation, but should not be used indiscriminately on high-traffic request threads. Weigh throughput, timeouts, and exception handling.

### When is a send considered successful?

That depends on acks:

- With acks=0, the producer does not wait for broker acknowledgement.
- With acks=1, the producer receives acknowledgement from the leader.
- With acks=all, the producer receives acknowledgement from replicas in the ISR per the min ISR policy.

Consequently, a successful callback does not carry the same guarantee across different acks settings. When high durability is required, configure acks=all and verify min.insync.replicas on the broker/topic.

## 8. Retries, timeouts, and uncertain send outcomes

A producer can time out when the broker has already written the record yet the response fails to reach the producer. The producer cannot know for certain whether the request failed before writing or only failed on the return response path.

Example:

~~~text
Producer                     Broker
   |                            |
   | -------- record ---------->|
   |                            | append record
   |                            |
   |       response lost        |
   |                            |
   | ---- retry same request -->|
   |                            |
   |<----------- ack -----------|
~~~

If the producer resends without idempotence, the broker may append a duplicate. This is why producer idempotence matters.

Timeouts that are commonly important to distinguish:

| Property | Role |
|---|---|
| request.timeout.ms | Time to wait for a response to one request sent to the broker |
| delivery.timeout.ms | Maximum total time for the producer to complete one send, including batching, requests, and retries |
| linger.ms | Additional time the producer may wait to group records into a batch |
| retry.backoff.ms | Pause interval between retry attempts in certain error conditions |

delivery.timeout.ms is the overall cap for one send. If the producer cannot finish before the deadline, the future fails. Increasing retry count without checking delivery timeout does not guarantee the send actually gets more time.

### Internal retries and application-layer retries

- **Internal producer retry:** the Kafka producer automatically resends requests on retriable errors. Producer idempotence protects against duplicates caused by retries within the same producer session.
- **Application retry:** the application calls KafkaTemplate.send() again after receiving an error. From the application's perspective this is a new send, which can create duplicates if the earlier send was written by the broker while the response was lost.

If retrying at the application layer, carry a stable eventId and make consumers idempotent. Never generate a new ID for the same event merely because the producer needed to resend.

## 9. What does producer idempotence protect against?

Producer idempotence uses a producer ID and sequence numbers so the broker can identify retries from the same producer. When a producer resends a batch due to a transient error, the broker can detect the retry and avoid appending a duplicate for an already written batch.

Idempotence helps:

- Avoid duplicates caused by internal producer retries.
- Preserve record order within a partition during retries under the idempotent mechanism.
- Increase reliability when paired with acks=all.

Idempotence does not eliminate every source of duplicates:

- The application calling send() twice for the same event.
- Two independent producer instances emitting the same event.
- A consumer reprocessing a record after failing to commit its offset.
- A business retry creating a new event with a new ID.
- External side effects outside Kafka succeeding before the consumer fails to commit its offset.

Therefore, producer idempotence and consumer idempotency address two different boundaries. For critical business logic, include a unique event ID and deduplication in the receiving system.

## 10. Record ordering during retries

Kafka preserves append order within each partition. Producers sending the same key normally route records to the same partition, yet retries can affect ordering if idempotence is disabled and multiple requests are in flight.

With a non-idempotent producer, if multiple requests are unacknowledged and an earlier request is retried, a newer request may be written first by the broker. This can make record order diverge from the order in which the application sent them.

When idempotence is enabled, the Kafka producer manages sequence numbers to preserve retry ordering within the producer and partition across supported limits. Modern Kafka clients allow up to five in-flight requests per connection when idempotence is enabled.

If business logic requires per-entity ordering:

1. Use a business key such as orderId or accountId.
2. Enable producer idempotence.
3. Do not spin up multiple independent producers emitting the same key if a single business order is required.
4. Avoid parallel consumer-side processing that reorders side effects.
5. Account for the impact of increasing partition counts because key mapping can change.

Ordering in Kafka is only guaranteed within a single partition. There is no global order across partitions.

## 11. Acknowledgements and Kafka transactions

Acknowledgements answer to what level a single record was accepted by the broker. Kafka transactions solve a different problem: multiple Kafka records and input offsets can be committed as an atomic unit.

Consume-transform-produce example:

~~~text
Consume input record
       |
Transform
       |
Begin Kafka transaction
       |
Produce output record(s)
       |
Add consumed offset to transaction
       |
Commit transaction
       |
Output and offset committed together
~~~

A transactional producer requires idempotence and an appropriate transactional ID. Consumers reading transactional output need isolation.level=read_committed to observe only records belonging to committed transactions.

acks=all does not create exactly-once by itself. It strengthens replication acknowledgement for written records. Exactly-once for a Kafka-to-Kafka pipeline requires a transaction encompassing both outputs and input offsets.

Kafka transactions also do not cover databases, emails, or HTTP APIs automatically. If a listener calls a system outside Kafka and the transaction later aborts, that side effect may run again when the input is re-read. Use an idempotency key or an appropriate inbox/outbox pattern.

## 12. Failure scenarios and mitigations

| Scenario | Possible outcome | Risk mitigation |
|---|---|---|
| Using acks=0, broker misses record | Producer may not detect failure | Use a higher ack level if the record is critical |
| Leader fails after acks=1 before follower replicates | Record may be lost when a new leader is elected | Use acks=all, proper min ISR, and clean leader election |
| ISR drops below min ISR | Broker rejects acks=all writes | Restore replicas, monitor under-replicated partitions |
| Producer times out after broker append | Uncertain send outcome; naive retry can duplicate | Enable idempotence; use a stable event ID |
| Delivery timeout expires | Future fails even though broker may have received the record if response was lost | Handle errors and deduplicate on the consumer |
| Application retries with a new send call | Can create an extra record for the same event | Use an idempotency key and retry rules |
| Producers emit same key across multiple instances | Business order may not match expectations | Coordinate producers or track business version/sequence |
| Consumer succeeds in processing but offset not committed | Record may be redelivered | Idempotent consumer or inbox/unique constraint |

A failed send does not always prove the record does not exist. For non-idempotent operations, treat this state as uncertain and design consumers to tolerate duplicates.

## 13. Testing producer acknowledgements

Tests must verify send behavior at the producer and broker level, not merely mock KafkaTemplate.

Valuable integration scenarios:

- Create a topic with replication factor 3 and min.insync.replicas=2, send records with acks=all, and verify the future completes and metadata contains partition/offset.
- Disconnect one follower so ISR drops to two, confirming writes can still succeed when min ISR is met.
- Drop ISR below min ISR, confirming the producer receives an error or retries until delivery timeout.
- Inject a transient connection error and verify producer idempotence does not create duplicates from internal retries.
- Send the same event ID via application retry to verify the consumer deduplicates properly.
- Verify both success and failure callbacks are recorded.
- Measure latency across acks levels in a test environment with real replication.

Do not use a single broker to draw conclusions about ISR behavior or replication factor 3. Scenarios require enough brokers and topology to simulate real replicas.

## 14. Observing the producer in production

Useful metrics:

- Send success and send failure rates.
- Producer retry rate and error rate by exception type.
- Request latency, record send rate, and batch size.
- Acknowledgement wait time and delivery timeouts.
- Under-replicated partitions, ISR shrink/expand, and offline partitions.
- Count of NotEnoughReplicas or errors related to min ISR.
- Count of duplicate event IDs detected by consumers.

When latency rises, check broker load, replication lag, network, request queue, and batch configuration. When send failures rise alongside ISR shrinks, the problem may lie in the broker cluster or network rather than KafkaTemplate logic.

## Producer design checklist

- [ ] Choose acks based on data criticality.
- [ ] Topic has a replication factor aligned with broker count and failure domains.
- [ ] min.insync.replicas reflects the minimum number of copies truly required.
- [ ] Producer idempotence is enabled when protection for internal retries is needed.
- [ ] request.timeout.ms and delivery.timeout.ms fit the SLO.
- [ ] KafkaTemplate.send() callbacks handle both success and failure.
- [ ] Application retries use a stable event ID and duplicate controls.
- [ ] Consumers process idempotently to tolerate redeliveries.
- [ ] If Kafka-to-Kafka exactly-once is needed, transactions include outputs and offsets.
- [ ] Metrics/alerts exist for send failures, retries, latency, and ISR.

## Conclusion

acks defines how far the producer waits for broker acknowledgement: no wait with 0, leader wait with 1, or ISR replica wait with all. Actual durability also depends on replication factor and min.insync.replicas. In Spring Kafka, configure appropriate producer properties, handle asynchronous KafkaTemplate results, enable idempotence when needed, and design consumers to tolerate duplicates. Acknowledgements confirm writes to Kafka at the chosen level; they do not replace business transactions or guarantee side effects in external systems.

