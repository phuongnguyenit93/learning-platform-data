# Distinguishing Shared Data from Per-Request Dependent Data

In Spring Cloud LoadBalancer, an **instance supplier chain** (`ServiceInstanceListSupplier` chain) typically handles two categories of information:

1. **Data shared across requests to the same service:** the list of replicas returned by discovery, network addresses, health status, or metadata on each `ServiceInstance`.
2. **Data specific to an individual request:** hints in HTTP headers, the API version desired by the request, sticky-session cookies, or routing criteria derived from request context.

These two types of data have different lifecycles and caching semantics. If you filter by request and place the result into a shared cache, subsequent requests can see a candidate list constrained by an earlier request. Conversely, if you only serve a fixed list and ignore request context, policies like canary routing or sticky sessions will misbehave.

This lesson explains how to identify which data can be shared, which data must be computed per request, and how to order suppliers so `ServiceInstance` selection stays reliable.

## 1. One Service ID, Many Possible Candidate Lists

Suppose `catalog-service` has three replicas:

| Instance ID | URI | `hint` Metadata |
|---|---|---|
| `catalog-stable-1` | `http://10.0.1.11:8080` | `stable` |
| `catalog-stable-2` | `http://10.0.1.12:8080` | `stable` |
| `catalog-canary-1` | `http://10.0.1.21:8080` | `canary` |

The discovery source returns the shared list:

~~~text
catalog-service:
  [catalog-stable-1, catalog-stable-2, catalog-canary-1]
~~~

However, a request carrying header `X-SC-LB-Hint: stable` may be filtered down to the two stable instances, while a request with `X-SC-LB-Hint: canary` may see only `catalog-canary-1`.

~~~mermaid
flowchart TD
    D["Discovery: catalog-service"]
    C["Shared list: stable-1, stable-2, canary-1"]
    A["Request A: hint=stable"]
    B["Request B: hint=canary"]
    F1["Candidates A: stable-1, stable-2"]
    F2["Candidates B: canary-1"]
    L1["LoadBalancer picks a replica for A"]
    L2["LoadBalancer picks a replica for B"]
    D --> C
    C --> A
    C --> B
    A --> F1
    B --> F2
    F1 --> L1
    F2 --> L2
~~~

The **baseline list** is identical for both requests at the same instant; the **post-filter list** differs because each request carries its own context. This is the core boundary when designing a supplier chain.

## 2. What Is Shared Data?

"Shared data" does not necessarily mean immutable or global across the entire application. In this lesson, it refers to data reusable across **multiple requests to the same service ID** over a period of time.

Typical examples:

| Data | Why can it be shared? | When does it change? |
|---|---|---|
| List of `ServiceInstance` for `catalog-service` | Many requests need the same registered instance set | Scaling up/down, registration/deregistration, discovery sync |
| Instance host, port, URI | Describes a concrete endpoint | Instance replacement or registration update |
| `zone`, `hint`, `weight` metadata on instances | Attributes published alongside the instance | Deployment or discovery metadata changes |
| Health check results | Can filter out unhealthy instances for many requests | Whenever a probe cycle produces new results |
| List cached by service ID | Avoids repeated discovery lookups per request | Cache expiration or refresh |

For example, `catalog-stable-1` has metadata `hint=stable`. That value is an **attribute of the instance**: it describes which group the instance belongs to. It is not a hint value that every request is forced to use.

Shared data can still become stale. Health checks, the registry, and caches may observe instance state at different points in time. When an instance stops before data refreshes, the shared list may still include an unreachable endpoint.

### Defining the Sharing Scope

In Spring Cloud LoadBalancer, each service ID typically has its own LoadBalancer configuration context. Therefore, `catalog-service` instance lists must not be mixed with `payment-service` lists. Even within the same service ID, results can differ across environments, namespaces, or client discovery configurations.

Never interpret "shared" as "stored in one static variable across all services and all requests."

## 3. What Is Per-Request Dependent Data?

Per-request dependent data is determined when a specific call is made and can differ between two consecutive calls to the same service ID.

| Per-request signal | Example | Possible usage |
|---|---|---|
| Hint in header | `X-SC-LB-Hint: canary` | Prefer instances with `hint=canary` metadata |
| Requested API version | `Accept-Version: 2` | Filter instances serving that version when configured |
| Sticky-session cookie | Cookie naming prior instance | Attempt to re-select the matching instance when sticky policy is enabled |
| Caller identity | Policy by calling app or priority tier | Pick an instance group based on trusted caller context |
| Processing region requirement | E.g., request must stay within a region | Filter by matching metadata if policy supports it |

These signals **do not take effect automatically** just by appearing in an HTTP request. They must be transferred by the LoadBalancer integration adapter into the appropriate context and read by a supplier or policy.

For example, `catalog-service` remains the service ID regardless of whether a request carries `hint=stable` or `hint=canary`. The hint only changes which candidates qualify for that specific call.

### Separating Instance Metadata from Request Data

~~~text
ServiceInstance.getMetadata():
    hint = canary          <-- Registered property of the instance

HTTP request:
    X-SC-LB-Hint: canary   <-- Intent of a specific call
~~~

The supplier matches both sides to pick eligible instances. Never write the current request's hint into a shared `ServiceInstance` metadata map, as doing so can affect other requests.

## 4. Two Key Methods of ServiceInstanceListSupplier

In Spring Cloud LoadBalancer, `ServiceInstanceListSupplier` provides `ServiceInstance` lists reactively:

~~~java
Flux<List<ServiceInstance>> get();

Flux<List<ServiceInstance>> get(Request request);
~~~

These are illustrative signatures from the API; `Request` belongs to LoadBalancer's abstraction, not necessarily an `HttpServletRequest`.

- `get()`: fetches the list using the supplier's source and logic without passing a specific request context.
- `get(Request request)`: lets the supplier use call context to filter or adjust the list.

A supplier that only needs discovery data may return similar results for both calls. A supplier enforcing a hint policy may return different results depending on `Request`.

Pure-function illustration:

~~~java
import java.util.List;
import org.springframework.cloud.client.ServiceInstance;

static List<ServiceInstance> byHint(
        List<ServiceInstance> candidates,
        String requestedHint
) {
    if (requestedHint == null || requestedHint.isBlank()) {
        return candidates;
    }

    List<ServiceInstance> matching = candidates.stream()
            .filter(instance -> requestedHint.equals(
                    instance.getMetadata().get("hint")))
            .toList();

    // Simulates the fallback behavior of HintBasedServiceInstanceListSupplier.
    return matching.isEmpty() ? candidates : matching;
}
~~~

This function depicts the **filtering step after a shared list is obtained**. It does not perform discovery and does not pick a single instance itself. Instance selection (such as round-robin) occurs after this filtering step.

The example above simulates the fallback behavior of Spring Cloud's built-in hint supplier: if no instance matches the hint, it returns the original list. **Do not rely on this fallback behavior to enforce tenant isolation or access control**. If policy strictly requires routing to the specified group, filter strictly, handle the empty-list case explicitly, and enforce authorization at the appropriate layers.

## 5. Why Ordering in the Supplier Chain Matters So Much

A supplier chain can wrap multiple layers: discovery queries, caching, health checks, zone filtering, hints, or custom filters. These steps cannot be reordered arbitrarily.

With per-request filtering policies, the desired structure is typically:

~~~text
Discovery source
    ↓
Shared list cache
    ↓
Per-request filter (e.g., hint)
    ↓
Candidate list for the current request
    ↓
LoadBalancer picks one ServiceInstance
~~~

In this model, the cache holds the shared list, while the filter builds a request-specific list **after reading from the cache**.

~~~mermaid
flowchart TD
    D["DiscoveryClientServiceInstanceListSupplier"]
    C["CachingServiceInstanceListSupplier"]
    H["HintBasedServiceInstanceListSupplier"]
    L["LoadBalancer"]
    D -->|"shared list"| C
    C -->|"reusable"| H
    H -->|"filtered by current request"| L
~~~

Official Spring Cloud documentation advises placing `CachingServiceInstanceListSupplier` right after the network-backed instance source, before other filtering suppliers. With `HealthCheckServiceInstanceListSupplier`, keep in mind that it has its own result-retention mechanism; combining it with an extra cache must be evaluated carefully to avoid two redundant cache layers.

### Risk of Placing Cache After a Per-Request Filter

Suppose the chain is misordered with respect to data semantics:

~~~text
Discovery -> hint filter -> shared cache -> LoadBalancer
~~~

What can happen when a cache stores filtered results without distinguishing requests:

1. Request A carries `hint=canary`; the filter returns `[catalog-canary-1]`.
2. The shared cache stores that list for `catalog-service`.
3. Request B carries `hint=stable`; the cache may serve back `[catalog-canary-1]`.
4. Request B gets the wrong candidate even though discovery still holds two stable instances.

This is the failure mode of **cross-request cache contamination**. Exact runtime behavior depends on the implementation and cache key, yet the safe rule is **never store per-request filtered results in a cache keyed solely by service ID**.

If you truly need to cache per-request outcomes, the cache key must incorporate every criterion affecting the result, use proper expiration, and avoid caching sensitive data. In most LoadBalancer scenarios, caching the baseline list and filtering per request afterward is simpler and easier to control.

## 6. Configuration Example with HintBasedServiceInstanceListSupplier

An easy-to-observe practice setup uses `SimpleDiscoveryClient` to supply a static instance list.

### Declaring Instances and Metadata

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://127.0.0.1:8081
                metadata:
                  hint: stable
              - uri: http://127.0.0.1:8082
                metadata:
                  hint: stable
              - uri: http://127.0.0.1:8083
                metadata:
                  hint: canary
~~~

All three instances belong to the same `catalog-service`. The `hint` metadata value is an attribute of each instance, not of a request.

### Configuring the Supplier Chain

In Spring Cloud versions supporting the corresponding builder methods, the service's supplier chain can follow this template:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalancerClient;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@LoadBalancerClient(
        name = "catalog-service",
        configuration = CatalogLoadBalancerConfiguration.class
)
class CatalogLoadBalancerRegistration {
}

// Place this class outside the default component scan scope or configure it
// so that it is only used inside the catalog-service child context.
class CatalogLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier catalogServiceInstanceListSupplier(
            ConfigurableApplicationContext context
    ) {
        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withCaching()
                .withHints()
                .build(context);
    }
}
~~~

The builder methods express the chain **discovery source → caching → hint filtering**. `@LoadBalancerClient` scopes this configuration to the named service ID. When adding this to a project, place `CatalogLoadBalancerConfiguration` outside the main application context's component scan scope so the per-service bean is not applied unintentionally elsewhere.

If the underlying discovery client already caches data (as in some registry integrations), consider disabling LoadBalancer's cache layer to avoid stacked caching. For a test application, you can keep the setup above to observe each role clearly.

### Sending Two Requests with Different Contexts

~~~http
GET http://catalog-service/products/42
X-SC-LB-Hint: stable
~~~

~~~http
GET http://catalog-service/products/42
X-SC-LB-Hint: canary
~~~

When the HTTP client is LoadBalancer-integrated and request headers flow through the proper adapter, `HintBasedServiceInstanceListSupplier` reads the `X-SC-LB-Hint` header, matches it against the `hint` metadata key, and supplies different candidate lists.

| Request | Discovery/cache list | Post-hint filter list |
|---|---|---|
| A: `stable` | `[8081, 8082, 8083]` | `[8081, 8082]` |
| B: `canary` | `[8081, 8082, 8083]` | `[8083]` |
| C: no hint | `[8081, 8082, 8083]` | `[8081, 8082, 8083]` |
| D: unmatched `preview` | `[8081, 8082, 8083]` | `[8081, 8082, 8083]` (default fallback) |

These are the expected results of the **hint supplier** under normal behavior; they do not yet reflect the final pick made by the LoadBalancer algorithm. For request A, for example, round-robin will proceed to choose one of the two stable instances depending on its state.

Note: the localhost example only works when the caller and instances share a network environment where `127.0.0.1` is reachable.

## 7. How Request Context Reaches the Supplier

Request data is placed into LoadBalancer's `Request` abstraction by the integrated HTTP client. Depending on the adapter and Spring Cloud version, the context may contain `RequestDataContext`, headers, or another request context object.

Conceptual flow:

~~~mermaid
sequenceDiagram
    participant Client as HTTP client
    participant Adapter as LoadBalancer adapter
    participant Supplier as Supplier chain
    participant LB as LoadBalancer
    participant Target as Target instance
    Client->>Adapter: HTTP request + hint header
    Adapter->>LB: choose(Request context)
    LB->>Supplier: get(Request)
    Supplier-->>LB: Request-filtered list
    LB-->>Adapter: Selected ServiceInstance
    Adapter->>Target: Send HTTP to host:port
    Target-->>Adapter: HTTP response
    Adapter-->>Client: Response
~~~

This explains a common pitfall: a `get(Request)` filter works when invoked through an integrated HTTP client, yet produces different results when test code calls `get()` directly or invokes the selector without supplying context. In that case, the supplier has no request hint data to filter on.

### Distinguishing Three Information Groups

- **Instance source:** answers "which replicas exist for this service?"
- **Request context:** answers "what kind of replica does this call require?"
- **Target selection policy:** answers "among eligible candidates, which replica should be chosen?"

All three steps must be accurate for the HTTP client to receive the right target. Successful target selection also does not guarantee HTTP transport and server execution will succeed.

## 8. Shared Data Can Also Be Processed by Policy

Not every supplier that ignores `Request` behaves like a raw discovery source. Some transformation steps rely on shared configuration or instance metadata, such as:

- **Zone preference:** picks instances whose `zone` metadata matches the client's zone. If the caller's zone is statically configured, the result can be reused across many calls from that caller.
- **Health filtering:** based on endpoint probes, produces a list of instances currently meeting health criteria.
- **Weighting:** reads `weight` metadata or a configured weight function to influence instance selection.
- **Instance subset restriction:** a configuration may define a fixed subset for a client to narrow access scope.

Thus, the key criterion is not "whether filtering occurs," but **whether the result depends on data that varies between requests**.

For example, if the client's zone is fixed to `zone-a`, zone preference can be derived from shared data. If each request declares its own zone, zone filtering becomes request-specific and must not be placed in a shared cache whose key omits the zone.

## 9. How Health Checks, Caching, and Request Filtering Differ

These three mechanisms are easy to confuse as doing the same job because all three affect the instance list.

| Mechanism | Primary input | Goal | Risk if misconfigured |
|---|---|---|---|
| Cache | List from discovery or backing supplier | Reduce repeated query cost | Stale lists, wrong caching scope |
| Health check | Endpoints and probe outcomes | Exclude or limit unhealthy instances | Dropping healthy instances, excessive probing, stale status |
| Request filtering | Request context plus instance metadata | Return candidates fitting a specific request | Mixing criteria across requests, unintended fallbacks |

`HealthCheckServiceInstanceListSupplier` has its own replay/result-retention mechanism, so Spring Cloud recommends placing it immediately after the network-backed source and considering **not** wrapping it with `CachingServiceInstanceListSupplier` unnecessarily. Never copy one supplier ordering across every combination without examining data types and how each supplier holds state.

Meanwhile, `HintBasedServiceInstanceListSupplier` is a clear example of request filtering: it needs the candidate list before matching metadata against the incoming hint.

## 10. Bugs When Mixing Shared and Per-Request Data

| Symptom | Cause to check | How to diagnose |
|---|---|---|
| `stable` requests occasionally hit canary | Hint not forwarded, fallback on mismatch, or wrong supplier order | Log service ID, received hint, and candidate list before/after filtering |
| Two requests with different hints get same filtered list | Per-request result cached under a service-ID-only scope | Inspect cache position, cache key, and delegate chain |
| Direct supplier calls always return all instances | Calling `get()` instead of `get(Request)`, or request lacks context | Verify how `Request` is constructed and passed |
| Stopped instance still chosen after scale down | Cache/discovery/health check not updated yet | Check TTL, heartbeats, and refresh timestamps |
| Hint filter returns all instances despite zero replicas for hint | Default fallback behavior of `HintBasedServiceInstanceListSupplier` | Inspect `hint` metadata and confirm whether strict filtering is needed |
| Filtered list is right yet HTTP fails | Host/port, TLS, network, or backend unavailability | Separate selection errors from HTTP transport errors |
| A request reaches an unauthorized instance group | Using client-supplied hints as authorization | Enforce access control independently of routing hints |

### Do Not Use Cache to Store Ephemeral Request State

Values like trace IDs, user IDs, access tokens, or per-request cookies must never be placed into shared instance lists. Moreover, you do not need to dump all of those values into debug logs: logging non-sensitive routing attributes—such as service ID, hint group, and selected instance—is usually sufficient.

### Do Not Confuse the Filtered List with LoadBalancer's Output

A supplier returns **multiple candidates**; LoadBalancer selects one concrete instance. If there are two stable instances, sending the same `stable` hint on two requests does not mean both must land on the exact same instance.

## 11. Practice: Testing Independence Between Requests

You can validate the configuration using a setup with three endpoints and four request types:

1. Declare two instances with `hint=stable` and one with `hint=canary`.
2. Use `ServiceInstanceListSupplier.builder().withDiscoveryClient().withCaching().withHints()` in `catalog-service` configuration.
3. Send requests sequentially with `X-SC-LB-Hint: stable`, `canary`, no hint, and an unmatched hint.
4. Compare the discovery list with each request's candidate list; they should match the table in Section 6.
5. Repeat in reverse request order. Filtering results for A must never depend on B having run right before it.
6. Stop one instance, wait for discovery/cache refresh, and resend. Observe the difference between **shared source** updates and **per-request filter** behavior.

A helpful observation log distinguishes:

~~~text
serviceId=catalog-service sourceCandidates=3
requestHint=stable filteredCandidates=2
selectedInstance=catalog-stable-2
httpStatus=200
~~~

Those lines are a desired log format example, not automatic framework log output. Combining trace IDs with pre/post-filter candidate counts pinpoints whether a fault lies in discovery, request context, filtering, or the HTTP step.

## 12. Design Rules to Remember

1. Determine **data scope** before deciding whether to cache: per service ID, per client, or per request.
2. Cache shared instance lists near the retrieval source; apply request-dependent filters afterward.
3. Forward context to suppliers via `get(Request)` whenever policies rely on headers, cookies, or request attributes.
4. Treat `ServiceInstance` metadata as descriptive instance data; never mutate shared metadata to hold the current caller's criteria.
5. Verify behavior when zero instances match: some suppliers fall back to the original list, whereas strict policies may need an empty list or an error.
6. Distinguish the **supplied** list, the **selected** instance, and the **executed** HTTP request; they are three independently observable stages.
7. When combining caching, health checks, zone preference, and hints, verify delegate order and each supplier's semantics in your Spring Cloud version.

The core principle of the instance supplier chain is: **discovery and metadata provide the baseline data for a service ID; request context only narrows candidates for the current call; LoadBalancer picks one instance from that result**. Separating these two data categories lets the system cache effectively while routing accurately when requests carry differing requirements.

**Official reference:** [Spring Cloud Commons – Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html).
