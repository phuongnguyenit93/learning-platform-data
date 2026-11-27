# Sharing Routes and Synchronizing Refreshes Across Multiple Replicas

## 1. The Problem: Route Edited on Gateway A, Yet Requests Still Hit the Old Route on Gateway B

A production API Gateway rarely runs as a single process. Suppose **Spring Cloud Gateway** is deployed as three replicas behind a load balancer:

- `gateway-a`: handles part of client requests.
- `gateway-b`: handles another share of requests.
- `gateway-c`: handles the remaining share.

All three must enforce identical routing rules—for instance forwarding `/api/orders/**` to `lb://ORDER-SERVICE` while executing route predicates, filter chains, path/header rewrites, service discovery, authentication, rate limiting, retries, circuit breakers, and TLS per policy.

Operations updates `/api/orders/**` from config revision **v41** to **v42** and calls the route-edit API on `gateway-a`. If only A receives the update, the system behaves erratically:

~~~text
Client -> External Load Balancer
  request #1 -> gateway-a -> route v42 -> new backend
  request #2 -> gateway-b -> route v41 -> old backend
  request #3 -> gateway-c -> route v41 -> old backend
  request #4 -> gateway-a -> route v42 -> new backend
~~~

The symptoms include intermittent `404`s, inconsistent header mutations, diverging auth/rate-limit policies across replicas, or requests reaching the wrong microservice. **You cannot fix this simply by firing one refresh call through the load balancer**, because that call only reaches a single instance.

This lesson belongs to the **Dynamic Routes** chapter in the **SPRING_CLOUD_GATEWAY** module. It focuses on **sharing route definitions** and **synchronizing change activation across multiple replicas**, rather than editing YAML on a single machine.

After this lesson, you will be able to:

1. Distinguish a shared route definition store from each replica's **local route cache**.
2. Choose between `RouteDefinitionRepository`, Redis, and external config sources for clustered deployments.
3. Understand that `RefreshRoutesEvent` and `POST /actuator/gateway/refresh` **affect only the JVM/instance receiving the event or command**.
4. Design a control plane featuring **revisions, change notifications, reconciliation on missed events, and per-replica applied confirmations**.
5. Test adding, updating, and deleting routes across 2–3 Gateway replicas, detect config drift, and execute rollbacks.
6. Protect management endpoints, Redis, route URIs, and filter configurations against unauthorized edits.

> **Scope:** Spring Cloud Gateway **Server WebFlux** and its route definition/Actuator APIs. Examples highlight namespace differences between WebFlux 4.x and newer releases using `spring.cloud.gateway.server.webflux`. Gateway Server MVC and other Spring Cloud versions may behave differently. Always verify against the docs for your running release before applying properties—especially for the Redis repository and Actuator access settings.

## 2. Three Layers to Distinguish: Source of Truth, Cache, and Refresh Signals

A dynamic routing system has at least three data layers:

| Layer | Question It Answers | Examples | Auto-Syncs Across Replicas? |
| --- | --- | --- | --- |
| **Shared route definitions** | *Which routes are desired?* | Redis, DB, Config Server/Git | Data is shared when all replicas read the same source |
| **Effective route cache per JVM** | *Which routes is this replica currently using?* | `CachingRouteLocator` | **No**, each JVM keeps independent state |
| **Refresh / change notification** | *When should a replica reload?* | `RefreshRoutesEvent`, Actuator, message bus | In-JVM events do **not** propagate to other JVMs automatically |

In Spring Cloud Gateway, `RouteDefinition` is the route description (ID, URI, predicates, filters, order, metadata). An effective `Route` is the result of compiling those descriptions into executable conditions and filters. A replica may **be able to read the new definition in Redis** yet keep serving from its **stale route cache** until that instance's own refresh executes.

This is the core distinction:

- **Shared store** ensures **nodes look at the same data source**.
- **Local refresh** ensures **a single node loads the new configuration**.
- **Cluster propagation and convergence checks** ensure **the entire cluster actually converged on the same revision**.

A shared Redis store alone is **insufficient** to guarantee every replica immediately serves the same effective routes; conversely, refresh commands alone are **insufficient** if each replica reads from a different source.

### 2.1. Target Architecture Diagram

~~~mermaid
flowchart TD
    OP["Admin / CI-CD / Route Control Plane"] -->|"Validate and commit revision v42"| S[("Shared Route Repository<br/>Redis / DB")]
    OP -->|"Publish route-changed revision v42"| BUS["Event Bus / Pub/Sub"]
    BUS --> A["Gateway A<br/>local refresh"]
    BUS --> B["Gateway B<br/>local refresh"]
    BUS --> C["Gateway C<br/>local refresh"]
    S -->|"Read route definitions"| A
    S -->|"Read route definitions"| B
    S -->|"Read route definitions"| C
    A --> ACK["Convergence monitor / ACK"]
    B --> ACK
    C --> ACK
    LB["Client Load Balancer"] --> A
    LB --> B
    LB --> C
    A --> U["Upstream microservices"]
    B --> U
    C --> U
~~~

**Events should only announce that a new revision exists**, without needing to carry full route objects or credentials. Replicas reload definitions from the source of truth, validate them, refresh their caches, and then report applied status. When events arrive late, duplicate, or get dropped, a reconciliation loop brings lagging replicas back to the current revision.

## 3. Spring Cloud Gateway Abstractions

| Component | Role | Key Takeaway |
| --- | --- | --- |
| `RouteDefinition` | Data-level route description | ID, URI, predicates, filters, order, metadata |
| `RouteDefinitionLocator` | Reads a list of `RouteDefinition`s | Can read from YAML, discovery, or a repository |
| `RouteDefinitionWriter` | Saves/deletes definitions via reactive API | Does not automatically reload the cache |
| `RouteDefinitionRepository` | Combines definition reading and writing | Can be in-memory or shared Redis |
| `RouteDefinitionRouteLocator` | Compiles definitions into executable routes | Requires compatible predicate/filter factories |
| `CachingRouteLocator` | Caches built runtime routes | Every Gateway replica keeps its own state |
| `RefreshRoutesEvent` | Signal to refresh routes inside the app | **JVM-local** Spring application event |
| `/actuator/gateway/refresh` | Endpoint to refresh the route cache | Applies only to **the instance receiving POST** |
| `DiscoveryClient` / LoadBalancer | Finds/picks upstream instances for `lb://` | **Separate** from sharing Gateway route definitions |

A `RouteDefinitionRepository` supports reading and writing at the abstraction level:

~~~java
// Illustrative signatures of Gateway abstractions:
public interface RouteDefinitionRepository
        extends RouteDefinitionLocator, RouteDefinitionWriter {
}

// Read:
Flux<RouteDefinition> getRouteDefinitions();

// Write or delete via the writer's reactive API:
Mono<Void> save(Mono<RouteDefinition> route);
Mono<Void> delete(Mono<String> routeId);
~~~

The snippet above illustrates **interface contracts**, not a standalone Java file to paste into an app: read/write methods belong to their respective interfaces. When implementing, use the exact types and APIs supplied by your project's Spring Cloud Gateway version.

### 3.1. Route Definition vs. Upstream Instance URLs

Route:

~~~yaml
id: orders-api
uri: lb://ORDER-SERVICE
predicates:
  - Path=/api/orders/**
filters:
  - StripPrefix=1
~~~

This is a **route definition**, governing how Gateway accepts requests. `ORDER-SERVICE` is a **logical service ID**; individual `order-service` instances have their own hosts/ports managed by `DiscoveryClient` and Spring Cloud LoadBalancer.

Updating the pod list of `order-service` normally requires no changes to the `lb://ORDER-SERVICE` route. Conversely, changing `Path=/api/orders/**` or `RewritePath` modifies **the Gateway route definition** and requires a route refresh.

## 4. Why `InMemoryRouteDefinitionRepository` Does Not Share Routes

Each Gateway replica maintains its own memory, `ApplicationContext`, and route cache:

~~~text
gateway-a (JVM #1)                gateway-b (JVM #2)
  InMemoryRouteDefinitionRepo       InMemoryRouteDefinitionRepo
  route ID = orders-v42             route ID = orders-v41
  cache = orders-v42                cache = orders-v41
~~~

Sending `POST /actuator/gateway/routes/orders-api` to A stores the route in **A's** repository. If the backing repository is in-memory, B cannot read that record even if you invoke `POST /actuator/gateway/refresh` on B.

This cannot be solved by tweaking load-balancing strategies across Gateway replicas. A load balancer only picks which node receives a request; **it does not replicate in-memory state**.

### 4.1. Do `application.yml` Routes Belong to the Dynamic Repository?

Do not treat routes declared in `application.yml` as freely editable/deletable via Actuator. Gateway normally uses a separate `PropertiesRouteDefinitionLocator`, while Actuator writes/deletes through the active `RouteDefinitionWriter`/repository.

Actuator documentation notes that routes defined in application configuration (or via `@Bean`) **cannot be deleted through the dynamic route management endpoint like Actuator-created routes**. If a static route and dynamic route share an ID or have unclear predicate precedence, requests can hit an unintended route.

Recommendations:

- Define clear **ownership per route ID**.
- Reserve a naming prefix/namespace for dynamic routes, such as `dyn-catalog-api`.
- Avoid duplicate IDs across YAML, Java DSL, `DiscoveryClient` locator, and Redis.
- Never use Actuator POST trying to overwrite static routes defined in code.
- Test route `order` whenever one URL can match multiple predicates.

## 5. Using `RedisRouteDefinitionRepository` for a Cluster

Spring Cloud Gateway documentation covers two `RouteDefinitionRepository` implementations: **`InMemoryRouteDefinitionRepository`** and **`RedisRouteDefinitionRepository`**. Across multiple Gateway replicas, Redis serves as a shared store for dynamic definitions. <https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/sharing-routes.html>

### 5.1. Dependencies and Infrastructure

A Gateway Server WebFlux project using the Redis repository needs:

- The Gateway Server WebFlux starter matching your Spring Boot/Spring Cloud release train.
- `spring-boot-starter-data-redis-reactive` for reactive Redis connectivity.
- A Redis endpoint reachable from **every Gateway replica**.
- Redis security: auth/ACLs, TLS if policy requires, and network isolation.
- Persistence, backup/restore, HA/failover, and key/schema governance.
- A notification and refresh synchronization mechanism across replicas (designed in sections 8–10).

**Do not confuse the Redis repository with `RedisRateLimiter`.** Both can use Redis, yet they store different data and solve different problems. Enabling `RedisRateLimiter` does not automatically store Gateway routes in Redis.

### 5.2. New WebFlux Configuration Namespace

Example for **Server WebFlux** using the `spring.cloud.gateway.server.webflux` property namespace published in newer branches:

~~~yaml
spring:
  data:
    redis:
      host: redis.internal.example
      port: 6379
  cloud:
    gateway:
      server:
        webflux:
          redis-route-definition-repository:
            enabled: true
~~~

If Redis requires TLS, passwords, sentinel/cluster mode, or custom auth, configure Spring Data Redis per your Spring Boot version and deployment environment. The snippet above illustrates only a sample endpoint—**not a complete production config**.

### 5.3. Common Namespace in WebFlux 4.x

Earlier versions and docs placed the property at:

~~~yaml
spring:
  cloud:
    gateway:
      redis-route-definition-repository:
        enabled: true
~~~

**These are version-specific alternatives, not two blocks to paste together.** Notably, the *Sharing Routes* guide and the configuration properties table in some releases display different prefixes; always inspect **the effective configuration of the exact JAR deployed**, not just a version number from a blog post.

Never claim "configuring the Redis repository makes the cluster auto-refresh." Redis is a shared data source, **not a guarantee that all JVMs updated their local route caches**.

### 5.4. Same Source Does Not Guarantee Same Effective Configuration

Suppose A, B, and C read the same Redis, yet:

- A refreshed to revision 42.
- B has not refreshed and still uses cached revision 41.
- C attempted to refresh but lacks a `CustomGatewayFilterFactory` present only in a newer binary, failing to build route 42.

Despite **sharing the same store**, the three replicas have not converged. Monitor per-node apply results and binary/feature-flag versions—never stop at checking whether Redis holds a record.

## 6. Actuator API: CRUD and Refresh Affect Only the Receiving Node

### 6.1. Relevant Endpoints

Spring Cloud Gateway exposes `/actuator/gateway`, with version-dependent APIs including:

| API | Meaning |
| --- | --- |
| `GET /actuator/gateway/routes` | Inspect routes currently built/exposed by Gateway |
| `GET /actuator/gateway/routedefinitions` | Inspect route definitions readable by Gateway |
| `GET /actuator/gateway/routes/{id}` | Inspect a specific route |
| `POST /actuator/gateway/routes/{id}` | Create a route via this instance's writer/repository |
| `DELETE /actuator/gateway/routes/{id}` | Delete a writer-managed route |
| `POST /actuator/gateway/refresh` | Trigger a route cache refresh **on this instance** |

**Write access is restricted by default** in recent releases. When only observation is needed:

~~~yaml
management:
  endpoint:
    gateway:
      access: read-only
  endpoints:
    web:
      exposure:
        include: health,info,gateway
~~~

`read-only` prevents mutating routes over HTTP management endpoints, though it does **not** replace securing Actuator via auth and network policies. Never expose route lists, internal URIs, or sensitive metadata to the public Internet.

When Actuator-based management is needed in a test environment or secured control plane, newer versions use:

~~~yaml
management:
  endpoint:
    gateway:
      access: unrestricted
  endpoints:
    web:
      exposure:
        include: health,info,gateway
~~~

**Warning:** `unrestricted` opens a highly sensitive routing control surface. Enable it only on an isolated management network behind strong authentication, TLS/mTLS, RBAC, auditing, and restricted network ingress—or better yet, build a dedicated control plane. Verify exact property names and exposure behavior against your Spring Boot/Actuator version. Never set `unrestricted` just to "test curl from the Internet."

### 6.2. Creating a Demo Route via Management API

Assume write access is enabled in staging and both `gateway-a` and `gateway-b` read the shared Redis repository. Set **test environment** variables:

~~~bash
# Example run in a shell with management network access.
export ADMIN_A="https://gateway-a-admin.internal.example"
export ADMIN_B="https://gateway-b-admin.internal.example"
# ADMIN_TOKEN is securely provisioned by infrastructure. Never store real tokens in docs.
~~~

Create the route via A:

~~~bash
curl -i -X POST "$ADMIN_A/actuator/gateway/routes/dyn-orders-api" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{
    "uri": "lb://ORDER-SERVICE",
    "predicates": ["Path=/api/orders/**"],
    "filters": ["StripPrefix=1"],
    "order": 0
  }'
~~~

Notes:

1. The JSON uses **shortcut DSL strings** in `predicates` and `filters`, matching Actuator's Create Route docs. GET route responses have a different presentation format—**never take a GET response and POST it back verbatim**.
2. `lb://` requires `spring-cloud-starter-loadbalancer` and a `ServiceInstance` source; saving a route does not verify the upstream exists.
3. With a Redis-backed writer, the record appears in the shared repository; if A's writer is still in-memory or the app has conflicting writers, this writes **no shared state**. Verify the active repository implementation.
4. This API is for learning and inspection. Production changes should flow through a validated, audited, versioned control plane.

**Never blindly re-POST the same route ID.** Recent Actuator docs warn that POSTing to an existing route ID can cause duplicate definitions and internal errors in certain cases. Updating via Actuator may require **delete then recreate**, which creates a brief missing-route window; production needs proper versioned/atomic publishing.

### 6.3. Refreshing A Does Not Refresh B

Run:

~~~bash
curl -i -X POST \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$ADMIN_A/actuator/gateway/refresh"
~~~

Then inspect A:

~~~bash
curl -sS \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$ADMIN_A/actuator/gateway/routes"
~~~

At this point there is **zero proof B is serving the new route**. B likely still holds the old cache. To test manually:

~~~bash
curl -i -X POST \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$ADMIN_B/actuator/gateway/refresh"

curl -sS \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$ADMIN_B/actuator/gateway/routes"
~~~

**Never send two refresh calls to a single load-balanced public URL** assuming you hit both A and B. Both requests might hit A. Targeting individual replicas requires **per-node/per-pod management endpoints** or an in-process agent/event consumer.

### 6.4. HTTP 200 from Refresh Does Not Certify Cluster Convergence

Actuator can return HTTP 200 for a route-cache refresh; in supported versions, the actual refresh can run asynchronously. Therefore:

- `200` only states **the command was accepted/handled per the endpoint contract**, not that all cluster requests now run v42.
- Inspect `GET /actuator/gateway/routes` on **every replica** and/or query an internal health/revision endpoint.
- When changing multiple routes, verify **every** required route built cleanly, not just a single ID.
- Requests already in progress prior to refresh may finish on the previously selected route and filters; refresh is not a transaction over in-flight HTTP requests.

In recent versions, Actuator also supports refreshing by route **metadata**; that is a local optimization, not a replacement for cluster-wide propagation, and should not be used without verifying version-specific invalidation semantics.

## 7. `RefreshRoutesEvent`: A Spring Signal Inside a Single JVM

One way to trigger a local refresh in code is emitting `RefreshRoutesEvent`:

~~~java
package example.gateway.control;

import org.springframework.cloud.gateway.event.RefreshRoutesEvent;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
public class LocalRouteRefresh {
    private final ApplicationEventPublisher publisher;

    public LocalRouteRefresh(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    // Called after the control plane signals a new revision.
    public void requestRefresh() {
        publisher.publishEvent(new RefreshRoutesEvent(this));
    }
}
~~~

This is a **minimal hook**, not a complete cluster synchronization solution. `ApplicationEventPublisher` emits events inside the `ApplicationContext` of **only the running process**. It does **not** send messages to A, B, or C.

To notify every replica, implement one of:

- **Bus / pub-sub** (Redis Pub/Sub, Kafka, RabbitMQ, or a managed event bus).
- **Node agent** receiving notifications over a secured channel and invoking local refresh.
- **Control plane** calling each replica's management API directly (when infrastructure allows and node membership is tracked accurately).
- **Periodic reconciliation / polling** reading the latest revision from the store and refreshing on mismatch.

If using Spring Cloud Bus or Spring Cloud Config, verify which event **actually** triggers route cache refreshes in your version. **Never equate Spring Cloud Context's `/actuator/refresh` with `/actuator/gateway/refresh` or `RefreshRoutesEvent`**: they have distinct contracts and scopes.

## 8. Multi-Replica Synchronization Architecture via Revisions + Bus + Reconciliation

A production design usually separates the **control plane** (route governance) from the **data plane** (Gateways serving live traffic).

### 8.1. Recommended Update Flow

~~~mermaid
sequenceDiagram
    autonumber
    participant Admin as Admin / CI
    participant CP as Route Control Plane
    participant DB as Shared Redis / DB
    participant Bus as Change Bus
    participant A as Gateway A
    participant B as Gateway B
    participant C as Gateway C
    Admin->>CP: Propose route revision v42
    CP->>CP: Validate, authorization, compare revision
    CP->>DB: Commit definition v42
    DB-->>CP: Persisted
    CP->>Bus: routes.changed(v42)
    Bus-->>A: Signal v42
    Bus-->>B: Signal v42
    Bus-->>C: Signal v42
    A->>DB: Reload definitions v42
    B->>DB: Reload definitions v42
    C->>DB: Reload definitions v42
    A-->>CP: Applied / failed v42
    B-->>CP: Applied / failed v42
    C-->>CP: Applied / failed v42
    CP-->>Admin: Convergence status, not just write success
~~~

The ACKs in the diagram are **application-designed control-plane features**, not something `RefreshRoutesEvent` sends back automatically.

Detailed steps:

1. **Authenticate the actor:** RBAC, approvals, auditing, change reason.
2. **Validate the candidate:** unique IDs, allowed URIs/schemes, valid predicates/filters, preserves security routes, no SSRF.
3. **Write to shared store:** monotonically increasing version/revision with lost-update protection.
4. **Only post-commit**, emit a `routes.changed` message carrying the revision or snapshot identifier.
5. **Each replica receives the signal** and compares against its currently applied revision.
6. **Local reload:** fire `RefreshRoutesEvent` or local refresh API so Gateway rebuilds effective routes from the shared locator.
7. **Verify:** inspect route snapshot/IDs/order/metadata and run a probe request or health check.
8. **ACK:** report applied revision and outcome per replica.
9. **Convergence monitor:** alert if any replica lags, stays unrefreshed, or fails; consider draining stale nodes from traffic.
10. **Periodic reconcile:** replicas poll the latest revision periodically to recover from dropped bus messages or late pod startups.

### 8.2. Notification Payloads Should Be Small and Immutable

Example notification from a control plane:

~~~json
{
  "eventType": "routes.changed",
  "revision": 42,
  "source": "gateway-routing",
  "changeId": "chg-2026-042",
  "publishedAt": "2026-11-24T05:00:00Z"
}
~~~

This is a **custom application format**, not a built-in Spring Cloud Gateway JSON event. Never put client secrets, full `Authorization` headers, raw cookies, or TLS key material inside events.

**Messages do not even need to carry full route definitions.** Each node can fetch the latest revision from the shared store, which also cleanly handles out-of-order events:

~~~text
Node is currently running v40.
Message v42 arrives before v41.
Node checks shared latest revision = v42.
Node applies v42.
Message v41 arrives late -> ignore or simply reconcile v42.
~~~

Never blindly apply a raw payload from a delayed v41 event arriving after v42 and accidentally roll back config.

### 8.3. Why Pub/Sub Alone Is Not Enough

Standard Redis Pub/Sub provides no durable queuing for offline subscribers. If `gateway-c` briefly disconnects when v42 is broadcast, it **misses the message**.

Therefore:

- On startup, nodes must **read the latest shared revision** and verify effective routes.
- After reconnecting to the bus, nodes must **reconcile** instead of waiting passively for the next event.
- Add low-frequency polling (e.g., every tens of seconds matching SLAs and store capacity) or use a durable message bus.
- Make consumers **idempotent**: receiving v42 two or three times remains safe.
- If a node fails to load v42, **report failure and retry with bounds**—never emit a fake v42 ACK.

**Sharing Redis route definitions is only part of the architecture**; revisions, ACKs, and reconciliation must be explicitly built if your organization requires reliable convergence.

### 8.4. Distinguishing Write ACK, Event ACK, and Applied ACK

| Signal | What It Proves | What It Does NOT Prove |
| --- | --- | --- |
| Shared repository save succeeded | Route definition persisted in store per contract | Nodes have read it |
| Event bus accepted message | Notification accepted/persisted per bus semantics | Each node refreshed |
| Node received message | Subscriber learned a new revision exists | Routes compiled cleanly |
| Local refresh triggered | Node was instructed to refresh | New effective routes are live |
| Node reports **applied revision** post-validation | Node verified route snapshot/behavior per policy | Prior in-flight requests have finished |
| Convergence monitor sees A/B/C at v42 | Cluster converged per verification criteria | Every downstream business request will succeed |

This breakdown explains why "Redis holds the new record" or "refresh returned HTTP 200" is **insufficient** for safe rollouts.

## 9. Integrating Local Refresh on Message Arrival

Below is the **internal per-node adapter** inside each Gateway. It assumes a trusted Kafka/Redis/HTTP subscriber invokes `onRouteChangeMessage` after verifying message authenticity.

~~~java
package example.gateway.control;

import org.springframework.cloud.gateway.event.RefreshRoutesEvent;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
public final class ClusterRouteChangeHandler {
    private final ApplicationEventPublisher publisher;

    public ClusterRouteChangeHandler(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    // Hook invoked by the bus consumer in this process.
    // Never invoke directly from public clients.
    public void onRouteChangeMessage(long revision) {
        // Demo version: publish local event. Production needs:
        // - compare revision against latest shared store;
        // - ignore stale/duplicate events;
        // - track refresh completion and validate effective routes;
        // - report ACK or failure; retry/reconcile when needed.
        publisher.publishEvent(new RefreshRoutesEvent(this));
    }
}
~~~

**What this snippet does NOT yet do**:

- Does not define the Redis/Kafka subscriber, TLS/auth, or message parsing.
- Does not compare revisions or guard against v42 arriving before v41.
- Does not await/confirm asynchronous refresh completion.
- Does not emit metrics/ACKs or retry on Redis failures.
- Does not validate against invalid route definitions.

This is only **the bridge between a cluster signal and a local Spring event**, not a turnkey "cluster synchronization" product. Production needs all the items above plus integration tests.

### 9.1. Do Not Block the Event Loop While Reading the Repository

Gateway Server WebFlux runs on a reactive model. Blocking JDBC, blocking network I/O, or `Thread.sleep()` inside Gateway filters or event-loop threads will stall requests.

When building a custom repository:

- When reactive drivers exist, use `Flux`/`Mono` with proper backpressure.
- If a blocking client is unavoidable, isolate it on a bounded scheduler and control concurrency.
- Never call `.block()` inside a `GlobalFilter` or Netty request-handling thread.
- Never fire unsupervised `.subscribe()` chains pretending publish/refresh has completed.
- Ensure repository errors are observed rather than silently leaving the route cache broken.

## 10. Atomicity When Updating Multiple Routes

A real change often requires updating **multiple routes together**:

~~~text
v41:
  /api/catalog/**  -> lb://CATALOG-V1
  /api/orders/**   -> lb://ORDER-V1

v42:
  /api/catalog/**  -> lb://CATALOG-V2
  /api/orders/**   -> lb://ORDER-V2
~~~

If the control plane saves the catalog route first and orders second, a node refreshing mid-way sees:

~~~text
catalog = V2
orders  = V1
~~~

That is a **mixed-version snapshot**. A repository offering route-by-route CRUD **does not guarantee atomic updates across an entire route set**.

Design patterns:

1. **Versioned snapshots:** write a full definition set under revision v42, validate completeness, and atomically flip an active-revision pointer from v41 to v42.
2. **Stage → validate → activate:** stage definitions in an inactive namespace; let nodes switch only after tests pass.
3. **Transactional DB / outbox:** commit definitions + an outbox record in one transaction (where supported) before emitting the event, avoiding commits without notifications.
4. **Control route order/precedence:** ensure staged routes never match live traffic before activation.
5. **Revision-based rollback:** revert cleanly to known-good snapshot v41 instead of manually patching individual routes.

These are **additional architectural patterns**. Basic `RedisRouteDefinitionRepository` **does not provide multi-route snapshot transactions or version switching out of the box**; atomic rollouts require building that into your control plane/repository or controlling deployment pipelines.

### 10.1. Races Between Multiple Admins

When two admins edit routes simultaneously:

~~~text
Admin A reads v41 -> wants v42: change catalog
Admin B reads v41 -> wants v42: change orders
Admin A writes catalog route
Admin B writes full old snapshot + orders -> catalog change is lost
~~~

Enforce **optimistic concurrency** (revision/ETag/compare-and-set) or transactional locking. When the base revision mismatches the latest, reject with conflict and require rebase/review—never use "last write wins" for routing or security without an explicit policy.

### 10.2. In-Flight Requests Matched Before Refresh

A request that matched an old route before v42 activated may finish on the old route—that is normal in-flight behavior. Therefore:

- Never rely on route refresh to abort already-started requests instantly.
- For emergency access termination, enforce blocks at the auth, upstream, or firewall layers as needed.
- During incompatible API migrations, keep old backends alive long enough for in-flight requests to drain, or use canary/staged rollouts.
- Never delete old routes until a tested rollback path is verified.

## 11. Other Route Update Paths and Their Limits

### 11.1. Git / Config Server

Teams can store route YAML in Git and distribute it via Spring Cloud Config. That is a **shared configuration source**, yet:

- Gateway replicas still must fetch/reload configs via their own mechanisms.
- Pushing to Git does not make every Gateway refresh right away.
- When properties change, verify property binding/reload and **route cache refresh** mechanics for your version.
- Never assume Config Client's `/actuator/refresh` automatically syncs Gateway routes across every node.
- Maintain commit versioning and rollback workflows.

GitOps fits well when changes align with deployments, require PR reviews/approvals, and do not need millisecond runtime updates.

### 11.2. `DiscoveryClient` Route Definition Locator

Generating routes from `DiscoveryClient` creates routes for registered services. **It is not a shared dynamic route repository**, despite sharing the word "discovery."

It determines **which routes are generated from the service catalog**, whereas LoadBalancer later picks instances for `lb://`. When enabling the discovery locator, restrict which services may be exposed publicly along with path rewrites, filters, and security—never turn it on blindly and expose your entire internal registry to the Internet.

### 11.3. Java DSL and `RouteLocator` Beans

Routes defined via `@Bean RouteLocator` are code-defined configurations, not mutable records managed by `RouteDefinitionRepository`. Modifying Java DSL normally requires a build/deploy or custom logic providing updated routes.

Never expect `DELETE /actuator/gateway/routes/{id}` to delete a Java-DSL route the way it deletes a writer-saved dynamic route.

### 11.4. Do Kubernetes ConfigMaps Auto-Refresh?

Updating a mounted ConfigMap/Secret on the filesystem **does not mean** Spring Boot automatically re-parses and applies new routes, nor that Gateway clears its cache. Even when Kubernetes updates volume mounts, the application requires a version-verified **reload mechanism**; rolling restarts can be simpler and more reliable in many cases.

Never inject a ConfigMap as container environment variables expecting a running process to pick up edits dynamically—pods require a rollout to see updated env vars.

## 12. Monitoring Convergence and Replica Drift

For reliable operations, track **two revision concepts**:

- **Desired revision:** the latest revision approved by the control plane and published in the shared store.
- **Applied revision:** the revision **each Gateway replica verifies** it has loaded, compiled, and is actively serving.

Example dashboard:

| Replica | Desired | Applied | Drift Age | Status |
| --- | ---: | ---: | --- | --- |
| gateway-a | 42 | 42 | 0 s | Converged |
| gateway-b | 42 | 42 | 0 s | Converged |
| gateway-c | 42 | 41 | 75 s | Lagging, investigate |

This is a **custom application dashboard**, not a built-in Spring Cloud Gateway endpoint.

### 12.1. What Should You Measure?

- Route definition count vs. effective route count on every node.
- Desired/applied revisions, last refresh timestamp, and success/failure outcome.
- Convergence lag over time, lagging node count, and p95/p99 time-to-convergence.
- Route-change events received, deduplicated, errored, or lost due to bus disconnects.
- Route build errors from missing predicate/filter factories or invalid URIs.
- Per-route/per-node 404/5xx spikes post-rollout and upstream traffic shifts.
- Redis connection errors/latency and source read failures.
- Route config audit logs: actor, revision, reason, rollback ID.

Spring Cloud Gateway can expose metrics for **route definition counts** with compatible Actuator/Micrometer setups, yet **desired/applied revisions and cluster ACKs** require custom instrumentation.

Never attach unbounded-cardinality labels like dynamic URIs, message IDs, or request IDs to every metric. Keep labels to bounded route IDs and move fine-grained details into access-controlled logs and audit trails.

### 12.2. Checking Redis Alone Is Not Enough

A health check that merely queries Redis and reports "route v42 exists" does **not** prove **`CachingRouteLocator` on that node has applied v42**.

An internal health/convergence endpoint should report a revision **only after** verifying the effective route snapshot. Where route metadata/Actuator cannot confirm directly in your version, use **synthetic requests** routed through each specific replica to verify actual behavior.

A `200 OK` from local refresh or a log saying `"received v42"` is not an applied ACK.

## 13. Manually Testing Three Replicas

### 13.1. Illustrative Setup

Assume:

- `gateway-a`, `gateway-b`, `gateway-c` running the same binary version.
- Admin ports accessible strictly from the test network: `18081`, `18082`, `18083`.
- All three share a Redis route-definition repository.
- A mock `ORDER-SERVICE` or live HTTP upstream serving `/orders/42`.
- Actuator write access enabled **strictly in staging** or behind secured management tooling.
- Redis/Kafka bus if testing automated sync; initially you can refresh each node manually.

Before making changes, query the route list on **each node directly** (bypassing the public load balancer):

~~~bash
curl -sS http://localhost:18081/actuator/gateway/routes
curl -sS http://localhost:18082/actuator/gateway/routes
curl -sS http://localhost:18083/actuator/gateway/routes
~~~

**The localhost URLs above assume port-forwarding or proxying** to secured management ports—never expose Actuator admin ports publicly. In authenticated environments, pass credentials securely rather than relaxing auth to anonymous for testing.

### 13.2. Testing a Write on One Replica

Create a dynamic route via A using your control plane or secured Actuator API. Verify it persisted in the Redis repository. Then:

1. Refresh **only A**.
2. Query GET endpoints on A, B, and C.
3. Observe that A has the new route while B and C still serve the old snapshot.
4. Refresh B and C.
5. Confirm A, B, and C now share the same route definitions and behavior.

This test demonstrates the difference between **shared persistence** and **per-instance cache invalidation**.

### 13.3. Testing Synchronization via Event Bus

Wire an event consumer on each replica and the control plane:

1. Commit `revision=42` to the shared store.
2. Emit one `routes.changed(v42)` event.
3. A, B, and C receive the event and trigger local refreshes.
4. Convergence monitor waits for **applied v42 ACKs** from all three.
5. Send synthetic requests through each node verifying updated path and header behavior.
6. Measure time-to-convergence, Redis read counts, and route build errors.

Do not stop at verifying the message broker "published successfully"—measure **effective route behavior** on every replica.

### 13.4. Test Scenario Matrix

| Case | Action | Expected Outcome |
| --- | --- | --- |
| M1 | Add route v42 on A with Redis repository | New definition appears in shared store |
| M2 | Refresh A without refreshing B/C | Divergent effective routes observed |
| M3 | Call refresh twice through load-balanced public URL | Cannot guarantee both nodes refreshed |
| M4 | Call refresh directly on each node | Every node reloads definitions from shared source |
| M5 | Publish v42 event once | Online nodes receive and refresh via bus |
| M6 | Replica C offline during v42 broadcast, then restarts | Startup/reconciliation brings C to latest revision |
| M7 | Duplicate v42 event delivered | Idempotent consumer; cache unaffected |
| M8 | Event v41 arrives **after** v42 | Does not roll back to v41 accidentally |
| M9 | Redis temporarily unreachable | Alert/error raised; cache behavior matches version policy |
| M10 | Route uses `CustomFilter` present only on A | B/C report apply failure; never falsely claim converged |
| M11 | Two admins concurrently edit revision 41 | Optimistic lock/conflict; zero lost updates |
| M12 | Update two coupled routes | No unintended mixed-version snapshot served |
| M13 | Change `uri` to unauthorized host | Validation rejects SSRF / disallowed scheme |
| M14 | Delete dynamic route | Store and all node caches eventually drop the route |
| M15 | Roll back v42 to v41 | Entire cluster converges on known-good revision |
| M16 | Request in-flight during refresh | Does not break or switch mid-request |
| M17 | Node refresh returns 200 yet route is invalid | Never ACK applied before verifying effective routes |
| M18 | Duplicate IDs across Redis and route caches | Conflict detected and resolved per ID ownership |

### 13.5. Why Assert Behavior, Not Just Counts?

A cluster can report **12 routes** everywhere while A routes `/api/orders` to `ORDER-V2` and B routes to `ORDER-V1`; route counts match while behavior is broken.

Integration tests should verify:

~~~text
expectedRevision: 42
expectedRouteIds: [dyn-orders-api, dyn-catalog-api]
expectedPath: /api/orders/42
expectedUpstreamPath: /orders/42
expectedTargetService: ORDER-SERVICE
expectedAuthPolicy: protected
expectedResultAcrossNodes: consistent per contract
~~~

Avoid exposing sensitive topology headers in production responses just to identify which node served a request. In staging, use an authenticated internal debug header or correlation/distributed tracing to identify replicas when needed.

## 14. When Redis or the Message Bus Fails: Failover and Last-Known-Good

### 14.1. Redis Unreachable During Refresh

If Redis times out while a node reloads routes:

- Depending on implementation and version, refresh may error, keep the old cache, clear to empty, or handle it differently.
- **Never blindly assume** Gateway always preserves old routes or always returns 503.
- Test actual behavior on your deployed release, including cold starts when no local cache exists yet.
- Never allow unvalidated changes into the route cache just to "keep the service alive."
- Document your operational policy: serve **verified last-known-good**, pull the node out of rotation, or fail closed if security guarantees cannot be verified.

**Last-known-good** is a **deliberately engineered strategy**; it is not an automatic persistence guarantee of `RedisRouteDefinitionRepository`. Cold-start recovery requires signed/verified snapshots and a safe rollback path.

### 14.2. Message Bus Drops Events

If a Kafka consumer lags or a Redis Pub/Sub subscriber drops:

- Run periodic reconciliation comparing desired vs. applied revisions.
- When the bus supports durable offsets/ACKs, persist and manage offsets carefully.
- Never assume event ordering across multiple partitions/topics unless guaranteed.
- Handle duplicate messages idempotently.
- Alert if any node stays stale beyond SLA thresholds.
- Test recovery when a node restarts after being offline for an extended period.

### 14.3. Partial Refresh Failures and Rollback

A route definition referencing a filter factory missing on one node will fail route construction there. Newer Actuator docs note that some async refresh failures preserve existing routes, yet **you should not generalize that as a universal guarantee across all custom repositories and releases**.

Rollback procedure:

1. Identify the faulty revision and root cause (route, filter, URI, missing dependency).
2. Reactivate a known-good snapshot (e.g., v41) via your versioned/transactional mechanism.
3. Emit `routes.changed(v41-rollback)` or a **new monotonic revision** carrying v41's content so consumers do not drop it as an old event.
4. Each replica refreshes and verifies activation.
5. Declare rollback complete only after target nodes converge.
6. Preserve audit history—never edit or erase logs needed for incident review.

**Using strictly increasing revisions is safer**—for instance, publishing v43 containing v41's content—so consumers enforce monotonic revision checks without dismissing rollback notifications as stale events.

## 15. Security: Route Administration Can Alter the Entire Entry Point

Anyone permitted to add or modify routes wields far greater impact than typical configuration editors:

- Redirecting `/api/payments/**` to an external host outside the organization.
- Adding `RewritePath` or header filters that subvert authentication or auditing.
- Pointing routes at `127.0.0.1`, private subnets, or cloud instance metadata endpoints (SSRF).
- Exposing internal services publicly via overly broad predicates.
- Overwriting route IDs, `order`, or `Host` predicates to hijack traffic to the wrong backend.
- Injecting filters that leak `Authorization`, cookies, tokens, or PII.

### 15.1. Control-Plane Validation Checklist

- **RBAC and approvals:** enforce who may edit which routes, scoped by environment and namespace.
- **ID uniqueness:** prevent collisions across static and dynamic routes; enforce clear ownership.
- **URI allowlist:** allow only approved `http`, `https`, or `lb` schemes; validate service IDs/domains, ports, and DNS/network policies.
- **Filter allowlist:** permit only reviewed `GatewayFilterFactory` implementations and args; block header/token exfiltration.
- **Predicate checks:** constrain `Path`, `Host`, `Method`, route `order`, and match breadth.
- **Compatibility:** ensure filter/predicate factories exist across **all live binary versions** during rollouts.
- **Change validation:** schema checks, dry-runs, routing tests, and security regressions.
- **Auditing / rollback:** log revision, author, approver, diff, and activation timestamp.
- **Network enforcement:** block Gateway egress to unauthorized destinations even if route config is flawed.
- **Secret hygiene:** route definitions and events must never carry raw credentials, private keys, or bearer tokens.

Never let public clients supply target URIs/hosts to be saved as routes. The route control plane is a **critical trust boundary** requiring stronger protection than ordinary business APIs.

### 15.2. Securing Actuator and Redis

- Isolate management interfaces from public API ports via firewalls/network policies.
- Default Actuator to **`read-only`**; enable `unrestricted` only with explicit justification, strong auth, and narrow scope.
- Enforce TLS/mTLS over untrusted networks and never log admin tokens.
- Restrict Redis access strictly to Gateway and control-plane clients using ACLs, auth, encryption, and backups.
- Never rely on `/actuator/gateway/refresh` being "hard to guess" for security.
- Rate-limit refreshes so no actor can trigger thousands of continuous route rebuilds.
- Keep rate-limit counters separated from route definitions in Redis ACL policies with strict least-privilege permissions.

## 16. Practical Scenario: Updating a Route Without Restarting the Cluster

Suppose a system has 3 Gateway replicas, a shared Redis repository, and route:

~~~text
Path:     /api/inventory/**
Route ID: dyn-inventory
Target:   lb://INVENTORY-SERVICE
Filter:   StripPrefix=1
Revision: 71
~~~

The development team wants to inject a common upstream header in revision 72 without restarting the cluster.

**Rollout plan:**

1. Control plane receives the change and validates owner, target service, predicates/filters, and auth impact.
2. Build candidate revision 72; confirm A, B, and C all have the required filter factory.
3. Persist the updated route to the shared store with version control and no duplicate route ID.
4. Emit `routes.changed(72)` post-commit.
5. A, B, and C receive the event, check the latest revision, and trigger local `RefreshRoutesEvent`.
6. Each node verifies `dyn-inventory` applies the new header behavior with no duplicate routes.
7. Convergence monitor confirms all three applied 72; if C fails, never report "100% deployed."
8. Run synthetic GET probes through each node verifying path, headers, and status.
9. Monitor 404/5xx rates, latency, upstream traffic, and auth/rate limits post-change.
10. On error, publish **revision 73** restoring revision 71's config, refresh, and verify all three nodes.

**Success criterion:** not merely "Redis holds the new route," but **all three Gateway nodes serve identical contract behavior** with a fast, safe rollback path.

### 16.1. Knowledge-Check Questions

1. Why is `InMemoryRouteDefinitionRepository` unsuitable for sharing routes across three JVMs?
2. When sharing Redis, why can B still serve the old route?
3. Which JVM does `RefreshRoutesEvent` affect, and why are an event bus or fan-out needed?
4. Does `POST /actuator/gateway/refresh` returning `200` prove cluster convergence?
5. If node C is offline during a Pub/Sub broadcast, what mechanism catches C up once back online?
6. `GET /actuator/gateway/routes` shows a built route—how do you prove which revision is active?
7. Why do identical route counts not guarantee identical routing behavior?
8. If two admins edit routes simultaneously, how do you prevent lost updates?
9. Why test filter compatibility across versions before updating during a rolling upgrade?
10. How do you roll back without tripping consumers' stale-event ignore logic?

## 17. Production Deployment Checklist

- [ ] Clearly separated **desired route definitions** from each replica's **effective route cache**.
- [ ] Confirmed the shared dynamic route store (Redis/DB) actually works rather than falling back to in-memory.
- [ ] Enabled Redis repository using the version-accurate property key and reactive Redis starter.
- [ ] Enforced unique route ID ownership with zero collisions across YAML, Java DSL, discovery, and Redis.
- [ ] Equipped every replica with local refresh handling and its own notification consumer.
- [ ] Avoided sending refresh calls to a load-balanced public URL expecting all replicas to refresh.
- [ ] Built bus/event notifications with revisions, deduplication, and out-of-order handling.
- [ ] Implemented periodic reconciliation or durable delivery for offline nodes and dropped events.
- [ ] Emitted events only after the control plane commits to the store.
- [ ] Enforced optimistic concurrency or transactional snapshots when multiple users edit routes.
- [ ] Used atomic/staged activation for coupled multi-route edits to avoid mixed-version states.
- [ ] Verified applied revisions after building effective routes rather than ACKing on HTTP 200.
- [ ] Deployed a convergence monitor, stale-node alerts, route diffs, and refresh-failure metrics.
- [ ] Tested Redis/bus outages, cold starts, rollbacks, duplicate events, and rolling binary upgrades.
- [ ] Tested last-known-good and rollback policies rather than assuming Gateway retains old caches automatically.
- [ ] Kept Actuator management endpoints private, tightly authorized, and `read-only` by default.
- [ ] Validated URIs, predicates, and filter arguments against SSRF and auth bypasses.
- [ ] Excluded tokens, cookies, secrets, and user data from event payloads and route metadata.
- [ ] Tested live requests through **every node** after rollout before declaring convergence.
- [ ] Verified route ordering, `lb://`, service discovery, and filter chains post-refresh.
- [ ] Verified in-flight requests and rollback compatibility against both old and new backends.

## 18. Summary and Official References

**Sharing routes and synchronizing refreshes across multiple replicas are two distinct challenges.** `RedisRouteDefinitionRepository` or a shared config store can supply identical **desired definitions** to A, B, and C, while each Gateway still maintains its own **local effective route cache**. `RefreshRoutesEvent` and `POST /actuator/gateway/refresh` refresh only the instance receiving that event or command.

Reliable cluster convergence requires a **control plane** writing validated routes to a shared store, **signals** reaching every replica, **local refreshes**, **applied revision verification**, **ACKs**, **reconciliation** for dropped events, and **versioned rollbacks**. Multi-route updates also require atomicity and precedence checks to prevent mixed-version states. Together, these practices let Gateway route dynamically while safeguarding authentication, rate limiting, retries, circuit breakers, service discovery, TLS, and observability.

Official references to verify against your running version:

- [Spring Cloud Gateway Server WebFlux — Sharing Routes between multiple Gateway instances](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/sharing-routes.html).
- [Spring Cloud Gateway Server WebFlux — Actuator API, refresh and route management](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/actuator-api.html).
- [Spring Cloud Gateway Server WebFlux — Configuration and RouteDefinitionLocator](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/configuration.html).
- [Spring Cloud Gateway — Configuration Properties, Redis repository namespace](https://docs.spring.io/spring-cloud-gateway/reference/configprops.html).
- [Spring Cloud Gateway 4.2 — Actuator API](https://docs.spring.io/spring-cloud-gateway/reference/4.2/spring-cloud-gateway/actuator-api.html).
