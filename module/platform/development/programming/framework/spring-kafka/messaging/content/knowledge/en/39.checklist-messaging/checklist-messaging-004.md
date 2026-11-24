# Consumer Configuration Checklist in Spring Kafka

A consumer operates reliably only when the Kafka client, listener container, and business processing configurations are chosen in harmony. A consumer can connect to the broker successfully yet read the wrong data due to an improper group ID or offset policy; it can receive records without committing offsets; or it can trigger rebalances because the listener takes longer than the poll budget. This checklist helps review configurations before running integration tests and deploying to production.

The scope covers single-record consumers and common Spring Kafka options: bootstrap servers, consumer groups, offsets, deserializers, poll/fetch, concurrency, acknowledgments, retry/DLT, security, monitoring, and shutdown. Numeric values in examples are only starting points; measure load and define ordering, latency, and durability requirements before using them in practice.

## 1. Overall checklist

| Group | Questions to answer | Required evidence |
|---|---|---|
| Connectivity | Is the consumer connected to the right cluster and security protocol? | Bootstrap servers, TLS/SASL tests |
| Identity | Is the group ID stable and properly isolated by environment/service? | Consumer group description |
| Offset | When a group has no offset, where does it start? When does it commit? | Offset policy, AckMode, integration tests |
| Deserialize | What Java types are payloads/schemas converted into? | Serializer contract and malformed-message tests |
| Poll/fetch | Does the consumer have enough processing time and memory for a batch? | Processing duration, poll/fetch metrics |
| Concurrency | Does consumer count fit the partition count and downstream capacity? | Assignment, thread-safety review |
| Error handling | Which exceptions retry, and which go to DLT? | Error handler policy and DLT tests |
| Security | Does the principal have only necessary permissions? | ACL tests and secret management |
| Observability | Can records be traced and lag/stuck consumers detected? | Logs, metrics, alerts |
| Lifecycle | Are start, pause, stop, and shutdown safe? | Lifecycle tests and deployment runbook |

Do not mark an item complete merely because a property exists in YAML. Verify evidence that the config binds to the right ConsumerFactory/container and that the behavior has been tested.

## 2. Choose the right bootstrap servers and environment

Declare the bootstrap servers of the cluster the consumer needs to read from:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}
```

Verify:

- Bootstrap addresses belong to the right dev, test, staging, or production environment.
- The list includes enough broker endpoints for the client to fetch metadata when a broker is unavailable.
- DNS, ports, network policies, and firewalls allow the workload to connect.
- Do not mix bootstrap servers between source and target clusters.
- If using multiple clusters, create separate ConsumerFactory/container factory beans with clear names.
- Do not hard-code production addresses in source code or test fixtures.

Bootstrap servers are only the initial entry point to obtain metadata. Afterward, the client connects to the leader/coordinator brokers returned by metadata; therefore, all advertised listener addresses must be reachable from the application's runtime environment.

## 3. Define the consumer group ID

The group ID defines the consumer group's identity and the scope of offsets stored by Kafka. Consumers in the same group share partitions; consumers in different groups can read the same topic independently.

Example:

```yaml
spring:
  kafka:
    consumer:
      group-id: orders-projection
```

Checklist:

- Group ID is stable across restarts of the same logical application.
- Separate group IDs between applications with independent processing purposes.
- Separate group IDs between dev/staging/production environments.
- Do not generate a random group ID on every startup if continuing from prior offsets is desired.
- Do not share a group ID between two consumers with different business logic just to "share load."
- Include group ID in logs and dashboards to investigate lag.

If two listeners need to receive every record independently, they must use different group IDs. If they share a group ID, Kafka distributes partitions across consumers in the group instead of broadcasting every record to every listener.

## 4. Choose auto-offset-reset according to business needs

`auto.offset.reset` applies only when a group has no valid committed offset, or when the current offset is no longer valid within retention/available log range. It does not rewind a group that already has offsets back to the start of the topic on every restart.

| Value | Behavior when no valid offset exists | Typical use cases |
|---|---|---|
| `earliest` | Starts from the earliest retained offset | New consumer needs to process retained history |
| `latest` | Starts from new data written after initialization | Only cares about new data; okay to skip history before the group started |
| `none` | Throws an error if no valid offset is found | Wants to fail fast so operators decide the offset |

Example:

```yaml
spring:
  kafka:
    consumer:
      auto-offset-reset: earliest
```

Before choosing, answer:

- Must a new consumer replay historical data?
- Does the topic have long enough retention for how long a consumer may be offline?
- When offsets expire, should the system restart automatically or halt for operator intervention?
- Could replay produce duplicate side effects in databases or downstream services?

Do not use `earliest` as a way to fix lag or reset offsets. To replay a group that already has offsets, use a controlled reset/seek procedure, record the old offsets, and assess side effects before executing.

## 5. Configure deserializers per event contract

The consumer must deserialize the exact data type the producer sent. Configure key and value deserializers explicitly:

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.value.delegate.class]": org.springframework.kafka.support.serializer.JsonDeserializer
        "[spring.json.value.default.type]": com.example.orders.event.OrderCreated
        "[spring.json.trusted.packages]": com.example.orders.event
```

The example uses `ErrorHandlingDeserializer` wrapping `JsonDeserializer` so deserialization errors can be routed into Spring Kafka's error handling/recovery. Class names, packages, and properties must match your actual models and dependencies.

Checklist:

- Key deserializer matches the producer's key serializer.
- Value deserializer matches the format: String, JSON, Avro, Protobuf, or custom.
- Event contracts/schema versions are managed.
- Trusted packages include only necessary packages; do not use broad wildcards arbitrarily.
- If using type headers, identify which producers are permitted to supply type metadata.
- If not using type headers, configure a clear default target type or converter.
- Tests exist for valid payloads, malformed payloads, old schemas, and new fields.
- Policy exists for tombstones (null value) if the topic is compacted.

Do not treat deserialization errors as ordinary business errors. The listener method may not even be invoked when deserialization fails; verify `ErrorHandlingDeserializer`, the error handler, and the ability to publish raw bytes to the DLT.

## 6. Control type headers and trusted packages

Spring Kafka's JSON deserializer can use type information in Kafka headers. This is convenient when multiple event types are exchanged, but type headers come from producers and must be controlled.

Checklist:

- Trust only packages containing permitted event DTOs.
- Do not enable trusted packages for the entire classpath unless necessary.
- Align type mappings between producers and consumers when package/class names differ.
- If the schema defines a single fixed type, consider configuring a default type and not relying on type headers.
- Check compatibility when renaming packages, renaming classes, or running multiple service versions simultaneously.
- Do not deserialize arbitrary classes from untrusted data.

If using Schema Registry with Avro/Protobuf, manage subject naming strategies, schema compatibility, and credentials separately. Do not apply JSON deserializer settings to other serializer formats.

## 7. Disable auto commit and choose AckMode

With Spring Kafka listener containers, let the container manage commits rather than enabling Kafka auto commit:

```yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: record
```

Spring Kafka containers default `enable.auto.commit=false` if not configured otherwise; declaring it explicitly makes intent easy to review. When auto commit is off, the container uses AckMode to decide when to commit.

| AckMode | When committed | Considerations |
|---|---|---|
| `RECORD` | After the listener finishes each record | Easy to reason about for record listeners; commits more frequently |
| `BATCH` | After finishing the entire batch from a poll | Better throughput; errors can affect the batch |
| `TIME` | When commit interval elapses and batch finishes | Requires understanding commit cycles |
| `COUNT` | When processed record count reaches threshold | Balances commit frequency and processed volume |
| `COUNT_TIME` | Combines count and time thresholds | Needs load and failure testing |
| `MANUAL` | Application calls acknowledge; commits per container semantics | Must ensure every branch acknowledges properly |
| `MANUAL_IMMEDIATE` | Commits immediately on acknowledge on the consumer thread when supported | Must adhere to thread/ordering contracts |

`BATCH` is the common default AckMode of the container when auto commit is off. Choose `RECORD` or `BATCH` explicitly per requirements rather than relying on implicit defaults.

Do not acknowledge before business side effects complete. If the database has written data but the offset is not yet committed, the record can be redelivered; consumers need idempotency or inbox/deduplication if side effects must not repeat.

## 8. Choose isolation.level when reading transactional topics

If producers use Kafka transactions, consumers may need:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[isolation.level]": read_committed
```

Two main options:

- `read_uncommitted`: may read records belonging to uncommitted or aborted transactions.
- `read_committed`: reads only committed records; records from aborted transactions are not returned to the application.

If the business flow requires processing only committed data from transactional producers, choose `read_committed`. Understand that consumers can be held back by the last stable offset while a transaction remains open for a long time; this affects reading subsequent records on the partition.

If producers do not use transactions and transactional visibility is not needed, do not add the setting automatically just because a lesson title says "exactly-once." Choose according to the data source's semantics.

## 9. Configure poll timeout and heartbeat

Three properties must be well understood:

| Property | Role |
|---|---|
| `max.poll.interval.ms` | Time limit between `poll()` calls; if processing a poll takes too long, the consumer may leave the group |
| `session.timeout.ms` | How long the broker waits for a valid heartbeat before considering the consumer disconnected |
| `heartbeat.interval.ms` | Interval at which the client sends heartbeats in the classic group protocol |

Illustrative example:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[max.poll.interval.ms]": 300000
        "[session.timeout.ms]": 45000
        "[heartbeat.interval.ms]": 15000
```

Do not copy these numbers verbatim without measuring. When a listener processes sequentially, the time to process all records from a poll, plus dependency waits, retries, GC pauses, and overhead, must fit within the poll budget.

`session.timeout.ms` does not replace timeouts for HTTP/DB. `max.poll.interval.ms` is not a timeout for a single query. Set finite connect/read/query timeouts downstream and choose the poll budget based on p95/p99 processing duration.

With the new Kafka consumer group protocol (`group.protocol=consumer`), some heartbeat/session behaviors are broker-driven and client properties may no longer apply as in the classic protocol. Check the protocol and Kafka client version before tuning.

## 10. Choose max.poll.records based on processing time

`max.poll.records` limits the number of records returned in one poll. Larger values can increase throughput but also make batches take longer to process and increase memory held for payloads.

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[max.poll.records]": 100
```

Choose the value based on:

- Processing time per record and p95/p99 batch duration.
- Average and maximum payload sizes.
- Number of records that can be held in memory.
- Database/API call durations.
- `max.poll.interval.ms`.
- AckMode and retry semantics.

Lower `max.poll.records` if batches take too long or memory pressure is high. Increase gradually once measurements show spare poll budget and downstream can handle the load.

For batch listeners, note that a batch can contain records from multiple partitions. Do not assume contiguous offsets or a single partition per poll.

## 11. Choose fetch size and memory budget

Fetch properties affect how much data the consumer receives from the broker:

| Property | Meaning |
|---|---|
| `fetch.min.bytes` | Minimum data the broker tries to accumulate before returning a fetch response |
| `fetch.max.wait.ms` | Maximum time the broker waits to reach `fetch.min.bytes` |
| `max.partition.fetch.bytes` | Fetch data limit per partition |
| `fetch.max.bytes` | Total fetch data limit in a single request |

Example:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[fetch.min.bytes]": 1
        "[fetch.max.wait.ms]": 500
        "[max.partition.fetch.bytes]": 1048576
        "[fetch.max.bytes]": 52428800
```

The values above are illustrative only. Raising `fetch.min.bytes` can improve throughput via batching at the cost of higher latency. Lowering `fetch.max.wait.ms` can reduce wait times but increase request counts. Fetch limits must match record batch sizes and memory budgets.

Kafka may return the first batch larger than some fetch limits so the consumer can still make progress when a batch exceeds the configured limit. Therefore, do not treat these properties as the sole hard cap protecting heap; enforce message size limits on producers/brokers/topics and monitor memory.

## 12. Choose concurrency according to partitions and downstream

Example listener configuration:

```yaml
spring:
  kafka:
    listener:
      concurrency: 3
```

Concurrency creates multiple consumers in the same group for the listener container. The number of consumers that can actually receive partitions is bounded by partition assignment.

Checklist:

- Total concurrency does not exceed downstream processing capacity.
- Compare concurrency against the partition counts of subscribed topics.
- Accept idle extra consumers if concurrency exceeds assigned partitions.
- Check whether partition keys distribute evenly or create hot partitions.
- Singleton listener beans must be thread-safe when multiple consumers invoke them concurrently.
- Do not share unsynchronized mutable state across listener threads.
- For databases, the connection pool size must support the concurrency without overloading the database.

Increasing concurrency will not automatically boost throughput if there is only one partition or downstream is saturated. When scaling parallelism, you may need to increase partition count and re-evaluate the key/ordering strategy.

## 13. Configure container factories explicitly

Spring Boot can auto-configure a listener container factory from `spring.kafka.*`. When custom policies are needed, declare a factory explicitly:

```java
@Configuration
public class KafkaConsumerConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            orderListenerContainerFactory(
                    ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);
        factory.getContainerProperties()
                .setAckMode(ContainerProperties.AckMode.RECORD);

        return factory;
    }
}
```

Listener using the factory:

```java
@KafkaListener(
        id = "orders-listener",
        topics = "orders.created.v1",
        groupId = "orders-projection",
        containerFactory = "orderListenerContainerFactory"
)
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
```

If there is a single shared policy, using Boot auto-configuration reduces duplicate configuration. If creating a custom factory, check whether it inherits required properties such as error handlers, observation, converters, interceptors, and common container properties. Do not assume a manually declared factory automatically receives all `spring.kafka.listener.*` properties.

## 14. Record listener vs. batch listener

Choose the listener type according to processing semantics:

| Type | Characteristics | Suitable for |
|---|---|---|
| Record listener | Invokes method per record | Independent business logic, easy per-record retry |
| Batch listener | Method receives a batch of records from poll | Batch processing, bulk inserts, or reducing overhead |

Checklist:

- `@KafkaListener` method signature matches the container factory's listener type.
- Batch listeners handle partial failures per a clear policy.
- Do not treat an entire batch as succeeded if one record was not processed.
- Define offset commit behavior when part of a batch fails.
- Bound batch sizes and processing times.
- Test batches containing records from multiple partitions and failing records at different positions.

Do not set `factory.setBatchListener(true)` without updating the method signature and testing corresponding error handling.

## 15. Configure error handlers and retry policies

Consumers need distinct policies for transient errors and unrecoverable errors:

| Error type | Examples | Typical policy |
|---|---|---|
| Transient errors | Inventory service timeout, flaky network | Bounded retry with backoff |
| Data errors | Validation failure, missing required field | No retry or very limited retry; route to DLT |
| Deserialization errors | Invalid JSON/schema | ErrorHandlingDeserializer and recovery/DLT |
| Authorization errors | ACL denies reading or publishing to DLT | Fix permissions; retries will not resolve it |
| Programming errors | NullPointerException, broken invariant | Investigate; avoid infinite retries |

For blocking retry, configure `DefaultErrorHandler` and an appropriate `BackOff`. For non-blocking retry, configure `@RetryableTopic` and retry topics as needed. Do not combine both mechanisms without understanding total delivery counts and processing order.

Checklist:

- Exceptions are classified as retryable vs. non-retryable.
- Attempt limits and backoff are clearly defined.
- Backoff does not cause the consumer to exceed its poll budget unexpectedly.
- DLT or recovery strategy exists for unprocessable records.
- DLT publisher can serialize both normal records and raw bytes when deserialization fails.
- Retry/DLT topics have ACLs, retention, monitoring, and replay procedures.
- Sensitive payloads are not logged in exceptions or DLT handlers.

## 16. DLT and access permissions

A DLT is not a place to "throw records away and forget them." Define who handles it, retention period, and replay procedure:

- DLT topic has a stable name and partition strategy.
- DLT has enough partitions if the recoverer preserves source partitions.
- Consumers/operators with permission to read the DLT are restricted.
- Records retain source metadata such as original topic, partition, offset, and exception type.
- Alerts trigger when DLT grows.
- Replay includes event IDs/idempotency to prevent duplicate side effects.
- Procedures exist for closing incidents and deleting data per retention policy.

If using `DeadLetterPublishingRecoverer`, check the destination resolver and the serializer of the producer used to publish. If the source record failed deserialization, the recoverer may need to publish `byte[]`; the template/serializer configuration must support the proper value type.

## 17. Choose appropriate isolation and transactions

If a consumer participates in Kafka transactions or reads from transactional producers:

- Use `isolation.level=read_committed` if only committed records should be processed.
- For consume-transform-produce exactly-once, configure the transaction manager and listener container per the Spring Kafka model.
- Do not commit offsets independently outside the transaction when output and input offsets must commit atomically.
- Do not assume Kafka transactions cover databases or HTTP APIs.
- For external side effects outside Kafka, use idempotency, inbox/outbox, or appropriate coordination.

If transactional semantics are not needed, keep configuration simple and choose `read_uncommitted`/default per system requirements. Do not add transactions just to "increase safety" without defining the failure model.

## 18. Consumer security

Example SASL_SSL with SCRAM:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[security.protocol]": SASL_SSL
        "[sasl.mechanism]": SCRAM-SHA-512
        "[sasl.jaas.config]": ${KAFKA_CONSUMER_JAAS_CONFIG}
```

Checklist:

- Secrets come from a controlled secret manager/config tree/environment.
- Do not commit JAAS passwords or TLS private keys to the repository.
- Consumer principal only has READ/DESCRIBE on required topics.
- Principal has READ permission on the consumer group needed to join/commit offsets.
- Read permission on retry/DLT is granted only if the consumer needs it.
- Do not share superuser credentials across services.
- Keep TLS hostname verification enabled.
- Credential/certificate rotation procedure exists.
- Do not log all consumer properties because they may contain secrets.

Exact ACL operation names depend on the Kafka authorizer/distribution; test with the real principal in a production-equivalent environment.

## 19. Consumer observability

At a minimum, monitor:

| Signal | Purpose |
|---|---|
| Consumer lag by group/topic/partition | Know if the consumer is falling behind |
| Records consumed rate | Know processing speed |
| Listener processing duration p95/p99 | Detect slow or stuck listeners |
| Commit rate/latency and commit failures | Detect offsets failing to advance |
| Rebalance count | Detect unstable groups |
| Retry/DLT rate | Detect business or dependency errors |
| Assigned partitions/member count | Detect consumers without assignments |
| Authentication/authorization errors | Detect misconfigured security |

Record-level logs should include event ID, group ID, topic, partition, and offset without sensitive payloads. Metric labels should not use event ID, offset, or order ID due to unbounded cardinality growth.

Alerts should examine sustained lag over sufficient duration, stalled offsets while log end offsets continue growing, listener duration breaching SLAs, or repeated rebalances. Zero lag with no new records is a normal idle state.

## 20. Shutdown and lifecycle

When the application shuts down or deploys:

- The container is stopped following the Spring lifecycle.
- Listeners have an opportunity to finish in-flight records within the shutdown timeout.
- Consumers close and leave the group; rebalances are expected.
- Offsets are committed only according to the configured AckMode/transaction.
- Uncommitted side effects can lead to redelivery after restart.
- Consumers must be idempotent or have deduplication if redelivery could repeat business effects.

Avoid repeatedly killing processes to stop consumers when graceful shutdown can be used. Size the shutdown timeout to match maximum processing duration and the deployment platform's termination grace period.

If using `KafkaListenerEndpointRegistry` to dynamically pause/stop listeners, audit the operations and ensure containers are resumed/restarted at the right time. Do not leave listeners paused permanently if an administrative branch fails.

## 21. Baseline configuration for review

This is a combined example for a JSON record listener; numbers are illustrative only:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}
    consumer:
      group-id: orders-projection
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.value.delegate.class]": org.springframework.kafka.support.serializer.JsonDeserializer
        "[spring.json.value.default.type]": com.example.orders.event.OrderCreated
        "[spring.json.trusted.packages]": com.example.orders.event
        "[max.poll.interval.ms]": 300000
        "[max.poll.records]": 100
        "[session.timeout.ms]": 45000
        "[heartbeat.interval.ms]": 15000
    listener:
      ack-mode: record
      concurrency: 3
```

Before using the baseline, verify:

- Whether `earliest` matches historical processing needs of a new group.
- Whether `read_committed` is required if sources use transactions.
- Whether JSON type headers/default type match the event contract.
- Whether poll interval and max records match actual processing durations.
- Whether concurrency matches partition count and downstream capacity.
- Whether error handler, retry, and DLT are configured separately; the baseline does not create a DLT automatically.
- Whether environment-specific security properties and credentials have been added.
- Whether the actual `ConsumerFactory`/container factory uses this configuration.

## 22. Pre-merge and pre-deploy checklist

### Configuration and contracts

- [ ] Bootstrap servers match the environment and advertised listeners are reachable.
- [ ] Group ID is stable and does not collide with independent applications.
- [ ] Offset reset policy is chosen and tested with a fresh group.
- [ ] Key/value deserializers match the format and event schema.
- [ ] Trusted packages/type headers are restricted.
- [ ] Tombstones are handled if the topic is compacted.

### Poll, concurrency, and commits

- [ ] Auto commit is disabled; AckMode is chosen explicitly.
- [ ] `max.poll.interval.ms` accommodates p99 batch processing duration.
- [ ] `max.poll.records` suits throughput and memory.
- [ ] Fetch size/wait align with latency, payloads, and heap.
- [ ] Concurrency is compared against partition count and downstream capacity.
- [ ] Listeners are thread-safe when running concurrently.
- [ ] Side effects finish before acknowledgment/commit.
- [ ] Consumers tolerate redelivery.

### Error handling and security

- [ ] Retryable/non-retryable exceptions are classified.
- [ ] Retries have clear limits and backoff.
- [ ] DLT destination, serializer, ACLs, and retention are tested.
- [ ] Transaction/isolation level matches the failure model.
- [ ] Credentials come from a secret store with rotation in place.
- [ ] ACLs grant only necessary permissions for topics/groups.
- [ ] Logs contain no payloads or secrets.

### Operations and testing

- [ ] Metrics exist for lag, processing duration, commits, and rebalances.
- [ ] Alerts exist for stalled offsets and rising DLT.
- [ ] Integration tests exist with a real broker or Testcontainers/Embedded Kafka.
- [ ] Tests cover malformed payloads, retries, DLT, rebalances, and restarts.
- [ ] Shutdown while a listener is processing has been tested.
- [ ] Controlled offset reset/replay runbook exists.

## 23. Testing consumer configuration

Do not only test that the Spring context starts. Include the following tests:

1. Consumer joins the right group and receives records from the expected topic.
2. A new group applies `auto.offset.reset` properly.
3. Restarting a consumer resumes from the committed offset.
4. Commits occur only after listener processing finishes according to AckMode.
5. Crashing before commit causes redelivery and the consumer handles it idempotently.
6. Malformed payloads are handled by the error handler/DLT without silently dropping or stalling the listener.
7. Retryable exceptions retry per count/backoff; non-retryable exceptions go to recovery/DLT.
8. Consumers with `read_committed` do not receive records from aborted transactions.
9. Concurrency and partition assignments match expectations.
10. Slow listener processing does not trigger unexpected rebalances.
11. Incorrect ACLs produce clear authorization errors; do not grant superuser just to pass tests.
12. Shutdown/restart does not lose uncommitted records.

Use dedicated topics and groups for tests to avoid interference from other environments' offsets. Wait on conditions using bounded polling rather than fixed `Thread.sleep()`. When testing offsets, verify topic-partition and committed offsets; do not only check invocation counts on a listener mock.

## 24. Common configuration mistakes

**Consumer re-reads all data on every restart:** group ID changes or offsets are not committed; `auto-offset-reset` only applies when no valid offset exists.

**Consumer does not read older data:** group has no offset and uses `latest`; verify whether historical replay is needed before switching to `earliest`.

**Listener is never invoked:** check partition assignment, deserialization, security, and container lifecycle before modifying business methods.

**Consumer rebalances continuously:** check processing time, `max.poll.interval.ms`, heartbeats, network, and instance restarts.

**Offsets do not advance:** check AckMode, manual acknowledgment, error handlers, transaction aborts, and commit failures.

**Increasing concurrency does not increase throughput:** check partition count, hot keys, and downstream bottlenecks.

**JSON deserialization fails:** check producer serializer, target type, type headers, trusted packages, and schema compatibility.

**Infinite retries:** check exception classifier and backoff; route unrecoverable data errors to DLT.

**DLT publish fails:** check producer credentials/ACL, destination topic, partition count, and serializer for raw bytes.

**Consumer reads uncommitted records:** check `isolation.level`; use `read_committed` when transactional visibility is required.

**Production logs leak secrets:** inspect SASL config, exceptions, payloads, headers, and Kafka client log levels.

## 25. Final principle-based checklist

A production-ready consumer configuration must answer five questions:

1. **Read from where?** Cluster, topic, group ID, partition assignment, and offset reset policy are clear.
2. **Read into what?** Deserializers, schemas, type mappings, and tombstone behavior are verified.
3. **Process within how long?** Poll/fetch, concurrency, downstream timeouts, and memory budgets match the load.
4. **When is it considered complete?** AckMode, commits, transactions, and idempotency are designed consistently.
5. **What happens on failure?** Retries, DLT, security, monitoring, and recovery runbooks are tested.

A consumer configuration checklist is not a list of properties to turn on indiscriminately. Every property must tie to a decision about data, throughput, ordering, latency, failure recovery, or security. Keep configurations intentional, test against a production-equivalent broker, and monitor offsets/lag after deployment to confirm the consumer actually behaves properly.

## References

- [Spring for Apache Kafka – Receiving Messages](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages.html)
- [Spring for Apache Kafka – Listener Container](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring for Apache Kafka – Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring Boot – Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)
- [Apache Kafka – Consumer Configs](https://kafka.apache.org/documentation/#consumerconfigs)
