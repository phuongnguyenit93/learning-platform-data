# Application Partitioning and Single-Active-Consumer

The Spring Cloud Stream RabbitMQ Binder can distribute messages by partition to increase parallel processing capacity. On the consumer side, the application declares a partitioned binding, total instance count, and the current instance's index. RabbitMQ also provides **single-active-consumer (SAC)**: multiple consumers can register on the same queue, yet the broker allows only one consumer to be active at a time while remaining consumers wait on standby.

Partitioning and single-active-consumer solve two different problems. Partitioning splits a stream into multiple parts so multiple instances process in parallel. SAC restricts a queue to a single active consumer receiving messages while allowing the broker to promote a standby if that consumer disconnects. They can be combined when parallel processing across partitions is needed alongside a single active consumer per partition queue.

This lesson belongs to the **RabbitMQ Binder** chapter of the `SPRING_CLOUD_STREAM` module. It focuses on the `Supplier`/`Function`/`Consumer` model, `partitionKeyExpression`, `partitionCount`, `partitioned`, `instanceCount`, `instanceIndex`, and the `x-single-active-consumer` queue argument, along with message ordering, concurrency, failover, and operations.

## 1. How Do Partitioning and Single-Active-Consumer Differ?

The two mechanisms are often used together but serve distinct goals:

| Mechanism | How does it distribute load? | Primary goal | Scope |
|---|---|---|---|
| Partitioning | Selects a partition based on a message key and routes to the corresponding queue | Increase parallelism and keep messages with the same key in the same partition | Entire stream divided into multiple partitions |
| Single-active-consumer | Multiple consumers register on a queue; broker delivers only to one active consumer | One consumer receives messages at a time with standby consumers for failover | A single queue |
| Concurrency | One instance runs multiple consumers/listeners or worker tasks | Increase concurrent processing within a single process | One application instance |

Partitioning does not by itself guarantee only one consumer is active on a queue. SAC does not split messages by key or create additional partitions. Concurrency likewise does not replace `instanceCount` or partition count.

```text
Partitioning: splits a stream into multiple queues

orders.events
     |
     +---- partition 0 ----> queue P0 ----> instance handling P0
     |
     +---- partition 1 ----> queue P1 ----> instance handling P1
     |
     +---- partition 2 ----> queue P2 ----> instance handling P2

SAC on a single queue:

queue P0
   |
   +---- consumer A (ACTIVE) <---- receives messages
   |
   +---- consumer B (STANDBY)
   |
   +---- consumer C (STANDBY)
```

In the combined example, each partition queue can have one active consumer. Different partitions can still be processed in parallel, while consumers registered on the same partition queue serve as standbys for one another.

## 2. Partition Keys Keep Related Messages in the Same Stream

Partitioning typically relies on a business key such as `orderId`, `accountId`, or `customerId`. The producer computes the partition from that key so messages sharing the same key land in the same partition.

For example, using `accountId` as the key:

| Message | `accountId` | Partition |
|---|---|---:|
| AccountOpened | `A-100` | 0 |
| DepositRecorded | `A-100` | 0 |
| WithdrawalRecorded | `A-100` | 0 |
| AccountOpened | `B-200` | 2 |
| DepositRecorded | `B-200` | 2 |

Events for the same account pass through the same partition, allowing ordered processing within that partition if the consumer processes sequentially. Different accounts can be processed in parallel across other partitions.

The key must be stable and accurately reflect the business ordering boundary. Using `eventId` as the partition key typically scatters individual messages and fails to keep events for the same aggregate in the same partition.

## 3. Configuring Partitioning on the Producer

Spring Cloud Stream provides common producer properties to select the partition key and partition count. Example:

```yaml
spring:
  cloud:
    function:
      definition: publishOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.events
          producer:
            partition-key-expression: payload.orderId
            partition-count: 6
```

`partition-key-expression` extracts `orderId` from the payload. `partition-count: 6` declares the number of partitions the producer uses for partitioning calculations. With the RabbitMQ Binder, partitions are implemented using binder-managed exchange/queue topology and routing; do not assume physical queue names or internal routing keys without checking your binder version.

If you want to use beans to compute the partition key or select the partition, configure `partitionKeyExtractorName` or `partitionSelectorName` per the Spring Cloud Stream API. Use one clear strategy per binding; avoid having producer and consumer implement two conflicting partitioning rules.

## 4. Configuring a Partitioned Consumer

The consumer binding must declare `partitioned: true`. The application must also know the total instance count and the current instance's index:

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      instance-count: ${INSTANCE_COUNT:3}
      instance-index: ${INSTANCE_INDEX:0}
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-processing
          consumer:
            partitioned: true
```

Meaning:

- `partitioned: true` enables partition-aware consumer mode for the binding.
- `instance-count` is the total number of application instances participating in processing the stream.
- `instance-index` is the index of the current instance, typically starting from `0`.
- `group` identifies the logical consumer group sharing the binder topology/queues.

With three instances, valid values are `instanceCount = 3` and `instanceIndex` values `0`, `1`, and `2`. All instances must use the same `instanceCount`, while each instance has a unique index. The index must satisfy:

\[
0 \leq instanceIndex < instanceCount
\]

The `instance-count` and `instance-index` properties sit under `spring.cloud.stream`, not inside the binding's `consumer` section. They describe application instances, not partition counts or processing threads.

## 5. Assigning Indices to Replicas

With three replicas:

```text
Replica A:
  INSTANCE_COUNT=3
  INSTANCE_INDEX=0

Replica B:
  INSTANCE_COUNT=3
  INSTANCE_INDEX=1

Replica C:
  INSTANCE_COUNT=3
  INSTANCE_INDEX=2
```

Replicas of the same logical consumer must share the same `group`, same destination, and same `instanceCount`. If all replicas use index `0`, the binder cannot distinguish instances under the declared partitioned model. If counts differ, instances may compute or subscribe to partition queues inconsistently.

In Kubernetes, a StatefulSet ordinal can map to `INSTANCE_INDEX`. With Deployments where pod names change, a mechanism is needed to assign a unique index to each replica. Do not leave a default value of `0` across all production pods.

`instanceCount` is the number of application instances, not `partitionCount`. For example, six partitions and three instances allow each instance to handle multiple partitions. If instance count exceeds partition count, some instances may receive no partitions. Actual assignment depends on how the Rabbit binder creates and binds queues.

## 6. What Is RabbitMQ Single-Active-Consumer?

Single-active-consumer is a RabbitMQ feature enabled on a queue via the queue argument:

```text
x-single-active-consumer = true
```

When multiple consumers register on a queue, RabbitMQ selects only one active consumer to receive messages. The remaining consumers stay on standby. When the active consumer is cancelled, loses its channel, or loses its connection, the broker promotes a standby consumer to become active.

Key points:

- SAC applies per queue, not across an entire exchange or cluster.
- Multiple consumer connections can exist on the same queue, yet only one active consumer receives messages at a time.
- Standby consumers receive no messages until promoted by the broker.
- When the active consumer disconnects, unacknowledged messages can be requeued and redelivered.
- SAC does not duplicate messages to each consumer; consumers on the same queue still belong to one competing-consumer setup.

This feature fits when you need one consumer processing a queue at a time while keeping standby replicas ready to take over quickly if the active consumer fails.

## 7. Configuring Single-Active-Consumer with the RabbitMQ Binder

RabbitMQ Binder versions that support the `singleActiveConsumer` consumer binding property can map this setting to the `x-single-active-consumer` queue argument:

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-processing
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              single-active-consumer: true
              concurrency: 1
```

`single-active-consumer` is a RabbitMQ-Binder-specific property, not a generic property applicable to Kafka or Pulsar. Verify whether your Spring Cloud Stream Rabbit binder version supports this property and how it applies to standard or partitioned queues.

If topology is provisioned externally, the queue must be declared with `x-single-active-consumer=true` before consumers connect. The binder and provisioning system must agree on queue arguments. RabbitMQ does not allow redeclaring an existing queue with incompatible attributes; enabling SAC after a queue already exists without migration can cause topology declaration failures on startup.

`concurrency: 1` in this example limits consumers created per instance to one. For failover, multiple replicas must register on the same queue. If only a single consumer exists, SAC has no standby consumer to take over.

## 8. SAC vs. Exclusive Consumers

Do not confuse single-active-consumer with an `exclusive` consumer:

| Criterion | Single-active-consumer | Exclusive consumer |
|---|---|---|
| Declaration | Queue argument `x-single-active-consumer=true` | Consumer registers with the exclusive flag |
| Multiple registered consumers | Allowed; one active, others on standby | Other consumers may be rejected once an exclusive consumer exists |
| Failover | Broker automatically promotes the next standby consumer | Not a standby-consumer model equivalent to SAC |
| Scope | Queue | Consumer registration on the queue |
| Goal | One active consumer with standby | Exclusive consumer registration |

SAC is usually better when you want multiple replicas waiting on a queue with automatic broker failover of the active role. Exclusive consumers fit scenarios requiring exclusive connection access, but should not be used in place of SAC when automatic failover across standby replicas is required.

## 9. Combining Partitioning with SAC

You can design one queue per partition and enable SAC on each queue. Then:

- The producer uses a partition key to route messages to a partition.
- The consumer deployment runs multiple instances to process different partitions.
- SAC restricts each partition queue to one active consumer.
- A standby consumer can take over a partition queue when the active consumer disconnects, provided topology allows multiple consumers to register on the same queue.

```text
                         orders.events
                              |
                  partition key = orderId
                              |
          +-------------------+-------------------+
          |                   |                   |
          v                   v                   v
       Queue P0            Queue P1            Queue P2
          |                   |                   |
       SAC P0              SAC P1              SAC P2
      /      \            /      \            /      \
   active  standby      active  standby      active  standby
     |                   |                   |
  Worker A            Worker B            Worker C
```

The diagram illustrates one active consumer per queue. All three partitions can still be processed in parallel. If a partition queue is assigned to only one instance with no other standby consumer registered on that queue, SAC provides no additional failover. Inspect the queue topology and how the binder assigns partitions before assuming which instances SAC protects.

Do not assume enabling `single-active-consumer` on a partitioned binding automatically provisions every required standby registration. Integration tests with your exact binder version must confirm which queues consumers register on and how the broker selects active consumers.

## 10. How Partitioning and SAC Affect Message Ordering

Partitioning keeps messages with the same key in the same partition when the producer uses a stable rule. SAC ensures only one active consumer receives messages from that queue. Combining both creates favorable conditions for per-key sequential processing, though it is not sufficient by itself to guarantee business completion order.

Ordering can still break if:

- A consumer processes multiple messages concurrently within the same instance.
- A handler hands work off to an asynchronous thread pool and acknowledges out of order.
- A message takes a long retry while subsequent messages are already delivered.
- Multiple routing keys send related messages to different partitions.
- The producer changes the partition key or partition count mid-stream.

If strict ordering on a queue is needed, typically restrict concurrency to `1`, process synchronously/sequentially, and choose an appropriate prefetch. If per-aggregate ordering is needed, partition by aggregate ID and ensure work within each partition runs sequentially. SAC does not fix asynchronous handler logic by itself.

## 11. SAC Is Not an Exactly-Once Mechanism

When the active consumer disconnects, messages already delivered but unacknowledged can be redelivered by RabbitMQ to the newly promoted consumer. The new consumer may receive a message for which the previous consumer already executed partial business side effects.

Example:

1. Consumer A receives `OrderPlaced`.
2. Consumer A updates inventory in the database.
3. Consumer A disconnects before acking.
4. RabbitMQ promotes consumer B to active.
5. The unacknowledged message is redelivered to B.

Consumer B needs idempotency keyed by `eventId` or an inbox table to avoid deducting inventory twice. SAC improves active/standby availability and failover; it does not replace acknowledgments, transactions, or deduplication.

## 12. Queue Durability and Single-Active-Consumer

SAC is a queue argument, whereas durability determines whether a queue survives broker restarts. The two attributes address separate questions:

| Attribute | Question addressed |
|---|---|
| `durable` | Does the queue survive a broker restart? |
| Persistent message | Is the message stored durably by the broker? |
| `x-single-active-consumer` | Among consumers registered on the queue, who receives messages at a given time? |
| `prefetch` | How many unacked messages can the broker pre-deliver to a consumer? |
| `acknowledgeMode` | How does the consumer acknowledge processed messages? |

A durable queue does not automatically make messages persistent. SAC also does not guarantee messages survive broker restarts. Combine queue durability, message delivery mode, publisher confirms, acknowledgments, and appropriate queue types/policies to meet durability requirements.

## 13. Scaling Partitioned Consumers

Suppose a producer writes to six partitions and the consumer deployment has three instances. Configuration must stay aligned:

```text
partitionCount = 6
instanceCount  = 3

Instance 0: instanceIndex = 0
Instance 1: instanceIndex = 1
Instance 2: instanceIndex = 2
```

When scaling from three to four instances, update `instanceCount` uniformly and assign indices `0`, `1`, `2`, `3`. Do not leave some replicas with count `3` and others with count `4` in steady state. Coordinate transitions with queue topology and binder behavior to avoid unassigned partitions or two instances unexpectedly sharing one partition.

SAC does not alter `partitionCount` or `instanceCount`. It only governs the active consumer on each queue. To raise throughput, evaluate partition count, key distribution, instance count, and processing capacity; adding standby consumers does not increase throughput on a single SAC queue.

## 14. When to Choose Partitioning?

Choose partitioning when:

- The stream has many independent keys requiring parallel processing.
- Messages for the same order/account/customer must stay on the same processing stream.
- A single consumer instance lacks sufficient throughput.
- You want to scale by partition count and instance count.
- A stable partition key can be derived from payload or headers.

Do not partition solely to add queues if data requires global ordering or has very few keys with skewed traffic. One hot key can overload a single partition while other partitions sit idle.

## 15. When to Choose Single-Active-Consumer?

Choose SAC when:

- A queue must have only one consumer receiving messages at a time.
- A standby consumer is needed to take over if the active consumer stops.
- Parallel consumption on the same queue must be constrained.
- Message delivery ordering within a single queue should be simplified, accepting lower throughput.
- Multiple replicas register on the queue and the broker should elect the active consumer.

Do not adopt SAC expecting higher throughput. With one queue and one active consumer, queue throughput is capped by that single active consumer. Adding standby consumers improves availability, not parallel processing capacity.

## 16. When to Combine Both?

Combine partitioning and SAC when:

- Parallelism across partitions is needed.
- Each partition needs only one active consumer at a time.
- Standby replicas are needed for each partition queue.
- Queue and consumer topology can be deployed and governed cleanly.

For example, a banking account service has six partitions keyed by `accountId`. Each partition queue has one active consumer processing events in order, plus standby consumers ready to take over if the active fails. Ensure standby consumers actually register on the same partition queues without violating the binder's `instanceIndex` rules.

If the goal is simply a single consumer across the entire stream with replica failover, one queue with SAC may suffice. If the goal is high throughput without single-active constraints, partitioning with multiple active consumers may fit better.

## 17. Common Configuration Mistakes

| Scenario | Consequence | Fix |
|---|---|---|
| Duplicate `instanceIndex` across replicas | Instances are not properly distinguished in the partitioned model | Assign unique indices within valid bounds |
| Inconsistent `instanceCount` | Replicas hold conflicting views of the topology | Standardize `instanceCount` across the group |
| Producer and consumer have mismatched partition counts | Messages may route to queues not consumed by the expected consumers | Align partition topology and inspect broker bindings |
| Using `eventId` as partition key | Events of the same aggregate scatter across partitions | Use an aggregate key such as `orderId` or `accountId` |
| Enabling SAC with only one consumer | No standby exists for failover | Deploy multiple consumers registering on the queue |
| Enabling SAC on an existing queue with different arguments | Queue redeclaration can fail | Provision/migrate the queue with aligned arguments |
| Confusing SAC with exclusive consumer | Standby consumers cannot register as expected | Use the SAC queue argument and inspect subscriptions |
| Increasing concurrency while expecting single-active behavior | Multiple tasks can run concurrently inside the handler | Restrict concurrency and process sequentially where required |
| Assuming SAC guarantees exactly-once | Duplicates still occur after disconnects before ack | Use event IDs and idempotency |
| Changing partition count without a plan | Keys remap to different partitions; transition ordering is hard to control | Plan a migration and test in-flight data |

## 18. Testing Partitioning and SAC

Tests must run against real RabbitMQ or an equivalent environment because queue arguments and active/standby election are enforced by the broker.

| Scenario | How to test | Expected verification |
|---|---|---|
| Stable partition key | Send multiple events with the same `orderId` | Events with the same key route to the same partition as configured |
| Multiple partitions | Send events across diverse keys | Messages distribute across partition queues |
| Multiple instances | Count `3`, indices `0`, `1`, `2` | Each instance receives its binder-assigned partitions |
| Duplicate index | Two instances with the same index | Validation/deployment catches the misconfiguration |
| SAC with two consumers | Two consumers register on the same SAC queue | Only one active consumer receives messages |
| Active consumer stops | Close connection/channel of the active consumer | Broker promotes a standby consumer |
| Unacknowledged messages | Stop active after receipt but before ack | Messages redeliver; consumer handles duplicates safely |
| SAC and concurrency | Test concurrency greater than 1 | Verify active consumer behavior and actual completion order |
| Partition + SAC | Multiple partition queues, each with multiple consumers | One active consumer per queue and parallelism across queues |
| Queue argument mismatch | Start binder with SAC differing from existing topology | Verify declaration error and migration workflow |
| Scale up/down | Change `instanceCount` and indices | No orphaned partitions or consumer conflicts |

The Test Binder can test functions and bindings at the Spring layer, but it does not fully emulate RabbitMQ's SAC algorithm. Use the RabbitMQ Management UI/API to inspect queue arguments, active consumers, and standby states; use integration tests to verify failover and redelivery.

## 19. Observability and Operations

Monitor these metrics:

- Partition queue count and message distribution across partitions.
- Registered consumer count per queue.
- Which consumer is active and which are standby.
- Failover time from active to standby.
- Redelivered message count and duplicate handling count.
- Queue backlog, oldest message age, and processing rate.
- Consumer concurrency, prefetch, and handler processing latency.
- Declaration errors due to incompatible queue arguments or topology.

Logs should record event ID, partition key, destination, group, instance index, and logical queue if exposed by the binder. Do not use event IDs as high-cardinality metric labels. Alert when a partition queue has no active consumer, no standby is registered, backlog grows steadily, or failovers happen frequently.

## 20. Implementation Workflow

1. Identify the aggregate key requiring ordering, such as `orderId` or `accountId`.
2. Choose `partitionCount` based on throughput and manageable queue count.
3. Configure producer `partition-key-expression` and `partition-count`.
4. Configure consumer `partitioned: true`.
5. Set `instanceCount` to total participating instances and assign unique `instanceIndex` values.
6. Decide whether SAC is needed per queue; clarify failover and ordering goals.
7. If using SAC, verify your Rabbit binder supports `singleActiveConsumer` or provision queues with `x-single-active-consumer=true`.
8. Ensure multiple standby consumers actually register on the same queues needing failover.
9. Tune concurrency, prefetch, and acknowledgments to match ordering requirements.
10. Design idempotency to handle redeliveries after failover.
11. Test partition assignment, active consumers, failover, scaling, and duplicates on RabbitMQ.
12. Monitor backlog, active/standby states, and recovery times in production.

## 21. Self-Check

- [ ] Can distinguish partitioning from single-active-consumer.
- [ ] Can explain the roles of partition key and `partitionCount`.
- [ ] Can configure `consumer.partitioned`, `instanceCount`, and `instanceIndex`.
- [ ] Know that replicas of the same logical consumer must share a group.
- [ ] Can explain the `x-single-active-consumer` queue argument.
- [ ] Can distinguish SAC from exclusive consumers.
- [ ] Understand that SAC allows one active consumer per queue with standbys for failover.
- [ ] Can explain how to combine partition queues with SAC.
- [ ] Recognize the impact of concurrency, prefetch, and retries on processing order.
- [ ] Understand that failover can still cause redelivery and requires idempotency.
- [ ] Can design integration tests on RabbitMQ for partition assignment and SAC.

## Conclusion

Partitioning splits a message stream by key across multiple queues/partitions to increase parallelism and keep same-aggregate messages in the same stream. Consumers use `partitioned`, `instanceCount`, and `instanceIndex` to participate in the RabbitMQ Binder's partitioned model. Single-active-consumer is a RabbitMQ queue feature: multiple consumers register, yet only one active consumer receives messages while others stand by for failover. Both mechanisms can be combined to process across partitions in parallel while keeping one active consumer per queue. SAC does not guarantee completion order or exactly-once processing by itself; tune concurrency/prefetch, acknowledgments, and idempotency, and test the live topology against your exact Rabbit binder and RabbitMQ versions.
