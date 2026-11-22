# Asynchronous Logging, Metrics, and Tracing After Restore

Java applications often write logs, collect metrics, and send traces through background components. An asynchronous logger has a queue and a worker thread; a metrics exporter may hold connections, timers, or a push schedule; a tracing SDK typically has a batch processor, span buffers, and an exporter to a collector. These components reduce per-request overhead, but their state is also affected when a process takes a CRaC checkpoint and then restores after a period of time.

The fact that a Java object still exists on the heap after restore does not mean that the worker thread, socket to the collector, file handle, timer, or credentials that the object uses still work properly. A queue may contain unsent events; an exporter may be holding a stale connection; an open span may have spanned across the checkpoint interval; in-memory counters may resume from old values or be duplicated when one checkpoint creates multiple replicas.

Therefore, observability must be managed according to the CRaC lifecycle. Before checkpoint, stop generating new work, drain requests and background tasks, flush logs/metrics/traces within a time limit, and then prepare or close resources that cannot be kept across checkpoint. After restore, refresh endpoints and credentials, restart workers/exporters using supported APIs, verify that data can be exported, and only open readiness once the application is ready.

## 1. Three Observability Signals Have Different Lifecycles

Logging, metrics, and tracing all help observe the application, but the ways they store and send data differ:

| Component | Primary data | Common asynchronous activity | Post-restore risks |
|---|---|---|---|
| Logging | Log events, timestamps, levels, MDC/context | Queue, async appender, worker thread, socket/file output | Logs remaining in queue, appender worker not running, stale file/socket, duplicate or lost events |
| Metrics | Counters, gauges, timers, histograms | Scrape scheduler, push registry, exporter thread, aggregation window | Stale process values, counter regression, gauges referencing stale objects, expired push connections |
| Tracing | Spans, trace context, parent/child relationships | Batch span processor, exporter queue, worker thread, OTLP/HTTP/gRPC connection | Unfinished spans, unexported batches, stale exporter connection, old context spanning across checkpoint |

Do not handle all three with a single generic `flush()` call. Each library has its own API and semantics. Identify exactly which component owns each queue, worker, socket, and registry; use official CRaC integration if your library version supports it.

## 2. Why Does Async Logging Need to Be Drained?

With synchronous logging, a log call typically writes directly through the appender/output before returning. With asynchronous logging, the call may only enqueue an event and return; a worker thread writes the event later.

```text
Request thread                 Async logger worker
     |                                  |
     |-- logger.info(event)             |
     |-- enqueue event ---------------->|
     |-- continue processing            |-- dequeue
     |                                  |-- write file / send to collector
```

If a checkpoint occurs while events remain in the queue:

- Events may reside in the heap and be restored along with the queue.
- The worker thread or synchronization state of the logging framework may require runtime-specific handling.
- The appender's file descriptor or socket may no longer be valid.
- Events with old timestamps may be sent after restore, distorting observation order.
- If an external system already received the event but the application has not recorded the successful send, retries may create duplicates.

Not all logging frameworks have the same checkpoint/restore behavior. Do not assume queues and workers automatically continue correctly just because they are Java objects. Before checkpoint, stop log producers at a safe boundary, wait for the queue to be processed, and call the framework's flush/drain API.

### Full Queues and Log Drop Policies

Async appenders typically have a bounded queue. When the queue is full, the framework may block producers, lower the log level, discard events, or apply another policy depending on configuration. While preparing for checkpoint, if the worker cannot write because the output has failed, the queue can grow rapidly and cause a drain timeout.

For audit logs or mandatory business logs, do not rely on an in-heap async queue as durable storage. Use a storage mechanism with write acknowledgment, a transaction/outbox, or an appropriate audit system. Diagnostic logs may have a controlled drop policy, but there should be a metric counting dropped events.

## 3. Before Checkpoint: Stop Producers Then Flush Logs

The sequence should be:

1. Switch readiness to refusing traffic and close the admission gate.
2. Drain requests, message handlers, and background jobs so no more logs are created from new business work.
3. Stop schedulers/consumers that generate new tasks.
4. Write a log message announcing the start of checkpoint preparation.
5. Call the async logger's flush/drain API and wait within a deadline.
6. If an appender has a socket/file handle that cannot be safely kept, close it via the lifecycle API and mark it to be recreated after restore.
7. Only proceed with checkpoint when critical logs have been processed or an error policy has been decided.

Do not stop the logger too early. CRaC callbacks or other recovery components may need to log when handling errors. If the entire logging system is shut down, errors in `afterRestore` may go unrecorded. It is usually better to drain queues before checkpoint, selectively close necessary appenders/network resources if the library supports it, and keep a safe fallback logger for the recovery phase.

### Example with Log4j2

Log4j2 has async loggers and async appenders with their own queue/worker mechanisms. How to manage them depends on how the application configures async loggers, `AsyncAppender`, context selectors, and the Log4j2 version. When integrating CRaC, prefer the CRaC module or guidance provided by the exact Log4j2 version if available.

With a self-managed lifecycle manager, the general idea is to wait for events to be processed before checkpoint:

```java
import java.time.Duration;

interface LoggingLifecycle {
    void stopAcceptingApplicationEvents();
    boolean awaitQueuesDrained(Duration timeout) throws InterruptedException;
    void flush() throws Exception;
    void closeCheckpointSensitiveOutputs() throws Exception;
    void reopenOutputs() throws Exception;
    void verifyWritable() throws Exception;
}
```

This is an illustrative application-defined interface, not a Log4j2 API. Do not invoke an internal framework method via reflection just because it happens to be named like `flush`. Use public APIs and documentation for the specific version.

### Example with Logback

Logback has a `LoggerContext` and an appender lifecycle. `AsyncAppender` has a queue and a worker; when stopping, the worker must be allowed to finish writing events following the framework's shutdown mechanism. Do not just close the output file while the async appender is still enqueueing events.

Conceptual example of context coordination:

```java
import ch.qos.logback.classic.LoggerContext;
import org.slf4j.LoggerFactory;

LoggerContext context =
        (LoggerContext) LoggerFactory.getILoggerFactory();

// Only call stop/restart according to the lifecycle designed for the application.
// LoggerContext.stop() stops the entire context and is not a lightweight
// flush operation that can be called arbitrarily before each checkpoint.
```

`LoggerContext.stop()` is a context shutdown operation and should not be used as a generic flush command if the application needs to continue logging when a checkpoint is aborted. Restarting the context and appenders after restore must be verified against the actual configuration; if using Spring Boot logging initialization, coordinate with Spring's lifecycle instead of creating a second context.

## 4. File Appenders, Socket Appenders, and Log Collectors

### File Appender

File appenders hold file handles and may participate in rotation. After restore, verify:

- The file descriptor is still valid and points to the right file.
- Log rotation did not rename or replace the file while the process was checkpointed.
- Permissions, mounts, and paths are still appropriate.
- Two appenders are not writing to the same file in a way that causes interleaving or duplicates.
- Buffers are flushed before closing.

If the environment may change mounts or files, close the appender before checkpoint and reopen the file via the framework lifecycle after restore. Do not manually call `close()` on the underlying file descriptor beneath the appender; the appender needs to manage its own buffers, locks, and rotation state.

### Socket and Network Appenders

Appenders sending logs over TCP, TLS, HTTP, or custom protocols may hold sockets to a collector. During checkpoint, the collector may restart, DNS may change IPs, certificates may rotate, or idle timeouts may close connections.

After restore, recreate network appenders/clients or use a supported reconnect mechanism. Re-read endpoints and credentials from current configuration. If an appender has a retry queue, determine how long that queue retains events and how duplicates are handled.

### Log Events with Old Timestamps

Events created before checkpoint but sent after restore should preserve the event's original timestamp, if the framework records the timestamp at creation time. Do not alter the timestamp to pretend the event occurred after restore. Metadata such as `restore_generation` or instance incarnation can be added so operators can distinguish events created before and after checkpoint.

## 5. Metrics: Distinguishing Counter, Gauge, Timer, and Histogram

A metrics registry typically holds data in memory. Upon restore, that data may continue from the checkpoint snapshot. This is useful in some cases, but you must understand the semantics of each meter type.

| Meter type | Meaning | Post-restore considerations |
|---|---|---|
| Counter | Cumulative count of events over the meter's lifetime | Value may continue from snapshot; backend may see counter regression or reset depending on identity/restore |
| Gauge | Instantaneous value from an object or callback | Callback may reference an old object, stale cache, or closed pool |
| Timer | Count and duration distribution of operations | In-flight samples need to finish/drain; accumulated statistics may be retained but do not represent the checkpointed interval |
| Distribution summary/histogram | Value distribution or buckets | Snapshot may hold old data; need to define window and semantics upon restore |
| Long task timer | Long-running work in progress | Should not let a sample represent an operation interrupted across checkpoint unless business logic defines it clearly |

### Counters Are Not Durable Business Data

Counters in a registry are typically per-process or per-instance observability figures. Do not use them as the source of truth for order counts, monetary amounts, or committed transaction counts. Such business data must be stored in a database or an appropriate ledger system.

If a checkpoint is restored with the same instance identity, counters may continue from old values. If the backend already scraped values before checkpoint, post-restore values may be lower because the checkpoint was created before the last scrape; the backend may interpret this as a reset. If a checkpoint is cloned into multiple replicas with the same metric labels, multiple processes may emit the same initial counter and make the data ambiguous.

The solution is to clearly define metric identity:

- Use service, environment, version, and instance/pod labels according to your backend model.
- Each incarnation needs an appropriate identity so the backend can distinguish a new process if semantics require it.
- Avoid adding unbounded UUIDs to every metric label because cardinality can grow rapidly; use an instance label already managed by the backend or a generation strategy with retention.
- Use a counter backend capable of properly recognizing resets.
- Use a database/event store for business figures requiring accuracy across restarts/restores.

Do not mechanically reset all counters. If the backend expects continuous counters per instance, resetting can cause inaccuracies; if a new instance is created, keeping snapshot counters can duplicate figures. Choose consistent semantics and identity.

### Gauges Must Point to Current State

Gauges typically read values from an object when the backend scrapes. For example, an active database connections gauge may hold a reference to an old, closed pool. After restore, if a new pool is created but the gauge still reads the old pool, the metric will be wrong or throw an exception.

An atomically replaceable holder can be used:

```java
final class PoolMetricsState {
    private final AtomicReference<DataSourceMetricsView> current =
            new AtomicReference<>();

    void install(DataSourceMetricsView view) {
        current.set(view);
    }

    int activeConnections() {
        DataSourceMetricsView view = current.get();
        return view == null ? 0 : view.activeConnections();
    }
}
```

`DataSourceMetricsView` is an application-defined abstraction. The gauge should read from the current holder instead of directly holding the replaced pool object. When the new pool is ready, update the holder; while the pool is recovering, it can return an unavailable state or an appropriate value per metric conventions.

## 6. Pull Metrics and Push Metrics After Restore

### Pull Model: Prometheus Scrape

With the pull model, Prometheus or a collector calls the application's metrics endpoint. There does not necessarily have to be a worker inside the application continuously sending metrics, but the web endpoint, registry, and meters still need to function.

After restore:

- Ensure the metrics endpoint is served by the rebound embedded server.
- Confirm the registry contains the right meters and gauges point to current objects.
- Determine whether the instance label changes per incarnation.
- Understand that the first scrape after restore may see old snapshot counters.
- Avoid having checkpoint-cloned replicas share labels that cause time series ambiguity.

Prometheus distinguishes time series by metric name and labels. If multiple replicas emit the same series with identical labels, data may conflict or overwrite depending on scrape target/configuration. Use target/instance identity appropriate to the topology.

### Push Model: Periodic Registry Push

Some registries periodically push metrics to a backend. They often hold a scheduler, exporter client, socket, or authentication token. Before checkpoint, stop the push schedule, perform a final flush if the API supports it, and close necessary exporter resources. After restore, create a new exporter/client with current endpoints and credentials, then start a new push schedule.

Do not assume a shut-down scheduler can be restarted. If the exporter has been closed, it is usually necessary to create a new exporter/registry or use the library's lifecycle integration. Ensure no two schedulers push the same meter set after restore.

### Micrometer

Micrometer provides the `MeterRegistry` abstraction and many registry implementations. Recovery depends on the specific registry, such as a Prometheus pull registry, a push registry, or a vendor-specific registry. `MeterRegistry.close()` is typically a registry-closing operation and may stop publishers; do not treat it as a lightweight flush command that can be called and then the same object reused.

When managing the lifecycle yourself:

- Identify which registries are pull and which have push workers.
- Stop schedulers/exporters before checkpoint if needed.
- Retain or recreate meters according to the desired semantics.
- Rebind gauges after pools/clients are recreated.
- Create a new registry/exporter if the old implementation was closed.
- Check that meters are not doubly registered while the ApplicationContext still exists.

If the Spring Boot or Micrometer version in use has CRaC integration, prefer that integration. Do not register an additional resource that independently closes a registry already owned by the official integration.

## 7. Tracing: Open Spans and Batch Exporters

Distributed tracing typically creates spans for requests, database calls, HTTP clients, and background jobs. The OpenTelemetry SDK may use `BatchSpanProcessor` to hold spans in a queue and send them in batches via an exporter such as OTLP.

```text
Request thread                 BatchSpanProcessor worker
     |                                  |
     |-- end(span)                      |
     |-- enqueue completed span ------->|
     |-- return response                |-- batch spans
                                        |-- export to collector
```

If a checkpoint occurs while spans are unfinished or batches have not been exported:

- Open spans may represent operations spanning across the interval when the process was not running.
- The queue may contain unsent spans.
- The exporter may hold stale gRPC/HTTP connections or DNS state.
- The batch worker may need to be stopped and recreated.
- Trace context in `ThreadLocal` or executor tasks may no longer be appropriate when work is resumed after restore.

Typically, drain requests and background tasks so business spans end before checkpoint, then call `forceFlush` with a timeout. Do not attempt to keep a request span open across many minutes of checkpoint unless the tracing system and business logic have clear semantics for a paused operation.

### Force Flush and Shutdown Are Two Different Things

In the OpenTelemetry Java SDK, `SdkTracerProvider.forceFlush()` requests processors to flush received data into the exporter. `shutdown()` closes the provider and processors. After shutdown, you should not assume the same provider can be reused.

If the exporter/socket needs to be closed before checkpoint, it may be necessary to create a new `SdkTracerProvider`, processor, and exporter after restore. If only force flushing while keeping the exporter, you still need to check the connection after restore or use an exporter with supported reconnect.

Example of calling a bounded flush:

```java
import java.time.Duration;
import java.util.concurrent.TimeUnit;

import io.opentelemetry.sdk.common.CompletableResultCode;
import io.opentelemetry.sdk.trace.SdkTracerProvider;

final class TracingLifecycle {
    private final SdkTracerProvider tracerProvider;

    TracingLifecycle(SdkTracerProvider tracerProvider) {
        this.tracerProvider = tracerProvider;
    }

    void flushBeforeCheckpoint(Duration timeout) {
        CompletableResultCode result = tracerProvider.forceFlush();
        boolean completed = result.join(
                timeout.toMillis(), TimeUnit.MILLISECONDS
        );
        if (!completed) {
            throw new IllegalStateException("Tracing flush timed out");
        }
        if (!result.isSuccess()) {
            throw new IllegalStateException("Tracing flush failed");
        }
    }
}
```

This is an illustrative SDK API example. Handle timeout/failure results according to the OpenTelemetry version in use and propagate errors up to the callback if critical traces cannot be flushed as required. Do not block indefinitely in the callback.

### Do Not Keep ThreadLocal Trace Context for Resumed Work

Trace context is typically propagated via request headers, context propagation, or task wrappers. A `ThreadLocal` still holding old context in the heap does not prove that context still belongs to the current work after restore.

For work that can continue after checkpoint, store durable business state. Upon resume, a new span can be created using the old trace context as a link if the system stored the context in a controlled manner and tracing semantics allow it. Do not continue a span opened before checkpoint just to preserve one long trace across downtime.

With message queues, trace context should be passed in message headers/metadata. When a consumer reprocesses a message after restore, create a new span from the propagated context and job idempotency.

## 8. OpenTelemetry SDK Integration After Restore

A commonly used lifecycle pattern:

### Before Checkpoint

1. Stop accepting new requests and triggers.
2. Drain request/background work so business spans complete.
3. Stop creating new spans from schedulers/consumers.
4. Call `forceFlush()` on the tracer provider and wait for the result within a deadline.
5. Flush or push metrics according to the registry implementation.
6. Drain async logging queues and flush appenders.
7. If an exporter needs to be closed, shut it down via the official API and mark it to be recreated after restore.

### After Restore

1. Initialize logging outputs early enough to record recovery errors.
2. Re-read current endpoints, TLS certificates, tokens, and observability configuration.
3. Recreate network appenders or verify file appenders.
4. Recreate metrics exporters/push schedulers if old implementations were closed; update gauges to new pools/clients.
5. Recreate OpenTelemetry exporters, span processors, and providers if shut down.
6. Emit a restore event/metric with the new incarnation ID.
7. Verify ability to export to the collector.
8. Switch readiness to accepting traffic.

It is not necessary to recreate the entire instrumentation API if the framework allows keeping the tracer/meter facade and swapping the provider via a supported mechanism. However, do not swap the provider arbitrarily if beans already hold references to the old provider. Create a lifecycle manager that owns the provider and injects a stable facade, or initialize the ApplicationContext using the framework's CRaC integration.

## 9. Example CRaC Resource Coordinating Observability

The interfaces in the example are application-defined abstractions. They help decouple CRaC logic from specific APIs of Logback, Log4j2, Micrometer, or OpenTelemetry.

```java
import java.time.Duration;

import org.crac.Context;
import org.crac.Resource;

final class ObservabilityResource implements Resource {
    private final ApplicationWorkLifecycle work;
    private final LoggingLifecycle logging;
    private final MetricsLifecycle metrics;
    private final TracingLifecycle tracing;
    private final Duration flushTimeout;

    ObservabilityResource(
            ApplicationWorkLifecycle work,
            LoggingLifecycle logging,
            MetricsLifecycle metrics,
            TracingLifecycle tracing,
            Duration flushTimeout) {
        this.work = work;
        this.logging = logging;
        this.metrics = metrics;
        this.tracing = tracing;
        this.flushTimeout = flushTimeout;
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        work.stopAcceptingNewWork();
        work.stopBackgroundTriggers();
        work.awaitInFlightWork(flushTimeout);

        tracing.forceFlush(flushTimeout);
        metrics.flushOrSnapshot(flushTimeout);
        logging.awaitQueuesDrained(flushTimeout);
        logging.flush();

        tracing.closeCheckpointSensitiveExporter();
        metrics.closeCheckpointSensitiveExporter();
        logging.closeCheckpointSensitiveOutputs();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        logging.reopenOutputs();
        logging.verifyWritable();

        metrics.recreateExportersAndRebindMeters();
        tracing.recreateExporterAndProcessor();

        metrics.verifyExport();
        tracing.verifyExport();
    }
}
```

This is an organizational diagram, not a class that compiles as-is because the lifecycle interfaces are application-provided. A real implementation needs to reopen the admission gate and readiness after the web server, database, and essential observability are all ready. If logging outputs cannot be opened yet, keep a console/stderr fallback or emergency mechanism to record errors instead of losing all recovery information.

The flush order may need adjustment. For example, tracing exporters or metrics exporters may log; therefore, drain business work first, flush tracing/metrics, and flush logging last so logs from the export process are also captured. If the framework manages the lifecycle via a resource tree, verify the callback order of the exact runtime instead of relying on arbitrary registration order.

## 10. Timeouts, Flush Errors, and Aborted Checkpoints

Flushing can fail because the collector is unreachable, the filesystem is slow, a queue is stuck, or a worker cannot finish. Do not wait indefinitely in `beforeCheckpoint`.

A practical policy:

- Set separate timeouts for draining work, trace flush, metrics export, and logging drain.
- Record the number of remaining pending events/spans and exporter errors.
- If audit logs or mandatory traces must be sent before checkpoint per system requirements, fail the callback and reject the checkpoint when flushing fails.
- If diagnostic logs may be dropped per policy, record a metric/drop counter and continue within the defined limit.
- Do not swallow errors and then mark observability as ready.
- If the callback has already closed exporters/appenders and the checkpoint attempt fails, reinitialize them on the continuing process or replace the instance; do not assume `afterRestore` will be called to roll back.

Illustrative timeouts:

| Phase | Example budget |
|---|---:|
| Drain requests and background work | 20 seconds |
| Flush trace batch | 5 seconds |
| Flush metrics/exporter | 3 seconds |
| Drain and flush async logs | 5 seconds |
| Close required outputs | 2 seconds |
| Checkpoint engine reserve | 10 seconds |

The numbers need to be measured in a real environment. Do not spend the entire checkpoint budget on logging/tracing and leave requests or transactions incomplete.

## 11. Metrics and Tracing When a Checkpoint Is Cloned Into Multiple Replicas

One checkpoint can be used as the restore source for multiple replicas. This is especially important for observability because registries, counters, and contexts can be copied along with the heap.

### Metrics

- Each replica needs an appropriate identity in labels/target metadata.
- Do not let two replicas emit the same time series with identical labels if they are two independent processes.
- A counter in a checkpoint is not a cluster-wide total; do not aggregate it as business data.
- Gauges must read the state of each replica's own pool/client.
- Do not keep an exporter leader flag in the heap as a mechanism to ensure only one replica pushes metrics.

### Tracing

- Each replica creates its own spans for startup/restore and new requests.
- Do not use a static trace ID stored in the checkpoint for all replicas.
- Do not share an exporter instance or credentials tied to the old process if it does not support clone/restore.
- If work is resumed on another replica, use an appropriate trace link/durable context rather than continuing a span in the previous replica's heap.

### Logging

- Attach instance/incarnation metadata to distinguish the log source.
- Avoid having multiple replicas write to the same local file or share the same appender identity if the backend requires uniqueness.
- A `process.restore` or `application.restore` event can be emitted to distinguish the new run.

## 12. Creating Restore Markers and Keeping Accurate Timestamps

A restore marker helps distinguish data before and after checkpoint. Fields such as the following can be logged:

- `service.name`, `service.version`, and `deployment.environment`.
- New `instance.id` or incarnation ID.
- `restore.generation` or checkpoint attempt ID.
- `restore.started_at` and time since checkpoint if a reliable timestamp source is available.
- Exporter reconnect results and readiness status.

Do not modify timestamps of old logs/spans. Events created before checkpoint must preserve their actual creation time; the new marker has a post-restore timestamp. If checkpoint duration needs to be measured, use a durable timestamp from the controller or external metadata, not inferred from a monotonic clock stored in the heap.

Do not put high-cardinality checkpoint IDs, instance IDs, or trace IDs into every metric label. Use appropriate log/tracing attributes or resource attributes; only use metric labels when the backend and retention allow it.

## 13. Observing Observability Health After Restore

An application may serve requests while failing to send telemetry. Treat observability as an operational dependency and determine its criticality:

| Status | Meaning | Action |
|---|---|---|
| Logging ready | Appender can write to intended output or fallback | Readiness can be opened if logging is not a strict mandatory dependency |
| Metrics ready | Registry/exporter works, gauges bound to right objects | Confirm scrape/push and identity |
| Tracing ready | Processor/exporter can send spans | Check batch queue and collector connection |
| Telemetry degraded | An exporter is temporarily unreachable | Bounded retry, record error metric, keep fallback log |
| Telemetry failed | Queue full or no output available | Depending on operational requirements: keep instance not ready or run with clear alert |

Not every system needs to reject all traffic if the tracing collector is temporarily unreachable. Distinguish whether telemetry is a mandatory audit/compliance requirement or merely a diagnostic channel. Audit logs with high durability requirements need a different mechanism than droppable debug logs.

## 14. Test Scenarios

Test on the exact JDK/CRaC runtime, logging framework, metrics registry, OpenTelemetry SDK, exporter, and collector that will be used in production:

1. Continuously log asynchronously, take a checkpoint, and confirm queues are drained or checkpoint is rejected on timeout.
2. Shut down the log collector before restore, confirm the appender reconnects or uses fallback without losing all recovery logs.
3. Replace log file/rotation during checkpoint, confirm the file appender opens the right file after restore.
4. Check counters before and after restore, confirm the backend properly handles resets/instance identity.
5. Check the active connections gauge after the pool is recreated, confirm the gauge does not reference the old pool.
6. Create spans and force flush before checkpoint; confirm spans are completed and exported.
7. Make the OTLP collector unreachable, confirm flush timeout and checkpoint policy are properly enforced.
8. Restore after a long downtime, confirm the exporter creates a new connection and trace context is not improperly retained.
9. Restore the same checkpoint into multiple replicas, confirm metric labels and instance identity do not conflict.
10. Test a failed checkpoint attempt after appenders/exporters have been closed, confirm the continuing process can recover telemetry.

## 15. Implementation Checklist

- [ ] Async loggers, appender queues, file/socket outputs, and worker threads have been inventoried.
- [ ] Requests and background work are drained before flushing telemetry.
- [ ] Async log queues are drained using supported APIs and with timeouts.
- [ ] File/network appenders are verified or recreated after restore.
- [ ] Audit logs and diagnostic logs have distinct data loss policies, if needed.
- [ ] Post-restore counter, gauge, timer, and histogram semantics have been defined.
- [ ] Gauges are bound to current pools/clients, holding no references to old objects.
- [ ] Pull metrics endpoints work after the server rebinds; push exporters are recreated if shut down.
- [ ] Counters and metric labels properly distinguish process/replica incarnations.
- [ ] Business spans are ended and batch exporters are force-flushed before checkpoint.
- [ ] Tracing exporters/processors are recreated if shut down; closed providers are not reused.
- [ ] Trace context for resumed work is recreated or re-linked according to clear semantics.
- [ ] Collector endpoints, TLS certificates, and credentials are refreshed after restore.
- [ ] Flushes have timeouts, errors are recorded, and there is a policy for failed checkpoint attempts.
- [ ] Single-replica and multi-replica restores have been tested with an interrupted collector.

## 16. Conclusion

Asynchronous logging, metrics, and tracing all have background state that must be managed across CRaC. Async loggers need queues drained and appenders recovered; metrics need counter/gauge semantics defined and exporters recreated if needed; tracing needs business spans ended, batches force-flushed, and exporters/processors reinitialized when providers have shut down.

Stop sources generating new telemetry by draining application work, flush each system via official APIs, and set clear timeouts before checkpoint. After restore, refresh endpoints/credentials, rebind gauges, recreate closed workers/exporters, and emit a restore marker with an appropriate incarnation ID. Only open readiness once essential observability channels are ready or a predefined degraded mode policy has been applied.
