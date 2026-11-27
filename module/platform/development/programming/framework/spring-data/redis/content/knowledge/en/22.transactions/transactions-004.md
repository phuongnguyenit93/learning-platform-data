# DISCARD and Canceling a Transaction Before Execution

In Spring Data Redis, a Redis transaction typically begins with the `MULTI` command, continues by queuing commands, and ends with either **`EXEC`** or **`DISCARD`**. `EXEC` instructs Redis to execute the queued commands; conversely, **`DISCARD` cancels the entire queue and takes the connection out of transaction mode before any queued command is executed**.

This mechanism is very useful when an application has started preparing a group of operations and then decides not to proceed: the user withdraws the request, business validation detects an unmet condition, or a preparation step fails before `EXEC` is called.

The most important thing to understand is that **`DISCARD` only cancels commands still waiting in the transaction**. It does not undo commands already executed by `EXEC`, does not restore effects on external systems, and does not replace relational-database rollback of any kind.

## 1. Lifecycle of a Redis Transaction

A Redis Transaction can be visualized as a state machine:

~~~text
        Connection in normal state
                         |
                         | MULTI
                         v
                Open transaction
                         |
             +-----------+------------+
             |                        |
       SET, INCR, ...            End decision
             |                        |
             v               +--------+---------+
         QUEUED              |                  |
             |               v                  v
             +---------->  EXEC              DISCARD
                             |                  |
                             v                  v
                      Execute queued      Drop all unexecuted
                      commands            commands
                             |                  |
                             +---------+--------+
                                       |
                                       v
                         Connection returns to normal state
~~~

| Command | Effect | Effect on data |
| --- | --- | --- |
| `MULTI` | Starts transaction mode on the current connection | Subsequent commands are not applied yet |
| `SET`, `INCR`, `DEL`… after `MULTI` | Placed into the queue, typically returning `QUEUED` | Does not modify data at queuing time |
| `EXEC` | Executes the command sequence in the queue | Changes may take effect |
| `DISCARD` | Clears the entire queue and ends the transaction | No pending commands are executed |
| `WATCH` | Watches key changes before `MULTI` for optimistic concurrency control | Does not write data itself; affects `EXEC` execution decision |
| `UNWATCH` | Stops watching `WATCH`ed keys | Useful when aborting a flow before starting `MULTI` |

An important characteristic: `MULTI` state is bound to the **connection**, not merely to key names or Java objects. Therefore, when using Spring Data Redis, `MULTI`, queued commands, and `DISCARD` or `EXEC` must run in the same connection context.

## 2. Redis CLI Example: `DISCARD` Preserves the Original Data

Suppose a product has stock quantity 10. A processing flow temporarily prepares to decrement stock and create a reservation state, but the buyer cancels before the transaction is executed.

First set initial values:

~~~redis
SET demo:stock:sku-42 10
DEL demo:reservation:r-101
~~~

Open a transaction and queue two commands:

~~~redis
MULTI
DECRBY demo:stock:sku-42 2
SET demo:reservation:r-101 "PENDING"
~~~

Typical Redis output:

~~~text
OK
QUEUED
QUEUED
~~~

Until `EXEC` is called, `DECRBY` and `SET` remain pending. If the application decides to cancel, send:

~~~redis
DISCARD
~~~

Redis returns:

~~~text
OK
~~~

Check again in normal state:

~~~redis
GET demo:stock:sku-42
EXISTS demo:reservation:r-101
~~~

Output:

~~~text
"10"
(integer) 0
~~~

**Stock was not decremented and the reservation was not created.** There is no need to run commands to increment stock back or delete the reservation to “reverse” the transaction, because those two commands were never executed.

If `DISCARD` were replaced with `EXEC`, Redis would execute the queued commands and return their respective results. Afterward, calling `DISCARD` **cannot** bring stock from 8 back to 10.

## 3. What Does `DISCARD` Actually Cancel?

`DISCARD` applies only to the command queue of the Redis transaction **currently open on that same connection**.

It performs the following actions:

1. Drops all commands queued after `MULTI`.
2. Exits transaction mode, allowing the connection to process normal Redis commands again.
3. Clears any keys watched by `WATCH` on that connection, if present.

`DISCARD` **does not** perform the following actions:

- Does not reverse Redis commands executed **before** `MULTI`.
- Does not undo any command already executed by `EXEC`.
- Does not delete or modify a Java object just because the command writing that object was discarded.
- Does not cancel commands in a transaction on another connection.
- Does not restore changes in JDBC, HTTP, the filesystem, or a message broker.
- Does not guarantee rollback for operations executed outside the Redis transaction.

For example:

~~~redis
SET demo:outside "done"
MULTI
SET demo:inside "queued"
DISCARD
~~~

After `DISCARD`, `demo:outside` still holds `"done"` because that command ran **before `MULTI`**. The key `demo:inside` was not created by the discarded transaction.

Similarly, after discarding a transaction, `EXEC` no longer has an open transaction to execute. Calling `EXEC` or `DISCARD` outside `MULTI` causes corresponding Redis errors, such as `ERR EXEC without MULTI` or `ERR DISCARD without MULTI`.

## 4. Canceling a Transaction in Spring Data Redis with `RedisCallback`

Spring Data Redis provides `RedisTemplate` and `StringRedisTemplate` to work with Redis. When you want direct control over `MULTI`, `EXEC`, and `DISCARD` on the same Redis connection, you can use **`RedisCallback`**.

The example below intentionally queues a write command and then **cancels before `EXEC`**, illustrating the exact role of `DISCARD`.

~~~java
package com.example.redis.transaction;

import java.nio.charset.StandardCharsets;
import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RedisDiscardService {

    private final StringRedisTemplate redis;

    public RedisDiscardService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void prepareAndCancel(String key, String proposedValue) {
        redis.execute((RedisCallback<Void>) connection -> {
            // StringRedisTemplate defaults to UTF-8 for keys and values.
            byte[] rawKey = key.getBytes(StandardCharsets.UTF_8);
            byte[] rawValue =
                proposedValue.getBytes(StandardCharsets.UTF_8);

            connection.multi();

            try {
                // Only queued; rawValue is not written to Redis yet.
                connection.stringCommands().set(rawKey, rawValue);
            } catch (RuntimeException cause) {
                // If preparation fails, close the open transaction.
                try {
                    connection.discard();
                } catch (RuntimeException cleanupFailure) {
                    cause.addSuppressed(cleanupFailure);
                }
                throw cause;
            }

            // Decide to cancel: do not call EXEC.
            connection.discard();
            return null;
        });
    }
}
~~~

Usage:

~~~java
redis.opsForValue().set("demo:order:1", "OLD");

discardService.prepareAndCancel("demo:order:1", "NEW");

String current = redis.opsForValue().get("demo:order:1");
System.out.println(current); // OLD
~~~

Key points to remember:

- `redis.execute(RedisCallback)` supplies a single connection for the entire callback, so commands stay within the same Redis session.
- `connection.multi()` opens the transaction before queuing `SET`.
- `connection.stringCommands().set(...)` is only placed in the Redis queue in `MULTI` mode.
- `connection.discard()` drops the pending `SET` command and ends the transaction.
- Calling `redis.opsForValue().get(...)` **after the callback** reads actual data and still sees the old value.
- The example uses default `StringRedisTemplate`, where strings convert to bytes using UTF-8. If the application customizes serializers, use the corresponding serializer instead of `getBytes(...)`.

This is an **explicitly canceled** transaction, so there is no `exec()` at the end of the callback. Avoid control flow where after calling `discard()`, execution falls through to an `exec()` branch.

### Why Not Call `multi` Then `discard` Separately on the Template?

The following example cannot reliably guarantee the same connection:

~~~java
// Do NOT treat this as a safe transaction pattern:
redis.multi();
redis.opsForValue().set("demo:key", "value");
redis.discard();
~~~

`RedisTemplate` acquires and releases a Redis connection per call unless running inside an appropriate connection-binding context. Splitting commands like this can prevent the sequence from running on one consistent transactional connection.

For groups of operations using high-level template APIs, **`SessionCallback`** is the standard way to pin the same Redis connection across the session. When you want direct connection-level control over Redis commands, `RedisCallback` presents it explicitly and avoids transaction-session confusion.

## 5. Deciding to Cancel Before or After Opening `MULTI`?

Rejecting a business request does not always require sending `DISCARD`.

**Case A — condition fails before `MULTI`:** No transaction has started. Simply stop processing without calling `DISCARD`.

~~~java
if (!request.isValid()) {
    return; // Not in MULTI yet, no DISCARD needed.
}

// Only open a transaction if there is a reason to prepare writes.
~~~

**Case B — `MULTI` called, `EXEC` not yet called:** Commands are pending and the application decides to cancel. Call `DISCARD` on the same connection.

**Case C — `EXEC` already called:** Data may already have changed. Fixing an issue requires an appropriate compensating action or recovery workflow; `DISCARD` is not the solution.

Decision diagram:

~~~text
             Should the business operation proceed?
                      |
            +---------+---------+
            |                   |
           No                  Yes
            |                   |
     Is MULTI open?        Validate/prepare
       /        \          prerequisites
      /          \               |
    No           Yes             v
     |            |            MULTI
     v            v              |
  Stop work    DISCARD           v
                           Queue Redis commands
                                 |
                           Need to cancel?
                             /         \
                           Yes          No
                            |            |
                            v            v
                         DISCARD        EXEC
~~~

A clean design checks as many business conditions **before `MULTI`** as possible. This reduces how long the connection stays in transaction mode and reduces how often queues must be discarded.

## 6. Structuring Code to Avoid Leaving Open Transactions

A common bug is calling `multi()` and then throwing an exception or returning early without calling `exec()` or `discard()`. A connection left in `MULTI` state can cause unpredictable behavior if reused.

Therefore, when managing transactions manually in a connection callback, structure control flow with one clear termination path: **either execute, or discard**.

Example with a cancellation branch **prior to execution**:

~~~java
public void cancelWhenNotApproved(
        String key, String value, boolean approved) {

    redis.execute((RedisCallback<Void>) connection -> {
        byte[] k = key.getBytes(StandardCharsets.UTF_8);
        byte[] v = value.getBytes(StandardCharsets.UTF_8);

        connection.multi();
        boolean stillOpen = true;

        try {
            connection.stringCommands().set(k, v);

            if (!approved) {
                connection.discard();
                stillOpen = false;
                return null;
            }

            // Execution branch.
            // Once EXEC is issued, DISCARD cannot be treated as rollback.
            stillOpen = false;
            connection.exec();
            return null;
        } finally {
            // Clear the queue if an error happens BEFORE sending EXEC.
            if (stillOpen) {
                connection.discard();
            }
        }
    });
}
~~~

In this example, `stillOpen` is only used to identify the branch needing queue cleanup before `EXEC`. If `exec()` was already sent and encountered a connection error or timeout, execution status may be **uncertain**: the server may have received and run the commands while the client failed to receive the reply. Do not assume a client error means rollback, and do not immediately re-run a non-idempotent transaction.

For production code, add result observability, controlled retries, idempotency keys, or state reconciliation depending on business needs. Handling Redis connection exceptions and ensuring clean connection return to the pool must also match the driver in use.

### Distinguishing Preparation Errors from Post-`EXEC` Errors

| Error timing | What can happen? | How to handle |
| --- | --- | --- |
| Before `MULTI` | No Redis transaction exists yet | Stop processing, no `DISCARD` needed |
| After `MULTI`, before `EXEC` | Commands may still be `QUEUED` | `DISCARD` if connection is still usable; surface original error |
| When `DISCARD` fails | Connection/Redis problem | Report error; do not assume cleanup succeeded |
| After issuing `EXEC` | Redis may have executed part or all of the sequence per Redis error rules | Inspect results and actual state; do not call `DISCARD` as rollback |
| When an error occurs in another system | Outside the Redis transaction's scope | Design separate compensation or business coordination |

## 7. `DISCARD` vs. Rollback After `EXEC`

A Redis transaction has an important property: when `EXEC` is accepted, Redis executes queued commands in order without interleaving commands from other clients in the middle of that sequence. However, it **has no general rollback** for errors raised while commands are executing.

Suppose a transaction:

~~~redis
SET demo:counter "not-a-number"
MULTI
INCR demo:counter
SET demo:flag "created"
EXEC
~~~

`INCR` fails because `demo:counter` does not contain a valid integer. Yet `SET demo:flag "created"` can still execute within the same `EXEC`. Redis returns a result list containing an error element, rather than automatically undoing all other changes due to a runtime error.

This differs sharply from the expectation that “every transaction rolls back everything if one command fails.” `DISCARD` prevents the whole queue from running **if called before `EXEC`**; it does not resolve errors occurring during `EXEC`.

Also distinguish **queue-time errors**. In modern Redis, if a syntax or arity error prevents a command from being queued validly in `MULTI` mode, `EXEC` is typically rejected with an error such as `EXECABORT`. An application that already detects a preparation error should proactively cancel the transaction with `DISCARD` rather than attempting to execute it anyway.

## 8. `WATCH`, `UNWATCH`, and `DISCARD`

For concurrent update control, `WATCH` monitors one or more keys before `MULTI`. Redis only executes `EXEC` if the watched keys were not modified by another client under optimistic locking rules.

Illustrative flow:

~~~text
Connection A                         Connection B
     |                                    |
 WATCH stock:sku-42                       |
     |                                    |
 GET stock:sku-42                         |
     |                            SET stock:sku-42 ...
     |                                    |
 MULTI                                    |
 DECRBY stock:sku-42 2                   |
     |                                    |
 EXEC  --------------------> Not executed due to WATCH conflict
~~~

If a `WATCH`ed key changes before `EXEC`, Redis **aborts execution** per `WATCH` rules; the client typically receives an empty nil/null `EXEC` result indicating execution did not occur due to conflict. Do not treat this result the same as a successful list of command outcomes.

Within that flow:

- **`UNWATCH`**: stops watching keys if the application halts **before opening `MULTI`**.
- **`DISCARD`**: cancels queued commands **after `MULTI` has been opened**, and also clears `WATCH` state.
- **`EXEC`**: requests execution; Redis rejects it if the `WATCH` condition no longer holds.

Redis CLI example:

~~~redis
WATCH demo:balance
GET demo:balance
~~~

If the application checks and decides not to transact:

~~~redis
UNWATCH
~~~

If the application already entered the transaction phase:

~~~redis
WATCH demo:balance
MULTI
DECRBY demo:balance 100
DISCARD
~~~

After `DISCARD`, `DECRBY` does not run and `WATCH` is cleared as well. A new operation starting normally on that connection does not inherit the old `WATCH` state.

**`WATCH` is not an exclusive lock.** Other clients can still modify the key. It is how Redis detects conflicts and rejects a stale `EXEC`. When a conflict occurs, the application usually needs to re-read state and decide whether to retry within a bounded limit.

## 9. Spring-Managed `@Transactional` and `DISCARD`

In Spring, the `@Transactional` annotation drives **the transaction of the configured transaction manager**. Do not assume simply adding `@Transactional` to a service automatically runs all `StringRedisTemplate` calls inside Redis `MULTI/EXEC`.

Spring Data Redis can participate in an active Spring transaction when transaction support is enabled on the template:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration
class RedisTemplateConfiguration {

    @Bean
    StringRedisTemplate transactionalRedisTemplate(
            RedisConnectionFactory factory) {
        StringRedisTemplate template = new StringRedisTemplate(factory);
        template.setEnableTransactionSupport(true);
        return template;
    }
}
~~~

When an actual Spring-managed transaction is active, Redis write commands can be queued and Spring Data Redis sends `EXEC` when the transaction completes successfully or `DISCARD` on rollback. Illustrative example:

~~~java
@Transactional
public void reserveOrder(String orderId) {
    redis.opsForValue().set("order:" + orderId, "RESERVED");

    if (!allowedToReserve(orderId)) {
        throw new IllegalStateException("Reservation not allowed");
    }
}
~~~

This example **assumes** the application already has an appropriate `PlatformTransactionManager`, the template has transaction support enabled, and the call passes through the Spring transaction proxy. Spring Data Redis does not provide a standalone `RedisTransactionManager` out of the box just so `@Transactional` can be used alone.

In transaction-managed mode:

- Spring decides commit/rollback based on the transaction boundary and rollback rules.
- The template participates in the transaction to issue `MULTI`, `EXEC`, or `DISCARD` along the lifecycle.
- **Do not manually call `discard()` in the same flow where Spring manages the transaction**, as this can desynchronize connection state and transaction synchronization logic.
- Read commands may be routed by Spring Data Redis to a different connection because replies on a connection in `MULTI` are only `QUEUED`; therefore, reads inside transactions must be understood properly.

If the primary transaction is managed by JDBC/JPA, Spring Data Redis participation **does not turn two data stores into one atomic distributed transaction**. One side may commit while the other fails. Multi-resource workflows require proper coordination, outbox, idempotency, or compensation design.

## 10. `DISCARD` Is Not Pipelining, Lua, or Compensation

These mechanisms may all appear in a Redis application, but they solve different problems:

| Mechanism | Purpose | Does it cancel already-executed commands? |
| --- | --- | --- |
| `MULTI` + `DISCARD` | Discards a transaction queue before `EXEC` | No |
| `MULTI` + `EXEC` | Sequentially executes queued commands | No general rollback |
| `WATCH` | Detects conflicts before `EXEC` | Prevents `EXEC` when keys change; does not revert executed commands |
| Pipelining | Reduces network round-trips by batching command sends | Not a rollback or automatic transaction mechanism |
| Lua scripts / Redis Functions | Moves logic to Redis for centralized/atomic execution per Redis semantics | No automatic SQL-style rollback for runtime errors mid-script |
| Compensating action | Fixes/reverses an already-occurred effect per business rules | Is a new operation; requires design and risk control |

You cannot rely on `DISCARD` to “cancel a pipeline” once pipelined commands have reached Redis and executed. Pipelining optimizes command transmission; it does not implicitly convert commands into a `MULTI` queue.

If a business decision must depend on the result of commands inside the operation group, note that **you cannot read a `QUEUED` `GET` result before `EXEC` and use it to decide whether to `DISCARD`**. In Redis CLI, `GET` inside `MULTI` returns `QUEUED`; in Spring Data Redis, some APIs return `null` or a placeholder while queuing, not the real Redis value.

For check-condition-and-write operations needing atomicity, consider `WATCH` + retry, Lua scripts, or an appropriate key/data-structure design instead of expecting to inspect fresh values inside `MULTI`.

## 11. Integration Test: `QUEUED` Commands Do Not Modify Keys After `DISCARD`

To verify behavior, use real Redis in an integration test. Testing with a mocked `RedisTemplate` only proves the `discard()` method was called, not that real Redis dropped the queue.

Example using Spring Boot, JUnit 5, AssertJ, and Testcontainers:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
}
~~~

**Test**:

~~~java
package com.example.redis.transaction;

import java.nio.charset.StandardCharsets;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest(classes = RedisDiscardIntegrationTest.TestApp.class)
class RedisDiscardIntegrationTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApp {
    }

    @Container
    static final GenericContainer<?> REDIS =
        new GenericContainer<>(DockerImageName.parse("redis:7.2-alpine"))
            .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add("spring.data.redis.port",
            () -> REDIS.getMappedPort(6379));
    }

    @Autowired
    StringRedisTemplate redis;

    @Test
    void discardPreventsQueuedWriteFromExecuting() {
        String key = "test:discard:" + UUID.randomUUID();

        try {
            redis.opsForValue().set(key, "before");

            redis.execute((RedisCallback<Void>) connection -> {
                byte[] rawKey = key.getBytes(StandardCharsets.UTF_8);
                byte[] rawValue =
                    "after".getBytes(StandardCharsets.UTF_8);

                connection.multi();
                connection.stringCommands().set(rawKey, rawValue);
                connection.discard();
                return null;
            });

            // Value remains "before", because SET "after" was discarded.
            assertThat(redis.opsForValue().get(key))
                .isEqualTo("before");
        } finally {
            redis.delete(key);
        }
    }

    @Test
    void execAppliesQueuedWriteForComparison() {
        String key = "test:exec:" + UUID.randomUUID();

        try {
            redis.opsForValue().set(key, "before");

            redis.execute((RedisCallback<Void>) connection -> {
                connection.multi();
                connection.stringCommands().set(
                    key.getBytes(StandardCharsets.UTF_8),
                    "after".getBytes(StandardCharsets.UTF_8)
                );
                connection.exec();
                return null;
            });

            assertThat(redis.opsForValue().get(key))
                .isEqualTo("after");
        } finally {
            redis.delete(key);
        }
    }
}
~~~

Both tests use UUID-suffixed keys to avoid collisions during parallel runs. The first test verifies `DISCARD` preserves the existing value; the second serves as a contrast with `EXEC` to demonstrate the difference between the two termination paths. The test runner needs Docker or a compatible container runtime.

In projects with custom serializers, use the same serializer to convert keys/values to bytes instead of calling `getBytes(UTF_8)` directly. When using a Spring application context with active Spring transactions, keep manual transaction tests separate from template transaction support so two controllers do not fight over the same connection.

## 12. Common Errors to Recognize

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `DISCARD` reports `without MULTI` | `MULTI` was not opened or transaction already ended | Only call `DISCARD` while a transaction is still open on the current connection |
| Called `DISCARD` but data still changed | Command ran before `MULTI`, on another connection, or `EXEC` already ran | Pinpoint exact transaction boundaries and connection |
| `MULTI` called but later commands not `QUEUED` | Calls did not share the same connection or template setup was wrong | Use `SessionCallback` or `RedisCallback` appropriately |
| Used `GET` inside `MULTI` and got `null`/`QUEUED` | Read command is sitting in the queue | Read before `MULTI` or use appropriate concurrency control |
| `EXEC` had an error yet some keys changed | Redis command execution errors do not always imply rollback | Validate inputs and handle individual command results |
| Exception between `MULTI` and `EXEC` left connection in transaction mode | Missing cleanup branch | Add `DISCARD` on the cancellation/error path before execution |
| Transaction canceled yet another system wrote data | `DISCARD` only applies to Redis queued commands | Design separate multi-resource transaction/compensation |
| `@Transactional` did not cancel Redis writes | Redis template did not join the transaction or boundary was misconfigured | Configure transaction support and understand actual transaction manager |
| Called `DISCARD` after timeout error on `EXEC` | Client does not know whether the server already executed | Reconcile state; use idempotency, do not assume rollback |
| Expected `DISCARD` to cancel a pipeline | Pipelining and transactions differ | Use `MULTI` if transactional queuing before `EXEC` is required |

## 13. Applying in Business Design

Suppose an API prepares multiple Redis changes to register a processing session:

~~~text
1. Validate input data and access permissions
2. Open MULTI
3. Queue SET session:<id>, SADD user:sessions:<userId>
4. If unable to proceed before EXEC -> DISCARD
5. If conditions are met and ready to commit -> EXEC
6. Inspect results and return appropriate response
~~~

Several design principles:

- **Validate before queuing whenever possible.** Shortens time spent in `MULTI` state and avoids unnecessary discards.
- **Bind the transaction to one connection.** Use an appropriate callback or transaction context in Spring Data Redis.
- **Keep the two termination paths separate.** Every self-managed transaction must reach either `EXEC` or `DISCARD`, never accidentally both.
- **Do not make decisions from return values of QUEUED commands.** Perform checks before the transaction or use proper concurrency control.
- **Set clear effect boundaries.** `DISCARD` only guarantees that commands queued in that transaction will not run.
- **Design post-commit error handling.** `EXEC` may have run even when the client times out; avoid blindly retrying increment/decrement or resource-creation commands.
- **Test against real Redis when proving transactional behavior.** Compare state before and after `DISCARD` instead of merely verifying a mock call.

`DISCARD` is a clean, explicit way to **drop all pending commands in an unexecuted Redis transaction**. In Spring Data Redis, using it properly requires understanding connection state, `MULTI/EXEC` boundaries, the difference between pre-execution and post-execution errors, and how Spring can manage transactions in place of manual code. Once these boundaries are clearly designed, the application can cancel operations safely at the right moment without accidentally mutating Redis data.
