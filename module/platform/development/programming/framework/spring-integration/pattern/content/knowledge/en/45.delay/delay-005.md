# Persistence of delayed messages in Spring Integration

## 1. Why does Delayer need persistent storage?

**Delayer** is an Enterprise Integration Pattern (EIP) that delays forwarding a message to the next step. After receiving a message, it computes the release time, holds the pending message, and uses a `TaskScheduler` to release the message when due. With a positive delay, the producer does not have to keep a thread waiting for the entire duration.

What happens if the application stops while a message is still waiting? With an in-memory store, the message may disappear along with the process. When using a **persistent message store**, the message is saved outside the process so Delayer can locate it and reschedule its release after the application starts.

For example, in an e-commerce system:

- At 09:00, receive event `eventId=reminder-501` that needs to wait 30 minutes.
- At 09:10, the application stops to deploy a new version.
- At 09:12, the application starts back up and finds the pending message in the database.
- Under normal operation, the message becomes eligible for release around 09:30; if it only restarts after 09:30, the overdue message may be released during recovery.

In the **SPRING_INTEGRATION_PATTERN** module, persistence helps design loosely coupled message flows when combining Delayer with Filter, Transformer, Router, Gateway, retry, error channel, correlation, and business branches. The system must clearly distinguish **received to wait**, **released to downstream**, and **business completed**.

> Persistence helps recover pending messages across restarts. It does not automatically guarantee exactly-once delivery or millisecond-exact release timing, nor does it record business outcomes on behalf of the consumer.

## 2. SimpleMessageStore and JdbcMessageStore

| Criterion | `SimpleMessageStore` | `JdbcMessageStore` |
| --- | --- | --- |
| Storage location | JVM memory | Database tables |
| Process shutdown | Pending messages may be lost | Committed messages remain intact |
| Setup | Easy, suitable for demos/tests | Requires `DataSource`, schema, access permissions |
| Overhead | Low | Has I/O, locks, transactions, database latency |
| Restart | Does not recover RAM-only data | Can reschedule stored messages |
| Risks | Message loss on stop | Database errors, serialization, schema, concurrency |
| Use cases | Messages that can be regenerated | Critical reminders and waiting tasks |

Typically, Delayer uses `SimpleMessageStore` when no custom store is configured. A long delay value **does not automatically turn an in-memory store into a persistent store**. If redelivery after restart is acceptable and messages must be preserved, configure an appropriate persistent `MessageGroupStore`.

## 3. Storage structure and identity

~~~mermaid
flowchart LR
    P[Producer] --> I[Input Channel]
    I --> D["DelayHandler<br/>messageGroupId=reminders.delay.v1"]
    D --> S[("JdbcMessageStore")]
    D --> T[TaskScheduler]
    S -. "Read pending messages" .-> D
    T --> R[Release when due]
    D --> R
    R --> F{Filter: order still unpaid?}
    F -->|Yes| C[Consumer]
    F -->|No| X[Discard with logging]
~~~

`DelayHandler` manages pending messages under a **message group** in `MessageGroupStore`. `TaskScheduler` is responsible for invoking the task when due. With persistence, data in the store can be used to restore the schedule if the previous process stopped.

| Identifier | Example | Role |
| --- | --- | --- |
| `messageGroupId` | `billing.payment-reminders.delay.v1` | Key for Delayer's waiting group in the store |
| `MessageHeaders.ID` | UUID | Identifies a Spring message instance |
| `correlationId` | `order-501` | Tracks messages of the same order/workflow |
| `eventId` | `reminder:order-501:v1` | Identifies the logical event for deduplication |

Two messages from two different orders can sit in the same `messageGroupId`. This group is **not** an Aggregator correlation group, nor should it be used as an individual event's deduplication key.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant D as DelayHandler
    participant S as JDBC Message Store
    participant T as TaskScheduler
    participant C as Consumer
    P->>D: eventId=reminder-501, delay=30 minutes
    D->>S: Save message to stable group
    D->>T: Schedule release
    D-->>P: Return control
    Note over D,T: Application may restart
    T->>D: Due
    D->>S: Read pending message
    D->>C: Release message to downstream
~~~

This diagram shows the logical flow. Details on when messages are retrieved/removed from the store and rollbacks depend on transactions, channels, error handling, and actual configuration; do not infer exactly-once guarantees from the diagram.

## 4. Configuring JdbcMessageStore in Spring Integration Java DSL

A Spring Boot application using JDBC Message Store needs:

1. `spring-boot-starter-integration` for Spring Integration flows and endpoints.
2. `spring-integration-jdbc` for `JdbcMessageStore`.
3. `spring-boot-starter-jdbc` or equivalent JDBC configuration, along with the database's JDBC driver.
4. A connectable `DataSource`; JDBC Message Store tables initialized for the exact Spring Integration/database version.

Do not guess table structures. Use the SQL schema provided by Spring Integration JDBC, applied via Flyway, Liquibase, or your current DB management workflow.

### 4.1. Creating the store and channels

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
public class PersistentReminderChannels {

    @Bean("delayedMessageStore")
    public JdbcMessageStore delayedMessageStore(DataSource dataSource) {
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

Here `JdbcMessageStore` receives the application-configured `DataSource`. The schema must be ready **before Delayer reads/writes messages**. `QueueChannel` is only used to observe release output in this example: it does not guarantee released data survives a restart, since the output channel itself still uses memory.

### 4.2. Connecting Delayer to the store

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jdbc.store.JdbcMessageStore;

@Configuration
public class PersistentReminderFlow {

    @Bean
    public IntegrationFlow paymentReminderFlow(
            @Qualifier("delayedMessageStore") JdbcMessageStore store) {

        return IntegrationFlow.from("reminder.in")
                .delay(delayer -> delayer
                        .messageGroupId("billing.payment-reminders.delay.v1")
                        .messageStore(store)
                        .defaultDelay(30 * 60 * 1_000L)
                        .delayExpression("headers['delayMs']"))
                .channel("reminder.ready")
                .get();
    }
}
~~~

`defaultDelay(30 * 60 * 1_000L)` represents 30 minutes. When the `delayMs` header is valid, the numeric value is interpreted in milliseconds and takes precedence; if the header is missing, the default is used.

The two most important settings:

- `messageStore(store)` selects persistent storage instead of the in-memory default.
- `messageGroupId("billing.payment-reminders.delay.v1")` sets a **stable** key so a new process finds Delayer's message group again.

If two **logically different** Delayers share the same database, they need distinct group IDs. If you change a group ID across a deploy without migrating or draining old data, pending messages may be left orphaned in the old group.

### 4.3. Sending messages with business identity

~~~java
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public boolean scheduleReminder(MessageChannel reminderInput) {
    return reminderInput.send(
            MessageBuilder.withPayload("order-501")
                    .setHeader("eventId", "reminder:order-501:v1")
                    .setHeader("correlationId", "order-501")
                    .setHeader("delayMs", 120_000L)
                    .build());
}
~~~

The example requires passing the `reminder.in` bean to `reminderInput`. Simple `String` and `Long` values reduce serialization risks. `eventId` must remain stable even if the same event is resent as a new `Message` with a different UUID.

### 4.4. Database configuration

PostgreSQL connection example:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/integration
spring.datasource.username=integration_app
spring.datasource.password=provided-by-secret-management
~~~

This is an illustrative configuration containing no real credentials. In practice, fetch username/password from a secret manager or deployment environment. Configuring `DataSource` **does not replace** creating the JDBC Message Store schema.

If using an H2 URL `jdbc:h2:mem:...`, data lives in database memory and does not survive after the process stops completely. To test persistence across restarts, keep the database outside the process lifecycle or use an appropriate disk-backed database.

## 5. Recovering delayed messages after restart

When Delayer starts up with a persistent store, messages remaining in its group can be read back and **rescheduled**. If the deadline passed while the application was down, the message may be released once recovery completes; the system cannot release at a timestamp already in the past.

~~~mermaid
sequenceDiagram
    participant A as Application version A
    participant DB as JDBC Message Store
    participant B as Application version B
    participant C as Consumer
    A->>DB: Write reminder-501 before shutdown
    Note over A: Stop at 09:10
    Note over DB: Committed message still persists
    B->>DB: Start at 09:12; read stable group ID
    DB-->>B: Pending message
    B->>B: Restore schedule until due
    Note over B: At 09:30
    B->>C: Release reminder-501
~~~

Recovery behavior preserves the meaning of the wait duration rather than recalculating "another 30 minutes" from each restart. Spring Integration supports rescheduling delayed messages in the store; when using in production, verify the behavior of your deployed version and the stored timestamp data.

| Scenario | Example | What needs to be handled |
| --- | --- | --- |
| Restart before deadline | Received 09:00, stopped 09:10, restarted 09:12, due 09:30 | Message continues waiting until due |
| Restart after deadline | Received 09:00, stopped 09:10, restarted 10:00, due 09:30 | Message is overdue, may be released immediately after recovery |
| Multiple restarts | Repeated stop/start before deadline | No loss of committed messages, no duplicated business side effects |

For reminders, a due message may become **no longer necessary** if the customer has already paid. Add a Filter or service check for status after Delayer, then decide whether to send the reminder or skip it. Persistence preserves processing intent; it does not "freeze" business state.

## 6. Three levels of guarantees to distinguish

~~~mermaid
flowchart LR
    A[Producer] --> B[Committed store]
    B --> C[Scheduler due]
    C --> D[Message released]
    D --> E[Consumer produces side effect]
    E --> F[Result confirmed]
~~~

A durable system must distinguish:

1. **Stored:** the message remains in the store after commit and restart.
2. **Released:** Delayer sends the message to the output channel.
3. **Business completed:** consumer/email/API/database confirms the result.

| When does the error occur? | Risk | Mitigation |
| --- | --- | --- |
| Before committing the stored message | Message is not yet durable | Controlled producer retry, outbox, confirmation |
| After commit but before schedule runs | Still in DB but not yet released | Startup rescheduling, backlog monitoring |
| While forwarding message downstream | Retry, rollback, or loss depending on configuration | Tested transactions and error channel |
| After consumer sent email but before recording completion | Same email might be sent again | Idempotent consumer, inbox/outbox, idempotency key |

### Transactions do not span every system

`JdbcMessageStore` can participate in JDBC transactions when properly configured with a `DataSource` and transaction manager. However, emails, REST APIs, or external brokers outside the database generally **do not automatically participate** in JDBC transactions.

Suppose an email succeeds and then the application crashes: rolling back the JDBC transaction cannot recall the email. Upon recovery/retry, the same `eventId` may pass through the consumer once more.

Therefore, clarify transaction boundaries on both the inbound and release paths, and use idempotency for external side effects. A persistent store is a **message storage component**, not a complete exactly-once solution.

## 7. Serialization and deploying new versions

Delayed messages may sit in the database during application upgrades. When the new version recovers old messages, verify:

- Can payloads be serialized/deserialized by the active store configuration?
- Do previously written Java classes still exist, or is there a compatible migration path?
- Do headers contain references to JVM objects such as temporary reply channels, connections, or threads?
- Does the message carry stale business data that needs refreshing when processed?

A lightweight and relatively maintainable example:

~~~java
MessageBuilder.withPayload("order-501")
        .setHeader("eventId", "reminder:order-501:v1")
        .setHeader("correlationId", "order-501")
        .build();
~~~

The consumer reloads order state by key `order-501` at release time. If complex DTOs are required, design explicit schema/versioning, verify serializers, and test real upgrades against messages stored by older versions.

| Data | Risk |
| --- | --- |
| `replyChannel` or `errorChannel` pointing to a JVM object | Reference may be invalid after restart |
| Java DTO package/name/shape changes | Cannot deserialize old messages |
| Header contains non-serializable object | Store write or recovery fails |
| Order status snapshot | Becomes stale after long waits |
| Timestamp string without time zone | Deadline miscalculated when switching environments |

Synchronous gateways may time out before a message is released. For tasks spanning across restarts, confirm **receipt** first and return results asynchronously based on `eventId` or a callback/broker with a durable identifier.

## 8. Testing persistence across restarts

A test waiting only 3 seconds inside the same JVM proves Delayer releases over time, **not that data survives a restart**. A persistence test needs two separate application contexts/processes and **a database that retains data**.

Testing procedure:

1. Prepare a test database with the version-matched JDBC Message Store schema.
2. Start `ApplicationContext A` using `messageGroupId=billing.payment-reminders.delay.v1`.
3. Send message `eventId=restart-test-001` with a delay longer than the test execution time, e.g., 30 seconds.
4. Verify the message was written/committed to the corresponding group.
5. Completely close context A **before the deadline**, ensuring the old scheduler is no longer running.
6. Keep the database; start context B with the same group ID, serializer, and appropriate channels/consumers.
7. Wait past the deadline, verify context B releases the exact `eventId`.
8. Verify the message is no longer waiting in the group and the business side-effect state matches policy.
9. Repeat with a restart **after the deadline**, downstream errors, and multiple messages becoming due simultaneously.

If using Testcontainers, the database container must remain intact between A and B. An in-memory H2 `mem` database inside the same context does not prove the application survives a full JVM shutdown.

You can inspect a snapshot of the waiting group using `MessageGroupStore`:

~~~java
import org.springframework.integration.store.MessageGroupStore;

int pending = messageGroupStore
        .getMessageGroup("billing.payment-reminders.delay.v1")
        .size();

System.out.println("Pending delayed messages: " + pending);
~~~

`pending` only indicates the number of messages in the group at **read time**, not that the consumer has finished processing. In CI tests, avoid races when the scheduler is close to the deadline.

### Failure-mode test matrix

| Case | Condition | What to verify |
| --- | --- | --- |
| Early restart | Not yet due, message committed | New context continues waiting then releases |
| Late restart | Deadline passed during downtime | Overdue handling matches policy |
| Store write failure | DB out of connections or rejects write | Error is detected, no false durable acknowledgment |
| Recovery failure | DB unavailable at startup | Alert raised, backlog not silently dropped |
| Downstream failure | Consumer throws exception | Retry, error channel, and transactions behave per design |
| DTO change | Message saved by older version | Readable or compatibility error detected |
| Two instances | Sharing store and group | Contention controlled, side effects not duplicated |
| Producer resends `eventId` | Two messages with different UUIDs | Consumer processes idempotently |

## 9. Retry and error channel when a message becomes due

With a positive delay, the producer may leave the endpoint before downstream actually processes the message. Errors during release typically cannot be returned directly to the original `send()` call.

Delayer supports release error-handling options:

~~~java
.delay(delayer -> delayer
        .messageGroupId("billing.payment-reminders.delay.v1")
        .messageStore(store)
        .defaultDelay(60_000L)
        .maxAttempts(3)
        .retryDelay(1_000L)
        .delayedMessageErrorChannel("reminder.delay.errors"))
~~~

This snippet replaces `.delay(...)`, rather than being a standalone flow. When using it, declare the `reminder.delay.errors` channel and a flow to handle `ErrorMessage`, logs/metrics, alerts, and dead-letter/quarantine if needed.

An error when sending an email **after the email was actually sent** can cause a retry to send a duplicate. Classify retryable errors, tune `maxAttempts`/`retryDelay`, and use an idempotency key on the receiving service.

Especially with transactions, once retries are exhausted, a message may no longer have an automatic schedule even while data remains in the store. Test behavior under transaction rollback, reschedule, or restart. Do not manually delete unprocessed messages without knowing the status of side effects.

## 10. Idempotency at the consumer

`MessageHeaders.ID` is a Spring-generated message ID; a resent event may receive a different UUID. Therefore, use a stable business key:

~~~java
void handleReminder(String eventId, String orderId) {
    // Pseudocode: claim needs to be atomic on a durable store.
    if (!idempotencyStore.tryClaim(eventId)) {
        return;
    }

    if (orderRepository.isUnpaid(orderId)) {
        reminderClient.send(eventId, orderId);
    }

    idempotencyStore.markCompleted(eventId);
}
~~~

**This is design pseudocode, not a complete production implementation.** If the process crashes after `tryClaim` but before or after the API call, you need leases/timeouts, `PROCESSING`/`COMPLETED` states, retries, transactions, and downstream idempotency to avoid stuck messages or repeated side effects.

Do not dedupe by `messageGroupId`: a Delayer can hold thousands of distinct events in the same group. Also do not default to deduping by `correlationId`: one order can legitimately have multiple distinct reminders.

## 11. Multi-instance deployments and database sharing

Multiple instances sharing `JdbcMessageStore` **do not automatically prove each message is released only once**. Instances may jointly detect pending messages and schedule them, contend at release time, or reprocess after restarts.

| Architecture | Requirement |
| --- | --- |
| Single instance owns Delayer | Leader/owner mechanism, health check, and failover |
| Multiple instances run the same logical Delayer | Tested locking, transactions, and duplicate detection |
| Multiple independent Delayers share a store | Distinct group IDs, no stealing each other's messages |
| Changing group ID on deploy | Drain/migrate old data before retiring previous ID |

Consider leader election, distributed locks, partitioning, or a scheduler/broker supporting delayed delivery if distributed coordination is complex. `JdbcMessageStore` primarily solves **message storage**, whereas release schedule ownership is an architectural decision.

Do not base group IDs on auto-generated build numbers if you still need to recover backlog from previous versions. With legacy groups still holding data, changing the ID without migration can prevent the new application from finding those messages.

## 12. Monitoring, operations, and troubleshooting

Minimum metrics:

| Category | Metric | How to use |
| --- | --- | --- |
| Backlog | `pendingCount`, age of oldest waiting message | Detect store buildup or stopped scheduler |
| Timeliness | `dueAt`, `releasedAt`, `releaseLagMs` | Measure release delay relative to deadline |
| Outcome | `eventId`, `attempt`, `processedAt`, `outcome` | Distinguish released vs. business-completed |

An application log entry can be designed as follows:

~~~text
flow=paymentReminderFlow
delayGroup=billing.payment-reminders.delay.v1
eventId=reminder:order-501:v1
correlationId=order-501
receivedAt=2026-11-21T09:00:00Z
dueAt=2026-11-21T09:30:00Z
releasedAt=2026-11-21T09:30:01.100Z
releaseLagMs=1100
outcome=RELEASED
~~~

This is an illustrative log **explicitly written by the application**, not all fields automatically provided by Spring Integration. Use UTC/`Instant` timestamps to simplify tracking across multiple instances.

| Symptom | Things to check |
| --- | --- |
| Reminders missing after restart | In-memory store, group ID changed, uncommitted, wrong DB connection |
| DB has messages but none released | Scheduler, Delayer startup, recovery/rescheduling, transactions |
| Messages arrive late | Downtime, busy scheduler, slow database |
| Recovery deserialization errors | Incompatible DTO class/schema/headers |
| Reminders sent twice | Retry, two competing instances, upstream resend; check idempotency |
| DB keeps growing without shrinking | Long backlog, prolonged errors, missing retention/cleanup policy |
| Gateway timeout | Reply released after caller stopped waiting |

**Do not directly delete active JDBC Message Store rows** merely because backlog grows. Identify pending messages, in-flight transactions, and business outcomes before performing administrative actions.

## 13. When to choose a Delayer with persistence?

Suitable when you need to delay **individual messages** within a Spring Integration flow, want survival across restarts, and accept controlled release jitter. For example:

- Payment reminders after a delay, re-checking the latest status upon release.
- Temporarily holding messages before forwarding to partners per business policy.
- Releasing a notification at a future `Date` timestamp.

Consider a business scheduler, workflow engine, or broker with delayed delivery if you have millions of long-lived schedules requiring flexible editing/cancellation, complex recurring schedules, or dedicated distributed orchestration. Delayer also does not replace a rate limiter, as many messages sharing a deadline can simultaneously spike downstream load.

## 14. Practice exercises and self-check questions

1. Configure `JdbcMessageStore` on a test database and prove a 30-second delayed message survives a full application stop.
2. Restart before the deadline and after the deadline. Compare `dueAt` with `releasedAt`, and verify policy for overdue messages.
3. Configure two independent Delayers using the same store but different `messageGroupId` values; observe each group's backlog.
4. Change the group ID in a test version while data remains, then propose a migration plan that does not abandon messages.
5. Write a payload in version A then change the class in version B. Test deserialization errors and propose schema versioning.
6. Simulate a consumer calling an API successfully but timing out when receiving the response. Explain why a JDBC transaction does not prevent duplicates.
7. Run two instances sharing a group and database, verify behavior during simultaneous restarts, and design idempotency by `eventId`.
8. Build `pendingCount`, `releaseLagMs`, and retry count metrics, then set alerts when backlog exceeds SLA.

**Self-check:** How does `MessageGroupStore` differ from `TaskScheduler`? Why must the group ID be stable? When is a message considered durably stored? Why can't `send() == true` be treated as business completion? Why must restart tests preserve the database across two processes? What should be checked before sending an overdue reminder?

## References

- [Spring Integration Reference — Delayer](https://docs.spring.io/spring-integration/reference/delayer.html): `messageGroupId`, delayed messages, persistence, and schedule recovery.
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html): `MessageGroupStore` and persistent stores.
- [Spring Integration Reference — JDBC Support](https://docs.spring.io/spring-integration/reference/jdbc.html): JDBC integration and storage schema.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): error channels and asynchronous error handling.
- [Spring Integration Reference — Idempotent Receiver](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): strategies for handling redelivered messages.
