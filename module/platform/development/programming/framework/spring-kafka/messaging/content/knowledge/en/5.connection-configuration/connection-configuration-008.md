# session.timeout.ms and heartbeat

In a Kafka consumer group, the broker needs to know which consumers are still participating in the group in order to retain or reassign partitions. Consumers periodically send heartbeats to signal that they are still active. If the broker does not receive a heartbeat within the allowed window, the broker considers the member lost and may initiate a rebalance.

Two commonly seen configurations in the classic consumer group protocol are **session.timeout.ms** and **heartbeat.interval.ms**. They directly relate to detecting disconnected consumers, yet they do not replace checking whether the consumer continues calling poll() and processing records. To operate Spring Kafka reliably, you also need to understand max.poll.interval.ms, listener processing time, offset commits, and the impact of rebalances.

## Learning objectives

After this lesson, you will be able to:

- Explain heartbeats, consumer sessions, and how the broker detects inactive members.
- Distinguish between session.timeout.ms, heartbeat.interval.ms, and max.poll.interval.ms.
- Choose timeout values suited to failover latency and network interruption tolerance.
- Configure consumer properties in Spring Boot and ConsumerFactory.
- Analyze the impact of slow listeners, garbage collection, network pauses, and rebalances.
- Recognize the difference between the classic consumer group protocol and the new consumer group protocol.
- Test and observe heartbeats, consumer lag, rebalances, and duplicate processing.

## 1. Heartbeats maintain consumer group membership

A consumer group can consist of multiple consumer instances sharing the reading of topic partitions. The group's coordinator (a broker selected by Kafka for the group) manages membership and partition assignment.

Consumers need to maintain contact with the coordinator. In the classic protocol, consumers send periodic heartbeats. Heartbeats tell the coordinator the member is still participating in the group. If the coordinator receives no heartbeat before the session expires, the member is considered to have left the group and its partitions may be reassigned to other members.

Simplified flow:

~~~text
Consumer A                         Group Coordinator
    |                                      |
    | -------- JoinGroup / SyncGroup ----> |
    | <------- partition assignment ------ |
    |                                      |
    | ------------ Heartbeat ------------> |
    | ------------ Heartbeat ------------> |
    | ------------ Heartbeat ------------> |
    |                                      |
    |   disconnected / missed heartbeats   |
    |                                      |
    |           session expired            |
    |                                      |
    | <--------- rebalance group --------- |
    |                                      |
Consumer B receives the reassigned partitions
~~~

Heartbeats do not carry the business outcome of a listener. They do not state that a record was written to a database, processed successfully, or that its offset was committed. They serve only consumer group membership and liveness.

Therefore, separate three signals:

| Signal | Question answered |
|---|---|
| Heartbeat | Is the consumer still maintaining membership with the coordinator? |
| poll() | Is the consumer continuing to fetch data and advance through the poll loop? |
| Offset commit | Up to what next read position has the consumer group recorded progress? |

A consumer can still be sending heartbeats while a listener is taking too long to process. Conversely, a consumer can finish processing a record without having committed its offset yet. Never use heartbeats as a proxy for business processing state.

## 2. session.timeout.ms

session.timeout.ms defines how long the coordinator waits for a consumer's heartbeat before considering that consumer lost. If no heartbeat arrives within this duration, the coordinator removes the member from the group and triggers partition reassignment.

Hypothetical example:

- session.timeout.ms = 15 seconds.
- Coordinator receives the latest heartbeat at 10:00:00.
- Consumer loses network connectivity immediately after that heartbeat.
- If no subsequent heartbeat arrives before the session expires, the coordinator may mark the member lost around 10:00:15, depending on processing timing and the actual heartbeat schedule.

These numbers only illustrate the timeout mechanism; they are not a millisecond-exact guarantee of failover timing.

### Short timeout

Advantages:

- Detects dead or disconnected consumers faster.
- Partitions can be handed over to surviving consumers sooner.
- Reduces waiting time when an instance has genuinely stopped.

Trade-offs:

- A brief network pause, CPU overload, or JVM stop-the-world pause can delay heartbeats.
- Healthy consumers may be kicked out of the group unintentionally.
- Frequent rebalances interrupt reading and add assignment re-initialization overhead.

### Long timeout

Advantages:

- More tolerant of transient network interruptions or pauses.
- Reduces the risk of falsely evicting consumers in environments with unstable latency.

Trade-offs:

- When a consumer truly dies, the coordinator waits longer before detecting it.
- Partitions remain idle waiting for failure detection longer before being reassigned.

Choose timeouts based on recovery goals and infrastructure characteristics. Do not just set them as low as possible; an overly sensitive timeout can trap the system in continuous rebalances.

### Broker-enforced bounds

In the classic protocol, the session timeout sent by a consumer must fall within the range allowed by the broker. Two broker configurations commonly apply:

- group.min.session.timeout.ms: lower bound.
- group.max.session.timeout.ms: upper bound.

If a client sends a value outside the broker's permitted range, the join-group request may be rejected. When changing session timeout, check both consumer settings and broker policies.

## 3. heartbeat.interval.ms

heartbeat.interval.ms defines the interval between consumer heartbeat transmissions in the classic protocol. This value must be smaller than session.timeout.ms. A common configuration guideline is to set the heartbeat interval no larger than roughly one-third of the session timeout so there are multiple chances to resend a heartbeat before the session expires.

Example:

~~~yaml
session-timeout: 15000
heartbeat-interval: 5000
~~~

With this illustrative configuration, the consumer is expected to send a heartbeat every 5 seconds while the coordinator waits up to 15 seconds from the last valid heartbeat before expiring the session.

If the heartbeat interval is too close to the session timeout, the consumer has little room to recover if a single heartbeat is delayed or lost. If set too small, heartbeat request volume rises and adds control traffic between consumers and the coordinator. Keep a sensible margin instead of setting the two values nearly equal.

The heartbeat interval is not the record-processing cycle. Nor does it mean the consumer polls Kafka on that cadence. Polling data and maintaining heartbeats are two related activities with distinct purposes.

## 4. Distinguishing from max.poll.interval.ms

This is the easiest point to confuse when configuring a consumer.

- session.timeout.ms controls how long the coordinator waits for heartbeats before treating a member as lost.
- heartbeat.interval.ms controls the heartbeat cadence in the classic protocol.
- max.poll.interval.ms limits the time between `poll()` calls from an active consumer under the consumer progress mechanism.

Ever since Kafka introduced background heartbeats, heartbeats can continue being sent while the application is processing records. Consequently, a slow listener does not necessarily cause an immediate session timeout. However, if the application does not call `poll()` again before max.poll.interval.ms expires, the consumer is considered no longer making progress and must leave the group or stop heartbeating according to client rules.

Example:

~~~text
Time            Event
-----------------------------------------------------
T0              Consumer calls poll(), receives batch
T1              Listener starts processing batch
T1 - T2         Heartbeats may still continue
T2              max.poll.interval.ms is exceeded
T3              Consumer leaves group / stops heartbeats
T4              Coordinator reassigns partitions
~~~

When a consumer processes records synchronously, total batch processing time must be evaluated alongside max.poll.interval.ms. If a batch has 100 records and each takes 2 seconds, processing can exceed 200 seconds, not counting downstream service calls and commits. Evaluate worst-case duration, not just average duration.

With static membership (configuring group.instance.id), exceeding max.poll.interval.ms may delay partition reassignment upon leaving until the session timeout expires. This can reduce rebalances on fast instance restarts, though it slows failover if the instance has actually died. group.instance.id must be unique across active consumer instances in the same group.

## 5. Heartbeats in the classic vs. new consumer group protocol

The properties session.timeout.ms and heartbeat.interval.ms are used in the familiar way under the **classic consumer group protocol**.

In Kafka versions supporting the new consumer group protocol, clients can select group.protocol=consumer. In this protocol, the broker controls heartbeat cadence and session timeout through broker-side configurations, typically:

- group.consumer.heartbeat.interval.ms
- group.consumer.session.timeout.ms

When using the new protocol, do not assume the two client properties session.timeout.ms and heartbeat.interval.ms still govern behavior as in the classic protocol. Check your Kafka broker version, kafka-clients version, and corresponding documentation before switching protocols. Support for the new protocol depends on cluster version and configuration.

| Aspect | Classic protocol | New consumer protocol |
|---|---|---|
| Session timeout | Consumer configures via session.timeout.ms, broker enforces allowed bounds | Broker manages via group.consumer.session.timeout.ms |
| Heartbeat interval | Consumer configures via heartbeat.interval.ms | Broker manages via group.consumer.heartbeat.interval.ms |
| Group protocol setting | group.protocol=classic | group.protocol=consumer |
| When tuning is needed | Check client properties and broker min/max session bounds | Adjust broker-side configs and verify compatibility |

If there is no need to switch protocols, use settings matching the cluster's current protocol. Avoid copying configurations from another Kafka version without checking the running client and broker.

## 6. Configuration in Spring Boot

Spring Boot allows passing Kafka Consumer properties through spring.kafka.consumer.properties. In YAML, use bracket notation to preserve dotted property names verbatim.

Example for the classic protocol:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: order-service
      enable-auto-commit: false
      properties:
        "[group.protocol]": "classic"
        "[session.timeout.ms]": "15000"
        "[heartbeat.interval.ms]": "5000"
        "[max.poll.interval.ms]": "300000"
        "[max.poll.records]": "100"
~~~

Meaning:

- group-id identifies the consumer group.
- enable-auto-commit=false lets the Spring Kafka container manage commits per the acknowledgment mode.
- session.timeout.ms and heartbeat.interval.ms control membership heartbeats under the classic protocol.
- max.poll.interval.ms limits the interval between polls.
- max.poll.records caps the maximum number of records returned in a single poll.

The values above are only examples to illustrate relationships among parameters. Tune them based on brokers, Kafka version, real processing durations, and system recovery objectives.

If the application uses multiple ConsumerFactory beans with different settings, make sure properties are passed into the exact factory used by the listener container. Placing properties in spring.kafka.consumer does not guarantee manually created ConsumerFactory beans receive those settings if initialized from separate maps.

## 7. Configuring via ConsumerFactory

When creating a ConsumerFactory manually, properties can be passed via Kafka ConsumerConfig:

~~~java
@Bean
public ConsumerFactory<String, OrderEvent> orderConsumerFactory() {
    Map<String, Object> props = new HashMap<>();

    props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
    props.put(ConsumerConfig.GROUP_ID_CONFIG, "order-service");
    props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class);
    props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            JsonDeserializer.class);

    props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
    props.put(ConsumerConfig.SESSION_TIMEOUT_MS_CONFIG, 15_000);
    props.put(ConsumerConfig.HEARTBEAT_INTERVAL_MS_CONFIG, 5_000);
    props.put(ConsumerConfig.MAX_POLL_INTERVAL_MS_CONFIG, 300_000);
    props.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 100);

    return new DefaultKafkaConsumerFactory<>(props);
}
~~~

This snippet illustrates timeout and heartbeat properties. In a real application, configure serializers/deserializers, trusted packages, and type mappings matching the application's message contract. Do not treat this illustrative snippet as a complete production configuration.

If using the new consumer group protocol, verify which client properties remain supported and configure heartbeats/sessions on the broker according to that protocol.

## 8. Relationship with the Spring Kafka listener container

Each Kafka consumer created by a listener container maintains its own membership in the consumer group. With ConcurrentMessageListenerContainer, each child container has its own consumer; each consumer has its own heartbeat and session.

Factory example:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        orderListenerContainerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);

    factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.RECORD
    );

    return factory;
}
~~~

Concurrency of 3 creates up to three child consumers. It does not turn session timeout into a shared container-wide value; each consumer has its own heartbeat and membership lifecycle.

If the topic has fewer partitions than consumers, some consumers may receive no partitions. Those consumers remain group members and continue maintaining membership via the client mechanism. Therefore, increasing concurrency does not increase partition count or speed up heartbeats.

Listeners should process within bounded time. Example:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-service",
    containerFactory = "orderListenerContainerFactory"
)
public void onOrder(OrderEvent event) {
    orderService.processIdempotently(event);
}
~~~

If processIdempotently calls a slow API, enforce timeouts on HTTP clients, databases, and dependencies. When synchronous processing takes significant time, max.poll.interval.ms must be evaluated alongside session timeout.

## 9. What happens when heartbeats are interrupted?

Several common scenarios:

| Scenario | Potential Impact | How to Handle |
|---|---|---|
| Consumer process is killed | Heartbeats stop; session expires and partitions are reassigned | Restart instance, monitor rebalances and consumer lag |
| Network partition between consumer and coordinator | Heartbeats fail to reach coordinator even though process is still running | Check network, broker connectivity, and timeouts |
| JVM stop-the-world pause | Heartbeats may be delayed or halted during the pause | Monitor GC pauses, heap pressure, and CPU |
| Broker/coordinator overloaded | Heartbeat requests or responses become slow | Monitor broker request latency, network, and coordinator load |
| Listener processes too slowly | May exceed max.poll.interval.ms even while heartbeats continue running | Optimize listener, reduce batch size, or adjust poll interval |
| Consumer rebalance | Partitions are revoked and reassigned; listener may pause briefly | Track rebalance causes and ensure idempotent processing |

When a consumer is evicted from the group, uncommitted records may be redelivered to a new consumer or the old consumer itself after rejoining. If side effects already completed before the offset was committed, duplicate processing can occur. Therefore, handlers should be idempotent and offsets should only be confirmed after necessary side effects complete.

A single failed heartbeat does not necessarily mean the consumer is dead. The client can retry heartbeats or recover from transient errors. Watch trends in heartbeat failures, session expirations, and rebalances rather than reacting to a single isolated log entry.

## 10. Choosing timeouts based on system characteristics

No single set of timeouts fits every environment. You can start with these principles:

1. Choose a session timeout short enough to meet recovery targets when a consumer genuinely dies, yet long enough to tolerate typical network/GC pauses.
2. In the classic protocol, set heartbeat interval below session timeout; roughly one-third is a common configuration guideline.
3. Set max.poll.interval.ms based on batch processing duration under heavy load or slow dependencies.
4. Choose max.poll.records so processing one batch fits well within the poll interval limit.
5. Set timeouts on database and HTTP clients so listeners never hang indefinitely.
6. Verify broker min/max session timeouts before rolling out new settings.
7. Test behavior when a consumer stops abruptly and when network connectivity is disrupted.

A short session timeout enables faster failover, yet if the application experiences frequent long pauses it will cause repeated rebalances. A long timeout reduces false positives but lengthens failure detection time. Choose values based on operational data and recovery SLOs.

## 11. Testing heartbeats and session timeouts

Integration tests should verify consumer group behavior when a member stops sending heartbeats or stops polling. You can use a real Kafka broker or Testcontainers matching the version deployed in production.

Useful scenarios:

- Start two consumers in the same group, abruptly stop one consumer, and observe partitions being reassigned.
- Simulate network delay or disconnect a consumer from the broker to inspect member-loss detection time.
- Create a listener that processes longer than max.poll.interval.ms to observe the consumer leaving the group and triggering a rebalance.
- Send a record, complete side effects, but stop the process before offset commit to confirm the handler tolerates redelivery.
- Increase concurrency and verify that the number of consumers receiving partitions matches the topic's partition count.
- Try a session timeout outside broker min/max bounds to confirm configuration errors are surfaced.

Do not use long sleeps in unit tests to infer exact broker session expiration timing. Use integration tests, synchronize on rebalance events or assignment state, and use bounded wait timeouts.

## 12. Observing in production

Signals to monitor:

- Rebalance count per consumer group and reasons when available.
- Active consumer count and partition assignments.
- Consumer lag per partition.
- Heartbeat request latency, heartbeat failures, and session expirations in available client/broker logs or metrics.
- Listener processing time and intervals between polls.
- JVM GC pauses, CPU, network errors, and broker coordinator load.
- Redelivered, retried, and dead-lettered record counts.

If rebalances spike suddenly, correlate timestamps with deployments, restarts, network incidents, GC pauses, and load changes. Simply increasing session.timeout.ms can mask symptoms without resolving the root cause.

## 13. Configuration checklist

- [ ] Identify whether consumers use the classic or the new consumer group protocol.
- [ ] For the classic protocol, session.timeout.ms is within broker-permitted bounds.
- [ ] For the classic protocol, heartbeat.interval.ms is smaller than session.timeout.ms with adequate margin.
- [ ] max.poll.interval.ms accommodates worst-case batch processing durations.
- [ ] max.poll.records does not produce batches exceeding allowed processing time.
- [ ] Listeners enforce dependency timeouts and do not block consumer threads indefinitely.
- [ ] Side effects are idempotent to tolerate redeliveries after rebalances.
- [ ] Metrics/logs can distinguish heartbeat failures, poll timeouts, and rebalances.
- [ ] Tested abrupt consumer termination, network disruption, and slow listener processing.
- [ ] Settings in Spring Boot or ConsumerFactory are actually wired into the listener container.

## Conclusion

session.timeout.ms determines how long the coordinator waits for heartbeats before removing a consumer from the group in the classic protocol. heartbeat.interval.ms governs the heartbeat cadence; max.poll.interval.ms controls poll loop progress. These three properties solve related but distinct problems. In Spring Kafka, each consumer created by a listener container maintains its own membership, so timeouts must be chosen according to protocol version, broker bounds, listener processing duration, and recovery goals. Heartbeats help Kafka detect lost members, while business correctness still depends on offset commits, retries, and idempotency.

