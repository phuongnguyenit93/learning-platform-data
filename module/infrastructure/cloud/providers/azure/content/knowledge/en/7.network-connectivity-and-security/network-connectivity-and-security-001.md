# Point-to-Site and Site-to-Site Connectivity with VPN Gateway

## 1. Lesson Objectives

An application on Microsoft Azure may consist of virtual machines, data services, private subnets, application components, and monitoring tools. Many components should only be accessed via private IP addresses within a virtual network (VNet). However, remote employees and on-premises office systems still need secure connectivity to those resources.

**Azure VPN Gateway** provides the capability to establish encrypted VPN tunnels over the Internet, connecting an Azure VNet to external devices or client machines. Two key models are:

- **Point-to-Site (P2S):** a single user device, such as an engineer's laptop, establishes a VPN connection to Azure.
- **Site-to-Site (S2S):** a VPN device at a branch office or data center connects the organization's internal network to Azure.

After this lesson, you will be able to distinguish between P2S and S2S, design non-overlapping IP address spaces, provision a VPN Gateway, configure both connectivity models, understand authentication and routing, verify security and availability, and troubleshoot common issues.

## 2. Comparing P2S and S2S

| Criterion | Point-to-Site (P2S) | Site-to-Site (S2S) |
|---|---|---|
| Target audience | Personal computers, remote-work devices | Office networks, branch offices, data centers |
| External endpoint | VPN client on each device | Site router or firewall/VPN device |
| Connection model | Users connect per session | Tunnel between two network endpoints, typically maintained continuously |
| Authentication | Can use certificates, Microsoft Entra ID, or RADIUS depending on supported protocols and SKUs | Typically uses IPsec/IKE with a pre-shared key (PSK); can include BGP for routing |
| Client IP assignment | Addresses from the P2S client address pool | Uses existing network ranges at the site |
| Typical scale | Access for individuals, operations teams, and remote workers | Linking offices with workloads in Azure |
| Key considerations | Client installation, identity, profiles, DNS, and routes on the machine | Compatible device, public IP, PSK/IKE, and bidirectional routing |

**Example:** an engineer working from home uses P2S to SSH or RDP into an internal VM in Azure. Meanwhile, an ERP system at the office needs to call an API inside an Azure VNet over S2S so the entire internal network has a persistent connection path.

P2S and S2S can share the same VPN Gateway if the SKU, configuration, and product limits allow it. They solve two different needs, and you do not necessarily have to choose only one model.

## 3. Components to Understand

### 3.1. Azure Virtual Network and Subnets

**Virtual Network (VNet)** is a private network space in Azure. Inside a VNet are subnets for workloads, such as a subnet for application VMs or databases. Workloads communicate via private IP addresses and are controlled using routes, Network Security Groups (NSGs), firewalls, or appropriate network policies.

### 3.2. Virtual Network Gateway

A **virtual network gateway** of type **VPN** is an Azure resource that provides VPN connectivity into a VNet. The gateway type, SKU, and configuration determine the supported protocols, throughput, number of connections, and redundancy capabilities.

It is important to distinguish a **VPN gateway** from an **ExpressRoute gateway**: ExpressRoute uses a private connection provided by a connectivity provider, whereas VPN Gateway builds encrypted tunnels over the Internet. For this lesson, we use a gateway of type VPN.

### 3.3. GatewaySubnet

Azure VPN Gateway requires a dedicated subnet named exactly **GatewaySubnet** inside the VNet. This subnet is used by Azure to deploy the gateway infrastructure; do not place VMs or application workloads here.

When creating a new VNet, plan for a **GatewaySubnet with a /27 prefix or larger address space**, depending on the gateway type and growth needs. For example, a /27 subnet contains more addresses than a /28. Avoid creating a subnet that is too small and having to re-address it when upgrading.

Avoid arbitrarily applying NSGs or user-defined routes to the GatewaySubnet, as this can break the gateway; always follow Azure's support guidelines for the specific SKU and deployment model.

### 3.4. VPN Gateway Public IP

The gateway uses one or more **public IP addresses** as the Azure-side VPN termination endpoint. A public endpoint is required to establish tunnels over the Internet; it does not mean that VMs inside the VNet must have public IPs.

Choose the Public IP type, SKU, and availability zone configuration according to the requirements of the current VPN Gateway. New deployments typically use Standard Public IPs matching the corresponding gateway SKUs. Some active-active models require two separate public IPs.

### 3.5. Local Network Gateway for S2S

**Local network gateway (LNG)** is a configuration resource in Azure that describes the **network endpoint outside Azure**, such as:

- The public IP or supported FQDN of the VPN device at the office.
- The IP address ranges belonging to the office network that need to be routed through the tunnel.
- BGP configuration of the external peer, if dynamic routing is used.

An LNG **is not a virtual machine or VPN appliance deployed by Azure at the office**. The actual VPN device still belongs to the on-premises infrastructure and must be configured by the network team.

### 3.6. Connection

**Connection** is the resource that links the Azure VPN Gateway with the Local Network Gateway in an S2S setup and stores the required settings, such as the pre-shared key. The connection status helps verify whether the tunnel has been established.

In P2S, client machines use the VPN client configuration and authentication method configured on the virtual network gateway; there is no need to create a separate Local Network Gateway for each laptop.

## 4. Reference Architecture Sharing P2S and S2S

Suppose an organization has an application running in an Azure VNet, remote workers, and a branch office with an internal system.

~~~mermaid
flowchart LR
    A[P2S Employee Laptop] -->|Encrypted VPN over Internet| GW[Azure VPN Gateway]
    B[Office Network 172.16.10.0/24] --> FW[VPN Router or Firewall]
    FW -->|S2S IPsec/IKE over Internet| GW
    subgraph AZ[Azure VNet 10.20.0.0/16]
        GW --> GS[GatewaySubnet]
        GS --> APP[Application Subnet 10.20.1.0/24]
        APP --> VM[VM or Service Using Private IP]
    end
~~~

The diagram illustrates the logical connection flow; the gateway operates with Azure's network fabric and is not a user-managed router VM placed inside an application subnet. Both P2S and S2S branches can reach permitted workloads in the VNet.

Example addressing plan:

| Component | Sample Address Range | Purpose |
|---|---|---|
| Azure VNet | 10.20.0.0/16 | Azure network space |
| Application subnet | 10.20.1.0/24 | VMs and workloads |
| GatewaySubnet | 10.20.255.0/27 | Reserved for Azure VPN Gateway |
| Office network | 172.16.10.0/24 | On-premises site connected via S2S |
| P2S client address pool | 172.20.10.0/24 | Assigns addresses to P2S clients |
| Office device public IP | 203.0.113.10 | Illustrative value for the S2S VPN endpoint |

**203.0.113.10** belongs to an address range reserved for documentation examples, not a real endpoint that can be used to establish a tunnel. In a real environment, replace it with the actual public address of the VPN device or an endpoint identification method supported by Azure.

The private ranges above are examples. You must verify that prefixes are **non-overlapping**, including Azure networks, the office, other branches, client pools, and even the local LAN where users connect from. If ranges overlap, the operating system or router may choose the wrong path, even when the VPN reports Connected.

## 5. Decisions to Finalize Before Deployment

### 5.1. Access Scope

List the exact services that need to be accessed and from where. For example:

- Engineer laptop → management VM in a private subnet.
- Office network → internal API in Azure.
- Azure VNet → data server at the office, if bidirectional traffic is required.

Do not open the entire network just because the VPN is encrypted. Configure user permissions, NSGs, Azure Firewall, and OS/workload firewalls strictly according to requirements.

### 5.2. Address Planning

Create an addressing table for the VNet, GatewaySubnet, target subnets, on-premises sites, P2S pool, and peered VNets. Check future subnets that may be added later as well. Resolving overlapping address spaces after going into production is much harder than choosing correctly from the start.

If address ranges at two sites already overlap, consider re-IPing or using VPN NAT mechanisms on supported models and SKUs. Never assume VPN automatically resolves IP conflicts.

### 5.3. Choosing Gateway Type, VPN Type, and SKU

For systems requiring both P2S and S2S, you typically choose **VPN Gateway with gateway type VPN and VPN type RouteBased**. Some legacy devices or S2S scenarios use PolicyBased, but that type has feature limitations and is not a general choice for both models.

Choose the gateway SKU based on:

- Supported P2S protocols and authentication methods.
- Required number of concurrent P2S/S2S connections.
- Estimated throughput and traffic patterns.
- Requirements for BGP, active-active, and zone redundancy.
- Region availability, limits, and cost.

SKUs and features can change over time. Check the official **VPN Gateway SKU / feature support** table before finalizing. Do not assume all SKUs support Entra ID authentication, OpenVPN, IKEv2, BGP, or active-active equally.

### 5.4. On-Premises Connectivity Readiness

For S2S, the router or firewall at the office must support IPsec/IKE configuration parameters compatible with Azure. The network team needs the public IPs of both sides, network prefixes, pre-shared key, IKE/IPsec algorithms and parameters, and return routes to Azure.

If the on-premises device sits behind NAT, confirm the NAT traversal design, public endpoint, and ability to initiate sessions from both sides. Verify the Internet circuit and firewall rules for VPN control traffic, commonly involving UDP 500/4500 for IKE/IPsec NAT traversal, depending on the actual protocol and configuration.

### 5.5. P2S Identity and Devices

For P2S, select the authentication mechanism according to requirements:

- **Certificate authentication:** issue valid certificates and manage key lifecycles.
- **Microsoft Entra ID authentication:** identity sign-in experience over **OpenVPN** combined with the Azure VPN Client in supported configurations.
- **RADIUS authentication:** use a RADIUS server and an appropriately designed authentication flow.

Support depends on the protocol, SKU, operating system, and VPN client. You cannot arbitrarily pick an authentication method and expect it to work with every client type.

## 6. Creating a Shared Azure VPN Gateway

The steps below describe the workflow using the **Azure Portal**. Field names may vary slightly depending on the portal UI version.

1. Create a **Resource group** for the lab, such as **rg-vpn-lab**, in the chosen region.
2. Create a **VNet** with the address space **10.20.0.0/16**.
3. Create an application subnet **10.20.1.0/24** and the special subnet named **GatewaySubnet** with prefix **10.20.255.0/27**.
4. Create a **Public IP** that meets the requirements of the gateway SKU.
5. Go to **Create a virtual network gateway** and select:
   - **Gateway type:** VPN.
   - **VPN type:** Route-based.
   - **SKU:** a SKU that fully supports the planned P2S/S2S design.
   - **Virtual network:** the VNet just created.
   - **Public IP address:** the Public IP dedicated to the gateway.
6. Confirm the region, zone/active-active settings if applicable, and deploy.
7. Wait until the resource status shows the gateway has finished provisioning before configuring connections.

Provisioning a VPN Gateway can take significantly longer than creating a subnet or NSG. Do not assume an error simply because the operation does not complete immediately. In real environments, factor deployment duration into change plans and remember that the resource incurs cost even when the tunnel has no traffic yet.

**Important:** The VPN Gateway must reside in the VNet you want to connect to, using that VNet's own GatewaySubnet. Creating a regular Public IP or only enabling VPN settings inside a VM does not replace creating a virtual network gateway.

## 7. Setting Up Site-to-Site VPN

S2S connects two networks via an IPsec/IKE tunnel. On the Azure side, you need a VPN Gateway, a Local Network Gateway describing the on-premises site, and a Connection; on the office side, you need an operational VPN device.

### 7.1. Create the Local Network Gateway

Assume the on-premises site has:

- Public IP: **203.0.113.10** (sample only; replace with the real IP).
- LAN: **172.16.10.0/24**.
- A device supporting Azure-compatible IKE/IPsec.

In the Azure Portal, create a **Local network gateway**:

1. Choose the resource group and name, such as **lng-branch**.
2. Enter the public IP or FQDN if supported by the configuration in use.
3. Declare the address space **172.16.10.0/24** of the external network.
4. If the design uses BGP, provide the required BGP peer information.
5. Save and double-check the IP and prefixes.

The address prefixes on the Local Network Gateway are used to route to networks outside Azure when using static prefix routing. Incorrect declarations can result in the VPN reporting connected while traffic never reaches the intended destination network.

### 7.2. Create the Connection

In the Azure Portal:

1. Open the newly created VPN Gateway and go to **Connections**.
2. Add a new connection of type **Site-to-site (IPsec)**.
3. Select the corresponding **Virtual network gateway** and **Local network gateway**.
4. Set a **shared key (PSK)** of appropriate strength.
5. If using BGP or a custom IPsec/IKE policy, enter parameters matching both sides.
6. Create the connection and check its status.

**Do not place real PSKs into repositories, publicly shared documents, or command history.** Store and exchange secrets through your organization's secrets management mechanism; for example, you can use Azure Key Vault with appropriate access controls. Both endpoints must use the exact same PSK per the connection configuration.

### 7.3. Configure the Office VPN Device

On the site's router/firewall, the network team needs to configure the corresponding settings:

- Remote peer: public IP of the Azure VPN Gateway.
- Local peer: public IP/NAT endpoint of the site.
- Compatible IKE/IPsec parameters; specific choices depend on the device and Azure-supported configurations.
- PSK matching the connection in Azure.
- Local network: 172.16.10.0/24.
- Remote network: 10.20.0.0/16 or the specific designed prefixes.
- Routes and firewall rules for bidirectional traffic.

Depending on the device, an on-premises policy-based IPsec model may require specific traffic selectors or crypto ACLs even when the Azure Gateway is RouteBased. Interoperability between both sides must be verified rather than relying solely on UI labels on the device.

### 7.4. Verify S2S

After creating the tunnel:

1. Check the connection status in Azure and the IKE/IPsec SA state on the router.
2. From a machine in the office network, test connectivity to the private IP of an Azure workload on an allowed service port.
3. If traffic from Azure back to the office is needed, test the reverse direction as well.
4. Confirm that NSGs, firewalls, OS firewalls, and routes are not blocking traffic.
5. Test DNS if hostnames or internal domain names are used.
6. Record status and verification evidence from both ends of the tunnel.

**Connected does not guarantee the application is reachable.** It only indicates that the VPN connection may be established; routes, return paths, and security filters can still be misconfigured.

## 8. Setting Up Point-to-Site VPN

P2S allows individual client machines to establish VPN sessions into Azure. Azure VPN Gateway assigns each client an address from the **P2S address pool**. Clients use the appropriate connection profile and must pass the configured authentication mechanism.

### 8.1. General P2S Configuration

In the Azure Portal:

1. Open the provisioned virtual network gateway.
2. Select **Point-to-site configuration**.
3. Configure an **Address pool** that does not overlap with VNet prefixes, on-premises sites, or client networks, such as **172.20.10.0/24**.
4. Choose a **Tunnel type / protocol** supported by the SKU and clients.
5. Select the appropriate **Authentication type**.
6. Enter the certificate, Microsoft Entra ID, or RADIUS details depending on your choice.
7. Save the configuration and download the appropriate client profile/package.
8. Install/configure the VPN client on an authorized machine and test connecting.

The methods below are explained separately because their setup steps differ.

### 8.2. Certificate Authentication

Certificate-based authentication is typically used when you want to control devices or users through an organization-managed certificate infrastructure:

1. Prepare a suitable root certificate to be trusted on the Azure Gateway.
2. Upload the **public certificate data** of the root certificate to the P2S configuration in the required format; never upload the root CA private key to the Portal.
3. Issue a client certificate signed by a valid root for the device/user.
4. Install the client certificate along with its own private key into the appropriate operating system certificate store.
5. Download the VPN client configuration package and establish the connection.
6. Verify that you can connect, then test the certificate revocation workflow according to organizational procedures when a user or device is no longer valid.

**Do not distribute the root CA private key.** If the issuing key is compromised, the risk of client impersonation increases sharply. A simple lab can use test certificates; a production environment requires key management, lifecycle, and certificate revocation processes.

### 8.3. Microsoft Entra ID Authentication

For scenarios where users sign in with their organizational identity, Azure VPN Gateway can support **Microsoft Entra ID authentication over OpenVPN** combined with the **Azure VPN Client**, depending on the SKU, operating system, and current configuration requirements.

Workflow:

1. Confirm that the VPN Gateway/SKU, OpenVPN protocol, and client platform are supported.
2. Select Microsoft Entra ID as the P2S authentication method.
3. Configure tenant, audience, and issuer according to current Azure guidance for your organization's tenant; do not guess URIs or app IDs.
4. Configure appropriate identity controls, including Conditional Access if within supported scope and organizational policy.
5. Download the Azure VPN Client configuration from the Azure Portal and import the profile on the machine.
6. Connect and sign in with an authorized identity.
7. Verify that the machine receives a P2S address, has routes to the VNet, and successfully connects to permitted workloads.

This model is typically well suited for employees using Microsoft Entra ID accounts, but do not assume that signing in with Entra ID automatically grants access to every application in the VNet. Network-layer and application-layer permissions still need to be configured separately.

### 8.4. RADIUS Authentication

If the organization has a RADIUS infrastructure, Azure VPN Gateway can be configured to forward authentication requests to a RADIUS server using supported protocols and connection types. You must ensure network connectivity from the gateway to the RADIUS server, configure the RADIUS shared secret, and ensure availability/redundancy of the authentication system.

RADIUS can integrate with an enterprise's internal authentication system; however, do not choose it solely because RADIUS already exists. Evaluate client support, VPN protocol compatibility, high availability, and security requirements.

## 9. Distributing VPN Client Profiles and Device Control

After configuring P2S, the **VPN client configuration** provides connection details such as the gateway endpoint, tunnel settings, and routes depending on the authentication method. Download and import steps may differ between the Azure VPN Client and built-in operating system clients.

Before putting it into use:

- Only distribute configurations to authorized devices or users.
- Never send private keys and passwords over insecure channels.
- Verify client version compatibility with the authentication method.
- Update the client configuration if VNet prefixes, peered networks, addresses, or gateway settings change in ways that require re-downloading the profile for that client type.
- Set up internal DNS or an appropriate name resolution mechanism if workloads use private endpoints or private DNS.
- Instruct users to disconnect the VPN when finished working and report lost devices promptly.

Do not treat the **Connected** indicator on the VPN client as the final test result. The client must receive an IP, have the proper routes, and be able to reach the intended target application.

## 10. Bidirectional Routing and Why VPN Connects Without Passing Traffic

An established VPN tunnel only solves the **encrypted path** part. Data packets still must be routed to the destination, and reply packets must find a path back.

### 10.1. S2S Path

For example, an office machine **172.16.10.25** wants to connect to Azure VM **10.20.1.10**:

1. The office machine sends the packet to the LAN's internal gateway.
2. The site router sees that **10.20.0.0/16** belongs to the network on the other side of the S2S link and sends it through the IPsec tunnel.
3. Azure VPN Gateway delivers the traffic into the VNet.
4. The NSG, firewall, and VM operating system allow or deny the service port.
5. The VM sends the reply packet to **172.16.10.25**; Azure must have a route back to the site via the VPN Gateway.

If the return path is missing, access can fail even if outbound packets reach the VM. Similarly, if the site device lacks a route to the VNet, the tunnel can still show Connected without carrying useful traffic.

### 10.2. P2S Path

For example, a laptop receives address **172.20.10.5** from the P2S pool:

1. The VPN client adds the routes matching the configuration it received.
2. Traffic destined for private IPs in the VNet is sent through the tunnel.
3. Azure VPN Gateway delivers the traffic to the target subnet.
4. The workload replies to the client address along the system's routing path.

**Split tunneling** typically sends only traffic destined for advertised prefixes through the VPN; regular Internet traffic continues using the client's local Internet connection. **Forced tunneling** or custom routes require separate configuration and depend on the VPN protocol and client. Do not assume every P2S profile pushes all Internet traffic into Azure.

### 10.3. DNS Is a Separate Step

An application may be reachable by IP **10.20.1.10** yet fail when called via **api.internal.example** because the client is not using the right DNS server or cannot resolve the private DNS zone.

You need to design DNS for both P2S and S2S—for example, Azure DNS Private Resolver, a DNS server in Azure, or an authorized on-premises DNS system. DNS configuration does not happen automatically just because a tunnel exists.

### 10.4. NSGs, Firewalls, and Routes

Only open the necessary flows:

- The NSG on the target subnet/VM allows the P2S pool or corresponding on-premises LAN source.
- Azure Firewall/NVA (if used) has appropriate rules and routes.
- The VM's host firewall allows the application port.
- The on-premises router/firewall permits both outbound and return traffic.
- UDRs do not accidentally steer reply traffic to an inappropriate next hop.

If you only use ICMP ping, remember that some operating systems and firewalls block ICMP by default. Test using the **actual TCP/UDP port that the application uses**, combined with route and log checks.

## 11. BGP and Static Routing on S2S

For a small branch office, listing prefixes manually on the Local Network Gateway may be sufficient. When there are multiple sites, many network ranges, or frequent route changes, an enterprise can consider **Border Gateway Protocol (BGP)**.

**Static routing:**

- On-premises network prefixes are declared manually.
- Easy to understand for small topologies.
- Requires configuration updates whenever site networks change.

**BGP:**

- Azure VPN Gateway and the on-premises device can exchange dynamic routing information if both the gateway SKU and the device support it.
- Requires configuring ASNs, BGP peer addresses, and compatible connection parameters.
- Helps manage prefix changes and certain multi-site or failover scenarios.
- Does not replace designing to avoid overlapping prefixes or security controls.

For example, if the office adds network **172.16.20.0/24**, static configuration requires updating the relevant prefixes; BGP can advertise the route as designed. However, misconfigured or overly broad BGP advertisements can also cause widespread outages. Inspecting learned routes and restricting advertisements are essential operational practices.

## 12. Combining P2S, S2S, and VNet Peering

An organization may use a central VNet (hub) containing the Azure VPN Gateway, while other application VNets act as spokes. In that case, note:

- P2S and S2S can enter the same hub gateway only when the SKU and protocols support simultaneous configuration.
- **VNet peering** does not automatically forward all traffic across spokes or to on-premises networks.
- Some designs use **gateway transit** over peering; you must configure the options properly on both sides and verify requirements for using a remote gateway.
- If P2S clients also need to reach on-premises via S2S, verify routes to on-premises networks, return paths to the **P2S address pool**, gateway support, and on-premises firewall rules.
- Changes to peered networks or prefixes may require updating/re-syncing P2S profiles so clients receive the new routes.

Do not describe hub-spoke or P2S-to-S2S transit as automatic behavior. It is a network design governed by routing, peering, gateway, and service support conditions.

## 13. Initial S2S Configuration with Azure CLI

Azure CLI helps deploy infrastructure in a repeatable way. The example below uses **bash** and the prefixes from this lesson; run it only in an authorized test environment. Values such as the office public IP, PSK, and SKU must be replaced with approved values.

### 13.1. Create Resource Group, VNet, and GatewaySubnet

~~~bash
az login
az account set --subscription "<subscription-id>"

az group create \
  --name rg-vpn-lab \
  --location southeastasia

az network vnet create \
  --resource-group rg-vpn-lab \
  --name vnet-vpn-lab \
  --location southeastasia \
  --address-prefixes 10.20.0.0/16 \
  --subnet-name snet-app \
  --subnet-prefixes 10.20.1.0/24

az network vnet subnet create \
  --resource-group rg-vpn-lab \
  --vnet-name vnet-vpn-lab \
  --name GatewaySubnet \
  --address-prefixes 10.20.255.0/27
~~~

### 13.2. Create Public IP and VPN Gateway

~~~bash
az network public-ip create \
  --resource-group rg-vpn-lab \
  --name pip-vpn-gateway \
  --location southeastasia \
  --sku Standard \
  --allocation-method Static

az network vnet-gateway create \
  --resource-group rg-vpn-lab \
  --name vng-vpn-lab \
  --location southeastasia \
  --public-ip-addresses pip-vpn-gateway \
  --vnet vnet-vpn-lab \
  --gateway-type Vpn \
  --vpn-type RouteBased \
  --sku VpnGw1
~~~

**VpnGw1** is an illustrative SKU; availability, SKU generation, and suitability for P2S/S2S or required features must be verified before running. If zone-redundant or active-active is needed, resource/Public IP design and parameters may differ from this example.

### 13.3. Declare the On-Premises Site

~~~bash
az network local-gateway create \
  --resource-group rg-vpn-lab \
  --name lng-branch \
  --location southeastasia \
  --gateway-ip-address 203.0.113.10 \
  --local-address-prefixes 172.16.10.0/24
~~~

**You cannot use 203.0.113.10 as a real VPN peer**: it is an example IP. Only after replacing it with a real site endpoint, configuring the router, and setting the shared key can a working S2S tunnel be established.

### 13.4. Create the Connection and Check Status

The following commands illustrate the basic parameters. In production, do not pass secret PSKs directly on the command line because they can be recorded in shell history or logs; use an organization-approved secrets management solution and deployment process.

~~~bash
az network vpn-connection create \
  --resource-group rg-vpn-lab \
  --name conn-branch \
  --location southeastasia \
  --vnet-gateway1 vng-vpn-lab \
  --local-gateway2 lng-branch \
  --shared-key "<lab-only-shared-key>"

az network vpn-connection show \
  --resource-group rg-vpn-lab \
  --name conn-branch \
  --query "{name:name,status:connectionStatus}" \
  --output json
~~~

This scenario uses static prefixes and does not configure BGP. If BGP or a custom IPsec/IKE policy is needed, apply parameters appropriate for your CLI version and actual VPN device.

Never put commands that delete an entire resource group into production pipelines; after the lab, only clean up test resources that have been inventoried and approved for deletion.

## 14. Securing VPN Gateway in Operations

Even though VPN traffic is encrypted, overall system security still depends on multiple layers:

**Authentication:**

- P2S should use an appropriate authentication method, enforcing MFA/Conditional Access where supported.
- Certificates must be issued, stored, and revoked according to procedure.
- S2S PSKs must be sufficiently strong, managed as secrets, and rotated in a controlled manner.

**Network segmentation:**

- Do not grant broader access than the services users or sites actually need.
- Use NSGs, Azure Firewall, host firewalls, and application rules to restrict sources and ports.
- Separate test and production environments when risk profiles differ.

**Azure governance:**

- Use Azure RBAC to restrict who can modify gateways, connections, VPN client authentication, and resource groups.
- Protect administrative accounts with Microsoft Entra ID, MFA, and time-bound privileged access such as PIM where appropriate.
- Record changes to gateways, tunnels, and network configurations using Azure Activity Log, diagnostic logs, and change management processes.

**Device operations:**

- Check firmware patches and IKE/IPsec configurations on on-premises firewalls.
- Protect private keys and client configurations; revoke access for lost devices.
- Do not treat VPN as a substitute for authorization in applications and data services.

## 15. High Availability and Disaster Recovery

### 15.1. Gateway Redundancy Within a Region

Azure VPN Gateway is a managed service and provides redundancy depending on the SKU and configuration. Some models support **active-active**, where gateway instances each have their own public IP and the on-premises site establishes multiple tunnels to improve connection resilience.

For active-active to actually deliver its benefits, the on-premises device must support and be configured for the corresponding tunnels. Simply creating an additional public IP without configuring the other side will not provide a complete redundant path.

Some gateway SKUs and regions support availability zone-redundant deployments. This capability depends on the SKU type and Public IP/GatewaySubnet design; check product documentation before choosing.

### 15.2. Internet Circuits and On-Premises Devices

If a branch office has only one Internet connection and one firewall, the site still has a single point of failure even if Azure runs multiple VPN instances. To increase end-to-end availability, dual Internet links, redundant VPN devices, or multiple tunnels/routes may be required in a supported design.

### 15.3. Region-Wide Outages

Intra-region redundancy does not guarantee availability if an entire region experiences an outage. Critical systems may require a VNet and gateway in a secondary region, redundant data and applications, and tested traffic failover procedures. This design increases cost and complexity.

Clearly define **RTO** (Recovery Time Objective) and **RPO** (Recovery Point Objective) for the entire application. VPN is only one component of a DR plan; a connectivity tunnel does not replicate databases or start standby services on its own.

## 16. Monitoring, Diagnostics, and Alerting

Signals to monitor:

| Data Group | What to Check |
|---|---|
| Connection status | Whether the S2S tunnel is Connected or Disconnected; change history |
| Gateway and tunnel metrics | Ingress/egress traffic, status, and connection metrics provided by the SKU |
| Diagnostic logs | IKE/IPsec negotiation details, tunnel, route, or gateway events by supported category |
| Azure Activity Log | Who modified the gateway, connection, public IP, or related resources |
| BGP routes/status | Learned/advertised prefixes and BGP session state if used |
| Client/endpoint logs | P2S client authentication, profile import, DNS, or route errors |
| On-premises device | IKE SA, IPsec SA, packet counters, routes, and firewall drops |

Azure Monitor can collect metrics and diagnostic logs as configured. Some log types require creating **diagnostic settings** to send data to a Log Analytics workspace, Storage account, or appropriate destination. Log/metric categories may vary by gateway and service version.

Useful alerts include: tunnel disconnected beyond a threshold, abnormal traffic drops, spikes in failed authentications, or gateway configuration changes outside maintenance windows. Tune thresholds to your operational model and avoid assuming every P2S client disconnect is a critical incident.

## 17. S2S Troubleshooting Guide

### 17.1. Tunnel Is Not Connected

Check in order:

1. Has the Azure VPN Gateway reached Provisioning Succeeded?
2. Are the public IPs of the Azure gateway and on-premises site correct?
3. Do the Internet circuit and firewall allow IKE/IPsec traffic as designed?
4. Do both sides use the same PSK and compatible IKE/IPsec settings?
5. Is the on-premises device using the right route mode/traffic selector or peer config?
6. Are there negotiation errors in VPN Gateway diagnostic logs or on-premises device logs?

If the two sides have mismatched PSKs or IKE parameters, traffic never enters the tunnel. Changing a workload's NSG will not fix a tunnel establishment failure.

### 17.2. Tunnel Connected but Application Is Unreachable

Check:

- Does the Local Network Gateway declare the correct on-premises prefixes?
- Does the on-premises router have a route to the VNet prefixes?
- Does the VNet/subnet have a return route to on-premises?
- Is there an overlapping prefix or a more preferred route taking another path?
- Do NSGs, intermediate firewalls, and host firewalls allow the application port?
- Does DNS resolve the service name to the right private IP?
- Is there incompatible NAT or traffic selector behavior?
- When using BGP, are routes actually being advertised and learned properly?

Distinguish between testing **by IP** and **by DNS name**. A failed ICMP test alone does not prove the network path is broken because ping may be intentionally blocked.

### 17.3. Tunnel Is Unstable or Slow

Inspect gateway throughput relative to the SKU, Internet link quality, MTU/MSS, packet loss, latency, IKE SA rekeying/changes, and firewall limits. Compare results from both ends over the same time window before concluding the bottleneck is inside Azure.

## 18. P2S Troubleshooting Guide

**Cannot connect VPN:** check the profile, endpoint, VPN client version, protocol, certificate or Entra ID/RADIUS authentication, user permissions, and whether the local network blocks the protocol.

**Client reports authentication failed:** verify the certificate is still valid and has a matching private key; or check tenant/audience/issuer and Microsoft Entra ID conditions if used. For RADIUS, verify the server, shared secret, acceptance policies, and network connectivity.

**Connected but no route to VNet:** check the P2S address pool, routing table on the machine, routes advertised by the profile, IP address overlaps, and whether the profile was re-downloaded after VNet configuration changes.

**Reachable by IP but not by name:** check the DNS servers assigned to the client and network reachability to the DNS server or private resolver.

**Cannot reach office systems over S2S:** check whether this is a supported transit scenario, including both the P2S → on-premises path and the return path to the P2S pool, plus on-premises firewalls and routes.

**Only some users experience failures:** compare client versions, authentication policies, certificate status, local LAN addressing where they connect from, and per-device routing tables.

A quick investigation table:

| Symptom | Check First | Useful Evidence |
|---|---|---|
| Authentication failed | Identity, certificate, Entra ID/RADIUS | VPN client logs, authentication events |
| No P2S IP received | Gateway P2S config, client profile | Pool configuration, client status |
| Cannot reach VM | Routes, NSG/firewall, target IP | Route table, flow logs/host logs, TCP test |
| Only name resolution fails | Internal DNS and client DNS | `nslookup`/`dig` against specific DNS server |
| Intermittent disconnects | Client network, gateway, and protocol | Timestamps, gateway metrics, client logs |

## 19. Understanding Costs and Technical Limits

A VPN Gateway is not free simply because no users are currently connected. Billing may include:

- Gateway provisioning/running charges based on SKU and usage duration.
- Data transfer according to applicable VPN and Azure pricing structures.
- Related resources such as Public IPs, Log Analytics, and log storage.
- Router/firewall infrastructure, Internet links, and site operations.
- Additional gateways and redundant connections if scaling across multiple regions or active-active.

SKU selection should be based on concurrent P2S users, number of S2S tunnels, expected traffic, protocols, and redundancy requirements. Published SKU throughput figures are reference metrics; actual performance is also affected by protocol, packet size, Internet quality, and on-premises hardware.

Before running labs, set budget alerts in Azure Cost Management and know how to clean up lab resources. Only clean up resources approved for deletion; deleting a VPN Gateway or GatewaySubnet in an active environment can disrupt connectivity for many applications.

## 20. Integrated Hands-On Lab

**Scenario:** the operations team needs to allow a laptop to connect to a VM using a private IP while also creating a test S2S connection to a compatible firewall in the lab.

**Prerequisites:** an Azure subscription permitted to create a VPN Gateway, approved cost budget, a VNet without conflicting gateways, an on-premises VPN device with a real public endpoint, and configuration access on both sides.

### Part A — Design

1. Draw a topology including the P2S laptop, Azure VPN Gateway, lab network, and private VM.
2. Choose non-overlapping prefixes. Use the addressing table in Section 4 as a template.
3. Choose a RouteBased SKU capable of supporting the planned P2S authentication method and S2S connection.
4. Identify the permitted application ports and required NSG/firewall rules.

### Part B — S2S Deployment

1. Create the VNet, GatewaySubnet, and VPN Gateway.
2. Declare the Local Network Gateway with the site's real endpoint IP and real LAN prefix.
3. Create the VPN connection and store the PSK securely.
4. Configure the site router/firewall with supported IPsec/IKE settings.
5. Verify the tunnel is Connected.
6. Use an allowed TCP connection to verify outbound and return packets between the site and the Azure VM.

### Part C — P2S Deployment

1. Set a P2S client pool that does not overlap other networks.
2. Choose certificate or Entra ID according to SKU/client support and lab policy.
3. Configure authentication, download, and import the profile.
4. Connect from the laptop and inspect the assigned address.
5. Inspect routes and test connecting to the VM via its private IP.
6. Test an internal DNS name; if it fails, add the proper DNS configuration and retest.

### Part D — Verification and Cleanup

1. Save two outputs: the S2S tunnel status and the P2S client status.
2. Record route, DNS, port check results, and relevant logs.
3. Turn off or disconnect the test P2S session.
4. Clean up test resources that are no longer needed and monitor Cost Management.
5. Write a short report explaining why P2S and S2S use different termination endpoints and authentication mechanisms.

**If you do not yet have an on-premises VPN device**, you can still practice P2S or complete the S2S design and document the required router configuration. Do not simulate an S2S Connected state without an actual site and compatible device.

## 21. Common Mistakes

- **Using overlapping network prefixes:** overlapping VNet, LAN, or P2S pools cause hard-to-diagnose routing failures.
- **Not naming GatewaySubnet accurately:** Azure VPN Gateway requires a dedicated subnet with that exact name.
- **Choosing a SKU solely by price while ignoring protocols:** certain P2S methods or HA/BGP features are only available on appropriate configurations/SKUs.
- **Mistaking Local Network Gateway for an Azure-deployed VPN endpoint:** LNG only describes the partner site.
- **Configuring only the Azure side in S2S:** the office device must have matching settings and proper routes.
- **Selecting a P2S protocol mismatched with the client:** certificate, Entra ID, RADIUS authentication, and clients must align.
- **Assuming Connected means application connectivity works:** you must still check NSGs, firewalls, DNS, and return paths.
- **Failing to update profiles after network changes:** P2S clients may continue using stale routes or settings.
- **Neglecting PSKs and certificates:** leaked or expired credentials increase risk or break connectivity.
- **Overlooking gateway costs:** resources can incur charges even before any traffic flows.
- **Evaluating HA only on the Azure side:** the site's Internet link and router can also be single points of failure.

## 22. Self-Check Questions

1. Why is P2S suitable for a remote engineer, whereas S2S is better suited to connecting an entire office network?
2. How does GatewaySubnet differ from an application subnet?
3. What information does a Local Network Gateway hold, and is it an actual VPN appliance?
4. If Azure and the office use the same 10.20.0.0/16 range, what problem must you resolve before creating the tunnel?
5. An S2S connection shows Connected, but a VM does not respond to TCP requests. In what order would you check routes, NSGs, and firewalls?
6. Why might a P2S client reach a VM by IP yet fail via a private DNS name?
7. Can Microsoft Entra ID authentication for P2S be used arbitrarily with every protocol and client?
8. When scaling from one branch office to multiple branches, what problems can BGP and HA models help address?
9. Why does a gateway in Azure still fail to guarantee availability if the site has only one router and one Internet link?
10. When using the same VPN Gateway for both P2S and S2S, how do you verify whether a P2S laptop can reach the on-premises network over S2S?

## 23. Takeaways

**Point-to-Site** creates tunnels from individual user devices into an Azure VNet; **Site-to-Site** connects an on-premises network to Azure via a VPN device and IPsec/IKE. Both rely on choosing the right Azure VPN Gateway, designing non-overlapping IP ranges, and configuring bidirectional routing.

For P2S, focus on authentication method, protocol/client compatibility, address pool, profile distribution, and DNS. For S2S, focus on the Local Network Gateway, public endpoint, PSK/IKE parameters, on-premises prefixes, and the partner router/firewall. In operations, monitor connections, logs, routes, access controls, and costs; if a VPN reports Connected but the application does not work, inspect the full forward and return paths before making random configuration changes.
