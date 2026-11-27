# Azure Firewall and Firewall Policy Management

In the **CLOUD_PROVIDERS_AZURE** module, learners explore the Microsoft Azure ecosystem—from subscriptions, resource groups, and Microsoft Entra ID to virtual networks, compute services, storage, and data. The goal is to deploy, monitor, secure, and control costs for an application architecture on Azure. In the **Network Connectivity and Security** chapter, **Azure Firewall** provides a centralized traffic inspection point, while **Firewall Policy** helps manage security rulesets in an auditable, reusable structure.

Imagine a company with a VNet hosting an ordering application. Application servers need to call certain external APIs to verify payments, but they should not freely access every address on the Internet. The security team also wants to restrict connections between application networks and log denied flows. Instead of maintaining scattered rules on individual VMs, the company can place Azure Firewall along the traffic path and use Firewall Policy to declare permitted connections.

After this lesson, you will be able to:

- Explain the capabilities and boundaries of Azure Firewall compared to NSGs, ASGs, and WAF.
- Describe the hub-and-spoke model, how UDRs steer traffic to the firewall, and the role of DNS proxy.
- Distinguish Network, Application, and DNAT rules, rule collections, rule collection groups, and Firewall Policy.
- Design rule priorities, allowlists, deny rules, and policy inheritance with appropriate scope.
- Create a baseline Firewall Policy using Azure CLI, manage rules with a structured workflow, and verify traffic paths.
- Use logs, Azure Monitor, and network diagnostic tools to pinpoint causes when connectivity fails.
- Estimate cost drivers and operational risks when deploying a centralized firewall.

## 1. What Is Azure Firewall?

**Azure Firewall** is a managed, **stateful** network firewall service on Azure used to filter traffic according to access policies. You can deploy the firewall into a VNet or use a supported Azure Virtual WAN model to centralize traffic control across many workloads.

Typical capabilities, depending on SKU and configuration, include:

- Filtering traffic by **source/destination address, port, and protocol** using network rules.
- Controlling **HTTP/HTTPS application connections by FQDN** using application rules.
- Forwarding inbound connections from public addresses/ports to internal targets via **Destination NAT (DNAT)** when supported by the architecture.
- Logging rule decisions and providing telemetry for diagnostics.
- Applying **threat intelligence filtering** and advanced capabilities such as IDPS and TLS inspection on appropriate SKUs.
- Managing rules centrally via **Firewall Policy**, which integrates cleanly with Infrastructure as Code (IaC).

Azure Firewall is a network filtering service; **it does not automatically force every packet in a VNet through itself**. Flows are inspected only when the network routes traffic through the firewall (or when traffic arrives at the firewall's public address in a supported inbound scenario). Consequently, a correct policy paired with wrong routing can still leave the firewall unable to observe or block the intended path.

Azure Firewall does not replace Microsoft Entra ID authentication, TLS encryption, host operating system firewalls, Web Application Firewalls, or data protection policies. A secure architecture always uses defense in depth.

## 2. Comparing Network Security Components

| Component | Primary Role | Scope Considerations |
|---|---|---|
| **Network Security Group (NSG)** | Allow/Deny rules by IP, port, protocol, and direction on a subnet or NIC | Ideal for network segmentation close to workloads; lacks full FQDN-based application filtering |
| **Application Security Group (ASG)** | Groups VM NICs/IP configurations by role to serve as NSG rule sources/targets | ASGs do not block traffic by themselves |
| **Azure Firewall** | Centralized stateful inspection point on paths routed through the firewall | Requires proper deployment, routing, RBAC, policy, and logging |
| **Web Application Firewall (WAF)** | Protects HTTP/HTTPS traffic against common application-layer attacks | Does not replace a network firewall for all protocols and paths |
| **Route table / UDR** | Dictates where packets are sent next | Routing does not equal Allow/Deny authorization |
| **Private endpoint** | Provides private connectivity to supported services via an IP inside the VNet | Does not replace data authorization or firewall policies along other paths |

For example, an NSG can restrict the web subnet to calling the API subnet only on TCP 8080. Azure Firewall can enforce centralized outbound policy across multiple spoke VNets: APIs can only call `api.partner.example` over HTTPS 443. If the web app needs protection against SQL injection or HTTP attack patterns, WAF plays a dedicated role at the web ingress tier.

Using both NSGs and Azure Firewall in the same architecture does not create a conflict: a connection must still be allowed by every effective control along the path. An Azure Firewall Allow rule does not override an NSG Deny or a VM's host firewall.

## 3. Azure Firewall Deployment Components

A common deployment pattern is **hub-and-spoke**:

```text
                              Internet / External Azure Services
                                           ^
                                           |
                                      Azure Firewall
                                    (hub VNet, policy)
                                           ^
                                           |
                                      VNet peering
                                           |
                +--------------------------+----------------------+
                |                          |                      |
           App spoke                  Data spoke             Shared spoke
           10.20.0.0/16              10.30.0.0/16            10.40.0.0/16
                |                          |                      |
           UDRs point to firewall when flows require centralized inspection
```

The **Hub VNet** holds shared network infrastructure such as Azure Firewall. **Spoke VNets** hold workloads. VNet peering and proper routing/forwarding configurations allow spokes to use the inspection point in the hub.

### 3.1. AzureFirewallSubnet

When deploying Azure Firewall into a VNet, the firewall requires a dedicated subnet named **`AzureFirewallSubnet`**. This subnet must meet the sizing and requirements of the chosen SKU/deployment model; Azure Firewall deployment guidance typically requires a **/26 or larger address space** for this subnet. Do not place regular workload VMs inside this dedicated subnet.

Illustrative design example:

| Component | CIDR / Address | Role |
|---|---|---|
| Hub VNet | `10.10.0.0/16` | Shared infrastructure network |
| `AzureFirewallSubnet` | `10.10.0.0/26` | Dedicated subnet for Azure Firewall |
| Firewall private IP | `10.10.0.4` | Assumed address used to illustrate the next hop |
| App spoke | `10.20.0.0/16` | Hosts API servers |
| API subnet | `10.20.1.0/24` | Has a route table forwarding controlled traffic |

The address `10.10.0.4` is only an example. In a real deployment, retrieve the **actual private IP assigned to your Azure Firewall** from its configuration; never hardcode or assume a fixed address.

Depending on the SKU, management model, and forced tunneling capabilities, a dedicated management subnet **`AzureFirewallManagementSubnet`** and its associated networking requirements may be required or optional. Never apply a template built for one SKU to another without checking the corresponding deployment guidance.

### 3.2. Routing Determines Whether the Firewall Sees Traffic

Suppose VM `10.20.1.10` initiates an outbound HTTPS connection to the Internet. If the subnet's effective routes point directly to the Internet next hop rather than the firewall, egress rules in Azure Firewall **will not be enforced for that flow**.

A commonly used spoke egress route is:

```text
Destination prefix: 0.0.0.0/0
Next hop type:      VirtualAppliance
Next hop address:   <Azure-Firewall-private-IP>
```

Do not blindly apply a default route to every subnet. Evaluate outbound needs of platform services, PaaS services, on-premises paths, specialized routes, management traffic, gateways, private endpoints, and **symmetric routing**. Asymmetric forward and return paths can cause a stateful firewall to drop connections or make troubleshooting confusing.

In hub-and-spoke designs, inspect peering settings and the option allowing **forwarded traffic** where required by the architecture. Azure Virtual WAN uses its own routing mechanisms and should not copy traditional VNet peering steps verbatim.

### 3.3. Public IP, SNAT, and DNAT

Azure Firewall can use public IPs for supported scenarios. When outbound traffic from a private IP goes to the Internet via the firewall, **Source NAT (SNAT)** translates the source address to the firewall's public IP per service rules.

**DNAT** translates the destination IP/port of an inbound connection at the firewall to the IP/port of an internal service. For instance, connections to the firewall's public IP on TCP 8443 can be mapped to an internal server on TCP 443 via a specific rule, if supported by the network model and service SKU.

DNAT does not mean publishing an application safely: you still need source access controls, TLS, NSGs, OS hardening, and usually a WAF if the app serves HTTP/HTTPS traffic to public users. Avoid exposing SSH/RDP publicly merely because DNAT looks simple.

## 4. What Role Does Firewall Policy Play?

**Azure Firewall Policy** is a resource that centrally manages Azure Firewall settings and rule sets. Rather than editing scattered rules manually, organizations can manage policies as versioned configurations that are reviewed and deployed through structured workflows.

Conceptual hierarchy:

```text
Azure Firewall
   |
   +-- Linked Firewall Policy
         |
         +-- Rule Collection Group (priority)
         |     +-- Rule Collection (priority, action, type)
         |     |     +-- Rule 1
         |     |     +-- Rule 2
         |     +-- Rule Collection
         |
         +-- Another Rule Collection Group
         |
         +-- SKU-appropriate policy settings:
               DNS / threat intelligence / TLS inspection / ...
```

A **Rule Collection Group (RCG)** groups rule collections and carries a priority for ordering. A **Rule collection** defines a group of rules of the same type with one action (Allow or Deny for filter collections; NAT collections use the corresponding translation action). A **Rule** describes a specific traffic flow to match.

Example separation of responsibilities:

| Object | Example | Responsible Owner |
|---|---|---|
| Firewall Policy | `pol-fw-hub-prod` | Platform and security team |
| Rule collection group | `rcg-egress-app-prod` | Policy governance team |
| Application collection | `allow-partner-https` | Proposed by app owner, approved by security |
| Rule | `Allow-Orders-Partner-Api` | Allows API subnet to call approved FQDNs |

Firewall Policies can be shared across multiple firewalls within supported limits and features. Managing policy separately from the firewall instance reduces configuration drift across environments adhering to the same standards.

### 4.1. SKUs and Features

Azure Firewall offers **Basic, Standard, and Premium** tiers with different feature sets and deployment prerequisites. Basic targets simpler requirements; Standard provides most common filtering capabilities; Premium adds advanced capabilities such as **TLS inspection** and **IDPS** when configured, alongside supported standard features.

Never assume a feature exists on every SKU. Before designing, check:

- Which capabilities and throughput limits each SKU supports.
- Corresponding VNet/subnet/public IP/management interface deployment prerequisites.
- Support and limits for DNS proxy, threat intelligence, FQDN filtering, Web categories, TLS inspection, IDPS, and policy inheritance.
- Fixed hourly costs, data processing charges, logging, and related network resources.

For **TLS inspection**, understand certificate setup, CA lifecycles, which connections can or cannot be inspected, and impacts on security, privacy, and application behavior. Never enable it broadly just to work around a routing issue.

## 5. Three Rule Types in Azure Firewall

### 5.1. Network Rules

Network rules control traffic primarily by **source address, destination address, port, and protocol** such as TCP/UDP. They fit connections requiring specific IP/port controls—for example, an app server connecting to an internal service on TCP 5432.

Illustrative example:

| Property | Value |
|---|---|
| Source | `10.20.1.0/24` |
| Destination | `10.30.2.10` |
| Protocol | TCP |
| Destination port | 5432 |
| Action | Allow |

If using an FQDN as the destination in a **network rule** where supported, configure and enable **DNS proxy** per Azure Firewall requirements. That behaves differently from application rules. To control HTTPS by hostname, application rules are generally preferable to a network rule allowing TCP 443 to broad IP ranges.

### 5.2. Application Rules

Application rules control supported application-layer connections, typically HTTP/HTTPS based on **FQDN** and matching protocols/ports.

Example: an API in subnet `10.20.1.0/24` may call only `api.partner.example` over HTTPS TCP 443. Place that rule inside an **Application Rule Collection** specifying the API subnet as source, HTTPS protocol, and the target FQDN.

An FQDN-based application rule does not necessarily inspect full URL paths or HTTPS payloads. Inspection depth depends on protocol, TLS metadata, and enabled features. Deep TLS decryption/inspection requires matching configuration and SKU. Avoid treating an FQDN-based HTTPS Allow rule as a substitute for API security reviews, authentication, certificate validation, or data protection.

### 5.3. DNAT Rules

DNAT rules translate the **destination address/port** at the firewall to a new internal destination address/port. Example:

```text
External source (restricted by policy)
     |
     | Firewall Public IP:8443
     v
 Azure Firewall (DNAT rule)
     |
     | 10.20.1.10:443
     v
 Web server in spoke
```

DNAT is used for publishing authorized inbound services. You must design proper return paths, check NSGs, routes, load balancing, and inbound support in your Azure Firewall deployment model. Never open access to the entire Internet automatically just for testing.

### 5.4. Quick Comparison

| Rule Type | Primary Match Criteria | Typical Scenario |
|---|---|---|
| Network | IP / port / protocol, and supported options | TCP traffic between subnets, internal apps to specific servers |
| Application | FQDN, supported application protocols | Restricting outbound websites/APIs by domain |
| DNAT | Destination address/port translation | Publishing an internal service via the firewall's public address |

## 6. Policy Processing Order and Priority Principles

Unlike a flat list of rules, Azure Firewall Policy organizes rules by **type**, **collection group**, **collection**, and **rule**. Each layer has distinct semantics.

Key principles to remember:

1. For standard rules, Azure Firewall evaluates by rule type with **DNAT first, then Network, then Application**. A network rule can decide a flow before application rules are ever evaluated.
2. Within the corresponding evaluation scope, **lower priority numbers take precedence**. Rule Collection Groups and Rule Collections have separate priority spaces; those two numbers do not form a single flat sequence across all rule types.
3. Filter rule collections are configured as **Allow** or **Deny**. A matching rule processed at that layer determines the flow's fate there. If no matching rule allows the flow, the default action is **deny**.
4. Where policy inheritance is supported, the **parent policy takes precedence over child policies**; child policies must not be treated as a way to relax restrictions imposed by the parent.
5. Features such as threat intelligence filtering or advanced inspection can add block/alert decisions, so actual outcomes also depend on policy and SKU settings.

**Practical consequence:** if you create a Network Allow rule for TCP 443 from the entire API subnet to all Internet addresses, it can permit traffic beyond the FQDN set you tried to restrict with application rules. When designing FQDN-allowlisted egress, avoid overly broad network rules on the same protocol/port.

Example collection organization:

| Policy Layer | Example | Purpose |
|---|---|---|
| RCG `rcg-network-required` | Network collection `allow-private-service` | Permits required private connectivity by IP/port |
| RCG `rcg-app-egress` | Application collection `allow-approved-sites` | Allows only specific FQDNs over HTTP/HTTPS |
| RCG `rcg-inbound-publish` | NAT collection `dnat-published-service` | Publishes an approved inbound endpoint |

Assign priorities deliberately, and document the owner and business justification for every rule. If adding a Deny rule to block a specific traffic group, verify where that Deny sits in the evaluation pipeline rather than picking a very low priority number and assuming it overrides all rule types.

## 7. Parent and Child Firewall Policies

For SKUs and configurations **supporting policy inheritance**, you can build layered policies:

```text
Base policy (parent)
  +-- Shared security constraints
  +-- Mandatory enterprise network rules
          |
          +-- App A policy (child)
          |      +-- Allows Partner A domains
          |
          +-- App B policy (child)
                 +-- Allows Partner B domains
```

The parent policy is typically managed by the security team, while child policies can be managed by application teams within delegated boundaries. The goal is **reusing baseline controls** while letting each workload define its own tailored rules.

For example, the parent policy can block unauthorized destinations across the organization; application teams cannot expect adding an Allow rule in a child policy to override that Deny. Always account for rule type, evaluation order, and specific inheritance behavior.

When using inheritance:

- Verify that the SKU and parent-child relationship are supported by Azure.
- Clarify who owns the parent policy and who may edit child policies.
- Follow naming and priority conventions; avoid overly broad or overlapping collections.
- Document exceptions and approval workflows.
- Test outcomes after parent changes because one edit can affect many firewalls/workloads.
- Track which policy is attached to each firewall before deleting or replacing anything.

In smaller organizations, a single policy per firewall may be easier to manage. Introduce hierarchy only when reuse and delegation benefits outweigh added complexity.

## 8. DNS Proxy and FQDN-Based Traffic Control

When an application calls a hostname like `api.partner.example`, DNS first resolves that hostname to one or more IP addresses. If the workload uses a different DNS resolver than Azure Firewall, resolution results can diverge over time or across network zones. This is especially critical when using **FQDNs in network rules**.

**DNS proxy** allows Azure Firewall to receive DNS queries from clients and forward them to configured DNS servers. When enabled and properly configured, the firewall can use the resolution data it observes to support FQDN filtering in network rules within service capabilities.

Design steps:

1. Select an appropriate upstream DNS server: Azure-provided DNS or the organization's custom resolver per architecture.
2. Enable DNS proxy on the firewall/policy per SKU and supported procedure.
3. Configure workloads or VNets to send DNS queries to Azure Firewall's private IP when the design requires DNS proxy.
4. Verify name resolution on source hosts and inspect rule hits in firewall logs.
5. Check alternate DNS paths, caching, split-horizon DNS, private DNS zones, and private endpoints if used.

**DNS proxy does not replace Application Rules.** Application rules inspect application hostnames from supported HTTP/HTTPS traffic metadata, whereas FQDNs in network rules resolve to IP addresses. With shared IPs hosting multiple domains, a network rule permitting an IP address may not constrain domains the same way an application rule does.

Never allowlist domains of unknown origin or overly broad wildcards. For apps with rapidly changing DNS records, test real behavior against Firewall Policy and SDK/client constraints.

## 9. Designing Egress Policy for an Ordering Application

Suppose an e-commerce system sits in a spoke VNet and routes outbound traffic through Azure Firewall in the hub. The API must call a partner service to validate transactions while also connecting internally to a database. Any flow outside the approved list must be denied.

### 9.1. Traffic Matrix

| Source | Destination | Protocol/Port | Recommended Policy |
|---|---|---|---|
| API subnet `10.20.1.0/24` | `api.partner.example` | HTTPS 443 | Application Allow, specific target domain |
| API subnet `10.20.1.0/24` | DB VM `10.30.2.10` | TCP 5432 | Network Allow if routed via firewall |
| API subnet `10.20.1.0/24` | Unlisted Internet | Any | No matching Allow rule; denied by default |
| Test subnet | Production database | TCP 5432 | No Allow rule; optionally add explicit Deny to state policy clearly |
| Approved admin host | Supported management endpoint | Minimal ports | Dedicated rules following secure admin workflows |

`api.partner.example` is an illustrative domain, not an actual Azure-validated or required endpoint. If a real partner uses multiple domains for auth, redirects, or content delivery, the deployment team must verify the exact domain list and paths before authoring rules.

Outbound path diagram:

```text
orders-api (10.20.1.10)
        |
        | DNS resolves, app connects over HTTPS 443
        v
Subnet route table: 0.0.0.0/0 -> Firewall private IP
        |
        v
Azure Firewall + Policy
        |
        +-- Application Allow matches api.partner.example -> Internet
        |
        +-- No matching Allow -> Deny, recorded in logs
```

This diagram illustrates a single egress flow. Actual paths require verifying **effective routes**, peering, NSGs, DNS, NAT, and host firewalls. For internal DB connections, a `0.0.0.0/0` route may not capture traffic if a more specific system or peering route exists; add or adjust routes explicitly if policy requires internal traffic to traverse the firewall.

### 9.2. Why Avoid Creating a Broad Network Allow for All Internet Port 443?

Suppose a policy has:

- Network Allow: `10.20.1.0/24` → `*`, TCP 443.
- Application Allow: `10.20.1.0/24` → `api.partner.example`, HTTPS 443.

The network rule can allow the flow before application rules are evaluated. Thus, the application allowlist loses effectiveness for traffic matching that overly broad network rule. A cleaner design creates network rules only for destinations **genuinely needing IP/port rules**, while using application rules for domain-based HTTP/HTTPS egress.

### 9.3. Explicit Deny Rules vs. Default Deny

Azure Firewall denies traffic by default if no matching rule allows it. Therefore, you do not need a catch-all Deny in every collection just to achieve default-deny behavior. However, organizations can use explicit Deny rules for specific destinations, protocols, or source groups to enforce policy clearly and aid auditing.

When adding an explicit Deny, check evaluation order across **rule types and policy hierarchy**. A misplaced Deny can block valid flows or fail to trigger as expected.

## 10. Hands-On: Creating Firewall Policy and Routing with Azure CLI

This lab uses **Bash** syntax in Azure Cloud Shell or a machine with compatible Azure CLI. This is a conditional design example: assume the platform team already created the hub VNet, spoke VNet, network links, firewall, and app subnet. Replace all variables with real values in your lab environment. Execute route changes only in a test environment or under an approved change process, as bad routes can sever connectivity.

### 10.1. Confirm Subscription and Create Policy

```bash
az account show --output table
az account set --subscription "<subscription-id>"

RG="rg-network-hub-dev"
LOCATION="southeastasia"
POLICY="pol-azfw-hub-dev"
RCG="rcg-egress-dev"

az network firewall policy create \
  --resource-group "$RG" \
  --name "$POLICY" \
  --location "$LOCATION" \
  --sku Standard
```

This command creates a **Firewall Policy** at the Standard SKU. It **does not deploy a live Azure Firewall processing traffic**. If no firewall exists yet, deploy an Azure Firewall in your VNet/Virtual WAN meeting subnet, IP, and SKU requirements and link the policy per the supported deployment process.

Inspect the policy resource:

```bash
az network firewall policy show \
  --resource-group "$RG" \
  --name "$POLICY" \
  --output json
```

### 10.2. Create a Rule Collection Group

```bash
az network firewall policy rule-collection-group create \
  --resource-group "$RG" \
  --policy-name "$POLICY" \
  --name "$RCG" \
  --priority 200
```

The newly created group is a container for adding rule collections. Before permitting application traffic, document requirements and configure the exact ruleset via the Azure Portal or IaC.

Example planned configuration presented as an **illustrative business specification** (not raw YAML directly importable into Azure):

```yaml
policy: pol-azfw-hub-dev
ruleCollectionGroup: rcg-egress-dev
groupPriority: 200
collections:
  - name: allow-partner-https
    type: Application
    priority: 200
    action: Allow
    rules:
      - name: Allow-Orders-Partner
        sourceAddresses: ["10.20.1.0/24"]
        protocols: ["Https:443"]
        targetFqdns: ["api.partner.example"]
  - name: allow-private-db
    type: Network
    priority: 300
    action: Allow
    rules:
      - name: Allow-Api-To-Db
        sourceAddresses: ["10.20.1.0/24"]
        destinationAddresses: ["10.30.2.10"]
        destinationPorts: ["5432"]
        protocols: ["TCP"]
```

This spec serves as a review artifact for rules. When entering via **Azure Portal**, open Firewall Policy → **Rule collection groups** → select the group → add collections and their rules. When deploying with **Bicep, ARM, or Terraform**, map fields to the exact schema of your provider/API version, validate syntax, and preview changes before applying.

Do not confuse the collection group `priority` with a collection's `priority`. In the example above, the group priority is 200, while collections have their own priorities of 200 and 300. Do not assume Application collection 200 is always evaluated before Network collection 300: **rule type still governs evaluation order**.

### 10.3. Associate the Firewall Policy with a Firewall

In the Azure Portal, open the target **Azure Firewall**, confirm its SKU and deployment model, and assign or switch its policy in the configuration blade. Verify:

1. Which policy is currently attached to the firewall.
2. Whether the policy contains the approved collection groups and rules.
3. Whether alerts, logging, and DNS/threat intelligence settings match expectations.
4. Which team has edit permissions vs. read-only access on the policy.

Updating a policy can simultaneously affect multiple linked firewalls. In production, preview diffs first and roll out progressively across environments with validation tests after each step.

### 10.4. Create a UDR to Route Spoke Traffic Through the Firewall

Assume the firewall is deployed and its real private IP has been confirmed. **The values below are illustrative**:

```bash
SPOKE_RG="rg-orders-dev"
SPOKE_VNET="vnet-orders-dev"
APP_SUBNET="snet-api"
ROUTE_TABLE="rt-orders-egress"
FW_PRIVATE_IP="10.10.0.4"

az network route-table create \
  --resource-group "$SPOKE_RG" \
  --name "$ROUTE_TABLE" \
  --location "$LOCATION"

az network route-table route create \
  --resource-group "$SPOKE_RG" \
  --route-table-name "$ROUTE_TABLE" \
  --name default-via-firewall \
  --address-prefix 0.0.0.0/0 \
  --next-hop-type VirtualAppliance \
  --next-hop-ip-address "$FW_PRIVATE_IP"
```

After verifying hub connectivity and blast radius, associate the route table with the subnet:

```bash
az network vnet subnet update \
  --resource-group "$SPOKE_RG" \
  --vnet-name "$SPOKE_VNET" \
  --name "$APP_SUBNET" \
  --route-table "$ROUTE_TABLE"
```

This command only exemplifies traffic matching `0.0.0.0/0`. More specific routes can take precedence, so inspect effective routes on an actual NIC. Also, changing a subnet's route table can overwrite previously configured routes. If a subnet already has a route table, never replace it blindly—reconcile all existing routes carefully.

### 10.5. Verify Deployed Objects

```bash
az network firewall policy rule-collection-group show \
  --resource-group "$RG" \
  --policy-name "$POLICY" \
  --name "$RCG" \
  --output json

az network route-table route list \
  --resource-group "$SPOKE_RG" \
  --route-table-name "$ROUTE_TABLE" \
  --output table

az network vnet subnet show \
  --resource-group "$SPOKE_RG" \
  --vnet-name "$SPOKE_VNET" \
  --name "$APP_SUBNET" \
  --query "{name:name,routeTable:routeTable.id}" \
  --output json
```

Checking policy and route table objects is necessary but insufficient. Verify via **effective routes**, live tests from the source VM, and firewall logs that traffic genuinely passes through the inspection point and matches the expected rule.

## 11. Monitoring, Diagnostic Settings, and Log Queries

A security policy is only useful when operations teams can see **which rule made a decision**, which flows were denied, and which change triggered an outage.

Azure Firewall can send diagnostics via **Diagnostic settings** to supported targets such as a **Log Analytics workspace**, storage account, or Event Hub depending on retention and integration needs. When using resource-specific log tables, common tables include:

| Log Analytics Table | Typical Contents |
|---|---|
| `AZFWNetworkRule` | Outcomes related to network rules |
| `AZFWApplicationRule` | Outcomes related to application rules |
| `AZFWNatRule` | Events related to NAT rules |
| `AZFWThreatIntel` | Events related to threat intelligence |

Table names and schemas depend on diagnostic settings mode, release timing, and ingestion configuration. If an environment uses legacy diagnostic mode, data may land in the `AzureDiagnostics` table instead; adapt queries to the actual schema.

Basic KQL example for resource-specific tables:

```kusto
AZFWApplicationRule
| where TimeGenerated > ago(1h)
| order by TimeGenerated desc
| take 50
```

To observe network rule volume:

```kusto
AZFWNetworkRule
| where TimeGenerated > ago(1h)
| summarize Events=count() by bin(TimeGenerated, 5m)
| order by TimeGenerated asc
```

The second example counts events per 5-minute bin; it does not prove how many business requests succeeded. To investigate failures, inspect the action, source, destination, rule/collection fields, and correlate with application logs.

Operational logging practices should include:

- Enable required log categories and verify logs actually arrive in the workspace.
- Set retention policies balanced for investigation needs and cost.
- Restrict log read access because connection telemetry reveals infrastructure and app behavior.
- Configure alerts for unusual Deny spikes, suspicious new flows, or critical security events.
- Track changes to Firewall Policy via Azure Activity Log alongside CI/CD/IaC history to see who changed a rule and when.

## 12. Diagnosing Application Connectivity Failures

Suppose `orders-api` cannot call `https://api.partner.example` after enabling Azure Firewall. Determine whether the fault lies in DNS, routing, policy, NSG, or the application itself.

### 12.1. Step-by-Step Investigation Workflow

1. **Verify symptoms:** record timestamp, source IP, target hostname, protocol, port, error code, and environment. Confirm the application actually sent the request.
2. **Check DNS:** from the source host, verify the hostname resolves; check the resolver and DNS proxy if used.
3. **Check effective routes:** confirm the next hop for the target IP actually points to Azure Firewall. Do not infer this solely from the subnet's attached route table, as more specific system routes may override it.
4. **Check linked policy:** is the firewall using the expected policy, collection group, and rule version?
5. **Search firewall logs:** filter by IP, timestamp, FQDN, port, rule, and action to distinguish Allow, Deny, or missing logs.
6. **Check other filtering layers:** NIC/subnet NSGs, OS firewalls, other network appliances, and target-side allowlists.
7. **Check TLS and application:** certificates, proxies, SNI/Host headers, DNS caching, timeouts, partner endpoints, and HTTP errors.
8. **Apply a small, controlled fix:** adjust the targeted rule, deploy via pipeline, retest, and verify logs.

### 12.2. Quick Diagnostic Matrix

| Symptom | Possible Cause | Where to Check |
|---|---|---|
| No logs for the request in firewall | Traffic bypasses firewall or diagnostics not configured | Effective routes, peering, forwarded traffic, diagnostic settings |
| `Deny` log present | Missing Allow rule; explicit Deny precedes; network rule decided before app rule | Rule type, RCG, collection priority, parent/child policy, FQDN/port |
| `Allow` log present but request times out | NSG, missing return route, target service, host firewall, or asymmetric path | Network Watcher, bidirectional routes, target application |
| DNS failure or wrong IP | DNS proxy/upstream/Private DNS/caching issue | Resolver, VNet DNS, DNS proxy, and resolution output |
| Only specific domains or URLs fail | Allowlist missing secondary endpoints, TLS/SNI, or rule type difference | Actual target domains, redirects, certificates, rule logs |
| Multiple apps fail simultaneously | Shared policy recently changed, hub network, or firewall incident | Activity Log, policy revision, Azure Service Health, metrics/logs |

**Note:** If the firewall logs Allow at the network layer, that does not guarantee the HTTP request will succeed. The target service can still return 401/403 for auth, 429 for rate limiting, or application errors.

### 12.3. Never Use Allow-All to Troubleshoot

Opening `Any → Any` or letting an entire subnet access `Any:443` may make the outage disappear while defeating egress security goals. When troubleshooting:

- Scope rules to exact IPs/FQDNs, ports, and source ranges.
- Test minimal changes in a non-production environment.
- Set expiration dates and accountable owners on any temporary exceptions.
- Revoke temporary test permissions once root cause is resolved.

## 13. Operating Firewall Policy Like a Product with a Lifecycle

A single policy is often shared across teams and can affect many applications. Therefore, establish a workflow from **proposal → review → deployment → verification → rule retirement**.

### 13.1. Standardizing Connection Requests

Each request should capture at least:

| Field | Example |
|---|---|
| Workload and environment | `orders-api`, production |
| Source | `10.20.1.0/24` or appropriate IP Group |
| Destination | `api.partner.example` |
| Protocol and port | HTTPS 443 |
| Business purpose | Send transaction verification requests |
| Owner | Ordering application team |
| Duration | Long-term or with expiration date |
| Validation test | Valid call succeeds; unapproved targets are blocked |

For multiple source or destination addresses serving the same purpose, consider **IP Groups** supported by Azure Firewall to reuse address sets across rules. However, only group IPs sharing ownership and access scope; editing a shared IP Group impacts every rule referencing it.

### 13.2. Managing via IaC and Source Control

A healthy workflow includes:

1. Developer or ops team submits the connectivity request with justification.
2. Security team reviews least privilege across source, destination, port, rule type, and parent/child policy impact.
3. Changes are authored in the IaC repository (Bicep/ARM/Terraform) with a description and ticket reference.
4. CI pipeline validates syntax/schema, compares against current policy, and runs **what-if/plan** per tooling support.
5. Apply first in a test environment with logically equivalent routes and NSGs.
6. Deploy to production per change controls, validating with logs and connectivity tests.
7. Record results and retire unused rules during periodic reviews.

If emergency edits happen in the Portal, enforce change tracking and reconcile IaC promptly to prevent **configuration drift**. When a policy is shared across firewalls, regression testing must cover critical flows for affected workloads.

### 13.3. Clear Naming and Priority Conventions

Example naming:

- Policy: `pol-fw-hub-prod`.
- Group: `rcg-egress-payments`.
- Collection: `app-allow-approved-partners`.
- Rule: `Allow-Orders-To-Payment-Api`.

Good conventions make log correlation and owner lookup fast. Leave numerical gaps between priorities so new rules can be inserted cleanly, while remembering that priorities **never override rule-type evaluation order**.

Avoid cramming every team's rules into one giant collection if that makes reviews painful. Conversely, do not create a separate collection for every single endpoint. Group rules by shared owner, scope, action, and lifecycle.

### 13.4. Safe Changes and Rollback

When a new rule could disrupt egress for multiple apps:

- Inventory critical network paths and connections before the change.
- Test rules in non-production, validating both Allow and Deny behavior.
- Keep the prior commit/configuration and a tested rollback procedure ready.
- Avoid changing routing, NSGs, and Firewall Policy simultaneously unless necessary.
- Record deployment timestamps to correlate logs and application feedback.

Deleting a policy or rule collection while firewalls or workloads still depend on it can break connectivity. Verify all associations and active traffic before cleaning up rules.

## 14. Availability, Security, and Cost

Azure Firewall is a managed service, yet architectures must still account for availability and limits of the SKU, region, and deployment model. When designing:

- Check **availability zones** and feature availability by Azure region and SKU.
- Assess the blast radius of a hub outage on dependent spokes, including both outbound and inter-network links.
- Size scaling, throughput, concurrent connections, DNS handling, and logging capacity.
- Monitor Azure Service Health, metrics/logs, and recovery workflows; never assume every network outage is caused by firewall policy.
- Consider multi-region architectures and redundant routing if applications carry corresponding recovery targets.

### 14.1. Cost Drivers

Azure Firewall pricing is typically driven by **deployment uptime and data processed** under the chosen SKU. Depending on the architecture, additional charges may accrue for public IPs, VNet peering, data transfer, Log Analytics workspaces, Azure Monitor, gateways, and supporting network services.

A realistic cost estimate should cover:

| Item | What to Estimate |
|---|---|
| Firewall SKU | Basic/Standard/Premium and regional unit rates |
| Uptime hours | Hours the firewall remains provisioned |
| Data processed | GB/TB of egress, ingress, and inter-network traffic traversing the firewall |
| Network charges | Public IPs, peering, gateways, or data transfer per design |
| Monitoring | Log ingestion, retention, queries/alerts per configuration |
| Advanced features | Premium capabilities and associated operational costs |

Do not estimate cost by counting firewall rules. Data volume traversing the firewall and provisioning hours are major cost drivers. Use the **Azure Pricing Calculator** and current regional pricing to build estimates, then track **Cost Management** to compare actuals against projections.

### 14.2. When Should You Use a Centralized Firewall?

A centralized firewall pays off when an organization operates multiple workloads/VNets and needs consistent egress control, shared logging, auditable rule governance, or reusable rule sets. For small systems, the cost and operational complexity of Azure Firewall may outweigh its benefits compared to NSGs, destination-side network access controls, and simpler networking options.

Base the choice on security requirements and traffic paths—not simply because a particular Azure resource exists.

## 15. Hands-On Exercise

### Scenario

A company has:

- `spoke-orders`: API in subnet `10.20.1.0/24`.
- `spoke-analytics`: reporting tool in subnet `10.40.1.0/24`.
- Azure Firewall in the hub, private IP `10.10.0.4` (assumed).
- The API may call only `api.partner.example` over HTTPS 443.
- The reporting tool must connect to a private DB VM on TCP 5432.
- Neither spoke may access the Internet freely.

**Requirements:**

1. Diagram the outbound path and propose the required UDRs, explaining why checking effective routes is mandatory.
2. Choose Network or Application Rule Collection for each flow and specify source, destination, protocol, port, and action.
3. Explain the design flaw if a Network Allow rule exists from both subnets to `Any` on TCP 443.
4. List at least three pieces of evidence that must appear in logs or an incident record if the API fails to reach the partner domain.
5. Propose how to structure parent/child policies when security wants to enforce baseline restrictions while app teams only add business allowlists.
6. Analyze what router/NSG/DNS changes could break connectivity even when the firewall rule logs Allow.

**Solution hints:** use an application rule for FQDN-based HTTPS; use a network rule for TCP 5432 to the DB VM IP. Route inspected paths through the firewall, potentially adding specific routes for internal traffic. Never create a `Network Allow Any:443` rule because it undermines FQDN filtering. Capture source IP, hostname/destination, timestamp, rule type, action, routes, and DNS. Keep baseline restrictions in the parent policy and permitted app rules in child policies per supported inheritance.

### Self-Check Questions

**1. Does creating a Firewall Policy automatically block outbound egress for all VMs?** No. The policy must be attached to a firewall and traffic must actually route through that firewall.

**2. Why might an FQDN-based Application Allow rule fail to restrict all HTTPS traffic?** A broad Network Allow rule can permit traffic before application rules run; also inspect routes, alternate egress paths, and FQDN visibility.

**3. What is DNAT used for?** Translating destination IP/port of inbound connections to an internal service's IP/port in supported scenarios.

**4. Is RCG priority the only number deciding all rule evaluation order?** No. Rule type and collection priority also affect evaluation order.

**5. If the firewall logs Allow but the application times out, what should you inspect?** Effective routes, return paths, NSGs, host firewalls, DNS, target endpoint, TLS, and application health.

**6. Why exercise caution when editing a parent policy?** One change can affect multiple child policies and firewalls, impacting many workloads simultaneously.

## 16. Checklist Before Moving Azure Firewall to Production

- [ ] Defined control objectives, spoke count, inbound/outbound flows, and inter-VNet requirements.
- [ ] Selected SKU based on required capabilities, regional availability, and cost estimate.
- [ ] Allocated dedicated subnets and public/private IP components per deployment prerequisites.
- [ ] Verified VNet peering/Virtual WAN, forwarded traffic, UDRs, and **effective routes**.
- [ ] Documented source, destination, protocol, port, owner, and expiration for every flow.
- [ ] Distinguished Network, Application, and DNAT rules; understood rule evaluation order.
- [ ] Avoided overly broad Network Allow rules that bypass application allowlists.
- [ ] Validated DNS, DNS proxy, and private DNS/endpoint dependencies if used.
- [ ] Configured RBAC for policy management, and parent/child policy hierarchy if needed and supported by SKU.
- [ ] Adopted IaC, change control, peer review, and tested rollback procedures.
- [ ] Configured diagnostic settings, Log Analytics, log retention, and alerts.
- [ ] Tested both Allow and Deny cases, including live connectivity and NSG/host layers.
- [ ] Reviewed availability, recovery, throughput, data processing costs, and scalability.

## Conclusion

**Azure Firewall** enforces centralized network inspection across traffic routed through it. **Firewall Policy** organizes rules into rule collection groups, collections, and rules that can be governed centrally, audited, and deployed via IaC. Network rules handle IP/port/protocol controls; application rules govern FQDN-based application traffic; DNAT rules handle supported inbound destination translation.

For the architecture to work reliably, combine **Firewall Policy + routing + DNS + NSGs + monitoring**. When a flow is blocked, rely on effective routes and firewall logs to isolate the exact enforcement point. A well-designed policy expresses least-privilege connectivity, assigns clear ownership, is validated through testing, and is maintained throughout the application lifecycle.
