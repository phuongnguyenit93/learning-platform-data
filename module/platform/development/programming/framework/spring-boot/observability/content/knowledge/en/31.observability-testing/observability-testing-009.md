# Test trace propagation

A request enters the Order Service, calls the Inventory Service over HTTP, and then publishes an event for asynchronous processing. When viewing the trace, operators need to see spans belonging to the same trace with proper parent-child relationships or links. If trace context is lost at HTTP headers, message headers, or executor boundaries, each service can start a separate trace; latency and cross-service errors become hard to investigate. Trace propagation tests confirm that context is injected, transmitted across the transport, and extracted properly on the receiving side.

The lesson **Test trace propagation** belongs to the **Testing observability** chapter of the **SPRING_BOOT_OBSERVABILITY** module. This module teaches how to set up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; understanding context propagation, tags/cardinality, exporters, sampling, and correlating signals to investigate errors, latency, and application behavior in production environments.

> **Principle:** Test both the wire format and framework integration. With W3C Trace Context, verify `traceparent`/`tracestate` are injected and extracted; verify the trace ID stays constant while the span ID changes per new span. With messaging, verify headers/context are transmitted and the consumer span has the right parent/link per transport semantics. Do not assert random IDs against fixed literals, and never put PII/secrets into baggage.

## 1. Learning objectives

After this lesson, you can:
1. Explain trace context propagation across process boundaries.
2. Distinguish trace ID, span ID, parent span, and tracestate.
3. Verify W3C `traceparent`/`tracestate` injection and extraction.
4. Write unit tests for propagators and integration tests for Spring Boot HTTP clients/servers.
5. Verify propagation across messaging headers.
6. Confirm parent-child relationships or span links per transport semantics.
7. Verify baggage allow-lists and privacy constraints.
8. Test context propagation across executor and reactive boundaries.
9. Understand sampling and why a trace may not be exported even when headers are propagated.
10. Use a test tracer/in-memory exporter to assert spans without a real backend.
11. Test malformed/missing header handling and starting a new trace when no parent exists.
12. Avoid flaky tests, shared tracing state, and duplicate spans.

## 2. What is trace context propagation?

Distributed tracing links operations across multiple processes into a single trace. When service A calls service B, A transmits context over the transport; B extracts the context to create a continuing span.

W3C Trace Context typically uses:
- `traceparent`: version, trace ID, parent span ID, and trace flags.
- `tracestate`: vendor-specific tracing state.
- `baggage`: application-defined key/value context propagated separately.

The trace ID identifies the entire trace. Each span has its own span ID. A child span preserves its parent's trace ID but gets a new span ID and sets its parent span ID to the caller span.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Order Service
    participant B as Inventory Service
    C->>A: HTTP request
    Note over A: Server span A
    A->>B: HTTP + traceparent
    Note over B: Extract context
    Note over B: Client/server span B
    B-->>A: HTTP response
    A-->>C: HTTP response
~~~

The diagram illustrates sharing the same trace over HTTP. Implementations may create a client span in A and a server span in B; both have distinct span IDs.

## 3. Distinguishing trace ID, span ID, and parent

| Field | Meaning | During propagation |
|---|---|---|
| trace ID | Identifies the trace across services | Preserved unchanged |
| span ID | Identifies a specific span | New span gets a new ID |
| parent span ID | Span that directly created the current span | Points to caller span per propagation model |
| trace flags | Sampling/trace flags per W3C format | Carried in `traceparent` |
| tracestate | Vendor-specific state | Carried if supported by propagator |
| baggage | Application key/value context | Propagated only per policy |

A test that checks only that the trace ID matches is insufficient. Verify that the new span ID differs from the parent span ID and that the parent relationship is accurate.

## 4. W3C Trace Context headers

A valid `traceparent` example looks like:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
tracestate: vendor=value
~~~

Structure of `traceparent`:
- Version: 2 hex characters.
- Trace ID: 32 hex characters, must not be all zeros.
- Parent ID: 16 hex characters, must not be all zeros.
- Trace flags: 2 hex characters.

Do not hand-parse headers with substring logic in production code when a standard propagator is available. Use the W3C propagator supplied by your tracing bridge/SDK to handle validation, versions, and invalid contexts.

## 5. Testing a propagator independently

Propagator unit tests should verify inject/extract without needing a Spring context or network.

Test concept:
1. Create a current trace context with known trace ID and span ID.
2. Call propagator `inject` into a mock carrier map/headers.
3. Assert `traceparent` has a valid format.
4. Extract context from the carrier.
5. Assert the trace ID is preserved.
6. Assert span/parent context matches the injected context.
7. Test `tracestate` and `baggage` if enabled.

Illustrative pseudocode:

~~~java
Map<String, String> carrier = new HashMap<>();
propagator.inject(context, carrier, Map::put);

String traceparent = carrier.get("traceparent");
assertThat(traceparent).matches(
        "00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}");
~~~

This is pseudocode because exact inject/extract APIs depend on the Micrometer Tracing bridge or OpenTelemetry SDK. Tests must use the API of the installed implementation; do not build a fake propagator just to test self-written logic.

## 6. Testing extraction from inbound HTTP

The server receives `traceparent` from request headers. Integration tests should:
- Send an HTTP request with a valid `traceparent`.
- Verify the server span uses the trace ID from the header.
- Verify the server span ID differs from the transmitted parent span ID.
- Verify the server span has a remote parent per the tracing implementation.
- Verify the response still succeeds even if `tracestate` is absent.

You can use MockMvc/WebTestClient or a random-port test server depending on your stack. When verifying actual servlet filter/server instrumentation, testing through an embedded HTTP server covers more wiring than a MockMvc slice.

Example request:

~~~http
GET /orders/42 HTTP/1.1
Host: localhost
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Assert that the trace ID equals the transmitted value and inspect the span relationship in the test reporter. Do not expect the server span ID to equal the caller's ID; it must be a new ID.

## 7. Testing outbound HTTP injection

When Order Service calls Inventory Service, client instrumentation must inject context into the outbound request.

An integration test can use MockWebServer/WireMock or a local HTTP server:
1. Send an inbound request carrying `traceparent`.
2. Inside the handler, call an instrumented `RestClient`/`RestTemplate`/`WebClient`.
3. The test server receives the outbound request and records its headers.
4. Assert the outbound `traceparent` carries the same trace ID.
5. Assert the parent span ID reflects the client span per the propagation model.
6. Assert no non-allow-listed baggage is present.

Example expected headers:

~~~text
Inbound trace ID: 4bf92f3577b34da6a3ce929d0e0e4736
Outbound trace ID: 4bf92f3577b34da6a3ce929d0e0e4736
Outbound span ID: generated child span ID
~~~

Do not hardcode the child span ID. Compare relationships and format rather than comparing random strings against fixed fixtures.

## 8. Spring Boot tracing test setup

Spring Boot tracing auto-configuration requires a Micrometer Tracing bridge and appropriate exporter. In tests, you can configure an in-memory exporter/reporter or bridge-provided test tracer to collect spans.

Things to verify:
- A tracing bridge is present (e.g., Brave or OpenTelemetry bridge).
- Tracer is auto-configured in `ApplicationContext`.
- `ObservationRegistry` has a tracing observation handler.
- HTTP client/server instrumentation is enabled.
- Test sampling probability does not drop traces under test.
- The test exporter/reporter receives spans when spans end.

Do not assume adding `spring-boot-starter-actuator` alone enables a tracing backend. You need the bridge/exporter dependencies and configuration matching your Spring Boot version.

### 8.1 Testing with a test reporter

With Brave, test utilities may offer `TestSpanHandler`/finished-span collections; with the OpenTelemetry bridge, use `InMemorySpanExporter` or a version-appropriate `SpanExporter` test double. Specific APIs vary, while assertions are similar:
- Span name.
- Trace ID.
- Span ID.
- Parent span ID.
- Kind (server/client/consumer/producer).
- Attributes/events/status.
- Start/end lifecycle.

## 9. Testing messaging propagation

Messaging propagation transmits context inside message headers/metadata rather than HTTP headers. The producer injects trace context; the consumer extracts context and creates a consumer span.

~~~mermaid
sequenceDiagram
    participant P as Order Producer
    participant Q as Broker
    participant C as Inventory Consumer
    P->>Q: Publish message + trace headers
    Note over Q: Broker preserves headers
    Q->>C: Deliver message
    Note over C: Extract trace context
    C->>C: Process message span
~~~

Tests must verify:
- A producer span is created around publish.
- Message headers contain `traceparent` or the format used by the integration.
- The consumer extracts context.
- The consumer span shares the same trace ID or has a link per messaging semantic conventions.
- Retries/redeliveries do not produce stale context or mislink parents.
- Batch consumption handles links/parent relationships per integration behavior.

Do not automatically assume a consumer span is always a direct child of the producer span. Some messaging conventions use span links, especially for batch processing or independently processed messages. Assert according to the semantics of your Spring Kafka/AMQP integration and convention version.

## 10. Testing baggage propagation and privacy

Baggage is not the same as `traceparent`. Trace context is required to link spans; baggage is application metadata that may be forwarded across many downstream services.

Tests should:
1. Create baggage with an allow-listed key, e.g. `tenant.tier=business`.
2. Add a disallowed key, e.g. `customer.email`.
3. Inject into an outbound carrier.
4. Assert only allow-listed keys are propagated.
5. Assert values are normalized and length-bounded.
6. Assert no tokens, cookies, emails, or account identifiers appear in headers/attributes.

Example policy:
- Allow `tenant.tier` with values `free`/`business`/`enterprise` if approved by privacy policy.
- Allow `request.class` with a bounded set of values.
- Reject `customer.email`, `user.id`, `authorization`, and session tokens.

Baggage can become span attributes or be forwarded further depending on instrumentation. Never put PII/secrets into baggage simply because a current test does not export them.

## 11. Context propagation across executors and async

`ThreadLocal` context does not automatically appear on another thread. When code dispatches to an executor, context can be lost without Micrometer Context Propagation or appropriate integrations.

Architecture illustration:

~~~mermaid
flowchart LR
    A["Request thread"] --> B["Capture context"]
    B --> C["Executor task"]
    C --> D["Restore context"]
    D --> E["Child span / Observation"]
~~~

Tests should:
- Create a parent span/Observation on the request thread.
- Submit a task through the executor configured with context propagation.
- Inside the task, create a child span/Observation.
- Assert the same trace ID and parent relationship.
- Finish the task and verify the scope is restored/cleared.
- Run another task to ensure context does not leak onto a reused thread.

Use a `Future`/latch to wait for task completion. Never use `Thread.sleep` for test synchronization. Verify the actual `TaskDecorator`, `ContextSnapshot`, or framework integration instead of assuming an executor propagates context automatically.

## 12. Reactive context propagation

In Reactor, execution can switch threads via `publishOn`/`subscribeOn`. Tracing context needs to ride Reactor Context and compatible instrumentation; plain `ThreadLocal` is not a safe contract across reactive pipelines.

Test:
1. Start a trace context.
2. Build a reactive pipeline with `publishOn`/`subscribeOn`.
3. Create a child Observation/span inside an operator or downstream service call.
4. Assert the child shares the same trace ID.
5. Verify context is restored properly on pipeline complete/error/cancel.
6. Subscribe multiple times to verify each subscription has a proper lifecycle.

Use Reactor Test `StepVerifier` to synchronize and assert terminal signals. Avoid checking thread names as the sole proof of context propagation.

## 13. Missing, malformed, and untrusted trace headers

Inbound headers from external clients may be missing, malformed, or forged. Test these cases:
- Missing `traceparent`: server starts a new trace per policy.
- Malformed `traceparent`: propagator ignores invalid context and creates an appropriate context.
- All-zero Trace ID or Parent ID: invalid header.
- Unsupported version: handled per W3C version rules.
- Overlong/invalid `tracestate`: validated or dropped by propagator.
- Baggage containing non-allow-listed keys/values: filtered/removed.
- Remote sampled flag = 0: sampling policy may choose not to export the trace.

Never trust trace headers as identity or authorization. Trace context is strictly for correlation; never use it to grant access or determine tenant identity.

## 14. Sampling and test expectations

Trace context propagation and sampling are related but distinct concerns:
- Context can be injected/extracted even when the trace is not exported.
- The sampled flag can influence downstream head sampling.
- A parent-based sampler can honor upstream decisions.
- Tail sampling can decide after the Collector receives spans.
- Tests can become flaky if sampling probability is low.

In integration tests, configure a deterministic sampler or 100% sampling probability for the test scope. Do not alter production sampling policy just to make a test pass. When testing propagation headers, assert headers independently of whether the exporter stores spans.

## 15. End-to-end multi-service testing

A test can launch Order API and Inventory API on random ports:
1. Send an inbound request with a `traceparent` fixture.
2. Order server creates a server span.
3. Order calls Inventory via an instrumented HTTP client.
4. Inventory receives and extracts the trace context.
5. Inventory creates a server span and returns a response.
6. Order finishes its server span.
7. The test reporter collects finished spans.
8. Assert shared trace ID, distinct span IDs, and proper parent relationships.

You can add a messaging path to verify producer/consumer behavior. However, multi-process/container tests should be reserved for critical contract/integration coverage; propagator unit tests are faster and easier to diagnose.

## 16. Troubleshooting

| Symptom | Possible cause | How to resolve |
|---|---|---|
| Each service has a different trace ID | Header not injected/extracted or client uninstrumented | Check `traceparent` at each boundary |
| Trace ID matches but span has no parent | Parent context lost or span started as root | Check current context and extraction |
| Outbound request missing `traceparent` | Tracing bridge/client instrumentation not enabled | Check client bean and observation handler |
| Server span ignores inbound trace ID | Malformed header, mismatched propagator format, or filter stripped header | Inspect raw headers and propagator |
| Messaging consumer trace disconnected | Producer did not inject headers or consumer did not extract | Check broker record headers |
| Async child span becomes root | Context not propagated across executor | Configure Context Propagation/`TaskDecorator` |
| Reactive span loses parent after scheduler switch | Reactor context instrumentation inactive | Check Reactor integration and context mode |
| No spans in test reporter | Sampling dropped trace, span unended, or exporter unwired | Use deterministic sampler and flush/await |
| Baggage contains PII | Baggage lacks allow-list | Filter at source and test with canary |
| Traces cross-wired between requests | `ThreadLocal`/context not cleared or carrier reused | Check scope close and carrier lifecycle |
| Batch consumer parent differs from expected | Messaging convention uses links | Assert span links per integration semantics |
| Flaky test | Random sampling, shared tracer, or sleep | Isolated registry/reporter, deterministic sampling, and latches |

## 17. Playbook: verifying a trace across HTTP and messaging

**Scenario:** An Order request calls Inventory over HTTP and then emits an event; the trace backend shows the consumer is disconnected from the initial trace.

1. Send a request with a valid `traceparent` fixture to the Order API.
2. Verify the Order server span uses the fixture trace ID.
3. Capture the outbound HTTP request at a test server and inspect `traceparent`.
4. Verify the Inventory server span uses the same trace ID and proper parent/client relationship.
5. Capture message producer headers prior to publishing.
6. Verify trace context is encoded in message headers.
7. Consume the message and verify the consumer span uses the context or link per convention.
8. Check that baggage contains only allow-listed keys.
9. Check sampling decisions and verify the test reporter receives finished spans.
10. If the trace splits, pinpoint the first boundary losing headers/context and fix instrumentation at that boundary.

Do not look only at the final trace UI. Capture headers and spans at each boundary to determine whether context was lost at the producer, transport, consumer, or exporter.

## 18. Self-check exercises

**Exercise 1 — Trace identifiers.** When A calls B, which field stays the same and which fields must change on the new span?

**Exercise 2 — HTTP injection.** How do you prove `RestClient`/`RestTemplate` injected `traceparent` into an outbound request?

**Exercise 3 — Messaging.** Why shouldn't you always assert that a consumer span is a direct child of the producer span?

**Exercise 4 — Baggage.** Design a test proving `customer.email` is not propagated while `tenant.tier` is allow-listed.

**Exercise 5 — Async.** Why can `ThreadLocal` context be lost when a task runs on another executor thread? Which mechanisms should you inspect?

**Exercise 6 — Sampling.** Why can a valid `traceparent` be present while the test exporter receives no span?

**Exercise 7 — Invalid headers.** How should a server handle a malformed `traceparent`? Why are trace headers not authentication credentials?

**Exercise 8 — Span relationship.** Beyond trace ID, what should you assert to verify a proper parent-child relationship?

### Suggested answers

1. Trace ID stays the same; the new span ID differs, and parent span ID points to the caller span per the propagation model.
2. Use a local mock HTTP server, send a request via the instrumented client bean, capture request headers, and assert a valid `traceparent` with the same trace ID.
3. Batch processing or messaging semantics may use span links depending on convention/integration.
4. Inject baggage with both keys, assert the carrier only contains `tenant.tier` with its allow-listed value and excludes `customer.email`.
5. `ThreadLocal` does not automatically follow into another thread; check Micrometer Context Propagation, `TaskDecorator`, or Reactor integration.
6. Sampling may not have selected the trace, the span has not ended yet, or the exporter/reporter is not configured/flushed.
7. Ignore the invalid context and start a new trace per policy; headers can be arbitrarily forged by callers and must never be used for authorization.
8. Parent span ID, distinct span ID, span kind, and relationship/links per transport semantics.

## 19. Official references

- [W3C Trace Context](https://www.w3.org/TR/trace-context/): `traceparent`, `tracestate`, and propagation format.
- [W3C Baggage](https://www.w3.org/TR/baggage/): baggage header and propagation behavior.
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): Micrometer Tracing, propagation, and sampling configuration.
- [Micrometer Tracing](https://docs.micrometer.io/tracing/reference/): tracer bridges, span lifecycle, and propagation.
- [Micrometer Context Propagation](https://docs.micrometer.io/context-propagation/reference/): context capture, restoration, and thread boundaries.
- [Spring for Apache Kafka — Micrometer Observation](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html): producer/consumer observation and tracing headers.
- [Spring AMQP — Micrometer Observation](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven/enable-micrometer.html): listener observation and propagation integration.
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/): context across process boundaries.
- [OpenTelemetry Semantic Conventions — Messaging](https://opentelemetry.io/docs/specs/semconv/messaging/): messaging spans, parent/link semantics, and attributes.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): HTTP client integration points.

**Takeaway:** Test trace propagation at every boundary: inbound extraction, outbound injection, broker headers, consumer extraction, and async context. Trace ID stays constant within a trace while span ID changes per operation; assert parents or links per HTTP/messaging semantics. Baggage needs allow-lists and privacy assertions. Sampling can prevent spans from being exported even when context is propagated. Use a test tracer/reporter and local transports to verify headers and span relationships without depending on a production backend.
