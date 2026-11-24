# Detecting Blocking Calls with BlockHound When Supported by the Environment

In Reactor, a pipeline can look completely reactive yet still contain **blocking** calls such as `Thread.sleep`, synchronous file access, JDBC, or lock waits. If those calls execute on an event loop or a thread designated for non-blocking processing, they can hold the thread too long, increase latency, reduce throughput, and force other requests to wait.

**BlockHound** is a JVM instrumentation tool developed by Project Reactor that detects certain blocking calls on threads marked **non-blocking only**. When it intercepts a recognized blocking method on such a thread, BlockHound throws `reactor.blockhound.BlockingOperationError`. This is a signal to fix your scheduler design or replace the blocking API with a reactive API; it is not an automatic mechanism that turns blocking code into non-blocking code.

The title emphasizes **"when supported by the environment"** because BlockHound requires JVM Java agent/instrumentation capabilities. Some JDKs, native-image builds, sandboxes, JVMs restricting dynamic attach, or CI environments may not support installing the agent. In those cases, continue testing pipelines with `StepVerifier`, `VirtualTimeScheduler`, timeout tests, and benchmarks; never claim BlockHound detected no blocking if instrumentation was not actually installed.

This lesson covers the principles, limitations, Gradle/JDK 17 configuration, a Reactor test suite with an intentional BlockHound opt-in mode, reading stack traces, fixing blocking in WebFlux, and strategies for unsupported environments.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish blocking, CPU-bound, and non-blocking calls.
2. Understand why event loops must not run synchronous waiting calls.
3. Know how BlockHound checks methods and threads.
4. Distinguish `Schedulers.parallel()`, `Schedulers.single()`, and `Schedulers.boundedElastic()`.
5. Understand the role of the `NonBlocking` marker and `Schedulers.isInNonBlockingThread()`.
6. Install BlockHound via `BlockHound.install()` at the right time.
7. Configure the required JVM flag for JDK 13+ in Gradle tests.
8. Enable BlockHound tests **explicitly**, without assuming every environment supports it.
9. Write positive tests asserting `BlockingOperationError` with `StepVerifier`.
10. Write control tests for non-blocking tasks and blocking tasks isolated on `boundedElastic`.
11. Distinguish Reactor's built-in `block()` guard error from BlockHound errors.
12. Locate the exact blocking call site via stack traces instead of hiding errors with arbitrary allowlists.
13. Use `markAsBlocking` or `allowBlockingCallsInside` in a controlled manner.
14. Recognize false negatives, false positives, and JVM-wide instrumentation effects.
15. Design a CI strategy and fallback alternatives when BlockHound cannot run.

## 2. Why Is Blocking Dangerous in Reactive Pipelines?

Reactor uses publishers, subscribers, and schedulers to execute work. In Spring WebFlux running on Reactor Netty, a relatively small number of event-loop threads manage a large number of connections. This model works efficiently when callbacks execute quickly without blocking the thread.

Example of a seemingly simple pipeline:

~~~java
Mono<String> result = Mono.just("hello")
    .map(value -> {
        Thread.sleep(500);
        return value.toUpperCase();
    });
~~~

The snippet above is illustrative and does not compile as-is because `Thread.sleep` requires handling `InterruptedException`. If you handle the exception and run it on the event loop, the thread is held for at least ~500 ms. Many concurrent requests will have to wait for that same worker thread.

### 2.1. Blocking vs. Non-Blocking

| Work type | Example | Impact |
| --- | --- | --- |
| Blocking wait | `Thread.sleep`, synchronous JDBC, synchronous socket read | Thread waits and cannot process other tasks |
| CPU-bound | Heavy continuous computation | Not necessarily blocking I/O, yet still monopolizes CPU and event loop |
| Non-blocking I/O | R2DBC, WebClient/Netty when used properly | Does not hold a thread waiting for I/O |
| Reactive delay | `Mono.delay(Duration)` | Scheduler schedules a timer without calling `Thread.sleep` in callbacks |
| Isolated legacy blocking | `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` | Offloads blocking wait to the `boundedElastic` pool, without making the API non-blocking |

BlockHound primarily checks **known or marked blocking methods** executed on non-blocking threads. It does not measure all latency, does not automatically detect CPU-bound loops, and does not replace a profiler.

### 2.2. Blocked Event Loop

~~~text
Event-loop thread
  |
  +-- Request A: parse header       1 ms
  +-- Request B: blocking JDBC    500 ms  <-- holds thread
  +-- Request C: handle response    ...   <-- must wait
  +-- Request D: handle response    ...   <-- must wait
~~~

A single blocking call can cause head-of-line blocking for tasks sharing that event loop. Under load, latency can spike non-linearly.

### 2.3. Why Not Use boundedElastic Everywhere?

`boundedElastic` is a bridge when legacy blocking APIs cannot yet be removed, yet it still has bounded threads and queues. If thousands of requests simultaneously call blocking JDBC, offloading everything to `boundedElastic` may still fail to meet SLAs. You need concurrency limits, timeouts, resource pooling, and preferably native reactive drivers whenever feasible.

## 3. How Does BlockHound Work?

BlockHound uses Byte Buddy / Java instrumentation to intercept methods considered blocking. When such a method is invoked, BlockHound checks whether the current thread belongs to the non-blocking-only group. If so, by default it throws:

~~~text
reactor.blockhound.BlockingOperationError:
Blocking call! java.lang.Thread.sleep
~~~

The method name in the stack trace helps locate the blocking call.

Three conditions must hold simultaneously:

1. **The agent installed successfully** and instrumented the target method.
2. The method is recognized/registered by BlockHound as blocking.
3. The call runs on a **thread marked non-blocking**.

If any one of the three is unmet, BlockHound may not report an error. That does not by itself prove the code is safe.

### 3.1. The NonBlocking Marker

Reactor defines the marker interface `reactor.core.scheduler.NonBlocking`. Many worker threads of `Schedulers.parallel()` and `Schedulers.single()` implement this marker. BlockHound integrates with Reactor to recognize those threads.

You can check:

~~~java
boolean isNonBlocking =
    Schedulers.isInNonBlockingThread();
~~~

The return value reflects the thread currently executing at the check site, not the publisher type declared in a Java variable.

### 3.2. Schedulers and Detection Behavior

| Scheduler/thread | Characteristics | Typical result for `Thread.sleep` after installing BlockHound |
| --- | --- | --- |
| `Schedulers.parallel()` | Non-blocking workers for short/CPU tasks | Detected |
| `Schedulers.single()` | Shared non-blocking worker | Detected |
| Reactor Netty event loop | Non-blocking network I/O | Detected under compatible integration conditions |
| `Schedulers.boundedElastic()` | Designed for bounded legacy blocking | Not blocked under default non-blocking-thread policy |
| Main/JUnit test thread | Usually not marked `NonBlocking` | May not be detected |
| Custom `ExecutorService` | Depends on thread type and predicate | Do not assume detection |
| Virtual threads | Depends on JDK/config and runtime | Requires separate compatibility testing |

**Do not write a `Thread.sleep(20)` test on the main test thread and conclude BlockHound is broken when no error occurs.** Use `subscribeOn(Schedulers.parallel())` or switch callbacks with `publishOn` to test on the right thread type.

### 3.3. Installing the Agent Before Running Pipelines

Simple installation:

~~~java
BlockHound.install();
~~~

Install early during test/application process startup, before creating many schedulers and executing pipelines. Installation is a **JVM-wide** action, not per-`Mono`. Do not call `install` again inside every `@Test` method.

Per BlockHound, subsequent install calls are typically ignored; do not rely on a second install call to alter allowlists. If multiple modules/test suites need custom integrations, design a single unified installation point.

### 3.4. Not a Compile-Time Check

BlockHound does not scan source code to forbid `Thread.sleep` at compile time. It detects **calls that actually execute** when tests run on qualifying threads. Unexecuted code paths are not observed.

## 4. Versions, JVM Flags, and Supported Environments

Examples in this lesson use:

- **Java 17** (HotSpot/OpenJDK with working Java instrumentation).
- **Reactor Core/Test 3.8.8**.
- **BlockHound 1.0.18.RELEASE**.
- **JUnit Jupiter 5.14.4**.
- **Gradle 8.x or newer** compatible with the JDK and plugins in use.

These versions were chosen for a matching Reactor Core/Test pair and a released BlockHound artifact. Projects using a version catalog or custom BOM must keep Reactor versions aligned on the same release train.

### 4.1. JDK 13+ Requirement

Current BlockHound documentation instructs adding the following JVM flag on JDK 13+:

~~~text
-XX:+AllowRedefinitionToAddDeleteMethods
~~~

This is a workaround for a JVM restriction on redefining native methods, not a performance flag. The flag must be passed to the **JVM running the tests**, not merely the Gradle daemon or shell. Depending on JDK vendor/version, the JVM may warn, drop support, or restrict other instrumentation mechanisms.

Do not blindly apply this flag to all production environments. Use it only in test JVMs that genuinely need BlockHound, and verify instrumentation startup succeeds.

### 4.2. Dynamic Attach and Native-Image

Some environments may disallow Java agent attach/retransformation:

- Containers with restricted process attach permissions.
- JVMs enforcing policies that forbid dynamic agent loading.
- `native-image` runtimes lacking equivalent Java instrumentation mechanisms.
- JDK vendors/versions incompatible with the bundled Byte Buddy agent.
- Security policies or test runners disallowing agents.
- Conflicts with other coverage/instrumentation agents.

If `BlockHound.install()` throws an exception, tests must report **failed to install**. Never conclude a pipeline is non-blocking simply because no `BlockingOperationError` appeared.

### 4.3. The "When Supported by the Environment" Principle

Maintain two test layers:

1. **Core Reactor tests**: run everywhere without depending on instrumentation.
2. **BlockHound opt-in tests**: enabled only on JVMs/test runners confirmed to support it; when enabled and installation fails, report a clear test failure.

Never wrap agent installation in a `try/catch` and still let the BlockHound suite PASS. That creates a false sense of safety.

## 5. Combining BlockHound with StepVerifier

`StepVerifier` asserts publisher signals: `onNext`, `onComplete`, or `onError`. When BlockHound throws `BlockingOperationError` inside a reactive callback, the error usually travels as `onError` to the subscriber.

### 5.1. Violating Pipeline

~~~java
Mono<String> wrong = Mono.fromCallable(() -> {
    Thread.sleep(30);
    return "done";
})
.subscribeOn(Schedulers.parallel());
~~~

The snippet uses `Thread.sleep`, so real code must handle `InterruptedException`. The complete code in section 9 includes a helper handling the exception.

With BlockHound installed successfully, sleeping on a `parallel` scheduler worker typically yields `BlockingOperationError`. Tests should verify the error type rather than merely calling `expectError()`, because a `NullPointerException` or codec failure would also make `expectError()` pass.

### 5.2. Targeting the Exact Error

~~~java
StepVerifier.create(wrong)
    .expectErrorSatisfies(error -> {
        assertTrue(isBlockingOperationError(error));
    })
    .verify(Duration.ofSeconds(5));
~~~

`isBlockingOperationError` is a test helper walking the cause chain. It avoids coupling to whether an operator wraps the error. Verify the cause is BlockHound, rather than accepting any arbitrary exception.

### 5.3. Control Tests

Two helpful controls:

- Non-blocking logic on `parallel` must complete.
- Blocking logic isolated on `boundedElastic` can complete without BlockHound flagging a non-blocking thread.

This proves the tool distinguishes execution contexts; it does not prove `boundedElastic` has infinite throughput or that legacy code is safe under heavy load.

## 6. subscribeOn and publishOn Determine Where Blocking Runs

A common mistake is switching schedulers at the wrong position.

### 6.1. subscribeOn Offloads Source Work

~~~java
Mono<String> result = Mono.fromCallable(
        () -> legacyBlockingCall()
    )
    .subscribeOn(Schedulers.boundedElastic());
~~~

`subscribeOn` places subscription/source execution onto the chosen scheduler. This is the familiar pattern for isolating an existing blocking API.

Replacing `boundedElastic` with `parallel` causes BlockHound to flag the source when it calls `Thread.sleep` or blocking I/O.

### 6.2. publishOn Affects Downstream Operators

~~~java
Mono<String> result = Mono.just("hello")
    .publishOn(Schedulers.parallel())
    .map(value -> legacyBlockingCall());
~~~

At this position, `map` runs after `publishOn` on a `parallel` worker, so the blocking call is caught.

In contrast:

~~~java
Mono<String> result = Mono.fromCallable(
        () -> legacyBlockingCall()
    )
    .publishOn(Schedulers.parallel());
~~~

`publishOn` sits **after** the source, so it does not run the preceding callable on `parallel`. Do not use this case to claim BlockHound is broken when it reports no error.

### 6.3. Combining Two Schedulers in One Flow

~~~java
Mono<String> flow = Mono.fromCallable(
        () -> legacyBlockingCall()
    )
    .subscribeOn(Schedulers.boundedElastic())
    .publishOn(Schedulers.parallel())
    .map(String::trim);
~~~

The blocking source runs on `boundedElastic`. After `publishOn`, the lightweight transformation runs on `parallel`. When maintaining code, remember that adding a blocking call **after** `publishOn` can reintroduce a violation.

## 7. BlockHound vs. Reactor's Built-In block() Guard

Reactor has its own guard for synchronous blocking APIs like:

~~~java
Mono.just("value").block();
~~~

When `block()` runs on a Reactor thread marked `NonBlocking` (such as `parallel`), Reactor itself can throw:

~~~text
java.lang.IllegalStateException:
block()/blockFirst()/blockLast() are blocking,
which is not supported in thread ...
~~~

This error can appear **even without BlockHound installed**.

By contrast, `BlockingOperationError: Blocking call! java.lang.Thread.sleep` comes from BlockHound instrumentation. Therefore, do not use `Mono.block()` as the sole test to verify BlockHound installation succeeded.

### 7.1. Is StepVerifier.verify() Blocking?

`StepVerifier.verify()` waits for the test result and blocks the **JUnit test thread**, which is normally not an event loop. That is normal testing practice. Never call `StepVerifier.verify()` inside `map`/`flatMap` or callbacks executing on a Reactor non-blocking thread.

### 7.2. Does withVirtualTime Detect Thread.sleep?

`StepVerifier.withVirtualTime` controls virtual scheduler time for operators like `delay`, `interval`, and `timeout`. It **does not make `Thread.sleep` non-blocking**, nor does it replace BlockHound. Use virtual time for time-based logic and BlockHound to catch blocking violations when the agent is active.

## 8. Common Scenarios in Spring WebFlux

### 8.1. Synchronous JDBC in a Controller

A handler like this is dangerous if run directly on the event loop:

~~~java
@GetMapping("/customers/{id}")
Mono<Customer> get(@PathVariable String id) {
    Customer customer = jdbcRepository.findById(id);
    return Mono.just(customer);
}
~~~

This illustrative snippet assumes application types `jdbcRepository` and `Customer`. The JDBC call executes **before** the method even returns the `Mono`; wrapping the result in `Mono.just` does not make JDBC non-blocking.

### 8.2. Isolating Legacy JDBC When It Cannot Yet Be Replaced

~~~java
@GetMapping("/customers/{id}")
Mono<Customer> get(@PathVariable String id) {
    return Mono.fromCallable(
        () -> jdbcRepository.findById(id)
    )
    .subscribeOn(Schedulers.boundedElastic());
}
~~~

This offloads blocking work to `boundedElastic`. You still need concurrency limits, JDBC pool sizing, timeouts, cancellation semantics, and overload control. The long-term fix is R2DBC, a reactive HTTP client, or a genuinely asynchronous adapter if business requirements permit.

### 8.3. Thread.sleep to "Wait a Moment"

Do not use:

~~~java
Mono.just("x")
    .map(value -> {
        sleepForOneSecond();
        return value;
    });
~~~

For non-blocking delays:

~~~java
Mono<String> delayed = Mono.just("x")
    .delayElement(Duration.ofSeconds(1));
~~~

Or:

~~~java
Mono<String> delayed =
    Mono.delay(Duration.ofSeconds(1))
        .thenReturn("x");
~~~

`delayElement` and `Mono.delay` schedule timers via a scheduler rather than blocking a thread with `Thread.sleep`.

### 8.4. Synchronous File I/O and HTTP Clients

`Files.readAllBytes`, `InputStream.read`, legacy synchronous Apache HttpClient, or third-party SDKs can block. Do not assume every I/O method is instrumented by BlockHound; whether an error is thrown depends on the method, JVM, and library integrations.

For APIs available only in synchronous form, isolate them:

~~~java
Mono<byte[]> content = Mono.fromCallable(
        () -> Files.readAllBytes(path)
    )
    .subscribeOn(Schedulers.boundedElastic());
~~~

This integration snippet assumes `path` is a `java.nio.file.Path`. With large files, `readAllBytes` also risks high heap usage; prefer streaming, size limits, or suitable I/O mechanisms.

### 8.5. Logging and Third-Party SDKs

A synchronous logging appender, driver, DNS resolver, or incompatible SDK can block inside seemingly lightweight callbacks. When BlockHound fires, inspect the library stack trace as well. Do not rush to allowlist an entire package.

## 9. Building Optional Tests: Normal Runs vs. Intentional BlockHound Opt-In

The example uses a **pure Java 17 Reactor** project. No Spring Boot server is needed; because this lesson focuses on testing Reactor and schedulers, the test suite targets publishers directly.

Structure:

~~~text
reactor-blockhound-lab/
├── build.gradle
└── src/
    ├── main/java/demo/BlockingExamples.java
    └── test/java/demo/
        ├── ReactorSchedulerTest.java
        └── BlockHoundOptionalTest.java
~~~

### 9.1. build.gradle

~~~groovy
plugins {
    id 'java'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.8.8'

    testImplementation 'io.projectreactor:reactor-test:3.8.8'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.14.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.14.4'

    testImplementation 'io.projectreactor.tools:blockhound:1.0.18.RELEASE'
}

tasks.named('test', Test) {
    useJUnitPlatform()

    String optIn = providers.gradleProperty('blockhound')
        .orElse('false')
        .get()

    systemProperty 'test.blockhound', optIn

    if (optIn == 'true') {
        jvmArgs '-XX:+AllowRedefinitionToAddDeleteMethods'
        maxParallelForks = 1
    }
}
~~~

Explanation:

- The BlockHound dependency lives only on the test classpath, never bundling the agent into production runtime by default.
- `test.blockhound` defaults to `false` during normal test runs.
- Only when running `-Pblockhound=true` does JUnit enable the instrumentation tests.
- The JDK 13+ flag is passed to the **test JVM** in the opt-in branch.
- `maxParallelForks = 1` avoids unnecessarily spawning multiple test JVMs for this example; each JVM maintains its own instrumentation state.
- Core tests still run when BlockHound is off.

Do not expect unsupported environments to silently ignore an agent installation error once opted in. **If opt-in is enabled and `BlockHound.install()` fails, the Gradle test run should fail loudly.**

### 9.2. BlockingExamples.java

~~~java
package demo;

import java.util.Locale;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public final class BlockingExamples {

    private BlockingExamples() {
    }

    public static String legacyWait(String input) {
        try {
            Thread.sleep(25);
        }
        catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                "Legacy operation interrupted", ex
            );
        }

        return input.toUpperCase(Locale.ROOT);
    }

    public static Mono<String> wrongOnParallel(String value) {
        return Mono.fromCallable(
                () -> legacyWait(value)
            )
            .subscribeOn(Schedulers.parallel());
    }

    public static Mono<String> isolatedOnBoundedElastic(String value) {
        return Mono.fromCallable(
                () -> legacyWait(value)
            )
            .subscribeOn(Schedulers.boundedElastic());
    }

    public static Mono<String> nonBlockingTransform(String value) {
        return Mono.just(value)
            .publishOn(Schedulers.parallel())
            .map(s -> s.toUpperCase(Locale.ROOT));
    }

    public static Mono<String> wrongAfterPublishOn(String value) {
        return Mono.just(value)
            .publishOn(Schedulers.parallel())
            .map(BlockingExamples::legacyWait);
    }

    public static Mono<Boolean> onParallelNonBlockingThread() {
        return Mono.fromSupplier(
                Schedulers::isInNonBlockingThread
            )
            .subscribeOn(Schedulers.parallel());
    }

    public static Mono<Boolean> onBoundedElasticNonBlockingThread() {
        return Mono.fromSupplier(
                Schedulers::isInNonBlockingThread
            )
            .subscribeOn(Schedulers.boundedElastic());
    }
}
~~~

Here:

- `legacyWait` simulates a synchronous API and handles `InterruptedException` properly.
- `wrongOnParallel` places the blocking operation on a `parallel` worker: BlockHound must catch it when the agent is active.
- `isolatedOnBoundedElastic` runs the same operation on the scheduler meant for legacy blocking.
- `nonBlockingTransform` merely uppercases a `String`, with no synchronous waiting.
- `wrongAfterPublishOn` tests operator placement after `publishOn`.
- The last two methods check Reactor's thread classification.

### 9.3. ReactorSchedulerTest.java — Always Runs

~~~java
package demo;

import java.time.Duration;

import org.junit.jupiter.api.Test;

import reactor.test.StepVerifier;

final class ReactorSchedulerTest {

    @Test
    void nonBlockingTransformCompletes() {
        StepVerifier.create(
            BlockingExamples.nonBlockingTransform("alpha")
        )
        .expectNext("ALPHA")
        .expectComplete()
        .verify(Duration.ofSeconds(5));
    }

    @Test
    void boundedElasticCanRunLegacyBlockingCall() {
        StepVerifier.create(
            BlockingExamples.isolatedOnBoundedElastic("beta")
        )
        .expectNext("BETA")
        .expectComplete()
        .verify(Duration.ofSeconds(5));
    }

    @Test
    void parallelWorkersAreMarkedNonBlocking() {
        StepVerifier.create(
            BlockingExamples.onParallelNonBlockingThread()
        )
        .expectNext(true)
        .expectComplete()
        .verify(Duration.ofSeconds(5));
    }

    @Test
    void boundedElasticWorkersAreNotMarkedNonBlocking() {
        StepVerifier.create(
            BlockingExamples.onBoundedElasticNonBlockingThread()
        )
        .expectNext(false)
        .expectComplete()
        .verify(Duration.ofSeconds(5));
    }
}
~~~

These four tests do not call `BlockHound.install()`. They verify scheduler classification and basic outputs, so they still run when agent instrumentation is unavailable.

### 9.4. BlockHoundOptionalTest.java — Runs Only When Opted In

~~~java
package demo;

import java.time.Duration;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;

import reactor.blockhound.BlockHound;
import reactor.blockhound.BlockingOperationError;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertTrue;

@EnabledIfSystemProperty(
    named = "test.blockhound",
    matches = "true"
)
final class BlockHoundOptionalTest {

    @BeforeAll
    static void installBlockHound() {
        BlockHound.install();
    }

    private static boolean containsBlockHoundError(
            Throwable error) {

        for (Throwable current = error;
                current != null;
                current = current.getCause()) {

            if (current instanceof BlockingOperationError) {
                return true;
            }
        }

        return false;
    }

    @Test
    void detectsSleepOnParallelScheduler() {
        StepVerifier.create(
            BlockingExamples.wrongOnParallel("alpha")
        )
        .expectErrorSatisfies(error ->
            assertTrue(
                containsBlockHoundError(error),
                () -> "Unexpected error: " + error
            )
        )
        .verify(Duration.ofSeconds(5));
    }

    @Test
    void detectsSleepAfterPublishOn() {
        StepVerifier.create(
            BlockingExamples.wrongAfterPublishOn("beta")
        )
        .expectErrorSatisfies(error ->
            assertTrue(
                containsBlockHoundError(error),
                () -> "Unexpected error: " + error
            )
        )
        .verify(Duration.ofSeconds(5));
    }

    @Test
    void legacyBlockingOnBoundedElasticStillCompletes() {
        StepVerifier.create(
            BlockingExamples.isolatedOnBoundedElastic("gamma")
        )
        .expectNext("GAMMA")
        .expectComplete()
        .verify(Duration.ofSeconds(5));
    }

    @Test
    void pureTransformOnParallelCompletes() {
        StepVerifier.create(
            BlockingExamples.nonBlockingTransform("delta")
        )
        .expectNext("DELTA")
        .expectComplete()
        .verify(Duration.ofSeconds(5));
    }
}
~~~

**Why use `@EnabledIfSystemProperty`?**

JUnit runs this test class only when `test.blockhound=true`. When disabled, tests in this class show as **skipped**, not passed. That is the honest status for environments without instrumentation. If enabled and `BlockHound.install()` fails, `@BeforeAll` fails the tests and reports the cause instead of swallowing the error.

**Why not `expectError()`?** Because we need to prove the failure came from BlockHound, not from application logic or dependency errors. The helper walking the cause chain makes the test's intent explicit.

### 9.5. Normal Test Run

If the project includes the Gradle wrapper:

~~~bash
./gradlew test
~~~

On Windows:

~~~powershell
.\gradlew.bat test
~~~

If there is no wrapper but a compatible Gradle is installed:

~~~bash
gradle test
~~~

**Expected result:** `ReactorSchedulerTest` runs and passes; `BlockHoundOptionalTest` is skipped because it is not enabled. This **does not mean** BlockHound verified the entire codebase is non-blocking.

### 9.6. Enabling BlockHound on a Supported Environment

With the Gradle wrapper:

~~~bash
./gradlew test -Pblockhound=true --rerun-tasks
~~~

On Windows:

~~~powershell
.\gradlew.bat test -Pblockhound=true --rerun-tasks
~~~

With an installed Gradle:

~~~bash
gradle test -Pblockhound=true --rerun-tasks
~~~

When Java 17 / agent are compatible:

- Gradle passes `-XX:+AllowRedefinitionToAddDeleteMethods` to the test JVM.
- JUnit enables `BlockHoundOptionalTest`.
- `@BeforeAll` installs BlockHound once.
- Both `detectsSleep...` tests receive `BlockingOperationError` and **PASS because they explicitly expect that error**.
- Both control tests complete normally.
- Regular test classes continue running as well.

If the agent fails to install, the tests must FAIL with the installation error. In that case, pass `-Pblockhound=true` only on supported runners; other runners continue running baseline tests without the agent.

### 9.7. Do Not Use Real Sleep for General Time Testing

`Thread.sleep(25)` in the example serves solely as a **blocking violation sample** observable by BlockHound. It is not a good approach for testing time-based timers/operators. For business logic involving delays/timeouts, use `StepVerifier.withVirtualTime` and the appropriate virtual scheduler instead of multi-second sleeps that slow tests down.

## 10. Analyzing BlockingOperationError Stack Traces

Sample error when BlockHound detects a call:

~~~text
reactor.blockhound.BlockingOperationError:
Blocking call! java.lang.Thread.sleep
    at java.base/java.lang.Thread.sleep(...)
    at demo.BlockingExamples.legacyWait(BlockingExamples.java:...)
    at demo.BlockingExamples.lambda$wrongOnParallel$0(...)
    at reactor.core.publisher.MonoCallable.call(...)
    ...
~~~

Exact line numbers and frames depend on Java/compiler/Reactor versions. Read from top to bottom:

1. `BlockingOperationError` shows the detector fired.
2. `java.lang.Thread.sleep` is the intercepted blocking method.
3. `demo.BlockingExamples.legacyWait` is the entry point in application code.
4. Reactor stack frames reveal which callback/operator invoked that helper.

When an error points into a third-party library, find the first call site belonging to application code to trace the call path. Never simply strip the top frame or immediately allowlist it without understanding why the code ran on a non-blocking thread.

### 10.1. Distinguishing Root Cause from Wrappers

Some operators can wrap exceptions. `StepVerifier` may then see a `Throwable` with `BlockingOperationError` inside `getCause()`. The `containsBlockHoundError` helper in the test example handles this case.

Avoid matchers relying solely on a message string that might vary across versions. Prefer the `BlockingOperationError` type and call-site info from the stack trace.

## 11. Customizing BlockHound and Avoiding Allowlist Abuse

BlockHound has a builder API to mark additional blocking methods, permit specific blocking regions, or integrate frameworks.

### 11.1. Marking an Application Method as Blocking

Suppose an internal library has a method:

~~~java
public String load(String key) {
    // In reality, performs synchronous I/O
    return "value";
}
~~~

This is an illustrative snippet, not a standalone class. If you know for certain this method blocks yet BlockHound does not recognize it, mark it using its JVM descriptor:

~~~java
BlockHound.install(builder ->
    builder.markAsBlocking(
        "com.example.LegacyStore",
        "load",
        "(Ljava/lang/String;)Ljava/lang/String;"
    )
);
~~~

The descriptor `(Ljava/lang/String;)Ljava/lang/String;` means the method takes a `String` and returns a `String`. Class name and method signature must match exactly. If the signature is wrong, the detector cannot instrument the target method.

### 11.2. Configuring allowBlockingCallsInside

Some libraries have bootstrap paths evaluated as acceptable for synchronous waiting in special contexts. When backed by clear evidence, BlockHound supports:

~~~java
BlockHound.install(builder ->
    builder.allowBlockingCallsInside(
        "com.example.SafeBootstrap",
        "initialize"
    )
);
~~~

This exception configuration **carries risk**: it suppresses blocking checks whenever calls originate inside the permitted region. It does not make the method non-blocking and does not make it safe if called from a real event loop.

### 11.3. Keeping Reactor's Default Integrations

`BlockHound.install()` loads available `BlockHoundIntegration`s via `ServiceLoader`, including the matching Reactor integration. When customizing, prefer the `BlockHound.install(integrations...)` overload to preserve default integrations.

Be careful with `BlockHound.builder().install()`: building directly does not automatically load SPI integrations like `BlockHound.install()`; you can lose the rules identifying Reactor `NonBlocking` threads if not configured completely.

### 11.4. Scoped Allowlists

If an exception is genuinely necessary:

- Document why blocking at that location is acceptable.
- Scope it to a specific method, never an entire namespace.
- Add tests proving other call sites are still flagged.
- Open an issue/criteria for removing the exception once the blocking API is replaced.
- Never use an allowlist to hide a newly introduced bug in a production controller.

### 11.5. Install Once and Global Side Effects

BlockHound instrumentation is process/JVM-wide. One test configuring an allowlist can affect other tests in the same fork. Therefore:

1. Have one single agent installation point before all BlockHound tests.
2. Avoid multiple test classes calling `install` with differing configurations.
3. Do not let a test suite modify global rules while other tests run in parallel.
4. When you need to compare different policies, separate them into distinct JVMs/test tasks.

## 12. What BlockHound Detects and Does Not Detect

| Scenario | Typical outcome | Explanation |
| --- | --- | --- |
| `Thread.sleep` on `parallel` after install | `BlockingOperationError` | Method is instrumented and thread is `NonBlocking` |
| `Thread.sleep` on `boundedElastic` | Not blocked by BlockHound | Scheduler is designated for blocking bridges |
| `Thread.sleep` on JUnit main thread | Usually not blocked | Thread is not marked `NonBlocking` |
| `Mono.block` on `parallel` | May throw Reactor's `IllegalStateException` | Not necessarily due to BlockHound |
| 100% CPU computation loop | May not report | Not an instrumented blocking call |
| Unregistered native/SDK I/O | May not report | BlockHound does not recognize every blocking API |
| Unexecuted code path in tests | Not reported | Detector operates at runtime |
| Agent installation failed | No detection guarantee | Instrumentation is inactive |
| Virtual threads / custom scheduler | Depends on thread markers/config | Requires environment verification |
| Task runs cleanly on `boundedElastic` | Test may pass | Does not guarantee resources under load |

### 12.1. False Negatives

A test reporting no errors can happen because:
- The pipeline never executed the blocking branch.
- The thread was not marked `NonBlocking`.
- BlockHound was not installed or failed to install.
- The blocking method was not recognized by BlockHound.
- A custom scheduler did not integrate the thread predicate.
- Instrumentation did not work on that JDK/runtime.

To verify the detector itself, keep a controlled test **intentionally calling `Thread.sleep` on `parallel`** and assert BlockHound throws `BlockingOperationError` when enabled.

### 12.2. False Positives or Benign Contextual Errors

Certain framework/logging initialization calls may be flagged as blocking even though they occur during a startup phase your team accepts. Inspect the execution context and startup order before adding an exception.

Specifically, classloader/instrumentation changes caused by other bytecode agents can trigger unusual errors. Do not treat every instrumentation-related error as a business-code violation.

### 12.3. Do Not Use BlockHound as a Performance Certificate

BlockHound catches one class of anti-pattern, yet tells you nothing about:
- Production p95/p99 latency.
- CPU saturation levels.
- Open connection counts.
- Actual database throughput.
- Memory/queue growth under backpressure.
- Timeouts or deadlocks across all scenarios.

You still need metrics, profiling, load tests, thread dumps, and tracing.

## 13. When the Environment Does Not Support BlockHound

If BlockHound cannot run on a given JVM, **you do not throw away your Reactor testing strategy**.

### 13.1. Run Baseline StepVerifier Tests

Use `StepVerifier` to check:
- `onNext`/`onComplete`/`onError`.
- Item ordering.
- Error recovery, retries, and cancellation.
- Timeouts and demand-driven backpressure.
- Resource cleanup on subscribe/cancel.

Those tests run cleanly on JVMs without agent support.

### 13.2. Concurrency and Responsiveness Tests

Use WebFlux integration tests to observe whether one slow request drives up latency on independent requests, though ensure a stable environment and warm-up so random timings do not mislead you.

You can check `Schedulers.isInNonBlockingThread()` at call sites under inspection to detect whether potentially blocking code runs on an event loop. This indicates thread classification, not automatic detection of all blocking methods.

### 13.3. Static Analysis and Code Review

Look for risky patterns inside reactive callbacks:
- `Thread.sleep`.
- `Future.get`/`CountDownLatch.await`.
- `InputStream.read`/`Files.readAllBytes`.
- Synchronous JDBC/JPA repositories.
- `block()`, `blockFirst()`, `blockLast()`.
- `toIterable()` and conversions to synchronous consumers.
- Synchronous network client SDKs.
- Locks/conditions that may wait long durations.

Static analysis can miss blocking hidden inside libraries or indirect callbacks, yet adds real value when agents cannot run.

### 13.4. Load Testing and Thread Dumps

Monitor event-loop utilization, p95/p99 latency, blocked/waiting thread states, and stack traces. If event-loop threads frequently sit inside JDBC/`Thread.sleep`/file reads, that is a clear signal to fix even without BlockHound.

### 13.5. Honest Test Reporting

| Condition | Accurate report |
| --- | --- |
| BlockHound tests enabled, agent installed, positive probe throws expected error | BlockHound detection verified |
| BlockHound tests not enabled | SKIPPED / not executed |
| Agent unsupported, tests not enabled | Not available on runner |
| Agent enabled yet installation failed | FAILED / setup failure |
| No errors observed in executed cases | No detected violation in tested paths only |

Never report "BlockHound PASS" for a runner that only executed baseline Reactor tests.

## 14. Intentional CI Integration

A practical CI pipeline:

~~~text
Build/CI
  |
  +--> Unit + StepVerifier baseline (all runners)
  |
  +--> Supported JVM job (opt-in)
  |       |
  |       +--> Java 17 + JVM native-method flag
  |       +--> -Pblockhound=true
  |       +--> instrumentation setup
  |       +--> positive detection probe
  |       +--> regression tests
  |
  +--> API integration tests
  |
  +--> Performance/latency and resource metrics
~~~

### 14.1. Pick a Verified Runner

Start with Java 17 HotSpot/OpenJDK on a runner with working attach instrumentation. Check Byte Buddy/BlockHound versions when upgrading JDKs. Do not upgrade all CI jobs to a new JDK and assume dynamic agents still work.

### 14.2. Opt-In and Fail-Fast

- Runner not yet confirmed supported: run `gradle test`; BlockHound class is transparently skipped.
- Runner confirmed supported: run `gradle test -Pblockhound=true`.
- When agent installation fails on an opted-in runner: fail the job and inspect JVM flags/runtime; never swallow exceptions.
- After upgrading JDK or BlockHound versions: run the positive probe before trusting test results.

### 14.3. Do Not Turn Skips into Quality "Success"

CI dashboards should display at least executed/skipped test counts and the name of the agent-enabled job. Tests marked skipped provide zero evidence of blocking detection. When BlockHound is a required quality gate, configure a dedicated job on a compatible runner and treat agent installation failures as blockers.

### 14.4. Isolate JVM-Wide Tests

BlockHound instrumentation has no general-purpose uninstall between tests. When running many tests in the same fork, watch out for global `Schedulers` hooks, parallel JUnit execution, and mocking agents. Split out a separate Gradle test task/JVM if a large suite needs isolation.

## 15. Troubleshooting

### 15.1. BlockHound Reports Missing JVM Flag

Symptom:

~~~text
It looks like you're running on JDK 13+.
You need to add '-XX:+AllowRedefinitionToAddDeleteMethods' JVM flag.
~~~

Fix: add the flag in `tasks.named('test', Test) { jvmArgs ... }` or the corresponding Surefire/Failsafe test JVM configuration. Re-run the opt-in tests. Do not just set an environment variable assuming every fork inherits it.

### 15.2. Cannot Self-Attach / Load Agent

Symptoms can be `IllegalStateException`, Byte Buddy attach failures, agent loading restrictions, or a JVM exception before test bodies execute.

Check JDK vendor, container security policies, JVM dynamic attach settings, Byte Buddy/BlockHound versions, and other coverage tools. If the current JVM cannot support it, run BlockHound on a compatible runner and keep baseline tests running there.

### 15.3. BlockHound Is Present Yet Tests Report No Error

Check:
1. Did `BlockHound.install()` actually run successfully?
2. Was the test class skipped by `@EnabledIfSystemProperty`?
3. Was the request/publisher subscribed to?
4. Did the blocking call run on `Schedulers.parallel`/`single` or an event loop?
5. Was the source accidentally placed on `boundedElastic` or the JUnit thread?
6. Is the method among the instrumented methods?
7. Did an allowlist or other integration ignore the call?

A controlled `Thread.sleep` test on `parallel` is a better baseline sanity check than guessing from a complex pipeline.

### 15.4. Reactor's block() Error Is Not BlockingOperationError

If the exception is `IllegalStateException` with message `block() ... not supported in thread`, that is likely Reactor's own guard. Although the root cause is also blocking on the wrong scheduler, do not present it as proof that BlockHound was installed successfully.

### 15.5. Errors Appear Only After Adding BlockHound

Read the stack trace to locate the blocking I/O call. If it is in your code, fix it with a reactive API or isolate it on `boundedElastic`. If it is in framework bootstrap/logging, verify lifecycle and version compatibility before considering a narrow allowlist. Never disable the entire detector because of a new failure.

### 15.6. JVM Warning About Dynamic Agents

Newer JDKs may warn that dynamic agent loading will be restricted in the future. Do not conclude tests failed from a warning alone; verify setup succeeded and the positive probe threw `BlockingOperationError`. Under JVM policies that block agents, do not try to bypass environment restrictions; pick another runner for agent tests.

### 15.7. Tests Randomly Fail Due to Scheduler Timing

For stable tests:
- Never expect exact millisecond timings.
- Use generous `StepVerifier` timeouts (e.g., 5 seconds).
- Do not depend on ordering across scheduler workers without a contract.
- Avoid `Thread.sleep` to "wait for schedulers to start".
- Do not spawn thousands of blocking tasks in unit tests.
- Let tests verify behavior rather than throughput.

## 16. Practice Exercises

### Exercise 1: Detecting an Error After publishOn

Run `BlockHoundOptionalTest.detectsSleepAfterPublishOn` with `-Pblockhound=true` on a supported JVM. Explain why `map` calling `legacyWait` runs on a `parallel` worker.

**Answer:** `publishOn(Schedulers.parallel())` switches the execution context for operators downstream of it. Therefore `legacyWait` runs on a non-blocking thread, and `Thread.sleep` is caught by BlockHound.

### Exercise 2: Fixing a Blocking Source

Replace:

~~~java
Mono.fromCallable(() -> BlockingExamples.legacyWait("abc"))
    .subscribeOn(Schedulers.parallel());
~~~

With:

~~~java
Mono.fromCallable(() -> BlockingExamples.legacyWait("abc"))
    .subscribeOn(Schedulers.boundedElastic());
~~~

Explain that this only isolates blocking onto an appropriate scheduler without making `Thread.sleep` non-blocking. If the need is a delay, replace it with `Mono.delay`/`delayElement`.

### Exercise 3: Adding a Non-Blocking Test

Create a `Mono` uppercasing text with no blocking API calls, run it on `parallel`, and assert completion. This serves as a negative control for the positive detection probe.

### Exercise 4: Simulating an Unsupported Environment

Run `gradle test` without `-Pblockhound=true`. Observe that the BlockHound test class is skipped. Ensure QA reports do not write "BlockHound detected no blocking" merely because the test class was skipped.

### Exercise 5: Adding a Rule for a Legacy Method

For `com.example.LegacyStore.load(String)`, consider `markAsBlocking` using the exact descriptor; write a positive test on `parallel` and a control test on `boundedElastic`. Do not permit broad exceptions without evaluating their impact.

## 17. Code Review and CI Checklist

1. **Environment:** does the test JVM support Java instrumentation and the Byte Buddy agent?
2. **Flag:** on JDK 13+, was `-XX:+AllowRedefinitionToAddDeleteMethods` passed to the test JVM?
3. **Version:** are Reactor Core/Test and BlockHound versions compatible?
4. **Install:** does `BlockHound.install()` run once early enough?
5. **Marker:** does the positive probe run on a non-blocking thread?
6. **Detection:** do tests assert `BlockingOperationError` rather than any generic exception?
7. **Negative control:** does non-blocking logic on `parallel` complete?
8. **Legacy control:** does the blocking bridge on `boundedElastic` work and stay bounded?
9. **Scheduler placement:** are `subscribeOn`/`publishOn` placed properly?
10. **API:** can the blocking API be replaced with a genuine reactive API?
11. **Scope:** are any critical code paths left unexecuted in tests?
12. **Exceptions:** is there any overly broad allowlist hiding real blocking?
13. **Global state:** do test classes avoid installing/altering rules multiple times in the same JVM?
14. **CI opt-in:** are unsupported runners reported SKIPPED while opted-in failures report FAILED?
15. **Monitoring:** are metrics, profiling, and latency/load tests also in place?
16. **Prod:** are test agents and test JVM flags kept out of production unless overhead and compatibility are evaluated?

**Conclusion:** BlockHound is a valuable companion for Reactor testing, catching blocking methods on non-blocking threads like `Schedulers.parallel()` and event loops when the agent can be installed. Configure the JVM properly, verify with a positive probe, and assert `BlockingOperationError`. When a JDK or environment does not support instrumentation, never fake a PASS; transparently skip the opt-in test class and rely on baseline `StepVerifier` tests, code review, profiling, and integration testing. Fixes should prioritize non-blocking APIs; when legacy blocking code is unavoidable, isolate it on `boundedElastic` with appropriate resource bounds.

## References

- BlockHound — GitHub README, installation, integrations, JDK 13+ flag: https://github.com/reactor/BlockHound
- BlockHound — Quick Start: https://github.com/reactor/BlockHound/blob/master/docs/quick_start.md
- BlockHound — Customization: https://github.com/reactor/BlockHound/blob/master/docs/customization.md
- BlockHound — Releases (1.0.18.RELEASE, October 2026): https://github.com/reactor/BlockHound/releases
- Reactor Core 3.8 — Threading and Schedulers: https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html
- Reactor Core 3.8 — NonBlocking and Schedulers API: https://projectreactor.io/docs/core/release/api/reactor/core/scheduler/Schedulers.html
- Reactor Test — StepVerifier: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html
- Reactor BlockHound Builder — API reference: https://projectreactor.io/docs/BlockHound/snapshot/api/reactor/blockhound/BlockHound.Builder.html
