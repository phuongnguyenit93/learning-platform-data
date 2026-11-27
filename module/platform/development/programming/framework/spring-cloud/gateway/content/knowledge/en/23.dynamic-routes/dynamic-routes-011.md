# Protecting Target URIs, Expressions, and Parameters in Dynamic Spring Cloud Gateway Configuration

In a microservices architecture, an **API Gateway** can modify routes without redeploying application source code. That capability is invaluable when onboarding new services, shifting traffic, or managing hundreds of APIs—yet it simultaneously turns route configuration into **input capable of steering networks, filter chains, and access policies**.

A seemingly simple route-creation call to a management API can:

- Change `uri` to a forbidden address, making Gateway call internal admin services, internal hosts, or cloud metadata endpoints (**SSRF**).
- Inject expressions, regexes, or `GatewayFilter` arguments altering paths, headers, retry budgets, or fallback destinations.
- Register overly broad predicates with high-priority `order`, letting the new route **hijack traffic** from protected routes.

This lesson belongs to the **Dynamic Routes** chapter, focusing on **protecting target URIs, expressions, and parameters in dynamic configuration** for **SPRING_CLOUD_GATEWAY**. It ties together route predicates, filter chains, path/header rewrites, service discovery, Spring Security, rate limiting, circuit breakers, retries, TLS, and observability so configuration changes never erode security boundaries.

> **Scope:** Examples target **Spring Cloud Gateway Server WebFlux**. Configuration namespaces, starter names, Actuator APIs, and internal mechanics vary across Spring Boot/Spring Cloud release trains. Gateway Server MVC follows a different model. Service names, hostnames, policies, and versions below are **illustrative**, not turnkey production policies.

## 1. Dynamic `RouteDefinition`s Are Executable-Privilege Configuration

In Gateway Server WebFlux, a `RouteDefinition` declares a route via these fields:

| Field | Example | Impact When Edited |
|---|---|---|
| `id` | `managed-public-catalog` | Identifier used for updates, deletion, and observability |
| `uri` | `lb://catalog-service` | Selects the **outbound target** |
| `predicates` | `Path=/api/public/catalog/**` | Selects **which requests enter the route** |
| `filters` | `StripPrefix=2` | Transforms requests/responses, enforces limits or fallbacks |
| `order` | `1000` | Precedence when multiple routes match |
| `metadata` | Timeouts, runtime-custom data | Can affect wait times or observability |

Static YAML configuration is typically reviewed and deployed alongside an application release. With dynamic routes, the exact same fields may arrive from a database, portal, management API, GitOps, or service registry. **Risk depends on the privilege of the data source**, not whether the route lives in YAML or JSON.

### Components in the Route Lifecycle

- `RouteDefinitionLocator` supplies route definitions.
- `RouteDefinitionWriter` models saving/deleting route definitions.
- `RouteDefinitionRepository` is a route source supporting both reading and writing; persistence depends on the implementation.
- Gateway components compile `RouteDefinition` into runtime `Route` objects and instantiate predicates/filters.
- Runtime routes may be cached to avoid querying config stores on every request.
- `RefreshRoutesEvent` and refresh mechanisms trigger reloads, yet **do not form a distributed commit protocol across every Gateway instance**.

~~~mermaid
flowchart TD
    C["Administrator / control plane"] --> AU["Authentication + authorization"]
    AU --> CMD["High-level command: resource, targetCode, policyId"]
    CMD --> V["Validate + allowlist + route conflict checks"]
    V --> D{"Approved?"}
    D -->|No| NO["Reject + audit"]
    D -->|Yes| P["Save snapshot/revision"]
    P --> RF["Refresh / per-node rollout"]
    RF --> RT["Gateway runtime routes"]
    RT --> TRAFFIC["Predicate match + filters + outbound routing"]
    TRAFFIC --> MON["Metrics + rollback readiness"]
~~~

**Foundational rule:** Never allow self-service callers to submit raw `RouteDefinition` payloads with arbitrary `uri`, `predicates`, `filters`, and `order` values and save them directly.

## 2. Threat Model for Route Update APIs

Not every portal account should wield full control over the Gateway. Separate capabilities across: **view**, **propose**, **approve**, **publish**, **roll back**, **delete**, and **manage target allowlists**.

| Threat | Example | Consequence | Control |
|---|---|---|---|
| SSRF | Picking internal/localhost URIs | Reading/calling unauthorized endpoints | Approved targets + network egress policies |
| Route hijacking | `Path=/**` with aggressive `order` | Capturing traffic from other APIs | Prefix/order/overlap validation |
| Cross-tenant tampering | Editing another tenant's route | Outage or cross-tenant data leakage | RBAC/ABAC and ownership |
| Expression abuse | Raw SpEL / Bean references | Referencing components outside the contract | Reject raw expressions |
| Header forgery | Injecting `X-Authenticated-User` or stripping auth headers | Impersonation, breaking identity contracts | Allowlist filters and headers |
| Regex DoS | Patterns with heavy backtracking | Sudden CPU/latency spikes | Ban arbitrary regexes; bound patterns |
| Retry storms | Excessive `retries` and timeouts | Amplifies load on backends | Bounded policy budgets |
| Unsafe caching | Caching personalized APIs | Leaking user data | Default-disable caching policy |
| Config drift | Only some nodes load the new route | Inconsistent routing and security | Versioned rollouts + reconciliation |

**Authorize against the route resource itself**, not just the HTTP `PUT` or `DELETE` verb. Knowing a route ID does not grant permission to modify that route.

## 3. Target URIs: Allowlist-Driven, Never Client-Chosen

The `uri` field governs where Gateway dispatches outbound requests. For portals managing routes to registered services, the clean pattern is letting users pick an approved **`targetCode`** and mapping it server-side to the real URI.

| Requested URI | Trust Level | Example Policy |
|---|---|---|
| `lb://catalog-service` | Valid if the service ID is approved | Allowed via mapping |
| `lb://internal-admin` | May exist in registry yet must stay private | Rejected |
| `https://partner.example.test` | External partner with dedicated contract | Permitted only under dedicated controls |
| `http://127.0.0.1:8080` | Loopback | Rejected in self-service |
| `http://169.254.169.254` | Link-local, tied to cloud metadata services | Rejected |
| `http://10.0.0.5` | Arbitrary private IP | Rejected unless explicitly contracted |
| `forward:/actuator/gateway/routes` | Forwards to internal handler | Rejected for self-service routes |
| `ws://...` / `wss://...` | WebSocket | Permitted only under explicit policy |
| URI with userinfo, fragment, or ambiguous host | Easily bypasses naive validator assumptions | Rejected if unsupported by schema |

**This is a recommended security policy, not an exhaustive list of schemes Gateway supports.** Runtime support for `lb`, `http`, `https`, `ws`, `wss`, `forward`, or others depends on version. Technical support for a scheme **does not make it permitted by default** in route-management APIs.

### Better Input: Omit the Raw URI Field

Avoid accepting:

~~~json
{
  "id": "anything",
  "uri": "http://arbitrary-host:8080",
  "predicates": ["Path=/**"],
  "filters": ["..."]
}
~~~

Prefer a narrow command schema:

~~~json
{
  "resource": "catalog",
  "targetCode": "catalog",
  "exposure": "PUBLIC_READ_ONLY"
}
~~~

Server performs the mapping:

~~~text
targetCode=catalog  -> lb://catalog-service
targetCode=articles -> lb://article-service
~~~

In a real application, that mapping also binds **owner, environment, authentication policy, permitted public prefixes, and usage rights**. `targetCode` is a platform catalog key—**not an arbitrary service name clients can invent**.

### Parsing a URI Cleanly Does Not Mean It Is Safe

`URI.create(input)` verifies basic URI syntax; it **does not prove** the scheme is safe, the domain is controlled, where DNS will resolve, whether outbound network policies are respected, or whether secrets are embedded. Regex validation over raw URI strings frequently misses canonicalization, IDNs, userinfo, ports, or lookalike domains.

**Prefer pre-built URLs/URIs from a curated target catalog**; if business requirements force registering HTTPS hosts, require domain-ownership verification plus an independent network egress control layer.

## 4. Preventing SSRF with Layered Controls

A hostname allowlisted when saving a route can still resolve to a different IP when Gateway proxies traffic. Guard specifically against **DNS rebinding, CNAME swaps, IPv4/IPv6 quirks, loopback, and unapproved link-local/private addresses**.

### HTTP(S) Destination Defense Flow

1. Parse the URI using a standard library and inspect `scheme`, hostname, port, userinfo, and fragment.
2. Canonicalize hostnames with strict label rules—never naive suffix checks like "ends with `example.test`" ignoring dot boundaries.
3. Allowlist exact approved **hostname + port + scheme** tuples rather than broad wildcard suffixes.
4. Enforce DNS and resolved-IP rules at the network layer to defeat time-of-check-to-time-of-use resolution drift.
5. Use egress firewalls, Kubernetes `NetworkPolicy`, ACL proxies, or security groups so Gateway **cannot** reach forbidden targets even if application validation has a bug.
6. For HTTPS, validate certificate chains, hostname/SNI, and TLS trust stores strictly—never use trust-all clients.
7. Audit redirects, proxies, and custom filters: never assume all HTTP clients uniformly follow or ignore `Location` headers across every code path.
8. Audit approved `targetCode`s and actual destinations appropriately without logging raw tokens or sensitive query strings.

**Private IPs are not inherently trusted.** Internal subnets host databases, actuators, metadata services, admin UIs, and workloads outside the route author's privilege boundary.

### `lb://` URIs and Service Discovery

`lb://catalog-service` constrains routing to a service ID, yet the registry/`DiscoveryClient` can return **different instance hosts and ports over time**. To stay safe:

- Allow only explicitly approved service IDs in public routes.
- Enforce access control over which workloads can register instances into the registry.
- Keep egress, network, and TLS policies active over addresses selected by LoadBalancer.
- Monitor discovery/health state; "present in registry" never equals "approved for public exposure."
- Never let route creators pick arbitrary service IDs to probe internal services.

## 5. Predicates Are Traffic-Selection Authority

An overly broad `Path` can capture legitimate requests meant for other routes even when the target URI is allowlisted.

~~~yaml
# Never allow self-service users to create this route.
id: overly-broad
uri: lb://catalog-service
order: -999
predicates:
  - Path=/**
~~~

Govern **both** predicates and `order` together rather than validating strings in isolation.

| Field / Predicate | Risk | Appropriate Policy |
|---|---|---|
| `Path` | `/**`, hijacking `/api/admin/**` | Platform allocates prefixes and builds patterns |
| `Host` | Hijacking another tenant's domain | Verify host ownership |
| `Method` | Accidentally exposing POST/PUT/DELETE | Permit only methods allowed by exposure policy |
| `Header` / `Cookie` | Heavy regexes, spoofed client headers | Never use as proof of identity |
| `Query` | Regexes / ambiguous query values | Allowlisted patterns only |
| `RemoteAddr` | Untrusted proxy/client IPs | Trusted proxy policy |
| `After` / `Before` / `Between` | Opening routes at the wrong time | Timezone and expiry reviews |
| `order` | Overriding critical routes | Platform-assigned value |

### Route Shadowing and Namespaces

Example:

~~~text
Existing routes:
  admin-api      Path=/api/admin/**       order=0
  public-api     Path=/api/public/**      order=100

Proposed route:
  new-route      Path=/api/**             order=-100
~~~

Under Gateway's normal matching behavior, lower `order` values take priority. The new route can capture traffic previously routed to `admin-api`, depending on other predicates. Therefore evaluate **the complete post-change route set**—including YAML, repositories, and service discovery—rather than validating one route in isolation.

**Never let self-service APIs claim** `/api/**`, `/actuator/**`, `/internal/**`, or another tenant's prefix. Account for casing, percent-encoding, trailing slashes, and path normalization differences across Gateway, proxies, and backends.

## 6. Valid Filter Names Do Not Prove Arguments Are Safe

`GatewayFilter` factories can mutate requests, responses, and system load.

| Factory or Filter Group | Risk If Free-Form Arguments Are Permitted |
|---|---|
| `SetRequestHeader`, `AddRequestHeader` | Injects forged identity/role/`Host` headers, overwriting trusted headers |
| `RemoveRequestHeader` | Strips `Authorization` or required backend metadata |
| `StripPrefix`, `SetPath`, `RewritePath` | Maps public paths onto sensitive backend endpoints |
| `RequestRateLimiter` | Picks arbitrary `KeyResolver`, overly generous quotas, or bypasses limits |
| `Retry` | Multiplies outbound attempts, replays non-idempotent POSTs |
| `CircuitBreaker` | Routes `fallbackUri`/handler outside approved targets |
| `FallbackHeaders` | Leaks raw exception messages to untrusted consumers |
| `LocalResponseCache` | Caches private or tenant-sensitive responses |
| `SetResponseHeader`, `RemoveResponseHeader` | Weakens CORS, security, or cache headers against policy |
| Custom factories | Runs scripts, queries, network calls, or buffers bodies via unvetted args |

**Allowlist both filter names and argument schemas.** If policy approves `StripPrefix` fixed at `2`, callers must not be able to change it to `10`. If rate limiting keys off an authenticated user via `KeyResolver`, callers must not swap it for raw client IP or an unapproved bean reference.

### Regexes Can Become Security and Performance Bugs

Certain predicates and filters accept regexes, such as `Header`, `Query`, or `RewritePath`. Patterns with nested quantifiers can trigger **catastrophic backtracking** and CPU spikes on long inputs.

To expose `/api/public/catalog/**`, platform-generated config is usually far simpler:

~~~yaml
predicates:
  - Path=/api/public/catalog/**
filters:
  - StripPrefix=2
~~~

If dynamic regexes are genuinely required, bound length, syntax, character classes, and matched fields, and run fuzz/performance tests. **Compiling cleanly does not prove a regex is safe under adversarial traffic.**

## 7. SpEL, Bean References, and Configuration Expressions

Some Gateway configurations use **Spring Expression Language (SpEL)**. For instance, `RequestRateLimiter` in Server WebFlux supports referencing a `KeyResolver` bean:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders-limited
          uri: lb://orders-service
          predicates:
            - Path=/api/orders/**
          filters:
            - name: RequestRateLimiter
              args:
                key-resolver: "#{@userKeyResolver}"
                redis-rate-limiter.replenishRate: 10
                redis-rate-limiter.burstCapacity: 20
~~~

`#{@userKeyResolver}` is fine when controlled by developers or ops. However, if route submitters can supply **arbitrary expression strings**, they may attempt to access unintended beans or behaviors depending on the evaluation context.

**Do not claim every SpEL input automatically causes remote code execution.** Blast radius depends on where expressions evaluate, restriction mechanisms, and runtime environment. Still, the security principle is clear: **never accept raw SpEL or bean references from self-service APIs**.

### Replace Expressions with Policy IDs

Avoid accepting:

~~~json
{
  "rateLimiter": {
    "keyResolverExpression": "untrusted-expression",
    "replenishRate": 100000
  }
}
~~~

Prefer accepting:

~~~json
{
  "rateLimitPolicy": "orders-user-read"
}
~~~

The server maps `orders-user-read` to a **pre-approved** policy containing the resolver, replenish rate, burst capacity, empty-key handling, and safe filter parameters. Apply the same principle to `discovery.locator.include-expression`, regexes, header templates, and custom factory arguments: **compile from a constrained schema** rather than storing user-supplied expressions.

## 8. Management APIs Should Accept High-Level Commands

Suppose the platform allows registering only two public-read API groups:

- `catalog` → `lb://catalog-service`;
- `articles` → `lb://article-service`.

Self-service payload:

~~~json
{
  "resource": "catalog",
  "targetCode": "catalog"
}
~~~

Server-side controls:

1. Authenticate caller with a trusted admin identity.
2. Authorize caller to create routes for the target owner and environment.
3. Validate `resource` against a strict charset, length, and authorized prefix.
4. Resolve `targetCode` strictly as a key in a **server-owned** map.
5. Generate the route ID server-side inside a namespace isolated from protected routes.
6. Derive `Path`, `Method`, `order`, and filters from platform policy.
7. Run conflict detection across existing routes and management URLs.
8. Save/publish with revisions, auditing, and dry-run/canary checks where required.

### Java Example: Compiling a Constrained `RouteDefinition`

This sample uses common Gateway Server WebFlux APIs; it is **not a complete production management system**. It omits authorization, optimistic locking, and multi-node distribution.

~~~java
package example.gateway.dynamic;

import java.net.URI;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

import org.springframework.cloud.gateway.filter.FilterDefinition;
import org.springframework.cloud.gateway.handler.predicate.PredicateDefinition;
import org.springframework.cloud.gateway.route.RouteDefinition;

public final class SafeRouteCompiler {

    private static final Pattern RESOURCE =
        Pattern.compile("[a-z][a-z0-9-]{0,31}");

    private static final Map<String, URI> ALLOWED_TARGETS = Map.of(
        "catalog", URI.create("lb://catalog-service"),
        "articles", URI.create("lb://article-service")
    );

    public record RouteCommand(String resource, String targetCode) {}

    public RouteDefinition compile(RouteCommand input) {
        if (input == null || input.resource() == null ||
            input.targetCode() == null ||
            !RESOURCE.matcher(input.resource()).matches()) {
            throw new IllegalArgumentException("Invalid route command");
        }

        URI target = ALLOWED_TARGETS.get(input.targetCode());
        if (target == null) {
            throw new IllegalArgumentException("Target is not approved");
        }

        if (!input.resource().equals(input.targetCode())) {
            throw new IllegalArgumentException("Resource/target mismatch");
        }

        RouteDefinition route = new RouteDefinition();
        route.setId("managed-public-" + input.resource());
        route.setUri(target);
        route.setOrder(1000); // Chosen by platform, not client.
        route.setPredicates(List.of(
            new PredicateDefinition(
                "Path=/api/public/" + input.resource() + "/**"),
            new PredicateDefinition("Method=GET,HEAD")
        ));
        route.setFilters(List.of(
            new FilterDefinition("StripPrefix=2")
        ));
        return route;
    }
}
~~~

### Why Are These Constraints So Effective?

- No arbitrary `uri` input, so callers cannot direct Gateway toward localhost or `forward:/actuator`.
- `resource` cannot contain slashes, wildcards, regex metacharacters, or control characters.
- Route accepts only `GET`/`HEAD` per the public-read exposure policy.
- Zero raw filters, SpEL, regexes, or `order` values from the client.
- Route ID uses the `managed-public-` namespace and platform-generated path filters.
- Target URI comes directly from an allowlist map rather than parsing caller-provided strings.

**Do not stop at the compiler:** layer on RBAC/ABAC, route-shadowing checks, ownership validation, route quotas, auditing, and backend path tests. Specifically, `StripPrefix=2` rewrites `/api/public/catalog/items/42` to `/catalog/items/42`; the backend must still enforce authorization if serving anything beyond public data.

## 9. Saving Routes and Refreshing in a Reactive Pipeline

After compiling cleanly, a management service can use `RouteDefinitionWriter` to persist the route and emit `RefreshRoutesEvent` upon completion:

~~~java
package example.gateway.dynamic;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.cloud.gateway.event.RefreshRoutesEvent;
import org.springframework.cloud.gateway.route.RouteDefinition;
import org.springframework.cloud.gateway.route.RouteDefinitionWriter;
import reactor.core.publisher.Mono;

public final class RoutePublisher {

    private final RouteDefinitionWriter writer;
    private final ApplicationEventPublisher events;
    private final SafeRouteCompiler compiler;

    public RoutePublisher(
            RouteDefinitionWriter writer,
            ApplicationEventPublisher events,
            SafeRouteCompiler compiler) {
        this.writer = writer;
        this.events = events;
        this.compiler = compiler;
    }

    public Mono<Void> upsert(SafeRouteCompiler.RouteCommand command) {
        // Call only when authZ, ownership, and conflict checks PASSED.
        RouteDefinition candidate = compiler.compile(command);

        return writer.save(Mono.just(candidate))
            .then(Mono.fromRunnable(() ->
                events.publishEvent(new RefreshRoutesEvent(this))));
    }
}
~~~

**Note:** `RouteDefinitionWriter` is an interface; the app must provide a **matching implementation** (in-memory or external repository). Saving inside one process does not automatically create durable persistence or shared state across Gateway instances.

Reactive composition via `then(...)` ensures the refresh event fires **after the save publisher completes**. Never call `.subscribe()` mid-chain and return HTTP success prematurely.

### Refresh Is Not a Distributed Transaction

After saving and emitting the event, verify:

- Did the repository persist durably?
- Which nodes received the new revision, and did any fail to refresh or bind?
- If two admins edit the same route ID concurrently, are revisions/optimistic locking enforced?
- Does a newly launched Gateway instance pull the right snapshot?
- If the new route produces 401/403/404/5xx errors, can you roll back to the previous snapshot?
- When a route is revoked, does it disappear from caches across every node?

`RefreshRoutesEvent` is strictly a local refresh lifecycle signal; **it does not guarantee every node sees the same version at the same instant**.

## 10. Gateway Actuator Is a Control Plane Requiring Protection

Depending on version and config, Spring Cloud Gateway exposes route inspection, refresh, and potentially route management under `/actuator/gateway/**`. Enable write endpoints only when genuinely required and behind **strict admin permissions**.

### Minimum Security Policy

- Never expose mutation endpoints to the public Internet.
- Use a private management network/VPN or identity-aware proxy.
- Protect with **Spring Security WebFlux** enforcing granular roles/scopes per capability.
- Separate permissions for **read/inspect**, **refresh**, **create/update/delete**, and **approve**.
- If Actuator runs on a dedicated port or application context, secure that exact context.
- Enforce request size caps, rate limits, auditing, and CSRF/session protections if a management UI uses cookies.
- Never return credentials, sensitive URIs, or raw configs in responses or logs to unauthorized actors.
- Verify exposure and read/write properties for **your exact version**; never assume endpoints, HTTP verbs, or property names stay constant across releases.

Minimal configuration avoiding exposing route management in a basic deployment:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Audit config overrides and actual management ports; examples never replace security rules or network ACLs. Never set `include: "*"` just for debugging convenience.

**Discovering a route ID from a listing endpoint does not grant permission to delete it.** Every update or delete must check ownership, protected flags, and revisions.

## 11. Validating Schemas Before and After Compilation

A secure dynamic routing system separates two representations:

1. **Command DTO:** business identifier, `targetCode`, policy ID, expected revision.
2. **Compiled `RouteDefinition`:** platform-generated URIs, predicates, and filters.

Illustrative policy source (**not a built-in Gateway YAML schema**):

~~~yaml
routePolicies:
  public-read:
    allowedResources: [catalog, articles]
    allowedMethods: [GET, HEAD]
    pathPrefix: /api/public/
    fixedFilters: [StripPrefix]
    stripPrefixCount: 2
    retryMax: 0
    cacheAllowed: false
    authorization: PUBLIC_READ_ONLY

  orders-user-read:
    allowedResources: [orders]
    allowedMethods: [GET]
    pathPrefix: /api/orders/
    fixedFilters: [StripPrefix, RequestRateLimiter]
    rateLimitPolicyId: orders-user-read
    cacheAllowed: false
    authorization: JWT_REQUIRED
~~~

`authorization: JWT_REQUIRED` in this illustrative YAML **does not automatically configure Spring Security**. Your platform must map policies to real security and routing rules and verify backend authorization.

| Pre-Compilation | Post-Compilation |
|---|---|
| Reject unknown fields, raw URIs, raw filters | URI/schema matches allowlist |
| Enforce payload size, charset, and nesting depth | Route ID avoids reserved IDs |
| Verify owner, tenant, and environment | Path/Host/Method/Order do not shadow routes |
| Verify caller is permitted to pick that policy ID | Filter names and args obey policy |
| Check expected revision | Does not drop or alter security headers outside contract |
| Reject arbitrary SpEL and regexes | No overly broad routes or unbounded timeouts/budgets |
| Audit requester and reason | Capture diff/snapshot prior to publishing |

**Never silently ignore unknown fields** in ways that cause two clients to interpret schemas differently. Define explicit handling for nulls, duplicate JSON keys, oversized payloads, deeply nested objects, and malformed encodings.

## 12. Route Shadowing: Must Validate Against the Entire Config Set

A candidate route may look clean in isolation yet conflict when combined with active routes.

~~~text
Existing:
  admin-api:  Path=/api/admin/**,  order=0
  public:     Path=/api/public/**, order=100

Proposed:
  new-route:  Path=/api/**,        order=-100
~~~

Here the candidate matches both admin and public paths with higher priority. **URI allowlists alone cannot stop traffic hijacking.**

A pre-publish checker should inspect:

- Prefixes allocated per team or tenant.
- Host/domain ownership and wildcard hosts.
- Route `order`, methods, and other predicates.
- Reserved public, internal, actuator, and security paths.
- Routes auto-generated by the `DiscoveryClient` locator.
- How `RewritePath`/`StripPrefix` maps public paths onto backend paths.
- Edge cases with percent-encoding, dot segments, double slashes, Unicode, and case normalization.
- Non-Gateway handlers that can still receive requests on overlapping paths.
- Default/global filters and response/security policies.

**Static analysis rarely proves all regex and predicate interactions.** Add integration tests using representative URLs, including targeted negative cases to catch shadowing.

## 13. Spring Security and Backend Authorization Remain Independent

A new route does not disable `SecurityWebFilterChain` by itself. Yet it can expose a new backend or path inside a `permitAll` URL region created by overly broad security matchers. Always review both **Gateway public URL security policies** and **backend business authorization**.

For example, a public `GET` route to `catalog-service` is safe only if backend path `/catalog/items/42` genuinely serves non-private data. Never judge safety solely by seeing `Method=GET` on the route predicate.

### Interactions Across Gateway Features

| Feature | What Dynamic Routes Must Respect |
|---|---|
| Authentication / Authorization | Never forge principals/roles or expose private APIs on public paths |
| `RequestRateLimiter` | `KeyResolver` keys off verified identity; handle empty-key and Redis errors safely |
| `CircuitBreaker` | Permit only approved breakers and `fallbackUri`s; never forward to admin handlers |
| `Retry` | Bound attempts, backoff, timeouts, idempotency, and total retry budgets |
| `LocalResponseCache` | Never cache user- or tenant-sensitive responses; test TTL, `Vary`, and correctness |
| LoadBalancer / `DiscoveryClient` | Service ID allowlists, instance registration ACLs, and health checks |
| TLS | Never allow disabling certificate or hostname verification |
| Headers | Never arbitrarily mutate `Authorization`, `Host`, or `X-Authenticated-User` |
| Observability | Include route ID and revision in traces; never log raw secrets |

### Retries and Caching After Changing URIs

If a route's URI switches from a public backend to a backend handling private data, pre-existing cache or retry filters may no longer be safe. Treat changing `uri` as **changing a security contract**, not just swapping TCP endpoints.

Local caches may retain entries across route refreshes depending on implementation; define explicit invalidation strategies. With retries, one request can trigger multiple outbound attempts—enforce budgets and avoid replaying side effects.

## 14. Safe Rollouts Across Multiple Gateway Instances

~~~mermaid
flowchart LR
    CP["Control plane, approved snapshot v12"] --> STORE["Versioned route store"]
    STORE --> A["Gateway A: v12"]
    STORE --> B["Gateway B: v11"]
    STORE --> C["Gateway C: v12"]
    A --> DS["Downstream services"]
    B --> DS
    C --> DS
    MON["Reconciliation / monitoring"] -.-> A
    MON -.-> B
    MON -.-> C
~~~

Identical URL requests can see divergent behavior while Gateway B lacks the new revision. For security-sensitive route edits, **a partial rollout lets requests hitting older nodes follow older policies**.

### Recommended Publication States

~~~text
DRAFT -> VALIDATED -> APPROVED -> PUBLISHED
                                  |
                                  +-> ACTIVE_ON_ALL_NODES
                                  +-> FAILED_ROLLOUT -> ROLLED_BACK
~~~

These are **control-plane governance states**, not built-in enums on `RouteDefinition`.

### Guarantees to Implement

1. Whole-route-set snapshots/versions.
2. Idempotent application and revision/optimistic locking.
3. Per-node reporting of loaded revisions and any binding errors.
4. Canary verification before expanding rollouts.
5. Rollback to an approved, verified snapshot.
6. Policies for draining or isolating stale nodes during security changes.
7. Post-refresh verification of route conflicts and security invariants.
8. Quotas on route/filter counts and cleanup of retired routes.

Never simply emit `RefreshRoutesEvent` and assume a cluster updated atomically.

## 15. Practice Lab: Testing Secure Dynamic Routing

Assume a lab environment with:

- Gateway Server WebFlux at `http://localhost:8080`.
- Registered catalog service with service ID `catalog-service` handling `GET /catalog/items/42`.
- A control-plane service permitting publishes only after authorization checks.
- `SafeRouteCompiler` and `RoutePublisher` from sections 8–9.
- A list of admin/public URLs that must remain untouched (negative-test fixtures).

### Step 1 — Propose a Valid Route

~~~json
{
  "resource": "catalog",
  "targetCode": "catalog"
}
~~~

Expected compiler output:

~~~text
id:         managed-public-catalog
uri:        lb://catalog-service
order:      1000
predicates: Path=/api/public/catalog/**, Method=GET,HEAD
filters:    StripPrefix=2
~~~

After publishing and refreshing, test:

~~~bash
curl -i "http://localhost:8080/api/public/catalog/items/42"
~~~

The backend should receive `/catalog/items/42` and respond per business policy. Also verify the active route revision on the Gateway instance handling the request.

### Step 2 — Prove Arbitrary Targets Cannot Be Created

In unit tests, call the compiler with a non-allowlisted target code:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class SafeRouteCompilerTest {

    private final SafeRouteCompiler compiler = new SafeRouteCompiler();

    @Test
    void allowsCuratedCatalogRoute() {
        var route = compiler.compile(
            new SafeRouteCompiler.RouteCommand("catalog", "catalog"));
        assertEquals("managed-public-catalog", route.getId());
        assertEquals("lb://catalog-service", route.getUri().toString());
    }

    @Test
    void rejectsPathInjection() {
        assertThrows(IllegalArgumentException.class,
            () -> compiler.compile(
                new SafeRouteCompiler.RouteCommand("../admin", "catalog")));
    }

    @Test
    void rejectsUnknownTarget() {
        assertThrows(IllegalArgumentException.class,
            () -> compiler.compile(
                new SafeRouteCompiler.RouteCommand("catalog", "internal-admin")));
    }
}
~~~

This test proves **compiler behavior**—not authentication, service discovery, Gateway route binding, or runtime security. Write dedicated integration tests for those.

### Step 3 — Control-Plane Negative Test Matrix

| Action / Payload | Expected Result |
|---|---|
| `resource=../admin` | Syntax rejected |
| `resource=**` | Wildcard rejected |
| `targetCode=internal-admin` | Unapproved target rejected |
| Payload adds extra `uri=http://127.0.0.1` field | Out-of-schema field rejected |
| Payload adds arbitrary `filters` | Out-of-schema field rejected |
| Payload injects SpEL `#{@someBean}` | Raw expression rejected |
| Tenant A user edits Tenant B route | `403` from control plane |
| User tries setting `order=-999` | Rejected / no permission to set `order` |
| Attempt to register `Path=/**` | Rejected by policy |
| Attempt to use `forward:/actuator/...` | No raw URI field; rejected |
| Collision with protected route ID | Overwrite blocked |
| Two updates share the same old revision | One must fail with conflict |
| One node refresh fails | Cluster is not marked active |
| Missing/expired token calls management API | `401`/`403` per policy |
| Public request to `/actuator/**` | Not hijacked or exposed by dynamic routes |

### Step 4 — Verify Security and Filter Semantics

Execute:

~~~bash
# Public catalog read-only:
curl -i -X GET "http://localhost:8080/api/public/catalog/items/42"

# Should not match this public-read-only route:
curl -i -X POST "http://localhost:8080/api/public/catalog/items/42"

# Protected paths must not be exposed by a new route:
curl -i "http://localhost:8080/api/admin/status"
curl -i "http://localhost:8080/actuator/gateway/routes"
~~~

Exact HTTP statuses depend on your security, router, and Actuator setup; **do not expect every POST or management URL to return one fixed code**. What you must prove is that they **are never misrouted to `catalog-service` and never open unauthorized access**.

### Step 5 — Multiple Gateway Nodes and Rollback

1. Publish the new route snapshot to a canary instance.
2. Send requests directly to each identified test instance.
3. Verify route revision, path, downstream target, 401/403 behavior, and default filters.
4. Intentionally submit a config rejected by the validator; verify **no node loads the invalid config**.
5. Simulate a refresh/persistence failure; verify rollout reports failure and retains or restores a safe snapshot.
6. Revoke the route, verify it stops matching across every instance, and handle cache invalidation.

Never probe real SSRF targets or sensitive endpoints in production; use **controlled fixtures** to test policy rejections.

## 16. Layer-by-Layer Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| URI parses cleanly yet gets denied | Target outside allowlist/egress policy | Verify target permissions; never loosen policies carelessly |
| Route saves cleanly yet stays inactive | Missing refresh or node holds old cache | Compare revisions and refresh outcomes |
| One node routes right, another routes wrong | Partial rollout / config drift | Reconcile snapshots, canary, or roll back |
| Requests hit the wrong service | Route shadowing, overlapping `order`/predicates | Inspect effective routes and matching order |
| `401`/`403` after publishing | Spring Security doesn't permit the new public path | Review policy; never open global `permitAll` |
| `404` | Predicate mismatch or bad path rewrite / backend endpoint | Compare public path against downstream path |
| `503` from `lb://` | Service ID unresolved or instances unhealthy | Inspect registry, TLS, and networking |
| Filter/expression fails to resolve | Missing bean or version mismatch on factory/args | Accept only approved policies; verify runtime |
| Latency spikes on new route | Regex ReDoS, retries, body buffering, or slow backend | Disable route, profile, and check budgets |
| Identity header disappears | Dynamic filter stripped or overwrote header | Roll back and restore header trust policies |
| User B sees User A's data | Wrong caching or routed to wrong backend | Disable route/cache; handle as security incident |
| Route disappears on restart | In-memory repository or divergent sources | Add persistent store and reconciliation |
| Uncontrolled Actuator calls | Endpoint mis-exposed or missing authZ | Lock down management network, audit, revoke access |
| Concurrent edits overwrite each other | Missing revisions / optimistic locking | Serialize publishes or enforce version checks |

### Six Questions to Isolate Issues

1. **Caller:** is the actor authorized for this route, owner, and environment?
2. **DTO:** does it contain raw URIs, filters, regexes, expressions, or out-of-schema fields?
3. **Compiled `RouteDefinition`:** does it obey policy without shadowing other routes?
4. **Repository / refresh:** which Gateway nodes loaded which revision?
5. **Runtime:** which route, `order`, and outbound target did live requests match?
6. **Trust boundary:** are Spring Security, backend authZ, egress, TLS, and header policies intact?

Never debug by opening public Actuator mutation endpoints or disabling certificate verification.

## 17. Pre-Deployment Checklist

- [ ] I treat dynamic `RouteDefinition`s as **executable-privilege configuration**, not ordinary CRUD.
- [ ] I enforce granular permissions for view, propose, approve, publish, edit, delete, and rollback by owner/environment.
- [ ] I never accept raw `RouteDefinition` payloads from self-service callers.
- [ ] I use a narrow command DTO/schema and server-side `targetCode` → approved URI mapping.
- [ ] I constrain URIs, schemes, hosts, ports, and service IDs, enforced alongside DNS, TLS, and egress policies.
- [ ] I block routes from arbitrarily targeting loopback, metadata, admin endpoints, or arbitrary `forward:` URIs.
- [ ] I govern service registries and instance registration permissions for `lb://`.
- [ ] I allocate public prefixes, hosts, methods, and `order` centrally rather than letting users claim namespaces.
- [ ] I check for route shadowing across the entire route set, including discovery routes.
- [ ] I reject client-supplied raw SpEL/bean references and raw regexes.
- [ ] I allowlist both filter names **and** argument structures/bounds.
- [ ] I block filters from forging principals, roles, or tenants, or stripping security headers outside policy.
- [ ] I bound `Retry`, `CircuitBreaker`, `RateLimiter`, caching, and timeouts per policy.
- [ ] I still protect requests independently via Spring Security and backend authorization.
- [ ] I verify public paths, rewritten paths, hosts, and encoded URL edge cases.
- [ ] I enforce revision/ownership/concurrency checks with redacted audit logs.
- [ ] I never treat `RefreshRoutesEvent` as a synchronous cluster-wide commit guarantee.
- [ ] I implement canaries, reconciliation, per-node active revision tracking, and rollback.
- [ ] I lock down management/Actuator APIs using network ACLs and authentication/authorization.
- [ ] I have tested SSRF negative cases, route conflicts, config injection, header spoofing, and refresh failures.
- [ ] I monitor route change metrics, 401/403/429/5xx rates, and downstream targets while scrubbing tokens/PII from logs.
- [ ] I have a kill switch to disable dangerous routes and handle cache invalidation during incidents.

## Official References

- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — `RouteDefinition`, `GatewayFilter` factories, `DiscoveryClient` routes, Actuator, Server WebFlux, and version-specific route config.
- [Spring Cloud Gateway Project](https://spring.io/projects/spring-cloud-gateway) — release trains and selecting matching documentation.
- [Spring Framework WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html) — `ServerWebExchange`, request handling, and reactive lifecycles.
- [Spring Security Reactive Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html) — securing control-plane HTTP endpoints with `SecurityWebFilterChain`.
- [Spring Boot Actuator](https://docs.spring.io/spring-boot/reference/actuator/) — managing exposure, security, and access for management APIs.
- [OWASP SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html) — allowlists, DNS, IP, and network controls.
- [OWASP Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html) — validating inputs with schemas and allowlists.
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) — least privilege, ownership, and deny-by-default.

**Key takeaway:** **Target URIs, predicates, filters, expressions, and parameters in dynamic routes can reshape Gateway's security boundary.** Never let management users submit arbitrary executable configuration: accept narrow-schema commands, map to approved URIs and policies, block SSRF with allowlists plus egress controls, verify route conflicts and authorization, manage revisions, and confirm rollouts on every node. **A syntactically valid `RouteDefinition` is never enough to go public.**
