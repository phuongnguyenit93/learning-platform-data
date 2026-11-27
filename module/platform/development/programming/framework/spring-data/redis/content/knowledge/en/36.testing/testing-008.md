# Testing Transactions, WATCH, Pipelines, and Lua

When an application uses **Spring Data Redis**, a single `GET` or `SET` succeeding does not prove operations stay consistent under multiple clients, network failures, or concurrency. Redis offers several mechanisms that are easy to confuse:

- **`MULTI`/`EXEC`**: queues multiple commands and executes them sequentially without allowing commands from other clients to interleave during `EXEC` execution.
- **`WATCH`**: adds optimistic locking preconditions to `EXEC`; if a watched key changes, the transaction is aborted before executing the queued commands.
- **Pipeline**: sends multiple commands without waiting for each individual reply, reducing round-trip overhead; **does not implicitly create a transaction**.
- **Lua script**: bundles read–check–write logic into a script that executes atomically with respect to interleaving commands from other clients on the same Redis server, yet **has no automatic rollback on script runtime errors**.

These four mechanisms solve distinct problems. Consequently, a strong test strategy must prove **Redis state after execution**, **outcomes under contention**, **behavior on failure**, and **guarantee boundaries**, rather than merely checking that a Java method throws no exception.

This lesson builds test scenarios using Spring Boot, `RedisTemplate`, `StringRedisTemplate`, `SessionCallback`, JUnit 5, Testcontainers, and Reactor. Examples can be adapted to the Spring Data Redis and Redis server versions in your project.

## 1. Define Exactly What Must Be Proved

Before writing tests, express business invariants as verifiable statements.

Example of a points management app:

```text
Key: points:{user-42}
Initial value: 10

Invariant A:
  When transferring 3 points from wallet A to wallet B,
  no client should observe a state where A was deducted without B being credited
  during the commands of a single EXEC.

Invariant B:
  If two clients concurrently update from version 10,
  one client must detect the conflict and avoid overwriting the other's result.

Invariant C:
  Writing 1,000 cache entries quickly does not require batch-wide transaction atomicity.

Invariant D:
  Checking a limit and incrementing a counter must be atomic;
  two concurrent requests must not both exceed the quota.
```

These four invariants map to different tools:

| Goal | Mechanism to Consider | Key Tests |
|---|---|---|
| Group of commands not interleaved by other clients during `EXEC` | `MULTI`/`EXEC` | Commit, discard, results, and in-transaction errors |
| Detect concurrent modifications to previously read data | `WATCH` + `MULTI`/`EXEC` | Contention between `WATCH` and `EXEC`, aborted transaction |
| Reduce latency when sending independent commands | Pipeline | All results valid, reply ordering, no rollback assumptions |
| Read–check–write in one Redis operation | Lua | Correct output, concurrent contention, script errors |
| Coordinating Redis with SQL transactions | Transaction synchronization/outbox | SQL commit/rollback and post-commit failure window |
| Multiple keys in Redis Cluster | Same hash slot or redesign | `CROSSSLOT`, routing/failover |

**Common mistake:** testing a pipeline of 100 `SET`s succeeding and naming the test `allWritesAreAtomic`. Pipelining only proves batch I/O sending and reply collection, not batch-wide atomicity.

## 2. Distinguish Guarantee Boundaries Before Testing

```text
Single Redis command:
  Command A
  -> processed by Redis as one command

MULTI/EXEC:
  MULTI
  QUEUED A
  QUEUED B
  EXEC -> runs A then B without other client commands interleaving

WATCH + MULTI/EXEC:
  WATCH key
  READ current
  ...
  MULTI
  QUEUED SET
  EXEC -> runs only if watched key remained unmodified

Pipeline:
  send A, B, C back-to-back -> receive replies
  does not inherently prevent other commands from interleaving

Lua:
  EVAL script
  -> multi-command Redis logic executes atomically
     relative to other client commands while the script runs
```

| Property | `MULTI/EXEC` | `WATCH + EXEC` | Pipeline | Lua |
|---|---|---|---|---|
| Reduces round-trips? | Possible depending on command batching | Not the primary goal | **Yes**, primary goal | Yes, consolidates logic server-side |
| Other client commands interleave during execution? | No, between commands executed inside `EXEC` | No, when `EXEC` runs | Possible | No, while the script runs |
| Detects changes between read and write? | No, with `MULTI` alone | **Yes**, for watched keys | No | Can perform checks directly inside the script |
| Rolls back all runtime errors? | **No** | **No** | **No** | **No** |
| Requires same Redis connection for control flow? | Yes | **Yes** | Pipeline manages connection within callback | Single script command |
| Auto-commits alongside PostgreSQL/JPA? | No | No | No | No |
| Safe to retry blindly after write timeout? | No | No | No | No |

From here, every test should state **initial state – action – synchronization point – expected Redis outcome**.

## 3. Keep Test Environments Independent of Production

Use a reproducible test Redis instance, never sharing caches, sessions, or queues with live environments.

Layout:

```text
JUnit 5 / Spring Boot integration test
                 |
                 +--> Spring ApplicationContext
                 |        |
                 |        +--> StringRedisTemplate
                 |        +--> RedisConnectionFactory (Lettuce)
                 |
                 +--> Testcontainers Redis
                          |
                          +--> Database 0 of test container
                 |
                 +--> Independent writer client for WATCH conflict
```

Benefits of Testcontainers:

- Real Redis server, not an in-memory mock guessing all semantics.
- Tests can create keys, `WATCH`, `MULTI`/`EXEC`, and Lua.
- Can configure `maxmemory`, ACLs, or network faults on a **dedicated container**.
- Disposes the container after tests without affecting applications.

### Illustrative Dependencies

```gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-redis")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:testcontainers")

    // Needed only if writing reactive tests:
    testImplementation("io.projectreactor:reactor-test")
}
```

Dependencies/versions may be managed by the Spring Boot BOM. Do not add redundant Redis clients if the starter already uses Lettuce; in `WATCH` tests, open **an independent Lettuce connection** from the existing dependency.

### Starting a Redis Test Container

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest
@Testcontainers
class RedisSemanticsIT {

    @Container
    static final GenericContainer<?> REDIS =
            new GenericContainer<>(
                    DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add("spring.data.redis.port",
                () -> REDIS.getMappedPort(6379));
    }

    // @Autowired StringRedisTemplate redis;
    // Specific tests appear below.
}
```

This is an **integration test skeleton**, not a standalone class with all test methods included. It requires a Spring Boot app/configuration in test scope and working Docker/Testcontainers. The image tag is pinned to prevent uncontrolled changes from `latest`; in real projects, pick a tag/digest matching your production Redis version.

If your Spring Boot version uses a different property prefix, adjust `@DynamicPropertySource` accordingly.

## 4. Isolate Data so Tests Do Not Depend on Each Other

Good tests never rely on leftover keys from previous runs.

Example:

```java
String id = java.util.UUID.randomUUID().toString();
String key = "test:redis:tx:" + id;
```

Use the same prefix for related keys in a scenario and clean up explicitly:

```java
String base = "test:redis:tx:" + id;
String a = base + ":a";
String b = base + ":b";

try {
    // Arrange / Act / Assert
} finally {
    redis.delete(java.util.List.of(a, b));
}
```

Never run `FLUSHDB` or `FLUSHALL` if Redis might be shared with anything outside test scope. With a container strictly dedicated to one suite, container teardown cleans everything, yet namespaced key deletion still aids parallel runs and auditability.

Avoid mistakes that make tests hard to reproduce:

- Calling `Thread.sleep(100)` to “wait for the other thread” without a synchronization point.
- Sharing static keys across parallel tests.
- Failing to reset timeouts/consumer state between scenarios.
- Asserting exact milliseconds on CI runners with variable CPU/network load.
- Checking only thrown exceptions without inspecting Redis data afterward.
- Using mocks to test semantics enforced only by the Redis server.

## 5. Redis Transactions: `MULTI`, `EXEC`, `DISCARD`

Redis transactions use:

```text
MULTI     -> start queuing commands
SET a 1   -> QUEUED
SET b 2   -> QUEUED
EXEC      -> execute queue, return replies
```

Or cancel before execution:

```text
MULTI
SET a 1   -> QUEUED
DISCARD   -> drop queue, do not run SET
```

Essential guarantees:

1. Redis executes commands inside `EXEC` **sequentially without interleaving commands from other clients**.
2. Before `EXEC`, commands sit in the queue without modifying data.
3. `DISCARD` drops previously queued commands.
4. Redis transactions **do not support SQL-style rollbacks** on runtime errors.
5. If the connection drops **before `EXEC` is sent**, queued commands are not committed.
6. If the client loses the reply during/after sending `EXEC`, the outcome from the client's perspective is **uncertain**; never blindly retry all side effects.
7. `WATCH` adds a precondition evaluated at `EXEC`; `MULTI` alone never checks whether another client modified data between reads.

### Testing with Redis CLI

```text
SET test:tx:a old
MULTI
SET test:tx:a new
SET test:tx:b second
EXEC
GET test:tx:a
GET test:tx:b
```

Expected after `EXEC`: `test:tx:a = new`, `test:tx:b = second`.

Try a separate scenario:

```text
SET test:tx:a old
MULTI
SET test:tx:a never
DISCARD
GET test:tx:a
```

Expected: still `old`. Also verify **pre-`EXEC` state** from an independent connection if proving queued commands have not taken effect yet.

## 6. `SessionCallback` Keeps Operations on the Same Connection for Transactions

`RedisTemplate` does not guarantee separate Java calls share the same Redis connection. `MULTI`/`EXEC` and `WATCH` represent connection-scoped state, so Spring Data Redis provides **`SessionCallback`** to run grouped operations inside one session.

Service/test example:

```java
import java.util.List;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;
import org.springframework.data.redis.core.StringRedisTemplate;

public final class RedisTransactionExamples {

    private final StringRedisTemplate redis;

    public RedisTransactionExamples(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<Object> savePair(String keyA, String keyB) {
        return redis.execute(new SessionCallback<List<Object>>() {

            @Override
            @SuppressWarnings({"rawtypes", "unchecked"})
            public List<Object> execute(RedisOperations operations)
                    throws DataAccessException {

                operations.multi();

                try {
                    operations.opsForValue().set(keyA, "A");
                    operations.opsForValue().set(keyB, "B");
                    return operations.exec();
                } catch (RuntimeException error) {
                    try {
                        operations.discard();
                    } catch (RuntimeException cleanupError) {
                        error.addSuppressed(cleanupError);
                    }
                    throw error;
                }
            }
        });
    }
}
```

In these `SessionCallback` examples, raw `RedisOperations` follows the pattern shown in Spring Data Redis reference docs. You can wrap it in project-specific type-safe helpers; the goal here is seeing the exact `multi → queued commands → exec` flow.

`RedisTemplate` deserializes `exec()` replies using matching serializers. Results arrive as `List<Object>` rather than direct return values from individual queued calls.

### Testing a Successful `EXEC`

```java
import static org.assertj.core.api.Assertions.assertThat;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.redis.core.StringRedisTemplate;

class TransactionCases {

    @Autowired
    StringRedisTemplate redis;

    @Test
    void execCommitsAllQueuedWrites() {
        String base = "test:tx:" + UUID.randomUUID();
        String keyA = base + ":a";
        String keyB = base + ":b";

        List<Object> replies =
                new RedisTransactionExamples(redis)
                        .savePair(keyA, keyB);

        assertThat(replies).hasSize(2);
        assertThat(redis.opsForValue().get(keyA)).isEqualTo("A");
        assertThat(redis.opsForValue().get(keyB)).isEqualTo("B");

        redis.delete(List.of(keyA, keyB));
    }
}
```

This illustrative class must run inside an appropriate Spring Test context (e.g., `@SpringBootTest` on the containing class), not as a plain JUnit unit test expecting `@Autowired`. When consolidating into one integration class, place these test methods inside `RedisSemanticsIT` from the setup section.

**What to prove:** not just the `replies` list, but that **both keys actually hold the expected values after `EXEC`**.

## 7. Testing `DISCARD` and Restoring Connection State

`DISCARD` cancels queued commands that have not run. Tests must verify both unchanged data and that the session is not left stuck in transaction state.

Example:

```java
@Test
void discardDoesNotWriteQueuedValue() {
    String key = "test:discard:" + UUID.randomUUID();
    redis.opsForValue().set(key, "before");

    redis.execute(new SessionCallback<Void>() {
        @Override
        @SuppressWarnings({"rawtypes", "unchecked"})
        public Void execute(RedisOperations operations) {
            operations.multi();
            operations.opsForValue().set(key, "should-not-appear");
            operations.discard();
            return null;
        }
    });

    assertThat(redis.opsForValue().get(key))
            .isEqualTo("before");

    // Subsequent commands must run normally after DISCARD.
    redis.opsForValue().set(key, "after");
    assertThat(redis.opsForValue().get(key))
            .isEqualTo("after");
}
```

Emphasize: `DISCARD` is used **before `EXEC`** to cancel the queue. You cannot call `DISCARD` after `EXEC` has already run and expect Redis to revert the result.

### Errors Between `MULTI` and `EXEC`

If Java throws an exception, a Redis command times out, or the client misses a reply between `MULTI` and `EXEC`, the connection may remain in transaction state. Inside `SessionCallback`, perform **best-effort** cleanup with `DISCARD` when appropriate, then rethrow the original error.

Never swallow cleanup errors—they can indicate a broken connection; at minimum attach them as suppressed exceptions or log at the technical layer.

If connectivity drops during `EXEC`, calling `DISCARD` afterward cannot "uncommit" an executed transaction. Distinguish **before sending `EXEC`** from **missing the reply to `EXEC`**.

## 8. Testing Command Errors Inside a Transaction: Do Not Assume Full Rollback

A critical difference from SQL is that Redis does not roll back succeeded commands when another command fails at runtime inside `EXEC`.

Lab example via Redis CLI:

```text
SET test:wrongtype "hello"
MULTI
SET test:tx:ok "written"
LPUSH test:wrongtype "not-a-list"
EXEC
GET test:tx:ok
GET test:wrongtype
```

At `EXEC`, `LPUSH` on a String returns `WRONGTYPE`, yet `SET test:tx:ok written` succeeded. Thus after `EXEC`, `GET test:tx:ok` still returns `written`.

Distinguish:

- **Errors detected while queuing commands** (e.g., protocol syntax errors): Redis flags the transaction as errored and `EXEC` rejects the queue.
- **Runtime errors during `EXEC`** (e.g., `WRONGTYPE`): other valid commands that succeeded are not rolled back automatically.
- **`WATCH` conflict**: `EXEC` returns nil/null and **executes nothing**.
- **`DISCARD` before `EXEC`**: the queue is dropped without execution.

| Scenario | Expectation |
|---|---|
| Two valid `SET`s, `EXEC` | Both are applied |
| `MULTI` → `SET` → `DISCARD` | `SET` is not applied |
| `WATCH`ed key changes before `EXEC` | Entire transaction aborts before execution |
| `EXEC` contains a runtime `WRONGTYPE` | Other valid commands can still take effect |
| Network failure after sending `EXEC` | Caller may not know whether the transaction ran |

**Tests must never assert “`EXEC` threw an error” and assume all keys rolled back.** Inspect every involved key.

## 9. `WATCH`: Optimistic Locking for Check-and-Set

`WATCH` makes `EXEC` conditional on whether watched keys remained untouched.

Workflow:

```text
Client A:
    WATCH account:42
    GET account:42      -> 10
    compute new value   -> 15
    MULTI
    SET account:42 15
    EXEC

Client B might write account:42 between A's GET and A's EXEC.
If modified, A's EXEC is aborted.
```

Redis does not compare “whether the value still equals 10” by text; it tracks **key modifications** after `WATCH`. In modern Redis, key expiration or eviction can also trigger a `WATCH` conflict.

Redis CLI example across **two distinct connections**:

```text
Connection A:
  SET test:watch:key v1
  WATCH test:watch:key
  GET test:watch:key  -> v1

Connection B:
  SET test:watch:key v2

Connection A:
  MULTI
  SET test:watch:key v3
  EXEC  -> nil/null because key was modified

Afterward:
  GET test:watch:key -> v2
```

If B did not modify the key, `EXEC` succeeds and the key becomes `v3`.

### Common Confusions

- `WATCH` must be called **before `MULTI`**; never call `WATCH` after queuing starts.
- `WATCH` binds to a **Redis connection**, not a global Java variable.
- A successful or aborted `EXEC` clears `WATCH` state for that session.
- `UNWATCH` stops watching if you decide not to proceed to `EXEC`.
- Contention aborts the transaction—it does not auto-retry; the application chooses whether to retry or return conflict.
- With multiple watched keys, modifying any one of them aborts `EXEC`.
- If a record can be deleted or expire mid-flight, tests must verify whether that counts as a valid conflict.

## 10. Writing Deterministic `WATCH` Tests with Synchronization Points

Never spawn two threads and call `Thread.sleep(200)` hoping client B writes before A's `EXEC`. Use `CountDownLatch` to enforce exact ordering.

Test sequence:

```text
Thread A                     Thread B
------------------------------------------------
WATCH key
GET key -> "v1"
signal WATCHED
WAIT releaseA
                             await WATCHED
                             SET key "v2"
                             releaseA
MULTI
SET key "v3"
EXEC -> aborted
------------------------------------------------
Final assert: key == "v2"
```

**Critical requirement:** B must use a **genuinely independent Redis connection** from A's `WATCH` connection. Some clients share native connections; if a test misuses a shared connection, contention tests fail to exercise two independent clients.

You can create a separate Lettuce client/connection for B in an integration test:

```java
import io.lettuce.core.RedisClient;
import io.lettuce.core.api.StatefulRedisConnection;

RedisClient external = RedisClient.create(redisUriForTestContainer);

try {
    StatefulRedisConnection<String, String> writer =
            external.connect();
    try {
        writer.sync().set(key, "v2");
    } finally {
        writer.close();
    }
} finally {
    external.shutdown();
}
```

`redisUriForTestContainer` is the test Redis URI built from the Testcontainers host and mapped port. Using a separate client avoids accidentally sharing `WATCH` state with the code under test.

### `WATCH` Example with Latches

```java
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;

CountDownLatch watched = new CountDownLatch(1);
CountDownLatch resume = new CountDownLatch(1);

// Run this block on worker thread A.
List<Object> outcome = redis.execute(
        new SessionCallback<List<Object>>() {

    @Override
    @SuppressWarnings({"rawtypes", "unchecked"})
    public List<Object> execute(RedisOperations ops) {
        ops.watch(key);

        try {
            String old = (String) ops.opsForValue().get(key);
            watched.countDown();

            // Test driver B awaits WATCHED, writes v2 on a separate connection,
            // and then calls resume.countDown().
            if (!resume.await(5, TimeUnit.SECONDS)) {
                ops.unwatch();
                throw new IllegalStateException(
                        "Timeout waiting for competing writer");
            }

            ops.multi();
            ops.opsForValue().set(key, old + "-A");
            return ops.exec();
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            ops.unwatch();
            throw new IllegalStateException(ex);
        } catch (RuntimeException ex) {
            // Perform best-effort cleanup per session state.
            throw ex;
        }
    }
});
```

This illustrates **thread A's logic**, not the complete coordinating test. The JUnit test submits this via `ExecutorService`/`Future`, awaits `watched.await(...)`, lets B write `v2` over a separate connection before calling `resume.countDown()`, and finally awaits the Future and asserts:

```java
assertThat(outcome).isNull(); // EXEC aborted by WATCH
assertThat(redis.opsForValue().get(key)).isEqualTo("v2");
```

If a Redis API/driver returns a different representation for aborted `EXEC`, follow your version's contract; in the Redis protocol, `EXEC` returns nil/null on `WATCH` abort.

Tests also need Future timeouts and `finally` cleanup so latches/threads never hang if an assertion fails. In production code, clean up with `UNWATCH` if aborting before `MULTI`, and `DISCARD` if `MULTI` started without `EXEC`.

## 11. Testing `WATCH` Without Contention

Alongside negative tests, include a positive path.

Example:

```java
String key = "test:watch:" + java.util.UUID.randomUUID();
redis.opsForValue().set(key, "10");

List<Object> result = redis.execute(
        new SessionCallback<List<Object>>() {

    @Override
    @SuppressWarnings({"rawtypes", "unchecked"})
    public List<Object> execute(RedisOperations ops) {
        ops.watch(key);
        String current = (String) ops.opsForValue().get(key);
        int next = Integer.parseInt(current) + 1;

        ops.multi();
        ops.opsForValue().set(key, Integer.toString(next));
        return ops.exec();
    }
});

assertThat(result).hasSize(1);
assertThat(redis.opsForValue().get(key)).isEqualTo("11");
```

If testing **counter increments**, Redis already has atomic `INCR`, which usually fits better than `WATCH + GET + SET`. `WATCH` shines when business conditions are complex or multiple keys must be checked before committing.

### `WATCH` and TTL

A `WATCH`ed key can expire or be evicted before `EXEC`, aborting the transaction. Tests should use a Redis version matching the production contract and never assume “only another Java writer causes conflicts.”

If tests use keys close to expiration, timing can make results flaky. To test expiration intentionally, use a dedicated scenario with a short TTL and clear synchronization; never accidentally apply short TTLs to `WATCH`ed keys in basic concurrency tests.

## 12. Retrying `WATCH` Conflicts Must Be Bounded

A `WATCH` conflict is an **expected outcome** under concurrent contention, not necessarily a system error.

CAS loop pattern:

```text
attempt = 1..maxAttempts:
    WATCH key
    read current
    validate business condition
    MULTI
    queue update
    EXEC
    if succeeded -> return success
    if conflict  -> short backoff, re-read, and retry
exhausted attempts -> return conflict/overload per contract
```

Tests needed:

1. Single uncontended client: succeeds immediately.
2. Two clients updating from the same version: one succeeds, one aborts and retries.
3. Continuous heavy contention across many clients: never loops forever.
4. Key deleted or expired during `WATCH`: handles conflict properly.
5. Business condition becomes false after retry: returns rejection without forcing writes.

Avoid long sleeps/backoffs while holding a `WATCH`ed Redis connection open unnecessarily. Typically, exit the session on conflict and back off before starting a fresh attempt.

For simple conditions, prefer atomic Redis commands (`INCR`, `SET NX`, `HINCRBY`, ...) or Lua to avoid `WATCH` retry loops.

## 13. Spring `@Transactional` Differs from Redis `MULTI/EXEC` in Tests

A `@Transactional` method is often managed by `JpaTransactionManager` or `DataSourceTransactionManager`. **It does not automatically make `RedisTemplate` use Redis transactions.**

Spring Data Redis lets you enable transaction support per template:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration
public class RedisTxTestConfiguration {

    @Bean("transactionalRedisTemplate")
    StringRedisTemplate transactionalRedisTemplate(
            RedisConnectionFactory factory) {

        StringRedisTemplate template =
                new StringRedisTemplate(factory);

        template.setEnableTransactionSupport(true);
        return template;
    }
}
```

When an active Spring-managed transaction and transaction synchronization are present, template write commands can be queued for `EXEC` upon Spring transaction commit or `DISCARD` upon rollback. Read-only commands inside the transaction may route through a separate connection to return immediate values.

### Recommended Test Matrix

| Scenario | Expectation |
|---|---|
| `enableTransactionSupport` disabled | Redis writes execute immediately without waiting for SQL commit |
| Support enabled + Spring transaction commits | Queued Redis writes execute on commit per supported lifecycle |
| Support enabled + Spring transaction rolls back | Queued Redis writes are discarded |
| Reading a key just `SET` before transaction commits | Do not assume the queued write is visible yet |
| SQL commits, Redis `EXEC` fails | SQL does not auto-rollback; requires repair/reconciliation |
| Method calls itself (*self-invocation*) | `@Transactional` proxy may not apply as expected |
| Test method has default `@Transactional` rollback | After-commit paths may never run, invalidating the test |

### Using `TransactionTemplate` for Explicit Commit and Rollback Control

Assuming the test context already provides a `PlatformTransactionManager` for a test database:

```java
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

TransactionTemplate tx =
        new TransactionTemplate(transactionManager);

tx.executeWithoutResult(status -> {
    transactionalRedisTemplate.opsForValue()
            .set(key, "committed");
});

assertThat(redis.opsForValue().get(key))
        .isEqualTo("committed");
```

Testing rollback:

```java
redis.opsForValue().set(key, "before");

assertThatThrownBy(() ->
        tx.executeWithoutResult(status -> {
            transactionalRedisTemplate.opsForValue()
                    .set(key, "should-not-commit");
            throw new IllegalStateException("force rollback");
        })
).isInstanceOf(IllegalStateException.class);

assertThat(redis.opsForValue().get(key))
        .isEqualTo("before");
```

`assertThatThrownBy` comes from AssertJ. This snippet assumes `transactionManager`, `transactionalRedisTemplate`, and `redis` are injected; do not build a fake transaction manager just to test Redis `MULTI/EXEC`.

**Important:** Spring tests often auto-rollback at the end when the test method itself carries `@Transactional`. To test `AFTER_COMMIT` callbacks, complete a **real** commit using `TransactionTemplate` or explicit test transaction management and assert **after commit**. Never place commit assertions inside an unfinished test transaction.

## 14. What `@Transactional` Does Not Guarantee

```text
SQL transaction           Redis transaction/callback
-----------------------   ---------------------------
BEGIN
UPDATE orders
COMMIT  ----------------> Redis EXEC/evict callback
                               |
                               +--> Redis may fail/timeout
```

Even with Redis transaction support enabled, there is no default **XA two-phase commit** binding SQL and Redis together.

Therefore, test:

1. Database commit succeeds.
2. Simulate Redis unavailable right during post-commit synchronization.
3. Verify the database **committed**.
4. Verify Redis does not yet reflect the change or the callback failed.
5. Verify reconciliation, retry, or transactional outbox mechanisms if required by the business.

Never blindly retry the entire SQL transaction after a cache callback failure: it can duplicate business data.

## 15. Pipelines: I/O Optimization, Not Atomic Transactions

Sequential synchronous Redis commands pay multiple round-trip waits:

```text
Client: SET k1 -> wait for reply
Client: SET k2 -> wait for reply
Client: SET k3 -> wait for reply
```

Pipelining dispatches commands without waiting for each reply individually:

```text
Client: SET k1
        SET k2
        SET k3
          |
          v
Redis processes, returns replies in command order
          |
          v
Client collects pipeline results
```

Pipelining cuts round-trip overhead significantly for batches of independent commands. However:

- It does not prevent Redis from processing commands from other clients **between** pipelined commands.
- One failed command does not undo earlier succeeded pipeline commands.
- Each command still produces its own reply type.
- Pipeline connections must be closed/flushed properly.
- Redis Cluster imposes per-slot/node routing restrictions depending on driver/commands.
- Performance measurements must account for serialization costs, reply-list memory, and batch size.

## 16. Spring Data Redis `executePipelined`

Spring Data Redis provides `RedisTemplate.executePipelined(...)` accepting a `RedisCallback` or `SessionCallback` to batch commands.

Example:

```java
import java.util.List;
import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;

public List<Object> writeAndReadPipeline(
        String keyA, String counterKey) {

    return redis.executePipelined(
            new SessionCallback<Object>() {

        @Override
        @SuppressWarnings({"rawtypes", "unchecked"})
        public Object execute(RedisOperations ops) {
            ops.opsForValue().set(keyA, "A");
            ops.opsForValue().increment(counterKey);
            ops.opsForValue().get(keyA);

            // The executePipelined callback must return null.
            return null;
        }
    });
}
```

**Why must the callback return `null`?** Direct callback return values are discarded; the actual return value is the `List<Object>` holding replies for all pipelined commands.

Spring Data Redis deserializes pipeline replies using matching serializers. With `StringRedisTemplate`, returned string values are Strings; numeric replies remain numbers or command-appropriate types.

### Testing Pipeline Results

```java
@Test
void pipelineReturnsRepliesAndPersistsCommands() {
    String base = "test:pipe:" + UUID.randomUUID();
    String keyA = base + ":a";
    String counter = base + ":counter";

    List<Object> replies =
            writeAndReadPipeline(keyA, counter);

    assertThat(replies).hasSize(3);
    assertThat(replies.get(2)).isEqualTo("A");

    assertThat(redis.opsForValue().get(keyA)).isEqualTo("A");
    assertThat(redis.opsForValue().get(counter)).isEqualTo("1");
}
```

If the application uses another serializer, adjust expected reply types rather than forcing everything to String.

**Never assert the immediate return value of `opsForValue().get` inside the pipeline callback.** In pipeline mode, command results are collected into the reply list once the pipeline completes, not returned synchronously inline.

## 17. Testing That Pipelines Are Not Atomic

A negative test should prove **pipelines do not roll back valid commands** when another command errors.

Conceptual test:

```text
Setup:
  SET test:pipeline:wrongtype "string-value"

Inside pipeline:
  SET test:pipeline:ok "written"
  LPUSH test:pipeline:wrongtype "x"  -> WRONGTYPE
  SET test:pipeline:later "maybe"

After pipeline finishes/errors:
  Verify test:pipeline:ok was written.
  Observe the reply/error for LPUSH.
  Check test:pipeline:later per driver and server behavior.
```

Some driver/template versions throw an exception while collecting pipeline replies; do not assume every error returns a three-element `List`. The vital takeaway is that **operations processed by Redis before the error are not undone**.

### Testing Interleaving with Another Client

To demonstrate that pipelines are **non-atomic**, use server-side instrumentation or controllable scheduling between commands. Avoid “loop 100,000 times hoping to hit an interleave” as primary evidence; it creates flaky tests.

When a group of commands must never interleave, use `MULTI/EXEC` or an appropriate Lua script instead of a bare pipeline.

## 18. Pipelining Does Not Mean Unbounded Batches

A pipeline packing millions of commands/replies inflates client and server memory, monopolizes the connection, spikes latency for other clients, or fails under network backpressure.

Test characteristics such as:

- Batch sizes of 100, 1,000, and 5,000 in an appropriate benchmark setup.
- Value sizes from tiny up to near-production payloads.
- Correctness before measuring latency.
- p95/p99 tail latency, not just average total time.
- Large memory allocations for reply lists.
- Impact when a command fails mid-batch.
- Behavior under multiple concurrent clients.
- Timeout/retry safety against duplicate side effects.

The right performance question is not “is pipelining always 10x faster?” but “for our actual command mix, batch size, and network latency, how much throughput does pipelining gain while preserving semantics and resource limits?”

## 19. Do Not Mix Pipeline and `MULTI/EXEC` Semantics Arbitrarily

Pipelines and transactions can be combined in specialized scenarios (e.g., sending `MULTI`, queued commands, and `EXEC` in a single flush) when supported by the driver/framework.

In Spring Data Redis testing, keep them distinct:

- `executePipelined` returns pipeline replies across potentially mixed result types.
- `execute(SessionCallback)` with `multi/exec` returns Redis transaction results.
- Calling `multi()` inside a pipeline alters reply shapes and connection state; you cannot apply plain pipeline assertions without understanding transaction replies.
- Enqueue errors and `EXEC` errors have different semantics than plain pipeline errors.
- Using `executePipelined(SessionCallback)` does not automatically wrap commands inside a transaction.

If the problem requires atomicity, write a dedicated transaction test first; if extra throughput is needed later, evaluate pipeline+transaction intentionally. Never call `executePipelined` simply to get “multiple atomic commands.”

## 20. Lua: Bundling Read–Check–Write into One Redis Operation

When an app must check a condition and update a key, Lua eliminates the race window present in `GET → Java logic → SET`.

Example **compare-and-set** rule:

```text
If current key equals expected:
    write newValue
    return 1
Otherwise:
    keep unchanged
    return 0
```

Lua script:

```lua
-- KEYS[1] = key to CAS
-- ARGV[1] = expected value
-- ARGV[2] = new value

local current = redis.call('GET', KEYS[1])

if current == ARGV[1] then
    redis.call('SET', KEYS[1], ARGV[2])
    return 1
end

return 0
```

Redis runs the script atomically relative to other clients' commands during execution. Two clients racing to CAS `v1` to different values cannot **both** observe `v1` and overwrite each other.

Never confuse “Lua is atomic” with “Lua scripts always roll back on errors.” If a script writes a key and then hits a runtime error later, prior writes are not automatically undone.

## 21. Running Lua in Spring Data Redis with `DefaultRedisScript`

`DefaultRedisScript<T>` wraps script text/resources and result types. Declare it as a **singleton bean** to avoid recomputing SHA1 hashes unnecessarily.

Example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.data.redis.core.script.RedisScript;

@Configuration
public class RedisScriptConfiguration {

    @Bean
    public RedisScript<Long> compareAndSetScript() {
        String lua =
                "local c = redis.call('GET', KEYS[1]); " +
                "if c == ARGV[1] then " +
                "  redis.call('SET', KEYS[1], ARGV[2]); " +
                "  return 1; " +
                "end; return 0;";

        DefaultRedisScript<Long> script =
                new DefaultRedisScript<>();
        script.setScriptText(lua);
        script.setResultType(Long.class);
        return script;
    }
}
```

Service calling the script:

```java
import java.util.List;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Service;

@Service
public class CompareAndSetService {

    private final StringRedisTemplate redis;
    private final RedisScript<Long> cas;

    public CompareAndSetService(
            StringRedisTemplate redis,
            RedisScript<Long> cas) {
        this.redis = redis;
        this.cas = cas;
    }

    public boolean update(
            String key, String expected, String replacement) {

        Long changed = redis.execute(
                cas,
                List.of(key),
                expected,
                replacement);

        return Long.valueOf(1L).equals(changed);
    }
}
```

`StringRedisTemplate` uses matching string serialization for keys and arguments in this example. If a template uses binary/JSON serializers, a Lua string comparison may not match the wire format.

Spring Data Redis's script executor typically attempts `EVALSHA` to leverage the server script cache and falls back to `EVAL` if the script is not yet cached. You do not need to hand-roll SHA1 invocation logic for basic use cases.

## 22. Lua Tests: Matching and Non-Matching Preconditions

Positive path test:

```java
@Test
void casUpdatesOnlyWhenExpectedValueMatches() {
    String key = "test:cas:" + UUID.randomUUID();
    redis.opsForValue().set(key, "v1");

    boolean changed =
            casService.update(key, "v1", "v2");

    assertThat(changed).isTrue();
    assertThat(redis.opsForValue().get(key))
            .isEqualTo("v2");
}
```

Negative path test:

```java
@Test
void casDoesNotUpdateWhenExpectedValueDiffers() {
    String key = "test:cas:" + UUID.randomUUID();
    redis.opsForValue().set(key, "v2");

    boolean changed =
            casService.update(key, "v1", "v3");

    assertThat(changed).isFalse();
    assertThat(redis.opsForValue().get(key))
            .isEqualTo("v2");
}
```

Assert **both the return value and the Redis state**. Asserting only `false` without reading the key back fails to prove the script avoided side effects.

## 23. Lua Concurrency Test: Two Clients, Only One Winner

With initial value `v1`, two clients concurrently request:

```text
A: CAS(v1 -> v2)
B: CAS(v1 -> v3)
```

Expectations:

- Total successes equal **1**.
- Final value is `v2` or `v3`, matching the winner.
- Never a mixed state or both winning.
- Losing client gets `0`/false without overwriting the winner.

Pseudo-test with latches:

```java
String key = "test:cas:race:" + UUID.randomUUID();
redis.opsForValue().set(key, "v1");

CountDownLatch release = new CountDownLatch(1);

Future<Boolean> left = executor.submit(() -> {
    release.await();
    return casService.update(key, "v1", "v2");
});

Future<Boolean> right = executor.submit(() -> {
    release.await();
    return casService.update(key, "v1", "v3");
});

release.countDown();

boolean a = left.get(5, TimeUnit.SECONDS);
boolean b = right.get(5, TimeUnit.SECONDS);

assertThat((a ? 1 : 0) + (b ? 1 : 0))
        .isEqualTo(1);

assertThat(redis.opsForValue().get(key))
        .isIn("v2", "v3");
```

This shows the test body; `executor` requires an `ExecutorService` with at least two worker threads and cleanup in `finally`. A single-threaded executor would pass CAS logic sequentially without testing real concurrency.

Redis executes Lua scripts sequentially, so tests do not seek interleaving *inside* a script. The goal is having two clients compete from the **same expected value**.

## 24. Testing Lua Runtime Errors: Atomic Does Not Mean Rollback

Example script intentionally failing **after** a write:

```lua
redis.call('SET', KEYS[1], 'written')
redis.call('LPUSH', KEYS[2], 'x')
return 1
```

If `KEYS[2]` is already a Redis String, `LPUSH` triggers `WRONGTYPE`. `KEYS[1]` **can still hold `'written'`**, because Redis does not roll back commands executed before the runtime error.

To verify in a lab:

1. Use a mutable test key for `KEYS[1]`.
2. Pre-populate `KEYS[2]` as a String to force `WRONGTYPE`.
3. Execute the script via a matching template/script executor.
4. Capture the Spring Data Redis exception.
5. Read `KEYS[1]` again and observe the pre-error write persisted.
6. Never assume the script rolled back simply because the client threw an exception.

**Safe script design:** validate types and preconditions before writing if partial effects from runtime errors must be avoided; keep scripts short, with explicit branches and input validation.

### Redis Cluster and Lua Keys

Every Redis key accessed by a script must be passed via `KEYS` and obey Redis Cluster hash-slot rules. For example:

```text
test:lua:{account-42}:balance
test:lua:{account-42}:version
```

Both keys share the same hash tag and slot. Standalone Redis tests cannot detect `CROSSSLOT`; if deploying to Cluster, run dedicated tests against a real Redis Cluster.

## 25. Testing the Script Cache and `NOSCRIPT`

Redis maintains a script cache. Spring Data Redis computes script SHA1 hashes, normally tries `EVALSHA`, and falls back to `EVAL` when the script is missing from the server cache.

Integration test scenario:

1. Run `compareAndSetScript` the first time against the container.
2. Run the script again with another key.
3. On a **dedicated lab Redis**, clear the script cache if testing `NOSCRIPT`.
4. Invoke the script again via Spring Data Redis.
5. Verify it still returns the expected result and updates the key.
6. Observe exceptions if a configuration/driver disables the assumed fallback.

In Redis CLI, `SCRIPT FLUSH` mutates node-level script cache, so **never run it on production to test**. On Redis Cluster, script caches across multiple nodes must also be accounted for per Redis version and deployment mechanics.

Do not assert “always uses `EVALSHA`” as a brittle performance assumption if you do not control script cache lifecycles; assert the script's **business outcome** and monitor performance separately.

## 26. Lua Cannot Perform Side Effects Outside Redis

Lua inside Redis runs Redis commands using server scripting facilities; it cannot open network sockets, access filesystems, or call external databases.

Therefore, you cannot write a Redis script to atomically execute:

```text
UPDATE PostgreSQL
SET Redis key
Publish HTTP message
```

as if Redis Lua were a distributed transaction coordinator. If PostgreSQL is the source of truth and Redis is a cache, use patterns like outbox, post-commit invalidation, versioning, or reconciliation.

A Redis error after SQL commit never rolls back SQL. This is an essential integration scenario when workflows span multiple resources.

## 27. Reactive Redis: Testing with `StepVerifier`

`ReactiveRedisTemplate` and `ReactiveStringRedisTemplate` return Reactor publishers. In reactive code, **creating a publisher without subscribing sends no Redis commands**.

Example reactive Lua execution given an existing `RedisScript<Long>`:

```java
import java.util.List;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;
import reactor.core.publisher.Flux;

public Flux<Long> reactiveCas(
        ReactiveStringRedisTemplate redis,
        RedisScript<Long> script,
        String key,
        String expected,
        String replacement) {

    return redis.execute(
            script,
            List.of(key),
            List.of(expected, replacement));
}
```

Exact method overloads depend on your Spring Data Redis version; script execution returns `Flux<T>` in reactive scripting.

Use `StepVerifier` to subscribe and assert:

```java
import reactor.test.StepVerifier;

StepVerifier.create(reactiveCas(
        reactiveRedis,
        casScript,
        key,
        "v1",
        "v2"))
        .expectNext(1L)
        .verifyComplete();
```

If the key is missing or expected does not match, the script emits `0L` per definition.

### Testing Errors in Reactive Pipelines

If Redis disconnects or rejects the script, the publisher emits `onError`. `Mono.empty()`/`Flux.empty()` does not represent timeouts or server failures. Never use `onErrorResume(ex -> Mono.empty())` and treat the test as “passing because no value arrived,” unless business rules explicitly endorse that fallback.

In WebFlux, avoid `block()` on event-loop threads; `StepVerifier` runs on the test thread to verify publishers, not as a pattern for production services.

## 28. How Does Redis Cluster Affect Tests?

Standalone Testcontainers Redis verifies `MULTI/EXEC`, `WATCH`, pipelines, and Lua semantics **on a single node**. Production deployments using Redis Cluster have additional constraints:

- Keys in transactions or scripts must satisfy hash-slot rules.
- Multi-key commands spanning different slots fail with `CROSSSLOT`.
- Multi-key pipelines depend on slot routing and driver support; do not assume all commands travel over one connection like standalone.
- Failover/resharding can trigger `MOVED`/`ASK`, timeouts, or slot-map invalidation.
- Standalone tests never prove retry/connection behavior during Cluster primary switches.
- Reading from replicas can observe stale data due to asynchronous replication.

Naming keys for the same entity:

```text
test:transfer:{account-42}:balance
test:transfer:{account-42}:audit
```

Both keys share hash tag `{account-42}`, mapping to the same slot.

To verify Cluster support:

1. Provision a test Redis Cluster with multiple primaries.
2. Run `WATCH`/Lua tests using co-located same-slot keys.
3. Execute a multi-key command across distinct slots and assert the expected error.
4. Perform failover/resharding in the lab cluster—never production.
5. Verify the application recovers/routes via the driver without violating business invariants.

Never include role/slot-mutating admin commands in tests hitting any shared Redis.

## 29. Network Failures, Timeouts, and Uncertain Outcomes

Happy-path-only tests miss the most dangerous failure mode:

```text
Client sends EXEC / EVAL / INCR
           |
           v
Redis executes the command
           |
           v
Network drops before reply reaches client
           |
           v
Client times out, unsure whether command ran
```

In this situation:

- `GET` can be retried according to read policy.
- Blindly retrying `INCR` can increment twice.
- A side-effecting Lua script may have completed even though the caller timed out.
- `EXEC` may have committed even though the client lost the reply.
- A pipeline may have executed **part or all** of its commands before disconnecting, depending on timing.
- `WATCH` is not an idempotency mechanism across retries.

### Fault-Injection Scenario

In a test environment:

1. Place a network proxy capable of cutting connectivity between the app and Redis.
2. Send a side-effecting command so it reaches the server without returning a reply.
3. Cut the connection at a controlled point.
4. Observe the caller's error/timeout.
5. Inspect Redis state via an independent admin connection.
6. Assert whether the retry policy avoids duplicate side effects.
7. When business logic requires exactly-once outcomes, enforce operation IDs/idempotency records in an authoritative store.

A fault proxy may not always hit the exact window between Redis execution and client reply receipt; use instrumentation or test doubles at the exact boundary when needed rather than claiming “proven lost reply after commit” from randomly killing a container.

## 30. Assert the Right Result Types and Serializers

Spring Data Redis serializes values as Strings, JDK objects, or JSON. Results from `exec()` and `executePipelined()` are deserialized using the template's serializers.

Common differences:

| Operation | Typical Return | What to Check |
|---|---|---|
| `SET` | Boolean/status or matching reply type | Do not blindly compare to String `"OK"` |
| `INCR` | `Long` | Do not treat numbers as Strings when checking replies |
| `GET` | Deserialized value | Key/value serializer compatibility |
| `HGET` | Hash value serializer | Do not confuse with plain value serializer |
| `MULTI/EXEC` | `List` of replies or nil on abort | `WATCH` conflict vs. `EXEC` success |
| `executePipelined` | `List` of replies in command order | Callback must return `null` |
| Lua returning `1`/`0` | `Long` when script result type is `Long` | Script result type and serializer |
| Lua returning boolean | `Boolean` when script result type is `Boolean` | Do not assume raw Redis reply types |
| Reactive script | `Flux` of script results | Requires subscription |

For example, if Java expects a JSON DTO while the Redis key holds a plain string, a decode failure is not proof that the Redis transaction failed. In tests, use `StringRedisTemplate` for transparent wire formats, plus dedicated tests for custom application serializers.

## 31. Recommended Test Matrix

| ID | Mechanism | Arrange/Act | Minimum Assertions |
|---|---|---|---|
| TX-01 | `MULTI/EXEC` | Queue 2 `SET`s then `EXEC` | Both keys match after `EXEC`; replies match |
| TX-02 | `DISCARD` | Queue `SET` then `DISCARD` | Key keeps old value |
| TX-03 | Pre-`EXEC` | Queue `SET`, read from another connection | Other connection does not see the write yet |
| TX-04 | Runtime error | Valid `SET` + `WRONGTYPE` inside `EXEC` | Valid `SET` can still persist |
| TX-05 | Connection cleanup | Error between `MULTI` and `EXEC` | Session cleaned up or connection not reused in dirty state |
| WATCH-01 | No conflict | `WATCH`, read, `MULTI`, `EXEC` | Succeeds, key holds new value |
| WATCH-02 | Conflict | B writes between A's `WATCH` and `EXEC` | A's `EXEC` aborts, B's value stays intact |
| WATCH-03 | Bounded retry | Multiple competing clients | No infinite loop, conflicts handled cleanly |
| WATCH-04 | Key expiration | `WATCH` key then key expires | Conflict handled per Redis version/contract |
| PIPE-01 | Pipeline happy path | `SET`, `INCR`, `GET` | Ordered reply list and final Redis state match |
| PIPE-02 | Callback return | Callback returns non-null | Test catches violated `executePipelined` contract |
| PIPE-03 | Partial failure | `WRONGTYPE` mid-batch | No assumption of rollback |
| PIPE-04 | Batch size | Bounded large command batch | Data intact, latency/memory measured |
| LUA-01 | CAS success | Expected matches | Script returns 1, key updated |
| LUA-02 | CAS rejection | Expected differs | Script returns 0, key unchanged |
| LUA-03 | Concurrent CAS | Two clients with same expected | Exactly one succeeds |
| LUA-04 | Runtime error | Script writes then hits `WRONGTYPE` | Distinguishes atomicity from rollback |
| LUA-05 | Script cache | Script flushed in lab | Executor falls back, result stays accurate |
| CLUSTER-01 | Same slot | Multi-key Lua/transaction | Succeeds per slot contract |
| CLUSTER-02 | Cross-slot | Multi-key across different slots | Error classified, not blindly retried |
| FAIL-01 | Timeout after write | Reply dropped | Retry causes no duplicate side effects |
| SQL-01 | Spring commit/rollback | `TransactionTemplate` and Redis tx support | Post-commit/rollback states match |
| SQL-02 | Redis fails after SQL commit | Simulate callback failure | SQL remains committed, repair path runs |

**Final check:** run each test at the right level (unit, integration, concurrency, fault injection) instead of dumping everything into one JUnit class with a single opaque timeout.

## 32. Benchmarking Pipelines and Lua Without Compromising Correctness

Measure performance only after correctness suites pass using realistic data and serializers.

A benchmark plan:

1. Prepare a dedicated lab Redis and fixed dataset.
2. Warm up JVM, connections, and serializers.
3. Measure `n` sequential `SET` operations.
4. Measure `executePipelined` with the same command count and sensible batch sizes.
5. If check–write logic is needed, benchmark the `WATCH` loop against the equivalent Lua script.
6. Measure p50/p95/p99 latency, throughput, CPU, and memory.
7. Run with multiple clients to observe contention.
8. Verify every final Redis value after the benchmark.
9. Test over realistic network latency rather than loopback alone.
10. Never compare a “write-only” pipeline against a “read, validate, retry” `WATCH` loop as if they shared identical semantics.

A benchmark claiming “pipelines are X times faster” means nothing without stating command count, payload size, network latency, Redis version, whether replies were deserialized, and concurrency level.

## 33. Debugging Failed Tests

### 33.1. `exec()` Returns `null` When Expected to Succeed

Likely causes: `WATCH` conflict, key expiration/eviction, or another thread mutating the key. Use unique keys, log `WATCH`/`EXEC` timestamps, keep TTLs stable, and ensure no background job touches the test namespace.

### 33.2. `GET` Inside `MULTI` Returns `null`

Inside a transaction, commands are queued and some methods immediately return `null` instead of real data. Never treat that temporary `null` as an executed read. To read before deciding, run `WATCH` and `GET` **before `MULTI`**.

### 33.3. Pipeline Returns Unexpected Java Types

Check `RedisTemplate` serializers—especially value, hash value, and custom result serializers. Key bytes may differ from names typed in the CLI.

### 33.4. `WATCH` Test Passes Sometimes and Fails Other Times

Likely caused by using `sleep` instead of latches, misusing a shared client connection, key/TTL interference from another test, or asserting before the `Future` finishes.

### 33.5. Lua Works in CLI Yet Spring Returns `0`

Check key bytes, argument serialization, wire format of the expected value, script result type, and key names. `StringRedisTemplate` fits string-comparing scripts; JSON serializers add quotes or formatting.

### 33.6. Lua Test Passes Standalone Yet Fails on Cluster

Check hash slots of all `KEYS` and how the script declares keys. Multi-key Cluster scripts require same-slot keys; standalone never catches this.

### 33.7. `@Transactional` Test Never Runs After-Commit Hooks

Spring Test rolls back test methods at completion by default. Commit an explicit transaction when testing `AFTER_COMMIT`, and assert outside the transaction.

### 33.8. Redis Timeouts Hang Tests

Set timeouts on Testcontainers startup, `Future`s, latches, and Redis commands, while distinguishing genuine performance bugs from starved CI runners. Never let a thread block indefinitely on a latch when setup fails.

### 33.9. “Rollback” Test Still Leaves a Key Written

Check whether a command failed at runtime inside `EXEC` or whether `DISCARD` ran before `EXEC`. Redis does not roll back runtime errors; expecting all keys to stay unchanged after partial `EXEC` execution is incorrect.

## 34. Self-Assessment Questions

**1. Why must `SessionCallback` be used with `MULTI/EXEC`?**  
Because `WATCH`/`MULTI`/`EXEC` are connection-bound; separate `RedisTemplate` calls are not guaranteed to reuse the same connection.

**2. Does `EXEC` roll back every command if one command triggers `WRONGTYPE`?**  
No. Runtime errors on one command can coexist with other commands that succeeded.

**3. What is `WATCH` used for?**  
Making `EXEC` conditional on whether watched keys remained unmodified since `WATCH`.

**4. Why do `WATCH` tests need two independent connections?**  
To simulate another client modifying the key between `WATCH` and `EXEC`, without mixing transaction state on the same connection.

**5. Do `WATCH` conflicts auto-retry?**  
No. The application must implement bounded retries with backoff or return conflict.

**6. Do pipelines create atomic transactions?**  
No. They optimize sending/receiving multiple commands, without guaranteeing rollback or preventing interleaving.

**7. What must the `executePipelined` callback return?**  
`null`; pipeline results are returned separately as a `List<Object>`.

**8. Which race does Lua CAS prevent?**  
The race between reading a value, checking a condition, and writing when two clients update the same key concurrently.

**9. Does a Lua script roll back if it fails after a `SET`?**  
No. Script atomicity does not mean prior writes are undone on a runtime error.

**10. Why should `INCR` not be retried blindly after a timeout?**  
Because the first command may have already executed; retrying can increment twice.

**11. Does a standalone Redis test prove multi-key Lua runs on Cluster?**  
No. You must test same-slot and cross-slot behavior against a real Redis Cluster.

**12. Can a `@Transactional` test method directly verify `AFTER_COMMIT`?**  
Not reliably; Spring Test defaults to rollback. Commit explicitly and assert outside the transaction.

**13. Why is asserting only the pipeline reply count insufficient?**  
Because you must verify final Redis values and partial errors; reply count alone does not prove correctness.

**14. When Redis acts as a cache for SQL, does a failed Redis `EXEC` roll back SQL?**  
Not automatically. Two stores do not share an atomic commit by default; use recovery/outbox patterns where needed.

## 35. Test Design Checklist Before CI Integration

- [ ] Use dedicated test Redis; never run dangerous admin commands on production.
- [ ] Give every test a unique key namespace and explicit cleanup.
- [ ] Document invariants, setup, synchronization points, and asserted final state.
- [ ] Include tests for `MULTI/EXEC` success, `DISCARD`, `WATCH` conflicts, and runtime `WRONGTYPE`.
- [ ] Trigger `WATCH` conflicts with latches and independent connections, not `sleep`.
- [ ] Enforce finite timeouts on `Future`s, threads, and connections.
- [ ] Pipeline tests assert **reply order + real Redis state**, never mistaking pipelines for transactions.
- [ ] Lua tests assert success, rejection, concurrency, and runtime-error semantics.
- [ ] Script serializers and result types are explicitly verified.
- [ ] Redis state is read **after `EXEC`/pipeline completion** via an appropriate connection/read path.
- [ ] Test Redis transaction support with `@Transactional`, including rollback paths.
- [ ] Test failures after SQL commit when Redis acts as a cache for a database.
- [ ] Every retried side effect has an idempotency strategy.
- [ ] Cluster deployments test hash slots, routing, and failover accordingly.
- [ ] CI reports failures clearly so unstarted Redis, resource timeouts, and business bugs stay distinct.

This checklist guides **designing the application test suite**, without replacing concrete assertions on Redis state.

## 36. Summary

- **`MULTI/EXEC`** executes queued commands sequentially during `EXEC`, yet Redis does not roll back all runtime errors.
- **`DISCARD`** drops un-`EXEC`ed queued commands; it does not undo committed transactions.
- **`WATCH`** enables optimistic concurrency; write conflict tests with deterministic ordering and independent connections.
- **Pipelines** reduce round-trips; test reply lists, serialization, ordering, and partial failures without assuming atomicity.
- **Lua** consolidates read–check–write on Redis; test concurrent clients racing from the same expected value and post-write runtime errors.
- **Spring Data Redis** provides `SessionCallback`, `executePipelined`, and `DefaultRedisScript`, each with distinct contracts.
- **`@Transactional` with SQL** does not make Redis and SQL commit atomically; test commit/rollback outcomes and post-commit failure handling.
- **Timeouts after writes** leave outcomes ambiguous; retries require idempotency, not merely higher retry counts.
- **Redis Cluster** introduces hash slots, redirections, and multi-key limits that require dedicated testing.
- **JUnit + Testcontainers + `StepVerifier`** let you verify real Redis behavior in isolation rather than guessing from mocks.

A trustworthy test suite does not merely ask “did the command run?” It asks **“When two clients race, one command errors, a connection drops replies, or a SQL transaction commits, what state actually remains in Redis and how does the application recover?”**

## References

- [Spring Data Redis — Transactions](https://docs.spring.io/spring-data/redis/reference/redis/transactions.html): `SessionCallback`, `multi`/`exec`/`discard`, and Spring transaction support.
- [Spring Data Redis — Pipelining](https://docs.spring.io/spring-data/redis/reference/redis/pipelining.html): `executePipelined`, callback results, and serializers.
- [Spring Data Redis — Scripting](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html): `DefaultRedisScript`, `EVALSHA`, and `EVAL`.
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html): connection handling and Redis operations.
- [Redis — Transactions](https://redis.io/docs/latest/develop/using-commands/transactions/): `MULTI`/`EXEC`/`DISCARD`/`WATCH`, optimistic locking, and no rollback.
- [Redis — WATCH](https://redis.io/docs/latest/commands/watch/): key-based optimistic locking.
- [Redis — EXEC](https://redis.io/docs/latest/commands/exec/): transaction execution and nil replies on `WATCH` abort.
- [Redis — Pipelining](https://redis.io/docs/latest/develop/using-commands/pipelining/): reducing round-trips and handling replies.
- [Redis — Lua Scripting](https://redis.io/docs/latest/develop/programmability/eval-intro/): `EVAL`/`EVALSHA`, atomicity, and scripting conventions.
- [Spring Framework — Testing Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): default rollback of test-managed transactions and `TestTransaction`.
- [Testcontainers — Java](https://java.testcontainers.org/): Redis test instance/container lifecycles.
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier` and testing reactive publishers.
- [Redis — Cluster Specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/): slot constraints for multi-key operations and Lua.
