# IP Addressing Design for Azure Virtual Network

An application on Azure typically consists of multiple components: web/API tiers, data services, management virtual machines, private endpoints, and connections to on-premises corporate networks. If IP addresses are assigned ad hoc, networks easily end up with **overlapping ranges**, run out of space for scaling resources, or require reconfiguration when connecting VNets via peering, VPN, or ExpressRoute. Designing IP addressing from the start keeps resources clearly organized, simplifies security segmentation, and minimizes disruption during expansion.

This lesson belongs to the **Virtual Networks and Name Resolution** chapter of the `CLOUD_PROVIDERS_AZURE` module. The module scope spans from subscriptions, resource groups, and Microsoft Entra ID to virtual networks, compute, storage, and data services, while also guiding deployment, monitoring, security, and cost control for application architectures on Microsoft Azure. This lesson focuses on **Azure Virtual Network (VNet) IP address planning**, establishing the foundation for the subsequent sections on routing, DNS, private connectivity, and network governance.

## 1. Objectives of a Good IP Addressing Design

After this lesson, you will be able to:

- Distinguish between **VNet address space**, **subnet prefix**, **private IP**, and **public IP**.
- Read CIDR notation and calculate the number of usable IPv4 addresses in an Azure subnet.
- Select private address ranges that do not overlap with other VNets or on-premises networks planned for connectivity.
- Allocate subnets based on workload roles and Azure service requirements.
- Reserve address capacity for autoscale, private endpoints, delegated-subnet services, and long-term growth.
- Verify the IP plan using the Azure Portal or Azure CLI before deployment.

**Guiding principle:** design from the organization-wide connectivity scope down to the VNet, and only then divide into subnets. A syntactically valid CIDR is not necessarily suitable for a real-world architecture.

## 2. VNet Address Space, Subnets, and IP Addresses

**Azure Virtual Network** is a managed virtual private network in Azure. Each VNet has one or more IP address blocks; within those blocks, you create **subnets** to segment resources by function, policy, and connectivity requirements.

Example:

```text
VNet: vnet-prod-app (10.60.16.0/20)
│
├── snet-app       10.60.16.0/23   Web, API, applications
├── snet-data      10.60.20.0/24   Private data components
├── snet-pe        10.60.22.0/24   Private endpoints
├── snet-integrate 10.60.23.0/24   PaaS service integration
└── snet-ops       10.60.24.0/26   Operations tooling

Remaining address ranges: reserved for growth.
```

In this example:

- `10.60.16.0/20` is the **address space** assigned to the VNet.
- `10.60.16.0/23` is a **subnet prefix**, which must fit entirely within the VNet's address space.
- Each eligible NIC, VM, or private endpoint can use a **private IP** within the subnet, allocated according to Azure and service behavior.
- **Public IP** addresses are used for Internet connectivity or as the frontend of public services; public IPs are not created by picking an arbitrary address from RFC 1918 ranges.

A VNet can have multiple distinct address spaces; subnets must belong to the VNet's address space and must not overlap each other. Two subnets within the same VNet cannot share an address range.

### Is a VNet IP a single address?

No. An address like `10.60.16.0/20` describes an **entire IP range**, not an IP assigned to a single device. A VNet is not a server that requires a single IP. It is the network interfaces and resources inside the subnets that use specific addresses.

## 3. CIDR and Calculating IPv4 Address Counts

CIDR (Classless Inter-Domain Routing) writes a network address in the form `address/prefix_length`. For IPv4, the part before the `/` is the base address; the part after indicates the number of network bits out of 32 total bits.

Examples:

- `10.60.16.0/20`: 20 network bits, 12 host bits → 2^(32−20) = **4,096 IPv4 addresses**.
- `10.60.16.0/23`: 23 network bits, 9 host bits → **512 addresses**.
- `10.60.20.0/24`: 24 network bits, 8 host bits → **256 addresses**.

Formulas:

```text
Number of IPv4 addresses in a CIDR block = 2^(32 - prefix_length)
Usable IPv4 addresses in an Azure subnet = total IPv4 addresses - 5
```

The second formula applies to an **Azure IPv4 subnet** because the platform reserves five addresses in every subnet. Do not apply that subtraction to calculate an overall “VNet IP pool” or to calculate IPv6.

| CIDR | Total IPv4 | Allocatable to resources in an Azure subnet | Reference scenario |
|---|---:|---:|---|
| `/29` | 8 | 3 | Very small technical scope; many services do not support it or are unsuitable |
| `/28` | 16 | 11 | Very small environment when permitted by the service |
| `/27` | 32 | 27 | Small subnet or certain dedicated infrastructure subnets |
| `/26` | 64 | 59 | Workloads or dedicated subnets requiring a larger minimum |
| `/25` | 128 | 123 | Medium-scale VM groups |
| `/24` | 256 | 251 | Common application subnet |
| `/23` | 512 | 507 | Application groups with high IP demand |
| `/22` | 1,024 | 1,019 | Large block, autoscale buffer, or high-capacity requirements |

**Note:** the table shows theoretical address limits after Azure's reservation; it does not guarantee that any arbitrary service will run on the smallest listed subnet. Some services have their own minimum subnet size and deployment requirements.

### Calculating Start and End Ranges

The block `10.60.16.0/20` covers addresses from `10.60.16.0` to `10.60.31.255`. Because /20 spans 16 values in the third octet, adjacent blocks are:

- `10.60.0.0/20` → `10.60.0.0` to `10.60.15.255`.
- `10.60.16.0/20` → `10.60.16.0` to `10.60.31.255`.
- `10.60.32.0/20` → `10.60.32.0` to `10.60.47.255`.
- `10.60.48.0/20` → `10.60.48.0` to `10.60.63.255`.

The base address of a CIDR block must align with the prefix bit boundary. For example, `10.60.17.0/20` is **not** a valid network base address for a /20 block starting at 17 in the third octet; the corresponding valid block actually starts at `10.60.16.0/20`.

## 4. Five Azure-Reserved Addresses in Each IPv4 Subnet

Azure reserves **the first four addresses and the last address** in every IPv4 subnet. They are unavailable for assignment to virtual machines or user resources.

For subnet `10.60.20.0/24`:

| Address | Status |
|---|---|
| `10.60.20.0` | Reserved by Azure |
| `10.60.20.1` | Reserved; default gateway address |
| `10.60.20.2` | Reserved for the Azure platform |
| `10.60.20.3` | Reserved for the Azure platform |
| `10.60.20.4` to `10.60.20.254` | Allocatable depending on service and usage state |
| `10.60.20.255` | Reserved by Azure |

Therefore, a /24 has **251**, not 254, addresses allocatable to resources. Similarly, a /26 has 59 usable addresses and a /23 has 507.

These five addresses are reserved **per subnet**, not just once at the VNet level. If a large block is split into many small subnets, the cumulative number of reserved addresses increases. This is one reason not to fragment subnets excessively when there is no clear governance need.

## 5. Choosing Private IP Ranges and Avoiding Network Overlap

Private IPv4 ranges are defined in RFC 1918:

| Private Range | Corresponding Span | Guidance |
|---|---|---|
| `10.0.0.0/8` | `10.0.0.0` – `10.255.255.255` | Easy to partition into many large regions for enterprises |
| `172.16.0.0/12` | `172.16.0.0` – `172.31.255.255` | Alternative option when 10/8 is already in use |
| `192.168.0.0/16` | `192.168.0.0` – `192.168.255.255` | Commonly found in small offices, home networks, or labs |

**Being inside RFC 1918 does not automatically make a range usable.** Before locking in a VNet range, check the addresses of:

1. Existing VNets across all subscriptions, regions, tenants, or organizations that will connect.
2. Networks at offices, data centers, and on-premises sites connected via VPN/ExpressRoute.
3. Partner, vendor, or project networks with planned peering or private connectivity.
4. Container systems, workload-specific networks, and IP ranges required by managed services.
5. Ranges that may be added in the future or reserved for shared network infrastructure.

When two networks use **overlapping** CIDR blocks, routing and establishing direct connectivity can be blocked. Azure VNet peering does not support overlapping address spaces. With hybrid connections or partner networks, overlapping ranges can create ambiguous routes and force a redesign or complex address translation solutions.

Example: a VNet using `10.60.16.0/20` overlaps with `10.60.20.0/24` because the /24 lies completely inside the /20. Conversely, `10.60.16.0/20` and `10.60.32.0/20` do not intersect.

**Key decision:** maintain an organization-wide IP address registry (IPAM) to prevent two independent teams from choosing the same CIDR. This registry should record owner, purpose, environment, region, subscription, VNet, required connected routes, and allocation/reservation status.

## 6. Designing Addresses from Organization Scale to Subnets

Recommended sequence:

1. **Define the topology:** hub-spoke network, multiple independent VNets, multi-region, or hybrid connectivity.
2. **Register the master block:** reserve an organization-level address pool, such as `10.60.0.0/16`, after verifying there are no conflicts.
3. **Allocate to VNets:** assign separate blocks for the hub, Production, Staging, and Development.
4. **Subdivide subnets within each VNet:** separate by workload role and technical requirements.
5. **Leave room for growth:** keep documented unused blocks rather than consuming everything just because addresses are available.
6. **Review with networking, security, and application teams:** verify connectivity needs, service-specific constraints, and expansion roadmaps.

### Example VNet Allocation by Environment

Assume the enterprise has verified that pool `10.60.0.0/16` does not conflict with any networks to be connected.

| VNet | CIDR | Role |
|---|---|---|
| `vnet-hub` | `10.60.0.0/20` | Shared connectivity components, VPN/ExpressRoute, network services if applicable |
| `vnet-prod-app` | `10.60.16.0/20` | Production applications |
| `vnet-test-app` | `10.60.32.0/20` | Testing, UAT |
| `vnet-dev-app` | `10.60.48.0/20` | Development |
| Unassigned blocks | Remainder of `10.60.0.0/16` | New VNets, other regions, or planned expansion |

Each /20 has 4,096 theoretical addresses. These ranges are only a learning example; organizations should size VNets according to actual demand rather than defaulting every VNet to /20. If multiple regions are used, an intermediate allocation tier by region can be added before splitting by environment.

### Example Subnetting for Production

Within `vnet-prod-app = 10.60.16.0/20`:

| Subnet or Reserved Range | CIDR | Usable IPv4 in Subnet | Purpose |
|---|---|---:|---|
| `snet-app` | `10.60.16.0/23` | 507 | Applications/VMs requiring scale |
| Reserved for applications | `10.60.18.0/23` | Unallocated | For expanding with a new subnet or an appropriate migration design |
| `snet-data` | `10.60.20.0/24` | 251 | Data components using private IPs |
| Reserved for data | `10.60.21.0/24` | Unallocated | Future requirements |
| `snet-private-endpoints` | `10.60.22.0/24` | 251 | Service private endpoints |
| `snet-integration` | `10.60.23.0/24` | 251 | VNet-integrated services per deployment requirements |
| `snet-ops` | `10.60.24.0/26` | 59 | Management machines or tooling |
| Other reserve | Remainder of `10.60.16.0/20` | Unallocated | Additional subnets, growth, or new workloads |

The illustrated subnets are **non-overlapping** and all reside inside the /20. The “Reserved” rows represent address ranges where **no subnet has been created yet**, so “usable IPv4” does not apply at the current time.

Keeping contiguous address space free can be helpful during planning, but it **does not guarantee** Azure will allow in-place resizing of a subnet that already contains resources. In practice, you often must create a new subnet and migrate resources according to plan. Check service requirements before designing changes.

### Illustration of Allocation Boundaries

```text
Organization pool: 10.60.0.0/16
|
+-- HUB          10.60.0.0/20
+-- PRODUCTION   10.60.16.0/20
|   +-- APP            10.60.16.0/23
|   +-- APP RESERVED   10.60.18.0/23
|   +-- DATA           10.60.20.0/24
|   +-- DATA RESERVED  10.60.21.0/24
|   +-- PRIVATE EP     10.60.22.0/24
|   +-- INTEGRATION    10.60.23.0/24
|   +-- OPS            10.60.24.0/26
|   +-- FUTURE         unallocated range
+-- TEST         10.60.32.0/20
+-- DEVELOPMENT  10.60.48.0/20
+-- FUTURE       remaining blocks
```

The organization pool is only an **IPAM planning convention**, not necessarily an actual VNet. Each VNet is a separate entity in Azure with an explicitly created address space.

## 7. Sizing Subnets for Peak Load and Growth

A subnet must have enough addresses for **peak usage**, not just currently running resources.

Suppose an application subnet is expected to require:

- 120 addresses for existing VMs or network interfaces.
- 80 addresses for the highest scale-out event.
- 40 buffer addresses for upgrades or parallel deployments.

The total requirement is **240 allocatable IPs**. A /24 provides 251 usable addresses so it meets the count, but leaves only 11 buffer addresses for unplanned situations. Choosing a /23 with 507 usable IPs may be more appropriate if growth is planned and address space permits.

Another approach is to pick a buffer percentage. With a peak demand of 300 IPs and a goal of leaving 25% **allocation capacity** free:

```text
Required capacity >= 300 / (1 - 0.25) = 400 IPs
/24 -> 251 usable IPs: insufficient
/23 -> 507 usable IPs: sufficient by count
```

A 25% buffer is only an **illustrative assumption**, not an Azure default requirement. The final decision depends on autoscale plans, blue-green deployment processes, maximum instance counts, standby resources, and actual service requirements.

### Factors That Change IP Demand

- **VM/NIC:** each NIC configuration and secondary IP can consume additional addresses in the subnet.
- **Private endpoint:** an endpoint typically requires a private IP from the chosen subnet; multiple services or subresources may require multiple endpoints.
- **PaaS apps with VNet Integration:** IP consumption, subnet delegation, and scale/upgrade requirements depend on each service.
- **AKS:** IP calculation varies by network plugin, Azure CNI/overlay mode, node count, pod count, and cluster upgrades; no single formula applies to all configurations.
- **Virtual network appliances and platform services:** firewalls, gateways, or management components have dedicated subnets with specific minimum address requirements.

Because each service allocates IPs differently, build a **per-service demand table** before selecting a CIDR. Do not use a “one workload = one IP” formula when the architecture involves multiple NICs, pods, private endpoints, or parallel deployment phases.

## 8. Dedicated Subnets and Service Constraints

Certain services require a **specific subnet name**, **minimum size**, or **delegation**. These are design constraints, not merely naming conventions.

| Component | What to Verify During Design |
|---|---|
| **VPN/ExpressRoute gateway** | Subnet named `GatewaySubnet`; requires sizing suited to gateway type and scale-out. For new designs, /27 or larger is commonly preferred depending on service requirements. |
| **Azure Bastion** | Dedicated subnet named `AzureBastionSubnet`; check minimum size, commonly /26 for new deployments, along with SKU requirements. |
| **Azure Firewall** | `AzureFirewallSubnet`, typically requiring /26 or larger; some topologies also require `AzureFirewallManagementSubnet`. |
| **Private endpoints** | Choose a subnet with enough IPs for each endpoint and verify Private Link network/NSG policies, routing, and DNS. |
| **App Service VNet Integration and similar PaaS** | Check subnet delegation requirements, minimum size, and extra IPs needed during scaling or upgrades. |
| **AKS** | Design around the specific network plugin, node/pod counts, and upgrade mechanism, which may require multiple subnets/address ranges. |

CIDR and feature requirements can vary by SKU and service version. When deploying in production, cross-check the current documentation for the Azure service in use. Do not place all components into one shared subnet simply because many addresses remain available.

**Hub-spoke:** if the gateway, Bastion, or Firewall resides in the hub, you do not necessarily need to create those dedicated subnets in every spoke. Reserve addresses in the exact VNet hosting the service and verify related routing, peering, and DNS requirements.

## 9. Dynamic vs. Static Private IPs and Resource Lifecycle

Azure typically assigns private IPs to NICs from a subnet. There are two common configuration modes:

- **Dynamic:** Azure automatically selects an address from the subnet's available pool. This fits many workloads with flexible lifecycles.
- **Static:** declares a specific private IP **within the subnet** and **outside Azure's five reserved addresses** for a supported NIC or resource.

Static addresses are useful when configurations depend on a specific IP, but require lifecycle management to avoid duplicate assignments. For applications that scale or replace instances frequently, prefer DNS, service discovery, load balancers, or private endpoints rather than hardcoding individual VM IPs.

**A private IP does not imply Internet reachability.** Outbound Internet access depends on routes, NAT Gateway, firewalls, or other egress mechanisms. Public IPs or NAT addresses are designed separately and are not part of a private subnet's CIDR.

Do not change IPs, delete subnets, or shrink prefixes on a running system without checking dependent resources and planning the change. Some operations are blocked by Azure while a subnet is in use; others can cause service disruption.

## 10. Relationship Between IP Addressing, Routing, Security, and DNS

IP design is a prerequisite for a well-functioning network, but **does not by itself create routes or access permissions**.

### Routing and Connectivity

- **VNet peering:** peered address spaces must not overlap. Peering connects two VNets, but does not automatically turn every peering chain into a transitive routing network.
- **VPN/ExpressRoute:** Azure and on-premises ranges must be coordinated from the outset; confirm advertised routes and partner CIDRs.
- **UDR (user-defined route):** used when traffic paths must be steered through a firewall or network virtual appliance.
- **Network Security Group (NSG):** controls traffic at the subnet/NIC level; having valid IPs in a range does not prove two resources are allowed to communicate.

For example, if the Production spoke uses `10.60.16.0/20` while the data center already uses `10.60.20.0/24`, hybrid connectivity can be difficult to route due to overlapping blocks. Adding NSG rules does not resolve a CIDR conflict.

### DNS and Private Link

When using private endpoints for Storage, SQL, or other Azure services, clients must resolve the hostname to the **correct private IP**. The design must account for:

1. A subnet with enough IPs for the endpoints.
2. The appropriate Private DNS zone for the service.
3. Virtual network links or a DNS forwarder/resolver topology for the VNets requiring resolution.
4. Name resolution for on-premises clients if traffic traverses a hybrid connection.

DNS may resolve the right name yet fail to connect without proper routes or NSGs. Conversely, non-overlapping IPs with DNS pointing to a public endpoint can send traffic along an unintended path.

## 11. IPv6 and Dual Stack

Azure supports **IPv4/IPv6 dual-stack** scenarios for VNets and select services. When IPv6 is needed, plan IPv6 addressing separately instead of applying IPv4 formulas.

In Azure IPv6 designs, VNets and subnets must use IPv6 prefixes in platform-supported sizes; IPv6 subnets are commonly planned as **/64** blocks, while the VNet address space is larger. Verify current Azure requirements and **IPv6 support for each individual service** before deployment, especially for load balancers, firewalls, gateways, private endpoints, and PaaS integrations.

Key questions:

- Does the application actually need IPv6 for Internet clients or internal traffic?
- Do services and hybrid links support IPv6 end-to-end?
- Does DNS require `A` records, `AAAA` records, or both?
- Are security, monitoring, and routing rules designed for both IPv4 and IPv6?

For an architecture currently running purely on IPv4, do not enable IPv6 merely “just in case” without evaluating dependencies. When dual stack is needed, design and test IPv6 flows separately.

## 12. Verifying and Deploying an Example with Azure CLI

The commands below are **examples** using resource group `rg-network-lab`, region `southeastasia`, and the addresses from the Production table. Replace names and subscription with your lab environment values before running. Commands creating VNets/subnets modify Azure resources; run them in an authorized environment and follow your organization's cost governance process.

### Step 1: Confirm Subscription and Tenant

```bash
az account show --query "{Name:name,Subscription:id,Tenant:tenantId}" --output table
```

If not on the assigned subscription, use the exact Subscription ID:

```bash
az account set --subscription "<SUBSCRIPTION_ID>"
```

### Step 2: Create the VNet and First Subnet

Assuming resource group `rg-network-lab` **already exists** in the correct subscription:

```bash
az network vnet create \
  --resource-group "rg-network-lab" \
  --location "southeastasia" \
  --name "vnet-prod-app" \
  --address-prefixes "10.60.16.0/20" \
  --subnet-name "snet-app" \
  --subnet-prefixes "10.60.16.0/23"
```

This is only a VNet/subnet deployment example. Do not use actual Production names in an organization's test environment without authorization.

### Step 3: Create a Non-Overlapping Subnet

```bash
az network vnet subnet create \
  --resource-group "rg-network-lab" \
  --vnet-name "vnet-prod-app" \
  --name "snet-data" \
  --address-prefixes "10.60.20.0/24"
```

Additional subnets can be created according to the planning table after reviewing delegations and specific constraints.

### Step 4: Inspect Address Space and Subnets

```bash
az network vnet show \
  --resource-group "rg-network-lab" \
  --name "vnet-prod-app" \
  --query "{VNet:name,AddressSpaces:addressSpace.addressPrefixes}" \
  --output json
```

```bash
az network vnet subnet list \
  --resource-group "rg-network-lab" \
  --vnet-name "vnet-prod-app" \
  --query "[].{Name:name,AddressPrefix:addressPrefix,AddressPrefixes:addressPrefixes}" \
  --output table
```

The `show` and `list` commands are read-only configuration checks used to compare actual subnets against the design table. When working in a subscription with existing resources, run these read commands before any create or modify operations.

### Verifying with the Azure Portal

In the Azure Portal:

1. Select the correct tenant and subscription.
2. Open **Virtual networks** and select the relevant VNet.
3. View **Address space** to confirm the VNet's CIDR.
4. Open **Subnets** to inspect names, prefixes, and associated services.
5. Cross-check all prefixes against the IPAM table, especially against hub networks, peerings, and hybrid connections.

Azure may reject a command if a prefix falls outside the address space, overlaps an existing subnet, lacks permissions, or conflicts with service requirements. Read the error message and check the design before changing to an arbitrary prefix just to make the syntax pass.

## 13. Common Design Mistakes

| Issue | Potential Consequence | Prevention |
|---|---|---|
| Two VNets to be peered use overlapping CIDRs | Cannot peer as designed or difficult routing | Check organization-wide scope before assigning CIDRs |
| Azure VNet overlaps corporate office network | Ambiguous hybrid routes, forcing re-addressing or NAT design | Gather all on-premises and site CIDRs upfront |
| Picking /28 because only a few VMs exist today | Exhausting IPs when scaling or adding endpoints | Calculate peak demand and buffer per service |
| Forgetting Azure's five reserved addresses | Overestimating available capacity | Calculate 2^(32−prefix) − 5 for each IPv4 subnet |
| Using a shared subnet for a service needing dedicated delegation | PaaS deployment fails or violates constraints | Check subnet requirements for each service |
| Creating too many tiny subnets | Wasting many reserved addresses, complex management | Split by governance boundaries and actual needs |
| Leaving no room for growth | Forced to create new VNets/subnets or migrate urgently | Reserve contiguous blocks and part of the org pool |
| Planning IPs while ignoring DNS | Private endpoint exists but app fails to resolve properly | Design private DNS zones and VNet links |
| Hardcoding VM static IPs in app configs | Coupled to VM lifecycle, hard to replace and scale | Prefer DNS, load balancing, or private endpoints |
| Changing prefixes on a live network | Potential outage, restricted operations, or broken routes | Assess dependencies and plan change/migration |

## 14. Hands-On Exercise: Creating an IP Plan for a Three-Tier Application

**Scenario:** A team needs to deploy a system comprising web/API, data processing, private endpoints, and management components. The system will connect to an existing hub VNet; the on-premises environment uses other address ranges already confirmed by the networking team. An approved address pool is `10.72.0.0/16`.

**Assumed Requirements:**

- Production needs at least 180 IPs for web/API at peak load, excluding buffer.
- The data tier needs 70 IPs.
- Private endpoints are projected at 24 IPs, with plans to grow to 60.
- Operations infrastructure needs 15 IPs.
- Keep at least 25% of allocatable capacity unused in the web/API subnet.
- Each component has an independent subnet; reserve additional free space for growth.
- All CIDRs must not overlap with the hub or on-premises networks.

### Reference Solution

Assume `10.72.16.0/20` is allocated to the application VNet:

| Subnet | Proposed CIDR | Usable IPs | Assessment |
|---|---|---:|---|
| `snet-web` | `10.72.16.0/23` | 507 | 180 peak IPs plus >=25% buffer |
| `snet-data` | `10.72.18.0/24` | 251 | 70 IPs plus growth |
| `snet-pe` | `10.72.19.0/24` | 251 | 60 future endpoints |
| `snet-ops` | `10.72.20.0/26` | 59 | 15 operations IPs |
| Unused range | Remainder of `10.72.16.0/20` | Unallocated | New subnets or planned expansion |

Here, /23 is a generous choice for web/API rather than a strict minimum. With 180 IPs and at least 25% capacity buffer, required capacity is >= 180/0.75 = 240 IPs; a /24 with 251 usable IPs also meets the number. However, /23 can be more sensible when accounting for autoscale exceeding assumptions or parallel deployments. Choosing /23 versus /24 ultimately depends on growth plans and how strictly the organization conserves its address pool.

For `snet-pe`, confirm the **actual private endpoint count**, not just logical service count: one service can create multiple endpoints depending on connections to subresources. If any service requires a dedicated subnet or delegation, adjust the layout for that constraint.

### Exercise Completion Criteria

- All CIDRs align on network boundaries and fit within VNet `10.72.16.0/20`.
- No subnets overlap; free space remains for future allocation.
- Capacity calculations subtract Azure's five reserved IPs in **each subnet**.
- Checked against the hub, VPN/ExpressRoute, on-premises ranges, and planned network peerings.
- Identified requirements for private endpoints, DNS, and any dedicated subnets if used.
- Documented an IPAM table recording owner, environment, region, subscription, prefix, and reservation status.

## 15. Knowledge Self-Check

**Question 1.** How many addresses in IPv4 subnet `10.20.8.0/24` in Azure can be assigned to resources?

A. 254  
B. 256  
C. 251

**Answer: C.** 256 total addresses, minus the five addresses reserved by Azure.

**Question 2.** VNet A is `10.60.16.0/20` and VNet B is `10.60.20.0/24`. Are they suitable for direct peering?

**Answer:** No. B falls inside A's range, so the two address spaces overlap.

**Question 3.** Do subnets `10.60.16.0/23` and `10.60.18.0/23` overlap?

**Answer:** No. The first subnet covers third octets 16–17, and the second covers 18–19; the two blocks are adjacent but do not intersect.

**Question 4.** A system expects up to 300 IPs and wants 25% of usable capacity kept free. Is a /24 sufficient?

**Answer:** No. At least 300/0.75 = 400 usable IPs are needed. A /24 only has 251; a /23 has 507, which meets the planning formula.

**Question 5.** When using a private endpoint for an Azure Storage account, is it enough to choose an IP and ignore DNS?

**Answer:** False. Clients must resolve the hostname to the right private IP; you must account for private DNS zones, VNet links, and DNS forwarding if hybrid connectivity exists.

**Question 6.** Should `GatewaySubnet` be placed in every spoke VNet?

**Answer:** Not necessarily. Only create dedicated subnets in the VNet that hosts the gateway per the architecture; hub-spoke topologies usually centralize connectivity services in the hub, depending on design and platform constraints.

**Question 7.** A subnet has run out of IPs. Can you simply change a /24 to /23 without affecting running resources?

**Answer:** No. Changing a prefix depends on contiguous free address space, existing resources, and service limits. You must assess dependencies and plan expansion or resource migration to a new subnet.

A good IP addressing design is more than non-overlapping CIDR blocks. It must also reflect organization-wide topology, Azure service capacity requirements, growth buffers, and dependencies with routing, security, and DNS. When these decisions are recorded in IPAM from the beginning, deploying and operating virtual networks becomes much easier to govern.
