# Checking Configuration Drift in Spring Kafka Reliability Operations

## 1. What Is Configuration Drift and Why Check It?

**Configuration drift** occurs when the effective configuration running in a system **diverges from the approved baseline**, or when two instances expected to behave identically run with different settings. In a Spring Kafka application, drift can creep in through config files, environment variables, Kubernetes ConfigMaps/Secrets, Helm values, custom code, Spring profiles, Kafka brokers, Kafka topics, or ACLs.

Consider an order-processing system designed to write events only when producers enforce matching durability guarantees:

~~~text
Approved configuration (baseline)
  producer.acks = all
  producer.enable.idempotence = true
  consumer.enable.auto.commit = false
  consumer.isolation.level = read_committed
  topic orders.events min.insync.replicas = 2

                    |
               Deployment
                    |
                    v
Runtime at Pod A                      Runtime at Pod B
  acks=all                            acks=1
  enable.idempotence=true             enable.idempotence=false
  enable.auto.commit=false            enable.auto.commit=true
  isolation.level=read_committed      isolation.level=read_uncommitted
~~~

Pod B may still run and send/receive messages, yet its **reliability contract** has changed. Watching throughput and HTTP health checks alone can miss the risk of lost events, mistimed offset commits, or reading uncommitted records.

Within **Spring Kafka Reliability Operations → Deployment and Configuration**, this lesson covers:

1. Defining **desired** configuration vs. **actual** configuration.
2. Separating drift across application, Kafka client, listener, topic, broker, and infrastructure layers.
3. Checking settings that directly govern delivery, ordering, retries, transactions, and replay.
4. Building **safe** config snapshots without exposing secrets.
5. Integrating drift detection into CI/CD, startup, scheduled scans, and alerting.
6. Establishing how to remediate drift without causing outages or corrupting consumer offsets.
7. Testing drift detectors and verifying real behavior after rollouts.

**Different configuration is not automatically a bug.** Staging often runs one broker while production runs many; timeouts, concurrency, and topic retention legitimately vary by environment. Drift is confirmed only against a **baseline approved for that specific environment, service, cluster, and version**.

## 2. Sources of Truth That Must Be Distinguished

A foundational reality is that **Git config does not equal runtime config**, and what `Spring Environment` sees does not always match what the Kafka client actually uses.

~~~text
1. Approved baseline
   Git / GitOps / Policy repository
            |
            v
2. Deployed configuration
   Helm rendered manifests / ConfigMap / Env / Secrets
            |
            v
3. Effective runtime configuration
   Spring Environment -> Kafka factories -> Kafka clients
            |
            v
4. Kafka cluster effective configuration
   Broker / Topic / ACL / Quotas / Replication / ISR
~~~

Essential comparisons:

| Comparison | What It Detects |
|---|---|
| Baseline ↔ Git deployment manifests | Unapproved pull requests altering configs |
| Git desired ↔ Kubernetes live resources | Manual edits via `kubectl`, admission controllers, or operators |
| Deployed env/config ↔ `Spring Environment` | Profile, CLI argument, env override, or property precedence surprises |
| `Spring Environment` ↔ Kafka `Producer`/`ConsumerFactory` | Customizers or Java code overriding properties |
| Client factory ↔ Live Kafka client | Kafka client defaults, runtime updates, or external configs |
| Broker/topic baseline ↔ `AdminClient` observations | Altered topic retention, min ISR, partition count, cleanup policy, or quotas |
| Pod A ↔ Pod B in the same release | Incomplete rolling updates, stale pods, mismatched env/secret revisions |

**Never diff `application.yml` alone and declare the system drift-free.** That misses someone increasing topic partitions directly on Kafka or an old pod running a different profile.

### Example of Drift That Causes No Immediate Error

A consumer is designed to process orders via an idempotent listener and explicit acknowledgment. A rollout flips **`enable.auto.commit`** to `true`. The app still consumes and processes records, yet offsets risk committing unexpectedly if the container actually honors that setting. The regression surfaces only when a process crashes mid-processing.

Drift detection therefore **prevents reliability degradation before incidents occur**, rather than merely aiding post-mortems.

## 3. Configuration Scopes to Bring Under Control

### 3.1. Kafka Producer

Settings commonly impacting reliability:

| Kafka Client Property | Meaning | What to Check |
|---|---|---|
| **`acks`** | Broker write acknowledgment level | Does baseline require `all` or another level? |
| **`enable.idempotence`** | Reduces duplicates from producer retries per Kafka semantics | Is it enabled with compatible configs? |
| **`retries`** | Producer-layer retry attempts | Aligns with delivery timeout and policy? |
| **`delivery.timeout.ms`** | Upper time bound for completing delivery | Not smaller than needed request/linger window? |
| **`request.timeout.ms`** | Timeout waiting for broker response | Fits latency and SLAs? |
| **`linger.ms`** | Batching wait before sending | No unintended latency/throughput shift? |
| **`batch.size`** | Per-partition send batch buffer | No unexpected memory growth? |
| **`max.in.flight.requests.per.connection`** | Unacknowledged requests per connection | Matches idempotence/ordering constraints? |
| **`compression.type`** | Batch compression | No surprising CPU or size changes? |
| **`transactional.id`** | Transactional producer identity | No collisions across active instances? |
| **`transaction.timeout.ms`** | Transaction duration limit | Fits processing time and broker policy? |
| **`key.serializer`/`value.serializer`** | Record serialization format | No unintended data contract changes? |

In modern Kafka producers, enabling idempotence imposes constraints such as **`acks=all`**, **`retries > 0`**, and **`max.in.flight.requests.per.connection` within supported bounds**. Never "fix drift" by flipping a single option without checking compatibility across the entire producer config.

**`acks=all`** must be evaluated alongside **replication factor, `min.insync.replicas`, and ISR health**. On a single-replica topic, `acks=all` does not deliver multi-replica durability.

### 3.2. Kafka Consumer

| Property | Risk When Drifting |
|---|---|
| **`group.id`** | Consumer joins another group, replaying or splitting workloads differently |
| **`enable.auto.commit`** | Offsets commit outside intended application semantics |
| **`auto.offset.reset`** | When a group lacks an offset, it may start at `earliest` or `latest` unexpectedly |
| **`isolation.level`** | `read_uncommitted` exposes uncommitted or aborted transactional records |
| **`max.poll.records`** | Records per poll exceed processing capacity |
| **`max.poll.interval.ms`** | Consumer appears stalled between polls, triggering rebalances |
| **`session.timeout.ms` / `heartbeat.interval.ms`** | Group liveness and failover timing alter unexpectedly |
| **`fetch.min.bytes` / `fetch.max.wait.ms`** | Changes latency/throughput characteristics |
| **`key.deserializer`/`value.deserializer`** | Breaks schema compatibility or decodes wrong types |
| **`allow.auto.create.topics`** | Client accidentally triggers topic creation depending on broker config |

**`auto.offset.reset`** does not reset a consumer group that already holds committed offsets. It governs position only when no valid offset exists under Kafka client rules. Thus drift on this property stays invisible day-to-day and strikes when a new group is created or offsets expire.

### 3.3. Spring Kafka Listener Container

Kafka consumer config is only one layer. Spring Kafka also governs:

- **`AckMode`**: `RECORD`, `BATCH`, `MANUAL`, `MANUAL_IMMEDIATE`, or container-specific modes.
- **`concurrency`**: number of consumer/container threads.
- **`pollTimeout`** and polling settings.
- **`CommonErrorHandler`**, `DefaultErrorHandler`, retries/backoff, and recoverers.
- **`DeadLetterPublishingRecoverer`** and DLT destinations.
- **`KafkaAwareTransactionManager`** for transactional listeners.
- **`AfterRollbackProcessor`** for transactional listeners.
- **`RecordFilterStrategy`** and batch listener mode.
- **Container pause/resume** and authentication retry intervals.

Drift in listener Java configuration often **never shows up as a simple Kafka client key**. Changing retries from 3 to infinite or swapping the DLT topic can stall a job on poison messages even when `application.yml` is untouched.

### 3.4. Broker, Topic, and Security

| Group | What to Observe |
|---|---|
| Topic | Existence, partitions, replication factor, `cleanup.policy`, `retention.ms`/`bytes` |
| Durability | `min.insync.replicas`, ISR, leader availability, under-replicated partitions |
| Transactions | `transaction.state.log.replication.factor`, `transaction.state.log.min.isr`, `transaction.max.timeout.ms` |
| Group offsets | `offsets.topic.replication.factor` and cluster metadata durability |
| Access | ACL principals/resources/operations, authentication mechanisms |
| Transport | `security.protocol`, TLS/SASL settings, certificate rotation |
| Quotas | Producer/consumer bandwidth and request quotas that can cause timeouts |
| Client/server compatibility | Kafka broker/client versions, protocol behavior |

Some parameters are **broker-level**, some **topic-level**, and some inherit broker defaults. `AdminClient` returns effective configs and config sources depending on Kafka version and permissions; commands showing only **dynamic overrides** can miss critical defaults.

## 4. Creating a Versioned, Scoped Baseline

A solid baseline needs an **identity** so operators know which policy they are comparing against:

~~~yaml
policyVersion: kafka-reliability-v4
service: orders-worker
environment: production
clusterAlias: kafka-prod-a
releaseChannel: stable

producer:
  acks: all
  enable.idempotence: true
  max.in.flight.requests.per.connection: 5

consumer:
  enable.auto.commit: false
  isolation.level: read_committed
  auto.offset.reset: earliest

listener:
  ackMode: BATCH
  concurrency: 3
  retryAttempts: 3
  dltTopic: orders.events.dlt

topics:
  orders.events:
    partitions: 6
    replicationFactor: 3
    min.insync.replicas: 2
    cleanup.policy: delete
~~~

This is an **illustrative policy manifest**, not syntax understood automatically by Spring Boot. A dedicated drift detector or CI step reads and compares this manifest against runtime observations.

The production values above are examples only. On a single-broker staging cluster, another baseline might use replication factor 1 and min ISR 1 for test goals. Never enforce a production policy verbatim on a test environment with a different topology.

Baselines should be:

1. Versioned in Git or an audited policy store.
2. Bound to an approved service, cluster, environment, and release.
3. Code-reviewed, especially for reliability-sensitive changes.
4. Annotated with rationale for time-bounded exceptions.
5. Free of raw secret values.
6. Typed with clear schemas for numbers, booleans, durations, and lists.

### Separate Policy from Observation

If the same script derives the baseline from **the effective runtime config itself** and compares runtime to that copy, the detector always reports PASS even after unauthorized edits. Expected sources must be independent and reviewed.

Never treat "whatever Kafka's current default is" as a valid baseline when a service previously relied on another version's default. For critical reliability settings, **explicit configuration** is far easier to govern than library defaults.

## 5. Understanding Spring Boot Property Precedence

An application might declare:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        "[enable.idempotence]": true
    consumer:
      enable-auto-commit: false
      properties:
        "[isolation.level]": read_committed
~~~

Yet deployment may inject environment variables or command-line args overriding several values:

~~~text
SPRING_KAFKA_PRODUCER_ACKS=1
SPRING_KAFKA_CONSUMER_ENABLE_AUTO_COMMIT=true
~~~

Now `application.yml` inside the image still looks "right," while runtime differs. Spring Boot resolves a precedence chain of `PropertySource`s (application files, environment variables, system properties, command-line arguments, config imports, etc.), and final precedence depends on Boot version, bootstrap style, and config layout.

To detect this, inspect the **effective `Spring Environment`** and, better yet, the **`ProducerFactory`/`ConsumerFactory` configuration maps** after customizers execute.

### Where Overrides Can Happen

- `application.yml` and `application-{profile}.yml`.
- `SPRING_PROFILES_ACTIVE` or profile flags passed via launch arguments.
- Environment variables from Deployment/Pod/ConfigMap/Secret.
- Spring Cloud Config or config imports when enabled.
- JVM system properties and command-line arguments.
- Java `@Configuration` creating custom `ProducerFactory`, `ConsumerFactory`, or `ListenerContainerFactory` beans.
- `BeanPostProcessor`s or customizers mutating properties.
- Kafka client defaults changing across library upgrades.
- Dynamic broker/topic configs modified outside the app.

A pod may also hold an outdated ConfigMap even after Git updates. **File-mounted ConfigMaps** and **env-injected ConfigMaps** update differently: a running process's env vars do not refresh when a ConfigMap is edited. Never assume every config drift resolves from a single ConfigMap patch.

## 6. Safely Collecting Effective Configuration

Three observation levels exist in an application:

**Level 1 — `Spring Environment`:** verifies resolved properties.

**Level 2 — Kafka factories:** verifies producer/consumer properties Spring Kafka intends to pass to clients.

**Level 3 — Live Kafka clients:** verifies runtime behavior/metrics and final settings after defaults, overrides, and client instantiation. Without tooling reading live client configs, explicitly note the scope limits.

`Spring Environment` example:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class KafkaEnvironmentSnapshot {

    private final Environment environment;

    public KafkaEnvironmentSnapshot(Environment environment) {
        this.environment = environment;
    }

    public String producerAcks() {
        return environment.getProperty(
                "spring.kafka.producer.acks");
    }

    public String consumerAutoCommit() {
        return environment.getProperty(
                "spring.kafka.consumer.enable-auto-commit");
    }
}
~~~

A `null` value may simply mean the property wasn't explicitly set; **do not conclude the client receives `null` or has no default**. Kafka keys inside Boot generic maps (like `producer.properties` and `consumer.properties`) bind differently; read them from bound `KafkaProperties` or the factories after binding.

### Inspect Kafka Factories Rather Than Only `application.yml`

For default or custom factories of the corresponding type:

~~~java
import java.util.Map;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;

public final class KafkaFactorySnapshot {

    public static Map<String, Object> producer(
            DefaultKafkaProducerFactory<?, ?> factory) {
        return factory.getConfigurationProperties();
    }

    public static Map<String, Object> consumer(
            DefaultKafkaConsumerFactory<?, ?> factory) {
        return factory.getConfigurationProperties();
    }
}
~~~

These maps show configuration **passed into the factory**, though they do not necessarily include every client default or every live client instance. Some apps also use custom factories instead of `DefaultKafkaProducerFactory`/`DefaultKafkaConsumerFactory`; use matching observation adapters rather than unsafe casts.

**Never log the entire configuration map.** It can contain SASL passwords, SSL keystore passwords, JAAS configs, or internal secrets. Export only a reviewed allowlist of keys.

## 7. Normalizing Data Before Diffing

The same setting can be represented in multiple ways:

~~~text
true, "true", TRUE
30000, "30000"
30s, 30000ms
acks=all, acks="-1" (depends on client/version representation)
cleanup.policy=compact,delete or delete,compact
~~~

Raw string comparison creates **false positives** for semantically identical values, while overly aggressive normalization can hide real differences.

Rules:

1. **Booleans:** parse to `true`/`false` before comparing.
2. **Durations:** convert to milliseconds with a unit-aware parser.
3. **Integers:** parse numerically; never string-compare `"05"` against `"5"`.
4. **Enums:** canonicalize against valid values without silently fixing typos.
5. **Lists/sets:** sort only when order **carries no meaning**; never sort bootstrap servers or priority-ordered lists if order matters.
6. **Kafka aliases:** treat two forms as equivalent only when confirmed by docs for your **active client version**.
7. **Absent vs. default:** distinguish "unset," "client default," and "explicit override" to catch post-upgrade drift.
8. **Secrets:** never turn secrets into readable logs or easily brute-forced hashes.

Example normalized snapshot:

~~~json
{
  "service": "orders-worker",
  "environment": "production",
  "policyVersion": "kafka-reliability-v4",
  "producer": {
    "acks": "all",
    "enable.idempotence": true
  },
  "consumer": {
    "enable.auto.commit": false,
    "isolation.level": "read_committed"
  }
}
~~~

Hashing normalized JSON helps compare two pods, yet **hashes are only reliable when schemas and canonicalization stay consistent**. If two pods share the exact same misconfiguration, their hashes match—always compare against the approved baseline.

## 8. Using `AdminClient` to Inspect Topic Configuration

Kafka brokers/topics sit **outside `Spring Environment`**. `AdminClient` inspects topic descriptions and configs when the principal holds permission.

Java example:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Properties;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.clients.admin.Config;
import org.apache.kafka.clients.admin.ConfigEntry;
import org.apache.kafka.common.config.ConfigResource;

public class KafkaTopicConfigurationObserver {

    public static void observe(String bootstrapServers,
                               String topicName) throws Exception {

        Properties props = new Properties();
        props.put(AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
                bootstrapServers);

        ConfigResource topic = new ConfigResource(
                ConfigResource.Type.TOPIC, topicName);

        try (AdminClient admin = AdminClient.create(props)) {
            Map<ConfigResource, Config> configs =
                    admin.describeConfigs(List.of(topic))
                            .all()
                            .get(10, TimeUnit.SECONDS);

            Config config = configs.get(topic);

            for (String key : List.of(
                    "min.insync.replicas",
                    "cleanup.policy",
                    "retention.ms")) {

                ConfigEntry entry = config.get(key);
                if (entry != null && !entry.isSensitive()) {
                    // Add key, value, source to the allowlisted snapshot.
                    // Do not dump the entire Config.
                    String effectiveValue = entry.value();
                    System.out.println(key + "=" + effectiveValue);
                }
            }

            var description = admin.describeTopics(
                    List.of(topicName))
                    .allTopicNames()
                    .get(10, TimeUnit.SECONDS)
                    .get(topicName);

            int partitionCount = description.partitions().size();
            System.out.println("partitions=" + partitionCount);
            // Replication factor can be inspected via partition replicas.
        }
    }
}
~~~

This snippet focuses on **allowlisted configs**; in production, send output to controlled loggers/collectors, pass proper security properties to connect to brokers, and handle timeouts and authorization errors. Never hardcode literal passwords.

For replication factor:

~~~java
int minReplicaCount = description.partitions().stream()
        .mapToInt(p -> p.replicas().size())
        .min()
        .orElse(0);
~~~

This reports the **minimum replica count observed across partitions**, useful for catching uneven partition replication. Never assume every partition shares the same replication factor if a topic underwent reassignment.

### Watch Config Sources

`AdminClient` can indicate whether a `ConfigEntry` comes from a **default**, **dynamic topic config**, or another source. Drift detectors should capture **source** when available, because an unapproved override matching the current effective default is still a governance signal.

Sensitive values are redacted by brokers. Never try to bypass secret masking; verify reference metadata or auth/rotation health through approved channels.

## 9. Defining Drift Policies and Severity Levels

Not every mismatch requires halting a service. Classify findings:

| Severity | Examples | Response |
|---|---|---|
| **Critical** | Transactional producer lost transaction config; transactional listener fails to commit offsets properly; consumer reads `read_uncommitted` when contract mandates `read_committed` | Block promotion or rollout; intervene before serving traffic |
| **High** | Lowered `acks`, disabled idempotence, `min.insync.replicas` below baseline, wrong DLT routing | Urgent alert and controlled fix rollout |
| **Medium** | `max.poll.interval`, retry backoff, or concurrency outside profile | Assess impact and remediate in a change window |
| **Low** | Intentional changes to client ID prefix, log level, or metric tags | Monitor or approve exception |
| **Unknown** | Cannot read config due to ACL/network/timeout | Report `UNKNOWN`, never `PASS` |

These severities are illustrative and depend on business SLAs. For a payment processor, a DLT policy change may be critical; for a best-effort analytics log consumer, severity may differ.

**Never kill all pods automatically when a detector hits a transient `AdminClient` timeout.** Startup fail-closed fits critical local invariants, but restarting every pod whenever a broker admin endpoint blips turns the drift detector into an outage generator. Separate:

- **Local critical invariants**: checked at startup, failing fast before taking traffic.
- **External observations**: bounded retries, `UNKNOWN` status, evaluated alongside cluster health.
- **Deployment gates**: blocking promotion unless baseline checks pass.
- **Runtime alerts**: notifying on drift emerging post-rollout.

## 10. Example Safe Snapshot Comparison Detector

Detectors should operate strictly on **allowlisted, normalized snapshots**, never ingesting raw secret-bearing maps and logging them.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class ConfigurationDriftDetector {

    public record Drift(
            String key, String expected, String actual) {
    }

    public List<Drift> compare(
            Map<String, String> approved,
            Map<String, String> observed) {

        List<Drift> drift = new ArrayList<>();

        for (Map.Entry<String, String> entry
                : approved.entrySet()) {

            String key = entry.getKey();
            String expected = entry.getValue();
            String actual = observed.get(key);

            if (!Objects.equals(expected, actual)) {
                drift.add(new Drift(
                        key, expected,
                        actual == null ? "[MISSING]" : actual));
            }
        }

        return List.copyOf(drift);
    }
}
~~~

Usage example:

~~~java
Map<String, String> approved = Map.of(
        "producer.acks", "all",
        "producer.enable.idempotence", "true",
        "consumer.isolation.level", "read_committed",
        "consumer.enable.auto.commit", "false");

Map<String, String> observed = Map.of(
        "producer.acks", "1",
        "producer.enable.idempotence", "true",
        "consumer.isolation.level", "read_uncommitted",
        "consumer.enable.auto.commit", "false");

List<ConfigurationDriftDetector.Drift> drift =
        new ConfigurationDriftDetector().compare(
                approved, observed);

// drift includes producer.acks and consumer.isolation.level.
~~~

**This is a snapshot comparator, not a complete Kafka discovery engine.** Real implementations need adapters collecting from `ProducerFactory`, `ConsumerFactory`, listener containers, `AdminClient`, and infra manifests, followed by schema-driven type normalization. A real key may hold an active default absent from a map; distinguish **missing observation** from **mismatch**.

### Never Print Sensitive Values on Drift

Output should resemble:

~~~json
{
  "service": "orders-worker",
  "policyVersion": "kafka-reliability-v4",
  "status": "DRIFT_DETECTED",
  "findings": [
    {
      "key": "producer.acks",
      "expected": "all",
      "actual": "1",
      "severity": "HIGH"
    },
    {
      "key": "consumer.isolation.level",
      "expected": "read_committed",
      "actual": "read_uncommitted",
      "severity": "CRITICAL"
    }
  ]
}
~~~

If a key is a password, token, or keystore secret, **never emit `expected`/`actual` values**. Better yet, exclude secret values from snapshots completely and verify existence, version/rotation metadata, and connectivity via dedicated security checks.

## 11. Checking Invariants at Application Startup

One drift safeguard is failing fast when **effective local config** violates non-negotiable contracts.

`Spring Environment` check example:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class KafkaReliabilityStartupGuard
        implements ApplicationRunner {

    private final Environment environment;

    public KafkaReliabilityStartupGuard(
            Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        require(
                "spring.kafka.producer.acks", "all");
        require(
                "spring.kafka.consumer.enable-auto-commit",
                "false");
    }

    private void require(String property, String expected) {
        String actual = environment.getProperty(property);

        if (!expected.equalsIgnoreCase(actual)) {
            throw new IllegalStateException(
                    "Kafka reliability config mismatch: "
                            + property);
        }
    }
}
~~~

This guard illustrates a **local startup assertion** on explicitly configured properties. It does not inspect broker topics, catch a custom `ProducerFactory` ignoring Spring properties, or verify all Kafka client defaults. In production, verify **bound factory configs**, an independent policy version, and run checks at the right point in the deployment lifecycle.

**Never hardcode one global baseline and deploy across staging and production without profile awareness.** If an invariant applies strictly to production, the guard must know the approved environment/release policy—never silence drift by disabling guards indiscriminately.

### Startup Guard vs. Health Indicator?

- Startup guards suit **critical configs that must hold before processing any message**.
- Health/Readiness indicators can flag invalid runtime configs, provided transient broker admin timeouts do not cause endless pod restart loops.
- An external drift detector outside the service is usually better suited for scanning cluster/topic state and multiple services together.

Choose mechanisms based on blast radius, config ownership, and rollback capability.

## 12. Kubernetes, Helm, and GitOps

In Kubernetes, drift can arise from:

- Editing Deployments/ConfigMaps with `kubectl` outside Git.
- Production Helm values diverging from reviewed commits.
- Unrolled pods still running old images or environment variables.
- Secret versions differing across pods.
- Operators or admission controllers mutating fields.
- Autoscalers adjusting replicas by design (not drift if permitted by policy).
- ExternalSecret/Secret Manager updates not yet reloaded by the app.
- Volume-mounted configs updated on disk without JVM re-application.

Workflow example:

~~~text
Git approved values
       |
       v
helm template
       |
       v
Kubernetes desired manifests
       |
       v
kubectl diff / GitOps reconciliation
       |
       v
Pods receive config
       |
       v
Spring Kafka runtime snapshot
       |
       v
Kafka broker/topic effective configs
~~~

Sample commands in an authorized environment:

~~~bash
# Render manifests from the chart and reviewed values.
helm template orders-worker ./chart \
  --namespace orders \
  --values values-production.yaml > rendered.yaml

# Diff desired state against live resources.
kubectl diff --namespace orders -f rendered.yaml

# Inspect deployment revision and rollout status.
kubectl --namespace orders rollout status \
  deployment/orders-worker

# Inspect Deployment template/config.
kubectl --namespace orders get deployment \
  orders-worker -o yaml
~~~

**Run these commands only with proper authorization in the right namespace/cluster.** Manifests may reference Secrets or sensitive details, so never dump raw outputs into public CI logs. Prefer GitOps controllers like Argo CD/Flux or policy engines when available to detect/reconcile drift through reviewed workflows.

Helm/GitOps manifests cannot prove Kafka **runtime behavior** if application code constructs custom clients directly. Bridge both inspection layers.

### Partial Rollouts

Suppose four pods are running:

~~~text
orders-worker-v12: Pod A, Pod B
orders-worker-v11: Pod C, Pod D
~~~

During a rolling deployment, two active config versions can be an **approved transient state**. Drift detectors need transition windows and target revisions:

1. Track both image digest and config/policy version per pod.
2. Permit mixed versions within a bounded rollout window.
3. After the deadline, verify all pods run the approved target revision.
4. If a rollout stalls, alert rather than assuming fleet convergence.
5. Verify protocol/topic compatibility while two versions process concurrently.

Never change a consumer group ID to "clean up" an old pod; changing group IDs can trigger replays or skip data depending on offset reset.

## 13. Checking Kafka Topics and Brokers Outside Deployment

Some drift comes from administrators operating directly on Kafka:

~~~text
Approved:
  topic orders.events
  partitions=6
  replication.factor=3
  min.insync.replicas=2

Observed:
  partitions=12
  replication.factor=3
  min.insync.replicas=1
~~~

Increasing partitions is not safely reversible. For `orderId`-keyed messages, changing partition count alters key → partition mapping for new records, threatening ordering expectations if the app assumes a key always lands on the same partition across history.

Lowering **`min.insync.replicas=2` to `1`** weakens durability guarantees for `acks=all` producers, even though no symptom appears while all brokers stay healthy.

### Kafka CLI for Investigations

Examples depending on CLI version:

~~~bash
# List topic configs recorded as overrides.
kafka-configs.sh \
  --bootstrap-server kafka-prod-a:9092 \
  --entity-type topics \
  --entity-name orders.events \
  --describe

# Inspect partitions, replicas, and ISR.
kafka-topics.sh \
  --bootstrap-server kafka-prod-a:9092 \
  --topic orders.events \
  --describe
~~~

`kafka-configs.sh` may omit inherited broker defaults. To inspect **effective values**, use `AdminClient.describeConfigs` or tooling that surfaces config sources; if the principal lacks `DESCRIBE_CONFIGS`, report **`UNKNOWN`/`UNAUTHORIZED`** rather than treating "no overrides shown" as `PASS`.

### ACLs Are Configuration Too

Suppose the same consumer app runs while an ACL edit revokes its `READ` permission on the topic or group. The app may time out/retry and look like a network outage. Access drift checks must compare **principal, resource pattern, operation, and cluster scope** against the baseline without dumping credentials.

## 14. Integrating Drift Detection into CI/CD

A pipeline can enforce controls across stages:

~~~text
Pull Request
   |
   +-- Validate baseline schema
   +-- Diff new config against approved policy
   +-- Check config ownership + change approval
   |
   v
Build / Unit tests
   |
   +-- Bind Spring Kafka properties
   +-- Assert critical invariants
   |
   v
Integration tests (Testcontainers / EmbeddedKafka)
   |
   +-- Verify behavior: send, retry, commit, rollback, DLT
   |
   v
Deploy staging
   |
   +-- Compare rendered manifests
   +-- Snapshot actual factories and Kafka topics
   |
   v
Deploy production (canary)
   |
   +-- Compare canary config against approved policy
   +-- Observe delivery/consumer lag/errors
   |
   v
Full rollout + periodic drift scan
~~~

**Static diffs do not replace behavioral integration tests.** `acks=all` cannot fulfill a durability contract if topic replication factor or min ISR is misconfigured. Conversely, one successful send test does not prove configs survive broker failures.

### Key Contract Tests

| Test | Expected Result |
|---|---|
| Producer `acks` differs from `all` in production | Pipeline fails or raises `HIGH` finding |
| Producer idempotence disabled against policy | `CRITICAL`/`HIGH` drift per contract |
| `read_committed` changed to `read_uncommitted` | `CRITICAL` drift for transactional consumers |
| `enable.auto.commit` enabled against policy | Drift flagged per ack/transaction model |
| Topic `min.insync.replicas` below baseline | `HIGH` drift with `AdminClient` evidence |
| Topic missing | Blocks deployment if topic is mandatory |
| Listener error handler lacks DLT | Drift flagged against reliability contract |
| Broker unreachable/unqueryable | `UNKNOWN`, never `PASS` |
| One pod has wrong config version post-rollout | Alert after transition window expires |
| Secret rotation changes value validly | Never logs or diffs plaintext secret |

### Testing with Spring Boot Context

A unit/integration test can inject property overrides to confirm the guard reacts. JUnit 5 example:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;
import org.springframework.boot.DefaultApplicationArguments;
import org.springframework.mock.env.MockEnvironment;

class KafkaReliabilityStartupGuardTest {

    @Test
    void rejectsProducerAcksDrift() {
        MockEnvironment env = new MockEnvironment()
                .withProperty(
                        "spring.kafka.producer.acks", "1")
                .withProperty(
                        "spring.kafka.consumer.enable-auto-commit",
                        "false");

        KafkaReliabilityStartupGuard guard =
                new KafkaReliabilityStartupGuard(env);

        assertThrows(IllegalStateException.class,
                () -> guard.run(new DefaultApplicationArguments()));
    }
}
~~~

This test verifies only the **local guard**; it does not prove the Kafka broker sees those settings. Pair it with Testcontainers/`EmbeddedKafka` and `AdminClient` assertions when testing topic drift or transactional consumer behavior.

## 15. Drift After the Application Is Already Running

Certain settings are read by Kafka clients **only at initialization time**. For example:

~~~text
10:00 Pod started
      Consumer created with isolation.level=read_committed

10:05 ConfigMap updated:
      isolation.level=read_uncommitted

10:06 JVM still runs with old consumer:
      read_committed

10:15 Pod restarted:
      New consumer reads changed config
      read_uncommitted
~~~

If a detector compares only mounted config files to Git, it flags drift at 10:05 even though **live consumer behavior won't change until clients recreate**. Conversely, inspecting only the existing client misses drift waiting to activate on the next restart.

Snapshots should therefore include:

- Deployed resource/config revision.
- Process startup time and app release version.
- Effective Spring properties after bootstrap.
- Factory properties.
- Client instance generation/recreation time when observable.
- Broker/topic configs and capture timestamp.

**Never assume Spring config refresh hot-reloads every Kafka client property.** Many changes require recreating consumers/producers/containers; others need specific APIs or behavior. Verify against your Spring Kafka version and actual config.

## 16. Assessing Drift Around Transactions and Exactly-Once

Systems using Kafka transactions must check multiple settings together:

~~~text
Producer:
  transactionIdPrefix distinct per active instance
  transactional producer factory enabled

Listener:
  transaction manager associated with Kafka listener container
  offsets sent in Kafka transaction as designed

Consumer:
  isolation.level=read_committed for downstream
  enable.auto.commit=false if contract requires

Broker:
  transaction coordinator healthy
  transaction timeout limits compatible
  replication/ISR adequate
~~~

**Having `transactionIdPrefix` alone does not prove end-to-end exactly-once.** If the listener container is not configured to send consumer offsets into the same Kafka transaction, outputs and offsets can still commit independently.

Drift detectors should check **listener wiring** and run behavioral tests:

1. Consume input.
2. Produce output inside the transaction.
3. On success, output is visible to `read_committed` consumers and input offset commits per design.
4. On failure before commit, output is aborted and offsets do not advance as committed.

For **database + Kafka** dual-writes, tests must separate DB transactions from Kafka transactions. To avoid lost events, use a transactional outbox or reconciliation rather than assuming enabling Kafka transactions makes two resources atomic.

## 17. Drift Affecting Consumer Lag, Retries, and DLT

Not every config drift throws an immediate error. For instance:

~~~text
Approved:
  max.poll.records=200
  max.poll.interval.ms=300000
  listener concurrency=4
  retryAttempts=3

Observed:
  max.poll.records=2000
  max.poll.interval.ms=300000
  listener concurrency=1
  retryAttempts=100
~~~

Consequences can include oversized poll batches exceeding `max.poll.interval`, rebalances, redeliveries, and rising consumer lag. Excessive retries also pin a partition on a poison message far longer.

Response should include:

- Comparing config and change history.
- Inspecting per-record latency, poll duration, partition assignments, and group rebalance counts.
- Checking DLT/retry policies and attempt caps.
- Load-testing to prove any new baseline causes no unintended duplicates or lag.
- Avoiding group ID swaps or offset resets as quick fixes for config mistakes.

Workloads legitimately require different tuning. Compare against a **service-specific policy**, not one blanket baseline across all consumers.

## 18. Observing and Alerting on Configuration Drift

A drift event should carry enough metadata to trace the change:

~~~json
{
  "event": "kafka.configuration.drift.detected",
  "service": "orders-worker",
  "environment": "production",
  "clusterAlias": "kafka-prod-a",
  "policyVersion": "kafka-reliability-v4",
  "release": "orders-worker-2.8.1",
  "observedAt": "2026-11-16T10:30:00+07:00",
  "scope": "consumer",
  "key": "isolation.level",
  "expected": "read_committed",
  "actual": "read_uncommitted",
  "severity": "CRITICAL",
  "status": "DRIFT_DETECTED"
}
~~~

This schema is illustrative. For sensitive fields, log only key/scope and status—**never log actual/expected secrets**.

Suggested metrics:

| Metric | Meaning |
|---|---|
| `kafka_config_drift_findings` | Finding count by service, scope, severity |
| `kafka_config_drift_scan_success` | Whether the scan retrieved complete data |
| `kafka_config_drift_scan_timestamp_seconds` | Timestamp of the latest scan |
| `kafka_config_drift_age_seconds` | Duration a finding remains unresolved |
| `kafka_config_drift_scan_duration_seconds` | Collection and comparison latency |
| `kafka_reliability_policy_version_info` | Active policy version metadata |

Metric names are **suggestions**, not built-in Spring Kafka meters. When exporting to Prometheus:

- Never use passwords, Kafka message keys, `customerId`, or raw URLs as labels.
- Avoid dynamic pod UIDs or `transactional.id`s on every metric if that causes high cardinality.
- Use bounded-cardinality labels such as `service`, `environment`, `scope`, `severity`, and policy revision.

### When to Alert?

**Immediate alert** for critical drift in environments handling critical data. **Scheduled review** for medium/low drift. **`UNKNOWN`/scan failures** also warrant alerts past a threshold if the detector loses visibility into a cluster for extended periods.

Avoid firing duplicate alerts on every scan for an unchanged finding; group/deduplicate alerts and track `firstSeen`/`lastSeen`. Approved exceptions must carry an owner, justification, and expiration date.

## 19. Drift Investigation Runbook

When the detector reports `producer.acks` changed from `all` to `1`:

1. Identify service, namespace, pod, image digest, Kafka cluster, and policy version.
2. Determine whether drift affects **all pods** or only a subset.
3. Read deployment manifests and effective Spring properties of affected pods via authorized channels.
4. Inspect `ProducerFactory` config, client generation, and custom configuration code.
5. Trace Git/Helm/GitOps change history, manual overrides, and rollout timestamps.
6. Use `AdminClient` to verify topic replication/`min.insync.replicas` and ISR health.
7. Assess whether messages were already affected; check outputs, offsets, and the incident window.
8. Decide between rolling back or rolling out a controlled fix.
9. After remediation, verify effective runtime config and behavior—not just Git diffs.
10. Record audit trail: root cause, approver, completion time, and regression tests.

### Never Fix Everything by Changing Everything at Once

If `acks`, idempotence, min ISR, partitions, and retry policies all drifted, restore **reliability invariants** in a controlled order. Partition count or group ID changes may not roll back cleanly, so never blindly run "sync everything back to Git."

### Fix Drift at the Owning Source

| Drift Source | Remediation Path |
|---|---|
| Wrong Git values | Pull request + review + rollout |
| Live Deployment edited manually | GitOps reconcile / managed rollback |
| Wrong env/profile override | Fix source env/ConfigMap/Secret reference, controlled restart |
| Custom `ProducerFactory` code | Fix bean configuration, unit/integration tests |
| Wrong broker/topic override | Approved `AdminClient`/operator update |
| Altered ACLs/quotas | Restore via security/platform change control |
| Stale pod post-rollout | Investigate rollout, readiness, draining, and canary |
| Dynamic config not yet applied by client | Recreate client/container per supported semantics |

## 20. Protecting Sensitive Information in Configuration Snapshots

Kafka configurations may include:

- SASL JAAS configs and passwords.
- SSL truststore/keystore paths and passwords.
- Schema Registry or related service API tokens.
- OAuth client secrets and callback handler configs.
- Internal broker endpoints and topology details.
- Policy-sensitive topic/customer/tenant names.

**Never dump raw `Environment`, `KafkaProperties`, or Kafka factory maps to logs.** Instead:

1. Maintain an allowlist of non-sensitive reliability keys.
2. For secrets, inspect only permitted metadata like secret references, rotation versions, or auth status—never values.
3. Restrict snapshot/Actuator/`configprops`/`env` endpoints; never expose them publicly.
4. Never store `kubectl`/Helm outputs containing secrets in public CI artifacts.
5. Encrypt snapshots in transit and store them in an audited system with appropriate retention.
6. Avoid error messages containing raw values of unclassified settings.
7. Assess risk before fingerprinting secrets: low-entropy secrets can be brute-forced from unsalted hashes.

A report might record:

~~~text
key=sasl.jaas.config
scope=consumer
status=SECRET_REFERENCE_CHANGED
expectedSecretVersion=v12
observedSecretVersion=v13
actualSecretValue=[NOT_COLLECTED]
~~~

This applies only when the secret manager exposes readable version metadata. **Do not assume a differing secret version is bad drift**: it may represent an approved rotation.

## 21. Drift Detection Test Matrix

| Scenario | Drift Injected in Test | Expected Detector Result |
|---|---|---|
| DRIFT-01 | Unchanged baseline | `PASS` |
| DRIFT-02 | Producer `acks` `all` → `1` | `HIGH`/`CRITICAL` per policy |
| DRIFT-03 | Producer idempotence `true` → `false` | Corresponding finding |
| DRIFT-04 | Consumer `read_committed` → `read_uncommitted` | `CRITICAL` under transactional contract |
| DRIFT-05 | Consumer auto-commit `false` → `true` | Finding per ack model |
| DRIFT-06 | Consumer `group.id` changed | Warning of potential replay/offset impact |
| DRIFT-07 | Topic min ISR `2` → `1` | `HIGH` |
| DRIFT-08 | Topic partition count changed | Finding requiring ordering review |
| DRIFT-09 | Topic does not exist | `FAIL`/`UNKNOWN` per deploy policy |
| DRIFT-10 | `AdminClient` permission denied | `UNKNOWN`/`UNAUTHORIZED`, never `PASS` |
| DRIFT-11 | Spring property valid yet custom factory overrides it | Factory-level detector catches it |
| DRIFT-12 | Env overrides `application.yml` | Effective config differs from file |
| DRIFT-13 | One pod remains on old release | Finding raised after rollout window |
| DRIFT-14 | Secret value changes during valid rotation | Zero secret leakage; policy handles exception |
| DRIFT-15 | Kafka client upgrade alters default | Detects absent/default semantic shift |
| DRIFT-16 | Listener DLT topic altered | Listener policy finding |
| DRIFT-17 | Retry policy attempts too high | Warning per SLA |
| DRIFT-18 | Topic config changed outside Git | `AdminClient` observation differs from baseline |
| DRIFT-19 | Single scan network timeout | `UNKNOWN` with bounded retries |
| DRIFT-20 | Drift remediated | Finding `RESOLVED`, history preserved |

### Test Types to Include

**Unit tests:** normalize booleans, durations, enums, missing keys, unknown states; compare expected/observed and assign severities accurately.

**Spring context tests:** inject intentional profile/property overrides, boot context, and inspect Kafka factories and startup guards. Avoid checking `Environment` alone when customizers can alter factories.

**Integration tests with `EmbeddedKafka`/Testcontainers:** create topics and `AdminClient`, mutate topic-level configs in a controlled way, and verify observers read accurately. Use an isolated test broker and test-scoped policy.

**Behavioral tests:** for transactional producers/consumers, verify commit/abort visibility with a `read_committed` consumer; for listeners, verify offsets/retries/DLT per contract. This proves runtime execution matches intent, not just config strings.

**Deployment tests:** render Helm, diff against live resources in a test namespace, and verify image/config versions and rolling update behavior.

**Security tests:** inject a dummy sentinel secret in test environments and assert reports/logs never contain the literal sentinel.

## 22. Common Mistakes

**Comparing only `application.yml` with Git.** Env vars, profiles, custom factories, Kafka defaults, and broker/topic configs can all differ.

**Using live runtime as the baseline.** The detector compares the source against itself and always passes.

**Comparing raw strings without type normalization.** `true` vs. `"true"` triggers false drift, while careless normalization hides real semantic differences.

**Treating unset properties as `null` received by the client.** Kafka clients supply defaults and Spring applies binding/customization; separate absent, default, and explicit values.

**Checking `producer.acks` while ignoring min ISR/replication factor.** Durability depends on broker and topic settings together.

**Assuming `acks=all` prevents record loss in every failure mode.** Replication, ISR, retention, and failure scenarios still govern outcomes.

**Assuming `transactionIdPrefix` alone gives exactly-once.** Listener offset transactions, `read_committed` downstreams, and external side effects need dedicated design.

**Treating `read_uncommitted` as equivalent to `read_committed`.** Consumers can read aborted records.

**Changing consumer `group.id` to fix drift.** Triggers unintended replays or skipped data depending on offset reset.

**Trying to shrink partition counts back to baseline.** Kafka does not support simple partition reduction; plan a topic migration if needed.

**Treating unresponsive dynamic config checks as `PASS`.** Unobservable means `UNKNOWN`, not drift-free.

**Dumping all configs to logs to debug.** Exposes SASL/SSL secrets and sensitive topology.

**Restarting all pods automatically on broker admin API timeouts.** Turns the drift detector into a secondary outage source.

**Failing to distinguish rollout windows from persistent drift.** During rolling updates, two versions are temporarily valid.

**Fixing drift at runtime without updating the source of truth.** The next reconciliation overwrites the fix and drift returns.

**Alerting without owners, SLAs, and runbooks.** Findings linger indefinitely without remediation.

## 23. Procedure for Rolling Out Configuration Drift Detection

Apply an operational workflow in steps:

1. **Define each service's reliability contract:** delivery, ordering, consumer offsets, transactions, retries, and DLT.
2. **Create versioned baselines** per environment/cluster/service without secrets.
3. **Map configuration sources:** Git, Helm, ConfigMaps/Secrets, `Spring Environment`, Kafka factories, listener containers, and brokers/topics.
4. **Collect observed snapshots** via least-privilege adapters over allowlisted safe keys only.
5. **Normalize against schemas** and distinguish defaults/overrides and missing/unknown values.
6. **Compare against independent baselines**, emitting findings with severity and evidence.
7. **Gate CI/CD** on critical configs and canary/rollout policies.
8. **Run periodic post-deploy scans** to catch manual edits or lagging pods.
9. **Verify behavioral contracts** against real test Kafka for transactions, retries, DLT, and offsets.
10. **Route alerts with owners and exception expirations**, keeping `firstSeen`/`lastSeen`/`resolvedAt` history.
11. **Remediate at the owning source**, rolling out carefully without unintended offset or partition changes.
12. **Verify post-fix outcomes** in runtime and brokers, not just when Git diffs return to zero.

## 24. Summary

**Checking configuration drift** in Spring Kafka is far more than diffing a YAML file. System reliability depends on **effective configuration across multiple layers**: Spring Boot binding, producer and consumer factories, listener containers, Kafka brokers/topics, deployment infrastructure, and consistency across running pods.

A trustworthy setup combines **independent approved baselines**, **provenance-aware observed snapshots**, type normalization, impact-based drift classification, and strict secret protection. Pairing **CI/CD diffs, startup guards, runtime scans, `AdminClient` checks, and behavioral tests** catches changes early before they cause lost events, duplicates, offset corruption, broken transaction visibility, or faulty retry/DLT behavior.

Above all, **never mistake configuration seen in Git for actual runtime behavior**. Only when effective settings match the environment baseline, brokers/topics are verified, and reliability contracts are tested can operations be confident a rollout has not silently degraded Spring Kafka reliability.
