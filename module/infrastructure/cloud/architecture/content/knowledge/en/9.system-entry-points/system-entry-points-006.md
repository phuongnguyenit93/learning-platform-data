# DDoS Defense, WAF, and Limiting Blast Radius at Entry Points

## 1. Entry Points Are a Critical Cloud Architecture Boundary

An application can deploy replicas across multiple availability zones and still become unavailable if all Internet requests pass through a bottlenecked entry point or if anomalous traffic pushes the database to its limits. Therefore, **system entry point** design must answer three questions simultaneously:

1. **Who is allowed in and along which path?** Define hostnames, protocols, ports, client types, and paths to the application.
2. **Which threats should be filtered before reaching the workload?** Distinguish infrastructure DDoS, malicious application traffic, bots, and API abuse.
3. **If the entry point is overloaded or a control fails, how tightly is the blast radius contained?** The goal is not merely blocking bad traffic, but preserving service availability for legitimate users.

In the **CLOUD_ARCHITECTURE** module, entry-point protection must be designed from business requirements alongside decisions on **networking, compute, data, and deployment models**. The focus is weighing trade-offs across **reliability, security, performance, scalability, cost, and operations** under Well-Architected principles.

**Running scenario:** a booking platform has a website, mobile app, room-search API, booking confirmation API, login, and payment webhooks. Search can be cached under appropriate policies; booking creation requires protecting transaction consistency; webhooks arrive from an external partner. The numbers in the examples below are **illustrative learning assumptions only** and must be replaced by verified load data and requirements.

## 2. Distinguishing DDoS, WAF, and Related Controls

**DDoS (Distributed Denial of Service)** refers to degrading or halting service availability through abnormal traffic volume or resource exhaustion from many sources. Depending on the attack vector, the bottleneck may be bandwidth, connection count, network device throughput, TLS, application compute, or data stores.

**WAF (Web Application Firewall)** inspects selected attributes of **HTTP/HTTPS** traffic, typically at the application layer (L7), and allows, logs, challenges, or blocks requests per rules. A WAF can catch common exploit patterns and abuse, but does not replace fixing application vulnerabilities or defending against every infrastructure-level DDoS vector.

| Risk Category | Common Impact Path | Primary Defense Layers to Evaluate | Misconception to Avoid |
| --- | --- | --- | --- |
| Volumetric DDoS | Saturates network links and ingress bandwidth ahead of the app | Cloud/ISP upstream DDoS protection, distributed/Anycast edge, scrubbing services | A WAF sitting near the origin cannot rescue an already-congested upstream link |
| Protocol or connection DDoS (L3/L4) | Exhausts state tables, connections, or network/transport capacity | L3/L4 DDoS protection, load balancers, connection policies, network capacity | L7 HTTP filtering alone cannot absorb all transport-layer floods |
| Application DDoS (L7) | Expensive HTTP requests exhaust threads, CPU, DB, or queues | WAF, bot management, rate limiting, concurrency caps, caching, backpressure | Measuring requests/sec alone misses low-rate, high-cost requests |
| HTTP/API exploits | Malformed payloads, unauthorized access, authorization flaws | Tuned WAF rules, authn, authz, input validation, patching, app security testing | A WAF never replaces object/data-level authorization |
| Credential stuffing & abusive bots | Automated logins, scraping, excessive API calls | Identity/risk-based rate limits, login hardening, bot detection, MFA where fit | Blocking purely by IP harms users behind shared NAT and is bypassed via IP rotation |
| Legitimate traffic spikes (flash crowds) | Promotions or events cause sudden organic surges | CDN/caching, autoscaling, queues, capacity planning, load shedding | Never treat every traffic spike as an attack and block real customers |

Effective defense relies on **coordinated layered controls**. The network layer absorbs link pressure, edge/WAF filters requests, gateways authenticate and throttle API usage, and applications protect internal resources. No single standalone service guarantees SLO compliance across every attack type.

### 2.1. Clearly Defining Defensive "Success"

The objective is not "block as many requests as possible." An overly aggressive blocking rule can turn away legitimate customers. Define:

- **Success rate of legitimate user journeys:** such as room search, login, and booking completion.
- **End-to-end latency:** p95/p99 per journey under normal load and controlled anomalous scenarios.
- **False positive rate:** valid requests wrongly rejected, challenged, or excessively delayed.
- **Time to detect, triage, and mitigate:** from anomaly onset to service quality restoration.
- **Cost and resource containment:** malicious requests must not translate into unbounded DB, compute, or billing consumption.

Every metric needs a measurement method, scope, test dataset, and designated owner. Never write requirements like "stop all DDoS," which cannot be verified against an unbounded threshold.

## 3. Threat Modeling and Quality Requirements

Before choosing a WAF or DDoS service, identify **protected assets**, critical user journeys, and paths that might bypass the entry point.

| Asset / Journey | Entry-Point Risks | Architectural Goal to Validate |
| --- | --- | --- |
| Catalog & search pages | Spiking L7 requests, scraping, heavy queries | Legitimate access maintains SLO success rate and latency |
| Login | Automated password guessing, excessive session creation | Abuse from a subset of sources cannot exhaust auth capacity or trigger mass lockouts |
| Booking creation | Duplicate submissions, room contention, expensive writes | Preserves idempotency and business consistency even during retries |
| Payment webhooks | Spoofed senders, duplicate events, malformed payloads | Verifies contractual signature/origin, blocks replays, handles duplicates safely |
| Administration | Endpoint probing or exploiting privileged actions | Restricts entry points, enforces strong auth, least privilege, and auditing |
| Origin, database, message broker | Direct access bypassing the WAF | Accepts connections only along approved paths; no public exposure of internal tiers |

### 3.1. Example Verifiable Requirements

The targets below are **design assumptions only** for exercise purposes:

| ID | Requirement | Verification Method |
| --- | --- | --- |
| SEC-EDGE-01 | Backend APIs accept Internet traffic only via approved entry points | Audit routing, firewalls/security groups, and run authorized direct-access tests |
| SEC-WAF-01 | Priority WAF rules enforce only after observation and false-positive review | Inspect logs, valid/invalid test suites, and staged rollout results |
| PERF-EDGE-01 | Search API p95 stays within 800 ms at 200 requests/sec on the defined dataset | Controlled load tests and distributed tracing to backends |
| REL-EDGE-01 | Search journey remains functional when the external payment endpoint fails | Drill partner timeouts/unreachability and verify search outcomes |
| OPS-EDGE-01 | Anomaly alerts reach on-call within 5 minutes of detection criteria being met | Alert drills, telemetry lag measurement, escalation verification |
| COST-EDGE-01 | Forecast protection, request processing, logging, and transfer spend at peak | Compare estimates against test-run billing and traffic models |

Distinguish **entry-point SLOs** from **business SLOs**. A load balancer returning HTTP 200 for an error page does not prove customers can book rooms; a WAF blocking a request does not prove the request was malicious. Validate full journeys with representative identities and data.

## 4. Reference Architecture: Layered Defense

~~~mermaid
flowchart TB
    U["Legitimate clients and Internet traffic"]
    DNS["DNS / global distribution point"]
    DDOS["Upstream L3/L4 DDoS protection"]
    EDGE["CDN / Edge with bot protection"]
    WAF["HTTP(S) WAF"]
    GW["Load balancer / API Gateway"]
    APP["Web and API in private network"]
    Q["Business-scoped queues / buffers"]
    DB[("Private databases and data services")]
    OBS["Metrics, audit logs, traces, and alerts"]
    U --> DNS --> DDOS --> EDGE --> WAF --> GW --> APP
    APP --> Q
    APP --> DB
    GW -.-> OBS
    WAF -.-> OBS
    APP -.-> OBS
~~~

This diagram illustrates **logical capabilities**, not a mandate to purchase separate products for every box. One provider may bundle DDoS protection, CDN, WAF, and load balancing into fewer physical tiers. Physical ordering also varies: some setups place WAF at the CDN, others on an API Gateway or load balancer. Always verify the live request path in provider documentation and active configs.

### 4.1. Design Questions at Each Layer

| Layer | Primary Responsibility | Mandatory Questions |
| --- | --- | --- |
| DNS / distribution | Steers clients to the right entry point | How is DNS redundant? Does it rely on one zone/provider? How long does failover take? |
| Upstream DDoS protection | Absorbs/filters pressure ahead of origin | Which IPs/endpoints are protected, and what are the service scope and limits? |
| CDN / edge | Caches eligible content, cuts origin hits | What data is safe to cache, what is the cache key, and how is user data isolation enforced? |
| WAF / bot protection | Inspects HTTP, detects risk patterns | Which managed rules apply, how are false positives handled, and are rules versioned? |
| API Gateway / LB | Routing, TLS, API auth/policies per service, health checks | Are global and per-route limits set? Are there shared single points of failure? |
| Application & data | Authn, authz, correctness, resource bounds | Are identity-scoped rate limits, timeouts, idempotency, concurrency caps, and queues present? |
| Observability / ops | Root-cause analysis and coordinated response | Do logs capture sufficient context without exposing secrets/PII? Are playbooks and on-call assigned? |

**Origin bypass** is a major risk: if someone reaches the origin's public IP directly, CDN WAF rules are skipped. Restrict inbound origin connections via provider-supported controls, authenticate edge-to-origin connections where applicable, and avoid leaking origin endpoints.

### 4.2. TLS, Client IP, and Trust Boundaries

- Specify where edge TLS terminates and whether the edge→origin leg remains encrypted and identity-verified as required.
- Never blindly trust client-supplied `X-Forwarded-For` or `Forwarded` headers. Rely strictly on trusted proxy chains and normalize client IPs at the entry boundary.
- When rate limiting by IP, recognize that mobile CGNAT, corporate networks, or shared gateways put many legitimate users behind one IP; banning a single IP outright can block many real customers.
- Ensure `Host` headers, paths, and methods are parsed consistently across edge, WAF, proxy, and application; parser discrepancies cause routing bugs and policy bypasses.
- TLS configurations and certificates must have owners, expiry monitoring, and rotation plans; a single broken edge certificate fails all legitimate traffic.

## 5. DDoS Defense: Start Where Pressure Arrives

### 5.1. Place Volumetric Defenses Upstream

When traffic exceeds link or ingress device capacity, **application-tier blocking is already too late**. To mitigate L3/L4 or volumetric pressure, evaluate your cloud/ISP filtering capacity, distributed architecture, and DDoS services sitting in front of the origin.

Common options include:

- Distributed edge/Anycast infrastructure absorbing traffic across many PoPs rather than concentrating on one endpoint.
- Network/cloud provider DDoS detection and mitigation at network and transport layers.
- Upstream scrubbing services for workloads with compatible requirements and network topologies.
- Redundant DNS, network paths, and deployment regions aligned with reliability targets.

**Never assume enabling a DDoS feature stops every attack.** Know which endpoints are actually covered, supported traffic types, service limits and support SLAs, mitigation triggers, visibility tools, and potential side effects on valid traffic.

### 5.2. Defending Against Application-Layer Attacks

For HTTP/HTTPS, request count is not the sole cost metric. A heavy filtered search query, a large upload, or a slowloris-style held connection consumes far more resources than a static fetch.

Combine these layers simultaneously:

1. **Appropriate caching** at CDN/edge for cacheable content using strict cache keys and personal-data checks.
2. **Rate limiting** tailored by identity, route, and resource cost—never one flat site-wide threshold.
3. **Concurrency caps, timeouts, request size limits, and read/write bounds** at both gateway and application tiers.
4. **Backpressure/queues** for work eligible for async execution, protecting connection pools and downstreams.
5. **Controlled graceful degradation** preserving top-priority flows when load exceeds capacity.

Always load test downstream databases and services. Edge blocking lowers pressure, yet if legitimate traffic exceeds DB write capacity, application and data-layer changes are required—a bigger WAF alone cannot help.

### 5.3. Distinguishing Organic Spikes from Abuse

A flash-sale campaign bringing real customers simultaneously resembles an L7 DDoS attack on raw RPS charts. Protective rules must rely on **multiple signals** and measure impact on legitimate users:

- Shifts broken down by endpoint, identity, country, and time window relative to baseline.
- Ratio of authenticated requests, valid behavioral sequences, sessions, and business completions.
- Latency, CPU/DB saturation, queue depth, error rates, and WAF/bot-manager scores.
- Challenged request volume and pass rates among legitimate users.

Never treat geography or a single IP as conclusive proof of malice. When geographic restrictions are necessary, account for travelers, corporate networks, legitimate VPNs, and business rules.

## 6. Designing Controllable, Explainable WAF Policies

A WAF enforces HTTP(S) rules for endpoints placed behind it. Rules can match methods, paths, headers, payload patterns, request traits, and bot signals depending on the product. **A WAF does not understand full business logic** and can generate false positives, requiring disciplined rule governance.

### 6.1. Managed Rules vs. Custom Rules

| Rule Group | When to Use | Risks or Limitations |
| --- | --- | --- |
| Provider-maintained managed rules | Reduce effort covering common web exploit classes | Can trigger false positives; automatic rule updates may alter behavior |
| Application-specific custom rules | Protect sensitive routes, restrict methods, block verified bad patterns | Easily drift as APIs evolve; require testing and clear owners |
| WAF rate-based rules | Curb traffic anomalies per supported keys/windows | Do not replace business quota limiters or app-state checks |
| Bot management & challenges | Curb automation on browser-friendly challenged flows | Unsuitable for many APIs, mobile clients, webhooks, or accessibility flows |
| Allowlists / exceptions | Permit verified special-purpose system flows | Overly broad exceptions punch holes through defenses |

Never disable rules globally just because one webhook or endpoint payload triggers a signature. **Scope exceptions narrowly by hostname, route, method, trusted source, and expiration**, and compensate with signature, token, or app-level validation.

### 6.2. Workflow for Promoting WAF Rules to Production

~~~mermaid
flowchart LR
    A["Analyze threats and endpoints"] --> B["Select managed/custom rule"]
    B --> C["Observe/Count/Log if supported"]
    C --> D["Evaluate valid traffic & false positives"]
    D --> E["Test in narrow scope"]
    E --> F["Promote to controlled Block/Challenge"]
    F --> G["Monitor, roll back, and tune"]
    G --> D
~~~

1. Assemble a **representative set of legitimate requests** covering web, mobile, APIs, payments, customer support, and specialized clients.
2. Start in observe/count mode where supported; gather metrics and sanitized log samples.
3. Classify expected matches, evaluate false-positive rates and missed-threat risks, and pick appropriate actions.
4. Roll out to a small traffic slice or production-like environment; record rule version, approver, and rollback criteria.
5. Promote rules incrementally to block/challenge while watching p95 latency, journey success rates, and user complaints.
6. Keep exceptions narrow with expiry dates; re-evaluate after application changes or managed rule updates.

**False positives** can cost revenue or drop webhooks, so track business impact alongside raw block counts. If a rule breaks valid traffic, roll back quickly while keeping remaining defensive layers intact.

### 6.3. A WAF Does Not Replace Application Security

A WAF helps block common injection or malformed requests, yet applications still must enforce:

- Authentication and **per-resource authorization** (preventing users from reading others' orders).
- Server-side input validation and parameterized queries or equivalent safe APIs.
- Session, secret, and token protection; client-appropriate CORS/CSRF controls.
- Idempotency and replay defense on mutating requests.
- Dependency patching, security testing, and anomaly monitoring.

For instance, a WAF may pass a syntactically valid order-lookup request yet **cannot know** whether Customer A is authorized to view Customer B's order. That check belongs strictly in the application and data layers.

## 7. Rate Limiting: Bounding by Real Behavior and Resource Cost

**Rate limiting** controls operation frequency or volume over time. It curbs abuse and allocates capacity fairly across clients, provided you pick **counting units and keys** aligned with business semantics.

| Limit Key | Best Suited For | Drawbacks to Address |
| --- | --- | --- |
| Source IP behind trusted proxy | Public entry points, unauthenticated calls, coarse detection | One IP can represent many valid users; bots rotate across many IPs |
| Account / user | Authenticated APIs and service usage policies | Abusers create multiple accounts; enterprise accounts differ from individuals |
| API key / client ID | Partners and API consumers | Keys must be guarded; multiple end clients may share one key |
| Tenant / organization | Multi-tenant SaaS with contractual quotas | Large tenants may need custom tiers; prevent noisy-neighbor exhaustion |
| Route / operation | Separating cheap searches from order writes, uploads, or exports | Must track route changes and reflect actual compute cost |
| Session or risk signal | Login flows, bot checks, challenges | Unreliable when cookies are blocked or non-browser clients call APIs |
| Multi-tier combinations | Protecting both global capacity and per-customer fairness | Define clear precedence and scope to avoid opaque overlapping limits |

**Never apply one global threshold across all routes** when processing costs and priorities differ. Viewing an image may hit cache, searching rooms may hit an index, while confirming a booking runs a transaction and calls a payment provider.

### 7.1. Token Buckets, Time Windows, and Bursts

A widely used pattern is the **token bucket**: each client group gets a maximum token capacity (burst size) and refills at a steady rate. Each request spends tokens; when empty, requests are rejected or queued per design.

Suppose each account is allowed **10 requests/sec with a maximum burst of 20 requests** on a read API. This is purely illustrative, not a recommended limit. With 20 tokens available, a sudden burst can spend up to 20 immediately; over sustained intervals, accepted rate converges to the 10 tokens/sec refill rate. Real behavior also reflects concurrency caps, processing latency, state sharing across gateways, and exact implementation details.

| Algorithm | Advantages | What to Check |
| --- | --- | --- |
| Fixed window counter | Simple to implement and count per interval | Prone to double bursts across window boundaries |
| Sliding window / rolling counter | Smooths boundary spikes depending on implementation | Higher state-storage overhead |
| Token bucket | Supports bounded bursts plus sustained average rate | Must define capacity, refill rate, and distributed state |
| Leaky bucket / queue | Smooths outbound processing rate | Excessive queuing adds latency, timeouts, and memory pressure |
| Concurrency limit | Caps simultaneous in-flight operations | Does not replace time-window caps or CPU/DB budgets |

### 7.2. Distributed Enforcement and Limit Consistency

Systems with multiple edge nodes, gateways, or regions must choose **global vs. local enforcement**. If each node tracks a separate bucket, aggregate accepted traffic can exceed intended caps. If every node queries a central state store synchronously on every request, the limiter becomes a bottleneck or shared failure point.

Options include local per-node limits for self-protection, distributed limits for high-value tenants, or **partitioned quota leases**. Document acceptable drift, sync intervals, and behavior when the limiter store is unavailable.

**Fail-open vs. fail-closed?** There is no universal answer. For low-risk read APIs, allowing bounded traffic during a limiter outage preserves availability; for sensitive write/costly operations, failing closed temporarily may be safer. Base the choice on risk, headroom, and approved policy.

### 7.3. Responding When Limits Are Exceeded

For HTTP APIs, **429 Too Many Requests** is the standard status for rate-limit rejections. A **Retry-After** header tells supporting clients how long to wait. Standardize error payloads and document limits in API contracts so clients implement backoff with jitter rather than synchronized retries.

When the overall system is capacity-exhausted, **503 Service Unavailable** often describes temporary overload more accurately than 429. Distinguishing causes helps clients and operators respond properly. Regardless, retry logic must **preserve idempotency** and cap attempts; never replay a payment mutation blindly just because a timeout left the outcome unknown.

### 7.4. Consumption-Based Limits Beyond Raw Request Counts

A report export request might burn 100× the CPU or DB I/O of a small record lookup. Combine:

- **Operations per second** keyed by identity and route.
- **Max concurrent export jobs** running simultaneously per tenant.
- **Request/upload size caps** and response payload limits.
- **DB query/connection caps** or execution timeouts in the application.
- **Bounded queues with explicit priority** for work eligible for async execution.

Calibrate these bounds through measurement. Policies tracking only requests/sec miss low-frequency, resource-heavy calls.

## 8. Limiting Blast Radius at the Entry Point

**Blast radius** is the scope of resources, services, and users affected when a fault or traffic anomaly strikes. Defense aims not only to drop requests at the edge, but to **prevent one route or tenant from taking down unrelated journeys**.

### 8.1. Prioritizing Journeys

In a booking system, teams might prioritize:

1. **Core flows:** booking status lookup, transaction confirmation, and access verification.
2. **Important flows with offload options:** search, room filtering, catalog browsing.
3. **Deferrable flows:** admin reports, non-urgent emails, batch analytics.

This order is illustrative; business owners must approve actual priorities. Under pressure, the system can serve static/cached pages, reduce recommendation refresh frequency, or defer reports—yet **must never return wrong booking statuses or confirm unverified payments**.

### 8.2. Blast-Radius Containment Techniques

| Technique | What It Protects | Limitations or Trade-Offs |
| --- | --- | --- |
| Entry isolation by hostname/route/tenant | Stops one route or customer group from starving global quotas | Does not automatically isolate CPU/DB if backends are shared |
| Concurrency limits / bulkheads | Keeps active work below safe ceilings at gateway and downstream | Excess traffic must be rejected or queued |
| Bounded queues & backpressure | Smooths async work; shields write services/workers | Overly deep queues inflate wait times, cost, and OOM risk |
| Timeouts & cancellation | Prevents slow partners or DBs from tying up resources indefinitely | Overly tight timeouts drop valid slow operations |
| Circuit breakers | Temporarily sheds calls to persistently failing dependencies | Needs safe recovery probing and avoids shifting load destructively |
| Caching with tuned TTLs | Offloads repeated reads | Requires managing PII, stampedes, and acceptable staleness |
| Load shedding | Drops lower-priority work during overload | Requires clear business priorities and consistent responses |
| DB / connection pool caps | Stops apps from opening excessive DB connections/transactions | Caps peak throughput; requires monitoring saturation |

For example, if search can receive 2,000 requests/sec while the DB handles only 300 heavy queries/sec, adding more API instances without caching, concurrency caps, or query tuning simply saturates the DB faster. **Place limits close to where cost is incurred and directly around the protected resource**.

### 8.3. Blast-Radius Isolation by Path

~~~mermaid
flowchart LR
    NET["Internet / anomalous traffic"]
    EDGE["Edge DDoS protection + WAF"]
    GW["API Gateway: auth, rate, concurrency"]
    READ["Search: cache / read replicas"]
    WRITE["Booking: queue, idempotency, DB pool"]
    DB[("Database")]
    PAYMENT["Payment provider"]
    NET --> EDGE --> GW
    GW -->|Read| READ
    GW -->|Write| WRITE
    WRITE --> DB
    WRITE -->|Timeout + reconciliation| PAYMENT
~~~

Read and write paths need limits matching their data semantics. **Sharing a single DB or gateway** can still couple them; monitor CPU, connection pools, and quotas, and build real execution bulkheads rather than merely drawing separate route labels.

### 8.4. Protecting Multi-Tenant Systems from Noisy Neighbors

In SaaS platforms, large customers legitimately consume more resources than small ones. Average quotas should align with contracts, entitlements, and real capacity—combining **per-tenant quotas** with global safety caps. Prioritization must never trust unverified client-supplied labels.

When one tenant breaches its quota, degradation should stay scoped to that tenant's allocation while preserving capacity for others. If all tenants share one unbounded connection pool, edge rate limits alone rarely guarantee isolation.

## 9. Protecting Web, API, Webhook, and Admin Entry Points Differently

Never enforce identical policies across dissimilar client types:

| Entry Point | Characteristics | Essential Controls |
| --- | --- | --- |
| Public website | Browsers, partially cacheable content, UX-sensitive | CDN/caching, tuned WAF, TLS, careful bot detection, risk-based rate limits |
| Mobile API | Automated clients, many devices behind carrier NAT, often cannot solve browser challenges | Token auth, account/client rate limits, versioning, valid request bounds |
| Partner API | Contracted app identities, scheduled traffic, dedicated quotas | API keys/OAuth or suitable auth, per-client limits, audits, retry contracts |
| Payment webhook | Partner-pushed events, may arrive duplicated or out of order | Signature and timestamp/nonce verification if supported, idempotency, queues, size caps, replay defense |
| Admin endpoints | Few users, privileged permissions, high-risk actions | Keep non-public if unnecessary, MFA, restricted access, auditing, granular authz |
| Health checks | Polled frequently by infrastructure | Source/tier-scoped rules; never expose sensitive diagnostics |

### 9.1. Never Force Webhooks Through CAPTCHAs

Placing browser challenges on webhook routes blocks payment providers from delivering notifications, leaving bookings stuck even after payment succeeded. For webhooks, prioritize **message signature verification, verified/published source checks where reliable, payload validation, blast-radius limits, deduplication, and reconciliation**.

Likewise, never exempt webhooks completely from the WAF due to a single false positive. Keep exceptions narrow and pair them with compensating controls. Provider-published IPs can change; IP allowlists without cryptographic signature verification are rarely sufficient.

### 9.2. Guarding Sensitive Write Paths with Idempotency

Suppose a booking request times out on the client and retries. Rate limiting reduces retry frequency, yet **cannot prevent every duplicate write**. Applications need stable idempotency keys/transaction IDs, concurrency rules, and status-returning handlers when a prior request already succeeded or is in flight.

Retries must never be treated blindly as fresh transactions. Systems also need payment-gateway reconciliation when network errors obscure final transaction state.

## 10. Availability Controls and Hidden Entry-Point Dependencies

Public entry points depend on many systems outside the app process: DNS, certificates, edge networks, WAF policies, API Gateways, identity providers, rate-limit counters, origin routes, and telemetry. A bad config change in a shared component can impact **every** request across multiple regions.

### 10.1. Identifying Failure Domains and Redundancy

- **Multi-AZ:** limits single-zone impact, provided LBs still retain healthy capacity and DBs/dependencies are also zone-resilient.
- **Multi-region:** survives regional connectivity loss only when data, DNS/routing, identity, quotas, and failover runbooks are ready. Never assume "multi-region" automatically yields good RTO/RPO.
- **Global entry points:** identify shared provider control planes, fallback paths, and operations when a control plane becomes unreachable.
- **DDoS protection & WAF:** ensure policy deployment, rollbacks, and protections cover all entry paths, including standby routes.
- **Identity & rate-limit stores:** define per-API behavior when shared dependencies slow down or fail rather than letting all requests hang indefinitely.

### 10.2. Never Let Failover Routes Become Security Bypasses

Failing over DNS to a standby origin lacking equivalent security controls lets malicious traffic enter through the backup path. Conversely, if you rely on a single WAF/edge provider and it suffers an outage, your failover design must specify **approved fallback procedures and accepted risks**.

Verify standby routes with the same rigor as primary paths: TLS, WAF/rate limits where applicable, authentication, network isolation, data controls, logging, and cutover rules. Never build a backup route merely to pass shallow health checks without testing live incident behavior.

## 11. Monitoring, Alerting, and Impact Assessment

Entry-point defense requires visibility across **three layers: incoming traffic, control effectiveness, and downstream business health**.

| Metric Group | Examples to Track | Decision Supported |
| --- | --- | --- |
| L3/L4 traffic | Bandwidth, connections/s, packets/s, handshake failures, DDoS service signals | Is congestion occurring ahead of WAF/origin? |
| L7 requests | RPS by hostname/route, status codes, payload sizes, user agents, valid client traits | Which routes are surging—campaign traffic or attack? |
| WAF / bots | Allow/block/challenge/count rates, rule IDs, suspicion scores, sampled false positives | Which rules reduce risk vs. block real users? |
| Rate limiting | 429s by identity/route/tenant, remaining quotas, retry rates | Are limits calibrated or degrading UX? |
| Edge & backend performance | p95/p99 latency, backend errors, connection pools, queue depth, CPU/DB saturation | Are edge controls actually relieving protected backends? |
| Business outcomes | Successful logins, searches, booking completions, valid webhook processing | Are real users still finishing core journeys? |
| Cost | WAF requests, CDN bandwidth, egress, log volume, contracted DDoS/monitoring fees | Is defense or attack traffic exceeding budget projections? |

**Protect logs and sensitive data:** never log passwords, tokens, session cookies, payment fields, or full request bodies by default in WAF/access logs. Enforce redaction, read RBAC, retention limits, and compliant log residency.

### 11.1. Minimum Questions a Dashboard Must Answer

1. How are requests/sec and bandwidth shifting at each entry point?
2. How do HTTP 2xx/4xx/5xx, 429, and challenge responses break down by route and tenant?
3. How many requests are rejected before reaching the origin, and what is the estimated false-positive rate?
4. Is saturation shifting from the edge down into apps, DBs, or partners?
5. Are search and booking journeys still meeting SLOs?
6. Can on-call immediately identify the active WAF rule version and latest config change?

Alert on meaningful thresholds across error rates, latency, backend saturation, WAF blocks, and 429s. Alerting solely on "RPS spike" triggers false alarms during promotions; correlate **system health, security signals, and user outcomes**.

### 11.2. Distinguishing Real Attack Impact

A traffic flood absorbed at the edge while backends stay healthy is very different from an event causing data outages. Post-incident reviews should record start/end timestamps, affected request scopes, triggered thresholds, impactful rules, estimated legitimate user impact, recovery time, cost, and follow-up hardening.

## 12. Entry-Point Incident Response Workflow

A defense runbook must state **who approves policy changes, what to adjust, how to measure impact, and when to roll back**.

~~~mermaid
flowchart TD
    A["Detect anomaly at edge/gateway"] --> B["Verify business SLIs and DDoS/bot signals"]
    B --> C{"Which layer is impacted?"}
    C -->|L3/L4| D["Coordinate upstream / network provider defenses"]
    C -->|L7/API| E["Inspect WAF rules, rate limits, cache, and backend load"]
    D --> F["Apply time-bound approved mitigations"]
    E --> F
    F --> G["Measure valid success, false positives, p95, and cost"]
    G --> H{"Back within acceptable bounds?"}
    H -->|No| B
    H -->|Yes| I["Stabilize, document timeline, review prevention"]
~~~

### Reference Procedure

1. **Triage:** identify impacted targets, trusted telemetry, legitimate traffic baselines, and active risks; distinguish infrastructure DDoS, L7 abuse, bots, misconfigurations, and flash crowds.
2. **Isolate:** pinpoint affected hostnames/routes/tenants, saturated downstream dependencies, and required protection levels. Engage upstream providers if network links saturate.
3. **Mitigate within bounds:** adjust managed/custom WAF rules, rate limits, caching, access policies, or concurrency caps per approved runbook.
4. **Measure continuously:** watch legitimate user success, p95 latency, error budgets, WAF false positives, connection pools, and cost. Never treat higher block counts alone as proof of success.
5. **Shift/recover critical journeys:** on write paths, protect consistency and reconciliation; on read paths, serve cached data where business rules permit.
6. **Restore normal configuration safely:** roll back temporary emergency rules once unneeded; never leave overly broad blocklists or open exceptions indefinitely.
7. **Learn and update:** refine load models, policies, tests, cost forecasts, and ownership; retain evidence for Well-Architected reviews.

Keep permissions clear: on-call SREs may execute pre-approved mitigations; sensitive changes require security or service owner approval; emergency access must be audited. In multi-vendor stacks, document contacts for ISPs, cloud providers, and CDN/WAF vendors.

## 13. Applying to the Booking Platform: Entry-Point Defense Matrix

Assume the system serves four customer routes and one partner route, each with distinct cost and risk profiles:

| Route | Edge Protections | Gateway / App Limits | Blast-Radius Mitigation |
| --- | --- | --- | --- |
| `GET /rooms/search` | Tuned WAF, bot protection, CDN caching for eligible responses | Scoped identity/IP limits; cap expensive queries | Tune indexes, cache results, shed heavy filters under high load |
| `POST /auth/login` | WAF, abuse detection, client-appropriate challenges | Account and risk-signal rate limits; MFA where warranted | Isolate auth pools, alert on anomalous login spikes |
| `POST /bookings` | WAF, TLS, auth; never cache transaction outcomes arbitrarily | Dedicated rate & concurrency caps, idempotency, authz, DB transactions | Guard DB pool, return clear processing status when dependencies lag |
| `GET /bookings/{id}` | WAF and authentication | Per-order authorization, per-user read limits | Never cross-cache across users; prioritize status lookups |
| `POST /payments/webhook` | Dedicated WAF rules without browser challenges | Message signatures, idempotency, body size caps, bounded queues | Reconcile during slowdowns; never lose state on duplicate deliveries |

**Note:** routes and controls are logical examples; adapt them to API contracts, payment integrations, WAF product features, and compliance mandates. If a WAF rule blocks valid webhooks, prefer **narrow, controlled exceptions** paired with application-level signature verification.

### 13.1. Vendor-Neutral Policy Template for Discussion

This illustrates **design intent**, not deployable YAML for a specific cloud service:

~~~yaml
edgePolicy:
  hostname: api.example.invalid
  tlsRequired: true
  allowedEntry:
    - approved-edge
  waf:
    managedRules:
      mode: monitor-then-enforce
    exceptions:
      - route: POST /payments/webhook
        reason: Never apply browser challenges to machine-to-machine clients
        compensatingControls:
          - verify-webhook-signature
          - idempotent-event-processing
  limits:
    search:
      identity: authenticated-user-or-trusted-client-signal
      algorithm: token-bucket
      ratePerSecond: 10   # Hypothetical value, do not apply by default
      burst: 20           # Needs tuning for load and false positives
    booking:
      identity: authenticated-user
      requireIdempotency: true
      concurrencyControl: enabled
  monitoring:
    - edge-http-latency
    - waf-action-by-rule
    - backend-error-rate
    - completed-bookings
    - false-positive-review
~~~

Before deploying to production, verify that your cloud tooling supports the exact **limiter types, identity keys, WAF actions, and network scopes** described. The 10 req/sec rate and 20 burst merely illustrate mechanics and must not be adopted without live traffic evidence.

### 13.2. Validation Through Authorized Testing

| Scenario | Outcomes to Verify |
| --- | --- |
| Valid web/mobile requests | Traverse edge, TLS, and auth cleanly; never falsely blocked by new WAF rules |
| Invalid HTTP payloads in safe test suite | Filtered/logged as expected with matching rule IDs and evidence |
| Campaign-scale valid traffic in test env | Scales/throttles smoothly; p95 and success rates meet agreed targets |
| Client exceeding API limits in approved load test | Receives expected limit responses without crashing gateway/backends or harming other clients |
| Duplicate valid webhooks per integration contract | Business effect executes once; state and audit logs stay accurate |
| Slow backend or saturated DB | Concurrency caps, queues, and timeouts protect resources; independent flows keep serving |
| Direct origin access bypassing entry point | Rejected by network/auth policies; no WAF bypass |
| New WAF rule falsely blocks customers | Detected via SLIs/logs, rolled back, and valid traffic restored within SLA |

Never generate destructive traffic against public services or unauthorized infrastructure. Run load and fault tests in controlled environments within approved bounds, scheduled windows, and kill-switch capability; exercises should simulate defensive signals rather than launching real DDoS attacks.

## 14. Cost, Operations, and Well-Architected Trade-Offs

Defensive costs can include advanced DDoS services, CDN/WAF, rule/rate-rule charges, inspected requests or bandwidth, bot challenges, load balancers, egress, logs, monitoring, and on-call staffing. Billing models vary by product, so review exact pricing docs. **Traffic blocked early reduces backend compute yet may still incur edge or logging charges** depending on the vendor.

| Pillar | Evaluation Questions |
| --- | --- |
| **Security** | Do public routes have tuned WAF, TLS, authn, authz, and origin-bypass prevention? |
| **Reliability** | Under overload, are critical journeys preserved, detected early, and shielded from single points of edge failure? |
| **Performance Efficiency** | Do caching, rate limits, and concurrency protect DBs while keeping p95 healthy for valid customers? |
| **Operational Excellence** | Are owners, runbooks, rule tests, false-positive tracking, rollbacks, and vendor escalation paths active? |
| **Cost Optimization** | Are request/traffic/log volumes, protection fees, and attack surge scenarios modeled to avoid runaway bills? |
| **Sustainability** | Are wasteful requests and redundant work minimized via caching without excessive idle capacity? |

Make trade-offs explicit: stricter WAF filtering cuts attacks yet raises false positives; more challenges curb bots yet hurt UX; extra intermediary tiers add latency, spend, and failure modes; larger headroom absorbs bursts yet costs budget. **Base decisions on goals and evidence**, not the number of security checkboxes enabled.

## 15. Practice Exercise: Entry-Point Defense for a Booking System

**Scenario:** a booking platform is expanding from one region to multiple regions. Room-search traffic fluctuates sharply during holidays. The order-creation API writes to the database, and payment webhooks arrive from an external partner. The company requires protecting the origin, curbing bot abuse, and keeping critical journeys online under anomalous load.

**Tasks:**

1. **Build a threat model:** list at least three risks across L3/L4/L7, affected targets, appropriate blocking points, and permitted behaviors.
2. **Draw the ingress path** from clients through DNS, DDoS protection, WAF, API Gateway/LB to private workloads; mark TLS termination and how origin bypass is blocked.
3. **Design route-specific policies for all five routes** listed; pick rate-limit keys, over-limit actions, and why webhooks skip challenges.
4. **Propose bulkheads** for search, booking, and reporting jobs; identify what can be cached/queued vs. what demands immediate consistency.
5. **Define four acceptance criteria** covering business SLIs, p95, false positives, and incident detection, plus telemetry tools.
6. **Walk through two incidents:** a WAF rule falsely blocking real customers and a surge saturating the DB. Outline triage, mitigation, rollback, and recovery proof.
7. **Estimate costs** across CDN, WAF, DDoS protection, gateway, data transfer, and logs under normal, peak, and attack loads; list assumptions needing verification.
8. **Write a concise ADR** covering entry-point design, options considered, trade-offs across security, performance, reliability, and budget, plus revisit triggers.

### Completion Criteria

| Criterion | Indicator of Completion |
| --- | --- |
| Layered defense | Distinguishes WAF from upstream volumetric DDoS mitigation; places controls at matching layers |
| Endpoint-specific protection | Separate policies for search, booking, login, and webhooks; app-layer authz preserved |
| Blast-radius containment | Clear rate, concurrency, timeout, and queue goals; search surges cannot corrupt bookings |
| False-positive prevention | Uses valid test suites, false-positive metrics, canary rollouts, and WAF rollbacks |
| Operability | Clear SLIs, alerts, owners, runbooks, and verified incident workflows |
| Cost governance | Models edge/log spend under anomalous load with clear spend-escalation owners |

## 16. Pre-Production Entry-Point Checklist

- [ ] Inventoried all externally reachable hostnames, routes, ports, and allowed client types.
- [ ] Reviewed upstream L3/L4 defenses and verified exact scope and limits of DDoS services.
- [ ] Locked down origin against paths bypassing WAF/CDN/gateway.
- [ ] Documented TLS termination, edge–origin encryption, and trusted proxy chains for client IPs.
- [ ] Grouped endpoints by risk, sensitivity, and compute cost rather than applying one uniform rule.
- [ ] Tested managed/custom WAF rules, false positives, policy updates, and rollback paths.
- [ ] Configured identity/tenant/route rate limits alongside 429/503 responses and safe retries.
- [ ] Defined concurrency caps, request size limits, timeouts, queues, and DB protections.
- [ ] Secured webhooks with message authentication, deduplication, and narrowly scoped WAF exceptions where needed.
- [ ] Tested graceful degradation and fault tolerance when a dependency or edge tier fails.
- [ ] Built unified dashboards correlating traffic, WAF actions, p95 latency, backend errors, business outcomes, and cost.
- [ ] Assigned on-call responders, upstream vendor escalation contacts, emergency change permissions, and rollback runbooks.
- [ ] Tested standby failover paths and verified security controls match primary paths.
- [ ] Recorded Well-Architected decisions and trade-offs in an evidence-backed ADR.

Effective entry-point defense comes from **layered architecture and blast-radius control**, spanning network DDoS mitigation through WAF, API throttling, and backend resource protection. Only when those layers are validated against legitimate user journeys, latency measurements, false-positive rates, failure drills, and clear operations does a system have a solid foundation to stay online under abnormal load.
