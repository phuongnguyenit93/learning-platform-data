# Detecting Blocking Calls Deep Inside Spring WebFlux Dependencies

## 1. The Problem: Reactive Code Can Still Make Blocking Calls

A controller may return §Mono§, services may use Reactor operators, and repositories may use reactive APIs, yet a dependency deep underneath may still perform synchronous I/O.

~~~java
@GetMapping("/prices/{sku}")
public Mono<PriceView> price(@PathVariable String sku) {
    return pricingService.find(sku);
}
~~~

The service may look reactive:

~~~java
public Mono<PriceView> find(String sku) {
    return Mono.fromCallable(() -> vendorSdk.fetch(sku))
        .map(PriceView::from);
}
~~~

Seeing §Mono§ is not enough to conclude the system is non-blocking. If §vendorSdk.fetch§ calls deep down into JDBC, §SocketInputStream.read§, §Thread.sleep§, §Future.get§, or a synchronous wait method, the thread running the pipeline is still held until that call returns.

~~~text
WebFlux Controller
      |
      v
PricingService.find()
      |
      v
VendorPricingSdk.fetch()
      |
      v
VendorHttpFacade.read()
      |
      v
LegacyTransport.execute()
      |
      v
SocketInputStream.read()  <-- blocking call
~~~

The blocking occurs at the lowest layer even though the controller and service contain no direct blocking calls. Therefore, inspecting only application source code is not enough; you also need to examine the dependency tree, stack traces, and runtime behavior.

The goal of this lesson is to detect blocking calls deep inside libraries, trace the call path, reproduce them with tests, and choose a fix that fits the WebFlux concurrency model.

## 2. Why Search for Blocking in Dependencies Too?

With Reactor Netty, a small group of event-loop threads handles many connections. Each thread takes turns processing requests, callbacks, and responses:

~~~text
reactor-http-nio-1
   |-- request A: read headers
   |-- request B: process callback
   |-- request C: write response
   |-- request A: DB callback completed
   |-- request D: read body
~~~

If request A calls a blocking SDK and waits 500 ms, the event-loop thread cannot process other work during that time. A few blocking calls can affect many unrelated requests.

Common symptoms under rising load:

- P95/P99 latency spikes even though CPU is not necessarily high.
- Timeouts and retries increase.
- Many requests slow down together even though only one dependency has an issue.
- Thread dumps show event-loop threads paused inside the same vendor method.
- Event-loop, scheduler, or connection pool queues grow.
- Retries amplify load on the already-slow dependency and spread the incident.

Reactive/non-blocking does not automatically make every single request faster. Its primary benefit is handling many concurrent I/O tasks with a relatively small number of threads. That benefit diminishes if the event-loop has to wait on synchronous I/O.

Thread names offer a clue:

| Common Thread Name | Role |
| --- | --- |
| §reactor-http-nio-*§ | Reactor Netty event loop |
| §parallel-*§ | Non-blocking scheduler for CPU-bound work |
| §boundedElastic-*§ | Bounded worker pool for blocking work |

A thread name alone is not conclusive; inspect stack traces, thread markers, and where scheduler switches occur.

## 3. Types of Blocking Commonly Hidden in Dependencies

| Category | API or Symptom | Risk |
| --- | --- | --- |
| Thread sleep/wait | §Thread.sleep§, §Object.wait§ | Holds the thread |
| Synchronous Future | §Future.get§, §CompletableFuture.join§ | Waits on another task |
| Lock/coordination | §CountDownLatch.await§, §Semaphore.acquire§, §LockSupport.park§ | Waits on a thread or signal |
| File I/O | §FileInputStream.read§, §Files.readAllBytes§, §RandomAccessFile§ | Waits on the filesystem |
| Network I/O | §Socket.connect/read§, §ServerSocket.accept§ | Waits on synchronous networking |
| Database | JDBC §executeQuery§, §ResultSet.next§, JPA repositories | Waits on database via blocking driver |
| Process | §Process.waitFor§ | Waits on an external process |
| Logging | Synchronous file/socket appender | Log I/O blocks the event loop |
| Native/custom code | JNI or custom wait methods | May not be instrumented |

A dependency may call through multiple layers:

~~~java
public Price fetch(String sku) {
    return client.getPrice(sku);
}

public Price getPrice(String sku) {
    return transport.readPrice(sku);
}

public Price readPrice(String sku) {
    return jdbcTemplate.queryForObject(
        "select price from prices where sku = ?",
        Price.class,
        sku
    );
}
~~~

The controller only sees §fetch§, but the blocking happens in JDBC. Stack traces from BlockHound or thread dumps help trace the call chain.

### Distinguishing Slow I/O, Blocking, and CPU-Bound Work

- **Slow non-blocking I/O:** the downstream request takes a long time, but the thread is released while waiting.
- **Blocking call:** the executing thread is held until the synchronous call returns.
- **CPU-bound work:** the thread is busy computing; not blocking I/O, yet it can still stall the event loop.
- **Lock contention:** threads wait on locks; can cause bottlenecks even without familiar I/O API calls.

BlockHound primarily detects blocking APIs that have been instrumented. It does not replace a profiler for finding every CPU hotspot or every form of lock contention.

## 4. How Does BlockHound Work?

§BlockHound§ is a Java agent from Project Reactor. It instruments a set of blocking methods in the JVM and checks when they execute on threads marked solely for non-blocking work.

Reactor threads such as those created by §Schedulers.parallel()§ implement the §NonBlocking§ marker. If an instrumented blocking method runs on such a thread, BlockHound throws §BlockingOperationError§ by default.

~~~java
BlockHound.install();

Mono.delay(Duration.ofMillis(10))
    .doOnNext(ignored -> {
        try {
            Thread.sleep(5);
        }
        catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(ex);
        }
    })
    .subscribeOn(Schedulers.parallel())
    .block();
~~~

The §Thread.sleep§ call here runs on a non-blocking thread. BlockHound may report:

~~~text
reactor.blockhound.BlockingOperationError:
Blocking call! java.lang.Thread.sleep

at java.base/java.lang.Thread.sleep(...)
at com.example.Demo.lambda$main$0(Demo.java:...)
~~~

The stack trace identifies both the blocking API and the frame calling it, helping uncover calls located inside external libraries as well.

### Limitations to Understand

1. BlockHound focuses on methods that have been instrumented or marked as blocking.
2. It reports only when the call executes on a thread recognized as non-blocking.
3. A blocking call on a regular thread or §boundedElastic§ may go unreported.
4. Native code, custom spin loops, monitor contention, or custom waiting mechanisms may not be fully detected.
5. A CPU-bound method taking 300 ms will not necessarily be flagged.
6. The absence of BlockHound errors does not prove the entire dependency stack is non-blocking.

Combine BlockHound with source/bytecode inspection, thread dumps, JFR, a profiler, and load tests.

## 5. Installing BlockHound in a Java 17 Project

At the time of writing, BlockHound has release §1.0.18.RELEASE§ on Maven Central. When upgrading, check the release and compatibility requirements for your JDK.

Test dependency:

~~~xml
<dependency>
    <groupId>io.projectreactor.tools</groupId>
    <artifactId>blockhound</artifactId>
    <version>1.0.18.RELEASE</version>
    <scope>test</scope>
</dependency>
~~~

Install the agent once before the tests to be verified run:

~~~java
class BlockingDependencyTest {

    static {
        BlockHound.install();
    }

    // tests...
}
~~~

§BlockHound.install()§ loads registered integrations via ServiceLoader and performs instrumentation. This is a global operation; there is no need to reinstall it per test.

It can be installed in a test listener or test bootstrap to ensure the agent runs before other tests. If the framework already installs BlockHound itself, use the §BlockHoundIntegration§ SPI for additional configuration.

Always include a smoke test with a known blocking call on §Schedulers.parallel()§ to confirm that instrumentation actually works.

If installation fails due to self-attach, Byte Buddy, or JVM instrumentation limits, check the error message and the documentation for the version in use. The agent can be configured via §-javaagent§ in the test/runtime JVM. Some JDK 13+ setups instruct adding §-XX:+AllowRedefinitionToAddDeleteMethods§; only add that flag when your specific environment reports it is needed rather than copying it blindly across all JDKs.

## 6. Reading Stack Traces and Finding the Deep Dependency

Suppose BlockHound reports:

~~~text
reactor.blockhound.BlockingOperationError:
Blocking call! java.lang.Thread.sleep

at java.lang.Thread.sleep(...)
at com.vendor.internal.RetryGate.waitBeforeRetry(RetryGate.java:84)
at com.vendor.http.LegacyTransport.execute(LegacyTransport.java:133)
at com.vendor.pricing.PricingClient.fetch(PricingClient.java:51)
at com.example.pricing.PricingService.lambda$find$0(PricingService.java:27)
~~~

Read from top to bottom:

1. §Thread.sleep§ is the actual blocking API.
2. §RetryGate.waitBeforeRetry§ is the vendor's internal class waiting before retry.
3. §LegacyTransport.execute§ is the transport layer invoking the wait method.
4. §PricingClient.fetch§ is the public API called by the application.
5. §PricingService.lambda...§ is where the application brings the dependency into the reactive pipeline.

Do not just patch the service line if the real issue resides in the SDK. Evaluate whether a non-blocking SDK version, a genuine async API, or a configuration to disable synchronous retry/sleep is available.

### When Dependency Source Code Is Unavailable

1. Identify the artifact and version using §mvn dependency:tree -Dverbose§.
2. Check which transitive dependency pulls the SDK onto the classpath.
3. Look for a sources JAR if published by the vendor.
4. Use an IDE decompiler to inspect the implementation.
5. Use §jar tf dependency.jar§ to locate relevant classes.
6. Use §javap -c -p§ with an appropriate classpath to inspect bytecode.
7. Cross-reference the stack trace with the vendor's release notes and issue tracker.
8. Write a minimal test calling only the suspect method to reproduce it.

Example:

~~~bash
mvn dependency:tree -Dverbose
mvn dependency:tree -Dincludes=com.vendor:pricing-sdk
~~~

If you only see the surface method §fetch§, keep tracing the call stack or bytecode to find where Socket, JDBC, file APIs, or waiting mechanisms are invoked.

Searching for §Thread.sleep§ in application source code will not uncover blocking inside dependency JARs, generated code, or indirectly invoked methods. An empty search result does not prove the system is clean.

## 7. Testing Deep Blocking with StepVerifier

A good test should run the dependency on a non-blocking thread and assert that an error appears in the Publisher:

~~~java
BlockHound.install();

Mono<String> result = Mono.fromCallable(
        () -> vendorClient.fetchPrice("BOOK-1")
    )
    .subscribeOn(Schedulers.parallel());

StepVerifier.create(result)
    .expectError(BlockingOperationError.class)
    .verify(Duration.ofSeconds(3));
~~~

§fromCallable§ catches exceptions during invocation; the BlockHound error is propagated as an §onError§ signal of the Mono. §StepVerifier§ asserts the error type and applies a timeout to prevent hanging tests.

Do not call the method directly on a JUnit thread to test it:

~~~java
vendorClient.fetchPrice("BOOK-1");
~~~

A standard JUnit thread is not marked §NonBlocking§, so BlockHound may not report anything even if the call blocks. The test must execute the call on a thread belonging to the non-blocking group.

You can verify that the stack trace contains the dependency class:

~~~java
StepVerifier.create(result)
    .expectErrorSatisfies(error -> {
        assertInstanceOf(BlockingOperationError.class, error);

        boolean vendorFrameFound = Arrays.stream(error.getStackTrace())
            .anyMatch(frame ->
                frame.getClassName().contains("LegacyPricingSdk")
            );

        assertTrue(
            vendorFrameFound,
            "Stack trace should identify the dependency call path"
        );
    })
    .verify(Duration.ofSeconds(3));
~~~

## 8. Moving Blocking Dependencies Off the Event Loop

If a synchronous library cannot yet be replaced, isolate the call on §Schedulers.boundedElastic()§:

~~~java
Mono<String> price(String sku) {
    return Mono.fromCallable(() -> vendorClient.fetchPrice(sku))
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

§boundedElastic§ is designed for resource-bounded blocking tasks. It does not turn the SDK reactive, but it prevents the event loop from waiting on synchronous calls.

The controller can still return a Publisher:

~~~java
@GetMapping("/prices/{sku}")
public Mono<PriceView> price(@PathVariable String sku) {
    return pricingService.price(sku)
        .map(value -> new PriceView(sku, value));
}
~~~

### subscribeOn and publishOn

For a blocking source, use §subscribeOn§ to shift subscribing/evaluating the source onto another scheduler:

~~~java
Mono.fromCallable(vendorClient::fetchPrice)
    .subscribeOn(Schedulers.boundedElastic());
~~~

§publishOn§ changes the scheduler for downstream operators starting from where it is placed. Placing §publishOn§ after a source callable does not automatically shift the initial callable invocation:

~~~java
// Not the recommended way to isolate a source callable.
Mono.fromCallable(vendorClient::fetchPrice)
    .publishOn(Schedulers.boundedElastic());
~~~

If blocking occurs in a downstream operator, §publishOn§ placed before that operator can shift that processing stage. For synchronous calls at the source, §subscribeOn§ is usually clearer.

### Methods Returning Mono That Block Before Returning

A method may return a Mono yet perform eager blocking while being invoked:

~~~java
Mono<Price> fetch() {
    return vendorClient.fetchReactive();
}
~~~

If §fetchReactive()§ blocks right when called before returning the Mono, adding §subscribeOn§ after the method has already been invoked may be too late.

Use §Mono.defer§ to defer the method call itself until subscription:

~~~java
Mono<Price> fetch() {
    return Mono.defer(() -> vendorClient.fetchReactive())
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

If the SDK is genuinely non-blocking and performs I/O only when the Publisher is subscribed to, do not wrap it in boundedElastic. If the method is synchronous or blocks immediately when called, use §fromCallable§ or §defer§ so the call runs on an appropriate scheduler.

### boundedElastic Is Not the Final Solution

- The pool has bounded threads and queues; excess load can still cause waiting.
- Many concurrent requests calling a slow SDK can cause queues and latency to climb.
- Publisher timeouts do not guarantee the underlying blocking library will interrupt the I/O call.
- Cancellation may not interrupt an in-progress synchronous call.
- Bound concurrency, configure client/driver timeouts, and apply bulkheads when needed.
- Prefer replacing the SDK with an official reactive or non-blocking API if available.

## 9. Marking Custom Methods and Handling Exceptions

A dependency may use JNI or native/custom methods to wait, causing BlockHound not to recognize that method by default.

§BlockHound.Builder§ allows marking additional methods as blocking:

~~~java
BlockHound.install(builder -> builder
    .markAsBlocking(
        "com.vendor.nativebridge.LegacyTransport",
        "readPrice",
        "(Ljava/lang/String;)Ljava/lang/String;"
    )
);
~~~

The last parameter is the method descriptor in JVM notation. In this example, the method takes one §String§ and returns one §String§.

Use this once you have verified the method actually blocks. Do not mark a method merely because its name contains §read§ or §fetch§; verify the implementation first.

### Custom Thread Pools

If the application uses a custom thread pool and wants BlockHound to treat those threads as non-blocking, you can customize the predicate. Preserve the built-in predicate:

~~~java
BlockHound.install(builder -> builder
    .nonBlockingThreadPredicate(current ->
        current.or(thread -> thread.getName().startsWith("my-event-loop-"))
    )
);
~~~

Do not completely replace the default predicate without understanding other integrations. Mislabeling a thread pool can trigger unintended errors for blocking calls that are legitimately permitted on it.

### allowBlockingCallsInside

You can declare a method as permitted to contain blocking calls:

~~~java
BlockHound.install(builder -> builder
    .allowBlockingCallsInside(
        "com.vendor.logging.LegacyAppender",
        "append"
    )
);
~~~

This is a narrowly scoped exception. Allowing a method may also allow blocking calls nested deep beneath it. If a specific child method still needs to be disallowed, use §disallowBlockingCallsInside§ to override it intentionally.

Do not allow an entire vendor package, every §execute/read/write§ method, or all threads. An allowlist does not make a library non-blocking.

## 10. False Positives and Logging

BlockHound may detect blocking calls inside libraries the team does not call directly. That is not automatically a false positive: if the call happens on the event loop, it truly blocks the thread.

Logging example:

~~~text
reactor-http-nio-2
  -> application log
  -> synchronous file appender
  -> file write
~~~

If a logger writes to a file synchronously on the event loop, BlockHound can catch it. The typical fix is using an asynchronous appender or moving logging I/O off the event loop, not disabling all checks.

If you must allow a third-party library method, document the reason, scope, version, and tests ensuring other call paths remain checked. Re-evaluate the exception after upgrading dependencies.

## 11. Reactor Debugging Complements BlockHound

The two tools answer different questions:

- **BlockHound:** which blocking method is running on a thread that is not allowed to block?
- **Reactor debugging:** where were the reactive operators assembled, and which pipeline stages did an error pass through?

### checkpoint

~~~java
return pricingService.find(sku)
    .checkpoint("pricing-controller -> vendor-pricing");
~~~

A labeled checkpoint helps identify the relevant chain when a Reactor error occurs. It does not detect blocking calls on its own.

### Global Operator Debug

~~~java
Hooks.onOperatorDebug();
~~~

This hook captures assembly stack traces for operators created after the hook is enabled. Reactor documentation warns that this incurs higher cost because stack traces must be captured across many operators; use it selectively in diagnostic environments.

### ReactorDebugAgent

§ReactorDebugAgent§ from the §reactor-tools§ artifact can instrument classes to provide assembly traces at a more suitable cost than global stacktrace capture. Initialize it before the application constructs reactive chains:

~~~java
public static void main(String[] args) {
    ReactorDebugAgent.init();
    SpringApplication.run(Application.class, args);
}
~~~

This is an assembly debugging tool, not a blocking detector. It does not replace BlockHound.

### log Operator

~~~java
return pricingService.find(sku)
    .log("pricing-pipeline");
~~~

§log()§ observes subscribe, request, onNext, onError, onComplete, and cancel at the operator's position. It is useful for seeing whether a pipeline subscribes/cancels properly, but logging signals does not by itself prove threads are unblocked.

When logging in production, configure the logging backend so it does not block request-processing threads.

## 12. Thread Dumps, JFR, and Profilers Under Load

BlockHound is great for targeted testing. When issues appear only under production-like load, combine runtime tools.

### Thread Dumps

~~~bash
jcmd <pid> Thread.print
~~~

Look for §reactor-http-nio-*§ threads and read their stacks. If multiple threads are paused in the same vendor method, that is a strong signal the dependency is blocking the event loop.

Frames worth watching for:

~~~text
java.lang.Thread.sleep
java.io.FileInputStream.read
java.net.SocketInputStream.socketRead0
java.util.concurrent.CountDownLatch.await
java.util.concurrent.FutureTask.get
java.util.concurrent.locks.LockSupport.park
com.vendor.internal.LegacyTransport.execute
~~~

A single frame is not enough to conclude. Examine thread states, repetition over time, request latency, and thread dumps across multiple snapshots.

### Java Flight Recorder

~~~bash
jcmd <pid> JFR.start name=webflux-blocking duration=60s filename=webflux-blocking.jfr
~~~

Then open the file with Java Mission Control to inspect thread activity, monitor contention, socket/file I/O, and related events. JFR does not replace BlockHound, but it helps uncover issues that appear only during real execution.

### Monitoring Metrics

Combine:

- P50/P95/P99 latency per endpoint.
- Request rate, active requests, and timeout count.
- Event-loop pending tasks/queue if the connector exposes metrics.
- Scheduler queues and thread usage.
- BoundedElastic active/queued task count.
- Database connection pool active/pending/timeouts.
- Downstream client latency and connection pools.
- CPU usage, allocations, and GC pauses.

If CPU is low yet latency is high and event-loop threads are frequently WAITING/TIMED_WAITING inside the same dependency, prioritize investigating blocking I/O or lock contention. If CPU is high and stacks sit inside computation loops, investigate CPU-bound work rather than relying solely on BlockHound.

## 13. Complete Example: Spring Boot 3.5, Java 17, and BlockHound

This project simulates a third-party SDK with multiple nested call layers. The bottom layer uses §Thread.sleep§ to represent a synchronous operation. BlockHound catches the call deep inside the SDK when run on §Schedulers.parallel()§; the adapter using boundedElastic completes.

### 13.1. Structure

~~~text
webflux-blocking-diagnostics/
├── pom.xml
└── src/
    ├── main/java/com/example/blocking/
    │   ├── BlockingDiagnosticsApplication.java
    │   ├── LegacyPricingSdk.java
    │   ├── PricingService.java
    │   └── PricingController.java
    └── test/java/com/example/blocking/
        └── BlockingDependencyTest.java
~~~

### 13.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>webflux-blocking-diagnostics</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>io.projectreactor.tools</groupId>
            <artifactId>blockhound</artifactId>
            <version>1.0.18.RELEASE</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
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
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <configuration>
                    <argLine>-XX:+AllowRedefinitionToAddDeleteMethods</argLine>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

BlockHound is in test scope only. The JVM flag in Surefire is an instrumentation compatibility setting noted by the BlockHound quick start for certain JDK 13+ versions; check the requirements of the exact JDK and BlockHound release in use. If your environment already supports self-attach/instrumentation without the flag, you can omit that configuration after verifying the test still installs the agent successfully.

### 13.3. BlockingDiagnosticsApplication.java

~~~java
package com.example.blocking;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BlockingDiagnosticsApplication {

    public static void main(String[] args) {
        SpringApplication.run(BlockingDiagnosticsApplication.class, args);
    }
}
~~~

### 13.4. LegacyPricingSdk.java

~~~java
package com.example.blocking;

import org.springframework.stereotype.Component;

@Component
public class LegacyPricingSdk {

    public String fetchPrice(String sku) {
        return LegacyTransport.readPrice(sku);
    }

    private static class LegacyTransport {

        private static String readPrice(String sku) {
            try {
                Thread.sleep(25);
            }
            catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                    "Legacy pricing call interrupted", ex
                );
            }

            return "42.00";
        }
    }
}
~~~

§fetchPrice§ is only a facade. The actual blocking resides in §LegacyTransport.readPrice§, simulating a dependency's internal transport layer.

In a real system, this deep class may belong to a vendor JAR without source code and appear only in stack traces or bytecode decompilation.

### 13.5. PricingService.java

~~~java
package com.example.blocking;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Service
public class PricingService {

    private final LegacyPricingSdk sdk;

    public PricingService(LegacyPricingSdk sdk) {
        this.sdk = sdk;
    }

    public Mono<String> findUnsafe(String sku) {
        return Mono.fromCallable(() -> sdk.fetchPrice(sku))
            .subscribeOn(Schedulers.parallel());
    }

    public Mono<String> findSafely(String sku) {
        return Mono.fromCallable(() -> sdk.fetchPrice(sku))
            .subscribeOn(Schedulers.boundedElastic());
    }
}
~~~

§findUnsafe§ is solely for failure-detection tests; do not use this pattern in production endpoints. §findSafely§ demonstrates a temporary adapter when a synchronous SDK cannot yet be replaced.

### 13.6. PricingController.java

~~~java
package com.example.blocking;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/prices")
public class PricingController {

    public record PriceView(String sku, String amount) {}

    private final PricingService service;

    public PricingController(PricingService service) {
        this.service = service;
    }

    @GetMapping("/{sku}")
    public Mono<PriceView> price(@PathVariable String sku) {
        return service.findSafely(sku)
            .map(amount -> new PriceView(sku, amount));
    }
}
~~~

### 13.7. BlockingDependencyTest.java

~~~java
package com.example.blocking;

import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.util.Arrays;

import org.junit.jupiter.api.Test;

import reactor.blockhound.BlockHound;
import reactor.blockhound.BlockingOperationError;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

class BlockingDependencyTest {

    static {
        BlockHound.install();
    }

    private final LegacyPricingSdk sdk = new LegacyPricingSdk();

    @Test
    void detectsBlockingCallDeepInsideDependency() {
        Mono<String> result = Mono.fromCallable(
                () -> sdk.fetchPrice("BOOK-1")
            )
            .subscribeOn(Schedulers.parallel());

        StepVerifier.create(result)
            .expectErrorSatisfies(error -> {
                assertInstanceOf(
                    BlockingOperationError.class,
                    error
                );

                boolean vendorFrameFound = Arrays.stream(error.getStackTrace())
                    .anyMatch(frame ->
                        frame.getClassName().contains("LegacyPricingSdk")
                    );

                assertTrue(
                    vendorFrameFound,
                    "Stack trace should identify the dependency call path"
                );
            })
            .verify(Duration.ofSeconds(3));
    }

    @Test
    void blockingDependencyWorksWhenIsolatedOnBoundedElastic() {
        Mono<String> result = Mono.fromCallable(
                () -> sdk.fetchPrice("BOOK-1")
            )
            .subscribeOn(Schedulers.boundedElastic());

        StepVerifier.create(result)
            .expectNext("42.00")
            .verifyComplete();
    }
}
~~~

The first test runs the SDK on §Schedulers.parallel()§. BlockHound catches §Thread.sleep§ at the deep layer and StepVerifier confirms the stack trace contains §LegacyPricingSdk§.

The second test runs the same SDK on boundedElastic. BlockHound does not raise an error because this scheduler permits blocking tasks; the Publisher emits §42.00§ and completes.

These two tests do not prove the SDK has become non-blocking. They demonstrate how to detect the issue and how to isolate synchronous calls away from non-blocking threads.

### 13.8. Running the Project

Requires JDK 17+ and Maven:

~~~bash
mvn test
~~~

There are two tests in the example. When BlockHound installs successfully and the JVM environment satisfies instrumentation requirements, both tests pass; Maven finishes with §BUILD SUCCESS§.

Start the application:

~~~bash
mvn spring-boot:run
~~~

Call the endpoint:

~~~bash
curl -i http://localhost:8080/prices/BOOK-1
~~~

Expected response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
~~~

~~~json
{"sku":"BOOK-1","amount":"42.00"}
~~~

This is a demo using a mock SDK to reproduce blocking. In a real application, replace §LegacyPricingSdk§ with the actual dependency and add tests along real call paths.

## 14. When a Dependency Provides Both Blocking and Reactive APIs

Some libraries offer both methods:

~~~java
Price fetch(String sku);                 // synchronous
Mono<Price> fetchReactive(String sku);   // non-blocking
~~~

If the reactive API truly uses non-blocking I/O, prefer that method:

~~~java
return vendorClient.fetchReactive(sku)
    .map(PriceView::from);
~~~

Do not wrap a reactive method in boundedElastic solely because it is an external dependency. Check the implementation, documentation, and tests to verify there is no blocking during assembly/subscription.

If the SDK lacks a reactive API:

~~~java
return Mono.fromCallable(() -> vendorClient.fetch(sku))
    .subscribeOn(Schedulers.boundedElastic());
~~~

If the SDK returns a Mono yet the method constructing the Mono may block eagerly:

~~~java
return Mono.defer(() -> vendorClient.fetchReactive(sku))
    .subscribeOn(Schedulers.boundedElastic());
~~~

If the dependency is JDBC/JPA, renaming a method or wrapping it in a Mono does not make it reactive. Consider R2DBC/an official async driver if the system needs end-to-end non-blocking behavior.

## 15. Rollout Strategy and Protecting Performance

Integrate blocking detection into the development workflow:

1. Add BlockHound under a controlled test profile.
2. Write tests for adapters/services that use SDKs, files, databases, or legacy libraries.
3. Install BlockHound once before tests run.
4. Execute tests on a Reactor non-blocking scheduler to expose blocking calls.
5. Inspect stack traces and dependency versions.
6. Replace with a non-blocking API if available.
7. If replacement is not yet possible, isolate calls with boundedElastic.
8. Configure timeouts at the SDK/driver level, bound concurrency, and monitor queues.
9. Load test endpoints after fixes to verify p95/p99 latency and throughput.
10. Use thread dumps/JFR when issues appear only under load.

Do not enable every instrumentation/debug hook in production without evaluating overhead. BlockHound is useful in test/diagnostic environments; Reactor assembly tracing, metrics, and profiling serve complementary roles.

### When Is a Change Considered Done?

- The reproduction test for the old bug genuinely fails with BlockingOperationError.
- The adapter or new dependency no longer invokes blocking APIs on non-blocking threads.
- Regression tests pass along the same code path.
- Tests have timeouts and do not depend on arbitrary sleeps or external networks.
- Load tests no longer exhibit event-loop starvation.
- BoundedElastic does not suffer queue/thread saturation from piling up too many blocking tasks.
- Logs/metrics exist to detect regressions after dependency upgrades.

## 16. Common Pitfalls

1. **Searching only for the keyword `block` in controllers:** blocking may reside deep inside dependency JARs.
2. **Seeing a method return Mono and concluding it is non-blocking:** the method may block before returning the Publisher or upon subscription.
3. **Calling the dependency on a JUnit thread and expecting BlockHound to report:** normal test threads are not marked non-blocking.
4. **Installing BlockHound after tests have already started schedulers:** the agent must be installed before the pipelines under test.
5. **Lacking an instrumentation smoke test:** passing tests do not prove BlockHound is actually working if the agent was never installed.
6. **Looking only at thread names:** verify stack traces and thread markers.
7. **Assuming BlockHound catches every CPU hotspot:** it focuses on instrumented blocking APIs.
8. **Assuming no errors means no blocking:** custom/native waits or uninstrumented APIs can slip through.
9. **Using publishOn after Mono.fromCallable to isolate the source:** the callable may still run on the initial subscribing thread; use subscribeOn.
10. **Wrapping a Mono-returning method with subscribeOn while ignoring eager blocking:** use defer if the method call blocks before returning the Publisher.
11. **Moving the entire pipeline onto boundedElastic:** forfeits event-loop benefits and can create excessive queues/threads.
12. **Using parallel for blocking I/O:** this scheduler is meant for CPU-bound, non-blocking work.
13. **Allowing an entire vendor package:** hides truly dangerous calls.
14. **Disabling BlockHound because a logger was flagged:** consider an async appender or a very narrow allowlist after evaluation.
15. **Changing only the dependency version without a regression test:** the issue may resurface on the next upgrade.
16. **Infinite retries against a blocking SDK:** increases queues and wait times when downstream is overloaded.
17. **Believing reactive timeouts always cancel synchronous I/O:** many blocking libraries do not support interruption/cancellation.
18. **Running only unit tests without load tests:** does not prove the event loop avoids starvation under real load.
19. **Ignoring the dependency tree:** you will not know which JAR/version brings the legacy library onto the classpath.
20. **Confusing Reactor checkpoint with BlockHound:** checkpoint traces assembly; BlockHound detects blocking calls.
21. **Using ThreadLocal or log context to infer the scheduler:** context propagation and thread identity are separate concepts.
22. **Failing to check custom thread pools:** BlockHound only recognizes threads according to configured predicates.
23. **Overlooking monitor contention:** synchronized locks or custom waits may require thread dumps/profilers as well.
24. **Assuming boundedElastic makes a dependency reactive:** it only isolates blocking onto a bounded worker pool.

## 17. Checklist for Investigating Blocking in Dependencies

- [ ] Do you know which endpoint/service sees rising latency under load?
- [ ] Do you have thread dumps from the time of the incident?
- [ ] Do event-loop threads share the same stack trace or vendor method?
- [ ] Has the dependency tree identified the artifact and version?
- [ ] Are source JARs or bytecode available to inspect deep methods?
- [ ] Was BlockHound installed before tests ran?
- [ ] Do tests execute the call on a non-blocking thread?
- [ ] Does the stack trace pinpoint the blocking API and dependency class?
- [ ] Is the blocking call a known JDK API or a custom/native method?
- [ ] Is markAsBlocking needed for verified custom methods?
- [ ] Are there false positives from logging or instrumentation?
- [ ] Can you switch to an official reactive API?
- [ ] If blocking must remain, are fromCallable/defer + subscribeOn(boundedElastic) placed correctly?
- [ ] Are concurrency limits, timeouts, and bulkheads configured?
- [ ] Are infinite retries and unbounded queues avoided?
- [ ] Have cancellation and slow-SDK behavior been tested?
- [ ] Are JFR/profiler/metrics used to inspect beyond BlockHound?
- [ ] Have post-change load tests verified latency and throughput?

## 18. Self-Check Questions

**1.** Why can WebFlux become slow even when controllers only return Mono? Because deep underlying dependencies may make blocking calls on the event-loop.

**2.** What is BlockHound? A Java agent that instruments blocking APIs and reports when they are called on threads marked non-blocking.

**3.** What error type does BlockHound throw by default? BlockingOperationError.

**4.** Why run tests on Schedulers.parallel()? Threads of this scheduler are marked non-blocking, exercising the proper BlockHound check condition.

**5.** Does BlockHound detect all CPU hotspots? No; use a profiler/JFR to locate CPU-bound work.

**6.** Does BlockHound detect every custom native wait? Not necessarily; verified custom methods can be marked with markAsBlocking.

**7.** Why not block directly on a JUnit thread to test? A standard JUnit thread is not a non-blocking thread.

**8.** What should you use when wrapping a synchronous method? Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic()).

**9.** If a method returns Mono yet blocks immediately when called, what should you use? Mono.defer(() -> dependency.method()).subscribeOn(boundedElastic()) to defer the invocation.

**10.** How does subscribeOn differ from publishOn? subscribeOn shifts subscribing/source execution; publishOn shifts downstream processing after the operator's placement.

**11.** Should Schedulers.parallel() be used for blocking JDBC? No; parallel is intended for CPU-bound non-blocking work.

**12.** Does boundedElastic make JDBC non-blocking? No, it only moves blocking onto a bounded worker pool.

**13.** Why inspect the BlockHound stack trace? To locate the exact blocking API, class, and method deep within the dependency.

**14.** When is markAsBlocking used? When a custom/native method has been verified to block yet is not recognized by BlockHound.

**15.** What risk does allowBlockingCallsInside carry? It may also allow blocking calls nested deep underneath the allowed method.

**16.** Does Reactor checkpoint replace BlockHound? No; checkpoint adds assembly information for the reactive chain.

**17.** When are thread dumps used? When you need to see where event-loop threads are waiting at the moment the system slows down.

**18.** How does JFR help? Observing thread activity, I/O, lock contention, and runtime behavior under load.

**19.** Does the absence of BlockingOperationError prove there is no blocking? No; the call might be uninstrumented or not running on a non-blocking thread.

**20.** How do you confirm a fix is complete? Regression tests, clean stack traces, no boundedElastic overload, and load tests confirming latency/throughput.

**Key Takeaway:** Blocking can hide deep inside dependencies even when controllers and services use Mono/Flux. Use BlockHound to catch blocking APIs on non-blocking threads, follow stack traces down to the real class/method, and inspect the dependency tree and bytecode when source is missing. Prefer genuine reactive APIs; if a synchronous library must remain, isolate calls with fromCallable/defer and subscribeOn(boundedElastic), along with timeouts and concurrency limits. Combine Reactor debugging, thread dumps, JFR, and load testing because BlockHound does not detect every type of slow work.

**Official Documentation:**
- [Spring Framework 6.2 — WebFlux concurrency model and blocking APIs](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/new-framework.html)
- [BlockHound — GitHub README and agent installation](https://github.com/reactor/BlockHound)
- [BlockHound — Quick Start](https://github.com/reactor/BlockHound/blob/master/docs/quick_start.md)
- [BlockHound — Customization: markAsBlocking, allow/disallow](https://github.com/reactor/BlockHound/blob/master/docs/customization.md)
- [Maven Central — BlockHound 1.0.18.RELEASE](https://central.sonatype.com/artifact/io.projectreactor.tools/blockhound)
- [Project Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html)
- [Project Reactor — Debugging Reactor](https://projectreactor.io/docs/core/release/reference/debugging.html)
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html).