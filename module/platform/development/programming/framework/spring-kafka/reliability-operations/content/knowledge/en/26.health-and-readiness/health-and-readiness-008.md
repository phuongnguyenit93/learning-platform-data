# Consumer Group Has No Partition Assignment

In Spring Kafka, a listener container can be running while its consumer has **no partitions assigned**. When that happens, the application receives no records, workload consumer lag may grow, and service readiness may be affected. However, having no partitions is not necessarily a bug: if the number of consumers exceeds the number of partitions, some consumers will legitimately sit idle while other consumers process all data.

Therefore, when diagnosing **Consumer group has no partition assignment**, answer three questions before restarting or changing configuration:

1. Does the entire consumer group truly have no assigned partitions, or does only one member lack an assignment?
2. Is having no assignment valid under the topology, or is it a sign that the group has not finished rebalancing or is misconfigured?
3. Should the application be considered ready when a pod receives no partitions, or is the workload still served by other members?

This lesson belongs to the **Health and readiness** chapter. It focuses on how Kafka distributes partitions, common causes in Spring Kafka, how to inspect groups and listener containers, building appropriate health policies, and safe recovery.

## 1. What is partition assignment?

Kafka stores records in topics. Each topic has one or more partitions; each partition is its own ordered log.

Consumer groups let multiple consumers share a workload. Under normal group management, the Kafka group coordinator coordinates members and the partition assignor to decide which consumer owns which partitions.

Example topic `orders.created` with six partitions:

    orders.created
      P0  P1  P2  P3  P4  P5

    Consumer group: order-workers

    Member A: P0, P1
    Member B: P2, P3
    Member C: P4, P5

Each partition in a group is assigned to at most one member at a time. Consumers in the same group share the workload; consumers in a different group can independently read the same topic.

**Assignment** is the list of partitions granted to a consumer group member. A consumer can only poll data from partitions it owns under subscribe/group management, or partitions explicitly assigned by the application in manual assignment mode.

If a member has no partitions, it receives no records from the group at that moment. This does not automatically mean the entire group stopped processing.

## 2. Distinguishing no partitions from no records

Two situations are frequently confused:

**No partitions assigned:**

    Consumer A
      assigned partitions = []

    Consumer B
      assigned partitions = [P0, P1]

Consumer A cannot read records from the topic under the current group assignment.

**Assigned partitions, but the topic has no new records:**

    Consumer A
      assigned partitions = [P0, P1]
      poll() -> empty
      poll() -> empty
      poll() -> empty

Consumer A still owns partitions and may be operating healthily; there is simply no new data.

| State | Assignment | Poll | Signals to Inspect |
|---|---|---|---|
| No partitions | Empty | No data to read from assignment | Group membership, assignor, subscription |
| Assigned, topic empty | Present | Poll returns empty | Idle events, producer traffic |
| Assigned, paused | Present | Container delivers no more records per pause policy | Pause state, backpressure |
| Assigned, consumer stuck | May still appear assigned | Poll does not progress | Non-responsive, thread dump, poll interval |
| Group rebalancing | Assignment may be transitioning | Temporarily unstable | Group state, rebalance events |

Do not use `ListenerContainerIdleEvent` to conclude a consumer has no partitions. Idle normally reports receiving no records within a configured window while assignments can still exist.

## 3. One member with no partitions vs. the whole group with no partitions

Suppose a topic has three partitions and the group has five consumers:

    Topic: orders.created
      P0  P1  P2

    Group: order-workers
      Member A -> P0
      Member B -> P1
      Member C -> P2
      Member D -> []
      Member E -> []

Members D and E having no partitions is a valid outcome: Kafka cannot split three partitions across five members while preserving the rule that one partition belongs to at most one member per group.

The group as a whole still has all three partitions processed by A, B, and C.

Conversely, if all members have empty assignments while the topic has partitions and the group is stable, investigate subscription, group identity, metadata, assignor, and group state.

When reading dashboards, distinguish:

- **Member assignment:** partitions of one specific consumer.
- **Group assignment:** union of partitions assigned to members in the group.
- **Topic partition count:** total partitions available across subscribed topics.
- **Expected assignment:** partitions expected by topology and assignor to be given to the group.

Seeing a single pod with no partitions is not enough to conclude the entire service stopped consuming.

## 4. When is having no partitions normal?

Several cases where empty assignment is expected:

1. **More consumers than partitions.** Excess consumers have no partitions.
2. **Topic subscription matches only a subset of topics.** A member may receive no partitions depending on subscription/assignment.
3. **Group membership just changed.** Consumers are waiting for a rebalance to finish.
4. **Topic lacks suitable partitions yet.** Metadata or topic creation is not finished; depends on auto-create config and timing.
5. **A listener container was created but not started.** It has not joined the group yet.
6. **Container was paused or stopped.** Pausing keeps assignments in many scenarios; stopping leaves the lifecycle/group accordingly.
7. **Application uses manual assignment.** Partitions are configured via `topicPartitions` or `assign()`, rather than the standard group assignor flow.

Readiness policies must understand the expected topology. Do not mark every pod without partitions as unhealthy if the deployment intentionally runs more replicas than partitions for standby or fast scaling.

## 5. Calculating parallelism limits from partition count

The number of consumers that can process in parallel within a group is bounded by the number of partitions subscribed and assigned to the group.

Example:

    orders.created: 8 partitions
    replicas: 3
    concurrency per pod: 4

    Total consumer threads: 3 x 4 = 12
    Partitions: 8
    Consumers with assignments: max 8
    Excess consumers: at least 4

Increasing concurrency from 4 to 8 will not make an eight-partition topic have 24 consumers processing 24 partitions in parallel. Some child consumers will simply receive no partitions.

| Partition count | Consumer threads | Members able to receive partitions | Minimum excess members |
|---:|---:|---:|---:|
| 3 | 3 | 3 | 0 |
| 3 | 5 | 3 | 2 |
| 8 | 6 | 6 | 0 |
| 8 | 12 | 8 | 4 |
| 24 | 12 | 12 | 0 |

This table reflects the simple limit when members subscribe to compatible topic sets with no other assignor constraints. Multiple topics, differing subscriptions, and assignors can produce uneven distributions.

Before increasing concurrency, calculate total consumer threads across all replicas in the group, not just a single pod.

## 6. Checking whether the topic exists and has partitions

A basic cause is a consumer subscribing to the wrong topic, an uncreated topic, or a topic named differently across environments.

Use Kafka CLI to list topics:

~~~bash
kafka-topics.sh --bootstrap-server localhost:9092 --list
~~~

Describe a topic in detail:

~~~bash
kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic orders.created
~~~

Topic description output shows partition counts and leaders/replicas for each partition. If the topic does not exist, check:

- Topic name in `@KafkaListener`.
- Active profile/environment.
- Whether topic configuration variables resolved properly.
- Topic provisioning/ACL/auto-create policies.
- Whether broker bootstrap servers point to the right cluster.

Do not turn on automatic topic creation in production just to patch a listener subscribed to a misspelled name. Creating the wrong topic can leave the application running while reading an empty log separate from real data.

## 7. Checking the consumer group's current state

Kafka groups transition through lifecycle states such as:

- **PreparingRebalance:** group is preparing to redistribute partitions.
- **CompletingRebalance:** group is finalizing assignments.
- **Stable:** group is stable with its current assignment.
- **Empty:** no active members remain in the group.
- **Dead:** group no longer exists per broker-managed state.

Enum/state names and display output can vary by Kafka version or CLI. Use the group describe command:

~~~bash
kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group order-workers
~~~

Depending on Kafka version, view detailed members and assignments:

~~~bash
kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group order-workers --members --verbose
~~~

Check:

- Does the group exist and have members?
- Does member count match expected `replicas × concurrency`?
- Is the group `Stable` or constantly rebalancing?
- Which partitions are assigned to each member?
- Are committed offsets and lag advancing?
- Which consumer client ID/host corresponds to the pod under investigation?

If the group is `Empty`, the issue may be that no consumer is joining the right group. If the group is `Stable` yet one member has an empty assignment, it may simply be an excess consumer.

## 8. Wrong group.id or confusing listener ID

In Spring Kafka, several identifiers must be distinguished:

- `@KafkaListener(id=...)` identifies the Spring listener/container endpoint.
- `groupId=...` identifies the Kafka consumer group for the listener when configured explicitly.
- `spring.kafka.consumer.group-id` is the default group ID in consumer configuration.
- `client.id` identifies the Kafka client instance.

If a service expects group `order-workers` yet the listener actually joins `order-worker`, a dashboard watching the old group will not see the expected members/assignments.

Example explicit declaration:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "orders.created",
    groupId = "order-workers",
    containerFactory = "ordersListenerFactory"
)
public void consume(OrderCreated event) {
    orderService.process(event);
}
~~~

Never use the listener ID to guess the group ID. Explicitly declaring `groupId` makes configuration readable and reduces cross-environment mistakes.

Check YAML, environment variables, profiles, annotations, and custom container factories. An overridden annotation value can make the actual group differ from the group ID you are inspecting.

## 9. Checking subscriptions: topics, topicPattern, and topicPartitions

Spring Kafka supports multiple ways to register a listener.

**Subscribe by topic list:**

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = {"orders.created", "orders.updated"},
    groupId = "order-workers"
)
public void consume(OrderEvent event) {
    orderService.process(event);
}
~~~

**Subscribe by regex pattern:**

~~~java
@KafkaListener(
    id = "tenantEventsListener",
    topicPattern = "tenant\\.events\\..*",
    groupId = "tenant-workers"
)
public void consume(TenantEvent event) {
    tenantService.process(event);
}
~~~

The pattern must match real topic names. For instance, `tenant.events.eu` does not match `tenant\\.event\\..*` because the pattern uses singular `event`.

**Manual partition assignment:**

~~~java
@KafkaListener(
    id = "ordersPartitionListener",
    groupId = "orders-manual",
    topicPartitions = {
        @TopicPartition(
            topic = "orders.created",
            partitions = {"0", "1"}
        )
    }
)
public void consume(OrderCreated event) {
    orderService.process(event);
}
~~~

When using `topicPartitions`, the application specifies partitions directly. This model differs from subscription via the group assignor; do not diagnose it expecting callbacks/assignments identical to a standard subscribed consumer.

Do not declare conflicting subscription modes simultaneously and assume they merge. Inspect the actual annotation and factory used by the listener.

## 10. Regex subscription not matching topics

With `topicPattern`, the Kafka client receives a pattern and periodically refreshes metadata to discover matching topics. An escaping error or naming convention difference can cause the subscription to match zero topics.

Example:

~~~java
@KafkaListener(
    id = "auditListener",
    topicPattern = "audit\\.events\\..*",
    groupId = "audit-workers"
)
public void consume(AuditEvent event) {
    auditService.process(event);
}
~~~

Matching topics:

- `audit.events.eu`
- `audit.events.us`
- `audit.events.internal`

Non-matching topics:

- `audit.event.eu`
- `orders.audit.events`
- `audit-events-eu`

If the group is `Stable` with no partitions, test the pattern against real topic names and inspect subscription metadata. An overly broad regex can also cause the listener to subscribe unintentionally to other topics.

Never fix a production regex by arbitrarily widening it to `.*`; the listener could consume data belonging to other services or violate access boundaries.

## 11. Consumer group has not finished rebalancing

When a new member joins, a member leaves, topic partitions change, or subscriptions change, Kafka can initiate a rebalance.

During a rebalance, old assignments may be revoked before new assignments are fully applied. Observing over a brief window may show zero partitions or shifting assignments.

Diagram:

    Members A, B are Stable
           |
           v
    Member C joins the group
           |
           v
    PreparingRebalance
           |
           v
    Revocation / assignment calculation
           |
           v
    CompletingRebalance
           |
           v
    Stable with new assignment

If the group repeatedly fails to reach `Stable`, investigate what causes recurring rebalances:

- Consumer processing takes too long, exceeding `max.poll.interval.ms`.
- Unstable network/broker connectivity.
- Repeated pod restarts.
- Static member fencing due to duplicate `group.instance.id`.
- Frequently changing subscriptions/metadata.
- Incompatible cooperative/eager assignors across members.
- Consumers crashing or failing to complete the poll lifecycle.

A brief rebalance is normal; a rebalance storm is an operational incident.

## 12. Cooperative and eager assignment

Kafka has multiple partition assignment strategies. Eager strategies generally revoke assignments broadly before building new assignments; cooperative strategies attempt to move only necessary partitions to reduce disruption.

Example assignor config in consumer properties:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        partition.assignment.strategy: org.apache.kafka.clients.consumer.CooperativeStickyAssignor
~~~

Class names and compatibility depend on Kafka client version. During rolling upgrades, watch compatibility between members running different strategies.

Cooperative rebalancing does not eliminate situations where a member has no partitions. If consumer threads outnumber partitions, some remain idle. It also does not prevent rebalancing when a consumer loses membership.

Do not change the assignor just because a pod has no assignment. First check partition count, member count, and subscriptions; changing assignors can trigger extra rebalances and affect the whole group.

## 13. RangeAssignor can produce uneven distributions

With multiple topics and partitions, assignors can distribute partitions unevenly depending on strategy and subscription.

For example, a group has two topics with three partitions each, and three consumers all subscribe to both topics. Range assignment divides partitions per topic, which can cause the first consumer to receive partitions from both topics while another member receives fewer depending on counts and layout.

When a consumer receives no partitions, check:

- Does it subscribe to the exact same topic set as other members?
- Is there a topic subscribed by only a subset of members?
- Are partition counts unequal across topics?
- What is the active assignment strategy?
- Do members share the same version/compatible configuration?

Do not compare only total cluster partitions to total consumer threads. Compare **partitions assignable to each member based on actual subscriptions**.

## 14. More consumer threads than partitions

Spring Kafka `concurrency` spawns multiple child consumers for one listener container. Concurrency does not create extra partitions.

Example:

~~~java
factory.setConcurrency(6);
~~~

If a topic has three partitions and the listener subscribes only to that topic, at most three child consumers can hold partitions in one group. The remaining three children will have no assignments.

With four replicas, each with `concurrency=6`:

    Total child consumers = 4 x 6 = 24
    Topic partitions = 3
    Max members with assignment = 3
    Min members without assignment = 21

This configuration usually wastes resources and increases group membership overhead. It does not raise throughput for a three-partition topic.

Choose concurrency based on partition topology and workload. If higher parallelism is needed, you may need to increase partition count after evaluating key distribution, ordering, and broker limits.

## 15. Topic not created yet or metadata not updated

When a listener starts before the topic is created, the consumer may lack suitable partition metadata yet. Depending on broker/client settings, auto topic creation, and subscription, discovery varies.

Things to check:

1. Does the topic exist in the right cluster?
2. Does the topic have a partition count greater than 0?
3. Does the broker permit automatic topic creation?
4. Do the principal's ACLs allow describe/subscribe/read?
5. Has the client refreshed metadata?
6. Is a newly created topic or partition increase still propagating?

A wrong topic name can keep a listener running without receiving data from the intended topic. If auto-create is enabled, Kafka can create an empty topic when the consumer subscribes, making the misconfiguration harder to spot.

Production should manage topics through provisioning/IaC and verify partition counts before deploying dependent consumers.

## 16. ACLs and authentication: distinguishing assignment from fetch permission

A consumer can hit security failures when subscribing or fetching:

- Missing `READ` permission on the topic.
- Missing appropriate permission on the consumer group.
- Wrong or expired SASL/TLS credentials.
- Broker authorization policies differing across environments.

Distinguish two phenomena:

- **No partition assigned:** group assignment/subscription gave the member no partitions.
- **Assigned, yet unable to read:** fetch/offset commit may be failing due to authorization or authentication.

Missing permissions do not always manifest as an empty assignment. The consumer can throw exceptions in `poll()` or log authorization errors even while metadata assignment exists.

Check broker/client logs and ACLs for the actual principal. Never log passwords, tokens, or private keys during investigation.

## 17. auto.offset.reset does not create partition assignments

A common misconception is that a group has no offsets so Kafka does not assign partitions.

In reality, partition assignment and offset initialization are two separate steps:

    Subscribe topic
        |
        v
    Group coordinator/assignor assigns partitions
        |
        v
    Consumer determines read position
        |
        +--> committed offset still valid
        |
        +--> if missing/expired: auto.offset.reset policy
        |
        v
    Poll records

`auto.offset.reset=earliest/latest/none` decides how to handle missing or invalid offsets. It is not an assignment mechanism.

If configured to `none`, a consumer can hold partitions yet throw an error because no offset is found. Never alter the reset policy to "fix" an assignment error before finding the real cause; `latest` can skip old records that needed processing.

## 18. Different group.id values split data differently

If each pod accidentally joins its own group ID, Kafka will not distribute partitions across pods as intended.

Example:

    Pod A -> group order-worker-A
    Pod B -> group order-worker-B
    Pod C -> group order-worker-C

Each independent group can receive all partitions of the topic. This creates fan-out, not load balancing across the three pods.

To share a workload, consumers must use the same group ID:

    Pod A --+
    Pod B --+--> group order-workers --> partitions split across members
    Pod C --+

If a dashboard watches `order-workers` while the running application uses `order-worker-A`, you might mistakenly conclude the group has no partitions.

Cross-check the runtime group ID from listener configuration and broker group descriptions, not just default YAML files.

## 19. Static membership and group.instance.id

Static membership uses `group.instance.id` to identify a stable member across qualifying restarts, which can reduce unnecessary rebalances.

However, `group.instance.id` must be unique within the group. If two instances use the same ID, Kafka can fence one member or cause membership errors.

Example:

    Pod A: group.instance.id=orders-0
    Pod B: group.instance.id=orders-1
    Pod C: group.instance.id=orders-2

Never configure the same `orders-worker` value for every pod.

Static membership does not prioritize a consumer for partitions and does not solve having more consumers than partitions. Nor does it replace graceful shutdown, heartbeats, or proper rebalance handling.

With Kubernetes StatefulSets, pod ordinals can provide stable identities; with dynamic Deployment replicas, a different ID strategy is needed to avoid reusing an ID while the old instance is still alive.

## 20. Is the Spring Kafka listener container running?

Before checking group assignment, verify the listener container has started.

You can access the container via `KafkaListenerEndpointRegistry`:

~~~java
@Service
public class ListenerStatusService {

    private final KafkaListenerEndpointRegistry registry;

    public ListenerStatusService(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public boolean isOrdersListenerRunning() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersListener");

        return container != null && container.isRunning();
    }
}
~~~

The listener must have the matching ID:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "orders.created",
    groupId = "order-workers"
)
public void consume(OrderCreated event) {
    orderService.process(event);
}
~~~

`isRunning()` reflects only container lifecycle. It does not prove the container holds partitions, polled successfully, or is processing records.

A container can be running while its subscription matches no topics, the group is rebalancing, or the member has no partitions due to excess consumers.

## 21. Observing assignments with a rebalance listener

Spring Kafka supports `ConsumerAwareRebalanceListener` to receive assignment/revocation/lost callbacks along with consumer context.

Example:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
ordersListenerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        PartitionAssignmentTracker tracker) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<
                    String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);

    factory.getContainerProperties()
            .setConsumerRebalanceListener(
                new ConsumerAwareRebalanceListener() {

                    @Override
                    public void onPartitionsAssigned(
                            Consumer<?, ?> consumer,
                            Collection<TopicPartition> partitions) {

                        tracker.assigned(
                            consumer,
                            partitions
                        );
                    }

                    @Override
                    public void onPartitionsRevoked(
                            Consumer<?, ?> consumer,
                            Collection<TopicPartition> partitions) {

                        tracker.revoked(
                            consumer,
                            partitions
                        );
                    }

                    @Override
                    public void onPartitionsLost(
                            Consumer<?, ?> consumer,
                            Collection<TopicPartition> partitions) {

                        tracker.lost(
                            consumer,
                            partitions
                        );
                    }
                }
            );

    return factory;
}
~~~

Key imports:

~~~java
import java.util.Collection;
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.listener.ConsumerAwareRebalanceListener;
~~~

`PartitionAssignmentTracker` is an application-defined service. Callbacks record actual assignments and update snapshots for health monitoring.

Notes:

- Callbacks may execute on the consumer thread.
- Keep callbacks short; avoid blocking HTTP/database calls.
- Never access `Consumer` from another thread.
- Handle multiple child consumers/concurrency safely.
- Do not treat an empty assignment callback during a transition as permanent group partition loss.
- Use `onPartitionsLost` specifically when ownership is lost; do not commit offsets inside the lost callback.

## 22. Storing assignment snapshots for health checks

Health endpoints normally execute on HTTP request threads, not consumer threads. Never call raw `KafkaConsumer.assignment()` from a health check because `KafkaConsumer` is not thread-safe.

A safer approach is updating an immutable snapshot from rebalance callbacks:

~~~java
@Component
public class PartitionAssignmentTracker {

    private final AtomicReference<Set<TopicPartition>> assigned =
            new AtomicReference<>(Set.of());

    public void assigned(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {

        Set<TopicPartition> next =
                new HashSet<>(consumer.assignment());

        assigned.set(Set.copyOf(next));
    }

    public void revoked(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {

        updateRemoving(partitions);
    }

    public void lost(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {

        updateRemoving(partitions);
    }

    public Set<TopicPartition> snapshot() {
        return assigned.get();
    }

    private void updateRemoving(
            Collection<TopicPartition> partitions) {

        assigned.updateAndGet(current -> {
            Set<TopicPartition> next = new HashSet<>(current);
            next.removeAll(partitions);
            return Set.copyOf(next);
        });
    }
}
~~~

This example illustrates a simple snapshot for a single consumer. With a concurrent container, store assignments keyed by **consumer/child identity** and compute the union or sum per listener. A single shared `AtomicReference` like the one above will overwrite another child's snapshot when multiple child callbacks write concurrently.

Production designs should maintain a map from child consumer identity to partition set and update atomically. When a child stops, remove its entry; on rebalance, replace only that child's assignment.

Never call `consumer.assignment()` inside a health endpoint to query a live consumer from an HTTP thread. Callback-updated snapshots cleanly separate thread ownership.

## 23. HealthIndicator: evaluating assignments against expectations

A useful health check must know which listeners **must** hold partitions and what valid wait duration applies for assignment.

Simple example for a listener dedicated to one topic:

~~~java
@Component
public class OrdersAssignmentHealthIndicator implements HealthIndicator {

    private final ListenerStatusService listenerStatus;
    private final PartitionAssignmentTracker tracker;

    public OrdersAssignmentHealthIndicator(
            ListenerStatusService listenerStatus,
            PartitionAssignmentTracker tracker) {
        this.listenerStatus = listenerStatus;
        this.tracker = tracker;
    }

    @Override
    public Health health() {

        boolean running = listenerStatus.isOrdersListenerRunning();
        int assignedCount = tracker.snapshot().size();

        if (!running) {
            return Health.down()
                    .withDetail("listenerRunning", false)
                    .build();
        }

        if (assignedCount == 0) {
            return Health.unknown()
                    .withDetail("listenerRunning", true)
                    .withDetail("assignedPartitions", 0)
                    .withDetail("reason", "No assignment observed")
                    .build();
        }

        return Health.up()
                .withDetail("listenerRunning", true)
                .withDetail("assignedPartitions", assignedCount)
                .build();
    }
}
~~~

This is an illustrative example for a listener with a single consumer snapshot. Production requires Spring Boot Actuator imports and appropriate health types.

Do not return `DOWN` immediately by default when assignment count is 0. This pod could be a valid excess consumer, awaiting a rebalance, or newly started. A sound health policy should also consider:

- Time elapsed since container start.
- Expected partition count.
- Total members/partitions in the group.
- Assignments of other members.
- Whether the listener is a mandatory workload on every pod.
- Whether the group is `Stable`.
- Whether lag is rising with no member processing.

You can use `UNKNOWN`/`OUT_OF_SERVICE` or a custom status depending on readiness goals, but you must distinguish **pod** health from **whole consumer group** health.

## 24. Pod readiness is not consumer assignment

Kubernetes readiness probes determine whether a pod enters service endpoints to receive network traffic. Kafka consumer groups do not rely on HTTP readiness to assign partitions.

If a pod has no partitions:

- Marking the pod NotReady does not automatically remove the member from the Kafka group.
- The consumer can remain in the group and wait for partitions.
- If a deployment controller replaces pods due to other readiness/liveness policies, it can trigger extra restarts/rebalances.
- If every pod is marked NotReady for empty assignment during a rebalance, the system can create a self-inflicted outage.

Distinguish:

| Health Dimension | Question | Source |
|---|---|---|
| Process liveness | Is the JVM alive and progressing? | Liveness, process/JVM |
| Application readiness | Can the API accept HTTP traffic? | Readiness |
| Listener lifecycle | Has the container started and not stopped? | Registry/container |
| Consumer assignment | Which partitions does the member own? | Rebalance callback/group description |
| Group health | Does the group have healthy members covering all required partitions? | Kafka Admin/metrics |
| Data freshness | Are records processed within SLA? | Lag/oldest age/business metrics |

A service can be HTTP-ready while its consumer group is inactive. Conversely, a pod with no partitions can still be a valid standby member.

## 25. Choosing a readiness policy by topology

There are three common models.

**Model A: every pod must hold partitions.** For example, replicas never exceed partition count and every instance is required capacity. When the group is `Stable` and a pod holds no assignment, it may indicate misconfiguration.

**Model B: more pods than partitions.** Some pods having no assignment is normal. Do not use per-pod assignment count as a readiness gate.

**Model C: dynamically scaling groups.** During scaling or rebalancing, assignments may briefly be empty. Readiness needs a grace period and group-stability confirmation before evaluating.

For overall workload health, a better question is:

> Are enough healthy members actively processing all required partitions, and is offset progress meeting the freshness SLO?

Not:

> Does every pod own at least one partition?

If a service has multiple listener groups, evaluate each listener by its role. An auxiliary listener or maintenance topic does not necessarily need to govern readiness for the entire API service.

## 26. Inspecting the group with Kafka AdminClient

Kafka `AdminClient` can describe consumer groups from a monitoring service or diagnostic tool.

Directional example:

~~~java
public Map<String, Object> describeGroup(
        AdminClient adminClient,
        String groupId) throws Exception {

    ConsumerGroupDescription description =
            adminClient.describeConsumerGroups(
                    List.of(groupId))
                .describedGroups()
                .get(groupId)
                .get();

    Map<String, Object> result = new HashMap<>();

    result.put("groupId", description.groupId());
    result.put("state", description.state().toString());
    result.put("memberCount", description.members().size());

    Map<String, List<String>> assignments = new HashMap<>();

    for (MemberDescription member : description.members()) {
        List<String> partitions =
                member.assignment().topicPartitions()
                    .stream()
                    .map(tp -> tp.topic() + "-" + tp.partition())
                    .toList();

        assignments.put(member.consumerId(), partitions);
    }

    result.put("assignments", assignments);
    return result;
}
~~~

Key imports:

~~~java
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.ConsumerGroupDescription;
import org.apache.kafka.clients.admin.MemberDescription;
~~~

This example uses `AdminClient` APIs found in modern Kafka clients; method and group-state types may vary across versions. Diagnostic calls perform network I/O, so apply timeouts and avoid running them synchronously at very high frequency on every readiness probe.

`AdminClient` descriptions show group/member assignments at the moment the broker responds. They do not prove listeners processed records successfully or that offsets are advancing. Combine group data with consumer metrics and application snapshots.

## 27. Comparing subscriptions and assignments across members

When one member has no partitions, compare it with other members:

| Info | Member A | Member B | Member C |
|---|---|---|---|
| `group.id` | `order-workers` | `order-workers` | `order-workers` |
| `client.id` | `orders-0` | `orders-1` | `orders-2` |
| subscribed topics | `orders.created` | `orders.created` | `orders.updated` |
| assignment | `P0, P1` | `P2, P3` | empty |
| state | `Stable` | `Stable` | `Stable` |

In this example, Member C subscribed to a different topic than the one with the partitions of interest. Do not expect it to receive partitions from `orders.created`.

If one group member has a different subscription than others, the assignor can only assign partitions matching its subscription. This often happens when deployments have differing profiles or some listeners subscribe to different patterns.

For investigation, logs/metrics should record listener ID, group ID, client ID, subscribed topic names (containing no sensitive data), and assignment count.

## 28. Increasing topic partitions does not guarantee instant distribution

When increasing a topic's partition count, the consumer group may need a metadata refresh and rebalance before new assignments reflect the new partitions.

Notes:

- Partition counts can only increase, not decrease through normal operations.
- Increasing partitions can change key-to-partition mappings for producers using hash partitioning.
- The consumer group must receive updated metadata and finish rebalancing.
- Assignment strategies may distribute new partitions unevenly during transition.
- Increasing partitions will not fix a wrong group ID or wrong topic subscription.

Do not add partitions just so every consumer gets an assignment if excess consumers exist by design. Partition counts impact key ordering, storage, replication, controller load, and downstream concurrency.

Before changing, assess ordering requirements, key distribution, and broker capacity.

## 29. Paused partitions are still assigned partitions

A consumer can hold assignments while its partitions are paused by the Spring Kafka container or the application. It delivers no further records to the listener per pause policy, yet that does not mean the group lost partitions.

Example:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");

if (container != null) {
    container.pause();
}
~~~

Container pause is typically designed to preserve the consumer lifecycle/polling needed while suspending fetch/delivery. Dashboards should therefore distinguish:

- assigned partition count.
- paused partition count.
- records consumed rate.
- listener processing rate.

If assigned count > 0 yet consumed rate = 0, inspect pause state, polling, backlog, and fetch errors. Do not diagnose "no partitions" when partitions are actually paused.

## 30. Manual assignment differs from group subscription

Spring Kafka can configure listeners for specific partitions via `@TopicPartition` or use `KafkaConsumer.assign()` in self-managed applications.

In manual assignment, the application specifies partitions directly and does not use the group assignor to distribute subscriptions the way `subscribe()` normally does.

Consequences:

- Multiple consumers can accidentally be configured with the same partition.
- The application must manage ownership and partition splitting.
- Rebalance callbacks/group assignments have different semantics.
- A group ID can still apply to offset commits, without the group coordinator automatically splitting partitions as in subscription mode.
- Scaling replicas does not automatically redistribute manual assignments.

If using `topicPartitions`, verify the annotation is on the right listener and partition numbers exist. Do not hunt for group assignor bugs when a listener uses manual assignment.

## 31. NonResponsiveConsumerEvent does not mean no partitions

Spring Kafka can emit `NonResponsiveConsumerEvent` when the monitor detects a consumer failing to poll at the configured cadence. This is a poll-progress issue, distinct from a member having a valid empty assignment.

Similarly:

- `ConsumerPausedEvent`: consumer paused.
- `ConsumerStoppedEvent`: consumer ended lifecycle.
- `ConsumerPartitionPausedEvent`: partition paused.
- `ListenerContainerIdleEvent`: container received no records over the configured window.
- Rebalance callbacks: assignments changed.

Do not lump all of these into one "consumer dead" health state. A member with no partitions can poll healthily; a member with partitions can become non-responsive.

Monitoring should track separate metrics for assignment, pause, poll responsiveness, stopped state, and lag.

## 32. Can a consumer group lose partitions due to max.poll.interval.ms?

`max.poll.interval.ms` sets the maximum time between polls for a consumer to retain group membership under Kafka mechanics. If a listener processes for too long, the consumer can lose membership and trigger a group rebalance.

Sequence of events:

    Consumer A is assigned P0
          |
          v
    Listener processes for too long
          |
          v
    Fails to poll again within limit
          |
          v
    Group updates membership / rebalances
          |
          v
    P0 may be assigned to Consumer B

After rebalancing, A may no longer hold partitions. Yet the root cause is slow processing/polling, not the assignor arbitrarily dropping partitions.

Check:

- `max.poll.interval.ms`.
- `max.poll.records`.
- listener processing duration p95/p99.
- synchronous commit latency.
- dependency timeouts/retries.
- GC pauses and CPU throttling.
- rebalance count/duration.
- `onPartitionsLost`/revoked callbacks.

Never just raise `max.poll.interval.ms` to hide an infinitely blocking listener. Bound dependency times, shrink batch sizes, or redesign processing.

## 33. Inspecting Spring Kafka logs

When assignments do not appear, Spring Kafka and Kafka client logs help trace group lifecycle.

You can temporarily raise log levels:

~~~yaml
logging:
  level:
    org.springframework.kafka.listener: DEBUG
    org.springframework.kafka.config: INFO
    org.apache.kafka.clients.consumer.internals.ConsumerCoordinator: DEBUG
    org.apache.kafka.clients.consumer.internals.AbstractCoordinator: INFO
~~~

Internal package names and log details depend on Kafka client version. Enable `DEBUG` only within needed scope and for a limited time because group/rebalance logging can be verbose.

Look for:

- Subscribed topics/patterns.
- Group join and generation.
- Rebalance started/completed.
- Assignments received.
- Commit/heartbeat failures.
- Authentication/authorization errors.
- Consumer shutdown/restart.
- Client ID and member identity.

Never log SASL passwords, bearer tokens, or private keys when enabling debug logging.

## 34. Metrics to monitor

An assignment/health dashboard should combine:

| Metric | Meaning |
|---|---|
| `assigned-partitions` | Partitions assigned to the consumer |
| `group-member-count` | Members in the group |
| `topic-partition-count` | Total workload partitions |
| `records-consumed-rate` | Rate of records consumed |
| `records-lag-max` | Max lag per client/partition if client exports it |
| `rebalance-total` | Rebalance count |
| `last-rebalance-seconds-ago` | Time since most recent rebalance, if supported |
| `commit-rate` / `commit-latency` | Offset commit progress |
| `listener-container-running` | Container lifecycle |
| `consumer-paused` | Pause state |
| `nonresponsive-events` | Non-responsive poll alerts |
| `oldest-record-age` | Age of unprocessed records |
| `processing-duration` | Listener processing time |

Exact metric names and groups depend on Kafka client, Spring Kafka, Micrometer, and exporter. Verify actual metrics before creating alerts.

Never attach `eventId`, `offset`, or `UUID` as metric labels due to high cardinality. Application, group, listener, and topic can be used if cardinality is controlled.

## 35. Readiness policy: do not mark DOWN solely because assigned count is 0

A naive readiness check such as:

~~~java
if (assignedPartitions.isEmpty()) {
    return Health.down().build();
}
~~~

can create false negatives when a pod is a valid excess consumer or the group is rebalancing.

A realistic policy needs at least:

1. Has the listener container started?
2. Is this pod in a set of instances required to hold partitions?
3. What are the current total partitions and consumer count?
4. Has the group been `Stable` long enough?
5. Are mandatory partitions covered by active members?
6. Are lag/oldest record age within SLO?
7. How long has the assignment been empty?
8. Is this an expected scaling/deployment state or an incident?

Health status can be categorized into:

- **UP:** container running and assignment/processing match topology.
- **UNKNOWN/STARTING:** insufficient time elapsed for assignment to finish.
- **DEGRADED:** one member has no assignment while the group still handles the workload.
- **DOWN/OUT_OF_SERVICE:** the whole group has no consumers covering mandatory partitions or freshness SLO is breached.

This is an example application classification, not a mandatory Spring Kafka enum. Choose the mapping to Kubernetes readiness based on deployment goals.

## 36. Do not use liveness to fix empty assignments

Failing a liveness probe typically restarts the container/pod. If a consumer has no partitions because concurrency exceeds partition count, restarting will not make new partitions appear.

A dangerous loop:

    Pod has no partitions
          |
          v
    Liveness fails
          |
          v
    Kubernetes restarts pod
          |
          v
    Consumer group rebalances
          |
          v
    New pod still gets no partitions
          |
          v
    Liveness fails again

The result is a rebalance storm and even less stable workloads.

Use liveness to detect a process failing to progress at the JVM/application level. Use readiness and group-level monitoring to reflect workload processing capability. Never use restarts to force the assignor to hand partitions to a specific member.

## 37. Ordered diagnostic procedure

When a listener reports receiving no partitions:

1. **Verify the exact group ID.** Read runtime config/annotations and compare with the group being inspected.
2. **Verify the exact topic.** Check topic name, regex pattern, and cluster.
3. **Check partition count.** Does the topic have appropriate partitions?
4. **Check listener lifecycle.** Has the container started?
5. **Check member count.** Do total consumer threads exceed partition count?
6. **Check group state.** `Stable`, `PreparingRebalance`, `CompletingRebalance`, or `Empty`?
7. **Check member assignments.** Is only one member empty or the entire group?
8. **Check assignor and subscriptions.** Do members share compatible strategies/topic sets?
9. **Check rebalance churn.** Slow polling, restarts, network, or static membership conflicts?
10. **Check ACLs/metadata.** Can the consumer read/describe/join the group?
11. **Distinguish pause and idle.** Are partitions assigned yet paused, or is the topic empty?
12. **Inspect offsets separately.** Check `auto.offset.reset` and retention only after confirming assignment.
13. **Check lag and committed offsets.** Are other members processing?
14. **Pick root-cause recovery.** Fix group/topic/config/partitions/capacity; avoid blind restarts.

This procedure prevents confusing misconfiguration with expected standby consumer states.

## 38. Real-world scenarios

### 38.1. One of three pods has no partitions

A topic has six partitions, the group has three pods with `concurrency=2`. Total six consumers; each consumer can get one partition. If one pod has no assignment, check member count and assignments on the other two pods. The group may still be stabilizing, or that pod's listener may have a different subscription.

### 38.2. Six pods but only two partitions

With `concurrency=1` per pod, the group has six members but only two partitions. Four pods having no assignments is normal. Do not restart or add partitions if current throughput meets SLA.

### 38.3. Group Stable yet all assignments empty

Check whether subscriptions match topics, whether group ID is right, whether topics have partitions, and whether members subscribe to the right topics. If the group description shows all members empty while the topic has partitions, inspect assignor/subscription and metadata.

### 38.4. Group stuck in PreparingRebalance

Check consumer processing duration, `max.poll.interval.ms`, network, pod restarts, and duplicate `group.instance.id`. An unstable group may not hold assignments long enough to process.

### 38.5. Assigned yet no records

Check producer traffic, committed offsets, pause state, and topic partitions. This can be normal idleness rather than an assignment failure.

### 38.6. Assigned yet poll hits authorization errors

Check ACLs and credentials. Assignment and fetch permissions are two separate issues; fix permissions rather than raising partition count.

## 39. Recovery: when to add partitions vs. reduce consumers

Only add partitions when throughput/parallelism genuinely requires it and business consequences have been evaluated.

**Adding partitions may fit when:**

- Consumer capacity is bottlenecked by partition count.
- Sufficient key distribution and broker capacity exist.
- Key-to-partition mapping changes for hash-partitioned producers are acceptable.
- Ordering is only required per partition and designed accordingly.

**Reducing concurrency/replicas may fit when:**

- Many consumers sit unassigned for long periods.
- Excess pods/consumers create unnecessary overhead.
- Autoscalers scale on an inappropriate metric and create surplus consumers.
- Downstream dependencies cannot sustain current consumer counts.

**Do not change topology when:**

- The group is in a brief rebalance.
- Topic/subscription/group ID is wrong.
- ACLs or metadata are failing.
- Consumers are paused or processing slowly.
- The real fault is an invalid offset rather than assignment.

No partition-count increase can fix a wrong group ID or mismatched topic pattern.

## 40. Testing assignments in Spring Kafka

Use Embedded Kafka or Testcontainers with a compatible broker to test real assignments.

A scenario:

1. Create topic `orders.created` with three partitions.
2. Create listener group `order-workers` with `concurrency=3`.
3. Wait for assignment to stabilize via callbacks or container metadata.
4. Verify total group assignment equals three.
5. Add two more consumer members in the same group.
6. Verify some members hold no partitions while the group still processes all three partitions.
7. Send records to each partition.
8. Verify records are processed by valid members.
9. Check committed offsets and lag after processing.
10. Stop one member, wait for rebalance, and verify partitions are redistributed.

Do not assert that a specific partition always belongs to a consumer with a fixed client ID if the assignor may shift assignments. Assert invariants: each partition is assigned to at most one member in the group and total assignments cover the subscribed partition set properly.

## 41. Testing cases where a group gets no partitions

Tests should cover configuration errors:

**Topic pattern mismatch:** listener subscribes with a pattern matching no topics; confirm no assignment and logs show actual subscription.

**Wrong group ID:** listener uses a different group than the one the test describes; confirm the member appears in the runtime group.

**Topic has no partitions yet:** test that the listener cannot receive data from an unprovisioned topic; control auto-create in tests so results are deterministic.

**Excess consumers:** create more consumers than partitions; confirm surplus members have empty assignments without failing the whole group.

**Rebalance:** add/remove members and confirm assignments can temporarily change before becoming `Stable`.

**Manual assignment:** test a listener using `topicPartitions` gets the exact configured partitions without relying on group assignor expectations.

## 42. Testing readiness policies

Health tests should verify readiness by topology, not just an empty snapshot.

Cases:

| Container | Group State | Group Assignment | Expected Outcome |
|---|---|---|---|
| Not started | `Empty` | None | Not ready |
| Running newly started | `PreparingRebalance` | Unstable | Starting/unknown during grace period |
| Running | `Stable` | Full partitions; this member empty due to excess consumers | Pod can still be ready |
| Running | `Stable` | Entire group empty despite mandatory partitions existing | Degraded/Not ready |
| Running | `Stable` | Assigned; topic has no records yet | Ready if other conditions pass |
| Running, paused | `Stable` | Assigned | Ready or degraded per pause/SLO policy |
| Stopped | `Empty` | None | Not ready if listener is mandatory |

Readiness checks should not call `AdminClient` with long timeouts on every probe. A bounded monitor can refresh group snapshots periodically, cache results briefly, and handle telemetry errors cleanly.

## 43. Runbook when a group receives no partitions

When an incident occurs in production:

1. Record application instance, listener ID, group ID, and topic.
2. Confirm whether the listener container is running.
3. Check topic existence and partition count.
4. Describe the consumer group, member count, state, and assignments.
5. Determine whether only one member or the entire group lacks partitions.
6. Compare total group consumer threads against partition count.
7. Confirm all members have compatible subscriptions/assignors.
8. Inspect rebalance, heartbeat, poll, and authentication logs.
9. Check for duplicate `group.instance.id`.
10. Check pause state and `NonResponsiveConsumerEvent`.
11. Cross-check committed offsets, lag, and oldest record age.
12. Fix the exact cause: topic, group ID, regex, ACLs, concurrency, partition count, or timeouts.
13. Wait for the group to become `Stable` and verify new assignments.
14. Send a safe test record and confirm listener processing.
15. Monitor lag/commit progress after recovery.
16. Document topology/config changes and update readiness expectations.

Never reset offsets or delete a consumer group to fix an empty assignment before identifying the root cause. Those actions can discard progress or trigger additional rebalances without fixing misconfiguration.

## 44. Common design mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Assuming every pod must have partitions | False unhealthy when excess consumers exist | Base readiness on topology/group |
| Inspecting only one member | Misses other members actively processing | Inspect whole group assignment |
| Confusing listener ID with group ID | Investigating the wrong group | Configure `groupId` explicitly |
| Raising concurrency when partitions are few | Creates extra surplus consumers | Calculate `replicas × concurrency` |
| Adding partitions to fix a topic pattern | Leaves broken subscription unfixed | Check regex/topic first |
| Using liveness restarts on empty assignments | Rebalance storm | Separate liveness and readiness |
| Confusing idle with no assignment | False alerts | Measure assigned partitions separately |
| Confusing pause with lost assignment | Wrong recovery actions | Track pause and assignment separately |
| Treating `auto.offset.reset` as assignment policy | Unnecessary offset changes | Diagnose assignment first |
| Ignoring group state | Restarting during normal rebalance | Wait for `Stable` with a timeout |
| Using manual assignment while expecting assignor | Partitions misassigned/unassigned | Verify subscription mode |
| Reusing `group.instance.id` | Member fencing/membership conflict | Unique identities |
| Calling `KafkaConsumer` from health thread | Thread-safety violation | Use snapshots/callbacks/`AdminClient` |
| Relying on `isRunning()` to declare health | Container running with no assignment | Combine group/lag/freshness |
| Alerting solely on assigned count | Does not reflect whether workload progresses | Combine assignment and SLO |

## 45. Production deployment checklist

- Verified actual topic and partition count?
- Listener uses the right cluster and group ID?
- Does `@KafkaListener` declare `topics`, `topicPattern`, or `topicPartitions`?
- Does the pattern match real topics?
- Does total `replicas × concurrency` exceed partition count?
- Do group members have compatible subscriptions?
- Is the group state stable or constantly rebalancing?
- Are assignments inspected at both member and group levels?
- Are consumer assignors compatible across members?
- Is `group.instance.id` unique?
- Is the container running and not unintentionally stopped/paused?
- Do ACLs/credentials allow subscribe/fetch/commit?
- Are `max.poll.interval.ms` and processing duration aligned?
- Do health checks distinguish pod readiness from group health?
- Are excess consumers treated as a valid state?
- Are metrics in place for assigned partitions, member count, lag, and rebalances?
- Do integration tests cover `Stable` groups, excess consumers, mismatched patterns, and rebalances?
- Does a runbook verify offsets before resetting/recovering?

## 46. Conclusion

**Consumer group has no partition assignment** can be a configuration bug or a valid topology state. Before intervening, distinguish one member lacking assignments from the entire group lacking assignments, then verify topic, partition count, group ID, subscription, concurrency, and group state.

In Spring Kafka, a running listener container does not prove the consumer has received partitions. Conversely, one member with an empty assignment does not necessarily impair the service if other members own all mandatory partitions. Readiness should evaluate **overall workload capability and freshness SLOs**, provide grace periods for startup/rebalances, and avoid using liveness restarts to force Kafka to assign partitions.

By diagnosing systematically across topic metadata, group descriptions, rebalance callbacks, container lifecycle, and consumer metrics, operations teams can fix root causes without causing rebalance storms, resetting offsets wrongly, or marking valid standby pods unhealthy.
