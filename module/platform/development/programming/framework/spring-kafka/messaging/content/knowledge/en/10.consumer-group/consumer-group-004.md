# Group Instance ID and Static Membership

In a consumer group, each consumer normally joins the group with a member ID assigned by Kafka. When a consumer stops or loses connectivity, the group may rebalance to redistribute partitions. For multi-instance applications that frequently restart during rolling deployments, brief group departures can trigger unnecessary rebalances, pausing listeners and increasing consumer lag.

Kafka supports **static membership** via the `group.instance.id` property. Instead of relying solely on a temporary member ID issued by the coordinator, a consumer declares a stable identifier for a logical instance. When the instance restarts while the session is still valid, it can rejoin the group with its previous identity and retain its assignment, avoiding some rebalances caused by short restarts.

Static membership is useful for long-lived consumers with stable instance identities, such as StatefulSets, VMs, or workers identified by ordinals. This mechanism must be configured carefully: every instance in the same group must have a unique `group.instance.id`, the ID must remain stable across restarts, and `session.timeout.ms` should match actual recovery times.

## 1. Dynamic Membership and Static Membership

Under standard dynamic membership, a consumer joins the group using `group.id`; the coordinator assigns a member ID for that session. When a consumer leaves the group or is considered disconnected, the group can rebalance to hand its partitions to remaining members. If a process restarts briefly, leaving and rejoining can cause a rebalance even though the instance was only momentarily interrupted.

Static membership adds `group.instance.id`, an application-provided identifier kept stable across runs of the same instance. The coordinator can recognize this as a static member that previously participated in the group. When the instance experiences a brief interruption, the coordinator retains the member state for the duration of `session.timeout.ms` instead of immediately redistributing partitions. If the instance returns in time with the same ID, it can continue participating without triggering a rebalance from that restart.

| Criterion | Dynamic membership | Static membership |
|---|---|---|
| Member identifier | Kafka assigns a member ID per join session | Application provides a stable `group.instance.id` |
| Short restarts | Can cause rebalances as the member leaves and rejoins | Can preserve assignment while the session remains valid |
| Stable ID requirement | No application-managed instance ID required | Requires a unique ID per instance in the same group |
| Dead instance detection | Based on heartbeats and session timeout | Also based on heartbeats and session timeout; partition revocation may be delayed until the session expires |
| Scaling out instances | A newly joined member causes the group to adjust assignments | A new static member can still trigger a group rebalance to redistribute partitions |
| Configuration risk | Low risk of ID collisions managed by the application | Duplicate `group.instance.id` values can cause a member to be fenced |

Static membership does not disable rebalancing. A group still needs to rebalance when partitions are added or deleted, subscriptions change, the actual member count changes, or a static member fails to return before the session timeout expires. This mechanism primarily reduces rebalances caused by brief interruptions of an instance with a stable identity.

## 2. What Is group.instance.id?

`group.instance.id` is a string configuration property of the Kafka consumer. When set, the consumer becomes a static member. This value must be unique within an active consumer group. Two consumers belonging to the same `group.id` must not concurrently share the same `group.instance.id`.

For example, workers reading the `orders` topic together:

```text
group.id = orders-worker

Instance A: group.instance.id = orders-worker-0
Instance B: group.instance.id = orders-worker-1
Instance C: group.instance.id = orders-worker-2
```

Each instance keeps its ID across restarts. When Instance A restarts, it reuses `orders-worker-0`. When scaling out an additional Instance D, the new instance needs an unused ID, such as `orders-worker-3`.

`group.instance.id` differs from `group.id`:

- `group.id` identifies the group of consumers that share partition reading and committed offsets.
- `group.instance.id` identifies a specific instance inside that group.
- The same instance ID can be used in another group because uniqueness is scoped per group, but one ID must not be shared between two active consumers in the same group.

`group.instance.id` also differs from `client.id`. `client.id` is mainly used to identify the client in logs, metrics, and quotas; it does not replace static member identity. Setting identical `client.id` values does not enable static membership, and setting `group.instance.id` does not replace `group.id`.

## 3. Why Does Static Membership Reduce Rebalances?

Suppose a consumer holds partitions `orders-0` and `orders-1`. The consumer's pod is restarted during a deployment. With dynamic membership, the coordinator can detect the member leaving the group and start redistributing partitions. When the new pod comes up, it rejoins and can trigger another rebalance.

With static membership, the new pod reuses the same `group.instance.id`. The coordinator retains the static member during the session timeout window. If the new pod returns before the session expires, the coordinator recognizes the old instance and can preserve the existing assignment. Remaining consumers do not need to pause to redistribute partitions just for this short restart.

A consequence to account for is that when a static member closes its consumer cleanly, the client does not immediately leave the group the way a dynamic member normally does. The coordinator holds the static member's identity and partitions until `session.timeout.ms` expires or that member rejoins. This benefits rolling restarts, but when scaling down or permanently stopping an instance, partitions may take longer to be reassigned. Therefore, static membership should be designed alongside deployment workflows and failover timing.

Illustrative diagram:

```text
Dynamic membership
------------------
Consumer running
    |
    v
Restart -> member leaves group -> rebalance
    |
    v
New consumer joins -> rebalance/reassignment

Static membership
-----------------
Consumer running with fixed group.instance.id
    |
    v
Short restart -> coordinator retains member during session timeout
    |
    v
Instance restarts with the same ID
    |
    v
Resumes assignment if it returns in time
```

This is a membership stability benefit, not a guarantee that partitions always belong to one instance under all circumstances. If the instance fails to return in time, the group must still revoke membership and redistribute partitions so the remaining consumers can continue working.

## 4. Configuring a Plain KafkaConsumer

Static membership is enabled by setting `ConsumerConfig.GROUP_INSTANCE_ID_CONFIG` in the consumer configuration:

```java
Properties props = new Properties();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(ConsumerConfig.GROUP_ID_CONFIG, "orders-worker");
props.put(ConsumerConfig.GROUP_INSTANCE_ID_CONFIG, "orders-worker-0");
props.put(ConsumerConfig.SESSION_TIMEOUT_MS_CONFIG, 45_000);
props.put(ConsumerConfig.HEARTBEAT_INTERVAL_MS_CONFIG, 15_000);
props.put(ConsumerConfig.MAX_POLL_INTERVAL_MS_CONFIG, 300_000);
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName());
props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName());

KafkaConsumer<String, String> consumer = new KafkaConsumer<>(props);
```

Imports and subscribe/poll logic are omitted to focus on static membership. Both the client and broker must support this property; static membership was introduced in Kafka 2.3. Use a Kafka client compatible with the broker and verify your actual cluster version before enabling it.

In the example, `orders-worker-0` is the stable ID of instance 0. Do not generate a new random UUID every time the application starts, because the coordinator will treat it as a different member and the benefit of preserving the old membership is lost. Also do not hard-code the same value for all replicas of a deployment.

## 5. Configuring in Spring Boot and Spring Kafka

Spring Kafka uses the Kafka consumer client underneath, so static membership can be configured via consumer properties:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: orders-worker
      enable-auto-commit: false
      properties:
        "[group.instance.id]": orders-worker-0
        "[session.timeout.ms]": 45000
        "[heartbeat.interval.ms]": 15000
        "[max.poll.interval.ms]": 300000
```

Spring Boot forwards properties in `consumer.properties` to the Kafka client. The bracket syntax preserves dotted property names in YAML. In multi-instance deployments, `group.instance.id` must be assigned individually to each instance instead of using the same `orders-worker-0` across all pods.

The listener can declare its group ID as usual:

```java
@Component
public class OrderListener {

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            id = "ordersListener",
            topics = "orders",
            groupId = "orders-worker")
    public void onMessage(String payload) {
        orderService.handle(payload);
    }
}
```

The listener's `groupId` must match the group that the static member joins. `group.instance.id` is a consumer configuration property, not a property of a message or individual record.

### Using Concurrency

A `ConcurrentMessageListenerContainer` can create multiple child containers, each owning a `KafkaConsumer`. Because every consumer in the same group needs its own `group.instance.id`, all child containers cannot share the same ID. Spring Kafka versions that support static membership for concurrent containers have a mechanism to append suffixes to the base ID for each child container to avoid collisions. Example:

```java
@KafkaListener(
        id = "ordersListener",
        topics = "orders",
        groupId = "orders-worker",
        concurrency = "3")
public void onMessage(String payload) {
    orderService.handle(payload);
}
```

If the instance's base ID is `orders-worker-pod-0`, the child consumers can be created with separate suffixed IDs managed by Spring Kafka. Exact behavior depends on the Spring Kafka version; verify how the container generates IDs before deploying with high concurrency. When manually creating multiple `ConsumerFactory` beans or multiple listener containers, ensure each consumer has a unique ID within the group.

## 6. Assigning Stable IDs to Instances

A static member needs a durable identity across restarts. How IDs are assigned depends on the deployment platform:

| Platform | Suggested ID Assignment | Notes |
|---|---|---|
| Kubernetes StatefulSet | Use pod name/ordinal such as `orders-worker-0` | A pod recreated with the same ordinal preserves its identity; avoid running two pods with the same ordinal concurrently |
| VMs or fixed hosts | Use node name or stable instance code | Do not reuse an ID for two processes in the same group running concurrently |
| Workers with a registry | Store a stable ID in a registry/configuration store | Must handle ID allocation and reclamation lifecycles |
| Deployment with random pod names | Requires a separate mechanism to generate stable identities | New pod names after a restart usually cannot preserve old IDs |

For example, with a Kubernetes StatefulSet, the pod hostname typically contains the StatefulSet name and ordinal. You can pass an environment variable into the application:

```yaml
env:
  - name: KAFKA_GROUP_INSTANCE_ID
    valueFrom:
      fieldRef:
        fieldPath: metadata.name
```

Then reference the environment variable in Spring Boot configuration:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[group.instance.id]": ${KAFKA_GROUP_INSTANCE_ID}
```

This example illustrates passing the pod name into configuration. Ensure the StatefulSet uses stable names/ordinals, and if concurrency is greater than one, handle per-child-consumer IDs according to Spring Kafka's mechanism.

Do not use a shared fallback value in production across multiple replicas. For example, `${KAFKA_GROUP_INSTANCE_ID:orders-worker}` is convenient for running a single local instance, but if multiple pods miss the environment variable, all will share the same ID and trigger fencing. Let the application fail fast when a required ID is missing in a multi-replica environment.

## 7. group.instance.id Must Be Unique

If two active consumers in the same group use the same `group.instance.id`, the coordinator cannot treat them as two separate static members. One member can be fenced when another member with the same ID joins the group. The application may receive errors such as `FencedInstanceIdException` or an equivalent error depending on the client/protocol version.

Example of an incorrect configuration:

```text
group.id = orders-worker

Pod A: group.instance.id = orders-worker
Pod B: group.instance.id = orders-worker   <-- duplicate ID
```

A proper configuration requires distinct IDs:

```text
group.id = orders-worker

Pod A: group.instance.id = orders-worker-0
Pod B: group.instance.id = orders-worker-1
```

When fencing occurs, first locate all running processes using the same `group.instance.id` in the group, along with actual configuration values and how IDs are generated in the deployment. Do not work around it by generating a random ID on every retry, as that masks the identity-allocation bug and can leave the old static member lingering until the session timeout expires.

## 8. session.timeout.ms and Recovery Time

`session.timeout.ms` is the duration the coordinator waits for a heartbeat before considering the consumer disconnected. With static membership, when an instance temporarily loses connectivity or restarts, partitions can be held for that member until the session timeout expires. Thus, session timeout directly affects the window in which the application can recover without triggering a rebalance.

| Session timeout value | Impact |
|---|---|
| Too short | Short restarts or brief network glitches can exceed the threshold; the group revokes the member early and rebalances |
| Well-sized | Allows an instance to restart within the expected time while detecting failures within an acceptable window |
| Too long | Reduces rebalances from brief disruptions, but if an instance dies completely, partitions may be held for a long time before being handed to another consumer |

Values accepted by the broker also depend on `group.min.session.timeout.ms` and `group.max.session.timeout.ms`. Clients sending values outside the broker-permitted range may be rejected when joining the group. `heartbeat.interval.ms` is normally set smaller than `session.timeout.ms`; Kafka documentation commonly recommends a heartbeat interval no greater than roughly one-third of the session timeout in typical configurations.

For example, `session.timeout.ms=45000` and `heartbeat.interval.ms=15000` create a 45-second session window. This is not a mandatory configuration for every system. Measure actual startup times, recovery times during broker/network disruptions, and failover requirements to pick appropriate values.

## 9. Distinguishing Session Timeout and max.poll.interval.ms

These two properties are often confused:

| Property | Monitors | When exceeded |
|---|---|---|
| `session.timeout.ms` | Heartbeats from the consumer to the group coordinator | The coordinator considers the member disconnected after the wait period expires |
| `max.poll.interval.ms` | Application progress calling `poll()` | The client is considered no longer making processing progress; it stops heartbeating / leaves the group according to membership semantics |

`session.timeout.ms` detects loss of connectivity; `max.poll.interval.ms` detects a consumer failing to call poll in time. A consumer can remain network-connected while a listener takes too long processing a batch and fails to poll again. Static membership does not allow a listener to process indefinitely.

With a dynamic member, when `max.poll.interval.ms` is exceeded, the consumer can leave the group and partitions are redistributed normally. With a static member, the client stops sending heartbeats when the poll limit is exceeded; the coordinator typically retains membership until `session.timeout.ms` expires before revoking and redistributing partitions. This helps reduce rebalances from certain brief stalls, but it can also lengthen the time to detect a stuck instance.

Therefore, configure both values for their two distinct purposes: `max.poll.interval.ms` must cover the maximum processing duration of one poll cycle; `session.timeout.ms` must cover the desired recovery window while still meeting failover SLAs. Combine these with `max.poll.records` and DB/HTTP timeouts to prevent listeners from blocking for too long.

## 10. Static Membership in Rolling Deployments and Autoscaling

Static membership is especially useful during sequential rollouts of instances with stable identities. For example, a StatefulSet has three pods `orders-worker-0`, `orders-worker-1`, and `orders-worker-2`. When updating pod ordinal 1, the new pod can reuse ID `orders-worker-1`; if it returns before the session timeout expires, the group has a chance to preserve the current assignment.

When scaling up, each new instance needs an ID not already present in the group. Adding a new member can cause the group to rebalance to redistribute partitions. When scaling down, a deleted static member will still be held until `session.timeout.ms` expires; therefore, its partitions may not be reassigned immediately to other members.

With Deployments that have random pod names, static membership rarely helps if every restart generates a new ID. You can build a stable ID assignment mechanism using ordinals or a registry, but you must handle the case where the old instance has not stopped yet while the new instance already receives the same ID. Two processes sharing an ID will cause fencing.

Do not enable static membership merely because you have multiple replicas. Consider:

1. Whether instances have stable identities across restarts.
2. Whether actual restart/rolling-update times fall within the session timeout.
3. What delay is acceptable when an instance dies and partitions have not yet been reassigned.
4. How the system assigns IDs during scale-up, scale-down, and node replacement.
5. Whether concurrency settings create multiple consumers in the same group on one instance.

## 11. Changes That Can Still Trigger Rebalances

Static membership does not keep assignments unchanged regardless of what happens. The following situations can still force the group to redistribute partitions:

- Adding or deleting partitions on a topic subscribed to by the group.
- Changing subscriptions or patterns so that the set of subscribed topics changes.
- Adding a new static member with a different ID to the group.
- A static member failing to return before `session.timeout.ms` expires.
- Coordinator or broker state changes requiring the group to recover membership.
- Changing the partition assignor or group protocol in a way that requires recomputing assignments.

Static membership also does not guarantee a consumer keeps the exact same partitions if assignments must change because the group topology changed. Treat it as a mechanism to reduce rebalances from brief restarts, not a mechanism to pin partitions permanently.

## 12. Monitoring and Troubleshooting

When deploying static membership, monitor:

- Rebalance counts and rebalance reasons per consumer group.
- Member IDs, `group.instance.id`, and partition assignments of each instance.
- Consumer lag during rolling deployments and after scaling.
- Actual restart times compared against `session.timeout.ms`.
- `FencedInstanceIdException` errors or duplicate static member ID errors.
- Listener processing times, records per poll, and `max.poll.interval.ms` breaches.
- Number of partitions not yet reassigned after a static member stops operating.

You can inspect group state with the Kafka CLI:

```bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group orders-worker
```

The output lets you inspect members, client IDs, hosts, partition assignments, current offsets, and lag. Depending on the Kafka version, the tool may provide additional static member details; if `group.instance.id` is not visible, use consumer logs or compatible admin tools to verify the actual configuration.

When fencing occurs, first find all processes using the same `group.instance.id` in the group. When partitions are reassigned slowly after a pod dies, inspect the session timeout and heartbeat logs. When rebalances still happen during rolling deployments, verify that the new pod uses the exact ID of the old pod, that restart time fits within the session timeout, and that no duplicate-ID instances run concurrently.

## 13. Common Configuration Mistakes

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `FencedInstanceIdException` | Two consumers in the same group use the same `group.instance.id` | Assign distinct IDs to each instance and stop duplicate processes |
| Restarts still cause rebalances | New ID after restart, startup exceeds session timeout, or topology changed | Keep IDs stable, measure startup time, and check rebalance triggers |
| Partitions reassigned slowly after a pod dies | Static member is retained until `session.timeout.ms` expires | Tune session timeout according to failover SLA |
| Consumer evicted during long batch processing | Exceeded `max.poll.interval.ms` | Lower `max.poll.records`, optimize the listener, and configure an appropriate poll interval |
| Multiple child consumers have the same ID | Concurrency configuration does not generate distinct IDs or Spring Kafka version lacks the expected suffixing | Check version, actual IDs of each child, and factory configuration |
| Client fails to join group | Broker/client does not support it or session timeout is outside broker bounds | Check Kafka version and `group.min/max.session.timeout.ms` |

## Checklist Before Enabling Static Membership in Production

- Brokers and Kafka clients support `group.instance.id`.
- Every consumer in the same group has a unique `group.instance.id`.
- IDs remain stable across restarts of the same instance.
- An ID is never used concurrently by two processes or two pods.
- If using Spring Kafka concurrency, each child consumer is verified to have a distinct ID.
- `session.timeout.ms` balances recovery time against failover time.
- `heartbeat.interval.ms` is within reasonable bounds and accepted by brokers.
- `max.poll.interval.ms` covers the processing cycle and is not used as a substitute for session timeout.
- Rolling restarts, scale-up, scale-down, and abrupt instance crashes have been tested.
- Monitoring is in place for rebalances, lag, static member IDs, and fencing errors.

Static membership makes consumer groups more stable when instances with fixed identities undergo short restarts. To benefit from this mechanism, the application must provide unique, durable `group.instance.id` values, align `session.timeout.ms` with recovery times, and keep `max.poll.interval.ms` aligned with processing times. When deployed properly, the group reduces unnecessary rebalances while still reclaiming partitions when an instance genuinely fails to return.
