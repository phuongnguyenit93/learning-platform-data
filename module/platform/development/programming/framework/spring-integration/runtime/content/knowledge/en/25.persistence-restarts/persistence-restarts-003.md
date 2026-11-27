# Recovering Delayed Messages and Pending Groups After Restarts

In Spring Integration, a message that has been received **is not necessarily finished being processed**. A delayer may hold a message to emit at a future time; an aggregator or resequencer may hold multiple messages within the same correlation group until release conditions are met. If the application stops midway, the key questions are: **which messages remain stored, which processing schedules are recreated, and which steps might execute again?**

This lesson belongs to the **Persistence and Restarts** chapter of the **SPRING_INTEGRATION_RUNTIME** module. We will practice recovering delayed messages and pending groups across the lifecycle of `IntegrationFlow`, channels, consumer endpoints, pollers, and executors; while examining transactions, retries, message stores, error flows, correlation, performance, and runtime state diagnostics.

> **Principle:** A persistent `MessageStore` preserves **message/group data**, but it does not automatically guarantee that every schedule, transaction, or side effect is restored as-is. You must design the Delayer's **reschedule** path and the Aggregator's **release/expire** path separately.

## 1. Two Types of State to Recover

| Aspect | Delayed Message | Pending Group of Aggregator/Resequencer |
|---|---|---|
| Waiting data | Individual messages with a future emit timestamp | Fragments sharing a correlation key and group metadata |
| Managing component | `DelayHandler` + `TaskScheduler` | `AbstractCorrelatingMessageHandler` + `MessageGroupStore` |
| Continuation condition | Delay expires, then sent to output | Group meets `ReleaseStrategy` or is force-completed |
| Can it be durably persisted? | Yes, via a persistent `MessageGroupStore` | Yes, via a persistent `MessageGroupStore` |
| On restart | Delayer reads stored messages and **reschedules** them | Group remains in store; new fragments can continue the group, but old timeout schedules must not be assumed intact |
| Preventing long-term backlog | Retry/recovery and business policy for overdue messages | `expireTimeout`, `expireDuration`, reaper, and partial/discard policies |
| Notable risks | Missing/duplicate emissions in the outage window between store deletion and downstream | Orphaned groups, duplicate releases, mismatched correlation, late-arriving messages |

~~~mermaid
flowchart TD
    A["Message enters flow"] --> B{"Why does it need to wait?"}
    B -->|Wait for time| D["DelayHandler"]
    B -->|Wait for fragments| G["Aggregator / Resequencer"]
    D --> DS[("Persistent delay group")]
    G --> GS[("Persistent correlation groups")]
    DS --> R["Restart: reschedule persisted messages"]
    GS --> P["Restart: accept new fragments / purge orphans"]
    R --> O["Release to downstream"]
    P --> Q["Release / partial / discard"]
~~~

In the diagram, the two stores are drawn separately to reflect **different ownership and lifecycles**. They may share the same database infrastructure, but they should have distinct beans/regions and handling policies.

## 2. What Does a Persistent MessageStore Preserve?

Spring Integration provides `MessageStore` for message data and `MessageGroupStore` for message groups. Some implementations such as `SimpleMessageStore` are purely in-memory; `JdbcMessageStore` uses a database, so it can retain data across restarts when the schema and configuration are appropriate.

Checks to verify before expecting recovery:

1. **Right store:** The delayer/aggregator is actually configured to use the persistent store; using JDBC for another component in the application does not automatically make them persistent.
2. **Committed:** The message or group was written successfully and the storage transaction committed before the process stopped.
3. **Stable identity:** Region, message group ID, correlation strategy, and endpoint identifiers do not change unintentionally across deployments.
4. **Readable data:** Serializers, payload classes, headers, application versions, and database schemas remain compatible.
5. **Active consumer to continue:** Endpoints, schedulers, error flows, and downstream systems are running after the restart.
6. **Reprocessing mechanism:** There must be a reschedule, a new incoming fragment, or a `forceComplete`/purge action; a row sitting in the DB does not mean it will be executed.

**Distinction:** `JdbcMessageStore` for delayer/aggregator messages and groups differs from `JdbcChannelMessageStore` used for persistent queue channels. Each has its own API and retrieval/deletion semantics; you cannot apply an arbitrary cleanup operation to both.

## 3. How Does Delayer Actually Recover Delayed Messages?

`DelayHandler` places delayed messages into a **message group** in a `MessageStore`. Due times are coordinated by a `TaskScheduler`; the sender typically does not have to wait for the delay duration. The `groupId` used by the delayer must remain stable so the new handler can locate old messages after a restart.

On the normal release path, the scheduled task retrieves/removes the message from the store **right before** sending it to the output channel. When using a persistent store:

- When the application context starts, the Delayer reads stored messages and recreates release schedules.
- For delays specified in milliseconds, the re-scheduled release time is based on **when the message originally arrived**, rather than restarting the full delay countdown after restart.
- If the delay is defined by a `Date` value, that date/time is used to reschedule.
- If the message is already overdue by the time of the restart, it is scheduled to fire promptly once the application starts and the scheduler is ready.

~~~mermaid
sequenceDiagram
    participant S as Sender
    participant D as DelayHandler
    participant DB as Persistent MessageStore
    participant T as TaskScheduler
    participant H as Downstream
    S->>D: message M, delay = 60s
    D->>DB: save M into delay group
    D->>T: schedule release
    Note over D,T: After 20s: application stops
    Note over DB: M remains if committed
    Note over D,T: Application restarts after 15s
    D->>DB: query persisted messages
    D->>T: schedule remaining duration
    T->>DB: fetch / remove M when due
    T->>H: send M to downstream
~~~

**Do not treat `TaskScheduler`'s in-memory schedule as durable data.** Recovery relies on messages remaining in the persistent store and the Delayer creating new schedules, not the scheduler preserving `ScheduledFuture` objects across processes.

### Two Easily Confused IDs

| ID | Purpose | Rule Across Restarts |
|---|---|---|
| `DelayHandler.messageGroupId` | Identifies the **group holding pending messages** for a delayer | Keep fixed across deploys; do not rely on auto-generated bean names |
| `MessageHeaders.ID` | ID of a specific message instance | Do not use as a business deduplication key; new/redelivered messages may have different IDs |
| `correlationId` | Links processing steps per flow contract | Preserve if needed for tracking; does not replace the Delayer's `messageGroupId` |
| `businessId`/`idempotencyKey` | Identifies a business action | Must be durable and checked downstream on replay |

A common mistake is letting the framework auto-generate an endpoint name and using that as the group ID. After a deploy, the new name may differ, leaving old messages in the DB while the new Delayer cannot find the group to reschedule them.

## 4. Java DSL Example: Reminder Preserved Across Restarts

The illustrative example uses Java 17+, Spring Integration 6.2+, and Spring JDBC. A database is provided for `JdbcMessageStore`, Spring has a `PlatformTransactionManager` along with a `DataSource`, and the Spring Integration JDBC tables are pre-created using dialect-appropriate scripts. To persist using Java serialization, payloads and retained headers must be serializable, or the application must configure another serializer/converter.

**Step 1 — payload with a stable business identifier:**

~~~java
public record Reminder(
        String reminderId,
        String recipient,
        String content
) implements java.io.Serializable {}
~~~

**Step 2 — declare persistent store, channel, and flow:**

~~~java
@Configuration
@EnableIntegration
public class ReminderFlowConfig {

    @Bean(name = "reminderDelayStore")
    JdbcMessageStore reminderDelayStore(DataSource dataSource) {
        JdbcMessageStore store = new JdbcMessageStore(dataSource);
        store.setRegion("reminders.delay.v1");
        return store;
    }

    @Bean(name = "reminders.input")
    MessageChannel remindersInput() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow reminderFlow(
            @Qualifier("reminderDelayStore") MessageGroupStore delayStore,
            PlatformTransactionManager txManager,
            ReminderDeliveryService service) {
        return IntegrationFlow.from("reminders.input")
            .delay(d -> d
                .messageGroupId("reminders.delay.pending.v1")
                .messageStore(delayStore)
                .defaultDelay(60_000L)
                .transactionalRelease(txManager)
                .maxAttempts(5)
                .retryDelay(1_000L))
            .handle(service, "recordDelivery")
            .get();
    }
}
~~~

Types used in the example: `org.springframework.integration.dsl.IntegrationFlow`, `org.springframework.integration.jdbc.store.JdbcMessageStore`, `org.springframework.integration.store.MessageGroupStore`, `org.springframework.integration.channel.DirectChannel`, `org.springframework.integration.config.EnableIntegration`, `org.springframework.messaging.MessageChannel`, `org.springframework.transaction.PlatformTransactionManager`, `javax.sql.DataSource`, and `org.springframework.beans.factory.annotation.Qualifier`.

`recordDelivery` is illustrated by a service writing to the DB within the same transaction when the Delayer releases:

~~~java
@Service
public class ReminderDeliveryService {
    private final JdbcTemplate jdbc;

    public ReminderDeliveryService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void recordDelivery(Reminder reminder) {
        jdbc.update(
            "INSERT INTO reminder_delivery(reminder_id, recipient) VALUES (?, ?)",
            reminder.reminderId(),
            reminder.recipient());
    }
}
~~~

The example requires a `reminder_delivery` table with `reminder_id` as a unique/primary key. The service only writes to the DB to demonstrate transactions; actually sending emails, SMS, or making HTTP calls **does not automatically roll back** alongside `JdbcMessageStore`. If reliable external notification is needed, write an outbox record inside the transaction and let an independent worker deliver it with idempotency.

**Step 3 — send the reminder:**

~~~java
Message<Reminder> message = MessageBuilder
    .withPayload(new Reminder("REM-42", "user@example.org", "Time to execute"))
    .setHeader("correlationId", "request-42")
    .build();

remindersInput.send(message);
~~~

`MessageBuilder` belongs to `org.springframework.integration.support`. To test restart behavior, send the message, verify the delay record exists and the storage transaction committed, then stop the application **before 60 seconds**. Restart with the same database, region, and `messageGroupId`: the Delayer reads the message, schedules it, and forwards it to `recordDelivery()` at the remaining delay or shortly after startup if already overdue.

**Limitation of the example:** `.transactionalRelease(txManager)` protects fetching the message from the JDBC store and **synchronous** downstream work participating in the same transaction manager. If you insert an `ExecutorChannel` between the Delayer and `recordDelivery()`, the transaction on the scheduled thread does not automatically span execution on another worker thread.

## 5. What Happens If Delayer Release Fails?

Delayer has its own release retry policy:

| Configuration | Meaning |
|---|---|
| `maxAttempts` | Maximum number of attempts to release the message when downstream fails; default 5 |
| `retryDelay` | Additional wait time before the next attempt; default 1 second |
| `transactionalRelease` / delayed advice | Can wrap fetching/removing the message and sending downstream in a single transaction |
| `delayedMessageErrorChannel` | Channel receiving `ErrorMessage` specifically for errors during message release |
| `reschedulePersistedMessages()` | Allows scanning and rescheduling remaining stored messages, e.g. after the scheduler was stopped |

**Without a transaction on release:** The Delayer may already have removed the message from the store before downstream throws an exception. The framework can retry releasing within the live process, but crashing during the window with no durable record creates a message-loss risk.

**When release is wrapped in a transaction on the right resource:** If synchronous downstream throws an exception and the transaction rolls back, the deletion from the persistent store can roll back, keeping the message intact. Once retry attempts are exhausted, it may remain in the store but **will no longer automatically be scheduled** until a restart or a call to `reschedulePersistedMessages()`.

An easily missed detail: if `delayedMessageErrorChannel` is used and the error channel consumer handles the error and **returns normally**, the Delayer may treat the error as handled; with transactional release, the transaction can commit and the message be removed from the store. If you want retries to continue, the error consumer must rethrow the exception per policy. Thus, the error channel is where **recovery is decided**, not inherently a durable dead-letter queue.

~~~mermaid
flowchart TD
    S["Scheduled release task"] --> T{"Has transactional release?"}
    T -->|Yes| R["Read / remove message in TX"]
    T -->|No| N["Remove before sending"]
    R --> D["Send to downstream"]
    N --> D
    D -->|Success| C["Commit / end release"]
    D -->|Error| E["Retry / delayed error flow"]
    E -->|TX rollback| P["Message may remain in store"]
    E -->|Handled| X["Finish per recovery policy"]
    P --> M["Reschedule if attempts exhausted / after restart"]
~~~

Additionally, since Spring Integration 5.3.7, if **saving** the delayed message occurs inside an active transaction, the release schedule is registered in an `afterCommit()` callback to prevent the scheduled task from firing before the record becomes readable. This does not turn downstream side effects into a distributed transaction.

## 6. Recovering Pending MessageGroups of an Aggregator

An aggregator collects messages by **correlation key** and stores them in a `MessageGroupStore`. For example, batch `B-17` requires three fragments, but only two arrived before restart:

~~~text
MessageGroup(B-17):
  fragment A  ✓
  fragment B  ✓
  fragment C  (not yet arrived)
  complete = false
~~~

With a persistent store, the two fragments and metadata can survive the restart. When fragment C arrives at the new application instance, the aggregator uses the same `CorrelationStrategy` and region/store to locate group `B-17`, adds C, and evaluates `ReleaseStrategy`. Once all three parts are present, the group releases normally.

**However, do not assume that a `groupTimeout` set before shutdown will automatically resume at the exact old time.** The in-memory task scheduler is not a durable store. If fragment C never arrives, the group may remain stuck until an appropriate scan/force-completion mechanism runs.

### Distinguishing Three Mechanisms

| Mechanism | When Does It Run? | Best Suited For |
|---|---|---|
| `ReleaseStrategy` | When the handler receives another message or is evaluated during force completion | Groups receiving additional fragments after restart |
| `groupTimeout` | Group timeout schedule while the flow is running; typically reset when a new message arrives | Groups missing fragments during normal runtime operation |
| `expireTimeout` + `expireDuration` | Scans aged groups in the store at startup and periodically | Recovering/handling **orphaned groups** after restart |
| `MessageGroupStoreReaper` | Dedicated task scanning old groups periodically | Centrally managed expiry/cleanup policies |

Force-completion/expiry paths still follow policies for **partial results or discarding**, when groups are removed, and how late fragments are handled. Persistent groups do not mean waiting forever.

## 7. Aggregator Example: Resuming Pending Groups and Handling Orphans

To illustrate another flow, use a **dedicated store** for the aggregator. Do not share the Delayer's `MessageGroupStore` from the previous example, and do not share a single store across multiple correlating endpoints if they have independent expiry callbacks.

~~~java
@Configuration
@EnableIntegration
public class BatchFlowConfig {

    @Bean(name = "batchGroupStore")
    JdbcMessageStore batchGroupStore(DataSource dataSource) {
        JdbcMessageStore store = new JdbcMessageStore(dataSource);
        store.setRegion("batches.aggregate.v1");
        return store;
    }

    @Bean
    IntegrationFlow batchFlow(
            @Qualifier("batchGroupStore") MessageGroupStore groups) {
        return IntegrationFlow.from("batches.fragments")
            .aggregate(a -> a
                .messageStore(groups)
                .correlationStrategy(
                    m -> m.getHeaders().get("batchId"))
                .releaseStrategy(group -> group.size() >= 3)
                .groupTimeout(2 * 60_000L)
                .sendPartialResultOnExpiry(false)
                .expireGroupsUponTimeout(true)
                .expireTimeout(30 * 60_000L)
                .expireDuration(Duration.ofMinutes(5))
                .discardChannel("batches.discarded"))
            .channel("batches.completed")
            .get();
    }
}
~~~

`Duration` belongs to `java.time`. This example needs appropriate channels/consumers for `batches.fragments`, `batches.completed`, and `batches.discarded`; if no downstream subscriber exists, release/discard may fail. These names must remain stable and actually be wired in the application.

**Explanation:**

1. Fragments are grouped using the `batchId` header, which stays stable across restarts.
2. When three fragments arrive, the aggregator releases normally.
3. While running, `groupTimeout` can force-complete the group after two minutes without new messages.
4. If very old groups remain after a restart, `expireTimeout` together with `expireDuration` finds orphaned groups at startup and continues scanning periodically.
5. With `sendPartialResultOnExpiry(false)`, incomplete groups are discarded per configuration, **without** emitting a fake complete batch. `expireGroupsUponTimeout(true)` allows removing metadata after timeout, so a late-arriving fragment may start a new group.

**This is a business choice for illustration, not a default retention policy to copy verbatim.** If a missing fragment means waiting for human verification, retain the group longer, route data to a replayable quarantine, or choose `sendPartialResultOnExpiry(true)` with an explicit "incomplete" flag. If late fragments must not recreate a group, retain a completion marker or use an independent idempotency store.

### Difference Between Delays and Pending Groups on Restart

~~~mermaid
sequenceDiagram
    participant APP as New Application
    participant DEL as DelayHandler
    participant AGG as Aggregator
    participant DB as JdbcMessageStore
    participant IN as New fragment
    APP->>DEL: context started
    DEL->>DB: read old delay group
    DEL->>DEL: reschedule each delayed message
    APP->>AGG: endpoint ready
    IN->>AGG: fragment C, batch B-17
    AGG->>DB: read group B-17 (A, B)
    AGG->>DB: add C and evaluate release
    AGG-->>APP: eligible batch processed
    Note over AGG,DB: Orphan purge/reaper handles old groups that never get C
~~~

## 8. Orphaned Groups, Empty Groups, and Late Messages

After a restart, some groups may no longer be able to complete: the publisher stopped, the final part was lost, or upstream moved to a new batch ID. These are called *orphaned groups* once they have lingered long enough and are no longer released by normal traffic.

In Spring Integration, `expireTimeout` (positive value, in ms) sets the age threshold, while `expireDuration` sets the check interval. `purgeOrphanedGroups()` can be invoked at startup, on a schedule, and via management operations when needed. Expiry runs through `forceComplete` logic, rather than a raw statement deleting all old rows directly.

`MessageGroupStoreReaper` can also call `expireMessageGroups(timeout)` on a schedule. **Do not enable multiple purge paths simultaneously on the same group store** without verifying callbacks, locking, transactions, and result emission. Scheduler intervals also mean actual expiry can occur later than the configured threshold.

Once a group completes, the aggregator may retain an **empty group/tombstone** to prevent late arrivals from creating a new batch. Related options:

- `expireGroupsUponCompletion(false)`: keeps completion traces after normal release.
- `expireGroupsUponTimeout(true)`: removes the group after timeout-triggered force completion.
- `minimumTimeoutForEmptyGroups`: sets the minimum retention time for empty group metadata when using appropriate cleanup mechanisms.
- Dedicated store/region and consistent `LockRegistry`: prevents concurrent releases or another endpoint's callbacks from affecting the wrong group.

If the business requires "batch B-17 is processed only once" even months later, a short-TTL tombstone is **not enough**. Persist a business idempotency key with a retention period matching your storage requirements.

## 9. Crash Matrix: Store, Fetch, Send, and Commit

Restart recovery must be evaluated based on **when the crash occurs**, not merely by asking "is the row still in the DB?".

| Crash Timing | Possible State | What to Verify |
|---|---|---|
| Before message/group write commits | Message may not exist in store yet | Does the source redeliver? Did ACK already happen? |
| Delayer saved and committed, not yet due | Message remains in persistent group | After restart, does the same group ID reschedule it? |
| Delayer just became due, not yet removed from store | Message may still remain | Schedule/lock may trigger a new attempt after restart |
| Delayer removed from store, not yet sent downstream, **no transactional release** | Message can be lost if process dies in this window | Never advertise a higher delivery guarantee than the mechanism provides |
| Delayer removed in transaction, downstream throws synchronous error | Rollback can keep message in store | Check transaction manager, shared resource, and retry/reschedule |
| Downstream executed external side effect, then crashed before confirmation | Unknown whether side effect occurred | Receiver-side idempotency, outbox/inbox, and reconciliation |
| Aggregator stored two fragments, not ready to release | Pending group exists | New fragment can still join using the same correlation key |
| Aggregator released, crash around commit/output | May produce duplicate output or incomplete group state | Transactions, locks, idempotency, and side-effect consequences |
| Scheduler stopped while process/store stays alive | Messages may still exist without firing on time | Scheduler status and controlled reschedule operations |

**Store durability does not equal exactly-once delivery.** Around crash windows involving external sends, you can usually only design at-least-once combined with idempotency or compensating workflows. Never claim a message will "never be lost/duplicated" based solely on a single `messageStore(jdbcStore)` line.

## 10. Transactions and Threading Boundaries

A delayed message is released on **the scheduled task's thread**. A pending group may be updated by a consumer endpoint on a caller thread, worker executor, or poller. Transactions bind to threads and active scopes, so:

| Topology | What to Watch Out For |
|---|---|
| Delayer -> `DirectChannel` -> JDBC service | Can wrap removal and synchronous downstream work in a release transaction using the same manager |
| Delayer -> `ExecutorChannel` | Release transaction ends at the task-handoff boundary; worker processing errors happen later |
| Aggregator receiving via `DirectChannel` | Sender's transaction can include the group update if the handler uses the same transaction manager |
| Aggregator receiving via `QueueChannel` + poller | Poller transaction determines whether receive and group update share a commit |
| Persistent queue via `JdbcChannelMessageStore` | Queue ACK/removal semantics must be checked separately, not inferred from group store |
| Multiple JVMs sharing a group store | Needs distributed lock/partition strategy to prevent multiple nodes from mutating/releasing a group concurrently |

When a transaction is active while the Delayer **saves** a message, Spring Integration registers the scheduled release in an `afterCommit` callback (on supported versions), preventing the scheduled task from running before data is readable. When the Delayer **releases**, transactional advice is a separate boundary; the two do not substitute for one another.

An asynchronous consumer may continue processing after the sender has timed out or returned success. On restart, requests waiting on a synchronous gateway reply cannot automatically "reattach" to the old thread/socket. Use correlation IDs, durable business state, and a dedicated result-query API for long-running work.

## 11. Clusters, Leaders, and Avoiding Duplicate Recovery

A single instance with a JDBC store is a simple starting point. With multiple pods sharing a persistent store, several situations can arise:

- Two Delayers start up, see messages in **the same delay group**, and both schedule releases.
- Two aggregators see a group become eligible and both run force completion without a shared lock.
- A pod changes `region`/`messageGroupId` during a rolling deployment, leaving old messages known only to pods from the prior version.
- One node holds a distributed lock too long, the lease expires, and another node begins operating on the same group.

For Delayer, establish a **clear ownership/partitioning strategy** for delayed messages (for example, only one active owner per group, or partitioning/scoping group IDs by pod/workload with an ownership handoff mechanism). Do not assume `JdbcMessageStore` coordinates all scheduler timers across a cluster.

For aggregators/resequencers, Spring Integration supports a `LockRegistry` per group. If replicas share a group store, use an appropriate distributed registry such as JDBC/Redis with the same namespace. Locks do not replace idempotency or transactions; if a lock lease expires during processing, stale writers remain possible.

When changing schemas or configuration between deploys, clarify:

1. Which version wrote the pending messages?
2. Can the new version read old payloads/headers?
3. Who owns the old group IDs/regions?
4. Should old groups be drained before changing the region or migrated to the new region?
5. While two versions run concurrently, do they share the same correlation, locking, and idempotency rules?

## 12. Diagnosing When Messages Do Not Run After Restart

Before tweaking schedulers or deleting data, locate where the message stopped:

| Symptom | Possible Cause | Evidence to Check |
|---|---|---|
| Delayed message exists in JDBC store but does not emit | `messageGroupId`/region changed; Delayer not started; scheduler not running | Actual group ID, bean lifecycle, reschedule logs |
| Delayed message fires immediately after restart | Already overdue relative to original arrival time | Delay header, arrival timestamp, downtime duration |
| Delayed message fires multiple times | Concurrent recovery, crash/rollback, non-idempotent downstream side effect | Lock/owner, transaction logs, idempotency key |
| Delayed message vanishes despite downstream error | Non-transactional release or error flow swallowed the error | Remove/commit timing and `delayedMessageErrorChannel` policy |
| Group has enough fragments but does not release | Wrong `correlationId`, release strategy, store region, or endpoint not started | Group contents, bean name, consumer metrics |
| Incomplete group lingers forever | Timeout task lost across restart, no orphan purge/reaper | Group age, `expireTimeout`, scheduler schedule |
| Batch released partially after startup | Orphan purge/timeout force-completed it | Partial/discard config and callbacks |
| Old message fails to deserialize | Class, serializer, or schema changed | Stack trace, payload version, migration state |
| Duplicate groups exist across two pods | Missing distributed lock or partitioning | Node ID, lock registry, group lifecycle |

Checks in order:

1. Verify **the number of records remaining in the persistent store** and classify delay groups, pending groups, and completed groups.
2. Check that the store bean has the right datasource, region, schema, and permissions to read old data.
3. Check that Delayer/aggregator endpoints are started, `TaskScheduler` has worker threads, and tasks are not being rejected.
4. For Delayer, confirm `messageGroupId` stability and startup rescheduling; only invoke `reschedulePersistedMessages()` manually when you understand the current scheduler state.
5. For aggregators, verify correlation/release strategies; check orphan purge or reaper settings if no new fragments are coming.
6. Inspect exceptions in scheduled tasks, error channels, retry/recovery handlers, and transaction rollbacks; never infer success solely from a "scheduled" log entry.
7. Check idempotency and downstream state to avoid re-triggering an already-executed side effect.
8. In a cluster, verify only the designated owner performs recovery or that all instances use safe locking/partitioning.

### Runtime Observability

Useful metrics include: persisted delayed message count, **age of oldest overdue message**, scheduled task queue depth, time from due timestamp to actual release, release/retry counts, publisher errors, pending group count, group age p95, orphan purge count, partial/discard counts, lock wait times, executor saturation, and rollback durations.

`DelayHandler` exposes management APIs such as `getDelayedMessageCount()` and `reschedulePersistedMessages()`, which can be exposed via JMX/Control Bus when configured. Never let reschedule become a blindly repeated operational command: check active tasks first and execute under proper controls.

## 13. Restart Testing Practice

Real testing requires **two application context lifecycles** sharing **the same persistent database**. Unit tests that merely mock `MessageStore` cannot prove data survives restarts or that rescheduling behaves properly.

| Scenario | Test Steps | Expected Result |
|---|---|---|
| Delay not yet due | Send M, commit, stop context A, start context B after 10 seconds | M emits after the remaining delay, not restarting from scratch |
| Delay overdue during downtime | Stop A past the deadline, start B | M is scheduled to emit promptly after startup |
| Transactional release, downstream throws | Trigger synchronous error, inspect JDBC store after rollback | Record remains if transaction is configured properly and rollback occurs |
| Release exhausts `maxAttempts` | Cause continuous errors then restore downstream | Understand that message stays stored without a schedule; controlled reschedule works |
| Error flow swallows error | Have `delayedMessageErrorChannel` handle and return | Observe commit/recovery per contract; do not assume retry |
| Aggregator pending group | A receives 2/3 fragments, stops; B receives final fragment | Old group resumes and releases once |
| Aggregator orphan group | A receives incomplete fragments, B receives no more | Purge/reaper applies timeout and partial/discard properly |
| Rolling deploy changes payload class | Start B reading store written by A | Compatible migration/serializer or clear quarantine |
| Two replicas recover concurrently | Both open the same backend/region | No duplicate side effects; ownership/locking works |
| Duplicate message from redelivery | Resend same business event after restart | Idempotency prevents unintended reprocessing |

Sketch of a delayed message test (not a standalone runnable test):

~~~java
// contextA and contextB are two Spring ApplicationContexts initialized against
// the same JDBC database but with separate scheduler/process lifecycles.
contextA.start();
MessageChannel input = contextA.getBean(
    "reminders.input", MessageChannel.class);
input.send(MessageBuilder.withPayload(
    new Reminder("REM-99", "test@example.org", "payload")).build());

// Ensure the MessageStore write has committed.
contextA.close();

// Restart contextB with the SAME database, region, and messageGroupId.
contextB.start();
// Wait with a timeout condition; assert the reminder_delivery record
// appears exactly once and emission time meets the SLA.
contextB.close();
~~~

When writing real integration tests, instantiate a fresh context rather than calling `start()` on a closed context, keep the database/Testcontainers instance running across both lifecycles, and use a timeout-based wait instead of a fixed `Thread.sleep()`. Use unique keys to detect duplicates and record transactions/metrics in each run.

## 14. Production Checklist for Persistence and Restarts

- [ ] Both Delayer and aggregator use appropriate persistent `MessageGroupStore`s; schemas and serializers are managed across deployments.
- [ ] Delayer has a stable `messageGroupId`, and the team knows when it reschedules automatically versus when manual recovery is needed.
- [ ] Delay schedules are understood relative to original arrival time, with clear behavior for messages overdue during downtime.
- [ ] Delayer release has transactions/advice suited to the store and synchronous downstream; retry/recovery does not unintentionally swallow errors.
- [ ] Pending groups keep the same correlation strategy/region across restarts; clear policy for waiting on new fragments vs. force completion.
- [ ] Orphan purge or `MessageGroupStoreReaper` is configured with business-appropriate age, interval, and partial/discard behavior.
- [ ] Late arrivals, group tombstones, and idempotency keys are defined for all replay paths.
- [ ] `ExecutorChannel`, poller, broker ACK, and transaction manager boundaries have been tested in practice.
- [ ] Each instance/pod has clear ownership/partitioning/locking on shared stores; concurrent crash and restart have been tested.
- [ ] Metrics and alerts exist for backlog, overdue age, orphans, retries, release failures, and deserialization errors.
- [ ] Test suite validates the same persistent database across **at least two application lifecycles**.

**Conclusion:** Spring Integration runtime recovery involves two distinct tasks: **recovering delayed messages by reading the store and rescheduling releases**, and **recovering pending groups by continuing correlation or handling orphans via expiry policies**. A persistent store supplies the data for both, but only a design with explicit transactions, retry/recovery, idempotency, lifecycle management, and observability ensures flows continue safely after a restart.

## References

- [Spring Integration Reference — Delayer](https://docs.spring.io/spring-integration/reference/delayer.html)
- [Spring Integration Reference — Aggregator and Group Timeout](https://docs.spring.io/spring-integration/reference/aggregator.html)
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html)
- [Spring Integration Javadoc — DelayerEndpointSpec (6.4)](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/dsl/DelayerEndpointSpec.html)
- [Spring Integration Javadoc — CorrelationHandlerSpec (6.5)](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/CorrelationHandlerSpec.html)
