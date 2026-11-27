# Subnets, Public IPs, and Private IPs

When building an application on Microsoft Azure, components such as virtual machines, web services, databases, and management systems must communicate over controlled network paths. Three foundational concepts for designing that network are **subnets**, **private IP addresses**, and **public IP addresses**.

For example, a retail system might accept Internet users through a public entry point, while order-processing servers and databases use only private connectivity. Proper design reduces the attack surface, controls data flows, supports scaling, and helps monitor costs. This lesson belongs to the *Virtual Networks and Name Resolution* chapter and establishes the foundation for Azure architectures combining Virtual Network, Azure DNS, App Service, virtual machines, storage, and data services.

## Learning Objectives

After this lesson, you will be able to:

1. Explain the relationship between an Azure Virtual Network (VNet), subnets, and IP addresses.
2. Read and calculate IPv4 address counts in a CIDR range, including Azure-reserved addresses.
3. Distinguish between private IPs, public IPs, and dynamic vs. static allocation methods.
4. Understand inbound and outbound Internet traffic paths for Azure resources and the roles of NAT Gateway, NSGs, and DNS.
5. Design non-overlapping subnets for a multi-tier application.
6. Create, view, and inspect VNets, subnets, and Public IPs using the Azure portal or Azure CLI.
7. Identify common misconfigurations and verify connectivity safely.

## 1. How Do VNets, Subnets, and IP Addresses Relate?

**Azure Virtual Network (VNet)** is a logical private network foundation for Azure resources. When creating a VNet, you declare one or more IP address ranges for internal components to use. You then divide these ranges into **subnets**, each representing a portion of the VNet's address space.

Example:

~~~text
VNet: vnet-sales            10.42.0.0/16
  |
  +-- snet-ingress          10.42.0.0/24
  +-- snet-web              10.42.1.0/24
  +-- snet-app              10.42.2.0/24
  +-- snet-private-endpoint 10.42.3.0/27
~~~

In this design, all subnets reside inside the VNet address space without overlapping. A virtual machine's Network Interface (commonly called a **NIC**) connects to a subnet. The NIC has an IP configuration to receive a private address from that subnet's range. Certain managed services use VNet integration or dedicated subnets according to their own service requirements.

**A subnet is not an automatic firewall mechanism.** Within the same VNet, Azure provides system routing that enables subnets to communicate with one another. To allow or block specific traffic flows, you must configure network controls such as Network Security Groups (NSGs), Azure Firewall, route tables, or equivalent security features.

## 2. IP Addresses and CIDR Notation

An IPv4 address has 32 bits, typically written as four decimal numbers separated by dots, such as **10.42.2.10**. **CIDR** notation appends a slash and the network prefix length:

~~~text
10.42.2.0/24
         ^^
       24 network bits; 8 bits remaining for addresses in the range
~~~

For an IPv4 range with prefix **/p**, the total number of addresses is **2^(32 − p)**. When designing subnets on Azure, you must also account for addresses reserved by the platform.

| CIDR Range | Total IPv4 Addresses | Reserved by Azure | Addresses Allocatable to Resources |
|---|---:|---:|---:|
| /24 | 256 | 5 | 251 |
| /26 | 64 | 5 | 59 |
| /27 | 32 | 5 | 27 |
| /28 | 16 | 5 | 11 |
| /29 | 8 | 5 | 3 |

**Azure reserves five IPv4 addresses in every subnet:** the first four addresses and the last address. For subnet **10.42.2.0/24**, the reserved addresses are **10.42.2.0** through **10.42.2.3** and **10.42.2.255**; for instance, **10.42.2.10** falls in the allocatable range.

Note: some services require a larger minimum subnet size or a dedicated subnet. Do not create a /29 subnet just because the current resource count is tiny; also account for scaling demand, buffer addresses, future additions, and service requirements.

### Planning Address Ranges

Private IPv4 address spaces typically use RFC 1918 ranges:

- **10.0.0.0/8**
- **172.16.0.0/12**
- **192.168.0.0/16**

Every subnet must fit inside a VNet address space and must not overlap with any other subnet in the same VNet. When planning to connect to other VNets via peering, or to on-premises networks via VPN or ExpressRoute, plan so that networks needing to route to each other also do not have overlapping address ranges. If network ranges overlap, establishing connectivity and routing may not work as intended.

For example, avoid using **10.42.1.0/24** simultaneously for both the Azure network and the corporate office network if the two will connect via VPN. Choose a different range for the Azure subnet or plan appropriate address translation before connecting.

## 3. Private IPs in Azure

A **Private IP** is an address used for communication within a VNet and legitimately connected networks. In standard designs, private IPs fall within RFC 1918 ranges. Private addresses are not directly routable over the public Internet.

For instance, a VM running an API receives IP **10.42.2.10** in subnet **snet-app**. Another VM in the VNet, or an on-premises device with appropriate connectivity and routing, can reach this IP if security rules permit it.

Private IPs are used by many components depending on the service:

- NICs of Azure Virtual Machines.
- Internal frontend IPs of Azure Load Balancer or Application Gateway.
- Private Endpoints providing private connectivity to supported services such as Storage or Azure SQL.
- Certain services using VNet injection, subnet delegation, or service-specific private networking integration.

### Dynamic and Static Private IP Allocation

For Azure VM NICs, Azure manages private IP allocation settings:

| Mode | How It Works | When to Use |
|---|---|---|
| **Dynamic** | Azure selects an available address from the subnet for the NIC's IP configuration | VMs or resources that do not need a specific pre-selected address |
| **Static** | You specify an available and valid IPv4 address within the subnet | Resources requiring a predictable internal address per architecture needs |

**A static private IP does not mean manually hardcoding an arbitrary address inside the operating system.** For Azure VMs, configure the allocation on the NIC's IP configuration in Azure, and ensure the OS network configuration remains compatible with Azure networking. Never assign an address outside the subnet, within Azure's five reserved addresses, or already used by another resource.

Even though a dynamic address typically remains stable throughout a NIC's lifecycle, applications should still rely on DNS or service discovery rather than hardcoding IP addresses into source code.

### Can Private IPs Communicate Across Subnets?

Yes. Subnets within the same VNet can generally route to each other via default system routes. Whether a connection succeeds depends on:

- NSGs at the subnet and/or NIC level, covering both inbound and outbound directions.
- Route tables and intermediate appliances such as Azure Firewall, if configured.
- OS-level firewalls, service ports, and listening processes.
- DNS resolution and application-layer authorization.

For example, a VM at **10.42.1.10** in **snet-web** can call an API at **10.42.2.10:443** in **snet-app** when routing and policies allow it. Placing the two machines in separate subnets enables tier-based policies, but separating subnets alone does not block traffic.

## 4. Public IPs in Azure

A **Public IP** is an address routable on the Internet and is used when a resource or frontend must communicate over public networks. Azure provides a **Public IP Address** as a standalone resource to associate with supported components, such as:

- A virtual machine NIC's IP configuration.
- The frontend of a public Azure Load Balancer.
- An Application Gateway with a public frontend.
- Azure NAT Gateway or other supported networking services.

With a **Standard Public IP** resource, the address is allocated using **static** allocation. When creating the resource, you can select the IP version, region, and available options suited to the service and architecture. Zone and deployment scope options depend on the Public IP type and regional support.

**Having a Public IP does not mean a server exposes all ports to the Internet.** Actual traffic remains governed by NSGs, OS firewalls, service configurations, routing, and other security layers. However, attaching a Public IP creates an additional network entry point that must be controlled. Avoid assigning a Public IP to every VM solely for administrative convenience.

### Where Are Public IPs Attached?

For a VM, the private address belongs to an IP configuration on the NIC; a Public IP, if used directly, is associated with that NIC's IP configuration. A Public IP **does not belong to the subnet's private address range**. A subnet can contain many NICs using private IPs without having any Public IPs at all.

Example:

~~~text
Internet
   |
Public IP (e.g., an Azure-assigned address)
   |
Application Gateway or Load Balancer frontend
   |
VNet: 10.42.0.0/16
   |
Application VM: 10.42.2.10 (private IP)
~~~

Here, users connect to the public frontend. The backend application VM still only needs a private IP. The frontend receives and forwards traffic as configured, while NSGs and other security layers restrict permitted access paths.

## 5. Comparing Private IPs and Public IPs

| Criterion | Private IP | Public IP |
|---|---|---|
| Scope of use | Inside a VNet and properly connected/routed networks | Routable over the public Internet |
| Address source | An address range belonging to a subnet, for subnet-bound resources | Issued by Azure as a Public IP resource or managed by a service |
| Can overlap across organizations? | Yes, in independent non-connected networks | Active addresses must be unique on the public Internet |
| VM configuration | NIC IP configuration | Public IP associated with the NIC configuration if the VM needs a direct Public IP |
| Common use cases | Internal APIs, databases, backends | Web entry points, public load balancers, outbound NAT addresses |
| Control requirements | NSGs, routes, firewalls, application permissions | Additional Internet access controls, firewalls, TLS, and attack monitoring |
| Cost | Usually part of related network/compute configuration; accompanying network services may incur charges | Public IPs and related services may incur charges based on configuration and duration |

A private IP does not guarantee a resource is secure: misconfigured permissions or overly broad network rules can still create risk. Likewise, a public IP does not imply a security vulnerability, provided there is a valid business need and appropriate protective controls.

## 6. Inbound and Outbound Internet Traffic Paths

You should distinguish **inbound** (Internet to workload) from **outbound** (workload to Internet) traffic.

### Inbound Traffic

A web application may need to accept HTTPS from clients on the Internet. Instead of assigning a Public IP to each application server, a common pattern is placing a controlled public entry point, such as an Application Gateway or Azure Load Balancer with an appropriately configured frontend and listener.

Illustrative flow:

~~~text
Users on the Internet
        |
        v
Public IP / HTTPS frontend
        |
        v
Application Gateway (dedicated subnet as required)
        |
        v
Backend servers or services using private IPs
        |
        v
Database with private-only access path
~~~

If a VM needs administrative ports, consider Azure Bastion, VPN, or a private management path instead of exposing RDP/SSH directly to the Internet. For PaaS services, the public entry point may be managed separately by the service without creating a Public IP resource inside your resource group.

### Outbound Traffic

A VM with only a private IP may still need to reach package repositories for updates, call partner APIs, or send data to public endpoints. Depending on the network design, outbound connectivity can use:

- **Azure NAT Gateway:** provides managed outbound connectivity for a subnet using an attached Public IP or Public IP Prefix; it does not create unsolicited inbound paths to the VM.
- **Azure Firewall:** inspects and logs traffic according to policy when routing is directed through the firewall.
- **Load Balancer outbound rules** or other service-supported outbound mechanisms.

Do not rely on implicit default outbound access, as behavior depends on configuration and platform changes. For production, explicitly define egress IPs, allowlisting needs, permitted traffic, and outbound data transfer costs.

**NAT Gateway lets multiple private VMs share one or a group of Public IPs for outbound traffic.** The machines retain their private IPs, while external Internet services see the NAT's public address. This does not mean VMs automatically accept incoming connections from the Internet.

## 7. Subnets, NSGs, Route Tables, and DNS

Subnets are units for organizing IP addresses, but a secure network architecture requires coordinating additional components.

### Network Security Group (NSG)

An NSG contains rules that allow or deny traffic based on source, destination, port, protocol, and direction. NSGs can be associated with subnets and/or NICs. For example:

- Allow HTTPS only from the frontend to the backend on the required port.
- Deny direct Internet access to the application subnet.
- Restrict administrative protocols to trusted addresses or networks.

An NSG is a network traffic filter; it does not replace user authentication, application authorization, WAF, or data protection mechanisms.

### Route Tables and Peering

Azure creates default system routes for intra-VNet communication. You can use a **User Defined Route (UDR)** to steer traffic through a firewall or appliance. When two VNets need to communicate, **VNet peering** can connect them if the respective conditions and configurations are met.

Having a network route does not guarantee access permission. NSG rules, firewalls, endpoint settings, and application permissions still determine whether traffic is accepted.

### DNS Is Not the Same as an IP

**DNS** translates names into address information according to the appropriate records. In Azure networking:

- Public DNS records can direct users to a frontend using a Public IP.
- Internal names can resolve to private IPs via an appropriate DNS service.
- **Azure Private DNS Zone** is commonly paired with Private Endpoints to resolve PaaS service names to private addresses.

For example, users visit **shop.example.com** and receive the frontend's public address. Internal applications access the database via a DNS name configured to resolve to the Private Endpoint's IP. Changing an IP may require updating DNS records or integrated DNS settings; therefore, design around service names whenever possible.

## 8. Designing Subnets for a Three-Tier Application

Suppose a retail system has an HTTPS ingress tier, an API processing tier, and a private connection to Azure SQL Database. An addressing plan might look like this:

| Component | Subnet | CIDR | Purpose |
|---|---|---|---|
| Frontend Application Gateway | snet-ingress | 10.42.0.0/24 | Dedicated to the gateway per deployment requirements |
| Web or presentation servers | snet-web | 10.42.1.0/24 | Runs web-serving components using private IPs |
| Internal API | snet-app | 10.42.2.0/24 | Runs backend services with only required ports open |
| Private Endpoint | snet-private-endpoints | 10.42.3.0/27 | Holds private IPs for accessing Private Link-supported PaaS services |

All subnets reside in **10.42.0.0/16**, each with its own distinct CIDR. The following logical diagram illustrates the flow:

~~~text
                    INTERNET
                       |
                   Public IP
                       |
          Application Gateway / HTTPS
            snet-ingress (10.42.0/24)
                       |
                    Private IP
                       |
             Web (10.42.1.0/24)
                       |
                Internal HTTPS
                       |
             API (10.42.2.0/24)
                       |
                 Private DNS
                       |
           Private Endpoint (Private IP)
            snet-private-endpoints
                       |
                Azure SQL Database
~~~

For PaaS services, subnets and connectivity mechanisms vary by resource type. For example, Azure App Service uses VNet Integration for outbound traffic and a separate Private Endpoint for inbound traffic; do not treat App Service like a VM with its own NIC in an arbitrary subnet. In real deployments, review subnet delegation, minimum subnet size, Private Endpoint, and access permission requirements for each service.

Security decisions to document:

1. Which tiers need a public address, and which should only have private IPs?
2. Which subnets need to exchange data, and on which ports?
3. Which outbound flows require a NAT Gateway or firewall?
4. How should DNS resolution work for the frontend and PaaS services?
5. How many addresses should be reserved for growth and additional services?
6. Do any CIDR ranges conflict with other VNets or corporate office networks?

## 9. Hands-On: Creating a VNet and Subnets with Azure CLI

The example below creates a simple network environment in the **Southeast Asia region**. The commands are illustrative and should only be run in an authorized subscription. Confirm costs and quotas before creating resources, especially if adding Public IPs or paid networking services.

### Step 1: Select a Subscription and Create a Test Resource Group

~~~bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"

az group create \
  --name rg-network-lab \
  --location southeastasia
~~~

Use a dedicated resource group for the lab exercise. The Subscription ID in the example is a placeholder and must be replaced with an authorized subscription.

### Step 2: Create the VNet and First Subnet

~~~bash
az network vnet create \
  --resource-group rg-network-lab \
  --name vnet-sales \
  --location southeastasia \
  --address-prefixes 10.42.0.0/16 \
  --subnet-name snet-web \
  --subnet-prefixes 10.42.1.0/24
~~~

The command creates a VNet with address space **10.42.0.0/16** and web subnet **10.42.1.0/24**.

### Step 3: Add the API and Private Endpoint Subnets

~~~bash
az network vnet subnet create \
  --resource-group rg-network-lab \
  --vnet-name vnet-sales \
  --name snet-app \
  --address-prefixes 10.42.2.0/24

az network vnet subnet create \
  --resource-group rg-network-lab \
  --vnet-name vnet-sales \
  --name snet-private-endpoints \
  --address-prefixes 10.42.3.0/27
~~~

In this lab, the subnets are created solely to illustrate CIDRs. No VMs, Private Endpoints, NSGs, or access rules have been deployed; naming a subnet does not automatically provision those services.

### Step 4: Inspect the Network Configuration

~~~bash
az network vnet show \
  --resource-group rg-network-lab \
  --name vnet-sales \
  --query "{name:name,addressSpace:addressSpace.addressPrefixes,location:location}" \
  --output json

az network vnet subnet list \
  --resource-group rg-network-lab \
  --vnet-name vnet-sales \
  --output table
~~~

Verify subnet names, CIDR ranges, and non-overlap. If a subnet is created with the wrong range, check IP usage status and constraints of attached resources before modifying it.

### Step 5: Create an Illustrative Public IP

~~~bash
az network public-ip create \
  --resource-group rg-network-lab \
  --name pip-lab \
  --location southeastasia \
  --sku Standard \
  --allocation-method Static

az network public-ip show \
  --resource-group rg-network-lab \
  --name pip-lab \
  --query "{name:name,ip:ipAddress,sku:sku.name}" \
  --output table
~~~

The newly created Public IP is a **standalone resource**. It is not yet attached to a NIC, Load Balancer, or Application Gateway, and does not create an application entry point by itself. A Public IP can incur costs even when not serving traffic; delete it after testing if it is no longer needed.

### Step 6: Clean Up After the Lab

~~~bash
az network public-ip delete \
  --resource-group rg-network-lab \
  --name pip-lab
~~~

Only when **rg-network-lab** is a dedicated lab resource group and you have confirmed no resources inside need to be kept should you delete the entire group along with its subnets and VNet:

~~~bash
az group delete \
  --name rg-network-lab \
  --yes
~~~

Deleting a resource group also deletes all resources inside it and may be irreversible. After cleanup, check Azure Cost Management if you need to track any incurred charges.

## 10. Equivalent Operations in the Azure Portal

When using the web interface:

1. Sign in to the **Azure portal** and verify the correct tenant and subscription.
2. Open **Virtual networks**, select **Create**, and enter the resource group, VNet name, and region.
3. Declare the address space, such as **10.42.0.0/16**, then create non-overlapping subnets.
4. Review the configuration before creating. Once the VNet exists, open **Subnets** to add or adjust subnets depending on resource state.
5. Open **Public IP addresses** to view or create Public IP resources according to SKU, region, and supported options.
6. Associate a Public IP with a NIC or service frontend only when there is a designed ingress/egress requirement and appropriate security controls are in place.

Tab and form labels in the portal may change across UI updates. The principles that remain constant are: valid CIDRs, accurate subscription scope, purpose-bound Public IPs, and explicit traffic policies.

## 11. Diagnosing Common Network Issues

| Symptom | Possible Cause | Where to Check |
|---|---|---|
| Cannot create subnet | CIDR outside VNet, overlapping, or fails service requirements | Inspect address space and existing prefixes |
| Cannot assign static private IP | Address reserved by Azure, already in use, or outside subnet | Check NIC IP configuration and used IPs in the subnet |
| VMs in two subnets cannot connect | NSG, UDR, OS firewall, or service not listening | Check effective security rules, routes, and service ports |
| Has Public IP but VM is unreachable | Missing inbound rule, firewall blocking, service down, or unlinked frontend | Check NSG, NIC/frontend association, IP, and app ports |
| Private-only VM cannot reach Internet | No suitable outbound path or egress blocked | Check NAT Gateway, firewall, routes, DNS, and outbound rules |
| PaaS traffic still goes via public IP | DNS or Private Endpoint not properly configured | Check name resolution results, Private DNS Zone, and network path |
| Peering/VPN not routing as expected | Overlapping CIDRs, incorrect routes, or incomplete gateway/peering setup | Compare address spaces, effective routes, and connection settings |

Useful tools and views include **Network Watcher**, **effective routes**, **effective security rules**, connection troubleshooting, enabled NSG or firewall logs, and DNS tools such as **nslookup** or **dig**. When troubleshooting, inspect both directions of traffic rather than checking only the source machine.

Example: the web VM cannot call the API at **10.42.2.10:443**. A logical sequence is to confirm DNS or destination IP, verify the API is listening on port 443, inspect NIC/subnet NSGs, check routes and the OS firewall, and then re-test connectivity. Do not open all ports or disable NSGs just to make a temporary test succeed.

## 12. Misconceptions to Avoid

**“Creating two subnets completely isolates two applications.”** Subnets organize addresses and apply policies; network traffic between them can still be routed unless rules explicitly block it.

**“Private IPs are directly reachable from anywhere on the Internet.”** Private IPs are not directly routable on the public Internet; an appropriate path such as VPN, peering, or an intermediate endpoint/frontend plus matching permissions is required.

**“A VM needs a Public IP to download updates.”** A VM with a private IP can use a NAT Gateway, firewall, or supported outbound solution, so it does not need its own Public IP just for outbound access.

**“Once a Public IP is created, the web server automatically works.”** A Public IP is just an address resource. It still must be associated with a frontend or NIC, with listeners, network paths, and security rules configured.

**“You can pick any static IP inside a subnet.”** You must choose a valid, unused address that is not among Azure's five reserved IPv4 addresses.

**“DNS and IP are the same thing.”** DNS is a name resolution mechanism; an IP address is used for routing and communication. One DNS name can map to different addresses depending on the design.

**“Private addresses never cause conflicts.”** Independent VNets can use identical ranges, but when direct connectivity between them or to on-premises networks is needed, overlapping CIDRs can block routing.

## 13. Hands-On Exercise and Self-Check

### Scenario

You are tasked with designing an Azure network for an inventory management application consisting of an HTTPS frontend, a backend API, an internal batch-processing VM, and Azure Storage accessed via a Private Endpoint. The organization already has VNet **10.60.0.0/16** and plans to connect the office network **192.168.100.0/24** over VPN.

Tasks:

1. Propose at least three non-overlapping subnets for the resource groups needing to use the VNet.
2. Calculate the number of allocatable addresses for subnet **10.60.10.0/27** in Azure.
3. Identify which component needs a public entry point and which components should only have private IPs.
4. Propose how the internal VM can access the Internet for software updates without assigning it a direct Public IP.
5. List the network flows that should be allowed via NSGs and the flows that should be denied.
6. Explain why private DNS configuration is needed for the Storage Private Endpoint.

A sound approach might use a dedicated subnet for the frontend gateway, a backend subnet, and a Private Endpoint subnet; keep the internal worker VM on a private IP only; route egress via NAT Gateway or a firewall; and use the HTTPS frontend as the controlled public entry point. For **10.60.10.0/27**, there are **32** IPv4 addresses total; Azure reserves **5**, leaving **27** addresses allocatable to resources. Adjust subnet sizes if any planned service has specific requirements.

### Self-Check Questions

1. How do a VNet, a subnet, and a private IP differ?
2. Why cannot **10.42.1.0/24** and **10.42.1.128/25** be used as two independent subnets in the same VNet?
3. How many IPv4 addresses can be assigned to resources in a /26 subnet on Azure?
4. For a VM NIC, what is the difference between a dynamic and a static private IP?
5. Which types of frontends use a Standard Public IP? Does creating a Public IP automatically open ports to a VM?
6. When a VM has no Public IP, what options exist for designing outbound traffic?
7. Why are NSGs still needed even after separating web and API into two subnets?
8. What role does DNS for a Private Endpoint play when an application accesses a PaaS service?
9. Why should overlapping CIDRs be avoided between an Azure VNet and an on-premises network slated for connection?

## References

- Microsoft Learn — *What is Azure Virtual Network?*: https://learn.microsoft.com/azure/virtual-network/virtual-networks-overview
- Microsoft Learn — *Add, change, or delete a virtual network subnet*: https://learn.microsoft.com/azure/virtual-network/virtual-network-manage-subnet
- Microsoft Learn — *IP address types and allocation methods in Azure*: https://learn.microsoft.com/azure/virtual-network/ip-services/public-ip-addresses
- Microsoft Learn — *Private IP addresses for Azure*: https://learn.microsoft.com/azure/virtual-network/ip-services/private-ip-addresses
- Microsoft Learn — *Azure NAT Gateway*: https://learn.microsoft.com/azure/nat-gateway/nat-overview
- Microsoft Learn — *Network Security Groups*: https://learn.microsoft.com/azure/virtual-network/network-security-groups-overview
- Microsoft Learn — *Azure Private Endpoint*: https://learn.microsoft.com/azure/private-link/private-endpoint-overview
