# Simulating an Unhealthy Instance and Recovery for Verification

A call to `http://catalog-service/api/items` may succeed at first, fail when an instance hits an outage, and succeed again once the instance recovers. **Spring Cloud LoadBalancer does not automatically know the exact instant an instance breaks or recovers**: it chooses from the `ServiceInstance` list provided by its supplier, while discovery, health checks, caching, and update cycles determine when that candidate set changes.

This hands-on lab belongs to the **Instance Health** chapter of the **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING** module. We will set up **two instances under the same service ID**, induce a controlled health failure on one instance, observe traffic shifting to the remaining healthy instance, bring the failing instance back up, and verify it re-enters the candidate pool. Throughout the lab, the lesson connects instance selection with **service discovery, health checks, routing policies**, as well as the behavior of **RestClient, WebClient, OpenFeign, timeouts, retries, and observability**.

The results should distinguish three cases:

1. **Probe fails while the process keeps running:** the health supplier can mark the instance unsuitable even though business endpoints can still respond.
2. **Process or network fails:** HTTP requests sent to a selected instance can hit connection refused or timeouts before the health supplier updates.
3. **Instance recovers:** only after health/discovery updates and the instance re-enters the list can the selector resume using it.

> All state-mutating endpoints in this lesson are strictly for local testing environments. Never deploy this kind of fault-injection endpoint publicly in production.

## 1. Experiment Architecture and Hypothesis

The system has one caller and two instances of the same logical service:

| Component | Local port | Role |
|---|---:|---|
| `caller-service` | `18090` | Calls URLs by service ID via a LoadBalancer-backed RestClient |
| `catalog-a` | `18081` | Instance A of `catalog-service` |
| `catalog-b` | `18082` | Instance B of `catalog-service` |

Both A and B are logically registered under the same service ID `catalog-service` in static discovery configuration. Each instance exposes:

- `GET /internal/lb-health`: returns `200 OK` when healthy and `503 Service Unavailable` when marked unhealthy.
- `GET /api/whoami`: returns the identifier of the instance that actually handled the request.
- `POST /__test/ready?healthy=false|true`: toggles probe state to simulate failure and recovery.

We use `HealthCheckServiceInstanceListSupplier` to detect changes from the health endpoint. Examples run in a local test environment without requiring Eureka or Kubernetes.

~~~mermaid
flowchart LR
    U["curl / test client"] --> CALLER["caller-service :18090"]
    CALLER --> LB["Spring Cloud LoadBalancer"]
    DISC["SimpleDiscoveryClient: A, B"] --> HEALTH["HealthCheckServiceInstanceListSupplier"]
    HEALTH --> LB
    HEALTH -. "GET /internal/lb-health" .-> A["catalog-a :18081"]
    HEALTH -. "GET /internal/lb-health" .-> B["catalog-b :18082"]
    LB --> A
    LB --> B
~~~

**Hypothesis:** in steady state, after health information updates, both A and B can receive requests; when B returns health `503`, new requests shift preferentially to A; when B returns to `200`, B gets selected again. Actual results must be verified through logs and supplier lists rather than relying on a single request.

## 2. Participating Layers and Each Layer's Limits

| Layer | What does it know? | What does it not guarantee? |
|---|---|---|
| `SimpleDiscoveryClient` | A and B are configured as instances of the same service ID | Does not automatically remove B when health changes inside the app |
| `HealthCheckServiceInstanceListSupplier` | Probe results updated according to configured mechanism and interval | Cannot guarantee every business HTTP request will succeed |
| `RoundRobinLoadBalancer` | The candidate list currently supplied | Does not run probes or inspect CPU itself |
| `RestClient` | Sent HTTP request and returned response/exception | Does not resolve service IDs on its own without LoadBalancer integration |
| Caller | Business outcome and error details of the call | Does not immediately see every state change on the server |

The logical order is **discovery → health supplier → selection algorithm → HTTP client**. When B fails, a brief window before the next check can exist during which LoadBalancer still sees B. This is a property of asynchronous state updates, not evidence that Round Robin is malfunctioning.

## 3. Environment Setup

Use **compatible Spring Boot and Spring Cloud versions** managed via a BOM in your project. Never mix incompatible release trains manually.

For the instance project, include at least:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

For the caller project:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
}
~~~

In a real Gradle or Maven build, apply the project's plugins and dependency management/BOM. The `dependencies` snippets above show only lab-specific dependencies, not a complete build file.

You can test the experiment using a browser, Postman, or `curl`; the commands below illustrate `curl`. Prepare three terminals to run the two instances and the caller independently.

## 4. Writing an Instance Application with Toggleable Health

For clear observation, both instances use the **same source code** running on two ports with different `instance.id` values:

~~~java
package demo.catalog;

import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class CatalogInstanceApplication {

    private final AtomicBoolean healthy = new AtomicBoolean(true);

    @Value("${instance.id:catalog-unknown}")
    private String instanceId;

    public static void main(String[] args) {
        SpringApplication.run(CatalogInstanceApplication.class, args);
    }

    @GetMapping("/internal/lb-health")
    public ResponseEntity<Map<String, Object>> health() {
        if (!healthy.get()) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(Map.of("status", "DOWN", "instance", instanceId));
        }
        return ResponseEntity.ok(
            Map.of("status", "UP", "instance", instanceId));
    }

    @GetMapping("/api/whoami")
    public Map<String, String> whoAmI() {
        return Map.of("instance", instanceId, "message", "request received");
    }

    // Enable in local lab only; never deploy this endpoint in production.
    @PostMapping("/__test/ready")
    public Map<String, Object> changeHealth(
            @RequestParam boolean healthy) {
        this.healthy.set(healthy);
        return Map.of("instance", instanceId, "healthy", healthy);
    }
}
~~~

**Why does the business endpoint still succeed when health is turned off?** This is intentional: to prove the health supplier filters on the **caller side**. Setting `healthy=false` only makes the probe endpoint return `503`; `GET /api/whoami` still works if hit directly on the instance. This distinguishes **simulating unhealthy** from **killing the process**.

Assuming the instance artifact is named `catalog-instance.jar`, launch two separate processes:

~~~bash
java -jar catalog-instance.jar --server.port=18081 --instance.id=catalog-a
~~~

~~~bash
java -jar catalog-instance.jar --server.port=18082 --instance.id=catalog-b
~~~

Verify both probes work:

~~~bash
curl -i http://localhost:18081/internal/lb-health
curl -i http://localhost:18082/internal/lb-health
~~~

Initially, both are expected to return HTTP `200` with a body reporting `UP`. If not, check ports, startup logs, port conflicts, and connectivity before proceeding.

## 5. Configuring the Caller with Static Discovery and Health Checks

In the caller's `application.yml`:

~~~yaml
server:
  port: 18090

spring:
  application:
    name: caller-service
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:18081
              - uri: http://localhost:18082
    loadbalancer:
      cache:
        enabled: false
      health-check:
        path:
          catalog-service: /internal/lb-health
        interval: 5s
~~~

Explanation:

- `spring.cloud.discovery.client.simple.instances.catalog-service` declares two addresses representing the same service ID.
- `health-check.path.catalog-service` specifies the probe endpoint for each instance.
- `health-check.interval: 5s` is a reference interval to observe changes in a lab environment; it is not a production recommendation.
- `cache.enabled: false` makes the experiment easier to reason about by not adding LoadBalancer caching as a stale data source. The health supplier still has its own emission and retention mechanism.

Related properties such as initial delay, refetch instances, update results, and timeouts may vary by Spring Cloud version. Check actual configuration properties for your project. Do not assume instances are checked simultaneously the moment the app starts.

### Registering the Health-Check Supplier for the Target Service ID

In the caller application, attach dedicated configuration for `catalog-service`:

~~~java
package demo.caller;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;
import demo.lbconfig.CatalogLbConfiguration;

@SpringBootApplication
@LoadBalancerClient(
    name = "catalog-service",
    configuration = CatalogLbConfiguration.class
)
public class CallerApplication {

    public static void main(String[] args) {
        SpringApplication.run(CallerApplication.class, args);
    }
}
~~~

Create the supplier configuration class:

~~~java
package demo.lbconfig;

import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CatalogLbConfiguration {

    @Bean
    ServiceInstanceListSupplier catalogInstanceListSupplier(
            ConfigurableApplicationContext context) {
        return ServiceInstanceListSupplier.builder()
            .withDiscoveryClient()
            .withHealthChecks()
            .build(context);
    }
}
~~~

Import `demo.lbconfig.CatalogLbConfiguration` into `CallerApplication`. **Place `CatalogLbConfiguration` outside the package tree scanned by Spring Boot from `demo.caller`**, so the specialized supplier bean is not accidentally applied to every service ID. `@LoadBalancerClient` loads this configuration inside the LoadBalancer context dedicated to `catalog-service`.

Use `withDiscoveryClient().withHealthChecks()` rather than adding `withCaching()` to the same chain: the health supplier has its own update lifecycle, and stacking caching makes verifying fresh data harder. This is a minimal lab choice, not a rule replacing every production architecture.

## 6. Creating a Load-Balanced RestClient and Observation Endpoint

The caller needs a `@LoadBalanced`-annotated builder so URLs like `http://catalog-service/...` resolve by service ID instead of local machine DNS.

~~~java
package demo.caller;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class RestClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder restClientBuilder() {
        return RestClient.builder();
    }
}
~~~

Endpoint calling the service:

~~~java
package demo.caller;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
class CatalogCallController {

    private final RestClient catalogRestClient;

    CatalogCallController(RestClient.Builder restClientBuilder) {
        this.catalogRestClient = restClientBuilder.build();
    }

    @GetMapping("/demo/whoami")
    ResponseEntity<String> callCatalog() {
        String body = catalogRestClient.get()
            .uri("http://catalog-service/api/whoami")
            .retrieve()
            .body(String.class);
        return ResponseEntity.ok(body);
    }
}
~~~

This example lets responses or exceptions pass through the controller simply, suitable for lab observation. Production requires explicit HTTP error mapping, timeouts, bounded retries, and handling cases where discovery cannot pick an instance.

After starting the caller, try:

~~~bash
curl -i http://localhost:18090/demo/whoami
~~~

A successful response will contain `catalog-a` or `catalog-b` in the body. This result comes from **the instance that actually received the request**, not from a LoadBalancer cache.

## 7. Scenario A — Both Instances Healthy

Follow these steps:

1. Confirm both `localhost:18081/internal/lb-health` and `localhost:18082/internal/lb-health` return `200`.
2. Start the caller and wait for the first health cycle to update the list.
3. Send a series of requests to `http://localhost:18090/demo/whoami`.
4. Record how many times `catalog-a` and `catalog-b` appear.

Example command in a Bash-compatible shell:

~~~bash
for i in $(seq 1 12); do
  curl -s http://localhost:18090/demo/whoami
  echo
done
~~~

If using PowerShell instead of Bash, you can run:

~~~powershell
1..12 | ForEach-Object {
  Invoke-RestMethod -Uri "http://localhost:18090/demo/whoami"
}
~~~

When both instances stay in the healthy list and default Round Robin is active, a sequential batch of requests is usually distributed fairly evenly. Do not judge from one or two requests; order and ratios can shift when multiple callers, retries, and concurrent requests run together.

Baseline records:

| Observation | Result to verify |
|---|---|
| Discovery | Both A and B present |
| Health | Both A and B return HTTP 200 |
| List after health supplier | Contains A and B after check results converge |
| Requests via caller | Responses can come from both |
| HTTP/timeout errors | None under normal lab conditions |

## 8. Scenario B — Marking B Unhealthy

Do not stop process B. Simply flip B's health state:

~~~bash
curl -i -X POST "http://localhost:18082/__test/ready?healthy=false"
curl -i http://localhost:18082/internal/lb-health
curl -i http://localhost:18081/internal/lb-health
~~~

Expected results:

- B returns `503` **for the health endpoint**.
- A still returns `200` for the health endpoint.
- Calling `http://localhost:18082/api/whoami` directly can still return `200` because process B has not stopped.

Continue sending requests through the caller. Once the health supplier actually receives the new result (which may take more than one configured cycle), check whether responses come only from A:

~~~bash
for i in $(seq 1 12); do
  curl -s http://localhost:18090/demo/whoami
  echo
done
~~~

### What Must Happen Internally?

~~~mermaid
sequenceDiagram
    autonumber
    participant T as Tester
    participant B as catalog-b
    participant H as HealthCheck supplier
    participant LB as LoadBalancer
    participant A as catalog-a

    T->>B: POST /__test/ready?healthy=false
    B-->>T: healthy=false
    H->>A: GET /internal/lb-health
    A-->>H: HTTP 200
    H->>B: GET /internal/lb-health
    B-->>H: HTTP 503
    Note over H: Updates healthy list per version mechanism
    LB->>H: Request ServiceInstance list
    H-->>LB: [A] (when filter policy applies)
    LB->>A: Select A for new request
~~~

**Key verification point:** observe B disappearing from the candidate set **after the health supplier updates**, rather than observing only the probe returning `503`. Right after flipping the status, a few new requests may still hit B before the check result is published.

In this step, HTTP `503` from `GET /internal/lb-health` is the **response from the probe endpoint**, not necessarily an HTTP `503` received by the caller when calling `GET /demo/whoami`. As long as requests routed to A succeed, the caller can still return `200` normally.

## 9. Scenario C — Recovering B and Testing Re-Admission

Re-enable B's healthy state:

~~~bash
curl -i -X POST "http://localhost:18082/__test/ready?healthy=true"
curl -i http://localhost:18082/internal/lb-health
~~~

Once B's probe returns `200` again, continue calling through the caller across several health cycles. After the healthy list updates, expect B to become eligible for selection again:

~~~mermaid
sequenceDiagram
    autonumber
    participant T as Tester
    participant B as catalog-b
    participant H as HealthCheck supplier
    participant LB as LoadBalancer

    T->>B: POST /__test/ready?healthy=true
    B-->>T: healthy=true
    H->>B: GET /internal/lb-health
    B-->>H: HTTP 200
    Note over H: B returns to healthy list
    LB->>H: Request updated list
    H-->>LB: [A, B]
    LB->>B: May select B
~~~

To conclude **full recovery**, gather sufficient evidence:

1. B's probe returned `200`.
2. The health supplier published a list containing B.
3. One or more requests via the caller actually reached B.
4. No abnormal errors appeared after resuming traffic.

**A `UP` probe alone does not prove the caller is already using B**; if the caller does not see B return, recheck the health interval, supplier list, path config, service ID, startup, and connectivity.

## 10. Timeline: Failures Are Not Detected Instantaneously

Suppose the health interval is 5 seconds, and at T0 the healthy list contains A and B. B flips health to `503` right after the most recent probe:

| Illustrative milestone | Event | What LoadBalancer may see |
|---|---|---|
| T0 | A and B healthy | [A, B] |
| T1 | B flips probe from 200 to 503 | May still be [A, B] |
| T2 | Next check cycle on B runs | Results updating |
| T3 | Health supplier emits new list | May be [A] |
| T4 | B is turned back on to 200 | May still be [A] |
| T5 | Next check cycle succeeds | May be [A, B] |

These milestones are not fixed SLAs: convergence time is affected by scheduling, probe timeouts, result update mechanics, Spring Cloud version, discovery state, and cache layers. An `interval: 5s` setting **does not guarantee** state changes are detected in exactly 5 seconds.

If faster reaction is needed, shortening the interval raises probe frequency while also increasing health requests from callers. With N callers, M instances, and each caller probing periodically, total health load can become significant.

## 11. Scenario D — Stopping Process B Completely

A second test stops the `catalog-b` process on port 18082 while keeping static discovery configured with both addresses.

This differs from setting `healthy=false`:

- There is no longer an HTTP server on port 18082, so direct calls to B hit **connection refused** or timeouts, with no successful HTTP response.
- The health supplier can detect the probe failure on the next cycle.
- Because `SimpleDiscoveryClient` still lists B's address, **discovery does not automatically remove B** just because the process stopped.
- A new request arriving before health updates can still pick B and suffer a connection error.

Upon restarting `catalog-b` with the same `instance.id` and port, once the HTTP server is ready and health checks pass, B can rejoin the candidate set.

Note that stopping processes in this lab should only be done on your own test processes—never shut down services serving real users.

### Comparing Three Failure Types

| Situation | Health probe | Direct request to B | Investigation path |
|---|---|---|---|
| `healthy=false` | HTTP 503 | `/api/whoami` may still return 200 | Check health supplier and update cycle |
| Process B stopped | Cannot connect | Cannot connect or timeout | Process, network, port, and discovery |
| Business endpoint on B failing | Health may still be 200 | HTTP 5xx or high latency | Endpoint, dependencies, and server logs |

If relying only on a shallow health check, LoadBalancer can keep selecting an instance whose business endpoint is failing. This is a limitation of the health signal, not a bug in the selection algorithm.

## 12. When Both A and B Are Unhealthy

Try marking both instances unhealthy via `/__test/ready`. When doing so, **do not assume automatically** that the selector is guaranteed to return an empty list or HTTP `503`.

Behavior when **no healthy instances remain** depends on the version and configuration of `HealthCheckServiceInstanceListSupplier`, including the policy when health checks find no healthy targets. Some setups return the original instance set when all health checks fail to avoid wiping out all candidates; other setups or custom suppliers may emit an empty list.

Therefore verify in practice:

1. What list does the supplier ultimately publish: empty, the initial list, or something else?
2. Is `Response<ServiceInstance>.hasServer()` `true`?
3. Does the HTTP client actually send a request to an instance or fail before sending?
4. If the caller returns `503`, was that status generated by the caller app itself or returned by the target service?

This experiment prevents misattribution: a probe returning `503` does not mean the caller API is guaranteed to receive `503`, and an instance unhealthy per probes can still answer test endpoints.

## 13. Adding Observability to Prove Traffic Shifting

Looking solely at response bodies is the fastest way for a lab, whereas production requires proper logs and metrics.

### What Should Be Logged?

| Field / metric | Purpose |
|---|---|
| `serviceId=catalog-service` | Identify which logical service is called |
| List and count of instances from discovery | Check the initial data source |
| Instance count after health supplier | Detect excluded and re-admitted instances |
| Instance selected by LoadBalancer | Observe actual routing |
| Probe result per instance | Distinguish 200, HTTP 503, and connection errors |
| Probe timestamps and convergence time | Measure failure/recovery detection latency |
| HTTP status from business endpoint | Avoid confusing health probes with business responses |
| Connect/response timeouts | Identify failures after target selection |
| Retry attempts and tried instances | Control whether retries amplify load |
| `traceId` / `correlationId` | Correlate caller with the request-handling instance |

You can leverage `LoadBalancerLifecycle` to observe call selection/completion stages, combined with Spring Boot Actuator and Micrometer for HTTP metrics. If deep visibility into the supplier chain is needed, add local instrumentation in appropriate supplier classes; avoid creating unintended extra subscriptions that would trigger redundant probes.

Logs should help distinguish:

~~~text
catalog-service -> catalog-b  [request selected]
catalog-b health -> DOWN      [probe reported unhealthy]
catalog-service -> catalog-a  [request selected after update]
catalog-b health -> UP        [probe recovered]
catalog-service -> catalog-b  [receiving traffic again]
~~~

These are **target log lines**, not Spring Cloud's default format. Never log tokens, cookies, sensitive request bodies, or personal data. Limit cardinality if adding instance IDs to metrics.

### Tracking Recovery Latency

Define:

- `t_down`: timestamp when B's probe starts returning 503.
- `t_excluded`: timestamp when B disappears from the final candidate list.
- `t_up`: timestamp when B's probe returns 200 again.
- `t_included`: timestamp when B re-enters the final candidate list.

You can approximate:

~~~text
Failure detection:   t_excluded - t_down
Recovery detection:  t_included - t_up
~~~

Actual values depend on probe interval and update lag. Separate **when the list updates** from **when the first request reaches B**, since LoadBalancer may not pick B immediately even after B re-enters the list.

## 14. Timeouts and Retries When an Instance Fails Mid-Selection

Health checks do not eliminate every race condition. An instance can die right after LoadBalancer selects it, or become overloaded before being marked unhealthy.

Thus RestClient/WebClient/OpenFeign still needs:

- **Connect timeout:** never wait indefinitely to connect to a broken address.
- **Read/response timeout:** bound time waiting for responses.
- **Selective retries:** retry only recoverable errors, with small attempt counts and bounded backoff.
- **Overall deadline:** never let multiple retries exceed the caller's response budget.
- **Idempotency:** never automatically retry side-effecting operations without duplicate-execution protection.
- **Error visibility before and after sending HTTP:** `EmptyResponse` differs from connection errors and differs from HTTP 503 from an instance.

A request may have reached B and been processed by the server while the response was lost. Retrying a write operation on A without an idempotency key can cause duplicate side effects.

Never assume enabling retries automatically picks a different instance. Whether the same or a different instance is chosen depends on client integration, retry policy, and the corresponding supplier.

## 15. Extending the Same Experiment to WebClient and OpenFeign

We used RestClient so the lab has fewer variables. For WebClient or OpenFeign, the principle of selecting an instance by service ID remains the same:

**WebClient:**

~~~java
// webClient built from @LoadBalanced WebClient.Builder
Mono<String> result = webClient.get()
    .uri("http://catalog-service/api/whoami")
    .retrieve()
    .bodyToMono(String.class);
~~~

Errors in WebClient surface via the reactive publisher's `onError` signal; never call `block()` inside an event-loop pipeline to inspect results. Observe via a reactive controller or test subscriber.

**OpenFeign:**

~~~java
@FeignClient(name = "catalog-service")
interface CatalogClient {

    @GetMapping("/api/whoami")
    String whoAmI();
}
~~~

With compatible OpenFeign dependencies and configuration, each call also uses the service ID when integrated with Spring Cloud LoadBalancer. However, exceptions, timeouts, retries, and HTTP status handling belong to each individual client. The health supplier for `catalog-service` still has to update the list before stable traffic-shifting behavior can be expected.

## 16. Verification Checklist and How to Conclude

Record an observation table for each phase:

| Phase | Probe A | Probe B | List after health (observed) | Instance via caller |
|---|---|---|---|---|
| Baseline | 200 | 200 | Expected [A, B] | A and B |
| B unhealthy, before refresh | 200 | 503 | May still be [A, B] | May still hit B |
| B unhealthy, after convergence | 200 | 503 | Expected [A] if policy filters B | Mostly/only A |
| B recovered, before refresh | 200 | 200 | May still be [A] | May still be only A |
| B recovered, after convergence | 200 | 200 | Expected [A, B] | B has a chance to return |
| B process stopped | 200 | Connection error | Depends on update timing | May error before convergence |
| Both unhealthy | 503 | 503 | Depends on fallback policy/version | Observe directly, do not guess |

The lab succeeds when you can demonstrate with evidence:

1. **Losing health** on B is not identical to B being removed from discovery.
2. **Health supplier results** affect the candidate list seen by LoadBalancer.
3. **Recovery** does not occur merely by flipping a flag; passing probes and publishing the updated list are required.
4. **In-flight requests** or requests sent before an update can fail even when the health policy works properly.
5. **HTTP 503** from a health endpoint, HTTP 503 from a business endpoint, and HTTP 503 generated by the caller are three distinct sources.
6. **Timeouts, retries, and observability** help manage the transition window, yet do not replace health checks.

**Conclusion:** Simulating an instance going unhealthy and recovering provides hands-on proof that Spring Cloud LoadBalancer routes based on **the currently supplied `ServiceInstance` set**, not on the system's instantaneous global truth. Discovery, health-check interval, caching, selection algorithms, and RestClient/WebClient/OpenFeign behavior together determine when failures are noticed, when requests shift away, and when instances return to service. Measure those milestones and verify supplier lists at each phase rather than concluding from a single HTTP call.
