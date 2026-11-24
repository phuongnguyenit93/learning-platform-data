# URI Labels by Route Template and Avoiding Excessive Label Cardinality

> **Module:** Spring Boot - web-runtime · **Group:** HTTP Observability. This lesson covers labeling `uri` in HTTP metrics/observations using **route/URI templates** instead of concrete URL values, thereby controlling **cardinality** and metrics cost. Examples use **Spring Boot 4.1.2**, **Java 17+**, Spring MVC, Micrometer, Actuator, and Prometheus; with comparisons to WebFlux, RestClient/WebClient, traces, and common pitfalls when Spring Security rejects a request before a controller is selected.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **actual URI**, **URI template**, query string, route pattern, HTTP method, HTTP status, and a meter **label/tag**.
2. Explain why `/api/users/123` and `/api/users/456` should share the same metrics label `uri="/api/users/{userId}"` rather than two separate labels.
3. Calculate the impact of cardinality on time series count when combining `uri` with method, status, outcome, instance, and histogram buckets.
4. Use Spring MVC/WebFlux default instrumentation with `http.server.requests`, understanding low-cardinality key `uri` and high-cardinality key `http.url` in **Observation**.
5. Configure Spring Boot Actuator `/actuator/metrics/http.server.requests`, expose `/actuator/prometheus`, and verify via cURL.
6. Build a Spring Boot 4.1.2 Maven project with parameterized paths and prove multiple requests collapse into one URI template in metrics.
7. Write outbound `RestClient`/`WebClient` calls using URI templates instead of raw URLs or arbitrary ID tags; understand `uri=none`/`UNKNOWN`/`NOT_FOUND` and pre-handler-mapping boundaries.
8. Apply `management.metrics.web.server.max-uri-tags`, `management.metrics.web.client.max-uri-tags`, and `MeterFilter` as a **last line of defense**, never as a substitute for fixing bad labels.
9. Design label allowlists, PII/token protections, cardinality explosion detection workflows, and operational dashboards/alerts.

## 2. Nature of a URI Template vs. Raw URI

A Spring MVC route:

~~~java
@GetMapping("/api/users/{userId}")
public String user(@PathVariable String userId) {
    return "user=" + userId;
}
~~~

Can handle many HTTP requests:

~~~text
GET /api/users/1
GET /api/users/2
GET /api/users/3
GET /api/users/customer-abcdef
GET /api/users/550e8400-e29b-41d4-a716-446655440000
~~~

These are **five distinct raw paths**, yet only **one route pattern**:

~~~text
/api/users/{userId}
~~~

For metrics tracking response latency and error rates by business endpoint, the useful question is: "How long does `GET /api/users/{userId}` take?"—not creating a separate meter for every customer or UUID.

| Component | Example | Should it go verbatim into a metrics label? |
| --- | --- | --- |
| URI template | `/api/users/{userId}` | **Yes**, bounded set of values |
| Raw URI path | `/api/users/123456` | **No**, IDs can grow unboundedly |
| Query string | `?email=a@example.test&page=123` | **No**, may hold PII/unbounded variants |
| Full URL with host | `https://api.example.test/api/users/123456` | Never use as a low-cardinality server label |
| Method | `GET`, `POST` | Yes, finite set |
| HTTP status | `200`, `404`, `500` | Yes, relatively bounded set |
| Error class | `IOException`, `none` | Possible, but check error class count and config |
| User ID / session ID | `u-39284923`, `sess-a1...` | **No**, both high-cardinality and sensitive |
| Free-form Tenant ID | `tenant-839201` | Usually **no**; consider allowlisted tiers/groups |
| HTTP route group | `billing`, `catalog`, `auth` | Yes, if the number of groups is stable |

**A route template describes endpoint structure**, not a naive regex replacing every digit in a URL. Consider `/api/v2/users/123`: `v2` is a fixed API version segment to preserve, while `123` is a path variable. A regex replacing all digit sequences with `{id}` wipes out the version and merges unrelated routes incorrectly.

### 2.1. Stable Templates Do Not Mean Collapsing Everything into One Pattern

Endpoints:

~~~text
/api/users/{userId}
/api/users/{userId}/orders/{orderId}
/api/orders/{orderId}
/api/search
/api/health
~~~

are **five distinct route groups** when declared and observed that way. Never collapse everything into `/api/**` because metrics would lose endpoint-level visibility. The goal is **just enough granularity for operational decisions**, not reducing all labels to a single value.

### 2.2. Query Parameters Are Not Route Templates

Requests:

~~~text
GET /api/search?q=java&page=1
GET /api/search?q=spring&page=999
GET /api/search?q=private-email@example.test&page=3
~~~

typically share the route pattern `/api/search`. Query values can have extreme cardinality and carry sensitive data. If you need to measure query categories, define a **predefined enum** like `search_type=prefix|exact|fuzzy|other` via an allowlist rather than attaching raw queries or emails to meters.

## 3. What Is Cardinality and Why Does It Cause Outages?

A metric time series is typically uniquely identified by **metric name + full label/tag set**. Changing any label value can create a brand-new series.

Example:

~~~text
http_server_requests_seconds_count{
  method="GET",
  uri="/api/users/{userId}",
  status="200",
  outcome="SUCCESS",
  instance="app-1"
}
~~~

Replacing `uri="/api/users/{userId}"` with `uri="/api/users/943573"` generates a separate time series per ID for an endpoint whose **behavior is identical**.

Cardinality explosion causes:

- Huge numbers of `Meter.Id`s, timers, and histograms allocated in the JVM.
- Huge numbers of label sets in Prometheus or similar backends.
- Spiking RAM, CPU, allocations, GC pauses, and observability storage costs.
- Larger scrape payloads, scrape timeouts, and remote-write backlogs.
- Heavy PromQL queries/recording rules and sluggish dashboards.
- Labels carrying tokens or user IDs leaking sensitive data into monitoring.
- When a cap is hit, new series are **dropped**, blinding you to newly deployed endpoints.

### 3.1. Counting Label Combinations

Suppose, hypothetically:

- 200 URI patterns.
- 4 HTTP methods per route.
- 5 possible status codes.
- 10 service instances.

The theoretical maximum combinations along these axes is:

~~~text
200 × 4 × 5 × 10 = 40,000 label combinations
~~~

If histograms add **20 buckets** per metric on each label combination, total bucket series multiply dramatically—on top of `_count`, `_sum`, and other labels. **This is an illustrative upper bound**, not a claim that every route sees every status/method or that every instance appears in one scrape; moreover `outcome` correlates directly with `status`, so do not multiply it unconditionally as an independent dimension.

Replacing 200 templates with 200,000 raw IDs scales that multiplier by orders of magnitude. No CPU/RAM budget is worth burning merely to store individual IDs on the same endpoint metric.

### 3.2. A Standalone Java Demo Showing Cardinality

Create `CardinalityExample.java`:

~~~java
import java.util.HashSet;
import java.util.Set;

public class CardinalityExample {
    public static void main(String[] args) {
        Set<String> rawUris = new HashSet<>();
        Set<String> routeTemplates = new HashSet<>();

        for (int id = 1; id <= 10_000; id++) {
            rawUris.add("/api/users/" + id);
            routeTemplates.add("/api/users/{userId}");
        }

        System.out.println("Unique raw URI values: " + rawUris.size());
        System.out.println("Unique route templates: " + routeTemplates.size());
    }
}
~~~

Run with JDK 17:

~~~bash
javac --release 17 CardinalityExample.java
java CardinalityExample
~~~

Exact stdout:

~~~text
Unique raw URI values: 10000
Unique route templates: 1
~~~

This is a Java `Set` demo and does **not** measure actual Spring Boot meters. It simply demonstrates why route-template tags keep cardinality low. In production, always measure real series counts after scraping rather than inferring from code alone.

## 4. Spring Boot, Micrometer, and Observation

Spring Boot Actuator integrates Micrometer metrics and the Observation API for HTTP servers and HTTP clients. For Spring MVC/WebFlux, default instrumentation records `http.server.requests`; for outbound clients, `http.client.requests`.

~~~text
HTTP request
   |
   v
Spring MVC / WebFlux instrumentation
   |
   v
ObservationRegistry
   +-- low-cardinality KeyValues  -> Micrometer metrics
   +-- high-cardinality KeyValues -> tracing (if configured)
   |
   v
MeterRegistry / Prometheus registry
   |
   v
/actuator/metrics (diagnostics) /actuator/prometheus (scrape)
   |
   v
Prometheus, Grafana, or another monitoring backend
~~~

**Important:** trace fields do not automatically become metrics labels. In Spring Observation, **low-cardinality key values** feed metrics; **high-cardinality key values** can be attached to traces depending on tracing integration. Never promote `http.url`, `user.id`, or queries into meter tags.

### 4.1. Default Low-Cardinality HTTP Server Labels

Per Spring Framework Observation conventions, common keys include:

| Key | Meaning |
| --- | --- |
| `method` | HTTP method or `none` if invalid |
| `status` | Status code or `UNKNOWN` if no response yet |
| `outcome` | HTTP outcome group, e.g., SUCCESS, CLIENT_ERROR |
| `uri` | **Route template** once mapping is resolved; fallback otherwise |
| `error` | Error class or `none` depending on exception handling/convention |
| `exception` | Legacy compatibility key, potentially deprecated/removed in future versions |

`uri` is the focus of this lesson. When a controller declares `@GetMapping("/api/users/{userId}")` and mapping succeeds, the label is `/api/users/{userId}`, **not** the concrete ID substituted into the path.

### 4.2. High-Cardinality URLs and Privacy

Spring Framework also records high-cardinality keys like `http.url` in context/tracing. Real URLs can contain IDs, query strings, or sensitive values. Therefore:

- **Never** copy `http.url` into a low-cardinality metric tag.
- Never put credentials, tokens, or PII into URLs even when metrics omit them: URLs still appear in access logs, proxies, traces, and browser history.
- For tracing, enforce appropriate sampling, access controls, retention, and redaction/sanitization.
- Never assume tracing components scrub PII automatically just because Micrometer metrics exclude it.

### 4.3. MVC and WebFlux Share the Goal, Differ in Extension Points

Spring Boot auto-instruments requests for Spring MVC controllers/functional handlers and WebFlux controllers/functional handlers when the proper dependencies are present. Each stack uses its own conventions:

| | MVC / Servlet | WebFlux / Reactive |
| --- | --- | --- |
| HTTP handler pipeline | `DispatcherServlet` | `DispatcherHandler` |
| Observation server filter | Servlet `ServerHttpObservationFilter` | Reactive `ServerHttpObservationFilter` WebFilter |
| Default convention class | `org.springframework.http.server.observation.DefaultServerRequestObservationConvention` | `org.springframework.http.server.reactive.observation.DefaultServerRequestObservationConvention` |
| Observation context | Servlet `ServerRequestObservationContext` | Reactive `ServerRequestObservationContext` |
| URI label | Matched route pattern when known | Matched route pattern when known |
| High-cardinality URL | Available to tracing | Available to tracing |

Do not copy a Servlet custom `ServerRequestObservationConvention` into WebFlux: their packages and contexts differ. Prefer default conventions unless there is a clear, justified need to alter labels.

## 5. Special Values of the `uri` Label: UNKNOWN, NOT_FOUND, REDIRECTION

Not every HTTP request reaches handler mapping. Spring Framework provides bounded fallback values to keep cardinality low:

- `uri="/api/users/{userId}"` when a route pattern is resolved.
- `uri="NOT_FOUND"` for 404 requests with no matching handler.
- `uri="REDIRECTION"` for 3xx redirects without a matching pattern.
- `uri="root"` when there is no path info per convention.
- `uri="UNKNOWN"` when no pattern can be inferred and none of the cases above apply.

**A fallback does not mean the actual URL was literally UNKNOWN.** It only means instrumentation does not have a **low-cardinality route template** for that request.

### 5.1. A Matched Route Can Still Return HTTP 404

Two distinct cases:

~~~text
GET /api/users/404      -> matches @GetMapping("/api/users/{userId}"),
                           controller returns 404 because record not found.

GET /not-a-real-route   -> no application handler matches the path.
~~~

The first case still has a route template, so metrics can tag `uri="/api/users/{userId}"`, `status="404"`. The second case typically gets `uri="NOT_FOUND"`. Never assume status 404 always produces `uri="NOT_FOUND"`.

### 5.2. Spring Security 401 Before MVC Mapping

In Spring Boot 4 / Spring Security 7, a request can be rejected by Security filters **before DispatcherServlet resolves the route pattern**. In that case, the 401 request's observation may carry `uri="UNKNOWN"`. This is intentional so the app **does not perform premature route matching solely for metrics**, avoiding extra cost and security implications.

Accordingly, when analyzing 401s:

- Do not jump to concluding a controller mapping is missing or Spring instrumentation is broken.
- Do not "fix" it by plugging `request.getRequestURI()` into low-cardinality `uri`; that triggers ID label explosion.
- Observe 401s via status/outcome/method, security-specific metrics, or protected logs/traces.
- If per-route breakdown is truly needed, evaluate instrumentation architecture and safe route resolution **before** security rather than guessing patterns with arbitrary regexes on raw paths.

In other deployments, proxies/filters, exceptions, and statuses can alter fallback behavior. Verify against your actual versions and dependencies.

### 5.3. Avoiding Raw Paths on 404 Errors

An attacker can probe millions of random paths like:

~~~text
/.env-0001
/.env-0002
/login/any-random-token
/api/users/never-existing-uuid
~~~

If server metrics set `uri` to the raw path on 404s, an attacker could force your monitoring backend to create unbounded time series even though **no route exists**. Spring defaults to `NOT_FOUND`/`UNKNOWN` as appropriate to prevent this. For security alerting, store request details in appropriate access logs/traces with rate limits, redaction, and access controls.

## 6. Hands-On Project: Spring Boot 4.1.2 + Actuator + Prometheus

Goal: run an MVC app on localhost, send HTTP requests with varying IDs, then inspect `http.server.requests` and the Prometheus exporter to confirm **a single `uri` template label**. Also include an endpoint making outbound `RestClient` calls with a URI template to verify client instrumentation.

**Requirements:** JDK 17+, Maven, and cURL. On Windows PowerShell, use `curl.exe` instead of the `curl` alias. No database or external service required.

### 6.1. Structure

~~~text
uri-cardinality-demo/
  pom.xml
  src/main/java/com/example/urimetrics/
    UriCardinalityApplication.java
    UserController.java
    LocalClientController.java
  src/main/resources/
    application.properties
~~~

### 6.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>uri-cardinality-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-restclient</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-registry-prometheus</artifactId>
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
~~~

Artifact versions are managed by Spring Boot; you do not need to pin the Micrometer registry version manually. `spring-boot-starter-webmvc` is the MVC starter in Boot 4.x; `spring-boot-starter-restclient` provides outbound blocking HTTP client integration; `spring-boot-starter-actuator` provides metrics endpoints; `micrometer-registry-prometheus` provides Prometheus scrape formatting.

### 6.3. UriCardinalityApplication.java

~~~java
package com.example.urimetrics;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class UriCardinalityApplication {
    public static void main(String[] args) {
        SpringApplication.run(UriCardinalityApplication.class, args);
    }
}
~~~

### 6.4. UserController.java

~~~java
package com.example.urimetrics;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class UserController {

    @GetMapping("/api/users/{userId}")
    public String user(@PathVariable String userId) {
        if (userId.startsWith("missing")) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "User not found");
        }
        return "user=" + userId;
    }

    @GetMapping("/api/orders/{orderId}")
    public String order(@PathVariable String orderId) {
        return "order=" + orderId;
    }

    @GetMapping("/api/search")
    public String search(@RequestParam(defaultValue = "") String q) {
        return "queryLength=" + q.length();
    }

    @GetMapping("/api/ping")
    public String ping() {
        return "pong";
    }
}
~~~

**Why is this example useful?**

- Calling `/api/users/1`, `/api/users/2`, `/api/users/1000` all match `/api/users/{userId}`.
- Calling `/api/orders/100` and `/api/orders/200` matches `/api/orders/{orderId}`.
- `/api/search?q=...` always resolves to `/api/search`; query strings are not part of the default URI label.
- `/api/users/missing-5` enters the **matched handler** and throws HTTP 404, distinguishing it from a URL with no handler at all.
- Returning plain text keeps tests free of JSON mapping or database dependencies.
- The demo app never turns the URL user ID into a new Micrometer tag.

### 6.5. LocalClientController.java

~~~java
package com.example.urimetrics;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class LocalClientController {

    private final RestClient client;

    public LocalClientController(RestClient.Builder builder) {
        this.client = builder
                .baseUrl("http://localhost:8080")
                .build();
    }

    @GetMapping("/api/demo-client/{userId}")
    public String callLocalUser(@PathVariable String userId) {
        return client.get()
                // Keep the URI template fixed and pass the ID separately.
                .uri("/api/users/{userId}", userId)
                .retrieve()
                .body(String.class);
    }
}
~~~

This is a **lab** calling back into itself over localhost HTTP to generate `http.client.requests`; avoid arbitrary self-HTTP calls in production business code. `RestClient.Builder` is **auto-configured by Spring Boot** and injected via constructor so it carries `ObservationRegistry` for the HTTP client.

This assumes the server runs on port 8080 as in `application.properties`. If you change the port, update `baseUrl` too; this is not a service-discovery example.

**Common mistake comparison:**

~~~java
// DO NOT build dynamic paths by concatenating the ID into the template string:
client.get().uri("/api/users/" + userId).retrieve().body(String.class);

// DO: keep URI template constant, pass variables separately:
client.get().uri("/api/users/{userId}", userId)
        .retrieve().body(String.class);
~~~

This code is a **fragment inside a method where `client` and `userId` are already declared**, not a standalone Java file. Reason: Spring client observation preserves the URI template passed to the request. Passing an already-expanded path string causes the instrumented client to treat that expanded string as the template, producing distinct `uri` values. With overloads accepting a pre-built `java.net.URI`, some clients fall back to `uri="none"` when template metadata is missing, depending on implementation: **never** assume raw paths get normalized automatically. Keep the URI template intact when building the request.

### 6.6. application.properties

~~~properties
# Run locally so /actuator is not exposed to the network.
server.address=127.0.0.1
server.port=8080

# Expose only the endpoints needed for observation in the lab.
management.endpoints.web.exposure.include=health,metrics,prometheus

# Safety guardrail for the number of HTTP meter uri label values.
management.metrics.web.server.max-uri-tags=40
management.metrics.web.client.max-uri-tags=40

# Low-cardinality static tag, helpful for distinguishing services.
management.metrics.tags.application=uri-cardinality-demo
~~~

**Notes:**

- `server.address=127.0.0.1` restricts the listener to loopback for the lab; production requires appropriate network/IAM/firewall policies and secured management endpoints.
- `management.metrics.web.server.max-uri-tags` and `management.metrics.web.client.max-uri-tags` exist in Boot 4.1 properties; 40 is intentionally low to illustrate the **guard**, not a universal threshold for every system.
- The guard caps the number of **unique URI tag values** admitted to those meters; once exceeded, metrics with **new tag values** are dropped. It does **not** fix bad labels and cannot infer the right template automatically. In systems with many valid routes, setting the cap too low silently drops observability for newer routes.
- Protect `/actuator/metrics` and `/actuator/prometheus` via network/access control in production. Never open `/actuator/**` to the Internet.
- `/actuator/metrics` is a **diagnostic** endpoint, not the primary Prometheus scrape target; `/actuator/prometheus` emits Prometheus scrape format.

### 6.7. Running Maven

Inside `uri-cardinality-demo`:

~~~bash
mvn spring-boot:run
~~~

The app listens on port 8080 at `127.0.0.1`. From another terminal:

~~~bash
curl -i http://127.0.0.1:8080/api/ping
curl -i http://127.0.0.1:8080/api/users/1
curl -i http://127.0.0.1:8080/api/users/2
curl -i http://127.0.0.1:8080/api/orders/99
curl -i "http://127.0.0.1:8080/api/search?q=java"
~~~

Expected body for GET `/api/ping` is:

~~~text
pong
~~~

Expected bodies for GET `/api/users/1` and `/api/users/2` are, respectively:

~~~text
user=1
user=2
~~~

Headers, timeouts, and `curl -i` formatting vary; the lines above represent the controller's **response body**, not full stdout.

### 6.8. Sending Many Raw URLs While Producing Few URI Label Values

Bash/POSIX:

~~~bash
for i in $(seq 1 100); do
  curl -fsS -o /dev/null \
    "http://127.0.0.1:8080/api/users/$i"
done
~~~

This sends 100 requests, all matching the **same** `@GetMapping("/api/users/{userId}")`. The goal is for the HTTP server metrics URI label to stay `/api/users/{userId}` instead of creating 100 distinct IDs. Request count increases while distinct URI label values for this route stay at **one**.

On Windows PowerShell:

~~~powershell
1..100 | ForEach-Object {
    curl.exe -fsS -o NUL "http://127.0.0.1:8080/api/users/$_"
}
~~~

PowerShell does not use `$(seq 1 100)` as Bash does; choose the command matching your OS. `curl.exe` only sends requests and does not create metrics directly.

### 6.9. Reading Actuator Metrics

~~~bash
curl -s http://127.0.0.1:8080/actuator/metrics
curl -s http://127.0.0.1:8080/actuator/metrics/http.server.requests
~~~

The first endpoint returns meter names; the second returns measurements and `availableTags` for `http.server.requests`. Within it you should see URI values:

~~~json
{
  "name": "http.server.requests",
  "availableTags": [
    {
      "tag": "uri",
      "values": [
        "/api/users/{userId}",
        "/api/orders/{orderId}",
        "/api/search",
        "/api/ping"
      ]
    }
  ]
}
~~~

**This JSON is abbreviated for illustration**: counts/ordering of `availableTags` and other tags depend on actual requests, Actuator endpoints, framework/proxy behavior, and version. Do not assume the entire response matches this snippet verbatim. Look for `availableTags` with `tag="uri"` and verify neither `/api/users/1` nor `/api/users/2` appears.

Drill down on a braced route using URL-encoded query parameters:

~~~bash
curl -sG \
  --data-urlencode 'tag=uri:/api/users/{userId}' \
  http://127.0.0.1:8080/actuator/metrics/http.server.requests
~~~

With this tag filter, `COUNT` (if present) reflects all requests matching the route rather than creating one meter per ID. If no traffic has hit that route yet, the meter may not exist yet, as most metrics register on demand.

### 6.10. Prometheus Exposition

~~~bash
curl -s http://127.0.0.1:8080/actuator/prometheus
~~~

You should find lines like:

~~~text
http_server_requests_seconds_count{method="GET",status="200",uri="/api/users/{userId}",...} 102
~~~

This is a **representative line**—`...` is not literal Prometheus exposition syntax; actual labels also include `application`, `error`/`outcome`, and exporter-specific ordering. `102` simply illustrates 100+ requests having been sent, not a mandatory exact count across all runs. Never use `...` wildcard syntax as a literal test assertion.

In Prometheus, the metric name is typically exported as `http_server_requests_seconds_count` along with `_sum` (and `_bucket` if histograms are enabled). Check real output at `/actuator/prometheus`, as conventions and timer units can vary with backend or meter configuration.

### 6.11. HTTP Client URI Templates in Metrics

Call a few IDs:

~~~bash
curl -i http://127.0.0.1:8080/api/demo-client/10
curl -i http://127.0.0.1:8080/api/demo-client/20
curl -i http://127.0.0.1:8080/api/demo-client/30
curl -s http://127.0.0.1:8080/actuator/metrics/http.client.requests
~~~

`RestClient` sends requests with concrete IDs over the wire, yet code supplies the template `/api/users/{userId}`. Client observation low-cardinality `uri` uses that template, with `client.name` identifying the host. Meanwhile, HTTP server metrics record two distinct route patterns: `/api/demo-client/{userId}` for the inbound call and `/api/users/{userId}` for the internal self-call.

**Do not confuse them:** two HTTP server requests are processed per call to `/api/demo-client/{userId}` (the initial call plus the self-call). This is solely a demo to observe server and client instrumentation together, not a production microservice pattern.

### 6.12. 404 with a Matched Route vs. Unmatched Path

~~~bash
curl -i http://127.0.0.1:8080/api/users/missing-7
curl -i http://127.0.0.1:8080/not-a-real-path-12345
curl -s http://127.0.0.1:8080/actuator/metrics/http.server.requests
~~~

The first request matches the controller pattern and throws `ResponseStatusException(HttpStatus.NOT_FOUND)`; metrics can record `uri="/api/users/{userId}"`, `status="404"`. The second request has no mapping and typically falls back to `uri="NOT_FOUND"`. If proxies, custom error handlers, or special servlet filters are active, verify actual output rather than assuming behavior.

If another app version has a Security filter rejecting before route matching, you may see `UNKNOWN` as in Section 5.2. **Never fix that with raw request paths.**

## 7. The `max-uri-tags` Guardrail in Spring Boot 4

### 7.1. Using Properties

Example:

~~~properties
management.metrics.web.server.max-uri-tags=100
management.metrics.web.client.max-uri-tags=100
~~~

In Spring Boot 4, this caps the number of unique `uri` tag values on the respective meter. Once the ceiling is reached, metrics with **new tag values** are denied registration by the filter. This protects against metric ID explosion; it does not collapse 1,000 raw paths into a single route template, nor does it reclaim already registered series.

If an app legitimately has more than 100 URI patterns, a cap of 100 will silently drop metrics for additional valid endpoints. Size the cap from real route count + growth headroom + fallbacks, monitor actual series counts, and alert when the guard trips. **Do not blindly raise it to one million** just to silence warnings.

### 7.2. Using `MeterFilter` for Custom Policies

Micrometer supports `MeterFilter` beans. Spring Boot 4 provides `MaximumAllowableTagsMeterFilter` to cap tag values for a meter prefix and log a warning when exceeded.

Optional class **instead of** the property guard in the main demo:

~~~java
package com.example.urimetrics;

import io.micrometer.core.instrument.config.MeterFilter;

import org.springframework.boot.micrometer.metrics.MaximumAllowableTagsMeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CardinalityGuardConfiguration {

    @Bean
    MeterFilter serverUriCardinalityGuard() {
        return new MaximumAllowableTagsMeterFilter(
                "http.server.requests", "uri", 80,
                "Check raw URL usage in low-cardinality URI tags");
    }
}
~~~

This class **can be added to the project** if you remove the duplicate guard property or coordinate both intentionally. Constructor and package follow Spring Boot 4.x APIs, which differ from some Boot 3.x classes/packages.

**Note:** The filter guards meter registration, not URL routing. Once series are denied, dashboards for newer endpoints go blind. Fix the producer/convention causing label explosion and add regression tests; the filter alone does not guarantee complete observability.

### 7.3. Never Abuse Caps to Mask Data Bugs

An anti-pattern:

~~~text
Problem: raw URIs created 100,000 label values.
Patch: max-uri-tags = 10.
Result: 100,000 series disappear, yet metrics for later routes
get dropped once the first 10 values exhaust the budget.
~~~

Corrective action:

1. Locate the source of raw URL/ID labels.
2. Switch code/convention/client calls to URI templates.
3. Add allowlists/normalization based on **known route metadata**, not ad-hoc regexes.
4. Only then set a guard sized to a realistic budget.
5. Test with 100–1,000 distinct IDs and verify `uri` stays a single route.
6. Monitor denied meters/guard warnings and series counts after deployment.

## 8. Never Put Raw URLs into Custom Metrics

### 8.1. Anti-Pattern in a Custom Micrometer Timer

~~~java
// WRONG: every user ID creates a new tag value.
Timer.builder("myapp.user.lookup")
        .tag("uri", "/api/users/" + userId)
        .register(meterRegistry)
        .record(() -> lookupUser(userId));
~~~

This is a **fragment** (assuming `userId`, `lookupUser`, and `meterRegistry` exist in the app), not a standalone Java file. With 1 million users, timer series grow per ID for the exact same operation.

Better approach in this scenario:

~~~java
// RIGHT: use a fixed route template.
Timer.builder("myapp.user.lookup")
        .tag("uri", "/api/users/{userId}")
        .register(meterRegistry)
        .record(() -> lookupUser(userId));
~~~

Even better, if this just measures an ordinary HTTP request, **do not create a duplicate custom Timer** alongside `http.server.requests`. Add custom business metrics only when measuring a distinct, meaningful operation.

### 8.2. Never Attach Sensitive Labels

Avoid:

~~~text
user_id      = "54839293"
email        = "someone@example.test"
session_id   = "abc..."
order_id     = "order-789123"
path         = "/payments/credit-card-number"
access_token = "eyJ..."
query        = "password=..."
~~~

Even at small scale, these values leak through dashboards and metric exports. To investigate a single request, use **trace IDs/log correlation** backed by access controls, retention, redaction, and privacy policies—never abuse metric labels for per-user lookup.

### 8.3. Custom Conventions: Keep Data Bounded

In Spring MVC, to adjust low-cardinality KeyValues, provide a bean extending `org.springframework.http.server.observation.DefaultServerRequestObservationConvention` or implementing `ServerRequestObservationConvention`. In WebFlux, the reactive package differs.

A safe custom convention should:

- Preserve `uri` from the matched route pattern whenever available.
- Use bounded fallbacks like `NOT_FOUND`/`UNKNOWN` for unmatched endpoints, never raw paths.
- If adding `feature`, choose from a finite enum like `catalog|checkout|auth|other` derived from controlled business routing.
- Never add `userId`, email, request headers, queries, or raw URLs.
- Include tests verifying tag values stay constant as request IDs vary.
- Remember that overriding defaults carelessly in a custom convention can drop essential standard tags if not extended properly.

Never recommend "just regex-parse `request.getRequestURI()`" into a template when Spring already provides matched route patterns. Regexes break easily on UUIDs, encoded slashes, API versions, nested paths, trailing slashes, and non-existent paths.

### 8.4. Route Cardinality Can Still Grow Even With Templates

IDs are not the only culprit. If an application dynamically registers thousands of **literal routes**, each with its own fixed path string, even genuine route templates become high cardinality. For example:

~~~text
/tenant-one/reports
/tenant-two/reports
/tenant-three/reports
...
~~~

If each tenant gets its own static handler mapping path, the pattern label varies per tenant. Designing the API around `/tenants/{tenantId}/reports` or stable route groups keeps cardinality bounded, provided authorization and routing remain sound. Do not break public APIs solely for metrics without assessing compatibility.

## 9. HTTP Client Instrumentation: RestClient, RestTemplate, WebClient

Spring Framework records outbound HTTP observations under `http.client.requests` with low-cardinality keys such as `method`, `uri`, `client.name`, `status`, `outcome`, and `error`. `uri` relies on the **URI template supplied by client code** when available; when absent, it may fall back to `none`.

### 9.1. Good vs. Bad RestClient Usage

~~~java
// Fragment; requires existing RestClient client and String userId.
client.get()
        .uri("/users/{id}", userId)
        .retrieve()
        .body(String.class);             // Preserves URI template

client.get()
        .uri("/users/" + userId)
        .retrieve()
        .body(String.class);             // Expanded string, easily explodes uri tags
~~~

Although both emit identical HTTP paths over the wire, instrumentation records different tags. **"The template must exist when building the request"**—do not try to patch raw paths later in an exporter.

### 9.2. RestTemplate

~~~java
// Fragment; RestTemplate configured with ObservationRegistry.
restTemplate.getForObject(
        "https://service.example.test/users/{id}",
        String.class,
        userId);
~~~

Passing a pre-constructed `java.net.URI` drops template metadata, causing `uri` to fall back to `none` per client semantics. `none` has low cardinality yet **loses endpoint granularity**, which is suboptimal when passing templates is straightforward.

### 9.3. WebClient

~~~java
// WebClient fragment returning Mono<String> in a reactive pipeline.
Mono<String> result = webClient.get()
        .uri("/users/{id}", userId)
        .retrieve()
        .bodyToMono(String.class);
~~~

Spring Boot configures `WebClient.Builder` with `ObservationRegistry` when the appropriate starters/dependencies are present. Avoid manually instantiating clients/connectors/observation registries in ways that drop configuration, causing `http.client.requests` to vanish and leading you to blame metrics instrumentation.

### 9.4. `client.name` Can Also Become High Cardinality

When an HTTP client calls a fixed set of hostnames, `client.name` is a valuable tag. However, if an app fetches arbitrary user-provided URLs, it can spawn unbounded hostnames:

~~~text
client.name = random1.example
client.name = random2.example
client.name = random3.example
...
~~~

Enforce guards, allowlists, egress policies, SSRF protections, and metric budgets. Capping `uri` alone is insufficient if other tags grow unboundedly. Do not strip `client.name` indiscriminately if it aids troubleshooting; restrict to stable host groups or managed service names.

## 10. Prometheus: Reading Metrics and Counting Series

Micrometer's `http.server.requests` typically exports to Prometheus series named `http_server_requests_seconds_count` and `http_server_requests_seconds_sum`, plus `_bucket` when histograms are enabled. Actuator's metrics endpoint keeps the **logical dot name**, while the exporter applies naming normalization.

### 10.1. Traffic by Route

~~~promql
sum by (uri) (
  rate(http_server_requests_seconds_count[5m])
)
~~~

This query shows requests/second per route template. If `uri` held raw IDs, you would get tens of thousands of series; with templates, one line represents one endpoint.

### 10.2. 5xx Ratio by Route

~~~promql
sum by (uri) (
  rate(http_server_requests_seconds_count{status=~"5.."}[5m])
)
/
clamp_min(
  sum by (uri) (rate(http_server_requests_seconds_count[5m])),
  1e-9
)
~~~

The result is a **decimal ratio** (e.g., 0.02 ≈ 2%) per route over 5 minutes. For routes with zero 5xx errors, the numerator vector omits those routes; dashboards must handle absent series rather than assuming zero values appear automatically. Never lump `UNKNOWN` together with a specific endpoint and attribute errors to it.

### 10.3. P95/P99 with Histograms

When timer histograms are enabled:

~~~properties
# Production option after evaluating series cost.
management.metrics.distribution.percentiles-histogram.http.server.requests=true
~~~

Illustrative PromQL:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, uri) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
~~~

Do not turn on histograms across every metric/tag combination without calculating series budgets. Histograms add substantial numbers of bucket series. If your metric name, exporter, or native histogram backend differs, adapt the query to actual data. Measuring latency per template supports meaningful aggregation; computing p95 per user ID is expensive and statistically sparse.

### 10.4. Counting Distinct URI Values Present

~~~promql
count(
  count by (uri) (http_server_requests_seconds_count)
)
~~~

This counts **distinct `uri` label values currently present** in the series vector at query time—not the total URI patterns declared in source code, and excluding values rejected by filters or routes without traffic. Also monitor total active series per job:

~~~promql
count(http_server_requests_seconds_count)
~~~

Always filter by `job`/`namespace`/`instance` in shared Prometheus servers to avoid mixing series across unrelated applications.

### 10.5. Scrape Volume and Retention

Label explosion causes a single app to inflate:

- Number of active time series.
- Scrape payload bytes/duration and scrape timeouts.
- Rate of new series / churn.
- Prometheus head-block memory and remote-write queues/latency.
- Chunk storage and retention bills.
- Dashboard query latency.

Backend ingestion limits do not fix the **source** problem if the JVM still creates excessive meters. Fixing cardinality at instrumentation is priority number one.

## 11. When Not to Turn a Metric into a Trace or Log

The three observability pillars answer different questions:

| Layer | Purpose | Should it hold concrete URIs? |
| --- | --- | --- |
| **Metrics** | Totals, latency, error ratios by route/method/status | **No**; use route templates |
| **Traces** | Request journey across services, span attributes | May include higher detail, **must enforce redaction and sampling** |
| **Logs** | Specific diagnostic/behavioral events | May include paths, IDs, `traceId`, subject to PII/token/retention controls |

To answer "What time did User X get a 404?", tagging metrics with User X is the wrong tool. Use correlation IDs and access-controlled request logs/traces with sensitive fields masked. If you need top-10 tenants by error count, use business analytics or pre-aggregated bounded groups instead of turning every tenant ID into a metric label.

### 11.1. Observation Low vs. High Cardinality

Never write:

~~~java
// WRONG illustrative fragment: request/user ID as a low-cardinality meter value.
observation.lowCardinalityKeyValue("user.id", userId);
~~~

If an identifier is needed on traces, evaluate privacy policies and use **high-cardinality attributes** protected by trace processors—never dump arbitrary PII into tracing. Exact code depends on observation lifecycle, span exporters, and data privacy controls.

## 12. HTTP 404/401, Static Resources, Redirects, and Gateways

### 12.1. HTTP Responses Before Matching

CORS preflight, Spring Security, Servlet filters, gateway rejections, and early error responses can terminate a request before MVC/WebFlux handler mapping runs. Without a known route template, `uri` may be `UNKNOWN` or another fallback. Never force raw request URIs into metrics just to eliminate `UNKNOWN`.

### 12.2. Static Files

Static resources may be served by a broad pattern like `/**` or a resource handler mapping. Depending on framework/version, static file URI tags may be a broad template or fallback. Verify actual runtime behavior; never override them with per-asset fingerprinted/hashed paths.

Fingerprinted assets such as:

~~~text
/assets/app.abc123.js
/assets/app.def456.js
~~~

multiply values after every deployment if placed verbatim into tags. Tag static resources under a single `static` group or skip per-file metrics when not tied to an SLO.

### 12.3. API Gateways and Ingress

A request can pass through:

~~~text
Browser -> CDN/Ingress -> API Gateway -> Spring Boot Controller
~~~

Each layer maintains its own metric labels. An ingress `path` tag uses its own configured route patterns and has no knowledge of `@GetMapping` inside the JVM. If the ingress labels metrics using raw request paths, cardinality still explodes even when Spring Boot metrics are clean.

Audit every instrumentation layer separately: Prometheus scrape jobs, service mesh, Envoy/Nginx exporters, and API gateway labels. A bug in another layer is not solved by Spring Boot's `management.metrics.web.server.max-uri-tags`.

### 12.4. Path Encoding and Request Normalization

Risks of hand-rolled path parsing:

- Percent-encoded slashes and Unicode normalization.
- Trailing slashes and letter casing.
- Matrix variables and path parameters.
- Spring MVC servlet path/context path.
- Proxy rewrites, version prefixes, and internal forwards.
- Spring Security 401/403 before controllers.
- Requests with no matching handler.

Rely on **framework matching metadata**, never ad-hoc "regex replacing numbers/UUIDs" to synthesize metric tags. If a gateway needs its own policy, maintain managed route/operation names and test edge cases thoroughly.

## 13. Designing Labels with a Finite Budget

It is not only `uri`: every label risks multiplying cardinality.

### 13.1. Useful Labels for HTTP Server Metrics

Examples:

- `method` (GET, POST, ...).
- `uri` (managed route pattern/operation name).
- `status` or `outcome` (bounded values).
- `application`, `region`, `environment` (small, controlled sets).
- `error` as class name if finite and free of arbitrary messages.

Beware `exception` tags: standard class names are bounded, yet plugins or dynamic wrappers can proliferate. Never put stack traces, exception messages, or SQL text into tags.

### 13.2. Labels to Avoid

- `userId`, `orderId`, `sessionId`, `traceId`, `requestId`.
- Dynamic hostnames from user-supplied URLs.
- Query text, emails, phone numbers, caller IPs.
- Tokens, API keys, cookies, arbitrary headers.
- Full exception messages, full SQL queries, raw request paths.
- File names/fingerprints when asset names change on every deploy.
- Labels copied unallowlisted from arbitrary HTTP headers or MDC.

If grouping by tenant tier is needed:

~~~text
tenant_tier = "free" | "standard" | "enterprise" | "unknown"
~~~

this has far lower cardinality than hundreds of thousands of tenant IDs. Even then, verify correctness, access controls, privacy, and whether dashboards truly need the new label.

### 13.3. Cardinality Budget and Acceptance Criteria

Example service policy:

| Item | Test criterion |
| --- | --- |
| Unique `uri` values | Roughly matches route templates plus bounded fallbacks; does not scale with IDs |
| Active series per service | Below Prometheus/backend ceiling |
| Request volume | 100,000 requests with distinct IDs do not create 100,000 route labels |
| Error labels | Free of raw URLs, tokens, emails |
| New deployment | No unbounded series growth from deploy hashes/asset fingerprints |
| Route cap | Metrics/logs emit signals when `max-uri-tags` filter denies registrations |
| Client metrics | Stable URI templates; bounded `client.name` |
| Scrape | Duration and payload size within SLO |

**Do not enforce one fixed budget across every system.** A 10-route microservice differs from a 1,000-route gateway, though neither should emit one metric series per customer. Budgets depend on labels, histograms, replica counts, scrape intervals, and retention.

## 14. CI/QA: Testing Cardinality Rather Than Just HTTP 200

### 14.1. Testing with Traffic and Actuator

A useful integration test can:

1. Start the Spring Boot app with Actuator enabled.
2. Send many distinct IDs to the same endpoint pattern.
3. Read `/actuator/metrics/http.server.requests` or inspect the Spring-managed `MeterRegistry`.
4. Assert tag `uri="/api/users/{userId}"` exists.
5. Assert tags `uri="/api/users/1"`, `uri="/api/users/2"`, ... do **not** exist.
6. Send a non-existent path and assert the fallback contains no raw path.
7. If Spring Security is enabled, test that a pre-handler 401 does not turn the raw URL into a metric tag.
8. For outbound clients, test `RestClient`/`WebClient` URI templates.
9. Test the cap property when template count exceeds the limit and confirm operational warnings fire rather than failing silently.

### 14.2. JUnit/Micrometer Snippet Checking Registry Tags

In a project with Spring Boot test dependencies and test framework, verify inside an integration context:

~~~java
// Test fragment: requires MeterRegistry, MVC test setup, and sent traffic.
// Not a standalone Java file.
Collection<Meter> meters = meterRegistry.find("http.server.requests").meters();

boolean hasTemplate = meters.stream()
        .anyMatch(m -> "/api/users/{userId}".equals(m.getId().getTag("uri")));

boolean hasRawPath = meters.stream()
        .anyMatch(m -> {
            String uri = m.getId().getTag("uri");
            return uri != null && uri.matches("/api/users/[0-9]+");
        });

assertTrue(hasTemplate);
assertFalse(hasRawPath);
~~~

Requires imports for `io.micrometer.core.instrument.Meter`, `MeterRegistry`, `java.util.Collection`, and JUnit assertions. Route real requests through web instrumentation; direct controller unit tests bypass `ObservationFilter` and give **false confidence** on metrics.

### 14.3. Do Not Treat `uri=UNKNOWN` as an Automatic Bug

When an auth filter returns 401 before MVC routing, the expected tag can be `UNKNOWN`. Tests should reflect lifecycle reality and **not** demand an unresolved route pattern. The invariant being protected is **no high-cardinality labels**, not forcing every request to carry a controller pattern.

### 14.4. When the Cap Blocks New Meters

If a metric disappears after high traffic, check:

- `max-uri-tags` / meter filter deny warnings.
- Custom conventions, dynamic routing, and raw URI tags.
- Changes in method/status labels and metric names.
- Actual registry and Prometheus scrape endpoint output.
- Actuator exposure/security/network configuration.
- Whether framework version and observation instrumentation remain enabled.

Never bump the cap hastily before diagnosing the root cause.

## 15. Troubleshooting: Finding the Source of Cardinality Explosion

### Symptoms

- Prometheus series count grows with user/request count rather than route count.
- `availableTags.uri.values` lists `/api/users/123`, `/api/users/124`, ...
- Scrapes grow huge or remote-write lags.
- Outbound `http.client.requests` contains many dynamic hostnames.
- New deployments spike JVM heap and metrics memory.
- Logs warn about meter tag limits.
- Latency metrics for newly added routes vanish because earlier values exhausted the cap.

### Resolution Steps

1. Identify the **metric name** and label with the highest cardinality from Prometheus/Actuator.
2. Distinguish whether raw paths originate from Spring Boot or a proxy/ingress exporter.
3. Audit custom `ObservationConvention`, `MeterFilter`, and any `Timer.builder(...).tag(...)` calls.
4. For HTTP clients, search for `.uri("/path/" + id)` or `URI.create(...)` used instead of URI templates.
5. For HTTP servers, inspect handler mappings, dynamic routes, pre-handler 404/401s, and custom instrumentation reading raw `requestURI`.
6. Fix code to use route metadata or constant templates before adjusting caps.
7. Check privacy: labels that leaked PII/tokens may already reside in TSDB/remote storage; trigger data retention/incident response per policy.
8. Re-run load tests with varying IDs and count URI values and series counts.
9. Maintain sensible guards and alert when caps trip, while checking for dropped metrics.
10. After deploy, monitor JVM `MeterRegistry`, exporter series count, and backend scrape performance.

### Common Pitfalls

| Error | Cause | Fix |
| --- | --- | --- |
| `uri="/users/1"`, `uri="/users/2"` | Raw path tag or dynamic client URI string | Use route templates |
| Client `uri=none` | Client lacks URI template metadata | Pass templates with placeholders |
| `uri=UNKNOWN` on 401 | Security blocked prior to route matching | Accept fallback; use security metrics/logs |
| `uri=NOT_FOUND` on random 404s | No matching route | Normal behavior; do not swap in raw path |
| Metrics lost after URI cap | Meter filter rejected new values | Fix cardinality at source, size cap properly |
| Grafana shows no per-user latency | Expected—metrics aggregate by route, not user | Use access-controlled traces/logs |
| Post-deploy series spike | Many literal templates, asset hashes, or client hosts | Audit routes and exporter tags |
| Custom convention missing status | Replaced full key set without keeping defaults | Extend default convention properly |
| Prometheus query finds no meter | Not scraped yet, renamed, or no traffic yet | Check `/actuator/prometheus` and registry |
| One route has multiple status series | Method/status are separate dimensions | Intentional breakdown |
| High CPU with histograms enabled | Every tag combination generates buckets | Restrict routes/tags/buckets |
| Raw URL appears in traces | High-cardinality attributes capture detail | Apply scrubbing/sampling/access controls |

## 16. Production Checklist

- [ ] `http.server.requests` uses route templates or bounded fallbacks, never raw IDs/URLs.
- [ ] `http.client.requests` uses URI templates on `RestClient`/`WebClient`/`RestTemplate` whenever possible.
- [ ] Never put `userId`, free-form `tenantId`, `sessionId`, email, tokens, queries, IPs, or `traceId` into low-cardinality meter labels.
- [ ] Never promote high-cardinality `http.url` trace keys into metric labels.
- [ ] Define policy for pre-handler 404/401s without forcing raw paths into tags just to hide `UNKNOWN`.
- [ ] Use Spring MVC/WebFlux defaults or tested custom observation conventions.
- [ ] Configure `max-uri-tags` aligned with real route counts and alert when meters are denied.
- [ ] Budget separately for histogram buckets, additional labels, and instance counts.
- [ ] Protect Actuator metrics/prometheus rather than exposing all management endpoints publicly.
- [ ] Monitor active series, new series churn, scrape duration/bytes, and remote-write backlogs.
- [ ] Maintain tests firing hundreds of distinct IDs while verifying URI tag values do not grow linearly.
- [ ] Add checks for dynamic routes and `client.name` host cardinality.
- [ ] Apply masking/retention/authorization to trace/log URLs.
- [ ] Build dashboards on stable URI templates, never per-user PromQL.
- [ ] On incidents, fix instrumentation at the source rather than merely raising memory or caps indefinitely.

## 17. Self-Check Questions with Answers

**Question 1.** Why should `/api/users/1` and `/api/users/2` share the same `uri="/api/users/{userId}"` label?

**Answer:** Because they belong to the same endpoint route pattern. Tagging by ID scales time series with user count instead of endpoint count, driving up cost and PII exposure.

**Question 2.** Can you pass `request.getRequestURI()` into a custom low-cardinality `uri` key to eliminate `UNKNOWN`?

**Answer:** No. Raw request URIs can grow unboundedly with IDs, query/URL variations, and 404 scanner paths; rely on route patterns or bounded fallbacks.

**Question 3.** Is `http.url` a default HTTP server metrics label?

**Answer:** Spring Observation treats it as a high-cardinality key suitable for tracing; it is **not** added verbatim to metric tags.

**Question 4.** Why can Boot 4 emit `uri=UNKNOWN` for HTTP 401?

**Answer:** Security can respond before Spring MVC matches a route template; do not guess patterns from raw paths to fill it in.

**Question 5.** Does `management.metrics.web.server.max-uri-tags=40` automatically rewrite 1,000 IDs into one template?

**Answer:** No. It drops new values once the cap is exceeded; you must fix route/client instrumentation and ensure 40 covers legitimate routes.

**Question 6.** Should a query string like `?email=a@example.test` be used as a metrics label?

**Answer:** No. It carries high cardinality and PII. Use route templates and, if classification is required, allowlisted bounded categories.

**Question 7.** If a controller returns HTTP 404 after route matching, will it always be tagged `uri=NOT_FOUND`?

**Answer:** No. Once mapping succeeds, it can retain the matched template alongside `status=404`. `NOT_FOUND` applies when no handler matched.

**Question 8.** Why can calling `.uri("/users/" + id)` on `RestClient` cause tag explosion?

**Answer:** Because client observation may treat the expanded URL string as the template. Pass `.uri("/users/{id}", id)` to preserve the pattern.

**Question 9.** When Prometheus accumulates millions of series from URI paths, is increasing JVM heap sufficient?

**Answer:** No. The bloat also impacts the exporter, Prometheus storage/scrapes, remote write, and dashboards. Fix tags at the source.

**Question 10.** If an endpoint emits 20 histogram buckets, should you also attach user ID as a tag?

**Answer:** No. Buckets multiply across tag combinations, worsening series explosion. Optimize label budgets and histogram configuration per SLO.

## 18. Official Documentation

- [Spring Boot — Metrics and Micrometer](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) — `http.server.requests`, `http.client.requests`, Actuator diagnostics, `MeterFilter`.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/) — `management.metrics.web.server.max-uri-tags` and client equivalent.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html) — exposure, access, and Prometheus endpoint.
- [Spring Boot — Enabling Production-ready Features](https://docs.spring.io/spring-boot/reference/actuator/enabling.html).
- [Spring Boot 4.1.2 API — MaximumAllowableTagsMeterFilter](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/micrometer/metrics/MaximumAllowableTagsMeterFilter.html).
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html) — low/high cardinality, MVC/WebFlux servers, RestClient/WebClient.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html) — URI templates and variables.
- [Spring Boot 4.1.2 Release](https://spring.io/blog/2026/10/23/spring-boot-4-1-2-available-now/).
- [Spring Security/Boot discussion — 401 uri UNKNOWN in Boot 4](https://github.com/spring-projects/spring-boot/issues/49640).
- [Micrometer — Concepts: Naming Meters and Tags](https://docs.micrometer.io/micrometer/reference/concepts/meters.html).
- [Micrometer — Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html).
- [Prometheus — Data Model: Metric Names and Labels](https://prometheus.io/docs/concepts/data_model/).
- [Prometheus — Histograms and Summaries](https://prometheus.io/docs/practices/histograms/).
- [Prometheus — Querying](https://prometheus.io/docs/prometheus/latest/querying/basics/).

**Takeaway:** HTTP metrics should answer "which endpoint is slow or failing", not "which ID was requested". **The `uri` label must be a route template** like `/api/users/{userId}` or a bounded fallback—never raw paths, queries, or PII. Spring MVC and WebFlux provide default instrumentation doing this once handler mapping succeeds; early 401/404/redirect responses may use `UNKNOWN`/`NOT_FOUND`/`REDIRECTION`. Supply URI templates when building outbound `RestClient`/`WebClient` calls, configure `max-uri-tags` guardrails, and monitor active series and histogram buckets. When labels explode, fix instrumentation **at the source** instead of endlessly raising memory or caps.