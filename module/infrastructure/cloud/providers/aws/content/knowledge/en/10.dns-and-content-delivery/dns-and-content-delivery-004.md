# Health Checks, DNS Failover, and TTL

> **Chapter:** DNS and Content Delivery  
> **Module:** `CLOUD_PROVIDERS_AWS` — exploring the AWS ecosystem from Regions/AZs, IAM, and VPCs to compute, storage, databases, integration, and serverless; practicing secure, observable, resilient, and cost-controlled system design.

When a system serves customers via a domain name like `app.example.com`, users do not need to know which Availability Zone (AZ) or AWS Region holds the servers. **DNS** finds the service address/target, while **health checks** determine which target still meets health criteria. Amazon Route 53 **DNS failover** combines both: if the primary target is evaluated as unhealthy, Route 53 can return the standby target for new DNS queries.

However, there is a critical limitation: **Route 53 cannot immediately control existing open connections or DNS records already cached by clients**. Therefore, failover design must account for **TTL (Time to Live)**, failure detection time, standby system readiness, and application retry/reconnect behavior.

Domain names, IP addresses, Regions, and configurations in this lesson are examples. Content focuses on **public DNS/Route 53** with necessary notes for private endpoints; real deployments must verify hosted zone type, target services, IAM permissions, quotas, and currently supported features.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Trace the path of a DNS query from an application to a recursive resolver and authoritative DNS.
2. Distinguish **Route 53 health checks**, **ALB target-group health checks**, **CloudWatch-alarm-based health checks**, and alias **Evaluate Target Health**.
3. Configure **primary/secondary failover** logic and explain outcomes when one or both targets are unhealthy.
4. Analyze the impact of **TTL**, recursive caching, long-lived client connections, and failure detection time on RTO.
5. Design two-Region failover with readiness endpoints, data replication, authentication, failback conditions, and observability plans.
6. Use the AWS CLI or DNS tools to inspect records, health status, and DNS answers without modifying resources.

## 2. What Does DNS Do—and What Doesn't It Do?

DNS (Domain Name System) translates a name like `app.example.com` into appropriate DNS data, such as `A`/`AAAA` records or other reference chains. **Amazon Route 53** can act as **authoritative DNS** for a public hosted zone, meaning it is the authoritative service answering for records in a domain delegated to it.

### 2.1. Path of a Query

~~~mermaid
sequenceDiagram
    participant App as Application / browser
    participant Resolver as Recursive DNS resolver
    participant R53 as Route 53 authoritative DNS
    participant API as Application endpoint
    App->>Resolver: Query A app.example.com
    alt Resolver still has valid cached record
        Resolver-->>App: Return cached record
    else Cache expired or missing
        Resolver->>R53: Query authoritative DNS
        R53-->>Resolver: Answer per current routing and health
        Resolver-->>App: Return answer and cache per TTL
    end
    App->>API: HTTPS connection to received address/target
~~~

The diagram simplifies DNS resolution; real lookups involve root/TLD/name servers, OS/application DNS caches, and possibly CNAMEs or multi-step queries. The key takeaway is that **Route 53 does not receive every query from every client**: many clients may share one recursive resolver, and the resolver can answer from cache without re-querying authoritative DNS.

### 2.2. DNS Is Not the Application Data Plane

- Route 53 answers **"where should you go?"**, not a proxy forwarding every HTTP request from client to server.
- Once it has an IP, the client opens TCP/TLS/HTTP per its application logic. A DNS change **does not automatically close live TCP connections**.
- Route 53 does not replace ALB, Auto Scaling, Security Groups, WAF, databases, or data recovery mechanisms.
- If DNS returns a healthy endpoint that lacks recent data, lacks capacity, or has permission errors, business operations will still fail.

### 2.3. Relevant Record Types

| Record | Role | Failover Relevance |
| --- | --- | --- |
| `A` | Returns IPv4 address | Can be used with failover routing policy |
| `AAAA` | Returns IPv6 address | If IPv6 is supported, plan IPv6 failover paths too |
| `CNAME` | Maps one name to another DNS name | Do not use CNAME at the zone apex per standard DNS rules |
| **Route 53 alias A/AAAA** | Points to a supported AWS resource or a record in the hosted zone | Supports failover and `Evaluate Target Health` when the target supports it |
| `NS`, `SOA` | Delegation and zone metadata | Essential for DNS hosting, not the primary/secondary pair |

**Alias is not synonymous with CNAME.** Alias is a Route 53 feature allowing `A`/`AAAA` records to point to supported resources like Elastic Load Balancing and works at the zone apex. Choose record types and targets based on resource documentation rather than arbitrarily using CNAME everywhere.

## 3. Health Checks in Route 53

A **health check** evaluates whether a resource or operational signal meets configured conditions. Route 53 uses that status to decide which records can be returned under supported routing policies.

### 3.1. Ways to Evaluate Health

| Evaluation Method | Input Signal | When to Use |
| --- | --- | --- |
| **Endpoint health check** | TCP, HTTP, or HTTPS probes to an endpoint | When a URL/port check reflects service availability |
| **CloudWatch alarm health check** | Alarm state and configured missing-data handling | When health cannot be measured by one HTTP URL and requires business metrics |
| **Calculated health check** | Combines status of child health checks | To express composite system health rules |
| **Private endpoint health check** (where available) | Health check source inside a VPC probing a private endpoint | Internal endpoints, distinct from public health checkers |
| **Alias Evaluate Target Health** | Status provided by AWS for a supported alias target | Alias records to ALB or resources supporting target health evaluation |

Not every option works identically across all alias record types and resources. For instance, do not assume `Evaluate Target Health` works the same for ALB, CloudFront, S3 websites, and every AWS service. Always verify target documentation and supported health mechanisms before use.

### 3.2. Endpoint Health Check: HTTP/HTTPS or TCP?

- **TCP**: only verifies whether a TCP connection can be established to the target port. An open port **does not prove the application can process transactions**.
- **HTTP/HTTPS**: sends a request to the configured endpoint (host/port/path) and checks the response; typically **2xx/3xx** status codes pass, with optional body **string matching** where supported.
- **HTTPS**: tests the HTTPS path, but do not assume it replaces monitoring **certificates, expiration dates, domain names, or TLS settings** required by security policy.
- **CloudWatch alarm**: suitable when health depends on metrics like transaction success count, queue backlog, or business errors not fully captured by an HTTP check.

A simple endpoint:

~~~http
GET /health/ready HTTP/1.1
Host: primary.example.net
~~~

Example healthy response:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain

READY
~~~

Failure response when the application cannot serve traffic:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: text/plain

NOT_READY
~~~

**Distinguish liveness from readiness:**

- **Liveness:** is the process running or hung; usually used to restart containers/processes.
- **Readiness:** is the instance/Region ready to serve live traffic; better suited for traffic routing.

An endpoint returning `200` merely because the web server is alive can keep Route 53 routing to a Region that lost its database or required dependencies. Conversely, a health check **too tightly coupled** to non-critical systems can trigger false failovers and constant flapping. Define a signal close to business readiness while avoiding heavy checks that overload the service.

### 3.3. Interval and Failure Threshold

For standard Route 53 endpoint health checks, you can choose an interval such as **30 seconds (standard)** or **10 seconds (fast)**, depending on supported types/features. **Failure threshold** is the number of consecutive failed checks before a checker marks an endpoint unhealthy; the default is often **3**.

Illustrative configuration:

| Property | Value |
| --- | --- |
| Type | HTTPS |
| Domain name | `primary.example.net` |
| Port/path | `443` / `/health/ready` |
| Request interval | 30 seconds |
| Failure threshold | 3 |
| Health-checker regions | Selected checker regions per support |

**Do not calculate "detection time = 30 × 3 = exactly 90 seconds."** Route 53 uses multiple health checkers across locations, each running on its own schedule, plus response timeouts, status aggregation, and DNS resolver caching. Ninety seconds is only an intuitive rough guide for the threshold, not an SLA or exact RTO.

A 10-second interval reacts faster in some cases, but usually **costs more** and still does not guarantee every client switches immediately.

### 3.4. Public Endpoints and Private Endpoints

Traditional **public** endpoint health checks use publicly accessible Route 53 health checkers. They cannot magically connect to a private IP `10.0.1.10` just because it exists in a VPC. Identify the real network path:

- For an internet-facing ALB or public API, use a health check matching host/path/port and ensure Security Groups/WAF do not accidentally block checkers.
- For services using private IPs only, use **private endpoint health checks** where supported by Region/features, or monitor from inside the VPC and surface status via a CloudWatch alarm/appropriate solution.
- Private endpoint health checks use a health-check source inside the VPC, with their own subnet/AZ/DNS requirements and failure domain; they are **not** the same as letting public health checkers reach private IPs directly.

For private applications, also consider **private hosted zones** and Route 53 Resolver within DNS scope. Public DNS failover does not create cross-Region private VPC connectivity.

### 3.5. When the Checked Host Matches the DNS Failover Name

If both primary and secondary are served under `app.example.com`, **do not** create a health check targeting `app.example.com` and attach that same health check to the record deciding what `app.example.com` returns. Having a health check depend on the DNS record it controls causes observation loops and unpredictable behavior.

Instead, use independent endpoints:

~~~text
app.example.com               ← User-facing failover DNS
primary.example.net           ← Primary health check (does not loop back through failover)
secondary.example.net         ← Secondary health check
~~~

If probing HTTPS by hostname, verify the `Host` header, TLS SNI, certificate, path, and WAF rules so the check hits the intended vhost. The checked address must represent the specific Region's service rather than passing through a shared cache/proxy that masks origin failures.

## 4. How Are Route 53 Health Checks Different from ALB Health Checks?

Production applications usually have multiple routing layers:

~~~mermaid
flowchart TB
    C["Client / recursive DNS resolver"] --> R53["Route 53 failover\nselects endpoint/Region"]
    R53 --> P["Primary Region ALB\nmulti-AZ"]
    R53 --> S["Secondary Region ALB\nmulti-AZ"]
    P --> PT["Primary target group\nEC2/ECS across AZs"]
    S --> ST["Secondary target group\nEC2/ECS across AZs"]
    PT --> DBP["Primary database"]
    ST --> DBS["Standby data\nmeeting RPO target"]
~~~

- **ALB target-group health checks** evaluate EC2/ECS/IP targets behind the ALB so Elastic Load Balancing distributes requests only to healthy targets.
- **Route 53 health checks** typically decide which **top-level endpoint** DNS returns (e.g., primary Region vs. standby Region).
- **Alias Evaluate Target Health** can consume the health signal provided by a supported target service (such as an ALB) instead of maintaining a separate Route 53 endpoint health check for that alias.

An ALB can have a healthy target group while the order workflow fails due to another dependency. Conversely, one failed target does not mean the whole Region is down: ALB/Auto Scaling can replace the target normally without triggering DNS failover.

**Principle:** fix narrow failures with the narrowest mechanism—recover targets at ALB/ASG first, and fail Route 53 over to another Region only when an outage or availability target truly warrants it.

## 5. DNS Failover: Primary and Secondary

Route 53 provides the **Failover routing policy** for **active–passive** architectures:

- **Primary:** default endpoint, receives DNS queries when Route 53 considers primary healthy.
- **Secondary:** standby endpoint, chosen when primary is unhealthy and secondary is eligible.
- The failover record pair shares the **same Record name and Record type**, differing by `SetIdentifier`/role `PRIMARY` and `SECONDARY`.
- Both can be non-alias or alias records per supported rules.
- If secondary has no health check, Route 53 can treat it as an available standby for DNS answers without **proving secondary is actually healthy**.

### 5.1. Decision Table When Both Have Health Checks

| Primary | Secondary | Route 53 Answers New DNS Queries With |
| --- | --- | --- |
| **Healthy** | Healthy | **Primary** |
| **Healthy** | Unhealthy | **Primary** |
| **Unhealthy** | Healthy | **Secondary** |
| **Unhealthy** | Unhealthy | **Primary** per this failover rule |

The last row is easily overlooked: **Route 53 cannot invent a healthy target when both are broken.** For a health-checked failover pair, if no healthy target remains, it can return primary rather than answering "no service." Thus, **simply seeing a DNS record returned is not proof that the endpoint is healthy**.

If you omit a health check on secondary, Route 53 cannot verify its actual state through that check. Traffic could be sent to a broken secondary even while primary is also down.

### 5.2. Two-Region Failover Sequence

~~~mermaid
sequenceDiagram
    participant HC as Health checkers
    participant P as Primary Region
    participant R53 as Route 53
    participant DNS as Recursive resolver
    participant C as Client
    participant S as Secondary Region
    HC->>P: HTTPS /health/ready
    P-->>HC: Consecutive 503 / timeouts
    HC->>R53: Primary status = unhealthy
    C->>DNS: Query app.example.com
    alt Resolver cache expired
        DNS->>R53: Query failover record
        R53-->>DNS: Secondary record
        DNS-->>C: Secondary (with TTL)
        C->>S: Open new connection
    else Resolver still caches primary
        DNS-->>C: Primary still cached
        C->>P: May continue failing
    end
~~~

**DNS failover does not transfer in-flight requests.** HTTP clients may need retries; TCP connection pools may still hold old IPs/connections; login sessions or state stored locally in the primary Region may not exist in the secondary Region.

### 5.3. Failback: When Primary Recovers

By default, once primary is deemed healthy again, Route 53 can resume returning primary for new DNS queries. However, **automatic failback** is not always safe:

- Primary may still suffer from **data lag** after the incident.
- Writes that happened on secondary might not yet be synced back.
- A freshly recovered service may lack warmed-up capacity.
- The health endpoint might "flap" (oscillating healthy/unhealthy).

In systems requiring strict control, use readiness signals that reflect data state, approved failback procedures, or manual/Route 53 ARC routing controls per your DR runbook. Never let DNS bounce back and forth while the data layer's write role is ambiguous.

## 6. TTL — Why Isn't Failover Instant?

**TTL (Time to Live)** is how long a DNS record may sit in a **resolver's cache** before querying authoritative DNS again. TTL is typically expressed in **seconds**, though actual caching behavior also depends on the OS, DNS resolver, and client libraries.

Non-alias record example:

~~~text
app.example.com.  60  IN  A  192.0.2.10
                  ^^
                  TTL = 60 seconds
~~~

`192.0.2.10` is an IPv4 address **used solely for documentation examples**; it is not a live Internet endpoint.

### 6.1. When a Resolver Still Holds Cache

Suppose a resolver queries Route 53 at `10:00:00` and gets primary with a 300-second TTL. Primary fails at `10:00:20`; Route 53 marks primary unhealthy and starts returning secondary at `10:01:00`. The resolver can still return cached primary until roughly `10:05:00` if it honors the 300-second TTL without early prefetching.

~~~text
10:00:00   Resolver fetches primary, TTL = 300s
10:00:20   Primary suffers an outage
10:01:00   Route 53 already returns secondary for new queries
10:02:00   Old resolver may still return primary from cache
10:05:00   Old cache expires; resolver re-queries and gets secondary
~~~

Timestamps are illustrative only. Some resolvers extend caches, prefetch early, or enforce min/max TTL floors; Java/JVM apps, HTTP clients, proxies, or mobile apps can also cache DNS independently.

### 6.2. Short TTL vs. Long TTL

| Sample TTL | Advantage | Trade-off |
| --- | --- | --- |
| **30–60 seconds** | Resolvers honoring TTL have a chance to pick up the new target sooner | Increases DNS queries as caches expire more often; does not eliminate health detection delay |
| **300 seconds** | Reduces queries to authoritative DNS | Stale answers can persist for several minutes |
| **3,600 seconds** | Long caching, fewer lookups | Unsuitable for applications needing fast failover |

For non-alias records with Route 53 health checks, AWS recommends a TTL of **60 seconds or less** so clients react relatively quickly to health changes. That is a **recommendation**, not a guarantee of 60-second regional failover.

**TTL is not a waiting period before Route 53 changes its answer.** Once a health check flips status, Route 53 updates its selection for new queries immediately; TTL governs how long recursive resolvers/clients keep using the previous answer.

### 6.3. TTL with Alias Records

If a Route 53 **alias** points directly to a supported AWS resource, you typically **do not set a TTL on the alias record**; Route 53 uses the TTL of the **alias target**. For example, ALB/ELB typically uses a TTL around **60 seconds** per service behavior. If an alias points to another record in the same hosted zone, TTL follows the target record.

**Do not confuse** the lack of a TTL input box when creating an alias record with "DNS does not cache." Alias responses still carry a TTL when returned by authoritative DNS.

### 6.4. TTL and RTO

A simple mental model:

~~~text
Time until a client actually uses secondary
  ≈ time to detect primary unhealthy
  + time to update status/routing
  + remaining DNS cache time at resolver/client
  + reconnect/retry time
  + time for secondary to have sufficient capacity and data ready
~~~

This is **not an SLA formula**: some steps overlap, and each client has different paths and caches. It helps ask the right questions when designing **RTO**.

For example, setting a 30-second TTL will not solve an outage if:

- Health checks take a long time to confirm failure.
- Applications hold existing connections for minutes without reconnecting.
- Secondary is not warmed up or lacks a database.
- Resolvers ignore short TTLs.

## 7. Designing a Scenario: Multi-AZ Application with Cross-Region Failover

### 7.1. Context

Suppose an e-commerce application runs in the **Singapore Region** (`ap-southeast-1`) with a standby in the **Sydney Region** (`ap-southeast-2`). Illustrative layout:

~~~text
app.example.com           -> Route 53 Failover DNS

Primary, Singapore:
  ALB (2+ AZ) -> EC2/ECS application (2+ AZ) -> primary database
  Health endpoint: primary.example.net/health/ready

Secondary, Sydney:
  ALB (2+ AZ) -> standby app and data ready to serve
  Health endpoint: secondary.example.net/health/ready
~~~

Choosing two Regions involves **trade-offs across latency, data residency, replication capability, and cost**. Pick Regions based on real business needs; do not treat this example pair as a default recommendation for every company.

### 7.2. Active–Passive vs. Active–Active

| Approach | Normal Flow | When Primary Region Fails | Data Complexity |
| --- | --- | --- | --- |
| **Active–passive** | Only primary receives user traffic | Route 53 shifts new DNS queries to secondary | Must ensure secondary is ready, synced, and write roles are clear |
| **Active–active** | Multiple Regions serve simultaneously | Traffic shifts to healthy Regions per routing policy | Must solve multi-Region writes, conflicts, sessions, and consistency |

Primary/secondary failover routing policy fits **active–passive**. For active–active, consider weighted, latency-based, or other routing strategies with appropriate health checks, without expecting DNS to "automatically solve" multi-Region data.

### 7.3. Network and Security Architecture

In each Region:

- Internet-facing ALB across subnets in multiple AZs, HTTPS listener with a valid certificate.
- Applications in private subnets, Auto Scaling/ECS with planned capacity.
- App Security Groups allow traffic only from the ALB; never expose backend ports publicly.
- Health endpoint reachable along the expected check path without leaking sensitive info in responses.
- IAM roles and secrets provisioned for each Region/account; no access keys baked into AMIs/images.
- WAF/CDN, Route 53 records, and certificates aligned for failover; avoid a standby endpoint with a mismatched TLS hostname.

**Common pitfall:** primary has a multi-AZ ALB, while secondary has a single EC2 instance and an unsynced database. DNS fails over cleanly yet the app still fails—this is not a "TTL too long" problem.

### 7.4. Ensuring Data and RPO

Before enabling automatic user failover to secondary, answer:

1. **How are orders written in primary** replicated to secondary?
2. **What is the maximum acceptable RPO** (data loss)?
3. Is secondary allowed to **accept writes**, or does it only serve read/notice views?
4. When primary returns, must writes made on secondary be synced back?
5. Do all dependencies—S3, databases, queues, caches, Secrets Manager—exist in secondary with proper access permissions?

RDS Multi-AZ only provides AZ-level redundancy within a single Region for supported deployments; it does not create a **cross-Region disaster recovery** plan. S3 replication is usually asynchronous and has lag. DNS failover is **traffic routing**, not data replication.

## 8. Creating a Failover Record Pair Properly

Suppose you have two **ALBs**, one in each Region. With Route 53 **alias A records**, you can create the pair:

| Field | Primary record | Secondary record |
| --- | --- | --- |
| Name | `app.example.com` | `app.example.com` |
| Type | `A` | `A` |
| Routing policy | Failover | Failover |
| Set identifier | `app-primary` | `app-secondary` |
| Failover role | **PRIMARY** | **SECONDARY** |
| Alias target | Singapore ALB DNS name | Sydney ALB DNS name |
| Evaluate Target Health | **Yes** if supported and appropriate | **Yes** if supported and appropriate |
| TTL | Inherited from alias target | Inherited from alias target |

When attaching separate health checks to **non-alias** failover records, assign the matching health check and a short TTL. With alias records, Route 53 can use **Evaluate Target Health** instead of a separate endpoint health check when the resource supports it; if combining both a health check and Evaluate Target Health, understand how the combined evaluation works.

### 8.1. CloudFormation YAML Example (Illustrative, Undeployed)

The snippet below shows only two **Route 53 alias failover recordsets**. Bucket/Region/ALB/zone parameters must come from real infrastructure. Specifically, **`HostedZoneId` inside `AliasTarget` is each load balancer's canonical hosted zone ID**, not the domain's hosted zone ID.

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: Route 53 DNS failover records (example)

Parameters:
  PublicHostedZoneId:
    Type: String
  PrimaryAlbDnsName:
    Type: String
  PrimaryAlbCanonicalZoneId:
    Type: String
  SecondaryAlbDnsName:
    Type: String
  SecondaryAlbCanonicalZoneId:
    Type: String

Resources:
  PrimaryRecord:
    Type: AWS::Route53::RecordSet
    Properties:
      HostedZoneId: !Ref PublicHostedZoneId
      Name: app.example.com.
      Type: A
      SetIdentifier: app-primary
      Failover: PRIMARY
      AliasTarget:
        DNSName: !Ref PrimaryAlbDnsName
        HostedZoneId: !Ref PrimaryAlbCanonicalZoneId
        EvaluateTargetHealth: true

  SecondaryRecord:
    Type: AWS::Route53::RecordSet
    Properties:
      HostedZoneId: !Ref PublicHostedZoneId
      Name: app.example.com.
      Type: A
      SetIdentifier: app-secondary
      Failover: SECONDARY
      AliasTarget:
        DNSName: !Ref SecondaryAlbDnsName
        HostedZoneId: !Ref SecondaryAlbCanonicalZoneId
        EvaluateTargetHealth: true
~~~

**Limitations of this example:**

- This CloudFormation template **does not create** ALBs, target groups, databases, health endpoints, or ACM certificates.
- `EvaluateTargetHealth` relies on the AWS-supported alias target's health. If the business requires **end-to-end** readiness monitoring (e.g., database), design another appropriate health signal and integrate it validly.
- If delivering via CloudFront, do not copy the ALB health config verbatim assuming Evaluate Target Health works the same for CloudFront. Check CDN/origin failover options or corresponding health checks.
- Add corresponding `AAAA` records if IPv6 is required and supported by the resources.
- Never deploy a test stack onto a production hosted zone: DNS changes can impact all users.

### 8.2. Non-Alias Records as an Alternative

If targets are **publicly reachable static IPs**, you can create non-alias failover `A` records and attach a `HealthCheckId` to each. You then **choose the TTL yourself**, e.g., `60`. However, for an ALB, **never hardcode an IP resolved from the ALB** into an `A` record: load balancer IPs can change; use an alias to the ALB so Route 53 tracks valid addresses automatically.

### 8.3. Avoiding Loops in Health Checks

Never configure primary's health check using `app.example.com` and attach it to the `app.example.com` failover record itself. When primary fails, the health checker may resolve secondary, see secondary healthy, and mistakenly mark primary healthy again. Use **per-endpoint hostnames/addresses** or service-provided health signals.

## 9. Inspecting with AWS CLI and DNS Tools (Read-Only)

The following commands only inspect status and do not create/edit/delete records. Replace hosted zone IDs and health check IDs with real authorized values.

### 9.1. View Failover Records in a Hosted Zone

~~~bash
aws route53 list-resource-record-sets \
  --hosted-zone-id Z0123456789EXAMPLE \
  --query "ResourceRecordSets[?Name=='app.example.com.'].[Name,Type,SetIdentifier,Failover,TTL,HealthCheckId,AliasTarget.DNSName,AliasTarget.EvaluateTargetHealth]" \
  --output table
~~~

Verify:

- Matching **Name** and **Type**.
- One PRIMARY and one SECONDARY, with unique `SetIdentifier` values in the record set group.
- Alias or non-alias targets match the intended Region and endpoint.
- `HealthCheckId`/`EvaluateTargetHealth` align with the design.
- For aliases, the TTL column may appear empty because Route 53 uses the alias target's TTL.

### 9.2. View Health Check and Latest Status

~~~bash
aws route53 get-health-check \
  --health-check-id 00000000-1111-2222-3333-444444444444

aws route53 get-health-check-status \
  --health-check-id 00000000-1111-2222-3333-444444444444
~~~

`get-health-check-status` returns status per health checker along with supported timestamps/details; do not treat it as a complete request log. For an alias relying on ALB `EvaluateTargetHealth` **without a separate Route 53 health check**, there is no health-check ID to pass to `get-health-check-status`.

### 9.3. Test What Route 53 Will Answer

~~~bash
aws route53 test-dns-answer \
  --hosted-zone-id Z0123456789EXAMPLE \
  --record-name app.example.com \
  --record-type A
~~~

`test-dns-answer` tests how Route 53 authoritative DNS answers queries per configuration; it **does not fully simulate** resolver caching, browser DNS caches, HTTP/TLS, or real clients.

### 9.4. Query DNS Like a Client (with `dig`)

~~~bash
dig app.example.com A
dig app.example.com AAAA
dig +short app.example.com A
~~~

Observe the **remaining TTL** of the record in full output; if the resolver already cached it, the observed TTL may be **smaller than the configured TTL**. Use an authorized DNS resolver in your operating environment; there is no need to change system DNS just to test. In corporate networks with split-horizon/private DNS, results may differ from public Internet queries.

### 9.5. Do Not Treat One DNS Answer as Final Proof

When testing failover:

1. **Route 53 health status** shows which target the system currently deems healthy.
2. **Authoritative DNS answer** shows which record Route 53 selects at test time.
3. **Recursive resolver answer** shows what the client-side cache currently returns.
4. **HTTP/TLS test** against the resolved endpoint confirms whether requests actually succeed.
5. **Business metrics** confirm whether the application completes transactions rather than merely returning 200 on a health endpoint.

## 10. Monitoring and Alerting for Failover

A monitoring plan should include **both health signals** and **business signals**:

| Layer | What to Monitor | Why |
| --- | --- | --- |
| **Route 53 health checks** | Healthy/unhealthy status and state transitions over time | Know when DNS failover conditions trigger |
| **CloudWatch alarms** | Health check status, error rates, latency, missing-data alarms | Alert operations on abnormal states |
| **ALB** | HealthyHostCount, HTTP 5xx, TargetResponseTime, target health | Distinguish single-target issues from full-Region failures |
| **Application** | Request rate, p95/p99 latency, checkout success, retries, and reconnects | Assess real user impact |
| **Database** | Replication lag, DB connections, failover events, write errors | Verify whether secondary can process transactions |
| **DNS queries** | Query log patterns if configured, resolver behavior | Spot lookup trends without assuming cache hits appear as queries |
| **Cost** | Hosted zones, DNS queries, health check types, alarms/logging, secondary infrastructure | Track overall DR budget |

Some Route 53 health check CloudWatch metrics appear in a specific Region designated for that feature; check documentation and the regional dashboard before assuming metrics are missing. For private endpoint health checks, metrics/alarms may reside in the checker source's Region.

**Never rely solely on DNS query logs to count users.** A single cached DNS answer can serve many connections without generating new authoritative DNS queries.

## 11. Cost and Design Trade-Offs

| Decision | Benefit | Cost/Risk |
| --- | --- | --- |
| Short TTL on non-alias failover records | Resolvers re-query more often, allowing earlier failover pickup | More authoritative DNS queries; uncontrollable caches still exist |
| Fast health checks | Faster failure detection in some scenarios | Higher fees and greater sensitivity to transient blips |
| HTTPS/string-match health checks | Deeper check than TCP port alone | Extra cost and probe load; requires valid host/path/cert/WAF setup |
| Warm/hot secondary | Better RTO, less startup delay | Ongoing compute, ALB, database, replication, and monitoring costs |
| Cold/backup-only secondary | Lower steady-state running cost | Longer RTO; unsuitable for rapid automatic failover |
| Monitoring both primary and secondary | Avoids failing over to an unhealthy standby | Additional health checks/metrics and operational effort |
| Automatic failback | Can reduce manual intervention | Risk of flapping, split-brain, or unsynced data |

No single TTL or failure threshold fits every application. Choose based on **measured RTO/SLO**, tolerance during stale-cache windows, cost, and real client behavior.

## 12. Common Issues and Remediation

| Symptom | Possible Cause | Priority Check |
| --- | --- | --- |
| Route 53 still returns primary despite app errors | Health check hits wrong hostname, checks TCP only, or ALB health misses DB failure | Endpoint/check type, state, dependencies, alias target health |
| Health check reports unhealthy yet browsers still succeed | Checker blocked by WAF/SG, different Host/SNI/path, status outside 2xx/3xx | Endpoint logs, allowlisting checker sources, probe request config |
| Primary is unhealthy yet some clients still reach primary | Recursive/app DNS cache still valid, connection pools hold old IPs | Returned TTL, resolver, JVM/cache, keep-alive/retries |
| Both primary and secondary unhealthy yet DNS returns primary | Standard failover behavior when both records are unhealthy | Check health of both; never treat DNS response as health proof |
| Route 53 switches to secondary yet writes fail | Secondary lacks data, lacks write role, or differs in IAM/KMS/secrets | RPO, replication, DB topology, app endpoint/roles |
| Failover oscillates back and forth | Over-sensitive readiness check, flaky dependency, no failback control | Review health history and stability criteria before taking load |
| Only IPv4 works after failover | `A` and `AAAA` lack aligned failover strategy | Check both record types and IPv6 connectivity |
| Using ALB alias with no configurable TTL | Alias inherits target TTL | Review AliasTarget docs and DNS answer |
| Health check hostname depends on failover record itself | DNS loop between record and health checker | Use independent hostnames per Region |
| Record changed yet users do not see it | Wrong DNS delegation, TTL cache, or intermediate CNAME chain | Check NS, authoritative answer, resolver chain |

**Handling timeouts:** when a request to secondary times out, do not blindly raise timeouts or lower TTL. Inspect the returned DNS answer, TCP/TLS, Security Groups/NACLs/WAF, ALB targets, logs, and database status to pinpoint the failing layer.

## 13. Rehearsing Failover Before Production

Changing production DNS can affect customers. Safe practice uses **sandbox/staging** or test domains, injecting controlled faults within approved boundaries.

### 13.1. Test Scenario

1. **Prepare:** separate primary and secondary, loop-free health endpoints, test data, and observability.
2. **Record baseline:** query DNS from multiple resolvers, measure remaining TTL, health status, and primary request success rate.
3. **Fail primary in staging:** switch readiness response to `503` or stop a test endpoint—never cut production Internet access.
4. **Observe detection:** log when health checkers see failure, Route 53 marks primary unhealthy, and authoritative answers switch to secondary.
5. **Test clients:** use both a client that cached DNS before the fault and a fresh client; compare when each actually connects to secondary.
6. **Measure business impact:** failed request count, recovery time, retries, session state, and data consistency.
7. **Restore primary:** test failback per approved strategy; never re-enable writes in both Regions simultaneously without data coordination.
8. **Report:** compare actual RTO/RPO against targets, noting TTL, client DNS caching, and capacity findings.

### 13.2. Sample Measurement Table

| Milestone | Illustrative Timestamp | What to Record |
| --- | --- | --- |
| Primary becomes unavailable | `t0` | App/health endpoint failure |
| Route 53 evaluates unhealthy | `t1` | Health status/metrics |
| Authoritative DNS returns secondary | `t2` | `test-dns-answer` or authoritative query |
| Resolver A expires primary cache | `t3` | DNS answer and TTL from client A |
| Client A transacts successfully on secondary | `t4` | Logs, metrics, request ID |
| Secondary data reaches writable state | `t5` | Replication lag, role promotion decision |

**Real RTO** must be measured against accepted business conditions, not simply `t2 - t0`. If secondary DNS is returned yet customers still cannot place orders, the recovery objective has not been met.

## 14. Reinforcement Exercises

### Exercise 1 — Computing Cache Impact

A resolver fetches the primary record at 10:00 with a 300-second TTL. Primary fails at 10:01, and Route 53 switches answers for new queries to secondary at 10:02. The resolver honors TTL and does not prefetch early.

**Question:** when can that resolver start re-querying and receive secondary?

**Hint:** around **10:05** after the cache expires. TTL is not how long Route 53 waits; it is the cache lifetime from when the resolver received the answer.

### Exercise 2 — Choosing Health Records

You have two ALBs in two Regions; each ALB has its own target groups and health checks. Propose Route 53 failover alias records, explain the benefit of `EvaluateTargetHealth=true`, and identify when a readiness signal beyond ALB target state is needed.

**Hint:** an `A` alias pair with the same Name/Type, distinct SetIdentifiers, PRIMARY/SECONDARY, aliasing each ALB, with target health evaluation enabled where supported. If targets are healthy while all writes fail due to the DB, add a business check / CloudWatch alarm instead of equating ALB health with full service health.

### Exercise 3 — Both Targets Unhealthy

Both primary and secondary have health checks, and both are evaluated as unhealthy. Which record does Route 53 return under the failover model?

**Answer:** **primary**. That does not prove primary has recovered; alerting and handling of an all-unhealthy state are still required.

### Exercise 4 — Distinguishing Three Health Checks

One EC2 target fails while the ALB still has multiple healthy targets. Another Region has healthy ALB targets while the DB is down. Decide where ALB target health, Route 53 endpoint health, and CloudWatch alarms help.

**Hint:** ALB handles a single target failure; Route 53 should switch Regions only when the endpoint/Region fails readiness; a CloudWatch alarm can bring business or DB metrics into the decision when an HTTP check is insufficient.

### Exercise 5 — Why Can't DNS Fix Data?

S3 Cross-Region Replication and the replica database lag by several minutes. Primary fails and DNS switches to secondary quickly. The application cannot find some recent orders.

**Hint:** DNS only changes the path to an endpoint; data replication has its own RPO. You need a data-loss tolerance policy, transaction reconciliation, and a decision on whether secondary may accept writes immediately.

### Exercise 6 — Proposing SLOs and Drills

A system needs a 5-minute RTO after a Region failure and allows at most 1 minute RPO. List the measurements required in staging, including health detection, DNS TTL, application caching, secondary capacity, and replication lag. Propose how to make safe failover/failback decisions when primary is flapping.

**Hint:** define pass criteria by **successful transactions and accurate data**, measuring from `t0` to a successful request—not just when authoritative DNS flips its answer. Never assume dropping TTL to 30 seconds achieves a 5-minute RTO if other layers are unready.

## 15. Key Takeaways

Three key points when designing Route 53 failover:

1. **Health checks** determine which endpoint/record is considered healthy based on the configured signal; choose signals that reflect true service readiness without creating DNS loops.
2. **DNS failover** returns primary when primary is healthy, and switches to secondary when primary is unhealthy and secondary is healthy per routing policy. If **both** are unhealthy, Route 53 can still return **primary**; it is not a cure-all for every outage.
3. **TTL and client caching** drive part of the delay each user observes. A new authoritative answer does not automatically flush all existing caches and open TCP connections.

To meet **RTO/RPO** goals, a system simultaneously needs a **truly ready secondary**, a sound data strategy, reliable health signals, client retries/reconnects, monitoring, and a drill plan. DNS is a critical coordination layer, but **it does not replace application and data availability**.

### Official AWS Documentation

- [Amazon Route 53 health checks](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/welcome-health-checks.html) — health check mechanisms, alarms, and results.
- [How Route 53 determines health](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/dns-failover-determining-health-of-endpoints.html) — request intervals, checkers, HTTP/TCP status, and private checks.
- [Creating and updating health checks](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/health-checks-creating-values.html) — configuring endpoints, Host, SNI, thresholds, and string matching.
- [Private endpoint health checks](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/health-checks-private-endpoints.html) — VPC health check sources and network requirements.
- [Active-active and active-passive failover](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/dns-failover-types.html) — failover models.
- [How Route 53 chooses records when health checking is configured](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/health-checks-how-route-53-chooses-records.html) — primary/secondary decisions and when both are unhealthy.
- [Values specific for failover records](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/resource-record-sets-values-failover.html) — Record Name, TTL, HealthCheckId, and limits.
- [Values specific for failover alias records](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/resource-record-sets-values-failover-alias.html) — alias and Evaluate Target Health.
- [Choosing between alias and non-alias records](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/resource-record-sets-choosing-alias-non-alias.html) — alias TTL and AWS resource support.
- [Route 53 DNS failover configuration task list](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/dns-failover-how-to.html) — configuration workflow from health checks to records.
- [Amazon Route 53 pricing](https://aws.amazon.com/route53/pricing/) — hosted zones, queries, health check types, and related charges.
