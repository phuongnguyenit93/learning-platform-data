# Designing Network Appliances and Traffic Inspection Routing

An application on Microsoft Azure may consist of multiple Virtual Networks (VNets): a web frontend VNet, a business services VNet, a data VNet, and a shared platform VNet. When these networks need to communicate, **VNet peering** provides private IP connectivity, yet it does not automatically ensure that flows are **inspected by a firewall or security appliance** before reaching their destination.

In the **Network Connectivity and Security** chapter of the **CLOUD_PROVIDERS_AZURE** module, this lesson focuses on designing **Network Virtual Appliances (NVAs)** and **traffic inspection routing**. The objective is to understand packet paths, use route tables/UDRs to steer inspected flows through the appliance, preserve symmetric return paths without disrupting applications, and know how to monitor, troubleshoot, and estimate costs.

Running example: the Orders application is deployed in Azure with two spoke VNets and one hub VNet. The security team wants traffic between the two spokes to traverse a firewall/NVA in the hub to enforce policy and log flows, rather than letting the spokes communicate directly outside the inspection point.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain network appliances, NVAs, Azure Firewall, and traffic inspection layers.
- Distinguish **north–south** flows, **east–west** flows, and the purpose of **service insertion**.
- Explain how VNet peering, **User Defined Routes (UDRs)**, Network Security Groups (NSGs), IP forwarding, and firewall policies work together.
- Design **forward and return** paths through an inspection appliance, understanding stateful inspection and asymmetric routing.
- Draw a hub–spoke diagram with non-overlapping CIDRs, a source–destination–port flow matrix, and deliberate routes.
- Create route tables and routes, associate subnets, and inspect effective routes using Azure CLI.
- Evaluate high availability (HA), scalability, logging, DNS, and NVA costs.
- Diagnose cases where peering is Connected yet traffic is blocked, bypasses the firewall, or flows only one way.

## 2. What Is a Network Appliance?

A **network appliance** is a component that processes traffic at the network, transport, or application layer. On Azure, an appliance can be a VM running third-party router/firewall software, or a managed network service like Azure Firewall in an architecture serving equivalent functions in key respects.

Common tasks include:

| Task | Example | Key Considerations |
|---|---|---|
| Traffic filtering | Allow app spoke to call data spoke only on TCP/443 | Rules must specify exact source, destination, port, and direction |
| Outbound control | Restrict workloads to approved endpoints only | Default routes must send traffic to the firewall with a valid egress path |
| Stateful firewall | Track TCP/UDP session state | Forward and return paths must not cross two independent nodes lacking state sync |
| IDS/IPS | Detect or block malicious behaviors | Requires signature updates, log retention, and false-positive management |
| NAT/SNAT/DNAT | Translate addresses/ports as required | NAT can hide original source IPs in logs or affect connections |
| Routing | Forward packets between subnets/VNets | The NVA must actually enable forwarding and hold routes to destinations |
| Application control | Process traffic at the application layer per product | Cannot inspect TLS-encrypted payloads by default |

**NVA** commonly refers to an appliance deployed on Azure VM infrastructure. An NVA may run a firewall, router, proxy, or SD-WAN solution managed by the customer or software vendor. **Azure Firewall** is an Azure-managed firewall service; it does not require you to manage VM operating systems as with a traditional NVA.

A system with an NVA on a diagram but no routes steering traffic through it **does not actually perform traffic inspection**.

### 2.1. Choosing Tools by Protection Scope

- **NSGs:** L3/L4 filtering on NICs or subnets by rule; effective for segmenting and constraining flows. NSGs do not replace a centralized firewall with advanced logging and controls.
- **Azure Firewall:** managed firewall service typically placed in a hub to enforce network/application rules and logging according to the selected SKU.
- **Third-party NVA:** used when specific features, policies, integrations, appliance chaining, or operations match organizational standards; customers must manage HA, patching, licensing, and throughput.
- **Web Application Firewall (WAF):** focuses on HTTP/HTTPS protection at the application layer; not a general traffic router across all protocols.
- **Azure DDoS Protection:** enhances defense against denial-of-service attacks within supported scope; does not replace per-connection rule inspection.
- **Azure Virtual WAN / Secured virtual hub:** an architectural option for large multi-connection environments; routing and security mechanics differ from self-managed NVAs.

Only introduce an NVA when specific requirements cannot be met cleanly by managed services or built-in controls. Adding an inline appliance introduces extra dependencies, latency, cost, and operational overhead.

## 3. Traffic Types Requiring Inspection

First, classify flows by direction and trust boundaries:

### 3.1. North–South

**North–south traffic** generally refers to traffic entering or leaving a network zone from outside:

- Internet users accessing web applications.
- Workloads accessing the Internet to fetch dependencies or call external APIs.
- On-premises networks accessing Azure systems via VPN Gateway or ExpressRoute.

Inbound Internet traffic may use Azure Front Door, Application Gateway/WAF, Load Balancer, a firewall, or other appliances depending on architecture. Outbound Internet traffic is typically governed by default routes, egress firewalls, DNS policies, and SNAT/egress mechanisms.

### 3.2. East–West

**East–west traffic** refers to flows between internal resources and network zones:

- An API in spoke A calling a data service in spoke B.
- A management VM in the hub accessing a workload in a spoke.
- Microservices in one VNet communicating with microservices in another via peering.

Not every east–west flow needs to traverse a centralized firewall. Base inspection decisions on data sensitivity, trust boundaries, compliance, throughput, latency, and cost.

### 3.3. Flow Policy Table Before Writing Routes

Example for the Orders application:

| Source | Destination | Port/Protocol | Requirement | Policy |
|---|---|---|---|---|
| Spoke-app 10.10.1.0/24 | Spoke-data 10.20.1.10 | TCP/443 | Mandatory inspection | Allow with logging via NVA |
| Spoke-data 10.20.1.0/24 | Spoke-app 10.10.1.0/24 | Arbitrary new connections | Not needed | Deny per firewall policy |
| Spoke-app | Approved external API | TCP/443 | Egress control | Route through egress firewall as needed |
| Operations workstation | NVA management interface | HTTPS/SSH per design | Ops team only | Restrict source and RBAC |
| Spoke-app | Internal DNS resolver | TCP/UDP 53 per system | Must work | Allow per DNS flow |

This table describes **permitted connection initiations**, not that reply packets for a valid session should be blocked. With stateful inspection, the firewall must see both directions of a session to make consistent decisions.

## 4. Reference Architecture: Hub–Spoke with NVA

Design three VNets with **non-overlapping** IP ranges:

| VNet | CIDR | Resource Group | Role |
|---|---|---|---|
| vnet-security-hub | 10.0.0.0/16 | rg-security-hub | Hosts NVA and shared network services |
| vnet-orders-app | 10.10.0.0/16 | rg-orders-app | Hosts API/app workloads |
| vnet-orders-data | 10.20.0.0/16 | rg-orders-data | Hosts data services or backends |
| snet-nva in hub | 10.0.1.0/24 | inside hub VNet | NVA with illustrative private IP 10.0.1.4 |
| snet-app in spoke A | 10.10.1.0/24 | inside spoke A | Application resources |
| snet-data in spoke B | 10.20.1.0/24 | inside spoke B | Target services |

Traffic path diagram:

~~~mermaid
flowchart LR
    A["Spoke A – Orders App<br/>10.10.0.0/16"]
    H["Hub VNet<br/>10.0.0.0/16"]
    F["NVA / Firewall<br/>10.0.1.4"]
    B["Spoke B – Data<br/>10.20.0.0/16"]
    A <-->|"Peering A–Hub"| H
    H <-->|"Peering Hub–B"| B
    H --- F
    A -. "UDR dest 10.20.0.0/16" .-> F
    B -. "UDR dest 10.10.0.0/16" .-> F
~~~

**The two dashed arrows represent next-hop intent**, not a direct Layer 2 link from spoke to NVA. Routes on each spoke specify the NVA's private IP as the next hop; actual packets traverse peering into the hub and are forwarded by the NVA to the target spoke per configured routing.

Do not create direct peering between A↔B if policy requires traffic to traverse the hub inspection point, unless bypass prevention has been explicitly analyzed. Peering is **non-transitive**: A peering with hub and B peering with hub does not automatically create an A→B route; the NVA combined with UDRs and forwarding settings provides transit.

### 4.1. Forward and Return Paths

Suppose source machine **10.10.1.10** in spoke A calls service **10.20.1.10:443** in spoke B:

1. The source subnet has UDR: **10.20.0.0/16 → Virtual appliance 10.0.1.4**.
2. Azure sends the packet from spoke A to the hub over the peering associated with that next hop.
3. The NVA receives the packet, applies firewall policy, and forwards it to **10.20.0.0/16** over the hub–spoke B peering.
4. The destination server replies to **10.10.1.10**.
5. The destination subnet has UDR: **10.10.0.0/16 → Virtual appliance 10.0.1.4**.
6. The NVA inspects the session's return traffic and forwards it back to spoke A.

If the return UDR is missing, reply packets may be dropped for lack of a transit route, or take a different path in a more complex topology. With a **stateful firewall**, forward and return traffic hitting two nodes without shared state can break the session even when network reachability exists in both directions.

### 4.2. Single-Spoke and Internet Scenario

When inspecting only Internet egress, an application subnet may use a default route:

~~~text
0.0.0.0/0 → Virtual appliance → 10.0.1.4
~~~

In that case, the NVA or Azure Firewall must have a **valid Internet egress path**, perform NAT per the architecture, and permit required services. Pointing a default route to a VM that lacks forwarding/egress capability breaks all outbound connectivity.

A default route has wide blast radius; avoid using it in an initial lab when you only intend to inspect A→B traffic.

## 5. Routing Rules and How UDRs Take Effect

Azure uses **system routes**, can learn routes advertised via gateways/BGP where supported, and allows configuring **User Defined Routes (UDRs)** inside route tables.

A subnet can associate with one route table containing multiple routes. When choosing a path, Azure evaluates destination prefixes and route types per platform rules. Key rules to remember:

- **Longest-prefix match** takes precedence. A specific `/24` route beats a `/16` or `0.0.0.0/0` route.
- For identical prefixes, UDRs generally override gateway/BGP routes and system routes, subject to platform exceptions.
- A UDR with next hop **Virtual appliance** sends traffic to your specified IP, but **does not make that appliance forward packets automatically**.
- A UDR on one subnet does not automatically apply to every subnet in the VNet. Verify exact subnet associations.
- NSGs and Azure Firewall policies are evaluated independently of route selection. Having a route to a destination does not mean policy allows the traffic.

Common next-hop types:

| Next Hop | Typical Meaning |
|---|---|
| Virtual network | Internal route managed by Azure within the network space |
| Virtual network peering | System route to a peered VNet's prefix |
| Virtual network gateway | Path via VPN/ExpressRoute gateway when configured |
| Virtual appliance | Forwards to an NVA private IP or supported receiver |
| Internet | Exits to the Internet per platform mechanisms and configuration |
| None | Drops packets matching that route prefix |

**Note:** the next-hop type displayed in **effective routes** may be worded slightly differently from the parameter accepted when creating a UDR. When creating a custom route to an NVA, pass **VirtualAppliance** and **next-hop-ip-address** per Azure CLI syntax.

### 5.1. Example Route Table

In the A–hub–B model:

| Route Table Attached To | Address Prefix | Next-Hop Type | Next-Hop IP |
|---|---|---|---|
| snet-app, spoke A | 10.20.0.0/16 | Virtual appliance | 10.0.1.4 |
| snet-data, spoke B | 10.10.0.0/16 | Virtual appliance | 10.0.1.4 |

This ensures only the selected prefixes are deliberately steered through the NVA. If other flows require inspection, add routes matching your traffic matrix after reviewing impacts and existing effective routes.

### 5.2. UDRs Do Not Replace Network Planning

Before authoring routes:

1. Verify the two VNets do not have overlapping address spaces.
2. Confirm hub↔spoke peerings are all **Connected**.
3. Confirm forwarded traffic across peering is configured for the intended flows.
4. Confirm the NVA holds the right static private IP and is running cleanly.
5. Check for broader routes (such as default routes).
6. Confirm NSGs and firewall policies permit required flows.
7. Account for return paths and NAT if present.

## 6. Peering and Forwarded Traffic

In a hub–spoke model, bidirectional peering is required between the hub and each spoke, with appropriate forwarding options. **Allow forwarded traffic** controls whether peering accepts traffic forwarded by an appliance from the peer side; it neither creates routes nor enables forwarding inside the NVA.

Items to verify:

- **Hub ↔ Spoke A** has both peering links pointing to the right remote VNets.
- **Hub ↔ Spoke B** has both peering links pointing to the right remote VNets.
- **Allow virtual network access** permits required direct flows per design.
- **Allow forwarded traffic** is enabled on the peering directions that must accept forwarded traffic via the NVA.
- Any **gateway transit / use remote gateways** settings have explicit justification rather than being enabled blindly.

Example peering check with Azure CLI:

~~~bash
az network vnet peering list \
  --resource-group rg-security-hub \
  --vnet-name vnet-security-hub \
  --query "[].{name:name,state:peeringState,allowVnet:allowVirtualNetworkAccess,forwarded:allowForwardedTraffic,remote:remoteVirtualNetwork.id}" \
  --output table
~~~

If peering exists on only one side, its state will not show **Connected**. If traffic fails to transit the hub, inspect the peering configurations on both spokes as well, not just on the hub.

**Do not enable forwarded traffic on links that do not need it**; it permits broader transit behavior and must be paired with reviewed filtering and routing rules.

## 7. Specific Requirements for VM-Based NVAs

A self-managed NVA is typically a VM with one or more network interfaces. To forward traffic properly, you must configure **two layers**:

1. **Azure NIC IP forwarding:** allows the network interface to receive/forward packets whose source or destination IP does not match the NIC's own IP, as required by an NVA.
2. **Operating system or appliance software:** enable kernel routing/IP forwarding, packet processing/firewall rules, interface policies, and internal routes.

Enabling forwarding only on the Azure NIC while forgetting the guest OS causes packets to be dropped. Enabling forwarding in the OS while leaving Azure NIC IP forwarding disabled also prevents traffic from flowing as intended.

### 7.1. Example: Enabling IP Forwarding on an Azure NIC

Example for an **NVA authorized to act as a router** (never apply automatically to ordinary app VMs):

~~~bash
az network nic update \
  --resource-group rg-security-hub \
  --name "<nva-nic-name>" \
  --ip-forwarding true
~~~

Check status:

~~~bash
az network nic show \
  --resource-group rg-security-hub \
  --name "<nva-nic-name>" \
  --query "{name:name,ipForwarding:enableIPForwarding,privateIPs:ipConfigurations[].privateIPAddress}" \
  --output json
~~~

On Linux, you can run a **read-only** command to check IPv4 forwarding:

~~~bash
sysctl net.ipv4.ip_forward
~~~

If the output is **0**, the host kernel has not enabled IPv4 routing. Persistent configuration, guest OS firewall rules, and multi-NIC setups depend on the NVA image/software. Never enable forwarding on a machine not configured as a router with proper controls.

### 7.2. Private IP and Next-Hop Address

The next-hop IP must be a **reachable** address in the network belonging to the NVA configuration or a service-supported next-hop endpoint. This lab illustrates **10.0.1.4**, but never assume that IP is already assigned to your VM. Check the NIC's IP and configure static private IP assignment via supported methods before pointing UDRs at it.

With an **HA solution via Internal Load Balancer (ILB)**, architectures may use the load balancer's frontend IP as the traffic receiver using HA ports supported by Azure and the NVA vendor. Never point a UDR next hop at an arbitrary load balancer frontend without verifying architectural support, probes, flow symmetry, and failover behavior.

### 7.3. Distinguishing Forwarding, NAT, and Proxy

- **Forward/routing:** the NVA routes packets between networks, typically preserving original IP addresses.
- **SNAT:** rewrites source IP/port; can simplify return paths but obscures original client IPs at the destination unless logged.
- **DNAT:** rewrites destination IP/port, commonly used for inbound publishing.
- **Proxy:** the client connects to the proxy, which opens a separate connection to the destination; involves protocol and TLS semantics distinct from pure packet forwarding.

Never enable NAT merely to paper over a routing mistake without understanding its impact on auditing, security policies, and application behavior.

## 8. Hands-On: Routing Traffic A → NVA → B with Azure CLI

**Assumptions:** VNets, subnets, peerings, and the NVA are already deployed per design and the NVA is operational; the subscription and resource groups are valid; both peerings permit forwarded traffic in the required directions. This exercise demonstrates creating UDRs and attaching them to subnets only. These commands alone do not create firewall policies or guarantee the NVA is ready.

Run only in an **approved sandbox/lab**. Attaching a route table immediately alters network paths for every machine in a subnet, so never run these commands in production without a change plan and rollback steps.

### 8.1. Prepare Variables and Verify Networks

Commands use **Bash** syntax in Azure Cloud Shell or a shell with Azure CLI:

~~~bash
az login
az account set --subscription "<subscription-id>"
az account show --output table

APP_RG="rg-orders-app"
DATA_RG="rg-orders-data"
APP_VNET="vnet-orders-app"
DATA_VNET="vnet-orders-data"
APP_SUBNET="snet-app"
DATA_SUBNET="snet-data"
NVA_IP="10.0.1.4"

# Inspect address spaces of both VNets
az network vnet show \
  --resource-group "$APP_RG" \
  --name "$APP_VNET" \
  --query "{name:name,prefixes:addressSpace.addressPrefixes}" \
  --output json

az network vnet show \
  --resource-group "$DATA_RG" \
  --name "$DATA_VNET" \
  --query "{name:name,prefixes:addressSpace.addressPrefixes}" \
  --output json
~~~

Confirm **10.10.0.0/16** and **10.20.0.0/16** are the right target networks with zero overlap, and that `NVA_IP` is the appliance's private IP. Record any existing route table on each subnet so you do not overwrite an existing configuration without owner approval.

~~~bash
az network vnet subnet show \
  --resource-group "$APP_RG" \
  --vnet-name "$APP_VNET" \
  --name "$APP_SUBNET" \
  --query "{name:name,addressPrefix:addressPrefix,routeTable:routeTable.id}" \
  --output json

az network vnet subnet show \
  --resource-group "$DATA_RG" \
  --vnet-name "$DATA_VNET" \
  --name "$DATA_SUBNET" \
  --query "{name:name,addressPrefix:addressPrefix,routeTable:routeTable.id}" \
  --output json
~~~

### 8.2. Create the Route Table for Spoke A

~~~bash
az network route-table create \
  --resource-group "$APP_RG" \
  --name "rt-orders-app-inspection" \
  --location southeastasia

az network route-table route create \
  --resource-group "$APP_RG" \
  --route-table-name "rt-orders-app-inspection" \
  --name "to-orders-data-via-nva" \
  --address-prefix "10.20.0.0/16" \
  --next-hop-type VirtualAppliance \
  --next-hop-ip-address "$NVA_IP"
~~~

This route steers traffic from **the subnet attached to the route table** destined for **10.20.0.0/16** through the appliance. It does not affect the subnet until the subnet association is created.

### 8.3. Create the Route Table for Spoke B

~~~bash
az network route-table create \
  --resource-group "$DATA_RG" \
  --name "rt-orders-data-inspection" \
  --location southeastasia

az network route-table route create \
  --resource-group "$DATA_RG" \
  --route-table-name "rt-orders-data-inspection" \
  --name "to-orders-app-via-nva" \
  --address-prefix "10.10.0.0/16" \
  --next-hop-type VirtualAppliance \
  --next-hop-ip-address "$NVA_IP"
~~~

The B→A route handles return traffic or connections initiated from B when allowed by policy. Connections initiated from A still rely on the NVA processing statefully with a matching return path.

### 8.4. Associate Route Tables with Subnets

**Proceed only if the subnets have no other route table or updating the existing route table is approved.** Azure allows one route table per subnet at a time; replacing the link can remove critical routes from the old table.

~~~bash
az network vnet subnet update \
  --resource-group "$APP_RG" \
  --vnet-name "$APP_VNET" \
  --name "$APP_SUBNET" \
  --route-table "rt-orders-app-inspection"

az network vnet subnet update \
  --resource-group "$DATA_RG" \
  --vnet-name "$DATA_VNET" \
  --name "$DATA_SUBNET" \
  --route-table "rt-orders-data-inspection"
~~~

Then verify the associations:

~~~bash
az network vnet subnet show \
  --resource-group "$APP_RG" \
  --vnet-name "$APP_VNET" \
  --name "$APP_SUBNET" \
  --query "routeTable.id" \
  --output tsv

az network vnet subnet show \
  --resource-group "$DATA_RG" \
  --vnet-name "$DATA_VNET" \
  --name "$DATA_SUBNET" \
  --query "routeTable.id" \
  --output tsv
~~~

### 8.5. Verify Route Table Contents

~~~bash
az network route-table route list \
  --resource-group "$APP_RG" \
  --route-table-name "rt-orders-app-inspection" \
  --output table

az network route-table route list \
  --resource-group "$DATA_RG" \
  --route-table-name "rt-orders-data-inspection" \
  --output table
~~~

Expected: route A shows prefix **10.20.0.0/16**, route B shows prefix **10.10.0.0/16**, both using the NVA's private IP as next hop. **You cannot yet conclude real traffic flows through the NVA** from route table configuration alone.

## 9. Verifying via Effective Routes and Connectivity Tests

### 9.1. Effective Routes

On the NIC of the source VM in spoke A, run:

~~~bash
az network nic show-effective-route-table \
  --resource-group "<vm-app-resource-group>" \
  --name "<vm-app-nic-name>" \
  --output table
~~~

Do the same for the NIC of the destination VM in spoke B:

~~~bash
az network nic show-effective-route-table \
  --resource-group "<vm-data-resource-group>" \
  --name "<vm-data-nic-name>" \
  --output table
~~~

Locate the route to the opposite prefix. Check:

- Whether the next hop is **Virtual appliance** with the exact expected IP.
- Whether a more specific route causes traffic to bypass the NVA.
- Whether any **None**, gateway, or default route interferes.
- Whether the route state is Active with the expected route source.

Some PaaS services or workloads lack a user-accessible NIC for this command directly. In those cases, use diagnostic tools appropriate for that service and platform.

### 9.2. Source–Destination–Port Test

Suppose VM A is 10.10.1.10 and the service on B is 10.20.1.10:443. From VM A, test the exact port:

~~~bash
nc -vz -w 5 10.20.1.10 443
~~~

If this is a real HTTPS endpoint, test hostname and TLS validation rather than just TCP port reachability:

~~~bash
curl --connect-timeout 5 https://api.orders.internal/health
~~~

The DNS name above is illustrative only; a valid DNS record and certificate are required in the lab. Ping is not a conclusive test: ICMP may be blocked even while TCP/443 is permitted.

### 9.3. Confirming Real Traffic Traverses the Appliance

This is the **most important** step to confirm inspection:

1. Generate a connection with a known timestamp, IP, and port from spoke A.
2. Locate the matching session or log entry on the NVA / Azure Firewall.
3. Verify **source and destination IPs, matched rule, traffic direction, and allow/deny action**.
4. Verify return routing and session state if using a stateful firewall.
5. Test a policy-denied flow to confirm rules actively enforce blocks.
6. Check logs on workloads and intermediate components if connections fail.

If A→B succeeds yet the NVA has no log entry, never conclude "it is protected." Traffic may have bypassed the appliance, logging may be disabled, the rule may not log, SNAT may have rewritten addresses, or your log query may be wrong.

### 9.4. Network Watcher

Use relevant Azure Network Watcher capabilities:

- **Connection troubleshoot** to test connectivity to an IP/port and help isolate causes.
- **IP flow verify** to evaluate which NSG rule affects a flow when source/destination are supported.
- **Effective security rules** to inspect the combined NSG rules applied to a NIC.
- **Effective routes** to verify UDRs and other route sources.
- **Traffic analytics / supported flow logging** to observe flows as configured by your organization.

Features, permissions, support conditions, and logging charges may vary. Before using, confirm the resource type, region, and configured data sources.

## 10. High Availability: Avoiding a Single NVA Failure Point

A single NVA VM creates a **single point of failure**. If that appliance stops, reboots, loses capacity, or saturates, multiple workloads can lose connectivity even while VNets and peerings remain up.

### 10.1. Typical HA Architectures

Depending on product and support:

- **Active–standby:** one primary NVA handles traffic while a standby NVA is ready to take over. Requires failover detection, route updates, and state sync if required by the product.
- **Active–active:** multiple NVAs process traffic concurrently. Requires flow distribution, stickiness/session symmetry controls, and design limits.
- **Internal Standard Load Balancer + HA ports:** in supported NVA architectures, uses a frontend IP and health probes to distribute flows across backend NVAs while matching routing constraints.
- **Availability Zones / Availability Sets:** spreads instances across fault domains where supported by the service/region, though it does not fix routing logic or guarantee stateful flow symmetry on its own.
- **Managed Azure Firewall:** replaces self-managed NVA VMs with Azure's built-in HA and scaling in supported regions/configurations.

Not every NVA vendor supports these patterns identically. Follow the vendor's reference architecture and guidance. In particular, **never assume a load balancer frontend IP is a valid next hop in every scenario** simply because you want HA.

### 10.2. Stateful Inspection and Symmetry

A single session can consist of packets:

~~~text
Client A → Firewall 1 → Server B
Server B → Firewall 2 → Client A
~~~

If Firewall 1 and Firewall 2 do not share state, the second node can drop the reply because it never saw the initial handshake. Therefore, HA must address:

1. How nodes are selected for forward and return directions.
2. Session affinity or state synchronization per product capabilities.
3. How SNAT affects return paths and log visibility.
4. Health probes that verify actual forwarding health, not merely that the VM OS is booted.
5. Failover behavior: whether existing sessions survive or must reconnect.
6. Consistency of routes and security policies across instances.

### 10.3. Fail-Open vs. Fail-Closed

- **Fail-closed:** when the appliance is unavailable, inspected flows are blocked. Suitable when security enforcement outweighs continuity.
- **Fail-open:** traffic bypasses the failed appliance. Can preserve connectivity, but requires explicit approval since traffic leaves the inspection boundary.

Azure does not choose this policy for your ops team. Document the decision, trigger conditions, and auditing controls.

### 10.4. Failover Testing

In a sandbox, simulate shutting down one NVA node or failing its health probe under an approved procedure, then measure:

- Recovery time for new connections.
- Impact on already-established sessions.
- Whether inspection logs continue recording.
- Whether traffic inadvertently bypasses inspection.
- Whether routes/peering, DNS, policies, and backend health remain valid.

Never run sudden failover tests in production without a formal plan and recovery procedure.

## 11. When Are Dynamic Routing and Azure Route Server Needed?

As VNets and NVAs grow, maintaining large sets of manual UDRs can become hard to scale. Some NVA solutions support **BGP**; in supported architectures, **Azure Route Server** exchanges routing information between NVAs and the Azure network fabric.

However:

- Route Server **is not a firewall**; it does not inspect payloads or filter traffic.
- BGP peering does not replace policy design, subnet routing, or return-path verification.
- Route advertisement and propagation behavior must follow specific Azure Route Server and NVA requirements.
- When both UDRs and BGP supply routes for the same prefix, understand route selection precedence before deploying.
- It introduces an added control plane and dependency, requiring HA, limit, monitoring, and cost assessment.

For a two-spoke lab, UDRs are transparent and ideal for learning the fundamentals. For multi-subscription environments, compare UDR/IaC automation, Route Server, Virtual WAN, or a managed firewall architecture.

## 12. DNS, TLS, and Payload Inspection Limits

Traffic may be **routed through an NVA**, yet application-level visibility and enforcement still depend on actual configuration.

### 12.1. DNS

Key points to evaluate:

- Do workloads use Azure-provided DNS, custom DNS, Azure Private DNS, or Private Resolver?
- Does the target service hostname resolve to a private IP or a public IP?
- Does the DNS server sit in another VNet, meaning DNS traffic itself needs appropriate routes and NSGs?
- Are there Private Endpoints requiring dedicated private DNS zones and VNet links?

A hostname resolving to an unexpected IP sends traffic down a different route. Always verify **`nslookup`/`dig`** output before blaming UDRs.

### 12.2. TLS and Applications

An NVA sees the source/destination IPs and ports of a TLS connection without reading the encrypted payload inside. Enabling **TLS inspection/decryption** requires supported features, explicit policy, trusted certificates/PKI, and security, legal, and privacy approvals.

Never treat "traffic passes through the firewall" as "every HTTPS payload is inspected." Some traffic uses encryption schemes, certificate pinning, or protocols incompatible with TLS interception.

### 12.3. Private Endpoints

A Private Endpoint provides access to a supported Azure service over a private IP. It does not replace controls between arbitrary subnets/VNets; conversely, peering does not grant data-plane authorization to a Private Endpoint service.

If traffic to a Private Endpoint must pass through an inspection appliance, review route limitations, network policies on the subnet hosting the private endpoint, and service-specific path rules. Never apply broad routes assuming Private Endpoint traffic obeys every UDR identically to standard VMs.

## 13. Logging, Monitoring, and Observing Inspected Traffic

A real firewall architecture needs **evidence** that policies are enforced. At minimum, collect:

| Data Source | What to Inspect |
|---|---|
| Firewall/NVA traffic logs | Timestamp, source IP, destination IP, port, protocol, action, rule, session |
| NVA system/health | CPU, memory, NIC throughput, packet drops, session counts, interface/HA state |
| Azure Monitor metrics | Managed service/resource health, error trends, and throughput |
| Azure Activity Log | Who modified route tables, peerings, NICs, NSGs, or infrastructure configs |
| Supported NSG/VNet flow telemetry | Whether network flows were allowed or denied at respective boundaries |
| Source/destination applications | HTTP status codes, timeouts, TLS errors, connection resets, latency |
| Cost Management | VM, license, Load Balancer, Azure Firewall, peering, and log ingestion costs |

During incident analysis, align on a common **timestamp** and **correlation ID** where available. NVA logs may show post-NAT IPs; correlate with NAT/session logs to trace the true origin.

Connection telemetry and logs can contain addresses, identifiers, or sensitive metadata. Apply appropriate RBAC, retention, and log access governance.

### 13.1. Setting Up Operational Alerts

Alerts should cover:

- Unhealthy NVA or loss of an HA node.
- Sessions, throughput, or CPU approaching solution limits.
- Abnormal spikes in packet drops, timeouts, or connection resets.
- Route table or peering changes outside maintenance windows.
- Critical flows disappearing from inspection logs.
- Unexpected spikes in network/egress costs.

Do not judge risk from denied-traffic counts alone; a healthy policy naturally blocks unwanted probes. Read counts alongside trends, sources, destinations, and workload criticality.

## 14. Common Failure Analysis

| Symptom | Potential Causes | How to Check |
|---|---|---|
| Peering Connected yet A cannot call B | Missing UDR, NVA not forwarding, NSG/firewall block | Effective routes, peering forwarded traffic, NIC/OS forwarding, NVA rules |
| A→B reaches NVA but never reaches B | NVA missing route, firewall deny, NIC forwarding disabled | Traffic logs, NVA routing table, NIC IP forwarding |
| B replies yet A never receives it | Missing return route, asymmetric path, broken session state | Route on subnet B, NAT, firewall session logs |
| Connection succeeds yet NVA has no logs | Traffic bypassed NVA or logging misconfigured | Compare effective routes, log filters, NAT, and time range |
| Cannot create peering | Overlapping VNet CIDRs or missing permissions | Both VNets' address spaces and RBAC on both sides |
| Route table exists yet traffic path unchanged | Not attached to the right subnet | `subnet.routeTable.id` and effective routes |
| Only one subnet fails | Route table or NSG applied only to that subnet | Subnet association, effective NSG rules, NIC subnet |
| TCP port open yet application fails | DNS, TLS, auth, or application policy | `nslookup`, certificates, application logs |
| Outbound Internet breaks after adding 0.0.0.0/0 | NVA lacks egress path or missing SNAT | Next hop, firewall/NAT, routing, Internet policy |
| Single NVA node failure causes wide outage | No HA or misconfigured health probe | Backend health, stateful sessions, route/failover behavior |
| Private Endpoint traffic ignores expected route | Specific Private Endpoint network policies/routing behavior | Private Link architecture, effective routing, support prerequisites |
| Sharp cost increase | High peering/firewall/logging volume or hairpin traffic | Cost Management, byte counters, traffic matrix |

### 14.1. Hop-by-Hop Investigation Workflow

When A cannot call B:

1. **Verify DNS:** what IP does the target hostname resolve to?
2. **Verify route on A:** which next hop does the effective route to B's IP select?
3. **Verify peering:** are A↔hub and hub↔B both Connected, with forwarded traffic enabled in the right directions?
4. **Verify NVA ingress:** do packets arrive at the NVA?
5. **Verify NVA policy/forwarding:** allow/deny rules, IP forwarding, and appliance routing table?
6. **Verify route on B:** can B send return traffic back through the NVA?
7. **Verify session state:** do forward and return paths hit the same stateful node or compatible state-sharing mechanism?
8. **Verify application:** are the listener, OS firewall, TLS, and authentication healthy?

Never fix issues by opening NSGs to **Any/Any** or disabling firewalls altogether as a "quick test" in production. If isolated testing is required, perform it in a lab, document scope, and restore immediately after capturing results.

### 14.2. Checking Routes on a Specific Machine

Example command:

~~~bash
az network nic show-effective-route-table \
  --resource-group "<vm-rg>" \
  --name "<vm-nic>" \
  --output table
~~~

If effective routes cannot be read directly from a NIC, verify resource prerequisites and use Azure Network Watcher tools rather than assuming no routes exist.

## 15. Controlled Changes and Rollback

Modifying UDRs, peerings, or firewall policies can cause outages across multiple services. Before deploying:

1. Snapshot current route table/subnet associations, peerings, and firewall rules.
2. List affected prefixes and applications.
3. Prepare an approved rollback plan, including out-of-band access to the NVA if management traffic traverses it.
4. Roll out subnet by subnet where feasible instead of updating all subnets at once.
5. Measure legitimate connectivity and check denied traffic before and after.
6. Confirm monitoring and owner sign-off on application stability.

In a lab where you created **new route tables** on subnets that originally **had no route table**, you can remove the associations:

~~~bash
az network vnet subnet update \
  --resource-group rg-orders-app \
  --vnet-name vnet-orders-app \
  --name snet-app \
  --remove routeTable

az network vnet subnet update \
  --resource-group rg-orders-data \
  --vnet-name vnet-orders-data \
  --name snet-data \
  --remove routeTable
~~~

Do this only in a lab with no prior route table to restore. If a subnet previously had its own route table, **rollback must re-attach the original route table**, not simply strip all associations. Verify subnets and connectivity after rollback.

Once certain the new lab route tables are no longer used, delete them individually:

~~~bash
az network route-table delete \
  --resource-group rg-orders-app \
  --name rt-orders-app-inspection

az network route-table delete \
  --resource-group rg-orders-data \
  --name rt-orders-data-inspection
~~~

Never delete NVAs, VNets, peerings, subnets, or resource groups containing other resources without verifying dependencies and ownership.

## 16. Performance, Limits, and Cost

### 16.1. Capacity to Plan For

An NVA can become a bottleneck when all traffic funnels through one point. Size capacity based on:

- Inbound/outbound throughput, concurrent traffic, and peak hours.
- New connections per second, active concurrent sessions, and session timeouts.
- Packet size, small-packet ratios, rule counts, and IPS/TLS inspection overhead if enabled.
- Appliance NIC/VM/CPU/memory limits and HA scaling.
- Overhead from logging, encryption, NAT, load balancers, and cross-region routing.

Do not equate nominal NIC bandwidth with guaranteed inspection throughput. Benchmark against realistic traffic profiles and vendor guidelines.

### 16.2. Costs to Account For

| Component | Potential Costs |
|---|---|
| NVA VM | Compute, disks, IPs, and software licensing |
| Azure Firewall | Tier pricing model, data processed, and add-on features |
| Load Balancer | SKU/configuration charges and data processing rules |
| VNet peering | Regional/global peering traffic charges by location and direction |
| Logs and monitoring | Ingestion, retention, queries, alerts, and SIEM integration |
| Egress | Service, path, and regional/Internet egress fees per rate card |
| HA/DR | Multiple instances, subnets, supporting devices, and ops staffing |

Routing A→hub→B can increase path length, peering data volume, and cost compared to direct routing. Measure using Azure Cost Management and current pricing tables before choosing to route every flow through centralized inspection.

### 16.3. Decisions to Capture as an ADR

An **Architecture Decision Record** should state:

- Why this flow requires inspection and the risk of bypass.
- Why Azure Firewall, an NVA, or an alternative was chosen.
- IP plan, prefixes, subnet associations, UDRs, and bidirectional routing.
- Scope of NAT, DNS, TLS inspection, and logging.
- HA model, failover, and fail-open vs. fail-closed stance.
- Owners, operational permissions, update workflows, and config backups.
- Capacity, projected cost, SLA/SLO targets, and monitoring approach.
- How routing and inspection are tested after every change.

## 17. Pre-Production Architecture Review

- [ ] Trust boundaries and source–destination–port traffic matrix clearly defined.
- [ ] Egress, inbound, and east–west flows needing inspection clearly separated.
- [ ] All VNets have non-overlapping CIDRs and required bidirectional peerings.
- [ ] Peering **Allow forwarded traffic** verified in all relevant directions.
- [ ] NVA or Azure Firewall genuinely sits on the active routed path.
- [ ] Azure NIC and guest/NVA IP forwarding configured if using an NVA VM.
- [ ] Next-hop IP is valid, stable, and backed by an HA strategy if needed.
- [ ] Subnet route tables do not unintentionally override critical existing routes.
- [ ] Forward and return paths tested with no unintended asymmetric routing.
- [ ] Firewall policy and NSGs permit only approved traffic.
- [ ] DNS, Private Endpoints, TLS, and management access paths evaluated separately.
- [ ] Logs prove traffic traverses the appliance and hits expected rules.
- [ ] Valid traffic, blocked traffic, failure/failover, and rollback tested in an appropriate environment.
- [ ] Throughput, HA, peering/firewall costs, and log retention estimated.
- [ ] Configuration and changes governed via IaC/pipelines or controlled change processes.

## 18. Hands-On Exercises and Reasoning Questions

### Exercise 1: Designing Routing Through an NVA

Given three VNets as in the example: hub `10.0.0.0/16`, spoke A `10.10.0.0/16`, spoke B `10.20.0.0/16`. The hub NVA has IP `10.0.1.4`.

Draw the diagram, write the routes needed on subnets A and B so TCP/443 traffic from A to B traverses the NVA, and explain why peering A–hub and hub–B alone is not enough.

**Pass criteria:** bidirectional UDRs, accurate next-hop IP, understanding of forwarded traffic, and guaranteed return path.

### Exercise 2: Finding the Cause of a Bypass

VM A can reach VM B, yet NVA logs show zero traffic. Outline the investigation order across: DNS, effective routes, direct peering, subnet route-table association, NAT, logging, and firewall rules.

### Exercise 3: Assessing the Risk of a Default Route

Operations wants to add `0.0.0.0/0 → NVA` to every subnet. List all pre-deployment checks needed: DNS, outbound access, PaaS/private endpoints, HA, SNAT, bandwidth, monitoring, and rollback.

### Exercise 4: Designing HA for a Stateful Firewall

Two active–active NVAs can process traffic behind a load balancer. Explain why having two VMs alone does not guarantee stateful HA, and specify requirements for session affinity, return paths, health probes, forwarding, and failover.

### Exercise 5: Design-Level Cost Analysis

Compare architecture (A) each spoke uses NSG rules with controlled direct connectivity versus (B) all east–west flows traverse a hub NVA. List all cost, performance, and complexity factors that belong in the decision—without inventing unit prices.

### Self-Check Questions

1. Does a UDR with next hop `VirtualAppliance` automatically enable IP forwarding on the VM?
2. Does a `Connected` peering guarantee traffic traverses the NVA?
3. Why does a stateful firewall generally require symmetric forward and return paths?
4. What are the differences among NSGs, WAF, NVAs, and Azure Firewall?
5. Does enabling `Allow forwarded traffic` automatically create routes between spokes?
6. When can SNAT hide the original source IP and complicate log analysis?
7. Why should you inspect effective routes instead of reading route table configuration alone?
8. If a TCP connection succeeds yet the NVA has no log entry, does that prove the traffic is secure?
9. Can Azure Route Server replace all firewall rules?
10. Why does a `0.0.0.0/0` route require stricter review than a `/16` route serving a specific flow?

## 19. References

- [Azure virtual network traffic routing](https://learn.microsoft.com/azure/virtual-network/virtual-networks-udr-overview)
- [Azure Virtual Network peering overview](https://learn.microsoft.com/azure/virtual-network/virtual-network-peering-overview)
- [Hub-spoke network topology in Azure](https://learn.microsoft.com/azure/architecture/networking/architecture/hub-spoke)
- [Azure Firewall documentation](https://learn.microsoft.com/azure/firewall/overview)
- [Azure Load Balancer HA ports overview](https://learn.microsoft.com/azure/load-balancer/load-balancer-ha-ports-overview)
- [Azure Route Server overview](https://learn.microsoft.com/azure/route-server/overview)
- [Azure Network Watcher connection troubleshoot](https://learn.microsoft.com/azure/network-watcher/network-watcher-connectivity-overview)
- [Network security groups overview](https://learn.microsoft.com/azure/virtual-network/network-security-groups-overview)
- [Azure Virtual Network pricing](https://azure.microsoft.com/pricing/details/virtual-network/)
