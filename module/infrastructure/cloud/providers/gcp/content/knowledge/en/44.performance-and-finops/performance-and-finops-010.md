# Optimizing Network Paths and Data Transfer Costs

An application can use minimal CPU and memory yet still generate significant Google Cloud charges if data constantly crosses zone, region, Internet, load balancer, or hybrid boundaries. For example, a Java API running in one region reads a database in another region, fetches an object from Cloud Storage, and proxies the entire file through the API back to the client. When every request repeats that path, data transfer costs and latency can grow faster with user volume than compute costs.

**Network path optimization** is the practice of mapping actual data flows, understanding where charges apply, and eliminating unnecessary transfers while maintaining reliability, resilience, security, and user experience. **Network FinOps** adds measurement, cost accountability, unit economics, and post-change verification.

This lesson belongs to the **Performance and FinOps** chapter of the **CLOUD_PROVIDERS_GCP** module. Across the journey from project organization, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage, and databases, learners need to know how to choose services, protect resources, automate releases, and track reliability alongside cost. Here, we combine Google Cloud networking architecture with controlled measurement, optimization, and verification practices.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish ingress, egress, intra-zone, cross-zone, inter-region, Internet, and hybrid data transfer.
- Explain why a single traffic flow can incur multiple SKUs: data transfer, NAT, load balancing, CDN, storage operations, and related services.
- Use Cloud Billing, BigQuery Billing export, Network Topology, VPC Flow Logs, and metrics to locate cost drivers.
- Evaluate placement across APIs, databases, workers, caches, and Cloud Storage.
- Choose among internal path optimization, Cloud CDN, private connectivity, and Network Service Tiers.
- Design Java/Spring application optimizations using caching, batching, pagination, compression, and direct object downloads.
- Estimate impacts on latency, RTO/RPO, HA, security, and cost before making changes.
- Build a testing, monitoring, and rollback runbook for a network change.

## 1. Start with the Data Flow, Not the Price Sheet

Suppose an e-commerce system includes:

- Web and mobile clients on the Internet.
- An External Application Load Balancer.
- Java APIs on Cloud Run or GKE.
- Cloud SQL storing order data.
- Cloud Storage storing images and attachments.
- Workers processing events from Pub/Sub.
- An ERP system still hosted in an on-premises data center.

The connections carry different data flows:

~~~mermaid
flowchart LR
  U[Users on Internet] --> LB[External Application Load Balancer]
  LB --> API[Orders Java API]
  API --> DB[(Cloud SQL)]
  API --> GCS[(Cloud Storage)]
  API --> W[Pub/Sub / workers]
  API --> NAT[Cloud NAT / external egress]
  NAT --> ERP[ERP / third parties]
  GCS --> CDN[Cloud CDN if appropriate]
  CDN --> U
  API -. logs / traces .-> OBS[Cloud Logging / Monitoring / Trace]
~~~

This is a logical diagram and does not claim every path traverses Cloud NAT. For example, connecting to Cloud SQL over private IP and calling certain Google APIs may bypass Internet NAT paths; which endpoint is used and how it is billed must be checked per service.

To uncover optimization opportunities, ask five questions for **each connection path**:

1. Who is the sender and who is the receiver?
2. Are the endpoints in the same zone, same region, different regions, Internet, or on-premises?
3. How many GiB and how many requests travel per day or month?
4. Does this flow truly need to traverse every current hop?
5. Will changing the path affect security, latency, SLAs, or fault tolerance?

A network diagram showing static configuration is not enough. You need **actual traffic telemetry**, including peak hours, end-of-day batches, replication, and backup runs.

## 2. Distinguishing Types of Data Transfer

The single most important concept: **ingress is usually billed differently from egress**, and "staying inside Google Cloud" does not mean every transfer is free.

| Transfer Direction | Example | What to Check |
|---|---|---|
| Ingress into Google Cloud | Clients sending requests to API | Service-specific ingress pricing; note load balancer and processing fees |
| Intra-zone | VM A → VM B in same zone | Eligibility conditions for VM-to-VM using internal/IPv6 addresses and network tier/type |
| Cross-zone same region | VM in zone A → VM in zone B | May incur data transfer out per GiB |
| Inter-region | Backend in region A → DB in region B | Rates vary by region pair and involved services |
| Internet egress | API returning responses to users | Pricing by region, tier, volume, and product type |
| Hybrid egress | Google Cloud → on-prem via VPN/Interconnect | Connection, traffic, and associated infrastructure charges |
| Cloud Storage data transfer | Bucket → service in another location | Dedicated Cloud Storage pricing table and exceptions |
| CDN delivery/cache fill | CDN cache → client; origin → cache | Cache lookup, cache data transfer out, cache fill, and other components |

According to **Google Cloud VM-to-VM pricing**, intra-zone traffic using internal addresses under specified conditions may have zero data transfer charge; cross-zone within the same region and inter-region VM-to-VM follow different rules. However, never generalize from VM-to-VM rules that **every** GCP service is free within the same region. Cloud Run, Cloud SQL, Cloud Storage, load balancing, and other products have separate pricing tables.

### Ingress Does Not Make the Whole Request Free

Even when inbound data transfer is not billed under a specific network SKU, the system can still incur fees for:

- External Application Load Balancer forwarding rules and data processing.
- Cloud Armor if enabled.
- Cloud NAT or Private Service Connect when billable traffic applies.
- Cloud Run/GKE CPU/memory and request counts.
- Logging, tracing, or storage operations triggered by the request.

Optimization must examine **total cost per transaction**, not just a single "Network Internet Egress" line item.

### GiB, GB, and Billing Units

Google Cloud pricing tables explicitly specify units (GiB, GB, requests, hours). One GiB equals $2^{30}$ bytes, whereas one GB equals $10^9$ bytes. When modeling costs, match the exact unit in the SKU/Cloud Billing export rather than mixing "GB" reported by a monitoring tool with "GiB" on a pricing page.

## 3. Modeling Paths and Per-Hop Costs

In FinOps, a single request path can generate charges at multiple hops. Example:

~~~mermaid
flowchart TD
  A[Browser downloads 8 MB image] --> B[Global external LB]
  B --> C{CDN cache hit?}
  C -->|Yes| D[Serve from edge cache]
  C -->|No| E[Cloud Storage / backend origin]
  E --> F[Cache fill]
  F --> D
  D --> G[Internet client]
~~~

On a CDN cache hit, the origin avoids re-serving the entire payload for that request. Yet never assume "CDN is free" because there can still be **cache lookup**, **cache data transfer out**, **cache fill** on misses, and corresponding load balancing or storage operation charges.

In Cloud CDN, a cacheable response must satisfy caching rules and HTTP headers. Personalized content or sensitive data requires careful cache key design and access controls—or must not be cached at all.

### General Cost Formula

An estimation model uses:

~~~text
Network-related monthly cost
  = sum(data transfer GiB by route x applicable SKU price)
  + NAT gateway hours + NAT processed traffic + NAT IP hours
  + load balancer fixed and processing charges
  + CDN cache lookup + cache fill + cache data transfer out
  + VPN/Interconnect/PSC-related charges where applicable
  + applicable storage and service operations
  - discounts and credits allocated to those usage lines
~~~

This is a **classification framework**, not an accounting formula where every line item is blindly summed. Some billing mechanisms replace others; for example, Cloud CDN cacheable traffic follows its own pricing structure. Always verify **actual SKUs** so traffic is never double-counted.

### Traffic Inventory Table to Build

| Source | Destination | Region / Zone | Traffic | GiB/Month | p95 Latency | Owner | Cost Hypothesis |
|---|---|---|---|---:|---:|---|---|
| orders-api | Cloud SQL | Same region | JDBC | Unmeasured | Unmeasured | backend | Lower egress with proper placement |
| orders-api | Cloud Storage | Different region | Object reads | Unmeasured | Unmeasured | media | Inter-location transfer |
| worker | warehouse | Different region | Batch ETL | Unmeasured | Unmeasured | data | Inter-region traffic |
| browser | backend/CDN | Internet | File downloads | Unmeasured | Unmeasured | frontend | Internet/CDN egress |
| orders-api | ERP | Hybrid | HTTPS | Unmeasured | Unmeasured | integration | VPN/Interconnect + transfer |

Never fill hypothetical guesses into a production inventory table. Mark cells "Unmeasured" and assign owners to collect measurements before deciding.

## 4. Measuring Current State with Cloud Billing

**Cloud Billing Reports** is the starting point for viewing costs by service, project, SKU, location, label, and time range. Across multiple projects or workloads, enable **Cloud Billing export to BigQuery** for granular, repeatable analysis.

### Execution Steps

1. Select the right billing account for the projects under investigation.
2. Inspect 30–90 days of spend plus any peak windows.
3. Group by services or SKUs tied to data transfer, NAT, load balancing, Cloud CDN, and connectivity.
4. Filter by project, location, and existing labels.
5. Correlate cost share against request counts, bytes transferred, and release events.
6. Enable Billing export if you need daily, project, SKU, or owner-level SQL breakdowns.
7. Establish a baseline with an explicit start date before making changes.

**Do not track total dollars alone:** a workload whose traffic doubles while cost per request falls can still be a FinOps win. Watch both **absolute cost** and **unit cost**.

### Example SQL for Billing Export

Assume **Standard usage cost export** is enabled with the standard schema. Replace project, dataset, table name, and dates; then refine SKU filters to match **actual SKU names in your account**:

~~~sql
SELECT
  DATE(usage_start_time) AS usage_date,
  project.id AS project_id,
  service.description AS service_name,
  sku.description AS sku_name,
  SUM(cost) AS gross_cost,
  SUM(
    COALESCE(
      (SELECT SUM(credit.amount) FROM UNNEST(credits) AS credit),
      0
    )
  ) AS credits,
  SUM(
    cost +
    COALESCE(
      (SELECT SUM(credit.amount) FROM UNNEST(credits) AS credit),
      0
    )
  ) AS net_cost
FROM
  `BILLING_PROJECT.BILLING_DATASET.gcp_billing_export_v1_ACCOUNT_ID`
WHERE
  usage_start_time >= TIMESTAMP('2026-10-01')
  AND usage_start_time < TIMESTAMP('2026-11-01')
  AND (
    LOWER(sku.description) LIKE '%data transfer%'
    OR LOWER(sku.description) LIKE '%egress%'
    OR LOWER(sku.description) LIKE '%nat%'
    OR LOWER(sku.description) LIKE '%load balancing%'
    OR LOWER(sku.description) LIKE '%cdn%'
  )
GROUP BY 1, 2, 3, 4
ORDER BY net_cost DESC;
~~~

Note: SKU names use varied terminology and may change over time. The filter above is an **exploratory query** and is not guaranteed to capture all network-related charges. For final financial reporting, build SKU lists from actual export rows while accounting for credits, adjustments, taxes, and internal allocation rules.

Billing export does not always provide identical resource-level detail across every product. Detailed export adds resource-level data where supported; GKE cost allocation data may need separate enablement. Export updates have latency, so never rely on them for real-time incident response.

## 5. Measuring Network Paths with Network Intelligence Center

Google Cloud **Network Intelligence Center** offers tools to move from static network configs to observed evidence:

| Tool | What It Does | What Not to Infer |
|---|---|---|
| Network Topology | Visualizes resources and observed egress across zones, regions, Internet, and hybrid links | Does not show every app-level dependency or flows inactive during the window |
| Connectivity Tests | Analyzes configured forwarding paths, reachability, and certain live dataplane checks | Does not guarantee production performance or every backend |
| Performance Dashboard | Shows packet loss/latency between supported zones or regions | Does not replace business p95 latency |
| Flow Analyzer / VPC Flow Logs | Analyzes source–destination flows, ports, and bytes | Does not automatically explain business intent or capture every connection |
| Network Analyzer | Detects configuration, routing, and service networking issues | Not a final billing calculator |

### Network Topology

Open Network Intelligence Center > Network Topology. Filter by:

- Traffic type: **cross-zonal**, **to the internet**, **hybrid**.
- Projects and resources with high egress.
- Timeframes matching cost spikes.
- VMs/instance groups or GKE workloads (where supported).

Per documentation, Network Topology can surface **High egress instances** and **High egress instance groups** insights alongside average throughput, packet loss, and latency metrics where supported. Topology reflects observed traffic that actually occurred, not every declared dependency.

For instance, if an API and Redis sit in different zones, the cross-zone egress chart may show heavy traffic. Before changing placement, confirm it is genuinely cache traffic using metrics, flow logs, or application tracing.

### Connectivity Tests

Use Connectivity Tests to validate forwarding paths before and after VPC, route, firewall, private endpoint, or load balancer changes. Some scenarios support live dataplane checks, yet a single test never substitutes for real load benchmarks because ECMP and load balancers distribute across different backends.

### VPC Flow Logs / Flow Analyzer

Flow Logs help identify source/destination IPs, ports, protocols, volumes, and timestamps. However, logs may be sampled/aggregated, incur Cloud Logging costs, and rarely explain application-level semantics. When collecting them, record sampling config and time range, and never equate raw flow-log bytes directly with total billed GiB.

Use labels, resource metadata, application catalogs, and ownership to map flows to workloads; never assume traffic to port 5432 is definitely a specific application's PostgreSQL transaction without verification.

## 6. Optimizing Placement: Bringing Chatty Components Closer Together

One of the most durable improvements is **cutting traffic across billing and latency boundaries**.

### API and Database

If a Java API runs in `asia-southeast1` while its database sits in another region, every query/response adds RTT and transfer fees. For OLTP apps issuing many small queries, extra latency also holds threads and connection pool slots longer.

Options to consider:

- Place the API and database in the **same region** when product needs, data residency, and DR permit.
- Use private connectivity and supported endpoints.
- Avoid microservices repeatedly calling a remote database when caching, read replicas, or service-local data can work.
- Measure end-to-end transaction latency after changes; do not measure ping alone.
- Inspect cross-zone behavior under HA: HA databases and regional GKE clusters generate intra-region cross-zone traffic, so check product pricing accordingly.

**Never cram all workloads into one zone solely to dodge cross-zone charges.** Doing so can destroy high availability if that zone fails. Cost savings must be weighed against RTO/RPO, SLOs, and outage impact.

### Data Gravity and Analytics Services

Data gravity describes the tendency for compute to belong near large datasets to avoid repeated transfers. If image-processing workers read from a bucket in a distant region:

1. Measure object bytes read per day and re-read counts.
2. Check bucket location and worker location.
3. Evaluate moving workers closer to data or reshaping the pipeline.
4. If multi-region replication is required, add storage, replication, and consistency costs.
5. Choose based on data residency and recovery needs.

With Cloud Storage, **a single region is not automatically treated as the same location as a multi-region containing it** for data transfer pricing rules. Check pricing tables for the exact bucket location and service consumer.

### Placing Caches or Replicas Near Consumers

Local or regional caches can cut repeated reads to databases or buckets in another region. Still, caching requires:

- Appropriate TTLs.
- Invalidation or event-driven refresh rules.
- Controls for sensitive data.
- Monitoring hit rates, staleness, and memory.
- Accounting for the cache's own operational cost.

For data replicas, understand replication lag and read-after-write consistency. Never rely on eventual consistency for flows requiring immediate visibility of new writes unless proper guarantees exist.

## 7. Multi-Zone and Multi-Region Architecture: Reliability-Constrained Optimization

Production applications typically span multiple zones/regions for availability and disaster recovery. Data transfer fees are part of the **cost of resilience**, not automatically waste.

| Goal | Choice | Trade-Off |
|---|---|---|
| Survive zone failure | Regional GKE cluster, HA database, multi-zone backend | Cross-zone traffic and replication |
| Survive region failure | Multi-region deployment/replication | Inter-region transfer, storage, and ops complexity |
| Global user latency | Multi-region frontends or CDN | Data sync, caching, routing complexity |
| Operational simplicity | Fewer regions when SLOs allow | Larger blast radius |
| Reduce data gravity | Co-locate jobs with data sources | Higher latency for distant consumers |

### Set Explicit Constraints

Suppose a system targets a 99.95% SLO, 15-minute RTO, and 5-minute RPO. Never propose disabling multi-zone database replication just to trim egress bills. Instead, eliminate **unnecessary business traffic** (polling, duplicate batches, bloated payloads) first; then evaluate alternative HA designs that still satisfy RTO/RPO.

### GKE and Pod Placement

On GKE, pod-to-pod traffic can traverse nodes in different zones. Use topology spread constraints, affinity, or placement-aware designs to account for locality among chatty components. However:

- Do not break replica distribution needed for HA.
- Avoid hardcoding zones in ways that hinder autoscaling or node recovery.
- Monitor cross-zone flows and Service routing policies.
- Decouple bulk data transfers from synchronous transaction paths whenever possible.

## 8. Cloud CDN: Cutting Origin Hits, Not Just Latency

Cloud CDN fits content requested repeatedly by many users: public images, static assets, JavaScript bundles, CSS, non-personalized documents, or explicitly designed cacheable API responses.

### When Does CDN Pay Off?

Imagine 1 million downloads of the same image per month. If every request hits the origin, the origin processes and transfers the image every time. With a high cache hit ratio, CDN serves most requests from the edge, cutting origin load and improving client latency.

Metrics to monitor:

- **Hit ratio** by request count and by bytes.
- Cache fill bytes.
- Cache data transfer out.
- Cache lookup requests.
- Origin traffic and CPU.
- Client p50/p95 latency.
- Invalidation/revalidation rate.

### Cache Modes

Cloud CDN supports cache modes such as:

- `CACHE_ALL_STATIC`: default suitable for cacheable static content.
- `USE_ORIGIN_HEADERS`: obeys valid cache directives returned by the origin.
- `FORCE_CACHE_ALL`: forces caching of successful responses regardless of origin private/no-store headers; **never use for personal, paid, or access-controlled data**.

Use HTTP headers such as `Cache-Control`, `CDN-Cache-Control`, `ETag`, and `Last-Modified` appropriately. Scope cache keys to hostnames, protocols, query strings, headers, or cookies only when they genuinely alter content.

### Illustrative Java Response

In Spring Boot, public assets versioned by hash in the URL can emit cache directives:

~~~java
@GetMapping("/public/assets/{hash}/{fileName}")
public ResponseEntity<Resource> publicAsset(
        @PathVariable String hash,
        @PathVariable String fileName) {
    Resource body = findApprovedPublicAsset(hash, fileName);

    return ResponseEntity.ok()
        .cacheControl(
            CacheControl.maxAge(Duration.ofDays(30))
                .cachePublic()
                .immutable()
        )
        .body(body);
}
~~~

This is a conceptual example, not a standalone buildable controller: it needs imports, `findApprovedPublicAsset` implementation, path-traversal validation, and proper access controls. Use long cache lifetimes only when URLs are immutable by content hash; mutating content at the same URL serves stale assets to clients.

For responses containing order details, tokens, or personal profiles, typically return `Cache-Control: private, no-store` per policy, and **never force CDN caching**.

### Auditing CDN Costs

CDN incurs cache lookup, cache data transfer out, and cache fill fees; cache misses can also trigger origin processing/operation fees. Thus:

~~~text
Compare:
  Option A = origin egress + origin compute/operations + LB processing
  Option B = CDN egress + cache fill + lookup + applicable LB/storage charges
               + remaining origin compute on cache misses
~~~

Pull unit prices from current pricing tables and actual billing SKUs rather than assuming a "flat" CDN price across all geographies.

## 9. Network Service Tiers: Premium or Standard?

**Premium Tier** and **Standard Tier** are network options for supported internet-facing services—not switches that turn private VPC traffic into a cheaper tier.

| Factor | Premium Tier | Standard Tier |
|---|---|---|
| Goal | Global performance optimization | Cost optimization for regional internet apps |
| Routing path | Uses Google's backbone close to users | Relies more on ISP/transit networks |
| Global services | Supports global load balancing/CDN | Limited; does not support Cloud CDN |
| Multi-region backends | Suits global architectures | Usually requires regional design |
| Internet egress pricing | Premium pricing table | Standard pricing table |
| Internal VPC network | Private traffic always uses Google backbone | Standard does not apply to private VPC traffic |

If an app serves international users and needs a global external Application Load Balancer or CDN, Standard Tier is not an equivalent substitute. When evaluating Standard Tier:

1. Confirm supported load balancer, IP, and backend types.
2. Check SLA, geography, and latency requirements.
3. Verify regional availability and destination pricing.
4. Benchmark p95 latency, packet loss, and availability with representative traffic.
5. Shift traffic gradually with rollback, never flipping tiers mid-outage.

**Never use tier switching as a fix during an ongoing outage.** Per Network Service Tiers documentation, migrating traffic from Standard to Premium during a Standard outage has limitations; tier selection must be a planned architectural decision.

## 10. Cloud NAT and Paths to Google APIs

### Cloud NAT Is Not a Free Egress Path

Public Cloud NAT lets resources without external IPs initiate supported outbound connections. While valuable for security and operations, costs typically include:

- Hourly NAT gateway charges.
- Per-GiB NAT data processing charges.
- Hourly charges for NAT external IP addresses.
- **Data transfer out charges** for traffic leaving the network, where applicable.

If workloads send heavy traffic to the Internet, Cloud NAT can raise bills beyond raw egress SKUs. Optimize by:

- Finding top talkers via NAT metrics/logs and flow logs.
- Caching or batching external API calls.
- Routing eligible Google APIs calls over private access paths where supported.
- Checking NAT error rates, port allocation, and external IP counts.
- Never deleting a NAT gateway if workloads still depend on external third-party APIs.

### Private Google Access

**Private Google Access** allows VMs with only internal IPs to reach eligible Google APIs and services. Enabled per **subnet**, it requires matching routing and DNS setup.

It does **not** mean:

- Every vendor's external API becomes reachable.
- All data transfer to Google APIs is automatically free.
- Private API connectivity always behaves identically to Internet routing.
- A subnet with Private Google Access skips firewall, DNS, or route checks.

If using `private.googleapis.com` or `restricted.googleapis.com`, configure DNS and routes accurately; `restricted.googleapis.com` has a narrower supported scope and is used in VPC Service Controls architectures.

### Private Service Connect and Private Services Access

Private Service Connect (PSC) uses endpoints/backends or service attachments depending on scenario; private services access is a distinct mechanism connecting to managed services via VPC peering. Never use these terms interchangeably. Both can carry **separate endpoint, data processing, or service charges** depending on configuration.

Choosing a private path must consider **supported services**, security boundaries, region, DNS, networking, and billing—not an assumption that "private" is always cheaper than "public."

### Cloud Storage and Google APIs

For VMs reading Cloud Storage, appropriate private API access avoids traversing NAT for the API traffic itself. Still, cross-location data transfer and storage operation charges may still apply. Always separate **how you connect** from **the service's data pricing**.

## 11. Hybrid Networking: Cloud VPN, Cloud Interconnect, and On-Premises

When part of a system still runs on-premises, traffic crosses Cloud VPN or Cloud Interconnect. Costs go beyond data transfer:

- Operational charges for VPN tunnels or Interconnect connections/attachments.
- Data transfer fees over the corresponding link.
- Carrier/port/cross-connect facility charges, where applicable.
- Routing, NAT, network hardware, and operational costs.
- Duplicated data costs across both environments.

### Common Scenario

An app moves to GKE on Google Cloud while its database remains in the data center. One request makes 20 queries over VPN. Each query adds RTT and transfer overhead. At thousands of requests per second, total latency climbs and traffic costs cease to make sense.

Possible solutions:

- Migrate app and database in the same wave when feasible.
- Cut round-trips via query batching or API redesign.
- Place caches near the app for read-mostly data.
- Set a firm hybrid transition window and retirement date for temporary flows.
- Size VPN/Interconnect by bandwidth, availability, and security, not price alone.
- Continuously measure transfer bytes and replication traffic.

Reducing traffic must never compromise transactional integrity or RPO. When adding caches or replicated data, verify staleness bounds and consistency mechanisms.

## 12. Optimizing in the Java and API Layer

Good network architecture underperforms if the application sends more requests or larger payloads than needed.

### 12.1 Pagination and Field Projection

Instead of returning 100,000 records in one payload, enforce pagination, cap page sizes, and return only fields the client needs. Distinguish server-side filtering from fetch-all-then-filter-in-client patterns.

~~~http
GET /v1/orders?limit=50&cursor=NEXT_PAGE_TOKEN
Accept: application/json
~~~

Cursors must be stable and protected against unauthorized tampering. Avoid huge `OFFSET` queries on rapidly changing data when cursor-based pagination fits better.

### 12.2 HTTP Compression

Gzip/Brotli reduces bytes on JSON, HTML, and text payloads. However:

- JPEG/PNG/MP4/ZIP files are already compressed and gain little from re-compression.
- Compression burns CPU and can hurt latency on tiny payloads.
- Never enable compression carelessly on sensitive data vulnerable to compression side-channel attacks.
- Verify proxy/load balancer, CDN, and client compression support.

Measure **actual wire response size**, CPU, p95 latency, and error rates before and after.

### 12.3 Batching

If a Java worker sends tiny individual events over HTTP to a service in another region, batch by size or time window. Define bounds for:

- Maximum batch size.
- Flush interval.
- Timeouts and retries with backoff.
- Idempotency and deduplication.
- Queue memory and backpressure.
- Partial batch failures.

Batching reduces per-request and connection overhead, though it does not always shrink total payload bytes and can raise latency if flush intervals wait too long.

### 12.4 Connection Reuse and Pooling

HTTP keep-alive/HTTP/2 and JDBC connection pooling cut handshake and setup overhead. However:

- Oversized pools can exhaust Cloud SQL connections.
- Retries without jitter amplify traffic and cost.
- Long-lived connections require proper health checks and idle timeouts.
- Connection reuse does not shrink response sizes by itself.

### 12.5 Intentional Caching

Caches can live at the client, CDN, regional Redis/Memorystore, or inside the app process. Each tier has:

- Hit rate and TTL.
- Invalidation policy.
- Consistency requirement.
- Memory footprint and cost.
- Security boundary.

Measure effectiveness via **origin bytes averted** and **latency improvement**, not request hit ratio alone.

## 13. Avoid Turning Your Java API into a Large-File Download Proxy

A common anti-pattern:

~~~mermaid
flowchart LR
  U[Browser] --> API[Java API]
  API --> GCS[(Cloud Storage object)]
  GCS --> API
  API --> U
~~~

The API reads entire images/videos from Cloud Storage and streams them back to clients. This can:

- Increase API CPU, memory, and request duration.
- Double bandwidth through the API and trigger extra egress.
- Add extra hops and latency.
- Block edge caching benefits.

### Controlled Direct-Access Pattern

~~~mermaid
flowchart LR
  U[Browser] --> AUTH[Java API: authenticate and authorize]
  AUTH --> URL[Signed URL / controlled access]
  URL --> GCS[(Cloud Storage)]
  GCS --> U
~~~

For data **permitted** for direct client access, the API can issue a short-lived signed URL or use a supported frontend flow so the client downloads from Cloud Storage without forcing the API to proxy every byte.

Considerations:

- A signed URL is a bearer capability: anyone holding it within its expiry can access the object per the URL's scope.
- Never log full signed URLs to logs or analytics.
- Enforce short expiries, exact HTTP methods, and specific object paths.
- Control MIME types, `Content-Disposition`, CORS, and caching headers.
- For high-traffic public content, evaluate Cloud CDN with a Cloud Storage backend bucket.
- For personalized data, enforce authorization checks and restrict sharing before considering CDN.

**Direct access is not automatically free.** Cloud Storage applies its own data transfer, operation, and storage pricing; savings come from shedding backend proxy load and intermediate hops. Measure total cost before and after.

## 14. Building a FinOps Model Around Unit Economics

Monthly averages can hide business efficiency. Pick unit metrics that fit:

- Network cost / 1,000 API requests.
- GiB Internet egress / 1,000 active users.
- CDN cost / 1,000 file downloads.
- Inter-region replication cost / GiB replicated.
- Network cost / successful order.
- Error rate and latency alongside each unit.

Example (**all figures below are hypothetical**, not Google Cloud pricing):

| Metric | Before Optimization | After Optimization |
|---|---:|---:|
| Successful orders/month | 800,000 | 800,000 |
| Data transfer on target path | 10 TiB | 7 TiB |
| Origin requests for public images | 4 million | 1 million |
| Image load p95 latency | 650 ms | 230 ms |
| Total cost of related SKUs | To be measured | To be measured |

The goal is not merely shrinking TiB. Measure **new CDN fees**, shifts in load balancer/Cloud Storage operations, and performance. Total bytes can drop while the total bill rises if request/lookup fees or service tiers change unfavorably.

### Responsible Cost Allocation

- Use labels, project hierarchies, and owner mappings for cost allocation.
- With Shared VPC, clarify how traffic between host and service projects is attributed.
- For shared external LBs/CDNs, allocate by requests, bytes, or a consistent FinOps-approved rule.
- Document assumptions and coverage gaps: some SKUs lack granular resource labels.
- Never dump all shared platform networking charges onto the highest-traffic app without supporting evidence.

## 15. Case Study: Optimizing a Product Image API

**Hypothetical scenario:** A Spring Boot API returns product metadata and images. Users sit in Southeast Asia, the database and API share a region, while object storage sits in a different location. Previously, the API fetched files from Cloud Storage and returned them to browsers. The team noticed Internet egress and cross-location transfer rising rapidly.

### Step 1: Measure and Find Root Causes

- Use Billing Reports filtered by Network and Cloud Storage SKUs.
- Use Network Topology/Flow Analyzer to isolate high-egress backend paths.
- Use app metrics to measure object fetch frequency, bytes, and latency.
- Inspect Cloud Storage bucket location and response cacheability.
- Verify public vs. private object classifications, lifecycles, and permissions.

### Step 2: Propose Three Options

| Option | Pros | Risks / Costs to Measure |
|---|---|---|
| Keep API proxy, add in-app cache | Minimal client changes | Memory, invalidation, still traverses app |
| Use direct signed URLs | Removes Java API hop | URL security, CORS, Storage data transfer |
| Use Cloud CDN for public images | Edge caching, slashes origin load | Cache fill/lookup/egress, invalidation, cache keys |

Never push personal order photos onto a CDN solely for a high hit rate; classify data sensitivity first.

### Step 3: Controlled Pilot

1. Pick public images with content hashes containing zero user data.
2. Create a canary path and cap traffic share.
3. Verify HTTP headers, cache keys, and TTLs.
4. Measure hit ratio, cache fill, origin traffic, and p95 latency.
5. Watch request errors, 404s, stale content, and access controls.
6. Compare SKU charges once sufficient billing data arrives.
7. If targets pass, ramp traffic gradually; otherwise roll back routing/cache configs.

### Step 4: Evaluate Results

A change is successful only when:

- p95 latency is at or better than target.
- Zero private content leaks occur.
- Total cost serving equivalent traffic falls per valid billing data.
- Backend CPU/memory/requests drop or stay within limits.
- Zero increase in errors, stale data, or incidents.

## 16. Network Path Optimization Runbook: Measure – Test – Decide

### Step 1: Define the Problem

Example: egress costs jumped 35% period-over-period while orders grew only 5%. Confirm the jump is not simply different day counts or billing lag.

### Step 2: Identify Top SKUs and Top Flows

- Billing export for spend and SKUs.
- Network Topology/Flow Logs for traffic paths.
- Service metrics for request counts/bytes and business units.
- Logs/traces for call paths and large payloads.

### Step 3: Form a Hypothesis

Example: "workers repeatedly fetch the same objects across two regions; adding a cache or moving workers closer will cut cross-region transfer." Document validation methods and risks.

### Step 4: Compare Options

Compare at least:

- Do nothing (baseline).
- App-level optimization: caching, batching, compression.
- Placement, network endpoint, tier, or CDN optimization where appropriate.

### Step 5: Set Guardrails

- p95/p99 latency and error rate bounds.
- Availability/SLOs and RTO/RPO.
- No weakening of data classification or ACLs.
- Cost caps and canary traffic limits.
- Sufficient observation window before concluding.
- Rollback plan for DNS, routes, CDN, or deployments.

### Step 6: Canary Rollout

Apply changes to a small slice and monitor metrics. Never push major network changes straight to production without a staged rollout.

### Step 7: Before/After Comparison

- Normalize for traffic, duration, and work volume.
- Isolate unrelated releases, marketing surges, or workload shifts.
- Account for billing lag and credits.
- Check for newly appearing SKUs.
- Record realized savings and confidence level.

### Step 8: Decide and Standardize

Keep the change if guardrails hold; otherwise roll back. Update network diagrams, runbooks, ownership records, and FinOps dashboards.

## 17. Common Issues and Fixes

| Symptom | Possible Cause | Investigation / Fix |
|---|---|---|
| Sudden Internet egress spike | Bloated payloads, endpoint scraping, higher downloads | Check clients/URLs, quotas, CDN, compression |
| Rising cross-zone egress | Chatty Pods/VMs across zones | Inspect placement alongside HA requirements |
| Rising inter-region cost | DB/workers/buckets in mismatched regions | Map source–destination pairs and traffic volume |
| High Cloud NAT bill | Heavy GiB processed, external IPs, or always-on gateways | Audit NAT logs/metrics and eligible private API paths |
| Cannot reach Google APIs privately | Misconfigured Private Google Access, DNS, or routes | Verify subnet settings and endpoint support |
| CDN unavailable on Standard Tier | Cloud CDN requires Premium Tier | Select compatible architecture/tier |
| Low CDN hit rate | Wrong `Cache-Control`, fragmented cache keys, unstable URLs | Fix headers, keys, TTLs, and response types |
| CDN cuts origin bytes yet bill stays flat | Cache fill/lookup/egress or LB processing rose | Reconcile all related SKUs |
| Slow API image downloads | Java proxying large files without streaming/caching | Compare direct download, signed URLs, and CDN if fitting |
| Flow Logs mismatch billing | Sampling, aggregation, or coverage differences | Combine billing export, metrics, and logs |
| App speeds up yet DB errors rise | Changed connection routing/latency or pool pressure | Audit DB pools, IAM, TLS, and capacity |
| Private Service Connect still incurs fees | Product-specific endpoint/processing charges | Check PSC pricing and billing SKUs |
| Cut cross-zone yet outage blast radius grew | Consolidated everything into one zone | Restore HA; optimize at app layer first |
| Missing BigQuery Billing export data | Export disabled, billing lag, or missing IAM | Check export setup, sync schedule, and dataset IAM |

## 18. Pre-Change Network Path Checklist

- [ ] Flows classified into intra-zone, cross-zone, inter-region, Internet, and hybrid.
- [ ] Top flows have owners, purposes, locations, and bandwidth measurements.
- [ ] Baseline compared over 30–90 days or full business cycles.
- [ ] Actual SKUs checked instead of assuming internal traffic is free.
- [ ] Related NAT, load balancing, CDN, storage, and connectivity fees understood.
- [ ] Placement verified across APIs, DBs, caches, workers, and buckets.
- [ ] Security, data residency, and access controls verified.
- [ ] Confirmed SLOs, HA, and RTO/RPO do not degrade outside approved bounds.
- [ ] If using CDN: cacheability, cache keys, TTLs, and sensitive data verified.
- [ ] If using Standard Tier: feature compatibility and benchmarks verified.
- [ ] If using Private Google Access/PSC: DNS/routes and pricing verified.
- [ ] Canary plan, monitoring, alerts, and rollback plan ready.
- [ ] Unit cost compared at equal traffic/business volume.
- [ ] Post-release monitoring and accountable reviewer assigned.

## Review Questions

1. Why can traffic between two VMs in two zones of the same region incur charges even without touching the Internet?
2. Does Cloud NAT make outbound data transfer free? What additional charges can apply?
3. How does Private Google Access differ from Private Service Connect?
4. Why should you avoid placing every API and database in a single zone just to cut cross-zone traffic?
5. Is a Cloud Storage bucket in a multi-region always treated as the same location as a VM in one of the constituent regions?
6. When can Cloud CDN lower origin load without necessarily lowering total cost?
7. What must be checked before switching an internet-facing service from Premium Tier to Standard Tier?
8. Can VPC Flow Logs be used directly as a per-GiB invoice? Why or why not?
9. When can signed URLs improve download paths compared to streaming files through a Java API?
10. Which metrics and guardrails prove that a network optimization succeeded?

## Conclusion

Network path optimization on Google Cloud blends **architecture**, **telemetry**, and **FinOps**—not simply flipping on a "cheaper" tier. You must know where traffic originates and terminates, which zone/region/Internet/hybrid boundaries it crosses, which layers bill for it, and what business flow it serves.

Cloud Billing and BigQuery reveal which SKUs cost money; Network Topology, Connectivity Tests, VPC Flow Logs, and application metrics supply traffic and performance evidence. Techniques such as co-locating compute with data, caching, CDNs, private API access, batching, compression, and removing proxy hops must all be tested against **total cost**, p95 latency, security, and SLOs. When rolled out via canary releases with rollback plans and unit-cost tracking, engineering teams can eliminate unnecessary data transfers without sacrificing system reliability.

## References

- [Google Cloud: Network pricing](https://cloud.google.com/vpc/network-pricing)
- [Google Cloud: Network Service Tiers overview](https://cloud.google.com/network-tiers/docs/overview)
- [Google Cloud: Network Service Tiers pricing](https://cloud.google.com/network-tiers/pricing)
- [Google Cloud: Cloud NAT pricing](https://cloud.google.com/nat/pricing)
- [Google Cloud: Private Google Access](https://cloud.google.com/vpc/docs/private-google-access)
- [Google Cloud: Private access options for services](https://cloud.google.com/vpc/docs/private-access-options)
- [Google Cloud: Cloud CDN overview](https://cloud.google.com/cdn/docs/overview)
- [Google Cloud: Cloud CDN caching](https://cloud.google.com/cdn/docs/caching)
- [Google Cloud: Cloud CDN pricing](https://cloud.google.com/cdn/pricing)
- [Google Cloud: Cloud Storage pricing](https://cloud.google.com/storage/pricing)
- [Google Cloud: Network Topology overview](https://cloud.google.com/network-intelligence-center/docs/network-topology/concepts/overview)
- [Google Cloud: Connectivity Tests overview](https://cloud.google.com/network-intelligence-center/docs/connectivity-tests/concepts/overview)
- [Google Cloud: Network Intelligence Center](https://cloud.google.com/network-intelligence-center/docs)
- [Google Cloud: Export Billing data to BigQuery](https://cloud.google.com/billing/docs/how-to/export-data-bigquery)
- [Google Cloud: Set up Billing export](https://cloud.google.com/billing/docs/how-to/export-data-bigquery-setup)
