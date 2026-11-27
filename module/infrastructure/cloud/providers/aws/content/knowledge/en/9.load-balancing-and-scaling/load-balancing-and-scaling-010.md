# Coordinating Load Balancers, Auto Scaling, and Multiple AZs on AWS

## Learning Objectives

After this lesson, you will be able to:

- Explain how **Elastic Load Balancing (ELB)**, **EC2 Auto Scaling**, **target groups**, **health checks**, and **Availability Zones (AZs)** work together to keep applications serving continuously as traffic fluctuates.
- Choose **Application Load Balancer (ALB)**, **Network Load Balancer (NLB)**, or another load balancer type based on protocol and requirements; distinguish load balancing from compute capacity scaling.
- Build a web/API architecture with **ALB across multiple public subnets**, an **Auto Scaling group (ASG) running EC2 in private subnets across multiple AZs**, and data tiers with matching availability mechanisms.
- Understand **load balancer health checks**, **ASG EC2/ELB health checks**, **health check grace period**, **instance warmup**, **target deregistration delay**, and their roles during scaling or failed-instance replacement.
- Select **target tracking**, **step scaling**, **scheduled scaling**, or **predictive scaling** based on workload data; define min/desired/max capacity and test peak load, single-instance failure, and single-AZ failure scenarios.
- Verify configurations using the AWS Console, AWS CLI, CloudWatch, and real testing tools; isolate faults across subnets, security groups, target registration, health checks, policies, quotas, and stateful data.
- Estimate resources/costs, design security, logging, backups, RTO/RPO, and recovery plans rather than treating instance count as the sole measure of reliability.

**Context:** This lesson belongs to the **Load Balancing and Scaling** chapter in the **CLOUD_PROVIDERS_AWS** module. Learners have already covered AWS building blocks: **Regions/AZs, IAM, VPC, compute, storage, databases, integration, and serverless**. In practice, an API running on EC2/ECS must combine **request distribution**, **backend fleet sizing**, and **multi-fault-domain placement** to meet security, observability, resilience, and cost goals.

> **Scope:** Hands-on examples use **Application Load Balancer + Amazon EC2 Auto Scaling** to make the mechanics clear. With **ECS Service Auto Scaling**, **EKS Horizontal Pod Autoscaler**, or Lambda concurrency, compute scaling is managed by each platform's own controller; never treat those mechanisms as EC2 Auto Scaling groups even when paired with ALB/NLB.

## 1. Three Components Solving Three Different Problems

A single EC2 instance can serve a website under low traffic. Yet as traffic grows or an instance fails, three questions must be answered:

1. **Which instance receives each user request?** → **Load balancer**.
2. **How many instances are needed right now, and what adds or removes them?** → **Auto Scaling**.
3. **If one AZ goes down, do backends in another AZ and traffic paths keep working?** → **Multi-AZ distribution**, combined with health checks and fault-tolerant dependencies.

| Component | Primary Responsibility | Does Not Do on Its Own |
| --- | --- | --- |
| **Load balancer** | Accepts connections/requests, selects eligible targets, runs configured target health checks | Does not launch EC2 instances on load spikes; does not back up data |
| **EC2 Auto Scaling group** | Maintains and adjusts EC2 counts per min/desired/max; replaces unhealthy instances | Does not replace ALB HTTP request routing; does not replicate databases |
| **Multiple Availability Zones** | Separates components across fault domains within a Region | Does not guarantee HA if healthy backends exist in only one AZ or a shared dependency fails |
| **CloudWatch / alarms** | Measures latency, errors, capacity, CPU, and metrics for decisions/alerts | Does not automatically fix application bugs |
| **Databases / queues / caches** | Manages application data and state | Not automatically protected simply because EC2 scales |

**Right mental model:** Load balancer and ASG cooperate to **route traffic and adjust backend counts**. **Multi-AZ** provides infrastructure fault isolation. All three must be configured properly and then **tested end-to-end** at the application layer.

### Typical Web Application Flow

~~~mermaid
flowchart TB
    Client[Client / Browser] --> DNS[Route 53 / DNS]
    DNS --> ALB[Application Load Balancer - Region]
    ALB --> TG[Target group: HTTP 8080]

    subgraph VPC["VPC in one AWS Region"]
        subgraph AZA["Availability Zone A"]
            PubA[Public subnet A / ALB node]
            AppA[Private subnet A / EC2 A]
        end
        subgraph AZB["Availability Zone B"]
            PubB[Public subnet B / ALB node]
            AppB[Private subnet B / EC2 B]
        end
        TG --> AppA
        TG --> AppB
        ASG[EC2 Auto Scaling group] -. Launch, register, replace .-> AppA
        ASG -. Launch, register, replace .-> AppB
    end

    AppA --> DB[(RDS Multi-AZ or suitable DB)]
    AppB --> DB
    AppA --> S3[(S3: images / objects)]
    AppB --> S3
    ASG --> CW[CloudWatch / scaling policies]
~~~

This is a **logical diagram**. ALB is a Regional resource enabled across multiple AZs; DNS and ALB nodes handle incoming traffic per service mechanics. The **target group** holds eligible targets; the **ASG** launches/terminates EC2 instances and handles registering/deregistering them with the target group. Requests do not travel sequentially across every AZ shown.

## 2. Which Load Balancer Fits?

AWS provides several Elastic Load Balancing types serving different protocol layers.

| Type | Layer / Key Traits | Best-Fit Scenarios | Points to Check |
| --- | --- | --- | --- |
| **Application Load Balancer (ALB)** | Layer 7: HTTP/HTTPS, routing by path/host/header and rich web features | Websites, REST APIs, HTTP(S) microservices, gRPC where supported | Target groups, health checks, TLS, routing rules, idle timeout, sticky sessions |
| **Network Load Balancer (NLB)** | Layer 4: TCP/UDP/TLS, high performance, static IPs per configuration | TCP/UDP services, game servers, apps needing static IPs / L4 features | Cross-zone, client IP preservation, TLS/listeners, target types, health checks |
| **Gateway Load Balancer (GWLB)** | Integrates/scales virtual traffic-inspection appliances via supported encapsulation | Network firewalls / inspection appliances | GWLB endpoints, route symmetry, appliance config, availability |
| **Classic Load Balancer (CLB)** | Legacy generation for older apps | Maintaining existing legacy workloads | Evaluate migrating new architectures to ALB/NLB |

**Quick selection rules:**

- HTTPS API routing `/users` and `/orders` → start with **ALB**.
- Specialized TCP/UDP services or needing static load-balancer IPs → evaluate **NLB**.
- Inserting virtual firewall appliances inline → **GWLB**.
- Container apps on Fargate behind ALB: use **target type = ip** where appropriate; EC2 ASGs in this lesson use **target type = instance**.

### Listeners and Target Groups Are Two Distinct Configurations

A **listener** defines which protocol and port ALB accepts and uses **rules** to decide where requests go. A **target group** holds the list of EC2/IP/Lambda targets per supported type, destination protocol/port, and health check settings.

Example:

~~~text
Users:
  HTTPS 443 → ALB listener
                  ├─ /api/* → target group "api" → EC2 port 8080
                  └─ /web/* → target group "web" → EC2 port 3000
~~~

On a public ALB, use **HTTPS with TLS certificates managed via ACM** per security requirements. The ALB → backend hop can use HTTP inside the VPC when policy permits, or end-to-end HTTPS when required. Manage app secrets via IAM/Secrets Manager; ALB does not replace business authorization.

## 3. Understanding Availability Zones and Subnet Layout

An **AWS Region** contains multiple AZs—physically separated infrastructure zones built to reduce correlated failures. A **subnet spans only a single AZ**. A VPC spans the Region and holds subnets across multiple AZs.

For typical public web/API applications:

- **Internet-facing ALB:** enable **at least two AZs** (ALB requires at least two AZs) using a **dedicated public subnet in each AZ** with routes to an Internet Gateway.
- **EC2 backends in ASG:** use **private subnets in at least two AZs**, allowing backend access from the ALB's SG.
- **RDS / data tier:** deploy Multi-AZ or replication/backups matching RTO/RPO; having multiple EC2 instances alone does not make data multi-AZ.
- **Egress paths:** if EC2 needs Internet/AWS API access, provision per-AZ NAT Gateways or VPC endpoints as needed; do not assume every private instance strictly requires NAT.
- **IAM / security:** enforce instance profiles/roles, Security Groups, private subnets, and least-privilege data access policies.

### Why Public ALB with Private EC2 Instances?

A public ALB acts as a controlled entry point; backends need no public IPs to serve Internet requests. Typical flow:

~~~mermaid
flowchart LR
    User[Internet / HTTPS 443] --> ALB[Public ALB, SG ALB]
    ALB -->|TCP 8080| A[EC2 A, private IP]
    ALB -->|TCP 8080| B[EC2 B, private IP]
    A --> DB[(Private DB)]
    B --> DB
~~~

**Sample Security Groups:**

| Resource | Inbound | Outbound |
| --- | --- | --- |
| **ALB SG** | TCP/443 from allowed client sources (e.g., `0.0.0.0/0` for public web) | To backend SG on TCP/8080 and required health check ports |
| **EC2 backend SG** | TCP/8080 **from ALB SG**; never open directly to the Internet | To database, S3 endpoints/APIs, or required app destinations |
| **DB SG** | DB port such as TCP/5432 **from backend SG** | Per DB needs; never grant arbitrary public inbound |

**ALB needs a valid VPC path to backends**, which never requires placing backends in public subnets. Verify **route tables, SGs, and NACLs** together. When tightening NACLs, remember NACLs are **stateless**, requiring return/ephemeral ports in both directions.

### Single-AZ Outage Scenario

When AZ A loses service, the goal is for new requests to continue reaching **healthy targets in AZ B**, subject to ALB/DNS state and configuration. The ASG attempts to launch replacement instances in surviving eligible AZs, yet **cannot guarantee instant provisioning** if capacity, quotas, or AMIs/launch templates fail.

Even across two AZs, **desired capacity = 2** typically places only **one backend per AZ** under normal conditions. If AZ A goes down, the sole backend in B can overload without extra capacity headroom. **Availability** and **surviving-capacity sufficiency during failures** are two separate properties to measure.

## 4. Cross-Zone Load Balancing and Target Distribution

**Cross-zone load balancing** lets a load balancer node distribute requests to healthy targets in other AZs rather than only targets in the node's own AZ.

### Differences Between ALB and NLB

| Setting | ALB | NLB |
| --- | --- | --- |
| Cross-zone at load balancer level | **Always enabled**; cannot be turned off at ALB level | **Disabled by default**; can be enabled |
| Override at target group level | Can **override** to disable per target group where supported | Can enable/disable or inherit load balancer setting |
| Why consider disabling at TG | Restrict traffic strictly within each AZ to limit cross-AZ blast radius in certain architectures | Keep traffic local to AZ, optimizing fault-domain isolation or data-transfer cost |
| Testing requirements | Target balance, stickiness, per-AZ capacity | Per-AZ resources, client affinity, cross-zone settings, and associated fees |

**Important note:** Never state "ALB can never disable cross-zone anywhere." Cross-zone is always enabled at the **ALB level**, yet a **target group** can override and disable cross-zone; features like stickiness and Lambda targets carry restrictions when target-group cross-zone is turned off. To predict real routing, inspect **both ALB attributes and target group attributes**.

### Example Showing Why Cross-Zone Helps

Suppose two AZs exist:

- ALB node in AZ A receives 50% of traffic; AZ A has **2 targets**.
- ALB node in AZ B receives 50% of traffic; AZ B has **6 targets**.

**Without cross-zone**, the 2 targets in AZ A shoulder far more load per host than each target in AZ B. With cross-zone enabled, nodes distribute load across all 8 healthy targets per the routing algorithm. Still, **cross-zone does not replace having sufficient capacity in one AZ if the other AZ fails**.

### Target Distribution Is Not Always Perfectly Even

Requests landing on each target also depend on:

- The chosen load-balancing algorithm (ALB supports round robin, least outstanding requests, and weighted random per configuration and constraints);
- long-lived sessions and uneven request processing times;
- **sticky sessions** pinning users to the same target;
- slow start, health checks, deregistration, and healthy target counts;
- incoming DNS/zonal traffic split and load-balancer routing policies.

**Never use session stickiness to replace proper state storage.** Store login sessions and shopping carts in a shared store such as DynamoDB, RDS, or ElastiCache, or use signed tokens so user state survives target replacement.

## 5. Target Groups and Health Checks

### 5.1. Load Balancer Health Checks

Each target group defines health check settings:

| Field | Example | Meaning |
| --- | --- | --- |
| **Protocol** | HTTP | How targets are probed |
| **Port** | `traffic-port` or dedicated port | Port receiving health checks |
| **Path** | `/health/ready` | Application endpoint reporting readiness |
| **Matcher** | HTTP `200` | Accepted response status codes per config |
| **Interval** | 15–30 seconds in examples | Probe frequency |
| **Timeout** | Matched to health endpoint latency | Max wait per probe |
| **Healthy threshold** | Multiple consecutive successes | Threshold to mark healthy |
| **Unhealthy threshold** | Multiple consecutive failures | Threshold to mark unhealthy |

In a Java/Spring Boot app, `/health/ready` should reflect whether the instance **has finished initializing and can serve requests**. Never return 200 right when the process starts if migrations or configs are still loading.

### 5.2. Liveness, Readiness, and Dependencies

**Liveness:** is the process alive and free of unrecoverable deadlocks?

**Readiness:** is the instance ready to accept new requests?

For instance, a backend takes 90 seconds on boot to load config, warm caches, and open database pools. Point target group health checks to **readiness** so ALB holds back traffic until initialization finishes, avoiding premature instance replacement loops.

**Balance carefully:** If readiness depends strictly on a flaky external service (such as a third-party payment API), all targets may go unhealthy together and trigger mass replacements even though EC2 hosts are fine. Scope readiness/liveness to true host-level serviceability and use retries/circuit breakers for external dependencies.

### 5.3. Target States to Read

Inspecting target health typically shows:

- **initial:** registering and awaiting initial health check results.
- **healthy:** passing health checks.
- **unhealthy:** failing health checks; inspect reason codes and actual responses.
- **draining:** deregistering and stopping new requests.
- **unused:** excluded due to config or preconditions; inspect detailed reason.

**Never look only at EC2 `running` counts.** A running EC2 instance whose app crashed, whose SG blocks the port, or whose health endpoint returns 503 is **not** an eligible serving backend.

### 5.4. When All Targets Are Unhealthy

Never assume a load balancer always blocks 100% of traffic to unhealthy targets. **ALB exhibits fail-open behavior** under certain conditions when every target across enabled AZs turns unhealthy: it can continue forwarding requests to those targets. That is not HA—alert on **HealthyHostCount = 0**, target errors, and app errors, and fix the root cause fast.

## 6. How Does an Auto Scaling Group Manage EC2 Lifecycles?

An **Amazon EC2 Auto Scaling group (ASG)** manages a fleet of EC2 instances according to launch configs and desired capacity. In multi-AZ designs, the ASG attaches subnets across multiple AZs so AWS attempts to balance instances evenly across zones.

### 6.1. Launch Template

A **Launch template** specifies how instances are created:

- Matching AMI and CPU architecture;
- instance type or mixed-instance options;
- IAM instance profile/role;
- security groups and networking settings;
- EBS root/data volume mappings and encryption;
- user data/bootstrap to start the app and fetch secrets securely;
- tags, metadata security (prefer IMDSv2), and monitoring.

**Common mistake:** the launch template boots EC2 cleanly yet **fails to install or start the application**. ASG keeps producing `running` EC2 instances while the target group marks every single one `unhealthy`.

### 6.2. Min, Desired, and Max Capacity

| Parameter | Meaning | Example |
| --- | --- | --- |
| **MinSize** | Minimum capacity the ASG maintains | 2 |
| **DesiredCapacity** | Current target instance count (when counting by instance) | 4 |
| **MaxSize** | Upper capacity ceiling allowed by config | 10 |

As traffic rises, a scaling policy increases desired from 4 to 6; the ASG launches instances if quotas and capacity allow. As traffic falls, desired drops and the ASG picks instances to terminate per its termination policies.

**DesiredCapacity is not a guaranteed count of healthy targets.** Instances may be `Pending`, `InService`, `Terminating`, failing health checks, or blocked by capacity shortages.

### 6.3. Distribution and AZ Rebalancing

The ASG attempts to keep instance counts balanced across its configured AZs and runs **AZRebalance** when counts drift. However:

- The ASG can launch only in configured AZs/subnets with available capacity;
- losing an AZ temporarily reduces serving capacity;
- AZ rebalancing does not eliminate the need for spare capacity in surviving AZs;
- termination policies, lifecycle hooks, and launch failures affect rebalancing speed.

### 6.4. When Does the ASG Replace a Failed Instance?

The ASG evaluates instance health from supported sources. By **default**, ASG uses **EC2 health checks** and related status signals—it **does not automatically replace an instance solely because a target group reports unhealthy** unless **ELB health checks** are enabled.

When **HealthCheckType = ELB** and target groups are attached, Auto Scaling marks and replaces EC2 instances deemed unhealthy by ELB. If multiple target groups are attached, failing checks in one target group can also trigger replacement under configured health check rules.

**Key distinction:** ALB health checks decide **whether traffic goes to a target**; ASG ELB health checks govern **whether the EC2 instance gets replaced**. The two behaviors cooperate, yet are not identical.

## 7. Integrating ASG, Target Group, and Health Checks

Integration steps:

1. Create an ALB with a listener and matching target group (e.g., `instance` target group, HTTP/8080).
2. Create a launch template ensuring EC2 boots the app and health endpoint cleanly.
3. Create an ASG spanning subnets in at least two AZs with `MinSize`, `DesiredCapacity`, and `MaxSize`.
4. **Attach the target group ARN** to the ASG so it automatically registers new instances and deregisters terminating ones.
5. Enable **ELB health checks** on the ASG when target health should trigger EC2 replacement, setting a **health check grace period** long enough for bootstrapping.
6. Configure dynamic/scheduled scaling policies and test both load scaling and unhealthy-instance replacement.

~~~mermaid
sequenceDiagram
    participant P as Scaling policy / CloudWatch
    participant A as EC2 Auto Scaling
    participant E as EC2 instance
    participant T as ALB target group
    participant U as Customer
    P->>A: Increase DesiredCapacity
    A->>E: Launch instance from launch template
    A->>T: Register new target
    T->>E: HTTP health check /health/ready
    alt Healthy
      T-->>A: Target healthy
      U->>T: Request via ALB
      T->>E: Forward request
    else Unhealthy after grace period expires
      T-->>A: Unhealthy (if ASG uses ELB health checks)
      A->>E: Replace instance per lifecycle
    end
    P->>A: Lower DesiredCapacity when appropriate
    A->>T: Deregister target
    T-->>E: Draining within configured delay
    A->>E: Terminate after lifecycle steps
~~~

The diagram shows the logical sequence; exact timing depends on health checks, hooks, warmup/deregistration timers, and ASG policies.

### Health Check Grace Period vs. Instance Warmup

**Health check grace period** on the ASG: shields newly launched instances from health-based replacement while the app initializes. Too short causes launch/terminate churn; too long delays replacing genuinely broken hosts. **Console ASG creation may use different defaults than CLI/SDK**, so **set an explicit value** grounded in measured bootstrap duration.

**Default instance warmup:** window before scaling policies treat a new instance as fully contributing to load metrics. It prevents **excessive repeat scale-outs** while fresh hosts are still starting and metrics lag.

**Target group health threshold:** criteria for ALB to start or keep routing traffic to a target.

All three parameters must align across the lifecycle, yet **they are not the same counter**. For example, if an app boots in 80 seconds, health checks need two 15-second probes, and warmup needs extra cache-priming time, measure real timings to set grace period, interval, and warmup coherently.

### Deregistration Delay and Graceful Shutdown

During scale-in, removing a target should let in-flight requests complete within a defined window:

- **Target deregistration delay** controls how long a target stays `draining` before deregistration finishes.
- Applications must handle **SIGTERM/shutdown**, stop accepting new requests, and finish in-flight work or fail gracefully.
- **ASG lifecycle hooks** provide wait gates for external deploy/decommission workflows; manage timeouts and heartbeats per docs.
- Never terminate instances mid-way through non-retryable jobs. Offload background jobs to SQS / Step Functions with **idempotency and retries**.

**Clean scale-in is still insufficient if apps hold state in RAM or on a single EBS volume.** If users lose sessions, carts, or uploads on instance replacement, fix the data tier.

## 8. Choosing Scaling Policies Based on the Right Signal

### 8.1. Target Tracking Scaling

**Target tracking** sets a metric goal and lets the ASG adjust capacity to hold that metric near target, like a thermostat.

| Metric | Makes Sense When | Risk If Used Without Verification |
| --- | --- | --- |
| **ASGAverageCPUUtilization** | CPU scales roughly linearly with request/work volume | CPU stays low while app bottlenecks on DB, network, or I/O |
| **ALBRequestCountPerTarget** | Request count approximates load per web instance in the target group | Requests vary wildly in cost, use long polling/WebSockets, or bypass ALB |
| **Custom metric** like queue backlog per instance | Async workers pulling jobs from SQS | Missing datapoints, poorly normalized capacity, or monitoring lag |

For a web API where instances handle uniform traffic through ALB, `ALBRequestCountPerTarget` can outperform CPU if CPU stays flat. Always ground target values in **SLO benchmarks** rather than guesswork.

### 8.2. Step Scaling

Uses **CloudWatch alarms** to add/remove capacity in tiered increments—e.g., +2 instances if CPU > 70% across several periods, or larger increments above 85%. Ideal when you want explicit tiered responses, provided cooldowns, warmups, and anti-flapping hysteresis are tuned.

### 8.3. Scheduled Scaling

For reliable time-based traffic—such as a daily 20:00 flash sale—schedule min/desired capacity increases **ahead of start time** so backends are warm before users arrive. Scale back down on schedule afterward if load patterns permit.

### 8.4. Predictive Scaling

AWS offers predictive scaling using historical load patterns under supported conditions to pre-provision capacity ahead of upcoming peaks. Ensure clean historical data and compare forecasts against actual traffic; never assume models predict unprecedented campaigns accurately.

### 8.5. Never Use Scale-Out to Cure Every Error

If CPU is low while latency spikes due to database table locks or exhausted connection pools, adding EC2 instances floods the DB with **even more connections**, worsening the outage. Before raising max capacity, confirm the **true bottleneck** across ALB, app, DB, queue, and storage metrics.

## 9. Sizing Capacity for Single-AZ Failure

Suppose load tests show each EC2 instance sustains **100 requests/second** within p95 latency targets, and peak demand is **300 requests/second**.

### 9.1. Normal-State Calculation Only

Theoretical minimum:

\[
N_{\text{normal}} = \left\lceil \frac{300}{100} \right\rceil = 3\ \text{instances}
\]

Yet 3 instances leave zero headroom for spikes, rolling deploys, or AZ outages. Even 4 instances split across two AZs (2 per AZ) leaves only 2 × 100 = 200 req/s if one AZ goes down—below the 300 req/s target.

### 9.2. Designing to Sustain Peak Load After Losing an AZ

To keep serving **300 requests/second** with **at least 25% headroom** after losing one AZ, each surviving AZ needs roughly:

\[
N_{\text{surviving AZ}}
= \left\lceil \frac{300 \times 1.25}{100} \right\rceil
= 4
\]

Running **4 instances/AZ** gives **8 instances total** normally. If AZ A fails, AZ B's 4 instances offer ~400 req/s theoretical capacity—safely above 300.

**This is a capacity-planning example, not a guarantee.** Instances may perform unevenly, long connections skew traffic, the database may bottleneck, or AZ failure alters cross-zone data transfer. Validate with real load and shared-resource tests.

### 9.3. How to Pick Min, Desired, and Max

Policy options:

- **Min/Desired = 8** if you must survive an instant AZ outage at peak without waiting for scale-out.
- **Max = 12** for extra burst or post-failure rebalancing headroom, within quotas and budget.
- Use **target tracking** for routine fluctuations, ensuring it never drops below your hard AZ-survival floor if required by SLOs.
- If traffic stays low most of the day, you can run a lower baseline and rely on scale-out, accepting a **temporary degradation window** while replacement EC2 instances boot during an AZ failure.

**Decision to make explicit:** "zero-downtime AZ failover" vs. "recovers within a few minutes of scaling." Those two goals yield **very different baseline capacities and bills**.

### 9.4. Little's Law and Concurrent Requests

For HTTP APIs, approximate concurrency is:

\[
\text{Concurrent requests} \approx \text{RPS}\times\text{Latency (seconds)}
\]

At 300 RPS with 0.2s average service time, concurrency averages ~60 active requests—excluding queued sockets, long polling, and uneven bursts. Measure p95/p99 latency, active connections, and app thread queues to size accurately.

## 10. Application Concerns When Scaling Across Multiple AZs

### 10.1. Never Keep Sessions Solely in One EC2's RAM

A user logs in on EC2 A, and their next request lands on EC2 B. If sessions live only in A's memory, the user gets logged out. With ASG, A can also be terminated during scale-in.

Solutions:

- Use securely verifiable stateless tokens where appropriate;
- store sessions/state in managed Redis/ElastiCache, DynamoDB, or a database;
- use stickiness only with clear justification and awareness of target-loss risks.

### 10.2. Files and Data Should Not Live Only on One EBS Volume

EBS volumes are AZ-scoped and instance stores are ephemeral. If a user uploads an image to local disk on EC2 A, EC2 B cannot read it—and replacing A can lose it.

Common architecture: store objects in **S3**, evaluate **EFS** if shared POSIX/NFS files are required, and keep relational data in **RDS/Aurora** or an HA data tier. Minimizing local state lets ASG replace EC2 safely.

### 10.3. Databases Need Their Own Availability Design

ASG can launch 10 more EC2 instances without turning a single-AZ database into Multi-AZ. Ensure:

- DB instances/clusters use Multi-AZ failover or replication aligned with RPO/RTO;
- connection pooling, retries/backoff, timeouts, and post-failover reconnect handling;
- tested backup/restore procedures;
- bounded connection pools so backend scale-out does not exhaust the DB.

### 10.4. Long Jobs and Queues

APIs should return fast whenever possible; offload emails, PDF generation, or image resizing to **Amazon SQS** processed by ECS/EC2/Lambda workers. If workers run in an ASG, scale on **queue backlog per instance** and processing time rather than ALB RPS. Design retries, DLQs, and idempotency so instance replacement neither drops nor duplicates work.

### 10.5. Concurrent Deployments Across Multiple AZs

Rolling deployments or instance refreshes run mixed versions concurrently inside the ASG. If each app version assumes an incompatible DB schema, serving mixed traffic breaks requests even while health checks pass. Use backward-compatible schemas/APIs, readiness probes, graceful draining, and controlled rollouts/canaries.

## 11. Console Walkthrough: Configuring ALB + EC2 Auto Scaling

> **Lab environment:** Use a dedicated VPC and two authorized AZs. IDs/names below are illustrative—never run verbatim in production. Creating EC2, ALB, NAT, logging, and RDS incurs charges; set an AWS Budget upfront and tear down lab resources afterward.

### Step 1 — Prepare VPC, Subnets, and Security Groups

Assuming Region `ap-southeast-1`:

| Zone | Subnet | Role |
| --- | --- | --- |
| AZ A | `public-a` | Internet-facing ALB node |
| AZ B | `public-b` | Internet-facing ALB node |
| AZ A | `private-app-a` | EC2 instances in ASG |
| AZ B | `private-app-b` | EC2 instances in ASG |

- Public subnets have routes to an Internet Gateway.
- Private subnets accept no direct Internet inbound traffic.
- `sg-alb`: inbound HTTPS/443 from permitted clients; outbound TCP/8080 to backends.
- `sg-app`: inbound TCP/8080 **from `sg-alb`**; outbound only to required resources.
- EC2 uses an IAM instance profile to read configs/ship logs—never embed access keys in user data.

If user data downloads packages over the Internet, private subnets need an **outbound path** (NAT / VPC endpoints or pre-baked AMIs). An EC2 instance whose bootstrap fails due to missing networking still shows `running`.

### Step 2 — Create the Launch Template

Use an AMI/test app listening on HTTP **8080** with a **`/health/ready`** endpoint returning 200 when ready.

In EC2 Console → **Launch Templates**, create the template specifying instance type/AMI, backend SG, IAM role, encrypted EBS root, and metadata options (IMDSv2).

**Pre-validate:** Launch one temporary lab EC2 instance from the template and test `curl http://localhost:8080/health/ready` plus logs. Never build an ASG first and debug broken bootstrapping across a fleet.

### Step 3 — Create the Target Group

In EC2/ELB Console → **Target Groups**:

- Target type **Instances**;
- matching VPC, protocol **HTTP**, port **8080**;
- health check path `/health/ready`, matcher `200`;
- interval, timeout, and thresholds tuned to real boot/response times.

With an ASG, **let the ASG manage target registration**. Avoid manually maintaining target lists once the ASG owns lifecycle management.

### Step 4 — Create the ALB

Under **Load Balancers**:

- Type = **Application Load Balancer**.
- Scheme = **internet-facing** (or internal for VPC/on-prem only).
- Select **at least two public subnets** in distinct AZs.
- Attach `sg-alb`.
- Listener **HTTPS/443** with matching ACM certificate; default action forwarding to the new target group.
- Optional per app: HTTP/80 redirecting to HTTPS, WAF, access logs, and listener routing rules.

### Step 5 — Create the ASG and Attach the Target Group

Under **Auto Scaling Groups**:

- Select the launch template;
- choose **private-app-a** and **private-app-b**;
- set `MinSize=2`, `DesiredCapacity=2`, `MaxSize=6` for initial lab testing;
- attach the **target group ARN**;
- enable **ELB health checks** and a grace period long enough for bootstrapping;
- configure default instance warmup / termination protection as intended;
- attach tags and scaling policies.

Once created, verify EC2 instances appear in **both AZs**, targets move from `initial` to `healthy`, and traffic flows through the ALB.

### Step 6 — Create a Scaling Policy

Lab example: **target tracking `ASGAverageCPUUtilization` = 55%**. 55% is not a universal rule; if the app is I/O- or DB-bound, CPU will not reflect load accurately. Switch to `ALBRequestCountPerTarget` after profiling if appropriate.

### Step 7 — Controlled Testing

- Call `https://<alb-dns>/health/ready` from a lab client; record results and latency.
- Generate controlled load within authorized limits; watch metrics and instance count rise.
- Make one lab instance unhealthy or trigger replacement in a controlled test to verify ALB stops routing to it and ASG replaces it when ELB health checks are enabled.
- Test load drop / scale-in, deregistration, and in-flight requests.
- Drill a single-AZ failure using an approved method to confirm surviving capacity/SLOs—never attempt to disrupt real AWS infrastructure.

**Expected outcome:** understand health checks, instance counts, scale-out latency, and degraded-mode serving rather than merely seeing a "green" dashboard.

## 12. AWS CLI: Inspecting Config and Safe Lab Mutations

Examples below use AWS CLI with `--profile lab`. Substitute real lab names, ARNs, IDs, and Regions before running. Never copy commands into production without review.

### 12.1. Read Identity, ALB, and Target Groups

~~~bash
aws sts get-caller-identity --profile lab

aws elbv2 describe-load-balancers \
  --names shop-alb \
  --region ap-southeast-1 --profile lab

aws elbv2 describe-target-groups \
  --names shop-web-tg \
  --region ap-southeast-1 --profile lab
~~~

Check `Scheme`, `Type`, ALB subnets/AZs, target type/protocol/port, and health check configuration.

### 12.2. Inspect Specific Target Health

~~~bash
aws elbv2 describe-target-health \
  --target-group-arn arn:aws:elasticloadbalancing:ap-southeast-1:111122223333:targetgroup/shop-web-tg/0123456789abcdef \
  --region ap-southeast-1 --profile lab
~~~

Output includes target ID, port, health state, reason, and description when applicable. For example, if a target is `unhealthy` due to timeout, verify the health path, SG, listening port, and endpoint response speed.

### 12.3. Inspect Auto Scaling Group, Scaling Policies, and Activities

~~~bash
aws autoscaling describe-auto-scaling-groups \
  --auto-scaling-group-names shop-web-asg \
  --region ap-southeast-1 --profile lab

aws autoscaling describe-policies \
  --auto-scaling-group-name shop-web-asg \
  --region ap-southeast-1 --profile lab

aws autoscaling describe-scaling-activities \
  --auto-scaling-group-name shop-web-asg \
  --max-items 20 \
  --region ap-southeast-1 --profile lab
~~~

Inspect `MinSize`, `MaxSize`, `DesiredCapacity`, `VPCZoneIdentifier`, `TargetGroupARNs`, `HealthCheckType`, `HealthCheckGracePeriod`, `Instances[].LifecycleState`, and scaling activity statuses. This quickly separates **"ASG failed to launch EC2"** from **"EC2 launched yet target is unhealthy."**

### 12.4. Attach a Target Group to an ASG (Only If Missing in Lab)

~~~bash
aws autoscaling attach-load-balancer-target-groups \
  --auto-scaling-group-name shop-web-asg \
  --target-group-arns arn:aws:elasticloadbalancing:ap-southeast-1:111122223333:targetgroup/shop-web-tg/0123456789abcdef \
  --region ap-southeast-1 --profile lab
~~~

Verify attachment, target registration, and target health afterward. **Never accidentally attach** a target group from another environment or divert production traffic outside change control.

### 12.5. Enable ELB Health Checks and Set Grace Period (Lab Only)

~~~bash
aws autoscaling update-auto-scaling-group \
  --auto-scaling-group-name shop-web-asg \
  --health-check-type ELB \
  --health-check-grace-period 180 \
  --region ap-southeast-1 --profile lab
~~~

**180 seconds is illustrative**; measure time from `InService` until readiness stabilizes, factoring in health thresholds and bootstrap. Too long delays replacing broken hosts; too short replaces healthy instances mid-boot.

### 12.6. Set CPU Target Tracking (Lab Only)

On an ASG with active metrics and proper permissions:

~~~bash
aws autoscaling put-scaling-policy \
  --auto-scaling-group-name shop-web-asg \
  --policy-name cpu-target-55 \
  --policy-type TargetTrackingScaling \
  --target-tracking-configuration '{"PredefinedMetricSpecification":{"PredefinedMetricType":"ASGAverageCPUUtilization"},"TargetValue":55.0}' \
  --region ap-southeast-1 --profile lab
~~~

This command uses **Bash shell** JSON quoting. On Windows PowerShell, quoting differs; put the JSON in a file and pass `--target-tracking-configuration file://cpu-target.json` to avoid escaping issues.

For **`ALBRequestCountPerTarget`**, supply the exact `ResourceLabel` combining the ALB and target group **full names** in AWS's required format. Never assemble ARNs by guesswork—fetch the full names from the API/Console and check documentation.

### 12.7. Inspect AZ Distribution Mapping

~~~bash
aws ec2 describe-subnets \
  --subnet-ids subnet-0123456789abcdef0 subnet-0fedcba9876543210 \
  --query 'Subnets[].{SubnetId:SubnetId,AZ:AvailabilityZone,AZId:AvailabilityZoneId,VpcId:VpcId}' \
  --region ap-southeast-1 --profile lab
~~~

Across multiple AWS accounts, **AZ names like `ap-southeast-1a` do not necessarily map to the same physical AZ across accounts**; to align physical fault domains, compare **`AvailabilityZoneId`**.

## 13. Effective Monitoring: ALB, ASG, and Application

### 13.1. Key Metrics to Track

| Group | CloudWatch Metric or Signal | Meaning / Alerting |
| --- | --- | --- |
| **ALB** | `RequestCount` | Requests passing through ALB; tracks traffic trends |
| **ALB target group** | `HealthyHostCount`, `UnHealthyHostCount` | Ready backend distribution; alert when healthy drops low or hits 0 |
| **ALB** | `TargetResponseTime` | Backend latency; track p95/p99 where available |
| **ALB** | `HTTPCode_ELB_5XX_Count`, `HTTPCode_Target_5XX_Count` | Separates ALB-generated errors from backend-returned errors |
| **ALB** | `TargetConnectionErrorCount` | Failures establishing connections from ALB to targets |
| **ALB** | `RequestCountPerTarget` | Average load per target; supports target tracking |
| **ASG** | `GroupDesiredCapacity`, `GroupInServiceInstances`, `GroupPendingInstances` | Target vs. active capacity; requires enabling ASG group metrics collection |
| **EC2** | `CPUUtilization`, status checks, network, EBS metrics | Distinguishes CPU, I/O, host failures, and bandwidth saturation |
| **Application** | p95/p99 latency, errors, queue depth, DB pool, throughput | Tracks real user experience and business bottlenecks |

ASG CloudWatch metrics require enabling **group metrics collection**; never assume every metric is emitted at your desired granularity and retention automatically.

### 13.2. Essential Alarms

- **Low `HealthyHostCount`** relative to redundancy floor, especially if healthy targets hit 0.
- **`ALB TargetResponseTime` p95/p99** breaching SLO across multiple periods.
- **`5xx` / `TargetConnectionError`** spikes coinciding with scaling events or deploys.
- **`ASG DesiredCapacity != InServiceInstances`** persisting abnormally or failed scaling activities.
- **ASG near `MaxSize`** while CPU/RPS/queue keeps climbing.
- **DB connections/CPU** or queue lag showing backend scale-out is pressuring downstream tiers.
- **EC2/ALB/NAT costs** trending abnormally against budget.

Ensure **application logs, ALB access logs** (when needed for audits/triage), and **CloudTrail** (tracking changes to SGs, routes, launch templates, and scaling policies) are active. Keep secrets and unnecessary PII out of logs and set proper retention.

### 13.3. "Scaled Out" Is Not an SLO

An ASG may scale from 2 to 6 EC2 instances while customers still see failures because:

- half the targets are not healthy yet;
- the database ran out of connections;
- the app routes traffic into a failing dependency;
- a TLS certificate expired;
- local state disappeared during instance replacement.

Therefore, set **user-centric SLOs** (availability, p95 latency, error rate) and use ASG/ALB metrics to diagnose root causes.

## 14. Common Failures and Diagnostics

| Symptom | Common Causes | Ordered Checks |
| --- | --- | --- |
| **ALB returns 503** | No eligible/registered targets, unusable target group, or listener route error | Listener/default action → target groups → registered targets → health |
| **ALB returns 502** | Target closed connection, protocol/backend TLS mismatch, or invalid response | Target app logs, listener/target protocols, keepalive/timeouts |
| **ALB returns 504** | Timeout connecting to or awaiting response from backend | Backend latency, SGs/NACLs, overload, DB, timeout settings |
| **EC2 running, yet target unhealthy** | Wrong health path, app not listening, SG blocks port, or matcher mismatch | `describe-target-health`, local `curl`, app SG from ALB SG |
| **ASG loops launching/terminating EC2** | ELB grace period too short, broken bootstrap, bad AMI, overly strict readiness | ASG activities, user data/cloud-init, app logs, health thresholds |
| **ASG won't scale despite heavy load** | No policy, flat metric, hit `MaxSize`, missing CloudWatch data, or failed activities | Scaling policies, alarms, desired/max, group metrics/activities |
| **ASG desired rises, yet `InService` stays flat** | EC2/Spot capacity shortage, quota, bad launch template, or exhausted subnet IPs | Scaling activities, EC2 launch errors, free subnet IPs, quotas |
| **One AZ has zero traffic or backends** | ASG subnet list omits AZ, failed placement/health, or TG cross-zone disabled | ALB enabled AZs, ASG `VPCZoneIdentifier`, TG cross-zone, target AZs |
| **Scale-in drops in-flight requests** | Short deregistration delay, missing graceful shutdown, or stateful jobs | TG attributes, lifecycle hooks, application shutdown |
| **Adding instances does not cut latency** | DB, storage, cache, or queue is the bottleneck | DB metrics, connection pools, CPU/I/O, app traces, request patterns |
| **Users get logged out on scale/failure** | In-memory/local-disk sessions; stickiness insufficient | Session storage, tokens, shared state, target lifetime |
| **Errors appear only on AZ shift** | Mismatched SGs/NACLs/routes, lack of capacity in AZ B, single-AZ dependency | Compare subnets/AZs, health, endpoint routes, and failover |
| **Public ALB unreachable** | Missing IGW route / public subnet config, listener SG, DNS/TLS cert | Subnets/IGW, ALB SG, listener 443, ACM, DNS |
| **Sudden cost spike** | Raised min/desired/max, LB traffic/LCUs, cross-AZ NAT, log retention | Cost Explorer by tags, scaling history, pricing, actual load |

### Short Triage Workflow

~~~text
1. Confirm FQDN, ALB, listener, target group, ASG, Region, and failure timestamp.
2. Check client → ALB (DNS, HTTPS/TLS, HTTP status).
3. Check target group (HealthyHostCount, per-target reasons, backend app logs).
4. Check ALB → backend (SGs, ports, VPC routes, health path, NACLs).
5. Check ASG (Desired, InService, Pending, activities, launch template, AZs).
6. Check CloudWatch CPU/RPS/latency/errors, DB/queues, and scaling policies.
7. Fix one clear cause, test from a real client, and compare before/after metrics.
8. Verify scale-in, single-AZ failure, and unauthorized access remain blocked.
~~~

**When suspecting route/security blocks:** use **VPC Reachability Analyzer** to statically evaluate AWS path config alongside **VPC Flow Logs** and live connection tests. Reachability Analyzer is static analysis—it does not prove listeners, TLS, or apps are healthy.

## 15. Security and Deployment Governance

**IAM, VPC, and TLS** must align with scaling:

1. **Instance profiles/roles:** instances launched from templates should use least-privilege IAM roles to access S3, Secrets Manager, CloudWatch, or needed services—never bake static access keys into AMIs or user data.
2. **Security groups:** backends accept the app port only from the ALB SG; databases accept connections only from the app SG. Never open SSH/22 to the entire Internet for debugging; prefer **AWS Systems Manager Session Manager** where supported.
3. **Private subnets:** keep public IPs off EC2 backends unless strictly required. Design egress cleanly via NAT or VPC endpoints.
4. **HTTPS/WAF:** enforce HTTPS/ACM on public ALBs; add AWS WAF, rate limiting, or CloudFront based on risk and needs.
5. **Data encryption:** encrypt EBS, S3, and RDS with KMS, plus TLS to the DB where needed; data access controls must never rely solely on traffic passing through an ALB.
6. **Infrastructure as Code:** manage ALBs, target groups, launch templates, ASGs, SGs, policies, and alarms via CloudFormation, CDK, Terraform, or your team's IaC standard.
7. **Auditing:** enable CloudTrail and audit changes to launch template versions, scaling policies, listener rules, target groups, and SGs; separate admin permissions from runtime permissions.

A public ALB should expose **only the public paths/ports intended for external users**. Internal operational endpoints, metrics, or admin dashboards belong behind proper auth/network boundaries so they are never accidentally exposed by a listener rule.

## 16. Cost: Multi-AZ and Auto Scaling Need a Budget

**Auto Scaling does not automatically save money.** It maintains or adjusts capacity per policy; if `MinSize` is too high, scale-in is disabled, or the tracked metric is poorly chosen, the fleet can run oversized all month.

### Cost Components to Account For

| Cost Line Item | Why It Matters |
| --- | --- |
| **EC2 instances** | Running hours, instance type, On-Demand / Spot / Savings Plans where appropriate |
| **EBS volumes / snapshots** | Every instance carries root/data volumes; snapshots and log retention accumulate |
| **ALB / NLB** | Hourly uptime charges plus capacity/processing units per load balancer type |
| **Network transfer** | Internet egress, cross-AZ/cross-Region transfer, and endpoint/NAT data processing |
| **NAT Gateways / VPC endpoints** | Hourly and per-GB charges; often overlooked across multiple AZs |
| **CloudWatch / logs / tracing** | Metrics, custom metrics, log ingestion/storage, and alarms |
| **RDS / ElastiCache / SQS** | Backend scale-out increases downstream resource demand and requests |
| **Single-AZ failure headroom** | Higher baseline required if SLOs must hold even before scale-out reacts |

**Cross-zone note:** ALB and NLB handle cross-zone data transfer pricing differently—enabling cross-zone on NLB can incur cross-AZ data transfer fees under current pricing rules. Always verify **AWS ELB pricing** by type and Region rather than applying a single blanket rule.

### Data-Driven Optimization Strategies

- Ground **min/desired/max** in SLOs and AZ-failure tolerance.
- Benchmark requests/instance, CPU, p95 latency, and bootstrap times to avoid over-provisioning.
- Choose instance types, purchase models, and Spot based on interruption tolerance; critical web baselines require reliable capacity supply.
- Combine scheduled scaling for predictable cycles with dynamic scaling for fluctuations.
- Optimize health checks, warmups, and graceful shutdown so EC2 instances spend minimal billed time unready.
- Use **AWS Budgets**, **Cost Explorer**, `service`/`environment`/`owner` tags, and anomaly alerts.

**Never cut AZ count to save money if the application requires AZ-level fault tolerance.** Weigh savings against RTO/RPO and outage revenue loss.

## 17. Three Reference Architecture Scenarios

### A. Small Website with Steady Traffic and Moderate Uptime Needs

**Assumed requirements:** internal informational site, low traffic, small ops team, scheduled maintenance downtime acceptable.

**Assessment:** ALB + ASG across two AZs with small min, gp3 volumes, state externalized off EC2, and basic backups. If strict HA is not required by policy, simpler layouts may be chosen after cost review—just never claim single-AZ is HA.

### B. E-Commerce API with Sudden Campaign Traffic Spikes

**Assumed requirements:** HTTPS/REST, peaks several times normal volume, downtime loses orders, database requires ACID transactions.

**Assessment:**

- Public ALB across at least two AZs with HTTPS/ACM and WAF as needed;
- ASG in multi-AZ private subnets using target tracking on **`ALBRequestCountPerTarget`** or load-tested CPU, paired with scheduled scaling before campaigns;
- RDS Multi-AZ, S3 for images/invoices, SQS for background tasks; stateless app with bounded DB pools;
- alarms for `HealthyHostCount`, error rate, p95 latency, ASG capacity, and DB connections;
- load tests, scaling drills, AZ-loss drills, and data restore tests.

**Key factor:** instances needed to hold SLOs through a single-AZ outage; boot/warmup times may be too slow if you wait for traffic spikes before scaling.

### C. TCP System Requiring Stable IP Addresses

**Assumed requirements:** clients use a custom TCP protocol and external firewalls must allowlist the load balancer's IP addresses.

**Assessment:** NLB across suitable AZs, TCP/TLS listeners and target groups, paired with an EC2 ASG. Check **cross-zone** settings (NLB defaults to off at the LB level), resilience if one AZ loses healthy targets, connection-level load distribution, and graceful shutdown. Test real TCP flows rather than configuring an incompatible HTTP health check if the app does not expose one.

## 18. Hands-On Exercises and Self-Check Questions

### Exercise 1 — Designing a Dual-AZ Architecture

**Prompt:** An API serves users at `https://api.example.com` with a Java backend on EC2 port 8080, PostgreSQL, and image storage.

Diagram:

- Route 53 / public ALB with HTTPS listener / ACM;
- public subnets in AZ A/B and private backend subnets in AZ A/B;
- target group with `/health/ready` health check;
- ASG with launch template, min/desired/max, and health-check grace period;
- RDS Multi-AZ, S3, and SQS for asynchronous background tasks;
- CloudWatch alarms, IAM roles, security groups, and AWS Budgets.

Explain why RDS Multi-AZ and externalized storage matter even with many EC2 instances.

### Exercise 2 — Sizing Capacity for AZ Failure

An app behind ALB sustains **75 RPS/EC2** within p95 latency targets. Peak traffic is **225 RPS**, and after losing one AZ you still want **at least 20% spare headroom**.

1. Calculate minimum surviving instances needed in the remaining AZ: `ceil(225 × 1.20 / 75) = 4`.
2. Across two AZs for **immediate** failover capacity, provision at least **4 instances/AZ**, i.e., 8 instances normally.
3. Propose sensible min/desired/max values and state cost trade-offs.
4. If a short degradation window while scaling out is acceptable, how could you lower the baseline and what must you test?

### Exercise 3 — Instance Fails, Yet ASG Does Not Replace It

The ALB target group marks an instance `unhealthy` because its health endpoint returns HTTP 500. EC2 remains `running` and ASG keeps the instance indefinitely.

**Task:** check ASG `HealthCheckType`, target group attachment, grace period, target health reasons, app logs, and scaling activities. Propose the minimal fix so ASG replaces instances marked unhealthy by ALB.

### Exercise 4 — Scaling Out, Yet Responses Get Slower

ASG scales from 2 to 8 instances after CPU crosses 70%, yet p95 latency climbs from 200 ms to 2 seconds and DB connections hit their ceiling.

**Task:** separate CPU/backend capacity issues from DB bottlenecks, diagram monitoring flows, pick alert metrics, and propose fixes like connection pooling, caching, queues, DB tuning, or query optimization. Explain why launching even more EC2 instances can overload the DB worse.

### Exercise 5 — Safe Scale-In

A target runs a 90-second report export; ASG scales in and terminates the instance after deregistration, cutting off the request.

**Task:** evaluate `deregistration_delay.timeout_seconds`, graceful shutdown, ASG lifecycle hooks, client/ALB timeout limits, and offloading long tasks to SQS / Step Functions. Verify requests support retries/idempotency during instance replacement.

### Self-Check Questions

1. **Do ALB and ASG have the same role?** No. ALB selects targets and routes traffic; ASG manages capacity and EC2 lifecycles.
2. **Are two instances in the same AZ considered Multi-AZ?** No. Distribute across at least two AZs and eliminate single-AZ shared dependencies.
3. **Does EC2 `running` mean the ALB target is `healthy`?** No. Health checks require the app, port, and path to respond properly.
4. **Is ALB cross-zone always enabled at every configuration level?** Always enabled at the load balancer level; target groups can override where supported.
5. **Does enabling a target group health check make ASG automatically replace every unhealthy instance?** Not by default; you must set ASG `HealthCheckType=ELB` along with target group attachment and grace period.
6. **Does ASG scaling out automatically increase database capacity?** No. Databases must be sized, scaled, and made HA independently.
7. **Should you track CPU or requests/target?** Pick the metric that reflects your workload and SLOs based on benchmarks—no single metric fits all apps.
8. **If one AZ fails, does ASG guarantee immediate full peak capacity?** No. You need spare headroom in surviving AZs, proper health/routing, and tested failure drills.

## 19. Pre-Production Deployment Checklist

- [ ] Defined SLOs for availability, p95/p99 latency, RTO/RPO, and normal/peak traffic.
- [ ] Selected **ALB/NLB/GWLB** by protocol/capabilities rather than guesswork.
- [ ] Internet-facing ALB has HTTPS listener/ACM, public subnets in **at least two AZs**, and tight SGs.
- [ ] Backend ASG spans multi-AZ private subnets with tested launch template/AMI/IAM role startup.
- [ ] Target group has matching **instance/ip** type, port, health path, matcher, thresholds, and cross-zone attributes.
- [ ] ASG attaches the **right target group ARN** with verified `MinSize`, `DesiredCapacity`, `MaxSize`, and subnets.
- [ ] Enabled ELB health checks on the ASG where unhealthy replacement is desired, with a measured grace period.
- [ ] Aligned warmup, scale-in/deregistration delay, and graceful shutdown to measured timings.
- [ ] Scaling policy tracks a metric aligned with load and SLOs; tested scale-out/in and capacity shortages.
- [ ] Surviving AZs hold required outage capacity; drilled controlled single-instance and single-AZ failures.
- [ ] Application is stateless; sessions, files, and jobs persist in shared, recoverable stores.
- [ ] Databases, caches, S3/EFS, SQS, and external dependencies have appropriate HA and backup/restore plans.
- [ ] Enforced least-privilege IAM, app SGs accepting only ALB SG, KMS/TLS, audit logs, and secure admin access.
- [ ] Active alarms for `HealthyHostCount`, latency, 5xx, ASG desired/in-service, DB connections, and cost.
- [ ] IaC, runbooks, rollback procedures, DNS/route validation, and deployment change processes in place.
- [ ] Budgeted EC2, EBS, ALB/NLB, NAT/endpoints, network transfer, monitoring, and AZ headroom costs.

## 20. Summary

**Load balancers route connections to healthy targets; Auto Scaling manages backend counts; Multi-AZ isolates fault domains.** All three must be **designed and tested as a single cohesive system**: listener → target group → health check → ASG/launch template → subnets/AZs → database/storage → monitoring.

For HTTP(S) websites and APIs, the standard starting architecture is an **ALB across at least two AZs**, a **multi-AZ private-subnet EC2 ASG**, load-correlated scaling policies, and **stateless backends**. Yet reliability holds only with accurate readiness probes, grace periods, graceful shutdowns, surviving-AZ headroom, and proper protection for data, queues, and databases. The ultimate goal is a **secure, consistently responsive, resilient, and cost-measurable application**—not merely EC2 counts scaling up and down.

### Official AWS Documentation for Reference During Deployment

- [Elastic Load Balancing overview](https://docs.aws.amazon.com/elasticloadbalancing/latest/userguide/what-is-load-balancing.html)
- [Application Load Balancers](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/application-load-balancers.html)
- [ALB target group attributes, cross-zone behavior](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/edit-target-group-attributes.html)
- [ALB target group health checks](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/target-group-health-checks.html)
- [Network Load Balancer cross-zone attributes](https://docs.aws.amazon.com/elasticloadbalancing/latest/network/edit-load-balancer-attributes.html)
- [Amazon EC2 Auto Scaling overview](https://docs.aws.amazon.com/autoscaling/ec2/userguide/what-is-amazon-ec2-auto-scaling.html)
- [Attach a load balancer to an Auto Scaling group](https://docs.aws.amazon.com/autoscaling/ec2/userguide/attach-load-balancer-asg.html)
- [Auto Scaling health check grace period](https://docs.aws.amazon.com/autoscaling/ec2/userguide/health-check-grace-period.html)
- [Target tracking scaling policies](https://docs.aws.amazon.com/autoscaling/ec2/userguide/as-scaling-target-tracking.html)
- [Scaling policies and instance warmup](https://docs.aws.amazon.com/autoscaling/ec2/userguide/ec2-auto-scaling-scaling-cooldowns.html)
- [Monitor Application Load Balancers with CloudWatch](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-cloudwatch-metrics.html)
- [AWS Elastic Load Balancing pricing](https://aws.amazon.com/elasticloadbalancing/pricing/)

> **Deployment note:** Feature support, defaults, metrics, pricing, and Console UI evolve over time. Always verify current AWS documentation, account quotas, and actual Region behavior before applying changes to production workloads.
