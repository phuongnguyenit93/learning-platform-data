# Shared Gateway, Domain Gateway, and Backend for Frontend

## 1. Why Distinguish Three Gateway Patterns?

In a microservices system, an application may have many API consumers: a website, mobile apps, an admin portal, and partners. Clients need a stable access address, while backend services are deployed, scaled, and changed independently. **Spring Cloud Gateway** provides request routing based on **route predicates**, processing through a **filter chain**, path/header modification, service discovery integration, and mechanisms such as authentication, rate limiting, circuit breakers, retries, TLS, and request observability.

However, using Spring Cloud Gateway does not mean every system must have a single gateway. There are three common ways to divide responsibilities:

- **Shared/edge gateway:** a single common entry point for multiple APIs and multiple client groups.
- **Domain gateway:** an entry point responsible for the APIs of one business domain, such as catalog, ordering, or payment.
- **Backend for Frontend (BFF):** a backend tailored specifically to the needs of one UI/client type, such as web or mobile.

These three approaches describe **scopes of responsibility**, not necessarily three technologies or three deployment layers that must always exist. A small system may use only a shared gateway; a larger system may combine a shared gateway, domain gateways, and BFFs.

### Learning Outcomes

After this lesson, you should be able to:

1. Explain the responsibilities and ownership boundaries of a shared gateway, a domain gateway, and a BFF.
2. Distinguish routing/filtering operations from UI-oriented data aggregation.
3. Sketch request flows and basic route configurations using Spring Cloud Gateway.
4. Choose an appropriate model based on client count, business domain count, API ownership, security, and operational cost.
5. Identify risks such as shared bottlenecks, misplaced business logic, duplicated policies, and increased network hops.

## 2. Shared Gateway: A Single Entry Point at the System Edge

A **shared gateway** is usually the first entry point for public APIs or client-facing internal APIs. It receives requests, evaluates route predicates to choose a route, and runs the corresponding filter chain before forwarding requests to backends.

~~~mermaid
flowchart LR
    W[Web client] --> E[Shared / Edge Gateway]
    M[Mobile client] --> E
    P[Partner client] --> E
    E -->|/api/catalog/**| C[Catalog service]
    E -->|/api/orders/**| O[Order service]
    E -->|/api/accounts/**| A[Account service]
~~~

Reasonable responsibilities for this layer include:

- **Routing:** selecting a backend by path, host, method, header, or other conditions.
- **Edge protection:** TLS termination (where appropriate for the infrastructure), edge authentication, enforcing coarse access policies, and applying rate limits.
- **Protocol handling:** normalizing paths, adding/removing trusted headers, handling CORS, attaching correlation IDs, and enforcing timeouts.
- **Edge reliability orchestration:** controlled retries, circuit breakers, and fallbacks when there is a clear reason.
- **Observability:** recording request counts, processing duration, status codes, route IDs, and tracing information.

The biggest advantage is that clients get a unified access address, while cross-cutting policies have a clear place to live. Even so, a shared gateway can become a **high-blast-radius failure point** if all requests pass through it. This requires multiple instances, load balancing, proper configuration, and independent deploy/rollback capability.

A shared gateway should keep its logic simple with minimal business coupling. For instance, rewriting **/api/catalog/products/42** to **/products/42** is a proper gateway responsibility; calculating order totals or determining refund eligibility belongs to backend business components.

## 3. Domain Gateway: An Entry Point for a Group of Business Capabilities

When a system spans multiple business domains and development teams own APIs independently, a single shared gateway can accumulate an ever-growing list of routes and domain-specific rules. A **domain gateway** groups the APIs of one domain, provides a stable access contract, and distributes requests to services within that domain.

For example, a **Catalog** domain has multiple services: products, inventory, and pricing. A Catalog domain gateway can manage the domain's routes instead of forcing the shared gateway to know every sub-service:

~~~mermaid
flowchart LR
    Client[Client] --> Edge[Shared Gateway]
    Edge -->|/api/catalog/**| CG[Catalog Domain Gateway]
    Edge -->|/api/orders/**| OG[Ordering Domain Gateway]
    CG --> PS[Product service]
    CG --> IS[Inventory service]
    CG --> PR[Pricing service]
    OG --> OS[Order service]
    OG --> FS[Fulfillment service]
~~~

A domain gateway is typically responsible for:

- Exposing the **domain's API contract**: paths, API versions, forwarding rules, and policies tailored to that API group.
- Routing to services within the same domain without exposing internal service layout to clients.
- Enforcing domain-level policies, such as access limits on a resource-intensive API group.
- Enabling the domain-owning team to deploy and change configurations independently within its contract with the edge gateway.

Important distinction: **a domain gateway does not automatically mean a new business logic layer**. It may perform only routing/filtering. If a domain needs an aggregated API or complex business logic, consider a well-scoped application service/facade rather than stuffing logic into a gateway filter.

A domain gateway provides autonomy, at the cost of an extra network hop and another service to observe, update, secure, and operate. In a small system with only a few backends and a single team, splitting out domain gateways may not yield proportional benefits.

## 4. Backend for Frontend: A Dedicated Backend per Experience

A **Backend for Frontend (BFF)** organizes APIs around the needs of a **client**, rather than the boundaries of a business domain. For example, a mobile home screen only needs thumbnails, current price, brief stock status, and up to five recommended products; a desktop website needs rich filters, comparison tables, and denser data.

Rather than forcing the client to call multiple services and assemble results itself, a **mobile BFF** can return a payload structured specifically for that screen:

~~~mermaid
flowchart LR
    Mobile[Mobile app] --> MG[Mobile BFF]
    Web[Web app] --> WG[Web BFF]
    MG --> C[Catalog service]
    MG --> I[Inventory service]
    MG --> R[Recommendation service]
    WG --> C
    WG --> I
    WG --> S[Search service]
~~~

A BFF is typically responsible for:

- **API composition:** calling multiple backends and aggregating data into a response tailored to a screen or UI flow.
- **Representation transformation:** renaming fields, trimming payloads, paginating, or formatting for web/mobile needs.
- **Reducing client round trips:** orchestrating multiple backend calls server-side, considering parallelization and timeouts.
- **Adapting to UI release cadence:** updating a response contract for one client without forcing all clients to change simultaneously.

A BFF **should not own core business rules** such as tax calculation, refund policies, or order-state decisions. Those rules must live in the appropriate business services so web, mobile, and partners receive consistent outcomes.

A BFF can be built with Spring Boot WebFlux, Spring MVC, or another backend stack. **Spring Cloud Gateway is well-suited for routing to BFFs and handling filters**, while complex data-assembly steps are usually easier to test, maintain, and observe when implemented in controllers/services of the BFF application. Therefore, **BFF is an architectural pattern**, not the name of a built-in Spring Cloud Gateway filter.

## 5. Quick Comparison by Design Goal

| Criterion | Shared gateway | Domain gateway | BFF |
| --- | --- | --- | --- |
| Who does it serve? | Multiple clients and multiple domains | Consumers of one domain's APIs | One client type or one experience |
| Partitioning axis | System edge | Business domain / bounded context | UI, device, or client group |
| Primary responsibility | Entry point, routing, cross-cutting policies | API contract and intra-domain routing | Data aggregation, filtering, transformation for UI |
| Typical owning team | Platform / infrastructure | Domain development team | Product / relevant frontend and backend team |
| Frequent changes | Edge policies, public routes | Domain internal API structure | Screen requirements, payloads, experience |
| Key benefit | Consistent access, centralized management | Domain autonomy, reduces central config | Fewer round trips, simpler clients |
| Key risk | Shared bottleneck / wide blast radius | Extra hops and duplicated policies | More backends, risk of duplicating business logic |

**Same request, classified by reason for change:** If you need a new route to forward requests to the Order service, that is routing. If Catalog needs a stable API contract for multiple client groups, consider a domain gateway. If mobile needs a response containing only fields rendered on screen, that is a BFF need.

## 6. Combining All Three in an E-Commerce System

Suppose an e-commerce platform has **web**, **mobile**, **partner APIs**, and the Catalog and Ordering domains. One option might look like this:

~~~mermaid
flowchart TB
    WEB[Web app] --> EDGE[Shared Gateway]
    MOB[Mobile app] --> EDGE
    PARTNER[Partner] --> EDGE

    EDGE -->|/web/**| WBFF[Web BFF]
    EDGE -->|/mobile/**| MBFF[Mobile BFF]
    EDGE -->|/api/catalog/**| CAT[Catalog Domain Gateway]
    EDGE -->|/api/orders/**| ORD[Ordering Domain Gateway]

    WBFF --> CATALOG[Catalog API]
    WBFF --> ORDER[Order API]
    MBFF --> CATALOG
    MBFF --> ORDER

    CAT --> CATALOG
    CAT --> INVENTORY[Inventory API]
    ORD --> ORDER
    ORD --> FULFILLMENT[Fulfillment API]
~~~

In this design:

1. Clients send requests through the shared gateway for common policy enforcement and destination selection.
2. Requests matching **Path=/api/catalog/\*\*** are routed to the Catalog domain gateway, which decides which service handles Catalog APIs.
3. Requests matching **Path=/mobile/\*\*** are routed to the mobile BFF; the BFF fetches data from backend APIs and returns a mobile-tailored response.
4. Requests matching **Path=/web/\*\*** are routed to the web BFF if web needs different payloads or aggregation flows than mobile.
5. Business backends remain responsible for resource authorization, calculations, and checking business invariants.

Calls from a BFF to backends can go directly via service discovery or through domain APIs/domain gateways depending on contracts and connectivity policies. Establish **a consistent internal call path**, avoiding accidentally looping the BFF back through the shared gateway and back into itself. Avoid chaining unnecessary hops by default.

### Request Illustration

Mobile sends **GET /mobile/home** to the shared gateway. The gateway strips the **/mobile** prefix and forwards **GET /home** to the mobile BFF. The BFF can call Catalog and Recommendation in parallel, normalize the data, and return a response such as:

~~~json
{
  "featuredProducts": [
    {
      "id": "P-42",
      "name": "Water bottle",
      "thumbnail": "/images/P-42-small.webp",
      "displayPrice": "199,000 VND",
      "available": true
    }
  ],
  "recommendations": [
    { "id": "P-81", "name": "Sports bag" }
  ]
}
~~~

In this example, the BFF decides **how data is presented** for mobile; Catalog/Pricing/Inventory still decide whether product data, prices, and stock levels are valid.

## 7. Illustrative Route Configuration with Spring Cloud Gateway

A shared gateway using Spring Cloud Gateway Server WebFlux can route based on the **Path predicate** and **StripPrefix filter**:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-domain
          uri: lb://catalog-gateway
          predicates:
            - Path=/api/catalog/**
          filters:
            - StripPrefix=2

        - id: ordering-domain
          uri: lb://ordering-gateway
          predicates:
            - Path=/api/orders/**
          filters:
            - StripPrefix=2

        - id: mobile-bff
          uri: lb://mobile-bff
          predicates:
            - Path=/mobile/**
          filters:
            - StripPrefix=1

        - id: web-bff
          uri: lb://web-bff
          predicates:
            - Path=/web/**
          filters:
            - StripPrefix=1
~~~

Meaning of the example:

| Initial Request | Selected Route | Path Forwarded to Target |
| --- | --- | --- |
| GET /api/catalog/products/42 | catalog-domain | /products/42 |
| GET /api/orders/123 | ordering-domain | /123 |
| GET /mobile/home | mobile-bff | /home |
| GET /web/dashboard | web-bff | /dashboard |

**Note on path contracts:** If the internal Ordering API expects **/orders/123**, strip only part of the prefix or use an appropriate rewrite; the example deliberately strips all of **/api/orders** to demonstrate how **StripPrefix=2** works. Internal paths must match actual controllers/backends. Likewise, do not apply StripPrefix mechanically to every route.

In the example, the **lb://** URI prefix requires a service-name resolution and load-balancing mechanism, such as Spring Cloud LoadBalancer paired with a configured discovery client. If you are not using service discovery yet, you can route to a static HTTP address in a test environment:

~~~yaml
uri: http://localhost:8081
~~~

**Version differences:** Gateway Server WebFlux configuration namespaces may change across Spring Cloud Gateway versions; some newer lines use **spring.cloud.gateway.server.webflux.routes** instead of **spring.cloud.gateway.routes**. When implementing, check the documentation for your exact Spring Cloud version and distinguish **Server WebFlux** from **Server Web MVC**; the example above illustrates common Gateway WebFlux syntax.

The Catalog domain gateway can further route from the domain contract to concrete services:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-products
          uri: lb://product-service
          predicates:
            - Path=/products/**

        - id: catalog-stock
          uri: lb://inventory-service
          predicates:
            - Path=/stock/**
~~~

This separates responsibilities: the shared gateway knows **which domain to go to**; the Catalog domain gateway knows **which service within the domain**. If an intermediate layer is not needed yet, the route on the shared gateway can point straight to the Product service.

### When Do You Need BFF Logic Instead of Adding Filters?

For example, mobile needs both featured products and recommendations together. A BFF application using a reactive client can express the aggregation idea in Java pseudocode:

~~~java
// Illustrative snippet inside Mobile BFF's service;
// productClient and recommendationClient are adapters calling backends.
Mono<MobileHomeResponse> loadHome() {
    Mono<List<ProductCard>> products = productClient.featured(5);
    Mono<List<RecommendationCard>> suggestions =
            recommendationClient.forHome();

    return Mono.zip(products, suggestions)
            .map(data -> new MobileHomeResponse(
                    data.getT1(),
                    data.getT2()
            ));
}
~~~

This is an **illustrative snippet**, not a complete runnable class. In a real application, you must add DTO contracts, proper identity propagation, timeouts, concurrency limits, error handling, and tests. **Mono.zip** waits for both results; if one source fails, the entire combination fails by default. If the UI tolerates missing recommendations, a fallback must be **deliberately** designed for that part alone.

## 8. Defining Authentication, Authorization, and Security

Splitting into multiple gateways does not change an essential principle: every request must pass through appropriate controls, and services handling resources must still protect those resources.

| Layer | Typically Appropriate Security Responsibilities |
| --- | --- |
| Shared gateway | Edge TLS per deployment design, token validation, global rate limiting, CORS, stripping spoofed external headers |
| Domain gateway | Access rules by API/domain group, dedicated limits for sensitive or resource-heavy APIs |
| BFF | Session or token management tailored to client type, response data minimization, preventing leakage of data unneeded by UI |
| Business service | Object/resource-level permission checks, business constraints, data access control |

Practical rules:

- **Authentication at the gateway does not replace authorization at the service.** Having a valid token does not mean a user can view someone else's order.
- **Do not trust client-supplied identity headers** such as **X-User-Id**. If the architecture uses internal headers, the edge layer must strip external values and set verified identity itself; internal connections must have a clear trust boundary.
- **Tokens/sessions need a consistent policy.** A BFF can hold sessions for browsers and call backends on the client's behalf, but it must protect cookies/tokens, guard against CSRF when using cookie-based authentication, and grant only necessary permissions.
- **TLS and internal identity** must match the infrastructure. Terminating TLS at an external proxy does not mean downstream connections are inherently secure.
- **Never log access tokens, cookies, passwords, or sensitive data** in access logs or traces.

If the same rule is configured across multiple gateways, specify clearly which layer is the policy source and which performs supplemental protection. For instance, you might cap overall requests at the edge and apply a stricter limit on an expensive search endpoint at the domain gateway; the two limits serve different purposes.

## 9. Reliability, Performance, and Observability

Every gateway adds one processing step, one network hop, and one more place where a timeout can occur. Splitting into multiple layers should therefore be justified by governance and API contract benefits, while measuring actual impact.

**Timeouts and retries:** Allocate a timeout budget across the entire request; if the shared gateway, domain gateway, and BFF each retry multiple times independently, backend traffic can surge sharply during an outage. Only retry recoverable errors and safe/idempotent operations, or operations protected by deduplication such as an idempotency key. For payment/order creation, never arbitrarily enable POST retries.

**Circuit breakers and fallbacks:** Circuit breakers help limit the blast radius of failing backends. Fallbacks must preserve semantics: a home page may omit recommendations when Recommendation is unavailable, but must never return fake prices or balances to mask critical service failures. Fallback decisions often require business context, making them a better fit in a BFF/application service than a generic fallback across all routes.

**Rate limiting:** The edge typically protects system-wide resources; a domain gateway can set dedicated quotas for an API group. When running multiple instances, shared state is required to enforce cluster-wide quotas. Consider keying rate limits by user, client, or verified identifier, avoiding total reliance on IP addresses behind NAT.

**End-to-end observability:** Tracing should link requests across the edge, domain gateways, BFFs, and backends via trace context. Key metrics to watch include:

- Request count, **4xx/5xx** error rates, and **p50/p95/p99** latency by route.
- Requests rejected by rate limiters, timeouts, circuit breakers, retries, and fallbacks.
- Inbound/outbound throughput, connection pool usage, and CPU/memory resources per gateway.
- Latency and error rate of each backend call inside a BFF, even when the aggregated response still returns **200**.

Avoid turning user IDs, tokens, or paths containing arbitrary IDs into high-cardinality metric labels; use stable route names and appropriate trace attributes.

## 10. Choosing an Architecture Based on Real Needs

You can start with a single shared gateway when the engineering team is small, backends are few, and APIs do not yet require independent contracts. Add a new layer only when you clearly know **who owns it**, **what problem it solves**, and **how to measure its benefit**.

| System Signal | Direction to Consider |
| --- | --- |
| A few services, small teams, mainly needing routing/TLS/auth | Shared gateway with clear routes |
| Multiple domains with independent API contracts and release cycles | Shared gateway combined with domain gateways where autonomy is needed |
| Web and mobile need different payloads/release schedules, clients make too many API calls | BFF for experiences with distinct needs |
| Web/mobile share nearly identical APIs and data | No need to split a BFF just because two client types exist |
| Complex business policies must stay consistent across all clients | Keep in domain/application services; gateway mainly handles protocol policies |
| Many hops with no clear observable benefit | Measure latency and operational complexity, and consider consolidating layers |

A pragmatic decision sequence:

1. **Need a stable entry point and edge policies?** Use a shared gateway.
2. **Does a domain have multiple services and an owning team needing independent API changes?** Consider a domain gateway for that domain.
3. **Does a UI type need custom data aggregation/transformation?** Consider a BFF for that experience.
4. **Is the logic just added actually a core business rule?** Move it back to the domain service and re-check ownership boundaries.
5. **Do the benefits outweigh the cost of a new deployable layer?** Evaluate via release velocity, latency, request volume, error rates, and operational effort.

### Anti-Patterns to Avoid

**God gateway:** A single gateway containing all business rules, data joins, resource authorization, and error handling for every domain; it creates a dependency bottleneck for all development teams.

**Domain gateway just to add a hop:** Adding an intermediate service without a clear independent contract, policy, or ownership boundary.

**BFF duplicating business logic:** Web BFF and mobile BFF independently calculating prices/taxes/promotions differently, producing inconsistent results.

**Self-looping gateway chain:** A BFF calling the shared gateway via a public route that points back to the BFF, causing loops or uncontrolled hop inflation.

**Load-amplifying retries:** Multiple layers all retrying, sending even more requests to an overloaded backend; lacking an overall timeout budget and retry monitoring.

## 11. Design and Verification Practice

**Context:** You have a Product service, Inventory service, Order service, website, and mobile app. Mobile needs an endpoint returning featured products with stock availability; partners need an API to access orders. The system uses Spring Cloud Gateway to protect the entry point and route requests.

### Part A — Minimal Design

1. Start with a shared gateway. Declare two routes **Path=/api/products/\*\*** and **Path=/api/orders/\*\*** pointing to their respective backends, specifying clearly what path the service receives.
2. Design a **/mobile/home** route pointing to a mobile BFF. The BFF calls Product and Inventory and aggregates a response containing only fields mobile needs.
3. Ensure the rules determining whether a product can be sold remain in the responsible business service, not in the BFF.

### Part B — Scaling as Services Grow

When the Catalog domain grows to include Product, Inventory, Pricing, and Search services managed by a separate team, evaluate adding a Catalog domain gateway. If you decide to split, define the public contract, internal routes, configuration owners, security standards, timeouts, and dedicated dashboards. Keep client contracts unchanged if possible.

### Part C — Behavior Verification

| Case | Expected Outcome |
| --- | --- |
| Call **GET /mobile/home** | Edge selects mobile BFF; response reflects the mobile contract |
| Call **GET /api/products/42** | Routes to the right backend, path rewrite/strip works accurately |
| Missing or invalid token | Request is rejected per authentication policy |
| User A reads User B's order | Business service denies due to missing permission on the resource |
| Recommendation/Inventory is slow | Timeout and fallback match data semantics; trace available for investigation |
| Sending requests exceeding quota | Rate limiter responds as configured without overloading backends |
| One gateway instance goes down | Infrastructure still routes requests through healthy instances if HA is configured |

When testing, cross-check the **initial request URL**, **selected route ID**, **forwarded URL**, **trusted headers**, **status code**, and **trace**. That provides direct evidence that the gateway/BFF boundaries behave as designed.

## 12. Takeaways

- **Shared gateway** organizes the common entry point and cross-cutting policies; typically the first hop clients hit.
- **Domain gateway** organizes APIs by business domain and ownership; only useful when there is a corresponding need to separate contracts/policies/deployments.
- **BFF** organizes APIs by client experience; focuses on aggregating and shaping data and reducing client round trips.
- **Spring Cloud Gateway** handles routing, predicates, filters, and gateway-layer capabilities; BFF applications can use other Spring components to implement aggregation logic.
- A system can combine all three, but must clearly design request flows, trust boundaries, timeouts, retries, authorization, and observability. Adding an architectural layer is justified only when it solves a real need and its cost is measured.
