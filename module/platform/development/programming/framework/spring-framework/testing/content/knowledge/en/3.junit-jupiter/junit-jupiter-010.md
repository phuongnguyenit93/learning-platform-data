# Standard Timeout vs. Preemptive (Thread-Switching) Timeout

Timeouts in JUnit Jupiter help detect when a test or an execution block takes longer than permitted. However, "running out of time" can be handled in two different ways: continuing execution on the test's own thread while sending an interrupt signal, or running the work on a separate thread so the framework can regain control when the deadline expires.

This difference affects the test lifecycle, task cancellation, transactions, ThreadLocals, and thread-bound contexts. Therefore, choosing a timeout is not just picking a number like one second or five seconds; you must also understand which thread the code will run on and what happens if it ignores interrupt signals.

## What Problem Do Timeouts Solve?

A test can hang due to a deadlock, waiting on an unresponsive service, an infinite loop, lock contention, or an asynchronous task that never completes. Without a time limit, a test suite may wait a very long time before surfacing the failure.

JUnit Jupiter provides timeouts at multiple levels:

- The `@Timeout` annotation sets a limit on a test method or lifecycle method.
- `assertTimeout()` measures the execution time of a block of code and fails if it runs too long.
- `assertTimeoutPreemptively()` runs the block on a separate thread and enforces the timeout preemptively.

These three options share a similar goal, yet their execution semantics differ. In particular, `assertTimeout()` does not stop the block at the deadline, whereas `assertTimeoutPreemptively()` moves the block onto another thread.

## The Two Thread Modes of @Timeout

JUnit Jupiter's `@Timeout` annotation has a `threadMode` attribute. The two primary modes are `SAME_THREAD` and `SEPARATE_THREAD`; `INFERRED` allows resolving the choice from JUnit configuration.

### SAME_THREAD: Executing on the Current Thread

Unless another thread mode is specified, `@Timeout` defaults to `SAME_THREAD` in standard configurations. The test method executes on the same thread JUnit uses to invoke it.

~~~java
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

class SameThreadTimeoutTest {

    @Test
    @Timeout(value = 2, unit = TimeUnit.SECONDS)
    void completesWithinTwoSeconds() {
        performOperation();
    }

    private void performOperation() {
        // Behavior under test.
    }
}
~~~

When the time limit is exceeded, JUnit sends an interrupt signal to the thread executing the test. The thread must still cooperate with interruption to stop promptly. For instance, blocking calls such as `Thread.sleep()`, `BlockingQueue.take()`, or certain I/O operations can throw `InterruptedException`.

Crucially, an interrupt is not a forced thread termination command. If code catches `InterruptedException` and ignores it, or runs a loop without checking interrupt status, the method can keep running. Because the test still occupies that execution thread, JUnit cannot simply reclaim the thread and move on as if the work had ended.

The advantage of `SAME_THREAD` is that the test method runs on the same thread as the lifecycle callbacks invoking it. Thread-bound data such as Spring's test-managed transactions, security context, or MDC remain visible in the usual way across synchronous test code.

### SEPARATE_THREAD: Executing on a Separate Thread

With `SEPARATE_THREAD`, JUnit runs the test method on a separate thread. When a timeout occurs, JUnit interrupts that execution thread and can resume control of the test engine without waiting indefinitely on the caller thread.

~~~java
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

class SeparateThreadTimeoutTest {

    @Test
    @Timeout(
        value = 2,
        unit = TimeUnit.SECONDS,
        threadMode = Timeout.ThreadMode.SEPARATE_THREAD
    )
    void completesWithinTwoSeconds() {
        performOperation();
    }

    private void performOperation() {
        // Behavior under test.
    }
}
~~~

This mode is helpful when you want to cap how long a test can block JUnit's control thread. If the code responds to interrupts, the separate thread stops and the test fails for exceeding the deadline.

However, if the code ignores interrupts, it can keep running on the separate thread even after JUnit has marked the test failed and moved on to other tests. That lingering thread may continue modifying the database, writing files, holding locks, sending messages, or mutating shared state. Thus, `SEPARATE_THREAD` is not a safe thread-killing mechanism.

### INFERRED: Resolving Thread Mode from Configuration

`Timeout.ThreadMode.INFERRED` tells JUnit to determine the thread mode from the configuration parameter `junit.jupiter.execution.timeout.thread.mode.default`. This is useful when a project wants to standardize its timeout policy via configuration without repeating the mode on every test.

Without an overriding configuration, JUnit's default behavior is `SAME_THREAD`. When using a project-wide setting, document the value in project test configuration or documentation so readers know which thread tests run on.

## Comparing @Timeout, assertTimeout, and assertTimeoutPreemptively

JUnit offers both annotation-based and assertion-based timeouts. When reading a test, check the exact API used rather than just seeing the word "timeout".

| API | Execution Thread | When Time Is Exceeded | Key Characteristic |
|---|---|---|---|
| `@Timeout` with `SAME_THREAD` | Test-calling thread | Interrupts that thread | Keeps the same thread as test lifecycle |
| `@Timeout` with `SEPARATE_THREAD` | Separate thread | Interrupts the separate thread; engine can continue if thread does not stop | Decouples execution from the control thread |
| `assertTimeout()` | Assertion-calling thread | Waits for the block to finish, then reports failure if overtime | Does not preempt the block at the deadline |
| `assertTimeoutPreemptively()` | Separate thread | Interrupts execution thread at deadline and reports timeout | Can regain control sooner, but changes thread context |

### assertTimeout: Wait for Completion Before Concluding

`assertTimeout()` executes the code block on the same thread calling the assertion. If execution exceeds the limit, the assertion reports failure only after the block finishes.

~~~java
import java.time.Duration;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertTimeout;

class AssertTimeoutTest {

    @Test
    void operationShouldFinishWithinOneSecond() {
        assertTimeout(Duration.ofSeconds(1), () -> {
            service.performOperation();
        });
    }
}
~~~

The example checks actual duration. If `performOperation()` takes three seconds, the assertion fails after the three-second call finishes. It does not abort the call at the one-second mark.

This fits when you need to measure the duration of a block while preserving thread context. It is unsuitable for protecting the test suite from code that might hang forever, because the assertion must wait for the block to return before concluding.

### assertTimeoutPreemptively: Execute the Block on a Separate Thread

`assertTimeoutPreemptively()` runs the executable or supplier on a separate thread. If time runs out, JUnit sends an interrupt and reports a timeout without waiting indefinitely on the assertion-calling thread.

~~~java
import java.time.Duration;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertTimeoutPreemptively;

class PreemptiveTimeoutTest {

    @Test
    void operationShouldFinishWithinOneSecond() {
        assertTimeoutPreemptively(Duration.ofSeconds(1), () -> {
            service.performOperation();
        });
    }
}
~~~

This behaves similarly to `@Timeout(threadMode = SEPARATE_THREAD)`: the code runs on a different thread and may no longer see contexts bound to the original thread. If the block ignores interrupts, it can still keep running after the assertion has failed.

Therefore, do not replace every `assertTimeout()` with `assertTimeoutPreemptively()` just to make tests "fail faster". Weigh thread context and side effects before switching to preemptive mode.

## How Does Thread Context Change?

Java has several mechanisms that bind state to the current thread. Examples include:

- `ThreadLocal` stores per-thread data.
- Spring Test normally binds test-managed transactions to the test execution thread.
- Spring Security can store the SecurityContext per thread.
- Logging frameworks can store MDC per thread.
- Spring's `RequestContextHolder` holds request information per thread in synchronous scenarios.

When code runs on a separate thread, those values are not automatically transferred from the test thread to the new thread. If the code relies on them, behavior may differ from running synchronously on the original thread.

### Risk with Spring Test Transactions

Spring Test typically begins a transaction for a test and binds that transaction to the test execution thread. Imagine a test like this:

~~~java
@SpringJUnitConfig(PersistenceTestConfig.class)
@Transactional
class CustomerTimeoutTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void insertsCustomer() {
        assertTimeoutPreemptively(
            Duration.ofSeconds(2),
            () -> customerRepository.save(new Customer("C-200", "Lan"))
        );
    }
}
~~~

In this example, the transaction managed by Spring Test lives on the test thread. The lambda inside `assertTimeoutPreemptively()` runs on another thread, so it does not automatically participate in that test-managed transaction.

If the repository or service starts its own transaction on the new thread, changes may commit independently. When the test thread finishes and rolls back its transaction, changes committed from the other thread may remain in the database.

This is a major reason to avoid thread-switching timeouts for code that must participate in a test-managed transaction. With Spring Test, prefer `SAME_THREAD` or `assertTimeout()` when current transaction and thread context must be preserved. If multithreaded behavior must be tested, design explicit transactions and cleanup for each thread instead of relying on the test thread's rollback.

This warning also applies to security context, request context, and MDC: if tests need those values, propagate or establish them deliberately on the executing thread.

## Interrupts Are Cooperative Signals, Not Thread-Kill Commands

Both `SAME_THREAD` and `SEPARATE_THREAD` rely on interrupts to signal to code that time has expired. Code must respond to this signal properly.

For example, if you must catch `InterruptedException`, restore the interrupt status or propagate an exception outward:

~~~java
void waitForWork() {
    try {
        Thread.sleep(10_000);
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException("Operation was interrupted", ex);
    }
}
~~~

Do not swallow interrupts:

~~~java
void waitIncorrectly() {
    try {
        Thread.sleep(10_000);
    } catch (InterruptedException ignored) {
        // Ignore cancellation signal.
    }
}
~~~

In the faulty example, the code clears the interrupt status and continues as if no stop request occurred. If the real operation is a long loop, check `Thread.currentThread().isInterrupted()` at safe points and exit work when signaled.

Not every operation is interruptible. CPU-bound code that never checks the interrupt flag can run indefinitely. Native calls or libraries without cancellation support may also fail to stop as desired. A timeout fails the test; it does not guarantee that all resources created by the test were reclaimed.

When using `SEPARATE_THREAD` or `assertTimeoutPreemptively()`, be especially careful about background threads continuing after a timeout. Put mechanisms in place to close resources, cancel tasks, await thread termination, and prevent lingering work from mutating data used by subsequent tests.

## When to Choose Which Approach

| Situation | Option to Consider | Reason |
|---|---|---|
| Standard synchronous test needing transactions or ThreadLocal | Default `@Timeout` / `SAME_THREAD` | Does not move execution to another thread |
| Need to verify duration of a call while still waiting for completion | `assertTimeout()` | Same thread, non-preemptive |
| Code risks hanging and JUnit must regain control | `SEPARATE_THREAD` or `assertTimeoutPreemptively()` | Detaches execution from calling thread |
| Test depends on a Spring test-managed transaction | Prefer `SAME_THREAD` or `assertTimeout()` | Keeps transaction bound to the test thread |
| Testing asynchronous tasks launched by the application | Await Future/CompletionStage or completion condition with timeout | Test method timeout alone does not prove worker tasks finished |
| Performance measurement or benchmarking | Dedicated benchmarking tools | Test timeouts are not stable performance measurements |

For asynchronous tasks, await the task's own result:

~~~java
@Test
void asynchronousOperationCompletes() throws Exception {
    Future<Result> future = executor.submit(() -> service.performAsyncWork());

    Result result = future.get(2, TimeUnit.SECONDS);

    assertThat(result.isSuccessful()).isTrue();
}
~~~

`Future.get(timeout, unit)` bounds the wait for the result. If it expires, it throws `TimeoutException`; the test can call `future.cancel(true)` and perform cleanup. Cancellation still depends on the task cooperating with interrupts, so manage the executor lifecycle and related resources carefully.

## Configuring Timeouts Consistently Across a Project

Timeouts can be placed at the method level:

~~~java
@Test
@Timeout(value = 3, unit = TimeUnit.SECONDS)
void respondsWithinBudget() {
    service.respond();
}
~~~

Or at the class level to apply a shared limit to methods in the class:

~~~java
@Timeout(value = 5, unit = TimeUnit.SECONDS)
class ServiceIntegrationTest {

    @Test
    void firstScenario() {
        // ...
    }

    @Test
    void secondScenario() {
        // ...
    }
}
~~~

JUnit Jupiter also allows configuring the default thread mode via the `junit.jupiter.execution.timeout.thread.mode.default` configuration parameter. When using `Timeout.ThreadMode.INFERRED`, the mode is derived from that configuration. Specify the setting explicitly in `junit-platform.properties` or equivalent test configuration so the policy does not depend on hard-to-observe runtime environments.

Avoid setting timeouts too close to average execution time. CI can run slower due to host load, context startup, I/O, or parallel execution. Limits that are too tight make tests flaky and turn environmental jitter into false failures. Timeouts should reflect a reasonable upper bound for the behavior, with enough headroom for normal variance.

## Common Misconceptions

**Thinking an expired timeout kills the thread.** JUnit sends an interrupt. Unresponsive code can keep running. Design explicit cancellation and cleanup.

**Thinking `assertTimeout()` stops code right at the deadline.** It waits for the code to finish before comparing elapsed time. For preemption, understand `assertTimeoutPreemptively()` or `SEPARATE_THREAD`.

**Using thread-switching timeouts on tests with Spring transactions.** Test-managed transactions are normally bound to the original thread. Code on another thread may run outside that transaction and leave committed data behind.

**Assuming a separate thread is automatically safer.** A separate thread decouples execution from the caller thread, yet it can keep running after timeout, hold resources, or corrupt shared state.

**Using timeouts for benchmarking.** Test timeouts primarily catch overdue or hung behaviors. Performance measurement requires controlling warm-up, data, JVM, host load, and statistics with benchmarking tools.

**Failing to clean up after a task times out.** A failed test does not mean background threads stopped, files were deleted, or messages were rolled back. Cleanup must cover all resources created by the test.

## Choosing a Timeout Intentionally

Before adding a timeout, identify which code needs bounding and why it might take too long. If the test needs Spring's thread context, choose same-thread execution. If you only want to check the duration of a synchronous operation, `assertTimeout()` is straightforward. If you must isolate code from the calling thread so the engine can continue past the deadline, consider a thread-switching timeout and prepare for the possibility that the task ignores interrupts.

For asynchronous work, bound the wait on the Future or CompletionStage itself, then cancel and clean up tasks as needed. In every mode, ensure code responds to interrupts, leaves no side effects outside test scope, and does not let stale threads affect subsequent tests.

`SAME_THREAD` prioritizes thread-context continuity; `SEPARATE_THREAD` prioritizes detaching execution from the control thread; `assertTimeout()` measures time without preemption; `assertTimeoutPreemptively()` runs the callback on a separate thread. Choosing the right mechanism allows timeouts to catch slow or hung tests without inadvertently breaking transactions, contexts, or test data.
