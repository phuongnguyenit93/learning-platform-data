# Private Endpoint, Firewalls, and Securing Database Connectivity

An ordering service running on **Azure App Service** needs to read and write data in **Azure SQL Database**. The development team created database accounts, enabled HTTPS for the website, and restricted app IPs, yet database traffic still travels to the public endpoint. When switching the database to a private network, the app suddenly suffers timeouts even though the deployment stays `Healthy`. In another environment, operations created a **Private Endpoint**, yet DNS still returned a public address; an engineer enabled the "Allow Azure services" firewall option as a quick fix, unintentionally widening access far beyond expectations.

This is a classic cloud database security problem: **Private Endpoint**, **firewalls**, **DNS**, **identity**, **TLS**, and **data access permissions** are distinct layers. Creating a Private Endpoint resource **does not automatically prove** the app uses a private path, and having a private network **does not mean** an arbitrary caller can read database tables.

This lesson sits in the **Relational Databases** chapter of the **CLOUD_PROVIDERS_AZURE** module, connecting to Azure subscriptions, resource groups, Microsoft Entra ID, virtual networks, compute, storage, and monitoring. The focus is implementing, verifying, and operating secure connectivity for **Azure SQL Database**, while highlighting critical differences when using **Azure SQL Managed Instance**, **Azure Database for PostgreSQL Flexible Server**, and **Azure Database for MySQL Flexible Server**.

After this lesson, you will be able to:

- Distinguish public endpoints, database firewalls, service endpoints/VNet rules, **Private Link/Private Endpoints**, and **VNet-injected private access**.
- Design the flow application → VNet/DNS → private IP → Azure database without confusing network boundaries with authentication.
- Choose the right Private DNS zone, verify FQDNs, and test DNS resolution from the application's **actual runtime**.
- Set up a Private Endpoint for an Azure SQL logical server in an authorized lab and test connectivity before disabling public access.
- Protect connections with **TLS certificate validation** and **Microsoft Entra ID/managed identity** where supported; apply least-privilege SQL permissions.
- Isolate DNS, network, firewall, certificate, database login, and data permission errors layer by layer.
- Plan cutovers from public to private without breaking apps unexpectedly, while handling HA/DR, observability, costs, and cleanup.

## 1. Threat Model: What Are We Protecting?

A relational database in Azure stores high-value data: customers, transactions, orders, HR records, or account balances. Protection goals typically include:

1. **Eliminating unnecessary public access paths to the endpoint.**
2. **Allowing only approved networks and workloads** to reach the database listener.
3. **Allowing only valid identities** to log in and execute statements inside the database.
4. **Encrypting network traffic and authenticating the server**, preventing eavesdropping and spoofing.
5. **Enforcing least-privilege SQL rights:** an order-reading API cannot drop arbitrary tables.
6. **Maintaining logs, alerts, and recovery paths** when endpoints, DNS, keys, certificates, or policies change.

These layers reinforce each other:

~~~mermaid
flowchart LR
    APP[Application / worker] --> EGRESS[Outbound route / VNet integration]
    EGRESS --> DNS[DNS resolves database FQDN]
    DNS --> PE[Private Endpoint IP or private VNet endpoint]
    PE --> DB[Managed relational database]
    APP -. TLS / certificate validation .-> DB
    APP -. Entra token or database credential .-> DB
    DB --> AUTHZ[Database roles / GRANT / row-level rules]
    MON[Monitor / audit / alert] -. Observe .-> APP
    MON -. Observe .-> DB
~~~

**A Private Endpoint is not a database user.** If an app has a valid network path but passes a wrong token/password or lacks `GRANT SELECT`, queries still fail. Conversely, a principal with database permissions but no network route cannot connect to the listener.

### 1.1. Three Questions Before Opening a Port

| Question | Example Answer | Control Layer |
|---|---|---|
| **Who is the client?** | Managed identity of `orders-api-prod` | Identity + SQL roles |
| **Where is the client coming from?** | App Service VNet Integration subnet | Routing, firewalls, Private Endpoint |
| **Where is the client connecting?** | `orders-sql.database.windows.net:1433` | DNS, TLS hostname, port, database name |

**Never use "private IP" as sole proof that a connection is secure.** Prove the hostname resolves accurately, the path is authorized, TLS validates the certificate, and the principal holds only required permissions.

## 2. Azure Database Services Do Not Share One Network Model

Hearing "Azure database" tempts learners to assume every service has an identical **Private Endpoint** button. In reality, each product has its own deployment model, listener, DNS, and firewall semantics.

| Service | Typical Endpoint/Network | Private Option | Key Note |
|---|---|---|---|
| **Azure SQL Database** | Logical server `<server>.database.windows.net` | **Private Link/Private Endpoint** for the SQL logical server; firewall/public network settings | Databases sit under a logical server; Private Endpoint does not create one separate endpoint per database |
| **Azure SQL Managed Instance** | Instance placed inside a dedicated VNet subnet | **VNet-native connectivity**; public/private endpoint options depending on model and current support | Do not blindly copy Azure SQL Database's `sqlServer` Private Endpoint steps |
| **Azure Database for PostgreSQL Flexible Server** | `<server>.postgres.database.azure.com` | **Private access (VNet integration)** or **Private Link** on compatible public-access/supported servers | Two distinct private models; do not assume you can toggle freely between them after creation |
| **Azure Database for MySQL Flexible Server** | `<server>.mysql.database.azure.com` | **Private access (VNet integration)** or **Private Link** per network mode and service capabilities | DNS/firewalls and connectivity change rules differ from Azure SQL |

**Do not mix** `az sql server ...` commands with `az postgres flexible-server ...` or `az mysql flexible-server ...`. Private DNS zone names, subresource IDs, ports, and authentication modes all differ.

### 2.1. Distinguishing Logical Server and Database

In **Azure SQL Database**:

~~~text
Azure subscription
  Resource group: rg-data-prod
    Azure SQL logical server: orders-sql-prod
      Public DNS name: orders-sql-prod.database.windows.net
      Database: ordersdb
      Database: reportsdb
      Private Endpoint connection: pe-orders-sql
    VNet: vnet-app-prod
      Subnet for application integration
      Subnet for Private Endpoints
    Private DNS zone: privatelink.database.windows.net
~~~

A Private Endpoint on a SQL logical server lets network-authorized clients reach databases on that server over a private path. **It does not restrict clients to logging into only one database**; database users/roles and authentication remain the per-database control gate.

### 2.2. VNet-Native Private Access Differs from Private Link

**Private Link/Private Endpoint** creates a **network interface with a private IP inside the client's VNet** to reach a target service resource. The database remains service-managed; you are not "moving a database VM" into your subnet.

**VNet-injected private access** on certain Flexible Servers uses a **delegated subnet** and dedicated private DNS right from the deployment model. It embeds the **server's access path inside the VNet**, rather than attaching a Private Endpoint NIC onto a public server. Subnet rules, DNS, HA, and mode-switching rules differ.

**Azure SQL Managed Instance** deploys into a VNet subnet using its own model; never create a SQL Database logical server Private Endpoint and mistake it for Managed Instance.

### 2.3. Design by Product, Not Habit

Before designing:

1. Identify exact **resource type/SKU**, region, and engine.
2. Check **creation-time networking mode** and supported Private Link/VNet integration features.
3. Identify connection sources: App Service, Functions, AKS, VMs, on-premises, or CI agents.
4. Determine which DNS resolver/Private DNS zone each source uses.
5. Choose public access, firewall, and database authorization policies.
6. Plan DR/failover, monitoring, and private networking costs.

## 3. How Public Endpoints, Service Endpoints, and Private Endpoints Differ

### 3.1. Public Endpoint + Database Firewall

With a public endpoint, the database listener uses a public domain name and inbound traffic is controlled by server firewalls or service network rules—for instance, allowlisting an app's **public egress IP**. This can be valid in some setups when TLS/auth/firewalls are tight, though the network exposure is wider than a private design.

Risks:

- Egress IPs change during scaling or NAT changes, suddenly getting blocked by the firewall.
- Operators open overly broad IP ranges to "fix" connectivity errors.
- The public endpoint remains Internet-reachable even when teams assume the database is "private."
- A principal with leaked credentials can attempt logins from allowlisted addresses.

### 3.2. Service Endpoints and VNet Firewall Rules

Some Azure services support **service endpoints/VNet rules** to recognize traffic originating from a subnet. In this model, the target service retains Azure **public service endpoint** semantics rather than placing a **private database IP** inside the client's subnet.

Do not use **service endpoint**, **private endpoint**, and **VNet integration** interchangeably. Each has distinct purposes and service compatibility; modern platforms prefer Private Link when eliminating public exposure.

### 3.3. Private Endpoint via Azure Private Link

A Private Endpoint places a private IP in a chosen subnet and binds it to the target service over a dedicated private connection. When the app's DNS resolves the database hostname to that IP, traffic flows over the private network/Private Link instead of public addresses.

~~~mermaid
flowchart LR
    APP[Orders API in VNet or connected network] --> RESOLVE[DNS for orders-sql.database.windows.net]
    RESOLVE --> PRIV[Private IP 10.20.2.4]
    PRIV --> NIC[Private Endpoint NIC in subnet]
    NIC --> PL[Azure Private Link]
    PL --> SQL[(Azure SQL logical server)]
    PUBLIC[Public network endpoint] -. Disable when cutover validated .-> SQL
~~~

**Critical milestone:** creating a Private Endpoint **does not automatically disable public network access** on Azure SQL. Both paths can coexist during migration. To achieve private-only access, verify every workload has cut over and then **explicitly disable public network access** per database policy.

### 3.4. Comparison Table

| Criterion | Public + Firewall | Service Endpoint/VNet Rule | Private Endpoint |
|---|---|---|---|
| Destination IP seen by client | Typically public service IP | Public service endpoint semantics | **Private IP inside VNet** |
| Source control | Public IP/database firewall | Service-specific subnet/VNet rule | Private endpoint, routes/NSGs as supported + identity |
| Private DNS zone | Not strictly needed | Not strictly needed | Usually needed so clients keep canonical FQDN |
| Closes public exposure | No if public access remains | Not by default | **Requires disabling public access separately** where supported |
| Access from on-premises | Over Internet/egress and firewall | Design-dependent | Over VPN/ExpressRoute/routing + proper DNS |
| Cost impact | Egress/firewall per architecture | Service-dependent | Private Endpoint, data processing, DNS/networking |

None of these mechanisms creates a database user or runs SQL `GRANT`. That remains the job of **database security**.

## 4. DNS Is Essential for Private Endpoint to Work Properly

Applications connect by **FQDN**, not raw IP addresses. Private Link relies on DNS returning the **private endpoint IP** to clients on the right network. If DNS is wrong, connections may:

- Hit the public endpoint and get rejected once public access is disabled.
- Time out due to mismatched public/private routing.
- Route to a Private Endpoint in another VNet/region unreachable from the client.
- Fail TLS validation if developers hard-code a private IP instead of the certificate's hostname.

### 4.1. Reference DNS Flow for Azure SQL Database

Suppose:

~~~text
SQL server FQDN: orders-sql-prod.database.windows.net
Private Endpoint IP: 10.20.2.4
Private DNS zone: privatelink.database.windows.net
Private DNS A record: orders-sql-prod → 10.20.2.4
~~~

Clients keep using the **canonical connection name** `orders-sql-prod.database.windows.net`. Under standard configuration, this hostname resolves via a chain referencing `orders-sql-prod.privatelink.database.windows.net`, and the Private DNS zone returns the private IP inside authorized networks. **Never change connection strings to `privatelink` hostnames or raw IPs** just to use Private Endpoint.

~~~mermaid
flowchart TD
    CLIENT[App asks DNS: orders-sql-prod.database.windows.net] --> DNS[Recursive DNS / Private DNS Resolver]
    DNS --> CNAME[Service DNS chain to privatelink name]
    CNAME --> ZONE[Private DNS zone privatelink.database.windows.net]
    ZONE --> A[A record 10.20.2.4]
    A --> CONNECT[TCP 1433 to Private Endpoint]
    CONNECT --> TLS[TLS verify hostname orders-sql-prod.database.windows.net]
    TLS --> AUTH[Entra or SQL authentication]
~~~

This is a **logical model**; resolvers may use Azure-provided DNS, custom DNS, Azure DNS Private Resolver, or hub forwarders. Exact CNAME/record chains vary by service. What matters is that the final answer **inside the application runtime** points to a routable private IP.

### 4.2. Common DNS Names to Distinguish

| Service / Model | Client-Used FQDN | Illustrative Private DNS Zone |
|---|---|---|
| Azure SQL Database via Private Link | `<server>.database.windows.net` | `privatelink.database.windows.net` |
| PostgreSQL Flexible Server via **Private Link** | `<server>.postgres.database.azure.com` | `privatelink.postgres.database.azure.com` |
| MySQL Flexible Server via **Private Link** | `<server>.mysql.database.azure.com` | `privatelink.mysql.database.azure.com` |
| PostgreSQL/MySQL Flexible Server via **VNet-injected private access** | Standard engine server FQDN | Private DNS zone per private-access config rules; **do not assume the Private Link zone applies** |
| Azure SQL Managed Instance | Service-assigned instance FQDN | Per MI's VNet-native/endpoint and DNS model, **different from SQL Database logical server** |

**Note:** zone names and Private Link support must be verified per **engine, networking mode, tier, and deployment timing**. Specifically, Flexible Server private access (delegated subnet) follows different private DNS rules than Private Link on a public-access server. Never copy a zone from an Azure SQL tutorial onto PostgreSQL/MySQL blindly.

### 4.3. VNet Links and Custom DNS

A Private DNS zone works only for networks whose DNS resolution path can query its records:

- **VNet links** let an Azure Private DNS zone serve linked VNets.
- **Hub-spoke** topologies can use Azure DNS Private Resolver or DNS forwarders so spokes and on-premises resolve records.
- **VPN/ExpressRoute** carry IP packets; resolving private hostnames still requires **DNS resolution** from on-premises.
- Custom DNS on a VNet may need conditional forwarders pointing to Azure-resolvable DNS.
- Never treat an `nslookup` on a laptop outside VPN as proof that AKS Pods in a private network resolve DNS properly.

### 4.4. Results from Two Locations Can Differ

~~~text
Laptop outside VNet:
  nslookup orders-sql-prod.database.windows.net
  → public address/chain via external DNS

VM/Pod inside VNet with Private DNS link:
  nslookup orders-sql-prod.database.windows.net
  → 10.20.2.4 (example)
~~~

**This is valid split-horizon DNS** when properly configured. One hostname yields different DNS answers depending on resolver context; it is not necessarily a bug. Verify from **each consumer's intended network path**.

### 4.5. Never Force Connection Strings to a Private IP

When an app connects directly to `10.20.2.4` instead of the server FQDN:

- Service TLS certificates are issued for the hostname, not the private IP.
- Drivers report **hostname mismatch** when certificate validation is enabled.
- Private Endpoint IPs can change if resources/networking are recreated.
- Failover, zone routing, and connection policies may require the canonical hostname.

**Keep the canonical FQDN and fix DNS rather than disabling TLS verification.** Never enable `TrustServerCertificate=true`, `sslmode=disable`, or bypass certificate validation to mask DNS/hostname mistakes.

## 5. Firewalls: Multiple Layers, Not One Switch

When a database fails to connect, operators often ask "is port 1433 open?" In reality, at least four layers need checking:

| Layer | Purpose | Example |
|---|---|---|
| **Azure database public network settings** | Allow/deny connections over the public endpoint | Azure SQL `Public network access: Disabled` |
| **Database firewall rules** | Restrict client public IPs/VNet rules per service | Allow a specific egress IP range |
| **VNet NSGs/UDRs/Azure Firewall** | Control paths and ports from app to endpoint | Allow app subnet to private endpoint TCP 1433 |
| **Database login/SQL permissions** | Authenticate identity and query privileges | Entra principal with `GRANT SELECT` |

**Firewalls do not replace SQL authorization.** An open TCP port merely lets traffic reach the handshake/login step; it is not permission to read data.

### 5.1. Public Network Access on Azure SQL Database

Once Private Endpoint exists and apps are verified over private IPs, you can set **Disable public network access** for private-only requirements.

- It restricts inbound access to the **SQL logical server** public endpoint per service capabilities.
- It does not change database users, passwords, schemas, or TLS requirements.
- It does not automatically switch app DNS to private IPs.
- If any app still connects from on-premises/laptop/CI over the public endpoint, it will **immediately lose connectivity**.
- Verify how Azure control-plane operations/diagnostics/automation interact with the database once public access is off.

### 5.2. "Allow Azure Services and Resources to Access This Server"

On an **Azure SQL logical server**, depending on firewall config, there is an option allowing **Azure services and resources** access via the public endpoint, generally corresponding to an Azure-origin firewall rule. This is a **broad exception**, not "just my own App Service."

Risk: it opens the network boundary to many Azure resources outside your VNet and ownership, leaving database authentication as the remaining gate. Never enable it casually to fix 40615/timeout errors; prefer **Private Endpoint**, controlled egress IPs, and per-principal permissions.

**Principle:** when private-only is required, audit and remove obsolete public paths/exceptions rather than creating a Private Endpoint while keeping broad exceptions "just in case."

### 5.3. NSGs and UDRs with Private Endpoint

A Private Endpoint is a NIC in a subnet, yet whether **NSG policies/route table policies apply directly to Private Endpoint traffic** depends on the subnet's **private endpoint network policies** setting and supported Azure rules.

- Do not assume attaching an NSG to a subnet filters **all** Private Endpoint traffic identically to VM NICs.
- Check `privateEndpointNetworkPolicies` on the subnet and support rules before using NSGs/UDRs to steer traffic through a firewall.
- With UDRs/forced tunneling, ensure routes to the private endpoint IP remain valid without asymmetric routing.
- Validate Azure Firewall/NVA filtering with packet flows and real logs.
- Network security never replaces TLS authentication and SQL permissions.

### 5.4. Ports and Connectivity

| Engine/Service | Typical Port | Note |
|---|---|---|
| Azure SQL Database | TCP **1433** for standard SQL connections | `Proxy`/`Redirect` connection policies and paths can introduce extra port/route requirements; check Azure SQL connectivity docs |
| Azure SQL Managed Instance | TDS port per MI endpoint/model | Ports and DNS can differ from SQL DB; do not copy a 1433 rule blindly |
| PostgreSQL Flexible Server | TCP **5432** | TLS and auth per PostgreSQL/Entra config |
| MySQL Flexible Server | TCP **3306** | TLS/auth per MySQL service/driver |

**Opening a TCP port is insufficient:** DNS must resolve correctly, the VNet must route, firewalls must permit traffic, TLS/hostname certificates must validate, and the database must accept the principal. App HTTP health probes do not verify these conditions.

## 6. Designing the Network Before Creating Resources

A private database design typically uses a **separate subnet for applications** and a **subnet hosting Private Endpoints**. Never place a Private Endpoint inside a subnet **delegated** to a service that forbids mixing resource types. Verify CIDRs, peering, routes, DNS, and ownership before provisioning.

### 6.1. Example VNet Architecture

~~~text
Subscription: app-production
Resource group: rg-orders-prod

VNet: vnet-orders-prod (10.20.0.0/16)
  subnet-app (10.20.1.0/24)
    App Service outbound VNet Integration / VM/AKS source

  subnet-private-endpoints (10.20.2.0/24)
    NIC of pe-orders-sql: 10.20.2.4

Private DNS zone:
  privatelink.database.windows.net
  A record orders-sql-prod → 10.20.2.4
  Linked to VNet(s) that should resolve privately

Azure SQL logical server:
  orders-sql-prod.database.windows.net
  Database: ordersdb
  Private Endpoint connection approved
  Public network access disabled AFTER testing
~~~

`10.20.2.4` is illustrative only. Across hubs/spokes, never pick VNet ranges overlapping on-premises or other networks. Azure assigns private IPs per Private Endpoint/subnet configuration; retrieve the real IP from the resource rather than guessing.

### 6.2. Choosing Connection Sources

| Workload | Outbound Path Required to Reach Private Endpoint |
|---|---|
| **Azure VM** in VNet | NIC/route from VM subnet to private endpoint IP |
| **AKS** | Pod/node DNS, VNet routes/NSGs, and node/Pod network topology |
| **App Service** | **Outbound VNet Integration** per plan/feature; an inbound App Service private endpoint does not substitute |
| **Azure Functions** | VNet Integration/outbound per hosting plan and features; check scaling/network |
| **Azure Container Apps** | Environment VNet integration, routing, DNS, and proper egress |
| **On-premises** | VPN/ExpressRoute or dedicated connectivity, DNS forwarding, and route to private IP |
| **Hosted CI/CD runner** | Public hosted agents lack VNet access; use private/self-hosted runners for data-plane deploys/tests |

### 6.3. Two Private Endpoints Do Not Connect Automatically

A database Private Endpoint only provides **an address to reach the database** in a subnet. It does not create:

- **Outbound VNet integration** for App Service/Functions if the workload isn't integrated yet.
- Peering/VPN/ExpressRoute between the application network and database network.
- DNS links/forwarding in other VNets.
- Database roles for workload identities.
- Automatic firewall rules for arbitrary workloads.

To connect from spoke A to a Private Endpoint in spoke B, both **routing and DNS** must span both networks. VNet peering allows traffic when configured, yet **peering does not automatically share/link Private DNS zones**.

### 6.4. Managing Multiple Private Endpoints and DNS

One database server can serve multiple networks/apps if properly designed. When multiple Private Endpoints exist for the same hostname across different VNets/regions, be very careful with Private DNS A records: **an improperly shared zone can return a private IP unroutable from another VNet**.

Solutions include regional/VNet-scoped DNS topologies, Azure Private DNS Resolver, conditional forwarding, and cleanly managed records. Never manually add multiple A records for one FQDN in a shared zone assuming clients "pick the nearest endpoint." Test resolution from each source.

## 7. Azure CLI Lab: Creating a Private Endpoint for Azure SQL Database

This lab focuses on **Private Endpoint for an Azure SQL Database logical server**, not Azure SQL Managed Instance or Flexible Server. **Use only an authorized test subscription/resource group**. Creating VNets, subnets, Private Endpoints, and Private DNS zones can incur charges; never run in production without change approval.

To avoid creating unrelated databases, assume you already have:

- An **Azure SQL logical server** and database `ordersdb` in the lab.
- An account/managed identity with sufficient **Azure RBAC** to create network resources and Private Endpoint connections, plus approval rights per resource/ownership.
- A workload **inside the VNet** or a test VM with SQL client/DNS tools.
- Safe login and read-test privileges; SQL `sysadmin` is unnecessary just to verify DNS.
- Public access still enabled until the private path is **verified end-to-end**.

### 7.1. Set Variables and Verify Subscription

~~~bash
az login

SUBSCRIPTION_ID="<lab-subscription-id>"
RG="rg-sql-private-lab"
LOCATION="southeastasia"
SQL_SERVER="<existing-sql-logical-server-name>"
SQL_DB="ordersdb"

VNET="vnet-sql-private-lab"
SUBNET_APP="snet-app"
SUBNET_PE="snet-private-endpoints"
PE_NAME="pe-sql-orders"
DNS_ZONE="privatelink.database.windows.net"
DNS_LINK="link-vnet-sql-lab"
DNS_ZONE_GROUP="sql-zone-group"

az account set --subscription "$SUBSCRIPTION_ID"
az account show --query "{id:id,name:name,tenantId:tenantId}" -o table
~~~

`<...>` values are placeholders; substitute real lab resources. Note that the SQL server's resource group may **differ** from the networking resource group. If separate, define `RG_SQL` and `RG_NETWORK` instead of assuming a single resource group.

Verify the existing server in the RG:

~~~bash
az sql server show \
  --resource-group "$RG" \
  --name "$SQL_SERVER" \
  --query "{id:id,fullyQualifiedDomainName:fullyQualifiedDomainName,publicNetworkAccess:publicNetworkAccess}" \
  --output json

az sql db show \
  --resource-group "$RG" \
  --server "$SQL_SERVER" \
  --name "$SQL_DB" \
  --query "{name:name,status:status}" \
  --output json
~~~

If the command returns `ResourceNotFound`, **do not create a separate production database**; verify your assigned subscription, logical server name, and resource group.

### 7.2. Create VNet and Subnets for the Lab

~~~bash
az network vnet create \
  --resource-group "$RG" \
  --name "$VNET" \
  --location "$LOCATION" \
  --address-prefixes 10.20.0.0/16 \
  --subnet-name "$SUBNET_APP" \
  --subnet-prefixes 10.20.1.0/24

az network vnet subnet create \
  --resource-group "$RG" \
  --vnet-name "$VNET" \
  --name "$SUBNET_PE" \
  --address-prefixes 10.20.2.0/24
~~~

These are **illustrative CIDRs**. Do not run in an existing VNet if `10.20.0.0/16` is already used or overlaps. If your organization manages VNets via Bicep/Terraform, use the IaC pipeline instead of manual commands. The app subnet may need delegation/integration settings per runtime, whereas the Private Endpoint subnet **must not be delegated to App Service**.

### 7.3. Get Resource ID and Create Private Endpoint

~~~bash
SQL_SERVER_ID=$(az sql server show \
  --resource-group "$RG" \
  --name "$SQL_SERVER" \
  --query id -o tsv)

az network private-endpoint create \
  --resource-group "$RG" \
  --name "$PE_NAME" \
  --location "$LOCATION" \
  --vnet-name "$VNET" \
  --subnet "$SUBNET_PE" \
  --private-connection-resource-id "$SQL_SERVER_ID" \
  --group-id sqlServer \
  --connection-name "sql-private-connection"
~~~

For an **Azure SQL Database logical server**, the group/subresource is typically `sqlServer`. Never copy `sqlServer` onto PostgreSQL/MySQL/Managed Instance; check the resource type and `az network private-link-resource list` or the service's documentation.

A Private Endpoint may be created in a pending-approval state depending on permissions and setup. Before proceeding, verify **connection state = Approved** per resource owner. If Pending/Rejected, do not consider the Private Endpoint operational.

~~~bash
az network private-endpoint show \
  --resource-group "$RG" \
  --name "$PE_NAME" \
  --query "{id:id,ipConfigs:ipConfigurations,connections:privateLinkServiceConnections}" \
  --output json
~~~

Depending on CLI/API version, IP/approval properties may reside in slightly different response structures; inspect full JSON if a query returns empty. CLI flags also evolve across versions, so check `az network private-endpoint create --help` in your deployment environment.

### 7.4. Create Private DNS Zone and VNet Link

~~~bash
az network private-dns zone create \
  --resource-group "$RG" \
  --name "$DNS_ZONE"

az network private-dns link vnet create \
  --resource-group "$RG" \
  --zone-name "$DNS_ZONE" \
  --name "$DNS_LINK" \
  --virtual-network "$VNET" \
  --registration-enabled false
~~~

For Private Endpoints targeting PaaS services, the DNS zone normally keeps **auto-registration disabled** because A records are managed/synced by the Private Endpoint DNS zone group, not VM hostname autoregistration.

### 7.5. Attach DNS Zone Group to the Private Endpoint

~~~bash
DNS_ZONE_ID=$(az network private-dns zone show \
  --resource-group "$RG" \
  --name "$DNS_ZONE" \
  --query id -o tsv)

az network private-endpoint dns-zone-group create \
  --resource-group "$RG" \
  --endpoint-name "$PE_NAME" \
  --name "$DNS_ZONE_GROUP" \
  --private-dns-zone "$DNS_ZONE_ID" \
  --zone-name "sql-zone-config"
~~~

A DNS zone group manages Private Endpoint DNS records automatically for the service. If your organization maintains a central DNS zone in another resource group, **do not create duplicate zones in each app RG** just to make commands run. Use the DNS-team-managed zone with proper permissions and peering/links.

### 7.6. Test DNS from the Actual Application Source

After configuring DNS and approving the connection, log into a VM/Pod/worker **inside a VNet with routing to the Private Endpoint**, then run:

~~~bash
nslookup "$SQL_SERVER.database.windows.net"

# On Linux with nc:
nc -vz "$SQL_SERVER.database.windows.net" 1433
~~~

On Windows PowerShell:

~~~powershell
Resolve-DnsName "<server>.database.windows.net"
Test-NetConnection "<server>.database.windows.net" -Port 1433
~~~

Expected results:

- `<server>.database.windows.net` resolves to the **private IP** bound to the Private Endpoint in your topology.
- TCP to the appropriate port succeeds over the private path.
- A SQL client using TLS and valid credentials completes **login/test queries**.

**`nc -vz` or `Test-NetConnection` only tests TCP, not TLS hostnames or SQL logins.** Next, test with a real driver/SQL client enforcing certificate validation and authentication.

### 7.7. Disable Public Access Only After Tests Pass

In an approved lab/private-only architecture:

~~~bash
# Action that can sever existing public clients:
az sql server update \
  --resource-group "$RG" \
  --name "$SQL_SERVER" \
  --public-network-access Disabled

az sql server show \
  --resource-group "$RG" \
  --name "$SQL_SERVER" \
  --query "{name:name,publicNetworkAccess:publicNetworkAccess}" \
  -o json
~~~

Flags to update public network access may vary by CLI/API version; check `az sql server update --help`. **Never run this just because private DNS resolves on one VM.** Before disabling, test **all** clients: App Service/Functions/AKS, on-premises, reporting, data migration tools, monitoring, and CI jobs needing data-plane access.

### 7.8. Verify Fail-Closed Behavior

After disabling public access:

1. Test **from private app/runtime**: private DNS, TLS login, and authorized read queries must succeed.
2. Test **from an external source without VPN/private routing**: data-plane connections must fail unlike before.
3. Verify monitoring and scheduled jobs, not just one ad-hoc request.
4. Confirm firewall exceptions/public IP rules are not needlessly retained in violation of policy.
5. Record resource IDs, private IP/DNS zone/connection status, change ticket, and rollback plan.

**Fail-closed** means unauthorized external paths must fail—never "fix" errors by disabling TLS verification or giving the app the SQL admin password.

## 8. Verifying Connectivity Across Three Layers: DNS, TCP, and Login/Query

No single command validates everything. A reliable verification approach covers:

### 8.1. Layer 1: Which Address Does DNS Return?

~~~bash
nslookup <server>.database.windows.net
~~~

Query from the **actual container/VM/worker runtime**, not just Azure Cloud Shell or an admin laptop. Azure Cloud Shell is generally outside your private VNet unless specifically configured in an isolated VNet environment.

If DNS returns a public IP, check:

- Does the Private DNS zone have the right name and A record for the private endpoint?
- Does the source's VNet have the link/private resolver/forwarder configured?
- Does custom DNS conditionally forward the zone to the right resolver?
- Have container resolvers/caches picked up the updated config?
- Are multiple Private Endpoints sharing the hostname with a record pointing to another VNet's IP?

### 8.2. Layer 2: Is There a TCP Route to the Listener?

~~~bash
nc -vz <server>.database.windows.net 1433
~~~

If it times out, check VNet integration, peering, NSGs/UDRs, firewalls/NVAs, private endpoint approval, and the exact port. **A TCP timeout is usually not a SQL password error**—the login phase hasn't even started.

### 8.3. Layer 3: TLS/Auth/Database Query

Example using a `sqlcmd` version supporting Microsoft Entra authentication:

~~~bash
sqlcmd \
  -S "tcp:<server>.database.windows.net,1433" \
  -d "ordersdb" \
  -G \
  -Q "SELECT DB_NAME() AS DatabaseName;"
~~~

`-G` syntax, identity selection, and encryption flags differ between modern `sqlcmd` releases and older drivers/OSes. **Check `--help` for your `sqlcmd` version**, use a token from the right tenant, and confirm the principal has a database user/permissions. Never skip certificate checks just to get a 2xx result.

If SQL login is rejected, check database principals, Microsoft Entra admin/config, token audience, expiry, and SQL grants. If login succeeds yet `SELECT` returns permission denied, **network and TLS are working**, and only specific SQL permissions are missing.

### 8.4. Layered Result Matrix

| DNS | TCP | TLS + Login | Interpretation |
|---|---|---|---|
| Wrong | Often fails or hits wrong target | Often fails | Fix DNS/resolver first |
| Correct private IP | Timeout | Cannot reach | Check routes/NSGs/approval/ports or server listener |
| Correct private IP | Succeeds | Certificate error | Hostname/certificate chain/TLS driver |
| Correct private IP | Succeeds | Login failed | Token/password/user/Entra/database config |
| Correct private IP | Succeeds | Login OK, query permission denied | Missing database `GRANT`/role |
| Correct private IP | Succeeds | Query OK | One test path passes; does not replace full workload testing |

**Test inside production runtimes:** one AKS Pod succeeding does not prove App Service Functions, CI runners, and on-premises apps connect too; they may use different DNS and routes.

## 9. TLS: Even Private Paths Require Server Authentication

**Private Link does not make TLS redundant.** A private IP describes only the network path; connections between drivers and databases still require protection against eavesdropping, spoofing, and tampering in transit.

### 9.1. Three Questions in a TLS Handshake

1. **Encryption:** do client and server negotiate a secure TLS version and cipher?
2. **Certificate trust:** does the client trust the CA/chain of the certificate presented by the server?
3. **Hostname verification:** does the certificate match the **FQDN the client intended to connect to**?

Switching a connection string from the FQDN to a Private Endpoint IP typically breaks step 3. **Never tell the driver to skip certificate validation to "fix" hostname mismatch**; fix DNS and keep the canonical FQDN.

### 9.2. Azure SQL Connection String (Sample)

~~~properties
# For Java apps using Microsoft JDBC Driver for SQL Server
jdbc:sqlserver://<server>.database.windows.net:1433;database=ordersdb;encrypt=true;trustServerCertificate=false;hostNameInCertificate=*.database.windows.net;loginTimeout=15;
~~~

This illustrates **TLS settings**, excluding authentication mode. In many newer driver versions, `encrypt` has defaults or supports `strict`/`mandatory`; use an approved driver version and verify compatibility with Azure SQL. Never hard-code passwords in JDBC URLs.

For `Microsoft.Data.SqlClient`/.NET, an illustrative config:

~~~text
Server=tcp:<server>.database.windows.net,1433;
Database=ordersdb;
Encrypt=True;
TrustServerCertificate=False;
Connect Timeout=15;
~~~

In code, add Entra/managed identity authentication per driver and runtime. `Encrypt=True` paired with `TrustServerCertificate=True` fails true server authentication.

### 9.3. PostgreSQL TLS Settings

~~~text
host=<server>.postgres.database.azure.com
port=5432
dbname=ordersdb
sslmode=verify-full
sslrootcert=/path/to/trusted-ca-bundle.pem
~~~

In PostgreSQL drivers/libpq, `sslmode=verify-full` enforces both trust-chain verification **and** valid hostname matching. `sslmode=require` encrypts without always enforcing the same hostname validation semantics as `verify-full`; check your driver and Azure Database for PostgreSQL Flexible Server's certificate policy.

Root/intermediate certificates can rotate on Azure schedules. **Never pin a single leaf certificate or sole CA without a rotation plan.** Update CA bundles/trust stores per policy and test ahead of rollovers.

### 9.4. MySQL TLS Settings

Example with a MySQL CLI/driver supporting server identity verification:

~~~bash
mysql \
  --host="<server>.mysql.database.azure.com" \
  --port=3306 \
  --ssl-mode=VERIFY_IDENTITY \
  --ssl-ca="/path/to/trusted-ca-bundle.pem" \
  --user="<db-user>" \
  --database="ordersdb"
~~~

Never pass real passwords via `--password=...` into shell history. MySQL user/password or Entra token auth depends on server features and drivers. **Choose `VERIFY_IDENTITY` once trust stores/CAs and hostnames are properly configured**; never downgrade to `DISABLED` just to run over Private Endpoint.

### 9.5. Checking Certificate Chains and Expiration

A production outage can happen when clients run outdated runtimes/CA bundles after Azure rotates a certificate chain:

- Track JDBC/.NET/ODBC/libpq/MySQL connector versions.
- Track CA trust stores and database minimum TLS version roadmaps.
- Test certificate rotation in production-like staging.
- Never forward secrets or password-laden connection strings to arbitrary diagnostic collectors.
- When TLS handshakes fail, inspect **chain/trust, hostname, and protocol version** errors before editing firewalls.

## 10. Identity and Database Permissions: Who Can Log In and Read Data?

Networking decides only **whether traffic reaches the listener**. Authentication identifies **who the principal is**; database authorization defines **what the principal may do**. An architecture using a Private Endpoint where the app connects with a SQL admin password still carries a massive blast radius.

### 10.1. Distinguish Three Types of Permissions

| Permission | Example | Does Not Mean |
|---|---|---|
| **Azure RBAC control plane** | Contributor creating DB server/Private Endpoint; Network Contributor configuring subnets | Automatic `SELECT` on all tables |
| **Entra/workload identity authentication** | Managed identity issued an access token for Azure SQL | Automatic SQL user/grants in every database |
| **Database authorization** | Database user granted `GRANT SELECT` on schema `sales` | Ability to create Azure Private Endpoints or edit public network access |

Manage all three layers independently, auditing who/what changes permissions in each layer.

### 10.2. Microsoft Entra ID with Azure SQL

With Azure SQL Database, enable **Microsoft Entra authentication** and use an App Service/Functions/AKS workload managed identity as the principal. General workflow:

1. Create or enable a managed identity for the app per runtime.
2. Configure a **Microsoft Entra admin** on the Azure SQL logical server per governance.
3. Connect as a principal authorized to create database users from external providers.
4. Inside the **target application database**, create a user representing the Entra principal and grant least privilege.
5. Have the app acquire access tokens via Azure Identity/drivers; avoid storing SQL admin passwords.
6. Verify token audience, tenant, refresh/rotation, and SQL permissions from the real runtime.

Illustrative SQL inside `ordersdb` (requires valid principal/permissions):

~~~sql
-- DBA command run inside ordersdb; MI name is illustrative.
CREATE USER [mi-orders-api-prod] FROM EXTERNAL PROVIDER;

GRANT SELECT ON SCHEMA::sales TO [mi-orders-api-prod];
GRANT INSERT, UPDATE ON SCHEMA::sales TO [mi-orders-api-prod];
~~~

**Never grant `db_owner` or `sysadmin` to runtime just because a permission error occurred.** Grant `SELECT/INSERT/UPDATE/EXECUTE` on exact objects/scopes needed for functionality. A read-only reporting API should use its own read-only identity; never share a managed identity with the migration pipeline.

**Nuance:** creating Entra principals can depend on name uniqueness, object IDs, directory resolution capability of the SQL server's identity, and Entra permissions. For duplicate display names/service principals or multi-tenant setups, advanced identification syntax/`WITH OBJECT_ID` may be required per supported features; verify against your Azure SQL version rather than guessing.

### 10.3. Token Audience and Lifetime

For Azure SQL, tokens are typically requested for the SQL resource/scope:

~~~text
https://database.windows.net/.default
~~~

**That is the token request scope**, not a Private Endpoint database hostname. If an app requests an Azure Resource Manager token and uses it to log into Azure SQL, the token audience mismatches and login fails.

Long-running apps must use drivers/SDKs supporting **token refresh**, connection pooling, and sensible retries. Never fetch one token at startup and reuse it forever; tokens expire.

### 10.4. Password Authentication When Entra Is Unavailable

Some legacy clients/engines/tools still use database usernames/passwords. In those cases:

- Create a **dedicated account per workload**; never use the administrator account.
- Store secrets in Key Vault or an approved secret store—never in Git or Dockerfiles.
- Rotate periodically per policy with safe transition overlaps.
- Restrict database grants and network exposure.
- Enforce TLS/certificate verification; passwords over a private network do not replace encryption.
- Monitor login failures and audit changes; forbid logging passwords or full connection strings.

**Never use Private Endpoint as an excuse for weak passwords.** Network isolation is an extra defense layer, not a replacement for strong authentication.

### 10.5. Application-Level Authorization

Suppose `orders-api`'s managed identity holds `SELECT` on the Orders table. The backend still must verify:

- Is the request's tenant/user authorized to read that specific `orderId`?
- Which business roles may update/cancel an order?
- Are Row-Level Security, views, or stored procedures constraining data access?
- Is SQL injection prevented with parameterized queries?
- Are sensitive actions audited while avoiding query log exposure?

**Private networking and managed identity do not isolate customer data** if application queries omit tenant/resource filters. That remains an application/database design responsibility.

## 11. Safe Java/JDBC Applications and Connection Pools

A Java app connecting to Azure SQL Database combines **private DNS**, **TLS driver settings**, **authentication**, and **SQL permissions**. SQL running on a DBA's laptop does not prove the Java app's service account holds permissions or valid VNet routes.

### 11.1. Java Example with Microsoft Entra Default Credential

The example below illustrates **Microsoft JDBC Driver for SQL Server** versions supporting `ActiveDirectoryDefault` and required Azure Identity libraries. The Java process must have a valid credential source (managed identity in Azure, developer credentials locally):

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.Statement;

public class AzureSqlConnectivityCheck {
    public static void main(String[] args) throws Exception {
        String host = System.getenv("SQL_HOST");
        String database = System.getenv("SQL_DATABASE");
        if (host == null || database == null) {
            throw new IllegalStateException(
                "SQL_HOST and SQL_DATABASE must be configured");
        }

        String url = "jdbc:sqlserver://" + host + ":1433;"
            + "databaseName=" + database + ";"
            + "encrypt=true;"
            + "trustServerCertificate=false;"
            + "loginTimeout=15;"
            + "authentication=ActiveDirectoryDefault;";

        try (Connection connection = DriverManager.getConnection(url);
             Statement statement = connection.createStatement();
             ResultSet result = statement.executeQuery(
                 "SELECT DB_NAME() AS db_name")) {
            if (result.next()) {
                System.out.println("Database: " +
                    result.getString("db_name"));
            }
        }
    }
}
~~~

Example environment variables:

~~~bash
export SQL_HOST="<server>.database.windows.net"
export SQL_DATABASE="ordersdb"
~~~

**Technical note:** `ActiveDirectoryDefault` is not available in every Microsoft JDBC Driver release. It requires compatible driver versions and Azure Identity dependencies; check driver release notes, managed identity setup, and runtime before use. An Entra user signed into the Azure Portal **does not automatically have a database user**; create SQL users and grants as shown in Section 10.

**Never log connection strings containing credentials.** With token authentication, never log raw access tokens or SQL exception details containing sensitive data in public places.

### 11.2. Connecting Through a Connection Pool

In production APIs, opening a new SQL connection per request without pooling causes:

- Repeated TCP/TLS handshakes and authentication overhead.
- Rising latency under high request volume.
- Exhausting sessions/connections during scale-out.
- Database resource exhaustion and login throttling.

Use a pool like HikariCP via Spring Boot/Micronaut or a supported driver/pool, while ensuring you:

1. Size **maximum pool size relative to app instance count** and database connection capacity.
2. Set sensible connection validation/timeouts to avoid keeping broken connections after failover.
3. Monitor active/idle/pending connections and SQL connection failures.
4. Design retries by error category, with backoff and transaction idempotency.
5. Ensure tokens/credentials refresh per driver support; never pin a static token at pool startup.
6. Never enable infinite retries during database/network outages.

### 11.3. Calculating Total Connection Budget

Suppose there are **8 replicas**, each configured with a max pool of **20 connections**:

\[
8 \times 20 = 160\ \text{potential connections}.
\]

If the database or supporting services lack headroom, scaling out the app triggers hundreds of concurrent logins/queries. Private Endpoint changes only the **network path**—it does not increase database CPU, IOPS, or connection limits.

### 11.4. Reading an Order with a Parameterized Query

~~~java
// Executed on an already authenticated Connection.
String sql =
    "SELECT Id, Status FROM sales.Orders WHERE Id = ?";

try (var statement = connection.prepareStatement(sql)) {
    statement.setString(1, orderId);
    try (var result = statement.executeQuery()) {
        while (result.next()) {
            // Process only data for the authorized order.
        }
    }
}
~~~

Private networking and `PreparedStatement` are still insufficient if the app forgets to **verify tenant/customer ownership** before querying or omits authorization filters. Parameterization stops SQL injection; authorization ensures the user is permitted to access the resource.

## 12. PostgreSQL and MySQL Flexible Server: Do Not Copy Azure SQL Steps

**Azure Database for PostgreSQL Flexible Server** and **Azure Database for MySQL Flexible Server** offer two main private connectivity paths:

1. **Private access with VNet integration:** deploys the server inside a delegated subnet using private DNS per that model.
2. **Private Link/Private Endpoint:** server uses a network mode supporting Private Link, with a Private Endpoint in the client VNet and a matching `privatelink.*` Private DNS zone.

Creation/modification options, region/SKU conditions, and Private Link support vary by service and version. **Do not assume a Flexible Server created in private-access mode can toggle Private Endpoint in one click like Azure SQL Database**, or switch public ↔ VNet-injected private access without recreating/migrating.

### 12.1. PostgreSQL Flexible Server

In **VNet-injected private access**:

- The server binds to a subnet with proper delegation (`Microsoft.DBforPostgreSQL/flexibleServers` per requirements).
- A Private DNS zone is configured per Flexible Server rules; zone names may be custom domains ending in `postgres.database.azure.com` per current requirements.
- Clients with proper routing/DNS connect over the standard PostgreSQL FQDN.
- Do not assume `privatelink.postgres.database.azure.com` is the default zone for **all** private access modes.

In **Private Link** mode (when supported):

- The server meets networking mode and prerequisites for creating a Private Endpoint.
- Uses a Private Link-specific Private DNS zone, typically `privatelink.postgres.database.azure.com`.
- Apps connect to `<server>.postgres.database.azure.com`, port 5432, TLS `verify-full` with matching CA trust.
- Public access/firewall policies must be checked separately; Private Endpoint does not guarantee public paths are closed.

**Read-only** commands to inspect status:

~~~bash
az postgres flexible-server show \
  --resource-group "<rg>" \
  --name "<postgres-flexible-server>" \
  --output json

az postgres flexible-server firewall-rule list \
  --resource-group "<rg>" \
  --name "<postgres-flexible-server>" \
  --output table
~~~

Inspect the actual network model before searching for Private Endpoint creation commands. If the server already sits in a delegated subnet under private-access mode, follow that network topology instead of running `az network private-endpoint create --group-id sqlServer`.

### 12.2. MySQL Flexible Server

With **VNet-integrated private access**, MySQL Flexible Server uses a delegated subnet and private DNS per service rules. With **Private Link**, where supported by networking mode/features, it uses a Private Endpoint and typically zone `privatelink.mysql.database.azure.com`.

~~~bash
az mysql flexible-server show \
  --resource-group "<rg>" \
  --name "<mysql-flexible-server>" \
  --output json

az mysql flexible-server firewall-rule list \
  --resource-group "<rg>" \
  --name "<mysql-flexible-server>" \
  --output table
~~~

These are **read-only inspection** commands, modifying nothing. Verify which networking model the server uses before changing public access/firewalls. Use hostname `<server>.mysql.database.azure.com`, port 3306, and TLS validation via a supported driver.

### 12.3. PostgreSQL/MySQL Authentication Differs from SQL Server

| Engine | Common Authentication | What to Verify |
|---|---|---|
| **Azure SQL** | SQL authentication or Entra token/managed identity | SQL contained users/roles and SQL token audience |
| **PostgreSQL Flexible Server** | PostgreSQL user/password or Microsoft Entra authentication per config | Entra server setup, PostgreSQL role mapping/GRANT, token audience, and driver |
| **MySQL Flexible Server** | MySQL user/password or Microsoft Entra authentication where supported | MySQL user/GRANT, role/driver plugin, and token setup |

For instance, PostgreSQL uses `GRANT SELECT ON TABLE ...` in PostgreSQL syntax—**never copy** Azure SQL's `CREATE USER [...] FROM EXTERNAL PROVIDER`. Each engine has its own SQL dialect, role model, certificate requirements, and authentication plugins.

### 12.4. Database Firewalls for Flexible Server

For servers still allowing **public access**, IP firewall rules guard the public path per feature support. For **VNet-injected private access** servers, access is governed mainly via VNet/subnet/DNS/routing/NSGs and database auth. For **Private Link**, verify Private Endpoint approval, DNS zones, and the server's public network access policy.

Never transfer Azure SQL logical server's "Allow Azure services and resources" onto PostgreSQL/MySQL servers without reviewing each service's design/features; if broad Azure IP exceptions exist, understand their scope before enabling.

### 12.5. Azure SQL Managed Instance

Azure SQL Managed Instance uses a **VNet-native** model with its own listeners and network prerequisites:

- The instance resides in a delegated subnet meeting Managed Instance requirements.
- Connectivity from other VNets or on-premises requires peering/VPN/ExpressRoute/DNS/routing.
- Public endpoints, private endpoints, and port connectivity (where configured/supported) differ from Azure SQL Database logical servers.
- Do not blindly apply Private DNS zone `privatelink.database.windows.net` and group ID `sqlServer` to MI.
- Verify subnet delegation, route tables, NSGs, SQL connection policies, and listener ports per specific MI deployment.

**General rule:** identify **engine and network model first**, then pick commands, zones, and ports. An Azure SQL Database guide is not a universal guide for every Azure relational database.

## 13. Apps Connecting to Databases Over Private Networks: Runtime Topologies

### 13.1. App Service → Azure SQL Private Endpoint

~~~mermaid
flowchart LR
    USER[Web browser] --> APP[Azure App Service]
    APP --> VNET[App Service outbound VNet Integration]
    VNET --> DNS[Private DNS zone / resolver]
    DNS --> PE[SQL Private Endpoint 10.20.2.4]
    PE --> SQL[(Azure SQL Database)]
    APP -. Managed Identity token .-> SQL
    APP -. TLS verification .-> SQL
~~~

**Common confusion:** a **Private Endpoint on App Service** is an **inbound** path for clients reaching the website/app privately; it **does not replace outbound VNet Integration** for the app calling a SQL Private Endpoint. Outbound VNet Integration (per plan/features) and proper egress/DNS are required.

Verify from the **runtime**: have the app execute a test read query under its actual managed identity, logging correlation/latency without secrets.

### 13.2. AKS Pod → PostgreSQL Flexible Server

~~~mermaid
flowchart LR
    POD[AKS Pod / Workload ID] --> CORE[AKS DNS + network]
    CORE --> ZONE[Private DNS resolution]
    ZONE --> SERVER[(PostgreSQL Flexible Server)]
    POD -. TLS verify-full .-> SERVER
    POD -. DB role / Entra token when configured .-> SERVER
~~~

Distinguish carefully:

- **Pod DNS** and actual cluster DNS/CoreDNS forwarding.
- CNI/network policies/NSGs and routes from node/Pod subnets to the database.
- Whether the server uses **VNet-injected private access** or **Private Link**.
- **Kubernetes service account/workload identity** for fetching Azure tokens, distinct from SQL/PG roles.
- Replica counts and connection pools to avoid overloading the database.

**Never test using a privileged debug Pod and assume production Pods work.** NetworkPolicies, service accounts, environments, and DNS configs may differ.

### 13.3. Azure Functions → MySQL Flexible Server

Azure Functions run on hosting plans with varying VNet Integration limits, scaling behavior, and cold starts. Verify plan networking capabilities before enforcing private-only databases:

1. Functions runtime has valid VNet integration.
2. DNS resolver returns a private IP for `<server>.mysql.database.azure.com`.
3. TCP 3306 and TLS `VERIFY_IDENTITY` succeed.
4. Credentials/Entra identity hold proper SQL grants.
5. Scaling/concurrency will not explode connection pools.
6. Retry logic avoids duplicate business transactions.

### 13.4. On-Premises → Azure SQL Over VPN/ExpressRoute

When a datacenter app needs to reach an Azure SQL Private Endpoint:

- Private routing exists over **VPN/ExpressRoute** to the VNet containing the Private Endpoint.
- An on-premises DNS conditional forwarder forwards private database zone queries to a resolver that can read Azure Private DNS.
- On-premises firewalls/NSGs/NVAs permit required service TCP traffic.
- The app keeps using the **canonical server FQDN** with TLS hostname verification.
- Failover and redundant DNS paths are tested.

**VPN/ExpressRoute carries packets; it does not automatically provide DNS resolution.** A working IP route can still fail if on-premises DNS returns a public address.

## 14. Migrating from Public Endpoints to Private-Only Without Unintended Outages

The highest-risk mistake is **disabling public network access before every consumer has moved to private paths**. A database often serves many clients beyond the primary API: reporting tools, batch jobs, DBA utilities, data pipelines, monitoring, or partner integrations. Missing one client breaks it at cutover.

### 14.1. Phased Workflow

~~~mermaid
flowchart TD
    INV[Inventory all clients and connections] --> PLAN[Design VNet, Private Endpoint, DNS, RBAC]
    PLAN --> BUILD[Provision PE + approve + DNS zone/link]
    BUILD --> TEST[Validate DNS / TCP / TLS / login from each runtime]
    TEST --> READY{All critical clients pass?}
    READY -->|No| FIX[Fix network/DNS/identity; keep public path controlled]
    FIX --> TEST
    READY -->|Yes| CUT[Approved change: disable public network access]
    CUT --> CHECK[Verify private success and public fail-closed]
    CHECK --> MON[Monitor jobs, application SLO, security logs]
    MON --> CLOSE[Document architecture and retire unused firewall exceptions]
~~~

Large systems do not need a "big bang." Create the Private Endpoint and DNS first, migrate workloads in groups, verify stability, and **only at the end** close the public endpoint when zero clients depend on it.

### 14.2. Client Inventory Table

| Consumer | Runtime/Network | FQDN/Port | Identity | Private Verified? |
|---|---|---|---|---|
| Orders API | App Service VNet Integration | SQL FQDN / 1433 | Managed identity | Must test from app |
| Invoice worker | Azure Functions | SQL FQDN / 1433 | Managed identity | Must test from worker |
| Data ETL | VM or private pipeline runner | SQL FQDN / 1433 | Managed identity/service principal | Must test on job schedule |
| DBA operations | VPN/ExpressRoute | SQL FQDN / 1433 | Entra DBA role | Must test VPN + DNS |
| Reporting | Power BI/data gateway or suitable service | SQL FQDN / 1433 | Dedicated identity | Must verify topology |
| External integration | Third-party client | Per contract | Dedicated principal | May need gateway/alternative design |

Never treat `az sql server firewall-rule list` as a complete consumer list; IP firewall rules do not prove who is actively connecting. Combine application inventories, database audit/connection metrics, logs, and team ownership.

### 14.3. Preparing a Rollback Without Recklessly Lowering Security

A rollback plan must document:

- Criteria for declaring a failed cutover (e.g., rising API 5xx, SQL write jobs failing).
- Which consumer/network lost connectivity and which FQDN/DNS/route is failing.
- Whether **fixing DNS/routing/identity** can restore private connectivity quickly.
- If public access must temporarily reopen: who approves, how tightly IPs are restricted, and the expiration time.
- How the temporary exception is audited and closed immediately after remediation.

**Never write a runbook saying "enable Allow Azure services on timeout."** That opens a much wider scope than needed. During an incident, fixing a DNS route may be safer than granting a broad firewall exception; if break-glass is unavoidable, keep it minimal, owned, and time-boxed.

### 14.4. Do Not Change Everything Simultaneously

If during one change window you simultaneously:

1. Rotate the database admin password;
2. Enable Private Endpoint;
3. Change custom DNS;
4. Disable public access;
5. Upgrade the JDBC driver version;
6. Modify the database schema;

isolating the root cause when something breaks becomes nearly impossible. Split changes into independently verifiable phases backed by versioned IaC and rollback evidence.

### 14.5. DNS Caching and Client Reconnects

After private DNS updates, some clients retain stale DNS caches or connection pools bound to old IPs. During cutover:

- Check resolver TTLs and runtime/JVM/OS DNS refresh behavior.
- Confirm newly opened connections use the updated DNS answer.
- Plan graceful pool recycling/restarts within the change window.
- Never delete old endpoints while clients/connections still rely on them.
- Watch reconnect behavior after failovers or scale-outs whenever networking changes.

**A fresh passing `nslookup` does not prove a long-lived connection pool opened new connections over the private path.** Verify live application connection behavior and diagnostics.

## 15. Troubleshooting: Separating DNS, TCP, TLS, Firewalls, and Permissions

When a database refuses connections, investigate in order: **target → DNS → route/port → TLS → login → database operation**, rather than randomly toggling firewalls and passwords.

### 15.1. Symptom Table

| Symptom | Common Cause | How to Check |
|---|---|---|
| DNS returns public IP inside VNet | Missing Private DNS zone/link or resolver forwarding | `nslookup` from runtime, zone A records, VNet links |
| DNS returns no answer | Broken DNS server/forwarder, wrong zone, policy block | Resolver config, conditional forwarding, DNS logs |
| DNS returns private IP, TCP times out | NSG/UDR/Firewall, PE pending, VNet lacks route | Port test, PE approval, effective routes, subnet policies |
| VNet VM connects, App Service fails | App Service lacks outbound VNet Integration or uses different DNS | App VNet Integration plan, routes, DNS from runtime |
| AKS debug Pod connects, production Pod fails | NetworkPolicy, service account, different Pod DNS | Namespace/Pod policies, node/Pod routes |
| SQL error: client IP not allowed/public access | Client hitting public endpoint instead of PE | DNS, actual destination IP, SQL network state |
| TLS hostname mismatch | Client using raw private IP/wrong alias; cert hostname mismatch | Canonical FQDN, driver hostname verification |
| TLS certificate chain untrusted | Outdated driver trust store, missing CA bundle | Update CA bundle/driver, check chain and expiry |
| SQL login failed | Wrong Entra token audience/tenant, missing user, wrong password | Principal, token source, SQL auth config |
| PostgreSQL `no pg_hba.conf entry` or SSL mismatch | Mismatched security/config/transport mode | PG Flexible Server logs/network/TLS/roles |
| Query permission denied | Missing SQL GRANT/role despite network and login success | Check effective database permissions |
| Connections drop on failover | Stale connection pool, DNS/routing, weak retries | Pool health, transient retries, failover topology |
| Mass timeouts after scale-out | Oversized pools, overloaded DB, SNAT/routes | Database metrics, connection pools, runtime scale |
| Private Endpoint created, status Pending | Not yet approved by database resource owner | PE connection state/approval workflow |
| On-premises resolves public IP | DNS forwarder not querying Azure Private DNS | Private DNS Resolver, conditional forwarding, VPN routes |
| CI job deploying SQL schema cannot reach private DB | Public hosted runner lacks private network path | Self-hosted/private runner, approved network path |

### 15.2. Layered Runbook

**Layer 0 — Confirm scope:**

~~~bash
az account show \
  --query "{id:id,name:name,tenantId:tenantId}" \
  -o table

az sql server show \
  --resource-group "$RG" \
  --name "$SQL_SERVER" \
  --output json
~~~

Confirm server FQDN, database name, public access setting, and exact Private Endpoint resource ID. Never rely on a similarly named server in another subscription.

**Layer 1 — DNS:** from the failing runtime, run `nslookup`/`Resolve-DnsName`. Does the final answer point to the right private endpoint IP? Check custom DNS/hub-spoke forwarding.

**Layer 2 — Network/port:** is TCP 1433/5432/3306 reachable? Are VNet integration/peering/Private Endpoint approval intact? Do NSG/UDR/firewall logs show denies?

**Layer 3 — TLS:** does the driver report certificate mismatch, trust chain, or protocol version errors? Use the **canonical FQDN**, update CA/drivers, and keep certificate validation on.

**Layer 4 — Authentication:** are token audience/issuer/expiry, SQL/PG/MySQL user, Microsoft Entra admin, and login configuration correct?

**Layer 5 — Authorization:** do queries report `permission denied`? Does the database user hold grants on the right schema/operations?

**Layer 6 — Performance:** are session/pool counts, CPU/IO, blocking, deadlocks, service saturation, or retries climbing?

**Layer 7 — Recovery:** fix the true failing layer, test business requests/transactions, document root cause, and sync IaC/docs.

### 15.3. A Very Common Mistake

~~~text
App reports:
  Connection timeout to orders-sql-prod.database.windows.net:1433

Developer assumes:
  "SQL password wrong, open firewall to all Azure services."

Correct investigation:
  1. nslookup inside App Service runtime → PUBLIC IP
  2. Check App Service outbound VNet Integration → not configured
  3. Configure proper VNet Integration and private DNS resolution
  4. TCP now reaches private endpoint
  5. TLS + Entra SQL login succeeds
  6. No broad public firewall exception needed
~~~

**A TCP-layer timeout message is never enough to infer bad SQL credentials.** Each step needs independent measurement.

### 15.4. Distinguishing Azure Control-Plane 401/403 from Database Logins

An engineer may hit **403 Azure RBAC** when creating a Private Endpoint, **SQL error 18456** logging into Azure SQL, or **permission denied** querying a table; these belong to three separate management planes.

- **403 creating resources:** check Azure RBAC, deny assignments, policies, provider registration, and Private Endpoint approval rights.
- **Login failed:** check tokens/passwords, server/database principals, Entra settings, and driver auth.
- **SELECT denied:** check database GRANTs/roles, row-level policies, and app permissions.

Never grant subscription Owner to runtime just because a `SELECT` query was denied; it **does not create** SQL database grants and severely expands security risk.

## 16. Observing Private Database Connectivity

A dashboard showing 20% database CPU can miss widespread failures caused by DNS or Private Endpoint connection state. Collect logs and metrics across both the **network plane and database/application planes**.

### 16.1. Data Sources

| Source | Signals to Watch | Notes |
|---|---|---|
| **Azure SQL / PostgreSQL / MySQL metrics** | Successful/failed connections, CPU/IO/storage, sessions, availability per engine | Metric names/dimensions differ per service |
| **Database audit/diagnostic logs** | Login failures, query activity, and permission changes per features | Must enable proper config and minimize PII |
| **Private Endpoint connection state** | Approved/Pending/Rejected, NIC/IP, zone group | Creating a PE does not mean the connection is Approved |
| **Private DNS zones/resolver** | A records, VNet links, DNS queries/forwarding | Verify from the target VNet/client |
| **NSGs/Firewalls/Network Watcher** | Traffic allow/deny, routes, and reachability | Logs/troubleshooting support depend on config and region |
| **App Insights/OpenTelemetry** | Database dependency duration, exceptions, connection timeouts | Requires app-side instrumentation/sampling |
| **Azure Activity Log** | Who changed public access/firewalls/Private Endpoints/RBAC | Does not replace database-level audits |
| **Azure Cost Management** | Private Endpoint, DNS resolver, network, and database costs | Break down by owner/environment/region |

Never assume creating a Log Analytics workspace automatically collects all database login events. Configure diagnostic settings/auditing and verify schemas/retention, especially for PostgreSQL/MySQL.

### 16.2. Recommended Indicators

1. **Database connection error rate** by app instance/engine.
2. **TCP connect time** and **TLS handshake/login latency** where instrumented.
3. **DNS resolution failures/private-vs-public answers** from synthetic probes inside the VNet.
4. **Successful business transaction rate**, e.g., order creation/profile reads.
5. **Database active sessions, CPU, IO, deadlocks, connection pool wait**.
6. **Private Endpoint state** and Activity Log changes.
7. **SQL/PG/MySQL failed logins** and user/role permission changes.
8. **Unexpected public connectivity** post private-only cutover (negative test).
9. **TLS certificate trust failures** and driver/runtime exceptions.
10. **RPO/RTO/failover readiness** from periodic DR drills.

### 16.3. Alerts with Owners and Runbooks

| Alert | Impact | Response |
|---|---|---|
| Private Endpoint connection not Approved | Apps may fail to reach database | Check PE approval/resource ownership |
| Private DNS probe returns public IP | Traffic may route publicly or get blocked | Check DNS zones/links/forwarding |
| Connect timeouts spike after deploy | Route/NSG/firewall or database overload | Triage network layer, then database |
| Login failures spike while TCP succeeds | Token/identity/password/SQL user issue | Check Entra/SQL roles/drivers |
| Query denials spike | SQL permissions changed | Audit role grants and recent app releases |
| Pool exhaustion | App scale or DB capacity mismatch | Cap concurrency, size pools, check DB capacity |
| Public access enabled outside change window | Exposure risk | Security incident review, Azure Policy/remediation |

**"Database unavailable" alerts must distinguish private-path failures from database service health.** If private DNS breaks, scaling up DB compute solves nothing. If DB CPU hits 100% and pool waits climb, adding another Private Endpoint solves nothing.

### 16.4. Safe Logging

An app might log:

~~~json
{
  "service": "orders-api",
  "environment": "production",
  "dbEngine": "azure-sql",
  "dbHost": "orders-sql-prod.database.windows.net",
  "networkPath": "private-endpoint",
  "operation": "GetOrder",
  "durationMs": 47,
  "success": true,
  "correlationId": "req-c4a91"
}
~~~

**Never log passwords, access tokens, secret-bearing connection strings, customer data tables, or full SQL results.** Note that `networkPath=private-endpoint` in this sample is only an application label; proving the actual network path requires checking DNS/routing/Private Endpoint logs rather than trusting a logged string.

### 16.5. Synthetic Tests from Inside and Outside

A strong strategy uses **two separate checks**:

- **Positive test inside VNet:** resolves private IP, TCP succeeds, TLS/Entra login and authorized query pass.
- **Negative test outside private network:** once public network access is disabled, data-plane connections over the Internet fail.

Never use real production customer records for synthetic transactions; use synthetic test data or harmless read-only queries under tightly scoped permissions. Synthetic probes also need dedicated identities and must keep passwords/tokens out of monitoring outputs.

## 17. High Availability, Failover, and Disaster Recovery

A private database does not automatically become **highly available**. Private Endpoint solves network access; HA/DR still depends on database service tiers, replicas, backups, regional failovers, DNS, and app reconnection logic.

### 17.1. Four Layers Required to Be Ready at Failover

~~~mermaid
flowchart TD
    DR[Database failover / disaster recovery] --> BACKEND[Database primary / secondary available]
    BACKEND --> DNS[Correct listener FQDN and DNS answers]
    DNS --> ROUTE[Private Endpoint + VNet routes reachable]
    ROUTE --> AUTH[TLS + identity + DB permissions valid]
    AUTH --> APP[App reconnects, retries safely, resumes business processing]
~~~

If a new replica is healthy yet the app points to a private IP from an old endpoint, traffic stays broken. **Never hard-code private IPs** in connection strings; use service-supported listener FQDNs and design Private Link/DNS for both primary and DR paths.

### 17.2. Azure SQL Database Failover Groups

Azure SQL Database can use **failover groups/geo-replication** depending on tier and support. When using failover groups:

- Apps should use the **failover group listener** or supported hostname per architecture instead of the current primary's server name alone.
- Plan listener DNS and Private Endpoint connectivity for **all participating SQL logical servers**.
- Never assume creating a Private Endpoint for the primary automatically provisions Private Endpoints/Private DNS/routes for the secondary in another region.
- Verify VNet links/resolvers in both primary and secondary regions and how clients resolve the listener.
- Confirm Entra auth/database permissions, TLS cert trust, and app network policies work along the failover path.
- Conduct controlled failover drills and measure **actual RPO/RTO**, rather than relying on diagrams.

**Never manually change connection strings to a secondary's private IP** during failover. Use proper listener DNS mechanisms and manage Private Endpoints/private DNS across both regions per service guidance.

### 17.3. PostgreSQL/MySQL HA and DR

Flexible Server supports **high availability, backup/PITR, replication, or geo-redundancy** depending on engine, SKU, and region. These capabilities **do not mean** standby/replica networking and DNS are automatically cloned into every VNet.

Before deploying DR:

1. Identify whether the deployment uses VNet-injected private access or Private Link.
2. Verify secondary subnets/zones/regions and matching private DNS.
3. Confirm FQDNs/failover semantics required by drivers.
4. Evaluate replication lag, data consistency, read replicas, and backup restores.
5. Create a reversible traffic/app-config cutover runbook.
6. Verify database roles/passwords/Entra authentication after restore/failover.

Never build systems assuming a read replica promotes automatically under the same hostname in every mode. Verify per engine and replication mechanism.

### 17.4. Connection Pools and Post-Failover Retries

A pool can hold stale TCP connections when a database switches primary. Applications must:

- Detect transient connection errors.
- Allow the pool to evict invalid connections.
- Retry with **backoff/jitter and deadlines**, avoiding infinite loops.
- For write transactions, enforce **idempotency** and handle uncertain commit states.
- Check token refresh, DNS caching, and listener connection strings.
- Watch service error rates post-failover alongside message/batch job processing.

**Never retry an un-idempotent payment/order** merely because failover caused a timeout; the transaction may have committed before the response dropped.

### 17.5. DR Drill Matrix

| Scenario | What to Verify | Evidence |
|---|---|---|
| Database zone outage | HA recovers per tier | Recovery duration, app error rate |
| Primary region outage | DB failover + secondary Private Link/DNS | Listener resolved, queries succeed from every network |
| Private DNS zone/link deleted | Resolver fallback and IaC restoration | Private probe catches failure, IaC restores |
| Private Endpoint rejected/deleted | Recreate/approve, NIC/IP/DNS update | PE status and TCP/TLS/login |
| Entra credential/role revoked | Identity recovery/least privilege | Login audit and service owner approval |
| CA/certificate rollover | Trust store/driver update | TLS handshake passes in staging/prod |
| VPN/ExpressRoute outage | Alternate on-premises connectivity | User-facing impact, route restoration |

DR reports must record **actual measured durations**, decision owners, potential data loss, and recovery steps. An untested "multi-region" architecture is a hypothesis, not proof of RTO.

## 18. Performance and Cost of Private Database Connectivity

Private Endpoint is usually chosen to **reduce public exposure, govern network paths clearly, and integrate into private networks**, not because every query runs faster than over a public endpoint.

### 18.1. Cost Components

| Component | Cost Driver |
|---|---|
| **Private Endpoints** | Hourly resource fee and data processing charges per regional pricing |
| **Private DNS zones / Resolver** | DNS zones, queries/links, resolver endpoints/transactions per service |
| **VNet connectivity** | VPN Gateway, ExpressRoute, peering, NAT/Firewall, NVA, and egress |
| **Database compute/storage** | SQL DB vCore/DTU, MI compute, PostgreSQL/MySQL vCores, backup/storage |
| **App compute** | App Service plans, Functions, Container Apps/AKS/VM instances |
| **Monitoring** | Log Analytics ingestion, Azure Monitor/App Insights, retention |
| **DR** | Secondary databases/regions, replication, private networking in standby region |

Rates depend on **SKU/region/time**; this lesson avoids fixed USD/GB or USD/hour claims. Use Azure Pricing/Cost Management with real throughput, backup, and DR estimates before deciding.

### 18.2. Private Link Does Not Fix Slow Queries

A query taking 12 seconds due to a table scan or lock contention will not speed up noticeably just by moving onto Private Endpoint. Track:

- SQL query plans, indexes, blocking, deadlocks.
- Database CPU/I/O/storage limits.
- Connection pool waits and client session counts.
- Network latency between app region and DB region.
- TLS handshake/reconnect overhead.
- Retry counts in both app and database drivers.

Co-locating apps and databases in the same region/availability profile, tuning pools, and optimizing SQL statements typically impact performance far more than swapping public IPs for private ones.

### 18.3. Sizing Network Appliances and Connection Pools

If routing all data-plane traffic through Azure Firewall/NVAs for inspection:

1. Size throughput and concurrent connections.
2. Verify route symmetry, SNAT/connection tracking, and TLS policies.
3. Ensure Private Link/endpoint paths are not blocked unexpectedly.
4. Monitor traffic processing and logging costs.
5. Account for firewall/forwarder HA; avoid introducing a single central point of failure.

**Never add extra firewalls/NATs solely for "more security"** if existing network controls already satisfy the threat model; every extra hop adds cost, latency, and operational risk.

### 18.4. Cutting Costs Without Weakening Security

- Use a clearly owned hub-spoke DNS/Resolver topology to avoid unnecessary duplicate resources, while **never** mis-merging DNS and breaking connectivity.
- Delete leftover Private Endpoints, lab VNets, VMs, gateways, and DNS resolvers after exercises.
- Size database SKUs/capacity around p95 load, backups/DR, and workload growth.
- Control log retention/sampling without capturing plaintext sensitive queries.
- Apply `owner`, `application`, `environment`, and `costCenter` tags appropriately.
- Use budgets/alerts and review network + database + app costs together per business unit.

**A budget alert is not a hard spending cap.** Shutting down database compute or deleting a Private Endpoint purely to save cost can break apps or risk data; cleanup requires owner/change approval.

## 19. Infrastructure as Code and Policy Guardrails

Private networking and database security quickly suffer **configuration drift** if engineers create a Private Endpoint in the Portal and forget to record DNS zone links, public network access, or RBAC. Production requires peer-reviewed **IaC** and pipelines.

### 19.1. Separating Ownership Boundaries

~~~text
Platform IaC (Bicep/Terraform/ARM):
  VNet/subnets/Private Endpoint
  Private DNS zone/link/zone group
  Azure Firewall/NSG/UDR/Private DNS Resolver
  Database resource/network settings
  Microsoft Entra identities, role assignments
  Diagnostic settings, alerts, tags

Database migration pipeline / DBA:
  Schema changes
  SQL users/GRANT and role model
  Backup/restore and DR

Application CI/CD:
  Workload runtime, managed identity binding
  Connection FQDN/environment settings
  Driver versions, TLS validation, pool config
  Smoke tests and SLO monitoring
~~~

Never let two independent pipelines manage `publicNetworkAccess` or the same Private DNS A record from conflicting "sources of truth." Review Terraform/Bicep plans carefully before applying, especially any action that **destroys/recreates a Private Endpoint or DNS zone link**.

### 19.2. Illustrative Bicep Snippet for a Private DNS Zone

This snippet demonstrates only a zone and link and is **not a complete production deployment**:

~~~bicep
@description('Resource ID of the approved VNet.')
param vnetResourceId string

resource sqlPrivateZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.database.windows.net'
  location: 'global'
}

resource vnetLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: sqlPrivateZone
  name: 'link-approved-vnet'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnetResourceId
    }
  }
}
~~~

**Never apply this into an environment where zones are owned by a platform team** without permission/change approval. Real setups must coordinate Private Endpoints, DNS zone groups, roles, NSG/firewall policies, diagnostics, and multi-VNet links properly. Verify Bicep resource API versions/features against your Azure deployment target.

### 19.3. Azure Policy and Controlling Public Exposure

Organizations can use **Azure Policy** per supported definitions to audit/deny/remediate database configs:

- Public network access enabled against policy.
- Databases missing diagnostic settings/auditing.
- Minimum TLS version set too low.
- Private Endpoints/approved networks failing policy.
- Associated Storage/Key Vault resources with broad network exposure.
- Missing ownership/`costCenter` tags.

Azure Policy conditions/effects depend on each service's resource schema; **never claim a single generic policy automatically blocks all public databases** without testing across SQL, PostgreSQL, MySQL, and MI. Nor does Policy replace database role reviews or application authorization.

### 19.4. IaC Pipeline with Verification Gates

~~~mermaid
flowchart LR
    PR[PR: Network and DB configuration] --> PLAN[Validate Bicep/Terraform + security review]
    PLAN --> APPLY[Apply approved changes]
    APPLY --> PE[Check Private Endpoint Approved]
    PE --> DNS[Test DNS from intended VNet]
    DNS --> TCP[Test TCP and TLS + database login]
    TCP --> CUT[Disable public path after sign-off]
    CUT --> TEST[Positive/negative connectivity + SLO]
    TEST --> AUDIT[Record configuration and changes]
~~~

Never let a pipeline automatically **disable public access immediately upon creating a Private Endpoint** without verifying all clients and rollback paths. Run checks from **production-equivalent networks**, not just public Azure CLI runners.

## 20. Case Study: Securing Azure SQL for an E-Commerce Application

**Hypothetical scenario:** An ordering system runs on Azure App Service and Azure Container Apps. The API calls Azure SQL Database, while a worker processes Azure Service Bus messages and saves invoices to Blob Storage. Most resources sit in one production subscription; security wants to **block SQL access from the Internet**, restrict who can query the database, and preserve DR. Currently the app uses the public SQL endpoint allowlisted for App Service egress IPs.

Requirements:

- Every production runtime connects to SQL over a **private path**; no broad "Allow Azure services" exception.
- App Service/Container Apps each hold separate managed identities; the database grants only required SQL permissions.
- TLS always verifies certificates/hostnames.
- A CI/private runner performs schema migrations without temporarily opening public access on each release.
- End-to-end testing, auditing, alerts, backups, and failover plans exist.
- On-call staff have runbooks to troubleshoot DNS/routing/TLS/logins without weakening security blindly.

### 20.1. Target Architecture

~~~mermaid
flowchart TB
    CUSTOMER[Web / mobile] --> WEB[App Service: orders-api]
    BUS[(Azure Service Bus)] --> WORK[Container Apps: invoice-worker]
    WEB -->|VNet Integration outbound| VNET[VNet app subnet / routing]
    WORK -->|VNet environment outbound| VNET
    VNET --> DNS[Private DNS Resolver + privatelink.database.windows.net]
    DNS --> PE[Private Endpoint NIC 10.20.2.4]
    PE --> SQL[(Azure SQL Database: ordersdb)]
    WEB -. Managed identity + verified TLS .-> SQL
    WORK -. Managed identity + verified TLS .-> SQL
    WORK --> BLOB[(Azure Blob Storage)]
    DBA[DBA / migration runner via private network] --> VNET
    MON[Azure Monitor + App Insights] -. Diagnostics .-> SQL
    MON -. Connection failures / traces .-> WEB
    MON -. Connection failures / traces .-> WORK
~~~

**Securing Blob/Service Bus is a separate networking/identity problem.** Having a SQL Private Endpoint does not automatically make every other service in the diagram private-only.

### 20.2. Design Decisions

| Topic | Illustrative Decision | Rationale |
|---|---|---|
| **Database service** | Azure SQL Database | Uses Private Link logical server + TLS/Entra |
| **App runtime** | App Service VNet Integration | Enables app outbound path to SQL PE |
| **Worker runtime** | Container Apps VNet environment | Enables worker access to private SQL |
| **DNS** | Central `privatelink.database.windows.net` zone with proper links/forwarders | Preserves canonical FQDN; avoids duplicate team zones |
| **Network** | Separate app and PE subnets; approved routes/NSGs | Clear ownership, segmentation, and flow control |
| **Authentication** | Separate managed identities for API and worker | Limits blast radius if one app is compromised |
| **SQL privileges** | API gets `SELECT/INSERT/UPDATE` on target schema; worker gets minimal needed rights | Avoids database admin at runtime |
| **Encryption** | TLS verifies hostname; driver manages CA trust | Protects traffic even on private networks |
| **Cutover** | Create PE/DNS, test each consumer, disable public last | Prevents breaking legacy clients |
| **Monitoring** | Synthetic probes + app metrics + SQL logs | Separates networking issues from login/performance |
| **DR** | SQL failover/backups per tier with tested private routing | Avoids mistaking one Private Endpoint for HA |

### 20.3. Practical Migration Plan

**Design phase (no runtime changes):**

1. Inventory all SQL clients: APIs, workers, reporting, CI migrations, DBAs, scheduled jobs.
2. Record FQDNs, DB names, current firewall rules, egress IPs, and SQL principals.
3. Review VNet address space, integration support, and central DNS ownership.
4. Define change/rollback approvals and network/DB SLOs.

**Preparation phase (public path remains controlled):**

5. Provision Private Endpoint and approve connection.
6. Create/link the proper DNS zone and verify the server A record.
7. Enable VNet integration on the app/worker per runtime.
8. Verify DNS, TCP, TLS, login, and a read-only query from each runtime.
9. Test the migration runner and DBA VPN access over the private path.
10. Enable monitoring before cutover; capture baseline latency/error rates.

**Cutover day (within change window):**

11. Confirm zero remaining clients depend on the public path with owner sign-offs.
12. Disable public network access on the logical server.
13. Run positive tests from private runtimes and negative tests externally.
14. Watch API error rates, worker queues, SQL logins, DNS/routes, and job schedules.
15. Retire obsolete public firewall exceptions per policy.

**Post-cutover:**

16. Rehearse failover/restore and verify secondary private paths.
17. Review connection pool sizes, token refresh, and CA/certificate update processes.
18. Archive IaC state/change tickets, DNS/routing diagrams, and on-call runbooks.

### 20.4. Incident 1: App Runs Yet Database Times Out

After disabling public access, `orders-api` returns HTTP 503. A debug VM in the VNet connects to SQL successfully, while App Service fails:

~~~text
VM debug:
  SQL FQDN → 10.20.2.4; TCP 1433 OK; SQL query OK

App Service:
  SQL FQDN → public IP; connect timeout

Likely cause:
  App Service outbound VNet Integration or DNS context
  is misconfigured.
~~~

**Remediation:** do not re-enable "Allow Azure services" before investigating. Inspect VNet Integration/routing/DNS from the App Service runtime; once DNS returns the private IP and TCP connects, verify TLS/Entra login. If a severe outage demands break-glass access, open only a narrow, time-boxed, approved exception and close it immediately afterward.

### 20.5. Incident 2: Private Network Works, SQL Reports Permission Denied

Worker `invoice-service` uses managed identity `mi-invoice-prod`; DNS resolution, private TCP, and TLS all succeed, yet `INSERT` into `sales.Invoices` is denied.

**Remediation:** inspect SQL users/`GRANT`s inside `ordersdb`—do not alter NSGs/Private Endpoints since networking already works. Have a DBA grant `INSERT` (and only required job permissions) on the target object/schema after review; avoid `db_owner`.

### 20.6. Incident 3: SQL Failover Breaks Client Reconnects

The database fails over to another region. The backend is healthy, yet the app's JDBC pool clings to stale connections and secondary listener DNS/Private Endpoints were never configured. The app reports timeouts or transient errors.

**Remediation:** use the service's failover listener FQDN, deploy Private Endpoints/private DNS for all participating logical servers, verify regional routes, DNS caching, pool health, and idempotent retries. Never hard-code an old region's IP in code or connection strings.

### 20.7. Lesson from the Case Study

A private path **is not** just a Private Endpoint. It is a testable chain:

~~~text
Runtime → outbound VNet integration/route → private DNS
        → approved Private Endpoint → TLS verification
        → Entra/database login → SQL GRANT → business transaction
~~~

If one link breaks, fix that exact layer. "Disable public access" should only be the **final step of a validated migration**, never the first.

## 21. Hands-On Exercise and Self-Assessment Questions

**Assignment:** You are tasked with migrating Azure SQL Database `inventorydb` from public firewall-based connectivity to private-only. Three consumers are an App Service, an AKS worker, and a reporting tool on the on-premises network. The database holds products and stock levels; faulty writes could cause negative inventory orders.

### 21.1. Design Tasks

1. Diagram App Service/AKS/on-premises, VNet, Private Endpoint, Private DNS Resolver, SQL database, Entra identities, and Azure Monitor.
2. Explain how Private Link/Private Endpoint differs from **service endpoints** and public firewall rules.
3. Specify which subnet hosts the Private Endpoint, where its private IP comes from, and why it does not provide outbound VNet Integration for App Service.
4. Select the right Private DNS zone for Azure SQL Database; describe how resolvers in the VNet and on-premises return the private IP.
5. Explain how to prove real clients still use the canonical FQDN rather than hard-coding a private IP.
6. Design firewall controls: public network access, Azure SQL "Allow Azure services," NSGs/UDRs, and DB roles.
7. Distinguish **Azure RBAC Contributor** from a **SQL user and `GRANT SELECT`**.
8. Design separate managed identities for a read-only API and a worker authorized to update inventory.
9. Choose TLS settings for Java/JDBC and explain `TrustServerCertificate=false`.
10. List Azure CLI steps to create a Private Endpoint, DNS zone/link/zone group, and verify approval.
11. Build a DNS/TCP/TLS/login/query test matrix across all consumers before disabling public access.
12. Propose a phased cutover plan, controlled rollback, and owner approvals.
13. If App Service resolves a public IP after cutover while AKS resolves the private IP, what do you check?
14. If JDBC throws a certificate hostname mismatch when using `10.20.2.4`, how do you fix it?
15. If TCP/TLS/login succeed yet SQL `SELECT` is denied, what must change?
16. Calculate how many potential sessions connection pools capped at 15 connections/instance across 12 app replicas create.
17. Propose at least six metrics/alerts for private DB connectivity.
18. Describe how to organize IaC, Azure Policy, and diagnostic settings to prevent accidental re-enabling of public access.
19. If SQL fails over to a secondary region, which network/DNS/driver components must be verified?
20. Compare Azure SQL's private connectivity path against PostgreSQL Flexible Server using VNet-injected private access.

### 21.2. Reference Lab Sequence

~~~text
PRECHECK
  - Confirm subscription, resource IDs, owner, DB engine/network mode
  - Collect all dependent clients, SQL credentials/identity and routes
  - Confirm private network ranges, DNS ownership, change plan

PREPARE
  - Create PE for Azure SQL logical server
  - Approve PE connection
  - Create/link private DNS zone and DNS zone group
  - Enable VNet egress for apps; connect on-prem VPN/DNS forwarder

TEST
  - nslookup SQL FQDN from each source → correct private IP
  - TCP port 1433 → success
  - TLS hostname/certificate verification → success
  - Entra login + least-privilege query → success

CUTOVER
  - Authorized change window
  - Disable public network access on SQL server
  - Positive test from private network
  - Negative test outside private network
  - Review application, database and security alerts

OPERATE
  - Save IaC and audit evidence
  - Rehearse DR and certificate/token rotation
  - Retire unused public firewall exceptions
~~~

### 21.3. Sample Answers to Selected Questions

**Q12 — why inventory every consumer?** If an on-premises report still uses the public SQL endpoint, disabling public access breaks reporting even while App Service/API keep working. You need DNS forwarding/private routing or an approved alternative integration.

**Q14 — how to resolve TLS hostname mismatch?** Connect using `<server>.database.windows.net`, let DNS return the Private Endpoint IP, keep certificate validation on, and update CA bundles/drivers if needed. **Never** disable hostname verification.

**Q15 — query permission denied?** Networking/TLS/login layers already work; have a DBA review database users and `GRANT`s rather than opening NSGs/firewalls.

**Q16 — total potential pool:**

\[
15\ \text{connections/replica} \times 12\ \text{replicas} = 180\ \text{connections}.
\]

This is the theoretical configured pool ceiling before adding migration runners, admin sessions, and background jobs. Leave headroom, measure DB sessions, and avoid scaling apps into DB overload.

**Q20 — engine differences:** Azure SQL Database logical server uses Private Endpoint `sqlServer` + zone `privatelink.database.windows.net`. PostgreSQL Flexible Server in VNet-injected private access uses a **delegated subnet and service-specific private DNS**, not the same group ID/zone, and does not necessarily use Private Endpoints.

### 21.4. Required Lab Evidence

| Evidence | Meaning |
|---|---|
| Resource IDs of SQL logical server and PE | Confirms exact target resources |
| PE connection Approved | Confirms network link authorization |
| PE IP and Private DNS records/links | Confirms resolver has accurate private records |
| `nslookup` from each runtime | Confirms clients resolve the private IP |
| TCP tests from each runtime | Confirms network reachability |
| TLS + Entra SQL read-query test | Confirms secure identity and connection work |
| Public negative test | Confirms no policy-violating public paths remain |
| Azure Activity Log/change ticket | Confirms accountable public-access change |
| App/business SLO | Confirms the app still serves users |
| Backup/DR evidence | Confirms recoverability beyond current network path |

Never include access tokens, passwords, or real customer data in lab reports. Use synthetic data and safe read-only SQL queries for testing.

## 22. Checklists Before, During, and After Private Database Cutover

### 22.1. Pre-Deployment

- [ ] Exact engine identified: Azure SQL Database, Managed Instance, PostgreSQL Flexible Server, or MySQL Flexible Server.
- [ ] Confirmed SKU/networking mode/region support the selected private connectivity option.
- [ ] Inventoried **all** apps, workers, DBA tools, reporting, CI runners, and on-premises clients using the database.
- [ ] Verified subscription/resource group/resource IDs and database/network ownership.
- [ ] Non-overlapping VNet CIDRs; dedicated subnets for App Service/Functions/AKS and Private Endpoints or delegated subnets.
- [ ] Private DNS zone matched to service/mode; no unnecessary duplicate zones.
- [ ] VNet links, peering, hub-spoke DNS/Private Resolver, and conditional forwarding planned.
- [ ] NSGs/UDRs/firewalls reviewed; not assuming PE traffic behaves identically to VM NICs by default.
- [ ] Entra/managed identities and database principals/`GRANT`s separated by workload.
- [ ] TLS driver config enforces hostname/certificate verification, trust store, and rotation plan.
- [ ] Monitoring/diagnostics and synthetic probes active before altering public network access.
- [ ] Change approval, rollback plan, and DR/backup evidence ready.

### 22.2. After Creating the Private Endpoint

- [ ] Private Endpoint connection is **Approved**, not Pending/Rejected.
- [ ] Private Endpoint NIC/private IP resides in the intended subnet targeting the right resource.
- [ ] DNS zone A record/zone group/links match every VNet's topology.
- [ ] Each consumer's actual runtime resolves the FQDN to a routable private IP.
- [ ] Engine/policy-appropriate TCP port succeeds from every consumer.
- [ ] TLS certificate chain and hostname validate; neither `TrustServerCertificate=true` nor `sslmode=disable` is used.
- [ ] Entra/database user login succeeds with strictly scoped permissions.
- [ ] End-to-end app smoke/business tests pass; p95 latency and connection errors do not degrade unexpectedly.
- [ ] CI/migration runners and on-premises DBA access tested over the private network.

### 22.3. When Disabling Public Access

- [ ] Sign-off evidence from every owner confirming zero reliance on the public endpoint.
- [ ] Change window, responsible owner, and rollback criteria documented.
- [ ] Change public access **only on the target resource**, avoiding simultaneous schema/cert/driver changes where possible.
- [ ] Positive private query tests pass from App Service/AKS/workers/DBAs.
- [ ] Negative tests outside the private network confirm public data-plane access is blocked.
- [ ] Scheduled jobs/queues/reporting continue operating normally.
- [ ] No overly broad firewall exceptions left behind out of policy.
- [ ] Monitoring alerts/dashboards active and assigned to owners.
- [ ] IaC/source of truth updated with private-only state to prevent drift.

### 22.4. During an Incident

- [ ] Confirm exact server FQDN/engine/networking mode/resource IDs.
- [ ] Test DNS from the **failing runtime**, not just a personal laptop.
- [ ] Check routing/TCP before touching SQL credentials.
- [ ] Check TLS chain/hostname before weakening security settings.
- [ ] Check Entra tokens/users/SQL grants once networking succeeds.
- [ ] Check database CPU/I/O/pool capacity to distinguish performance bottlenecks from network errors.
- [ ] Never enable broad "Allow Azure services" or grant `db_owner` carelessly as a quick fix.
- [ ] If break-glass access is genuinely required, keep scope minimal, owned, time-boxed, and fully audited.
- [ ] After recovery, validate business transactions and close temporary exceptions.

## 23. Lab Cleanup Without Breaking Shared Networks or Databases

Private Endpoints, Private DNS, VNets, VPNs/Firewalls/Resolvers, and databases can keep accruing costs after a lab ends. However, **accidentally deleting a shared Private DNS zone or Private Endpoint** can sever connectivity across many applications.

### 23.1. Inventory Resources Before Cleanup

~~~bash
az account show --query "{id:id,name:name}" -o table

az resource list \
  --resource-group "$RG" \
  --output table

az network private-endpoint list \
  --resource-group "$RG" \
  --output table

az network private-dns zone list \
  --resource-group "$RG" \
  --output table

az sql server show \
  --resource-group "$RG" \
  --name "$SQL_SERVER" \
  --output json
~~~

The listing commands above are **read-only**. If the private DNS zone lives in another hub RG, it won't appear in the lab RG list; verify ownership and dependencies before deleting network resources. Never run deletion commands against an unverified `RG` variable.

### 23.2. Cleanup Decision Order

1. Confirm all targeted resources belong to a **disposable lab** with zero real consumers.
2. Check **database backups and test data**; never delete a SQL logical server hosting production databases.
3. Check which Private Endpoints belong exclusively to the lab vs. **shared central DNS** zones.
4. Check which VNet links are used by other VNets; never delete central zones/Private DNS Resolvers owned by the platform team.
5. Stop test CI jobs/VMs and verify no scheduled tasks still touch SQL.
6. Remove individual resources per owner workflow while verifying other environments remain unaffected.
7. Review residual spend: database compute, PE hourly fees, DNS/Resolver, VPN/Firewall, monitoring/logs, and backups.

Deletion commands—**illustrative only and commented out**:

~~~bash
# DO NOT execute blindly. Confirm this PE is exclusively for the lab.
# az network private-endpoint delete \
#   --resource-group "$RG" \
#   --name "$PE_NAME"

# Never delete a Private DNS zone still used by other VNets/PEs.
# Never delete an entire resource group if SQL/servers or networking are shared.
# az group delete --name "$RG" --yes
~~~

**Never assume deleting a Private Endpoint safely reverts the database to public access.** If public access is disabled, deleting the PE cuts off the workloads' only path. Plan disconnections and resource ownership carefully.

## 24. Key Takeaways

**Private endpoints, firewalls, and securing database connectivity** form a **multi-layered** problem. A Private Endpoint brings the service onto a private IP; DNS lets apps keep the canonical hostname; VNet routes/NSGs/firewalls govern network paths; TLS authenticates the server and encrypts transit; Entra/database logins verify the principal; and database `GRANT`/roles limit data operations.

Principles to remember:

1. **Do not confuse private network types:** Private Endpoint differs from service endpoints and **VNet-injected private access**; Azure SQL, Managed Instance, PostgreSQL, and MySQL have distinct network models.
2. **Preserve the canonical database FQDN:** Private DNS must return the private IP from each connecting runtime; never hard-code Private Endpoint IPs in connection strings.
3. **Private Endpoint does not disable public access:** provision/approve/configure DNS/test first, and disable public network access last per policy.
4. **Firewalls have multiple layers:** public database firewalls, NSGs/UDRs/routing, and SQL logins/permissions do not substitute for one another.
5. **TLS remains mandatory:** verify CA chains and hostnames; never disable certificate validation to mask DNS bugs.
6. **Least-privilege identity:** prefer Microsoft Entra/managed identity where supported; Azure RBAC Contributor does not grant SQL `SELECT`, and app runtime must not run as database admin.
7. **Test layer by layer:** DNS → TCP → TLS → authentication → SQL authorization → business transaction.
8. **Runtimes need explicit outbound paths:** App Service outbound VNet Integration differs from App Service inbound Private Endpoints; AKS/Functions/on-premises each have distinct topologies.
9. **Plan migrations and DR:** inventory every consumer, build cutover/rollback plans, and test failover listeners and secondary private networking.
10. **Operations/FinOps:** monitor connection failures, DNS, SQL metrics, logs, network costs, and IaC sources of truth; never leave broad public exceptions open indefinitely.

A private database design is only complete when there is verified proof that **every authorized workload resolves the canonical FQDN, traverses private routes, validates TLS, authenticates with the right identity, operates within least-privilege grants, and recovers across network/database changes—while out-of-scope sources are blocked per policy**.