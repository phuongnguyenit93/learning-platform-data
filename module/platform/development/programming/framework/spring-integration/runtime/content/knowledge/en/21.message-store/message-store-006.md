# StoreTimeout and Cleaning Up Old Messages

When Spring Integration stores messages in memory or a persistent store, a flow can resume operating after an application restart. However, data does not vanish on its own simply because a message has sat in the store for too long. An aggregator may wait forever for the final part of a group; a queue may accumulate messages with no active consumer; a completed group may retain metadata to reject late-arriving messages. Without an expiration policy, the store grows in size, scan times increase, and runtime state becomes harder to investigate.

The topic **"StoreTimeout and Cleaning Up Old Messages"** belongs to the **Message store** chapter of the **SPRING_INTEGRATION_RUNTIME** module. We will align retention policies with message flows running across channels, endpoints, consumers, pollers, and executors, while examining transactions, retries, correlation, errors, and performance during data cleanup.

> **Naming note:** Spring Integration does not have a single universal <code>StoreTimeout</code> property to automatically set a TTL for every <code>MessageStore</code>. Here, "StoreTimeout" is a label for *the requirement to limit storage age*. The exact API depends on the component using the store: an aggregator's <code>groupTimeout</code>, <code>MessageGroupStoreReaper</code>, <code>expireTimeout</code>/<code>expireDuration</code>, or retention mechanisms specific to queues and backends.

## 1. What Can Reside in a Message Store?

Spring Integration uses <code>org.springframework.integration.store.MessageStore</code> and specialized interfaces for components that need to buffer messages. Two categories are easily conflated:

| Component | Stored Data | When Typically Taken/Deleted? | Risk of Improper Cleanup |
|---|---|---|---|
| Aggregator / resequencer | <code>MessageGroup</code>s by correlation key, potentially holding incomplete groups | When release criteria are met, on timeout, or on expiry | Loss of data awaiting aggregation; partial release; late arrivals creating duplicate groups |
| <code>QueueChannel</code> with <code>ChannelMessageStore</code> | Messages queued for a poller/consumer | When consumer receives successfully per store semantics | Deleting unprocessed work, breaking delivery guarantees |
| Delayer | Messages waiting for scheduled emission | When delay elapses and handler pulls to send | Delayed messages lost before sending |
| Claim Check | Payload saved and replaced with reference token | When downstream checks out payload or revocation policy requires | Token exists while original data is gone |
| Correlation state store | Completed group metadata, including empty groups | When metadata expiry, reaper, or purge is configured | Losing completed-group trace, causing late arrivals to re-group |

<code>SimpleMessageStore</code> keeps data in memory—useful for testing, but does not survive restarts. Implementations like <code>JdbcMessageStore</code>, Redis/MongoDB stores, or <code>JdbcChannelMessageStore</code> provide persistent storage according to each implementation's features. **Having a persistent store does not mean automatic TTL.** To delete old messages, explicitly define *when deletion is permitted* and which component owns that decision.

~~~mermaid
flowchart LR
    P["Producer"] --> CH["Channel / Endpoint"]
    CH --> S{"Storage type"}
    S -->|Correlation| G["MessageGroupStore"]
    S -->|Queue| Q["ChannelMessageStore"]
    G --> A["Aggregator / Resequencer"]
    Q --> C["Poller / Consumer"]
    A --> D["Release / expire group"]
    C --> E["Receive and process message"]
    F["Retention policy"] -.-> D
    F -. "Do not delete queue arbitrarily" .-> Q
~~~

## 2. Distinguishing Types of Timeouts

Having "timeout" in a property name does not tell you which data will be deleted.

| Configuration / Concept | Scope | Primary Behavior |
|---|---|---|
| <code>groupTimeout</code> or <code>groupTimeoutExpression</code> | One group in aggregator/resequencer | Schedules *force completion* when the group has not released via normal strategy |
| <code>sendPartialResultOnExpiry</code> | Expired group / <code>forceComplete</code> execution | Decides whether to emit incomplete parts or discard unsatisfied messages |
| <code>expireGroupsUponTimeout</code> | Group completed due to timeout | Decides whether to delete the group outright or retain completed metadata |
| <code>minimumTimeoutForEmptyGroups</code> | Empty completed group metadata | Allows cleaning empty groups after a minimum hold time, per scheduling mechanism |
| <code>MessageGroupStoreReaper.timeout</code> | Groups in a <code>MessageGroupStore</code> | When <code>run()</code> executes, asks store to expire groups older than the threshold |
| <code>expireTimeout</code> + <code>expireDuration</code> | Old/orphaned groups in a correlating handler's store | Scans at startup and periodically to clean up stale groups |
| Channel or poller send/receive timeout | Send/receive method calls | Limits wait time; does **not** auto-delete messages due to age |
| Database, Redis, or broker retention/TTL | Backend-specific records/entries | Depends on backend mechanism; not automatically aligned with Spring Integration semantics |

For example: setting <code>receiveTimeout=1000</code> on a poller means waiting up to roughly one second to receive a message where supported; it does **not** mean "delete the message after one second". Similarly, <code>sendTimeout</code> bounds how long a blocking send waits, rather than acting as an old-data cleanup policy.

## 3. Group Timeout: Waiting for Messages Then Handling Incomplete Groups

Suppose the system receives three fragments <code>A</code>, <code>B</code>, <code>C</code> of the same batch. The aggregator waits for all three, but only <code>A</code> and <code>B</code> arrive. Without a timeout, the group can sit in the store indefinitely.

~~~mermaid
sequenceDiagram
    participant U as Upstream
    participant A as Aggregator
    participant S as MessageGroupStore
    participant T as TaskScheduler
    participant D as Downstream / Discard
    U->>A: batch-42, fragment A
    A->>S: add A to group-42
    U->>A: batch-42, fragment B
    A->>S: add B to group-42
    A->>T: reset groupTimeout deadline
    Note over U,D: Fragment C never arrives
    T->>A: forceComplete(group-42)
    A->>S: complete or expire group
    A-->>D: partial result or discard per configuration
~~~

<code>groupTimeout</code> is typically measured from the last message arriving in the group (the timer can reset whenever another message joins the group). That **differs** from "the group must end exactly 60 seconds after creation": that requirement needs an expression based on the group's creation timestamp or an explicit business deadline. Timeout tasks run on a scheduler, so actual firing time may slip if the pool is busy or the application is stopped.

### On Expiry, Emit Partial Parts or Discard?

| Policy | When a Part Is Missing | When a Fragment Arrives Late |
|---|---|---|
| <code>sendPartialResultOnExpiry=true</code> | Can emit a result containing only available fragments | Depends on whether group was fully deleted and late-arrival guards |
| <code>sendPartialResultOnExpiry=false</code> | Incomplete fragments can be discarded on force complete | No partial result; must still decide whether to retain or delete metadata |
| <code>expireGroupsUponTimeout=true</code> | Deletes group completely on timeout per completion logic | Later messages can start a **new group with the same correlation key** |
| <code>expireGroupsUponTimeout=false</code> | Can retain completed group metadata | Late arrivals can be rejected via completion trace until metadata is purged |

This is a **business data policy**: is a batch missing one of three fragments valid to emit, or must it go to quarantine? A financial system may reject incomplete batches, whereas an analytics pipeline might accept a partial result tagged "incomplete".

## 4. Java DSL Example: Timeout and Retaining Completed Group Trace

Spring Integration 6.x, Java 17+ example. To focus on group lifecycle, this section uses <code>SimpleMessageStore</code>; in production, swap in <code>JdbcMessageStore</code> with appropriate schema/serialization.

~~~java
@Configuration
@EnableIntegration
public class FragmentFlowConfig {

    @Bean
    MessageGroupStore fragmentGroups() {
        return new SimpleMessageStore();
    }

    @Bean
    IntegrationFlow fragmentAggregator(
            @Qualifier("fragmentGroups") MessageGroupStore store) {
        return IntegrationFlow.from("fragments.input")
            .aggregate(a -> a
                .messageStore(store)
                .correlationStrategy(m -> m.getHeaders().get("batchId"))
                .releaseStrategy(group -> group.size() >= 3)
                .groupTimeout(60_000L)
                .sendPartialResultOnExpiry(false)
                .expireGroupsUponTimeout(false)
                .minimumTimeoutForEmptyGroups(10 * 60_000L))
            .channel("fragments.completed")
            .get();
    }
}
~~~

Key types: <code>org.springframework.integration.dsl.IntegrationFlow</code>, <code>org.springframework.integration.store.MessageGroupStore</code>, <code>org.springframework.integration.store.SimpleMessageStore</code>, <code>org.springframework.integration.config.EnableIntegration</code>. The example needs a consumer/subscriber on <code>fragments.completed</code> and messages carrying a valid <code>batchId</code> header. For output construction, the aggregator's default strategy combines payloads, so downstream must know the actual payload type.

In this configuration:

1. Groups are keyed by the <code>batchId</code> header; messages sharing the key join the same group.
2. A group with three fragments releases normally.
3. A group missing fragments for one minute after the last arrival is force-completed **without emitting a partial result**.
4. <code>expireGroupsUponTimeout(false)</code> retains completed metadata to prevent late arrivals from recreating the group right after timeout.
5. <code>minimumTimeoutForEmptyGroups</code> enables purging empty metadata after a minimum window; once the trace is removed, very late arrivals may be treated as a new group. If business rules require rejecting duplicates permanently, maintain a dedicated idempotency record with an appropriate retention period.

If you want to **delete the group completely right on timeout**, change to <code>expireGroupsUponTimeout(true)</code>. Then weigh the impact of late arrivals and distinguish expiry timeouts from retries/redeliveries.

> **Do not treat the configuration above as retention for every queue in the application.** It only applies to groups managed by this aggregator; other <code>QueueChannel</code>s or claim-check stores are unaffected.

## 5. Using MessageGroupStoreReaper to Scan Stale Groups

<code>org.springframework.integration.store.MessageGroupStoreReaper</code> is a schedulable component. It calls <code>MessageGroupStore.expireMessageGroups(timeout)</code> to trigger expiry callbacks for sufficiently old groups. A reaper **does not run automatically at exact timeout boundaries** unless something schedules calls to <code>run()</code>.

Java example:

~~~java
@Configuration
@EnableScheduling
public class GroupCleanupConfig {

    @Bean
    MessageGroupStoreReaper fragmentReaper(
            @Qualifier("fragmentGroups") MessageGroupStore groupStore) {
        MessageGroupStoreReaper reaper =
            new MessageGroupStoreReaper(groupStore);
        reaper.setTimeout(30 * 60_000L); // 30 minutes, in ms
        reaper.setExpireOnDestroy(false);
        return reaper;
    }
}

@Component
class GroupCleanupJob {
    private final MessageGroupStoreReaper reaper;

    GroupCleanupJob(
            @Qualifier("fragmentReaper") MessageGroupStoreReaper reaper) {
        this.reaper = reaper;
    }

    @Scheduled(fixedDelay = 60_000L)
    public void reap() {
        reaper.run();
    }
}
~~~

Here <code>@EnableScheduling</code>/<code>@Scheduled</code> belong to Spring Context Scheduling, and <code>MessageGroupStoreReaper</code> belongs to Spring Integration. The example illustrates *an alternative strategy* for operating a correlating endpoint's store; avoid accidentally enabling group timeout, a reaper, and another purge task on the same groups without evaluating overlapping callbacks and schedules.

A reaper with a 30-minute threshold running every minute: a group that just passed 30 minutes may wait until the next scan. If the scheduler is busy, delay increases further; expiration timing is **approximate**. Expected cleanup latency can be estimated:

~~~text
Cleanup time ≈ time when group becomes old enough
             + wait until next scan cycle
             + scheduler/lock/transaction latency
~~~

Per Spring Integration guidance, keep the reaper interval no longer than the timeout if you want to avoid holding stale groups too long.

### A Reaper Is Not Simply a DELETE

Each correlating handler normally registers callbacks on its <code>MessageGroupStore</code> to decide what happens when a group expires. A callback can:

- force-complete the group;
- emit a partial result when permitted;
- send messages to a discard flow;
- delete the group or retain completed metadata per configuration;
- throw an exception if downstream timeout processing fails.

Therefore, never treat a reaper like a SQL statement that "deletes all old rows". It can **emit new messages and cause downstream side effects**. Error handling, transactions, idempotency, and the reaper's scheduler thread must all be tested.

## 6. Cleaning Up Orphaned Groups After Restart: expireTimeout and expireDuration

A special case for **persistent MessageGroupStore** is groups left waiting when the application stops. Upon restart, previous in-memory timeout timers may no longer exist. If no new fragment arrives, old groups risk living forever.

Spring Integration provides **purge orphaned groups** on correlating handlers, using <code>expireTimeout</code> for the age threshold and <code>expireDuration</code> for the scan interval. When configured, the handler can sweep at startup and periodically; there is also a <code>purgeOrphanedGroups()</code> API for intentional operational triggers.

Example configuration fragment for an aggregator using a persistent store:

~~~java
IntegrationFlow orphanAwareFlow(MessageGroupStore dedicatedStore) {
    return IntegrationFlow.from("batches.input")
        .aggregate(a -> a
            .messageStore(dedicatedStore)
            .correlationStrategy(m -> m.getHeaders().get("batchId"))
            .releaseStrategy(group -> group.size() >= 3)
            .expireTimeout(30 * 60_000L)
            .expireDuration(Duration.ofMinutes(5))
            .sendPartialResultOnExpiry(false))
        .channel("batches.completed")
        .get();
}
~~~

This is **an illustrative configuration snippet**, not a complete <code>@Bean</code>. It requires channel beans, consumers, and a <code>MessageGroupStore</code> dedicated to this aggregator. The API belongs to Spring Integration Java DSL; <code>Duration</code> is <code>java.time.Duration</code>. Choose thresholds based on late-fragment SLAs and realistic restart schedules.

Differences from <code>groupTimeout</code>:

- <code>groupTimeout</code> schedules per-group timers while the flow is actively receiving and processing messages.
- <code>expireTimeout</code> targets groups **already sitting old enough in the store**, useful after restarts when no new events trigger those groups.
- <code>expireDuration</code> controls the purge interval; it does not mean deleting every message after that exact duration.
- <code>MessageGroupStoreReaper</code> is a standalone scanner usable with a compatible group store, provided callbacks and store ownership are clear.

Do not share **a single <code>MessageGroupStore</code> instance across multiple aggregators/resequencers** and let each component expire the others' groups. The framework detects some overlapping-callback cases, but a safe design dedicates an isolated store/partition to each correlating endpoint. With JDBC you can use <code>region</code>; with MongoDB you can separate collections depending on storage design.

## 7. Empty Groups and Late-Arriving Messages: Why Keep a "Tombstone"?

After a group releases successfully, some flows **retain empty group metadata** to remember that the correlation key already completed. This metadata is descriptively called a *tombstone* (completion trace).

~~~text
groupId=batch-42
messages=[]
complete=true
~~~

If a late message arrives carrying <code>batchId=batch-42</code>, the completion trace prevents the aggregator from accidentally starting a second round of processing. Yet if every tombstone is kept forever, the store still balloons even with zero payloads.

Three linked decisions:

1. **After normal release:** delete the group outright via <code>expireGroupsUponCompletion</code> or retain metadata?
2. **After timeout:** delete the group via <code>expireGroupsUponTimeout</code> or retain metadata?
3. **As empty metadata ages:** use <code>minimumTimeoutForEmptyGroups</code> and a suitable cleanup mechanism to bound retention?

For example, if business rules allow late messages for 24 hours: purge tombstones only after an independent deduplication policy takes over or after a retention window larger than 24 hours plus a safety margin. If tombstones are deleted early, late arrivals creating new groups is **expected behavior by design**, not a random bug.

## 8. What About Old Messages in QueueChannel?

A <code>QueueChannel</code> uses a <code>ChannelMessageStore</code>, distinct from the groups held by an aggregator. A queued message can become "old" because a consumer stopped, processing slowed down, or the data expired in business terms. Spring Integration **does not provide a single unified TTL knob** to safely delete messages across every queue store.

| Scenario | What to Do |
|---|---|
| Queue has many messages while consumer still processes slowly | Diagnose poller cadence, pools/executors, downstream latency, and backpressure before deleting |
| Message lost business validity (e.g. expired price quote) | Define an expiry header/deadline at ingress or pre-processing; route expired messages to quarantine/discard per contract |
| Queue backed by JDBC/Redis | Review APIs, transactions, and retention supported by that store implementation; do not assume <code>MessageGroupStoreReaper</code> sweeps queue messages like aggregator groups |
| Poison message looping repeatedly | Classify errors, cap retries, move to dead-letter/quarantine; never bulk-delete to hide failures |
| Messages already queued during a new version deploy | Ensure serialization/schema compatibility and migration/replay policies before running cleanup |

**Never run raw `DELETE` by timestamp directly against message store tables while consumers are running** unless you have verified the exact schema, locks, transactions, and concurrency behavior of that store implementation. Deleting a database row can break indexes/metadata, affect consumers holding references, or lose work before ACK.

If business TTL is needed, separate *retention* from *delivery*: the consumer reads the message, checks its deadline, and routes it either to normal processing or to an expired flow. For durable queues, receiving/ACKing and recording expired items must coordinate transactions/outboxes to avoid losing data on crashes.

## 9. Transactions, Retries, and Errors in Cleanup Tasks

Group expiration can trigger <code>forceComplete</code> and emit output. If downstream throws an exception inside a scheduler task, keep in mind:

- **Transaction scope:** a cleanup task does not automatically join an already-finished producer's transaction. When group state changes and emitted events must stay consistent, apply transaction advice/synchronization suited to the store and downstream.
- **Retries:** retrying a force-completion can emit duplicate outputs if the earlier attempt produced non-transactional side effects. Use an idempotency key per correlation/group and a "released" state contract.
- **Error channel:** scheduled tasks should have a proper error handler. Spring Integration recommends <code>MessagePublishingErrorHandler</code> for schedulers when expiration can emit downstream messages, so exceptions surface in error flows.
- **Locks and concurrency:** when multiple instances scan the same persistent store, enforce per-group locking, dedicated ownership/partitioning, or a distributed lock per backend capability. Never let two schedulers complete the same group simultaneously.
- **Lifecycle:** stopping an endpoint or shutting down the application does not mean all groups were cleaned up. Establish clear shutdown/startup policies, especially to avoid losing pending work.

~~~mermaid
flowchart TD
    T["Scheduler triggers timeout / reaper"]
    L{"Acquired group lock?"}
    P{"Group qualifies?"}
    F["forceComplete / callback"]
    O{"Emit partial / discard?"}
    S["Update store in transaction"]
    E["Error handling + retry policy"]
    T --> L
    L -->|Yes| P
    L -->|No| E
    P -->|No| S
    P -->|Yes| F
    F --> O
    O --> S
    F -. "Exception" .-> E
~~~

The diagram outlines control points rather than a turnkey atomic transaction implementation. Choose retry and rollback strategies based on your actual message source, scheduler, JDBC/Redis transactions, and output channel.

## 10. Observing and Diagnosing a Growing Message Store

Do not look solely at "remaining message count" and conclude all messages are old or useless. Track these as well:

| Indicator | Diagnostic Meaning |
|---|---|
| Open groups vs. completed/empty groups | Distinguishes incomplete fragment backlogs from tombstones |
| Oldest group age, age distribution by correlation key | Detects orphans and stalled schedulers |
| Queued message count and ingress/egress rates | Identifies slow consumers vs. missing consumers |
| Timeout / partial release / discard counts | Measures business impact of expiry policies |
| Store scan duration, groups processed per run | Catches slow scans, missing indexes, or lock contention |
| Scheduler task errors, rejections, lock timeouts | Exposes missed cleanups or cross-instance contention |
| Transaction rollbacks during cleanup | Assesses risk of re-executing side effects |
| DB/Redis storage size, I/O, serialization failures | Monitors operational cost and data compatibility bugs |

### Sequential Investigation Procedure

1. Identify whether the store backs an **aggregator, queue, delayer, or claim-check**; review that component's exact contract.
2. Confirm endpoints/pollers are started, executors are healthy, and no upstream outage leaves groups permanently incomplete.
3. Separate waiting groups, completed groups, and unconsumed queue messages.
4. Check timeout configs, actual scheduler execution schedules, <code>expire</code> callback logs, scan metrics, and exceptions.
5. Verify correlation keys, serialization schemas, and late-arrival policies.
6. Before enabling purges, test on sample data and reconcile released, discarded, and remaining store records.
7. In multi-instance apps, inspect locks, shared regions/partitions, and overlapping schedules.
8. After tuning, compare oldest group age, cleanup throughput, timeout rates, and backlog across several scheduler cycles.

## 11. Testing Expiration and Data Cleanup Scenarios

Include the following test cases before enabling cleanup on a persistent store:

| Test Case | Expectation |
|---|---|
| All fragments arrive before timeout | Aggregator releases normally; no partial timeout |
| Missing fragment past timeout | Partial or discard per policy; group deleted/retained per config |
| Message arrives right after timeout | No unintended duplicate side effects |
| No new messages after restart | <code>expireTimeout</code> or reaper finds and handles old groups |
| Scheduler interval longer than timeout | Cleanup runs on scan cycle, not expected to millisecond precision |
| Empty group retained for days | Completion trace stays long enough, then purges per policy |
| Queue consumer paused | Messages remain intact for resumed processing; not wiped by group policies |
| Downstream receives partial then fails | Error flow observes exception; transactions/retries do not duplicate side effects |
| Two instances scan the same persistent store | No double-release; locking/partitioning holds |
| Application version upgrade | Old store records still decode; migration or quarantine plan handles older schemas |

For timeout tests, use short durations and conditional waiting with timeouts rather than assuming schedulers fire at exact wall-clock instants. For JDBC stores, test against a real database or Testcontainers to validate transactions and concurrent cleanup. Do not use unit tests mocking <code>MessageGroupStore</code> to prove messages roll back or survive restarts.

## 12. Production Deployment Checklist

- [ ] Clearly defined what "old" means by **reference timestamp**: group creation, last message, completion, or business deadline.
- [ ] Separated pending messages from completed group metadata; avoided a blind blanket TTL.
- [ ] For aggregators, explicitly configured <code>groupTimeout</code>, partial/discard behavior, <code>expireGroupsUponTimeout</code>, and empty-group retention.
- [ ] For persistent stores, evaluated reaper or <code>expireTimeout</code>/<code>expireDuration</code> to handle orphans after restarts.
- [ ] Dedicated an isolated store/partition and correlation keys per correlating endpoint; prevented expiry callbacks from hitting the wrong groups.
- [ ] Tested cleanup schedules, transactions, distributed locks, and error handlers under realistic load.
- [ ] Established policies for late messages, retries/redeliveries, idempotency, and persisting failed records where needed.
- [ ] Managed queues/channels/delayers/claim-checks per their own semantics instead of deleting raw records arbitrarily.
- [ ] Added metrics, alerts, correlation logs, and a recovery plan if retention proves too short; avoided logging sensitive payloads.

**Conclusion:** Cleaning up old messages in Spring Integration is about managing **per-endpoint data lifecycles**, not slapping on a single timer and deleting every overdue row. For aggregators, combine <code>groupTimeout</code>, expiry callbacks, reapers, or orphan purges as required. For queues and other stores, pair layer-appropriate retention with transactions, idempotency, and clear replay policies. Keeping these boundaries distinct bounds storage growth without breaking message-processing guarantees.

## References

- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html)
- [Spring Integration Reference — Aggregator (Group Timeout, Expiring Groups)](https://docs.spring.io/spring-integration/reference/aggregator.html)
- [Spring Integration Javadoc — CorrelationHandlerSpec](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/dsl/CorrelationHandlerSpec.html)
- [Spring Integration Javadoc — MessageGroupStoreReaper](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/store/MessageGroupStoreReaper.html)
