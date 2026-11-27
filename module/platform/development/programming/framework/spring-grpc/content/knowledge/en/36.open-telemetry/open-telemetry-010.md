# Testing Propagation

## Lesson Objectives

In **SPRING_GRPC**, trace context must travel through the client, HTTP/2 metadata, server interceptors, services, worker executors, and downstream RPCs so that every piece of work in a request is linked into the same trace. Propagation configuration can look right when reading code yet still fail at runtime: the client fails to inject metadata, the server fails to extract it, async callbacks lose context, baggage is dropped, or another instrumentation layer creates duplicate spans.

This lesson focuses on **testing propagation**: verifying W3C Trace Context inject/extract, validating trace relationships between the gRPC client and server, preserving OpenTelemetry `Context` across executors and callbacks, testing baggage, sampling, and invalid inputs, as well as detecting context leaks and duplicate instrumentation.

After this lesson, you will be able to:

1. Design standalone propagator tests and gRPC integration tests.
2. Verify trace ID, span ID, parent-child relationships, and the sampled flag.
3. Test client/server instrumentation over in-process transport and real network transport.
4. Test OTel `Context` across executors, `CompletableFuture`, and async callbacks.
5. Test baggage allowlists, size limits, and untrusted inputs.
6. Test sampling, exporters, and behavior when traces are not recorded.
7. Detect duplicate spans, context leaks, and cross-request miscorrelation under concurrency.
8. Build end-to-end propagation tests without depending on a production dashboard.

> **Scope:** Examples use the OpenTelemetry Java API/SDK, gRPC Java, and Spring. The gRPC instrumentation package API depends on the instrumentation version in use. In-process examples test gRPC-layer interceptors/propagation, but do not replace testing TLS, ALPN, or HTTP/2 over real sockets.

## 1. Layers to Test

Propagation is not a single operation. A solid test strategy separates boundaries so you know where a failure occurs.

| Layer | What to Verify | Test Type |
| --- | --- | --- |
| Propagator | Trace context is injected/extracted per spec | Unit test with carrier map |
| Client instrumentation | Outbound RPC creates client span and metadata | gRPC client integration test |
| Server instrumentation | Inbound metadata is extracted and creates server span | gRPC server integration test |
| Parent-child | Client/server spans share trace and proper parent | In-process or socket test |
| Async boundary | Context stays intact on worker/callback threads | Executor/`CompletableFuture` test |
| Baggage | Only permitted keys/values are propagated | Propagator/security test |
| Sampling/export | Spans are recorded/exported per policy | SDK with in-memory exporter |
| Isolation | Concurrent requests never mix context | Concurrency test |
| Transport | TLS, HTTP/2, proxies preserve metadata | Network integration test |

Do not check only that `traceparent` appears in a map and conclude all gRPC propagation works. Likewise, do not merely glance at a dashboard for a trace while skipping verification of parent-child links and async task context.

## 2. Preparing the OpenTelemetry SDK for Tests

Use a dedicated SDK instance in tests to collect spans directly in memory. The OpenTelemetry Java testing artifact provides `InMemorySpanExporter`; keep its version aligned with your project's OTel SDK and instrumentation.

Example fixture:

```java
InMemorySpanExporter spanExporter =
        InMemorySpanExporter.create();

SdkTracerProvider tracerProvider =
        SdkTracerProvider.builder()
                .setSampler(Sampler.alwaysOn())
                .addSpanProcessor(
                        SimpleSpanProcessor.create(spanExporter))
                .build();

OpenTelemetrySdk openTelemetry =
        OpenTelemetrySdk.builder()
                .setTracerProvider(tracerProvider)
                .setPropagators(
                        ContextPropagators.create(
                                W3CTraceContextPropagator.getInstance()))
                .build();

Tracer tracer =
        openTelemetry.getTracer("spring-grpc-propagation-test");
```

In real fixtures, close `tracerProvider` after tests and reset the exporter between tests. Do not call `GlobalOpenTelemetry.set()` repeatedly inside the same JVM if tests run in parallel; global state introduces order-dependent tests. Prefer injecting the `OpenTelemetry` instance into the instrumentation and components under test.

`Sampler.alwaysOn()` ensures test spans are deterministically recorded. When testing sampling, build a separate SDK fixture with the target sampler rather than mutating a global sampler between tests.

### 2.1. Test Dependencies

Projects typically need:

- OpenTelemetry API and SDK at the same version.
- OpenTelemetry SDK testing in test scope for `InMemorySpanExporter`.
- gRPC instrumentation compatible with the gRPC Java version in use.
- gRPC in-process transport for service/interceptor tests where appropriate.
- Spring Boot test support if application context startup is required.

Use the OpenTelemetry BOM or version alignment chosen by the project. Never mix arbitrary alpha instrumentation, SDK, and API versions; binary compatibility errors can surface at test time or startup.

## 3. Testing W3C Trace Context Inject/Extract

W3C Trace Context transfers trace identity through standard headers such as `traceparent` and `tracestate`. Propagator unit tests should verify:

- A `Context` with a valid `SpanContext` is injected into `traceparent`.
- Trace ID and span ID remain intact after extraction.
- The sampled flag is preserved accurately.
- `tracestate` propagates according to propagator semantics.
- Malformed headers do not crash the application or get trusted as valid context.

Example round-trip via a carrier map:

```java
String traceId = "4bf92f3577b34da6a3ce929d0e0e4736";
String spanId = "00f067aa0ba902b7";

SpanContext remoteParent =
        SpanContext.createFromRemoteParent(
                traceId,
                spanId,
                TraceFlags.getSampled(),
                TraceState.getDefault());

Context parentContext =
        Context.root().with(Span.wrap(remoteParent));

Map<String, String> carrier = new HashMap<>();

TextMapPropagator propagator =
        W3CTraceContextPropagator.getInstance();

propagator.inject(
        parentContext,
        carrier,
        (map, key, value) -> map.put(key, value));

Context extracted =
        propagator.extract(
                Context.root(),
                carrier,
                (map, key) -> map.get(key));

SpanContext actual =
        Span.fromContext(extracted).getSpanContext();

assertEquals(traceId, actual.getTraceId());
assertEquals(spanId, actual.getSpanId());
assertTrue(actual.isSampled());
```

This tests the propagator, not gRPC yet. It isolates formatting/inject/extract bugs before adding channels, servers, and instrumentation.

### 3.1. Testing Invalid Context

Construct carriers missing `traceparent`, with wrong `traceparent` length, invalid version/flags, or all-zero trace/span IDs. Verify that the propagator does not construct a valid `SpanContext` from that input and that the application handles the request according to policy.

Never parse `traceparent` manually with substrings inside business interceptors. Use the standard propagator for consistent validation. Trace context sent by a caller is only for correlation; never use it as identity or proof of authorization.

## 4. Testing Baggage

Baggage is a set of key/value pairs propagated across services alongside context. It differs from span attributes: baggage can cross many processes and grow metadata size at every hop.

Baggage tests should verify:

- Only allowlisted keys are propagated.
- No tokens, passwords, emails, or personal data are included.
- Values obey length and total size limits.
- Baggage does not cross tenant/security boundaries unintentionally.
- Baggage is never used in place of authentication or authorization.

If the application enables the W3C Baggage propagator, test baggage inject/extract individually as well as the composite propagator used at runtime. Create tests with allowed keys, disallowed keys, and oversized values; verify the filtering policy before injection.

Do not merely assert that baggage is present on the server. Assert exact keys/values and verify that sensitive keys never appear in outbound metadata.

## 5. Testing gRPC Client/Server Propagation

Once propagator unit tests pass, test instrumentation over real gRPC calls. With gRPC Java instrumentation providing a `GrpcTelemetry`-style API, configure both client and server interceptors using the same test `OpenTelemetry` SDK.

Illustrative in-process structure:

```java
GrpcTelemetry telemetry = GrpcTelemetry.create(openTelemetry);

ServerServiceDefinition instrumentedService =
        ServerInterceptors.intercept(
                inventoryService,
                telemetry.newServerInterceptor());

Server server =
        InProcessServerBuilder.forName(serverName)
                .directExecutor()
                .addService(instrumentedService)
                .build()
                .start();

ManagedChannel rawChannel =
        InProcessChannelBuilder.forName(serverName)
                .directExecutor()
                .build();

Channel instrumentedChannel =
        ClientInterceptors.intercept(
                rawChannel,
                telemetry.newClientInterceptor());
```

This is an illustrative skeleton; package/artifact names and factory APIs must match the gRPC instrumentation version in your build. Close the server/channel in `finally` or a JUnit extension so tests do not leak threads/resources.

Start a parent span in the test, call the generated stub over the instrumented channel, and then end the parent span. Retrieve `SpanData` from the exporter and verify:

- A client span exists for the outbound call.
- A server span exists for the inbound call.
- Client and server spans share the same trace ID.
- The server span's parent is the client span per instrumentation semantics.
- Span kinds are accurately `CLIENT`/`SERVER`.
- RPC method/status attributes match your instrumentation version's conventions.
- Exactly one client/server span is created per attempt executed.

Avoid hardcoding brittle string assertions on span names/attributes if semantic conventions or instrumentation versions may change. Prefer asserting `SpanKind`, trace ID, parent span ID, and stable contract attributes.

### 5.1. Testing Parent-Child Relationships

Filter `SpanData` by `SpanKind.CLIENT` and `SpanKind.SERVER`. For a single RPC attempt:

```java
SpanData clientSpan = findSingleSpan(
        spanExporter.getFinishedSpanItems(),
        SpanKind.CLIENT);

SpanData serverSpan = findSingleSpan(
        spanExporter.getFinishedSpanItems(),
        SpanKind.SERVER);

assertEquals(
        clientSpan.getTraceId(),
        serverSpan.getTraceId());

assertEquals(
        clientSpan.getSpanId(),
        serverSpan.getParentSpanId());
```

`findSingleSpan` is a test helper locating the single span by kind. When retries, hedging, or multiple outbound calls occur, span counts differ; tests must distinguish the logical RPC from individual attempts and verify relationships per call.

## 6. Testing Propagation Across Executors

An RPC may offload database or blocking work to a worker pool. OTel `Context` must be captured on the submitting thread and activated inside the worker.

Example:

```java
Context captured = Context.current();
String expectedTraceId =
        Span.current().getSpanContext().getTraceId();

Future<SpanContext> result =
        workerPool.submit(captured.wrap(
                () -> Span.current().getSpanContext()));

SpanContext workerSpan =
        result.get(2, TimeUnit.SECONDS);

assertEquals(
        expectedTraceId,
        workerSpan.getTraceId());
```

Run this check while the parent span is active. Capture `expectedTraceId` before submitting and compare it against the value returned by the worker; do not read `Span.current()` on the test thread after the scope closes and treat that as the expected value.

### 6.1. Verifying Cleanup on a Shared Thread Pool

Use a single-thread executor to force two tasks onto the same worker:

1. Task A runs inside an OTel `Context` containing span A.
2. Task A completes and the wrapper must restore the previous context.
3. Task B runs with no request context.
4. Verify Task B cannot see span A.
5. Repeat with Task A throwing an exception to verify cleanup in `finally`.

This test catches context leaks that tests spawning a fresh thread per task miss. For MDC, verify `trace_id`/`span_id` are also restored or cleared after the task.

### 6.2. `CompletableFuture` and Callbacks

Async stages must use an OTel `Context`-wrapped executor or proper context propagation instrumentation. Test each boundary:

- `supplyAsync` on a worker pool.
- `thenApplyAsync` with an executor.
- `whenComplete`/`handle` callbacks.
- External async API callbacks.
- gRPC `StreamObserver` callbacks if transport/instrumentation does not automatically preserve context along that path.

Never assume non-async and async stages run on the same thread. Assert trace ID in every stage while also verifying the worker thread returns to its clean baseline state after completion.

## 7. Testing gRPC Context and OTel Context Separately

gRPC `Context` and OTel `Context` (OpenTelemetry `Context`) are two independent mechanisms. A task can retain its OTel span while losing gRPC deadline/cancellation, or retain a gRPC request ID while having no active span.

Test both directions:

| Condition | Expectation |
| --- | --- |
| Only OTel `Context` wrapped | Active span is preserved; gRPC `Context` is not assumed preserved |
| Only gRPC `Context` wrapped | Deadline/request-scoped gRPC values preserved; OTel span is not assumed preserved |
| Both wrapped | Both contexts are present inside the worker |
| Task throws an exception | Both contexts are restored |
| Next task on the same thread | Does not see the previous request's context |

When combining wrappers, clarify which context is captured at submit time and which is activated inside the worker. Use each library's wrapper helpers rather than setting `ThreadLocal` manually.

## 8. Testing Sampling and Exporters

Not every valid trace context results in stored spans. Sampling determines which spans are recorded/exported; tests must therefore separate propagation from recording.

Scenarios:

| Sampler / Scenario | Expectation |
| --- | --- |
| `alwaysOn` | Spans are recorded and appear in the in-memory exporter |
| `alwaysOff` | Spans are not exported, yet the application does not fail due to missing `SpanData` |
| `ParentBased` with sampled parent | Child spans follow the parent sampling decision |
| `ParentBased` with unsampled parent | Child spans are typically not recorded per parent decision |
| Exporter failure | RPC still executes per policy; telemetry errors do not break business calls |
| Exporter reset | Subsequent test sees no spans from prior tests |

Test propagation of unsampled context separately: a trace ID can be propagated with the sampled flag false even when the trace backend stores no spans. Never write tests asserting every request must produce a stored trace when a sampler is dropping traces.

`InMemorySpanExporter` is suited for asserting span data in unit/integration tests. It does not replace testing the production exporter/collector/network pipeline. Include smoke tests verifying that the OTLP exporter, collector, and backend receive data properly.

## 9. Detecting Duplicate Instrumentation

If the Java agent and manual gRPC interceptors both instrument an RPC, traces can show two client spans or two server spans for the same operation.

Tests should:

1. Start the application the exact way production enables the agent/SDK.
2. Invoke a single RPC attempt.
3. Filter spans by `SpanKind`, method, and trace ID.
4. Verify client/server span counts match the attempt count.
5. Verify the parent-child hierarchy does not introduce an extra duplicate layer.
6. Disable one instrumentation source and compare results if duplication occurs.

Do not simultaneously enable multiple instrumentations for the same library without clearly defined ownership. If the Java agent already instruments gRPC automatically, add manual interceptors only for a specific reason and after verifying no duplication occurs.

## 10. Testing Concurrent Requests and Isolation

Propagation frequently breaks under concurrency when context is stored in singletons, mutable maps, or uncleaned `ThreadLocal`s.

Create two requests with different parent spans, interleave them on the same worker pool, and verify:

- Each server span belongs to the trace of its corresponding client call.
- Logged `trace_id`/`span_id` are never swapped between requests.
- Request A's baggage never appears in Request B.
- Completion callbacks still carry the original request's context.
- An exception/cancellation in A does not alter B's context.
- No trace context is stored in fields of singleton services.

Use `CountDownLatch`, `CyclicBarrier`, or test synchronization primitives to control interleaving. Avoid long sleeps, which make tests pass or fail depending on OS scheduling.

## 11. Testing Real Transport

In-process transport tests gRPC call/interceptor behavior quickly, but skips the full network stack. Add tests over real gRPC Netty/sockets to verify:

- HTTP/2 metadata is injected/extracted properly.
- TLS handshakes and ALPN `h2` do not break propagation.
- Proxies/ingress do not strip `traceparent`/`tracestate` or permitted baggage.
- Channel reconnects/retries still produce traces per attempt.
- Deadlines/cancellations and context remain accurate under network delays/resets.
- Exporters function when running with the corresponding application profile.

Transport tests should use ephemeral ports, test CA/certificate fixtures, and bounded timeouts. Never use plaintext production endpoints or real production certificates in CI.

## 12. Security Testing for Propagation Data

Trace context and baggage can arrive from external callers. Propagation does not authenticate the sender and does not establish a trust boundary.

Security tests must cover:

- Malformed `traceparent` is ignored per propagator semantics.
- Disallowed baggage keys are stripped.
- Oversized baggage is bounded or rejected per policy.
- Tokens/passwords/PII are never added to baggage.
- Logs never record raw authorization metadata.
- Trace attributes contain no sensitive payloads.
- Callers cannot use trace ID/baggage to bypass authorization.
- Header propagation is bounded by hop/network policies.

If the system accepts trace context from public callers, evaluate trust, sampling, and trace-restart policies at appropriate boundaries. Even though trace IDs are not secrets, callers can deliberately craft trace IDs to confuse correlation or inflate telemetry load.

## 13. Keeping Test Helpers and Assertions Stable

Avoid tests that depend heavily on exact span names or export ordering when the SDK can finish spans in varying orders. Build helpers that:

- Filter `SpanData` by `SpanKind`.
- Locate spans using stable method attributes for your instrumentation version.
- Assert trace ID and parent span ID.
- Assert status/errors per semantics.
- Assert span counts against RPC attempt counts.
- Assert baggage allowlisting and context restoration.
- Reset the exporter between tests.
- Enforce timeouts on all `Future`s, streams, and server shutdowns.

When a test fails, print a filtered summary containing span kind, trace ID, span ID, parent span ID, method, and status. Never dump all attributes if they might contain sensitive data.

## 14. Common Issues and Troubleshooting

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Carrier unit test passes, but gRPC server has no parent | Client/server interceptor unregistered or wrong instrumentation version | Check gRPC instrumentation wiring and actual metadata |
| Client/server spans have different trace IDs | Inject/extract did not run or context was overwritten | Check propagator, interceptors, and outbound metadata |
| Server span has no parent | Header missing/invalid or server instrumentation did not extract | Test `traceparent` and server interceptor independently |
| Async task has no span | OTel `Context` was not captured/wrapped | Use `Context.wrap` at the submission boundary |
| Task B sees span A | Context not restored after task | Use standard wrappers and test with a single-thread executor |
| OTel span present, but deadline lost | Wrapped only OTel `Context`, not gRPC `Context` | Propagate both contexts separately |
| Baggage contains unwanted data | Missing allowlist/size policy | Filter before inject and test negative cases |
| Two server spans exist for one RPC | Java agent and manual interceptor both instrumenting | Pick one instrumentation path |
| Trace missing from exporter | Sampler dropped it or span never ended | Check sampling, scopes, and span lifecycle |
| Test flags unsampled request as an error | Test conflates propagation with recording | Assert sampled flag and do not require `SpanData` |
| Tests pass in-process but fail in staging | TLS/HTTP2/proxies were never tested | Add network integration tests |
| Tests are order-dependent | Shared `GlobalOpenTelemetry`/exporter state | Inject isolated SDKs, reset fixtures, avoid global mutation |

## 15. Practice Exercises

1. Build an OTel SDK fixture with `InMemorySpanExporter` and an `alwaysOn` sampler.
2. Write a W3C Trace Context inject/extract unit test using a carrier map.
3. Add tests for malformed `traceparent`, sampled flag, and `tracestate`.
4. Set up an in-process gRPC server/channel with OTel client/server interceptors.
5. Invoke a generated stub under a parent span and assert client/server spans share the same trace ID.
6. Assert that the server span's parent is the client span per instrumentation version.
7. Offload a task to a single-thread executor via OTel `Context.wrap`; assert trace ID stays intact.
8. Run a second task on the same worker; assert the previous task's span is gone.
9. Combine gRPC `Context` and OTel `Context`; assert deadlines/request values and active span are both preserved.
10. Test baggage allowlists, value length, and secret/PII rejection.
11. Run a test with an `alwaysOff` sampler; verify propagation can occur even when the exporter receives no spans.
12. Enable the Java agent or manual instrumentation matching production config; assert no duplicate client/server spans exist.
13. Run two concurrent RPCs; assert trace/log/baggage isolation.
14. Create a transport integration test over TLS/HTTP2 and verify `traceparent` is preserved.
15. Write a CI test ensuring telemetry exporter failures do not break business RPCs per policy.

### Self-Check Questions

- Why should you test the propagator separately before testing gRPC end-to-end?
- Which fields must be asserted in W3C Trace Context inject/extract tests?
- Why do in-process tests fail to prove TLS/HTTP2 propagation?
- How do you verify that client/server spans share a trace ID and have the right parent?
- At which boundary must OTel `Context.wrap` be invoked?
- Why should you test on a shared single-thread executor?
- How do gRPC `Context` and OTel `Context` differ?
- How does sampling affect propagation and exported spans?
- Why does baggage require an allowlist and size limits?
- How do you detect duplicate spans caused by the Java agent and manual instrumentation?
- When is testing through a proxy/ingress necessary?
- How do you distinguish a propagation failure from an exporter/backend failure?

## References

- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/): principles of injecting/extracting context.
- [OpenTelemetry — Java API](https://opentelemetry.io/docs/languages/java/api/): `Context`, `Span`, `Tracer`, and `Propagator`.
- [OpenTelemetry Java — SDK](https://opentelemetry.io/docs/languages/java/sdk/): SDK, samplers, processors, and exporters.
- [OpenTelemetry Java — Instrumentation](https://opentelemetry.io/docs/zero-code/java/agent/): automatic instrumentation for Java applications.
- [OpenTelemetry Java — Testing](https://github.com/open-telemetry/opentelemetry-java/tree/main/sdk/testing): in-memory exporter and test utilities.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/): `traceparent`/`tracestate` format and processing.
- [W3C Baggage](https://www.w3.org/TR/baggage/): baggage propagation and header semantics.
- [gRPC — Metadata](https://grpc.io/docs/guides/metadata/): metadata sent over RPCs.
- [gRPC Java — Context](https://grpc.github.io/grpc-java/javadoc/io/grpc/Context.html): gRPC context, deadlines, and executor propagation.

**Expected Outcome:** Learners can test OpenTelemetry propagation from W3C carriers through gRPC clients/servers, async workers, and downstream services; verify trace/span parentage, baggage, sampling, and exporters; detect duplicate spans and context leaks; and prove propagation works over real transport without exposing sensitive data.
