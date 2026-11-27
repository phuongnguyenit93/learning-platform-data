# API Aggregation, Backend for Frontend, and Reducing Round Trips

A single web or mobile screen often needs data from multiple business capabilities: account details, product listings, order statuses, availability calendars, payments, and notifications. If the client has to call each API individually, network round trips multiply, data-merging logic gets duplicated across clients, and user experience degrades whenever one service responds slowly. **API aggregation** and **Backend for Frontend (BFF)** are two architectural patterns that organize data retrieval around client needs while reducing call counts and controlling browser/app complexity.

This lesson belongs to the **API Architecture** chapter in the **Cloud Architecture** learning path. The focus is designing aggregated APIs, choosing BFF boundaries, composing data from multiple services, and reducing round trips while preserving domain ownership, security, scalability, cost efficiency, and operability. The goal is not to cram every API into one giant endpoint; the goal is to create contracts tailored to a journey or screen, with clear bounds on data, latency, and responsibility.

After this lesson, you will be able to:

- Explain API aggregation, API composition, and BFF, and distinguish their roles.
- Decide when to aggregate at an API gateway, BFF, business backend, or query layer.
- Design BFFs per client type and user journey without duplicating core business logic.
- Reduce round trips through batching, projections, caching, pagination, and purpose-built endpoints.
- Handle timeouts, partial failures, retries, concurrency, and consistency when aggregating multiple sources.
- Protect access control, personal data, tenant boundaries, and defend against over-fetching.
- Measure effectiveness via p95/p99 latency, request counts, payloads, errors, cost, and end-to-end SLOs.

## 1. The problem of many small APIs from the client's perspective

Suppose a rental order details page needs to display:

- Basic order details and current status.
- Customer name and permitted contact details.
- Equipment list, images, and rental period.
- Total amount, payment status, and invoice.
- Delivery progress and latest notifications.

If the client calls five APIs sequentially—and each triggers additional sub-requests—the page can feel slow even when every individual backend responds relatively fast. If the client calls them in parallel, total latency may drop, but the client must know about many services, handle diverse error formats, manage auth, and stitch data together.

Common problems that arise:

1. **Excessive round trips:** every request pays fixed overhead for DNS, TLS, network, gateway, and processing.
2. **Duplicated stitching logic:** web, iOS, and Android independently call the same sources and merge them.
3. **Coupling to backends:** clients must know internal service names, endpoints, schemas, and data relationships.
4. **Over-fetching or under-fetching:** APIs return too much data, or clients make extra calls just for a few fields.
5. **Complex error handling:** when part of the data fails to load, clients must decide what to render.
6. **Hard-to-evolve contracts:** backend refactors force multiple clients to update simultaneously.
7. **Wide security surface:** clients interact with many endpoints and risk calling internal APIs improperly.

API aggregation and BFF shift appropriate coordination to the backend so clients receive a contract aligned with their display needs.

## 2. Distinguishing architectural patterns

### 2.1. API aggregation

**API aggregation** is having an endpoint or backend component call multiple data sources/services, combine the results, and return a single response. The aggregator hides the number of underlying backends and can run parallel calls, transform schemas, or apply presentation rules.

Example: endpoint GET /rental-details/{id} calls Booking, Inventory, Billing, and Delivery, then returns a combined response.

### 2.2. API composition

**API composition** typically describes a pattern where a component queries multiple services and combines their data into a result for the caller. This term often overlaps closely with API aggregation, though usage varies across organizations/frameworks. What matters is that the composition layer coordinates queries and shapes outputs while data ownership stays with the source services.

### 2.3. Backend for Frontend

A **Backend for Frontend (BFF)** is a backend tailored around the needs of a specific client type or experience. For instance, you may have separate BFFs for web, mobile, and partners; each BFF provides a contract suited to that client's capabilities, interaction flows, security model, and constraints.

A BFF commonly uses API aggregation to fetch data, and can also handle:

- Session/token authentication and standardized identity forwarding.
- Response adaptation for a specific client and version.
- Appropriate pagination, filtering, and field projections.
- Orchestrating read steps needed for a screen.
- Managing caching or request coalescing.
- Normalizing errors and providing fallbacks for optional data.

A BFF must not become a dumping ground duplicating business logic from source services. Rules like "which rental orders can be cancelled," "which assets are reserved," or "when refunds apply" must be enforced by the authoritative domain capabilities.

### 2.4. Comparison table

| Pattern | Question it solves | Typical scope | Example |
| --- | --- | --- | --- |
| API aggregation | How to combine multiple sources into one response? | A single use case/query | Rental order overview page |
| API composition | How to query multiple services and assemble results? | Data coordination layer | Status report from Booking and Billing |
| BFF | What contract does a specific client need? | One experience or client type | Web BFF, Mobile BFF |
| API gateway | How to manage a shared entry point? | Cross-cutting edge concerns | TLS, auth, routing, rate limits |
| GraphQL gateway/federation | How should clients select fields and compose schemas? | Schema/query API | Query multiple domains via one graph |

These patterns can be combined. A BFF can act as an API aggregator; an API gateway sits in front of the BFF to enforce shared edge policies. GraphQL can serve as the query surface, though GraphQL itself does not automatically solve ownership, authorization, N+1 queries, or query limits.

## 3. When do you need API aggregation?

Aggregation fits when a clear use case needs data from multiple sources and direct client calls would complicate the client or raise latency.

Signals include:

- A screen routinely requires 3 or more APIs across different domains.
- Multiple clients repeat identical data-merging logic.
- Backend data structures do not match presentation semantics.
- Sources can be called safely in parallel or batched.
- Errors, timeouts, and fallbacks need server-side normalization.
- There is an opportunity to cut round trips without creating uncontrolled coupling.

Do not aggregate solely to shrink the endpoint count in documentation. If a screen only needs one fast, stable API, adding an aggregator introduces an extra hop, failure point, and cost.

### 3.1. Before and after example

**Before:** client fetches data from multiple backends.

~~~mermaid
flowchart TB
    C["Web / Mobile client"]
    C --> B["Booking API"]
    C --> I["Inventory API"]
    C --> P["Payment API"]
    C --> D["Delivery API"]
    C --> N["Notification API"]
~~~

**After:** client calls one aggregated endpoint.

~~~mermaid
flowchart TB
    C["Web / Mobile client"] --> A["Rental Details Aggregator"]
    A --> B["Booking API"]
    A --> I["Inventory API"]
    A --> P["Payment API"]
    A --> D["Delivery API"]
    A --> N["Notification API"]
    A --> R["Single screen-tailored response"]
~~~

The diagram does not mean the aggregator replaces source backends. Services remain responsible for their own data and domain rules; the aggregator only coordinates reads and shapes the response.

## 4. Defining BFF boundaries by client and journey

Not every app or every screen needs its own BFF. Boundaries should be drawn around meaningful differences in requirements, release cycles, protocols, security, or user experience.

Examples:

| Client | Specific needs | Suitable response design |
| --- | --- | --- |
| Admin web | Wide tables, rich filters, bulk actions | Pagination, sort/filter, role-scoped admin fields |
| Customer mobile | Small payloads, unstable networks, compact screens | Minimal projections, thumbnail images, appropriate caching |
| Partner API | Stable contract, clear versioning and limits | Published schemas, quotas, idempotency on commands |
| Device/kiosk | Constrained connectivity, only a few fields needed | Compact responses, short timeouts, local TTL caching |

One BFF for Web and one for Mobile can make sense if responses, release cadence, security, or network constraints differ substantially. Yet if two clients share nearly identical needs and owners, a single BFF with projections or API versioning may be simpler.

### 4.1. Questions to decide on a BFF

1. Do clients require genuinely different data structures?
2. Does one client have specific bandwidth, memory, battery, or connectivity constraints?
3. Do release schedules and version compatibility differ?
4. Are there distinct security, session, or authorization policies?
5. Does aggregation require experience-specific presentation logic?
6. Is there sufficient team ownership and observability to operate another backend?

Create a new BFF only when UX, permission, change-velocity, or performance gains outweigh the added cost of another service, pipeline, monitoring setup, and on-call burden.

## 5. What should a BFF do—and not do?

A BFF is an adaptation layer between client and backend, not a new domain service holding all business logic.

**Should do:**

- Combine data tailored to one experience.
- Shrink or normalize payloads.
- Map DTOs/backend schemas to client contracts.
- Enforce edge permissions and forward identity/context safely.
- Standardize pagination, error formats, and trace context.
- Cache read data appropriately and bound request fan-out.
- Orchestrate read flows; for commands, delegate to the authoritative business service.

**Should not do:**

- Duplicate domain rules such as pricing calculations, refund approvals, or inventory decisions.
- Write directly to another service's database.
- Share one overly privileged service credential across all clients.
- Return raw backend dumps and force clients to filter them.
- Become a mandatory choke point for internal service-to-service flows that do not need it.
- Bundle long workflows or multi-step transactions into a single synchronous aggregation request.
- Omit limits on backend call counts, timeouts, and payload sizes.

A good litmus test: if changing a core business rule forces you to modify the BFF to preserve correctness, that rule likely lives in the wrong layer.

## 6. Designing responses around use cases

An aggregated response should be a **read model** tailored to the client's question, not a raw dump of every backend.

Example rental order details response:

~~~json
{
  "booking": {
    "id": "bk-100582",
    "status": "CONFIRMED",
    "startDate": "2026-12-03",
    "endDate": "2026-12-06"
  },
  "customer": {
    "displayName": "Nguyen A"
  },
  "items": [
    {
      "id": "asset-21",
      "name": "Camera kit",
      "thumbnailUrl": "/media/asset-21/thumb"
    }
  ],
  "payment": {
    "status": "PAID",
    "total": {
      "amount": 1250000,
      "currency": "VND"
    }
  },
  "delivery": {
    "status": "SCHEDULED",
    "estimatedAt": "2026-12-03T02:00:00Z"
  }
}
~~~

These fields are illustrative. The BFF must return only fields the client is authorized to see. For example, customers should not necessarily see internal audit notes, anti-fraud flags, or sensitive billing addresses.

### 6.1. Projections and field selection

Projections deliver only the fields needed. You can design separate endpoints for summaries and details:

| Endpoint | Fields | Purpose |
| --- | --- | --- |
| GET /me/bookings | id, status, startDate, endDate, thumbnail | Lightweight listing |
| GET /me/bookings/{id} | Order details, items, payment status, delivery summary | Detail screen |
| GET /admin/bookings/{id} | Extended details scoped by staff permissions | Administration |

Letting clients select arbitrary fields is not always better. Unrestricted field selection complicates queries, triggers backend over-fetching, or exposes sensitive fields. If using GraphQL or query languages, enforce field allowlists, depth/complexity caps, pagination, and field/object-level authorization.

### 6.2. Screen-specific APIs vs. resource APIs?

**Resource APIs** like GET /bookings/{id} provide a canonical representation of a resource reusable across many clients.

**Experience APIs** like GET /mobile/home-summary aggregate multiple resources around a screen's needs.

The two are not mutually exclusive. Resource APIs keep domain contracts clean; experience APIs cut round trips and payloads. Avoid creating a bespoke endpoint per pixel/screen when data and behavior are nearly identical.

## 7. Reducing call counts: batching and controlled fan-out

Aggregation does not automatically reduce backend load. An aggregator making 10 backend calls per client request cuts client round trips, but can amplify internal fan-out. Optimize both tiers.

### 7.1. Batching multiple identifiers

If a client needs the status of 20 bookings, instead of 20 separate calls, the backend can provide a batch endpoint:

~~~http
POST /booking-status:batchGet
Content-Type: application/json

{
  "bookingIds": ["bk-1", "bk-2", "bk-3"]
}
~~~

Batch APIs must bound item counts, define behavior when some IDs do not exist or are unauthorized, and guard against oversized payloads. Responses should key results by ID so clients correlate reliably.

Batching does not mean accepting unbounded arrays. A request with 10,000 IDs can trigger massive queries, memory pressure, and timeouts. Enforce pagination, maximum batch sizes, and quota checks.

### 7.2. DataLoader and N+1

In GraphQL or resolver composition, the N+1 problem happens when each item's resolver makes its own backend call. A page of 100 bookings can trigger 1 list query plus 100 customer queries.

A batch loader coalesces IDs within one execution tick into a single batch query:

~~~text
for each booking in page:
    customer = loadCustomer(booking.customerId)

DataLoader groups customer IDs:
    customerService.getByIds([id1, id2, ...])
~~~

DataLoader must be scoped properly; request-scoped caching is safer than process-wide caching when data and permissions depend on caller/tenant. Never let User A's cached result leak to User B.

### 7.3. Parallel calls

If backend queries are independent, the aggregator can call them in parallel instead of sequentially. If three backends take 80, 120, and 150 ms respectively, sequential calls take roughly 350 ms plus overhead; parallel calls take roughly as long as the slowest backend plus overhead. This is illustrative—actual timing depends on networking, pools, queues, and percentile latency.

Never allow unbounded concurrency. Cap fan-out, connection pools, and calls per request; enforce per-dependency timeouts, circuit breakers, or bulkheads; prevent one user from flooding backends with amplified calls.

## 8. Data aggregation models and consistency

When an aggregator calls multiple services, responses may reflect different points in time. For instance, Booking may have transitioned to CONFIRMED while Payment API still returns an older state due to asynchronous updates. The combined response can therefore represent a non-atomic snapshot.

Decide required consistency levels:

- For low-risk display fields like thumbnails or product titles, eventual consistency is usually acceptable.
- For payable amounts, refund eligibility, or action permissions, read from the authoritative source rather than inferring from stale caches.
- Where version correlation matters, return lastUpdated/version timestamps or an updating status.
- For transactions requiring atomicity, the aggregator never replaces the owning service's transaction/workflow.

### 8.1. Partial responses

Not all sources are equally critical. Classify them:

| Data | Criticality | Behavior on source failure |
| --- | --- | --- |
| Booking status | Required | Fail request if unobtainable |
| Payment status | Required for payment actions | Disallow sensitive actions on missing data |
| Thumbnail | Optional | Placeholder or omit field |
| Delivery estimate | Possibly optional on summary page | Return unavailable state with metadata |
| Notification preview | Optional | Omit or return empty list if contract defines |

When returning partial data, indicate the status per section explicitly; never fabricate misleading defaults such as payment status = PAID when the payment API timed out.

Illustrative partial response structure:

~~~json
{
  "booking": {
    "id": "bk-100582",
    "status": "CONFIRMED"
  },
  "payment": {
    "status": "UNAVAILABLE",
    "updatedAt": null
  },
  "delivery": {
    "status": "SCHEDULED"
  },
  "meta": {
    "partial": true,
    "unavailableSections": ["payment"]
  }
}
~~~

Use this only when the product and API contract explicitly define how clients handle unavailable sections. For charging/cancelling/refunding actions, the backend must verify authoritative state before executing.

## 9. Timeouts, retries, and partial failures

As a coordination point, an aggregator can amplify backend failures. If an aggregated request calls 8 services and each is allowed 3 seconds, response times can easily breach client SLOs.

Design should:

- Set an overall deadline and allocate per-dependency budgets.
- Cancel no-longer-useful calls when the caller times out/cancels if the platform supports it.
- Retry only transient failures, with low attempt limits and backoff; never retry business or validation errors.
- Avoid synchronized retries hitting an overloaded backend.
- Use circuit breakers/bulkheads or concurrency limits where needed.
- Classify critical vs. optional dependencies.
- Return clear errors with correlation IDs for support.
- Never mask errors with stale data without indicating freshness.

### 9.1. Illustrative latency budget

Suppose a screen requires p95 = 500 ms. A reference budget might look like:

| Component | Target budget |
| --- | ---: |
| Client → API edge and auth | 70 ms |
| Aggregator processing/serialization | 40 ms |
| Booking backend | 120 ms |
| Payment summary | 100 ms |
| Delivery summary | 100 ms |
| Network/variance buffer | 70 ms |
| Total | 500 ms |

If the three backends run in parallel, latencies do not sum linearly as in a table; each dependency still needs its own timeout and an overall deadline. Measure end-to-end percentiles, because combined p95 cannot be accurately calculated by summing component p95s.

## 10. Caching, request coalescing, and read data

Aggregation can increase backend load if every client request triggers many queries. Caching and request coalescing cut duplicate work, provided freshness and permissions are respected.

### 10.1. Cache layers

| Location | Benefit | Risk |
| --- | --- | --- |
| Client cache | Reduces requests and improves UX on weak networks | Stale data, sensitive data lingering on device |
| CDN/edge cache | Helpful for public or slow-changing data | Accidentally caching user/tenant-specific data |
| BFF response cache | Reuses responses for identical contexts | Missing user/tenant/permission in key leaks data |
| Backend/domain cache | Cuts source queries, shared across consumers | Complex invalidation and consistency |
| Request-scoped memoization | Prevents duplicate queries within one request | Valid only for the current request |

Cache keys must include factors that alter outputs: tenant, user scope, locale, currency, permissions, query parameters, and version where relevant. Never share response caches for personal data without proven isolation.

### 10.2. Time to live and invalidation

Longer TTLs raise hit rates at the cost of staleness. A few minutes may suit a product catalog, whereas payment status needs tighter freshness. Tune TTLs per business rules rather than applying one global TTL to all resources.

Techniques include:

- Short TTLs with stale-while-revalidate for low-risk summaries.
- Event-driven invalidation when domains emit state-change events.
- ETags/conditional requests to shrink payloads when data has not changed.
- Request coalescing so concurrent identical requests share one backend fetch.
- Avoiding caching sensitive errors or payment states by default.

### 10.3. Caches never replace authoritative sources

If a customer clicks "Refund," the BFF must not check a cached order status and decide eligibility. It must forward the command to the owning business service, which verifies current state and invariants at write time.

## 11. Pagination, filtering, and payload shaping

An aggregated endpoint can easily return too many records by accident. If a detail page loads full transaction history, every notification, and the entire catalog, payloads balloon rapidly.

Design should:

- Paginate at appropriate sources and return safe continuation tokens/cursors.
- Cap page sizes; never trust client-supplied sizes without validation.
- Allow filtering/sorting only on permitted fields.
- Project per use case to drop unneeded fields.
- Bound payloads and nested list sizes.
- Never fetch page 1 from Service A and page 2 from Service B unless cursors share unified semantics.
- When aggregating multiple sources, define clearly how pagination applies per collection.

When combining multiple independent lists, return separate cursors/nextPage tokens per section or split endpoints if independent scrolling is needed. A single shared cursor only works when the backend has a unified read model or query plan guaranteeing shared ordering and consistency.

## 12. Security and access control in a BFF

A BFF sits close to clients, accepts untrusted inputs, and aggregates data across domains. If authorization happens only at the API gateway based on login status, **Broken Object Level Authorization (BOLA)** can occur: an authenticated user requests someone else's bookingId.

Principles:

1. **Authenticate callers:** verify tokens/sessions, issuer, audience, expiry, and signatures.
2. **Object-level authorization:** verify the caller is permitted to view the specific resource, not just hold a general role.
3. **Tenant isolation:** bind tenant context from verified identity; never trust client-submitted tenantIds.
4. **Least-privilege service-to-service:** BFF only invokes needed operations; never use global admin credentials.
5. **Data minimization:** do not forward backend fields unnecessary for the UI.
6. **Output encoding and validation:** prevent malicious data from reaching UIs or downstream queries.
7. **Rate limiting:** curb fan-out abuse, ID brute-forcing, and oversized requests.
8. **Auditing:** log sensitive access and administrative actions per policy.

### 12.1. User context and service identity

A BFF can use its service identity to call backends while forwarding signed/authorized user context so backends enforce domain authorization. Specific mechanisms depend on the stack: token exchange, on-behalf-of flows, or service-to-service auth paired with verified claims.

Avoid blindly passing raw client bearer tokens everywhere if unnecessary, and never strip user context so backends trust every call from the BFF indiscriminately. Establish clear trust boundaries and validate token audiences/scopes.

### 12.2. Protecting aggregated responses

A multi-domain response risks concentrating sensitive data in a single endpoint. Logging full responses, misconfiguring shared caches, or leaking internal backend objects widens blast radius. Use schema allowlists, field-level authorization where needed, metadata-only logging, and cache isolation tests.

## 13. Designing BFFs for multiple client versions

Web apps update instantaneously while older mobile versions stay in the wild for months. A BFF must manage contracts and compatibility.

- Version endpoints or use header/content negotiation where appropriate.
- Adding optional fields is usually safer than renaming/removing fields.
- Never repurpose existing fields with new meanings.
- Maintain deprecation windows, measure adoption, and communicate clearly with client owners.
- For older apps, the BFF can adapt newer backend schemas back to older contracts.
- Avoid supporting infinite legacy branches; enforce a version support policy.

Serving as an adaptation layer slows backend churn from breaking clients, yet the BFF itself becomes a contract requiring versioning, testing, and ownership.

## 14. Aggregation, CQRS, and read models

If an aggregated screen frequently joins many sources under tight latency targets, calling multiple domain services sequentially or in parallel on every request can become a bottleneck. **CQRS (Command Query Responsibility Segregation)** and **read models/projections** fit when aggregated read patterns are stable, high-volume, or structurally very different from transactional models.

In this model:

- Domain services keep owning writes and business rules.
- When domain state changes, services emit durable events via appropriate mechanisms.
- Consumers build read models containing fields needed for a use case.
- The BFF reads from the read model instead of fanning out broadly on every request.
- Read models can be eventually consistent; UIs and sensitive actions must handle freshness properly.

~~~mermaid
flowchart TB
    B["Booking service"] --> E["Domain events"]
    P["Payment service"] --> E
    D["Delivery service"] --> E
    E --> PROJ["Projection consumer"]
    PROJ --> RM[("Rental details read model")]
    C["Client"] --> BFF["BFF / API"]
    BFF --> RM
~~~

Read models cut call counts and enable query optimization, at the cost of sync pipelines, schemas, storage, replays, and lag handling. Do not build a separate projection for every screen if multiple needs can share one stable read model.

### 14.1. When should you still call directly?

A low-traffic admin page needing always-fresh data across two sources can use a direct aggregator. A high-read dashboard joining a dozen sources with tight latency fits a projection. Choose based on **load, freshness, cost, eventual-consistency tolerance, and sync complexity**.

## 15. Avoiding N+1 and item-proportional fan-out

An aggregator can accidentally introduce N+1 queries: fetching 50 bookings and calling Payment API once per booking. Even though the client sent one request, the BFF generates 51 backend calls.

Remedies:

- Use bounded-ID batch endpoints.
- Use read models containing frequently displayed summary fields.
- Provide list APIs returning sufficient summary fields if domain owners agree.
- Apply DataLoader/request-scoped caching to batch IDs and deduplicate queries.
- Cap fan-out and alert when upstream calls/request spike abnormally.

Track **upstream calls per client request** as a core metric. Fewer edge requests do not automatically mean lower total system load.

## 16. Error strategies and partial availability

When aggregating multiple backends, overall success depends on mandatory dependencies. If an optional dependency fails, the BFF can return a partial response; if a critical dependency fails, return an appropriate error.

Classification:

| Dependency class | Behavior |
| --- | --- |
| Critical for entire use case | Fail request with error details and correlation ID |
| Critical only for sensitive action | Allow viewing other sections while disabling the action or prompting refresh |
| Optional presentation | Return partial response, placeholder, or omit section |
| Valid cache available | May return stale data if contract indicates freshness and domain allows |

Never return HTTP 200 with missing critical data and no metadata. Conversely, do not fail an entire page just because an optional thumbnail failed to load.

### 16.1. Selective retries

- Never retry validation errors, 401/403, or resource-not-found unless specifically justified.
- Retry timeouts/503/429 within remaining deadline and dependency retry policies.
- For idempotent read requests, bounded retries can help.
- Never retry transaction-creating commands without an idempotency key.
- Do not let multiple layers (client, BFF, gateway, SDK) retry unboundedly in parallel, multiplying call volume.
- When downstream is overloaded, prefer load shedding and failing fast over continued fan-out.

## 17. Measuring aggregation and BFF effectiveness

Before optimizing, establish baselines and targets.

| Metric | Meaning | How to use |
| --- | --- | --- |
| Client round trips | Requests the client must send for a use case | Measure client load and complexity reduction |
| Upstream calls/request | Backend calls generated by the BFF | Detect fan-out or N+1 |
| End-to-end latency p50/p95/p99 | User experience | Compare before/after aggregation |
| Payload size | Response bytes | Measure over-fetching and network cost |
| Error/partial response rate | Rate of incomplete/failed use cases | Assess reliability and dependencies |
| Cache hit/staleness | Cache efficiency and data age | Tune TTLs and invalidation |
| Cost per successful use case | Cost to complete one journey | Covers BFF, backends, caches, logs, and transfer |
| CPU/memory/concurrency | BFF capacity | Sizing and autoscaling |

Illustrative product target: reduce rental detail page from 6 client requests to 1, cut p95 from 900 ms to under 500 ms, and keep payload under 150 KB. These are illustrative targets; compare before/after metrics under identical load and device profiles.

Never use client request count as the sole metric. If a BFF cuts client round trips from 6 to 1 while creating 20 upstream calls, doubling payload size, and adding a single point of failure, the design may actually hurt the system.

## 18. Design example: customer overview screen

Suppose a mobile home screen needs display name, 3 upcoming bookings, overall payment status, unread notification count, and a few recommended items.

### 18.1. Client-tailored contract

The endpoint could be GET /mobile/home-summary. Response includes only:

- Customer display name.
- Up to 3 upcoming bookings with status and times.
- Required payment summary for display.
- Unread notification count.
- A bounded recommendation list.
- Freshness/partial-section metadata if applicable.

Do not return full booking history, sensitive payment details, full profile, or the entire catalog.

### 18.2. Aggregation flow

~~~mermaid
flowchart LR
    M["Mobile app"] --> BFF["Mobile BFF"]
    BFF --> C["Customer summary"]
    BFF --> BK["Upcoming bookings query"]
    BFF --> PY["Payment summary"]
    BFF --> N["Unread notifications"]
    BFF --> R["Recommendation query"]
    BFF --> RESP["Compact mobile response"]
~~~

The BFF calls independent queries in parallel, sets per-source deadlines, and defines which fields are optional. If recommendations fail, still return the home screen; if booking status cannot be retrieved, mark the section unavailable or prompt reload per product requirements.

### 18.3. Scaling further as load grows

If this endpoint becomes one of the highest-traffic APIs, you can introduce a HomeSummary read model updated from domain events. The BFF reads one projection and fetches highly volatile fields separately if needed. Monitor projection lag and surface freshness in the UI.

### 18.4. Command and query boundary

GET home-summary only reads and aggregates. When the user taps "Cancel order," the BFF forwards the command to the Booking service; Booking checks permissions, cancellation policy, and payment status, and executes the required workflow. Never let the BFF write directly to the Booking database just to save one hop.

## 19. Common design mistakes

| Mistake | Consequence | Prevention |
| --- | --- | --- |
| One aggregation endpoint serving everything to every client | Bloated payloads, overly broad permissions, brittle contracts | Split by use case or BFF when real differences exist |
| Putting core domain logic in the BFF | Duplicated rules, inconsistent outcomes | Keep invariants and commands in domain services |
| Routing every request through a single BFF | BFF becomes a bottleneck and huge blast radius | Scope BFFs by client/ownership, scale and isolate properly |
| Calling independent backends sequentially | Cumulative latency | Call in parallel when independent with concurrency caps |
| Fanning out one call per item | N+1 problem, spikes backend load | Batching, projections, DataLoader |
| Returning partial responses unmarked | Clients mistake missing data for empty/valid data | Explicit partial metadata and states |
| Omitting tenant/user from cache keys | Cross-user data leakage | Key by security context and test isolation |
| Caching sensitive state too long | Decisions made on stale state | Risk-based TTL/invalidation, check authoritative state |
| Retrying all upstream failures | Outage amplification and higher cost | Deadlines, retry budgets, load shedding |
| One shared cursor across independent sources | Broken pagination or missing records | Per-section cursors or a unified ordered read model |
| Optimizing only client call counts | Upstream fan-out can surge | Measure calls per request, latency, and end-to-end cost |
| Not versioning BFF contracts | Old apps break on backend schema changes | Compatibility policy, deprecation, and adoption metrics |
| Logging entire aggregated responses | Leaks multiple data domains at once | Structured metadata, masking, and data minimization |

## 20. Design and implementation workflow

1. **Start from the journey:** identify screens/use cases, clients, required data, frequency, and SLOs.
2. **Map dependencies:** source backends, data owners, permissions, and latencies.
3. **Classify critical vs. optional:** decide which dependencies are mandatory and partial-failure behavior.
4. **Choose a pattern:** endpoint aggregation, dedicated BFF, gateway composition, or read model/CQRS.
5. **Design contracts:** response schemas, projections, pagination, errors, and versioning.
6. **Design security:** user/tenant context, object-level authorization, service identity, and cache isolation.
7. **Optimize flows:** batching, parallelism, request coalescing, caching, and fan-out limits.
8. **Set timeouts/deadlines:** end-to-end and per-upstream budgets, selective retries, circuit breakers as needed.
9. **Deploy via IaC/CI/CD:** contract tests, compatibility tests, rollouts, and rollbacks.
10. **Measure:** round trips, upstream calls, payloads, p95/p99, partial responses, costs, and SLOs.
11. **Re-evaluate:** move to read models when fan-out/load/freshness warrants it.

### Acceptance checklist

- [ ] A specific use case/client justifies the aggregated endpoint or BFF.
- [ ] Every piece of data has an identified owning source and query endpoint.
- [ ] Responses contain only fields needed by the client and permitted for the caller.
- [ ] Commands remain handled by the owning domain services.
- [ ] Fan-out, N+1, batch sizes, and concurrency are bounded.
- [ ] Timeouts/deadlines and retry policies are tested.
- [ ] Partial responses have clear semantics and never masquerade failures as valid data.
- [ ] Cache keys include security context; TTLs/freshness fit domain risk.
- [ ] Pagination/cursors are defined per collection.
- [ ] BFF contracts have versioning and backward compatibility for older clients.
- [ ] Tracing/correlation covers all upstream calls.
- [ ] End-to-end latency, payloads, upstream calls, errors, caching, and cost are measured.

## 21. Well-Architected assessment

| Perspective | Design questions |
| --- | --- |
| **Reliability** | Are critical/optional dependencies clear? Are timeouts, partial responses, fallbacks, and retries controlled? Does a BFF outage impact multiple clients? |
| **Security** | Is object/tenant authorization enforced? Can caches or responses leak data? Does the BFF hold least privilege? |
| **Performance efficiency** | Were round trips genuinely reduced? Did upstream fan-out, N+1, payloads, and p95/p99 improve? |
| **Cost optimization** | Did total queries and cost per successful use case drop? Are BFF, cache, and projection ops costs reasonable? |
| **Operability** | Are there correlation-ID traces, upstream latency/error views, version adoption tracking, partial-response metrics, and runbooks? |

## 22. Applied exercise

A car-rental app has a dashboard screen displaying user info, the three most recent trips, unpaid invoices, maintenance schedules, and notifications. Admin web needs additional audit data; mobile needs only a compact summary and may operate on slow networks. The payment service occasionally takes 1 second; vehicle photos can be cached for 10 minutes.

Design:

1. Should you use one shared aggregator, separate web and mobile BFFs, or add a read model? State why.
2. Which data fields are critical to render the dashboard and which can be partial?
3. Which calls can run in parallel, and which must check authoritative state?
4. How should cache keys and TTLs differ for photos, notifications, payment summaries, and trip data?
5. How do you avoid N+1 when displaying three trips alongside vehicle and invoice data?
6. How do you protect audit data so mobile cannot access it even if it knows the endpoint?
7. Which metrics will you measure to prove the new architecture lowers latency and total load?

A well-founded design may use dedicated BFFs when web and mobile genuinely diverge in needs, batching or projections for trip data, TTL caching for photos, and avoid long-lived caching for payments. Payment or trip-cancellation actions must always verify latest state at the authoritative business service.

**Key takeaway:** API aggregation reduces the complexity of calling multiple sources by combining data for a use case; a BFF shapes contracts around client needs; batching, projections, caching, and fan-out caps reduce round trips and load. They only succeed when domain ownership, authorization, error semantics, and data freshness stay intact. An API with fewer client requests is not automatically a better system; measure the full journey from client to data sources, including latency, errors, payloads, cost, and operability.
