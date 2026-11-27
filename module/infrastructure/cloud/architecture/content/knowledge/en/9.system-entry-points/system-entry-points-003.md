# Host, Path, Geographic, and Latency-Based Routing

When a user accesses a cloud application, each request passes through one or more **system entry points** before reaching the right service. A single domain can serve web pages, APIs, images, and an admin console. Users across multiple geographies may need an entry point close to them, yet not every request is permitted to be processed everywhere. If one cluster fails, the system must know where to shift traffic and how data will be available there.

These questions lead to four fundamental routing approaches:

- **Host-based routing:** routes by target domain name such as **app.example.com** or **api.example.com**.
- **Path-based routing:** routes by the URL path component such as **/api/bookings** or **/static/**.
- **Geographic routing:** routes by inferred origin location, policy region, or defined target geography.
- **Latency-based routing:** selects the destination expected to offer better network response time based on latency signals supported by the routing platform.

These methods are typically **layered together across tiers**, not four mutually exclusive options. A system may choose an edge near the user, select a service by host/path, and then route write operations to the region authoritative for the data.

This lesson belongs to the **System Entry Points** chapter of the **CLOUD_ARCHITECTURE** module. Its goal is to design entry points and network flows from business requirements while balancing reliability, security, performance, scalability, cost, and operations under Well-Architected principles.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish the roles of DNS, CDN/edge, global traffic manager, load balancer, reverse proxy, API gateway, and ingress controller in a request flow.
2. Design hostname and path routing rules, including precedence, rewrites, default routes, and unmatched-route handling.
3. Explain the differences between geographic routing, latency-based routing, Anycast, and health-based load balancing.
4. Align routing with session requirements, data consistency, RTO/RPO, data sovereignty, and multi-region resilience.
5. Identify security risks such as Host spoofing, trusting unverified forwarded headers, path normalization bypasses, and unauthorized access to admin endpoints.
6. Test routing configurations, measure regional service quality, and build failover plans backed by operational evidence.

## 2. Which Tiers Does a Request Traverse?

A typical cloud web architecture includes the following layers:

~~~mermaid
flowchart LR
    U[User / Client] --> DNS[DNS / Traffic policy]
    DNS --> EDGE[CDN / WAF / Global entry]
    EDGE --> LB[Load balancer / Reverse proxy]
    LB --> GW[API Gateway / Ingress]
    GW --> WEB[Web service]
    GW --> API[API service]
    API --> DATA[(Database / Cache)]
~~~

This is a logical diagram. A real product may combine CDN, WAF, global load balancing, and L7 routing into one service; an internal system may omit a CDN. Do not assume every request passes through the exact number of layers drawn here.

| Tier | Information Available for Decisions | Example Outcome |
|---|---|---|
| **DNS / traffic manager** | Queried domain; weighted, geo, latency, or endpoint health policies depending on features | Returns an IP or target name for a region |
| **Anycast / global network / edge** | Network path, nearby/available PoPs, provider policies | Directs connection to an ingress point on the global network |
| **Layer 4 (L4) load balancer** | IP, port, TCP/UDP, and health signals | Distributes connections across healthy targets |
| **Reverse proxy / Layer 7 (L7) load balancer** | HTTP Host, path, method, headers, and supported HTTP policies | Sends **/api/** to API service, **/assets/** to static service |
| **API gateway / ingress** | Route, auth, quota, version, tenant, and app policies | Validates authorization, enforces rate limits, forwards to right backend |
| **Application** | Business rules, user permissions, and data state | Confirms booking, checks availability, selects data shard |

**L4 cannot natively read or parse HTTP paths.** Conversely, for L7 to inspect hostnames and paths in HTTPS traffic, the platform generally must terminate TLS at an appropriate point or support protocol handling per the chosen design.

### 2.1. One Request Involves Multiple Routing Decisions

Suppose a client calls **https://api.example.com/v1/bookings/123**. The system may make several sequential decisions:

1. The resolver looks up the target address of **api.example.com** under the active DNS policy.
2. Connection reaches the edge or load balancer; the TLS certificate is verified.
3. The proxy inspects hostname **api.example.com**, then matches path **/v1/bookings/123**.
4. The gateway authenticates the caller and maps the request to the Booking API.
5. The Booking API enforces permissions and determines where authoritative data resides based on tenant, storage policy, and consistency needs.

The decision in step 1 does not guarantee step 5 executes in the same country. Edge-to-origin, API-to-database, and third-party service paths must be designed and verified separately.

## 3. Host-Based Routing

### 3.1. Hostname Selects the Application or Tenant

Host-based routing relies on the hostname requested by the client. In HTTP/1.1, this is typically carried in the **Host** header; in HTTP/2 and HTTP/3, URL authority is represented by the **:authority** pseudo-header.

| Requested Host | Candidate Target Service | Purpose |
|---|---|---|
| **www.example.com** | Web frontend | Public site |
| **api.example.com** | Public API gateway | Mobile/web API endpoint |
| **admin.example.com** | Admin gateway | Privileged operations UI and API |
| **files.example.com** | Download service / object CDN | Static assets and controlled file downloads |
| **customer-a.example.com** | Tenant frontend or tenant route | Customer-specific experience if multi-tenant policy permits |

Example L7 rule set:

~~~text
IF host == "www.example.com"   -> web-frontend
IF host == "api.example.com"   -> public-api-gateway
IF host == "admin.example.com" -> admin-gateway
ELSE                           -> 404 or reject undeclared host
~~~

This is **routing policy pseudocode**, not a configuration meant to be applied verbatim to a specific cloud provider.

### 3.2. TLS SNI and HTTP Host Serve Different Roles

With HTTPS, clients typically send **Server Name Indication (SNI)** during the TLS handshake so the receiver can choose the appropriate config/certificate. HTTP Host or :authority is processed later at the HTTP layer. They often match, yet **you must never assume they always match**.

Architects must verify:

- Does the certificate cover all public hostnames in use; does TLS terminate at edge, ingress, or backend?
- Which proxy tier reads Host, which forwards SNI, and does Host get rewritten when calling the origin?
- What policy handles requests with an undeclared Host or a Host mismatched with the TLS session?
- Could an overly broad default rule inadvertently let a public hostname reach an internal backend?

The Host header is **client-supplied input**. Never use it alone as proof that the client is authenticated or authorized for a tenant. If hostnames identify tenants, validate the tenant mapping against the logged-in identity and requested data.

### 3.3. Exact Hosts, Wildcards, and Default Routes

A wildcard such as **\*.example.com** is convenient for multi-tenant subdomains, but precedence between specific hostnames and wildcards must be explicit. Invalid domains must be explicitly rejected. Never configure a default backend that accidentally falls back to an admin or internal service.

Details to align on: hostname casing (DNS names are case-insensitive), ports included in authority, internationalized domain names (IDNs), trailing dots, and unprovisioned hostnames. Rely on the actual normalization behavior of your project's gateway and verify it with tests.

## 4. Path-Based Routing

### 4.1. Paths Split One Domain into Multiple Functional Groups

Within the same domain **app.example.com**, the system can select targets by URL path:

| Path Rule | Backend | Notes |
|---|---|---|
| **/** (exact) | Landing page | Homepage only |
| **/app/** (boundary-aware prefix) | Web frontend | Customer application |
| **/api/bookings/** | Booking API | Reservation workflows |
| **/api/listings/** | Listing API | Property/item catalog |
| **/assets/** | Static origin/CDN | Static content cached per policy |
| **/internal/** | Reject at public gateway | Never rely on secret paths as security |

Matching precedence across **exact**, **prefix**, and **regular expression** rules varies by proxy/ingress. When a longer, more specific route exists, verify it is not swallowed by an earlier generic rule.

### 4.2. Pitfalls in Path Matching

1. **Overly broad prefixes:** prefix **/api** may also match **/apix** in naive string matching. Use segment-aware matching, or explicitly separate **/api/** and **/api** by convention.
2. **Trailing slashes:** **/api/bookings** and **/api/bookings/** may behave differently; decide whether to redirect, rewrite, or accept both.
3. **URL encoding and normalization:** **%2F**, **..** segments, **//**, Unicode characters, or case variations can be interpreted differently by CDN, WAF, proxy, and backend. Align normalization rules and test against bypasses.
4. **Query strings:** **/search?q=room** has path **/search**; query parameters affect app logic or cache keys, not typical path routing rules.
5. **HTTP methods:** GET and POST on the same path carry different semantics. Separate routes and enforce authorization by method where needed; never infer write permission from path alone.
6. **Rewrites:** a gateway may receive **/api/v1/bookings** and forward **/v1/bookings** to the backend. Both sides must agree on base paths to avoid broken redirects, bad asset URLs, or missing log context.

Example policy:

~~~text
Host: api.example.com

1. exact /healthz                  -> health-handler (minimal response payload)
2. prefix /v1/bookings/            -> booking-api
3. prefix /v1/listings/            -> listing-api
4. prefix /v1/                    -> api-not-found
5. fallback                       -> 404
~~~

Do not assume a public health endpoint replaces internal health checks; an endpoint returning 200 without verifying critical dependencies can keep traffic flowing to a broken backend.

### 4.3. Separate Routing from Access Control

A rule routing **/admin/** to the admin service does not mean only administrators can call it. Enforce authentication and authorization at the appropriate layers, including backend checks on sensitive operations. Proxies can pre-authenticate requests, yet service owners remain responsible for protecting business permissions.

In multi-tenant APIs, path or host routing can pick the right service, while the backend must still verify access to every resource and tenant; never trust client-supplied tenant IDs.

## 5. Geographic Routing

### 5.1. Whose Location Is Actually Measured?

A DNS traffic manager often uses the **recursive DNS resolver's** IP address to infer the requester's region; some systems use **EDNS Client Subnet (ECS)** when present and supported. Hence, DNS-inferred location is not always the end-user device's actual location.

At an edge or proxy, platforms estimate location from the **connecting IP address**. Results can still be wrong due to VPNs, proxies, CGNAT, corporate networks, roaming, stale geolocation databases, or users near geographic borders.

| Decision Point | Typically Available Location Data | Caveats |
|---|---|---|
| DNS resolver / traffic policy | Resolver IP, sometimes client subnet via ECS | Not precise user coordinates; DNS caching affects outcomes |
| CDN / edge | Client IP seen at edge, IP geolocation DB | IP may belong to VPN/proxy; predictions vary |
| Application | Verified address/account or user-selected region, plus IP | Requires privacy policy, verification, and conflict resolution |
| Data processing system | Tenant attributes, data classification, approved residency policy | This is the authoritative layer for residency/sovereignty rules |

### 5.2. When Is Geographic Routing Useful?

- Serving market-specific UI, language, or localized content.
- Selecting frontend/edge locations close to users.
- Directing users to regional support centers.
- Partially supporting customer segmentation policies when paired with explicit definitions and checks.
- Controlling regional feature availability, such as launching a feature only in specific countries.

**Never rely on IP geolocation as the sole mechanism for data compliance.** Where a request originates does not dictate where data may be stored or processed. Data flows onward to origins, replicas, backups, logs, and third-party processors.

### 5.3. Geographic Routing Differs from Data Residency Constraints

Suppose a customer belongs to a tenant whose data policy requires storage in an approved region, while a user from that tenant is traveling abroad. Routing to the nearest IP edge may land on an overseas PoP. Your design must distinguish:

- **Connection termination and caching:** the edge handles TLS, WAF, and public content; scrutinize caching of sensitive data carefully.
- **Business data processing:** APIs/backends may need to execute only within compliant regions.
- **Data, log, and backup storage:** must obey per-classification residency rules.
- **Remote access:** operational and sub-processor access controls may apply beyond simple region names.

If no compliant target region is available, never automatically fail over to an arbitrary healthy region. Enforce approved fallback behavior: fail over to an approved standby region, degrade gracefully, or reject the operation temporarily.

### 5.4. Geographic Routing and Geoproximity Are Not Identical

Some platforms distinguish:

- **Geolocation:** rules based on configured countries, continents, or geographic areas.
- **Geoproximity:** rules based on physical distance to resource locations, sometimes with adjustable bias/radius.
- **Latency-based:** rules based on estimated or measured network latency to endpoints.

Shorter physical distance **does not guarantee** lower network latency: Internet routing, peering, fiber cuts, and network congestion can make a farther endpoint respond faster.

## 6. Latency-Based Routing

### 6.1. Purpose and Signal Sources

Latency-based routing selects the endpoint the platform expects to yield better latency for the requester's network region. Platforms may rely on historical measurements, global network probes, or operator-supplied metrics. Algorithms and coverage vary by CSP and product.

Unlike **weighted** load balancing, it does not primarily maintain fixed traffic percentages. Unlike **geographic** routing, it does not rely strictly on geographic borders. Nor is it a live per-request latency measurement at the instant each request is sent.

### 6.2. Low Network Latency Does Not Guarantee Fast Transactions

End-to-end task latency comprises multiple components:

~~~text
User-perceived time ~ DNS / connect / TLS
                     + client -> entry point
                     + entry point -> backend
                     + backend -> database / dependencies
                     + application processing
                     + response transfer / client rendering
~~~

This additive model helps reason about the request path, **not as an exact formula for every app**; parallelism, streaming, caching, and pipelining change total timing.

Illustrative example: Edge A sits close to the client with a 20 ms hop to its API, yet that API queries a distant DB adding 180 ms. Edge B sits farther at 80 ms, yet its local backend and DB add only 15 ms. For DB-bound calls, path B **may** respond faster overall. Decisions must rely on end-to-end p50/p95/p99 measurements, not RTT to the edge alone.

### 6.3. Combining Latency with Health and Policy

A practical routing policy should check in order:

1. Is the endpoint within the **allowed** set for this data type and tenant?
2. Is the endpoint **healthy** under meaningful checks?
3. Does the endpoint have adequate **capacity/quota** below load limits?
4. Do the latency metrics actually apply to this request class?
5. Will shifting targets break session affinity or read-after-write consistency?

Only after passing those filters should you prefer the lowest-latency endpoint. Otherwise, a "fast" region lacking required data or legal authorization can cause severe failures.

### 6.4. Do Not Confuse Latency Routing with Autoscaling or Failover

Latency routing does not spin up new instances under load, recover databases, or guarantee safe region failover. Those responsibilities belong to autoscaling, load balancing, health checks, replication, DR planning, and application workflows.

A design may use a global traffic manager to pick a region and a regional load balancer to distribute traffic across healthy instances. Specify behavior when **all compliant regions are unhealthy**: return controlled errors, enter degraded mode, or execute manual DR per runbook rather than violating data policies.

## 7. Combining All Four Routing Methods in One System

### 7.1. Decision Order Should Start from Hard Constraints

There is no single fixed physical sequence across every provider: DNS/Anycast may pick an edge before L7 reads Host/path, and the app may verify tenant afterward. Yet for **architectural design**, layer decisions logically:

1. **Endpoint identity and protocol:** allowed domains, TLS, Host/path normalization, rejecting invalid targets.
2. **Business capability:** route by host/path/method and enforce authn/authz requirements.
3. **Data and tenant scope:** restrict eligible origins/regions for the specific request.
4. **Health and capacity:** exclude failing, saturated, or dependency-impaired targets.
5. **Distribution optimization:** among valid targets, optimize for location, latency, weights, cost, or canary versions.
6. **Post-routing verification:** measure latency and transaction outcomes; apply retries/fallbacks per business rules.

At tiers operating before request decryption or tenant authentication, routing decisions are **provisional**. Gateway/application rules must enforce hard data constraints once full context is known.

### 7.2. Sample Policy Table

Suppose a booking platform has three data classes: public images, cacheable search, and booking transactions requiring strict data governance.

| Host + Path | Logical Backend | Geo/Latency Policy | Notes |
|---|---|---|---|
| **www.example.com/** | Web frontend | Serve from appropriate CDN/edge | Cache public assets per policy |
| **www.example.com/assets/** | Object storage via CDN | Edge near client | Verify purges, cache keys, access controls |
| **api.example.com/v1/search/** | Search API | Select healthy low-latency region from allowed list | Results may lag authoritative source slightly if SLA permits |
| **api.example.com/v1/bookings/** | Booking API | Authoritative tenant/data region; HA per design | Requires idempotency, state consistency, DR |
| **admin.example.com/** | Admin gateway | Protected endpoints only; never open broadly by IP geo | SSO/MFA, authz, audit, network restrictions as appropriate |
| Invalid host or path | Deny/default | Never fall back to sensitive backends | 404/403/421 per protocol and deployment policy |

### 7.3. Combined Architecture Diagram

~~~mermaid
flowchart TB
    U[Clients across regions] --> G[DNS / Anycast / Global entry]
    G --> EDGE[Edge: TLS / WAF / Host + Path]
    EDGE -->|www / assets| CDN[CDN + Static origin]
    EDGE -->|api / search| SR[Search routing]
    EDGE -->|api / bookings| BR[Booking routing]
    EDGE -->|admin| ADMIN[Controlled admin gateway]
    SR --> POLICY{Target allowed and healthy?}
    POLICY -->|Yes| FAST[Search API in eligible region]
    POLICY -->|No| DEG[Degraded mode / controlled error]
    BR --> TENANT[Authz + tenant / data policy]
    TENANT --> ALLOWED{Region allowed + healthy?}
    ALLOWED -->|Yes| BOOK[Booking API + authoritative data]
    ALLOWED -->|No| DR[Approved DR / return error]
    FAST --> READ[(Search index / read model)]
    BOOK --> DB[(Booking database)]
~~~

This diagram is logical. An edge cannot deduce tenant permissions from domain/path alone. Tenant validation and data policy enforcement must happen in a component holding trusted context before restricted destinations process data.

### 7.4. Illustrative Policy Configuration

~~~yaml
# YAML-style pseudocode, NOT directly applicable to a specific ingress.
virtualHosts:
  - host: www.example.com
    paths:
      - match: /assets/*
        backend: static-origin
        cachePolicy: public-assets
      - match: /*
        backend: web-frontend
  - host: api.example.com
    paths:
      - match: /v1/search/*
        backend: search-router
        regionPolicy: allowed-healthy-low-latency
      - match: /v1/bookings/*
        backend: booking-router
        regionPolicy: tenant-authoritative-region
  - host: admin.example.com
    paths:
      - match: /*
        backend: protected-admin
        authentication: required
defaultAction: reject-unknown-host
~~~

When translating into real configs, verify syntax, wildcard support, match precedence, path rewrites, authentication hooks, and regional policy enforcement in your chosen product. Never ship pseudocode to production as a finished configuration.

## 8. Decisions Involving State and Consistency

### 8.1. Session Affinity Is Not the Answer to All State

Some apps store sessions in process memory and rely on sticky sessions to keep users pinned. That may seem simple short-term, yet when an instance or region fails, sessions vanish. Consider properly signed cookies, shared state stores with scoped permissions, or stateless auth tokens where requirements allow.

Sticky sessions can also skew load; never use them to mask an unrecoverable dependency on local in-memory state.

### 8.2. Reads and Writes May Require Different Policies

An API reading item listings can serve from a cache or nearby read replica; a booking write must prevent double-booking. Therefore:

- **Reads:** can tolerate slight staleness if UX and API contracts permit; define TTLs and invalidation rules.
- **Writes:** must reach an authoritative writer with concurrency controls and idempotency keys to prevent duplicate mutations on retry.
- **Read-after-write:** if users must immediately see a booking they just submitted, read from the authoritative source or wait for projections to reach the required version.

Routing writes to the "nearest" region can increase lock contention, add cross-region DB hops, or create hard-to-reconcile distributed writes. Design for transaction correctness first, then optimize latency.

### 8.3. Retries and Failover Must Respect Request Semantics

Idempotent GETs by contract are safer to retry, though infinite retry loops must still be prevented. A payment or booking POST may have already committed at the backend even if the response was lost; retrying into another region risks creating duplicate transactions unless idempotency spans all candidate targets.

Across multi-region routing, specify clearly: who generates idempotency keys, their validity scope, where results are persisted, retention duration, reconciliation logic, and when write failover is permitted.

## 9. Availability, Health Checks, and Recovery

### 9.1. Health Checks Must Measure the Right Level

| Level | What It Can Verify | What It Cannot Prove Alone |
|---|---|---|
| TCP / TLS | Target accepts connections; certs/protocols work | API returns valid results or DB is reachable |
| HTTP /ready | App initialized and ready for some traffic | End-to-end booking workflow succeeds |
| Synthetic transaction | Simulated safe business flow succeeds | All request types and peak loads are healthy |
| Production SLIs | Success rate, p95/p99, errors per host/path/region | System can survive total loss of a region |
| DR exercise | Traffic shifts and data recovers per test scenario | Every conceivable future outage is covered |

A backend might return 200 on **/healthz** while its Booking DB is unreachable. If a global traffic manager relies solely on shallow health endpoints, traffic keeps flowing to a region unable to complete transactions.

### 9.2. DNS Failover Has Its Own Latency

Updating a DNS record does not move all clients immediately. Resolvers and clients cache records up to TTL; network conditions, open connections, and non-compliant DNS caches also affect shift timing. Shorter TTLs help in some cases, yet increase query volume and **never guarantee** RTO.

With Anycast or global proxies, ejecting an unhealthy backend can be faster in certain topologies, though true failover duration still depends on data, capacity, check intervals, and connection draining. Only live drills reveal actual recovery times.

### 9.3. Multi-Region Does Not Automatically Equal Highly Available

To fail over across regions while keeping transactions valid, you need:

- Standby region **legally/policy-approved** to process the data.
- Compute, configs, secrets, identities, and quotas ready or fast to launch.
- Database replicas or backups meeting business RPO/RTO with post-failover consistency checks.
- DNS/global routing rules reflecting whether the new region is genuinely serving.
- Handling for in-flight requests, duplicate messages, and payment/booking reconciliation.
- Runbooks, on-call responders, error telemetry, and a failback plan once the primary recovers.

Single-region multi-AZ HA and cross-region DR address different failure domains. Select based on failure scope and business criticality.

## 10. Entry-Point Security and Trust Boundaries

### 10.1. Host and Path Are Routing Inputs, Not Access Credentials

A reverse proxy uses hostname or path to pick a service, yet attackers can craft requests with arbitrary Host/path values. Therefore:

- Accept only registered hostnames; enforce a safe default route.
- Validate TLS certs/SNI/Host per gateway capabilities; never build password-reset URLs, callbacks, or redirects from an unvalidated Host header.
- Trust **X-Forwarded-For, X-Forwarded-Host, Forwarded** only from explicitly configured trusted proxies; never let clients assert privileged IPs or schemes.
- Align path normalization/decoding across CDN, WAF, proxy, and backend; test ambiguous paths.
- Enforce authn/authz on admin APIs and per business resource at the backend layer.
- Apply TLS, WAF, rate limiting, and request size limits commensurate with risk; monitor anomalous traffic.

If a CDN permits direct origin access, edge WAF/routing rules can be bypassed. Lock down origin access via proper network/identity controls rather than relying solely on a spoofable header.

### 10.2. Geo-Blocking Is Not Identity Control

Blocking traffic from a given country may reduce abuse exposure for certain workloads, yet IP geolocation is imprecise and trivially bypassed via VPNs/proxies. Never substitute inferred country for authentication, authorization, or data protection policies.

### 10.3. Protecting Caches and Private Data

At the CDN, verify which host, path, query, and header fields form the **cache key**, especially for responses tied to accounts or cookies. A misconfigured cache key or cache policy can serve one user's response to another. Cache only shareable content per policy; for sensitive data, enforce private/no-store headers or validated, tested rules.

## 11. Observability, Testing, and Routing Incident Response

### 11.1. Tie Metrics and Logs to Routing Decisions

Useful signals:

| Category | What to Record / Monitor | Helps Detect |
|---|---|---|
| Routing | Normalized host, route ID, backend ID, target region/zone, policy version | Traffic hitting wrong service or region |
| Performance | p50/p95/p99 latency, TTFB, upstream connect time, retry count | "Nearby" route hitting a slow backend |
| Business quality | Booking creation success rate, login failures, search failures | Healthy proxy masking broken core flows |
| Health & capacity | Healthy targets, saturation, queue depth, quotas, autoscaling | Capacity shortfall or overload on failover |
| Data | Replica lag, processing region, policy denials, unexpected data flows | Routing incompatible with consistency/sovereignty |
| Security | Unknown hosts, blocked paths, WAF actions, auth failures, rate limits | Scanning, bypass attempts, access anomalies |
| Cost | CDN requests, cache-hit ratio, inter-region transfer, egress | Overly distant routes or poor caching |

Never log tokens, card details, sensitive payloads, or raw full IPs without an approved purpose and policy. Keep metric label cardinality bounded; never put bookingId or userId into metric labels, which causes time-series explosion.

### 11.2. Route Testing Matrix

| Test | Expected Outcome | Verification Method |
|---|---|---|
| Valid web and API hosts | Right backend, valid certificate | HTTPS calls to each hostname; inspect route ID/logs |
| Undeclared host | Rejected; never reaches admin/internal backends | Request with unknown hostname in test env |
| Exact and prefix paths | **/api/** and **/apix** do not collide | Test suite for exact/prefix, slashes, encoded paths |
| Rewrites and queries | Backend receives URI matching contract | Integration tests and gateway→backend traces |
| Unauthorized requests | 401/403 with no data leak | Test across tenants/roles, including direct origin checks |
| Multi-region requests | Lands in policy-compliant region with measured latency | Probes from real regions; inspect trace/region tags |
| Unhealthy region or endpoint | Shifts to valid target or returns clean error | Simulate backend outage; measure failover and RTO |
| POST retry after timeout | No duplicate transaction created | Test idempotency, reconciliation, and final state |
| CDN caching | Public assets cached; private data never leaked | Check cache headers/keys across multiple accounts |

Example host/path verification commands in an authorized test environment:

~~~bash
# Test URL and certificate through standard DNS resolution.
curl -i https://api.example.com/v1/bookings/booking_123

# Override domain resolution to a specific entry-point IP in testing;
# curl still preserves the URL hostname for HTTPS, SNI, and HTTP Host.
curl --resolve api.example.com:443:203.0.113.10 \
  -i https://api.example.com/v1/bookings/booking_123
~~~

**203.0.113.10** belongs to the documentation example IP range; substitute an authorized endpoint in your test environment. These commands illustrate route verification only and do not imply the API returns success without valid auth tokens or IDs.

When testing geographic routing, do not rely solely on injecting an **X-Forwarded-For** header: a properly hardened system ignores untrusted headers. Use probes located in real networks/regions or official geo-testing tools, and confirm the serving region in logs/traces.

### 11.3. Troubleshooting Runbook for Misrouting

1. Confirm symptoms and blast radius: host, path, method, timestamp, affected regions, and impacted SLIs.
2. Check DNS/TTL, certificate, and resolved entry point; isolate name resolution, TLS handshake, and HTTP issues.
3. Inspect active route rules/versions, match precedence, host/path normalization, rewrites, and selected backend.
4. Check target health, WAF, auth, rate limits, upstream traces, DB, and dependencies.
5. Compare chosen region against tenant/data policies, latency metrics, and regional health.
6. Roll back the faulty config or execute failover per runbook without breaking transaction consistency.
7. Verify recovery via synthetic checks and business SLIs, then update docs/diagrams and postmortem root cause.

## 12. Practice Scenario: Multi-Region Accommodation Booking Platform

A hypothetical product serves customers in Vietnam and select international markets, including a web app, public images, property search, booking, and an admin portal. Requirements below are **illustrative targets**, not cloud provider guarantees:

- Fast image loading across multiple markets.
- Booking must prevent double-bookings and handle retries safely over unstable networks.
- Data owners approve the list of regions allowed to store/process each data class.
- Booking SLOs and DR targets must be proven through measurement and drills; choosing multi-region alone proves nothing.
- Admin portal requires MFA, scoped permissions, and auditing.

### 12.1. Initial Design

1. **Global entry + CDN:** serve public assets from appropriate edge locations with caching and invalidation policies.
2. **Host routing:** **www.example.com** to frontend, **api.example.com** to API, **admin.example.com** to protected admin portal.
3. **Path routing:** under **api.example.com**, **/v1/search/** to Search, **/v1/bookings/** to Booking.
4. **Geo/latency routing:** Search may run across multiple compliant healthy regions; routing optimizes measured latency within that approved set.
5. **Data-aware routing:** Booking authenticates the tenant and routes writes to the authoritative region with an approved standby option; never write arbitrarily to the nearest edge.
6. **Observability:** dashboards segmented by host, path group, region, health, cache-hit ratio, replication lag, latency, and transaction success rate.

### 12.2. Trade-offs Across Three Options

| Option | Benefits | Risks / Costs | Best Fit When |
|---|---|---|---|
| **A – Single region, multi-AZ, global CDN** | Simpler write consistency; CDN accelerates static assets | Distant APIs may feel slower; needs DR plan for region outage | Small team prioritizing consistency without multi-region API complexity |
| **B – Multi-region Search, centralized Booking writes** | Lower read latency globally while keeping one authoritative write path | Requires read projections/indexes, replication, data policies, and lag monitoring | High read volume where search eventual consistency is acceptable |
| **C – Multi-region for writes as well** | Can reduce distance to users and increase regional capacity | Hardest write conflicts, transactions, consistency, DR, and cost | Strong business need backed by team capability for distributed writes |

Never select Option C under the assumption that "the nearest region is always fastest." For bookings with strict no-double-booking invariants, transaction correctness and data ownership must be solved before allowing distributed writes.

### 12.3. Failure Walkthrough and Evaluation

**Scenario 1 – Search in region A becomes unhealthy:** global routing removes A from eligible targets and routes to B only if B complies with policy and has capacity; Search degrades gracefully if all compliant regions fail.

**Scenario 2 – Booking API times out after POST:** client reuses the same idempotency key and queries status/reconciliation before retrying; never blindly retry as a fresh transaction in another region.

**Scenario 3 – IP geolocation misidentifies user region:** the user is still governed by account permissions and tenant data policy; the system never relies on IP location alone to decide where booking records live.

**Scenario 4 – Migrating path from /api/bookings to /v1/bookings:** gateway preserves compatibility on a defined schedule, updates API contracts, tests rewrites and caches, and monitors legacy version usage before deprecation.

## 13. Well-Architected Review

| Pillar | Key Questions to Answer | Illustrative Trade-offs |
|---|---|---|
| **Operational Excellence** | Who owns routes, how are IaC/PR changes reviewed, who is on call, and are rollbacks tested? | Granular host/path/region rules increase flexibility but demand strict testing and observability |
| **Security** | Are TLS, WAF, Host validation, authz, origin access, and data boundaries enforced? | Flexible routing easily creates misconfigurations without strong policies and tests |
| **Reliability** | Do routes respect target health? Are DNS TTL, failover, consistency, and RTO/RPO drilled? | Multi-region reduces certain single points of failure while complicating data and incident response |
| **Performance Efficiency** | Do regional end-to-end p95/p99 improve, or only RTT to the edge? | A nearby edge may still call a distant DB; caching and distributed reads must preserve semantics |
| **Cost Optimization** | What do CDN, WAF, gateway, LB, inter-region traffic, egress, and logs cost? | Cross-region traffic forwarding can inflate bandwidth and operational spend |
| **Sustainability** | Are compute, caches, or data transfers duplicated unnecessarily? | Distributing only the components that truly benefit cuts wasted resources and traffic |

No single routing policy optimizes every pillar simultaneously. Business requirements and data constraints are mandatory gates; latency and cost are optimized within the valid solution space.

## 14. Common Mistakes

| Mistake | Why It Is Dangerous | How to Fix |
|---|---|---|
| Assuming DNS knows exact user location | Resolvers, VPNs, and ECS introduce error | Measure actual endpoints; treat location as an approximate signal |
| Routing every request to the nearest region | Transactions may hit distant DBs or violate residency rules | Separate read/write and tenant policies; measure end-to-end |
| Using Host or path instead of authentication | Clients can send arbitrary Host/path values | Enforce authn/authz, default deny, and resource checks |
| Using an overly broad /api prefix | Can match unintended routes | Enforce segment boundaries, exact/prefix precedence, and normalization |
| Trusting every X-Forwarded-For header as real client IP | Clients can spoof headers | Trust forwarded headers only from configured trusted proxies |
| Treating /healthz 200 as sufficient for booking readiness | App may be up while DB or core flow is broken | Layer health checks with synthetic transactions and end-to-end SLIs |
| Assuming low TTL gives instant failover | DNS caches and open connections linger | Measure failover, design DR, and accept DNS limits |
| Assuming multi-region allows writing anywhere | Replication does not ensure strong consistency or data compliance | Design authoritative writers, idempotency, and approved failover |
| Caching all /api responses at the CDN | Can leak data across user accounts | Scope cache policies, cache keys, and test tenant isolation |
| Failing over to any surviving region | Can breach data residency and break business state | Constrain to policy-compliant regions before optimizing availability |

## 15. Practice Exercises

### Exercise A – Host and Path

A gateway has two rules: any request to **api.example.com** goes to Legacy API; any request with path **/v2/orders/** goes to New API. An admin assumes **api.example.com/v2/orders/1** will definitely reach New API.

**Question:** Can you conclude that?

**Hint:** Not yet. You need to know whether the rules live on the same tier or separate tiers, rule precedence, and how the platform matches host vs. path. Define a virtual host for **api.example.com**, place specific path rules before the default route, and write path/version integration tests.

### Exercise B – Users Behind a VPN

A customer belongs to a tenant restricted to region A but connects over a VPN exit IP in country B. DNS selects edge B for lower RTT, and the gateway attempts to route writes to database B.

**Question:** What are the risks and remediation?

**Hint:** IP location does not define allowed data processing locations. Edge B may terminate connections if policy allows, but Booking must authenticate the tenant and route writes to region A or an approved standby region. Audit logs, caches, and backups as well.

### Exercise C – Failover Causes Duplicate Transactions

A client sends a booking POST to region A. Region A commits the booking, then the connection drops before the response returns. DNS shifts the client to region B, the client retries POST, and creates a second booking.

**Question:** What is missing in the design?

**Hint:** Missing unified transaction intent tracking and consistent state across all candidate target regions. Implement idempotency keys with shared persistence and TTL, status queries on timeout, coordinated failover, and reconciliation.

### Exercise D – "Nearest" Latency Is Worse

Both regions are healthy. Region A has lower client→API RTT than B, yet backend A queries a distant DB. Users still observe higher transaction p95 latency.

**Question:** What should you measure and change?

**Hint:** Measure end-to-end latency by route/region, backend→DB spans, cache hit rates, connection pooling, and tail latency. Keep write compute close to authoritative data, add read caches/read models where appropriate, or adjust routing policy. Never optimize solely on edge RTT.

## 16. Pre-Production Checklist for Routing

- [ ] Every public hostname has a clear certificate, owner, default route, and TLS policy.
- [ ] Host/path/method matching order is deterministic; tested for exact, prefix, trailing slash, encoding, rewrites, and invalid routes.
- [ ] Only trusted proxies supply forwarded headers used in security decisions.
- [ ] APIs and admin endpoints enforce authentication, per-tenant/resource authorization, and appropriate rate limiting.
- [ ] Geo, latency, health, weighted, and stateful routing rules are clearly separated.
- [ ] Origins, logs, caches, replicas, backups, and external partners comply with data residency policies.
- [ ] Read/write and transaction flows define consistency, session, idempotency, and retry/failover rules.
- [ ] p50/p95/p99 latency, error rates, business SLIs, health, and capacity metrics are tracked per route/region.
- [ ] Multi-region tests, unhealthy-region drills, DNS cache checks, and measured recovery plans exist.
- [ ] Edge/CDN, global routing, gateway, egress, replica, observability, and operational costs are estimated.
- [ ] Routes and policies are versioned, code-reviewed, rolled out progressively, and reversible.
- [ ] Request flow diagrams, security boundaries, runbooks, and route owners reflect the live system.

**Key takeaway:** host routing selects **the application by domain name**; path routing selects **the function by URL**; geographic routing uses **inferred location or territorial rules**; latency routing favors **the path expected to respond faster**. Reliable cloud architectures combine these with authorization checks, health validation, authoritative data sources, approved geographic scope, and end-to-end experience measurement.
