# JUnit Jupiter: Timeouts and the Difference Between Regular and Preemptive Timeouts

## 1. Understanding the true goal of timeouts in testing

A test may produce the **correct result** yet take far too long due to deadlocks, broken polling, hung I/O, or pathological algorithms. JUnit Jupiter provides mechanisms to set a **time budget** and fail the test when that budget is exceeded.

Two ideas are frequently confused:

- **Regular (non-preemptive) timeout:** lets the code under test run to completion, then checks whether it exceeded the limit. Typical API: `Assertions.assertTimeout(...)`.
- **Preemptive timeout:** monitors the deadline and **attempts to terminate waiting early** when time expires. Typical API: `Assertions.assertTimeoutPreemptively(...)`. Jupiter runs the callback on **another thread** and attempts to interrupt it once the deadline passes.

"Preemptive" here **does not mean forcibly and safely killing any arbitrary work**. Java `Thread.interrupt()` is cooperative: a task may respond and stop, or ignore the signal and keep running.

Separately, the `@Timeout` annotation behaves according to its `threadMode`. Do not assume `@Timeout` is identical to `assertTimeout`: in `SAME_THREAD` mode, Jupiter can **interrupt the test-executing thread** upon expiration, whereas `assertTimeout` deliberately waits for the callback to finish before evaluating elapsed time.

**Learning outcomes:** after this lesson, you can explain when failure occurs and which thread is used; pick `assertTimeout`, `assertTimeoutPreemptively`, or `@Timeout` for the right goal; recognize interruption limits; and avoid transaction rollback failures when combining Spring Boot with preemptive timeouts.

## 2. Comparing four key mechanisms

| Mechanism | Scope | Thread running the body | When limit is exceeded | Risks to remember |
| --- | --- | --- | --- | --- |
| `assertTimeout(duration, executable)` | A callback or code block | **Same thread** calling the assertion | Waits for callback to finish, then fails based on measured duration | Test can hang indefinitely if the callback never finishes |
| `assertTimeoutPreemptively(duration, executable)` | A callback or code block | **Different thread** | Assertion fails on expiration, tries to interrupt the callback thread | Callback may keep running; `ThreadLocal`/test-managed transactions do not carry over |
| `@Timeout(..., threadMode = SAME_THREAD)` | Annotated JUnit method | **Current test-executing thread** | Watcher tries to interrupt the thread after deadline; Jupiter records timeout | Interrupt is not guaranteed to stop uncooperative JDBC/network/logic |
| `@Timeout(..., threadMode = SEPARATE_THREAD)` | Annotated JUnit method | **Separate thread** | Tries to interrupt/records timeout on expiration | Same thread-bound context and side-effect risks as preemptive assertions |

Those two `@Timeout` options differ from `@Timeout.ThreadMode.INFERRED`: `INFERRED` is the default; it takes its decision from `junit.jupiter.execution.timeout.thread.mode.default`, and if unset or invalid, **falls back to `SAME_THREAD`**.

**Distinguish deadline checks from benchmarks:** timeout tests catch unacceptably slow work in a test environment; they are **not** accurate performance measurements or substitutes for profilers/microbenchmarks. CPU, CI load, GC, networking, and startup cause timings to fluctuate.

## 3. assertTimeout(): finish running, then evaluate

Import:

~~~java
import java.time.Duration;
import static org.junit.jupiter.api.Assertions.assertTimeout;
~~~

Use for an `Executable` callback with no return value:

~~~java
assertTimeout(Duration.ofSeconds(2), () -> {
    service.performOperation();
});
~~~

The snippet above is **illustrative code**: `service` must be provided by your project. If `performOperation()` runs for 2.3 seconds and returns normally, the assertion **fails after 2.3 seconds have elapsed**, rather than stopping the call right at second 2. If the method hangs forever, this assertion cannot free its calling thread either.

With a `ThrowingSupplier<T>`, the API also returns a value from the callback:

~~~java
int result = assertTimeout(
        Duration.ofSeconds(2),
        () -> Math.multiplyExact(12, 4));

assertEquals(48, result);
~~~

`assertEquals` in this snippet needs importing from `org.junit.jupiter.api.Assertions`. On success, the result is `48`. If the callback throws an unexpected exception, the test still fails; timeouts never turn business errors into passing outcomes.

A major advantage of `assertTimeout` is **keeping the code under test on the same thread**. Thread-bound contexts — such as certain `ThreadLocal` values or Spring TestContext-managed transactions — remain accessible inside the callback, provided the application code does not spawn another thread internally.

**When to choose:** testing services/validation/repositories inside the same test-managed transaction, checking a branch with an advisory deadline, or needing return values/exceptions without introducing a thread boundary.

**Limitations:** because it does not abort work early, it is insufficient as a hard hang guard for I/O calls that can block indefinitely. Add proper timeouts on the HTTP client, JDBC statement, socket, or broker itself; isolate into separate workers/processes when stronger isolation is required.

## 4. assertTimeoutPreemptively(): run on a separate thread and try to interrupt early

Import:

~~~java
import java.time.Duration;
import static org.junit.jupiter.api.Assertions.assertTimeoutPreemptively;
~~~

Example testing a pure calculation:

~~~java
int result = assertTimeoutPreemptively(
        Duration.ofSeconds(2),
        () -> Math.multiplyExact(12, 4));

assertEquals(48, result);
~~~

This snippet also returns `48` if completed in time. The big difference is **the callback runs on a worker thread separate from the assertion caller thread**. When the callback does not finish before the deadline, Jupiter flags a timeout and attempts to `interrupt()` the worker thread. Therefore the caller can receive a failure earlier than when the callback actually stops working.

Illustration assuming a task taking ~500 ms with a 100 ms limit:

| Milestone | `assertTimeout(100 ms)` | `assertTimeoutPreemptively(100 ms)` |
| --- | --- | --- |
| t = 0 | Starts callback immediately on caller thread | Dispatches callback to worker thread |
| t ≈ 100 ms | Callback still running; assertion keeps waiting | Detects expiration, tries to interrupt worker, returns timeout failure |
| t ≈ 500 ms | Callback finishes, assertion confirms overrun and fails | Worker **may have stopped** or **may still be running** if uncooperative with interrupt |

These milestones are a **conceptual model**, not a millisecond-accurate scheduling guarantee. OS scheduling and load can shift actual timings.

Why does "attempting to interrupt" not equal "canceled"?

- `Thread.sleep(...)`, `Object.wait(...)`, and *interruptible* blocking operations usually throw `InterruptedException`, letting the callback stop.
- CPU loops that do not check interrupt status can keep running.
- Certain I/O, native calls, or libraries may not react promptly to interrupts.
- Callbacks might catch `InterruptedException` and swallow it, continuing to write data or emit events.
- Side effects already performed **do not automatically roll back** just because the assertion reported a timeout.

Never use `assertTimeoutPreemptively` as a mechanism to manage transactions, cancel HTTP requests, or guarantee cleanup. If your intent is guarding against hangs in external resources, set timeouts and cancellation at the client/driver/protocol level, and verify whether post-cancellation state is safe.

## 5. @Timeout: method-level annotation with explicit thread modes

`@Timeout` is a **JUnit Jupiter** annotation, distinct from JUnit 4's `@Test(timeout = ...)`.

~~~java
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

class TimeoutAnnotationExamples {

    @Test
    @Timeout(value = 2, unit = TimeUnit.SECONDS,
             threadMode = Timeout.ThreadMode.SAME_THREAD)
    void sameThreadDeadline() {
        int result = Math.addExact(20, 22);
        org.junit.jupiter.api.Assertions.assertEquals(42, result);
    }

    @Test
    @Timeout(value = 2, unit = TimeUnit.SECONDS,
             threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
    void separateThreadDeadline() {
        int result = Math.addExact(20, 22);
        org.junit.jupiter.api.Assertions.assertEquals(42, result);
    }
}
~~~

This is a **standalone Java/JUnit annotation example** operating only on pure data, so both tests PASS. Explicitly writing `threadMode` shows readers the thread boundary rather than relying on defaults.

**Meaning:**

- `@Timeout(2)` defaults to `unit = TimeUnit.SECONDS`, thus representing a 2-second limit.
- `SAME_THREAD` runs the test method on the test thread; upon expiration, JUnit uses a monitor thread to **interrupt the thread running the test**. This is not identical to `assertTimeout`'s "wait until method finishes on its own".
- `SEPARATE_THREAD` runs the method on a separate thread and attempts to interrupt on expiration; it shares the same `ThreadLocal`, test transaction, and side-effect risks as `assertTimeoutPreemptively`.
- `INFERRED` is the default, reading `junit.jupiter.execution.timeout.thread.mode.default`; if missing/invalid, it chooses `SAME_THREAD`.

### @Timeout on classes and special cases

You can place `@Timeout` on a class to set a default limit for **test/test template/test factory methods** in that class, including `@Nested` classes, unless overridden by a more specific annotation. **Class-level annotations do not automatically apply to lifecycle methods** such as `@BeforeEach` and `@AfterEach`. You can attach `@Timeout` directly to a lifecycle method to bound that method itself, depending on Jupiter version support.

With `@ParameterizedTest` or `@RepeatedTest`, each invocation is timed independently. With `@TestFactory`, `@Timeout` on the factory only measures the time to **generate dynamic tests**, not the total execution time of the generated `DynamicTest` instances; use `assertTimeout(...)` or `assertTimeoutPreemptively(...)` inside each dynamic test if you want to bound execution.

Do not set overly tight deadlines on tests that boot containers/contexts or depend on CI; real execution speed depends on more than the Java logic inside the test method.

## 6. Complete Java 17+ example: observing the difference between the two threads

`src/test/java/example/TimeoutStrategiesTest.java` below contains five independent tests. The example requires a Java 17+ project with compatible JUnit Jupiter 5.x (typically provided via `spring-boot-starter-test` in Spring Boot). No Spring context, DB, HTTP server, or Docker is required.

~~~java
package example;

import java.time.Duration;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTimeout;
import static org.junit.jupiter.api.Assertions.assertTimeoutPreemptively;

@DisplayName("Comparing JUnit Jupiter timeouts")
class TimeoutStrategiesTest {

    private Thread testThread;

    @BeforeEach
    void rememberTestThread() {
        testThread = Thread.currentThread();
    }

    @Test
    @DisplayName("assertTimeout runs on the same calling thread")
    void nonPreemptiveUsesCallingThread() {
        Thread callbackThread = assertTimeout(
                Duration.ofSeconds(5),
                Thread::currentThread);

        assertSame(testThread, callbackThread);
    }

    @Test
    @DisplayName("assertTimeout returns a value from the supplier")
    void normalTimeoutReturnsValue() {
        int total = assertTimeout(
                Duration.ofSeconds(5),
                () -> Math.addExact(1_200, 800));

        assertEquals(2_000, total);
    }

    @Test
    @DisplayName("assertTimeoutPreemptively uses a different thread")
    void preemptiveUsesAnotherThread() {
        Thread callbackThread = assertTimeoutPreemptively(
                Duration.ofSeconds(5),
                Thread::currentThread);

        assertNotSame(testThread, callbackThread);
    }

    @Test
    @DisplayName("Caller's ThreadLocal is not automatically propagated to worker")
    void preemptiveDoesNotInheritThreadLocal() {
        ThreadLocal<String> trace = new ThreadLocal<>();
        trace.set("trace-42");

        try {
            String sameThreadValue = assertTimeout(
                    Duration.ofSeconds(5),
                    trace::get);

            String workerThreadValue = assertTimeoutPreemptively(
                    Duration.ofSeconds(5),
                    trace::get);

            assertEquals("trace-42", sameThreadValue);
            assertNull(workerThreadValue);
        } finally {
            trace.remove();
        }
    }

    @Test
    @Timeout(value = 5, unit = TimeUnit.SECONDS,
             threadMode = Timeout.ThreadMode.SAME_THREAD)
    @DisplayName("@Timeout SAME_THREAD preserves the test thread")
    void annotationSameThread() {
        assertSame(testThread, Thread.currentThread());
        assertEquals(6, Math.multiplyExact(2, 3));
    }
}
~~~

**Detailed analysis of the test:**

1. `rememberTestThread()` runs before each method, recording the current thread. Under the default lifecycle, test instances are not shared across methods.
2. `nonPreemptiveUsesCallingThread()` receives the exact `Thread` object back through `assertTimeout`. `assertSame` checks **object identity**, not merely thread name.
3. `normalTimeoutReturnsValue()` shows a supplier callback returning `2000`; Jupiter checks duration and returns the value when successful.
4. `preemptiveUsesAnotherThread()` calls `Thread.currentThread()` inside the callback. The result is a different thread from the one executing the test.
5. `preemptiveDoesNotInheritThreadLocal()` creates a regular `ThreadLocal` (not `InheritableThreadLocal`). The same-thread callback reads `trace-42`, while the callback on the new worker reads `null`. This is a miniature model of losing thread-bound context.
6. `annotationSameThread()` illustrates explicitly selecting `@Timeout(... SAME_THREAD)` in a test with setup and assertions.

**Execution expectation:** all **5 tests PASS** in a compatible JUnit Jupiter 5.x environment; they print no stdout. A 5-second threshold is generous for trivial operations, reducing CI jitter failures. They **do not benchmark algorithms** and intentionally avoid simulating hung tasks so the suite has no deliberate failures.

### Running with Gradle

In a Spring Boot project that already has the Gradle plugin and dependency management, `build.gradle` typically includes (this is a **configuration snippet**, not a complete build file):

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Run from the appropriate module/build root:

~~~bash
./gradlew test --tests example.TimeoutStrategiesTest
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests example.TimeoutStrategiesTest
~~~

When configured validly, Gradle/JUnit Platform discovers all five methods, the test task succeeds, and Gradle reports `BUILD SUCCESSFUL` if related tasks also succeed. There is no fixed exact stdout because IDE/Gradle log formats vary by environment.

In a real project, the business class under test must be the **production implementation** from `src/main/java`. The example above deliberately checks JUnit's timeout/thread semantics directly and therefore contains no Spring beans.

## 7. A critical risk in Spring Boot: losing test-managed transactions

Spring TestContext supports `@Transactional` testing: before invoking the test, the framework can open a **test-managed transaction** and roll it back when the test ends. Transaction state is bound to the **current thread** via `ThreadLocal` (e.g., context inside transaction synchronization).

Simple diagram:

~~~text
Test thread (Spring has bound transaction T1)
  |
  +-- assertTimeout(...) --------> service/repository uses T1
  |                                |__ test finishes -> T1 rolls back
  |
  +-- assertTimeoutPreemptively(...)
          |
          +-- Worker thread ------> DOES NOT have T1's ThreadLocal
                                      |__ service/repository may
                                          open another transaction and COMMIT
Test thread rolling back T1 cannot roll back writes committed on the worker.
~~~

Consequently, a test **can PASS or FAIL on timeout yet still leave data in the DB** if it executes write code on a worker thread. This is especially dangerous when a test suite shares a test database: subsequent tests can observe data leaked by earlier ones.

### Wrong usage (illustrative only, not a standalone Java file)

~~~java
// Inside a Spring test class with @Transactional and an injected OrderRepository:
@Test
void unsafePreemptiveWrite() {
    assertTimeoutPreemptively(Duration.ofSeconds(2), () -> {
        repository.save(new Order("ORD-100"));
    });
}
~~~

Here `repository` and `Order` are hypothetical application components; this snippet only illustrates an **anti-pattern**. If the repository uses an independent transaction on the worker, the write can commit even though the test thread's transaction rolls back. Never treat test-thread rollback as proof that worker-thread data was cleaned up.

### Better approach for transaction tests (illustrative)

~~~java
// Inside the same @Transactional Spring test class:
@Test
void usesTestManagedTransaction() {
    assertTimeout(Duration.ofSeconds(5), () -> {
        repository.save(new Order("ORD-100"));
        assertEquals(1, repository.count());
    });
}
~~~

`assertTimeout` runs the callback on the test thread, letting Spring-managed code participate properly in the test-managed transaction **if** propagation and application transaction settings are compatible. Spring can then roll back the transaction per its normal test contract.

Note: `assertTimeout` does not forcibly halt a hung query. If integration risks long I/O waits, add limits at the JDBC statement, connection/driver, HTTP client, or server level. For whole-method bounds, `@Timeout(threadMode = SAME_THREAD)` is generally safer for thread-bound context than `SEPARATE_THREAD`, though **interrupt still does not guarantee immediate cancellation of all I/O operations**.

**Nuance to understand:** this warning concerns *test-managed transactions*. Application-created transactions can have different propagation, and intentionally asynchronous code will likewise leave the test thread. Do not conclude "every call on a worker commits" in every setup; the accurate conclusion is **do not rely on the test thread's rollback covering a worker thread**.

## 8. Why do ThreadLocal, context, and side effects easily cause bugs?

Frameworks bind data to threads: transaction synchronization, some security contexts, MDC/correlation IDs, request data, locales, or tracing. Context on one thread **does not automatically** appear on another thread. Some libraries provide explicit propagation mechanisms, but you should never assume propagation works just because an API says "timeout".

Concrete impacts:

- In plain Java unit tests, a preemptive callback reading a `ThreadLocal` may receive `null` even though the caller thread set a value.
- In Spring integration tests, a repository/service called from a worker may not see the test's bound transaction.
- Tracing/logging contexts may lose correlation IDs, making reports hard to follow.
- Security contexts and request contexts may behave differently unless explicitly propagated.
- Async tasks spawned inside the callback can outlive the assertion and emit side effects after the test has moved on.

If the code under test **intentionally** runs asynchronously, use coordination mechanisms suited to that technology: `Future`/`CompletableFuture` with timeouts, interrupt-aware cancellation, HTTP/DB client timeouts, isolated test fixtures, and verifiable cleanup. Do not use `assertTimeoutPreemptively` to paper over task cancellation issues; preemptive assertions only provide a test signal.

## 9. Three right-choice scenarios in Spring Boot

### Scenario A: Plain Java logic unit test

For example, a service computing totals from in-memory data. Choose `assertTimeout(Duration.ofSeconds(...), () -> service.calculate(...))` to enforce a generous budget and assert results, since this is a simple same-thread call. If pure CPU logic risks an infinite loop and you genuinely need to fail fast, `assertTimeoutPreemptively` can help, **but only if you manage the possibility of the thread running forever after timeout**. For loops ignoring interrupts, the test runner may still hold resources.

### Scenario B: Repository integration test with @Transactional

Choose `assertTimeout` around the callback or `@Timeout(..., SAME_THREAD)` on the test method, and configure appropriate statement/driver timeouts. Verify rollback with dedicated integration tests when that is a key risk. Avoid `assertTimeoutPreemptively` or `@Timeout(..., SEPARATE_THREAD)` for code participating in test-managed transactions.

### Scenario C: HTTP calls or Kafka/Redis that may hang

Do not rely solely on a Jupiter timeout to guard infrastructure. Configure **connect timeout / read timeout / request timeout / transaction timeout** appropriately for the protocol and client, use test containers or stub servers when testing integration behavior, and put `@Timeout` on the method as a **final safety net** for the suite. A test-framework timeout does not replace network bounds, nor does it prove the system rolled back or canceled the request.

## 10. Default timeout configuration and debugging

JUnit Jupiter allows setting default timeouts in `src/test/resources/junit-platform.properties`. The example below is for projects using a Jupiter version supporting these configuration parameters:

~~~properties
# Default 5-second limit for test methods using @Test.
junit.jupiter.execution.timeout.test.method.default = 5 s

# Keep thread for INFERRED @Timeout when thread-bound context exists.
junit.jupiter.execution.timeout.thread.mode.default = same_thread

# Temporarily disable timeouts while a debugger (JDWP) is detected.
junit.jupiter.execution.timeout.mode = disabled_on_debug
~~~

Explanation:

- `junit.jupiter.execution.timeout.test.method.default` sets the default limit for `@Test` methods lacking a more specific timeout annotation. There are other scopes such as `...testable.method.default`, `...lifecycle.method.default`, and `...default`; more specific settings take precedence over broader ones.
- `junit.jupiter.execution.timeout.thread.mode.default` only determines the mode when the annotation uses `INFERRED`. It does not change the nature of `assertTimeoutPreemptively`: it **always runs the callback on a separate thread**.
- `disabled_on_debug` is helpful because hitting a breakpoint can make a test exceed its limit even when logic is correct. It detects debugging via JVM parameters; not "every IDE tool" is detected identically.
- You can use `enabled` or `disabled` for `junit.jupiter.execution.timeout.mode` per project policy; CI should keep sensible limits to catch hung tests.

**Do not adjust the entire suite just to patch one repeatedly failing test.** Diagnose the cause (DB locks, HTTP timeouts, CI machines, shared fixtures), then choose sensible thresholds for the right test group.

## 11. Timeouts can introduce flakiness if thresholds are poorly chosen

A test may sometimes PASS and sometimes FAIL when the threshold sits too close to normal execution time.

For example, do not set a 10 ms threshold for a test that boots a Spring context, talks to a DB container, or uses the network. On an idle local machine it may PASS, while under heavy CI load it will FAIL. Even plain Java tests occasionally experience GC or OS pauses.

Solutions based on the root cause:

1. **Measure and understand the path:** is the test waiting on files, DB, network, locks, or computation?
2. **Separate setup from execution:** apply `@Timeout` to the right scope; configure lifecycle timeouts separately if setup hangs.
3. **Choose deadlines with safety margin** based on real CI behavior instead of tuning down to the millisecond.
4. **Use fake clocks and wait conditions** when testing time-based logic: inject `Clock` for date/time business rules, and use condition-based waits instead of hardcoded `Thread.sleep`.
5. **When testing a client's own timeout behavior**, use a stub server or controlled fake clock to verify exceptions/cancellation without depending on millisecond scheduler precision.
6. **Do not use `assertTimeoutPreemptively` to hide design flaws:** put deadlines in the right places (SQL queries, retry policies, HTTP clients) to guarantee safety outside tests.

If a system needs p95/p99 latency measurements or microbenchmarks, use dedicated measurement tools and controlled environments; `assertTimeout` is a correctness guard and cannot represent production performance.

## 12. Common mistakes and how to avoid them

**1. Mistaking `assertTimeout` for a task-cancellation mechanism.** It waits for the callback to finish and then fails; hung tasks still hang the test. HTTP/DB time limits must be configured at the respective client layer.

**2. Thinking `assertTimeoutPreemptively` kills the thread.** It only attempts to interrupt; tasks ignoring interrupts can keep running after the assertion fails. Avoid callbacks with hard-to-undo side effects.

**3. Using preemptive timeouts in Spring `@Transactional` tests.** Worker callbacks do not inherit the original thread's test-managed transaction; writes may commit outside expected rollback. Prefer same-thread execution.

**4. Treating `@Timeout(SAME_THREAD)` as identical to `assertTimeout`.** Both keep the thread, but the annotation has a mechanism to **interrupt on expiration**, while the non-preemptive assertion checks after callback completion.

**5. Leaving thread mode blank and guessing.** `@Timeout` defaults to `INFERRED` and reads Jupiter config. Explicitly choose `SAME_THREAD` when it matters for Spring transactions.

**6. Reading `@Timeout(100)` as 100 ms.** The annotation's default unit is **seconds**, not milliseconds. Write `unit = TimeUnit.MILLISECONDS` when you mean 100 ms.

**7. Using JUnit 4's `@Test(timeout = 1000)` in Jupiter.** `org.junit.jupiter.api.Test` has no `timeout` attribute. Use `@Timeout`, `assertTimeout`, or `assertTimeoutPreemptively`.

**8. Assuming `@TestFactory` timeout covers every `DynamicTest`.** It only applies to the factory method. Execution limits must be placed inside each dynamic test.

**9. Catching `InterruptedException` and ignoring it.** The thread may continue past the deadline, causing leaks or unintended writes. When cooperative cancellation is genuinely needed, handle interruption per contract and clean up.

**10. Setting deadlines too close to typical runtime.** Causes CI flakiness. Pick generous margins or build tests with virtual time and deterministic synchronization.

**11. Thinking timeout implies rollback.** A timeout only signals elapsed time exceeded a limit; rollback, compensation, idempotency, and cleanup belong to transactions and business logic.

**12. Missing thread clues during diagnosis.** If transaction, context, or security failures only appear after switching to preemptive mode, check which thread the callback runs on and which contexts are bound/propagated.

## 13. Workflow for choosing timeouts when writing a new test

Start by asking "what happens if the code exceeds expected time?":

1. **Only need to report slow logic?** Use `assertTimeout` (same thread, completes then evaluates).
2. **Need to bound an entire method?** Use `@Timeout`; with thread-sensitive Spring contexts, explicitly choose `SAME_THREAD`.
3. **Need the caller not to wait past a deadline?** Only use `assertTimeoutPreemptively`/`SEPARATE_THREAD` when the callback is safe across threads and interrupts, does not rely on thread-bound transactions, and side effects/cleanup are controlled.
4. **Can I/O block indefinitely?** Add driver/protocol timeouts and proper cancellation; the test framework is an extra guardrail.
5. **Need to verify no side effects remain after timeout?** Test cancellation, cleanup, and durable state with appropriate integration tests; timeout assertions do not supply that evidence automatically.
6. **Does CI fluctuate?** Pick wide thresholds and observe real runs; never claim production performance from short tests.

### Pre-commit self-check list

- [ ] Clearly know whether the timeout uses `assertTimeout`, `assertTimeoutPreemptively`, or `@Timeout`.
- [ ] Know **which thread** the code runs on and whether thread-bound context is required.
- [ ] Understand whether exceeding the limit means *check after completion* or *attempt interrupt*.
- [ ] For Spring `@Transactional` tests, avoid preemptive threads that lose rollback.
- [ ] Do not assume `interrupt()` cancels every task and undoes all side effects.
- [ ] Configure real HTTP/DB/broker timeouts when I/O can block.
- [ ] Timeout thresholds fit CI; tests do not pass merely through scheduling luck.
- [ ] Business/state assertions exist; timeout is not the sole assertion when correctness must be verified.
- [ ] Test names/`@DisplayName` describe purpose rather than just "timeout test".
- [ ] Cleanup/cancellation strategy exists if the test runs async work or out-of-process side effects.

**Remember:** `assertTimeout` keeps the callback on the **same thread** and **waits for completion before evaluating**; `assertTimeoutPreemptively` moves the callback to **another thread** and **attempts to interrupt on expiration**; `@Timeout` has its own thread modes, where `SAME_THREAD` still uses an interrupt mechanism. In Spring Boot, thread selection decides whether test transactions and contexts still apply.

### Official references

- [JUnit 5 User Guide – Assertions: Timeout](https://docs.junit.org/5.12.0/user-guide/#writing-tests-assertions): `assertTimeout`, `assertTimeoutPreemptively`, and value-returning variants.
- [JUnit 5 User Guide – Declarative Timeouts](https://docs.junit.org/5.12.0/user-guide/#writing-tests-declarative-timeouts): `@Timeout`, `ThreadMode`, and timeout configuration.
- [JUnit Jupiter API – Assertions](https://junit.org/junit5/docs/5.12.0/api/org.junit.jupiter.api/org/junit/jupiter/api/Assertions.html): contracts and notes for both assertions.
- [Spring Framework – Test-managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): warnings about preemptive timeouts and `ThreadLocal` transactions in Spring TestContext.
- [Gradle User Manual – Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): running JUnit Platform and test reporting.
