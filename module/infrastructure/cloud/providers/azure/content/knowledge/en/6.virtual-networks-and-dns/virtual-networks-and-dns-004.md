# Network Security Groups and Application Security Groups

In the **CLOUD_PROVIDERS_AZURE** module, we explore Microsoft Azure from subscriptions, resource groups, and Microsoft Entra ID through virtual networks, compute services, storage, and data; then learn how to deploy, monitor, secure, and control costs for an application architecture on Azure. In the **Virtual Networks and Name Resolution** chapter, understanding **Network Security Groups (NSGs)** and **Application Security Groups (ASGs)** is fundamental for controlling traffic flows inside an Azure Virtual Network (VNet).

Imagine an order-processing application with three tiers: web servers, APIs, and a database. Users should only reach the web tier over HTTPS; the web tier should only call the API on port 8080; and only the API should be permitted to connect to the database on port 1433. If all virtual machines reside in one VNet without traffic controls, tiers can communicate far more broadly than intended. NSGs define allow/deny rules; ASGs express those rules by application role instead of maintaining lists of individual IP addresses.

After this lesson, you will be able to:

- Explain the purpose, attachment points, evaluation order, and stateful behavior of NSGs.
- Distinguish between NSGs, ASGs, and other Azure network security components.
- Read and design rules based on source, destination, port, protocol, direction, action, and priority.
- Use ASGs to represent multi-VM application tiers within the same VNet.
- Create NSGs, ASGs, and rules via Azure CLI; inspect effective security rules and troubleshoot connectivity failures.
- Recognize risks from default rules, overlapping configurations, overly permissive access, and service-disrupting changes.

## 1. What Is an NSG and What Scope Does It Protect?

A **Network Security Group** is an Azure resource containing a set of **security rules** that filter incoming (**inbound**) and outgoing (**outbound**) IP traffic for supported network components. For Azure virtual machines, an NSG can be associated with:

1. A VNet **subnet**, to control traffic involving network interfaces within that subnet.
2. A VM's **Network Interface (NIC)**, to apply additional rules to a specific interface.

A single subnet or NIC can be directly associated with only **one NSG** at a time, though the same NSG can be associated with multiple eligible subnets/NICs. You do not need to attach NSGs at both levels in every architecture; establish a clear convention to avoid confusion when troubleshooting denied connections.

An NSG is a network- and transport-layer traffic filtering mechanism based on attributes such as IP addresses, ports, and protocols. It does **not** replace user authentication, TLS, guest OS firewalls, a Web Application Firewall, or application vulnerability management.

### 1.1. What Fields Make Up a Rule?

| Field | Function | Example |
|---|---|---|
| `name` | Meaningful name for the rule | `Allow-Web-To-Api-8080` |
| `priority` | Rule evaluation order; **lower numbers are evaluated first** | `200` |
| `direction` | Traffic direction | `Inbound` or `Outbound` |
| `access` | Action taken on match | `Allow` or `Deny` |
| `protocol` | Protocol evaluated | `Tcp`, `Udp`, `Icmp`, `*` |
| Source | IP/CIDR, service tag, or ASG | `10.20.1.0/24`, `VirtualNetwork`, `asg-web` |
| Source port | Initiating or packet source port | `*` (typically ephemeral ports) |
| Destination | IP/CIDR, service tag, or ASG | `10.20.2.0/24`, `asg-api` |
| Destination port | Target application port receiving the connection | `443`, `8080`, `1433` |

For example, an inbound rule with `priority=200`, source `asg-web`, destination `asg-api`, protocol `Tcp`, destination port `8080`, and access `Allow` permits connections matching all of those criteria **provided no other NSG blocks them along the path**.

Custom rule priorities in an NSG range from **100–4096**. Within the same NSG, each direction requires unique priorities across configured rules; the same priority number can be used independently in inbound and outbound directions. A rule with a lower priority number is evaluated before a rule with a higher number.

### 1.2. How an NSG Decides Allow or Deny

Azure evaluates rules in ascending priority order for the corresponding traffic direction. The **first matching rule** determines Allow/Deny; lower-priority rules (i.e., higher numbers) are not evaluated for that flow.

Example within the same NSG:

| Priority | Direction | Source | Destination port | Access |
|---:|---|---|---:|---|
| 100 | Inbound | `10.20.1.5` | `8080` | Deny |
| 200 | Inbound | `10.20.1.0/24` | `8080` | Allow |
| 300 | Inbound | `VirtualNetwork` | `*` | Deny |

Traffic from `10.20.1.5` to port 8080 is denied by rule 100, even though it also falls within the source range of Allow rule 200. Traffic from `10.20.1.6` to port 8080 matches rule 200 and is allowed. Other internal connections match Deny rule 300 and are rejected.

NSGs evaluate based on declared fields. **A rule's name does not dictate its behavior**: a rule named `Deny-SSH` with `access=Allow` is still an allow rule.

## 2. Default Rules in an NSG

When an NSG is created, Azure includes **default security rules**. They enable baseline traffic to function, but may not satisfy isolation requirements between application tiers.

### 2.1. Default Inbound Rules

| Priority | Rule Name | Meaning |
|---:|---|---|
| 65000 | `AllowVnetInBound` | Allows traffic from `VirtualNetwork` to `VirtualNetwork` |
| 65001 | `AllowAzureLoadBalancerInBound` | Allows traffic from the `AzureLoadBalancer` service tag |
| 65500 | `DenyAllInBound` | Denies all remaining inbound traffic |

### 2.2. Default Outbound Rules

| Priority | Rule Name | Meaning |
|---:|---|---|
| 65000 | `AllowVnetOutBound` | Allows traffic from `VirtualNetwork` to `VirtualNetwork` |
| 65001 | `AllowInternetOutBound` | Allows outbound traffic to `Internet` as defined by the service tag |
| 65500 | `DenyAllOutBound` | Denies all remaining outbound traffic |

Default rules cannot be deleted directly; to override their behavior, create **custom rules** with higher priority (a smaller numeric value). The default `AllowVnetInBound` rule is a frequent reason two VMs in the same VNet can still communicate even after you add a few custom Allow rules.

**Key takeaway:** adding an `Allow-Web-To-Api` rule **does not automatically block** other internal sources from reaching the API. To isolate the API, you need an explicit Deny rule placed at higher priority than `AllowVnetInBound`. Verify management paths, DNS, health probes, and valid dependencies before deploying a Deny rule.

The `VirtualNetwork` service tag can encompass multiple address ranges associated with network connectivity configurations, such as VNet ranges and connected networks where supported. Do not assume this tag covers only a single subnet.

## 3. NSGs Are Stateful and Applied at Multiple Levels

NSGs are **stateful**: when a connection is permitted by a matching rule, return traffic for that connection is tracked and does not require a separate reverse rule for response packets.

For instance, if the web VM initiates a connection to the API VM from ephemeral source port 52000 to destination TCP port 8080, the API's response back to port 52000 belongs to the same tracked connection. That does **not** mean the API VM can initiate a brand-new connection to the web VM without an Allow rule.

Modifying or deleting a rule generally affects **new connections**. Existing active connections may continue until their flow state terminates; do not rely solely on NSG edits to immediately sever established sessions.

### 3.1. When Both Subnet and NIC Have NSGs

Traffic must traverse every filtering layer applied to it. For inbound traffic to a VM, Azure evaluates the subnet NSG first, then the NIC NSG. For outbound traffic from a VM, the evaluation order is the NIC NSG first, then the subnet NSG.

```text
Inbound:
Source --> Subnet NSG --> NIC NSG --> VM

Outbound:
VM --> NIC NSG --> Subnet NSG --> Destination
```

A new connection must be allowed by **all involved NSGs**. An Allow rule on the NIC cannot override a Deny rule on the subnet, and vice versa. Priority ordering only applies **within each individual NSG**, not as a global priority list across merged NSGs.

Example:

- The subnet NSG allows TCP 8080 from the web tier.
- The API NIC NSG denies TCP 8080 from that same source.
- Result: connections to the API are **blocked**, even though the subnet NSG has an Allow rule.

In operations, many teams attach NSGs only at the subnet level for centralized management and fewer overlapping layers; others add NIC NSGs when controlled exceptions are needed. Both patterns work well if ownership and update procedures are clearly defined.

## 4. What Is an ASG?

An **Application Security Group** is a way to **logically group VM network interfaces/IP configurations by application role** for use inside NSG rules. Instead of listing individual IP addresses of web servers, you can specify the source as `asg-web`.

Example:

```text
VNet vnet-orders-prod (10.20.0.0/16)
|
+-- subnet-web (10.20.1.0/24)
|    +-- vm-web-01 [asg-web]
|    +-- vm-web-02 [asg-web]
|
+-- subnet-api (10.20.2.0/24)
|    +-- vm-api-01 [asg-api]
|    +-- vm-api-02 [asg-api]
|
+-- subnet-db (10.20.3.0/24)
     +-- vm-db-01  [asg-db]
```

Names and IPs are illustrative. An ASG defines **membership** on VM network configurations; an ASG **does not filter traffic on its own**. For enforcement, you must still create NSG rules referencing the ASG and associate that NSG with the relevant subnet or NIC.

When `vm-api-03` is added to `asg-api`, existing NSG rules referencing that ASG automatically apply to the new VM without editing rules to add its IP. This is especially beneficial when VMs scale out/in or get replaced.

### 4.1. Limits and Scope to Understand

- ASGs apply to VM NIC IP configurations within supported feature scope. You **cannot** use ASGs to automatically group arbitrary PaaS resources such as Azure SQL Database, Storage Accounts, or App Service.
- NICs placed in the same ASG must comply with Azure's **same virtual network** constraints. When spanning multiple VNets/peerings, verify ASG constraints before designing cross-network rules.
- Configuring an ASG does not replace subnets, route tables, NSGs, or Azure Firewall.
- A VM can belong to multiple ASGs via supported IP configurations; check current subscription/region quotas and limits.
- Including an ASG in a rule only provides a source or destination match criterion; the rule still requires direction, access, protocol, port, and priority.

If the data tier is **Azure SQL Database (PaaS)**, do not treat it as a VM placed inside `asg-db`. Instead, use appropriate access mechanisms such as private endpoints, Azure SQL networking settings, supported-scope NSGs, and identity controls. In the three-tier ASG example above, `vm-db-01` is a **self-managed database on a VM**.

## 5. Comparing NSGs and ASGs

| Criterion | Network Security Group (NSG) | Application Security Group (ASG) |
|---|---|---|
| Nature | Set of Allow/Deny network filtering rules | Logical role-based grouping of network interfaces |
| Directly blocks packets? | Yes, when attached to an eligible scope | No |
| Where applied? | Subnet or NIC | NIC IP configuration membership; referenced in NSG rules |
| Specifies ports and protocols? | Yes | No |
| Purpose | Control traffic flows | Avoid maintaining IP lists in rules |
| Example | Allow only TCP 8080 from web to API | Group of VMs serving the `asg-api` role |

NSGs answer **“which flows are allowed?”**; ASGs answer **“which VMs act as the source/destination in that rule?”**. They are typically used **together**, not as alternatives to each other.

## 6. Designing Network Segmentation for a Three-Tier Application

Suppose an order-processing workload has:

- Web tier: `vm-web-01`, `vm-web-02`, serving only HTTPS 443 from a designated entry point.
- API tier: `vm-api-01`, `vm-api-02`, listening on TCP 8080 and accepting new connections only from the web tier.
- Database tier: `vm-db-01` running SQL Server on a VM, listening on TCP 1433 and accepting new connections only from the API tier.
- The tiers reside in three separate subnets in the **same VNet**; VMs are assigned to their respective ASGs.

Intended policy:

| Source | Destination | Port/Protocol | Expected Outcome |
|---|---|---|---|
| Approved web entry point | `asg-web` | TCP 443 | Allow |
| `asg-web` | `asg-api` | TCP 8080 | Allow |
| `asg-api` | `asg-db` | TCP 1433 | Allow |
| Other internal sources | `asg-api` | Other ports | Deny per isolation policy |
| Other sources | `asg-db` | TCP 1433 and unapproved ports | Deny per isolation policy |
| Any Internet source | `asg-db` | Any | Deny |

Rules only take effect when NSGs are attached to the subnets/NICs containing the corresponding VMs. To achieve the desired outcome, evaluate **both default rules** and all other applicable NSGs. In the following hands-on example, we focus on protecting API inbound traffic; apply the same principles when configuring NSGs for the web and database tiers.

An example inbound rule set for the API subnet:

| Priority | Source | Destination | Port | Access |
|---:|---|---|---|---|
| 200 | `asg-web` | `asg-api` | TCP 8080 | Allow |
| 300 | `VirtualNetwork` | `asg-api` | Any | Deny |
| 65000 (default) | `VirtualNetwork` | `VirtualNetwork` | Any | Allow |

Deny rule 300 is evaluated **before** default Allow 65000, preventing unauthorized internal sources from initiating new connections to the API. However, the `VirtualNetwork` scope and other rules must be carefully reviewed. For example, if the API needs health probes or internal management connections, create dedicated Allow rules for the approved sources and ports at lower priority numbers than the Deny rule.

This is an example of **network segmentation**, not a complete zero-trust model. Continue enforcing service authentication, TLS, data authorization, route control, and OS hardening.

## 7. Hands-On with Azure CLI: Creating NSGs and ASGs

The commands below use **Bash** syntax in Azure Cloud Shell or an environment with a compatible Azure CLI. They assume you have an active subscription, resource group `rg-orders-net-dev`, VNet `vnet-orders-dev`, subnet `snet-api`, and two web/API VM NICs. Names are illustrative. You need permissions to create network resources and update NICs/subnets and NSGs. These commands can alter live network settings; practice in a test environment or follow change-approval processes.

### 7.1. Verify Subscription and Set Variables

```bash
az account show --output table
az account set --subscription "<subscription-id>"

RG="rg-orders-net-dev"
LOCATION="southeastasia"
VNET="vnet-orders-dev"
API_SUBNET="snet-api"
NSG="nsg-orders-api-dev"
ASG_WEB="asg-orders-web-dev"
ASG_API="asg-orders-api-dev"
WEB_NIC="nic-orders-web-01"
API_NIC="nic-orders-api-01"
```

Before attaching rules, verify that the NICs and subnet exist in the target resource group and that the VMs belong to the same VNet. For production infrastructure, manage configurations with Bicep/ARM templates or Infrastructure as Code tooling rather than manual edits.

### 7.2. Create Two ASGs

```bash
az network asg create \
  --resource-group "$RG" \
  --name "$ASG_WEB" \
  --location "$LOCATION"

az network asg create \
  --resource-group "$RG" \
  --name "$ASG_API" \
  --location "$LOCATION"
```

Retrieve the Resource IDs for explicit use in subsequent commands:

```bash
ASG_WEB_ID=$(az network asg show \
  --resource-group "$RG" --name "$ASG_WEB" \
  --query id --output tsv)

ASG_API_ID=$(az network asg show \
  --resource-group "$RG" --name "$ASG_API" \
  --query id --output tsv)
```

### 7.3. Assign NIC IP Configurations to ASGs

Assume each NIC has an IP configuration named `ipconfig1`. Confirm the actual name in your environment before running.

```bash
az network nic ip-config list \
  --resource-group "$RG" \
  --nic-name "$WEB_NIC" \
  --output table

az network nic ip-config list \
  --resource-group "$RG" \
  --nic-name "$API_NIC" \
  --output table
```

Then update membership:

```bash
az network nic ip-config update \
  --resource-group "$RG" \
  --nic-name "$WEB_NIC" \
  --name ipconfig1 \
  --application-security-groups "$ASG_WEB_ID"

az network nic ip-config update \
  --resource-group "$RG" \
  --nic-name "$API_NIC" \
  --name ipconfig1 \
  --application-security-groups "$ASG_API_ID"
```

If an IP configuration already belongs to another ASG whose membership must be preserved, check the update command's behavior and pass the full list of groups to retain; avoid accidentally dropping existing memberships. Add other web/API VMs to their corresponding ASGs the same way.

### 7.4. Create the NSG and API Rules

```bash
az network nsg create \
  --resource-group "$RG" \
  --name "$NSG" \
  --location "$LOCATION"

az network nsg rule create \
  --resource-group "$RG" \
  --nsg-name "$NSG" \
  --name Allow-Web-To-Api-8080 \
  --priority 200 \
  --direction Inbound \
  --access Allow \
  --protocol Tcp \
  --source-asgs "$ASG_WEB_ID" \
  --source-port-ranges "*" \
  --destination-asgs "$ASG_API_ID" \
  --destination-port-ranges 8080
```

The rule above allows **new** TCP 8080 connections from web ASG members to API ASG members, but does not yet block other traffic permitted by default rules. To establish an internal boundary for the API, add a Deny rule with higher priority than the default:

```bash
az network nsg rule create \
  --resource-group "$RG" \
  --nsg-name "$NSG" \
  --name Deny-Other-VNet-To-Api \
  --priority 300 \
  --direction Inbound \
  --access Deny \
  --protocol "*" \
  --source-address-prefixes VirtualNetwork \
  --source-port-ranges "*" \
  --destination-asgs "$ASG_API_ID" \
  --destination-port-ranges "*"
```

**Deployment warning:** Deny rule 300 can unexpectedly block internal connections if specific Allow rules are missing. Before applying in production, confirm DNS sources, health checks, management tooling, backups, monitoring services, and required operational traffic. If an NSG is also attached to the API NIC, inspect NIC rules as well, because a subnet Allow rule cannot override a NIC Deny rule.

### 7.5. Attach the NSG to the API Subnet

```bash
az network vnet subnet update \
  --resource-group "$RG" \
  --vnet-name "$VNET" \
  --name "$API_SUBNET" \
  --network-security-group "$NSG"
```

This operation protects the API subnet and can affect **every** NIC associated with the subnet. If the subnet contains VMs outside `asg-api`, some of their flows may still be allowed by default rules; therefore, do not assume this represents a complete policy for all resources in the subnet. Inventory the entire subnet, existing NSGs, and connectivity requirements before updating.

## 8. Inspecting Configuration and Actual Network Flows

### 8.1. Read Back Rules and Associations

```bash
az network nsg rule list \
  --resource-group "$RG" \
  --nsg-name "$NSG" \
  --output table

az network vnet subnet show \
  --resource-group "$RG" \
  --vnet-name "$VNET" \
  --name "$API_SUBNET" \
  --query "{name:name,nsg:networkSecurityGroup.id}" \
  --output json

az network nic ip-config show \
  --resource-group "$RG" \
  --nic-name "$API_NIC" \
  --name ipconfig1 \
  --query "{name:name,asgs:applicationSecurityGroups}" \
  --output json
```

Inspect configuration across all three places: where **rules are defined** (NSG), where **enforcement is attached** (subnet/NIC), and where **membership is assigned** (ASGs on NIC IP configurations).

### 8.2. Effective Security Rules and IP Flow Verify

The rules visible inside a single NSG are not necessarily the entire effective policy on a VM. Azure Network Watcher provides tools such as:

- **Effective security rules:** aggregates all rules relevant to a NIC, including NSGs applied at both NIC and subnet levels.
- **IP flow verify:** evaluates an IP flow by source/destination, direction, protocol, and port, returning Allow/Deny along with the matching rule.
- **Connection troubleshoot:** checks connectivity between source and destination within supported scope, useful when the cause may lie outside NSGs.

A reference command to view effective NSG rules on a NIC:

```bash
az network nic list-effective-nsg \
  --resource-group "$RG" \
  --name "$API_NIC" \
  --output json
```

Diagnostic operations may require a running VM, appropriate permissions, and Network Watcher enabled. When testing a flow, record all parameters—**source IP, source port, destination IP, destination port, protocol, and direction**; omitting any parameter can lead to the wrong conclusion.

### 8.3. Test Matrix

For the three-tier scenario, once NSGs are fully configured on the required subnets/NICs:

| Test Case | Expected Result | If Unexpected |
|---|---|---|
| Web → API, TCP 8080 | Allowed | Check web/API ASGs, both NSG levels, routes, host firewall, listening process |
| Web → API, TCP 22 | Denied unless covered by a special Allow rule | Check default `AllowVnetInBound` and rule priority order |
| Non-web internal VM → API, TCP 8080 | Denied | Check Deny rule 300 and any lower-numbered Allow rules |
| API → DB VM, TCP 1433 | Allowed only if DB rules are properly configured | Check DB NSG; the API lab alone does not configure DB rules |
| Internet → DB VM | Denied per DB policy | Check public IPs, NSGs, routes, and actual ingress paths |

Commands like `curl` or `nc` from a source VM can test target ports, but success or failure also depends on whether the application is listening, OS state, DNS, routes, load balancers, and other network components. Network Watcher helps isolate NSG decisions from application issues.

## 9. How Do NSG, ASG, Azure Firewall, and WAF Differ?

| Component | Primary Purpose | What Not to Expect |
|---|---|---|
| **NSG** | Filter traffic by IP, port, protocol, direction, and rule priority | Does not perform deep HTTP inspection or OWASP protection at the application layer |
| **ASG** | Group NICs by role for referencing inside NSG rules | Does not Allow/Deny traffic or attach to subnets by itself |
| **Azure Firewall** | Centralized network security policy and traffic inspection based on service features and SKU | Does not replace RBAC, workload identity, or all host-level security controls |
| **Web Application Firewall (WAF)** | Protects HTTP/HTTPS traffic against web attack patterns when integrated with supported services | Does not filter arbitrary TCP traffic between VMs |
| **Route table / UDR** | Dictates traffic forwarding paths | Not an Allow/Deny access control list like an NSG |

Do not confuse **DNS resolution** with **network authorization**. DNS only helps clients find a service's IP address. NSGs do not generally authorize outbound traffic by domain name/FQDN like an application-aware firewall. If you need FQDN-based outbound filtering or Layer 7 inspection, evaluate the appropriate service rather than attempting to force ASGs to do it.

NSGs also do not determine which users log into an application, do not encrypt traffic themselves, and do not replace least-privilege access for service accounts, Key Vault, or databases.

## 10. Common Configuration Mistakes

**Adding only Allow rules and assuming other sources are blocked.** NSGs include `AllowVnetInBound` by default. Review default rules and add properly ordered Deny rules when segmenting traffic.

**Assuming an ASG protects a VM on its own.** An ASG is only a membership group. Without NSG rules referencing the ASG and an NSG attached at the proper scope, the ASG enforces nothing.

**Setting source port equal to destination port.** When web calls API on TCP 8080, the source port is typically ephemeral, not 8080. Inbound rules usually set `source-port-ranges="*"` and restrict the destination port by service.

**Forgetting a NIC NSG after allowing at the subnet.** Traffic can still be blocked at the NIC layer. Inspect effective rules on the NIC instead of reading only one NSG.

**Overly broad Deny rules.** An internal Deny rule can inadvertently block management, health checks, or essential services. Map dependencies and test before updating production.

**Ignoring existing active connections.** Because NSGs are stateful, rule changes may not immediately terminate established sessions. Incident containment must combine application, host, and network actions.

**Assuming ASGs act as filters for all PaaS services.** ASGs primarily apply to supported VM NIC IP configurations. PaaS services require their own networking and identity capabilities.

**Treating an Allow rule as a guarantee of connectivity.** Routes, DNS, network appliances, Windows/Linux firewalls, VM power state, and listening applications still determine whether connections succeed.

**Allowing administrative access from `Any`.** Ports such as SSH/RDP must be tightly restricted, favoring secure management approaches like Azure Bastion, private connectivity, or controlled just-in-time access. Do not open them to the Internet just for quick testing.

## 11. Workflow for Building Production NSG/ASG Policies

1. **Map traffic flows:** document workloads, sources/destinations, protocols, ports, directions, and owners for every flow.
2. **Classify roles:** decide which ASGs correspond to VM groups sharing network permissions; separate ASGs when requirements diverge.
3. **Define enforcement points:** choose subnet NSGs, NIC NSGs, or both per governance conventions; inventory existing NSGs.
4. **Design the allowlist:** explicitly declare needed flows. Check for default Allow rules that could widen policy beyond intent.
5. **Add controlled Deny rules:** set clear priorities and scopes while preserving valid infrastructure flows.
6. **Deploy via IaC:** manage ordering, naming, rule priorities, ASG memberships, and NSG associations in reviewable version control.
7. **Verify before and after changes:** check effective rules, IP flow verify, live connectivity, and applications; watch alerts post-deployment.
8. **Monitor and review:** document exceptions, audit `Any` rules, remove stale rules/ASGs, and update configurations as VMs scale.

For changes that could sever server access, establish an independent recovery path and rollback plan before applying.

## 12. Hands-On Exercise

A VNet `10.30.0.0/16` contains:

- `snet-web`: `vm-web-01` and `vm-web-02` in `asg-web`.
- `snet-api`: `vm-api-01` in `asg-api`.
- `snet-db`: `vm-db-01` in `asg-db` (database running on a VM).

Business requirement: web calls API over TCP 8080; API calls DB over TCP 1433. Other VMs must not freely open connections to these two tiers.

**Tasks:**

1. Build a table of required inbound rules for the API and DB subnets, including priority, source ASG, destination ASG, port, and Allow/Deny.
2. Explain why you cannot simply create two Allow rules and ignore `AllowVnetInBound`.
3. Describe how to assign `vm-web-02` to the ASG without modifying target rules.
4. Predict the outcome if the API subnet NSG allows 8080 while the API NIC NSG denies 8080.
5. If web → API still fails even though IP flow verify reports Allow, list at least three causes to investigate.

**Solution guidance:** for API, use an Allow from `asg-web` to `asg-api` on TCP 8080, followed by a Deny for remaining internal sources to the API; for DB, use an Allow from `asg-api` to `asg-db` on TCP 1433, followed by a Deny for other sources per policy. Check rule order carefully and preserve valid operational flows. Assign the ASG on the new VM's IP configuration; no VM IPs need to be added to NSG rules. Both NSG levels must allow the flow. If effective NSG rules allow it yet connections still fail, inspect routes, DNS, guest OS firewalls, and whether the service is listening on the port.

## 13. Self-Check Questions

**1. Between NSG and ASG, which directly allows or denies traffic?** NSG. An ASG is only used as a source/destination criterion inside an NSG rule.

**2. Is rule priority 120 or 300 evaluated first?** Priority 120, because lower numbers have higher precedence.

**3. Why can VMs in the same VNet communicate by default even with a newly created NSG?** Because default NSGs include `AllowVnetInBound` and `AllowVnetOutBound`.

**4. Is a reverse inbound rule required for return packets of an allowed outbound connection?** Typically no; NSGs track flow state. A new connection initiated from the opposite side still requires rule evaluation.

**5. Does adding a VM to an ASG automatically block other traffic?** No. There must be NSG rules referencing the ASG and an NSG applied at the appropriate subnet/NIC.

**6. Can Azure SQL Database PaaS be treated like a VM inside `asg-db`?** No. It must be designed using PaaS networking features and supported mechanisms, such as private endpoints where appropriate.

## 14. Deployment Checklist

- [ ] Documented diagram of VNet, subnets, NICs, and permitted traffic flows.
- [ ] Distinguished inbound, outbound, and stateful return traffic.
- [ ] Listed both **custom rules** and **default rules**, especially `AllowVnetInBound`.
- [ ] No duplicate priorities within the same direction of an NSG.
- [ ] Rules tightly scoped to required sources, destinations, protocols, and ports.
- [ ] ASG members fall within supported VNet scope and are attached to the right NIC IP configurations.
- [ ] NSGs attached to the correct subnets/NICs; checked for overlapping NSGs.
- [ ] Preserved essential Allow rules before applying internal Deny rules.
- [ ] Verified effective rules and tested both allowed and denied connections.
- [ ] Prepared rollback, monitoring, and secure administrative access.
- [ ] Configuration managed via IaC or an auditable change process.

## Conclusion

**NSGs** are where Azure evaluates Allow/Deny rules by direction, source, destination, port, protocol, and priority. **ASGs** group members by application role so rules depend less on individual VM IP addresses. When combined properly, you can segment traffic across web, API, and database tiers while scaling or replacing VMs under a consistent connectivity policy.

In day-to-day operations, always read default rules alongside custom ones, inspect both subnet and NIC NSGs, verify effective flows with Network Watcher, and maintain defense-in-depth at other layers. Secure network design must go hand in hand with identity, TLS, logging, monitoring, recovery, and change governance across your Azure architecture.
