# Routing, Peering, and Transit in Multi-Network Systems

When a cloud application grows from a single private network into multiple networks across environments, products, or accounts, the question is no longer simply “is the port open?”. Architects must define **which networks may reach which, where packets traverse, what the return path is, who manages the links, and what happens when a path fails**. Ignoring those questions easily leads to asymmetric connectivity, test environments accidentally reaching production, overlapping IP addresses, ballooning data transfer costs, or a hub turning into a single point of failure.

This lesson belongs to the **Network Architecture** chapter of the **CLOUD_ARCHITECTURE** module. The goal is to understand the principles of **routing**, **peering**, and **transit**; know when to apply them across multiple VPCs/VNets, accounts, subscriptions, or projects; and evaluate options across reliability, security, scalability, cost, and operations under the Well-Architected mindset.

> **Foundational principle:** Network connectivity is the combination of **non-conflicting addresses, bidirectional routing, forwarding capability across intermediate components, and permissive security policies**. A line drawn on a diagram or a peering connection showing “active” status does not prove that applications can actually communicate.

## 1. Why Must Multi-Network Architecture Be Explicitly Designed?

Suppose a booking platform has the following functional zones:

- **Booking-prod:** APIs, workers, and booking data inside the Booking team's production network.
- **Payments-prod:** Payment services and more sensitive security dependencies.
- **Shared-services:** DNS, observability systems, deployment tooling, or shared platform services.
- **Non-production:** Dev and staging environments with permissions and policies distinct from prod.
- **On-premises:** Internal corporate systems connected via VPN or dedicated links.

Splitting networks helps govern resources by team, reduce the blast radius of changes, constrain access paths, and clarify budgets. Once split, however, teams must decide which flows still need connectivity:

| Source → Destination | Business example | Connectivity requirement |
|---|---|---|
| Booking-prod → Payments-prod | Confirm a payment | Reach only required APIs/ports, with service authentication |
| Booking-prod → Shared-services | Send logs/traces, query DNS | Valid path and permissions; do not grant blanket access to all shared services |
| Staging → Another test environment | Integration testing | Permitted conditionally; avoid connecting directly to prod databases |
| Prod → On-premises | Query corporate systems | Hybrid connectivity, consistent routing, and name resolution |
| Internet → Public API | Users placing bookings | Traverse a protected public edge; never expose data stores directly |

**Network boundaries do not align one-to-one with administrative boundaries.** Two VPCs in different accounts can be interconnected; two subnets inside the same VPC can still be blocked from each other by firewalls or security groups. Separating accounts/subscriptions/projects is an administrative governance decision; actual traffic paths must be designed, authorized, and verified separately.

## 2. Routing Fundamentals: CIDRs, Route Tables, and Next Hops

### 2.1. What Does Each Route Describe?

A **route** is a rule selecting where to forward traffic toward an IP destination. A route entry typically contains:

- **Destination prefix:** Target range in CIDR notation, e.g., 10.20.0.0/16.
- **Target/next hop:** Where to forward packets next, such as a local interface, peering connection, transit attachment, VPN gateway, or routing virtual appliance.
- **Origin and scope:** Local route, manual static entry, dynamically learned via protocol, or injected by a cloud service; governed by platform-specific precedence rules.
- **Operational state:** A route may remain in the table even when its next hop is unavailable or the downstream link has failed.

A subnet, VPC, VNet, or router may evaluate multiple route tables across different layers. When a packet traverses **multiple routing domains**, each domain makes forwarding decisions using only the information visible to it. You therefore cannot inspect the source machine's route table alone and conclude the entire path is correct.

### 2.2. Longest-Prefix Match

When multiple routes match the same destination address, standard IP routing picks the **most specific prefix (longest-prefix match)**. For example:

| Destination in route table | Illustrative next hop | Matches 10.20.8.50? |
|---|---|---|
| 0.0.0.0/0 | Internet/NAT gateway | Yes, but least specific |
| 10.0.0.0/8 | Internal router | Yes |
| 10.20.0.0/16 | Transit attachment | Yes |
| 10.20.8.0/24 | Security inspection appliance | Yes, most specific |

If all routes are active and evaluated within the same prefix-selection process, destination **10.20.8.50** matches **10.20.8.0/24**. In practice, when static routes, dynamic routes, or different target types tie in prefix length, **precedence rules are defined by the platform**; do not infer tie-breaking solely from this illustrative table.

Common prefixes:

- **10.10.0.0/16:** Roughly 65k IPv4 addresses theoretically; actual usable addresses in cloud subnets depend on the provider and subnet sizing.
- **10.10.4.0/24:** A child range inside 10.10.0.0/16.
- **0.0.0.0/0:** Default route for IPv4 when no more specific route matches; **does not mean** traffic automatically goes to the Internet, as the next hop could be a firewall or transit hub.
- **::/0:** Default route for IPv6, which must be evaluated separately from IPv4 routes.

**Destination reachability does not define access permission.** A route to Payments only provides a path; Security Groups, firewalls, Network ACLs, IAM, and the application still decide whether packets and requests are allowed.

### 2.3. Outbound Path and Return Path

An API request between two networks requires at least two matching directions:

~~~text
Booking API (10.10.5.10)                        Payments API (10.20.7.20)
          |                                                ^
          v                                                |
     Route to 10.20.0.0/16   --> Transit --> Route to Payments
          ^                                                |
          |                                                v
     Return route to Booking <-- Transit <-- Route to 10.10.0.0/16
~~~

If Booking has a route to Payments but Payments lacks a return route to 10.10.0.0/16, the TCP handshake generally cannot complete. Similarly, if traffic traverses a **stateful firewall**, both directions usually must traverse the matching inspection path so the appliance maintains session state. Asymmetric routing can cause firewalls to drop legitimate packets even when each side appears to have a route to the other.

## 3. What Is Peering?

**Peering** directly links two private networks, enabling traffic exchange over the cloud provider's network fabric via supported mechanisms. Common examples include **AWS VPC Peering**, **Azure Virtual Network Peering**, and **Google Cloud VPC Network Peering**.

~~~mermaid
flowchart LR
    subgraph A["Network A — Booking (10.10.0.0/16)"]
        APP["Booking API"]
        RTA["Route to 10.20.0.0/16"]
        APP --> RTA
    end
    subgraph B["Network B — Payments (10.20.0.0/16)"]
        RTB["Route to 10.10.0.0/16"]
        PAY["Payments API"]
        RTB --> PAY
    end
    RTA <-->|"Peering: direct link between two networks"| RTB
~~~

In this scenario, for Booking API to call Payments API over private addresses, verify:

1. The two IP ranges do not overlap under the platform's peering constraints.
2. The peering connection is created and accepted through cross-account/project/tenant approval if applicable.
3. Bidirectional routes are configured or exchanged properly per platform semantics.
4. Firewalls, security groups, network ACLs, and other policies allow the required source, destination, and port.
5. DNS and applications use the right addresses without confusing public and private endpoints.

### Peering Does Not Automatically Create Transit

In standard VPC/VNet peering models, peering is **non-transitive**:

~~~mermaid
flowchart LR
    A["VPC/VNet A"] <-->|"Peering A–B"| B["VPC/VNet B"]
    B <-->|"Peering B–C"| C["VPC/VNet C"]
    A -. "No automatic A–C path via B" .- C
~~~

That is, **A peering with B** and **B peering with C** does not let **A use B as a transit router to reach C**. If A–C traffic is needed, you must add a direct link or a valid transit mechanism. Some platforms allow combining forwarding virtual appliances and gateway transit under specific conditions; never assume peering itself supports arbitrary transitivity.

### When Peering Fits Well

Peering is usually a clean option when:

- Only **a few network pairs** need direct communication.
- Connectivity relationships are fairly stable and pairwise links remain manageable.
- You want to avoid operating virtual routers or hubs just to connect two networks.
- You can satisfy provider CIDR, quota, permission, and networking constraints.

Drawbacks appear as network count grows: many links to create, many routes to update, and higher risk of misconfiguring permitted paths. Peering data transfer fees—especially cross-Region—must also be checked by provider and traffic direction.

## 4. Transit: Connecting Many Networks Through a Routing Hub

**Transit** routes traffic through a central forwarding component instead of building every pairwise peering link. The hub may be a managed routing service, a gateway/hub, or a *network virtual appliance (NVA)* capable of forwarding.

~~~mermaid
flowchart TB
    BK["Booking-prod<br/>10.10.0.0/16"] <-->|"Attachment + routes"| HUB["Transit hub<br/>Routing and segmentation"]
    PAY["Payments-prod<br/>10.20.0.0/16"] <-->|"Attachment + routes"| HUB
    SHR["Shared-services<br/>10.30.0.0/16"] <-->|"Attachment + routes"| HUB
    DEV["Non-production<br/>10.40.0.0/16"] <-->|"Attachment + routes"| HUB
    CORP["On-premises<br/>172.16.0.0/16"] <-->|"VPN / dedicated connection"| HUB
~~~

In the diagram, **having an attachment does not mean every network is allowed to talk to every other network**. The transit hub forwards traffic to a destination only when a matching route exists and is not blocked by segmentation controls. This is precisely what lets an organization build prod, non-prod, shared, and hybrid network groups with distinct policies.

### Cloud Implementation Options

| Platform | Multi-network connectivity option | Architectural notes |
|---|---|---|
| **AWS** | **AWS Transit Gateway**, or **AWS Cloud WAN** for broader network models; paired with VPN/Direct Connect for hybrid | Transit Gateway has attachments and separate route tables; association/propagation must be explicitly designed. Cloud WAN mechanics, pricing, and limits differ from Transit Gateway |
| **Azure** | **Hub-spoke with Azure Virtual Network** and NVA/Azure Firewall as needed; **Azure Virtual WAN** with virtual hubs where suitable | VNet peering is not natively transitive. Forwarding, gateway transit, user-defined routes, and Azure Virtual WAN policies depend on each model's config and constraints |
| **Google Cloud** | **Network Connectivity Center (NCC)** and hub/spoke designs or appropriate routers/gateways; can pair with Cloud Router, Cloud VPN, Interconnect | Do not treat VPC Network Peering as transit. Spoke types, route exchange, site-to-site capabilities, and NCC limits must be verified per service/config |

**Do not map these three products as identical equivalents.** Differences may lie in route learning and advertisement, segmentation, cross-Region connectivity, attachment limits, inspection features, hybrid support, and billing models. The logical “spokes connected through transit” architecture must be verified against the actual product.

### Transit Routing: Two Separate Decisions

A transit design must answer:

1. **How does a spoke send packets into the hub?** Subnet/VPC/VNet routes or equivalent networking rules must point the target prefix toward the transit attachment/gateway.
2. **To which attachment does the hub forward the packet?** The hub's route table/segment must select the right next hop, and the return path must exist.

Adding a route only in the spoke while the hub lacks a destination route still drops packets. If the hub has routes but the spoke does not know to send packets into the hub, the outcome is the same.

## 5. Comparing Mesh Peering, Hub-and-Spoke, and Hybrid Topologies

### 5.1. Mesh Peering

When **every pair** among N networks needs direct connectivity, the maximum number of peering connections in a full mesh is:

\[
\frac{N(N-1)}{2}
\]

For example, **6 networks need 15 connections** in a full mesh, while **10 networks need 45 connections**. The formula counts pairwise edges between networks, not actual route counts; each connection can entail multiple route tables, permissions, and operational updates.

**Pros:** Direct paths, ideal for a small number of pairs; minimal dependency on a central hub. **Cons:** Link counts grow quadratically, routes and policies scatter, hard to standardize across many teams.

### 5.2. Hub-and-Spoke

Endpoint networks (**spokes**) attach to a central transit hub. With N spokes, the baseline topology needs only **N spoke–hub links**, though it also requires route tables, segmentation, hub redundancy, and potentially inspection components.

**Pros:** Easy to standardize connectivity, policy governance, and network onboarding; convenient hybrid integration. **Cons:** The hub can become a shared dependency for performance, configuration, security, and cost; paths through the hub may be longer.

### 5.3. Hybrid Model

Many systems use hub-and-spoke for cross-team links while creating direct connections for selected low-latency or very high-volume pairs if platform and policy permit. For instance, Booking-prod calls Payments-prod via controlled transit, whereas a high-volume data link between two networks under the same owner gets a dedicated connection.

Do not add direct paths merely because a hub “seems slow”. First measure **latency, throughput, per-GB processing cost, cross-zone fees, and inspection mandates**, then verify whether adding a bypass breaks segmentation policies or causes asymmetric routing.

| Criterion | Direct peering | Transit hub | Hybrid |
|---|---|---|---|
| Connection scale | Good for few pairs | Suited for many networks needing central governance | Suited when controlled exceptions exist |
| Routing | Managed mostly per pair and related route tables | Managed at spokes and at hub/segments | Must manage both paths and avoid competing routes |
| Segmentation | Relies on peering pair choice and network policies | Supports centralized segments/route tables and inspection | Flexible, but easier to introduce policy bypasses |
| Reliability | Avoids single-hub dependency for direct pairs | Must evaluate hub HA/failover and blast radius | More paths; must define precedence and failover |
| Cost | Connection and data transfer fees per cloud | Typically hub, attachment, data processing, and transfer fees | Must measure to justify exception value |
| Operations | Simple when small, complex as pairs grow | Higher initial design, easier long-term standardization | Requires strict processes and automation |

## 6. Designing CIDRs and Segmentation Before Building Routes

An **IP address plan** is a prerequisite for multi-network architecture. Overlapping CIDRs create ambiguous routes and block several peering types; with transit or hybrid setups, handling overlapping CIDRs typically demands NAT, renumbering, or integration workarounds with heavy trade-offs.

An illustrative enterprise plan:

| Network | IPv4 CIDR | Role | Permitted essential connections |
|---|---|---|---|
| Booking-prod | 10.10.0.0/16 | APIs, apps, and business services | Payments API, shared monitoring, selected on-prem |
| Payments-prod | 10.20.0.0/16 | Payment processing | Booking via controlled API; security services |
| Shared-services | 10.30.0.0/16 | DNS, logging, platform tooling | Approved shared endpoints only |
| Non-production | 10.40.0.0/16 | Dev, staging | Testing services; no broad routes to prod |
| On-premises | 172.16.0.0/16 | Corporate systems | Specific hybrid services |

These ranges are **examples**, not default addresses to copy blindly. A company already using 10.0.0.0/8 internally must inventory everything before allocating new subnets. Also reserve ample space for compute subnets, databases, endpoints, containers, and multi-year growth.

### Distinguish “No Route” from “Route Exists but Blocked”

- **Not advertising or configuring routes** from Non-production to Payments-prod lowers reachability at the network layer.
- **Firewalls and security policies** continue blocking unauthorized flows even where a route exists.
- **IAM and application auth** restrict operations on APIs, data, and secrets; establishing TCP does not mean the caller is authorized.

Strong designs combine these control layers. Network isolation supports the principle of **least privilege and blast-radius containment**, rather than replacing application-layer authentication or authorization.

## 7. End-to-End Example: Booking-prod Calling Payments-prod via Transit

Suppose the booking system needs to call the payment API over private addresses:

- Booking API sits at **10.10.5.10** in Booking-prod.
- Payments API sits at **10.20.7.20** in Payments-prod.
- Both networks attach to the transit hub via their respective attachments.
- The payment service listens only on HTTPS port 443 and authenticates workload identity.

### 7.1. Illustrative Route Tables

**Route table for Booking API's subnet:**

| Destination | Next hop | Meaning |
|---|---|---|
| 10.10.0.0/16 | Local | Traffic within Booking-prod |
| 10.20.0.0/16 | Transit attachment | Send to Payments-prod via hub |
| 10.30.0.0/16 | Transit attachment | Send to permitted shared services |
| 172.16.0.0/16 | Transit attachment | Reach approved corporate systems |
| 0.0.0.0/0 | Per dedicated egress design | Do not assume all traffic defaults straight to Internet |

**Route table for Payments API's subnet:**

| Destination | Next hop | Meaning |
|---|---|---|
| 10.20.0.0/16 | Local | Traffic within Payments-prod |
| 10.10.0.0/16 | Transit attachment | Return path to Booking |
| 10.30.0.0/16 | Transit attachment | Required security/observability services |

**Logical routing rules at the transit hub (illustrative only):**

| Ingress source | Destination | Egress | Allowed? |
|---|---|---|---|
| Booking-prod | 10.20.0.0/16 | Payments-prod attachment | Yes |
| Payments-prod | 10.10.0.0/16 | Booking-prod attachment | Yes |
| Booking-prod | 10.30.0.0/16 | Shared-services attachment | Yes as required |
| Non-production | 10.20.0.0/16 | Omit route or apply supported block mechanism | No |
| On-premises | 10.20.0.0/16 | Per hybrid network policy | Approved flows only |

This is a **logical model** for segmentation. In AWS Transit Gateway, the design uses **associations**, **route propagation**, static routes, and possibly blackhole routes per service features; which table inspects ingress from an attachment depends on the attachment's association. On Azure/Google Cloud, translate this logic into the matching route tables, hub connections, segments, or policies rather than copying AWS syntax.

### 7.2. Path of an HTTPS Request

~~~mermaid
sequenceDiagram
    participant B as Booking API 10.10.5.10
    participant BR as Booking subnet route
    participant T as Transit hub
    participant PR as Payments subnet route
    participant P as Payments API 10.20.7.20

    B->>BR: TCP SYN to 10.20.7.20:443
    BR->>T: Next hop for 10.20.0.0/16
    T->>PR: Route to Payments attachment
    PR->>P: Check policy and deliver packet
    P-->>PR: TCP SYN-ACK to 10.10.5.10
    PR-->>T: Return route to 10.10.0.0/16
    T-->>BR: Route to Booking attachment
    BR-->>B: TCP reply
~~~

This simplified diagram shows the logical path; a route table is not necessarily a standalone physical box. In reality:

1. Booking resolves Payments' private name to the right address.
2. The OS sends the packet to the subnet's default gateway; cloud routing forwards it to the transit attachment based on prefix.
3. Transit evaluates the route/segment for the ingress source and forwards toward Payments.
4. Security groups, firewalls, network ACLs, or platform policies inspect traffic per platform behavior.
5. Payments replies along the return route, traversing required inspection points.
6. After TCP and TLS are established, **application authentication and authorization** still decide which payment operations Booking may invoke.

**Common mistake:** The Booking team adds route 10.20.0.0/16 and opens port 443, but forgets route 10.10.0.0/16 on the Payments side, or the hub lacks the matching egress route. Result: requests time out even though peering/attachment status reports active.

### 7.3. Checking Non-Business Traffic Directions

Booking → Payments is not the only flow:

- **DNS:** Which resolver does Booking use? Are private DNS zones linked/forwarded properly across networks?
- **Observability:** Do logs/traces ship to Shared-services, and if that service goes down, does the payment path block?
- **Keys and secrets:** Do secret/KMS endpoints cross the hub or use private endpoints in each network?
- **Callbacks/webhooks:** If Payments calls back into Booking, that is a separate application flow needing its own routing, auth, and authorization.
- **Maintenance:** Package/image updates, time sync, health checks, or managed-service control planes may require distinct endpoints.

Therefore, a diagram showing only a single “Booking ↔ Payments” arrow must be accompanied by a **flow matrix** listing source, destination, port/protocol, owner, purpose, and verification method.

## 8. Hybrid Connectivity, BGP, and Route Propagation

When the cloud must communicate with on-premises or another network provider, architectures commonly use:

- **Site-to-site VPN:** Encrypted tunnels over suitable network infrastructure. Availability and throughput depend on the service, appliances, Internet links, and HA setup.
- **Dedicated connection:** For example AWS Direct Connect, Azure ExpressRoute, or Google Cloud Interconnect, using private connectivity models per provider terms. Dedicated circuits do not automatically encrypt traffic end-to-end; design encryption per security requirements.
- **BGP (Border Gateway Protocol):** Exchanges route information between routing systems, suited for dynamic prefix learning, multi-path failover, or connecting multiple network domains.

### Static Routes vs. Dynamic Routes

| Criterion | Static routes | Dynamic/BGP routes |
|---|---|---|
| How updated | Declared by admins or IaC | Routers/gateways advertise, learn, and withdraw routes per session and policy |
| Initial simplicity | Good for few fixed prefixes | Requires understanding peers, ASNs, prefix filters, and routing policy |
| Reaction to network changes | Must update configuration manually | Can converge automatically if services and backup paths support it |
| Risks | Stale un-updated routes, wrong next hop | Accidental prefix leaks, learning overly broad routes, subtle preference shifts |
| Best scope | Simple links, default routes, or targeted overrides | Multi-network hybrid, redundant paths, and large-scale route exchange |

**BGP does not grant access permissions.** BGP advertises and selects paths between valid neighbors; firewalls, segmentation policies, IAM, and app controls still decide what traffic is allowed. Route propagation likewise does not mean every route belongs in every segment. Prefixes must be **filtered, summarized, and scoped to connectivity needs**.

### Example with Dual Hybrid Links

On-premises has `172.16.0.0/16`, connected to the cloud over two paths (e.g., primary dedicated circuit, backup VPN). For reliable failover:

1. Define which routes are advertised over each path and how precedence works under actual platform rules.
2. Verify return routes from cloud back to on-premises.
3. Monitor BGP peer/tunnel status and route withdrawal conditions when a path drops.
4. Measure convergence time and impact on TCP sessions; **successful failover does not guarantee existing open connections survive**.
5. Test unidirectional link failures, gateway outages, policy errors, and primary-link failback.

Never assume “BGP always converges in a few seconds” without testing configurations, timers, carriers, and network conditions. Recovery targets must rest on real measurements.

## 9. Routing and Security Layers: Protecting Connected Paths

A multi-network system generally needs **trust-tier segmentation**, especially between prod, non-prod, and payment-data environments.

### 9.1. Layered Controls

| Layer | Control question | Example |
|---|---|---|
| **Routing** | Does a route exist to the target range? | Do not advertise routes from Non-production → Payments-prod |
| **Network firewall / security group** | Which sources may reach which destinations and ports? | Only Booking API may call HTTPS on Payments API |
| **DNS** | Does the service name resolve to the right endpoint? | payments.internal points to private IP |
| **TLS / service identity** | Do both ends verify identity and encrypt data in transit? | mTLS or TLS plus workload identity as required |
| **Application authorization** | Which actions may an authenticated service execute? | Booking may create payment requests, not read all records |
| **Monitoring / auditing** | Can anomalous paths, bad access, and policy changes be detected? | Network flow logs, firewall logs, audit logs, and alerts |

Never rely on routing as your sole security control: routers mainly govern paths, whereas blocking unauthorized traffic requires explicit policy layers. Conversely, opening firewall rules without bidirectional routing still fails to connect.

### 9.2. Centralized Inspection and Asymmetric Routing Risk

Some organizations force cross-network flows through a **central firewall or NVA** for policy enforcement, logging, or intrusion detection.

~~~mermaid
flowchart LR
    A["Booking-prod"] --> HUB1["Transit ingress"]
    HUB1 --> FW["Central firewall / inspection"]
    FW --> HUB2["Transit egress"]
    HUB2 --> B["Payments-prod"]
    B -. "Return path must also pass matching inspection" .-> FW
~~~

With **stateful inspection**, outbound and return paths normally must traverse the same stateful path or an HA state-sharing mechanism. If outbound crosses firewall A while replies bypass it or cross an un-synced firewall B, connections can fail. Features like appliance mode, route symmetry support, or HA syncing vary by product, so check documentation and test failover.

Additional decisions:

- Place firewalls in the **central hub** or inside each spoke, and who owns the rules?
- Is **east–west inspection** (inter-network) required, or only **north–south** (Internet or on-premises ingress/egress)?
- Must DNS, proxies, managed service endpoints, or cross-Region traffic also traverse inspection?
- If the hub/firewall fails, does the system **fail closed** or use a bypass path? Rules depend on data classification.
- Do per-hop cost and latency fit the business budget and SLOs?

### 9.3. DNS and Private Endpoints

Routes operate on IP addresses; applications usually call **domain names**. When linking networks, inspect private DNS zones, inbound/outbound resolvers, DNS forwarding, overlapping domain names, and record visibility scopes. Deploying a private endpoint for a managed service does not automatically teach DNS in every spoke to resolve to that private IP.

Many “service unreachable” incidents are actually **DNS returning a public IP while the network only permits private paths**, or returning a stale IP after an endpoint change. Always test name resolution from the **actual source network** before debugging routes.

## 10. Common Routing Failures and How to Investigate

When connectivity breaks, never edit multiple route tables simultaneously. Troubleshoot layer by layer based on symptoms.

| Symptom | Likely causes | Verification step |
|---|---|---|
| Peering active yet TCP fails | Missing one-way route, firewall block, wrong subnet/port | Inspect source/dest routes, policies on both sides, flow logs |
| A↔B and B↔C work, A↔C fails | Assumed transitive peering | Verify valid transit model or direct A–C peering |
| Only one subnet cannot connect | Subnet uses a different route table or policy | Check exact subnet route-table association and security rules |
| One direction arrives, replies fail | Missing return route, asymmetric routing, misconfigured NAT | Trace both directions, firewall state, SNAT/DNAT steps |
| IP works but domain name fails | Broken DNS zone, resolver, forwarding, or stale cache | Query DNS directly from the source workload and compare with endpoint |
| Failures after adding a new network | Overlapping CIDR, more specific route, propagation change | Audit full prefix table, route selection, and advertisement policies |
| Failures during hybrid failover | Unconverged BGP routes, missing backup route, firewall state | Check BGP peers/advertised-learned routes and test failover |
| Fails only on large payloads | MTU/PMTU mismatch or blocked fragmentation | Check Path MTU, MSS clamping, and tunnel/appliance limits |
| Ping fails yet HTTPS works | ICMP blocked or target drops ICMP | Test the real application protocol; never conclude solely from ping |
| Unusually slow connections | Hairpinning through hub/Region, inspection, NAT, or saturation | Measure per-hop latency with proper tools and device metrics |

### Step-by-Step Debugging Workflow for a Specific Flow

Example: Booking (10.10.5.10) calling Payments (10.20.7.20:443):

1. **Pin down the exact flow:** Source IP/subnet, destination IP/FQDN, protocol, port, timestamp of failure, and initiation direction.
2. **Verify DNS:** Does Payments' name resolve to the right private IP from Booking? Any TTL/forwarding/zone overrides?
3. **Verify source routing:** Where does the longest-prefix match for 10.20.7.20 point? Is that route table actually associated with Booking's subnet?
4. **Verify intermediate links:** Are peerings/attachments/tunnels healthy, does the transit segment hold the target route, and is anything blackholed or misrouted?
5. **Verify destination routing:** Does Payments have a return route to 10.10.5.10, and is the return path consistent with inspection?
6. **Verify policies:** Security groups, firewalls, network ACLs, NVA rules, or endpoint policies. For stateful vs. stateless rules, check the return direction as applicable.
7. **Verify the application:** Is the service listening on the right port, does TLS handshake succeed, is the cert valid, and what error does auth/authZ return?
8. **Use live telemetry:** Flow logs, firewall logs, transit/tunnel metrics, packet captures if permitted, and provider path-analysis tools.

Examples of cloud path-analysis tools include **AWS VPC Reachability Analyzer**, **Azure Network Watcher**, and **Google Cloud Connectivity Tests**. Simulation capabilities, supported resource types, and coverage vary; a “reachable” result at the network layer does not guarantee applications, certificates, or business rules succeed.

## 11. Reliability, Scalability, Cost, and Operations of Transit

### Reliability

A central hub standardizes connectivity yet widens the **blast radius of misconfigurations**. Distinguish:

- **Managed services with built-in redundancy:** Cut infrastructure toil, but do not protect against misconfigured routes/policies or attaching to the wrong segment.
- **Hybrid connections:** Require multiple circuits, devices, and diverse locations matching recovery targets; two tunnels riding the same physical failure point may be insufficient.
- **Network vs. application:** A healthy hub does not keep a feature up if the destination database is down; SLOs must span the full dependency chain.
- **Resilience drills:** Test route, attachment, hub, firewall, DNS, and dedicated-circuit failures against defined RTO/RPO or connectivity recovery targets.

**RTO** specifies maximum recovery time and **RPO** specifies acceptable data loss upon recovery. RPO mainly applies to data; never use RPO alone to evaluate a route table. For networking, track complementary metrics like convergence time, connection success rate, latency, and packet loss.

### Performance and Scaling

Transit can introduce extra hops or detours. Limits to assess include attachment counts, route counts, bandwidth, packets per second, NVA connections, session tables, VPN quotas, and inspection throughput. **Adding API instances will not help if the bottleneck sits in the hub, firewall, or hybrid link.**

During design, estimate **east–west** app traffic, data access traffic, peak loads, capacity during single-link failure, and backup/sync traffic. For latency-sensitive apps, test from the actual planned Region, AZs, and link types.

### Cost

Cost categories typically needing estimation:

| Category | Cost drivers | Waste-reduction hints |
|---|---|---|
| **Connectivity footprint** | Peering, hub, attachment, or gateway fees per provider | Build only needed connections; consider grouping compatible flows |
| **Data through hub** | Processing or transfer fees by direction, GB, and uptime | Measure east–west volume; avoid unnecessary detours |
| **Cross-region/cross-zone** | Fees and latency for crossing location boundaries | Place services intentionally, balancing against HA and compliance |
| **Inspection** | Managed firewalls, NVA compute, licenses, logs | Scope which flows need inspection, right-size, and set quotas |
| **Hybrid** | Dedicated circuits/VPNs, ports, carriers, data transfer | Measure bandwidth and redundancy needs rather than guessing |
| **DNS/NAT/logging** | Resolver endpoints, NAT gateways, queries, log retention | Design DNS/private endpoints and log retention policies purposefully |

Exact pricing varies by product, Region, and traffic direction; never apply a single generic number across all clouds. Direct peering can be cheaper when only two networks exchange data; transit can lower operational cost at scale while adding hub and data-processing fees. Decisions must weigh **traffic profiles and total cost**, including operational effort.

### Operations

Manage routes, attachments, and policies via **Infrastructure as Code (IaC)** or a peer-reviewed change workflow with pre- and post-deploy checks. For large systems, establish:

- Clear owners for each network, CIDR, attachment, prefix, and route/segment.
- An approved flow catalog with business justifications and accountable owners.
- Change logs for network policies, routes, BGP, and cross-network access.
- Dashboards tracking link health, tunnel drops, BGP sessions, latency, packet loss, bytes/GB, and spend.
- Route rollback procedures and post-change bidirectional routing tests.
- Logical network diagrams and deployment docs updated alongside architectural changes.

## 12. Well-Architected Review

The goal of a review is to produce **evidence** for each decision—not merely checking that a diagram shows a hub, spokes, and a firewall icon.

| Perspective | Review question | Expected evidence |
|---|---|---|
| **Operational Excellence** | Who manages routes, builds links, and fixes bad changes? | IaC, owners, change reviews, runbooks, rollback drills |
| **Security** | Can non-prod reach prod? Do firewalls/IAM protect sensitive endpoints? | Flow matrix, segments, denied-access tests, flow logs |
| **Reliability** | Who is impacted by a transit attachment, DNS, firewall, or hybrid failure? | Dependency map, failover tests, convergence times, alerts |
| **Performance Efficiency** | Does the hub have enough throughput and low enough latency at peak load? | Load tests, network metrics, quotas, cross-Region path tests |
| **Cost Optimization** | Where does inter-network traffic flow and where is it billed? | Traffic forecasts, billing/cost attribution, per-attachment volume |
| **Sustainability** | Are there idle network/NVA resources or over-retained logs? | Right-sizing, log lifecycle policies, unused attachment/route cleanup |

### Illustrative Acceptance Criteria

For the Booking–Payments system, the team might agree on measurable targets:

1. **Booking-prod → Payments-prod:** HTTPS succeeds over the intended path, and only approved sources/ports may connect.
2. **Non-production → Payments-prod:** No approved path exists; unauthorized connection tests are blocked.
3. **Single hybrid link failure:** Backup path restores connectivity within the agreed target time, verified via periodic drills.
4. **Peak hours:** P95 connection setup time and network latency stay within application thresholds at design load.
5. **Cost visibility:** Transit/attachment and inter-network traffic costs can be attributed by owner or product team.

Exact quantitative thresholds (such as convergence time or monthly GB) must come from real requirements and service capabilities; never assume defaults from a diagram alone.

## 13. Workflow for Choosing Peering vs. Transit

A practical decision workflow:

1. **Inventory networks and owners:** VPCs/VNets, accounts/subscriptions/projects, CIDRs, Regions, environments, data classifications.
2. **Build the connectivity matrix:** Source network, destination network, protocol/port, expected load, return flow, owner, and business reason.
3. **Plan addressing and DNS:** Prevent overlapping CIDRs; define private DNS, resolvers, endpoints, and administrative ownership.
4. **Choose topology:** Use peering for few pairs; consider transit when many networks need connectivity, governance, or central hybrid access; evaluate hybrid options for special requirements.
5. **Design bidirectional routes:** Source subnet, transit/hub segment, destination subnet, and return path; verify zero unintended routes.
6. **Design segmentation and security:** Route filters, firewalls, inspection, IAM, TLS, and cross-boundary policies.
7. **Evaluate limits and cost:** Quotas, attachments, bandwidth, latency, data processing, cross-region fees, managed services, and ops overhead.
8. **Verify:** Run permitted/denied connectivity tests, route failures, BGP failover, DNS, peak load, and actual cost checks.
9. **Document decisions:** Topology diagram, flow matrix, route tables/segments, ADR, assumptions, and review triggers.

Example short **Architecture Decision Record (ADR)**:

> **Context:** The enterprise has over a dozen networks across production, testing, and shared services; frequently provisions new networks; needs hybrid links; and must restrict non-prod to prod flows.
>
> **Options:** (A) Expand mesh peering; (B) build a transit hub with centrally governed routes/segments and policies; (C) combine transit for general links with direct peering for approved exceptions.
>
> **Illustrative decision:** Choose B as the default topology, allowing exceptions only with an ADR and route verification tests.
>
> **Rationale:** Cuts pairwise configuration, standardizes network onboarding and hybrid integration, and enables centralized segmentation.
>
> **Trade-offs:** Hub dependency, attachment/data-processing fees, and overhead of managing routes/inspection and redundancy.
>
> **Verification:** Test permitted bidirectional connectivity, block non-prod → prod, measure load/cost, simulate hybrid link loss, and update runbooks.

The ADR captures **rationale and consequences**; network diagrams and route tables capture **structure and paths**. Keep these artifacts synchronized whenever adding networks, changing CIDRs, adding Regions, or switching providers.

## 14. Practice Exercise: Finding Flaws in a Multi-Network Design

A company has four networks:

| Network | CIDR | Requirement |
|---|---|---|
| A — Booking-prod | 10.10.0.0/16 | Calls payment API in B and sends logs to C |
| B — Payments-prod | 10.20.0.0/16 | Accepts requests from A, replies to A |
| C — Shared-services | 10.30.0.0/16 | Provides logging and DNS for approved networks |
| D — Non-production | 10.40.0.0/16 | Testing only; must not reach Payments-prod |

Currently the team created **peering links A–C, B–C, and D–C**. Booking cannot reach Payments. One member suggests “let traffic go from A into C and automatically forward to B since both peer with C”. Another suggests adding route 10.20.0.0/16 in A without changing anything in B.

### Tasks

1. Explain why the current peering setup does not let A call B through C automatically.
2. Propose two solutions: direct A–B connectivity, or a valid hub/transit design. When would you choose each?
3. For the transit option, describe routes required in subnet A, the hub, subnet B, and the return path; state clearly how D → B is blocked.
4. Specify how to test DNS for the Payment API and the HTTPS flow on port 443.
5. List at least three risks of placing a central firewall to inspect A ↔ B.
6. Build a test matrix covering A → B, A → C, D → B, and losing a redundant hybrid link.

### Guided Solution

**Part 1 — Peering:** A peering C and B peering C only establish two separate links A–C and B–C. Under non-transitive peering semantics, C is not a default transit router. Therefore A has no automatic path to B via C.

**Part 2 — Choosing connectivity:** If only A and B need direct communication across a small set of networks, adding A–B peering with bidirectional routes/policies can be simple. If network count, hybrid needs, and shared governance are growing, a transit hub with proper routing and segmentation scales better. The choice also depends on specific cloud service features and pricing.

**Part 3 — Routes and segmentation:** A routes 10.20.0.0/16 to transit; the hub routes ingress from A to attachment B; B routes 10.10.0.0/16 to transit; the hub routes ingress from B back to attachment A. D neither learns nor receives a route to B under policy, and firewalls/policies block unwanted access. Also inspect any more specific routes or default routes that might create unintended detours.

**Part 4 — DNS and HTTPS:** From A, resolve the Payment API's FQDN, confirm it returns B's private IP, test TCP 443, TLS, and app auth. Then inspect logs/metrics to verify traffic takes the intended route and firewall and returns to A.

**Part 5 — Central firewall:** Can become a shared failure point, add latency/cost, and drop sessions if asymmetric routing occurs or state fails to sync during failover. Requires sizing, HA, route symmetry, rule governance, and drills.

**Part 6 — Testing:** Document every allowed/denied flow, test method, and evidence, for example:

| Test | Expected result | Evidence |
|---|---|---|
| A calls B:443 | Connects successfully; API enforces permissions properly | Connection/TLS, application response, flow logs |
| B replies to A | Return packets follow intended path; not dropped by firewall | Route tables, bidirectional flow logs |
| A sends logs to C | Reaches logging endpoint with proper permissions | Logs received, network logs |
| D calls B:443 | Blocked by policy; no unauthorized path exists | Policy/route review and denied-connection test |
| Drop one hybrid link | Redundant flows fail over within target time | BGP/tunnel metrics, latency, and app test results |

**Key takeaway:** In multi-network systems, design **outbound paths, return paths, transitivity boundaries, and trust perimeters** as part of application architecture. Peering works well for small pairs; transit manages connectivity at scale; yet both require sound CIDRs, accurate route configurations, access controls, observability, cost evaluation, and fault testing to turn a network diagram into a reliable cloud system.
