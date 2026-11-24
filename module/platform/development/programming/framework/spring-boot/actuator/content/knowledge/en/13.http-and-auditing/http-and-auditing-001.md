# Distinguishing HTTP Exchange History from Access Logs, Metrics, and Distributed Tracing

## An HTTP request can leave multiple types of evidence

Suppose a customer reports that an order API call was slow. You might see the response status code and processing time in HTTP exchange history, a line in the access log, a latency spike on a metrics chart, and a trace passing through the order, inventory, and payment services.

These pieces of data relate to the same activity but capture **different perspectives**. Enabling one feature does not mean you have full coverage of the other three.

In Spring Boot 3.3, four concepts need to be distinguished:

- **HTTP exchanges**: request–response records stored in an `HttpExchangeRepository`, readable via the `httpexchanges` endpoint.
- **Access log**: access records emitted by an HTTP server or proxy according to a configured format and retention policy.
- **Metrics**: counts, timings, and distributions aggregated across defined tags.
- **Distributed tracing**: units of work linked into traces to follow the path across multiple components or services.

Start with the question you need to answer, then choose the appropriate evidence.

## 1. Comparison by question, data unit, and scope

| Data source | Appropriate question | Data unit | Typical scope | Limitations to remember |
| --- | --- | --- | --- | --- |
| HTTP exchanges | "Which requests did the application just receive and how did it respond?" | A request–response pair | One application/instance, depending on the repository | A bounded buffer is not a complete history |
| Access log | "At this ingress point, which requests passed through, what status was returned, and how long did they take?" | An access record in the log format | Proxy, HTTP server, or collected log set | Does not describe internal processing steps on its own |
| Metrics | "How did traffic, error rate, and latency change over a time window?" | Measurements/time series by tag set | Instance or entire service when aggregated properly | Does not preserve individual request identity |
| Distributed tracing | "Where did a single execution pass through and which step was slow?" | A trace composed of linked spans | Components with instrumentation and context propagation | Sampling or missing instrumentation can cause missing traces |

`Instrumentation` is code or a library attached to a processing point to emit observability data. An uninstrumented component creates a gap; having no data does not mean no activity occurred.

Examples of choosing a source:

- Want to know the API p99 over 15 minutes: start from metrics with suitable distribution data.
- Want to find the response code of a specific call: check the access log or HTTP exchange records if still retained.
- Want to know why that call was slow in the payment service: inspect the trace and related logs.
- Want to quickly check the headers of a recently completed request in a development environment: HTTP exchanges are often convenient.

p99 is the 99th percentile of a latency distribution, not the duration of a request with a "p99 code".

## 2. HTTP exchanges: inspecting recent request–response pairs

### What does a record keep?

The `HttpExchange` model describes the start timestamp, request, response, time taken, and optional extra details depending on configuration, such as principal or session. The request can include method, URI, and selected headers; the response includes status and selected headers.

Example excerpt of a synthetic record to inspect the structure:

```json
{
  "exchanges": [
    {
      "timestamp": "2024-01-01T00:00:03Z",
      "request": {
        "uri": "https://example.test/orders/104",
        "method": "GET",
        "headers": {}
      },
      "response": {
        "status": 404,
        "headers": {}
      },
      "timeTaken": "PT0.1S"
    }
  ]
}
```

`PT0.1S` is a duration representation of 0.1 seconds. Do not interpret it as a timestamp or 0.1 milliseconds. The actual set of fields also depends on the recording configuration. This standard model does not provide a default copy of the full request body, response body, SQL statements, and stack traces. [Spring Boot 3.3: httpexchanges API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/httpexchanges.html).

Duration at the HTTP recording layer also does not inherently include all time perceived by the user: DNS, connection setup, time at a CDN/proxy, and network transit belong to other observation points.

### The repository governs storage; the endpoint only provides read access

Spring Boot enables recording via auto-configuration when a suitable `HttpExchangeRepository` bean is present. A configuration for development might look like:

```java
package example.observability;

import org.springframework.boot.actuate.web.exchanges.HttpExchangeRepository;
import org.springframework.boot.actuate.web.exchanges.InMemoryHttpExchangeRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class HttpExchangeConfiguration {

    @Bean
    HttpExchangeRepository httpExchangeRepository() {
        var repository = new InMemoryHttpExchangeRepository();
        repository.setCapacity(100);
        return repository;
    }
}
```

This is a configuration snippet added to a Spring Boot application with Actuator and the corresponding web stack; it is not a standalone Java program.

`InMemoryHttpExchangeRepository` keeps the **most recent 100 exchange pairs** by default. Spring recommends using this simple repository for development; production environments need a proper observability solution or a repository designed for storage requirements. [Spring Boot 3.3: Recording HTTP Exchanges](https://docs.spring.io/spring-boot/3.3/reference/actuator/http-exchanges.html).

Three concerns must be separated:

1. **Recording**: a repository exists and the recording mechanism is active.
2. **Retention**: how many records the repository keeps, for how long, and where.
3. **Access over HTTP**: whether the endpoint is exposed and the caller has permission to read it.

Exposing `httpexchanges` alone does not create a history store. Conversely, disallowing remote reading of the endpoint does not necessarily disable recording. The property `management.httpexchanges.recording.enabled=false` controls recording; `management.httpexchanges.recording.include` selects which categories of information are recorded. Exposure and authorization policies are separate layers.

### Limitations of an in-memory buffer

With an in-memory repository:

- Restarting the process loses the held records.
- Each instance has its own buffer and does not automatically merge into a cluster-wide history.
- Older records are evicted when capacity is exceeded.
- Capacity is measured in record count, not a fixed window like "10 minutes".
- Record count is not a hard byte limit: long headers and URIs still increase memory usage.

If there are 100 slots and the recording rate is around 200 requests per second, the retained history may correspond to only about **0.5 seconds** under those conditions. This is a traffic-based estimate, not a retention-time guarantee.

Reading `/actuator/httpexchanges` can itself create another exchange recorded after the read request completes. Do not rely on the assumption that the observation operation is always excluded from the observed dataset.

## 3. Access log: recording traffic at an ingress point

### Access logs differ from business logs

An access log typically records method, path, status, byte count, and duration at that server or proxy. It is not like a log line actively written by the business layer such as "order has been confirmed".

With embedded Tomcat, an example configuration in a Spring Boot application:

```yaml
server:
  tomcat:
    basedir: ./runtime-tomcat
    accesslog:
      enabled: true
      pattern: '%t method=%m path=%U status=%s bytes=%b elapsed_us=%D'
```

This configuration is for **Tomcat** and does not apply verbatim to Jetty, Undertow, or Reactor Netty. Setting an explicit base directory makes the storage location clear; the example above places logs in the `logs` directory under `runtime-tomcat`. Rotation, collection, and long-term retention still require separate policies. [Spring Boot 3.3: Configure Access Logging](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html#howto.webserver.configure-access-logs).

In this Tomcat pattern, `%U` is the request path, `%s` is the status, `%b` is the number of response body bytes or `-` when zero, and `%D` uses **microseconds**. Do not read `elapsed_us=100000` as 100,000 milliseconds; it is 100 milliseconds. Do not infer another server's unit from the same symbol. [Tomcat 10.1: Access Log Valve](https://tomcat.apache.org/tomcat-10.1-doc/config/valve.html#Access_Log_Valve).

### The observation point determines what the log proves

A request may traverse:

```text
Browser -> CDN/proxy -> Tomcat -> Spring Security -> controller -> other service
```

If the CDN returns an error before forwarding to the application, Tomcat may have no corresponding record. If the application returns 200 but the proxy connection fails, the status seen by the user may differ from the status the application logged.

Therefore, you need to know where the log comes from, what point in time the timestamp represents, and which processing segment the duration covers. Do not add proxy log line counts and application log line counts together and treat the sum as unique requests; the same call can appear in both places.

Access logs can be kept longer than an in-memory HTTP buffer if there is durable storage and a collection pipeline. However, "being a log" does not automatically guarantee completeness or immutability: files can be rotated, lost when a container is replaced, filtered, or fail to be shipped to a central store.

Details missing from the format also cannot be queried retroactively by changing the log level after an incident.

## 4. Metrics: aggregating to see trends and scale

### From many requests to a group of measurements

Spring Boot uses Micrometer for metrics. With the corresponding default HTTP instrumentation, the server-side meter name is typically `http.server.requests`; tag sets partition measurements along dimensions such as method, route pattern, or status. [Spring Boot 3.3: HTTP metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.supported.spring-mvc).

A timer can provide the recorded count and total time, along with additional measurements depending on configuration and backend. For example, given four recorded durations `10, 20, 70, 100 ms`:

```text
count = 4
total = 200 ms
mean  = 200 / 4 = 50 ms
```

From these numbers, you know the average of the recorded set. You do not know which customer's request took 100 ms, nor can you compute a reliable p99 from count and total alone. Histograms or percentiles require appropriate configuration and aggregation. [Micrometer: Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html).

A metric may be updated when a request completes and then read or pushed periodically. It is not a JSON list of every request. A time-series backend helps inspect long-term fluctuations, but data scope still depends on instrumentation, filters, export intervals, and retention time.

### Tags must have bounded value counts

Two requests:

```text
GET /orders/101
GET /orders/102
```

should normally be aggregated under the route `/orders/{id}`, rather than creating a separate time series for each order ID.

The number of distinct tag combinations is called **cardinality**. Putting `requestId`, `traceId`, email addresses, or URIs with unbounded IDs into tags can cause time-series counts to grow very rapidly. Identifiers needed for individual cases should live in detailed data with an appropriate policy, not be turned into default metric tags.

Having few metric tags does not mean "lacking functionality". Aggregating across controlled groups is precisely what enables answering large-scale questions at reasonable cost.

### Error rate and latency need the same data scope

If you want to compute the 5xx rate, you must divide the number of 5xx requests by the total requests over the **same time window, same service, and same selected set of routes/instances**.

You also need to clarify:

- Policy on whether 4xx counts as an error under the service level objective (SLO).
- How counter resets on process restart are handled.
- Whether health checks, Actuator requests, and internal traffic are included.
- Whether measurements come from all instances or just one instance.
- Whether filters or missing exported data skew the observed sample.

Do not take a simple average of two p99 values or two means when the two groups have different request counts. For the overall mean, divide total duration by total count; for an overall percentile, you need distribution data that can be aggregated using the chosen mechanism.

## 5. Distributed tracing: linking steps of a single execution

### What roles do traces and spans play?

A **span** describes a unit of work with a start/end point and associated context. A **trace** links spans along an execution path, typically using a trace ID along with parent–child relationships or appropriate links.

Conceptual diagram example of a single order placement:

```text
Trace T
└─ Order API
   ├─ call inventory service
   │  └─ query stock data
   └─ call payment service
      └─ call payment gateway
```

The diagram only appears in full if the points to be observed are actually instrumented and propagate context. Enabling tracing on the ingress API does not automatically create spans for every SQL statement, every Java method, or every external service. [OpenTelemetry: Traces and Spans](https://opentelemetry.io/docs/concepts/signals/traces/).

From a trace, you can identify slow steps, retries, and relationships between incoming and outgoing calls. If two branches run in parallel, do not sum the durations of all spans and treat that as user wait time: intervals can overlap.

### Context must be propagated across boundaries

To link spans across the network, the caller must inject context and the receiver must extract it in a compatible format. Similarly, when handing off to a queue or asynchronous task, context must be preserved or linked using the library's mechanism.

Merely logging a string named `traceId` across multiple services does not create a valid relational trace. An application's `requestId` is also not inherently a trace ID. [OpenTelemetry: Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/).

In Spring Boot 3.3, tracing requires the corresponding dependencies and configuration for Micrometer Tracing along with a tracer/exporter. For HTTP clients, use builders auto-configured by Boot so they receive instrumentation and context propagation; creating clients outside that configuration path can break traces.

### Sampling makes traces different from traffic counters

Tracing commonly uses **sampling** to limit data volume. The default documented by Spring Boot 3.3 is 10% sampling for tracing; the actual policy must still be checked in the active system and context propagation path. [Spring Boot 3.3: Tracing](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html).

The absence of a trace for a request can result from not being sampled, missing instrumentation, broken context propagation, export errors, or retention expiration. It does not prove the request never happened.

A request not being exported as a trace also does not mean HTTP metrics must exclude that request. These are two signals with different collection mechanisms. Do not treat the number of visible traces as total traffic and compute a system-wide error rate while ignoring sampling.

Increasing sampling to 100% during testing makes observation easier but still does not guarantee zero data loss in the exporter/backend. Production decisions must weigh traffic volume, cost, and investigative purpose.

## 6. Java experiment: the two latest records are not the sum of four calls

The experiment below uses `InMemoryHttpExchangeRepository` and Micrometer's `SimpleMeterRegistry` directly. It generates synthetic data and records the given durations; **it does not open an HTTP server, send four real requests, or automatically generate access logs or traces**.

Inputs:

| Simulated request | Status | Duration |
| --- | --- | --- |
| `/orders/101` | 200 | 10 ms |
| `/orders/102` | 200 | 20 ms |
| `/orders/103` | 500 | 70 ms |
| `/orders/104` | 404 | 100 ms |

The repository is given only two slots; metrics are recorded for all four calls.

Create a separate test directory with the following `pom.xml` to include Spring Boot 3.3.x and Micrometer dependencies. This is a plain Java program and does not need a `@SpringBootApplication` class:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>http-signals-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-core</artifactId>
        </dependency>
    </dependencies>
</project>
```

Save the code below at `src/main/java/HttpSignalsDemo.java`:

```java
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.net.URI;
import java.time.Duration;
import java.time.Instant;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import org.springframework.boot.actuate.web.exchanges.HttpExchange;
import org.springframework.boot.actuate.web.exchanges.InMemoryHttpExchangeRepository;

public class HttpSignalsDemo {
    public static void main(String[] args) {
        var repository = new InMemoryHttpExchangeRepository();
        repository.setCapacity(2);

        var registry = new SimpleMeterRegistry();
        try {
            int[] statuses = {200, 200, 500, 404};
            long[] durationsMs = {10, 20, 70, 100};
            Instant start = Instant.parse("2024-01-01T00:00:00Z");

            for (int i = 0; i < statuses.length; i++) {
                var request = new HttpExchange.Request(
                        URI.create("https://example.test/orders/" + (101 + i)),
                        null, "GET", Map.of());
                var response = new HttpExchange.Response(statuses[i], Map.of());
                var exchange = new HttpExchange(
                        start.plusSeconds(i), request, response,
                        null, null, Duration.ofMillis(durationsMs[i]));
                repository.add(exchange);

                Timer.builder("demo.http.requests")
                        .tags("method", "GET", "uri", "/orders/{id}",
                                "status", Integer.toString(statuses[i]))
                        .register(registry)
                        .record(Duration.ofMillis(durationsMs[i]));
            }

            System.out.println("exchanges.retained=" + repository.findAll().size());
            for (HttpExchange exchange : repository.findAll()) {
                System.out.println("exchange=" + exchange.getRequest().getUri().getPath()
                        + " status=" + exchange.getResponse().getStatus());
            }

            var timers = registry.find("demo.http.requests").timers();
            long count = timers.stream().mapToLong(Timer::count).sum();
            double totalMs = timers.stream()
                    .mapToDouble(timer -> timer.totalTime(TimeUnit.MILLISECONDS)).sum();
            long serverErrors = timers.stream()
                    .filter(timer -> timer.getId().getTag("status").startsWith("5"))
                    .mapToLong(Timer::count).sum();

            System.out.println("metrics.count=" + count);
            System.out.printf(Locale.ROOT, "metrics.total.ms=%.1f%n", totalMs);
            System.out.printf(Locale.ROOT, "metrics.mean.ms=%.1f%n", totalMs / count);
            System.out.println("metrics.5xx=" + serverErrors);
            System.out.printf(Locale.ROOT, "metrics.5xx.percent=%.1f%n",
                    100.0 * serverErrors / count);
        } finally {
            registry.close();
        }
    }
}
```

With JDK 17 or later and Maven, compile and gather dependencies:

```bash
mvn -q compile dependency:copy-dependencies
```

Run on Windows PowerShell:

```powershell
java -cp 'target/classes;target/dependency/*' HttpSignalsDemo
```

On Linux/macOS, use `:` to separate classpath entries:

```bash
java -cp 'target/classes:target/dependency/*' HttpSignalsDemo
```

Maven needs access to the dependencies if they are not already cached. These commands are only for the test project just created.

Exact stdout:

```text
exchanges.retained=2
exchange=/orders/104 status=404
exchange=/orders/103 status=500
metrics.count=4
metrics.total.ms=200.0
metrics.mean.ms=50.0
metrics.5xx=1
metrics.5xx.percent=25.0
```

Explanation:

- The repository keeps the two most recent calls and returns them newest-first under the default configuration.
- Two records being evicted from the repository do not cause measurements already recorded in the registry to disappear.
- The total is 200 ms and the mean is 50 ms because metrics aggregate all four calls.
- There is one 5xx call out of four, so the 5xx rate of the input set is 25%.
- If you look only at the two retained records, you see one 5xx out of two calls, i.e., 50% **of the most recent two calls**. It is not representative of all four calls.
- 404 is not counted as 5xx. If policy requires tracking 4xx, that group must be defined separately.

The name `demo.http.requests` is a timer explicitly created by the program for illustration, not a claim that Boot's automatic HTTP instrumentation is enabled. The `uri=/orders/{id}` tag demonstrates route grouping; detailed URIs remain in the retained exchange records.

The program intentionally records predetermined durations instead of measuring `Thread.sleep`, so arithmetic results are reproducible. Do not use these numbers as a performance benchmark of the repository or a web application.

## 7. Combining signals when investigating an incident

Suppose metrics report rising latency on the `/checkout` route, yet only a few customers report errors. A well-grounded investigation flow is:

1. Select the time window and identify the affected service, route, and instances from metrics.
2. Locate specific requests in the access log, checking status, duration, and correlation IDs if present.
3. Use the trace ID to open the stored trace and see which step was slow or had retries.
4. Read business logs related to that span/trace to understand the error context.
5. If reproducing in a development environment, use HTTP exchanges to inspect request–response pair details still in the repository.

Each step adds evidence; an upward chart alone does not prove the root cause is in the database. A slow span must also be read in the context of uninstrumented segments.

To correlate signals, timestamps/time zones, service and instance identifiers, and correlation ID propagation must be consistent. Spring Boot supports injecting trace/span IDs into logs when using Micrometer Tracing, but do not assume every access log on a proxy or server already has those same fields.

Diagnostic context of the logger (MDC) and tracing context also do not automatically cross every thread boundary or executor outside supported configuration. When seeing logs "lose the trace ID", inspect the context propagation path rather than randomly injecting a new ID to make lines look alike.

### Why can counts and durations differ across sources?

| Situation | Observable consequence |
| --- | --- |
| Request blocked at proxy | Proxy has a log entry; application has no corresponding exchange |
| HTTP buffer is full | Metrics still reflect recorded calls, but older exchanges are gone |
| Tracing samples requests | Logs/metrics exist, but no stored trace is found |
| Call is retried | One user action can generate multiple requests and spans |
| Data read from different instances | Local buffers and local counters do not match |
| Two sources measure two different segments | Durations differ even for the same call |
| Collector/exporter or ingestion pipeline fails | Backend data is missing relative to what occurred in the process |

Before concluding which source is "wrong", check the scope, observation point, time window, and retention/sampling policy of each source.

## 8. HTTP history does not automatically become an audit log

This knowledge area relates to HTTP and auditing, yet a request returning `200` is not enough to prove a business change was executed properly.

For example, "who changed which account's limit, from what amount to what amount, and with what outcome?" requires a business event with a clear actor, target, action, timestamp, and outcome. A line `POST /limits -> 200` does not provide all of that.

Spring Boot has a dedicated auditing mechanism with `AuditEventRepository`. When configured appropriately with Spring Security, events such as authentication success/failure or access denied can be published; business events must be emitted according to application design. This is not auto-generated from `HttpExchangeRepository`. [Spring Boot 3.3: Auditing](https://docs.spring.io/spring-boot/3.3/reference/actuator/auditing.html).

If long-term evidence is needed, you must design durable storage, tamper/deletion controls, access permissions, and appropriate retention periods. A buffer keeping recent records, ordinary log files, or sampled traces do not automatically satisfy those requirements.

## 9. Controlling data and cost per source

| Source | Common risks | Control direction |
| --- | --- | --- |
| HTTP exchanges | URI/header/principal may be sensitive; buffer grows with record size | Select recorded data, limit capacity, and restrict endpoint read access |
| Access log | Query strings, cookies, or headers added to the pattern can leak data; files grow continuously | Limit fields, rotate, collect, and retain per policy |
| Metrics | High-cardinality tags explode time series; personal identifiers in tags | Use bounded value groups; avoid per-request/per-user identifiers |
| Tracing | Span attributes/baggage can carry sensitive data; high trace volume | Choose attributes carefully, propagate context intentionally, sample, and secure the backend |

Do not assume Actuator's configuration-value sanitization automatically masks every URI, log, or span attribute. In particular, a token in a query string can leak into multiple sources even when the Authorization header is not recorded.

Exposing a management endpoint is an access-surface decision, not a way to make data inherently safe. Allowing only authorized readers and minimizing data at collection time complement each other.

## 10. Self-check on choosing evidence

1. Need the service-wide 5xx rate over 30 minutes. Why are the last 100 exchanges of one instance insufficient?
2. A customer has a request ID and a specific timestamp. Where should you look first to match that call, and where next to view the path across services?
3. No trace is found for a request, yet the access log shows status 500. What possibilities need to be checked?
4. In the experiment, why does metrics count equal 4 while the repository only has 2 records?
5. Why should you not put a trace ID into a tag of `http.server.requests`?
6. When needing to know who changed a business permission, why do an HTTP 200 status and a successful trace still not replace an audit event?

You have distinguished the four sources when you can clearly state the **data unit, observation point, retention model, and question each source answers**, and combine them without turning missing data or aggregated data into detailed evidence that was never recorded.
