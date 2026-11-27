# Weighted, Latency-Based, and Location-Based Routing Policies

> **Chapter:** DNS and Content Delivery  
> **Module:** CLOUD_PROVIDERS_AWS — exploring AWS infrastructure across Regions/Availability Zones (AZs), IAM, VPC, compute, storage, database, integration, and serverless; practicing service selection, secure application design, monitoring, recovery, and cost control.

## Learning Objectives

After this lesson, you will be able to:

1. Describe how **Amazon Route 53** selects DNS answers via routing policies, distinguishing DNS routing from HTTP request proxying.
2. Explain **Weighted routing**, compute relative weights, plan canary/blue-green rollouts, and understand the exception for **weight = 0**.
3. Explain **Latency-based routing** using latency data to AWS Regions, distinguishing it from picking the geographically closest Region on a map.
4. Explain **Geolocation routing** by continent, country, U.S. state, and **default record**; distinguish it from **Geoproximity routing** and bias.
5. Analyze the impact of **health checks**, alias records, Evaluate Target Health, TTL, recursive DNS caching, and EDNS Client Subnet.
6. Design DNS policies for multi-Region systems, combining Route 53 with ALB, CloudFront, IAM, VPC, and monitoring to improve availability.
7. Read configurations, simulate DNS answers using the AWS CLI in **read-only** mode, and troubleshoot misrouted endpoint issues.

## 1. How Does Route 53 Route at the DNS Level?

**Amazon Route 53** is AWS's DNS and domain management service. When a client wants to access **api.example.com**, it typically asks a recursive DNS resolver to translate the domain name into DNS information such as an IPv4 address (**A**), IPv6 address (**AAAA**), or another target name. When Route 53's authoritative DNS server must answer, it selects a record matching the configured routing policy.

For example, suppose an application has two backends:

- Endpoint A in Singapore, representing an ALB or application backend in AWS Region **ap-southeast-1**.
- Endpoint B in Tokyo, representing a backend in Region **ap-northeast-1**.

Both serve the same API. Route 53 can be configured to answer by:

- **Weight**: actively distribute most DNS answers to A and a small fraction to B.
- **Latency**: prefer the AWS Region predicted to have the lowest network latency for the query source.
- **Geographic location**: prefer an endpoint by specified country, continent, or geographic area.

~~~mermaid
sequenceDiagram
    participant U as Browser / application
    participant R as Recursive DNS resolver
    participant D as Route 53 authoritative DNS
    participant E as Selected endpoint
    U->>R: Query api.example.com
    R->>D: Query when needed, if not cached
    Note over D: Select RRset by routing policy and health
    D-->>R: DNS response, TTL
    R-->>U: Answer, may be cached
    U->>E: HTTPS connection to received endpoint
~~~

**A Route 53 routing policy is not an HTTP load balancer sitting between the client and the application.** Route 53 answers **DNS queries**, and the client then connects to the returned endpoint. If the client already cached DNS, keeps an existing TCP/HTTP connection open, or the DNS resolver's TTL has not expired, policy changes may not affect live traffic immediately.

### 1.1. Routing Policies Do Not Replace the Application Layer

Four conditions to separate:

1. **DNS:** which endpoint does the domain name return?
2. **Network:** can the client reach the endpoint over the Internet/VPC and through Security Groups/NACLs?
3. **Transport:** are HTTPS/TLS and the certificate valid for the hostname?
4. **Application:** is the endpoint healthy, is the session valid, and is the data available in the selected Region?

A correct DNS answer cannot fix a broken VPC route, an unreplicated database, or a certificate hostname mismatch.

### 1.2. Public Hosted Zone vs. Private Hosted Zone

- **Public hosted zone** manages public DNS when a domain/subdomain is delegated to the appropriate name servers.
- **Private hosted zone** provides DNS for associated VPCs, with distinct resolver and routing behaviors.

Weighted, latency, and geolocation policies can be used in private hosted zones where supported by the service. However, **how location is determined** in a private hosted zone can differ from a public zone. Do not use public DNS behavior to assume how private VPC DNS behaves in every case.

## 2. Key Concepts Before Choosing a Policy

| Term | Meaning | Example |
| --- | --- | --- |
| **Hosted zone** | Collection of DNS resource record sets belonging to a domain/subdomain. | example.com |
| **Record name** | Full name being queried. | api.example.com |
| **Record type** | Type of DNS data. | A, AAAA, CNAME |
| **Record set (RRset)** | Group of values forming a logical record per Route 53 fields. | An A record using Weighted policy. |
| **Routing policy** | How Route 53 selects an answer when multiple records share a name/type. | Weighted, latency, geolocation. |
| **SetIdentifier** | ID distinguishing records with the same name and type in a multi-record routing group. | stable-95, canary-5 |
| **TTL** | Duration a recursive resolver may cache the DNS answer. | 60 seconds |
| **Alias record** | Route 53-specific record pointing to supported resources/records. | api.example.com → ALB |
| **Health check** | Checks health of an endpoint or monitored resource per configuration. | HTTP /health |
| **EvaluateTargetHealth** | Alias option to factor in target health where supported by AWS. | Alias to ALB |

When using weighted/latency/geolocation, you typically have multiple records with the **same Name and Type**, distinguished by **SetIdentifier** and policy-specific attributes. You cannot arbitrarily mix a weighted record and a geolocation record sharing the **same name + type** expecting Route 53 to automatically know which policy runs first.

To combine multiple policies, you usually need a **hierarchical record/alias tree** or **Route 53 Traffic Flow**, rather than illegally mixing record types at the same level.

## 3. Weighted Routing — Distributing by Relative Weight

**Weighted routing** lets you assign weights to multiple records sharing the same name and type. Route 53 selects a record based on **the ratio of its weight to the total weight of eligible records in the group**. This is ideal for canary releases, relative traffic splitting, or phased migrations between service versions.

### 3.1. Formula

For records with positive weights that are all considered eligible:

\[
P(i) = \frac{w_i}{\sum_{j=1}^{n} w_j}
\]

Where:

- \(w_i\) is the weight of the \(i\)-th record.
- The denominator is the sum of weights of the records currently considered in the group.
- \(P(i)\) is the **expected proportion of DNS answers**, not an exact guarantee of HTTP request ratio or user count.

Example:

| Record | SetIdentifier | Weight | Expected DNS ratio if all eligible |
| --- | --- | ---: | ---: |
| Stable backend | stable | 90 | 90% |
| Canary backend | canary | 10 | 10% |
| **Total** | | **100** | **100%** |

Across 9,000 independent DNS answers, you can expect roughly 8,100 answers for stable and 900 for canary under suitable statistical conditions. **Never promise an exact 8,100/900 split**: DNS caching, health checks, actual query patterns, and client distribution make application-layer ratios differ significantly.

### 3.2. Example Record Sets JSON

Two illustrative records for **api.example.com**, each using an IP from **TEST-NET** documentation ranges, not real AWS endpoints.

~~~json
[
  {
    "Name": "api.example.com.",
    "Type": "A",
    "SetIdentifier": "stable-90",
    "Weight": 90,
    "TTL": 60,
    "ResourceRecords": [
      {"Value": "192.0.2.10"}
    ]
  },
  {
    "Name": "api.example.com.",
    "Type": "A",
    "SetIdentifier": "canary-10",
    "Weight": 10,
    "TTL": 60,
    "ResourceRecords": [
      {"Value": "198.51.100.20"}
    ]
  }
]
~~~

This shows **ResourceRecordSet objects** for reading structure, **not** a complete **ChangeResourceRecordSets** payload. With real ALBs, you typically use **AliasTarget** instead of self-managed A record IPs, and you must supply the ALB's exact DNS name and hosted zone ID.

### 3.3. Canary Release with Weighted Policy

A controlled rollout plan:

1. Deploy **v2** to an independent backend; verify health, TLS, database compatibility, and rollback.
2. Keep traffic 100% on stable and 0% on canary (or omit canary from routing per design).
3. Shift weights to **99:1** and monitor error rates, latency, request logs, and business metrics.
4. Gradually increase **95:5 → 90:10 → 50:50 → 0:100** once stability evidence is sufficient.
5. If rollback is needed, shift weights back to stable, monitor DNS caching, and handle active sessions.

One critical caveat: if a recursive DNS resolver serves many clients behind it and caches the answer, **many users may hit the same backend** even at weight 1%. Thus DNS-based canary is not an exact per-user splitter or a mechanism for pinning a canary by customer ID.

If you need rollout control by user, cookie, header, or session, use **ALB routing rules**, feature flags, or an application-layer release control system instead of relying solely on DNS.

### 3.4. Weight = 0 Is Not an Absolute Disable Switch

Behavior to remember per AWS documentation:

- If some records with **weight > 0** are eligible/healthy, Route 53 generally considers those and does not select **weight = 0** records.
- If **all records have weight = 0**, Route 53 chooses among them with **equal probability** so the group still returns an answer.
- When health checks are configured and **all positive-weight records** become unhealthy, Route 53 may evaluate **weight = 0 records** as a fallback.
- If **all health-checked records** are unhealthy, Route 53 exhibits **fail-open** behavior per policy group: it can still return records that would normally be excluded rather than returning no answer by default.

**Implication:** Do not treat weight 0 as security isolation or a hard shutoff for an endpoint. If a version must receive zero traffic, enforce it at the **deployment, routing group, network/app access** layer or delete the record cleanly—do not rely solely on setting weight 0.

### 3.5. Common Weighted Routing Mistakes

- Confusing **weight = 10** with "10%" even when total weight does not equal 100.
- Treating DNS answer weight ratios as actual HTTP request ratios.
- Assuming weight 0 disables an endpoint completely even if all other records go unhealthy.
- Leaving a weak target without a health check while expecting Route 53 to detect failures automatically.
- Using weighted DNS for sticky sessions or per-request load balancing.
- Forgetting unique **SetIdentifier** values for records sharing the same name/type.

## 4. Latency-Based Routing — Optimizing Latency by AWS Region

**Latency routing** lets you create records representing endpoints serving an application from **multiple AWS Regions**. Route 53 uses AWS network latency measurements to determine which **Region** is predicted to provide the lowest latency for the DNS query source, and selects that Region's record.

~~~mermaid
flowchart TD
    C["Client / DNS resolver"] --> R53["Route 53 latency policy"]
    R53 --> SGP["ap-southeast-1 — Singapore"]
    R53 --> TYO["ap-northeast-1 — Tokyo"]
    SGP --> A["Singapore Region ALB / app"]
    TYO --> B["Tokyo Region ALB / app"]
~~~

### 4.1. Do Not Equate Latency with Map Distance

A user in northern Vietnam is not automatically routed to Singapore, Tokyo, or any specific Region just because it looks closer on a map. Latency routing relies on **observed network latency data that changes over time**.

- BGP routing, ISP peering, and network conditions can give a geographically farther Region lower latency.
- A browser may use a recursive resolver located far from the user.
- **EDNS Client Subnet (ECS)** can help Route 53 estimate client location more accurately when the resolver supports it.
- AWS latency data does not directly measure every path to endpoints **outside AWS**; actual results with external endpoints may vary.

**Latency routing is not geo-fencing.** If business rules require users in Vietnam to be served by a specific system, latency policy does not guarantee that.

### 4.2. Example Record Sets for Latency Routing

~~~json
[
  {
    "Name": "api-latency.example.com.",
    "Type": "A",
    "SetIdentifier": "sg-region",
    "Region": "ap-southeast-1",
    "TTL": 60,
    "ResourceRecords": [
      {"Value": "192.0.2.10"}
    ]
  },
  {
    "Name": "api-latency.example.com.",
    "Type": "A",
    "SetIdentifier": "tokyo-region",
    "Region": "ap-northeast-1",
    "TTL": 60,
    "ResourceRecords": [
      {"Value": "198.51.100.20"}
    ]
  }
]
~~~

This is a study example using test IPs. The **Region** attribute on the record indicates the AWS Region serving the resource for latency policy evaluation, **not where the hosted zone lives**. Route 53 is a global DNS service; you do not create a separate hosted zone per Region just to use latency routing.

### 4.3. When Latency Routing Is Useful

- The application runs **active-active multi-Region** and wants to reduce initial round-trip time.
- Each Region has sufficient backends, data stores/replicas, and capacity to handle traffic sent to it.
- Health checks / Evaluate Target Health can be paired to avoid preferring an unhealthy endpoint where supported.
- The system monitors **p95/p99 latency** at the application layer and real data metrics per Region.

Do not enable latency routing across an API in Singapore and a backend in Tokyo **if Tokyo lacks the required data**, lacks business consistency support, or is merely a cold standby not ready for traffic.

### 4.4. Latency Routing in Private Hosted Zones

In a private hosted zone, Route 53 can choose an endpoint based on the **AWS Region associated with the VPC/resolver originating the query** and inter-Region measurements per AWS's documented behavior. Do not assume it geolocates **an employee's physical office address** like a public DNS query.

If using Route 53 Resolver inbound/outbound endpoints, where the resolver receives the query can affect the decision. Always test from the target VPC and actual DNS path.

## 5. Geolocation Routing — Explicitly Choosing by User Location

**Geolocation routing** lets you specify endpoints based on the **geographic location Route 53 determines for the DNS query source**, by:

- **Continent**.
- **Country** (e.g., ISO code for Vietnam is **VN**).
- **Subdivision** (U.S. state, where supported).
- **Default** for locations without a matching record or where location cannot be determined.

Example:

| Applicable Location | Target Endpoint | Purpose |
| --- | --- | --- |
| Country = **VN** | Application tailored for the Vietnam market. | Local language/content policy. |
| Continent = **EU** | European version of the application. | Content tailored for the EU market. |
| **Default** | Global general application. | Prevent DNS from returning no answer for unconfigured locations. |

### 5.1. More Specific Regions Take Precedence

Suppose there are three geolocation records with the same name/type:

- Continent = **AS** (Asia) → backend A.
- Country = **VN** → backend B.
- Default → backend C.

When Route 53 identifies a query as coming from Vietnam, the **VN** record is chosen because it is more specific than **AS**. A query from another Asian country without a specific record may go to backend A. A query from an unmatched or unidentifiable location uses **Default**.

~~~mermaid
flowchart TD
    Q["DNS query"] --> V{"Matches country VN?"}
    V -->|"Yes"| VN["Vietnam endpoint"]
    V -->|"No"| A{"Matches Asia AS?"}
    A -->|"Yes"| AS["Asia endpoint"]
    A -->|"No/unknown"| D["Default endpoint"]
~~~

The diagram illustrates only two geo rules and a default; in a full setup, Route 53 checks the **most specific location** (e.g., U.S. state, country, continent) with a valid record, along with endpoint health if configured.

### 5.2. Example GeoLocation Records

~~~json
[
  {
    "Name": "site-geo.example.com.",
    "Type": "A",
    "SetIdentifier": "vietnam",
    "GeoLocation": {"CountryCode": "VN"},
    "TTL": 60,
    "ResourceRecords": [
      {"Value": "192.0.2.10"}
    ]
  },
  {
    "Name": "site-geo.example.com.",
    "Type": "A",
    "SetIdentifier": "default",
    "GeoLocation": {"CountryCode": "*"},
    "TTL": 60,
    "ResourceRecords": [
      {"Value": "198.51.100.20"}
    ]
  }
]
~~~

This example uses reserved documentation IPs. **CountryCode = "\*"** in the `GeoLocation` field represents **Default** in the record API structure, not an IP wildcard.

### 5.3. Why Is a Default Record Necessary?

Some IPs cannot be mapped accurately to a geographic location or belong to regions for which you have not created records. **Without a default**, Route 53 can return a DNS response **with no answer** for queries that find no geolocation match.

A default record helps:

- Avoid accidentally locking out legitimate users from unconfigured locations.
- Provide a fallback when geolocation data is ambiguous.
- Serve a general endpoint/content for other markets.

**Default does not mean "handles every case."** If a system is legally barred from serving a market, enforce that with appropriate application/access controls rather than relying solely on DNS IP geolocation.

### 5.4. Geolocation Does Not Pinpoint Every Individual User

The routing decision usually depends on the IP address of the **recursive DNS resolver** or the truncated client subnet sent via **EDNS Client Subnet**.

- VPNs, public DNS resolvers, NAT, carrier networks, and ECS support can make DNS location differ from physical location.
- DNS geolocation **is not proof of residency or citizenship**.
- For data policy, content licensing, and compliance controls, the application must still enforce business rules and data governance properly.

### 5.5. Geolocation Combined with Health Checks

When a record for a specific region becomes unhealthy and you have configured health checks, Route 53 can evaluate **broader geographic regions** such as country → continent → default to find a healthy endpoint. For instance, a U.S. state record can fall back to the U.S. country record or continent record before reaching default.

However, if all evaluated endpoints are unhealthy, **fail-open behavior** can occur: Route 53 still returns a record per policy rules. Never rely on DNS health checks as a guaranteed mechanism to completely exclude broken endpoints.

## 6. How Does Geoproximity Differ from Geolocation?

Within **location-based routing**, another option is **Geoproximity routing**.

| Criterion | **Geolocation** | **Geoproximity** |
| --- | --- | --- |
| Core question | "Which country/continent/state does the user belong to?" | "Which resource is the user closer to considering location and bias?" |
| Rules | Country, continent, U.S. state, and default. | AWS Region/Local Zone group or external resource coordinates where supported. |
| Partitioning | By explicitly chosen geographic boundaries. | By zones of influence around each resource. |
| Weighting adjustment | Change assigned rules/locations; no geoproximity-style distance bias. | Positive/negative **bias** to expand/shrink the zone of influence. |
| Best suited for | Market-specific content, language, or national borders. | Balancing traffic by geographic proximity and resource capacity. |
| Same as latency routing? | No. | No: distance/influence zones differ from measured latency data. |

### 6.1. Bias in Geoproximity

Bias lets you **expand or shrink the geographic area** that a record attracts. A **positive** bias expands the endpoint's zone of influence; a **negative** bias shrinks it.

AWS documents the bias-adjusted distance model as:

\[
\text{biased distance}=\text{actual distance}\times\left(1-\frac{\text{bias}}{100}\right)
\]

For example, an endpoint 150 km from a resolver with bias **+50** has an effective distance of 75 km for geoproximity selection. That illustrates the record selection math—**it does not physically shorten the network path by 75 km**.

Avoid making large bias changes all at once in production: geographic boundaries can shift dramatically, suddenly sending a backend more traffic than its provisioned capacity.

### 6.2. When to Choose Geolocation Instead of Geoproximity?

- Want users in Vietnam to receive Vietnamese content by explicit rule → **Geolocation**.
- Want users assigned to a geographically nearby endpoint while tuning coverage area by capacity → **Geoproximity**.
- Want to optimize predicted network transit time between users and AWS Regions → **Latency**.

Do not confuse **"close"** in geoproximity with **"lowest latency"**: geographic distance is only one factor affecting network latency.

## 7. Decision Matrix: Weighted, Latency, and Location

| Criterion | **Weighted** | **Latency-based** | **Geolocation** | **Geoproximity** |
| --- | --- | --- | --- | --- |
| Primary rule | Record weights. | Region with lowest predicted latency. | DNS query location by defined region. | Influence zone based on resource location and bias. |
| Key record field | **Weight**. | **Region**. | **GeoLocation**. | **GeoProximityLocation/Bias** per API. |
| Required inputs | Weights and endpoints. | Endpoints across multiple AWS Regions. | Country/continent/state/default. | Resource locations/bias. |
| Canary rollout | **Very suitable** at DNS level. | Does not directly control rollout %. | Does not directly control %. | Does not set direct % weights. |
| Latency optimization | Does not optimize automatically. | **Primary goal**. | Does not measure latency. | Location-based, not direct latency measurement. |
| Market-based rules | None. | Not guaranteed. | **Suitable**. | Does not follow political boundaries precisely. |
| Deterministic per user/request | No. | No. | Does not pinpoint individuals absolutely. | No. |
| Health integration | Yes. | Yes. | Yes. | Yes, per supported mechanism. |
| TTL/cache still applies | Yes. | Yes. | Yes. | Yes. |

**Quick rule of thumb:** Need rollout proportions → Weighted; need multi-Region latency optimization → Latency; need routing by specified country/region → Geolocation; need to tune coverage zones around service points → Geoproximity.

When the requirement is active-passive disaster recovery, evaluate **Failover routing policy** rather than trying to emulate it completely with Weighted 100:0. When you need to return multiple health-check-aware IPs, **Multivalue answer** differs from Weighted. When an enterprise knows exact CIDR ranges per ISP/client, **IP-based routing** may fit better than IP geolocation guessing.

## 8. Health Checks: Routing Policies Do Not Know Automatically When an App Fails

Without a corresponding health signal, Route 53 **does not automatically infer that an endpoint is broken** just because a website starts returning HTTP 500 or the database stops accepting connections.

### 8.1. Endpoint Health Checks

Route 53 can check HTTP/HTTPS/TCP endpoints or use other AWS-supported health check mechanisms. Design health signals to reflect operational intent:

- Probe `/health` or `/ready` on the proper protocol/port.
- The checked endpoint should reflect whether the application can actually serve traffic.
- Separate liveness and readiness if workloads have unready dependencies.
- Avoid overly heavy health checks that add load or cause false negatives.
- Configure health checker source ranges, Security Groups, and network paths so AWS health checkers can actually reach the target endpoint.

An ALB in front of an application runs its own target health checks; a Route 53 alias to ELB has the **EvaluateTargetHealth** option where supported. Still, Route 53 health checks and ALB target group health checks are **two distinct layers**.

### 8.2. Alias and EvaluateTargetHealth

An **Alias record** can point to ELB, CloudFront, an S3 website endpoint, or another record among supported AWS targets. For alias targets that support health evaluation, **EvaluateTargetHealth = true** tells Route 53 to factor in target health accordingly.

Not every alias target type supports arbitrary EvaluateTargetHealth settings. For example, CloudFront distributions have different constraints from ALBs; always consult the docs for that alias target type.

If an alias points to **another record in the same hosted zone**, health evaluation can cascade down to the underlying record group per Route 53 rules. This enables layered routing policies (e.g., latency selecting a Region, then weighted selecting a version within that Region).

### 8.3. All-Unhealthy and Fail-Open

Per AWS logic, when every record in a health-checked group is marked unhealthy, Route 53 still needs to return an answer and may **treat all records as eligible** under the routing policy. This **fail-open** behavior prevents returning no answer at all due to health checks.

**Therefore:**

- Never claim "enabling health checks guarantees DNS always excludes every broken endpoint."
- Upstream apps/load balancers need proper error handling, retries, and circuit breakers.
- Drill both **single-endpoint loss** and **all-endpoints-unhealthy** scenarios, measuring DNS update time under TTL and client behavior.

### 8.4. Health Checks Must Target the Specific Entity

A classic mistake is pointing a health check at **api.example.com** itself when api.example.com holds multiple weighted/latency/geolocation records. The health check may pass through the routing policy and probe a **different** backend from the one it is meant to monitor.

Use dedicated health endpoints per backend, for example:

- **sg-health.example.com** → Singapore Region.
- **jp-health.example.com** → Tokyo Region.

Each health check must verify its exact backend and path without depending on the DNS policy it controls.

## 9. TTL, DNS Caching, and EDNS Client Subnet

### 9.1. TTL Is Not an Absolute Cutoff Timer for Traffic

**TTL** (Time To Live) indicates how long a resolver may cache a DNS answer. For example, a 60-second TTL means a recursive resolver can serve the cached answer within the allowed window without **re-querying Route 53 for every client request**.

After a policy change:

- Authoritative Route 53 records need time to propagate updates.
- Recursive resolvers may still hold the previous answer in cache.
- Browsers/OSes/apps may maintain separate caches.
- Open HTTP/TCP connections may be reused even after DNS changes.

Consequently, changing 90:10 to 100:0 **does not guarantee every HTTP request shifts to stable within 60 seconds**.

### 9.2. Short TTL vs. Long TTL

| TTL | Advantage | Trade-off |
| --- | --- | --- |
| Short, e.g., 60 seconds | Resolvers re-query sooner, making traffic shifts/failover more responsive. | More DNS queries, potentially higher cost; many clients do not honor TTL strictly. |
| Long, e.g., 300–3600 seconds | Fewer queries to authoritative DNS, lower lookup overhead. | Extends the window during which clients keep using an old endpoint. |

AWS generally recommends a TTL of **60 seconds or less when using health checks** on non-alias records where you set the TTL. The right TTL depends on RTO, rollout frequency, DNS query volume, and actual caching layers.

For aliases to certain AWS resources, the answer's TTL may be dictated by the **alias target** rather than entered independently as on a standard A record.

### 9.3. Recursive Resolvers and EDNS Client Subnet

Route 53 can base routing decisions on:

- The **IP of the recursive DNS resolver** if the resolver does not send EDNS Client Subnet.
- **Truncated client address info** forwarded by the resolver via EDNS Client Subnet (ECS), when supported.

~~~mermaid
flowchart TD
    U["User in Vietnam"] --> R{"Does resolver send ECS?"}
    R -->|"No"| I["Route 53 estimates from resolver IP"]
    R -->|"Yes"| E["Route 53 uses forwarded client subnet"]
    I --> S["Select record by policy and health"]
    E --> S
~~~

The same user can receive different answers when switching DNS resolvers, VPNs, or network paths, even if the website and Route 53 records remain unchanged. Do not interpret **nslookup/dig output from one network** as proof that an entire market receives the intended endpoint.

### 9.4. Private Hosted Zones Determine Location Differently from Public DNS

For private hosted zones, Route 53 uses logic based on the **VPC/Resolver in an AWS Region** rather than Internet EDNS0 client subnet info; ECS does not apply the same way in private zones. Always test by querying through the target VPC's resolver.

## 10. Architecture Example: Multi-Region Application and Controlled Rollout

Suppose an API application runs in:

- **Singapore (ap-southeast-1)** with an ALB and a group of EC2/ECS backends.
- **Tokyo (ap-northeast-1)** with an ALB and another backend group.
- Business data has appropriate replication/consistency design; logs, IAM, secrets, and monitoring are configured in both Regions.

~~~mermaid
flowchart TD
    C["Users across locations"] --> R53["Route 53: api.example.com"]
    R53 -->|"Latency selects Region"| S["sg.api.example.com"]
    R53 -->|"Latency selects Region"| T["jp.api.example.com"]
    S -->|"Weighted selects stable/canary"| SG1["Singapore ALB stable"]
    S -->|"Weighted"| SG2["Singapore ALB canary"]
    T -->|"Weighted selects stable/canary"| JP1["Tokyo ALB stable"]
    T -->|"Weighted"| JP2["Tokyo ALB canary"]
~~~

### 10.1. Multi-Layer Policy Design

**Layer 1 — Region selection:** Create latency alias records for **api.example.com**, one representing **Singapore** and one representing **Tokyo**, each with its own SetIdentifier and Region.

**Layer 2 — In-Region version selection:** Under each branch, create weighted record groups at distinct intermediate names such as **sg.api.example.com** and **jp.api.example.com**.

**Layer 3 — Health checks:** Attach appropriate health checks or EvaluateTargetHealth at each level so Route 53 can fail over to the other branch when a Region/backend group becomes unhealthy under supported conditions.

**Layer 4 — Application protection:** ALB listeners/target groups, HTTPS certificates, Security Groups, IAM/VPC, WAF if needed, data replication, and monitoring.

This presentation is a **logical architecture**; the alias tree must be constructed validly with exact record names, DNS types, alias target hosted zone IDs, and health settings. Do not copy diagram arrows blindly into DNS configs without verifying record constraints.

### 10.2. Do Not Mix Policies Directly Under the Same Name/Type

Do not create **one group of api.example.com A records** where peer records arbitrarily mix **Weight**, **Region**, and **GeoLocation**. Route 53 requires records sharing a Name/Type in a routing group to follow one corresponding policy type.

If you need **geography → weighted → endpoint**, design it with **intermediate names and alias records** or supported **Traffic Flow**. Start with a simple policy and measure before adding layers.

### 10.3. Do Not Neglect the Data Plane

Multi-Region DNS is only valuable if each Region can **independently serve the application**:

- Backends are healthy with adequate scaling capacity.
- Databases have replication/backups and business-appropriate consistency handling.
- The application handles a user switching Regions between requests.
- Session storage, S3 objects, secrets/credentials, IAM/KMS, and DNS names are properly designed.
- RPO/RTO targets, backups, failover, and full-Region recovery plans exist.

Route 53 **does not replicate RDS, S3 objects, EBS volumes, or session state** across Regions. Those remain the application architecture's responsibility.

### 10.4. When to Use CloudFront Instead of Route 53 Alone?

If the goal is delivering images, CSS, JavaScript, or video with low latency to users across many locations, **Amazon CloudFront** provides CDN edge caching, origin protection/routing mechanisms, and content delivery features.

Route 53 can point an **Alias** to a CloudFront distribution, but Route 53 routing policies **do not cache web content at the edge**. The two services complement each other:

- Route 53: answers DNS.
- CloudFront: delivers and caches content across the edge network, connecting to configured origins.
- ALB/API Gateway: handles HTTP(S) termination, routing, and request-layer features per service capabilities.
- Application: authentication, authorization, content, and business consistency.

## 11. Security and Governance for DNS Changes

### 11.1. IAM Least Privilege

Not everyone needs permission to edit public DNS records. One mistaken DNS edit can send all users to the wrong endpoint or cause an outage.

Separate permissions:

- **Viewer/Support:** read hosted zones, records, health checks.
- **Deployment automation:** modify only approved record names/types per workflow and supported IAM conditions.
- **DNS administrator:** administer zones/delegation, IAM, DNSSEC as needed; elevated access requires review.

Relevant IAM actions include **route53:ListHostedZones**, **route53:ListResourceRecordSets**, **route53:GetHostedZone**, **route53:ChangeResourceRecordSets**, **route53:GetChange**, **route53:GetHealthCheck**, and others as needed. When using IaC, verify apply permissions and CloudTrail auditing.

### 11.2. DNS Is Not a User Authentication Mechanism

Weighted or geolocation records do not prove a caller is authorized to access a system:

- Websites must use a **TLS certificate** matching the hostname.
- Private APIs need authentication/authorization at the application, API Gateway, ALB, or appropriate layer.
- Security Groups, VPC network paths, and WAF (where supported) must still be configured.
- Route 53 does not block direct endpoint access if the endpoint is public and the app lacks proper access controls.

### 11.3. DNSSEC and Domain Protection

**DNSSEC** helps verify DNS data integrity/authenticity within a valid chain of trust when properly configured; it does not replace TLS, IAM, or stop application attacks. DNS delegation, registrar lock, MFA, CloudTrail, and hosted zone write permissions must also be governed.

### 11.4. Rollback Plan for Policy Changes

1. Store the current version of record sets in IaC/controlled configuration backups.
2. Verify target endpoints, SSL certificates, health checks, and data consistency.
3. Apply changes in small/appropriate batches and record the change ID.
4. Use **GetChange** to verify **INSYNC** status.
5. Monitor error rates, request volumes, latency, and business KPIs.
6. If rolling back, restore the previous config and remember that TTL/connection reuse prevents instant traffic shifting.

In high-traffic applications, avoid treating **INSYNC** as "every client on the Internet has evicted the old DNS cache." INSYNC only means the change has been propagated to Route 53's name servers per AWS mechanics.

## 12. AWS CLI: Observing and Simulating Routing (Read-Only)

The following commands **do not create, edit, or delete** hosted zones or records. Replace illustrative IDs and domains with resources from your authorized environment. AWS Route 53 is a global DNS service; you do not need to pass a Region flag for every hosted zone management command as you do with EC2.

### 12.1. Identify Account and Hosted Zone

~~~bash
aws sts get-caller-identity

aws route53 list-hosted-zones \
  --query "HostedZones[].{Name:Name,Id:Id,Private:Config.PrivateZone}"

aws route53 get-hosted-zone \
  --id ZEXAMPLE123456
~~~

One domain can appear in **multiple hosted zones** (e.g., public/private or separate zones). Check **zone ID**, **PrivateZone**, name servers, and active delegation—never rely on the name alone.

### 12.2. View Weighted, Latency, and Geolocation Records

~~~bash
aws route53 list-resource-record-sets \
  --hosted-zone-id ZEXAMPLE123456 \
  --query "ResourceRecordSets[?Name=='api.example.com.']"

aws route53 list-resource-record-sets \
  --hosted-zone-id ZEXAMPLE123456 \
  --query "ResourceRecordSets[?Name=='api-latency.example.com.']"

aws route53 list-resource-record-sets \
  --hosted-zone-id ZEXAMPLE123456 \
  --query "ResourceRecordSets[?Name=='site-geo.example.com.']"
~~~

In the JSON output, inspect:

| Field | Interpretation |
| --- | --- |
| **Name / Type** | Which DNS name and record type these records serve. |
| **SetIdentifier** | Which record in the routing group. |
| **Weight** | Weighted routing weight. |
| **Region** | Latency routing Region. |
| **GeoLocation** | Geolocation routing setting. |
| **GeoProximityLocation** | Geoproximity routing setting if applicable. |
| **TTL** | Cache duration for standard records. |
| **ResourceRecords** | Direct values such as IP addresses. |
| **AliasTarget** | Alias target pointing to an AWS resource or record. |
| **HealthCheckId** | Attached health check if configured. |
| **EvaluateTargetHealth** | Inside AliasTarget, whether target health is evaluated. |

With paginated CLI output, be sure to process all pages if the list is large. Output only shows **AWS configuration**; it does not prove every recursive resolver/client is returning that exact IP at that moment.

### 12.3. Simulate DNS Answers

~~~bash
aws route53 test-dns-answer \
  --hosted-zone-id ZEXAMPLE123456 \
  --record-name api.example.com \
  --record-type A
~~~

**TestDnsAnswer only supports public hosted zones.** It returns the expected Route 53 answer for a simulated DNS query. It provides options to simulate a resolver IP or EDNS Client Subnet:

~~~bash
# Syntax illustration only. Replace addresses with a real resolver IP
# or permitted test client subnet; do not use TEST-NET IPs
# to infer real-world user geography.
aws route53 test-dns-answer \
  --hosted-zone-id ZEXAMPLE123456 \
  --record-name site-geo.example.com \
  --record-type A \
  --resolver-ip 8.8.8.8
~~~

Available flags as needed: **--resolver-ip**, **--edns0-client-subnet-ip**, and **--edns0-client-subnet-mask**. With anycast public resolvers, the IP you see does not always accurately represent the user's location. Do not treat a test from one IP as comprehensive testing across all countries.

**Caveat when testing weighted routing:** Running one test returns only a single simulated answer; one test cannot prove a 90:10 ratio. Evaluating real distribution requires a sufficient sample size, independent resolvers, and real backend telemetry.

### 12.4. Inspect Health Checks

~~~bash
aws route53 list-health-checks

aws route53 get-health-check \
  --health-check-id EXAMPLEHEALTHCHECKID

aws route53 get-health-check-status \
  --health-check-id EXAMPLEHEALTHCHECKID
~~~

Inspect HTTP/HTTPS/TCP target settings, path, expected response, thresholds, and health status. Route 53 health check status only reflects the criteria it is configured to probe; it does not guarantee every business workflow is healthy.

### 12.5. Check Progress of a DNS Change

~~~bash
aws route53 get-change \
  --id /change/EXAMPLECHANGEID
~~~

A change reaches **INSYNC** once Route 53 has propagated it to its name servers per service mechanics. Resolvers/clients may still cache old answers until TTL expires or per their caching behavior.

### 12.6. Check DNS from the OS

~~~bash
# On systems with dig:
dig api.example.com A
dig api.example.com AAAA
dig site-geo.example.com A

# Query a chosen resolver, if permitted:
dig @1.1.1.1 api.example.com A
~~~

The **dig** command inspects DNS answers returned by a resolver at query time; results may come from cache. To distinguish recursive vs. authoritative responses, query the zone's actually delegated authoritative name servers. Never run one query and conclude global geo or weighted policy works everywhere.

## 13. Guide to Choosing Policies for AWS Applications

### 13.1. Scenario A — 5% Canary Users for a New API

**Context:** Stable is running, v2 has not been load-tested fully. You want to send a small share of DNS answers to v2.

**Initial choice:** **Weighted routing** (e.g., 95:5).

**Mandatory checks:**

- Both stable and canary have proper health checks.
- v2 is database-schema compatible and does not break when users switch between versions.
- Metrics and logs are separated by version/target.
- Do not interpret 5% weighted answers as exactly 5% of active sessions or HTTP requests.
- Rollback plan must not assume "weight 0 guarantees zero traffic."

**When unsuitable:** If the canary must stick strictly by user ID, tenant account, or cookie, consider application-layer routing.

### 13.2. Scenario B — API Serving Asia and Europe

**Context:** Backends in Singapore and Frankfurt are both ready, with compatible data and authorization.

**Initial choice:** **Latency-based routing**, if speed of user experience is the primary goal.

**Checks:**

- Measure p95/p99 latency and error rates by Region.
- Test failover when the nearest Region's backend fails.
- Assess data replication/consistency and cross-Region impact.
- Test DNS results from multiple resolvers/countries rather than picking Regions by map distance.

If **legal boundaries govern data storage/processing**, design separate data policies and application controls; latency routing alone does not satisfy those constraints.

### 13.3. Scenario C — Website Serving Vietnam-Specific Content

**Context:** Users in Vietnam should see Vietnamese content/endpoints; other visitors receive the global website.

**Initial choice:** **Geolocation**, country VN and **Default**.

**Checks:**

- Test across multiple resolvers/ISPs/VPNs.
- Do not confuse resolver location with physical user location.
- Include Default for unconfigured countries and unmapped IPs.
- Provide manual language selection or account preferences in the app so you do not rely exclusively on geo-IP.

### 13.4. Scenario D — Balancing Load Between Two Data Centers

**Context:** Two endpoints in different locations have unequal capacity; you want to expand the coverage area of the higher-capacity endpoint.

**Candidate:** **Geoproximity** with a small **bias** and incremental testing. If the goal is an overall percentage split unrelated to geography, **Weighted** is clearer to express.

**Checks:** Observe real traffic and latency. A bias of +10 does not directly mean +10% traffic.

### 13.5. Scenario E — 100% Standby When Primary Region Fails

**Context:** The secondary Region takes no traffic during normal operation and only serves when the primary Region fails.

**Candidate:** **Failover routing policy** with primary/secondary and appropriate health checks, or a validated multi-layer DNS model.

**Avoid:** Merely setting weighted 100:0 and assuming RTO is met, because TTL, caching, and health check/fail-open behavior still apply.

## 14. Troubleshooting DNS Routing

| Symptom | Possible Cause | Check |
| --- | --- | --- |
| 90:10 yet canary backend gets 30% of requests. | Recursive resolver caching, low query volume, session/connection reuse, uneven clients or retries. | Sample DNS answers and inspect backend request logs/metrics. |
| Users in Vietnam receive the Default endpoint. | Query arrives via a resolver elsewhere, no ECS, unmapped IP, misconfigured VN record. | TestDnsAnswer with appropriate source, GeoLocation config, and actual resolver. |
| Latency routing picks Tokyo instead of Singapore. | AWS-measured latency is better to Tokyo; resolver/ECS location differs from expected. | Check Region field, DNS tests, real latency, and resolver. |
| App is down yet DNS still returns the old record. | Missing health check, wrong target/path, or all records unhealthy triggering fail-open. | `get-health-check-status`, EvaluateTargetHealth, health config. |
| Rolled back yet some clients still hit canary. | TTL/cache, long-lived connections, or weight 0 fallback when other endpoints are unhealthy. | `GetChange` INSYNC, TTL, connection pooling, backend health. |
| DNS returns "no answer" in some countries. | Missing geolocation Default or matching record. | Inspect GeoLocation records and simulate locations. |
| Alias to ALB does not work. | Wrong AliasTarget DNSName/HostedZoneId, policy/zone, ALB health, or routing/network. | `list-resource-record-sets`, ELB/target health, DNS, and TLS. |
| Different environments return different endpoints for the same domain. | Overlapping public/private hosted zones, VPC association, or resolver forwarding rules. | `get-hosted-zone`, VPC Resolver path, delegation, query from target environment. |
| New record does not take effect publicly. | Domain not delegated to right name servers, change not INSYNC, stale cache. | NS records at registrar/parent zone, `GetChange`, TTL. |

### 14.1. Suggested Diagnostic Tree

~~~mermaid
flowchart TD
    A["Client reaches wrong endpoint"] --> B{"Right hosted zone and delegation?"}
    B -->|"No"| B1["Fix hosted zone / NS delegation"]
    B -->|"Yes"| C{"Right Record Name, Type, SetIdentifier?"}
    C -->|"No"| C1["Check RRset and policy"]
    C -->|"Yes"| D{"Resolver source / ECS understood correctly?"}
    D -->|"No"| D1["Test via other resolvers and locations"]
    D -->|"Yes"| E{"Health checks / alias target right?"}
    E -->|"No"| E1["Check health and fallback"]
    E -->|"Yes"| F{"Stale TTL cache or existing connections?"}
    F -->|"Yes"| F1["Wait for valid cache / inspect sessions"]
    F -->|"No"| G["Correlate app and network logs/metrics"]
~~~

**Do not** try to fix every error by dropping TTL to 0 or opening endpoint permissions. Identify whether the fault is in **DNS routing, DNS caching, networking, or the application**.

## 15. Monitoring, Cost, and Resilience

### 15.1. Metrics and Logs to Monitor

- **Route 53 health checks:** per-endpoint status and corresponding alarms.
- **CloudWatch metrics:** DNS query counts by type via AWS-supported sources, alongside endpoint health and application resource metrics.
- **Route 53 query logging:** configured per hosted zone type (public/private) and appropriate log destination.
- **CloudTrail:** records Route 53 management events such as record/zone changes as configured.
- **ALB/API/CloudFront/application metrics:** request counts, status codes, p95/p99 latency, errors, target health.
- **Cost:** hosted zone, DNS query, health check, and logging fees, plus ALB/EC2/ECS/CloudFront/data transfer/cross-Region/backend costs.

Route 53 query logs help analyze DNS lookups, but **do not show all HTTP requests browsers send to the backend**. DNS caching lets one lookup serve many requests.

### 15.2. Balancing Cost and Recovery Time

Shorter TTLs help resolvers re-query sooner when endpoints change, but DNS query counts and costs may rise. DNS health checks incur fees by type/feature. Active-active multi-Region also adds costs for:

- Compute/database resources in multiple Regions.
- Cross-Region replication and data transfer.
- Monitoring, backups, logs, and failover drills.
- Operational overhead, certificates/secrets, and per-Region deployment infrastructure.

Do not judge Latency routing purely by DNS response: **end-to-end request latency, consistency, error rates, RPO/RTO, and total system cost** determine true effectiveness.

### 15.3. Resilience at Two Layers

**DNS layer:** policies, health checks, TTL, alias tree, and zone delegation work as designed.

**Service layer:** backends, data, networking, certificates, IAM/KMS, sessions, and failover are designed and rehearsed.

If the application has only one database in Region A while DNS shifts users to Region B, Region B's service will still fail business operations. DNS failover does not automatically replicate or recover data.

## 16. Practice Exercises

### Exercise 1 — Calculating Weights

A weighted record group has weights:

- **v1 = 180**
- **v2 = 20**
- **v3 = 0**

Assuming v1/v2 are healthy and eligible, estimate the DNS answer ratio.

**Answer:** v1 ≈ 90%, v2 ≈ 10%, v3 ≈ 0%. However, v3 with weight 0 is not permanently disabled if all positive-weight records become unhealthy and Route 53 applies fallback.

If all weights are changed to 0, Route 53 does not shut down the group completely—instead it selects among the records with equal probability per documented behavior.

### Exercise 2 — Canary Does Not Match Request Ratio

An organization uses Weighted 99:1 for an API, yet canary sees nearly 15% of HTTP requests during a short window. Name at least three possible causes.

**Hint:** Recursive DNS caching concentrates many clients, low DNS query count, long-lived connections, retries, uneven client traffic, resolver-specific traffic skew, or health checks altering the eligible set. Collect a larger sample and backend logs before concluding the policy is broken.

### Exercise 3 — Latency or Geography?

An application runs in Singapore and Tokyo. The primary goal is reducing perceived latency for users across Asian countries, with **no country-based content restrictions**.

**Answer:** Start with **Latency routing** and measure results. Do not pick Geolocation based solely on a map. If specific markets later require distinct content policies, consider Geolocation alongside application mechanisms.

### Exercise 4 — Default for Geolocation

A hosted zone has records for VN and EU, but no Default. Visitors in Canada get no answer. What should you do?

**Answer:** Configure a **Default geolocation record** if you intend to serve remaining regions; verify zone/record type, DNS cache, health checks, and actual behavior. If the business intentionally refuses service in Canada, enforce that decision in the security/application layer rather than relying on an empty DNS answer as legal compliance.

### Exercise 5 — Health Check Pointing to the Controlled Hostname

You point the Singapore endpoint's health check to **api.example.com**, while api.example.com has latency records for Singapore and Tokyo. Why is that dangerous?

**Answer:** The health check can pass through the routing policy itself and hit the other backend, causing health status to misrepresent Singapore's endpoint. Probe a dedicated hostname/IP/endpoint per backend instead.

### Exercise 6 — Multi-Region Without Data

Route 53 Latency policy shifts users from Singapore to Tokyo when Singapore fails. The Tokyo ALB is healthy, yet business queries fail because Tokyo lacks the latest data.

**Answer:** Load balancer health checks do not prove data/application readiness. Design data replication, consistency, thorough readiness/health checks, RPO/RTO targets, and failover drills before claiming multi-Region resilience.

## 17. Self-Check Questions

**Question 1.** Does Route 53 Weighted routing guarantee exactly 10% of HTTP requests reach canary?  
**Answer:** No. Weights guide DNS answer distribution; caching, persistent connections, and client behavior can make request ratios differ.

**Question 2.** Two weighted records have weights 30 and 70; what share does the first record get?  
**Answer:** Roughly 30% of DNS answers when both are eligible/healthy and no other records exist in the group.

**Question 3.** If all weighted records have weight 0, does Route 53 return no answer?  
**Answer:** No. They can be selected with equal probability per AWS rules.

**Question 4.** When can a weight 0 record still be selected?  
**Answer:** When all positive-weight records are marked unhealthy in a proper health-checked setup, or when the entire group has weight 0.

**Question 5.** Does Latency routing choose the closest endpoint in kilometers or based on AWS data?  
**Answer:** Based on estimated network latency data to configured AWS Regions, not simple geographic distance.

**Question 6.** What location types does Geolocation route by?  
**Answer:** Continent, country, U.S. state where supported, and Default.

**Question 7.** Given records for Asia, Vietnam, and Default, which record takes precedence for a query geolocated in Vietnam?  
**Answer:** Vietnam, because it is the more specific location match.

**Question 8.** Why is a Default record needed?  
**Answer:** To serve locations with no match or unidentifiable IPs; omitting Default can cause no DNS answer for those queries.

**Question 9.** How does Geoproximity differ from Geolocation and Latency?  
**Answer:** Geoproximity computes zones of influence from resource/client location and bias, unlike Geolocation's country/continent rules and Latency routing's real latency measurements.

**Question 10.** With health checks configured, if all endpoints are unhealthy, does Route 53 always return no answer?  
**Answer:** No. Route 53 exhibits fail-open behavior per policy group to continue returning answers in several configurations.

**Question 11.** Does a 60-second TTL guarantee every client switches endpoints exactly 60 seconds after an update?  
**Answer:** No. Caches, resolvers, application behavior, open connections, and DNS propagation all affect timing.

**Question 12.** What does EDNS Client Subnet help with?  
**Answer:** When supported by the DNS resolver, it sends part of the client's subnet so Route 53 can estimate location instead of relying solely on the resolver's IP.

**Question 13.** Can `TestDnsAnswer` be used to test a private hosted zone?  
**Answer:** No. The **test-dns-answer** API only supports **public hosted zones**.

**Question 14.** Does Route 53 Latency routing replicate databases across AWS Regions?  
**Answer:** No. Data replication/failover must be architected separately.

**Question 15.** If you need to test a new feature with exactly 5% of user IDs, is weighted DNS ideal?  
**Answer:** No. Feature flags or application-layer user/session routing are better suited for exact user-cohort control.

**Question 16.** Does Route 53 replace CloudFront for edge caching of static images?  
**Answer:** No. Route 53 returns DNS answers; CloudFront is the CDN that delivers and caches content.

## 18. Summary

**Key policies to distinguish:**

- **Weighted routing:** chooses records by **relative weight**. Suited for canary, gradual traffic shifting, and active distribution; does not guarantee HTTP request percentages or hard-disable an endpoint via weight 0 alone.
- **Latency-based routing:** chooses the **AWS Region with the best predicted network latency** for the DNS query source. Suited for active-active multi-Region; does not guarantee regulatory data residency boundaries.
- **Geolocation routing:** chooses endpoints by **continent/country/U.S. state**, prioritizing the most specific match and requiring a **Default**. Suited for market-based content routing; does not pinpoint individual users with certainty.
- **Geoproximity routing:** chooses by **location and bias** to expand/shrink a resource's zone of influence; not equivalent to latency measurement.

**Safe deployment mindset:** Pick policy by goal → structure records/aliases properly → attach accurate health checks → account for TTL/caching/resolvers/ECS → validate app and data in every Region → monitor performance/error rates → rehearse rollback/failover → govern IAM, DNS delegation, and total cost.

Route 53 determines the **DNS answer**, while product availability also depends on **ALB, VPC, compute, database, IAM, TLS, monitoring, and recovery**. Designing both layers ensures effective, secure, and resilient AWS operations.

### Official AWS Documentation

- [Choosing a routing policy](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/routing-policy.html) — Route 53 routing policies.
- [Weighted routing](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/routing-policy-weighted.html) — weights and weight-0 behavior.
- [Latency-based routing](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/routing-policy-latency.html) — choosing Regions by latency.
- [Geolocation routing](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/routing-policy-geo.html) — specific locations, precedence, and Default.
- [Geoproximity routing](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/routing-policy-geoproximity.html) — bias and zones of influence.
- [EDNS0 and client location](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/routing-policy-edns0.html) — using resolver IP and EDNS Client Subnet.
- [How Route 53 chooses records with health checks](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/health-checks-how-route-53-chooses-records.html) — healthy, unhealthy, and fail-open.
- [Best practices for Route 53 DNS](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/best-practices-dns.html) — TTL, routing, propagation, and DNS design.
- [AWS CLI: test-dns-answer](https://docs.aws.amazon.com/cli/latest/reference/route53/test-dns-answer.html) — simulating answers from public hosted zones.
