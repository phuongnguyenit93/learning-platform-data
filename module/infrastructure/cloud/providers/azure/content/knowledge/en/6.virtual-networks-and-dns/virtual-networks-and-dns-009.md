# Private DNS Zones and VNet Links

> **Chapter:** Virtual Networks and Name Resolution  
> **Module:** `CLOUD_PROVIDERS_AZURE` — Explore the Microsoft Azure ecosystem from subscriptions, resource groups, and Entra ID to virtual networks, compute services, storage, and data. Learn how to deploy, monitor, secure, and control costs for an application architecture on Azure.

## Lesson Objectives

After this lesson, you will be able to:

1. Explain what an **Azure Private DNS Zone** is and why it is used for internal name resolution inside an Azure Virtual Network (VNet).
2. Distinguish between DNS records, **virtual network links**, **resolution links**, and **registration links**.
3. Describe how machines inside a VNet resolve names, how zones relate to multiple VNets, and the limitations of VNet peering with respect to DNS.
4. Create a private zone, link it to a VNet, add an `A` record, and verify it using Azure CLI.
5. Understand how Private DNS Zones integrate with **Private Endpoints** and **Azure DNS Private Resolver** in hybrid topologies.
6. Troubleshoot common issues and govern permissions, record lifecycles, and costs.

## 1. The Problem: Internal Applications Need Stable Domain Names

Suppose a company operates an order-processing system on Azure:

- A VM or server runs an API at private address `10.20.1.4`.
- An application inside VNet `vnet-app-dev` calls this API.
- Dev and Prod environments have different IP addresses.
- The operations team does not want IP addresses hardcoded into source code.

The application should call an intuitive name such as:

~~~text
api.corp.example.com
~~~

Inside the Dev VNet, querying that name should return:

~~~text
api.corp.example.com  →  10.20.1.4
~~~

In another environment, the same service might use a distinct name like `api.prod.corp.example.com` or a separate private zone depending on the architecture. When the IP changes, operations updates the DNS record; the application does not need configuration edits everywhere.

**Azure Private DNS Zone** is a managed service that hosts and serves DNS records within configured private network scopes. Because private zones are managed by Azure, you do not have to run high-availability DNS servers yourself just to serve internal names.

Problems Private DNS Zones help solve:

- Name resolution for workloads across one or more VNets.
- Decoupling logical service names from private IP addresses.
- Automatic record registration for eligible virtual machines when registration is enabled.
- Private name resolution for services accessed via **Azure Private Endpoints**.
- Multi-network, multi-subscription, or hybrid internal DNS architectures when paired with appropriate DNS forwarding components.

**Important note:** DNS only translates names into addresses. Resolving `10.20.1.4` does not guarantee access if network routing, NSGs, firewalls, or application permissions are missing.

## 2. What Is a Private DNS Zone?

A **DNS zone** is a namespace containing DNS records under a specific suffix. For example, the `corp.example.com` zone may contain:

| Record name | Type | Value | Fully Qualified Domain Name (FQDN) |
| --- | --- | --- | --- |
| `api` | A | `10.20.1.4` | `api.corp.example.com` |
| `db` | A | `10.20.2.8` | `db.corp.example.com` |
| `files` | CNAME | `api.corp.example.com` | `files.corp.example.com` |
| `@` | Service-managed SOA/NS | Zone metadata | `corp.example.com` |

**FQDN** (*Fully Qualified Domain Name*) is the complete domain name, such as `api.corp.example.com`.

Key concepts to distinguish:

- **Private DNS Zone:** an Azure resource of type `Microsoft.Network/privateDnsZones` managing a set of private DNS records.
- **DNS record set:** a group of records sharing the same name and type, such as the `A` record for `api`. A record set can contain multiple IPs.
- **Virtual network link:** a resource linking a zone to a VNet so that VNet can resolve names in the zone; auto-registration can be enabled or disabled.
- **Azure-provided DNS:** the DNS service provided by Azure to workloads in a VNet when the network uses Azure's default DNS settings.
- **Custom DNS:** organization-managed DNS servers or other DNS services; may require conditional forwarding to resolve Azure private zones.

### How Do Private DNS and Public DNS Differ?

| Criterion | Public DNS Zone | Private DNS Zone |
| --- | --- | --- |
| Scope | Names served across public DNS infrastructure per delegation/config | Names resolved within networks with an appropriate private DNS path |
| Uses VNet links? | Not the primary mechanism | Yes, so Azure-provided DNS resolves the zone inside a VNet |
| Use cases | Public websites, email MX records | Internal services, Private Endpoints |
| Record addresses | Public IPs or other record types | Typically private IPs, though record types are not restricted solely to private IPs |
| Governance | Depends on public DNS delegation | Managed inside Azure and linked to VNets |

Zone `corp.example.com` can serve as an internal namespace; this illustrative name does not imply you own the public domain `example.com`. In real enterprise designs, use a **subdomain controlled by your organization** (e.g., `internal.company.example`) and plan to avoid collisions with public DNS.

A Private DNS Zone is created as a resource inside a resource group/subscription, but **does not sit “inside” a subnet or VNet**. For a VNet to use the zone via Azure-provided DNS, you must create a **virtual network link**.

## 3. Relationship Between Zones, VNets, and Records

Suppose a company has two VNets that both need to resolve internal names:

~~~mermaid
flowchart TD
    Z["Private DNS Zone\ncorp.example.com"]
    R["A: api → 10.20.1.4\nA: db → 10.20.2.8"]
    L1["VNet link dev\nregistrationEnabled: false"]
    L2["VNet link ops\nregistrationEnabled: false"]
    V1["VNet: vnet-app-dev"]
    V2["VNet: vnet-ops"]
    C1["Dev VM / app"]
    C2["Ops VM / app"]
    Z --> R
    Z --> L1 --> V1 --> C1
    Z --> L2 --> V2 --> C2
~~~

Both VNets can resolve `api.corp.example.com` to `10.20.1.4` **if clients use the proper DNS path**. However, actual connectivity from the Ops VNet to the Dev server still depends on whether the networks are connected and permit the traffic.

Three relationships to remember:

1. **Zone → record set:** the zone holds the names and values to be resolved.
2. **Zone → VNet link:** linked VNets gain resolution scope for the zone when using Azure-provided DNS.
3. **VNet → network path:** peering, routing, VPN/ExpressRoute, NSGs, or firewalls determine whether the client can actually connect to the returned IP.

One private zone can be linked to multiple VNets within current service conditions and limits. One VNet can also link to multiple differently named private zones as needed by the design.

### Linking Is Not the Same as VNet Peering

**VNet peering** connects VNets so endpoints can exchange data according to routing and policies. A **Private DNS virtual network link** enables resolving zone names inside a VNet.

The two mechanisms are independent:

- Peering **does not automatically propagate private zone resolution rights** to the peered VNet.
- A DNS link **does not create network routes or access permissions** between two VNets.
- For VNet A and B to both resolve a zone via Azure-provided DNS, you typically create links from **both A and B** to the zone (or design centralized DNS forwarding instead).
- Reaching the target IP still requires actual network connectivity.

For example, after linking both VNets, `nslookup api.corp.example.com` on a VM in the Ops VNet may return `10.20.1.4`, while `curl` to the API still times out because routing is missing or a firewall blocks it.

## 4. Resolution Links vs. Registration Links

When linking a zone to a VNet, a key property is `registrationEnabled`.

| Property | Resolution Link | Registration Link |
| --- | --- | --- |
| `registrationEnabled` | `false` | `true` |
| Resolves zone records | Yes | Yes |
| Automatically creates/updates eligible VM A records in the VNet | No | Yes, within supported feature scope |
| Best suited for | Service-consumer VNets, management networks, VNets with Private Endpoints | VNets with VMs needing automatic hostname registration |
| Private zones for Private Endpoints | Standard | Do not use VM auto-registration for Private Endpoints |

### Resolution Link: Name Resolution Only

With `registrationEnabled: false`, clients in the VNet can query Azure DNS for records in the zone, while Azure **does not automatically register hostnames of VMs in that VNet** into the zone.

Use cases:

- Multiple application VNets needing to reach an internal API.
- A VNet hosting operations VMs needing to resolve server names in another VNet.
- Connecting a Private Endpoint zone to VNets where client applications execute queries.

### Registration Link: Registering VM Names

With `registrationEnabled: true`, Azure automatically manages **`A` records for Azure VMs in the linked VNet**, including updating/deleting records across supported VM lifecycle events. A registration link also provides name resolution just like a resolution link.

This helps when VMs are frequently created or deleted. However:

- **It does not apply to all Azure resources.** Creating App Service, Azure SQL Database, or Private Endpoints does not trigger VM registration.
- Do not use VM auto-registration as a substitute for **Private DNS zone groups** on Private Endpoints.
- Link limits, name collisions, and hostname behaviors must be checked against your design and current product documentation.
- Do not assume VMs will receive application-friendly names if hostnames and DNS naming conventions are not designed.

**Selection rule:** If a VNet only needs to **read** records in a zone, use a resolution link. Enable auto-registration only when genuinely needed and when you understand how VMs are registered.

## 5. Name Resolution Flow from a Machine in a VNet

Suppose:

- Zone: `corp.example.com`.
- Record: `api.corp.example.com A 10.20.1.4`.
- VNet: `vnet-app-dev` is linked to the zone.
- The VM uses Azure's default DNS settings.

High-level flow:

~~~mermaid
sequenceDiagram
    participant App as App in VNet
    participant DNS as Azure-provided DNS
    participant Zone as Private DNS Zone
    participant API as API 10.20.1.4
    App->>DNS: Lookup api.corp.example.com
    DNS->>Zone: Search record in linked zone
    Zone-->>DNS: A = 10.20.1.4
    DNS-->>App: Return private IP
    App->>API: Connect to 10.20.1.4
    Note over App,API: Connection succeeds only if network and security permit
~~~

In a VNet using default Azure DNS, Azure-provided DNS resolves records belonging to linked private zones. Azure's platform DNS service address is documented as `168.63.129.16`; this is a special platform virtual IP, **not a public DNS server for arbitrary Internet devices to query**.

### What If a Machine Uses Custom DNS?

A VNet can be configured with custom DNS servers, such as an Active Directory domain controller or enterprise DNS service. In that case:

- Clients normally send queries to the **custom DNS**, rather than directly to Azure-provided DNS.
- The custom DNS must know how to resolve internal zones; a standard pattern is **conditional forwarding** of relevant suffixes through a DNS forwarder in Azure or **Azure DNS Private Resolver**.
- When running a DNS forwarder on an Azure VM, forwarding to Azure DNS (`168.63.129.16`) requires a **VNet context linked to the private zone**.
- On-premises DNS servers should not be designed to forward directly to `168.63.129.16`. Instead, forward to a Private Resolver inbound endpoint or a forwarder reachable over configured private connectivity.

**Diagnostic clue:** A VNet is linked to the zone yet `nslookup` still returns `NXDOMAIN` or public records. Check which DNS server the client actually uses before modifying the zone.

### DNS Caching and TTL

DNS resolvers and applications cache answers until their **TTL** (*Time To Live*) expires. After updating a record, clients may not all observe the new IP simultaneously.

Choose TTL values based on how often IPs change and stability needs; never assume updating a record means every client sees the new IP instantaneously.

## 6. Hands-On: Creating a Private DNS Zone and VNet Link with Azure CLI

The example below uses hypothetical names and internal IP ranges. Creating zones/records/links **modifies resources and may incur charges**; run only in an authorized lab subscription. Commands assume `vnet-app-dev` already exists in resource group `rg-app-dev` and you hold permissions on both the zone and VNet.

### 6.1. Prepare Subscription and Network Identifier

Before making changes, confirm the active subscription:

~~~bash
az login
az account show \
  --query "{subscription:name, subscriptionId:id, tenantId:tenantId}" \
  --output json

# Select the assigned subscription if needed.
az account set --subscription "<SUBSCRIPTION_ID>"

# Retrieve resource ID to link the exact VNet, even if the zone is in another resource group.
VNET_ID=$(az network vnet show \
  --resource-group rg-app-dev \
  --name vnet-app-dev \
  --query id \
  --output tsv)

echo "$VNET_ID"
~~~

The output should look like:

~~~text
/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-app-dev/providers/Microsoft.Network/virtualNetworks/vnet-app-dev
~~~

If the VNet ID fails to resolve, check the name, subscription, and VNet read permissions; never guess a Resource ID.

### 6.2. Create the Zone

Inside an existing DNS resource group, such as `rg-dns-lab`:

~~~bash
az network private-dns zone create \
  --resource-group rg-dns-lab \
  --name corp.example.com

az network private-dns zone show \
  --resource-group rg-dns-lab \
  --name corp.example.com \
  --output json
~~~

Creating a zone **does not automatically make it active for any VNet**. The next step is creating a link.

### 6.3. Create a Resolution Link

~~~bash
az network private-dns link vnet create \
  --resource-group rg-dns-lab \
  --zone-name corp.example.com \
  --name link-vnet-app-dev \
  --virtual-network "$VNET_ID" \
  --registration-enabled false
~~~

Verify the link:

~~~bash
az network private-dns link vnet list \
  --resource-group rg-dns-lab \
  --zone-name corp.example.com \
  --output table
~~~

Inspect link name, provisioning state, linked VNet, and registration mode. To attach another VNet, create a second link pointing to its VNet ID with a unique link name within the zone. Links can span resource groups or subscriptions when permissions and policies allow; the zone does not have to sit in the same resource group as the VNet.

### 6.4. Create an A Record for an Internal API

~~~bash
# Create record set with a 300-second TTL.
az network private-dns record-set a create \
  --resource-group rg-dns-lab \
  --zone-name corp.example.com \
  --name api \
  --ttl 300

# Add the API's private IPv4 address.
az network private-dns record-set a add-record \
  --resource-group rg-dns-lab \
  --zone-name corp.example.com \
  --record-set-name api \
  --ipv4-address 10.20.1.4

# Inspect the newly created record.
az network private-dns record-set a show \
  --resource-group rg-dns-lab \
  --zone-name corp.example.com \
  --name api \
  --output json
~~~

In zone `corp.example.com`, record set `api` produces the FQDN:

~~~text
api.corp.example.com  A  10.20.1.4
~~~

IP `10.20.1.4` is illustrative only; a real record must point to an existing, properly routed endpoint.

### 6.5. Verify Inside the VNet

Sign in to an authorized VM inside `vnet-app-dev` using Azure-provided DNS, then run:

~~~bash
# Available tools depend on the operating system.
nslookup api.corp.example.com

# On Linux, if dig is installed:
dig api.corp.example.com A +short
~~~

Expected output:

~~~text
10.20.1.4
~~~

`az network private-dns record-set a show` confirms **the record exists**. Running `nslookup` from a VM inside the VNet confirms **the client's resolution path** actually works. Those are two separate checks.

If the VM uses custom DNS, this check succeeds only after the custom DNS is configured with proper forwarding as described in Section 5.

### 6.6. When to Use a Registration Link

For a dedicated VM VNet where you want automatic hostname registration, create the link with `--registration-enabled true` instead of `false`:

~~~bash
# VNET_VM_ID must be the resource ID of the VM VNet;
# do not run with an unverified VNet name.
az network private-dns link vnet create \
  --resource-group rg-dns-lab \
  --zone-name corp.example.com \
  --name link-vnet-vm-registration \
  --virtual-network "$VNET_VM_ID" \
  --registration-enabled true
~~~

This is an **optional alternative for an eligible VM VNet**, not a mandatory requirement of the lab. Before running, set `VNET_VM_ID` to the VNet that actually needs auto-registration and check existing links to avoid conflicting configurations.

### 6.7. Clean Up Lab Resources

When finished and after verifying resources belong solely to the lab, delete the zone's links first, then remove lab-created record sets and the zone (if unused by other workloads). You can use the Azure portal or matching management commands. **Never delete a private zone actively serving VNets or Private Endpoints**, as losing name resolution can cause application outages.

## 7. Private DNS Zones and Private Endpoints

Applications frequently need to connect to **Azure Storage, Azure SQL, Key Vault**, or other PaaS services over private IPs. With **Azure Private Endpoint**, service access is brought into the VNet via a network interface with a private IP.

In this case, DNS is critical: the application still calls the familiar service hostname, which must resolve to the **private endpoint's IP** from where the application runs.

### Example: Azure Blob Storage via Private Endpoint

Suppose a storage account is named `stappdemo001` and its private endpoint receives IP `10.20.3.5`. The application calls:

~~~text
stappdemo001.blob.core.windows.net
~~~

In a supported Private Link configuration, the public service name's CNAME chain resolves to a Private Link suffix:

~~~text
stappdemo001.blob.core.windows.net
  → stappdemo001.privatelink.blob.core.windows.net
  → 10.20.3.5
~~~

The private `A` record normally lives in zone:

~~~text
privatelink.blob.core.windows.net
~~~

Example record set:

~~~text
stappdemo001  A  10.20.3.5
~~~

Supported zones and subresources vary by service; **you must pick the exact DNS zone specified by Microsoft for that Private Endpoint type**. Some services have multiple subresources with distinct zones.

~~~mermaid
flowchart LR
    APP["App in VNet"]
    RES["DNS resolver\nwith private zone path"]
    ZONE["Private DNS Zone\nprivatelink.blob.core.windows.net"]
    PE["Private Endpoint\n10.20.3.5"]
    ST["Azure Storage\nstappdemo001"]
    APP -->|"Query storage FQDN"| RES
    RES -->|"Private Link internal name"| ZONE
    ZONE -->|"A = 10.20.3.5"| APP
    APP -->|"Private IP connection"| PE --> ST
~~~

**Logical deployment steps:**

1. Create the private endpoint for the exact storage account and subresource (`blob`).
2. Select or create private zone `privatelink.blob.core.windows.net`.
3. Link the private zone to VNets containing clients needing resolution (or set up appropriate DNS forwarding).
4. Configure a **Private DNS zone group** on the private endpoint when using supported automatic record management.
5. From the workload inside the VNet, verify that the **original service hostname** resolves to the private endpoint's private IP.
6. Test service connectivity and service access policies.

### Private DNS Zone Group vs. Registration Link

| Mechanism | Target | Primary Effect |
| --- | --- | --- |
| Zone **registration link** | Azure VMs in the linked VNet | Automatically registers `A` records for supported VMs |
| Private endpoint **Private DNS zone group** | Private endpoint resource | Manages private DNS records for PaaS services via supported integration |
| Zone **resolution link** | VNets containing clients | Allows Azure-provided DNS to resolve records in the zone |

For Private Endpoints, the standard setup is **zone group + resolution links**, not enabling VM auto-registration.

### Dangerous Misconceptions About Private Link

- **Having a private endpoint does not mean DNS is right.** Connections may still resolve to public addresses if zones, links, or forwarders are wrong.
- **Having a private DNS `A` record does not mean a Private Endpoint exists.** DNS does not secure data connectivity on its own.
- **Do not proliferate duplicate zones with the same name per endpoint without a sharing plan.** Records become hard to manage or collide across multiple VNets and endpoints for the same service.
- **Do not manually edit or delete records managed by a zone group**, because the integration updates records across the private endpoint's lifecycle.
- Private Endpoints are also governed by **network routing, NSGs, DNS, service network settings, and authentication/authorization**; inspect each layer when troubleshooting.

## 8. Multiple VNets, Hub-Spoke, and Hybrid DNS

### 8.1. Two Independent VNets Sharing One Zone

A zone `corp.example.com` can be linked to both `vnet-dev` and `vnet-ops` so both networks resolve its records. If a machine in `vnet-ops` needs to reach endpoint `10.20.1.4` in `vnet-dev`, actual network connectivity such as peering or routing must also exist.

**Peering does not inherit DNS links.** DNS resolution must be planned explicitly for each VNet.

### 8.2. Hub-Spoke Using Azure-Provided DNS

In a hub-spoke topology, workloads run in spoke VNets while network firewalls or shared services sit in the hub VNet. If spokes use Azure-provided DNS and need to resolve a zone, the simplest approach is to **link the zone directly to those spokes**.

Do not assume linking a zone only to the hub and peering all spokes lets every spoke resolve its records. Nor is there a need to create duplicate zones inside every spoke if one shared zone meets your needs and governance boundaries.

### 8.3. Hub-Spoke with Custom DNS

If the enterprise runs custom DNS servers in the hub, spoke machines can query the hub DNS. In that case:

- The DNS forwarder's VNet must be able to resolve the required zones.
- DNS servers must have conditional forwarding configured for the right suffixes.
- Networking/NSGs must allow DNS UDP/TCP 53 traffic as designed.
- Account for DNS server high availability, bandwidth, and operational ownership.

Linking zones to VNets will not fix failures if clients only query custom DNS and that custom DNS does not know where to forward queries.

### 8.4. Hybrid: From On-Premises to Private Zones in Azure

Servers in an on-premises data center may need to query `api.corp.example.com` in Azure over VPN or ExpressRoute.

**Azure DNS Private Resolver** provides managed DNS forwarding, typically using:

- **Inbound endpoint:** a private IP inside a VNet where DNS servers from privately connected networks send queries into Azure.
- **Outbound endpoint:** sends queries through a **DNS forwarding ruleset** to target DNS servers according to rules.
- **Forwarding ruleset:** maps domain suffixes to forwarding targets and links to applicable VNets.

Example flow:

~~~mermaid
flowchart LR
    ONP["Internal server\non-premises"]
    AD["Enterprise DNS\nconditional forward"]
    VPN["VPN / ExpressRoute"]
    IN["Private Resolver\ninbound endpoint in hub"]
    Z["Private DNS Zone\ncorp.example.com"]
    APP["API in Azure\n10.20.1.4"]
    ONP --> AD --> VPN --> IN
    IN -->|"Query private zone linked to resolver VNet"| Z
    Z -->|"10.20.1.4"| ONP
    ONP -.->|"Data connection over private network"| APP
~~~

The zone must be properly linked to the VNet where resolver lookup occurs. On-premises DNS servers forward to the **privately routable inbound endpoint IP**, never directly to `168.63.129.16`.

In the opposite direction, an Azure app needing to resolve on-premises Active Directory names may require an **outbound endpoint + forwarding ruleset** pointing to enterprise DNS. This configuration is independent of creating private zones and is only needed when required.

### 8.5. Distinguishing DNS Private Resolver from Private DNS Zone

- **Private DNS Zone** is **where records are stored**.
- **Private DNS Resolver** is the **component that processes/forwards DNS queries** across environments per architecture.
- **VNet peering/VPN/ExpressRoute** establishes data-plane network connectivity, but **does not automatically create DNS resolution rules**.

## 9. Practical Design: Naming, Resource Organization, and Security

### 9.1. Naming Conventions

A solid naming strategy prevents collisions across environments and reduces friction during service migrations.

Examples:

| Scope | Example Zone or FQDN | Rationale |
| --- | --- | --- |
| Shared internal apps | `corp.example.com` | Easy to share across multiple VNets |
| Dev systems | `dev.corp.example.com` | Isolates record lifecycle from Prod |
| Prod systems | `prod.corp.example.com` | Minimizes blast radius from Dev record edits |
| Blob Storage private endpoint | `privatelink.blob.core.windows.net` | Follows the service's Private Link suffix |
| Service name | `api.prod.corp.example.com` | Clearly identifies environment and role |

Prefer subdomains under domains controlled by the organization. Avoid suffixes that collide with unintended external names or namespaces inconsistently managed by other DNS servers.

### 9.2. Governance Placement and Permissions

A private zone is an independent Azure resource. You can place zones in a shared network management resource group while VNets and workloads live in separate resource groups. Administrative actions may require permissions across the **private zone, VNet, and private endpoint**, depending on the operation.

Applying Azure RBAC:

- Network admins can create/modify zones and VNet links at appropriate scopes.
- Application teams can update only records they legitimately own via scoped permissions.
- Clients querying inside a VNet **do not automatically gain permission to edit DNS resources** merely because the VNet is linked.
- Avoid manually editing Private Endpoint records when they are automatically managed.

Because a zone may serve multiple environments, any edit or deletion of a zone must be evaluated for cross-VNet impact.

### 9.3. DNS Does Not Replace Network Security

A private zone **does not by itself make a service private or secure**. If a server still exposes a public endpoint permitted by firewalls, changing DNS does not block public access.

Combine with:

- Network Security Groups (NSGs) and routing.
- Azure Firewall or equivalent firewall if part of the architecture.
- Private Endpoints with appropriate public network access restrictions where supported.
- Application/service authentication and authorization.
- DNS logs, connection logs, and monitoring per product capabilities.

Private DNS Zones provide **name resolution**, not firewall enforcement.

### 9.4. Cost Considerations

Components that can affect budget:

| Component | Cost Drivers to Check |
| --- | --- |
| Azure Private DNS | Number of hosted zones, DNS query volume, and current billing terms |
| Azure DNS Private Resolver | Inbound/outbound endpoints, forwarding rulesets, and usage per pricing rules |
| VNet peering/VPN/ExpressRoute | Network data transfer, gateways, or connections per billing model |
| Self-managed DNS forwarder VMs | VMs, disks, networking, and operations |
| Private Endpoint | Endpoint resources and data processing per service pricing |

**Actual pricing depends on region and active pricing terms.** Do not extrapolate total bills solely from record counts or VNet link counts.

## 10. Troubleshooting DNS Layer by Layer

When an application fails to resolve a name or connect, trace in order: **record → link → DNS client → network path → service**.

| Symptom | Common Possibility | How to Verify |
| --- | --- | --- |
| `NXDOMAIN` from VM | Zone unlinked, missing record, wrong FQDN, different DNS server answering | Check record, VNet link, and active DNS server |
| `nslookup` returns public IP | Machine querying public/custom DNS; misconfigured private zone or forwarding | Compare query from linked-VNet VM; inspect Private Endpoint DNS |
| Right private IP yet connection times out | Missing route, NSG/firewall block, endpoint unhealthy | Inspect network path and TCP reachability |
| VNet A resolves, VNet B fails | Only A has a DNS link; peering does not carry DNS links | Check each VNet and B's DNS configuration |
| VM name not appearing automatically | Link is resolution-only; VM unsupported or wrong VNet | Check `registrationEnabled` and VM lifecycle |
| On-prem host cannot resolve Azure zone | Missing conditional forwarder, inbound resolver, or network path | Check target DNS IP and VPN/ER path |
| Returns old IP after update | Client/resolver cache or TTL | Compare record in zone against TTL duration |
| Private Endpoint exists yet DNS is wrong | Missing zone group, wrong private zone, or missing VNet link | Check `A` record, zone group, and FQDN used by app |
| Queries to DNS servers give inconsistent answers | Unsynced custom DNS servers, forwarding, or cache | Note responding server and inspect each DNS server config |

### Sample Diagnostic Workflow

**Step 1: Verify the record in Azure.**

~~~bash
az network private-dns record-set a show \
  --resource-group rg-dns-lab \
  --zone-name corp.example.com \
  --name api \
  --output json
~~~

If the record is missing or has the wrong IP, fix the zone record through your governance process.

**Step 2: Verify virtual network links.**

~~~bash
az network private-dns link vnet list \
  --resource-group rg-dns-lab \
  --zone-name corp.example.com \
  --output json
~~~

Confirm the right VNet is linked, link state, and registration mode.

**Step 3: Check which DNS server the host queries.**

On Linux:

~~~bash
cat /etc/resolv.conf
nslookup api.corp.example.com
~~~

`/etc/resolv.conf` may display only a local stub resolver (such as `systemd-resolved`); when needed, inspect actual upstream DNS settings with OS tools like `resolvectl status`. On Windows, use `ipconfig /all` and `nslookup` to inspect DNS details.

**Step 4: Cross-check returned address with connectivity.**

If DNS accurately returns `10.20.1.4` yet the API is unreachable, check ports, routing, NSGs, firewalls, host/service state, and auth; continuing to tweak DNS will not resolve it.

**Step 5: Record TTL and scope.**

Test from two VMs with the same or different DNS paths and note timestamps. From a laptop outside Azure not designed to reach internal DNS, an `nslookup` failure can be expected behavior.

## 11. Capstone Lab: Two VNets Sharing Internal DNS

### Scenario

An application includes an internal API in the Dev VNet and an operations host in the Ops VNet:

- Zone: `corp.example.com`.
- Dev VNet: `vnet-app-dev`, API VM at IP `10.20.1.4`.
- Ops VNet: `vnet-ops`, operations host needs to resolve `api.corp.example.com`.
- Both VNets can be connected via peering per approved network configuration and permissions.

### Tasks

1. Draw a diagram with one private zone, two VNet links, and the `A` record for `api`.
2. Decide whether either link should enable `registrationEnabled`; justify based on requirements.
3. Use commands from Section 6 to create the zone, `A` record, and Dev link. For Ops, link using a separate verified VNet resource ID.
4. From a VM in each VNet, run `nslookup api.corp.example.com` and record the returned IP.
5. Attempt connecting to the API on a valid port and verify the difference between **name resolution** and **network reachability**.
6. Discuss what happens when deleting the Ops link, changing the record's IP, or switching Ops to custom DNS without configuring forwarding.

### Sample Answers and Expectations

| Question | Answer |
| --- | --- |
| Which link type should both use? | **Resolution** (`registrationEnabled=false`) because they only need to read records; VM registration is not required |
| What does the Dev VM resolve? | `10.20.1.4` if record, link, and DNS client are configured properly |
| Can the Ops VM resolve the name? | Yes, if the Ops link is valid and the querying host reaches the zone |
| Does successful resolution guarantee the API works? | No; peering/routing, NSGs/firewalls, and a healthy service are also required |
| What happens if the Ops link is deleted? | Machines using Azure DNS in Ops lose resolution via that link unless another DNS path exists; caches may linger briefly |
| How does editing the `A` record take effect? | New answers propagate per TTL/caching and affect every VNet sharing that zone |
| What if Ops uses custom DNS without forwarding? | Queries may fail to find the record even though the VNet link still exists |

### Advanced Question: Migrating the API to a Private Endpoint

If the app uses Blob Storage via a Private Endpoint instead of a VM API, what must change?

- The zone must use the **service-appropriate Private Link name**, such as `privatelink.blob.core.windows.net` for Blob.
- Records are managed via a **private DNS zone group** when using supported integration.
- Workloads continue calling the **original service name**, such as `stappdemo001.blob.core.windows.net`, verifying it resolves to the private endpoint IP.
- Client VNets are configured with resolution links or proper DNS forwarding paths.
- Still verify routing, firewalls, authentication, and the service's public network access settings.

## 12. Self-Check Questions

**Question 1.** A Private DNS Zone is created without linking to any VNet. Can VMs in a VNet automatically resolve its records using Azure-provided DNS?

**Answer:** Do not assume yes. You need a matching VNet link or a DNS forwarding design capable of resolving that zone.

**Question 2.** Does enabling VNet peering between Dev and Prod automatically let Prod use a private zone linked only to Dev?

**Answer:** No. Peering provides network connectivity, while zone resolution via Azure-provided DNS comes from a VNet link or another configured DNS path.

**Question 3.** Does `registrationEnabled=true` automatically register Private Endpoints into the zone?

**Answer:** No. Auto-registration on a VNet link applies to eligible VMs. Private Endpoints use their own Private DNS zone group mechanism.

**Question 4.** `nslookup` returns the right private IP yet the application still times out. What do you check next?

**Answer:** Check target IP/port, routes, peering/VPN, NSGs/firewalls, and service health. DNS has already resolved one part of the path.

**Question 5.** A machine in a VNet uses corporate DNS servers and cannot resolve the private zone even though the VNet link exists. Why?

**Answer:** The machine queries custom DNS, which cannot yet answer or forward queries to Azure DNS through a properly configured context.

**Question 6.** Should on-premises servers configure conditional forwarding directly to `168.63.129.16` to resolve all Azure Private DNS Zones?

**Answer:** Do not design it that way. That is Azure's platform DNS address requiring VNet context; on-premises normally forwards to an Azure DNS Private Resolver inbound endpoint or a DNS forwarder inside Azure with proper network connectivity.

## Key Takeaways

- A **Private DNS Zone** stores private DNS records; a **VNet link** connects the zone to networks consuming it.
- A **resolution link** enables name resolution; a **registration link** additionally enables automatic record registration for supported VMs.
- **VNet peering does not create DNS links**, and DNS links do not create network routes.
- For **Private Endpoints**, use the exact Private Link suffix, DNS zone group, and resolution links/forwarding so service names return private IPs.
- When using **custom DNS** or on-premises systems, design forwarding explicitly; Azure DNS Private Resolver bridges DNS namespaces across hybrid architectures.
- Troubleshoot in order: **record → link → DNS client/forwarder → IP → network/security → application**, while governing permissions, TTLs, costs, and DNS change impact.
