# Dedicated Connectivity with ExpressRoute

An enterprise with an on-premises data center and multiple applications running on Microsoft Azure often needs reliable data transfer between the two environments. For example, an order management system might host its API on Azure App Service while still relying on a database or ERP system in its own data center. Transferring data over the Internet can meet many needs, but workloads with high traffic volumes, consistent network performance requirements, or specific enterprise connectivity architectures may require another approach.

**Azure ExpressRoute** lets you establish private connectivity to the Microsoft network through a connectivity provider or supported direct connection location. ExpressRoute traffic does not traverse the public Internet in the way a typical site-to-site VPN connection does. However, a private circuit **does not automatically mean end-to-end encryption, absolute security, or zero downtime**. To deploy it properly, you need to understand the roles of circuits, peerings, BGP, gateways, routing, security, cost, and redundancy.

This lesson belongs to the **Network Connectivity and Security** chapter in the Azure learning path covering the Azure ecosystem—from subscriptions, resource groups, and Microsoft Entra ID to virtual networks, compute, data, deployment, monitoring, and cost control for an application architecture.

## Learning Objectives

After this lesson, you will be able to:

1. Explain what ExpressRoute is and when to choose it over a site-to-site VPN.
2. Identify the components of an ExpressRoute architecture: circuit, connectivity provider, peering, BGP, ExpressRoute gateway, and VNet.
3. Distinguish between **Azure private peering** and **Microsoft peering**.
4. Understand requirements around CIDRs, ASNs, VLANs, routing, DNS, security, and high availability.
5. Plan the deployment of connectivity from an on-premises network to an Azure VNet in verifiable steps.
6. Check resource status using the Azure portal or Azure CLI and troubleshoot common connectivity issues.
7. Evaluate costs and design a redundancy strategy appropriate for your workload.

## 1. What Is ExpressRoute?

ExpressRoute is an Azure connectivity service that allows enterprises to establish a **private connection** between their on-premises infrastructure or a connectivity provider's facility and the Microsoft network. The connection traverses a **connectivity provider**—such as a telecom carrier or colocation/connectivity service provider at a peering location—or uses **ExpressRoute Direct** for supported direct physical connection models.

ExpressRoute is designed for scenarios requiring:

- Hybrid connectivity between an enterprise data center and VNets hosting applications in Azure.
- High-volume data transfers, stable contracted connectivity with a provider, and network-level path control.
- Connecting multiple internal systems to Azure workloads through a hub-and-spoke architecture.
- Increased redundancy and connectivity control options when enterprise networks depend heavily on Azure.
- Meeting specific private-connectivity architectural requirements driven by internal policies, contracts, or organizational regulations.

ExpressRoute typically delivers more predictable latency and stability characteristics than a public Internet link, but **there is no universal guarantee that every workload will be faster than over VPN**. Actual results depend on the peering location, provider transport path, bandwidth, traffic profile, Azure region, and application design.

### What ExpressRoute Is Not

ExpressRoute is **not** a Public IP address attached to a virtual machine. It does not automatically create private DNS, replace firewalls, enable DDoS protection for your entire application, or grant access to all Azure resources.

ExpressRoute is also not a default data encryption mechanism. Depending on requirements, organizations must still use TLS for applications, data encryption, or an appropriate IPsec layer; with ExpressRoute Direct, certain scenarios can use MACsec on the direct physical link when support conditions are met.

## 2. How Does ExpressRoute Differ from Site-to-Site VPN?

**Azure VPN Gateway** can create an IPsec/IKE tunnel over the Internet between an on-premises network and an Azure VNet. **ExpressRoute** provides private connectivity to the Microsoft network through a provider ecosystem and uses BGP to exchange routes. Both can be used in hybrid architectures, but there are important differences.

| Criterion | Site-to-site VPN | ExpressRoute |
|---|---|---|
| Connection path | Tunnel over the Internet | Private connection via provider/peering location or Direct |
| Encryption | Typically uses IPsec/IKE to encrypt the tunnel | Does not encrypt traffic by default |
| Dependencies | ISP/Internet, VPN gateway, VPN device | Provider or Direct connection, circuit, peering, gateway, and network devices |
| Deployment | Usually faster if both sides already have Internet and compatible devices | Requires provisioning links with a provider, configuring peering, and deploying a gateway |
| Bandwidth, latency | Depends on Internet connectivity and gateway configuration | Depends on circuit bandwidth, provider, and network path design |
| Cost | Gateway, data transfer, and Internet connectivity | Circuit/port, provider, gateway, data transfer plan, and related services |
| Best fit | Small branches, testing, moderate traffic, or backup connectivity | Enterprise hybrid, high throughput, or private link requirements |

Do not choose ExpressRoute merely because an application needs security: an encrypted VPN over the Internet is sometimes a better fit with a more accessible cost structure. Conversely, ExpressRoute can be the right choice when an organization already has WAN infrastructure, needs large-scale private connectivity, and accepts the operational responsibility of managing routing, providers, redundancy, and cost.

Some designs support **ExpressRoute and VPN Gateway coexistence** to provide a backup path, subject to gateway, topology, and routing requirements. This must be explicitly designed and tested; simply adding a second gateway does not automatically create complete failover.

## 3. Components in an ExpressRoute Architecture

Imagine an enterprise with routers in its data center using a connectivity provider's network to reach a Microsoft peering location and then access a VNet in Azure.

~~~text
Enterprise Data Center
 +---------------------------+
 | ERP App, DB Servers       |
 | Edge Router/Firewall      |
 +-------------+-------------+
               |
      WAN / Provider Network
               |
     ExpressRoute peering location
               |
    Microsoft Enterprise Edge (MSEE)
      |                    |
      +--- BGP peering ----+
               |
       ExpressRoute circuit
               |
      ExpressRoute connection
               |
       ExpressRoute gateway
               |
  Azure VNet / hub / spoke VNet
      |                    |
  Private API/VM      Private Endpoint
                           |
                      PaaS Service
~~~

This is a logical diagram to explain the components. In real-world deployments, ExpressRoute includes redundant paths and BGP sessions; exact ordering and physical paths can vary by provider, region, and gateway model.

### 3.1. ExpressRoute Circuit

A **circuit** is the Azure resource representing the ExpressRoute connection ordered with parameters such as provider, peering location, bandwidth, and SKU. The circuit includes a service identifier (**service key**) used to coordinate with the connectivity provider during provisioning.

Creating a circuit in Azure **does not mean** the physical connection is ready. The provider must complete their corresponding steps to bring the circuit to an operational state. If using Direct, port provisioning and cross-connects carry separate operational requirements.

### 3.2. Connectivity Provider and Peering Location

A **connectivity provider** is the organization delivering transport from the enterprise environment to the Microsoft interconnection point under the chosen service model. A **peering location** is the network facility where traffic is exchanged with Microsoft's network; it **is not** the Azure region hosting your virtual machines.

For example, a circuit with a peering location in Singapore can connect to a VNet in an Azure region permitted by the SKU and routing scope. Always verify availability by geography, SKU, and current service policies.

### 3.3. Microsoft Enterprise Edge (MSEE)

MSEE routers are the Microsoft-side network devices participating in peering connections and exchanging BGP routes. Enterprises do not configure MSEE routers directly like internal routers; required parameters are declared via circuit/peering configuration and coordinated with the provider.

### 3.4. Peering

**Peering** is the configuration for exchanging routes and traffic between the customer/provider network and Microsoft over the circuit. Different peering types serve different purposes, notably **Azure private peering** and **Microsoft peering**.

### 3.5. ExpressRoute Virtual Network Gateway and Connection

In a traditional VNet architecture, a **Virtual Network Gateway** of type **ExpressRoute** is deployed into a dedicated subnet named **GatewaySubnet**. The gateway links the VNet to the circuit through a **connection**. An active circuit alone does not enable a VNet to reach on-premises networks without an appropriate gateway, peering, and connection.

In some Azure Virtual WAN architectures, the ExpressRoute gateway deployment and hub connection model differ from a standard VNet gateway. Choose the right hub model before deploying.

### 3.6. BGP

**Border Gateway Protocol (BGP)** enables both sides to exchange reachability information for IP prefixes. ExpressRoute uses BGP for peering. If prefixes are not advertised, not received, or filtered incorrectly, the circuit may appear healthy while applications still cannot connect.

## 4. Private Peering vs. Microsoft Peering

This is the most important distinction to master when learning ExpressRoute.

| Capability | Azure private peering | Microsoft peering |
|---|---|---|
| Purpose | Connects on-premises networks to private IP addresses of workloads in an Azure VNet | Connects to supported Microsoft public service endpoints under applicable support conditions |
| Typical targets | VMs using private IPs, private backends, accessing Private Endpoints as designed | Supported public Microsoft/Azure services and permitted prefixes |
| Routing | Exchanges private network routes via BGP, then connects to the VNet via gateway/connection | Advertises and receives valid prefixes per Microsoft peering requirements |
| Prerequisites | Non-overlapping CIDRs, BGP, peering, corresponding VNet gateway/connection | BGP, suitable public IP prefixes, ownership validation and routing requirements, route filters if applicable |
| Misconceptions | Does not automatically connect to all public Microsoft services | Does not replace private peering for accessing private IPs inside a VNet |

### Azure Private Peering

This is the standard choice for building **hybrid connectivity**. For example, the office network uses **172.20.0.0/16** and the Azure VNet uses **10.40.0.0/16**. Both sides exchange routes via BGP so traffic destined for private IPs of Azure workloads flows over ExpressRoute.

To access Azure SQL Database or a Storage Account via **Private Endpoint**, on-premises applications must route to the endpoint's private IP and **DNS must resolve correctly to that private address**. Private peering does not create Private Endpoints or configure DNS automatically.

### Microsoft Peering

Microsoft peering is used to reach Microsoft services that have public endpoints supported over ExpressRoute. It is a separate configuration with rules regarding public prefixes, route advertisements, and technical prerequisites. Which endpoints can be used depends on the service type and current policies.

Do not assume Microsoft peering is the recommended path for all **Microsoft 365** traffic. Most Microsoft 365 deployments are designed to be accessed directly over the Internet; exceptions and ExpressRoute requirements must be evaluated against Microsoft's specific guidance.

**Remember:** Connecting to a PaaS database via the private IP of a Private Endpoint generally belongs to an **azure private peering** design—do not assume Microsoft peering is required simply because that PaaS service also has a public endpoint.

## 5. Provisioning Models and Service Scope

### ExpressRoute via Connectivity Provider

The enterprise works with a supported connectivity provider at a peering location. The provider manages their portion of the network, while the enterprise manages internal connectivity, routers, firewalls, routing policies, and Azure configuration.

Before ordering, align on the service type, peering location, bandwidth, provisioning lead time, BGP addressing, VLANs, redundancy model, and incident-handling responsibilities across all parties.

### ExpressRoute Direct

ExpressRoute Direct provides direct physical port connectivity into Microsoft's network at supported locations, typically suited to organizations with large connectivity footprints or requirements for direct port control. Direct has its own requirements for ports, physical cross-connects, circuits created over ports, and link-layer protection. It is not a toggle that turns an existing provider-hosted circuit into a direct connection.

### SKU, Geography, and Data Plans

ExpressRoute circuits offer SKU, routing scope, and billing options—such as **Local**, **Standard**, and **Premium**—along with data plans under supported configurations. Geographic reach, maximum linked VNets, bandwidth tiers, and supported features vary across these options.

Check the SKU documentation and pricing tables at deployment time, because not every combination of provider, location, bandwidth, SKU, and billing model is available everywhere.

### Global Reach and FastPath

- **ExpressRoute Global Reach** can interconnect on-premises networks across different locations through their respective circuits, when product and geographic conditions are met. It provides inter-site network connectivity and does not replace routing design or network segmentation.
- **ExpressRoute FastPath** can optimize the data path by bypassing the ExpressRoute gateway for supported scenarios and resources. The gateway and connection remain part of the control plane, and FastPath has specific SKU, configuration, and service requirements. Never assume FastPath is enabled for every gateway.

## 6. BGP, CIDR, and Routing in ExpressRoute

To ensure traffic follows the intended path, plan IP addressing and routing tables before ordering the circuit.

### 6.1. Non-Overlapping Address Planning

Example enterprise address plan:

| Component | CIDR | Role |
|---|---|---|
| Data center | 172.20.0.0/16 | On-premises workloads |
| Azure hub VNet | 10.40.0.0/16 | Gateway, firewall, shared network services |
| Production VNet | 10.41.0.0/16 | Application APIs and data |
| Development VNet | 10.42.0.0/16 | Development workloads |

These ranges do not overlap. When designing hub-and-spoke connectivity, define peering options, gateway transit, route tables, and firewall inspection. Do not assume that merely peering VNets with a hub causes every VNet to automatically advertise or receive full routes over ExpressRoute.

If on-premises and Azure networks use overlapping ranges, routing can become ambiguous or blocked by service rules. Resolve addressing designs prior to connecting, or apply a controlled address translation strategy in supported scenarios.

### 6.2. BGP ASN, Peering Subnets, and VLANs

When setting up private peering, both sides coordinate and configure:

- **ASN (Autonomous System Number)** for the customer/provider side, per service requirements.
- **VLAN ID** to isolate the peering channel on the physical/logical link.
- **Peering address prefixes** used for the BGP sessions; for IPv4, designs typically require two separate /30 ranges for the primary and secondary links.
- **Network prefixes to advertise**, such as on-premises networks and Azure routes propagated by the gateway.
- **BGP policies**, including route filtering, path preference, failover behavior, and route limits per actual support.

Addresses used for **BGP peering** are distinct from the application address space inside a VNet. Do not pick an arbitrary CIDR and use it for both peering and workloads. Coordinate exact values with your provider and the circuit's technical requirements.

### 6.3. Forward and Return Paths

Suppose an on-premises application **172.20.10.25** calls an API in Azure **10.41.2.10**. Both sides must know how to reach the opposite network:

1. The on-premises router has a route to **10.41.0.0/16** via ExpressRoute.
2. Azure knows the return path to **172.20.0.0/16** via BGP/gateway and proper routing configuration.
3. NSGs, firewalls, security appliances, and host operating systems permit the required traffic.
4. The application uses the right IP or DNS name and holds application-layer authorization.

**An active circuit does not guarantee a working application flow.** A misconfiguration in any one of these four steps can cause timeouts or refused connections.

### 6.4. Default Route and Internet Path

If the on-premises network advertises a default route **0.0.0.0/0** and Azure accepts it per the architecture, outbound traffic from Azure workloads can be routed back on-premises. This may be intentional for centralized Internet egress control (*forced tunneling*), or it may break platform service access, increase latency, or create asymmetric routing.

Before deploying a default route or UDR that changes the next hop, evaluate return paths, firewalls, DNS, platform endpoint access, and resilience. Only apply it when the topology and gateway support it and after testing.

## 7. From Circuit to VNet: How Connectivity Is Established

In a traditional VNet design, connectivity becomes operational once several independent steps complete:

~~~mermaid
flowchart TD
  A["Select provider, peering location, SKU, bandwidth"] --> B["Create ExpressRoute circuit"]
  B --> C["Coordinate service key to provision link"]
  C --> D["Configure Azure private peering and BGP"]
  D --> E["Create GatewaySubnet and ExpressRoute gateway"]
  E --> F["Create connection from gateway to circuit"]
  F --> G["Verify BGP routes, DNS, and application flows"]
  G --> H["Monitor, test failover, manage costs"]
~~~

In practice, some tasks can be prepared in parallel. However, linking the circuit to the VNet requires all prerequisite components and compatibility conditions to be ready.

### GatewaySubnet

Azure requires a subnet named **GatewaySubnet** to host the VNet's Virtual Network Gateway. This subnet needs enough address space to deploy and scale the gateway according to service requirements; many architectures use **/27 or larger address spaces** for future growth. Always verify minimum sizing and latest guidance for your planned SKU.

GatewaySubnet is dedicated to the gateway; **do not place VMs or ordinary application services in this subnet**. Do not attach arbitrary NSGs or UDRs that could disrupt gateway operation. Any security or routing rules allowed by Microsoft for gateways must be checked specifically before applying.

### ExpressRoute Gateway

A gateway of type ExpressRoute handles connectivity between the VNet and the circuit and participates in route distribution. Choose a gateway type and SKU supporting the required throughput, availability zones, and features. A gateway is not the circuit itself and cannot substitute for provider provisioning.

### Hub-and-Spoke

In multi-workload architectures, the ExpressRoute gateway is typically placed in a **hub VNet**. **Spoke VNets** can use VNet peering with **gateway transit / allow remote gateway** settings to reach on-premises networks when topology rules permit.

Sharing a gateway does not automatically allow every spoke to connect as desired. Review routes, NSGs, firewalls, spoke-to-spoke routing, and access to shared resources.

## 8. Safe ExpressRoute Deployment Workflow

This section outlines the implementation sequence. Because ExpressRoute involves external network carriers and can incur substantial charges, learners are not expected to provision a real circuit on a personal subscription for practice.

### Step 1: Define Business Requirements and Scope

Document clearly:

- Which on-premises sites and Azure regions/VNets must connect.
- Expected traffic volume, peak-hour bandwidth, data flow directions, and latency targets.
- Critical workloads, sensitive data, acceptable downtime, and redundancy requirements.
- Tenant, subscription, and resource group structure, admin permissions, and team ownership.
- Existing private endpoints, DNS zones, firewalls, route tables, and VNet peerings.
- Existing gateway or Virtual WAN configurations, to avoid conflicting architectures.

### Step 2: Select the Connectivity Option

Work with the provider or Direct connectivity team to finalize **peering location, bandwidth, SKU, data plan, physical paths, provisioning lead time, and cost**. Confirm support for your target Azure regions and primary/secondary path layout. If you need to avoid single-provider or single-location dependency, evaluate having multiple independent circuits.

### Step 3: Create the ExpressRoute Circuit

In the Azure portal:

1. Select the appropriate **subscription** and **resource group** managing connectivity.
2. Search for **ExpressRoute circuits** and select Create.
3. Configure name, resource management region, provider, peering location, bandwidth, and supported SKU/billing model.
4. Double-check choices before creation, as some parameters and commitments have limited mutability.
5. Record the **service key** and share it via a controlled channel with the provider for provisioning.

Creating a circuit can incur charges even before any traffic passes. Obtain technical and budget approval before proceeding.

### Step 4: Provider Provisions the Circuit

Coordinate with the provider to link their infrastructure to the peering location and update the service state. Track both **provider provisioning status** and **circuit provisioning state** in the portal. An ARM resource status of Succeeded alone does not mean the provider has finished provisioning the link.

Verify peering addresses, VLANs, ASNs, bandwidth, and both paths. Record support contacts for the provider, intermediate carriers, and Microsoft.

### Step 5: Configure Private Peering / BGP

Configure **Azure private peering** when the goal is accessing private IPs inside VNets. Both sides must align on ASNs, peering prefixes, VLANs, and routing. Verify that redundant BGP sessions are established and advertised prefixes match the plan.

Never advertise unauthorized prefixes or unintended default routes; mistakes can pull traffic from unrelated systems across ExpressRoute.

### Step 6: Create the Gateway and Link to the Circuit

Create **GatewaySubnet** in the hub VNet and deploy an **ExpressRoute virtual network gateway** with an appropriate SKU. Then create a connection from the gateway to the circuit. If the circuit and VNet reside in different subscriptions, an **authorization** and corresponding linking steps are required under the supported governance model.

After connecting, confirm BGP routes are exchanged, the gateway is healthy, and the VNet has paths back to on-premises prefixes. For spoke VNets, verify peering and gateway transit settings if used.

### Step 7: Validate Application Flows

Run targeted checks instead of relying solely on ping:

1. From an on-premises machine, resolve the DNS name of the Azure API or resource.
2. Check whether the route to the destination private IP follows the expected path.
3. Test TCP/TLS connectivity to the authorized service port.
4. From Azure, verify the return route back to the on-premises network.
5. Verify NSGs, firewalls, application rules, and data access permissions.
6. Measure latency and throughput appropriate for the workload and compare against your baseline.

Some services block ICMP, so **a failed ping does not automatically prove ExpressRoute is down**. Use application-port checks and routing data for reliable conclusions.

### Step 8: Monitoring and Operational Handover

Set up metrics and alerts for the circuit, peering, gateway, and related network components. Store topology diagrams, lists of CIDRs, ASNs, VLANs, gateways, owners, provider contracts, troubleshooting runbooks, and failover procedures. Set subscription budgets and reconcile costs across the circuit, gateway, provider transport, and security services.

## 9. Checking Connectivity with Azure CLI (Read-Only)

The commands below are for **viewing status** without creating or modifying resources. You must sign in to Azure and hold read permissions on the subscription containing the circuit or gateway.

### Confirm Subscription

~~~bash
az login
az account show --query "{name:name,id:id}" --output table
az account set --subscription "<SUBSCRIPTION_ID>"
~~~

### List Circuits in a Resource Group

~~~bash
az network express-route list \
  --resource-group "rg-network-hub" \
  --output table
~~~

### Inspect a Specific Circuit's Status

~~~bash
az network express-route show \
  --resource-group "rg-network-hub" \
  --name "er-circuit-prod" \
  --query "{name:name,provisioningState:provisioningState,providerState:serviceProviderProvisioningState,peeringLocation:serviceProviderProperties.peeringLocation,bandwidthMbps:serviceProviderProperties.bandwidthInMbps}" \
  --output json
~~~

Output properties may vary by provisioning method and API version. Check both the Azure Resource Manager state and the provider provisioning state.

### View Peering Configuration

~~~bash
az network express-route peering list \
  --resource-group "rg-network-hub" \
  --circuit-name "er-circuit-prod" \
  --output table
~~~

### View ExpressRoute Gateway in the Hub VNet

~~~bash
az network vnet-gateway show \
  --resource-group "rg-network-hub" \
  --name "ergw-hub-prod" \
  --query "{name:name,gatewayType:gatewayType,provisioningState:provisioningState,sku:sku.name}" \
  --output json
~~~

**Note:** the resource group, circuit, and gateway names are illustrative values. In Azure Virtual WAN, gateways use different resource types and management commands than standard virtual network gateways. Confirm which architecture is in use before checking.

These commands **do not replace** checking BGP session states, learned/advertised routes, and application connectivity from on-premises. For deeper diagnostics, combine the portal, metrics, route inspection, provider tools, and internal network checks.

## 10. ExpressRoute Security and Access Control

### A Private Path Is Not Default Encryption

ExpressRoute uses private connectivity instead of the public Internet, but traffic **is not automatically encrypted end-to-end**. For sensitive data, implement TLS and application-layer protections, or consider adding IPsec/MACsec where the model and services support it.

A private network can still be compromised if admin accounts are hijacked, firewall rules are overly permissive, or applications have vulnerabilities. Combine multiple layers:

| Control Layer | Examples |
|---|---|
| Identity and permissions | Microsoft Entra ID, Azure RBAC, least privilege |
| Network | Azure Firewall, NSGs, UDRs, hub/spoke segmentation |
| Application connectivity | TLS, API authentication, certificate management |
| Secrets and keys | Azure Key Vault, appropriate access policies |
| Data | Encryption at rest, database permissions, backups |
| Monitoring | Azure Monitor, firewall logs, gateway/circuit metrics |

### Private Endpoint and DNS

When an on-premises application uses ExpressRoute to reach a PaaS service over a **Private Endpoint**, traffic must route to the private IP inside the VNet and the service name must resolve to the right IP. Azure Private DNS Zones, DNS resolvers, and conditional forwarding mechanisms can be used depending on design.

For instance, if an on-premises app calls a storage account by FQDN while DNS still returns a public IP, traffic may take the wrong path or get blocked by firewall policy. Always test DNS from **actual client machines**, not only from a VM inside the VNet.

### Minimizing Permissions and Route Scope

Advertise only required prefixes, filter routes per network policy, and restrict access per subnet and resource. Avoid advertising routes for every internal subnet when workloads only need a small group of services. In hub-and-spoke topologies, clearly define which firewall inspects traffic and ensure return traffic follows the same expected routing rules.

## 11. High Availability and Redundancy Design

ExpressRoute supports redundant connectivity structures into the Microsoft network. Each circuit includes redundant links and peering sessions per the service and provider architecture. However, **a single circuit does not eliminate all single points of failure**, especially if both paths share a facility, fiber route, or provider.

Levels of redundancy to evaluate:

1. **Intra-circuit redundancy:** dual links/BGP sessions built into ExpressRoute; the provider must provision both cleanly.
2. **Independent connection redundancy:** consider two circuits across different transport paths, providers, or peering locations if availability targets demand it.
3. **Gateway and VNet redundancy:** select SKUs, availability zones, and topologies aligned with uptime goals.
4. **VPN backup:** VPN Gateway can serve as a fallback path in supported coexistence topologies, with verified routing and BGP policies.
5. **Application redundancy:** multiple instances, resilient databases, bounded retries, circuit breakers, and recovery plans.

### Real Failover Testing Is Essential

Failover drills may include dropping one link, shutting down one BGP session, or simulating a single provider path outage in coordination with the network team. Record which routes are chosen, convergence time, impact on active sessions, and whether traffic fails back cleanly to the primary path.

Never simulate link failures in production without a formal plan and approval. BGP failover involves convergence time and can interrupt active connections. A dual-circuit architecture only fulfills its redundancy goal when tested in **both outbound and return directions**, avoiding asymmetric routing across stateful firewalls.

## 12. Monitoring and Troubleshooting

When users report that on-premises ERP cannot reach Azure, isolate the issue by layer:

| Symptom | Possible Cause | How to Investigate |
|---|---|---|
| Circuit not ready | Provider has not provisioned or circuit is in failed state | Check circuit provisioning state, provider state, and contact provider |
| BGP session not established | Wrong ASN, VLAN, peering prefix, physical port, or router config | Compare parameters on both sides; check primary/secondary BGP status |
| BGP up but no Azure routes | Misconfigured private peering, gateway connection, or route propagation | Inspect advertised/received prefixes, connection, gateway, and VNet topology |
| Azure has no route back on-premises | On-premises prefixes filtered or not advertised | Check BGP advertised/learned routes and effective routes |
| Connection to VM times out | Blocked by NSG, UDR, firewall, or OS firewall | Check routes, destination port, firewalls, and Network Watcher |
| PaaS via Private Endpoint unreachable | DNS resolves to public IP or path to private IP is invalid | Test DNS from on-premises, check private DNS and route to endpoint subnet |
| Slow or packet loss | Congestion on provider link, gateway/circuit, app, or security appliance | Correlate traffic, error, latency, utilization metrics, and logs |
| Fails only during failover | Incomplete BGP preference, return path, or redundancy setup | Inspect paths before/after failover and configurations on both sides |
| Cannot reach a spoke | Incorrect gateway transit, peering, or firewall/UDR | Review hub-spoke topology and spoke effective routes |

### Recommended Investigation Order

1. **Scope the issue:** which site, which VNet, which service, since when, all traffic or partial traffic?
2. **Check provisioning:** are circuit, provider, peering, and connection/gateway statuses healthy?
3. **Check BGP:** are all required sessions up, with the right prefixes in both directions?
4. **Check DNS:** what IP does the FQDN resolve to from the actual source machine?
5. **Check data path:** NSGs, UDRs, firewalls, routing appliances, ports, and application state.
6. **Check load and redundancy:** metrics, logs, packet loss, and recent changes.
7. **Align ownership:** determine whether the issue lies in Azure, the provider, internal networking, or the application so it routes to the right support team.

Azure Monitor and network diagnostic tools help surface traffic spikes, health states, and resource changes. For provider incidents, capture the circuit identifier, peering location, incident timestamps, BGP status, and carrier contact details for correlation.

## 13. Costs and Governance Controls

ExpressRoute is an architectural decision carrying ongoing operational and financial commitments, not just a technical setting. Cost components can include:

- **Circuit or port:** billed by ExpressRoute type, bandwidth, SKU, geography, and billing plan.
- **Connectivity provider:** WAN transport, cross-connects, setup fees, and private network contracts.
- **ExpressRoute gateway:** gateway resources carry separate charges by SKU and uptime, even at low utilization.
- **Data transfer:** varies by metered vs. unlimited selection, routing scope, and billable traffic direction.
- **Supporting network services:** Azure Firewall, Private Endpoints, DNS, VNet peering, monitoring, and related components.
- **Operations:** router/BGP administration, failover testing, maintenance, support, and architecture updates.

Before creating a circuit, the architecture team should estimate bidirectional traffic, analyze traffic bursts, verify appropriate bandwidth, compare against VPN, and account for provider invoices outside Azure billing. Track Azure spend using **Azure Cost Management**, budgets, and ownership tags, while noting that provider charges generally arrive separately from Azure.

Never claim one billing model is always cheaper. Pricing, reach, and limits vary by SKU, location, and time, so always verify current pricing tables and contracts.

## 14. Real-World Scenario: Connecting On-Premises ERP with an Azure Sales System

An enterprise runs an ERP system in its data center and an ordering application deployed on Azure:

- **On-premises network:** 172.20.0.0/16, hosting the ERP and business databases.
- **Hub VNet:** 10.40.0.0/16, hosting the ExpressRoute gateway and firewall as designed.
- **Production spoke VNet:** 10.41.0.0/16, hosting the application APIs.
- **Data services:** Azure SQL Database and Storage using Private Endpoints where appropriate.
- **Connectivity:** ExpressRoute private peering to the hub, with controlled routing to spokes.

The objective is to let APIs on Azure call the on-premises ERP service while internal staff access specific private application endpoints in Azure.

### Proposed Design

1. Inventory all existing CIDRs and verify that **172.20.0.0/16**, **10.40.0.0/16**, and **10.41.0.0/16** do not overlap with any connected networks.
2. Select a provider, peering location, bandwidth, SKU, and backup path plan.
3. Establish private peering BGP, configure the hub gateway/connection, and enable gateway transit for spokes where supported by topology.
4. Advertise only required prefixes; use firewalls and NSGs to restrict directions and ports between the API and ERP.
5. Configure DNS appropriately so on-premises ERP names and Azure Private Endpoint names resolve to the correct private addresses.
6. Enforce application-layer data authorization, use TLS for sensitive traffic, and manage secrets with appropriate tooling.
7. Test both directions: API calls to ERP, on-premises apps reaching permitted Private Endpoints, and verify unauthorized traffic is blocked.
8. Monitor the circuit/gateway/provider; rehearse link failure scenarios and measure business impact.

### Acceptance Checklist

| Criterion | Expected Evidence |
|---|---|
| Circuit and provider | Provisioning complete; parameters match contract |
| BGP peering | Required sessions established; bidirectional routes match plan |
| Gateway and connection | Healthy operational state; VNet linked to the right circuit |
| DNS | ERP and Private Endpoint FQDNs resolve properly from source machines |
| Access control | Only authorized connections pass firewalls/NSGs and applications |
| Load and latency | Test results meet business SLOs |
| Redundancy | Single-link outage scenario has a verified continuity/recovery path |
| Monitoring and cost | Metrics, alerts, owners, budgets, and provider contract documented |

## 15. Common Misconceptions

**"ExpressRoute automatically encrypts all data."** No. It is a private connection; consider TLS/IPsec or MACsec under supported configurations to protect data in transit.

**"Creating a circuit means the VNet is connected to on-premises."** Not yet. You still need provider provisioning, peering/BGP, a gateway or compatible connectivity architecture, and a connection to the VNet/hub.

**"The peering location is the same as the application's Azure region."** No. The peering location is where you interconnect with Microsoft's network; the region is where Azure resources are deployed.

**"Microsoft peering is used to reach all private IPs in a VNet."** No. VNet private IPs are the standard case for Azure private peering; Microsoft peering applies to supported public Microsoft services/endpoints.

**"Circuit up means the application will work."** You still need forward and return routes, DNS, firewalls, NSGs, and healthy applications. A healthy BGP session does not guarantee application-layer success.

**"Having two BGP sessions means no further redundancy planning is needed."** Intra-circuit redundancy does not protect against provider-wide, facility, or physical path failures.

**"ExpressRoute is always cheaper than VPN."** ExpressRoute costs span multiple components and often depend on provider contracts. Evaluate based on traffic volume, SLOs, and operational costs.

**"With ExpressRoute, Private Endpoints or internal DNS are unnecessary."** ExpressRoute provides the network path; reaching PaaS services via private IP still requires Private Endpoints, DNS, and access controls.

## 16. Self-Check Questions

1. What problems does ExpressRoute solve when connecting a data center to Azure? Give two scenarios where it should be considered.
2. What are the main differences between ExpressRoute and site-to-site VPN in terms of network path, encryption, and cost?
3. What distinct roles do a circuit, peering, and ExpressRoute gateway perform?
4. Why is it important to distinguish a peering location from an Azure region?
5. When do you use Azure private peering? Which endpoints is Microsoft peering intended for?
6. What happens if the on-premises router does not receive Azure prefixes or Azure lacks a return route to the on-premises network?
7. Why does a **Private Endpoint** require proper **DNS** configuration even when ExpressRoute private peering is already working?
8. If the circuit is healthy but an on-premises VM cannot call an Azure API over HTTPS, which layers would you inspect and in what order?
9. Why might a single circuit with primary and secondary links still fail to meet high-availability requirements?
10. What cost components must be included when comparing ExpressRoute and VPN?
11. When using hub-and-spoke, what must be checked so spokes can reach on-premises while still restricting traffic flows?
12. Design an acceptance checklist for ExpressRoute supporting an ERP workload and sales API prior to production cutover.

## References

- Microsoft Learn — *What is Azure ExpressRoute?*: https://learn.microsoft.com/azure/expressroute/expressroute-introduction
- Microsoft Learn — *ExpressRoute circuits and peerings*: https://learn.microsoft.com/azure/expressroute/expressroute-circuit-peering
- Microsoft Learn — *Connect a virtual network to an ExpressRoute circuit*: https://learn.microsoft.com/azure/expressroute/expressroute-howto-linkvnet-portal-resource-manager
- Microsoft Learn — *ExpressRoute routing requirements*: https://learn.microsoft.com/azure/expressroute/expressroute-routing
- Microsoft Learn — *ExpressRoute frequently asked questions*: https://learn.microsoft.com/azure/expressroute/expressroute-faqs
- Microsoft Learn — *ExpressRoute documentation*: https://learn.microsoft.com/azure/expressroute/
