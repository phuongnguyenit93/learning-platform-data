# CountDownLatch, Barriers, and Controlled Thread Coordination

In the **Async and Scheduling** group of the **Spring Boot - testing** module, a very common testing failure is "the test passes on my machine but fails on CI". The root cause usually lies not in JUnit, but in the test relying on **guessed timing**, such as calling `Thread.sleep(200)` and hoping an `@Async`, `@Scheduled`, or executor task has finished. When the scheduler is slow, the thread pool is busy, GC occurs, or the CI machine has fewer CPUs, that assumption breaks.

**CountDownLatch**, **CyclicBarrier**, and **Phaser** are three tools from `java.util.concurrent` that explicitly orchestrate critical points in time: waiting for a number of workers to reach a checkpoint, actively opening a gate for workers to proceed, or requiring a group of threads to meet before starting the next phase. Good tests also combine `Future/CompletableFuture`, **finite timeouts**, interruption handling, `finally` blocks to release waiters, and executor cleanup.

Lesson goals:

1. Use `CountDownLatch` to know when **N tasks have reached a checkpoint** and to **release them once the test is ready**.
2. Distinguish a **start gate** from a **completion signal**; understand that `countDown()` does not make a thread wait by itself.
3. Use `CyclicBarrier` to coordinate a **fixed** number of parties across multiple phases; understand broken barriers, timeouts, and resets.
4. Know when `Phaser` with dynamic parties is a better fit.
5. Write JUnit 5 tests that reproduce **race conditions intentionally**, instead of sleeping and hoping to hit a race.
6. Test a Spring Boot `@Async` service with a real executor and two latches; avoid self-invocation or Mockito-only tests when the goal is verifying the thread boundary.
7. Test `@Scheduled`: decouple business logic from the trigger; use a latch as a signal when a real scheduler smoke test is needed.
8. Avoid deadlocks, false timeouts, lost exceptions, resource leaks, and asserting ordering or rollbacks that the test did not actually prove.

Examples use **Java 17+, JUnit Jupiter, Spring Boot 3.5 / Spring Framework 6.2**. The Java SE section includes `javac/java` commands and **exact stdout**; the Spring Boot section includes classes, tests, and Gradle dependencies so learners can run them in a real project. Each example states the boundary of what it verifies.

## 1. Why is Thread.sleep not a coordination tool?

A fragile test:

```java
service.startAsyncWork();
Thread.sleep(200);
assertEquals(1, repository.count());
```

This is an **illustrative anti-pattern**, not a complete file. It has no event guaranteeing the task has started or finished before the assertion runs. If CI scheduling is slower than 200 ms, the test fails spuriously; if the task finishes immediately, the test wastes 200 ms. When a task throws an exception on a background thread, the test may still pass if it never collects the result.

Instead of asking "have we slept long enough?", ask something observable:

- Has the worker **started**? Use `started.countDown()` and `started.await(timeout)`.
- Have **N workers reached the checkpoint**? Use `new CountDownLatch(N)`.
- Do we need to hold workers at the checkpoint until the test sets up state? Use `release.await(timeout)` and have the test call `release.countDown()`.
- Do all workers need to finish **each phase** together? Use `CyclicBarrier` or `Phaser`.
- Need to know the **final result/exception**? Use `Future.get(timeout, unit)` or `CompletableFuture.get(...)`.
- Need to wait for an external condition to change without controlling the signaling code? Use Awaitility with appropriate timeout/polling, not fixed `Thread.sleep`.

**No primitive guarantees a specific OS scheduler execution order.** They only establish specific coordination relationships. Place signals at the right points, use the right party counts, and observe side effects with thread-safe state.

## 2. Three synchronization models

```text
CountDownLatch: one gate / one-shot
  Worker A ---- countDown --+
  Worker B ---- countDown --+--> count == 0 --> waiter is released
  Test thread - await ------+

CyclicBarrier: rendezvous, multiple phases
  Worker A -> phase 1 -> await --+
  Worker B -> phase 1 -> await --+--> both pass the barrier
  Worker A -> phase 2 -> await --+
  Worker B -> phase 2 -> await --+--> pass together again

Phaser: multi-phase rendezvous, dynamic parties
  Phase 0: A + B + C
  Phase 1: A + B      (C deregisters)
  Phase 2: A + B + D  (D registers)
```

| Tool | Purpose | Reusable? | Parties |
| --- | --- | --- | --- |
| `CountDownLatch` | Wait for count to reach 0, one-way gate | **Does not reset** | Fixed count at creation |
| `CyclicBarrier` | Threads wait for each other at barrier | **Yes, multiple generations** | Fixed party count |
| `Phaser` | Multi-phase coordination | Yes | Can register/deregister |
| `Future/CompletableFuture` | Result/exception of a task | Per task/chain | Does not replace barrier groups |
| `Semaphore` | Limit concurrent access permits | Yes | Permits instead of rendezvous |
| `BlockingQueue` | Pass events/values between threads | Yes | Producer/consumer |
| `AtomicInteger/locks` | Protect state mutation | Yes | Does not replace gate behavior |

**Very important:** `CountDownLatch` and `CyclicBarrier` **do not turn a non-atomic read-modify-write algorithm into a thread-safe one**. They help reproduce/control timing; shared data still requires CAS, locks, transactions, or appropriate protection.

## 3. CountDownLatch: exact semantics

`CountDownLatch` is constructed with a non-negative `count`:

```java
CountDownLatch arrived = new CountDownLatch(2);
CountDownLatch release = new CountDownLatch(1);
```

Core API:

- `countDown()`: decrements count by one if greater than 0; when it reaches 0, wakes threads calling `await()`. This method **does not block** waiting for others to finish.
- `await()`: waits indefinitely unless interrupted; **should not be used unbounded in integration tests**.
- `await(long timeout, TimeUnit unit)`: returns `true` if count reached 0; returns `false` if the timeout elapsed. Throws `InterruptedException` if interrupted.
- `getCount()`: snapshot for debugging; do not use as the primary synchronization condition because it can change immediately after reading.
- Once count == 0, further `countDown()` calls have no effect; `await(...)` returns immediately.
- **There is no `reset()` on `CountDownLatch`.** If a new round is needed, create a new latch or choose `CyclicBarrier`/`Phaser`.

### Start gate and completion gate are different

```java
CountDownLatch start = new CountDownLatch(1);
CountDownLatch finished = new CountDownLatch(2);
```

A worker might do:

```java
try {
    start.await();
    process();
} finally {
    finished.countDown();
}
```

The test/driver does:

```java
start.countDown();
boolean done = finished.await(
        5, TimeUnit.SECONDS);
```

This is an **illustrative snippet**, requiring imports, `process()`, and an executor. `finished.countDown()` is placed in `finally` so the test does not hang forever if `process()` throws. However, **`finished` reaching 0 only proves the worker passed through `finally`**; it does not mean the worker succeeded. To see exceptions, keep the `Future` and call `get(...)`.

### Memory barrier (happens-before)

The Java SE 17 documentation states: actions in a thread prior to calling `countDown()` *happen-before* actions following a successful return from a corresponding `await()` in another thread. This matters for memory visibility.

```text
Worker:
  write shared data
  latch.countDown()
                   happens-before
Test:
  latch.await() returns successfully
  read shared data
```

However, observing `getCount()==0` at a point in time does not replace proper synchronization design, and incrementing a counter with `counter++` does not become atomic merely because a latch exists.

## 4. Reliable pattern: ready latch + release latch + Futures

A powerful structure for testing concurrency uses **two latches with distinct purposes**:

```text
                  Worker A                Worker B
                  --------                --------
                  reach.countDown()       reach.countDown()
                  release.await()         release.await()
                         |                       |
                         +------- blocked -------+
                                         ^
                                         |
Test thread:  reach.await(timeout) ------+
              assert workers reached gate
              prepare/assert initial state
              release.countDown()
              futureA.get(timeout)
              futureB.get(timeout)
```

This controls the exact starting point of a sensitive operation. When `reach.await(...)` returns true, the test knows **enough workers reached the signal point**; it does not prove each worker is frozen permanently. When worker code properly places `reach.countDown()` right before `release.await()`, the test actively opens `release` to initiate the next step.

**Note on pool size:** if **2 workers must wait at the gate simultaneously**, the executor must have at least **2 runnable threads**. With `newSingleThreadExecutor()`, the first worker blocks waiting on `release` while the second sits in the queue: `reach` can never reach 0. When the test waits for `reach` before releasing, that is a design deadlock, not "slow CI".

## 5. CyclicBarrier: meeting at each phase

`CyclicBarrier(parties)` waits for the exact number of parties calling `await()` in the **same generation**. When the last party arrives, the barrier trips and all are released; the instance can be reused in the next generation.

```java
CyclicBarrier barrier = new CyclicBarrier(2);

Callable<Void> worker = () -> {
    performPhaseOne();
    barrier.await(5, TimeUnit.SECONDS);

    performPhaseTwo();
    barrier.await(5, TimeUnit.SECONDS);
    return null;
};
```

This is an illustrative snippet; `performPhaseOne`/`Two` are not defined here. In the runnable section, two real workers are submitted and both pass through **two phases**.

**Key points:**

- `parties=2` means **two `await` calls** must arrive in each generation; if only one worker runs, it waits and times out.
- `await(timeout, unit)` can throw `TimeoutException`, `InterruptedException`, or `BrokenBarrierException`.
- When one waiter times out or is interrupted, the barrier normally enters the **broken state**; other waiters in that generation receive `BrokenBarrierException`.
- `isBroken()` reports the broken state. `reset()` starts a new generation but can cause current waiters to fail; use `reset()` **only when lifecycle is coordinated**, never blindly to "fix a test".
- The constructor accepts an optional `barrierAction` that runs once when the last party arrives at the barrier, before parties are released.
- `getNumberWaiting()` is a debugging snapshot, **not for reliable scheduling assertions**.

### How does CyclicBarrier differ from CountDownLatch?

With `CountDownLatch`, a thread simply calls `countDown()` and **continues**, without waiting for other threads. With `CyclicBarrier`, the **parties themselves wait for each other** at `await()`. Reusing `CountDownLatch` requires a new object; `CyclicBarrier` can cycle across multiple phases.

If the JUnit thread must also be one of the parties, include the **test thread** in the party count. For example, if two workers + the test thread all call `barrier.await()`, then `parties=3`, not 2. However, it is usually easier to debug if the **test uses latches for orchestration** and only workers participate in the `CyclicBarrier`.

## 6. Phaser: dynamic parties and multiple generations

`Phaser` is similar to `CyclicBarrier`, except the number of participants can change:

- `register()` or `bulkRegister(n)`: add parties.
- `arrive()`: signal phase completion without waiting.
- `arriveAndAwaitAdvance()`: signal arrival and wait for the phase to advance.
- `arriveAndDeregister()`: signal arrival and withdraw from subsequent phases.
- `awaitAdvanceInterruptibly(phase, timeout, unit)`: wait for phase change with timeout/interrupt; non-interruptible overloads have different semantics.
- `forceTermination()`: puts the phaser into the terminated state, releasing waiters when recovery is needed.

A snippet:

```java
Phaser phaser = new Phaser(1); // test/driver
phaser.register();             // one worker
int current = phaser.getPhase();

// Registered worker calls:
// phaser.arriveAndDeregister();

// Test calls:
int advanced = phaser.arriveAndAwaitAdvance();
```

This is an **explanatory model**, not a runnable test; actually running it requires starting the worker and handling timeouts/cleanup. If a registered party never arrives, the phase never advances. Therefore, for simple tests with two fixed workers, `CountDownLatch` or `CyclicBarrier` is usually less complex.

**`Phaser` is not the default answer for every async test.** Use it when you genuinely need multiple generations with changing worker counts, such as multi-stage pipelines where tasks register/deregister. With many tasks submitted to a small pool, avoid registering all of them and having some wait at a phase while the rest have not yet been scheduled: that can cause starvation/deadlock.

## 7. Design principles for non-flaky concurrency tests

Before writing the test, clarify 4 elements:

| Element | Question to answer |
| --- | --- |
| **Entry checkpoint** | Which step does the task signal reaching? Does the signal precede the read/write to control? |
| **Gate release** | Who opens the gate? Is it guaranteed to open even when an assertion fails? |
| **Result/exception** | Does the test read from a `Future`, queue, or callback? Is there a finite timeout? |
| **Cleanup/lifecycle** | Who stops the executor, scheduler, and cleans up DB/mocks? Are workers still blocked? |

**Minimum checklist:**

1. Create latches/conditions **before** submitting tasks.
2. Submit enough workers and ensure the pool has enough threads.
3. Have workers call `countDown()` at the exact checkpoint; do not signal earlier than what you need to prove.
4. Have the test call `await(timeout)` and **assert true**; never use unbounded `await()` in CI.
5. Have the test open the gate in `finally`, not only on the happy path.
6. Call `get(timeout)` on **every `Future`** so exceptions are never overlooked.
7. Call `shutdownNow()`/`shutdown()` + termination policy; never leave blocked threads alive after the test.
8. If a worker is interrupted, restore the flag with `Thread.currentThread().interrupt()` and exit cleanly.
9. Use thread-safe state such as `AtomicInteger`, `ConcurrentHashMap`, or locks/synchronized per contract.
10. Do not assert thread name ordering or timestamps that the JVM/OS does not guarantee.
11. Run the test repeatedly/on CI to detect timing dependence, but do not use "100 passes" to claim an algorithm is definitely correct.
12. State clearly that test synchronization **does not fix** bugs present in production execution.

## 8. Complete Java 17 and Spring Boot 3.5 project

Source structure:

```text
src/
├── main/java/example/concurrency/
│   ├── CoordinationApplication.java
│   ├── GateCoordinator.java
│   ├── GateDemo.java
│   ├── AsyncPoolConfig.java
│   ├── ControlledAsyncService.java
│   ├── ScheduledProbe.java
│   └── ScheduledHeartbeat.java
└── test/java/example/concurrency/
    ├── GateCoordinatorTest.java
    ├── RaceConditionTest.java
    ├── ControlledAsyncServiceTest.java
    └── ScheduledHeartbeatTest.java
```

The **Java SE** part consists of `GateCoordinator.java` and `GateDemo.java` — compilable standalone with JDK 17 alone. The **Spring Boot** part includes the application, async executor, service, scheduled probe, and integration tests.

### Gradle dependencies

In a Spring Boot **3.5.x** project already configured with Gradle plugins, repositories, dependency management, and Java 17+ toolchain:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The snippet above is the **addition to `build.gradle`**, not a complete standalone build script. Unit tests use JUnit Jupiter from `spring-boot-starter-test`; Spring scheduling, `@Async`, and `ThreadPoolTaskExecutor` come from Spring Context on the application classpath. No Docker/database is needed for this test suite.

**Version awareness:** the code uses Java 17 records, non-preview switch/syntax, JUnit Jupiter, and Spring Boot 3.5. With Java 21 virtual threads, executor/scheduler policies may vary, yet Java latch/barrier semantics still require the same protections.

## 9. Java SE source: GateCoordinator.java

Create `src/main/java/example/concurrency/GateCoordinator.java`:

```java
package example.concurrency;

import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class GateCoordinator {
    private GateCoordinator() {
    }

    public static String latchPair() throws Exception {
        ExecutorService pool =
                Executors.newFixedThreadPool(2);
        CountDownLatch bothReady =
                new CountDownLatch(2);
        CountDownLatch release =
                new CountDownLatch(1);

        try {
            Future<String> first = pool.submit(() -> {
                bothReady.countDown();

                if (!release.await(
                        5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "worker A timed out");
                }
                return "A";
            });

            Future<String> second = pool.submit(() -> {
                bothReady.countDown();

                if (!release.await(
                        5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "worker B timed out");
                }
                return "B";
            });

            if (!bothReady.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "workers did not reach gate");
            }

            release.countDown();

            return first.get(5, TimeUnit.SECONDS)
                    + second.get(5, TimeUnit.SECONDS);
        } finally {
            // Even if test/await throws, still open the gate.
            release.countDown();
            pool.shutdownNow();
        }
    }

    public static int barrierPhases()
            throws Exception {
        ExecutorService pool =
                Executors.newFixedThreadPool(2);
        AtomicInteger completedPhases =
                new AtomicInteger();

        CyclicBarrier barrier =
                new CyclicBarrier(
                        2, completedPhases::incrementAndGet);

        Callable<Void> work = () -> {
            barrier.await(5, TimeUnit.SECONDS);
            barrier.await(5, TimeUnit.SECONDS);
            return null;
        };

        try {
            Future<Void> first = pool.submit(work);
            Future<Void> second = pool.submit(work);

            first.get(5, TimeUnit.SECONDS);
            second.get(5, TimeUnit.SECONDS);

            return completedPhases.get();
        } finally {
            pool.shutdownNow();
        }
    }
}
```

**Runnability checks:**

- Exactly **2 worker threads** for `bothReady=2`, so both tasks can reach the gate.
- Each worker calls `bothReady.countDown()` before `release.await(...)`.
- The test/driver waits for both to arrive, then actively calls `release.countDown()`.
- Both `Future.get(timeout)` calls return **each task's value or exception**; not just waiting on the latch.
- `finally` ensures release and calls `shutdownNow()`; a real service should have an appropriate lifecycle/termination policy.
- `CyclicBarrier(2, action)` trips **twice**, and the action increments `completedPhases` on each generation.
- Do not print directly from workers, since worker output order is non-deterministic; the method returns values and `GateDemo` prints from the main thread after all Futures finish.

**Timeout limitation:** 5 seconds is an example hang guard, not an SLO for every environment. Extremely slow tests may time out; if so, check CPU/pool size/deadlocks before blindly raising the number.

## 10. Java SE source: GateDemo.java and exact stdout

Create `src/main/java/example/concurrency/GateDemo.java`:

```java
package example.concurrency;

public class GateDemo {
    public static void main(String[] args)
            throws Exception {
        System.out.println(
                "latch result="
                        + GateCoordinator.latchPair());
        System.out.println(
                "barrier phases="
                        + GateCoordinator.barrierPhases());
    }
}
```

From the project root, using JDK 17+:

```bash
javac -d out src/main/java/example/concurrency/GateCoordinator.java src/main/java/example/concurrency/GateDemo.java
java -cp out example.concurrency.GateDemo
```

Exact stdout **when both operations complete within the timeout**:

```text
latch result=AB
barrier phases=2
```

Explanation: Futures A and B can execute in any order, but `main` concatenates `first.get() + second.get()`, so the output order is always `AB`. The barrier action runs whenever **both** parties arrive at the barrier; because each worker passes through two generations, the counter equals **2**. If a worker times out or is interrupted, the program throws an exception and prints no success stdout as above; that is a clear failure rather than noisy output.

**This is a real Java SE demo**, opening no Spring context, starting no real scheduler, and requiring no database/broker. Subsequent integration tests verify Spring `@Async` and `@Scheduled` separately.

## 11. JUnit unit tests for CountDownLatch and CyclicBarrier

Create `src/test/java/example/concurrency/GateCoordinatorTest.java`:

```java
package example.concurrency;

import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class GateCoordinatorTest {

    @Test
    void gateReleasesBothWorkers() throws Exception {
        assertEquals("AB", GateCoordinator.latchPair());
    }

    @Test
    void barrierCanBeReusedAcrossTwoPhases()
            throws Exception {
        assertEquals(2, GateCoordinator.barrierPhases());
    }

    @Test
    void latchIsOneShotAndCannotBecomePositiveAgain()
            throws Exception {
        CountDownLatch latch = new CountDownLatch(1);

        latch.countDown();
        latch.countDown();

        assertEquals(0L, latch.getCount());
        assertTrue(latch.await(0, TimeUnit.MILLISECONDS));
    }

    @Test
    void barrierTimeoutBreaksCurrentGeneration()
            throws Exception {
        CyclicBarrier barrier = new CyclicBarrier(2);

        assertThrows(
                TimeoutException.class,
                () -> barrier.await(
                        1, TimeUnit.MILLISECONDS));

        assertTrue(barrier.isBroken());

        assertThrows(
                BrokenBarrierException.class,
                () -> barrier.await(
                        1, TimeUnit.MILLISECONDS));

        barrier.reset();
        assertFalse(barrier.isBroken());
    }
}
```

**Four JUnit methods**:

1. `gateReleasesBothWorkers` checks that both workers finish after the gate.
2. `barrierCanBeReusedAcrossTwoPhases` checks that the same barrier trips twice.
3. `latchIsOneShot...` proves the count does not go negative and `await` returns true once count reaches 0.
4. `barrierTimeoutBreaksCurrentGeneration` intentionally creates a 2-party barrier with only **one caller**, so it times out; the broken barrier makes the next `await` throw `BrokenBarrierException`, and `reset()` restores the unbroken state.

**No Spring or Docker needed.** Tests use timeouts to prevent hangs, except the fourth test which **intentionally tests timeout** when no second party exists. They do not depend on background task latency.

**Do not abuse `reset()` in production**: resetting while other parties are waiting can cause them to fail. Here no other threads exist, so testing `reset` is safe.

## 12. Reproducing races intentionally instead of relying on timing

Concurrency tests often want to catch **lost updates**, double booking, or overselling. If two futures run concurrently without locking the read/write point, the race might occur 1 in 1,000 times or never. For an accurate test, use two latches to **force both workers to read the same snapshot before writing**.

Suppose inventory has exactly 1 item left. Buggy code:

```java
int observed = remaining.get();
if (observed > 0) {
    remaining.set(observed - 1);
    return true;
}
return false;
```

This is an **illustrative buggy algorithm**. `AtomicInteger.get()` and `set()` are individually thread-safe, but the **get–check–set sequence is not atomic**. Two threads can both read 1 and both return true, even though only one item exists.

### RaceConditionTest.java — two controlled tests

Create `src/test/java/example/concurrency/RaceConditionTest.java`:

```java
package example.concurrency;

import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RaceConditionTest {

    @Test
    void gatesReproduceLostUpdateDeterministically()
            throws Exception {
        AtomicInteger stock = new AtomicInteger(1);
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);
        ExecutorService pool =
                Executors.newFixedThreadPool(2);

        Callable<Boolean> unsafe = () -> {
            int snapshot = stock.get();
            bothRead.countDown();

            if (!release.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "release gate timed out");
            }

            if (snapshot <= 0) {
                return false;
            }

            stock.set(snapshot - 1); // Intentionally wrong.
            return true;
        };

        try {
            Future<Boolean> one = pool.submit(unsafe);
            Future<Boolean> two = pool.submit(unsafe);

            assertTrue(
                    bothRead.await(5, TimeUnit.SECONDS));

            release.countDown();

            assertTrue(one.get(5, TimeUnit.SECONDS));
            assertTrue(two.get(5, TimeUnit.SECONDS));

            // Both report selling an item, even though stock had only 1.
            assertEquals(0, stock.get());
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }

    private static boolean reserveSafely(
            AtomicInteger stock) {
        for (;;) {
            int current = stock.get();

            if (current <= 0) {
                return false;
            }

            if (stock.compareAndSet(
                    current, current - 1)) {
                return true;
            }
        }
    }

    @Test
    void compareAndSetPreventsDoubleReservation()
            throws Exception {
        AtomicInteger stock = new AtomicInteger(1);
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);
        ExecutorService pool =
                Executors.newFixedThreadPool(2);

        Callable<Boolean> safe = () -> {
            ready.countDown();

            if (!release.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "release gate timed out");
            }

            return reserveSafely(stock);
        };

        try {
            Future<Boolean> one = pool.submit(safe);
            Future<Boolean> two = pool.submit(safe);

            assertTrue(
                    ready.await(5, TimeUnit.SECONDS));
            release.countDown();

            int successes =
                    (one.get(5, TimeUnit.SECONDS) ? 1 : 0)
                    + (two.get(5, TimeUnit.SECONDS)
                            ? 1 : 0);

            assertEquals(1, successes);
            assertEquals(0, stock.get());
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
```

**These two tests share the same 2-thread environment but reach two different conclusions:**

- The first test **actively proves the bug**: before release, both took `snapshot=1`. After release, both return true; this is overselling. Test pass means **the bug reproducer works**, not that the unsafe code is correct.
- The second test uses a CAS loop `compareAndSet(expected, update)`; only one worker can transition stock from 1 to 0. The other worker sees 0 or fails CAS, retries, and returns false. Test pass means the invariant "only one reservation succeeds" holds in this scenario.

**What the test does NOT prove:** CAS is not a solution for every distributed inventory system. Across multiple processes/instances, you need DB atomic updates, optimistic/pessimistic locking, or an appropriate distributed consistency strategy. Latches in JUnit do not replace production database transaction isolation.

## 13. Spring Boot: enabling @Async and @Scheduled intentionally

Create `src/main/java/example/concurrency/CoordinationApplication.java`:

```java
package example.concurrency;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableAsync
@EnableScheduling
public class CoordinationApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                CoordinationApplication.class, args);
    }
}
```

- `@EnableAsync` turns on Spring interception for `@Async` methods.
- `@EnableScheduling` lets Spring discover `@Scheduled` methods on created beans.
- This **does not mean arbitrary methods run on a background thread**: you must call through the Spring proxy for `@Async`; scheduled methods are invoked by the Spring scheduler per trigger.
- In tests, the example's scheduler bean is created only when `lesson.scheduler.enabled=true`, preventing background timing from interfering with other tests.

**Self-invocation pitfall:** if a bean calls `this.asyncMethod()` inside itself, the call normally **bypasses the proxy** in default mode, so `@Async` may not apply. The example below separates the test from the service and asserts thread names/receipts to catch misconfiguration.

## 14. Configuring a dedicated executor with enough workers

Create `src/main/java/example/concurrency/AsyncPoolConfig.java`:

```java
package example.concurrency;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class AsyncPoolConfig {

    @Bean(name = "lessonExecutor")
    public ThreadPoolTaskExecutor lessonExecutor() {
        ThreadPoolTaskExecutor pool =
                new ThreadPoolTaskExecutor();

        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(2);
        pool.setQueueCapacity(8);
        pool.setThreadNamePrefix("lesson-worker-");
        pool.initialize();

        return pool;
    }
}
```

There are **2 worker threads**, so two `@Async("lessonExecutor")` tasks can arrive at the gate concurrently. `ThreadPoolTaskExecutor` is managed by Spring, so the pool closes when `ApplicationContext` terminates.

**Why declare `queueCapacity`?** A thread pool may queue a third task instead of spawning another thread. When a test requires N workers to be blocked at a latch simultaneously, ensure **`corePoolSize >= N`** or appropriate worker capacity. `maxPoolSize=10` does not guarantee 10 workers will run when the queue is large; in `ThreadPoolTaskExecutor`, queuing affects when the pool grows.

**Do not blindly rely on the common `ForkJoinPool`** for a test requiring an exact worker count. Declaring a dedicated executor makes tests clearer and reduces interference from other tasks in the process.

## 15. ControlledAsyncService: checkpoint inside an @Async method

Create `src/main/java/example/concurrency/ControlledAsyncService.java`:

```java
package example.concurrency;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ControlledAsyncService {

    public record Receipt(
            String jobId, String threadName) {
    }

    @Async("lessonExecutor")
    public CompletableFuture<Receipt> awaitRelease(
            String jobId,
            CountDownLatch reached,
            CountDownLatch release,
            long waitMillis) {

        reached.countDown();

        try {
            if (!release.await(
                    waitMillis,
                    TimeUnit.MILLISECONDS)) {
                throw new IllegalStateException(
                        "worker release timed out");
            }
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "worker interrupted", error);
        }

        return CompletableFuture.completedFuture(
                new Receipt(
                        jobId,
                        Thread.currentThread().getName()));
    }
}
```

**This is an illustrative test seam**, not advice to pass `CountDownLatch` in production business APIs. The class aims to verify that Spring `@Async` truly runs via the executor, the gate works, and timeouts throw an observable exception.

Points easily confused:

- `awaitRelease(...)` has `@Async("lessonExecutor")`, so the caller gets a `CompletableFuture<Receipt>` from Spring's async invocation.
- Inside the target method, returning `CompletableFuture.completedFuture(...)` is valid with Spring `@Async` — the proxy manages the outer asynchronous result.
- `reached.countDown()` marks that the worker entered the method **before waiting on `release`**.
- `release.await(waitMillis, MILLISECONDS)` has a finite timeout; if false, throws `IllegalStateException`.
- If interrupted, preserve the interrupted status and finish with an exception. Do not swallow interruption.
- Thread names start with `lesson-worker-` when actually executed by the example's executor.
- A future completed exceptionally can still be observed via `future.get(...)`; exceptions are normally wrapped in `ExecutionException`.
- If an `@Async` method returns `void`, the caller cannot retrieve failures through a `Future`; when testing async errors, use `Future`/`CompletableFuture` or a controlled error callback channel.

## 16. ControlledAsyncServiceTest: JUnit integration with a real executor

Create `src/test/java/example/concurrency/ControlledAsyncServiceTest.java`:

```java
package example.concurrency;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment =
                SpringBootTest.WebEnvironment.NONE)
class ControlledAsyncServiceTest {

    @Autowired
    private ControlledAsyncService service;

    @Test
    void bothWorkersWaitUntilTestOpensGate()
            throws Exception {
        CountDownLatch reached =
                new CountDownLatch(2);
        CountDownLatch release =
                new CountDownLatch(1);

        CompletableFuture<ControlledAsyncService.Receipt>
                first = service.awaitRelease(
                        "first", reached, release, 10_000);

        CompletableFuture<ControlledAsyncService.Receipt>
                second = service.awaitRelease(
                        "second", reached, release, 10_000);

        try {
            assertTrue(
                    reached.await(5, TimeUnit.SECONDS));

            assertFalse(first.isDone());
            assertFalse(second.isDone());
        } finally {
            release.countDown();
        }

        ControlledAsyncService.Receipt firstReceipt =
                first.get(5, TimeUnit.SECONDS);
        ControlledAsyncService.Receipt secondReceipt =
                second.get(5, TimeUnit.SECONDS);

        assertEquals("first", firstReceipt.jobId());
        assertEquals("second", secondReceipt.jobId());

        assertTrue(firstReceipt.threadName()
                .startsWith("lesson-worker-"));
        assertTrue(secondReceipt.threadName()
                .startsWith("lesson-worker-"));
    }

    @Test
    void gateTimeoutCompletesFutureExceptionally()
            throws Exception {
        CountDownLatch reached =
                new CountDownLatch(1);
        CountDownLatch release =
                new CountDownLatch(1);

        CompletableFuture<ControlledAsyncService.Receipt>
                future = service.awaitRelease(
                        "timeout", reached, release, 30);

        try {
            assertTrue(
                    reached.await(5, TimeUnit.SECONDS));

            ExecutionException failure = assertThrows(
                    ExecutionException.class,
                    () -> future.get(5, TimeUnit.SECONDS));

            assertInstanceOf(
                    IllegalStateException.class,
                    failure.getCause());
        } finally {
            release.countDown();
        }
    }
}
```

**Two JUnit integration methods** actually create the Spring context and invoke the `@Async` bean through its proxy:

1. **Two workers gate:** when `reached.await(...)` returns true, both workers have entered the method and are waiting on release. The test observes the Futures are not yet done, opens `release` in `finally`, then retrieves receipts and asserts thread names match the executor.
2. **Timeout observable:** the worker is given a short 30 ms timeout and does not receive `release` until the failed Future is observed. The test asserts `ExecutionException` with cause `IllegalStateException`, ensuring no background error gets "logged and lost".

**No `Thread.sleep`**, no asserting exact milliseconds, no dependence on completion order between `first` and `second`. The scope of this test is verifying **gating and executor boundary**, not proving other application business logic.

**Dual-timeout note:** `await(30, MILLISECONDS)` is the **worker gate** timeout, whereas `future.get(5, SECONDS)` is the **test's wait** timeout. If `get(...)` times out, that is a different error from `IllegalStateException` thrown by the worker. Do not lump both situations into one assertion.

## 17. @Scheduled: separate logic from trigger, do not sleep waiting for cron

For scheduled jobs, separate two responsibilities:

- **Business logic**: a service method tested directly with unit tests/JDBC integration tests.
- **Trigger/scheduler wiring**: does Spring invoke the `@Scheduled` method? When verification is truly needed, use a **signal with a timeout** instead of sleep.

In the sample project, we build a thread-safe probe: the test "arms" a latch and the job signals on tick. The probe **does not store an unbounded list of ticks** and does not depend on whether a tick happened before the test started.

### ScheduledProbe.java

Create `src/main/java/example/concurrency/ScheduledProbe.java`:

```java
package example.concurrency;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.stereotype.Component;

@Component
public class ScheduledProbe {
    private final AtomicReference<CountDownLatch> armed =
            new AtomicReference<>();

    public void arm(CountDownLatch latch) {
        armed.set(latch);
    }

    public void seenTick() {
        CountDownLatch latch =
                armed.getAndSet(null);

        if (latch != null) {
            latch.countDown();
        }
    }

    public void clear(CountDownLatch latch) {
        armed.compareAndSet(latch, null);
    }
}
```

`AtomicReference` is required because the scheduler thread reads/writes separately from the test thread. `getAndSet(null)` atomically claims an armed latch once; if another tick occurs before the test arms again, it does not decrement an old latch. This signals **at most one tick per arm**, not a metric counting all job executions.

### ScheduledHeartbeat.java

Create `src/main/java/example/concurrency/ScheduledHeartbeat.java`:

```java
package example.concurrency;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(
        name = "lesson.scheduler.enabled",
        havingValue = "true")
public class ScheduledHeartbeat {
    private final ScheduledProbe probe;

    public ScheduledHeartbeat(ScheduledProbe probe) {
        this.probe = probe;
    }

    @Scheduled(
        fixedDelayString =
                "${lesson.scheduler.delay-ms:1000}")
    public void tick() {
        probe.seenTick();
    }
}
```

The `@Scheduled` method is **no-arg, void**, invoked by Spring's scheduler. `fixedDelay` measures the interval **after the previous execution finishes** until the next begins, while `fixedRate` targets start times at a fixed period. Neither guarantees callbacks fire at exact milliseconds under GC/load, and overlap depends on scheduler configuration, task duration, and triggers.

**Important:** this component exists only when `lesson.scheduler.enabled=true`. In tests focused only on `@Async`, the scheduler bean is absent, preventing unrelated background tasks from running. For cron expressions, timezone/DST also need testing per zone/clock policy; a latch only proves a tick fired, not that an entire cron calendar is accurate.

## 18. ScheduledHeartbeatTest: smoke test for real scheduler

Create `src/test/java/example/concurrency/ScheduledHeartbeatTest.java`:

```java
package example.concurrency;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.annotation.DirtiesContext;

import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment =
                SpringBootTest.WebEnvironment.NONE,
        properties = {
                "lesson.scheduler.enabled=true",
                "lesson.scheduler.delay-ms=50"
        })
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ScheduledHeartbeatTest {

    @Autowired
    private ScheduledProbe probe;

    @Test
    void scheduleInvokesJobWithoutThreadSleep()
            throws Exception {
        CountDownLatch nextTick =
                new CountDownLatch(1);

        probe.arm(nextTick);

        try {
            assertTrue(
                    nextTick.await(5, TimeUnit.SECONDS));
        } finally {
            probe.clear(nextTick);
        }
    }
}
```

**One JUnit integration method** proves the Spring scheduler **invoked it at least once** after the test armed the latch. It does not assert the exact period is 50 ms, does not assert a tick count over a wall-clock window, and does not depend on whether a tick happened *before* the test started. If the job already ran before arming, the test waits for the next tick.

`@DirtiesContext(AFTER_CLASS)` closes the context and scheduler after this test class, preventing a short-interval task from keeping on ticking when other tests use Spring context caching. This is a **real trigger smoke test** with a 5-second max timeout. It still depends on the real scheduler, so results can be affected under heavy CI load; that is one reason not to use this integration test style for **every** business job assertion.

### Testing scheduled job logic independently

In complex production code, `ScheduledHeartbeat.tick()` should call a service containing the real logic. A JUnit unit test can instantiate the target bean with a mock service and call `tick()` directly to verify delegation; that is a **logic unit test**, not proof that the cron/`fixedDelay` trigger works. In the example, the probe is a test seam and not a place for business transactions.

**Do not use `@Scheduled` as a precision timer** for financial/payment/order-cutoff transactions: you need deadline/clock semantics, idempotency, distributed locks, or job queues per SLA.

## 19. Transactions across threads: latches do not propagate Spring transactions

A critical realization in **Spring Boot - testing**: a Spring test-managed transaction on an `@Transactional` JUnit test with JDBC is normally **bound to the current thread**.

```text
JUnit test thread                 @Async worker thread
----------------                 --------------------
BEGIN test-managed tx
  |
  +-- submit @Async ------>       work begins
  |                                new thread
  |                                not joined test tx
  |                                own @Transactional
  |                                  if service proxy configured
  |
ROLLBACK test tx                 worker commits separately
```

`CountDownLatch` and `CyclicBarrier` can coordinate **when** operations run, but **do not move JDBC connections/transaction state across threads**. If the worker calls an `@Transactional` service bean through a Spring proxy, that service may open its own transaction and commit; the JUnit thread's rollback will not undo that committed row.

**This impacts cleanup:** with real `@Async`/HTTP, do not have `@AfterEach` inside a test-managed transaction delete committed rows thinking cleanup is durable. The DELETE may be rolled back. Use a dedicated test database, distinct keys, end the test transaction, and perform independent cleanup when workflows write to a real DB.

**The runnable suite in this lesson has no DB.** The tests check thread coordination and scheduling. The transaction discussion in this section is a **boundary to keep in mind**, not a claim that this lesson verified DB rollback.

Reactive transactions also differ: Spring reactive infrastructure typically carries context through Reactor Context rather than conventional JDBC ThreadLocal. Do not apply observations about test-managed JDBC transactions verbatim to all reactive pipelines.

## 20. Timeout, interruption, and proper error handling

### CountDownLatch timeout returns boolean

```java
if (!ready.await(5, TimeUnit.SECONDS)) {
    throw new AssertionError(
            "workers never reached checkpoint");
}
```

If you merely call `ready.await(5, SECONDS);` and **ignore the return value**, the test can proceed as if the gate opened even though it timed out.

### CyclicBarrier timeout throws an exception

```java
try {
    barrier.await(5, TimeUnit.SECONDS);
} catch (TimeoutException error) {
    // This generation is broken; coordinate shutdown
}
```

This is a snippet requiring imports and a declared barrier. Do not continue executing logic that depends on a broken barrier. If calling `reset()`, ensure other parties are no longer waiting on the old generation or have been notified of the failure.

### Interruption is not an "ignorable error"

Java workers commonly handle it like this:

```java
try {
    release.await(5, TimeUnit.SECONDS);
} catch (InterruptedException error) {
    Thread.currentThread().interrupt();
    return;
}
```

This is a snippet for a `void` method/matching lambda. Restore the interrupt flag or propagate the checked exception per contract. **Do not catch and ignore**, because shutdown/cancellation may stop working and tests can hang during teardown.

### Future.get brings exceptions back to the test

- `Future.get(timeout)` can throw `TimeoutException`, `ExecutionException`, `InterruptedException`.
- `ExecutionException.getCause()` lets the test inspect the worker's root error.
- `future.cancel(true)` requests an interrupt if possible, yet **does not guarantee the task stopped immediately**; the task may ignore interruption.
- `CompletableFuture.join()` has no timeout in its basic overload and typically wraps exceptions in `CompletionException`; in tests needing bounded waits, prefer `get(timeout)`.
- `CompletableFuture.allOf(...)` combines multiple tasks, but if you need per-task/ID errors, inspect each `Future`/cause individually.

### Teardown when an assertion fails

```java
try {
    assertTrue(ready.await(5, TimeUnit.SECONDS));
    // inspect state, prepare worker to proceed
} finally {
    release.countDown();
    pool.shutdownNow();
}
```

Without `finally`, a failing assertion can leave workers stuck in `await()`, preventing the test process from exiting. For production-quality cleanup, add `awaitTermination(timeout)`, thread dump diagnostics, and clear resource lifecycles. Do not put an unbounded wait inside cleanup to "fix" timeout errors.

## 21. Executor starvation and miscounted parties

A classic deadlock:

```java
ExecutorService oneThread =
        Executors.newSingleThreadExecutor();
CountDownLatch reached = new CountDownLatch(2);
CountDownLatch release = new CountDownLatch(1);

// Submit 2 tasks; the first task waits on release.
// The second task sits in the queue.
// The test waits for reached == 0 before releasing.
```

This is a **structural anti-pattern**, not a complete runnable test. It can never finish because the sole thread is blocked while the second task has not started. Solutions:

- Increase worker capacity enough for all blocking parties to run concurrently, or
- Restructure the flow so it does not block the whole pool while required tasks remain queued, or
- Use a different coordination fit for an asynchronous/nonblocking design.

Party-count errors:

- `new CountDownLatch(3)` with only two actual `countDown()` calls → test times out.
- A worker calls `countDown()` **twice** in one branch and misses it in another → the latch no longer represents "N workers".
- `CyclicBarrier(3)` with only 2 workers calling `await()` → timeout/broken.
- The test thread is counted as a party yet never calls `await()`.
- Worker A waits at barrier phase 1 while worker B hits barrier phase 2 on different code branches → generation mismatch.
- `Phaser.register()` while forgetting `arrive()/deregister()` on task failure → phase stalls.
- A task annotated `@Async` actually runs synchronously due to self-invocation → the test can even block directly inside the call before submitting the next task.

**Do not fix by raising the timeout from 5 seconds to 5 minutes** when there is a party count or pool starvation bug. Draw the waits-for graph.

## 22. Happens-before does not mean atomicity or arbitrary ordering

Concurrency primitives provide memory visibility per the Java Memory Model, but do not make compound operations atomically correct.

Race example from Section 12:

```text
Worker A                    Worker B
--------                    --------
read stock = 1              read stock = 1
    |                            |
bothRead.countDown()        bothRead.countDown()
    |                            |
wait release                wait release
    |                            |
write stock=0               write stock=0
return true                 return true
```

The latch guarantees both read the snapshot before the test opened release; yet nothing enforces **only one worker may decide "sold"**. Thus both workers logically succeed even though stock started at 0 remaining after one sale.

Fix with `AtomicInteger.compareAndSet` for single-process code, or appropriate transactions/constraints when multiple JVMs are involved. What the test controls is **interleaving to reproduce the bug**, not fixing business logic.

Also avoid asserting that `Thread.currentThread().getName()` follows an increasing order, as names are metadata. In Spring async integration tests, only assert the **prefix** to prove the right executor was selected, without relying on exact thread suffixes.

### Visibility once CountDownLatch reaches 0

Per the JMM, actions before `countDown()` happen-before actions after a successful `await()` on another thread. However, if the worker keeps mutating shared state **after `countDown`**, the test can still read state mid-modification. To assert final state, wait for **Future completion**, a done latch in `finally`, or synchronization marking the true completion point.

## 23. @Scheduled and scheduling properties beyond latch scope

`CountDownLatch` helps tests verify **the job ran at least once**, not every property of a scheduler:

- **`fixedRate`:** targets interval between start times; can drift when tasks run long or the scheduler is overloaded.
- **`fixedDelay`:** waits an interval after the previous execution completes.
- **`cron`:** depends on zone, DST, and clock; cron expression correctness should be tested via schedule-calculation logic or controlled `Clock` when needed.
- **scheduler pool:** a single scheduler thread serializes tasks; multiple workers/schedulers can run concurrently if configured.
- **distributed deployment:** multiple application instances enabling a scheduled job can execute simultaneously; `@Scheduled` is not a distributed lock by default.
- **transactions:** scheduled jobs run on scheduler threads and do not inherit test-managed JDBC transactions.
- **runtime errors:** exceptions from scheduled tasks may be logged while subsequent triggers continue depending on scheduler/error handler; tests must observe failures per policy.
- **graceful shutdown:** running background tasks need clear termination/ownership policies.

Do not write a unit test calling `job.tick()` and say "cron ran on schedule". And do not write a real scheduled test with `Thread.sleep(1000)` asserting an exact tick count when cron/delay are subject to load. For complex scheduling contracts, prefer injecting `Clock`, testing pure-Java schedule calculations, or using framework-version-appropriate scheduler test utilities.

## 24. Separating test levels: unit, integration, and end-to-end

| Level | How it is tested | What it proves | What it does NOT prove |
| --- | --- | --- | --- |
| Java SE unit | `GateCoordinatorTest` | Latch/barrier logic and in-JVM visibility contracts | Spring proxy/scheduler |
| Race reproduction | `RaceConditionTest` | Buggy interleaving and CAS within one JVM | Cross-process database concurrency |
| Spring async integration | `ControlledAsyncServiceTest` | `@Async` via executor, threads/gates/Future errors | Real DB/HTTP/sockets |
| Spring schedule integration | `ScheduledHeartbeatTest` | Spring trigger invokes at least one tick | All cron/DST/SLO behavior |
| Database integration | SQL + transactions + concurrency barriers | Engine locks/constraints/isolation | Side effects outside DB |
| Full E2E | App + broker/HTTP/DB | Workflow outcome under real setup | All production failure windows |

**Not all concurrency tests need to start a Spring context.** When an algorithm only uses Java `AtomicInteger` or `CyclicBarrier`, plain JUnit is faster and easier to diagnose. Start Spring only when testing real scheduling/async proxy/bean lifecycle.

**Do not use `@MockBean`/`@MockitoBean` just to speed up tests at the cost of losing the boundary**: mocking the executor or service can eliminate actual execution on another thread. Mocks are great for business logic, not for proving thread switching.

## 25. Running the tests

From the project root with a Gradle wrapper:

```bash
./gradlew test --tests example.concurrency.GateCoordinatorTest
./gradlew test --tests example.concurrency.RaceConditionTest
./gradlew test --tests example.concurrency.ControlledAsyncServiceTest
./gradlew test --tests example.concurrency.ScheduledHeartbeatTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.concurrency.GateCoordinatorTest"
.\gradlew.bat test --tests "example.concurrency.RaceConditionTest"
.\gradlew.bat test --tests "example.concurrency.ControlledAsyncServiceTest"
.\gradlew.bat test --tests "example.concurrency.ScheduledHeartbeatTest"
```

**Method counts:**

| Test class | Methods | Needs Spring? |
| --- | ---: | --- |
| `GateCoordinatorTest` | 4 | No |
| `RaceConditionTest` | 2 | No |
| `ControlledAsyncServiceTest` | 2 | Yes, to test @Async proxy |
| `ScheduledHeartbeatTest` | 1 | Yes, to test scheduler |
| **Total** | **9** | |

These are **expected outcomes when the project and runtime are configured properly**, not a claim that JUnit was executed in the learner's environment. Gradle/JUnit console output varies by version/runner/logging, so there is no single universal stdout. Only the Java SE demo in Section 10 has deterministic stdout once both operations finish within the timeout.

When running the full suite, keep Spring TestContext caching and the scheduled test's `@DirtiesContext` in mind. If a real project uses a database or shared static state, each test needs isolated data and cleanup rather than relying on method order.

## 26. Diagnosing failures by symptom

**A. `await(timeout)` returns false.** Not enough `countDown()` calls arrived; check counts, submitted tasks, exception branches, pool capacity, and checkpoint placement.

**B. `Future.get(...)` throws `TimeoutException`.** The task did not finish within the limit. Check if it is blocked on a gate, barrier, I/O, or queue; do not assume a Future timeout cancels the task.

**C. `ExecutionException`.** The worker threw an error; inspect `getCause()` before changing timeouts.

**D. `BrokenBarrierException`.** A party was interrupted, timed out, or reset, breaking the barrier generation; log parties/generation and coordinate shutdown.

**E. `CyclicBarrier` never trips.** Wrong party count or insufficient executor workers; the test thread might have been miscounted.

**F. `Phaser` does not advance.** A party registered without arriving/deregistering, or termination/phase management is wrong.

**G. `@Async` method runs on the main/JUnit thread.** `@EnableAsync` is not active, missing executor bean, or self-invocation via `this.method()`, bypassing the Spring proxy.

**H. `@Scheduled` test passes when calling the method directly, but the trigger never fires.** Missing `@EnableScheduling`, bean excluded by `@ConditionalOnProperty`, wrong cron/zone, or scheduler not ready.

**I. Test passes in isolation, fails in full suite.** Shared static state, context cache, lingering async tasks, pool starvation, parallel JUnit, or improper cleanup.

**J. Thread leak / JVM fails to exit after failure.** Workers stuck on `await()` because the test did not release in `finally`; executor not shut down.

**K. Test asserts wrong ticket/reservation count.** Non-atomic check-then-set; use CAS/locks/transactions instead of adding more latches.

**L. Test has `@Transactional`, yet async DB row persists.** The worker did not join the test transaction thread; clean up in an independent transaction and verify after-commit state.

## 27. Common mistakes to avoid

**1. `Thread.sleep` to wait for async work.** Fixed durations do not synchronize with actual completion.

**2. Calling `await(timeout)` and ignoring the boolean.** The test may continue despite timing out.

**3. Using unbounded `await()` in CI.** Deadlocks hang the job.

**4. Forgetting `release.countDown()` in `finally`.** Assertion failures leave workers waiting forever.

**5. Miscounting parties.** `CountDownLatch(3)` with only 2 signals; `CyclicBarrier(3)` with only 2 `await` callers.

**6. Executor smaller than the number of blocked workers needed at the gate.** Tasks queue up and the test wait can never finish.

**7. Treating a latch countdown as proof the task succeeded.** A worker can `countDown()` and then throw; retrieve the `Future`.

**8. Reusing one `CountDownLatch` across rounds expecting automatic reset.** `CountDownLatch` is one-shot; use a new instance, `CyclicBarrier`, or `Phaser`.

**9. Calling `CyclicBarrier.reset()` while waiters are active without coordination.** Can break waiting generations.

**10. Using `getNumberWaiting`/`getCount` snapshots for state decisions.** Racy; use `await`/response synchronization.

**11. Using only `AtomicInteger.get` + `set` for read-modify-write.** Two individually atomic calls do not make the combination atomic.

**12. Claiming a race is fixed just because a 2-thread test passed a few times.** You need invariants, proper synchronization, and tests for relevant interleavings.

**13. Catching `InterruptedException` and ignoring it.** Breaks cancellation/shutdown and increases thread leaks.

**14. Future times out without cleanup/cancel.** The task may continue mutating state after the test fails.

**15. `@Async` self-invocation.** The annotation is not intercepted by the proxy; the method runs synchronously.

**16. `void @Async` fails unobserved by the test.** Use `CompletableFuture`/callbacks or an error handler.

**17. Mocking the entire service/executor when trying to test thread switching.** Mocks do not prove real executor behavior.

**18. Testing `@Scheduled` with sleep and asserting exact counts.** Wall-clock timing is unstable.

**19. Setting timeouts too small for CI capacity, or inflating timeouts to mask deadlocks.** Choose a reasonable budget and diagnose the waits-for graph.

**20. Using a latch hoping an async JDBC transaction joins the test transaction.** Timing coordination does not move transactions across threads.

**21. Failing to clean up scheduled contexts/test executors.** Background tasks outlive the method and break subsequent tests.

**22. Asserting stdout order from worker threads.** Schedulers do not guarantee ordering; print results from the coordinator or compare sets/maps.

**23. Using `@Timeout` preemptive thread mode without accounting for thread-bound transactions.** With Spring TestContext JDBC, callbacks on another thread can run outside the test transaction.

**24. Using a latch without placing the memory/side-effect checkpoint properly.** The test may receive the signal too early and read incomplete state.

## 28. Final QA checklist

**Primitive semantics:**

- Did you choose a one-shot latch vs a multi-phase barrier appropriately for the problem?
- If using `Phaser`, do parties register/deregister accurately?
- Does `CountDownLatch` have the exact signal count? Does the barrier have the exact `await` caller count?
- Do you distinguish non-blocking `countDown()` from blocking `CyclicBarrier.await()`?

**Test orchestration:**

- Are both ready/release latches created before submitting tasks?
- Do workers signal the checkpoint right before blocking at the intended place?
- Does the executor have enough workers for all parties to reach the barrier?
- Do all `await`/`get` calls have finite timeouts, except where owner cleanup is proven?
- Are boolean `await` returns asserted and `Future` exceptions inspected?
- Is `release.countDown()` in `finally` and is the executor shut down?
- Is interruption restored properly?

**Concurrency correctness:**

- Is shared state protected with real atomics/locks/transactions?
- Does the test intentionally reproduce races via controlled interleaving rather than running 100 times by luck?
- Do assertions avoid depending on scheduling order, timing, or exact thread names?
- Do you distinguish a test passing as a bug reproducer vs verifying a fix?
- Do you await a **completion signal** when checking final state, rather than just a started signal?

**Spring Boot:**

- Are `@EnableAsync`, `@Async("lessonExecutor")`, and the bean proxy working?
- Are `@EnableScheduling` and scheduling enablement properties scoped properly?
- Does the `@Scheduled` test verify real triggers via latch instead of `Thread.sleep`?
- Do background tasks have explicit cleanup and context lifecycles?
- Does `@Transactional` in tests ensure `@Async` side effects stay in the intended transaction, or do they need independent DB cleanup?

**Conclusion:** `CountDownLatch`, `CyclicBarrier`, and `Phaser` give tests **explainable, repeatable thread coordination**. `CountDownLatch` fits one-shot gates/counters; `CyclicBarrier` fits multiple rounds with fixed parties; `Phaser` fits parties changing across phases. Good coordination does not stop at `await()`: it requires **timeouts, Future exceptions, `finally` releases, executor cleanup, isolation, and atomic state**. When testing Spring `@Async` and `@Scheduled`, observe real executor/scheduler behavior without relying on sleep or assuming transactions moved onto worker threads.

## 29. References

- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): one-shot latch, timed await, and happens-before.
- [Java SE 17 — CyclicBarrier](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CyclicBarrier.html): parties, generations, barrier action, broken state, and reset.
- [Java SE 17 — Phaser](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Phaser.html): registering/deregistering parties, phases, termination, timed wait.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): submit, Future, shutdown, awaitTermination.
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): asynchronous results, errors, and completion.
- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html): `TaskExecutor`, `@EnableAsync`, `@Async`, `@Scheduled`, proxies, and schedulers.
- [Spring Boot 3.5 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html): auto-configuration and executor customization.
- [Spring Framework — Test-managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): thread-bound test transactions and preemptive timeouts.