# Restarts while messages are waiting in Spring Integration Delayer

## 1. What happens to a waiting message if the application restarts?

In Spring Integration, **Delayer** is an Enterprise Integration Patterns (EIP) endpoint that delays forwarding individual messages to the next step. With a positive delay, `DelayHandler` holds the message in a `MessageGroupStore` and uses a `TaskScheduler` to schedule its release after the waiting period.

For example, a sales service receives an order creation event at **09:00** and needs to send a payment reminder after **30 minutes**. At 09:10, the application begins deploying a new version. The system must answer:

- Does the pending message survive after the old process stops?
- When the new version starts, is the deadline still 09:30 or is it recalculated to 09:42?
- If the application only restarts at 10:00, how are overdue messages handled?
- If the message had been released to the consumer right before the process died, is there a risk of duplicate processing?
- If two instances start simultaneously and see the same message, which one gets to release it?

This is the **restart recovery** problem, encompassing storage, timing, flow initialization, message identification, transaction boundaries, and consumer behavior. In the **SPRING_INTEGRATION_PATTERN** module, it connects to building loosely coupled flows with Filters, Routers, Transformers, Gateways, retries, error channels, and correlation, while testing and monitoring processing branches.

**Goal of this lesson:** design and verify the lifecycle **receive → wait → stop → restart → release** of a message, even when downtime extends past the scheduled timestamp.

## 2. Three timestamps that must be tracked

| Timestamp | Meaning | Example |
| --- | --- | --- |
| `receivedAt` | Time when Delayer first received the message | 09:00 |
| `dueAt` | Time when the message becomes eligible for release | 09:30 |
| `releasedAt` | Actual time when the message reaches the output after Delayer | 09:30:01 or later |

With a relative 30-minute delay:

\[
\text{dueAt} = \text{receivedAt} + \text{delayMs}
\]

With an absolute delay passed as `java.util.Date`, `dueAt` is the exact timestamp requested by the message.

**A restart should not automatically extend the deadline of a waiting message.** When using a persistent store, Spring Integration provides a mechanism to restore schedules from stored message data. How the application interprets timestamps and stores headers should be verified against the deployed Spring Integration version, especially when changing configurations or serializers.

~~~mermaid
gantt
    title Example of restart before expiration
    dateFormat HH:mm
    axisFormat %H:%M
    section Message
    Wait until due              :active, 09:00, 30m
    section Application
    Version A active            :09:00, 10m
    Stop for deployment         :crit, 09:10, 2m
    Version B active            :09:12, 18m
~~~

The diagram depicts a hypothetical schedule. Actual release timing also depends on startup time, the scheduler, and the consumer.

## 3. Restarts with an in-memory store vs. a persistent store

| Scenario | `SimpleMessageStore` in JVM | `JdbcMessageStore` with persistent DB |
| --- | --- | --- |
| Message not yet due, process shuts down | Risk of losing message and schedule | Written/committed messages can remain in DB |
| Starting a new process | No RAM data from the old process | Delayer can read the waiting group and reschedule |
| Downtime exceeds deadline | No message to recover if RAM is lost | Can release overdue messages after startup |
| Payload serialization error | Not constrained by external JDBC storage | May fail to write/read message |
| Two instances accessing simultaneously | Each instance has separate memory | Must evaluate contention, locking, and idempotency |

**Prerequisite for recovery:** pending messages must reside in a store that exists independently of the stopped process. Simply configuring `defaultDelay(30_000L)` does not provide persistence. Replacing the output `QueueChannel` with a database also does not solve storing messages **before release time** if Delayer still keeps pending messages in RAM.

### Lifecycle across two processes

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant A as Delayer A
    participant DB as Persistent MessageStore
    participant B as Delayer B
    participant C as Consumer
    P->>A: eventId=reminder-501, wait 30 minutes
    A->>DB: Store message in group
    Note over A: A stops before due
    Note over DB: Committed message is retained
    B->>DB: Initialize with same messageGroupId
    DB-->>B: Pending messages
    B->>B: Reschedule by deadline
    Note over B: Due or already overdue
    B->>C: Release message
~~~

This diagram shows the intent of recovery. Writes, group removals, and retries may occur in separate transactions depending on configuration; you cannot conclude from this diagram that each downstream side effect occurs only once.

## 4. What must remain stable across restarts

A new deployment may change bean names, package structures, application version, and instance count. For waiting messages, pay special attention to:

| Component | Requirement |
| --- | --- |
| Delayer's `messageGroupId` | Keep stable so the new version reads the right group holding pending messages |
| `MessageGroupStore` | Same persistent data source, same schema, and connection details |
| Serializer/payload | New version must be able to decode messages from the previous version |
| Business headers | Preserve `eventId`, `correlationId`, and necessary deadline metadata |
| Output channel/consumer | Still has a valid processing target when the message is released |
| Transaction/error handling | Clear policy if release fails after restart |
| Clocks and time zones | Use UTC/`Instant` when exchanging absolute timestamps |

`messageGroupId` is set in a Delayer's configuration, e.g., `billing.reminders.delay.v1`. It is the **key of the pending message group**, not the ID of an individual message or order. Changing it to `billing.reminders.delay.v2` without a plan for the old group can leave messages sitting in the DB without being recovered by the new flow.

Each event should have a **durable `eventId`** generated by business logic, e.g., `reminder:order-501:payment:v1`. `MessageHeaders.ID` is a UUID attached to a Spring message instance; when an event is rebuilt as a new message, the UUID may differ. `correlationId` can link messages for the same order, while `eventId` identifies a specific logical action.

## 5. Spring Integration Java DSL example supporting schedule recovery

This example builds a simple flow:

~~~text
reminder.in -> Delayer (JDBC store) -> reminder.ready
~~~

`reminder.ready` is a `QueueChannel` used for illustration and testing; a real application needs a consumer handling messages at the output and an appropriate acknowledgment strategy.

Dependencies required in a Spring Boot application:

- `spring-boot-starter-integration`;
- `spring-integration-jdbc`;
- `spring-boot-starter-jdbc` with the corresponding JDBC driver;
- database and JDBC Message Store schema matching the Spring Integration version.

### 5.1. Declaring channels and the persistent store

~~~java
import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.jdbc.store.JdbcMessageStore;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class RestartAwareDelayChannels {

    @Bean("restartDelayedStore")
    public JdbcMessageStore restartDelayedStore(DataSource dataSource) {
        return new JdbcMessageStore(dataSource);
    }

    @Bean("reminder.in")
    public MessageChannel reminderInput() {
        return new DirectChannel();
    }

    @Bean("reminder.ready")
    public PollableChannel reminderReady() {
        return new QueueChannel();
    }
}
~~~

`JdbcMessageStore` stores messages using `DataSource`. Having just the Java bean is not enough: the database must outlive process shutdown, and JDBC Message Store tables must be created using a compatible schema. Use the SQL scripts bundled with Spring Integration JDBC and manage migrations with an appropriate tool such as Flyway/Liquibase.

### 5.2. Setting a fixed group name in Delayer

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jdbc.store.JdbcMessageStore;

@Configuration
public class RestartAwareDelayFlow {

    public static final String DELAY_GROUP =
            "billing.reminders.delay.v1";

    @Bean
    public IntegrationFlow reminderDelayFlow(
            @Qualifier("restartDelayedStore") JdbcMessageStore store) {

        return IntegrationFlow.from("reminder.in")
                .delay(spec -> spec
                        .messageGroupId(DELAY_GROUP)
                        .messageStore(store)
                        .defaultDelay(60_000L)
                        .delayExpression("headers['delayMs']"))
                .channel("reminder.ready")
                .get();
    }
}
~~~

In the example, the default value is one minute. The `delayMs` header lets each message set an individual delay; if the header is absent, the expression returns `null` and Delayer uses `defaultDelay`. Numeric durations are interpreted as **milliseconds**. To send into the flow:

~~~java
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public boolean scheduleReminder(MessageChannel input) {
    return input.send(MessageBuilder.withPayload("order-501")
            .setHeader("eventId", "reminder:order-501:payment:v1")
            .setHeader("correlationId", "order-501")
            .setHeader("delayMs", 120_000L)
            .build());
}
~~~

The `input` parameter must receive the `reminder.in` bean. With a positive delay, a successful send means Delayer has accepted and processed the scheduling step under the current context; it **does not prove** the reminder was delivered to the customer or the business transaction completed.

**Note about the example:** the default `QueueChannel` at the output is not automatically durable across restarts. If you need guarantees even for messages *already released but not yet picked up by the consumer*, design persistence/handoff for the **output** or consumer accordingly, such as a broker or outbox. Storage in Delayer only covers messages still **in the waiting phase**.

## 6. Restart before the deadline

Suppose:

| Time | Activity |
| --- | --- |
| 09:00 | Delayer A receives message, 30-minute delay, and saves to JDBC store |
| 09:10 | A stops for an upgrade, message not yet due |
| 09:12 | Delayer B starts with the same database and `messageGroupId` |
| 09:30 | Original deadline arrives |
| 09:30:00.xxx | Message can be released when the scheduler executes |

Points to verify:

1. The message was **committed to the DB** before A stopped. If the write transaction was not committed, data cannot be assumed to exist.
2. B has the same group ID and compatible serializer, so it finds the pending message.
3. B restores the schedule from stored data. If numeric delays are processed properly from the original timestamp, the message does not wait an extra 30 minutes from when B started.
4. The consumer receives the exact `eventId`. Do not use the message UUID as the sole proof, since a logical event may be recreated during processing.
5. After processing, the group state no longer contains that pending message according to the semantics of the configured store/transaction.

Verification requires more than checking a single `"application started"` log line. Observe **actual output**, pending data in the store, and event traces.

## 7. Restart after the deadline

If A receives a message at 09:00, sets deadline 09:30, then stops from 09:10 to 10:00, when B starts the message is already **overdue**:

~~~mermaid
flowchart TD
    A[Startup B at 10:00] --> B[Read pending messages]
    B --> C{Has deadline passed?}
    C -->|No| D[Schedule for remaining duration]
    C -->|Yes| E[Eligible for immediate release after recovery]
    D --> F[Release downstream]
    E --> F
    F --> G{Does order still need reminder?}
    G -->|Yes| H[Send reminder]
    G -->|No| I[Discard with logging]
~~~

For reminders, an overdue message should not necessarily trigger an immediate side effect. The customer may have paid while the system was down, or a promotion's expiration may have passed. Place a **Filter or Service Activator after Delayer** to read the latest business state, then decide whether to send, skip, or route to a manual handling branch.

Example business logic after release time:

~~~java
// Illustrates business logic, not complete DB integration code.
public void afterRelease(String orderId, String eventId) {
    if (paymentRepository.isAlreadyPaid(orderId)) {
        auditService.recordSkipped(eventId, "ORDER_ALREADY_PAID");
        return;
    }
    reminderService.send(eventId, orderId);
}
~~~

Order state and sending actions may run concurrently with other processes. In a real application, you need idempotency, transaction/outbox, or a business contract to avoid races when payment and reminder release occur concurrently.

## 8. Failure windows during shutdown and restart

Failures can happen at multiple points:

~~~mermaid
flowchart LR
    A[Producer] --> B[Accept into Delayer]
    B --> C[Commit pending message]
    C --> D[Schedule]
    D --> E[Release]
    E --> F[Consumer causes side effect]
    F --> G[Mark completed]
~~~

| Failure point | Risk | Handling / verification approach |
| --- | --- | --- |
| Before writing/committing pending message | Message is not in persistent store | Producer retry/outbox and semantically accurate receipt confirmation |
| Committed but schedule registration incomplete | Message is in DB without a scheduled task | Startup recovery/reschedule must locate pending messages |
| After schedule registration, before deadline | Scheduler lost with old process | Schedule must be restored from persistent store |
| While releasing to output channel | Transaction may roll back or handler may retry | Test downstream failures, retry policy, and error channel |
| After consumer causes side effect but before ack | May be processed again after retry/recovery | Idempotent consumer, inbox/outbox, stable `eventId` key |
| After release to RAM queue, before consumer polls | Message left Delayer but output is not durable | Design durable downstream handoff when needed |

`JdbcMessageStore` helps store pending messages, but a JDBC transaction **cannot roll back** a sent email or a succeeded HTTP request. Avoid concluding "having a database means exactly-once".

### Designing an idempotent consumer

~~~java
// Pseudocode: claim must be atomic on a durable store.
void handleReminder(String eventId, String orderId) {
    if (!idempotencyStore.tryClaim(eventId)) {
        return;
    }

    if (orderRepository.isUnpaid(orderId)) {
        reminderClient.sendWithIdempotencyKey(eventId, orderId);
    }

    idempotencyStore.markCompleted(eventId);
}
~~~

This is **pseudocode** and does not handle all production failures. If the process dies after `tryClaim` but before `markCompleted`, the event could get stuck or side effects could repeat. A complete design needs `PROCESSING/COMPLETED` states, leases, retries, transactions, and idempotency support at the target service whenever possible.

## 9. Safe restart procedure during deployment

A simple runbook for systems with Delayer and critical pending messages:

1. **Pre-deploy check:** verify the database and schema are healthy; check backlog by `messageGroupId`, age of pending messages, and recent errors. Ensure the new version can still read payloads/headers saved by the old version.
2. **Determine schedule ownership:** with multiple instances, clearly identify which instance is allowed to reschedule/release. If distributed coordination is unproven, run with only a single owner at a time.
3. **Controlled intake stop:** depending on architecture, stop producers or pause flow inputs to limit incoming messages during cutover.
4. **Stop the old version:** allow it to finish or record in-flight tasks per application rules; do not assume shutdown will wait for hours-long deadlines.
5. **Start the new version:** use the same group ID and persistent database; check migrations, serializers, and `TaskScheduler` health.
6. **Verify recovery:** compare pending count, overdue messages, releases, and error logs. For overdue messages, enforce business policy before producing side effects.
7. **Reopen intake:** after confirming the flow restores schedules and consumers are healthy, monitor backlog until it returns to normal levels.

This is a reference procedure; pausing intake and transferring ownership depend on the application's operational capabilities. If using a rolling deployment where versions A and B run simultaneously, check the risk of both releasing the same message. Sharing a database and `messageGroupId` **does not automatically provide single-delivery schedule coordination**.

### Changing group ID is a data change

When upgrading from `billing.reminders.delay.v1` to `...v2`, old messages still carry the old group key. Have a plan: let the old group drain completely, actively migrate data/schedules through a controlled process, or maintain a compatible flow dedicated to the old group. Never change the group ID string to a random build number on every deploy.

## 10. Testing real restarts with two ApplicationContexts

A test using only `Thread.sleep(3000)` in one context proves delay works, **not restart recovery**. You must create two separate application lifecycles using **the same persistent database**.

### Test procedure

1. Initialize a test database (PostgreSQL/Testcontainers or file-backed H2) with the JDBC Message Store schema.
2. Create `ApplicationContext A` with the configuration from section 5, send a message with `eventId=restart-test-001` and a sufficiently long delay, e.g., 15 seconds.
3. Wait for the store write to complete, then verify the message belongs to `billing.reminders.delay.v1`.
4. **Completely close context A before the deadline.** Verify A's scheduler has stopped.
5. Create `ApplicationContext B` with the same database, group ID, and message serialization configuration.
6. Wait past the original deadline, receive the message from B's `reminder.ready` output.
7. Verify `eventId` and payload match, and release time is not earlier than the original deadline.
8. Re-read the message group to see if anything remains pending and check business processing results.

A test harness snippet describing how to open/close two contexts, assuming `dataSourceForSameDatabase()` provides connections to **the same persistent database** throughout the test:

~~~java
// Integration pseudocode: DataSource/schema config and time management
// must be implemented separately in an actual test.
var contextA = startContext(dataSourceForSameDatabase());

try {
    MessageChannel input = contextA.getBean(
            "reminder.in", MessageChannel.class);
    input.send(MessageBuilder.withPayload("order-501")
            .setHeader("eventId", "restart-test-001")
            .setHeader("delayMs", 15_000L)
            .build());

    assertPendingInStore(contextA, "billing.reminders.delay.v1", 1);
} finally {
    contextA.close(); // Close before release deadline.
}

var contextB = startContext(dataSourceForSameDatabase());
try {
    PollableChannel output = contextB.getBean(
            "reminder.ready", PollableChannel.class);
    Message<?> restored = output.receive(20_000);
    assertNotNull(restored);
    assertEquals("restart-test-001",
            restored.getHeaders().get("eventId"));
} finally {
    contextB.close();
}
~~~

The snippet above is **pseudocode** showing the test sequence, not a standalone JUnit class; you must define `startContext`, wait helpers for committed data, schema setup, assertions, and timing control. In real tests, consider controllable clocks/schedulers to reduce flakiness, and verify context B uses a database outside context A's lifecycle.

### Key test matrix

| Test case | Setup | Criteria to prove |
| --- | --- | --- |
| Early restart | Stop A while still waiting | B releases according to original deadline |
| Late restart | Stop past deadline | Message handled per overdue policy |
| Non-persistent message store | Use RAM store then stop JVM | Clearly observe lack of recovery |
| DB failure on write | Simulate connection loss | No false durable acknowledgment if uncommitted |
| DB failure on startup | Store temporarily unreachable | Error/alert raised, backlog not silently dropped |
| Header/payload fails deserialization | Deploy incompatible new version | Failure detected and handled cleanly |
| Message released, consumer fails | Make consumer throw exception | Retry/error channel and transaction match design |
| Two instances start together | Same store and group ID | Evaluate races and idempotency effectiveness |
| Group ID changed | Run B with different group | Identify orphaned messages and migration process |

**Note:** Testcontainers is allowed, but the database container must be kept alive across both context A and B. An H2 database like `jdbc:h2:mem:...` does not prove data survives shutting down **the entire JVM**.

## 11. Observing recovery and release

A system with periodic restarts needs to distinguish messages that are **waiting**, **overdue**, **released**, and **business-completed**.

| Metric | Interpretation |
| --- | --- |
| `pendingCount` | Number of messages waiting in the group at read time |
| `oldestPendingAge` | Age of the oldest pending message |
| `overdueCount` | Number of pending messages whose deadline has passed |
| `recoveryDuration` | Time from startup until required schedules are restored |
| `releaseLagMs` | Lag between actual release time and deadline |
| `retryCount` | Number of retries under error-handling mechanisms |
| `businessOutcome` | Business outcome: succeeded, skipped, or failed |

Metrics such as `overdueCount` and `releaseLagMs` require the application to measure/record timestamps appropriately; do not assume all fields are automatically exported by Spring Integration.

Structured log example:

~~~text
flow=paymentReminderFlow
delayGroup=billing.reminders.delay.v1
eventId=reminder:order-501:payment:v1
correlationId=order-501
receivedAt=2026-11-21T09:00:00Z
dueAt=2026-11-21T09:30:00Z
recoveryAt=2026-11-21T09:12:00Z
releasedAt=2026-11-21T09:30:00.650Z
releaseLagMs=650
outcome=RELEASED
~~~

This is an illustrative log added explicitly by the application, not default logging. Use `Instant`/UTC for absolute timestamps in multi-machine deployments and propagate `eventId` across Filters, Routers, and error channels to correlate steps.

You can check the number of waiting messages via `MessageGroupStore`:

~~~java
int count = messageGroupStore
        .getMessageGroup("billing.reminders.delay.v1")
        .size();
~~~

`count` is only a pending snapshot in the group, not an indication that all consumer side effects have succeeded. A message may have left Delayer while still sitting in a downstream queue/broker or undergoing retry.

### When errors appear after restart

| Symptom | What to check first |
| --- | --- |
| Pending messages missing | Same DB/schema? Did group ID change? Was data committed? |
| Messages in DB but not releasing | Did Delayer initialize? Did recovery/rescheduling run? Any scheduler or log errors? |
| Messages released very late | Downtime, overloaded scheduler, slow DB, large backlog |
| Errors when reading messages back | Incompatible serializer, payload package/class, or headers |
| Two consumers process the same event | Retry or two competing instances; check `eventId`/idempotency |
| Gateway times out | Reply arrived after caller's wait limit; consider async contract |
| Reminder sent to wrong recipient | Consumer did not re-read business state at release time |

Do not manually delete messages in a persistent store just because you see a backlog. Determine whether tasks are still running, transactions are unfinished, and side effects have already occurred.

## 12. Distinguishing restart recovery from retry

**Restart recovery** answers: "Will a message that wasn't due in the previous run be found and released after the application starts?"

**Retry** answers: "When a release/processing attempt fails, should it be retried and how many times?"

Both mechanisms can appear together. Delayer has `maxAttempts`, `retryDelay`, and `delayedMessageErrorChannel` options for release failures:

~~~java
.delay(spec -> spec
        .messageGroupId("billing.reminders.delay.v1")
        .messageStore(store)
        .defaultDelay(60_000L)
        .maxAttempts(3)
        .retryDelay(1_000L)
        .delayedMessageErrorChannel("reminder.delay.errors"))
~~~

This snippet illustrates **an alternative Delayer configuration block**, not a full standalone runnable flow. You must declare the `reminder.delay.errors` channel and an error flow receiving `ErrorMessage`, recording logs/metrics, classifying errors, and applying an appropriate dead-letter/quarantine policy.

Release errors and downstream side-effect errors can carry different meanings. After a failure, a message may be retried, remain in the store, or require manual rescheduling depending on transactions and handling mechanisms. Test consumer exceptions and process shutdowns at each stage before defining production recovery policies.

## 13. When should you use a Delayer with recovery?

Suitable when you need to delay **individual messages** with relative or absolute deadlines, the application may redeploy while waiting, and the business can handle controlled late releases.

For long-lived schedules needing frequent edits/cancellations, complex cron schedules, or massive distributed scale, consider a business scheduler, workflow engine, or broker supporting delayed delivery. Delayer does not automatically replace a rate limiter: many messages sharing a deadline may release in a burst after restart and create a downstream load spike.

The final design must protect **pending messages in Delayer**, **messages handed off downstream**, and **business side effects**. Persistence, recovery, error handling, observability, and idempotency must all be verified together.

## 14. Practice exercises and self-check questions

1. Use `JdbcMessageStore` to persist a 20-second delayed message; restart the application after 5 seconds and measure the deadline after restart.
2. Stop the application past the release deadline. Use a Filter after Delayer to skip reminders for already-paid orders.
3. Intentionally change `messageGroupId` between two versions, observe the orphaned backlog, and propose a migration plan.
4. Have the producer resend the same `eventId` under two different Spring Message UUIDs; test the idempotent consumer.
5. Configure a consumer to throw an exception after the message becomes due; observe retries, the error channel, and storage state.
6. Start two instances sharing the same JDBC store; test races when due simultaneously and verify the effectiveness of the schedule ownership strategy.
7. Trigger a shutdown right after a message is released to an in-memory `QueueChannel` before the consumer polls it; explain why persistence in Delayer alone is insufficient.
8. Measure `pendingCount`, `overdueCount`, and `releaseLagMs` after a simulated downtime and define alert thresholds based on SLA.

**Self-check questions:** Why shouldn't a restart recalculate the entire delay from startup time? What must be kept stable to read the right group? How does restarting after a deadline differ from restarting before a deadline? How do `eventId` and `messageGroupId` have different responsibilities? Why can't a JDBC transaction automatically recall a sent email? What evidence is sufficient to say recovery works rather than just seeing the service started?

## References

- [Spring Integration Reference — Delayer](https://docs.spring.io/spring-integration/reference/delayer.html): how Delayer delays messages, message stores, and schedule recovery.
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html): options for in-memory or out-of-process message storage.
- [Spring Integration Reference — JDBC Support](https://docs.spring.io/spring-integration/reference/jdbc.html): JDBC support configuration and message store schema.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): error channels and exceptions in asynchronous flows.
- [Spring Integration Reference — Idempotent Receiver](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): principles for protecting consumers against duplicate processing.
