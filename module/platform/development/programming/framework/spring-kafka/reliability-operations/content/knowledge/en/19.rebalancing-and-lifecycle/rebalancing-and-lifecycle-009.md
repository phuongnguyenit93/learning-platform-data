# Graceful shutdown

In a Spring Kafka production application, **graceful shutdown** is the **coordinated** process of stopping consumers, listener containers, and related resources, instead of terminating the process immediately. The goal is to stop accepting new work, safely process or finish in-progress records, commit offsets according to the proper acknowledgment/transaction mechanism, and close Kafka consumers and producers before the process exits.

Graceful shutdown is especially critical during Kubernetes rolling updates, new version deployments, scale-downs, instance restarts for configuration changes, or when the OS sends **SIGTERM**. If the process is simply killed with SIGKILL, in-flight records may be re-executed when partitions are assigned to another consumer. For operations like sending emails, creating invoices, or updating a database, that can cause duplicate side effects.

A proper shutdown does not equal a promise that **there will never be duplicates**. Standard Kafka consumers have at-least-once delivery semantics; an instance can still crash, run out of shutdown time, or lose partition ownership right before committing. Production design needs both layers: **stopping orderly when given the chance** and **idempotent processing when a safe stop is not possible**.

This lesson places graceful shutdown within the **Rebalancing and lifecycle** chapter of Spring Kafka, clarifying participating components, how Spring lifecycle stops containers, impacts on offsets and transactions, shutdown in Kubernetes, plus strategies for draining in-flight processing and operational monitoring.

## 1. How do abrupt shutdown and graceful shutdown differ?

Suppose a consumer in group `inventory-service` reads topic `orders.events`, partition 2, and processes the record at offset 100.

**Abrupt shutdown:**

~~~text
Consumer A polls offset 100
        |
        v
Calls Inventory API / updates database
        |
        v
SIGKILL / process crash
        |
        v
No opportunity to run lifecycle shutdown
        |
        v
Consumer B receives partition
        |
        v
Re-reads from prior committed offset
        |
        v
Record 100 may be processed again
~~~

**Graceful shutdown:**

~~~text
Consumer A receives SIGTERM
        |
        v
Spring begins lifecycle stop
        |
        v
Kafka listener container is requested to stop
        |
        v
Stops new poll loops and finishes processing units
permitted by stop policy
        |
        v
Commits offsets / completes or aborts Kafka transaction
according to actual outcome
        |
        v
Closes Kafka consumer and producer resources
        |
        v
Partitions are handed over to other group members
        |
        v
Process exits
~~~

Graceful shutdown helps reduce records that must be replayed, yet **cannot undo** business side effects already executed before an offset commit fails. That is the responsibility of idempotency and consistency design.

## 2. Which components are involved in shutdown?

A Spring Kafka application typically has multiple coexisting lifecycles:

| Component | Role during shutdown | What to watch out for |
|---|---|---|
| Spring ApplicationContext | Coordinates lifecycle and closes beans | Spring Boot must receive an orderly stop signal |
| KafkaListenerEndpointRegistry | Manages `@KafkaListener` containers | Can stop a container by ID or the whole registry |
| KafkaMessageListenerContainer | Polls records and invokes listener | Stops polling, handles active records, and commits per policy |
| ConcurrentMessageListenerContainer | Manages multiple child consumers | Must wait for consumer threads to finish properly |
| KafkaConsumer | Consumer group member owning partitions | Wakeup/close, handles rebalance and offsets |
| KafkaTemplate/ProducerFactory | Sends Kafka outputs or DLT | Pending sends and transactions must have clear outcomes |
| KafkaTransactionManager | Manages Kafka transactions | Commits/aborts per listener/container semantics |
| Database/HTTP clients | Side effects outside Kafka | Timeouts, idempotency, and resource closing order |
| Kubernetes/Process manager | Sends SIGTERM then potentially SIGKILL | Grace period must be long enough for shutdown path |

Looking only at `KafkaConsumer.close()` is insufficient. For example, the consumer may have stopped polling while an async task is still updating the database; exiting the process before the task completes can force the record to be reprocessed after restart.

## 3. Spring Kafka listener container is a SmartLifecycle

Spring Kafka listener containers participate in Spring **SmartLifecycle**. This allows Spring `ApplicationContext` to start and stop them according to lifecycle phases, rather than relying on a manual loop inside `@PreDestroy`.

In Spring Boot, when an application receives a termination signal such as SIGTERM, normal context shutdown asks `SmartLifecycle` beans to stop, waits for callbacks per each phase's timeout, and only then destroys beans and closes resources.

### 3.1. Lifecycle phase affects stopping order

Spring lifecycle follows a general principle:

- On startup, components with lower phases usually start first.
- On shutdown, components with higher phases are usually stopped first.
- Dependencies between beans can affect the actual order.

Spring Kafka listener containers typically use a very high phase so they start after many dependencies and are requested to stop early during shutdown. This is helpful: consumers should stop accepting work **before** database pools, producer factories, or service dependencies close.

Do not arbitrarily alter phases with large/small numbers without understanding the full dependency graph. Check the actual phase of containers and other `SmartLifecycle` resources in your active version.

### 3.2. Managed shutdown instead of immediate System.exit

Do not use a shutdown hook that calls `Runtime.halt()` or forces `System.exit` before the Spring context finishes stopping. If the application must expose an admin endpoint to stop a listener, use registry/container lifecycle APIs and let Spring handle resource cleanup.

## 4. Configuring Spring Boot shutdown wait times

Spring Boot supports configuring timeouts for lifecycle phases:

~~~yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 45s
~~~

This property gives Spring a maximum duration **for each shutdown phase** when waiting for `SmartLifecycle` beans to stop. It does not guarantee the entire application will stop in exactly 45 seconds, because there are other phases, bean destruction, and time outside Spring.

For Kafka containers, some versions also have dedicated shutdown timeout parameters on the container/container properties. Verify those parameters against the API/Javadoc of your exact Spring Kafka version.

Distinguish:

- **Spring lifecycle phase timeout:** how long the framework waits for stop callbacks of `SmartLifecycle` beans in a phase.
- **Kafka container stop/shutdown timeout:** how long the container can wait for threads/consumers to exit per config.
- **Kubernetes terminationGracePeriodSeconds:** total budget Kubernetes grants a container before forced termination.
- **HTTP/database timeouts:** time limits dependency calls can hold a listener.
- **Kafka max.poll.interval.ms:** consumer poll progress limit under group protocol.

All these timeouts participate in one shutdown plan; no single property covers everything on its own.

## 5. stopImmediate: stop after current record or whole poll?

A Kafka poll typically returns multiple records. Upon receiving a stop request, Spring Kafka can finish previously fetched records or stop sooner depending on configuration.

**By default in many Spring Kafka versions**, the container completes remaining records from the current poll before stopping. You can configure **stopImmediate** so the container stops after processing the current record, rather than continuing through all records received in the poll.

Example:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setStopImmediate(true);
    return factory;
}
~~~

Conceptual difference:

~~~text
poll() returns [R1, R2, R3, R4]
                |
                v
           Processes R1
                |
             SIGTERM
                |
       +--------+---------+
       |                  |
 stopImmediate=false  stopImmediate=true
       |                  |
       v                  v
 Processes R2,R3,R4   Stops after record
 in current poll      currently processing
       |                  |
       v                  v
 Container stops      Unprocessed records
                      can be re-read after
                      resume
~~~

Choose configuration by goal:

- If records are very fast, finishing the current poll can reduce replay volume.
- If records take long to process or poll batches are large, `stopImmediate` speeds up shutdown.
- Unprocessed records must remain eligible for re-consumption; never commit offsets past what actually processed successfully.

Setter names and exact handling details may vary by version; verify against your actual Spring Kafka release, especially with batch listeners or manual acknowledgment.

## 6. max.poll.records affects the shutdown budget

Suppose:

- `max.poll.records = 500`.
- Each record averages 300 ms to process sequentially.
- Consumer just polled a full 500 records.
- `stopImmediate = false`.

Processing those 500 records alone can take around:

~~~text
500 × 0.3 seconds = 150 seconds
~~~

If Kubernetes only grants 30 seconds to terminate, the container risks being SIGKILLed mid-way. Even if steady-state throughput looks fine, the shutdown path is misaligned.

An illustrative configuration:

~~~yaml
spring:
  kafka:
    consumer:
      max-poll-records: 100
      properties:
        max.poll.interval.ms: 300000
~~~

Lowering `max.poll.records` caps how many records sit in flight after one poll, yet does not reduce per-record latency on its own. In systems using batch listeners, batch size directly affects commit/rollback scope.

If records process slowly, address dependency timeouts, batching, concurrency, backpressure, and `stopImmediate` together.

## 7. AckMode determines which offsets are committed

Graceful shutdown is only safe when offsets reflect **work that truly completed**. Spring Kafka supports several `AckMode`s.

| AckMode | General mechanism | Points to note on shutdown |
|---|---|---|
| RECORD | Commits after each record processed successfully per container mechanism | Current failing record may be redelivered |
| BATCH | Commits after records in a poll are processed per policy | Interrupted poll may cause replaying multiple records |
| TIME / COUNT / COUNT_TIME | Commits based on time/count thresholds after processing | Processed records may remain uncommitted on abrupt stop |
| MANUAL | Listener calls acknowledge; container processes pending acks per mode semantics | Must ack properly after business logic completes |
| MANUAL_IMMEDIATE | Can commit immediately when acknowledged in the right context | Must not ack before side effects complete |

**Key takeaway:** offset commit is information the consumer group uses to resume reading next time, **not a side-effect deduplication mechanism**. If the database committed while the Kafka offset did not, the record can replay.

### 7.1. Manual acknowledgement example

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setAckMode(
        ContainerProperties.AckMode.MANUAL_IMMEDIATE
    );
    return factory;
}

@KafkaListener(
    id = "orders-listener",
    topics = "orders.events",
    containerFactory = "ordersFactory"
)
public void consume(
        ConsumerRecord<String, OrderEvent> record,
        Acknowledgment acknowledgment) {

    orderService.apply(record.value());   // Complete business logic first
    acknowledgment.acknowledge();         // Then acknowledge
}
~~~

If `apply()` throws an exception, acknowledgement is not called and the error handler performs retry/recovery. If `apply()` finishes yet ack/commit fails right at shutdown, the record can be re-read. Therefore the handler must be idempotent.

Do not ack at the start of the listener to "avoid replays" on shutdown; that risks losing business records if the process dies after acking.

## 8. Stopping listener containers via KafkaListenerEndpointRegistry

Spring Kafka allows accessing listener containers by ID for runtime management:

~~~java
@Component
public class KafkaConsumerControl {

    private final KafkaListenerEndpointRegistry registry;

    public KafkaConsumerControl(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void stopOrdersListener() {
        MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

        if (container != null) {
            container.stop();
        }
    }

    public void startOrdersListener() {
        MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

        if (container != null) {
            container.start();
        }
    }
}
~~~

Notes:

- The ID must match the `id` attribute on `@KafkaListener` or the corresponding registered listener container.
- `stop()` requests the container to stop per lifecycle; timing and completion waiting depend on API/implementation.
- `start()` should only be called while the application is still active and dependencies are ready.
- Do not call `stop()` from inside the listener and wait on the same thread in a way that causes deadlock.
- When Spring `ApplicationContext` shuts down, you normally **do not need** to call `registry.stop()` yourself from `@PreDestroy`; Spring lifecycle already coordinates stopping containers.

If you need to wait for a stop callback rather than assuming `stop()` completed immediately, use the version-supported `stop(Runnable)` API combined with an appropriate caller-side timeout.

### 8.1. Do not confuse pause with stop

Spring Kafka also supports pause/resume:

- **pause:** temporarily stops fetching/delivery per container semantics while the consumer can keep polling to retain membership.
- **stop:** ends the consumer container lifecycle, closes the consumer, and yields partitions per group protocol.

Pause is suitable for backpressure or waiting briefly on a dependency without leaving the group; stop is suitable when the instance is truly terminating. **Pause is not a complete shutdown**, as connections and consumer membership may remain active.

## 9. Graceful shutdown and rebalance

When a consumer leaves a consumer group, its partitions must be assigned to remaining active members. That is part of **rebalance** or assignment adjustment under the consumer group protocol.

In the common dynamic membership case:

1. Container receives stop request.
2. Consumer finishes in-flight operations per stop policy.
3. Consumer close leaves the group per client behavior.
4. Group coordinator updates membership.
5. Partitions are reassigned to remaining consumers.

Timing and number of revoked partitions depend on the assignor, group protocol, static membership, coordinator state, and other members.

### 9.1. Eager and cooperative rebalance

- **Eager rebalance:** may revoke many or all partitions of members before reassigning.
- **Cooperative rebalance:** supports incremental revocation, reducing disruption when topology permits.

Cooperative assignment reduces churn in many scenarios yet **does not replace shutdown safety**. An in-flight record can still replay if its offset is uncommitted or ownership is lost.

### 9.2. Static membership

Consumers using `group.instance.id` can be treated by the coordinator as static members under the Kafka protocol. In certain rolling restart scenarios, static membership helps reduce unnecessary rebalances, though stopping and disconnecting have different semantics from dynamic membership.

You cannot assume stopping a static member releases partitions immediately like a dynamic member across all clients/versions. When using static membership, consider `session.timeout.ms`, `max.poll.interval.ms`, and orchestration restart policies to avoid holding assignments longer than desired.

## 10. ConsumerRebalanceListener and partition state

Spring Kafka provides hooks for partition assign/revoke/lost events. With Spring Kafka, **ConsumerAwareRebalanceListener** lets you react at stages such as:

- `onPartitionsAssigned`.
- `onPartitionsRevokedBeforeCommit`.
- `onPartitionsRevokedAfterCommit`.
- `onPartitionsLost`.

During shutdown/rebalance, these hooks can help observe partition ownership or update per-assignment state.

Conceptual example:

~~~java
public class OrdersRebalanceListener
        implements ConsumerAwareRebalanceListener {

    @Override
    public void onPartitionsAssigned(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {
        log.info("Assigned partitions: {}", partitions);
    }

    @Override
    public void onPartitionsRevokedBeforeCommit(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {
        log.info("Revoking partitions: {}", partitions);
    }

    @Override
    public void onPartitionsLost(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {
        log.warn("Lost partitions: {}", partitions);
    }
}
~~~

This is an illustrative pattern: exact method signatures, callbacks, and listener registration must be checked against your Spring Kafka version. When a container receives **onPartitionsLost**, the consumer may already have lost authority over partitions; never attempt to commit offsets as if still owning them.

Do not put long database calls inside rebalance callbacks. Callbacks execute in the consumer context and can slow down rebalancing or polling. Only record necessary state/metrics and coordinate long work via another safe mechanism.

## 11. Handling synchronous vs asynchronous tasks differently

### 11.1. Synchronous listener

A synchronous listener returns only after business processing completes:

~~~java
@KafkaListener(topics = "orders.events")
public void onMessage(OrderEvent event) {
    orderService.process(event);
}
~~~

In this model, the container generally knows the listener finished when the method returns. Graceful shutdown can wait for the current record or poll batch per stop policy, then handle acks/offsets.

However, if `orderService.process()` calls an HTTP client without a timeout and hangs indefinitely, the container struggles to stop within the grace period. **Every blocking dependency must have a finite timeout**.

### 11.2. Listener launching asynchronous tasks

Example prone to unsafety:

~~~java
@KafkaListener(topics = "orders.events")
public void onMessage(OrderEvent event) {
    executor.submit(() -> orderService.process(event));
    // Method returns immediately even though business logic is still running.
}
~~~

If the container assumes the listener succeeded and commits the offset when the method returns, the process can stop before the task completes. The record has its progress recorded even though side effects are incomplete.

Asynchronous processing requires an explicit protocol:

- Do not acknowledge before the task finishes successfully.
- Manage in-flight task counts and executor shutdown draining.
- Preserve partition ordering if required by the domain.
- Classify async errors and route them back to error handling per APIs supported by your Spring Kafka version.
- Consider async listener return types supported by your running Spring Kafka version instead of fire-and-forget.
- Set a shutdown timeout on the worker pool and avoid acking after the container has lost partitions.

A thread pool may finish draining while Kafka offsets are still uncommitted; idempotency is still needed because crashes can occur between those two steps.

## 12. Designing an in-flight work tracker

For pipelines requiring processing outside the consumer thread, a tracker can manage running tasks.

Concept:

~~~text
Listener receives record
       |
       v
In-flight counter +1
       |
       v
Start asynchronous processing
       |
       +-- Success -> record status, ack via API
       |
       +-- Failure -> retry/recovery per policy
       |
       v
In-flight counter -1

Shutdown:
       |
       v
Stop accepting new tasks
       |
       v
Wait for counter to reach 0 within grace budget
       |
       v
Finalize offsets/producers/transactions, close container
~~~

Do not use a counter reaching 0 as the sole proof that work is durably committed. The counter can hit 0 before Kafka producer acknowledgements or offset commits complete.

Combine:

- In-flight count per component.
- Executor queue depth.
- Futures/completion signals.
- Pending Kafka producer sends.
- Pending acknowledgements and offset commits.
- An overall shutdown deadline.

If the drain deadline expires, the application needs clear behavior: stop accepting work, emit warning logs/metrics, and let uncommitted records replay; never force-ack just so the process exits on time.

## 13. Shutdown order of consumers and producers

A safe shutdown must avoid closing producers too early while listeners are still sending Kafka outputs or DLT messages.

Conceptually desired order:

~~~text
1. Stop accepting new work if other ingress exists.
2. Request Kafka listener containers to stop/pause intentionally.
3. Wait for permitted processing to complete.
4. Confirm producer sends or finish transactions
   required for completed processing.
5. Handle offset commit/rollback per listener semantics.
6. Close Kafka consumers, producers, and resources.
7. Terminate Spring ApplicationContext.
~~~

In Spring Boot, do not try to orchestrate everything via a chain of `@PreDestroy` methods across multiple beans assuming the order always holds. `SmartLifecycle` phases and bean dependencies determine stop order; use an appropriate lifecycle component when the application has executors/custom queues needing draining.

### 13.1. Producer flush is not committing a Kafka transaction

With non-transactional producers, `flush` waits for pending producer records to be sent per producer API. However:

- Flush does not turn a database update and Kafka publish into a single transaction.
- Flush does not replace checking whether send futures succeeded or failed.
- Flush does not mean consumer offsets have committed.
- With transactional producers, flush does not replace `commitTransaction()`.

If using a transactional `KafkaTemplate` inside a listener container, let the transaction manager/container complete commits or aborts per outcome. Do not call `commitTransaction` directly on a framework-managed producer.

## 14. Graceful shutdown with Kafka transactions

With a transactional listener, the container can bundle Kafka outputs and consumed offsets into one transaction. When shutdown happens mid-transaction:

**Transaction finishes and commits successfully:**

- Transactional outputs become visible to `read_committed` consumers.
- Input offsets are recorded in the same transaction.
- Records do not need replay due to that transaction.

**Transaction cannot commit or aborts:**

- Transactional outputs of an aborted transaction remain hidden from `read_committed` consumers.
- Consumed offsets in the transaction are not committed.
- Inputs can be reprocessed when the group reassigns partitions.

~~~text
Input record 300
       |
       v
Kafka transaction begins
       |
       v
Listener sends output
       |
       +-- Graceful stop has enough time
       |       |
       |       v
       |   Commit output + input offset
       |
       +-- Process forcibly stopped / TX aborts
               |
               v
           Output hidden if aborted
           Input offset not committed
           Record may replay
~~~

On the transactional path, Spring Kafka typically uses **DefaultAfterRollbackProcessor** to manage retry/recovery after rollback. Do not assume non-transactional `DefaultErrorHandler` governs all transaction rollbacks.

### 14.1. Transaction timeout still applies

`transaction.timeout.ms` limits how long a producer transaction can stay open. A graceful shutdown deadline does not automatically extend the Kafka transaction timeout.

If a listener needs 90 seconds to finish while `transaction.timeout.ms` only allows 60 seconds, the broker may abort the transaction before the Kubernetes grace period expires. Therefore, keep transaction scopes short and evaluate `transaction.timeout.ms`, `max.poll.interval.ms`, and shutdown deadlines **independently**.

### 14.2. Producer fencing during rolling restarts

If a new instance reuses a `transactional.id` while the old instance has not stopped yet, the old producer may be **fenced**. Fencing protects Kafka transactions from zombie producers, yet does not roll back external HTTP/database side effects outside Kafka.

During rolling updates:

- Control transactional ID prefixes/instance identities.
- Do not let two independent instances accidentally use the same `transactional.id`.
- Accept cases where an old instance is fenced or a transaction aborts and records replay.
- Use idempotency at the business boundary.

Do not infinitely retry a fenced producer.

## 15. Why is idempotency still mandatory?

Suppose a listener:

1. Writes to the database successfully.
2. Prepares to commit the Kafka offset.
3. Instance receives SIGKILL because the grace period expired.
4. A new consumer re-reads the record.

The database already has the change, yet the Kafka group may not have recorded the offset. If the handler is not idempotent, the change is applied twice.

A common pattern is **processed_events/inbox**:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(128) NOT NULL,
    consumer_name VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (event_id, consumer_name)
);
~~~

Within the **same database transaction**:

- Insert event ID under the unique constraint.
- If it already exists, skip the duplicate side effect.
- If the insert succeeds, apply business updates.
- Commit database.
- Then let the Kafka container commit offsets per `AckMode`.

If the Kafka commit fails, the record replays and the inbox avoids duplicate side effects. If the database transaction fails, both the processed marker and side effect roll back.

Do not believe graceful shutdown alone guarantees exactly-once business behavior. Power failures, node crashes, OOMKills, or network partitions can strike at any moment.

## 16. Error handler, retry, and DLT when a container stops

A record may be inside a `DefaultErrorHandler` retry sequence when shutdown occurs.

Example:

~~~text
Record X processing fails
      |
      v
Retry 1 after 1 second
      |
      v
Retry 2 after 2 seconds
      |
      v
SIGTERM
      |
      v
Container requested to stop
      |
      v
Retry/backoff has not finished yet
~~~

Depending on Spring Kafka version, `BackOffHandler`, and container state, the container may process the stop during the wait or interrupt the retry chain so the consumer leaves the group. If the record has not recovered and offsets are uncommitted, the record can be re-read on startup.

For stable shutdowns:

- Blocking retries need finite attempt counts and durations.
- HTTP/database requests need separate timeouts.
- Do not configure infinite retries on the consumer thread without a stop strategy.
- Permanent failures should route to DLT/recovery per policy.
- If DLT publish has not been confirmed, do not try to commit offsets just because the shutdown deadline is near.
- Monitor recovery publish failures and in-flight retry durations.

### 16.1. Non-blocking retry topics

If the system uses `@RetryableTopic`, failed records may already be published to a retry topic and source offsets committed per policy. At that point another consumer of the retry topic can continue processing after the original instance stops.

Graceful shutdown must account for **all retry-topic containers**, not just the main topic container. Dashboards should track pending records in retry topics and DLTs.

A successful publish to a retry topic before source offset commit can also create duplicates on redelivery. Idempotency and stable event IDs help the system survive this failure window.

## 17. Kubernetes: SIGTERM and terminationGracePeriodSeconds

Kubernetes normally asks a container to terminate with a terminate signal, then can forcibly kill it if **terminationGracePeriodSeconds** is exceeded.

An illustrative configuration:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inventory-consumer
spec:
  replicas: 3
  selector:
    matchLabels:
      app: inventory-consumer
  template:
    metadata:
      labels:
        app: inventory-consumer
    spec:
      terminationGracePeriodSeconds: 90
      containers:
        - name: app
          image: example/inventory-consumer:1.0.0
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            periodSeconds: 5
~~~

90 seconds is an example, not a fixed recommendation for every workload. Measure actual stop times of listeners, executors, producers, and Spring context, then add a safety buffer.

### 17.1. Grace time is not solely for listeners

The Kubernetes budget covers lifecycle operations such as `preStop` hooks, waiting for the process to react to SIGTERM, Spring context shutdown, and resource cleanup. If a `preStop` hook consumes most of the time, Spring Kafka may have very little time left to finish running records.

Therefore:

~~~text
T_k8s_grace
  > T_preStop
    + T_listener_drain
    + T_commit_or_abort
    + T_resource_close
    + T_safety_margin
~~~

This is a budgeting formula, not a hard execution time guarantee. Phases can overlap or be affected by scheduling, GC, broker timeouts, and thread pools.

### 17.2. preStop does not automatically stop Kafka consumers

A hook like:

~~~yaml
lifecycle:
  preStop:
    exec:
      command:
        - /bin/sh
        - -c
        - sleep 5
~~~

only delays termination; it **does not** automatically make `@KafkaListener` stop polling immediately. It can be useful for HTTP traffic draining in some architectures, but is not a Kafka consumer shutdown solution.

To stop Kafka in a controlled way, let the process receive SIGTERM and let Spring lifecycle stop containers, or design a dedicated drain endpoint/protocol when genuinely needed.

### 17.3. Readiness probes do not control Kafka groups

When a Pod is not ready, Kubernetes Services normally stop routing new **HTTP traffic** to that Pod. However, Kafka brokers and consumer groups do not use Kubernetes readiness to decide which consumers are assigned partitions.

Therefore, setting `readiness=false` **does not automatically pause/stop Kafka consumers**. If a service has both a REST API and `@KafkaListener`s, both ingress paths must be coordinated separately.

## 18. JVM shutdown must receive SIGTERM

A Java application running in a container must ensure SIGTERM reaches the JVM process. If a shell entrypoint swallows signals or the Java process does not run under proper signal forwarding, Spring `ApplicationContext` may not receive the signal to close.

Illustrative Dockerfile/entrypoint:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY app.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Exec-form ENTRYPOINT typically delivers signals directly to the Java process. If a shell script is required, consider `exec java ...` to replace the shell with the JVM.

Do not expect `@PreDestroy` to run when a process hits SIGKILL, OOMKill, or host power loss. Shutdown callbacks are best-effort when the runtime still has a chance to finish.

## 19. Rolling deployments and concurrency

When a Pod stops, remaining Pods take over its partitions. If scaling down from 6 instances to 3, remaining consumers absorb more partitions and backlog.

Points to monitor:

- Partition counts, active consumer counts, and listener container concurrency.
- Rebalance frequency and duration.
- Consumer lag per partition, not just group totals.
- Listener stop duration and new assignment latency.
- Oldest record age, throughput, and latency after scale-down.
- Dependency throughput: more partitions concentrating onto fewer consumers can increase per-instance load.

Increasing concurrency does not always shorten shutdown time; if every container thread holds heavy in-flight work, many tasks must drain in parallel and downstream resources may overload.

For rolling updates, avoid stopping too many instances simultaneously. Use deployment strategies, `PodDisruptionBudget` where appropriate, and size capacity for remaining replicas.

## 20. Distinguishing shutdown from pause/resume for backpressure

Some operations teams want to halt consumers during downstream outages to avoid retry storms.

**Pausing the container** fits when:

- The application stays running and wants to keep group membership properly.
- The dependency is expected to recover shortly.
- You want to resume without recreating the entire container.
- Monitoring/alerting exists if paused too long.

**Stopping the container** fits when:

- The instance is about to terminate.
- Kafka consumer resources must be freed.
- Partitions need to transfer to other instances.
- A deployment or maintenance requires a real stop.

**Shutting down ApplicationContext** fits when:

- The entire service is terminating.
- Listeners, producers, executors, and databases must close together.

Do not use pause as a way to make a Pod exit: pause can keep consumer connections open, and the process stays running.

## 21. When stop does not finish in time: what happens?

Graceful shutdown has a **deadline**. When the deadline expires, the orchestrator can forcibly terminate the process.

Possible states:

| State when stopped | Potential consequence |
|---|---|
| Record not yet processed | New consumer reads from uncommitted offset |
| Record processed yet offset uncommitted | Record may replay, requiring idempotency |
| Kafka producer send unconfirmed | Output may or may not have been written; outcome uncertain |
| Uncommitted Kafka transaction | Coordinator may abort; `read_committed` downstream sees no aborted output |
| Database committed, Kafka offset uncommitted | Side effects may duplicate on replay |
| DLT publish unconfirmed | Cannot treat recovery as safe; record may need redelivery |
| Asynchronous task still running | Task may be interrupted; no completion guarantee |

No `stopImmediate` or `shutdownTimeout` flag eliminates all these failure boundaries. Prioritize **not committing incomplete work**, recording clear outcomes, and letting subsequent runs process idempotently.

## 22. Calculating shutdown budget from SLOs

An illustrative calculation:

- Listener processing p99: 3 seconds/record.
- `max.poll.records`: 40.
- `stopImmediate`: false.
- Producer commit/flush: max 8 seconds.
- Consumer close and Spring cleanup: 7 seconds.
- Buffer for GC/network/scheduling: 15 seconds.

If processing a poll sequentially, worst-case time under assumptions could be:

~~~text
T_listener = 40 × 3s = 120s
T_commit   = 8s
T_close    = 7s
T_margin   = 15s

T_grace_budget ≈ 150s
~~~

If Kubernetes `terminationGracePeriodSeconds` is 30 seconds, this large poll cannot be expected to drain completely under the current stop policy.

Adjustments include:

1. Enable `stopImmediate` if semantics and Spring Kafka version allow.
2. Lower `max.poll.records` or reduce processing time per record.
3. Set dependency timeouts.
4. Split long work out of the listener into a durable workflow.
5. Raise grace period when genuinely needed and backed by latency measurements.
6. Use idempotency to tolerate replay of remaining records.

Do not set an excessively large grace period just to avoid replays: a hung instance can hold resources and make rollouts painfully slow.

## 23. Graceful shutdown and batch listeners

With a batch listener, the method receives a list of `ConsumerRecord`s instead of a single record.

~~~java
@KafkaListener(
    topics = "orders.events",
    containerFactory = "batchFactory"
)
public void consumeBatch(List<OrderEvent> events) {
    batchService.apply(events);
}
~~~

If a batch has 500 records and `batchService.apply` takes 60 seconds, shutdown must wait per container behavior. If the process dies mid-batch, offset commits may not have happened and many records are redelivered.

Principles:

- Keep batch sizes and processing times under operational budgets.
- Define commit/ack semantics when a single record in the batch fails.
- Use idempotency per event or per appropriate batch ID.
- Do not treat partial DB commits of a batch as an atomic Kafka offset commit.
- If batches are huge, consider appropriate chunking and checkpoints or switching to a record listener.

`stopImmediate` with batch listeners cannot necessarily halt mid-method while processing a batch; the Java method must still finish or support valid cancellation itself.

## 24. External operations that should not be interrupted arbitrarily

During shutdown, threads may be interrupted or dependencies closed. Yet arbitrarily cancelling a critical task right after sending a request can leave the outcome **ambiguous**.

Payment API example:

~~~text
Consumer sends charge request
       |
       v
Payment API executes successfully
       |
       v
Listener has not received response yet
       |
       v
SIGTERM -> task cancelled
       |
       v
New consumer retries charge
~~~

Do not solve this by "waiting forever for Payment API to respond". Instead:

- Attach an idempotency key to charges.
- Have a lookup API for payment status when responses time out.
- Persist business state and recovery intent durably.
- Use outbox/saga if workflows span beyond Kafka.
- Bound shutdown time while accepting safe replays.

Graceful shutdown makes sense when business logic is designed to stop/resume along clear commit boundaries.

## 25. Custom shutdown hooks: when to use?

In many pure Spring Kafka applications, built-in lifecycles are enough. A custom shutdown hook is only useful when coordinating resources outside Kafka, such as:

- Stopping HTTP ingress before consumers stop.
- Halting schedulers emitting new work.
- Waiting for executor queues to drain.
- Writing dedicated checkpoints for a long-running worker.
- Closing external API connections after consumers finish.

If writing your own hook, avoid:

- Calling `System.exit` inside `@PreDestroy`.
- Calling `listenerContainer.stop()` from inside the listener itself and blocking indefinitely.
- Closing `KafkaTemplate`/`ProducerFactory` while listeners still send outputs.
- Merely sleeping a fixed duration and hoping draining finished.
- Swallowing exceptions and reporting shutdown success while work remains pending.
- Spawning a hung non-daemon thread that prevents the JVM from exiting.

A custom `SmartLifecycle` component can coordinate draining when needed, provided dependencies/phases are clearly defined. With Spring Boot and `KafkaListenerEndpointRegistry`, prefer lifecycle APIs already supported by the framework.

## 26. Testing graceful shutdown

You cannot claim shutdown safety merely with unit tests on a listener method. Integration tests with a real Kafka broker/test infrastructure and realistic stop conditions are needed.

### 26.1. Stop with no in-flight records

Start the consumer, confirm group assignment, then send a stop signal. Verify the container transitions to stopped, no consumer connections remain, and restarting causes no unexpected duplicate processing.

### 26.2. Stop mid-synchronous record

Have the listener process a record for a known duration. Send SIGTERM after the listener starts. Verify:

- The active stop policy applies properly.
- If the listener finishes within the grace period, offsets can commit per `AckMode`.
- If stopped before commit, the record can replay after restart.
- Business side effects do not duplicate thanks to idempotency.

### 26.3. Stop mid-poll with multiple records

Set `max.poll.records` small yet greater than 1. Send multiple records and shut down mid-way. Compare `stopImmediate=false/true` for your version:

- How many records processed before stop?
- What was the last committed offset?
- How many records redelivered after restart?
- Were any unprocessed records skipped?

### 26.4. Stop while producer send/DLT send is incomplete

Introduce controlled producer delays or Kafka failures. Verify logic does not treat unconfirmed future sends as successful and does not commit offsets of records not safely recovered.

### 26.5. Stop with an open Kafka transaction

Send transactional outputs and shut down before commit. Verify `read_committed` downstream does not see aborted transaction outputs and input records can redeliver.

### 26.6. Forced termination

Run the same scenario using forced kill in a test environment. This truly validates idempotency: the graceful path does not run, yet the pipeline must still recover validly.

### 26.7. Multi-replica rolling update

Test-deploy with production-like replica counts and concurrency. Observe rebalance duration, lag spikes, shutdown times, replayed record counts, and downstream catch-up capability.

Never run destructive kill/scale-down experiments on production clusters or mutate critical topics for testing; use dedicated environments and authorized permissions.

## 27. Observability and alerting during shutdown

Signals to collect:

| Signal | Meaning |
|---|---|
| Shutdown initiated/completed timestamps | Time from signal receipt to closing completion |
| Listener container running/stopping state | Whether containers remain active past deadline |
| In-flight listener count | How many records/tasks are currently processing |
| Last processed offset and committed offset | Whether a gap exists between processing and commits |
| Producer pending send count/failures | Whether unconfirmed outputs exist at shutdown |
| Transaction commits/aborts | Whether transactions completed or rolled back properly |
| Consumer group rebalance count/duration | How long partition handoffs took |
| Partition lag and oldest record age | Whether the group recovers progress after rollout |
| Duplicate/idempotency hits | How many replayed records were safely absorbed |
| DLT recovery failures | Whether failed records were saved before shutdown |
| Kubernetes termination reason | Normal SIGTERM, OOMKilled, or forced kill |
| Grace-period exceeded count | Whether instances routinely fail to stop in time |

A shutdown log should record:

- Application instance/pod ID.
- Consumer group, listener ID, and owned partition count.
- Stop start and completion timestamps.
- Initial and remaining in-flight record/task counts.
- Last processed offset and most recent committed offset if available.
- Outcomes of pending producers/transactions/recoverers.
- Wait duration and timeout reason.

Do not log full payloads/credentials. Event IDs/correlation IDs suffice to trace partially processed records.

## 28. Runbook: Pod SIGKILLed because stop missed deadline

### Step 1: Identify termination type

Inspect Pod status, termination reason, exit code, and application shutdown logs. Distinguish SIGTERM handled-but-timed-out, JVM not receiving signal, OOMKill, or node disruption.

### Step 2: Find the slowing component

- Does the listener have HTTP/database calls without timeouts?
- How are `max.poll.records` and `stopImmediate` configured?
- Is a batch listener taking too long?
- Does an async executor still hold tasks/queues?
- Are producer/DLT sends or Kafka transactions waiting on brokers?
- What is the Spring lifecycle phase timeout?

### Step 3: Inspect data

- What is the group's committed offset after restart?
- Were records redelivered?
- Did database/HTTP side effects duplicate?
- Is there new DLT or retry topic backlog?
- Were transaction outputs aborted or read by `read_uncommitted` downstream?

### Step 4: Fix root cause

Set dependency timeouts, reduce poll/batch sizes, enable `stopImmediate` when appropriate, drain executors using completion signals, fix producer timeouts/backoffs, or adjust grace periods based on real measurements.

### Step 5: Verify next rollout

Re-test termination in a representative environment. Confirm stop duration stays under grace period, lag recovers, group rebalances stabilize, and no uncontrolled duplicate side effects occur.

## 29. Runbook: consumer lag rises after rolling deployment

A slight lag bump during rebalance can be normal, yet prolonged growth needs investigation.

1. Check if enough active consumers exist after rollout.
2. Verify partitions assigned per instance and concurrency.
3. Inspect rebalance count/duration, assignor, and group membership.
4. Confirm new consumers are actually running and listener/container factories started properly.
5. Inspect oldest record age and throughput after rollout.
6. Check database/HTTP capacity as partitions may concentrate onto fewer instances.
7. If static membership, check whether old members still hold assignments until session timeout.
8. Check whether replays/duplicates are adding load or lock contention.
9. Adjust rolling update strategy, grace periods, and readiness/health policies accordingly.

A dashboard showing only aggregate consumer group lag can hide a single stuck partition caused by a poison record or a static member that has not yet released its partition.

## 30. Common design mistakes

| Practice | Consequence | Adjustment |
|---|---|---|
| Setting only terminationGracePeriodSeconds without controlling listeners | Listeners may still poll/process for a long time | Use Spring lifecycle and proper stop policy |
| Relying on readiness=false to stop Kafka consumption | Kafka group does not read Kubernetes readiness | Stop/pause listeners via Kafka lifecycle |
| preStop merely sleeps very long | Consumes grace budget before JVM gets SIGTERM | Keep preStop minimal and measure end-to-end shutdown |
| Shell entrypoint not forwarding SIGTERM | JVM never runs shutdown hooks | Use exec ENTRYPOINT or forward signals |
| Using stopImmediate without understanding offsets | Unprocessed records in poll may replay | Ensure AckMode/commit matches processed portion |
| Large max.poll.records, slow listener, short grace | Forced kill before draining poll | Reduce poll/batch, set timeouts, raise grace reasonably |
| Acking before DB/HTTP write succeeds | Silent business data loss on shutdown | Ack only after durable processing |
| Fire-and-forget async tasks from @KafkaListener | Container commits before task completes | Async contract + in-flight drain + proper ack |
| Closing producer before listeners stop | Pending outputs/DLT may fail | Coordinate SmartLifecycle and dependencies |
| Calling flush and assuming transaction committed | Broken EOS semantics | Commit/abort transactions via manager |
| Raising max.poll.interval.ms to fix hung shutdown | Masks dependencies lacking timeouts | Fix root cause and design retries/budgets |
| Trying to commit offsets after onPartitionsLost | Consumer may have lost partition authority | Do not commit as old owner; accept redelivery |
| Assuming graceful shutdown eliminates duplicates | Forced kills and commit failures still happen | Consumer/business idempotency |
| Monitoring lag only right before stop | Misses backlogs in retry topics and DLT | Monitor entire pipeline |
| Testing shutdown only with zero load | Misses in-flight races | Test under load, rebalance, and forced kill |

## 31. Production checklist

Before operating listeners on Kubernetes or orchestration platforms:

1. Does Spring Boot receive SIGTERM and close `ApplicationContext`?
2. Do Kafka listener containers participate in `SmartLifecycle` with a sensible shutdown phase?
3. Has `stopImmediate` been evaluated against poll/batch size and latency?
4. Does `max.poll.records` fit final processing time on stop?
5. Do HTTP/database calls inside listeners have finite timeouts?
6. Do `AckMode` and manual acknowledgements ensure no commits occur before successful processing?
7. Are there custom async executors needing draining before producers/databases close?
8. Do in-flight tasks have completion signals and a shutdown deadline?
9. Do producer sends, DLT sends, and Kafka transactions have properly verified outcomes?
10. Is the orchestrator's grace period larger than measured lifecycle stop duration plus buffer?
11. Does the `preStop` hook consume too much of the grace budget?
12. Is readiness policy separated from Kafka consumer group membership?
13. Are Kafka transaction timeout, `max.poll.interval.ms`, and shutdown timeout evaluated independently?
14. Does the rolling update strategy maintain enough active consumers and downstream capacity?
15. If using static membership, is the impact of session timeout on reassignment understood?
16. Do external side effects outside Kafka have idempotency keys or inbox/outbox?
17. Are there metrics for stop duration, in-flight tasks, commits, rebalances, lag, and duplicates?
18. Are there tests stopping mid-record, mid-poll, mid-Kafka-transaction, and mid-DLT-send?
19. Are there forced-kill tests proving the system recovers when the graceful path never runs?
20. Does the operations team have runbooks for Pods missing stop deadlines and post-rollout lag spikes?

**Conclusion:** Graceful shutdown in Spring Kafka is a lifecycle and rebalance procedure, not just calling `close()` or sleeping a few seconds before a Pod exits. Applications must stop intake at the container, handle in-flight work per stop policy, commit only offsets with safe outcomes, finish or abort Kafka transactions at the proper boundary, and close resources within the shutdown budget. Spring `SmartLifecycle`, `stopImmediate`, `AckMode`, and Kubernetes `terminationGracePeriodSeconds` help coordinate this, yet **idempotency and replayability** remain the foundation protecting data when shutdown does not finish as planned.
