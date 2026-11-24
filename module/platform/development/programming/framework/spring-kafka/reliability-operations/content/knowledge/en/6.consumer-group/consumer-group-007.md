# Rebalancing During Scale-Out

When increasing the number of instances of a Spring Kafka application, new consumers join the consumer group and Kafka must redistribute partitions among members. This process is called a rebalance. Rebalancing enables leveraging additional consumers to increase parallel processing capacity, yet it can also disrupt record reading while partition ownership is handed over.

Scale-out improves throughput only when the topic has enough partitions, current consumers are the bottleneck, and downstream dependencies have headroom to absorb the load. If consumer count exceeds partition count, some consumers will not be assigned any partitions. If workload concentrates on a single key or partition, adding instances will not make the hot partition process faster.

Good operations require predicting when rebalances happen, understanding partition assignment mechanics, ensuring listeners stop and resume safely, and measuring disruption duration and its impact on consumer lag.

## 1. Consumer Groups and Partition Assignment

A consumer group is a collection of consumers sharing the work of reading one or more topics. Within a group, at a given time, each partition is assigned to at most one consumer member. Multiple groups can read the same topic independently; each group maintains its own offsets.

The fundamental parallelism limit is determined by the partition count:

- A partition within a group has only one owning consumer at a time.
- One consumer can own multiple partitions.
- If active consumers outnumber assignable partitions, surplus consumers remain without partitions.
- Increasing consumer count does not automatically increase the topic's partition count.

Example of a 12-partition topic:

| Consumers in group | Ideal distribution | Maximum parallelism |
|---:|---|---:|
| 3 | Each consumer receives roughly 4 partitions | 12 partitions |
| 4 | Each consumer receives roughly 3 partitions | 12 partitions |
| 6 | Each consumer receives roughly 2 partitions | 12 partitions |
| 12 | Each consumer receives 1 partition | 12 partitions |
| 16 | 12 consumers hold partitions, 4 consumers hold none | 12 partitions |

Actual distribution depends on the partition assignor, subscriptions, and partition counts of all topics subscribed by the group. The table above only illustrates a single topic with 12 partitions where consumers share identical subscriptions.

### 1.1. Consumer instances in Spring Kafka

With `@KafkaListener`, a listener container can create multiple consumers via the `concurrency` attribute. If the application runs multiple replicas, total consumer clients can exceed the pod count:

~~~java
@KafkaListener(
        topics = "orders",
        groupId = "billing-service",
        concurrency = "3")
public void consume(OrderCreated event) {
    billingService.handle(event);
}
~~~

If 4 pods are deployed and each pod runs with concurrency 3, the group can have 12 consumer members. Scaling from 4 to 6 pods increases total members from 12 to 18. For a 12-partition topic, the number of consumers holding partitions remains capped at 12; the remaining six members do not increase group parallelism.

In real configurations, concurrency may be set on the annotation, listener container factory, or Spring Boot properties depending on how containers are created. Calculate total consumers across all listener containers joining the same group, rather than counting pods alone.

## 2. What Happens During Scale-Out?

Suppose a group currently has three consumers and the topic has six partitions. When a new instance is added, the new consumer initializes its Kafka client, joins the group, and sends its subscription metadata. The group coordinator detects the membership change and initiates a rebalance.

At a high level, the process unfolds as follows:

~~~text
Before scale out
  C1: P0, P1
  C2: P2, P3
  C3: P4, P5

       Add consumer C4
               |
               v
        Group rebalance
               |
               v
After redistribution
  C1: P0, P1
  C2: P2
  C3: P3
  C4: P4, P5
~~~

This is an illustrative example, not a fixed assignment outcome. The assignor may choose a different distribution to balance partition counts, preserve prior assignments, or minimize partition movement.

During a rebalance, consumers may have to stop polling partitions, finish or handle in-flight work per container semantics, commit appropriate offsets, and hand over ownership. New consumers begin processing partitions only after assignment completes. This window can lower throughput or temporarily pause record reading.

### 2.1. Why can rebalancing cause disruption?

A consumer group must prevent two members from simultaneously being considered valid owners of the same partition within the same group. When membership changes, Kafka coordinates revoking and assigning partitions. Depending on the assignor and group protocol, this may require revoking all assignments or moving only the necessary partitions.

Factors that prolong rebalances:

- Consumers taking a long time to finish in-flight listener executions.
- Consumers failing to call `poll()` frequently enough.
- Slow responses from the coordinator or brokers.
- Large numbers of partitions or members in the group.
- Members starting, stopping, or dropping connections continuously.
- Assignment strategies requiring multiple exchange rounds to move partitions.
- Application rollouts or autoscaling causing multiple membership changes simultaneously.

If rebalances happen frequently, consumers spend much of their time leaving and rejoining the group instead of processing records. Consumer lag may grow even though instance count increased.

## 3. Distinguishing Eager and Cooperative Rebalances

The partition assignor determines how partitions are distributed across members. How assignments transition directly affects the blast radius of disruption.

### 3.1. Eager rebalance

Under an eager protocol, when a rebalance is required, members generally must revoke all partition assignments before the new assignment is finalized. This can create a broader pause in reading, even for partitions that do not need to move to another consumer.

The advantage is a simple handover model compatible with many legacy assignors. The drawback is that even minor membership changes can pause the entire group during redistribution.

### 3.2. Cooperative rebalance

Cooperative rebalancing supports incremental partition transfers. Members revoke only the partitions that must move; unchanged partitions can continue being retained. The handover may take multiple rebalance rounds to complete.

Kafka provides `CooperativeStickyAssignor`, combining sticky assignment stability with the cooperative protocol. When a group scales out, the assignor tries to keep partitions on existing consumers where possible and moves only the partitions needed to bring new consumers online.

Can be configured in Spring Boot:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        "[partition.assignment.strategy]": org.apache.kafka.clients.consumer.CooperativeStickyAssignor
~~~

Or configured directly in Kafka consumer properties:

~~~java
props.put(
        ConsumerConfig.PARTITION_ASSIGNMENT_STRATEGY_CONFIG,
        CooperativeStickyAssignor.class.getName());
~~~

Class names and APIs must match the Kafka client version in use. When migrating a group from an eager assignor to a cooperative assignor, roll out the change following a compatible migration plan. Members in the same group must use compatible assignment strategies; mixing incompatible cooperative and eager assignors can prevent the group from completing rebalances properly.

Cooperative rebalancing narrows the set of paused partitions, yet it does not eliminate all disruption. Consumers still handle revoke/assign callbacks, complete running work, and initialize required state for newly assigned partitions.

## 4. Partition Assignors and Scale-Out Impact

Common Kafka assignors:

| Assignor | Distribution behavior | Operational characteristics |
|---|---|---|
| `RangeAssignor` | Splits partitions by range per topic for each consumer | Can produce skewed distribution across multiple topics if partition counts are uneven |
| `RoundRobinAssignor` | Alternates partitions across consumers | Can distribute more evenly when subscriptions match |
| `StickyAssignor` | Balances assignments while trying to keep prior partitions | Reduces unnecessary assignment churn, but uses eager protocol |
| `CooperativeStickyAssignor` | Keeps assignments stable and moves partitions incrementally | Often suitable when minimizing rebalance disruption is important |

No single assignor is optimal for every subscription. If consumers subscribe to different sets of topics, actual assignments can differ substantially from single-topic examples. Observe actual assigned partitions and evaluate load distribution.

In Spring Kafka applications, the assignor is configured via the Kafka consumer property `partition.assignment.strategy`. Confirm all instances in the same group run compatible configurations after each rollout.

## 5. Increase Concurrency or Increase Pod Count?

Both scaling dimensions have different impacts on resources and consumer lifecycles.

**Increasing concurrency within a pod** creates additional consumer clients inside the same process. This can leverage more CPU cores and partitions without adding pods. However, consumers share CPU, heap, connection pools, and downstream resources within the same instance.

**Increasing pod count** spreads consumers across multiple processes or nodes. This improves process-level fault tolerance and distributes resources, while adding network connections, consumer memberships, cluster overhead, and potential rebalances as new pods join.

Example with a 24-partition topic:

| Configuration | Total consumers | Max consumers with partitions | Notes |
|---|---:|---:|---|
| 3 pods × concurrency 2 | 6 | 6 | Each consumer may receive roughly 4 partitions |
| 6 pods × concurrency 2 | 12 | 12 | Provides greater parallelism |
| 12 pods × concurrency 2 | 24 | 24 | Up to one consumer per partition in this single-topic example |
| 16 pods × concurrency 2 | 32 | 24 | 8 surplus consumers have no partitions |

Useful consumer count also depends on CPU, processing time, database connections, downstream APIs, and broker capacity. Raising concurrency too aggressively can exhaust database connection pools, spike concurrent requests, or overload downstream systems.

### 5.1. Calculate total consumers before scaling

For a simple single-listener group:

~~~text
Total consumer members
  = pod count
    x concurrency per pod
~~~

If multiple listener containers join the same group, sum consumer members across all of those containers. If listeners use different group IDs, each group has independent assignments and lag.

Do not use pod count as a proxy for consumer count when concurrency is greater than one. Operational dashboards should display pod count, consumer member count, and assigned partition counts.

## 6. Conditions for Scale-Out to Truly Increase Throughput

Scale-out helps when consumer processing is the bottleneck and the topic has enough partitions to distribute work.

Before adding instances, check:

1. Is consumer lag climbing steadily, or is it just a brief traffic burst?
2. Is the partition count greater than or equal to the target consumer count?
3. Are records and keys distributed fairly evenly across partitions?
4. Is the listener slowed down by databases, HTTP APIs, locks, or CPU work?
5. Do brokers have sufficient capacity to serve extra fetch requests and network traffic?
6. Can downstream systems handle the new concurrency level?

If consumers are waiting on a database, adding consumers can increase concurrent queries and slow the database down further. If one partition receives the bulk of traffic, other consumers remain idle while the hot partition caps throughput.

### 6.1. Hot partitions and key distribution

Kafka preserves ordering within a partition. Records with the same key are typically routed to the same partition by the partitioner. This is a standard way to maintain ordering for an aggregate, such as events for the same `orderId`.

If one key or group of keys dominates traffic, its corresponding partition can become a hot partition. Adding consumers cannot split one partition across multiple consumers in the same group. Inspect record rates, bytes in/out, and lag per partition.

Potential solutions include:

- Adjusting key generation if business ordering requirements allow.
- Redistributing keys or designing sharding for hot aggregates.
- Separating distinct workloads into dedicated topics or groups.
- Optimizing processing duration for records on the hot partition.
- Adding partitions when needed while evaluating impacts on key mapping.

Never alter keys solely to balance load if doing so breaks business ordering guarantees.

## 7. Is Increasing Partition Count Consumer Scale-Out?

Adding partitions and adding consumers are two distinct changes.

- Adding consumers brings more members into the same group to divide existing partitions.
- Adding partitions gives the topic more parallel units and can allow more consumers to do useful work.
- Changing partition count is not broker replica reassignment. Replica reassignment moves partition replicas between brokers; consumer group rebalancing changes which member owns a partition for reading.

If a topic has 6 partitions and 12 active consumers are needed, scaling pods/concurrency to 12 still leaves at most 6 consumers receiving partitions. Increasing partition count may be required, but you must verify broker throughput, file/partition counts, replication cost, and ordering requirements.

Adding partitions can change key-to-partition mapping under the default partitioner. Older records for the same key may sit in an old partition while newer records route to a different partition. Since Kafka only guarantees ordering per partition, adding partitions can affect cross-partition ordering for a key during the transition window.

Do not reduce an existing topic's partition count as a routine scaling operation. When major structural changes are needed, design a new topic and a controlled data migration plan.

## 8. Common Triggers for Rebalances

Scale-out is one trigger, but rebalances also occur when consumers lose connectivity, poll too slowly, or topic metadata changes.

| Cause | What happens | How to investigate |
|---|---|---|
| Adding consumers | New member joins the group | Correlate scale timestamps with group membership logs |
| Consumer stop or crash | Member leaves group or heartbeats drop | Check exit codes, pod restarts, and shutdown logs |
| `max.poll.interval.ms` exceeded | Consumer considered stalled on polling | Measure batch processing duration and poll gaps |
| Session timeout | Coordinator receives no heartbeat within limit | Check network, GC pauses, CPU starvation, and timeouts |
| Topic/partition changes | Assignments require metadata refresh | Check topic creation or partition expansion operations |
| Subscription changes | Member subscribes to a different topic set | Check pattern subscriptions and configuration |
| Rolling deployment | Multiple members stop and start | Check rollout speed and shutdown grace periods |

Do not arbitrarily raise `session.timeout.ms` or `max.poll.interval.ms` to mask rebalances. Identify why consumers fail to heartbeat or poll on time before adjusting timeouts.

## 9. `poll()`, Listener Processing, and Timeouts

Kafka consumers must keep calling `poll()` within `max.poll.interval.ms`. If the application spends too long processing a batch before the next poll, the consumer may leave the group and its partitions will be reassigned to another member.

Properties that commonly need coordination:

| Property | Role | Considerations |
|---|---|---|
| `max.poll.records` | Maximum records returned per poll | Large batches can extend processing duration |
| `max.poll.interval.ms` | Maximum time between polls before the consumer is considered stalled | Must exceed batch processing time under predictable slow conditions |
| `session.timeout.ms` | Time coordinator waits for heartbeats before marking a member lost | Relates to detecting disconnected members |
| `heartbeat.interval.ms` | Heartbeat frequency in the classic group protocol | Typically must be smaller than session timeout per Kafka rules |

Configuration example:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
      properties:
        "[max.poll.records]": 50
        "[max.poll.interval.ms]": 300000
        "[session.timeout.ms]": 30000
        "[heartbeat.interval.ms]": 10000
~~~

These are illustrative values for the classic consumer group protocol. Your Kafka client/broker version and active group protocol can affect how heartbeats and timeouts are configured; consult the documentation for your deployed version.

If a single record can take several minutes to process, raising `max.poll.interval.ms` can reduce eviction risk during processing, yet it also delays detecting a genuinely hung consumer. An alternative design is bounding processing time, breaking work into smaller units, or moving long-running work into a durable stateful workflow. Never acknowledge records before work is durably persisted.

## 10. Handling Revoke and Assign in Spring Kafka

Spring Kafka provides listener hooks so applications can react when partitions are revoked or assigned. `ConsumerAwareRebalanceListener` lets you run logic before and after revoke/assign phases, depending on the callback:

~~~java
factory.getContainerProperties().setConsumerRebalanceListener(
        new ConsumerAwareRebalanceListener() {
            @Override
            public void onPartitionsRevokedBeforeCommit(
                    Consumer<?, ?> consumer,
                    Collection<TopicPartition> partitions) {
                log.info("Partitions revoked before commit: {}", partitions);
            }

            @Override
            public void onPartitionsAssigned(
                    Consumer<?, ?> consumer,
                    Collection<TopicPartition> partitions) {
                log.info("Partitions assigned: {}", partitions);
            }
        });
~~~

The snippet illustrates registering the listener on `ContainerProperties` of the listener container factory. Imports, factory types, and configuration placement depend on how the application builds containers and the Spring Kafka version.

Inside the revoke callback, the application can:

- Stop accepting new work for partitions about to be lost.
- Safely complete or cancel running work per design.
- Flush application state or checkpoints if needed.
- Log partitions and handover timestamps.

Inside the assigned callback, the application can:

- Initialize state or caches bound to the partitions.
- Restore application checkpoints.
- Record when the consumer took ownership of the partitions.
- Resume record processing after assignment completes.

Rebalance callbacks are not the place for long-running network operations. If a callback blocks for too long, the rebalance itself can drag out. Perform only short, bounded-timeout, recoverable operations.

### 10.1. Avoid unmanaged asynchronous processing

A common design mistake is having a listener submit records to an executor and return immediately. The container may treat the listener as succeeded and commit offsets while asynchronous work is still incomplete. If the partition is revoked or the pod stops, that work may be lost.

If using an executor:

- Track in-flight work counts per partition.
- Do not ack/commit before work is durably saved or completed as guaranteed.
- On revoke, stop accepting new work and settle in-flight work within a deadline.
- Maintain idempotency because records can still be redelivered after failures.
- Avoid blocking consumer threads indefinitely in callbacks waiting on executors.

## 11. Cooperative Rebalancing in Rollouts and Autoscaling

A cooperative assignor can limit disruption scope when adding or removing members. Still, autoscaling should change capacity at a measured pace.

When scaling out:

1. Confirm lag genuinely requires additional processing capacity.
2. Verify remaining assignable partitions exist.
3. Add replicas in steps aligned with startup and rebalance times.
4. Monitor member counts, assignments, rebalance duration, and lag.
5. Verify new consumers receive partitions and show processing throughput.
6. Stop scaling once partition parallelism is saturated or downstream begins overloading.

When scaling in:

1. Avoid terminating many pods simultaneously if the group holds a large backlog.
2. Allow containers to stop cleanly.
3. Ensure grace periods give listeners enough time to finish in-flight work.
4. Monitor partition revocations, commits, and rebalances.
5. Confirm remaining consumers sustain the incoming rate after scale-in.

CPU-only HPA rules can mis-scale: consumers waiting on databases may use little CPU while lag climbs. Conversely, high CPU can stem from serialization or GC, where adding consumers increases total load. Consumer lag, processing rate, and oldest record age can serve as scaling signals, provided smoothing, cooldowns, and replica bounds are applied to prevent oscillation.

## 12. Static Membership and Reducing Restart Rebalances

Static membership lets a consumer declare a stable `group.instance.id`. When a member disconnects temporarily and returns with the same identity within the allowed window, the group can preserve or restore its assignment without treating it as an entirely new member.

Static membership is useful in environments with frequent restarts or rolling deployments. It can cut down unnecessary rebalances, though it does not eliminate rebalances for every scale-out change.

Principles to follow:

- Each consumer member needs a unique `group.instance.id` within the group.
- Identities must remain stable across restarts of the same instance.
- Never share the same ID across simultaneously running pods.
- Account for session timeout because the coordinator may wait for a static member to return before redistributing partitions.
- When adding pods, assign fresh identities to new members.

With Spring Kafka and concurrent listener containers, verify how the framework generates distinct identities for each child consumer. Do not construct IDs solely from the service name if multiple consumers in the same pod would collide.

Static membership can lengthen detection time for truly dead members depending on timeout settings. If a pod is permanently lost, its partitions may wait out the timeout before reassignment to another member. Balance fewer rebalances on brief restarts against recovery time when instances disappear permanently.

## 13. Graceful Shutdown During Scale-In

When an orchestrator stops a pod, the application typically receives a termination signal. Spring Kafka listener containers need time to stop consumers, finish in-flight records, and commit offsets per configuration. If the process is killed prematurely, records may be redelivered.

For controlled shutdowns:

- Set `terminationGracePeriodSeconds` long enough for the maximum acceptable processing time.
- Configure readiness so instances stop receiving new traffic before shutdown if the architecture requires it.
- Ensure listener containers stop before dependencies such as database connection pools close.
- Never allow shutdown hooks to hang indefinitely.
- Keep consumers idempotent because some records can still be redelivered.
- Track in-flight record counts and shutdown durations.

With Spring Kafka, containers can be managed by the Spring lifecycle. Test actual behavior when sending `SIGTERM`, especially for slow listeners, batch listeners, and manual acknowledgments. Application shutdown timing and platform grace periods must align.

## 14. Measuring Rebalances and Scale-Out Effectiveness

Do not measure success solely by the count of running new pods. Confirm the consumer group has stabilized and throughput has genuinely increased.

| Metric | Meaning | How to use |
|---|---|---|
| Consumer group member count | Number of members in the group | Confirms scale-out added consumers |
| Assigned partitions/member | Partitions owned per consumer | Detects idle members or skewed assignments |
| Rebalance count/rate | Frequency of group rebalances | Detects membership churn |
| Rebalance duration | Time from start until assignments stabilize | Measures scaling disruption |
| Consumer lag | Pending records per partition/group | Assesses backlog |
| Oldest record age | Age of the oldest unprocessed record | Connects lag to business SLAs |
| Records consumed rate | Actual processing rate | Confirms throughput increased |
| Listener processing duration | Duration per record/batch | Identifies business-logic bottlenecks |
| Poll interval / max poll gap | Time between poll calls | Detects risk of exceeding `max.poll.interval.ms` |

Monitor lag per partition rather than group total alone. Total lag can drop while a hot partition continues growing. Also distinguish lag count from record age: record age reflects user-visible delay more closely.

### 14.1. Determining whether scale-out worked

Compare before and after scaling under equivalent load conditions:

- Did the consumer processing rate increase?
- Did lag and oldest record age decrease?
- Did listener p95/p99 change?
- Did rebalances depress throughput for a noticeable period?
- Did downstream databases/APIs see higher latency or error rates?
- Are any members left without partition assignments?

If consumer count rises without processing rate increasing, check partition limits, hot partitions, broker bottlenecks, and downstream systems. If lag drops for a few minutes and then climbs again, new capacity may still fall short of incoming rate or the autoscaler may be oscillating.

## 15. Runbook When Scale-Out Causes Prolonged Rebalances

### 15.1. New consumers join but the group does not stabilize

1. Inspect group coordinator logs and member IDs.
2. Confirm all instances share the same `group.id` and compatible subscriptions.
3. Verify partition assignment strategies are uniform and compatible.
4. Check if consumers are exceeding `max.poll.interval.ms` or missing heartbeats.
5. Check pod restarts, CPU throttling, GC pauses, and network interruptions.
6. If the assignor was just changed, verify the rollout followed a compatible transition plan.

### 15.2. Scaled out yet new consumers receive no partitions

1. Count topic partitions and total consumer members in the group.
2. Check the subscriptions of the new consumers.
3. Inspect current assignments and member states.
4. Identify surplus consumers caused by total concurrency exceeding partition count.
5. Check the assignor and assignment error logs.

If consumers already equal or exceed partitions, new consumers will not necessarily receive partitions. Consider adding partitions after evaluating key mapping and broker capacity.

### 15.3. Lag spikes immediately after scaling

1. Check rebalance duration and how long the group took to stabilize.
2. Check processing rates during and after the rebalance.
3. Compare per-partition lag to detect hot partitions.
4. Check if downstream systems were overloaded by increased concurrency.
5. Inspect batch processing times and gaps between polls.
6. Throttle scaling speed or concurrency if downstream is under pressure.

### 15.4. Repeated rebalances after rolling deployments

1. Check pod stop/start timing and how many members change concurrently.
2. Verify shutdown grace periods and listener container stop behavior.
3. Check static membership if enabled, especially duplicate identities or timeouts.
4. Consider a cooperative assignor to reduce partition revocation scope.
5. Tune rollout `maxUnavailable`/`maxSurge` or cooldowns to limit simultaneous member churn.

## 16. Testing Scale-Out Before Production

A useful test applies continuous load while changing consumer counts. Scaling only on an idle topic will not reveal impacts on backlog and SLAs.

Recommended scenario:

1. Create a topic with a production-representative partition count and produce records with realistic key distribution.
2. Run the group at an initial consumer count, measuring processing rate, lag, record age, and rebalances.
3. Add consumers incrementally; record when members join and when assignments stabilize.
4. Compare eager vs. cooperative assignors in staging if evaluating a switch.
5. Stop a consumer mid-processing to verify revocation, commits, and redelivery.
6. Test scale-in and send `SIGTERM` to verify graceful shutdown.
7. Inject latency into the database or downstream API to identify concurrency limits.
8. Verify zero record loss and that duplicate deliveries do not cause duplicate business effects.

Results should capture rebalance duration, throughput recovery time, peak lag, oldest record age, and reprocessed record counts. These metrics inform autoscaling cooldowns and shutdown grace periods.

## 17. Consumer Group Scale-Out Checklist

### Before adding instances

- [ ] Consumer lag or record age confirms additional processing capacity is needed.
- [ ] Total consumer members calculated from pod count and listener concurrency.
- [ ] Topic has enough partitions for the target consumer count.
- [ ] Key distribution does not create severe hot partitions.
- [ ] Databases, downstream APIs, CPU, and brokers have spare capacity.
- [ ] Assignment strategy is compatible across all members.

### During scaling

- [ ] Increase replicas in controlled steps.
- [ ] Monitor member count, partition assignments, and rebalance duration.
- [ ] Monitor lag by group and per partition.
- [ ] Monitor listener duration, poll gaps, and downstream latency.
- [ ] Stop scaling once partition parallelism is reached or downstream overloads.

### After scaling

- [ ] Group has stabilized and new consumers hold assigned partitions.
- [ ] Processing rate increased as expected.
- [ ] Consumer lag and oldest record age returned within SLO.
- [ ] No recurring rebalances or timeout-based member evictions.
- [ ] Duplicate deliveries produce no duplicate business side effects.
- [ ] Autoscaling and cooldown configs reflect measured results.

## Conclusion

Scaling out Spring Kafka adds new consumers to the group and triggers a rebalance to redistribute partitions. Maximum parallelism is bounded by partition count; adding pods or concurrency beyond this cap produces idle consumers. Cooperative sticky assignment, static membership, well-tuned poll timeouts, and graceful shutdown reduce disruption from membership changes. To verify that scale-out actually helps, measure rebalance duration, assignments, processing rate, consumer lag, and oldest record age while checking downstream capacity. When scaling is performed incrementally and validated with metrics, systems can raise throughput while keeping partition handoffs safe for reprocessing.
