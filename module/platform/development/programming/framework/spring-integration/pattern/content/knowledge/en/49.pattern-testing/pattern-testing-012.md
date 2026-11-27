# Testing Restarts with Pending Messages in Spring Integration

## 1. Problem: Restarting Before a Delayer Emits Its Message

A system receives an `OrderCreated` event and delays 30 minutes before sending a payment reminder. At 09:00, the Delayer accepts the message for order `order-501` and schedules emission for 09:30. The application is redeployed between 09:10 and 09:12.

Tests must prove:

1. A message received before the old process stops **still exists** after restart.
2. The new process finds the exact message and resumes the pending schedule.
3. The deadline **remains 09:30**, rather than silently shifting to 09:42 simply because the app restarted at 09:12.
4. When the application stays down past the scheduled time (e.g., 09:10–10:00), the overdue message gets a chance to be processed upon recovery.
5. Delayer emission is not confused with the entire consumer having completed its business effect.

This tests **pending-message recovery** for the *Delayer* Enterprise Integration Pattern. In the **SPRING_INTEGRATION_PATTERN** module, outcomes must be cross-checked against Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation branches. The goal is not just proving the application starts back up, but verifying **message flow, persisted state, and business outcomes** after a process disappears.

### A Test Using One ApplicationContext Is Not a Restart Test

~~~java
input.send(message);
Thread.sleep(2_000);
assertNotNull(output.receive(0));
~~~

The snippet above only proves a message can be emitted after a delay within **a single application lifecycle**. It does not test whether the message is persisted durably, the scheduler is recreated, or another process reads the data back.

Instead, the test must span at least **two separate lifecycles**:

~~~mermaid
sequenceDiagram
    participant T as Test harness
    participant A as ApplicationContext A
    participant DB as Persistent MessageStore
    participant B as ApplicationContext B
    T->>A: Start instance A
    T->>A: Send eventId=evt-501, deadline=09:30
    A->>DB: Persist pending message
    DB-->>T: Pending record readable
    T->>A: Close context A before deadline
    Note over A: Scheduler A stops
    T->>B: Start instance B with same DB/group ID
    B->>DB: Read pending message, recover schedule
    Note over B: Original deadline arrives
    B-->>T: Output contains evt-501
    T->>DB: Verify state after release
~~~

Two sequential `ApplicationContext` instances inside **the same JVM** form a very useful integration test. However, it still does not prove data survives **killing the entire JVM/host**; that requires testing across two separate processes or containers.

## 2. Minimum Conditions for Meaningful Recovery

A Delayer uses a `TaskScheduler` to schedule emissions. For positive delays, pending messages are managed by a `MessageGroupStore`. With an in-RAM store, data is lost when the process terminates. When messages must survive restarts, configure a **persistent** store such as `JdbcMessageStore` backed by a database whose lifecycle is independent of the restarted context/process.

| Component | What to Do in a Restart Test | Mistakes to Avoid |
| --- | --- | --- |
| `MessageGroupStore` | Same persistent DB shared by A and B | Recreating `SimpleMessageStore` or losing in-memory H2 data |
| `messageGroupId` | Keep the ID string stable between A and B | Changing ID per build/release so old groups cannot be found |
| Payload and headers | Serializable/deserializable across versions | Using RAM-only objects or incompatible class renames |
| Deadline | Store original timestamp, compare against actual emission time | Recomputing the entire delay at startup |
| `TaskScheduler` | A's scheduler stops; B starts and recovers schedule | Leaving A running and claiming B recovered it |
| Output channel | Dedicated probe for B, asserting exact `eventId` | Reading message from A's queue instead of B's |
| Transaction | Verify the pending message **committed** | Seeing uncommitted data on the producer's own connection |
| Consumer | Proper retry/idempotency policy | Claiming exactly-once just because output was received once |

**Key distinction:** `messageGroupId` is the ID of the pending message group inside a Delayer; `MessageHeaders.ID` identifies one `Message` object; `correlationId` links parts of the same workflow; and `eventId` should be a stable business key for reconciliation and deduplication.

### Choosing Relative Delay vs. Absolute Time

| Configuration | Meaning | What to Verify After Restart |
| --- | --- | --- |
| `delayExpression("headers['delayMs']")` returning `Long` | Relative wait measured from when Delayer received the message | Does not restart counting from zero at startup if original schedule data is recovered |
| `delayExpression("headers['releaseAt']")` returning `Date` | Absolute release timestamp | Preserves the exact target `Instant` |
| `defaultDelay(10_000L)` | Fallback when no delay is resolved | Does not silently fall back when deadline is missing/corrupt |

In the tests below, we choose an **absolute `Date`** so the deadline is easy to observe without depending on reinterpreting relative durations. An additional test covers `Long` delays.

## 3. Layered Testing Strategy

Do not rely on a single giant test for every failure mode. Split into layers:

| Layer | Goal | Tools / Criteria |
| --- | --- | --- |
| Unit | Convert business date/time into the right deadline | Injectable `Clock`, `Instant`, pure assertions |
| Single-context integration | Delayer stores pending and emits when due | `MessageGroupStore`, `PollableChannel.receive(timeout)` |
| Two-context integration | A closes, B reopens with same DB and group | Verify pending before restart, release in B |
| Process restart | JVM/container A killed, JVM/container B reads DB | Two separate processes, DB outlives A |
| Failure injection | DB error, crash on release, consumer failure | Fault injection, retry/error channel, reconciliation |
| Multi-instance | Two instances see the same pending message | Test ownership/races and idempotency |

**Async testing rule:** wait for **actual messages or state** with a bounded timeout, rather than guessing "sleeping 2 seconds is probably enough for recovery." For **downtime past deadline** tests, wait for the exact time condition using a proper polling/clock tool instead of arbitrary unconditioned sleeps.

## 4. Setting Up PostgreSQL Outside the Application Lifecycle

The example uses PostgreSQL because `JdbcMessageStore` can persist messages in a database and Spring Integration ships a matching JDBC schema. In a JVM restart test, the database container must stay alive **across both A and B**.

Typical dependencies in a Spring Boot application, alongside compatible version management:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-jdbc</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jdbc</artifactId>
</dependency>
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
~~~

Depending on the Testcontainers version or BOM used by your project, artifact coordinates and versions may differ; use the dependencies managed by your project. For PostgreSQL, the schema must contain the tables and constraints required by `JdbcMessageStore`. In tests, you can run `org/springframework/integration/jdbc/schema-postgresql.sql` from the **matching-version** Spring Integration JDBC dependency.

Example DB setup in JUnit (initialization part of the test):

~~~java
import javax.sql.DataSource;

import org.junit.jupiter.api.BeforeAll;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
class PendingMessageRestartIT {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    static DataSource database;

    @BeforeAll
    static void prepareSchema() {
        database = new DriverManagerDataSource(
                postgres.getJdbcUrl(),
                postgres.getUsername(),
                postgres.getPassword());

        var schema = new ResourceDatabasePopulator(
                new ClassPathResource(
                        "org/springframework/integration/jdbc/schema-postgresql.sql"));
        schema.execute(database);
    }

    // Flow configuration and @Test methods appear below.
}
~~~

**Test operation note:** a static `@Container` keeps PostgreSQL alive throughout the test class lifecycle, while `ApplicationContext A` and `B` are created and closed separately. If A and B share `jdbc:h2:mem:...`, data may be lost when connections/contexts close; that is not a trustworthy test for restarts across JVMs.

## 5. Configuring Spring Integration for Message Recovery

A minimal configuration uses:

- `DirectChannel` as input.
- `JdbcMessageStore` to persist pending messages.
- A fixed `messageGroupId` without deployment IDs.
- `delayExpression` reading a `Date`-typed `releaseAt` header.
- A dedicated output `QueueChannel` for **each context**, so the test receives and verifies the message emitted by context B.
- A probe after the Delayer recording **release time**; this is a better marker than measuring when the JUnit thread wakes up.

~~~java
import java.time.Instant;
import java.util.concurrent.atomic.AtomicReference;

import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jdbc.store.JdbcMessageStore;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class RestartDelayFlowConfig {

    public static final String GROUP = "billing.pending-reminder.delay.v1";

    @Bean
    public JdbcMessageStore delayedMessageStore(DataSource dataSource) {
        return new JdbcMessageStore(dataSource);
    }

    @Bean("restart.in")
    public MessageChannel input() {
        return new DirectChannel();
    }

    @Bean("restart.out")
    public PollableChannel output() {
        return new QueueChannel();
    }

    @Bean
    public AtomicReference<Instant> releaseObservedAt() {
        return new AtomicReference<>();
    }

    @Bean
    public IntegrationFlow restartAwareDelayFlow(
            JdbcMessageStore store,
            AtomicReference<Instant> releaseObservedAt) {

        return IntegrationFlow.from("restart.in")
                .delay(d -> d
                        .messageGroupId(GROUP)
                        .messageStore(store)
                        .delayExpression("headers['releaseAt']")
                        .defaultDelay(10_000L))
                .handle(String.class, (payload, headers) -> {
                    releaseObservedAt.set(Instant.now());
                    return payload;
                })
                .channel("restart.out")
                .get();
    }
}
~~~

Points to watch:

1. `JdbcMessageStore` uses the `DataSource` supplied by the test. Never create a fresh database for context B.
2. `GROUP` must match across both contexts; otherwise pending messages in the old group may not be rescheduled.
3. Payloads use `String` and headers use `Date`/`String` for clean serialization across restarts.
4. `releaseObservedAt` is a probe of the **currently running context**. When the message appears on B's output, the timestamp was recorded in B, not A.
5. In a real application, output may go to a broker or consumer; the `QueueChannel` used here **only tests the handoff** and is not itself durable after the message leaves the Delayer.

## 6. Starting Two ApplicationContexts Sharing One DataSource

Do not use `@SpringJUnitConfig` with a single context and mutate state to fake a restart. A test can start two Spring contexts sequentially:

~~~java
import javax.sql.DataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

static AnnotationConfigApplicationContext openApplication(DataSource database) {
    AnnotationConfigApplicationContext app =
            new AnnotationConfigApplicationContext();

    // Register the same DataSource for both instances.
    app.getBeanFactory().registerSingleton("dataSource", database);
    app.register(RestartDelayFlowConfig.class);
    app.refresh();
    return app;
}
~~~

This method is added to `PendingMessageRestartIT` from section 4. It creates a new application context (with fresh Delayer and scheduler beans) while pointing to the same `DataSource` backed by the Testcontainers PostgreSQL instance.

**Regarding versions:** startup of `DelayHandler` with a persistent store includes rescheduling of persisted pending messages. Do not call `reschedulePersistedMessages()` repeatedly in normal tests unless specifically testing administrative actions; verify the startup behavior of your exact version. If recovery does not occur, verify that the endpoint actually started, DB schema exists, and group IDs match before modifying code.

## 7. Primary Scenario: Restart **Before Deadline**

Test requirements:

1. Context A receives `eventId=restart-before-001` and persists the message into the JDBC store.
2. Before the deadline, the test verifies the group holds one pending message.
3. Close A **before the deadline**, so A's scheduler has no active tasks left.
4. Open B with the same store and group ID.
5. Wait for the message on B's output.
6. Verify the payload, `eventId`, release timestamp no earlier than the original deadline, and that the pending group has been cleared.

~~~mermaid
gantt
    title Illustrative timeline (local time for display)
    dateFormat HH:mm
    axisFormat %H:%M
    section Pending message
    Original deadline 09:30 :milestone, m1, 09:30, 0m
    section Application
    Context A active :09:00, 10m
    App down :crit, 09:10, 2m
    Context B active :09:12, 18m
~~~

In test code, use `Instant` and `Date` so tests never depend on the CI machine's default timezone.

### JUnit Integration: A Closes, B Receives the Message

~~~java
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Date;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.jdbc.store.JdbcMessageStore;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

// Method placed in PendingMessageRestartIT (section 4).
@Test
void restoresPendingMessageAcrossApplicationContexts() {
    // Date has millisecond precision: avoid nanosecond comparison mismatch.
    Instant dueAt = Instant.now().plusSeconds(15)
            .truncatedTo(ChronoUnit.MILLIS);

    AnnotationConfigApplicationContext appA = openApplication(database);
    try {
        MessageChannel input =
                appA.getBean("restart.in", MessageChannel.class);

        assertTrue(input.send(
                MessageBuilder.withPayload("ORDER-501")
                        .setHeader("eventId", "restart-before-001")
                        .setHeader("correlationId", "order-501")
                        .setHeader("releaseAt", Date.from(dueAt))
                        .build()));

        JdbcMessageStore store = appA.getBean(JdbcMessageStore.class);
        assertEquals(1, store.getMessageGroup(
                RestartDelayFlowConfig.GROUP).size());
    } finally {
        appA.close();
    }

    assertTrue(Instant.now().isBefore(dueAt),
            "Context A must close before the deadline; if CI is too slow, " +
            "increase the test delay window");

    AnnotationConfigApplicationContext appB = openApplication(database);
    try {
        PollableChannel output =
                appB.getBean("restart.out", PollableChannel.class);

        // receive(timeout) returns immediately once the message arrives.
        Message<?> recovered = output.receive(20_000);
        assertNotNull(recovered, "Context B did not release the pending message");
        assertEquals("ORDER-501", recovered.getPayload());
        assertEquals("restart-before-001",
                recovered.getHeaders().get("eventId"));

        AtomicReference<Instant> releaseObservedAt =
                appB.getBean("releaseObservedAt", AtomicReference.class);
        assertNotNull(releaseObservedAt.get());
        assertFalse(releaseObservedAt.get().isBefore(dueAt),
                "Message must not be emitted before the persisted deadline");

        JdbcMessageStore store = appB.getBean(JdbcMessageStore.class);
        assertEquals(0, store.getMessageGroup(
                RestartDelayFlowConfig.GROUP).size());
    } finally {
        appB.close();
    }
}
~~~

**Scope of code:** these pieces assemble into one test class per sections 4–7 rather than being one verbatim copy-paste Java file: place `@Test` inside `PendingMessageRestartIT`, `openApplication` inside that class, and `RestartDelayFlowConfig` in its own configuration class. Run against PostgreSQL with the right schema and compatible dependencies and versions.

### Why Are These Assertions Meaningful?

- `store.getMessageGroup(...).size() == 1` proves the pending message exists **in the store** before A closes, not merely as a task in scheduler RAM.
- `appA.close()` terminates A's lifecycle; B has a fresh scheduler and endpoint.
- `output.receive(20_000)` is **event-driven waiting**, not blindly sleeping for 15 seconds.
- Probe `releaseObservedAt` placed **in the flow right after the Delayer** captures emission time at the endpoint instead of when the JUnit thread wakes up.
- `size() == 0` after release confirms the message is no longer in the pending group; it does not prove the final consumer finished business processing.

**Timing limit:** if CI is too slow, A may close **after** the deadline and the test should fail on the precondition assertion rather than pretending it tested a pre-deadline restart. Choose a deadline and timeout with headroom. Never degrade reliability by replacing conditions with `Thread.sleep(...)`.

## 8. Restart Scenario **After Deadline**

Another case: A receives at 09:00, deadline 09:30, A stops at 09:10, and B starts only at 10:00. The message became **overdue** during downtime.

~~~mermaid
flowchart TD
    A[A receives message with fixed dueAt] --> B[DB commits pending message]
    B --> C[A stops before deadline]
    C --> D[Deadline passes while app is down]
    D --> E[B starts with same MessageStore]
    E --> F[Reschedule/recover overdue message]
    F --> G[Release after B becomes active]
    G --> H{Business condition still valid?}
    H -->|Yes| I[Consumer processes]
    H -->|No| J[Audited discard]
~~~

To write the test:

1. Send a message with `releaseAt = Instant.now().plusSeconds(5)` to A; close A immediately after confirming pending persistence.
2. Wait until the clock passes `releaseAt` using an **explicit condition**, e.g. Awaitility `until(() -> !Instant.now().isBefore(releaseAt))`; do not sleep an arbitrary duration.
3. Open B; wait for the message on B's output via `receive(timeout)`.
4. Assert the right `eventId` and that it emits promptly after B starts; B must not wait another 5 seconds from startup.
5. If the business action is sending a reminder, the consumer must re-check order status to avoid sending a reminder when the customer already paid during downtime.

Conditional deadline-wait snippet:

~~~java
import java.time.Duration;
import java.time.Instant;
import static org.awaitility.Awaitility.await;

Instant releaseAt = Instant.now().plusSeconds(5);

// After A has closed and pending data has committed:
await().atMost(Duration.ofSeconds(10))
        .until(() -> !Instant.now().isBefore(releaseAt));

// Start ApplicationContext B then call output.receive(timeout).
~~~

This snippet illustrates a **test harness** requiring the Awaitility library. Waiting for the deadline to pass is intentional for the **overdue** case; it is completely different from sticking `Thread.sleep(5000)` into every test "hoping" the scheduler finished. For fast runs, use a fake clock/scheduler in **unit tests** of time logic, while real recovery integration tests still exercise the real lifecycle and scheduler.

## 9. What Happens If Only an In-RAM Store Is Used?

A **negative/control test** should prove the boundary of the configuration:

1. Use an in-memory store (e.g., `SimpleMessageStore`) in A with a sufficiently long delay.
2. Verify the message is pending in A's store.
3. Close A; create B with **a brand-new RAM store**.
4. Verify B does not have that pending message.

Never run this kind of negative test against `JdbcMessageStore` itself because committed data must survive. Never assert only "no output after 100 ms" and conclude the message was lost forever; verify **the new store is genuinely empty** and no publisher is resending the same event.

**Common trap:** if A and B share one `SimpleMessageStore` instance in the same JVM, the message survives only because the test itself kept the object alive across restarts. That falsely simulates process boundaries. Tests must create **two independent RAM store instances**.

## 10. Transaction Boundary: Reading Committed Data from DB

With `JdbcMessageStore`, "message sent" and "durably committed" may not coincide if the send runs inside an outer transaction.

~~~mermaid
sequenceDiagram
    participant P as Producer transaction
    participant D as Delayer
    participant DB as Database
    participant R as Restart test
    P->>D: Send message
    D->>DB: Write pending inside transaction
    DB-->>P: Insert statement succeeds
    alt COMMIT
        P->>DB: COMMIT
        R->>DB: Query from independent connection
        DB-->>R: Pending message exists
    else ROLLBACK
        P->>DB: ROLLBACK
        R->>DB: Query from independent connection
        DB-->>R: Pending message not visible
    end
~~~

In a test annotated with `@Transactional` on **the JUnit method itself**, Spring Test may roll back at the end of the test. If A and B see data through the test's open transaction, that does not prove the message survives after commit. Safer practice:

- Do not wrap the entire A/B lifecycle inside one auto-rolling-back test transaction.
- If the producer needs a local transaction, use `TransactionTemplate` or a `@Transactional` service method and **wait for the transaction to commit** before closing A.
- Verify pending state from an **independent connection/transaction** after commit.
- Test the rollback case: messages must not be recovered from uncommitted data.

In a Delayer flow, when the schedule is registered vs. when the transaction commits must be checked against your actual Spring Integration version and configuration. Do not assume that because an SQL insert returned, B's scheduler will always see that record.

## 11. Testing Restarts at the Real **JVM/Process** Level

Two `ApplicationContext`s in one JVM make a fast integration test, yet do not prove:

- Classloader, process, heap, and scheduler **are all destroyed**.
- The database does not rely on A's connections.
- Data remains readable after the JVM vanishes completely.
- Version B's config can still deserialize payloads/headers persisted by version A.

For true end-to-end restart verification, run **two independent processes** against an external DB:

~~~text
Test harness / CI
 ├─ PostgreSQL (kept running throughout test)
 ├─ Process A (writer app)
 │    ├─ START
 │    ├─ SEND eventId=restart-process-001, dueAt=UTC...
 │    ├─ REPORT persisted-and-committed
 │    └─ KILL / STOP before deadline
 └─ Process B (reader app)
      ├─ START with same database + group ID
      ├─ OBSERVE recovered pending message
      ├─ OBSERVE release after deadline
      └─ REPORT eventId and business state
~~~

### Automatable Runbook

1. Start PostgreSQL Testcontainers or an independent test DB; create the schema once.
2. Start process A with fixed connection settings, `messageGroupId`, and serializer.
3. Send a message with a unique `eventId` and a sufficiently distant deadline; wait for a **persisted-and-committed signal** read from DB.
4. Stop A cleanly; in another test, use **kill -9 / process termination** to simulate a hard crash. The test must not leave process A running.
5. Verify the pending row still exists in PostgreSQL after A is dead.
6. Start process B from the same binary or a newer version, using the same DB and group ID.
7. Wait for B's observable keyed by `eventId` with a finite timeout: audit output, consumer inbox, message broker, or test endpoint.
8. Verify deadline, processing count, and final state in the durable store; clean up test data and processes afterward.

**Never call `System.exit` inside the JUnit test runner JVM.** Run the test app as a **child process** or separate container; the harness is responsible for terminating it, waiting for process exit, and collecting logs/status. Only use hard kills in an isolated test environment.

## 12. Restart Does Not Prove Exactly-Once: Release Failure Windows

Delayer persistence protects **pending messages**. Once a message becomes due and is emitted downstream, a new boundary begins:

~~~mermaid
flowchart LR
    A[Pending in JDBC MessageStore] --> B["Release: emit to output"]
    B --> C["Queue / Broker / Handler"]
    C --> D[Business side effect]
    D --> E[ACK / Record completion]
    B -. "Crash / Retry" .-> F[Duplicate risk]
    D -. "Crash before ACK" .-> F
~~~

| Failure Window | What Can Happen | Additional Test Needed |
| --- | --- | --- |
| A dies **before pending commit** | No pending data saved | Transaction rollback and producer retry/outbox |
| A dies **after commit, before deadline** | Data remains in store | B recovers and emits on original deadline |
| B starts **after deadline** | Overdue message | Overdue recovery re-checks business state |
| Message released into RAM `QueueChannel`, B dies | Output queue can lose data | Separate durable handoff if needed |
| Broker ACKed yet handler failed to persist | Business state may be incomplete | Consumer ACK/transaction per contract |
| Handler performed side effect, process dies before confirm | May reprocess | Inbox/idempotency keyed by `eventId` |
| Retry or two instances emit concurrently | Duplicate | Unique constraint, idempotent receiver, and fencing/ownership |
| Serializer/payload class changed | Recovery cannot read message | Compatibility/migration test across both versions |

**Never claim exactly-once** because a test received one message in a single run. A single run rarely hits the hardest crash windows; business guarantees come from idempotent design and repeated fault-injection testing.

### Minimal Consumer Inbox

Example SQL in the consumer's database:

~~~sql
CREATE TABLE processed_event (
    event_id      varchar(128) PRIMARY KEY,
    processed_at  timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

The consumer can insert `eventId` in **the same transaction** as its business state change; duplicates hit a unique conflict or are skipped per database handling. If the consumer calls an external service outside the transaction, you also need idempotency at the target service or an outbox/saga to manage side effects.

For a reminder, `eventId=reminder:order-501:v1` must stay stable even if the Delayer re-emits it or a producer recreates a `Message` with a new Spring UUID.

## 13. When to Use `reschedulePersistedMessages()`?

`DelayHandler` provides a feature to recover/reschedule persisted messages. In a normal application lifecycle, proper configuration with a persistent store lets the endpoint recover messages at startup. Certain administrative scenarios may require triggering rescheduling explicitly.

However, in restart tests:

- **Prioritize testing B's natural startup behavior** rather than calling manual reschedule before knowing whether startup recovery works.
- If testing administrative operations separately, write a dedicated test; clearly log when it is called, pending counts before/after, and scheduler ownership.
- Do not call manual reschedule arbitrarily multiple times across multiple instances, as it can cause emission contention; understand the concurrency/transaction behavior of your version.
- If release retries are exhausted and a transaction rollback leaves the message **still in the store**, do not conclude a pending row guarantees an active task is still running; inspect scheduling state and explicit reschedule policies.

An operational scheduling method should never be used as a "band-aid" hiding database or group-ID misconfigurations in integration tests.

## 14. Multi-Instance Testing: Does Recovery Contend?

In a scaled-out environment, two instances may start up together and observe the same pending messages in a shared store.

~~~mermaid
sequenceDiagram
    participant DB as Persistent Store
    participant B as Instance B
    participant C as Instance C
    participant I as Idempotent Consumer
    B->>DB: Read pending group
    C->>DB: Read pending group
    Note over B,C: Both may see the same eventId
    B->>I: Release evt-501
    C->>I: Release evt-501 (race condition)
    I->>I: Apply side effect only once per eventId
~~~

**Sharing `JdbcMessageStore` and a group ID does not automatically guarantee safety for every active-active strategy.** Concurrent scheduling, claiming, transactions, and deletion depend on implementation and configuration. Design explicit ownership, locks/leases, or partitioning, and protect the **consumer** against duplicates.

Concurrency test:

1. Both B and C start against the same DB snapshot containing a pending message.
2. Start both instances nearly simultaneously using a `CountDownLatch` in the harness.
3. Wait for the expected number of `eventId`s **accepted by the consumer**; count total executions and rejected duplicates.
4. Check final pending group size, error logs, and transaction failures.
5. Repeat multiple times under varying schedules/load; never rely on a single passing run.

If the requirement is "only one instance may emit," you must have a provable ownership mechanism, not merely hope the DB prevents every race. If the design accepts at-least-once delivery, tests must prove the idempotent consumer still preserves a single business outcome.

## 15. Restart and Failure-Injection Test Matrix

| Test Case | Setup / Scenario | What Must Be Proven |
| --- | --- | --- |
| Restart before deadline | A closes before `dueAt`, B opens same DB | B finds pending, emits no earlier than original deadline |
| Restart after deadline | A closes and downtime passes `dueAt` | B handles overdue without waiting the full delay again |
| Restart with RAM store | A/B have two separate RAM stores | No recovery across new lifecycle |
| DB rollback | Pending write rolled back | B never sees uncommitted message |
| Temporary DB outage at B startup | Store unreachable | Error/health/alert detected, backlog not silently dropped |
| Incompatible serializer | A stores payload/header B cannot decode | Observable error and migration plan |
| Changed `messageGroupId` | B uses different ID than A | Orphaned pending messages detected and migration plan exists |
| Restart when handler fails | Release occurs yet handler throws | Retry/error channel and store state match policy |
| Crash after side effect | Consumer acted but has not ACKed | Idempotent inbox blocks duplicate effect |
| Two instances | B/C read same store | Ownership rules clear, duplicate risk verified |
| Non-durable output/broker | Message left Delayer yet output failed | Do not claim Delayer store protects all of downstream |
| Slow scheduler | Many messages become due together | Measure release lag and backlog; never treat deadline as hard SLA |

### Narrowing Down Bugs from Final State

| Symptom | Check First |
| --- | --- |
| B cannot find pending message | Same DB/schema or different? Did `messageGroupId` change? Did A commit? |
| Message still in store yet never releases | Did Delayer start? Does scheduler have tasks? Did rescheduling error? |
| B releases too late | Downtime duration, scheduler pool, database, backlog, and slow downstream |
| Message emitted multiple times | Retry/recovery/concurrent instances, transactions, and idempotency |
| B fails to deserialize | Payload, headers, Java class, serializer, and schema version |
| Event released yet business incomplete | Output channel/broker/consumer error or missing ACK |
| Two-context integration test passes, two-JVM fails | In-JVM resource, config/secrets, or DB connection not truly independent |

## 16. Observability to Verify Instead of Guessing

A test can inspect messages via `PollableChannel`, databases, and probes. Production also needs logs and metrics:

~~~text
flow=paymentReminder
delayGroup=billing.pending-reminder.delay.v1
eventId=reminder:order-501:v1
correlationId=order-501
receivedAt=2026-11-21T09:00:00Z
dueAt=2026-11-21T09:30:00Z
processInstance=deployment-B
recoveryAt=2026-11-21T09:12:00Z
releasedAt=2026-11-21T09:30:00.450Z
releaseLagMs=450
businessOutcome=SENT
~~~

These fields are **application-designed log attributes**, not all automatically emitted by Spring Integration.

| Metric | Meaning |
| --- | --- |
| `pendingMessageCount` | Pending messages remaining in the group |
| `oldestPendingAge` | Age of the oldest pending message |
| `overdueCount` | Messages whose deadline is in the past yet remain pending |
| `startupRecoveryDuration` | Time from B startup until required schedule recovery completes |
| `releaseLagMs` | `releasedAt - dueAt`; may be positive when scheduler lags |
| `releaseFailureCount` | Failed downstream release attempts |
| `duplicateSuppressedCount` | Duplicate messages blocked by the idempotent consumer |
| `businessCompletedCount` | Final completed business effects |

In tests, **do not equate** `pendingMessageCount == 0` with `businessCompletedCount == 1`. A message may have left the Delayer while still waiting in a queue/broker or retrying in a consumer. Those are two separate verification boundaries.

## 17. Preventing Flaky Tests: Wait on Conditions, Never Arbitrarily

### Never Use `Thread.sleep(...)` Just Because "It's Probably Due Soon"

| Technique | Usage in This Lesson |
| --- | --- |
| `PollableChannel.receive(timeout)` | Wait for B's output message |
| `MessageGroupStore.getMessageGroup(...).size()` | Check pending count in store |
| Awaitility `untilAsserted(...)` | Wait for a DB/health condition during async relay |
| `CountDownLatch` | Coordinate when writer committed or worker started |
| `Instant.now()` probe at release | Record release time on endpoint thread, reducing JUnit thread skew |
| `Clock.fixed(...)` | Test pure business deadline math, **does not drive TaskScheduler automatically** |
| JUnit `@Timeout` | Guard against infinitely hung tests |

### Test Isolation Rules

- Use a unique `eventId` per case and separate DB schemas/namespaces or controlled cleanup.
- Do not leave A running when B starts if the scenario requires a **non-overlapping** restart.
- Do not wrap the entire test in an auto-rolling-back `@Transactional` and assume persistence was tested.
- Wait for context B to finish `refresh()/start` before collecting output; for overdue messages, emission can happen during startup, so the output queue must be created **before** lifecycle startup runs.
- Never use A's `QueueChannel` as evidence that B recovered.
- Close `ApplicationContext` and the PostgreSQL container after tests; never leave scheduler threads alive between tests.
- For timestamp tests, pick timeouts with CI headroom and assert **no premature emission** via an endpoint probe; never assert emission at "exactly 15,000 ms."
- To prove zero permanent duplicates, use a durable inbox/side-effect counter and control all emission sources, not just a single `receive(0) == null`.

## 18. Practice Exercises

1. Implement `RestartDelayFlowConfig` using `JdbcMessageStore` with PostgreSQL. Send a 15-second delayed message in A; close A and verify B emits the matching `eventId`.
2. Replace the `Date`-typed `releaseAt` header with a `Long`-typed `delayMs`. Verify the original receipt time is still honored after restart.
3. Let A stay down past the deadline using a controlled time condition. Verify B releases the overdue message promptly after startup.
4. Switch from `JdbcMessageStore` to a RAM store and create B with its own store. Explain the difference.
5. Trigger a transaction rollback after sending a message into the Delayer. Check the store from another connection and verify B's result.
6. Run processes A and B in two separate JVMs/containers sharing a DB; kill A before the deadline and inspect the pending row.
7. Change `messageGroupId` between two runs; detect orphaned pending messages in the old group and propose a migration.
8. Give B a payload class incompatible with what A persisted; design a migration/deserialization test.
9. Once B finishes releasing, simulate a consumer failure; verify the error channel and retry/replay behavior per design.
10. Start B and C simultaneously against the same store. Count emissions vs. actual business effects protected by the consumer inbox.
11. Use an in-RAM outbound `QueueChannel`, stop B after release yet before consumer poll. Explain why the Delayer store alone is insufficient to preserve this message.
12. Collect `pendingMessageCount`, `overdueCount`, and `releaseLagMs` on restart with 100 messages sharing the same deadline; identify scheduler backlog signals.
13. Add a Filter after the Delayer to drop reminders if the order was already paid during downtime, then test the audited discard branch.

### Self-Check Questions

- Why are two sequential `ApplicationContext`s necessary yet insufficient to prove a **full-JVM** restart?
- Why must the database and `messageGroupId` remain stable between A and B?
- Why is reading an uncommitted row insufficient to prove a message survives restart?
- Why measure the timestamp at **endpoint release**, not only on the JUnit thread?
- How does restarting after the deadline differ from restarting before the deadline?
- When should `reschedulePersistedMessages()` be considered, and why should it not be called arbitrarily?
- Why does an output `QueueChannel` receiving a message not prove the consumer completed?
- Why are a stable `eventId` and an idempotent consumer required in crash/retry scenarios?
- If two instances both see a pending message, how do you prove no duplicate business effect occurs?

## References

- [Spring Integration Reference — Delayer](https://docs.spring.io/spring-integration/reference/delayer.html): persisting pending messages, schedulers, rescheduling persisted messages, and release timing.
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html): `MessageGroupStore` and choosing a persistent store.
- [Spring Integration Reference — JDBC Support](https://docs.spring.io/spring-integration/reference/jdbc.html): `JdbcMessageStore` and database schemas.
- [Spring Integration Reference — Testing Support](https://docs.spring.io/spring-integration/reference/testing.html): testing flows and endpoints.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): release failures and asynchronous error handling.
- [Testcontainers for Java — PostgreSQL](https://java.testcontainers.org/modules/databases/postgres/): database containers in integration tests.
- [Awaitility Documentation](https://github.com/awaitility/awaitility/wiki/Usage): waiting for a condition until true or timeout.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): distinguishing commits, rollbacks, and visibility across transactions.
