# Test failures without losing telemetry

In the **Testing observability** chapter of the **SPRING_BOOT_OBSERVABILITY** module, testing failures without losing telemetry is the suite of tests that verify an application still records metrics, logs, and traces when an operation fails. An exception is not just a business outcome; it is also the most critical moment to observe clearly so operators can determine where the failure happened, how many requests were affected, and which dependencies were involved.

Telemetry can be lost if an `Observation` is not closed per its lifecycle, an exception is caught and never recorded, context is lost across thread hops, an exporter fails to flush before shutdown, or instrumentation code itself throws an exception that masks the original error. Therefore, tests must exercise both success and failure paths, inspect each signal, and verify error telemetry is still exported even when application operations fail.

This lesson focuses on testing error recording in Micrometer Observation/Tracing, metrics, and structured logs; preserving context across async execution; handling exporter failures; using test exporters/in-memory registries; and building reproducible fault-injection tests.

## 1. Learning objectives

After this lesson, you can:
1. Explain how telemetry should be recorded when an operation throws an exception.
2. Distinguish exception propagation, error recording, and business outcomes.
3. Test the `Observation` lifecycle and handlers on success and failure.
4. Verify span status, exception events, and parent-child relationships.
5. Verify metric counts, durations, and bounded error classifications.
6. Verify logs include error types and trace correlation without leaking sensitive data.
7. Ensure context propagation across executor/async boundaries.
8. Detect exporter failures, queue overflows, and flush/shutdown losses.
9. Use in-memory test exporters and fault injection to reproduce failures.
10. Establish regression tests ensuring application errors never lose telemetry.

## 2. Why is telemetry easily lost on error paths?

A happy-path test typically checks only that an operation returns a result and a meter/span is created. Error paths introduce many extra branches:
- Exceptions escape the method or are caught/translated.
- The `Observation` might be stopped before or after the error is recorded.
- An error handler might return a fallback that makes instrumentation think the operation succeeded.
- Async callbacks may run outside the current `Observation` scope.
- Logging may record the exception but lack trace/span correlation.
- A span may be created but remain with status `UNSET` if the exception is not recorded.
- Exporters may drop data due to full queues, failing endpoints, or premature process shutdown.
- Instrumentation code might throw and mask the original error.

~~~mermaid
flowchart TD
    Start["Start operation"]
    Start --> Obs["Start Observation / span"]
    Obs --> Work["Execute business work"]
    Work -->|success| Success["Record success and stop"]
    Work -->|exception| Error["Record exception and error outcome"]
    Error --> Stop["Stop Observation / span"]
    Success --> Export["Export telemetry"]
    Stop --> Export
    Export --> Verify["Verify metrics, logs and trace"]
~~~

The testing goal is to prove both branches complete their lifecycles and deliver data to the required sinks.

## 3. Distinguishing exceptions, errors, and outcomes

Not every exception means a business operation failed, and not every business failure is represented by an exception.

| Concept | Example | What to test |
| --- | --- | --- |
| Exception | `SQLException`, `TimeoutException` | Exception type is recorded and propagated properly. |
| Span error | Span status `ERROR` or exception event | Tracing handler applies error semantics. |
| Metric outcome | `success`, `failure`, `rejected` | Tag belongs to a finite set and matches business meaning. |
| HTTP result | 400, 404, 500 | Status/outcome reflects the request contract. |
| Business rejection | Insufficient balance | May be a valid outcome, not necessarily an exception. |

A method may catch an exception and return a fallback. In that case, the `Observation` callback sees the method complete normally. If the operation should still be classified as degraded/failure, code must record the outcome explicitly. Conversely, do not mark every exception as `ERROR` if it is an expected business outcome handled normally.

## 4. Closing the Observation lifecycle properly

With Micrometer Observation, prefer `observe(...)` whenever possible so the API manages start/stop and error handling around the callback.

~~~java
Observation.createNotStarted("payment.authorize", registry)
        .lowCardinalityKeyValue("operation", "authorize")
        .observe(() -> paymentService.authorize(command));
~~~

If the callback throws an exception, the `Observation` lifecycle finishes per API/handler semantics and the exception continues propagating to the caller. Tests must verify the `Observation` is created, the error is recorded per handler/convention, stop is called once, the original exception still reaches the caller, and the current `Observation`/trace scope is restored after the callback.

If managing the lifecycle manually with `start`/`stop`, use `try`/`finally`:

~~~java
Observation observation =
        Observation.start("inventory.reconcile", registry);
try {
    reconciler.reconcile();
} catch (RuntimeException error) {
    observation.error(error);
    throw error;
} finally {
    observation.stop();
}
~~~

Never call `stop` before recording the error. Never swallow exceptions just to make tests pass. If an error is caught and converted to a fallback, record an appropriate business outcome before closing the `Observation`.

## 5. Unit testing Observation error recording

You can use `ObservationRegistry` with a test handler to observe the lifecycle without an external backend. Example of a simple handler recording callbacks:

~~~java
class RecordingObservationHandler
        implements ObservationHandler<Observation.Context> {

    final List<String> events = new ArrayList<>();
    Throwable recordedError;

    @Override
    public boolean supportsContext(Observation.Context context) {
        return true;
    }

    @Override
    public void onStart(Observation.Context context) {
        events.add("start");
    }

    @Override
    public void onError(Observation.Context context) {
        events.add("error");
        recordedError = context.getError();
    }

    @Override
    public void onStop(Observation.Context context) {
        events.add("stop");
    }
}
~~~

Test example:

~~~java
@Test
void recordsErrorAndStopsObservation() {
    ObservationRegistry registry = ObservationRegistry.create();
    RecordingObservationHandler handler =
            new RecordingObservationHandler();
    registry.observationConfig().observationHandler(handler);

    RuntimeException failure = new IllegalStateException("simulated failure");

    assertThatThrownBy(() ->
            Observation.createNotStarted("job.execute", registry)
                    .observe(() -> { throw failure; }))
            .isSameAs(failure);

    assertThat(handler.events).contains("start", "error", "stop");
    assertThat(handler.recordedError).isSameAs(failure);
}
~~~

This is an illustrative skeleton; callback ordering and handler APIs must be verified against the Micrometer version managed by Spring Boot. In real tests, assert the lifecycle contract rather than relying on strict ordering across multiple handlers unless guaranteed by the API.

## 6. Testing span status and exception events

When a Micrometer Tracing bridge is configured, an `Observation` can create spans. Tests should use a compatible tracer/test exporter to verify:
- A span is created for the operation.
- The span ends even when the callback fails.
- Error status is set per convention.
- Exception events or error attributes are recorded if supported by the bridge.
- Trace ID/span ID hold valid values.
- Parent span is preserved when the operation is a child of a request.
- No duplicate spans are created by two instrumentation layers.

Do not assert attribute names or event fields by guesswork. Micrometer Tracing bridges, OpenTelemetry/Brave, and semantic conventions can differ. Verify contracts and payloads for your actual versions.

~~~java
assertThat(exportedSpan.getName()).isEqualTo("payment.authorize");
assertThat(exportedSpan.getStatus()).isEqualTo(StatusCode.ERROR);
assertThat(exportedSpan.getEvents())
        .extracting(EventData::getName)
        .contains("exception");
~~~

The snippet above depends on the exporter and span model in use. With Brave, span inspection APIs differ from the OpenTelemetry SDK. Wrap a small test adapter so your test suite is not coupled to implementation details across every test.

## 7. Metrics must still be recorded when operations fail

Timers typically record duration/count when an `Observation` stops, including when the callback ends with an exception if handlers are configured properly. Error counters can supplement failure counts using bounded outcome/error categories.

~~~java
@Test
void timerRecordsFailedInvocation() {
    SimpleMeterRegistry meters = new SimpleMeterRegistry();
    ObservationRegistry observations = ObservationRegistry.create();
    observations.observationConfig()
            .observationHandler(new DefaultMeterObservationHandler(meters));

    assertThatThrownBy(() ->
            Observation.createNotStarted("catalog.lookup", observations)
                    .lowCardinalityKeyValue("operation", "lookup")
                    .observe(() -> {
                        throw new IllegalArgumentException("not found");
                    }))
            .isInstanceOf(IllegalArgumentException.class);

    Timer timer = meters.find("catalog.lookup").timer();
    assertThat(timer).isNotNull();
    assertThat(timer.count()).isEqualTo(1);
}
~~~

This is a conceptual example; meter names and handler constructors depend on Micrometer version. Inspect actual meters in the registry rather than hardcoding naming convention assumptions.

Never put exception messages into metric tags. Use `error.type` or `outcome` with bounded values such as `timeout`, `validation`, `dependency`, or `unexpected`. If exception types have many subclasses or generated classes, map them to a finite taxonomy.

## 8. Structured logs and trace correlation on error paths

Error logs need sufficient diagnostic detail without containing secrets/PII. Useful fields include: `event.name` or operation, `error.type`/category, stable service and route/task identities, `trace_id`/`span_id` when context is present, retry attempt when retries are bounded, outcome, and duration.

~~~java
try {
    inventoryService.reserve(command);
} catch (RuntimeException error) {
    log.atError()
            .addKeyValue("event.name", "inventory.reserve.failed")
            .addKeyValue("error.type", error.getClass().getSimpleName())
            .addKeyValue("outcome", "failure")
            .log("Inventory reservation failed", error);
    throw error;
}
~~~

The logging framework/encoder can automatically include exception stack traces and MDC fields in output. Tests should confirm trace correlation is preserved and messages/stacks do not contain tokens, passwords, or sensitive payloads. Never log full request/response bodies on failure.

## 9. Async execution and context propagation

A common failure mode is an `Observation` starting on thread A while the callback fails on thread B. Without context propagation, child spans and logs can lose the trace ID or become unrelated root traces.

~~~mermaid
sequenceDiagram
    participant A as Request thread
    participant E as Executor thread
    participant T as Trace backend
    A->>A: Start parent Observation
    A->>E: Submit task with context
    E->>E: Start child Observation
    E->>E: Operation throws exception
    E->>T: Export child error span
    A->>A: Complete parent request
~~~

Tests should:
1. Create a parent `Observation`/trace.
2. Submit work through the executor configured with context propagation.
3. Throw an exception in the worker thread.
4. Verify the child span has the same trace ID and proper parent span ID.
5. Verify the exception is recorded even though the callback ran on another thread.
6. Verify context is restored/cleared after task completion to prevent leaking into the next task.

Spring/Micrometer context propagation can use `TaskDecorator` or stack/version-appropriate integrations. Do not assume manually copying MDC also propagates the entire Observation/Tracing context.

## 10. Testing failures at HTTP server/client and database boundaries

A service request can fail at multiple layers:
- HTTP server: controller throws an exception and returns 5xx.
- HTTP client: timeout, connection refused, or downstream 5xx.
- JDBC: `SQLException`, pool acquisition timeout, or transaction rollback.
- Messaging: publish/consume failure, nack, or retry.
- Scheduled task: task exception with no HTTP request parent.

At each boundary, tests should verify proper parent/child span relationships, errors recorded on the right span, accurate HTTP status/outcome or operation outcome, Timer/count recording, log correlation IDs when context exists, no raw payloads/credentials logged, and retries emitting telemetry per policy without duplicate instrumentation.

Do not only verify the controller returns status 500. Inspect telemetry for the failed dependency call to distinguish local errors from downstream errors.

## 11. Exporter failures and telemetry delivery

An operation may create spans/meters/logs in-process yet fail to deliver data to the backend. Causes include Collector/backend unavailability, full export queues, network timeouts or TLS/authentication failures, shutdown before flush, overly short exporter timeouts, sampling dropping traces before export, or async logging appenders not draining queues.

Exporter failure tests should distinguish **recorded in-process** from **delivered to backend**. Never let an exporter exception mask a business exception or fail the main request, unless the application explicitly requires synchronous audit delivery.

Check exporter/SDK indicators such as queue size, dropped spans, export failures, and batch timeouts if exposed by the implementation. Metric names depend on the SDK/exporter version.

## 12. Flushing and shutting down without losing telemetry

In integration tests using a real process/context, verify:
- Observations stop before the exporter closes.
- Batch span processors flush before process exit.
- Logging appenders drain/flush.
- Shutdown timeouts allow enough time for bounded flushing.
- Exporter close/flush is not called multiple times in a way that causes errors.
- Flush errors are surfaced via appropriate diagnostics without masking the root shutdown cause.

You can call `forceFlush` in test exporters/SDKs when supported by the API to keep tests deterministic. Never use arbitrary `sleep` calls to wait for exporters; wait on completion signals or flush futures with bounded timeouts.

## 13. Fault injection and test matrix

Inject controlled failures without relying on external outages:
- Throw exceptions directly.
- Mock HTTP client timeouts/5xx responses.
- Mock repositories throwing `DataAccessException`.
- Reject message publishing.
- Fail executor tasks after context propagation.
- Make exporter test doubles throw errors or time out.
- Fill test queues to verify drop policies.
- Trigger shutdown immediately after generating telemetry to verify flushing.

| Scenario | Primary assertion |
| --- | --- |
| Business method throws | Exception propagates, `Observation` stops, and error is recorded. |
| Exception caught/fallback | Outcome recorded explicitly per business semantics. |
| HTTP downstream timeout | Client span/error and parent trace preserved. |
| JDBC exception | Database span and request timer recorded. |
| Async task failure | Trace context/parent relationship preserved. |
| Exporter unavailable | Business error unmasked; exporter failure observable. |
| Shutdown during export | Flush/close honors deadline and dropped telemetry is detectable. |

## 14. Testing with test exporters and in-memory registries

Use an in-memory exporter to inspect spans without an external backend. With the OpenTelemetry SDK, use version-appropriate exporter/testing utilities; with Micrometer Tracing, choose the corresponding bridge and test facilities. For metrics, `SimpleMeterRegistry` verifies timers/counters; for logs, use test appenders or captured output.

A solid test harness should:
- Create a fresh registry/tracer for each test.
- Register the right `Observation` handlers.
- Avoid sharing mutable exporters across parallel tests.
- Flush the exporter before reading exported spans.
- Reset meter/log state after each test.
- Enforce timeouts so tests never hang.
- Never use production backends or real credentials.

Do not mix Brave and OpenTelemetry bridges in the same test context just for a convenient API. Test the same stack your real application runs.

## 15. Troubleshooting

| Symptom | Possible cause | Investigation direction |
| --- | --- | --- |
| Exception reaches caller with no span | `Observation` not created or tracing handler missing. | Check `ObservationRegistry`/bridge. |
| Span exists without `ERROR` status | Exception caught or error recording convention not applied. | Check catch/fallback logic and error API. |
| Error log exists without trace ID | Context inactive or MDC propagation missing. | Check scopes and executor decorators. |
| Timer does not increment on error | `Observation` handler did not stop or meter filter dropped it. | Check lifecycle and registry. |
| Child span becomes trace root | Context not propagated across thread boundary. | Check `TaskDecorator`/context propagation. |
| Exporter receives no span | Sampling, queue drop, or endpoint/network/auth failure. | Check sampler, exporter diagnostics, and Collector. |
| Test does not see span immediately | Batch exporter has not flushed yet. | Call `forceFlush` or await completion with timeout. |
| Exporter exception masks original error | Custom handler/export call throws synchronously. | Isolate exporter failures and preserve business exceptions. |
| Error tags inflate cardinality | Dynamic exception message/class used as tag. | Map to a bounded error category. |
| Telemetry lost on shutdown | Processor/appender not flushed before process exit. | Check lifecycle order and shutdown timeout. |

## 16. Runbook when error telemetry is lost

1. Identify the affected operation and error path.
2. Check whether the exception escapes the callback or is caught/translated.
3. Verify the `Observation` starts, records the error, and stops.
4. Inspect the tracing bridge and `Observation` handlers.
5. Check for the span in-process/in the test exporter before checking the backend.
6. Check sampling decisions and parent context.
7. If async, verify trace ID/parent span across the executor boundary.
8. Inspect Timers/counters and meter filters.
9. Inspect structured logs, MDC, and masking policies.
10. Inspect exporter queues, drop counters, network, and Collector receivers.
11. Check `forceFlush`/shutdown ordering and timeouts.
12. Add a fault-injection regression test for the identified root cause.

## 17. Self-check exercises

### Exercise 1 — Observation never stops

A method throws an exception and code manually calls `start()` without `finally`. What is the risk?

**Answer:** The `Observation` may never stop, leaving scopes/lifecycles uncleaned and Timers/spans incomplete or unexported. Use `observe()` or `try`/`finally` with error recording.

### Exercise 2 — Caught exceptions

A service catches an exception, returns a fallback, and tests do not see an `ERROR` span. Why?

**Answer:** The callback finishes normally so handlers never see an escaping exception. If the business outcome is degraded/failure, record the error/outcome explicitly.

### Exercise 3 — Async context

A request submits a task to an executor; the worker throws an error, yet the log is missing a trace ID. What should be checked?

**Answer:** Context propagation across the executor, `TaskDecorator` or Micrometer context mechanisms, and MDC correlation.

### Exercise 4 — Span created but missing in backend

The test exporter sees the span, but the trace backend does not. Where could the fault lie?

**Answer:** Exporter/Collector networking, auth/TLS, queue/drops, sampling, or backend ingestion. Distinguish in-process recording from backend delivery.

### Exercise 5 — Exporter failures

An unavailable Collector causes the exporter to throw an exception. Should the business request fail too?

**Answer:** Usually no; telemetry delivery should be isolated from the business path. Exceptions apply when synchronous audit delivery is explicitly required. Record exporter failures separately.

### Exercise 6 — Shutdown flushing

The application exits right after a task fails and the span never reaches the backend. What should be verified?

**Answer:** `Observation` stop, batch processor `forceFlush`/close, logging queue drain, and shutdown timeout. Use completion signals instead of `sleep` in tests.

## 18. Implementation checklist

- [ ] Error paths create and stop `Observation` per lifecycle.
- [ ] Original exceptions propagate or business outcomes are recorded explicitly.
- [ ] Span status/error events are verified against the actual tracer bridge.
- [ ] Timers/counts still record when operations fail.
- [ ] Error types/outcomes use bounded value sets.
- [ ] Logs include trace/span correlation when context exists.
- [ ] Logs/traces contain no secrets, PII, or out-of-policy raw payloads.
- [ ] Async executors propagate context and restore it after task completion.
- [ ] HTTP/JDBC/messaging/scheduled boundaries have appropriate fault tests.
- [ ] Exporter failures/drops/queue saturation have diagnostics.
- [ ] Telemetry failures never mask business exceptions.
- [ ] Test exporters/in-memory registries are isolated between tests.
- [ ] Batch exporters and logging appenders flush before shutdown.
- [ ] Tests use completion/flush signals instead of arbitrary sleeps.
- [ ] CI includes fault-injection regression cases.
- [ ] Production monitors dropped telemetry and exporter failures.

**Takeaway:** Error paths must close Observations per lifecycle, record exceptions/outcomes, preserve trace context, and export metrics/logs/traces within delivery policy limits. Test in-process recording separately from backend export; fault injection across HTTP/JDBC/async/exporter/shutdown boundaries catches telemetry loss before production. Keep error tags bounded and never let telemetry failures mask original business errors.
