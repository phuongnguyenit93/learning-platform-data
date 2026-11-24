# Repeated Runs, Order Shuffling, and Race Condition Analysis

## 1. Why Does a Test Always Pass Alone Yet Fail in the Full Suite?

A Spring Boot test runs in isolation and PASSES. Run alongside 200 other tests, it occasionally FAILS; shuffle class order and it PASSES again; enable parallel execution and failures spike. These are classic signs of **broken test isolation, state leakage, unsynchronized async work, or race conditions**—not an excuse to slap in `Thread.sleep(3000)` and declare the suite stable.

Three fundamental diagnostic techniques must be **clearly distinguished**:

1. **Repetition**: running the same logic repeatedly to uncover probabilistic failures, time-dependent bugs, leftover data, or uncleaned resources. JUnit Jupiter uses `@RepeatedTest`; CI can also re-run the entire Maven suite multiple times.
2. **Order shuffling (random ordering)**: varying method/class order to uncover cases where Test A accidentally sets up data, cache, environment, or singleton state that Test B relies on. JUnit offers `MethodOrderer.Random` and `ClassOrderer.Random`; Maven Surefire offers `runOrder=random` at the test-class level.
3. **Parallel execution**: creating genuine interleavings across threads/classes to expose check-then-act, lost updates, shared mutable state, connection pool exhaustion, and data contention. JUnit 5 uses `junit.jupiter.execution.parallel.*`, `@Execution`, `@ResourceLock`, and `@Isolated`.

**These are not the same tool:**
- Repeating 1,000 times **sequentially** does not necessarily make two threads write the same value concurrently.
- Shuffling order does not automatically trigger simultaneous writes.
- Parallel execution does not guarantee hitting the narrow interleaving of a rare bug.
- JUnit test method ordering does not control OS thread scheduling or DB commit order.
- Maven Surefire's `rerunFailingTestsCount` re-runs failing tests, **without curing flaky tests**.

This lesson falls under **Isolation and Parallel Execution** in Spring Boot Testing. It focuses on identifying **what is shared, what is racing, how to reproduce deterministically, and what evidence proves a fix**. The lab is a standalone **Java 17 / Spring Boot 3.5.16 / Maven / H2 / Spring JDBC / JUnit 5** project with tests demonstrating a **lost update** and two fixes: atomic SQL update and optimistic compare-and-set (CAS). Extension guidance applies to JPA `@Version`, PostgreSQL/Testcontainers, Kafka/Redis, and the TestContext cache.

### Learning Outcomes

After this lesson, you will be able to:

- Distinguish **flaky tests**, order-dependent tests, data contamination, timeouts, and race conditions.
- Use `@RepeatedTest`, `RepetitionInfo`, and `failureThreshold` without misunderstanding lifecycles.
- Shuffle methods/classes with `MethodOrderer.Random`, `ClassOrderer.Random`, and replayable seeds.
- Configure `junit-platform.properties` to run classes in parallel while keeping methods inside each class sequential.
- Use `@ResourceLock`/`@Isolated` for JVM resources prone to cross-contamination, understanding engine scope limits.
- Avoid using `@TestMethodOrder(OrderAnnotation.class)` to mask inter-test dependencies.
- Use `CountDownLatch`, `ExecutorService`, and `Future.get(timeout)` to force critical interleavings **without sleeps**.
- Prove lost updates with two workers reading the same value and both writing back, rather than hoping for lucky scheduling.
- Distinguish Java data races from database lost updates, transaction isolation, and optimistic locking.
- Assert outcomes only after all workers finish rather than while asynchronous actions are still running.
- Avoid test-level `@Transactional` hiding transaction commits or blocking visibility to worker threads.
- Scope test data by unique IDs rather than wiping entire tables on shared DBs/containers.
- Know when to lock resources, when to fix production concurrency control, and when to reset test fixtures.
- Reproduce failures from seeds, thread dumps, correlation IDs, and CI artifacts; never report PASS if all tests were skipped.
- Design a CI strategy combining fast smoke tests, randomized/parallel passes, and stress/production-like suites.

## 2. Classify the Failure Before Picking a Tool

### 2.1. A Flaky Test Is a Symptom, Not a Diagnosis

A flaky test produces varying outcomes when code and expected contracts haven't changed. Common causes:
- Race conditions in business logic or test fixtures.
- Global mutable singletons/static fields or shared Spring beans.
- Leftover database/Redis/broker state from another test.
- Dependency on method/class execution order.
- Read-before-commit and eventual consistency lags.
- Timeouts/slow CI, unready containers, or exhausted connection pools.
- Uncontrolled current time, timezones, random data, or UUIDs.
- `@DirtiesContext` closing a context while another test uses it.
- Incorrect assumptions about transaction/thread boundaries.
- Message consumer/subscriber A stealing an event awaited by B.
- Shared mock/stub setups reset by another test.
- Unrestored file/temp directory/system property/environment state.

A 1-in-1000 failure can represent a critical bug. Never weaken assertions, blindly raise timeouts, or enable retries just to turn builds green without finding the root cause.

### 2.2. Order Dependency vs Race Condition

**Order dependency**: running A→B PASSES, running B→A FAILS. No overlap between tests is needed. Examples:
- A creates an entity that B fails to seed itself.
- A sets System property `feature.enabled=true` without restoring it.
- A warms a Redis cache that B assumes is always warm.
- B assumes a table sequence starts at 1, yet A inserted rows first.
- A sets a static field read later by B.

**Race condition**: the outcome depends on the interleaving of competing operations. Examples:
- Two threads both read `balance=100` and write `balance=90`, losing one debit.
- Two consumers both observe `eventId` is absent and both execute side effects.
- Spring test class A clears a cache/singleton while B is using it.
- B iterates a shared `List` while A writes to it.
- An assertion queries the DB before an async transaction commits.

A single bug can exhibit **both**: leaked fixture state can raise the probability of a race.

### 2.3. Java Memory Model Data Race vs Transaction Race

In Java, a **data race** involves unsynchronized concurrent accesses to the same memory location where at least one is a write. Under the Java Memory Model, this causes stale visibility, lost increments, or broken invariants.

In a database, races like **lost updates** happen across transactions/clients even when Java thread-local state is spotless. That is a matter of transaction isolation and concurrency control. Marking a Java field `volatile` **does not fix** a lost update across two JDBC connections. Likewise, a database unique constraint **does not fix** an unsynchronized shared Java `HashMap`.

Identify exactly what shared resource is involved:
- Java heap object;
- JDBC row/transaction;
- Redis key;
- Kafka consumer group/offset;
- filesystem path;
- HTTP session/cache;
- environment/System properties;
- Spring `ApplicationContext`/bean definition;
- external service quota.

### 2.4. False Positives from Asserting Too Early

~~~java
asyncService.schedule("operation-7");
assertThat(repository.findById("operation-7")).isEmpty();
~~~

The test can PASS before the worker even starts; milliseconds later the worker inserts the row. **Absence of a side effect at the instant of reading** does not prove the side effect will never happen. Wait for a completion signal or observation window matching the contract. For transactional operations, meaningful assertions belong **after** all involved workers commit or roll back.

## 3. Three Testing Axes: Repeat, Shuffle, Parallel

| Axis | What It Varies | Bugs It Catches | What It Does Not Prove |
| --- | --- | --- | --- |
| `@RepeatedTest(n)` | Execution count of one test | Timing flakes, state leaks, intermittent failures | Does not force simultaneous races |
| Random method order | Method order within one class | Dependencies on in-class fixtures/shared state | Does not shuffle class order |
| Random class order | Top-level class order | Cross-class data/cache/context dependencies | Does not force thread scheduling |
| Surefire `runOrder=random` | Surefire test class order | Class-level order dependence | Does not directly randomize Jupiter method order |
| Parallel classes | Multiple classes may overlap | Shared DB/cache/singleton/global races | Does not guarantee exact micro-interleavings |
| Parallel methods | Methods inside one class overlap | Test-instance/shared-fixture races | Can break unisolated fixtures |
| Explicit barrier | Forces a specific interleaving | Lost updates, check-then-act, TOCTOU | Does not prove all interleavings were tested |
| Multi-run stress/soak | Many runs, sustained load/duration | Rare bugs, pool/resource leaks | Does not replace invariant proofs |

Best strategy: **reproduce deterministically first**, then add randomized/parallel/long-running regression coverage.

## 4. Repeated Runs in JUnit Jupiter

### 4.1. `@RepeatedTest` and Lifecycle

~~~java
@RepeatedTest(value = 20,
        name = "repetition {currentRepetition}/{totalRepetitions}")
void repeatInFreshFixture(RepetitionInfo repetition) {
    assertThat(repetition.getCurrentRepetition())
            .isBetween(1, 20);
}
~~~

This is a snippet requiring JUnit and AssertJ imports. Each repetition is treated by JUnit Jupiter as a separate test invocation:
- `@BeforeEach` runs before each repetition.
- `@AfterEach` runs after each repetition.
- Parameter resolution and extensions run normally.
- Under default `@TestInstance(PER_METHOD)`, each invocation gets a fresh test instance.
- With `@TestInstance(PER_CLASS)`, instance fields persist across repetitions; reset them or make them thread-safe.
- `@SpringBootTest` **does not build a new `ApplicationContext` per repetition**; Spring TestContext reuses the context per cache key.

To isolate data, allocate fresh fixtures in `@BeforeEach` and clean up in `@AfterEach`. Never assume "new test instance = clean DB".

### 4.2. RepetitionInfo

`RepetitionInfo` exposes current/total repetition counts and failure threshold info depending on JUnit version. Useful for tagging display names and logs. Never use repetition numbers alone as **business idempotency keys** when multiple test classes/forks can generate the same number; combine with a unique namespace or UUID.

### 4.3. failureThreshold

JUnit Jupiter 5.10+ supports:

~~~java
@RepeatedTest(value = 100, failureThreshold = 1)
void stopAfterFirstRepro() {
    // ...
}
~~~

Once a repetition FAILS, remaining repetitions can be skipped per the threshold. Handy for **triage**: one failure is enough to prove the bug exists. With parallel repetitions, JUnit docs note that failure thresholds cannot be enforced as strictly as in sequential mode; pair with `@Execution(SAME_THREAD)` when relying on `failureThreshold`.

When measuring stability/flake rates across all runs, omit `failureThreshold = 1` so every repetition executes and reports accurately. Passing once after a failure does not mean the bug fixed itself.

### 4.4. Repetition Is Not `rerunFailingTestsCount`

- `@RepeatedTest(20)`: **proactively** executes 20 invocations even when every run PASSES.
- Surefire `rerunFailingTestsCount=2`: re-runs only **failures** per provider/plugin, marking a test as flaky in reports if a retry PASSES.
- In-method loop `for (i=0; i<100; i++) ...`: still one JUnit test method; lifecycle callbacks and fixtures do not reset between loop iterations.

In CI, never use failure reruns to turn an initial failure into "no problem". Inspect Surefire XML, `flake` counts, and preserve artifacts from the first failure.

### 4.5. Repeating an Entire Suite

~~~bash
mvn -q clean test
mvn -q test
mvn -q test
~~~

These are three separate executions. When Surefire forks a JVM, cached contexts and static state reset per fork; external DBs/containers may or may not reset depending on ownership. Use CI matrices or stress jobs to run multiple iterations while saving seeds, configs, and failure reports. Never treat `mvn test` in the same working directory as pristine if filesystem state or reusable containers persist.

## 5. Shuffling Order to Uncover Hidden Dependencies

### 5.1. JUnit Default Order Is Not Random Every Run

JUnit Jupiter's default method/class ordering uses a **deterministic yet intentionally unpredictable** algorithm. It promises neither alphabetical nor source-code order; its goal is repeatability. Assuming Java reflection or declaration order is a contract is wrong.

To shuffle explicitly:

~~~java
@TestMethodOrder(MethodOrderer.Random.class)
class OrderIndependentTest {
    @Test void createsOwnFixture() { }
    @Test void readsOnlyOwnFixture() { }
}
~~~

This is a snippet. `MethodOrderer.Random` shuffles **methods within a class**; it does not alter thread scheduling between two workers inside one method.

### 5.2. Random Class Order

In `src/test/resources/junit-platform.properties`:

~~~properties
junit.jupiter.testclass.order.default=org.junit.jupiter.api.ClassOrderer$Random
junit.jupiter.testmethod.order.default=org.junit.jupiter.api.MethodOrderer$Random
~~~

These settings randomize **test discovery order**, not `@Order` annotations on business logic. Furthermore, `ClassOrderer.Random` does not guarantee classes **actually start executing** in that exact sorted order when JUnit parallel scheduling is enabled.

### 5.3. Reproducible Seeds

JUnit provides:

~~~properties
junit.jupiter.execution.order.random.seed=4242026
~~~

The same seed + same test plan/discovery inputs normally reproduces the pseudorandom order. If tests are added, removed, or renamed, or JUnit versions change, do not expect identical ordering purely from keeping the seed constant. When a CI job FAILS, save:
- Seed.
- Maven/Gradle command.
- JUnit version and discovery set.
- JVM/forks/parallelism settings.
- Executed test methods/classes.
- Relevant thread/request correlation IDs and DB state.

If no seed is configured, the random orderer picks a default seed; capture the seed logged by JUnit at `CONFIG` level for replay.

### 5.4. Surefire `runOrder` vs Jupiter `MethodOrderer`

~~~bash
mvn -q -Dsurefire.runOrder=random test
~~~

`surefire.runOrder=random` tells Maven Surefire to randomize the order of test **classes** it invokes. **Method** ordering inside each class belongs to JUnit Jupiter orderers.

Never run `mvn -Dsurefire.runOrder=random` and claim all methods and interleavings were shuffled. With parallel forks, actual start order also depends on the OS/scheduler.

### 5.5. Never Use `@TestMethodOrder` to Mask Bugs

A suite like:

~~~java
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class FragileWorkflowTest {
    @Test @Order(1) void createsRecord() { }
    @Test @Order(2) void updatesRecordFromPreviousTest() { }
    @Test @Order(3) void deletesRecordFromPreviousTest() { }
}
~~~

may represent an **intentionally ordered integration workflow scenario**, not three independent tests. Running one method alone lacks prerequisites. Prefer either **one `@Test` method** encapsulating the full workflow, or giving every method its own fixture setup/cleanup. Never use `@Order` to couple tests that are expected to be independent.

### 5.6. Signs of an Order-Dependent Test

- Test PASSES only when another method ran before it.
- Running `-Dtest=MyTest#singleMethod` FAILS.
- Class B PASSES only after Class A.
- Adding `@DirtiesContext` to one class flips another class between PASS and FAIL.
- Changing the seed consistently breaks one specific permutation.
- A test relies on a mock setup created earlier in the suite that disappears when run solo.

Immediately inspect static fields, Spring singleton bean state, DB/cache data, System properties, timezones, mocked beans, and Spring TestContext caching.

## 6. Parallel Execution in JUnit 5

### 6.1. Enabling Two Different Configurations

To run both **methods** and **classes** concurrently:

~~~properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=concurrent
~~~

Enabling `enabled=true` alone without setting execution modes leaves nodes running sequentially under default `SAME_THREAD`.

To run **classes in parallel while keeping methods within each class sequential**—a much easier model to control:

~~~properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=same_thread
junit.jupiter.execution.parallel.mode.classes.default=concurrent
junit.jupiter.execution.parallel.config.strategy=fixed
junit.jupiter.execution.parallel.config.fixed.parallelism=3
~~~

The lab uses this configuration. Two test classes can execute simultaneously while each class runs its own `@BeforeEach`/`@AfterEach` sequentially. **The race test explicitly spawns two application worker threads inside a method**, so it does not rely on Jupiter running methods in parallel.

### 6.2. `@Execution`

~~~java
@Execution(ExecutionMode.CONCURRENT)
class ParallelSafeTests {
    // Appropriate only when fixtures/data/beans are thread-safe.
}
~~~

`@Execution` controls Jupiter test node scheduling; it does not magically make an entire Spring app thread-safe. Parallel execution must also be enabled with valid defaults/config.

To keep a class's methods sequential:

~~~java
@Execution(ExecutionMode.SAME_THREAD)
class SharedFixtureTests {
}
~~~

Use this only with an explicit contract reason; the long-term goal remains full test independence. Exercise caution combining `@RepeatedTest` `failureThreshold` with concurrent repetitions.

### 6.3. `@ResourceLock`

JUnit Jupiter's `@ResourceLock` declares a shared resource touched by a test:

~~~java
@ResourceLock(value = Resources.SYSTEM_PROPERTIES,
              mode = ResourceAccessMode.READ_WRITE)
@Test
void changesPropertyTemporarily() {
    // write System.setProperty(...) and restore in finally
}
~~~

- `READ_WRITE`: exclusive lock against all tests declaring the same resource key.
- `READ`: can run concurrently with other readers, excluded from writers.
- Held by the Jupiter engine across `@BeforeEach`/test/`@AfterEach`, not just the method body.
- Coordinates **only among JUnit tests sharing the engine and resource naming contract**.
- Does not lock arbitrary application threads, other processes/JVMs, or external actors. If another test mutates System properties without declaring the lock, a race remains.

Custom resource names can also be declared:

~~~java
@ResourceLock(value = "test-db:shared-schema",
              mode = ResourceAccessMode.READ_WRITE)
class SharedSchemaExclusiveTests {
}
~~~

This is a snippet, not a database-level advisory lock. Resource locks coordinate tests, never replacing database locks.

### 6.4. `@Isolated`

`@Isolated` instructs JUnit Jupiter to run a class separately from other classes within the **same JUnit engine execution**, helpful when JVM-global mutations cannot be broken down into narrow resource keys. It reduces throughput, so prefer fixture isolation or precise `@ResourceLock` keys.

`@Isolated` does not isolate Docker namespaces, prevent other JVMs from running, or fix races inside business code. Spring TestContext docs recommend against parallelizing tests using `@DirtiesContext`, `@MockitoBean`/`@MockitoSpyBean`, or unisolated mutations of shared external services.

### 6.5. Class Order + Parallel Scheduling

With random class ordering and parallel classes enabled, initial discovery order is shuffled, yet **actual start timing** is decided by the execution scheduler. Never assert "Class A ran before Class B" via a shared static boolean. Tests must pass regardless of start/finish interleaving.

### 6.6. Thread Counts and CI Resources

Setting `fixed.parallelism=3` does not mean only three threads exist in the JVM. Spring applications/executors, Hikari housekeepers, Kafka listeners, JUnit worker pools, and GC all run additional threads. Size Hikari pools and DB connection limits appropriately; excessive parallel tests often time out from **resource contention** rather than data races.

## 7. Spring Boot Pitfalls Under Parallel Execution

### 7.1. The ApplicationContext Cache Is Shared State

`@SpringBootTest` can reuse the same `ApplicationContext` across multiple methods and classes. Great for speed, yet watch out for:
- Singleton services with mutable fields.
- `CacheManager`/Redis caches retaining entries.
- Shared DataSources and connection pools.
- `@MockitoBean` replacements being reset or re-stubbed.
- Embedded databases retaining rows without rollback/cleanup.
- Testcontainers backends serving multiple classes simultaneously.

Spring Framework 6.2 maintains a static JVM context cache defaulting to 32 contexts with LRU eviction. A cache hit does not mean clean data. Multiple forks maintain separate static caches.

### 7.2. `@DirtiesContext` Is Not Default Isolation

`@DirtiesContext` marks a context for cache eviction and closure. If Class A closes the context while Class B still uses it in parallel, B can fail with `ApplicationContext ... no longer active` or destroyed clients. Spring docs warn that such tests **should not run in parallel** without special control. Never scatter `@DirtiesContext` to solve data contamination.

### 7.3. `@MockitoBean`/`@MockitoSpyBean` and Parallel Tests

In Spring Framework 6.2, `@MockitoBean`/`@MockitoSpyBean` replace beans inside the context. Concurrent mock resets/stubbings from two tests sharing that context can conflict. Spring TestContext docs categorize tests with bean overrides as unsafe to parallelize without isolation. For unit/slice tests, minimize shared full-context mocks or separate configurations.

### 7.4. Test-Level `@Transactional` Does Not Cover Worker Threads

Spring TestContext `@Transactional` on a test method opens a **test-managed transaction** bound to the current thread and rolls it back at test end. If the test:
1. Inserts a fixture inside the uncommitted test transaction.
2. Submits a worker thread.
3. The worker executes in a **different** JDBC transaction.
4. The worker either cannot see the uncommitted fixture or the test's rollback fails to undo the worker's committed changes.

This is neither a Java nor an H2 bug: Spring imperative JDBC transaction state uses `ThreadLocal`. Never expect `@Transactional` to propagate into `ExecutorService`, `@Async`, or JUnit preemptive timeout threads.

The lab deliberately **omits `@Transactional` on the test class**, so setup and cleanup commit immediately and worker threads see the seeded IDs.

### 7.5. Preemptive Timeouts Worsen Misunderstandings

Spring docs warn that `assertTimeoutPreemptively(...)` inside a test-managed transaction executes the test body on a separate thread outside the original transaction, leaving writes uncommitted/unrolled back contrary to expectations. When testing transaction semantics, prefer bounded `Future.get(timeout)`/non-preemptive timeouts with clean architecture, and inspect committed state after completion.

### 7.6. `@Sql` and Database Cleanup

`@Sql` is convenient for seeding/cleanup, yet running `TRUNCATE all tables` on a shared DB during parallel class execution wipes other tests' fixtures. Every test should own:
- Unique business keys/namespaces.
- Clear transaction boundaries.
- Setup with proper commit/visibility.
- Targeted cleanup `WHERE id = ...`.
- Or a dedicated schema/database/container when global reset is required.

Never use `@DirtiesContext` as a substitute for DB isolation.

### 7.7. Testcontainers and Shared Infrastructure

Sharing PostgreSQL/Redis/Kafka saves startup time, yet:
- Two tests sharing a topic/group/queue can steal each other's messages.
- Leftover Kafka offsets from an earlier test cause the next test to skip events.
- Redis `FLUSHALL` destroys other tests' data.
- Postgres unique keys/sequences retain leftover state.
- Per-class JUnit `static @Container` instances can stop before a cached Spring context closes.
- Slow Docker startup/readiness causes timeouts unrelated to business races.

Distinguish **container lifetime**, **client connection lifetime**, **data isolation**, **JUnit class lifetime**, and **Spring context lifetime**. Use Spring-managed container beans when you want the backend lifecycle synchronized with the context cache.

## 8. Analyzing Race Conditions via Execution Schedules

### 8.1. Lost Update: The Classic Case

Initially:

~~~text
counter = 0
~~~

Two workers both execute:

~~~text
read counter
compute counter + 1
write counter
~~~

Failure schedule:

~~~text
Time    Worker A                    Worker B                Database
----    --------                    --------                --------
T0                                                          value = 0
T1      SELECT -> 0
T2                                  SELECT -> 0
T3      compute 1
T4                                  compute 1
T5      UPDATE value=1
T6                                  UPDATE value=1
T7                                                          value = 1 (wrong)
~~~

Expected after two operations is 2; actual is 1. Sequential tests observe only 2 and miss the bug. A barrier placed **after `SELECT` and before `UPDATE`** deterministically reproduces this exact interleaving.

### 8.2. Check-Then-Act / TOCTOU

Example:

~~~java
if (!repository.existsById(operationId)) {
    externalGateway.charge(operationId);
    repository.saveReceipt(operationId);
}
~~~

Two workers can both observe `exists=false` and both charge. This is a **time-of-check to time-of-use race**. Calling `existsById` a second time solves nothing; you need atomic claims/unique constraints/idempotency keys, plus external payment/provider idempotency when side effects leave the DB.

### 8.3. Read-Modify-Write on a Java Field

~~~java
private int counter;

void increment() {
    counter++;
}
~~~

`counter++` is read, compute, write—not atomic. Use `AtomicInteger.incrementAndGet()` or locking depending on invariants. `volatile int counter` improves visibility only; it **does not make `++` atomic**. Testing Java heap concurrency targets a different layer than the lab's JDBC example.

### 8.4. ConcurrentMap Does Not Automatically Protect Compound Operations

~~~java
if (!map.containsKey(key)) {
    map.put(key, create());
}
~~~

Even with `ConcurrentHashMap`, a separate check-then-put races. When matching the contract, `computeIfAbsent`/`putIfAbsent` offers atomic mapping semantics (mindful of side effects and mapping function caveats). Similarly, Redis uses `SET key value NX`/Lua transactions, and databases use unique indexes/CAS/upserts/locks.

### 8.5. Double Publish, Double Charge, Double Ack

Two workers can concurrently:
- Publish the same event twice.
- Send duplicate emails.
- Decrement the same inventory row inconsistently.
- Process a redelivered message twice.
- Mark a job `DONE` while another path hasn't finished side effects.

Establish a stable **business operation identity** across retries, a durable idempotency record, and clear transaction boundaries. `synchronized` locks only within one JVM and is insufficient across a multi-instance Spring Boot cluster.

### 8.6. Deadlocks Are Also Concurrency Bugs

Two transactions lock A and B in opposite orders:
- Worker 1 locks row A, then waits for B.
- Worker 2 locks row B, then waits for A.

The database picks a victim transaction to roll back. Tests should check retry policies, lock ordering, and bounded waits; never assume concurrency failures only manifest as lost updates.

### 8.7. Race or Scheduling Flake?

If a test fails because no event arrived after 50 ms, you do not yet know if:
- The worker hasn't run because the executor is busy.
- The worker ran and rolled back.
- The message went to another queue.
- A data race occurred.
- An assertion read the DB before commit.
- Eventual consistency lagged.

Use correlation/event IDs, completion signals, layer-appropriate logs/metrics, and durable state checks. Never call every failure a "race" without interleaving evidence.

## 9. Forcing Interleavings with CountDownLatch Instead of Sleep

### 9.1. Post-Read Barrier

A `CountDownLatch(2)` in the test acts as:
1. Worker A reads the current value.
2. Worker B also reads the current value.
3. Both call `countDown()`.
4. Both call `await(timeout)` until both arrive.
5. Only then do both proceed to `UPDATE`.

Starting at 0, both A and B capture local `before=0`, forcing both `UPDATE`s to write `1`. This **tests a specific interleaving deterministically** without relying on scheduler luck.

### 9.2. Two Gate Levels Are Needed

- **Start gate**: `ready=CountDownLatch(2)` + `start=CountDownLatch(1)` ensures both tasks are poised before starting.
- **After-read gate**: `CountDownLatch(2)` ensures both have read the same state before either writes.

Never use a non-volatile shared mutable boolean as a gate—that itself is a Java data race. `CountDownLatch`/`CyclicBarrier`/`Phaser` provide proper memory synchronization guarantees.

### 9.3. Finite Timeouts and Teardown

Every `await`/`get` needs a finite timeout:
- If one worker throws before counting down, the other does not hang forever.
- If CI is CPU-starved, the test fails with a clear message instead of blocking indefinitely.
- `Future.get(timeout)` propagates real exceptions from workers.
- `ExecutorService` must shut down inside `finally`.
- Fixture cleanup/connection release must not run while workers are still active.

Awaitility helps wait for **eventual conditions**, yet never use polling to force a precise two-read barrier. Barriers reproduce bugs; polling waits for state convergence.

### 9.4. Barriers Can Deadlock If Placed in the Wrong Spot

If two workers are already holding **an exclusive lock** when hitting a barrier, Worker A holds the lock waiting for B while B waits on the lock to reach the barrier → deadlock/timeout. Place gates **before** acquiring locks or at non-locking boundaries when forcing concurrent reads.

The lab uses JDBC auto-commit for `unsafeIncrement` with no outer transaction holding row locks across the barrier; H2's two `SELECT`s do not block each other on read. Then the fixed atomic SQL update serializes properly inside the database.

## 10. Maven Project: Reproducing Lost Update and Two Fixes

### 10.1. Model

A `demo_counters` table stores `counter_id` and `current_value`. Three algorithms:

1. **Unsafe read-then-overwrite**: reads `current_value`, invokes `afterReadGate.run()`, writes `old+1`. The test forces both workers to read 0 → final 1.
2. **Atomic SQL increment**: `UPDATE demo_counters SET current_value = current_value + 1 WHERE counter_id = ?`. The database increments in a single SQL write operation; two updates on the same ID → final 2 (absent connection/transaction errors).
3. **Optimistic compare-and-set**: reads current, then `UPDATE ... WHERE current_value = expected`. Only one worker wins when both read 0. The losing caller reloads/retries per policy. The test asserts one succeeds, one conflicts, and a retry reaches 2.

This demonstrates a database race. It does not claim to prove Java heap `AtomicInteger` or production PostgreSQL isolation modes. Production code must enforce concurrency invariants at the database/transaction boundary or distributed coordinator, not merely via synchronized Java objects.

### 10.2. Directory Tree

~~~text
test-order-and-races-lab/
├── pom.xml
├── src/main/
│   ├── java/com/example/racelab/
│   │   ├── RaceLabApplication.java
│   │   ├── CounterRepository.java
│   │   └── CounterService.java
│   └── resources/
│       ├── application.properties
│       └── schema.sql
└── src/test/
    ├── java/com/example/racelab/
    │   ├── CounterRaceIntegrationTest.java
    │   ├── OrderIndependentIntegrationTest.java
    │   └── SystemPropertyIsolationTest.java
    └── resources/junit-platform.properties
~~~

`src/test/resources/junit-platform.properties` enables class-level parallelism + random ordering so the suite **genuinely** exercises both axes. Every test method in the Spring classes keeps its own fixture without `@DirtiesContext` or global mock mutations.

### 10.3. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>test-order-and-races-lab</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
      <groupId>com.h2database</groupId>
      <artifactId>h2</artifactId>
      <scope>runtime</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

The Maven parent manages compatible Spring Framework, Spring JDBC, Hikari, H2, JUnit Jupiter, AssertJ, and Surefire versions. `spring-boot-starter-web` is omitted since no HTTP server runs. JDK 17+ and Maven are required; Docker is unnecessary because the backend is H2 in-memory.

### 10.4. application.properties

`src/main/resources/application.properties`:

~~~properties
spring.application.name=test-order-and-races-lab
spring.main.web-application-type=none

spring.datasource.url=jdbc:h2:mem:race_lab;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=6
spring.datasource.hikari.connection-timeout=10000

spring.sql.init.mode=always
~~~

A Hikari pool size of 6 suffices for two worker threads plus main/test queries in the lab. H2 `DB_CLOSE_DELAY=-1` keeps the in-memory DB alive inside the JVM until shutdown without **cleaning automatically between test classes**. That is why each fixture uses its own UUID.

H2 concurrency/isolation semantics differ from PostgreSQL/MySQL. Use this project to learn mechanics and verify SQL logic; for production DB guarantees, add Testcontainers integration tests against the real RDBMS/schema/migrations.

### 10.5. schema.sql

`src/main/resources/schema.sql`:

~~~sql
CREATE TABLE IF NOT EXISTS demo_counters (
    counter_id VARCHAR(90) PRIMARY KEY,
    current_value INTEGER NOT NULL
);
~~~

A primary key prevents duplicate counter IDs. It **does not** prevent lost updates when the app reads and overwrites a row without CAS/locks. Those are two separate invariants: row uniqueness vs update correctness.

### 10.6. RaceLabApplication.java

`src/main/java/com/example/racelab/RaceLabApplication.java`:

~~~java
package com.example.racelab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RaceLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(RaceLabApplication.class, args);
    }
}
~~~

The main class bootstraps Spring Boot. Neither `@EnableScheduling` nor `@Async` is added; tests spawn worker threads explicitly with `ExecutorService`.

### 10.7. CounterRepository.java

`src/main/java/com/example/racelab/CounterRepository.java`:

~~~java
package com.example.racelab;

import java.util.Objects;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class CounterRepository {

    private final JdbcTemplate jdbc;

    public CounterRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void insert(String id, int initialValue) {
        jdbc.update(
                "INSERT INTO demo_counters "
                        + "(counter_id, current_value) "
                        + "VALUES (?, ?)",
                id, initialValue);
    }

    public int value(String id) {
        Integer current = jdbc.queryForObject(
                "SELECT current_value FROM demo_counters "
                        + "WHERE counter_id = ?",
                Integer.class,
                id);
        return Objects.requireNonNull(current);
    }

    public void overwrite(String id, int newValue) {
        int affected = jdbc.update(
                "UPDATE demo_counters SET current_value = ? "
                        + "WHERE counter_id = ?",
                newValue, id);
        if (affected != 1) {
            throw new IllegalArgumentException(
                    "Unknown counter: " + id);
        }
    }

    public int incrementAtomically(String id) {
        return jdbc.update(
                "UPDATE demo_counters "
                        + "SET current_value = current_value + 1 "
                        + "WHERE counter_id = ?",
                id);
    }

    public int compareAndSet(
            String id, int expected, int next) {
        return jdbc.update(
                "UPDATE demo_counters SET current_value = ? "
                        + "WHERE counter_id = ? AND current_value = ?",
                next, id, expected);
    }

    public void delete(String id) {
        jdbc.update(
                "DELETE FROM demo_counters WHERE counter_id = ?",
                id);
    }
}
~~~

No `@Transactional` sits on the repository or service. In the lab, `JdbcTemplate` statements run in standard JDBC auto-commit mode, letting us force interleaving **between `SELECT` and `UPDATE`** without holding transaction-level row locks across the barrier.

Inside a real transaction, `SELECT ... FOR UPDATE` or isolation/optimistic locking changes behavior, yet merely slapping on `@Transactional` does not automatically cure lost updates. Understand DB isolation and conflict detection.

### 10.8. CounterService.java

`src/main/java/com/example/racelab/CounterService.java`:

~~~java
package com.example.racelab;

import java.util.Objects;

import org.springframework.stereotype.Service;

@Service
public class CounterService {

    private final CounterRepository counters;

    public CounterService(CounterRepository counters) {
        this.counters = counters;
    }

    /**
     * Intentionally contains a race for demonstration.
     * Do not use this read-then-overwrite pattern for production counters.
     */
    public void unsafeIncrement(
            String id, Runnable afterReadGate) {

        int seen = counters.value(id);
        Objects.requireNonNull(afterReadGate).run();
        counters.overwrite(id, seen + 1);
    }

    /**
     * Single SQL operation updating at the database.
     */
    public void atomicIncrement(String id) {
        int affected = counters.incrementAtomically(id);
        if (affected != 1) {
            throw new IllegalArgumentException(
                    "Unknown counter: " + id);
        }
    }

    /**
     * Single compare-and-set; a caller losing on conflict
     * receives false to reload/retry at the proper boundary.
     */
    public boolean compareAndSetIncrementOnce(
            String id, Runnable afterReadGate) {

        int seen = counters.value(id);
        Objects.requireNonNull(afterReadGate).run();
        return counters.compareAndSet(
                id, seen, seen + 1) == 1;
    }
}
~~~

**Design notes:**
- `afterReadGate` is a seam intentionally inducing interleaving in tests. Production code needs no gate; if keeping a seam, separate implementations/fault hooks so public APIs do not leak test mechanics.
- The unsafe method is intentionally non-atomic.
- The atomic method lets the database compute `current_value + 1` inside the write operation rather than passing stale `seen` from the application.
- The CAS method uses `WHERE current_value = expected`, returning `false` if data changed since the read; the caller decides whether to retry or report conflict.
- Never swallow transaction/data access exceptions and pretend the operation succeeded.

### 10.9. junit-platform.properties

`src/test/resources/junit-platform.properties`:

~~~properties
# Shuffle method and class order.
junit.jupiter.testmethod.order.default=org.junit.jupiter.api.MethodOrderer$Random
junit.jupiter.testclass.order.default=org.junit.jupiter.api.ClassOrderer$Random

# Allow different classes to run in parallel,
# while keeping methods within each class sequential.
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=same_thread
junit.jupiter.execution.parallel.mode.classes.default=concurrent
junit.jupiter.execution.parallel.config.strategy=fixed
junit.jupiter.execution.parallel.config.fixed.parallelism=3
~~~

Notes:
- No seed is pinned, so each suite execution can pick a new order.
- Seeds can be overridden via JVM/test config for replay.
- Random method ordering does not prove every permutation was tried.
- Parallel methods are **not** enabled by default here; the race test spawns two worker threads inside each method.
- Spring tests share `ApplicationContext`/DB while fixtures **use a unique ID per method**.
- Any test class mutating global resources must use `@ResourceLock` or proper isolation.
- If production CI prohibits parallel tests on a shared DB, separate class-level parallel suites from mutating tests or switch to per-test schemas/databases.

### 10.10. CounterRaceIntegrationTest.java

`src/test/java/com/example/racelab/CounterRaceIntegrationTest.java`:

~~~java
package com.example.racelab;

import java.util.List;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.RepeatedTest;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestMethodOrder;
import org.junit.jupiter.api.MethodOrderer;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@Execution(ExecutionMode.SAME_THREAD)
@TestMethodOrder(MethodOrderer.Random.class)
class CounterRaceIntegrationTest {

    @Autowired
    CounterRepository repository;

    @Autowired
    CounterService service;

    private String id;

    @BeforeEach
    void seedFreshCounter() {
        id = "race_" + UUID.randomUUID()
                .toString().replace("-", "");
        repository.insert(id, 0);
    }

    @AfterEach
    void cleanupOnlyThisCounter() {
        repository.delete(id);
    }

    /**
     * Forces both workers to finish reading before either
     * proceeds to the UPDATE step.
     */
    private static final class TwoReaderBarrier
            implements Runnable {

        private final CountDownLatch bothRead =
                new CountDownLatch(2);

        @Override
        public void run() {
            bothRead.countDown();

            try {
                if (!bothRead.await(
                        5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "both-read gate timed out");
                }
            }
            catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                        "interrupted waiting for both reads",
                        interrupted);
            }
        }
    }

    /**
     * Both tasks become ready before starting.
     * Uses Future.get(timeout) to propagate exceptions.
     * No Thread.sleep or mutable boolean gates.
     */
    private List<Boolean> runTwo(
            Callable<Boolean> operation)
            throws Exception {

        ExecutorService pool =
                Executors.newFixedThreadPool(2);

        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);

        Callable<Boolean> task = () -> {
            ready.countDown();

            if (!start.await(
                    5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "start gate timed out");
            }

            return operation.call();
        };

        Future<Boolean> first = pool.submit(task);
        Future<Boolean> second = pool.submit(task);

        try {
            assertThat(ready.await(
                    5, TimeUnit.SECONDS)).isTrue();

            start.countDown();

            return List.of(
                    first.get(10, TimeUnit.SECONDS),
                    second.get(10, TimeUnit.SECONDS));
        }
        finally {
            start.countDown();
            first.cancel(true);
            second.cancel(true);
            pool.shutdownNow();

            assertThat(pool.awaitTermination(
                    5, TimeUnit.SECONDS)).isTrue();
        }
    }

    @RepeatedTest(value = 12,
            name = "lost update repetition {currentRepetition}")
    void deliberatelyUnsafeReadModifyWriteLosesAnUpdate()
            throws Exception {

        TwoReaderBarrier barrier =
                new TwoReaderBarrier();

        List<Boolean> results = runTwo(() -> {
            service.unsafeIncrement(id, barrier);
            return true;
        });

        assertThat(results)
                .containsExactlyInAnyOrder(true, true);

        // Both read 0, both UPDATEd to 1.
        assertThat(repository.value(id)).isEqualTo(1);
    }

    @RepeatedTest(value = 12,
            name = "atomic update repetition {currentRepetition}")
    void atomicSqlUpdatePreservesBothIncrements()
            throws Exception {

        List<Boolean> results = runTwo(() -> {
            service.atomicIncrement(id);
            return true;
        });

        assertThat(results)
                .containsExactlyInAnyOrder(true, true);

        assertThat(repository.value(id)).isEqualTo(2);
    }

    @RepeatedTest(value = 10,
            name = "CAS repetition {currentRepetition}")
    void optimisticCasDetectsConflictAndRetrySucceeds()
            throws Exception {

        TwoReaderBarrier barrier =
                new TwoReaderBarrier();

        List<Boolean> results = runTwo(
                () -> service.compareAndSetIncrementOnce(
                        id, barrier));

        // Both readers saw 0:
        // one CAS succeeds, one CAS conflicts.
        assertThat(results)
                .containsExactlyInAnyOrder(true, false);

        assertThat(repository.value(id)).isEqualTo(1);

        // Retry with a fresh read, not stale value.
        boolean retryAccepted =
                service.compareAndSetIncrementOnce(
                        id, () -> { });

        assertThat(retryAccepted).isTrue();
        assertThat(repository.value(id)).isEqualTo(2);
    }

    @Test
    void singleThreadBaselineDoesNotRevealRace() {

        service.unsafeIncrement(id, () -> { });
        service.unsafeIncrement(id, () -> { });

        assertThat(repository.value(id)).isEqualTo(2);
    }

    @Test
    void atomicIncrementRejectsMissingCounter() {

        repository.delete(id);

        org.assertj.core.api.Assertions
                .assertThatThrownBy(
                        () -> service.atomicIncrement(id))
                .isInstanceOf(
                        IllegalArgumentException.class)
                .hasMessageContaining("Unknown counter");
    }
}
~~~

### 10.11. Why Isn't This Test Code Itself Flaky Due to Fixtures?

- `@BeforeEach` runs before **each repetition** and creates a new UUID without reusing DB keys across iterations.
- `@AfterEach` deletes only the seeded ID, never wiping the whole table.
- Test methods lack `@Transactional`, so fixtures commit before worker threads run.
- `runTwo` uses a two-thread pool, bounded start gate, and `Future.get`.
- `TwoReaderBarrier` sits after `SELECT` in the **unsafe** and **CAS** paths, forcing identical seen values.
- The SQL atomic update needs no post-read barrier; it protects increments at the SQL statement level.
- `List.of` receives two non-null Booleans, avoiding null-element exceptions.
- Once futures finish, `repository.value` checks the final committed state.
- `finally` cancels/shuts down the executor so no task lingers into cleanup.
- Other test classes use unique IDs and never touch this row.
- Only the deliberate "unsafe final=1" assertion demonstrates the bug; never treat that as desired production behavior.

### 10.12. Outcomes of Each Group

**Unsafe lost update** (12 repetitions):
- Both workers read 0 thanks to the barrier.
- Both `UPDATE` statements wrote 1.
- Final value = 1 instead of 2.
- This is a **red flag intentionally reproduced by the test**; asserting `isEqualTo(1)` makes sense only in a **diagnostic lab**. In production regression tests, expected must be the business invariant 2 and the implementation must be fixed.

**Atomic SQL** (12 repetitions):
- Each `UPDATE value=value+1` increments once.
- The database serializes concurrent updates per statement semantics.
- Final value = 2.
- If the DB is unavailable, deadlocks, or rolls back, the test must fail rather than reporting success.

**CAS** (10 repetitions):
- Both read the same expected value 0.
- One conditional `UPDATE` affects 1 row; the other affects 0 rows.
- No silent lost update; the losing caller gets `false`.
- After retrying with a fresh read, final = 2.
- **Never** use unbounded retry loops in production. Enforce max attempts, backoff, and an error policy under high contention.

**Sequential baseline**:
- Two sequential calls to the unsafe method still yield 2.
- This explains why single-threaded tests miss the race.

**Missing item**:
- The atomic method does not silently PASS when the row is absent; it enforces the exception contract.

### 10.13. OrderIndependentIntegrationTest.java

`src/test/java/com/example/racelab/OrderIndependentIntegrationTest.java`:

~~~java
package com.example.racelab;

import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.MethodOrderer;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestMethodOrder;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@TestMethodOrder(MethodOrderer.Random.class)
class OrderIndependentIntegrationTest {

    @Autowired
    CounterRepository repository;

    @Autowired
    CounterService service;

    private String id;

    @BeforeEach
    void createOwnedFixture() {
        id = "order_" + UUID.randomUUID()
                .toString().replace("-", "");
        repository.insert(id, 0);
    }

    @AfterEach
    void deleteOwnedFixture() {
        repository.delete(id);
    }

    @Test
    void freshFixtureAlwaysStartsAtZero() {
        assertThat(repository.value(id)).isZero();
    }

    @Test
    void independentMethodCanIncrementOwnFixture() {
        service.atomicIncrement(id);
        assertThat(repository.value(id)).isEqualTo(1);
    }

    @Test
    void staleCasDoesNotOverwriteNewerValue() {
        int oldValue = repository.value(id);

        service.atomicIncrement(id);

        int updated = repository.compareAndSet(
                id, oldValue, oldValue + 1);

        assertThat(updated).isZero();
        assertThat(repository.value(id)).isEqualTo(1);
    }

    @Test
    void sequenceWithinSingleMethodIsAValidScenario() {
        // Two inherently ordered operations inside one test.
        service.atomicIncrement(id);
        service.atomicIncrement(id);

        assertThat(repository.value(id)).isEqualTo(2);
    }
}
~~~

Each method seeds and cleans up on its own without `@Order` relying on another method as a prerequisite. Random method ordering can vary freely while every test gets a clean fixture. That is **order independence**.

When you need a "create → update → delete" scenario, put the sequence inside **one test method** (like the last method) or an explicit fixture builder. Never split interdependent steps across three test methods chained with `@Order(1,2,3)`.

### 10.14. SystemPropertyIsolationTest.java

`src/test/java/com/example/racelab/SystemPropertyIsolationTest.java`:

~~~java
package com.example.racelab;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;
import org.junit.jupiter.api.parallel.Resources;

import static org.assertj.core.api.Assertions.assertThat;

class SystemPropertyIsolationTest {

    private static final String KEY =
            "racelab.synthetic.test.flag";

    private void changeAndRestore(String value) {
        String previous = System.getProperty(KEY);

        try {
            System.setProperty(KEY, value);
            assertThat(System.getProperty(KEY))
                    .isEqualTo(value);
        }
        finally {
            if (previous == null) {
                System.clearProperty(KEY);
            }
            else {
                System.setProperty(KEY, previous);
            }
        }

        assertThat(System.getProperty(KEY))
                .isEqualTo(previous);
    }

    @Test
    @ResourceLock(
            value = Resources.SYSTEM_PROPERTIES,
            mode = ResourceAccessMode.READ_WRITE)
    void propertyWriterOneRestoresOriginalState() {
        changeAndRestore("writer-1");
    }

    @Test
    @ResourceLock(
            value = Resources.SYSTEM_PROPERTIES,
            mode = ResourceAccessMode.READ_WRITE)
    void propertyWriterTwoRestoresOriginalState() {
        changeAndRestore("writer-2");
    }
}
~~~

Both methods declare the JUnit resource key for System properties; the engine will not schedule conflicting accesses concurrently. `try/finally` restores state even when an assertion throws. Locks do not replace cleanup, and cleanup does not replace locks when two tests can mutate the same resource simultaneously.

`SystemPropertyIsolationTest` omits `@SpringBootTest` because it tests a pure JVM-global resource. Never boot an `ApplicationContext` just to demonstrate `System.setProperty`.

### 10.15. Running the Project

Requirements: JDK 17+, Maven, and access to Maven repository or local cache.

~~~bash
mvn -q clean test

# Run only race tests, including repeated invocations:
mvn -q -Dtest=CounterRaceIntegrationTest test

# Run order-isolation tests:
mvn -q -Dtest=OrderIndependentIntegrationTest test

# Override seed to reproduce random class/method order:
mvn -q -Djunit.jupiter.execution.order.random.seed=4242026 test

# Shuffle test class order via Maven Surefire:
mvn -q -Dsurefire.runOrder=random test

# Diagnostic reruns: never use to mask failures in CI.
mvn -q -Dsurefire.rerunFailingTestsCount=2 test
~~~

**Expected invocations in the sample suite:**
- `CounterRaceIntegrationTest`: `12 + 12 + 10` repeated invocations plus 2 ordinary tests = **36 test invocations**.
- `OrderIndependentIntegrationTest`: **4** tests.
- `SystemPropertyIsolationTest`: **2** tests.
- Total **42 JUnit invocations** when all tests run under this JUnit/Surefire configuration with zero skips or failure reruns.
- "Unsafe final=1" is asserted deliberately to demonstrate the race; production regression suites must replace it with expected final=2 after fixing.
- Caches/pools/backends share the Spring configuration across classes without colliding on DB keys.
- Surefire reports reside in `target/surefire-reports`.

**Execution QA:** This code is designed to be runnable and reviewed for imports/APIs/logic. **Maven and the 42 invocations were not executed during authoring**, so the outcomes above are expected behavior rather than an observed PASS report.

### 10.16. Running Multiple Seeds in CI

To uncover order-dependent bugs, CI can trigger multiple jobs/runs with seeds like 4242026, 4242027, 4242028 and record the seed used. Each job needs:
- Identical code/commit.
- Identical test subset and dependency versions.
- Known JVM/Surefire fork and parallel settings.
- Reports, logs, and test event IDs.
- Dedicated namespaces for each test data set.

For dozens of runs, orchestrate via CI matrices/driver scripts. Never treat a single passing seed as proof that all permutations are safe.

## 11. Reading Race Condition Traces Systematically

### 11.1. Start with the Invariant

For a counter:
- Given initial = 0.
- When **two independent increments** succeed.
- Then final must = 2.

The bug is the lost update, not merely "two tasks ran at the same time". Define the business invariant before instrumenting.

For inventory:
- Available quantity must never go negative.
- Two orders racing for one remaining item allow only one reservation.

For payments:
- One operation ID must never be captured twice.
- Retrying the same idempotency key returns the same result; conflicting payloads are rejected.

For message consumers:
- Redelivering the same `eventId` must not produce two business effects.
- Offsets/acks must not commit before DB commit when at-least-once semantics apply.

### 11.2. Record an Event Timeline

Log per operation:
- Synthetic operation ID.
- Worker/thread name.
- Before value, after value.
- Transaction ID or correlation ID.
- DB updated row count.
- Start/finish/commit timestamps **for diagnostics, never exact wall-clock assertions**.
- Exception/timeout/rollback status.
- Test random seed, repetition number, concurrent pool size.

Example:

~~~text
case=lost-update seed=4242026 counterId=race_9
A READ 0
B READ 0
A gate passed
B gate passed
B UPDATE 1 affected=1
A UPDATE 1 affected=1
FINAL 1, expected invariant 2
~~~

Log **only after sanitizing sensitive info**. Never write passwords, authorization tokens, or real customer data to test logs. Remember that log line ordering across threads can differ from actual commit order due to buffering.

### 11.3. Use Thread Dumps

When a test hangs:
- Dump stacks of executor worker threads.
- Look for `WAITING` on `CountDownLatch` or `BLOCKED`/lock waits.
- Inspect the transaction connection pool.
- Check deadlock detection logs.
- Check which timeout fired first.

If Worker A holds a row lock waiting for B at a barrier while B waits for the lock to reach the barrier, the bug is in the **test synchronization design**, not necessarily the business algorithm.

### 11.4. Prove Fixes with Negative and Positive Paths

For CAS:
- Two simultaneous updates: one succeeds, one reports conflict.
- Conflicted call retries with a fresh read: final 2.
- No conflict: increment succeeds on first attempt.
- Missing row: handled per contract.
- Retries exceeding budget: explicit failure, no infinite loop.
- Payload/time/restart edge cases when required.

For atomic SQL:
- Both sequential and concurrent.
- N workers yielding final value = N.
- Transaction rollback behavior.
- Database-specific isolation/lock timeouts.
- Production DB integration when critical.

### 11.5. Advanced Considerations: Jepsen / Linearizability

For critical distributed systems, operation histories (invocations/responses) can be checked with linearizability/concurrency model checking or chaos/fault injection. A lab barrier proves one specific interleaving, **not a formal linearizability proof over all execution histories**.

## 12. Do Not Mistake Workarounds for Fixes

### 12.1. `Thread.sleep` Only Alters Probability

~~~java
Thread.sleep(200);
assertThat(counter).isEqualTo(2);
~~~

Adding 200 ms may pass on a laptop and fail on a busy CI runner. It establishes no happens-before guarantee. Use completion signals and concurrency invariants.

### 12.2. Raising Timeouts Never Fixes a Lost Update

If final=1 due to an overwrite, waiting 30 more seconds still yields 1. Timeout tuning applies only to real resource readiness/latency budgets, never broken algorithms.

### 12.3. `synchronized` Does Not Protect Multiple Service Instances

~~~java
public synchronized void increment(String id) { ... }
~~~

Within **one JVM on the same object**, `synchronized` serializes threads; in Kubernetes, two pods have separate objects and monitors while database/Redis/Kafka state remains shared. Use database atomic SQL, pessimistic/optimistic locking, unique constraints, or leases/fencing per requirements.

### 12.4. `volatile` Does Not Make Compound Operations Atomic

`volatile int n` guarantees visibility, not atomicity for `n++`. Use `AtomicInteger` for an in-memory counter or a lock protecting multi-field invariants. Do not confuse this with SQL row concurrency.

### 12.5. `@Transactional` Alone Is Not Enough

A transaction wrapping `SELECT → compute → UPDATE` does not guarantee serializable invariants across all isolation levels and databases. With JPA:
- `@Version` optimistic locking detects conflicts and requires transaction retries.
- `@Lock(PESSIMISTIC_WRITE)` serializes row reads/writes.
- Atomic SQL updates eliminate the lost-update window.
- DB unique indexes/constraints enforce invariants.
- Choose `SERIALIZABLE` isolation when needed, and **handle serialization failures**.

### 12.6. Never Slap `@DirtiesContext` on Every Test

For order dependence caused by global state, `@DirtiesContext` may suppress one symptom while destroying cache reuse, slowing the suite, and still leaving Redis/Kafka/DB residue outside the Spring context. Fix fixtures, state resets, or dedicated resources instead.

### 12.7. Never Use `@Order` to Stabilize Non-Independent Tests

Forcing method A before B may yield a green build, yet running B alone still fails and parallel suites still clash. Merge scenarios when business order is inherent, or make every test establish its own prerequisites.

### 12.8. Never Use Surefire Reruns to Hide Flaky Tests

`rerunFailingTestsCount=2` can help collect evidence, yet fixes nothing and can paint builds green despite initial failures. On critical modules, configure builds to fail on flakes over budget and report initial failures prominently.

### 12.9. Never Wipe Global DB Tables to "Reset"

If two classes share a database, `DELETE FROM all_records` in Test A breaks Test B. Use unique IDs/tenants/schemas, targeted cleanup, and resource locks only when isolation is truly impossible.

### 12.10. Never Assert Full Lists from Multiple Threads by Insertion Order

A concurrent collection can hold the exact expected elements without guaranteeing order. Any contract requiring ordering must specify the ordering model: per-key, per-partition, monotonic sequence, or total order. Never rely accidentally on thread scheduler interleaving.

## 13. JPA `@Version` and Optimistic Locking in Real Applications

### 13.1. Entity Version Field

A Spring Data JPA app can declare:

~~~java
@Entity
public class InventoryItem {

    @Id
    private Long id;

    @Version
    private long version;

    private int available;

    // constructors/getters/behavior omitted for illustration
}
~~~

This is an **architectural snippet, not a file in the Maven JDBC lab**. `@Version` instructs Hibernate to include the version predicate in `UPDATE`s. When two transactions both read version 0, only one updates cleanly; the other throws an optimistic locking exception at flush/commit.

**Never** catch the exception and treat both operations as successful. To retry, catch at the **outer transaction boundary** and start a new transaction/reload fresh state with bounded attempts.

### 13.2. Pessimistic Locking

~~~java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("select i from InventoryItem i where i.id = :id")
Optional<InventoryItem> findLocked(@Param("id") Long id);
~~~

This snippet requires Spring Data JPA imports and a real repository interface. Locks must be acquired inside a transaction. In a two-worker test:
- Never place a `CountDownLatch` barrier **after Worker A acquires the exclusive lock** expecting Worker B to reach the barrier too.
- Place a start gate before acquiring the lock.
- Assert outcomes after commit.
- Test lock timeouts/deadlocks/retries against the real production DB vendor.

### 13.3. Isolation Levels Differ

`READ_COMMITTED`, `REPEATABLE_READ`, and `SERIALIZABLE` behave differently across database engines. An H2 test can diverge from PostgreSQL/MySQL under concurrent transactions—especially around deadlocks, MVCC, and serialization anomalies. Never claim an H2 pass proves PostgreSQL production guarantees.

### 13.4. CAS in SQL

The lab's query:

~~~sql
UPDATE demo_counters
SET current_value = :next
WHERE counter_id = :id
  AND current_value = :expected;
~~~

detects whether a row changed since it was read. When `affectedRows=0`, either a conflict occurred or the row is missing; query again if the business contract needs to distinguish them. Under high contention, CAS retries can starve; enforce budgets, backoff, and monitoring.

### 13.5. Composite Invariants

An atomic increment on a single row does not enforce invariants spanning **two rows**, such as transferring money from Account A to Account B. That requires an enclosing transaction, concurrency controls over both records, and deadlock handling. Test contention against the real invariant rather than extrapolating from a single-row counter demo.

## 14. Redis, Messaging, HTTP Clients, and External Concurrency

### 14.1. Redis Key Collisions

Two test classes both using `cache:user:42`:
- A sets a value, B reads A's value.
- A calls `FLUSHDB` in teardown, wiping B's fixture.
- TTL tests suffer leaked keys from prior runs.

Use a unique namespace such as `it:<runId>:<testId>:cache:user:42`; clean up only owned prefixes/keys and never wipe a shared Redis instance.

### 14.2. Kafka Groups and Message Redelivery

Two listeners sharing a consumer group split partitions, starving Test B of its message. Committed offsets and broker retention persist across tests. Use unique topics/consumer groups/event IDs, isolate listener lifecycles, await partition assignments/acks, and guard against duplicate side effects. Parallel tests sharing Kafka must verify both data separation and business outcomes.

### 14.3. RabbitMQ Queues

Two tests sharing a queue contend over messages (competing consumers). If fanout is desired, declare separate queues and bindings. Use unique queue/exchange names, explicit cleanup, bounded awaits, and never assume queue depth = 0 before consumers finish.

### 14.4. External HTTP Stubs

With a shared WireMock server, Test A resetting all mappings while Test B sends a request yields 404s or stub mismatches. Options:
- Per-test WireMock instance/port;
- Unique URL path/token/request ID;
- Resource lock when a global stub is mandatory;
- Separate contexts or properly aligned test extension lifecycles.

Never add `@DirtiesContext` just to cure a mock server reset race when the server lives on a separate lifecycle.

### 14.5. Testcontainers Reuse and Schemas

Sharing a PostgreSQL container does not automatically isolate tests. Schemas/test data must be namespaced. Never stop a container before cached Spring clients close. When chaos/stress tests restart DB containers, give them a **dedicated context/container** instead of disrupting the suite's shared infrastructure.

### 14.6. Time and Scheduler Races

`@Scheduled` jobs can fire during test setup/cleanup if scheduling stays enabled. In tests:
- Disable scheduled triggers via profile or inject fake triggers.
- Invoke job logic through its public method directly.
- Use `Clock.fixed` when testing time windows.
- With `@Async`, use completion signals and bounded waits.
- When production requires multi-instance schedulers, test distributed locks/idempotency separately.

## 15. Reading Surefire and CI Results Accurately

### 15.1. PASS After Retries Occurred

Surefire can report a test as flaky when the initial run FAILS and a rerun PASSES. Do not check exit codes alone; inspect:
- XML reports showing initial failures and rerun results.
- Flaky counts.
- Actual invocation counts.
- Recorded seed/parallelism/forks.
- Thread dumps/logs from the initial failure.
- Correlation IDs/test data IDs.
- Docker/DB/runtime versions.

### 15.2. Test Failures with Timeouts

A timeout can stem from:
- Pool size smaller than concurrency.
- Barrier deadlock caused by holding a DB lock.
- External service readiness delays.
- Slow CI resource contention.
- Genuine infinite loops/deadlocks.
- Assertions waiting for an event that was never emitted.

Logging `start gate reached` and `after-read gate reached` with safe test IDs aids triage. Never bump a timeout from 5s to 300s without diagnosing why.

### 15.3. Do Not Confuse Parallelism with Test Counts

`@RepeatedTest(12)` executes 12 invocations from a single source method. Surefire reports represent repetitions via display names. When stress suites span multiple forks, context/container counts also change. Report separately:
- Source methods.
- JUnit test invocations.
- Number of executions/seeds.
- Failures vs flakes vs skips.

### 15.4. Seed Reproducibility Alone Is Insufficient for Real Races

Preserving a seed reproduces JUnit's random ordering. Thread scheduling and DB transaction timing remain nondeterministic. To reproduce races reliably, use explicit barriers/failure gates or a replayable concurrency harness. Never expect `-Dseed=4242026` to trigger the exact same micro-interleaving on every machine.

### 15.5. Reporting Results Accurately

Examples of clear reporting:
- "Randomized order 10 seeds, parallel classes=3, all 42 invocations per run, 0 failures/skips/flakes".
- "Reproduced lost update deterministically 12/12 attempts with forced two-read gate".
- "Atomic SQL fix final count 2 on every 12 attempts".
- "CAS detected conflict in every forced interleaving; after retry final count 2".
- "PostgreSQL Testcontainers confirmation still pending/was run with version X".

These sample sentences with numbers are **report formatting templates**, not claims measured during authoring of this document.

## 16. Investigation Workflow for a Flaky Spring Boot Integration Test

### Step 1 — Narrow the Scope

- Run the failing method alone.
- Run the whole class.
- Run the suite in a fixed order.
- Repeat the class 20–100 times.
- Randomize method order and class order.
- Toggle parallel off and on.
- Record environment details and failure rate.

If it FAILS only after Class A, check state leaks/order dependency. If it FAILS in parallel, check races/shared resources. If it FAILS after 30 minutes, check resource leaks/TTLs/time.

### Step 2 — Identify Shared Mutable Resources

Inventory:
- static fields/singletons.
- Spring cached beans.
- Mockito overrides.
- DB tables/sequences/transactions.
- Redis caches.
- Kafka groups/offsets/topics.
- Files/temp paths.
- System properties/default locale/timezone.
- Web server ports, WireMock stubs.
- Container lifecycles.
- Test executors/thread pools.

For each resource, ask: "Who owns it, who cleans it up, and who might still be using it during cleanup?"

### Step 3 — State the Invariant

Examples: "Two successful increments must yield final=2", "One event ID produces only one durable receipt", "After Test A, all global properties return to previous values", "Each test deletes only its own records".

A failure log alone is insufficient; define an assertable invariant on observed state.

### Step 4 — Force the Interleaving

- Start gate.
- After-read barrier.
- Failure injection at transaction boundaries.
- Controlled Fake Clock.
- Fake external API returning responses gated by a latch.
- Queued test appender/callback capturing completion.

If an interleaving cannot be forced deterministically in a test, label the test as probabilistic stress rather than deterministic race reproduction.

### Step 5 — Fix at the Proper Layer

- Java state: `AtomicInteger`/locks/immutable state.
- DB: atomic SQL, optimistic/pessimistic locking, transaction isolation/unique constraints.
- Broker: idempotent consumers/event IDs/delivery semantics.
- Test fixtures: UUIDs/schemas/targeted cleanup.
- Spring context: minimize shared mutable overrides, avoid careless `@DirtiesContext`.
- Global JVM state: restore + `@ResourceLock`.
- Async: future/latch/condition awaits.

### Step 6 — Guard with a Regression Suite

Maintain:
- A deterministic interleaving test for the fixed bug.
- A randomized-order/parallel suite to catch new dependencies.
- Production-like Testcontainers tests when DB/broker semantics matter.
- Monitoring of test duration and flake counts in CI.

Never keep a permanently "sometimes fails" test without an owner or quarantine policy as an uninvestigated endurance check.

## 17. Quick Troubleshooting

| Symptom | Common Cause | Resolution |
|---|---|---|
| Green alone, red in suite | State leak/order dependency | Randomize order, locate shared fixture |
| Outcome changes with seed | Method/class order dependency | Independent setup/cleanup |
| Enabling parallel breaks DB count | Lost update/unsafe cleanup | Atomic SQL/CAS + unique IDs |
| Two-worker counter ends at 1 | Two `SELECT`s read 0 and overwrite | Read barrier, then fix with atomic/CAS |
| CAS `affectedRows=0` | Concurrent update or missing row | Reload/retry or report conflict |
| `@Transactional` test misses worker row | Test fixture uncommitted/other thread | Seed with explicit commit, remove outer test tx |
| Test rolls back yet DB retains data | Worker thread outside test transaction | Query after workers/explicit cleanup |
| `@DirtiesContext` causes inactive context | One test closed shared cached context | Do not parallelize/isolate |
| `@MockitoBean` stubbing shifts | Shared mock bean/reset in parallel tests | Separate contexts/run sequentially |
| `@ResourceLock` misses external race | Lock coordinates only Jupiter participants | DB/external lock or per-test namespace |
| `@Isolated` still sees duplicate DB rows | Other JVMs/actors and business races | Backend idempotency/transaction control |
| `CountDownLatch` timeout | Worker never reached gate, blocked lock/pool | Thread dump/place gate properly |
| `Thread.sleep` lowers flake rate without fixing | Unsynchronized timing race | Future/latch/barrier |
| Parallel Class A deletes B's data | Global `TRUNCATE`/shared DB | Targeted ID/schema cleanup |
| Kafka message stolen by another test | Shared topic/group/consumer | Unique topic/group/`eventId` |
| Redis test reads stale value | Shared keys/unreset cache | Unique prefix/TTL/cleanup |
| Spring context recreates constantly | Differing profiles/mocks/properties/keys | Inspect cache stats |
| Fork-per-class loses context reuse | JVM static cache doesn't span processes | Adjust Surefire fork policy appropriately |
| `rerunFailingTestsCount` greens the build | Failures reported as flakes | Inspect XML/fail-on-flakes policy |
| Test reports show 0 executed | Skipped tests/discovery mismatch | Check Surefire executed counts |
| H2 test PASSES yet PostgreSQL race FAILS | Different DB isolation/dialect | Testcontainers PostgreSQL |
| Disabling context cache didn't fix bug | Race lives in external data | Fix real resource isolation |
| Deadlock between two-reader gate and row lock | Barrier placed after exclusive lock | Move gate before lock |
| Scheduled job interferes with fixture | Scheduling enabled in test | Disable via profile/manual trigger |
| Negative async test PASSES too early | Worker hasn't finished yet | Await completion/settling contract |
| Suite slows down after isolation changes | Too much `@DirtiesContext`/container restarts | Measure startup/cache hit/miss |

## 18. Exercises

1. Run `CounterRaceIntegrationTest` and explain why the intentionally unsafe increment always yields final 1 when the barrier forces two reads.
2. Remove `TwoReaderBarrier` and repeat 100 times. Observe the difference between probabilistic and deterministic reproduction.
3. Add `Thread.sleep(20)` before `UPDATE` in one branch and explain why that is not a fix.
4. Switch `unsafeIncrement` to `atomicIncrement` and update expected final from 1 to 2 as a production regression test.
5. Add `@Transactional` to the unsafe method, observe H2 behavior, and explain why it is insufficient to claim production isolation guarantees.
6. Write a PostgreSQL Testcontainers variant of the atomic/CAS tests and compare results.
7. Add a JPA `@Version` entity variant testing an optimistic conflict and bounded retry.
8. Add a pessimistic row-lock variant; place the barrier properly so it does not self-deadlock.
9. Test 8 concurrent workers and verify final = 8 with atomic SQL updates.
10. Create a shared `static int` counter, test `++` with a barrier, and fix it with `AtomicInteger`.
11. Use `ConcurrentHashMap.putIfAbsent` for duplicate operation IDs and verify create-once semantics.
12. Add a duplicate payment-like operation with a fake gateway using a stable idempotency key.
13. Add tests with unique per-method IDs and `@AfterEach` targeted cleanup.
14. Replace targeted cleanup with `DELETE FROM demo_counters`, enable class parallelism, and observe cross-contamination risk.
15. Add method A intentionally setting a System property without restoring it, and use random ordering to detect it.
16. Add `@ResourceLock(Resources.SYSTEM_PROPERTIES)` and restore the property in `finally`.
17. Create an `@Isolated` class mutating global JVM locale; compare the overhead.
18. Add `@DirtiesContext` to a class, enable parallelism, and observe cache behavior; never use this setup in a shared production suite.
19. Create a `@RepeatedTest(value=100,failureThreshold=1)` test and explain reporting under concurrent repetitions.
20. Randomize classes/methods via properties and record a failing seed for replay.
21. Run Maven Surefire `runOrder=random` and explain why it does not randomize method order.
22. Enable `rerunFailingTestsCount=2` and inspect Surefire flaky results instead of checking only exit codes.
23. Change JUnit parallel config to concurrent methods and identify which fixtures must change.
24. Write a test using `CompletableFuture`/`Future.get(timeout)` for an async service.
25. Put `@Transactional` on a test, seed a fixture, have a worker thread query it, and explain why data may be invisible.
26. Use `Clock.fixed` to replace wall time in job expiry/retry tests.
27. Use JUnit `RepetitionInfo` to log attempt index and correlation ID in failed run reports.
28. Write a Kafka listener test with unique group/`eventId` preventing redelivery and test order dependence.
29. Write a Redis integration test with unique key prefixes and targeted cleanup.
30. Enable multiple Surefire forks and explain why the static Spring TestContext cache and resource locks do not synchronize cross-JVM.
31. Use a thread dump to diagnose a test stuck at a latch and distinguish it from a DB row lock.
32. Build a resource table for your module: owner, scope, mutability, cleanup, concurrency guard.
33. Write an ADR defining when `@ResourceLock` is permitted vs when per-test DB/schemas are mandatory.
34. Add a CI matrix with at least three seeds and parallelism 1/2/4; log seeds/failures without masking.
35. Expand into a 1,000-operation stress suite tracking deadlock/retry metrics; evaluate risk/latency without claiming linearizability from one test.

## 19. Review Checklist

- [ ] Is the business invariant defined before writing the concurrency test?
- [ ] Are flaky order dependencies distinguished from actual races?
- [ ] Does each test/repetition have an independent fixture?
- [ ] Are `@BeforeEach`/`@AfterEach` independent of method order?
- [ ] Are random method/class orders enabled when testing isolation?
- [ ] Are seeds saved to reproduce failures?
- [ ] Is `@Order` avoided for hiding unintended dependencies?
- [ ] Has the test been run solo, per-class, full-suite, and in parallel?
- [ ] Is `@RepeatedTest` used with proper lifecycle understanding, not confused with Surefire reruns?
- [ ] Does parallel config explicitly set method/class modes and parallelism?
- [ ] Does `@ResourceLock` use consistent keys for global resources?
- [ ] Is `@Isolated` understood to apply only within one engine/JVM?
- [ ] Do you avoid assuming `@ResourceLock` protects Java threads outside JUnit?
- [ ] Are `@DirtiesContext`/`@MockitoBean` shared contexts kept out of uncontrolled parallel runs?
- [ ] Do you avoid treating the Spring context cache as a data reset?
- [ ] Does test-level `@Transactional` avoid masking worker thread visibility/commits?
- [ ] Are `CountDownLatch`/Phasers/barriers placed accurately before/between critical sections?
- [ ] Does every wait/future have a finite timeout?
- [ ] Are executors/tasks shut down/awaited before fixture cleanup?
- [ ] Is `Thread.sleep` avoided for synchronizing business outcomes?
- [ ] Do race tests inspect final durable DB state after worker completion?
- [ ] Is there a negative test for concurrent lost update/retry conflicts?
- [ ] Is the fix at the proper layer: atomic SQL/CAS/JPA `@Version`/locks/idempotency?
- [ ] Are transaction semantics verified against a production-like DB when critical?
- [ ] Are per-test IDs/namespaces and targeted cleanup used instead of global `TRUNCATE`/`FLUSHALL`?
- [ ] Are Kafka topics/groups, Rabbit queues, and Redis keys isolated?
- [ ] Do no test-controlled schedulers/async workers remain running during teardown?
- [ ] Do logs capture safe operation IDs and seeds without secrets/PII?
- [ ] Do Surefire reports confirm full test invocations with no silent skips/flakes?
- [ ] Are CI diagnostic reruns distinguished from real fixes?
- [ ] Is there a CI stress/order matrix fitting the resource budget?
- [ ] Do you avoid claiming all interleavings are proven from a single barrier test?

**Conclusion:** For Spring Boot integration tests, **repetition**, **order shuffling**, and **parallel execution** must work together as three complementary probes. Repetition catches intermittent bugs, random ordering catches hidden fixture/class dependencies, and parallelism catches resource contention; critical races should be forced with barriers to produce reproducible evidence. Once exposed, fix at the **actual shared resource**: transactions/SQL/optimistic locking for DBs, proper synchronization for Java heaps, idempotency for brokers/payments, namespaces and cleanup for test data, and resource locks for JVM-global state. Trustworthy results verify invariants **after all operations finish**, backed by reproduction seeds/traces and regression tests—never a lucky green Maven run or auto-rerun.

## 20. Official Documentation

- JUnit Jupiter 5.12 — Repeated Tests, `RepetitionInfo`, `failureThreshold`: https://docs.junit.org/5.12.0/user-guide/#writing-tests-repeated-tests
- JUnit Jupiter 5.12 — Test Execution Order (`MethodOrderer.Random`, `ClassOrderer.Random`): https://docs.junit.org/5.12.0/user-guide/#writing-tests-test-execution-order
- JUnit Jupiter 5.12 — Parallel Execution and `@ResourceLock`/`@Isolated`: https://docs.junit.org/5.12.0/user-guide/#writing-tests-parallel-execution
- JUnit Jupiter 5.12 — Configuration Parameters: https://docs.junit.org/5.12.0/user-guide/#running-tests-config-params
- JUnit 5 API — `MethodOrderer.Random`, reproducible seed: https://docs.junit.org/5.12.0/api/org.junit.jupiter.api/org/junit/jupiter/api/MethodOrderer.Random.html
- Spring Framework 6.2 — Parallel Test Execution guidelines: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/parallel-test-execution.html
- Spring Framework 6.2 — TestContext Context Caching: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html
- Spring Framework 6.2 — Test-managed Transactions and thread-local/preemptive timeout caveats: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html
- Spring Framework 6.2 — `@Sql` Test Data and Transactions: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/executing-sql.html
- Spring Boot 3.5 — Spring Boot Testing: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 — Testcontainers: https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html
- Maven Surefire — Rerun failing tests: https://maven.apache.org/components/surefire/maven-surefire-plugin/examples/rerun-failing-tests.html
- Maven Surefire — `runOrder` and `forkCount`/`reuseForks`: https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo
- Java SE 17 — `CountDownLatch` Javadoc: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html
- Java SE 17 — `ExecutorService` and `Future`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- PostgreSQL — Transaction Isolation: https://www.postgresql.org/docs/current/transaction-iso.html
- PostgreSQL — Explicit Locking: https://www.postgresql.org/docs/current/explicit-locking.html