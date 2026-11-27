# Impact of Logging, Metrics, and Tracing on Performance Measurements

## 1. Why Does Observability Change Performance?

In the **SPRING_BOOT_NATIVE_IMAGE** module, a Spring Boot application is processed with Spring AOT and compiled into a GraalVM Native Image to evaluate startup time, memory, and operability. When measuring these indicators, you must account for the cost of the observability stack: **logging, metrics, and distributed tracing**.

Every log call can format strings, construct an event, capture a stack trace, and ship data to stdout or a file. Every metric update can look up a meter and update counters or histograms. Every tracing span can allocate objects, store context, attach attributes, propagate trace context, and export data to a collector.

Individual costs may be small, but they multiply by the number of requests, log events, meter series, and spans. In a high-load service, observability can alter:

- CPU usage and memory allocations per request;
- throughput and latency, especially at p95/p99;
- RSS, heap, and exporter queue sizes;
- startup time and time to readiness;
- network traffic to log collectors, metrics backends, and trace collectors;
- benchmark accuracy if runs use different observability configurations.

The goal is not to turn off observability to get pretty numbers. The goal is to **measure with an observability configuration matching the operational environment, understand the overhead introduced by each component, and keep overhead within an acceptable budget**.

## 2. The Three Signals and Sources of Cost

| Signal | Data recorded | Common costs |
| --- | --- | --- |
| Logging | Events, messages, context, stack traces | Message creation/formatting, serialization, I/O, queues, storage |
| Metrics | Counters, gauges, timers, histograms | Meter updates, tag lookups, cardinality, buckets, and scrape/export |
| Tracing | Spans, parent-child relations, attributes, events | Span creation, context propagation, sampling, queues, and export |

~~~mermaid
flowchart LR
    A["Request / background job"] --> B["Application code"]
    B --> L["Logging"]
    B --> M["Metrics"]
    B --> T["Tracing"]
    L --> LC["Log collector"]
    M --> MC["Metrics backend"]
    T --> TC["Trace collector"]
    LC --> S["Storage / analysis"]
    MC --> S
    TC --> S
~~~

The three signals can share a correlation or trace ID, but they do not have identical characteristics. Metrics are typically aggregated into time series; logs store detailed events; traces describe an operation's path across multiple components. Lowering tracing sampling does not automatically reduce metrics or logs.

## 3. Logging: Cost of Event Creation and Data Output

### 3.1. Formatting and Expression Evaluation

Use parameterized logging to avoid formatting messages when the log level is disabled:

~~~java
private static final Logger log =
    LoggerFactory.getLogger(InvoiceService.class);

void createInvoice(String invoiceId) {
    log.debug("Creating invoice {}", invoiceId);
}
~~~

With the call above, the logger can defer message formatting. However, expressions passed as method arguments are still evaluated by Java before the call:

~~~java
log.debug("Invoice details: {}", buildExpensiveSummary(invoice));
~~~

`buildExpensiveSummary(invoice)` still executes even when DEBUG is disabled. If constructing an argument is expensive, check the log level first:

~~~java
if (log.isDebugEnabled()) {
    log.debug("Invoice details: {}", buildExpensiveSummary(invoice));
}
~~~

Do not serialize an entire object graph or compute checksums solely for logging on a hot path. Log fields sufficient for diagnosis, such as operation ID, action type, status, and duration.

### 3.2. Volume of Log Events

A single log event incurs costs across multiple stages:

1. The application builds the message and metadata.
2. The logging framework creates the event and applies filters.
3. The encoder serializes the event to text/JSON.
4. The appender writes to stdout, a file, or a socket.
5. The collector reads, parses, enriches, and forwards it.
6. The backend indexes and stores it.

Writing a log line for every item in a large loop can turn logging into a bottleneck. Prefer logging per operation or per batch, including success/failure counts and total duration.

### 3.3. Stack Traces and Exceptions

Stack traces are helpful when errors require investigation, but they build large strings and consume CPU/I/O. Avoid logging the same exception at every layer:

~~~java
try {
    archive.store(document);
}
catch (ArchiveUnavailableException ex) {
    log.warn("Archive operation failed, documentId={}", document.id());
    throw ex;
}
~~~

At the layer responsible for final error logging, you can log the exception with its stack trace:

~~~java
log.error("Could not persist invoice, operationId={}", operationId, ex);
~~~

Pick one place to log the stack trace for an error handled and propagated across multiple layers. Do not log and swallow an exception if business logic requires the caller to know the operation failed.

### 3.4. Log Levels and Sampling

| Level | Usage | Performance note |
| --- | --- | --- |
| ERROR | Error causing an operation to fail or needing intervention | Avoid duplicate logging of the same exception across layers |
| WARN | Abnormal condition where execution can continue | Rate-limit repeated errors if needed |
| INFO | Business/lifecycle events with operational value | Do not log every request at high load if access logs already cover it |
| DEBUG | Details for investigation | Disable or restrict in production; avoid expensive argument evaluation |
| TRACE | Very granular information | Enable only targeted and briefly |

You can sample or rate-limit repetitive logs such as "dependency unavailable" to prevent log storms. However, do not arbitrarily sample audit logs, security events, or events required by business compliance. If dropping events, maintain a counter indicating how many were suppressed.

### 3.5. Synchronous vs. Asynchronous Logging

Synchronous appenders can block request-handling threads when stdout, disk, or sockets slow down. Async appenders offload events to a queue and dedicated writer thread, decoupling I/O from the request path.

Async logging also introduces costs and trade-offs:

- event allocation and enqueue/dequeue overhead;
- memory for the queue;
- contention when multiple threads log concurrently;
- events may be dropped when the queue is full per the discard policy;
- shutdown must flush the queue within a bounded timeout;
- if the process is killed abruptly, unflushed events may be lost.

Do not assume async is always faster. Measure both slow-collector and near-full-queue scenarios. For critical audit logs, choose a lossless policy or an appropriate durable storage channel; do not rely on an in-memory async queue as an audit store.

### 3.6. Structured Logging and MDC

Structured JSON helps collectors parse fields reliably, though the encoder must serialize each event. Include only necessary fields in logs. Avoid logging large payloads, access tokens, passwords, secrets, or personal data.

MDC/correlation IDs link logs to requests and traces. When using executors or asynchronous processing, ensure context is propagated and cleared properly; leaking context across requests both corrupts data and adds unnecessary overhead.

## 4. Metrics: Cost of Meters, Tags, and Cardinality

### 4.1. Counters, Gauges, Timers, and Histograms

Micrometer provides common meter types:

- `Counter` counts events;
- `Gauge` observes a value at read time;
- `Timer` measures duration and execution count;
- `DistributionSummary` tracks the distribution of values;
- `Histogram` groups measurements into buckets.

Updating a single counter is usually lightweight, but total cost grows with the number of meters, tag combinations, histogram buckets, and scrape/export frequency.

### 4.2. Cardinality Is a Major Cost Driver

Each combination of metric name and tag values can create a separate time series. Adding tags with millions of values—such as `userId`, `requestId`, `email`, or raw URLs—can cause series count to explode.

Example to avoid:

~~~java
Counter.builder("billing.request")
    .tag("customerId", customerId)
    .tag("requestId", requestId)
    .register(registry)
    .increment();
~~~

These tags create a meter series per combination of values. Use tags with small, bounded value domains:

~~~java
Counter.builder("billing.request")
    .tag("operation", "create-invoice")
    .tag("outcome", "success")
    .register(registry)
    .increment();
~~~

If you need to look up a specific request/customer, use controlled trace/log attributes complying with data policies; do not turn them into metric labels.

### 4.3. Timers Can Generate Many Series

A `Timer` can emit count, total time, max, and histogram buckets depending on registry/configuration. When percentile histograms are enabled, each tag combination can create many additional series. Thus, tag cardinality multiplied by bucket count heavily impacts storage and scrape payloads.

Enable histograms/percentiles only for metrics where latency distribution analysis is truly needed. Define buckets aligned with your SLOs instead of enabling histograms on every meter.

### 4.4. Setting Cardinality Limits

You can use a `MeterFilter` to cap tag values on a meter:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.boot.actuate.metrics.MeterRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class MetricsConfiguration {

    @Bean
    MeterRegistryCustomizer<MeterRegistry> metricLimits() {
        return registry -> registry.config().meterFilter(
            MeterFilter.maximumAllowableTags(
                "billing.request",
                "operation",
                20,
                MeterFilter.deny()
            )
        );
    }
}
~~~

The example uses the Micrometer API; verify your project's actual dependencies and versions. This is a secondary guardrail. Designing low-cardinality tags from the start remains the primary defense.

You can attach stable common tags:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.actuate.metrics.MeterRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class CommonMetricsTagsConfiguration {

    @Bean
    MeterRegistryCustomizer<MeterRegistry> commonTags() {
        return registry -> registry.config()
            .commonTags("application", "billing-service");
    }
}
~~~

Do not place environment-specific secrets, random hostnames, or request IDs into common tags. Common tags apply across many meters and thus have broad impact.

### 4.5. Measuring Duration with Timer Example

Create stable meters and reuse them rather than generating dynamic names/tags per request:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;
import java.util.function.Supplier;

@Component
class InvoiceMetrics {

    private final MeterRegistry registry;
    private final Timer successTimer;
    private final Timer failureTimer;

    InvoiceMetrics(MeterRegistry registry) {
        this.registry = registry;
        successTimer = Timer.builder("billing.invoice.create")
            .description("Time to create an invoice")
            .tag("outcome", "success")
            .register(registry);

        failureTimer = Timer.builder("billing.invoice.create")
            .description("Time to create an invoice")
            .tag("outcome", "failure")
            .register(registry);
    }

    <T> T record(Supplier<T> operation) {
        Timer.Sample sample = Timer.start(registry);
        try {
            T result = operation.get();
            sample.stop(successTimer);
            return result;
        }
        catch (RuntimeException | Error ex) {
            sample.stop(failureTimer);
            throw ex;
        }
    }
}
~~~

`Timer.Sample` lets you select the timer after knowing the outcome. In real applications, decide whether to include dependency wait time and avoid double-measuring the same operation across layers. For frequently used metrics, keep stable meter references as shown.

## 5. Scraping and Exporting Metrics

### 5.1. Pull Model

With Prometheus, applications typically expose a scrape endpoint. Spring Boot Actuator example:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
  endpoint:
    health:
      probes:
        enabled: true
~~~

You need the Prometheus registry dependency matching your Spring Boot/Micrometer version:

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
~~~

Scraping too frequently or returning huge payloads increases CPU and network usage. Set scrape intervals according to observability needs and backend capacity; do not use ultra-short intervals to compensate for metrics that are meaningful too late.

### 5.2. Push Model and Exporter Queues

With OTLP or push registries, the application serializes and sends metrics over the network. Batch exporting reduces request count but uses queues and memory. When the backend is slow or disconnected, queues can fill and metrics get dropped.

Monitor export duration, queue size, drop counts, meter/time-series counts, payload sizes, connection errors, and exporter retries.

Do not let synchronous exporters block the request path. Use library-supported batching/asynchronous export with bounded timeouts and shutdown flush limits.

## 6. Tracing: Cost of Spans and Context Propagation

### 6.1. One Request Creates Multiple Spans

A single HTTP request can create spans in the server, controller, service, HTTP client, database, and message broker. Manually creating spans on every method can bloat traces without adding useful insight.

Instrument only meaningful boundaries:

- inbound/outbound requests;
- dependency calls;
- critical transactions or business operations;
- message publishing/consumption;
- background tasks correlated with a request.

Avoid creating spans for getters, tight loops, or overly frequent internal methods. When the framework already auto-instruments HTTP clients or databases, do not create duplicate manual spans for the same call.

### 6.2. Sampling

Sampling determines which spans are recorded and exported. Head sampling decides early when a trace begins; parent-based sampling inherits the parent's decision to keep traces consistent.

Spring Boot example with Micrometer Tracing:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
~~~

`0.1` represents a 10% sampling probability for root traces in this configuration; child spans normally follow the parent's decision. Sampling reduces recorded/exported spans, though it does not eliminate all instrumentation and context propagation costs.

With the OpenTelemetry SDK, you can configure a parent-based trace ID ratio sampler via environment variables:

~~~bash
OTEL_TRACES_SAMPLER=parentbased_traceidratio
OTEL_TRACES_SAMPLER_ARG=0.1
~~~

Configure only one unified tracing stack. If Spring Boot is managing Micrometer Tracing, check which bridge/exporter is active before adding a standalone OpenTelemetry SDK that could create two duplicate pipelines.

Tail sampling at the collector can keep error or slow traces after seeing the entire trace, but the collector must buffer traces and consume more memory. It does not mean the application avoids sending spans to the collector.

### 6.3. Batch Span Processors and Export

Exporting spans synchronously as soon as each span ends forces request threads to wait on the network. A batch processor collects spans and sends them in the background:

- reduces exporter invocations;
- moves most I/O off request threads;
- requires a queue and worker thread;
- may drop spans when the queue fills;
- needs a bounded flush on shutdown.

Monitor queue saturation, export errors, dropped spans, and shutdown flushes. Do not grow queues without bound to mask an under-provisioned collector.

### 6.4. Attributes and Baggage

Attributes aid trace analysis, yet also carry serialization, network, and backend storage costs. Add only useful fields such as operation, dependency, outcome, or version.

Never put tokens, passwords, request bodies, personal data, or large payloads onto spans. Baggage propagated across services can enlarge headers and get copied across many hops; use it only for concrete needs and strictly control the key list.

## 7. Combining Logs, Metrics, and Traces

The three signals can be linked via trace ID and span ID:

- logs with a trace ID help open the exact trace;
- traces carry attributes describing dependencies and operations;
- metrics reveal overall trends, latency, and error rates.

Do not put trace IDs into metric tags. Trace IDs have near-unique cardinality per request and will make time series grow uncontrollably.

Example correlated log:

~~~java
log.info(
    "Invoice created, invoiceId={}, outcome={}",
    invoiceId,
    "success"
);
~~~

When the tracing bridge integrates with MDC, trace/span IDs can be injected automatically into the log pattern. Verify your actual logging configuration; do not generate new IDs at every layer if trace context already exists.

A single failure can increment a metric counter, mark a span with `ERROR` status and an exception event, and emit one error log at the responsible layer. Avoid logging the same stack trace in the controller, service, adapter, and global exception handler.

## 8. Observability Configurations for Benchmarking

To measure overhead, build repeatable configurations:

| Configuration | Logging | Metrics | Tracing | Purpose |
| --- | --- | --- | --- | --- |
| Baseline | Disable unnecessary logs | Disabled/uninstrumented | Disabled | Estimate minimal application cost |
| Logs | Production config | Disabled | Disabled | Measure log and appender cost |
| Metrics | Minimal | Enabled | Disabled | Measure meter updates and scrape/export |
| Tracing | Minimal | Disabled or fixed baseline | Chosen sampling enabled | Measure spans/context/export |
| Production-like | Realistic config | Realistic config | Realistic sampling | Measure combined production-near overhead |

When comparing an individual signal, hold the other signals constant. Turning on JSON logging, histograms, 100% tracing, and switching exporters all at once makes it impossible to isolate where overhead comes from.

The baseline is only for breaking down costs. Release decisions must rely on the production-like configuration, since real systems require observability to operate.

## 9. Performance Measurement Methodology

### 9.1. Measure Startup Separately from Steady State

Record at least two milestones:

- **Startup-to-ready:** from process start until the readiness endpoint reports ready.
- **Time-to-first-useful-request:** time until the first business request completes.

Observability can increase startup due to initializing loggers, registries, exporters, DNS/TLS, or sending resource attributes. Do not require an exporter to successfully connect to a backend before allowing the application to serve requests unless the design demands it.

Also measure shutdown/flush time if logs and traces must be drained when the process stops. Flushes must have a timeout so shutdown cannot hang indefinitely.

### 9.2. Measuring Steady State

Under identical workloads, record:

- requests/second or operations/second;
- p50, p95, p99 latency;
- error rate and timeouts;
- CPU utilization;
- RSS and heap;
- allocation rate/GC if provided by the runtime;
- network bytes sent to collectors;
- log events, meter series, and spans exported;
- dropped events/spans.

Do not look solely at average latency. Congested logging/export queues or growing histograms/cardinality usually show up much more clearly in tail latency and memory.

### 9.3. Controlling Measurements

1. Use identical binary/dependency versions and application configuration.
2. Use identical datasets, request mixes, concurrency, and load durations.
3. Run an equivalent collector/backend for runs with observability enabled.
4. Measure multiple times and compare medians/distributions rather than cherry-picking the best run.
5. Keep native build time separate from runtime startup.
6. For JVM, control warm-up/JIT and document heap settings.
7. For native executables, record OS/CPU, libc, container limits, and RSS.
8. Hold scrape intervals, sampling ratios, and log levels constant.

JVM and native executable RSS do not reflect identical memory structures. Report RSS, heap, and container limits clearly rather than comparing a single raw number without context.

## 10. Example Relative Overhead Calculation

Suppose the same workload yields:

| Configuration | Throughput | p95 latency | RSS |
| --- | ---: | ---: | ---: |
| Baseline | 8,000 req/s | 24 ms | 180 MB |
| Logs | 7,700 req/s | 27 ms | 188 MB |
| Metrics | 7,850 req/s | 25 ms | 184 MB |
| Tracing 10% | 7,760 req/s | 26 ms | 186 MB |
| Production-like | 7,420 req/s | 31 ms | 198 MB |

These are hypothetical figures to illustrate presentation, not Spring Boot or GraalVM benchmark results. In the example, production-like throughput is roughly 7.25% below baseline; p95 increases by 7 ms; RSS increases by 18 MB.

Do not simply add up the individual overheads of logs, metrics, and tracing to predict total overhead. They can share CPU, queues, memory allocators, and I/O; running simultaneously, their effects can interact or amplify.

## 11. Native Image-Specific Observability Notes

### 11.1. Instrumentation Must Be Native-Compatible

Native Image uses closed-world analysis. Logging, metrics, tracing, or exporter libraries may need reflection/resource/proxy metadata. Prefer library versions with published native support/reachability metadata and verify via native builds and runtime tests.

Verify that:

- the logging provider and configuration are found in the executable;
- exporters can initialize and connect at runtime;
- resources such as logging configs, certificates, and service descriptors are present;
- required proxies/reflection have proper hints;
- native libraries needed by exporters/transports match the OS/CPU/ABI.

### 11.2. Do Not Capture Environment Config Into the Image Heap

Collector endpoints, credentials, log destinations, sampling ratios, and truststores are typically environment-specific configurations. Read them from runtime properties/environment variables or secret stores. Do not initialize clients, open sockets, or read secrets in static initializers running at build time.

If changing runtime config still leaves the native executable using build-machine values, check class initialization and how configuration is bound. Do not apply `--initialize-at-run-time` across an entire logging/tracing package by guesswork; locate the specific class initializer and fix only the needed scope.

### 11.3. Java Agents and Native Executables

Java agents typically attach to the JVM via `-javaagent` at launch. A native executable does not run as a standard JVM process, so you cannot assume a JVM Java agent will automatically work with a native binary.

For native images, prefer instrumentation through supported libraries/APIs, Spring/Micrometer integrations, or build-time/native instrumentation mechanisms published by the vendor. Check version-specific documentation for each agent/exporter before adding it to the pipeline.

### 11.4. Shutdown and Flush

When a native process receives `SIGTERM`, the application must close exporters and flush data remaining in batch queues according to the supported lifecycle. Set finite timeouts and test both normal shutdown and container termination.

Do not wait indefinitely for a collector. If the collector is unavailable, the application must stop within the deployment's grace period and record counts of lost events/spans if possible.

## 12. Testing Overhead and Failures in the Observability Pipeline

Do not measure only the healthy-collector case. Test:

- slow or unavailable collectors;
- congested stdout/file logging;
- full async log queues;
- large metrics scrape payloads;
- full span exporter queues;
- DNS/TLS failures when exporters connect;
- shutdown with unflushed events remaining;
- sampling ratio changes;
- high-cardinality tags rejected or capped.

The application must not lose its ability to serve requests simply because the observability backend is temporarily unavailable. Maintain bounded queues, timeouts, bounded retries, and clear drop policies for telemetry. Policies for audit/business events must be designed separately.

### 12.1. Testing Log Volume

Generate controlled load and compare event counts by level, log bytes per request, stack trace counts, suppressed event counts, CPU, and latency with sync vs. async appenders, queue depth, and dropped events.

### 12.2. Testing Metrics Cardinality

Count series by metric name and tag combinations. Send requests with many distinct user/request IDs and verify series counts do not scale with request counts. Monitor scrape duration, payload size, and backend ingestion.

### 12.3. Testing Tracing Sampling

Send a workload containing parent/child calls, errors, and slow requests. Verify child spans preserve parent trace context, sampling ratios are applied per policy, error statuses/attributes appear on retained traces, exporter queues do not grow unbounded, and trace IDs do not appear as metric tags.

## 13. Common Misconfigurations

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| CPU spikes when enabling DEBUG | Expensive messages/arguments, excessive logging, or serializing large objects | Reduce hot-path logging, guard arguments, and restrict levels |
| p99 spikes when stdout is slow | Synchronous appender blocks request threads | Measure async appenders, queues, and collectors; set clear overflow policies |
| RSS grows over time | Async/exporter queues accumulate or cardinality grows | Monitor queues, drop counts, meter series, and exporters |
| Prometheus scrape is slow | Too many series/buckets or overly frequent scraping | Reduce cardinality, pick necessary histograms, and adjust scrape interval |
| Metrics backend storage costs surge | Tags have near-unique values per request | Remove request/user IDs from metric tags |
| Trace export slows down requests | Synchronous export or slow collector/network | Use batch processor, timeouts, and bounded queues |
| Traces miss child spans | Broken context propagation or inconsistent sampling | Check executor/reactive context and parent-based sampler |
| Works on JVM but native lacks logging provider | Missing service descriptors/resources/reachability metadata | Check dependency metadata and native output |
| Native cannot connect to collector | Wrong DNS, TLS, CA, or runtime endpoint | Check truststore, hostname, and runtime config |
| Native uses build machine's sampling ratio | Config captured at build time or bound incorrectly | Move config to runtime and check class initialization |
| Data lost on shutdown | Queue not flushed or timeout too short | Check lifecycle, flush timeout, and termination grace period |

## 14. Hands-On Workflow for Measuring Overhead

Suppose a billing service has an HTTP endpoint creating invoices and calling an archive service.

**Step 1 — Define the workload**

- fix request mix, concurrency, and dataset;
- specify success/error ratio;
- pick a duration long enough to observe steady state;
- run on identical OS/CPU and resource limits.

**Step 2 — Establish the baseline**

- disable unnecessary debug/trace logs;
- disable tracing and external exporters;
- keep business logic and dependencies identical;
- measure startup, throughput, p95/p99, CPU, and RSS.

**Step 3 — Enable production-like logging**

- use planned deployment log levels and format;
- keep collector/appender conditions constant;
- measure log bytes/request, queues, CPU, and latency.

**Step 4 — Enable metrics**

- use planned meter names and tag cardinality;
- enable histograms only on required metrics;
- run scrape/export at real intervals;
- measure series count, scrape duration, payload, and RSS.

**Step 5 — Enable tracing**

- pick the planned sampling ratio;
- use batch export and an equivalent collector;
- generate traces with HTTP/database/client spans;
- measure spans/request, queues, export latency, and p99.

**Step 6 — Enable full observability**

Re-run the same workload. Compare combined results against individual configurations to spot interactions between signals.

**Step 7 — Repeat on the native executable**

Build native from the same source/dependencies and matching AOT config. Run the same workload, collector, sampling, and log levels. Record native build time separately; do not fold it into startup time.

**Step 8 — Fault testing**

Slow down or stop the collector, increase log volume, send many requests while keeping metric tags stable, and observe queues, drops, latency, and recovery.

## 15. Checklist Before Publishing Measurements

- [ ] Logging, metrics, and tracing configurations are documented for every run.
- [ ] Hot-path logs do not format or serialize large data unnecessarily.
- [ ] Async logging has bounded queues, overflow policies, and clear shutdown behavior.
- [ ] Audit/security events are not sampled outside policy.
- [ ] Metric tags have low, stable cardinality.
- [ ] Histograms/percentiles are enabled only on required metrics.
- [ ] Scrape intervals and exporter batching are recorded.
- [ ] Tracing sampling ratio and sampler type are recorded.
- [ ] Span export uses appropriate batching/timeouts/bounded queues.
- [ ] Trace IDs are never used as metric labels.
- [ ] Secrets, credentials, or sensitive payloads are never logged or exported.
- [ ] Startup-to-ready and time-to-first-useful-request are measured separately.
- [ ] Throughput, p50/p95/p99, CPU, RSS, queues, and drop counts are measured.
- [ ] JVM warm-up and native build/startup are kept separate.
- [ ] Identical workloads and collectors are used when comparing.
- [ ] Native executable has been verified for providers, resources, TLS, and shutdown flushes.
- [ ] Unavailable collector and queue saturation scenarios have been tested.

**Key takeaway:** logging, metrics, and tracing all incur CPU, memory, I/O, and network costs. High cardinality, excessive log events, unnecessary histograms, and synchronous span exports can skew measurements or degrade latency. Measure each signal individually, re-measure a production-like configuration, and repeat on the native executable under identical workloads and deployment conditions.

## References

- [Spring Boot Reference — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer, Actuator metrics, and registry configuration.
- [Spring Boot Reference — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): Micrometer Tracing, sampling, and exporter integration.
- [Micrometer Documentation](https://docs.micrometer.io/micrometer/reference/): meter types, registries, filters, timers, and cardinality.
- [OpenTelemetry — Sampling](https://opentelemetry.io/docs/concepts/sampling/): head/tail sampling and reducing exported trace volume.
- [OpenTelemetry — Batch Span Processor](https://opentelemetry.io/docs/specs/otel/trace/sdk/): span processors, batching, and SDK behavior.
- [Logback Manual — Appenders](https://logback.qos.ch/manual/appenders.html): synchronous/asynchronous appenders and queue behavior.
- [GraalVM Native Image — Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/): metadata for reflection, resources, and service loading in native executables.
