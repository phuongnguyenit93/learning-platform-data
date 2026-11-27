# Organizing Multi-Branch Connectivity with Azure Virtual WAN

An enterprise has three branch offices in Hanoi, Da Nang, and Ho Chi Minh City, an on-premises data center, and applications running on Azure. Each branch needs access to internal applications, certain services must pass through security inspection controls, and the enterprise wants to onboard new branches without rebuilding the entire network. Manually setting up multiple separate VPN gateways and point-to-point links between networks causes the number of connections, routing tables, and maintenance points to grow rapidly.

**Azure Virtual WAN** centralizes connectivity management for multiple branches, remote users, and Virtual Networks (VNets) into Azure-managed **virtual hubs**. This lesson explains how to design the topology, choose connectivity technologies, organize routing, enforce security, plan redundancy, and operate a multi-branch architecture with Virtual WAN.

This lesson belongs to the **Network Connectivity and Security** chapter of the `CLOUD_PROVIDERS_AZURE` module. The module introduces the Microsoft Azure ecosystem—from subscriptions, resource groups, and Microsoft Entra ID to virtual networks, compute services, storage, and data—while guiding how to deploy, monitor, secure, and control costs for an application architecture on Azure. With Virtual WAN, networking decisions must support availability, security, and cost control alike.

## 1. Learning Outcomes

After completing this lesson, you will be able to:

- Explain **Virtual WAN**, **virtual hub**, **VPN site**, **S2S VPN**, **ExpressRoute**, **P2S VPN**, and **VNet connection**.
- Select an appropriate model for an enterprise with multiple offices, multiple regions, or hybrid environments.
- Plan non-overlapping IP ranges for branches, hubs, application VNets, and on-premises networks.
- Design traffic paths for **branch-to-Azure**, **branch-to-branch**, and **VNet-to-VNet** flows using virtual hub routing.
- Describe how to combine Azure Firewall, routing intent, NSGs, and DNS to protect required flows.
- Plan link redundancy and monitoring aligned with SLAs and operational needs.
- Execute configuration, validation, and troubleshooting workflows at the architectural level or in an authorized lab.

## 2. What Is Virtual WAN?

Azure Virtual WAN is a networking service that provides centralized management of connectivity to and between network regions on Azure. You create a **Virtual WAN resource** to organize configuration at scale, then deploy one or more **virtual hubs** in the Azure regions you need to serve. Hubs act as connectivity points for branches, VNets, VPN users, and supported network services.

| Component | Function | Design Notes |
|---|---|---|
| **Virtual WAN resource** | Management resource for Virtual WAN, containing the virtual hubs. | An organizational container; not a VPN route or a traditional subnet. |
| **Virtual hub** | An Azure-managed regional connectivity hub providing routing and connectivity capabilities. | Requires its own address prefix, suitable region, and planned gateway/hub capacity. |
| **VPN site** | Represents an on-premises location and the links to its VPN devices. | Declares branch IP ranges, device metadata, public endpoints, and BGP if used. |
| **Site-to-site (S2S) VPN gateway** | Establishes IPsec/IKE tunnels between a branch or data center and the hub. | Verify device compatibility, tunnel parameters, bandwidth, and redundancy. |
| **ExpressRoute gateway** | Connects on-premises networks via an ExpressRoute circuit/provider into a virtual hub. | Consider provider availability, peering, bandwidth, and route propagation. |
| **Point-to-site (P2S) VPN gateway** | Connects remote users/devices into the hub. | Requires authentication configuration, client setup, and a client IP pool. |
| **VNet connection** | Attaches an application or infrastructure VNet to a virtual hub. | Verify IP overlaps, route tables, and workload security. |
| **Hub routing** | Controls learning, propagation, and path selection across connections. | Essential for transit and traffic segmentation. |

**A virtual hub differs from a regular VNet.** A hub is a service-managed networking resource with its own address space and connectivity capabilities. You do not treat a hub like a spoke VNet to attach VM NICs, arbitrarily create application subnets, or use standard VNet peering as with a normal VNet. Workloads should run in separate VNets, which then connect to the hub.

### Basic vs. Standard

Azure Virtual WAN offers options such as **Basic** and **Standard**, differing in the scope of connectivity scenarios:

| Requirement | Basic | Standard |
|---|---|---|
| Centralized S2S VPN to branches | Suitable for basic connectivity capabilities | Yes |
| Connecting VNets to hubs for complex enterprise topologies | More limited; do not choose Basic for multi-branch VNet transit designs | Yes |
| P2S VPN, ExpressRoute, inter-hub/VNet connectivity | Outside Basic scope | Supported per feature and configuration |
| Any-to-any transit routing and hub security models | Not an appropriate choice | Foundation used for advanced architectures |

For an enterprise requiring **branch ↔ application VNet, branch ↔ branch, multiple hubs, and centralized security**, **Standard Virtual WAN** is generally the appropriate choice. Verify support across target regions, SKUs, gateways, and current service limits before deploying to production.

## 3. Reading a Multi-Branch Architecture

Consider an enterprise with three branch offices, one data center, a Production application in Southeast Asia, and a disaster recovery environment in Japan East.

```text
                          On-premises
       ┌─────────────────┬──────────────────┬───────────────────┐
       │                 │                  │                   │
    Hanoi             Da Nang            HCMC             Data center
  10.41.0/20          10.41.16/20       10.41.32/20        10.42.0/16
       │                 │                  │                   │
       └──── S2S VPN ────┴────── S2S VPN ───┘                   │
                         │                                     │
                         │                           ExpressRoute (if used)
                         ▼                                     ▼
           ┌─────────────────────────────────────────────────────┐
           │              Virtual WAN (Standard)                 │
           │                                                     │
           │     Virtual Hub - Southeast Asia                    │
           │        Hub IP: 10.240.0.0/23                         │
           │          ├── S2S VPN gateway                        │
           │          ├── ER gateway (if used)                   │
           │          └── Hub router / route tables              │
           │                    │                                │
           │                    ├──── VNet Production            │
           │                    │      10.60.0.0/20              │
           │                    │                                │
           │                    └──── Virtual Hub - Japan East  │
           │                           10.240.2.0/23            │
           │                               │                     │
           │                               └── VNet DR           │
           │                                   10.61.0.0/20      │
           └─────────────────────────────────────────────────────┘
```

This is a logical diagram. Branches can use one or more Internet links/tunnels; ExpressRoute is a private carrier connection option rather than an Internet tunnel. Hub-to-hub paths, route propagation, and security policies must be configured and verified in practice to achieve the required transit flows.

**Meaning of the components:**

- **Branches** use router/firewall appliances supporting IPsec/IKE and can use BGP to exchange routes.
- **Virtual Hub Southeast Asia** serves as the entry point near Production applications, where connections and routes are managed.
- **VNet Production** hosts workloads (web/API, private databases, private endpoints) and attaches to the hub via a VNet connection.
- **Virtual Hub Japan East** supports the disaster recovery region or workloads in another region under a multi-hub model.
- **Data center** can use ExpressRoute or S2S VPN depending on goals, carrier availability, and budget.

The design benefit goes beyond reducing manual connection setup. The network team also gains a unified model to manage sites, routes, security, traffic visibility, and branch onboarding using a consistent template.

## 4. When Should You Choose Virtual WAN?

Virtual WAN is useful when you have many branches, need centralized connectivity management, combine VPN/ExpressRoute/P2S, or span multiple Azure regions.

Directional comparison:

| Criterion | Self-Managed Hub-and-Spoke VNet | Azure Virtual WAN |
|---|---|---|
| Central connectivity point | Hub VNet with gateways, routes, and components you manage more directly | Azure-managed virtual hub |
| Multi-branch integration | Create and operate gateways, sites, and peering/routes per architecture | VPN sites and hubs model for centralized organization |
| Multi-region transit | Design peering/gateways/routing per topology | Standard multi-hub model controlled via hub routing |
| Topology control | Flexible when customizing network appliance/hub VNet infrastructure | Integrated management capabilities within virtual hub constraints |
| Cost | Depends on gateways, appliances, peering, and data transfer | Includes hub, gateway, processing/traffic, and add-on service charges |

Not every organization needs Virtual WAN. A system with one VNet and one simple VPN link may not need this additional management layer. Base your decision on site count, region count, transit needs, security, operational capacity, and cost model.

## 5. Planning IP Addresses and Regions

**Address planning is the first step before creating any VPN or peering.** Prefixes advertised from branches, data center networks, application VNets, and hubs must be verified to be non-overlapping under the actual connectivity topology.

Illustrative IPAM table:

| Scope | Planned CIDR | Notes |
|---|---|---|
| Hanoi branch | `10.41.0.0/20` | Office LAN |
| Da Nang branch | `10.41.16.0/20` | Office LAN |
| Ho Chi Minh City branch | `10.41.32.0/20` | Office LAN |
| Data center | `10.42.0.0/16` | May contain actual sub-subnets |
| Virtual hub Southeast Asia | `10.240.0.0/23` | Dedicated prefix assigned to hub |
| Virtual hub Japan East | `10.240.2.0/23` | Does not overlap with the first hub |
| VNet Production | `10.60.0.0/20` | Primary workloads |
| VNet DR | `10.61.0.0/20` | Standby/DR workloads |
| P2S VPN pool (if used) | `10.250.0.0/22` | Dedicated pool for VPN clients |

These ranges are illustrative only; during implementation, check all VNets, sites, partner links, and network zones that may interconnect in the future.

### Why Must a Virtual Hub Have Its Own IP Range?

A virtual hub uses a dedicated IP range to operate its managed connectivity and routing components. The hub address space must be allocated per service requirements; it is **not** where you deploy application VM subnets.

Size the block based on the number and types of gateways, required integrations, and room for expansion. For example, `/23` can be a planning choice; minimum prefix requirements or changes to hub address space per service features must be checked against current documentation. Never pick an overly small range or share a range with another branch just to save IP addresses.

### Choosing Hub Regions

Place hubs in regions serving critical connectivity and workloads, while evaluating:

- Latency from branch users to applications.
- Where workloads run and regional DR plans.
- Regional availability of required gateway and security features.
- Cross-region data flows and associated transfer charges.
- Availability of ExpressRoute circuits/providers at the corresponding locations.

A hub in a region close to users **does not guarantee** the lowest latency for every flow; you still need to measure end-to-end path performance, especially when traffic traverses firewalls or another region.

## 6. Modeling Branches as VPN Sites

In Virtual WAN, a **VPN site** represents a physical connectivity location. When creating a site, you declare the details required for the links at that location, such as:

1. Site name, description, geography, or owning team.
2. Branch LAN prefixes to advertise.
3. Site VPN device metadata (vendor/model, where relevant).
4. Device public IP or endpoint, per ISP/link.
5. Expected link bandwidth and BGP configuration if used.
6. The virtual hub/gateway to which the site will connect.

A site can be modeled with multiple device/ISP links depending on supported connection types. This lets you represent a branch with redundant WAN links instead of maintaining disconnected entries for the same physical site.

### Static Routing or BGP?

| Mechanism | Advantages | Considerations |
|---|---|---|
| **Static** | Simple for small environments with few prefixes and infrequent changes. | When adding branches or changing prefixes, routes must be manually updated and retested. |
| **BGP** | Dynamic route exchange, suited to many prefixes and changing link states. | Requires preparing ASNs, BGP peers, route filters, device authentication/policies, and understanding route propagation. |

With many branches, BGP usually reduces manual route management overhead, but only works safely when routes are advertised accurately. Never arbitrarily advertise a broad supernet or a default route `0.0.0.0/0` without an agreed routing design.

### Preparing Branch Devices

Verify IPsec/IKE compatibility, cryptographic algorithms, NAT traversal, public endpoints, BGP support, and tunnel parameters against VPN gateway requirements. Confirm the ISP permits required traffic and that the appliance has sufficient encryption capacity for real throughput.

Tunnel/IPsec/IKE parameters and pre-shared keys must be handled via your organization's secrets management channels; never embed live keys in exercises, source code, or public tickets.

## 7. Choosing S2S VPN, ExpressRoute, or P2S

The three technologies address different access patterns:

### Site-to-Site VPN

**S2S VPN** establishes IPsec/IKE encrypted tunnels between an on-premises location and a VPN gateway inside a virtual hub over suitable transport networks, typically the Internet.

Best suited when:

- Branches have stable Internet connectivity and compatible VPN appliances.
- New sites must be onboarded quickly.
- A backup path is needed for a private dedicated link.
- Centralized management of VPN sites and tunnels is desired.

Factors to test: effective throughput after encryption, latency, packet loss, link and router failover behavior, route convergence, session count, and quality across dual ISPs.

### ExpressRoute

**ExpressRoute** uses a private connection through a provider into Microsoft's infrastructure. It suits data centers or sites with high bandwidth, stability, and private-network requirements.

Requires explicit design of circuits, peerings, and routes. ExpressRoute does not replace application-layer security controls and does not mean traffic is encrypted end-to-end in all cases. If organizational policy requires encryption, evaluate appropriate protection mechanisms.

### Point-to-Site VPN

**P2S VPN** connects remote users' laptops/devices into the Azure network infrastructure, unlike S2S VPN between two network sites.

Consider authentication type, certificates or Microsoft Entra ID per supported features, VPN client software, user address pool, split tunneling, and resource access permissions. P2S is usually an optional extension in a Standard architecture, not a mandatory component for interconnecting fixed branches.

### Selecting Technologies by Scenario

| Scenario | Typical Solution to Consider |
|---|---|
| 20 branches with dual ISPs needing access to Azure apps | S2S VPN via Virtual WAN with redundancy design |
| Data center requiring private connectivity to Azure | ExpressRoute, optionally paired with S2S VPN as backup |
| Remote employees on laptops | P2S VPN or an appropriate application access model |
| Multiple application VNets across regions | VNet connections and Standard multi-hub |
| Branches needing to exchange data through Azure | Appropriate hub routing and route propagation; verify transit paths |

## 8. Routing Inside a Virtual Hub

A VPN connection showing "Connected" or a tunnel showing "Up" **does not prove the application is reachable**. Traffic also needs forward and return routes, firewall controls, DNS, and workload-level policies.

In Standard Virtual WAN, the virtual hub uses routing constructs to connect different network connection types. Key concepts include:

- **Route table:** a collection of routes used to determine traffic forwarding paths.
- **Association:** defines which route table a connection uses when sending traffic into the hub.
- **Propagation:** defines which route tables receive the routes advertised by a connection.
- **Label:** a logical grouping name that helps manage propagation across multiple route tables.
- **Default route table:** the default routing table used in standard connectivity setups; verify actual configuration.
- **None route table:** an option to skip propagating routes in supported setups; should not be treated as the sole security measure.
- **Routing intent / routing policy:** a mechanism to direct categories of traffic such as private or Internet traffic through a supported security solution.

Route tables, labels, propagation, and routing intent have specific compatibility constraints. Never assume you can mix any routing option arbitrarily or override security behavior with a custom route table.

### Example Flows to Support

| Source | Destination | Requirement | Key Checks |
|---|---|---|---|
| Hanoi branch | `10.60.0.0/20` (Production) | Permitted, via inspection point if mandated | Route branch→hub→VNet; return route; firewall/NSG; DNS |
| Da Nang branch | Hanoi branch | Only approved services | Branch-to-branch transit, route propagation, segmentation policy |
| Data center | VNet Production | Private/stable connectivity | ExpressRoute/VPN, BGP, route preference, bidirectional security |
| VNet DR | VNet Production | Replication per app design | Inter-hub routing, required ports, latency, and cross-region traffic |
| VPN laptop | Internal app | Identity- and permission-based | P2S pool, authentication, routes, DNS, authorization |

### Branch → Application Traffic

For a packet from a machine in Hanoi to the private IP of a Production server:

1. The branch router selects the tunnel/path to Azure for prefix `10.60.0.0/20`.
2. The S2S VPN gateway at the hub receives the packet, and the hub router selects the route to the matching VNet connection.
3. If routing intent or centralized security is configured, the flow may be steered through the inspection point per policy.
4. The workload's NSG/firewall/host firewall decides whether the packet is allowed.
5. A return path must exist, satisfy stateful connection inspection, and avoid unintended asymmetric routing.

If only the forward route exists, ping or TCP will still fail. When using stateful inspection appliances, forward and return paths must be designed to avoid passing through different firewalls unless they share session state in a supported manner.

### Branch-to-Branch and Hub-to-Hub

In the Standard tier, Virtual WAN supports transit between connections and between virtual hubs within the scope of configured features. However, actual reachability depends on **association, propagation, routing policy, gateways, and security controls**. Never assume that connecting two branches to the same Virtual WAN means they can exchange traffic.

If the organization requires that **branches must not access each other directly**, design explicit route segmentation and firewall policies, and test that blocked flows are actually denied. Route isolation does not replace application-layer access controls.

## 9. Organizing Security in Virtual WAN

Virtual WAN brings networks into a consistent management model; **creating a hub alone does not automatically filter any traffic**. You must decide where and how to enforce security inspection.

### Secure Virtual Hub

You can pair Virtual WAN Standard with supported security services, such as Azure Firewall inside a **secured virtual hub**. In architectures using routing intent and routing policies, **private traffic** or **Internet traffic** flows can be steered through the integrated security control solution.

Conceptual diagram:

```text
Branch / VPN site
        │
        ▼
  VPN gateway at hub
        │
        ▼
  Hub routing / routing policy
        │
        ▼
  Firewall / security service (when configured)
        │
        ▼
  VNet workload → NSG/host policy → application
```

Routing through a firewall must be **configured and verified**; exact behavior depends on hub type, features, and security service. Do not treat the diagram above as the automatic path of every Virtual WAN.

### Control Layers

- **IPsec/IKE:** protects S2S VPN tunnels across suitable transport paths.
- **BGP and route policies:** control learned/advertised routes, preventing unwanted network propagation.
- **Azure Firewall or supported integrated NVA:** inspects flows requiring policy enforcement.
- **NSGs:** filter traffic at subnets/NICs within workload VNets.
- **Identity and authorization:** define which users, service principals, or workloads may use an application.
- **Private endpoints and DNS:** enable accessing PaaS services via private IPs when configured properly.
- **Logging/monitoring:** provide evidence for operations and security investigations.

Never create an `Allow Any Any` firewall rule just to test connectivity and leave it in Production. Specify exact source–destination pairs, protocols, ports, and business justification.

## 10. DNS When Multiple Branches Access Azure Applications

Successful IP connectivity still leaves an application unusable if domain names fail to resolve correctly. Many systems use private endpoints or internal names requiring cross-network DNS resolution.

For example, an application uses `api.internal.example` and an Azure SQL private endpoint. Branches need:

1. A route to the target IP inside the VNet or associated endpoint.
2. Internal name resolution via enterprise DNS or Azure DNS Private Resolver as designed.
3. DNS forwarding configured from on-premises sites to the appropriate resolver, if using that pattern.
4. Private DNS zones linked to the required VNets where supported.
5. Firewall/NSG rules and return paths verified for both DNS queries and application traffic.

**Virtual WAN does not replace an internal DNS design.** Having VPN tunnels and routes does not make private hostnames resolve automatically. Test both DNS queries and connectivity to the resolved IP.

## 11. Designing Redundancy and Resilience

A multi-branch architecture must account for failures in ISPs, on-premises hardware, VPN tunnels, gateways, hubs, and even application regions.

### Multiple ISP Links and Tunnels

Critical branches should evaluate:

- Two independent circuits or two ISPs whenever feasible.
- Redundant VPN appliances or site-level high availability.
- Multiple VPN site links/tunnels per service-supported models.
- BGP to detect and adjust routes during outages, combined with clear path preference policies.
- Testing whether dropping one ISP, one appliance, or one tunnel disrupts application sessions.

Do not assume "having two tunnels" makes the system resilient. If both depend on the same modem, fiber duct, power source, or router, a single point of failure still remains.

### Multi-Hub, Multi-Region

For workloads serving multiple geographies or requiring DR, deploy multiple virtual hubs and connect VNets in the corresponding regions. Define:

- Which branches prefer which hub during steady state.
- When a hub/region fails, which backup routes take over and who authorizes changes.
- Whether application and database services in the DR region are truly ready and data-consistent.
- Acceptable RTO/RPO and latency per application.
- Bandwidth capacity and cross-region transfer costs when traffic fails over.

**Multi-hub alone does not create application DR.** If the database or application only runs in one region, a redundant network path cannot keep the service running during a primary region outage.

### Failover Testing Procedure

1. Measure baseline latency, packet loss, throughput, and route states during normal operation.
2. Execute a controlled change in a maintenance/lab window, such as disabling one ISP link.
3. Observe BGP/tunnel states, route convergence, and application disruption duration.
4. Re-verify return paths, DNS resolution, TCP sessions, and results from branches.
5. Restore configuration and document recovery times, alerts triggered, and action items.

## 12. Deployment Workflow in the Azure Portal

A layered deployment sequence reduces misconfigurations and makes fault isolation easier.

### Phase A: Preparation

Gather the list of sites, local subnets, VPN devices, WAN/ISP IPs, BGP capabilities, bandwidths, regions, VNet addresses, security requirements, and application flow matrices. Select the subscription, resource group, regions, and admin permissions.

Draft the IP addressing table, allowed-flow matrix, failover plan, and budget before provisioning gateways that incur ongoing charges.

### Phase B: Create Virtual WAN and Hubs

1. Open [Azure Portal](https://portal.azure.com/) and navigate to **Virtual WANs**.
2. Create a Virtual WAN resource with the chosen subscription, resource group, name, and type **Standard** if the architecture requires advanced connectivity.
3. Create a **virtual hub** in the primary region with an approved dedicated CIDR space.
4. Select and deploy the hub VPN gateway with appropriate capacity for S2S VPN; add ExpressRoute/P2S gateways if actually used.
5. If needed, create a second hub in the DR region and design inter-hub connectivity.

Creating hubs and gateways can take significant provisioning time and incurs charges even with minimal traffic. Only deploy components approved in the architecture.

### Phase C: Declare Sites and Create S2S VPN Connections

1. Create **VPN sites** for Hanoi, Da Nang, and Ho Chi Minh City.
2. Enter LAN prefixes, device details, and links/public IPs.
3. Select the target virtual hub/VPN gateway, create VPN connections, and configure BGP if required by the model.
4. Download the Azure-provided configuration matching your VPN appliance or map parameters against vendor documentation.
5. Configure the branch appliances with matching tunnel and routing parameters.
6. Verify tunnels and BGP reach the expected state.

When using ExpressRoute, add steps to configure the circuit and link it to the ExpressRoute gateway. P2S requires separate user, authentication method, and VPN client configuration.

### Phase D: Connect VNets and Control Routing

1. Create or select the Production VNet with non-overlapping prefixes.
2. Create a VNet connection from that VNet to the virtual hub.
3. Define route table association and propagation for the connection.
4. Configure security policies / routing intent as designed if using a secured hub.
5. Verify routes between branches and VNets, between permitted branches, and to VNets in other regions.
6. Configure DNS and workload rules (NSGs/host firewalls).

### Phase E: Pre-Acceptance Testing

- Each branch reaches the application using the proper **hostname** and service port.
- Prohibited flows between branches or network segments are genuinely blocked.
- ISP/tunnel failover behaves according to procedure.
- Logs, metrics, and alert rules show observable signals.
- Observed bandwidth/latency and projected costs align with business requirements.

Do not treat "Connected" in the Portal as sufficient for sign-off; execute end-to-end application tests.

## 13. Inspecting Configuration with Azure CLI

After deploying via the Portal, Azure CLI helps inspect resources and feed operational workflows. The commands below are **read-only** and do not create gateways or tunnels. Substitute your actual resource group and subscription.

### Confirm Subscription

```bash
az account show \
  --query "{Subscription:id,Tenant:tenantId,Name:name}" \
  --output table
```

### List Virtual WANs

```bash
az network vwan list \
  --resource-group "rg-connectivity" \
  --output table
```

### List Virtual Hubs

```bash
az network vhub list \
  --resource-group "rg-connectivity" \
  --output table
```

### List VPN Sites

```bash
az network vpn-site list \
  --resource-group "rg-connectivity" \
  --output table
```

### Inspect a Specific Hub

```bash
az network vhub show \
  --resource-group "rg-connectivity" \
  --name "vhub-sea" \
  --output json
```

Configuration-listing commands do not prove traffic routes are working properly. To check link health, effective routes, gateways, and traffic, combine information from the Azure Portal, metrics, diagnostic logs, and monitoring tools on on-premises devices. Capabilities and flags for some advanced Virtual WAN commands depend on the Azure CLI version and extensions; check `az network ... --help` before automating.

## 14. Monitoring and Troubleshooting Connectivity

Areas to monitor include: **tunnel status**, **BGP routes**, **VPN/ER gateway metrics**, **hub routing**, **traffic/packet loss/latency**, **ISP/device health**, **DNS**, and **security logs**.

Common observation sources:

- **Virtual WAN**, **Virtual hub**, **VPN site**, and **VPN connection** blades in the Portal.
- **Azure Monitor metrics** and alerts for supported gateways/services.
- **Diagnostic settings/logs** sent to Log Analytics, Storage, or Event Hubs depending on feature support.
- **Effective routes** or virtual hub route views (subject to Portal/API availability).
- Logs, BGP/IPsec states, and ISP metrics on branch routers/firewalls.
- DNS, TCP/HTTPS, and application monitoring tests between source and destination.

### Troubleshooting Table

| Symptom | Common Causes | How to Isolate |
|---|---|---|
| S2S tunnel does not come up | Wrong public IP, IKE/IPsec mismatch, wrong shared key, NAT, or ISP block | Compare parameters on both ends, check device and VPN gateway logs |
| Tunnel up but app unreachable | Missing route, missing return route, NSG/firewall block, or wrong DNS | Inspect effective routes; test from source to IP first, then hostname |
| One branch connects, another cannot | Different site prefix/BGP propagation or segmentation policy | Compare configurations of both sites and associated route tables |
| Reachable by IP but not by hostname | Missing DNS forwarding, private zone link, or wrong record | Query DNS directly from the branch machine; inspect resolver |
| Traffic detours through unexpected region | Misconfigured association/propagation or route preference | Inspect hub routes, BGP advertisements, and routing policy |
| Losing one ISP drops the whole branch | Missing backup link/tunnel or BGP failover fails to converge | Test backup link and inspect BGP peer state |
| App times out while VPN stays green | Capacity exhaustion, packet loss, firewall state, or workload fault | Measure traffic, latency, gateway metrics, app, and firewall |
| Unexpected branch-to-branch access | Overly broad route propagation or missing segmentation policy | Inspect route table association/propagation and security policies |

### Rapid Investigation Workflow

1. **Define scope:** which site, which hostname/IP, which port, since when, and which traffic type.
2. **Check transport:** ISP/device health, tunnel status, BGP, gateway health.
3. **Check bidirectional routes:** source–destination prefixes and return path, hub route tables, advertised routes.
4. **Check security:** Azure Firewall/NVA, NSGs, on-premises ACLs, host firewalls.
5. **Check DNS:** resolve hostnames from an actual branch machine.
6. **Check recent changes:** site links, routes, policies, VNet connections, or firmware.
7. **Capture evidence:** request timestamps, IPs, routes, logs, alerts, and recovery time.

## 15. Cost and Operational Governance

Virtual WAN reduces the effort of managing many individual gateways, but you must **estimate costs across the full architecture**. Cost components can include:

| Category | Cost Drivers |
|---|---|
| Virtual hubs | Count, tier/features, and uptime duration |
| VPN/ExpressRoute/P2S gateways | Provisioned capacity, gateway scale units, duration, and connection types |
| Data transfer/routing | Traffic between sites, VNets, hubs, regions, and associated processing charges |
| ExpressRoute | Circuit/provider, bandwidth, and selected billing model |
| Azure Firewall / security solutions | Security services and volume of traffic processed |
| Log Analytics and monitoring | Ingestion volume, retention, alerts, and storage |

There is no single fixed price applicable to every Virtual WAN. Before deploying, use the **Azure Pricing Calculator** and current carrier/provider quotes to estimate based on hub count, site links, gateway capacity, monthly traffic, and security services. Pay particular attention to **additional hubs in DR regions** and **cross-region data transfer**.

### How to Organize Governance

Establish and maintain:

- **Site inventory table:** site owner, ISP, appliance, firmware, public endpoint, subnets, BGP ASN.
- **IPAM table:** CIDRs for hubs, VNets, sites, P2S pools, and reserved prefixes.
- **Connectivity matrix:** source, destination, port, firewall inspection requirement, approving team.
- **Runbooks:** standard device config, tunnel-down handling, route changes, rollback, and failover.
- **Monitoring baseline:** tunnel uptime, packet loss, RTT, throughput, route stability, and app health.
- **Change management process:** admin RBAC, pre/post route validation, and change logs.

In organizations with multiple subscriptions or operations teams, define clear ownership for who manages hubs, who manages VPN sites, who approves security policies, and who operates each VNet/workload.

## 16. Hands-On Exercise: Designing Virtual WAN for Three Branches

**Scenario:** An enterprise has three offices in Vietnam and two applications in two Azure regions. All offices need access to the Production application, but only Hanoi and Ho Chi Minh City are allowed to access business systems hosted at each other's offices. The on-premises data center uses an ExpressRoute connection. Each branch has two Internet links.

Assumed details:

| Component | Parameters |
|---|---|
| Hanoi | `10.41.0.0/20`, dual ISPs |
| Da Nang | `10.41.16.0/20`, dual ISPs |
| Ho Chi Minh City | `10.41.32.0/20`, dual ISPs |
| Data center | `10.42.0.0/16` |
| Primary hub Southeast Asia | `10.240.0.0/23` |
| Standby hub Japan East | `10.240.2.0/23` |
| VNet Production | `10.60.0.0/20` |
| VNet DR | `10.61.0.0/20` |

### Tasks

1. Choose the Virtual WAN tier suitable for S2S VPN, ExpressRoute, VNet connections, and multi-hub.
2. Draw a diagram covering both hubs, three sites, the data center, and both application VNets.
3. Verify that all CIDRs are non-overlapping and select the primary hub by region.
4. Describe the VPN site and dual links for each branch; specify whether BGP is used.
5. Write the connectivity matrix: branches → Production, data center → Production, Hanoi ↔ Ho Chi Minh City, Da Nang ↔ Hanoi (prohibited).
6. Describe route association/propagation to support permitted paths and firewall controls to block prohibited paths.
7. Explain how internal hostnames and private endpoints are resolved via DNS.
8. Propose ISP/tunnel/hub failover strategies and how to verify the application stays healthy.
9. Build a list of logs, metrics, alerts, and budget items to track.

### Reference Solution

**Choice:** **Standard** Virtual WAN because multiple connection types, VNet transit, and multi-hub capabilities are needed. In a real deployment, verify gateway and security feature support in the selected regions.

**Primary paths:** the three VPN sites use S2S VPN into the Southeast Asia hub; the data center connects to the hub via an ExpressRoute gateway; VNet Production connects to the primary hub, and VNet DR connects to the Japan East hub. Inter-hub routing is verified for DR traffic per design.

**Routing and segmentation:** branches advertise non-overlapping prefixes; routes to Production are propagated to the required connections. The Hanoi ↔ Ho Chi Minh City path is allowed only via routing policy and security inspection. Da Nang ↔ Hanoi is denied using route segmentation and corresponding firewall policies. Do not rely on route isolation alone as a sufficient security control if applications hold sensitive data.

**Availability:** each site has redundant links, monitors tunnel status and BGP routes, and tests single-ISP failures. VNet DR and application DR must be prepared independently of routing; during a primary region outage, verify both the application and data layers.

**Acceptance criteria:**

- All three branches reach the Production application by **hostname** and the right port.
- Hanoi and Ho Chi Minh City communicate only for approved services.
- Da Nang cannot reach prohibited internal Hanoi subnets/services.
- Losing one Internet circuit does not break total connectivity beyond acceptable recovery time.
- Evidence exists for forward/return routes, BGP, firewall logs, and DNS.
- The cost sheet accounts for hubs, gateways, data processing, ExpressRoute, security, and logs.

## 17. Self-Check Knowledge

**Question 1.** Why do enterprises with many branches and VNets across multiple regions typically choose Virtual WAN Standard?

A. Because Basic includes all connection types and hub-to-hub transit by default.  
B. Because Standard supports VNet connections, multi-hub topologies, and advanced connection types as configured.  
C. Because Standard makes all firewall rules unnecessary.

**Answer: B.** Standard supports more complex topologies, though routing and security still must be designed properly.

**Question 2.** Which Virtual WAN resource represents a branch including its LAN subnets and ISP links?

**Answer:** **VPN site**. Branch links and prefixes are declared as part of the site model.

**Question 3.** An S2S tunnel is up, but staff cannot access the application by hostname. What should you check?

**Answer:** Bidirectional routes, BGP/association/propagation, firewalls/NSGs, and especially **DNS** at the branch; tunnel status alone does not guarantee application access.

**Question 4.** Two sites have prefixes `10.41.0.0/20` and `10.41.8.0/21`. What is wrong with this design?

**Answer:** The two ranges overlap because `10.41.8.0/21` falls inside `10.41.0.0/20`. Re-plan addressing or implement an explicit resolution before routing.

**Question 5.** When using ExpressRoute, can you assume data is always encrypted end-to-end like an IPsec VPN?

**Answer:** No. ExpressRoute is a private connection via a provider; encryption must be evaluated independently according to security requirements.

**Question 6.** Are two branches connected to the same Virtual WAN guaranteed to reach each other directly?

**Answer:** No. That depends on routing, propagation, association, and security policies. Configure properly and test both permitted and denied flows.

**Question 7.** If you have two tunnels but both pass through a single physical router, what risk remains?

**Answer:** The router is a single point of failure. Evaluate redundancy across hardware, ISPs, power, and physical paths rather than tunnel count alone.

**Question 8.** Is a second virtual hub in another region enough to guarantee application DR?

**Answer:** No. You also need redundant workload/data layers, synchronization planning, RTO/RPO targets, DNS handling, and actual failover mechanisms.

Virtual WAN helps enterprises **organize multiple branches under a centrally manageable connectivity architecture**. To operate reliably, engineering teams still must design non-overlapping addressing, bidirectional routes, security segmentation, DNS, redundancy, and traffic telemetry. The service's value becomes clearest when onboarding a new branch under the same standards while keeping paths, access scope, and costs under control.
