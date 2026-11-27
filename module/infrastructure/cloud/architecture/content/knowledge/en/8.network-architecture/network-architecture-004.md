# Hub-and-Spoke, Centralized, and Distributed Networking

When a cloud application grows from a few services into multiple environments, development teams, accounts, or projects, the network is no longer just a simple set of subnets. Architects must decide **which services may connect to each other, where traffic traverses, where security policies are enforced, and who owns operating those connections**. That decision directly impacts performance, reliability, security, scalability, and the cloud bill.

In the **CLOUD_ARCHITECTURE** module, this lesson in the **Network Architecture** chapter focuses on three related yet distinct ideas: **hub-and-spoke** is a connectivity topology, **centralized networking** is how network functions and governance are consolidated, and **distributed networking** is placing connectivity, controls, and ownership close to each workload. No single diagram is optimal for every system. Choices must be backed by evidence from business requirements, data flows, security policies, actual load, and operational capability under the Well-Architected mindset.

## 1. Three Concepts Often Conflated

| Concept | Essence | Example | What not to infer |
| --- | --- | --- | --- |
| **Hub-and-spoke** | Connectivity topology: spoke networks connect to a shared hub | Each application has a VPC/VNet connected to a transit hub | Does not mean every packet must pass through a hub firewall |
| **Centralized networking** | Functions/rules managed at a central point or by a shared team | Egress, DNS forwarding, firewalls, and hybrid connectivity managed by a platform team | Does not require putting every workload in one subnet or account |
| **Distributed networking** | Connectivity, policy enforcement points, or operations distributed across multiple networks and areas | Each workload manages its own ingress/egress, private endpoints, and local policies | Does not mean lacking governance, lacking standards, or needing a full mesh |

Two key axes to separate are **connectivity topology** and **policy enforcement location**. A hub-and-spoke system can use the hub for inter-network routing while keeping firewalls per workload. Conversely, a network with many direct point-to-point links can still be governed by centralized security policies and shared automation infrastructure.

### Architectural Goals to Clarify

1. **Segmentation:** Do sensitive data, production, and development environments need separate boundaries?
2. **Connectivity:** Which workloads must talk directly; which services must corporate networks (on-premises) or branch offices reach?
3. **Inspection and controls:** Are packet inspection, audit logging, NAT, or centralized egress policies mandatory?
4. **Latency and bandwidth:** Are there high-volume traffic paths across services, availability zones (AZs), or regions?
5. **Reliability:** Losing which hub, gateway, or hybrid link would disrupt which business journeys?
6. **Cost and accountability:** How are data transfer, gateway, traffic inspection, logging, and operational costs allocated?

Before drawing hubs or peering links, build a **communication matrix**: source, destination, port/protocol, frequency, data handled, security requirements, latency, and owner. This serves as the input to routing and firewalls; a diagram with mere lines cannot express policy.

## 2. Classifying Traffic Flows to Choose Paths

Different flows carry different requirements:

| Flow | Characteristics | Decisions required |
| --- | --- | --- |
| **North–south ingress** | From Internet, partners, or users into the application | Where is the public endpoint? Which CDN/WAF/load balancer protects it? |
| **North–south egress** | From the application out to the Internet or SaaS | Are static source IPs, NAT, domain filtering, logging, or a central proxy needed? |
| **East–west** | Between services, subnets, spokes, or clusters | Direct routing, via hub, or via private service endpoint? |
| **Hybrid** | Between cloud and corporate network or datacenter | VPN/dedicated circuit, BGP, DNS resolution, and redundant paths? |
| **Cross-region** | Data replication, API calls, or DR across regions | Latency, inter-region transfer fees, consistency, data residency requirements? |
| **Management/control** | CI/CD, monitoring, DNS, secrets, management APIs | Who has access, auditing, and control-plane resilience? |

**Ingress is not egress.** An Internet-facing load balancer bringing users to an API does not replace a NAT/proxy solution for processes in private subnets calling external APIs. Nor should all traffic between two workloads in the same VPC/VNet be forced to hairpin through a hub if they already have an appropriately controlled internal path.

A useful flow-discovery workflow extracts flows from business diagrams and tracing, cross-checks them against VPC/VNet flow logs or network observability tools, and validates which connections are genuinely needed. Traffic without a business justification should remain **deny-by-default** under the active policy.

## 3. Building Blocks of Cloud Network Architecture

| Component | Role | Key verification points |
| --- | --- | --- |
| **VPC/VNet** | Logical network space for workloads | CIDRs, subnets, routes, DNS, environment/account isolation |
| **Subnets and route tables** | Determine forwarding paths by destination address | Explicit targets, return paths, local routes, route precedence |
| **Peering** | Direct connection between networks under provider rules | Do not assume automatic transit to a third network |
| **Transit hub/router/gateway** | Connects multiple networks and routes via a shared system | Route propagation, segmentation, throughput, and quotas |
| **Firewall/inspection appliance** | Inspects traffic per network/application policies | Stateful flows, return paths, HA, logs, processing limits |
| **NAT/proxy** | Controls source/destination for outbound flows | Source IPs, connection counts, port limits, SNAT, and cost |
| **DNS resolver/forwarder** | Resolves private/public service names and hybrid names | Split-horizon, caching, conditional forwarding, redundancy |
| **Private endpoint/service connectivity** | Accesses managed services over private paths per platform capabilities | DNS names, endpoint access policies, actual data path |
| **VPN/dedicated connectivity** | Links cloud to external networks | BGP/static routes, bandwidth, encryption, backup links |
| **WAF/CDN/load balancer** | Distributes and protects inbound application flows | TLS, Layer 7, health checks, client source IP, failover |
| **Network policy/security group/ACL** | Enforces connection allowlists at specific boundaries | Least privilege, outbound rules, connection statefulness |

Cloud platforms differ in resource names and limits. When implementing, check the exact **peering transit behavior, route selection rules, automatic route propagation, connection limits, and billing model** of your chosen provider. A conceptual diagram cannot substitute for route table configuration and path testing.

### Routing Is Different from Security

**Routes tell packets where they can go; policies decide whether packets are allowed to go.** Having a route between two spokes does not mean they are permitted to call every port. Conversely, if a firewall allows a connection but the return route is missing, traffic still fails.

Segmentation is usually multi-layered: separating accounts/projects and networks, route domains, firewalls, security groups/network policies, service authentication, authorization, and encryption. Avoid treating a hub firewall as the sole line of defense for sensitive data.

## 4. How Does Hub-and-Spoke Work?

A **hub** centralizes shared connectivity, while **spokes** hold workloads or environments requiring isolation. Depending on the platform, the hub may be a shared VPC/VNet, a managed transit service, or a combination of transit and network-services subnets.

~~~mermaid
flowchart TB
    INTERNET["Internet / SaaS"]
    OFFICE["Corporate network"]
    subgraph HUB["Network hub / platform account"]
        TRANSIT["Transit routing"]
        INSPECT["Firewall / inspection"]
        EGRESS["NAT / egress proxy"]
        DNS["Private DNS / resolver"]
        HYBRID["VPN / dedicated connectivity"]
    end
    subgraph SPK1["Spoke A — Catalog"]
        A["API and database"]
    end
    subgraph SPK2["Spoke B — Booking"]
        B["API and database"]
    end
    subgraph SPK3["Spoke C — Analytics"]
        C["Data workloads"]
    end
    A <--> TRANSIT
    B <--> TRANSIT
    C <--> TRANSIT
    TRANSIT <--> INSPECT
    INSPECT <--> EGRESS
    EGRESS <--> INTERNET
    TRANSIT <--> HYBRID
    HYBRID <--> OFFICE
    DNS --- TRANSIT
~~~

This diagram is logical: lines from spokes to transit represent **connectivity capability**, not an implication that every flow must go through inspection or that DNS queries always follow the exact data-packet path. Designers must specify which traffic classes route through the firewall, which go directly, and which are blocked.

### What Functions Does a Hub Commonly Provide?

- **Connectivity:** A single place consolidating spoke links, VPNs, and corporate network circuits.
- **Egress control:** NAT, proxies, destination allowlists, and logs for workloads reaching the Internet.
- **Centralized inspection:** Where policy requires, applying firewall inspection to selected spoke-to-spoke, hybrid, or Internet flows.
- **Shared services:** DNS resolvers, service endpoints, and management/observability tooling where suitable.
- **Routing governance point:** Creating or advertising routes by policy; separating route domains so not every network can see every other network.

A hub can reduce connection counts and standardize policies, yet it also introduces **longer paths**, gateway processing charges, and wider blast radius if shared paths fail. Separate **centralized policy management** from **centralized packet processing**: policies governed in one place can still be enforced across multiple distributed firewalls/endpoints.

## 5. Flows Through a Hub: Routes, Return Paths, and Inspection

Suppose we use these illustrative private IPv4 ranges:

| Network | CIDR | Function |
| --- | --- | --- |
| Hub | 10.40.0.0/16 | Routing, firewall, DNS, egress |
| Spoke A | 10.41.0.0/16 | Catalog |
| Spoke B | 10.42.0.0/16 | Booking |
| Spoke C | 10.43.0.0/16 | Analytics |
| Corporate network | 172.20.0.0/16 | On-premises systems |

These CIDRs **do not overlap**; they are merely an address-structure example, do not show actual subnets, and cannot be applied blindly to any cloud account. When scaling, reserve room for new subnets, Kubernetes/pod networks, partner connections, and future addresses.

### 5.1. Spoke A Calls an Internal API in Spoke B

Assume policy mandates that every connection between two spokes is inspected at the firewall:

1. Catalog in Spoke A resolves Booking's private name to a private IP in Spoke B.
2. The route in Spoke A for **10.42.0.0/16** sends traffic to the transit/hub system.
3. Hub routing selects the inspection path, and the firewall enforces the **Catalog → Booking** policy on the exact protocol, port, and source/destination.
4. Once permitted, the hub forwards packets to Spoke B.
5. **Return traffic** from B to A must traverse a path that recognizes connection state or uses a mechanism supported by the firewall; if return packets take a shortcut, a stateful firewall may drop them and break the connection.

*Asymmetric routing* is a common bug with multiple AZs, multiple route tables, or multiple firewalls. A flow traversing a firewall in AZ A whose return packets pass through an un-synced firewall in AZ B can fail even when every network ACL permits it. When using stateful appliances, design flow affinity, symmetric routing, and HA according to platform mechanics.

### 5.2. Spoke Reaches the Internet via Centralized Egress

In centralized egress, the Internet route sends packets from the spoke to the hub, then through a firewall/proxy and NAT outward. Note that **NAT is not an application firewall by default**: NAT translates addresses/ports according to its mechanics; filtering by domain, URL, or content requires dedicated solutions. A static egress IP is often helpful for partner allowlists, yet can create port/connection limits if all workloads share one IP.

Do not force every destination's egress through the hub mechanically. Access to object storage, managed databases, or platform APIs can use **private endpoints** as supported by the cloud; separate routes, DNS, and policies appropriately to avoid hairpinning out toward the Internet.

### 5.3. Hybrid: Spoke to On-Premises Systems

Spokes may need a route for **172.20.0.0/16** toward the hub and then over a VPN or dedicated interconnect. On-premises needs return routes for spoke ranges and matching firewall rules. If using BGP, inspect prefix advertisements, route filtering, route precedence, and failover; misconfigured route propagation can cause **blackholes** or unintentionally leak reachability beyond intended boundaries.

### Purpose-Based Illustrative Route Table

| Routing point | Destination | Desired processing path |
| --- | --- | --- |
| Spoke A | 10.42.0.0/16 | Transit/hub, inspected when policy requires |
| Spoke A | 172.20.0.0/16 | Hub toward hybrid gateway |
| Spoke A | 0.0.0.0/0 | Hub egress if central egress is chosen |
| Hub/transit | 10.41.0.0/16 | Attachment to Spoke A |
| Hub/transit | 10.42.0.0/16 | Attachment to Spoke B |
| Hub/transit | 172.20.0.0/16 | Hybrid attachment |
| Hub egress | Internet | Firewall/proxy then NAT or appropriate public egress mechanism |

This table shows **intent**, not copy-pasteable config commands. Verify route tables per subnet/attachment, return routes, route precedence, appliance forwarding, and limits for your specific cloud service. Internal VPC/VNet ranges usually have platform-provided local routes; a default route must not override legitimate internal paths.

## 6. Centralized Networking: Benefits and Limitations

**Centralized networking** typically has a platform/network team owning routing, on-premises links, firewalls, egress, DNS forwarding, and connectivity standards across accounts/projects. Application teams deploy workloads into authorized spokes or network zones using agreed-upon policies.

Advantages:

- **Policy consistency:** Sensitive flows get uniform inspection rules and centralized audit logging.
- **Convenient hybrid management:** Instead of every VPC/VNet maintaining separate VPN links to the datacenter, the hub aggregates connections and advertises routes within permitted scopes.
- **Reuse of network services:** Shared name resolution, traffic inspection, egress IPs, or observability infrastructure can serve many spokes.
- **Templated onboarding:** The platform team provides standard workflows for CIDR registration, attachment, policy provisioning, and connectivity testing.
- **Clear division of responsibility:** App teams own service-level and local security rules; the platform team governs routing topology, external links, and guardrails.

Limitations to evaluate:

- **Concentrated failure domain:** A misconfigured shared route or firewall change can affect multiple products; the hub requires genuine HA and strict change control.
- **Bottlenecks or hairpinning:** Traffic between two co-located spokes may be forced through multiple devices, raising latency and processing fees.
- **Slow change velocity:** If every port opening waits on manual review by one team, app teams become bottlenecked on release schedules.
- **Harder cost chargeback:** Shared gateways/inspection/egress need byte- or workload-level attribution to avoid “unowned” costs.
- **Scaling limits at a single choke point:** Firewall throughput, tunnel counts, concurrent sessions, NAT ports, and route table entries have limits even when managed transit scales by design.

**Centralized governance does not mean using a single firewall instance.** A centralized design may require multiple AZs, multiple instances/appliances, synchronized state, and failover paths to eliminate single points of failure.

## 7. Distributed Networking: Controls Near Workloads and Team Autonomy

**Distributed networking** places connectivity functions or enforcement mechanisms close to where traffic originates. Each workload can manage its subnets, ingress, egress, private endpoints, network policies, local firewalls, and lifecycle within shared guardrails.

~~~mermaid
flowchart TB
    POLICY["Shared guardrails: IAM / policy / IaC / audit"]
    subgraph RA["Workload A network"]
        A["API A"]
        EA["Egress / inspection A"]
    end
    subgraph RB["Workload B network"]
        B["API B"]
        EB["Egress / inspection B"]
    end
    subgraph RC["Workload C network"]
        C["API C"]
        EC["Egress / inspection C"]
    end
    A --> EA
    B --> EB
    C --> EC
    POLICY -.-> EA
    POLICY -.-> EB
    POLICY -.-> EC
    A <-->|"Controlled private link"| B
    B <-->|"Controlled private link"| C
~~~

Note: this illustrates **distributed enforcement points**, not a recommendation to build full-mesh peering. Inter-network connectivity can use private service connectivity, regional transit, service networking, or managed options; every path still needs routes and policies.

Advantages:

- **Shorter paths for selected flows:** Avoids detouring through central firewalls/transit when workloads and policies permit direct private connectivity.
- **Smaller blast radius from shared network devices:** An egress outage in app A is less likely to impact B when they hold independent resources and policies.
- **Release autonomy:** App teams can ship policy updates alongside app changes through tested pipelines.
- **Data-tailored controls:** Sensitive services enforce granular authentication, network policies, and telemetry right at their own perimeter.

Limitations:

- **Risk of inconsistency:** If every team invents its own rules, logging, TLS configuration, or egress controls are easily missed.
- **Resource duplication:** Per-workload NATs, firewalls, gateways, and local links can raise fixed costs.
- **Harder global visibility:** Routing, logs, and incidents span many projects; centralized inventory and observability are mandatory.
- **Higher risk of overlapping networks:** Independent teams picking identical CIDRs, DNS zones, or target IPs create painful future integration work.
- **Complex cross-network management:** Point-to-point peering across many networks grows rapidly and makes permission matrices hard to maintain.

**Distributed does not mean unrestricted.** One practical pattern keeps *policy definition, identity, asset inventory, and auditing* centralized while distributing *policy enforcement and data paths*. This often yields an effective hybrid model.

## 8. Hub-and-Spoke vs. Direct Connectivity vs. Selective Hybrid

| Criterion | Hub-and-spoke with centralized control | Direct private/distributed connectivity | Selective hybrid model |
| --- | --- | --- | --- |
| Route complexity at scale | Spokes attach to hub; route domains stay cleaner | Pairwise peering grows rapidly | Keep transit for most links; allow dedicated direct paths where justified |
| East–west latency | Can rise if hairpinning through inspection | Usually shorter when co-located with direct routes | Hot paths optimized; sensitive flows inspected |
| Security | Easy to enforce uniform policy at checkpoints | Needs strong guardrails to keep teams consistent | Shared policies, enforcement tailored to data sensitivity |
| Fault blast radius | Hub or shared routes carry large blast radius | Single-network faults are more isolated, though cross-dependencies remain | Isolate critical traffic; enforce HA on shared services |
| Operations | One team owns routing/inspection; changes affect many teams | Workload teams move faster but need network/security skill | Clear split of ownership backed by automation |
| Cost | Shared gateways/inspection, with processing and transit fees | Possible duplicated appliances; direct cross-network fees | Optimize based on byte distribution and real load |
| Hybrid/on-premises | Convenient via a few centralized gateways/links | Multiple independent circuits can be expensive | Hybrid via hub; specialized high-volume flows get direct paths |

This is a **qualitative** comparison. Real performance and cost depend on transit products, attachment types, HA levels, cloud provider, AZs/regions, and where traffic is metered. Always validate against measurements and pricing for the proposed configuration.

### Avoid Defaulting to a Full Mesh by Inertia

With \(n\) networks needing pairwise direct connections, the theoretical number of links is:

\[
\frac{n(n-1)}{2}.
\]

For example, **12 networks** would require **66** pairwise connections if all peer with one another. In a basic hub-and-spoke setup, 12 spokes need 12 attachments to the hub—though internally the hub still carries route tables, segmentation, gateways, inspection, and other costs. Comparing link counts highlights administrative overhead; it **does not prove a hub is cheaper** when traffic volumes are huge.

For certain high-throughput flows, a controlled direct path may be superior—for example, compute services and a data store in the same region. Conversely, sensitive flows such as analytics accessing payment data may need to pass through an inspection point or be blocked outright depending on policy.

## 9. Security Policy: Separating Connectivity from Authorization

Hub-and-spoke only supplies topology. Security architecture must define **who may connect where, what proof verifies identity, and what data may be exchanged**.

A multi-layer control model:

1. **Account and environment partitioning:** Production, staging, development, and sensitive-data workloads live in separate boundaries; one team cannot by default alter routes/policies across everything.
2. **Network segmentation:** Route domains and firewalls curb lateral movement; routes exist only for genuinely needed connections.
3. **Source and destination filtering:** Network policies/security groups scope exact ports, protocols, and service groups; never rely solely on a hub firewall.
4. **Application identity and encryption:** Enforce mTLS/TLS, IAM, and service/workload-identity authorization instead of trusting every private IP.
5. **Egress controls:** Restrict target domains/services where possible, monitor anomalous outbound calls, keep secrets out of code, and block unnecessary Internet egress.
6. **Observability and audit:** Flow logs, firewall decision logs, DNS query logs, route/policy change trails; redact sensitive fields in logs.
7. **Release discipline:** Infrastructure as Code (IaC), peer review, policy-as-code, route testing, and drift detection.

### Access Matrix Example

| Source | Destination | Purpose | Illustrative policy |
| --- | --- | --- | --- |
| Catalog API | Booking API | Read required status info | Allow HTTPS only from authenticated workload identity |
| Analytics | Booking primary database | Direct query of transactional data | **Deny**; provide a controlled dataset/projection instead |
| Booking | Payment gateway | Submit payment orders | Egress only to approved endpoints, TLS, centrally managed secrets |
| CI/CD agent | Production workloads | Authorized deployments | Least-privilege deploy permissions, audit trail, short-lived identity |
| Internet | Database subnet | Direct connection | **Deny**; expose only required application ingress |

Do not use a shared egress NAT IP as an **authentication** mechanism between services: multiple workloads can appear behind the same IP. Authorization must still rely on application identity and security contracts.

### DNS and Private Endpoints Are Part of Network Policy

A private hostname may resolve differently inside each spoke or from on-premises; define **who owns DNS zones, which networks receive records, edit permissions, cache TTLs, and forwarding paths**. With private endpoints, reaching the private IP can depend simultaneously on private DNS, routing, and managed resource policies. If DNS returns a public IP when the app expects a private path, even correct firewall rules cannot guarantee the intended data path.

A DNS outage or shared resolver failure can sever service discovery across many workloads even while IP routing stays healthy. Build redundant resolvers, test conditional forwarding, and monitor both resolution latency and DNS failures.

## 10. Cost, Latency, and Throughput: Follow the Actual Packet Path

Longer paths can incur **transit/inspection processing fees, inter-AZ or inter-region data transfer fees, NAT charges, Internet egress fees, and shared-system ops overhead**. You cannot estimate cost from total monthly GB alone because flows cross different appliances and billing boundaries.

A cost breakdown table to maintain:

| Line item | Volume to measure | Forecasting questions |
| --- | --- | --- |
| Transit/gateway attachments | Attachment count, active hours, bytes traversing gateway | Are inbound/outbound directions or service types billed differently? |
| Firewall/inspection | Endpoint/instance count, uptime hours, bytes processed | How many checkpoints and AZs does traffic traverse? |
| NAT/proxy | Uptime hours, bytes, active connections | Is cloud service traffic also going through NAT alongside Internet traffic? |
| Inter-AZ/inter-region | Bytes across zones and source/destination locations | Are flows detouring across another AZ or between regions? |
| Internet egress | Outbound bytes by destination/region/tier | Do CDN caching or compression cut origin transfer? |
| VPN/dedicated links | Circuits, bandwidth, ports/infrastructure, transfer | Are backup links needed, and is corporate WAN a bottleneck? |
| DNS/logging | Queries, log volume, retention window | How much data and cost do flow logs and firewall logs generate? |

### Example Throughput Calculation to Verify

Suppose Catalog calls Booking at **5,000 requests/second** during peak hours; each request averages **10 KB** outbound payload and **60 KB** response (1 KB = 1,000 bytes). Looking strictly at application payload in both directions:

\[
5,000 \times (10,000+60,000)\times 8
= 2,800,000,000\ \text{bit/s}\approx2.8\ \text{Gb/s}.
\]

This is aggregate bidirectional throughput at one point on the path, **before TLS/HTTP/IP overhead, traffic bursts, retries, and replication**. If both requests and responses pass through a hub firewall, verify actual firewall bandwidth and concurrent session limits at that load. If a flow crosses two gateway/inspection services, each service may meter bytes separately; never arbitrarily double physical bandwidth or cost line items without confirming exact metering rules.

If 2.8 Gb/s occurs for only 10 minutes, cost forecasts must reflect the **time-series traffic distribution**. Conversely, sizing appliance capacity must plan for **short-window peaks**, not the 30-day average.

### Latency and Bottlenecks

End-to-end flow latency includes application processing, network hops, gateways, inspection, and queuing. A same-region hub does not inherently add huge latency, yet stacked inspection hops or cross-AZ detours can hurt tight SLO journeys. Measure **p50/p95/p99**, TCP handshake time, timeout rates, and failover recovery time.

Performance also hinges on **packets/second, concurrent sessions, NAT port limits, per-AZ throughput, DNS query rate, and attachment/route limits**. A firewall with high theoretical bulk throughput may still struggle with millions of short-lived connections under heavy Layer 7 inspection rules.

## 11. Reliability: The Hub Must Not Become a Single Point of Failure

When many workloads rely on a hub, a single routing or firewall mistake has far larger blast radius than a failure inside one spoke. Reliability design must examine both the **data plane** (forwarding live packets) and **control plane** (modifying routes, policies, and attachments) within the chosen service's capabilities and limits.

| Incident | Potential impact | Mitigations and tests |
| --- | --- | --- |
| A firewall instance dies | New and active flows may fail | Multi-AZ HA, health checks, route failover, test session preservation/loss |
| An AZ loses connectivity | Inspection or NAT paths in that AZ go down | Sufficient capacity per AZ, proper route/flow affinity, test failover under load |
| Shared transit/gateway degrades | Multiple spokes lose connectivity | Track SLIs, quotas, rate limits; identify bypass paths where supported |
| Incorrect route propagation | Traffic misroutes or blackholes | Manage routes via IaC, policy checks, canary rollouts, and rollback |
| Central DNS resolver fails | Apps fail service discovery | Redundant resolvers, isolate failure domains, monitor DNS |
| NAT exhausts ports or connections | New outbound connections fail | Monitor connection/port exhaustion, shard egress IPs or NAT per workload |
| VPN or dedicated circuit drops | Hybrid connectivity lost | Multiple tunnels, diverse circuits/devices where needed; test route failover |
| Broad firewall policy error | Multiple journeys fail simultaneously | Code review, pre-prod testing, staged rollout, drift detection, safe rollback |

### Distributing Functions Across AZs

When running stateful firewalls across multiple AZs, verify **how the transit service picks an AZ for packets**. Two conditions are equally critical:

1. Outbound and return packets of a session must respect statefulness requirements, typically needing **symmetric paths** or platform-supported state sync/flow pinning.
2. When one AZ is lost, the remaining AZs must have **actual spare capacity**, not just a healthy endpoint status.

For NAT, keeping egress within the same AZ avoids cross-AZ detours and reduces dependencies, though it increases the number of resources to manage. If egress is concentrated across two AZs while one AZ carries most of the traffic, test losing the largest AZ and verify how much load the surviving paths must absorb.

### Recovery Targets by Business Flow

A firewall failing over “within 30 seconds” does not mean bookings recover in 30 seconds. Old TCP connections may reset; clients and application connection pools must reconnect; DNS caches or proxies may hold stale paths. Measure SLIs from the perspective of **APIs, successful requests, and latency** of the real user journey alongside network appliance metrics.

If connectivity between two spokes drops, bounded retries, queues for async tasks, and graceful degradation can help. However, **never blindly widen firewall allow rules** to “rescue” connectivity; doing so breaks security policy and can widen the incident.

## 12. Multi-Region Design: Regional Hubs or One Global Hub?

In multi-region systems, routing all traffic back to **a single region** for inspection adds latency, inter-region data transfer fees, and dependency on that central region. A commonly evaluated approach uses **regional hubs**, sharing common standards and policies while processing traffic locally.

~~~mermaid
flowchart LR
    subgraph R1["Region 1"]
        HUB1["Regional hub 1"]
        APP1["Application spoke"]
        DATA1["Data spoke"]
        APP1 <--> HUB1
        DATA1 <--> HUB1
    end
    subgraph R2["Region 2"]
        HUB2["Regional hub 2"]
        APP2["Application / DR spoke"]
        DATA2["Data / DR spoke"]
        APP2 <--> HUB2
        DATA2 <--> HUB2
    end
    HUB1 <-->|"Controlled inter-region"| HUB2
    POLICY["Policy-as-code / audit / inventory"]
    POLICY -.-> HUB1
    POLICY -.-> HUB2
~~~

Inter-region links between hubs represent **conditional connectivity**, not unrestricted mutual access. Distinguish data replication, management, DR, and API calls; permit only necessary prefixes and services.

### Key Decisions

- **Locality:** Where are users and applications located; do daily requests really need to cross regions?
- **Data:** What data may replicate across regions, what lag is acceptable, encryption, and RPO/RTO?
- **Inter-region linking:** Platform-supported interconnect, backup routing, route filtering, and hop limits.
- **Region outage:** Can surviving applications independently reach DNS, identity, secrets, egress, and databases in the standby region?
- **Management under control-plane failure:** If you cannot create new routes or update resources in a failed region, are pre-staged configurations already in place to keep serving?
- **Failback:** When the primary region recovers, prevent split-brain writes or conflicting prefix advertisements causing unexpected path flips.

Not every system needs multi-region active-active. If RTO/RPO targets permit, backup/restore or warm standby may meet goals at lower cost. Evaluate options by **business journeys** and failure modes rather than the number of connected regions on a diagram.

## 13. Process-Driven Design: From Requirements to Routes and Policies

A disciplined execution sequence:

### Step 1 — Define Scope and Environments

List tenants, accounts/projects, production/staging, deployment regions, sensitive data zones, Internet users, corporate networks, and partners. Clarify change ownership and cost budgets. Across multiple teams, agree on who manages the hub, who manages spokes, and who approves policies.

### Step 2 — Build the Communication Flow Matrix

For each source/destination, record **protocol, port, initiation direction, data transferred, expected throughput, latency SLO, frequency, sensitivity, and fallback path**. Separate internal API calls, public ingress, Internet egress, hybrid flows, and inter-region replication.

### Step 3 — Plan Addressing and Naming

Select non-overlapping CIDRs; budget for growth, container/pod networking, VPN/partners, and new regions. Specify private DNS architecture, conditional forwarding, zone ownership, and recovery mechanisms. Never assume widely used CIDRs can be changed later without disruption.

### Step 4 — Choose Topology and Policy Boundaries

Identify where transit, inspection, NAT, private endpoints, and direct connectivity are needed. You may use a hub for hybrid, governance, and egress while keeping high-throughput traffic on authorized direct paths. Isolate route domains for lower-trust zones and enforce default-deny for unneeded paths.

### Step 5 — Design Bidirectional Routes and Failure Behavior

Trace **request and response** paths for every critical flow, including AZs, firewalls, NAT, DNS, and behavior when any component fails. Verify how peering/transit actually works on the target cloud instead of assuming automatic transit or appliance forwarding.

### Step 6 — Quantify Performance, Cost, and Scalability

Estimate GB/day per path, RPS, packet rate, concurrent flows, connection setup rate, p95/p99, peak bandwidth, inter-AZ bytes, and inter-region bytes. Estimate transit, firewall, NAT, egress, hybrid link, DNS, and logging costs. Set quota alerts and capacity scaling plans.

### Step 7 — Automate and Test

Use IaC with peer review, validate route/policy configs pre-rollout, test inter-spoke connectivity, and verify unauthorized access is denied. Canary a subset of attachments before broad network changes. Keep baselines for latency, error rates, bytes processed, and DNS.

### Step 8 — Operate and Re-evaluate Periodically

Dashboards should surface attachment/tunnel health, route changes, throughput, packet drops, firewall denials, NAT exhaustion, DNS errors, and cost by source. Maintain runbooks for AZ loss, bad routes, firewall overload, VPN flaps, and connectivity recovery. Revisit initial assumptions whenever new workloads arrive or east–west flows surge.

~~~mermaid
flowchart LR
    REQ["Business requirements + SLOs"]
    MATRIX["Traffic + data matrix"]
    TOPO["Topology + routes + policies"]
    TEST["Connectivity & fault testing"]
    OBS["Measure performance, cost, risk"]
    REQ --> MATRIX --> TOPO --> TEST --> OBS
    OBS --> MATRIX
~~~

## 14. Case Study: Multi-Environment Booking Platform with Hybrid Connectivity

Suppose a company operates three workload groups:

- **Catalog:** Read-heavy API with CDN caching; images stored in object storage.
- **Booking/Payment:** Transactions holding sensitive data; must tightly control access and egress to payment gateways.
- **Analytics:** Batch data processing requiring curated datasets from Booking and access to certain datacenter services.

The system spans multiple dev teams, separate production/staging zones, and an on-premises network `172.20.0.0/16`. Security wants egress auditing and hybrid control, while the product team needs low latency for Catalog → Booking. Transactional data must not be queried directly by all analytics workloads.

### Option A — Everything Through the Hub with Centralized Inspection

All spokes connect to the hub; inter-spoke, egress, and hybrid flows are all inspected. Pros: one clear observability and policy enforcement point. Cons: **Catalog ↔ Booking hairpinning** drives up gateway byte charges and creates dependency on shared infrastructure, even though most of that traffic does not require the same inspection depth as payment egress.

Option A can fit if strict centralized inspection is mandated and load permits. However, you must prove **throughput, latency, failure handling, and cost**. If inspecting high-GB/day east–west traffic, this design can prove costlier and harder to scale than expected.

### Option B — Every Workload Uses Dedicated Connectivity and Egress

Catalog, Booking, and Analytics each manage their own private endpoints, NATs, policies, and links. This reduces hub dependency and shortens paths for high-traffic pairs. In return, each team must handle guardrails, audits, DNS, CIDRs, quotas, and resilience on its own. If Analytics opens a direct path to the Booking database, security and data ownership boundaries risk violation.

Option B fits better with mature operational teams, uniform policy automation, and real justification for independent network domains.

### Option C — Hub Combined with Distributed Controls

A balanced design direction:

1. **Shared hub** provides hybrid routing, conditional DNS forwarding, inventory, on-premises links, and egress for workloads requiring centralized inspection.
2. **Booking** runs in a dedicated production spoke, controlling inbound from Catalog and egress to the payment gateway; enforces workload identity, TLS, and app-proximate policies.
3. **Catalog** serves users via suitable CDN/WAF/ingress; selected internal connections may use non-hairpinned private service connectivity if platform and policy allow.
4. **Analytics** never queries the transactional database directly; receives data via controlled events/exports or an analytics-scoped API.
5. **Staging** sits in an isolated route domain with no default link to production. Admin access goes through identity-backed, audited controls.
6. **Platform team** supplies IaC templates, address governance, policy-as-code, and central dashboards, while each team owns its workload rules and resources.

Option C is a strong candidate **to take into testing**, not a blanket default. If compliance mandates centralized inspection for all east–west traffic, direct paths must be revised. If high volume turns a gateway into a bottleneck, revisit inspection policies and transit structure.

### Compact Decision Matrix

| Criterion | Verification question | Evidence to collect |
| --- | --- | --- |
| Security | Is Analytics blocked from directly accessing Booking DB? | Route reachability, firewall decisions, IAM/identity policies |
| Performance | Does Catalog → Booking meet latency SLO at peak load? | p95/p99, throughput, hop counts, packet drops |
| Reliability | Does losing one AZ in the hub break bookings? | Failover tests, recovery time, error budget |
| Operations | Does adding a new spoke create accurate routes, DNS, and policies? | IaC plans, policy checks, connectivity tests |
| Cost | Which bytes traverse inspection, NAT, inter-AZ, and inter-region? | Flow logs, billing tags, per-traffic-class spreadsheets |
| Hybrid | If one VPN tunnel drops, does a compliant path remain active? | BGP routes, tunnel metrics, failover tests |

## 15. Common Design Mistakes

**1. Assuming hub-and-spoke lets every spoke see every other spoke by default.** A hub attachment only shows potential connectivity. Route domains, route tables, and firewalls must explicitly define permitted pairs. Some peering services do not automatically provide transit through an intermediate VPC/VNet.

**2. Designing outbound paths while forgetting return paths.** Stateful firewalls require flow paths compatible with state tracking. Asymmetric routing across AZs or appliances causes sporadic, hard-to-reproduce drops.

**3. Running a centralized hub with a single firewall/NAT.** This creates a single point of failure and throughput choke point under load. Require HA, AZ distribution, capacity limits, and failover tests.

**4. Forcing every byte through inspection without a requirement.** Hairpinning and stacked gateways inflate latency, cost, and blast radius. Classify traffic by sensitivity, caller, and appropriate path.

**5. Equating network reachability with authorization.** Being routable to a private IP proves neither identity nor business permission. Enforce identity, TLS, least privilege, and application checks.

**6. Forgetting DNS when adopting private networking.** Routes and endpoints may be valid while resolvers still return public IPs or fail to forward internal zones, sending apps down the wrong path or causing timeouts.

**7. Lacking a long-term CIDR plan.** Overlapping production, staging, Kubernetes, and on-premises ranges make expansion and hybrid integration costly. Never let teams pick arbitrary CIDRs independently and try to stitch them later.

**8. Using a shared NAT IP as proof of identity.** Multiple workloads behind one egress IP look identical; granting payment-gateway access by IP alone is insufficient.

**9. Mistaking HA for DR.** A multi-AZ hub can still share dependencies on one region, DNS, or global config. Define separate targets and drills for AZ loss, region loss, and misconfiguration.

**10. Treating logging as free and infinite.** Flow logs, DNS logs, and firewall logs generate substantial volume, including sensitive metadata. Plan retention, sampling where suitable, access controls, and budgets.

**11. Testing only inbound Internet flows.** An app may serve its frontend fine yet fail when calling payments, internal services, or on-premises systems. Test all critical flows bidirectionally and under component failures.

**12. Comparing costs solely by gateway count.** Factor in uptime hours, processed bytes, AZ/region transfers, NAT, egress, DNS, logs, and operational effort. Fewer gateways carrying massive transit volume are not automatically cheaper.

## 16. Practice Exercises and Guided Answers

A cloud organization has the following networks:

| Workload | CIDR | Requirement |
| --- | --- | --- |
| Hub | 10.80.0.0/16 | Hybrid gateway, DNS resolver, egress inspection |
| Spoke A — Frontend | 10.81.0.0/16 | User-facing; calls APIs in B only |
| Spoke B — Orders | 10.82.0.0/16 | Order transactions; calls payment provider over Internet |
| Spoke C — BI | 10.83.0.0/16 | Receives analytics data from pipeline; must not touch Orders DB directly |
| On-premises | 172.21.0.0/16 | Accesses internal API gateway only per policy |

The platform team wants auditable Internet egress, hybrid control, and standardized operations. The Orders team needs low API latency, while BI transfers large batch datasets.

### Question 1 — Choosing a Topology

**Prompt:** Should you deploy full mesh, hub-and-spoke, or a hybrid? Propose a verifiable approach.

**Guided answer:** Choose **hub-and-spoke for hybrid, DNS, and selected egress requiring inspection**, paired with **workload-proximate policies** for Frontend → Orders. BI should receive data over a controlled pipeline rather than touching Orders DB directly. If Frontend → Orders sees very high volume, evaluate direct/private service connectivity if policy and platform allow. This candidate design must measure latency, cost, and security tests before sign-off.

### Question 2 — Tracing a Transaction Path

**Prompt:** Frontend in A calls the Orders API in B through the hub firewall. Which components must be configured and tested?

**Guided answer:** You need private DNS/domains resolving the right IP, route A→B, hub forwarding/inspection, firewall policy allowing only that flow, route to B, and **return route B→A** aligned with stateful inspection. At the receiver, enforce network policy/security group, identity/TLS, and API authorization. Test both directions, single-AZ loss, and post-failover DNS resolution.

### Question 3 — Calculating Pairwise Link Counts

**Prompt:** With 15 spokes, how many pairwise links does a theoretical full mesh have? How many spoke attachments does a simple central hub have?

**Solution:** Full mesh requires \(15\times14/2=105\) pairwise links. With hub-and-spoke, there are **15 spoke attachments to the hub**. This excludes route tables, hub internals, redundant paths, and policies; do not use link counts alone to conclude which option is cheaper.

### Question 4 — Identifying Risk from Routes and NAT

**Prompt:** Spoke B uses a default route via the hub to reach the Internet. Post-launch, payments suffer intermittent timeouts at high load while the internal Orders API remains healthy. What should you check?

**Guided answer:** Check NAT connection/port exhaustion and throughput, firewall drops, session limits, stateful return paths, DNS latency, payment provider rate limits or timeouts, retry counts, and reconciliation results. Never blame NAT from symptoms alone. If the network is healthy, inspect the app, client pools, and provider; if NAT truly bottlenecks, evaluate splitting egress IPs or scaling capacity as supported by the provider.

### Question 5 — Challenging an “All Traffic Through the Hub” Mandate

**Prompt:** BI needs to transfer 2 TB daily from a data store in the same region, yet routing through the hub firewall adds cost and latency. How do you balance security and performance?

**Guided answer:** Clarify what the policy is actually protecting: data access permissions, payload inspection, access auditing, or merely network segmentation. You can evaluate a private endpoint or dedicated private channel with full identity, encryption, and logging if policy allows. If regulations mandate inspection, budget gateway/firewall capacity for that byte volume and optimize placement to curb inter-AZ transit. Any decision requires matching policy approval and live traffic measurements.

### Question 6 — Evaluating Reliability

**Prompt:** The hub runs two firewalls across two AZs; when AZ A fails, routes automatically shift traffic to AZ B, yet all active Orders → Payment connections must reopen. Can this be called “zero disruption”?

**Guided answer:** Not conclusively. Depending on SLOs, reset TCP sessions and timed-out requests can burn error budget. Measure recovery time from the **Orders transaction perspective**, idempotent retries, AZ B firewall/NAT capacity, and failed request counts. RTO must tie to the business journey under AZ-loss conditions, not just firewall health status.

## 17. Architecture Review Checklist

| Question | Required evidence |
| --- | --- |
| Is there a complete inventory of required connections and forbidden paths? | Source–destination–protocol–data matrix and owners |
| Do CIDRs avoid overlaps with future spokes, on-premises, and partners? | Address allocation map and registration workflow |
| Are request/response paths, transit, firewalls, NAT, and DNS documented per key flow? | Flow diagrams and bidirectional route tables |
| Are routed paths backed by access-control policies? | Firewall rules, network policies, IAM, deny tests |
| Is egress scoped by source/destination and sized for capacity? | Flow logs, firewall/NAT metrics, quotas, load tests |
| How many workloads are hit by a hub, AZ, VPN, or DNS failure? | Failure-domain diagrams, failover drills, user SLIs |
| Does multi-region preserve data residency and RPO/RTO? | Inter-region routes, replication plans, DR tests |
| Are costs measured per byte across gateways, AZs/regions, Internet, and logs? | Cost model tied to telemetry and billing |
| Are route/firewall changes controlled and reversible? | IaC, policy-as-code, reviews, canaries, audit trails |
| Are hub/spoke responsibilities clear with runbooks in place? | RACI/ownership, dashboards, drill schedules, incident runbooks |

A network decision that holds up in an architecture review demonstrates **why each flow traverses the hub or goes direct, which security layers apply, what happens when a link breaks, and whether measured cost and latency meet business requirements**. Armed with that evidence, architects can select hub-and-spoke, centralized, distributed, or hybrid topologies while keeping Well-Architected goals in balance.
