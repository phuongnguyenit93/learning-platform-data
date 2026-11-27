# Choosing VPN or Interconnect Based on Connectivity Requirements

> **Chapter:** DNS and Hybrid Connectivity  
> **Module:** CLOUD_PROVIDERS_GCP

When moving part of an enterprise data center system to Google Cloud, the key question is not merely "how do two networks see each other?" Engineering teams must decide between **IPsec-encrypted connectivity over the Internet versus a dedicated private circuit**, how much bandwidth is needed, acceptable latency, fault tolerance, who operates the hardware, and what cost fits. Choosing between **Cloud VPN** and **Cloud Interconnect** directly affects performance, security, availability, and scalability.

In the **CLOUD_PROVIDERS_GCP** module, learners study project organization, IAM, and VPCs; deploying Compute Engine, GKE, Cloud Run, storage, and databases; protecting resources, automating releases, and monitoring reliability and costs. This lesson focuses on the hybrid connectivity decision so a Cloud Run API or GKE/Compute Engine workload can communicate in a controlled way with on-premises databases, DNS, identity systems, or applications.

**After learning, you will be able to:**

1. Distinguish Cloud VPN, Dedicated Interconnect, Partner Interconnect, Cross-Cloud Interconnect, and HA VPN over Cloud Interconnect.
2. Use bandwidth, latency, encryption, SLA, location, deployment timeline, and cost requirements to select the right technology.
3. Explain the roles of VPCs, Cloud Router, BGP, gateways, VLAN attachments, and enterprise-side appliances.
4. Design diagrams with primary paths, backup paths, forward/return directions, and failover testing.
5. Build an architecture decision table, cost estimate, and verification plan in an authorized environment.
6. Recognize routing errors, CIDR overlaps, firewalls, MTU, BGP, DNS, and technology-specific limitations.

## 1. What Is the Hybrid Connectivity Problem?

**Hybrid connectivity** allows networks in data centers, branch offices, partner networks, or other cloud providers to connect to one or more Google Cloud **VPC networks**. The usual goal is accessing resources via **private IP addresses** rather than exposing every service to the public Internet.

Example of a partially migrated order application:

~~~text
On-premises: 172.16.0.0/16
├── ERP system            172.16.10.20
├── Business database     172.16.20.10
└── Internal DNS          172.16.53.10

Google Cloud VPC: 10.20.0.0/16
├── Compute Engine VM     10.20.1.10
├── GKE worker/pod ranges (per configuration)
└── Cloud Run via appropriate VPC egress
~~~

GCP services need to reach `172.16.20.10:5432` without exposing the database to the public Internet. Connectivity must support packets **from GCP to on-premises and return traffic back**.

To design this, separate four layers:

| Layer | Questions to Answer |
| --- | --- |
| **Transport** | Over the Internet via IPsec, a dedicated circuit to Google, or a connectivity provider's network? |
| **Routing** | How does the VPC learn `172.16.0.0/16`? How does the enterprise network know the path back to `10.20.0.0/16`? |
| **Security** | Is traffic encrypted? Who is allowed access? How are firewalls and DNS configured? |
| **Operations** | Are there redundant paths, BGP/tunnel/circuit monitoring, and single-link failure tests? |

**Note:** Cloud VPN is a **site-to-site IPsec VPN**, not a client VPN service for employees dialing into a VPC from personal laptops. If the requirement is individual laptop access, use an appropriate user-access solution rather than assuming Cloud VPN provides client VPN.

## 2. Five Options to Distinguish

### 2.1. Cloud VPN: IPsec Tunnels Over the Internet

**Cloud VPN** connects an enterprise or external network to a VPC using **IPsec** tunnels. Data is encrypted between VPN gateways; with standard Cloud VPN, traffic traverses the **public Internet**.

Google Cloud offers:

- **HA VPN:** the recommended choice for new connections needing high availability. The gateway has two interfaces with dedicated external IPs and uses **dynamic routing (BGP) via Cloud Router**. Qualifying topologies can meet a **99.99%** SLA; other topologies may only qualify for **99.9%** or no SLA.
- **Classic VPN:** single-interface gateway supporting static routing (route-based/policy-based), **99.9%** SLA. Primarily understood for maintaining or migrating legacy systems; HA VPN is a better starting point for new BGP designs.

Each Cloud VPN tunnel's speed is limited by **packet rate** (currently documented at up to roughly **250,000 packets per second** combined ingress and egress). Depending on packet size, performance is roughly equivalent to **1–3 Gbps per tunnel**. This is **not guaranteed bandwidth**. RTT, packet loss, peer gateway capacity, MTU, TCP stream count, and encryption load all affect actual throughput.

**When to consider:** Proof-of-concept connections, low-to-moderate traffic, fast deployment, no colocated infrastructure yet, temporary backup, or links that can tolerate Internet variability.

### 2.2. Dedicated Interconnect: Direct Physical Connections

**Dedicated Interconnect** establishes physical Ethernet connections between an enterprise network and Google's network at a supported **colocation facility**. The enterprise needs compatible routers/appliances, coordinates with the facility provider, and completes circuit ordering, LOA-CFA, cross-connects, testing, and activation.

Supported physical links include **10 Gbps, 100 Gbps, and 400 Gbps**, depending on location and equipment. One Dedicated Interconnect connection can bundle multiple circuits, while **VLAN attachments** carve out connectivity to specific VPCs.

Typical advantages:

- Network path does not traverse the public Internet.
- High bandwidth with better traffic and latency predictability than a typical Internet path.
- Well suited for large data transfers and long-term stable hybrid systems.
- Greater enterprise control over facility connectivity, hardware, and capacity.

Trade-offs: Port/circuit fees, cross-connects, routers, operations, staffing, and **physical provisioning lead time**. If the system does not require this scale of capacity or cannot reach a colocation facility, Dedicated may not fit.

### 2.3. Partner Interconnect: Connectivity via a Service Provider

**Partner Interconnect** connects an enterprise to Google Cloud through a supported **service provider**. The enterprise does not necessarily need to bring its own hardware to a Google colocation facility. For this connection type, a **VLAN attachment's** documented capacity ranges from **50 Mbps to 50 Gbps**, depending on tiers actually offered by the provider and location.

Partner Interconnect has two models:

| Partner Model | Who Manages BGP Near Google? | When Does It Fit? |
| --- | --- | --- |
| **Layer 2** | Enterprise configures BGP between its on-premises router and Cloud Router | Wants direct control of BGP/prefixes and has routing operations capability |
| **Layer 3** | Service provider establishes BGP with Cloud Router; enterprise-side setup depends on contract | Wants the provider to manage part of routing and reduce hands-on configuration |

Advantages: Smaller bandwidth increments than Dedicated and support for sites far from colocation facilities. Trade-offs: Dependency on the provider, SLA/pricing, and operational responsibility including the enterprise-to-provider segment.

**Important regarding SLAs:** Google's Partner Interconnect SLA covers the **VPC ↔ service provider network** segment; it does not automatically cover the entire **enterprise network ↔ provider ↔ Google Cloud** path. Review the provider's SLA and physical path design as well.

### 2.4. Cross-Cloud Interconnect

If the remote side is not a private data center but a **network at another cloud provider**, Google Cloud offers **Cross-Cloud Interconnect** to connect directly to supported providers. It is part of the Cloud Interconnect family, with its own port ordering, pairing locations, supportability, BGP, and pricing rules.

This option is worth evaluating when data volume between Google Cloud and AWS/Azure/OCI or another supported cloud is high, steady, or requires dedicated connectivity. Do not substitute on-premises Dedicated Interconnect for Cross-Cloud in diagrams, as the remote operator and provisioning workflow differ.

For Cross-Cloud / managed cloud partner solutions, supported product portfolios and regions can change. Check current documentation for both source and target clouds.

### 2.5. HA VPN over Cloud Interconnect: Combining Private Circuits and IPsec

**Cloud Interconnect does not encrypt traffic by default.** If IP encryption between the enterprise network and VPC is required, you can deploy **HA VPN over Cloud Interconnect** over Dedicated or Partner Interconnect. Thus:

- **Cloud Interconnect** provides connectivity to Google without traversing the public Internet.
- **HA VPN tunnels** apply IPsec encryption on top of that path.
- **Two layers** must be configured: VLAN attachments/Cloud Router for Interconnect, and HA VPN gateways/tunnels/Cloud Router for VPN.
- For redundancy/SLA, proper attachment counts and topologies are needed—not just a single tunnel.
- **VPN tunnel packet-rate limits still apply**; having a 10/100 Gbps circuit does not mean a single IPsec tunnel runs at circuit speed.

This is suitable when **both a private path and network-layer encryption** are required. **MACsec for Cloud Interconnect** can also be used on supported connections, though encryption covers the Ethernet link segment between your router and a supported Google edge router; MACsec does not automatically protect end-to-end across Google's internal network. MACsec can be combined with IPsec/TLS per security policy.

## 3. Quick Comparison Table for Orientation

| Criterion | HA VPN | Dedicated Interconnect | Partner Interconnect | HA VPN over Interconnect |
| --- | --- | --- | --- | --- |
| **Path** | IPsec over public Internet | Physical connection to Google | Via service provider | IPsec over Interconnect |
| **Default encryption** | Yes, IPsec | No | No | Yes, IPsec |
| **Throughput** | Limited per tunnel/packet rate; can add tunnels | 10/100/400 Gbps circuits, depending on config | 50 Mbps–50 Gbps attachments, per provider | Interconnect plus per-IPsec-tunnel limits |
| **Deployment time** | Usually fast if VPN peer and public IPs exist | Requires circuit ordering/cross-connect, longer | Depends on provider provisioning time | Requires Interconnect first, then VPN setup |
| **Enterprise requirements** | Compatible IPsec peer and BGP | Routers, colocation or backhaul, BGP, VLANs | Provider contract; L2 or L3 BGP | VPN appliances plus Interconnect requirements |
| **Latency** | Affected by Internet and RTT | Usually consistent, fewer public hops | Depends on provider network | Interconnect latency plus IPsec processing overhead |
| **SLA** | 99.99% when HA topology qualifies; never inferred from 1 tunnel | 99.9%/99.99% per qualifying topology | 99.9%/99.99% for Google–provider scope; needs provider SLA | Per supported Interconnect/HA VPN topology |
| **Cost** | Tunnels/gateway and data transfer, peer network costs | Ports/circuits, attachments, data transfer, colocation | Attachments, data transfer, provider fees | Interconnect + VPN + operations |
| **Used as backup?** | Common when needing technology diversity | Can be primary or one leg | Can be primary or alternate leg | Yes if HA and routing are designed properly |

This table only helps **screen options**; it does not replace capacity math and SLA topology checks against official documentation. The "99.99%" figure is tied to **deployment conditions and service scope**, not an automatic entitlement from a product name.

## 4. Six Requirement Groups to Gather Before Choosing

### 4.1. Bandwidth and Traffic Pattern Needs

Measure:

- **Average and peak traffic**, both GCP-to-on-premises and on-premises-to-GCP.
- **Packet rate (pps)**, packet sizes, small-packet ratio, and concurrent TCP flows.
- **Daily/monthly transfer volumes**, e.g., backups, data sync, DB replication.
- **Projected growth** over 12–24 months.
- **Failover capacity requirement:** what share of traffic must the surviving path carry?
- **Sensitivity to packet loss/RTT**, especially synchronous replication and DB transactions.

A rough average bandwidth estimate:

~~~text
Average bandwidth (Mbps)
  = bytes transferred in period × 8 / seconds in period / 1,000,000

Required capacity
  ≈ peak traffic + headroom + load absorbed during failover
~~~

Never order circuits based solely on average bandwidth. A system moving 1 TB/day may have modest average throughput yet still require several Gbps during a short backup window. Check actual peak rates and packet rates.

**For Cloud VPN:** 250,000 pps per tunnel is a very important limit. A workload composed of small packets can hit the pps limit before reaching expected Gbps. For Interconnect, also factor in VLAN overhead, MTU, router capacity, attachment size, and provider bandwidth.

### 4.2. Latency and Stability

"Private Interconnect" typically uses paths less exposed to the public Internet, which helps stabilize latency. However, **there is no fixed RTT number** for every destination. RTT still depends on geographic distance, metro, provider paths, hop counts, application load, and encryption devices.

Measure latency from the **actual workload location** to the **actual on-premises service**, not just by pinging a gateway address from a test VM. For Java/SQL applications making many round trips, small RTT differences can compound into noticeable transaction latency.

### 4.3. Availability and Recovery

State the application's **SLOs** and **RTO/RPO**. A connection "with a 99.99% SLA" does not guarantee a database will not error during a few seconds of network drop, or that BGP failover occurs fast enough for active transactions. Test retries, timeouts, connection pools, and application recovery mechanisms.

### 4.4. Security and Compliance

Ask:

1. Is **encryption in transit** mandatory?
2. Does policy permit IPsec-encrypted transit over the Internet?
3. Must data traverse specific network providers or geographic regions?
4. Is application-layer TLS required regardless of the network path?
5. Where are firewalls, segmentation, and access logs managed?

**A private path does not equal an encrypted path.** If policy mandates IPsec, pick HA VPN or HA VPN over Interconnect; if only segment-level Ethernet protection is required, evaluate MACsec while documenting the exact protected boundary.

### 4.5. Location and Provisioning Feasibility

- Does the enterprise have routers in a Google-supported **colocation** facility for Dedicated?
- Can it lease backhaul/cross-connects to colocation and staff operations?
- Which service providers offer suitable PoPs, bandwidth, SLAs, and pricing for Partner?
- Where are the target cloud region and VPC? Which metros and edge availability domains apply?
- Does on-premises have static public IPs and IPsec/BGP appliances compatible with HA VPN?
- Must connectivity be up in days, or can it follow a multi-week procurement, installation, and approval cycle?

### 4.6. Total Cost of Ownership (TCO)

Google service pricing is only part of the picture; also count hardware, circuits, operations, support, and redundancy.

| Cost Category | Cloud VPN | Dedicated | Partner |
| --- | --- | --- | --- |
| Google resources | Gateways/tunnels and associated traffic | Physical connections/ports, VLAN attachments, traffic | VLAN attachments and traffic |
| Off-Google costs | Peer VPN gateways, ISPs, encryption appliances | Colocation, cross-connects, routers, backhaul | Provider/circuit charges, operational costs |
| Redundancy | Multiple tunnels/gateways/peers, possibly multiple ISPs | Multiple connections, metros, domains, routers | Multiple attachments/providers/metros |
| Operations | IPsec, keys, BGP, tunnel sessions | Circuits, BGP, optics, capacity, and colocation | Provider SLA, L2/L3 BGP, incident coordination |
| Scaling | Add tunnels; watch pps limits | Upgrade/add links/circuits, attachment capacity | Depends on provider services and capacity |

Compare over the **same period** (month/year), same total data egress, same redundancy level, and same peak traffic. Never pick an option merely by comparing the price of one VPN tunnel against one Interconnect port; their cost scopes differ.

## 5. Reference Architectures and Role of Cloud Router

### 5.1. Dual-Path HA VPN Pattern

~~~mermaid
flowchart LR
    subgraph DC["Enterprise network"]
      LAN["172.16.0.0/16"]
      PEER1["Peer VPN gateway A"]
      PEER2["Peer VPN gateway B"]
      LAN --> PEER1
      LAN --> PEER2
    end
    subgraph GCP["Google Cloud"]
      VPC["VPC 10.20.0.0/16"]
      GW0["HA VPN gateway interface 0"]
      GW1["HA VPN gateway interface 1"]
      CR["Cloud Router · BGP"]
      GW0 --> CR
      GW1 --> CR
      CR -. "Manages routes" .-> VPC
    end
    PEER1 == "IPsec tunnel + BGP" ==> GW0
    PEER2 == "IPsec tunnel + BGP" ==> GW1
~~~

Depending on peer hardware and topology, you can use one peer with two interfaces or two independent peers. To qualify for the highest supported SLA tier, **connect both interfaces**, configure matching tunnel pairs, and ensure peer-side redundancy. An HA VPN gateway with only one tunnel or one active interface **does not automatically qualify for the SLA**.

**Cloud Router** manages **BGP** sessions and dynamic routes. The VPC routing infrastructure performs packet forwarding. Never describe Cloud Router as a VM router receiving and forwarding every packet.

### 5.2. Dedicated Interconnect Pattern

~~~mermaid
flowchart LR
    ON["On-premises router"] --> COL["Colocation / Cross-connect"]
    COL == "Dedicated Ethernet circuits" ==> EDGE["Google edge router"]
    EDGE --> VLAN["VLAN attachment"]
    VLAN --> CR["Cloud Router · BGP"]
    CR -. "Dynamic routes" .-> VPC["VPC 10.20.0.0/16"]
~~~

This diagram **illustrates only a single path** and does not satisfy production HA requirements. A production architecture needs multiple circuits/connections, edge availability domains, potentially multiple metros, VLAN attachments, Cloud Routers, and customer hardware per the corresponding SLA topology.

Key concepts:

- **Connection:** physical resource provisioned to Google's network.
- **VLAN attachment:** logical link between an Interconnect connection and a VPC/region, with bandwidth capacity and BGP.
- **Cloud Router:** exchanges BGP routes; can apply regional/global dynamic routing per VPC and topology.
- **Edge availability domain:** independent maintenance domain within a metro, typically named `zone1`/`zone2`; distinct from a **Compute Engine zone**.
- **Metro:** metropolitan area containing interconnect locations; redundancy rules apply across metros/domains.

### 5.3. Partner Interconnect Pattern

~~~mermaid
flowchart LR
    ON["Enterprise network"] --> CSP["Partner: service network"]
    CSP --> EDGE["Google edge"]
    EDGE --> VLAN["VLAN attachment"]
    VLAN --> CR["Cloud Router / BGP"]
    CR -. "Dynamic routes" .-> VPC["Google Cloud VPC"]
~~~

In Partner **Layer 2**, BGP sessions typically run between the enterprise router and Cloud Router over the provider-carried circuit. In Partner **Layer 3**, the provider manages BGP on the Google side per the service model, and the customer coordinates routing on its own side with the provider.

**The Google–provider segment covered by Google's SLA differs from the provider–customer segment.** When assessing end-to-end availability, factor in the carrier/last-mile SLA, repair times, and physical path diversity.

### 5.4. HA VPN over Interconnect Pattern

~~~mermaid
flowchart LR
    LAN["On-premises LAN"] --> PEER["Peer VPN gateway"]
    PEER --> ATT["VLAN attachments over Interconnect"]
    ATT --> HAGW["HA VPN gateway attached to attachment"]
    HAGW --> VPC["VPC private workloads"]
    BGP1["Cloud Router for Interconnect"] -. "Exchanges VPN gateway prefixes" .-> ATT
    BGP2["Cloud Router for HA VPN"] -. "Exchanges workload prefixes" .-> HAGW
~~~

Here **two Cloud Routers have distinct roles**: the Interconnect-layer router supports reachability to the VPN gateways across attachments, while the HA VPN-layer router exchanges actual prefixes between the VPC and enterprise network. This is more complex than direct IPsec over the Internet.

**Design point:** When enabling IPsec on a VLAN attachment, the choice must be made at attachment creation time; do not assume an existing standard attachment can be flipped to encrypted via a simple setting. Review migration and redundancy procedures carefully.

## 6. BGP Path Selection and Failover Design

Both **HA VPN** and **Cloud Interconnect** typically use **Cloud Router + BGP** to exchange prefixes between a VPC and enterprise systems. Even the right product choice will fail if routes are not advertised or the return path is broken.

### 6.1. Clearly Define Prefixes on Both Sides

Example:

~~~text
Google Cloud VPC:          10.20.0.0/16
On-premises:               172.16.0.0/16

Cloud Router receives from peer: 172.16.0.0/16
Peer router receives from GCP:   10.20.0.0/16
~~~

Before configuring:

- CIDRs **must not overlap** between the VPC and on-premises networks.
- Both sides advertise the right ranges and have **return paths**.
- Ingress/egress firewalls allow the **required protocols/ports**.
- The VPC's dynamic routing mode covers the regions of workloads and gateways.
- Check for more specific static/PBR routes that might alter the expected next hop.

Never accept a default route `0.0.0.0/0` from a peer casually: it can pull broad VPC traffic through on-premises unexpectedly, creating dependencies or network charges.

### 6.2. BGP Established Does Not Mean Packets Are Delivered

A BGP session in **Established** state proves two BGP peers can exchange routing updates. Yet TCP from a VM to a database also depends on:

1. Whether the dynamic route is installed and active in the VM's **region**.
2. Whether the VPN tunnel or VLAN attachment is actually forwarding data.
3. Whether enterprise routing has a path to the DB and a return path to the VPC.
4. Whether firewalls/ACLs/NAT and network policies permit the connection.
5. Whether the target service is running and listening on the required port.

With Partner Layer 3, BGP status on Cloud Router may reflect the session with the **provider**, not guaranteeing the last mile to the customer router is healthy.

### 6.3. Active/Active, Active/Passive, and Failover Capacity

| Pattern | Characteristics | Conditions to Check |
| --- | --- | --- |
| **Active/active** | Multiple paths used simultaneously when routes/priorities match; can use ECMP | Per-flow balancing, stateful firewalls, NAT, and capacity |
| **Active/passive** | One path preferred; secondary chosen when primary becomes unavailable | BGP advertisements/MED, failover detection, path-switch tests |
| **Multi-provider / multi-metro** | Reduces single-carrier or single-location risk | Physical path independence, hardware, and last-mile SLAs |
| **VPN backing up Interconnect** | IPsec over the Internet when private circuits fail | Sufficient capacity, matching prefixes/routing, security policy, and failback |

**Never choose a model by link count alone.** Multiple links sharing one router, one ISP, or one edge availability domain still share a common point of failure.

### 6.4. SLA Conditions Must Match the Topology

According to current documentation:

- **HA VPN:** qualifying topologies generally require **two tunnels across two interfaces** and matching peer configuration; some topologies qualify for 99.99%, others only 99.9% or no SLA.
- **Dedicated Interconnect:** **99.9%** and **99.99%** topologies have distinct requirements for connection counts, locations, edge domains, and VPC routing mode. For instance, the classic multi-region production topology uses at least **four connections across two metros**, spanning two edge domains; current documentation also provides a **single-region option** qualifying for 99.99% with specific connection/facility allocations.
- **Partner Interconnect:** production topologies typically use **four VLAN attachments** distributed across metros/edge domains and Cloud Routers per documentation; Google's SLA covers only the connection to the provider.
- **HA VPN over Interconnect:** SLA depends on the underlying Interconnect topology; a single attachment does not meet HA SLA requirements.

Never multiply individual service SLAs together and claim the result as an end-to-end application SLA. Verify **current commitments, exclusions, and scope** from Google, carriers, on-premises infrastructure, and workload SLOs.

## 7. Encryption and Security Responsibilities

| Mechanism | Where Does It Protect? | What Not to Infer |
| --- | --- | --- |
| **Cloud VPN IPsec** | Encrypts traffic between VPN gateways | Does not restrict users/apps on either side by itself |
| **Cloud Interconnect** | Private transport bypassing the public Internet | Does not encrypt payloads automatically |
| **MACsec for Cloud Interconnect** | Ethernet layer on supported link segments between router and Google edge | Does not automatically encrypt end-to-end inside Google or to applications |
| **HA VPN over Interconnect** | IPsec on traffic traversing Interconnect | Does not bypass pps/tunnel limits or HA topology requirements |
| **Application TLS/mTLS** | Secures application sessions between participating endpoints | Does not replace IAM, firewalls, or network controls |
| **Firewalls / IAM** | Network and identity access control, depending on service | Does not create transport paths or encrypt data |

For example, an ERP carrying sensitive data requires a private path and encryption: choose Dedicated/Partner Interconnect with **HA VPN over Interconnect**, or design end-to-end TLS/mTLS if compliant with policy. When using Partner, verify whether the segment inside the provider's network is encrypted end-to-end as required.

Beyond encryption, manage IPsec keys, project/network IAM permissions, organization policies, permissions to edit Cloud Routers/attachments, firewalls, logs, and DNS configurations. **Never commit shared secrets or keys into repositories or training materials.**

## 8. DNS in Hybrid Systems

This chapter is named **DNS and Hybrid Connectivity** because IP reachability alone is not enough for applications accessing internal services by domain name. Suppose a GCP API needs to call `db.corp.example`, which points to `172.16.20.10`:

- Routes and firewalls to the on-premises DNS resolver must exist if queries are forwarded to the enterprise network.
- **Cloud DNS forwarding zones** or supported inbound/outbound forwarding mechanisms can resolve names across VPCs.
- Enterprise DNS servers must be able to resolve GCP zones when bidirectional applications require it.
- Verify policies, forwarders, Cloud DNS query source IPs, and related network rules; never assume DNS queries go directly from every VM to on-premises DNS over one shared path.
- Successful DNS resolution **does not prove** TCP to the target IP succeeds; and a successful IP ping does not prove domain resolution works.

**Distinction:** DNS determines the **destination address**, while VPN/Interconnect and routing determine the **path to that address**. When troubleshooting, check sequentially: DNS lookup, IP route, firewall, TCP/TLS, and application.

Admin/hybrid connectivity in Shared VPC or Network Connectivity Center adds requirements around host/service projects, VPC attachments, route exchange, and DNS policies. Never assume a tunnel into one VPC automatically connects all other VPCs through it.

## 9. Costs: Compare Under Identical Load and Topology

### 9.1. Common Cost Components

- **Cloud VPN:** Cloud VPN tunnel/gateway fees per current pricing and data transfer; peer VPN appliances, ISP bandwidth, and management staffing.
- **Dedicated Interconnect:** physical ports/circuits, VLAN attachments, data transfer, colocation/cross-connects/routers/backhaul; rates vary by region and setup.
- **Partner Interconnect:** VLAN attachments, Google-billed data transfer, service provider fees, access circuits to the provider, and redundancy.
- **HA VPN over Interconnect:** Interconnect costs **plus** VPN component and operational costs; never estimate using Interconnect pricing alone.
- **Other services:** logging, monitoring, cloud egress generated by services, testing, and on-premises equipment.

Do not lump "data from VPC to on-premises," Internet egress, and provider charges into one generic unit rate. Pricing models and egress billing vary by product, location, capacity, and contract.

### 9.2. Example TCO Estimation Table

| Line Item | Details to Fill In |
| --- | --- |
| Demand | Peak Gbps, pps, TB/month, growth forecast |
| Architecture | HA VPN / Dedicated / Partner / Hybrid encryption |
| Link count | Number of tunnels, connections, VLAN attachments, and providers |
| Google resources | Fixed monthly fees and traffic fees |
| External resources | Circuits, appliances, colocation, support |
| Reliability | SLA topology, surviving paths after a failure, redundancy cost |
| Scalability | Cost and lead time to add bandwidth |
| TCO | Monthly/annual total, including peak scenarios |

With live data, you can use **Cloud Billing export to BigQuery** to reconcile network/hybrid costs and track changes after optimization. Always look up current prices at **Cloud VPN pricing** and **Cloud Interconnect pricing** when making decisions rather than hardcoding unit rates from a lesson.

## 10. A Practical Decision Process

Do not start with a product name. First classify **requirements**, then eliminate unsuitable options.

~~~mermaid
flowchart TD
  S["Need private connectivity between VPC and another network"] --> C{"Is the remote side another cloud?"}
  C -- "Yes" --> X["Evaluate Cross-Cloud Interconnect, partner cross-cloud, or HA VPN"]
  C -- "On-premises" --> B{"Need high, predictable bandwidth on a private path?"}
  B -- "Not yet" --> V["Evaluate HA VPN + BGP + 2 paths"]
  B -- "Yes" --> LOC{"Can reach Google colocation / backhaul?"}
  LOC -- "Yes" --> D["Evaluate Dedicated Interconnect"]
  LOC -- "No" --> P["Evaluate Partner Interconnect"]
  D --> ENC{"Need end-to-end IPsec encryption over the link?"}
  P --> ENC
  ENC -- "Yes" --> HV["Review HA VPN over Interconnect and tunnel limits"]
  ENC -- "No / handled otherwise" --> SEC["Check MACsec/TLS, IAM, firewalls"]
  V --> SLA["Calculate SLA topology and N-1 capacity"]
  HV --> SLA
  SEC --> SLA
  X --> SLA
  SLA --> T["Compare TCO and benchmark failover/latency/throughput"]
~~~

### 10.1. Starting Selection Rules

1. **Low-to-moderate traffic, fast setup, encryption needed:** start with **HA VPN**.
2. **High bandwidth, predictable transport, presence at Google colocation:** evaluate **Dedicated Interconnect**.
3. **Significant bandwidth without colocation presence, or flexible capacity tiers:** evaluate **Partner Interconnect**.
4. **Want both a private circuit and network-layer encryption:** examine **HA VPN over Interconnect** and multi-tunnel scaling.
5. **Multi-cloud connectivity:** evaluate **Cross-Cloud Interconnect**, partner options, or HA VPN based on specific topology.
6. **High-availability production:** design **SLA-compliant redundancy** from day one and test failover end-to-end; never leave a single tunnel/circuit as a single point of failure.

This is a **preliminary filter**. Final decisions require engineering review, pricing, supported regions, and security approval.

### 10.2. Suggested Scoring Matrix

A compact matrix avoids gut-feel choices:

| Criterion | Illustrative Weight | How to Evaluate |
| --- | ---: | --- |
| Meets peak throughput/pps | 25% | Testing or capacity planning |
| Availability and failover | 25% | SLA topology, path independence, measured RTO |
| Security/compliance | 20% | IPsec/TLS, locations, policies |
| TCO | 15% | Google + provider + hardware + operations |
| Deployment lead time | 10% | Circuits/paperwork/contracts/provisioning |
| Operations and scaling | 5% | Team skills, monitoring, automation |

Weights are **illustrative only**: a project with strict data rules can treat security as a mandatory gate before scoring. Any option failing a hard requirement must be disqualified regardless of total score.

## 11. Deployment Scenario: Java App Connecting to On-Premises ERP

### 11.1. Context

An enterprise has:

- Java services on Compute Engine and a Cloud Run backend API.
- Order data in Cloud SQL, while needing lookups against an ERP in the data center.
- On-premises network `172.16.0.0/16` and VPC `10.20.0.0/16`.
- Moderate current traffic with heavy spikes during sync windows; ERP must not be exposed to the Internet.
- Encryption required, redundancy needed, small ops team, and no colocation presence yet.

**Initial candidate:** HA VPN with dual-interface tunnel pair/BGP and appropriate dual peers. Reasons: provides IPsec, deploys faster than physical circuits, and supports qualifying HA topologies. However, measure peak Mbps/pps and simulate failures to validate before finalizing.

### 11.2. When Should the Decision Change?

Six months later, if data sync grows sharply, traffic stays continuously high, and a dedicated path is required, the team should compare **Partner Interconnect** (if providers offer suitable coverage) against **Dedicated** (once routers exist at colocation). If IPsec remains mandatory, plan **HA VPN over Interconnect** and size the number of tunnels by packet rate.

### 11.3. Sample Architecture Decision Record (ADR)

~~~text
Decision: HA VPN, two tunnels on two interfaces, BGP via Cloud Router
Workload: Java VM + Cloud Run accessing on-premises ERP
VPC: 10.20.0.0/16 ; On-premises: 172.16.0.0/16
Hard requirements: No public ERP; IPsec; redundant paths
Quantitative requirements: Peak throughput, pps, p95 latency, RTO on tunnel loss
Alternatives: Partner Interconnect, Dedicated Interconnect, HA VPN over IC
Current rationale: Moderate scale, no colocation yet, fast rollout needed
Assumptions: Peer supports BGP/IPsec; no CIDR overlap on either side
Risks: Internet jitter, peer gateway outage, MTU/MSS, failover dropping TCP
Verification: BGP routes, VPN tunnel status, Connectivity Tests, live app tests
Scale triggers: Throughput/pps hits ceiling, VPN TCO > private circuit option
Owner: Platform/Network/Security; next review date: ...
~~~

Populate real measurements, resource regions, and provider pricing/SLA citations before approving for production.

## 12. Read-Only Checks with Google Cloud CLI

This section is for **verification** after an authorized team deploys connectivity. The commands below do not create or delete infrastructure; replace placeholders with real IDs.

~~~bash
# Check the active project
gcloud config get-value project

# Inspect VPCs and subnets
gcloud compute networks list --project=PROJECT_ID
gcloud compute networks subnets list --project=PROJECT_ID

# Inspect HA VPN gateways and tunnels
gcloud compute vpn-gateways list --project=PROJECT_ID
gcloud compute vpn-tunnels list --project=PROJECT_ID

# Inspect status of a VPN tunnel in the right region
gcloud compute vpn-tunnels describe TUNNEL_NAME \
  --region=REGION --project=PROJECT_ID

# Inspect Cloud Routers and BGP sessions
gcloud compute routers list --project=PROJECT_ID
gcloud compute routers get-status ROUTER_NAME \
  --region=REGION --project=PROJECT_ID

# Inspect physical Interconnect links and VLAN attachments (if any)
gcloud compute interconnects list --project=PROJECT_ID
gcloud compute interconnects attachments list --project=PROJECT_ID

# Inspect an attachment in the right region
gcloud compute interconnects attachments describe ATTACHMENT_NAME \
  --region=REGION --project=PROJECT_ID
~~~

**Distinguish data scopes:** Cloud Router status shows BGP/learned/advertised route details, whereas resource list commands only confirm existence and metadata. Never infer "everything works" from a single resource status line.

Google Cloud VPC provides **Effective routes** in the Console to inspect usable routes, yet visible routes still must be cross-checked against **source, region, firewalls, return path**, and application health. For complex paths, use **Network Intelligence Center – Connectivity Tests** to simulate a trace where APIs/IAM and product limits permit.

### 12.1. Pre-Production Verification Checklist Table

| Check | Expected Evidence |
| --- | --- |
| Tunnel/circuit connectivity | Active status confirmed on both ends |
| BGP peers | Session Established, accurate learned/advertised prefixes |
| Network/VPC routing | VPC has routes to on-prem; on-prem has return routes |
| Redundancy | When one tunnel/circuit is unavailable, surviving path handles load |
| Firewalls | Only required protocols/ports open; logging per policy |
| Hybrid DNS | Internal service names resolve accurately from app origins |
| Performance | Throughput, packet rate, RTT, jitter, and loss measured |
| MTU | No large-packet blackholing; TCP MSS tuned if needed |
| Security | IPsec/TLS/MACsec per design, permissions, and key rotation |
| Cost | Monthly fixed costs, egress, provider/circuit, and logging tracked |

## 13. Common Troubleshooting

| Symptom | Possibilities to Check | Diagnostic Steps |
| --- | --- | --- |
| VPN tunnel stays down | Wrong peer IP, PSK/IKE/IPsec proposal, NAT-T, peer firewall | Check tunnel status and peer logs; compare both configs |
| VPN up but BGP not Established | ASN, BGP IPs, peer interface, route/access | Check `gcloud compute routers get-status` and peer config |
| BGP Established yet app times out | Missing route, return route, firewall, NAT, target service | Inspect Effective routes on both sides, Connectivity Tests, app logs |
| One tunnel failure breaks all connectivity | Single path or incomplete redundancy setup | Review HA VPN topologies and run live failover test |
| Low VPN throughput | 250k pps/tunnel limit, RTT/loss, MTU, peer CPU | Measure pps, packet sizes, multi-flow TCP, and gateway capacity |
| Interconnect attachment not passing traffic | Not activated, partner not provisioned, BGP unconfigured | Check attachment operational status and provider portal |
| Interconnect has bandwidth yet packet loss occurs | Overloaded device/circuit, shaping, link errors, failover saturation | Check port/attachment metrics and peer appliances |
| Private link works yet violates encryption policy | Interconnect lacks IPsec by default | Evaluate HA VPN over IC, MACsec/TLS per requirements |
| IP works, domain name fails | Hybrid DNS forwarding, resolver, zone, or DNS firewall | Trace DNS query path and corresponding policies |
| Wrong subnets advertised | Regional/global routing mode or custom advertisements | Inspect Cloud Router advertised/learned routes |
| Some TCP sessions drop on failover | ECMP/stateful appliances/NAT, BGP convergence | Test app retries and review stateful path design |
| Partner link fails in the last mile | Google SLA ends at provider network | Gather traces, check provider SLA, and open ticket at boundary |

### 13.1. MTU and MSS

IPsec adds headers/overhead; VLANs and encapsulation layers also affect MTU. A connection may pass small packets fine yet fail or hang on large payloads or certain handshakes. Common issues involve:

- Packet size exceeding usable payload MTU.
- ICMP "fragmentation needed" being blocked, breaking **Path MTU Discovery**.
- Different MSS/MTU settings applied on both sides after IPsec.
- Stacked encapsulations (such as IPsec over Interconnect) without accounting for overhead.

The fix is to read the **MTU specification for the exact product/topology**, check peer devices, and configure appropriate TCP MSS clamping/PMTUD. Never pick a "universal MTU for every VPN/Interconnect" without knowing IP version and ciphers.

### 13.2. Measuring from the Real Application

Measure latency to the ERP with real business requests rather than only pinging routers. For APIs executing many synchronous SQL queries, even a small RTT can multiply into high cumulative latency. When scaling bandwidth, test throughput across multiple streams, packet sizes, and peer gateway encryption CPU. When packet loss appears, check **both forward and return directions**.

**Failover tests** should record: which path was fault-injected, how long traffic took to recover, whether requests failed, throughput on the surviving path, whether the app retried safely, and whether costs changed. Verification tests may require maintenance windows and infrastructure approval; never drop production tunnels casually.

## 14. Decision-Making Practice (No Resources Required)

Build a decision matrix for the four requirements below. Use concepts from this lesson and official documentation; the goal is to **justify the selection conditions**, not guess product names.

| Scenario | Requirements | Initial Candidate |
| --- | --- | --- |
| **A. Hybrid lab** | Connect dev network to on-prem; a few hundred Mbps, little sensitive data yet IPsec mandatory, quick rollout | HA VPN |
| **B. High-volume data sync** | Continuous transfer, multi-Gbps peaks, routers at Google colocation, private path required | Dedicated Interconnect |
| **C. Remote branch** | No colocation, wants private path and scalable bandwidth under carrier contract | Partner Interconnect |
| **D. Financial data** | Requires private circuit, network-layer encryption, HA, and app calling on-prem ERP | HA VPN over Interconnect |

**Tasks:**

1. For each scenario, list **at least three conditions** to verify: bandwidth/pps, region, ISP, encryption level, SLA, and cost.
2. Define the **redundancy topology**: number of paths/tunnels/attachments per SLA docs, edge availability domains, and peer devices.
3. Map routes from GCP to on-prem and back; note where Cloud Router/BGP sits.
4. Pick at least **one alternative** and explain why it was not chosen first.
5. Create a test plan covering basic connectivity, DNS, MTU, throughput, failover, and logs.
6. Estimate Google, carrier/colocation, gateway, and operational costs over the same period.

**Hints:** Scenario A choosing HA VPN makes sense only if bandwidth/pps and peer readiness match. B may require multiple circuits to meet SLA rather than a single physical link. C must verify the provider ↔ enterprise segment SLA and bandwidth at the real site. D must ensure enough encrypted tunnels for capacity, because putting a single tunnel on a high-speed circuit creates a bottleneck.

### 14.1. Sample Decision Table Template

| Attribute | Option 1 | Option 2 |
| --- | --- | --- |
| Data and traffic | … | … |
| Path (Internet/private) | … | … |
| Encryption | … | … |
| Peak Gbps, pps | … | … |
| SLO/SLA and topology | … | … |
| Region/metro/provider | … | … |
| Deployment timeline | … | … |
| 12-month TCO | … | … |
| Failure points and redundancy | … | … |
| Test results | … | … |
| Conditional conclusion | … | … |

**Completion criteria:** You do not merely name the right product—you articulate **assumptions, documentation sources, verification measurements, and remaining risks**.

## 15. Self-Check Questions

1. **Is Cloud VPN a client VPN for laptops?** No. Cloud VPN provides site-to-site IPsec to peer networks.
2. **Does HA VPN use static routes like Classic VPN?** No. HA VPN uses dynamic BGP routing via Cloud Router.
3. **Does every HA VPN qualify for a 99.99% SLA?** No. Topology, tunnels, and peers must meet specific conditions; some topologies qualify for less or no SLA.
4. **What is the core difference between Dedicated Interconnect and Partner Interconnect?** Dedicated requires dedicated physical connections to Google at colocation; Partner goes through a supported service provider.
5. **Why doesn't Interconnect automatically satisfy encryption requirements?** Private circuits lack IPsec by default; appropriate IPsec/TLS/MACsec is needed.
6. **Does Cloud Router forward every packet?** No. Cloud Router manages BGP/control plane; the VPC data plane handles forwarding.
7. **Can one HA VPN tunnel saturate a 100 Gbps circuit?** No; per-tunnel packet-rate limits and IPsec overhead still apply.
8. **Does Google guarantee an end-to-end Partner Interconnect SLA all the way to the customer network?** Not automatically; Google's SLA covers up to the provider, so review the provider contract.
9. **Why must two connected networks avoid overlapping CIDRs?** Overlaps make routes ambiguous/conflicting and complicate hybrid design; renumber or apply intentional NAT solutions.
10. **Why is the return path critical?** TCP and request/response protocols require replies; a valid one-way route is not enough.
11. **When should Cross-Cloud Interconnect be used?** When the remote side is a network at another supported CSP and dedicated connectivity is appropriate.
12. **Why test failover under load?** The surviving path might lack sufficient bandwidth, or stateful apps might break even after BGP reroutes.

## 16. Pre-Design Finalization Checklist

- [ ] Identified VPCs/projects, regions, and CIDRs on both sides, with no overlap or a clear mitigation plan.
- [ ] Recorded peak Gbps, pps, TB/month, RTT/packet loss, and projected growth.
- [ ] Defined requirements for IPsec/TLS, sensitive data, and private transport.
- [ ] Compared HA VPN, Dedicated, Partner, and hybrid combinations where applicable.
- [ ] Verified colocation/metro/edge domain locations or provider coverage.
- [ ] Designed Cloud Router/BGP, advertised/learned prefixes, and return paths.
- [ ] Selected topology and SLA scope per current Google and provider documentation.
- [ ] Calculated surviving bandwidth upon single-link failure and target failover duration.
- [ ] Defined IAM, firewalls, DNS forwarding, NAT, and MTU/MSS.
- [ ] Estimated TCO including off-Google fees and operations.
- [ ] Prepared test plan, monitoring, alerting, runbooks, and rollback procedures.
- [ ] Recorded an ADR with assumptions, trade-offs, verification results, and next review date.

## 17. Official Google Cloud References

Re-read these documents at deployment time because capacities, pricing, SLA topologies, new features, and supported locations can change:

- [Choosing a Network Connectivity product](https://docs.cloud.google.com/network-connectivity/docs/how-to/choose-product) — workflow comparing Cloud VPN/Dedicated/Partner and general criteria.
- [Cloud VPN overview](https://docs.cloud.google.com/network-connectivity/docs/vpn/concepts/overview) — IPsec, HA/Classic VPN, throughput, limits.
- [HA VPN topologies](https://docs.cloud.google.com/network-connectivity/docs/vpn/concepts/topologies) — tunnel pairs and SLA per topology.
- [Cloud VPN best practices](https://docs.cloud.google.com/network-connectivity/docs/vpn/concepts/best-practices) — BGP, peer redundancy, and operations.
- [Cloud Interconnect overview](https://docs.cloud.google.com/network-connectivity/docs/interconnect/concepts/overview) — Interconnect types, security, throughput.
- [Dedicated Interconnect overview](https://docs.cloud.google.com/network-connectivity/docs/interconnect/concepts/dedicated-overview) — physical circuits, port capacities, and topologies.
- [Partner Interconnect overview](https://docs.cloud.google.com/network-connectivity/docs/interconnect/concepts/partner-overview) — providers, L2/L3, attachments, and SLAs.
- [Cross-Cloud Interconnect overview](https://docs.cloud.google.com/network-connectivity/docs/interconnect/concepts/cci-overview) — direct connectivity between cloud providers.
- [HA VPN over Cloud Interconnect](https://docs.cloud.google.com/network-connectivity/docs/interconnect/concepts/ha-vpn-interconnect) — IPsec, two-tier architecture, MTU/limits.
- [MACsec for Cloud Interconnect](https://docs.cloud.google.com/network-connectivity/docs/interconnect/concepts/macsec-overview) — Layer 2 encryption scope.
- [Cloud Router overview](https://docs.cloud.google.com/network-connectivity/docs/router/concepts/overview) — BGP/control plane and dynamic routing.
- [Dedicated 99.99% availability topology](https://docs.cloud.google.com/network-connectivity/docs/interconnect/tutorials/dedicated-creating-9999-availability) — single-region/multi-region requirements.
- [Cloud VPN troubleshooting/status](https://docs.cloud.google.com/network-connectivity/docs/vpn/how-to/checking-vpn-status) — inspecting tunnels and BGP.
- [Cloud VPN pricing](https://cloud.google.com/network-connectivity/docs/vpn/pricing) and [Cloud Interconnect pricing](https://cloud.google.com/network-connectivity/docs/interconnect/pricing) — check current pricing before calculating TCO.
- [Cloud DNS forwarding zones](https://docs.cloud.google.com/dns/docs/zones/forwarding-zones) — integrating hybrid name resolution.
- [Connectivity Tests](https://docs.cloud.google.com/network-intelligence-center/docs/connectivity-tests/concepts/overview) — verifying network paths by source/destination.

**Key takeaway:** **HA VPN** fits when IPsec is needed and traffic does not yet justify dedicated circuits; **Dedicated/Partner Interconnect** fits when private connectivity, higher bandwidth, or greater stability is needed; **HA VPN over Interconnect** combines private circuit benefits with IPsec encryption. The right decision rests on measured requirements, redundant topology, test results, and total operating cost.
