# Graceful Rolling Deployment in Spring Kafka

## 1. Why Can Rolling Deployments Still Cause Consumers to Misprocess?

A Spring Kafka system runs three `orders-consumer` replicas sharing the `orders-workers` consumer group. Each replica consumes partitions from `orders.events`, updates a database, and acknowledges offsets after processing. Operations wants to upgrade the application version without halting stream processing system-wide.

A Kubernetes `Deployment` using `RollingUpdate` replaces old Pods with new Pods in waves. However, **Kubernetes rolling updates do not automatically guarantee that Kafka consumers finish in-flight records or commit offsets safely**. When an old Pod receives a termination signal, there may still be records buffered from the latest `poll()`, an open transaction, an in-flight HTTP call, or a `CompletableFuture` running on another thread pool.

A flawed rollout can produce this sequence:

```text
Consumer A (v1)                        Consumer B (v2)
-------------------------------        ----------------------------
polls offset 104                       New Pod starts
writes DB for offset 104               joins same consumer group
Pod A receives SIGTERM                 rebalance begins
JVM killed with SIGKILL before commit 105  receives partition from A
                                       re-reads offset 104
                                       writes DB a second time
```

This is **at-least-once behavior with possible redelivery**, not necessarily a Kafka bug. If business logic is not idempotent, the same record can double-credit balances, send duplicate notifications, or create duplicate transactions. Conversely, if the app **commits offsets before side effects are truly durable**, a crash can lose unfinished business work.

The goals of *graceful rolling deployment* are:

1. Have old Pods/consumers stop **accepting new work** along a supported lifecycle path.
2. Let in-flight work finish or hand off cleanly via controlled retries.
3. Commit only **truly safe** offsets under your ack mode and transaction semantics.
4. Let the consumer group transfer partition ownership to surviving or newly created members.
5. Ensure any redeliveries run safely via idempotency.
6. Maintain overall availability, monitor consumer lag, and retain a rollback plan.

**Graceful does not mean absolute zero duplicates, zero rebalances, and zero latency.** It is a discipline for reducing risk, shrinking disruption windows, and controlling remaining failure windows.

## 2. Lifecycle Layers Involved in a Rollout

```text
Kubernetes Deployment
   | RollingUpdate: creates new Pod, selects old Pod to terminate
   v
Kubernetes Pod / container runtime
   | readiness, preStop (if any), SIGTERM, grace deadline
   v
Java process / Spring ApplicationContext
   | closes context, stops SmartLifecycle beans
   v
Spring Kafka listener container
   | completes callbacks per stop policy, handles ack/commit,
   | closes KafkaConsumer, leaves group
   v
Kafka consumer group
   | rebalance / partition reassignment
   v
New Pod consumes from committed offsets
   | idempotency protects against redelivery
   v
Business DB / external services
```

Each layer has its own timeout. For instance, Kubernetes may grant a 90-second grace period while Spring Kafka's container waits at most 10 seconds under default config, or Spring Boot waits 30 seconds per shutdown phase while a callback blocks on a 120-second API call. Therefore, design an **end-to-end shutdown budget**, not just a huge `terminationGracePeriodSeconds`.

### 2.1. Availability vs. Correctness

| Aspect | Question | Example Pass Criteria |
|---|---|---|
| Pod availability | Are enough replicas ready per Kubernetes? | `maxUnavailable` and readiness satisfy rollout strategy. |
| Consumer availability | Does the consumer group have active members owning partitions? | Members active; assignments re-established. |
| Processing correctness | Did records finish before offsets were committed? | Side effects durable before ack/commit; retries safe. |
| Business correctness | Do reprocessed records cause duplicate outcomes? | Unique keys, idempotency keys, or reconciliation. |
| Recovery | When a Pod is force-killed, does the system recover cleanly? | Broker retains records, group reassigns, handler retries/DLTs properly. |

Kubernetes readiness probes typically govern **Service traffic routing**, not direct Kafka broker partition assignment. A consumer can keep calling `poll()` even when marked `NotReady`. Likewise, a `Ready` Pod does not prove it owns partitions or has caught up on consumer lag.

## 3. How Does a Normal Rolling Deployment Proceed?

Suppose a Deployment has three v1 Pods, a six-partition topic, and `concurrency=2` per Pod. Before rollout, up to six consumer instances share the group, with partitions distributed via group assignment.

```text
Before rollout:
  v1-Pod-A  -> 2 consumer threads
  v1-Pod-B  -> 2 consumer threads
  v1-Pod-C  -> 2 consumer threads

Rollout with maxSurge=1, maxUnavailable=0:
  1. Create v2-Pod-D, wait until Pod becomes Ready.
  2. D can join the consumer group -> rebalance.
  3. Select one v1 Pod to terminate.
  4. Old Pod receives SIGTERM -> Spring closes listener container.
  5. Group adjusts assignment; remaining members continue consuming.
  6. Repeat for remaining v1 Pods.

Expected outcome:
  v2-Pod-D/E/F running; Pods A/B/C have left the group.
```

With `maxSurge=1`, total consumers temporarily **exceed Kafka partition counts**; having some idle consumers without assignments is normal. Therefore, **never require every consumer to hold a partition for readiness**, or surge Pods will never turn Ready and rollouts will deadlock. At the same time, HTTP server readiness does not prove Kafka producers/consumers are healthy if your workload requires Kafka-specific checks.

`maxUnavailable=0` maintains Ready Pod counts by **Kubernetes definitions**; it does not guarantee 100% Kafka throughput or zero rebalance pauses. Membership changes during a rolling update normally cause brief lag fluctuations.

## 4. How Does Spring Kafka Shut Down Listener Containers?

Listeners created from `@KafkaListener` are typically managed by `KafkaListenerEndpointRegistry`. Listener containers implement `SmartLifecycle`, starting and stopping with the `ApplicationContext`.

During a normal Spring Boot shutdown, the framework stops `SmartLifecycle` beans by phase. Spring Kafka containers stop fetching, close Kafka consumers, and handle commits per configuration. Final behavior depends on **ack mode**, handler exceptions, callback duration, and whether any async work runs outside the container.

### 4.1. `stopImmediate` and Records from the Last Poll

Spring Kafka `ContainerProperties` provides `stopImmediate`:

| Value | Record Listener Behavior When Stopped | Trade-Off |
|---|---|---|
| `false` (default in Spring Kafka 3.x) | Typically finishes processing records already fetched from the last `poll()` before stopping. | Drains the poll batch cleanly; shutdown can take long if `max.poll.records` is large or records are slow. |
| `true` | Stops after the current record rather than finishing all records from the last poll. | Faster shutdown; unprocessed records are redelivered when the group resumes, per ack/offset semantics. |

For example, if one `poll()` returns 100 records taking 200 ms each and stop is requested after the first record, `stopImmediate=false` may spend roughly 20 seconds finishing the batch; `true` stops sooner while leaving remaining records for replay.

**`false` does not guarantee shutdown waits forever.** If the process receives `SIGKILL`, hangs inside a callback, or hits timeouts, the container still cannot finish cleanly. For batch listeners, a single invocation receives a list of records as one unit; `stopImmediate=true` cannot interrupt mid-callback.

### 4.2. `shutdownTimeout`

`ContainerProperties.setShutdownTimeout(long)` caps how long (in milliseconds) to wait for container shutdown. In Spring Kafka 3.3, the default is typically **10,000 ms**. A callback taking 25 seconds needs a larger timeout if you intend to let it finish during shutdown.

Distinguish three limits: container `shutdownTimeout`, Spring's lifecycle phase timeout, and Kubernetes' `SIGKILL` deadline are **three separate bounds**. `shutdownTimeout` does not cancel a hung HTTP request; configure timeouts and cancellation directly on HTTP/JDBC clients inside the listener.

### 4.3. `pause()` Is Not `stop()`

`MessageListenerContainer.pause()` stops dispatching records to the listener once pause takes effect. While paused, the container keeps calling `poll()` at the `KafkaConsumer` level to retain group membership; therefore **pausing does not release partition assignments** to new Pods.

| API | Use Case | Leaves Consumer Group? |
|---|---|---|
| `pause()` | Temporarily halt record delivery, e.g., backpressure or coordinated draining. | No; container keeps polling to stay in the group while paused. |
| `resume()` | Resume receiving records after pausing. | No; continues in the same group. |
| `stop()` | Stop container via lifecycle, closing consumer and allowing partition reassignment. | Normally yes, as consumer closes/leaves group or session expires. |
| `ApplicationContext` shutdown | Stops container lifecycles, then closes remaining resources by phase. | Normally triggers a graceful group leave. |

`pauseImmediate` is a separate setting: when pausing, it decides whether to halt delivery after the current record or after the entire poll batch. It is **not the same** as `stopImmediate` and does not manage application shutdown.

If implementing a **drain-before-stop** protocol, an orchestrating layer can call `pause()`, wait for `isConsumerPaused()` or `ConsumerPausedEvent` plus in-flight work to reach zero, and then call `stop()` on an **orchestration thread**. Never call consumer control APIs from inside a Kafka listener callback and block waiting for that same callback to finish—that risks deadlocks or stalling polls.

## 5. Offset Commits and Ack Modes Determine Replay Scope

With `enable.auto.commit=false`, Spring Kafka containers support different `AckMode`s. Understand when offsets commit before assuming a stop means "zero lost records."

| Ack Mode | Typical Commit Point | Notes During Rolling Updates |
|---|---|---|
| `RECORD` | Commits offset after the listener finishes each record (for record listeners). | Easy to reason about completed progress; higher commit overhead. |
| `BATCH` (common default for record listeners) | Commits after processing all records from one poll. | Fewer commits; crashing mid-batch redelivers processed-but-uncommitted records. |
| `MANUAL` | Listener calls `Acknowledgment.acknowledge()`; container applies commit rules. | Ack only after business work completes; avoid forgotten or premature acks. |
| `MANUAL_IMMEDIATE` | Ack commits immediately when invoked on the consumer thread, per config. | Understand calling threads, sync/async commits, and side-effect timing. |

`enable.auto.commit=true` makes the Kafka client commit offsets periodically on its own timer, decoupling commits from business completion. Pipelines needing explicit at-least-once guarantees normally set `enable.auto.commit=false` and pick an explicit ack mode.

### 5.1. At-Least-Once and the Duplicate Window

```text
1. Consumer receives record offset 200.
2. Business DB transaction commits successfully.
3. JVM is killed BEFORE Kafka offset 201 commits successfully.
4. Replacement consumer receives offset 200 again.

=> Zero lost records, yet duplicate processing can occur.
```

The proper fix is **idempotent business processing**, not forcing Kafka to commit early. Committing offsets before durable processing risks losing work if the process dies between offset commit and business transaction commit.

### 5.2. Final Commits Are Not Guaranteed Under Shutdown Timeouts

When asked to stop, the container tries to finish/commit per ack mode and callbacks; however, if a DB transaction blocks, the consumer loses partition ownership, a rebalance intervenes, or broker connectivity drops, the commit can fail. Always monitor commit/rebalance errors and design safe replays.

`CommitFailedException`, `RebalanceInProgressException`, transaction fencing, and interrupted callbacks must be diagnosed per client/handler version. Commit retries may help in some cases, yet infinite retries cannot succeed once a consumer has lost partition ownership.

### 5.3. Kafka Transactions and Exactly-Once

For **Kafka consume → Kafka produce** pipelines using Kafka transactions and transactional offsets properly, Spring Kafka/Kafka supports exactly-once semantics within the Kafka transaction scope. This **does not automatically extend** to an atomic transaction across Kafka offsets and databases, HTTP calls, or third-party APIs.

When using transactional producers during rolling updates, manage `transactional.id`/`transaction-id-prefix` carefully to avoid **unintended producer fencing** between old and new Pods overlapping during surge windows. Never reuse one fixed transactional ID across two concurrently active processes; design transaction identity per replica and concurrency.

## 6. Spring Boot 3.x / Spring Kafka 3.x Example: Synchronous Consumer

This example targets Java 17+, Spring Boot 3.x, and Spring Kafka 3.x. It illustrates a **synchronous record listener**—a clean baseline before introducing asynchronous worker pools. Property values are illustrative; tune to your SLAs and dependencies.

### 6.1. `application.yml`

```yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 60s

  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    consumer:
      group-id: orders-workers
      enable-auto-commit: false
      auto-offset-reset: earliest
      properties:
        max.poll.records: 100
        max.poll.interval.ms: 300000
        session.timeout.ms: 45000
    listener:
      ack-mode: record

server:
  shutdown: graceful

management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,info
```

**Explanation:**

- `timeout-per-shutdown-phase` caps how long Spring waits for each `SmartLifecycle` stop phase; it is not necessarily the entire shutdown total.
- `server.shutdown=graceful` governs primarily the embedded web server; Kafka listener containers have their own lifecycle and timeout.
- `max.poll.records=100` bounds records returned per client poll; it does not turn each record into a transaction.
- `max.poll.interval.ms` must cover actual time between polls including full batch processing and backoff; otherwise the consumer risks eviction and rebalancing.
- `session.timeout.ms` obeys broker/group protocol bounds and has no universal optimum. Raising it does not speed up callbacks and delays detecting sudden consumer crashes.
- `auto-offset-reset=earliest` **applies only when the group lacks a valid committed offset**; normal rollouts resume from committed offsets rather than replaying from the start.
- Actuator readiness endpoints exist only when corresponding dependencies and configs are present; they reflect your defined health model, not Kafka partition assignments.

### 6.2. Container Factory with Shutdown Policy

```java
import org.springframework.boot.autoconfigure.kafka.ConcurrentKafkaListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.ContainerProperties;

@Configuration
class OrdersKafkaContainerConfig {

    @Bean("ordersKafkaListenerFactory")
    ConcurrentKafkaListenerContainerFactory<String, String> ordersKafkaListenerFactory(
            ConcurrentKafkaListenerContainerFactoryConfigurer configurer,
            ConsumerFactory<String, String> consumerFactory) {

        var factory = new ConcurrentKafkaListenerContainerFactory<String, String>();
        configurer.configure(factory, consumerFactory);

        factory.setConcurrency(2);
        factory.getContainerProperties().setAckMode(
                ContainerProperties.AckMode.RECORD);
        factory.getContainerProperties().setStopImmediate(false);
        factory.getContainerProperties().setShutdownTimeout(45_000L);

        return factory;
    }
}
```

Here `shutdownTimeout=45s`, Spring lifecycle phase is `60s`, and the Kubernetes example below uses a `90s` grace period. This is an **illustrative budget with headroom**, not a magic guarantee of clean shutdown. With a 2-minute callback or an unbounded network call, Pods will still be killed at the deadline.

`setConcurrency(2)` creates up to two consumer instances for the container; total group members depend on Pod counts, other listeners, and partition counts. When concurrency exceeds assigned partitions, extra threads sit idle. Never require every child consumer to hold an assignment for readiness.

### 6.3. Listener Returning Only After Business Completion

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrdersEventConsumer {

    private final OrderProcessingService orderProcessingService;

    OrdersEventConsumer(OrderProcessingService orderProcessingService) {
        this.orderProcessingService = orderProcessingService;
    }

    @KafkaListener(
            id = "ordersConsumer",
            topics = "orders.events",
            groupId = "orders-workers",
            containerFactory = "ordersKafkaListenerFactory")
    public void onRecord(ConsumerRecord<String, String> record) {
        orderProcessingService.applyIdempotently(
                record.key(), record.value());
        // RECORD ack mode: container may commit after method returns.
    }
}
```

`OrderProcessingService.applyIdempotently(...)` is **application-implemented logic**, not a Spring Kafka API. It must finish the business transaction and deduplicate **before** returning. On unrecovered errors, let exceptions propagate to the configured error handler rather than swallowing them and returning normally.

Simple PostgreSQL idempotency mechanism:

```sql
CREATE TABLE processed_order_event (
    event_id VARCHAR(128) PRIMARY KEY,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Within the SAME business transaction as the business mutation:
INSERT INTO processed_order_event (event_id)
VALUES (:eventId)
ON CONFLICT (event_id) DO NOTHING;
```

Real service code must check **whether the row was inserted or already existed** to decide whether to apply the business mutation. Inserting the marker and still applying the mutation anyway still duplicates side effects. `event_id` must stay stable across retries/redeliveries per your data contract; never generate a fresh random UUID on consume.

If the marker and business update live in **different databases or transactions**, re-evaluate your idempotency guarantees. The marker must share a consistent transaction boundary with the side effect it protects.

## 7. Kubernetes Deployment Example Using RollingUpdate

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-consumer
spec:
  replicas: 3
  revisionHistoryLimit: 5
  progressDeadlineSeconds: 600
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: orders-consumer
  template:
    metadata:
      labels:
        app: orders-consumer
    spec:
      terminationGracePeriodSeconds: 90
      containers:
        - name: orders-consumer
          image: example/orders-consumer:1.0.0
          imagePullPolicy: IfNotPresent
          ports:
            - containerPort: 8080
          env:
            - name: KAFKA_BOOTSTRAP_SERVERS
              valueFrom:
                configMapKeyRef:
                  name: kafka-connectivity
                  key: bootstrap-servers
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            periodSeconds: 5
            failureThreshold: 24
          resources:
            requests:
              cpu: "250m"
              memory: "512Mi"
            limits:
              memory: "1Gi"
```

This YAML is an **illustrative template requiring** ConfigMap `kafka-connectivity`, web/Actuator on port 8080, Kafka brokers, and matching security configuration. `example/...` is a placeholder image; do not use verbatim. Timeouts, CPU/RAM, and replica counts illustrate coordination only and must be sized to actual record processing durations.

### 7.1. `maxSurge` and `maxUnavailable`

- `maxSurge: 1`: allows one extra Pod above desired replicas during rollout, giving capacity to start new Pods before terminating old ones.
- `maxUnavailable: 0`: Kubernetes keeps Ready Pods at least equal to desired replicas during rollout. It does not guarantee consumer lag stays flat or prevent group rebalances.
- When partitions are fewer than temporary total consumers, new surge Pods can still become Ready without owning partitions; that is acceptable.
- `progressDeadlineSeconds` marks stalled rollouts; it does not replace consumer lag or error monitoring.

### 7.2. Readiness, Liveness, and Startup Probes

| Probe | What It Should Answer | What Not to Infer |
|---|---|---|
| Startup | Has the app finished starting enough for liveness/readiness checks? | Backlog is not necessarily drained. |
| Liveness | Does the process need a restart due to an unrecoverable state? | Transient Kafka broker faults rarely justify killing the Pod immediately. |
| Readiness | Is the Pod fit to receive traffic/participate per health policy? | Ready does not guarantee partition assignments. |

If liveness depends too tightly on Kafka broker health, a brief outage can **trigger fleet-wide Pod restarts**, fueling extra rebalances. Health policies should separate transient disconnects, intentional consumer pauses, and genuinely deadlocked processes.

In consumer-only workloads receiving no HTTP traffic, readiness still supports rollout gating and observability, though `NotReady` does not stop Kafka `poll()`. To drain Kafka explicitly, use listener container APIs or shutdown lifecycle hooks.

### 7.3. Why Is `preStop` Unnecessary in Every Application?

Kubernetes runs `preStop` hooks (if defined) **before** sending `SIGTERM`, and `preStop` duration counts against `terminationGracePeriodSeconds`. A naive `sleep 30` hook does not stop Kafka consumers; they keep polling during the sleep and leave less time for Spring shutdown afterward.

Add `preStop` only with a **tested, bounded drain protocol**—for example, hitting an internal endpoint that puts the app in draining mode, stops listener containers, and returns once in-flight work completes, coordinated with the subsequent `SIGTERM` and overall budget. Never call non-existent endpoints or close consumers from a record-processing thread while blocking on it.

### 7.4. Java Must Receive the Termination Signal

Docker images should invoke Java directly or use `exec` in shell wrappers so PID 1 receives signals properly:

```dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

If an entrypoint uses a shell script without `exec`, verify `SIGTERM` actually reaches the JVM and closes the Spring context. Processes run fine normally while silently failing graceful shutdown if a wrapper swallows signals.

## 8. Designing the Shutdown Time Budget

A graceful setup is trustworthy only when every timeout comes from **real measurements**. Let:

- `T_preStop`: hook duration before OS sends signal (if used).
- `T_listener`: max time for listeners to finish in-flight work after stop is requested.
- `T_commit`: time to flush/ack/commit and close Kafka consumers and DB connections.
- `T_other`: shutdown of HTTP server, executors, publishers, caches, telemetry, and other resources.
- `T_margin`: buffer for scheduling, GC, network jitter, and outliers.

A starting estimation rule:

\[
T_{KubernetesGrace} > T_{preStop} + T_{listener} + T_{commit}
   + T_{other} + T_{margin}
\]

This is a **conservative budget**, not an exact formula computed by Spring or Kubernetes. Some shutdown phases overlap while others run sequentially; observe actual lifecycles to avoid miscounting. Note also that `spring.lifecycle.timeout-per-shutdown-phase` applies **per phase**, not necessarily across total shutdown time.

### 8.1. Estimating Drain Time from `max.poll.records`

For sequential record listeners, an approximate upper bound for finishing one poll batch is:

\[
T_{pollBatch} \approx N_{polled} \times T_{record,pessimistic}
\]

For instance, with `max.poll.records=100` and p99 per-record latency of 300 ms, if all 100 records hit that latency, draining takes ~30 seconds **before** commit/flush. If each record can hit a 3-second timeout, one poll batch can take minutes and miss a 90-second grace deadline.

| Option | Throughput Impact | Shutdown Impact |
|---|---|---|
| Lower `max.poll.records` | May increase poll frequency/overhead or trim batch throughput. | Shrinks max work buffered per poll. |
| `stopImmediate=true` | No steady-state impact, alters stop behavior. | Stops after current record; requires accepting replay of unprocessed items. |
| Per-item HTTP/DB timeouts | Prevents callbacks hanging forever. | Bounds processing/rollback time under failures. |
| Idempotent writers | May add DB/unique-constraint overhead. | Makes redelivery safe, easing pressure for 100% drain. |
| Larger grace period | No throughput gain. | Buys time, but slows rollouts and holds resources longer. |
| Async pipeline with drain protocol | Higher concurrency, more complexity. | Must track in-flight futures and cleanly complete or roll back. |

**Never inflate `max.poll.interval.ms` just to mask slow shutdowns.** It governs max intervals between consumer group polls, not Kubernetes termination deadlines; a slow blocking listener still gets killed by the Pod grace period.

### 8.2. Sample Budget with Headroom

Suppose benchmarks show the largest normal poll batch takes 25 seconds, flush/commit takes at most 5 seconds, and closing other resources takes 10 seconds. You might budget:

```text
Kubernetes terminationGracePeriodSeconds  = 90 s
Spring lifecycle timeout per phase        = 60 s
Kafka listener container shutdownTimeout  = 45 s
Normal poll batch drain                   = 25 s
Commit + cleanup                          = 5–10 s
Margin                                    = remainder
```

If callbacks occasionally take 120 seconds, this config is insufficient. Either tighten request timeouts, shrink poll batches, adjust stop policy, or rely on safe replay. Never treat `90` in YAML as "graceful solved" without testing shutdown under active load.

## 9. Consumer Group Rebalances When Replacing Pods

Kafka assigns partitions to consumer group members. As new Pods join and old Pods leave, Kafka performs **rebalances** to redistribute partitions. This is a normal part of rolling updates, not an error to "fix" by restarting all Pods.

### 9.1. Eager vs. Cooperative Rebalancing

| Assignment Style | High-Level Behavior | Rollout Impact |
|---|---|---|
| Eager rebalance | Members may revoke many partitions while the group reassigns. | Wider processing pauses during membership transitions. |
| Cooperative / incremental rebalance | Revokes only partitions that must move when supported by the assignor. | Shrinks disruption scope, though pauses/rebalances still occur. |

Kafka clients provide assignors such as `CooperativeStickyAssignor`; using it requires **the entire consumer group to support compatible strategies** and follow Kafka's documented migration sequence. Never flip `partition.assignment.strategy` mid-rollout across mixed versions where old and new members disagree on protocols.

Example property once the group is designed for it:

```yaml
spring:
  kafka:
    consumer:
      properties:
        partition.assignment.strategy: org.apache.kafka.clients.consumer.CooperativeStickyAssignor
```

This is a **conditional option**, not mandatory for every app. Newer Kafka client/protocol versions manage consumer group protocols and assignors differently, so align with your broker/client versions. Where heterogeneous consumers share a group, verify compatibility before rolling out.

### 9.2. Rebalance Listeners Are Not for Heavy Work

Spring Kafka supports rebalance callbacks like `ConsumerAwareRebalanceListener` to observe partition assignment/revocation and run hooks around commits per contract. These callbacks run inside the consumer lifecycle—never put unbounded HTTP calls or million-row reconciliation jobs here.

Appropriate tasks include:

- Recording metrics for assigned/revoked partitions, rebalance duration, and permitted member IDs.
- Flushing local state **only when genuinely needed and supported**, under bounded timeouts.
- Confirming processed/acked records per ack mode without committing offsets for work still running on another thread.

Kafka revoking a partition does not roll back external database transactions. If async work continues after revocation, enforce strict ownership/idempotency rules and never call `Consumer.commitSync(...)` arbitrarily from another thread.

### 9.3. Static Membership (`group.instance.id`)

Static membership reduces rebalances when a consumer restarts quickly with the same identity. With Spring Kafka's `ConcurrentMessageListenerContainer`, setting `group.instance.id` alongside `concurrency > 1` causes the framework to append `-n` suffixes per child consumer.

**Warning for Kubernetes Deployments:** Pod names change on rollouts; if every replica shares one fixed `group.instance.id`, Kafka **fences members** due to duplicate identity. Likewise, expecting unstable Deployment Pod identities to persist across rollouts is a flawed assumption. Static membership requires identities that are **unique across concurrently active consumers and stable across restarts**, which fits StatefulSets or platforms offering stable identities far better.

Raising `session.timeout.ms` curbs brief-restart rebalances at the cost of slower crash failover; balance availability against dead-member detection time. Never use static membership as a substitute for proper shutdown and idempotent outputs.

## 10. Long-Running Listeners, Batch Listeners, and Offset Ordering

### 10.1. Long-Running Callbacks

Suppose a listener calls an external service taking 40 seconds per record. If a poll returns 100 records, `stopImmediate=false` blows past termination budgets. Instead of raising timeouts endlessly, consider:

1. Setting connection, read, and overall timeouts on HTTP/gRPC/DB calls.
2. Reducing `max.poll.records` if throughput allows.
3. Offloading slow work to a system with dedicated work ownership and ack semantics.
4. Using `stopImmediate=true` with idempotent processing to accept fast replay.
5. Measuring p95/p99 latency and testing `SIGTERM` under heavy backlogs.

`max.poll.interval.ms` must cover actual time between polls. If callbacks routinely run too long and the consumer loses membership, later commits fail even though business logic finished.

### 10.2. Batch Listeners Receiving a List of Records

With `@KafkaListener` in batch mode, one callback processes an entire list. The container cannot abort a running Java method mid-execution via `stopImmediate=true`. If a business batch takes 3 minutes, either budget enough time or design internal checkpoints/idempotency with timeouts and cancellation.

Under `AckMode.BATCH`, commits follow poll-batch completion rules. If a listener processes half a batch and returns normally, the framework **may consider the entire batch done**; never return normally while records remain safely unprocessed.

### 10.3. Manual Ack and Async Acks

Calling `Acknowledgment.acknowledge()` before DB transactions commit risks advancing offsets ahead of business writes. Offloading work to a thread pool and returning from the listener means **method return does not prove work finished**. Some async ack modes permit out-of-order completion yet demand strict shutdown and rebalance controls.

```text
Consumer thread                Worker thread
  receive offset 50              process offset 50...
  submit task -------->          calls API/DB
  returns immediately            not yet complete
  container stop
  worker result arrives after stop -> ack may no longer be valid
```

In Spring Kafka 3.2+, listeners can return `CompletableFuture` or reactive types with framework support for async completion. Still, **never assume stopping the consumer container automatically awaits all custom app executor work**, especially on custom thread pools. Check version docs on stopping/draining and add explicit in-flight wait logic when needed.

An async drain protocol typically enters `DRAINING`, stops accepting new work, waits for `inFlight` to hit zero within a timeout, flushes/acks safe outcomes, stops the container, and then shuts down executors. Explicitly specify what happens to pending futures on timeout—never report "drained" merely because the consumer thread stopped.

## 11. Retries, DLT, and In-Flight Work Across Version Transitions

Spring Kafka commonly uses `DefaultErrorHandler`, retry/backoff, and dead-letter publishing for fault handling. During rolling updates, failing records mid-retry can encounter shutdown or rebalances. Understand your error policy before deciding ack or stop behavior.

| Scenario | Possible Consequence | Required Design |
|---|---|---|
| Error handler retrying the same record | Shutdown mid-retry redelivers the record to a new member. | Idempotent retry side effects and reasonable backoff. |
| Retries routed to retry topics | Work waits in another topic across deployment versions. | Both v1 and v2 schemas/handlers must support retry payloads. |
| DLT publish succeeds | Record preserved for investigation/reprocessing per config. | DLT retention, alerts, correlation, and controlled re-drive. |
| DLT send succeeds, source offset uncommitted | Restart may publish to the DLT a second time. | DLT consumer/producer idempotency and clear delivery semantics. |
| Shutdown during long backoff | Delays stop or interrupts for replay. | Align error handlers/backoff with lifecycle and deadlines. |

**Never swallow exceptions just to speed up rollouts.** If a business record neither succeeded nor recovered under an approved policy, never return cleanly and commit its offset. Conversely, once safely published to a DLT under an approved recovery policy, preserve evidence and re-drive tooling.

### 11.1. Compatibility Between Two Application Versions

During a rolling update, v1 and v2 run **concurrently** on the same topic/group for a transition window. If v2 makes incompatible changes to message schemas, deserializers, or database schemas, records delivered to v1 mid-rollout will fail.

Safe upgrades usually follow **expand → migrate → contract**:

1. Teach v1 consumers to tolerate v2 data or keep producers on compatible schemas.
2. Run additive database migrations compatible with both versions.
3. Rolling-deploy v2 consumers and watch group/retry/DLT metrics.
4. Only after every v1 instance exits and rollback windows close, drop legacy fields/tables or enable breaking formats.

Kafka records **carry no "deliver to v2 only" tag** when two versions share one group. Never rely on Pod rollout order to route records to matching code.

## 12. Observability During Rolling Deployments

Never rely solely on `kubectl rollout status` to declare Kafka processing healthy. Watch these signals **before, during, and after** rollout:

| Signal | What to Verify |
|---|---|
| `Ready` / `Terminating` Pods | Is Kubernetes maintaining availability per strategy? |
| Consumer group members & assigned partitions | Are members active with assignments and expected thread counts? |
| Consumer lag & lag growth rate | Does backlog climb during rebalances or approach SLA limits? |
| Records consumed/s & p95/p99 latency | Did v2 degrade throughput? |
| Offset commit latency/failures | Are commits failing or spiking during shutdowns/rebalances? |
| Rebalance count/duration | Is the rollout triggering excessive or prolonged rebalances? |
| Producer errors / transaction fencing | If producing/transacting, are identity or transactional ID errors occurring? |
| Retries, DLT, deserialization errors | Did v2 introduce schema or handler failures? |
| Duplicate suppression / idempotency conflicts | Are redeliveries controlled without duplicate surges post-rollout? |
| Shutdown duration & forced kills | Were Pods terminated by `SIGKILL` after grace timeout? |
| DB pool / locks / HTTP timeouts | Do side effects finish cleanly before listeners return? |

Structured technical lifecycle logs should use consistent fields:

```text
deployment.shutdown.requested pod=orders-consumer-abc version=v1
kafka.listener.stop.requested listenerId=ordersConsumer
kafka.listener.stopped listenerId=ordersConsumer elapsedMs=18800
deployment.shutdown.completed pod=orders-consumer-abc elapsedMs=21400

kafka.partition.assigned group=orders-workers topic=orders.events partition=3
kafka.partition.revoked group=orders-workers topic=orders.events partition=3
```

These lines show a **suggested format**, not exact built-in Spring log lines. Never log full payloads or access credentials to debug rollouts. If a process crashes before emitting `shutdown.completed`, inspect Kubernetes termination reasons/exit codes alongside Kafka group metrics.

**Keep metric cardinality bounded:** use low-cardinality labels like `application`, `version`, `listenerId`, and `topic`. Never label by per-message keys, payloads, or random request IDs. Pod IDs help in logs and short-lived metrics, provided monitoring backend retention/cardinality stay bounded.

### 12.1. Defining a Successful Rollout

Testable completion criteria include:

- All target Pods run v2 and are `Ready` per policy.
- Zero v1 members remain in the consumer group once rollout finishes.
- Lag returns to baseline or below SLO thresholds within an agreed window.
- Error, timeout, and DLT rates show no abnormal increase over pre-deploy baselines.
- Zero evidence of lost business outcomes; any duplicates were absorbed by idempotency.
- Old Pod shutdown times stayed within grace periods with no unexpected `SIGKILL`s.

If criteria fail, halt or roll back per runbook. **`kubectl rollout undo` does not erase data side effects already written by v2**; maintain separate data, schema, and message compatibility rollback plans.

## 13. Spring Kafka Integration Testing for Graceful Shutdown

Handler unit tests do not prove the container awaits callbacks or commits offsets on shutdown. At least one integration test must run a real listener container against a test broker, request stop mid-callback, and assert outcomes.

### 13.1. Dependencies and Environment

Gradle Groovy example with Spring Boot dependency management:

```groovy
dependencies {
    implementation 'org.springframework.kafka:spring-kafka'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`@EmbeddedKafka` runs an in-process test broker; Testcontainers Kafka is also great for more realistic containerized broker testing. Use **unique topics and group IDs per test suite** so prior tests never leave offsets that skew subsequent tests.

### 13.2. Testing Container Stop Mid-Callback

Use `CountDownLatch` in a test listener to confirm the callback is actively running, invoke container stop, and release the callback only after stop is requested. This is far **more deterministic than `Thread.sleep(3000)`**.

```java
// In test configuration of a @SpringBootTest + @EmbeddedKafka.
@Component
class ControlledOrderListener {

    final CountDownLatch entered = new CountDownLatch(1);
    final CountDownLatch mayFinish = new CountDownLatch(1);
    final AtomicInteger completed = new AtomicInteger();

    @KafkaListener(
            id = "controlledOrders",
            topics = "orders-rolling-it",
            groupId = "orders-rolling-it-group")
    public void onMessage(String value) throws InterruptedException {
        entered.countDown();

        if (!mayFinish.await(15, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Test release timeout");
        }

        completed.incrementAndGet();
        // In real systems, replace with a durable business transaction.
    }
}
```

Test logic:

```java
@Autowired KafkaTemplate<String, String> kafkaTemplate;
@Autowired KafkaListenerEndpointRegistry registry;
@Autowired ControlledOrderListener listener;

@Test
void gracefulStopAllowsCurrentCallbackToFinish() throws Exception {
    kafkaTemplate.send("orders-rolling-it", "order-1")
            .get(10, TimeUnit.SECONDS);

    assertTrue(listener.entered.await(15, TimeUnit.SECONDS));

    MessageListenerContainer container =
            registry.getListenerContainer("controlledOrders");
    assertNotNull(container);

    CompletableFuture<Void> stopped = new CompletableFuture<>();
    container.stop(() -> stopped.complete(null));

    assertFalse(stopped.isDone(),
            "Container should still be stopping while callback is blocked");

    listener.mayFinish.countDown();
    stopped.get(20, TimeUnit.SECONDS);

    assertEquals(1, listener.completed.get());
}
```

Required imports include `CountDownLatch`, `AtomicInteger`, `TimeUnit`, `CompletableFuture`, `KafkaListenerEndpointRegistry`, `MessageListenerContainer`, Spring Kafka `@KafkaListener`, `@Component`, and JUnit assertions. These are **snippets meant for a test class** assuming a Spring `ApplicationContext` with `ControlledOrderListener`, String serializers/deserializers, `KafkaTemplate`, and broker wiring.

Points to maintain:

1. Use `entered` to prove the callback started before stopping.
2. Call `stop(Runnable callback)` and await completion; never block the consumer thread with control calls.
3. Use `mayFinish` so tests can release the callback without hanging.
4. Set finite timeouts on broker ACKs, listener startup, and container stop.
5. **Never infer committed offsets and zero duplicates** solely from `completed=1` and stop completion. Verify offsets/state separately.

`assertFalse(stopped.isDone())` asserts within the latch-held callback window, relying on container stop contracts and thread scheduling. In real suites, add dedicated probes for ordering guarantees and release `mayFinish.countDown()` in a `finally` block so failing assertions never leak threads.

### 13.3. Verifying Offsets and Redeliveries After Stop/Restart

To truly prove at-least-once delivery with zero lost work, start a new consumer with **the same `group.id`** after the old container stops and inspect committed offsets or redelivered records per scenario:

| Scenario | Expectation |
|---|---|
| Callback finishes, ack/commit succeeds, then stops | New consumer resumes after committed offset without reprocessing that record. |
| Callback interrupted before business work finishes and before ack | Record may be redelivered to the new consumer. |
| Business DB committed, Kafka offset uncommitted | Record may redeliver; idempotency prevents duplicate side effects. |
| Listener catches exception and returns success wrongly | Offset advances, losing business work. Tests must catch this bug. |

Inspect committed offsets via Kafka `AdminClient` or a dedicated consumer after the group stabilizes, using APIs matching your client version. Never deduce committed offsets from `auto.offset.reset=earliest`; that applies only when no valid committed offset exists.

### 13.4. Testing `stopImmediate=true`

With `max.poll.records` large enough, send multiple records and call stop while the first callback runs. With `stopImmediate=true`, verify:

- The active callback finishes within timeout.
- Unprocessed records from the poll are **reprocessed** after restart per ack/offset policy, never lost.
- Final business row counts match with zero duplicates via unique business keys or data assertions.
- When a callback throws, the error handler still governs retries/DLT without blindly committing all offsets.

Never assert that the listener processes **strictly one record** after stop across all scheduling races: a stop request can arrive just as the container steps to the next record. Synchronize via latches/record IDs and assert final Kafka/DB state.

## 14. Testing Deployments on Kubernetes / Real Processes

`@EmbeddedKafka` cannot fully simulate `SIGTERM`, `SIGKILL`, Pod lifecycles, network partitions, or multi-process group rebalances. Run staging tests with a **persistent test Kafka broker across multiple Pods** and isolated business data.

### 14.1. Realistic Rolling Update Scenario

```text
Setup:
  - Test topic has 6 partitions.
  - 3 v1 consumer Pods, concurrency 2.
  - Producer emits records with stable eventId.
  - Business DB has unique eventId for reconciliation.

Test:
  1. Run steady workload and record baseline throughput/lag.
  2. Start rolling update v1 -> v2, maxSurge=1/maxUnavailable=0.
  3. Watch partition revoke/assign, consumer lag, commits,
     shutdown duration, and Pod termination reasons.
  4. Wait for all v2 Pods Ready and old Pods terminated.
  5. Wait for lag to return to baseline; reconcile event IDs/DB output.

Pass criteria:
  - Zero lost business events;
  - Any duplicates handled by idempotency;
  - Zero Pods force-killed with SIGKILL due to shutdown timeout;
  - Throughput and error rates meet SLOs.
```

Sample observation commands in an **authorized test/staging** Kubernetes environment:

```bash
kubectl rollout status deployment/orders-consumer -n batch-staging
kubectl get pods -n batch-staging -l app=orders-consumer -o wide
kubectl describe deployment orders-consumer -n batch-staging
kubectl logs -n batch-staging deployment/orders-consumer --tail=200
```

Watching rollout status alone does not prove correctness; reconcile published business event IDs against committed DB outputs. Commands like `kubectl rollout restart` or `kubectl rollout undo` are **mutating operations** and must follow staging/deployment procedures.

### 14.2. Grace Exhaustion Scenario: Force-Killing a Test Process

Test the worst case:

1. Pause a listener while processing a record with a controlled DB side effect.
2. On an **isolated test process/Pod**, simulate zero cleanup window (e.g., killing the container via a chaos test workflow).
3. Observe Kafka group session/rebalances, record redelivery, and DB state.
4. Confirm final state shows **zero loss and zero unintended duplicates** thanks to idempotency.
5. Record failure-detection time and lag recovery duration.

Never kill production Pods or the JVM hosting your JUnit runner for this test. Expect retries/redeliveries rather than graceful-path completion after a hard kill.

### 14.3. Testing Alongside Database Migrations and Schema Changes

Run v1 and v2 simultaneously in one group while producers emit records under the published schema. Confirm both versions deserialize and process cleanly. Run additive (expand) DB migrations before the rolling update; contract schemas only after v1 is completely gone and rollback windows close.

This test is essential because **rolling updates intentionally run two versions side-by-side**. A graceful infra rollout still fails en masse if a breaking message or DB schema change slips in.

## 15. Deployment and Rollback Runbook

### Pre-Rollout

1. Verify the new version is compatible with v1 across event schemas, retry topics, DLTs, and databases.
2. Check partitions, replicas, concurrency, and DB capacity; confirm `maxSurge` stays within resource budgets.
3. Confirm listener callbacks have timeouts, explicit ack modes, and idempotent writers.
4. Size `max.poll.records`, p99 latency, and `shutdownTimeout`/Spring lifecycle/Kubernetes grace budgets.
5. Capture baseline lag, records/s, retry/DLT rates, consumer members, and commit failures.
6. Confirm staging shutdown logs show containers finishing before `SIGKILL`.
7. Prepare rollback commands and rollout-halt thresholds if lag/errors breach SLOs.

### During Rollout

1. Launch v2 Pods and watch startup, readiness, and deserialization/auth/transaction-fencing errors.
2. As v1 Pods terminate, trace `SIGTERM` → listener stop → consumer group leave.
3. Watch rebalance count/duration, assignments, lag shifts, and post-takeover offsets.
4. If v2 causes data corruption or DLT spikes, **pause/roll back the rollout per runbook** rather than looping restarts via liveness probes.
5. Never force-delete old Pods merely because they are draining a normal poll batch; diagnose why shutdown exceeded budget if genuinely hung.

### Post-Rollout

1. Verify all v1 Pods exited; group members and assignments are stable.
2. Wait for consumer lag and latency to return within targets inside the allotted window.
3. Reconcile business event IDs/DB outputs and verify duplicates were safely suppressed.
4. Inspect retry/DLT events emitted by v1 that may still await v2 processing.
5. Record rollout metrics to refine timeouts, concurrency, or `max.poll.records` next time.

### When Rollback Is Required

Rolling back an image version does not automatically roll back database migrations or already-written side effects. Verify old code can still read/process data created by v2. If schemas already crossed a breaking threshold, execute a **roll-forward fix**, compatibility adapter, or controlled data recovery rather than relying on `kubectl rollout undo` alone.

## 16. Common Mistakes

| Symptom | Possible Cause | Fix |
|---|---|---|
| Pod killed by `SIGKILL` despite `RollingUpdate` | 30s grace insufficient or Spring/container shutdown timeout too short. | Measure drain time, increase budget, shrink poll batch/external timeouts. |
| Pod `Ready` yet processes no messages | No partition assignment, more consumers than partitions, or rebalance unfinished. | Check group members/partitions; never equate HTTP readiness with Kafka assignment. |
| Rollout stalls because surge Pod never turns Ready | Readiness requires assigned partitions in a saturated group. | Fix health contract; avoid requiring partitions on every Pod. |
| Consumer lag spikes during rollout | Rebalance/pause delay, slower v2 throughput, or producer burst. | Measure rebalance duration, processing rate, DB waits, and error handlers. |
| Record processed twice after Pod replacement | DB committed before Kafka offset commit, followed by redelivery. | Idempotency/unique business keys and commit-crash window testing. |
| Business record lost while Kafka offset advanced | Early ack/commit before side effects, or swallowed exception. | Ack only after durable processing; audit error handling. |
| After `pause()`, new Pod gets no partitions | Paused consumers still poll to stay in the group. | Use `stop()`/shutdown lifecycle to leave the group, not `pause()`. |
| Stop takes long despite `stopImmediate=false` | Listener drains remaining poll records and/or callbacks block. | Measure `max.poll.records` × latency, add timeouts, tune stop policy. |
| Fast stop causes records to replay | `stopImmediate=true`; uncommitted poll records were not acked. | Often expected behavior; rely on idempotency and verify committed offsets. |
| Consumers rebalance continuously | Replicas/concurrency oversized, slow polls, or liveness restart storms. | Inspect membership churn, `max.poll.interval`, probes, and assignment strategy. |
| Static membership gets fenced | Duplicate `group.instance.id` across live Pods. | Assign unique, stable identities via StatefulSets or account for rollout overlap. |
| Transactional producers fenced during v1/v2 overlap | Identical transactional IDs across two instances. | Make prefix/transaction IDs unique per active instance and concurrency. |
| Async callbacks keep running after container stops | `stop()` does not wait for custom executors or in-flight futures. | Implement version-aware drain protocols awaiting completion or rely on idempotent replay. |
| DLT surges post-rollout | Broken schema/handler or retry-topic compatibility. | Test v1/v2 mixed mode, monitor closely, and roll back if needed. |
| `preStop` sleep burns the grace period | Hook sleeps before `SIGTERM` while consumer keeps polling. | Remove useless sleeps or implement a real bounded drain endpoint. |
| Rolled-back v1 fails on new events | v2/producer wrote breaking schema to Kafka. | Use expand-contract and dual compatibility before emitting breaking formats. |
| `maxUnavailable=0` still sees brief message pauses | Kubernetes maintains Ready Pods while Kafka still rebalances. | Budget SLOs/lag for rebalances; use cooperative assignment where compatible. |

## 17. Framework for Choosing Among Drain, Fast Stop, and Replay

Reliable systems select shutdown policies to fit the workload:

| Consumer Type | Typical Sound Policy | Mandatory Preconditions |
|---|---|---|
| Short records, transactional DB writes | `stopImmediate=false`, `AckMode.RECORD`, or benchmarked mode. | Idempotency, DB commit completes before ack. |
| Very long records, tight Pod deadlines | `stopImmediate=true` or smaller poll size with per-call timeouts. | Uncommitted records safe to replay; idempotent side effects. |
| Batch listeners doing bulk writes | Drain active callback if possible with bounded timeouts. | Real transaction atomicity; test batch failures. |
| Async workers / `CompletableFuture` | Custom in-flight drain protocol checking version-specific semantics. | Never ack early; keep executors open until in-flight tasks finish. |
| Kafka-to-Kafka transactional pipelines | Properly configured Kafka transactions/EOS. | Unique transaction identities, compatible brokers/clients. |
| Consumers calling payment/email/external APIs | Prioritize idempotency first, stop policy second. | Receiver-enforced idempotency keys and reconciliation. |

Every choice balances **maximum drain duration**, redelivery rates, rollout latency, temporary lag spikes, and duplicate-handling costs. Long grace periods never replace correctness; safe replay is usually far more practical than attempting to eliminate all redelivery risk.

## 18. Hands-On Exercises

### Exercise 1 — Measure a Rolling Deployment with Graceful Shutdown

Create a six-partition test topic, three `orders-consumer` Pods with concurrency 2, and a steady producer. Run a `RollingUpdate` with `maxSurge=1`, `maxUnavailable=0`, and a 90-second grace period. Measure rebalance duration, consumer lag, and per-Pod stop time. Explain why business outputs must still be reconciled after Kubernetes reports rollout complete.

### Exercise 2 — Compare Both `stopImmediate` Settings

Write a latch-controlled listener that holds one record mid-processing. Send 20 records and test `stopImmediate=false` vs. `true` in separate test suites. Measure stop time, records processed before shutdown, and records redelivered after restarting in the same group. Never deduce results from listener invocation counts alone; reconcile committed offsets and DB rows.

### Exercise 3 — Crash Between DB Commit and Kafka Offset Commit

Build `OrderProcessingService` storing business results and idempotency markers in the same transaction. Simulate a hard crash in a separate test process after DB commit yet before offset commit, then start a replacement consumer. Prove the record can redeliver while the database records strictly one business outcome.

### Exercise 4 — Calculate a Termination Budget

Given `max.poll.records=200`, 300 ms per record, 8s commit+cleanup, 5s `preStop`, and 12s other framework shutdown, estimate the minimum budget with reasonable margin. Analyze what happens if an HTTP call has a 120s timeout, and how to adjust poll size, stop policy, and timeouts.

### Exercise 5 — Rebalances and Readiness

Create a group with six partitions, six consumer instances, and one surge Pod adding two consumers. Observe assignments when consumers outnumber partitions. Test a readiness rule requiring partition assignment and explain why rollouts deadlock. Design a readiness rule matching the workload's real needs.

### Exercise 6 — Breaking Schema Rollback

Design two consumer versions: v1 reads `v1` events, v2 reads `v1` and `v2`. Plan producer and database upgrades via expand-contract so v1 and v2 coexist during rollout. Simulate a v2 defect and roll back; identify when rolling back to v1 is safe vs. when a roll-forward is required.

## 19. Key Principles to Remember

1. **Kubernetes `RollingUpdate` does not guarantee Kafka record-level correctness.** It orchestrates Pod replacement, not business transactions or offset commits.
2. **`SIGTERM` must reach the JVM and close the Spring context.** `SIGKILL` skips shutdown hooks; always design safe replay.
3. **Spring Kafka listener containers use `SmartLifecycle`**, requiring a shutdown budget sized to poll-batch processing times.
4. **Default `stopImmediate=false` usually drains fetched poll records before stopping; `true` stops after the current record.** Test both against your actual ack mode.
5. **`pause()` does not release partitions.** Containers keep polling to remain in the group; `stop()` is how containers leave for reassignment.
6. **Business work must be durable before ack/offset commit** to avoid losing work; expect redeliveries under at-least-once semantics.
7. **Idempotency matters more than trying to eliminate duplicates completely**, especially for databases and APIs outside Kafka transactions.
8. **Readiness is not consumer partition assignment.** Surge Pods can be Ready without partitions; never build health gates that deadlock rollouts.
9. **Grace periods cover `preStop` and multiple shutdown phases.** Measure real durations, leave margin, and enforce I/O timeouts.
10. **Test active processing, stopping, rebalancing, redelivery, and rollback.** Never treat `kubectl rollout status` as proof that data was processed accurately.

## 20. Official References

- [Spring Kafka Reference — Listener Container Properties](https://docs.spring.io/spring-kafka/reference/3.3/kafka/container-props.html): `stopImmediate`, `shutdownTimeout`, `pauseImmediate`, `pollTimeout`, and ack-related settings.
- [Spring Kafka Reference — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html): `SmartLifecycle`, offset commits, `AckMode`, concurrency, and static membership.
- [Spring Kafka Reference — Pausing and Resuming Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/pause-resume.html): `pause()`, `resume()`, and `isConsumerPaused()`.
- [Spring Kafka Reference — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html): `DefaultErrorHandler`, retries, stopping error handlers, and recovery.
- [Spring Kafka Reference — Asynchronous Listener Return Types](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/async-returns.html): async completion/acks and container drain limits.
- [Spring Kafka Reference — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html): scope of Kafka transactions/EOS.
- [Spring Boot Reference — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html): `spring.lifecycle.timeout-per-shutdown-phase` and web server shutdown.
- [Kubernetes Documentation — Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/): rolling updates, `maxSurge`, `maxUnavailable`, and rollout availability.
- [Kubernetes Documentation — Termination of Pods](https://kubernetes.io/docs/concepts/workloads/pods/pod-termination/): `preStop`, grace periods, `SIGTERM`/`SIGKILL`, and endpoint behavior.
- [Spring Kafka Reference — Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html): `@EmbeddedKafka` and integration testing.
- [Apache Kafka Consumer Configuration](https://kafka.apache.org/documentation/#consumerconfigs): `max.poll.records`, `max.poll.interval.ms`, `group.instance.id`, assignment strategies, and commit behavior.


