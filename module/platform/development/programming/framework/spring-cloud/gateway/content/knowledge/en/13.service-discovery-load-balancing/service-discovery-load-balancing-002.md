# Integrating Spring Cloud LoadBalancer with Gateway Server WebFlux

## 1. The Problem: One Service ID, Multiple Instances

Initially, an API Gateway might forward requests to a fixed backend:

~~~yaml
uri: http://localhost:9091
~~~

However, in a microservices system, the same `catalog-service` can run on `localhost:9091`, `localhost:9092`, or across multiple pods with constantly changing IPs. If you hardcode a single URL, every scaling event, instance replacement, or deployment region change forces you to edit the gateway configuration.

**Spring Cloud LoadBalancer** selects a specific instance of a logical service. **Spring Cloud Gateway Server WebFlux** integrates with it through a special URI:

~~~yaml
uri: lb://catalog-service
~~~

The client still calls a stable public endpoint such as `GET /api/catalog/items/42`. The Gateway matches the route via predicates, runs the filter chain, requests the instance list for `catalog-service`, picks an instance, and sends the actual HTTP request to that instance.

This lesson belongs to the **Service Discovery and Load Balancing** chapter of **SPRING_CLOUD_GATEWAY**. This knowledge connects route predicates, the filter chain, path/header transformations, and service discovery with operational concerns: authentication, rate limiting, circuit breakers, retries, TLS, and request observability. The goal is to understand **why `lb://` works and how to verify it**, rather than just copying a line of configuration.

After this lesson, you will be able to:

1. Distinguish **route**, **service ID**, **ServiceInstance**, **service discovery**, and **load balancing**.
2. Explain the `ReactiveLoadBalancerClientFilter` flow in Gateway Server WebFlux.
3. Add the LoadBalancer dependency and provide instances via `SimpleDiscoveryClient` or a registry.
4. Build a gateway connected to two instances and observe the selected backend via response headers.
5. Distinguish between no route match, no instance found, backend connection failure, and backend-returned errors.
6. Know how to account for caching, health checks, retries, circuit breakers, TLS, and metrics in real deployments.

> **Scope:** This lesson uses **Spring Cloud Gateway Server WebFlux** (reactive, typically paired with Reactor Netty). Gateway Server MVC has a different integration API. Choose Spring Boot, the Spring Cloud BOM, and starters compatible with your running version; route property names differ between WebFlux 4.x and 5.x.

## 2. Five Concepts That Are Easy to Confuse

| Concept | Example | Answers the question |
| --- | --- | --- |
| **Gateway route** | `catalog-api` | Which requests match, which filters run, where is the logical target? |
| **Service ID** | `catalog-service` | Logical name for looking up instances; **not** an HTTP URL that can be called directly |
| **Discovery client** | `SimpleDiscoveryClient`, Eureka, Consul, Kubernetes discovery | Which instances of the service exist? |
| **`ServiceInstance`** | `catalog-service → localhost:9092` | Which host/port does a concrete backend reside at, and what are its secure flag/metadata? |
| **Spring Cloud LoadBalancer** | `RoundRobinLoadBalancer` | Given the available list, which instance should this request choose? |

Example:

~~~text
catalog-service
  ├── instance A: http://localhost:9091
  ├── instance B: http://localhost:9092
  └── instance C: http://localhost:9093
~~~

The Gateway only needs the route `uri: lb://catalog-service`, while the instance list is supplied by an independent source. **Discovery finds the list; LoadBalancer picks one element; Gateway routing makes the HTTP call** once the target address is known.

Route `order` is used to arbitrate between routes with overlapping predicates. It is **not a load-balancing algorithm**: only after the route is selected does LoadBalancer decide the instance.

## 3. Request Flow of lb:// in Gateway WebFlux

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway WebFlux
    participant L as Spring Cloud LoadBalancer
    participant D as Discovery / ServiceInstanceListSupplier
    participant A as catalog A :9091
    participant B as catalog B :9092
    C->>G: GET /api/catalog/items/42
    Note over G: Path predicate matches catalog-api
    Note over G: StripPrefix=1 → /catalog/items/42
    G->>L: Select instance for catalog-service
    L->>D: Fetch instance list
    D-->>L: A:9091 and B:9092
    L-->>G: Choose B
    G->>B: GET /catalog/items/42
    B-->>G: 200 + X-Backend-Instance: B
    G-->>C: HTTP 200 + JSON + headers
~~~

The diagram is **illustrative** and does not imply the first request always picks B. Main processing sequence:

1. `RoutePredicateHandlerMapping` selects a route based on the incoming request.
2. `FilteringWebHandler` organizes `GlobalFilter`s and the route's `GatewayFilter`s in the proper order; `StripPrefix` or `RewritePath` may modify the path.
3. `RouteToRequestUrlFilter` creates the logical target URL and stores it in exchange attribute `ServerWebExchangeUtils.GATEWAY_REQUEST_URL_ATTR`. For `lb://catalog-service`, the URL contains the `lb` scheme and service ID.
4. **`ReactiveLoadBalancerClientFilter`** recognizes the `lb` URI scheme (or corresponding prefixed scheme), asks Spring Cloud `ReactorLoadBalancer` to choose a `ServiceInstance`, and overwrites the logical URL with a URL containing the selected **host, port, and scheme**. The original URL is saved in the exchange's history attribute.
5. Once the URL is `http://...` or `https://...`, `NettyRoutingFilter` uses the HTTP client to send the request to the backend. The response is processed and written back to the client through the response phase of the filter chain.

~~~text
Client URL:              http://localhost:8080/api/catalog/items/42?lang=vi
Route URI:               lb://catalog-service
Path after StripPrefix:  /catalog/items/42
Logical URL:             lb://catalog-service/catalog/items/42?lang=vi
Selected instance:       localhost:9092
Actual HTTP URL:         http://localhost:9092/catalog/items/42?lang=vi
~~~

`lb://` is not an HTTP scheme that a browser can send requests to directly, nor does it turn a service ID into an IP address via DNS on its own. For it to work, the Gateway needs **the LoadBalancer starter, an instance source, and network connectivity to the instances**. Query parameters, body, and HTTP method are not altered by LoadBalancer merely because it picks an instance; other gateway filters can still modify them.

## 4. Required Dependencies

In recent Gateway **Server WebFlux** lines, typical Maven dependencies are:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>
</dependencies>
~~~

Many earlier Gateway WebFlux versions used `spring-cloud-starter-gateway` instead of the new Server WebFlux starter. **Use a Spring Cloud BOM/release train compatible with your project's Spring Boot version** to manage dependency versions. Do not pick standalone Spring Cloud versions arbitrarily, and do not add `spring-boot-starter-web` (Servlet MVC) when running Gateway Server WebFlux.

**Are Eureka or Consul mandatory?** No. Spring Cloud Commons provides `SimpleDiscoveryClient`, which can read a static instance list from properties. This is an ideal way to learn the integration and test `lb://` before using a real registry. In production, a registry or appropriate discovery provider updates instances dynamically as pods/VMs scale or change.

**Is `@EnableDiscoveryClient` required?** In modern Spring Cloud lines, usually not: a discovery client implementation on the classpath can be auto-configured. The annotation does not replace configuring a registry and its dependencies.

## 5. Configuring a Gateway Connected to Two Backends

Lab topology:

| Component | URL | Purpose |
| --- | --- | --- |
| Gateway | `http://localhost:8080` | Route `/api/catalog/**` and pick an instance |
| Instance A | `http://localhost:9091` | Return header `X-Backend-Instance: A` |
| Instance B | `http://localhost:9092` | Return header `X-Backend-Instance: B` |

### 5.1. application.yml for Gateway Server WebFlux 5.x

~~~yaml
server:
  port: 8080

spring:
  application:
    name: catalog-gateway-lab
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:9091
              - uri: http://localhost:9092

    gateway:
      server:
        webflux:
          routes:
            - id: catalog-api
              uri: lb://catalog-service
              predicates:
                - Path=/api/catalog/**
              filters:
                - StripPrefix=1
                - SetRequestHeader=X-Edge-Source, gateway-lab
                - AddResponseHeader=X-Gateway-Route, catalog-api
~~~

`spring.cloud.discovery.client.simple.instances.catalog-service` is the address list for the logical service. `spring.cloud.gateway.server.webflux.routes` declares only **one route** with URI `lb://catalog-service`. `StripPrefix=1` removes the first `api` segment so the backend receives `/catalog/items/42`, not `/api/catalog/items/42`.

The `X-Edge-Source` and `X-Gateway-Route` headers are used to observe bidirectional request/response flow, not as proof of user authentication.

### 5.2. application.yml for Gateway Server WebFlux 4.2.x / 4.3.x

Corresponding WebFlux 4.x lines typically place routes under `spring.cloud.gateway.routes`, while the **Spring Cloud Commons SimpleDiscoveryClient** namespace remains unchanged:

~~~yaml
server:
  port: 8080

spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:9091
              - uri: http://localhost:9092
    gateway:
      routes:
        - id: catalog-api
          uri: lb://catalog-service
          predicates:
            - Path=/api/catalog/**
          filters:
            - StripPrefix=1
            - SetRequestHeader=X-Edge-Source, gateway-lab
            - AddResponseHeader=X-Gateway-Route, catalog-api
~~~

Only use **the single route namespace matching your running version**. If the route is not loaded, requests return 404 before LoadBalancer is ever called. Do not jump to the conclusion that `SimpleDiscoveryClient` is broken before verifying the route itself.

### 5.3. Why doesn't the example enable the discovery locator?

We proactively declared the `catalog-api` route; `SimpleDiscoveryClient` merely supplies the instance list for the service ID. **Instance discovery** is different from **auto-generating routes from a registry**. You do not need to enable `DiscoveryClient Route Definition Locator` for a manual route to use `lb://`.

## 6. Building an Echo Backend with the Same Source Code for A and B

Create a separate Spring Boot project for the backend with the `spring-boot-starter-webflux` dependency. Use a controller that echoes back the instance ID and the received request details.

`src/main/resources/application.yml`:

~~~yaml
server:
  port: ${PORT:9091}

demo:
  instance-id: ${INSTANCE_ID:A}
~~~

`src/main/java/demo/catalog/CatalogApplication.java`:

~~~java
package demo.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

`src/main/java/demo/catalog/CatalogController.java`:

~~~java
package demo.catalog;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseEntity;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class CatalogController {
    private final String instanceId;

    public CatalogController(@Value("${demo.instance-id:A}") String instanceId) {
        this.instanceId = instanceId;
    }

    private Map<String, Object> describe(ServerHttpRequest request, String id) {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("instance", instanceId);
        data.put("method", request.getMethod().name());
        data.put("path", request.getPath().value());
        data.put("query", request.getURI().getRawQuery());
        data.put("itemId", id);
        data.put("edgeSource",
                request.getHeaders().getFirst("X-Edge-Source"));
        return data;
    }

    @GetMapping("/catalog/items/{id}")
    public ResponseEntity<Map<String, Object>> getItem(
            @PathVariable String id, ServerHttpRequest request) {
        return ResponseEntity.ok()
                .header("X-Backend-Instance", instanceId)
                .body(describe(request, id));
    }

    @PostMapping("/catalog/items/{id}")
    public Mono<ResponseEntity<Map<String, Object>>> echoBody(
            @PathVariable String id,
            @RequestBody Mono<Map<String, Object>> payload,
            ServerHttpRequest request) {
        return payload.map(body -> {
            Map<String, Object> data = describe(request, id);
            data.put("body", body);
            return ResponseEntity.ok()
                    .header("X-Backend-Instance", instanceId)
                    .body(data);
        });
    }
}
~~~

This is an **echo** backend that performs no business updates or session authentication. In production projects, do not expose endpoints that reflect sensitive headers or request bodies like this.

### 6.1. Start the three processes

With the Maven Wrapper and both projects created, open three separate terminals.

~~~bash
# Terminal 1: inside the catalog backend project
PORT=9091 INSTANCE_ID=A ./mvnw spring-boot:run

# Terminal 2: inside the same catalog backend project, another terminal
PORT=9092 INSTANCE_ID=B ./mvnw spring-boot:run

# Terminal 3: inside the Gateway project
./mvnw spring-boot:run
~~~

The syntax above is for Bash. In Windows PowerShell, set the environment variables in each backend window respectively:

~~~powershell
# Terminal A
$env:PORT = "9091"
$env:INSTANCE_ID = "A"
.\mvnw.cmd spring-boot:run

# Terminal B, another window
$env:PORT = "9092"
$env:INSTANCE_ID = "B"
.\mvnw.cmd spring-boot:run
~~~

In the Gateway terminal, run `.\mvnw.cmd spring-boot:run`. The two instances **must be two separate processes** because they share the same source code but listen on different ports.

### 6.2. Test the backends directly first

~~~bash
curl -i "http://localhost:9091/catalog/items/42?lang=vi"
curl -i "http://localhost:9092/catalog/items/42?lang=vi"
~~~

Instance A should return status 200, header `X-Backend-Instance: A`, and JSON containing `"instance":"A"`, `"path":"/catalog/items/42"`. Instance B should have `X-Backend-Instance: B`. If direct calls fail, fix the backend before testing gateway integration.

### 6.3. Verify instance selection through the Gateway

~~~bash
curl -i "http://localhost:8080/api/catalog/items/42?lang=vi"
~~~

An **illustrative** response:

~~~http
HTTP/1.1 200 OK
X-Backend-Instance: B
X-Gateway-Route: catalog-api
Content-Type: application/json

{"instance":"B","method":"GET","path":"/catalog/items/42","query":"lang=vi","itemId":"42","edgeSource":"gateway-lab"}
~~~

This is **not a measured result**; either A or B may be selected.

Test multiple times (Bash):

~~~bash
for i in $(seq 1 10); do
  curl -sS -D - -o /dev/null \
    "http://localhost:8080/api/catalog/items/42" |
    grep -i -E '^(HTTP/|X-Backend-Instance:|X-Gateway-Route:)'
done
~~~

Checks to perform:

1. **Route:** response header `X-Gateway-Route: catalog-api` is present.
2. **Path:** backend sees `/catalog/items/42`, proving `StripPrefix=1` ran.
3. **Query:** `lang=vi` remains intact when no filter modifies the query.
4. **Request header:** `edgeSource=gateway-lab` appears in the backend JSON.
5. **Instance:** responses may carry `X-Backend-Instance: A` or `B`. With the default Round Robin, when both instances are available, you can typically observe both across multiple requests.

**Do not guarantee that every two consecutive requests strictly alternate A–B**: the instance list, concurrency, other simultaneous requests, retries, and the number of Gateway replicas all affect the outcome.

### 6.4. Test POST body

~~~bash
curl -i -X POST "http://localhost:8080/api/catalog/items/42" \
  -H "Content-Type: application/json" \
  --data-binary '{"stock":12,"active":true}'
~~~

The chosen backend must receive `POST`, path `/catalog/items/42`, and JSON with numeric `stock` and boolean `active`. LoadBalancer **selects an instance**; it does not alter the body or method on its own. If the body is missing, check filters that read the request body, `Content-Type`, timeouts, and any other proxies.

## 7. Algorithms, Suppliers, Caching, and Health Checks

Spring Cloud LoadBalancer uses the reactive `ReactorLoadBalancer<ServiceInstance>` interface and `ServiceInstanceListSupplier` to obtain candidates. Spring Cloud Commons provides **`RoundRobinLoadBalancer` as the default** and also includes `RandomLoadBalancer`. Advanced algorithms/suppliers require separate configuration; metadata does not automatically turn a route into weighted balancing.

### 7.1. Round Robin per Gateway context

With a stable list `[A, B]`, Round Robin typically selects A → B → A → B… in turn. However:

- Each **Gateway process** has its own LoadBalancer context; no single global counter is shared across all gateway replicas.
- The instance list can change due to discovery/health checks/caching.
- Concurrent requests, retries, or other traffic streams can make the observed sequence non-trivial.
- HTTP keep-alive only reuses connections; it does not necessarily mean all requests stick to the same instance.

To evaluate production distribution, measure **request counts, errors, and latency per instance** over an appropriate window rather than comparing just a few responses.

### 7.2. Caching the instance list

LoadBalancer supports a default cache and a **Caffeine**-backed cache when the dependency is present. Spring Cloud Commons documentation describes properties such as:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 35s
~~~

`35s` is an illustrative value corresponding to the default in current documentation; tune it according to your registry update speed. Caching reduces discovery lookup load, though it can retain an instance that just stopped until the list refreshes.

If the discovery client caches the list itself (e.g., some Eureka configurations), additional caching in LoadBalancer can increase update latency. You may consider:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: false
~~~

**Do not disable caching unconditionally in production**: the choice depends on the discovery type and query cost. When assembling a custom `ServiceInstanceListSupplier` chain, place caching in the right order; caching after a per-request filtering supplier can produce unintended results.

### 7.3. Health checks and stopped instances

`SimpleDiscoveryClient` holds a **static** list. If you shut down instance B on port `9092` while leaving B's URI in configuration, the discovery list will not automatically drop B. LoadBalancer may still select instance B and hit a connection error.

Spring Cloud Commons provides `HealthCheckServiceInstanceListSupplier` to actively probe instances; this feature is especially helpful with static instance sources, though it requires **configuring the supplier and an appropriate health endpoint**. With a registry that already manages health and returns only healthy instances, adding another health-check layer may be unnecessary.

### 7.4. Weighted, zone, and hint-based selection

The Commons documentation also describes `WeightedServiceInstanceListSupplier`, `ZonePreferenceServiceInstanceListSupplier`, and hint-based filtering. They can prioritize higher-capacity instances, same-zone instances, or matching metadata. Simply adding `weight=5` to metadata **does not guarantee** weighted load balancing unless the corresponding supplier is enabled.

## 8. Distinguishing 404, 503, and Connection Errors

| Scenario | Stage | Typical result |
| --- | --- | --- |
| No route matches `Path` or `Method` | Route matching | **404** if no other handler matches |
| Route `lb://catalog-service` matches, but LoadBalancer receives **0 instances** | Instance selection | **503 Service Unavailable** by default |
| Instance is in the list, but TCP cannot connect | HTTP client/routing | Connection error or timeout, typically **5xx** |
| Backend receives wrong path after `StripPrefix` | Backend | Backend may return **404** |
| Backend explicitly returns 500 | Backend | Gateway usually forwards 500 unless another filter changes it |
| Gateway blocks via authentication/rate limiter | Pre-routing security/filter | May return **401**, **403**, **429** |

According to the Gateway WebFlux documentation, when no instance is available, **503** is returned by default. If there is a clear reason, it can be switched to 404 via a version-specific property:

~~~yaml
# Gateway Server WebFlux 5.x (optional)
spring:
  cloud:
    gateway:
      server:
        webflux:
          loadbalancer:
            use404: true
~~~

~~~yaml
# Gateway Server WebFlux 4.2/4.3 (optional)
spring:
  cloud:
    gateway:
      loadbalancer:
        use404: true
~~~

**Do not switch 503 to 404 just to hide registry outages.** No-instance is not the same as a nonexistent endpoint. The property above only applies to the missing-instance case; it does not convert connection errors or backend-returned HTTP 404s into another type.

Experiment: temporarily change `lb://catalog-service` to `lb://missing-service` and reload routes; requests still match `Path=/api/catalog/**` but find no instances, so they typically return 503. Restore the service ID afterward. If you only stop B, the list still contains B and the error may be **connection refused**, not no-instance.

## 9. Registries and DiscoveryClient Route Definition Locator

With a registry like Eureka, Consul, or a Kubernetes platform, instances can be updated dynamically instead of declared statically. Once the corresponding discovery client is on the classpath and registry access is configured, **manually declared** routes still use `lb://catalog-service` as before; the source providing the instance list changes, while the route semantics stay the same.

### 9.1. Should you enable the discovery locator to auto-create routes?

`DiscoveryClient Route Definition Locator` can automatically generate routes from services returned by discovery. According to the documentation, by default these routes use `lb://serviceId`, a predicate like `/serviceId/**`, and a rewrite filter that strips `serviceId` from the path before forwarding to the backend.

In WebFlux **5.x**, the official Configuration Properties table documents:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          discovery:
            locator:
              enabled: true
~~~

For **WebFlux 4.2/4.3**, the configuration is typically:

~~~yaml
spring:
  cloud:
    gateway:
      discovery:
        locator:
          enabled: true
~~~

> Some 5.x discovery locator guides still show the legacy namespace in examples; when they differ, consult the **Configuration Properties reference for your running version** and verify runtime routes using secured operational tooling rather than guessing from a single example.

**Security warning:** a service registered in a registry **is not meant to be public by default** via the Gateway. Only enable auto-generated routes when exposed services, predicates/filters, and authorization are properly controlled. If you customize the `discovery.locator.filters` list, check whether you accidentally replaced the default rewrite filter that strips `serviceId` from the path.

### 9.2. Service ID casing and Docker/Kubernetes networking

`catalog-service` in `lb://catalog-service` must match the service ID returned by discovery according to the provider's rules; some registries normalize uppercase/lowercase characters. In Docker, `localhost:9091` from the Gateway **refers only to the Gateway container itself**, not another catalog container; use proper container URIs/networking. In Kubernetes, distinguish between cluster Service DNS names and a discovery client supplying Pod/`ServiceInstance` entries, avoiding confusion just because both use the word "service".

## 10. TLS, Headers, and Policies After Instance Selection

### 10.1. Client HTTPS does not guarantee backend HTTPS

~~~text
Client ── HTTPS ──> Gateway ── HTTP or HTTPS ──> ServiceInstance
~~~

Per the `ReactiveLoadBalancerClientFilter` documentation, the `isSecure` property of the chosen `ServiceInstance` can determine the outbound scheme. Therefore, a client reaching the Gateway over HTTPS **does not guarantee** the downstream request to the backend also uses HTTPS. Configure URI/secure metadata, truststores/certificates, or Gateway HTTP client SSL bundles to match the real topology; if mTLS is required, implement and test it separately.

### 10.2. Host and X-Forwarded headers

The Gateway may update `Host` and other headers per hop. If the backend needs the client's original host/scheme, use `Forwarded`/`X-Forwarded-*` from a **trusted proxy** that sanitizes headers sent from the Internet. The `X-Edge-Source: gateway-lab` header in the example is strictly for diagnostics, not proof of identity.

### 10.3. Retries, timeouts, circuit breakers, and rate limits

| Mechanism | Decides | Notes |
| --- | --- | --- |
| LoadBalancer | Which instance receives the call | May pick a failing instance if discovery has not updated |
| Timeout | How long to wait for connection/response | Bounds time and resources |
| Retry | Whether to call the backend again | One client request can become **multiple backend calls**, possibly to different instances |
| Circuit breaker | Whether to call a failing service or fall back | Does not protect individual instances separately by default |
| Rate limiter | Whether the caller is allowed through the Gateway | Rate-limit keys must be based on verified identity/API key/IP |

For order-creation or payment `POST` requests, a timeout can occur **after the backend has already persisted data**. Retrying without an idempotency key/deduplication logic will cause duplicate side effects. Do not assume adding `spring-cloud-starter-loadbalancer` automatically enables circuit breakers, business-safe retries, or rate limiters.

## 11. Observability and Debugging

To trace the `lb://` flow, collect the route ID, service ID, selected instance host/port, client method/path, path sent to the backend, status/latency, trace ID, and error source. Combine Micrometer/Actuator/Tracing when appropriate dependencies and configuration are in place; secure management endpoints and never log access tokens, cookies, or sensitive bodies.

A helpful inspection sequence:

1. **Did the request reach the Gateway?** Verify DNS/TLS/ingress/port and access logs.
2. **Did a route match?** Correct namespace and `Path=/api/catalog/**`, with no lower-`order` route swallowing the request?
3. **Did filters rewrite path/headers properly?** The backend should receive `/catalog/items/42`, not `/api/catalog/items/42`.
4. **Are LoadBalancer/supplier working?** Correct dependencies, service ID, and instance list returned by discovery?
5. **Is the instance reachable from the Gateway's network?** Call the instance address directly from the Gateway environment.
6. **Did the backend see the request?** Check the `X-Backend-Instance` response header and backend logs.
7. **Are retries, caches, health checks, or fallbacks involved?** Compare backend call counts, metrics, cache state, and traces.

| Symptom | Possible cause | Next step |
| --- | --- | --- |
| All requests return 404 | Route not loaded or wrong predicate | Verify runtime namespace/config |
| Route matches but returns 503 | No instances for service ID | Check discovery, spelling, registry, health filtering |
| Alternating 200 and connection errors | One instance stopped but still in the list | Call A/B directly, check health/cache |
| Backend returns 404 | Wrong path rewrite | Compare the path received by the backend |
| Only A appears | B is not running, missing from list, or custom policy | Check instance supplier and send multiple requests |
| HTTPS inbound but HTTP outbound | URI/`ServiceInstance.isSecure` and SSL config | Check outbound scheme |
| One request appears multiple times at backend | Retries/timeouts | Check retry policy and idempotency |
| 401/403/429 before backend | Security/rate limiter | Check whether the request passed Gateway filters |

## 12. Pre-Deployment Checklist

- [ ] Gateway **Server WebFlux** uses compatible Boot/Cloud BOM and starters, including LoadBalancer.
- [ ] `lb://...` routes use the exact service ID and have an instance source.
- [ ] Route ordering is clearly distinguished from the instance selection algorithm.
- [ ] Host/port/URI/secure metadata match the real network and TLS policy.
- [ ] Cache/health refresh settings are appropriate, without unnecessary double caching.
- [ ] Discovery locator does not unintentionally expose internal services.
- [ ] Path/query/headers/body/status and actual backend instance have been verified with test requests.
- [ ] Tests cover no-instance, single instance down, backend timeout, and registry outage.
- [ ] Retries/circuit breakers/timeouts are bounded, and write `POST` requests are protected against duplicates.
- [ ] Auth/rate limiting rely on verified identity or trusted keys; backends still enforce authorization.
- [ ] Metrics/tracing separate Gateway/discovery/backend errors without logging sensitive data.

## 13. Official Spring Documentation

1. [Gateway Server WebFlux — Global Filters](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/global-filters.html): `ReactiveLoadBalancerClientFilter`, how `lb://` is resolved, 503 errors, and schemes.
2. [Gateway 4.3 — Global Filters](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/global-filters.html): corresponding behavior and 4.x route namespaces.
3. [Spring Cloud Commons — LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): Round Robin, suppliers, caching, health checks, weighted/zone.
4. [Spring Cloud Commons — Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): `SimpleDiscoveryClient` and instance sources.
5. [Gateway — Configuration Properties](https://docs.spring.io/spring-cloud-gateway/reference/configprops.html): `server.webflux.routes`, `server.webflux.loadbalancer.use404`, and locator prefixes.
6. [Gateway — DiscoveryClient Route Definition Locator](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/the-discoveryclient-route-definition-locator.html): auto-generating routes by service ID.

**Remember:** `lb://catalog-service` is a **logical address**, not a direct HTTP URL. Gateway WebFlux picks a route using predicates, executes the route's filters, `ReactiveLoadBalancerClientFilter` selects a `ServiceInstance` via LoadBalancer and discovery/suppliers, and only then does the routing filter send HTTP(S) to the backend. Understanding this chain helps you control scalability, security, timeouts/retries, TLS, and observability when operating an API Gateway.
