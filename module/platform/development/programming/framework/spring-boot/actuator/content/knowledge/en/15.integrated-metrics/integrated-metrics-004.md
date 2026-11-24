# Observing the HTTP Server: Request Count, Latency, Status Codes, and URI Templates

## 1. Viewing an HTTP Request From Four Angles

When an API slows down or returns errors, four initial questions usually arise:

1. How many requests are passing through, and how is the rate changing?
2. How long did completed requests take on the server side?
3. Which status codes is the server returning?
4. Which path group do requests belong to, such as `/api/items/{id}`?

A total request count cannot answer latency. An average latency does not tell you which API is failing. A full URL containing every individual ID can explode the number of metric series to monitor.

Spring Boot Actuator integrates Micrometer to provide built-in HTTP measurements. This lesson uses Spring MVC on Spring Boot 3.3.13, focusing on `http.server.requests` and how to read those four perspectives.

The examples include both application code and MockMvc verification. Do not build a custom counter to replace Spring's built-in measurement.

## 2. http.server.requests Is a Timer, Not Just a Counter

Spring Boot auto-configures measurements for requests handled by Spring MVC, with default name `http.server.requests`. In this Boot line, the mechanism integrates through Micrometer Observation and the framework's HTTP filter. See [Spring Boot: Spring MVC Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.supported.spring-mvc).

General processing flow:

```text
Request enters the instrumented server layer
    -> starts observation
    -> selects handler, processes request, and builds response
    -> observation finishes
    -> Timer records count and duration along with tags
    -> Actuator/backend reads the recorded metrics
```

With a Timer:

| Statistic | Meaning |
| --- | --- |
| `COUNT` | Number of completed and recorded request samples |
| `TOTAL_TIME` | Total duration of those samples |
| `MAX` | Maximum duration over the implementation's statistics window |
| Histograms/percentiles | Additional information when configured and supported by the backend |

Because count is already present in the Timer, there is no need to add another Counter to re-count the exact same requests merely because the metric name contains "requests."

An in-flight request does not yet have a completed duration sample in this Timer. Count is neither the current number of connections nor the number of active requests in progress. Observing in-flight work requires active measurements or appropriate server instrumentation.

## 3. Tags Turn One Total Into Analyzable Groups

In the configuration verified in this lesson, the key information groups are:

| Tag | Example | Answers |
| --- | --- | --- |
| `method` | `GET`, `POST` | Which HTTP method generates traffic? |
| `status` | `200`, `201`, `404`, `503` | Which code did the server return? |
| `outcome` | `SUCCESS`, `CLIENT_ERROR`, `SERVER_ERROR` | Result group by status-code family |
| `uri` | `/api/items/{id}` | Which path template/handler group? |
| `error`, `exception` | `none` or recorded error type name | Was an error attached to the observation? |

Tag names and details can change across versions, stacks, and custom conventions. Boot 3.3.13 run in this lesson includes both `error` and `exception`; inspect actual tags rather than assuming the exact list from another Spring version.

One metric name `http.server.requests` can have multiple Timers: each tag combination creates a distinct meter identity. Two requests with the same URI template but different statuses still belong to separate statistical groups.

Example:

```text
method=GET, uri=/api/items/{id}, status=200
method=GET, uri=/api/items/{id}, status=404
method=POST, uri=/api/items, status=201
```

Filtering by URI alone may not select a single Timer. When isolating one branch, also filter by method, status, or relevant tags.

## 4. Request Count and Rate: Do Not Confuse HTTP With Business Events

The Timer's count shows how many requests the measurement recorded. When a process restarts or a series identity changes, cumulative counts can start over.

A user clicking "Checkout" can trigger multiple HTTP requests due to loading data, polling status, or retrying. A request can also fail before a business transaction is created. Therefore:

```text
HTTP request count != number of users
HTTP request count != number of successful orders
HTTP request count != number of unique business transactions
```

For charts and alerts, you usually need a rate over time, such as requests/second, across the same tag set. Do not compare cumulative counts from two processes of different ages and conclude which machine is under heavier load.

Also define the request set: does it include monitoring endpoints, health checks, static resources, and unmatched API requests? An unfiltered total can include all of those groups.

If you change filters, document the meaning of the new count. Do not label every counted request as a "successful business request."

## 5. Latency: Units, Scope, and Distribution

### 5.1. Server Timer Is Not the End-User Clock

`http.server.requests` measures HTTP exchange handling time within the instrumented framework/server scope. It does not automatically include all DNS, TLS, network, proxy queue, and browser processing time.

Nor is it merely time spent inside a controller method. The measurement boundary sits at the HTTP infrastructure layer and can cover other steps within that scope. With async processing or streaming, verify the observation lifecycle of your stack.

If a proxy times out while the application continues processing, data at the proxy and application can differ. Compare each from its proper perspective.

### 5.2. Average Uses Total Time Divided by Corresponding Sample Count

Arithmetic example: three requests in the same group take 100 ms, 300 ms, and 500 ms:

```text
COUNT      = 3
TOTAL_TIME = 900 ms
mean       = 900 / 3 = 300 ms
```

These are illustrative numbers for the calculation, not fixed latencies of the verification suite below.

Read `baseUnit` when inspecting Actuator. With this lesson's configuration, the returned time unit is seconds; Prometheus also exports series with the `seconds` suffix. Do not take a value in seconds and label it milliseconds.

When aggregating across multiple instances or groups, sum the total times and sum the corresponding counts before dividing. Do not take a simple average of averages that have different sample counts.

### 5.3. Mean, Max, and p95 Answer Different Questions

A small number of very slow requests can be hidden by a low mean. Max reveals a peak value within a statistical window, but does not describe the distribution of all requests.

p95 requires appropriate percentile/histogram data. It does not exist automatically just because a Timer exists, and it cannot be derived from count plus total time.

A basic Timer's max can expire over a window; it is not a lifetime record. Do not sum or average p95s across machines and call that a combined p95. See [Micrometer: Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/1.13/concepts/histogram-quantiles.html).

## 6. Status Codes, Outcome, and Exceptions Are Not Synonymous

Outcome groups commonly map to HTTP status families:

| Code Family | Outcome | Examples |
| --- | --- | --- |
| 1xx | `INFORMATIONAL` | Informational responses |
| 2xx | `SUCCESS` | `200`, `201`, `204` |
| 3xx | `REDIRECTION` | `302` |
| 4xx | `CLIENT_ERROR` | `400`, `401`, `404`, `429` |
| 5xx | `SERVER_ERROR` | `500`, `503` |

Group names describe the HTTP code family; they do not by themselves prove which party caused the root issue. For instance, 429 may reflect load limiting, while 404 may be a probing request or a URL mistake in one of the system's own clients.

A controller returning `ResponseEntity.status(503)` might not throw an exception. In that case, status=503 and outcome=SERVER_ERROR, yet error/exception can still be none.

Conversely, an exception handled by `@ExceptionHandler` is not always automatically attached to the observation. Error recording paths must be configured/marked appropriately if the application wants to retain that info. Spring Boot documents this limitation in [HTTP server metrics guide](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.supported.spring-mvc).

Therefore:

- Track 5xx rate by status/outcome if the goal is HTTP 5xx responses.
- Do not use `exception != none` alone as a proxy for all HTTP errors.
- Do not treat status=200 as proof that all business success conditions were met.
- When investigating root causes, combine metrics with logs or traces; aggregated tags do not carry full error details.

## 7. URI Templates: Grouping Properly Without Unbounded Series

### 7.1. Templates Differ From Paths With Substituted IDs

Three requests:

```text
GET /api/items/101
GET /api/items/202
GET /api/items/303
```

can match the same mapping:

```text
GET /api/items/{id}
```

The metric should preserve the URI template to view the whole API as a group. Putting each ID into a tag grows the number of series with every accessed ID. That is a **cardinality** problem—the number of label combinations created.

Keep tags within a controlled set of values. Do not put query strings, tokens, request IDs, or user IDs into metric tags as a substitute for logs/traces. Micrometer warns about tags growing with user input in [Naming Meters](https://docs.micrometer.io/micrometer/reference/1.13/concepts/naming.html).

In Boot's Observation model, high-cardinality details belong to traces; do not turn them into metric tags. See [Spring Boot: Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

### 7.2. The Same Template Still Has Multiple Status/Method Groups

Two requests returning 200 and one returning 404 on `/api/items/{id}` can create two Timers by status, even under the same URI template.

A query parameter like `source=dashboard` does not automatically create a new URI template in the example's default convention. However, if the parameter causes the app to take a different branch or return a different status, measured results can differ for that reason.

### 7.3. 404 Does Not Always Have uri=NOT_FOUND

Distinguish:

1. Matched `/api/items/{id}` but the resource does not exist: URI can still be that template.
2. No matching controller, yet handled by a resource handler: a pattern like `/**` may be used.
3. No suitable pattern: conventions may use placeholder values such as `NOT_FOUND` or `UNKNOWN` depending on the situation.

In this lesson's default MVC configuration, `/api/not-mapped` hits the resource handler, returns 404, and is recorded with `uri=/**`. The verification suite confirms that exact case.

Do not turn every 404 into the raw path "for clarity." A scan hitting thousands of non-existent URLs can cause series count to grow uncontrollably. To see exact URLs, use appropriate diagnostic sources while keeping aggregated tags stable.

## 8. Practice: A Repeatable Application and Verification Suite

Use JDK 21 and Maven 3.6.3+. Application code compiles targeting Java 17; versions are pinned to Spring Boot 3.3.13 so tag results in the lesson have a clear context.

The project can be used in two ways:

- Run MockMvc to verify mappings, statuses, tags, counts, and Prometheus export format without opening a network port.
- Package and run the web application to try HTTP commands locally.

MockMvc does not measure network latency, TLS, or reverse-proxy behavior. Absolute durations must not be hardcoded as constants in assertions.

### 8.1. Structure and Dependencies

```text
http-server-metrics-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── HttpMetricsApplication.java
    │   │   └── ItemController.java
    │   └── resources/application.properties
    └── test/java/demo/HttpServerMetricsTest.java
```

Contents of `pom.xml`:

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
  <artifactId>http-server-metrics-lab</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
      <groupId>io.micrometer</groupId>
      <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
```

Starter web provides MVC, Actuator provides metrics infrastructure, the Prometheus registry provides export formatting, and starter test is used for verification. There is no custom HTTP Counter or Timer.

### 8.2. Application Entry Point

File `src/main/java/demo/HttpMetricsApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpMetricsApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpMetricsApplication.class, args);
    }
}
```

### 8.3. Controller Producing Observable Outcomes

File `src/main/java/demo/ItemController.java`:

```java
package demo;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import java.net.URI;
import java.util.Map;

@RestController
public class ItemController {
    @GetMapping("/api/items/{id}")
    ResponseEntity<Item> item(@PathVariable String id) {
        if (id.equals("404")) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(new Item(id, "demo"));
    }

    @PostMapping("/api/items")
    ResponseEntity<Item> create() {
        return ResponseEntity.created(URI.create("/api/items/303"))
                .body(new Item("303", "created"));
    }

    @GetMapping("/api/reports")
    ResponseEntity<Map<String, String>> report() {
        return ResponseEntity.status(503)
                .body(Map.of("message", "temporarily unavailable"));
    }

    public record Item(String id, String name) {}
}
```

This is a learning API to produce HTTP scenarios:

- Two different IDs go through the same GET mapping.
- ID `404` makes the controller actively return 404.
- POST returns 201.
- The report API actively returns 503 without throwing an exception.

There is no database or persistence logic in the example; status codes serve as test data for observation.

### 8.4. Local Configuration

File `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=18090
management.endpoints.web.exposure.include=health,metrics,prometheus
```

The application binds only to loopback. The example configures no authentication and is intended solely for a learning environment. Actuator paths in an operational system must be protected according to the system's governance configuration.

There is no need to manually register `ServerHttpObservationFilter` in this Boot application when auto-configuration is active.

### 8.5. Seven Requests and Expected Outcomes

| Sample Request | Status | URI Template in Lesson Configuration |
| --- | --- | --- |
| GET `/api/items/101` | 200 | `/api/items/{id}` |
| GET `/api/items/202` | 200 | `/api/items/{id}` |
| GET `/api/items/404` | 404 | `/api/items/{id}` |
| POST `/api/items` | 201 | `/api/items` |
| GET `/api/reports` | 503 | `/api/reports` |
| GET `/api/not-mapped` | 404 | `/**` |
| GET `/api/items/101?source=dashboard` | 200 | `/api/items/{id}` |

With all other default tags unchanged, these seven requests roll up into five completed Timer series:

```text
GET  /api/items/{id}  200 -> count 3
GET  /api/items/{id}  404 -> count 1
POST /api/items       201 -> count 1
GET  /api/reports     503 -> count 1
GET  /**             404 -> count 1
```

### 8.6. Complete Verification

File `src/test/java/demo/HttpServerMetricsTest.java`:

```java
package demo;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.prometheusmetrics.PrometheusMeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.actuate.observability.AutoConfigureObservability;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;
import java.util.stream.StreamSupport;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(classes = HttpMetricsApplication.class)
@AutoConfigureMockMvc
@AutoConfigureObservability
class HttpServerMetricsTest {
    @Autowired MockMvc mvc;
    @Autowired MeterRegistry registry;
    @Autowired ObjectMapper json;
    @Autowired PrometheusMeterRegistry prometheus;

    @Test
    void observeHttpRequests() throws Exception {
        mvc.perform(get("/api/items/101")).andExpect(status().isOk());
        mvc.perform(get("/api/items/202")).andExpect(status().isOk());
        mvc.perform(get("/api/items/404")).andExpect(status().isNotFound());
        mvc.perform(post("/api/items")).andExpect(status().isCreated());
        mvc.perform(get("/api/reports")).andExpect(status().isServiceUnavailable());
        mvc.perform(get("/api/not-mapped")).andExpect(status().isNotFound());
        mvc.perform(get("/api/items/101").param("source", "dashboard"))
                .andExpect(status().isOk());

        Timer ok = timer("GET", "/api/items/{id}", "200");
        Timer missingItem = timer("GET", "/api/items/{id}", "404");
        Timer report = timer("GET", "/api/reports", "503");
        Timer created = timer("POST", "/api/items", "201");
        Timer unknown = registry.find("http.server.requests")
                .tag("status", "404").timers().stream()
                .filter(t -> !"/api/items/{id}".equals(t.getId().getTag("uri")))
                .findFirst().orElseThrow();

        List<Timer> all = List.copyOf(
                registry.find("http.server.requests").timers());
        long count = all.stream().mapToLong(Timer::count).sum();
        assertThat(count).isEqualTo(7);
        assertThat(ok.count()).isEqualTo(3);
        assertThat(missingItem.count()).isEqualTo(1);
        assertThat(created.count()).isEqualTo(1);
        assertThat(report.count()).isEqualTo(1);
        assertThat(report.getId().getTag("outcome")).isEqualTo("SERVER_ERROR");
        assertThat(report.getId().getTag("exception")).isEqualTo("none");
        assertThat(report.getId().getTag("error")).isEqualTo("none");
        assertThat(unknown.getId().getTag("uri")).isEqualTo("/**");
        assertThat(all).hasSize(5);
        boolean rawUriTagged = all.stream().anyMatch(t ->
                List.of("/api/items/101", "/api/items/202", "/api/items/404")
                        .contains(t.getId().getTag("uri")));
        assertThat(rawUriTagged).isFalse();
        assertThat(all).allMatch(t -> t.totalTime(TimeUnit.NANOSECONDS) > 0);

        String scrape = prometheus.scrape();
        assertThat(scrape).contains("http_server_requests_seconds_count");
        assertThat(scrape).contains("http_server_requests_seconds_sum");

        System.out.println("CHECK business.count=" + count);
        System.out.println("CHECK items.GET.200.count=" + ok.count());
        System.out.println("CHECK items.GET.404.count=" + missingItem.count());
        System.out.println("CHECK items.POST.201.count=" + created.count());
        System.out.println("CHECK report.status=" + report.getId().getTag("status"));
        System.out.println("CHECK report.outcome=" + report.getId().getTag("outcome"));
        System.out.println("CHECK report.exception=" + report.getId().getTag("exception"));
        System.out.println("CHECK report.error=" + report.getId().getTag("error"));
        System.out.println("CHECK unknown.uri=" + unknown.getId().getTag("uri"));
        System.out.println("CHECK completed.series=" + all.size());
        System.out.println("CHECK raw.uri.tagged=" + rawUriTagged);

        String body = mvc.perform(get("/actuator/metrics/http.server.requests")
                        .param("tag", "uri:/api/items/{id}", "method:GET", "status:200"))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();
        JsonNode measurements = json.readTree(body).path("measurements");
        double filteredCount = StreamSupport.stream(measurements.spliterator(), false)
                .filter(m -> m.path("statistic").asText().equals("COUNT"))
                .mapToDouble(m -> m.path("value").asDouble())
                .findFirst().orElseThrow();
        assertThat(filteredCount).isEqualTo(3.0);
        System.out.println("CHECK metrics.filtered.count=" + (long) filteredCount);

        long afterMetricsQuery = registry.find("http.server.requests")
                .timers().stream().mapToLong(Timer::count).sum();
        assertThat(afterMetricsQuery).isEqualTo(8);
        System.out.println("CHECK after.metrics.query.count=" + afterMetricsQuery);
    }

    private Timer timer(String method, String uri, String status) {
        return registry.get("http.server.requests")
                .tags("method", method, "uri", uri, "status", status).timer();
    }
}
```

The test runs in a fresh application context, sends seven sample requests, and then sends one filtered Actuator query.

`@AutoConfigureObservability` enables what is required for observability/registry verification in a test context. Do not assume every test slice or `@SpringBootTest` automatically initializes every exporter just like production runtime. See [Spring Boot: Using Metrics in Tests](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html#testing.spring-boot-applications.metrics).

From the project directory, run:

```powershell
mvn -q test
```

Aside from Spring startup logs and test runner output, the `CHECK` lines printed by the test match exactly:

```text
CHECK business.count=7
CHECK items.GET.200.count=3
CHECK items.GET.404.count=1
CHECK items.POST.201.count=1
CHECK report.status=503
CHECK report.outcome=SERVER_ERROR
CHECK report.exception=none
CHECK report.error=none
CHECK unknown.uri=/**
CHECK completed.series=5
CHECK raw.uri.tagged=false
CHECK metrics.filtered.count=3
CHECK after.metrics.query.count=8
```

Key points to note:

1. `business.count` is a label in the test for the seven sample requests, not the number of successful business transactions.
2. Two IDs and one query parameter still contribute to the single GET/200 template group.
3. A 404 matching a controller differs from a 404 handled by the resource handler.
4. Status 503 does not by itself produce an error/exception other than none.
5. The `metrics` query returns COUNT=3 for the filtered tag set.
6. After the diagnostic query itself, total Timer count rises from 7 to 8 in this configuration. Management requests can also be measured like other HTTP requests.
7. Duration is only verified as recorded; do not fabricate a fixed millisecond total across all machines.
8. Real export content from the Prometheus registry is verified to contain the corresponding count/sum series.

## 9. Running the Web App and Reading Metrics via HTTP

Once verification passes, you can package and run:

```powershell
mvn -q -DskipTests package
java -jar target/http-server-metrics-lab-1.0.0.jar
```

The application uses port 18090 as configured. Wait for the server to finish starting, then use another terminal. Press `Ctrl+C` in the Java terminal to stop after experimenting.

The following commands use `curl.exe` on Windows; on Linux/macOS replace with `curl`:

```powershell
curl.exe --include "http://127.0.0.1:18090/api/items/101"
curl.exe --include "http://127.0.0.1:18090/api/items/202"
curl.exe --include "http://127.0.0.1:18090/api/items/404"
curl.exe --include --request POST "http://127.0.0.1:18090/api/items"
curl.exe --include "http://127.0.0.1:18090/api/reports"
curl.exe --include "http://127.0.0.1:18090/api/not-mapped"
curl.exe --include "http://127.0.0.1:18090/api/items/101?source=dashboard"
```

This recreates the sample request set. Cumulative counts on a running server also depend on previously sent requests, including browser requests or management endpoints. To compare accurately against the test suite, use a fresh process and controlled traffic.

### 9.1. Discovering Names, Units, and Tags

```powershell
curl.exe --silent --show-error "http://127.0.0.1:18090/actuator/metrics"
curl.exe --silent --show-error "http://127.0.0.1:18090/actuator/metrics/http.server.requests"
```

Read:

- `baseUnit` to check the unit.
- `measurements` to distinguish COUNT, TOTAL_TIME, MAX.
- `availableTags` to see the available tags/values.

An unfiltered query can aggregate multiple Timers. Do not treat that aggregate as the latency of a single route.

### 9.2. Filtering by Template, Method, and Status

```powershell
curl.exe --silent --show-error --get "http://127.0.0.1:18090/actuator/metrics/http.server.requests" --data-urlencode "tag=uri:/api/items/{id}" --data-urlencode "tag=method:GET" --data-urlencode "tag=status:200"
```

Each `tag` is a `name:value` condition. When inspecting an API group, use the observed template rather than the path with substituted IDs.

`--data-urlencode` preserves braces and special characters in parameters. With a fresh request set matching the test, the filtered group has COUNT=3; actual durations vary across runs.

The `metrics` endpoint is for diagnosing registered values. It does not retain history and should not be used as a production backend or scrape endpoint. See [Spring Boot: Metrics endpoint](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html).

### 9.3. Viewing Prometheus Export Format

```powershell
curl.exe --silent --show-error "http://127.0.0.1:18090/actuator/prometheus"
```

With this lesson's registry, the verified names include:

```text
http_server_requests_seconds_count
http_server_requests_seconds_sum
```

The name used at `/actuator/metrics` remains `http.server.requests`. Do not pass the Prometheus-converted name into the metrics endpoint path and conclude the meter disappeared.

A direct point read shows current state; charting over time requires a monitoring system that scrapes and stores history.

## 10. Monitoring Queries Must Preserve the Right Dataset

The expressions below are PromQL examples once Prometheus collects the data. Suppose the application's dataset is labeled `job="http-lab"`; in deployment, choose the real job/service and system filtering policy.

### 10.1. Rate by URI and Method

```promql
sum by (uri, method) (
  rate(http_server_requests_seconds_count{job="http-lab"}[5m])
)
```

The result is in requests/second. `[5m]` is the rate calculation window, not individual request latency and does not set the scrape interval.

The `rate` function handles resets and extrapolates from observed data. Across multiple instances, compute `rate` on each series before summing so individual process resets are not lost. See [Prometheus: rate](https://prometheus.io/docs/prometheus/latest/querying/functions/#rate).

### 10.2. Average Latency Over the Same Window

```promql
1000 *
sum by (uri, method) (
  rate(http_server_requests_seconds_sum{job="http-lab"}[5m])
)
/
sum by (uri, method) (
  rate(http_server_requests_seconds_count{job="http-lab"}[5m])
)
```

Multiply by 1000 to express milliseconds. Numerator and denominator must share the exact same filter and grouping. If there is insufficient data or zero requests in the window, do not assume latency equals 0.

Total duration is not CPU time. Multiple requests can overlap and wait on shared resources.

### 10.3. 5xx Response Percentage

```promql
100 *
sum(
  rate(http_server_requests_seconds_count{
    job="http-lab",status=~"5.."
  }[5m])
)
/
sum(
  rate(http_server_requests_seconds_count{job="http-lab"}[5m])
)
```

This expression describes the 5xx rate within the selected request set, not every kind of business failure. If management endpoints remain in the denominator, be aware they also affect the ratio.

If policy excludes health/management or considers only certain routes, apply the matching filter to both numerator and denominator. Do not substitute a different group's traffic as the denominator.

Also distinguish an absent 5xx series, a zero error value, and no traffic. Display and alerting logic must handle these explicitly rather than treating any missing point as "healthy."

## 11. When You Need p95 and Latency Thresholds

To emit histograms for HTTP Timers, an additional configuration can be:

```properties
management.metrics.distribution.percentiles-histogram.http.server.requests=true
management.metrics.distribution.slo.http.server.requests=100ms,500ms,1s
```

This is an extension, not part of the verification suite's default configuration. Restart with the proper configuration, generate traffic, and verify actual bucket data before running percentile queries.

Example computing p95 from a classic histogram when the corresponding buckets exist:

```promql
histogram_quantile(
  0.95,
  sum by (le, uri, method) (
    rate(http_server_requests_seconds_bucket{job="http-lab"}[5m])
  )
)
```

This result is in seconds. Choose status filters intentionally: p95 of successful requests and p95 of all responses can differ, especially when errors fail very quickly.

Histograms multiply series count by the number of buckets and tag combinations. Never enable all distribution statistics on a tag space that already includes unbounded IDs. An estimated percentile also does not guarantee every single request was below a strict bound.

Per-meter properties are documented in [Spring Boot: Per-meter Properties](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.customizing.per-meter-properties).

## 12. Investigation and Common Mistakes

Start from a concrete question such as "GET item is slow" or "503 rate is rising," then check:

1. **Measurement scope:** right server, right instance, right metric; are HTTP client metrics being confused with server metrics?
2. **Traffic:** is count/rate truly rising, or is data missing or did a process just restart?
3. **Outcome group:** which status/outcome is rising, and is it tied to one method/URI?
4. **Latency:** are you looking at mean, max, or percentile; over the same window and request set?
5. **URI template:** is it using a template, a resource handler wildcard, or a placeholder value?
6. **Root cause details:** which logs/traces, GC state, connection pools, or downstream errors explain the rest?

Easy mistakes to make:

| Practice | Problem |
| --- | --- |
| Adding a separate Counter for all the same measured HTTP requests | Redundant semantics, can drift due to different recording points |
| Treating count as in-flight requests | Standard Timers record completed calls |
| Treating total time as average | Missing division by corresponding count |
| Treating server latency as client end-to-end latency | Different scope from network/proxy and client processing |
| Filtering errors only by exception | 5xx responses may throw no exception, or exceptions may be handled |
| Putting URLs with individual IDs into tags | Cardinality grows with user input |
| Assuming all 404s share one placeholder URI | Mappings, resource handlers, and conventions can differ |
| Sending many metrics queries and expecting total HTTP count to stay flat | Management queries themselves can be measured |
| Averaging p95 across instances | Does not yield a mathematically valid combined p95 |
| Using older Boot properties/customization patterns without checking | Observation infrastructure and tag contracts may have changed |

In Boot 3.3, if you genuinely need to alter tag extraction, use the corresponding observation convention contract and preserve required default tag semantics. Never replace `uri` with raw URLs for a temporary investigation.

Metrics are aggregated data; logs and traces explain individual executions. A spike in 503s calls for finding the cause—such as resource limits, downstream failures, or intentional error branches—not just recoloring a chart line.

## 13. Self-Check

**Exercise 1:** Send 100 GET requests with 100 different IDs matching `/api/items/{id}`, all returning 200 with identical other tags. Must 100 Timers be created?

**Answer:** No. Under that template and tag set, they contribute to the same Timer with count increasing by 100. Putting raw IDs into tags is what causes unnecessary series growth.

**Exercise 2:** A controller returns 503 without throwing an exception. Does `exception=none` negate the HTTP error?

**Answer:** No. Status/outcome describe the HTTP response; exception/error describe error information recorded on the observation. In the example, 503 appears with SERVER_ERROR and none.

**Exercise 3:** A Timer has COUNT=4 and TOTAL_TIME=0.8 seconds. What is the mean?

**Answer:** 0.2 seconds, or 200 ms, assuming both statistics come from the same sample set. Do not call 0.8 seconds the average latency.

**Exercise 4:** The test sends 7 sample requests, yet after an Actuator read total count is 8. Is it certain a business request was double-counted?

**Answer:** No. In the lesson's configuration, the diagnostic request itself is measured. Check the URI/tags of the extra count.

**Exercise 5:** A 404 is recorded with `uri=/**` instead of NOT_FOUND. Does that mean raw URLs entered the tag?

**Answer:** No. In the verified configuration, that is the resource handler's pattern. Check actual mappings and conventions; `/**` is not a specific ID.

**Exercise 6:** You have count and sum. Can you compute an exact p95 from those two numbers alone?

**Answer:** No. Appropriate distribution data such as histograms is required, together with the backend's aggregation and windowing rules.

When observing an HTTP server, keep four factors together: request volume, processing duration, status codes, and URI templates. A sound conclusion must specify which request group was measured, over what interval, and from which component's perspective.
