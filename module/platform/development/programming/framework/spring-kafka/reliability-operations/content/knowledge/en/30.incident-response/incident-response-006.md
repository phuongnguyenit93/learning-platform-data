# Runbook When a Consumer Is Fenced

## Purpose and Scope

This runbook guides investigation and recovery when a Kafka consumer using Spring for Apache Kafka is fenced, especially `FencedInstanceIdException` errors related to static membership. Fencing is an ownership protection mechanism: when Kafka determines an old instance is no longer a valid member, that instance is blocked from continuing to operate under an identity already claimed by another instance.

In Spring Kafka operations, the phrase "consumer is fenced" is commonly used when two consumers share the same `group.instance.id`. When a new consumer registers with the same static member ID, the coordinator can fence the old consumer. However, application logs may also contain fencing errors from a transactional producer, such as `ProducerFencedException`. The two cases have different causes and fixes; you must identify the specific exception before changing configuration.

This runbook applies to Spring Kafka applications running on VMs, containers, or Kubernetes, including standard listener containers and consume-process-produce applications with transactions. Configuration and events may vary by Kafka client, broker, Spring Kafka, and group protocol versions. Always cross-check against your actual versions before applying examples.

## Understanding Types of Fencing Properly

### Consumer Fenced Due to Duplicate Static Member ID

Kafka supports static membership via `group.instance.id`. This value stably identifies a consumer group member across restarts. When another consumer joins the group with the same `group.instance.id`, the coordinator can accept only one member for that identity. The old member can be fenced and receive `FencedInstanceIdException`.

Common scenarios:

- Two pods receive the same `group.instance.id` because a literal value is configured across all replicas.
- Two processes run concurrently during a rollout, failover, or manual restart while sharing the same static member ID.
- A stateful workload recreates a pod with the old identity while the old process is still alive or has not yet left the group.
- Multiple listener child containers share the same ID because static membership configuration does not account for `concurrency` or how Spring Kafka generates IDs for child containers.
- Two environments or two applications accidentally share the same `group.id` and `group.instance.id`.

With static membership, a consumer can keep its place in the group for the duration of the session timeout during a brief disconnect. This reduces rebalances on short restarts, but requires each logical member to have a unique ID and a clearly managed lifecycle.

### Transactional Producer Fenced in a Consume-Process-Produce Flow

An application may consume a record, process it, and publish results within a Kafka transaction. In that case, `ProducerFencedException` typically indicates an older transactional producer was replaced by another producer with the same `transactional.id`, or the producer is using a stale epoch.

Common causes:

- Multiple application instances share the same `transactional.id` or the same `transactionIdPrefix` without a unique suffix.
- Two producers attempt to own the same transactional ID after a rollout, failover, or duplicate process launch.
- An old transactional producer continues sending/committing after a new producer has initialized with the same identity.

Producer fencing errors are not fixed by changing `group.instance.id`. Check `transactional.id`, `spring.kafka.producer.transaction-id-prefix`, and how suffixes are assigned to each producer instance.

### Easily Confused Errors

| Log symptom | Meaning to investigate |
|---|---|
| `FencedInstanceIdException` | The consumer's static member ID has been claimed by another member in the same group |
| `ProducerFencedException` | The transactional producer ID/epoch has been superseded by a newer producer |
| `CommitFailedException` | Commit is no longer valid, usually because the consumer no longer owns the partition or the group changed; trace the preceding cause |
| `RebalanceInProgressException` | Group is rebalancing; by itself this does not prove a duplicate static member ID |
| `Commit cannot be completed since the group has already rebalanced` | Commit arrived after group generation changed; correlate poll interval, rebalances, and processing duration |

Do not conclude fencing occurred from a single rebalance or failed commit message alone. Identify the root exception and the associated member/client IDs.

## Symptoms and Impact

Possible symptoms:

- Consumer logs show `FencedInstanceIdException`, messages about a fenced static member ID, or an invalid member instance.
- The listener container stops or the consumer stops polling after a fencing error; exact behavior and emitted events depend on the Spring Kafka version.
- One pod logs being fenced while another pod with the same identity continues consuming.
- Group members/assignments change near deployments, pod restarts, scaling, or failovers.
- Lag increases because a member stopped, partitions had to be reassigned, or the consumer group had to restabilize.
- With transactional producer fencing, logs show `ProducerFencedException`, transaction aborts, or transaction commit failures.

Fencing prevents two processes from continuing to operate under an identity that Kafka requires to be unique. Do not try to defeat fencing by restarting repeatedly. If duplicate ownership still exists, the new instance may keep fencing the old one and the incident will repeat.

## Handling Principles

1. Capture the root exception and distinguish consumer fencing from transactional producer fencing.
2. Identify the cluster, `group.id`, `group.instance.id`, `client.id`, pod/host, and timestamps for each member.
3. Inspect all replicas and child containers in the same group before restarting. A single restart can mask duplicate ownership without removing the duplicate configuration.
4. Ensure unique consumer or transactional producer identities across the scope Kafka requires.
5. Do not reset offsets, delete the group, increase concurrency, or change group ID as a quick fix without assessing data processing impact.
6. Record old configurations and change only one root cause per intervention.

## Incident Response Procedure

### 1. Confirm Exception and Scope

Collect the following information before intervening:

| Information | What to determine |
|---|---|
| Cluster and environment | Production/staging, bootstrap servers, namespace, or host |
| Consumer group | Exact `group.id` and list of topic subscriptions |
| Exception | Full class, stack trace, and first message at the time of failure |
| Consumer identity | `group.instance.id`, `client.id`, consumer ID, pod/host, and process start time |
| Listener | `@KafkaListener` ID, container factory, concurrency, and replica count |
| Transaction | Whether Kafka transactions/EOS are used; what `transactional.id` or `transactionIdPrefix` is set |
| Most recent change | Deployment, scale, restart, failover, configuration change, or node replacement |
| Impact | Which consumers stopped, lag, throughput, commit errors, and business impact |

Read the root exception in logs, not just the final container log line. If the stack trace goes through `KafkaConsumer.poll()` and shows `FencedInstanceIdException`, follow the consumer static membership branch. If the error occurs while sending/committing a transaction and shows `ProducerFencedException`, jump to the transactional producer branch in step 5.

### 2. Inspect the Consumer Group and Running Members

From a host with Kafka CLI and cluster access, capture group state:

```bash
export BOOTSTRAP_SERVERS="broker-1:9092,broker-2:9092"
export GROUP_ID="orders-consumer-v1"

kafka-consumer-groups.sh \
  --bootstrap-server "$BOOTSTRAP_SERVERS" \
  --describe \
  --group "$GROUP_ID" \
  --state

kafka-consumer-groups.sh \
  --bootstrap-server "$BOOTSTRAP_SERVERS" \
  --describe \
  --group "$GROUP_ID" \
  --members \
  --verbose
```

Depending on Kafka version, `--state`, `--members`, and `--verbose` options may differ. If the CLI does not support them, use the basic `--describe --group` command and inspect member details in broker logs or corresponding admin tools.

Correlate results with logs from each pod/process:

- How many processes are running with the same `group.instance.id`?
- Are two pods/hosts declaring the same static member ID at the same time?
- Which consumer got fenced and which consumer retains that identity?
- Did a new member appear right after a deployment or restart?
- Is one `group.id` unexpectedly shared across multiple services or environments?
- Does the actual consumer count match `replica count × listener concurrency`?

Member details in the CLI may not display the full `group.instance.id` directly depending on version and output format. Use client logs/rendered configuration to verify the value. Do not infer IDs from `client.id` without confirming how the application generates them.

Snapshot group state multiple times to see which members appear or vanish. Record timestamps and timezone to correlate rollouts, orchestrator events, and broker logs.

### 3. Inspect How `group.instance.id` Is Assigned

Locate every place where consumer properties are configured:

- `spring.kafka.consumer.properties` in YAML/properties.
- `ConsumerConfig.GROUP_INSTANCE_ID_CONFIG` in `ConsumerFactory` config.
- Manually declared `DefaultKafkaConsumerFactory` or `ConcurrentKafkaListenerContainerFactory`.
- Environment variables, ConfigMaps, Secrets, Helm values, or JVM arguments.
- Dynamically generated config based on hostname, pod name, StatefulSet ordinal, or application instance ID.

Ensure every member in the same group has its own `group.instance.id`. Using the same literal value for all replicas is a misconfiguration. The ID should remain stable for the same logical member when static membership is needed, while never being assigned to two concurrently running processes.

Example Spring Boot configuration for one consumer member per pod:

```yaml
spring:
  kafka:
    consumer:
      group-id: orders-consumer-v1
      properties:
        "[group.instance.id]": "orders-${HOSTNAME}"
```

The example above is safe only when `HOSTNAME` truly differs across pods/members and is injected into the application as expected. With a Kubernetes StatefulSet, the hostname usually ties to the pod ordinal, enabling stable identity across restarts of the same ordinal. With a Deployment, new pods typically get new names; hostname-based IDs remain unique, but do not preserve static identity across pod replacements. Choose the strategy matching your operational goals and deployment model.

If the listener container uses `concurrency > 1`, ensure each child consumer gets a unique ID. Some Spring Kafka versions automatically append a suffix to `group.instance.id` for child containers of `ConcurrentMessageListenerContainer`; verify the behavior of your exact running version and check the final value in Kafka client logs. Do not append your own suffix alongside the framework's mechanism if doing so produces inconsistent IDs.

### 4. Resolve Duplicate Static Member IDs

Once you identify two processes using the same `group.instance.id`:

1. Determine which process is the intended owner based on replica, StatefulSet ordinal, or instance allocation rules.
2. Confirm whether the old process has completely stopped or is eligible to be replaced. Check pod/process state, termination grace period, and node/network partitions.
3. Fix the configuration source so each member receives a unique ID. Do not patch only one pod's runtime if ConfigMaps/Helm values or environment variables will recreate duplicate IDs on the next rollout.
4. If a logical member is restarted, allow only one process to own that ID at a time. Ensure the orchestrator is not unintentionally running two pods with the same ordinal/identity in parallel.
5. Perform a controlled restart or rollout after fixing the configuration. Watch logs to confirm `FencedInstanceIdException` does not recur.
6. Confirm the group returns to `Stable`, partitions are assigned properly, and lag begins recovering.

If static membership is unnecessary or stable/unique IDs cannot be guaranteed, consider removing `group.instance.id` to use dynamic membership. Kafka will assign member identities dynamically; members joining/leaving may still cause rebalances, but duplicate static IDs of this type will be eliminated. Switching requires a coordinated rollout and assessment of rebalance impact.

Do not simply increase `session.timeout.ms` to fix duplicate IDs. A longer timeout only extends how long the coordinator retains an old member after disconnect; it does not make two processes sharing the same ID valid.

### 5. If the Error Is `ProducerFencedException`

Take this branch when the stack trace shows a transactional producer was fenced. Check:

- Whether the application enables transactions via `spring.kafka.producer.transaction-id-prefix`, `KafkaTransactionManager`, `KafkaTemplate.executeInTransaction`, or EOS settings.
- Whether pods/replicas share the same `transactionIdPrefix`.
- Whether each producer instance has a unique transactional ID/suffix.
- Whether an old producer continues operating after a new instance initialized with the same transactional ID.
- Whether multiple application deployments share the same prefix on the same cluster.

Example per-instance prefix configuration:

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: "orders-${HOSTNAME}-"
```

The prefix must be unique across application instances running transactional producers concurrently. Spring Kafka uses the prefix to generate transactional IDs for producers; verify the suffixing and caching behavior of your exact version. Do not configure an identical literal prefix for all replicas if instances can create producers simultaneously.

After fixing:

1. Confirm no two instances share a transactional ID.
2. Stop or remove the stale producer instance per deployment procedures.
3. Instantiate a new producer with a valid prefix/ID.
4. Monitor transaction begin/send/commit errors, transaction aborts, and fencing logs.
5. Inspect both publish results and consumer offsets to confirm the consume-process-produce flow remains consistent.

Do not change `group.instance.id` to cure `ProducerFencedException`. Those two identities belong to separate mechanisms.

### 6. Check Rollout and Orchestration

If fencing coincides with deployments or scaling, check:

- Whether rolling updates allow old and new pods to run simultaneously with the same identity.
- Whether `maxSurge`, `maxUnavailable`, termination grace period, and `preStop` hooks are appropriate.
- Whether the application closes listener containers and Kafka clients cleanly upon receiving `SIGTERM`.
- Whether a node partition or hung pod prevents the orchestrator from confirming the old process terminated.
- Whether StatefulSet ordinals, volume identities, hostnames, and static member configs are consistent.
- Whether an autoscaler creates more replicas than expected or oscillates continuously.

With static membership, design rollouts so two processes cannot receive the same `group.instance.id` simultaneously. You may need to adjust the rollout strategy or limit surge for that workload. Only use `maxSurge: 0` or a specific policy after evaluating availability requirements and member shutdown capability; it is not a universal setting for every application.

If the system needs to replace a member quickly while an old process might still be alive due to a network partition, fencing the old instance is the intended protective behavior. Fix why the old process failed to stop or lose access, then confirm the new instance is the sole owner.

## Configuration and Operational Decisions

### When to Use Static Membership

Static membership is useful when members have stable identities and experience frequent short restarts, such as workloads with fixed ordinals. It can avoid rebalances during brief restarts when the member returns before the session timeout expires.

Enable it only when all conditions are met:

- Every logical member has a unique ID within the group scope.
- The ID remains stable across restarts of the same logical member.
- The orchestrator prevents two processes from concurrently using the same ID outside intentional failover scenarios.
- Clear rollout, shutdown, and member replacement procedures exist.
- The operations team understands that an old member may be held in the group until its session timeout expires.

If these conditions cannot be guaranteed, dynamic membership is usually simpler and easier to operate.

### When to Review Session Timeout

`session.timeout.ms` controls how long the coordinator waits for member heartbeats in the classic group protocol. For static members, this timeout also affects how long an old member is retained after a temporary disconnect. Adjust this value only after reviewing:

- Application restart and startup duration.
- Network latency, heartbeats, and JVM pauses.
- Acceptable failover duration for the system.
- Broker-side min/max session timeout limits.
- Group protocol and Kafka client/broker versions.

Values too large can make the group wait too long when a member genuinely dies; values too small can evict members during brief interruptions. With newer group protocols, heartbeat/session management may differ from the classic protocol; verify documentation for your exact version before configuring.

## Post-Mitigation Verification

Monitor through at least one restart/rollout cycle or long enough to cover the scenario that triggered the failure. Verify:

- No more `FencedInstanceIdException` or `ProducerFencedException` corresponding to the resolved issue.
- Every active `group.instance.id` is unique within the consumer group.
- If using transactions, transactional IDs/prefixes are uniquely assigned per application instance.
- The consumer group remains `Stable`; member counts and partition assignments match expected replicas/concurrency.
- Listener containers continue polling and processing records without unexpected stops after fencing.
- Consumer lag decreases or stabilizes at an acceptable level; throughput and latency recover.
- No abnormal commit errors or transaction aborts occur.
- Business outcomes and output data are consistent; any record reprocessing causes no unintended duplicate side effects.
- A test restart or rollout does not generate duplicate identities.

Record the final identity configuration, how IDs are generated per pod/child container, replica/concurrency counts, Kafka/Spring Kafka versions, rollout timestamps, and before/after metrics. Retain initial fencing logs along with recovery verification evidence.

## When to Escalate

Escalate to the Kafka/platform team when:

- `FencedInstanceIdException` keeps recurring even though the application confirms unique IDs and only one process per logical member.
- Multiple consumer groups or services experience abnormal fencing simultaneously.
- Brokers/coordinators report errors related to group membership, sessions, or coordinator failover.
- The member holding a static identity cannot be identified due to a network partition or unreachable node.
- Changes are needed to group protocol, broker-level timeouts, transactional topology, or shared rollout policies.

Escalate to the application team when:

- `ProducerFencedException` stems from duplicate `transactional.id`/`transactionIdPrefix` across instances.
- Spring Boot, `ConsumerFactory`, listener container factory, or producer factory configuration generates incorrect identities.
- Containers stop or fail to restart according to expected behavior after fencing.

When escalating, attach cluster/environment, group ID, topic, full exception, timestamps and timezone, Kafka broker/client versions, Spring Kafka version, group protocol, `group.instance.id`, `client.id`, transactional ID/prefix (if any), pod/host/process start times, replicas/concurrency, group state, consumer/coordinator logs, and recent deployment changes. Redact sensitive information from logs/configs before sharing.

## Quick Action Checklist

- [ ] Capture the root exception and distinguish `FencedInstanceIdException` from `ProducerFencedException`.
- [ ] Record cluster, group ID, topic, client ID, pod/host, and timestamps.
- [ ] Snapshot group state, members, assignments, and lag.
- [ ] Locate every `group.instance.id` configuration in the application, container factories, and deployment environment.
- [ ] Confirm no two processes/child containers use the same static member ID.
- [ ] Check rollouts, restarts, StatefulSet/Deployment, autoscaling, and shutdown lifecycle.
- [ ] If producer fencing, verify `transactional.id`/`transactionIdPrefix` is unique across instances.
- [ ] Fix the identity configuration source, then perform a controlled rollout.
- [ ] Confirm group stability, resumed container polling, lag recovery, and accurate transactions/offsets.
- [ ] Document configurations, before/after evidence, and escalate if fencing recurs.
