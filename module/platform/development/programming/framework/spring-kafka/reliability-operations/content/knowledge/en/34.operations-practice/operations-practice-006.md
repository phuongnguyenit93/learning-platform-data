# Simulating Broker Disconnection in Spring Kafka

## 1. Lab Objectives

In production, a Spring Kafka application can lose its connection to a broker while producing or consuming messages. Causes include broker restarts, network glitches between pods and Kafka, misconfigured DNS/routing, load balancers closing idle connections, a partition leader dying, or a partial cluster isolation. The Kafka client has built-in reconnect and retry mechanisms, yet **automatic reconnection does not mean every message was processed strictly once with zero ambiguous outcomes**.

For example, a `payment-events` service receives `eventId=evt-103`, updates business tables, and prepares to commit its Kafka offset. Right after the database commits, the broker connection drops. Once connectivity returns, another consumer may reread that same event if the offset commit never succeeded. Without idempotency, a brief connectivity blip can create duplicate processing.

```text
Producer app                       Kafka cluster                 Consumer app
     |                                   |                             |
     |--- send(eventId=evt-103) -------->|                             |
     |<-- ACK or uncertain outcome ------|--- poll(event) ------------>|
     |                                   |                             |-- DB commit
     |                     [BROKER DISCONNECTED]                       X-- offset commit?
     |                                   |                             |
     |                   [CONNECTION RESTORED]                         |
     |                                   |--- possible redelivery ---->|
     |                                   |                             |-- check idempotency
```

This lab targets six concrete outcomes:

1. **Induce controlled failures**: stop a local broker or sever client network paths via a proxy in a test environment.
2. **Observe producer behavior**: reconnects, retries, futures completing successfully or exceptionally, or hitting deadlines.
3. **Observe consumer behavior**: polling, group rebalancing, pauses during connection errors, and resuming consumption after recovery.
4. **Evaluate durability and offsets**: distinguish broker record persistence, producer ACK receipt, consumer business completion, and committed offsets.
5. **Verify business outcomes**: no confirmed event is dropped and no unexpected duplicate side effects occur.
6. **Author an operations runbook**: know when to wait for self-recovery, when to fix configuration/ACLs, and when to intervene.

**Safety boundary:** the stop/kill/network-cut commands in this lesson **are strictly for isolated test Kafka instances, local/container clusters, or authorized chaos testing environments**. Never run them against production Kafka, shared clusters, or hosts serving unrelated workloads.

## 2. Not Every "Lost Broker" Scenario Is Identical

| Scenario | Is the Broker Actually Dead? | Likely Behavior |
|---|---|---|
| Docker broker container stopped | Yes, broker process exits. | Clients attempt reconnects; leader/coordinator may vanish. |
| Network cut from **one application** to Kafka | No; broker keeps serving other clients. | Only that client loses access; other group members may keep running. |
| One broker in a 3-node cluster dies | Yes, one node stops. | Partitions with eligible replicas elect a new leader; clients fail over. |
| All broker nodes unreachable | Cluster unavailable from client's view. | Produce/poll/commit calls stall or fail on deadlines. |
| Broker alive, `advertised.listeners` wrong | No. | Bootstrap may succeed, then client receives an unreachable endpoint. |
| DNS fails to resolve broker hostname | Not necessarily. | Client cannot reach host or open new connections per DNS policy. |
| Invalid ACLs or credentials | No. | Authentication/authorization error; often fatal rather than transient network. |
| Consumer has no new messages | No. | Normal idle state; does not prove Kafka is down. |

**Separate three verification layers:** (1) broker process/cluster health; (2) connectivity to the right brokers from **the client's network namespace**; (3) correctness of business processing and offsets after recovery. A `ping` or open TCP port check alone does not verify all three layers.

### 2.1. One Broker Differs from a Replicated Kafka Cluster

In a single-broker lab with replication factor 1, stopping the broker makes essentially the entire topic unavailable. In a three-broker cluster with `replication.factor=3`, killing one node may only cause a brief leader election if remaining replicas qualify. Therefore:

- A **single-broker** lab is suitable for learning producer timeouts, client reconnects, and recovery after full broker outages.
- A **multi-broker** lab is required to test leader failover, in-sync replicas (ISR), `acks=all`, `min.insync.replicas`, and partial cluster loss.
- A **per-client network cut** lab is ideal for isolating a single service while the broker stays up, especially using Toxiproxy or a similar network proxy.

Never treat a passing single-broker test as proof that a production cluster survives losing a node, or vice versa.

## 3. Understanding `bootstrap.servers` and `advertised.listeners` Before Injecting Faults

The Kafka client uses `bootstrap.servers` to make an initial connection and fetch **cluster metadata**. Afterward, producers and consumers connect directly to partition leaders and the coordinator using addresses published in `advertised.listeners`.

```text
Spring Kafka app
  bootstrap.servers = broker-a:9092,broker-b:9092
                |
                v
         Bootstrap broker
                |
          Metadata response:
            node 1 = kafka-a:9092
            node 2 = kafka-b:9092
            node 3 = kafka-c:9092
                |
                v
     Client opens connections to advertised addresses
```

Key implications for this lab:

- If you only route the **bootstrap port** through a proxy while the broker advertises **direct** Kafka addresses, the client bypasses the proxy right after metadata lookup. Network-cut tests will produce misleading passes.
- Under Docker, a hostname like `kafka:9092` resolves only inside the Docker network; apps running on a Windows/Linux host may need `localhost:<mapped-port>` or another advertised endpoint.
- Listing multiple bootstrap servers gives the client multiple entry points to the cluster; it **does not give topics replication** and does not ensure failover if leaders/ISR are insufficient.
- `bootstrap.servers` does not need every broker listed, though production should supply multiple valid endpoints to avoid relying on a single bootstrap host.

**Requirement for realistic network tests:** every Kafka connection path the client can use during the experiment must pass through the fault-injection point. Inspect bootstrap hosts, advertised endpoints, leader/coordinator addresses, and fallback routes rather than assuming one closed socket means all of Kafka is unreachable.

## 4. Preparing a Reproducible Lab Environment

### 4.1. Minimal Scope

A compact setup includes:

| Component | Suggested Setup | Purpose |
|---|---|---|
| Local Kafka broker | One Apache Kafka 3.9.1 container on Docker | Practice single-broker outage. |
| Spring Boot app | Java 17+, Spring Boot 3.x, Spring Kafka 3.x | Producer, listener, and client observation. |
| Topic | `orders.outage.lab`, 1 partition, replication factor 1 | Easy observation of offsets and ordering. |
| Consumer group | `outage-lab-workers` | Preserves offsets across app restarts if broker storage persists. |
| Business store | Test DB with unique `eventId` or fake idempotent store | Verifies duplicate side effects. |
| Monitoring | Timestamped logs, counters, Kafka client/consumer metrics | Compare before, during, and after outage. |

Never reuse topics or groups serving production jobs. In CI or shared machines, pick unique topic and group names per test run to avoid leftover offsets from other tests.

### 4.2. Running a Local Broker with Docker

Per Apache Kafka 3.9.x Docker guidance, the official JVM image can start locally with default settings. In a Docker-enabled shell:

```bash
docker run -d --name kafka-outage-lab \
  -p 9092:9092 \
  apache/kafka:3.9.1

docker ps --filter name=kafka-outage-lab
docker logs --tail=100 kafka-outage-lab
```

This is a **local lab broker**; if port 9092 is already occupied, update and align the listener mapping as supported by the image rather than only remapping the host port and assuming metadata matches. On Docker Desktop or different OSes, verify the actual bootstrap address used by the Spring app.

Create the topic using the CLI inside the container image:

```bash
docker exec kafka-outage-lab /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create --if-not-exists \
  --topic orders.outage.lab \
  --partitions 1 \
  --replication-factor 1

docker exec kafka-outage-lab /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe --topic orders.outage.lab
```

The `/opt/kafka/bin` path reflects the Apache Kafka image layout; adjust if using another image. Run the producer and consumer in a **Spring Boot process outside the broker container**; if you run test clients inside the broker container and stop it, the clients die too and you cannot observe reconnects.

### 4.3. Data Persistence and Cleanup

`docker stop` / `docker start` on **the same container** preserves its writable layer and attached volumes, making it suitable for short recovery tests. However, `docker rm`, `docker compose down -v`, or creating a fresh container without keeping the data volume **wipes logs and committed offsets**. To test persistence across container recreation, mount an explicit volume with consistent cluster/KRaft metadata.

When finished with the lab:

```bash
docker stop kafka-outage-lab
docker rm kafka-outage-lab
```

Run cleanup only after confirming `kafka-outage-lab` is your temporary test container holding no data you need to keep. Never run wildcard cleanup or delete Docker volumes in shared environments.

## 5. Spring Boot Producer and Consumer Configuration for Observability

Example `src/main/resources/application-lab.yml`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092

    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 15000
        request.timeout.ms: 3000
        max.block.ms: 5000
        retry.backoff.ms: 200
        reconnect.backoff.ms: 200

    consumer:
      group-id: outage-lab-workers
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      enable-auto-commit: false
      auto-offset-reset: earliest
      properties:
        session.timeout.ms: 10000
        max.poll.interval.ms: 300000

    listener:
      ack-mode: record
      idle-event-interval: 10s

logging:
  level:
    root: INFO
    org.apache.kafka.clients.NetworkClient: WARN
    org.springframework.kafka: INFO
```

Short timeouts speed up lab tests; **never copy them verbatim into production**. `delivery.timeout.ms` must be at least `request.timeout.ms + linger.ms` and long enough for outages the application is expected to ride out. Setting it too low causes producers to fail on brief network blips even if the broker recovers seconds later.

Spring Boot loads `application-lab.yml` only when the `lab` profile is active (`spring.profiles.active=lab` or equivalent). For consumer groups and offsets, `auto-offset-reset=earliest` applies only when there is no valid committed offset; it does not force an existing group to reread from the beginning.

**Security warning:** this lab uses PLAINTEXT and String serializers only. For Kafka with SASL/TLS, manage secrets and keystores through a secret management system. Never disable TLS verification or log credentials to "fix" connection errors.

### 5.1. Producer with Explicit Success/Failure Signals

Spring Kafka 3.x returns `CompletableFuture<SendResult<K,V>>` from `KafkaTemplate.send(...)`:

```java
import java.util.concurrent.CompletableFuture;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class OutageLabProducer {

    private static final Logger log =
            LoggerFactory.getLogger(OutageLabProducer.class);

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OutageLabProducer(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, String>> publish(
            String eventId, String payload) {

        CompletableFuture<SendResult<String, String>> send =
                kafkaTemplate.send("orders.outage.lab", eventId, payload);

        send.whenComplete((result, error) -> {
            if (error != null) {
                log.warn("kafka.produce.failed eventId={} errorType={}",
                        eventId, error.getClass().getSimpleName());
            } else {
                log.info("kafka.produce.acked eventId={} partition={} offset={}",
                        eventId,
                        result.getRecordMetadata().partition(),
                        result.getRecordMetadata().offset());
            }
        });

        return send;
    }
}
```

Keep two outcome layers distinct:

- `KafkaTemplate.send(...)` can block or throw **before returning a future** while awaiting metadata/buffer space or hitting config errors; `max.block.ms` bounds some of those cases.
- Once a future is returned, the **asynchronous** outcome depends on producer ACKs, retries, and `delivery.timeout.ms`. `.whenComplete(...)` observes the outcome. Calling `send()` alone does not prove the record reached the broker.
- If caller code invokes `future.get(3, TimeUnit.SECONDS)` and hits `TimeoutException`, that is only the **caller's wait timing out**; the producer future may continue and succeed later. Never treat every caller timeout as proof Kafka failed to write the record.
- Even when the producer catches an exception after timeout, the network boundary can leave an **ambiguous ACK/outcome**. If the application retries at the business layer, use a stable event ID and downstream idempotency.

### 5.2. Consumer Completing Business Work Before ACK

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OutageLabConsumer {

    private final IdempotentOrderService orderService;

    public OutageLabConsumer(IdempotentOrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            id = "outageLabConsumer",
            topics = "orders.outage.lab",
            groupId = "outage-lab-workers")
    public void consume(ConsumerRecord<String, String> record) {
        String eventId = record.key();

        // This method must commit business changes before returning.
        orderService.applyOnce(eventId, record.value());

        // AckMode.RECORD: container handles offset commit after callback.
    }
}
```

`IdempotentOrderService` is an application-built component, not a built-in Spring Kafka class. For PostgreSQL, you can enforce a unique constraint on `event_id`, persisting the marker and business update **in the same transaction**; if the marker already exists, skip duplicate side effects per business rules.

```sql
CREATE TABLE processed_event (
    event_id VARCHAR(128) PRIMARY KEY,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Inside the same transaction as the business update:
INSERT INTO processed_event (event_id)
VALUES (:eventId)
ON CONFLICT (event_id) DO NOTHING;
```

The service must check whether the insert created a new row. Inserting a unique marker and still applying balance updates unconditionally is **not idempotent**. If two deliveries share `eventId` with different payloads, add conflict detection rather than silently swallowing them.

## 6. What Does a Producer Do When a Broker Disconnects?

The Kafka producer manages metadata, buffers, request retries/backoff, and delivery deadlines. It normally attempts to reconnect on recoverable network errors; depending on outage duration and deadlines, some `send` calls may fail.

| Property | Effect | Common Misconception |
|---|---|---|
| `bootstrap.servers` | Endpoints for initial cluster discovery. | Not the exclusive list of brokers the producer talks to forever. |
| `acks=all` | Requires ACKs per topic ISR/durability policy. | Does not automatically make consumer side effects exactly-once. |
| `enable.idempotence=true` | Prevents duplicates from **internal retries within the same producer session** per producer protocol. | Does not deduplicate when the app calls `send()` again for the same business event. |
| `delivery.timeout.ms` | Overall deadline to report success or failure after `send` accepts a record. | Not the same as `future.get()` timeout. |
| `request.timeout.ms` | Wait time for a single request response; eligible for retry if configured. | Not the total budget across all retries. |
| `max.block.ms` | Bounds blocking on metadata/buffer in `send()` and synchronous producer APIs. | Does not bound business callback execution time. |
| `reconnect.backoff.ms` | Delay between connection retry attempts. | Does not guarantee instant reconnection the moment a broker starts. |
| `retry.backoff.ms` | Delay between retriable requests. | Does not replace `delivery.timeout.ms` or business limits. |
| `max.in.flight.requests.per.connection` | Unacknowledged requests allowed per connection. | With idempotence, must satisfy client constraints; invalid settings error or affect ordering. |

### 6.1. Illustrative Timeline

```text
T+0s:  producer.send(event-1) -> ACK succeeds
T+2s:  connection to broker lost
T+3s:  producer.send(event-2) -> buffered or awaiting metadata
T+4s:  Kafka client begins reconnect/retry
T+18s: event-2 hits delivery timeout (e.g., 15s from send)
        -> future completes exceptionally
T+20s: broker connectivity restored
T+21s: producer.send(event-3) -> can ACK successfully
```

This timeline is illustrative; exact timing depends on metadata, batch queues, network conditions, broker startup, and client settings. In particular, **you cannot conclude `event-2` is absent from Kafka** simply because the caller timed out: if the ACK was lost after the broker appended the record, the producer sees an ambiguous failure.

### 6.2. Kafka Client Retries vs. Application-Level Retries

Inside the Kafka client, internal retries paired with an idempotent producer prevent batch-resend duplicates during transient faults. Yet if the application catches an exception and invokes `publish(eventId, payload)` again as a fresh producer operation, that is **a separate business send** and can append a new record to the topic.

Therefore, for critical events:

- Attach an **immutable business event ID** to the key/header/payload.
- Persist publish status in an outbox or durable coordinator rather than only in RAM.
- Allow consumers to process the same event ID safely on redelivery.
- During reconciliation, check destination state instead of guessing from callback timeouts.

## 7. What Does a Consumer Do When a Broker Is Lost?

A `@KafkaListener` runs inside a Spring Kafka container calling `poll()` on the Kafka client. When the broker connection drops, the consumer logs connection errors and attempts to reconnect, resuming polling or rejoining the group once the broker returns. However, **there is no single callback guaranteed to fire instantaneously when a broker disconnects**.

Key components involved:

| Component | Role During Outage |
|---|---|
| `KafkaConsumer.poll()` | Fetch loop and group heartbeat driver; reacts based on connectivity and metadata. |
| Group coordinator | Manages membership and committed offsets; coordinator may move if a node dies. |
| Partition leader | Broker serving fetches for a partition; losing the leader triggers election. |
| `session.timeout.ms` | Duration after which the group may consider a member dead under applicable conditions. |
| `max.poll.interval.ms` | Maximum gap between polls; overly slow business work also triggers rebalances. |
| `enable.auto.commit` and `AckMode` | Controls when offsets are committed. |
| `DefaultErrorHandler` | Handles listener/record exceptions per policy; not a dedicated handler for every broker disconnect. |
| `KafkaListenerEndpointRegistry` | Inspects and controls listener container lifecycle. |

### 7.1. Where Does the Consumer Resume When Connectivity Returns?

The consumer resumes based on assignment, position, and **committed offsets**; if it lost group membership or had to reinitialize, it restarts from the last valid committed offset. This yields *at-least-once* delivery: a record whose business work finished while its offset commit failed can be redelivered.

```text
offset 40: business DB processed, Kafka committed offset = 41
offset 41: business DB processed, offset commit 42 failed
                      |
                 broker outage
                      |
           consumer group recovers
                      |
           may redeliver offset 41
```

Never use `@KafkaListener` invocation counts as the unique count of business events. Compare the **set of event IDs** confirmed at the source against your output tables or idempotency markers, while checking lag and committed offsets in tests.

### 7.2. Do Not Confuse Idle with Broker Disconnection

Spring Kafka can emit `ListenerContainerIdleEvent` when `idleEventInterval` is enabled and no records arrive. Yet **a healthy empty topic also emits idle events**. `NonResponsiveConsumerEvent` is a separate signal indicating `poll()` has not returned within the monitor threshold—not a universal detector for every outage.

Losing broker connectivity **does not necessarily emit `ConsumerStoppedEvent`**. The consumer may keep running and reconnecting; `ConsumerStoppedEvent` typically fires when the container actually stops. Thus, no single Spring application event serves as a complete health check.

### 7.3. Authentication/Authorization Differs from Network Errors

`AuthenticationException` and `AuthorizationException` usually require checking secrets, ACLs, certificates, and policies; by default they can stop the container unless an appropriate auth retry setting is configured. Spring Kafka provides `authExceptionRetryInterval` for cases where credentials/permissions may be fixed while the container stays alive—**it is not a fix for network outages**.

Never raise retries endlessly for invalid credentials or disable TLS validation just to watch a consumer reconnect. Classify errors in logs and fix the real endpoint or ACL issue.

## 8. Lab A — Stopping and Restarting a Local Broker

This is the simplest scenario to observe a **full broker** outage using a single-node lab.

### 8.1. Before Injecting Faults

1. Start the `kafka-outage-lab` container and create the topic per section 4.
2. Start the Spring Boot app with the `lab` profile (the client must run outside the broker container).
3. Send `eventId=before-001` and wait for the producer future ACK.
4. Wait for the consumer to process it and verify the business marker `before-001` was written once.
5. Record baseline Kafka client metrics, consumer group lag, timestamps, and the bootstrap endpoint in use.

### 8.2. Inducing the Outage

In a terminal managing the **test container**:

```bash
# Stop broker using normal shutdown:
docker stop kafka-outage-lab

docker ps -a --filter name=kafka-outage-lab
```

`docker stop` sends a termination signal with a grace period before killing the process. If you want to simulate an **abrupt broker crash** in a separate test, use:

```bash
# Test container ONLY; differs from graceful stop:
docker kill kafka-outage-lab
```

Do not run both commands back-to-back for the same incident. Once a container is stopped with `docker stop`, `docker kill` does nothing extra. An abrupt crash can have different leader/coordinator recovery behavior than graceful shutdown; document which scenario you ran.

### 8.3. Observing Producer and Consumer During the Outage

While the container is stopped:

- Call `publish("during-001", payload)` from the Spring app and record when the future completes or times out.
- Inspect exception classes and logs; distinguish caller `TimeoutException` from a producer future completing exceptionally.
- Check whether the consumer stays running or stops, and inspect connection warnings, group assignments, and offset commits.
- Never infer lost records merely from missing ACKs; recheck after the broker recovers.
- If `KafkaTemplate.send(...)` blocks on metadata/buffer space, observe `max.block.ms` and thread pools rather than spawning unbounded parallel sends.

**Not every send must fail the instant the broker stops**; producers buffer, retry, and obey timeouts. For an outage longer than the delivery deadline, expect sends to terminate in failure, with exact errors depending on timing and configuration.

### 8.4. Recovery and Reconciliation

```bash
docker start kafka-outage-lab
docker ps -a --filter name=kafka-outage-lab
docker logs --tail=100 kafka-outage-lab
```

After the broker reports ready:

1. Wait for the producer to send **a new message** `after-001` and receive an ACK.
2. Wait for the consumer to read `after-001` and the business store to confirm processing.
3. Reconcile `during-001`: it may have failed cleanly, succeeded just before/during the outage, or ended in an ambiguous client state. Reconcile by event ID and business rules.
4. Check whether the consumer committed offset advances after processing; if the group rebalanced, record the duration.
5. Verify lag returns to baseline within an acceptable window.

**Lab completion criteria:** the producer successfully sends new messages after recovery, the consumer resumes processing, outputs contain all contractually confirmed events, and zero duplicate business side effects exist. Reconnect warnings disappearing from logs is a supporting indicator, not the sole final assertion.

## 9. Lab B — Cutting Only Client Networking with Toxiproxy

In Lab A, the broker actually died. In production, another common failure is **the broker remains healthy while one application loses connectivity** due to firewalls, routing, sidecars, or network partitions. To reproduce this cleanly, put Toxiproxy as a TCP proxy between the app and Kafka.

```text
Spring Boot client
    |
    | bootstrap + all broker connections in test scope
    v
Toxiproxy (TCP port with cut/latency injection)
    |
    v
Kafka broker in Docker network

T+0: proxy active => normal producer/consumer
T+1: cut upstream and downstream => client cannot see Kafka
T+2: producer timeout / consumer reconnect
T+3: restore proxy => client reconnects
```

Advantages over `docker stop`:

- The broker stays alive with intact logs and cluster state.
- You can isolate only Producer A, Consumer B, or a subset of clients.
- You can inject latency, jitter, timeouts, packet fragmentation, or bandwidth caps.
- You can restore traffic instantly by removing toxics without waiting for broker boot.

### 9.1. The Most Important Requirement: Kafka `advertised.listeners`

Kafka does not use the bootstrap server as the sole traffic destination. If your app bootstraps via `toxiproxy:8666` while the broker advertises `broker:9092` and the app can reach `broker:9092` directly, the test **no longer intercepts all Kafka traffic**.

```text
Wrong:
  client -> proxy -> broker bootstrap
  client <- metadata broker=broker:9092
  client -----------------> broker:9092 (bypasses proxy)

Right:
  client -> proxy -> broker bootstrap
  client <- metadata broker=proxy-address
  client -> proxy -> broker leader/coordinator
```

Therefore, configure a listener on the broker whose **advertised endpoint points back to the proxy** for test clients. In multi-broker clusters, route and control **every advertised broker endpoint** under test rather than putting a proxy on one address and assuming the entire group is isolated.

### 9.2. Dependencies for Spring Boot Integration Tests

Gradle Groovy example using Spring Boot's BOM and compatible Testcontainers modules:

```groovy
dependencies {
    implementation 'org.springframework.kafka:spring-kafka'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:testcontainers-kafka'
    testImplementation 'org.testcontainers:testcontainers-toxiproxy'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Testcontainers artifact names, packages, and overloads vary across major versions. The next snippet uses Testcontainers APIs supporting `org.testcontainers.kafka.KafkaContainer.withListener(listener, advertisedListenerSupplier)` and `ToxiproxyContainer`. **Align all Testcontainers modules to the same BOM/version** and verify `withListener` against your version; never mix incompatible Testcontainers 1.x and 2.x releases.

### 9.3. Illustrative Toxiproxy Fixture

The Java snippet below shows **how to wire the fixture**, not a standalone test class runnable without Spring context, topics, assertions, and lifecycle cleanup. Its purpose is demonstrating how the broker listener advertises the proxy address:

```java
import eu.rekawek.toxiproxy.Proxy;
import eu.rekawek.toxiproxy.ToxiproxyClient;
import eu.rekawek.toxiproxy.model.ToxicDirection;

import org.testcontainers.containers.Network;
import org.testcontainers.containers.ToxiproxyContainer;
import org.testcontainers.kafka.KafkaContainer;
import org.testcontainers.utility.DockerImageName;

// In integration test fixture/setup; close resources in finally.
Network network = Network.newNetwork();

ToxiproxyContainer proxyContainer = new ToxiproxyContainer(
        DockerImageName.parse("ghcr.io/shopify/toxiproxy:2.5.0")
                .asCompatibleSubstituteFor("shopify/toxiproxy"))
        .withNetwork(network);

// Proxy must start first so host/mapped port are known.
proxyContainer.start();

KafkaContainer broker = new KafkaContainer(
        DockerImageName.parse("apache/kafka:3.9.1"))
        .withNetwork(network)
        .withListener(
                "kafka:19092",
                () -> proxyContainer.getHost() + ":"
                        + proxyContainer.getMappedPort(8666));

broker.start();

ToxiproxyClient toxiproxyClient = new ToxiproxyClient(
        proxyContainer.getHost(), proxyContainer.getControlPort());

Proxy kafkaProxy = toxiproxyClient.createProxy(
        "kafka-proxy", "0.0.0.0:8666", "kafka:19092");

String clientBootstrap = proxyContainer.getHost() + ":"
        + proxyContainer.getMappedPort(8666);

// Use clientBootstrap for the Spring producer/consumer under test.
```

With `@DynamicPropertySource`, build the fixture **before the Spring `ApplicationContext` creates `ProducerFactory`/`ConsumerFactory`**, then register `spring.kafka.bootstrap-servers` as `clientBootstrap`. Tests should create their own topics via `NewTopic`/`KafkaAdmin` or `AdminClient`; do not assume the Testcontainers broker auto-creates every application topic.

**Ordering note:** `broker.start()` runs after `proxyContainer` already has its mapped port so the supplier returns the advertised address. The TCP proxy can be created after broker startup, but must be ready **before the client under test connects**. If your Testcontainers version lacks the advertised-listener supplier, use the documented network topology for that version rather than overriding environment variables Testcontainers overwrites.

### 9.4. Cutting and Restoring Network Traffic

Once producer and consumer are confirmed communicating through the proxy, break both directions:

```java
// Add toxics to the exact Proxy used by the app.
kafkaProxy.toxics().bandwidth(
        "cut-up", ToxicDirection.UPSTREAM, 0);
kafkaProxy.toxics().bandwidth(
        "cut-down", ToxicDirection.DOWNSTREAM, 0);

// Here the test observes send/poll/timeout/reconnect.

// Always remove both toxics in finally.
kafkaProxy.toxics().get("cut-up").remove();
kafkaProxy.toxics().get("cut-down").remove();
```

A zero-bandwidth toxic simulates a severed link; a `timeout` toxic can actively close sockets after a delay. For already-open connections, tests should verify existing connections are actually disrupted rather than assuming calling the toxic API sufficed.

**Clean up faults in `finally`:** if a test fails halfway without removing toxics, subsequent tests will still see an unreachable broker and flake. With static or shared containers, each test must guarantee network state resets cleanly.

### 9.5. Proxy Test Procedure

1. Producer sends `before-proxy-001`; consumer reads it and writes the business marker.
2. Enable bidirectional toxics; verify a request through the proxy fails within a reasonable window.
3. During the outage, call `publish("during-proxy-001", ...)` and observe the future **with a bounded deadline**; do not cancel it yourself and assume the broker never wrote it.
4. Remove toxics in `finally`.
5. Wait for the producer to **send a new message** `after-proxy-001` and receive an ACK; consumer processes it.
6. Reconcile `during-proxy-001`: it may succeed after reconnect if the outage was shorter than `delivery.timeout.ms`, or fail if the deadline expired.
7. Verify the business store missed no confirmed events and wrote no duplicates by `eventId`.

To test producer **delivery expiration**, keep the network cut longer than the test profile's `delivery.timeout.ms` and await the future within a wider test timeout. To test **self-recovery before deadline**, remove toxics earlier and check whether the future ACKs; never reuse one timeline to demand two contradictory outcomes.

## 10. Integration Tests: Distinguishing ACKs, Timeouts, and Ambiguous Outcomes

A test asserting only `assertThrows(TimeoutException.class, () -> send.get(1000ms))` does not prove the producer actually failed. It only proves the test thread received no result within one second.

### 10.1. Verifying a Future Completes Exceptionally

When producer timeouts are kept short for tests and the network stays cut long enough:

```java
CompletableFuture<SendResult<String, String>> send =
        producer.publish("outage-event-1", "sample-payload");

try {
    send.get(30, TimeUnit.SECONDS);
    throw new AssertionError("Expected send to fail during long outage");
} catch (ExecutionException expected) {
    // Producer future completed exceptionally.
    // Inspect cause/exception category per Kafka client version.
} catch (TimeoutException waitingTooLong) {
    // Only the test timed out; does not prove the producer future failed.
    throw new AssertionError(
            "Future did not reach a terminal state within test budget",
            waitingTooLong);
}
```

Key imports: `CompletableFuture`, `ExecutionException`, `TimeUnit`, `TimeoutException`, `SendResult`. Set the test producer's `delivery.timeout.ms` below the overall test wait budget, accounting for broker startup and `max.block.ms`. Depending on the failure, `send(...)` may throw synchronously before returning a future; wrap the `publish(...)` call in test code and handle both paths cleanly.

**Do not hardcode one specific exception class for every network cut.** Depending on timing, the client may throw `TimeoutException`, `NetworkException`, `NotLeaderOrFollowerException`, or others via the future. What matters is classifying the failure/timeout and ensuring business workflows never mark a message durably published without proper confirmation.

### 10.2. Testing Self-Recovery Before the Delivery Deadline

A second scenario uses a generous deadline (such as 30 seconds), cuts the network briefly, and restores it **before** the deadline expires:

```text
send(eventId=short-outage-1)
    |
    +-- client retrying / awaiting metadata
    |
    +-- proxy restored
    |
    +-- future may complete successfully if broker conditions recover
```

Never guarantee a specific future will definitely succeed merely because the network returned before the deadline: the broker also needs an elected leader, healthy ISR, and valid metadata/producer state. Tests should observe actual outcomes, assert that **new messages after restore** succeed, and reconcile in-flight messages per contract.

### 10.3. Proving Business Results Are Idempotent

Suppose the test database has:

```sql
CREATE TABLE account_event_result (
    event_id VARCHAR(128) PRIMARY KEY,
    account_id VARCHAR(64) NOT NULL,
    applied_amount NUMERIC(14,2) NOT NULL
);
```

Feed the consumer the same event ID twice (you can publish two records carrying the **same event ID** to simulate controlled duplicate delivery). The service must persist **one** business result per policy and never double-credit the amount. This idempotency test is independent of network timing and should run even if an outage test does not happen to trigger a redelivery.

When a broker outage strikes between DB commit and offset commit, duplicates are **normal at-least-once behavior**. The right test proves the final business state is accurate, not that the listener method was invoked strictly once.

## 11. Consumer Integration Tests: Recovering After Disconnection

A consumer test must prove the app **actually resumes consuming** once the broker returns, not merely that the `ApplicationContext` stayed alive.

### 11.1. Bounded-Time Probe

In test configuration, you can update a `BlockingQueue`/`ConcurrentLinkedQueue` from the consumer listener once business processing **has committed**:

```java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

final class ProcessedEventProbe {
    final BlockingQueue<String> completedIds = new LinkedBlockingQueue<>();

    void onCommitted(String eventId) {
        completedIds.offer(eventId);
    }

    boolean await(String eventId, long timeoutSeconds) throws InterruptedException {
        long deadline = System.nanoTime()
                + TimeUnit.SECONDS.toNanos(timeoutSeconds);

        while (System.nanoTime() < deadline) {
            long remaining = deadline - System.nanoTime();
            String received = completedIds.poll(
                    Math.max(1, remaining), TimeUnit.NANOSECONDS);
            if (eventId.equals(received)) {
                return true;
            }
        }
        return false;
    }
}
```

This is an **illustrative test utility**; encapsulate waits and reset the probe per test rather than sharing a queue across parallel tests. Call `onCommitted(...)` only after the business transaction commits when asserting durable state; firing a callback on listener entry does not prove processing succeeded.

### 11.2. Assertion Sequence

```text
[A] Kafka healthy
    send(before-id) -> producer ACK
    wait business committed(before-id)

[B] Cut network / stop broker
    verify Kafka failure path per profile
    do not require listener to stop immediately

[C] Restore
    send(after-id) -> producer ACK
    wait business committed(after-id)

[D] Reconcile
    confirmed event IDs must exist in output
    no duplicate business side effects
    group lag returns to baseline
```

Use **bounded timeouts**, such as 10–30 seconds on a local broker, and allow larger budgets on slow CI runners or multi-broker clusters. Avoid fixed `Thread.sleep(...)` calls to guess when the broker or rebalance finished.

### 11.3. When the Consumer Recovers Yet the Service Still Fails

Kafka connectivity can recover while the business handler keeps failing due to schemas, databases, or downstream APIs. Never blame Kafka simply because `@KafkaListener` produced no output. Check:

- Did the producer event ACK, and at which topic/partition/offset?
- Does the consumer group hold partition assignments and fetch records?
- Are there deserialization errors? Is there a DLT or retry topic?
- Did the database transaction commit or roll back?
- Is the error handler recovering records per policy or still retrying/backing off?

`DefaultErrorHandler` handles in-listener exceptions per policy; **it does not turn a pure broker outage into message-level DLT records by default**. When the consumer cannot fetch records because the broker is unreachable, there is no concrete record to route through standard DLT recovery.

## 12. Advanced Lab — Losing One Broker in a Multi-Broker Cluster

Testing cluster-level fault tolerance requires a test Kafka cluster with **multiple independent brokers**, topics configured with proper replication factors, and explicit ISR constraints.

Suppose a three-broker cluster hosts a topic configured with:

```text
partitions=3
replication.factor=3
min.insync.replicas=2
producer acks=all
```

In classic configurations, if one partition leader dies while **two replicas remain in ISR** and an eligible replica is elected leader, the cluster can continue accepting writes after election. If ISR falls below `min.insync.replicas`, `acks=all` writes can fail. Exact behavior depends on Kafka version, leader/group election protocols, and replication features, so always observe **actual leader/ISR state** rather than guessing from live broker counts.

### 12.1. Losing a Follower

```text
Partition P0: leader=B1, ISR=[B1,B2,B3]
Kill B3 (follower)
Partition P0: leader=B1, ISR may shrink to [B1,B2]
Producer acks=all, minISR=2 -> writes can usually proceed
```

Measure: ISR shrinkage, producer latency while a replica is missing, under-replicated partitions, and replica catch-up speed when B3 returns. Do not expect a consumer rebalance solely from losing a follower if the group coordinator and partition leaders remain healthy.

### 12.2. Losing a Leader

```text
Partition P1: leader=B2, ISR=[B1,B2,B3]
Kill B2 (leader)
Election -> B1 or B3 may become leader (if eligible)
Producer refreshes metadata/retries -> can keep sending
Consumer fetches from new leader
```

During leader election, producers may see retriable errors or higher latency; avoid knee-jerk restarts of all producers and consumers. Clients refresh metadata and retry automatically; what matters is having enough delivery budget and reconciling business outputs.

### 12.3. Losing Quorum/ISR Required for Writes

```text
Partition P2: replica set=[B1,B2,B3], minISR=2
Only one replica available in ISR
Producer acks=all -> may fail with NotEnoughReplicas...
```

Evaluate consumer reads, availability, and durability against topic state and configuration; **never lower `min.insync.replicas` to 1 in production just to make tests look green** without accepting the durability risk. Enabling unclean leader election can also risk losing previously ACKed records under certain failures; it is a serious operational trade-off, not a quick fix for a lab.

### 12.4. Cluster Expectations Table

| Experiment | Producer | Consumer | What to Verify |
|---|---|---|---|
| Kill follower, ISR still sufficient | Can keep sending; latency shifts. | Usually continues if leader/coordinator healthy. | ISR and replication catch-up. |
| Kill leader, enough replicas | May retry during election, then continue. | Brief fetch pause, then switches to new leader. | Zero committed data loss, recovery duration. |
| Lose multiple brokers, ISR short | `acks=all` may fail/timeout. | Depends on partition availability and leader. | Never report success when durability contract is unmet. |
| Broker returns | Recovers once leader/ISR qualify. | Group resumes, backlog drains. | Catch-up, lag, and data reconciliation. |
| Network cut from only one consumer | Other producers unaffected. | That consumer stops fetching; group may reassign. | Liveness of remaining members and redeliveries. |

## 13. Metrics and Logs to Collect Throughout the Experiment

A useful experiment captures the milestones `before → outage injected → outage observed → restored → business caught up`.

| Group | Signal | How to Interpret |
|---|---|---|
| Producer | Sends/sec, error rate, request latency | Throughput and failures during outage. |
| Producer | Failed futures, delivery timeouts, record retries | Separates active retries from terminal failures. |
| Producer | Buffer available/wait time, `max.block` timeouts | Shows buffer saturation during prolonged broker loss. |
| Consumer | Records consumed/sec, poll time, commit latency/failures | Shows whether processing and offset commits still succeed. |
| Consumer group | Member count, partition assignments, rebalance duration | Detects membership churn. |
| Backlog | Consumer lag per topic/partition | Measures catch-up rate after restore. |
| Cluster | Broker health, leader elections, under-replicated partitions, ISR shrink | Separates client network issues from broker failover. |
| Spring | Container `isRunning`, `ListenerContainerIdleEvent`, `NonResponsiveConsumerEvent` | Supporting signals, never sole conclusions. |
| Business | Persisted event IDs, duplicate suppressions, pending outbox rows | Ground-truth evidence of business correctness. |

### 13.1. Logging by Event ID Without Printing Sensitive Payloads

Example:

```text
2026-11-16T03:00:01Z kafka.produce.acked eventId=evt-001 partition=0 offset=103
2026-11-16T03:00:05Z chaos.kafka.disconnected scope=producer-test case=network-cut
2026-11-16T03:00:20Z kafka.produce.failed eventId=evt-002 errorType=TimeoutException
2026-11-16T03:00:30Z chaos.kafka.restored scope=producer-test
2026-11-16T03:00:32Z kafka.produce.acked eventId=evt-003 partition=0 offset=104
2026-11-16T03:00:33Z business.event.applied eventId=evt-003 status=COMMITTED
```

Timestamps and values are **format examples only**. Never log full JSON payloads, headers carrying tokens, keystore credentials, or PII to debug an outage. A stable event ID / trace ID makes reconciliation far easier than thousands of identical stack traces.

### 13.2. Do Not Count Kafka `NetworkClient` Warnings Alone

During an outage, clients emit connection and coordinator warnings. Some warnings are expected during retries and failover. Correlate logs with **end-to-end metrics** and business outputs; fewer warnings do not prove backlogs have drained.

### 13.3. Consumer Idle Does Not Mean Cluster Down

When no new messages arrive, `ListenerContainerIdleEvent` fires even when the broker is completely healthy. When network issues stall `poll()`, `NonResponsiveConsumerEvent` can alert per monitor thresholds. Interpret every signal alongside partition assignments, lag, broker reachability, and producer health.

## 14. Readiness, Liveness, and Restart Policies When Kafka Is Unavailable

For Spring Boot running on Kubernetes, poorly tuned health probes can make a temporary Kafka outage **far worse** if they restart every pod in a loop.

| Scenario | Recommended Policy | Risk if Handled Poorly |
|---|---|---|
| Brief Kafka outage, clients still retrying | Keep process alive; monitor backlog and reconnects. | Mass liveness kills trigger rebalance storms and startup spikes. |
| Consumer stopped on fatal auth error | Alert and fix credentials/ACLs; restart per policy. | Infinite network retries cannot fix bad ACLs. |
| Prolonged Kafka outage, service cannot serve requests | Readiness may reflect unavailability depending on service role. | `readiness=false` does not stop Kafka polling; understand HTTP vs. Kafka impact. |
| Large producer backlog in RAM | Apply backpressure, bounded buffers, reject/defer requests. | OOM or lost events when the process dies. |
| Consumer group lacks assignment after broker recovery | Inspect group, metadata, rebalances, and container state. | Blind restarts increase churn. |

Spring Boot Actuator `liveness` is meant to indicate whether the process itself is wedged; tying it to Kafka connectivity must be considered carefully. For a consumer service built to retry and reconnect, temporary Kafka downtime **does not mean the JVM is broken**. True liveness checks must distinguish process deadlocks/fatal states from external dependency outages.

## 15. Specific Risks Around Retries, DLT, and Transactions

### 15.1. `DefaultErrorHandler` and Record Retries

`DefaultErrorHandler` handles exceptions raised inside a record listener per policy. When the broker is unreachable and **no records are being delivered**, that is not an item-level failure that an error handler can immediately skip or route to a DLT.

Conversely, if the listener received a record, called a database or API, and failed, the error handler can retry or send to a DLT as configured. **A Kafka outage and a downstream outage must never share the same diagnosis:** distinguish failures before poll, during processing, and during recovery/commit.

### 15.2. A DLT Does Not Solve an Unavailable Broker

If the DLT lives on the same down Kafka cluster, the dead-letter producer cannot publish either. Never catch DLT publish exceptions and commit the source offset as if the record were recovered, unless an explicit durable fallback store and business policy allow it.

For critical messages, avoiding loss during Kafka outages requires a transactional outbox, a durable producer-side queue, or application-level durable retries. **In-memory queues** and console logs are not durable storage across crashes.

### 15.3. Kafka Transactions / Transactional Producers

If an application uses Kafka transactions for consume-transform-produce, losing the coordinator or broker can cause transaction timeouts, aborts, retries, or producer fencing. Kafka's exactly-once semantics remain scoped to supported Kafka transactions; **they do not automatically make HTTP/DB side effects exactly-once**.

When testing transactions under outages, observe producer state after fatal errors. A fenced or fatally errored producer must be closed and replaced per Spring Kafka lifecycle rather than retrying `send` indefinitely on the same instance. Also ensure `transactional.id` never collides unintentionally across active replicas.

### 15.4. `read_committed` and Unfinished Transactions

A consumer with `isolation.level=read_committed` reads only committed transactional records per Kafka semantics. During an outage, in-flight transactions may remain unresolved until coordinators/brokers recover or transaction timeouts expire. This can make lag and visibility differ from `read_uncommitted`; never assume "new offsets exist on the topic yet the consumer isn't reading" automatically means the consumer is broken.

## 16. Chaos Test Matrix to Avoid Missing Critical Cases

Never run a single `docker stop` and declare the application resilient. A practical test matrix includes:

| Test ID | Fault Injection | Injection Timing | Primary Expectation |
|---|---|---|---|
| `B1` | Stop single broker | While producer/consumer idle | Clients reconnect when broker returns. |
| `B2` | Kill single broker | While producer actively sending | Success/failure/ambiguous futures handled per contract; no confirmed events lost. |
| `B3` | Cut proxy both ways | After consumer DB commit, before offset commit | Possible redelivery; idempotency prevents duplicate side effects. |
| `B4` | Cut proxy then restore quickly | Before `delivery.timeout.ms` | Producer can complete send; new sends after restore succeed. |
| `B5` | Cut proxy longer than delivery deadline | Under multi-message load | Terminal future failures observed; bounded retries/backpressure hold. |
| `B6` | Inject proxy latency/jitter | Under active traffic | Measure p95/p99 latency, request timeouts, retry rates. |
| `B7` | Kill follower in multi-node cluster | While leader healthy and ISR sufficient | Writes/reads continue; ISR shrinks then recovers. |
| `B8` | Kill partition leader | With sufficient replicas | Leader election completes; clients refresh metadata and continue. |
| `B9` | Lose enough brokers to drop ISR below minISR | With `acks=all` producer | Writes fail/retry per durability policy; no false success. |
| `B10` | Misconfigure `advertised.listeners` in lab | After bootstrap succeeds | Client fails reaching metadata endpoints; diagnosed as config issue. |
| `B11` | Deny ACL/credentials in test | During consumer startup | Classified as auth error, not network outage. |
| `B12` | Restore broker while downstream DB stays down | After network restore | Kafka connectivity healthy while business processing still fails; error handler follows policy. |

In every test, record: topic, partition count, replication factor, `min.insync.replicas`, producer `acks`, consumer ack mode, key/event IDs, and injection timestamps. Changing multiple variables at once makes it impossible to prove which setting caused the observed behavior.

### 16.1. Using Immutable Record IDs for Reconciliation

For example, a test producer emits:

```text
before-0001
before-0002
inflight-0003
during-0004
after-0005
```

Each event carries a stable `eventId` as its Kafka key and business deduplication key. Before running, classify **expected event sets** by outcome:

- `ACKED`: producer received Kafka confirmation matching `acks`.
- `FAILED`: producer future completed exceptionally; requires retry/reconciliation policy rather than assuming the record is absent.
- `UNKNOWN`: caller timed out or process died before learning the outcome.

After recovery, reconcile all groups against your contract. A zero-data-loss test normally requires every `ACKED` event to be processed accurately in business state, while `UNKNOWN` events are resolved via reconciliation or idempotent retries. **Do not demand every attempted send appear on Kafka**, because some sends during a broker outage may legitimately fail before acceptance.

### 16.2. Measuring Recovery Time

Record timestamps:

```text
t0: fault injected
t1: client/monitor detects issue
t2: network/broker restored
t3: first successful producer ACK after fault
t4: first consumer business commit after fault
t5: lag returns to baseline / backlog drained
```

From these, compute **detection latency**, **reconnect time**, **time-to-first-success**, and **time-to-catch-up**. Use synchronized clocks and event traces with correlation IDs. If the broker recovered at `t2` while `t5` lags far behind, the bottleneck may be backlog volume or consumer throughput rather than reconnection itself.

## 17. Operations Runbook When Kafka Brokers Are Unreachable

When alerted on producer timeouts or rising consumer lag, follow a structured sequence:

### Step 1 — Determine Incident Scope

1. Is only one service/pod failing, or all clients?
2. Is one broker node, one partition leader, or the entire cluster unreachable?
3. Are producers unable to send, consumers unable to fetch, commits failing, or is there simply no new traffic?
4. Were there recent changes to DNS, certificates, ACLs, network policies, service meshes, or advertised listeners?
5. Is the Kafka cluster undergoing a planned restart or rolling upgrade?

If only one pod fails while peer pods remain healthy, inspect that pod's network namespace, sidecar, or egress policy before declaring the Kafka cluster down.

### Step 2 — Collect Evidence Safely

- Record timestamps, client IDs, bootstrap hosts, topics/partitions, and consumer groups—never log credentials.
- Check broker process health, cluster metadata, leaders/ISR, and coordinators.
- Inspect Kafka client logs for disconnects, timeouts, auth/authorization errors, or deserialization failures.
- Collect consumer lag, producer error rates, retries, timeouts, commit failures, and buffer metrics.
- Check side-effect stores, outbox tables, and business databases to see which events actually committed.

Never flip the entire Kafka client to `DEBUG` on high-throughput production workloads indefinitely without log controls, as network and record log volume can explode.

### Step 3 — Wait for Self-Recovery or Intervene?

| Condition | Suggested Action |
|---|---|
| Brief network blip, cluster healthy, clients reconnecting | Monitor against SLO/timeouts; avoid mass restarts. |
| Wrong advertised hostname | Fix listener/DNS/routing at source; restarting clients alone won't help. |
| Partition leader unavailable, ISR sufficient | Monitor leader election, metadata refresh, and producer deadlines. |
| ISR short, writes fail durability checks | Restore broker/replica health and capacity; never silently weaken durability. |
| Bad auth/ACL | Fix identity, permissions, or certificates; avoid infinite retries or disabling security. |
| Consumer container stopped on fatal error | Inspect `ConsumerStoppedEvent`/logs before targeted restart. |
| Producer buffer saturated | Enforce backpressure, durable queues, or controlled request rejection. |
| Offset commit failed after DB success | Allow idempotent replays and reconcile outcomes. |

### Step 4 — Confirm Recovery with Data

1. Producer can send a **new event** and receive an ACK matching `acks`.
2. Consumer group holds active assignments and consumes new events.
3. Business store reflects all confirmed events accurately.
4. Duplicate suppressions do not become business errors; no unpolicy-approved data loss occurred.
5. Lag, throughput, and timeout rates remain stable over an observation window.
6. If using transactional producers, verify transaction and fencing state recovered cleanly.

### Step 5 — Post-Incident Review and Hardening

Document root cause, outage duration, ambiguous events, retry handling, ISR/leader state, catch-up speed, and any SLA breaches. Use findings to tune timeouts, retries, backpressure, idempotency, and alert thresholds—avoid blindly "raising all timeouts" without evidence.

## 18. Common Pitfalls When Simulating Broker Disconnection

| Symptom | Common Cause | Resolution |
|---|---|---|
| Stopping broker container also stops Spring app | Test app placed inside the same container/process as broker. | Run test clients outside the broker container. |
| Cutting Toxiproxy still lets producer send | Metadata advertises direct broker address, bypassing proxy. | Route both bootstrap and advertised broker endpoints through proxy. |
| Changed Docker host port, client still uses old port | `advertised.listeners` mismatches client-reachable address. | Align listener config, mapped ports, and metadata. |
| Sending while Kafka is down doesn't throw immediately | Producer buffers/retries asynchronously; `.send()` returns a future. | Await terminal outcome or check `max.block`/`delivery.timeout`. |
| `future.get(1s)` times out, test assumes record failed | Caller wait timeout differs from producer `delivery.timeout.ms`. | Inspect completion callback or future terminal state. |
| Prior records missing after broker restart | Container recreated fresh without persistence, or different group offset. | Reuse container/volumes and verify topic, group, key, and retention. |
| `auto-offset-reset=earliest` doesn't read from start | Consumer group already has a committed offset. | Use a fresh test group or controlled seek/reprocess. |
| Idle logs mistaken for broker down | Topic genuinely has no new messages. | Correlate lag, broker connectivity, and producer rates. |
| No `ConsumerStoppedEvent` when broker dies | Container remains running and reconnecting. | Track network/consumer metrics rather than expecting stop events. |
| Kafka reconnects yet DB output stays missing | Downstream/DB/handler failing or offset commit misconfigured. | Reconcile events, transactions, and error handlers. |
| Records processed twice | DB side effect committed before Kafka offset commit. | Enforce consumer idempotency by business event ID. |
| Producer emits duplicates after retry | App resends same event as a new request. | Durable outbox, stable event IDs, and consumer deduplication. |
| Testing cluster failover with RF=1 topic | No replica exists to take over leadership. | Use a 3-broker cluster, RF=3 topics, and proper minISR. |
| `acks=all` fails when one broker dies | ISR dropped below policy or election in progress. | Inspect ISR/leader/minISR rather than lowering `acks` blindly. |
| Intermittent CI failures after network restore | Fixed `Thread.sleep`, shared topics/groups, incomplete rebalance. | Use bounded awaits, isolated fixtures, and verify assignments/outputs. |
| Docker data deleted mid-test | Uncontrolled `docker rm -v` / `down -v` cleanup. | Clean up only labeled lab resources after confirmation. |
| Liveness probes restart all pods during Kafka blip | Kafka connectivity treated as fatal process signal. | Decouple external outages from JVM liveness to prevent restart storms. |
| DLT publish also times out | DLT broker shares the same cluster outage. | Use durable pending/outbox storage or policy-driven retry/reconciliation. |
| Toxiproxy test cuts the wrong client | Multiple client factories/advertised endpoints; only one path proxied. | Identify client IDs and point all test factories at proxy bootstrap. |
| Broker restarted but no leader ready yet | Metadata/leader election/controller still initializing. | Wait for cluster/topic readiness, not just an open TCP port. |

## 19. Recommended Automated Test Scenarios

### 19.1. Unit Tests: Error Classification Without a Kafka Broker

A service handling publish results should decouple policy from `KafkaTemplate`:

```text
send ACK succeeds -> mark CONFIRMED
future terminal exception -> mark FAILED/RETRYABLE by error class
caller timeout while future non-terminal -> UNKNOWN/PENDING
crash between Kafka ACK and state save -> reconcile by event ID
```

Unit tests can mock `CompletableFuture` completions to test classification and outbox updates without a real broker. Never mark `UNKNOWN` rows as `NOT_PUBLISHED` and blindly resend without an idempotency strategy.

### 19.2. Integration Tests: Broker Reachable and Unreachable

With Testcontainers/Toxiproxy or a local Docker lab, verify:

1. Under normal networking, `KafkaTemplate.send` receives ACKs and the listener receives records.
2. When the network is cut long enough, send futures fail within the configured deadline.
3. Once the network recovers, the producer sends new records successfully without rebuilding the entire `ApplicationContext` in self-recovery scenarios.
4. The consumer processes new events and group lag returns to target baseline.
5. Business state holds the exact expected event IDs with zero duplicate side effects.

Do not write tests demanding **every in-flight future fail** during a short network cut, because the producer may retry and succeed. For tests exceeding delivery timeout, await terminal outcomes rather than using fixed sleeps and guessing.

### 19.3. Integration Tests: Broker Crash and Restart

Set up a test-owned local broker or cluster with persistent storage across restarts. Inject a crash while a record is in flight; after recovery, inspect business markers and committed offsets. If killing real processes, run producer/consumer and broker in separate processes/containers so you do not kill the JUnit runner. Never run chaos tests against a shared Kafka cluster.

### 19.4. Ensuring Clean Teardown

- Remove Toxiproxy toxics inside `finally`.
- Stop/close Testcontainers resources cleanly after tests.
- Never leave stale events in shared static `BlockingQueue`s from prior tests.
- Use isolated topic/group IDs and reset business DB fixtures.
- Ensure no background producer task continues writing into the next test's topics.
- Never run parallel chaos tests against the same broker/container when tests require exclusive control over network state.

## 20. Practice Exercises

### Exercise 1 — Stop Broker and Self-Recover

Start local Kafka with Docker alongside the Spring Boot producer and consumer from the examples above. Send two events before the outage, stop the broker with `docker stop`, monitor producer futures and consumer logs, then run `docker start`. Send a new event and verify the consumer completes it. Build a timeline with exact timestamps and distinguish `caller timeout` from `producer delivery timeout`.

### Exercise 2 — Cut Network Without Killing the Broker

Use Toxiproxy to sever traffic both ways between client and broker. Verify the client does not bypass the proxy thanks to `advertised.listeners` while the Kafka broker stays healthy. Restore the proxy and measure time to first producer ACK, first consumer business commit, and lag catch-up.

### Exercise 3 — Short vs. Long Outages

Test 3-second and 25-second network cuts against a producer profile with `delivery.timeout.ms=15000`. Compare outcomes for in-flight futures, new sends after network restore, and caller wait times. Do not assert that a 3-second cut always succeeds; explain broker readiness, metadata, and retry factors.

### Exercise 4 — Idempotency After Ambiguous Offset Commit

Design a service writing business state and an `event_id` marker in one transaction, then feed the same event twice. Verify the business result applies only once. Next, simulate losing the broker right after DB commit but before offset ACK to observe redelivery; verify via final DB state, not callback counts alone.

### Exercise 5 — Leader/Follower Failure in a Three-Broker Cluster

Create a topic with RF=3, `min.insync.replicas=2`, and producer `acks=all`. In two separate tests, stop a follower and then stop a leader; observe leader election, ISR, latency, and consumer continuity. Then reduce available replicas below minISR in the test cluster and record producer errors. Explain why production must not weaken durability policies just to "fix" the test.

### Exercise 6 — Distinguishing Unavailable Kafka from Auth Errors

Test two lab scenarios: broker unreachable due to network loss, and a test principal denied by ACLs. Observe exception families, container state, `ConsumerStoppedEvent` if emitted, and the proper remediation. Never disable production TLS/ACLs for simulation.

### Exercise 7 — Building a Recovery Dashboard

Build a dashboard showing producer error rates, consumer lag, group assignments, retry counts, broker ISR / under-replicated partitions, and duplicate suppression counts. Annotate outage/restore markers. Propose alert thresholds separating true broker loss, legitimately empty Kafka topics, and slow downstream consumers.

### Exercise 8 — Writing a Runbook and Chaos Test Report

Draft a report following this template:

```text
Experiment: kafka-network-cut-478
Environment: isolated test
Kafka topology: 1 broker / 1 partition / RF=1
Fault: proxy upstream+downstream blocked
Duration: <recorded seconds>
Producer config: acks=all, idempotence=true, delivery.timeout.ms=15000
Consumer config: auto-commit=false, AckMode.RECORD

Before: produced/acked/processed event IDs
During: errors, unknown outcomes, commit failures, lag
After: new producer ACK, consumer resumed, lag caught up
Business: missing IDs, duplicates suppressed, unresolved ambiguous IDs
Recovery time: measured timestamps
Conclusion: pass/fail against declared acceptance criteria
```

**The template uses illustrative labels**; fill in actual measurements. Never mark `PASS` simply because the Kafka container returned to `running`; final acceptance must verify business data and continued processing capability.

## 21. Key Principles to Remember

1. **Broker loss, per-client network loss, and cluster leader loss are three distinct failures.** Choose the right fault injection to prove what you claim.
2. **`bootstrap.servers` only fetches initial metadata; `advertised.listeners` governs subsequent connections.** A proxy sitting only in front of bootstrap can be bypassed.
3. **Producer `.send()` does not equal an ACK.** Observe futures/callbacks and separate caller wait timeouts from `delivery.timeout.ms`.
4. **Retries and idempotent producers do not replace business idempotency.** An application resending an event as a new call can still append a duplicate Kafka record.
5. **Consumers can reconnect and reread records.** Offset commits and DB commits are not automatically atomic across separate transactions.
6. **Never use `ListenerContainerIdleEvent` as proof Kafka is down.** Healthy idle topics and stalled polls are different things.
7. **Do not expect `DefaultErrorHandler`/DLT to solve pure broker network outages.** When no records are polled, record-level recovery has nothing to process.
8. **Only replicated clusters with ISR properly test broker failover.** Single-broker RF=1 setups only simulate full-service outages.
9. **Restored connectivity does not mean business outputs are complete.** Reconcile ACKed events, ambiguous outcomes, lag, and idempotency.
10. **Every experiment needs isolation, bounded timeouts, and cleanup.** Never run stop/kill/netem against production Kafka without an approved chaos engineering process.

## 22. Official References

- [Spring Kafka Reference — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html): `AckMode`, offset commits, rebalances, and listener container lifecycle.
- [Spring Kafka Reference — Application Events](https://docs.spring.io/spring-kafka/reference/kafka/events.html): idle, non-responsive, and consumer stop events.
- [Spring Kafka Reference — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html): `DefaultErrorHandler`, retries, and recovery on listener failures.
- [Spring Kafka Reference — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html): scope of Kafka transactions and EOS.
- [Spring Kafka Reference — Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html): `@EmbeddedKafka` and integration testing.
- [Spring Boot Reference — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html): `spring.kafka.*`, factories, `KafkaTemplate`, and testing.
- [Apache Kafka — Producer Configuration](https://kafka.apache.org/documentation/#producerconfigs): `acks`, idempotence, delivery timeout, retries, and reconnects.
- [Apache Kafka — Consumer Configuration](https://kafka.apache.org/documentation/#consumerconfigs): group membership, offsets, and polling configuration.
- [Apache Kafka — Topic Configuration](https://kafka.apache.org/documentation/#topicconfigs): replication, ISR, and min ISR constraints.
- [Apache Kafka 3.9 — Docker](https://kafka.apache.org/39/getting-started/docker/): running the official Apache Kafka JVM image in a local lab.
- [Testcontainers for Java — Kafka Module](https://java.testcontainers.org/modules/kafka/): Kafka containers and custom listeners for test networks.
- [Testcontainers for Java — Toxiproxy Module](https://java.testcontainers.org/modules/toxiproxy/): fault injection via network proxies, latency, and connection cuts.



