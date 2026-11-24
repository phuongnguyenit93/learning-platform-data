# Runbook: Handling When a Spring Kafka Consumer Fails to Start

## 1. Objective and Scope

This runbook guides incident response when a Spring Boot/Spring Kafka application fails to start its consumer or a listener does not begin receiving messages. The goal is to pinpoint the exact stage where the consumer is stuck, restore operation safely, and preserve Kafka offset state.

In Spring Kafka, it is important to distinguish four states that are commonly grouped under "consumer won't start":

1. **Application fails to start:** Spring `ApplicationContext` fails before the application becomes ready.
2. **Application is running, but the listener is not running:** the listener bean is not registered, the container is stopped, or `autoStartup` configuration prevents the container from starting.
3. **Listener container is running, but has no partitions assigned:** the consumer has not joined the group, is not subscribed to the right topic, or has not completed partition assignment.
4. **Partitions are assigned, but messages are not processed:** the consumer has started; errors occur during polling, deserialization, listener execution, or business processing.

Classifying the state accurately avoids mistreatment. For example, changing `auto.offset.reset` does not fix a DNS error; increasing `concurrency` does not fix an ACL issue; changing `group.id` can create a new consumer group and alter which messages are read.

## 2. Response Principles

- Record the start time, environment, service name, pod/instance, Kafka cluster, topic, consumer group, and recently deployed version.
- Save logs around the failure timestamp before restarting or changing configuration. Preserve the root exception and the entire `Caused by` chain.
- Inspect one instance first. If there are multiple replicas, avoid restarting all of them at once, as that can trigger a rebalance across the entire consumer group.
- Change one factor at a time and record before/after values. Prioritize restoring a configuration known to work.
- Do not arbitrarily change `group.id`, delete the consumer group, reset/seek offsets, delete topics, or toggle auto-commit during investigation.
- Never place passwords, SASL JAAS configs, tokens, private keys, or secret contents into tickets, shared logs, or saved diagnostic commands.

If there is a risk of data loss, duplicate message processing, or multi-service impact, notify the Kafka owner/on-call before performing any operation that could alter offsets, ACLs, or topic data.

## 3. Quick Incident Triage

| Symptom | Likely state | What to check first |
|---|---|---|
| Pod continuously restarts; logs show `Application run failed` or bean creation error | Application fails to start | Root exception, Spring config, beans, and listener container factory |
| Application is Ready but no consumer startup logs appear | Listener not running | `@KafkaListener`, registry, `autoStartup`, profiles, and bean conditions |
| Logs show broker connection, DNS, TLS, or SASL errors | Cannot connect to Kafka | Bootstrap servers, network, TLS/SASL, and mounted secrets |
| Logs show join group/rebalance but no partitions assigned | No assignment yet | Topic/subscription, group, partitions, ACLs, and member status |
| Partition assignment exists but lag does not drop or listener reports errors | Started, error during processing | Deserializer, exception handler, listener code, downstream dependencies, and processing duration |

Do not conclude a consumer is healthy merely because the process is running or the health endpoint returns UP. Confirm that the listener container and consumer group are actually operating.

## 4. Gather Evidence Before Fixing

### 4.1. Confirm Impact Scope

Record the following details:

| Information | Value to record |
|---|---|
| Service and environment | Application name, namespace, environment |
| Failing instance | Pod name, hostname, or instance ID |
| Timing | Last time the consumer processed successfully and time of first failure |
| Kafka | Cluster/bootstrap servers and security protocol (do not record secrets) |
| Subscription | Topic or topic pattern |
| Consumer group | Effective group ID after configuration binding |
| Most recent change | Release, ConfigMap, Secret, certificate, ACL, network policy |
| Impact scope | All replicas or just one replica; one topic or multiple topics |

Compare a failing instance with a healthy instance (if available). Focus on image/version, active profiles, environment variables, secret versions, bootstrap servers, group ID, and topics. Do not dump the full environment if it contains secrets.

### 4.2. Read Logs Over the Right Time Range

Retrieve logs from before startup until after the error appeared. Look for the following message groups:

- `Application run failed`, `BeanCreationException`, `UnsatisfiedDependencyException`: Spring or dependency initialization errors.
- `Failed to start bean` or errors involving `KafkaListenerEndpointRegistry`: listener container startup failure.
- `Bootstrap broker`, `Connection to node`, `disconnected`, `TimeoutException`: broker connectivity or metadata errors.
- `UnknownHostException`, `ConnectException`: DNS or network path issues.
- `SslAuthenticationException`, `SSLHandshakeException`, `SaslAuthenticationException`: TLS/SASL or authentication credential issues.
- `TopicAuthorizationException`, `GroupAuthorizationException`, `ClusterAuthorizationException`: Kafka permission errors.
- `UnknownTopicOrPartitionException`: topic name, metadata, or non-existent topic.
- `SerializationException`, `RecordDeserializationException`: deserialization failure while reading messages.
- `Rebalance`, `Revoking previously assigned partitions`, `Successfully assigned`: group join and assignment status.

These lines are clues to narrow down the issue, not standalone conclusions. Read the first exception and its cause chain; the last error logged is sometimes only a downstream consequence of the initial config error.

For Kubernetes, retrieve logs and pod descriptions using the following read-only commands (replace placeholders with actual names):

```bash
kubectl logs <pod-name> -n <namespace> --since=20m --all-containers=true
kubectl describe pod <pod-name> -n <namespace>
```

Check `Events`, restart status, readiness/liveness probes, image, and volume mounts as well. If the application runs outside Kubernetes, pull logs from the specific process/instance and inspect its restart mechanism.

### 4.3. Check Listener State Inside the Application

If the application is running, inspect listener containers via `KafkaListenerEndpointRegistry`. The snippet below only reads container state; it can be placed in a temporary diagnostic component or used inside a secured internal endpoint.

```java
import lombok.extern.slf4j.Slf4j;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

@Slf4j
@Component
public class KafkaListenerDiagnostics {

    private final KafkaListenerEndpointRegistry registry;

    public KafkaListenerDiagnostics(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void logListenerStates() {
        for (String id : registry.getListenerContainerIds()) {
            MessageListenerContainer container = registry.getListenerContainer(id);
            log.info("Kafka listener id={}, found={}, running={}",
                    id,
                    container != null,
                    container != null && container.isRunning());
        }
    }
}
```

If the registry does not contain the expected listener ID, investigate endpoint registration and bean creation. If the ID is present but `running=false`, check `autoStartup`, programmatic stops from the application, and errors during container start. If `running=true`, proceed to check connectivity, assignments, and polling; that state alone does not prove the consumer has received partitions.

Do not expose diagnostic endpoints to the public Internet, and do not log configuration properties containing credentials.

## 5. Sequential Investigation Procedure

### Step 1 — Confirm Whether the Application Completed Startup

**Symptoms:** process exits, pod restarts, readiness fails, or logs stop during `ApplicationContext` creation.

Check:

1. Find the first exception in startup logs and read the full `Caused by` chain.
2. Confirm the active Spring profile matches the environment.
3. Verify placeholders such as `${KAFKA_BOOTSTRAP_SERVERS}`, `${KAFKA_GROUP_ID}`, and topic names are resolved.
4. Inspect the listener bean, dependency injection, `KafkaListenerContainerFactory`, and deserializer configuration.
5. Compare current ConfigMaps/Secrets/versions against the most recent working deployment.

Common causes:

- Missing environment variable or unresolved placeholder.
- Listener bean or a listener dependency fails to initialize.
- `containerFactory` name in `@KafkaListener` does not match any declared factory bean.
- Invalid deserializer or security configuration causing bean/client initialization to fail.
- Topic configuration is checked at startup and the topic does not exist while missing topics are configured as fatal.

**Recovery:** fix the faulty configuration value or bean; if the failure started after a release/config change, consider rolling back to the last known-good version. Then deploy one instance and confirm `ApplicationContext` finishes starting before expanding the rollout.

### Step 2 — Confirm the Listener Endpoint Is Registered and Allowed to Start

**Symptoms:** the application is Ready, yet the listener ID is absent from the registry or the container is not running.

Inspect the listener declaration and related configuration:

```java
@KafkaListener(
    id = "orders-listener",
    topics = "${app.kafka.orders-topic}",
    groupId = "${app.kafka.orders-group}"
)
public void consume(OrderEvent event) {
    // Process the message
}
```

Verify the following:

- Is the class containing `@KafkaListener` component-scanned and instantiated as a bean?
- Do `@Profile`, `@ConditionalOnProperty`, or feature flags disable the bean in the failing environment?
- Does the application have `@KafkaListener` processing enabled and the correct listener container factory?
- Are `topics`/`topicPattern`, `groupId`, and `containerFactory` resolved properly?
- Is `autoStartup=false` configured on the annotation, container factory, or Spring Boot properties?
- Did operational code call `stop()` on the container after application startup?

Configurations to check typically include:

```yaml
spring:
  kafka:
    listener:
      auto-startup: true
```

`auto-startup` can be overridden by profiles, environment variables, or deployment configurations. Inspect the effective value inside the running process rather than only reading YAML files in the repository. If the listener is intentionally started manually, verify the component responsible for calling `start()` has run.

Note: `id` in `@KafkaListener` is the listener container's ID. If no separate `groupId` is declared, Spring Kafka may use `id` as the group ID depending on the `idIsGroup` setting. Therefore, verify the effective group ID; never infer the group ID solely from the method name or bean name.

**Recovery:** restore bean creation conditions, factory name, topic/group placeholders, or the startup flag to approved values. Start the container again only after confirming the configuration is correct and identifying why the container was stopped.

### Step 3 — Verify Bootstrap Servers and Network Path to Kafka

**Symptoms:** the listener has started, yet logs repeatedly report disconnects, timeouts, or inability to fetch metadata.

Check in order:

1. Does `spring.kafka.bootstrap-servers` point to the correct cluster for the environment; the format must be a `host:port` list.
2. Does DNS for the broker hostnames resolve from the exact pod/container/host running the application?
3. Do network policies, firewalls, security groups, service mesh, or routes allow connections to the brokers?
4. Are the brokers returned in metadata reachable from the runtime? Reaching the bootstrap address does not guarantee reaching every broker in the cluster.
5. Do the port and security protocol match the broker's listener?

Example DNS and TCP checks from the application runtime (if the image includes these utilities):

```bash
getent hosts <broker-host>
nc -vz <broker-host> <broker-port>
```

If `getent` or `nc` is unavailable, use the environment's standardized diagnostic tool. Do not install packages or modify network policies directly in production just to test.

**Recovery:** fix the bootstrap address, DNS, route, or network rule at the owning layer. After the change, verify connectivity from a failing instance and monitor metadata/consumer logs before rolling out the remaining replicas.

### Step 4 — Check TLS, SASL, and Secrets

**Symptoms:** logs show handshake failures, certificate errors, authentication failures, or brokers rejecting connections.

Verify:

- Does `security.protocol` match `SSL`, `SASL_SSL`, `SASL_PLAINTEXT`, or whichever mechanism the cluster requires?
- Do the SASL mechanism and JAAS configuration match the broker configuration?
- Do truststore/keystore have the right file, format, password reference, and read permissions?
- Are certificates unexpired, with valid hostnames/SANs and trust chains?
- Is the secret mounted into the right container and does the secret version match the release?
- Is the system clock accurate for certificate validation?

Never print `sasl.jaas.config` values, passwords, or private keys for comparison. Verify only secret names, versions, paths, file permissions, and certificate metadata/fingerprints per organizational security policy.

**Recovery:** coordinate with the Kafka/identity management team to reissue or mount the correct credentials/certificates. Never disable TLS hostname verification or downgrade the security protocol as an emergency workaround. After a secret is updated, restart the target instance per rollout procedure so the client reloads configuration.

### Step 5 — Verify Topic, Consumer Group, and ACLs

**Symptoms:** broker connection succeeds, yet the consumer does not subscribe, fails to join the group, or the broker returns authorization errors.

Check the exact topic name, including environment prefixes/suffixes. Verify the topic exists and has partitions:

```bash
kafka-topics.sh \
  --bootstrap-server <bootstrap-server> \
  --describe \
  --topic <topic-name>
```

Check the consumer group:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server <bootstrap-server> \
  --describe \
  --group <group-id>
```

The `--describe` output shows consumer members, assigned partitions, current offset, log end offset, and lag (depending on Kafka version). If the group does not exist yet, it may simply mean the consumer has never joined the group; continue correlating logs and listener state.

Check:

- Does the topic in the annotation match the actual topic; if using `topicPattern`, does the regex match the topic name after prefixes are applied?
- Does the topic have partitions and valid metadata?
- Was the consumer group ID altered by a profile, environment variable, or the annotation's `groupId` attribute?
- Is another member in the group holding assignments or repeatedly joining/leaving and causing rebalances?
- Does the application's principal have cluster ACL permissions to read the topic and join the consumer group?
- If the cluster uses ACLs, can the Kafka admin team verify effective permissions for the exact principal, topic, and group?

For authorization errors, distinguish topic permissions from group permissions. Do not grant broad permissions or modify ACLs directly to test; ask the cluster owner team to verify the principal and grant least-privilege permissions through governance channels.

If the topic does not exist yet, determine whether that is a deployment mistake or whether topics are provisioned by a separate process. Create a topic only after confirming its name, partition count, replication factor, and retention configuration with the data owner. If the application sets `missingTopicsFatal=true`, a missing topic will fail container startup; do not disable this check to mask a provisioning bug.

### Step 6 — If the Container Is Running but Has No Partition Assignment

**Symptoms:** the listener container reports running and the consumer can reach brokers, yet the group has no assigned partitions.

Check:

- Is the consumer actually subscribed to the right topic or pattern?
- Does the topic have partitions and can those partitions be assigned?
- Does the group ID match the group being monitored?
- Is continuous rebalancing occurring due to pod restarts, flaky networking, or consumers leaving the group?
- Is `group.instance.id` (if using static membership) duplicated across replicas?
- Is `partition.assignment.strategy` compatible with the configuration and client versions of other members?
- Do ACLs allow the consumer to read both the topic and the group?

A consumer group may have more members than partitions; in that case, some members receive no partitions while the consumer group still operates normally. Compare member count with partition count before concluding there is an error.

**Recovery:** fix the subscription/group or the member configuration causing rebalances. If one instance repeatedly loses connectivity, address that instance first. Do not reflexively raise concurrency: the number of concurrently active consumers is bounded by the number of assignable partitions.

### Step 7 — If Partitions Are Assigned but Messages Are Not Processed

**Symptoms:** the consumer group shows partitions/members, yet lag does not drop, logs show deserialization errors, or the listener fails repeatedly.

Classify further:

- **Deserialization:** inspect key/value deserializers, schemas/types, headers, actual data, and `ErrorHandlingDeserializer` configuration if used. An incompatible message can fail polls or be routed through the error handler depending on configuration.
- **Listener exception:** read exceptions from the handler method, check validation, null handling, and business logic. Determine whether the error handler retries, recovers, seeks, or stops the container.
- **Downstream dependency:** inspect databases, HTTP services, locks, or connection pools required by the listener. The consumer may be blocked waiting on a dependency rather than failing to start.
- **Poll interval:** processing a batch for too long can exceed `max.poll.interval.ms`, causing the consumer to leave the group and rebalance. Measure processing duration and check rebalance logs before adjusting timeouts.
- **Concurrency and partitions:** verify partition count, member count, and actual throughput; more threads do not create more assigned partitions.

Do not set infinite retries or swallow exceptions just to make lag drop on dashboards. Before changing retry/DLT/error handler settings, confirm the policy for failed messages, duplicate-processing safety, and data retention requirements.

## 6. Frequently Misunderstood Configurations

| Configuration | Effect | What it cannot fix |
|---|---|---|
| `spring.kafka.bootstrap-servers` | Bootstrap address for clients to fetch Kafka metadata | Wrong ACLs, wrong topic, or disabled listener |
| `spring.kafka.consumer.group-id` | Default consumer group ID | Does not prevent annotations from overriding group ID |
| `@KafkaListener(groupId = "...")` | Group ID applied to that listener | Is not the container ID |
| `@KafkaListener(id = "...")` | Listener container identifier; may be used as group ID per `idIsGroup` if `groupId` is omitted | Does not prove the listener is running |
| `spring.kafka.listener.auto-startup` / `autoStartup` | Enables or prevents automatic listener container startup | Does not fix connectivity, authentication, or missing topics |
| `spring.kafka.consumer.auto-offset-reset` | Chooses starting position when the group has no valid offset | Does not reset committed offsets; does not fix startup/connection errors |
| `spring.kafka.listener.concurrency` | Number of consumer threads/containers for the listener | Does not create extra partitions and does not fix rebalances on its own |
| `max.poll.interval.ms` | Limits time between polls per Kafka consumer mechanics | Should not be increased before measuring processing time and finding the root cause |

In particular, `auto.offset.reset=earliest` or `latest` only takes effect when no valid committed offset exists. `earliest` can cause the consumer to re-read all data still within retention; `latest` can skip pre-existing data when a group starts fresh. Never use this change as a routine consumer restart step.

Changing `group.id` creates a different consumer group. The new group has its own offsets and will follow `auto.offset.reset`; this can re-read or skip data compared to the old group. Do this only with an explicit decision on data semantics and a rollback plan.

## 7. Safe Recovery Sequence

1. Identify the specific root cause from logs, container state, and broker/topic/group inspection results.
2. Record the current configuration and identify the owning layer for the fix: application, deployment platform, network, security, or Kafka.
3. Choose the smallest change capable of resolving the root cause; change only one configuration group at a time.
4. If a release or config fix is needed, use the standard deploy/rollback process. Do not edit running pods directly unless the change is persisted in the canonical config source.
5. Deploy or restart a single instance. Confirm the application is Ready, the listener container is running, and the consumer joins the group and receives partition assignments.
6. Observe logs, consumer group status, and lag long enough to verify the consumer is polling and processing messages.
7. Once the canary instance is stable, roll out the remaining replicas in stages.
8. If errors return, halt the rollout, capture fresh evidence, and roll back the change per procedure.

Do not delete offsets or reset the group to make a consumer "run again." If a business replay is required, create a separate plan: define partition/offset ranges, estimate data volume, assess idempotency, and obtain data owner approval.

## 8. Recovery Verification Criteria

Close the incident only when all conditions applicable to the system are confirmed:

- The application starts stably and meets readiness checks.
- The expected listener ID is present in the registry and the container is running.
- The consumer connects to brokers, joins the right group, and receives expected partition assignments.
- `kafka-consumer-groups --describe` shows sensible members/assignments; lag decreases when the topic has new data and the consumer can keep up.
- No recurring DNS, connection, TLS/SASL, authorization, or deserialization errors remain.
- Application logs or business metrics confirm messages are being processed successfully.
- Other replicas remain healthy; no rebalance loops or restart loops follow the rollout.
- No unplanned changes were made to group IDs, offsets, topics, ACLs, or security protocols.

If the topic has no new messages and lag is 0, unchanging lag cannot be used to conclude the consumer is hung. Confirm partition assignment and at least one successful poll/heartbeat via available logs or metrics.

## 9. Information to Send When Escalating

When escalating to the Kafka, platform, or security team, send a concise bundle containing:

1. Service, environment, pod/instance, and failure timestamps (with timezone).
2. Topic, effective group ID, Kafka cluster, and application/client versions.
3. Status of `ApplicationContext`, listener registry/containers, and consumer group.
4. Relevant startup logs, root exception with `Caused by` chain; scrubbed of secrets and sensitive data.
5. Output of `kafka-topics --describe` and `kafka-consumer-groups --describe` if permitted to run.
6. DNS/TCP/TLS/SASL test results relevant to the error.
7. Most recent changes, steps already tried, outcomes of each step, and rollback status.
8. Impact scope: affected replicas, topics/partitions, lag or outage duration, and business impact.

Ask the receiving team to clearly confirm the failing layer (application, network, authentication, ACL, topic/group, or message processing), next action, owner, and completion criteria.

## 10. Quick Action Checklist

- [ ] Determine whether the application finished starting.
- [ ] Save startup logs and the root exception before restarting.
- [ ] Confirm the listener ID is in `KafkaListenerEndpointRegistry` and the container is running.
- [ ] Check effective `autoStartup`, active profiles, topic, group ID, and container factory.
- [ ] Check bootstrap servers, DNS, TCP, and broker metadata reachability.
- [ ] Check TLS/SASL, certificates, and secrets without exposing credentials.
- [ ] Check topics, partitions, consumer group, assignments, and ACLs.
- [ ] If partitions are assigned, check deserialization, listener exceptions, downstream dependencies, and poll intervals.
- [ ] Recover with one controlled change on a single instance first.
- [ ] Confirm assignments, message processing, and lag before rolling out the rest.
- [ ] Document root cause, changes, outcomes, and any data/offset impact.
