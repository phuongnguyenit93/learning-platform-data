# Comparing Fixed URLs with Service-Name Calls

When two microservices communicate over HTTP, the source code can use either a **fixed physical URL** such as `http://127.0.0.1:8081` or a **logical service name** such as `http://catalog-service`. The two URLs look similar, but they **do not carry the same routing semantics**.

In **Spring Cloud LoadBalancer**, `catalog-service` can act as a **service ID**: the client fetches the list of `ServiceInstance` entries, picks one replica, replaces the logical host/port with the physical address, and sends the HTTP request. Conversely, with a fixed URL, the HTTP client goes straight to a known endpoint; there is no instance-selection step through Spring Cloud LoadBalancer.

This lab belongs to the **Hands-On Project** chapter of the Spring Cloud LoadBalancer module. You will launch **two replicas of `catalog-service` and one `order-service`**, test both calling styles inside the same application, observe request distribution, and examine what happens when an instance stops.

After this lesson, learners will be able to:

1. Distinguish between a physical URL, a service ID, and a DNS hostname.
2. Configure both a direct `RestClient` and a `@LoadBalanced RestClient.Builder` in the same caller.
3. Supply two replicas via `SimpleDiscoveryClient` without installing Eureka/Consul.
4. Observe the exact instance handling each request from the response.
5. Explain behavior around scale-up, dead instances, static discovery, caching, and retries.
6. Apply the same principles to `WebClient` and OpenFeign.

> The example runs on localhost and is intended strictly for learning environments. In Docker/Kubernetes, `127.0.0.1` points to the process/container's own network namespace, not automatically to another service.

## 1. Two HTTP Calling Strategies

### 1.1. Calling a Fixed URL

~~~java
RestClient direct = RestClient.create("http://127.0.0.1:8081");

CatalogItem item = direct.get()
        .uri("/api/products/{id}", 42)
        .retrieve()
        .body(CatalogItem.class);
~~~

Path:

~~~text
order-service
    |
    | GET http://127.0.0.1:8081/api/products/42
    v
catalog-service replica A (8081)
~~~

The client knows the specific host/port. If a new replica starts on port 8082, that URL **does not automatically switch to 8082**. A direct URL can still point to an external proxy/load balancer, but **the caller's Spring Cloud LoadBalancer** does not participate when the client is not configured as load-balanced.

### 1.2. Calling by Service ID

~~~java
// Builder already configured with @LoadBalanced and Spring Cloud.
RestClient logical = loadBalancedBuilder
        .baseUrl("http://catalog-service")
        .build();

CatalogItem item = logical.get()
        .uri("/api/products/{id}", 42)
        .retrieve()
        .body(CatalogItem.class);
~~~

When the integration is active, the hostname `catalog-service` is treated as a **service ID**, and the actual HTTP destination address is determined by LoadBalancer from the instance list.

~~~mermaid
flowchart LR
    A["order-service<br/>GET http://catalog-service"]
    B["Spring Cloud LoadBalancer"]
    C["ServiceInstanceListSupplier"]
    D["catalog-a<br/>127.0.0.1:8081"]
    E["catalog-b<br/>127.0.0.1:8082"]
    A --> B
    B <--> C
    B --> D
    B --> E
~~~

### Comparison Table

| Criterion | Fixed URL | Service ID + Spring Cloud LoadBalancer |
|---|---|---|
| Base URL | `http://127.0.0.1:8081` | `http://catalog-service` |
| Host value | Physical host or known proxy | Service ID resolved via a supplier |
| Instance selection at caller | No | Yes, if the client has an LB interceptor/filter |
| Adding an instance | Does not update the URL automatically | Can be used once discovery updates |
| One instance dies | Requests to it fail | May still be selected if discovery/cache is stale |
| Round-robin/weight/zone | Not at the caller | Configurable |
| DNS | May be used if the URL contains a hostname | No DNS needed for logical service IDs in the lab |
| Retry, pool, timeout | Handled by HTTP/resilience layer | Still handled by HTTP/resilience layer after selection |

**Important:** merely writing `http://catalog-service` does not automatically enable LoadBalancer. A plain HTTP client may attempt to resolve `catalog-service` as a DNS hostname and fail if no corresponding record exists.

## 2. Lab Architecture

We will build two Spring Boot applications and run them as **three processes**:

- `catalog-service` A running on port `8081`, returning `instanceId=catalog-a`.
- `catalog-service` B running on port `8082`, returning `instanceId=catalog-b`.
- `order-service` running on port `8080`, exposing two endpoints: one calling directly and one calling by service ID.

~~~mermaid
flowchart TB
    U["Learner / curl"]
    O["order-service :8080"]
    D["RestClient direct<br/>127.0.0.1:8081"]
    L["RestClient load-balanced<br/>catalog-service"]
    LB["LoadBalancer"]
    S["SimpleDiscoveryClient<br/>A + B"]
    A["catalog-a :8081"]
    B["catalog-b :8082"]
    U --> O
    O -->|"/compare/direct/42"| D --> A
    O -->|"/compare/service/42"| L --> LB
    LB <--> S
    LB --> A
    LB --> B
~~~

Suggested source layout:

~~~text
url-vs-service-id-demo/
├── settings.gradle.kts
├── catalog-service/
│   ├── build.gradle.kts
│   └── src/main/java/com/example/catalog/
│       ├── CatalogApplication.java
│       └── CatalogController.java
└── order-service/
    ├── build.gradle.kts
    ├── src/main/java/com/example/orders/
    │   ├── OrderApplication.java
    │   ├── CatalogItem.java
    │   ├── CatalogClientConfiguration.java
    │   └── ComparisonController.java
    └── src/main/resources/application.yml
~~~

The tree above shows **files the learner creates for the lab**, not files pre-generated by this article. You can use Maven instead of Gradle.

## 3. Preparing Environment and Dependencies

Prerequisites:

- JDK compatible with your project's Spring Boot version; Spring Boot 3.x typically uses Java 17+.
- Spring Framework **6.1+** if using `RestClient`.
- **Compatible** Spring Boot and Spring Cloud BOM/release train versions; do not mix starter versions arbitrarily.
- Ports 8080, 8081, and 8082 available; three terminals and `curl` or PowerShell.

`settings.gradle.kts`:

~~~kotlin
rootProject.name = "url-vs-service-id-demo"
include("catalog-service", "order-service")
~~~

Dependencies in `catalog-service/build.gradle.kts`:

~~~kotlin
plugins {
    java
    id("org.springframework.boot")
    id("io.spring.dependency-management")
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
}
~~~

Dependencies in `order-service/build.gradle.kts`:

~~~kotlin
plugins {
    java
    id("org.springframework.boot")
    id("io.spring.dependency-management")
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

The Gradle snippets only show the lesson-relevant parts: a complete build configuration still needs plugin versions, Maven Central, and the Spring Cloud BOM `spring-cloud-dependencies` in the parent/root. On Spring Boot 4, pick the WebMVC starter and dependency management matching the Boot 4 generation. **Do not copy a Boot 3 snippet verbatim into a Boot 4 project without checking starter names.**

`spring-cloud-starter-loadbalancer` must be present in the caller for Spring Cloud to perform instance selection. `spring-boot-starter-web` does not replace that dependency.

## 4. Writing the catalog-service Backend

### Application Entry Point

Create `CatalogApplication.java`:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

### Controller Returning Instance ID

Create `CatalogController.java`:

~~~java
package com.example.catalog;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
public class CatalogController {

    private final String instanceId;
    private final int port;

    public CatalogController(
            @Value("${demo.instance-id}") String instanceId,
            @Value("${server.port}") int port) {
        this.instanceId = instanceId;
        this.port = port;
    }

    @GetMapping("/{id}")
    public CatalogItem get(@PathVariable long id) {
        return new CatalogItem(
                id, "Product-" + id, instanceId, port);
    }

    public record CatalogItem(
            long id, String name, String instanceId, int port) {
    }
}
~~~

When running on port 8081 with `demo.instance-id=catalog-a`, the response is:

~~~json
{
  "id": 42,
  "name": "Product-42",
  "instanceId": "catalog-a",
  "port": 8081
}
~~~

The replica on port 8082 will return `catalog-b` and `8082`. The purpose of these two fields is to **help the test identify which backend actually handled the request**. You do not necessarily want to expose topology details in production APIs.

## 5. Writing order-service and Configuring Discovery

### 5.1. Application Class

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

### 5.2. DTO for Receiving JSON from catalog

Create `CatalogItem.java`:

~~~java
package com.example.orders;

public record CatalogItem(
        long id, String name, String instanceId, int port) {
}
~~~

The lab uses the same JSON contract in both applications. In real systems, sharing the Java DTO class is not required; what is required is that client and server agree on the HTTP contract.

### 5.3. application.yml

~~~yaml
server:
  port: 8080

demo:
  catalog:
    direct-url: http://127.0.0.1:8081

spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://127.0.0.1:8081
              - uri: http://127.0.0.1:8082
    loadbalancer:
      cache:
        enabled: false
      retry:
        enabled: false
~~~

| Property | Effect |
|---|---|
| `demo.catalog.direct-url` | Custom application property for the direct client |
| `spring.cloud.discovery.client.simple.instances.catalog-service` | Static list of two `ServiceInstance` entries |
| `uri` | Physical endpoint of each instance |
| `spring.cloud.loadbalancer.cache.enabled=false` | Disables LB cache to simplify the lab |
| `spring.cloud.loadbalancer.retry.enabled=false` | Disables LB retry to distinguish a single call from multiple attempts |

`SimpleDiscoveryClient` has no heartbeat and does not automatically remove an instance when port 8081 closes. If A stops, YAML still contains A. Setting cache disabled **does not mean discovery updates itself**.

A production project should reconsider caching appropriate to its discovery client; do not use the lab configuration as a default deployment recommendation.

## 6. Configuring Two RestClients in the Same Caller

Create `CatalogClientConfiguration.java`:

~~~java
package com.example.orders;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class CatalogClientConfiguration {

    // A: Regular RestClient calling a physical URL.
    @Bean("catalogDirectClient")
    RestClient catalogDirectClient(
            @Value("${demo.catalog.direct-url}") String url) {
        return RestClient.builder()
                .baseUrl(url)
                .build();
    }

    // B: Builder customized by Spring Cloud LoadBalancer.
    @Bean("catalogLoadBalancedBuilder")
    @LoadBalanced
    RestClient.Builder catalogLoadBalancedBuilder() {
        return RestClient.builder();
    }

    @Bean("catalogServiceClient")
    RestClient catalogServiceClient(
            @Qualifier("catalogLoadBalancedBuilder")
            RestClient.Builder builder) {
        return builder
                .baseUrl("http://catalog-service")
                .build();
    }
}
~~~

**The critical difference lies in the builder**, not in the variable names `directClient` or `serviceClient`:

- `catalogDirectClient` is built from a regular `RestClient.builder()` with the 8081 URL.
- `catalogServiceClient` uses a `@LoadBalanced` `RestClient.Builder` and the service ID hostname.
- `@Qualifier` by bean name avoids injecting the wrong client when multiple beans share the same type.

In projects using multiple Spring Boot customizers for observability, encoding, or SSL, consider using the Boot-managed `RestClientBuilderConfigurer`/builder for your version instead of a raw builder as in this minimal lab.

### What Not to Do

~~~java
// Not "direct" if the builder is @LoadBalanced:
RestClient wrongDirect = catalogLoadBalancedBuilder
        .baseUrl("http://127.0.0.1:8081")
        .build();
~~~

Once the LoadBalancer interceptor is attached, the hostname `127.0.0.1` may be interpreted as a **service ID** to resolve, resulting in a no-instance error. To call a physical URL, use a **non-load-balanced** client.

Conversely:

~~~java
// Just a regular RestClient; does not select a ServiceInstance.
RestClient ordinary = RestClient.create("http://catalog-service");
~~~

`ordinary` may send the hostname through DNS and work if the environment has a DNS record; that outcome **does not prove** Spring Cloud LoadBalancer is running.

## 7. Controller Placing Both Calling Styles Side by Side

Create `ComparisonController.java`:

~~~java
package com.example.orders;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
@RequestMapping("/compare")
public class ComparisonController {

    private final RestClient directClient;
    private final RestClient serviceClient;

    public ComparisonController(
            @Qualifier("catalogDirectClient")
            RestClient directClient,
            @Qualifier("catalogServiceClient")
            RestClient serviceClient) {
        this.directClient = directClient;
        this.serviceClient = serviceClient;
    }

    @GetMapping("/direct/{id}")
    public CatalogItem direct(@PathVariable long id) {
        return directClient.get()
                .uri("/api/products/{id}", id)
                .retrieve()
                .body(CatalogItem.class);
    }

    @GetMapping("/service/{id}")
    public CatalogItem byServiceName(@PathVariable long id) {
        return serviceClient.get()
                .uri("/api/products/{id}", id)
                .retrieve()
                .body(CatalogItem.class);
    }
}
~~~

Both endpoints are identical in HTTP method, backend path, and JSON DTO. The **only intentional difference** is the injected client:

~~~text
GET /compare/direct/42
  -> direct RestClient
  -> http://127.0.0.1:8081/api/products/42

GET /compare/service/42
  -> @LoadBalanced RestClient
  -> LoadBalancer selects ServiceInstance
  -> http://127.0.0.1:8081 or :8082/api/products/42
~~~

If the backend returns invalid JSON, both clients can encounter decoder errors. That error belongs to the HTTP contract and does not prove whether LoadBalancer did or did not select an instance.

## 8. Starting the Three Processes

With a Gradle project that has valid plugin/BOM configuration, open **three separate terminals**.

**Terminal 1 — catalog A**

~~~powershell
./gradlew :catalog-service:bootRun --args="--server.port=8081 --demo.instance-id=catalog-a"
~~~

**Terminal 2 — catalog B**

~~~powershell
./gradlew :catalog-service:bootRun --args="--server.port=8082 --demo.instance-id=catalog-b"
~~~

**Terminal 3 — order-service**

~~~powershell
./gradlew :order-service:bootRun --args="--server.port=8080"
~~~

If using prebuilt JARs, run the same `catalog-service` JAR twice with the corresponding `--server.port` and `--demo.instance-id` arguments. Both backends must remain running simultaneously during the test.

On Windows PowerShell, use `curl.exe` to avoid confusion with the `curl` alias.

Check both backends directly:

~~~powershell
curl.exe -s http://127.0.0.1:8081/api/products/42
curl.exe -s http://127.0.0.1:8082/api/products/42
~~~

The first must return `catalog-a`, and the second must return `catalog-b`. If not, check the ports, `demo.instance-id`, whether both applications started successfully, and whether the endpoints share the same path.

## 9. Experiment A — Fixed URL

Call the caller:

~~~powershell
curl.exe -s http://127.0.0.1:8080/compare/direct/42
~~~

Expected result:

~~~json
{
  "id": 42,
  "name": "Product-42",
  "instanceId": "catalog-a",
  "port": 8081
}
~~~

Repeat 10 times:

~~~powershell
1..10 | ForEach-Object {
    (Invoke-RestMethod "http://127.0.0.1:8080/compare/direct/42").instanceId
}
~~~

With the 8081 URL configuration, all successful responses must come from `catalog-a`.

**What the test proves:** requests from the direct client go to the designated physical endpoint. It does not prove that a fixed hostname in another environment cannot point to a gateway or DNS load balancer.

## 10. Experiment B — Service Name and Multiple Instances

Call the load-balanced client:

~~~powershell
curl.exe -s http://127.0.0.1:8080/compare/service/42
~~~

Repeat multiple times:

~~~powershell
1..12 | ForEach-Object {
    (Invoke-RestMethod "http://127.0.0.1:8080/compare/service/42").instanceId
}
~~~

In a lab without special policies, with two available instances and the common round-robin algorithm, the results typically include **both `catalog-a` and `catalog-b`**.

Illustrative example:

~~~text
catalog-a
catalog-b
catalog-a
catalog-b
...
~~~

**Do not assert that the first request always picks A**, or that 12 requests always split strictly 6/6 if concurrency or state differences exist. Initial choice and order can depend on LoadBalancer state. The meaningful check here is that **both backends are observed**.

If all requests return A, check:

- Is `catalogServiceClient` actually built from `@LoadBalanced RestClient.Builder`?
- Has `SimpleDiscoveryClient` bound both URIs?
- Is there a zone/hint, weight, health, or custom supplier providing only A?
- Was a fixed URL accidentally placed on the service client?
- Does backend B return the right instance ID and is it still available?

## 11. Breaking Down a Request's Path

~~~mermaid
sequenceDiagram
    participant U as Learner
    participant O as order-service
    participant LB as BlockingLoadBalancerClient
    participant S as ServiceInstanceListSupplier
    participant HTTP as HTTP transport
    participant B as catalog-b:8082
    U->>O: GET /compare/service/42
    O->>LB: Choose target for catalog-service
    LB->>S: Get ServiceInstances
    S-->>LB: catalog-a, catalog-b
    LB-->>O: catalog-b
    O->>HTTP: Request to physical URI :8082
    HTTP->>B: GET /api/products/42
    B-->>HTTP: JSON instanceId=catalog-b
    HTTP-->>O: CatalogItem
    O-->>U: CatalogItem
~~~

Three boundaries to distinguish:

1. **Discovery:** returns the list of `ServiceInstance` entries for the service ID.
2. **Selection:** uses round-robin/random/weight/zone or another policy to pick one instance.
3. **Transport:** performs DNS (if needed), pooling, TCP/TLS, sends the request, and reads the response.

An instance that is successfully selected can still refuse connections, time out, or return HTTP 500. Do not describe every HTTP failure after selection as "LoadBalancer picked wrong."

## 12. Experiment C — Stopping Replica A

Stop the `catalog-service` process on port 8081; keep catalog B and `order-service` running.

### Direct URL

~~~powershell
curl.exe -i http://127.0.0.1:8080/compare/direct/42
~~~

The direct client continues pointing at 8081, so requests typically fail to connect. Since the controller has no custom exception handler, downstream failures may be surfaced by the caller application as HTTP 500. **Do not claim a guaranteed specific HTTP status code from the caller**, as it depends on the application's exception handling.

### Service ID

~~~powershell
1..8 | ForEach-Object {
    try {
        (Invoke-RestMethod "http://127.0.0.1:8080/compare/service/42").instanceId
    } catch {
        "FAILED"
    }
}
~~~

**Key point:** `SimpleDiscoveryClient`'s YAML still contains both A and B. With LB retry disabled and an unchanged list, requests picking A can fail while requests picking B succeed.

| Calling Path | A Stopped, B Alive |
|---|---|
| Direct to 8081 | Calls to A fail |
| Service ID, static list still has A/B | Can both fail and succeed depending on the chosen instance |
| Service ID, list source only has B | Selects B and succeeds if B is healthy |

This is not evidence that LoadBalancer is "useless." It illustrates the limit of **stale discovery data**: instance selection is only as good as the list provided by the supplier.

## 13. Experiment D — Changing the Discovery List

Keeping A stopped, edit `order-service/application.yml` in the **lab project** so the list contains only B:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://127.0.0.1:8082
    loadbalancer:
      cache:
        enabled: false
      retry:
        enabled: false
~~~

Leave `demo.catalog.direct-url: http://127.0.0.1:8081` unchanged. **Restart the caller** to ensure the static configuration is applied; do not assume YAML hot-reloads automatically.

Repeat both paths:

~~~powershell
curl.exe -i http://127.0.0.1:8080/compare/direct/42

1..8 | ForEach-Object {
    (Invoke-RestMethod "http://127.0.0.1:8080/compare/service/42").instanceId
}
~~~

Expected results:

- The direct path keeps failing because it still points to A.
- The service ID path only picks B and succeeds.

**Benefit of service ID:** the caller does not have to hard-code "B" into every call site; endpoint selection depends on the instance source. With a dynamic registry (Eureka/Consul), membership can update via heartbeats/registration/deregistration, though there is still latency from caching and health checks; there is no guarantee of instant failover.

## 14. Experiment E — Service ID Is Different from DNS

Both lines below contain `http://catalog-service`, yet they are **not the same**:

~~~java
// With @LoadBalanced builder:
RestClient springLbClient = catalogLoadBalancedBuilder
        .baseUrl("http://catalog-service")
        .build();

// Without LoadBalancer interceptor:
RestClient dnsClient = RestClient.create("http://catalog-service");
~~~

| Client | How the Hostname Is Resolved |
|---|---|
| `springLbClient` | Spring Cloud LoadBalancer treats `catalog-service` as a service ID |
| `dnsClient` | HTTP transport/DNS handles it as a regular hostname |
| `dnsClient` on a laptop without a DNS record | May encounter `UnknownHostException` |
| `dnsClient` in Kubernetes with Service DNS | May work via ClusterIP/mesh **without using Spring Cloud LB** |

Do not use "calling by service name worked" as proof that the client-side LoadBalancer is active. You must inspect **the bean, interceptor/filter, candidate list, and selected instance**.

With Kubernetes/service mesh, both architectures are valid:

1. Call the service DNS/ClusterIP and let the infrastructure distribute traffic.
2. Use Spring Cloud LoadBalancer and discovery to pick a `ServiceInstance` right in the caller.

Avoid accidentally stacking multiple load-balancing layers unnecessarily without understanding the boundary of each layer.

## 15. Same Principle with WebClient and OpenFeign

### WebClient

~~~java
@Configuration(proxyBeanMethods = false)
class CatalogReactiveClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }

    @Bean
    WebClient directWebClient() {
        return WebClient.builder()
                .baseUrl("http://127.0.0.1:8081")
                .build();
    }

    @Bean
    WebClient serviceWebClient(
            @LoadBalanced WebClient.Builder builder) {
        return builder
                .baseUrl("http://catalog-service")
                .build();
    }
}
~~~

This snippet omits imports and assumes Spring WebFlux and the compatible LoadBalancer dependency have been added. `WebClient` uses a LoadBalancer exchange filter on the service path, while the direct client has no filter attached.

### OpenFeign

~~~java
@FeignClient(name = "catalog-service")
interface CatalogFeignByName {
    @GetMapping("/api/products/{id}")
    CatalogItem findById(@PathVariable("id") long id);
}

@FeignClient(
        contextId = "catalogDirectFeign",
        name = "catalog-service",
        url = "http://127.0.0.1:8081")
interface CatalogFeignDirect {
    @GetMapping("/api/products/{id}")
    CatalogItem findById(@PathVariable("id") long id);
}
~~~

To use Feign, you need the OpenFeign starter, `@EnableFeignClients`, and the LoadBalancer starter if you want instance selection by name. **Feign with a fixed `url` goes directly**; it bypasses LoadBalancer selection by service ID for that client. Also check URL configuration in properties, since those can likewise make Feign bypass LoadBalancer.

Do not conflate Feign's transport with Spring Cloud LoadBalancer: HTTP pooling, read timeouts, and retries remain separate concerns.

## 16. Fixed URLs Are Not Always Wrong

A direct URL can be appropriate when the target is:

- An external API with a stable hostname and provider-managed load balancing.
- A gateway/reverse proxy acting as a single entry point.
- An admin/health/debug endpoint that must target one exact replica.
- A standalone service or a test case needing a pinned host to reproduce an issue.

A service ID is especially useful when:

- The caller must choose among multiple replicas that change via discovery.
- Policies like round-robin, weighted, zone/hint, or filtering are needed.
- Endpoint management should be decoupled from business code.
- Observability per service ID and knowing which instance was chosen are required.

Ask: **"Does the fixed URL point to a leaf instance, or to a virtual IP/gateway with its own load balancing?"** A fixed hostname URL can still sit in front of a multi-server cluster.

## 17. Retries, Health Checks, and Timeouts Do Not Appear Automatically When Changing URLs

A common false expectation is that simply switching from `http://127.0.0.1:8081` to `http://catalog-service` gives you automatic failover.

| Component | Direct URL | Service ID via LoadBalancer |
|---|---|---|
| Connect/read timeout | Determined by HTTP transport | Still determined by HTTP transport after instance selection |
| Connection pool | Keyed by HTTP client address/route | Keyed by chosen physical endpoint |
| Retry | HTTP/resilience policy | Can add LB retry if enabled/configured |
| Health check | Separate or infrastructure mechanism | Can use health supplier when configured |
| Circuit breaker | Requires separate configuration | Still requires separate configuration |
| Discovery cache | No service ID lookup needed | May have its own cache and stale entries |
| Graceful shutdown | Coordinated by backend/infra | Still requires backend/discovery/cache coordination |

In the lab, `spring.cloud.loadbalancer.retry.enabled=false` is explicitly set so one logical request corresponds to one attempt without automatic LB retries. If you enable retries later, check:

- Whether retries hit the same instance or a different instance.
- Which errors/statuses are retried.
- Backoff, overall timeout, and maximum attempts.
- Whether the request body is replayable, especially for uploads/streaming.
- Idempotency of POST/PUT operations.

**Retries do not make `SimpleDiscoveryClient` update its list automatically.** If the static source still contains A, a policy or an updated discovery source is still needed to remove A completely.

## 18. Automated Testing Instead of Manual Observation

An integration test should spin up **two fake HTTP servers on dynamic ports**, then pass their actual URIs to `SimpleDiscoveryClient` via `@DynamicPropertySource`. The test runs both `RestClient` beans inside a real Spring context.

Example assertions to include:

~~~java
// Illustrative helper in an integration test,
// not a complete standalone @SpringBootTest.
static void assertRouting(
        RestClient directClient,
        RestClient serviceClient) {

    for (int i = 0; i < 5; i++) {
        CatalogItem direct = directClient.get()
                .uri("/api/products/{id}", 42)
                .retrieve()
                .body(CatalogItem.class);

        assertEquals("catalog-a", direct.instanceId());
    }

    Set<String> observed = new HashSet<>();

    for (int i = 0; i < 12; i++) {
        CatalogItem item = serviceClient.get()
                .uri("/api/products/{id}", 42)
                .retrieve()
                .body(CatalogItem.class);
        observed.add(item.instanceId());
    }

    assertEquals(Set.of("catalog-a", "catalog-b"), observed);
}
~~~

This snippet assumes `assertEquals` and `Set`/`HashSet` from JUnit/Java are imported. In a complete test, start the fake backends before creating the Spring context, inject both `RestClient` beans by exact name, and shut down the servers after the test. Keep retry/cache aligned with test conditions and avoid reusing contexts with stopped URIs.

**Unit tests** on `ServiceInstanceListSupplier` can prove the candidate set is right, but they do not prove `@LoadBalanced` is attached to the HTTP client. Conversely, a few passing integration requests do not prove the system handles load or fails over reliably at scale.

### Test Matrix

| Scenario | Direct URL | Service ID + LB |
|---|---|---|
| Both backends running | Only A | Can reach both A and B |
| Change direct URL to B | Only B | Unchanged if discovery is unchanged |
| Discovery has only B | Still follows direct URL | Selects only B |
| Discovery empty | Independent of list | No instance to select |
| A stopped, discovery still has A/B | Calls to A fail | Some attempts may fail |
| HTTP 200 invalid JSON | Decoder may fail | Decoder may fail too |
| Connect/read timeout | Belongs to HTTP transport | Belongs to HTTP transport after selection |
| Missing `@LoadBalanced` | Does not affect direct | Logical host may be resolved via DNS |
| Add retry | Depends on transport/resilience | Depends on LB/transport/resilience policy |

## 19. Recording Observations and Diagnosing Failures

Fill in the following table **with real measurements** from your test machine:

| Run | Path | Instance List | Receiving Backend | Status | Latency | Notes |
|---|---|---|---|---|---|---|
| A1 | Direct | A/B | A | Measure yourself | Measure yourself | Fixed endpoint |
| B1 | Service ID | A/B | A or B | Measure yourself | Measure yourself | Selection active |
| C1 | Direct, A stopped | A/B | No reply | Measure yourself | Measure yourself | Direct still points to A |
| C2 | Service, A stopped | A/B | B or failed on A | Measure yourself | Measure yourself | Stale static source |
| D1 | Service, only B | B | B | Measure yourself | Measure yourself | Discovery updated |
| D2 | Direct, still A | B | No reply | Measure yourself | Measure yourself | Does not use discovery |

Do not fill in estimated timings or error rates as actual observed results. In applications with observability, record:

- `serviceId`, route template, and operation type.
- `instanceId` or an allowed infrastructure identifier.
- HTTP status, elapsed time, and error category.
- `NO_INSTANCE`, `CONNECT_FAILURE`, `READ_TIMEOUT`, `DECODE_FAILURE`.
- Retry attempt, if a policy is actually enabled.
- `traceId` to correlate caller/backend logs.

Never log raw `Authorization`, `Cookie`, raw URLs with query strings, sensitive bodies, or unsanitized exception messages.

## 20. Common Errors

| Symptom | Likely Cause | How to Diagnose |
|---|---|---|
| Both direct and service return only A | Service builder lacks LB; discovery only sees A; policy picks only A | Check beans, candidate list, instance ID |
| `UnknownHostException: catalog-service` | Called with a regular RestClient without LB | Check `@LoadBalanced` and dependencies |
| `No instances available` | Wrong service ID or discovery/supplier is empty | Check properties and metadata |
| LB client with URL `127.0.0.1` fails with no-server | IP is treated as a service ID | Use a regular builder for direct calls |
| A is stopped yet still selected | Static discovery or stale cache | Remove A from list, refresh/discovery health |
| Both backends return the same `instanceId` | Wrong startup arguments | Check each terminal |
| Port conflict on startup | 8080/8081/8082 already in use | Change ports and update URIs |
| Docker cannot call host localhost | Different network namespace | Use container network/hostname |
| Service ID URL works even without LB | DNS/mesh handles the hostname | Check interceptors/filters and network path |
| YAML edited but routing unchanged | Context not reloaded or stale cache | Restart caller, verify config |
| Instance selected but request times out | HTTP transport/backend issue | Check selected URI and per-phase latency |
| OpenFeign uses only one IP | `url` set in annotation/properties | Remove URL to select by service name |

**Diagnose in order:** `ServiceInstance` list present → instance selected → connected to physical URI → HTTP response received → body decoded and validated. Do not try to fix network errors by increasing cache TTL, or fix JSON contract bugs by switching the round-robin algorithm.

## 21. Extension Exercises

**Exercise 1 — URL via environment variable.** Change the direct property to:

~~~yaml
demo:
  catalog:
    direct-url: ${CATALOG_DIRECT_URL:http://127.0.0.1:8081}
~~~

Run the caller with `CATALOG_DIRECT_URL` pointing to 8082. Predict that direct switches to B, while service ID still uses the instance list.

**Exercise 2 — Add replica C.** Start catalog on 8083, add it to `SimpleDiscoveryClient`, restart the caller, and observe that service ID can reach all three, whereas direct does not automatically call C.

**Exercise 3 — Weighted selection.** Add `weight` metadata and apply the version-appropriate weighted supplier. Measure distribution over many calls. Do not assert exact ratios over a small sample of requests.

**Exercise 4 — Health checks and graceful shutdown.** Try a health supplier or dynamic registry; measure how long it takes before an instance is removed from the candidate list. Distinguish health/cache state from idle sockets in the HTTP pool.

**Exercise 5 — Load test through the caller.** Use k6 or an equivalent tool to send load to `/compare/service/42`, **without calling the backend directly** if you want to measure Spring Cloud LoadBalancer's choices. Track requests per replica, p95/p99, errors, and pool behavior.

## 22. Acceptance Checklist

1. Are two `catalog-service` processes genuinely running with distinct `instanceId` values?
2. Does `order-service` have two independent RestClients, one direct and one load-balanced?
3. Are `spring-cloud-starter-loadbalancer` and the proper `@LoadBalanced RestClient.Builder` bean present?
4. Does `SimpleDiscoveryClient` define the exact service ID `catalog-service` and two URIs?
5. Do repeated calls to `/compare/direct/42` return only A?
6. Can `/compare/service/42` return both A and B when both are healthy?
7. When A stops, can you explain why static discovery still contains A?
8. When keeping only B in the list and restarting the caller, does service ID call only B even though direct still points to A?
9. Have you distinguished between a service ID resolved by Spring Cloud and a DNS/service mesh hostname?
10. Have you verified that timeouts/retries/health checks are not enabled automatically just by changing the URL?
11. Did you record real test measurements rather than fabricated numbers?
12. Can you turn these verification steps into an integration test using dynamic ports without depending on round-robin order?

**Conclusion:** A physical URL and a service ID are not two notations for the same kind of address. With a **direct RestClient**, the caller specifies the exact endpoint to call. With a **RestClient built from `@LoadBalanced RestClient.Builder`**, the caller supplies a **service ID**, and Spring Cloud LoadBalancer selects a `ServiceInstance` before the HTTP transport sends the request. Understanding and verifying this boundary is essential for properly handling scaling, registry caching, dead replicas, retries, timeouts, and routing policies in microservices systems.

**Official references:**

- [Spring Cloud Commons – RestClient as a LoadBalancer Client](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud Commons – Spring Cloud LoadBalancer, discovery and caching](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
- [Spring Framework – REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html)
- [Spring Cloud OpenFeign – Declarative HTTP Client](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html)
