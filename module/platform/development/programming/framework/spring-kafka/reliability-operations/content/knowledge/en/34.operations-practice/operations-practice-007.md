# Simulating Consumer Lag in Spring Kafka: An Operations Lab from Basics to Incident Response

## 1. Why Simulate Consumer Lag?

In an Apache Kafka system, a consumer can still be running, throwing zero exceptions, and steadily logging "processed," yet **fail to keep pace with incoming data**. The count of unconfirmed records builds up—this is one manifestation of **consumer lag**. Left unchecked, order, payment, notification, or inventory sync events arrive at downstream systems past their SLAs.

The lab **Simulating Consumer Lag**, part of *Spring Kafka Reliability Operations → Operations Practice*, guides you through creating **controlled** lag scenarios in an isolated Kafka environment, measuring them with operational tooling, and recovering based on root cause. This is not a "set concurrency to 10 and lag disappears" exercise: you must understand offsets, partition assignment, throughput, transactions, retries, and duplicate handling.

### What Will You Practice?

1. Spin up an isolated Kafka broker/topic and Spring Boot consumer group.
2. Inspect `CURRENT-OFFSET`, `LOG-END-OFFSET`, and `LAG` using the Kafka CLI.
3. Induce lag from **five causes**: producer bursts, slow consumer processing, pause/stop, insufficient consumer capacity, and partition/key skew.
4. Distinguish lag caused by high input arrival rates from lag caused by stalled committed offsets.
5. Measure production rates, commit rates, lag trends, and catch-up time estimates.
6. Examine the interaction among `max.poll.records`, `max.poll.interval.ms`, and rebalances.
7. Compare recovery via latency reduction, higher concurrency, partition expansion, and upstream load shedding.
8. Recognize "lag is 0 yet data is wrong" caused by premature acks or broken error handling.
9. Design dashboards, alerts, runbooks, and recovery tests.
10. Clean up lab resources safely without touching production consumer groups.

Illustrative code uses **Java 17, Spring Boot 3.4.x, Spring Kafka 3.3.x**, **Kafka 3.9.x** brokers, and Docker Compose. Commands shown are **meant for learners to run in an isolated lab**; this guide does not run Docker, Gradle, Kafka, or load against live systems.

### Safety Scope

Every topic, group, and control endpoint in this lesson is prefixed `lag.lab.*`, uses a **local** broker, contains no customer data, and omits production security. Never run deliberate pauses, injected errors, offset resets, overload tests, or producer bursts against enterprise clusters. Such actions can breach SLAs, trigger redeliveries, or drop unprocessed data if misused.

---

## 2. Understanding Lag Before Running Experiments

### 2.1. Offsets Within a Partition

A Kafka topic is divided into partitions. Within each partition, records sit at monotonically increasing offsets (without assuming contiguous offsets under compaction or retention policies).

```text
Topic: lag.lab.orders
Partition: 0

offset       0   1   2   3   4   5   6   7   8   9  10 ...
record       ●   ●   ●   ●   ●   ●   ●   ●   ●   ●   ●
                         ▲                       ▲
             committed next offset = 4     log end = 11

Remaining consumer-group offset lag ≈ 11 - 4 = 7
```

**Note:** Kafka's committed offset is the **next position** the consumer expects to read after already-committed records. If the group committed `4`, it generally means records prior to offset 4 (i.e., 0–3) completed per commit policy—not that record 4 itself was processed.

### 2.2. Lag Formula per Consumer Group and Partition

For partition `p`:

```text
L_p = max(0, logEndOffset_p - committedOffset_p)

L_total = Σ L_p
```

Example:

| Partition | CURRENT-OFFSET | LOG-END-OFFSET | LAG |
|---:|---:|---:|---:|
| 0 | 500 | 900 | 400 |
| 1 | 1,000 | 1,100 | 100 |
| 2 | 600 | 1,300 | 700 |
| **Total** | | | **1,200** |

These numbers are **illustrative**, not actual lab measurements.

In `kafka-consumer-groups.sh --describe`, `CURRENT-OFFSET` represents the group's committed offset, `LOG-END-OFFSET` is the log end offset reported by the tool, and `LAG` is the difference. A record already polled into memory but **not yet committed** still counts toward committed-offset lag.

### 2.3. Lag Does Not Always Equal Unprocessed Business Events

Offset counts do not always match unprocessed business events:

- A record may be **processed** while its Kafka offset has not committed yet.
- A consumer may commit an offset before the business DB commits: lag looks low while data is missing.
- In compacted topics or topics containing transaction/control markers, offset gaps do not necessarily equal readable business records.
- With `isolation.level=read_committed`, readable position also depends on the Kafka transaction **Last Stable Offset (LSO)**; log-end and broker metrics must be interpreted alongside isolation and exporter behavior.
- Records routed to a DLT allow main-topic offsets to advance even though those business events still await replay.
- A group without any committed offset yet may display `-` or omit rows; never report that as "lag = 0."
- Kafka retention can delete records before a lagging group reads them, making offset differences hide lost events.

**Operational rule:** always correlate lag with throughput, error/DLT counts, event age, DB state, and business SLAs.

### 2.4. Whether Lag Grows or Shrinks Depends on Two Rates

Over an interval `Δt`:

```text
ending lag ≈ max(
    0,
    starting lag
      + newly readable records
      - committed offset progress
)
```

Suppose a producer emits 120 records/second while the consumer group commits only 40 records/second under backlog:

```text
Lag growth rate ≈ 120 - 40 = 80 records/s

After 60 seconds, lag grows by roughly 4,800 records.
```

If the producer stops and the consumer sustains 40 records/s, draining a 4,800-record backlog takes roughly 120 seconds, **assuming actual processing throughput holds and no failing record stalls a partition**.

### 2.5. Record Lag Differs from Time Lag

Two groups both showing 50,000 records of lag can carry very different risk:

- Group A processes 25,000 records/second and catches up quickly.
- Group B processes 50 records/second and stays backlogged for a long time.
- One partition's oldest unread record might be 45 minutes old while another partition's is 10 seconds old.

Therefore, monitor **age of oldest unprocessed event**, catch-up ETA, and business deadlines—never a single LAG number alone.

---

## 3. Prerequisites and Topology

### 3.1. Requirements

- Docker Engine / Docker Desktop with Docker Compose.
- Java 17 and Gradle / Gradle Wrapper.
- Host port `29092` free for Kafka and `8080` for local Spring Boot.
- `docker compose` CLI.
- PowerShell or equivalent shell terminal.
- Synthetic test payloads only.

This lab does not require Kafka Connect, Schema Registry, or a full Prometheus server to observe offsets. The Kafka CLI and Actuator endpoints suffice for the first pass.

### 3.2. Topology

```text
                Docker Compose
          ┌────────────────────────┐
          │ Kafka KRaft single node│
          │ internal: kafka:9092   │
          │ host: localhost:29092  │
          └───────────┬────────────┘
                      │
              topic lag.lab.orders
                 3 partitions
                      │
       ┌──────────────┴────────────────┐
       │                               │
       ▼                               ▼
Producer perf CLI             Spring Boot app
test throughput levels        group lag-lab-v1
                              @KafkaListener
                                   │
                        ┌──────────┴──────────┐
                        │ delay/pause/resume  │
                        │ metrics / stats     │
                        └─────────────────────┘
                                   │
                                   ▼
                       kafka-consumer-groups CLI
                         offset / lag / members
```

**Single broker, replication factor 1, and plaintext are for labs only.** Never copy these settings to production: there is no high availability, no TLS/SASL, no multi-tenant isolation, and no resource sizing for live traffic.

---

## 4. Starting the Broker with Docker Compose

Create a dedicated lab directory, e.g., `spring-kafka-lag-lab`, with `compose.yaml`:

```yaml
services:
  kafka:
    image: apache/kafka:3.9.1
    hostname: kafka
    container_name: kafka-lag-lab
    ports:
      - "127.0.0.1:29092:29092"
    environment:
      KAFKA_NODE_ID: 1
      KAFKA_PROCESS_ROLES: broker,controller
      KAFKA_CONTROLLER_QUORUM_VOTERS: "1@kafka:9093"
      KAFKA_LISTENERS: "PLAINTEXT://:9092,CONTROLLER://:9093,HOST://:29092"
      KAFKA_ADVERTISED_LISTENERS: "PLAINTEXT://kafka:9092,HOST://localhost:29092"
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: "PLAINTEXT:PLAINTEXT,CONTROLLER:PLAINTEXT,HOST:PLAINTEXT"
      KAFKA_CONTROLLER_LISTENER_NAMES: CONTROLLER
      KAFKA_INTER_BROKER_LISTENER_NAME: PLAINTEXT
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
      KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR: 1
      KAFKA_TRANSACTION_STATE_LOG_MIN_ISR: 1
```

Here:

- Internal containers reach the broker at `kafka:9092`.
- The Java app running on the host connects to `localhost:29092`.
- The host port binds only to loopback `127.0.0.1`; Kafka APIs are not exposed to the network.
- A single node acts as both broker and controller in KRaft mode; no ZooKeeper is used.
- Internal replication factors are set to `1` because there is only one broker.
- The image tag is pinned to prevent `latest` from changing behavior unexpectedly.

Bring up the cluster:

```bash
docker compose up -d
docker compose ps
docker compose logs --tail=80 kafka
```

If the broker is not ready yet, Kafka CLI commands may fail with connection refused during startup. Check logs and readiness before running experiments; never assume container status "Up" guarantees the broker is ready.

### 4.1. Creating a Three-Partition Topic

```bash
docker compose exec -T kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:9092 --create --if-not-exists --topic lag.lab.orders --partitions 3 --replication-factor 1
```

Inspect it:

```bash
docker compose exec -T kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:9092 --describe --topic lag.lab.orders
```

Expect `PartitionCount: 3` and `ReplicationFactor: 1`. You do not need to delete or recreate the topic before each experiment round: you can create a new group ID or record baseline offsets depending on your goal.

### 4.2. Checking the Broker from the Host

If Kafka CLI tools are installed on your host:

```bash
kafka-topics.sh --bootstrap-server localhost:29092 --list
```

If not, all measurement commands below run via `docker compose exec -T kafka` with no extra host tools required.

### 4.3. Avoiding Lab Collisions

Do not use `orders.events` or `orders-prod` if another system uses them. Names like `lag.lab.orders` and `lag-lab-v1` are easy to recognize, yet **naming does not replace environment isolation**: always confirm `--bootstrap-server kafka:9092` points strictly to your local Docker broker.

---

## 5. Building a Spring Boot Consumer with Adjustable Latency

### 5.1. Layout

```text
spring-kafka-lag-lab/
├── compose.yaml
├── build.gradle
├── settings.gradle
└── src/
    └── main/
        ├── java/com/example/laglab/
        │   ├── LagLabApplication.java
        │   ├── LagLabListener.java
        │   └── LagLabControlController.java
        └── resources/
            ├── application.yml
            └── application-lag-lab.yml
```

This project provides:

- A `@KafkaListener` consuming records sequentially per partition.
- An `AtomicLong delayMs` to simulate slow business processing.
- `KafkaListenerEndpointRegistry` to pause, resume, stop, and start the consumer container.
- A local HTTP API to adjust delay during the lab.
- Micrometer `Counter`/`Timer` metrics for processing throughput.
- Spring Boot Actuator to inspect metrics and health.

### 5.2. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.5'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.kafka:spring-kafka'

    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`settings.gradle`:

```groovy
rootProject.name = 'spring-kafka-lag-lab'
```

These versions target Spring Boot 3.4.x. On Spring Boot 4 / Spring Kafka 4, check compatibility and API changes rather than upgrading a single artifact outside the BOM.

### 5.3. Spring Boot Application

```java
package com.example.laglab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LagLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(LagLabApplication.class, args);
    }
}
```

### 5.4. `application.yml`

Set safe defaults:

```yaml
spring:
  application:
    name: spring-kafka-lag-lab
  kafka:
    bootstrap-servers: "localhost:29092"
    consumer:
      group-id: "lag-lab-v1"
      auto-offset-reset: earliest
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      max-poll-records: 50
      properties:
        max.poll.interval.ms: 300000
    listener:
      type: single
      ack-mode: record
      concurrency: 1
      poll-timeout: 2s

app:
  lab:
    topic: "lag.lab.orders"
    group-id: "lag-lab-v1"
    concurrency: 1
    delay-ms: 0

management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics,prometheus"

server:
  address: "127.0.0.1"
  port: 8080
```

Explanation:

- `enable-auto-commit=false`: offsets are managed by the Spring Kafka container.
- `ack-mode=record`: for a synchronous non-transactional record listener, the container commits after each record succeeds per policy.
- `max-poll-records=50`: limits each poll to at most 50 records to cap continuous processing time between polls.
- `max.poll.interval.ms=300000`: 5-minute baseline preventing rebalances during normal exercises.
- `auto-offset-reset=earliest`: applies only when the group lacks a valid committed offset; it **does not** rewind an already-active group to the beginning.
- `concurrency=1`: makes baseline consumption easy to observe.
- `server.address=127.0.0.1`: prevents exposing the lab control HTTP API externally.
- The group ID appears in both `spring.kafka.consumer.group-id` and `app.lab.group-id` so the listener can override it explicitly; keep both aligned or consolidate into one config source in real projects.

`application-lag-lab.yml` can hold lab-profile overrides, though the baseline defaults here are already safe for localhost. The profile gates the listener and control beans in the app.

### 5.5. Listener Simulating Slow Business Processing

Create `LagLabListener.java`:

```java
package com.example.laglab;

import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Profile;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
@Profile("lag-lab")
public class LagLabListener {

    private static final Logger log =
            LoggerFactory.getLogger(LagLabListener.class);

    private final AtomicLong delayMs;
    private final AtomicLong processed = new AtomicLong();

    private final Counter processedCounter;
    private final Timer processingTimer;

    public LagLabListener(
            @Value("${app.lab.delay-ms:0}") long initialDelay,
            MeterRegistry registry) {

        this.delayMs = new AtomicLong(initialDelay);

        this.processedCounter = Counter.builder(
                        "lag.lab.processed")
                .description("Successfully processed lab records")
                .register(registry);

        this.processingTimer = Timer.builder(
                        "lag.lab.processing.duration")
                .description("Lab listener processing latency")
                .register(registry);
    }

    @KafkaListener(
            id = "lag-lab-consumer",
            topics = "${app.lab.topic}",
            groupId = "${app.lab.group-id}",
            concurrency = "${app.lab.concurrency:1}")
    public void onRecord(ConsumerRecord<String, String> record)
            throws InterruptedException {

        long startNanos = System.nanoTime();
        try {
            long sleep = delayMs.get();
            if (sleep > 0) {
                // INTENTIONAL lab delay; never ship to production!
                Thread.sleep(sleep);
            }

            long count = processed.incrementAndGet();
            processedCounter.increment();

            // Avoid logging every record so log I/O does not skew measurements.
            if (count % 500 == 0) {
                log.info(
                        "processed={}, partition={}, offset={}, delayMs={}",
                        count, record.partition(),
                        record.offset(), sleep);
            }
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw interrupted;
        } finally {
            processingTimer.record(
                    System.nanoTime() - startNanos,
                    TimeUnit.NANOSECONDS);
        }
    }

    public long getProcessed() {
        return processed.get();
    }

    public long getDelayMs() {
        return delayMs.get();
    }

    public void setDelayMs(long newDelay) {
        if (newDelay < 0 || newDelay > 5_000) {
            throw new IllegalArgumentException(
                    "Lab delay must be between 0 and 5000 ms");
        }
        delayMs.set(newDelay);
    }
}
```

**Why `AtomicLong`?** An HTTP thread updates the delay while the Kafka consumer thread reads it; `AtomicLong` provides visibility and thread safety for a simple state variable.

**Limitation:** the `processed` counter only counts within the **current JVM lifetime**, not total committed records across restarts. Durable group totals come from Kafka committed offsets. The counter also cannot prove database side effects committed because this demo only sleeps instead of writing to a DB.

**Never put `Thread.sleep` inside a real listener** to throttle production. In production, slowness is a symptom pointing to DB, network, external API, thread pool, GC, or backpressure bottlenecks; solve it via timeouts, rate limits, concurrency, and resilient architecture.

### 5.6. Local Control API to Pause, Resume, and Change Delay

Create `LagLabControlController.java`:

```java
package com.example.laglab;

import java.util.Map;

import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.kafka.config
        .KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@Profile("lag-lab")
@RequestMapping("/lab")
public class LagLabControlController {

    private final KafkaListenerEndpointRegistry registry;
    private final LagLabListener listener;

    public LagLabControlController(
            KafkaListenerEndpointRegistry registry,
            LagLabListener listener) {
        this.registry = registry;
        this.listener = listener;
    }

    private MessageListenerContainer container() {
        MessageListenerContainer result =
                registry.getListenerContainer(
                        "lag-lab-consumer");

        if (result == null) {
            throw new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE,
                    "Lab listener not registered");
        }
        return result;
    }

    @GetMapping("/status")
    public Map<String, Object> status() {
        MessageListenerContainer c = container();
        return Map.of(
                "processedSinceStartup", listener.getProcessed(),
                "delayMs", listener.getDelayMs(),
                "running", c.isRunning(),
                "pauseRequested", c.isPauseRequested(),
                "containerPaused", c.isContainerPaused());
    }

    @PostMapping("/delay")
    public Map<String, Object> setDelay(
            @RequestParam("ms") long ms) {

        if (ms < 0 || ms > 5_000) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "ms must be between 0 and 5000");
        }

        listener.setDelayMs(ms);
        return Map.of("delayMs", listener.getDelayMs());
    }

    @PostMapping("/pause")
    public Map<String, Object> pause() {
        MessageListenerContainer c = container();
        c.pause();
        return Map.of(
                "pauseRequested", c.isPauseRequested());
    }

    @PostMapping("/resume")
    public Map<String, Object> resume() {
        MessageListenerContainer c = container();
        c.resume();
        return Map.of(
                "pauseRequested", c.isPauseRequested());
    }

    @PostMapping("/stop")
    public Map<String, Object> stop() {
        MessageListenerContainer c = container();
        c.stop();
        return Map.of("stopRequested", true);
    }

    @PostMapping("/start")
    public Map<String, Object> start() {
        MessageListenerContainer c = container();
        c.start();
        return Map.of("startRequested", true);
    }
}
```

**Warning:** this API is for lab use only. Never ship consumer control endpoints to production without authentication, authorization, auditing, and strict operator access controls. Binding `server.address=127.0.0.1` limits exposure, yet does not replace security on shared hosts.

`pause()` may not finish by the moment the HTTP response returns; `isPauseRequested()` and `isContainerPaused()` have different semantics. After calling pause, wait until `containerPaused` becomes `true` before measuring.

`stop()` stops the container's consumer and affects group membership and rebalances. `pause()` in Spring Kafka continues polling underneath to keep group membership alive and avoid unnecessary rebalances. These two experiments are **not equivalent**.

---

## 6. Starting the Consumer and Establishing a Baseline

### 6.1. Running Spring Boot

With Gradle Wrapper on Linux/macOS:

```bash
./gradlew bootRun --args='--spring.profiles.active=lag-lab'
```

With PowerShell/Windows:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=lag-lab"
```

These are **sample commands for learners to run** in their own lab project.

Check the status endpoint:

```bash
curl http://127.0.0.1:8080/lab/status
```

Expect JSON similar to:

```json
{
  "processedSinceStartup": 0,
  "delayMs": 0,
  "running": true,
  "pauseRequested": false,
  "containerPaused": false
}
```

Actual state depends on broker readiness and Spring context startup. If the listener fails to start, inspect connectivity, topic, group, and exception logs before producing thousands of messages.

### 6.2. Sending Warm-Up Records to Initialize the Group

Run Kafka's producer performance tool with a small batch:

```bash
docker compose exec -T kafka /opt/kafka/bin/kafka-producer-perf-test.sh --topic lag.lab.orders --num-records 30 --record-size 128 --throughput 20 --producer-props bootstrap.servers=kafka:9092 acks=all
```

This producer generates dummy 128-byte payloads with no real data. With `delayMs=0`, the group quickly consumes and commits these records.

### 6.3. Viewing Consumer Group Offsets

```bash
docker compose exec -T kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server kafka:9092 --describe --group lag-lab-v1
```

Example output:

```text
GROUP       TOPIC           PARTITION CURRENT-OFFSET LOG-END-OFFSET LAG
lag-lab-v1  lag.lab.orders  0         11             11             0
lag-lab-v1  lag.lab.orders  1         10             10             0
lag-lab-v1  lag.lab.orders  2          9              9             0
```

Distribution of 30 records across three partitions is not fixed; this illustrates committed counts rather than guaranteeing 10 records per partition.

### 6.4. Viewing Members and Assignments

```bash
docker compose exec -T kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server kafka:9092 --describe --group lag-lab-v1 --members --verbose
```

With one consumer thread, a single group member typically receives all three partitions. With three consumer threads in the same group, assignments can split into one partition per consumer. Actual distribution depends on subscriptions, group protocols, and the assignor.

### 6.5. Why Establish a Baseline First?

If a group has never committed an offset, some Kafka CLI versions show `CURRENT-OFFSET=-`, providing no meaningful lag baseline. Sending 30 warm-up records and waiting for commits establishes a clean reference point.

Never see `-` and write "lag = 0" in a report. Record it as **offset uninitialized / not yet committed** and verify `auto.offset.reset` and group state.

---

## 7. Scenario 1: Producer Burst Increasing Lag

### 7.1. Hypothesis

- Consumer runs with `delayMs=0`, concurrency `1`.
- Producer sends a burst of several thousand records.
- Goal: observe lag climb while the producer outpaces the consumer, then drain once the consumer catches up.

Producer command:

```bash
docker compose exec -T kafka /opt/kafka/bin/kafka-producer-perf-test.sh --topic lag.lab.orders --num-records 6000 --record-size 256 --throughput 500 --producer-props bootstrap.servers=kafka:9092 acks=all
```

`throughput=500` is the tool's target rate, not a guaranteed outcome. The tool prints actual records/s; record measured numbers rather than assuming exactly 500/s.

### 7.2. Observing While the Producer Runs

Open a second terminal:

```bash
docker compose exec -T kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server kafka:9092 --describe --group lag-lab-v1
```

Repeat every few seconds. In PowerShell:

```powershell
1..10 | ForEach-Object {
    docker compose exec -T kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server kafka:9092 --describe --group lag-lab-v1
    Start-Sleep -Seconds 5
}
```

**Do not launch hundreds of CLI processes concurrently**; describing a group is an observation query and needs only modest polling intervals.

### 7.3. Recording the Experiment Table

| Timestamp | Total LOG-END-OFFSET | Total CURRENT-OFFSET | Total LAG | Notes |
|---|---:|---:|---:|---|
| t0 | Measured | Measured | Measured | Before burst |
| t1 | Measured | Measured | Measured | Producer sending |
| t2 | Measured | Measured | Measured | End of burst |
| t3 | Measured | Measured | Measured | Consumer catching up |
| t4 | Measured | Measured | Measured | Returned to baseline |

If the consumer is fast enough, lag may stay near `0` in every snapshot. That is **not a failed experiment**; it proves this load did not exceed capacity. To create a clearer backlog, move to Scenario 2 with processing delay rather than trying to generate infinite load.

### 7.4. Takeaways

- Lag rises whenever append rate exceeds group commit rate.
- Once the burst ends, lag drops if the consumer is healthy.
- A "mountain-shaped" lag curve can be completely normal for planned batches or bursts.
- Alert only when backlog/age breaches SLAs, grows continuously, or fails to catch up on time.

---

## 8. Scenario 2: Slow Business Processing

### 8.1. Setting a 100 ms Delay per Record

On Linux/macOS:

```bash
curl -X POST "http://127.0.0.1:8080/lab/delay?ms=100"
```

In PowerShell:

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8080/lab/delay?ms=100"
```

With a single consumer thread and ignoring overhead, theoretical max throughput is:

```text
1000 ms / 100 ms per record ≈ 10 records/s
```

Actual throughput is slightly lower due to polling, commits, logging, and scheduling, and although Kafka assigns three partitions, the consumer **still processes sequentially on one thread** at concurrency `1`.

### 8.2. Generating Input Faster Than the Consumer

```bash
docker compose exec -T kafka /opt/kafka/bin/kafka-producer-perf-test.sh --topic lag.lab.orders --num-records 1200 --record-size 256 --throughput 150 --producer-props bootstrap.servers=kafka:9092 acks=all
```

While the producer runs, theoretical rates are:

```text
Arrival rate ≈ 150 records/s
Consume rate ≈ 10 records/s
Lag growth ≈ 140 records/s
```

Sending 1,200 records at 150/s takes roughly eight seconds under ideal conditions; backlog near the end will be around 1,000 records. These are **estimates**, not measured tool output.

### 8.3. Key Questions to Record

- Is `LOG-END-OFFSET` climbing fast or slow?
- Is `CURRENT-OFFSET` advancing slowly or frozen?
- Does lag rise across all three partitions or concentrate in one partition?
- Are rebalances occurring? Is the group `Stable`?
- How does business method duration compare to `max.poll.interval.ms`?
- Are CPU, GC, network, or databases the real bottleneck? In the lab, we know the cause is `sleep`.

### 8.4. Lowering Delay to Catch Up

```bash
curl -X POST "http://127.0.0.1:8080/lab/delay?ms=10"
```

Theoretical consumer capacity jumps toward 100 records/s under backlog, draining lag faster. Once the producer stops, any positive consume rate eventually drains the backlog. If the producer is still emitting 150 records/s, raising capacity to 100/s **still lets lag grow**, just more slowly.

### 8.5. Reliability Lessons

In production, per-record latency can come from:

- Unindexed SQL queries or connection pool waits.
- High-p99 HTTP calls to remote APIs.
- Lock contention or overly long transactions.
- GC pauses from heavy object allocations.
- Heavy deserialization or business logic.
- Retries/backoff, circuit breakers, or poison messages.
- Slow DLT publishing.

Never "fix" this by raising `max.poll.interval.ms` unboundedly; find the latency source and address capacity, timeouts, retry budgets, bulkheads, or durable async handoffs.

---

## 9. Scenario 3: Pausing the Container While Keeping Group Membership

### 9.1. How Pause Differs from Stop

Spring Kafka supports `MessageListenerContainer.pause()`. A pause request takes effect at poll boundaries; the container continues necessary polling to maintain consumer group membership, yet **dispatches no new records** while paused.

This is ideal for testing **intentional backpressure**.

### 9.2. Steps

First reduce delay:

```bash
curl -X POST "http://127.0.0.1:8080/lab/delay?ms=0"
```

Request pause:

```bash
curl -X POST "http://127.0.0.1:8080/lab/pause"
curl "http://127.0.0.1:8080/lab/status"
```

Wait until `containerPaused=true`. If records from an active poll are still executing, the container finishes those before pausing completely.

Send 2,000 more records:

```bash
docker compose exec -T kafka /opt/kafka/bin/kafka-producer-perf-test.sh --topic lag.lab.orders --num-records 2000 --record-size 128 --throughput 200 --producer-props bootstrap.servers=kafka:9092 acks=all
```

Observe:

- `LOG-END-OFFSET` rises.
- `CURRENT-OFFSET` remains nearly static once stably paused.
- `LAG` grows proportionally.
- The consumer stays in the group and retains its partition assignment.
- Over longer periods, the broker continues receiving heartbeats/polls per container behavior.

Then resume:

```bash
curl -X POST "http://127.0.0.1:8080/lab/resume"
```

Watch lag drain as the consumer resumes processing.

### 9.3. Do Not Confuse Pause with Completed Processing

Pausing does not automatically acknowledge already-fetched records. If pause occurs mid-poll, in-flight records remain; watch `isContainerPaused` and counters.

Never call `KafkaConsumer.pause()` directly from an HTTP thread: `KafkaConsumer` is not thread-safe, and Spring Kafka provides the container API to request pause/resume safely.

### 9.4. When Is Pause Useful in Production?

- A downstream service is temporarily overloaded and expected to recover shortly.
- Brief planned database maintenance where you want to avoid consumer group rebalances.
- Throttling consumption via a circuit breaker.
- Temporarily halting ingestion while investigating a data correctness incident.

Crucial caveat: pausing **increases lag**; never leave it paused indefinitely without watching retention and SLAs. When you need to shut down the service completely or cannot keep group membership, `stop()` is more appropriate.

---

## 10. Scenario 4: Stopping and Restarting the Consumer

### 10.1. Actions

```bash
curl -X POST "http://127.0.0.1:8080/lab/stop"
```

Wait for the container to stop, then keep sending data:

```bash
docker compose exec -T kafka /opt/kafka/bin/kafka-producer-perf-test.sh --topic lag.lab.orders --num-records 1000 --record-size 128 --throughput 200 --producer-props bootstrap.servers=kafka:9092 acks=all
```

The consumer group no longer has an active member from this listener; Kafka still retains committed offsets per retention policy. Depending on CLI/version/group state, `--describe` may show group state `Empty` with existing offsets, or different output if the group expired or never committed.

Restart:

```bash
curl -X POST "http://127.0.0.1:8080/lab/start"
```

Inspect `--members --verbose` and lag.

### 10.2. How Does Stop Differ from Pause?

| Aspect | Pause | Stop |
|---|---|---|
| Consumer container still running? | Typically yes | No |
| Continues polling to keep group? | Yes, per pause mechanics | No once stopped |
| Rebalance triggered? | Usually avoided | May occur as member leaves |
| Resume speed | Typically faster | Must start and rejoin group |
| Lag while producer continues | Rises | Rises |
| Best fit | Short-lived backpressure | Longer maintenance / deployment stops |

If **two replicas share the group**, stopping one replica allows partitions to rebalance to the surviving replica; lag **may not jump immediately** because the peer handles the load. Inspect actual partition assignments to explain the behavior.

### 10.3. Do Not Wipe Committed Offsets on Restart

When a Spring Kafka container restarts normally, it resumes from the group's committed offsets. Changing the group ID during a restart creates a **brand-new subscription group** with no shared checkpoint; `auto.offset.reset` may then read from the start of retention or skip to the end.

Never change group IDs in production as a way to "clear lag."

---

## 11. Scenario 5: Concurrency vs. Partition Count

### 11.1. Basic Formula

For a topic with three partitions, the total consumer threads in a group are roughly:

```text
total consumers = replicas × concurrency per listener
```

However, active consumers processing that topic concurrently cannot exceed its assigned partitions:

```text
active consumers ≤ min(total consumers, topic partitions)
```

Example:

| Replicas | Concurrency per Pod | Total Consumers | Max Active Consumers on 3 Partitions |
|---:|---:|---:|---:|
| 1 | 1 | 1 | 1 |
| 1 | 2 | 2 | 2 |
| 1 | 3 | 3 | 3 |
| 1 | 6 | 6 | 3 |
| 2 | 2 | 4 | 3 |
| 3 | 3 | 9 | 3 |

This assumes a single topic and single group; with multiple topics or different assignors, verify actual partition assignments.

### 11.2. Raising Concurrency by Restarting the App

Stop the app and run:

```bash
./gradlew bootRun --args='--spring.profiles.active=lag-lab --app.lab.concurrency=3 --app.lab.delay-ms=100'
```

Or on Windows:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=lag-lab --app.lab.concurrency=3 --app.lab.delay-ms=100"
```

`@KafkaListener(concurrency="...")` resolves when creating the container, so it does not change dynamically via the HTTP `/lab/delay` endpoint. Restarting with updated arguments is a simple way to spin up three consumer threads in the lab.

### 11.3. Predict Before Measuring

At 100 ms/record:

- Concurrency 1: theoretical capacity ~10 records/s total.
- Concurrency 3 across 3 evenly loaded partitions: ~30 records/s total.
- Concurrency 6 with only 3 partitions: does not become 60 records/s, because at most three consumers get partitions.

Actual throughput is lower due to commits, context switching, workload skew, and broker/CPU overhead. If a downstream DB handles only 20 requests/s, scaling concurrency to 3 can trigger queues/timeouts instead of higher throughput.

### 11.4. Measuring Assignments

```bash
docker compose exec -T kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server kafka:9092 --describe --group lag-lab-v1 --members --verbose
```

Check:

- How many members exist?
- Which member has `#PARTITIONS=0`?
- Which partitions belong to each member?
- Which partition holds the lag?
- Did higher concurrency improve throughput and catch-up ETA?

### 11.5. Increasing Partition Count Has Trade-Offs

To scale beyond three partitions' throughput, you can design topics with more partitions. Yet adding partitions to a live topic **changes how keys map to partitions** for new records, which can break ordering for the same business key unless producers manage partitioning carefully.

In the lab, it is simpler to create a separate 6-partition topic with a new group to compare. In production, changing partition counts is an architectural decision requiring tests of key distribution, ordering, retention, replays, and downstream state.

---

## 12. Scenario 6: Partition Skew / Hot Key

### 12.1. Uneven Lag Distribution

Suppose a topic has three partitions and three consumers, yet the producer sends 90% of events with the same key. Kafka's default partitioner hashes identical keys to the same partition; one consumer runs "hot" while the other two sit idle.

```text
producer keys:
   customer-A 90%
   customer-B  5%
   customer-C  5%
          │
          ▼
      Kafka topic
  ┌────────┬────────┬────────┐
  │ p0     │ p1     │ p2     │
  │ 9000   │ 500    │ 500    │
  └───┬────┴───┬────┴───┬────┘
      ▼        ▼        ▼
   Worker 1 Worker 2 Worker 3

Lag p0 ↑↑↑ while p1/p2 stay near 0
```

Raising concurrency beyond three threads will not help because Kafka's ordering model never assigns one partition to multiple members of the same group concurrently.

### 12.2. Producing Records with the Same Key

The Kafka console producer supports parsing keys via a separator. For example, in PowerShell, send many messages sharing the key `hot`:

```powershell
1..1000 | ForEach-Object { "hot:event-$_" } | docker compose exec -T kafka /opt/kafka/bin/kafka-console-producer.sh --bootstrap-server kafka:9092 --topic lag.lab.orders --property parse.key=true --property key.separator=:
```

Unlike the perf test earlier, this sets an explicit key, ideal for skew experiments. For more precise rate control, write a Java producer sending `ProducerRecord<>(topic,"hot",payload)` at the desired rate.

### 12.3. How to Spot It

- Check `LAG` per partition, never just total lag.
- Run `--members --verbose` to map partitions to consumers.
- Compare processing latency across partitions.
- Inspect business key distribution without logging PII.
- If a hot key sits on one partition, adding consumer instances will not solve the root bottleneck.

### 12.4. Remediation Options

- If strict per-key ordering is mandatory, optimize processing for hot keys or rethink domain partitioning.
- If business key sharding is permitted, distribute keys more broadly and enforce ordering per shard.
- For heavy outlier events, offload or batch-process them via a durable async handoff.
- Reduce p99 latency and lock/DB contention on the hot partition.
- Never randomize keys per event when the domain requires ordered updates for the same aggregate.

---

## 13. Scenario 7: `max.poll.interval.ms` and Rebalances

### 13.1. Why Slow Consumer Processing Triggers Rebalances

A Kafka consumer must call `poll()` frequently enough to prove progress. With a synchronous record listener, if one poll returns many records and each record takes too long, the gap until the next `poll()` can exceed `max.poll.interval.ms`.

Example configuration dedicated to this experiment:

```yaml
spring:
  kafka:
    consumer:
      max-poll-records: 20
      properties:
        max.poll.interval.ms: 10000

app:
  lab:
    delay-ms: 800
```

Estimate:

```text
20 records × 800 ms = 16 seconds
max.poll.interval.ms = 10 seconds
```

When a poll returns all 20 records and processes them sequentially, elapsed time exceeds the limit. The consumer group rebalances and revokes partitions; subsequent offset commits fail, records are redelivered, and duplicate attempts plus lag spike.

**Important:** this is a **lab-only** fault-injection scenario, separate from the 5-minute baseline. Never apply these settings to production apps or groups handling critical data.

### 13.2. Observations

Monitor:

- Kafka client logs for rebalances, member leaves, and exceeded poll intervals.
- Consumer group state and member count.
- Lag stalling or jumping erratically.
- Does the processing counter keep climbing while the committed offset stays frozen?
- Do duplicate deliveries occur once partitions change ownership?

A consumer can execute business code for a record and then have its offset commit rejected after losing partition ownership. **A "processed" log line does not prove the offset committed.**

### 13.3. Proper Fixes

- Measure p95/p99 latency of the business method.
- Bound blocking HTTP/DB timeouts.
- Lower `max.poll.records` so each poll finishes within a smaller window.
- Increase concurrency **within partition and downstream capacity limits**.
- For prolonged outages, use bounded retry/backoff, pause, or async durable queues.
- Consider raising `max.poll.interval.ms` moderately when workloads genuinely need more time, balancing detection speed for wedged consumers.
- Design idempotency because rebalances and crashes cause redeliveries.

### 13.4. Do Not Confuse `max.poll.interval.ms` with `session.timeout.ms`

- `max.poll.interval.ms` governs application-level progress between `poll()` calls.
- `session.timeout.ms` governs consumer group session heartbeats so the broker detects disconnected members.
- `heartbeat.interval.ms` controls heartbeat cadence in the group protocol.
- Spring Kafka's `pollTimeout` is merely how long a single `poll()` call waits for data.

Each parameter serves a distinct role. Never tweak parameters blindly before diagnosing the symptom.

---

## 14. Distinguishing Four Backlog Patterns Using Metrics

| Observation | Likely Cause | Next Verification |
|---|---|---|
| Log end grows; committed offset grows more slowly | Consumer lacks capacity | Input/output rates, latency, partitions |
| Log end grows; committed offset frozen; group has members | Pause, poison record, long retries, blocking | Pause state, logs, consumer threads |
| Log end grows; group has no active members | Consumer stopped/crashed, bad deploy | Registry / pod health / group state |
| One partition lag huge; other partitions low | Key skew or heavy record | Per-partition lag, assignments, key distribution |
| Lag oscillates wildly with frequent rebalances | Poll interval, pod churn, network/broker | Rebalance logs, CPU/GC, deployments |
| Lag is 0 yet DB lacks records | Early ack, filter/drop, DLT, swallowed error | Transactions, dedup, DLT, reconciliation |
| Lag unchanged after raising concurrency | Too few partitions or downstream bottleneck | Active members, DB/API throughput |
| Lag jumps after restart | Reprocessing / uncommitted records | Offset commits, error handler, idempotency |

**This is a diagnostic guide**, not automated root-cause analysis. For instance, a stationary committed offset can also result from an open Kafka transaction awaiting commit or a long batch listener, not solely from pause.

---

## 15. Estimating Catch-Up Time

### 15.1. Basic Formula

Given positive backlog `L`, stable producer rate `λ`, and stable group commit rate `μ`:

```text
If μ > λ:
    catchUpSeconds ≈ L / (μ - λ)

If μ ≤ λ:
    backlog does not converge to 0 under this model
```

Example with an 18,000-record backlog:

| Producer Rate | Consumer Commit Rate | Net Drain | ETA |
|---:|---:|---:|---:|
| 0/s | 300/s | 300/s | 60 seconds |
| 100/s | 300/s | 200/s | 90 seconds |
| 200/s | 300/s | 100/s | 180 seconds |
| 300/s | 300/s | 0/s | Not shrinking |
| 400/s | 300/s | -100/s | Keeps growing |

These calculations assume steady rates with no partition skew, retry storms, or rebalances.

### 15.2. Why You Must Not Measure Throughput on an Empty Topic

When backlog is zero, even a consumer capable of 10,000 records/s will show only 10/s on dashboards if the producer emits 10/s. Treating an idle observed rate of 10/s as capacity is wrong.

Benchmark under controlled backlog, measure sustained processing throughput, and locate per-partition bottlenecks. Never extrapolate business listener throughput from producer perf tests whose payloads and DB writes are completely different.

### 15.3. Commit Rate Differs from Processed Counter

The demo app increments `lag.lab.processed` when the method finishes, whereas Kafka group offset commits happen afterward per policy. If commits fail, method successes rise while group lag stays flat.

With `AckMode.RECORD`, the gap is small under normal conditions. With `AckMode.BATCH`, `MANUAL`, transactions, or retries, the gap can be substantial. During investigations, measure **both processed rate and committed offset rate**.

---

## 16. Systematic Monitoring via the Kafka CLI

### 16.1. Viewing Offsets

```bash
docker compose exec -T kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server kafka:9092 --describe --group lag-lab-v1 --offsets
```

`--offsets` selects offset mode; depending on version, the flag can be omitted since it is typically the default.

### 16.2. Viewing Member Assignments

```bash
docker compose exec -T kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server kafka:9092 --describe --group lag-lab-v1 --members --verbose
```

### 16.3. Viewing Consumer Group State

```bash
docker compose exec -T kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server kafka:9092 --describe --group lag-lab-v1 --state
```

Typical states include `Stable`, `PreparingRebalance`, `CompletingRebalance`, or `Empty` (depending on group protocol/version). An `Empty` group does not automatically delete committed offsets.

### 16.4. Taking Time-Series Snapshots

Save timestamps and CLI outputs every 5–10 seconds. A solid experiment captures at least:

- Producer start timestamp.
- Producer completion timestamp.
- Delay/concurrency/pause change timestamp.
- Peak lag timestamp.
- Timestamp when lag drains back to target.

Never take a single snapshot during high lag and conclude "the consumer is stuck": the **trend** reveals whether the consumer is catching up.

### 16.5. Caution with New Groups

Changing the group ID from `lag-lab-v1` to `lag-lab-v2` with `auto.offset.reset=earliest` lets the new group read the entire retained log. Group v2's initial lag can look huge even when v1 was fine.

With `latest`, the new group skips existing history. Changing group IDs to hide lag numbers never fixes a business backlog.

---

## 17. Observing via Micrometer and Spring Boot Actuator

### 17.1. Demo Listener Metrics

The code registers:

- `lag.lab.processed`: Counter incremented on listener completion.
- `lag.lab.processing.duration`: Timer measuring callback duration.

With a Prometheus registry, metric names are normalized (underscores plus `_total`, `_seconds_count`, `_seconds_sum`), so inspect live output:

```bash
curl http://127.0.0.1:8080/actuator/prometheus
```

Never assume every Kafka metric renders identically across Micrometer/Spring Kafka versions. Query `/actuator/metrics` to inspect registered meter names.

### 17.2. Consumer Client Metrics

Key Kafka client metrics include:

- `records-consumed-rate`.
- `records-lag-max`.
- `fetch-rate` / fetch latency.
- `commit-rate` / commit latency where exposed.
- `assigned-partitions`.
- Rebalance-related metrics in compatible Kafka client versions.

Note that `records-lag-max` measured by the Kafka client at fetch time **is not identical** to group committed-offset lag from `AdminClient` or a consumer-group exporter. They update differently and carry distinct semantics; pick the right metric for each question.

### 17.3. Essential Operational Metrics

| Metric | Where Measured | Question Answered |
|---|---|---|
| Group committed offset lag / partition | Kafka exporter / `AdminClient` | How far behind log-end is the group? |
| Oldest-event lag age | Application / exporter / custom | How late is the oldest unread record? |
| Producer append rate | Broker / producer metrics | How fast is incoming load arriving? |
| Consumer consumed / commit rate | Kafka client + group offsets | Is real progress happening? |
| Listener processing p95/p99 | Micrometer | Where is business code slow? |
| Retry and DLT rate | Spring Kafka error handler / metrics | Are poison pills or outages happening? |
| Rebalance count / duration | Kafka client metrics / logs | Is the group stable? |
| DB latency and pool wait | Hikari / JDBC metrics | Is downstream the bottleneck? |
| CPU, heap, GC, throttling | JVM / container | Is the worker resource-starved? |
| Container pause/stop state | Spring Kafka registry / events | Is pausing intentional or an error? |
| Business reconciliation count | DB / side-effect state | Were records actually persisted accurately? |

Never put raw `orderId`, emails, or message payloads into metric labels; high cardinality explodes storage and leaks data. Keep tags bounded to cluster, topic, group, partition, service, environment, and error category.

### 17.4. Idle Does Not Mean Zero Lag

Spring Kafka emits `ListenerContainerIdleEvent` when no messages arrive during an idle interval. However:

- The topic may genuinely have no new data.
- The container may be paused.
- Another listener in the group may own the partitions.
- The deserializer or poll loop may be failing.
- When brokers are unreachable, event behavior differs across setups.

Treat idle events strictly as secondary signals. Pair them with consumer-group lag and end offsets to verify backlogs.

### 17.5. `NonResponsiveConsumerEvent`

Spring Kafka emits `NonResponsiveConsumerEvent` when the monitor detects polling is unresponsive. Unlike idle events, this targets cases where the poll loop stops progressing for an abnormal duration.

When configuring `ContainerProperties.setMonitorInterval(...)` and `setNoPollThreshold(...)`, calibrate thresholds against `pollTimeout` and workload latency. The event does not pinpoint the root cause; pair it with thread dumps, GC logs, network metrics, and application logs.

---

## 18. Operational Response When Lag Rises

### 18.1. Choosing Actions by Root Cause

| Root Cause | Priority Action | What Not to Do |
|---|---|---|
| Planned producer burst | Monitor ETA and SLA; wait to drain if capacity suffices | Panic and change group IDs |
| Intentionally paused listener | Verify reason; resume once dependency recovers | Blindly resume while DB is still down |
| Consumer stopped/crashed | Restart with valid version and credentials | Reset offsets to `latest` |
| Slow DB/API | Check p99, pools, timeouts, rate limits | Blindly raise consumer concurrency |
| Partition skew | Optimize hot keys / partitioning strategy | Add threads beyond partition count |
| Infinite retries on poison message | Classify exceptions; bounded DLT/recovery | Skip all exceptions silently |
| Rebalances from long polls | Shrink poll batch / latency; tune intervals | Raise poll interval infinitely |
| Consumer lag 0 yet DB missing data | Reconcile, enforce idempotency, fix ack timing | Treat `0` as proof of success |
| Broker/network issue | Check cluster health, leaders, request timeouts | Send more producer bursts |
| Retention nearing expiration | Prioritize preserving/replaying data safely | Purge data or reset groups recklessly |

### 18.2. Check Capacity Before Scaling

Every scaling decision should check:

1. Current partition count.
2. Active consumer threads.
3. Incoming events/s per partition.
4. p95/p99 processing latency per record.
5. DB/API capacity and connection pools.
6. Retry and DLT rates.
7. CPU, GC, and network utilization.
8. Projected catch-up ETA after scaling.

If a DB supports only 50 writes/s, scaling from 2 to 20 consumers triggers timeouts, more retries, and **worse lag**.

### 18.3. Never Sacrifice Data Correctness to Lower Lag

Two systems can both report `lag = 0` with completely different quality:

- System A commits offsets after the DB transaction commits.
- System B catches DB exceptions, logs a warning, and returns normally.

System B "eliminates lag" by dropping business work. During production incidents, always verify total outputs, deduplication counts, side-effect success, and DLT records alongside lag.

---

## 19. SLO-Driven Consumer Lag Alerting

### 19.1. Time-Based Thresholds

Suppose an SLO states "95% of orders reflect in the target system within 2 minutes." Alerting purely on `LAG > 10,000` is weak: 10,000 records clear in seconds on a fast pipeline or take hours on a slow one.

Consider alerting on:

- **Backlog age:** age of the oldest unprocessed/uncommitted record.
- **Catch-up ETA:** estimated time until backlog returns to normal.
- **Rate imbalance:** lag growing steadily across consecutive windows.
- **No-progress detection:** committed offsets frozen while a backlog exists.
- **Error/DLT anomalies:** error rates spiking even if lag drops.

### 19.2. Sample Alert Rules

These thresholds are **illustrative** and must be tuned per service:

| Alert | Condition | Meaning |
|---|---|---|
| Warning | Lag growing steadily for 10 minutes | Group cannot keep up with producer |
| Critical | No committed progress for 5 minutes while end offset grows | Likely pause, block, or poison pill |
| Warning | Catch-up ETA > 30 minutes | Risk of breaching SLA |
| Critical | Oldest unprocessed age > business deadline | SLA already impacted |
| Critical | DLT publish failed | Recovery risks data loss |
| Warning | Rebalance count abnormally high | Unstable group membership |
| Critical | Zero active members in group when service must run | Service down or misconfigured |

`no-progress` rules must exclude ultra-low traffic, uninitialized groups, empty topics, and declared planned pauses. Every alert must link to a runbook rather than displaying only a raw number.

---

## 20. Offset Resets: Dangerous Mechanics to Understand, Never to Mask Lag

Kafka CLI offers `--reset-offsets`. This **alters the committed position of a consumer group**; it does not make consumers process any faster.

### 20.1. Consequences

- Resetting to `latest` **skips unprocessed records**.
- Resetting to `earliest` triggers massive replays and potential duplicate side effects.
- Resetting by timestamp can skip or replay extra events depending on timestamps and retention.
- Resetting while a group is active is usually rejected; consumers must stop per procedure first.
- On compacted or expired topics, older offsets may no longer hold records.

### 20.2. Preview-Only in the Lab

Command that **makes no changes**:

```bash
docker compose exec -T kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server kafka:9092 --group lag-lab-v1 --topic lag.lab.orders --reset-offsets --to-earliest --dry-run
```

`--dry-run` only previews target offsets. If you ever run an actual reset in a separate exercise, use a stopped lab group, snapshot committed offsets first, understand `--execute`, and audit business replays. This lag-simulation lab **does not require executing a real reset**.

### 20.3. Never Reset Offsets When Outcomes Are Unknown

In payment or order-fulfillment pipelines, some records may already have updated the DB without committing Kafka offsets; resetting to `earliest` risks duplicate deliveries, while resetting to `latest` drops pending obligations. Require deduplication, reconciliation, and operational sign-off before any reset.

---

## 21. Error Handlers, DLTs, and "Lag Stuck at One Offset"

### 21.1. Poison Records

An unparseable or validation-failing record can make a listener fail repeatedly. If the error handler retries forever, that partition stalls while other partitions keep moving, creating skewed lag growth.

```text
Topic partition 1:
  offset 100: OK
  offset 101: BAD_JSON  ◄─ retries forever
  offset 102: OK
  offset 103: OK
  ...
```

One poison record causes **head-of-line blocking**. Raising concurrency cannot unblock partition 1 if it still has a single owner, so that partition's backlog keeps climbing.

### 21.2. Separating Transient and Permanent Errors

- Transient: DB timeouts, HTTP 503, or recoverable rate limits → bounded retries + backoff.
- Permanent: bad JSON/schema, unrecoverable business rule violations → DLT/quarantine per contract.
- Infrastructure: broken broker auth, topic ACLs, or deserializer config → operational fix, never "skip all."

### 21.3. DLT Does Not Equal Business Success

Once a record routes to the DLT and the source offset commits per recovery policy, main-topic lag may drop, yet the business event remains **unprocessed**. Ensure:

- Proper DLT topic retention and ACLs.
- Monitoring of records awaiting triage/replay.
- Stable idempotency keys for replay.
- Confirmation of DLT send success before marking recovered.
- Alerts when pending DLT items grow or exceed SLAs.

A dashboard tracking only main-topic lag hides backlogs piling up in recovery workflows.

---

## 22. Testing Redelivery and Idempotency

### 22.1. Why Does Consumer Lag Relate to Duplicate Side Effects?

Reading from Kafka and committing to a business database do not share a single distributed transaction by default:

```text
poll record
    │
    ▼
update DB
    │
    ▼
DB COMMIT succeeds
    │
    ▼
consumer crashes before Kafka offset commit
    │
    ▼
consumer restarts → redeliver same record
```

If the service increments balances, sends emails, or calls payment APIs without idempotency, redelivery executes the side effect twice.

### 22.2. Business Idempotency Keys

In production, use a stable `eventId` or business transaction ID. PostgreSQL example:

```sql
CREATE TABLE processed_events (
    consumer_group VARCHAR(120) NOT NULL,
    event_id VARCHAR(120) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_group, event_id)
);
```

Inside the same DB transaction:

```java
@Transactional
public void apply(OrderEvent event) {
    boolean firstTime =
            processedEventRepository.tryInsert(
                    "orders-worker",
                    event.eventId());

    if (!firstTime) {
        return;
    }

    orderRepository.applyBusinessChange(event);
}
```

Both operations must share **the same DB transaction**. If the deduplication insert commits while the business change fails, future redeliveries would be wrongly skipped. Because the lab listener only sleeps with no DB side effects, duplicate deliveries are harmless here; never assume production code is automatically safe.

### 22.3. When Can Offset Lag Diverge from DB Progress?

- Offset committed before DB succeeded.
- DB committed while offset commit failed.
- Listener offloads work asynchronously and returns early.
- Batch listener polls multiple records and commits at batch boundaries.
- Transactional consumer/producer offset semantics differ from non-transactional ones.
- Records routed to DLT/recovery before business completion.

Therefore, reconcile key counts and states rather than relying solely on `CURRENT-OFFSET`.

---

## 23. Testing Spring Kafka for Lag Scenarios

### 23.1. Integration Tests with `EmbeddedKafka`

Spring Kafka provides `spring-kafka-test` and `@EmbeddedKafka`. Test goals:

- The listener registers with the right group and topic.
- Increasing delay reduces throughput.
- Pausing the container halts the processed counter once in-flight records finish.
- Resuming restarts progress.
- Given enough records, committed offsets eventually catch up to log end.
- Stop/start does not accidentally alter the group ID.
- No records are lost per fixture expectations.

Skeleton:

```java
@SpringBootTest(
    properties = {
        "spring.profiles.active=lag-lab",
        "app.lab.topic=lag.lab.orders",
        "app.lab.group-id=lag-lab-test",
        "server.port=0"
    })
@EmbeddedKafka(
    partitions = 3,
    topics = "lag.lab.orders",
    bootstrapServersProperty =
            "spring.kafka.bootstrap-servers")
class LagLabIntegrationTest {

    @Autowired
    KafkaListenerEndpointRegistry registry;

    @Test
    void listenerIsRegistered() {
        var container =
                registry.getListenerContainer(
                        "lag-lab-consumer");

        assertNotNull(container);
    }
}
```

Key imports:

```java
import static org.junit.jupiter.api.Assertions.assertNotNull;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.test.context.EmbeddedKafka;
```

This skeleton verifies bean/container registration only; **it does not yet prove lag behavior**. To test offset lag, send real messages, query committed offsets/log-end via `AdminClient` or consumer group APIs, and await asynchronous delivery with bounded timeouts.

### 23.2. Awaitility / Eventual Assertions

For asynchronous consumers, avoid:

```java
Thread.sleep(100);
assertEquals(100, listener.getProcessed());
```

because startup and poll timing are non-deterministic. Use Awaitility or a bounded polling helper:

```java
await()
    .atMost(Duration.ofSeconds(30))
    .untilAsserted(() ->
        assertEquals(100, listener.getProcessed()));
```

Add the corresponding Awaitility test dependency if used. When running multiple tests in the same context, reset or capture baseline counters so counts from earlier tests do not interfere.

### 23.3. Testing Pause/Resume

Steps:

1. Send warm-up records and wait for commits.
2. Call `pause()` and wait until `isContainerPaused() == true`.
3. Send 100 more records.
4. Confirm committed offsets stay static during the measurement window.
5. Call `resume()` and wait for all records to process and commit.
6. Verify no unexpected errors or rebalances occurred.

**Never assert that `pause()` freezes the counter synchronously the instant it is called**, because already-polled or in-flight callbacks can finish first.

### 23.4. Testing Processing Delay and Capacity

- Run 1 consumer with a 100 ms delay; send 200 records.
- Measure total time and commit rate for the 200 records.
- Re-run in isolation with concurrency 3 across 3 partitions and evenly distributed keys.
- Compare throughput without assuming an exact 3x speedup.
- Monitor JVM CPU/GC/network and broker send rates to rule out unrelated bottlenecks.

### 23.5. Testing Rebalances and Failover

- Start two instances in the same group on a 3-partition topic.
- Gracefully stop or crash one instance.
- Observe assignments shifting to the surviving instance.
- Verify no records are lost in the lab.
- When DB side effects exist, verify idempotency across redelivered records.
- Confirm group IDs and topic subscriptions stay unchanged during rolling deploys.

### 23.6. Testing Hot Partitions

- Send hundreds of records sharing key `hot`.
- Record the key's actual partition via producer metadata or consumer logs.
- Confirm lag concentrates on one partition.
- Raise concurrency above partition count and observe the hot-partition bottleneck persists.
- Test processing optimizations or partitioning strategies allowed by ordering constraints.

### 23.7. Testing Failures with a DLT

- Send invalid payloads with a bounded-retry error handler and DLT.
- Verify main-topic lag drains once the record recovers to the DLT.
- Verify the DLT receives the record and supports a replay workflow.
- Simulate DLT broker/ACL failures to guard against "false recovery success."
- Verify zero duplicate business side effects on redelivery.

---

## 24. Operations Runbook: Responding to a Consumer Lag Alert

### Step 1 — Identify Scope and Impact

Record:

```text
environment:
cluster:
topic:
consumerGroup:
alertTimeUtc:
businessSla:
totalLag:
maxPartitionLag:
oldestEventAge:
activeGroupMembers:
deployVersion:
```

Never stop at total lag; inspect which partitions lag and how late business data is.

### Step 2 — Measure Current Velocity

Take two or three snapshots 30–60 seconds apart:

- Is log-end increasing?
- Is the current committed offset advancing?
- Is lag growing, shrinking, or flat?
- Does the group have active members?
- Are p99 processing latencies or retries climbing?
- Is DLT/recovery backlog growing?

If lag is shrinking with an acceptable ETA, emergency intervention may be unnecessary.

### Step 3 — Inspect Topology

- Is the consumer group ID right?
- Are assignments active as expected?
- Do consumer threads outnumber partitions?
- Does one partition carry a hot key?
- Are pods experiencing CPU throttling, OOMs, restarts, or GC pauses?
- Are frequent rebalances occurring?
- Did someone intentionally pause the container?

### Step 4 — Pinpoint the Bottleneck

Separate three tiers:

1. **Upstream:** producer burst or sustained rate increase.
2. **Consumer:** deserialization, processor, retries, batch size, offset commits.
3. **Downstream:** DB/API/cache/storage rate limits, locks, network.

Never increase concurrency before confirming downstream can absorb the extra load.

### Step 5 — Choose Recovery

- Planned pause: verify dependency health, then resume.
- Consumer crash: restore service and confirm group membership.
- Slow DB/API: cut latency, add capacity, or throttle requests.
- Producer burst: if backlog fits SLA, monitor drain.
- Hot partition: adjust partition key strategy or worker model safely.
- Poison message: bounded retries + DLT/quarantine per policy.
- Long processing: reduce poll size or redesign asynchronously.
- Retention risk: prioritize safe data preservation/replay with proper permissions rather than reckless offset resets.

### Step 6 — Verify Recovery

Close the incident only when:

- Lag drains to target levels and stabilizes.
- Oldest-event age is back within SLA.
- Consumer members and assignments are stable.
- Retries, DLT rate, and DB errors drop back to normal.
- Business data reconciles completely.
- Zero records remain "offset committed without business effect executed."

### Step 7 — Document Prevention

Capture the incident timeline: producer rate, commits/s, peak lag, catch-up time, root cause, canary/rollback actions, resource limits, and follow-up improvements. Add load and recovery tests to prevent recurrence.

---

## 25. Quick Diagnostic Table

| Symptom | Check First | Appropriate Action |
|---|---|---|
| `CURRENT-OFFSET=-` | Has the group ever committed? | Establish baseline; check reset policy |
| Lag grows steadily | Incoming rate > commit rate? | Measure capacity and bottlenecks |
| Lag stays flat after producer stops | Consumer paused, blocked, or retrying? | Inspect registry, logs, thread dumps |
| Lag concentrated on one partition | Key skew / hot partition? | Check assignments and producer keys |
| Lag spikes after deploy | Group ID, offset policy, or exceptions changed? | Diff configuration and rebalances |
| Lag = 0 yet data is missing | Early ack, DLT, or swallowed exceptions? | Reconcile business data |
| Consumer "running" yet not polling | `max.poll.interval`, blocking call? | Check no-poll events and thread dumps |
| Many records in DLT | Permanent validation, schema, or infra error? | Triage, fix, and replay |
| Every restart replays many records | Infrequent commits or crashes pre-commit | Check ack timing and idempotency |
| Raising concurrency does not cut lag | Partition count or DB capacity limit? | Check active members and partitions |
| Lag climbs during DB failover | Retries/backoff, connection pools | Restore DB, apply throttling |
| Producer tool achieves low rate | Broker or host resource limit | Measure actual producer throughput |
| Topic invisible from Spring Boot | Wrong Kafka `advertised.listeners` | Fix host/container listener config |
| Group describe shows zero members | Container stopped / group empty | Check app status and subscriptions |

---

## 26. Mistakes That Skew Lab Results

### 26.1. Confusing Committed Offset with Consumer Position

Consumer position can advance simply by fetching/polling records while the committed offset lags behind. `kafka-consumer-groups.sh` reports group-committed progress. When measuring business throughput, inspect application-side processing completions alongside offset commits.

### 26.2. Leaving Auto-Commit On in a Reliability Lab

With `enable.auto.commit=true`, offsets commit on a timer even if business work has not finished. Dropping lag does not prove data succeeded. This lab explicitly uses `enable.auto.commit=false` and `AckMode.RECORD` to keep semantics clear.

### 26.3. Testing Against a Group That Never Committed

A fresh group can report `-` or no committed state; calling that `lag=0` is inaccurate. Always send warm-up records to establish committed offsets or note that the group is uninitialized.

### 26.4. Sending Unbounded Load

Producer bursts should set explicit `--num-records` and `--throughput` against a local broker. Never run infinite producer loops that fill disks, stress retention, and destabilize your workstation.

### 26.5. Using Production Payloads

Never use customer PII, payment cards, or access tokens to benchmark throughput. Kafka logs retain payloads for days, and lab brokers lack production security controls.

### 26.6. Changing Group IDs to "Clear Lag"

A new group ID starts with separate offsets. With `reset=latest`, lag looks small only because past data was skipped—not because the consumer became faster.

### 26.7. Setting Concurrency Above Partition Count

Active consumers cannot exceed the partition count of a topic within one group. Excess concurrency sits idle while still wasting resources and adding operational noise.

### 26.8. Watching Only Total Lag

A total lag of 10,000 could be spread evenly across ten partitions or piled onto one partition. Scaling options and catch-up times differ completely.

### 26.9. Raising `max.poll.interval.ms` Without Fixing Slow Processing

Doing so reduces slow-processing rebalances, yet delays detecting genuinely wedged consumers. Balance timeouts, batch sizes, circuit breakers, and alerts together.

### 26.10. Treating Pause and Stop as Identical

Pause keeps polling and group membership alive per container mechanics; stop terminates membership. Both produce distinct rebalance and lag profiles and must be tested separately.

### 26.11. Comparing Only "Processed" Log Counts

Logs can fire before transaction commits, or a listener invocation can repeat across redeliveries. True reliability checks require committed offsets and business state.

### 26.12. Hiding Errors in a DLT and Calling It Success

A DLT protects main-topic progress from poison records, yet those failed events still require resolution. Zero lag on the main topic does not mean all business obligations succeeded.

---

## 27. Lab Results Template

When running the lab, record **actual measured numbers**, never theoretical estimates.

| Scenario | Input Record Count | Producer Measured r/s | Consumer Concurrency | Delay ms | Peak Lag | Catch-Up Time | Rebalance Count |
|---|---:|---:|---:|---:|---:|---|---:|
| Baseline | Measured | Measured | 1 | 0 | Measured | Measured | Measured |
| Burst | 6,000 | Measured | 1 | 0 | Measured | Measured | Measured |
| Slow listener | 1,200 | Measured | 1 | 100 | Measured | Measured | Measured |
| Slow + 3 consumers | 1,200 | Measured | 3 | 100 | Measured | Measured | Measured |
| Pause | 2,000 | Measured | 1 | 0 | Measured | Measured | Measured |
| Stop/start | 1,000 | Measured | 1 | 0 | Measured | Measured | Measured |
| Hot key | 1,000 | Measured | 3 | 100 | Measured per partition | Measured | Measured |
| Poll interval fault | Measured | Measured | 1 | 800 | Measured | Measured | Measured |

Include environment details:

```text
Kafka version:
Spring Boot version:
Spring Kafka version:
JVM version:
OS/Docker resource limits:
Topic partitions:
Consumer group:
Producer payload size:
Consumer max.poll.records:
Consumer max.poll.interval.ms:
AckMode:
Date/time and timezone:
```

This metadata is essential for reliable comparisons across runs. Without payload sizes, CPU/disk limits, or group IDs, it is easy to misattribute throughput gains to a config change.

---

## 28. Advanced Exercises

### Exercise 1 — Calculating Lag Rate

Producer emits 800 records/s while the group processes 500 records/s for 10 minutes. Estimate the accumulated lag and drain time once the producer stops and the group sustains 500/s. Cross-check with section 2's formula.

### Exercise 2 — ETA Under Sustained Load

Backlog is 120,000 records; producer keeps sending 200/s while consumer processes 500/s. Compute the ETA. When consumer throughput drops to 180/s due to a DB bottleneck, explain why the backlog diverges.

### Exercise 3 — Pause vs. Stop

With identical input counts, compare lag and rebalance counts after pause/resume vs. stop/start. Why might planned short maintenance favor pause?

### Exercise 4 — Active Consumer Count

On a 3-partition topic, run one replica with concurrency 1, 2, 3, and 6. Record member counts, assignments, and consumption rates. Explain why concurrency 6 does not yield six active consumers.

### Exercise 5 — Hot Partition

Send 90% of records with the same key against three consumers. Tabulate per-partition lag and propose a mitigation that preserves business ordering.

### Exercise 6 — Poll Interval

With `max.poll.records=100`, p99 processing latency 500 ms, and potential retry/backoff adding 90 seconds, compute a conservative per-poll bound. Choose `max.poll.interval.ms` and ways to lower rebalance risk.

### Exercise 7 — Lag 0 Yet Missing Side Effects

Modify a test listener to catch a DB exception and return normally. Observe offsets advancing while the DB lacks records. Fix the listener to propagate exceptions and add idempotency; explain the difference.

### Exercise 8 — Poison Pill

Inject schema-invalid JSON events with a `DefaultErrorHandler` configured for bounded retries + DLT. Demonstrate main-topic lag clearing after recovery while the DLT holds pending items needing triage.

### Exercise 9 — Monitoring

Design a dashboard displaying group lag, max partition lag, lag age, consumed rate, processing p99, retry/DLT rates, rebalances, and DB pools. Define an alert for "lag rising while group remains running."

### Exercise 10 — Rolling Deploy

Deploy two replicas sharing one group in a test environment and stop one replica at a time. Observe assignments, rebalances, and duplicate deliveries; specify idempotency requirements for the business writer.

### Exercise 11 — Capacity Planning

Given a 12-partition topic, producer rate 1,200/s, p99 record processing 20 ms, and downstream capacity capped at 600 requests/s, calculate theoretical consumer needs, identify the real bottleneck, and propose load shedding or downstream scaling.

### Exercise 12 — Runbook

Write a one-page consumer lag incident runbook branching on: app stopped, wrong group ID, slow DB, hot partition, poison pill, and broker outage. Each branch must cite metric evidence before action.

---

## 29. Cleaning Up the Lab Environment

When finished, stop the Spring Boot consumer (Ctrl+C in the app terminal). Do not leave a background consumer running if you want clean backlog comparisons next time.

Stop the local broker:

```bash
docker compose down
```

This stops and removes containers and networks created by Compose; depending on volume settings, Kafka data may be lost when containers are removed. **Never run `docker compose down -v` if a volume holds data you need**, and never run cleanup commands without confirming your terminal is in the exact lab directory and Compose project.

To rerun experiments with clean committed offsets, purposefully create a **new lab group ID** and document `auto.offset.reset`. Never use production group IDs or reset production offsets.

---

## 30. References

- [Apache Kafka — Basic Kafka Operations](https://kafka.apache.org/44/operations/basic-kafka-operations/): `kafka-consumer-groups.sh --describe`, `--offsets`, `--members --verbose`, `--state`, and offset resets.
- [Apache Kafka — Consumer Configuration](https://kafka.apache.org/documentation/#consumerconfigs): `max.poll.records`, `max.poll.interval.ms`, commits, and group settings.
- [Apache Kafka — Consumer Group Protocol](https://kafka.apache.org/documentation/): partition assignment, offset commits, and membership.
- [Spring Kafka 3.3 — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/3.3/kafka/receiving-messages/message-listener-container.html): concurrency, ack modes, polling, and offset semantics.
- [Spring Kafka — Pausing and Resuming Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/pause-resume.html): `pause()`, `resume()`, and continued polling while paused.
- [Spring Kafka — Application Events](https://docs.spring.io/spring-kafka/reference/kafka/events.html): idle, non-responsive, pause, and resume events.
- [Spring Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html): retries, `DefaultErrorHandler`, and recovery.
- [Spring Kafka — Dead Letter Publishing](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html): `DeadLetterPublishingRecoverer` and DLT reliability.
- [Spring Kafka — Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html): `@EmbeddedKafka` and test utilities.
- [Spring Kafka — Micrometer Observation](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html): listener and producer observations/metrics.
- [Spring Boot 3.4 — Kafka Support](https://docs.spring.io/spring-boot/3.4/reference/messaging/kafka.html): `spring.kafka.*` configuration.
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): meter registry, Prometheus endpoint, and instrumentation.
- [Apache Kafka Docker Official Image](https://hub.docker.com/r/apache/kafka): running the Kafka broker in Docker in an isolated environment.

## 31. Conclusion

**Simulating consumer lag** makes visible behaviors that stay hidden when everything runs smoothly: committed offsets differ from polled positions, lag grows whenever arrival rates outpace committed processing rates, pause differs from stop, concurrency is capped by partition count, and a single hot key or poison pill can stall progress despite multiple consumers.

This lab walked from a local Kafka broker, an adjustable-delay Spring Boot listener, and `kafka-consumer-groups.sh` through burst, slow-processing, pause, stop, skew, and rebalance experiments alongside recovery workflows. In production, watch **lag trends, event age, ETA, processing latency, retries/DLTs, resource saturation, and business outcomes** together—never shrink lag figures by resetting offsets or swallowing exceptions.

A reliable consumer group is more than "lag at zero." It must **process every required record, avoid duplicating side effects on redelivery, meet SLAs, and follow a clear runbook whenever backlogs rise**.
