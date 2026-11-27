# Cloud DNS Routing Policies and Traffic Steering

> **Chapter:** Load Balancing and Content Delivery  
> **Module:** CLOUD_PROVIDERS_GCP

When deploying an application across multiple Google Cloud regions, users typically access a single domain name such as `api.example.com`. Yet that same domain name can point to multiple endpoints: a primary endpoint in Singapore, an endpoint in Tokyo, or a new release receiving only a small fraction of DNS queries. **Cloud DNS routing policies** determine which set of DNS records to return based on weights, query source geography, or primary/backup health status.

In the **CLOUD_PROVIDERS_GCP** module, learners study project organization, IAM, and VPC, choose Compute Engine, GKE, Cloud Run, storage, and databases, protect resources, automate releases, and track reliability and cost. This lesson belongs to the **Load Balancing and Content Delivery** chapter and explains how Cloud DNS works with Cloud Load Balancing, Cloud CDN, Cloud Monitoring, and hybrid connectivity to steer users to the right service.

**After this lesson, you will be able to:**

1. Distinguish DNS-based traffic steering from HTTP(S)/TCP load balancing at the connection layer.
2. Choose between **Weighted Round Robin (WRR)**, **Geolocation (GEO)**, **GEO with geofence**, and **Failover**.
3. Explain why TTLs, recursive resolvers, and EDNS Client Subnet cause real user traffic ratios to differ from configured weights.
4. Configure record sets and health checking appropriate for the zone/endpoint type.
5. Use the Google Cloud Console and `gcloud dns` commands to inspect, practice, and troubleshoot.
6. Design traffic paths and failure scenarios accounting for IAM, backend load, DNS caching, reliability, and cost.

## 1. How Does DNS Steer Traffic?

**DNS (Domain Name System)** translates a name like `api.example.com` into data clients use—most commonly IP addresses in **A** or **AAAA** records. In the basic model, an RRset (resource record set) contains one or more addresses sharing the same name and record type.

With a **Cloud DNS routing policy**, an RRset contains **policy items**. Instead of always returning the exact same address list, Cloud DNS chooses an answer based on the policy and signals observable at query time.

~~~mermaid
flowchart LR
    U["Browser / Application"] --> RES["Recursive DNS resolver"]
    RES --> AUTH["Cloud DNS authoritative zone"]
    AUTH --> POL{"RRset routing policy"}
    POL --> A["Returns A: 203.0.113.10"]
    POL --> B["Returns A: 198.51.100.20"]
    A -. "After resolution" .-> LB1["Endpoint / Load balancer A"]
    B -. "After resolution" .-> LB2["Endpoint / Load balancer B"]
~~~

*These IPs belong to documentation address ranges, not real endpoints.*

**Processing flow:**

1. The application requests domain resolution.
2. The resolver checks its cache; if a valid record remains cached, it may answer **without querying Cloud DNS again**.
3. When querying the authoritative server is required, Cloud DNS evaluates the RRset's routing policy.
4. Cloud DNS returns the matching IP/name record; resolvers and clients may cache it for the TTL duration.
5. **The client opens its own connection** to a received address. From there, VPC routing, Cloud Load Balancing, firewalls, and the application govern serving.

**Important distinction:** Cloud DNS decides the **DNS answer**; it does not sit in the middle of every HTTP request, does not proxy TCP sessions, and does not steer packets after a client has already connected. When an endpoint fails, a DNS policy can change answers for subsequent lookups, but it cannot migrate an already-established TCP session to another endpoint.

### 1.1. Cloud DNS and Cloud Load Balancing Serve Different Layers

| Criterion | Cloud DNS Routing Policies | Cloud Load Balancing |
| --- | --- | --- |
| Decision unit | Returns RRset per **DNS query** | Distributes **connections/requests** per LB configuration |
| Steering signals | Weights, DNS query source region, supported endpoint health state | LB type, backend services, health checks, URL maps, traffic policies, etc. |
| Sees HTTP path, host header? | Cannot read HTTP paths when selecting A/AAAA answers | Application Load Balancer supports Layer 7 HTTP(S) routing |
| Ratio accuracy | Affected by recursive DNS caching and client behavior | Direct control at the request/connection layer per LB features |
| Failover | Takes effect as resolvers re-query and health signals update | Handled across backends via LB mechanisms |
| Pairing with CDN | DNS can point to the LB/CDN hostname or IP | Cloud CDN pairs directly with External Application Load Balancers |
| Best suited for | Splitting across multiple endpoints/regions/providers; DNS-tier active-backup | Distributing into backends of one or more services |

For example, a global static website using an **External Application Load Balancer + Cloud CDN** may only need a single global frontend IP and one static DNS A record. Not every multi-region app needs a GEO policy. Evaluate DNS steering when you have **multiple distinct frontend addresses** or need region/weight steering at the DNS layer.

### 1.2. Three Exact Concepts to Remember

- **Managed zone:** where Cloud DNS manages a domain's data; can be **public** or **private**.
- **Resource record set (RRset):** records sharing the same name, type, and TTL, e.g., `api.example.com. A`.
- **Routing policy:** a configuration **attached to an RRset**, not a rule automatically applied to every record in a zone.

Cloud DNS also has **server policies** (forwarding/hybrid DNS, logging) and **response policies** (overriding answers by queried domain conditions). Those two are **different** from DNS routing policies. They can coexist within supported boundaries, but do not assume every "policy" performs traffic splitting.

## 2. Choosing a Policy by Goal

Cloud DNS supports three core routing policy types: **WRR**, **GEO**, and **FAILOVER**. GEO has an optional **geofence** setting.

| Policy | Selection Signal | Typical Scenario | What to Watch Out For |
| --- | --- | --- | --- |
| **Weighted Round Robin (WRR)** | Weights across policy items | Distributing traffic across two frontends, weighted rollouts | Ratios apply to **DNS queries**, not guaranteed request ratios |
| **Geolocation (GEO)** | Source location of query arriving at DNS | Directing users near a deployment region | May see resolver/ECS IP rather than end user's GPS location |
| **GEO with geofence** | GEO while confining answers within geolocation boundary | Strict regional serving constraints | If that region's endpoint fails, DNS may still return unhealthy IPs |
| **Failover** | Primary/backup with health signals | VPC internal active-backup services | Fails over only when **all primaries** are deemed unhealthy; still subject to DNS caching |

**Combination rule:** one RRset uses **only one routing policy type**. You cannot arbitrarily stack WRR and GEO into two layers on the same RRset. The supported exception is **FAILOVER with GEO-configured backups**.

### 2.1. Choosing by Scenario

- "Want to shift ~10% of queries to a new frontend in a lab" → **WRR**.
- "Want DNS queries from Singapore to receive the Asia frontend, and US queries to receive the US frontend" → **GEO**.
- "Clients must receive the designated region's answer even if that region fails" → **GEO + geofence**, while accepting downtime risk.
- "Want internal clients to use VIP A, returning VIP B only when A is unhealthy" → **FAILOVER**.
- "Want to route HTTP `/api/*` to one service and `/static/*` to another" → **Application Load Balancer URL map**, not a DNS policy.
- "Want to cache files near users and cut fetch times for cacheable content" → Evaluate **Cloud CDN** with a load balancer; a GEO RRset may be unnecessary.

## 3. Weighted Round Robin (WRR)

WRR assigns a **weight** to each policy item. Cloud DNS distributes answers proportionally according to weights among eligible items.

Example:

| Policy Item | DNS Target | Weight | Expected Share Over Many Independent Queries |
| --- | --- | ---: | ---: |
| Stable frontend | `203.0.113.10` | 90 | Roughly 90% |
| Candidate frontend | `198.51.100.20` | 10 | Roughly 10% |

Weight share formula:

\[
P(\text{item }i) = \frac{w_i}{\sum_j w_j}
\]

Weights of 9 and 1 yield the same 90:10 ratio. Per documentation, weights can be **0**; when all items have weight 0, Cloud DNS distributes evenly. A weight-0 item can also serve as a fallback in certain health-check configurations, so **never treat weight 0 as an absolute "guaranteed never returned" rule**.

### 3.1. Why Doesn't 90:10 Equal 90:10 HTTP Requests?

One resolver may cache an answer for `TTL=60` seconds and serve that exact IP to thousands of clients on its network. One client may send 100 HTTP requests after **a single DNS lookup**. Meanwhile, different DNS resolvers query at vastly different rates.

Hypothetical example:

~~~text
Authoritative DNS queries in 1 minute:
  Resolver A -> Stable    (5,000 HTTP requests from A's users)
  Resolver B -> Candidate (80 HTTP requests from B's users)
  Resolver C -> Stable    (10 HTTP requests)

Sampled query ratio: Stable 2/3, Candidate 1/3
Actual HTTP request ratio: completely different
~~~

Thus, for rollouts needing an **exact** 10% of users/sessions/requests, traffic splitting in **Cloud Run** or at the load balancer/application layer is more accurate. DNS WRR is suited for **approximate gradual shifts** or balancing across independent endpoints.

### 3.2. WRR and Health Checks

When policy items reference health-checked supported endpoints, Cloud DNS can exclude unhealthy endpoints from answers and redistribute across healthy ones. Note:

- Health checking occurs only when **enabled and properly configured** on a supported endpoint type.
- A bare A record pointing to an arbitrary IP **does not automatically get health checks**.
- Weight-0 items and mixed health-checked/non-health-checked items have specific fallback rules.
- **If every endpoint is unhealthy**, Cloud DNS can still return all endpoints as if healthy to avoid empty answers; this does not guarantee the application works.

### 3.3. Using WRR as a Canary Tool: Risk Assessment

Before shifting from 100:0 to 90:10:

1. Do both frontends share the same API contract/behavior and serve valid HTTPS/TLS for the domain?
2. Could clients cache DNS longer than the configured TTL?
3. Are sessions/state shared or consistent if users switch endpoints?
4. Are error, latency, and request count metrics tracked **per endpoint**?
5. Is there a rollback plan if the candidate fails, and how long before metrics reflect the shift?
6. If most DNS queries come through one recursive resolver, is the sample representative of real users?

## 4. Geolocation Routing Policy (GEO)

GEO maps **source geographies** to corresponding DNS answers. In Cloud DNS, geographies map to supported **Google Cloud regions**. When no rule matches the exact source region, Cloud DNS picks the closest configured geography per the service's algorithm.

Conceptual configuration example:

| Query Source Identified by Cloud DNS | Policy Item | Result |
| --- | --- | --- |
| Source mapped to `asia-southeast1` | Singapore | `203.0.113.10` |
| Source mapped to `us-central1` | US Central | `198.51.100.20` |
| Source in an undeclared region | Nearest configured location | An IP from the selected geography |

**GEO does not guarantee the chosen region is physically closest to the user's device.** It relies on how DNS queries enter Google Cloud and visible geographic signals.

### 4.1. Public DNS: What Is the Source?

For public zones, the source can be inferred from:

- The IP address of the recursive resolver sending the query to authoritative Cloud DNS; or
- **EDNS Client Subnet (ECS)** if the resolver forwards client subnet info in the query.

If a user in Vietnam queries a resolver located in Europe that does not forward ECS, Cloud DNS may infer the source as Europe. Therefore, **never rely on GEO DNS as proof of a user's real country** or as the sole enforcement mechanism for data residency laws.

### 4.2. Private DNS: Source Is the Region of the Querying System

In private zones, Cloud DNS **does not use ECS** for GEO:

- DNS queries from a **Compute Engine VM** inside a VPC take the **region containing the VM** as source geography.
- DNS queries arriving via an **inbound server policy** from on-premises take the region of the **Cloud VPN tunnel**, **Cloud Interconnect VLAN attachment**, or **Router appliance** receiving the query packet.

A query from a data center in Hanoi traversing a tunnel terminated in another region is evaluated using the **tunnel's region**, not the data center's physical city. When designing hybrid DNS, document entry paths and ingress regions to explain outcomes.

### 4.3. GEO and Health Checks: Failing Over to the Next Region

When GEO includes health checks and the chosen region's endpoint becomes unhealthy, with **geofencing disabled**, Cloud DNS can return endpoints from the **next closest healthy geography**. Policy changes affect only subsequent DNS queries; resolvers may keep the previous IP until TTL expires.

~~~mermaid
flowchart TD
   Q["DNS query from Asia source"] --> GEO["GEO selects Singapore"]
   GEO --> HC{"Is Singapore target healthy?"}
   HC -- "Yes" --> SG["Return Singapore VIP"]
   HC -- "No, geofence OFF" --> ALT["Evaluate nearest healthy geography"]
   ALT --> TK["Return matching alternate region VIP"]
   HC -- "No, geofence ON" --> STAY["Continue returning selected region's IP"]
~~~

### 4.4. GEO with Geofence

**Geofence** prevents automatic spillover to another geography. When **geofence is enabled** and **all endpoints in the target region are unhealthy**, Cloud DNS must still return an authoritative answer and can return that region's addresses even though they are unhealthy.

Thus GEO + geofence is a **regional serving preference**, not a data-safety kill switch. If the underlying workload crashes while traffic still routes there, users see errors. Strict residency mandates also require controlling data storage locations, app routing, IAM, networking, and policies independently of DNS.

### 4.5. Multiple Addresses in One Geography

Cloud DNS permits multiple IPs inside a single GEO policy item. When returned, resolvers/clients receive **multiple addresses** and pick among them per their own client logic. Do not treat this as a strict 50:50 weighted split, as clients may prefer the first IP, keep persistent connections, or cache records.

## 5. Failover Routing Policy

**Failover** suits **active-backup** setups for **internal VPC resources**. An RRset declares primary VIPs and a backup set. While at least one primary VIP is healthy, Cloud DNS serves healthy primary VIPs. When **all primary VIPs** are judged unhealthy, the service shifts to backup.

Backups are configured using **GEO** where supported, allowing region-aware backup selection. **Trickle traffic** can be enabled to send a small fraction of queries to the backup even while primaries are healthy, verifying backup readiness.

~~~mermaid
flowchart TD
    Q["Client in VPC resolves db-api.internal.example."] --> DNS["Cloud DNS private zone"]
    DNS --> C{"Any healthy primary VIP?"}
    C -- "Yes" --> PRI["Return primary VIP(s)"]
    C -- "No" --> BAK["Return backup via GEO"]
    PRI -. "Optional trickle" .-> BAK
    BAK --> LB["Backup internal load balancer"]
~~~

### 5.1. Trickle Ratio

Trickle traffic is configured as a **ratio from 0 to 1**. Examples:

| Trickle Ratio | Approximate Meaning |
| ---: | --- |
| `0` | Do not intentionally steer queries to backup while primaries are healthy |
| `0.05` | Roughly 5% of DNS decisions go to backup |
| `0.1` | Roughly 10% of DNS decisions go to backup |
| `1` | Can manually steer 100% of queries to backup |

**Never treat trickle as a guarantee of 5% HTTP requests.** Recursive resolver caching and TTLs cause actual request counts to diverge. For stateful services, backups must be ready to handle real data/connections even under tiny trickle ratios.

### 5.2. DNS Failover Differs from Full Disaster Recovery

Switching DNS to a backup only ensures **new client lookups resolve to a different endpoint**. A real DR plan must also answer:

- How is data synchronized to the backup? What is the acceptable RPO?
- Can the backup database accept writes, or is it still read-only standby?
- Does the backup backend have enough capacity to absorb 100% of production load?
- Are tokens, secrets, IAM, TLS certificates, and dependencies available in the backup?
- How will clients holding open connections to the primary retry?
- Could users keep hitting the old IP even after TTL expires?
- Once the primary recovers, is **manual failback** and error monitoring required?

RTO targets cannot be inferred directly from TTL alone. Real failover time depends on health check intervals, DNS caching, client behavior, new connection establishment, and backup readiness.

## 6. Health Checks in Cloud DNS Routing Policies

WRR/GEO/Failover policies can integrate **health signals** for supported endpoints. The two main branches are **internal load balancers** and **external endpoints**.

| Characteristic | Internal Load Balancer | External Endpoint |
| --- | --- | --- |
| Zone using health checking | **Private zone** | **Public zone** |
| Endpoint | Internal Application LB, internal passthrough NLB, cross-region internal ALB; internal proxy NLB per feature status | Public IP/port reachable from the Internet, including LBs or non-GCP servers |
| Evaluation mechanism | Based on load balancer/backend health signals depending on LB type | Cloud DNS sends TCP/HTTP/HTTPS probes from designated regions |
| How enabled | Reference the **forwarding rule**, not just a typed VIP | Declare the endpoint and matching health check |
| Constraints | Global access on regional LBs, IAM, and LB config | Firewalls, probe sources, port, HTTP status/body, interval |

### 6.1. Internal Load Balancers

Types listed in Google Cloud documentation include:

- Regional **internal Application Load Balancer**.
- Cross-region **internal Application Load Balancer**.
- **Internal passthrough Network Load Balancer**.
- **Internal proxy Network Load Balancer** (verify Preview/support status when using).

For internal Application/Proxy Load Balancers, DNS checks the **load balancer endpoint** health, while the load balancer distributes to healthy backends. For **internal passthrough NLB**, Cloud DNS uses backend instance health info to evaluate the endpoint; documentation cites a default **20% healthy backends** threshold. A passthrough NLB with zero backends may still be treated as "healthy" by Cloud DNS, so **configure at least one backend** for health checking to reflect reality.

When using a regional internal LB with Cloud DNS health checks, Google requires **global access** per the guide for that LB type. Verify connectivity scope and LB support before enabling.

**Crucial detail:** on the CLI, when enabling health checking for an internal LB, you must supply a **forwarding rule reference**, not just an IP address. A plain IP A record can be distributed via WRR/GEO, yet does not automatically inherit LB health checks.

### 6.2. External Endpoints

Cloud DNS supports health checking for **external IP endpoints** in **public zones**. Endpoints must be reachable over the Internet from health check probes. Current documentation notes:

- TCP, HTTP, or HTTPS health checking, with protocol-specific attribute limits.
- HTTP/HTTPS requires an **HTTP 200** response per check rules; response body matching can be configured.
- Health check intervals for external endpoints range from **30 to 300 seconds**.
- Configures **three Google Cloud source regions**, with **three probers** per region—nine probers total per endpoint as designed.
- **Source IP ranges are not fixed** like certain Google Cloud load balancer health checks; consult firewall guidance specifically for Cloud DNS external health checks.

This differs from Cloud Load Balancing backend health checks. Simply copying an LB health check IP allowlist onto an external endpoint's firewall can block DNS probes and mark the endpoint unhealthy.

Never loosen production firewalls arbitrarily; coordinate with security teams on probe ports and permitted probe access per real requirements.

### 6.3. When All Endpoints Are Unhealthy

A common false assumption is "Cloud DNS will return NXDOMAIN or a DNS error if all endpoints are unhealthy." Per documented behavior, **when all policy buckets are unhealthy, Cloud DNS falls back to treating all endpoints as healthy and returns addresses**. Thus clients may still connect to failing services.

**DNS health checks do not spin up new backends, repair databases, or guarantee avoiding broken endpoints completely.** You still need alerting, resilience engineering, and testing for all-unhealthy scenarios.

### 6.4. DNSSEC and Record Type Constraints

Cloud DNS routing policies support **A, AAAA, CNAME, MX, SRV, and TXT** within specific limits.

- **A:** health checks supported for internal load balancers in private zones and external endpoints in public zones.
- **AAAA:** external endpoint health checks supported per docs; do not assume internal LB IPv6 health checks behave identically.
- **CNAME, MX, SRV, TXT:** usable in routing policies, yet **do not support health checks**.
- When **DNSSEC** is enabled in a managed zone, health checking configurations have constraints, such as one IP per WRR/GEO policy item; verify requirements before migrating zones or updating records.
- A policy item cannot always mix health-checked and non-health-checked targets depending on the case; read the caveats for your exact policy type and DNSSEC setup.

**Never draw a CNAME health check** or write diagrams claiming "Cloud DNS pings every record automatically" when the record/endpoint type is unsupported.

## 7. TTL, Caching, and Route-Change Latency

**TTL (Time to Live)** on an RRset is the number of seconds recursive resolvers may cache the answer. A 30-second TTL is an upper-bound caching hint—**it does not guarantee every browser, OS, proxy, and recursive resolver re-queries after exactly 30 seconds**.

### 7.1. Why Isn't DNS Failover Instantaneous?

~~~mermaid
sequenceDiagram
   participant U as Client
   participant R as Recursive resolver
   participant D as Cloud DNS
   participant A as Endpoint A
   participant B as Endpoint B

   U->>R: Resolve api.example.com
   R->>D: DNS query
   D-->>R: A = Endpoint A, TTL 60s
   R-->>U: Endpoint A
   U->>A: HTTPS request
   Note over A: A fails afterward
   U->>R: Re-resolve while cache still valid
   R-->>U: Endpoint A from cache
   Note over D: Health checking detects failure
   R->>D: Re-query after cache expires
   D-->>R: Endpoint B
   R-->>U: Endpoint B
   U->>B: New request
~~~

Transition latency depends on at least four factors: health-check interval/failure detection, TTL/caching, client retries, and backup readiness. **Lowering TTL does not solve everything**: very low TTLs increase DNS query volume, cost, and resolver load while still failing to move clients holding long-lived connections.

### 7.2. Choosing TTL by Use Case

| Scenario | Approach |
| --- | --- |
| Static DNS record rarely changing | Moderate/high TTL to reduce repeated lookups |
| WRR canary | Short enough TTL to observe shifts, measured via real traffic |
| Rapid-response failover | Consider lower TTL, tested alongside health checks and client retries |
| Queries from centralized enterprise resolvers | Test real caching behavior and any resolver TTL overrides |
| High-traffic public domain | Weigh query cost impact, cache efficiency, and steering goals |

**When running A/B tests:** DNS query counts per policy item do not equal user session counts or HTTP requests. Measure at the application layer per frontend, user cohort, or session whenever exact ratios matter.

## 8. Supported Scope and Unsupported Configurations

Routing policies **cannot be configured** on several private managed zone types, including:

- **Forwarding zones**.
- **DNS peering zones**.
- **Managed reverse lookup zones**.
- **Service Directory zones**.

If you need both on-premises name resolution and WRR/GEO steering, design zones and record sets appropriately. Do not assume you can create a forwarding zone to on-prem DNS and add a WRR record set inside it.

An RRset cannot freely combine WRR+GEO, and once a **routing policy type** is chosen, switching to another type may require **deleting and recreating** the record set via a controlled procedure. Replacing records can have wide blast radius, especially for public names and cached entries.

### 8.1. Public vs. Private Zones

| Factor | Public Zone | Private Zone |
| --- | --- | --- |
| Who resolves? | Published via public authoritative DNS when properly delegated | Authorized VPCs and hybrid sources with appropriate resolution paths |
| GEO location | Resolver IP or ECS | VM/source region or hybrid ingress region |
| Supported health checks | External IP endpoints | Internal load balancer endpoints |
| Typical returned addresses | Public addresses of frontends/CDNs/LBs | Internal VIPs / private addresses |
| Scenarios | Multi-region/multi-provider APIs, multi-CDN, public rollouts | Internal apps, service discovery, multi-region active-backup |

Never publish a private VIP into a public zone as a connectivity workaround; public DNS returning a private IP **does not make a private IP reachable from the Internet**. Conversely, a private zone bound to specific VPCs is not visible to arbitrary Internet clients.

### 8.2. CDN: DNS Steering Does Not Replace Caching

If the goal is delivering images, CSS, JavaScript, or static files to global users:

- **Cloud CDN** caches at the edge and pairs with compatible load balancers, cutting RTT and origin load.
- **Cloud DNS** only answers hostname/endpoint lookups; it does not store or serve content.
- GEO records can steer users to regional CDN providers or frontends, though effectiveness must be measured via cache hit ratio, latency, error rate, and egress cost.
- Never build manual GEO DNS routing to replace a CDN when a global load balancer + Cloud CDN already solves the problem cleanly.

## 9. Reference Architecture: Dual-Region Public API

**Context:** An e-commerce application runs API frontends in Singapore and Tokyo, using Cloud Run or GKE behind appropriate **regional external Application Load Balancers**. The hostname is `api.example.com`. The goal is directing most Asian users to their preferred endpoint while failing over regionally if one fails.

~~~mermaid
flowchart TD
  CLIENT["Users / Resolvers"] --> DNS["Public Cloud DNS zone example.com"]
  DNS --> GEO{"GEO policy: api.example.com A"}
  GEO --> SG["Regional external ALB - Singapore"]
  GEO --> JP["Regional external ALB - Tokyo"]
  SG --> APISG["API service Singapore"]
  JP --> APIJP["API service Tokyo"]
  SG -. "Health signal when configured" .-> H["Cloud DNS external endpoint health checks"]
  JP -. "Health signal when configured" .-> H
~~~

**GEO Approach:** Declare policy items for relevant source regions with the two frontend public IPs. With external endpoint health checks enabled and **geofence disabled**, Cloud DNS can shift answers to another healthy geography if the nearest region's endpoint fails.

**Items to verify beyond DNS:**

1. If a request is in flight when Singapore fails, how does the client retry?
2. Can both regions access the database with the same schema/permissions? What about consistency and cross-region latency?
3. Do TLS certificates on both frontends cover `api.example.com`?
4. When using session cookies, tokens, or idempotency keys, are both regions compatible?
5. If one region takes 100% of traffic during an outage, does it have sufficient quotas, autoscaling headroom, and DB connections?
6. Do network paths and firewalls to backends allow the corresponding health probes?
7. Does compliance permit processing user data in Tokyo? If not, unrestricted GEO failover may violate policy.

### 9.1. When Is WRR Better Than GEO Here?

If the goal is **de-risking a rollout** of a new API version running in the same region, WRR 95:5 is a better fit than GEO. Yet if an exact 5% request/canary split is required, use traffic splitting in **Cloud Run** (where supported) or a load balancer mechanism suited to the backend architecture. DNS weights only govern expected ratios of DNS responses.

### 9.2. When Should You Skip DNS Policies?

If both backend groups already sit behind a single **global external Application Load Balancer** with a global anycast IP and Cloud CDN, the LB frontend may already handle backend distribution and caching. Adding Cloud DNS GEO in front **may bring zero benefit** if it still points to a single global IP. Start from the **technical objective** before deciding whether multiple DNS endpoints are needed.

## 10. Reference Architecture: Private Failover for an Enterprise App

**Context:** A Java system on Compute Engine needs an internal service across two regions. Private zone `corp.internal.` is attached to the VPC. The service has a **primary internal load balancer** and a **backup internal load balancer** with proper health configuration.

~~~mermaid
flowchart LR
  VM["Java VM in VPC"] --> DNS["Cloud DNS private zone"]
  DNS --> CH{"FAILOVER policy for svc.corp.internal"}
  CH --> A["Primary internal LB VIP"]
  CH -. "When primary unhealthy" .-> B["Backup internal LB VIP"]
  A --> P["Primary workload"]
  B --> S["Standby workload"]
~~~

An initial configuration might set **trickle 0.05** so the backup receives a small share of DNS lookups while the primary is healthy. The team must ensure the standby handles warmup requests cleanly—not merely verify that DNS can return the backup VIP.

**Must be clearly defined:**

- Which health signal marks the primary unhealthy?
- Are the backup application and data actually ready?
- Is there a split-brain risk if both regions accept writes simultaneously?
- Once the primary recovers, does the system fail back automatically, and are there side effects?
- How long do DNS caches or connection pools pin the old endpoint?
- Which VPCs does the private zone apply to; do Shared VPC and peering require specific DNS visibility settings?
- For on-premises queries via inbound DNS, backup GEO uses the **VPN/Interconnect ingress region**—does that match expectations?

**Never use DNS failover as a database synchronization strategy.** RPO, duplicate data, transaction locks, and consistency must be solved at the storage/application layer.

## 11. Configuring Routing Policies in the Console

Below is the general sequence following **Configure DNS routing policies and health checks**. Perform it in an authorized project/lab and always confirm zone type, DNS name, record type, TTL, endpoints, and rollback plan.

### Step 1 — Identify Zone and Endpoints

1. Open [Cloud DNS](https://console.cloud.google.com/net-services/dns/zones).
2. Select the project containing the **managed zone**, e.g., a public zone for `example.com.` or a private zone for `corp.internal.`.
3. Verify NS delegation if public; verify VPC visibility if private.
4. Confirm the frontend IP/forwarding rule and live service are working.
5. Check **A/AAAA** and supported health-checking scope.

### Step 2 — Create a Policy-Based Resource Record Set

1. Inside the zone, select **Add standard** or **Create record set** depending on Console version.
2. Enter the DNS name, record type (e.g., **A**), and TTL.
3. Choose **Routing policy**: WRR, Geolocation, or Failover.
4. Enter weights, source regions, or primary/backup items per policy.
5. If GEO, confirm whether **geofencing** is enabled or disabled; if enabled, understand spillover is disabled.
6. If health checks are needed, select the exact internal LB forwarding rule or external endpoint + health check depending on zone type.
7. Review and create the record set.

### Step 3 — Verify and Monitor

- Run `gcloud dns record-sets list` or check the Console to confirm the record set and policy.
- Query through multiple recursive resolvers using `dig`/`nslookup`; outputs may vary due to caching.
- Inspect health-check logs when enabled to confirm they accurately reflect endpoint state.
- Correlate Cloud DNS query behavior with **per-frontend request metrics**, not just DNS query counts.
- Verify TLS and HTTP responses from real clients after resolution.
- For failover, run controlled simulations in a lab—never deliberately break a production endpoint to test.

### 11.1. IAM Permissions and APIs

Configuring routing policies requires the **Cloud DNS API** and RRset edit permissions. Google documentation cites permissions/roles such as:

| Permission / Role | When Needed |
| --- | --- |
| `dns.changes.create` | Creating record set changes |
| `dns.managedZones.list` | Listing zones |
| `roles/dns.admin` | DNS admin role commonly used for configuration |
| `dns.networks.useHealthSignals` | Accessing health signals for internal passthrough NLB in applicable cases |
| `roles/dns.peer` | Specialized role when DNS peering/health signal permissions are required |

Exact permissions may depend on whether LBs and DNS zones live in different projects. Never grant project-wide Owner/Editor just to create an A record. In restricted labs or teams, ask an admin for least-privilege roles and verify cross-project IAM.

**Caution:** Changing the policy of a live production RRset can alter answers for the entire hostname. Always review before creating, updating, or deleting.

## 12. Google Cloud CLI Examples

### 12.1. Read-Only Commands

First verify active account and project:

~~~bash
gcloud config get-value project
gcloud auth list

# List DNS managed zones
gcloud dns managed-zones list --project=PROJECT_ID

# Read RRsets inside a zone
gcloud dns record-sets list \
  --zone=MANAGED_ZONE \
  --project=PROJECT_ID

# Inspect recent DNS changes (if any)
gcloud dns record-sets changes list \
  --zone=MANAGED_ZONE \
  --project=PROJECT_ID

# Inspect load balancer frontends and health checks
gcloud compute forwarding-rules list --project=PROJECT_ID
gcloud compute health-checks list --project=PROJECT_ID
~~~

If a command group changes or differs in your CLI version, check `gcloud dns --help` or the [gcloud reference](https://docs.cloud.google.com/sdk/gcloud/reference/dns). List commands only show resources within your IAM read scope.

### 12.2. Example: Creating WRR Without Health Checking

Assuming a **test public zone** `lab-zone` for `api.example.com.` and two prepared real IPs, an example command looks like:

~~~bash
# DNS change example: use only in an authorized lab
gcloud dns record-sets create api.example.com. \
  --type=A \
  --ttl=30 \
  --zone=lab-zone \
  --project=LAB_PROJECT_ID \
  --routing-policy-type=WRR \
  --routing-policy-item=weight=9,rrdatas=203.0.113.10 \
  --routing-policy-item=weight=1,rrdatas=198.51.100.20
~~~

Both IPs in this example are **documentation addresses**; replace them with real lab endpoints when testing live connectivity. This WRR example **does not enable health checks**, so Cloud DNS will not remove an IP if the app endpoint fails.

This command uses `--routing-policy-item`, replacing the older `--routing-policy-data` flag marked **deprecated** in the CLI reference. Flags can change across CLI upgrades, so verify syntax with `gcloud dns record-sets create --help` before running.

### 12.3. Example: Creating GEO Without Health Checking

~~~bash
# DNS change example: use only on a lab managed zone
gcloud dns record-sets create geo-api.example.com. \
  --type=A \
  --ttl=30 \
  --zone=lab-zone \
  --project=LAB_PROJECT_ID \
  --routing-policy-type=GEO \
  --routing-policy-item=location=asia-southeast1,rrdatas=203.0.113.10 \
  --routing-policy-item=location=us-central1,rrdatas=198.51.100.20
~~~

GEO returns **answers based on the source geography detected by the service**, not the closest IP to each user's GPS coordinates. Health checking is absent in this example; geofencing and health checks must be configured separately per verified requirements.

### 12.4. Health-Checked RRsets

When configuring health checks for an **internal LB**, the command must reference a valid forwarding rule; for external endpoints, it requires IPs with matching health check configs and a **public zone**. Options may live under `--routing-policy-item`, `--health-check`, or be configured via Console/API.

Never replace a forwarding rule with a raw IP string assuming health checking still works. For safe learning, practice this part via the **Console** following official steps, then use **read-only** CLI commands to inspect the result. Creating health checks or modifying RRsets affects live resources and may incur costs.

### 12.5. Testing DNS from a Client Machine

In a terminal with `dig`:

~~~bash
# Query A record via default DNS resolver
dig api.example.com A

# Query via a public resolver (illustrates resolver vantage point only)
dig @8.8.8.8 api.example.com A

# Inspect remaining TTL in the answer
dig api.example.com A +noall +answer
~~~

On Windows PowerShell, you can use:

~~~powershell
Resolve-DnsName api.example.com -Type A
nslookup api.example.com
~~~

Running queries repeatedly from the **same resolver** usually returns cached answers. To study WRR, sample across multiple resolvers/sources over a sufficiently long window and pair with request metrics. Never flood production public DNS with queries to "test percentages".

## 13. Observability and Troubleshooting

### 13.1. Signals to Monitor

| Signal | Question | Tool |
| --- | --- | --- |
| DNS query count by name/zone | Is DNS being used? Are queries spiking from low TTLs? | Cloud DNS monitoring/logging per support |
| DNS responses by source/region | Are WRR/GEO distributing as expected? | DNS query tests, health-check logging |
| Endpoint health | Which target is unhealthy? Probe, LB, or backend failure? | Cloud DNS health-check logs, LB monitoring |
| Frontend request count | How many HTTP requests actually hit each LB? | Cloud Load Balancing / Cloud Run metrics |
| Error rate and p95/p99 latency | Is one region/endpoint slow or failing? | Cloud Monitoring, logs, traces |
| TTL/cache | Are clients still using the old IP? | `dig`, resolver logs, client telemetry |
| Cost | How are query volume, health checks, and egress trending? | Cloud Billing, FinOps dashboards |

### 13.2. Quick Diagnostic Table

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| Policy creation fails | Wrong zone type, RRset type, IAM perms, or invalid policy fields | Cross-check zone type, supported records, and gcloud reference |
| New record missing in public DNS | Missing NS delegation, caching, wrong zone/project | Check NS records, managed zone, and authoritative response |
| WRR 90:10 yet app ratio differs widely | Resolver caching, uneven client cohorts, connection reuse | Compare DNS query volume against per-frontend request metrics |
| GEO returns unexpected region IP | Resolver in another region, missing ECS, or hybrid ingress region | Check resolver and ingress region where queries enter Google |
| GEO fails to fail over when region crashes | Geofence enabled, health checks missing, or signal not yet unhealthy | Inspect GEO config, health logs, and target type |
| GEO returns failed endpoint despite health failure | Geofence enabled or all buckets unhealthy | Review fallback behavior and policy settings |
| Failover doesn't switch to backup | Not **all** primaries down, DNS cache, stale health signal | Check primary set, TTL, and health logs |
| DNS switched yet clients still fail | Existing connections, missing app retries, backup unready | Test from client, backend readiness, data consistency |
| Internal LB marked healthy yet service fails | LB health differs from app readiness, or empty passthrough NLB | Inspect backend health and application path |
| External endpoint marked unhealthy | Firewall blocks probes, non-200 HTTP response, wrong port/URL/TLS | Check logs, probe config, and firewalls |
| CNAME route doesn't fail over on health | CNAME health checks unsupported | Use supported A/AAAA records and appropriate frontend design |
| Private DNS replies don't reach on-prem | Missing inbound forwarding/routes/network or VPC policy | Check hybrid DNS, Cloud VPN/Interconnect, and IAM |
| DNS resolves yet TCP to IP fails | Firewall, routing, LB backend, TLS, or service error | Separate DNS tests from Connectivity Tests and HTTP probes |

### 13.3. Ordered Troubleshooting Sequence

~~~text
Are the domain name and zone right?
   ↓
Are public delegation or private VPC visibility right?
   ↓
Does the RRset have the right policy type, items, TTL, and record type?
   ↓
Where do DNS queries actually originate? Is caching or ECS involved?
   ↓
Is health checking supported and working properly?
   ↓
Is the returned endpoint reachable? Are LB/backends/app healthy?
   ↓
Do request, error, latency, data, and cost metrics meet targets?
~~~

**When suspecting Cloud DNS:** query both authoritative and recursive resolvers from different vantage points; remember authoritative queries can trigger fresh policy evaluations while resolvers return cached data. **When suspecting connectivity:** continue investigating routes, firewalls, load balancers, and the application; changing DNS does not fix underlying network errors.

## 14. Learning Scenario: Dual-Region Booking API

**Context:** A Java system serves `booking.example.com`. The current version runs in Singapore and an experimental version runs in Tokyo; primary data lives in a relational database requiring cross-session consistency. The team plans to send a slice of users to Tokyo and then expand.

### 14.1. Option A — WRR to Evaluate the Experimental Build

1. Provision two frontend IPs/LBs serving the same HTTPS hostname.
2. Verify TLS, API contracts, database migrations, user sessions, and idempotency.
3. Configure WRR 95:5 when approximate DNS-level distribution is acceptable.
4. Collect **per-endpoint request counts**, error rates, p95 latency, DB query latency, and cross-region session counts.
5. Adjust weights or roll back based on telemetry.
6. If an exact 5% user split is required, use traffic splitting/app routing instead.

### 14.2. Option B — GEO by Query Source

1. Select frontend regions satisfying data and latency requirements.
2. Declare geographies for key DNS source regions.
3. Test from varied recursive resolvers, including corporate/hybrid resolvers.
4. If health checks are enabled, test GEO failover **without geofence** when an endpoint fails.
5. If compliance forbids cross-region spillover, consider geofence while accepting users see errors if the chosen region goes down.

### 14.3. Option C — One Global ALB and Cloud CDN

If the goal is cutting latency for static assets or managing multi-region backends behind a global load balancer, compare using a single public hostname and global LB frontend with Cloud CDN. Measure cache hit ratio, backend latency, cost, and operational complexity rather than assuming DNS GEO is automatically superior.

### 14.4. Sample ADR for the Engineering Team

~~~text
Decision: Use WRR 95:5 across two external LBs to evaluate experimental build
DNS name: booking.example.com
Zone: public
Endpoints: frontend A in Singapore, frontend B in Tokyo
Constraints: API contract, TLS, database consistency, data policy
Key metrics: requests per endpoint, HTTP 5xx, p95, errors after retry
Expectation: ~5% of DNS responses to B; does not guarantee 5% of users
Rollback: Set weight for B to 0 / update record per change process
Risks: TTL/caching, session affinity, failover, and DB latency
Validation: DNS samples + LB request metrics + load test
Next review: After collecting sufficient telemetry across resolvers/regions
~~~

For production systems handling sensitive transactional data, complete security, recovery, data modeling, and cost reviews before increasing traffic shares.

## 15. Self-Check Exercises

**Exercise 1 — Choose Policy by Scenario**

| Requirement | Expected Choice | Reason |
| --- | --- | --- |
| 10% of DNS answers to new release | WRR | Weighted distribution across policy items |
| US clients receive US frontend | GEO | Based on detected source geography |
| Use only one region's endpoint even if region fails | GEO + geofence | Blocks spillover; trades off availability |
| Internal primary/backup VIPs | FAILOVER | Uses health signals, GEO backup, and trickle |
| Split by HTTP path `/images` | Application LB | DNS cannot inspect HTTP request paths |
| Accelerate static images near clients | Cloud CDN | Provides edge caching; DNS does not cache content |

**Exercise 2 — Compute Weight Shares.** Given three WRR items with weights 5, 3, and 2. What are the expected query ratios? If the first group's resolver generates 10,000 HTTP requests from just 1 DNS query, does it still represent 50% of HTTP traffic?

**Hint:** Weights yield 50% / 30% / 20% over a large, independent sample of DNS decisions. You cannot infer HTTP request ratios because cache behavior and resolver-to-client ratios vary.

**Exercise 3 — GEO and Hybrid DNS.** A user in Hanoi queries a public zone through a resolver in Europe that does not send ECS. Meanwhile, a VM in Singapore queries a private zone inside the VPC, and an on-prem host uses inbound DNS over a VPN in `asia-southeast1`. How are the three sources geolocated?

**Hint:** Public relies mainly on resolver IP/ECS; private VM uses the VM's region; inbound hybrid uses the region where query packets enter via the VPN/Interconnect appliance.

**Exercise 4 — Health Checking.** An internal passthrough NLB has zero backend instances, yet Cloud DNS still shows the target as "healthy". Can you conclude the endpoint is ready to process transactions?

**Hint:** No. You need at least one backend and application-level readiness monitoring; DNS health signals do not replace business health checks.

**Exercise 5 — Failover.** TTL is 60 seconds, the primary fails, health checks detect it after 30 seconds, and a recursive resolver still caches the old IP. Can you guarantee every client switches within 30 seconds?

**Hint:** No. Account for TTL, caching behavior, client retries, and existing connections. These numbers are an educational scenario, not a Google SLA.

### Completion Checklist for the Exercises

- [ ] Identified public/private zone, record type, and TTL.
- [ ] Selected policy from requirements and explained trade-offs.
- [ ] Understood GEO source location relies on resolver/ECS or VPC/hybrid ingress region.
- [ ] Distinguished DNS answer weights from actual request/user ratios.
- [ ] Verified whether health checking is supported for the endpoint/record type.
- [ ] Understood GEO geofence and failover/trickle behavior.
- [ ] Accounted for DNS caching, all-unhealthy fallback, and existing connections.
- [ ] Prepared read commands to inspect RRsets and multi-resolver test plans.
- [ ] Defined application metrics and a rollback plan.
- [ ] Evaluated data model, SLOs, security, and cost.

## 16. Reasoning Fallacies to Avoid

1. **"WRR 90:10 means 90% of users hit A."** It only weights DNS decisions; caching skews request shares.
2. **"GEO knows the user's GPS location."** Cloud DNS relies on query source/resolver/ECS or private network region.
3. **"DNS works like a global load balancer."** DNS does not manage TCP connections or URL paths.
4. **"Enabling geofence makes the system more reliable."** Geofence can keep returning unhealthy IPs in the pinned region, trading off availability.
5. **"Any record pointing to an IP has health checks."** Health checking must be explicitly enabled on supported endpoint types.
6. **"Every record type supports health checks."** CNAME/MX/SRV/TXT do not; A/AAAA have specific scopes.
7. **"When all endpoints are unhealthy, DNS stops returning answers."** Cloud DNS can fall back to returning all endpoints.
8. **"TTL=30 means RTO=30 seconds."** Health detection, caching, and retries do not run on a single shared clock.
9. **"DNS query count equals real traffic volume."** One resolver query can serve thousands of HTTP requests.
10. **"Cloud DNS replaces Cloud CDN."** CDN caches and delivers content; DNS only resolves endpoints.
11. **"A private zone automatically works in every VPC."** Requires proper VPC visibility, peering, or forwarding.
12. **"Internal LB health checks work just like external IPs in a public zone."** The two models have different scopes and prerequisites.
13. **"Switching WRR to GEO only edits one property."** Changing policy type afterward may require delete/recreate per procedure.
14. **"A valid DNS answer means the application is healthy."** Verify routing, firewalls, TLS, backend readiness, and data.

## 17. Official Google Cloud Documentation

Details regarding supported endpoints, health checking, DNSSEC constraints, policy types, and CLI syntax can change; check official pages at deployment time:

- [Cloud DNS overview](https://docs.cloud.google.com/dns/docs/overview) — zones, public/private zones, resolution basics.
- [DNS policies overview](https://docs.cloud.google.com/dns/docs/policies-overview) — server, response, and routing policies.
- [DNS routing policies and health checks](https://docs.cloud.google.com/dns/docs/routing-policies-overview) — WRR, GEO, geofence, failover, health checks, supported RR types.
- [Configure DNS routing policies and health checks](https://docs.cloud.google.com/dns/docs/configure-routing-policies) — Console, CLI, API, and permission guides.
- [gcloud dns record-sets create](https://docs.cloud.google.com/sdk/gcloud/reference/dns/record-sets/create) — current syntax, `--routing-policy-item`, policy types.
- [gcloud dns record-sets update](https://docs.cloud.google.com/sdk/gcloud/reference/dns/record-sets/update) — updating RRsets and policy-type change constraints.
- [Cloud DNS best practices](https://docs.cloud.google.com/dns/docs/best-practices) — operations and testing.
- [Cloud DNS logging and monitoring](https://docs.cloud.google.com/dns/docs/monitoring) — observing DNS queries and health.
- [Cloud Load Balancing overview](https://docs.cloud.google.com/load-balancing/docs/load-balancing-overview) — LB types and backend distribution decisions.
- [Cloud CDN overview](https://docs.cloud.google.com/cdn/docs/overview) — edge caching, static content, and eligible dynamic caching.
- [Google Cloud DNS pricing](https://cloud.google.com/dns/pricing) — zone and DNS query pricing model.
- [Connectivity Tests overview](https://docs.cloud.google.com/network-intelligence-center/docs/connectivity-tests/concepts/overview) — analyzing network paths beneath DNS.

**Core Takeaway:** Cloud DNS routing policies govern **DNS answers**, not individual requests. **WRR** fits weighted distribution, **GEO** fits query-source region selection, **geofence** pins regions at the risk of downtime, and **FAILOVER** supports internal active-backup via health signals. Reliable architectures measure DNS caching, endpoint health, real serving capacity, data consistency, and cost rather than merely checking that a record exists.
