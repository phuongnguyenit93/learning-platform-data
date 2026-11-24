# The Role of Logs, Metrics, and Distributed Traces

## 1. Starting from a Slow Request

An e-commerce application is returning responses slowly. Operators must answer three distinct groups of questions:

- **Scope of impact:** how many requests are slow, when did the error rate start rising, and is this happening on one host or many?
- **Path of a single request:** is time spent in the receiving application, the payment call, or the database query step?
- **Specific events:** which processing step failed, what error occurred, and which execution branch did the application take?

**Metrics** help you see trends and scope of impact. **Distributed traces** help follow the stages of an execution. **Logs** provide events and details recorded along the way.

The ability to understand internal system state from external outputs is called **observability**. These three signal types complement one another; simply collecting lots of data does not guarantee operational questions can be answered. In Spring Boot, Micrometer Observation is the foundation connecting observation to metrics and tracing. See [Spring Boot 3.3 — Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

This lesson belongs to the Actuator overview section: the goal is knowing where each signal helps, how they connect, and Actuator’s role. Deploying a full storage backend and monitoring UI is a separate step.

## 2. Logs: Recording Events and Context

### 2.1. What Does a Log Record Answer?

A log is a record of an event. A useful record typically includes a timestamp, severity level, originating application, event name, and context explaining what happened.

The example below is **self-invented illustrative data**, not Spring Boot’s default output format:

~~~text
time=2026-11-04T10:00:01Z level=WARN service=checkout
event=payment.timeout provider=sandbox
traceId=4bf92f3577b34da6a3ce929d0e0e4736 spanId=00f067aa0ba902b7
~~~

This record tells us the `checkout` application observed a payment timeout with a sandbox provider. To know how many users hit this in five minutes, you still need to count across the full dataset or check metrics. A single log line does not convey incident scale.

Structured logs use stable fields so search tools can filter by `event`, `service`, or trace ID. JSON is one representation; structuredness also depends on consistent field names, types, and semantics. Refer to [OpenTelemetry — Logs](https://opentelemetry.io/docs/concepts/signals/logs/).

### 2.2. Log Levels and Details to Record

One way to choose levels in an application:

| Level | Intended meaning in examples |
| --- | --- |
| `DEBUG` | Diagnostic details, such as which branch of a handler was selected |
| `INFO` | Normal events worth tracking, such as completing a task |
| `WARN` | Anomaly requiring attention where the system can still continue or recover |
| `ERROR` | Failed operation that requires investigation |

The development team should agree on level conventions. The number of `ERROR` lines does not automatically equal the number of failed HTTP requests: one request may log multiple errors, or an exception may be handled into a business outcome.

In Spring Boot with default starters, Logback is the preconfigured logging system. You can use SLF4J in application code:

~~~java
logger.info("event=checkout.accepted channel={}", channel);
~~~

This statement sits inside a method and assumes `logger` and `channel` are already declared. The `{}` placeholder passes values using the logging library’s mechanism. When logging an exception, pass the exception object itself to preserve the call stack trace:

~~~java
logger.error("event=checkout.failed", exception);
~~~

Log level configuration controls which records are actually emitted. See [Spring Boot 3.3 — Logging](https://docs.spring.io/spring-boot/3.3/reference/features/logging.html).

### 2.3. Value and Limits

Logs are well suited when you need to know **what event occurred** and **what the specific context was**. However, what was never logged usually cannot be recovered merely by raising log levels after an incident.

Prioritize meaningful events and necessary fields. Never log passwords, access tokens, or full payment data. Order IDs or user information must also be reviewed against purpose, access control, and retention; they are not automatically safe just because we call them “context”.

## 3. Metrics: Measuring Scale and Trends

### 3.1. From Many Executions to Aggregated Numbers

Metrics represent measurements during runtime, usually aggregated and stored over time—for example, request counts, error counts, memory in use, or processing duration.

Identifying information for a metric series typically consists of a measurement name and descriptive tags. For example, measuring request counts split by HTTP method or response status. When reading metrics, always check **the unit, time interval, and set of requests included**. See [OpenTelemetry — Metrics](https://opentelemetry.io/docs/concepts/signals/metrics/).

Three common types in Micrometer:

| Type | Used to know | Example |
| --- | --- | --- |
| `Counter` | How many times an event was recorded | Number of accepted tasks |
| `Gauge` | Value at the moment of observation | Number of items waiting in a queue |
| `Timer` | Count and total duration of measured operations | Call count and request processing duration |

A `Counter` accepts positive increments; when analyzing it, account for process lifecycle and restarts. Rate of increase over an interval is usually more useful than a standalone cumulative total. Refer to [Micrometer — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html).

A `Timer` already provides count and total time, so you do not need an extra counter just to recount the exact events the timer already measured. Whether percentiles or histograms are available depends on configuration and the receiving system. Refer to [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html).

### 3.2. Reading Metrics for the Right Question

Suppose **within the same five-minute window**, an API route had 1,000 completed requests, of which 20 returned 5xx responses:

~~~text
5xx rate = 20 / 1,000 = 2%
~~~

The denominator here is total requests in the window under review, not total requests since application startup. Nor should you automatically equate 5xx rate with every business failure: a rejected transaction might be represented with a different status depending on the API contract.

Another example has ten processing times, in milliseconds:

~~~text
10, 10, 10, 10, 10, 10, 10, 10, 10, 910
Mean = 100 ms
~~~

The mean hides the fact that one request took 910 ms. When caring about slow user experiences, inspect the distribution and appropriate percentiles. For instance, p95 describes the threshold covering roughly 95% of observations in the computed set/window; it is not “95% of the mean”. Estimation methods depend on tooling and configuration.

When aggregating across multiple hosts, preserve proper weighting. Host A has 100 requests averaging 10 ms; Host B has 900 requests averaging 110 ms. The overall mean is:

~~~text
(100 × 10 + 900 × 110) / 1,000 = 100 ms
~~~

Taking a simple average of 10 and 110 would give 60 ms and mislead your conclusion. Likewise, do not average per-host p95 values and call that the system-wide p95.

### 3.3. Limits of Metrics

Metrics help detect rising error rates or latency, yet an aggregated series usually does not preserve the full story of individual requests. From a “2% error” chart alone, you cannot conclude whether the error stems from an SQL query, a payment provider, or a configuration change.

That is when you pivot to traces or logs inside the exact anomalous time window.

## 4. Traces: Following One Execution Through Stages

### 4.1. Trace, Span, and Parent–Child Relationships

A **trace** describes one monitored execution. A **span** represents a stage with start and end timestamps and associated context.

`traceId` links spans belonging to the same trace; `spanId` identifies each span. Parent–child relationships show which stage ran within the context of another stage. Traces remain useful inside a monolith when you need visibility into internal steps, not only across multi-service architectures. See [OpenTelemetry — Traces](https://opentelemetry.io/docs/concepts/signals/traces/).

Hypothetical trace tree example:

~~~text
checkout: HTTP processing            800 ms
├── request validation                10 ms
├── call payment service             730 ms
│   └── payment: request handling    700 ms
└── save result                       40 ms
~~~

Spans must actually be instrumented to appear; the tree above illustrates how to read one, not a claim that Actuator creates all those steps automatically.

In the example, investigate the payment branch first because it accounts for most of the request duration. You cannot yet conclude code inside the payment service is the root cause: inspect child spans, dependency details, and corresponding logs.

Do not sum every duration in the tree. Child spans sit inside their parent span’s time range; stages can also overlap when running in parallel. “Call payment service” and “payment: request handling” are not two independent durations to add together.

### 4.2. Why Is Context Propagation Needed?

A receiving service needs the trace context from the caller. **Context propagation** connects stages into the same trace; with W3C Trace Context, context is carried via the `traceparent` header.

When a call fails to propagate or restore context properly, the receiver may start a separate trace. The data still exists, but the path looks split in two. Switching threads or handling work asynchronously also requires proper context propagation. See [OpenTelemetry — Context propagation](https://opentelemetry.io/docs/concepts/context-propagation/).

### 4.3. Traces May Not Capture Every Request

Sampling selects a subset of traces to store or export, helping control cost. Not finding a trace does not prove the request never happened: it might not have been sampled, might lack instrumentation, might have failed to export, or might have been queried in the wrong time window.

Distributed traces also differ from **exception stack traces**. A stack trace describes the call stack of an exception; a distributed trace describes the stages of an execution and can exist even when no exception occurred.

## 5. Linking the Three Signals

### 5.1. Choosing a Starting Signal by Question

| Question | Start with | Follow up with |
| --- | --- | --- |
| When did error rate start rising, and how many requests are affected? | Metrics | Traces/logs within the anomalous window |
| Which stage slowed down a specific request? | Trace | Logs for the suspected stage |
| Why did the application choose the payment-rejection branch? | Logs with business context | Traces and metrics to gauge impact |
| After a fix, did the overall system improve? | Metrics | Representative traces and logs for confirmation |

These are sensible starting points based on the question, not a rigid order for every investigation. If a user already gave you a trace ID, you can open that trace first.

### 5.2. A Complete Investigation Scenario

Suppose the checkout dashboard shows the 5xx rate jumping from 0.2% to 2% after 10:00. An investigation workflow could look like:

1. **Scope with metrics:** check the API route, application version, timestamps, and affected hosts. Compare over the same window and same request set.
2. **Inspect slow/errored traces:** among retained traces, many show the payment branch stretching near the timeout threshold. That gives a lead to inspect this branch.
3. **Search logs by traceId:** related logs record timeouts when calling the same sandbox provider.
4. **Verify the hypothesis:** cross-check configuration, receiver logs, network status, and deployment changes. Coinciding timestamps alone do not prove causality.
5. **Evaluate after remediation:** monitor error rate and latency distribution, then inspect additional representative requests.

A timeout log only shows the logging side observed a timeout. It does not determine for sure whether the receiver processed the request or not; nor is it enough by itself to decide to retry a transaction that could cause side effects.

### 5.3. Linking Does Not Mean Putting traceId in Every Metric Tag

If a log is written while a span is active, the tracing library can place `traceId` and `spanId` into the MDC—the context map used by logging. Spring Boot 3.3 supports printing these correlation IDs when using Micrometer Tracing. Outside an active context, those IDs may not appear. The relationship between logs and traces is explained in [Spring — Observability with Spring Boot 3](https://spring.io/blog/2022/10/12/observability-with-spring-boot-3/).

To propagate traces automatically over HTTP in Spring Boot, build clients from auto-configured builders such as `RestClient.Builder`, `RestTemplateBuilder`, or `WebClient.Builder`. A client instantiated another way does not automatically get the same instrumentation. See [Spring Boot 3.3 — Tracing](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html).

Spring Boot 3.3 defaults tracing sampling probability to 0.1. The property `management.tracing.sampling.probability` takes values from 0 to 1; the test configuration below uses 1.0. See [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html).

## 6. Where Do Actuator and Micrometer Fit?

### 6.1. Separating Component Responsibilities

In a Spring Boot application, you can visualize the data flow as follows:

~~~text
Instrumented application code / libraries
├── Logger → console or file → log collection system
└── ObservationRegistry
    ├── metrics handler → MeterRegistry → metrics system
    └── tracing handler → tracer/exporter → traces system
~~~

**Instrumentation** creates points in code or libraries that record events, measurements, or stages. An **exporter** sends data to a destination; the storage system retains data for searching and analysis.

With Micrometer Observation, handlers receive lifecycle callbacks for each observation. A single observation point can drive both timing measurements and span creation when corresponding handlers are configured. Creating an observation does not automatically write all business logs for you. See [Micrometer — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html).

Actuator provides operational capabilities and integration auto-configuration. It does not replace the full storage, search, or monitoring UI stack:

| Capability | Meaning |
| --- | --- |
| `/actuator/metrics` | Discover and inspect measurements currently recorded by the application |
| `/actuator/prometheus` | Expose metrics in Prometheus format when the registry is present and endpoint is exposed |
| Micrometer Tracing integration | Support creating/exporting traces when matching libraries and config are present |
| Application logger | Emit events actually logged by application code or libraries |

Spring Boot can measure HTTP requests under `http.server.requests`. Do not treat `/actuator/metrics` as a historical repository for the whole system. External metrics systems handle storing time series when deployed appropriately. See [Spring Boot 3.3 — Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

### 6.2. Choosing Tags So Data Remains Usable

**Cardinality**—the number of distinct combinations of tag values—directly affects how many metric series must be tracked. For instance, one measurement with 2 methods, 3 outcomes, and 4 routes can produce up to 24 combinations, even before considering hosts or environments.

If each request adds a distinct `traceId` to metric tags, combinations will keep growing with every request. For detecting errors by API route, use a bounded tag like the path template `/orders/{id}` instead of individual paths `/orders/78421`.

In Micrometer Observation:

- **Low-cardinality key values** are for bounded sets of values and can go into both metrics and traces.
- **High-cardinality key values** are for widely varying values and go into traces rather than becoming metric tags in the standard observation pipeline.

For example, `channel=web/mobile` is a good low-cardinality tag candidate; individual order IDs do not belong in metric tags. Even when stored only in traces or logs, data must still be evaluated for cost and privacy. Refer to [Spring Boot 3.3 — Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

## 7. Demonstration in Spring Boot 3.3.x

This example creates a business observation point, logs inside that observation, and inspects its metric. It runs **inside a Spring Boot 3.3.x project with Gradle configured, dependency version management, and the `bootRun` task available**, using JDK 17 or newer. The `dependencies` snippet below is the portion to add to the project, not a complete `build.gradle`.

### 7.1. Minimal Dependencies and Configuration for Logs and Metrics

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

In `src/main/resources/application.yml` of the test project:

~~~yaml
spring:
  application:
    name: checkout-demo

management:
  endpoints:
    web:
      exposure:
        include: health,metrics
~~~

The example assumes local execution on port 8080, without Spring Security, and with default context path and management port. Expose only the endpoints needed in a test environment; exposing an endpoint over HTTP and authorizing access are two separate concerns. See [Spring Boot 3.3 — Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

### 7.2. One Complete Java File

Place the file at `src/main/java/example/observation/ObservabilityDemoApplication.java`:

~~~java
package example.observation;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ObservabilityDemoApplication {
    private static final Logger logger =
            LoggerFactory.getLogger(ObservabilityDemoApplication.class);

    private final ObservationRegistry registry;

    public ObservabilityDemoApplication(ObservationRegistry registry) {
        this.registry = registry;
    }

    @GetMapping("/demo/checkout")
    public String checkout() {
        return Observation.createNotStarted("shop.checkout", registry)
                .lowCardinalityKeyValue("channel", "web")
                .observe(() -> {
                    logger.info("event=checkout.accepted channel=web");
                    return "ACCEPTED";
                });
    }

    public static void main(String[] args) {
        SpringApplication.run(ObservabilityDemoApplication.class, args);
    }
}
~~~

The method only simulates accepting an operation without calling a bank or creating a real transaction.

`observe` wraps the work being measured. `shop.checkout` is a stable observation name, and `channel=web` is low-cardinality information. The log is written inside the active observation scope. The outer HTTP request and inner business operation are two distinct scopes; do not sum their counts into a single transaction total.

### 7.3. Run and Read the Evidence

In the test project directory, run using the Gradle wrapper:

~~~powershell
.\gradlew.bat bootRun
~~~

In another terminal window:

~~~powershell
curl.exe --silent http://localhost:8080/demo/checkout
~~~

The expected exact response body is:

~~~text
ACCEPTED
~~~

The console prints a message containing `event=checkout.accepted channel=web`. The full log line also depends on timestamp, thread, and log format, so it is not fixed.

After calling the API, inspect the metric:

~~~powershell
curl.exe --silent http://localhost:8080/actuator/metrics/shop.checkout
~~~

The expected JSON result includes the name `shop.checkout` and timing/count measurements. Duration values vary across runs; the count increases if called again. You can cross-check the outer HTTP metric with:

~~~powershell
curl.exe --silent "http://localhost:8080/actuator/metrics/http.server.requests?tag=uri:/demo/checkout"
~~~

Using `curl.exe` avoids confusion with the `curl` alias in some Windows PowerShell versions. The commands above assume a project meeting the stated prerequisites; a standalone Java file cannot be compiled and run with `javac` alone without the Spring/Micrometer classpath.

### 7.4. Adding Tracing to See the Business Stage

To connect the example to a tracing system, add a compatible bridge/exporter pair. For example, using OpenTelemetry and Zipkin:

~~~groovy
dependencies {
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    implementation 'io.opentelemetry:opentelemetry-exporter-zipkin'
}
~~~

Add to the **existing** `management` key, keeping the endpoints configuration intact:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
  zipkin:
    tracing:
      endpoint: http://localhost:9411/api/v2/spans
~~~

The Zipkin receiving endpoint and sampling property are listed in [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html).

This YAML snippet shows the part to merge; do not create two duplicate `management` keys in the same document. Run Zipkin at that address to receive data, then restart the application and call the API again. This is a small test setup with 100% sampling.

Once data is exported successfully, you can find the trace containing the `shop.checkout` business stage inside the HTTP call’s context. Display names of spans may be normalized by the library. You do not need an `/actuator/traces` endpoint to view them; use the configured trace backend. Combining these dependencies and exporters is described in [Spring Boot 3.3 — Tracing](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html).

Merely adding Actuator and running the log/metrics portion above does not configure enough to store and view distributed traces in Zipkin. If you need trace detail down to SQL, external calls, or a background task, each path must be supported by libraries or instrumented with an appropriate observation point.

## 8. Common Misconceptions and How to Self-Check

| Misconception | How to verify |
| --- | --- |
| Having lots of logs means understanding the whole system | Check whether logs carry enough context and whether metrics show scope of impact |
| No ERROR means no failures | Check logging conventions, log levels, API responses, and metrics |
| A low mean means all requests are fast | Inspect distributions, slow outliers, and calculation windows |
| The longest trace immediately points to root cause | Cross-check child spans, logs, and dependencies; duration is a clue |
| Seeing traceId in logs guarantees the trace is stored | Check sampling, export pipeline, query window, and retention |
| Enabling Actuator automatically provides all traces, centralized logs, and UI | Verify instrumentation, integration libraries, and destinations separately |
| Putting per-request IDs into metric tags makes searching easier | Keep IDs in logs/traces where suitable; keep metric tag cardinality bounded |

### Self-Practice

1. Given only “20 errors in five minutes”, state what information is missing to compute the error rate.
2. An API is slow without throwing exceptions. Choose which signal to use for detection and which to use to locate the slow stage.
3. Logs contain a `traceId`, yet no trace is found. State at least two hypotheses and how to verify them.
4. In the Spring Boot example, call the business endpoint three times. Read the `shop.checkout` metric, find the corresponding logs, and if tracing is configured, check the trace backend.
5. Explain why `channel` with a small set of values fits better as a metric tag than `orderId`.

**Comparison hints:** question 1 needs total requests in the same window and the error definition; question 2 can start from latency metrics then inspect traces; question 3 checks sampling, export pipeline, and query range; question 4 distinguishes business invocations from other HTTP requests; question 5 considers tag-combination cardinality rather than just the field name.
