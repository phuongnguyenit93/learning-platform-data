# Testing MDC Context in Java Logging

## 1. Goals of Testing MDC

**Mapped Diagnostic Context (MDC)** is a logging API mechanism that attaches key–value pairs such as `requestId`, `traceId`, `jobId`, or `messageId` to the current context. When the logger and encoder support it and are configured properly, multiple log events from the same task can be correlated using the same ID.

Desired example:

~~~text
INFO  requestId=req-42 event=request_started
WARN  requestId=req-42 event=retry_scheduled
INFO  requestId=req-42 event=request_completed
~~~

**Testing MDC context** is not just calling `MDC.put` and asserting that `MDC.get` returns the expected value. Critical bugs typically appear at boundaries:

- Whether the log event has the right ID **at the moment the logger is called**.
- Whether the previous value is **restored** after the scope ends, or unintentionally removed/retained.
- Whether cleanup still runs when a handler throws an exception.
- Whether the context is propagated properly across `ExecutorService` or `CompletableFuture` boundaries.
- When a thread pool reuses a worker, whether logs from request B carry over request A's `requestId`.
- When multiple tasks run concurrently, whether IDs leak or mix between threads.
- Whether `AsyncAppender` captures MDC before the caller modifies or clears it.
- Whether the JSON/text encoder actually outputs the MDC fields, and whether the collector parses them correctly.
- Whether keys containing personal data or tokens are blocked before logs are emitted.

Key takeaway: **correct state on a thread does not automatically prove that the data is present in the log event or pipeline output**. You need to test each layer and understand the logging provider in use.

## 2. API and Semantics to Know

SLF4J provides the common MDC operations:

| API | Meaning | How to test |
| --- | --- | --- |
| MDC.put(key, value) | Set or overwrite a key | Within the scope, the new value is visible |
| MDC.get(key) | Read a key from the current context | Each task/thread sees the appropriate ID |
| MDC.remove(key) | Remove an individual key | Key is absent after the scope if it did not exist beforehand |
| MDC.clear() | Clear all MDC entries on the current thread | Do not use it to indiscriminately wipe the caller's context |
| MDC.getCopyOfContextMap() | Obtain a copy of the context map | Snapshot does not change unexpectedly after capture |
| MDC.setContextMap(map) | Replace the current context with a map | Worker context is activated and restored |
| MDC.putCloseable(key,value) | Manage key lifecycle via `close` | Do not assume automatic restoration of a nested previous value |
| Logback ILoggingEvent.getMDCPropertyMap() | Query the MDC of an event | Read/capture at a safe point in time |

SLF4J is a **facade/API**, while Logback or Log4j 2 is the concrete implementation. How an adapter stores and captures MDC may vary by version. Tests that use Logback's `ILoggingEvent` are not provider-independent.

MDC is commonly backed by **ThreadLocal** and does not automatically follow tasks executed on another executor thread. Child threads, inherited context, virtual threads, thread pools, and reactive pipelines must be understood according to the respective provider/framework; do not use a single-thread check to conclude propagation behavior across all threads.

For a non-existent key, tests should prefer **assertNull(MDC.get("requestId"))**. Do not over-constrain whether **getCopyOfContextMap()** returns `null` or an empty map, as that detail can depend on the adapter or state.

## 3. Three Levels of Testing

| Level | What to assert | Tools |
| --- | --- | --- |
| **Scope/state** | Accurate `put`/`get`/`restore`/`remove` | JUnit assertions on MDC |
| **Logging-event** | Event holds the right MDC at logging time, without reading stale/mutated state later | Logback appender capturing events |
| **Pipeline/end-to-end** | Text/JSON encoder, async queue, stdout/file/collector contain the right fields | Integration test with real logging config |

A test that only calls `MDC.get` can PASS even if the pattern is missing `%X{requestId}`. A test checking `ILoggingEvent` with the right MDC can PASS even if the JSON encoder drops the field or the collector loses it. Conversely, merely searching for the `requestId` string in the output can produce a false positive if the ID appears in the message text rather than in a structured MDC field.

Design tests around the contract: if every `ERROR` event is required to have `traceId`, assertions should inspect the fields of the **emitted event** and the serialized output, not just the method's MDC state.

## 4. Scope Lifecycle and Nested Restore

A typical SLF4J helper:

~~~java
import org.slf4j.MDC;

void withRequestId(String id, Runnable work) {
    String previous = MDC.get("requestId");
    try {
        MDC.put("requestId", id);
        work.run();
    } finally {
        if (previous == null) {
            MDC.remove("requestId");
        } else {
            MDC.put("requestId", previous);
        }
    }
}
~~~

This snippet is **integration code** that requires the SLF4J dependency and an application class. It owns only `requestId`, so it does not delete `traceId`/`jobId` set by other components. Tests should cover:

1. No ID before the scope; `req-A` visible inside the scope; key disappears after the scope.
2. `outer` exists before the scope; inner scope sees `inner`; after the inner scope, `outer` is restored.
3. Handler throws `RuntimeException`; `finally` still restores `previous`.
4. Caller has `traceId`; the scope does not lose `traceId`.
5. Calling the helper multiple times sequentially does not retain the previous call's ID.
6. If the key did not exist beforehand, use `remove` instead of writing the literal string `"null"`.

**MDC.putCloseable** is convenient when a scope only needs to remove a key on close. However, for nested scopes that overwrite the same key, do not assume `close` automatically restores the old value; saving `previous` and restoring it as shown above is easy to test and verify.

**MDC.clear()** may be appropriate at a boundary that owns the entire map, but it is inappropriate inside a library that only owns a single key, because it could wipe out `traceId` or baggage managed by the caller.

## 5. Standalone Java 17 Example: Context Scope Principle

The first example uses only JDK 17 and simulates context with `ThreadLocal`. **It is not SLF4J MDC**, and it does not replace testing the real provider; it helps illustrate nested restore and `finally`.

Create **MdcScopeConceptDemo.java**:

~~~java
public class MdcScopeConceptDemo {
    private static final ThreadLocal<String> REQUEST = new ThreadLocal<>();

    private static void withId(String id, Runnable work) {
        String previous = REQUEST.get();
        try {
            REQUEST.set(id);
            work.run();
        } finally {
            if (previous == null) {
                REQUEST.remove();
            } else {
                REQUEST.set(previous);
            }
        }
    }

    private static String current() {
        String value = REQUEST.get();
        return value == null ? "<absent>" : value;
    }

    public static void main(String[] args) {
        System.out.println("before=" + current());
        withId("req-outer", () -> {
            System.out.println("outer=" + current());
            withId("req-inner", () ->
                    System.out.println("inner=" + current()));
            System.out.println("restored=" + current());
        });
        System.out.println("after=" + current());
    }
}
~~~

Run:

~~~bash
javac MdcScopeConceptDemo.java
java MdcScopeConceptDemo
~~~

Deterministic stdout:

~~~text
before=<absent>
outer=req-outer
inner=req-inner
restored=req-outer
after=<absent>
~~~

The output shows that a nested scope can temporarily replace the context without erasing the previous value. In production, you must use the proper MDC adapter and propagation framework; this pure-JDK example only explains the principle.

## 6. Setting Up Maven, JUnit 5, SLF4J, and Logback

The next test suite runs on **Java 17 + JUnit 5 + SLF4J 2.0 + Logback 1.5**. The versions below are **compatible illustrative examples**, not necessarily the latest releases. Projects using Spring Boot or another BOM should choose dependencies matching their runtime to avoid provider conflicts.

Structure:

~~~text
mdc-test-demo/
  pom.xml
  src/test/java/example/MdcContextTest.java
~~~

File **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>mdc-test-demo</artifactId>
  <version>1.0-SNAPSHOT</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.slf4j</groupId>
      <artifactId>slf4j-api</artifactId>
      <version>2.0.13</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>ch.qos.logback</groupId>
      <artifactId>logback-classic</artifactId>
      <version>1.5.6</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>5.10.2</version>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.2.5</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Because the tests only use the logging API in test scope, Logback can be a test dependency. A production application can provide its own runtime provider according to its requirements.

**Note:** Logback-specific tests use **ch.qos.logback.classic.Logger** and `ILoggingEvent`. If you switch the backend to Log4j 2, you need to switch the capture mechanism or test provider-neutral output; do not force-cast an implementation that is not on the classpath.

## 7. Pitfall When Testing ListAppender: Lazy MDC Snapshot

A common test pattern creates a Logback `ListAppender` and keeps references to `ILoggingEvent`, but only calls **getMDCPropertyMap()** after the application has already modified or cleared MDC.

The problem: some event data can be **prepared or retrieved lazily** by the implementation. If you read MDC too late, the test can become timing-dependent or read a state that does not match when the logger call occurred.

Solution when writing a test appender:

1. Immediately inside `append`, call **event.prepareForDeferredProcessing()**.
2. Read **event.getMDCPropertyMap()** while the event is being processed.
3. Make an **immutable copy** of the key/value pairs to verify.
4. Capture the formatted message, level, and relevant fields.
5. Only after that allow application code to modify or clear MDC.

Do not mutate the event or the adapter's map directly. For async logging, the requirement is to preserve the **producer thread's context at event creation time**, not the background appender worker's MDC.

## 8. JUnit 5: Complete Test Suite on Logback

Create **src/test/java/example/MdcContextTest.java**:

~~~java
package example;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.AppenderBase;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import static org.junit.jupiter.api.Assertions.*;

class MdcContextTest {
    record Snapshot(String message, Level level,
                    Map<String, String> mdc) {}

    static final class CaptureAppender extends AppenderBase<ILoggingEvent> {
        final List<Snapshot> events = new CopyOnWriteArrayList<>();

        @Override
        protected void append(ILoggingEvent event) {
            event.prepareForDeferredProcessing();
            Map<String, String> values = event.getMDCPropertyMap();
            Map<String, String> copy =
                    values == null ? Map.of() : Map.copyOf(values);
            events.add(new Snapshot(
                    event.getFormattedMessage(),
                    event.getLevel(), copy));
        }
    }

    private Logger logger;
    private CaptureAppender appender;

    @BeforeEach
    void setUp() {
        MDC.clear();
        logger = (Logger) LoggerFactory.getLogger(
                "example.mdc." + UUID.randomUUID());
        logger.setLevel(Level.INFO);
        logger.setAdditive(false);

        appender = new CaptureAppender();
        appender.setContext(logger.getLoggerContext());
        appender.start();
        logger.addAppender(appender);
    }

    @AfterEach
    void tearDown() {
        logger.detachAppender(appender);
        appender.stop();
        logger.setLevel(null);
        logger.setAdditive(true);
        MDC.clear();
    }

    private static void withRequestId(String id, Runnable work) {
        String previous = MDC.get("requestId");
        try {
            MDC.put("requestId", id);
            work.run();
        } finally {
            if (previous == null) {
                MDC.remove("requestId");
            } else {
                MDC.put("requestId", previous);
            }
        }
    }

    private static Runnable withCapturedMdc(Runnable work) {
        Map<String, String> captured = MDC.getCopyOfContextMap();
        Map<String, String> snapshot =
                captured == null ? null : Map.copyOf(captured);

        return () -> {
            Map<String, String> previous =
                    MDC.getCopyOfContextMap();
            try {
                if (snapshot == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(snapshot);
                }
                work.run();
            } finally {
                if (previous == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(previous);
                }
            }
        };
    }

    @Test
    void eventCapturesMdcAtLoggingTime() {
        MDC.put("requestId", "req-42");
        logger.info("first");

        MDC.put("requestId", "req-99");
        logger.warn("second");

        MDC.remove("requestId");
        logger.info("third");

        assertEquals(3, appender.events.size());
        assertEquals("req-42",
                appender.events.get(0).mdc().get("requestId"));
        assertEquals("req-99",
                appender.events.get(1).mdc().get("requestId"));
        assertFalse(appender.events.get(2).mdc()
                .containsKey("requestId"));
        assertEquals(Level.WARN, appender.events.get(1).level());
        assertEquals("third", appender.events.get(2).message());
    }

    @Test
    void nestedScopeRestoresContextEvenOnFailure() {
        MDC.put("requestId", "outer");
        MDC.put("traceId", "trace-7");

        withRequestId("inner", () -> {
            assertEquals("inner", MDC.get("requestId"));
            logger.info("nested");
        });

        assertEquals("outer", MDC.get("requestId"));
        assertEquals("trace-7", MDC.get("traceId"));
        assertEquals("inner",
                appender.events.get(0).mdc().get("requestId"));

        MDC.remove("requestId");
        assertThrows(IllegalStateException.class, () ->
                withRequestId("temporary", () -> {
                    throw new IllegalStateException("expected");
                }));

        assertNull(MDC.get("requestId"));
        assertEquals("trace-7", MDC.get("traceId"));
    }

    @Test
    void executorTaskDoesNotLeakMdc() throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            pool.submit(MDC::clear).get();
            MDC.put("requestId", "req-worker");

            assertNull(pool.submit(
                    () -> MDC.get("requestId")).get());

            pool.submit(withCapturedMdc(
                    () -> logger.info("worker-event"))).get();

            assertEquals("req-worker",
                    appender.events.get(0).mdc().get("requestId"));
            assertNull(pool.submit(
                    () -> MDC.get("requestId")).get());
            assertEquals("req-worker", MDC.get("requestId"));
        } finally {
            pool.shutdownNow();
        }
    }

    @Test
    void exceptionRestoresWorkersPreviousContext() throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            pool.submit(() -> MDC.put("requestId", "worker-old"))
                    .get();
            MDC.put("requestId", "caller-new");

            assertThrows(ExecutionException.class, () ->
                    pool.submit(withCapturedMdc(() -> {
                        assertEquals("caller-new",
                                MDC.get("requestId"));
                        throw new IllegalArgumentException("failure");
                    })).get());

            assertEquals("worker-old", pool.submit(
                    () -> MDC.get("requestId")).get());
            assertEquals("caller-new", MDC.get("requestId"));
        } finally {
            pool.submit(MDC::clear).get();
            pool.shutdownNow();
        }
    }
}
~~~

Run from the directory containing `pom.xml`:

~~~bash
mvn test
~~~

**Expected result:** Maven exits with code 0, and **4 test methods** complete with no assertion failures. The exact summary/stdout lines printed by Maven/Surefire may vary by environment; do not assume a fixed console string for this command.

### What Each Test Verifies

- **eventCapturesMdcAtLoggingTime:** three log events have `requestId` values `req-42`, `req-99`, and absent, respectively. Assertions rely on the **event snapshot**, not on the current MDC after the lines have been logged.
- **nestedScopeRestoresContextEvenOnFailure:** the inner scope restores `outer`, preserves `traceId` (`trace-7`), and cleans up `requestId` after an exception.
- **executorTaskDoesNotLeakMdc:** the worker initially does not automatically inherit the caller's `requestId`; the wrapper propagates it while the task runs; afterward, the worker does not retain `requestId`.
- **exceptionRestoresWorkersPreviousContext:** the worker has `worker-old`; the task receives `caller-new` and throws an error; `finally` restores `worker-old`, while the caller still keeps `caller-new`.

The test appender uses **prepareForDeferredProcessing** and **Map.copyOf** to freeze data; `CopyOnWriteArrayList` safely collects events across multiple threads. The logger is created with a unique name and **setAdditive(false)** so events do not propagate to root appenders; the fixture detaches and stops it after each test.

**Limitations:** these are JUnit tests with Logback; they do not test Kafka/HTTP, do not prove that the final JSON encoder outputs MDC, and do not guarantee that every logging backend has the exact same semantics as Logback.

## 9. Test Isolation and Shared Logging State

There are two separate state areas:

**MDC context** is typically thread-scoped; it must be cleaned up in `try`/`finally` or after each task. **Logger configuration/appenders** belong to the logger context and can be shared across multiple tests.

How to reduce flakiness:

- Use a dedicated logger per test and an appender with proper start/stop lifecycle management.
- Avoid changing the root logger level or removing global appenders, as other tests may be affected.
- Clear MDC on the test thread before and after each test case.
- For worker threads, perform cleanup **inside the task**; do not assume calling `MDC.clear()` on the test thread cleans up workers.
- Use a test-owned `ExecutorService` and shut it down in `finally`.
- When running tests in parallel, do not share a single static `ListAppender` without filtering or synchronization.
- If testing MDC on async events, capture data at the right moment and wait for the consumer to finish using a deterministic mechanism.

If a test passes in isolation but fails when running the full suite, check shared logger/ThreadLocal/provider setup before increasing timeouts or adding `Thread.sleep`.

## 10. Propagation Across ExecutorService

For asynchronous tasks, you must **capture on the caller** and then **activate on the worker**:

~~~text
Caller: MDC(requestId=req-A)
    |
    | getCopyOfContextMap()
    v
Runnable + captured snapshot
    |
    v
Worker:
    previous = worker MDC snapshot
    setContextMap(captured)
    run task
    finally restore previous or clear
    |
    v
Worker receives next task
~~~

Tests should verify:

1. The snapshot is taken at submission time, before the caller changes its context.
2. The worker sees the ID from the snapshot, not a leftover ID.
3. When the task finishes normally, the worker returns to its previous state.
4. When the task throws an exception, `finally` still restores the previous state.
5. The caller keeps its original MDC; the worker does not mutate the caller's map directly.
6. Task B reusing the same worker with a different ID does not get mixed up.
7. When the caller context lacks a key, the wrapper does not fabricate an old value.

**Do not use InheritableThreadLocal as the default propagation strategy for thread pools.** Worker threads may be pre-created or reused across many tasks.

Frameworks such as Spring `TaskDecorator`, Micrometer Context Propagation, or OpenTelemetry provide built-in mechanisms; use the framework's mechanism and test its semantics rather than stacking multiple custom wrappers.

## 11. CompletableFuture and Reactive Callbacks

Operations like `supplyAsync`, `thenApplyAsync`, and `CompletableFuture` callbacks may execute on different threads. Therefore:

- Specify a **test-owned executor** when you need deterministic control.
- Capture context at the submission boundary or attach a framework-provided decorator.
- Test a callback after the caller has changed MDC: the callback still uses the context of the submitted task.
- Test `exceptionally`/`handle`/`whenComplete` branches, not just successful `thenApply`.
- Test propagation across retry/cancellation with explicit synchronization.
- Do not assert a global log order across independent futures unless a happens-before relationship exists.

In reactive frameworks like Reactor, **Reactor Context** is not identical to `ThreadLocal`. An MDC bridge must be built on the available instrumentation/context-propagation operators; a `ThreadLocal`-style servlet test is not enough to prove a reactive pipeline does not leak.

## 12. Thread Pool Reuse and Context Leak Checks

A very valuable regression scenario:

~~~text
worker-1: request A -> log A -> cleanup
worker-1: request B -> log B -> cleanup
worker-1: task C (no requestId) -> log C
~~~

Assertions:

- Event A has `req-A`, event B has `req-B`.
- Event C **has no `requestId`**, if the contract does not require one.
- After each task, the worker retains no stale values.
- The caller outside the executor does not have its context altered.
- If task A throws an exception, task B still starts clean.

Using a **single-thread executor** ensures A and B run on the same worker. Use `Future.get()` to confirm completion before asserting; **Thread.sleep is not reliable synchronization**. When testing concurrency with multiple threads, use `CountDownLatch`/`CyclicBarrier` and deadlines to force overlap without relying on scheduler timing.

Do not "fix" a leaking test by manually adding `MDC.clear()` before task B when production code has no corresponding step. The test must prove that the application's own scope-management layer performs cleanup.

## 13. Concurrency Testing

With two tasks A and B running concurrently:

~~~text
Thread-1: event=A1 requestId=req-A
Thread-2: event=B1 requestId=req-B
Thread-1: event=A2 requestId=req-A
Thread-2: event=B2 requestId=req-B
~~~

Do not assert a single global log line order unless ordering is guaranteed. Instead:

- Assign distinct IDs to each task and use a stable correlation key.
- Capture snapshots with a thread-safe appender.
- Filter/group events by ID and verify every event of A carries `req-A`.
- Verify no event mixes keys/IDs from A and B out of scope.
- Use a latch/barrier so tasks genuinely overlap; do not use arbitrary sleeps.
- Set deadlines and clean up the executor when the test finishes.

A subtle bug is when two futures share the same **mutable Map** as a snapshot. If the caller continues modifying the map after submission, the task may observe the mutated state. Use an immutable copy snapshot before submission, and test the case where the caller changes the ID immediately after enqueuing.

## 14. Exceptions, Timeouts, Cancellation, and Retries

MDC cleanup must be guaranteed on every exit path:

| Scenario | Recommended assertion |
| --- | --- |
| Normal return | Context is restored |
| RuntimeException | `finally` runs, previous value is preserved |
| Wrapped checked exception | Restoration still occurs |
| `Future.get` timeout | Only the caller times out; the task may still be running |
| Cancellation before execution | Snapshot is not retained beyond the required lifecycle |
| Cancellation during execution | If the task actually terminates, `finally` cleans up |
| Retry on another executor | Each attempt has the right ID and does not mix tasks |
| DLQ/replay | `messageId` is preserved according to contract |

**Future.cancel(true) does not guarantee immediate task termination** if the work does not cooperate with interruption. When testing timeouts, do not immediately assert an empty worker MDC as soon as the caller receives `TimeoutException`; wait for the task to finish and `finally` to run.

During retries, **messageId** may stay the same while `attemptNo` changes. Never use a process-wide static field to store the ID of a single message.

## 15. Testing in HTTP Filters and Interceptors

In a servlet-based Spring MVC or Java web application:

1. Request A attaches a validated `requestId`, and controller/service logs carry ID A.
2. Request B on a reused thread does not carry ID A.
3. Invalid headers containing newlines or exceeding length limits are rejected or replaced with a new ID per policy.
4. Controller throws an exception; the filter's `finally` block still restores context.
5. Servlet async or thread-switching callbacks have compatible propagation.
6. The tracing SDK generates a real `traceId`, and the MDC log field matches the trace context.
7. The response correlation header and log ID can be cross-checked if required by contract.

You can use MockMvc or HTTP integration tests, but **asserting response headers does not replace asserting log event MDC**. When a framework provides auto-propagation, test with the actual runtime configuration.

With WebFlux/Reactor, do not assume thread-bound MDC across all operators; test the actual Reactor Context and context-propagation bridge.

## 16. Testing in Message Consumers

In message-driven services, `messageId`/trace context usually comes from headers/envelopes:

~~~text
Broker receive
   |
   v
Validate envelope and IDs
   |
   v
Activate MDC scope
   |
   v
Handler -> log events -> business commit
   |
   v
ACK / retry / DLQ
   |
   v
Restore MDC
~~~

Test according to contract:

- Message A has the right ID in the handler's log events.
- Message B running afterward on the same worker does not receive A's ID.
- When the handler fails and retries, context is still cleaned up.
- On redelivery, the logical `messageId` stays the same while `attemptNo` differs per policy.
- Child messages carry allowed correlation/causation context.
- Deserialization errors occurring before a payload exists still log broker metadata safely without dumping raw secrets.
- Do not equate ACK/offset commit with verifying correct MDC; inspect actual events or output.

For message batches or fan-out, test IDs per individual message—do not reuse a single MDC map for the entire batch if each record requires its own correlation.

## 17. Testing JSON and Text Encoders

Example Logback text pattern:

~~~text
%d{ISO8601} %-5level request=%X{requestId} trace=%X{traceId} %logger - %msg%n
~~~

If the pattern only has `%msg`, MDC can still exist in the event without appearing in the output. Therefore, pipeline tests should:

1. Load **logback-test.xml** or the corresponding production encoder configuration.
2. Emit events with real MDC values.
3. Flush/stop the appender or wait for completion using a supported mechanism.
4. Read the text/JSON output from the test sink.
5. Parse specific fields and assert `requestId`, `traceId`, and `eventCode` have the right types and values.
6. Test that fields are absent when out of scope.
7. Verify that passwords, tokens, raw `Authorization` headers, and disallowed PII are not emitted.

Expected JSON example:

~~~json
{
  "level": "ERROR",
  "event": "order_failed",
  "requestId": "req-42",
  "traceId": "trace-7",
  "errorCode": "INVENTORY_TIMEOUT"
}
~~~

This is an **illustrative schema**, not Logback's default output. A JSON serializer must handle escaping; **correct encoding does not automatically mean redaction**.

Do not just grep for a large substring: the ID might appear in the message text while the structured MDC field is missing. Parse the JSON and assert against the collector's actual schema.

## 18. AsyncAppender, Snapshots, and Backpressure

With async logging, an event is created on the request thread but formatted/written later by a worker:

~~~text
caller: MDC=req-A -> logger.info -> MDC.clear
                         |
                         v
                    async queue
                         |
                         v
                   log writer
~~~

The emitted event must carry `req-A` **at the time the logger was called**, rather than reading the writer's empty context. Verify:

- Log an event with `req-A`, immediately switch to `req-B` or clear, then verify the event output still has `req-A`.
- Ensure the async appender captures or prepares required fields before queuing.
- Wait for the queue to drain/flush using a proper mechanism, not a fixed `Thread.sleep`.
- Measure the **backpressure** policy when the queue is full: block, drop, or discard depending on configuration.
- Test shutdown flush and log-drop metrics under high load.
- Do not assume async logging retains every `ERROR` if the provider is configured to discard or if the process is killed.

**A ListAppender storing raw ILoggingEvent references can produce misleading tests** if it does not prepare and snapshot MDC inside `append`. The JUnit suite in section 8 captures data immediately to reduce that risk.

## 19. Common Testing Anti-Patterns

| Anti-pattern | Why it is insufficient | Better alternative |
| --- | --- | --- |
| Only asserting `MDC.get` after `put` | Does not verify whether the logger wrote the field | Inspect the event MDC snapshot |
| Reading `event.getMDCPropertyMap` too late | May hit lazy preparation/timing issues | Call `prepareForDeferredProcessing` inside `append` |
| Only clearing MDC on the test thread | Workers have their own context | Clean up inside tasks and test worker reuse |
| Using shared root logger/appenders | Shared state causes test interference | Dedicated logger and proper teardown |
| Testing concurrency with `sleep` | Prone to flakiness | Latches, barriers, `Future.get` |
| Asserting total ordering of parallel logs | Scheduler does not guarantee order | Group events by correlation ID |
| Using `InheritableThreadLocal` with thread pools | Does not bind context per task | Capture/activate/restore |
| Assuming `putCloseable` restores nested old values | It may only remove the key | Save `previous`, restore in `finally` |
| Testing `traceId` with a fake string | Does not prove distributed tracing | Test inject/extract and SDK context |
| Enabling `INFO`/`ERROR` while testing `DEBUG` events | Events may be filtered out | Configure levels explicitly |
| Checking console text only | Encoder may drop fields; sampling/drops | Event tests + output integration tests |
| Putting real tokens/payloads into MDC for tests | May leak sensitive data in CI logs | Use dummy data and allowlists |

## 20. Checklist for CI and Production

| Item | Criterion |
| --- | --- |
| MDC state | `put`/`get`/`remove` and nested restore work accurately |
| Cleanup | `try`/`finally` guarantees cleanup on success, exception, and cancellation |
| Context ownership | Does not delete keys owned by the caller or framework |
| Event capture | Tests capture MDC at logging time |
| Provider | Test backend and version match runtime |
| Thread pool | No context leaks between task A and task B |
| Propagation | `Executor`/`CompletableFuture` use appropriate scope/decorators |
| Concurrency | Overlap tests are deterministic without unfounded ordering assertions |
| HTTP/message boundaries | IDs are created and restored per request/delivery |
| Trace correlation | Real `traceId`, propagated via headers/SDK where needed |
| Encoder | JSON/text outputs fields accurately and omits them out of scope |
| Async | Snapshot, flush, and queue overflow policies are tested |
| Test fixture | Appender detached/stopped; executor shut down; state cleaned up |
| Privacy | IDs validated; no secrets, PII, or log forging exposed |
| Observability | Able to distinguish missing MDC, missing events, and collector drops |

## 21. How to Investigate Failing Tests

If an event is missing `requestId`:

1. Check whether `MDC.put` occurs **before the logger call**.
2. Check whether the logger level/filter actually emits the event.
3. Check whether the test appender has been started and attached to the right logger.
4. Check whether the MDC snapshot was captured before the caller cleared it.
5. If a callback/worker runs on another thread, check context capture and activation.
6. Check whether the SLF4J/Logback provider is bound to the right dependencies.
7. If the event snapshot is correct but JSON lacks the ID, check the encoder schema.
8. If logs are missing in production, check async drops, collector parsing, sampling, and retention.

If request B carries A's ID, inspect worker cleanup and run a single-thread executor test to reproduce deterministically. Do not "fix" it by clearing MDC only in the test when production lacks that cleanup.

**Conclusion:** reliable MDC context testing must prove **accurate data in the log event, scope/exception cleanup, isolation across worker threads, propagation at async boundaries, and encoder/collector output**. Use JUnit 5 with a snapshot-capturing Logback appender for deterministic assertions, and use integration tests to verify the entire pipeline against a realistic environment.
