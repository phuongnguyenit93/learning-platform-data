# Metrics Endpoint

When a dashboard alerts on rising latency, the operations team needs to verify which meters are being recorded on a Spring Boot instance, which tags exist, and what the current measurements look like. The Actuator Metrics endpoint provides an HTTP interface to list meter names, read a specific meter, and filter by tags. It is a useful diagnostic tool during development and operations.

The **Metrics endpoint** lesson belongs to the **Actuator and Management** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module teaches how to set up observability for Spring Boot with Micrometer Observation, metrics, logs, and distributed tracing; understanding context propagation, tags/cardinality, exporters, sampling, and correlating signals to investigate errors, latency, and application behavior in real environments.

> **Core takeaway:** `GET /actuator/metrics` lists meter names; `GET /actuator/metrics/{requiredMetricName}` reads a specific meter and its tag values; query parameter `tag=KEY:VALUE` filters by tag. The endpoint reads the current application process's `MeterRegistry`, returns diagnostic JSON, and is neither a Prometheus exposition endpoint nor a historical time-series store.

## 1. Learning Objectives

After this lesson, you will be able to:
1. Explain the role of the Actuator Metrics endpoint.
2. Enable Actuator and configure base path, port, and endpoint exposure.
3. List meter names and query a specific meter.
4. Filter meters using tag keys/values.
5. Read measurements of Counter, Gauge, Timer, and DistributionSummary.
6. Understand why histogram/percentile fields may not appear.
7. Distinguish the Metrics endpoint from the Prometheus scrape endpoint.
8. Protect the endpoint with authentication, network policies, and minimal exposure.
9. Investigate missing meters, mismatched tags, and growing cardinality.
10. Know when a dashboard, exporter, or tracing backend is needed.

## 2. What Is the Actuator Metrics Endpoint?

Spring Boot Actuator provides the `metrics` endpoint to read meters registered in the Micrometer `MeterRegistry`. Each meter has a name, type, measurements, and optionally tags.

| HTTP request | Purpose |
|---|---|
| GET /actuator/metrics | List meter names |
| GET /actuator/metrics/{requiredMetricName} | Read a meter by name |
| GET /actuator/metrics/{requiredMetricName}?tag=key:value | Filter meter by tag |
| GET /actuator | Discovery document if links are enabled and exposed |

The endpoint only reads data from the current application process/registry. It does not directly query databases, Prometheus, an OTLP Collector, or metrics from other services.

For example, the `http.server.requests` meter may come from HTTP server instrumentation; `jvm.memory.used` from a JVM binder; `app.orders.created` registered by the application itself.

## 3. Adding Spring Boot Actuator

With Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

With Maven, add `spring-boot-starter-actuator` and rely on Spring Boot dependency management to select compatible versions.

Actuator provides endpoint infrastructure and integrations. Which meters appear still depends on auto-configuration, binders, `MeterRegistry`, instrumentation for MVC/HTTP clients/databases/messaging/JVM, and custom meters. Merely adding Actuator does not automatically give every method metrics; instrumentation or a binder must create the meter.

## 4. Configuring Endpoint Exposure

Actuator endpoints can be exposed over HTTP or JMX. Configuring HTTP exposure:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
~~~

If using the Prometheus registry and a scrape endpoint is needed, expose `prometheus` explicitly:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
~~~

Expose only needed endpoints. Avoid wildcard `*` in production without evaluating every endpoint and security policy.

The default base path is usually `/actuator`; it can be changed:

~~~yaml
management:
  endpoints:
    web:
      base-path: /manage
~~~

When the base path changes, the Metrics endpoint becomes `/manage/metrics`. If the management server runs on a separate port, URLs must use that port. Verify the actual configuration rather than assuming it always uses the application port.

## 5. Listing Meter Names

Send a request:

~~~http
GET /actuator/metrics
Accept: application/vnd.spring-boot.actuator.v3+json
~~~

Example response:

~~~json
{
  "names": [
    "application.ready.time",
    "http.server.requests",
    "jvm.memory.used",
    "process.cpu.usage",
    "system.cpu.usage"
  ]
}
~~~

The actual list depends on runtime, dependencies, and instrumentation. Not every application will have the exact meters in the example.

The names list helps discover meter names; it does not return full time series or history. A meter may not appear yet if the code path that creates it has not run or its binder is not enabled.

### 5.1 Common Meter Groups

| Group | Example Meter | Meaning |
|---|---|---|
| HTTP server | http.server.requests | Count and handling duration of HTTP requests |
| HTTP client | http.client.requests | Outbound HTTP exchanges |
| JVM memory | jvm.memory.used | Memory in use by area/tag |
| JVM threads | jvm.threads.live | Number of live threads |
| CPU | process.cpu.usage, system.cpu.usage | Process or host CPU |
| Data source | jdbc.connections.active | Active connections if binder is supported |
| Executor | executor.active | Active tasks if executor is instrumented |
| Application | app.orders.created | Custom business meter |

Names and tags depend on version, registry, and integration. Use the endpoint to confirm a meter exists before writing queries.

## 6. Reading a Specific Meter

Example:

~~~http
GET /actuator/metrics/http.server.requests
~~~

Abbreviated example response:

~~~json
{
  "name": "http.server.requests",
  "description": "Duration of HTTP server request handling",
  "baseUnit": "seconds",
  "measurements": [
    {"statistic": "COUNT", "value": 1250.0},
    {"statistic": "TOTAL_TIME", "value": 42.7},
    {"statistic": "MAX", "value": 1.82}
  ],
  "availableTags": [
    {"tag": "method", "values": ["GET", "POST"]},
    {"tag": "status", "values": ["200", "404", "500"]},
    {"tag": "outcome", "values": ["SUCCESS", "CLIENT_ERROR", "SERVER_ERROR"]}
  ]
}
~~~

These figures are illustrative data. A Timer typically provides `COUNT`, `TOTAL_TIME`, and `MAX`; distribution statistics may add more fields depending on configuration and registry. Do not assume every meter has the same measurements.

### 6.1 Meaning of Measurements

- `COUNT`: number of recorded events.
- `TOTAL_TIME`: total recorded duration, in the base unit.
- `MAX`: maximum value in the window/ring buffer maintained by the meter implementation.
- `VALUE`: current value of a Gauge or FunctionCounter depending on meter type.
- Other distribution statistics: depending on meter type and configuration.

For a Timer, `baseUnit` is typically `seconds` when returned through Actuator, but always read `baseUnit` and `statistic` rather than assuming.

### 6.2 Available Tags

`availableTags` lists tag keys and values recorded for the meter. It helps discover available dimensions for writing queries. It is not a list of tag values across all services or all points in time in the system; it reflects the registry the endpoint is currently reading.

## 7. Filtering Meters by Tag

Use the `tag` query parameter:

~~~http
GET /actuator/metrics/http.server.requests?tag=method:GET
~~~

Multiple conditions can be passed by repeating the query parameter:

~~~http
GET /actuator/metrics/http.server.requests?tag=method:GET&tag=status:200
~~~

Example investigating POST returning 500:

~~~http
GET /actuator/metrics/http.server.requests?tag=method:POST&tag=status:500
~~~

Each tag filter narrows results by the corresponding key/value. If a tag key/value does not exist or no meter matches, the endpoint may return a not-found error for matching meters. Check `availableTags` first for exact tag names and values.

### 7.1 Encoding Query Parameters

Some tag values contain special characters, spaces, or characters requiring URL encoding. HTTP clients/browsers must encode query parameters properly. Do not concatenate unencoded/unvalidated user input directly into management endpoint URLs.

### 7.2 Tag Filtering Is Not PromQL

Actuator tag filters only select meters by tag values. They do not support aggregation, `rate`, histogram quantiles, or cross-series math like PromQL. Use Prometheus or a metrics backend for time-series queries and complex calculations.

## 8. Counter, Gauge, Timer, and DistributionSummary

| Meter Type | Observed Data | How to Interpret |
|---|---|---|
| Counter | COUNT | Total count of counter increments |
| Gauge | VALUE | Value at the moment of reading |
| Timer | COUNT, TOTAL_TIME, MAX and distribution stats if enabled | Operation count and duration |
| DistributionSummary | COUNT, TOTAL and MAX/percentiles if configured | Distribution of sizes/values |
| FunctionCounter | COUNT | Cumulative value read from a function |
| LongTaskTimer | ACTIVE_TASKS, DURATION | Running tasks and active duration per implementation |

A Counter cannot decrease; a Gauge can increase or decrease. A Timer records durations of events; a DistributionSummary records values that are not necessarily durations.

Example reading a gauge:

~~~http
GET /actuator/metrics/jvm.memory.used?tag=area:heap
~~~

Example reading a custom counter:

~~~http
GET /actuator/metrics/app.orders.created
~~~

If the meter has no `area` tag or `app.orders.created` has not been registered yet, the request will not return the expected result. Check `names` and `availableTags` first.

## 9. Percentiles and Histograms

Not every Timer automatically includes percentiles or histogram buckets. Distribution statistics must be configured on the meter or corresponding registry.

Example enabling a percentile histogram for a meter via `MeterFilter`:

~~~java
@Bean
MeterFilter httpServerHistogram() {
    return new MeterFilter() {
        @Override
        public DistributionStatisticConfig configure(
                Meter.Id id,
                DistributionStatisticConfig config) {
            if (id.getName().equals("http.server.requests")) {
                return DistributionStatisticConfig.builder()
                        .percentilesHistogram(true)
                        .build()
                        .merge(config);
            }
            return config;
        }
    };
}
~~~

This example illustrates registry configuration; verify your application's binders, registries, and naming conventions. You can use properties such as `management.metrics.distribution.percentiles-histogram` by meter name in supported versions.

When distribution statistics are enabled, the endpoint may show additional measurements such as percentiles or histogram-related data depending on meter/registry. Do not assume calling the endpoint guarantees `p95`/`p99` will be present.

### 9.1 Percentiles and Histograms Differ

- Client-side percentiles are computed per meter instance; they are difficult to aggregate accurately across multiple instances.
- Histogram buckets can be aggregated by a backend to compute quantiles and SLOs.
- Histograms increase the number of time series; enable them only for needed meters.
- Bucket boundaries should match latency objectives and workload.

The Metrics endpoint is suited for checking configuration and local values; a dedicated backend is suited for fleet-wide percentile analysis.

## 10. Custom Metrics Appearing in the Endpoint

When an application registers a meter via Micrometer, the endpoint can read that meter from `MeterRegistry`.

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
class OrderMetrics {

    private final Counter created;

    OrderMetrics(MeterRegistry registry) {
        this.created = Counter.builder("app.orders.created")
                .description("Number of created orders")
                .tag("channel", "web")
                .register(registry);
    }

    void recordCreated() {
        created.increment();
    }
}
~~~

This example hardcodes `channel=web` to illustrate a bounded tag. In a real application, if `channel` is an input variable, allow only a finite set of values and normalize them before creating the meter. Do not create new meters per order ID or customer ID.

After `recordCreated` runs, call:

~~~http
GET /actuator/metrics/app.orders.created
~~~

You can filter by tag if the meter has multiple registered `channel` values.

### 10.1 Common Tags

Common tags can be configured via `MeterRegistryCustomizer` or properties to attach metadata like service/environment to meters. Choose stable values; do not attach instance-specific IDs or request data if they unnecessarily inflate cardinality.

## 11. Metrics Endpoint vs. Prometheus Endpoint

| Endpoint | Purpose | Response |
|---|---|---|
| /actuator/metrics | Diagnose a single meter in the application | Actuator JSON |
| /actuator/prometheus | Prometheus scrape | Prometheus exposition text |
| OTLP metrics exporter | Push metrics to Collector/backend | OTLP protocol |
| Metrics backend query API | Query stored data over time | Backend-specific query result |

For Prometheus scraping, add the appropriate registry dependency and expose the endpoint:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
~~~

Prometheus scrapes `/actuator/prometheus`; it does not scrape `/actuator/metrics` as if it were an exposition endpoint. The Metrics endpoint does not provide time-based history; it reads current meter state in the process.

## 12. Securing the Metrics Endpoint

Metrics can reveal service names, dependencies, and internal topology; route names, HTTP statuses, and traffic patterns; JVM/process utilization; database pool state; and business volumes.

Do not expose the endpoint publicly without authentication/network controls. Principles:
1. Expose only necessary endpoints.
2. Place the management port/network interface in a management network when appropriate.
3. Protect with Spring Security or reverse proxy authentication.
4. Use TLS on untrusted networks.
5. Restrict access by role/service account.
6. Never put credentials, request payloads, or PII into custom tags.
7. Record appropriate audit/access logs and control retention.
8. Verify endpoint exposure after every configuration change.

Exposure decides whether an endpoint has a route; authentication/authorization is a separate control layer. Exposing only health and metrics does not mean the endpoints are authenticated.

## 13. Management Port and Base Path

You can separate the management server from the application port:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 8081
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include: health,metrics
~~~

In this example, the application HTTP server listens on 8080 and the management server listens on 8081. The metrics path is `/actuator/metrics` on the management port. A separate address/interface can be configured per deployment; ensure load balancers, firewalls, and service networks only allow monitoring clients to access it.

When using a separate management port, some health/readiness/liveness checks may behave differently when the management server is unavailable. Design probes and availability policies according to the Actuator guide for your version.

## 14. Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| /actuator/metrics returns 404 | Actuator missing, endpoint not exposed, or different base path | Check dependency, exposure, and URL |
| Endpoint returns 401/403 | Security requires authentication/role | Use appropriate credentials/service account |
| Names missing expected meter | Instrumentation has not created meter or binder missing | Check dependencies, registry, and code paths |
| Meter exists with count 0 | No events recorded since meter registration | Trigger operation and read again |
| Tag query does not match | Wrong key/value or tag has not appeared yet | Inspect availableTags |
| Timer lacks p95/p99 | Distribution statistics not enabled or different registry | Configure histograms/percentiles |
| Metrics endpoint has data but Prometheus fails to scrape | Missing registry or prometheus not exposed | Add Prometheus registry and configure scrape endpoint |
| Gauge changes between calls | Gauge reflects current state | Interpret as a snapshot, not a counter |
| Metric cardinality increases | Dynamic tag values creating new meter IDs | Normalize/allowlist dimensions |
| Meter name differs from expected | Naming convention/normalization or integration version | Inspect registry and meter names |
| Management port unreachable | Bind address/firewall/service network | Check network path and management server |
| Endpoint leaks internal data | Overly broad exposure or missing auth | Narrow exposure, network policy, and security |

## 15. Playbook: Investigating Elevated HTTP Latency with the Metrics Endpoint

**Scenario:** A dashboard alerts on rising HTTP latency, and you need to confirm meters and tags on one instance.

1. Access the management address over an authorized network.
2. Call `/actuator/metrics` to confirm the `http.server.requests` meter exists.
3. Call `/actuator/metrics/http.server.requests` to inspect measurements and `availableTags`.
4. Filter by `method`, `uri`, and `status` to examine the target request group.
5. Compare `COUNT`, `TOTAL_TIME`, and `MAX`; remember the endpoint is a registry snapshot, not history.
6. Open the trace backend to find specific requests and inspect downstream spans.
7. Compare with Prometheus/backend queries to view `p95`/`p99`, rates, and trends across multiple instances.
8. If a tag value is missing, verify instrumentation/conventions and route mappings.
9. If the endpoint lacks the meter, check auto-configuration, binders, and code paths.
10. After investigation, keep the management endpoint within its required access boundary.

Do not use a single reading of `MAX` or `COUNT` to conclude the entire fleet is healthy or failing; the endpoint reflects only the local registry.

## 16. Self-Check Exercises

**Exercise 1 — Listing meters.** Which endpoint lists meter names? Does it return metrics history?

**Exercise 2 — Reading a Timer.** A Timer has `COUNT=100`, `TOTAL_TIME=20`, and `baseUnit=seconds`. What is the average duration per event in seconds? Why can't `p95` be inferred from these two numbers?

**Exercise 3 — Tag filtering.** Write the URL to read HTTP server requests for POST with status 500. How can multiple tag filters be passed?

**Exercise 4 — Available tags.** What is `availableTags` used for? Why is it not the list of tag values for the entire distributed system?

**Exercise 5 — Prometheus.** Why does Prometheus scrape `/actuator/prometheus` instead of `/actuator/metrics`?

**Exercise 6 — Percentiles.** Why doesn't the Metrics endpoint include `p95`/`p99` for every Timer by default? What cost do histograms incur?

**Exercise 7 — Security.** What types of information does the Metrics endpoint reveal? Name two protection layers to configure.

**Exercise 8 — Missing meter.** The meter `app.orders.created` does not appear in `names`. List the checks to perform in order.

### Answer Hints

1. `GET /actuator/metrics`; the endpoint lists meter names and does not store time-series history.
2. Average 0.2 seconds. `COUNT`/`TOTAL_TIME` do not reveal the distribution, so `p95` cannot be derived.
3. `/actuator/metrics/http.server.requests?tag=method:POST&tag=status:500`; repeat the `tag` query parameter for each condition.
4. Used to discover tag keys/values of a meter in the current registry; not across all instances or backend history.
5. The Prometheus endpoint returns the exposition format designed for scrapers; the Metrics endpoint returns Actuator diagnostic JSON.
6. Distribution statistics require configuration and carry memory/series/ingestion costs; enable only for needed meters.
7. Reveals topology, routes, traffic, and resource utilization. Restrict network exposure and require authentication/authorization.
8. Check meter registration code, increment code path, `MeterRegistry`, filters/predicates, endpoint exposure, and actual meter name.

## 17. Official References

- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): endpoint exposure, access, base path, and security considerations.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer integration, meter names, tags, and distribution statistics.
- [Spring Boot — Prometheus](https://docs.spring.io/spring-boot/reference/actuator/metrics.html#actuator.metrics.export.prometheus): Prometheus registry and scrape endpoint.
- [Micrometer — Meters](https://docs.micrometer.io/micrometer/reference/concepts/meters.html): meter types, Counter, Gauge, Timer, and DistributionSummary.
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): Timer measurements, histograms, and percentiles.
- [Spring Boot — Security](https://docs.spring.io/spring-boot/reference/web/spring-security.html): protecting management endpoints with Spring Security.
- [Prometheus — Exposition Formats](https://prometheus.io/docs/instrumenting/exposition_formats/): metrics format that Prometheus scrapes.
- [OpenTelemetry — Metrics](https://opentelemetry.io/docs/concepts/signals/metrics/): metric instruments and aggregation concepts.

**Takeaway:** The Metrics endpoint lets you discover and read meters in a Spring Boot instance's registry. Use the root endpoint to list names, the meter-name endpoint to view measurements/`availableTags`, and the `tag` query parameter to filter. It returns diagnostic JSON, not history or Prometheus exposition format. To query rates, `p95`/`p99`, and fleet-wide trends, use Prometheus/a metrics backend; keep management endpoints inside a protected network and expose only what operations need.
