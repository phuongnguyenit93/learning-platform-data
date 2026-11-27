# ReactiveLoadBalancerClientFilter and ServiceInstance Resolution

## 1. From a Service Name to a Real HTTP Address

In a microservices architecture, each service can run multiple instances, scale replicas up and down automatically, and change addresses on redeployment. If **Spring Cloud Gateway** always proxies requests to a fixed host, such as `http://10.0.0.17:8080`, the configuration quickly becomes stale when that instance is replaced.

Instead of knowing every instance's address, a route can point to a **logical service name**:

~~~yaml
uri: lb://inventory-service
~~~

The `lb` (load-balanced) scheme does not mean the Gateway connects to a host named `lb`. The Gateway must select a **ServiceInstance** of `inventory-service`, then rewrite the target URL to a network-reachable HTTP(S) address. In **Spring Cloud Gateway Server WebFlux**, that resolution step is performed by **ReactiveLoadBalancerClientFilter** working together with **Spring Cloud LoadBalancer**.

~~~mermaid
flowchart LR
    Client[Client] --> Gateway[Spring Cloud Gateway]
    Gateway --> Route[Route: lb://inventory-service]
    Route --> LB[ReactiveLoadBalancerClientFilter]
    LB --> Choices[ServiceInstance candidates]
    Choices --> A[Instance A: port 9001]
    Choices --> B[Instance B: port 9002]
    LB --> HTTP[HTTP routing to chosen instance]
    HTTP --> Client
~~~

In this lesson from the **Service Discovery and Load Balancing** chapter, you will learn:

1. The roles of `ReactiveLoadBalancerClientFilter`, `ReactorLoadBalancer`, and `ServiceInstance`.
2. The path from an `lb://service-id` route to an `http(s)://host:port` URL.
3. How **service discovery**, instance list sources, and instance selection algorithms work together.
4. An example with two real backends and load balancing configuration in the Gateway.
5. Behavior when no instances exist, when an instance fails to connect, and when TLS is enabled.
6. How to operate safely alongside route predicates, the filter chain, retries, circuit breakers, rate limiting, and observability.

> **Scope:** This content targets **Spring Cloud Gateway Server WebFlux**, which is built on Reactor. Gateway Server Web MVC has different routing components and filters. YAML namespaces, starter dependencies, and some APIs vary by version; verify against your actual stack.

## 2. Where ReactiveLoadBalancerClientFilter Sits in the Filter Chain

After a request matches a route predicate, the Gateway executes the route's filters together with GlobalFilters sorted by order. The flow can be visualized as follows:

~~~mermaid
flowchart TD
    A[Incoming HTTP request] --> B[RoutePredicateHandlerMapping]
    B --> C[FilteringWebHandler]
    C --> D[Path / header filters]
    D --> E[RouteToRequestUrlFilter]
    E --> F{Target scheme}
    F -->|lb| G[ReactiveLoadBalancerClientFilter]
    G --> H[Choose a ServiceInstance]
    H --> I[Reconstruct http/https target URI]
    I --> J[NettyRoutingFilter]
    F -->|http/https| J
    J --> K[Upstream HTTP server]
    K --> L[NettyWriteResponseFilter / HTTP response]
~~~

The diagram simplifies pre/post phases, security filters, metrics, error handling, and special routing modes such as `forward:` or WebSocket. The roles are:

| Component | Responsibility |
| --- | --- |
| **RoutePredicateHandlerMapping** | Selects a route by `Path`, `Method`, `Header`, `Host`, etc. |
| **FilteringWebHandler** | Executes the chain of GlobalFilters and GatewayFilters for the route |
| **RouteToRequestUrlFilter** | Builds the logical target URL from the route URI and request |
| **ReactiveLoadBalancerClientFilter** | If the URL requests load balancing, picks an instance and updates the URL |
| **NettyRoutingFilter** | Sends the HTTP(S) request to the final host/port using Reactor Netty |
| **NettyWriteResponseFilter** | Participates in writing the upstream response back to the client |

**ReactiveLoadBalancerClientFilter does not send HTTP requests to the backend directly.** It selects the address and leaves network I/O to the subsequent routing filter. This separates instance selection from network connection handling.

### End-to-end request example

Client sends:

~~~http
GET /api/inventory/items/42?warehouse=HCM HTTP/1.1
Host: api.example.test
~~~

Route:

~~~yaml
id: inventory-api
uri: lb://inventory-service
predicates:
  - Path=/api/inventory/**
filters:
  - StripPrefix=2
~~~

`StripPrefix=2` transforms the path into `/items/42`. The logical URL after building the target URL looks like:

~~~text
lb://inventory-service/items/42?warehouse=HCM
~~~

Suppose the load balancer picks an instance at `10.2.0.17:8080` over HTTP; the URL used to send the request looks like:

~~~text
http://10.2.0.17:8080/items/42?warehouse=HCM
~~~

The load balancer focuses on resolving **service ID → instance**; it does not arbitrarily strip query parameters or route `/items/42` to a different business endpoint. The path change is the responsibility of `StripPrefix` in the example.

## 3. What Information Does a ServiceInstance Contain?

`ServiceInstance` is a Spring Cloud abstraction describing an instance registered or provided to serve a logical service.

| API or property | Meaning | Example |
| --- | --- | --- |
| `getServiceId()` | Logical service name | `inventory-service` |
| `getHost()` | Hostname or IP | `10.2.0.17` |
| `getPort()` | Service port | `8080` |
| `isSecure()` | Secure connection flag of the instance | `true` / `false` |
| `getUri()` | URI describing the instance | `http://10.2.0.17:8080` |
| `getMetadata()` | Metadata depending on discovery source | Zone, version, environment info |
| `getInstanceId()` | Unique ID if supported by the source | `inventory-a7c` |

For example, the same `serviceId=inventory-service` may have two candidates:

~~~text
A: host=10.2.0.17, port=8080, secure=false
B: host=10.2.0.18, port=8080, secure=false
~~~

**Having a ServiceInstance does not guarantee the instance is actually healthy.** A registry may still hold a recent heartbeat, a cache may retain a deregistered address, or an application may not be ready because a downstream dependency is down. The load balancer picks from the candidates it receives and does not guarantee the HTTP connection will succeed.

### Service ID vs. DNS hostname

`lb://inventory-service` requests resolution against Spring Cloud LoadBalancer's `ServiceInstance` list. It differs from `http://inventory-service`, where the HTTP client uses a hostname and may rely on environment DNS. In Kubernetes, a DNS Service can load balance, but that does not automatically turn `http://inventory-service` into Spring Cloud LoadBalancer instance resolution.

Do not infer from the service ID alone whether the system uses Eureka, Consul, Kubernetes, or another registry: you must check the actual **instance list source**.

## 4. Steps Performed by ReactiveLoadBalancerClientFilter

Conceptually, this component:

1. Reads the current URL from a shared **exchange attribute** used by routing filters.
2. Detects that the URL has scheme `lb` (or a supported load-balanced scheme prefix).
3. Extracts the service ID from the logical URL, such as `inventory-service`.
4. Invokes the reactive load balancer to pick a `ServiceInstance` for that service ID.
5. If no candidate is available, produces an appropriate error response (typically 503 under default configuration).
6. If a candidate exists, builds a new target URI using the chosen host, port, and corresponding HTTP/HTTPS scheme.
7. Updates the target URL in `ServerWebExchange`, records the original URL per Gateway's convention, and continues the filter chain.
8. Lets the routing filter execute the HTTP request using the newly resolved concrete URL.

~~~mermaid
sequenceDiagram
    participant Client
    participant Gateway as Gateway filter chain
    participant Filter as ReactiveLoadBalancerClientFilter
    participant Load as ReactorLoadBalancer
    participant Supplier as ServiceInstanceListSupplier
    participant Netty as NettyRoutingFilter
    participant Service as Inventory instance

    Client->>Gateway: GET /api/inventory/items/42
    Gateway->>Gateway: Target lb://inventory-service/items/42
    Gateway->>Filter: Continue chain
    Filter->>Load: Choose inventory-service
    Load->>Supplier: Request candidate instances
    Supplier-->>Load: [A, B]
    Load-->>Filter: Selected B
    Filter->>Gateway: Target http://B:8080/items/42
    Gateway->>Netty: Continue routing
    Netty->>Service: HTTP request
    Service-->>Netty: HTTP response
    Netty-->>Client: Response via Gateway
~~~

In Spring Cloud LoadBalancer, the reactive selector can be provided via `ReactorLoadBalancer<ServiceInstance>` (and related factory interfaces/mechanisms); candidate lists are usually supplied by `ServiceInstanceListSupplier`. Auto-configuration mechanisms and concrete classes vary across releases; normally **you do not need to instantiate ReactiveLoadBalancerClientFilter manually**.

## 5. Exchange Attributes and When the URL Changes

Important attributes in `ServerWebExchange`:

~~~java
ServerWebExchangeUtils.GATEWAY_ROUTE_ATTR
ServerWebExchangeUtils.GATEWAY_REQUEST_URL_ATTR
ServerWebExchangeUtils.GATEWAY_ORIGINAL_REQUEST_URL_ATTR
~~~

| Attribute | Typical content | Why it is useful |
| --- | --- | --- |
| `GATEWAY_ROUTE_ATTR` | Selected route definition | Identifies route ID and route URI |
| `GATEWAY_REQUEST_URL_ATTR` | Before selection: `lb://inventory-service/items/42`; after selection: `http://10.2.0.17:8080/items/42` | Shows the target URL at each stage |
| `GATEWAY_ORIGINAL_REQUEST_URL_ATTR` | URLs prior to replacement | Tracks URL transformation history |

`ReactiveLoadBalancerClientFilter` reads `GATEWAY_REQUEST_URL_ATTR`, resolves an instance, and updates that exact attribute. These values are **internal exchange data**, not HTTP headers sent by the client.

### Scheme prefix

Some route URI notations use a **scheme prefix** to combine load balancing with schemes such as HTTP or WebSocket. In that case, the Gateway may use the `GATEWAY_SCHEME_PREFIX_ATTR` attribute to determine the appropriate handling step. Do not combine schemes arbitrarily or deduce the final scheme from the client URL; check the syntax supported by your **actual Gateway version**.

### Why custom filters must understand ordering

If a custom GlobalFilter reads `GATEWAY_REQUEST_URL_ATTR` very early in the **pre** phase, the value may still be `lb://...` or not yet prepared. After the load balancer succeeds, the value is typically a concrete HTTP(S) URI. Place your observation point at the right stage—such as on the downstream publisher's completion signal—or use built-in load balancer and HTTP client instrumentation.

## 6. Instance List Sources: Service Discovery and Suppliers

**Service discovery** answers: "Which instances are known to the system?" **Load balancing** answers: "From that list, which instance should be picked for this request?" **HTTP routing** answers: "How is the request sent to the chosen URL?"

~~~mermaid
flowchart TD
    D[Registry or static configuration] --> S[ServiceInstanceListSupplier]
    S --> F[Optional caching / filtering]
    F --> L[ReactorLoadBalancer]
    L --> I[Selected ServiceInstance]
    I --> G[ReactiveLoadBalancerClientFilter]
~~~

| Source | How it is used | Limits to keep in mind |
| --- | --- | --- |
| Static list | Declare instances via config or custom supplier | Does not automatically discover new replicas unless config changes |
| Eureka | Services register with the registry | Depends on heartbeats, clients, and registry state |
| Consul | Suitable service catalog/discovery | Requires dependency, network, and health integration |
| Kubernetes | Discovery via Spring Cloud Kubernetes integration or equivalent | Depends on namespaces, RBAC, endpoint readiness, and config |
| Custom supplier | Fetches from an internal management source | You own caching, thread safety, and error handling |

The list can also pass through candidate filtering layers by zone/metadata, health checks, and caching if configured. **These layers do not activate automatically just because metadata is present.** Exact names and behaviors depend on Spring Cloud LoadBalancer and its version.

### Do not confuse with DiscoveryClient Route Definition Locator

These are two separate things:

- **Explicitly declared route** with `uri: lb://inventory-service`: an explicit API using a service ID; `ReactiveLoadBalancerClientFilter` selects an instance once the request matches the route.
- **DiscoveryClient Route Definition Locator**: if enabled and configured, it can **auto-generate route definitions** from services known to discovery.

Auto-generating routes for all services can unintentionally expose internal APIs. On a public Gateway, control route predicates, authentication, authorization, rate limits, and network policies instead of automatically exposing every service in the registry.

## 7. Example: Configuring the Gateway with Two Static Instances

To practice without a dedicated registry, you can use **SimpleDiscoveryClient** to provide two instances of the same logical service. Here is an example configuration for a **Spring Cloud Gateway Server WebFlux** version using the `server.webflux` namespace:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:9001
              - uri: http://localhost:9002

    gateway:
      server:
        webflux:
          routes:
            - id: inventory-api
              uri: lb://inventory-service
              predicates:
                - Path=/api/inventory/**
              filters:
                - StripPrefix=2
~~~

For the example to work, you need:

1. A **Spring Cloud Gateway Server WebFlux** starter compatible with your Spring Boot/Spring Cloud BOM.
2. **Spring Cloud LoadBalancer** on the classpath, usually via `spring-cloud-starter-loadbalancer`.
3. Instance provision from **SimpleDiscoveryClient** via the configured Spring Cloud Discovery stack; the load balancer must see two instances.
4. Two real backends running on ports 9001 and 9002, both supporting `GET /items/{id}`.

For many earlier versions, route YAML uses `spring.cloud.gateway.routes` instead of `spring.cloud.gateway.server.webflux.routes`. Pick the **exact namespace and starter** for your project's release rather than copying both configurations side by side and assuming both work.

`SimpleDiscoveryClient` is well suited for learning instance selection; in production, instances usually come from a registry/orchestrator to track scale-out and scale-in.

### Test backend with an identifier marker

Both backends can run the same controller, differing only in the configured `instance.id` value:

~~~java
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class InventoryController {
    private final String instanceId;

    InventoryController(@Value("${instance.id:unknown}") String instanceId) {
        this.instanceId = instanceId;
    }

    @GetMapping("/items/{id}")
    Mono<Map<String, String>> getItem(@PathVariable String id) {
        return Mono.just(Map.of(
                "itemId", id,
                "handledBy", instanceId
        ));
    }
}
~~~

Start two instances of the backend application, setting `server.port` to 9001 and 9002 respectively, and `instance.id` to A and B. If configuration loads properly, responses look like:

~~~json
{"itemId":"42","handledBy":"A"}
~~~

Or:

~~~json
{"itemId":"42","handledBy":"B"}
~~~

These are **illustrative responses**, not measured output from a live run in this guide. `handledBy` is simply a field created by the demo backend; it is not a default Gateway header.

## 8. Testing Routes and Instance Selection Behavior

Send multiple requests through the Gateway:

~~~bash
curl -i 'http://localhost:8080/api/inventory/items/42?warehouse=HCM'
curl -i 'http://localhost:8080/api/inventory/items/42?warehouse=HCM'
curl -i 'http://localhost:8080/api/inventory/items/42?warehouse=HCM'
~~~

A request goes through:

1. `Path=/api/inventory/**` matches route `inventory-api`.
2. `StripPrefix=2` produces path `/items/42`.
3. Logical URL corresponds to `lb://inventory-service/items/42?warehouse=HCM`.
4. The load balancer fetches the instance list and selects either A or B.
5. HTTP routing calls `http://localhost:9001/items/42?warehouse=HCM` or `http://localhost:9002/items/42?warehouse=HCM`.
6. The response contains `handledBy`, showing which test backend handled it.

In common configurations, **round-robin** is the usual default algorithm. Still, do not strictly expect the first three requests to always be A-B-A: selection depends on load balancer state, list ordering, version, concurrency, number of Gateway replicas, and other concurrent requests.

| Scenario | Result to verify |
| --- | --- |
| Both instances running | Across multiple requests, both A and B can be seen selected |
| Only B in the supplied list | Requests are routed to B |
| A stopped but still in static list | Some requests may fail with connection errors to A |
| Empty list | Resolution cannot pick an instance, typically returns 503 |
| URI uses wrong service ID | Matching instance group cannot be found |
| Path does not match route | Does not hit Inventory route; status depends on other routes/handlers |
| Backend returns 404 | Route may have matched, but the backend resource does not exist |
| Query contains `warehouse=HCM` | Backend should receive the query if filters/proxies do not alter it |

### Distinguishing a matched route from a successful backend response

A request returning HTTP 404 does not necessarily mean the Gateway failed to match a route: the Gateway may have routed successfully while the backend returned 404 for `/items/42`. Likewise, HTTP 503 can come from failing to select an instance, from an unavailable service, or from a fallback filter. Inspect route ID, target URL, exceptions, and upstream responses to pinpoint the cause.

## 9. When No ServiceInstance Is Available

When the target URL requires `lb` but the load balancer finds no instances for the service ID, **ReactiveLoadBalancerClientFilter** typically produces a **503 Service Unavailable** response. Some versions support returning **404 Not Found** instead of 503 via the `use404` option.

Example property name used in some versions:

~~~properties
spring.cloud.gateway.loadbalancer.use404=true
~~~

In newer lines, the namespace may differ; confirm in the configuration documentation for your exact Gateway Server WebFlux version. **Switching to 404 does not fix discovery errors.**

| Case | Failing stage | Interpretation |
| --- | --- | --- |
| No candidates for service ID | When load balancer selects an instance | Gateway can typically return 503 |
| Candidate exists, wrong port | After instance selection, in HTTP client | May cause connection error or timeout |
| Instance exists, wrong TLS certificate | After selection, during TLS handshake | Trust/hostname/TLS policy error |
| Instance exists and connects, backend returns 503 | Backend application | 503 response originated from the service |

Do not use infinite retries or turn every 503 into 200 to mask resolution failures. If a critical service has no instances, the system needs independent monitoring alerts and a business-appropriate fallback policy.

## 10. Round-Robin, Metadata, Zones, and Health Status

Spring Cloud LoadBalancer can use different selection and candidate-filtering mechanisms depending on dependencies, version, and configuration:

| Capability | Meaning | What not to assume |
| --- | --- | --- |
| **Round-robin** | Iterates sequentially through the candidate list | No guarantee of exact equal split in every time window |
| **Random selection** | Picks a candidate at random | No guarantee A and B get equal calls in a small sample |
| **Zone preference** | Prefers a region/zone when configured appropriately | Having zone metadata does not automatically force same-zone selection |
| **Health-check supplier** | Can filter candidates using health signals | Does not replace orchestrator readiness probes and network policies |
| **Caching** | Reduces the cost of repeated discovery queries | May briefly retain an instance that already left the system |
| **Hint/request-aware policy** | Adjusts selection based on context or trusted hints | Not enabled automatically just because a client sends a header |

A common issue: instance A remains listed right after shutting down. With a static list, the Gateway **does not automatically remove A** just because a request to A failed. With a dynamic registry, updates also take time to propagate via heartbeats, caches, or change events.

### Health, readiness, and reachability are three different concepts

1. **Liveness:** is the application process still alive?
2. **Readiness:** is the instance ready to accept live traffic?
3. **Reachability:** from the Gateway process, is the host/port or TLS endpoint reachable?

A backend may still be running yet not ready because its database is down. It may also report ready on its health endpoint yet be unreachable from the Gateway due to network policy. Any team using health filtering must know which signal **actually controls the instance list**.

### Sticky sessions do not happen automatically

If a backend stores user session state only in instance A's RAM, a subsequent request routed to B will not see that data. Round-robin does not guarantee session affinity. Prefer stateless services or shared session stores; if sticky routing is required, configure and test a dedicated mechanism while accounting for disappearing instances and uneven traffic distribution.

## 11. Client-Side HTTPS and Backend-Side HTTPS Are Two Separate Connections

A common misconception: **clients using HTTPS to the Gateway does not mean the Gateway uses HTTPS to the backend**.

~~~mermaid
flowchart LR
    Browser[Client] -->|TLS hop 1| Gateway[Spring Cloud Gateway]
    Gateway -->|HTTP or TLS hop 2| Service[Chosen ServiceInstance]
~~~

When reconstructing the upstream URL, `ReactiveLoadBalancerClientFilter` can use `ServiceInstance.isSecure()` to decide between HTTP and HTTPS schemes. For instance, if the instance is described as non-secure, the backend connection may use HTTP even though the client-to-Gateway request used HTTPS. Conversely, a secure instance can use HTTPS on the second hop. When a route uses a specific **scheme prefix**, scheme precedence may differ; verify the behavior in your running release.

**isSecure alone does not guarantee proper TLS.** Security on the Gateway → backend hop also depends on:

- The backend actually listening for HTTPS on the advertised port.
- Certificates signed by a trusted CA or present in a valid truststore.
- The hostname/IP used to connect matching the certificate's names.
- HTTP client settings, TLS protocols, and ciphers meeting policy.
- If **mTLS** is required, proper configuration of the Gateway's client certificate and backend verification.
- Any intermediate proxies/sidecars introducing extra TLS termination or custom network paths.

Never resolve trust/hostname errors by disabling certificate verification. Fix DNS, certificates, truststores, or how `ServiceInstance` advertises its address.

### Forwarded and Host headers

In architectures with TLS termination at an ingress, the public client URL may be `https://api.example.test` even when the Gateway receives HTTP on an internal network. Headers like `Forwarded`, `X-Forwarded-Proto`, or `X-Forwarded-Host` are trustworthy only when set by a **trusted proxy** and clients cannot spoof them to influence routing or redirects.

The load balancer selects an **upstream address**, not client identity authentication. Backends must obtain identity through Spring Security/proper propagation and enforce resource authorization, never trusting arbitrary client-supplied `X-User-Id` headers.

## 12. Interaction with Path Rewriting and Header Filters

A route can combine multiple filters:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: product-api
              uri: lb://product-service
              predicates:
                - Path=/api/products/**
                - Method=GET
              filters:
                - StripPrefix=1
                - AddRequestHeader=X-Gateway-Source, edge
~~~

A `GET /api/products/42?lang=vi` request is handled by route `product-api`. `StripPrefix=1` creates `/products/42`, and the load balancer picks an instance of `product-service`. The `X-Gateway-Source: edge` header can be added to the outbound request to the backend.

**What ServiceInstance selection does NOT do automatically:**

- Does not rewrite `/api/products/42` to `/products/42` without a path filter.
- Does not interpret what query `lang=vi` means.
- Does not authenticate users or authorize access.
- Does not guarantee `X-Gateway-Source` or `X-Role` is trustworthy merely because it exists.
- Does not control request body size or long-lived connection counts.
- Does not guarantee a POST is processed only once when retries are enabled.

When combining multiple filters, distinguish **route order** (which route is matched) from **filter order** (which filter runs earlier/later). If a custom filter needs to inspect the chosen URL, reading too early may see only `lb://...` instead of the final host. If a custom filter inadvertently modifies `GATEWAY_REQUEST_URL_ATTR`, it can bypass load balancing or send the request to a different address.

## 13. Example GlobalFilter to Observe the Resolved URL

In a test environment, you can use a filter to inspect the route ID and target URI after downstream processing completes. This snippet **only observes** and does not choose instances:

~~~java
import java.net.URI;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.cloud.gateway.route.Route;
import org.springframework.core.Ordered;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

import static org.springframework.cloud.gateway.support.ServerWebExchangeUtils
        .GATEWAY_REQUEST_URL_ATTR;
import static org.springframework.cloud.gateway.support.ServerWebExchangeUtils
        .GATEWAY_ROUTE_ATTR;

@Component
public class ResolvedTargetObservationFilter implements GlobalFilter, Ordered {

    private static final Logger log =
            LoggerFactory.getLogger(ResolvedTargetObservationFilter.class);

    @Override
    public int getOrder() {
        return -1000;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        return chain.filter(exchange)
                .doFinally(signal -> {
                    Route route = exchange.getAttribute(GATEWAY_ROUTE_ATTR);
                    URI target = exchange.getAttribute(GATEWAY_REQUEST_URL_ATTR);

                    String routeId = route == null ? "none" : route.getId();
                    String scheme = target == null ? "none" : target.getScheme();
                    String host = target == null ? "none" : target.getHost();

                    log.debug("route={}, upstreamScheme={}, upstreamHost={}, signal={}",
                            routeId, scheme, host, signal);
                });
    }
}
~~~

**Explanation:**

1. `chain.filter(exchange)` gives downstream filters the opportunity to select an instance and send the request.
2. `doFinally` receives a signal when the publisher completes, errors, or cancels; at this point the attribute usually reflects the resolved URL if selection succeeded.
3. If load balancing failed early, `target` may still be the logical `lb://...` URI with no real upstream host.
4. `doFinally` does not mean the request succeeded at the backend; you must check status and exceptions.
5. Do not log raw queries, `Authorization`, cookies, or bodies. Hosts and instance IDs also need bounded cardinality if used in metrics.

In production, prefer **Micrometer/Actuator/tracing** supported by Spring Cloud Gateway and the HTTP client. The example above illustrates observing filter-chain outcomes without calling `subscribe()` or `block()`.

## 14. Retries, Circuit Breakers, and Selecting Failing Instances

**Selecting an instance** is only one step. The system still has to handle unresponsive instances, timeouts, disconnects, HTTP errors, circuit breakers, and non-idempotent operations.

| Mechanism | Role | Risk if misused |
| --- | --- | --- |
| Discovery | Reports known instances | Registry/cache may hold stale data |
| Load balancing | Picks an instance by policy | Does not guarantee the chosen instance is healthy |
| Timeout | Bounds I/O wait time | Too-short deadlines cut off valid requests |
| Retry | Retries when conditions allow | Amplifies load or repeats side effects |
| Circuit breaker | Prevents repeatedly calling failing dependencies | Fallbacks can mask outages |
| Rate limiting | Limits incoming HTTP requests to Gateway | Does not balance load across instances |

### Does retry automatically switch to another instance?

**Do not assume yes by default.** A retry may pick the same instance again or a different one depending on the retry filter, load balancing mechanism, whether selection is re-invoked, error-instance avoidance policies, and version. To guarantee avoiding a failing instance, configure and verify it explicitly on your current stack.

Especially with `POST /orders` or payments, the backend may have processed the request while the response was lost. Retrying to another instance can create duplicate orders or charges. Require idempotency keys and safe retry policies for operations with side effects.

### A circuit breaker does not automatically remove instances from discovery

A circuit breaker protects against degrading dependencies, but it does not necessarily alter the `ServiceInstance` list. To avoid selecting unready instances, use readiness probes, registry health, TTL/caching, or appropriate suppliers/filters. Combine circuit breakers and health filtering deliberately.

For partially sent SSE or NDJSON responses, an upstream error occurring **after the HTTP response is committed** cannot change the status to 503. Retrying the entire stream can duplicate events; design resume/replay at the application level.

## 15. Securing Instance Sources and Service IDs

Load balancing is an important routing boundary: requests are sent to the host/port appearing in the instance list, so not only Gateway code but also the **service discovery source** must be protected.

1. **Never take an arbitrary service ID from an untrusted path/header/query** and concatenate it into `lb://...` for dynamic routing. If business requirements call for selecting among several services, enforce an allowlist and authorization.
2. **Protect write access to the registry.** A forged `ServiceInstance` entry can cause the Gateway to send requests to unintended internal addresses, creating routing-layer SSRF risks.
3. **Restrict networks the Gateway can reach.** Use network policies/firewalls, environment segmentation, and TLS/mTLS per policy.
4. **Isolate staging/production and tenants.** Identical service IDs across environments must never allow requests to cross boundaries.
5. **Backend authentication/authorization** remains mandatory; Gateway route predicates and the load balancer do not prove a user is authorized to read or mutate a resource.
6. **Never log sensitive information** when debugging resolved URLs: tokens, cookies, private queries, client identities, and auth headers must be protected.

A trusted registry and proper TLS infrastructure keep the Gateway from forwarding data to unauthorized targets. Never rely solely on a client-sent `X-Service-Id` header to decide routing to internal systems.

## 16. Hop-by-Hop Observability and Troubleshooting

When a request fails, separate **route selection → instance selection → HTTP connection → backend response**.

| Symptom | Possible cause | How to verify |
| --- | --- | --- |
| `lb://...` does not work | Missing Spring Cloud LoadBalancer or incompatible dependencies/starters | Check classpath, auto-configuration, and loaded routes |
| Gateway returns 503 very early | Instance source has no candidates, wrong service ID | Check instance list, registered name, and choose-step logs |
| Instance selected, connection refused | Backend stopped, wrong port, firewall | Call `host/port` directly from Gateway's network |
| Only one backend is ever called | Source has only one instance, stale cache, or custom selection policy | Inspect list and send multiple requests |
| Stopped instance still gets selected | Static list or registry cache has not refreshed | Check health, TTL, refresh, and supplier |
| Backend receives wrong path | Incorrect `StripPrefix` or `RewritePath` | Log paths at the test backend |
| Client uses HTTPS but upstream uses HTTP | Two independent TLS hops and different `isSecure()`/scheme | Inspect resolved URL and backend TLS config |
| HTTP 404 after routing | Resource missing on backend or another route matched | Distinguish Gateway 404 from backend 404 |
| Retries cause duplicate POSTs | Missing idempotency contract | Check business IDs, retries, and side effects |
| CircuitBreaker returns 200 fallback | Failures hidden in HTTP status metrics | Track fallback counts and upstream errors separately |
| Custom filter sees `lb://` instead of host | Filter reads attribute before load balancing | Move observation point or use proper instrumentation |

### Recommended diagnostic workflow

1. **Route:** did the request match the expected predicate and route ID?
2. **URI:** does the route actually have `lb://inventory-service` rather than `http://...`?
3. **Classpath:** are load balancer and discovery dependencies auto-configured properly?
4. **Candidates:** how many instances does the load balancer see, and at what host/port?
5. **Choose:** was a `ServiceInstance` selected?
6. **Target URL:** did `GATEWAY_REQUEST_URL_ATTR` become a valid `http(s)://host:port`?
7. **HTTP/TLS:** did the request reach the backend; are there connection, TLS, or timeout errors?
8. **Business contract:** did the backend receive the expected path, query, and headers, and return the expected status/body?
9. **Resilience:** did retries, circuit breakers, or other filters alter the outcome?

Never fix a no-instance outage by raising retry counts indefinitely or disabling TLS. Diagnose the failing layer first before adjusting configuration.

## 17. Metrics and Operational Readiness

In production, monitor at least these signal groups:

| Signal | Question answered |
| --- | --- |
| Request rate by route and service | Which routes are under heavy load? |
| Gateway and upstream latency | Is latency introduced in the proxy or the backend? |
| Instance count | Is the system reflecting scale-in/scale-out? |
| No-instance / choose errors | How many requests failed to select a candidate? |
| Connection/TLS/timeouts | How many errors occurred after instance selection? |
| Retries and CircuitBreaker | Is there a retry storm or continuous fallback? |
| HTTP 4xx/5xx | Are errors originating at client, Gateway, or backend? |
| Active connections, event-loop latency | Is the Gateway hitting reactive I/O resource contention? |

Use **Micrometer**, **Spring Boot Actuator**, logging, and tracing appropriate for your Spring Cloud Gateway version. Management endpoints must enforce authentication and network restrictions; never expose full route tables or infrastructure details to the internet.

**Metric cardinality matters.** Route ID is a useful tag and usually has a bounded set of values; raw URL queries, request IDs, or user IDs can create unbounded series. Instance IDs and IPs also churn heavily during autoscaling; consider grouping strategies rather than putting them directly into every time series.

With multiple Gateway replicas, each replica can maintain its own round-robin state. Observing a single Gateway is not enough to evaluate cluster-wide traffic distribution; aggregate by route/service and watch for skew caused by differing discovery views.

## 18. Comprehensive Lab

**Context:** A retail system has an Inventory service running two instances. The Gateway exposes `GET /api/inventory/items/{id}` using `lb://inventory-service`.

### Part A — Configuration

1. Run two Inventory backends on ports 9001 and 9002, both exposing `GET /items/{id}`, with different `handledBy` values.
2. Configure `SimpleDiscoveryClient` or a dynamic registry with two `ServiceInstance` entries.
3. Ensure a compatible Spring Cloud LoadBalancer dependency is present.
4. Create a route with `uri: lb://inventory-service`, predicate `Path=/api/inventory/**`, and filter `StripPrefix=2`.

### Part B — Prove the URL Is Resolved

1. Send multiple requests through the Gateway; observe `handledBy` and do not assume a strict A-B-A-B sequence.
2. Compare `lb://inventory-service` in configuration with the `http://localhost:9001` or `http://localhost:9002` URL used by the HTTP client.
3. Test query `?warehouse=HCM` and verify the backend receives the right path and query.
4. Add the observation filter from Section 13 in a test environment; inspect the target URL and route ID without logging tokens.

### Part C — Simulate Failures

1. Stop backend A **without editing** the static list. Record cases where A is still picked and requests fail to connect.
2. Keep only B in the candidate list; verify requests reach B.
3. Change the route's service ID to a name with no instances; observe no-instance behavior.
4. Test a bounded GET timeout/retry and observe how many times backends are called and which instance is chosen on retry.
5. Measure instance-selection errors separately from connection errors; confirm fallbacks do not hide failure rates.

### Part D — Security

1. Verify whether Gateway → backend connections use HTTP or HTTPS per policy.
2. Verify that a client-supplied `X-User-Id` header is not trusted as an authenticated identity.
3. If using a dynamic registry, test scaling up/down and measure the latency to detect new instances or drop old ones.
4. Verify Spring Security and data authorization are enforced at the proper layers.

**Pass criteria:** The route matches correctly, the `ServiceInstance` list resolves, an HTTP(S) address is chosen, and paths/queries are not unexpectedly altered. You must be able to distinguish **no-instance**, **connection failure**, and **backend error** using evidence from logs/traces, backends, and HTTP clients; never use retries or status rewrites to hide outages.

## 19. Takeaways

- **ReactiveLoadBalancerClientFilter** is the step that resolves load-balanced URIs like `lb://service-id` to a concrete upstream URL in **Spring Cloud Gateway Server WebFlux**. The filter picks an instance; **it does not send the HTTP request directly**.
- **Service discovery supplies the list**, **Spring Cloud LoadBalancer selects a ServiceInstance**, and the **routing filter** sends HTTP(S) to the chosen instance.
- `GATEWAY_REQUEST_URL_ATTR` holds the URL at the routing stage, and `GATEWAY_ORIGINAL_REQUEST_URL_ATTR` helps trace prior URLs. They are exchange attributes, not HTTP headers.
- For an `lb://` route to work, you need the **load-balancer dependency**, a **valid instance source**, and a compatible configuration namespace. Manually declared routes differ from auto-generating routes from discovery.
- **No available instance** typically leads to **503**; **selecting an instance that fails to connect** is a failure at a different stage. Observe each layer before configuring retries or fallbacks.
- **Client-side TLS and backend-side TLS are independent**; `ServiceInstance.isSecure()` does not replace truststore configuration, certificate validation, or mTLS.
- Load balancing does not replace **health/readiness, security, authorization, rate limiting, circuit breakers, safe retries, metrics, or tracing**. Verify the entire request flow to operate your microservices entry point reliably and securely.
