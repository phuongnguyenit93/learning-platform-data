# Testing context propagation in Spring Boot

A Spring Boot request has a valid trace context, yet when the service offloads work to an executor or calls downstream HTTP, the subsequent span gets a new trace ID. Worker logs may lack a trace ID, or worse, the next task on the same thread pool carries the previous task's trace ID.

These bugs rarely fail business unit tests. They surface at **execution boundaries**: a different thread, a reused thread pool, an HTTP client/server, a message consumer, or a Reactor scheduler. Therefore, context propagation must be tested independently to prove context is captured, propagated, restored, and cleaned up in the right places.

This lesson belongs to the **Context propagation** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module teaches how to set up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; covering context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production. This lesson focuses on unit, integration, and end-to-end testing strategies for context propagation.

## Learning objectives

After this lesson, you will be able to:

1. Identify boundaries that need testing: thread, executor, HTTP, messaging, and Reactor.
2. Distinguish testing current context, parent-child relationships, trace headers, log correlation, and export.
3. Use `TestObservationRegistry` to verify observation lifecycles.
4. Test executors to prove context is captured/restored and does not leak to the next task.
5. Verify HTTP client injection and server extraction of trace context using B3 or W3C.
6. Test `CompletableFuture`, `@Async`, and Reactor at the time callbacks/subscriptions execute.
7. Design tests for success, exception, cancellation, rejection, timeout, and thread reuse.
8. Separate propagation bugs from sampling, reporter, exporter, collector, and backend issues.
9. Write deterministic assertions that do not depend on random trace IDs.
10. Combine metrics, logs, and traces to catch context leakage and cardinality regressions.

## 1. What must propagation tests prove?

A test that only checks a task completes or an HTTP response is 200 **does not prove context propagated**. Before writing tests, identify the invariants that must hold at each boundary:

- **Before submit:** the request thread holds the expected active trace/span.
- **When the worker starts:** the worker sees the context of that exact submission.
- **Inside the task:** new spans have the expected trace ID and appropriate parent relationship.
- **After the task:** the scope is closed; the worker does not retain the used context.
- **Outbound HTTP:** the client injects the right header format.
- **Downstream:** the server extracts context and creates a linked span.
- **Logs:** trace ID/span ID at log time reflect the active scope.
- **Export:** spans are sent when sampler and exporter are configured to keep data.

```text
Request thread: trace T / span A
       |
       +-- submit executor task
       |      worker restores context A
       |      task span B belongs to trace T
       |
       +-- HTTP client call
              outbound header identifies T / span B
                       |
                       v
                downstream server
                  extracts T / parent B
                  creates span C
```

Not every test needs to check every invariant. Unit tests focus on a single boundary; integration tests verify Spring wiring; end-to-end tests verify traces across multiple processes.

### 1.1. Distinguishing propagation from export

Propagation carries **trace context** across an execution boundary so the next span can link properly. Export delivers finished spans to the collector/backend.

| Observation | Could be a propagation bug? | Could be an export bug? |
|---|---:|---:|
| Worker has no active trace context | Yes | Not necessarily |
| Downstream creates a new trace ID | Yes | Not necessarily |
| Logs have trace ID yet Zipkin lacks span | Not necessarily | Yes |
| Span has right parent in test yet missing in backend | No | Yes |
| Task B carries Task A's trace ID on same worker | Yes, usually cleanup/restore bug | Not necessarily |

Do not tweak sampling or the Zipkin endpoint when context on the worker is already wrong. Conversely, do not rewrite `TaskDecorator` when context is right yet the reporter fails to send spans.

## 2. Choosing the right test layer

| Test layer | Goal | Common tools | Should not depend on |
|---|---|---|---|
| Unit test | Capture/restore, scope cleanup, observation creation logic | JUnit, single-thread executor, Micrometer Context Propagation | Network/backend |
| Observation test | Lifecycle and handlers observing events/errors | `TestObservationRegistry`, Micrometer assertion helpers | Zipkin UI |
| Spring integration | Bean wiring, `TaskDecorator`, auto-configuration, client instrumentation | `SpringBootTest`, `TestConfiguration`, `MockMvc` | Public backend |
| HTTP boundary | Header inject/extract and trace ID continuity | Mock HTTP server, WireMock or MockWebServer | Stored export |
| Async/reactive | Context at callback/signal time | `CompletableFuture`, controlled executor, Reactor `StepVerifier` | Assuming callback runs on calling thread |
| End-to-end | Trace across multiple services and pipeline | Testcontainers or integration environment | Fixed IDs or absolute span ordering |

Lower-layer tests are usually faster and more deterministic; higher-layer tests verify real wiring but require environment management.

## 3. Testing observation lifecycle

Micrometer provides test support for Observation, typically via the `micrometer-observation-test` artifact. `TestObservationRegistry` records observations and lifecycle events for assertions in unit tests. Dependency versions must match your project's Spring Boot/Micrometer BOM.

```groovy
dependencies {
    testImplementation 'io.micrometer:micrometer-observation-test'
}
```

Example creating a dedicated test registry:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.tck.TestObservationRegistry;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class PaymentObservationTest {

    @Test
    void recordsObservationAroundOperation() {
        TestObservationRegistry registry =
                TestObservationRegistry.create();

        String result = Observation.createNotStarted(
                        "payment.authorize", registry)
                .contextualName("authorize payment")
                .observe(() -> "approved");

        assertEquals("approved", result);
        // Use the assertion API / TestObservationRegistryAssert
        // from your Micrometer version to verify lifecycle, name, and tags.
    }
}
```

Asserting the callback return value only proves business code ran. In real tests, use your Micrometer version's assertion API or a test handler to verify start/stop/error and context. `TestObservationRegistry` does not fully simulate a Brave/OpenTelemetry tracer; verifying trace ID/span ID requires a test tracer or testing the actual boundary.

### 3.1. Testing the error branch

```java
@Test
void operationFailureIsPropagated() {
    TestObservationRegistry registry =
            TestObservationRegistry.create();

    IllegalStateException thrown = assertThrows(
            IllegalStateException.class,
            () -> Observation.createNotStarted(
                            "payment.authorize", registry)
                    .observe(() -> {
                        throw new IllegalStateException("boom");
                    }));

    assertEquals("boom", thrown.getMessage());
    // Add assertions per your Micrometer version to confirm
    // observation stop and error context were recorded.
}
```

The goal is confirming the exception propagates properly and the lifecycle ends. Do not infer from this test that the backend received a span.

## 4. Testing capture/restore with a single-thread executor

A single-thread executor is useful because the same worker executes task A, task B, and task C. Scenario:

- Task A is submitted while context A is active.
- Task B is submitted while context B is active.
- Task C is submitted with no context.
- A sees A, B sees B, C sees null.
- No task sees the previous task's context.

### 4.1. Using ContextSnapshot

Micrometer Context Propagation provides `ContextSnapshot` to capture/restore contexts that have matching registered accessors.

```java
import io.micrometer.context.ContextSnapshot;
import io.micrometer.context.ContextSnapshotFactory;

import java.util.concurrent.Executor;

final class ContextAwareSubmitter {
    private final Executor delegate;
    private final ContextSnapshotFactory factory;

    ContextAwareSubmitter(
            Executor delegate, ContextSnapshotFactory factory) {
        this.delegate = delegate;
        this.factory = factory;
    }

    void execute(Runnable task) {
        ContextSnapshot snapshot = factory.captureAll();
        delegate.execute(snapshot.wrap(task));
    }
}
```

Each submission captures the active context. `snapshot.wrap(task)` restores context inside a scope while the worker runs and closes the scope after the callback. Verify builder APIs and accessor registration against your actual Micrometer version.

### 4.2. Thread reuse test pattern

```java
@Test
void doesNotLeakContextBetweenTasks() throws Exception {
    ExecutorService worker = Executors.newSingleThreadExecutor();
    try {
        // Pseudocode: submitUnderTrace must submit while source span/scope
        // is still active; currentTraceId reads from the real tracer.
        Future<String> a = submitUnderTrace(
                "trace-A", worker, this::currentTraceId);
        Future<String> b = submitUnderTrace(
                "trace-B", worker, this::currentTraceId);
        Future<String> c = submitWithoutTrace(
                worker, this::currentTraceId);

        assertEquals("trace-A", a.get(2, TimeUnit.SECONDS));
        assertEquals("trace-B", b.get(2, TimeUnit.SECONDS));
        assertNull(c.get(2, TimeUnit.SECONDS));
    } finally {
        worker.shutdownNow();
    }
}
```

This is pseudocode: the helper must open the span/scope on the test thread, submit while context is active, and then close the source scope. Do not use a custom ThreadLocal unrelated to the tracer and claim it proves trace propagation.

Use `Future.get` with a bounded timeout or `CountDownLatch` to synchronize. Never use `Thread.sleep` as a condition guessing the callback has run. Always shut down the executor in `finally`.

## 5. Testing Spring ContextPropagatingTaskDecorator

Spring Framework 6.1+ provides `ContextPropagatingTaskDecorator` to integrate Micrometer Context Propagation. Availability depends on the Spring Framework version bundled with Spring Boot.

```java
@Configuration(proxyBeanMethods = false)
class AsyncConfiguration {

    @Bean
    ThreadPoolTaskExecutor applicationTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("app-worker-");
        executor.setTaskDecorator(
                new ContextPropagatingTaskDecorator());
        executor.initialize();
        return executor;
    }
}
```

Tests must confirm:

- The executor bean with the right name/qualifier is injected by the application.
- `TaskDecorator` is attached before the executor accepts tasks.
- Code using `@Async("applicationTaskExecutor")` actually goes through the Spring proxy.
- No code branch bypasses it with a raw `Executor` or `new Thread`.
- The next task on the same worker does not see a failing task's context.
- Spring context shutdown does not leave workers running unexpectedly.

**Do not just assert the bean exists.** A service may use another executor; `@Async` may pick a default executor. Integration tests should inject the service from `ApplicationContext` and exercise the real call path.

`TaskDecorator` restores context; it does not decide which span to measure. If you want to measure receipt-sending duration, create an observation inside the worker callback so the lifecycle wraps actual work. If the task outlives the request, consider an independent consumer/trace with a span link instead of holding the parent request scope open for minutes.

## 6. Testing HTTP propagation

HTTP propagation has two parts: the client injects context into request headers and the server extracts headers to create a linked span. An HTTP 200 status does not prove either part works.

### 6.1. W3C and B3

W3C Trace Context:

```http
traceparent: 00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01
tracestate: vendor=value
```

B3 multi-header:

```http
X-B3-TraceId: 0af7651916cd43dd8448eb211c80319c
X-B3-SpanId: b7ad6b7169203331
X-B3-Sampled: 1
```

Applications can use W3C, B3 single, or B3 multi depending on bridge/propagator. Tests must verify the exact format configured for production.

### 6.2. Testing outbound with a mock HTTP server

A mock server such as MockWebServer or WireMock can receive requests and let the test inspect headers:

```java
// Pseudocode: mock server started on a dynamic port.
server.enqueue(new MockResponse()
        .setResponseCode(200)
        .setBody("approved"));

withActiveSpan("parent-span", () -> paymentClient.authorize());

RecordedRequest request =
        server.takeRequest(2, TimeUnit.SECONDS);
assertNotNull(request);

// W3C: parse traceparent.
// B3: read X-B3-TraceId and X-B3-SpanId.
// Compare trace ID against the created test context;
// do not hardcode random IDs.
```

Assertions should verify valid header format, matching source trace ID, appropriate outbound span ID, sampling flag matching test policy, and no secrets/baggage outside the allowlist.

### 6.3. Testing server extraction

Send an inbound request with a known `traceparent` or B3 header, let Spring server instrumentation create the server span, and verify:

- The server span has a trace ID equal to the inbound ID.
- The new span ID differs from the inbound parent ID.
- Parent relationship is accurate per instrumentation.
- Requests without headers are handled per root-trace policy.
- Malformed/invalid headers are not trusted outside trust policy.

In-process `MockMvc` does not fully simulate networks/proxies. To test two applications, use real server/client instances or a mock HTTP server at the boundary.

## 7. Testing @Async and CompletableFuture

`@Async` methods typically work through a Spring proxy. Calling an internal method from the same object can bypass the proxy.

```java
@Service
class ReceiptService {
    @Async("applicationTaskExecutor")
    public CompletableFuture<String> sendReceipt() {
        return CompletableFuture.completedFuture(
                currentTraceIdOrNull());
    }
}
```

Tests must inject `ReceiptService` from the Spring context, invoke via the injected bean, await with `get(timeout, unit)`, and compare the trace ID inside the callback against the source context. Do not instantiate the service directly with `new`.

With `CompletableFuture`:

```java
CompletableFuture
        .supplyAsync(this::loadPayment, contextAwareExecutor)
        .thenApplyAsync(this::mapResult, contextAwareExecutor);
```

Each async callback can use a different executor. Test `supplyAsync`, `thenApplyAsync`, `thenComposeAsync`, `handleAsync`, `whenCompleteAsync`, and external library callbacks. Non-async callbacks may run on the thread that completed the previous stage or on the caller depending on state; do not infer thread execution solely from method names.

## 8. Testing Reactor and WebFlux

In Reactor, `Context` is attached to the subscription; threads can change while the pipeline runs. Tests need to check context when signals are processed.

```java
StepVerifier.create(
        Mono.deferContextual(context ->
                Mono.just(context.get("request-key")))
            .contextWrite(context ->
                context.put("request-key", "request-A")))
    .expectNext("request-A")
    .verifyComplete();
```

This example only proves Reactor Context travels through the pipeline; it does not itself prove Micrometer/Brave trace context is linked properly. To test tracing, you need the appropriate integration and assertions on the current span where operators execute.

Test context across `contextWrite`, `publishOn`/`subscribeOn`, `flatMap`, `onErrorResume`, and cancellation. Avoid using `ThreadLocal` directly inside operators without an appropriate context bridge. Automatic context propagation or Reactor hooks have broad effects, so also test independent pipelines to catch context leakage between subscriptions.

## 9. Testing failure, cancellation, timeout, and rejection

| Case | What to verify |
|---|---|
| Callback succeeds | Context accurate; scope closed on completion |
| Callback throws exception | Error attached to span/observation; worker cleaned up |
| Future exceptional completion | Error callback has right context |
| Cancellation | Lifecycle ends per policy; scopes not held open indefinitely |
| Timeout | Do not assume task stopped unless cancelled |
| Executor rejection | Task does not run; no fake span created for unexecuted work |
| Shutdown | Queued/running tasks handled cleanly |
| Caller-runs policy | Task may run on submitter thread; caller context restored |
| Nested task | Child task receives right context from parent task |

With `CallerRunsPolicy`, a rejected task can run directly on the submitting thread. Tests must verify the decorator does not corrupt caller context after the callback finishes.

Do not assert that every submitted task exports a span if the executor can reject or the sampler can drop. Assert lifecycle/context per branch; export is a separate layer.

## 10. Testing exporter and backend

| Test assertion | What it proves | What it does not prove |
|---|---|---|
| Worker reads right trace ID | Context restored inside worker | Reporter sent span |
| Outbound has `traceparent` | Client injected W3C context | Server extracted or backend stored |
| Server span has same trace ID | Server extracted and created linked span | All downstream spans exported |
| Collector receives span | Export pipeline delivered data | UI/retention work properly |
| Zipkin UI displays trace | Trace ingested and searchable | Every request is sampled |
| Logs have trace ID | Log correlation worked at log time | Span exists in backend |

At the unit/integration layer you can use a test tracer/exporter to collect spans in memory. Exact APIs depend on Brave, OpenTelemetry SDK, and Micrometer versions; do not mix APIs from another implementation.

Keep E2E tests limited in number:

1. Start two services and a trace backend in an isolated environment.
2. Configure a deterministic sampler to keep test traces.
3. Send requests across services.
4. Capture the trace ID from context or test response correlation.
5. Query the backend by trace ID.
6. Assert client/server spans and appropriate parent relationships.
7. Check reporter/collector errors.
8. Clean up containers/processes.

Backends may ingest asynchronously; poll with a finite deadline instead of a long fixed sleep.

## 11. Stable assertions and avoiding flaky tests

**Assert:** trace ID continuity, parent/link semantics, header format, scope cleanup, absence of stale trace in subsequent tasks, error/cancellation lifecycles.

**Avoid asserting:**

- Hardcoded trace IDs.
- Unnecessary nanosecond/microsecond timestamp precision.
- Strict ordering of concurrently executing spans.
- Parent duration equaling the exact sum of child span durations.
- Every request appearing in the backend when sampling is not deterministic.
- Internal library attributes that can change across versions.
- Character-for-character log lines if the log pattern is not an application contract.

Use Future/latch/`StepVerifier` with bounded timeouts. Good tests explain why an assertion matters; for example, a contextless task C guards against context leakage across requests sharing a worker.

## 12. Verifying metrics and logs alongside context

### 12.1. Log correlation

A log-capture test can open a trace/span scope, log on the current thread, log inside a decorated executor, capture via an appender/test sink, and assert matching trace ID/span ID. Submit an extra contextless task on the same worker to confirm the old ID is gone.

Reading MDC directly checks only part of the path; if log format is an operational contract, add a log-capture test. Never use `System.out` as proof of MDC if the logging pattern does not print MDC.

### 12.2. Metrics do not attach trace ID as a tag

Metrics should use stable dimensions such as operation, route template, method, status group, or dependency. Do not attach trace ID as a metric label due to high cardinality. If the backend supports exemplars, test linking metric samples to traces via that mechanism.

Sampling can drop traces while metrics still reflect requests per design. Verify business metrics do not accidentally depend on whether the sampler kept a span.

## 13. Suggested test matrix

| Scenario | Unit | Spring integration | E2E |
|---|:---:|:---:|:---:|
| Observation start/stop/error | ✓ |  |  |
| `ContextSnapshot` capture/restore | ✓ | ✓ |  |
| Thread pool reuse / contextless task | ✓ | ✓ |  |
| `TaskDecorator` bean wiring |  | ✓ |  |
| `@Async` via Spring proxy |  | ✓ |  |
| `CompletableFuture` across executors | ✓ | ✓ |  |
| Reactor Context/scheduler | ✓ | ✓ |  |
| HTTP client header injection |  | ✓ | ✓ |
| HTTP server header extraction |  | ✓ | ✓ |
| B3/W3C between two services |  | ✓ | ✓ |
| Sampling policy | ✓ | ✓ | ✓ targeted |
| Reporter/collector/backend ingestion |  |  | ✓ |
| Log MDC correlation | ✓ | ✓ |  |
| Metrics still recorded when trace sampled out | ✓ | ✓ |  |
| Telemetry security/privacy |  | ✓ | ✓ per security test |

Pick representative combinations covering the executors, clients, messaging, and reactive paths your application actually uses; there is no need to multiply every combination into hundreds of tests.

## 14. Diagnostic workflow when tests fail

1. **Source thread:** is trace/span context active before submit?
2. **Executor:** does code use the decorated bean or a raw executor?
3. **Accessors:** does the context registry know how to capture/restore trace/MDC/custom ThreadLocals?
4. **Capture timing:** is a snapshot taken per submission or is an old snapshot reused?
5. **Worker:** is context inside the callback accurate? Does the next task carry an old ID?
6. **Lifecycle:** are scopes/spans closed on the executing thread? Did the callback finish before observation stopped?
7. **Network:** does the client inject headers, does the proxy preserve them, and does the server extract with the right propagator?
8. **Sampling/export:** if context is right yet the backend is empty, are the sampler, reporter, collector, retention, and query working?

| Finding | Action to take |
|---|---|
| Source lacks context | Check server instrumentation and scope before submit |
| Source has context, worker lacks it | Check executor, decorator, snapshot, accessors |
| Worker has trace, child gets new root ID | Check current span/parent creation, tracer bridge |
| Worker right, outbound header missing | Check HTTP client instrumentation/propagator |
| Header right, server has different trace | Check server extraction, gateway, format |
| Context/parent right, Zipkin empty | Check reporter, sampler, collector, backend |
| Task B sees trace A | Check cleanup/restore and worker reuse |
| Contextless task sees prior trace | Context leakage; check scope/`finally`/reset |

## 15. Anti-patterns when testing propagation

| Anti-pattern | Why weak/wrong | Alternative |
|---|---|---|
| Only asserting HTTP 200 | Proves nothing about trace context | Assert active trace and headers |
| Only checking logs contain `traceId` | May only pass a string without parent span | Check tracer context and span relationship |
| Testing only task A | Misses leakage | Single-thread executor, tasks B/C |
| Using `Thread.sleep` | Test depends on machine speed | Future/latch/`StepVerifier` |
| Hardcoding trace IDs | Brittle tests | Capture ID inside test |
| Bypassing Spring proxy in `@Async` test | Does not test wiring | Inject bean through context |
| Mocking executor to run inline | Creates no thread boundary | Test with real worker thread |
| Testing `ContextSnapshot` without accessors | Does not prove trace context | Assert real tracer integration |
| Using E2E backend for all tests | Slow, hard to diagnose | Focus on unit/integration |
| Setting 100% sampling in production | Cost/risk | Separate test sampler |
| Equating missing trace with propagation failure | Could be export/retention | Check context first, pipeline second |
| Ignoring cancellation/exceptions | Scopes might fail to clean up | Test all terminal paths |

## 16. Pre-merge checklist

1. Are thread/executor/HTTP/messaging/Reactor boundaries tested?
2. Does the source thread have active context before submit?
3. Are snapshots captured per submission rather than shared across requests?
4. Do callbacks see the right trace/span/tenant context?
5. Are scopes closed and workers restored even on errors/cancellation?
6. Do tasks A, B, and a contextless task run on the same worker with zero leakage?
7. Do observations/spans wrap actual work rather than just enqueue time?
8. Does the HTTP client inject and server extract B3/W3C properly?
9. Do Reactor/messaging use the appropriate propagation models?
10. Are `@Async` and real executors tested via Spring beans?
11. Is log correlation accurate without leaking into other tasks?
12. Do metrics avoid trace ID labels and avoid unintended sampling coupling?
13. Do tests separate context correctness from export?
14. Are headers/baggage/attributes free of tokens and non-allowlisted PII?
15. Do tests use deterministic executors/latches/Futures/`StepVerifier` with finite timeouts?
16. Are APIs compatible with Spring Boot, Spring Framework, Micrometer, and tracer versions?

## 17. Self-assessment questions

**Question 1.** An async method returns the right result yet the worker's trace ID is null. Did the propagation test pass?

**Hint:** No. Business correctness tests and context propagation tests are two separate contracts.

**Question 2.** Why is a single-thread executor useful for testing context leakage?

**Hint:** Tasks are guaranteed to reuse the same worker, making leftover ThreadLocal/MDC from a previous task easy to catch.

**Question 3.** Task A sees trace A and task B sees trace B. Is that enough to prove cleanup works?

**Hint:** Add a contextless task C and confirm C sees null.

**Question 4.** Outbound has the right `traceparent`. Does that prove downstream has a span in the same trace?

**Hint:** No. You must also check server extraction and downstream span context.

**Question 5.** Does `TestObservationRegistry` verify that Zipkin stored the span?

**Hint:** No. It supports testing Observation lifecycles; export/ingestion/backend require separate tests.

**Question 6.** Why shouldn't trace IDs be hardcoded in assertions?

**Hint:** IDs are typically random; capture the ID in the test, then parse and compare it.

**Question 7.** The worker sees the current span and outbound headers are right, yet the backend has no trace. What should you inspect?

**Hint:** Sampling, span end, reporter/exporter, collector, storage, retention, and query.

**Question 8.** Must an email-sending task running after the request returns a response always be a child span of that request?

**Hint:** No. For long-lived independent work, a consumer/root span with a link to the producer context may be more semantically accurate.

**Question 9.** Why is an inline mock executor insufficient for testing cross-thread propagation?

**Hint:** It creates no execution boundary; ThreadLocal remains on the calling thread.

**Question 10.** With 10% sampling, can you assert every test run produces a trace in Zipkin?

**Hint:** No. Use a dedicated deterministic sampler in tests that need to verify export.

## Conclusion

**Context propagation testing must prove context is accurate at every execution boundary and cleaned up properly once work finishes.** In Spring Boot, combine unit tests for `ContextSnapshot`/lifecycles, a single-thread executor to catch thread-reuse leakage, integration tests for `TaskDecorator`/`@Async`/HTTP clients, and a handful of cross-service E2E tests. Assert trace context and semantically accurate parent/link relationships, verify B3/W3C headers, error/cancellation paths, and log correlation, while keeping propagation failures distinct from sampling, reporter, exporter, and backend issues. A pipeline is only trustworthy when it not only delivers the right context to the current task, but also guarantees the next task never inherits stale context.
