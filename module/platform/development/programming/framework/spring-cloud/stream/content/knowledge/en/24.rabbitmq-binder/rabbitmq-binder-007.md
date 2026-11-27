# Quorum Queues and Choosing the Right Queue Type

RabbitMQ supports multiple message storage types, among which classic queues, quorum queues, and streams address different needs. Classic queues fit traditional queue models when a single copy suffices. Quorum queues replicate copies across multiple nodes and use the Raft algorithm to maintain state when a node fails. RabbitMQ streams are durable logs that allow multiple consumers to re-read data by offset instead of removing messages once acknowledged by one consumer.

The Spring Cloud Stream RabbitMQ binder maps logical destinations to exchanges and queues per consumer group. For standard queues, the binder creates classic queues by default. You can configure `quorum.enabled` so the binder creates a quorum queue for the group queue; dead-letter queues also have separate configuration. The binder also supports the RabbitMQ Stream Plugin with dedicated container and producer settings. Choosing the right storage type should be based on requirements for availability, replay, fan-out, retention, ordering, and operational cost.

This lesson explains the differences among classic queues, quorum queues, and streams; how the RabbitMQ binder declares these types; how to choose quorum size, handle poison messages and dead-lettering; important limitations; and how to deploy, test, and migrate queues safely.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish between classic queues, quorum queues, and RabbitMQ streams.
- Explain quorum, leader/follower roles, and Raft-based replication.
- Choose quorum queues for workloads requiring high durability and availability.
- Configure quorum queues using the RabbitMQ binder for a consumer group.
- Configure quorum size, delivery limits, and dead-letter queues.
- Understand the limitations of quorum queues compared to classic queues.
- Distinguish destructive-consumption queues from replayable streams.
- Use RabbitMQ Stream Plugin support in the binder for appropriate use cases.
- Plan migrations and test failures, redelivery, and DLQs.

## 1. Queue Type Determines Storage Semantics

In RabbitMQ, an exchange receives messages from producers and routes them to queues or streams according to bindings. A queue stores messages until consumers process and acknowledge them; a stream stores a log that multiple consumers can re-read.

Three main options:

| Type | Storage structure | Replication | Reading model | Typical use case |
|---|---|---|---|---|
| Classic queue | Traditional FIFO queue | Does not replicate queue state across nodes in RabbitMQ 4.x | Destructive consume: messages are removed after ack | General work queues, regenerable data, or modest HA needs |
| Quorum queue | Queue with leader and followers | Raft-based replication, requires majority to progress | Destructive consume, with ack and redelivery | Orders, payments, critical tasks needing HA |
| Stream | Append-only log | Replicated, durable | Non-destructive; consumers read by offset and can replay | Event logs, massive fan-out, replay, long backlogs, and high throughput |

Queue type is not merely a performance option. It affects how data survives failures, how consumers re-read messages, how dead-lettering behaves, and how operators scale the topology.

## 2. Classic Queues

Classic queues are RabbitMQ's traditional queue type. They support exchanges/bindings, acknowledgments, prefetch, message TTL, queue TTL, priority, queue length limits, and dead-letter exchanges.

### 2.1. Characteristics

- A classic queue does not replicate message state across multiple nodes.
- The queue can be durable; messages can be persistent to survive restarts depending on storage settings.
- Consumers receive messages and ack; after successful ack, the message is removed from the queue.
- Supports temporary queues, exclusive queues, and auto-delete queues.
- Supports many traditional queue features such as priority and TTL.

Durable queues and persistent messages help recover after restarts, but they do not mean the queue is replicated across nodes. If the node hosting a classic queue suffers a severe failure, recovery depends on the specific storage volume and configuration.

### 2.2. When to Choose Classic Queues?

Classic queues are suitable when:

- The workload can tolerate a single-node queue copy.
- Messages can be regenerated or data-loss impact is deemed acceptable.
- Temporary, exclusive, or auto-delete queues are needed.
- The workload needs classic features that quorum queues do not support.
- The topology has a large number of queues and requires a smaller footprint.

In RabbitMQ 4.0 and later, classic queues no longer have mirrored queue replication. If a replicated, highly available queue is needed, evaluate quorum queues or streams.

## 3. Quorum Queues

A quorum queue is a durable, replicated queue based on the Raft consensus algorithm. Each quorum queue has one leader and multiple followers. The leader handles write operations; changes are replicated to members. An operation must be confirmed by a majority of members to be considered committed.

### 3.1. What Does Quorum Mean?

With $N$ members, a majority is:

\[
Q = \left\lfloor \frac{N}{2} \right\rfloor + 1
\]

Examples:

| Members | Required majority | Members that can be lost while retaining majority |
|---:|---:|---:|
| 1 | 1 | 0 |
| 3 | 2 | 1 |
| 5 | 3 | 2 |
| 7 | 4 | 3 |

A three-member quorum queue can continue operating when one member is unavailable, as long as the remaining two members can communicate and form a majority. If majority is lost, the queue cannot make progress on consensus-requiring operations until majority is restored.

Odd quorum sizes are generally preferred because adding a member from an even to an odd count increases fault tolerance; adding a member from an odd to an even count generally does not increase the number of nodes that can be lost while retaining majority.

### 3.2. Leader and Followers

~~~text
Quorum queue: orders.fulfillment

Node A: Leader
   | \
   |  \ replicate log
   v   v
Node B: Follower
Node C: Follower

Majority = 2 of 3 members
~~~

If the leader fails, the remaining members can elect a new leader. Failover time depends on cluster state, network, and whether followers have the required log entries. Consumers may experience a brief interruption while a new leader is elected.

Replication does not eliminate every failure. If a network partition breaks majority or multiple nodes fail together, the queue may temporarily stop accepting/delivering messages. Quorum queues prioritize consistency and data safety over continuing writes on an isolated minority.

### 3.3. Data Characteristics

- Quorum queues are always durable; non-durable queues are not supported.
- Quorum queues do not support exclusive or temporary queues.
- Messages are stored durably across members according to quorum queue semantics.
- Built-in poison message handling and delivery limits.
- Supports dead-letter exchanges; can be configured for at-least-once dead-lettering under specific conditions.
- Supports TTL and queue length limits, though some overflow/dead-letter combinations are restricted.

Quorum queues suit long-lived queues holding critical work—such as payment instructions, orders to fulfill, or business requests that must not be lost when a node stops.

## 4. When Should You Choose Quorum Queues?

Choose quorum queues when the primary requirement is a highly durable work queue capable of continuing operation when a RabbitMQ node fails.

Examples:

- Accepting orders and payment commands.
- Critical background tasks that must be redelivered after consumer or node failures.
- Business processing queues where losing a message corrupts system state.
- Queues requiring leader election and replication rather than a single copy.

Do not convert every queue to a quorum queue just because quorum offers replication. A system with thousands of small queues, temporary queues, RPC reply queues, or regenerable messages may not need replication overhead for every queue.

### 4.1. Cases Where Quorum Is Not the Best Choice

| Requirement | Reason to reconsider |
|---|---|
| Temporary, exclusive, or auto-delete queues | Quorum queues do not support temporary queue semantics |
| Short-lived RPC reply queues | Replication typically does not justify the overhead |
| Regenerable messages without HA requirements | Classic queues can be simpler |
| Large fan-out where many subscribers need to re-read | Streams may be a better fit |
| Long-term event logs | Streams support offsets and replay more naturally |
| Millions of messages retained long-term | Streams are generally better suited than traditional queues |

Quorum queues are a strong choice for many critical work queues, but not a universal replacement for every queue type.

## 5. Configuring Quorum Queues with the Spring Cloud Stream RabbitMQ Binder

By default, the RabbitMQ binder creates classic queues for consumer groups. You can set the consumer property `quorum.enabled` to `true` to create a quorum queue instead of a classic queue.

Example:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: fulfillment
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              quorum:
                enabled: true
                initialGroupSize: 3
                deliveryLimit: 10
~~~

In this example:

- `destination` is the logical exchange name used by the binder.
- `group` creates a dedicated queue for the consumer group, typically named after destination and group.
- `quorum.enabled` instructs the binder to declare the queue as a quorum queue.
- `quorum.initialGroupSize` sets the initial number of quorum members when the queue is created.
- `quorum.deliveryLimit` sets the delivery limit before a message is dropped or dead-lettered per broker configuration.

Quorum properties are Rabbit-binder-specific properties under the prefix `spring.cloud.stream.rabbit.bindings.<binding>.consumer`. Use the exact actual binding name, such as `processOrder-in-0`.

### 5.1. Using Properties Format for Easy Comparison

~~~properties
spring.cloud.stream.bindings.processOrder-in-0.destination=orders
spring.cloud.stream.bindings.processOrder-in-0.group=fulfillment
spring.cloud.stream.rabbit.bindings.processOrder-in-0.consumer.quorum.enabled=true
spring.cloud.stream.rabbit.bindings.processOrder-in-0.consumer.quorum.initialGroupSize=3
spring.cloud.stream.rabbit.bindings.processOrder-in-0.consumer.quorum.deliveryLimit=10
~~~

If your binder version does not recognize these properties, check your Spring Cloud Stream Rabbit binder version and its configuration metadata. Do not assume every version exposes the exact same property set.

### 5.2. Provisioning Queues Before Consumers Run

The Rabbit binder can declare queues when the consumer binding is created. For producers that need to provision queues for groups before consumers start, use `requiredGroups` on the producer binding. Producer-side quorum properties apply only to groups declared in `requiredGroups`.

Example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders
          producer:
            required-groups:
              - fulfillment
      rabbit:
        bindings:
          publishOrder-out-0:
            producer:
              quorum:
                enabled: true
                initialGroupSize: 3
                deliveryLimit: 10
~~~

`required-groups` lets the binder create queues for the specified groups even before consumers are deployed. Without `requiredGroups`, producer-side quorum properties have no group queues to apply to.

### 5.3. Quorum Queues and Dead-Letter Queues

The source quorum queue and the dead-letter queue are two separate queues and can have different types. The Rabbit binder provides `dlqQuorum.enabled` to create the DLQ as a quorum queue when the binder provisions the DLQ for a required group or consumer.

Example consumer configuration:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: fulfillment
          consumer:
            max-attempts: 3
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              quorum:
                enabled: true
                deliveryLimit: 10
              autoBindDlq: true
              dlqQuorum:
                enabled: true
~~~

`max-attempts` is the binder container's retry count. `quorum.deliveryLimit` is the broker-side delivery limit for quorum queues; the two properties address different retry layers. Check how the binder rejects/requeues messages to avoid unintended interactions between container retries and broker delivery limits.

If managing DLX/DLQ manually, configure the topology in RabbitMQ and disable the corresponding binder auto-declaration options to avoid conflicting declarations.

## 6. Quorum Size and Placement

A quorum queue can only tolerate node failures if its members are distributed across independent nodes. Setting `initialGroupSize` to 3 when all three members depend on the same node or failure domain does not provide genuine HA.

### 6.1. Choosing the Member Count

Common configurations:

- 3 members for most critical queues, tolerating the loss of 1 member.
- 5 members when tolerating 2 member losses is required and higher replication overhead is acceptable.
- Avoid increasing member count merely to increase consumer count; replication member count and consumer concurrency are separate concepts.

More members increase replication traffic, disk I/O, and network load. Balance fault tolerance against operational cost.

### 6.2. Placing Members Across Multiple Nodes or Availability Zones

In a multi-node cluster, RabbitMQ manages queue members. Distribute members across distinct nodes and failure domains, such as separate availability zones if supported by infrastructure.

If both the leader and followers reside on the same physical host or zone that can fail together, the quorum queue cannot protect against that shared failure. Verify actual placement rather than looking only at member count.

### 6.3. Changing Members After Creation

`initialGroupSize` is the initial member count when the queue is declared. It is not a mechanism that automatically resizes replicas on every application restart. RabbitMQ has dedicated membership management and reconciliation tools; use supported administrative commands or policies/features to change topology.

Do not delete a production queue to change quorum size without a drain, backup, or data migration plan. Membership changes should be tested both under normal operation and under node disconnection.

## 7. Poison Messages and Delivery Limits

A poison message is a message that repeatedly causes the consumer to fail and gets requeued, so it is never successfully acknowledged. Without a limit, a single bad message can create a redelivery loop and consume resources.

Quorum queues track failed redelivery attempts and can enforce a delivery limit. Once the limit is exceeded, the message is dropped or dead-lettered if the queue has a DLX.

Binder example:

~~~yaml
spring:
  cloud:
    stream:
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              quorum:
                enabled: true
                deliveryLimit: 10
              autoBindDlq: true
~~~

`deliveryLimit` is a quorum queue property and depends on the broker version. Default values may be determined by the RabbitMQ broker; for consistent behavior across environments, configure it explicitly and test it.

### 7.1. Delivery Limit vs. Binder Retries

Binder retries can re-invoke the listener inside the container before the message is rejected. Quorum queue delivery limits track failed deliveries at the broker level. If the binder retries three times within a single delivery and then rejects, the broker's delivery count may not increment by three in the same way application retries are counted.

Clarify:

- How many times the listener is invoked within one delivery.
- When the binder rejects or requeues.
- When the broker increments delivery count.
- What happens when the delivery limit is exceeded.
- Whether a DLX is configured to retain failed messages.

### 7.2. RabbitMQ 4.3 and nack/reject

Starting with RabbitMQ 4.3, quorum queue delivery limits are based on delivery-count. Certain ways of returning messages via `basic.nack` may not increment the delivery count the same way earlier versions did. If an application relies on delivery limit to stop poison messages while using `nack` with `requeue=true`, verify your broker version's semantics and consider `basic.reject` per RabbitMQ guidance.

Do not rely on delivery limit as the sole safeguard. Binder retries, dead-lettering, idempotency, and logging are still essential.

## 8. Dead-Lettering and At-Least-Once Dead-Lettering

Quorum queues support dead-letter exchanges. However, default dead-lettering can be at-most-once: a message is moved off the source queue and can be lost if the target fails to accept it in certain scenarios.

RabbitMQ supports at-least-once dead-lettering for quorum queues under specific configuration conditions:

- `dead-letter-strategy` must be `at-least-once`.
- `overflow` must be `reject-publish`.
- The queue must have a `dead-letter-exchange`.
- On versions requiring it, the broker's `stream_queue` feature flag must be enabled.

Keys `dead-letter-strategy`, `overflow`, and `dead-letter-exchange` are typically configured via RabbitMQ policies. Verify broker version, feature flags, and policy matching for the target queue before enabling this mechanism.

In this mode, the source queue retains the dead-lettered message until the destination queue confirms receipt. This reduces message loss risk during transfer, though it can create duplicates at the destination if confirms are lost or retried.

### 8.1. Why Are Length Limits Necessary?

At-least-once dead-lettering holds messages on the source queue while the destination has not confirmed. If the DLX or target queue is unavailable for an extended period, dead-lettered messages can continue occupying space on the source queue.

Configure appropriate `max-length` or `max-length-bytes` and monitor queue depth, disk, and memory. `overflow: reject-publish` can cause publishers to be rejected when the queue is full; applications must handle publish nacks/returns and retries.

### 8.2. Do Not Confuse Binder Republish with Broker Dead-Lettering

The Rabbit binder can retry in the container and then republish failed messages to a DLQ with exception headers. That is binder-driven behavior. RabbitMQ broker dead-lettering routes messages via DLX when messages are rejected, exceed TTL, or hit certain queue limits.

The two mechanisms can differ in metadata, confirms, duplicates, and target routing. Establish one clear policy so you do not accidentally both republish and broker-dead-letter the same stream.

## 9. RabbitMQ Streams and Super Streams

A RabbitMQ stream is a different data structure from a traditional queue. A stream is an append-only, replicated, and durable log. Consumers read by offset; one consumer reading a message does not delete it from the stream. Multiple consumers can read the same data independently and replay from older offsets within the retention window.

### 9.1. When to Choose Streams?

Streams are well suited when:

- Multiple consumers need to re-read the same event log.
- Replay or reading from an offset/timestamp is required.
- Large fan-out is needed without creating a separate queue per subscriber.
- Long backlogs or throughput-oriented workloads exist.
- A durable log model is preferred over a destructive work queue.

Streams do not replace quorum queues for every use case. Traditional work queues where messages disappear after ack still fit queues best. Streams retain data based on retention policies and consumer offsets.

### 9.2. Streams vs. Quorum Queues

| Aspect | Quorum queue | RabbitMQ stream |
|---|---|---|
| Model | Raft-based replicated queue | Replicated append-only log |
| Reading | Destructive consume; ack removes message from queue | Non-destructive; consumers read by offset |
| Replay | Not a natural post-ack re-read model | Supports replay within retention |
| Dead-letter exchange | Yes | No DLX like traditional queues |
| TTL | Message/queue TTL with certain limitations | Uses retention instead of queue TTL |
| Priority | Strict priority | Does not support message priority |
| Work distribution | Suited for worker queues | Suited for logs/fan-out/replay |

Streams require the appropriate plugin and client/protocol. You cannot enable a stream by setting `quorum.enabled=true`; they are two different storage types.

## 10. RabbitMQ Stream Plugin Support in the Binder

The Spring Cloud Stream Rabbit binder provides initial support for the RabbitMQ Stream Plugin. To use it, the classpath must include `spring-rabbit-stream` matching the corresponding `spring-amqp` and `spring-rabbit` versions.

### 10.1. Stream Consumer

You can configure the consumer container type to `stream`:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        audit-in-0:
          destination: audit-stream
          group: audit-reader
      rabbit:
        bindings:
          audit-in-0:
            consumer:
              containerType: stream
~~~

With a stream container, many consumer properties designed for queues are not supported. The binder reference notes that concurrency is only supported for super streams; each stream binding normally consumes a single stream queue. Offset selection, offset tracking, and consumer naming may require customizers.

### 10.2. Super Streams

A super stream is a logical stream partitioned into multiple stream partitions. It is useful when scaling consumers by partition while keeping log semantics.

The binder supports super stream consumers using instance count, concurrency, container type, and `super-stream`:

~~~properties
spring.cloud.stream.bindings.audit-in-0.destination=audit
spring.cloud.stream.bindings.audit-in-0.group=audit-reader
spring.cloud.stream.bindings.audit-in-0.consumer.instance-count=3
spring.cloud.stream.bindings.audit-in-0.consumer.concurrency=3
spring.cloud.stream.rabbit.bindings.audit-in-0.consumer.container-type=STREAM
spring.cloud.stream.rabbit.bindings.audit-in-0.consumer.super-stream=true
~~~

The super stream topology and partition count are provisioned by the binder according to configuration. Verify partition mapping, routing keys, and offsets before deploying multiple instances.

### 10.3. Stream Producer

The Rabbit binder supports these producer types:

- `AMQP`: uses the AMQP client for classic and quorum queues.
- `STREAM_SYNC`: uses the RabbitMQ Stream Plugin client and waits for confirms.
- `STREAM_ASYNC`: uses the RabbitMQ Stream Plugin client asynchronously.

Example producer configuration:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishAudit-out-0:
          destination: audit-stream
      rabbit:
        bindings:
          publishAudit-out-0:
            producer:
              producerType: STREAM_SYNC
~~~

When using `STREAM_SYNC` or `STREAM_ASYNC`, producer properties meant for AMQP queues may not be supported. Consult the binder reference for stream producers and do not copy quorum queue settings onto stream producers.

## 11. Key Limitations When Switching to Quorum Queues

Quorum queues share many behaviors with classic queues, but have differences you must verify:

- Non-durable queues are not supported.
- Exclusive queues are not supported; use single active consumer if one active and standby consumer is needed.
- Global QoS prefetch is not supported; use per-consumer prefetch.
- Delivery limits and poison message handling are built in.
- At-least-once dead-lettering is supported but requires `overflow: reject-publish` and DLX configuration.
- Priority uses strict priority; not all classic queue priority semantics are identical.
- Certain queue features and arguments have specific restrictions.

Before enabling `quorum.enabled`, check whether any existing queue has the matching type. Queue type is set at declaration time and cannot be changed via policy. If the binder tries to declare a quorum queue over an existing classic queue of the same name, RabbitMQ may return `PRECONDITION_FAILED` due to an `x-queue-type` argument mismatch.

## 12. Migrating from Classic to Quorum

An existing classic queue cannot be converted in place to a quorum queue simply by changing binder configuration. RabbitMQ does not alter queue type in place.

A safe migration workflow:

1. Identify the active queues, exchanges, bindings, and consumer groups.
2. Assess backlog, unacknowledged messages, and whether producers can pause.
3. Create a new quorum queue with a new name or destination.
4. Verify member count, placement, and DLX/DLQ.
5. Switch producers or bindings in a controlled phase.
6. Drain the old queue or process remaining messages as planned.
7. Move consumers to the new queue.
8. Monitor publisher confirms, redeliveries, queue depth, and consumer health.
9. Delete the old queue only after confirming no needed data remains.

If the queue name must stay unchanged, you may need to stop consumers, drain or copy messages, delete the old queue, and redeclare it with the new type. This is a potentially disruptive topology change requiring a backup/rollback plan.

### 12.1. Pre-Created Queues

If RabbitMQ infrastructure is managed by a platform team, the application can configure the binder not to auto-declare or bind queues. Operations must then create the exchange, queue, type, and bindings beforehand.

Do not let both the binder and infrastructure declare the same queue with incompatible parameters. All changes to `x-queue-type`, durability, exclusivity, and arguments must be coordinated between application deployment and broker provisioning.

## 13. Testing Quorum Queues

Tests should verify both declared configuration and behavior under node failures.

### 13.1. Testing Queue Type

With a RabbitMQ test broker:

1. Start a broker supporting quorum queues.
2. Start the Spring Cloud Stream application with a fixed consumer binding group and `quorum.enabled=true`.
3. Verify the created queue has argument `x-queue-type=quorum`.
4. Verify the initial group size matches configuration.
5. Send messages and verify consumers receive, process, and ack them successfully.

Do not only verify that properties bind into the Spring context. Inspect the actual queue via the RabbitMQ Management API or CLI.

### 13.2. Testing Leader Failure

In a multi-node test cluster:

- Identify the node currently serving as the queue leader.
- Stop or isolate that node in a controlled test.
- Observe leader election and recovery time.
- Verify consumers reconnect and continue processing.
- Verify confirmed messages are not lost beyond the guaranteed semantics.

Do not run node-kill experiments in production without operational planning and approval.

### 13.3. Testing Poison Messages and DLQs

Send a message that causes the listener to fail consistently. Verify:

- Binder retries execute the expected number of times.
- Messages are rejected/requeued as configured.
- The quorum queue's delivery limit operates per your broker version.
- Messages are dead-lettered or dropped according to policy.
- The DLQ has the expected queue type if `dlqQuorum.enabled=true`.
- Consumers can continue processing subsequent valid messages.

### 13.4. Testing Streams Separately

If using streams, test offset tracking, replay, retention, and super stream partition assignment. Do not extrapolate stream behavior from quorum queue tests, since consume and storage semantics differ.

## 14. Observability and Operations

Quorum queues require monitoring both queue state and cluster state:

| Metric | Meaning |
|---|---|
| Queue leader | Node currently coordinating the queue |
| Quorum members | Member count and status of each follower |
| Majority availability | Whether the queue has enough members to make progress |
| Ready messages | Number of messages waiting for consumers |
| Unacknowledged messages | Messages delivered but not yet acknowledged |
| Redelivery/delivery count | Indicator of consumer errors or poison messages |
| DLQ depth | Failed messages awaiting investigation |
| Publisher confirms/nacks | Broker publish confirmation outcomes |
| Disk and memory | Node and queue resource usage |
| Raft/leader election events | Replication incidents or state transitions |

For streams, monitor retention, disk, consumer offset/lag, and read rates. Streams retain messages after consumers read them; queue depth is not an equivalent backlog measure to destructive queues.

### 14.1. Alerting

Consider alerting when:

- A queue loses majority or has no leader.
- Leader elections repeat frequently.
- Redeliveries climb continuously.
- Queue or DLQ depth grows persistently.
- Publisher nacks/returns increase.
- Disk nears capacity or nodes hit frequent resource alarms.
- Stream consumer lag exceeds SLA.

Do not track message counts alone. A quorum queue can still hold messages while unable to make progress due to lost majority; a stream retains data per retention even after consumers have read it.

## 15. Common Mistakes

1. **Enabling quorum for every queue**: adds unnecessary replication overhead. Classify queues by criticality and semantics.
2. **Confusing durable with replicated**: a durable classic queue still lacks quorum replication. Evaluate failure domains.
3. **Setting a large quorum size without distributing nodes**: members in the same failure domain can fail together. Verify placement.
4. **Using quorum for exclusive or temporary queues**: quorum does not support these semantics. Use classic queues or another pattern.
5. **Assuming quorum queues work without majority**: queues stop progressing without consensus. Design clusters and networks properly.
6. **Enabling `quorum.enabled` on an existing classic queue**: queue declaration fails due to `x-queue-type` mismatch. Migrate using a new queue or planned drain.
7. **Confusing `deliveryLimit` with `maxAttempts`**: one belongs to the broker quorum queue, the other to the binder container. Test both.
8. **Not configuring a DLQ for poison messages**: messages may be dropped once the delivery limit is exceeded. Define a dead-letter policy and monitor it.
9. **Enabling at-least-once dead-lettering without queue limits**: unconfirmed dead-lettered messages can exhaust resources. Configure overflow and max length per broker guidance.
10. **Treating a stream as a quorum queue**: streams have non-destructive reads and offset replay. Choose based on application semantics.
11. **Using queue consumer properties with a stream container**: many queue properties are unsupported. Follow the Rabbit Stream binder docs.
12. **Using `STREAM_SYNC`/`STREAM_ASYNC` with AMQP producer settings**: producer properties may not apply. Configure per producer type.
13. **Not checking actual queue type after deployment**: application config may not take effect if the queue already existed. Inspect broker metadata.

## 16. Queue Type Selection Workflow

When designing a RabbitMQ destination for Spring Cloud Stream:

1. Determine whether data needs to be re-read after a consumer acks it.
2. If replay, massive fan-out, or long-term logs are required, evaluate RabbitMQ streams or super streams.
3. If a destructive work queue with HA is required, evaluate quorum queues.
4. If a single queue copy suffices and temporary/exclusive queues are needed, consider classic queues.
5. Determine quorum member count and distribute across failure domains.
6. Configure `quorum.enabled` and `initialGroupSize` on the appropriate bindings.
7. Define `deliveryLimit`, binder retries, and DLQs.
8. Verify queue type does not conflict with existing queues.
9. Test node failure, leader election, redelivery, DLQs, and publisher confirms.
10. Set up dashboards for queue state, majority, backlog, DLQ, and resources.
11. Plan migrations before changing queue types.

## Conclusion

Classic queues are the traditional choice for work queues when a single copy meets requirements. Quorum queues use Raft to replicate queues across multiple nodes and fit critical workloads requiring durability and HA. RabbitMQ streams are durable, replicated logs readable by offset, ideal for replay, fan-out, and long backlogs.

The Spring Cloud Stream RabbitMQ binder enables creating quorum queues via `quorum.enabled`, configuring `initialGroupSize` and `deliveryLimit`, and selecting the DLQ type separately with `dlqQuorum.enabled`. For streams, the binder uses `containerType=stream` for consumers and `producerType` for producers, along with the corresponding dependencies/plugins. Choose based on storage and consumption semantics, verify the live queue type on the broker, and test failure modes before production deployment.

## References

- [Spring Cloud Stream RabbitMQ Binder — Consumer Properties](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/rabbitmq-consumer-properties.html)
- [Spring Cloud Stream RabbitMQ Binder — Reference Guide](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-rabbit.html)
- [RabbitMQ — Quorum Queues](https://www.rabbitmq.com/docs/quorum-queues)
- [RabbitMQ — Classic Queues](https://www.rabbitmq.com/docs/classic-queues)
- [RabbitMQ — Streams and Super Streams](https://www.rabbitmq.com/docs/streams)
