# Connecting Networks with VNet Peering

In Microsoft Azure, an application typically does not place every virtual machine, service, and dataset inside a single Virtual Network (VNet). Platform teams often run a **hub VNet** hosting shared services, while each application or environment uses its own **spoke VNet**. Resources in different VNets need to communicate over private IP addresses while still respecting network segmentation and access controls.

**VNet peering** is a mechanism that directly connects two Azure Virtual Networks, allowing resources in those networks to communicate across Microsoft's network backbone using private IP addresses, without routing over the public Internet just to move between two VNets. This lesson belongs to the **Virtual Networks and Name Resolution** chapter of the **CLOUD_PROVIDERS_AZURE** module, where learners build Azure application architectures from subscriptions and resource groups through networking, compute, data, monitoring, security, and cost.

The goal is not merely to create a peering link showing the Connected state, but to design non-overlapping addressing, bidirectional routing, name resolution, and proper security policies, followed by connectivity testing and operational cost estimation.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain VNet peering, local VNet peering, and global VNet peering.
- Distinguish peering from VPN Gateway, ExpressRoute, Private Endpoints, and a single flat network.
- Design non-overlapping IP addresses and recognize that peering is **non-transitive**.
- Understand bidirectional peering and the **Allow virtual network access**, **Allow forwarded traffic**, **Allow gateway transit**, and **Use remote gateways** settings.
- Create peering via the Azure Portal and Azure CLI, verify state, and test private IP connectivity.
- Examine the impact of Network Security Groups (NSGs), User Defined Routes (UDRs), Network Virtual Appliances (NVAs), and DNS.
- Diagnose connectivity failures, modify address spaces, remove peering, and account for costs and limits.

## 2. What Is VNet Peering?

A VNet is a logical network boundary in Azure containing an address space and subnets that hold VM network interfaces or VNet-integrated resources. Each VNet can be managed independently by subscription, resource group, deployment region, and organizational policy.

**VNet peering** establishes a connectivity relationship between **two VNets**. When properly configured and permitted by network policies, packets travel between resources using private IP addresses over Microsoft's backbone network.

Peering does not merge two VNets into one: both networks retain their own address spaces, subnets, NSGs, route tables, governance boundaries, and lifecycles. Nor is peering a VPN tunnel configured with customer gateway appliances.

### 2.1. Two Types of Peering

| Type | Location of the Two VNets | Typical Use Case |
|---|---|---|
| **Virtual network peering** (regional/local) | Two VNets in the same Azure region | Connecting an application VNet to a shared services VNet in the same region |
| **Global virtual network peering** | Two VNets in different supported Azure regions | Private communication between applications deployed across different regions |

Examples:

- **Regional**: hub and spoke both in Southeast Asia.
- **Global**: an application VNet in Southeast Asia needs to reach a private service in East Asia.

Both types follow the same core principles for address spaces and bidirectional peering. Regional support, service SKUs, paths, and data transfer pricing should be verified against current Azure documentation and pricing before production rollout.

### 2.2. When Should You Use It?

VNet peering is helpful when:

1. **Separating applications and environments:** distinct VNets for production, testing, or business units that still require specific network flows.
2. **Hub–spoke topologies:** spokes share a DNS resolver, firewall, Bastion, or platform services hosted in the hub.
3. **Separating administrative boundaries:** each team manages its own VNet or resource group while maintaining agreed internal connectivity.
4. **Multi-region connectivity:** distributed workloads needing to communicate over Azure's private network.
5. **Migration/application modernization:** legacy and new systems placed in separate VNets that need to communicate during a transition phase.

Peering is unnecessary when components already reside in the same VNet and can communicate using subnets, NSGs, and routing. Likewise, avoid creating broad peering links if only access to one specific service is needed: consider Private Endpoints or a more targeted service-access pattern.

## 3. Prerequisites and Key Limitations

### 3.1. Non-Overlapping Address Spaces

This is the single most critical requirement. Two VNets to be peered must have **non-overlapping IP address spaces**, including address ranges not yet allocated to subnets.

Valid example:

| Network | Address Space | Illustrative Subnet |
|---|---|---|
| Hub VNet | 10.10.0.0/16 | snet-shared: 10.10.1.0/24 |
| Orders app spoke | 10.20.0.0/16 | snet-app: 10.20.1.0/24 |
| Data spoke | 10.30.0.0/16 | snet-data: 10.30.1.0/24 |

Invalid example:

- VNet A: **10.10.0.0/16**.
- VNet B: **10.10.50.0/24**.

The two networks overlap because 10.10.50.0/24 lies inside 10.10.0.0/16. Do not inspect only active subnets; compare the entire VNet address spaces and any ranges planned for future addition.

If an overlap exists, plan to re-address or use an appropriate intermediate architecture. VNet peering does not perform NAT automatically to resolve colliding ranges.

### 3.2. Peering Must Be Created in Both Directions

For two VNets **A** and **B**, two peering resources are normally required:

- Peering **A → B** created on VNet A.
- Peering **B → A** created on VNet B.

When both are properly established, the connection state becomes **Connected**. If only one side is created, you will see **Initiated** or an incomplete state; do not treat it as a ready bidirectional connection. The Azure Portal can create both sides simultaneously when your account has sufficient permissions, whereas the CLI commands below create each direction explicitly.

Peering is a relationship between two VNets—you do **not** create separate peering links per subnet.

### 3.3. Peering Is Non-Transitive

This is a frequent source of confusion in hub–spoke architectures.

~~~mermaid
flowchart LR
    A["Spoke A<br/>10.20.0.0/16"] <-->|Peering| H["Hub<br/>10.10.0.0/16"]
    H <-->|Peering| B["Spoke B<br/>10.30.0.0/16"]
    A -. "No automatic direct route" .- B
~~~

If A peers with Hub and B also peers with Hub, **A does not automatically connect to B**. For A to communicate with B, you can:

- Create a **direct peering A ↔ B** if it fits your governance model.
- Deploy an **NVA or Azure Firewall in the hub** with appropriate UDRs and forwarded-traffic settings to route through the hub.
- Use another connectivity/transit service suited to the need, such as Azure Virtual WAN.

Never assume that merely enabling Allow forwarded traffic creates full transitive routing. It permits forwarded traffic across a peering link; you still need the appropriate routes, forwarding appliances, and security rules.

### 3.4. Permissions to Create Peering

The operator must hold appropriate permissions to configure peering on the involved VNets, such as the **Network Contributor** role at the relevant scope or a custom role with the required operations. If VNets sit in different subscriptions, permissions must be granted on each respective side.

Cross-subscription peering and certain cross-tenant scenarios are supported when authorization conditions are met. Do not assume an account with Network Contributor on VNet A automatically has rights to modify VNet B. Coordinate with the owner of the other side and use Azure-supported delegation/authorization mechanisms.

### 3.5. Peering Does Not Bypass NSGs or Firewalls

When peering is added:

- NSGs on subnets and NICs are still evaluated.
- Azure Firewall, NVAs, route tables, and network controls can still block or redirect packets.
- Guest OS firewalls still govern connections reaching local processes.
- Applications must still listen on the right IP/port and authorize callers.

In particular, several default NSG rules reference the **VirtualNetwork** service tag, whose effective address set can expand to include peered VNets. As a result, peering can broaden effective reachability if you rely solely on default rules. For production, inspect effective security rules and configure explicit allow/deny rules.

## 4. Hub–Spoke Reference Model

Suppose an organization deploys the **Orders** service in an Azure subscription. The platform team operates a hub for shared services; the application team manages its own spoke. The goal is for a VM or app in the spoke to reach an internal service host in the hub via private IP.

~~~mermaid
flowchart TB
    subgraph Azure["Azure Subscription"]
      subgraph HubRG["rg-network-hub"]
        subgraph HubVnet["vnet-hub — 10.10.0.0/16"]
          HubSubnet["snet-shared — 10.10.1.0/24"]
          Shared["Internal Service<br/>10.10.1.10:443"]
          HubSubnet --- Shared
        end
      end
      subgraph AppRG["rg-orders-prod"]
        subgraph SpokeVnet["vnet-orders-prod — 10.20.0.0/16"]
          AppSubnet["snet-app — 10.20.1.0/24"]
          App["Orders Workload<br/>10.20.1.10"]
          AppSubnet --- App
        end
      end
      HubVnet <-->|"Two symmetric peerings"| SpokeVnet
    end
~~~

| Component | Illustrative Value | Role |
|---|---|---|
| Subscription | Current subscription | Contains both VNets |
| Hub resource group | rg-network-hub | Owns shared network infrastructure |
| Hub VNet | vnet-hub, 10.10.0.0/16 | Provides shared service subnet |
| Application resource group | rg-orders-prod | Owns application resources |
| Spoke VNet | vnet-orders-prod, 10.20.0.0/16 | Hosts the Orders workload |
| Flow to test | 10.20.1.10 → 10.10.1.10:443 | Internal HTTPS from app to service |

These diagrams and values are illustrative, not pre-created resources. The `.10` addresses are only valid if unassigned in those subnets and the target service is actually listening on TCP/443.

### 4.1. What Needs to Be Prepared?

1. An Azure subscription with permissions to create/read VNets and peerings on both sides.
2. Two existing VNets with non-overlapping address spaces.
3. Subnets, test VM/app, and target service deployed if testing live traffic.
4. Known resource group, VNet name, and resource ID for each side.
5. NSGs, firewalls, route tables, DNS, and application rules verified.
6. Estimated peering data transfer costs and resource costs during practice.

If two VNets do not exist yet, create them in an organization-approved sandbox environment. Never modify peering or routing in production without a connectivity diagram, rollback plan, and change management process.

## 5. Setting Up Peering via the Azure Portal

The following steps describe the standard flow; exact labels and button placements may shift as the Azure Portal updates:

1. Open the Azure Portal and search for **Virtual networks**.
2. Select **vnet-hub**.
3. Under the VNet's settings, open **Peerings**, then click **Add**.
4. Name the hub-side peering link, for example **hub-to-orders**.
5. Select remote virtual network **vnet-orders-prod**. If the two VNets are in different subscriptions, pick the right subscription/tenant and use the appropriate identifier mechanism.
6. Configure virtual network access per your design. In a basic direct model, allow VNet traffic between both networks.
7. If the Portal offers creating the remote peer simultaneously, name it **orders-to-hub** and create both sides when permissions allow.
8. Check the peerings list on **both VNets** and verify the connection state.
9. Once the state reaches **Connected**, proceed to check NSGs, routes, DNS, and real connectivity.

Do not enable **gateway transit** or **forwarded traffic** simply to make peering work. Those options serve specialized flows and require additional conditions as covered below.

## 6. Creating and Verifying Peering with Azure CLI

The CLI suits repeatable configuration, pipelines, and documenting hands-on steps. The example below uses **Bash** syntax in Azure Cloud Shell or a workstation with Azure CLI.

### 6.1. Verify Subscription and Retrieve Resource IDs

~~~bash
# Sign in if no session is active
az login

# Select the subscription for the lab exercise
az account set --subscription "<subscription-id>"
az account show --output table

HUB_RG="rg-network-hub"
HUB_VNET="vnet-hub"
APP_RG="rg-orders-prod"
APP_VNET="vnet-orders-prod"

HUB_ID=$(az network vnet show \
  --resource-group "$HUB_RG" \
  --name "$HUB_VNET" \
  --query id --output tsv)

APP_ID=$(az network vnet show \
  --resource-group "$APP_RG" \
  --name "$APP_VNET" \
  --query id --output tsv)

printf "Hub ID: %s\nSpoke ID: %s\n" "$HUB_ID" "$APP_ID"
~~~

Verify both IDs are non-empty and point to the intended VNets before creating peers. If they reside in two subscriptions, fetch each resource ID under the right subscription context using **--subscription** or Azure CLI configuration, ensuring permissions on both sides.

### 6.2. Inspect Address Spaces

~~~bash
az network vnet show \
  --ids "$HUB_ID" \
  --query "{name:name,location:location,addressSpace:addressSpace.addressPrefixes}" \
  --output json

az network vnet show \
  --ids "$APP_ID" \
  --query "{name:name,location:location,addressSpace:addressSpace.addressPrefixes}" \
  --output json
~~~

You should see **10.10.0.0/16** and **10.20.0.0/16**, or other approved non-overlapping ranges. If an address collision is detected, halt setup and redesign first.

### 6.3. Create Peering from Hub to Spoke

~~~bash
az network vnet peering create \
  --resource-group "$HUB_RG" \
  --vnet-name "$HUB_VNET" \
  --name "hub-to-orders" \
  --remote-vnet "$APP_ID" \
  --allow-vnet-access
~~~

The **--remote-vnet** parameter takes the resource ID of the opposite VNet. The **--allow-vnet-access** flag enables VNet-to-VNet traffic across the peering in a basic topology.

### 6.4. Create Reverse Peering from Spoke to Hub

~~~bash
az network vnet peering create \
  --resource-group "$APP_RG" \
  --vnet-name "$APP_VNET" \
  --name "orders-to-hub" \
  --remote-vnet "$HUB_ID" \
  --allow-vnet-access
~~~

After creating both sides, inspect status:

~~~bash
az network vnet peering list \
  --resource-group "$HUB_RG" \
  --vnet-name "$HUB_VNET" \
  --output table

az network vnet peering list \
  --resource-group "$APP_RG" \
  --vnet-name "$APP_VNET" \
  --output table
~~~

To inspect a single peering in detail:

~~~bash
az network vnet peering show \
  --resource-group "$HUB_RG" \
  --vnet-name "$HUB_VNET" \
  --name "hub-to-orders" \
  --query "{state:peeringState,remote:remoteVirtualNetwork.id,allowVnetAccess:allowVirtualNetworkAccess,allowForwarded:allowForwardedTraffic,gatewayTransit:allowGatewayTransit,useRemoteGateways:useRemoteGateways}" \
  --output json
~~~

The goal of the basic example is **Connected** state on both sides. If only one side exists, permissions are missing on one end, or the remote VNet ID is wrong, resolve that before testing data transfer.

### 6.5. Can You Create the VNets First via CLI?

In an empty lab, the following commands illustrate creating resource groups, VNets, and subnets. Run them only when you have permissions, have checked organization-wide address space, and accept creating the lab resources:

~~~bash
# Example: two resource groups in the same region
az group create --name rg-network-hub --location southeastasia
az group create --name rg-orders-prod --location southeastasia

az network vnet create \
  --resource-group rg-network-hub \
  --name vnet-hub \
  --location southeastasia \
  --address-prefixes 10.10.0.0/16 \
  --subnet-name snet-shared \
  --subnet-prefixes 10.10.1.0/24

az network vnet create \
  --resource-group rg-orders-prod \
  --name vnet-orders-prod \
  --location southeastasia \
  --address-prefixes 10.20.0.0/16 \
  --subnet-name snet-app \
  --subnet-prefixes 10.20.1.0/24
~~~

Creating VNets does not automatically create VMs or test services. A **Connected** peering also does not prove applications at both ends can communicate.

## 7. Peering Options You Must Understand Precisely

Azure exposes several peering attributes beyond name and remote VNet. Do not enable all of them by default.

| Attribute / CLI Flag | Meaning | When to Use |
|---|---|---|
| **Allow virtual network access** / **--allow-vnet-access** | Permits access to resources in the peer VNet across the peering | Direct private IP connectivity between two VNets |
| **Allow forwarded traffic** / **--allow-forwarded-traffic** | Accepts traffic **forwarded** from the peered VNet | When traffic passes through an NVA/Azure Firewall or designed forwarding appliance |
| **Allow gateway transit** / **--allow-gateway-transit** | Lets a peered network use the gateway in this VNet under supported conditions | A hub with a VPN/ExpressRoute gateway sharing connectivity |
| **Use remote gateways** / **--use-remote-gateways** | Instructs this VNet to use the peered VNet's gateway | A spoke using the hub's gateway instead of its own |

### 7.1. Allowing VNet Access Does Not Mean Allowing Every Packet

Even when VNet access is enabled on both sides, NSGs, route tables, guest OS firewalls, and applications still determine whether specific connections succeed. Operators must verify **source, destination, protocol, port, and traffic direction**, not just peering status.

### 7.2. Forwarded Traffic: Traffic Passing Through an Intermediary Appliance

Suppose an Azure Firewall in the hub receives traffic from Spoke A and forwards it to Spoke B. For this pattern to work, you generally must:

- Have peerings between each spoke and the hub.
- Enable **Allow forwarded traffic** on the peerings/directions receiving forwarded traffic.
- Configure **UDRs** on relevant subnets to send traffic to the private IP of the firewall/NVA.
- Ensure the appliance can forward packets and firewall policies allow the required flows.
- Verify **forward and return paths** to prevent asymmetric routing.
- Check NSGs and DNS requirements.

Enabling forwarded traffic alone does not create a router or automatically build transitive routes.

### 7.3. Gateway Transit: Using the Hub's Gateway

Common pattern: the hub has a VPN Gateway or ExpressRoute gateway connected to the corporate network; spokes want to use this path to reach on-premises.

~~~mermaid
flowchart LR
    O["On-premises"] <-->|VPN/ExpressRoute| G["Gateway in hub VNet"]
    G --- H["Hub VNet"]
    H <-->|Peering with gateway transit| S["Spoke VNet"]
~~~

General conditions to check:

1. The hub has a valid gateway with routing configured for the requirement.
2. The **hub → spoke** peering enables **Allow gateway transit**.
3. The **spoke → hub** peering enables **Use remote gateways**.
4. The spoke does not simultaneously have an incompatible local virtual network gateway, and cannot use multiple remote gateways via standard peering.
5. On-premises routes, address ranges, access policies, and return paths must be verified.

Gateway transit is completely distinct from forwarded traffic. Gateway transit enables using a peered VNet's virtual network gateway in supported topologies; forwarded traffic handles packets forwarded by an intermediate appliance.

Before enabling in production, check support for the specific gateway type, deployment region, and connectivity service. Never assume any arbitrary gateway can be shared across every spoke.

## 8. Routing: Why Connected Is Still Not Enough

Once peering is established, Azure updates system routing for the peer VNet's prefixes. Resources in VNet A see routes to VNet B's addresses with next hop type **VNet peering**.

However, **User Defined Routes (UDRs)**, gateway routes, policies, and forwarding behavior can alter the expected path. Always inspect effective routes on the workload's network interface rather than inferring from diagrams alone.

### 8.1. Direct Path

In the basic example, packets from **10.20.1.10** to **10.10.1.10** traverse the spoke-to-hub peering if:

- Both VNets are successfully peered.
- VNet access is allowed.
- Effective routes direct traffic for the peer prefix over peering.
- NSGs and firewalls allow TCP/443.
- The hub service host has the expected IP and listens on port 443.

Public IPs are not needed on either machine solely to communicate over VNet peering.

### 8.2. UDR Redirecting Through a Firewall

If all spoke-to-hub traffic must traverse a firewall, configure UDRs with next hop **Virtual appliance** and the firewall's private IP on the relevant subnets. However, design return routes, policies, and allowed address scopes so you do not inadvertently block DNS, platform endpoints, or essential management traffic.

A common mistake is sending outbound traffic through the firewall while return traffic bypasses it or uses another gateway. When troubleshooting, inspect both directions and session state on the appliance.

### 8.3. Inspecting Effective Routes

If the workload is a VM with an eligible network interface, you can view its effective route table via CLI:

~~~bash
az network nic show-effective-route-table \
  --resource-group "<vm-resource-group>" \
  --name "<nic-name>" \
  --output table
~~~

Reading effective routes may depend on VM power state, permissions, and supported conditions. Look for the route targeting the peer prefix, its next hop, and any UDR or gateway routes whose precedence affects the connection. If the route is missing, check peering state and address space synchronization.

## 9. NSGs, Firewalls, and Trust Boundaries

Peering provides only **network-layer reachability**; do not turn it into unrestricted application access.

### 9.1. NSG Rules in the Sample Scenario

If the hub service uses TCP/443 and only spoke workloads should call it, write rules with specific source and destination scopes. For example:

| Criterion | Illustrative Value |
|---|---|
| Direction | Inbound |
| Protocol | TCP |
| Source address | 10.20.1.0/24 |
| Destination address | 10.10.1.10 or the service subnet |
| Destination port | 443 |
| Action | Allow |
| Priority | Lower number than applicable deny rules |

Do not open management ports 22/3389 from every peered VNet unless genuinely required. Once explicit allows are added, review broader rules on both subnets and NICs, especially the default VirtualNetwork rules.

NSGs are stateful for active connections as supported by the service; still verify connection initiation direction, intermediate firewalls, and return routes.

### 9.2. Azure Firewall in the Hub

A hub running Azure Firewall can centralize flow control across multiple VNets. However, the firewall is not automatically placed inline merely because VNets peer with the hub. You still need proper UDRs, peering forwarded traffic, and firewall policy rules.

If two spokes have a direct peering or an alternate route, traffic may bypass the firewall contrary to intent. Always check effective routes and test to verify the actual path.

### 9.3. Separating Trust Zones

Between production and development environments:

- Evaluate whether full VNet peering is needed or only access via a service endpoint.
- Use NSGs and firewalls to narrow allowed sources and ports.
- Separate identities and administrative permissions across teams.
- Do not treat VNet peering as a user authentication barrier.
- Use TLS or application-level encryption when policy mandates data-in-transit protection; never treat peering as an automatic substitute for application-layer encryption.

## 10. DNS: IP Reachability Does Not Mean Name Resolution Works

Workloads normally call services by name such as **api.orders.internal** rather than by IP address. After peering shows Connected, you might ping or connect by private IP yet still fail to reach the service by name.

VNet peering primarily solves **IP reachability and routing**, not a shared DNS system that automatically resolves every host name across peered VNets.

### 10.1. Azure-Provided DNS

Azure-provided DNS supports resolution within a VNet's context, but **does not automatically resolve hostnames in a peered VNet** merely because peering exists. Design DNS explicitly whenever services call each other by hostname.

### 10.2. Private DNS Zone

A common pattern uses an Azure Private DNS Zone linked to the VNets needing resolution.

~~~mermaid
flowchart TD
    Z["Private DNS Zone<br/>orders.internal"] --> L1["Virtual Network Link: vnet-hub"]
    Z --> L2["Virtual Network Link: vnet-orders-prod"]
    L1 --> H["Workload in hub"]
    L2 --> S["Workload in spoke"]
    S -->|Query api.orders.internal| Z
~~~

Notes:

- Appropriate records must exist (`A`, `CNAME`, or others as required).
- Link the zone to every VNet that needs to query it; auto-registration applies only under supported conditions and does not register every service name automatically.
- If using custom DNS servers or Azure DNS Private Resolver, configure forwarders and network paths to the DNS servers properly.
- NSGs/firewalls and routing must permit DNS queries to custom DNS servers.
- Private Endpoints generally require proper private DNS configuration so the service's hostname resolves to its assigned private IP.

### 10.3. DNS Verification Workflow

1. From the spoke workload, query the hostname using **nslookup** or **dig**.
2. Note which DNS server responded.
3. Confirm the returned IP matches the intended private IP.
4. Check zone, virtual network links, records, and forwarders if `NXDOMAIN` or an unexpected IP is returned.
5. Once DNS returns the right IP, test the target port and verify the TLS certificate.

Never use successful name resolution as proof that a firewall permits the application port. DNS only identifies the target address; actual connectivity must be tested separately.

## 11. End-to-End Connectivity Testing

After peering reaches Connected, verify connectivity in order so you can isolate which layer fails.

### 11.1. Step A: Confirm Peering

~~~bash
az network vnet peering show \
  --resource-group rg-network-hub \
  --vnet-name vnet-hub \
  --name hub-to-orders \
  --query "{state:peeringState,remote:remoteVirtualNetwork.id}" \
  --output json

az network vnet peering show \
  --resource-group rg-orders-prod \
  --vnet-name vnet-orders-prod \
  --name orders-to-hub \
  --query "{state:peeringState,remote:remoteVirtualNetwork.id}" \
  --output json
~~~

Both must reference the correct remote VNet and report **Connected**.

### 11.2. Step B: Confirm Routes

Inspect effective routes on the application VM's NIC, specifically the route to **10.10.0.0/16**. If UDRs exist, confirm why the next hop may no longer be VNet peering.

### 11.3. Step C: Test TCP Connectivity

On a Linux VM in the spoke with appropriate tools:

~~~bash
# Test TCP/443 to the private service in the hub
nc -vz -w 5 10.10.1.10 443

# If the HTTPS service is actually running on the target
curl -vk --connect-timeout 5 https://10.10.1.10/
~~~

Depending on the tool and certificate, calling HTTPS by IP address can report a hostname mismatch; that is a TLS/hostname validation error, not necessarily a routing error. For clean verification, call using a valid hostname and matching certificate instead of skipping TLS checks. Use **-k** only for lab diagnostics, never in production applications.

On Windows, you can test with:

~~~powershell
Test-NetConnection -ComputerName 10.10.1.10 -Port 443
~~~

Some hosts block ICMP/ping via firewall, so a failed ping is **not sufficient** to conclude VNet peering is broken. Prefer testing the actual protocol and port used by the application.

### 11.4. Step D: Check the Application Layer

Even when TCP/443 is open, HTTP requests can still fail due to host headers, authentication, certificates, backend health, or application policies. Collect client and server logs to separate network-layer issues from application-layer issues.

### 11.5. Azure Diagnostic Tools

- **Network Watcher – Connection troubleshoot:** tests reachability from an Azure source to a supported destination and helps locate failing hops.
- **Network Watcher – IP flow verify:** determines whether NSG rules allow or deny a given IP flow on supported resources.
- **Effective security rules:** inspects active NSG rules on a NIC.
- **Effective routes:** shows paths resulting from system routes, UDRs, and related routes.
- **NSG flow logs or appropriate network logging mechanisms:** views traffic traces when configured and supported, noting service and logging capability updates over time.

Do not assume Network Watcher or every logging type is enabled by default. Before using a tool, verify support conditions, region, permissions, and storage costs.

## 12. Common Errors and Resolutions

| Symptom | Possible Cause | Verification / Fix |
|---|---|---|
| Cannot create peering | Overlapping address spaces | Compare full address spaces, not only existing subnets |
| Cannot create remote peer | Missing permissions in the other subscription/VNet | Check Azure RBAC on both VNets and coordinate with owners |
| **Initiated** state | Only one side exists or remote side incomplete | Create/check reverse peering and remote VNet ID |
| **Disconnected** state | One side's peering was deleted or out of sync | Inspect both sides, clean up broken peering, recreate properly |
| **Connected** yet TCP fails | NSG, OS firewall, service not listening, or wrong route | Check effective rules, routes, and service listener |
| Only one direction works | Asymmetric rules or routes, host firewall/app issue | Check both forward and return paths |
| Spoke A cannot reach Spoke B via hub | Peering is non-transitive | Add direct peering or configure NVA/UDR/forwarded traffic |
| IP works but hostname fails | DNS zone/record/link/forwarder misconfigured | Check resolver, zone links, and nslookup results |
| IP works but HTTPS errors | Hostname/certificate mismatch or TLS policy | Check SNI, DNS, and application certificate |
| Added new prefix but route missing | Peering requires address space sync | Check new prefix, ensure no overlap, sync peering per Azure docs |
| Cannot reach on-premises from spoke | Missing gateway transit, routes, gateway, or on-prem route | Check allow gateway transit, use remote gateways, and return path |
| Traffic bypasses Azure Firewall | Missing UDR or incorrect next hop | Check effective routes across subnets and path symmetry |
| Unexpected charges | Peering data transfer, global transfer, or firewall/gateway usage | Review Cost Management and regional pricing |

### 12.1. Interpreting States

- **Initiated:** the opposite side's relationship is incomplete or only one end is configured.
- **Connected:** both ends of the peering are established, though application traffic is not guaranteed to pass.
- **Disconnected:** one side of the relationship may have been deleted or become incomplete; investigate rather than assuming it will self-heal.

Verify exact state names and behaviors against current Azure documentation, especially when changing addressing, configs, or peerings during large deployments.

## 13. Modifying Address Spaces After Peering

Sometimes an application needs additional subnets and address space. For example, a spoke uses 10.20.0.0/16 and needs to expand with **10.21.0.0/16**.

Safe workflow:

1. Check the organization-wide IP allocation registry and all peered VNets to confirm the added prefix does not overlap.
2. Assess impact on routing, NSGs, firewalls, DNS, gateways, and on-premises systems.
3. Update the VNet's address space using a supported procedure.
4. Sync peering if required by Azure so peers receive the new prefix.
5. Verify effective routes, NSGs, and actual connectivity.

The CLI supports peering synchronization in eligible scenarios:

~~~bash
az network vnet peering sync \
  --resource-group rg-network-hub \
  --vnet-name vnet-hub \
  --name hub-to-orders

az network vnet peering sync \
  --resource-group rg-orders-prod \
  --vnet-name vnet-orders-prod \
  --name orders-to-hub
~~~

Adding or modifying prefixes does not always require deleting and recreating peering. Still, verify support conditions for the change type, dependent resources, and system state. Never modify prefixes in production without an addressing transition plan.

## 14. Comparing VNet Peering with Other Connectivity Options

| Technology | Primary Purpose | Key Distinction |
|---|---|---|
| **VNet peering** | Private IP connectivity between two Azure VNets | Direct path over backbone; each VNet retains its own config; non-transitive by default |
| **VPN Gateway / VNet-to-VNet VPN** | Connectivity over VPN tunnels in appropriate scenarios | Uses gateways and VPN/IPsec; different operations, performance, and cost vs. peering |
| **ExpressRoute** | Private connectivity between enterprise infrastructure and Microsoft services | Commonly used for on-premises/hybrid networks; not a default replacement for all VNet links |
| **Azure Virtual WAN** | Managing multi-site/branch/VNet connectivity at broad scale | Managed hub and routing model tailored to large-scale transit |
| **Private Endpoint / Private Link** | Access a specific resource/service via private IP | Does not create full-mesh VNet connectivity; usually requires private DNS |
| **NVA / Azure Firewall + UDR** | Inspect, filter, and forward traffic by policy | Requires routing design and operational fees; typically complements peering |
| **Single VNet** | Subnets inside one shared VNet | Simpler when separate VNet governance boundaries are unnecessary |

Choose based on requirements: number of networks, full-network access vs. single-service access, transitive routing, mandatory encryption, security policy, scalability, cost, and operational ownership.

## 15. Production Design: Performance, Availability, and Cost

### 15.1. Performance and Latency

VNet peering delivers high-throughput private IP traffic, though actual performance still depends on:

- VNet regions and geographic distance.
- VM/service sizes and network bandwidth limits at both ends.
- Bandwidth, application latency, TCP behavior, and concurrent connections.
- NSGs, UDRs, firewalls/NVAs, and additional hops.
- Platform limits or constraints of the services in use.

Never promise that global peering will match intra-region latency. Test with representative workloads and measure results before committing latency-sensitive architectures.

### 15.2. Availability and Configuration Changes

VNet peering is an Azure-managed connectivity service, but applications must still design high availability for their own components. For critical services:

- Assess blast radius before changing routes, peerings, DNS, or firewalls.
- Deploy gateways, firewalls/NVAs, and DNS in high-availability topologies if they sit inline.
- Monitor response times, connection error rates, and target service health.
- Maintain rollback runbooks for UDRs, NSG rules, and peering changes.

### 15.3. Cost

Never assume peering is free just because no VPN Gateway is provisioned. Azure charges for **data transferred across VNet peering** according to the applicable model and regions, where regional and global peering may carry different rates or billing rules. Other components such as Azure Firewall, VPN Gateway, Private DNS Resolver, and logging data have their own pricing models.

Example cost analysis:

- Estimate monthly GB transferred between hub VNet and spoke VNet in **each direction**.
- Identify both regions involved if using global peering.
- Cross-check current Azure VNet peering pricing for the specific regions and link type.
- Add firewall, gateway, and monitoring charges if traffic traverses them.
- Track actual spend in Azure Cost Management after deployment.

Never quote fixed unit prices without checking the target region, current pricing table, and effective date.

### 15.4. Scalability and Lifecycle

As the number of spokes grows, so do peerings, UDRs, rules, private DNS links, and permission scopes. A two-VNet topology can be configured manually; an environment with dozens or hundreds of VNets should use Infrastructure as Code and consider centralized network governance.

A sound change process should include:

1. Centralized IP address planning to prevent overlaps.
2. Consistent source–destination peering naming conventions.
3. Storing peering, route, NSG, and DNS configurations in Infrastructure as Code where appropriate.
4. Pull-request reviews to catch unintended connectivity paths.
5. Pre- and post-deployment connectivity and security testing.
6. Tracking costs, owners, and expiration dates for temporary links.

## 16. Cleaning Up Lab Resources and Troubleshooting Peering Removal

If practicing connectivity between two dedicated lab VNets, delete the peering relationship from **both sides** when no longer needed:

~~~bash
az network vnet peering delete \
  --resource-group rg-network-hub \
  --vnet-name vnet-hub \
  --name hub-to-orders

az network vnet peering delete \
  --resource-group rg-orders-prod \
  --vnet-name vnet-orders-prod \
  --name orders-to-hub
~~~

Then check the peering list on both VNets. Never delete production VNets, subnets, or resource groups. If VNets were created solely for a lab, delete them only after confirming no needed resources or data remain, checking dependencies, and obtaining owner approval.

If resolving a **Disconnected** peering caused by deleting the remote side, audit both ends and recreate the peering once configuration is aligned. Avoid leaving orphaned peerings or manual routes pointing to deleted appliances.

## 17. Pre-Production Checklist

- [ ] Both VNets have non-overlapping address spaces with growth capacity reserved.
- [ ] Owners, subscriptions, resource groups, and peering permissions on both sides are confirmed.
- [ ] Both peering directions exist, reference the correct resource IDs, and show Connected.
- [ ] All required flows are documented by source, destination, port, protocol, and authentication requirements.
- [ ] NSGs, OS firewalls, and application rules permit only necessary traffic.
- [ ] Effective routes in both forward and return directions are valid, especially with UDRs and firewalls.
- [ ] No assumption of transitive peering across multiple spokes.
- [ ] Forwarded traffic / gateway transit enabled only when genuinely required by the architecture and verified.
- [ ] Private/custom DNS is designed and resolves hostnames to the intended IPs.
- [ ] Tested TCP/application connectivity, TLS, and denied access paths.
- [ ] Assessed change risk, rollback, performance, and cost.
- [ ] Configuration captured in IaC/documentation with a designated operational owner.

## 18. Hands-On Exercises

### Exercise 1: Connecting Two VNets in the Same Region

Create two lab VNets with non-overlapping address spaces, such as 10.10.0.0/16 and 10.20.0.0/16. Set up bidirectional peering via Azure CLI, confirm the Connected state, and describe the additional conditions required for a VM in the spoke to connect to a TCP/443 service in the hub.

**Pass criteria:** both peerings created, non-overlapping addresses, correct state, knows how to check NSGs/routes/ports, does not conclude readiness solely from Connected.

### Exercise 2: Analyzing a Three-VNet Hub–Spoke Network

Hub uses 10.10.0.0/16, Spoke A uses 10.20.0.0/16, and Spoke B uses 10.30.0.0/16. Both A and B peer with the hub yet cannot reach each other.

Explain the non-transitivity of peering. Propose two architectures for A to reach B and compare their impacts on routing, cost, and security.

### Exercise 3: Diagnosing DNS

A workload in the spoke connects to **10.10.1.10:443** successfully, but calling **api.orders.internal** fails.

List checks for the DNS client, zone, records, virtual network links, DNS server, and certificates. Explain why adding another NSG allow rule will not necessarily fix this error.

### Exercise 4: Designing Gateway Transit

The Hub VNet has a VPN Gateway connected to on-premises. The Spoke has no gateway of its own and needs to reach an on-premises subnet. Draw a diagram and explain the roles of Allow gateway transit on the hub, Use remote gateways on the spoke, return routes, and the limitation when a spoke already has its own gateway.

### Self-Check Questions

1. Why can two VNets with overlapping IP ranges not peer directly?
2. Can two VNets in different Azure regions peer under supported conditions?
3. Does Connected peering guarantee TCP/443 will work?
4. Do three VNets A–Hub–B automatically communicate A↔B through the hub?
5. Does Allow forwarded traffic automatically create an NVA or transitive routes?
6. When should you use a Private Endpoint instead of peering an entire VNet?
7. Why must you design DNS explicitly for service names in a peered VNet?
8. When expanding an address space, why must you inspect peering synchronization and effective routes?
9. How can regional peering vs. global peering affect costs?

## 19. References

- [Azure Virtual Network peering — Microsoft Learn](https://learn.microsoft.com/azure/virtual-network/virtual-network-peering-overview)
- [Create, change or delete a virtual network peering](https://learn.microsoft.com/azure/virtual-network/virtual-network-manage-peering)
- [Azure virtual network traffic routing](https://learn.microsoft.com/azure/virtual-network/virtual-networks-udr-overview)
- [Azure Network Security Groups](https://learn.microsoft.com/azure/virtual-network/network-security-groups-overview)
- [Azure Private DNS](https://learn.microsoft.com/azure/dns/private-dns-overview)
- [Azure VPN Gateway: Configure gateway transit for virtual network peering](https://learn.microsoft.com/azure/vpn-gateway/vpn-gateway-peering-gateway-transit)
- [Network Watcher connection troubleshoot](https://learn.microsoft.com/azure/network-watcher/network-watcher-connectivity-overview)
- [Azure Virtual Network pricing](https://azure.microsoft.com/pricing/details/virtual-network/)
