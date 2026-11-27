# AWS Direct Connect, Virtual Interfaces, and Connection Redundancy

When AWS applications need to exchange data frequently with an *on-premises* data center, standard Internet connectivity may fall short on consistent transport, predictable bandwidth, or network route governance. **AWS Direct Connect (DX)** provides a dedicated network connection between an enterprise network and an **AWS Direct Connect location**. Over the physical link, enterprises configure **virtual interfaces (VIFs)** and **BGP** routing to reach the right AWS resources.

However, a single Direct Connect circuit can become a *single point of failure*. Real-world designs must simultaneously account for **circuits, hardware, Direct Connect locations, BGP, gateways, route tables, security, bandwidth, and failover mechanisms**.

This lesson belongs to the **Advanced Network Connectivity** chapter of the **CLOUD_PROVIDERS_AWS** module. It situates Direct Connect within the AWS ecosystem—covering Regions/AZs, IAM, VPC, compute, storage, databases, integration, and serverless—helping learners choose services and design applications that are secure, observable, resilient, and cost-controlled.

## 1. Learning Objectives

After this lesson, learners will be able to:

1. Describe Direct Connect and distinguish between **dedicated connections**, **hosted connections**, **virtual interfaces**, **Direct Connect gateways**, and **Transit Gateways**.
2. Choose the right **private VIF**, **public VIF**, or **transit VIF** for connectivity scenarios.
3. Explain the roles of **802.1Q VLANs**, **BGP ASNs**, BGP peers, routing prefixes, and the difference between physical link status and application data flow.
4. Design redundancy across hardware, carriers, fiber paths, and Direct Connect locations, and add **Site-to-Site VPN** where appropriate.
5. Compare **active/active** with **active/passive**, explain their impact on forward/return paths, and test failover.
6. Monitor link state, BGP sessions, bandwidth, and network errors, and evaluate total hybrid connectivity costs.

## 2. Where Does Direct Connect Fit in Hybrid Architecture?

Direct Connect is a network connectivity service with a demarcation point at a **Direct Connect location**, typically a *colocation* facility or partner interconnection point. The enterprise needs a physical circuit or provider service to reach that location from its router. A Direct Connect location is **not** an Availability Zone or a place where EC2/RDS instances run; it links the corporate network to the AWS network.

Basic flow:

~~~mermaid
flowchart LR
    subgraph DC["Corporate Data Center"]
        LAN["Internal network / applications"]
        CR["Customer router"]
        LAN --> CR
    end
    CR -->|"Circuit / partner"| LOC["AWS Direct Connect location"]
    LOC -->|"Dedicated / hosted connection"| VIF["Virtual interface + BGP"]
    VIF --> GW["VGW or Direct Connect gateway"]
    GW --> VPC["VPC: EC2, ECS, RDS, internal services"]
~~~

Depending on the VIF type, destinations can be **VPCs using private IPs**, **public addresses of AWS services**, or **multiple VPCs connected via Transit Gateway**. Each hop has its own configuration and access controls; a BGP session reaching *Established* alone does not prove applications can connect.

### 2.1. Comparing Connectivity Options

| Option | Transport path | Best-fit scenarios | Key limitations |
|---|---|---|---|
| **AWS Site-to-Site VPN over Internet** | IPsec over Internet connection | Fast setup, backup path, moderate traffic | Subject to Internet variability; performance fluctuates with path conditions |
| **AWS Direct Connect** | Dedicated physical connection to a DX location | Long-term hybrid, steady bandwidth, frequent data transfers | Requires physical/partner provisioning; must design redundancy; does not encrypt traffic by default |
| **VPN combined with Direct Connect** | IPsec combined with DX infrastructure per supported architecture | Need DX transport plus network-layer encryption | More complex setup; must distinguish VPN using DX as transport vs. independent Internet VPN |
| **Internet / public API connectivity** | Internet and public endpoints | Applications only calling public APIs | Does not replace private connectivity to private subnets |

A Direct Connect circuit can carry traffic to AWS resources across multiple Regions via appropriate gateway configurations; do not assume a DX physical location must match the Region hosting the VPC.

## 3. Dedicated Connections, Hosted Connections, and VIFs

### 3.1. Dedicated Connection

A **dedicated connection** is a physical Ethernet connection dedicated to a single customer at a Direct Connect location. The customer orders the connection through AWS and arranges physical cross-connects with the colocation facility or carrier during provisioning. When full control over VIF count, hardware, link settings, and redundancy design is required, this is often a suitable choice.

### 3.2. Hosted Connection

A **hosted connection** is provisioned by an **AWS Direct Connect Partner** over the partner's interconnect infrastructure. The enterprise works with the partner for capacity and deployment. Supported bandwidths and handoff formats depend on the partner and configuration.

**Do not confuse:** a *hosted connection* is a connectivity service provisioned by a partner; a *hosted virtual interface* is a VIF created for another AWS account that must be accepted by the receiving account per workflow. These are two distinct concepts.

| Criterion | Dedicated connection | Hosted connection |
|---|---|---|
| Provisioning entity | Customer orders directly from AWS | Provisioned by an AWS Direct Connect Partner |
| Management model | Customer manages the DX link and VIFs within supported limits | Customer/partner share responsibilities per purchased service |
| Hardware and last-mile | Must meet cross-connect and network equipment requirements | Path depends on partner infrastructure and contract |
| Redundancy | Can place dedicated circuits across multiple DX locations | Must clarify path, location, and hardware independence provided by partner |
| Selection basis | Capacity, control, and existing infrastructure | Partner capabilities, provisioning speed, and operational needs |

### 3.3. Where Do Virtual Interfaces Fit?

A **VIF** is a logical interface configured over a Direct Connect connection, using **802.1Q VLANs** and one or more **BGP peering** sessions with configured IP addresses. The VIF determines **the type of AWS resources reachable** and the appropriate logical termination point, while the DX circuit serves as the underlying transport.

Parameters typically prepared include:

- **Connection ID** of the physical or hosted connection, and the VIF type to create.
- Valid, non-conflicting **VLAN ID** within the connection scope per AWS requirements.
- **Customer BGP ASN** and AWS/Direct Connect gateway-side ASN.
- **IPv4 or IPv6 BGP peer addresses**, and BGP session authentication config if used.
- **Target gateway**, VIF-owning account, and network prefixes to advertise/receive.
- **MTU** and frame type compatible with hardware and VIF type; configure jumbo frames only if all components support them.

Never use VLANs or BGP as substitutes for application **security groups, NACLs, firewalls, route tables, or IAM**. They address different control layers.

## 4. Three Virtual Interface Types and How to Choose

| VIF Type | Primary destination | Logical attachment | Typical use case | Not used for |
|---|---|---|---|---|
| **Private VIF** | **Private** addresses inside one or more eligible VPCs | **Virtual Private Gateway (VGW)** or **Direct Connect gateway (DXGW)** with VGW associations | On-premises accessing private EC2/RDS in VPCs | Attaching directly to Transit Gateway |
| **Public VIF** | **Public** addresses belonging to AWS networks and public AWS services | Public BGP peering to AWS public prefixes | On-premises calling AWS public endpoints, e.g., services with public APIs | General Internet transit or accessing private VPC IPs |
| **Transit VIF** | Multiple VPCs or attachments connected via **Transit Gateway (TGW)** | **DXGW**, then **TGW association** | Large hybrid networks, many VPCs/accounts, centralized routing | Attaching directly to VGW |

### 4.1. Private VIF: Accessing Private IPs Inside VPCs

For a single VPC with a **VGW**, a private VIF can attach directly to the VGW when appropriate. To connect to **multiple VPCs across supported Regions or accounts**, a private VIF can terminate at a **DXGW**, which then associates with multiple **VGWs**.

~~~mermaid
flowchart LR
    R["On-prem router"] --> DX["Direct Connect connection"]
    DX --> PV["Private VIF"]
    PV --> DG["Direct Connect gateway"]
    DG --> VG1["VPC A VGW"]
    DG --> VG2["VPC B VGW"]
    VG1 --> V1["VPC A: private workload"]
    VG2 --> V2["VPC B: private workload"]
~~~

**Limitation to remember:** a DXGW associating multiple VGWs does not automatically become a **VPC-to-VPC** router or a **hairpin path through on-premises** for two VPCs to talk directly. VPC-to-VPC communication requires an explicit routing architecture such as Transit Gateway or other suitable VPC connectivity options.

### 4.2. Public VIF: Calling AWS Public Endpoints

A public VIF carries traffic from the corporate network to **AWS public IP prefixes**; AWS advertises eligible prefixes over BGP. This provides a path for AWS APIs or resources using public addresses, but it is **not an Internet transit service** to reach arbitrary public Internet addresses.

Public VIFs have specific requirements for **public IP prefixes** advertised by the enterprise, ownership registration, and routing verification. Coordinate with your carrier and AWS before configuring prefix advertisements. Data must still be protected at the application/transport layer as required: calling HTTPS on a public endpoint does not mean the physical DX link encrypts traffic by itself.

When accessing AWS services **via private IPs/endpoints inside a VPC**, consider private/transit VIFs and **VPC endpoints/PrivateLink** if supported by the service; a public VIF does not replace designing the corresponding private path.

### 4.3. Transit VIF: Connecting Many VPCs via TGW

For systems with many applications, VPCs, and accounts requiring centralized routing, **Transit VIF → DXGW → TGW → VPC attachments** is the standard pattern:

~~~mermaid
flowchart LR
    ONP["On-premises networks"] --> DX["Direct Connect connection"]
    DX --> TV["Transit VIF + BGP"]
    TV --> DG["Direct Connect gateway"]
    DG --> TG["Transit Gateway"]
    TG --> VA["VPC A attachment"]
    TG --> VB["VPC B attachment"]
    TG --> VC["Shared services VPC"]
~~~

In this design:

1. Create a **DXGW** with an appropriate ASN.
2. Create a **Transit VIF** on the DX connection pointing to the DXGW.
3. Associate the **TGW** with the DXGW; complete proposal acceptance when cross-account workflows apply.
4. Set up **VPC attachments**, TGW route tables, propagations/associations, VPC route tables, firewalls, and allowed prefixes.
5. Verify BGP, forward and return paths, and application access controls.

**Do not attach a private VIF directly to a TGW** and **do not attach a transit VIF directly to a VGW**. A DXGW used for VGW/private VIF configurations cannot arbitrarily be shared simultaneously for TGW/transit VIF attachments; follow current association rules and quotas. The ASNs of the TGW and DXGW must be different when associating them per service requirements.

## 5. Roles of DXGW, VGW, TGW, and Route Tables

| Component | Role | Common mistakes |
|---|---|---|
| **DXGW** | Logical bridge between VIFs and AWS gateways in supported configurations | Treating DXGW as an intermediate router that automatically connects every VPC |
| **VGW** | VPC virtual private gateway for certain DX/VPN architectures | Forgetting route propagation or configuring only one direction |
| **TGW** | Routing hub across VPCs/VPNs and hybrid links | Missing TGW route-table association/propagation or attachment routes |
| **VPC route table** | Controls packet forwarding out of subnets | Adding routes on-premises while forgetting return routes from the VPC |
| **Security group/NACL** | Controls traffic at network/resource layer | BGP is up yet TCP connections fail due to missing rules |
| **Customer router/firewall** | BGP, route filtering, LAN connectivity, and security policies | Advertising wrong prefixes or creating asymmetric return paths |

**Bidirectional routing is mandatory.** When a packet travels from the LAN to a private IP in a VPC, there must be a forward route **LAN → DX → VPC** and a return route **VPC → DX → LAN**. Traffic must also be allowed in security groups, NACLs, and firewalls; DNS must resolve to the right IP, especially when using private hosted zones or hybrid DNS resolvers.

**Illustrative CIDR example:**

- On-premises network: **10.40.0.0/16**.
- Application VPC: **10.80.0.0/16**.
- Data VPC: **10.90.0.0/16**.

CIDRs must not overlap if the routing architecture cannot handle address collisions. Before connecting multiple VPCs or accounts, inventory CIDRs, route propagations, and advertised prefix lists. With DXGW/TGW, pay special attention to **allowed prefixes**: this controls permitted routes in the gateway association, not a replacement for a firewall.

## 6. BGP Peering and Path Selection

Direct Connect uses **Border Gateway Protocol (BGP)** to exchange routing information between the customer router and AWS. Typically, each VIF requires the right **ASN**, peering addresses, and BGP neighbor settings. A VIF can configure IPv4/IPv6 peering depending on capabilities and needs.

### 6.1. BGP Up Does Not Mean Application Traffic Works

Distinguish states by layer:

| Verification layer | Success indicator | Examples of failure despite lower layer working |
|---|---|---|
| Physical link | Port and DX link active | Missing VIF or wrong VLAN |
| VLAN and BGP | BGP session **Established** | Required prefixes not advertised/received |
| Routing | Valid bidirectional prefixes and next hops | TGW/VPC route table missing forward/return paths |
| Network policy | Firewall, SG, NACL permit traffic | TCP blocked or DNS resolves incorrectly |
| Application | API/DB responds within SLO | Wrong IAM, TLS, database auth, or service endpoint |

If BGP does not come up, check in order: **interface state → VLAN → peer IPs → ASN → BGP authentication → router ACL/firewall → session parameters**. If BGP is up yet routes are missing, check **import/export** policies, prefix filtering, **allowed prefixes**, gateway association status, and route propagation.

### 6.2. Active/Active and Active/Passive

Two DX circuits can be configured as:

- **Active/active:** both links carry traffic; AWS supports **ECMP (Equal-Cost Multi-Path)** under eligible BGP and topology conditions. This can improve bandwidth utilization and leave an active path during failures.
- **Active/passive:** one link is preferred while the other waits to take over after BGP and routing reconverge. Useful when predictable primary/backup paths are desired, though failover time and backup capacity must be measured.

**Important:** BGP routes across multiple devices. The **on-premises → AWS** direction is governed by BGP policies on your router; the **AWS → on-premises** direction depends on AWS policies, advertised prefixes, and path attributes. The two directions are **not automatically symmetric**.

For private/transit VIFs, AWS supports **BGP local preference communities** to influence return path priority from AWS back to on-premises:

| Community | Meaning |
|---|---|
| **7224:7100** | Low preference (*low*) |
| **7224:7200** | Medium preference (*medium*) |
| **7224:7300** | High preference (*high*) |

When conditions permit, you can advertise the same prefix from the primary VIF with a high-preference community and from the backup VIF with a low-preference community. For active/active, both paths can use the same community and matching attributes to qualify for ECMP. AWS evaluates **longest prefix match**, **local preference**, **AS_PATH**, and other routing attributes—not a single BGP community alone.

Do not copy communities from **private/transit VIFs** to **public VIFs**: public VIFs have their own prefix rules and BGP communities. Before changing route preferences in production, test failover and observe both the **forward path** and the **return path**.

### 6.3. Faster BGP Failure Detection

Direct Connect supports **Bidirectional Forwarding Detection (BFD)** to detect link failures faster in eligible setups. AWS may enable BFD support automatically on VIFs, but **the customer router must still be configured properly** for it to take effect. Convergence time depends on timers, hardware, topology, and backup paths; never promise a fixed RTO based on BFD alone.

## 7. Designing Connection Redundancy by Failure Domain

Failures can occur at multiple layers:

1. **Enterprise port/router**: optical transceiver, module, router, or power supply.
2. **Local loop / last mile**: fiber cut, shared conduit, or carrier outage.
3. **DX location**: AWS hardware at the interconnection point or full-facility outage.
4. **Routing**: BGP down, wrong route filtering, prefix changes, or route table edits.
5. **AWS applications and infrastructure**: VPC misconfiguration, AZ/Region service disruption, DNS, or backend failures.

A second link **only genuinely increases resilience** when it avoids sharing the failure domain you need to protect against. Two circuits from two differently named carriers can still share the same physical fiber conduit; request path-diversity diagrams and verify them with partners.

### 7.1. AWS Direct Connect Resiliency Toolkit

AWS provides the **Direct Connect Resiliency Toolkit** and *Connection wizard* to help select dedicated connection topologies with appropriate redundancy. Common models:

| Model | Typical design | Mitigated risks | Meaning |
|---|---|---|---|
| **Development and test** | Separate connections to different devices at the **same DX location** | Individual device failure | Does not survive a full DX location outage |
| **High resiliency** | Two dedicated connections to **multiple DX locations** | Link or device failure; reduces location outage impact | Fits many production workloads; still verify SLA terms |
| **Maximum resiliency** | Separate connections on separate devices at **more than one DX location**, often combining multiple links per location | Higher resilience against device, link, and full-location failures | Fits mission-critical systems, requiring matching budget and operations |

Toolkit documentation notes design targets associated with **99.9%** SLA for *High resiliency* and **99.99%** SLA for *Maximum resiliency*, but these are **not automatic guarantees** merely from naming the architecture. SLA eligibility depends on all terms in the AWS Direct Connect SLA, actual configuration, and customer/partner responsibilities.

### 7.2. Example Two-Location Redundant Topology

~~~mermaid
flowchart LR
    subgraph ON["Enterprise / on-premises"]
        LAN["LAN / workloads"]
        R1["Router 1"]
        R2["Router 2"]
        LAN --> R1
        LAN --> R2
    end
    R1 -->|"Carrier / path A"| LA["DX Location A"]
    R2 -->|"Carrier / path B"| LB["DX Location B"]
    LA -->|"VIF A / BGP A"| DG["Direct Connect gateway"]
    LB -->|"VIF B / BGP B"| DG
    DG --> TG["Transit Gateway"]
    TG --> VPC["VPC applications / data"]
~~~

This diagram illustrates **two links across two DX locations**, which by itself does not prove *Maximum resiliency*. Achieving that target requires the full set of connections, separate hardware, locations, and SLA verification. Maintain detailed physical diagrams showing **routers, physical hardware, circuit pairs, network carriers, and DX locations** rather than only drawing two lines on a logical diagram.

### 7.3. Why Is LAG Insufficient for Location-Level HA?

A **Link Aggregation Group (LAG)** uses **LACP** to bundle multiple dedicated connections into one logical interface, typically to increase bandwidth and simplify management. AWS LAG members terminate at the **same DX location and the same AWS device**; AWS does not support **multi-chassis LAG** for this DX configuration.

Therefore:

- A LAG can help survive **a single member link failure** within configuration limits.
- **A single LAG does not eliminate AWS device failures or DX location outages**.
- Location-level HA requires **independent connections/LAGs across multiple locations** with appropriate BGP/routing failover.

### 7.4. VPN as a Backup Path

**AWS Site-to-Site VPN over the Internet** can serve as a backup path when DX fails, if bandwidth and SLA permit. Configure two VPN tunnels as recommended by the service, along with routes and health checks. Do not confuse this with **IPsec VPN running over Direct Connect**: if the VPN rides over the failed DX circuit, it loses its transport too.

A true backup path requires an **independent failure domain**, sufficient bandwidth for critical workloads, compatible route configurations, and tested DNS/firewall behavior.

| Failure scenario | Second DX in same location | DX in another location | Independent VPN over Internet |
|---|---|---|---|
| One DX port or link fails | Can continue if hardware/path not shared | Can continue | Can continue |
| One DX location fails | Not guaranteed | Can continue if links and routing are independent | Can continue if Internet/VPN does not share failure domain |
| Shared carrier/last-mile cut | Both may fail | Only effective if last-mile is truly diverse | Depends on surviving Internet path |
| Misconfigured AZ/VPC route table | Usually not resolved | Usually not resolved | Usually not resolved |
| Entire AWS Region outage | Does not recover application automatically | Does not recover application automatically | Does not recover application automatically |

**Network redundancy and application redundancy are different.** Surviving an entire AZ/Region outage requires **Multi-AZ/DR** design, database replication, DNS/routing, and application-layer runbooks—not merely adding Direct Connect links.

## 8. Encryption and Security on Direct Connect

**Direct Connect does not encrypt data in transit by default.** A dedicated connection has a private physical path, which does not mean data is encrypted end-to-end.

Protection options:

| Solution | Protection scope | Notes |
|---|---|---|
| **TLS/HTTPS** | Protects application-layer connections to supported endpoints | Recommended for APIs, service calls, and sensitive apps |
| **IPsec / Site-to-Site VPN over DX** | Network-layer encryption in a compatible VPN architecture | Must verify tunnel throughput, endpoints, MTU, routes, and redundancy |
| **MACsec** | Point-to-point Layer 2 encryption on supported DX connections | MACsec link scope, hardware support, connection type, and location must be verified; does not replace end-to-end TLS/IPsec |
| **Firewalls, SGs, NACLs, IAM** | Controls paths, ports, identities, and actions | Does not directly encrypt data; must be configured alongside |

If using **MACsec**, verify compatible hardware, supported connection types, and encryption modes. Depending on mode, if MACsec negotiation fails, the link may **stop forwarding traffic** or **fall back to unencrypted traffic**; choose according to enterprise security policy. Never assume every hosted connection supports MACsec.

For systems handling sensitive data, combine IAM authorization, network rules, encryption at rest (S3/EBS/RDS), encryption in transit, and logging. Direct Connect **does not by itself satisfy national/Regional data residency requirements**; inspect traffic paths and where data is processed and stored.

## 9. Sample Deployment Workflow

### Step 1 — Gather Requirements

Create a specification covering: target VPCs/Regions and AWS accounts, applications, on-premises CIDRs, peak bandwidth, latency, security requirements, RTO/RPO, active/active vs. active/passive, redundancy tier, provisioning lead time, and budget.

If the corporate network spans multiple sites, evaluate **shared failure points** in the core network and carriers before finalizing circuit counts.

### Step 2 — Choose Locations, Connection Type, and Redundancy Model

Select DX locations and carriers with suitable network paths. Confirm provisioning capability, *cross-connects*, hardware at both ends, dedicated vs. hosted type, and redundancy plan. For critical workloads, consider the **Resiliency Toolkit** Connection wizard.

### Step 3 — Choose VIF/Gateway Model

- **Single VPC, private IPs:** consider private VIF → VGW.
- **Multiple VPCs using VGWs across Regions/accounts:** consider private VIF → DXGW → VGWs.
- **Multiple VPCs via central hub:** transit VIF → DXGW → TGW.
- **AWS public endpoints:** public VIF; verify public prefix requirements.

Design around **gateway association limits**, routing capabilities, bandwidth, and cross-account governance.

### Step 4 — Plan BGP and Routing

Define ASNs, VLANs, peer addresses, BGP authentication, allowed prefix lists, route filters, default-route policies, and return routes. With multiple DX locations, define BGP preferences/communities for active/active or active/passive. Diagram both **on-prem → AWS** and **AWS → on-prem** paths in full.

### Step 5 — Establish Connections and Security Policies

Once ports/hosted connections are provisioned and the partner completes physical links, configure VIFs, DXGW/VGW/TGW, VPC route tables, TGW route tables if applicable, SGs/NACLs, DNS resolvers, and required encryption layers. Assign IAM permissions for Direct Connect administration following least privilege; document network configs and approvers.

### Step 6 — Functional and Load Testing

Verify **link/VLAN/BGP → learned prefixes → bidirectional routing → application**, then run realistic test traffic and monitor metrics. Validate bandwidth, jitter, packet loss, MTU, costs, and failover characteristics.

### Step 7 — Planned Failover Testing

Simulate losing each link, a BGP session, or a location under approved change procedures, verify alerts, and measure:

- BGP detection and convergence time.
- Total application downtime or degradation duration.
- Throughput on the surviving path when carrying full load.
- Whether forward and return paths shift as expected.
- Clean failback to the primary path without flapping or unexpected load distribution.

**AWS Direct Connect Failover Test** in the Resiliency Toolkit can help test BGP failover within supported scopes. Perform tests only in announced change windows with rollback plans, as fault injection can disrupt live traffic.

## 10. Checking Status with AWS CLI

The following commands are **read-only** and require an AWS profile with appropriate permissions; replace illustrative IDs with actual lab resources. AWS CLI and Direct Connect endpoints must target the configured Region.

~~~bash
# List Direct Connect connections visible to the account.
aws directconnect describe-connections \
  --query 'connections[].{Id:connectionId,Name:connectionName,State:connectionState,Location:location,Bandwidth:bandwidth}' \
  --output table

# List virtual interfaces, VIF types, states, and connection IDs.
aws directconnect describe-virtual-interfaces \
  --query 'virtualInterfaces[].{Id:virtualInterfaceId,Type:virtualInterfaceType,State:virtualInterfaceState,Connection:connectionId,Vlan:vlan}' \
  --output table

# View Direct Connect gateways within supported scope.
aws directconnect describe-direct-connect-gateways \
  --query 'directConnectGateways[].{Id:directConnectGatewayId,Name:directConnectGatewayName,ASN:amazonSideAsn}' \
  --output table

# List Direct Connect metrics in CloudWatch.
aws cloudwatch list-metrics --namespace AWS/DX
~~~

Cross-check results against **BGP session state** on the corporate router and VIF **BGPPeers** status; if using DXGW/TGW, also inspect gateway associations, attachments, and actual route tables.

### 10.1. Metrics to Monitor

| Metric (CloudWatch, namespace `AWS/DX`) | Operational meaning | When to alert |
|---|---|---|
| **ConnectionState** | Link up/down state | Loss of any required connection |
| **ConnectionBpsIngress / ConnectionBpsEgress** | Ingress/egress throughput from AWS's perspective | Approaching capacity or sudden drop/spike |
| **ConnectionErrorCount** | Link-layer errors at the port | Abnormal increase; suspect cabling/optics |
| **VirtualInterfaceBgpStatus** | VIF BGP session status | BGP down or frequent flapping |
| **VirtualInterfaceBgpPrefixesAccepted / Advertised** | Count of accepted/advertised prefixes | Unexpected drop or missing routes |
| **VirtualInterfaceBpsIngress / Egress** | VIF traffic throughput | VIF saturation or unexpected traffic loss |
| **ConnectionEncryptionState** | Link encryption status when configured | Loss of encryption in architectures requiring MACsec |

**ConnectionState = up** does not prove applications are serving normally. Combine with **synthetic monitoring**, RTT/packet-loss measurements, firewall logs, API/database probes, and application SLOs. CloudWatch aggregates data over periods; tune alarms appropriately so brief outages aren't missed without triggering excessive false positives.

### 10.2. Troubleshooting Runbook

| Symptom | Check in order | Initial remediation |
|---|---|---|
| **ConnectionState down** | Carrier, optics, cross-connect, router interface, DX notifications | Shift to backup path; coordinate with AWS/carrier |
| **Connection up, BGP down** | VLAN, peer IP, ASN, authentication, device/router | Inspect peering/config before altering broad routing |
| **BGP up, expected routes missing** | Route filters, advertised prefixes, allowed prefixes, DXGW/TGW associations | Fix corresponding routing policies |
| **Routes exist, yet TCP cannot reach EC2/RDS** | VPC/TGW route tables, SGs, NACLs, firewalls, DNS | Verify bidirectional paths and service ports |
| **Primary DX down, backup does not take load** | BGP preferences, communities, AS_PATH, prefix count, backup capacity | Fix failover conditions and retest |
| **Low bandwidth, high packet loss** | Utilization, MTU, queuing, interface drops, ISP/carrier | Isolate congested segment; balance load/upgrade capacity |
| **MACsec state unhealthy** | Hardware, keys/mode, supported port, CloudWatch encryption state | Follow encryption recovery runbook; avoid weakening security posture |

## 11. Costs and Operational Responsibilities

Total Direct Connect cost must account for more than the AWS circuit port alone:

| Item | Example charges | Party to verify with |
|---|---|---|
| **Direct Connect fees** | Port/capacity hours and outbound data transfer by pricing model and Region | AWS pricing page, current pricing terms |
| **Cross-connect/colocation** | Physical port at demarcation facility, patch cables, rack space | Colocation facility |
| **Last-mile and carrier circuits** | Fiber path from office/data center to DX location | Carrier or Direct Connect Partner |
| **Backup paths** | Secondary circuits, hardware, operational staffing, backup VPN | AWS + partner + enterprise |
| **AWS gateways and companion services** | TGW attachment/data processing, VPN, monitoring, cross-service/Region traffic | AWS per specific design |
| **Maintenance and testing** | Implementation effort, change windows, incident support, failover drills | Operations team and partners |

AWS offers multiple Direct Connect pricing models depending on terms and timing; do not assume a single hourly fee or flat data transfer rate for every scenario. Use **AWS Pricing Calculator** and official pricing pages, factoring in one-way/two-way traffic, redundancy, and capacity when **a single link must carry the entire load**.

Cost optimization must be weighed against availability: dropping a DX location reduces cost but can create production outage risks far outweighing the savings.

## 12. Design Scenarios and Exercises

### Scenario A — Single VPC with Basic Connectivity Needs

An enterprise runs an accounting app on-premises that needs to access a private RDS instance in one AWS VPC. Bandwidth is relatively steady, data is sensitive, and the system can tolerate a brief planned outage window.

**Question:** Which VIF should be chosen and what must be checked?

**Hint:** Use a **private VIF** with a VGW or DXGW per topology. Ensure non-overlapping private CIDRs, bidirectional routes, security groups opening only the DB port from the corporate network, and application-layer encryption. Prepare a backup link or independent VPN separate from the primary DX link and test the application after failover.

### Scenario B — Multiple VPCs Across Multiple Accounts

An organization has application, data, and shared-services networks across multiple VPCs in different accounts. The goal is centralized hybrid network governance without creating separate VIFs for every VPC.

**Question:** Private VIF with multiple VGWs or transit VIF + TGW?

**Hint:** Determine whether centralized VPC-to-VPC routing and multiple attachments are needed, or only on-premises-to-VPC. If centralized networking is needed, evaluate **transit VIF → DXGW → TGW**, then design TGW route tables and cross-account resource sharing. If only private links to a few VPCs are needed, **private VIF → DXGW → VGW associations** may suffice. Both models differ in quotas, routing, costs, and limits.

### Scenario C — Primary DX Link Fails

The system has two physical connections, both terminating on **the same device in the same DX location**, bundled into a single LAG. When that DX location suffers an outage, both connections go down.

**Question:** Why didn't two connections preserve access? What must change?

**Hint:** Cable count does not determine failure-domain independence. Design across two truly distinct locations, separate routers/last-mile paths, with BGP and failover plans. For critical workloads, reference **High/Maximum resiliency** in the Toolkit, check SLA terms, and run location-loss drills. Backup VPN only helps if its transport remains healthy.

### Scenario D — Asymmetric Routing

On-premises routers send traffic over VIF A, while AWS returns traffic over VIF B due to differing BGP preferences. The enterprise's *stateful* firewall drops many TCP sessions.

**Question:** What must be verified and adjusted?

**Hint:** Inspect both traffic directions, BGP local preference on on-premises routers, communities/AS_PATH advertised to AWS, route tables, and firewall placement. After selecting a consistent load-balancing policy, test long-lived/sensitive sessions during path transitions, checking timeouts and connection states.

## 13. Checklist Before Moving Direct Connect to Production

- [ ] Identified target applications, accounts, Regions, VPCs, CIDRs, and actual bandwidth needs.
- [ ] Distinguished **dedicated** vs. **hosted connection**, carrier contracts, and physical path to DX locations.
- [ ] Selected the right **private/public/transit VIF** and **VGW/DXGW/TGW** architecture.
- [ ] Verified VLANs, peer IPs, ASNs, BGP auth, route filters, allowed prefixes, and MTU.
- [ ] Verified **bidirectional** routes across on-premises, DX, TGW/VPC, and firewall/SG/NACL policies.
- [ ] Verified truly independent physical failure domains; LAG is not mistaken for location-level HA.
- [ ] Chosen redundancy model, checked SLA conditions, and prepared failover runbooks.
- [ ] Addressed **encryption in transit** via TLS, IPsec, or MACsec as appropriate; DX does not encrypt by default.
- [ ] Configured CloudWatch alerts for **ConnectionState**, BGP, throughput, and link errors.
- [ ] Tested link loss, BGP convergence, load on backup links, and application impact.
- [ ] Budgeted DX, data transfer, carrier, cross-connect, TGW/VPN, and operational costs.
- [ ] Documented network diagrams, owners, support contacts, and design review schedules.

## 14. Takeaways

**Direct Connect** provides a dedicated network connectivity layer between enterprise networks and AWS, while **VIFs** determine how resources are reached. **Private VIFs** target private IPs inside VPCs; **public VIFs** target AWS public prefixes; **transit VIFs** connect via DXGW and TGW to serve multi-VPC networks. **BGP and route tables** govern bidirectional reachability. **Redundancy is only effective when avoiding shared failure domains**, paired with failover mechanisms and realistic testing under application load. Finally, Direct Connect does not automatically replace encryption, IAM, network security, monitoring, or Multi-AZ/Multi-Region recovery architectures.

### Official AWS Documentation to Reference During Implementation

- [AWS Direct Connect — User Guide](https://docs.aws.amazon.com/directconnect/latest/UserGuide/) — concepts, connectivity models, and service scope.
- [Direct Connect virtual interfaces](https://docs.aws.amazon.com/directconnect/latest/UserGuide/create-vif.html) — private, public, and transit VIFs.
- [Direct Connect gateways](https://docs.aws.amazon.com/directconnect/latest/UserGuide/direct-connect-gateways.html) — gateway association patterns.
- [Virtual private gateway associations](https://docs.aws.amazon.com/directconnect/latest/UserGuide/virtualgateways.html) — private VIF/DXGW/VGW limits.
- [Transit Gateway associations](https://docs.aws.amazon.com/directconnect/latest/UserGuide/direct-connect-transit-gateways.html) — transit VIF and DXGW/TGW.
- [Routing policies and BGP communities](https://docs.aws.amazon.com/directconnect/latest/UserGuide/routing-and-bgp.html) — active/active, active/passive, and route preference.
- [Direct Connect Resiliency Toolkit](https://docs.aws.amazon.com/directconnect/latest/UserGuide/resiliency_toolkit.html) — redundancy models, SLAs, and failover testing.
- [Link aggregation groups](https://docs.aws.amazon.com/directconnect/latest/UserGuide/lags.html) — LACP, single-device termination, and LAG limits.
- [Encryption in AWS Direct Connect](https://docs.aws.amazon.com/directconnect/latest/UserGuide/encryption-in-transit.html) — VPN, MACsec, and data encryption.
- [Monitor with Amazon CloudWatch](https://docs.aws.amazon.com/directconnect/latest/UserGuide/monitoring-cloudwatch.html) — ConnectionState, BGP, throughput, and metrics.
- [AWS Direct Connect Pricing](https://aws.amazon.com/directconnect/pricing/) — pricing models and cost factors.
