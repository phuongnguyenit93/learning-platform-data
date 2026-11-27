# Planning DNS, Connectivity, and Identity Synchronization During Migration

## 1. Why Plan These Three Layers Together?

When migrating an application from an on-premises data center (*on-premises*) to Microsoft Azure, provisioning virtual machines, databases, or containers is usually only part of the job. An application can boot cleanly yet still fail if domain names point to the wrong IP, network routes cannot reach dependencies, or users cannot sign in with their existing identities.

This lesson belongs to the **Hybrid Cloud and Migration to Azure** chapter of the `CLOUD_PROVIDERS_AZURE` module. It ties together subscriptions, resource groups, Microsoft Entra ID, virtual networks, compute, storage, databases, monitoring, security, and cost into an executable migration plan.

Three layers must be designed **in lockstep**:

1. **DNS:** Which names must resolve where before, during, and after moving the application? Who is the authoritative DNS and who is the recursive resolver? Do internal and public clients get the same answer?
2. **Connectivity:** Which paths carry traffic between users, Azure VNets, the data center, PaaS services, and management networks? Are bandwidth, network permissions, routes, and latency sufficient?
3. **Identity:** Where do user and service accounts authenticate, which attributes must sync, which system is the *source of authority*, and what happens if on-premises connectivity drops?

Example: an `orders` system uses on-premises Active Directory Domain Services (AD DS), `corp.example.com` DNS, and an on-premises database. When the API moves to Azure App Service, the legacy database hostname may still resolve to the data center; the Azure workload needs routing and network permissions to reach it. Employees sign in via Microsoft Entra ID, while a legacy job still relies on AD DS Kerberos. Changing DNS before connectivity and identity are ready causes an outage even when the software itself has zero bugs.

**Learning objectives:** After this lesson, you will be able to build a dependency inventory, design hybrid DNS, choose connectivity options, plan Microsoft Entra Connect Sync/Cloud Sync, execute a criteria-driven cutover, and create verification/rollback checklists.

## 2. Scope, Assumptions, and Success Criteria

Consider the following sample system. Domain names under `example.com`, IP addresses, resource group names, and SLA values are **hypothetical learning assumptions** and must be replaced with real values in production.

| Component | Before Migration | Expected Post-Migration State |
| --- | --- | --- |
| Users | Customers hit `orders.example.com` from Internet; staff use internal SSO | Frontend/API on Azure, staff identities via Microsoft Entra ID |
| Application | On-premises VMs | Azure App Service or VM/AKS per workload |
| Database | Internal SQL at `sql01.corp.example.com` | Remains on-premises initially; later moves to suitable Azure data service |
| Internal DNS | AD-integrated DNS in `corp.example.com` | Hybrid DNS; some names remain managed by AD DNS |
| Public DNS | Authoritative DNS for `example.com` | Keep or change provider; `orders.example.com` repointed at cutover |
| Network | LAN/data center | Azure hub-spoke, Site-to-Site VPN or ExpressRoute |
| Identity | AD DS is source of internal users/groups | Microsoft Entra ID syncs a subset of identities from AD DS |
| Secrets/workload identity | Service accounts, internally managed secrets | Managed Identity/Key Vault where supported; keep legacy accounts as needed |
| Monitoring | Separate logs and monitoring | Azure Monitor/Application Insights paired with existing tools |

**Acceptance criteria** should tie directly to business journeys:

- Users reach the right frontend at the existing FQDN with valid TLS certificates.
- The Azure API reaches the database during the hybrid phase and service endpoints obey private/public policies.
- Test user logins, group permissions, and legacy apps behave as expected.
- DNS returns the right records per query origin without forwarding loops or leaking internal domain names.
- Transition time, outage duration, and data loss (if any) stay within agreed RTO/RPO.
- Teams can measure, detect errors, and revert to a safe state via runbook.

## 3. Start with a Dependency Map

Do not start by editing DNS records. First catalog **names, addresses, protocols, permissions, and owners** across all links.

~~~mermaid
flowchart TB
    U["Customers / staff"] --> PUB["Public DNS: orders.example.com"]
    PUB --> IN["Azure ingress / application"]
    IN --> VM["Azure API / worker"]
    VM --> PRIV["Private DNS: database and Azure services"]
    VM --> ID["Microsoft Entra ID / Managed Identity"]
    VM --> HYB["VPN or ExpressRoute link"]
    HYB --> AD["On-prem AD DS + DNS"]
    HYB --> SQL["On-prem SQL / legacy systems"]
    PRIV --> PEP["PaaS Private Endpoint"]
    MON["Azure Monitor / Logs"] -.-> IN
    MON -.-> VM
    MON -.-> HYB
~~~

Create an inventory table to guide the transition:

| Dependency | FQDN/IP and Port | Currently Managed By | Post-Migration Plan | How to Test |
| --- | --- | --- | --- | --- |
| Public web | `orders.example.com`:443 | Public authoritative DNS | Point to Azure ingress at cutover | External DNS + HTTPS synthetic |
| Domain controllers | `dc01.corp.example.com`; DNS/Kerberos/LDAP as needed | AD DS / DNS team | Reach via hybrid network or DC in Azure | SRV lookup, domain join/logon |
| On-prem SQL | `sql01.corp.example.com`:1433 (example) | Database team | Keep over hybrid network in wave 1 | TCP reachability + app queries |
| PaaS Storage | `stordersdemo001.blob.core.windows.net`:443 | Azure Storage | Private Endpoint + matching DNS | Resolve private IP, TLS, and auth |
| Authentication | Microsoft Entra sign-in endpoints | Identity team | Cloud auth/SSO per design | MFA/Conditional Access login |
| Secrets | Key Vault endpoint | Security/platform | Managed Identity + Private Endpoint if chosen | Fetch secret with least privilege |
| Monitoring | Ingest endpoint, workspace | SRE | Emit telemetry in new environment | Inspect traces, logs, alerts |

**Do not list only HTTP/443.** AD DS may use DNS 53, Kerberos 88, LDAP/LDAPS 389/636, SMB 445, RPC endpoint mapper 135, and dynamic RPC ports depending on operations. Base exact port rules on actual operations and policy rather than opening wide ranges unchecked.

Also document **return paths**, batch job dependencies, email, queues, certificate validation, update repositories, and management tasks. Then flag:

- Connections that must stay operational during parallel run.
- FQDNs that must remain unchanged across migration.
- Dependencies deferred to later waves.
- Permissions and certificates required before enabling live traffic.

## 4. Understanding DNS Roles in a Hybrid Environment

DNS serves two distinct functions:

1. **Authoritative DNS** holds the official records for a zone, such as public `example.com` or AD DS zone `corp.example.com`.
2. **Recursive resolver** receives client queries, resolves or forwards them to find answers, and caches responses according to TTL.

An AD DS DNS server can perform both roles for different zones, but **never confuse a record existing in a zone with every client querying the same resolver**.

### 4.1. Public DNS, Private DNS, and Split-Horizon

| Type | Example | Who Should Query It? | Risk When Misconfigured |
| --- | --- | --- | --- |
| **Public DNS** | `orders.example.com` | Internet customers and internal clients using public endpoints | Bad cutover sends users to legacy env or breaks TLS |
| **AD-integrated DNS** | `corp.example.com` and domain SRV records | Authorized devices and AD-joined workloads | Domain logon, Kerberos, service discovery break |
| **Azure Private DNS Zone** | `privatelink.blob.core.windows.net` | Linked VNets and configured hybrid resolvers | Private Endpoint resolves wrong IP or fails to resolve |
| **Split-horizon/split-brain DNS** | Same FQDN returning public or private IP depending on client | Per access policy | Hard to debug when queries hit an unexpected resolver |

You do not need to migrate every DNS zone to Azure simply because an app moves to Azure. A sound strategy keeps **zone ownership** clear and sets up only the forwarding/links required.

### 4.2. TTL and Caching During Cutover

**TTL (Time to Live)** dictates how long resolvers may cache a DNS answer. Lowering a public record's TTL ahead of cutover shortens how long clients retain old addresses, yet:

- A new TTL only helps after prior cached entries expire; lowering TTL minutes before cutover **does not purge** existing caches.
- Recursive resolvers, browsers, apps, connection pools, and proxies may cache results or reuse connections on their own schedules.
- Negative caching (`NXDOMAIN`), CNAME chains, and CDN/ingress layers can all affect behavior.
- Changing authoritative DNS/NS delegation requires different preparation than updating an A/CNAME record.

Example policy: reduce TTL from 3600 seconds to 300 seconds **at least long enough beforehand for the prior TTL to expire**, then verify across multiple recursive resolvers. These numbers are illustrative; actual timing and policy depend on the service.

**Never treat a low TTL as a guarantee that “100% of traffic switches in exactly 5 minutes.”** After cutover, keep the legacy endpoint in an appropriate state during observation with a plan for straggling requests.

### 4.3. Do Not Overlook Records Beyond A/CNAME

For public domains, review `AAAA`, `CNAME`, domain verification `TXT`, `CAA`, `MX`, `SRV`, and related records. If changing **authoritative DNS providers**, verify DNSSEC/DS records at the registrar and full zone parity. Never let a website cutover accidentally break email or domain validation.

For AD DS, `_ldap._tcp` and `_kerberos._tcp` (and related SRV records) locate domain controllers. Pointing a VM's DNS client at a public resolver can stop it from finding domain controllers even when IP routing works.

## 5. Recommended Hybrid DNS Resolution Architecture

Azure offers **Azure DNS Private Resolver** to handle hybrid DNS without maintaining full DNS forwarder VMs for supported scenarios. It provides:

- **Inbound endpoint:** a VNet IP address where authorized sources (e.g., on-prem DNS via VPN/ExpressRoute) send queries to resolve using Azure capabilities.
- **Outbound endpoint:** pairs with a DNS forwarding ruleset to forward matching queries from Azure to external DNS servers, such as on-premises DNS.
- **DNS forwarding ruleset:** rules mapping domain suffixes to target DNS servers; links to supported VNets.

Endpoints require dedicated subnets and network setups matching service rules; verify supported subnets, regions, and constraints prior to deployment.

~~~mermaid
flowchart LR
    ON["On-prem client"] --> ODNS["On-prem DNS"]
    ODNS -->|"Forward Azure-related suffix"| IN["Private Resolver inbound endpoint"]
    IN --> AZDNS["Azure DNS / private zone"]
    AZCLIENT["Azure VM / workload"] --> RULE["VNet-linked DNS forwarding ruleset"]
    RULE --> OUT["Private Resolver outbound endpoint"]
    OUT -->|"Forward corp.example.com"| ODNS
    AZDNS --> PZ["VNet-linked Private DNS zone"]
~~~

This depicts bidirectional queries. VNet links, suffix choices, and forwarding direction must avoid **forwarding loops**:

- For `corp.example.com` owned by on-premises authoritative DNS, Azure forwards queries for that suffix via the outbound endpoint to internal DNS.
- For Azure Private Endpoint names, on-premises sends planned suffix queries to the inbound endpoint so Azure resolves them via linked private zones.
- If on-prem DNS also forwards `corp.example.com` back to Azure while Azure forwards it back on-prem, queries loop until timing out.

### 5.1. Forwarding Rules and Client DNS Settings

Document explicitly **which DNS servers clients use**. Azure VMs can use Azure default VNet DNS or configured custom DNS servers. With custom DNS, those servers must forward appropriately to Private Resolver/Azure DNS; linking a Private DNS Zone to a VNet **does not make custom DNS answer properly if it lacks forwarding**.

Azure-provided DNS uses the special address `168.63.129.16` within Azure-supported contexts. Do not treat it as directly queryable from on-premises across VPN/ExpressRoute. For on-premises queries, use a **Private Resolver inbound endpoint** or a suitable DNS forwarder in Azure.

Verify DNS server ordering, forward zones, fallback behavior when targets fail, policy allowlists, and subnet routes. If Azure workloads remain domain-joined to AD DS, VM DNS must resolve both AD domain names/SRV records and Azure PaaS names per design.

### 5.2. Azure Storage Private Endpoint: Resolution Example

Suppose storage account `stordersdemo001` is accessed through a Blob Private Endpoint.

~~~text
Client requests:
stordersdemo001.blob.core.windows.net

Service DNS CNAME:
stordersdemo001.privatelink.blob.core.windows.net

Private DNS zone in Azure:
privatelink.blob.core.windows.net

Corresponding private A record:
stordersdemo001 -> 10.42.2.10  (illustrative IP)
~~~

Clients continue using the **standard service FQDN** `stordersdemo001.blob.core.windows.net` so TLS/SNI and SDKs work seamlessly. The DNS chain resolves to the Private Endpoint IP when clients sit on a properly configured private resolution path. Applications do not change URLs to `privatelink` just to connect.

For on-premises resolution, Microsoft typically recommends conditional forwarding of the **service's public DNS zone suffix** (e.g., `blob.core.windows.net`) to the Azure DNS Private Resolver inbound endpoint in the corresponding pattern. Check interactions with storage accounts **without Private Endpoints** and existing private DNS zones; never blindly forward an entire namespace if doing so breaks resolution of public resources.

**Note:** Creating a Private Endpoint does not automatically disable public network access on the service. Disabling public access and configuring network rules must be done explicitly per service.

### 5.3. Linking a Private DNS Zone to a VNet

The Bicep snippet below illustrates only a **virtual network link** from an existing Private DNS Zone to a VNet. It assumes the Private DNS Zone resides in the target resource group, the VNet ID is valid, and the deployment identity holds required permissions.

~~~bicep
targetScope = 'resourceGroup'

@description('Resource ID of the VNet that needs to resolve the Private DNS zone.')
param vnetResourceId string

@description('Name of the virtual network link to create.')
param dnsLinkName string = 'link-orders-spoke'

resource privateZone 'Microsoft.Network/privateDnsZones@2020-06-01' existing = {
  name: 'privatelink.blob.core.windows.net'
}

resource vnetLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: privateZone
  name: dnsLinkName
  location: 'global'
  properties: {
    virtualNetwork: {
      id: vnetResourceId
    }
    registrationEnabled: false
  }
}

output linkId string = vnetLink.id
~~~

For Private Endpoints, auto-registration is typically not used on `privatelink` zones. Private Endpoint records can be managed via a **private DNS zone group** where supported. This snippet does not create the Private Endpoint, A record, inbound/outbound resolver, or cross-subscription permissions; verify each piece separately.

**Safety rule:** Only modify links/records in zones managed by the responsible DNS team, and assess impact on other services sharing the zone before making changes.

## 6. Network Connectivity Design: Site-to-Site VPN or ExpressRoute?

During a hybrid phase, an Azure API may need to call on-premises AD DS, SQL, or legacy systems. Common options include **Site-to-Site VPN** over IPsec/IKE and **Azure ExpressRoute** over provider-backed private connectivity. They differ in transport, routing behavior, cost, operations, and HA requirements.

| Criterion | Site-to-Site VPN | ExpressRoute |
| --- | --- | --- |
| Transport path | Encrypted IPsec tunnel over Internet or supported link | Private connection via provider/peering per service model |
| Link encryption | IPsec encrypts tunnel | Private link **does not mean automatic end-to-end encryption**; separate encryption may be required by policy |
| Positioning | Often fits pilots or moderate hybrid needs | Often fits high bandwidth/stability and enterprise architecture needs |
| Bandwidth, latency | Depends on tunnels, on-prem devices, ISP, and gateway SKU | Depends on circuit, provider, peering, gateway, and routing |
| Redundancy | Design redundant tunnels/gateways/on-prem devices | Design redundant circuits/peerings/providers/paths |
| Cost | Gateway, data transfer, devices, operations | Circuit/provider, gateway, data transfer, and related charges |
| Replaces public Internet | Not by default; depends on routes and design | Does not automatically route all public endpoints over private peering |

**ExpressRoute does not solve DNS or Entra ID sync by itself.** Conversely, an active VPN does not prove application protocols, ports, TLS, and IAM permissions are right.

### 6.1. IP Addressing and Routing Must Be Decided Upfront

Example plan:

~~~text
On-premises datacenter : 10.10.0.0/16
Azure hub VNet         : 10.40.0.0/16
Azure app spoke VNet   : 10.41.0.0/16
Azure data spoke VNet  : 10.42.0.0/16

Hybrid routing:
Azure app -> VNet peering / hub -> VPN or ExpressRoute -> On-prem SQL
On-prem client -> VPN/ExpressRoute -> Azure Private Endpoint
~~~

These addresses are illustrative; **they cannot be copied if actual CIDRs overlap**. Audit all data centers, branch offices, other clouds, VNets/spokes, Kubernetes pod/service CIDRs where needed, and partner networks. Overlaps create ambiguous routing; NAT or re-addressing are possible workarounds but add DNS, audit, and address-visibility constraints.

Design outputs include:

- CIDRs/subnets, regions, and role of each subnet.
- Routes advertised from on-premises and Azure; BGP if used, route propagation, default routes.
- Hub/spoke peering, gateway transit, and remote gateway usage where supported.
- Route tables/UDRs, Azure Firewall/NVAs, and return paths; avoid asymmetric routing through stateful firewalls.
- NSG and firewall rules **matching exact source, destination, protocol, and port**.
- MTU/MSS, timeouts, long-lived connections, and tunnel failover behavior.
- Bandwidth/throughput limits, network latency, path redundancy, and transfer costs.
- DNS resolver endpoint IPs and access policies from authorized sources.

Never treat `Connected` on a gateway as proof the application works. A tunnel can be up while routes, DNS, NSGs, firewalls, or database permissions are broken.

### 6.2. Hub-and-Spoke and Security Segmentation

The hub hosts connectivity, firewall/inspection, private resolvers, or shared services; spokes host app/data workloads. Benefits are clear governance, provided you verify:

- VNet peering is non-transitive; hub-spoke routing requires proper gateway transit or NVA forwarding.
- With UDRs via a firewall, ensure return packets follow a symmetric path.
- Private Endpoint connections typically use the **endpoint's private IP**; DNS and routing must align.
- NSGs permit only necessary ports; use service tags and endpoint policies per service support.
- Separate deployment, network ops, and identity administration via RBAC and change workflows.

### 6.3. Hybrid Link Resilience

A single link is a single point of failure. Depending on RTO targets, apps may need multiple tunnels, redundant on-prem devices, or ExpressRoute with backup connectivity—plus rehearsed route failover. Also ask: **if data center connectivity drops**, can Azure workloads run in degraded mode or do they halt completely?

Good migration plans progressively reduce reliance on hybrid links wave by wave. As long as legacy databases/AD remain on-premises, Azure workload RTO may remain bounded by data center connectivity.

## 7. Testing Connectivity in Order: DNS → Route → TCP → Application

A layered debugging order prevents false conclusions:

~~~mermaid
flowchart TD
    F["Client calls API/DB by FQDN"] --> D{"DNS returns right IP from right DNS source?"}
    D -->|"No"| DR["Check resolver, zone, forwarder, TTL"]
    D -->|"Yes"| R{"Valid route and return path?"}
    R -->|"No"| RR["Check VNet, gateway, BGP, UDR"]
    R -->|"Yes"| T{"TCP/TLS to target port?"}
    T -->|"No"| TR["NSG, firewall, MTU, cert, listener"]
    T -->|"Yes"| A{"Auth and business transaction?"}
    A -->|"No"| AR["Check token, RBAC, Kerberos, DB permissions"]
    A -->|"Yes"| OK["Record evidence + evaluate latency and HA"]
~~~

### 7.1. DNS and Port Verification Commands

From an authorized Windows client:

~~~powershell
# Confirm which DNS server the client actually uses.
Get-DnsClientServerAddress

# Compare responses from internal resolver and Private Resolver inbound endpoint.
Resolve-DnsName -Name "sql01.corp.example.com" -Type A
Resolve-DnsName -Name "sql01.corp.example.com" -Type A -Server "10.10.1.10"

# Check Azure service FQDN along the private DNS path.
Resolve-DnsName -Name "stordersdemo001.blob.core.windows.net" -Type A

# Test TCP reachability to required port; does not prove login succeeds.
Test-NetConnection -ComputerName "sql01.corp.example.com" -Port 1433
Test-NetConnection -ComputerName "stordersdemo001.blob.core.windows.net" -Port 443
~~~

From a Linux host with `dig` and `curl`:

~~~bash
dig sql01.corp.example.com A
dig @10.10.1.10 sql01.corp.example.com A

dig stordersdemo001.blob.core.windows.net A
dig stordersdemo001.blob.core.windows.net CNAME

curl -I --connect-timeout 5 https://stordersdemo001.blob.core.windows.net/
~~~

`curl -I` against Storage may return **403/400** without credentials or valid operation headers, yet it still exercises DNS, TCP, TLS, and the response path. Never treat HTTP 403 as proof of a network block: inspect which endpoint generated the response and test with valid authorization. These commands measure **from one specific client**, so compare results from both on-premises and Azure.

### 7.2. Read-Only Azure CLI Inspection Helpers

~~~bash
# Confirm subscription/tenant before analyzing.
az account show --query "{subscription:id,tenant:tenantId}" -o json

# Inspect address space of an authorized VNet.
az network vnet show \
  --resource-group rg-network-hub \
  --name vnet-hub \
  --query "{name:name,location:location,addressSpace:addressSpace.addressPrefixes}" \
  -o json

# List VNet links on an existing Private DNS Zone.
az network private-dns link vnet list \
  --resource-group rg-network-dns \
  --zone-name privatelink.blob.core.windows.net \
  -o table
~~~

The resource groups, VNets, and private zones in these examples must exist and the operator needs read access. To inspect routes/NSGs from an Azure VM, **Network Watcher** (effective routes, effective security rules, connection troubleshoot) can be used where supported and permitted. Correlate probe outputs with application and firewall logs before concluding root cause.

## 8. Identity Synchronization: How AD DS Differs from Microsoft Entra ID

**Active Directory Domain Services (AD DS)** is a traditional directory/domain service providing domain controllers, LDAP, Kerberos, Group Policy, domain join, and AD-integrated DNS. **Microsoft Entra ID** is a cloud identity service providing modern authentication, OAuth 2.0/OpenID Connect, enterprise app SSO, Conditional Access, and cloud identity governance.

Syncing users/groups from AD DS to Entra ID **does not turn Entra ID into a domain controller**. Applications requiring LDAP/Kerberos or Group Policy still need an appropriate AD DS design, or must be modernized to modern auth standards.

| Need | Direction |
| --- | --- |
| Employees accessing SaaS/modern apps via SSO | Entra ID; OIDC/SAML per app |
| Users/groups still authored and managed in on-prem AD DS | Sync identities to Entra ID via supported tooling |
| VMs/legacy apps needing domain join, LDAP/Kerberos | Reachable AD DS or supported domain service option |
| Azure workloads calling PaaS and Azure APIs | Managed Identity and RBAC/data-plane permissions where supported |
| Partners using external identities | Entra External ID/B2B per policy |
| Apps needing custom attributes or custom provisioning | Check sync/provisioning capabilities, transformations, and connector limits |

### 8.1. Entra Connect Sync and Entra Cloud Sync

Microsoft offers AD DS-to-Entra ID synchronization options including **Microsoft Entra Connect Sync** and **Microsoft Entra Cloud Sync**. They differ in feature sets, agent/engine architecture, configuration requirements, and limitations.

A tool selection plan must establish:

1. How many forests/domains, topologies, and trusts exist?
2. Are specific attributes, object types, writeback, or specialized hybrid features needed?
3. Are high availability, staging servers, or agent redundancy required?
4. Can **Cloud Sync** cover all current requirements, or is **Connect Sync** required?
5. Are OU/group scoping and filtering rules clearly defined?
6. Have current version, licensing, and supportability been verified at deployment time?

**Do not treat the two products as 1-to-1 drop-in substitutes in every scenario.** Before choosing, check the current feature support matrix, versioning, and enterprise prerequisites.

### 8.2. Source of Authority and Identity Attributes

Decide **which system owns creating and editing attributes** (source of authority) per object group before enabling sync. For AD DS-synced users, many attributes are mastered in AD DS and synced upward; edits in Entra ID may be overwritten or restricted depending on the feature.

Key attributes/structures to verify:

- **UPN (User Principal Name):** does the sign-in name use an Entra ID-verified domain suffix matching user experience?
- **mail/proxyAddresses:** avoid duplicate aliases, invalid emails, or collisions with existing Entra ID objects.
- **Source anchor / immutable identifier:** stable link between on-prem and cloud objects; careless edits can create duplicates or mismatches.
- **Object IDs and group relationships:** do apps key off user/group IDs? Will migration alter identity references?
- **Disabled/deleted accounts:** align offboarding, deletion, and restore policies.
- **OU/group scoping:** limit pilots to intended objects; avoid syncing unnecessary sensitive directory objects.

**Common pitfall:** A cloud-only user `user@example.com` already exists, and enabling AD DS sync creates a duplicate object. Soft/hard matching must be planned using Microsoft-supported mechanisms; botched immutable ID edits can break links, drop permissions, or lock users out. Test on a pilot group and record state before bulk changes.

## 9. Hybrid Authentication: Password Hash Sync, PTA, and Federation

Directory sync and the **authentication method** are related yet distinct decisions.

| Method | High-Level Principle | Migration Considerations |
| --- | --- | --- |
| **Password Hash Synchronization (PHS)** | Syncs a derived form of password hashes from AD DS to Entra ID via service mechanism | Can reduce runtime dependency on on-prem auth; verify policy and features |
| **Pass-through Authentication (PTA)** | Entra ID delegates password validation via agents connected to AD DS | Depends on agents and AD connectivity; needs HA and outage testing |
| **Federation** | Uses a federated identity provider over supported protocols | Depends on IdP, certificates, DNS, network, policies, lifecycle, and HA |

PHS **does not sync plaintext passwords**; its exact mechanics and security safeguards must align with service docs. Choosing PHS/PTA/federation directly governs whether users can sign in if on-premises connectivity fails. Evaluate MFA, Conditional Access, credential resets, password writeback (if supported/licensed), and change convergence times.

### 9.1. Mandatory Identity Tests

Pilot acceptance matrix:

| Test | Expected Behavior | What to Record |
| --- | --- | --- |
| Synced user login | Exact UPN, MFA/Conditional Access per policy | Timestamp, auth method, sign-in logs |
| New user created in pilot OU | Object appears properly in Entra ID | Sync latency, allowed attributes |
| Controlled rename/UPN change | Permissions and login continue smoothly | Any app dependency on old name |
| User disabled | Access revoked within policy target | Token/session lifetime, sync delay |
| Group membership change | Authorization updates properly | Claims, token renewal, app caching |
| Simulated on-prem disconnect | Behavior matches PHS/PTA/federation design | Can new/existing users sign in? |
| Break-glass cloud accounts | Emergency access works per policy if sync/IdP fails | Logging, protection, monitoring access |

**Never equate “sync success” with completed identity migration.** Users must actually sign in and receive expected application permissions. Some changes only take effect once new tokens are issued or caches expire.

### 9.2. Emergency Access Accounts to Avoid Tenant Lockout

Before cutover, establish protected, monitored, and separately tested **emergency access/break-glass** procedures for Entra ID. Never make all administrative sign-in paths depend on an on-premises IdP undergoing migration. Authorized holders, usage runbooks, evidence, and alerts must be approved by security.

Never record passwords, tokens, recovery codes, or break-glass credentials in migration docs, test scripts, or logs.

## 10. Workload Identity and Legacy Apps During Parallel Operation

Syncing users does not solve service-to-service authorization. When an API moves to Azure:

- For supported Azure Storage, Key Vault, Azure SQL, and Azure APIs, prefer **Managed Identity** with Azure RBAC or database permissions, avoiding long-lived secrets.
- For workloads lacking Managed Identity support, use service principals/federated credentials and policy-compliant secret vaults.
- If an app still requires **Kerberos/Windows Integrated Authentication**, ensure domain controllers/KDCs, DNS SRV lookups, SPNs, time sync, and required ports work. Simply “having a matching username in Entra ID” is not enough.
- When using LDAPS or certificate-based apps, verify trust chains, hostnames, and certificate lifecycles in Azure.
- If apps log into databases via AD DS or managed identities, verify exact configuration and supported auth methods for that **specific database service**.

Options for legacy apps include placing AD DS domain controllers on Azure VMs (with proper site/replication/DNS, security, and DR) or evaluating Microsoft Entra Domain Services where requirements and support scope match. **Entra Domain Services does not replace every feature of self-managed AD DS**; assess features and limits before selecting.

### 10.1. Alignment Across DNS, Network, and Identity

Example domain-joined Azure VM:

1. VM resolves `_ldap._tcp.dc._msdcs.corp.example.com` to valid DCs via DNS/forwarders.
2. Routes from VM subnet to DC exist; NSGs/firewalls permit required protocols.
3. System clocks stay synchronized so Kerberos does not fail on time skew.
4. User/machine holds valid AD DS permissions; Group Policy and SPNs are accurate.
5. If the primary tunnel fails, redundant routing preserves authentication availability.

Test each layer independently: successful DNS resolution **does not prove** Kerberos works, and successful ping **does not prove** login permissions succeed.

## 11. Wave-Based Migration Instead of Big-Bang Cutover

A manageable approach splits work into phases:

| Wave | Goal | DNS | Connectivity | Identity |
| --- | --- | --- | --- | --- |
| **0 – Discovery** | Inventory dependencies, owners, RTO/RPO, baselines | Records, zones, TTLs, forwarders | IP/CIDRs, ports, latency, routes | Users/groups, app auth, source of authority |
| **1 – Landing zone** | Build Azure foundation | Private DNS Zones, Resolver, test FQDNs | Hub/spoke, VPN/ER, NSGs, monitoring | Tenant, RBAC, sync pilot, break-glass |
| **2 – Pilot** | Run isolated app instance | Test records or subdomain | Test each dependency path | Test login, tokens, LDAP/Kerberos if needed |
| **3 – Hybrid production** | Run app in Azure while DB remains on-prem | Prep cutover TTLs/records | Production paths and HA | Sync users, permissions, workload identity |
| **4 – Data migration** | Move data/dependencies to Azure | Update internal target names per plan | Switch database/queue paths | Update auth and permissions accordingly |
| **5 – Cutover/optimization** | Switch live traffic and reduce legacy ties | Update records/ingress, watch caches | Trim unused links | Retire legacy auth components with evidence |
| **6 – Decommission** | Safely retire legacy infrastructure | Clean stale records | Decommission unused tunnels/routes | Clean up accounts/SPNs/secrets per process |

Waves follow **dependencies**, not necessarily resource types. For example, you cannot drop hybrid connectivity before finishing database migration and any jobs still calling on-premises Kerberos.

### 11.1. Go / No-Go Criteria per Wave

Advance a workload to the next wave only when:

- Owner, scope, and blast radius are confirmed.
- Baselines, metrics, tracing, and alerts are operational.
- DNS resolution passes across key client segments.
- Bidirectional routing, TLS, firewalls, and dependency ports pass.
- Pilot users, admins, and workload identities authenticate cleanly.
- Data is synced safely preserving consistency, with read/write tests passing.
- Clear **rollback**, approvers, stop triggers, and RTO/RPO measurements are ready.

If criteria fail, log concrete blockers and revisit the architecture; never compensate by opening wide firewall rules or enabling anonymous access just to “pass” a test.

## 12. Controlled DNS and Traffic Cutover Process

Suppose `orders.example.com` currently points to on-premises ingress and will move to Azure ingress. Preparation goes far beyond editing an A/CNAME record.

### Before Cutover Day

1. Verify control over the public authoritative zone and record updates; snapshot existing A/AAAA/CNAME, TTL, and DNSSEC/DS records if applicable.
2. Validate TLS certificates, SNI/hostname bindings, WAF, CDN/Front Door, and Azure backend health—never send traffic to an unready target.
3. Lower TTL **early enough** for old caches to expire, not minutes beforehand.
4. Confirm private DNS for database/Key Vault/Storage and hybrid clients; never mix public and private endpoint records.
5. Prepare end-user validation via test hostnames or host-specific routing without impacting production (ensuring valid TLS/Host headers).
6. Run controlled load tests; measure SLIs/SLOs and resilience.
7. Verify **data ownership**: which store holds write authority and what state data is in when traffic shifts? Avoid dual writers without conflict resolution.

### During Cutover

~~~mermaid
sequenceDiagram
    participant IC as Incident/Change Lead
    participant DNS as Authoritative DNS
    participant OLD as Legacy ingress
    participant NEW as Azure ingress
    participant MON as Monitoring
    IC->>MON: Mark UTC start timestamp and baseline
    IC->>NEW: Verify health, TLS, and synthetic transactions
    IC->>DNS: Update records per approved change
    DNS-->>IC: Record updated
    MON->>NEW: Synthetic checks from multiple vantage points
    MON->>OLD: Monitor straggling traffic on legacy target
    NEW-->>MON: Success rates, latency, dependency health
    IC->>MON: Compare SLOs and data state
    Note over IC,MON: Go / rollback per pre-agreed thresholds
~~~

For applications supporting weighted traffic management, blue/green, or reverse proxies, shifting traffic incrementally can be safer than a single DNS flip. Regardless of mechanism, watch **real users** alongside synthetic checks; seeing DNS return the new IP is never sufficient.

### After Cutover

- Verify resolution for the same FQDN from public DNS, on-premises, and Azure; log resolvers and timestamps.
- Monitor residual traffic hitting the old environment, long-lived connections, and DNS caches.
- Check sign-in logs, MFA, tokens, domain-joined apps, and claims/group permissions.
- Verify database write consistency, queue backlogs, log ingestion, backups, and alerts.
- Keep the legacy environment read-only or ready for rollback when feasible; do not delete immediately.
- Raise TTL back only once the new path is stable and change policy permits.

## 13. Rollback Is Not Just Reverting DNS

**DNS rollback** redirects **new requests** to the legacy ingress, yet does not sync data written in Azure nor revoke issued tokens, sessions, or open connections. For stateful systems, define **which store is authoritative** in every phase.

| Scenario | Risk | Must Be Defined Beforehand |
| --- | --- | --- |
| Azure frontend fails, DB still on-prem | Minimal cross-site data drift if writing to old DB | Revert ingress, inspect in-flight requests |
| DB promoted in Azure, then app rolls back | Two writable sources, split-brain | Fence writers, controlled sync/replay, data owner workflow |
| User changes password during parallel run | Password/hash sync, auth policies, and convergence lag differ | Define source of authority and test login post-rollback |
| Private DNS misconfigured | Clients hit public endpoint or wrong IP | Zone/record snapshot, revert links/forwarding, test from VNets |
| VPN/ER fails mid-cutover | Azure workloads lose on-prem reachability | Backup route, degraded mode, or halt transition |
| Lingering TTL/caching | Clients split traffic across both ingresses | Keep both targets compatible, monitor/drain traffic |

**Rollback criteria** must be explicit: business error rate exceeding threshold over an observation window, DB connectivity loss, severe sign-in failures, or risk of data loss. Name rollback decision-makers, cutoffs, verification steps, and communication protocols upfront.

Never weaken security controls to rescue a failing cutover without formal approval. A safer recovery may be **temporarily freezing writes**, keeping reads available, and prioritizing data integrity.

## 14. Observability and Failure Drills in Hybrid Mode

Combine Azure Monitor, Application Insights, Log Analytics, Network Watcher, gateway metrics, and identity logs (Microsoft Entra sign-in/provisioning/sync logs within available telemetry) with on-premises tooling.

Minimum signals:

| Layer | Metrics | Why |
| --- | --- | --- |
| DNS | Resolution success rate, returned IPs, query latency, failures/loops | Spot wrong records or unexpected resolvers |
| Hybrid network | Tunnel/circuit state, BGP routes, bytes, errors, latency, packet loss | Distinguish link outage from app bug |
| Compute/API | Success rate, p95/p99 latency, dependency failures | Measure real user impact |
| Data | DB connection success, transaction errors, replication lag, queue backlog | Catch failing data dependencies |
| Identity | Sign-in errors, sync failures, MFA/CA outcomes, agent health | Detect lockouts and permission drift |
| Security | NSG/firewall denies, Key Vault access failures, cert expiry | Detect blocked paths or missing permissions |
| FinOps | Egress, VPN/ER/Resolver spend, log ingestion | Control parallel and post-migration costs |

### 14.1. Failure Drills to Run Before Cutover

- **DNS resolver failure:** one forwarder goes down; do clients fail over cleanly or time out?
- **Missing private DNS link:** does an Azure workload in a second spoke still resolve the Private Endpoint?
- **Primary tunnel loss:** do BGP routes and on-prem DNS continue over the backup path?
- **AD sync paused:** can already-synced users sign in per design; when do new users appear?
- **On-prem auth outage:** does the app behave per PHS/PTA/federation design and does break-glass access work?
- **Spiking DB network latency:** do connection timeouts/retries/backoffs overload the app?
- **Mid-transition partial rollback:** are sessions, writes, and caches handled safely?

Run drills in test environments or approved scopes using synthetic data, active monitoring, and explicit stop conditions. Never trigger broad production outages merely to “check a box.”

## 15. Handover Documentation and Ownership Matrix

Migrations span multiple teams: networking, DNS, identity, application, database, security, and FinOps. Without clear owners, incidents bounce between teams.

| Workstream | Primary Owner | Handover Evidence |
| --- | --- | --- |
| Public DNS/registrar/TTL | DNS/platform team | Before/after records, authority, rollback access |
| Private DNS/Resolver | Azure networking | Zone links, rulesets, target IPs, query tests |
| VPN/ExpressRoute/routing | Network team | Route tables, failover tests, bandwidth/latency |
| AD DS/Entra sync | Identity team | Source mapping, sync health, UPN/attribute tests |
| Auth and app permissions | App + security | Sign-in logs, RBAC, Managed Identity, tests |
| Database and data migration | Data team | Sync/checksums, write ownership, rollback/failback |
| Monitoring and incident response | SRE | SLI/SLO dashboards, alerts, runbooks |
| Cost and quotas | FinOps/platform | VPN/ER/Resolver/egress forecasts, capacity, budgets |
| Cutover coordination | Change/incident lead | Go/No-Go, UTC timeline, stakeholder updates |

Assign a **backup owner**, target dates, and links to reviewed configs/docs for every workstream. DNS and identity are shared infrastructure: evaluate every change against **all dependent workloads**, not solely the migrating app.

## 16. Practice Exercise: Designing Migration for an Ordering App

**Context:** An enterprise has data center `10.10.0.0/16`, AD DS at `corp.example.com`, and `orders.example.com` on VMs. SQL Server `sql01.corp.example.com` remains on-premises initially. The enterprise builds Azure hub `10.40.0.0/16`, app spoke `10.41.0.0/16`, and data spoke `10.42.0.0/16`. The Azure app needs a Storage Private Endpoint; staff use Entra ID SSO, while a batch worker requires Kerberos to AD DS. Names and numbers are hypothetical for practice.

### Task A — Draw the DNS and Networking Architecture

1. Identify authoritative servers for `example.com`, `corp.example.com`, and `privatelink.blob.core.windows.net`.
2. Trace DNS query paths from **on-prem clients**, **Azure VMs**, and **spoke apps** to the database and Storage Private Endpoint.
3. Sketch VPN or ExpressRoute, hub/spoke routes, required firewall/NSG rules, and return paths.
4. Identify at least two single points of failure with monitoring and redundancy measures.

**Guidance:** On-prem authoritative DNS manages `corp.example.com`, while Azure private DNS zones attach to Azure with matching inbound/outbound resolver endpoints. Azure must never loop queries back to itself. Azure workloads reach on-prem SQL over the hybrid route; Azure clients receive private IPs for Storage FQDNs via the proper DNS path.

### Task B — Design Identity Synchronization

1. List pilot users/groups, UPNs, and source anchors; check for colliding cloud-only objects.
2. Propose Connect Sync or Cloud Sync per requirements; note features needing verification first.
3. Pick PHS/PTA/federation based on enterprise availability goals; analyze impact if data center connectivity drops.
4. Separate **user SSO** from **batch Kerberos** permissions; propose how to retain AD DS for legacy or modernize it.
5. Design break-glass access, Conditional Access/MFA, rollback, and sign-in test cases.

**Guidance:** Object sync and authentication are distinct layers. Entra ID does not directly replace AD DS for Kerberos/LDAP; the batch worker still needs DNS/routing/DC reachability or code modernization. Pilot tests must validate login, group claims, and actual access rights.

### Task C — Build the Cutover Plan

Complete the table:

| Time | Action | Approver | Passing Evidence | Rollback Trigger |
| --- | --- | --- | --- | --- |
| T−several days | Lower public TTL; inventory DNS | DNS owner | New/old TTL answers observed | Inconsistent DNS records |
| T−1 day | Probe hybrid path, DNS, identity, DB | Network + identity + app | Test matrix passes | Any critical dependency fails |
| T0 | Lock data writer and enable Azure ingress | Change lead + data owner | SLIs and data accurate | Split-brain risk or DB error |
| T+monitoring | Flip public DNS or routing weights | DNS/change lead | New requests land on right target | 5xx/latency/login above threshold |
| T+stabilization | Watch caches, backlogs, telemetry | SRE | SLOs hold continuously | Data anomalies |
| Post-retention | Controlled teardown of legacy infra | App + data + security | Zero remaining dependencies | Insufficient evidence |

Never treat hypothetical dates as production schedules. Milestones and approvers must be formally endorsed by the organization.

### Task D — Author the Verification Checklist

Build a checklist spanning all three vantage points: on-premises, Azure VM, and external client. For each, verify DNS A/CNAME/SRV, TCP/TLS, business queries, user login, worker permissions, telemetry, cost/latency, and rollback paths. Report **actual measured outputs**, not merely commands returning exit code 0.

### Exercise Passing Criteria

- Diagrams show DNS ownership, resolver paths, and zero forwarding loops.
- Non-overlapping CIDRs, bidirectional routing, and least-privilege firewall rules for SQL/AD/Storage.
- Clear identity source of authority, sync scope, auth model, and pilot test accounts.
- Migration wave schedule, Go/No-Go gates, rollback/data ownership, and SLI/RTO/RPO criteria.
- Measured multi-vantage evidence, owners, and full alignment across DNS, networking, and identity.

## 17. Common Pitfalls and Troubleshooting

| Symptom | Common Causes | How to Diagnose and Fix |
| --- | --- | --- |
| Azure VM cannot find domain controller | DNS client uses public resolver; missing forward zone/SRV or route to AD DNS | Inspect DNS servers, SRV lookups, routes, and ports |
| Private Endpoint still resolves to public IP | Missing zone link, custom DNS not forwarding, wrong namespace or record | Trace CNAME chain, private A record, VNet links, and inbound endpoint |
| On-premises fails to resolve private PaaS names | Forwarder not pointing to Azure resolver / no network path | Test queries directly against on-prem DNS and inbound endpoint |
| High DNS timeouts | Forwarding loop or unreachable target DNS | Inspect bidirectional rules, logs, and resolver health |
| Tunnel “Connected” yet SQL unreachable | Bad UDR/BGP, NSG, firewall, return path, or DB listener | Trace layer-by-layer from actual source IP |
| API TLS errors post-cutover | Mismatched certificate/hostname/SNI | Inspect ingress bindings and application FQDN |
| Synced user cannot sign in | UPN, Conditional Access/MFA, auth method, or object matching issue | Inspect sign-in logs, sync logs, pilot mappings |
| Duplicate users or lost permissions | UPN/alias collision, source anchor mismatch, or group drift | Pause scope expansion, verify links, restore per identity runbook |
| Kerberos/LDAP fails despite working Entra login | AD DS dependency unmigrated or unreachable | Check DCs, DNS, time sync, SPNs, and required ports |
| DNS rolled back yet data is wrong | Both sides accepted writes without sync/reconciliation | Data owner verifies authoritative writer and repairs data |
| Unexpected cost spike post-cutover | Cross-region egress, Resolver, VPN/ER, log retention, or dual traffic | Inspect Cost Analysis by scope, meter, service, and time |

## 18. Principles to Remember

1. **DNS picks the destination by name, routing delivers packets to IPs, and identity governs who gets access.** All three must succeed before declaring migration complete.
2. **Private DNS needs end-to-end resolution paths.** Azure Private DNS Zones, VNet links, Private Resolver, conditional forwarders, and client DNS settings must align without loops.
3. **Hybrid connectivity is a real network system.** VPN/ExpressRoute demands non-overlapping addressing, bidirectional routing, security, HA, and app-level validation—not just a green gateway status.
4. **Identity sync does not replace AD DS.** Entra ID, AD DS, Connect Sync/Cloud Sync, PHS/PTA/federation, and Kerberos/LDAP each serve distinct roles.
5. **Pilot first, cut over in waves.** Lower TTLs early enough, test from multiple vantage points, verify certs/logins/data, then switch production traffic.
6. **Rollback requires data and auth planning.** Reverting DNS does not resolve issued tokens, sessions, database writes, or split-brain risk.
7. **Measure from the user's perspective.** Valid DNS responses, connected VPNs, and successful sync jobs do not prove end-to-end business transactions work.
8. **Assign owners and keep docs current.** Networking, DNS, identity, application, data, and FinOps must execute from one shared runbook.

By planning DNS, connectivity, and identity synchronization as **one unified design**, an organization can move applications to Azure in controlled stages, preserve service continuity during hybrid operation, safeguard identities and data, and lower risk throughout cutover and legacy decommissioning.
