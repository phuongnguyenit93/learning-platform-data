# Network Interfaces and Workload IP Configuration

An application running on Azure needs to communicate with databases, internal services, the Internet, or external users. For traffic to reach the right destination under proper control, operators must understand **network interfaces (NICs)**, IP addresses, subnets, routing, DNS, and network protection layers.

Within the **CLOUD_PROVIDERS_AZURE** module, this lesson belongs to the **Virtual Networks and Name Resolution** chapter. This knowledge forms the foundation for deploying workloads on Azure Virtual Machines (VMs), designing application networking, connecting to storage and data services, auditing security, and troubleshooting network incidents. The focus is on configuring NICs and IP addressing for workloads, primarily via VMs; some PaaS services use different connectivity mechanisms and do not expose a VM NIC for direct configuration.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish between VNet, subnet, NIC, IP configuration, private IP, and public IP.
2. Understand how Azure allocates dynamic or static IPs and why IP configuration in Azure differs from guest OS configuration.
3. Create, inspect, and update NICs and IP configurations using the Azure Portal or Azure CLI.
4. Decide when a workload requires a public IP, multiple IP addresses, or multiple NICs.
5. Understand the effects of Network Security Groups (NSGs), route tables, DNS, and guest OS network configuration.
6. Diagnose common issues and perform changes safely.

## 2. Where Does a NIC Sit in an Azure Network?

An **Azure Virtual Network (VNet)** is the private logical network boundary for a workload. A VNet is divided into **subnets**, each with its own IP range inside the VNet's address space. A **NIC** is an Azure resource that connects a virtual machine to a subnet, holding IP configurations and connection-level network properties.

~~~
VNet: 10.20.0.0/16
  |
  +-- Subnet app: 10.20.1.0/24
  |      |
  |      +-- NIC web-nic
  |             |
  |             +-- ipconfig1: 10.20.1.10 (private IPv4)
  |             +-- Public IP: as needed
  |             |
  |             +-- VM web-01
  |
  +-- Subnet data: 10.20.2.0/24
         |
         +-- NIC db-nic
                |
                +-- ipconfig1: 10.20.2.10 (private IPv4)
                +-- VM db-01
~~~

In the diagram, VMs web-01 and db-01 have private IPs on different subnets of the same VNet. Resources can communicate via Azure's internal routing unless blocked by an NSG, firewall, route, or other network policy.

**A NIC is not the same as a VM.** A NIC is a network resource with its own lifecycle and configuration, attached to an eligible VM. A VM can have multiple NICs when supported by the VM size and deployment method. A single NIC cannot be attached to multiple VMs simultaneously.

| Component | Responsibility |
|---|---|
| VNet | Defines the private network space and connectivity capabilities |
| Subnet | Partitions address ranges and serves as the scope for many network settings |
| NIC | Connects a VM to the network; holds IP configurations, NSG, and related settings |
| IP configuration (ipconfig) | Describes the private IP and optional public IP reference |
| Private IP | Address for communication inside the VNet or across connected networks |
| Public IP | Internet-routable address resource associated with an eligible endpoint |
| NSG | Controls allowed traffic via inbound/outbound rules |
| Route table | Controls packet paths at the subnet level |
| DNS | Maps domain names to IP addresses so workloads reach the right target |

## 3. IP Configuration of a NIC

Every NIC has at least **one IP configuration**. An IP configuration contains key attributes:

- Configuration name, such as `ipconfig1`.
- Subnet and private IP allocated within that subnet's range.
- Private IPv4 allocation method: **Dynamic** or **Static**.
- IP version: IPv4 or IPv6 if supported by the network and workload.
- Reference to a **public IP resource**, if a public IP needs to be assigned to the configuration.
- A **primary** flag when a NIC has multiple IP configurations.

### Primary NIC vs. Primary IP Configuration

Two concepts are frequently confused:

- **Primary NIC**: the main network interface of a VM when the VM uses multiple NICs. VMs have specific limits and rules for the primary NIC depending on deployment.
- **Primary IP configuration**: the primary IP configuration inside a single NIC. When a NIC has multiple configurations, one configuration is marked primary.

A VM with only one NIC can still have multiple IP configurations on that NIC. Conversely, a VM with multiple NICs does not mean each NIC holds multiple IP addresses. Adding NICs must also satisfy the VM size's NIC limit and same-VNet connectivity rules.

### Why Would a Workload Have Multiple IP Addresses?

Some valid scenarios:

- A server hosting multiple endpoints or service addresses.
- Legacy applications requiring dedicated IP addresses per process.
- A network virtual appliance (NVA) needing multiple interfaces to handle traffic.
- Designs requiring separation of management and application traffic across multiple subnets/NICs when supported.

Do not automatically add NICs or IP addresses simply to “increase speed.” Multiple NICs complicate route tables, firewalls, guest OS IP setup, and monitoring. Network throughput also depends on VM size, platform capabilities, and features like Accelerated Networking.

## 4. Private IPv4: Dynamic vs. Static

Private IPs are used for internal traffic, not addresses routed directly from the public Internet. For a NIC, private IPv4 addresses typically come from the subnet's address range.

### Dynamic

In **Dynamic** mode, Azure picks an available address from the subnet. This is **Azure-managed allocation**, distinct from arbitrarily setting an IP inside the OS. Do not rely on a Dynamic address as an immutable guarantee for systems requiring a fixed long-term address.

### Static

In **Static** mode, the administrator selects a valid, available address in the subnet, and Azure reserves that address for the IP configuration until the configuration is changed or released. For example, a workload with fixed internal routing requirements might use `10.20.1.10` in subnet `10.20.1.0/24`.

**A static private IP is not a public IP address.** “Static” here only describes how the address is allocated inside the VNet.

### Azure-Reserved Addresses

Azure reserves **5 IPv4 addresses** in every subnet: the first four addresses and the last address. For subnet `10.20.1.0/24`:

| Range/Address | Meaning |
|---|---|
| `10.20.1.0` | Network address, reserved by Azure |
| `10.20.1.1` | Default gateway of the subnet |
| `10.20.1.2` and `10.20.1.3` | Reserved by Azure |
| `10.20.1.4` to `10.20.1.254` | Address range generally available for resource allocation |
| `10.20.1.255` | Last address in the subnet, reserved by Azure |

Thus, a `/24` subnet has a maximum of **251 usable IPv4 addresses** under Azure's allocation rules. Actual available addresses are lower if NICs, private endpoints, or other resources already consume IPs.

> When choosing a static IP, check the subnet, used addresses, and the environment-wide IP plan. Avoid “guessing” an address by hostname or checking solely with ping: an address that does not respond to ping may still already be allocated.

### Crucial Point: Private IP in Azure vs. in the Guest OS

For standard NIC IPv4 configurations, **select Static in Azure while keeping the primary IPv4 address in the guest OS set to DHCP**. Azure delivers the exact address reserved on the NIC through the platform networking layer.

Do not manually switch the VM's primary address to a static IP configuration inside Windows/Linux assuming Azure will recognize that change. Mismatches between the guest OS and the NIC can break remote access or cause hard-to-diagnose failures.

When assigning **multiple private IPs on the same NIC**, secondary addresses generally need to be configured inside the guest OS following OS-specific guidance. Azure manages IP configurations in the control plane; the guest OS needs to know which addresses applications will actually bind to.

## 5. Public IPs and Internet Connectivity

A VM can use only a private IP and still connect to internal resources across VNets, VNet peering, VPN, or ExpressRoute, depending on the architecture. A VM is **not required to have a public IP** to participate in an application.

When Internet access into a VM is needed, you can associate a **Public IP address** resource with a NIC's IP configuration. However, having a public IP does not mean every port is open; NSGs and security controls still determine which traffic is allowed.

### Common Options

| Goal | Connectivity Approach to Consider |
|---|---|
| Administer VMs without exposing SSH/RDP to the Internet | Azure Bastion or access through a controlled private network |
| Public web workload across multiple servers | Azure Application Gateway, Azure Load Balancer, or an appropriate frontend service |
| Private VM needing outbound Internet access | Explicit outbound design such as NAT Gateway on the subnet |
| Test VM needing an Internet endpoint | Standard public IP on the NIC with NSG restricting source IPs/ports |
| Internal-only application | Private IP, private DNS, and private connectivity paths |

### Standard Public IP and Usage Scope

For new deployments, prefer **Standard SKU Public IP** whenever a direct public IP is needed. Standard public IPs use static allocation; the address is managed as a separate Azure resource rather than configured directly inside the VM OS.

Public IP resources have constraints around region, zone, SKU, and compatible target resources. Before creating one, confirm that the public IP is compatible with the NIC, Load Balancer, or related service. An IPv4 public IP does not turn an IPv4 subnet into IPv6.

**Ingress** (traffic entering the application) and **egress** (traffic leaving to the Internet) are two separate concerns. NAT Gateway handles subnet-level outbound traffic and does not open inbound ports from the Internet to individual VMs. Do not rely on implicit platform outbound IPs when a system requires a fixed source address or durable configuration.

## 6. IPv4, IPv6, and Dual-Stack

IPv4 is the standard choice for many Azure workloads, though some architectures support **dual-stack**, where the same network/workload has both IPv4 and IPv6 addresses.

When designing IPv6, consider all of the following together:

1. IPv6 address space of the VNet and subnets.
2. IPv6 support across VM size, NIC, public IP, and dependent services.
3. Network Security Groups, firewalls, routes, and DNS `AAAA` records.
4. How the application opens sockets, logs traffic, validates source IPs, and prioritizes protocols.
5. Limits and behavior of intermediate components such as load balancers, proxies, or hybrid links.

Do not assume every CLI operation or service supports IPv6 identically to IPv4. For predominantly IPv4 environments, finalize IPv4 flows first and test dual-stack as a separate architectural change.

## 7. How NSGs, Routes, and DNS Affect a NIC

A NIC holds IP configurations, but actual reachability also depends on **network permissions** and **packet paths**.

### Network Security Group

An NSG can be attached to a **subnet** and/or a **NIC**. Inbound/outbound rules use source, destination, port, protocol, and priority to allow or deny traffic.

If both the subnet and NIC have NSGs, traffic must satisfy the effective rules across all applied layers. NSGs are **stateful**: when a flow is permitted, return traffic for that flow is handled accordingly; this does not mean new connections initiated in the reverse direction are permitted.

For example, a VM with a public IP on its NIC still cannot accept SSH directly from the Internet over TCP/22 if the NSG does not permit it from the management network. Do not open `0.0.0.0/0` to SSH/RDP just to test connectivity when safer administrative access options exist.

You can inspect **effective security rules** in the Azure Portal or via network diagnostic tools when the NIC is attached to a running VM.

### Route Tables and Next Hop

Subnets have Azure system routes and can also have **user-defined routes (UDRs)** to steer specific traffic through a firewall or NVA. As a result, even if a destination IP is in the expected range, packets may take a different path.

Common routing pitfalls include a `0.0.0.0/0` route sending all traffic through a firewall that does not permit it, source and destination networks using overlapping CIDRs, missing return routes, or an NVA not forwarding packets.

### DNS

DNS lets applications locate services by name rather than hardcoded IPs. A VNet can use Azure-provided DNS or custom DNS servers. Azure also allows configuring DNS servers at the NIC level in supported scenarios.

If using custom DNS servers, ensure network paths and NSGs allow the VM to reach those resolvers. Changing DNS settings on a VNet/NIC may require renewing the DHCP lease, refreshing network configuration, or restarting the VM depending on the situation so the guest OS picks up the new settings.

**DNS does not assign IPs to a NIC.** DNS resolves names; the Azure control plane manages IP configurations; DHCP delivers primary IP settings to the guest OS.

## 8. Hands-On: Reading and Creating a NIC with Azure CLI

The commands below assume you have permissions in a test subscription and have already prepared a valid **VNet and subnet**. Adjust the example names for your actual environment. This lab uses Bash or Azure Cloud Shell in Bash mode.

First, verify the active subscription to avoid operating in the wrong environment:

~~~bash
az account show --query "{subscription:name, id:id, tenant:tenantId}" -o table
~~~

Declare example variables:

~~~bash
RG="rg-network-lab"
VNET="vnet-lab"
SUBNET="snet-app"
NIC="nic-app-01"
IP="10.20.1.10"
~~~

This example assumes `snet-app` belongs to `vnet-lab`, has prefix `10.20.1.0/24`, and address `10.20.1.10` is available. **These are illustrative parameters; do not run resource-creation commands without verifying they exist and do not conflict with other environments.**

### Step 1: Inspect the Subnet

~~~bash
az network vnet subnet show \
  --resource-group "$RG" \
  --vnet-name "$VNET" \
  --name "$SUBNET" \
  --query "{id:id,prefix:addressPrefix,prefixes:addressPrefixes}" \
  -o json
~~~

A subnet may return `addressPrefix` or `addressPrefixes` depending on configuration and API model. Confirm the intended private IP lies within the appropriate IPv4 prefix, is not one of Azure's reserved addresses, and is not used by another resource.

### Step 2: Create a NIC with a Static Private IP

~~~bash
az network nic create \
  --resource-group "$RG" \
  --name "$NIC" \
  --vnet-name "$VNET" \
  --subnet "$SUBNET" \
  --private-ip-address "$IP"
~~~

The `--private-ip-address` option assigns a specific private IPv4 address to the NIC; Azure validates availability and correctness during creation. If you want Azure to allocate automatically, omit this option to use the default Dynamic allocation in standard cases.

### Step 3: Verify the IP Configuration

~~~bash
az network nic show \
  --resource-group "$RG" \
  --name "$NIC" \
  --query "{name:name,vm:virtualMachine.id,ipConfigs:ipConfigurations[].{name:name,privateIp:privateIPAddress,allocation:privateIPAllocationMethod,primary:primary}}" \
  -o json
~~~

The output should show the private IP and corresponding allocation method. If `virtualMachine` is `null`, the NIC is not yet attached to a VM. Having a NIC exist does not prove the workload inside the VM is running.

View details of the primary configuration:

~~~bash
az network nic ip-config show \
  --resource-group "$RG" \
  --nic-name "$NIC" \
  --name "ipconfig1" \
  -o json
~~~

The default name is usually `ipconfig1` for NICs created via Azure CLI; if the actual name differs, retrieve it from the IP configuration list and substitute accordingly.

### Step 4: Update a Private IP During a Planned Change

For example, to move the address to `10.20.1.12` (after confirming it is available):

~~~bash
az network nic ip-config update \
  --resource-group "$RG" \
  --nic-name "$NIC" \
  --name "ipconfig1" \
  --private-ip-address "10.20.1.12"
~~~

Changing the IP of a NIC serving live traffic can drop active connections, break DNS/allowlists, and require updating dependent applications. Some NIC connectivity changes require stopping and deallocating the VM depending on the operation; verify exact requirements, prepare a maintenance window, and ensure a fallback management path before proceeding.

## 9. Attaching a Public IP When the Workload Truly Needs It

When there is a valid requirement for inbound Internet access to a VM, create a Standard Public IP resource:

~~~bash
PIP="pip-app-01"

az network public-ip create \
  --resource-group "$RG" \
  --name "$PIP" \
  --sku Standard \
  --allocation-method Static
~~~

Associate the public IP with a NIC IP configuration:

~~~bash
az network nic ip-config update \
  --resource-group "$RG" \
  --nic-name "$NIC" \
  --name "ipconfig1" \
  --public-ip-address "$PIP"
~~~

Check the allocated address:

~~~bash
az network public-ip show \
  --resource-group "$RG" \
  --name "$PIP" \
  --query "{address:ipAddress,sku:sku.name,allocation:publicIPAllocationMethod}" \
  -o json
~~~

For users to actually connect, also check: the VM has the NIC attached and is running, the NSG allows the application port from appropriate sources, the guest OS firewall permits it, the process listens on the right interface, and routing works.

**A Public IP can incur charges even if the workload receives little traffic.** In a lab, verify remaining resources after finishing and delete them when no longer needed according to your environment's permissions and procedures.

If you only want a web service publicly accessible, consider an Application Gateway or Load Balancer with a public frontend to shield individual backend VMs and centralize traffic control.

## 10. Multiple IP Configurations and Multiple NICs

### Adding a Second Private IP to the Same NIC

In a test environment, after ensuring `10.20.1.11` is available:

~~~bash
az network nic ip-config create \
  --resource-group "$RG" \
  --nic-name "$NIC" \
  --name "ipconfig-secondary" \
  --private-ip-address "10.20.1.11"
~~~

View both IP configurations:

~~~bash
az network nic show \
  --resource-group "$RG" \
  --name "$NIC" \
  --query "ipConfigurations[].{name:name,privateIp:privateIPAddress,primary:primary}" \
  -o table
~~~

Inside the guest OS, secondary private IPv4 addresses typically must be configured on the interface per Azure and OS documentation. If added only in Azure Portal/CLI without matching guest OS configuration, applications may fail to bind or respond on the secondary address.

### When Are Multiple NICs Needed?

A VM can use multiple NICs if supported by its VM size. Each NIC can connect to an appropriate subnet within the VM's **same VNet**; different NICs can connect to different subnets within that VNet. Common scenarios include NVAs, virtual firewalls, or servers requiring traffic-plane separation.

With multiple NICs, the guest OS must configure interfaces, routes, and default gateways properly. Unintended multiple default routes easily cause **asymmetric routing**: traffic enters one NIC but replies exit another, causing firewalls or intermediate appliances to drop packets.

### IP Forwarding

Azure NICs provide an **IP forwarding** option for cases where a VM must receive or send traffic whose source/destination IP is not the NIC's own IP, such as an NVA forwarding traffic. Enabling IP forwarding on the Azure NIC still requires configuring forwarding/routing in the guest OS and enforcing controls via NSGs, route tables, and firewalls.

**Do not enable IP forwarding on regular application VMs** just so they can call APIs or talk to databases.

### Accelerated Networking

Accelerated Networking can reduce latency and network processing overhead on supported VM sizes, operating systems, and images. Availability depends on the deployment environment, and it is a performance feature rather than a substitute for subnet/IP design or security policies.

## 11. Network Configuration Inside the Guest OS

Azure manages configuration in the control plane; Windows or Linux inside the VM must still have a **functioning network interface** receiving the proper IP, route, and DNS information.

### Linux

Common diagnostic commands:

~~~bash
ip -br address
ip route
ip route get 10.20.2.10
resolvectl status
~~~

`ip -br address` displays IPv4/IPv6 addresses on interfaces; `ip route` shows the routing table; `ip route get` previews the expected path to a destination. `resolvectl` is only present on systems using a compatible resolver; on other images, inspect DNS configuration with the appropriate tool.

### Windows

In PowerShell:

~~~powershell
Get-NetIPConfiguration
Get-NetIPAddress -AddressFamily IPv4
Get-NetRoute -AddressFamily IPv4
Get-DnsClientServerAddress
~~~

These are read-only status commands. Do not rush to change the primary address with `netsh`, `ip addr add`, or network manager configs to “match Azure”: first verify the NIC configuration and Azure-provided DHCP delivery. For secondary IPs, follow OS-specific secondary address instructions and check routing impacts.

## 12. Diagnosing Connectivity Issues Layer by Layer

When a VM cannot reach another workload, investigate in an order that isolates the root cause:

1. **Azure scope:** verify subscription, resource group, VNet, subnet, NIC, VM, and region.
2. **NIC/IP configuration:** inspect private IP, public IP association, primary/secondary flags, and VM attachment.
3. **Guest OS:** confirm the interface has the right IP, mask, routes, and DNS; check if the application is listening on the right address/port.
4. **NSG:** inspect rules on both subnet and NIC; view effective security rules if available.
5. **Routing:** check system routes, UDRs, next hop, VNet peering, VPN, firewall, and return routes.
6. **DNS:** distinguish name resolution failure from failure to connect to a known IP.
7. **Target application and service:** check guest OS firewall, service status, TLS, authentication, and logs.

### Azure Network Watcher Tools

Azure Network Watcher supports diagnostic capabilities depending on the environment, such as:

- **IP flow verify:** evaluates NSG rules to see whether a hypothetical flow is allowed or denied.
- **Next hop:** inspects the next hop for a network flow.
- **Connection troubleshoot:** tests reachability to a destination and provides diagnostic details.
- **Effective security rules/effective routes:** views active rules and routes for a NIC when supported by the VM and region.

One passing tool check does not validate the entire application stack. For example, if an NSG allows TCP/443 but the web server is not listening or the OS firewall blocks it, connections will still fail.

### Symptom Table

| Symptom | Common Cause | Where to Check |
|---|---|---|
| VM lacks expected IP | NIC set to Dynamic, static IP in wrong subnet, or guest OS mismatch | Azure IP configuration and guest DHCP info |
| Cannot SSH/RDP despite having a public IP | NSG, OS firewall, route, VM stopped, or service not listening | Port, inbound rules, source IP, and VM status |
| Ping gets no reply | ICMP blocked or target does not respond | Test appropriate TCP connectivity instead of relying solely on ping |
| Cannot connect to database by hostname | Misconfigured DNS, missing private DNS link, or name points to wrong IP | DNS lookup compared against target private IP |
| Can reach IP but not hostname | Wrong DNS resolution or application caching stale records | Resolver, TTL, A/AAAA records, and cache |
| Multi-NIC VM sends return traffic the wrong way | Default route or UDR causing asymmetric paths | Guest routes, next hop, and return routes |
| Secondary IP works in Azure but app does not listen | Secondary IP not configured in guest OS or app bound only to primary IP | Guest interface and socket bindings |
| Private VM needs outbound Internet but lacks access | No explicit egress design, blocked by UDR/firewall/NSG | NAT Gateway, default route, and outbound rules |

## 13. Designing a Secure Web–Data Workload

Suppose an application has two tiers:

- **Web VM** in subnet `10.20.1.0/24`, private IP `10.20.1.10`.
- **Database VM** in subnet `10.20.2.0/24`, private IP `10.20.2.10`.

Requirements: users can access the web tier; the database must not expose a public IP; the web tier may connect to the database only on the required port.

One approach:

~~~mermaid
flowchart TD
  U[Internet Users] --> F[Public frontend or application gateway]
  F --> W[Web VM / NIC 10.20.1.10]
  W -->|Allowed DB port| D[DB VM / NIC 10.20.2.10]
  W --> N[NAT Gateway or controlled egress path]
  D --> P[Private DNS and internal services]
~~~

Key decisions:

- The Web VM has a static private IP if configuration or integration requires a fixed address; the public frontend should be managed at an appropriate ingress tier.
- The Database uses only a private IP, with no direct public IP attached.
- NSGs at the subnet or NIC level permit only the required application ports, preferring application security groups or approved network ranges.
- Internal DNS resolves the database name to its private IP or private endpoint per architecture, avoiding unnecessary IP hardcoding.
- Workloads calling external Internet services use a governed outbound path, such as NAT Gateway, alongside proper logging and firewalling.
- When changing database addresses or migrating workloads, update DNS, client configurations, and test connectivity rather than changing only the Azure IP.

This design illustrates a NIC's role within a broader architecture: the NIC provides addresses and network attachment for the VM, while **security and availability** are also shaped by subnets, NSGs, routing, DNS, frontends, and the application itself.

## 14. Checklist for Changing IPs in a Live Environment

A small change in an IP configuration can impact many systems. Before making changes, document:

- Which NIC and IP configuration are affected; which subscription, resource group, and region are targeted.
- Whether the new IP lies in the subnet, avoids reserved addresses, and is unallocated.
- Which applications, DNS records, NSGs, routes, load balancers, allowlists, monitoring systems, or third parties reference the old IP.
- Whether the change requires stopping/deallocating the VM or refreshing the guest OS.
- How connectivity will be verified before and after, success criteria, and change window.
- Rollback plan using the original IP/configuration and required permissions.
- Owners responsible for communication, testing, updating IPAM records, and cleaning up test resources.

After execution, validate all three levels: **Azure NIC/IP**, **guest OS**, and **actual application connectivity**. A successful update command in Azure does not guarantee all clients have switched to the new IP.

## 15. Hands-On Exercise and Self-Check Questions

### Scenario

You need to prepare a NIC for an application VM in VNet `10.20.0.0/16`, subnet `10.20.1.0/24`, with private IP `10.20.1.10`. The workload connects to an internal database at `10.20.2.10` and does not need an inbound public IP.

**Tasks:**

1. Explain why `10.20.1.1` is invalid to manually assign to this NIC.
2. Create the NIC with private IP `10.20.1.10` via Azure CLI after confirming the subnet and IP availability.
3. Use `az network nic show` to confirm the IP allocation method and IP configuration name.
4. Explain why the VM should continue receiving its primary IPv4 address via DHCP even though the NIC is set to Static in Azure.
5. Describe the minimum NSG rules needed for the web VM to reach the database on the approved application port.
6. List checks to perform if the VM fails to resolve the database hostname while direct IP access still succeeds.
7. Propose how to provide outbound Internet access if the workload needs package updates without a direct public IP.
8. Describe the impact and test plan if the private IP changes from `10.20.1.10` to `10.20.1.12`.

### Self-Check Questions

**Question 1.** How many IP configurations can a single NIC hold? Does having two private IPs in Azure guarantee the guest OS automatically uses both?

**Question 2.** How does a Static private IP differ from a Standard public IP in usage scope and function?

**Question 3.** Why should you avoid attaching a public IP directly to every production VM?

**Question 4.** When NSGs allow traffic yet the workload remains unreachable, which layers should you inspect next?

**Question 5.** For a VM with multiple NICs, what configuration can cause asymmetric routing?

**Completion criteria:** you can describe the roles of NICs and IP configurations, create/read NIC settings via Azure CLI, choose Dynamic or Static appropriately, distinguish public vs. private IPs, and troubleshoot connectivity from the Azure control plane down to the guest OS.

## Conclusion

A network interface is a VM's network attachment point in Azure; IP configurations govern private addresses, allocation methods, and optional public IP associations. A proper configuration must align with subnets, routing, NSGs, DNS, and guest OS networking state. By understanding the difference between **Static in Azure** and **DHCP inside the VM**, as well as between **reachable IPs** and **actually permitted traffic**, you will deploy more reliable workloads and reduce outage risks when operating Azure networks.
