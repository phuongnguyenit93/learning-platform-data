# Route Tables, System Routes, and User-Defined Routes

When a virtual machine in an Azure Virtual Network (VNet) sends a packet to a destination IP address, Azure must determine the **next hop**: forward directly within the virtual network, route to the Internet, send via a virtual network gateway, pass through a network virtual appliance, or drop the packet. This decision relies on the network interface's **effective routing table**, composed of Azure-provided routes and administrator-configured routes.

This lesson belongs to the **Virtual Networks and Name Resolution** chapter of the **CLOUD_PROVIDERS_AZURE** module. The module explores Microsoft Azure from subscriptions, resource groups, and Entra ID to virtual networks, compute services, storage, data, deployment, monitoring, security, and cost control. After learning how to create VNets and subnets, you need routing to control traffic paths across subnets, VNets, on-premises networks, and the Internet. DNS resolves names to IP addresses; **routing decides the path to that IP address**. The two functions are related but do not replace each other.

After this lesson, you will be able to:

- Explain the relationship between subnets, system routes, route tables, and effective routes.
- Distinguish between system routes, user-defined routes (UDRs), and BGP-learned routes.
- Predict the selected route using **longest prefix match** and tie-breaking precedence for identical prefixes.
- Choose the appropriate next hop for Internet, internal networks, on-premises networks, and network virtual appliances (NVAs).
- Create route tables, add UDRs, and associate route tables with subnets using the Azure Portal or Azure CLI.
- Inspect effective routes and use Network Watcher to diagnose misrouted traffic.
- Identify risks around routing loops, asymmetric return paths, IP forwarding, and costs.

## 1. Where Does Routing Occur in Azure?

A VNet is a logical network scope containing CIDR address spaces and subnets. Each virtual machine's network interface (NIC) connects to a subnet. When a NIC transmits an IP packet, the Azure infrastructure evaluates the effective routes for that NIC to choose the next hop.

A route typically consists of these components:

| Component | Meaning | Example |
|---|---|---|
| Address prefix | Destination network in CIDR notation | 10.40.0.0/16 |
| Next hop type | Category of the next hop | VirtualAppliance |
| Next hop IP | IP address of the NVA if required by the next hop type | 10.20.2.4 |
| Source | Origin of the route: system, user, or BGP | User |
| State | Operational status of the route in effective routes | Active or Invalid depending on evaluation |

For example, the route **10.40.0.0/16 → VirtualAppliance 10.20.2.4** means traffic destined for network 10.40.0.0/16 is forwarded to the NVA with private IP 10.20.2.4, provided that route is selected and the path to the NVA is valid.

To understand routing, distinguish three concepts:

1. **System route:** automatically created by Azure when a VNet/subnet exists or when compatible network connections are configured.
2. **User-defined route (UDR):** explicitly configured by administrators to override or shape desired traffic paths.
3. **Effective routes:** the combined set of routes active on a NIC after Azure evaluates system routes, UDRs, and BGP-propagated routes.

An Azure **route table** resource primarily holds **UDRs** and settings related to BGP propagation. It does not mean every system route lives inside a route table resource you created. A NIC still has effective routes even when its subnet is not associated with any custom route table.

## 2. System Routes: Routes Created Automatically by Azure

When you create a VNet, Azure automatically provisions baseline routes. Common ones include:

| Address Prefix | Typical System Next Hop | Meaning |
|---|---|---|
| VNet address space, e.g., 10.20.0.0/16 | Virtual network | Routes traffic between addresses inside the VNet |
| 0.0.0.0/0 | Internet | Default route for destinations not matching a more specific route |
| 10.0.0.0/8 | None | Drops traffic to this private range unless a more specific route exists |
| 172.16.0.0/12 | None | Same for this private IPv4 range |
| 192.168.0.0/16 | None | Same for this private IPv4 range |
| 100.64.0.0/10 | None | Shared address space handled by Azure baseline routing |

The sample routes above describe common IPv4 routing. Azure may generate additional system routes depending on VNet addressing and network features; IPv6 also has its own behavior. **Do not treat this table as an exhaustive static list of all effective routes.** Inspect effective routes on an actual NIC to verify the result.

### Why Can VNet 10.20.0.0/16 Still Communicate When 10.0.0.0/8 → None Exists?

A packet destined for **10.20.1.10** matches both **10.0.0.0/8** and **10.20.0.0/16**. Azure picks the **/16** prefix because it is more specific than **/8**. Consequently, the packet is routed inside the VNet rather than dropped by the broader None route.

### Additional System Routes That Can Be Added

- **VNet peering:** Azure adds routes to the peered VNet's address space with a peering next hop.
- **Virtual network gateway:** when VPN/ExpressRoute connections and route propagation are configured, routes to external networks can appear in effective routes.
- **Service-specific routes:** certain services and network configurations inject specialized routes; routing behavior should be verified on the workload's NIC.

The default system route 0.0.0.0/0 → Internet **does not guarantee** Internet reachability for a VM. Outbound access also depends on outbound connectivity methods (such as NAT Gateway or a supported egress path), NSGs, firewalls, resource state, and other policies. A route only specifies the intended path.

## 3. User-Defined Routes (UDRs) and the Route Table Resource

A **UDR** enables administrators to override or supplement routing choices. You create a **route table**, add routes to it, and **associate** the route table with the target subnet.

~~~text
VNet: vnet-app (10.20.0.0/16)
    |
    +-- subnet-app (10.20.1.0/24) -- [rt-app]
    |                                  |
    |                                  +-- 0.0.0.0/0
    |                                       next hop: 10.20.2.4 (NVA)
    |
    +-- subnet-nva (10.20.2.0/24)
                |
                +-- Firewall/NVA: 10.20.2.4
~~~

In this example, workloads in subnet-app send traffic matching 0.0.0.0/0 to the NVA instead of using the default Internet system route. For destinations inside the VNet itself, the more specific system route still typically wins over 0.0.0.0/0.

Scoping rules to remember:

- UDRs are applied by **associating a route table with a subnet**, not by attaching a route table directly to individual VMs.
- A subnet can be associated with at most **one route table** at a time.
- A single route table can be associated with **multiple subnets**, within Azure's limits and networking requirements.
- A route table is an independent resource. Deleting a route table or editing routes on a shared table affects all associated subnets simultaneously.
- Subnets not associated with that table are unaffected by its UDRs.
- Azure computes effective routes per NIC; exact routes may vary across subnets, peerings, gateways, and related policies.

### When Should You Use UDRs?

| Goal | Example UDR | Notes |
|---|---|---|
| Route egress through a central firewall | 0.0.0.0/0 → VirtualAppliance | The NVA must forward packets and have a valid egress path |
| Steer traffic to a target network via an appliance | 10.40.0.0/16 → VirtualAppliance | Check return paths and NVA reachability to the target |
| Explicitly drop traffic to a range | 198.51.100.0/24 → None | Controls routing only; does not replace a firewall |
| Explicitly direct traffic to the Internet | 0.0.0.0/0 → Internet | Evaluate security impact, forced tunneling, and outbound connectivity |
| Route via a virtual network gateway when supported | On-premises network prefix → VirtualNetworkGateway | Depends on gateway architecture, configuration, and route propagation |

UDRs determine the **path**, not packet content inspection or port-based allow/deny filtering like NSGs or firewalls.

## 4. UDR Next Hop Types

Commonly used next hop types:

| Next Hop Type | Primary Behavior | Use Case |
|---|---|---|
| **Virtual network** | Forwards traffic within VNet infrastructure toward reachable destinations | Custom routes needing to point back to the VNet |
| **Internet** | Routes traffic along Azure's Internet path | Explicitly choosing the Internet path when required |
| **Virtual appliance (VirtualAppliance)** | Sends packets to the private IP of an NVA/firewall | Centralized traffic inspection, filtering, or steering |
| **Virtual network gateway (VirtualNetworkGateway)** | Forwards traffic through an eligible gateway | On-premises networks over gateway connections |
| **None** | Drops packets matching the route | Blocking routing to a prefix |

When selecting **VirtualAppliance**, you must configure a **next hop IP address**. This is typically the private IP address of an appliance reachable over the Azure network. That IP must belong to a valid routing architecture, and the appliance must be configured to forward packets toward the destination network.

**None** is a next hop type that drops packets when that route is selected. It is useful for routing tests and certain cases where you want to blackhole a path to a destination. However, if you need access control by source, destination, protocol, port, user, or application, use NSGs/firewalls and corresponding policies.

**VirtualNetworkGateway** is not a universal default for every connection to another network. It is valid only when the architecture has an eligible gateway and related routing conditions are met. Architectures like hub-spoke, Azure Virtual WAN, or VPN/ExpressRoute have specific routing requirements that must be checked against service documentation.

## 5. How Does Azure Choose a Route? Longest Prefix and Precedence

The primary rule is **longest prefix match**: when multiple routes match the same destination address, Azure prefers the route with the **longest prefix** (the most specific destination network). For example, /24 is more specific than /16, and /16 is more specific than /0.

If multiple routes match the **exact same prefix**, the standard precedence order is:

1. **User-defined route (UDR)**.
2. **BGP route**.
3. **System route**.

This precedence order applies **only after comparing prefix lengths**. A /24 system route can beat a /16 UDR because /24 is more specific. A /24 BGP route can also beat a /16 UDR. Never assume a UDR always overrides every route regardless of prefix length.

### Path Calculation Example

Suppose a VM sits in VNet **10.20.0.0/16**. After configuring a gateway and route table, effective routes might contain the following entries:

| Source | Prefix | Next Hop |
|---|---|---|
| System | 10.20.0.0/16 | Virtual network |
| System | 10.0.0.0/8 | None |
| System | 0.0.0.0/0 | Internet |
| User | 10.40.0.0/16 | VirtualAppliance 10.20.2.4 |
| BGP | 10.40.8.0/24 | Virtual network gateway |
| User | 0.0.0.0/0 | VirtualAppliance 10.20.2.4 |

For each destination IP:

| Destination IP | Matching Routes | Selected Route | Reason |
|---|---|---|---|
| 10.20.1.20 | 10.0.0.0/8, 10.20.0.0/16, 0.0.0.0/0 | System 10.20.0.0/16 | /16 is more specific than /8 and /0 |
| 10.40.8.25 | 10.0.0.0/8, UDR 10.40.0.0/16, BGP 10.40.8.0/24, 0.0.0.0/0 | BGP 10.40.8.0/24 | /24 is the most specific |
| 10.40.50.25 | 10.0.0.0/8, UDR 10.40.0.0/16, 0.0.0.0/0 | UDR 10.40.0.0/16 | /16 is the most specific |
| 8.8.8.8 | System 0.0.0.0/0, UDR 0.0.0.0/0 | UDR 0.0.0.0/0 | Both are /0; User takes precedence over System |

This example is a **hypothetical** route set meant to illustrate route selection mechanics; BGP routes only appear when a gateway and route propagation are configured. Actual effective routes may differ based on configuration rules and system connectivity.

### What If a Route Has an Invalid State?

Never read prefixes alone and conclude a route is active. In **Effective routes**, also inspect **State** (e.g., Active/Invalid), Source, and Next hop. An Invalid route is not used as an active forwarding path. Some routes may be invalidated because a higher-precedence route overrides them or due to configuration issues; rely on the observed state and actual diagnostic tools.

## 6. Design Scenario: Forcing Egress Through a Firewall/NVA

In a hub-spoke or internal VNet architecture, you may want all outbound traffic to pass through a firewall for logging and policy enforcement.

~~~text
Application VM
10.20.1.10 (subnet-app)
       |
       | UDR: 0.0.0.0/0 -> 10.20.2.4
       v
Firewall/NVA
10.20.2.4 (subnet-nva)
       |
       | Firewall rules, SNAT/appropriate routing
       v
External / Internet Destination
       |
       | Return path must be valid
       v
Application VM receives response
~~~

Technical prerequisites:

- **The NVA must forward packets:** if using a VM as a router/firewall, enable **IP forwarding** on the Azure NIC and configure forwarding inside the OS/application. Azure Firewall is a managed service with its own deployment model and next hop behavior.
- **Path to the NVA exists:** IP 10.20.2.4 must be a next hop address reachable from the source network.
- **Return path exists:** verify routes from the NVA to the destination network and return routes back to the source machine. Asymmetric paths can cause stateful firewalls to drop packets.
- **Check NSGs and firewalls:** a valid route alone is not enough; NSGs and firewall policies can still block traffic.
- **Avoid routing loops:** do not configure a route on the NVA's own subnet pointing back to the NVA or looping between two appliances.
- **Consider HA:** if the NVA fails, the UDR may still forward packets to an unresponsive next hop. Design high availability and failover appropriately.

**Forced tunneling** redirects default traffic through a central inspection point or on-premises network. It helps security and auditing, but can increase latency, introduce dependencies on firewalls/gateways, and impact Azure service traffic. Evaluate exceptions, required service access, and routing policies before deploying to production.

## 7. BGP Routes and Gateway Route Propagation

When using VPN Gateway or ExpressRoute, routes from connected networks can be advertised via **BGP** so Azure learns how to reach on-premises prefixes.

For example, the corporate office advertises **172.20.0.0/16** over a VPN Gateway. When BGP routes propagate to the application subnet, VMs in that subnet learn the route to 172.20.0.0/16 via the gateway without requiring manual UDRs on every subnet.

A route table provides a **BGP route propagation** setting. If you disable propagation on a subnet's route table, BGP routes advertised by the gateway will not appear in that subnet's effective routes. This is useful in certain designs that intentionally steer everything via UDRs, but it can also break workload connectivity to on-premises networks.

When evaluating propagation:

1. Identify which prefixes the gateway advertises and where those prefixes are needed.
2. Check gateway sharing and related configuration requirements if using VNet peering.
3. Check whether UDRs have more specific prefixes or overlap with BGP prefixes.
4. Inspect effective routes before and after changes and test bidirectional connectivity.

**Do not disable BGP propagation merely to suppress one unwanted route** without understanding the impact across VPN/ExpressRoute connections. Certain special subnets and network services have specific route table and propagation requirements.

## 8. Configuring a Route Table in the Azure Portal

Suppose you have a VNet with an application subnet and need a UDR directing destination network **10.40.0.0/16** through an appliance.

1. Open the [Azure Portal](https://portal.azure.com/) and verify your subscription and resource group.
2. Search for **Route tables** and select **Create**.
3. Choose subscription, resource group, region, and a recognizable name such as **rt-app-egress**.
4. Review the **Propagate gateway routes** option and set it to match your architecture.
5. Create the route table.
6. Inside the route table, open **Routes > Add**. Enter name **to-remote-via-nva**, address prefix **10.40.0.0/16**, next hop type **Virtual appliance**, and next hop address **10.20.2.4**.
7. Go to **Subnets > Associate** (or edit the subnet inside the VNet) and attach the route table to the right application subnet.
8. Verify which subnet is associated with the route table and confirm using effective routes on a VM's NIC in that subnet.

Portal labels or layouts may vary over time. If a route table is associated with multiple subnets, editing **Routes** affects all of them.

## 9. Configuring with Azure CLI

The following commands illustrate creating a route table and UDR without requiring an active application. Select the right subscription and substitute resource names from your own environment.

### Check Account and Subscription

~~~bash
az login
az account list --output table
az account set --subscription "<SUBSCRIPTION_ID>"
az account show --output table
~~~

In Cloud Shell, the account is usually already signed in. Always verify the active subscription before modifying resources.

### Create a Route Table

~~~bash
az network route-table create \
  --resource-group rg-az-routing-lab \
  --name rt-app-lab \
  --location southeastasia
~~~

The example uses Bash line-continuation syntax. In PowerShell, either write it on one line or use PowerShell's line-continuation character. Replace the region with one permitted in your subscription.

### Add a Route to an NVA

Suppose destination network **10.40.0.0/16** must traverse appliance **10.20.2.4**:

~~~bash
az network route-table route create \
  --resource-group rg-az-routing-lab \
  --route-table-name rt-app-lab \
  --name to-remote-via-nva \
  --address-prefix 10.40.0.0/16 \
  --next-hop-type VirtualAppliance \
  --next-hop-ip-address 10.20.2.4
~~~

**Run the command above only if NVA 10.20.2.4 actually exists and has a valid forwarding path.** If no NVA is deployed, use the NVA-free lab in Section 12.

### Associate the Route Table with a Subnet

~~~bash
az network vnet subnet update \
  --resource-group rg-az-routing-lab \
  --vnet-name vnet-routing-lab \
  --name snet-app \
  --route-table rt-app-lab
~~~

Associating a route table with a subnet changes the routing behavior for workloads inside that subnet. If the subnet already runs live applications, assess the impact beforehand and schedule an appropriate change window.

### Verify the Route Table and Configured Routes

~~~bash
az network route-table show \
  --resource-group rg-az-routing-lab \
  --name rt-app-lab \
  --output json

az network route-table route list \
  --resource-group rg-az-routing-lab \
  --route-table-name rt-app-lab \
  --output table
~~~

Inspect the subnet's route table association:

~~~bash
az network vnet subnet show \
  --resource-group rg-az-routing-lab \
  --vnet-name vnet-routing-lab \
  --name snet-app \
  --query "{name:name, routeTable:routeTable.id}" \
  --output json
~~~

The **show/list** commands verify the configuration of the route table and subnet. They do not prove live packets traverse the next hop; also inspect effective routes and surrounding network components.

## 10. Inspecting Effective Routes and Troubleshooting

When a VM cannot reach a destination, do not inspect only the UDR you just created. Azure also applies system routes, BGP routes, NSGs, firewalls, and resource states that affect the outcome.

### Effective Routes on a NIC

In the Portal:

1. Open **Network interfaces** or the NIC attached to the VM under investigation.
2. Locate **Effective routes** under support/troubleshooting.
3. Inspect address prefixes, source, state, next hop type, and next hop IP.
4. Match Active routes against the destination prefix and the longest prefix match rule.

In Azure CLI, you can run:

~~~bash
az network nic show-effective-route-table \
  --resource-group <VM_RESOURCE_GROUP> \
  --name <NIC_NAME> \
  --output table
~~~

Viewing effective routes depends on the NIC and the VM/network state. If no VM exists or it is not in a queryable state, you can inspect the route table configuration but cannot observe full effective routes as with a running VM.

### Network Watcher: Next Hop

Azure Network Watcher includes the **Next hop** tool to check which next hop Azure chooses for traffic originating from a VM toward a destination IP. During investigation, select the right VM/NIC, source IP, and destination IP, then compare against your expected route.

If the route looks right yet connectivity still fails:

- Check **Effective security rules** on the NIC/subnet; an NSG may be blocking traffic.
- Check whether the firewall/NVA has an allow rule and has IP forwarding enabled.
- Check the **return path** from the target machine, gateway, or appliance.
- Verify DNS resolves to the intended IP. Wrong DNS can mislead you into diagnosing the wrong route.
- For VNet peering, confirm peering is Connected and forwarded traffic / gateway transit options are properly configured.
- For on-premises connectivity, check BGP advertisements, route propagation, gateways, and VPN/ExpressRoute status.

For outages following a UDR update, record the timestamp, route table, subnet, destination IP, and before/after observations. This evidence helps pinpoint the root cause without tearing down multiple configurations at once.

## 11. Distinguishing UDRs from NSGs, DNS, and Firewalls

| Component | Core Question It Solves | Example |
|---|---|---|
| **Route / UDR** | Where should packets for a destination IP go next? | Forward 0.0.0.0/0 via a firewall |
| **NSG** | Allow or block traffic based on L3/L4 rules? | Block TCP 22 from the Internet |
| **Azure Firewall/NVA** | Enforce centralized policy inspection on traffic | Log and filter egress |
| **DNS** | Which IP address does a domain name resolve to? | app.internal.example → 10.20.1.10 |
| **NAT Gateway** | Translate source addresses and provide service-managed outbound connectivity | Stabilize a subnet's outbound IP address |

A UDR with next hop **VirtualAppliance** does not mean the NVA automatically allows or inspects traffic content. If the NVA is unconfigured, traffic may simply be dropped. A **None** UDR drops packets matching the selected prefix, but cannot express application policies by account, URL, or port like a firewall.

### Notes on Private Endpoints and PaaS Services

Private Endpoints use private IP addresses within a VNet and exhibit specialized routing behavior depending on the service and configuration. Do not assume a 0.0.0.0/0 UDR forces all Private Endpoint flows through an NVA. More specific routes may take precedence; applying route tables to a Private Endpoint subnet and modifying network policies must align with service support and configuration requirements.

Additionally, service endpoints, Azure infrastructure management, and special subnets (such as GatewaySubnet) have restrictions or exceptions. Check documentation for the exact service being deployed, especially when designing broad forced tunneling.

### Cost and Operational Impact

Creating a simple VNet and route table does not usually generate direct usage charges, but architectures using **Azure Firewall, VPN Gateway, NAT Gateway, appliance VMs, peering, Internet egress, and monitoring** incur costs. UDRs can route traffic through extra appliances or network regions, adding latency and data transfer fees. Estimate costs before rolling out at scale and track spending with Cost Management.

## 12. Hands-On Lab: Creating a Safe UDR and Observing Configuration

Goal: create a dedicated VNet, a subnet, a route table, and the route **198.51.100.0/24 → None**, then associate the route table with the subnet. The range **198.51.100.0/24** is reserved for documentation/examples, making it suitable for demonstration without needing a running VM or NVA.

**Expected output:** see the UDR in the route table, see the route table attached to the subnet, and explain why a packet to 198.51.100.10 selects the /24 UDR over the 0.0.0.0/0 system route. No VM needs to be created to complete this configuration lab.

### Prerequisites

- Azure CLI signed in with the right lab subscription selected.
- Permissions to create resource groups, VNets, subnets, route tables, and UDRs.
- Chosen region allows creating these basic resources.
- Do not use resource group or subnet names from live systems to avoid impacting others.

### Step 1: Create a Dedicated Resource Group

~~~bash
az group create \
  --name rg-az-routing-lab \
  --location southeastasia \
  --tags environment=learning purpose=routing-lab
~~~

### Step 2: Create a Test VNet and Subnet

~~~bash
az network vnet create \
  --resource-group rg-az-routing-lab \
  --name vnet-routing-lab \
  --location southeastasia \
  --address-prefixes 10.60.0.0/16 \
  --subnet-name snet-app \
  --subnet-prefixes 10.60.1.0/24
~~~

### Step 3: Create the Route Table

~~~bash
az network route-table create \
  --resource-group rg-az-routing-lab \
  --name rt-app-lab \
  --location southeastasia
~~~

### Step 4: Add a UDR Dropping Packets to the Sample Prefix

~~~bash
az network route-table route create \
  --resource-group rg-az-routing-lab \
  --route-table-name rt-app-lab \
  --name drop-documentation-prefix \
  --address-prefix 198.51.100.0/24 \
  --next-hop-type None
~~~

**Explanation:** if a VM with a NIC in snet-app sends a packet to 198.51.100.10, the new /24 route is more specific than the 0.0.0.0/0 Internet route. Azure selects next hop None and drops the packet. For another IP not matching the /24 route and without a more specific route, behavior continues to rely on baseline/other effective routes.

### Step 5: Associate the Route Table with the Subnet

~~~bash
az network vnet subnet update \
  --resource-group rg-az-routing-lab \
  --vnet-name vnet-routing-lab \
  --name snet-app \
  --route-table rt-app-lab
~~~

### Step 6: Inspect the Results

~~~bash
az network route-table route list \
  --resource-group rg-az-routing-lab \
  --route-table-name rt-app-lab \
  --output table

az network vnet subnet show \
  --resource-group rg-az-routing-lab \
  --vnet-name vnet-routing-lab \
  --name snet-app \
  --query "{subnet:name,routeTable:routeTable.id}" \
  --output json
~~~

You should see route **drop-documentation-prefix** with next hop **None**, and the routeTable field of **snet-app** pointing to **rt-app-lab**. If you want to verify with Effective routes / Next hop tools, use an existing test VM or create one within your authorized budget. **Creating a VM is not required** for this lab.

### Step 7: Clean Up

Once finished, confirm the resource group contains only lab resources and no data worth keeping, then delete the group:

~~~bash
az group delete --name rg-az-routing-lab --yes
~~~

Verify whether the group still exists:

~~~bash
az group exists --name rg-az-routing-lab
~~~

A value of **false** indicates the resource group is gone from ARM. Cost data can lag behind actual deletion, so still check Cost Management if any billable resources were deployed.

### Evidence to Record

| Item | Evidence |
|---|---|
| Subscription/region | Subscription name, subscription ID, and region used |
| VNet | vnet-routing-lab: 10.60.0.0/16 |
| Subnet | snet-app: 10.60.1.0/24 |
| Route table | rt-app-lab |
| UDR | 198.51.100.0/24 → None |
| Association | snet-app associated with rt-app-lab |
| Cleanup | Deletion result for rg-az-routing-lab |

## 13. Failure Scenarios and Troubleshooting

| Symptom | Possible Cause | Where to Check |
|---|---|---|
| UDR missing from effective routes | Table not associated with subnet, inspecting wrong NIC/subnet, or route invalid | Check subnet association, NIC, Source, and State |
| Packets still reach an IP despite a broad None route | A more specific route exists for that IP | Compare longest prefixes; check all Active routes |
| Internet traffic stops after setting 0.0.0.0/0 → NVA | NVA not ready, missing forwarding/SNAT/egress | Check NVA, IP forwarding, forward path, and return path |
| On-premises traffic drops after editing table | BGP propagation disabled or UDR overrode gateway route | Check BGP, gateway, prefixes, and states |
| Route looks right yet traffic still times out | Blocked by NSG, firewall, target app, or broken return path | Check Effective security rules, logs, and reverse path |
| VNet peering works but forwarded traffic fails | Forwarded traffic not enabled or mismatched topology/UDR | Check peering settings in both directions and NVA config |
| Editing route table breaks multiple applications | Same route table shared across multiple subnets | List associated Subnets before every change |
| Route 0.0.0.0/0 → Internet exists yet VM lacks Internet | Missing outbound connectivity method or blocked by NSG/firewall | Check NAT/outbound, NSG, IP, and service settings |
| Hard to tell if error is DNS or routing | Hostname resolving to unexpected IP | Resolve DNS first, then trace route using actual target IP |

During production incidents, collect the route table, effective routes, change timestamps, and Network Watcher outputs before making fixes. Avoid deleting or altering multiple UDRs at once, as it makes it difficult to identify which change caused or resolved the issue.

## 14. Self-Check Questions

1. Why does an Azure NIC have effective routes even when its subnet is not associated with any custom route table?
2. When the destination is 10.20.1.10, why does system route 10.20.0.0/16 win over 10.0.0.0/8 → None?
3. If both a system route and a UDR have prefix 0.0.0.0/0, which route does Azure prefer?
4. A /24 BGP route and a /16 UDR both match a destination IP. Which route is selected and why?
5. Why is attaching a UDR 0.0.0.0/0 → VirtualAppliance insufficient on its own for Internet traffic to work?
6. What is the difference between a route with next hop None and an NSG deny rule?
7. How can disabling BGP route propagation affect on-premises connectivity?
8. Why must you check both forward and return paths when using a stateful firewall?
9. To determine which routes actually apply to a VM, should you inspect the configured route table or the NIC's effective routes?
10. Does DNS determine the packet's next hop after a hostname has been resolved?

## 15. References

- [Azure virtual network traffic routing](https://learn.microsoft.com/azure/virtual-network/virtual-networks-udr-overview) — system routes, UDRs, BGP, next hops, and route selection rules.
- [Create, change, or delete an Azure route table](https://learn.microsoft.com/azure/virtual-network/manage-route-table) — creating route tables, associating subnets, and managing UDRs.
- [Azure CLI: az network route-table](https://learn.microsoft.com/cli/azure/network/route-table) — route table management commands.
- [Azure CLI: az network route-table route](https://learn.microsoft.com/cli/azure/network/route-table/route) — adding, viewing, and deleting individual routes.
- [Network Watcher next hop](https://learn.microsoft.com/azure/network-watcher/next-hop-overview) — diagnostic tool for next hop selection.
- [Diagnose a virtual machine routing problem](https://learn.microsoft.com/azure/virtual-network/diagnose-network-routing-problem) — troubleshooting connectivity and effective routes.

A sound routing design must identify **destination IP, most specific matching prefix, next hop, and return path**. When using UDRs to steer traffic through a firewall or gateway, verify actual behavior on the NIC and coordinate with NSGs, DNS, NVA routing, security policies, and operational costs.
