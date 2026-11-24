# Pausing When the Database Is Overloaded in Spring Kafka

When a Kafka consumer reads records faster than a database can write them, the system can saturate its connection pool, CPU, I/O, or locks. If the listener keeps reading and executing queries, queued database requests pile up; timeouts trigger retries; retries push even more load onto the database. The result can be a feedback loop making the database progressively slower.

In the **Spring Kafka Reliability Operations** module, the **Pausing When the Database Is Overloaded** lesson focuses on using the Spring Kafka listener container's **pause/resume** mechanism to implement **backpressure**. Instead of continuing to feed new records into the listener when the database lacks capacity, the application instructs the container to temporarily stop delivering data, gives the database time to recover, and then resumes processing.

**Pause does not delete records, does not commit offsets on its own, does not roll back database transactions, and does not automatically fix business errors.** It is an intake throttle valve. Implementing it safely requires combining health signals, hysteresis, timeouts, timely acknowledgments, idempotency, error handlers, and monitoring.

## 1. Nature of backpressure from Kafka to the database

Kafka stores records durably by topic and partition. Consumers can process data at their own pace. When downstream slows down, consumer lag grows; rising lag by itself is not necessarily data loss, provided Kafka retains records within the retention window.

~~~text
Producers
    |
    v
Kafka topic orders.events
    |
    v
Spring Kafka consumers
    |
    +--> Consumer 1
    +--> Consumer 2
    +--> Consumer 3
    |
    v
Business listener
    |
    v
HikariCP connection pool
    |
    v
PostgreSQL
    |
    +--> High CPU
    +--> Increased lock waits
    +--> Slow queries
    +--> Threads waiting for connections
~~~

A system without backpressure can create its own downward spiral:

1. Kafka has many records ready.
2. The listener keeps executing database queries.
3. The connection pool runs out of idle connections.
4. Threads wait for connections, then time out.
5. `DefaultErrorHandler` or a retry mechanism retries them.
6. Multiple retries hit the already-slow database simultaneously.
7. Throughput drops further and consumer lag climbs.

The goal of backpressure is **reducing the number of newly started jobs** so the target system does not collapse. Do not simply raise concurrency or `max.poll.records` to try catching up with Kafka when the true bottleneck is the database.

## 2. What is container pause?

Spring Kafka exposes operations on `MessageListenerContainer`:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");

container.pause();

// After the database recovers:
container.resume();
~~~

A paused container:

- Temporarily halts delivering additional new records to the listener.
- Normally continues calling `KafkaConsumer.poll()` while paused to maintain consumer group membership.
- Does not actively skip records or advance offsets merely because it is paused.
- Can resume to process data still stored in the topic.
- Does not automatically cancel running listener or JDBC calls.

~~~text
RUNNING
   |
   | DB saturation detected
   v
PAUSE_REQUESTED
   |
   | Consumer applies pause at poll boundary
   v
PAUSED
   |
   | Consumer can still poll to keep group
   | Listener receives no additional new records
   |
   | DB healthy long enough
   v
RESUME_REQUESTED
   |
   v
RUNNING
~~~

**Pause differs from stop.** Stopping the container closes the consumer per lifecycle, potentially triggering partition reassignment. Pause typically keeps the consumer in the group and retains partition assignments, making it suited for temporary overload incidents.

Understand the limitation: calling `pause()` is not completely synchronous with when the consumer actually pauses. The consumer may still be processing a record or batch polled prior to receiving the request.

## 3. Pause requested is not pause completed

Spring Kafka distinguishes requested state from actual state:

| API | Purpose |
|---|---|
| `pause()` | Requests the container to pause |
| `resume()` | Requests the container to resume |
| `isPauseRequested()` | Determines whether a pause request is active |
| `isConsumerPaused()` | Checks whether the consumer/container is in the paused state |
| `pausePartition(TopicPartition)` | Requests pausing a single partition when supported by the API |
| `resumePartition(TopicPartition)` | Requests resuming that partition |

With `ConcurrentMessageListenerContainer`, child consumers can apply the pause when they reach an appropriate point in the poll loop. When multiple child containers exist, distinguish a pause request at the parent container level from the actual state of each individual consumer.

Spring Kafka provides lifecycle events related to pause/resume. In applications needing observability, you can listen for `ConsumerPausedEvent`, `ConsumerResumedEvent`, and partition-level events when supported by the version to separate **pause requested** from **pause actually applied**.

## 4. Already-received records may still keep running

A common point of confusion is that the container may have polled many records before the application calls `pause()`.

~~~text
poll() returns 100 records
      |
      +--> process record 1
      +--> process record 2
      |
      +--> monitoring detects DB overload
      |       |
      |       +--> calls container.pause()
      |
      +--> some already-polled records may continue
      |
      v
consumer returns to poll loop and applies pause
~~~

Normally, pause takes effect at the poll boundary. Some Spring Kafka versions support `pauseImmediate` via `ContainerProperties` to pause right after the currently processing record rather than waiting to finish all already-polled records:

~~~java
factory.getContainerProperties().setPauseImmediate(true);
~~~

This does not interrupt an active database transaction mid-flight, nor is it a way to split a batch listener callback into pieces. Verify support in your Spring Kafka version and actual listener type.

If the database is hung and the listener waits indefinitely for a connection, the container never returns to the poll loop; a `pause()` call from a scheduler cannot fix that problem. **Timeouts at the database layer are mandatory**, not an optional feature replaceable by pause.

## 5. Which signals identify database overload?

Never rely on a single isolated metric. A database with many active connections can still be healthy if queries are fast; conversely, a pool with few active connections does not guarantee health if the database has lost connectivity completely.

| Signal | What to watch | Notes |
|---|---|---|
| Hikari active connections | Connection pool utilization rising | Compare against max pool size |
| Hikari threads awaiting | Threads queued waiting for connections | Usually a clear saturation signal |
| Connection acquisition p95/p99 | Acquiring connections slower than normal | Avoid reacting to a brief spike |
| Query latency p95/p99 | Queries slowing down | Differentiate by query type |
| JDBC timeout/error rate | Database failing to respond to requests | May stem from network or backend |
| Lock waits/deadlocks | Transactions contending on locks | Requires fixing query/transaction root cause |
| Database CPU/IO | Resource usage nearing limits | DB-wide metric, not just one pod |
| Circuit breaker state | Dependency evaluated as unavailable | Health may be OPEN when active=0 |
| Consumer lag growth | Consumer falling behind producers | Lag alone is insufficient to prove DB overload |

In HikariCP, `HikariPoolMXBean` provides methods such as `getActiveConnections()`, `getTotalConnections()`, `getIdleConnections()`, and `getThreadsAwaitingConnection()`. `HikariDataSource` exposes `maximumPoolSize` configuration alongside the MXBean accessor.

When designing a policy, combine **local signals** such as waiting connections with **database-wide signals** such as query p99, saturation, or circuit breakers. If multiple services share the database, inspecting only one pod's Hikari pool can miss pressure caused by another service.

## 6. Designing pause/resume with hysteresis

If the controller pauses immediately at 80% utilization and resumes as soon as it drops to 79%, the system easily flaps:

~~~text
80% -> PAUSE
79% -> RESUME
81% -> PAUSE
78% -> RESUME
...
~~~

Use two distinct thresholds:

~~~text
100% |
     |
 90% | ---- PAUSE THRESHOLD
     |
     | Keep current state in the middle band
     |
 55% | ---- RESUME THRESHOLD
     |
  0% |
~~~

Illustrative policy:

- Pause when connection pool reaches roughly 90% capacity or has waiting threads/high error rates, and overload persists across multiple samples.
- Resume when connection utilization drops below 55%, zero threads are waiting, the database is healthy, and recovery persists across multiple samples.
- Enforce a minimum pause duration and cooldown to prevent rapid state flipping.
- An OPEN circuit breaker must keep the container paused even when active connections are low.
- When the circuit breaker is HALF_OPEN, do not let all Kafka listeners unleash full load simultaneously; use bounded probes.

**90% and 55% are illustrative application policy values, not Spring Kafka defaults.** Tune thresholds based on database workload, connection acquisition latency, and service SLOs.

## 7. Spring Boot configuration: database pool and consumer

A reference configuration:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/orders
    username: orders_app
    hikari:
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 3000
      validation-timeout: 1000

  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092,kafka-3:9092
    consumer:
      group-id: order-service
      enable-auto-commit: false
      max-poll-records: 100
      properties:
        "[max.poll.interval.ms]": 300000
    listener:
      ack-mode: record
      concurrency: 3
~~~

Meaning:

- `maximum-pool-size` limits pool connections per application instance.
- `connection-timeout` prevents threads from waiting indefinitely for a connection.
- `max-poll-records` shrinks the amount of work per poll.
- `max.poll.interval.ms` caps allowed time between consumer polls.
- `AckMode.RECORD` commits after each successfully processed record in the listener.
- `concurrency` creates parallel child consumers, though it can also multiply concurrent database calls.

Calculate expected total connections across **all replicas and all services**, not a single pool. If 10 pods each have `maximum-pool-size=20`, the application can consume up to 200 connections, excluding other services.

DB query timeouts and transaction timeouts may need separate JDBC/framework/database configuration, because Hikari's `connection-timeout` only bounds waiting to **acquire a connection**, not the execution duration of every SQL query.

## 8. Controlling the container via KafkaListenerEndpointRegistry

Declare the listener with a stable `id`:

~~~java
@Component
public class OrderListener {

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            id = "ordersListener",
            topics = "orders.events",
            groupId = "orders-service"
    )
    public void onOrder(OrderEvent event) {
        orderService.processIdempotently(event);
    }
}
~~~

A control service:

~~~java
@Service
public class OrderListenerControl {

    private final KafkaListenerEndpointRegistry registry;

    public OrderListenerControl(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void requestPause() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersListener");

        if (container != null
                && container.isRunning()
                && !container.isPauseRequested()) {
            container.pause();
        }
    }

    public void requestResume() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersListener");

        if (container != null
                && container.isRunning()
                && container.isPauseRequested()) {
            container.resume();
        }
    }
}
~~~

Use the Spring Kafka container API instead of calling `Consumer.pause()` directly from a scheduler thread. `KafkaConsumer` cannot be accessed concurrently from arbitrary threads; the container handles interacting with the consumer on the proper thread.

If a container is created manually rather than via `@KafkaListener` registry, the application must retain a direct reference to that container instead of expecting the registry to find it.

## 9. Controller that auto-pauses when the pool saturates

You can use `@Scheduled` to periodically read HikariCP signals and make decisions. The following example shows a basic mechanism without dwell time or distributed coordination.

~~~java
@Component
public class DatabaseBackpressureController {

    private final HikariDataSource dataSource;
    private final KafkaListenerEndpointRegistry registry;
    private final DatabaseHealthSignals healthSignals;

    public DatabaseBackpressureController(
            HikariDataSource dataSource,
            KafkaListenerEndpointRegistry registry,
            DatabaseHealthSignals healthSignals) {

        this.dataSource = dataSource;
        this.registry = registry;
        this.healthSignals = healthSignals;
    }

    @Scheduled(fixedDelay = 2000)
    public void evaluate() {

        MessageListenerContainer container =
                registry.getListenerContainer("ordersListener");

        if (container == null || !container.isRunning()) {
            return;
        }

        HikariPoolMXBean pool = dataSource.getHikariPoolMXBean();

        if (pool == null) {
            return;
        }

        int active = pool.getActiveConnections();
        int waiting = pool.getThreadsAwaitingConnection();
        int max = dataSource.getMaximumPoolSize();

        if (max <= 0) {
            return;
        }

        double ratio = (double) active / max;

        boolean overloaded =
                waiting > 0
                || ratio >= 0.90
                || healthSignals.circuitOpen();

        boolean recovered =
                waiting == 0
                && ratio <= 0.55
                && healthSignals.databaseHealthy();

        if (overloaded && !container.isPauseRequested()) {
            container.pause();
        }
        else if (recovered && container.isPauseRequested()) {
            container.resume();
        }
    }
}
~~~

`DatabaseHealthSignals` is an application abstraction providing circuit breaker and database health state. `@Scheduled` requires enabling scheduling, e.g., `@EnableScheduling`. `HikariDataSource` can be injected only when the actual datasource uses HikariCP; with multiple datasources, select the exact target pool.

This is an illustrative controller, not a complete production controller. You must add:

- Consecutive sample counts to confirm state.
- Minimum pause duration.
- Resume cooldown.
- Logs of pause/resume reasons.
- Manual maintenance override.
- Per-container tracking state.
- Health signals derived from existing telemetry instead of running heavy SQL queries every run.

Do not query the database with a connection-consuming health SQL query every two seconds while the database itself is starved for connections. Prefer telemetry, circuit breakers, and lightweight deadline-bounded probes only when needed.

## 10. Prevent conflicting pause controllers

A listener can be paused for several reasons:

~~~text
DATABASE_OVERLOAD
MANUAL_MAINTENANCE
DOWNSTREAM_CIRCUIT_OPEN
REBALANCE_OR_RECOVERY_CONTROL
~~~

If the DB scheduler sees the database healthy and calls `resume()` while an operator intentionally paused for maintenance, the container can be resumed wrongly. A good design should have a **pause coordinator** or clear state-ownership rules.

Example policy:

~~~text
pauseReasons = {DATABASE_OVERLOAD, MANUAL_MAINTENANCE}

DB recovers:
  remove DATABASE_OVERLOAD
  pauseReasons = {MANUAL_MAINTENANCE}
  => STILL PAUSED

Operator finishes maintenance:
  remove MANUAL_MAINTENANCE
  pauseReasons = {}
  => RESUME
~~~

If `DefaultErrorHandler` or `ContainerPausingBackOffHandler` also uses pause state, verify interactions with health-based pausing in your Spring Kafka version. Never assume one subsystem knows all reasons held by another subsystem.

## 11. Events to observe actual pause/resume

Spring Kafka can publish `ConsumerPausedEvent` and `ConsumerResumedEvent` when consumers pause/resume.

~~~java
@Component
public class KafkaPauseLogging {

    @EventListener
    public void paused(ConsumerPausedEvent event) {
        log.info(
                "Kafka consumer paused, partitions={}",
                event.getPartitions()
        );
    }

    @EventListener
    public void resumed(ConsumerResumedEvent event) {
        log.info(
                "Kafka consumer resumed, partitions={}",
                event.getPartitions()
        );
    }
}
~~~

This example illustrates listening for events; exact event signatures/getters should be checked against your Spring Kafka API. You can emit metrics for paused duration, resume counts, and flapping.

Distinguish:

1. Controller decides to pause.
2. `pause()` command is issued.
3. Container applies pause.
4. Records already delivered to the listener finish.
5. Database begins recovering.

These are distinct points in time. Do not treat a successful pause event as proof that every database transaction has stopped.

## 12. Pause the whole container or pause per partition?

If the entire database is overloaded, pausing the whole container is usually appropriate:

~~~java
container.pause();
~~~

If only a single partition/tenant generates abnormal load and the workload allows it, you can request a partition pause in supporting versions:

~~~java
TopicPartition partition =
        new TopicPartition("orders.events", 2);

container.pausePartition(partition);

// When processing can continue:
container.resumePartition(partition);
~~~

When pausing an individual partition, manage topic/partition assignments:

- Only the consumer currently assigned that partition controls reading from it.
- Partitions can change owners during rebalances.
- Pause state and fairness policies must be restored or updated when assignments change.
- Do not assume the partition with highest lag is the one causing DB overload.
- When the database is globally saturated, pausing just one partition may not shed enough load.

With `ConcurrentMessageListenerContainer`, understand which child consumer `pausePartition` applies to and how state behaves after rebalance in your version.

## 13. Why does pause keep the consumer in the group?

A Kafka consumer must poll on time per the group protocol. A listener sleeping for too long can exceed `max.poll.interval.ms` and lose partition ownership. Spring Kafka's container pause lets the consumer keep polling while paused, thereby maintaining normal membership.

~~~text
Container paused:
   |
   +--> consumer.poll() continues
   |
   +--> no new records delivered to listener
   |
   +--> group membership maintained
   |
   +--> consumer lag may increase
~~~

Conversely, code like:

~~~java
@KafkaListener(topics = "orders.events")
public void onOrder(OrderEvent event)
        throws InterruptedException {

    Thread.sleep(600_000L);
    orderService.process(event);
}
~~~

keeps the consumer thread trapped in the listener, interrupting polls. This is not a safe backpressure strategy.

**Important:** pause does not automatically solve a listener blocked inside JDBC. If a query hangs before the container returns to poll, you still risk exceeding `max.poll.interval.ms`. Set connection/query/transaction timeouts and bound batch processing time.

## 14. Offset ack must follow database commit

Pause only controls inflow. A record already inside the listener must still be processed under the proper acknowledgment policy:

~~~text
Record E
   |
   v
Begin DB transaction
   |
   +--> Business update
   |
   +--> DB commit succeeds
   |       |
   |       v
   |   Listener returns success
   |       |
   |       v
   |   Kafka offset commits per AckMode
   |
   +--> DB exception / rollback
           |
           v
       Listener throws exception
           |
           v
       Error handler retries / recovers
~~~

Never acknowledge early just to lower lag. Wrong example:

~~~java
public void onOrder(
        OrderEvent event,
        Acknowledgment acknowledgment) {

    acknowledgment.acknowledge(); // Wrong position

    orderService.saveToDatabase(event);
}
~~~

A better example with manual ack:

~~~java
@KafkaListener(
        topics = "orders.events",
        containerFactory = "manualAckFactory"
)
public void onOrder(
        OrderEvent event,
        Acknowledgment acknowledgment) {

    orderService.processIdempotently(event);

    acknowledgment.acknowledge();
}
~~~

`manualAckFactory` must be configured with `AckMode.MANUAL` or `MANUAL_IMMEDIATE`. `processIdempotently` returns only after the database transaction has safely completed.

If the listener dispatches work to a thread pool and returns right away, `AckMode.RECORD` may commit offsets before the database finishes. Pause does not fix that completion-boundary flaw. Process synchronously or use an async ack mechanism that properly tracks completion and ordering.

## 15. Idempotency ensures safety across pauses, crashes, and rebalances

An event can complete database processing successfully yet fail to commit its Kafka offset before the container crashes, stops, or rebalances. A new consumer may re-read that event.

~~~text
Consumer A:
  DB COMMIT succeeds
  Kafka offset NOT YET committed
  JVM crashes
       |
       v
Consumer B:
  redelivers event E
       |
       v
  If not idempotent: DB update may run a second time
~~~

Use `eventId` and a database unique constraint:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(150) NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Implement the service inside a single database transaction:

~~~java
@Transactional
public void processIdempotently(OrderEvent event) {

    boolean firstTime = processedEvents.insertIfAbsent(
            "orders-service",
            event.eventId()
    );

    if (!firstTime) {
        return;
    }

    orders.apply(event);
}
~~~

`insertIfAbsent` must use an atomic insert/unique constraint; recording the marker and `orders.apply` sit inside the same DB transaction. If the DB rolls back, the processed marker must roll back too.

This does not eliminate redeliveries, yet it ensures **business effects** are not duplicated when records are redelivered after incidents.

## 16. Error handlers and health-based pause serve different roles

The two mechanisms complement each other:

| Mechanism | Trigger | Goal |
|---|---|---|
| Health-based pause | Database is overloaded or circuit breaker is open | Reduce new incoming work |
| `DefaultErrorHandler` | Listener throws an exception on a specific record | Retry or recover the record |
| `BackOff` | Retryable record needs a wait | Pace retry attempts |
| DLT | Permanent error or retries exhausted | Store unprocessable records |
| Circuit breaker | Downstream is currently unhealthy/unstable | Prevent additional dependency calls |

Error handler example:

~~~java
@Bean
DefaultErrorHandler ordersErrorHandler(
        KafkaTemplate<Object, Object> dltTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(dltTemplate);

    DefaultErrorHandler handler =
            new DefaultErrorHandler(
                    recoverer,
                    new FixedBackOff(1_000L, 2L)
            );

    handler.addNotRetryableExceptions(
            InvalidOrderEventException.class
    );

    return handler;
}
~~~

If the DB fails temporarily, the listener must still throw the exception so the error handler knows the record did not succeed. Never swallow errors and return normally, because the container may commit the offset. If a payload is permanently invalid, pausing the DB helps nothing; classify as non-retryable and route to DLT/quarantine.

During a long DB outage, aggressive retries can add extra pressure. Coordinate backoff retries with health-based pausing. If retries exhaust too fast while the DB is only temporarily unavailable, massive numbers of valid records may be dumped into the DLT; choose policies matching expected recovery times and SLAs.

## 17. ContainerPausingBackOffHandler vs. health-based pause

Spring Kafka provides `ContainerPausingBackOffHandler` for error handling to wait out long retry backoffs while continuing to poll.

~~~text
Failed record
    |
    v
DefaultErrorHandler / BackOff
    |
    v
ContainerPausingBackOffHandler
    |
    +--> pause for backoff interval
    +--> polling continues
    |
    v
Retry failed record
~~~

Health-based pause is triggered by overall database condition without needing a failed record first. Both cases use the same pause primitive yet serve different goals.

When using both, ensure one component does not resume the container while the other still requires pausing. Verify state and lifecycle for your Spring Kafka version and actual listener factory.

## 18. Concurrency, max.poll.records, and database load

When the database is the bottleneck, raising Kafka concurrency increases concurrent DB calls, making matters worse.

~~~text
Concurrency 3:
  3 consumer threads
  about 3 concurrent DB operations running

Concurrency 12:
  12 consumer threads
  about 12 DB operations contending for connections
~~~

These figures illustrate only a synchronous listener doing one DB operation per record. Batch operations, async tasks, and multiple queries per record can consume more or fewer connections.

Mitigations:

- Cap concurrency according to database capacity.
- Lower `max.poll.records` so each poll fetches fewer records.
- Configure connection acquisition timeouts.
- Optimize queries/indexes and shorten transactions.
- Use batch inserts/updates where bulk APIs genuinely improve efficiency.
- Limit request admission from other sources sharing the DB.
- Calculate total pool capacity across all pods, not just one pod.

Example:

~~~yaml
spring:
  kafka:
    consumer:
      max-poll-records: 50
    listener:
      concurrency: 3
~~~

`max.poll.records` is the maximum records per poll, not a records/second rate or a limit on database queries. Smoother throttling may require a rate limiter or bounded worker queue at the processing layer.

## 19. Batch listeners need bounded processing duration

A batch listener receives a collection of records per callback. If a batch holds hundreds of records and the database slows down, the listener can stay trapped inside one database operation for too long.

~~~text
poll() -> 500 records
        |
        v
Batch listener
        |
        v
Database bulk write
        |
        +--> DB lock wait/timeout
        |
        v
Consumer has not returned to poll
~~~

At this point, a scheduler calling `pause()` cannot cancel the running query. Bound batch sizes, query timeouts, and transaction durations to avoid exceeding `max.poll.interval.ms`.

If a batch partially processes and then fails, already-processed records may be re-executed. Use bulk operations with clear transaction semantics and idempotency. Batch error handlers must identify failed records or batches according to your Spring Kafka version.

When low latency and per-record independence matter, record listeners can be easier to manage than batch listeners.

## 20. Multiple replicas and thundering herd upon resume

A 10-pod deployment can have 10 listener containers. Once the database recovers, all pods might detect healthy state and resume simultaneously.

~~~text
DB recovers
    |
    +--> Pod 1 resumes
    +--> Pod 2 resumes
    +--> Pod 3 resumes
    +--> ...
    +--> Pod 10 resumes
    |
    v
Backlog floods DB simultaneously
    |
    v
DB overloads again
~~~

Prevent cyclical oscillation:

1. Resume only after health stays stable across multiple samples.
2. Enforce cooldowns and minimum pause durations.
3. Limit concurrency or DB operation rate during recovery.
4. Consider staggered resuming with jitter if a coordinating controller exists.
5. Monitor query p99 and pool waiting threads right after resume.
6. If the DB overloads again, pause with hysteresis without continuous flapping.

A controller relying only on a single pod's local pool may fail to realize the DB is under load from other pods. Combine DB-wide signals or admission control at scale.

## 21. Consumer lag rising while paused is expected

Producers can continue publishing while consumers are paused. Data is not dropped by pausing; it accumulates in the Kafka topic per retention.

~~~text
Producer rate = 800 records/second
Paused 60 seconds

Backlog grows by roughly:
  800 * 60 = 48,000 records
~~~

This is an illustrative calculation assuming steady rates and no new records processed while paused. Rising consumer lag can be the right trade-off to keep the DB from crashing.

However, ensure:

- Kafka topic retention covers pause duration plus recovery time.
- Broker storage/quotas can hold the backlog.
- When the DB is healthy, consumer throughput exceeds producer rate to drain lag.
- Monitoring tracks **oldest unprocessed event age**, not just lag counts.
- A maximum SLA exists for event backlog age.
- A plan exists if a DB outage lasts longer than Kafka retention.

If maximum healthy throughput merely equals producer rate, backlog generated during pause will never drain. In that case, optimize the database or slow down upstream rather than just resuming.

## 22. When the database is completely down, pool utilization can mislead

If the database is completely down, the Hikari pool may fail to open any new connections. Active connections can drop to 0, tricking a controller watching only utilization ratio into thinking the DB recovered.

~~~text
DB down
    |
    +--> active connections = 0
    +--> waiting threads may rise
    +--> connection timeouts/errors rise
    +--> circuit breaker OPEN
~~~

Therefore, the resume condition must require `databaseHealthy()` or a stably CLOSED circuit breaker, not merely a ratio below the low threshold.

When the circuit breaker is HALF_OPEN, allow only a small number of deadline-bounded probes. Never unleash the entire backlog as a massive wave of concurrent probes.

Avoid continuously running a heavy SQL health check to verify the DB while the DB is overloaded. Use telemetry and bounded probes.

## 23. Partition pause, rebalance, and ownership

With per-partition pausing, assignments can change when the consumer group rebalances.

~~~text
Before rebalance:
  Consumer A -> P0, P1
  Consumer B -> P2

After rebalance:
  Consumer A -> P0
  Consumer B -> P1, P2
~~~

If P1 was paused under a specific policy, the application must define how that policy carries over once P1 moves to Consumer B. Do not assume in-memory state in Consumer A remains active in Consumer B.

Conversely, if the whole container paused due to shared database overload, each pod/container must independently evaluate health and maintain appropriate state after rebalance.

Never commit offsets just to skip a load-inducing record; failed records need error handlers/recovery. When a partition is revoked/lost, work already running on an old worker thread may still complete, creating duplicate side effects alongside the new consumer. Use event IDs, version checks, or fencing to protect the database.

## 24. Pause, stop, and throttling with rate limiters

| Action | Appropriate when | Trade-off |
|---|---|---|
| Container-wide `pause()` | DB temporarily overloaded, all partitions share the DB | Lag increases, processing rate drops near 0 |
| `pausePartition()` | One partition/tenant generates isolated load | Requires managing assignments and fairness |
| Rate limiter before DB calls | Need smoother throttling rather than full halt | Listener keeps receiving records; must avoid blocking poll too long |
| Lower concurrency | Sustained load adjustment | Can alter assignments and throughput |
| Lower `max.poll.records` | Reduce per-poll bursts | May lower throughput and raise overhead |
| Container `stop()` | Prolonged maintenance or shutdown | Consumer leaves group, may trigger rebalance |

Pause should not become a way to hide an N+1 query, missing index, or lock-holding transaction. Fixing the database bottleneck remains the foundational solution.

If the service must stay halted for several days, evaluate keeping containers alive in paused state versus a controlled stop; Kafka retention and pod resource costs guide the choice.

## 25. Common incidents

### Paused yet the listener keeps processing more records

The container had already polled data before pause. Check `pauseImmediate` if supported by your version, lower `max.poll.records`, and ensure finite listener processing times.

### Paused yet Kafka lag keeps climbing nonstop

This can be the expected result. Check retention, event age, and catch-up throughput instead of rushing to resume while the database still lacks capacity.

### Container fails to resume after DB becomes healthy

Check `isPauseRequested()`, `ConsumerResumedEvent`, controller health signals, manual pause reasons, container running status, and circuit breaker state. Do not leave an old pause reason forgotten.

### Immediately pauses again right after resume

Thresholds lack hysteresis or backlog surge hits too fast. Add dwell time, cooldown, and gradual ramp-up.

### Pool active connections very low yet listeners still time out

The DB may be down or connection acquisition is failing. Use circuit breakers/error rates/health state rather than watching active count alone.

### Pause fails to prevent max.poll.interval.ms expiry

The listener is blocked in a JDBC call and has not returned to poll. Set query/connection timeouts, bound batch sizes, and avoid `Thread.sleep` in listeners.

### Offsets committed yet DB is missing records

The listener may have returned/acked before DB commit or swallowed exceptions. Fix completion boundaries; pause cannot restore erroneously committed records.

### DLT spikes during a DB outage

Retry policy may exhaust attempts too quickly. Separate transient database errors from permanent data errors; coordinate pause and retries instead of dumping valid records into the DLT en masse.

### Multiple pods resuming together overload the DB again

Use phased recovery or bounded rate admission instead of monitoring only each pod's own pool.

## 26. Monitoring and alerting

Monitor Kafka and the database together:

| Signal | Meaning |
|---|---|
| Pause requested count | How often the controller requested pause |
| Actual paused duration | Duration consumer actually stopped delivering records |
| Resume count/flapping count | Whether continuous oscillation is occurring |
| Consumer lag per partition | Where backlog sits |
| Oldest event age | Data freshness SLO |
| Records processed rate | Recovery throughput |
| Listener duration p95/p99 | Processing cost per record/batch |
| Hikari active/idle/total | Connection pool utilization |
| Hikari threads awaiting | Connection acquisition saturation |
| Hikari acquisition latency | Time spent waiting for connections |
| DB query latency/error rate | Downstream speed and failures |
| DB CPU/IO/lock waits | Nature of the bottleneck |
| Circuit breaker state | OPEN, HALF_OPEN, CLOSED |
| Error handler retry/DLT count | Record failures and recovery |
| Rebalance count | Consumer group stability |
| Duplicate event rejections | Whether idempotency protects against redelivery |

Actual metric names differ across Kafka client, Spring Kafka, Micrometer, HikariCP, and exporters. Some such as pause reasons or flapping must be emitted by the application itself.

A structured log sample:

~~~text
event=kafka_backpressure_pause
listener_id=ordersListener
reason=DATABASE_SATURATION
pool_active=19
pool_max=20
threads_waiting=4
db_circuit=CLOSED
container_state=PAUSE_REQUESTED
~~~

Never use event IDs, Kafka keys, or queries containing sensitive data as high-cardinality metric labels.

## 27. Testing operational scenarios

| Scenario | Expected outcome |
|---|---|
| Hikari pool reaches pause threshold | Controller requests pause on the right container |
| Pool below resume threshold, DB healthy | Resumes with hysteresis |
| DB down with active connections at 0 | Does not resume falsely |
| Pause mid-large poll | Already-polled records handled per semantics, new records halted |
| Producers keep sending while paused | Lag rises, records remain in Kafka |
| Prolonged pause | Container polls to stay in group while consumer thread is unblocked |
| Listener blocked in SQL query | Finite timeout triggers, does not hang forever |
| DB commits, crash before Kafka offset commit | Idempotency protects redelivery |
| Manual acknowledge called prematurely | Test catches data-loss risk |
| Multiple replicas resume together | Controller/rate limiter prevents fresh overload |
| Rebalance during partition pause | Assignments and pause state remain valid |
| Permanent schema error | Error handler/DLT handles it rather than pausing forever |
| Retries during DB outage | Does not create an infinite retry storm |
| Graceful shutdown while container is paused | Safe lifecycle and redelivery |

Verify actual pause state, committed offsets, database state, listener calls, and consumer lag. A unit test merely calling `pause()` on a mock container does not prove group membership and offset handling work properly.

## 28. Production rollout process

1. Identify database bottlenecks via query latency, pool waiting, and CPU/IO/lock metrics.
2. Configure connection/query/transaction timeouts; never let listeners block indefinitely.
3. Bound Kafka concurrency and `max.poll.records` to match DB capacity.
4. Ensure listeners return/ack strictly after DB commit.
5. Use event IDs or unique constraints to prevent duplicates on redelivery.
6. Use a stable `@KafkaListener` id and `KafkaListenerEndpointRegistry`.
7. Build a health controller consuming pool, error-rate, and circuit-breaker signals.
8. Apply `pause()`/`resume()` with hysteresis, dwell time, and cooldown.
9. Monitor actual pause/resume events and consumer lag.
10. With multiple pods, use recovery policies preventing thundering herds.
11. Maintain separate error handler/backoff/DLT policies for failed records.
12. Verify Kafka retention covers pause duration plus catch-up.
13. Test DB outages, query timeouts, crashes, rebalances, and recovery.
14. Establish runbooks for stuck pauses, flapping, and excessive backlogs.

## 29. Implementation checklist

- Clear definition of database overload rather than relying on a single metric.
- Pause/resume controlled through the Spring Kafka container, never calling `KafkaConsumer.pause()` from worker threads.
- Understand `isPauseRequested` differs from actual paused state.
- Know pause applies at poll boundaries; in-progress records are not auto-canceled.
- `pauseImmediate` enabled only when listener type and version support it.
- Pause/resume thresholds include hysteresis and stability windows.
- Controller does not resume while manual pause or circuit breaker OPEN remains active.
- Connection acquisition/query timeouts prevent hung listeners.
- Concurrency and `max.poll.records` match database capacity.
- Listener commits offsets strictly after durable side effects.
- Idempotency ensures redelivery does not duplicate DB effects.
- Retries are bounded; DLT handles permanent errors.
- Health-based pause does not swallow exceptions on in-progress records.
- Kafka retention suffices to hold data during pauses.
- Plan exists to drain backlog once the database recovers.
- Multiple replicas do not resume in a sudden load spike.
- Partition pauses are handled cleanly when assignments change.
- Monitoring covers pause duration, lag, DB latency, pool saturation, and DLT.
- Tested crash/rebalance occurring after DB commit and before Kafka offset commit.

**Conclusion:** Pausing Spring Kafka listeners when the database is overloaded is a backpressure measure to protect downstream: the container can stay in the consumer group and keep polling while stopping new record delivery. Data stays safely in Kafka until the system can process it. To make this design safe, combine health signals, hysteresis, timeouts, concurrency limits, post-DB-commit acknowledgments, idempotency, and a backlog drain plan. Pause is strictly an intake throttle valve; it **does not replace transactions, retry/DLT, or fixing the underlying database bottleneck**.

