# RefreshRoutesEvent and Refreshing the Route Cache

## 1. The Problem: Route Config Changed, Why Is Gateway Still Taking the Old Path?

In a microservices architecture, **Spring Cloud Gateway Server WebFlux** often serves as the unified entry point: accepting requests, selecting a route via **route predicates**, running the **filter chain**, rewriting paths/headers, optionally resolving backends via `lb://service-id`, and proxying requests to the chosen instance. A route may be statically declared in `application.yml` or pulled from a dynamic config store.

Suppose Gateway initially holds the route:

~~~yaml
id: catalog-live
uri: http://localhost:9191
predicates:
  - Path=/api/catalog/**
filters:
  - StripPrefix=1
~~~

An operator updates the target to `http://localhost:9192` in the route definition store. Even though the store holds the new value, subsequent requests may still reach port **9191**. The reason is that **the data-source `RouteDefinition`** and **the cached runtime `Route` list held by Gateway** are not the same object.

Spring Cloud Gateway WebFlux provides **`RefreshRoutesEvent`** to notify route-management components—most notably `CachingRouteLocator`—that the route list needs to be reloaded. On the management API side, the corresponding operation is **`POST /actuator/gateway/refresh`** when Gateway Actuator is enabled and write access is granted.

This is the subject of **"RefreshRoutesEvent and Refreshing the Route Cache"**, in the **Dynamic Routes** chapter of the **SPRING_CLOUD_GATEWAY** module. The goal is to understand **definition source → conversion to runtime routes → cache → refresh**, rather than just memorizing a cURL command. Security, rate limiting, circuit breaking, retries, TLS, and observability must also remain intact whenever routes change.

After this lesson, you will be able to:

1. Distinguish `RouteDefinition`, `RouteLocator`, and `CachingRouteLocator`.
2. Explain what `RefreshRoutesEvent` does and **does not do**.
3. Create/delete a dynamic route in a lab and refresh the cache **without restarting Gateway**.
4. Emit the event from Java **after route definition save/delete operations complete**.
5. Verify runtime routes using Actuator, live requests, and backend logs.
6. Analyze asynchronous refreshes, configuration errors, multiple Gateway replicas, and production security requirements.

> **Scope:** This lesson covers **Gateway Server WebFlux**; Gateway Server MVC uses different implementations and APIs. Management examples are strictly for an **isolated local environment**. Never expose route-modification features or writable Gateway Actuator endpoints to the public Internet.

## 2. Three Layers: `RouteDefinition`, Runtime `Route`, and Route Cache

A common operational mistake is equating **finished writing config** with **requests already routing by that config**. In Gateway WebFlux, keep three layers distinct:

| Layer | Representative Types / Components | Role |
| --- | --- | --- |
| **`RouteDefinition` source** | `PropertiesRouteDefinitionLocator`, `DiscoveryClientRouteDefinitionLocator`, `RouteDefinitionRepository` | Supplies route descriptions: ID, URI, predicates, filters, order, metadata |
| **Runtime `Route`** | `RouteDefinitionRouteLocator`, `RouteLocator` | Converts definitions into bound predicates/filters ready for route selection |
| **Route cache** | `CachingRouteLocator` | Holds the built list of runtime routes so requests do not rebuild them every time |

Conceptual diagram:

~~~mermaid
flowchart TD
    Y["application.yml / Config Server"] --> RD["RouteDefinitionLocator(s)"]
    S["Repository: in-memory / Redis / DB"] --> RD
    D["Service discovery locator (if enabled)"] --> RD
    RD --> C["RouteDefinitionRouteLocator<br/>bind predicates + filters"]
    J["Java DSL RouteLocator (if any)"] --> CO["Composite RouteLocator"]
    C --> CO
    CO --> CA["CachingRouteLocator<br/>runtime route cache"]
    CA --> M["RoutePredicateHandlerMapping"]
    M --> F["GatewayFilter chain"]
    F --> B["HTTP backend / lb://service"]
    E["RefreshRoutesEvent"] -.-> CA
~~~

Class names and locator composition details vary slightly between versions; this diagram outlines the core responsibilities. Specifically, **`RouteDefinitionRepository`** is a definition source, whereas `CachingRouteLocator` sits at the **runtime `Route`** layer. Evicting an entry from the cache is not the same as deleting a definition from the repository.

### 2.1. What Does a `RouteDefinition` Hold?

A typical `RouteDefinition` contains:

~~~text
id          = catalog-live
uri         = http://localhost:9191
predicates  = Path=/api/catalog/**
filters     = StripPrefix=1
order       = 0
metadata    = { group: "lab", revision: "v1" }
~~~

This is not yet an instantiated Java predicate function or an executable `GatewayFilter`. When converting a definition into a runtime `Route`, Gateway must resolve factories by name, bind arguments, validate the configuration, and instantiate predicates and filters.

**Misconfigured routes can fail during the conversion phase.** For instance, an invalid `uri` or a nonexistent `GatewayFilterFactory` can cause a refresh error or prevent the route from working as intended. Checking that YAML/JSON syntax parses cleanly is **never enough**.

### 2.2. What Cost Does the Route Cache Eliminate?

Without a route cache, gathering, converting, and sorting route definitions from multiple sources would add overhead to every request. `CachingRouteLocator` lets incoming requests match against a pre-built runtime route snapshot.

**Consequence:** modifying a repository **without refreshing the cache** may leave new requests routing on old rules. Conversely, refreshing the cache while the repository still holds stale data simply **reloads the same stale data**.

### 2.3. How Does the Route Cache Differ from Other Caches?

| Cache | Contents | Does Refreshing the Route Cache Handle It? |
| --- | --- | --- |
| `CachingRouteLocator` | Runtime `Route` set | **Direct scope** of `RefreshRoutesEvent` |
| Discovery / registry cache | `ServiceInstance` lists, health metadata | **No guarantee** of synchronous refresh alongside routes |
| Spring Cloud LoadBalancer cache | Instance lists / supplier computations | Has its own lifecycle and policies |
| DNS / JVM / HTTP client connection pools | Host lookups and sockets | Not automatically cleared on route refresh |
| CORS configuration mapping | Per-route/path CORS policies | Version/implementation-dependent interaction; verify explicitly |
| CDN / proxy / browser caches | HTTP responses or preflights | Unrelated to Gateway route loading |

For example, `uri: lb://orders-service` stays constant while Eureka swaps instances. An issue there lies in the **discovery/LoadBalancer cache**, not the route definition. Firing `RefreshRoutesEvent` repeatedly should never be treated as a cure-all for instance-discovery lag.

## 3. `RefreshRoutesEvent`: Mechanics, Scope, and Timing

`RefreshRoutesEvent` is a **Spring application event** in Gateway WebFlux under package:

~~~java
org.springframework.cloud.gateway.event.RefreshRoutesEvent
~~~

A component inside the same application can trigger a refresh via:

~~~java
applicationEventPublisher.publishEvent(
        new RefreshRoutesEvent(this));
~~~

In documented WebFlux releases, `CachingRouteLocator` listens for this event and **reloads routes from the source `RouteLocator`** to update its cache; some versions also emit `RefreshRoutesResultEvent` for observing refresh outcomes. Exact internal fetch/swap mechanics or async result delivery vary across releases, so consult the source and docs for your exact version.

~~~mermaid
sequenceDiagram
    participant A as Trusted admin / config change
    participant R as RouteDefinitionRepository
    participant P as ApplicationEventPublisher
    participant C as CachingRouteLocator
    participant L as Source RouteLocator
    participant G as Gateway request handling

    A->>R: save / delete RouteDefinition
    R-->>A: Mono completes
    A->>P: publish RefreshRoutesEvent
    P->>C: notify refresh needed
    C->>L: load, bind, and sort routes
    L-->>C: new runtime Route list
    C-->>C: update route cache
    G->>C: new request needs route selection
    C-->>G: Route from active cache
~~~

This illustrates the **intended logical ordering**. In a reactive implementation, cache updates may execute **asynchronously** relative to `publishEvent(...)` returning or an actuator endpoint responding. Never assume a returning Java event call or an HTTP 200 from refresh **guarantees every replica's cache now holds the new revision**.

### 3.1. Refresh Does Not Save Definitions Automatically

~~~java
publisher.publishEvent(new RefreshRoutesEvent(this));
~~~

**Does not**:

- Create, update, or delete any `RouteDefinition` in a repository.
- Re-read modified `application.yml` files on disk and hot-reload arbitrary properties.
- Propagate events from Gateway A to Gateway B in another process or JVM.
- Clear LoadBalancer, Redis, DNS, or HTTP response caches.
- Verify caller permissions or ensure the new config has no security flaws.

The proper sequence for a new route is **update the definition source, then request a refresh**. With Java's `RouteDefinitionWriter`, wait for the save/delete `Mono<Void>` to **complete** before emitting the event.

### 3.2. What Does HTTP 200 from Actuator Mean?

Official docs state `POST /actuator/gateway/refresh` returns **200** with an empty body when the endpoint handles the refresh request. That indicates success of **the management call**, not proof that new runtime routes are active.

To truly verify:

1. Call `GET /actuator/gateway/routes` over a secured management channel to confirm runtime routes show the desired revision.
2. Send a live business request matching the route and verify target backend and filters.
3. With multiple Gateway replicas, verify **every replica** or use a confirmation-based orchestrator.
4. Declare deployment success only after end-to-end checks pass.

### 3.3. What If Rebuilding Fails?

Gateway Actuator docs note that if an **asynchronous refresh encounters an error**, the operation leaves the existing route list unchanged. This preserves the last working route set rather than replacing it with a broken one.

Still, **do not assume every route source or release guarantees identical "atomic" behavior** under races or partial config edits. Verify on your exact Gateway version by checking error logs, the active route table, and live requests under repeated failures.

## 4. Four Common Ways to Trigger Route Refreshes

| Source / Update Method | Modification Action | What Additional Step Is Needed? |
| --- | --- | --- |
| Actuator managing dynamic routes | `POST/DELETE /actuator/gateway/routes/{id}` | Call `POST /actuator/gateway/refresh` per docs |
| Java via `RouteDefinitionWriter` | `save/delete(Mono<...>)` | Emit `RefreshRoutesEvent` **after completion**; verify runtime |
| Custom DB/Redis repository | Transaction commit / revision bump | Trigger refresh on **every Gateway replica** once new data is ready |
| Auto-generated DiscoveryClient locator | Registry/discovery source updates | Follows its own listener/refresh mechanics; inspect both discovery and route caches |

**Editing `application.yml` on disk is not continuously watched by Gateway by default.** Unlike repository updates, changing a local config file post-startup typically requires an external config reload mechanism or a restart/redeploy. Emitting `RefreshRoutesEvent` alone does not rebind `@ConfigurationProperties` from disk.

Events from Spring Cloud Config/`@RefreshScope` or discovery heartbeats can trigger route refreshes in appropriately wired setups, yet **not every Spring configuration refresh event behaves identically to `RefreshRoutesEvent`**.

## 5. Lab Preparation: Gateway, Actuator, and Echo Backends

The following lab uses two applications:

| Component | Local Address | Role |
| --- | --- | --- |
| WebFlux Gateway | `http://127.0.0.1:8080` | Public API port for routing tests |
| Gateway Actuator | `http://127.0.0.1:9090` | Loopback-only management, write-enabled **for lab** |
| Backend A | `http://127.0.0.1:9191` | Echoes instance ID, path, and header |
| Backend B | `http://127.0.0.1:9192` | Same codebase returning a different instance ID |

Everything runs on loopback on a single machine. **Never deploy these writable management settings on a server reachable by untrusted networks.**

### 5.1. Gateway Dependencies

For a modern Gateway Server WebFlux project, typical Maven dependencies are:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
~~~

Older WebFlux 4.x releases used starter `spring-cloud-starter-gateway`; choose compatible Spring Boot, Spring Cloud BOM, and starter versions for your release. Gateway Server MVC does not use the same configuration mechanism. Never add the Servlet MVC starter to Gateway Server WebFlux just to use Actuator.

When declaring **static routes** in YAML, remember the namespace:

- Gateway Server WebFlux **4.2.x/4.3.x**: `spring.cloud.gateway.routes`.
- Gateway Server WebFlux **5.x**: `spring.cloud.gateway.server.webflux.routes`.

In this lab, **do not declare `catalog-live` in YAML routes**, because we want to create and delete it via the dynamic repository. If the same ID comes from multiple sources, route selection can become non-deterministic.

### 5.2. Gateway `application.yml` in the Lab

~~~yaml
server:
  address: 127.0.0.1
  port: 8080

spring:
  application:
    name: dynamic-routes-lab

management:
  server:
    address: 127.0.0.1
    port: 9090
  endpoint:
    gateway:
      access: unrestricted
  endpoints:
    web:
      exposure:
        include: health,gateway
~~~

Gateway 4.2/5.x docs specify that the `gateway` actuator **disables writes by default**; setting `management.endpoint.gateway.access=unrestricted` alongside `management.endpoints.web.exposure.include=gateway` enables write/refresh APIs in supported versions. Depending on Boot generation, older flags like `management.endpoint.gateway.enabled=true` existed, so follow **the exact version's docs** instead of mixing snippets arbitrarily.

**Why isolate port 9090 and bind `127.0.0.1`?** Strictly to prevent the lab from accidentally exposing route-write endpoints over the network. In Docker/Kubernetes, port binding/forwarding differs; production must use a private management network, admin authn/authz, auditing, and restricted write permissions.

> If the endpoint returns **404/405/403**, check the Actuator dependency, `access`/exposure settings, Spring Security, and management path/port before blaming `RefreshRoutesEvent`.

### 5.3. Echo Backend `application.yml`

Create a Spring Boot WebFlux backend project with dependency `spring-boot-starter-webflux`:

~~~yaml
server:
  address: 127.0.0.1
  port: ${BACKEND_PORT:9191}

demo:
  instance: ${INSTANCE_ID:A}
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
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CatalogController {

    private final String instanceId;

    public CatalogController(
            @Value("${demo.instance:A}") String instanceId) {
        this.instanceId = instanceId;
    }

    @GetMapping("/catalog/items/{id}")
    public Map<String, Object> item(
            @PathVariable String id,
            ServerHttpRequest request) {

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("instance", instanceId);
        body.put("itemId", id);
        body.put("method", request.getMethod().name());
        body.put("path", request.getPath().value());
        body.put("revision",
                request.getHeaders().getFirst("X-Route-Revision"));
        body.put("query", request.getURI().getRawQuery());
        return body;
    }
}
~~~

Launch backends A and B in two terminals from **the same backend project**, and Gateway in a third terminal:

~~~bash
# Backend A, terminal 1
BACKEND_PORT=9191 INSTANCE_ID=A ./mvnw spring-boot:run

# Backend B, terminal 2
BACKEND_PORT=9192 INSTANCE_ID=B ./mvnw spring-boot:run

# Gateway, terminal 3 inside the Gateway project
./mvnw spring-boot:run
~~~

That uses Bash syntax. In PowerShell, set `$env:BACKEND_PORT="9191"` and `$env:INSTANCE_ID="A"` in terminal A, set `9192`/`B` in terminal B, and run `.\mvnw.cmd spring-boot:run` in each terminal.

Test the backends directly:

~~~bash
curl -i "http://127.0.0.1:9191/catalog/items/42"
curl -i "http://127.0.0.1:9192/catalog/items/42"
~~~

Expected JSON outputs contain `"instance":"A"` and `"instance":"B"` respectively. If a backend fails, fix it before testing route refreshes.

## 6. Actuator Lab: Create, Refresh, Retarget, and Delete Routes

### 6.1. Check State Before Creating the Route

On Gateway with no `/api/catalog/**` route declared yet, run:

~~~bash
curl -i "http://127.0.0.1:8080/api/catalog/items/42"

# Inspect runtime routes via loopback management port:
curl -sS "http://127.0.0.1:9090/actuator/gateway/routes"
~~~

The first call should return **404** assuming no other route/handler matches. The runtime list lacks `catalog-live`. This establishes a clean baseline; **404 is not a `RefreshRoutesEvent` failure**.

### 6.2. Create a `RouteDefinition` in the Internal Repository

Gateway Actuator 5.0 docs specify that `POST /actuator/gateway/routes/{id}` accepts a route definition with `predicates` and `filters` as **shortcut DSL strings**, not the raw JSON returned by GET runtime routes.

~~~bash
curl -i -X POST \
  "http://127.0.0.1:9090/actuator/gateway/routes/catalog-live" \
  -H "Content-Type: application/json" \
  --data-binary '{
    "predicates": ["Path=/api/catalog/**"],
    "filters": [
      "StripPrefix=1",
      "AddRequestHeader=X-Route-Revision,v1"
    ],
    "uri": "http://127.0.0.1:9191",
    "order": 0,
    "metadata": {
      "group": "lab",
      "revision": "v1"
    }
  }'
~~~

Per the documented API, success returns **201 Created**. This updates **the Actuator-managed route definition store** inside the process receiving the request; it is **not proof** that Gateway's cache has refreshed.

**Note:** In PowerShell, single-quoted JSON escaping and the `curl` alias behave differently from Bash. Use `curl.exe` or build a PowerShell here-string and send it to the management URL.

### 6.3. Request a Cache Refresh

~~~bash
curl -i -X POST \
  "http://127.0.0.1:9090/actuator/gateway/refresh"
~~~

Official docs note that the refresh endpoint returns **200 OK** with an empty body when accepted. Refresh runs via Gateway's event/cache machinery and can be **asynchronous**: never assume a business request in the very same millisecond sees the new route.

Once the refresh call finishes, inspect the runtime route list **and** send a test request:

~~~bash
# Inspect materialized routes:
curl -sS "http://127.0.0.1:9090/actuator/gateway/routes"

# You can also inspect a specific route ID, depending on version response format:
curl -i \
  "http://127.0.0.1:9090/actuator/gateway/routes/catalog-live"

# Send a new request through the route:
curl -i \
  "http://127.0.0.1:8080/api/catalog/items/42?lang=vi"
~~~

**Illustrative** business response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"instance":"A","itemId":"42","method":"GET","path":"/catalog/items/42","revision":"v1","query":"lang=vi"}
~~~

Verify three facts:

1. Route ID `catalog-live` appears in the runtime list.
2. The backend receives path `/catalog/items/42`, proving `StripPrefix=1` ran.
3. The backend receives `X-Route-Revision: v1` via `revision`, and `instance=A` confirms port 9191.

If the response is still 404 right after refresh, check logs and re-read runtime routes before declaring failure. Never spin in an infinite loop waiting for a new route; deployments need bounded timeouts and clear rollback triggers.

### 6.4. Distinguishing `GET routedefinitions` from `GET routes`

These two endpoints serve different purposes:

| Endpoint | Observes | Meaning |
| --- | --- | --- |
| `GET /actuator/gateway/routedefinitions` | Source route definitions where supported | Reflects what `RouteDefinitionLocator`s provide |
| `GET /actuator/gateway/routes` | Runtime `Route` list | Reflects materialization / the route cache Gateway routes against |
| `GET /actuator/gateway/routes/{id}` | One specific route | JSON format may differ from POST creation payloads |
| `POST /actuator/gateway/refresh` | Requests route cache reload | Does not write or delete any `RouteDefinition` |

A route definition can **already exist in the source** while missing or sitting at an older revision in **runtime**. Conversely, runtime can still hold an old route if the repository updated without a refresh. Comparing these two views is the most direct way to separate source errors from cache errors.

### 6.5. Selective Refresh by Metadata

Gateway WebFlux 4.2/5.0 docs describe selective refreshes using the `metadata` query parameter with `key:value` pairs. In our lab, the route carries metadata `group: lab`:

~~~bash
curl -i -X POST \
  "http://127.0.0.1:9090/actuator/gateway/refresh?metadata=group:lab"
~~~

This refreshes routes matching that metadata rather than rebuilding every route. Still:

- Metadata **selects a route group**; it is **not an access control** or authorization rule.
- Check **your exact version** to confirm filtering syntax, async sequencing, and behavior when metadata itself changes.
- When deleting a route or moving a route between groups, selective refresh may be harder to reason about; a **full refresh** is a safer default for labs.
- When updating multiple interdependent routes simultaneously, enforce revision controls and post-refresh verification.

### 6.6. Switching Target from Backend A to Backend B

With the Actuator route management API documented for Gateway 5.0, **never POST an existing route ID**: the docs warn this can create duplicate route definitions and break route queries. To edit a route via this API, **delete the old definition, create the new definition, and then refresh**.

~~~bash
# 1) Delete the Actuator-managed RouteDefinition
curl -i -X DELETE \
  "http://127.0.0.1:9090/actuator/gateway/routes/catalog-live"

# 2) Recreate with a different URI and revision
curl -i -X POST \
  "http://127.0.0.1:9090/actuator/gateway/routes/catalog-live" \
  -H "Content-Type: application/json" \
  --data-binary '{
    "predicates": ["Path=/api/catalog/**"],
    "filters": [
      "StripPrefix=1",
      "AddRequestHeader=X-Route-Revision,v2"
    ],
    "uri": "http://127.0.0.1:9192",
    "order": 0,
    "metadata": {
      "group": "lab",
      "revision": "v2"
    }
  }'

# 3) Request cache reload
curl -i -X POST \
  "http://127.0.0.1:9090/actuator/gateway/refresh"

# 4) Verify end-to-end
curl -i \
  "http://127.0.0.1:8080/api/catalog/items/42?lang=vi"
~~~

Once refresh completes, requests should reach **backend B** and return `"revision":"v2"`. Successfully switching targets proves Gateway **reloaded the route from its source** rather than merely restarting a backend.

**Warning:** The DELETE → POST sequence is **not an atomic update transaction**. If another refresh runs mid-sequence, the route temporarily disappears; if POST fails, the definition store lacks the route altogether. Thus, this pattern suits an **Actuator lab**, not zero-downtime production rollouts.

In production, use a repository with versioned (or transactional) updates, validate before committing, and then dispatch coordinated refreshes. For changes spanning multiple coupled routes, publish **versioned config snapshots** so traffic never sees a half-old, half-new state.

### 6.7. Deleting the Route and Verifying

~~~bash
curl -i -X DELETE \
  "http://127.0.0.1:9090/actuator/gateway/routes/catalog-live"

curl -i -X POST \
  "http://127.0.0.1:9090/actuator/gateway/refresh"

curl -sS "http://127.0.0.1:9090/actuator/gateway/routes"
curl -i "http://127.0.0.1:8080/api/catalog/items/42"
~~~

Once refresh finishes, assuming no other route/handler matches `/api/catalog/**`, requests should return **404**. If the route still appears in cache, investigate async refresh timing, another definition source, or multiple Gateway replicas.

**Actuator limitation:** Per Gateway 5.0 docs, routes defined directly in `application.yml` or via Java `@Bean` cannot be arbitrarily deleted via `DELETE /actuator/gateway/routes/{id}` like Actuator-created routes; the API may return 404 for those. Do not repeatedly delete and refresh trying to "remove" a YAML-owned route.

## 7. Java: Saving `RouteDefinition` Before Emitting `RefreshRoutesEvent`

Mirroring Actuator actions, an application can run a **trusted route administration** flow using Gateway WebFlux APIs:

~~~text
Authorized route change
   → validate route + destination allowlist
   → RouteDefinitionWriter.save/delete(...)
   → await Mono completion
   → ApplicationEventPublisher.publishEvent(RefreshRoutesEvent)
   → verify runtime Route and business requests
~~~

### 7.1. Two Core Interfaces

~~~java
// Conceptual signatures of the Gateway WebFlux API
public interface RouteDefinitionLocator {
    Flux<RouteDefinition> getRouteDefinitions();
}

public interface RouteDefinitionWriter {
    Mono<Void> save(Mono<RouteDefinition> route);
    Mono<Void> delete(Mono<String> routeId);
}
~~~

`RouteDefinitionRepository` extends both **locator** and **writer**, enabling it both to supply route definitions and to perform saves and deletes. Gateway docs distinguish `InMemoryRouteDefinitionRepository` (process-local state) from `RedisRouteDefinitionRepository` (shareable state). Never equate **storing `RouteDefinition`s centrally** with **auto-refreshing every replica's cache**.

### 7.2. Controlled Update Service Pattern

In the WebFlux Gateway project, create `src/main/java/demo/gateway/routes/RouteMutationService.java`:

~~~java
package demo.gateway.routes;

import java.net.URI;
import java.util.List;
import java.util.Map;

import org.springframework.cloud.gateway.event.RefreshRoutesEvent;
import org.springframework.cloud.gateway.handler.predicate.PredicateDefinition;
import org.springframework.cloud.gateway.filter.FilterDefinition;
import org.springframework.cloud.gateway.route.RouteDefinition;
import org.springframework.cloud.gateway.route.RouteDefinitionWriter;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class RouteMutationService {

    private static final String ROUTE_ID = "catalog-live";

    private final RouteDefinitionWriter writer;
    private final ApplicationEventPublisher publisher;

    public RouteMutationService(RouteDefinitionWriter writer,
            ApplicationEventPublisher publisher) {
        this.writer = writer;
        this.publisher = publisher;
    }

    // Allow only two approved destinations: avoid turning Gateway
    // into an open proxy or SSRF gateway.
    public Mono<Void> setCatalogTarget(String target) {
        URI destination = switch (target) {
            case "A" -> URI.create("http://127.0.0.1:9191");
            case "B" -> URI.create("http://127.0.0.1:9192");
            default -> throw new IllegalArgumentException(
                    "Target must be A or B");
        };

        RouteDefinition definition = new RouteDefinition();
        definition.setId(ROUTE_ID);
        definition.setUri(destination);
        definition.setOrder(0);
        definition.setPredicates(List.of(
                new PredicateDefinition("Path=/api/catalog/**")));
        definition.setFilters(List.of(
                new FilterDefinition("StripPrefix=1"),
                new FilterDefinition(
                        "AddRequestHeader=X-Route-Revision," + target)));
        definition.setMetadata(Map.of(
                "group", "lab",
                "revision", target));

        return writer.save(Mono.just(definition))
                // Publish event ONLY AFTER save completes.
                .then(Mono.fromRunnable(this::requestRefresh));
    }

    public Mono<Void> deleteCatalog() {
        return writer.delete(Mono.just(ROUTE_ID))
                .then(Mono.fromRunnable(this::requestRefresh));
    }

    private void requestRefresh() {
        publisher.publishEvent(new RefreshRoutesEvent(this));
    }
}
~~~

Explanation:

- The service restricts **target to an A/B allowlist**. Never let clients submit free-form URIs like `http://169.254.169.254/...` or arbitrary `http://localhost:...` ports: route mutation rights carry severe SSRF and open-proxy risk.
- `new PredicateDefinition("Path=...")` and `new FilterDefinition("StripPrefix=1")` build definitions using Gateway's shortcut DSL.
- `writer.save(Mono.just(definition))` returns **`Mono<Void>`**: nothing executes until subscribed. `.then(Mono.fromRunnable(...))` ensures the publisher fires **only after persistence succeeds**.
- If save fails, `.then(...)` **does not run**. If backed by a transactional store, wait for **commit** rather than an in-memory buffer.
- `publishEvent(...)` triggers refresh in **the current process**. It does not return a `Future` proving the cache swapped or other replicas completed.
- For repositories supporting **upsert/replace by ID**, `save` can update definitions; those semantics differ from Actuator POST and depend on implementation. Do not assume this pattern works identically across every repository without checking how it handles existing IDs.

**Never call `.subscribe()` loosely inside a service and return HTTP 200 right away.** Return `Mono<Void>` to a trusted reactive caller/workflow so it subscribes at the reactive boundary. A management handler accepting an update may return **202 Accepted** once persistence and event emission succeed, while the controller/orchestrator **verifies async refresh** in a separate step.

### 7.3. Single-Process Repository for the Lab

If you need to guarantee the service in 7.2 has a writable repository, strictly within a **lab profile** you can define a bean:

~~~java
package demo.gateway.routes;

import org.springframework.cloud.gateway.route.InMemoryRouteDefinitionRepository;
import org.springframework.cloud.gateway.route.RouteDefinitionRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("route-lab")
public class RouteLabRepositoryConfiguration {

    @Bean
    RouteDefinitionRepository routeDefinitionRepository() {
        return new InMemoryRouteDefinitionRepository();
    }
}
~~~

Many Gateway releases auto-configure an in-memory repository when no other repository exists, so **adding this bean manually is not required in every project**. When configuring a custom repository, ensure only the intended repository/writer bean is active—avoiding candidate bean conflicts or two sources emitting duplicate route IDs.

The **Actuator** lab in section 6 is enough to learn refresh mechanics, so **you do not need to register both section 7's service and repository simultaneously just to repeat the steps**. Section 7 demonstrates **how to integrate refresh events into an authenticated/authorized Java workflow**; never expose an unprotected public controller just to fire events.

### 7.4. When Using a Remote Config Update System

With PostgreSQL, Redis, or Config Server:

1. Accept change requests from an **authenticated and authorized** management system.
2. Validate route ID, URI scheme, host allowlist, predicate/filter syntax, request paths, and security policies.
3. Persist to the source of truth using a transaction or revision-controlled write.
4. Only after commit, publish the event inside each Gateway process.
5. Monitor refresh outcomes, verify route revisions, and run smoke tests on every replica.
6. Record an audit trail (who changed what, from which revision to which) and maintain rollback capability.

Never place `publishEvent(...)` before transaction commit: listeners may read stale data and re-cache the old state.

## 8. Running Multiple Gateway Replicas: Each Process Has Its Own Cache

Consider this deployment:

~~~mermaid
flowchart TD
    C["Clients"] --> LB["Load Balancer / Ingress"]
    LB --> A["Gateway A<br/>CachingRouteLocator A"]
    LB --> B["Gateway B<br/>CachingRouteLocator B"]
    A --> DB[("Shared RouteDefinitionRepository<br/>Redis / DB")]
    B --> DB
    E["Admin workflow<br/>write revision v2"] --> DB
    E -.->|"separate refresh event/push"| A
    E -.->|"separate refresh event/push"| B
    A --> D1["Backend A / B"]
    B --> D1
~~~

Even when A and B share **one Redis store** holding `RouteDefinition`s, **each Gateway instance holds its own `CachingRouteLocator` in process memory**. Java's `ApplicationEventPublisher` emits events **locally within one JVM**, not over the network to B.

### 8.1. Three Common Scenarios

| Definition Store | Gateway A/B Caches | What Happens When Only A Refreshes? |
| --- | --- | --- |
| Process-local `InMemoryRouteDefinitionRepository` | Separate per process | B never sees definitions written on A; refreshing B won't help since B lacks the data |
| Shared Redis / DB | Separate per process | A loads the new revision while B keeps serving the old revision |
| Shared Config Server or discovery | Separate per process, plus upstream caches | Must ensure both the source and per-replica refresh have picked up the new revision |

**Never confuse a "shared repository" with a "distributed route cache."** A shared repository merely lets nodes **read the same data**; cache invalidation and rebuilds must still be orchestrated and verified per node.

### 8.2. `RedisRouteDefinitionRepository` and Version Namespaces

Spring Cloud Gateway provides `RedisRouteDefinitionRepository` to store routes in Redis rather than RAM alone. Enabling it requires the reactive Redis dependency and matching configuration. On **Gateway Server WebFlux 5.x**, Configuration Properties specifies:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          redis-route-definition-repository:
            enabled: true
~~~

On **Gateway WebFlux 4.x** using the older namespace, docs show:

~~~yaml
spring:
  cloud:
    gateway:
      redis-route-definition-repository:
        enabled: true
~~~

Typical reactive Redis dependency in Spring Boot 3.x:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis-reactive</artifactId>
</dependency>
~~~

**Version note:** Several prose *Sharing Routes* pages in 5.x docs still show the `spring.cloud.gateway.redis-route-definition-repository.enabled` prefix, whereas the 5.x Configuration Properties table lists the `server.webflux` prefix. Whenever docs differ, check **configuration metadata and bean wiring on your exact artifact/release**. Never assume adding a property alone activated the Redis repository.

Using Redis also does not automatically solve cross-route transactions, distributed refreshes, or security policies. Custom DBs or stores may need versioned snapshots and dedicated update APIs.

The full WebFlux 5.x property name in Config Props is `spring.cloud.gateway.server.webflux.redis-route-definition-repository.enabled`; on 4.x lines it is `spring.cloud.gateway.redis-route-definition-repository.enabled`. Verify the active repository bean rather than checking YAML alone.

### 8.3. Cluster-Wide Refresh Broadcast Mechanisms

A common architecture:

1. Admin persists new revision **v2** to the shared store.
2. Post-commit, publish a change message carrying `revision=v2` over a reliable channel (message bus, event stream, controller/orchestrator).
3. Each Gateway replica receives the **authenticated** event, checks the revision, and publishes `new RefreshRoutesEvent(...)` locally.
4. Each replica materializes the new routes and reports **applied/failed** status plus its active revision.
5. The orchestrator marks the rollout succeeded only once the SLA-required replica count hits the revision—or drains failing replicas from traffic.

**Do not assume Spring Cloud Bus or Redis pub/sub is active automatically** just because Spring Cloud Gateway or Redis is on the classpath. You must configure that integration along with delivery retries, at-least-once semantics, and deduplication.

If a Gateway replica loses connectivity to the shared store, refreshes cannot load updated definitions. Decide upfront on **last-known-good retention**, readiness/liveness behavior, alerts, and maximum staleness bounds.

### 8.4. "Instant Update" Does Not Mean Every Cluster Request Sees v2 Simultaneously

During the transition window:

~~~text
10:00:00  Repository committed revision v2
10:00:01  Gateway A caches v2, Gateway B still caches v1
10:00:02  Load balancer may route requests to A or B
10:00:03  Gateway B finally caches v2
~~~

This timeline is illustrative. Any system demanding **strong rollout consistency** needs connection draining/quiescing, snapshot versioning, and coordinated releases; emitting `RefreshRoutesEvent` does not deliver cluster-wide atomicity.

## 9. Asynchrony, Concurrency, and Race Conditions During Refresh

### 9.1. Back-to-Back Refreshes Can Read Different Revisions

Suppose the source updates rapidly:

~~~text
Repository: v1 → v2 → v3
Refresh X starts reading v2, runs slowly
Refresh Y starts reading v3, runs quickly
~~~

If the implementation does not serialize or revision-guard cache swaps, a slow earlier refresh finishing late **risks overwriting** the newer result. Spring Cloud Gateway issues have documented concurrency/race scenarios in certain releases. **Never claim every version is buggy**, yet this illustrates why production must stress-test rapid refreshes on the exact patch level deployed.

Mitigations:

- Enforce **a single config-release workflow** per route group rather than two admins editing concurrently.
- Attach **monotonic revisions** to snapshots and verify versions before and after refresh.
- Coalesce/debounce bursts of refresh signals instead of firing unbounded refreshes.
- Abort rollout if validation or materialization fails; retain last-known-good.
- After refresh, **inspect runtime routes and send probe requests** rather than stopping at HTTP 200.
- If an older result ever overtakes a newer revision, re-sync to the latest snapshot and investigate root cause.

### 9.2. Coupled Route Changes Must Ship as One Configuration Batch

Suppose `payment-public` requires an auth filter while `payment-internal` enforces mTLS. Updating them in two separate writes with a refresh in between can briefly expose **missing protective filters** or unintended route overlaps.

Production should:

1. Validate **the entire snapshot** (unique route IDs, path/method conflicts, priority/`order`, destinations, security filters).
2. Commit the full snapshot or use revision-based compare-and-swap.
3. Refresh replicas in controlled stages.
4. Verify end-to-end access control after refresh.
5. Retain rollback capability to the prior safe snapshot on failure.

**Never let security rest solely on a route filter that a management API can delete.** Authentication and authorization boundaries must also be enforced in the Spring Security `WebFilter` chain and backends.

### 9.3. Failed Refreshes and Stale Routes: What Must You Observe?

Actuator docs state that when an async refresh errors, the existing route cache stays intact. However, "the old cache remains" is only comforting when you know the old cache is safe and have verified actual cluster state.

Record:

- **source revision:** does the store currently hold v2 or v3?
- **applied revision:** which revision is each Gateway replica actually running?
- **refresh result:** success, failure, timeout, or skipped due to matching revision;
- **route count/hash:** do IDs, URIs, predicates, and filters match the expected snapshot?
- **request outcome:** where is client traffic landing, and are security policies holding?

Log only route names, revisions, and sanitized error summaries—**never secrets**, tokens, cookies, raw request bodies, or config credentials.

## 10. Verification Through Controlled Tests

A solid test suite separates **route cache state** from **backend availability**. Using the A/B lab:

| Case | Action | Expected Verification |
| --- | --- | --- |
| T1 | GET before any route exists | 404 assuming no other handler matches |
| T2 | Create `RouteDefinition` to A, **without refresh** | Store may hold v1; do not assume runtime switched |
| T3 | POST refresh, inspect runtime routes | `catalog-live` present, URI 9191, revision v1 |
| T4 | GET `/api/catalog/items/42` | Backend A receives path `/catalog/items/42` |
| T5 | Delete + recreate targeting B, then refresh | Runtime shows URI 9192, revision v2 |
| T6 | GET after T5 | Backend B receives request |
| T7 | Delete route, then refresh | Route gone; unmatched requests normally return 404 |
| T8 | Create route with nonexistent filter | Refresh/materialization reports failure; never silently drop protection |
| T9 | Attempt `DELETE` on an `application.yml` route | Must not be relied on to remove YAML-owned routes |
| T10 | Selective metadata refresh | Trust result only after inspecting the exact runtime group for your release |
| T11 | Two Gateway replicas; refresh only A | A and B can hold different revisions; trigger and verify independently |
| T12 | Slow/failing store during refresh | Verify last-known-good, timeouts, and alerts |

### 10.1. Testing a Route with an Invalid Filter Config

**Deliberately invalid** example:

~~~json
{
  "predicates": ["Path=/api/catalog/**"],
  "filters": ["NoSuchSecurityFilter=required"],
  "uri": "http://127.0.0.1:9191",
  "order": 0
}
~~~

Once saved and materialized by Gateway, the missing filter triggers a failure per that version's mechanics. **Never test this against production**, especially on routes protecting sensitive APIs. The goal is verifying your pipeline rejects bad configs, logs cleanly, and rolls back.

### 10.2. Writing Your Own Integration Test

With `@SpringBootTest`, `WebTestClient`, and a test `RouteDefinitionRepository`:

1. Materialize initial routes so the cache holds v1.
2. Update the source to v2 via `save(...)` and **await completion** (e.g., using `StepVerifier` in tests).
3. Inspect pre-refresh state to establish a baseline.
4. Publish `RefreshRoutesEvent` in the same application context.
5. Wait using a **bounded-timeout** condition while re-reading routes until the expected revision appears.
6. Send HTTP requests via `WebTestClient` and assert target backend and filter effects.
7. Test controlled failure handling when the source emits an invalid definition.

Never use `Thread.sleep(5000)` and assume the test is reliable: refresh latency varies across machines, backends, and JVMs—wait on an **explicit condition** instead. In production code, never call `.block()` on the Reactor Netty event loop to "wait for cache refresh."

### 10.3. Distinguishing the Route Cache from In-Flight Requests

A request that already selected a route before refresh may finish on **the old `Route` object** while new requests take the new route. A single in-flight request does not switch mid-stream, nor should you **kill every in-flight request** just to change a URI.

During rolling changes, plan connection draining and timeouts if the new backend changes API contracts substantially. Test short requests, long-lived streams, and WebSockets if used.

## 11. Security: Route Management APIs Can Be More Dangerous Than Business APIs

Permitting arbitrary route creation can turn Gateway into an:

- **SSRF proxy:** reaching cloud metadata services or restricted private IPs;
- **open proxy:** forwarding Internet traffic to arbitrary external hosts;
- **authorization bypass:** exposing alternate paths that skirt existing policies;
- **filter bypass:** dropping mandatory JWT validation, rate limits, or circuit breakers;
- **header injector:** tampering with `Host`, `Authorization`, `Forwarded`, or security headers;
- **denial-of-service vector:** flooding thousands of heavy routes, broken predicates/filters, or endless refreshes.

Therefore:

1. **Never expose writable `/actuator/gateway/routes*` or `/actuator/gateway/refresh` to the Internet.**
2. Default production Gateway Actuator to **`read-only`** for inspection; enable `unrestricted` only inside an isolated management plane if truly required.
3. Enforce **authentication, role-based authorization, and audit trails** on route management, reinforced by private/loopback networking and mTLS.
4. Validate route destinations against a **hostname/scheme/port allowlist** rather than accepting arbitrary client URIs. Account for DNS rebinding and HTTP redirects if URLs are indirectly controlled.
5. Validate predicate collisions, route `order`, path rewrites, and **mandatory security filters** before saving.
6. Rate-limit and lock refresh operations to prevent abuse or refresh storms.
7. Never store secrets, JWTs, keys, or sensitive internal details inside route metadata readable via Actuator.

**Never build a public HTTP endpoint like `POST /admin/routes/refresh` gated only by a client-supplied `X-Admin: true` header.** If you build a custom management HTTP API, place it in a strictly access-controlled control plane and ensure it is never exposed as a public Gateway route.

### 11.1. Dynamic Routes Can Break Security Assumptions

Suppose Spring Security only requires authentication on `/api/orders/**`; a misgoverned admin API could create `/internal/orders/**` pointing to the same unguarded backend. Whenever updating routes, verify that **WebFilter and downstream security policies** cover every possible public path, not just one route's config.

Verify CORS across public paths and origins too: if a new route alters metadata or URIs, runtime CORS mappings may need rebuilding per version mechanics. Earlier releases saw timing issues between Redis route refreshes and CORS mappings; therefore **test CORS preflights and actual requests** after significant route edits.

### 11.2. Actuator `read-only` vs. `unrestricted`

In the referenced Gateway 4.2/5.0 docs, Actuator supports:

~~~properties
# Inspect routes: recommended production default
management.endpoint.gateway.access=read-only
management.endpoints.web.exposure.include=gateway
~~~

and when writes are genuinely needed in a protected management plane:

~~~properties
# Strictly for labs or tightly locked-down control planes
management.endpoint.gateway.access=unrestricted
management.endpoints.web.exposure.include=gateway
~~~

`read-only` disables creating, deleting, or refreshing routes via Actuator. Verify `management.endpoint.gateway.access` against your Spring Boot version, as older versions configured this differently. An "exposed" endpoint is not automatically **secured**: configure Spring Security and network isolation independently.

## 12. Observing Refreshes in Production

### 12.1. Metrics You Should Collect

Useful indicators (names below are **custom metric suggestions**, not guaranteed built-in Gateway exports):

~~~text
gateway_route_refresh_total{node, outcome="success|failure"}
gateway_route_refresh_duration_seconds{node}
gateway_routes_applied_revision{node}
gateway_routes_count{node}
gateway_route_change_total{operation="save|delete|rollback"}
gateway_route_stale_seconds{node}
gateway_route_probe_success{route_group,node}
~~~

Alongside metrics, record audit events:

~~~text
change-id:       change-128
requested-by:    authenticated admin principal
source-revision: v21
target-revision: v22
changed-routes:  catalog-live
validation:      PASS
node-A:          applied v22
node-B:          applied v22
smoke-test:      PASS
rollback:        not-needed
~~~

Never put full URIs with credentials, access tokens, cookies, per-user request IDs, or payloads into metric labels—that causes **high cardinality** and data leaks.

### 12.2. Logging Configuration During Investigation

Gateway docs suggest logger:

~~~yaml
logging:
  level:
    org.springframework.cloud.gateway: DEBUG
~~~

Enable `DEBUG`/`TRACE` only temporarily for targeted environments or routes. If enabling Netty wiretap, exercise extreme caution because it can dump sensitive headers and bodies into logs. Never log raw JWTs or session cookies while debugging refreshes.

### 12.3. Questions to Ask When Seeing an Old Route Revision

1. **What revision is the route source on?** Inspect the repository or Config Server directly via secured admin tools.
2. **Did the event fire in this process?** Check event/change-ID logs.
3. **Did any predicate/filter or URI fail binding?** Inspect route materialization error logs.
4. **Did this process's runtime routes update?** Inspect Actuator and route counts/hashes.
5. **Which replica handled the live request?** Bypass the load balancer or inspect replica-identifying headers in test environments.
6. **Is another route taking higher precedence?** Check route `order` and predicate overlaps.
7. **Does the URI use `lb://`?** Inspect discovery and LoadBalancer caches separately.
8. **Is a CDN or client cache returning a stale response?** Check response headers and backend traces.

## 13. Troubleshooting Table

| Symptom | Possible Cause | Check / Resolution |
| --- | --- | --- |
| `POST /actuator/gateway/refresh` returns 404 | Gateway Actuator disabled/unexposed, wrong port or context path | Verify Actuator starter, management port, and exposure/access config |
| Refresh returns 403/405 | Endpoint is `read-only`, or blocked by Security/firewall | Do not open writes blindly; use an authorized management plane |
| POST route returns 201 yet business request gets 404 | Cache not refreshed, refresh still pending, or wrong predicate | POST refresh, inspect runtime routes, test with bounded timeout |
| `GET routedefinitions` shows v2, `GET routes` still v1 | Source updated, but runtime/cache failed to reload | Check refresh events/error logs and route materialization |
| Runtime route shows v2 yet traffic still hits backend A | Another route wins, request hit an unrefreshed replica, or upstream/cache issue | Check route `order`, replica ID, revision header, and backend logs |
| Deleting route via Actuator returns 404 | Route is owned by `application.yml`/Java bean, not Actuator | Edit the owning config source; stop forcing Actuator deletes |
| Refresh errors on unknown `GatewayFilterFactory` | Route definition has invalid filter name or args | Validate routes completely before commit |
| Old route keeps working after refresh | Async refresh, stale source, or cache retained last-known-good | Verify source revision, refresh result, and runtime on each node |
| Node A has v2, B still has v1 | Event only fired in process A | Trigger/orchestrate refresh separately on B |
| New `lb://...` URI returns 503 | Discovery finds no healthy instances | Check service ID/registry/LoadBalancer; don't confuse with route cache |
| Requests return 401/403 after route change | Different security policy or new path uncovered | Inspect WebFilter authorization, token/scopes, and public paths |
| CORS `OPTIONS` returns 404 or old policy | Method predicate excludes `OPTIONS`, or stale CORS mapping | Inspect global CORS, origins/methods, and version-specific refresh behavior |
| Cache reverts revision after rapid consecutive refreshes | Race/stale snapshot or implementation issue | Serialize updates, check patch release, snapshot revisions, and roll back |
| Latency spikes during refresh | Heavy route materialization or contention | Measure duration/CPU, debounce refreshes, and cap route counts |

## 14. Dynamic Route Rollout Checklist

- [ ] Established a clear **source of truth** for route definitions; avoid uncoordinated concurrent edits across sources.
- [ ] Clearly distinguished `RouteDefinitionRepository`, `RouteDefinitionRouteLocator`, and `CachingRouteLocator`.
- [ ] Completed/committed `RouteDefinitionWriter.save/delete` **before** publishing `RefreshRoutesEvent`.
- [ ] Never treated `publishEvent` returning or HTTP 200 refresh as proof runtime routes updated.
- [ ] Verified **route ID, URI, predicates, filters, order, metadata, and revision** after refresh.
- [ ] Ran smoke tests with real business requests verifying target backend and actual path/headers.
- [ ] Prevented duplicate route IDs or unintended path/`order` collisions.
- [ ] Rejected invalid configs; maintained last-known-good, audit trails, and rollback.
- [ ] Bounded concurrent refreshes and enforced revision checks to mitigate race conditions.
- [ ] For multi-replica Gateways, verified **every node's cache**; shared DB/Redis never broadcasts events automatically.
- [ ] Kept the route cache distinct from discovery, LoadBalancer, DNS, and HTTP response caches.
- [ ] Never exposed writable Gateway Actuator to the Internet; defaulted production to `read-only` or a private management plane.
- [ ] Validated all destination URIs against allowlists/schemes to prevent SSRF and open proxying.
- [ ] Verified Security WebFilters, rate limiters, retries, circuit breakers, TLS, and CORS remain intact post-update.
- [ ] Instrumented metrics for refresh failures, applied revisions, staleness duration, route counts, and probe results.
- [ ] Tested rapid refreshes, failed rebuilds, route deletion, multi-node drift, and slow repositories.

## 15. Self-Check Questions

**1. Why can a repository hold v2 while Gateway still routes to backend v1?**

Because `CachingRouteLocator` may still hold the runtime route set compiled from v1. You must request a refresh and confirm runtime routes picked up v2.

**2. Does calling `publishEvent(new RefreshRoutesEvent(this))` modify a route inside the repository?**

No. The event only asks relevant listeners to reload; the `RouteDefinition` source must already have been saved or deleted separately.

**3. When `POST /actuator/gateway/refresh` returns HTTP 200, is Gateway B guaranteed to have updated?**

No. Events and caches are process-local; Gateway B may be another JVM that never received the refresh trigger, even when sharing a Redis repository.

**4. Can Actuator DELETE remove arbitrary routes declared in `application.yml`?**

No. That API manages Actuator-created routes; routes owned by YAML or Java beans cannot be removed through that endpoint by default.

**5. A new route `lb://orders-service` returns 503. Is that always caused by forgetting to refresh routes?**

No. The route itself may be active while discovery/LoadBalancer finds no healthy `orders-service` instances. Analyze those two cache layers separately.

**6. Why must route updates verify security and CORS beyond getting a backend 200?**

Because a new route can bypass path-based security rules, alter filters, or change CORS metadata. A backend returning 200 does not prove unauthorized callers are properly blocked.

**7. Why must you wait for `save(Mono<RouteDefinition>)` to complete before emitting the event?**

Because if the event runs before persistence/commit finishes, listeners can read old definitions and re-cache the stale route set.

## 16. Official References for Verification

1. [Spring Cloud Gateway Server WebFlux 5.0 — Actuator API](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/actuator-api.html): route cache refresh, managing route definitions, HTTP statuses, and metadata options.
2. [Gateway Server WebFlux 4.2 — Actuator API](https://docs.spring.io/spring-cloud-gateway/reference/4.2/spring-cloud-gateway/actuator-api.html): management operations and refresh on the 4.2 line.
3. [Gateway Server WebFlux 5.0 — Configuration](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/configuration.html): `RouteDefinitionLocator` and route definition sources.
4. [Gateway Server WebFlux 5.0 — Configuration Properties](https://docs.spring.io/spring-cloud-gateway/reference/5.0/configprops.html): `spring.cloud.gateway.server.webflux.routes` namespace and Redis route definition repository.
5. [Gateway — Sharing Routes between Multiple Instances](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/sharing-routes.html): in-memory vs. Redis repositories; verify property prefixes against your release's Config Props table.
6. [Spring Cloud Gateway — Configuration Reference](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/configuration.html): overview of routes, predicate/filter configs, and sources.
7. [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): exposure, access levels, and securing management endpoints.
8. [Spring Framework — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events): `ApplicationEventPublisher` and listener mechanics.

**Key takeaway:** **`RefreshRoutesEvent` tells Gateway WebFlux to reload its route cache—it neither persists `RouteDefinition`s nor synchronizes multiple replicas automatically.** To update routes safely, follow **write config source → request refresh → verify runtime routes and live requests**, backed by revisions, validation, admin permissions, and rollback. An HTTP 200 from `/actuator/gateway/refresh` is merely one step in that workflow, never a guarantee that the entire cluster is routing on the new config.
