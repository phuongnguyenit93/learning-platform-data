# Combining ExpressRoute and VPN for Redundancy

An application on Microsoft Azure may need to continuously exchange data with an enterprise data center: querying internal databases, syncing identities, sending transactions to an ERP system, or calling services still hosted on-premises. If all traffic depends on a single WAN link, a carrier outage, network device failure, or routing misconfiguration can disrupt the application even while Azure resources remain completely healthy.

**ExpressRoute** provides private connectivity from the enterprise network to the Microsoft network via a connectivity provider. **Site-to-Site VPN (S2S VPN)** establishes an IPsec/IKE tunnel over the public Internet. By connecting an on-premises network to an Azure Virtual Network (VNet) using both methods simultaneously, an enterprise can prefer ExpressRoute for daily operations while keeping VPN as a backup path when the primary link is unavailable.

In the CLOUD_PROVIDERS_AZURE module, this architecture connects directly to subscriptions, resource groups, virtual networks, VPN Gateway, ExpressRoute Gateway, Azure Monitor, governance permissions, and cost. The most critical lesson here is that **high availability depends on both ends of the link and routing policy**, not merely on both connections showing a Connected state.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the roles of ExpressRoute and VPN in a redundant hybrid connectivity design.
2. Identify the components: ExpressRoute circuit, private peering, ExpressRoute virtual network gateway, VPN gateway, local network gateway, and BGP.
3. Design a VNet containing both an ExpressRoute Gateway and a route-based VPN Gateway under Azure's coexistence support rules.
4. Describe path selection, failover to VPN when ExpressRoute fails, and failback to the primary path upon recovery.
5. Build a checklist for monitoring, failover drills, and troubleshooting asymmetric routing.
6. Evaluate encryption requirements, network segmentation, service limits, and costs of the backup path.

Recommended background knowledge: IP addresses/CIDRs, route tables, Azure Virtual Networks, subnets, Azure VPN Gateway, Azure RBAC, and reading resource status in the Azure Portal or Azure CLI.

## 2. Comparing ExpressRoute and Site-to-Site VPN

| Criterion | ExpressRoute | Site-to-Site VPN |
|---|---|---|
| Transport path | Private connection via connectivity provider or Microsoft peering location | IPsec/IKE tunnel over the Internet |
| Traffic characteristics | Does not traverse the public Internet along normal ExpressRoute paths | Packets traverse the Internet, with tunnel payload protected by IPsec |
| Encryption | Not automatically encrypted end-to-end simply by using ExpressRoute | VPN tunnel uses IPsec/IKE encryption when properly configured |
| Capacity | Multiple bandwidth options depending on circuit, gateway, and provider | Depends on VPN Gateway SKU, device, Internet link, and IPsec settings |
| Latency | Typically more stable via private connection, though still dependent on provider and actual path | Can vary with Internet conditions |
| Routing technology | BGP over private peering, linking the circuit to a VNet gateway | Can use BGP in supported configurations; other route configuration methods exist |
| Role in this architecture | Primary path for hybrid traffic | Backup path when ExpressRoute routes are withdrawn or unavailable |
| Cost | Circuit, provider, gateway, and data transfer per applicable pricing model | VPN Gateway, public IPs, Internet/transit, and egress/traffic charges |
| Best fit | Workloads requiring private, predictable connectivity | Rapid connectivity expansion, backup, or sites without an ExpressRoute circuit |

**ExpressRoute is not encrypted by default.** Even over a private network, sensitive data should still use TLS or encryption mechanisms matching security requirements. Site-to-Site VPN encrypts flows over the Internet; however, that does not give the Internet the same SLA or predictability as a dedicated private link.

An ExpressRoute circuit natively includes redundant physical links on the Microsoft and provider sides per the service model. However, redundancy within a single circuit does not eliminate shared points of failure such as the same building entrance, CPE device, carrier, or routing configuration error. Backup VPN provides the greatest value when its Internet circuit and terminating hardware are designed to minimize shared dependencies with ExpressRoute.

## 3. Combined Architecture in a Single Azure Virtual Network

### 3.1. Connectivity Model

Suppose an enterprise has an on-premises data center using 172.20.0.0/16 and a hub VNet on Azure using 10.40.0.0/16. Logical model:

~~~mermaid
flowchart LR
    D["On-premises DC\n172.20.0.0/16"] --> R["Enterprise\nRouter/Firewall"]
    R -->|Private connectivity provider| C["ExpressRoute circuit\nPrivate Peering"]
    C --> EG["ExpressRoute Gateway"]
    R -->|Internet + IPsec/IKE| V["Site-to-Site VPN"]
    V --> VG["VPN Gateway"]
    subgraph A["Azure: Hub VNet 10.40.0.0/16"]
      EG --> H["Hub network / shared services"]
      VG --> H
      H --> S["Applications, data services,\nauthorized workloads"]
    end
~~~

In this model:

- The ExpressRoute circuit and private peering create a private link from the enterprise network to Microsoft.
- The **ExpressRoute virtual network gateway** connects the VNet to the circuit.
- The **Route-based VPN Gateway** establishes a tunnel to the on-premises VPN device over the Internet.
- The two gateways serve two separate connection types while delivering traffic into the same VNet when coexistence is supported.
- BGP and routing policies on both sides determine the primary path and how failover occurs.

This diagram is a logical model. In Azure, the ExpressRoute Gateway and VPN Gateway are deployed as two distinct gateway resources of different types. You do not configure a single gateway that switches types between ExpressRoute and VPN.

### 3.2. Required Components and Functions

| Component | Function |
|---|---|
| Hub VNet | Azure virtual network connecting back to the enterprise; can act as a central hub to other workloads |
| GatewaySubnet | Dedicated subnet for virtual network gateways inside the VNet |
| ExpressRoute circuit | Circuit provisioned by the provider and Microsoft, associated with private peering |
| ExpressRoute Gateway | Connection point between the VNet and the ExpressRoute circuit |
| VPN Gateway | Gateway for Site-to-Site connections using IPsec/IKE |
| Local Network Gateway | Azure resource describing the public IP, BGP peer, and/or network prefixes on the on-premises side |
| VPN connection | Connection resource linking the Azure VPN Gateway and the on-premises site |
| Customer Edge router/firewall | On-premises device managing BGP, IPsec, route policies, and failover switching |
| Azure Monitor/Network Watcher | Monitors gateway health, circuits, routes, and application connectivity |

Azure services often vary by region, SKU, gateway type, and coexistence limits. Therefore, check the support documentation and quotas for your **exact subscription, region, and SKU** before deploying. Never assume every SKU combination supports running ExpressRoute and VPN simultaneously.

### 3.3. IP Address Planning

Example valid addressing plan:

| Scope | Illustrative CIDR | Purpose |
|---|---|---|
| On-premises | 172.20.0.0/16 | Enterprise network |
| Azure hub VNet | 10.40.0.0/16 | Hybrid connectivity and shared services |
| GatewaySubnet in hub | 10.40.255.0/26 | Subnet for gateways per design |
| Workload subnet in hub | 10.40.10.0/24 | Apps/services placed in hub if needed |
| Azure spoke VNet (optional) | 10.41.0.0/16 | A workload VNet peered with the hub |

A critical requirement is **non-overlapping address ranges** across networks that route to each other. If systems already have overlapping CIDRs, re-address the networks or evaluate product-supported NAT mechanisms; NAT should not be treated as an uncontrolled quick fix because it complicates tracing and failover.

GatewaySubnet needs enough address space for the gateways in use and future expansion. The /26 example above is an illustrative planning choice and does not replace minimum subnet requirements for specific SKUs and features. If a smaller GatewaySubnet already exists, assess the impact before resizing or adding another gateway.

When using a hub-spoke model with gateway transit over VNet peering, verify the Allow gateway transit / Use remote gateways settings and constraints on peered networks. Spokes do not automatically see all on-premises routes simply by peering with a hub; verify route propagation, UDRs, and return routes.

## 4. Prerequisites for ExpressRoute and VPN to Back Up Each Other

### 4.1. Gateway Requirements

A standard coexistence design requires:

1. An ExpressRoute circuit that has been provisioned successfully, with private peering routing properly configured.
2. An Azure VNet using an ExpressRoute Gateway that supports linking to the circuit.
3. A **route-based** VPN Gateway using an Azure-supported SKU and configuration for coexistence.
4. A sufficiently sized GatewaySubnet and IP addresses/public IPs for the VPN Gateway as required by the SKU.
5. An IPsec/IKE-compatible VPN device on-premises with a dedicated Internet link or access to the Internet during ExpressRoute outages.
6. Synchronized route scopes, BGP ASNs, BGP peering IPs, and router policies across both sides.

When higher resilience is needed on the VPN side, you can deploy an **active-active VPN Gateway** and multiple on-premises devices/tunnels if supported by the SKU, hardware, and scenario. Active-active primarily increases the fault tolerance of the VPN path; it does not turn VPN into a private circuit and does not guarantee application failover if routes are misadvertised.

**Do not use a policy-based VPN Gateway for this architecture.** Combining ExpressRoute with VPN and automatic BGP failover requires a route-based design and verified SKU support.

### 4.2. Keep the Two Paths as Independent as Possible

The value of a backup path is undermined if both links share dependencies on:

- A single physical router acting as a common point of attachment.
- An unredundant power source, switch, or WAN port.
- A single fiber path or carrier whose outage drops both ExpressRoute and the Internet simultaneously.
- A single firewall or BGP ruleset where one misconfiguration breaks both paths at once.
- The same authentication system or management plane sitting behind the failed link itself.

Map out all dependency points and test each failure mode. For systems with strict RTO/RPO targets, you may need **two ExpressRoute circuits at different peering locations/providers**, VPN as an additional backup layer, or a multi-region architecture; one ExpressRoute circuit plus one VPN tunnel does not cover every failure scenario.

## 5. How BGP Chooses the Active Path

### 5.1. Why BGP Is Essential for Failover

BGP (Border Gateway Protocol) allows both sides to advertise reachable prefixes and withdraw routes when the associated session or path becomes unavailable. When ExpressRoute and VPN connect to the same VNet, Azure and on-premises can learn prefixes from both sources and select routes according to routing policy.

For example, both paths provide reachability to:

~~~text
On-premises prefix: 172.20.0.0/16

Primary path: ExpressRoute private peering
Backup path: Site-to-Site VPN using BGP
~~~

In typical Azure coexistence configurations, **ExpressRoute is preferred over VPN for the same on-premises prefix when route selection criteria are otherwise equal**. However, route selection is also influenced by **longest-prefix match**, UDRs, Azure network configuration, BGP state, and on-premises policies. Never treat "ExpressRoute always wins" as an absolute rule for every packet.

Important example: if VPN advertises 172.20.10.0/24 while ExpressRoute only advertises 172.20.0.0/16, traffic to 172.20.10.5 will prefer VPN because /24 is more specific than /16. This is a common design error when the two paths advertise inconsistent prefix sets.

### 5.2. Controlling Bidirectional Traffic

Distinguish between the **Azure → on-premises** direction and the **on-premises → Azure** direction.

| Traffic Direction | What Primarily Selects the Path? | What to Check |
|---|---|---|
| Azure → on-premises | Effective routes at the Azure source, routes learned via gateways, and associated UDRs | Prefixes, ER/VPN preference, route propagation, gateway health |
| On-premises → Azure | Enterprise router/firewall using BGP policy / local preference / route policy | Local preference, prefix-lists, AS path, next hop, tunnel, and return path |
| Between spoke VNets via hub | Spoke routes, VNet peering/gateway transit, and traffic inspection setup | UDRs, gateway transit, route propagation, firewall/NVA |

If one end prefers ExpressRoute while the other prefers VPN, **asymmetric routing** occurs. Asymmetric routing does not always fail, but stateful firewalls, NAT devices, traffic inspection appliances, and on-premises equipment frequently drop packets when they do not see both directions of a session.

Therefore, verify both forward and return paths, especially for TCP services, private endpoints, intermediate firewalls, or NAT.

### 5.3. Reference Route Policy

An initial route policy might look like this:

| Route/Prefix | Over ExpressRoute | Over VPN | Goal |
|---|---|---|---|
| 172.20.0.0/16 (on-prem) | Advertised | Same prefix advertised | Azure can use VPN when ER is unavailable |
| 10.40.0.0/16 (Azure hub) | Valid advertisement | Valid advertisement | On-premises has paths to hub via both methods |
| 10.41.0.0/16 (spoke, if present) | Per confirmed transit/routing capability | Per confirmed transit/routing capability | Traffic reaches workloads as designed |
| 0.0.0.0/0 | Only if required with a forced tunneling design | Do not advertise arbitrarily | Prevent unintended Internet egress rerouting |

On the enterprise router, BGP policy can raise preference for Azure routes learned over ExpressRoute and keep VPN as backup. Exact implementation depends on the device and internal network standards—such as local preference or appropriate path selection policies. Never copy a set of local preference values without reviewing existing routes in the environment.

**Do not advertise overly broad routes or prefixes you do not own.** Use prefix-lists, route filters, device max-prefix limits, and monitoring for route leaks. If you use UDRs pointing to a network virtual appliance or disable BGP route propagation on a subnet, automatic failover behavior may differ from the baseline design.

### 5.4. Sequence During an ExpressRoute Outage

Expected failover flow:

~~~mermaid
sequenceDiagram
    participant O as On-premises Network
    participant E as ExpressRoute
    participant B as VPN/BGP
    participant A as Azure Workload
    O->>E: Production traffic over preferred path
    E->>A: Connection active
    Note over E: Link or valid route lost
    E--xA: Primary path no longer available
    Note over O,A: BGP/route policy updates and converges
    O->>B: Select backup VPN route
    B->>A: Traffic over IPsec tunnel
    Note over O,A: Verify return path and application status
~~~

All of the following conditions must hold simultaneously:

1. The system detects that the ExpressRoute path is lost or no longer preferred.
2. VPN routes remain advertised and accepted.
3. Both the enterprise router and Azure hold valid return routes.
4. The VPN tunnel, firewalls, NAT, and application services have sufficient capacity for the traffic.
5. Application connection state can recover if existing TCP sessions were interrupted.

**Failover does not mean zero disruption.** BGP takes time to detect loss, withdraw routes, and converge; existing sessions may have to reconnect. Actual recovery time depends on configuration and network conditions—never promise a fixed number of seconds without measuring it in the real environment.

### 5.5. Failback When ExpressRoute Recovers

When ExpressRoute routes return and preference policies apply, traffic shifts back from VPN to ER. You must:

- Confirm both BGP sessions / VPN and ExpressRoute links are stable.
- Verify that received routes match the expected prefixes.
- Watch for route flapping (repeated withdrawal/re-advertisement) causing recurring path switches.
- Assess application load and stateful firewall sessions when the path changes.
- Verify service health and latency after failback, rather than relying only on gateway status.

Certain BGP policy or timer tweaks can speed up convergence while also increasing the risk of route flapping. Test in a lab environment and follow vendor guidance before adjusting production settings.

## 6. Step-by-Step Deployment Workflow

This is a design sequence for deploying via the Azure Portal or Infrastructure as Code; menu labels and feature support may evolve across Azure releases.

### Step 1. Gather Connectivity Details

Document clearly:

- Subscription ID, resource group, Azure region, and target VNet.
- CIDRs for the Azure hub, spokes, and on-premises networks; confirm zero overlap.
- Bandwidth, latency, session-drop tolerance, and recovery requirements of the applications.
- Existing ExpressRoute circuit, provider, private peering, BGP ASN/peering IPs, and provisioning state.
- On-premises CPE/router, VPN public IP, IKE/IPsec parameters, BGP ASN, and allowed advertised prefixes.
- Primary/backup routing strategy, monitoring, admin permissions, drill plan, and rollback steps.

If an ExpressRoute circuit is already live, inventory all prefixes currently in use before adding VPN. Avoid making bulk changes to primary-path routing policies during the same change window as adding the backup path.

### Step 2. Plan the VNet and GatewaySubnet

Example layout:

~~~text
Subscription: sub-connectivity-prod
Resource group: rg-hub-network-prod
Region: southeastasia

Hub VNet: vnet-hub-prod-sea
  Address space: 10.40.0.0/16

  GatewaySubnet: 10.40.255.0/26
  Subnet-App:    10.40.10.0/24

ExpressRoute Gateway: gw-er-hub-prod
VPN Gateway:          gw-vpn-hub-prod
~~~

GatewaySubnet is dedicated to gateways. Do not place VMs, firewall appliances, or application services inside GatewaySubnet. The illustrative /26 range must fit inside the VNet address space and not overlap any other subnet.

Before deploying, verify that the ExpressRoute Gateway SKU, VPN Gateway SKU, and gateway coexistence are supported in the target region. For multi-zone environments, consider gateway SKUs supporting zone redundancy if availability requirements call for it.

### Step 3. Connect ExpressRoute

Administrative sequence:

1. Order/provision the ExpressRoute circuit with the appropriate model and provider.
2. Complete provisioning between the provider and Microsoft.
3. Configure private peering and BGP with the enterprise using the provider's details.
4. Create the ExpressRoute Gateway in the hub VNet.
5. Link the circuit to the gateway via an ExpressRoute connection.
6. Verify circuit status, peering, BGP routes, and reachability to Azure subnets.

Private peering does not become operational automatically just because a circuit is created. Verify BGP sessions and actual routes before moving to the backup step.

### Step 4. Set Up VPN as the Backup Path

1. Deploy a route-based VPN Gateway in the same hub VNet per coexistence requirements.
2. Create a Local Network Gateway describing the on-premises site, including public IP and BGP/prefix settings as needed.
3. Create a Site-to-Site VPN connection from the VPN Gateway to the Local Network Gateway.
4. Configure the matching settings on the on-premises firewall/router, including IKE/IPsec, peer IP, security policies, and BGP if used.
5. Verify tunnel status, BGP peering, and learned routes.
6. Confirm ExpressRoute remains the preferred path as designed, ensuring adding VPN does not unintentionally shift primary traffic.

Pre-shared keys or VPN credentials must be stored per secrets management policies; never write them into repositories, terminal history, or public documents.

### Step 5. Tune Routes and Test Both Directions

Verify:

- Azure learns on-premises prefixes via both expected paths.
- On-premises receives the required Azure prefixes via both ExpressRoute and VPN.
- When both are active, the primary path is selected.
- NSGs, Azure Firewall/NVAs, UDRs, and on-premises firewalls permit application traffic.
- No unexpected default route pulls Internet traffic back through the data center.
- Spokes and Private Endpoints can use the hybrid path only where routing and DNS are properly configured.

**DNS is part of the hybrid architecture.** When applications call internal private names, verify DNS resolvers, Private DNS zones/links, and name resolution over the backup path. Working IP connectivity does not keep an application running if DNS depends on a failed primary path.

### Step 6. Configure Monitoring, Alerts, and Drills

Create dashboards tracking circuit status, BGP, VPN tunnels, errors, and service reachability. Configure Action Groups or incident management integrations so on-call engineers receive alerts. Then execute one controlled failover drill and one failback drill, recording real evidence.

## 7. Observing Status with Azure CLI

The following commands are primarily for **reading configuration and status**, suitable for pre- and post-drill inspection. Examples use Bash syntax; replace names with your environment's actual resource names.

### 7.1. Inspect Subscription and Both Gateways

~~~bash
az account show --output table

az network vnet-gateway show \
  --resource-group rg-hub-network-prod \
  --name gw-er-hub-prod \
  --query "{name:name,type:gatewayType,sku:sku.name,state:provisioningState}" \
  --output table

az network vnet-gateway show \
  --resource-group rg-hub-network-prod \
  --name gw-vpn-hub-prod \
  --query "{name:name,type:gatewayType,sku:sku.name,bgp:enableBgp,state:provisioningState}" \
  --output table
~~~

Do not confuse `provisioningState` with end-to-end traffic health. A gateway showing `Succeeded` can still have a downed tunnel, wrong routes, or a firewall blocking traffic.

### 7.2. Check Connections and BGP Status

~~~bash
az network vnet-gateway connection show \
  --resource-group rg-hub-network-prod \
  --name conn-er-hub \
  --query "{name:name,type:connectionType,status:connectionStatus}" \
  --output table

az network vnet-gateway connection show \
  --resource-group rg-hub-network-prod \
  --name conn-vpn-onprem \
  --query "{name:name,type:connectionType,status:connectionStatus}" \
  --output table

az network vnet-gateway list-bgp-peer-status \
  --resource-group rg-hub-network-prod \
  --name gw-vpn-hub-prod \
  --output table
~~~

Inspect routes learned via BGP on a supported gateway:

~~~bash
az network vnet-gateway list-learned-routes \
  --resource-group rg-hub-network-prod \
  --name gw-vpn-hub-prod \
  --output table
~~~

Command names, support, and returned columns depend on the Azure CLI version, gateway type, and BGP configuration. If expected routes are missing, inspect BGP on both sides, prefix filters, and tunnel state. Do not treat an empty command result as definitive proof that on-premises lacks routes if the operator lacks permissions or queried the wrong resource.

### 7.3. Check the ExpressRoute Circuit

~~~bash
az network express-route show \
  --resource-group rg-connectivity-prod \
  --name er-main-prod \
  --query "{name:name,sku:sku.tier,circuitState:circuitProvisioningState,providerState:serviceProviderProvisioningState}" \
  --output table
~~~

A provisioned circuit does not guarantee that BGP private peering, the gateway connection, and application calls are working. You must verify peering status and test actual connectivity, coordinating with the provider if a carrier network issue is suspected.

### 7.4. Test from a Source Machine to a Real Destination

From an authorized VM or application host, test connecting to an internal service on its real port. For example, in PowerShell on a Windows VM:

~~~powershell
Test-NetConnection -ComputerName 172.20.10.20 -Port 443
~~~

Or on Linux, if the service supports HTTPS with an appropriate certificate:

~~~bash
curl --connect-timeout 5 --max-time 15 \
  https://internal.example.invalid/health
~~~

The IP address and hostname in these examples are placeholders. Testing must target a real endpoint with valid authentication; do not disable TLS verification just to get an HTTP success code.

In addition to connectivity, record latency, error rate, convergence time, DNS results, return path, and long-lived session behavior. A `Connected` gateway status is a necessary indicator but insufficient to prove application experience.

## 8. Failover and Failback Drill Scenarios

### 8.1. Preparing Before the Drill

Drills must have a schedule, an accountable owner, a defined blast radius, and a rollback plan. In production, execute only under change approval and organizational runbooks. Test the model in a non-production environment or narrow scope first.

Initial checklist:

1. Both ExpressRoute and VPN are healthy; BGP peers are in the expected state.
2. Snapshot Azure and on-premises routing tables and both gateways' statuses.
3. Have end-to-end telemetry ready: TCP/application health probes, DNS checks, timeouts, and error rates.
4. Define start time, pass/fail criteria, abort thresholds, and rollback ownership.
5. Maintain an out-of-band management path to recover if a route change breaks primary connectivity.
6. Ensure application, infrastructure, security, and provider teams are aware of the test window.

### 8.2. Test Matrix

| Scenario | Controlled Simulated Action | Expected Observation |
|---|---|---|
| Both paths healthy | Check connectivity and routes with both paths up | Traffic flows via ExpressRoute per policy; VPN is ready |
| ExpressRoute path lost | Coordinate with router/provider to drop or withdraw advertisements in test scope | VPN is selected after convergence; application recovers |
| ExpressRoute recovers | Restore routes/peering in test scope | Traffic returns to ER once stable, without flapping |
| Backup VPN fails while ER is up | Simulate VPN tunnel down independently | App stays running on ER; backup-path alert triggers properly |
| Single on-premises branch failure | Isolate one device/tunnel in a multi-device setup | Remaining paths sustain connectivity as designed |
| Wrong or filtered route | Test route policy in a lab | Missing prefix detected; no route leak or unintended default route |
| DNS over backup path | Query internal names while ER is shut down in test | Names still resolve; application reaches right destination |

**Never delete gateways/circuits or shut down production links just for a "quick test."** Withdrawing routes, changing peering policies, or cutting links can cause wide outages. Tests must be scoped, documented, and reversible.

### 8.3. Measuring Failover Time

Choose objective timestamps for connection or application RTO:

- T0: moment ExpressRoute path loss is observed by the system.
- T1: moment valid routes via VPN are selected on both sides.
- T2: moment TCP probes and the application begin responding again.
- T3: moment all required workflows stabilize within target criteria.

You can calculate:

~~~text
Network convergence time  = T1 - T0
Application recovery time = T2 - T0
Full stabilization time   = T3 - T0
~~~

Do not equate network convergence time with application recovery time. TCP sessions, database connection pools, DNS caches, stateful firewalls, and retry logic can delay application recovery. Run multiple measurements under realistic conditions, record observed figures, and compare against business requirements.

### 8.4. Evidence and Rollback

A minimum drill record should include:

~~~yaml
testId: NET-DR-ER-VPN-001
environment: non-production
primaryPath: ExpressRoute
backupPath: Site-to-Site VPN
scope:
  azureVnet: vnet-hub-prod-sea
  onPremPrefix: 172.20.0.0/16
preconditions:
  - "BGP peers established"
  - "Gateway connection health verified"
  - "Application probe baseline captured"
observations:
  - "Record T0, T1, T2, T3 in UTC"
  - "Capture route changes and path after failover"
  - "Capture error rate and DNS behavior"
result: "<PASS_OR_FAIL_WITH_EVIDENCE>"
rollback:
  - "Restore original on-prem routing policy"
  - "Verify both paths and primary route preference"
  - "Confirm application health"
~~~

This example is a template, not an actual executed test result. Store records in the change ticket and cross-check against Azure Monitor, BGP route snapshots, and on-premises device logs. Never put VPN keys or sensitive credentials into tickets.

## 9. Post-Deployment Monitoring and Operations

### 9.1. Signals to Monitor

| Component | Suggested Signals | What to Alert On |
|---|---|---|
| ExpressRoute circuit | Circuit/provider provisioning, traffic and link quality, peering status | Primary link lost, provider issue, abnormal traffic |
| ExpressRoute gateway | Gateway health, route availability, SKU-supported telemetry | Azure no longer has a valid route to on-premises |
| VPN Gateway | Tunnel connection status, BGP peer status, ingress/egress, tunnel errors | Backup path unavailable even while ER is still running |
| On-premises network | BGP neighbor state, learned/advertised prefixes, interfaces, ISP availability | CPE failure, missing prefixes, or both paths sharing a single failure point |
| Application | TCP success, DNS, HTTP 5xx, latency, retries, and timeouts | Network failover succeeded but workload is still failing |
| Routing | Effective routes, UDRs, firewall/NVA logs | Wrong next hop, asymmetric routing, route leak, or route flapping |
| Cost | ExpressRoute, gateways, bandwidth, and data transfer | Backup path incurring unexpected continuous charges or unintended VPN traffic |

Set dedicated alerts for **backup path unavailable** even when ExpressRoute is healthy. If you only monitor the application, a broken VPN tunnel may go unnoticed until ExpressRoute actually fails.

Azure Monitor provides different metrics and diagnostic capabilities depending on gateway/circuit type and service tier. Select metrics supported by your active resources and configure Action Groups, runbooks, escalation paths, and tested thresholds.

### 9.2. Incident Response Runbook

A practical runbook should answer:

1. Did the alert originate from the circuit, gateway, BGP session, tunnel, or application?
2. Is actual traffic currently flowing over ExpressRoute or VPN?
3. Do learned/advertised routes match the expected prefixes and scope?
4. Is the failure unidirectional or bidirectional?
5. Does the VPN have enough capacity if all traffic shifts to it?
6. Is there a dependency on the provider, on-premises hardware, DNS, firewall, or private endpoint?
7. Who contacts the carrier, who is authorized to modify routes, and who signs off on recovery?
8. Should the system stay on VPN for a stabilization window before failing back?

During a live incident, prioritize service continuity and collect current logs before making changes whenever feasible. Avoid rapidly changing multiple route policies at once, as it becomes hard to tell which change resolved the fault.

## 10. Security of the Redundant Architecture

### 10.1. Encryption and Data Protection

ExpressRoute uses a private link, but it should not be treated as a complete data encryption mechanism. Enforce TLS at the application layer or an appropriate encryption solution whenever data requires end-to-end protection. VPN uses IPsec/IKE, and requires algorithms, key lifetimes, certificates, or PSKs aligned with organizational policy.

If you need an added encryption layer over ExpressRoute, evaluate solutions compatible with your ExpressRoute tier, hardware, topology, and operational impact. Never assume that configuring a backup VPN automatically encrypts ExpressRoute traffic.

### 10.2. Permissions and Network Controls

- Use Azure RBAC with least privilege for admins managing circuits, gateways, routes, and diagnostic settings.
- Restrict access to BGP, IPsec, public IP, and peering policy details on a need-to-know basis.
- Enforce consistent NSG, Azure Firewall, and on-premises firewall rules across **both** paths; never create a "less restricted" VPN path just because it is only used during outages.
- Restrict advertised and accepted prefixes; avoid accidentally exposing sensitive subnets.
- Apply DNS resolution, firewall inspection, logging, and segmentation consistently across primary and backup paths.
- Check data residency, compliance, and traffic-path requirements when one link fails.

### 10.3. Redundancy Is Not a Security Backup Copy

If a system relies on a single on-premises firewall or DNS service, adding VPN does not remove that shared point of failure. Likewise, if the service account needed to adjust routes is disabled during an outage, the team may be unable to execute recovery. Plan for out-of-band management, backup admin access, and emergency procedures.

## 11. Cost and Performance

A backup path can incur costs **even when no application traffic uses it**. Cost components to budget for include:

- ExpressRoute circuit by bandwidth/tier and provider contract.
- ExpressRoute Gateway by SKU, uptime, and applicable data transfer.
- VPN Gateway and public IP addresses per the selected configuration.
- Internet circuit, secondary WAN link, firewall/router hardware, and operations.
- Egress traffic, data processing, or related charges depending on pricing model and region.
- Azure Monitor/Log Analytics, Network Watcher, and billable monitoring components.

Before deployment, model costs both during steady state and when all traffic fails over to VPN. Check VPN Gateway throughput for your workload type, IPsec algorithms, tunnel count, and remote-device performance. Nominal bandwidth does not necessarily equal achievable application throughput when encryption and many concurrent sessions are involved.

For example, an application transferring large continuous data volumes may run smoothly on ExpressRoute yet experience higher latency and lower throughput on backup VPN. In that case, the business must decide which functions must remain active during a primary outage, whether to shed non-critical load temporarily, or whether to invest in higher Internet/VPN Gateway SKUs.

Azure Cost Management helps track spending, but budget alerts do not automatically throttle or shut down network links when exceeded. Never configure automated cost-saving scripts to tear down a backup VPN without assessing the availability impact.

## 12. Common Errors

### 12.1. VPN Shows Connected but Does Not Take Over Traffic

**Possible causes:** BGP is not enabled, BGP session failed to establish, prefixes are filtered, VPN does not advertise the same required networks, route propagation is disabled, or a UDR pins a fixed next hop.

**How to check:** inspect BGP peers, learned/advertised routes, and effective routes on the source subnet in both directions. Do not look only at `connectionStatus`.

### 12.2. When Both Paths Are Up, Traffic Goes Over VPN

**Possible causes:** VPN advertises a more specific prefix than ExpressRoute, on-premises router policy has wrong preferences, or a UDR steers traffic through a network appliance.

**How to check:** compare route prefixes and prefix lengths, on-premises local preference policies, UDRs, and firewall logs. Fix at the identified policy source after preparing a rollback plan.

### 12.3. Azure Can Reach On-Premises, but On-Premises Cannot Reach Azure

**Possible causes:** missing return route, NAT mismatch, stateful firewall drop, NSG rule, DNS mismatch, or missing rules on backup-path devices.

**How to check:** test TCP in both directions, compare post-NAT source/destination IPs, inspect routes, and check firewall logs. Do not judge success solely by ping since ICMP may be blocked independently.

### 12.4. BGP Is Established, but Applications Cannot Connect

**Possible causes:** BGP neighbor is up but prefixes are rejected, subnet lacks routes, DNS resolves incorrectly, firewall blocks ports, or the backup link lacks sufficient throughput.

**How to check:** distinguish BGP session state from actual installed routes; inspect effective routes, gateway connections, and run application probes.

### 12.5. Failback Causes Disruption Even Though ER Is Healthy

**Possible causes:** route flapping, forward and return paths switching at different times, dropped sessions, stale state on NAT/firewall devices from the VPN path, or lack of application retries.

**How to check:** correlate BGP timelines, route transitions, outage timestamps, and application logs. Define stability criteria for the primary path before allowing failback.

### 12.6. Both ExpressRoute and VPN Fail in the Same Outage

**Possible causes:** both paths share the same router, physical circuit, ISP, power feed, or a route policy error applied to both.

**How to fix:** map dependencies, add independent hardware/ISPs or multiple circuits as required by the business, and audit the full chain from application to carrier.

## 13. Real-World Scenario: Hybrid Order Application

Suppose a company runs an order-intake application on App Service in Azure and a legacy business database in its data center. The app normally reaches the internal service through a hub VNet over ExpressRoute, with Site-to-Site VPN over the Internet configured as backup.

### Normal State

~~~text
App Service / Azure Workload
    ↓ VNet integration / appropriate hybrid route
Hub VNet
    ↓ ExpressRoute Gateway
ExpressRoute private peering
    ↓
On-premises API 172.20.10.20:443
~~~

At this stage, both gateways are monitored. The VPN tunnel is kept ready, BGP routes are validated, and backup costs are budgeted. The application team runs periodic probes against the internal API.

### During an ExpressRoute Outage

ExpressRoute BGP routes are no longer usable. If both sides are configured properly and the VPN tunnel is healthy, VPN routes take over. Some in-flight connections may time out; the application uses bounded retries, connection timeouts, and idempotency/deduplication controls to prevent duplicate orders.

The operations team verifies:

- VPN/BGP states have converged.
- The internal API is reachable on port 443.
- DNS returns the expected IP.
- Application error rates return to acceptable levels.
- Traffic and CPU on the VPN Gateway and on-premises device remain within capacity.

When ExpressRoute recovers, the team verifies primary-path stability, monitors failback, and records metrics in the incident report. This illustrates that the ultimate goal is **maintaining business continuity**, not merely turning a tunnel status green.

## 14. Self-Check Knowledge

1. **Why combine ExpressRoute and VPN?** ExpressRoute provides primary private connectivity; Site-to-Site VPN provides an alternate path over the Internet when the primary path is unavailable.
2. **Does ExpressRoute automatically encrypt all packets?** No. Protect data using TLS or an appropriate encryption solution.
3. **Can a single VNet contain both an ExpressRoute Gateway and a VPN Gateway?** Yes, in Azure-supported coexistence configurations using compatible gateways, SKUs, and GatewaySubnet sizing.
4. **Why do matching prefixes matter?** If VPN advertises a more specific prefix, longest-prefix match can send traffic over VPN even when ExpressRoute is healthy.
5. **Does an Established BGP session mean application connectivity works?** No. You must still verify actual routes, DNS, firewalls, bidirectional paths, and application behavior.
6. **Does on-premises → Azure select paths using the exact same mechanism as Azure → on-premises?** Not necessarily. The enterprise router applies its own BGP policies; both directions must be checked.
7. **Does failover guarantee zero dropped TCP sessions?** No. Convergence time and stateful firewalls can interrupt existing sessions; applications need proper retry handling.
8. **Can an idle backup VPN incur costs?** Yes. Gateways and supporting resources typically carry ongoing charges.
9. **Why test DNS during drills?** Internal names may rely on a DNS resolver reachable only via the failed primary link, even when IP routing works over the backup path.
10. **When ExpressRoute recovers, what should you watch for?** BGP stability, route shift back to ER, route flapping, bidirectional connectivity, and application health.
11. **Does one backup VPN tunnel eliminate every single point of failure?** No. Both paths can still share routers, ISPs, power feeds, or configuration policies.
12. **Which metric reflects actual application recovery?** The time until application health criteria pass again (e.g., T2 − T0), not merely when BGP switches routes.

## 15. References

- [Azure ExpressRoute documentation](https://learn.microsoft.com/azure/expressroute/) — overview of circuits, peerings, gateways, and deployment guidance.
- [ExpressRoute and VPN coexistence](https://learn.microsoft.com/azure/expressroute/expressroute-howto-coexist-resource-manager) — configuring ExpressRoute and Site-to-Site VPN simultaneously in a VNet using Azure Resource Manager.
- [Azure VPN Gateway documentation](https://learn.microsoft.com/azure/vpn-gateway/) — IPsec/IKE, Site-to-Site VPN, SKUs, and gateway configuration.
- [BGP with Azure VPN Gateway](https://learn.microsoft.com/azure/vpn-gateway/vpn-gateway-bgp-overview) — principles and requirements for using BGP.
- [Azure VNet traffic routing](https://learn.microsoft.com/azure/virtual-network/virtual-networks-udr-overview) — route selection, system routes, BGP, and user-defined routes.
- [Azure Network Watcher](https://learn.microsoft.com/azure/network-watcher/) — tools for verifying and monitoring connectivity.
- [Azure Monitor documentation](https://learn.microsoft.com/azure/azure-monitor/) — metrics, diagnostic data, and alerting.

Before moving this architecture into production, verify coexistence requirements, SKU support, limits, and features against Microsoft documentation at deployment time. Gateway health, routing, and application behavior must be validated through a controlled drill before declaring redundancy goals met.
