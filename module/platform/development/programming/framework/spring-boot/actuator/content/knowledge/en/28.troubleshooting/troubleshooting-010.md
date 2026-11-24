# Finding Why Prometheus Scraping Fails or the Registry Exports No Data

## 1. Understand the Path of a Measurement Properly

In Spring Boot Actuator, a measurement does not jump straight from Java code to a dashboard chart. It travels through multiple layers:

```text
Application code / Spring Boot auto-configured instrumentation
                 |
                 v
MeterRegistry actually used by the application
                 |
                 v
PrometheusMeterRegistry and its collector
                 |
                 v
HTTP endpoint /actuator/prometheus
                 |
                 v
Prometheus connects, reads, and parses the exposition
                 |
                 v
Samples are accepted, stored, and queried
```

**Registry** is where Micrometer manages meters such as counters, timers, and gauges. **Scrape** is Prometheus actively sending an HTTP request to the application and reading the exported measurements. In this standard pull model, Spring Boot does not actively push data to Prometheus.

Therefore, "seeing no data" can be several distinct failures:

- Prometheus cannot connect to the application.
- Connection succeeds, yet hits the wrong path, fails authentication, or gets the wrong format.
- The endpoint works, yet the desired meter is not in the exported registry.
- The exposition contains the meter, yet Prometheus drops or rejects the samples.
- Prometheus stored the data, yet the query uses the wrong name, labels, or time range.

The diagnostic goal is to find the **first boundary where evidence no longer holds**. Fix configuration only at that layer; do not enable every endpoint or swap every dependency at once.

Configuration examples below use Spring Boot 3.3.x, Java 17+, and Spring Boot-managed Micrometer versions. If your app uses a different version, cross-check property names and Prometheus client types against the running version rather than copying config from an older article.

## 2. Gather Evidence Before Changing Anything

Record at least the following for the exact failing instance:

| Evidence | Question to answer |
| --- | --- |
| Actual versions | Which Spring Boot, Micrometer, and Prometheus client versions resolved? |
| Management address | Which exact scheme, host, port, and full path are being scraped? |
| Request origin | Did the request come from a laptop, a Prometheus container, or which Pod? |
| HTTP response | What are the status, Content-Type, and actual body? |
| Target state | What are Last scrape, Last error, and job/instance labels? |
| Expected meter | What are the Micrometer name, Prometheus exported name, and expected label set? |
| Effective configuration | Which profiles, env vars, and command-line flags override? |
| Timeline | Did the failure start after a deploy, dependency change, security change, or load spike? |

Do not use opening the URL in a local browser to conclude Prometheus can reach it too. The two callers may have different DNS, network paths, credentials, and certificates.

When sharing logs or check output, strip passwords, tokens, and credentials. Keep only the address needed for diagnosis, error codes, and relevant response excerpts.

### Checking HTTP Raw

The command below uses Bash-style shell syntax; on Windows, call `curl.exe` explicitly and adjust variable/path syntax for PowerShell:

```bash
curl -i --max-time 10 http://localhost:8080/actuator/prometheus
```

Read both headers and body:

- `200` with metric text: proceed to checking meters and ingestion.
- `200` yet body is HTML: you may be receiving a login page, error page, or frontend page.
- `301`/`302`: check `Location`; redirects can send requests to another scheme, host, or login page.
- `401`/`403`: branch into authentication/authorization.
- `404`: check dependencies, endpoint state, exposure, and path.
- `500`: check application-side errors during collection/export.
- No HTTP response: prioritize DNS, TCP, TLS, and timeouts.

Do not add `-L` on the first check, as following redirects can hide the original response. When simulating Prometheus, inspect actual redirect behavior in its scrape configuration.

## 3. Short Decision Tree

```text
Does Prometheus have a valid target for this instance?
  No -> check discovery, relabeling, and scrape config
  Yes
   |
   +-- Connection failure/timeout/TLS -> fix networking and addressing
   |
   +-- HTTP received but 401/403/404/500 -> fix endpoint/security/export
   |
   +-- 200 but metrics unreadable -> check body, Content-Type, format
   |
   +-- 200 with valid metrics
          |
          +-- Desired metric missing from body -> check MeterRegistry/meter
          |
          +-- Metric present in body -> check ingestion, relabeling, and query
```

This order prevents a common reasoning error: editing PromQL while the endpoint still returns `404`, or editing the registry while Prometheus points to the wrong container.

## 4. Branch One: Prometheus Cannot Find or Connect to the Target

### 4.1. Verify the Actual Target

In Prometheus's Targets page or target status API, check:

- Whether the target exists and is in active state.
- Whether the post-discovery/relabel scrape URL has the right host, port, scheme, and path.
- Whether `job`, `instance`, and discovery labels point to the right instance.
- Whether `Last error` mentions DNS, connection, TLS, HTTP, or parsing.
- Whether the last scrape timestamp matches the current deployment.

If no target exists, the app is not necessarily broken. The cause may be an unloaded scrape file, discovery returning no instance, or `relabel_configs` dropping the target.

In Kubernetes environments, distinguish container port, Service port, `targetPort`, and discovery config. Adding an annotation has no effect on its own if your Prometheus setup does not read that annotation.

### 4.2. The localhost Pitfall Between Containers

`localhost` always refers to the network namespace of the process sending the request. Prometheus inside a container calling `localhost:8080` is calling the Prometheus container itself, not the Spring Boot app in another container.

Example of two services on the same Docker Compose network:

```yaml
scrape_configs:
  - job_name: boot-actuator
    metrics_path: /actuator/prometheus
    static_configs:
      - targets: ["app:8080"]
```

In this example, `app` must be a resolvable service name on the network Prometheus joins. If the management server runs on port `9091`, the target must use `app:9091`. Host-published ports and container-internal ports can differ.

### 4.3. Classifying Connection Errors

| Symptom | Priority hypothesis | How to verify |
| --- | --- | --- |
| Name fails to resolve | Wrong DNS or service name | Check DNS from the Prometheus environment |
| Connection refused | Wrong port, no listener, or app stopped | Check listening ports and startup logs |
| Connection timeout | Routing, firewall, NetworkPolicy, or unresponsive target | Test connectivity from the same network and check policies |
| TLS handshake/certificate error | Wrong scheme, untrusted CA, hostname mismatch, or mTLS required | Check certificates, hostnames, and TLS config |
| Timeout after connecting | Slow endpoint, slow proxy, or heavy load | Measure response time and inspect relevant logs/thread dumps |

`management.server.address=127.0.0.1` on a separate management server can restrict it to loopback connections only. Do not reflexively switch to listening on all addresses; identify which networks need access and configure that exact boundary.

With TLS, configure the right CA and hostname in Prometheus. Disabling certificate checks only hides misconfiguration; it is not proof the scrape path is configured properly.

## 5. Branch Two: Endpoint Does Not Exist or Returns Wrong HTTP Status

### 5.1. Four Requirements for Prometheus Exposition

Under standard auto-configuration, verify all four:

1. Actuator is on the runtime classpath.
2. A matching Prometheus registry is on the runtime classpath and not disabled.
3. The `prometheus` endpoint is not disabled.
4. The endpoint is exposed over HTTP and requests reach the right path and port.

Reference configuration for Spring Boot 3.3.x:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

The snippet above is the `dependencies` block of a Gradle project already applying the Spring Boot plugin and Spring Boot dependency management. It is not a standalone `build.gradle`.

Use the Micrometer version managed by Spring Boot's BOM unless there is a verified compatibility reason. Do not mix one `micrometer-core` version with a different registry/client version and blame Actuator for errors.

Inspect actual dependencies using tasks on the exact Gradle project:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency micrometer-registry-prometheus --configuration runtimeClasspath
./gradlew dependencyInsight --dependency micrometer-core --configuration runtimeClasspath
```

In a multi-project build, prefix the appropriate project path before the task name. On Windows, use `gradlew.bat`. A dependency appearing in `testRuntimeClasspath` or another module does not prove the running application has it.

### 5.2. Endpoint and Export Configuration

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
  endpoint:
    prometheus:
      enabled: true
  prometheus:
    metrics:
      export:
        enabled: true
```

The three branches have distinct roles:

- `management.endpoints.web.exposure.include`: selects endpoints exposed over HTTP.
- `management.endpoint.prometheus.enabled`: enables/disables the endpoint under Spring Boot 3.3.x's config model.
- `management.prometheus.metrics.export.enabled`: enables/disables Micrometer Prometheus export auto-configuration in Boot 3.3.x.

Having the registry does not mean the endpoint is exposed. Exposing `prometheus` does not add missing dependencies either.

Also check `management.endpoints.web.exposure.exclude`, since exclude takes precedence over include. If the app disables all endpoints by default via `management.endpoints.enabled-by-default=false`, verify re-enabling the specific endpoint. For metrics, also check settings disabling exporters by default and individually enabling the Prometheus exporter.

Properties like `management.metrics.export.prometheus.enabled` from older Spring Boot generations should not be copied verbatim into Boot 3.3.x. An unrecognized property may not fail startup as users expect.

If YAML looks right yet behavior is wrong, check active profiles, environment variables, external config, and command-line arguments. The required evidence is **effective values in the running process**, not merely `application.yml` in source.

You can enable the auto-configuration conditions report at startup with `--debug` in a suitable diagnostic environment. Find the condition preventing the registry or Prometheus endpoint from being created. You do not need to expose `env`, `beans`, or `conditions` over HTTP just to perform this step.

### 5.3. Management Path and Port

The common default URL is:

```text
http://host:8080/actuator/prometheus
```

Yet the actual URL can be altered by:

- `server.port`.
- `management.server.port` for a separate management server.
- `management.endpoints.web.base-path`.
- `management.endpoints.web.path-mapping.prometheus`.
- Servlet context path or reactive app base path when sharing the server.
- Base path of a separate management server.
- Proxy or ingress adding/stripping a path prefix.

Separate management server example:

```yaml
management:
  server:
    port: 9091
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,prometheus
```

With no extra base path or path mapping, the endpoint is `http://host:9091/manage/prometheus`. When separating the management server, do not prepend the application server's context path onto the management URL.

Corresponding Prometheus config:

```yaml
scrape_configs:
  - job_name: boot-actuator
    metrics_path: /manage/prometheus
    static_configs:
      - targets: ["app:9091"]
```

An app returning `200` on `/actuator/health` does not prove `/actuator/prometheus` exists, is exposed, or is authorized. These are endpoints with different conditions and access rules.

### 5.4. Handling 401, 403, and Login Redirects

If Spring Security is present, check the security chain handling management requests:

- Which chain matches this URL/port?
- Is the scrape identity authenticated?
- Does that identity have permission to read the Prometheus endpoint?
- Does a reverse proxy preserve auth headers and paths?
- Is there a redirect to a login page that Prometheus receives as HTML?

When an app declares custom security chains, do not assume default Actuator security rules still govern every endpoint. With multiple chains, ordering and matchers both affect the outcome.

`basic_auth`, `authorization`, or TLS/mTLS config in Prometheus must match the server side. Use your environment's secret management; never embed credentials in sample URLs or commit them to source.

A typical scrape is an HTTP GET; disabling CSRF application-wide is not a default fix for scrape failures. Do not open all of Actuator with `include: "*"` or drop all security just to mask a misconfigured authorization rule.

### 5.5. Handling HTTP 500

If the request reaches the right endpoint yet returns `500`, inspect the stack trace at the exact scrape time. Causes to check:

- A custom collector or gauge supplier throws an exception.
- A meter produces invalid data/metadata for the exporter.
- Dependency conflict or class linkage error.
- A collector performs slow I/O, holds locks, or creates excessive load.

Do not claim every failing gauge causes the whole endpoint to return `500`: handling depends on meter type, collector, and version. Actual HTTP responses and logs dictate the right fix.

## 6. Branch Three: Endpoint Works, Yet Meters Are Missing

### 6.1. Distinguish Three Questions About Registries

Clearly separate:

1. Into **which registry** was the meter registered?
2. Is that registry a Prometheus registry, or does it forward to one?
3. From **which registry** is the endpoint exporting?

Common wrong example:

```java
// Anti-pattern illustrative code: this is a separate registry.
MeterRegistry isolated = new SimpleMeterRegistry();
isolated.counter("learning.scrape.check").increment();
```

The counter in `isolated` does not appear on Spring Boot's managed `/actuator/prometheus`. Having a meter in the heap does not mean it resides in the registry exported by the endpoint.

The standard approach is injecting the Spring-managed `MeterRegistry`:

```java
@Component
class ScrapeCheckRecorder {
    private final Counter counter;

    ScrapeCheckRecorder(MeterRegistry registry) {
        this.counter = Counter.builder("learning.scrape.check")
                .description("Number of diagnostic events")
                .tag("result", "ok")
                .register(registry);
    }

    void record() {
        counter.increment();
    }
}
```

This is a component inside a Spring Boot app, not a standalone program. Required imports are `io.micrometer.core.instrument.Counter`, `io.micrometer.core.instrument.MeterRegistry`, and `org.springframework.stereotype.Component`.

If multiple registries exist, Spring Boot may use a composite registry. Injecting `MeterRegistry` does not guarantee the received instance is a specific Prometheus class. Inspect child registries and actual bean configuration.

With `CompositeMeterRegistry`, events occurring before a child registry is added are not replayed like a history queue. You cannot create a Prometheus registry later and expect to recover all prior increments.

### 6.2. Do Not Mix Old and New Prometheus Clients

Spring Boot 3.3 moved to the Prometheus Java client 1.x generation via `micrometer-registry-prometheus`. Its registry class lives in package `io.micrometer.prometheusmetrics`.

The legacy client compatibility path uses artifact `micrometer-registry-prometheus-simpleclient` and package `io.micrometer.prometheus`. Watch for this difference when reading older guides.

If a custom collector is registered into the legacy client's collector registry while the endpoint exports via the new client, that collector will not automatically bridge to the new path. The reverse is also true.

Signs to investigate:

- Both client families appear together in the dependency tree.
- `NoClassDefFoundError`, `NoSuchMethodError`, or imports mismatched with the artifact.
- Creating a separate collector registry in Java code instead of using the app's registry.
- A custom collector has data yet is not wired to the registry used by the endpoint.

Do not add both artifacts "just to be safe." Choose the client family you need, let Spring Boot manage versions, and wire custom instrumentation to the right registry.

### 6.3. Micrometer Names Are Not Necessarily Prometheus Names

Micrometer commonly uses dot-separated names, whereas Prometheus uses exporter naming rules and suffixes.

For example, counter `learning.scrape.check` is typically exported as:

```text
learning_scrape_check_total{result="ok"} 1.0
```

The line above illustrates name and label; numeric formatting or extra labels may vary. Do not treat the absence of the literal string `learning.scrape.check` in the exposition as proof the counter does not exist.

For timer `http.server.requests`, series typically take forms like `http_server_requests_seconds_count`, `http_server_requests_seconds_sum`, and others depending on distribution config. Not every timer has `_bucket`; histograms must be configured appropriately. Nor are arbitrary percentiles available by default for any query.

If the `metrics` endpoint is exposed and the investigator is authorized to use it, you can inspect Micrometer names there. If that endpoint is not exposed, you do not need to enable it just to finish diagnosis; inspect the registry in internal diagnostic code or controlled logs.

### 6.4. Meter Not Yet Created or Triggered

Some meters are created upon first activity. Trigger the exact business event and scrape again:

- Call the measured API rather than only calling `/actuator/health`.
- Execute the code branch that actually increments the counter.
- Complete the task measured by the timer.
- Wait for the next collection cycle if a meter relies on its own schedule.

Do not assume calling the scrape endpoint alone creates every HTTP or business metric. Nor should you use a random metric from a different instance as proof for the instance under investigation.

For counters, an unchanging value does not mean the exporter is broken. There may simply be no new events, requests may route to another replica, or the increment condition may not be executing.

### 6.5. Filters, Tags, and Registration Collisions

Check:

- Whether a `MeterFilter` denies the meter name or caps tag cardinality.
- Whether `management.metrics.enable.<prefix>` disables the metric group you seek.
- Whether a filter renames or strips tags so multiple meters collapse to one identity.
- Whether registrations in the same metric family use inconsistent tag key sets.
- Whether a name was already registered with a different meter type.

For instance, two counters named `orders.processed`, one using tag `region` and the other using tag `status`, can violate Prometheus export rules. Design a consistent tag key set for each metric family and read registry registration warnings.

Meter identity depends on name and tags; instantiating a new object does not automatically yield an independent time series. Duplicate registration with a colliding identity can return the existing meter, misleading the author into thinking the new callback or object is being measured.

Avoid using `requestId`, `userId`, or raw URLs containing IDs as tags. Exploding time series counts can exhaust memory, slow down scrapes, and hit ingestion limits. A constantly changing tag value does not fix export failures.

### 6.6. Gauge Loses Its Target Object or Returns Abnormal Values

Many Micrometer gauges hold weak references to the observed object. If the object is created only in a local variable with no remaining strong reference, garbage collection can reclaim it. The gauge may then return `NaN` or fail to provide expected values depending on type and export path.

The following example easily develops a lifecycle bug:

```java
// Illustrative code: AtomicInteger is not held by a long-lived owner.
registry.gauge("queue.depth", new AtomicInteger(0));
```

Hold the state object in a bean or object with an appropriate lifecycle; the supplier should be fast, non-blocking, and safe for concurrent calls. `NaN` from a gauge does not prove scrape networking is broken.

## 7. Branch Four: HTTP 200, Yet Prometheus Rejects the Exposition

### 7.1. Status 200 Is Not Enough

A successful scrape also requires:

- The body is actually in a format Prometheus supports.
- `Content-Type` matches the negotiated format.
- Samples and metadata obey format rules.
- Target ingestion limits are not exceeded.
- No proxy truncates content, alters the body, or returns an error page under status `200`.

Test along the exact route Prometheus uses. A request straight to a Pod can succeed while a request through ingress receives a different body.

Prometheus text exposition typically contains:

```text
# HELP learning_scrape_check_total Number of diagnostic events
# TYPE learning_scrape_check_total counter
learning_scrape_check_total{result="ok"} 1.0
```

This is an illustrative sample, not Spring Boot's complete exposition.

With OpenMetrics, formatting and requirements such as the trailing `# EOF` marker must match. Do not hand-edit endpoint bodies or force a proxy to rewrite Content-Type to mask malformed exposition.

You can verify the response when explicitly requesting Prometheus text:

```bash
curl -i --max-time 10 -H "Accept: text/plain;version=0.0.4" http://localhost:8080/actuator/prometheus
```

If using `promtool check metrics`, run it on Prometheus text compatible with your tool version. The Bash example below saves headers and body separately:

```bash
curl --fail --silent --show-error --max-time 10 \
  -H "Accept: text/plain;version=0.0.4" \
  -D scrape.headers -o scrape.txt \
  http://localhost:8080/actuator/prometheus
promtool check metrics < scrape.txt
```

Before running the second command, verify curl succeeded and headers look right. A `promtool` lint warning and a parse error marking a target DOWN are not identical; inspect the exact message. Passing format checks also does not prove the payload clears ingestion limits or was stored.

### 7.2. Sample Limits, Labels, and Relabeling

Inspect Prometheus config and errors:

- Was `sample_limit` exceeded?
- Were label count or label length limits exceeded?
- Did duplicate samples with the same name and labels cause an error?
- Are timestamps invalid, too old, or out of order?
- Did `metric_relabel_configs` drop the metric you are looking for?

Distinguish:

| Configuration | When it takes effect | Observable consequence |
| --- | --- | --- |
| `relabel_configs` | Before scraping, on targets and discovery labels | Target address/labels changed or target dropped |
| `metric_relabel_configs` | After reading samples, before storage | HTTP scrape has data, yet specific metric is not stored |

When a limit is exceeded, the entire scrape may be marked failed rather than just dropping one metric. Read `Last error` and logs instead of inferring from the app's HTTP `200`.

If a custom collector attaches its own timestamps, inspect the timestamp source. Normal metrics typically let Prometheus assign scrape timestamps; do not add timestamps manually as a default fix.

## 8. Branch Five: Data Is Stored, Yet Queries Find Nothing

Start with a simple query using the right metric name and right target. For example, replace `instance` with the real label from Targets:

```promql
up{job="boot-actuator", instance="app:8080"}
```

- `1`: the latest scrape of that target series succeeded; does not guarantee every business metric exists.
- `0`: the target's latest scrape failed.
- No series: selector may be wrong, target not discovered, or series absent in the evaluation window. "No series" differs from "equals 0."

Next, look up the counter without adding a rate calculation yet:

```promql
learning_scrape_check_total{job="boot-actuator"}
```

Only then constrain `instance` and other tags. With multiple replicas, the test request and queried target must be the same instance, or the query must aggregate properly across replicas.

Common query mistakes:

- Using the dot-separated Micrometer name instead of the Prometheus exported name.
- Using a tag the exporter does not emit, or a mismatched tag value.
- Time range does not cover when data appeared.
- Using `rate()` before at least two suitable samples exist.
- Using a `rate()` window too short relative to the scrape interval.
- Expecting a counter to keep rising after process restart; process counters can reset.
- Taking `_sum` while forgetting the timer's unit, or querying `_bucket` when histograms are not enabled.
- Viewing an old chart with a pinned selector for an instance whose address changed.

Event rate example:

```promql
rate(learning_scrape_check_total{job="boot-actuator"}[5m])
```

The `5m` window is only an example. Pick a window containing enough scrapes per your real config. `rate()` handles counter resets, yet cannot invent data that was never scraped.

You can also inspect `scrape_duration_seconds`, `scrape_samples_scraped`, and `scrape_samples_post_metric_relabeling` for the target. These help compare scraped samples, post-relabel samples, and scrape duration; they do not replace checking the specific metric.

## 9. Hands-On Lab: Creating a Controlled Diagnostic Signal

The goal is isolating instrumentation from networking and querying. Use a test app with `spring-boot-starter-web`, `spring-boot-starter-actuator`, and `micrometer-registry-prometheus` as in the dependencies section above.

File `src/main/java/demo/ScrapeDemoApplication.java`:

```java
package demo;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ScrapeDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ScrapeDemoApplication.class, args);
    }
}

@RestController
class DiagnosticController {
    private final Counter checks;

    DiagnosticController(MeterRegistry registry) {
        checks = Counter.builder("learning.scrape.check")
                .description("Number of diagnostic events")
                .tag("result", "ok")
                .register(registry);
    }

    @GetMapping("/demo")
    String record() {
        checks.increment();
        return "recorded";
    }
}
```

File `src/main/resources/application.yml` in the test environment:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
```

This program runs inside a Spring Boot project, not directly via `javac`, because it requires Spring dependencies and runtime. With a project using the Gradle wrapper and Boot plugin:

```bash
./gradlew bootRun
```

On Windows, use `gradlew.bat bootRun`. In this minimal lab with no Spring Security, default port, and no proxy, the app listens for HTTP on port `8080`.

From another terminal, call exactly once on a freshly started process:

```bash
curl --fail --silent --show-error http://localhost:8080/demo
```

The exact response body is:

```text
recorded
```

This command does not ask the server for a trailing newline; your shell prompt may appear right after the body. Then read the exposition:

```bash
curl --fail --silent --show-error http://localhost:8080/actuator/prometheus
```

Find the series named `learning_scrape_check_total` with tag `result="ok"`. If this was the sole call to `/demo`, the counter value is `1`; numeric representation may be `1.0` or equivalent depending on the exporter. Scrapes themselves do not increment this counter because only the `/demo` handler calls `increment()`.

Once Prometheus has completed enough scrapes, check in sequence:

```promql
up{job="boot-actuator"}
learning_scrape_check_total{job="boot-actuator", result="ok"}
```

If running multiple instances or a tool calls `/demo` automatically, the "single call" condition no longer holds; target the right instance and record the actual request count.

### Four Failure Labs to Pinpoint the Exact Layer

Perform only in a test environment and change one factor at a time:

| Change | Symptom to verify | Conclusion |
| --- | --- | --- |
| Remove `prometheus` from exposure | Endpoint is no longer exposed over HTTP | Endpoint exposure bug, does not prove registry lost data |
| Point target to a port with no listener | Prometheus reports connection error | Address/connection bug, not counter bug |
| Record counter to a private `new SimpleMeterRegistry()` | Counter does not enter Boot's exposition | Wrong target registry |
| Use selector with `result="failed"` | Query returns no series even though body has `result="ok"` | Wrong query filter |

The exact HTTP status when removing exposure also depends on security/proxy; do not assume every environment returns the same code.

After each experiment, revert the change, restart if config requires it, and verify via both HTTP and Targets. Do not leave multiple faults active at once or it becomes hard to tell which edit caused which outcome.

## 10. When Scraping Is Slow or Fails Intermittently

An endpoint that sometimes succeeds and sometimes times out must be investigated as a performance issue, not just a URL bug:

1. Measure response time and body size at the exact times Prometheus reports errors.
2. Compare `scrape_duration_seconds` against `scrape_timeout`.
3. Check CPU, GC, time series count, and meter count.
4. Look for gauges/custom collectors calling databases, remote services, or scanning large data structures during scrapes.
5. Check locks and blocked threads; inspect thread dumps when necessary.
6. Check proxy timeouts, response size limits, and differences across replicas.

A gauge supplier should read already-available state quickly. A gauge calling an external API on every scrape can turn the monitoring system into a load generator or bottleneck.

Increase timeouts only after knowing normal execution time and pipeline limits. Scrape timeout must not exceed scrape interval in valid Prometheus config. Raising both without fixing the root slowdown may merely delay incident detection.

If payload size is too large, prioritize reducing high-cardinality tags, unnecessary histogram buckets, and dynamically registered meters lacking lifecycle cleanup. Do not drop metrics randomly before confirming monitoring needs.

## 11. Diagnostic Wrap-Up Checklist

Consider an incident resolved only when evidence holds across all relevant layers:

- Target is discovered properly and the final URL points to the right instance.
- Connectivity from the Prometheus environment succeeds with proper TLS/authentication.
- Endpoint returns valid HTTP status and metric format.
- Desired meter resides in the right registry and appears in the body after triggering the right event.
- Prometheus scrapes successfully with no related ingestion errors.
- Metric appears with the expected name, labels, unit, and time range.
- The fix preserves intended exposure scope and management read permissions.
- If the failure only appeared under load or after restart, that exact condition has been re-tested.

The crux is separating three pieces of evidence: **the app measured it**, **the endpoint exported it**, and **Prometheus stored the queryable data**. Each proves only one segment of the path; connecting them for the exact instance and timestamp reveals the root cause.
