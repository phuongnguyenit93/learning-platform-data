# Simulating Failing External Dependencies, Probe State Transitions, and Interrupted Exporters

## 1. Three Failure Paths to Distinguish

An application can still answer HTTP requests when an external dependency is unreachable, when an instance is refusing traffic, or when a monitoring collector goes down. These three situations call for three different conclusions. Simply checking that `/actuator/health` returns 200 in normal state does not show how the system will react under failure.

This lesson builds an experiment following the sequence **normal → inject fault → observe → clear fault → verify recovery**. We check HTTP status codes, health status, request-handling capability, and data actually passing through the metric exporter simultaneously. The example uses Spring Boot 3.3.13, Java 17+, and JUnit 5; it can run on JDK 21.

| Concept | Question to Answer | Evidence |
| --- | --- | --- |
| External dependency | Does the called service respond correctly and on time? | HTTP errors, timeouts, or connection errors handled properly |
| Liveness probe | Is the application instance still in a valid running state? | `liveness` group and `LivenessState` |
| Readiness probe | Should the instance receive new requests? | `readiness` group and `ReadinessState` |
| Exporter | Is telemetry data leaving the application? | Send attempts, shipped payload, and collector-side results |
| Recovery | After the fault clears, does the system work properly again? | Repeat the action and observe the new result |

`HealthIndicator` produces health results; health groups aggregate the configured results. `ApplicationAvailability` stores readiness/liveness states. Micrometer handles metric recording and exporting. These mechanisms are related, yet they do not automatically collapse into a single state.

## 2. Choose the Policy Before Writing Assertions

### 2.1. A Failing Dependency Does Not Mean the Instance Should Restart

Do not put a database, external API, or monitoring collector into liveness just to detect failures quickly. Restarting the application usually cannot fix an external service. If every instance checks a dependency via liveness, a shared outage can trigger mass restarts. By default, Spring Boot does not automatically add other health indicators to the two probe groups; putting a dependency into readiness must be a deliberate choice. [Spring Boot 3.3 Probe Groups](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes).

For readiness, ask: when this dependency fails, can the instance still serve any meaningful portion of its work?

- **Mandatory dependency with no fallback:** may be placed in readiness, provided you accept that all instances may be pulled from traffic together when a shared system fails.
- **Optional dependency or one with a fallback:** tests must prove the remaining path still works; policy may put this fault only into diagnostic health.
- **Monitoring collector:** in this lesson, exporting metrics is a supporting function. Collector failure does not fail readiness or liveness. Special business requirements need their own policy and tests.

No single choice fits every application. Write down the policy first, then pick the expected outcomes.

### 2.2. Availability State and Routing Are Two Separate Layers

You can publish an `AvailabilityChangeEvent` with `ReadinessState.REFUSING_TRAFFIC` or `ACCEPTING_TRAFFIC` in tests. The event updates availability state; by default it does not shut down the HTTP listener or install a filter blocking all URLs. [Application availability](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-availability).

In Kubernetes, failing readiness makes the instance ineligible to receive normal traffic through a Service. Failing liveness past the threshold can cause the container to restart. Local Spring tests have no kubelet and therefore do not prove traffic removal, container restarts, or convergence time; those behaviors must be tested in a cluster. [Kubernetes Probe Configuration](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/).

### 2.3. Outcome Matrix for the Experiment

Below, `external` is included in readiness; the OTLP collector is not included in either probe group; other availability states remain normal.

| Scenario | Readiness | Liveness | Additional Evidence |
| --- | --- | --- | --- |
| Dependency returns 200 | 200 / `UP` | 200 / `UP` | Baseline before fault |
| Dependency returns 503 | 503 / `DOWN` | 200 / `UP` | Clear fault and readiness returns to 200 |
| Dependency responds too slowly | 503 / `DOWN` | 200 / `UP` | Check enforces a timeout |
| Publish refusing-traffic event | 503 / `OUT_OF_SERVICE` | 200 / `UP` | Calling `/work` directly still returns 200 in test |
| OTLP collector returns 503 | 200 / `UP` | 200 / `UP` | Send was attempted but receiver rejected it |
| Collector returns to 200 | 200 / `UP` | 200 / `UP` | New payload arrives containing updated metric value |

HTTP status code and status string are two separate assertions. By default `DOWN` and `OUT_OF_SERVICE` map to 503; if the application customizes mappings, assert against the actual contract. [Mapping Health to HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.writing-custom-healthindicators).

## 3. Designing Repeatable Faults

Use a stub HTTP server on `127.0.0.1`, with an OS-assigned port:

- `/dependency` switches between returning 200, returning 503, and waiting longer than the request timeout.
- `/v1/metrics` decodes the OTLP message, records the attempt, and returns 200 or 503 under test control.

The Spring application runs on another random port. The test calls Actuator endpoints over real HTTP. Calling `HealthIndicator.health()` directly tests only part of the logic; it does not prove that health groups, paths, and HTTP status codes are configured properly.

Follow four principles:

1. One primary fault per round to isolate the cause.
2. Enforce client-side timeouts so tests never hang indefinitely. `HttpRequest.Builder.timeout(...)` sets the response timeout for a request. [JDK 21 HTTP request timeout](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html#timeout(java.time.Duration)).
3. Restore shared state after each test; close servers, executors, and registries when finished.
4. Always test recovery as well. Proving only `UP → DOWN` can miss stuck states or an exporter that stops retrying.

`Thread.sleep(800)` in the example lives only in the stub server to produce a slow response. The test does not sleep guessing when the exporter runs; it triggers each export explicitly. The three-second assertion is a hang guard, not a promise that the entire HTTP request finishes in exactly 250 ms.

## 4. Complete Runnable Example

Create a standalone lab directory with the following two files. No `main` class is needed: the application configuration lives right inside the test. Do not include this fault-control setup in production code.

### 4.1. `pom.xml`

Spring Boot manages library versions. OTLP is used only in tests; `java.version=17` allows compiling for Java 17 when running on JDK 17 or 21.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-parent</artifactId><version>3.3.13</version><relativePath/></parent>
  <groupId>example</groupId><artifactId>actuator-failure-lab</artifactId><version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
  <dependencies>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-web</artifactId></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-actuator</artifactId></dependency>
    <dependency><groupId>io.micrometer</groupId><artifactId>micrometer-registry-otlp</artifactId><scope>test</scope></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-test</artifactId><scope>test</scope></dependency>
  </dependencies>
</project>
```

### 4.2. `src/test/java/example/ActuatorFailureTest.java`

This is the entire test class, containing the stub server, test application, and four scenarios. `@Execution(SAME_THREAD)` keeps tests in this class from running concurrently since they control a shared stub server.

```java
package example;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import io.micrometer.core.instrument.Clock;
import io.micrometer.core.instrument.Counter;
import io.micrometer.registry.otlp.OtlpConfig;
import io.micrometer.registry.otlp.OtlpMeterRegistry;
import io.opentelemetry.proto.collector.metrics.v1.ExportMetricsServiceRequest;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    classes = ActuatorFailureTest.TestApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "management.endpoints.web.exposure.include=health,metrics",
        "management.endpoint.health.probes.enabled=true",
        "management.endpoint.health.group.liveness.include=livenessState",
        "management.endpoint.health.group.readiness.include=readinessState,external",
        "management.otlp.metrics.export.enabled=false"
    }
)
@Execution(ExecutionMode.SAME_THREAD)
class ActuatorFailureTest {
    enum DependencyMode { OK, ERROR, SLOW }

    static final AtomicReference<DependencyMode> dependencyMode =
        new AtomicReference<>(DependencyMode.OK);
    static final AtomicInteger collectorStatus = new AtomicInteger(200);
    static final List<Attempt> attempts = new CopyOnWriteArrayList<>();
    static final ExecutorService executor = Executors.newCachedThreadPool();
    static final HttpServer stub = createStub();
    static final HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofMillis(200)).build();

    record Attempt(int status, ExportMetricsServiceRequest payload) {}

    static HttpServer createStub() {
        try {
            HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
            server.setExecutor(executor);
            server.createContext("/dependency", exchange -> {
                DependencyMode mode = dependencyMode.get();
                if (mode == DependencyMode.SLOW) {
                    try {
                        Thread.sleep(800);
                    } catch (InterruptedException exception) {
                        Thread.currentThread().interrupt();
                    }
                }
                respond(exchange, mode == DependencyMode.ERROR ? 503 : 200);
            });
            server.createContext("/v1/metrics", exchange -> {
                var payload = ExportMetricsServiceRequest.parseFrom(
                    exchange.getRequestBody().readAllBytes());
                int status = collectorStatus.get();
                attempts.add(new Attempt(status, payload));
                respond(exchange, status);
            });
            server.start();
            return server;
        } catch (IOException exception) {
            throw new ExceptionInInitializerError(exception);
        }
    }

    static void respond(HttpExchange exchange, int status) {
        try {
            // An empty protobuf message is a valid OTLP success response.
            exchange.getResponseHeaders().set("Content-Type", "application/x-protobuf");
            exchange.sendResponseHeaders(status, -1);
        } catch (IOException ignored) {
            // A timed-out client may close the connection before the stub server responds.
        } finally {
            exchange.close();
        }
    }

    static String stubUrl(String path) {
        return "http://127.0.0.1:" + stub.getAddress().getPort() + path;
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import(WorkController.class)
    static class TestApplication {
        @Bean
        HealthIndicator externalHealthIndicator() {
            return () -> {
                var request = HttpRequest.newBuilder(URI.create(stubUrl("/dependency")))
                    .timeout(Duration.ofMillis(250)).GET().build();
                try {
                    var response = client.send(request, HttpResponse.BodyHandlers.discarding());
                    return response.statusCode() == 200
                        ? Health.up().build()
                        : Health.down().withDetail("reason", "remote-status").build();
                } catch (InterruptedException exception) {
                    Thread.currentThread().interrupt();
                    return Health.down().withDetail("reason", "interrupted").build();
                } catch (IOException exception) {
                    return Health.down().withDetail("reason", "transport").build();
                }
            };
        }
    }

    @RestController
    static class WorkController {
        @GetMapping("/work")
        String work() {
            return "done";
        }
    }

    @Autowired TestRestTemplate http;
    @Autowired ObjectMapper json;
    @Autowired ConfigurableApplicationContext context;

    @BeforeEach
    void reset() {
        dependencyMode.set(DependencyMode.OK);
        collectorStatus.set(200);
        attempts.clear();
        AvailabilityChangeEvent.publish(context, LivenessState.CORRECT);
        AvailabilityChangeEvent.publish(context, ReadinessState.ACCEPTING_TRAFFIC);
    }

    @AfterEach
    void restore() {
        dependencyMode.set(DependencyMode.OK);
        AvailabilityChangeEvent.publish(context, LivenessState.CORRECT);
        AvailabilityChangeEvent.publish(context, ReadinessState.ACCEPTING_TRAFFIC);
    }

    @AfterAll
    static void stopStub() {
        stub.stop(0);
        executor.shutdownNow();
    }

    void assertHealth(String group, int code, String expected) throws Exception {
        var response = http.getForEntity("/actuator/health/" + group, String.class);
        assertThat(response.getStatusCode().value()).isEqualTo(code);
        assertThat(json.readTree(response.getBody()).path("status").asText())
            .isEqualTo(expected);
    }

    @Test
    void externalFailureAndRecovery() throws Exception {
        assertHealth("readiness", 200, "UP");
        dependencyMode.set(DependencyMode.ERROR);
        assertHealth("readiness", 503, "DOWN");
        assertHealth("liveness", 200, "UP");
        dependencyMode.set(DependencyMode.OK);
        assertHealth("readiness", 200, "UP");
    }

    @Test
    void slowDependencyAndRecovery() throws Exception {
        dependencyMode.set(DependencyMode.SLOW);
        long start = System.nanoTime();
        assertHealth("readiness", 503, "DOWN");
        assertThat(Duration.ofNanos(System.nanoTime() - start))
            .isLessThan(Duration.ofSeconds(3));
        assertHealth("liveness", 200, "UP");
        dependencyMode.set(DependencyMode.OK);
        assertHealth("readiness", 200, "UP");
    }

    @Test
    void readinessEventDoesNotCloseHttpConnector() throws Exception {
        AvailabilityChangeEvent.publish(context, ReadinessState.REFUSING_TRAFFIC);
        assertHealth("readiness", 503, "OUT_OF_SERVICE");
        assertHealth("liveness", 200, "UP");
        var response = http.getForEntity("/work", String.class);
        assertThat(response.getStatusCode().value()).isEqualTo(200);
        assertThat(response.getBody()).isEqualTo("done");
        AvailabilityChangeEvent.publish(context, ReadinessState.ACCEPTING_TRAFFIC);
        assertHealth("readiness", 200, "UP");
    }

    static class ManualOtlpRegistry extends OtlpMeterRegistry implements AutoCloseable {
        ManualOtlpRegistry() {
            super(new OtlpConfig() {
                @Override public String get(String key) { return null; }
                @Override public boolean enabled() { return false; }
                @Override public String url() { return stubUrl("/v1/metrics"); }
            }, Clock.SYSTEM);
        }

        void publishOnce() {
            super.publish();
        }
    }

    @Test
    void exporterFailureAndRecovery() throws Exception {
        try (var registry = new ManualOtlpRegistry()) {
            Counter counter = registry.counter("lab.completed");
            counter.increment(2);
            collectorStatus.set(503);
            registry.publishOnce();
            assertThat(attempts).hasSize(1);
            assertThat(attempts.get(0).status()).isEqualTo(503);
            assertThat(counter.count()).isEqualTo(2);
            assertHealth("readiness", 200, "UP");
            assertHealth("liveness", 200, "UP");
            var response = http.getForEntity("/work", String.class);
            assertThat(response.getStatusCode().value()).isEqualTo(200);
            assertThat(response.getBody()).isEqualTo("done");

            collectorStatus.set(200);
            counter.increment();
            registry.publishOnce();
            assertThat(attempts).hasSize(2);
            Attempt recovered = attempts.get(1);
            assertThat(recovered.status()).isEqualTo(200);
            double exported = recovered.payload().getResourceMetricsList().stream()
                .flatMap(resource -> resource.getScopeMetricsList().stream())
                .flatMap(scope -> scope.getMetricsList().stream())
                .filter(metric -> metric.getName().equals("lab.completed"))
                .mapToDouble(metric -> metric.getSum().getDataPoints(0).getAsDouble())
                .findFirst().orElseThrow();
            assertThat(exported).isEqualTo(3);
        }
    }
}
```

## 5. Running and Reading Results

In the directory containing `pom.xml`, use Maven with JDK 17 or 21:

```shell
mvn test
```

Maven compiles the test code, starts the application on a random port, and runs JUnit. Do not use `javac ActuatorFailureTest.java` on its own because the example needs the Spring, JUnit, and OTLP libraries on the classpath.

In `target/surefire-reports/example.ActuatorFailureTest.txt`, the result section should contain:

```text
Tests run: 4, Failures: 0, Errors: 0, Skipped: 0
```

This is the stable portion of the output; port numbers, PID, elapsed time, and startup logs vary by environment. When the stub collector returns 503, Micrometer logs a warning that metric export failed, which matches the fault being simulated; all assertions must still PASS. Do not silence all logs just to make reports look clean.

If a Windows JDK reports `Unable to establish loopback connection` with a root cause in `UnixDomainSockets.connect`, inspect the socket environment and temporary directory path before concluding Actuator is at fault. When the temporary path is too long, you can set `jdk.net.unixdomain.tmpdir` to point to a short, existing, writable directory. This is a JVM option for the test run, not a Spring property. [How Windows JDK Selects the Socket Directory](https://github.com/openjdk/jdk21u/blob/master/src/java.base/windows/classes/sun/nio/ch/UnixDomainSocketsUtil.java).

## 6. Interpreting Each Experiment and Limits of the Evidence

### 6.1. HTTP 503 from an External Dependency

`externalFailureAndRecovery()` starts with readiness `UP`, switches the stub server to 503, asserts readiness `DOWN` and liveness still `UP`, then clears the fault and verifies readiness returns to `UP`.

The `externalHealthIndicator` bean has health ID `external`. Readiness is configured to include `readinessState,external`; liveness includes only `livenessState`. Hence the external fault enters readiness aggregation and not liveness aggregation. The test verifies that separation via HTTP endpoints.

The experiment does not yet prove database queries, transactions, retries, or fallback handling in a real application. When applying this, add assertions on business operations that use the dependency; a health endpoint returning the right status does not replace business-logic tests.

### 6.2. Slow Responses and Timeouts

`slowDependencyAndRecovery()` delays the response longer than the request's 250 ms timeout. The I/O error is translated to `DOWN`; liveness still responds; after removing the delay, readiness returns to `UP`.

Immediate failures and hanging failures differ in resource impact: waiting too long can tie up threads, connections, and in-flight tasks. Therefore, include a slow-response scenario alongside the HTTP 503 scenario.

`connectTimeout(200 ms)` bounds connection establishment; `HttpRequest.timeout(250 ms)` is the request timeout. Do not treat them as the same quantity, nor require the entire HTTP test to finish in an exact fixed millisecond count. The three-second assertion leaves headroom for HTTP and CI environments.

This test does not fully simulate DNS, refused TCP connections, pool exhaustion, or every phase of reading large bodies. Those cases need dedicated network scenarios. In a real application you must also check the timeouts of the actual HTTP client/driver libraries in use; kubelet timeout settings do not automatically cancel work inside the application.

### 6.3. Readiness Events Do Not Close the HTTP Port

`readinessEventDoesNotCloseHttpConnector()` publishes `REFUSING_TRAFFIC` and checks `OUT_OF_SERVICE`/503. It then calls `/work` directly and still receives 200. This proves that availability is a signal for infrastructure to consume; the application does not block all incoming requests simply by publishing the event.

`/work` only returns an internal result without calling the external dependency. Its success does not mean requests needing a database will also succeed. The test has no Kubernetes Service or load balancer to remove the instance from rotation.

After publishing `ACCEPTING_TRAFFIC`, readiness must return to `UP`. Checking only the event object without making HTTP calls misses the mapping from availability to endpoint output. Conversely, manually publishing the event does not prove that real startup logic publishes the event at the right moment; that requires separate testing.

### 6.4. Failing and Recovering OTLP Collector

`exporterFailureAndRecovery()` uses the real `OtlpMeterRegistry`. The test-only subclass exposes a method that calls `publish()`; `enabled()=false` stops the background scheduler from running automatically. Each `publishOnce()` call is an explicitly controlled export without sleeping for the `step` interval.

Verification sequence:

1. Increment `lab.completed` to 2, set the collector to return 503, and trigger an export.
2. Verify there is one decodable OTLP request, the collector returned 503, and the local counter remains 2.
3. During that condition, call readiness, liveness, and `/work` to verify the test HTTP path still works.
4. Restore the collector to 200, increment the counter by 1, and export again.
5. Decode the protobuf from the new send, find the `lab.completed` metric, and assert its value equals 3.

Micrometer 1.13 defaults to `cumulative` aggregation for OTLP. The value 3 shows that the subsequent send reflects the new counter total; it does not prove that the exporter persisted and replayed every failed batch. For `delta` or histograms, write assertions matching the corresponding interval and data. [Micrometer 1.13 OTLP Configuration](https://docs.micrometer.io/micrometer/reference/1.13/implementations/otlp.html).

`OtlpMeterRegistry` in the 1.13 line logs a warning when HTTP fails or shipping encounters an error. Asserting "calling publish did not throw an exception" is not enough to conclude data was received. [OtlpMeterRegistry 1.13.15 Source](https://github.com/micrometer-metrics/micrometer/blob/v1.13.15/implementations/micrometer-registry-otlp/src/main/java/io/micrometer/registry/otlp/OtlpMeterRegistry.java).

The stub collector only decodes and records messages. HTTP 200 here does not prove data was durably stored in a time-series system or appeared on a real dashboard.

`ManualOtlpRegistry` declares `implements AutoCloseable` so it can be used with `try-with-resources` via the inherited `close()` method. This is a test-support class, not a requirement to modify registries in production.

## 7. Testing Real Export Paths Without False Passes

### 7.1. Proving the Exporter Is Actually Running

In `@SpringBootTest`, registries that ship to external systems are not auto-configured the same way as during normal application startup; in-memory registries may still exist. If you want to test the exporter auto-configuration path itself, use `@AutoConfigureObservability` and point the exporter to a test collector. [Metrics in Spring Boot 3.3 Tests](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html#testing.spring-boot-applications.metrics).

The example above instantiates the registry manually. The property `management.otlp.metrics.export.enabled=false` prevents an auto-configured registry from sending unintentionally in the background; it does not govern instances created with `new ManualOtlpRegistry()`. Thus the test proves registry behavior during collector failure alongside continuing HTTP capability, without verifying all production auto-configuration and publishing schedules.

For an integration test of a real export path, also verify:

- A registry/exporter of the right type exists and receives the exact metric to observe.
- The export target points to the test collector and does not accidentally ship to a real system.
- Before injecting the fault, the receiving side already has a valid data point confirming the pipeline works.
- During the fault, representative business operations still meet outcome and time/resource budgets per policy.
- After recovery, the receiving side shows new data with the right identity, value, and timestamp; do not mistake leftover prior requests for new results.
- The registry and background threads are closed; no send tasks remain active after the context closes.

With a real scheduler, use a bounded wait on a condition. Do not require an exact single request if the design batches or retries. Filter specifically for the current run's data rather than relying on the ordering of all background requests. Do not add unbounded random tags to production metrics just to make test lookups easier.

### 7.2. Prometheus Scrapes Data; OTLP in the Example Pushes Data

In the standard Prometheus model, Prometheus actively scrapes data from `/actuator/prometheus`. Prometheus stopping does not mean the application is failing an HTTP push request to Prometheus. Distinguish this model from dedicated push mechanisms such as Pushgateway. [Micrometer Prometheus Model](https://docs.micrometer.io/micrometer/reference/implementations/prometheus.html).

A suitable scenario for the scrape path:

1. Record a known metric, call the scrape endpoint, and confirm it is exposed properly.
2. Stop or block the scraper in the test environment; keep generating load and verify the application behaves per policy.
3. Verify that monitoring detects missed scrapes. Local metrics at `/actuator/metrics` do not prove Prometheus received them.
4. Restore scraping and verify new samples arrive in the monitoring system.

Do not promise that all intermediate samples are recovered. A cumulative counter can reflect the new total after an outage, yet it cannot reconstruct every change that happened during the gap.

### 7.3. Metric Recovery Does Not Prove Trace and Log Recovery

Traces require controlling sampling in test configuration, finishing spans, and verifying trace IDs on the receiving side. Asynchronous logging requires testing queue limits, full-queue policies, and flushing on shutdown. Use test data markers to distinguish new data, duplicates, and late arrivals.

Only claim zero data loss when storage/queuing mechanisms and tests actually prove that guarantee. An alert clearing or a dashboard turning green again is not enough.

## 8. Extending Faults and Testing at the Right Layer

A stub server works well for HTTP status codes and slow responses. When you need more realistic network faults, use a fault-injecting proxy or an isolated container environment; never stop a user-serving service to run automated tests.

| Fault | How to Create in Test Environment | Additional Assertions |
| --- | --- | --- |
| HTTP 500/503 | Stub server changes response code | Health accurate, clear fault and verify recovery |
| Slow response | Delay response in stub server | Client timeout takes effect, probe does not hang |
| Connection refused/dropped | Proxy or stop the right test container | Tasks exit on time, resources released |
| Flaky network | Alternate healthy/failing in a deterministic script | State does not get stuck after multiple fault/recovery cycles |
| Collector falling behind | Slow down the receiving path | Monitor queues, threads, memory, business latency |
| Shared dependency down | Block the same dependency for multiple test instances | Evaluate readiness impact on the whole service and fallback handling |

If the application uses a separate management port, test the business port too. You can expose additional probes on the main port with `management.endpoint.health.probes.add-additional-paths=true` and then test the exact deployed path. Working probes on the management port alone are not enough to prove the main port serves requests. [Probes on the Application Port](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes).

In a test cluster, check `periodSeconds`, `timeoutSeconds`, `failureThreshold`, and probe recovery settings. Verify that Pods are removed from and restored to Service endpoints, while tracking restart counts. If a startup probe is configured, test the startup phase separately so liveness failures during initialization are not mistaken for business bugs. Do not infer cluster convergence times from a local HTTP test alone.

## 9. Common Testing Mistakes

| Practice | Why the Conclusion Is Insufficient | Better Testing Approach |
| --- | --- | --- |
| Calling only `/actuator/health` | Does not distinguish each group's purpose | Call each probe, check HTTP code and body |
| Mocking the whole health result to DOWN | Bypasses dependency error-handling code | Keep the real indicator, inject fault at the HTTP/adapter boundary |
| Only publishing availability events | Does not check that endpoints reflect the state | Call HTTP after the event and after recovery |
| Seeing counter increase and assuming exported | That is only in-registry data | Check shipped payload and collector-side result |
| Exporter disabled yet test passes | Export path was never exercised | Prove valid reception both before and after the fault |
| Fixed multi-second sleep | Depends on CI speed and background schedule | Trigger sends explicitly or wait on a bounded condition |
| Testing only the fault phase | Misses stuck state or leaks | Assert recovery and clean up resources |
| Error log as the only assertion | Does not prove payload reached collector | Assert structured payload and actual values |

## 10. Hands-On Verification Exercises

1. Remove `external` from readiness, rerun the test, and explain which assertion fails. Then write new expectations for an optional-dependency policy; do not change expectations merely to hide a misconfiguration.
2. Add a test that publishes `LivenessState.BROKEN`, asserts liveness `DOWN`/503, and then restores `CORRECT`. Explain why readiness can remain `UP` if no mechanism changes it.
3. Add a connection error toward the collector, verify that the export task finishes on time, and verify that the post-recovery send contains updated data. Separate connection errors from HTTP 503.
4. Create another test class using OTLP auto-configuration. Prove that the exporter is enabled, the collector receives data, and scheduled publishing stops when the context closes.
5. Replace `/work` with a representative business operation from a real application, including both a dependency-using path and a fallback path. Verify outcomes both during the fault and after recovery.

A satisfactory scenario clearly identifies where the fault is injected, which signals must change, which functions must keep working, what data actually reaches the collector, and what evidence confirms recovery. In this way, testing moves from an endpoint returning the right status code to evaluating application behavior during incidents.
