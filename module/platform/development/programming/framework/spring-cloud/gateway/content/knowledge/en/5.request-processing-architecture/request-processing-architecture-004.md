# RouteDefinition, Route, and Configuration Conversion in Spring Cloud Gateway

In **SPRING_CLOUD_GATEWAY**, declaring a route in YAML is only the step of describing intent: which requests are accepted, where they are forwarded, and which filters apply. To process real HTTP traffic, Spring Cloud Gateway must convert that description into an **executable `Route`** containing predicates for matching requests and filter objects for the processing chain.

This lesson belongs to the **Request Processing Architecture** chapter and explains the path **configuration → `RouteDefinition` → `Route` → route selection on incoming request → filter chain → downstream**. Understanding these steps helps diagnose issues such as "the declaration exists, yet the route does not appear", "the route is registered, yet it never matches", "a filter is placed in YAML, yet it does not run", or "the route was updated, yet the system still uses the old version".

> **Example scope:** Java class names and main YAML configurations illustrate **Spring Cloud Gateway Server WebFlux** in versions with the corresponding API/structure, especially Gateway 4.x. **Gateway Server MVC** has its own pipeline and routing mechanism. Starter names, properties, and route management mechanisms can change across versions; always check the documentation for your exact release train before applying.

## 1. Two Models to Keep Separate

At the architectural level, the Gateway performs two distinct jobs:

1. **Building the routing model from configuration**: loading route declarations from configuration files, repositories, discovery, or other sources; converting them into executable predicates and GatewayFilters.
2. **Processing individual HTTP requests**: finding a `Route` that matches an incoming request, running the filter chain, forwarding the request to the corresponding upstream/downstream, and returning the response.

These two jobs are related, yet **YAML is not re-read and re-parsed on every request**. The Gateway maintains a built or cached set of routes; refreshing the route set follows its own process.

~~~mermaid
flowchart TD
    subgraph BUILD["Route build / refresh phase"]
        A["application.yml, repository, discovery"] --> B["RouteDefinitionLocator"]
        B --> C["RouteDefinition"]
        C --> D["RouteDefinitionRouteLocator"]
        P["RoutePredicateFactory"] --> D
        F["GatewayFilterFactory"] --> D
        D --> E["Route (predicates + filters + URI + metadata)"]
        E --> L["RouteLocator / route cache"]
    end
    subgraph REQUEST["HTTP processing phase"]
        R["HTTP request"] --> H["RoutePredicateHandlerMapping"]
        L --> H
        H --> M{"Matching route?"}
        M -->|"No"| N["Not forwarded via this route; usually returns 404"]
        M -->|"Yes"| W["FilteringWebHandler"]
        W --> G["GlobalFilter + GatewayFilter"]
        G --> U["Routing filter / downstream"]
        U --> V["Response to client"]
    end
~~~

The diagram illustrates the core components. In production operation, security filters, Spring WebFlux handlers, caching, load balancers, and response-processing filters also participate according to configuration.

## 2. `RouteDefinition`: Configuration-Level Route Description

`RouteDefinition` is a **data object describing** a route. In Gateway Server WebFlux, it is typically built from bound configuration or provided by a `RouteDefinitionLocator`. It holds key properties:

| Property | Role | Example |
|---|---|---|
| `id` | Route identifier for management and observability | `orders-read` |
| `uri` | Forwarding destination or scheme for the routing step | `http://localhost:9090`, `lb://order-service` |
| `predicates` | Declared list of conditions to accept a request | `Path=/api/orders/**`, `Method=GET` |
| `filters` | Declared list of route-specific filters | `StripPrefix=1`, `SetRequestHeader=...` |
| `order` | Priority **among routes** when searching for a match | `-10` |
| `metadata` | Additional data for classification or processing integration | `owner: orders-team` |

The following YAML example shows a `RouteDefinition` in the declarative format commonly used in Gateway Server WebFlux 4.x:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders-read
          order: -10
          uri: http://localhost:9090
          predicates:
            - Path=/api/orders/**
            - Method=GET
          filters:
            - StripPrefix=1
            - SetRequestHeader=X-Gateway-Route,orders-read
          metadata:
            owner: orders-team
~~~

Meaning:

- The route has ID `orders-read`, with priority `-10` compared to routes with larger `order` values.
- Only requests whose path matches `/api/orders/**` **and** whose method is `GET` pass all predicates of the route.
- After the route is selected, `StripPrefix=1` removes the first path segment; `SetRequestHeader` sets the header on the request sent to the backend.
- `uri` points to `http://localhost:9090`. This is the **downstream address as seen from the environment running the Gateway**, not necessarily `localhost` on the client machine.
- `metadata.owner` is user-defined sample data. It **does not create any behavior on its own** unless a component reads that metadata.

**Important:** the YAML above is not the runnable `Route` object itself. Values such as `Path`, `Method`, `StripPrefix`, etc. are still **name and argument declarations** that must be resolved by the Gateway into processing objects.

### PredicateDefinition and FilterDefinition

In the declarative model, each item under `predicates` corresponds to a `PredicateDefinition`, and each item under `filters` corresponds to a `FilterDefinition`. They store the factory name and argument map parsed from shortcut syntax or expanded configuration syntax.

Example:

~~~yaml
predicates:
  - Path=/api/orders/**
  - Method=GET
filters:
  - StripPrefix=1
~~~

Here `Path` and `Method` are names of the corresponding **RoutePredicateFactory** implementations; `StripPrefix` is the name of a **GatewayFilterFactory**. These declarations are not yet directly lambdas receiving a request or filters on which `filter(exchange, chain)` can be called.

Not every YAML property belongs to `RouteDefinition`: some configuration groups such as `default-filters`, global CORS, HTTP client, or discovery are managed at the Gateway level and applied through separate build or runtime steps.

## 3. `Route`: The Evaluable and Executable Model

In Gateway Server WebFlux, a constructed `Route` has key components such as:

- **ID**, **URI**, **order**, and **metadata** carried over from the definition or set via DSL.
- **Executable predicate**, typically asynchronous and bound to `ServerWebExchange`, used to check whether a request belongs to the route.
- **Initialized list of `GatewayFilter` instances**, used to process the request/response if the route is selected.

The difference can be summarized as follows:

| `RouteDefinition` | `Route` |
|---|---|
| Describes *what is desired* using names and arguments | Holds components that *actually execute* the described steps |
| `Path=/api/orders/**` is configuration | Built predicate that inspects `ServerWebExchange` |
| `StripPrefix=1` is a filter definition | Created `GatewayFilter` with `parts=1` |
| Suitable for storing, loading, and editing configuration | Suitable for the Gateway to match and process requests |
| Retrieved via `RouteDefinitionLocator` | Provided via `RouteLocator` |

Do not think of a `Route` as a single routed request. A `Route` is an object representing a rule applicable to **many requests**. Each request has its own `ServerWebExchange` and is only associated with the route after predicates match.

## 4. Sources of `RouteDefinition`

In Gateway Server WebFlux, the `RouteDefinitionLocator` interface represents a **source from which route definitions are read**. A system can have multiple sources:

| Source | Typical Operation | Notes |
|---|---|---|
| Static configuration | Binds the `routes` list from application YAML/properties | Editing the file does not change runtime routes without an appropriate reload/refresh |
| Route repository | Definitions are stored in a `RouteDefinitionRepository` | Save/delete operations and cache reloading must be coordinated consistently |
| Service discovery | A component defines routes from service discovery data when enabled and configured accordingly | Discovery client/load balancer are extra dependencies; they do not appear just because a URI says `lb://` |
| Custom source | Application provides a custom `RouteDefinitionLocator` | Must manage duplicate IDs, invalid data, and refresh lifecycle |

Some versions include specific classes/beans such as `PropertiesRouteDefinitionLocator`, `DiscoveryClientRouteDefinitionLocator`, or a composite mechanism combining multiple locators. Naming, features, and activation conditions must be verified against the exact version in use.

### Why Distinguish a Locator from a Repository?

- **Locator** returns readable definitions to be converted into routes.
- **Repository** is an interface/mechanism supporting saving, finding, and deleting definitions; a repository typically also serves as a source of definitions.
- **Refresh** determines when the active `Route` set is rebuilt/reloaded. A successful `save` operation does not prove all Gateway instances are simultaneously using the new route.

In a cluster with multiple Gateway instances, consider **distributing changes and synchronizing caches** across instances; do not assume every node updates automatically just because one node received a new route.

## 5. How Does `RouteDefinitionRouteLocator` Convert Configuration into a Route?

`RouteDefinitionRouteLocator` is a bridge between **declarative definitions** and **runnable routes**. In this WebFlux model, the conceptual process consists of:

1. **Fetch `RouteDefinition`s** from sources via `RouteDefinitionLocator`.
2. **Build predicates**: for each `PredicateDefinition`, find the matching `RoutePredicateFactory` by name; bind/validate arguments; create the predicate.
3. **Combine predicates**: predicates declared within the same route are typically combined with **AND**. For a route to match, every required condition must hold.
4. **Build `GatewayFilter`s**: for each `FilterDefinition`, find the corresponding `GatewayFilterFactory` and apply the bound arguments. Configured `default-filters`, if applicable, may also be attached to the route.
5. **Construct `Route`** with predicates, filters, ID, URI, order, and metadata.
6. **Expose via `RouteLocator`** for request processing to consume; there may be a caching/sorting layer for routes in the pipeline.

~~~mermaid
flowchart LR
    RD["RouteDefinition: orders-read"] --> RP["PathDefinition + MethodDefinition"]
    RD --> FD["StripPrefix + SetRequestHeader definitions"]
    RP --> RF["RoutePredicateFactory"]
    FD --> GF["GatewayFilterFactory"]
    RF --> P["Executable predicate (AND)"]
    GF --> FIL["GatewayFilter objects"]
    P --> R["Route: orders-read"]
    FIL --> R
    RD --> R
~~~

If a predicate/filter name does not exist or arguments are invalid, conversion can fail, log errors, or render the route unavailable depending on the version and when the route set is loaded. Therefore, before debugging request-time filters, verify **whether the route was successfully created**.

### Easily Confused Similar Names

| Component | Question It Answers |
|---|---|
| `RouteDefinitionLocator` | Where do route declarations come from? |
| `RouteDefinitionRouteLocator` | How are declarations turned into runnable routes? |
| `RoutePredicateFactory` | How does this name/argument pair build a match condition? |
| `GatewayFilterFactory` | How does this name/argument pair build a route filter? |
| `RouteLocator` | Which `Route`s currently exist for the Gateway to choose from? |
| `RoutePredicateHandlerMapping` | For this request, which `Route` matches? |
| `FilteringWebHandler` | Once a `Route` is selected, how is the filter chain executed? |

`RouteLocator` is the interface that provides `Route`s; not every implementation converts from `RouteDefinition`.

## 6. From `RouteLocator` to a Real Request

Consider the request:

~~~http
GET /api/orders/42 HTTP/1.1
Host: gateway.example.test
Authorization: Bearer <token>
~~~

Assume the Gateway runs with the YAML from section 2 and downstream serves `GET /orders/42`. When a request arrives:

1. **Spring WebFlux receives the request** and creates a `ServerWebExchange`. `WebFilter`s outside the routing handler, such as Spring Security WebFlux if configured, can process the request here.
2. **`RoutePredicateHandlerMapping`** queries the `Route` set from `RouteLocator` and evaluates predicates in the order routes are provided. For this example, `Path` matches `/api/orders/42` and `Method` matches `GET`.
3. On a match, the Gateway **attaches the selected `Route` to the exchange** so subsequent components know which route is active.
4. **`FilteringWebHandler`** combines global filters and the `Route`'s gateway filters, sorts them using the filter ordering mechanism, and executes the processing chain.
5. `StripPrefix=1` changes the path from `/api/orders/42` to `/orders/42`; `SetRequestHeader` sets the `X-Gateway-Route` header on the forwarded request.
6. The appropriate **routing filter** forwards to the target URI; ordinary HTTP(S) cases typically use components such as Netty routing in Gateway Server WebFlux. When downstream responds, response-processing filters complete and the Gateway sends the result back to the client.

This description is the **logical flow**. Exact ordering of certain filters depends on `Ordered` of global filters, gateway filters, and version; do not infer that all filters run strictly in YAML appearance order when global/default filters or filters with explicit orders exist.

### What If the Request Does Not Match?

- `POST /api/orders/42` does not satisfy `Method=GET`.
- `GET /public/orders/42` does not satisfy `Path=/api/orders/**`.
- If no other route matches and no other handler serves the path, the Gateway typically returns **404**.

A route **existing** yet failing to **match predicates** is a different state from a route failing to be constructed due to misconfiguration. Inspection and remediation differ for these two situations.

## 7. Route Order Differs from Filter Order

### Order Between Routes

A `Route`'s `order` property controls priority when **multiple routes match the same request**. Lower values are normally evaluated earlier in the sorted route list.

Example:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders-get
          order: -20
          uri: http://localhost:9091
          predicates:
            - Path=/api/orders/**
            - Method=GET

        - id: orders-fallback
          order: 10
          uri: http://localhost:9092
          predicates:
            - Path=/api/orders/**
~~~

With `GET /api/orders/42`, both routes can match, yet `orders-get` takes precedence due to its smaller order. With `POST /api/orders/42`, the first route does not satisfy Method, so the second route can be selected.

**Do not rely on YAML appearance order** to resolve conflicts when two routes match the same request. Set explicit `order` values, design sufficiently distinct predicates, and avoid depending on tie-breaking behavior when `order` values are equal.

### Order Inside the Filter Chain

During request processing, the Gateway merges **`GlobalFilter`s** and **route-level `GatewayFilter`s** and sorts them appropriately. In a filter chain with before/after (`pre`/`post`) logic:

- The **before** part (prior to calling the next filter) typically proceeds in ascending order.
- The **after** part (once the next filter completes) typically runs in reverse order.

~~~text
Filter A — pre
  Filter B — pre
    Filter C — pre
      Routing / downstream
    Filter C — post
  Filter B — post
Filter A — post
~~~

This is a general view of the chain when filters continue the chain. A filter can reject a request or terminate early, such as a security/rate-limit rule, so **requests do not always reach downstream**. Route-level `order` **does not** determine the execution position of individual filters.

## 8. Roles of GlobalFilter, Default Filters, and Route-Specific Filters

When designing a multi-microservice Gateway, choose the right processing scope:

| Type | Scope | Example Usage |
|---|---|---|
| `GlobalFilter` | Participates in requests routed by the Gateway through the corresponding pipeline | Attaching correlation ID, logging, measuring latency, common error handling |
| `default-filters` | Default filters applied to routes created from configuration within supported mechanisms | Removing/setting shared headers, baseline policies |
| `filters` of a `RouteDefinition` | Applied only when that specific route is selected | `RewritePath`, `StripPrefix`, service-specific retries, per-API rate limits |

**`GlobalFilter` is not synonymous with `WebFilter`.** In WebFlux, `WebFilter` (for example, Spring Security HTTP components) sits in the overall web pipeline and can process requests even before the Gateway selects a route. By contrast, Gateway's `GlobalFilter` is typically invoked in the processing chain **after a `Route` is selected**.

If you need to block requests **that match no route at all**, choose an appropriate interception point, such as WebFlux-layer security or upstream infrastructure; do not assume `GlobalFilter` will run for every HTTP request arriving on the port.

An example of header modification on a route:

~~~yaml
filters:
  - RemoveRequestHeader=Cookie
  - SetRequestHeader=X-Edge-Service,orders
~~~

When the route matches, filters created from this declaration run in the resulting chain order. However, removing cookies or setting headers is not a complete security policy: check interactions with authentication, authorization, token relay, and upstream proxies.

## 9. Must Java DSL Routes Go Through `RouteDefinition`?

**No.** Gateway Server WebFlux supports creating `Route` objects directly via a Java DSL such as `RouteLocatorBuilder`, for example in releases with the corresponding API:

~~~java
import org.springframework.cloud.gateway.route.RouteLocator;
import org.springframework.cloud.gateway.route.builder.RouteLocatorBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class GatewayRoutes {

    @Bean
    RouteLocator catalogRoutes(RouteLocatorBuilder builder) {
        return builder.routes()
            .route("catalog-java", r -> r
                .path("/api/catalog/**")
                .filters(f -> f.stripPrefix(1))
                .uri("http://localhost:9092"))
            .build();
    }
}
~~~

This path produces a **`RouteLocator` with executable `Route`s** without going through the YAML configuration → `RouteDefinition` → `RouteDefinitionRouteLocator` flow for those DSL-declared routes. However, when a request arrives, those `Route`s are still selected and executed through the Gateway's routing/filter pipeline.

Brief comparison:

- **`RouteDefinition` from YAML/repository**: convenient for data-driven declarations, externalized changes without code edits, and configuration-based route management.
- **Routes created via Java DSL**: convenient when predicates/filters are expressed in code, programmatic structures, or custom conditions.
- **Common output**: `Route` objects used by the Gateway to evaluate predicates and execute the filter chain.

Therefore, saying "every `Route` goes through `RouteDefinitionRouteLocator`" is **incorrect**. This converter is central to the **data-driven route definition flow**, not mandatory for every way of declaring routes.

## 10. When Configuration Changes, When Do Running Routes Update?

A route can change when:

- An operator edits static configuration and **restarts** the Gateway or uses a supported reload mechanism.
- The application saves/deletes routes via a repository or management API.
- Service discovery provides updated information for dynamically generated routes.
- A **refresh routes** event/mechanism triggers re-reading and reconverting definitions.

In Gateway Server WebFlux versions featuring `CachingRouteLocator`, the `Route` set may be **cached** to avoid rebuilding on every request. Modifying the data source does not guarantee the cache changes instantaneously. Verify the refresh event mechanism, cache behavior, and final route state on each Gateway instance.

~~~mermaid
sequenceDiagram
    participant O as Operator / configuration
    participant S as RouteDefinition source
    participant C as RouteLocator / cache
    participant G as Gateway request handler
    O->>S: Add/edit/delete RouteDefinition
    Note over S,C: Changing source data does not immediately change cache
    O->>C: Trigger appropriate refresh mechanism
    C->>S: Re-read definitions
    S-->>C: List of RouteDefinitions
    Note over C: Rebuild Routes, predicates, and filters
    G->>C: New request looks up Route
    C-->>G: Updated Route set (after refresh succeeds)
~~~

**Note on change control:** If using route management or Actuator Gateway endpoints, restrict access via security and internal networking, exposing only necessary endpoints. Never allow Internet users to write/edit routes or trigger refreshes. Availability, endpoint paths, and exposure rules vary across Spring Boot/Gateway versions.

### Updating Routes and Updating Service Instances Are Two Different Things

A URI like `lb://order-service` indicates routing via an appropriate load balancing/service discovery mechanism. **The `Route` itself may not change**, while the set of `order-service` instances changes during scaling or rolling deployments. On the other hand, adding a new service to **generate a new route** via a discovery locator involves updating the `Route` set.

Distinguish clearly:

- `RouteDefinition` changes: the route's ID, predicates, filters, or URI changes.
- Service instance list changes: the `lb://...` URI can remain identical while a different downstream is picked at request time.
- Route/cache refresh: how the Gateway sees changes in the `Route` set, which can be independent of instance list updates in the load balancer.

## 11. Diagnosing Errors by the Right Stage

An effective approach is to classify errors by **where they occur** before applying fixes.

| Symptom | Stage to Check | Diagnostic Questions |
|---|---|---|
| Route does not appear in list | Definition source / conversion / cache | Did YAML bind properly? Does the locator return `RouteDefinition`? Were factories found? Was refresh triggered? |
| Startup or refresh error when building routes | Conversion | Are predicate/filter names valid and arguments compatible with the version? Can the URI be parsed? |
| Route is in list, yet requests get 404 | Predicate matching | Do Path, Method, Host, or Header truly satisfy all predicates? Does a higher-priority route intercept first? |
| Request reaches backend with wrong path | GatewayFilter chain | Did `StripPrefix`/`RewritePath` run? Is a default/global filter or another proxy modifying the path? |
| Route exists, filters run, yet downstream errors | Routing / downstream | Are URI, DNS, load balancer, TLS, connectivity, and backend health correct? |
| Config changed, yet behavior unchanged | Reload / refresh | Which source was updated? Did every node's route cache reload? |
| Auth or rate limiting behaves unexpectedly | WebFilter / GatewayFilter | Which layer holds the rule? Does a route match before the filter runs? What are the order and scope? |
| Metrics lack route ID or request has no trace | Observability | Did the request select a `Route`? Are metric/tracing integrations enabled for the right version? |

### Appropriate Observability Tools

In some Gateway versions, **Spring Boot Actuator + Gateway actuator endpoints** can provide visibility into known routes and refreshing. Paths commonly mentioned in docs are `/actuator/gateway/routes` or `/actuator/gateway/refresh`, **but do not assume these endpoints are always enabled, share the same contract, or are accessible in every version**. Consult the reference docs and applicable security policies.

Inspection sources to combine:

1. **Dependencies and versions**: ensure artifacts, WebFlux/MVC variant, and configuration namespaces align.
2. **Startup/refresh logs**: look for errors binding data or instantiating predicates/filters.
3. **Constructed `Route` list**: check ID, URI, order, predicates, and active filters.
4. **Request and downstream logs**: compare actual URI/path/headers, response codes, and timings.
5. **Metrics/tracing**: inspect route ID, latency, and error rates if observability is enabled.

For systems with multiple Gateway instances, include the **instance ID** when comparing configuration or request paths; otherwise, the same URL through a load balancer can return different results because caches across instances are out of sync.

## 12. Hands-On: Verifying the Path from YAML to Route

Suppose a simple backend at `http://localhost:9090` returns HTTP 200 upon receiving `GET /orders/42`. Configure Gateway Server WebFlux following the section 2 example; assume the Gateway server runs on `localhost:8080`.

### Step 1 — Confirm the Route Was Loaded

Start the Gateway and inspect logs or an authorized management endpoint to confirm route ID `orders-read` exists with URI `http://localhost:9090`, `Path` and `Method` predicates, and the corresponding filters.

**If the route is missing**, stop at the configuration conversion step to inspect YAML, versions, and factories rather than modifying the backend.

### Step 2 — Send a Matching Request

~~~bash
curl -i http://localhost:8080/api/orders/42
~~~

Expected: the Gateway matches `GET` and `/api/orders/42`, applies `StripPrefix=1`, and the backend receives `GET /orders/42` with header `X-Gateway-Route: orders-read`. This assumes no other filter overwrites the path/header or alters the target route.

### Step 3 — Send Non-Matching Requests

~~~bash
curl -i -X POST http://localhost:8080/api/orders/42
curl -i http://localhost:8080/other/orders/42
~~~

Neither request satisfies all predicates of `orders-read`. If the application has no other route/handler accepting them, the result is usually **404**. This does not prove `RouteDefinition` is broken; it proves **route predicates did not select that route**.

### Step 4 — Simulate a Downstream Failure

Stop the backend on port 9090 and resend the valid GET request. Now **the route can still match** and GatewayFilters still execute, but routing to downstream fails, typically yielding a 5xx error. The exact status depends on filters and error-handling/retry/circuit-breaker configuration. Clearly separate downstream connection errors from missing-route errors.

### Step 5 — Modify and Refresh the Route with Verification

If the environment supports dynamic configuration changes, make a valid change (such as editing `Path`) in the **actual configuration source**, trigger the supported refresh workflow, and check both the `Route` list and before/after requests. When using static config files without reload support, **restart** the application in a test environment and verify again.

Record results in a table:

| Case | Signal to Observe | Stage Proven |
|---|---|---|
| Route `orders-read` present | ID, URI, predicates, and filters created | Conversion and RouteLocator |
| Valid GET | Request reaches right backend; path/header transformed | Match + filter + routing |
| POST wrong Method | This route is not selected | Predicate |
| Backend not running | Route still matches, yet downstream connection fails | Routing |
| Route refreshed | New `Route` set visible and active | Cache/refresh |

## 13. Connection to Security and Operability

Understanding the `RouteDefinition` → `Route` path helps implement controlled Gateway capabilities:

- **Authentication and authorization**: decide whether policies should run before route matching (e.g., WebFlux security) or inside a selected route; avoid letting unmatched endpoints accidentally fall outside required checks.
- **Rate limiting**: choose key resolver, route scope, and filter order; ensure traffic exceeding limits is handled according to policy before calling the backend.
- **Circuit breaker and retry**: identify which filters wrap forwarding; avoid retrying non-idempotent operations or generating unintended call amplification.
- **TLS**: verify client-to-Gateway TLS and Gateway-to-downstream TLS are two separately configured connections; neither is determined solely by a `Route` building successfully.
- **Service discovery**: distinguish route discovery from instance selection via `lb://`; inspect both route definitions and instance resolution.
- **Request observability**: attach route IDs and trace context when a route is selected; still capture events for requests blocked before routing via the appropriate layer's component.

Do not equate "having a `Route`" with "the system is secure". Route predicates and filters are only part of overall security; policies at the web server, Spring Security, downstream services, and network infrastructure must also be verified.

## 14. Common Misconceptions

| Misconception | Accurate Explanation |
|---|---|
| `RouteDefinition` and `Route` are the same object | One is a data declaration; the other holds constructed predicates/filters ready to execute |
| Every HTTP request reads YAML and rebuilds the `Route` | The Gateway uses `RouteLocator` and usually caching; refreshing is a separate process |
| Every `Route` must have a `RouteDefinition` | Routes from the Java DSL can be created directly |
| A route with multiple predicates only needs one condition to be true | In standard declarations, predicates of the same route combine with **AND** |
| Routes follow YAML order so filters also run in YAML order | Route selection `order` differs from filter order; the filter chain also includes global/default filters |
| `GlobalFilter` runs for every HTTP request even without a route match | Gateway `GlobalFilter` normally participates after a `Route` is selected; `WebFilter` operates at a different layer |
| Updating the repository means every node already uses the new `Route` | Refresh/caching and synchronization across instances must be considered |
| `lb://service` means `RouteDefinition` is rewritten as instances scale | The `Route` can stay unchanged; the load balancer picks a service instance at request time |
| Gateway returning 404 definitely means YAML is wrong | 404 can also come from predicate mismatch, another route, or another handler |
| Seeing a route in Actuator is enough to prove the backend works | Real requests are needed to verify predicates, filters, and downstream connectivity |

## 15. Architecture Self-Check Checklist

- [ ] I can distinguish **`RouteDefinition` (data)** from **`Route` (executable)**.
- [ ] I know where `RouteDefinitionLocator`, `RouteDefinitionRouteLocator`, and `RouteLocator` operate.
- [ ] I know `RoutePredicateFactory` and `GatewayFilterFactory` are used to instantiate runtime components.
- [ ] I understand **AND** across predicates within one route and priority ordering across routes.
- [ ] I separate **route order** from **filter order**, and **`GlobalFilter`** from **`WebFilter`**.
- [ ] I can explain the behavior of `Path`, `Method`, `StripPrefix`, and `SetRequestHeader` on a real request.
- [ ] I know routes created via Java DSL can bypass the `RouteDefinition` step.
- [ ] I know a configuration change requires an appropriate route-set and cache update workflow.
- [ ] I can distinguish **route not loaded**, **predicate mismatch**, and **downstream unavailable** errors.
- [ ] I have checked Gateway version, WebFlux/MVC variant, and security before enabling route management endpoints.

## Official References

- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — documentation on routes, predicates, filters, GlobalFilter, routing, and route management; select the matching version.
- [Spring Cloud Gateway Project](https://spring.io/projects/spring-cloud-gateway) — project info, release trains, and documentation links.
- [Spring Framework WebFlux Reference](https://docs.spring.io/spring-framework/reference/web/webflux.html) — `DispatcherHandler`, handler mapping, `WebFilter`, and `ServerWebExchange`.
- [Spring Boot Actuator Reference](https://docs.spring.io/spring-boot/reference/actuator/) — configuration principles, security, and exposure of management endpoints.

**Key takeaway:** `RouteDefinition` answers **"what does the configuration say to route?"**; `Route` answers **"which executable rules does the Gateway currently hold?"**; and `RoutePredicateHandlerMapping` plus `FilteringWebHandler` decide **"which rule and filter chain does this specific request pass through?"**. Separating these three questions helps you develop and operate an API Gateway safely and verifiably as microservices scale.
