# Server-Side and WebClient-Side Observations and Metrics

In Spring WebFlux, an **Observation** is a layer that records an application operation under a unified lifecycle. From a single Observation, Micrometer can produce metrics, traces, or other observability data depending on registered handlers. Spring Boot Actuator integrates this mechanism to automatically measure server-side HTTP requests and outbound requests made via WebClient.

The two most important metrics:

- `http.server.requests`: timing and outcome of handling HTTP requests in the WebFlux application.
- `http.client.requests`: timing and outcome of WebClient HTTP exchanges with target services.

In Spring Boot, Actuator auto-configures Observation for WebFlux controllers and functional endpoints. For WebClient, you should use the `WebClient.Builder` provided by Spring Boot so the observation registry is attached automatically. If you create a client manually via `WebClient.create()` or a standalone builder, you must configure `ObservationRegistry` explicitly.

This lesson progresses from ObservationRegistry, MeterRegistry, conventions, and cardinality to server/client metrics, Prometheus configuration, safe custom tags, and a Java 17 example with an integration test verifying both metrics.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish Observation, Metric, Trace, and Log.
2. Explain the roles of `ObservationRegistry`, `ObservationContext`, and `ObservationHandler`.
3. Understand `ObservationConvention`, `ObservationFilter`, and `ObservationPredicate`.
4. Distinguish low-cardinality and high-cardinality key values.
5. Know how Spring Boot Actuator creates `http.server.requests` for Spring WebFlux.
6. Know how `http.client.requests` is created for WebClient.
7. Use the Boot auto-configured WebClient builder to preserve instrumentation.
8. Manually configure ObservationRegistry for a self-created WebClient.
9. Add server tags using `DefaultServerRequestObservationConvention`.
10. Inspect metrics via the Actuator metrics endpoint and Prometheus.
11. Configure histograms, SLO buckets, and percentiles for the right purpose.
12. Understand when an exception is recorded as an observation error.
13. Avoid metric cardinality explosion and personal data leakage.
14. Write a Java 17 application and test server/client metrics using WebClient.

## 2. Observability: Observation, Metric, Trace, and Log

These concepts are related, not identical.

| Component | Answers the Question | Example |
| --- | --- | --- |
| Log | What happened, and in what context? | Request rejected due to missing permission |
| Metric | How are trends and counts changing? | p95 latency, request rate, error rate |
| Trace | Which services did a request pass through? | API → WebClient → inventory service |
| Observation | Under what lifecycle is an operation recorded? | HTTP server request, HTTP client exchange |

**Observation is an integration point**, not a storage backend. An Observation is created, started, may receive events/errors, and then stops. ObservationHandlers consume that lifecycle to produce metrics, traces, or other outputs.

Example of an HTTP request:

~~~text
HTTP request arrives
       |
       v
Observation starts
       |
       +--> collect method, route, status context
       |
       +--> controller and downstream WebClient calls
       |
       v
Observation stops
       |
       +--> Meter handler records timer/counter
       |
       +--> Tracing handler finishes span (if configured)
~~~

If only a Micrometer meter registry is present, Observation can produce metrics without producing distributed traces. For distributed traces, you must add a Micrometer Tracing bridge and an appropriate exporter.

## 3. Micrometer Observation Components

### 3.1. ObservationRegistry

`ObservationRegistry` is the registration and coordination point for Observations. Instrumented components such as Spring WebFlux and WebClient receive the registry to emit lifecycle events.

In Spring Boot with Actuator, the registry is auto-configured and integrated with handlers. If a component is not wired with an appropriate registry, its observations can become no-ops and record no metrics.

### 3.2. ObservationContext

`ObservationContext` holds data related to an operation: request, response, exception, key values, and attributes needed by instrumentation. The HTTP server has its own context containing request/response info; WebClient has a context for client exchanges.

The context lets conventions and handlers share information without passing individual fields through many code layers.

### 3.3. ObservationConvention

`ObservationConvention` determines the observation name and the key values to collect. For example, the HTTP server convention can add method, URI template, status, and outcome.

Spring provides default conventions. An application can extend the default convention to add stable tags, or implement a custom convention when the entire contract needs to change.

### 3.4. ObservationHandler

`ObservationHandler` receives lifecycle callbacks such as start, error, event, and stop. A handler can forward data to a MeterRegistry, tracing system, or custom system.

Spring Boot automatically registers a meter observation handler when Actuator and an appropriate registry are present. Thus, typical applications do not need to write custom handlers just to get HTTP metrics.

### 3.5. ObservationFilter and ObservationPredicate

- `ObservationFilter` modifies the context after conventions contribute key values and before handlers process the result.
- `ObservationPredicate` decides whether an observation should be created; if not, the operation can become a no-op.

These two extension points are useful for application-wide policies, but should not be used to arbitrarily strip fields needed for debugging or SLOs.

### 3.6. ObservationRegistry Differs from MeterRegistry

| API | Role |
| --- | --- |
| `ObservationRegistry` | Manages Observation lifecycle and handlers |
| `MeterRegistry` | Stores/registers Counter, Timer, Gauge, DistributionSummary |
| `ObservationConvention` | Names observations and provides key values |
| `ObservationHandler` | Receives lifecycle callbacks and produces outputs |
| `MeterFilter` | Filters/customizes meters upon registration |

Do not mistakenly pass a MeterRegistry to an API expecting an ObservationRegistry. Spring Boot connects the two registries via configured handlers.

## 4. Low Cardinality and High Cardinality

Cardinality is the number of distinct values a tag/key can take.

**Low-cardinality** has a finite, relatively small set of values. Examples:

- HTTP method: GET, POST, PUT, DELETE.
- Outcome: SUCCESS, CLIENT_ERROR, SERVER_ERROR.
- Status: 200, 400, 404, 500.
- URI template: `/api/items/{id}`.

**High-cardinality** can generate a vast number of distinct values. Examples:

- Actual URL `/api/items/8f3a...`.
- User ID, order ID, email, session ID.
- Trace ID or request ID.
- Query string values containing user data.

Micrometer uses low-cardinality values for metric tags; high-cardinality values can be kept in trace context, but should not be put into meter tags because they cause time-series explosion.

Good example:

~~~text
http.server.requests{
  method="GET",
  uri="/api/items/{id}",
  status="200",
  outcome="SUCCESS"
}
~~~

Bad example:

~~~text
http.server.requests{
  uri="/api/items/8f3a4e2b-...",
  userId="user-928374",
  traceId="7b1d..."
}
~~~

If every user or every request creates a new time series, Prometheus and metrics backends can consume massive amounts of memory and index space.

**Principle:** metric tags describe bounded groups; trace attributes are more appropriate for per-request unique identifiers when data policy permits.

## 5. WebFlux Server-Side Observations and Metrics

When using Spring Boot Actuator, auto-configuration enables instrumentation for requests handled by Spring WebFlux controllers and functional endpoints. Default metric:

~~~text
http.server.requests
~~~

This metric measures HTTP exchange processing time and attaches tags describing the outcome.

### 5.1. Default Tags

Common low-cardinality tags:

| Tag | Meaning | Example |
| --- | --- | --- |
| `method` | HTTP method | GET |
| `uri` | Handler URI template | /api/items/{id} |
| `status` | HTTP status | 200 |
| `outcome` | Outcome category | SUCCESS |
| `exception`/`error` | Error type if recorded | none or exception name |

Exact error tag names can vary across Spring/Micrometer convention versions. Inspect actual meters in your application instead of hardcoding assumptions across major versions.

High-cardinality metadata may include the full HTTP URL; do not promote that value into an unbounded metric tag.

### 5.2. How Important Is the URI Template?

With the mapping:

~~~java
@GetMapping("/api/items/{id}")
Mono<ItemView> get(@PathVariable String id) {
    return service.find(id);
}
~~~

The `uri` tag should be:

~~~text
/api/items/{id}
~~~

not:

~~~text
/api/items/10001
/api/items/10002
/api/items/10003
~~~

Spring uses the handler's URI template whenever it can be determined. This is why mappings should be declared using clear templates rather than dynamically creating thousands of routes.

### 5.3. Observation for Controllers and Functional Endpoints

WebFlux instrumentation covers both annotated controllers and functional handlers. Thus, a request handled by `@GetMapping` or `RouterFunction` can still be recorded if the server ObservationRegistry is configured.

If using plain Spring Framework without Boot, you must attach ObservationRegistry to `WebHttpHandlerBuilder` when building the HttpHandler. Spring Boot Actuator typically performs this configuration automatically.

### 5.4. Exceptions Handled Inside Controllers

Server observation typically records an exception when the error escapes processing back to the instrumentation layer. If a controller or `@ExceptionHandler` catches the error and turns it into a normal response, that exception might not automatically appear in the request metric's error tag.

If you want a handled error to still be recorded, the application must explicitly attach the error to the observation context/request attribute according to the API and version in use. Do not assume every 4xx/5xx response gets the same exception tag.

## 6. WebClient-Side Observations and Metrics

Spring Boot Actuator manages instrumentation for WebClient. Default metric:

~~~text
http.client.requests
~~~

Observation measures the entire HTTP client exchange, from connection establishment until the response body is deserialized per the client's contract.

### 6.1. Default Tags

| Tag | Meaning | Example |
| --- | --- | --- |
| `method` | HTTP method | GET |
| `uri` | URI template used when calling the client | /inventory/{id} |
| `client.name` | Target host | inventory.internal |
| `status` | HTTP response status or error state | 200 |
| `outcome` | Outcome category | SUCCESS |
| `error` | Error type if the exchange failed | none or exception type |

High-cardinality HTTP URLs can be stored in trace context, but should not be placed in metric tags.

### 6.2. Using the WebClient.Builder Provided by Spring Boot

Recommended approach:

~~~java
@Service
class InventoryClient {

    private final WebClient webClient;

    InventoryClient(WebClient.Builder builder) {
        this.webClient = builder
            .baseUrl("https://inventory.internal")
            .build();
    }

    Mono<ItemView> find(String id) {
        return webClient.get()
            .uri("/inventory/{id}", id)
            .retrieve()
            .bodyToMono(ItemView.class);
    }
}
~~~

The Boot auto-configured builder has ObservationRegistry and related customizers applied. Requests made through this client can emit `http.client.requests`.

### 6.3. Manually Creating WebClient Can Lose Instrumentation

Way that easily misses the registry:

~~~java
WebClient client = WebClient.create("https://inventory.internal");
~~~

A standalone WebClient does not automatically inherit Boot's customizers. If creating a builder manually, attach the registry:

~~~java
WebClient client = WebClient.builder()
    .observationRegistry(observationRegistry)
    .baseUrl("https://inventory.internal")
    .build();
~~~

You can also attach a custom convention via the builder API if needed. What matters is that the client is actually configured with the ObservationRegistry used by the application.

### 6.4. Do Not Measure Completion Time Incorrectly

Client observation spans the exchange; with a reactive body, completion is tied to receiving/reading the body according to client semantics. Do not measure only the time to build the WebClient request builder and call that HTTP latency.

If code ignores or fails to consume the response body properly, lifecycle and connection reuse can be affected. Use `retrieve().bodyToMono` or the exchange API with explicit cleanup.

## 7. Configuring Spring Boot Actuator and Prometheus

Add the dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Actuator provides Observation/Micrometer integration and diagnostic endpoints. The Prometheus registry provides the scrape format at the Prometheus endpoint.

### 7.1. application.properties

~~~properties
spring.application.name=webflux-observation-demo

management.endpoints.web.exposure.include=health,info,metrics,prometheus

management.metrics.distribution.percentiles-histogram.http.server.requests=true
management.metrics.distribution.percentiles-histogram.http.client.requests=true

management.metrics.distribution.slo.http.server.requests=100ms,250ms,500ms,1s
management.metrics.distribution.slo.http.client.requests=100ms,250ms,500ms,1s
~~~

Meaning:

- Expose health/info/metrics/prometheus for the demo environment.
- Enable histograms suitable for backends to compute aggregatable percentiles.
- Define SLO buckets for both types of HTTP requests.

In production, expose only necessary endpoints and protect Actuator with network policies or authentication. Do not expose metrics/Prometheus endpoints to the public Internet without controls.

### 7.2. Metrics Endpoint for Diagnostics

List metrics:

~~~http
GET /actuator/metrics
~~~

View server metric:

~~~http
GET /actuator/metrics/http.server.requests
~~~

View client metric:

~~~http
GET /actuator/metrics/http.client.requests
~~~

Filter by tag, for example:

~~~http
GET /actuator/metrics/http.server.requests?tag=method:GET
~~~

The metrics endpoint is suitable for diagnosing a running application and inspecting available meters/tags. It should not be used as the primary production scrape backend.

### 7.3. Prometheus Scrape Endpoint

Prometheus reads:

~~~http
GET /actuator/prometheus
~~~

Example scrape configuration:

~~~yaml
scrape_configs:
  - job_name: "webflux-app"
    metrics_path: "/actuator/prometheus"
    static_configs:
      - targets: ["localhost:8080"]
~~~

Prometheus scrapes periodically, stores time series, and enables queries/rules/alerts. When using Kubernetes/service discovery, replace static targets with appropriate discovery.

### 7.4. Histograms, SLOs, and Percentiles

Histograms provide bucket counts that can be aggregated across multiple instances. SLO buckets help track the proportion of requests falling within defined latency thresholds.

Percentiles computed locally per process cannot necessarily be summed or aggregated accurately across multiple instances. If cluster-wide p95/p99 is needed, histogram buckets and backend queries capable of aggregation are typically used.

Do not enable histograms unconditionally for every metric. Histograms increase the number of time series; enable them only for metrics with clear latency/SLO requirements.

## 8. Customizing Server Tags with ObservationConvention

Spring Boot lets you provide a bean extending `DefaultServerRequestObservationConvention` to add low-cardinality tags.

Example adding a fixed tag `service.area=catalog`:

~~~java
package demo;

import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.server.reactive.observation.DefaultServerRequestObservationConvention;
import org.springframework.http.server.reactive.observation.ServerRequestObservationContext;
import org.springframework.http.server.reactive.observation.ServerRequestObservationConvention;

@Configuration(proxyBeanMethods = false)
class ObservationConfiguration {

    @Bean
    ServerRequestObservationConvention serverRequestConvention() {
        return new DefaultServerRequestObservationConvention() {
            @Override
            public KeyValues getLowCardinalityKeyValues(
                    ServerRequestObservationContext context) {

                return super.getLowCardinalityKeyValues(context)
                    .and(KeyValue.of("service.area", "catalog"));
            }
        };
    }
}
~~~

The convention preserves default tags and adds one tag with a small value set. Spring Boot uses this convention bean for WebFlux server observations.

### 8.1. When Should You Implement a Custom Convention?

- **Extend the default:** when you only need to add a few stable tags.
- **Implement the full interface:** when you need to change the observation name or all key values.
- **ObservationFilter:** when you need to modify the context after conventions have generated tags.
- **ObservationPredicate:** when you need to intentionally skip certain observations.

Extending the default is usually easier to maintain because it preserves the framework's default tags.

### 8.2. Avoid High-Cardinality Custom Tags

Never add values like user ID, order ID, email, or trace ID to low-cardinality metric tags. These values can differ on every request, creating millions of time series. If genuinely needed, consider controlled trace attributes with data protection policies.

### 8.3. Customizing WebClient Observation

WebClient uses `ClientRequestObservationConvention` in package:

~~~text
org.springframework.web.reactive.function.client
~~~

You can provide a convention bean to customize client tags. Keep the necessary method, URI template, host, status, and outcome; do not put full URLs or dynamic IDs into low-cardinality tags.

If you only need the registry, no custom convention is required. The Boot-managed `WebClient.Builder` already includes default instrumentation.

## 9. Recording Observations for Custom Business Operations

HTTP exchanges are not the only operations that can be observed. A business operation such as a cache lookup or order processing can also create its own Observation.

Example with a synchronous operation:

~~~java
ItemView loadFromLegacyCache(
        String id,
        ObservationRegistry observationRegistry) {

    return Observation.createNotStarted(
            "catalog.cache.lookup",
            observationRegistry
        )
        .lowCardinalityKeyValue("cache", "product")
        .observe(() -> legacyCache.get(id));
}
~~~

The example assumes `legacyCache.get(id)` is a synchronous API returning ItemView. Observation measures the exact execution duration of that synchronous call.

**Do not blindly wrap Mono creation with `observe()`.** With publishers, the supplier usually only returns the Mono object very quickly; the Observation can stop before the pipeline actually executes. To instrument a reactive publisher, use the Micrometer/Reactor integration appropriate for your version, or manage the lifecycle around subscribe/terminate/cancel so the observation spans actual execution.

### 9.1. Business Names and Tags

Names should be stable:

~~~text
catalog.cache.lookup
orders.payment.authorize
inventory.reserve
~~~

Tags should have a bounded value set:

~~~text
cache=product
operation=lookup
result=hit|miss
~~~

Do not use separate observation names per order/user. Keep operation names stable and use low-cardinality tags.

## 10. Tracing and Context Propagation

Observations can be processed by a tracing handler if the application includes a Micrometer Tracing bridge and matching exporter. Then an HTTP server request can create a server span, a WebClient exchange creates a client span, and trace context is propagated across services.

Some rules:

- Use the Boot-configured WebClient builder to preserve observation/tracing customizers.
- Do not strip trace headers without reason.
- Do not manually generate a trace ID with UUID and record it as a metric tag.
- Verify Reactor context propagation when switching schedulers.
- Keep baggage small and free of secrets.
- Sampling decides which traces are kept; metrics typically still record all requests per configuration.

Metrics answer overall trends; traces help investigate a specific request. Do not use traces as a substitute for metrics or vice versa.

## 11. Complete Java 17 Example: Measuring Both Server and WebClient

The example uses **Spring Boot 3.5.16**, Java 17, WebFlux, and Actuator. The test sends an HTTP request using WebClient to the running server itself on a random port. Thus, a single call produces both:

- `http.client.requests` on the WebClient side.
- `http.server.requests` on the WebFlux server side.

The test also verifies the custom tag `service.area=catalog`.

### 11.1. Project Structure

~~~text
webflux-observation-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/ObservabilityApplication.java
    │   ├── java/demo/ItemView.java
    │   ├── java/demo/ItemController.java
    │   ├── java/demo/ObservationConfiguration.java
    │   └── resources/application.properties
    └── test/java/demo/ObservabilityIntegrationTest.java
~~~

### 11.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 11.3. application.properties

~~~properties
spring.application.name=webflux-observation-demo

management.endpoints.web.exposure.include=health,info,metrics,prometheus

management.metrics.distribution.percentiles-histogram.http.server.requests=true
management.metrics.distribution.percentiles-histogram.http.client.requests=true

management.metrics.distribution.slo.http.server.requests=100ms,250ms,500ms,1s
management.metrics.distribution.slo.http.client.requests=100ms,250ms,500ms,1s
~~~

### 11.4. ObservabilityApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ObservabilityApplication {

    public static void main(String[] args) {
        SpringApplication.run(ObservabilityApplication.class, args);
    }
}
~~~

### 11.5. ItemView.java

~~~java
package demo;

public record ItemView(
    String id,
    String status
) {}
~~~

### 11.6. ItemController.java

~~~java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
class ItemController {

    @GetMapping("/api/items/{id}")
    Mono<ItemView> getItem(@PathVariable String id) {
        return Mono.just(
            new ItemView(id, "available")
        );
    }
}
~~~

### 11.7. ObservationConfiguration.java

~~~java
package demo;

import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.server.reactive.observation.DefaultServerRequestObservationConvention;
import org.springframework.http.server.reactive.observation.ServerRequestObservationContext;
import org.springframework.http.server.reactive.observation.ServerRequestObservationConvention;

@Configuration(proxyBeanMethods = false)
class ObservationConfiguration {

    @Bean
    ServerRequestObservationConvention serverRequestConvention() {
        return new DefaultServerRequestObservationConvention() {
            @Override
            public KeyValues getLowCardinalityKeyValues(
                    ServerRequestObservationContext context) {

                return super.getLowCardinalityKeyValues(context)
                    .and(KeyValue.of("service.area", "catalog"));
            }
        };
    }
}
~~~

### 11.8. ObservabilityIntegrationTest.java

~~~java
package demo;

import java.time.Duration;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.web.reactive.function.client.WebClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class ObservabilityIntegrationTest {

    @LocalServerPort
    int port;

    @Autowired
    WebClient.Builder webClientBuilder;

    @Autowired
    MeterRegistry meterRegistry;

    @Test
    void webClientCallRecordsClientAndServerMetrics() {
        WebClient client = webClientBuilder.clone()
            .baseUrl("http://localhost:" + port)
            .build();

        ItemView item = client.get()
            .uri("/api/items/{id}", "42")
            .retrieve()
            .bodyToMono(ItemView.class)
            .block(Duration.ofSeconds(5));

        assertNotNull(item);
        assertEquals("42", item.id());
        assertEquals("available", item.status());

        Timer clientTimer = meterRegistry
            .find("http.client.requests")
            .timer();

        Timer serverTimer = meterRegistry
            .find("http.server.requests")
            .tag("service.area", "catalog")
            .timer();

        assertNotNull(clientTimer);
        assertNotNull(serverTimer);
        assertTrue(clientTimer.count() >= 1);
        assertTrue(serverTimer.count() >= 1);
    }
}
~~~

**Why does this test prove instrumentation works?**

1. The test injects the Boot-managed `WebClient.Builder`.
2. The builder creates a client with a configured ObservationRegistry.
3. The client sends a GET request to the WebFlux server on a random port.
4. WebClient creates `http.client.requests`.
5. WebFlux server creates `http.server.requests`.
6. The custom server convention adds the tag `service.area=catalog`.
7. The test reads both Timers from MeterRegistry and verifies count >= 1.

`block(Duration)` is only inside the JUnit test thread to wait for the HTTP result. Do not copy this synchronous wait into a WebFlux controller/event loop.

### 11.9. Running Tests

With the Gradle wrapper:

~~~bash
./gradlew test
~~~

On Windows:

~~~powershell
.\gradlew.bat test
~~~

If there is no wrapper yet and a compatible Gradle version is installed:

~~~bash
gradle test
~~~

The test uses a random server port and does not call any external service.

### 11.10. Inspecting While the Application Is Running

Start:

~~~bash
./gradlew bootRun
~~~

Call the API:

~~~bash
curl http://localhost:8080/api/items/42
~~~

Expected JSON response:

~~~json
{"id":"42","status":"available"}
~~~

View the server metric:

~~~bash
curl http://localhost:8080/actuator/metrics/http.server.requests
~~~

View the client metric after a WebClient call has occurred:

~~~bash
curl http://localhost:8080/actuator/metrics/http.client.requests
~~~

View Prometheus exposition:

~~~bash
curl http://localhost:8080/actuator/prometheus
~~~

Calling the endpoint directly with curl only produces server metrics; it does not produce `http.client.requests` in the same application because curl is not a WebClient running inside the process. To produce client metrics, a request must be issued through an instrumented WebClient.

## 12. Reading and Interpreting Metrics

### 12.1. Request Rate

Count requests over a time window using count/rate metrics in the backend. Distinguish overall requests from requests grouped by method/status/route.

### 12.2. Latency

A Timer records count, total time, and max; histogram/SLO buckets support distribution analysis. Use p50/p95/p99 to observe tail latency, not just averages.

### 12.3. Error Rate

Filter by status/outcome/error. Distinguish:

- Server returning 4xx due to input/client.
- Server returning 5xx due to application error.
- Client receiving no response due to DNS/connect/TLS/timeout.
- Downstream returning 4xx/5xx.
- Request cancelled before completion.

### 12.4. Server and Client Metrics Can Differ

A single incoming server request can make multiple downstream WebClient calls. Therefore, `http.client.requests` counts can exceed `http.server.requests` counts.

Conversely, some server requests do not call downstream services. Do not expect both metrics to have equal counts.

### 12.5. Client Duration Longer Than Server Duration

Client timers can include DNS/connection setup, network, remote processing, and body decoding. Server timers only measure server-side processing per instrumentation. Differences can reflect network, queues, connection pools, downstream latency, or body transfer.

## 13. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Thinking Observation is a metric itself | Unclear which handler creates output | Observation is a lifecycle; handlers create metrics/traces |
| Not adding Actuator | Expected auto-configured metrics are missing | Add spring-boot-starter-actuator |
| Using WebClient.create() and expecting metrics | Client observation may be no-op | Inject Boot-managed WebClient.Builder |
| Creating WebClient.Builder manually without registry | Missing http.client.requests | Call observationRegistry(registry) |
| Confusing ObservationRegistry with MeterRegistry | Wrong API wired and missing handlers | Use each registry for its responsibility |
| Adding userId/orderId as metric tags | Uncontrolled cardinality growth | Use low-cardinality tags; put detailed IDs only in traces when appropriate |
| Tagging URI with actual path values | Every ID creates a new time series | Use URI templates |
| Checking only server metrics | Unknown whether downstream calls are measured | Check both http.server.requests and http.client.requests |
| Calling curl and looking for client metrics | curl does not run inside the application process | Use an instrumented WebClient |
| Not exposing Actuator endpoints | Cannot access metrics/prometheus | Configure exposure and proper security |
| Exposing Actuator publicly without protection | Leaks topology and operational data | Restrict via network/authentication |
| Enabling histograms on every metric | Increases series count and storage | Enable only per SLO/use case |
| Looking only at average latency | Misses tail latency | Inspect histograms and p95/p99 |
| Assuming handled exceptions always become error tags | Missing error metrics | Review exception handling and set observation error if needed |
| Using observe() around Mono creation | Observation stops before the publisher runs | Use appropriate reactive instrumentation/lifecycle |
| Creating a convention that unintentionally replaces all defaults | Default tags are lost | Extend DefaultServerRequestObservationConvention |
| Writing full URLs/tokens into tags | Data leakage and high cardinality | Mask data; never tag secrets |
| Using the metrics endpoint as the Prometheus scraper | Backend polling diagnostic endpoint suboptimally | Use /actuator/prometheus |

## 14. Implementation Checklist

1. **Dependency:** is spring-boot-starter-actuator present?
2. **Server:** do WebFlux controllers and functional endpoints produce http.server.requests?
3. **Client:** does WebClient use the auto-configured builder or an explicitly attached registry?
4. **ObservationRegistry:** do components use the right registry?
5. **MeterRegistry:** is the needed exporter/backend configured?
6. **Convention:** are default tags preserved when customizing?
7. **Cardinality:** do metric tags have small, bounded value sets?
8. **URI:** do metrics use route templates rather than actual IDs?
9. **Errors:** does exception handling drop necessary error context?
10. **Histogram:** are SLOs/percentiles clearly defined for monitoring?
11. **Tracing:** are a tracing bridge and exporter configured if distributed traces are needed?
12. **Context:** does Reactor/WebClient context propagation work across scheduler switches?
13. **Endpoints:** are metrics/prometheus exposed only to authorized parties?
14. **Tests:** do integration tests verify both client and server timers?
15. **Operations:** do dashboards separate server latency, client latency, status, and outcome?

**Key Takeaway:** Spring Boot Actuator automatically instruments the WebFlux server into `http.server.requests` and WebClient into `http.client.requests` when the client uses the Boot-configured `WebClient.Builder`. ObservationRegistry coordinates the lifecycle; MeterRegistry stores metrics; conventions provide tags. Use URI templates and low-cardinality tags to keep time-series counts under control. Add histograms/SLOs when latency analysis is needed, expose Prometheus securely, and test both server and client end-to-end instead of looking at only one side.

## References

- Spring Boot 3.5 — Actuator Metrics, WebFlux and WebClient instrumentation: https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html
- Spring Boot — Actuator endpoints and Prometheus exposure: https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html
- Spring Framework — Observability Support, ObservationRegistry and conventions: https://docs.spring.io/spring-framework/reference/integration/observability.html
- Spring Framework 6.2 — DefaultServerRequestObservationConvention API: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/http/server/reactive/observation/DefaultServerRequestObservationConvention.html
- Spring Framework — WebClient configuration and observation: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
- Micrometer — Observation components and lifecycle: https://docs.micrometer.io/micrometer/reference/observation/components.html
- Micrometer — Observation concepts and cardinality: https://docs.micrometer.io/micrometer/reference/observation/introduction.html
