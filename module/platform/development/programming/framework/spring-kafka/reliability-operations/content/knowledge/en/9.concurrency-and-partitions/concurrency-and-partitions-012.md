# Checking Assignments After Deployment

After deploying a new version of a Spring Kafka service, you must confirm that consumer instances have joined the right consumer group and received the expected partitions. A pod in `Running` or `Ready` state does not prove Kafka has assigned partitions to the consumer. Likewise, running replica count does not reveal the exact number of consumer members or how partitions are distributed.

Post-deployment assignment checks catch issues early, such as an altered group ID, concurrency not taking effect, consumers exceeding partition count, consumers receiving no partitions, prolonged rebalances, or traffic piling onto one partition. Verification should combine deployment state, Kafka consumer group state, Spring Kafka logs, and consumer lag.

## 1. Understanding What Assignments to Verify

Kafka assigns partitions to consumer members within a consumer group. For a given topic and group, each partition is assigned to at most one member at a time. One member can receive multiple partitions; a member can also receive zero partitions.

Example of the `orders` topic with six partitions and a service running three replicas, each with one consumer:

```text
Deployment: order-service
Replicas: 3
Listener concurrency: 1
Group ID: order-service

Consumer A -> orders-0, orders-1
Consumer B -> orders-2, orders-3
Consumer C -> orders-4, orders-5
```

The assignment above is only an example. Kafka may distribute partitions differently depending on the partition assignor, subscriptions, and active members. What must be verified is that every expected partition is owned by the group, no partition is assigned twice within the same group, and load is distributed appropriately.

In Spring Kafka, distinguish:

- **Replica:** an application process or pod.
- **Listener concurrency:** the number of child consumer containers created for a listener endpoint within each process.
- **Consumer member:** a Kafka consumer participating in the group. One listener can spawn multiple members when concurrency exceeds one.
- **Partition assignment:** the set of partitions Kafka assigns to each member.

For one listener endpoint sharing a group ID, expected member count is usually estimated as:

```text
expected members = replicas × listener concurrency
```

This is the expected member count once all replicas and child containers start successfully. If an application has multiple listener endpoints, each endpoint can have its own group ID, subscription, and concurrency; do not sum all listeners into one figure if they belong to different groups.

## 2. Confirm the Deployment Completed

Before checking Kafka, confirm Kubernetes has finished rolling out the intended version. For example:

```bash
kubectl rollout status deployment/order-service
kubectl get deployment order-service
kubectl get pods -l app=order-service -o wide
```

Check the following:

- Desired replica count matches ready pod count.
- Pods are running the expected new image/tag.
- No pods are restarting repeatedly or failing readiness/liveness probes.
- Old pods have terminated per rollout policy, unless the deployment intentionally uses surge.
- Environment variables and ConfigMaps/Secrets supply the right `group.id`, topics, and concurrency.

During a rolling update, new pods may join the group before old pods leave. Member count can temporarily exceed configured replica count. This is normal when the deployment uses `maxSurge`; wait for the rollout to settle before drawing conclusions about final assignments.

You can inspect logs across all pods:

```bash
kubectl logs -l app=order-service --since=10m --prefix=true
```

Depending on `kubectl` version, the `--prefix` flag may differ. If unsupported, fetch logs per pod by pod name. With multiple replicas, prefixes or pod names help pinpoint which instance emitted an assignment log.

## 3. Check the Consumer Group in Kafka

The `kafka-consumer-groups` tool provides direct visibility into consumer group state and offsets. Run it from an environment with Kafka client tooling connected to the target cluster:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --list
```

Confirm the service's group ID appears in the list. Then inspect group state:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --group order-service \
  --state
```

On supported Kafka versions, this command prints group state and coordinator details. A stable state is normally reported as `Stable`. While members join or leave, transitional states such as `PreparingRebalance` or `CompletingRebalance` may appear. State names and CLI flags can vary across Kafka versions; check `kafka-consumer-groups.sh --help` if an option is unsupported.

A group stuck continuously rebalancing must be investigated. Causes include crashing/restarting pods, missed heartbeats, exceeding `max.poll.interval.ms`, changing subscriptions, or connectivity failures. Do not judge a group broken from a single snapshot taken mid-deployment; re-check after the rollout finishes.

### Inspect Members and Partition Assignments

On versions supporting `--members --verbose`, run:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --group order-service \
  --members \
  --verbose
```

Output typically includes columns such as:

| Column | Meaning |
|---|---|
| `CONSUMER-ID` | Current member identifier within the group. Value can change after consumer restarts or rebalances. |
| `HOST` | Host address observed by the broker for the member. |
| `CLIENT-ID` | Client ID used to identify the consumer in logs and metrics. |
| `#PARTITIONS` | Number of partitions currently assigned to the member. |
| `ASSIGNMENT` | List of topic-partitions assigned to the member. |

This provides direct evidence to reconcile member count and assignments. Do not use `CONSUMER-ID` as a long-lived pod identifier because consumer IDs can change on restart. Cross-reference `HOST`, `CLIENT-ID`, startup logs, and pod names to identify the exact instance.

If your Kafka version does not support `--members --verbose`, consult docs for your version or use Kafka AdminClient's `describeConsumerGroups`. Do not infer assignments solely from offset rows in default output.

### Inspect Offsets and Lag

The default describe command shows committed offsets and lag per partition:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --group order-service
```

Common columns include `TOPIC`, `PARTITION`, `CURRENT-OFFSET`, `LOG-END-OFFSET`, `LAG`, `CONSUMER-ID`, `HOST`, and `CLIENT-ID`.

| Column | How to read it |
|---|---|
| `CURRENT-OFFSET` | The group's committed offset for the partition, usually the next position to read. |
| `LOG-END-OFFSET` | End of the partition log at query time. |
| `LAG` | Offset difference between log end and committed offset. This is a progress indicator, not always identical to exact pending business records. |
| `CONSUMER-ID` / `HOST` | Member currently owning the partition per returned group state. |

If a group just started or has not committed offsets yet, some fields may show `-`. Do not interpret that as zero lag. Check group state, member assignments, and the first offset commit.

## 4. Reconciling Assignments with Replicas and Concurrency

Suppose a deployment has four replicas, listener concurrency of two, and the topic has eight partitions:

```text
Expected consumer members = 4 × 2 = 8
Available partitions = 8
```

The group can assign one partition per member. If the topic had only five partitions, at most five members would hold partitions and the remaining three would sit idle for that topic. That does not automatically indicate an application error.

| Replicas | Concurrency | Expected members | Topic partitions | Expectation |
|---:|---:|---:|---:|---|
| 2 | 1 | 2 | 6 | Two members split six partitions. |
| 3 | 2 | 6 | 6 | Six members can receive one partition each. |
| 4 | 2 | 8 | 5 | Up to five members receive partitions; three stay idle. |
| 6 | 1 | 6 | 3 | Up to three members receive partitions; three stay idle. |

With multiple topics under the same subscription, sum all partitions consumed by the group and inspect actual assignments. With differing subscriptions across members, simple division cannot predict precisely which member gets which partition.

If member count in Kafka is lower than expected, check:

- How many pods are truly ready and running the right version.
- Whether listener containers were created and started successfully.
- Actual `concurrency` configured on the listener endpoint.
- Whether `group.id` matches across all replicas meant to share load.
- Whether logs show authentication, broker connection, or subscription errors.
- Whether some replicas run different configs or have endpoints disabled by profile.

If member count exceeds expectations, check rollout surge, lingering old pods, multiple listener endpoints sharing the group, and processes running outside Kubernetes. Cross-reference members with host/client IDs before deleting or restarting instances.

## 5. Checking Assignments in Spring Kafka Logs

Kafka CLI shows what brokers observe. Application logs connect those members to specific listener containers and pods. Enable appropriate logging for Spring Kafka packages during investigations:

```yaml
logging:
  level:
    org.springframework.kafka.listener: INFO
    org.springframework.kafka.core: INFO
```

Adjust log levels by version and environment. DEBUG or TRACE can be verbose, so enable temporarily only when detailed poll, rebalance, or container lifecycle traces are needed.

Spring Kafka also publishes application events for partition assignments and revocations. You can listen for `ConsumerPartitionAssignedEvent` and `ConsumerPartitionRevokedEvent` to log when partitions are granted or revoked:

```java
@Component
public class KafkaAssignmentEvents {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaAssignmentEvents.class);

    @EventListener
    public void onAssigned(ConsumerPartitionAssignedEvent event) {
        log.info("Kafka partitions assigned: container={}, partitions={}",
                event.getContainer(), event.getPartitions());
    }

    @EventListener
    public void onRevoked(ConsumerPartitionRevokedEvent event) {
        log.info("Kafka partitions revoked: container={}, partitions={}",
                event.getContainer(), event.getPartitions());
    }
}
```

These event classes belong to the Spring Kafka listener package; check your running version's API when importing or implementing. Events fire during consumer coordination, so handlers should stay brief and avoid synchronous database or HTTP calls. If forwarding data elsewhere, dispatch a small record to a bounded executor.

Another option is configuring a `ConsumerAwareRebalanceListener` on `ContainerProperties` to observe `onPartitionsAssigned` and `onPartitionsRevoked` callbacks. This helps when logic ties directly to the assignment lifecycle. Whether using application events or rebalance listeners, keep enough fields in logs to correlate container, pod, group ID, and deployment timestamp.

Example log fields to include:

```text
event=partitions_assigned
application=order-service
pod=order-service-7c9f8b9d6f-abc12
group=order-service
partitions=orders-0,orders-1
```

Pod name and group ID usually come from MDC or environment-based logging config. `ConsumerPartitionAssignedEvent` supplies the container and partitions; the application should enrich logs with deployment metadata if searching by pod is needed.

## 6. Distinguishing Assignment from Data Processing Health

Having a partition assignment does not mean a consumer is processing records successfully. Assignment only proves Kafka granted partitions to the member. Next confirm the consumer is polling, the listener is finishing work, offsets are advancing, and lag is not climbing abnormally.

Verify together:

- Group is in a `Stable` state post-deployment.
- Every expected partition appears in the group's assignment.
- No partition is assigned to multiple members in the same group.
- Members map to the expected pods and listener endpoints.
- `CURRENT-OFFSET` advances as new data arrives.
- `LAG` stays steady or drops in line with expected load.
- Logs show no recurring deserialization errors, listener exceptions, commit failures, or poll timeouts.
- Throughput and processing duration metrics align with baselines.

If assignments are valid yet lag climbs, consumers may be slower than producers, partitions may have skewed load, or dependencies may be congested. If assignments are missing, focus on membership, subscriptions, and rebalances first. If offsets do not advance while lag is low, the topic may simply have no new data; confirm via producer logs or log end offsets.

## 7. Checking When a Partition Is Unassigned

A partition missing from assignments can signal an incomplete group rebalance, a subscription omitting that topic, or an inactive group. Check in order:

1. Confirm the topic and partition exist in the queried cluster.
2. Confirm the right group ID and member subscriptions.
3. Wait for any rebalance to finish, then re-run `--state` and `--members --verbose`.
4. Cross-check assignments across all members to spot missing partitions.
5. Inspect consumer logs for subscription, authorization, metadata, or rebalance errors.
6. Check whether the partition was paused by the application or listener container.

A paused partition can still belong to a consumer's assignment. Pausing temporarily stops the container from delivering records from that partition to the listener, without transferring ownership to another member. Distinguish `assigned` from `paused` during observation.

If there are more consumers than partitions, some idle members are normal. Do not restart those members merely to force every pod to own a partition. To enable more members to work in parallel, increase partitions deliberately after evaluating key ordering, existing data, and dependent systems.

## 8. Investigating Post-Deployment Rebalances

Deployments naturally trigger rebalances as new pods join and old pods stop. One rebalance during rollout is normal; repeated rebalances after rollout completion require investigation.

Common causes:

| Cause | Clues to look for |
|---|---|
| Pod restarts or crash loops | Increasing pod restart count, repeated startup/shutdown logs. |
| Consumers failing to call `poll()` on time | Poll timeout logs or `max.poll.interval.ms` breaches; slow listeners or synchronous retries. |
| Lost heartbeats or connectivity | Heartbeat/session timeout logs, broker/network errors. |
| Changed group ID or subscriptions | Members registering different groups or topic subscriptions across replicas. |
| Rolling update creating temporary extra members | Member count rises during rollout then drops as old pods exit. |
| Duplicate static member IDs | Fencing logs or `group.instance.id` collisions. |

Correlate timestamps across Kubernetes events, pod restarts, Spring Kafka assignment/revoke events, and Kafka group state. If the group leaves stable state for only a few seconds during rollout and then settles, that is likely expected behavior. If the group repeatedly drops out of `Stable`, locate what causes members to churn.

With static membership, `group.instance.id` must be unique per member in the same group. If every replica uses the same ID, they can fence one another or cause conflicts. With listener concurrency greater than one, each child consumer also needs a distinct ID if static membership is configured. Verify how your Spring Kafka version generates IDs for child containers.

## 9. Post-Deployment Verification Workflow

Use the following workflow as an operational checklist for `order-service`:

**Step 1 — Verify application version.** Confirm the rollout completed, ready replicas match desired count, and pods run the expected image/tag.

**Step 2 — Verify listener configuration.** Check group ID, topic subscriptions, and actual concurrency. Compute expected members per consumer group.

**Step 3 — Verify group stability.** Run `kafka-consumer-groups --describe --group order-service --state`. If the group is still rebalancing, wait a reasonable interval and check logs before continuing.

**Step 4 — Verify members and assignments.** Run `--members --verbose`, match host/client IDs to pods, and confirm expected partitions are assigned.

**Step 5 — Verify progress.** Run `--describe --group order-service` to inspect committed offsets, log end offsets, and per-partition lag. Re-run after a short interval to confirm offsets advance.

**Step 6 — Verify listener behavior.** Check assignment/revoke logs, listener exceptions, commit failures, poll timeouts, and throughput metrics. Ensure no recurring errors appear once the group stabilizes.

**Step 7 — Save deployment evidence.** Record image/tag, verification timestamp, group ID, member count, assignments, lag, and any remaining warnings. This provides a baseline for future releases.

## 10. Combined Verification Command Examples

For a non-authenticated test cluster, run:

```bash
# 1. Inspect group state
kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --group order-service \
  --state

# 2. Inspect individual consumer members and assignments
kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --group order-service \
  --members \
  --verbose

# 3. Inspect per-partition offsets and lag
kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --group order-service
```

For clusters with SASL or TLS enabled, append `--command-config client.properties` per your environment's security configuration. Never pass passwords or secrets directly in command history; use protected config files per operational policy.

If running checks on Windows, Kafka distributions normally provide corresponding `.bat` scripts, such as `kafka-consumer-groups.bat`. Script names and supported flags vary by Kafka version.

## 11. Common Issues and Remediation

| Symptom | Possible cause | Remediation |
|---|---|---|
| Pod Ready but no members in group | Listener container not started, different group ID, connection failure, or authorization error. | Inspect container logs, group ID, bootstrap servers, and topic/group ACLs. |
| Members present but assignments empty | More members than partitions, mismatched subscriptions, or group in transition. | Check partition count, subscriptions, and group state after rebalance. |
| Member count higher than replicas × concurrency | Rolling update surge, lingering old pods, multiple endpoints, or external processes in same group. | Match host/client IDs against pods and listener endpoints. |
| Partition missing from assignments | Wrong topic subscription, unstable group, or stale partition metadata. | Check topics, subscriptions, group state, and metadata logs. |
| Assignments valid yet lag grows | Slow consumer, hot partition, or congested dependency. | Measure throughput, listener latency, retries, batch size, and per-partition lag. |
| Repeated rebalances after deploy | Pod restarts, poll timeouts, heartbeat failures, or duplicate static member IDs. | Correlate log timestamps, timeout settings, and `group.instance.id`. |
| Consumer member IDs change on every deploy | Consumer IDs are typically ephemeral across restarts. | Use host/client IDs and deployment logs for mapping; do not rely on fixed consumer IDs. |

## 12. Operating Principles

- Check deployment and group state after rollout finishes; do not draw conclusions mid-rebalance.
- Target the right cluster and group ID when running Kafka CLI commands.
- Reconcile replica count, listener concurrency, and actual member count.
- Inspect assignments per member, not merely total consumer count.
- Inspect offsets and lag per partition to confirm consumers are genuinely advancing.
- Use Spring Kafka assignment/revoke logs to map partitions to pods and containers.
- Distinguish valid idle members (when consumers exceed partitions) from subscription or group membership failures.
- Investigate repeated rebalances by correlating timestamps from Kubernetes, the application, and Kafka.
- Do not use consumer ID as a persistent pod identifier; rely on deployment metadata and client/host details.
- Archive post-deployment assignment and lag evidence as a baseline for the next release.

Checking assignments after deployment requires verifying membership, partition distribution, and processing progress together. By combining the Kafka consumer group CLI, Kubernetes state, and Spring Kafka logs, operations teams can see which replica consumes which partitions, catch unexpected idle consumers, and diagnose rebalance causes before service throughput or reliability degrades over time.
