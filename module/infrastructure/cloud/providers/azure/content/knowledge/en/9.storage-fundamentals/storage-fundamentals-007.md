# Firewalls, Private Endpoints, and Secure Storage Access

Azure Storage may hold product images, invoices, backup files, transactional data, and other critical application documents. A Storage Account performing well is not necessarily well protected: the service might still accept connections from public networks, an account key might be shared too broadly, or internal systems might still hit the wrong endpoint after private networking is deployed.

To protect data on Azure, you must combine **network path controls** (Storage firewalls, virtual network rules, private endpoints, and DNS), **authentication and authorization** (Microsoft Entra ID, Azure RBAC, and SAS only when truly needed), and **monitoring and configuration governance**. No single switch replaces all of these layers.

This lesson belongs to the **Azure Storage Fundamentals** chapter, along the path exploring Microsoft Azure from subscriptions and resource groups to virtual networks, compute, storage, data, security, monitoring, and cost control for an application.

## Learning Objectives

After this lesson, you will be able to:

1. Explain why network access controls must be separated from data read/write permissions in Azure Storage.
2. Distinguish public endpoints, Storage firewalls, virtual network service endpoints, and private endpoints.
3. Design Storage access paths via private IPs, Private DNS Zones, and corporate networks connected to Azure.
4. Recognize authentication options using Microsoft Entra ID, RBAC, managed identities, SAS, and account keys.
5. Follow a secure configuration workflow for Storage firewalls, private endpoints, and DNS in the Azure portal.
6. Inspect configuration status with Azure CLI and verify connectivity using networking tools.
7. Troubleshoot common issues such as DNS returning public IPs, connection timeouts, or receiving 403 responses.

## 1. Two Control Layers: Network and Identity

When an application wants to read a blob in a Storage Account, at least two sets of conditions must be met:

- **Valid network path:** does the request reach the right endpoint; does the Storage firewall allow public ingress; do the private endpoint and DNS work; do NSGs, route tables, and intermediate firewalls permit the connection?
- **Permissions on the data:** does the presented identity or credential hold permission to perform that operation, such as reading a blob or writing a new file?

A user holding **Storage Blob Data Reader** can still be blocked if they send a request from an unpermitted public network. Conversely, a machine sitting in an allowed subnet does not automatically have permission to download all data without valid credentials or data permissions.

~~~text
Client / application
    |
    | 1. DNS selects endpoint
    v
Network path: public endpoint or private endpoint
    |
    | 2. Network controls (firewall / routes / NSGs if applicable)
    v
Azure Storage data plane
    |
    | 3. Authentication + authorization
    v
Blob / File / Queue / Table / application data
~~~

The **control plane** manages resources via Azure Resource Manager (ARM), such as creating a Storage Account or updating network settings. The **data plane** reads, writes, and deletes data inside the Storage service. Resource management permissions and data access permissions are two distinct layers. Being able to view a Storage Account in the Azure portal does not prove the current machine can read data via the data plane.

## 2. Public Endpoints and Storage Firewalls

A Storage Account typically exposes endpoints per service, for example:

~~~text
https://stordersprod.blob.core.windows.net
https://stordersprod.queue.core.windows.net
https://stordersprod.table.core.windows.net
https://stordersprod.file.core.windows.net
~~~

The name **stordersprod** is illustrative only, not a real account. Other services or configurations, such as Data Lake Storage Gen2, may add a **dfs** endpoint. These are standard service names; they do not mean the data permits anonymous access.

The **Storage firewall** controls requests arriving at the **public endpoint** of the Storage Account. Current network settings typically map to the following logical states:

| Configuration | Effect on Public Endpoint | Notes |
|---|---|---|
| Enable public network access from all networks | Public endpoint is reachable from broad network sources | Still requires auth/data permissions, yet exposes a wide network surface |
| Enable public network access from **selected networks** | Only sources matching IP rules, VNet rules, or allowed exceptions pass the firewall | Requires default deny, rule audits, and bypass review |
| **Disable public network access** | Blocks data-plane access via the public endpoint per Storage support mechanics | Access via configured and approved private endpoints can continue working |

In Azure CLI, two properties commonly inspected are **publicNetworkAccess** and **networkRuleSet.defaultAction**. They are not the same property: public network access state determines whether the public endpoint can be used at all, whereas default action/rules specify which sources are permitted when public network access is enabled.

### IP Network Rules

You can allow appropriate **public IPv4 addresses** or ranges to reach the public endpoint. For example, an office server NATs to the Internet via a static public IP; the business can allow that egress address when accessing Storage over the public endpoint is genuinely required.

Do not enter RFC 1918 private addresses such as **10.20.0.0/16** into the public firewall IP allowlist expecting Storage to recognize them as Internet sources. If an office network goes through NAT, Storage sees the public NAT IP. Moreover, IP-based firewall rules carry constraints around address types, prefix ranges, and same-region sources; verify support conditions before choosing them.

### Virtual Network Rules and Service Endpoints

Azure Storage supports **virtual network rules** to allow requests only from designated Azure subnets when using the corresponding **service endpoint** mechanism. In this model:

1. The subnet enables the service endpoint for the Storage service as supported.
2. The Storage Account allows that subnet in its network configuration.
3. Traffic still targets Storage's **public service endpoint**, yet Azure identifies the source by VNet/subnet rather than relying solely on public IP addresses.

**A service endpoint does not assign a private IP to the Storage Account.** That is a key difference from a Private Endpoint. Ensure both the subnet configuration and the firewall rule are configured properly; merely enabling a service endpoint on a subnet does not automatically grant access.

### Trusted Services and Resource Instances

Some Storage Accounts offer an option allowing documented **trusted Microsoft services** to bypass public network restrictions under supported conditions. This is **not** a blanket exception for every Azure service, every Microsoft VM, or every subscription. Requests must still satisfy authentication and authorization requirements.

Document clearly why any bypass is enabled, its scope, and its owner. Certain scenarios also offer resource instance rules or service-specific exception mechanisms. Avoid widening bypasses merely as a quick fix for an undiagnosed access failure.

## 3. Private Endpoints and Azure Private Link

A **Private Endpoint** is a network interface with a **private IP** created inside a VNet subnet and connected to a supported service over **Azure Private Link**. For Azure Storage, this endpoint lets applications access the data plane over a private address rather than routing to the public endpoint.

Example:

~~~text
API VM: 10.50.2.10
  |
  | TLS to stordersprod.blob.core.windows.net
  v
Private DNS: stordersprod.blob.core.windows.net
             -> 10.50.3.4
  |
  v
Private Endpoint (blob): 10.50.3.4
  |
  v
Azure Private Link
  |
  v
Storage Account: stordersprod
~~~

In this example, the application keeps using the standard Storage service hostname. DNS within the configured scope resolves it to the Private Endpoint's private IP. As a result, no code change is needed to hard-code a fixed IP address.

### Key Points

- A Private Endpoint is created **inside a subnet**, so plan for sufficient free IP addresses.
- The endpoint maintains a **private endpoint connection** with the Storage Account; states such as **Approved**, **Pending**, or **Rejected** determine usability.
- A private endpoint binds to a specific Storage **subresource**, such as **blob**, **file**, **queue**, **table**, or **dfs** depending on the account and purpose.
- If an app uses both the Blob and ADLS Gen2 DFS APIs, it may need private endpoints and DNS for **both blob and dfs** according to workflow requirements.
- A Private Endpoint does not grant data access permissions; apps still need Microsoft Entra ID/RBAC, SAS, or another valid authentication method.
- You can **disable public network access** on Storage after verifying all legitimate access paths route through private endpoints or another supported mechanism.

### A Private Endpoint Is Not a VNet Service Endpoint

| Criterion | Service Endpoint + VNet Rule | Private Endpoint |
|---|---|---|
| Storage address clients connect to | Service's public endpoint | Endpoint's private IP inside the VNet |
| Primary control mechanism | Identifies allowed subnets reaching the public endpoint | Private Link connection, private IP, DNS, and network path |
| DNS | Usually no private-name override needed | Must resolve hostname to private IP in client environments |
| Access from on-premises | Depends on network design and model support; not inherently private from on-prem | Works over VPN/ExpressRoute with proper routes and DNS to the private IP |
| Ability to disable public network access | Cannot keep using public endpoint when disabled | Continues using private endpoint if connection, DNS, and auth are valid |
| Additional configuration | Service endpoint on subnet, VNet rule on Storage | Private endpoint, connection approval, and Private DNS |

No single option is optimal for every system. Service endpoints can fit when Azure apps use the public endpoint and need subnet-level restriction. Private Endpoints usually fit better when a private network path is desired and public network access must be closed completely.

## 4. Private DNS Zones: Required to Take the Right Path

Creating a Private Endpoint **without designing DNS** is a common mistake. Applications may continue resolving the Storage name to a public address, taking the wrong path or getting blocked by the firewall even though the private endpoint succeeded.

For Blob Storage, the standard private DNS zone is:

~~~text
privatelink.blob.core.windows.net
~~~

In a VNet linked to the Private DNS Zone with proper records configured, resolution flows like this:

~~~text
Application queries:
stordersprod.blob.core.windows.net
          |
          v
Resolves via associated Private Link name:
stordersprod.privatelink.blob.core.windows.net
          |
          v
Private DNS A record
          |
          v
10.50.3.4  (Private Endpoint IP)
~~~

**The application still calls the original Storage hostname**, such as **stordersprod.blob.core.windows.net**. Never hard-code the Private Endpoint IP into connection strings or source code.

### DNS Zones per Storage Subresource

| Subresource | Standard Private DNS Zone |
|---|---|
| blob | privatelink.blob.core.windows.net |
| dfs | privatelink.dfs.core.windows.net |
| file | privatelink.file.core.windows.net |
| queue | privatelink.queue.core.windows.net |
| table | privatelink.table.core.windows.net |

Create only the endpoints and zones your application truly needs. **Azure Data Lake Storage Gen2** may use both DFS and Blob APIs in operations such as redirects or data interactions; verify scenarios and create both endpoints when required.

### VNet Links and DNS Zone Groups

The Private DNS Zone must be linked to VNets hosting clients or appropriate DNS infrastructure. A **Private DNS zone group** attached to the private endpoint helps manage related DNS records when configured. Without accurate records, clients may still receive public IPs or fail name resolution.

When multiple VNets or multiple private endpoints share a Storage Account, design zones, links, and records carefully to avoid conflicts or misresolution. Do not reuse the exact same manual record across endpoints if networks need distinct access paths.

### Access from On-Premises Networks via VPN or ExpressRoute

For on-premises servers, having a VPN/ExpressRoute to a VNet is not enough. On-premises DNS must forward Private Link queries to DNS/forwarder infrastructure capable of querying the Private DNS Zone in Azure. You can use **Azure DNS Private Resolver** or organization-managed DNS forwarders in a supported architecture.

Required end-to-end flow:

1. On-premises machine resolves the Storage name to the right **private IP**.
2. On-premises routers and firewalls have routes to the subnet hosting the private endpoint.
3. Intermediate VNets/NSGs/routes/firewalls allow traffic per supported conditions.
4. The private endpoint connection is in the Approved state.
5. The request carries valid data access permissions.

**Do not test DNS solely from one Azure VM.** Run DNS lookups from every actual environment consuming Storage, including on-premises servers, App Service, containers, or batch jobs.

## 5. Public Network Access and Private Endpoints Working Together

A common production pattern:

~~~text
                         Internet
                             |
                             X  Public network access: Disabled
                             |
                     Storage public endpoint

Azure workloads / privately connected on-premises
            |
            v
      VNet + private DNS
            |
            v
   Storage private endpoint (10.50.3.4)
            |
            v
      Azure Storage data plane
            |
            v
       Entra ID + Azure RBAC
~~~

In this model, disabling public network access eliminates data-plane access via the public endpoint; connections to the private endpoint must still satisfy networking, DNS, and identity controls. **The Storage firewall does not replace NSGs, route tables, or Azure Firewall on the VNet side.**

When applying NSGs or UDRs to a subnet hosting private endpoints, check whether **private endpoint network policies** are supported and enabled or disabled. Never assume every NSG/UDR applies to a private endpoint identically to a VM NIC across all configurations.

### Why Do Public Domain Names Still Appear?

An application using the hostname **stordersprod.blob.core.windows.net** does not mean requests necessarily traverse the Internet. What determines the actual path is the DNS resolution result, target IP address, and routing. In a proper configuration, the standard hostname resolves via Private Link to a private IP.

Conversely, if a client uses the right hostname yet receives a public IP in an environment permitting only private endpoints, requests will be blocked. Fix DNS/routing before considering reopening Storage public access.

## 6. Storage Authentication and Data Authorization

**Network restrictions are only one layer of defense.** You must choose how applications prove identity and receive permissions to data.

### Microsoft Entra ID and Azure RBAC

For Blob Storage, a preferred option is **Microsoft Entra ID** with Azure RBAC data-plane roles:

- **Storage Blob Data Reader:** read blobs within the assigned scope.
- **Storage Blob Data Contributor:** read/write and manipulate Blob data per role permissions.
- Other roles or access models may be needed for Queue, Table, Files, and specific workloads.

For instance, an API running on Azure App Service can use a **managed identity** granted Storage Blob Data Contributor at the container or Storage Account scope as required. The app uses the Azure SDK to acquire tokens instead of storing an account key in configuration.

**Management-plane Azure Contributor or Owner does not automatically grant all Blob data-plane rights via Microsoft Entra ID.** Some management permissions can indirectly affect data or keys depending on configuration, so evaluate specific roles and enforce least privilege.

### Shared Access Signature (SAS)

**SAS** grants conditional, time-limited access to Storage resources depending on SAS type and signing method. Use SAS when temporary access must be delegated to a task or partner, while restricting:

- Permitted service, container, or object.
- Required actions, e.g., read-only or write-only.
- Validity window and expiration time.
- Additional conditions supported by the SAS type, such as IP restrictions or HTTPS.

For Blob Storage, prefer **user delegation SAS** authorized via Microsoft Entra ID when scenarios support it, rather than generating SAS signed by an account key. Protect any SAS like a sensitive credential: anyone holding a valid SAS string can exercise the permissions it grants.

### Account Keys and Shared Key Authorization

A Storage Account may support **account keys**, a secret granting broad data access when used with Shared Key. Sharing account keys across multiple apps makes revocation/rotation and access auditing difficult.

For workloads supporting Microsoft Entra ID, consider discontinuing Shared Key and configuring appropriate restriction policies. **Do not disable Shared Key hastily** if legacy apps, Azure Files, or tools still depend on it; inventory compatibility and migrate step by step.

### Anonymous Blob Access Is a Separate Setting

**Allow Blob anonymous access** at the Storage Account level and container access levels are separate controls from public network access. An endpoint can be reachable from the Internet yet reject anonymous reads because authentication is required. Conversely, where anonymous read is enabled within supported limits, assess data-exposure risks.

Never infer blob read/write permissions from network firewall status, and never infer whether an endpoint is publicly reachable from data-plane permissions.

## 7. Reference Architecture: Sales Application Accessing Storage via Private Endpoint

Suppose an organization has:

- Subscription **sub-sales-prod**, resource group **rg-sales-prod**.
- An API running on VMs or compute with VNet connectivity.
- Storage Account **stordersprod** holding invoices and product images.
- VNet **vnet-sales (10.50.0.0/16)**, API subnet **10.50.2.0/24**, and private endpoint subnet **10.50.3.0/27**.
- An on-premises accounting server connected to Azure networking via VPN or ExpressRoute.

Security objectives:

1. The API and accounting server access Blob via private IP.
2. Public network access to the Storage Account is disabled after acceptance testing.
3. The API uses a managed identity and least-privilege data-plane role; the accounting server holds an appropriate identity/permission.
4. DNS in Azure and on-premises resolves to the right private endpoint address.
5. Data access logging, monitoring, and recovery plans exist if DNS or network paths fail.

~~~text
                  Internet users
                         |
                 Frontend/API HTTPS
                         |
                   API workload
                (managed identity)
                         |
                         | Blob HTTPS
                         v
            VNet / Private DNS Zone
                         |
              PE blob: 10.50.3.4
                         |
                         v
                 Storage Blob data
                 (network + RBAC)

On-premises accounting server
        |
       VPN / ExpressRoute
        |
       DNS forwarder / resolver
        |
        +--------> PE blob: 10.50.3.4
~~~

The path from Internet users to the frontend differs from the path from the API to Storage. The API can be a public-facing service while the Storage Account still keeps its public data endpoint closed to users.

### Responsibility Split

| Team | Responsibilities |
|---|---|
| Networking team | VNet/subnets, routes, private endpoints, DNS, firewalls, and on-premises connectivity |
| Application team | SDKs, managed identity, required blob permissions, error handling, and testing |
| Security team | Public access policies, RBAC, SAS/keys, monitoring, and exceptions |
| Operations team | IaC, backups, alerts, cost tracking, and approved configuration changes |

## 8. Secure Configuration Workflow in the Azure Portal

The steps below outline building a practice environment **inside an authorized subscription**. Confirm potential charges from Private Endpoints, Private DNS, network connectivity, and Storage usage beforehand. Never modify a production Storage Account without a migration plan and approval.

### Step 1: Inspect Current Configuration

In the **Azure portal**, open the Storage Account and confirm the subscription, resource group, and region. Check:

- Which Storage services are genuinely used: blob, dfs, file, queue, or table.
- **Networking**: public network access, firewall/VNet/IP rules, trusted services bypass.
- **Private endpoint connections**: existing endpoints and connection states.
- **Access control (IAM)** and **Configuration**: authentication methods, anonymous access, Shared Key access if present.
- Diagnostic settings, Azure Monitor, and currently connected clients.

Record a **baseline**: who is connecting, from where, using which DNS, and which read/write operations are critical. Until all clients are accounted for, do not block the public endpoint.

### Step 2: Prepare the VNet/Subnet

Select a VNet reachable by workloads. Create or reuse a subnet with enough IPs to host private endpoints, such as **snet-private-endpoints (10.50.3.0/27)**. Confirm non-overlapping CIDRs, valid routes, and subnet/NSG/Private Endpoint network policies per design.

A Private Endpoint for Storage is **not** a subnet delegation for an app service. Verify the subnet meets endpoint deployment criteria and is not shared with conflicting configurations.

### Step 3: Create a Private Endpoint for the Exact Subresource

On the Storage Account, open **Networking** or **Private endpoint connections** and create a Private Endpoint. Select:

1. Appropriate resource group, endpoint name, and region.
2. Target Storage Account.
3. **Target subresource**: e.g., **blob**.
4. VNet and subnet **snet-private-endpoints**.
5. **Private DNS Zone** integration if using Azure-managed DNS.

If the application uses both the Blob API and DFS API, evaluate adding a **dfs** endpoint as well. If using Azure Files, choose **file** and configure dedicated DNS for the File endpoint per service guidance.

Verify the private endpoint connection reaches **Approved** before relying on it in production. Approval from the Storage Account owner may be required when permissions span separate teams/subscriptions.

### Step 4: Verify Private DNS

In the Private DNS Zone, verify:

- Zone name matches the subresource, e.g., **privatelink.blob.core.windows.net**.
- A record maps the Storage name to the right private IP.
- VNet links exist for networks hosting clients or resolvers.
- DNS forwarders/private resolvers handle on-premises queries if needed.

From a VM or workload inside the accessing network, resolve the standard Storage name:

~~~bash
nslookup stordersprod.blob.core.windows.net
~~~

The expected answer is the designed private endpoint address, e.g., **10.50.3.4**. Do not stop at seeing **privatelink** in a CNAME chain; verify the **final resolved IP address** the client receives.

### Step 5: Test the Data Plane Before Locking Public Access

From an application inside the VNet:

1. Confirm DNS returns the private IP.
2. Confirm TCP/443 connectivity to the endpoint.
3. Sign in with a valid identity and test **reading** a sample blob.
4. If the app needs writes, test write/delete inside an authorized test area.
5. Check logs and outcomes from the actual application or SDK.

Retest from real external environments such as the on-premises accounting server. If a client cannot connect via the private endpoint, fix DNS, routing, firewalls, or permissions first; do not disable public network access yet.

### Step 6: Restrict Public Network Access

Once all legitimate clients use the private path, set public network access on the Storage Account to **Disabled** and save changes per change management procedures. If an integration strictly requires the public endpoint during transition, retain selected networks and restrict sources while migrating.

Firewall changes can immediately cut off legacy jobs, pipelines, or admin workstations. Schedule a maintenance window, designate an owner, and prepare an approved rollback plan.

### Step 7: Acceptance Testing and Monitoring

Verify three traffic flows:

| Request Source | Expectation After Locking Network |
|---|---|
| API with proper private DNS, routes, and RBAC | Reads/writes within permitted scope |
| On-premises machine via VPN/ExpressRoute, proper DNS, and permissions | Succeeds if allowed by design |
| Internet client bypassing private endpoint | Cannot reach data plane via public endpoint |

Also verify that users **without data permissions** remain denied even when connecting from a permitted network. Check diagnostic settings, alerts, and budgets for newly added resources.

## 9. Inspecting Configuration with Azure CLI

The commands below read configuration in an existing environment. They are useful for before/after comparisons and **do not toggle firewalls themselves**.

### Select Subscription

~~~bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"
~~~

### Inspect Public Network Access and Network Rule Set

~~~bash
az storage account show \
  --resource-group "rg-sales-prod" \
  --name "stordersprod" \
  --query "{name:name,publicNetworkAccess:publicNetworkAccess,defaultAction:networkRuleSet.defaultAction,bypass:networkRuleSet.bypass,allowBlobPublicAccess:allowBlobPublicAccess,allowSharedKeyAccess:allowSharedKeyAccess}" \
  --output json
~~~

Note that properties may be absent or hold different values depending on configuration and API version. Read actual state before concluding a policy is fully enforced.

~~~bash
az storage account network-rule list \
  --resource-group "rg-sales-prod" \
  --account-name "stordersprod" \
  --output json
~~~

Inspect IP rules, VNet rules, and bypasses. If **publicNetworkAccess** is **Disabled**, do not mistake an older IP rule in the config for an open public endpoint.

### Inspect Private Endpoint and Connection

~~~bash
az network private-endpoint show \
  --resource-group "rg-sales-network" \
  --name "pe-blob-orders" \
  --query "{name:name,provisioningState:provisioningState,subnet:subnet.id,connections:privateLinkServiceConnections}" \
  --output json
~~~

You can also inspect the Storage Account's private endpoint connections via the Azure portal or corresponding service CLI commands. **ProvisioningState = Succeeded** on the private endpoint resource does not substitute for verifying **Approved** status on the Private Link connection.

### Check DNS from the Client

~~~bash
nslookup stordersprod.blob.core.windows.net
~~~

On Linux with `dig`:

~~~bash
dig stordersprod.blob.core.windows.net
~~~

To test port 443 connectivity on a machine with PowerShell:

~~~powershell
Test-NetConnection stordersprod.blob.core.windows.net -Port 443
~~~

A TCP/443 success only proves a network connection can be established to the resolved address. It does **not** prove valid tokens, roles, or Blob read/write permissions.

### Conditional Configuration Example (Do Not Run Without Approval)

To illustrate how properties relate: a **selected networks** design can keep public network access enabled with default deny, then add approved IP/VNet rules:

~~~bash
az storage account update \
  --resource-group "rg-sales-prod" \
  --name "stordersprod" \
  --public-network-access Enabled \
  --default-action Deny
~~~

This command **modifies live configuration** and can disrupt connectivity. It does not add allowed networks by itself, so treat it strictly as an example under change control. Once all clients use private endpoints properly, set **Disabled** rather than reopening public network access. Never copy commands into production just to test a lesson.

## 10. Troubleshooting Common Errors

When Storage access fails, categorize across **DNS**, **network path**, **Storage firewall**, **private endpoint state**, and **data-plane permissions** before making changes.

| Symptom | Possible Cause | Where to Check |
|---|---|---|
| DNS still returns a public IP | Missing Private DNS Zone link, wrong record, or broken on-premises forwarding | Run nslookup from real client, check CNAME/A records, VNet links, and resolvers |
| TCP/443 times out to private IP | Blocked by routes, VPN/ExpressRoute, NSG/UDR, or intermediate firewall | Check outbound/return routes, endpoint subnet, effective rules, and source connectivity |
| Private Endpoint exists yet fails | Connection not Approved, wrong subresource, or DNS pointing to wrong IP | Check connection status, target subresource, and endpoint NIC |
| Blob works yet DFS API fails | Missing endpoint/zone or DNS path for dfs | Check ADLS Gen2 usage and both blob/dfs configurations |
| Portal shows Storage Account yet cannot list blobs | Management plane works while data plane hits network rules or missing role | Check browser source network and Storage Blob Data Reader permissions |
| HTTP 403 response | Missing data permission, bad/expired SAS, Shared Key disabled, or network firewall denial | Read specific error code and request ID; check auth and network separately |
| Selected networks configured yet VM still blocked | Subnet missing service endpoint, missing VNet rule, or client taking another path | Check subnet service endpoint, Storage rule, and DNS |
| On-premises over private endpoint still fails | On-premises DNS or routing to PE private IP is misconfigured | Test DNS resolution and routing directly from the on-premises host |
| Switching to Disabled breaks a pipeline | Pipeline runs outside VNet/private endpoint and previously used public endpoint | Locate where pipeline runs; provide private path or adjust design |
| App Service cannot reach Private Endpoint | Missing outbound/VNet Integration networking, DNS, or routing | Separate Storage's Private Endpoint from App Service networking features |

### Distinguishing 403 Errors from Connection Failures

**Timeouts or failed TCP handshakes** usually point to DNS, routing, or intermediate firewalls. **HTTP 403** means the request reached an HTTP-responding component and was denied; the root cause may lie in Storage network rules or data authentication/authorization.

Capture the **detailed error code**, request ID, timestamp, hostname, resolved IP, and source network. With Azure Storage, a bare 403 message is insufficient to blame RBAC. Likewise, never resolve it by toggling **Allow access from all networks** or broadly sharing account keys before identifying the cause.

### Short Diagnostic Workflow

1. Confirm target Storage Account, subresource, and subscription.
2. From the failing client, check whether DNS returns a private or public IP.
3. Verify TCP/443 or network reachability to the resolved IP.
4. Check private endpoint Approved state, Storage public network access, and applicable network rules.
5. Verify authentication method, data-plane roles, tokens/SAS, and operation permissions.
6. Correlate diagnostic logs, request IDs, and recent changes.
7. Apply the smallest fix and retest both allowed flows and flows that should remain blocked.

## 11. Monitoring, Governance, and Cost Control

A secure Storage solution must maintain its intended posture after every application deployment or scaling event.

### Policies and Permissions

Use Azure Policy to audit or enforce supported configurations, such as restricting public network access or requiring private networking per organizational standards. Use Azure RBAC to restrict who can modify Storage Accounts, network settings, Private Endpoints, DNS zones, and data-plane roles.

Across multiple subscriptions/resource groups, apply owner **tags** and clearly assign networking, application, and security teams. Avoid subscription-wide Owner when a narrower role suffices.

### Logs and Alerts

Consider enabling **diagnostic settings** and appropriate monitoring telemetry for Storage services, such as read/write/delete operation logs where supported, plus request count, error, and latency metrics. Depending on service and configuration, logs can route to Log Analytics, a Storage Account, or Event Hubs.

Watch for indicators such as:

- Spikes or sudden jumps in failed requests.
- 403 responses following firewall/DNS changes.
- Private endpoint connection state changes.
- Public network access re-enabled outside change approval.
- Tokens, SAS, or account keys used against policy.

**Storage logs can contain sensitive information or client identifiers.** Manage retention windows, log read access, and ingestion costs according to organizational policy.

### Cost

Items to budget include Storage capacity and operations, bandwidth/data transfer, Private Endpoints (hourly usage and processed data per current pricing), Private DNS Zones/Resolvers, VPN or ExpressRoute, logs, and monitoring infrastructure. Adding Private Endpoints for multiple subresources or multiple networks can increase both cost and complexity.

Before production deployment, check **Azure Cost Management** alongside current regional/SKU pricing and limits. Never assume Private Endpoints are free or that disabling public network access drops Storage costs to zero.

## 12. Checklist for Migrating Storage from Public to Private

| Stage | Task | Expected Outcome |
|---|---|---|
| Before | Inventory clients and active blob/dfs/file/queue/table endpoints | List of workloads and owners |
| Before | Audit public access, firewall rules, bypasses, and account keys/SAS | Network and identity baseline |
| Before | Plan subnets, IPs, VPN/ExpressRoute, and routes | Valid network path to Private Endpoint |
| Before | Create endpoint for exact subresource and approve connection | Private Endpoint Approved |
| Before | Link Private DNS Zone and configure forwarding | Real clients resolve to private IP |
| Before | Test reads/writes using Entra ID/RBAC or valid auth | Application works over private path |
| Cutover | Disable public network access during approved window | Public endpoint no longer serves unintended flows |
| After | Test requests from allowed and disallowed networks | Accurate allow/deny enforcement |
| After | Verify logs, alerts, policies, role assignments, and costs | Monitoring and ownership in place |
| After | Update IaC, DNS docs, runbooks, and recovery plans | Ready for operations/incident response |

**A rollback plan** must be defined prior to the change. If rolling back, never default to opening the public endpoint to all networks; restore only the previously approved scope while keeping authentication intact.

## 13. Scenario Exercise

A contract management app runs its API on Azure App Service and stores PDFs in Blob Storage. Currently, the app uses a connection string containing an account key, and the Storage Account allows public networks. The company wants to move to private access while still allowing an accounting job in the corporate datacenter to consume PDF files.

Design the solution by answering:

1. Which network components are needed for App Service to reach Blob via a Private Endpoint?
2. Which outbound VNet connectivity mechanism does App Service need, and what address must DNS return?
3. How should the on-premises accounting server configure VPN/ExpressRoute, routing, and DNS forwarding?
4. When using only the Blob API, which Storage subresource and Private DNS Zone are needed?
5. How do you migrate from account keys to managed identity and Azure RBAC without application downtime?
6. Which read/write operations, denied-access checks, and public flows must be tested before disabling public network access?
7. If after the cutover the API receives 403 while the accounting machine times out, what two distinct root-cause groups must be investigated?
8. List the logs, policies, costs, and rollback plan to prepare.

A solid solution includes a Storage Private Endpoint for **blob**, the corresponding Private DNS Zone, outbound VNet Integration for App Service per supported features, private connectivity from the datacenter with DNS forwarding, and a managed identity assigned the least-privilege Blob data-plane role. Only disable public network access after all legitimate sources are verified; never share account keys as a substitute for RBAC.

## 14. Common Misconceptions

**"Once a Private Endpoint exists, the Storage public endpoint closes automatically."** Not necessarily. You must verify and set public network access per policy; creating a private endpoint does not automatically remove public paths.

**"Firewall selected networks means only private IPs are allowed."** False. Selected networks can permit public IPs or subnets via service endpoints. Private Endpoint is a separate mechanism.

**"Service endpoints and Private Endpoints are the same thing."** No. Service endpoints restrict source subnets reaching the public service endpoint; Private Endpoints use private IPs connected via Private Link.

**"You can hard-code a fixed private IP in the connection string and skip DNS."** Avoid this. Using standard service hostnames with proper DNS supports TLS validation, endpoint routing, and infrastructure changes cleanly.

**"A Private Endpoint grants read access to blobs without signing in."** False. Network connectivity and authorization are two independent layers.

**"The Storage firewall blocks the Internet, so disabling blob anonymous access isn't needed."** False. These are separate controls; configure both network and data access controls properly.

**"Setting All networks to fix a 403 error is a safe solution."** No. A 403 can stem from RBAC, SAS, account keys, or firewalls; diagnose the root cause and open only what is needed and approved.

**"Once VPN is up, the Storage private endpoint is always reachable."** Not sufficient. You also need accurate DNS, routes to the private IP, an Approved connection, and valid authentication.

## 15. Self-Check Questions

1. How does the Storage firewall protect the public endpoint? Does it replace data-plane RBAC?
2. When public network access is set to Disabled, over which path should clients connect to Storage?
3. What is the key difference between a Storage service endpoint and a Private Endpoint?
4. Why does creating a Private Endpoint for **blob** not automatically cover **dfs** or **file** access?
5. Why is DNS resolution from the actual client machine critical evidence when validating a Private Endpoint?
6. Why can the Azure portal still display Storage Account details even when you cannot list blobs inside it?
7. When an application receives HTTP 403, list at least three distinct cause categories to separate.
8. What advantages do managed identities and Storage Blob Data Contributor provide over sharing account keys?
9. Why test on-premises traffic before disabling public network access?
10. What costs and monitoring settings must be considered when deploying multiple Private Endpoints?

## References

- Microsoft Learn — *Configure Azure Storage firewalls and virtual networks*: https://learn.microsoft.com/azure/storage/common/storage-network-security
- Microsoft Learn — *Use private endpoints for Azure Storage*: https://learn.microsoft.com/azure/storage/common/storage-private-endpoints
- Microsoft Learn — *What is a private endpoint?*: https://learn.microsoft.com/azure/private-link/private-endpoint-overview
- Microsoft Learn — *Private endpoint DNS configuration*: https://learn.microsoft.com/azure/private-link/private-endpoint-dns
- Microsoft Learn — *Authorize access to Azure Storage*: https://learn.microsoft.com/azure/storage/common/authorize-data-access
- Microsoft Learn — *Authorize access to Blob data with Microsoft Entra ID*: https://learn.microsoft.com/azure/storage/blobs/authorize-access-azure-active-directory
- Microsoft Learn — *Security recommendations for Azure Blob Storage*: https://learn.microsoft.com/azure/storage/blobs/security-recommendations
