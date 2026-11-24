# Consumer Not Receiving Records

When a Spring Kafka application fails to receive records, the cause may lie in the producer, topic, consumer group, offset, listener container, deserialization, or broker connection. Merely checking the method annotated with `@KafkaListener` is usually not enough: the listener may not have started, the consumer may have no assigned partitions, the group may already be at the end offset, the record may be filtered out, or a deserialization error may occur before the method is invoked.

An effective approach is to trace the record's path and find the last point where it still works: did the producer publish, is the record in the topic, does the group have an assignment, is the offset advancing, and is the listener actually called? Each step needs concrete evidence before moving to the next.

## 1. Identify the Exact Symptom

Before modifying configurations, clarify what "not receiving records" means:

| Symptom | First area to check |
|---|---|
| Producer sends, yet no records appear in the topic | Send result, topic, broker, and serializer |
| Topic has records, yet consumer group has no assignment | Group membership, subscription, and partitions |
| Group has assignment, yet lag does not decrease | Consumer poll, listener, pause state, and processing errors |
| Lag is 0, yet listener does not run | Offset is at log end, wrong topic, or no new records |
| Listener is not invoked, yet logs report deserialization errors | Deserializer and `ErrorHandlingDeserializer` |
| Only certain keys/partitions are not processed | Partition assignment, hot partition, transactions, and record filtering |
| Works locally, fails in deployed environments | Bootstrap servers, `advertised.listeners`, ACLs, and TLS |
| Consumer ran previously, then stopped receiving | Rebalances, exceptions, container lifecycle, and poll interval |

Record these details before investigating:

- Topic and environment under test.
- Actual consumer group ID.
- Listener ID and container factory used.
- Partition count of the topic.
- Timestamp when the producer sent the record and the send outcome.
- Consumer group lag, assignment, and committed offsets.
- Isolation level, auto offset reset, and security settings.

Do not alter offsets or create a new group right away. Those actions can change which data the consumer reads and make finding the root cause harder.

## 2. Verify Whether the Producer Published Successfully

Calling `KafkaTemplate.send()` normally returns a future because sending a record is asynchronous. Calling `send()` without observing the result does not prove the broker acknowledged the record.

Example of checking the send result:

~~~java
SendResult<String, OrderEvent> result =
        kafkaTemplate.send(
                "orders",
                event.orderId().toString(),
                event
        ).get(10, TimeUnit.SECONDS);

RecordMetadata metadata = result.getRecordMetadata();

log.info(
        "Published order event topic={} partition={} offset={}",
        metadata.topic(),
        metadata.partition(),
        metadata.offset()
);
~~~

In production applications, you do not necessarily have to block with `get()` on every send. You can handle the future using callbacks or `CompletableFuture`. What matters is capturing publish errors such as timeouts, serialization errors, authorization failures, or broker unavailability.

When sending asynchronously, check callback/future exceptions. If errors are not observed, the producer might fail while business logs still claim "sent".

Points to confirm:

- The producer sends to the right topic in the current environment.
- Key/value serializers can serialize the event.
- The broker returns a successful acknowledgement.
- The topic exists or the broker is allowed to auto-create it.
- The producer has `WRITE` and `DESCRIBE` permissions on the topic.
- No exceptions are swallowed in callbacks.

A producer receiving an acknowledgement shows the broker accepted the record per the acknowledgement setting; it still does not prove the consumer group is reading the right topic or offset.

## 3. Confirm the Record Is Actually in the Topic

Use Kafka CLI to inspect topic metadata:

~~~bash
kafka-topics.sh   --bootstrap-server localhost:9092   --describe   --topic orders
~~~

Check:

- Whether the topic exists on the right cluster.
- Whether the partition count matches expectations.
- Whether each partition's leader is available.
- Whether replicas and ISR look abnormal.

You can read a few sample records with the console consumer:

~~~bash
kafka-console-consumer.sh   --bootstrap-server localhost:9092   --topic orders   --from-beginning   --max-messages 10   --property print.key=true   --property print.partition=true   --property print.offset=true
~~~

This command creates a consumer to read data. Do not use the production group ID for testing, as the diagnostic consumer could join the same group and share partitions with the running application. If you need to specify a group, use a separate temporary group and remember that a new group has its own offsets.

When using `--from-beginning`, the console consumer can read retained data from the start. Limit the record count and target the right cluster/topic to avoid reading large or sensitive datasets by mistake.

If the console consumer also sees no records, go back to the producer, topic, cluster, ACLs, and send timing. If the console consumer sees records while the application does not, focus on group, subscription, offset, listener, and deserialization.

## 4. Check `@KafkaListener` Topic and Subscription

Confirm the annotation points to the right topic:

~~~java
@KafkaListener(
        id = "orders-listener",
        topics = "orders",
        groupId = "order-service"
)
public void consume(OrderEvent event) {
    log.info("Received orderId={}", event.orderId());
    orderService.process(event);
}
~~~

Common mistakes:

- Misspelled topic name or wrong letter casing.
- Active profile overrides the property to a different topic.
- Listener uses a local topic while the producer sends to another cluster.
- Listener uses `topics` when the setup actually requires `topicPattern`.
- Placeholder fails to resolve as expected.
- Listener is created by a different `containerFactory` than the one being configured.

If using properties:

~~~java
@KafkaListener(
        id = "orders-listener",
        topics = "${app.kafka.orders-topic}",
        groupId = "${app.kafka.orders-group}"
)
public void consume(OrderEvent event) {
    orderService.process(event);
}
~~~

Check property values after Spring loads profiles. You can log topic names and group IDs at startup, without logging credentials or full sensitive configurations.

If subscribing via regex, verify the pattern matches real topic names and the consumer refreshes metadata to discover new topics. If a topic is created after the listener starts, discovery timing also depends on subscription mode and metadata refresh.

## 5. Check Whether the Listener Container Is Running

Spring Kafka manages listeners via listener containers. Having an annotated method does not mean the listener receives records if its container has not started.

Example listener with auto-startup disabled:

~~~java
@KafkaListener(
        id = "orders-listener",
        topics = "orders",
        groupId = "order-service",
        autoStartup = "false"
)
public void consume(OrderEvent event) {
    orderService.process(event);
}
~~~

With `autoStartup=false`, the application must start the container explicitly. You can inspect it via `KafkaListenerEndpointRegistry`:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("orders-listener");

if (container == null) {
    log.error("Listener container was not registered");
}
else {
    log.info(
            "Listener container running={}",
            container.isRunning()
    );
}
~~~

If the container is not running, check:

- `autoStartup` on `@KafkaListener` or the container factory.
- Whether the listener bean is component-scanned and instantiated by Spring.
- Whether the `ApplicationContext` finished startup.
- Whether logs show consumer creation or container startup errors.
- Whether another component called `stop()` or `pause()`.
- Whether listener IDs collide or the registry lookup uses the wrong ID.

`isRunning()` only indicates container lifecycle state. It does not prove the consumer has been assigned partitions. Check assignments or the consumer group to confirm the listener has a record source.

## 6. Check Consumer Group and Partition Assignment

Kafka distributes partitions among consumers within the same group. Each partition is assigned to at most one consumer in the group at any given time. If a group has more consumers than partitions, some consumers stay idle.

Inspect group status:

~~~bash
kafka-consumer-groups.sh   --bootstrap-server localhost:9092   --describe   --group order-service
~~~

The output typically includes these columns:

| Column | Meaning |
|---|---|
| GROUP | Consumer group ID |
| TOPIC | Consumed topic |
| PARTITION | Described partition |
| CURRENT-OFFSET | Committed offset of the group |
| LOG-END-OFFSET | Current end offset of the partition |
| LAG | Difference between log end and committed position reported by the tool |
| CONSUMER-ID | Assigned consumer instance |
| HOST | Consumer host |
| CLIENT-ID | Client ID |

How to read it:

- No topic/partition rows: the group may not be subscribed to the topic, may be inactive, or may have no assignment/offsets shown by the tool.
- Empty `CONSUMER-ID`: the partition is not assigned to an active consumer.
- Continuously rising `LAG`: the consumer is falling behind the producer or is not processing.
- Advancing `CURRENT-OFFSET`: the group is committing progress, though you still need to verify whether the listener completes business logic.
- `LAG` equals 0: the group has caught up to the committed view at measurement time; this does not mean older records were definitely read if the offset was initialized at log end.

If one group is shared by multiple unrelated services, those consumers will split partitions among themselves. Each service that needs every event independently should generally use its own group ID. Conversely, instances of the same logical service typically share a group ID to balance load.

## 7. Check Whether the Consumer Group ID Is Right

The group ID determines which offsets are used. It can be configured via Spring Boot:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: order-service
      auto-offset-reset: earliest
~~~

Or specified directly in the annotation:

~~~java
@KafkaListener(
        topics = "orders",
        groupId = "order-service"
)
public void consume(OrderEvent event) {
    orderService.process(event);
}
~~~

If the annotation specifies `groupId`, check whether it overrides the default group ID you are inspecting in the CLI.

A common mistake is having the producer and consumer on the right topic while the operator inspects the wrong group. The actual consumer might be using a different group ID due to profiles, placeholders, or annotation attributes.

Do not generate a random group ID in production on every startup if you need to resume from prior offsets. A brand-new group has no committed offsets, so its starting behavior depends on `auto.offset.reset`.

## 8. Check Committed Offsets and `auto.offset.reset`

`auto.offset.reset` applies only when a group has no valid committed offset for a partition. It does not rewind data once a group already has an offset.

Two common values:

| Value | Behavior when no valid offset exists |
|---|---|
| earliest | Starts from the earliest retained offset |
| latest | Starts from the end of the log at the time the consumer needs a reset |

Example:

1. Producer has already written 100 records.
2. A new consumer group starts with `auto.offset.reset=latest`.
3. The consumer positions itself at the end of the log.
4. No new records arrive afterward, so the listener is never invoked.

This is a frequent cause when a topic has data yet a new consumer receives zero records.

Configuration:

~~~yaml
spring:
  kafka:
    consumer:
      auto-offset-reset: earliest
~~~

Only use `earliest` when business logic wants to read retained data for a group without offsets. Once a group has committed offsets, changing `latest` to `earliest` will not make that group re-read from the beginning automatically.

To replay, perform an intentional offset reset with impact analysis and a clear runbook. Never run `--reset-offsets` on a production group just to experiment without determining partition scope and duplicate-processing consequences.

## 9. Check Deserialization Before the Listener

If the Kafka consumer cannot deserialize the key or value, the `@KafkaListener` method might never be called. The error happens when converting bytes to objects, before the payload reaches the listener.

Example JSON configuration:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: "com.example.events"
        spring.json.value.default.type: "com.example.events.OrderEvent"
~~~

Verify that producer and consumer agree on:

- Matching serializer and deserializer.
- Actual schema/DTO sent.
- Header type mapping if using JSON type headers.
- Trusted packages and default type.
- Class versions and field compatibility.
- Charset/format if using a custom serializer.

In Spring Kafka, `ErrorHandlingDeserializer` turns deserialization errors into metadata that the error handler can process:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.trusted.packages: "com.example.events"
        spring.json.value.default.type: "com.example.events.OrderEvent"
~~~

Check consumer and error handler logs. A record that fails deserialization can be handled by a recoverer/DLT policy without calling the business listener. If you only look for logs inside the listener method, you will miss the cause.

Do not widen trusted packages overly in production unless necessary. Deserialization configuration must match data sources and security policies.

## 10. Check `isolation.level` and Kafka Transactions

A consumer can be configured to read only records from committed transactions:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        isolation.level: read_committed
~~~

With `read_committed`, the consumer does not return records belonging to uncommitted or aborted transactions. If a producer transaction remains open on a partition, the Last Stable Offset (LSO) can cap how far the consumer is allowed to read. Records after an open transaction may be held back until that transaction finishes.

This can make the consumer look as if it is not receiving new records even though the log end offset increases. Check whether producer transactions are stuck, hitting transaction timeouts, failing to commit, or experiencing producer fencing.

If the application does not use transactional producers and does not need to filter out aborted records, `read_uncommitted` may fit requirements. Do not change isolation level just to make records show up without understanding the required data semantics.

## 11. Check Whether the Listener or Partition Is Paused

The container may still report `isRunning` while the consumer is paused. When paused, the container keeps polling to maintain group membership, but paused partitions stop delivering new records to the listener.

You can check pause state through the container API appropriate for your Spring Kafka version. If the application uses pause/resume for backpressure, inspect whether a controller calls `pause()` or `pausePartition()` and has matching resume conditions.

Common causes:

- Internal queue hits a high watermark.
- Downstream returns errors and a controller pauses the consumer.
- A partition gets paused and is never resumed after recovery.
- The container was paused via an administrative action.
- State-control logic drifts out of sync after a rebalance or restart.

Distinguish pause from stop: pause keeps the consumer inside the group; stop closes the consumer and triggers a group rebalance. When records are not received, check both states.

## 12. Check Poll Interval and Blocked Listeners

Kafka consumers must poll periodically. If synchronous listener processing takes too long, the consumer may fail to call poll within `max.poll.interval.ms`. When exceeded, the consumer can leave the group and its partitions are reassigned.

Related settings:

| Setting | Role |
|---|---|
| `max.poll.interval.ms` | Maximum time between polls before the consumer is considered stalled |
| `max.poll.records` | Maximum number of records returned in a single poll |
| `session.timeout.ms` | Time the coordinator waits for missed consumer heartbeats before removing it from the group under the group protocol |
| `heartbeat.interval.ms` | Heartbeat interval in protocols supporting this setting |
| Container `pollTimeout` | Time the container waits for a single poll to return data |

If a listener calls APIs without timeouts or processes large batches too slowly, the consumer may repeatedly rebalance and fail to process steadily.

Remediation:

- Set timeouts on HTTP/database calls.
- Lower `max.poll.records` if each record takes significant time.
- Optimize processing and batching.
- Raise `max.poll.interval.ms` only when processing time is justified and measured.
- Avoid long sleeps inside listeners.
- Use async processing with explicit offset management and backpressure.

Increasing `max.poll.interval.ms` does not make slow dependencies faster. It only changes the threshold before the consumer is considered stalled.

## 13. Check Listener Filters and Interceptors

Records may be received from Kafka yet never reach the listener method because they are filtered or modified in the container pipeline.

Inspect:

- `RecordFilterStrategy` on the listener container factory.
- `FilteringMessageListenerAdapter`.
- `RecordInterceptor`.
- `BatchInterceptor` if using a batch listener.
- Custom deserializer or message converter logic.
- Whether an error handler/recoverer skips or redirects records elsewhere.

Example filter:

~~~java
factory.setRecordFilterStrategy(
        record -> record.value() == null
);
~~~

With this configuration, records with a null value are discarded before the listener according to the filter. Depending on `ackDiscarded` and container semantics, discarded records may be acknowledged/committed as handled. Check whether a filter accidentally drops all records due to a faulty condition.

Temporarily instrument before and after the filter in a test environment to pinpoint where the record disappears. Avoid logging entire sensitive payloads.

## 14. Check Bootstrap Servers, `advertised.listeners`, and Network

A producer may reach the bootstrap server while a consumer running in another environment cannot reach the brokers advertised in metadata.

Kafka clients use `bootstrap.servers` to fetch cluster metadata, then connect to the broker endpoints advertised via `advertised.listeners`. If those addresses are only reachable on an internal network or have wrong DNS/ports, the consumer may connect initially yet fail when fetching from leaders.

Check:

- `spring.kafka.bootstrap-servers` matches the environment.
- Broker DNS and ports are reachable from the consumer's pod/VM.
- `advertised.listeners` publishes hostnames/ports reachable by the client.
- Firewalls, network policies, and service meshes do not block traffic.
- TLS truststore/keystore and hostname verification.
- SASL mechanism, username/password, and JAAS config.
- ACLs allow the consumer `DESCRIBE`/`READ` on the topic and `READ` on the group.

If authorization, authentication, or disconnect errors appear, check Kafka client and broker logs. Never write SASL passwords, private keys, or tokens to logs.

## 15. Check Topic Partitions and Concurrency

A consumer group can process in parallel at most up to the number of assigned partitions. If a topic has three partitions while listener concurrency is eight, at most three consumers hold assignments in the group at a time; the remaining consumers stay idle.

If a partition lacks a leader or has abnormal ISR replicas, the consumer may be unable to fetch data from that partition.

Inspect topic:

~~~bash
kafka-topics.sh   --bootstrap-server localhost:9092   --describe   --topic orders
~~~

Inspect group:

~~~bash
kafka-consumer-groups.sh   --bootstrap-server localhost:9092   --describe   --group order-service
~~~

If only one partition is not being processed, focus on leader, assignment, key distribution, paused partitions, and record errors in that partition. If no partitions are processed at all, focus on subscription, group, connectivity, and lifecycle.

## 16. Check Spring Boot Consumer Configuration

A baseline configuration must stay consistent across the broker, group, and serializers:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-service
      auto-offset-reset: earliest
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: "com.example.events"
        spring.json.value.default.type: "com.example.events.OrderEvent"
~~~

This example only applies when the producer sends JSON compatible with `OrderEvent`. If the application uses Avro, Protobuf, or custom serializers, substitute the deserializer and registry properties for the actual format.

With Spring Kafka listener containers, offsets are usually managed by the container's `AckMode`. `enable.auto.commit=false` is common so the container manages commits. If enabling auto-commit or using manual acknowledgment, understand clearly when offsets get committed.

Avoid changing multiple settings simultaneously during diagnosis. Adjust one factor at a time with a hypothesis, re-measure group/lag, and record the result to identify which change fixed the problem.

## 17. An Outside-In Diagnostic Workflow

Work through these steps in sequence:

1. **Producer:** confirm send future/callback succeeded and captured topic/partition/offset.
2. **Topic:** check the topic is on the right cluster with partitions and leaders.
3. **Console read:** use a separate temporary consumer to confirm records exist.
4. **Listener lifecycle:** confirm the bean is created, listener ID registered, and container running.
5. **Subscription:** confirm the exact topic/pattern the listener subscribes to.
6. **Consumer group:** inspect group ID, members, partition assignments, and lag.
7. **Offset:** check committed offsets and `auto.offset.reset`.
8. **Deserialization:** check serializer/deserializer errors and the error handler.
9. **Isolation:** check `read_committed` and open transactions.
10. **Pause/filter:** check container/partition pause state and record filters/interceptors.
11. **Poll:** check blocked listeners, `max.poll.interval.ms`, and rebalances.
12. **Network/security:** check `advertised.listeners`, ACLs, TLS, and SASL.

Require evidence at each step. For example, if the console consumer reads records and the group has no assignment, do not tweak the serializer first; investigate subscription, group, and listener lifecycle.

## 18. Symptom-to-Cause Matrix

| Observed symptom | Possible cause | Next check |
|---|---|---|
| Producer send timeout | Broker/network or metadata | Producer logs, broker health |
| Topic does not exist | Wrong name/cluster or unprovisioned | `kafka-topics --describe` |
| Console reads, app does not | Group/subscription/offset/listener | Consumer group and container |
| Group has no members | Container not started or connection error | Listener registry and client logs |
| Group has members, no assignment | Subscription mismatch, partition metadata, or rebalance | Topic describe and group state |
| Lag is 0, no callback | Offset at log end or no new records | Current offset, log end, and send timestamp |
| Lag rises continuously | Consumer not polling or slow processing | Processing time, polls, rebalances |
| Deserialization exception | Incompatible payload/schema | Delegate deserializer and DLT |
| Only records in uncommitted transactions missing | `read_committed`/LSO | Producer transaction state |
| Listener running yet not receiving | Paused, filtered, or unassigned | Pause state, interceptor, assignment |
| Disconnect/authentication errors | Network, TLS, SASL, ACLs | Client/broker security logs |

## 19. Operations Requiring Caution

Certain actions can alter data-reading behavior:

- Resetting offsets to `earliest` can replay all retained data.
- Creating a new group ID can read from the beginning or end depending on `auto.offset.reset`.
- Running a console consumer under the production group can steal partitions from the application.
- Deleting a topic destroys data and topic metadata.
- Increasing partitions can alter key-to-partition mapping and ordering.
- Disabling `read_committed` can expose records from aborted transactions to the consumer.
- Disabling filters or switching deserializers can let malformed data enter the business listener.

Only perform these operations after defining the goal, partition scope, and duplicate-handling capability. In production, require a runbook and clear ownership for offset/topic operations.

## 20. Quick Troubleshooting Checklist

- [ ] Producer received acknowledgement and logged topic/partition/offset.
- [ ] Topic exists on the right cluster and has leaders for its partitions.
- [ ] A separate temporary console consumer can read records.
- [ ] `@KafkaListener` subscribes to the right topic or pattern.
- [ ] Listener bean is registered and the container is running.
- [ ] Container is neither paused nor stopped.
- [ ] Consumer group ID matches the group being inspected.
- [ ] Group has active members and partition assignments.
- [ ] Committed offsets and log end offsets have been compared.
- [ ] `auto.offset.reset` is understood properly; not confused with resetting committed offsets.
- [ ] Key/value deserializers and schemas are compatible.
- [ ] `ErrorHandlingDeserializer`/error handler is not silently routing records to a DLT.
- [ ] `isolation.level` and transaction state are not blocking uncommitted records.
- [ ] Listener is not blocked past `max.poll.interval.ms`.
- [ ] Filters/interceptors are not dropping records unintentionally.
- [ ] Bootstrap servers, `advertised.listeners`, TLS, SASL, and ACLs are valid.
- [ ] Diagnostic tools do not share the production group.
- [ ] Metrics for lag, assignment, processing time, and error logs are monitored after fixing.

When a consumer receives no records, trace the record from producer to topic, then from topic through group, assignment, offset, and listener container. Clearly distinguish having no new records from sitting at the end offset, lacking a partition assignment, having records paused/filtered, or hitting deserialization errors before the listener. Layered diagnosis backed by metrics, CLI, and logs finds the real cause without risky offset resets or topology changes.

