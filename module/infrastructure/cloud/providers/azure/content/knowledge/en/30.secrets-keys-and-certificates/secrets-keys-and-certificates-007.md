# Private Endpoints and Key Vault Access Restrictions

In the **CLOUD_PROVIDERS_AZURE** module, learners explore the Microsoft Azure ecosystem from subscriptions, resource groups, and Microsoft Entra ID to virtual networking, compute, storage, and data services. The ultimate goal is to deploy, monitor, protect, and control costs of an application architecture on Azure. Part of the **Secrets, Keys, and Certificates** chapter, this lesson explains how to restrict access paths to **Azure Key Vault** using **Private Endpoints/Private Link**, Azure Virtual Networks, private DNS, and network policies, while combining them properly with authentication and authorization.

Running example: a Java Spring Boot application running on **Azure Kubernetes Service (AKS)** needs to read the `orders-db-password` secret from Key Vault. Security policy requires that secrets must not be retrievable from the public internet, even by users holding a valid Azure sign-in; only authorized workloads on the private network may read them. The operations team also needs to deploy the configuration without locking out administration paths, configure private DNS, allow CI to run controlled tests, and monitor denied requests.

After completing this lesson, you will be able to:

- Distinguish **Key Vault control plane, data plane, network authorization, and identity authorization**.
- Choose correctly among **public endpoint + firewall/IP allowlist**, **Virtual Network service endpoints**, and **Private Endpoints**; understand the limits of **trusted Microsoft services bypass**.
- Design **Private Link**, the `privatelink.vaultcore.azure.net` private DNS zone, VNet links, and hybrid connectivity over VPN/ExpressRoute.
- Deploy and verify configurations using **Azure Portal, Azure CLI**, DNS/TLS probes, Key Vault REST/SDKs, and the **Java Azure SDK**.
- Configure **Microsoft Entra ID, managed/workload identities, and Azure RBAC or access policies** for the data plane without confusing private networking with secret-read permissions.
- Understand the sequence for migrating from public to private without outages, and how to troubleshoot `403 Forbidden`, broken DNS, unapproved private endpoints, SSL errors, RBAC propagation, and route/firewall issues.
- Validate policies with **negative tests**, record audit logs, set up alerts, roll back safely, and optimize operational costs.

## 1. What Does Key Vault Protect?

**Azure Key Vault** is a managed service for storing and accessing:

| Object Type | Purpose | Examples |
|---|---|---|
| **Secret** | Confidential strings/values and versions | Passwords, API keys, connection secrets |
| **Key** | Cryptographic keys and operations per policy | RSA keys for sign/verify, wrap/unwrap |
| **Certificate** | Certificate lifecycle management and related metadata | TLS certificates, policy/renewal |

Not every certificate operation is an ordinary secret read: certificates have linked objects, and retrieving **private-key-bearing certificate material** may require corresponding secret access. Assign data-plane roles according to the exact operation required.

### 1.1. Four Conditions for a Secret Read

A request to retrieve a secret traverses multiple layers:

```text
Java application
      |
      v
1. DNS resolves <vault>.vault.azure.net
      |
      v
2. Network path and Key Vault network policy
   (public firewall OR approved private endpoint)
      |
      v
3. Microsoft Entra authentication
   (token, audience, identity)
      |
      v
4. Data-plane authorization
   (Azure RBAC or vault access policies)
      |
      v
Key Vault returns secret value over TLS
```

**A Private Endpoint only addresses the network path layer.** It does not grant `secrets/get`. Conversely, an identity holding `Key Vault Secrets User` cannot bypass a Key Vault firewall on its own. For a read to succeed, **both networking and identity/authorization** must be valid.

### 1.2. “Two-Lock” Security

You can remember it as:

```text
ALLOW_ACCESS =
  NETWORK_PATH_ALLOWED
  AND AUTHENTICATED_IDENTITY
  AND DATA_PLANE_PERMISSION
  AND APPLICATION_POLICY_ALLOWED
```

This is a **mental model**, not an executable Azure Policy expression. Beyond cloud policies, the application still needs business authorization so an authorized client cannot read unrelated secrets.

### 1.3. Key Vault Is Not a High-Throughput App Data Store

Do not call Key Vault on **every request** of a web app just to fetch the same secret. Besides cost, latency, and throttling, doing so puts Key Vault synchronously on the hot path. Use a credential/secret cache with a TTL/rotation policy tailored to risk, avoid logging secret values, and ensure revocation/rotation is not overly delayed by caching.

## 2. Control Plane vs. Data Plane

The **control plane** uses Azure Resource Manager (ARM) to create/modify Key Vault resources, configure networking, assign permissions, diagnostics, and policies. The **data plane** uses the vault's endpoint to `get/list/set/delete` secrets, sign/verify keys, and manage certificates.

| Plane | Conceptual endpoint/flow | Example operations | Security implications |
|---|---|---|---|
| **Control plane (ARM)** | Azure Resource Manager APIs | `az keyvault create/update/show`, configure network ACLs | Administrative ARM/RBAC rights must be restricted |
| **Data plane (vault)** | `https://<vault>.vault.azure.net` | `SecretClient.getSecret("orders-db-password")` | Governed by network access rules and data-plane authorization |
| **Identity plane** | Microsoft Entra ID token endpoint | Managed identity acquires access token | Token audience/tenant/principal must match |
| **Application layer** | Enterprise-owned API/worker | App decides who may invoke logic using the secret | Never replaced by a network allowlist |

### 2.1. Critical Trap: Disabling Public Access Does Not Lock All Admin Operations

`publicNetworkAccess: Disabled` primarily restricts **Key Vault data-plane access over the public endpoint**. It **does not disable the Azure Resource Manager control plane**. Anyone with sufficient admin rights can still alter vault settings via ARM from allowed management paths. Therefore, protect **ARM permissions** using Azure Policy, PIM, approvals, activity logs, and governance controls rather than only adding a private endpoint.

### 2.2. Vault Management Rights Do Not Equal Secret Read Rights

When a vault uses the **Azure RBAC data-plane model**, a principal with ARM management rights like “Contributor” does not automatically gain permission to read secret values. Conversely, high ARM privileges may allow **modifying role assignments or network settings**, creating a privilege-escalation path; evaluate blast radius carefully. Under the **legacy access policy model**, managing access policies follows a different governance model. Pick one explicit model, manage it via IaC, and test effective access with real requests.

## 3. Ways to Restrict Network Access

Key Vault can be protected under several network models:

| Model | Data path | Rules | Pros | Limitations |
|---|---|---|---|---|
| **Default public endpoint** | Internet → public vault FQDN | May allow all networks depending on settings | Easy to start | Broad network surface if unrestricted |
| **Public endpoint + firewall/IP rules** | Public endpoint | Only allowlisted public IPv4/CIDR | Fits sources with static egress IPs | IP changes/NAT; still traverses public endpoint |
| **Virtual Network service endpoint** | Service endpoint to service; logical endpoint remains public | Key Vault network ACL permits subnet | Restricts to specific VNet/subnet | No dedicated private IP for vault; requires proper subnet/service-endpoint setup |
| **Private Endpoint** | VNet → private IP → Private Link → vault | Approved private endpoint + DNS + permissions | Private access; public data-plane access can be disabled | DNS/hybrid/peering, approvals, monitoring, and cost add complexity |

Specific choices also depend on **Key Vault type, region, compliance requirements, and current Azure configuration**. **Managed HSM** uses a different endpoint/network/permission model; this lesson focuses on standard **Azure Key Vault vaults** holding secrets, keys, and certificates—do not assume every command applies verbatim to Managed HSM.

### 3.1. Is Keeping the Public Endpoint with an Allowlist Enough?

Sometimes it suffices for a small workload with a fixed public IPv4 egress and permissive security policy. However, with AKS/App Service, egress IPs can change with architecture, NAT, or scaling, causing IP rules to drift or break unexpectedly. **An allowed IP does not authenticate an application**: any principal with a valid token and data-plane permissions calling from that IP can still access the vault, so identity remains an independent layer.

### 3.2. How Do Service Endpoints Differ from Private Endpoints?

With a **Virtual Network service endpoint**, Azure networking identifies traffic from an authorized subnet toward the Key Vault service. The vault still uses its public FQDN; you enable the **`Microsoft.KeyVault` service endpoint** on the subnet and add a **subnet network rule** on the vault. There is no dedicated private IP NIC per vault as with Private Endpoints. With a Private Endpoint, DNS resolves the vault FQDN to the **endpoint's private IP inside the VNet**.

### 3.3. Public Network Access, Default Action, and Bypass Are Three Separate Concepts

- **`publicNetworkAccess`** controls whether the data plane is reachable over the public network per current feature semantics.
- **`networkAcls.defaultAction`** (Allow/Deny) is the default firewall action for public paths when enabled.
- **`networkAcls.ipRules`/`virtualNetworkRules`** are allowlist exceptions when that model is active.
- **`networkAcls.bypass`** can permit a finite set of **trusted Microsoft services** in supported configurations; it does not exempt every Azure resource from the firewall.

**Do not count on IP allowlists or “trusted services” bypass as an escape hatch once public network access is disabled**, if that feature no longer permits public-path access. Check the exact behavior of the resource API/tier and set up **private management/test paths** before closing public access.

## 4. How Private Link and Private Endpoints Work

**Azure Private Link** provides access to supported services over a **Private Endpoint**—a network interface/private IP inside your VNet bound to a target resource/subresource. For a standard Key Vault, the subresource/group ID for the private endpoint is **`vault`**.

```text
Azure subscription A                         Azure-managed service
  +--------------------------------+         +---------------------+
  | VNet vnet-app-prod             |         | Azure Key Vault     |
  |                                |         | kv-orders-prod      |
  |  AKS / VM / private app        |         |                     |
  |       |                        |         | Data plane          |
  |       | TLS to vault FQDN      |         |                     |
  |       v                        |         +-----------+---------+
  |  Private DNS resolution        |                     ^
  |       |                        |                     |
  |       v                        |           Private Link service
  |  10.42.5.4  (private endpoint) +---------------------+
  |                                |
  +--------------------------------+

Client URL stays: https://kv-orders-prod.vault.azure.net/
DNS inside VNet: resolves to PE private IP (example 10.42.5.4)
```

**`10.42.5.4` is an example.** Never copy an illustrative IP into real configurations. The Private Endpoint must be deployed in a valid VNet subnet and its connection state **Approved** by an authorized owner. If the target vault and VNet belong to different subscriptions/tenants, follow the required cross-scope approval workflow.

### 4.1. Private Endpoints Belong to the VNet, Not Each Pod

AKS pods and VMs route to the private endpoint IP; you do not create a Private Endpoint per Pod. One endpoint can serve multiple workloads on networks **with proper routing and DNS**, subject to tenant isolation and network segmentation policies. If VNets lack connectivity, being in the “same subscription” does not grant network reachability.

### 4.2. A Private Endpoint Does Not Turn Key Vault into an Internal VM

Key Vault remains a Microsoft-managed service. The Private Endpoint is simply a **private entry point**; you do not get a shell on Key Vault or control OS/server keys like a VM. Managed service quotas, API permissions, auditing, and Key Vault data-plane behaviors still apply.

### 4.3. Endpoint Configuration Does Not Replace Encryption or Auth

Private Link keeps traffic on the Azure backbone, yet you must still use **HTTPS/TLS with hostname validation** and authentication. Never change the SDK URL to `https://10.42.5.4` to “connect directly by IP”: TLS certificates and HTTP host headers bind to **`<vault>.vault.azure.net`**. Keep the **official vault FQDN** in the SDK and let DNS steer traffic onto the private route.

## 5. Private DNS: What Decides Whether Traffic Hits the Endpoint

A Private Endpoint alone is ineffective if app DNS still returns the public IP. For standard Azure Key Vault, the canonical private DNS zone is:

```text
privatelink.vaultcore.azure.net
```

Clients still call:

```text
https://<vault-name>.vault.azure.net
```

In a properly configured Private Link setup, the DNS chain typically looks like:

```text
kv-orders-prod.vault.azure.net
       CNAME
kv-orders-prod.privatelink.vaultcore.azure.net
       A record (private DNS linked to VNet)
10.42.5.4   <-- example PE private IP
```

Public DNS CNAME details may include additional layers or change over time in Azure; **what you must verify is that resolving the vault hostname from the workload VNet yields the private endpoint IP**, rather than hardcoding the CNAME chain.

### 5.1. Why Use `privatelink.vaultcore.azure.net`?

Microsoft recommends the dedicated private-link domain so private endpoints and private DNS integrate cleanly. **Never create a `vault.azure.net` private DNS zone arbitrarily**: it can shadow public records for other vaults and break DNS resolution. Likewise, never hardcode endpoint IPs in production `hosts` files—it breaks on IP changes/failover and complicates auditing.

### 5.2. DNS Components

| Component | Role | Common Mistake |
|---|---|---|
| Private DNS zone | Holds the private-link A record for the vault | Misspelling the zone name |
| A record | Maps vault alias → PE IP | Record pointing to a stale IP |
| Virtual Network link | Lets a VNet resolve the private zone | Forgetting to link the AKS/VM VNet |
| Private Endpoint DNS zone group | Manages DNS record registration for the PE | Missing zone group or pointing to wrong zone |
| Custom DNS forwarder/resolver | Handles enterprise/hybrid name resolution | Failing to forward the private-link zone |
| Workload DNS cache | JVM/OS/CoreDNS caches DNS results | Holding onto old IPs after cutover |

### 5.3. Always Test from the Workload Itself

Run `nslookup`/`dig` inside the actual AKS Pod, VM, or runner/VNet; **Azure Cloud Shell by default is not inside your application VNet**, so Cloud Shell resolving the public IP **does not mean your app's Private Endpoint is broken**. Do not test solely from a personal laptop whose VPN/DNS path differs from AKS.

### 5.4. Multiple Private Endpoints for One Vault

A single vault can have multiple Private Endpoints across different networks or regions. Managing **a single private DNS zone and its links/records** requires attention to how Azure writes A records, resolver contexts, and multiple resulting IPs. Sharing one Private DNS zone across multiple endpoints of the **same vault** across VNets can steer workloads to an unintended endpoint; design **DNS zones/resolution scopes** per topology instead of attaching the same zone group to every PE assuming it always picks the closest IP.

## 6. Designing for AKS, App Service, VMs, and On-Premises

### 6.1. AKS

```text
AKS Pod -> CoreDNS / node DNS -> private DNS resolution
        -> VNet route / firewall / NSG
        -> Private Endpoint IP -> Key Vault data plane
        -> Entra workload identity -> Key Vault RBAC
```

Verify both **DNS** and **identity**. A Pod with a valid federated identity whose DNS returns a public IP will hit a network denial. A Pod resolving the private IP without `Key Vault Secrets User` will still hit an authorization denial.

### 6.2. App Service / Azure Functions

App Service/Functions typically require **VNet Integration** (on supported plans/features) so outbound traffic from the app enters the VNet toward the Private Endpoint. **An inbound Private Endpoint for App Service** is a separate feature/object—it does not grant the app **outbound** access to Key Vault. Verify outbound routing, DNS settings, and plan/pricing constraints.

### 6.3. Azure VMs

A VM in a VNet linked to the DNS zone, with routing to the private IP and proper managed identity/RBAC, can read secrets via the vault FQDN. If the VM uses custom DNS, do not assume a private zone link automatically works with custom DNS; configure forwarders/resolvers.

### 6.4. On-Premises via VPN/ExpressRoute

An on-premises machine cannot reach `10.42.5.4` just because a Private Endpoint exists. It needs **private network connectivity** (site-to-site VPN/ExpressRoute or equivalent), routing, firewall allowances, and DNS resolving the vault alias to the private IP. Usually an **Azure DNS Private Resolver inbound endpoint** or a VNet DNS forwarder is needed for on-prem queries; **Azure-provided DNS virtual IP `168.63.129.16` cannot be queried directly from arbitrary on-premises machines**.

### 6.5. Peering / Hub-and-Spoke

VNet peering does not automatically propagate private DNS links to every spoke. If apps run in spokes, verify DNS forwarding and private zone visibility from each spoke, along with UDRs/firewalls/NSGs. With custom DNS in hub-and-spoke, link the zone to the DNS resolver/hub VNet and forward properly; with Azure-provided DNS, link the relevant VNets per design.

## 7. Choosing a Key Vault Protection Strategy

There is no single “most secure” configuration usable unconditionally for every workload. Balance **allowed network scope, operations, developer/CI mobility, compliance, and cost**.

### 7.1. Decision Matrix

| Need | Option to consider | Conditions |
|---|---|---|
| Demo/dev sandbox with no real secrets | Public endpoint with RBAC and firewall if needed | Manage lifecycle; never embed secrets in source |
| CI with fixed egress IP and no VNet yet | Public firewall/IP rules dedicated to a test vault | Allowed by policy and IP is manageable |
| VM in trusted subnet, public endpoint permitted | Service endpoint + VNet rules | Public logical endpoint is acceptable |
| Production requiring private-only data plane | **Private Endpoint + public network access Disabled** | DNS/routing/identity prepared beforehand |
| Hybrid datacenter reading Vault | Private Endpoint + VPN/ExpressRoute + DNS resolver | Routing and on-prem DNS must be tested |
| AKS using workload identity | Private Endpoint + private DNS + federated identity/RBAC | Networking and identity are two separate tasks |
| Multi-VNet/multi-region, DR | Per-topology private endpoints/resolvers/DNS | Design DNS/failover/cost and test every region |

### 7.2. Minimum Threat Model

Key risks:

1. **Internet-exposed data plane:** clients with valid tokens can attempt reads from external networks when public access is open.
2. **Credential compromise:** a principal with overly broad permissions leaks a token/key.
3. **DNS misrouting:** workload thinks it is on a private path but resolves a public IP, failing or taking an unintended path.
4. **Control-plane privilege escalation:** someone able to change RBAC or re-enable public access alters the security posture.
5. **Shared network blast radius:** every workload in the VNet can route to the PE even if not every workload should read secrets.
6. **Secret exfiltration via logs:** SDK/app logging accidentally prints `KeyVaultSecret.getValue()`.
7. **Single dependency outage:** DNS resolver, firewall, private endpoint, or identity outage prevents startup from fetching secrets.

Private Endpoints reduce the **network exposure surface**, but still require least privilege, governance, auditing, token lifecycle management, egress controls, and environment isolation.

### 7.3. Protect Against “Re-Enabling Public Access”

From a compliance standpoint, the requirement is rarely just “the vault is private today”. Use **Azure Policy** to audit or deny non-compliant network settings, restrict who can change network settings, require approvals/PIM, and alert if `publicNetworkAccess` is re-enabled. Resource locks can block deletes/edits depending on lock type and ARM operation, but do not replace **Policy + IAM** across all configuration changes.

## 8. Preparing Before Creating a Private Endpoint

Before deployment, align on the topology:

```text
Subscription: approved non-prod or production
Key Vault resource group: rg-security-...
Network resource group: rg-network-...
Key Vault: kv-orders-...
VNet: vnet-orders-...
PE Subnet: snet-private-endpoints
Private Endpoint: pe-kv-orders-...
Private DNS zone: privatelink.vaultcore.azure.net
Test workload: VM/AKS Pod in the target VNet
Identity: managed/workload identity granted data-plane role
```

### 8.1. Mandatory Decisions

- **Existing vault or greenfield?** If existing, who currently reads secrets over public access? You need a consumer inventory and migration plan.
- **Key Vault RBAC or access policy model?** Choose one model and know how permissions are assigned.
- **Which VNet/subnet?** Are there subnet policies, route tables, NSGs, or private endpoint network policies?
- **Which DNS resolver?** Azure-provided DNS, custom DNS appliance, Azure DNS Private Resolver, or on-prem forwarder?
- **Which hybrid/peered VNets?** Which paths must be tested?
- **How to roll back?** If disabling public access exposes a DNS failure, who is authorized to recover during the change window?
- **Owners and tags:** network owner, security owner, application owner, run ID, cost center.

### 8.2. Permissions Required to Deploy

Creating a **Private Endpoint**, modifying VNets/subnets, creating private DNS zones/links/zone groups, approving the target Key Vault connection, and assigning Key Vault RBAC may require **multiple distinct roles and scopes**. Never assume a principal with `Key Vault Secrets User` can create a PE, or that `Network Contributor` can read secrets.

### 8.3. Choosing a Subnet

The private endpoint subnet needs enough IP addresses and policy compliance; a Private Endpoint consumes a private IP and NIC in the VNet. Azure provides **network policies for Private Endpoints** to apply NSGs/UDRs as supported; never assume “NSGs never affect private endpoints” or “all UDRs apply automatically”. Verify exact subnet settings, effective routes, NSG rules, and platform behavior.

### 8.4. Define Success Criteria Before Changes

A “private-only” migration succeeds when:

1. Private Endpoint connection is **Approved**.
2. Workloads in the VNet resolve the vault FQDN to the right **private IP**.
3. Workloads complete HTTPS/TLS port 443 connections.
4. The authorized identity holds data-plane permissions and reads a test secret.
5. A principal with secret-read permissions calling from **outside the allowed network** cannot reach the data plane via the public endpoint.
6. Dashboards/alerts no longer depend on unapproved public egress.
7. CI/deployment/rotation/monitoring paths continue functioning.

## 9. Azure Portal: Controlled Private Endpoint Deployment

Portal UI layouts evolve; the logical sequence is:

1. Open **Key Vault → Networking** and document current **public network access, firewall rules, and private endpoint connections**.
2. Create or select a **Private Endpoint** from Networking/Private endpoint connections or Private Link Center.
3. Choose the right subscription, resource group, region, VNet, and subnet.
4. Select target **`Microsoft.KeyVault/vaults`**, the exact vault, and subresource **`vault`**.
5. Configure **Integrate with private DNS zone** pointing to `privatelink.vaultcore.azure.net` per your model.
6. Verify the created endpoint and NIC private IP; if manual approval is required, have the vault owner **Approve** it.
7. Check the zone A record and VNet link where workloads resolve DNS.
8. From a **VNet-integrated VM/Pod/App Service**, test FQDN resolution and secret retrieval using a test identity.
9. **Only after private-path tests PASS**, disable public network access during the change window.
10. Run positive + negative tests, record configuration/Azure Activity Log evidence, and update runbooks.

**Never disable public access in step 1 before a private path is verified**, especially on a vault actively serving deployment pipelines, app startups, or certificate rotation. If policy mandates private-only from creation, provision test workload/management paths first, then deploy the vault via IaC with dependency checks.

### 9.1. Private Endpoint Approval

When the private endpoint belongs to another team/owner, the connection may sit in **Pending** until the vault owner approves it. Do not mistake a created PE resource for an Approved service connection. A Rejected/Disconnected endpoint will not serve data-plane traffic even if DNS/IP entries remain.

### 9.2. DNS Zone Groups

A Private DNS Zone Group binds a PE to one or more supported private zones to manage records. For Key Vault, verify the record for the **vault alias/private IP** after the zone group takes effect. When recreating a PE or changing IPs, verify the zone group/records update cleanly and remove any stale manually created A records.

## 10. Azure CLI: Creating a Lab Key Vault Environment

The examples below use **Bash/Azure Cloud Shell** to create resources in a test subscription. **Do not run on production without change review.** Commands creating Azure resources can incur charges; choose valid, globally unique names and replace placeholders. **Cloud Shell only runs ARM APIs; private data-plane verification must run from inside the target VNet.**

### 10.1. Set Variables and Select Subscription

```bash
az login
az account set --subscription "<non-production-subscription-id>"
az account show --output table

REGION="southeastasia"
RG="rg-kv-private-lab"
VNET="vnet-kv-private-lab"
SUBNET="snet-private-endpoints"
VAULT="<globally-unique-key-vault-name>"
PE="pe-kv-lab"
CONN="conn-kv-lab"
ZONE="privatelink.vaultcore.azure.net"
LINK="link-vnet-kv-lab"
```

Never put private keys, secret values, or Azure account tokens into shell command history or CI logs. Use distinct names across dev/staging/prod and verify account/subscription before any destructive operation.

### 10.2. Create Resource Group and VNet/Subnet

```bash
az group create \
  --name "$RG" \
  --location "$REGION" \
  --tags environment=lab purpose=keyvault-private-endpoint

az network vnet create \
  --resource-group "$RG" \
  --name "$VNET" \
  --location "$REGION" \
  --address-prefixes 10.42.0.0/16 \
  --subnet-name "$SUBNET" \
  --subnet-prefixes 10.42.5.0/24
```

Lab CIDRs are examples; **never use overlapping ranges with peered VNets or on-prem networks**. Configure NSGs/UDRs/private endpoint network policies per your real topology and never skip subnet reviews.

### 10.3. Create Key Vault with Azure RBAC Data Plane

```bash
az keyvault create \
  --resource-group "$RG" \
  --name "$VAULT" \
  --location "$REGION" \
  --enable-rbac-authorization true

VAULT_ID=$(az keyvault show \
  --resource-group "$RG" \
  --name "$VAULT" \
  --query id -o tsv)

echo "Target vault resource ID:"
echo "$VAULT_ID"
```

**The lab keeps initial networking defaults so the PE can be set up first**; do not assume a newly created vault is already private-only. Key Vault enables soft delete by default; production typically requires purge protection and approved policies. **Once enabled, purge protection cannot be disabled arbitrarily and affects test vault cleanup/lifecycle**: plan retention and cleanup before enabling it.

### 10.4. Verify Vault ID and Config

```bash
az keyvault show \
  --resource-group "$RG" \
  --name "$VAULT" \
  --query "{id:id,publicNetworkAccess:properties.publicNetworkAccess,networkAcls:properties.networkAcls,enableRbacAuthorization:properties.enableRbacAuthorization}" \
  --output json
```

CLI/REST fields can vary by Azure CLI/API version; if a field returns null, check `az keyvault show --help` and actual ARM resource properties rather than guessing values. Always check the **actual state** before altering network rules.

## 11. Azure CLI: Creating a Private Endpoint for Key Vault

### 11.1. Create PE Targeting Subresource `vault`

```bash
az network private-endpoint create \
  --resource-group "$RG" \
  --name "$PE" \
  --location "$REGION" \
  --vnet-name "$VNET" \
  --subnet "$SUBNET" \
  --private-connection-resource-id "$VAULT_ID" \
  --group-id vault \
  --connection-name "$CONN"
```

This requires appropriate Network and Key Vault permissions. The **connection name** identifies the PE-to-vault link object, not a secret; never pass `--group-id managedHSM` for a standard Key Vault.

### 11.2. Check Connection State

```bash
az network private-endpoint show \
  --resource-group "$RG" \
  --name "$PE" \
  --query "{id:id,connections:privateLinkServiceConnections,manualConnections:manualPrivateLinkServiceConnections}" \
  --output json
```

Inspect `privateLinkServiceConnectionState.status` where present. Expect **Approved** before starting DNS/TLS validation. If pending on another owner, request approval via Key Vault → Networking/Private endpoint connections or the corresponding management API; never try to force approval without permissions.

### 11.3. Check Private IP

```bash
az network private-endpoint show \
  --resource-group "$RG" \
  --name "$PE" \
  --query "customDnsConfigs" \
  --output json
```

Properties expose `ipAddresses`/FQDN depending on API version. You can also inspect the PE's **network interface** in Portal/CLI to verify the actual IP. **Never hardcode the output IP into the Java SDK**—use private DNS.

## 12. Azure CLI: Creating Private DNS Zone, VNet Link, and Zone Group

### 12.1. Create Zone and Link VNet

```bash
az network private-dns zone create \
  --resource-group "$RG" \
  --name "$ZONE"

VNET_ID=$(az network vnet show \
  --resource-group "$RG" \
  --name "$VNET" \
  --query id -o tsv)

az network private-dns link vnet create \
  --resource-group "$RG" \
  --zone-name "$ZONE" \
  --name "$LINK" \
  --virtual-network "$VNET_ID" \
  --registration-enabled false
```

A Private DNS link on one VNet **does not automatically propagate to every peered VNet**. With hub-and-spoke or custom DNS, map the DNS query path and create all required links/forwarding rules.

### 12.2. Create DNS Zone Group on the Endpoint

```bash
ZONE_ID=$(az network private-dns zone show \
  --resource-group "$RG" \
  --name "$ZONE" \
  --query id -o tsv)

az network private-endpoint dns-zone-group create \
  --resource-group "$RG" \
  --endpoint-name "$PE" \
  --name "default" \
  --private-dns-zone "$ZONE_ID" \
  --zone-name "keyvault-private-zone"
```

This is Azure CLI syntax for a **PE DNS zone group** on compatible CLI versions; check `--help` if CLI flags change. The zone group manages A records automatically; avoid creating duplicate manual records when a zone group handles them.

### 12.3. Verify A Record and Zone Link

```bash
az network private-dns record-set a list \
  --resource-group "$RG" \
  --zone-name "$ZONE" \
  --output table

az network private-dns link vnet list \
  --resource-group "$RG" \
  --zone-name "$ZONE" \
  --output table
```

Seeing the A record is not enough; you must also **resolve from the workload** because custom DNS, NAT, VNet peering, or forwarders might bypass this zone. Only disable public access after positive tests pass.

## 13. Switching to “Private-Only” and Configuring the Firewall

Once the PE connection is Approved, private DNS resolves properly, and the workload reads a test secret with an authorized identity, restrict network access per policy:

```bash
az keyvault update \
  --resource-group "$RG" \
  --name "$VAULT" \
  --public-network-access Disabled

az keyvault show \
  --resource-group "$RG" \
  --name "$VAULT" \
  --query "properties.publicNetworkAccess" \
  --output tsv
```

**Never run this on a production vault without a rollback runbook and consumer inventory.** Disabling public network access closes the public data-plane route; applications must traverse an allowed private path. Azure Resource Manager management access must still be protected via IAM/Policy.

### 13.1. Firewall defaultAction Deny While Public Access Is Enabled

If policy allows a **public endpoint with an allowlist** instead of private-only, one pattern is:

```bash
# Choose this model ONLY when public access is explicitly permitted.
az keyvault update \
  --resource-group "$RG" \
  --name "$VAULT" \
  --public-network-access Enabled \
  --default-action Deny \
  --bypass None

# In an authorized environment, add public IPv4/CIDR
# or VNet service-endpoint rules using the corresponding commands.
```

“Public allowed by firewall” and “private-only” are **two different modes**. Never copy `Enabled` into a private-only production script as a “quick fix” without approval.

### 13.2. IP Allowlists Require Valid Public IPv4 Addresses

Key Vault network ACL IP rules target **supported public IPv4 ranges** with rule-count limits; never add a Pod/VM's **RFC1918 private IP** to the IP allowlist expecting it to replace a Private Endpoint. For clients behind NAT/firewalls, determine the **actual public egress IP** when using public allowlists. If egress changes, rules go stale.

### 13.3. Service Endpoints Are a Different Option

To use the **`Microsoft.KeyVault` service endpoint**, enable the service endpoint on the subnet and add a **VNet rule** to the Key Vault network ACL when firewall mode applies. Do not confuse this with creating a Private Endpoint or assume service endpoints create a private DNS A record.

### 13.4. Trusted Microsoft Services Bypass

Depending on network mode, Key Vault supports `bypass AzureServices` for a Microsoft-defined set of **trusted Microsoft services**; **not every Azure service** (including arbitrary App Service/AKS/CI runners) is on that list. Never assume Azure DevOps hosted agents or Cloud Shell bypass the firewall. When **public network access is Disabled**, verify platform-supported exceptions and **never build a dependency on an unverified public bypass**.

### 13.5. Procedure to Avoid Locking Yourself Out

Before cutover, ensure:

- A **bastion/test VM or workload inside the VNet** with verified DNS, routing, TLS, and RBAC.
- An approved ARM administrative account/principal to execute rollback.
- Monitoring and secret rotation systems already routing over the private path.
- CI/CD runners with VNet access or a dedicated deployment workflow.
- Clear change window, validation script, and decision maker.

After cutover, run both a **positive request** (inside the VNet with the right identity) and a **negative request** (outside the network using an identity that holds secret-read permission). The negative test proves the firewall blocks access even with an authorized token.

## 14. Microsoft Entra ID and Key Vault Authorization

Key Vault accepts **Microsoft Entra access tokens** for the calling workload/service identity. When running on AKS, App Service, VMs, Azure Functions, or CI, prefer **managed identity/workload identity** wherever supported by environment and SDK. Never embed vault access keys or long-lived client secrets in source code.

### 14.1. Two Data-Plane Permission Models

| Model | How permissions are granted | Notes |
|---|---|---|
| **Azure RBAC authorization** | Assign built-in/custom data-plane roles at appropriate scopes | Centralized Azure RBAC governance; role propagation may lag |
| **Vault access policies** | Grant permissions to principals directly on Key Vault (legacy model) | Different governance; restrict ARM rights that allow self-modifying access policies |

Each vault enforces **its configured permission model**. When `enableRbacAuthorization=true`, do not expect a legacy `access policy get` entry to authorize requests. Switching models on production can disrupt live apps; audit permissions first, plan migration, and use IaC/change control.

### 14.2. Common Built-In Roles

| Role | Used for | Do not assume |
|---|---|---|
| **Key Vault Secrets User** | Workloads needing to read secret values at scope | Does not grant full vault admin rights |
| **Key Vault Secrets Officer** | Manage secret data plane (add/edit/delete) | Usually unneeded for read-only apps |
| **Key Vault Crypto User** | Cryptographic operations on keys per role definitions | Does not inherently read all secrets |
| **Key Vault Certificates Officer** | Manage certificates per defined permissions | Does not automatically permit arbitrary private cert byte extraction |
| **Key Vault Reader** | Read info/metadata per role | Does not grant reading secret values |
| **Key Vault Administrator** | Broad data-plane management | Never grant to ordinary workloads |

Role definitions and exact permissions can evolve or include custom roles. Never infer a role from its name alone; inspect **`dataActions`** and run positive/negative tests on a test vault.

### 14.3. Grant Secret Read Permissions to a Workload

```bash
# Object ID of the test managed identity / service principal.
# Do not pass a user email when the script expects a principal object ID.
PRINCIPAL_OBJECT_ID="<test-workload-principal-object-id>"

az role assignment create \
  --assignee-object-id "$PRINCIPAL_OBJECT_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Key Vault Secrets User" \
  --scope "$VAULT_ID"
```

**A role assignment does not replace private DNS or network firewalls.** It only authorizes the principal. If a new assignment isn't effective yet due to propagation/caching, wait within a bounded window and inspect errors; never add `Owner` or `Key Vault Administrator` to bypass a 403.

### 14.4. Least Privilege at Vault or Secret Scope?

Roles can be assigned at vault scope or supported child-resource scopes. Choose the **narrowest practical scope** that remains maintainable. When multiple apps have independent secrets and strict boundaries, consider **separate vaults per app/environment** rather than packing every secret into one vault with broad roles. Separating networking, identity, lifecycle, and auditing often matters more than naming conventions alone.

### 14.5. Managed Identity Is Not Magic

The application must fetch tokens from the exact intended identity. With a **system-assigned managed identity**, lifecycle is tied to the resource; with a **user-assigned managed identity**, configure the client ID/assignment in the runtime. On AKS Workload Identity, you also need a federated credential and Kubernetes service account. A pod holding a valid identity token that **lacks a role on the target Key Vault** will still fail.

## 15. Verifying the Private Path with DNS, TCP, and HTTPS

The most efficient troubleshooting order is **DNS → route/connectivity → TLS → token → Key Vault authorization**. Never start by editing RBAC while DNS still resolves a public IP.

### 15.1. Basic Commands from a Linux Container/VM in the VNet

```bash
VAULT="<globally-unique-key-vault-name>"
FQDN="$VAULT.vault.azure.net"

# If the image includes dnsutils/bind-tools:
nslookup "$FQDN"

# Or check the OS resolver:
getent hosts "$FQDN"

# Check TLS/HTTP without printing bearer tokens/secrets:
curl --connect-timeout 5 --max-time 15 -v \
  "https://$FQDN/" \
  -o /dev/null
```

An HTTP `401`, `403`, or `404` on the root path still confirms DNS/TCP/TLS reached an HTTP endpoint; it **does not prove secret GET is authorized**. On the TLS path, inspect hostname/certificate chain and connection target without logging credentials.

### 15.2. PowerShell from a Windows Test VM

```powershell
$vault = "<globally-unique-key-vault-name>"
$hostName = "$vault.vault.azure.net"

Resolve-DnsName -Name $hostName
Test-NetConnection -ComputerName $hostName -Port 443
```

Check `RemoteAddress` in the TCP test: expect the **private endpoint IP** for private-only workloads. Note that if an HTTP/TLS proxy is enforced, OS/browser/curl and Java may route through different proxies; verify the connection path from the **actual application process**.

### 15.3. Check DNS at Each Vantage Point

| Vantage point | Expected when private DNS is right | If wrong |
|---|---|---|
| VM in same VNet as PE | FQDN resolves to private IP | Zone link, A record, or resolver |
| AKS Pod | FQDN → private IP via CoreDNS/forwarding | CoreDNS stub domains, custom DNS |
| VNet-integrated App Service | FQDN → private IP, outbound to PE | VNet integration and DNS/routing |
| On-prem via VPN | FQDN → private IP, private route over VPN | DNS forwarder/Private Resolver, routing |
| Laptop outside VPN | May see public endpoint or no private route | Expected to be blocked from data plane when public disabled |

Never use ICMP `ping` as the sole check: many managed service endpoints drop ping, while HTTPS 443 is the actual protocol.

### 15.4. DNS Caching in JVMs and Containers

After cutover, OS, CoreDNS, JVM, or HTTP connection pools may cache old DNS records or connections briefly. Review TTL/resolver settings and perform a **controlled** application restart if needed—never disable DNS caching system-wide or mass-restart all production pods at once. Account for downtime and connection churn.

## 16. Testing the Actual Key Vault Data Plane

A DNS test does not verify tokens or RBAC. Once `nslookup` returns the private IP:

```bash
# Run on a VM/Pod/runner inside the VNet logged in with an authorized identity.
az keyvault secret show \
  --vault-name "$VAULT" \
  --name "orders-db-password" \
  --query id \
  --output tsv
```

`secret show` **actually calls the data plane** and fetches the secret response; `--query id` limits output to avoid printing the secret value in the terminal. Run this only with an authorized identity on an existing secret. Never use production secrets in labs; create safe **synthetic** fixtures.

### 16.1. Distinguishing Role Tests from Network Tests

Build a test matrix:

| Location / identity | DNS / route connectivity | Data-plane role | Expected |
|---|---|---|---|
| VNet VM + test reader | Private IP reachable | Secrets User | **Allow** |
| VNet VM + no-role identity | Private IP reachable | None | **Deny authorization** |
| Laptop outside VNet + reader | Public path (private-only vault) | Secrets User | **Deny network** |
| VNet VM + wrong tenant token | Private IP reachable | Invalid | **Deny auth** |
| App Service without VNet integration + reader | No private path | Secrets User | **Deny network/connection** |
| Admin via ARM outside VNet | Separately controlled ARM API | ARM permission | Can manage config per IAM/Policy |

**Network negative tests should use a principal that already has read permission in a test vault**; if it also lacks a role, a 403 does not prove whether the firewall blocked it. Never copy real tokens/secrets onto untrusted machines for this test; use dedicated test identities in controlled environments.

### 16.2. Testing Without Exposing Secrets

A test can assert a **known fixture value** in memory or compare length/checksum without **logging the raw secret**. CI artifacts are often broadly readable; never print default `az keyvault secret show` JSON since it includes `value`. In production, fetching secrets by ID may appear in traces; redact appropriately.

### 16.3. If the Secret Does Not Exist Yet

`404 SecretNotFound` once networking and auth pass is a **different** signal from `403 ForbiddenByFirewall`. Never create a missing secret using an Officer identity just to make a read test pass if you are testing least privilege. Separate the **fixture setup identity** (write rights) from the **application read identity** (get only).

## 17. Java Azure SDK: Reading Secrets Over a Private Endpoint

With the **Azure SDK for Java**, a secret-reading client uses **`SecretClient`** from `azure-security-keyvault-secrets` and a `TokenCredential` from `azure-identity`. The URL in the SDK **remains the public vault FQDN**; runtime DNS resolves the private route.

### 17.1. Maven Dependencies

```xml
<!-- POM fragment; declare a project-appropriate BOM version. -->
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>com.azure</groupId>
      <artifactId>azure-sdk-bom</artifactId>
      <version>${azure.sdk.bom.version}</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>

<dependencies>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-security-keyvault-secrets</artifactId>
  </dependency>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-identity</artifactId>
  </dependency>
</dependencies>
```

`${azure.sdk.bom.version}` is a **Maven property to declare**, not a pre-verified version. Pin the Azure SDK BOM via dependency management and verify runtime/JDK compatibility and release notes before upgrading.

### 17.2. Java Code Reading a Secret

```java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.SecretClientBuilder;
import com.azure.security.keyvault.secrets.models.KeyVaultSecret;

import java.net.URI;
import java.util.Objects;

public final class KeyVaultSecretReader {
    public static void main(String[] args) {
        String vaultUrl = Objects.requireNonNull(
                System.getenv("AZURE_KEY_VAULT_URL"),
                "AZURE_KEY_VAULT_URL is required");

        // Keep https://<vault>.vault.azure.net; never use the PE IP.
        URI uri = URI.create(vaultUrl);
        if (!"https".equalsIgnoreCase(uri.getScheme())
                || uri.getHost() == null
                || !uri.getHost().endsWith(".vault.azure.net")) {
            throw new IllegalArgumentException("Unexpected vault URL");
        }

        SecretClient client = new SecretClientBuilder()
                .vaultUrl(vaultUrl)
                .credential(new DefaultAzureCredentialBuilder().build())
                .buildClient();

        KeyVaultSecret secret = client.getSecret("orders-db-password");

        // Use secret value in memory only for authorized app logic.
        String value = secret.getValue();
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Secret value is missing");
        }
        System.out.println("Secret retrieved successfully");
        // Never print(value) or write it to traces/logs/metrics.
    }
}
```

This is an **illustrative program**. Checking the hostname suffix only guards against malformed URLs—it is **not a vault allowlist or defense against arbitrary host abuse**: production must validate the **exact expected vault resource/FQDN** from trusted configuration. The SDK never needs the private endpoint IP or private DNS zone name directly.

### 17.3. Local Developer and Azure Identities Can Differ

`DefaultAzureCredential` is a chain of credential providers. On a developer laptop, it may pull credentials from Azure CLI, IDE, or environment variables; on AKS/App Service/VMs, it uses workload/managed identity per supported configuration. **A successful run on a laptop does not verify identity or networking inside a production pod.** In environments requiring an explicit identity, configure the credential provider/client ID explicitly and verify non-secret principal/tenant/scope details.

### 17.4. How the SDK Connects Over the Network

Running inside an AKS Pod, this code:

1. Resolves the vault FQDN via CoreDNS to the PE private IP.
2. Opens TLS 443 with a valid hostname.
3. Obtains a Microsoft Entra token via workload identity.
4. Sends `GET secret` with the bearer token to the vault.
5. Receives `403` if lacking the data-plane role even though DNS succeeded.

Because these steps are independent, Java exceptions must be classified cleanly; **never** catch all errors and “retry against the public endpoint”.

## 18. Handling Java SDK Errors Without Exposing Secrets

In production apps, distinguish:

| Error | Likely cause | Troubleshooting direction |
|---|---|---|
| `UnknownHostException` | DNS failed to resolve | Check private DNS zone/links/CoreDNS |
| `ConnectTimeoutException` | Route/NSG/firewall/PE unreachable | Check TCP 443 from runtime |
| `SSLHandshakeException` | Truststore/hostname/TLS proxy issue | Never disable certificate verification |
| `ClientAuthenticationException` | Failed to obtain token/expired/wrong tenant | Check managed identity/federation |
| `403 ForbiddenByFirewall` | Network ACL/public-disabled/bypassing PE | Check private route; do not grant broad roles |
| `403 Forbidden/AccessDenied` | Insufficient RBAC/access policy | Check principal, dataActions, propagation |
| `404 SecretNotFound` | Wrong name/version/vault or missing secret | Check fixture/version/soft-delete |
| `429 TooManyRequests` | Throttling | Bounded SDK backoff/retries, caching |
| `5xx/transient` | Transient service/network failure | Bounded retries, circuit breaker as needed |

Exact exception names and error codes vary by Azure SDK version and service response. **A bare `403` is not enough to distinguish network vs. IAM**; inspect **sanitized error codes/inner statuses** alongside independent DNS/IP/identity checks.

### 18.1. Java Snippet Classifying HTTP Errors

```java
import com.azure.core.exception.HttpResponseException;
import com.azure.core.exception.ResourceNotFoundException;
import com.azure.identity.CredentialUnavailableException;
import com.azure.core.exception.ClientAuthenticationException;

try {
    var secret = client.getSecret("orders-db-password");
    // Use secret.getValue() in authorized business flow; never log.
} catch (ResourceNotFoundException ex) {
    System.err.println("Requested secret does not exist");
} catch (ClientAuthenticationException ex) {
    System.err.println("Entra credential authentication failed");
} catch (CredentialUnavailableException ex) {
    System.err.println("No supported credential available");
} catch (HttpResponseException ex) {
    int status = ex.getResponse().getStatusCode();
    System.err.println("Key Vault HTTP status=" + status);
    // Never log full response body if it risks exposing secrets/PII.
    throw ex;
}
```

This is a **method-body snippet** assuming `client` from Section 17. Verify the exact exception hierarchy and catch ordering against your SDK version and Java compiler. The Azure SDK can wrap network exceptions; production apps should use tested **structured error classification** rather than fragile message string parsing.

### 18.2. Retries Do Not Fix Broken DNS or Wrong RBAC

If the vault returns 403 due to network denial, retrying 100 times only adds load. If DNS points to a public IP, an SDK retry will not create a private zone link. **Separate permanent configuration errors** from transient 429/5xx errors; use bounded backoff, caps, and retry metrics. Never fall back to the public network to “self-heal” a private connection failure.

### 18.3. Secret Caching and Rotation

Once a secret read succeeds, the value can be cached in the JVM. During rotation, workloads need to refresh per TTL/version policy; during a temporary vault outage, a security-approved **stale credential** grace window may apply. Never cache secrets indefinitely or write plaintext secrets to disk/logs to avoid Key Vault dependency.

## 19. AKS Workload Identity + Key Vault Private Endpoint

A common production design:

```text
AKS namespace: orders-prod
       |
Kubernetes ServiceAccount (workload identity annotation)
       |
Pod with projected service account token
       |
       +--> Microsoft Entra token exchange
       |    (federated identity credential)
       |
       +--> Azure DNS / CoreDNS -> PE private IP
       |
       v
Key Vault SecretClient.getSecret()
       |
       +--> Data plane authorization: Key Vault Secrets User
       |
       v
Application receives secret over HTTPS/TLS
```

### 19.1. Necessary and Sufficient Conditions

| Component | Must verify |
|---|---|
| AKS/OIDC issuer | Workload Identity enabled and properly configured |
| Federated credential | Issuer, subject, and audience match service account and identity |
| Workload Pod | ServiceAccount/labels/env match supported SDK integration |
| Identity | Azure client ID/tenant and exact principal |
| Key Vault | RBAC model + `dataActions` and appropriate scope |
| VNet | Route from Pod/node to Private Endpoint |
| DNS | Vault FQDN from Pod resolves to private IP |
| Policy | Network/identity/tenant boundaries and safe logging |

**Attaching a Kubernetes ServiceAccount to a Pod does not automatically grant Key Vault access.** Federated identity and data-plane RBAC must be configured separately.

### 19.2. Probe Inside a Pod, Not Just from a Jumpbox

A jumpbox in the VNet might resolve DNS fine while CoreDNS in AKS uses a different custom forwarder. Test using an **ephemeral debug Pod** in the target namespace/network policy, or via controlled application telemetry. Never mount a production service account token into an untrusted debug Pod.

### 19.3. Azure Key Vault Secrets Store CSI Driver

On AKS, the **Secrets Store CSI Driver + Azure provider** can mount/sync secrets into Pods as supported, using workload/managed identity. In that case:

- The network path **from the node/provider component** to the private endpoint must work.
- The identity used by the provider needs corresponding get/list rights.
- Secrets mounted in the Pod have distinct lifecycle, permission, and rotation semantics.
- Some setups sync into Kubernetes Secrets, bringing **Kubernetes RBAC, etcd encryption, and deletion/rotation responsibilities**.

Never assume a mounted secret refreshes instantaneously just because the Key Vault value rotated. Verify **refresh intervals, app reload behavior, and mount/update errors** per CSI driver/provider version.

### 19.4. Split-Horizon DNS Across Multiple Clusters

If clusters A and B reside in two different VNets sharing one vault, their Private Endpoints can have different IPs. Design **DNS zone linking and resolution scopes** per cluster/region rather than creating one static record for every environment. Run positive/negative tests from **each cluster** after DNS changes.

## 20. App Service and Azure Functions Key Vault References

App Service/Functions support **Key Vault references** in application settings per plan/runtime support. A reference points to a secret ID/URI rather than embedding the value in configuration; the platform resolves the reference using the configured identity.

### 20.1. Example Reference in an App Setting

```text
DB_PASSWORD=@Microsoft.KeyVault(SecretUri=https://kv-orders-prod.vault.azure.net/secrets/orders-db-password/)
```

This is illustrative syntax for an App Service/Functions **Key Vault reference**—not a general Java property syntax. Check your platform documentation for URI/versioning, refresh, and caching behavior.

### 20.2. Why Can References Fail When the Vault Is Private-Only?

If App Service lacks outbound VNet Integration or DNS does not resolve the vault hostname to the private endpoint, the platform cannot fetch the secret. Even with the right managed identity and Key Vault role, requests can be blocked by the firewall. Check:

1. App Service plan supports outbound VNet Integration.
2. App VNet/subnet integration and route to the PE.
3. Private DNS zone/link and custom DNS settings.
4. Key Vault reference identity (system-assigned or user-assigned per config).
5. RBAC/data-plane permissions and secret/version existence.
6. Platform reference refresh/cache and application restart behavior.

### 20.3. App Service Inbound PE Is a Different Story

A private endpoint **for calling into App Service** secures inbound HTTP traffic to the app. It **does not replace** outbound VNet Integration needed for the app to read Key Vault. Both paths must be designed separately:

```text
Client -> App Service private inbound endpoint
                    |
             App Service runtime
                    |
          outbound VNet Integration
                    |
          Key Vault private endpoint
```

### 20.4. Deployment Slots and Environments

Staging slots can have different identities, app settings, Key Vault references, and VNet settings from production slots. Before swapping, check **slot-specific settings/identities/configs** so staging never accidentally reads production secrets and production never loses secrets on switchover. Never reuse production vault secrets for dev/test simply because the URI is convenient.

## 21. Azure DevOps / GitHub Actions and Deployment Networking

CI may need Key Vault access for secrets, certificates, or deployments. **Hosted runners are not inside your VNet by default.** If a vault is private-only, a pipeline running without private connectivity may receive `ForbiddenByFirewall` even with a valid OIDC/service principal role.

### 21.1. Options

| CI executor | Private Key Vault access | Notes |
|---|---|---|
| Default public hosted runner | Usually lacks a direct PE path | Do not rely on public IP allowlists for private-only vaults |
| Self-hosted runner inside VNet | Can reach PE | Secure runner, DNS, identity, and egress |
| Managed runner with private-network integration (if supported) | Possible | Verify service/plan/feature and routing |
| Job running inside AKS/private VM | Possible | Least privilege on service account/managed identity |
| Standard Cloud Shell | Does not prove a private path | Runs ARM operations, but data plane may be blocked |

### 21.2. Separate Deployment Config from Secret Retrieval

A pipeline deploying resources via **ARM** does not necessarily need to read secret values; if the app uses **managed identity** and Key Vault references/SDK, grant the pipeline rights to update infrastructure without reading secrets. That minimizes principals needing access to the private data-plane network. Only pipelines that genuinely must export/inject secrets should get approved data-plane access.

### 21.3. OIDC Federation Is Identity Security, Not a VNet

OIDC-based CI credentials eliminate long-lived client secrets, but **they do not open a network route** to a PE. A pipeline with a valid token still fails if DNS or the network path is wrong. Design both layers independently and test separately.

## 22. Controlling Firewalls, NSGs, and Routes to the Private Endpoint

A Private Endpoint places a private IP in your VNet. NSGs, UDRs, and network appliances can sit on the path depending on network policies and topology. For both the PE subnet and source subnets, verify **effective routes**, VNet peering, firewall inspection, and active policies.

### 22.1. Checking Routes and ACLs

When TCP 443 times out even though DNS is right:

1. Verify **PE connection Approved** and NIC private IP.
2. Check the workload's source IP/subnet.
3. Check **route tables/UDRs**, firewalls/NVAs, and return paths.
4. Check **NSG rules** on subnets/NICs enforced under network policies.
5. Check peering/VPN if cross-VNet or on-premises.
6. Check outbound proxies; an HTTP proxy can send requests to the internet instead of the PE.
7. Confirm there is no IP overlap with on-prem/VNets.
8. Separate DNS faults (wrong IP) from network faults (right IP, cannot connect).

### 22.2. Never Open Every Path Because a Test Failed

A dangerous “fix” is stripping all NSG/firewall rules or enabling public network access to “clear the 403”. That can violate compliance and mask the real cause. Instead, open the **minimal required path** for exact source, destination private IP, port 443, routes, and identity.

### 22.3. Multi-Region Sources

A PE in a VNet in region A can be called from VNet B over valid peering/connectivity, though latency, network cost, and failure domains differ. For DR, plan private endpoints/DNS/topologies in the standby region and test failover. **Key Vault DNS does not automatically route workloads to the “nearest private endpoint” just because multiple PEs exist.**

## 23. Public Firewall IP Rules and Service Endpoints: Examples and Pitfalls

### 23.1. Illustrative IP Rule

When a public endpoint with firewall rules is permitted:

```bash
# Example only for a test runner's static public IPv4 egress.
# Replace with an IP/CIDR verified by your network team.
az keyvault network-rule add \
  --resource-group "$RG" \
  --name "$VAULT" \
  --ip-address "<approved-public-ipv4-or-cidr>"
```

Never enter private IPs from `10.0.0.0/8`, `172.16.0.0/12`, or `192.168.0.0/16` here; Azure Key Vault firewall rules target public IPv4 addresses/ranges. If a client sits behind NAT, specify the **actual public egress address**, not the private source IP.

### 23.2. Service Endpoints on a Subnet

Conceptual pattern:

```bash
# Only when using service endpoint/firewall mode (not PE-only).
az network vnet subnet update \
  --resource-group "$RG" \
  --vnet-name "$VNET" \
  --name "<application-subnet>" \
  --service-endpoints Microsoft.KeyVault

APP_SUBNET_ID="<full-application-subnet-resource-id>"
az keyvault network-rule add \
  --resource-group "$RG" \
  --name "$VAULT" \
  --subnet "$APP_SUBNET_ID"
```

`--subnet` takes the **ARM resource ID**, obtained from `az network vnet subnet show --query id` for the actual subnet. Enabling a service endpoint on an **application subnet** differs from placing a **Private Endpoint** in its subnet; in private-only designs, use the approved PE path rather than treating service endpoints as an ad-hoc workaround.

### 23.3. Trusted Services Bypass Is Not Allow-All for Cloud Services

When policy restricts public traffic, use the trusted services bypass only for **specific supported features/permissions**. An app running in an Azure VM or third-party SaaS is not automatically on the trusted services list, and Microsoft maintains that list per service. Check official docs for each integration rather than relying on bypass without testing.

### 23.4. Azure Network Security Perimeter (If Applicable)

Some Azure resources support **Network Security Perimeter (NSP)** depending on feature, region, and tier. NSP is not another name for Private Endpoint, and interactions among public network access, private endpoints, and perimeter rules require separate evaluation. This lesson focuses on **Key Vault firewalls and Private Link**; never copy NSP guidance from another service if APIs/configs are incompatible.

## 24. Keeping Secrets Protected in Operations

No private network helps if the application itself writes secret values into logs, traces, or public error responses.

### 24.1. Never Log Values

Anti-pattern:

```java
var secret = client.getSecret("orders-db-password");
System.out.println("DB password: " + secret.getValue()); // DO NOT do this
```

Replace with:

```java
var secret = client.getSecret("orders-db-password");
System.out.println("Key Vault secret retrieved; name=" + secret.getName());
// Pass the value only to authorized components in memory.
```

Even secret names can reveal operational details; classify logs, enforce retention, and restrict log readers. Never push full exception bodies, tokens, or authorization headers into public logs.

### 24.2. Least Privilege per Workload

A web API that only reads `orders-db-password` does not need vault-wide `set/delete/purge`. A certificate rotation service needs a different scope/role; never share identities across deployment pipelines, Java APIs, and security administrators.

### 24.3. Protect Control-Plane Changes

For private-only requirements:

- Azure Policy to audit/deny vaults with non-compliant public access.
- PIM/approvals for principals allowed to edit networking/RBAC.
- Azure Activity Log monitoring `Microsoft.KeyVault/vaults/write`, role assignments, and private endpoint changes.
- Prevent routine CI pipelines from modifying `publicNetworkAccess` unnecessarily.
- Deploy configurations via IaC with diff reviews and drift detection.

### 24.4. Rotation and Private Access

A secret rotation workflow may run from Azure Automation, Functions, Logic Apps, or another service. If the vault is private-only, the workflow needs a **valid private network path or officially supported integration**, plus data-plane write permissions. Never assume an “Azure-managed service” always bypasses network rules. Whenever networking changes, test the **rotation process** as well as app reads.

### 24.5. Never Let Backups or Tests Open Security Holes

A backup script for secrets/keys running from a laptop or external CI runner will break after private cutover. Never toggle public access on temporarily in a cron job without auditing. Move backup/restore jobs onto a VNet-connected runner, or use a policy-compliant backup strategy. Note that Key Vault backup/restore operations have **region/subscription/permission constraints**, and backup blobs themselves are sensitive artifacts.

## 25. Azure Monitor: Auditing Networking, Permissions, and Key Vault Behavior

Production Key Vaults require visibility into **data-plane access, control-plane config changes, network connectivity, and consuming apps**. Some signals come from Azure Monitor/Activity Log, while others must be instrumented by the application.

### 25.1. Categorizing Monitoring Sources

| Source | Example info | Insufficient to prove |
|---|---|---|
| **Key Vault platform metrics** | API latency, availability/request volume/throttling per supported metric | Does not show whether the app used the secret properly |
| **Key Vault diagnostic logs** | Audit operations, outcomes/identity metadata in enabled categories | Does not log every Java app logic decision |
| **Azure Activity Log** | Management changes to vault resource/network/RBAC/PE | Does not replace data-plane auditing |
| **Private Endpoint/network diagnostics** | Connection state, IP, reachability | Does not prove RBAC Secrets User |
| **DNS/VM/AKS/App Service telemetry** | Resolver answers, TLS/connection latency/errors | Does not prove secret existence |
| **Application metrics** | Secret fetch success, 403/429s, cache age, rotation refresh | Must never contain secret values |

### 25.2. Discover Metric Definitions Instead of Guessing

```bash
az monitor metrics list-definitions \
  --resource "$VAULT_ID" \
  --output table

az monitor diagnostic-settings categories list \
  --resource "$VAULT_ID" \
  --output table

az monitor diagnostic-settings list \
  --resource "$VAULT_ID" \
  --output json
```

Metric names, log categories, and Log Analytics tables depend on configuration and service version. **Never write KQL against a non-existent table and conclude there are no audit logs.** Diagnostic settings must point to a properly permissioned Log Analytics workspace, Storage account, or Event Hub.

### 25.3. Sample Diagnostic Settings

Once the resource confirms category `AuditEvent` is available, an example command:

```bash
LAW_ID="<approved-log-analytics-workspace-resource-id>"

az monitor diagnostic-settings create \
  --name "diag-kv-audit" \
  --resource "$VAULT_ID" \
  --workspace "$LAW_ID" \
  --logs '[{"category":"AuditEvent","enabled":true}]'
```

Verify **category compatibility, destination/log table mode, retention, and ingestion cost** before executing. Never route to an unauthorized shared/public Log Analytics workspace since audits can contain caller identities, network metadata, and secret names. Configuring diagnostics requires separate control-plane permissions.

### 25.4. Illustrative KQL

In a workspace **using the legacy `AzureDiagnostics` table** that actually receives Key Vault audit logs:

```kusto
AzureDiagnostics
| where TimeGenerated > ago(24h)
| where ResourceProvider =~ "MICROSOFT.KEYVAULT"
| where Category == "AuditEvent"
| summarize Events=count() by ResultType, OperationName
| order by Events desc
```

This is a **table-schema-dependent sample**, not a guarantee that Log Analytics always uses `AzureDiagnostics` or exact columns `ResultType`/`OperationName`. With resource-specific tables, query the actual emitted table/column names per your configuration. **Never build security alerts on a query untested against real data.**

### 25.5. Essential Alerts

1. **Data-plane forbidden rate** spikes unexpectedly after DNS/RBAC changes.
2. **Throttling/429** or service latency rises, preventing apps from fetching secrets.
3. **Private Endpoint connection** transitions to Pending/Rejected/Disconnected.
4. **Public network access** is re-enabled or firewall rules change outside policy.
5. **Role assignments/data-plane access policies** change without a change ticket.
6. **Application secret-fetch failures** or cache staleness past rotation SLA.
7. **DNS resolution fails to return a private IP** from synthetic probes in the workload network.
8. **Certificate/secret expiry** approaches or rotation jobs fail.

An alert firing on “403 > 0” can generate noise from **legitimate negative security tests**. Use thresholds/time windows, principal/source filters, and tagged planned tests—without ignoring all 403s and hiding exfiltration attempts.

### 25.6. Never Log Secret Values in Synthetic Probes

Synthetic monitoring can call `getSecret("health-test")` using an identity limited to a dedicated fixture secret. Assertions should verify **success/status/version** without logging the value. If the value rotates, update expectations properly; never use a production database password as a health probe.

## 26. Validating Policies with Positive and Negative Tests

A vault is truly **private-only** only when evidence shows **the right principal on the right network succeeds**, while **wrong paths are blocked**.

### 26.1. Acceptance Test Matrix

| Test | DNS | Identity | Expected |
|---|---|---|---|
| Workload in VNet, valid reader | FQDN → PE private IP | Secrets User | Fixture secret GET succeeds |
| Workload in VNet, no-role principal | FQDN → PE private IP | No data role | GET denied due to authorization |
| Outside VNet, valid reader | Public path, vault public disabled | Secrets User | Cannot read secret via public route |
| Private network, wrong secret name | Private IP | Valid reader | `404 SecretNotFound` (auth/network pass) |
| Private network, expired/wrong tenant token | Private IP | Invalid credential | Authentication failure |
| Private network, broken DNS | Fails to resolve or wrong IP | Valid reader | DNS/connectivity/network error |
| App Service without VNet integration | No private path | Valid managed identity | Cannot read private-only vault |
| Control plane admin outside VNet | ARM endpoint | Appropriate ARM permission | ARM operations per IAM/Policy; data plane still blocked |

### 26.2. Separating Errors Sharing the Same HTTP Status

Case A: An **authorized principal** outside the network gets `ForbiddenByFirewall` → network policy is blocking.

Case B: An **unauthorized principal** inside the network gets `ForbiddenByRbac`/permission denial → network works, authorization is missing.

Case C: Caller fails to acquire a token → identity failure before ever reaching Key Vault.

Never verify both layers with **a single 403 test**. Ensure tests use principals and routes with **known state** and never expose real secrets.

### 26.3. Testing Across Multiple Zones/Regions

If AKS spans multiple node pools, subnets, or regions, test every critical network path. One test VM next to the PE does not prove all Pod subnets or peered spokes have valid routing and DNS. Build dashboards showing **success rate per app/cluster/region** rather than averages that hide a broken cluster.

### 26.4. Test Automation

A CI/staging test can:

```text
Provision known test secret & reader identity
       |
       v
Check private endpoint Approved
       |
       v
Probe DNS FQDN -> allowed private IP set
       |
       v
Probe TLS 443 / certificate hostname
       |
       v
GET secret by expected workload identity
       |
       v
GET with no-role identity -> denied
       |
       v
GET from unauthorized network -> denied
       |
       v
Record result, sanitized error code, cleanup
```

Do not run **destructive firewall negative tests** by toggling production configs mid-traffic; run from an external network runner or against a test vault to observe expected denials without disrupting applications.

## 27. Runbook 1: Key Vault Returns 403 Despite a Private Endpoint

**Symptom:** Java `getSecret` fails with HTTP 403 after the network team provisioned a PE.

### 27.1. Ordered Investigation

1. **Right vault?** Verify Key Vault resource ID, subscription, tenant, and `<vault>.vault.azure.net` URL.
2. **PE approved?** Check connection state and endpoint resource association.
3. **Actual DNS?** Resolve vault FQDN from the **Pod/VM**; does it match the PE's private IP?
4. **Network path?** Does TCP 443/TLS reach the private IP?
5. **Auth token?** Does the runtime identity have the right tenant/client/object ID?
6. **Vault permission model?** Azure RBAC or access policies?
7. **Role/dataActions?** Is the principal granted `secrets/get` at the right scope/secret?
8. **Role propagation?** Has a newly created assignment finished propagating?
9. **Log error code?** Separate network restriction from authorization denial.
10. **Post-fix:** re-run positive and negative tests; record incident timeline.

### 27.2. Distinguish by Symptom

| Clue | Likely cause | Action |
|---|---|---|
| FQDN returns public IP, public disabled | Private DNS not applied | Fix zone/link/custom DNS/CoreDNS |
| FQDN returns PE IP, TLS 443 succeeds | IAM/token/data role or other policy | Check principal/RBAC/audits |
| Private DNS right, 443 times out | NSG/UDR/Firewall/PE state | Investigate routing and connection |
| Azure CLI user works, AKS pod fails | Different principals/network paths | Test the pod's actual identity and DNS |
| Failures start right after rotation | Secret version/credential/cache/permission change | Inspect rotation contract |

### 27.3. What Not to Do

- Never grant Subscription Owner to an app to fix `403`.
- Never disable firewalls or enable public access on production “for speed”.
- Never point the Java SDK URL to the raw private IP.
- Never disable TLS verification.
- Never change DNS, roles, NSGs, and SDK config all at once and lose track of root cause.

### 27.4. Recovery Criteria

Workload reads the fixture secret with the intended identity over the private IP; app health/startup recovers; external positive-role negative-network test remains **blocked**; audits show zero out-of-policy traffic.

## 28. Runbook 2: DNS Resolves Public IP or Fails to Resolve

**Symptom:** Vault private endpoint is Approved, yet `nslookup` from AKS returns a public IP, NXDOMAIN, or timeout.

### 28.1. Verification Steps

1. Identify which resolver the **workload** uses (`/etc/resolv.conf`, CoreDNS, custom DNS) and its source network.
2. Verify the Private DNS zone is named **`privatelink.vaultcore.azure.net`**.
3. Check the vault alias A record and private endpoint IP.
4. Check the VNet link to the workload's VNet or resolver VNet.
5. With peering/hub-and-spoke, confirm DNS queries reach a resolver linked to the zone.
6. For on-prem, verify conditional forwarding to the **Private Resolver inbound endpoint** or Azure VNet forwarder over VPN/ExpressRoute.
7. Check split-horizon DNS, negative caching, and stale records after PE recreation.
8. Re-test FQDN from Pod/VM; test TCP 443 and Key Vault GET.
9. Verify other vaults are not shadowed by an overly broad DNS zone.
10. Document DNS query paths and fixes in architecture/runbooks.

### 28.2. Never Fix DNS via Production Hosts Files

Adding `kv-prod.vault.azure.net=10.42.5.4` to a hosts file might make a quick test pass, but creates **drift and outages when PE IPs change**. Use standard Private DNS zones, zone groups, and resolver topologies managed via IaC.

### 28.3. Multiple Private Endpoints

If one vault has PEs in multiple VNets writing into one shared zone and causing cross-region resolution, design zones around **DNS resolution scope**. Never rely on round-robin A records when apps require private routes and not every IP is reachable from every spoke.

## 29. Runbook 3: Private DNS Is Right, Yet TCP/TLS Fails

**Symptom:** `nslookup` returns `10.42.5.4`, yet `curl` or `SecretClient` times out or fails SSL.

### 29.1. Classification

- **Connect timeout:** routing/NSG/firewall/UDR, peering, proxy, or PE status.
- **Connection reset:** middlebox/proxy/network flaps or service-side close.
- **TLS handshake failure:** truststore/CA/hostname mismatch, TLS interception/proxy.
- **HTTP 401/403:** HTTP response arrived; continue auth/network ACL diagnosis per error code.

### 29.2. Procedure

1. Confirm PE is Approved and NIC IP still matches DNS.
2. Inspect source subnet, effective NSGs/routes, and firewall logs.
3. Verify DNS returns the proper IP from the runtime itself.
4. Inspect proxy variables `HTTPS_PROXY`, `NO_PROXY`, and JVM proxy settings.
5. Test TCP 443 to the FQDN and inspect the TLS certificate hostname.
6. If TLS inspection is present, request a security/network review; **never disable verification**.
7. Check peering/VPN/return routes if calling from another network.
8. Compare against a reference VM in the VNet to isolate Pod vs. network issues.
9. After fixing, test `SecretClient.getSecret` with the fixture identity.
10. Confirm negative paths outside the VNet still deny.

### 29.3. Do Not Open Arbitrary Inbound Ports on Key Vault

There is no VM/SSH listener inside Key Vault requiring app-server-style NSG inbound rules. Valid connectivity is client HTTPS to the **private endpoint IP on port 443** over a supported path; the target service is Azure-managed.

## 30. Runbook 4: App Service/CI or Rotation Breaks After Private Cutover

**Symptom:** The AKS API still reads secrets, yet Azure Functions fails to refresh, CI pipelines fail to deploy, or certificate rotation errors out.

### 30.1. Find Every Consumer

Inventory:

```text
AKS workloads / CSI provider
App Service Key Vault references
Azure Functions / Logic Apps / Automation
CI/CD runners / scripts / Terraform or Bicep provisioning
VMs / jumpboxes / batch jobs
Certificate renewal / backup & recovery operations
Monitoring / synthetic probes
Hybrid/on-prem apps
```

Never assume every consumer calls Key Vault with the same identity or network path. Some only use ARM for config, while others call the data plane.

### 30.2. Remediation

1. Identify exactly which consumers broke and when cutover occurred.
2. Check that consumer's VNet Integration/private path; never rely on AKS test results as a proxy.
3. Verify DNS and Private Endpoint reachability from that runtime.
4. Verify the identity used by the reference/SDK and its data-plane role.
5. Check platform cache/refresh behavior for Key Vault references.
6. For hosted CI, move to VNet-connected runners or redesign pipelines to avoid secret retrieval.
7. For rotation jobs, provision both a private network path and write permissions.
8. Run end-to-end tests post-fix and monitor expiration.
9. If rolling back public access is unavoidable, follow an **approved emergency change plan** with temporary controls, strict time limits, and auditing.
10. Update the dependency inventory so future cutovers never miss a consumer.

### 30.3. Do Not Use “Trusted Services Bypass” as an Emergency Switch

Bypass does not guarantee hosted runners or arbitrary Azure apps pass the firewall. Under a private-only policy, the durable fix is **placing the consumer on a network that reaches the PE** or redesigning the secret flow, never leaving public access open indefinitely.

## 31. Disaster Recovery, Multi-Region, and Private Endpoint Lifecycle

A Key Vault accessed via a private endpoint does not automatically constitute a complete application DR plan.

### 31.1. Separate Vault HA from Network Path Availability

The Key Vault managed service can be completely healthy while your Java app cannot read secrets because:

- Private DNS Resolver in the hub VNet failed.
- Peering/VPN/ExpressRoute dropped.
- A firewall blocks TCP 443 between AKS and the PE.
- The Private Endpoint connection changed or sits Pending.
- App Service lost outbound VNet integration after scaling/redeployment.
- Identity token acquisition failed due to federation/tenant policy.

**Application RTO** is when the app successfully retrieves secrets and resumes function, not merely when Key Vault reports healthy.

### 31.2. What Does a Standby Region Need?

```text
Region A
  App A -> DNS A -> Private Endpoint A -> Key Vault
  Local identity/RBAC and connectivity tested

Region B
  App B -> DNS B -> Private Endpoint B -> Key Vault
  Local identity/RBAC and connectivity tested
```

This diagram is **conceptual**. Private endpoint regional placement, vault DR, replication/failover, and client routing must be verified against the active Azure service model. A “Geo-Redundant vault” does not automatically provision private DNS, endpoints, or network routes in Region B.

### 31.3. One Vault or Two Vaults?

| Model | Benefits | Challenges |
|---|---|---|
| One vault shared by all workloads | Single secret/version source to manage | Network/identity blast radius, latency/DR coupling |
| Separate vault per environment/app | Small access boundary, lower blast radius | More rotation/sync and inventory overhead |
| Separate vault per region | Supports regional autonomy/DR if designed well | Secret/certificate sync, version drift, cost |

Never assume secret versions and certificates sync automatically between **two independent vaults**; if using regional vaults, implement a secure **secret synchronization/rotation strategy** with change audits and zero plaintext logging.

### 31.4. After Deleting/Recreating a Private Endpoint

A recreated Private Endpoint can get a new IP; DNS zone groups and A records must update. Workloads may hold stale DNS caches; verify:

1. PE connection Approved and new NIC IP.
2. DNS zone A record matches the new IP and VNet links exist.
3. DNS resolver caches and Java HTTP connection pools.
4. NSG/UDR/firewall rules do not hardcode the old IP.
5. App workloads across all subnets/regions read secrets cleanly.
6. External negative network tests remain blocked.

### 31.5. Recovery When a Vault Is Accidentally Deleted

Key Vault offers **soft delete** and optional **purge protection** to mitigate accidental delete/purge. Understand retention/restore limits, backup/restore permissions, and naming constraints; never purge a vault just to “free up the name” if it holds data under retention obligations. **Private Endpoint and DNS dependencies may need to be rebuilt/reverified** after recovery operations.

## 32. Migrating a Production Vault from Public to Private with Minimal Disruption

This is a **migration runbook** for a vault serving multiple active workloads; execute under organizational change management, not a single toggle script.

### 32.1. Phase A — Inventory

1. List all **data-plane** clients: AKS Pods, VM services, App Service refs, Functions, CI/rotation jobs, on-prem.
2. List principal identities and roles/access policies per workload.
3. Identify Azure resources/app settings storing vault URIs/secret names.
4. Measure QPS, secret caching, rotation cadence, and peak deploy traffic.
5. Record current public firewall/VNet rules and diagnostic settings.
6. Identify owners of PE, DNS zones, VNet links, and custom DNS/forwarders.
7. Lock down acceptance and rollback criteria.

### 32.2. Phase B — Prepare Private Networking

1. Provision the PE targeting the right Key Vault and subresource `vault`.
2. Wait for approval and verify the PE IP.
3. Configure Private DNS zone `privatelink.vaultcore.azure.net`.
4. Link/forward DNS to all required VNets, regions, and hybrid consumers.
5. Configure VNet Integration for App Service/Functions and private CI runners.
6. Verify routing/NSGs/firewalls/private DNS from **every workload tier**.
7. Test fixture secret GET using the real workload identities.

### 32.3. Phase C — Canary

Pick a low-risk service:

```text
Canary (10% traffic or a test deployment)
    |
    +-- Check FQDN resolves PE IP
    +-- Check secret GET p95/error rate
    +-- Check application health/startup
    +-- Check rotation/ref refresh path
    +-- Check no public dependency
    |
    v
Approve broader rollout
```

**Canarying works only if it uses the same network/DNS/identity pattern as production**; a test VM in another VNet does not substitute for testing App Service/AKS networking.

### 32.4. Phase D — Close Public Access

During the change window:

1. Snapshot network/IaC config and record the change ticket.
2. Set `publicNetworkAccess Disabled` as required.
3. Confirm apps continue reading secrets over the private path.
4. Run a negative test from the public internet using a valid test reader.
5. Verify alerts, diagnostic logs, app health, and secret rotation.
6. Observe through at least one startup/refresh cycle aligned with business SLA.
7. Obtain security owner sign-off.

### 32.5. Phase E — Rollback (Only When Authorized)

If widespread outages hit due to DNS/routing and recovery exceeds RTO, **evaluate rollback per the approved plan**. One technical option is temporarily re-enabling public access with a strict firewall allowlist—only if **security/compliance policy permits it**. Otherwise, use pre-staged private break-glass network paths. Every rollback requires:

- Authorized approver.
- Scoped and time-boxed exception.
- Logging/alerting whenever public access changes.
- Plan to return to private-only once DNS/PE is fixed.
- Root-cause analysis and action items.

**Never leave the public endpoint open indefinitely** after a quick recovery and forget about it.

### 32.6. Phase F — Drift Management

Post-migration, codify PE, DNS zones/links, network ACLs, role assignments, and diagnostic settings in **IaC**. Apply **Azure Policy** and scheduled reviews to catch unplanned configuration drift.

## 33. IaC and Environment-Specific Security Config

An IaC design should capture:

```yaml
# Architectural pseudocode: NOT an executable Terraform/Bicep template.
environment: production
keyVault:
  name: kv-orders-prod
  publicNetworkAccess: Disabled
  authorizationMode: AzureRBAC
  secretReaders:
    - identity: orders-api-workload-identity
      role: KeyVaultSecretsUser
privateEndpoint:
  subresource: vault
  subnet: /subscriptions/.../subnets/snet-private-endpoints
  requireApprovedConnection: true
privateDns:
  zone: privatelink.vaultcore.azure.net
  linkedVirtualNetworks:
    - vnet-orders-prod
    - vnet-shared-dns-hub
logging:
  keyVaultAudit: enabled
  activityLogSecurityAlerts: enabled
validation:
  dnsMustResolveToPrivateIp: true
  allowedIdentityCanReadFixture: true
  publicReaderDenied: true
```

These fields form an **architectural/learning contract**, not an ARM/Bicep/Terraform schema. For real deployments, use exact API versions, role IDs, Private DNS zone groups, RBAC, VNet links, and identities matching your IaC provider version.

### 33.1. Why Must IaC Include DNS?

A template that creates the vault and PE while omitting the zone group/VNet links can still report deployment succeeded. Applications then resolve the public endpoint and fail. Treat **DNS as a first-class dependency** alongside the PE and Key Vault resource.

### 33.2. Deployment Dependency Order

```text
VNet/Subnet + Key Vault
         |
         v
Private Endpoint resource
         |
         v
Connection Approved
         |
         v
Private DNS zone/links/zone group
         |
         v
VNet-connected workload + identity/role
         |
         v
Positive secret GET + negative public test
         |
         v
Public network access Disabled / compliance sign-off
```

For greenfield production deployments under private-only policies from day one, a different sequence via ARM control plane may apply, while still ensuring **network readiness before workload startup**. Never treat an illustrative sequence as a guarantee that all resource providers provision synchronously.

### 33.3. Policy-as-Code and Compliance Evaluation

Azure Policy can audit/deny vaults with non-compliant network configs, but policy **cannot prove DNS/routing actually works**. Combine:

- Static checks: public network disabled, PE exists, RBAC mode right.
- Dynamic tests: DNS/443/GET from intended runtimes, public deny.
- Operational monitors: network/role drift, failed secret reads, certificate expiry.

### 33.4. Never Manage Secrets as Plaintext in IaC

Never pass secret values in template parameters or store them in Terraform state without strict controls. Terraform state and CI artifacts can persist sensitive values even when outputs are masked; choose **managed identities, runtime secret references, secure parameters, and protected state backends**. PE/network IaC never needs to output secret values.

## 34. Cost and Operability

Private Endpoints improve security while adding infrastructure and operational costs. Line items can include:

| Component | Potential cost | Optimization |
|---|---|---|
| Private Endpoint | Endpoint hours and data processed per service/region pricing | Create only needed PEs under a clean network architecture |
| Azure Private DNS | Zones/queries per current billing model | Purposeful zones/links; avoid duplicate DNS |
| Azure DNS Private Resolver | Inbound/outbound endpoints and queries/usage | Use for hybrid/custom DNS as needed; right-size |
| VNet peering/VPN/ExpressRoute | Data transfer, gateways/connectivity | Design locality and shared networking |
| Key Vault | Secret/key/certificate operations, transactions | Cache per security policy; batch appropriately |
| Azure Monitor/Log Analytics | Log ingestion/retention/alerts | Collect needed categories; redact |
| CI/private runners | Runner compute/networking | Scheduling, auto-stop, scoped access |
| Operations | DNS incidents, cert rotation, change reviews | IaC, runbooks, and synthetic probes |

### 34.1. Never Quote Fixed Unit Prices

Private Link, DNS Resolver, Key Vault operations, and logging prices vary by **region, SKU, volume, and pricing model**. Use the **Azure Pricing Calculator, Cost Management, and actual bills**. Never assume “private access is free” just because traffic stays inside Azure.

### 34.2. Cost from Retries and Quotas

If a Java service calls `getSecret` on every API request and broken DNS/firewalls cause 50% failures, retries multiply Key Vault transactions, thread contention, and log volume. **Caching, startup orchestration, and bounded retries** reduce load; just avoid infinite caches that delay secret revocation during rotation/compromise.

### 34.3. Pros and Cons of Sharing One Vault Across Many Apps

Centralizing vaults reduces PE count and admin overhead, yet increases blast radius and tangles permissions, networking, and rotation. Per-app/environment vaults add cost while making **security boundaries far cleaner**. Evaluate by threat model and TCO, not resource count alone.

### 34.4. Availability and Dependency Budgets

Apps needing secrets at startup need a strategy if Key Vault or DNS is temporarily unavailable: bounded startup retries, health/restart policies, credential rotation windows, and approved caching. Never let all pods restart and fetch secrets simultaneously in a **thundering herd**. A crash-looping startup can turn a brief Key Vault blip into a full-app outage.

## 35. Case Study: Securing Key Vault for a Java Ordering Platform

### 35.1. Context

The platform includes:

- **`orders-api`** Java 17/Spring Boot app on **AKS** inside a production VNet.
- Queue worker on **Azure Functions**.
- **Azure SQL Database** storing orders; Key Vault stores the database password, signing key reference, and certificate metadata.
- **Azure DevOps/GitHub Actions** deploying via OIDC.
- On-premises connectivity for incident response.
- Requirements: zero secret reads from the public internet; Azure RBAC least privilege; automated secret rotation; auditing and alerting.

### 35.2. Target Architecture

```text
                  Azure Control Plane / IaC
                           |
                  Policy + PIM + audit
                           |
                           v
                   Key Vault resource
                   public access = Disabled
                           ^
                           |
                Azure Private Link data plane
                           |
                    PE private IP
                           ^
                           |
            Private DNS zone/link + resolver
               /           |           \
              /            |            \
    AKS orders-api    Functions worker   On-prem management
       workload ID    VNet integration   VPN + DNS forwarder
              \            |            /
               +-----------+-----------+
                           |
                   Entra token + RBAC
                           |
                   Audited secret access

CI: deploy ARM resources; only private runner may perform
    Key Vault data-plane tests/secrets operations.
```

### 35.3. Permission Split

| Principal | Permissions needed | Not needed |
|---|---|---|
| AKS `orders-api` workload identity | Get specific secret/certificate/key operation per design | Set/delete/purge all secrets |
| Functions rotation identity | Manage the secrets requiring rotation | VNet-wide Network Contributor |
| CI IaC identity | Deploy infra/role changes under approval | Read all secret values |
| CI private integration identity | Read test secret fixture | Modify production secrets |
| Security administrators | Policy/IAM/auditing under approval | Share app runtime credentials |
| Developer laptop | Read metadata/docs, push code | Public data-plane access to production vault |

### 35.4. Illustrative Cutover Schedule

```text
Day -7: Inventory data-plane consumers and identities
Day -5: Deploy PE, private DNS zone, VNet links
Day -4: Test AKS pod and Functions outbound access
Day -3: Move CI secret-reading step to VNet-connected runner
Day -2: Test secret rotation + monitoring + hybrid DNS
Day -1: Canary access, verify data plane RBAC allow/deny
Day  0: Disable public network access in approved window
Day +1: Watch secret-fetch errors, rotation and API health
```

This timeline **illustrates the workflow**, not mandatory durations or an Azure SLA.

### 35.5. A Frequent Incident

Post-cutover, AKS keeps working while Azure Functions fails to resolve its Key Vault reference. The network team placed the PE in the AKS VNet, yet the Functions app lacks **outbound VNet Integration** or custom DNS cannot see the private zone.

Remediation:

1. Do not re-enable public access immediately.
2. Check the Functions hosting plan and VNet Integration.
3. Check FQDN DNS resolution from the Functions runtime.
4. Check the Key Vault reference identity and Secrets User role.
5. Test a fixture secret and check refresh timing.
6. Update the dependency inventory and add a synthetic probe for Functions.

**Lesson:** one working workload does not prove the entire fleet has private connectivity.

### 35.6. Another Hybrid DNS Incident

An on-prem management client uses internal DNS without forwarding `privatelink.vaultcore.azure.net` via Private Resolver. The vault FQDN resolves to a public IP and is denied. Operators confirm the VPN route is up and mistakenly suspect Key Vault is broken.

Remediation:

- Configure conditional forwarding to the Azure DNS Private Resolver inbound endpoint per topology.
- Confirm on-prem clients resolve the private IP.
- Check routing and TCP 443 firewall rules to the PE.
- Test token and Key Vault data-plane roles once DNS works.

### 35.7. Acceptance Metrics

```text
Network:
  AKS, Functions and authorized on-prem resolve PE IP.
  Outside VNet public path cannot read test secret.

Identity:
  Intended principals can get exactly required secret.
  No-role principal is denied inside VNet.

Operations:
  Key Vault reference and rotation workflows work.
  Audit logs and alerts received in approved workspace.
  Rollback/DR path documented and rehearsed.

Application:
  Secret fetch p95/error within SLO.
  No secret value in logs.
  No unexpected outage after startup/scale/deploy.
```

## 36. Practice Exercises

### Exercise A — Separating Two Protection Layers

A VM inside the VNet has proper private DNS and succeeds on TCP 443 to the PE, yet `SecretClient.getSecret()` still returns 403.

**Task:** list five ordered diagnostic steps distinguishing `ForbiddenByFirewall` from missing `Key Vault Secrets User`.

**Guidance:** check resource ID, PE status, DNS/routing/TLS, token principal/tenant, RBAC model/`dataActions`, and sanitized error codes. Never enable public access or grant Owner.

### Exercise B — Connecting from AKS

Design an AKS Pod using Workload Identity to read a secret from a private-only vault. Diagram service account → OIDC federation → Entra token → private DNS → PE → Key Vault.

**Task:** identify at least three misconfigurations that make the Pod fail while a jumpbox VM passes.

**Guidance:** Pod CoreDNS/custom DNS differs from VM, missing federated credential/client ID, Pod network policy/outbound route, wrong Key Vault role/scope.

### Exercise C — Private DNS

A PE is created with IP `10.42.5.4` and linked to `vnet-app`, yet on-prem `nslookup kv-prod.vault.azure.net` returns a public IP.

**Task:** design the DNS Private Resolver path and VPN routing, explaining why creating an A record in Azure alone is insufficient for on-prem.

**Guidance:** on-prem DNS must forward the private-link zone/queries to a resolver with visibility into Azure Private DNS; routing to the PE and network firewalls must permit traffic.

### Exercise D — Public Endpoint Firewall or PE?

A partner has a static public IPv4 and calls Key Vault only a few times daily. Company policy forbids public data-plane access in production.

**Task:** compare IP allowlists, service endpoints, and Private Endpoints; choose a policy-compliant solution and specify required networking.

**Guidance:** IP allowlists violate private-only policy; require private connectivity/identity integration or redesign so the partner does not call Key Vault's data plane directly.

### Exercise E — IAM Negative Test Verification

Security wants proof that someone holding `Key Vault Secrets User` outside the network cannot read secrets.

**Task:** design a safe test using a test principal/fixture that separates network denial from auth denial without leaking secrets via CLI logs.

**Guidance:** keep a known role on a test vault; run from both an authorized external test host and a private workload, printing only secret ID/status and never echoing values.

### Exercise F — Zero-Downtime Cutover

A vault is currently used by AKS, App Service, CI, and on-prem. Build a **migration checklist** covering inventory, DNS/VNet, identity, staged validation, disabling public access, negative tests, and rollback.

**Guidance:** never disable public access before verifying every data-plane consumer; Cloud Shell and hosted CI lack private paths by default.

### Exercise G — Java SDK and TLS

A developer changed `https://kv-prod.vault.azure.net` to `https://10.42.5.4` to “force the private path”; the app throws `SSLHandshakeException`.

**Task:** explain why hostname mismatch occurs and the right fix.

**Guidance:** keep the vault FQDN in `SecretClientBuilder.vaultUrl` and configure DNS to resolve the private IP; never disable certificate validation.

### Exercise H — Azure Key Vault References

App Service has a Key Vault reference and managed identity configured, yet the setting fails to resolve once the vault goes private-only.

**Task:** distinguish App Service's inbound PE from outbound VNet Integration, checking private DNS, identity, RBAC, and reference caching.

**Guidance:** configure the proper outbound private route, test on a supported plan/runtime, and verify reference identity and secret version/refresh.

### Exercise I — Multiple Private Endpoints

Two VNets in two regions have two PEs to one vault. After sharing one Private DNS zone, some clients in Region B receive Region A's PE IP and cannot route to it.

**Task:** design how to organize zones/links/resolver scopes and measure during cutover.

**Guidance:** DNS must return a reachable endpoint per network; review zone groups/A records and conditional forwarding, and test from each VNet/region.

### Exercise J — KQL and Alerting

Requirements call for alerts when (1) Key Vault forbidden rate spikes, (2) public access is re-enabled, and (3) rotation jobs fail.

**Task:** identify Azure Monitor/Activity Log/application metric sources, configure diagnostics, write KQL against **actual existing tables/fields**, and define owner, window, and runbooks.

**Guidance:** data-plane audits and control-plane activity are separate sources; synthetic secret-fetch telemetry measures application impact.

### Exercise K — Cost and Caching

A Java app handles 3,000 requests/s, calling Key Vault once per request. The team wants to cut Key Vault QPS while still picking up rotations within a bounded window.

**Task:** design cache TTL/refresh, failure policy, zero-secret-logging, and cost/latency/retry measurements.

**Guidance:** cache per security policy with explicit rotation invalidation or bounded refresh, never letting stale secrets linger forever.

### Exercise L — DR and Resolver Loss

The Key Vault platform reports healthy, yet one region cannot read secrets because the hub DNS resolver failed.

**Task:** write a runbook distinguishing a Key Vault outage from a network/DNS outage; describe resolver/private-path failover and app RTO validation criteria.

**Guidance:** platform health is not enough; check DNS probes, TCP, token/RBAC, app secret-get and health SLOs, and negative public tests.

## 37. Self-Check Questions

**1. Does a Private Endpoint automatically grant permission to read secrets?** No. It provides a private network path; the identity must still authenticate with Microsoft Entra ID and hold data-plane permissions.

**2. What are Key Vault's two primary planes?** The ARM **control plane** manages resources/config; the **data plane** reads/modifies secrets, keys, and certificates via the vault endpoint.

**3. Does setting `publicNetworkAccess Disabled` block the entire ARM control plane?** No; ARM/management permissions must be protected separately via RBAC, Azure Policy, and change controls.

**4. Should a Java client put the PE's private IP in `vaultUrl`?** No. Use `https://<vault>.vault.azure.net` and let DNS return the private IP.

**5. What is the standard Private DNS zone for a Key Vault vault?** `privatelink.vaultcore.azure.net`.

**6. Why shouldn't you arbitrarily create a `vault.azure.net` private DNS zone?** It can shadow valid public DNS records and break resolution to other vaults.

**7. What state must a Private Endpoint connection have before testing?** **Approved**, alongside valid DNS, routing, and permissions.

**8. Does an approved PE prove applications will resolve the private IP?** No. Private DNS zone groups, A records, VNet links, and DNS forwarders are still required.

**9. Is Azure Cloud Shell inside the same VNet as AKS by default?** No. Private network tests must run from the target workload/VNet.

**10. How do service endpoints and private endpoints differ?** Service endpoints route/ACL subnet traffic to the service's public logical endpoint; private endpoints allocate a private IP inside the VNet via Private Link.

**11. Should IP firewall allowlists contain private VM/Pod IPs?** That is not a PE substitute; Key Vault public IP rules target supported public IPv4/CIDRs.

**12. Does the trusted Microsoft services bypass cover every Azure resource?** No. The trusted services list is finite and feature-specific, not an allow-all switch.

**13. What happens to a workload with `Key Vault Secrets User` if DNS resolves a public IP on a private-only vault?** It cannot reach the data plane over the public route and receives a firewall error.

**14. What happens to a workload that resolves the private IP properly but lacks Secrets User?** It connects over the network yet lacks data-plane authorization, receiving 403.

**15. Does `Key Vault Reader` allow reading plaintext secret values by default?** No; metadata roles and secret-value permissions are distinct.

**16. When a vault uses Azure RBAC mode, is a legacy access policy `get` sufficient?** No; check the active authorization model.

**17. Can a service principal with ARM Contributor always read secrets?** No; data-plane permissions are required. Overly broad admin rights still pose a config-change/escalation risk.

**18. What does AKS Workload Identity need beyond a ServiceAccount?** Proper OIDC issuer/federated credential, Azure identity, data-plane RBAC, DNS, and routing to the PE.

**19. Does an inbound Private Endpoint on App Service provide outbound access to Key Vault?** No. Outbound VNet Integration must be configured separately.

**20. Does OIDC for CI automatically provide a private network path?** No. Identity federation and network connectivity are two separate layers.

**21. Why might DNS still fail on-prem even with a working VPN?** Private DNS zones are not automatically visible to on-prem resolvers; conditional forwarding via an Azure DNS resolver/forwarder is needed.

**22. Can every on-prem resolver forward DNS directly to Azure-provided DNS `168.63.129.16`?** Do not assume so; use an Azure DNS Private Resolver inbound endpoint or a VNet DNS forwarder.

**23. Why does `curl https://vault.vault.azure.net/` returning 401 not prove an RBAC bug?** The root path is not a secret API call; TCP/TLS succeeded, while authorization/request semantics have not been tested yet.

**24. Does HTTP 403 always mean a missing role?** No. Network ACLs, firewalls, data-plane policies, or wrong principals can all cause 403; inspect sanitized error codes plus DNS/identity diagnostics.

**25. If private DNS is right but port 443 times out, where do you check first?** PE connection/NIC IP, NSGs/UDRs/firewalls/routes, peering/VPN, proxies, and source subnet.

**26. What is the fix for `SSLHandshakeException` after replacing the hostname with the PE IP?** Restore the vault FQDN and private DNS; never disable certificate verification.

**27. Why run a negative test from outside the network with an identity that holds read permissions?** To prove **network restrictions** work independently of RBAC; if the identity also lacked a role, denial proves nothing about the firewall.

**28. Which consumers are most often forgotten when disabling public access?** CI runners, App Service/Functions Key Vault references, rotation/backup jobs, on-prem tools, monitoring probes, and slots.

**29. Should `getSecret` be called on every HTTP request?** Usually no; use caching/refresh and rotation policies balanced for security, latency, and quotas.

**30. Does a Private Endpoint prevent secrets from leaking through application logs?** No. Apps can still log secret values or expose them via APIs.

**31. How do Key Vault audit logs differ from the Activity Log?** Data-plane operations vs. control-plane resource/config changes, each with specific schemas and categories.

**32. What should be monitored besides Key Vault health?** DNS/PE connectivity, workload secret-get errors/latency, rotation, RBAC drift, and public access config changes.

**33. Do multiple PEs for one vault automatically route to the closest endpoint?** No. DNS resolution and routing must be designed explicitly per VNet/region.

**34. Should public access be disabled before setting up private DNS?** Not on a vault serving live workloads unless a greenfield/rollback design meets policy; ensure the private path is ready first.

**35. If an App Service reference fails to resolve, should the app be granted Owner?** No. Check outbound VNet Integration, DNS, reference identity, role scope, and refresh.

**36. How can purge protection affect lab cleanup?** Once enabled, you cannot arbitrarily purge/disable during the retention window, reserving the vault name and affecting test lifecycles.

**37. Does Azure Policy alone prove DNS is working?** No. Static compliance checks must be paired with dynamic network/secret-fetch tests.

**38. What does a rollback that re-enables public access require?** Security/compliance approval, strict IP allowlists, time-boxing, auditing, and a plan to return to private-only.

**39. Why must secret rotation be tested after cutover?** The rotation service is also a data-plane consumer needing its own network path, private DNS, identity, and write permissions.

**40. What are the complete private-only acceptance criteria?** Private IP DNS/routing/TLS work, authorized identity reads the fixture, no-role identity is denied, external read-role identity is blocked, rotation/CI/monitoring work, and configs are governed/audited.

## 38. Production Deployment Checklist

### 38.1. Scope, Threat Model, and IAM

- [ ] Target **Azure Key Vault vault** identified and distinguished from Managed HSM if applicable.
- [ ] Secrets, keys, certificates, and required permissions classified.
- [ ] Resource/subscription/tenant/region and business owners documented.
- [ ] Threat model covers public exposure, credential compromise, IAM escalation, and DNS misrouting.
- [ ] Vault deliberately uses RBAC or access policy mode; models are not mixed by assumption.
- [ ] Apps hold minimal data-plane roles; never broad Key Vault Administrator/Owner.
- [ ] Managed/Workload identities verified by principal/object ID/tenant; no long-lived shared passwords.
- [ ] Control-plane network/RBAC changes enforce PIM/approvals/Policy and auditing.
- [ ] Developers/CI cannot re-enable public access outside approved workflows.

### 38.2. Private Endpoint and DNS

- [ ] PE targets exact Key Vault resource ID and subresource `vault`.
- [ ] PE connection state is **Approved** and NIC private IP is verified.
- [ ] Private DNS zone `privatelink.vaultcore.azure.net` is accurate.
- [ ] PE DNS zone group/A record manages the right vault alias/IP.
- [ ] VNets, spokes, and hub resolvers are linked/forwarded per topology.
- [ ] AKS Pods/VMs/App Service runtimes/hybrid resolve the vault FQDN to the private IP.
- [ ] TCP 443 routing and TLS certificate hostname tested from actual runtimes.
- [ ] NSGs, UDRs, firewalls, proxies, and peering/VPN/ExpressRoute verified.
- [ ] No hardcoded private IPs or IP-based SDK URLs.
- [ ] Multi-PE/multi-region DNS design prevents returning unreachable IPs.

### 38.3. Network Policies

- [ ] Public network access is Disabled when policy requires private-only.
- [ ] If using public firewall mode, `defaultAction`, IP/VNet rules, and bypasses are approved.
- [ ] No RFC1918 private addresses in public IP allowlists.
- [ ] Trusted-services bypass limits are understood; never treated as allow-all.
- [ ] Positive secret-get test passes from private network with authorized identity.
- [ ] Negative auth test fails from private network with no-role identity.
- [ ] Negative network test fails from outside private network with authorized identity.
- [ ] Tests never expose secret values or credentials.
- [ ] Azure ARM control plane/IAM remains protected independently of the data plane.

### 38.4. Java Apps, AKS, and App Service

- [ ] Java `SecretClient` uses `https://<vault>.vault.azure.net` and Entra credentials.
- [ ] Client/token lifecycle and SDK versions are managed; clients are not recreated per request.
- [ ] Secrets never appear in application logs, traces, exceptions, or CI artifacts.
- [ ] Error classification handles DNS, network, TLS, auth, 403, 404, 429, and 5xx.
- [ ] SDK retries have deadlines, backoff, and never bypass security.
- [ ] Secret caching enforces TTL/rotation/refresh policies without infinite plaintext retention.
- [ ] AKS OIDC/federated credential/data role/VNet DNS tested inside Pods.
- [ ] CSI driver/secret mount refresh and Kubernetes permissions verified if used.
- [ ] App Service/Functions have outbound VNet Integration where needed.
- [ ] Key Vault references use right identity, URL, version/refresh, and slot config.
- [ ] CI data-plane jobs run from approved private networks when vaults are private-only.
- [ ] Certificate rotation/backup/monitoring consumers are not overlooked.

### 38.5. Operations, Monitoring, and Recovery

- [ ] Azure Monitor metric definitions/diagnostic categories discovered from the live vault.
- [ ] Diagnostic settings ship data-plane audits to a secure destination with proper retention.
- [ ] Azure Activity Log/Policy alerts monitor public access, PE, and RBAC drift.
- [ ] Synthetic DNS/TLS/secret GET probes run from every workload region.
- [ ] Alerts cover secret-fetch error rates, latency/throttling, and secret/certificate expiry.
- [ ] Runbooks exist for 403s, wrong DNS, 443 timeouts, and reference/CI failures.
- [ ] Data-plane consumer inventory completed before network changes.
- [ ] Change window/canary, private-first rollback, and security sign-off in place.
- [ ] DR/failover evaluates Private DNS Resolver, network/identity, and app RTO.
- [ ] Lab cleanup never purges protected vaults or deletes shared resources.
- [ ] Private Endpoint, DNS Resolver, Logs, and Key Vault operation costs have owners/budgets.
- [ ] Infrastructure as Code + Policy-as-code protect configs and detect drift.

## 39. Conclusion

**Private endpoints and Key Vault access restrictions** are a combined **networking, DNS, identity, authorization, and operations** challenge. A Private Endpoint routes Key Vault data-plane traffic through a VNet private IP, but works properly only when the connection is Approved, **`privatelink.vaultcore.azure.net` private DNS**, VNet links/forwarders, and TCP/TLS paths from workloads are configured accurately. For private-only requirements, set `publicNetworkAccess` to `Disabled` only after every critical consumer has been tested; **Key Vault firewalls/IP allowlists, service endpoints, and trusted Microsoft services bypass are not synonyms for Private Endpoints**.

On the authorization side, **Microsoft Entra ID, managed/workload identities, and Key Vault data-plane RBAC/access policies** remain independent prerequisites alongside the network path. The Java SDK continues using the **vault FQDN** and HTTPS/TLS, never a raw private IP. Production readiness demands **positive/negative tests, DNS/443 probes, audit logs, Azure Policy, 403/DNS/routing runbooks, and rollback/DR plans**. When implemented properly, applications on AKS, App Service, Functions, or on-premises can consume secrets, keys, and certificates over private, permission-controlled, observable, compliant, and resilient paths on Microsoft Azure.
