# Independent Broker and Client Upgrades in Spring Kafka

In a Kafka ecosystem, upgrading **Kafka brokers** does not necessarily force every producer and consumer to upgrade its Java client at the exact same moment. A single cluster may serve Java, Python, Go, or Kafka Streams applications with different deployment lifecycles. Likewise, application teams may need to upgrade **Spring Kafka** or `kafka-clients` for bug fixes and security patches before the platform team upgrades the cluster.

The ability to upgrade **brokers and clients independently** comes from Kafka's protocol capability negotiation between client and broker. However, that **does not mean every version combination is always compatible**, every new feature runs on older brokers, or upgrading a Kafka cluster has zero impact on in-flight processing.

Within **Spring Kafka Reliability Operations → Upgrades and Compatibility**, this lesson teaches you how to construct a **compatibility matrix, upgrade ordering, rollout procedure, and safe rollback**, while verifying message delivery, offsets, retry/DLT, transactions, schemas, and security at each stage.

```text
           Application Team A              Application Team B
         Spring Boot / Kafka            Spring Boot / Kafka
        kafka-clients version X        kafka-clients version Y
                 |                              |
                 | Kafka wire protocol          |
                 +---------------+--------------+
                                 |
                                 v
                       Kafka broker cluster
                   broker versions in a
                   controlled rolling upgrade
                                 |
                         KRaft controllers
                    + metadata feature levels
```

**Core message:** decoupling broker and client upgrade timing is a valuable architectural capability; to leverage it safely, maintain two separate contracts: the **wire protocol contract** between Kafka components and the **business contract** covering payloads, keys, ordering, offsets, retries, and side effects.

## 1. First, Which "Kafka Version" Are We Talking About?

In a Spring Boot application, there are multiple relatively independent version layers:

| Layer | Where It Lives | Responsibility | What to Verify on Upgrade |
| --- | --- | --- | --- |
| **Kafka broker** | Server cluster | Log storage, replication, group coordinator, transaction coordinator, protocol APIs | Rolling upgrade, feature level, cluster health, client compatibility |
| **KRaft controller** | Controller quorum | Manages cluster metadata and broker state | Quorum, release-specific upgrade guide, metadata compatibility |
| **Apache Kafka Java client** (`org.apache.kafka:kafka-clients`) | Inside producer/consumer JVM | Send/receive records, metadata, offset commits, broker protocol | Wire APIs, broker feature availability, client config, and JDK |
| **Spring Kafka** (`org.springframework.kafka:spring-kafka`) | Inside Spring application | `@KafkaListener`, containers, `KafkaTemplate`, error handlers, retry topics, transactions | API/binary compatibility with Kafka client and Spring Framework |
| **Spring Boot** | Application | Dependency management, auto-configuration, properties, and lifecycle | Boot/Spring Kafka/Framework/Java support matrix |
| **Schema Registry / serializers** | Libraries and external service | Avro/JSON Schema/Protobuf, payload evolution | Schema compatibility, serializer version, subject strategy |
| **Kafka Connect/Streams** | Specialized applications | Connector tasks or stateful stream processing | Dedicated upgrade guides, state stores, assignment, and protocol |

For instance, a system may upgrade brokers first while applications remain on Spring Kafka 3.x and the Kafka Java client from Spring Boot 3.x's dependency tree. This **does not automatically force** you to bump the Spring Boot major version at the same time as the brokers.

Conversely, upgrading Spring Boot may simultaneously pull in newer Spring Kafka, Kafka clients, Jackson, and Spring Framework versions. That is a **multi-layer application upgrade**, even when Kafka brokers stay unchanged.

### 1.1. Three Types of Changes to Distinguish

```text
Change A: Broker only
  broker B1 -> B2
  client C1 unchanged

Change B: Client only
  broker B1 unchanged
  kafka-clients C1 -> C2

Change C: Application stack
  Spring Boot / Spring Kafka / Java / kafka-clients change together
  broker B1 unchanged
```

Testing differs across A, B, and C. A "producer sends and consumer receives one message" check is useful yet does not prove transactional semantics, rebalances, or retry/DLT remain unchanged after upgrading.

## 2. Why Can Brokers and Clients Upgrade Separately?

Apache Kafka uses a request/response protocol over TCP. Each request type has an API key and versioned request/response schemas. Kafka clients can issue `ApiVersionsRequest` to discover which API versions the broker supports and choose a compatible communication path.

```text
Kafka Java client C2                        Broker B1
        |                                      |
        |------ ApiVersionsRequest ---------->|
        |<----- Supported API versions --------|
        |                                      |
        |------ ProduceRequest(version K) ---->|
        |<----- ProduceResponse(version K) ----|
```

If a newer client supports an API version not yet supported by an older broker, the client typically must select a compatible protocol version for that operation or **cannot use the new feature**. A feature requiring explicit broker support cannot be "enabled" merely by upgrading the client JAR.

### 2.1. Wire Compatibility Does Not Equal Feature Parity

| Goal | New Client + Old Broker | New Broker + Old Client |
| --- | --- | --- |
| Routine produce/consume | Usually has a compatible path if the pair is supported | Usually has a compatible path if the pair is supported |
| Using new Kafka API or group protocol | May be constrained by the old broker | Old client may not know the new feature |
| Transactions / idempotent producer | Needs coordinator and matching APIs/versions | Needs a client with the matching implementation |
| New schema | Depends on serializers and consumers, not just brokers | Brokers do not automatically decode/validate business schemas as apps expect |
| New Spring Kafka retry/DLT | Depends on Spring Kafka and topics/ACLs | New broker does not auto-create app retry policies |
| KRaft metadata management | Belongs to cluster control plane | Java producer/consumer does not upgrade metadata feature levels |

**Never write in operational docs that "Kafka supports backward compatibility so any client works with any broker."** Practical limits depend on **release pairs, APIs, client languages, security settings, and specific features**. Always verify release notes and compatibility guidance for your exact two target versions.

### 2.2. Inter-Broker Compatibility During a Rolling Upgrade

A cluster undergoing a rolling upgrade temporarily runs brokers on two versions. This is **broker-to-broker compatibility**, distinct from Java client-to-broker compatibility.

For example:

```text
Before upgrade:
  broker-1 = version N
  broker-2 = version N
  broker-3 = version N

Mid-rolling upgrade:
  broker-1 = version N+1
  broker-2 = version N
  broker-3 = version N

After binary rollout completes:
  broker-1 = version N+1
  broker-2 = version N+1
  broker-3 = version N+1
```

Kafka permits such a mixed-broker phase **only within the bounds of an official upgrade path**, not leaving a cluster in mixed versions indefinitely. If versions N and N+1 do not lie on a supported direct upgrade path, intermediate hops or a dedicated migration are required.

## 3. Four Cells of the Compatibility Matrix

Before each upgrade, build a **2 × 2** matrix:

| | Current Broker B1 | Target Broker B2 |
| --- | --- | --- |
| **Current Client C1** | (1) Running baseline | (2) Post broker-first state |
| **Target Client C2** | (3) Post client-first state | (4) Final target |

If you plan to **upgrade brokers first**, prove cell **(2)**: client C1 still performs required business operations against broker B2. If you plan to **upgrade clients first**, prove cell **(3)**: client C2 operates against broker B1 without accidentally enabling an unsupported feature.

Put all four cells into one test plan rather than testing only final target **(4)**. Many incidents occur only in transitional states: an un-upgraded legacy application, a Kafka Streams service using older assignment, or a Spring Kafka retry container still running with a different serializer.

### 3.1. Illustrative Decision Table

Suppose a project runs:

```text
Kafka broker: version B1
Spring Boot: version S1
Spring Kafka: version SK1
kafka-clients: version C1

Target:
Kafka broker: version B2
Spring Boot: keep S1 in phase 1
Spring Kafka / kafka-clients: upgrade later to SK2 / C2
```

Preparation table:

| Combination | Test Scope | Pass Criteria |
| --- | --- | --- |
| B1 + C1 | Baseline | Measured throughput, lag, errors, offsets, and outputs recorded |
| B2 + C1 | Broker-first transition | Produce, consume, rebalances, retry/DLT, auth, and transactions if used |
| B1 + C2 | Client-first transition | Zero `UnsupportedVersionException`; new configs require no unsupported broker features |
| B2 + C2 | Final state | Passes functional, failure-path, and performance regression tests |

Labels B1/B2/C1/C2 intentionally **avoid hardcoding specific version pairs**. Do not infer every Kafka 3.x/4.x pair is valid from this table; actual releases and mandatory migration steps must be confirmed prior to rollout.

## 4. Changes That Can Break Compatibility Even While Protocol Works

A client can connect and fetch metadata successfully yet still process business logic incorrectly. Risk areas:

1. **Deserializer/serializer:** Avro/Protobuf/JSON payloads change schemas, subjects, or headers.
2. **Consumer group protocol:** assignment protocol, `group.protocol`, or assignor changes.
3. **Offsets:** `group.id`, `auto.offset.reset`, ack mode, or commit policy changes.
4. **Transactions:** `transactional.id`, isolation level, or Kafka transaction manager changes.
5. **Retry/DLT:** topic names, container factories, backoff, commit behavior, or forwarding serializers change.
6. **Security:** SASL mechanism, mTLS, truststore, ACLs, or principal mapping changes.
7. **Runtime:** JDK baseline or how clients open/close inside containers changes.
8. **Broker metadata/features:** enabling new cluster features before all components are ready.
9. **Operational capacity:** long rebalances, ISR drops, or throughput/latency shifts.

A basic smoke test is therefore only the **first gate**, not certification for the entire upgrade.

## 5. KRaft, ZooKeeper, and Metadata Feature Levels

When saying "upgrade Kafka brokers," distinguish **upgrading broker binaries** from **raising cluster metadata feature levels**.

### 5.1. ZooKeeper to KRaft Is Not a Minor Change

Earlier Kafka generations could use **ZooKeeper** to manage cluster metadata. Modern Kafka uses **KRaft** with a controller quorum. Apache Kafka **4.0 removes ZooKeeper mode**; thus any cluster still relying on ZooKeeper must complete the supported migration path **before** moving to Kafka 4.x.

```text
Old system:
  Kafka brokers <--> ZooKeeper ensemble

New system:
  Kafka brokers <--> KRaft controller quorum

Do not do this:
  Upgrade straight to 4.x broker binaries on a cluster still in ZooKeeper mode
  and expect it to keep starting up as before.
```

ZooKeeper → KRaft migration is **its own infrastructure project**, with preflight checks, snapshots/backups, version-specific guides, and stage-specific rollback boundaries. Do not combine that migration with simultaneously upgrading Spring Boot clients in one batch unless genuinely required and thoroughly tested.

### 5.2. What Is `metadata.version`?

In KRaft, cluster metadata feature levels are managed via **feature levels**, typically expressed by `metadata.version`. Upgrading broker binaries does not automatically activate every new metadata feature immediately.

```text
Phase A: Binary rollout
  controller/broker binaries upgraded to target version
  metadata.version stays at a level supported for upgrade/rollback

Phase B: Observe
  verify ISR, elections, client APIs, groups, transactions, lag

Phase C: Feature finalization
  once compatibility is verified and binary rollback is no longer needed,
  raise metadata feature level per release runbook
```

This is a **conceptual model**, not a promise that every release lets you stay on an old feature level forever or roll back freely. Specific Kafka releases may dictate different ordering for controller/broker upgrades and feature finalization.

Inspection command in a KRaft cluster:

```bash
kafka-features.sh \
  --bootstrap-server broker1:9092 \
  describe
```

This command shows the feature levels advertised by the cluster. Syntax for changing feature levels and flags such as `--release-version` depend on the Kafka release; **never copy a feature-level upgrade command from an article for another release and run it in production**.

### 5.3. Distinguishing from `inter.broker.protocol.version`

In Kafka upgrade docs for ZooKeeper-based generations, you frequently see `inter.broker.protocol.version` (IBP) and sometimes `log.message.format.version`. Those settings apply to specific eras and architectures. With KRaft and newer Kafka releases, compatibility management relies primarily on **feature levels**, especially `metadata.version`.

**Do not mechanically apply the legacy "hold IBP, upgrade binaries, then bump IBP" recipe from older Kafka to a modern KRaft cluster.** Confirm the cluster mode and target release first, then follow the corresponding upgrade guide.

### 5.4. The Controller Quorum Must Be Planned Explicitly

In KRaft, the controller quorum needs enough live members to manage metadata. When rolling-restarting controllers:

- Never stop multiple controllers simultaneously and break quorum availability.
- Check leader/controller elections and metadata replication health.
- Follow the controller and broker upgrade sequence of the target release.
- In **combined broker/controller** node deployments, restarting one node impacts both roles; capacity/quorum planning matters even more.
- Watch KRaft metadata convergence before moving to the next node.

Never assume "restart brokers one by one" covers everything if controllers run on dedicated nodes or a release requires controller updates before/after brokers.

## 6. Inventory Current State Before Upgrading

An upgrade plan should start with an **inventory**, not a deploy command.

| Group | What to Collect |
| --- | --- |
| Cluster | Kafka version of each broker/controller, cluster mode (KRaft/ZooKeeper), metadata feature level |
| Topology | Broker count, controller count, racks, partition counts, replication factor, ISR |
| Client | Language, `kafka-clients`/librdkafka version, Spring Boot/Spring Kafka versions |
| Java | JDK runtime, container image/base OS, TLS provider |
| Consumer | `group.id`, member count, assignment strategy, group protocol, static membership |
| Producer | `acks`, `enable.idempotence`, retries, transaction settings, compression |
| Topics | Partition counts, retention, min ISR, compaction, retry/DLT topology |
| Serialization | JSON/Avro/Protobuf, Schema Registry/subject compatibility, header conventions |
| Security | SASL/SSL, certificates, ACLs, OAuth, SCRAM, principal mapping |
| Operations | Alerts, lag dashboards, error rates, throughput, rollback windows |
| Dependencies | Connect, Streams, MirrorMaker, ksqlDB, admin clients, CDC components |

A Java application may pull in multiple Kafka-related libraries. Inspect the **runtime dependency tree**, not only directly declared versions in `build.gradle`.

### 6.1. Inspecting Java Client Dependencies

With Gradle:

```bash
./gradlew dependencyInsight \
  --dependency kafka-clients \
  --configuration runtimeClasspath
```

In Windows PowerShell:

```powershell
.\gradlew.bat dependencyInsight --dependency kafka-clients --configuration runtimeClasspath
```

These are **reference commands for learners to run themselves**, not mandatory build steps executed by this article. The output reveals which version of `org.apache.kafka:kafka-clients` actually resolves and whether overrides or conflicts exist. Whenever upgrading Spring Boot or Spring Kafka, re-check the dependency tree afterward.

### 6.2. Checking CLI Versions and Broker Capabilities

```bash
# Version of the Kafka CLI tools in use.
kafka-topics.sh --version

# API versions advertised by the broker.
kafka-broker-api-versions.sh \
  --bootstrap-server broker1:9092

# KRaft feature levels (when applicable to the release/cluster mode).
kafka-features.sh \
  --bootstrap-server broker1:9092 \
  describe
```

**`kafka-topics.sh --version` prints the CLI tool version**, not necessarily every broker's version in a mixed-version cluster. `kafka-broker-api-versions.sh` is useful for inspecting API capabilities, yet does not replace reading actual versions/configs from monitoring and release inventories.

For clusters using SASL_SSL/mTLS, CLI commands need a matching `--command-config client.properties`; protect that file since it references credentials/truststores. Never paste passwords into logs or tickets.

### 6.3. Inspecting Topics and Consumer Groups

```bash
kafka-topics.sh \
  --bootstrap-server broker1:9092 \
  --describe \
  --topic orders.events

kafka-consumer-groups.sh \
  --bootstrap-server broker1:9092 \
  --describe \
  --group orders-service
```

Capture baselines for partition leaders, ISR, consumer offsets, and lag. With many groups, automate inventory via appropriate admin tooling rather than checking just one sample topic.

## 7. Scenario A: Upgrade Brokers First, Keep Old Clients

This strategy is commonly chosen when a platform team manages the cluster and multiple applications upgrade on separate schedules.

```text
Before:
  Kafka cluster B1
       |---- Spring Kafka client C1
       |---- Python client P1
       +---- Kafka Streams S1

Broker phase:
  Kafka cluster B2
       |---- Spring Kafka client C1 (unchanged)
       |---- Python client P1 (unchanged)
       +---- Kafka Streams S1 (unchanged)

Later application phase:
  Kafka cluster B2
       |---- Spring Kafka client C2
       |---- Python client P2 on its own schedule
       +---- Kafka Streams S2 per its own plan
```

### 7.1. Prerequisites for Broker-First

1. All current client versions fall within the compatibility range supported by the target Kafka release.
2. No application relies on an API/behavior that was removed or changed without migration.
3. The cluster has sufficient replication, controller quorum, and capacity for a rolling restart.
4. Target broker binaries have been tested with current workloads/clients in staging.
5. Operations knows which stages allow binary rollback and which feature finalization steps limit reverting.
6. Kafka Connect/Streams/non-Java clients have also been accounted for.

### 7.2. Recommended Rollout Phases

```text
P0 Preflight: inventory + compatibility release notes + baseline
      |
      v
P1 Staging: prod-like cluster, B2 + C1, failure tests
      |
      v
P2 Select canary/batch brokers per upgrade guide
      |
      v
P3 Sequential rolling broker/controller upgrade, watching quorum/ISR
      |
      v
P4 Soak: client C1 running on B2, measuring functionality and reliability
      |
      v
P5 Finalize new cluster features once rollback is no longer needed
      |
      v
P6 Schedule subsequent upgrades per client group
```

Never restart all brokers simultaneously. A rolling restart can trigger leader elections, consumer rebalances, and producer retries; systems must handle **bounded disruption** rather than assuming zero errors.

### 7.3. During Mixed-Broker Versions

A new broker may lead a partition to which an old client produces; an old broker may still coordinate a consumer group. Monitor:

- Producer errors/latency, metadata refreshes, and retries.
- Leader elections, offline partitions, and ISR shrink/expansion.
- Consumer group rebalances, lag, and partition assignments.
- Transaction coordination and aborted transactions if applicable.
- Retry/DLT forwarding to target topics and ACL permissions.
- Cross-broker replication and network/disk saturation.

If SLOs breach thresholds, **halt the rollout** and investigate before continuing to the next node. Completing binary rollout alone is not a signal to raise feature levels immediately.

## 8. Scenario B: Upgrade Clients First, Keep Old Brokers

A client-first strategy fits when applications need CVE patches, Spring Boot/Spring Kafka upgrades for long-term support, or new client APIs while the platform is not ready to upgrade brokers.

```text
Before:
  Spring Boot S1 / Spring Kafka SK1 / kafka-clients C1
                       |
                       v
                  Broker B1

After client-first:
  Spring Boot S2 / Spring Kafka SK2 / kafka-clients C2
                       |
             protocol negotiation
                       |
                       v
                  Broker B1
```

Do not upgrade **only** the Kafka Java client via an arbitrary version override while ignoring the **Spring Kafka ↔ kafka-clients** compatibility matrix. A library binary API change can trigger `NoSuchMethodError`, `ClassNotFoundException`, or JVM startup errors even when the client could still speak the broker's wire protocol.

### 8.1. Safe Client-First Order

1. Determine the Java/JDK baseline of the target Spring Boot/Spring Kafka/Kafka clients.
2. Pick a version combination supported by Boot/Spring Kafka, preferring official dependency management.
3. Check whether old Kafka configurations remain valid, became deprecated, or changed defaults.
4. Run C2 integration tests against broker B1 without enabling B2-only features.
5. Canary a few application instances and monitor group rebalances, retry/DLT, and outputs.
6. Roll client instances per deployment policy without restarting the entire consumer group unnecessarily.
7. Retain C1 configs/binaries for rollback **before** introducing incompatible schema/message formats or application state changes.

### 8.2. Some New Client Features Still Require New Brokers

For example:

- A new consumer group protocol requires brokers/coordinators that understand that protocol.
- A new request API version may not be supported by older brokers.
- A new transaction, partition assignment, or authorization feature has broker-side dependencies.
- A new serializer/client can write payloads older consumers cannot read, regardless of broker version.

If the target client has a feature requiring broker B2, **keep that feature disabled** until after the broker upgrade, or choose broker-first. Never expect the client to silently fall back to old semantics once a feature is configured as required.

## 9. Spring Boot and Spring Kafka: Avoid Uncontrolled Dependency Overrides

In Spring Boot, `spring-kafka` and `kafka-clients` are typically managed by the BOM/dependency management. Illustrative Gradle snippet:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<BOOT_VERSION>'
    id 'io.spring.dependency-management' version '<PLUGIN_VERSION>'
}

dependencies {
    implementation 'org.springframework.kafka:spring-kafka'
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Both placeholders `<BOOT_VERSION>` and `<PLUGIN_VERSION>` must be replaced with versions **selected by your project per the support matrix**; this snippet illustrates dependency ownership, not a runnable verbatim `build.gradle`.

### 9.1. Why Avoid `force` on Kafka Client Versions?

Risky example:

```groovy
configurations.all {
    resolutionStrategy.force(
        'org.apache.kafka:kafka-clients:<ARBITRARY_VERSION>'
    )
}
```

If that Kafka client version falls outside the range tested by the target Spring Kafka release, application code may compile yet fail at runtime. Prefer to:

- Upgrade Spring Boot/Spring Kafka to a released, supported dependency set.
- Override only with explicit justification (e.g., security patch) permitted by release notes.
- Inspect **`runtimeClasspath`**, not only `compileClasspath`.
- Test against both the current broker and target broker.
- Document dependency override exceptions in an ADR and rollback plan.

### 9.2. Sample Spring Kafka Configuration for Compatibility Testing

Illustrative `application.yml` for string messages:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}

    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000

    consumer:
      group-id: orders-service
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      auto-offset-reset: earliest

    listener:
      ack-mode: record
```

These values are only an illustrative baseline. `enable.idempotence=true` requires full producer/client/broker support without conflicting settings. `acks=all` guarantees acknowledgment across the current ISR per broker policy; it **does not replace** business idempotency, nor does it mean Kafka can never lose data under every catastrophic scenario.

If the application already has a custom transaction/offset strategy, do not change ack mode or idempotence mid-migration just to match an example; measure exact current behavior before and after.

## 10. Consumer Group Rebalances During Rolling Client Upgrades

Every time an application instance restarts, the consumer group may rebalance or reassign partitions. When upgrading multiple instances, this can raise consumer lag, cause processors to re-receive records, or invoke side effects again.

```text
Group orders-service
  Instance A / client C1
  Instance B / client C1
  Instance C / client C1

Rollout:
  A -> C2 (B,C still C1)
  observe assignments and lag
  B -> C2 (A,C still running)
  C -> C2
```

**Do not assume two consumer client versions can always share a group under every assignment strategy.** Check `partition.assignment.strategy`, `group.protocol`, remote assignors, and Spring Kafka container configs to confirm the group protocol/assignor stays compatible while members are mixed.

### 10.1. Classic vs. New Consumer Group Protocol

Newer Kafka releases support a **new consumer group protocol** alongside classic mode, controlled by settings such as `group.protocol=consumer` on supporting clients. Whether it can be enabled depends on Kafka brokers/group coordinators and client versions.

Do not switch an entire group from classic to the new protocol **at the same time** as upgrading brokers/clients without dedicated testing. Treat changing group protocol as a **separate feature migration**, with its own plan for assignment behavior, metrics, compatibility, rollback, and accepted config values.

### 10.2. Cooperative Assignment and Static Membership

Strategies such as cooperative-sticky assignment and static membership (`group.instance.id`) can reduce rebalance disruption where suitable, yet:

- Settings must align across members in the same group.
- `group.instance.id` must be **unique** across instances; duplicate IDs cause fencing/errors.
- Kubernetes rolling deploys can overlap old and new Pods, requiring careful instance identity design.
- If a processor wrote a side effect without committing its offset before a rebalance, the record can still be redelivered.

Do not treat static membership as protection against business duplicates. It only governs group membership/assignment; business handlers must still be idempotent.

## 11. Producer Reliability When Brokers and Clients Upgrade Separately

After an upgrade, producers may change API version selection, compression, error mapping, or default settings (depending on version). Verify not only that messages reach the broker, but also **how the producer behaves when leaders change and requests retry**.

### 11.1. A Controlled Producer Baseline

```java
@Service
public class OrderPublisher {

    private final KafkaTemplate<String, String> template;

    public OrderPublisher(KafkaTemplate<String, String> template) {
        this.template = template;
    }

    public CompletableFuture<SendResult<String, String>> publish(
            String orderId, String payload) {
        return template.send("orders.events", orderId, payload);
    }
}
```

This snippet illustrates the `CompletableFuture` return type in modern Spring Kafka versions, requiring imports from `java.util.concurrent`, `KafkaTemplate`, and `SendResult`. When upgrading from older Spring Kafka releases, `KafkaTemplate.send` APIs/future types may change; **compile/runtime tests** must cover these call sites, not just broker integration tests.

Caller usage:

```java
publisher.publish("order-123", "{\"event\":\"CREATED\"}")
    .whenComplete((result, error) -> {
        if (error != null) {
            // Classify and log error; do not treat as sent.
        } else {
            // Broker acknowledged per producer config.
        }
    });
```

An `ack` from the Kafka producer does not prove downstream consumers executed business logic. If a record is re-published after a timeout by issuing a new application request, protocol-level producer idempotence may **not deduplicate** two independent business messages. Stable event IDs/outboxes per business contract are required.

### 11.2. Failure Paths to Test

| Scenario | What to Verify |
| --- | --- |
| Broker leader restart | Producer retries and recovers with no out-of-SLA output loss |
| Brief Kafka broker outage | Bounded timeouts; requests do not hang indefinitely |
| ISR drops below `min.insync.replicas` | `acks=all` producer rejects writes per durability policy |
| Request timeout after broker ack | App resolves unknown outcomes via event ID/idempotency |
| Large messages or compression changes | Broker/client configs do not fail serialization/record size |
| ACL or TLS changes | Producer authenticates/authorizes cleanly; clear error classification |
| Mixed broker versions | Zero abnormal API version/metadata refresh errors |

### 11.3. `acks=all`, ISR, and Downtime

`acks=all` combined with replication factor and `min.insync.replicas` forms part of the durability strategy. During a rolling broker upgrade, ISR can temporarily shrink while a replica restarts. If it drops below min ISR, producers may receive errors rather than accepting under-replicated writes.

This is typically **expected safety behavior per policy**, not a reason to immediately lower `min.insync.replicas` or enable unclean leader election. Weakening durability guards merely to keep a rollout error-free risks data loss.

## 12. Consumer Offsets and Acknowledgment Must Not Change Unintentionally

Upgrading a client does not mean changing `group.id`, ack mode, or offset reset policy. Those parameters dictate how the system resumes after restarts.

```text
Partition orders.events-0
offset:         100 101 102 103 104 105
                      ^
                 committed next offset = 101

Client C1 restarts as C2:
  if group.id and committed offset are preserved,
  the consumer resumes from the group's stored offset per protocol.

If group.id changes:
  it becomes a different group; initial offset follows auto.offset.reset
  or new seek policy, risking replay or missed data.
```

With `AckMode.RECORD`, commit strategies differ from `MANUAL`, `MANUAL_IMMEDIATE`, or Kafka transactions. Changing ack mode in the same upgrade makes attributing duplicates or data loss much harder.

### 12.1. Dangerous Crash Windows to Test

1. Handler completes a database side effect before committing the Kafka offset.
2. Process dies after polling a record before the handler commits its side effect.
3. A rebalance occurs during a slow processing callback.
4. Retry/DLT forwarding succeeds yet committing the source offset fails.
5. Consumer restarts with the old group ID but a changed deserializer configuration.

**At-least-once delivery** can redeliver records at several of these points. To prevent duplicates, use unique business keys, inbox/dedup stores, or transactional outboxes per architecture. A newer broker/client version does not automatically make HTTP/JDBC side effects exactly-once.

## 13. Kafka Transactions and Streams Need Dedicated Plans

For transactional producers or consumers using `isolation.level=read_committed`, the compatibility matrix must include:

- Transaction coordinator and `transactional.id` lifecycle.
- Commit/abort, fencing, and timeouts.
- Read-committed visibility when broker leaders change.
- Kafka transaction manager configuration in Spring Kafka.
- Sending offsets within transactions when matching EOS models.

Spring Kafka's non-blocking retry topics have limitations when combined with container transactions; do not enable `@RetryableTopic` in a transactional pipeline without checking version docs and choosing the right architecture.

### 13.1. Streams and Stateful Processing

Kafka Streams maintains task assignments, internal topics, changelogs, repartition topics, local state stores, and its own versioning mechanisms. Upgrading the `kafka-streams` library should not be treated like swapping `kafka-clients` in a stateless `@KafkaListener`.

Additional checks:

- Whether old and new Kafka Streams instances can coexist per the upgrade guide.
- Whether internal topic configs/replication/partitioning change.
- Whether local state restores properly from changelogs after restarts.
- Whether exactly-once processing mode remains compatible.
- Whether the new topology requires resetting application state or migrating store formats.

If you run only Spring Kafka record listeners, Streams tests are unnecessary. Yet a **cluster-wide broker upgrade** plan must inventory any Streams applications consuming that cluster.

## 14. Schemas and Serialization: Compatibility Independent of Brokers

Kafka brokers generally do not interpret a JSON `status` field or business Avro schema. Consequently, a broker upgrade can run smoothly while a new producer/consumer **breaks payload compatibility**.

Old JSON example:

```json
{
  "orderId": "O123",
  "amount": 100
}
```

New version:

```json
{
  "orderId": "O123",
  "amount": {
    "currency": "USD",
    "value": 100
  }
}
```

If an old consumer expects `amount` as an integer, it fails deserialization or business mapping. This is a **schema/application contract** change, not a Kafka wire protocol issue.

### 14.1. How to Evolve Payloads Safely

- Use a Schema Registry and appropriate compatibility mode (backward/forward/full) if using Avro/Protobuf/JSON Schema.
- Design additive fields with defaults or keep old formats during a transition window.
- Deploy consumers able to read both old and new formats before producers emit the new format, when appropriate.
- Test schema evolution against **messages saved from previous versions**, not just messages created by new producers and consumers together.
- Control `type headers`, trusted packages, and serializer configs when upgrading Spring Kafka.
- Include a message/event version in the business contract if schema registry metadata alone cannot express conversion logic.

For DLTs, if an old record fails deserialization, the new app must know how to read **raw bytes** or retain original metadata for investigation. Do not assume upgrading brokers automatically converts historical messages stored in Kafka.

## 15. Security and Java Runtime Can Break an Upgrade

A new client may fail to connect to an older broker due to **TLS/SASL** even when the Kafka request protocol is compatible.

| Component | Risk | Mitigation |
| --- | --- | --- |
| TLS | Cipher suites / certificate chains / hostname verification differ | Test TLS handshakes using the new runtime image |
| SASL SCRAM/PLAIN | Credentials or broker listener configs changed | Test auth in staging with real principals |
| OAuth/OIDC | Token audience/issuer/clock skew or client library changed | Smoke-test token refresh and reauthentication |
| ACLs | Retry/DLT topics, consumer groups, or transactional IDs lack permissions | Test both success paths and failure paths |
| Java version | Newer Spring Boot/Spring Kafka/Kafka client needs a newer JDK | Lock the Java/JDK matrix and container base image |
| Truststore/keystore | Path, password, JKS/PKCS12 format, or mount changed | Inspect image/deployment manifests |
| Network/DNS | Bootstrap brokers, advertised listeners, load balancers | Test connectivity to **every advertised broker**, not just bootstrap |

**Never grant wildcard ACLs or disable TLS hostname verification to "fix compatibility errors."** Pinpoint the exact config mismatch, fix the CA/listener/principal within scope, and audit changes.

### 15.1. Bootstrap Working Does Not Prove the Whole Cluster Is Reachable

Kafka clients contact bootstrap addresses initially, then receive metadata containing **advertised listeners for all brokers**. If a new app changes container networking, DNS, or certificate trust, it might connect to bootstrap yet fail when producing/consuming to another broker leader.

Smoke tests should send records across multiple partitions (via distinct keys or explicit partitions in test environments) to touch multiple leaders rather than sending one record to one partition.

## 16. Do Retry Topics and DLTs Change During Upgrades?

In Spring Kafka, non-blocking retries usually create **listener containers for retry and DLT topics** based on `@RetryableTopic` or `RetryTopicConfiguration`. Upgrading Spring Kafka can alter the number of retry topics, suffix/reuse naming, default fatal exception classifiers, container factories, or error handling depending on the release.

```text
Main topic            orders.events
Retry destinations    orders.events-retry-...
DLT                   orders.events-dlt

Spring Kafka version SK1
   |
   +-- backlog still sitting in SK1 retry topics

Deploy SK2 changing retry topic naming
   |
   +-- new listeners only read SK2 topics?
   +-- is SK1 backlog orphaned?
```

Upgrading **brokers only** does not require changing Spring Kafka retry topologies. When upgrading the **client stack**, however, inventory the retry topic graph and consumer groups:

1. List main/retry/DLT topics managed by the application.
2. Identify naming strategy, suffixes, topic reuse, and partition counts.
3. Check lag on each retry topic prior to deploy.
4. Compare listeners between old and new releases.
5. Keep a drain/migration mechanism for old backlogs if naming changes.
6. Test retryable records reaching destinations and non-retryable ones reaching the DLT per policy.
7. Test `KafkaTemplate` forwarding succeeds with new serializers/ACLs.

Never delete old retry/DLT topics simply because the app moved to a new version. They may hold **unprocessed work** even when the main topic lag is 0.

## 17. Compatibility Testing with a Staging Cluster

An `@EmbeddedKafka` environment is great for testing Spring listener wiring, yet **does not fully simulate a rolling upgrade of a multi-broker KRaft cluster**. To test true broker/client compatibility, use a production-like staging cluster:

- Appropriate broker/controller layout.
- Exact Kafka releases B1/B2.
- Production-like TLS/SASL/ACLs.
- Similar replication factor, `min.insync.replicas`, partitions, and retention.
- Consumer groups with multiple members to exercise rebalances.
- Retry topics and DLTs.
- A dataset of messages from older schema versions.

### 17.1. Functional and Reliability Test Matrix

| Test | B1 + C1 | B2 + C1 | B1 + C2 | B2 + C2 |
| --- | :---: | :---: | :---: | :---: |
| Producer send/ack | Baseline | Mandatory | Mandatory | Mandatory |
| Consumer receive/offset commit | Baseline | Mandatory | Mandatory | Mandatory |
| Restart/rebalance without data loss | Baseline | Mandatory | Mandatory | Mandatory |
| Exception → retry → success | Baseline | Mandatory if used | Mandatory if used | Mandatory if used |
| Retries exhausted → DLT | Baseline | Mandatory if used | Mandatory if used | Mandatory if used |
| Transaction commit/abort | Baseline | Mandatory if used | Mandatory if used | Mandatory if used |
| Old/new schemas | Baseline | Per contract | Mandatory when changing serializers | Mandatory |
| Security/ACL/TLS | Baseline | Mandatory | Mandatory | Mandatory |
| Rolling broker disruption | Per rehearsal | Mandatory in staging | N/A if client-only | Mandatory if combined |
| JDK/runtime startup | Baseline | Client unchanged | Mandatory | Mandatory |

If a cell falls outside a Kafka release's supported compatibility path, **do not try forcing tests to pass**: reorder the upgrade or insert an intermediate step. Base the matrix on release documentation, not merely a tiny single-topic test.

### 17.2. Spring Kafka Smoke Test with Real Producer/Consumer

Spring Boot 3.x + Spring Kafka 3.x example. The test connects to a **staging Kafka cluster** without spinning up an in-test broker.

Listener probe:

```java
package com.example.kafka.upgrade;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class UpgradeProbeListener {

    final BlockingQueue<String> received =
        new LinkedBlockingQueue<>();

    @KafkaListener(
        id = "upgradeSmokeListener",
        topics = "upgrade.smoke",
        groupId = "upgrade-smoke-consumer"
    )
    public void onMessage(String value) {
        received.add(value);
    }
}
```

Integration test:

```java
package com.example.kafka.upgrade;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.kafka.test.utils.ContainerTestUtils;

@SpringBootTest
class KafkaUpgradeSmokeTest {

    @Autowired
    KafkaTemplate<String, String> template;

    @Autowired
    KafkaListenerEndpointRegistry registry;

    @Autowired
    UpgradeProbeListener listener;

    @Test
    void producerAndConsumerCommunicateWithTargetBroker()
            throws Exception {

        MessageListenerContainer container =
            Objects.requireNonNull(
                registry.getListenerContainer("upgradeSmokeListener"));

        // Topic upgrade.smoke has 1 partition in this fixture.
        ContainerTestUtils.waitForAssignment(container, 1);

        String message = "upgrade-probe-" + UUID.randomUUID();
        template.send("upgrade.smoke", message, message)
            .get(10, TimeUnit.SECONDS);

        assertThat(listener.received.poll(10, TimeUnit.SECONDS))
            .isEqualTo(message);
    }
}
```

Prerequisites for running this test:

1. Topic `upgrade.smoke` is **pre-provisioned in staging** with one partition, and the principal holds `READ`/`WRITE` and group permissions.
2. Spring Boot test targets the right B1 or B2 broker per matrix cell; never point at production.
3. Group IDs/topics are **isolated** across parallel test runs, or use explicit cleanup and correlation. If a shared topic holds old records, the queue might receive an older record before the test message.
4. Producer and consumer use `StringSerializer`/`StringDeserializer` or consistent payload configs.
5. `KafkaListenerEndpointRegistry` registers the listener and the container receives assignment before sending.

This test **proves only basic produce/consume connectivity**; it does not prove durable offset commits, transactional semantics, retry/DLT, broker rolling restarts, or security across all listeners.

### 17.3. Crash/Replay and Idempotency Test

For event `order-123`, construct the scenario:

```text
Producer sends order-123, broker acks.
Consumer C1/C2 receives message.
DB commits order-123 result.
Consumer process dies before Kafka offset commit.
App restarts, message redelivers since offset was uncommitted.

Business expectation:
  processed_orders(order_id=order-123) has exactly 1 effect,
  retry/replay is logged,
  final committed offset advances to the right position.
```

To verify, DB output needs a **unique business key or idempotent upsert**, not merely asserting `@KafkaListener` ran once. If the handler invokes an external API, enforce an idempotency key or target state reconciliation.

### 17.4. Rebalance and Rolling Broker Test

In staging:

1. Start multiple members in the same consumer group.
2. Produce a set of records with unique event IDs spanning multiple partitions.
3. Rolling-restart a broker/controller per the upgrade guide.
4. Record rebalances, leader elections, lag, producer errors, and duplicate processing.
5. Repeat with old/new client versions.
6. Reconcile the **final set of business keys**: zero lost or duplicated effects.

If a CI test uses single-node Kafka Testcontainers, it cannot fully represent ISR or controller quorum verification during a rolling broker upgrade. Use a dedicated HA/staging environment for those failure modes.

## 18. Observability and Go/No-Go Criteria

Record baselines over representative load intervals, then compare during the rolling upgrade and once stabilized.

| Group | Signals to Observe | Meaning |
| --- | --- | --- |
| Broker | Offline partitions, under-replicated partitions, ISR shrink | Durability and availability |
| Controllers | Quorum health, metadata lag, elections | Is the control plane stable? |
| Producer | Send error rate, request latency p95/p99, retries, timeouts | Is the client hitting protocol/network/ISR errors? |
| Consumer | Group rebalance rate, commit failures, lag, fetch latency | Are consumers maintaining progress? |
| Application | Processing failures, side-effect duplicate conflicts, output completeness | Business reliability |
| Retry/DLT | Retry lag, oldest pending age, DLT arrivals | Are downstream errors hidden from main lag? |
| Security | SASL/TLS/authorization failures | Are principals/certs/configs compatible? |
| Resource | CPU, memory, GC, network, disk I/O | Any regressions or contention? |
| API compatibility | `UnsupportedVersionException`, unknown config/API errors | Is the client–broker pair missing capabilities? |

Specific metric/JMX names vary across Kafka versions and monitoring tools. Never hardcode dashboards to old-release metric names and conclude a disappearing metric means the broker is healthy. Align exporters/dashboards with the new version.

### 18.1. Sample Go/No-Go Gate

Table filled in by system owners with **real thresholds**:

```text
Gate G1: Controller quorum healthy                PASS/FAIL
Gate G2: OfflinePartitions = 0                     PASS/FAIL
Gate G3: ISR/reassignment within defined bounds    PASS/FAIL
Gate G4: Producer p99 latency < SLO                PASS/FAIL
Gate G5: Consumer lag recovers within SLA window   PASS/FAIL
Gate G6: Retry/DLT forwarding succeeds             PASS/FAIL
Gate G7: Business output reconciliation 100%       PASS/FAIL
Gate G8: Rollback path remains viable              PASS/FAIL
```

Do not impose arbitrary latency numbers like "p99 must be under 10 ms" across every cluster. For systems handling many partitions or cross-region replication, derive thresholds from baselines, SLOs, and concrete fault tolerances.

### 18.2. Alerts During Mixed Versions

Signals to halt rollout:

- Unstable controller quorum or inability to update metadata.
- Offline partitions or abnormally slow ISR recovery.
- Producers emitting bursts of errors/timeouts/authorization failures.
- Consumer groups rebalancing continuously or failing offset commits.
- Retry/DLT forwarding failures, rising lag alongside falling business success rates.
- Clients hitting API/protocol or schema incompatibilities.
- Outputs showing data loss or duplicates beyond policy.
- New broker processes failing to join the cluster due to incompatible config/feature levels.

Never keep upgrading the next broker just to hit a rollout percentage while data gates are failing.

## 19. Rollback: Broker Rollback Is Not Like Client Rollback

A good rollback has **pre-validated rollback conditions before deployment**.

### 19.1. Client Rollback

If only Spring Kafka/client code upgraded without changing payload schemas or business state, rollback usually means redeploying the previous image. Still check:

- Were consumer group IDs/offsets modified?
- Were new message formats published that old clients cannot read?
- Can the old version read Kafka Streams state/changelogs?
- Did retry/DLT topics change naming with remaining backlogs?
- Are database schema migrations compatible with old code?
- Did TLS/cert/secret rotations prevent the old image from connecting?

Thus "rolling back the Helm chart" is not always rolling back the data.

### 19.2. Broker Binary Rollback

If new broker binaries finished rolling while the cluster metadata feature level has **not yet** been raised and release docs permit reverting, binary rollback may still be viable following a supported sequence.

**Never blindly downgrade binary versions after raising `metadata.version` or enabling new features/record formats.** Some feature-level/metadata changes are irreversible directly; check release docs and tested snapshot/backup recovery procedures.

### 19.3. Plan A and Plan B

```text
Upgrade fails before feature finalization:
  Halt rollout
  → inspect cluster/clients
  → roll back binaries if release supports it
  → reconcile logs and outputs

Upgrade fails after feature finalization:
  Halt rollout
  → do not blindly downgrade binaries
  → follow release-specific recovery/migration path
  → preserve evidence and verify data
```

In both cases, never delete topics, reset consumer group offsets, or randomize `transactional.id` just to get applications "looking green" again.

## 20. Troubleshooting Common Post-Upgrade Errors

| Symptom | Hypothesis to Test | Resolution |
| --- | --- | --- |
| `UnsupportedVersionException` | Client uses API/feature unsupported by broker | Check `ApiVersions` and feature flags; change upgrade order or disable new feature |
| `NoSuchMethodError` / `ClassNotFoundException` | Spring Kafka/Kafka clients JAR binary mismatch | Compare `runtimeClasspath`, BOM, and dependency overrides |
| Producer reports `NotEnoughReplicas`/`NotEnoughReplicasAfterAppend` | ISR below policy threshold | Restore replicas/ISR; never lower durability blindly |
| Client connects to bootstrap yet send times out | `advertised.listeners`, DNS, TLS/leader access | Test reaching every broker; inspect metadata and networking |
| `TopicAuthorizationException` | New topic, retry/DLT ACL, or principal changed | Grant exact resource/action ACLs, no wildcards |
| Consumer group rebalances continuously | Incompatible assignment/group protocol or slow heartbeat/poll | Check member versions/configs and processing times |
| Offset commit failure | Coordinator/rebalance or commit policy changed | Inspect group state and ack mode; avoid skipping errors |
| Duplicate messages after rollout | At-least-once replay, retries, changed group ID, or non-idempotent writer | Reconcile business keys, offset timelines, and side effects |
| Main lag is 0 yet work is unfinished | Retry/DLT backlog | Inspect all retry destinations |
| Schema deserialization error | New producer changed payloads or headers | Restore compatibility using old fixtures |
| Kafka Streams fails to start | State store/internal topic or Streams API change | Follow Streams upgrade guide; never wipe state recklessly |
| New broker fails to join cluster | Feature level, controller quorum, or config incompatibility | Halt rollout; consult release guide and controller logs |
| New client reports TLS errors | JDK/truststore/ciphers/hostname validation | Fix trust chain and listeners while preserving security |

### 20.1. Do Not Blame Every Error on "Kafka Version Mismatch"

A `TimeoutException` can stem from broker overload, networking, DNS, ISR, or ACLs rather than wire protocol incompatibility. Conversely, an API compatibility issue typically surfaces clearly as `UnsupportedVersionException` or rejected configuration logs.

Effective debugging sequence:

1. Record **exact client version, broker version, and rollout timestamp**.
2. Capture stack traces/exact exceptions, correlation IDs, and relevant broker logs.
3. Verify Kafka APIs/feature levels and effective configurations.
4. Rule out networking, auth, topic/partition/ISR, and serialization.
5. Reproduce the same test case across B1/C1, B2/C1, B1/C2, and B2/C2.
6. Change only one version/config layer at a time when reproducing failures.

This prevents rolling back an entire cluster when the actual fault is a single `KafkaTemplate` using the wrong serializer after a Spring Boot bump.

## 21. Sample Upgrade Workflow for a Multi-Team System

Suppose an organization operates:

```text
Cluster orders-kafka
  3+ brokers, KRaft controllers, multiple topics and consumer groups

Applications:
  orders-api       : Spring Kafka producer
  billing-worker   : Spring Kafka transactional consumer
  reporting-worker : Spring Kafka consumer with retry/DLT
  audit-connector  : Kafka Connect
  fraud-pipeline   : Kafka Streams
```

A practical plan:

### Phase 1 — Lock Scope and Inventory

Lock the target broker release, existing Java clients, KRaft status, JDK requirements, and specialized application groups. Document upgrade paths accepted by Apache Kafka/Spring. Inventory all retry topics, Connect plugins, and Streams internal topics.

### Phase 2 — Staging Compatibility Matrix

Run the B1/C1 baseline and both transitional states B2/C1 and B1/C2 where supported. Test not only the `orders-api` producer, but also billing transactions, reporting DLT, Connect, and Streams state recovery.

### Phase 3 — Broker Rolling Upgrade

Upgrade strictly per controller/broker guide, a small batch at a time. Each step gates on controller quorum, leader elections, ISR, produce/consume, and consumer lag. Hold metadata feature levels at a release-safe level during the rollback window.

### Phase 4 — Soak with Existing Clients

Run existing workloads under representative traffic, observing real records, retry failures, transaction aborts, and schema payloads. Proceed to feature finalization only with sufficient evidence if needed.

### Phase 5 — Upgrade Clients per Application

Upgrade lower-risk groups first (such as stateless producers/consumers), followed by transactional consumers and Kafka Streams after specialized testing. Use rolling deployments to minimize rebalances; protect `group.id`, assignments, and ack behavior.

### Phase 6 — Treat New Features as Separate Changes

Enable new consumer group protocols, compression/record format changes, metadata feature levels, or retry topic naming in **separate change requests**, each with its own compatibility matrix and rollback plan. Never bundle "switch protocol + upgrade broker + upgrade Spring Boot + change schema" into one hard-to-debug ticket.

### Phase 7 — Reconcile and Close the Change

Reconcile received business events, completion status, pending retries, DLT/quarantine, final outputs, and lag. Confirm no old retry topics were orphaned, no consumer groups lost offsets, and operational docs reflect the new release versions.

## 22. ADR Template and Pre–Go-Live Checklist

A concise **Architecture Decision Record**:

```markdown
# ADR: Independent Kafka Broker and Spring Kafka Client Upgrade

## Context
- Current Kafka cluster: B1, KRaft mode.
- Current Spring Boot / Spring Kafka / kafka-clients: S1/SK1/C1.
- Target broker: B2; subsequent target client: C2.
- Billing uses transactions; reporting uses retry/DLT.

## Decision
- Upgrade broker-first if B2 + C1 falls inside the compatibility window.
- Freeze client configs and business schemas during broker rollout.
- Execute staging compatibility matrix and failure tests beforehand.
- Finalize metadata feature level only after soak and rollback window.
- Upgrade Spring Kafka/clients per service without forcing JAR overrides.

## Consequences
- Requires additional staging, test cluster, and monitoring time.
- Mixed versions exist only within the supported upgrade window.
- Client rollback depends on messages/schemas and application state.

## Validation
- Controller quorum, ISR, produce/consume, transactions, retry/DLT.
- Consumer rebalances, lag recovery, and business idempotency.
- Test evidence for B1+C1, B2+C1, B1+C2, and B2+C2.
```

Version labels are placeholders, not an official support matrix. Replace them with exact release numbers and links to your project's release notes.

### Deployment Checklist

| Question | Required Condition |
| --- | --- |
| Are actual broker/client versions known? | Inventory of every broker/controller and every app runtime |
| Were release notes checked for the upgrade path? | No extrapolating from generic major versions |
| Is cluster mode confirmed? | KRaft/ZooKeeper, migration prerequisites |
| Is there a `metadata.version`/feature finalization plan? | Separated from binary upgrade; rollback limits understood |
| Do controller quorum and ISR have enough headroom? | Rolling restarts do not breach availability/SLOs |
| Was B2+C1 tested before broker-first? | Evidence for producer, consumer, errors, transactions |
| Was B1+C2 tested before client-first? | No unsupported broker-only features enabled |
| Are Spring Boot/Spring Kafka BOMs compatible? | Verified runtime dependency tree and JDK |
| Are `group.id`/assignment/ack modes preserved? | No unintended replays or skipped records |
| Was side-effect idempotency tested? | Redelivery/rebalance does not duplicate business output |
| Is the retry/DLT topic graph preserved? | No lost backlogs or forwarding permissions |
| Do producers/consumers have full ACL/TLS? | Smoke tests run with production-like identities |
| Were old/new schemas tested? | Consumers process payloads from prior releases |
| Are go/no-go metrics monitored? | Alerts on quorum, ISR, lag, errors, DLT, and data checks |
| Is a rollback plan ready before feature finalization? | Point of no return and evidence to retain documented |
| Is a runbook ready for hard failures/recovery? | Halt rollout and follow release-specific guide |

## 23. Conclusion

Kafka is designed so **brokers and clients can evolve relatively independently** through API version negotiation, yet that capability has limits and must be verified for **actual version pairs**. A Java client may still talk to a new broker while a Spring Kafka feature, Kafka Streams state, consumer group protocol, or payload schema proves incompatible.

To upgrade safely:

1. Separate **broker binaries**, **KRaft metadata feature levels**, **Kafka Java clients**, and the **Spring Boot/Spring Kafka stack** into distinct change layers.
2. Build the **B1/C1, B2/C1, B1/C2, B2/C2** matrix and choose broker-first or client-first based on real compatibility.
3. Upgrade clusters via **rolling upgrades per release guide**, protecting controller quorum, ISR, and business outputs.
4. Upgrade applications per service, avoiding changing group IDs, schemas, retry naming, transactions, and client versions all at once.
5. Test **failure paths, retry/DLT, rebalances, transactions, and idempotency**, not merely a producer sending one message successfully.
6. Finalize cluster features only after gathering sufficient evidence and understanding rollback limits.

In **Spring Kafka Reliability Operations**, a successful upgrade is not defined by every Pod and broker running a new binary. It is defined by **maintaining processing, preserving messages and business effects, keeping failures observable, and having an explainable, rehearsed recovery path**.

## References

- [Apache Kafka Documentation](https://kafka.apache.org/documentation/): client protocol, brokers, consumer groups, configuration, security, and upgrade guides.
- [Apache Kafka — Upgrade Guide](https://kafka.apache.org/documentation/#upgrade): prerequisites and upgrade order per Kafka release.
- [Apache Kafka — Protocol Guide](https://kafka.apache.org/protocol.html): API versions, requests/responses, and wire protocol compatibility.
- [Apache Kafka — KRaft](https://kafka.apache.org/documentation/#kraft): controller quorum and cluster metadata in KRaft.
- [Spring for Apache Kafka Reference](https://docs.spring.io/spring-kafka/reference/): `KafkaTemplate`, listener container, acknowledgment, transactions, retry topics, and testing APIs.
- [Spring Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html): scope of Kafka transactions/EOS and related limits.
- [Spring Kafka — Non-Blocking Retries](https://docs.spring.io/spring-kafka/reference/retrytopic.html): retry/DLT topology and operational limits.
- [Spring Kafka — Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html): `@EmbeddedKafka`, test utilities, and integration tests.
- [Spring Boot — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html): auto-configuration, Kafka properties, and dependency integration.
- [Gradle Dependency Management](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): inspecting resolved runtime dependency trees when upgrading Kafka clients.
