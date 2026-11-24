# Testing Failures Between Two Systems

A Spring Kafka application often coordinates **Kafka and a database** within a single business flow: consuming an event from Kafka and writing to PostgreSQL, creating an order in a database and emitting an event, or updating a database while producing output and confirming input offsets. These processes span **two systems with separate transaction coordinators and storage engines**. If one system commits while the other has not committed yet, a crash, timeout, or network drop can produce an inconsistent state.

**Testing failures between two systems** is not merely checking "does the listener retry when an error occurs?" The goal is actively injecting faults right at **commit boundaries**, observing durable data on both sides, and proving the system recovers under a defined policy: never losing critical business events, avoiding duplicate side effects, or reconciling discrepancies.

In Spring Kafka, a Kafka transaction can atomically commit Kafka outputs and input consumer offsets. Yet it **does not merge a database transaction into a distributed ACID transaction**. Therefore, tests must cover partial commits, ambiguous outcomes, redelivery, duplicates, and recovery cycles after instance restarts.

## 1. Define the reliability contract before writing tests

Before spinning up Testcontainers, state clearly what the system promises to the business.

Suppose the requirement is: "Every order successfully written to the database must eventually emit an `OrderCreated` event for downstream processing."

Guarantees to distinguish:

| Guarantee | Meaning | How to verify |
|---|---|---|
| Database atomicity | SQL changes in the same DB transaction commit or roll back together | Query DB state after injecting failure. |
| Kafka transaction atomicity | Kafka outputs and offsets included in the same Kafka transaction commit or abort together | Read topic with a `read_committed` consumer; verify committed offsets. |
| At-least-once delivery | Events may be resent/reread, but are never permanently dropped under covered recovery conditions | Restart/replay and wait for eventual completion. |
| Idempotent business processing | The same event is processed multiple times, yet the business effect applies once | Count ledger/balance updates or unique business rows. |
| Eventual publication | Once DB commits, the event eventually appears in Kafka even if the initial publish fails | Kill/restart outbox publisher, restore broker, and check event. |
| Ordering | Events for the same aggregate apply in required order | Produce multiple events with the same key and inject retries/rebalances. |
| Recovery visibility | When the two systems diverge, logs/metrics and repair procedures exist | Check outbox pending rows, alerts, or reconciliation results. |

**Exactly-once** must be scoped explicitly. Exactly-once on the Kafka side does not mean external databases or APIs execute business logic only once. In tests, designs are typically verified around **at-least-once delivery + idempotent processing** to guarantee correct final results.

### 1.1. Use a stable event ID

Every retry or replay should carry a stable `eventId`:

~~~json
{
  "eventId": "f08b42c3-3e24-440f-ae73-cbb3c5d8c6b0",
  "orderId": "O-1001",
  "status": "CREATED"
}
~~~

If the publisher resends the same event after an incident, the event ID **must not change**. Generating a fresh UUID on every retry makes it hard for downstream to recognize it as the same business event, even with Kafka producer idempotence enabled.

In the database, unique constraints can guard `event_id` and `order_id` per business policy. Tests must observe **the count of business effects**, not merely listener invocation counts.

## 2. Map commit boundaries of the flow under test

At least three common models exist, each with distinct failure windows:

~~~text
A. DB-first synchronous producer:
   Begin DB -> SQL -> Kafka send (transactional)
   -> DB COMMIT -> Kafka COMMIT

B. Kafka transactional listener + DB:
   Begin Kafka TX -> poll/handle -> Begin DB -> SQL
   -> DB COMMIT -> Kafka output + input offsets COMMIT

C. Transactional outbox:
   Begin DB -> SQL business + INSERT outbox -> DB COMMIT
   -> Outbox publisher -> Kafka publish -> mark sent/CDC checkpoint
~~~

Models A and B have **two independent commits**. Model C does not attempt to commit DB and Kafka together; it persists durable publish intent in the DB first, then emits the event asynchronously.

The test suite must establish **which system commits first**. Never infer commit order solely from the line order of `repository.save()` and `kafkaTemplate.send()`, because both calls usually execute **before** actual commits.

### 2.1. Mandatory failure matrix

| Fault injection point | DB committed? | Kafka committed? | Phenomenon to observe |
|---|---|---|---|
| Before DB write | No | No | No new business state or event. |
| After SQL, before DB commit | No | No | DB rolls back; no committed event. |
| Right after DB commit, before Kafka commit | **Yes** | No or unknown | Partial commit can occur; must recover/outbox/reconcile. |
| Kafka commit request sent, response lost | Yes | **Unknown** | Must not infer from exception that the event was definitely not written. |
| After both commits, before HTTP response | Yes | Yes | Client retry can create duplicate commands without idempotency. |
| After Kafka publish from outbox, before marking sent | Yes | Yes | Outbox republishes event; consumer must tolerate duplicates. |
| After DB commit in Kafka listener, before input offset commit | Yes | Offset uncommitted | Input may redeliver; DB must be idempotent. |

A test is meaningful only when it proves **post-incident data** and **post-recovery data**, not merely asserting that an exception was thrown.

## 3. Set up a realistic integration environment

Use a real database and real Kafka broker in tests, such as **PostgreSQL Testcontainers** paired with **Kafka Testcontainers**. Unit tests mocking `JdbcTemplate` and `KafkaTemplate` cannot verify commits, visibility, offsets, or transaction timeouts as in real systems.

Illustrative JUnit 5 + Spring Boot skeleton wiring dynamic endpoints into the application context:

~~~java
@Testcontainers
@SpringBootTest
class KafkaDatabaseFailureIT {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("orders_test");

    @Container
    static final KafkaContainer kafka =
            new KafkaContainer(
                    DockerImageName.parse("apache/kafka:3.8.1"));

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
        registry.add("spring.kafka.bootstrap-servers",
                kafka::getBootstrapServers);
        registry.add("spring.kafka.producer.transaction-id-prefix",
                () -> "failure-it-tx-");
    }
}
~~~

This snippet is a test skeleton requiring appropriate imports, Testcontainers Kafka/PostgreSQL modules, and Spring Boot classpath dependencies. `KafkaContainer` packages and supported Docker images vary across Testcontainers versions, so pick the image/API matching your actual dependencies rather than assuming every version is identical.

Helpful additional components:

- **Toxiproxy** to sever or throttle connections between the application and the broker or database.
- **Failpoints/barriers** in the application to pause execution right near commit boundaries.
- **A separate application process** for real process kills instead of only throwing exceptions inside the test JVM.
- **AdminClient** to inspect consumer group committed offsets and metadata.
- **Test consumer** configured with `isolation.level=read_committed` to observe Kafka outputs.
- **Direct database queries** post-incident to distinguish committed transactional state from cached persistence-context data.

Never share consumer groups or transactional IDs across tests running in parallel. Each test should use its own topic/group/instance ID namespace or controlled environment reset.

## 4. Why must fault injection hit the exact boundary?

Throwing an exception at the start of a listener only tests simple rollback. It **does not** reproduce the more dangerous case: **the DB committed successfully, yet Kafka has not committed**.

Example of a low-value test:

~~~java
when(repository.save(any())).thenThrow(new RuntimeException("db failure"));
assertThrows(RuntimeException.class, () -> service.handle(command));
~~~

This test only checks method error handling when the repository throws; no DB transaction ever committed and failed at Kafka commit.

To exercise failure windows, control the application at milestones such as:

~~~text
[1] After SQL, before DB COMMIT
[2] Right after DB COMMIT, before KAFKA COMMIT
[3] While Kafka commit request is in flight
[4] After KAFKA COMMIT, before updating tracking/outbox state
[5] After both commits, before response or offset acknowledgment
~~~

Not every milestone is easy to inject with a hook inside the same method. Spring transaction synchronization, lifecycle callbacks, and callback ordering must be understood accurately. If you need strong guarantees on **failure timing**, build an explicit seam in the test flow or run the application in a separate process to control crashes/network drops at boundaries.

## 5. Testing DB-first: failure before DB commit

In a DB-first model using the database transaction as primary, SQL or validation errors before commit should trigger DB rollback, while the Kafka transaction also never becomes committed output.

Example:

~~~java
@Transactional(transactionManager = "dataSourceTransactionManager")
public void createOrder(CreateOrder request) {
    orderRepository.insert(request.orderId());

    kafkaTemplate.send(
            "orders.created",
            request.orderId(),
            new OrderCreated(request.eventId(), request.orderId()));

    if (failureSwitch.failBeforeDbCommit()) {
        throw new IllegalStateException("injected-before-db-commit");
    }
}
~~~

The test must verify:

1. The method exits with an exception.
2. Re-reading the database in a **new transaction** shows no saved order.
3. A `read_committed` consumer sees no committed `OrderCreated`.
4. Events are not lost from the inbox or command queue per design, if an upstream source needs to retry.
5. The application does not leave the transactional producer stuck in an unusable state.

If using JPA, remember `flush()` does not equal `commit()`; tests must inspect data after the transaction ends, not merely call `entityManager.flush()`.

## 6. Testing the window: DB commit succeeds, Kafka commit fails

This is the single most important scenario for **DB-first commit order**. Once the database commits, no normal rollback call can revoke that transaction.

~~~text
DB COMMIT OK
      |
      +---- fault injection: Kafka unavailable / TX commit fails
      |
KAFKA COMMIT FAILED or UNKNOWN
      |
      +---- DB row still exists
      +---- Kafka event may not be visible yet
      +---- recovery must have data to reconcile
~~~

### 6.1. Controlling the milestone with two separately transacted methods

A pattern that hits this milestone cleanly is **a Kafka transactional listener calling a database writer in another bean**:

~~~java
@Service
public class OrderDbWriter {

    private final JdbcTemplate jdbc;

    public OrderDbWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(transactionManager = "dataSourceTransactionManager")
    public void apply(OrderEvent event) {
        jdbc.update(
                "INSERT INTO processed_orders (event_id, order_id) "
                + "VALUES (?, ?) ON CONFLICT DO NOTHING",
                event.eventId(), event.orderId());
    }
}
~~~

Listener with container Kafka transaction:

~~~java
@KafkaListener(
        topics = "orders.in",
        containerFactory = "transactionalListenerFactory")
public void onEvent(ConsumerRecord<String, OrderEvent> record) {
    dbWriter.apply(record.value());       // DB commits when method returns

    failureGate.afterDbCommit();          // test interception point

    kafkaTemplate.send(
            "orders.out",
            record.key(),
            new OrderAccepted(record.value().eventId()));
}
~~~

Once `dbWriter.apply()` returns successfully through the Spring proxy, its DB transaction has finished. The Kafka listener container has not committed its active Kafka transaction until the listener completes. `failureGate` is a test seam, **not a built-in Spring Kafka API**.

In the test, have the gate signal reaching this point and inject the fault: sever the **application process's** Kafka network using Toxiproxy, kill the application process, or throw an exception forcing the Kafka transaction to roll back. Depending on injection method, verify sequentially:

- The DB already contains `processed_orders(event_id)`.
- Neither the Kafka output transaction nor the input offset committed, or the commit outcome remains unknown if the network dropped mid-commit.
- Once the broker/application recovers, the input record is redelivered.
- The unique constraint prevents the DB from executing the business effect a second time.
- Post-recovery Kafka output stays consistent with the original event ID.

Note: merely throwing an exception at `failureGate` tests a deterministic **Kafka rollback after DB commit**. To prove **lost response on a Kafka commit request**, inject at the network/commit-request path; that is a distinct scenario.

### 6.2. Do not block inside the same JVM and pretend it crashed

A failpoint using `CountDownLatch` is great for pausing and controlling execution order. However, calling `Thread.interrupt()`, throwing an exception, or cancelling a future **is not the same as a process crash**:

- Spring can still run `finally`/rollback/lifecycle callbacks.
- The Kafka producer may still be closed cleanly.
- Database connections may stay alive and clean up automatically.
- Transaction commit may still be handled by the framework as the method unwinds.

To test a hard crash, run the Spring Boot application as a **child process/container** and kill it from an independent test controller. Then restart it with the same group configuration and observe persisted state.

## 7. Testing Kafka-first: Kafka event committed, database uncommitted

Even if most flows are DB-first, a cross-system failure suite should cover the reverse direction if the architecture uses Kafka-first or nested transactions.

~~~text
Kafka output COMMIT succeeds
         |
         v
DB COMMIT fails
         |
         +---- Consumer sees Kafka event
         +---- DB lacks corresponding business state
~~~

For example, a service uses an outer/inner Kafka transaction configuration and then attempts a DB write afterward. A database error can leave the event visible before business state exists.

Tests must prove whether this condition can occur under your specific design. If the requirement is "downstream must never observe a non-existent order," Kafka-first may be unsuitable unless compensation, pending states, or an explicit eventual-consistency contract is accepted.

**Do not infer Kafka-first just because `kafkaTemplate.send()` is called before `repository.save()`.** Verify the real transaction commit boundaries.

## 8. Testing unknown outcomes when commit responses are lost

A harder failure mode than an explicit failure is an **unknown outcome**:

~~~text
Application                        Kafka broker
     |                                  |
     +---- EndTxn(COMMIT) request ------>|
     |                                  | commit may have succeeded
     X  Network lost before response    |
     |                                  |
     +---- Outcome uncertain -------------+
~~~

The application may receive a timeout or exception, while the broker may already have committed. If a test assumes "an exception means the event definitely does not exist," that conclusion is unreliable.

An unknown-outcome test should:

1. Use a fixed event ID and observe downstream data once connectivity returns.
2. Inspect Kafka records using a `read_committed` consumer.
3. Never generate a new event ID when retrying.
4. Verify deduplication if retries lead to duplicate outputs.
5. Flag the incident as **requiring reconciliation** rather than rigidly classifying it as "committed" or "uncommitted" from the exception alone.
6. Assert test results using actual state on the broker and database.

Hitting the exact network drop point requires a test harness controlling request/response paths, sometimes via purposeful proxies or instrumentation. Do not treat randomly stopping the broker as proof that you intercepted the commit response specifically.

## 9. Testing redelivery after DB commit in a Kafka listener

A common failure: **the DB wrote durably, yet the Kafka input offset did not commit**. The Kafka consumer group can redeliver the same record after restart or rebalance.

Example input `PaymentCaptured(eventId=E-5, amount=100)`:

~~~text
Consumer receives E-5
       |
       v
Database updates balance or writes ledger
       |
       v
DB COMMIT succeeds
       |
       v
Kafka transaction rolls back / offset uncommitted
       |
       v
E-5 redelivery
       |
       v
Business operation risks running a second time
~~~

Tests must not only count listener invocations; they must verify **the count of business data mutations**.

An inbox/idempotency design in PostgreSQL:

~~~sql
CREATE TABLE consumed_event (
    consumer_name TEXT NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE account_ledger (
    id UUID PRIMARY KEY,
    event_id UUID NOT NULL UNIQUE,
    account_id TEXT NOT NULL,
    amount BIGINT NOT NULL
);
~~~

Within one database transaction, first insert the marker using `ON CONFLICT DO NOTHING`; apply the ledger mutation only if the marker insert succeeded. If a business error rolls back the DB transaction, the marker must roll back alongside the ledger.

The test resends the same event ID two or more times and verifies:

- The marker has exactly one row for the consumer/event.
- The ledger has exactly one business transaction.
- Post-recovery Kafka offsets advance properly when the listener completes.
- When handling a duplicate, the listener still completes cleanly without repeating side effects.

Do not assume a final `account.balance` "looking right" is sufficient if the system has audits or other side effects such as emails, payment API calls, or ledger inserts. Verify every effect that must not repeat.

## 10. Testing transactional outbox across DB–Kafka failures

**Transactional outbox** shifts the problem from "two commits must happen simultaneously" to "DB durably saves business state and publish intent in the same transaction; a publisher retries afterward."

~~~text
CreateOrder
     |
     v
DB TRANSACTION
  +---- orders INSERT
  +---- outbox_events INSERT
     |
     v
DB COMMIT
     |
     v
Outbox publisher -> Kafka
     |
     v
Mark published / CDC checkpoint
~~~

### 10.1. Invariants to prove

| Scenario | What must hold true |
|---|---|
| Error before DB commit | Neither a new order nor a new outbox event exists. |
| DB commits, Kafka is down | Order and outbox event remain in DB; publisher does not drop the event. |
| Kafka recovers | Outbox event is eventually published with the same event ID. |
| Publisher dies after publish, before mark sent | Duplicate may be published, yet downstream never applies the business effect twice. |
| Two competing publishers | Claim/lock mechanism prevents two workers from running uncontrolled duplicate effects. |
| Publishing fails repeatedly | Outbox retains retry state, alerts, and operational procedures; never deleted silently. |

### 10.2. Schema example

~~~sql
CREATE TABLE orders (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL
);

CREATE TABLE outbox_events (
    event_id UUID PRIMARY KEY,
    aggregate_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ NULL
);
~~~

The business service writes both tables in the same DB transaction. In tests, when injecting an exception before commit, both `orders` and `outbox_events` must roll back. When Kafka is down after commit, both rows persist and remain ready for the publisher to resume.

### 10.3. Failure after publish, before marking sent

This test verifies true outbox delivery semantics:

~~~text
Publisher reads outbox event X
       |
       v
Kafka publish succeeds
       |
       v
Inject crash before UPDATE published_at
       |
       v
Publisher restarts and reads X again
       |
       v
Kafka may receive X again
       |
       v
Consumer deduplicates based on eventId
~~~

Do not expect an outbox to eliminate all duplicates in Kafka. The standard model is **at-least-once publication**. Tests should prove event IDs stay constant across publishes and consumers never duplicate effects.

If using CDC (such as the Debezium outbox pattern), failure windows sit at connector offsets/checkpoints and broker publication. Test connector restarts, snapshots/replays, and duplicates rather than testing only a polling publisher.

## 11. Fault injection: pick the right tool for each failure type

| Method | What failure can it create? | Limitation |
|---|---|---|
| Throwing an exception at a service failpoint | Deterministic business/rollback errors before or after DB ops | Does not simulate hard crashes or network response loss. |
| Barriers/latches and a process controller | Pause execution at an exact stage before killing | Needs a dedicated test harness to avoid deadlocks. |
| Toxiproxy | Packet loss, latency, resets, severing broker/DB links | Hard to ensure packet cuts hit exactly at `EndTxn` without instrumentation. |
| Stopping/restarting Kafka container | Broker unavailable, producer timeouts, recovery | Can affect the entire test rather than a single connection. |
| Stopping/restarting PostgreSQL container | DB connection failures, transaction failures | Must not infer whether commit occurred from a socket exception alone. |
| Killing a child application via test supervisor | Hard crash without normal cleanup | Requires a separate process, log collection, and independent restart. |
| Purposeful custom wrapper/transaction synchronization | Inject at specific lifecycle seams | Must verify actual ordering of Spring callbacks. |
| Fault-injecting API/database client proxy | Simulate dependency timeouts or ambiguous responses | Does not replace commit tests with a real database and Kafka. |

Use **two layers of tests**: fast unit/contract tests with failpoints, plus integration/failure tests with a real broker and database. For hard crashes and unknown outcomes, use an out-of-process test controller.

Never ship unprotected failpoints to production. If chaos testing mechanisms remain in staging, guard them with configuration, access control, auditing, and allowlist only approved environments.

## 12. Designing failpoints without distorting business code

You can define a seam activated only in tests:

~~~java
public interface FailureGate {
    void afterDatabaseCommit();
    void beforeKafkaTransactionCompletes();
}
~~~

Default no-op implementation:

~~~java
@Component
@ConditionalOnMissingBean(FailureGate.class)
class NoopFailureGate implements FailureGate {
    @Override
    public void afterDatabaseCommit() {
    }

    @Override
    public void beforeKafkaTransactionCompletes() {
    }
}
~~~

In tests, an implementation uses `CountDownLatch` to signal "reached boundary" and wait for the controller to proceed. Crucial: a method name like `afterDatabaseCommit()` is accurate only if it is **truly invoked after the DB transaction commits**, such as after a transactional service returns through its proxy. Never name a callback `afterCommit` if it runs when SQL has flushed but the DB has not yet committed.

With Kafka transactions managed by a listener container, listener code **does not perform the final Kafka commit itself**. Therefore, a failpoint inside the listener can only sit "before the listener returns"; the actual commit occurs afterward in the container. To intervene precisely inside the transaction manager's commit phase, use proper instrumentation or transaction-lifecycle failpoints.

## 13. Verifying Kafka transactions with read_committed

When checking rolled-back records, configure a consumer with:

~~~java
Map<String, Object> config = Map.of(
    ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers,
    ConsumerConfig.GROUP_ID_CONFIG, uniqueTestGroupId,
    ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest",
    ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_committed",
    ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class,
    ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class);
~~~

This snippet illustrates the configuration map. In real tests, match deserializers to the event types on the topic.

Key conditions:

- `read_committed` never returns records from aborted transactions.
- A successful producer send future is **not** enough to prove transaction commit.
- A `read_uncommitted` consumer can see records from uncommitted or aborted transactions; using it to test Kafka transaction visibility leads to wrong conclusions.
- With open transactions, the last stable offset (LSO) can constrain how far a `read_committed` consumer reads.
- Inspect both output topics and **consumer group committed offsets** with the right APIs; they are not the same observation.

Example offset check: if an input at partition 0 offset 41 was processed and committed in a Kafka transaction, the committed group offset afterward is normally 42. If the transaction rolled back, the offset remains uncommitted, even though in-memory consumer position may have advanced on poll.

Never simply assert "the topic has a record" and declare success; verify **the record is committed** and has the expected event ID.

## 14. Database assertions must run after the test transaction

A common pitfall in Spring tests: putting `@Transactional` directly on the test method. Spring Test may open a transaction wrapping the entire test and roll it back at the end. That is convenient for ordinary database unit/integration tests, but masks real application commits and breaks tests coordinating with Kafka.

For failure-window tests:

- Avoid wrapping the whole test method in a test-managed transaction when observing **durable commits**.
- Let the application service start and end its own transactions.
- Use a fresh connection/transaction to query DB state after the application finishes or crashes.
- If using JPA, clear the persistence context or open a new `EntityManager`; do not rely on cached entities.
- When verifying isolation, check isolation levels and database-specific behavior.

Direct query example:

~~~java
Integer count = jdbcTemplate.queryForObject(
        "SELECT count(*) FROM outbox_events WHERE event_id = ?",
        Integer.class,
        eventId);

assertThat(count).isEqualTo(1);
~~~

If the test expects a database rollback, run the query only after the service transaction has truly ended. Querying inside the same uncommitted transaction can read transient data and produce false conclusions.

## 15. Running controlled restart/rebalance tests

A failure can trigger a consumer group rebalance, producer fencing, or record redelivery. Tests should actively exercise this:

~~~text
Instance A: poll event E
      |
      v
DB commit success
      |
      v
A is killed before Kafka offset commit
      |
      v
Consumer group rebalance
      |
      v
Instance B takes over partition
      |
      v
E redelivery
      |
      v
DB deduplication -> no duplicate effect
      |
      v
Kafka offset advances after successful processing
~~~

To keep tests deterministic, use **one input partition**, control consumer instances, and know event offsets upfront. When testing multiple partitions or high concurrency, distinguish redelivery duplicates on the same partition from independent parallel processing.

If producer A's transaction was fenced, do not keep retrying on the stale producer session. Verify that a valid instance creates a new producer session and resumes work. Colliding `transactional.id` values across two active-active replicas is a configuration bug, distinct from controlled failover.

## 16. Race conditions and business event ordering

Consistency is not just record counts. After failures/recovery, events may arrive late or be reprocessed out of order, especially with retry topics, multi-worker outboxes, or multiple aggregates.

Example for a single order:

~~~text
OrderCreated (version 1)
OrderPaid    (version 2)
OrderShipped (version 3)
~~~

If `OrderCreated` hits a publish failure and `OrderPaid` is emitted first, downstream consumers can see version 2 before version 1. Depending on business rules, this may be unacceptable.

Tests should verify:

1. Kafka keys use `orderId`/aggregate ID consistently.
2. Publishers preserve per-aggregate event order across outbox retries.
3. Consumers enforce versioning or buffering if events can arrive out of order.
4. DLT/replays never overwrite newer state with older events.
5. With multiple outbox workers, claiming does not inadvertently break per-aggregate ordering.

Kafka guarantees ordering **within each partition** in append order. It does not preserve business event ordering if the publisher emits events out of order or changes partition keys across versions.

## 17. Assert on final state rather than hardcoded timings

Failures across two systems involve nondeterministic timings: leader elections, transaction coordinator recovery, consumer rebalances, database reconnects, and retry backoffs.

An unstable test:

~~~java
publishEvent();
Thread.sleep(2000);
assertThat(orderRepository.count()).isEqualTo(1);
~~~

If CI runs slower, the test fails even when the system is healthy; if broken logic finishes fast, the test can pass falsely.

Wait on **observable conditions** with a bounded timeout, for example:

~~~java
await()
    .atMost(Duration.ofSeconds(30))
    .untilAsserted(() -> {
        assertThat(outboxRepository.countPending()).isZero();
        assertThat(ledgerRepository.countByEventId(eventId))
                .isEqualTo(1);
    });
~~~

This illustrates using Awaitility. Success conditions should tie to system SLOs and specific event IDs. Never wait merely for "consumer group is running," since that does not prove the event was processed.

For moments when **zero output is expected**, waiting briefly and asserting zero is weak evidence. Combine producer transaction state, committed offsets, and explicit synchronization milestones to confirm the event aborted or never committed.

## 18. Do not rely on ambiguous callback ordering

A common mistake is writing:

~~~java
@Transactional
void createOrder() {
    writeDatabase();
    kafkaTemplate.send("orders", event);
    registerAfterCommitCallback(() -> throw new RuntimeException());
}
~~~

and claiming the callback definitely runs **before the Kafka transaction commit**. In reality, `TransactionSynchronization` execution order depends on lifecycle, synchronization ordering, and how transaction managers integrate. Without verifying order or using an explicit seam, fault injection can fire at the wrong moment.

More reliable approaches:

- For Kafka transactional listeners: place a barrier **after the transactional DB writer finishes**, but before the listener returns.
- For DB-primary transaction synchronization: use verified commit-order instrumentation or a test transaction manager wrapper to inject precisely at secondary commit.
- For hard crashes: the parent test verifies DB committed, then kills the child process before the Kafka transaction completes.
- For unknown outcomes: inject a protocol-level network fault and verify actual persisted data rather than assuming an error means uncommitted.

Test descriptions should clearly state **which milestone is guaranteed** and **which milestone is only approximated**.

## 19. Extended failure matrix for outbox and DLT

When the system uses outbox, inbox, retries, or DLTs, critical scenarios expand:

| Failure | Correct behavior |
|---|---|
| Outbox insert fails inside DB transaction | Business mutation also rolls back. |
| Kafka goes down after DB commit | Pending outbox persists; publisher retries once broker recovers. |
| Publisher sends successfully then disconnects before ack | May retry and duplicate; event ID remains stable. |
| Publisher receives ack but updating published marker fails | Record may republish; deduplication keeps it safe. |
| Consumer finishes DB update, offset commit fails | Event redelivers; inbox blocks duplicate side effects. |
| DLT publish fails due to ACL/serializer | Recovery is never silently marked successful. |
| Retries exceed limit | Record is quarantined or handled by operator per runbook, never dropped. |
| Schema changes while queued | Publisher/consumer still decode older events or follow a migration plan. |
| Reconciliation job restarts mid-run | Has checkpoints and idempotent event replays. |
| Same event replayed from DLT and redelivered from main | Deduplication still prevents double application. |

Not every system uses DLTs or outboxes. Pick scenarios matching your active architecture, while documenting the limits of untested cases.

## 20. Observability and collecting evidence in tests

Every failure-window test should produce a minimal **evidence bundle**:

- `eventId`, `aggregateId`, topic, partition, offset, and consumer group.
- DB row counts and business state values post-failure and post-recovery.
- Outbox/inbox markers, retry counts, and published state if applicable.
- Kafka records committed under `read_committed`.
- Consumer group committed offsets; never confuse with in-memory consumer position.
- Timestamps of fault injection, restarts, rebalances, retries, and recovery.
- Exception classes from database, producer transactions, and listeners/error handlers.
- Correlation IDs in logs to trace operations across both systems.

A Kafka commit incident with an ambiguous result should be logged as **UNKNOWN** until state is reconciled. Tests must not normalize that error into `FAILED` or `COMMITTED` based solely on the exception.

In production, useful metrics include:

| Metric | To detect |
|---|---|
| Secondary Kafka commit failures after DB commit | Partial commits in DB-first models. |
| Outbox pending count/oldest age | Durable events stuck prior to publish. |
| Inbox duplicate suppression count | Redelivery rates or publisher duplicates. |
| Consumer lag per partition | Stuck partitions or prolonged retries. |
| DLT publish/recovery failure rate | Records failing quarantine/recovery. |
| Reconciliation mismatch count | DB and Kafka views out of sync. |
| Transaction abort/fencing count | Transaction coordinator, producer identity, or churn issues. |

## 21. Checklist for writing meaningful tests

Before considering a Kafka–database failure test suite good enough, answer:

1. **Which system commits first** in the real code path?
2. Does the test use a real broker/database or only mock methods?
3. Does the failpoint sit **before or after commit**, with evidence proving that timing?
4. After failure, does the test re-read the DB in a new transaction/connection?
5. Do Kafka assertions use `read_committed` when verifying transaction visibility?
6. Are input **committed offsets** verified, not only Kafka outputs?
7. On uncertain commit outcomes, does recovery preserve a stable event ID?
8. When a record is redelivered, is the business side effect applied **exactly once in business terms**?
9. If Kafka goes down after a DB commit, does outbox/reconciliation ensure the event eventually publishes?
10. If the publisher crashes after Kafka publish, do consumers tolerate duplicates?
11. If recovery takes longer, are metrics and alerts sufficient for operations?
12. Are tests deterministic with bounded timeouts instead of hardcoded sleeps replacing state checks?
13. Are transactional IDs, topics, and consumer groups isolated across test cases?
14. Are real hard crashes tested via a separate process when crash consistency must be proven?
15. During rollbacks/redeploys, do event schemas and backlogged records continue processing cleanly?

## 22. Choosing a testing strategy by risk level

| Level | Test suite | When appropriate |
|---|---|---|
| Baseline | Unit tests for idempotency/unique constraints and error classification | Every service using Kafka + DB. |
| Integration | PostgreSQL + Kafka Testcontainers, pre-commit failures, redelivery, DLT | Services needing stable at-least-once and transaction semantics. |
| Advanced | Fault injection for DB committed/Kafka rollback, unknown outcomes, Toxiproxy | Critical workflows relying on commit synchronization. |
| Crash consistency | Child application process, hard kills, restarts, reconciliation | Payments, ledgers, orders, or workflows requiring real recovery guarantees. |
| End-to-end | Outbox/inbox, multi-replica, rebalances, CDC, event replays, and reconciliation | Multi-service systems with long-term operational requirements. |

Higher levels require greater test runtime and cost, yet catch bugs that mocks and happy-path tests never expose. Run fast tests on every pull request, and organize heavy chaos/crash tests in dedicated integration pipelines with controlled environments.

**Testing failures between two systems** means testing the **committed, uncommitted, and uncertain** states of each resource. With Spring Kafka and a database, the goal is not proving that two independent transactions magically become one atomic transaction, but proving the system **never loses critical business data, recovers from partial commits, and tolerates duplicates**. A trustworthy test suite injects faults right at boundaries, observes durable state from both sides, and verifies final outcomes through explicitly designed outboxes, inboxes, idempotency, or reconciliation.
