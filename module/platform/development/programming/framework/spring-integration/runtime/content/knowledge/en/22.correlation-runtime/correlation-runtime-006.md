# LockRegistry and Group Synchronization

In Spring Integration, **correlation** identifies messages belonging to the same unit of work; a **group** is the accumulated state of messages sharing a correlation key. Aggregators and resequencers can receive multiple messages of the same group almost simultaneously from an <code>ExecutorChannel</code>, pollers, or multiple application instances. If two consumers concurrently update, check the release condition, or complete a group without synchronization, the system can assemble incomplete data, release twice, or store corrupt metadata.

This lesson belongs to the **Correlation runtime** chapter of **SPRING_INTEGRATION_RUNTIME**. Its focus is <code>LockRegistry</code>: how Spring Integration locks group operations, the difference between single-JVM and distributed locks, and how locking relates to <code>MessageGroupStore</code>, transactions, retries, timeouts, error flows, threading, performance, and lifecycle.

> **Key takeaway:** <code>LockRegistry</code> protects the *critical section* when operating on a group. It **does not create a transaction**, does not guarantee each message is delivered only once, and cannot replace idempotency or business uniqueness constraints.

## 1. Why do correlation groups need synchronization?

An aggregator might collect three fragments of the same batch:

~~~text
batchId = B-42
  ├─ fragment A arrives from executor thread-1
  ├─ fragment B arrives from executor thread-2
  └─ fragment C arrives from executor thread-3
       ↓
  same MessageGroup(B-42)
       ↓
  release when all three fragments arrive
~~~

Group state is maintained in a <code>MessageGroupStore</code>, typically including received messages, condition, completion status, and metadata for resequencing or expiration. When a message arrives, the correlating handler conceptually performs:

1. Compute the **correlation key** from the message (by default using the <code>correlationId</code> header, or a custom strategy).
2. Acquire the lock corresponding to the group's key.
3. Check/retrieve the group in <code>MessageGroupStore</code>.
4. Add the message, update the group, and evaluate <code>ReleaseStrategy</code>.
5. If qualified, prepare the result and mark/release the group according to policy.
6. Finish processing within the lock scope and release the lock per handler logic.

~~~mermaid
sequenceDiagram
    participant T1 as Thread-1
    participant T2 as Thread-2
    participant L as LockRegistry
    participant S as MessageGroupStore
    participant A as Aggregator
    T1->>L: lock("B-42")
    L-->>T1: acquired
    T2->>L: lock("B-42")
    Note over T2,L: Thread-2 waits for same group
    T1->>S: add(fragment A)
    T1->>A: check release
    T1->>L: unlock("B-42")
    L-->>T2: acquired
    T2->>S: add(fragment B)
    T2->>A: check release
    T2->>L: unlock("B-42")
~~~

Without a lock surrounding the **entire read–modify–evaluate decision**, two threads can both observe an incomplete group, overwrite metadata, or both believe they are the first thread to release. Using a thread-safe storage structure for each individual <code>add</code> operation alone does not guarantee atomicity for a sequence of operations.

## 2. Three concepts that must stay separate

| Concept | What does it protect? | What is not guaranteed |
|---|---|---|
| <code>LockRegistry</code> | Exclusive right to process the same lock key at one time within the registry's scope | Does not roll back DB writes; does not guarantee messages won't be redelivered |
| <code>MessageGroupStore</code> | Stores group messages/metadata; may be durable depending on backend | A persistent store does not mean multi-step operations are automatically synchronized across nodes |
| Transaction manager | Commits/rolls back resources participating in a transaction | Does not lock all correlation groups automatically; does not provide atomic transactions across independent brokers/APIs |
| Business idempotency | Blocks duplicate side effects upon retry/redelivery or group recreation | Does not replace locking when multiple threads must mutate metadata concurrently |

In a reliable system, **locking to prevent races**, **transactions to ensure consistent data changes**, and **idempotency to live with redelivery** must work together.

## 3. LockRegistry API and locking by group ID

Spring Integration defines <code>org.springframework.integration.support.locks.LockRegistry</code>:

~~~java
LockRegistry registry = new DefaultLockRegistry();
Lock lock = registry.obtain("B-42");

lock.lock();
try {
    // Operations requiring mutual exclusion by B-42
} finally {
    lock.unlock();
}
~~~

<code>obtain(Object lockKey)</code> returns a <code>java.util.concurrent.locks.Lock</code>. For a correlating handler, the key used for locking is tied to the **resolved group ID**. Therefore:

- Messages with the **same** group ID contend for the same lock and execute serially within the locked scope.
- Messages with **different** group IDs can potentially process concurrently if the registry assigns distinct locks.
- A key must be stable, have sensible <code>equals()</code>/<code>hashCode()</code>, and have a consistent representation across nodes.
- A group is only safe across a cluster when **every instance** respects the same lock space.

Since Spring Integration **6.2**, <code>LockRegistry</code> provides the <code>executeLocked(...)</code> utility to reduce the risk of forgetting <code>unlock()</code>:

~~~java
LockRegistry registry = new DefaultLockRegistry();

registry.executeLocked("B-42", () -> {
    updateSomeSharedState();
});
~~~

This snippet illustrates the API for **an application-managed critical section**. When you configure a <code>LockRegistry</code> on an aggregator, the framework already manages acquiring/releasing the lock; you normally **do not need** to manually add locks around every message send call.

### DefaultLockRegistry is not “one ReentrantLock per group”

<code>DefaultLockRegistry</code> is an in-memory registry backed by *striped* <code>ReentrantLock</code>s. Its default configuration uses 256 locks; a lock is chosen from the key's hash. Consequently, **two distinct keys can still land in the same stripe** and wait on each other. This is not wrong for consistency, yet it introduces contention and can cap throughput under high load.

<code>DefaultLockRegistry</code> only synchronizes threads using **the same registry instance within one JVM**. Two pods running two separate JVMs, even if each pod defines a bean with the same name, still have two independent lock sets.

## 4. Java DSL example: multiple fragments in the same batch within one instance

The example below uses Java 17+ and Spring Integration 6.x. Each batch has three fragments; two different batches can be processed concurrently, while fragments of the same batch are synchronized when updating the group. The default aggregator output is a message containing the collection of fragment payloads.

~~~java
public record Fragment(String fragmentId, String value) {}

@Configuration
@EnableIntegration
public class BatchFlowConfig {

    @Bean(name = "fragments.input")
    MessageChannel fragmentsInput() {
        return new DirectChannel();
    }

    @Bean(name = "fragments.completed")
    PollableChannel fragmentsCompleted() {
        return new QueueChannel();
    }

    @Bean
    MessageGroupStore fragmentGroupStore() {
        return new SimpleMessageStore();
    }

    @Bean
    LockRegistry fragmentGroupLocks() {
        return new DefaultLockRegistry();
    }

    @Bean
    IntegrationFlow fragmentFlow(
            @Qualifier("fragments.input") MessageChannel input,
            MessageGroupStore fragmentGroupStore,
            LockRegistry fragmentGroupLocks) {
        return IntegrationFlow.from(input)
            .aggregate(a -> a
                .messageStore(fragmentGroupStore)
                .lockRegistry(fragmentGroupLocks)
                .correlationStrategy(
                    message -> message.getHeaders().get("batchKey"))
                .releaseStrategy(group -> group.size() >= 3)
                .expireGroupsUponCompletion(false)
                .releaseLockBeforeSend(true))
            .channel("fragments.completed")
            .get();
    }
}
~~~

Key imports:

~~~java
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.store.MessageGroupStore;
import org.springframework.integration.store.SimpleMessageStore;
import org.springframework.integration.support.locks.LockRegistry;
import org.springframework.integration.support.locks.DefaultLockRegistry;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.beans.factory.annotation.Qualifier;
~~~

To send a fragment:

~~~java
Message<Fragment> fragment = MessageBuilder
    .withPayload(new Fragment("F1", "data-A"))
    .setHeader("batchKey", "tenant-7:B-42")
    .build();

fragmentsInput.send(fragment);
~~~

Here <code>MessageBuilder</code> belongs to <code>org.springframework.integration.support</code>; <code>fragmentsInput</code> is the <code>fragments.input</code> bean. After three messages arrive, you can call <code>fragmentsCompleted.receive(timeout)</code> in tests to fetch the result.

**Meaning of the configuration:**

1. <code>correlationStrategy</code> reads <code>batchKey</code>, so all fragments carrying header <code>tenant-7:B-42</code> enter one group.
2. <code>messageStore</code> holds group state; the example uses an in-memory <code>SimpleMessageStore</code>.
3. <code>lockRegistry</code> determines which lock is acquired when processing the group.
4. <code>releaseStrategy</code> evaluates the three-part condition; this is a **release rule**, not a lock function.
5. <code>expireGroupsUponCompletion(false)</code> retains completion metadata to handle late-arriving messages under default policy; a cleanup strategy for metadata will be needed later.
6. <code>releaseLockBeforeSend(true)</code> lowers the risk of holding the group lock while dispatching output downstream, especially if downstream has a callback path or another lock.

This is a **single-JVM** exercise. You cannot take the <code>fragmentGroupLocks</code> bean in different pods and conclude the two pods synchronize on the same group.

### What changes when an ExecutorChannel is present?

If messages pass through an <code>ExecutorChannel</code> before the aggregator, multiple threads can reach the handler simultaneously. The group lock still restricts state access for the same key within one JVM, though threads may have to wait. An executor does not create a shared transaction across fragments; if each message has its own transaction, lock acquisition, store writes, commits, and retries must be analyzed against the actual transaction manager.

## 5. Multiple instances sharing a MessageGroupStore: distributed locking is needed

Suppose two replicas A and B share one <code>JdbcMessageStore</code>. Each replica has its own local lock:

~~~mermaid
flowchart TD
    PA["Replica A<br/>DefaultLockRegistry"] --> GA["Group B-42"]
    PB["Replica B<br/>DefaultLockRegistry"] --> GB["Group B-42"]
    GA --> S[("Shared JDBC MessageGroupStore")]
    GB --> S
    N["Two JVMs do not share the same ReentrantLock set"] -.-> GA
    N -.-> GB
~~~

Replicas A and B **can both acquire their local locks simultaneously**, read the same group state, and both decide to release. Switching to a persistent store does not resolve this race.

The solution is configuring a <code>LockRegistry</code> backed by a shared resource, such as:

| Registry | Synchronization source | When appropriate | Operational considerations |
|---|---|---|---|
| <code>DefaultLockRegistry</code> | Single JVM memory | Single instance, or groups strictly partitioned to a single JVM | Contention, stripe size, process lifecycle |
| <code>JdbcLockRegistry</code> | Lock table in RDBMS via <code>LockRepository</code> | Shared database and wanting cross-replica locking | DDL, transaction manager, TTL, lock renewal, DB latency |
| <code>RedisLockRegistry</code> | Key/lease in Redis | Multiple instances with shared Redis | Lease expiry, renewal, failover, cache, and network |
| <code>ZookeeperLockRegistry</code> | Coordination via ZooKeeper | System already has ZooKeeper and needs cross-node access arbitration | Sessions, connectivity, and cluster state |

Distributed registries ensure instances **coordinate on the same lock key and namespace**. Correctness still depends on registry semantics, connectivity conditions, lease duration, and how nodes handle loss of lock ownership.

### Example using JdbcLockRegistry for two replicas

This is the configuration for one replica. The other replica must use **the same database, store region, and lock region**, while each replica has its own <code>DefaultLockRepository</code> bean managed by that application.

~~~java
@Configuration
public class SharedGroupInfrastructure {

    @Bean
    DefaultLockRepository groupLockRepository(
            DataSource dataSource,
            PlatformTransactionManager transactionManager) {
        DefaultLockRepository repository =
            new DefaultLockRepository(dataSource);
        repository.setRegion("batch-aggregator-lock");
        repository.setTransactionManager(transactionManager);
        return repository;
    }

    @Bean(name = "distributedGroupLocks")
    LockRegistry distributedGroupLocks(DefaultLockRepository groupLockRepository) {
        return new JdbcLockRegistry(groupLockRepository);
    }

    @Bean
    MessageGroupStore sharedGroupStore(
            DataSource dataSource,
            @Qualifier("distributedGroupLocks") LockRegistry groupLocks) {
        JdbcMessageStore store = new JdbcMessageStore(dataSource);
        store.setRegion("batch-aggregator");

        // Applies only when using Spring Integration 6.5+.
        store.setLockRegistry(groupLocks);
        return store;
    }
}
~~~

Additional imports:

~~~java
import javax.sql.DataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.integration.jdbc.lock.DefaultLockRepository;
import org.springframework.integration.jdbc.lock.JdbcLockRegistry;
import org.springframework.integration.jdbc.store.JdbcMessageStore;
~~~

In the aggregator flow, replace <code>SimpleMessageStore</code> with the <code>sharedGroupStore</code> bean and pass the <code>distributedGroupLocks</code> bean to <code>.lockRegistry(...)</code>. Both nodes must use the same <code>batchKey</code> rule. Table schemas for <code>JdbcMessageStore</code> and <code>DefaultLockRepository</code> must be initialized using the scripts for the target RDBMS before running; this configuration does not create tables automatically.

**Version distinction:** before Spring Integration 6.5, <code>AbstractCorrelatingMessageHandler</code> already had a <code>lockRegistry</code> configuration for the handler's group operations. Since **6.5**, <code>AbstractMessageGroupStore.setLockRegistry(...)</code> supports locking for metadata/group mutations at the store layer. These are **two related but non-identical protection points**. On 6.5+, evaluate using a consistent registry at both places while avoiding creating unnecessary nested lock acquisitions.

## 6. Lock key, correlation key, and namespace must be consistent

For a group, the **effective lock key** is usually derived from the resolved correlation key. Consequently, a bug in <code>CorrelationStrategy</code> can turn into a locking error or corrupted data:

| Mistake | Consequence | How to fix |
|---|---|---|
| Using only <code>orderId</code> when tenants can share IDs | Mixes messages across tenants | Use a key containing <code>tenantId</code> + <code>orderId</code> per contract |
| Using an unstable object / mutating <code>hashCode()</code> | Threads or nodes fail to locate the same group/lock | Use immutable types and stable strings/value pairs |
| Different nodes normalize keys differently | Two nodes treat the same batch as two separate groups | Standardize format, casing, encoding, and version strategy |
| Two independent aggregators share the same store and key | Group collisions; expiry callbacks may act on the wrong handler | Separate store regions and lock namespaces per endpoint |
| Changing region across deployments | Can no longer find old metadata/locks the same way | Plan migration/cleanup and rolling-deploy compatibility |
| Using <code>MessageHeaders.ID</code> for correlation | Every fragment creates its own group | Use a stable business/batch key; message ID is not a group ID |

**Cross-node consistency** matters more than how a key looks. With <code>JdbcMessageStore</code>, <code>region</code> separates groups on the same backend. With <code>DefaultLockRepository</code> or <code>RedisLockRegistry</code>, the lock namespace/region must separate independent flows while **matching across replicas of the same flow**.

## 7. Deadlocks across multiple groups or nested aggregators

Group locking prevents races, yet can cause deadlocks when a processing chain acquires multiple locks in **different orders**.

~~~mermaid
flowchart LR
    T1["Thread 1<br/>holds lock A"] --> W1["waits for lock B"]
    T2["Thread 2<br/>holds lock B"] --> W2["waits for lock A"]
    W1 -.-> T2
    W2 -.-> T1
~~~

Example flow:

~~~text
... → aggregator-1 → DirectChannel → aggregator-2 → ...
~~~

One thread holds aggregator-1's group lock and dispatches synchronously to aggregator-2, thus needing aggregator-2's lock. Meanwhile, another thread holds aggregator-2's lock and, due to a router/loop or another path, needs aggregator-1's lock. Both wait on each other; no business timeout automatically breaks a Java deadlock.

Mitigation approaches:

1. **Give each aggregator an appropriate lock namespace/registry** instead of accidentally sharing one lock space across independent endpoints. If one aggregator has multiple replicas, those replicas must still share that aggregator's namespace.
2. Use <code>.releaseLockBeforeSend(true)</code> so the group lock is not held while dispatching output downstream. Test late arrivals, retries, and how downstream behaves once group state is already completed.
3. Consider an <code>ExecutorChannel</code>/<code>QueueChannel</code> boundary after the aggregator to avoid synchronous lock chaining. This **changes transaction/thread/ACK semantics**, so design accordingly.
4. If acquiring multiple locks manually, enforce a **global lock ordering** (e.g., by endpoint name then group key) and always release inside <code>finally</code>.
5. Avoid slow HTTP calls, slow DB queries, or long-blocking APIs inside sections holding a group lock.

<code>releaseLockBeforeSend</code> solves one common deadlock case; it does **not** guarantee every kind of deadlock disappears. Store-level locks, database row locks, transactions, and downstream retries can still form other wait cycles.

## 8. Distributed lock TTL and loss-of-ownership failures

A distributed lock typically carries a **lease/TTL** so another node can reclaim the lock if the holding node dies. This is the TTL of the **lock**, not the aggregator's <code>groupTimeout</code>.

~~~text
Node A: acquire lock(B-42) → starts updating
                 |
          processing exceeds TTL
                 |
Lock lease expires (in backend)
                 |
Node B: acquire same lock(B-42)
                 |
  both nodes may execute the same work if A has not stopped
~~~

With <code>JdbcLockRegistry</code> and <code>RedisLockRegistry</code>, set the TTL large enough for the *critical section* or use supported renewal mechanisms. Depending on version, <code>RenewableLockRegistry</code> exposes lease-extension methods; Redis supports configuring an auto-renewal scheduler. **Calling <code>unlock()</code> after losing ownership can throw an exception**, which is a serious signal because the protected resource may already have been mutated concurrently.

Do not treat inflating TTL as a complete fix: an overly long TTL forces other nodes to wait a long time after a crash. For operations needing strong guarantees, add **fencing tokens/version checks** or conditional database updates if the backend and architecture support them. Distributed locks without fencing still carry risks during JVM pauses or network partitions.

### Differences across Spring Integration versions

- Spring Integration 6.2 added <code>LockRegistry.executeLocked(...)</code>.
- Spring Integration 6.5 added support for <code>AbstractMessageGroupStore.setLockRegistry(...)</code> for group metadata operations.
- Spring Integration 7.0 adds <code>DistributedLock</code> with custom TTL APIs and extends renewal capabilities for JDBC/Redis.

When on Spring Integration 6.x, do not copy 7.x-only methods into your code assuming they already exist.

## 9. How do transactions, retries, expiry, and lifecycle interact with locks?

### Transactions do not replace locks

A transaction can roll back written data, yet two transactions on two replicas can still read the same group state and race to release. Locks serialize processing decisions; transactions protect data mutations. With JDBC stores/lock registries, check transaction managers, isolation, commit timing, and lock ordering so distributed locks are not held too long or lost before commit.

### Retries/redeliveries are not eliminated by locks

After thread A completes a group and unlocks, a duplicate message can arrive again. It will acquire the lock normally. Therefore:

- Retain completion markers when **late-arriving messages** must be blocked.
- Use business keys/idempotency stores to prevent duplicates when a group expires or is recreated.
- When retrying database errors, re-examine transaction boundaries; do not blindly retry lock timeout errors forever.
- If output is emitted and a crash occurs before status updates, consider an outbox and downstream duplicate controls.

### Group timeouts and reapers must also synchronize

<code>groupTimeout</code>, <code>forceComplete()</code>, and <code>MessageGroupStoreReaper</code> can run concurrently with newly arriving messages. The expiry path does not merely delete data: it may release a partial result or discard the group. Consequently, expiry callbacks must also respect locks and the group's transaction/side-effect policy; test scenarios where the final fragment arrives right at timeout.

### Stop/restart does not instantly clear all work

When an <code>IntegrationFlow</code> or polling endpoint stops, workers that already received a message or are waiting for a lock may persist until their task completes. With local locks, a JVM crash wipes in-memory locks; with distributed locks, the backend may retain the record/lease briefly. When the application starts back up, a persistent store may still hold unfinished groups while in-memory timeout schedules must be re-established or handled via orphan cleanup.

## 10. Threading, throughput, and contention control

A per-group lock serializes operations in the *critical section* for the same key. Therefore, raising an executor pool from 8 to 64 threads will not increase throughput if 90% of messages belong to one batch: most threads simply queue behind the same group lock.

| Scenario | Symptom | Adjustment worth considering |
|---|---|---|
| One ultra-hot correlation key | Many workers wait on lock; throughput barely rises | Partition batches in a controlled way or reduce concurrency on that key |
| Different groups still waiting on each other | Local lock stripes collide; backend lock has high overhead | Evaluate <code>DefaultLockRegistry</code> config or distributed lock under real load |
| Lock held across slow downstream | Long lock hold duration, rising queue depth | <code>releaseLockBeforeSend</code>, decouple downstream, trim side effects in critical section |
| Slow JDBC locks | DB lock contention, strained queries/connection pool | Measure p95/p99 lock wait; inspect indexes, pool, transactions |
| Redis lock lease expires | Exception on unlock; multiple replicas process same group | Renew leases and inspect max processing duration |
| Backlog on only one node | Skewed routing/partition key or one node holding locks too long | Inspect key distribution, thread dumps, and lock owners |

Useful metrics: **lock acquisition wait**, **lock hold duration**, lock acquisition failures or timeouts, open group count, oldest group age, release/expiry counts, queue depth, active workers, store latency, and downstream timeout counts. Attach <code>correlationId</code>, endpoint name, and node ID to traces/logs, without logging full sensitive payloads.

## 11. Runtime diagnosis when groups stall or results duplicate

1. **Check correlation first:** confirm all three fragments actually share the same stable key, tenant/flow, and schema.
2. **Check message location:** inbound adapter → channel → endpoint → message store; do not blame locking if messages never reached the aggregator.
3. **Check topology:** <code>DirectChannel</code>, executors, pollers, replica counts, and how stores/registries are shared among them.
4. **Measure lock wait:** distinguish threads blocked on a group lock from threads waiting on database queries, queue receives, or downstream HTTP calls.
5. **Use thread dumps** (<code>jstack</code>/<code>jcmd Thread.print</code> depending on environment) to spot <code>ReentrantLock</code> contention/deadlocks. With JDBC/Redis locks, combine with backend logs/metrics because thread dumps alone cannot reveal distributed lease owners.
6. **Inspect release strategy and metadata:** is the group incomplete, completed with a tombstone remaining, or force-completed on timeout?
7. **Inspect transactions/retries:** did failures roll back, were messages redelivered, did any side effects occur prior to rollback?
8. **Test on staging with concurrency:** multiple fragments per group, two replicas, timeouts/restarts, and network faults; verify a group releases strictly per contract.

### Distinguishing common symptoms

| Symptom | Hypothesis to verify | Evidence required |
|---|---|---|
| Two outputs for the same batch | Multiple nodes local-locking a shared store; TTL expired; group deleted then recreated | Lock owner logs, group lifecycle, idempotency records |
| A group never releases | Missing fragment, faulty release strategy, stopped consumer, lock contention | Message/group counts, endpoint status, lock wait |
| Thread dump reports deadlock | Two aggregators acquiring locks in opposite order; cyclic call chain | Stack traces of both threads, lock owner/target |
| <code>unlock()</code> throws in Redis/JDBC | Lease expired or owner lost ownership | TTL, lock hold duration, renewal/backend logs |
| Old groups “stuck” after restart | Persistent store retained groups, but timeout schedules were not re-armed | Group age, orphan purge/reaper configuration |
| More threads do not raise TPS | Hot key or striped lock collision | Correlation key distribution, p95 lock hold/wait |

## 12. Testing group synchronization

Single-threaded unit tests only prove release logic; they do **not** prove concurrency safety. Include at least these cases:

| Case | Expected outcome |
|---|---|
| Three same-key fragments arrive concurrently | Group receives all parts, releases once, no lost fragments |
| Multiple batches with distinct keys arrive concurrently | Groups do not mix messages; concurrency matches expectations |
| Duplicate messages from retry/redelivery | Side effects do not duplicate per idempotency contract |
| Two Spring contexts/replicas sharing a JDBC store | Group releases once with a shared **distributed** lock |
| One instance uses a local registry, another uses a different registry | Test must expose the lack of cluster mutual exclusion |
| Final fragment and <code>groupTimeout</code> occur close together | Group releases/expires per policy without unintended loss or duplication |
| Downstream throws exception at release | Error path and transactions/retries do not cause duplicate output |
| Node crashes while holding lock | Lease is reclaimed per configuration; group can resume or is quarantined |
| One aggregator synchronously invokes another aggregator | No deadlocks under concurrent load, or deadlock prevention works |

Sketch of a concurrent test in one Spring context (using beans configured above):

~~~java
ExecutorService workers = Executors.newFixedThreadPool(3);
CountDownLatch gate = new CountDownLatch(1);
List<Future<?>> tasks = new ArrayList<>();

for (int n = 1; n <= 3; n++) {
    int index = n;
    tasks.add(workers.submit(() -> {
        gate.await();
        Message<Fragment> message = MessageBuilder
            .withPayload(new Fragment("F" + index, "part-" + index))
            .setHeader("batchKey", "tenant-7:B-42")
            .build();
        fragmentsInput.send(message);
        return null;
    }));
}

gate.countDown();
for (Future<?> task : tasks) {
    task.get(10, TimeUnit.SECONDS);
}

Message<?> combined = fragmentsCompleted.receive(10_000);
assertNotNull(combined);
assertEquals(3, ((Collection<?>) combined.getPayload()).size());
assertNull(fragmentsCompleted.receive(0));
workers.shutdownNow();
~~~

Types used in the example: <code>Executors</code>, <code>ExecutorService</code>, <code>Future</code>, <code>CountDownLatch</code>, <code>TimeUnit</code>, <code>List</code>, <code>ArrayList</code>, and <code>Collection</code> from <code>java.util</code>/<code>java.util.concurrent</code>; assertions from JUnit 5. In production tests, put <code>shutdownNow()</code> inside <code>finally</code> or use a lifecycle-managed executor to avoid leaking threads if an assertion fails.

This test proves behavior for one JVM and one input flow. It does **not** test distributed locks, JDBC store transactions, or lease-expiration behavior. Those cases require two application contexts/processes sharing a real backend (e.g., via Testcontainers), fault injection, and post-commit data inspection.

## 13. Checklist for applying LockRegistry properly

- [ ] Correlation keys are stable, namespaced by tenant/flow where needed, and formatted identically across all nodes.
- [ ] <code>MessageGroupStore</code> and <code>LockRegistry</code> are properly scoped: local for one JVM, distributed for replicas sharing a store.
- [ ] Each correlating endpoint has its own region/namespace; replicas of the same endpoint share that region/namespace.
- [ ] Exact boundaries of group mutation/release/expiry locking and store-updating transactions are defined.
- [ ] <code>releaseLockBeforeSend</code>, synchronous channel boundaries, nested aggregators, and deadlock risks have been evaluated.
- [ ] Distributed lock TTL/renewal matches lock hold time; loss-of-ownership behavior is handled.
- [ ] Retries/redeliveries, late arrivals, and idempotency are tested independently of locks; locks are not treated as an exactly-once guarantee.
- [ ] Metrics exist for lock wait/hold, group counts, timeouts/expiries, queue depth, executor saturation, and error channel failures.
- [ ] Both single-JVM concurrency tests **and** two-node shared persistent store tests exist if the application runs clustered.

**Conclusion:** In Spring Integration, <code>LockRegistry</code> is the mechanism that ensures **each correlation group is updated and evaluated for release consistently under concurrency**. For a single JVM, <code>DefaultLockRegistry</code> typically covers initial requirements; when multiple instances share a <code>MessageGroupStore</code>, a distributed registry and unified keys/namespaces are required. Combine locking with transactions, expiry policies, idempotency, lease management, and runtime observability to keep message flows stable under high load or system faults.

## References

- [Spring Integration Reference — Aggregator, Lock Registry, and Avoiding Deadlocks](https://docs.spring.io/spring-integration/reference/aggregator.html)
- [Spring Integration Reference — Distributed Locks](https://docs.spring.io/spring-integration/reference/distributed-locks.html)
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html)
- [Spring Integration Reference — JDBC Lock Registry](https://docs.spring.io/spring-integration/reference/jdbc/lock-registry.html)
- [Spring Integration Reference — Redis Lock Registry](https://docs.spring.io/spring-integration/reference/redis.html)
- [Spring Integration Javadoc — CorrelationHandlerSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/CorrelationHandlerSpec.html)
