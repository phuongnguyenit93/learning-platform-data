# Mitigating Attacks with Azure DDoS Protection

> **Chapter:** Network Connectivity and Security  
> **Module:** `CLOUD_PROVIDERS_AZURE` — Explore the Microsoft Azure ecosystem from subscriptions, resource groups, and Entra ID to virtual networks, compute services, storage, and data; learn how to deploy, monitor, secure, and control costs for an application architecture on Azure.

## Lesson Objectives

After this lesson, you will be able to:

1. Identify common **Distributed Denial of Service (DDoS)** attack types and their impact on application availability.
2. Explain how Azure DDoS Protection defends traffic targeting **public IPs of Azure resources** and distinguish it from NSGs, Azure Firewall, and Web Application Firewall (WAF).
3. Compare Azure's default infrastructure protection against **DDoS Network Protection** and **DDoS IP Protection**.
4. Identify the protection scope, link a DDoS protection plan to a VNet when using Network Protection, and verify configurations.
5. Build a monitoring mindset using Azure Monitor, alerts, diagnostic logs, and incident response workflows.
6. Plan controlled verification, assess technical limits, manage permissions, and estimate costs.

## 1. Why Is DDoS Mitigation Needed?

A sales API might run on Azure Virtual Machines, Azure Load Balancer, or Application Gateway. Normally the app handles 2,000 requests/minute; one day, many sources across the Internet simultaneously flood it with massive traffic, preventing real customers from reaching the service.

This could be a **DDoS** attack: multiple coordinated or aggregated sources generating traffic that exhausts the target's network capacity, connection-handling tables, or application resources.

An attacker's goal is not necessarily stealing data; they may aim to make the service **unavailable**. A DDoS attack can cause:

- Access disruption, elevated latency, timeouts, or refused connections.
- Bandwidth saturation or exhaustion of packet/connection processing capacity.
- Backend overload causing cascading failures across gateways, APIs, and databases.
- Lost revenue and damaged trust when critical operations go down.
- Difficulty distinguishing attack traffic from legitimate traffic spikes without proper observability.

**DDoS mitigation** does not mean every malicious packet is dropped or that a service can never experience disruption. The objective is to detect and absorb/filter attack traffic, keep as much legitimate traffic flowing as possible, and maintain visibility for investigation and response.

### How Does DDoS Differ from a Legitimate Traffic Spike?

Both can produce high CPU, high connection counts, and elevated latency. A real flash-sale campaign can also overload an application. Investigation requires correlating:

- Traffic changes over time by protocol, source IP, port, and source distribution.
- Network metrics compared against capacity and normal traffic baselines.
- Valid request volume, HTTP status codes, backend load, and application logs.
- Recent system changes near the incident time, such as new releases or firewall edits.

Never treat "increased traffic" alone as proof of DDoS without supporting telemetry.

## 2. Attack Layers to Distinguish

DDoS attacks are commonly classified by where they apply pressure.

| Category | General Example | Expected Impact | Primary Defense Layer |
| --- | --- | --- | --- |
| **Volumetric** | Massive UDP packets or amplification traffic | Saturates bandwidth, congesting ingress links | Network-layer DDoS mitigation |
| **Protocol / state exhaustion** | Floods of TCP/SYN connection setup requests | Exhausts connection state tables | L3/L4 DDoS Protection, network design, and service configuration |
| **Application-layer** | High volumes of HTTP/HTTPS requests targeting expensive routes | Exhausts app worker threads, CPU, and databases | WAF, rate limiting, caching, auth, and resilient app design |
| **Multi-vector** | Combines network-layer floods with application-layer requests | Pressures multiple layers simultaneously | Defense in depth, unified observability, response playbook |

**L3/L4** refers to the network/transport layers (IP, TCP, UDP). **L7** refers to the application layer (HTTP, APIs, business logic). Azure DDoS Protection focuses on mitigating **L3/L4** attacks; defending against HTTP floods or business-logic abuse requires complementary application-layer controls.

Do not equate a DDoS attack with password brute-forcing, SQL injection, or code-level exploits. Both pose security risks, but they require different detection signals and protective controls.

## 3. How Does Azure DDoS Protection Work?

Microsoft operates Azure's underlying infrastructure with platform-level DDoS defense. **Azure DDoS Protection** is a service that adds dedicated mitigation, telemetry, and management capabilities for traffic targeting supported **public IPs**.

For eligible protected resources, the service analyzes traffic directed at the public IP, learns normal traffic patterns, and detects anomalies. When an attack exceeds protection thresholds, the platform triggers mitigation to scrub attack traffic; traffic assessed as legitimate continues to the application within service capacity.

### High-Level Flow

~~~mermaid
flowchart LR
    U["Legitimate users"]
    B["Attack traffic sources"]
    A["Azure edge network"]
    D{"L3/L4 DDoS detection\nand mitigation"}
    W["Workload public IP"]
    G["Load Balancer / Application Gateway / VM"]
    APP["Application and backend"]
    M["Azure Monitor\nMetrics, alerts, logs"]

    U --> A
    B --> A
    A --> D
    D -->|"Legitimate traffic forwarded"| W
    D -->|"Traffic identified as attack"| X["Filtered / mitigated"]
    W --> G --> APP
    D -.-> M
~~~

This is a conceptual architecture diagram, not an exact map of transmission links or internal Microsoft components. Actual mitigation is managed by the service and can vary by attack type, resource, configuration, and SKU.

### Key Characteristics to Understand

- **Tuned to protected public IPs:** traffic baselines and detection thresholds apply to supported resources; do not assume every resource in a subscription shares identical coverage.
- **Automatic upon detection:** no need for an admin to manually sign in and enable scrubbing for each attack—though the protection service must be configured beforehand.
- **Monitoring and notifications:** eligible plans/configurations emit metrics, attack notifications, and mitigation reports/flow logs for SOC incident triage.
- **Azure ecosystem integration:** works alongside Azure Monitor, alerts, and incident workflows.
- **Scope boundaries:** L3/L4 protection does not replace application security, backend resilience, multi-region design, or access control.

### Relationship to Private IPs Inside a VNet

If an application uses only **private IPs** and receives no direct inbound flows through a covered public IP, do not conclude you need DDoS Network Protection merely because servers live in a VNet. Identify the **actual Internet ingress path**: it might be the public IP of an Application Gateway or Load Balancer, another managed edge service, or there may be no public endpoint at all.

## 4. Protection Options and Scope

When architecting on Azure, distinguish three frequently referenced concepts:

1. **Azure infrastructure-level DDoS protection:** the baseline protection provided automatically across Azure infrastructure without creating a separate DDoS protection plan.
2. **Azure DDoS Network Protection:** a **VNet**-scoped management option using a DDoS protection plan; covers supported public IPs associated with resources inside linked VNets.
3. **Azure DDoS IP Protection:** an option enabling dedicated protection per supported **public IP** when applied to individual addresses.

SKU names, detailed features, compatibility scopes, and terms may be updated by Microsoft over time. Before production deployment, verify current tier specifications and pricing for your target region and subscription.

| Criterion | Default Infrastructure Protection | DDoS Network Protection | DDoS IP Protection |
| --- | --- | --- | --- |
| Management scope | Shared Azure infrastructure protection | Supported public IPs within plan-linked VNets | Individual supported public IPs with the feature enabled |
| Customer configuration | No separate plan created | Create a DDoS protection plan and link VNets | Configured directly on the corresponding public IP resource |
| Best fit | Baseline default coverage | Many public IPs/VNets, large-scale network topologies | One or a few standalone public IPs needing dedicated protection |
| Telemetry/included capabilities | Do not assume full dedicated telemetry | Includes monitoring and support per plan terms | Includes corresponding capabilities per tier terms |
| Additional cost | No dedicated DDoS Protection fee | Per current Network Protection pricing | Per current IP Protection pricing |

**Do not select a tier solely by IP count while ignoring resource characteristics.** Verify whether each public IP is eligible for that protection tier, whether ingress actually traverses that address, and whether included monitoring/support meets operational needs.

### Relationship Between DDoS Network Protection, VNet, and Public IP

A DDoS protection plan is a **dedicated Azure resource** used to enable DDoS Network Protection across eligible VNets. Once a VNet links to the plan, **public IPs of supported resources inside that VNet** fall under the plan's protection scope.

That **does not mean** every private IP in the VNet becomes a public endpoint. Nor does it mean every global PaaS public FQDN belongs to that same plan.

Examples:

- An Application Gateway with a frontend public IP in a VNet serving an app can fall within Network Protection's eligible scope.
- A VM with a supported public IP in that VNet can be covered.
- A global Azure Front Door endpoint is a Microsoft-managed edge service with its own architecture; you do not "attach" DDoS Network Protection to Front Door by linking an arbitrary VNet.

### When Is Network Protection Useful?

A company operates three VNets across Dev, Staging, and Prod containing many public IPs serving critical services. The network team wants VNet-level protection management, centralized telemetry, and uniform operational runbooks. This is a strong scenario for evaluating DDoS Network Protection.

### When Is IP Protection Useful?

A small application has only one directly exposed, supported public IP and does not need a multi-VNet governance plan. In that case, DDoS IP Protection can be evaluated per IP address. Verify the public IP SKU, region, resource type, and included features at deployment time.

## 5. Combining DDoS Protection with Other Security Layers

Azure security components serve distinct objectives:

| Mechanism | Primary Role | What It Does Not Solve Alone |
| --- | --- | --- |
| **Azure DDoS Protection** | Detects and mitigates L3/L4 floods targeting supported public IPs | App vulnerabilities, auth abuse, targeted HTTP floods |
| **Network Security Group (NSG)** | Allows/denies network flows by IP, port, protocol, and direction | Does not replace large-scale DDoS scrubbing |
| **Azure Firewall** | Enforces, logs, and applies network flow policies per SKU capabilities | Does not replace DDoS mitigation services or WAF across all flows |
| **Web Application Firewall (WAF)** | Filters HTTP/HTTPS threats, app rules, and certain traffic rate controls | Not a scrubbing layer for all L3/L4 volumetric floods |
| **Azure Front Door** | Global entry point, routing/caching, and edge protection features per tier | Does not secure an origin that remains directly reachable |
| **Azure Monitor / Log Analytics** | Observes metrics, logs, alerts, and investigations | Not an active traffic filtering mechanism itself |
| **Autoscale / caching / redundancy** | Increases capacity and reduces bottlenecks | Does not block attack traffic and can amplify costs |

### Defense-in-Depth Example for an E-Commerce Application

~~~mermaid
flowchart TD
    INTERNET["Clients on Internet"]
    EDGE["Entry point: appropriate public IP / gateway / edge"]
    DDOS["L3/L4 DDoS mitigation\non protected public IP"]
    WAF["WAF / HTTP rules\nrate limiting, managed rules"]
    APP["App tier / API"]
    DB["Database over private network"]
    OBS["Azure Monitor\nalerts and incident process"]
    INTERNET --> EDGE
    EDGE -.-> DDOS
    EDGE --> WAF --> APP --> DB
    DDOS -.-> OBS
    WAF -.-> OBS
    APP -.-> OBS
~~~

This is a functional model. When an application uses Azure Front Door as its entry point, edge protections must be configured within Front Door's capabilities; do not assume all boxes in the diagram are separate resources you can chain arbitrarily.

**Design principle:** identify the entry point first, then pair DDoS/WAF controls with the **actual resource**. If direct public access to the origin is left open, attackers can hit the origin directly and bypass the edge WAF.

## 6. Surveying Protection Scope Before Enabling the Service

Suppose a system consists of:

- Subscription `prod-subscription`.
- VNet `vnet-web-prod`, subnet `snet-appgw` containing an Application Gateway.
- Public IP `pip-appgw-prod` acting as the frontend for Internet access.
- APIs running in a private subnet and a database using a Private Endpoint.
- Several other services serving users through Azure Front Door.

Do not turn on protection broadly without first mapping ingress paths.

### Sample Assessment Table

| Component | Internet Ingress? | Public IP in VNet? | Protection Evaluation Direction |
| --- | --- | --- | --- |
| Application Gateway `pip-appgw-prod` | Yes | Yes, if frontend is configured as described | DDoS Network/IP Protection per support + WAF |
| Private-IP API VM | Not directly | No | Protect upstream ingress, NSGs, and app layer |
| Azure SQL via Private Endpoint | Not directly via private endpoint | Not a VM public IP | Private networking, auth, and monitoring |
| Azure Front Door endpoint | Yes | Not a public IP inside the app VNet | Use Front Door edge protection + WAF |
| Dedicated public IP for supported network service | Yes | Depends on deployment | Verify Network/IP Protection support |

**Questions to answer before creating a DDoS plan:**

1. Which public IPs receive Internet traffic, and which subscription, region, and resource do they belong to?
2. Which VNet is each public IP attached to, and does it use Standard SKU or other mandatory prerequisites for the protection tier?
3. What flows traverse each public IP, and which protocols/ports must remain served?
4. How many VNets exist, and how many IPs genuinely require dedicated protection?
5. Who owns the budget, alert operations, incident response, and configuration RBAC?
6. Are there L7 components needing WAF, application rules, or caching?

This inventory provides the basis for a sound architectural choice rather than enabling services by name alone.

## 7. Enabling Azure DDoS Network Protection for a VNet

This section shows an **illustrative configuration workflow** and does not require you to provision billable resources. CLI syntax and flags can vary by version; use a supported Azure CLI release and check command help in your environment.

### 7.1. Preparation

You need:

- An authorized Azure subscription for practice.
- An existing resource group for security governance, such as `rg-security-prod`.
- A VNet containing public IP resources needing protection, such as `vnet-web-prod` in `rg-network-prod`.
- Appropriate Azure RBAC permissions to manage DDoS protection plans and update target VNets.
- Cost/budget review and change approval if working in a real environment.

Check CLI context:

~~~bash
az login
az account show \
  --query "{subscription:name, subscriptionId:id, tenantId:tenantId}" \
  --output json

# Select the subscription once you are certain of the target Subscription ID.
az account set --subscription "<SUBSCRIPTION_ID>"
~~~

Verify the VNet exists:

~~~bash
az network vnet show \
  --resource-group rg-network-prod \
  --name vnet-web-prod \
  --query "{id:id, name:name, location:location}" \
  --output json
~~~

If the VNet does not exist, stop and verify scope. **Never create a new VNet just to mask selecting the wrong subscription.**

### 7.2. Create the DDoS Protection Plan

Illustrative command:

~~~bash
az network ddos-protection create \
  --resource-group rg-security-prod \
  --name ddos-plan-prod

# Retrieve the plan's Resource ID rather than concatenating strings manually.
PLAN_ID=$(az network ddos-protection show \
  --resource-group rg-security-prod \
  --name ddos-plan-prod \
  --query id \
  --output tsv)

echo "$PLAN_ID"
~~~

`az network ddos-protection create` creates a **billable plan resource**. Run it only with proper authorization and budget approval. A plan does not protect a VNet simply by existing; you must link it under Network Protection.

### 7.3. Link the DDoS Protection Plan to the VNet

~~~bash
az network vnet update \
  --resource-group rg-network-prod \
  --name vnet-web-prod \
  --ddos-protection true \
  --ddos-protection-plan "$PLAN_ID"
~~~

Once completed, the VNet is configured to use the DDoS plan for supported resources. If you encounter errors involving permissions, region, subscription, or an invalid plan, diagnose the root cause before retrying; never grant subscription-wide Owner as a default workaround.

### 7.4. Verify Configuration

~~~bash
az network vnet show \
  --resource-group rg-network-prod \
  --name vnet-web-prod \
  --query "{name:name, ddosEnabled:enableDdosProtection, planId:ddosProtectionPlan.id}" \
  --output json
~~~

Expect `ddosEnabled` to be `true` and `planId` to point to the newly created protection plan.

You can also verify in **Azure portal → Virtual networks → [VNet] → DDoS protection** or the corresponding blade in the current UI.

**Verifying configuration does not verify live mitigation:** seeing a linked plan confirms only configuration state; telemetry and approved validation procedures are needed to assess operational readiness.

### 7.5. Choosing IP Protection Instead of Network Protection

With **DDoS IP Protection**, configuration focuses on each supported **public IP resource**. In the Azure portal, locate the DDoS protection setting on the public IP and select the appropriate option. Do not use VNet-level plan commands for Network Protection to infer that an out-of-scope public IP has IP Protection enabled.

After configuring, inspect the **public IP** itself on the target resource and verify live Internet traffic flows. Below is a command to read the public IP's full properties:

~~~bash
az network public-ip show \
  --resource-group rg-network-prod \
  --name pip-appgw-prod \
  --output json
~~~

Check the SKU, address, DDoS settings (if exposed by the resource/API version schema), and association with the frontend of the service actually receiving traffic. Different API versions may represent DDoS fields differently; never infer protection status solely from the public IP's name.

### 7.6. Never Delete a Plan Serving Live Workloads

If one plan covers multiple VNets, inspect every linked VNet before modifying or deleting the plan. Disabling protection on a production VNet alters its defense posture and service coverage.

In an authorized lab cleanup, unlink the VNets per product documentation, confirm zero remaining dependencies, and only then delete the plan. Check post-lab charges in Cost Management. Never run bulk delete scripts in a subscription without tight scoping.

## 8. Monitoring Attacks with Azure Monitor

Protection is operationally effective when the team can answer: **is an attack occurring, when did it start, how much traffic was dropped, are customers impacted, and has the system recovered?**

### 8.1. Useful Signal Groups

For eligible public IPs and plans, common telemetry groups include:

| Signal Group | Answers | Notes |
| --- | --- | --- |
| **DDoS attack status** | Is the public IP currently flagged as under attack? | Depends on whether the metric is emitted for that resource |
| **Inbound traffic / packet metrics** | When did inbound bandwidth and packet rate spike? | Compare against baseline and app timestamps |
| **Forwarded/dropped traffic during mitigation** | How many packets/bytes were forwarded vs. scrubbed? | Do not equate "dropped" with app failure |
| **DDoS protection notifications** | When did mitigation start and stop notifications fire? | Usually requires configuring diagnostic settings |
| **Mitigation reports** | Summary of attack vectors and mitigation actions | Depends on supported log/tier types |
| **Mitigation flow logs** | Detailed flow records captured during mitigation | Account for log volume and access control |
| **Application and gateway** | What are latency, HTTP 5xx, saturation, and success rate? | Must correlate to gauge real user impact |

In the Azure portal, inspect related metrics on the public IP or Monitor blades. Exact metric names, dimensions, and availability vary by resource and tier, so always select from the live metric picker rather than hardcoding names in dashboards.

### 8.2. Configure Diagnostic Settings

On a protected public IP of a supported service type:

1. Open **Diagnostic settings** on the source resource or the appropriate DDoS monitoring configuration.
2. Select available DDoS log categories—such as **DDoSProtectionNotifications**, **DDoSMitigationReports**, and **DDoSMitigationFlowLogs**—when present.
3. Choose an organization-approved destination such as a **Log Analytics workspace**, storage account, or Event Hubs per feature support.
4. Verify logs arrive after an actual qualifying event; having no mitigation logs when no attack has occurred is normal.
5. Configure retention, access permissions, and cost controls per investigation needs.

Log categories may land in different tables/schemas depending on pipeline mode. A starter KQL query in a workspace using the `AzureDiagnostics` table might look like:

~~~kusto
AzureDiagnostics
| where TimeGenerated >= ago(7d)
| where Category in (
    "DDoSProtectionNotifications",
    "DDoSMitigationReports",
    "DDoSMitigationFlowLogs"
  )
| project TimeGenerated, ResourceId, Category
| order by TimeGenerated desc
~~~

This query **only works when data is ingested into `AzureDiagnostics` under that schema**. If the workspace uses resource-specific tables or has no events yet, inspect the workspace table list, connectors, diagnostic settings, and current schema docs. Never try to generate test logs by launching unauthorized attack traffic.

### 8.3. Create Alerts for On-Call Operations

A sample alert workflow:

- **Trigger:** the public IP reports an active DDoS attack status, or a mitigation notification arrives, depending on supported metrics/logs.
- **Additional context:** assess severity and customer impact via application metrics.
- **Action:** Azure Monitor Action Group notifies SOC/NOC or the incident system.
- **Correlation:** attach the public IP, VNet, subscription, application endpoint, and UTC timestamp.
- **Alert closure:** record attack end time, application recovery, and actions taken.

Design example:

~~~text
Signal:     Metric "Under DDoS attack or not" (if available)
Scope:      pip-appgw-prod
Condition:  Status indicates attack detected
Action:     Notify SOC/NOC team
Context:    Subscription, public IP, VNet, application, UTC
Next:       Check 5xx, latency, throughput, and user impact
~~~

This is a **logical template**, not an executable API/ARM command. When creating a metric alert, select the **actual metric and condition expression** in Azure Monitor scoped to the public IP.

### 8.4. Why DDoS Metrics Alone Are Not Enough to Assess an Incident

Scenario A: DDoS mitigation is active, most malicious traffic is dropped, and the HTTP success rate stays steady. From the user's perspective, the service may remain healthy.

Scenario B: No clear DDoS metric fires, yet the API times out because the backend database is overloaded. The cause may be an application bug, legitimate traffic surge, or an L7 flood; adding L3/L4 protection will not fix the backend.

Accurate conclusions require **both DDoS telemetry and application SLIs/SLOs**: request success rate, p95/p99 latency, timeouts, CPU, connection saturation, and database load.

## 9. Incident Response Workflow for a DDoS Event

Suppose at 14:05 UTC, the metric on public IP `pip-appgw-prod` switches to under-attack status and customers report timeouts.

### Step 1 — Triage and Confirm Scope

- Record start time, public IP, application, VNet, subscription, protection tier, and on-call responder.
- Verify the alert comes from genuine DDoS telemetry rather than an unrelated CPU/network threshold.
- Inspect gateway/VM/application logs to check whether legitimate users are affected.
- Correlate recent infrastructure changes around the same timestamp.

### Step 2 — Build a Timeline

| Assumed UTC Time | Observation | Hypothesis to Verify |
| --- | --- | --- |
| 14:00 | Normal request success rate | Application baseline |
| 14:05 | Sharp spike in inbound traffic to public IP | Possible DDoS or legitimate traffic event |
| 14:06 | DDoS metric/notification indicates mitigation | Platform is classifying and scrubbing traffic |
| 14:07 | Portion of packets dropped, latency increases | Correlate legitimate volume vs. backend capacity |
| 14:20 | Traffic subsides, error rate returns to normal | Potential recovery; watch for recurrence |

This timeline is illustrative only. Never assign definitive root causes to timestamps without supporting records.

### Step 3 — Monitor Mitigation Effectiveness

Correlate traffic before, during, and after mitigation:

- Graphs of inbound traffic, forwarded/dropped traffic, and attack status.
- Whether the application continues processing legitimate requests.
- Whether L7 attack patterns appear in WAF/application logs.
- Whether multiple public IPs or regions are affected.
- Customer impact severity and differences across routes or geographies.

### Step 4 — Coordinate Across Teams

- **NOC/network team:** verify ingress, routing, NSGs, firewalls, and telemetry sources.
- **SOC/security team:** examine attack vectors, severity, evidence, and related activity.
- **App/SRE team:** track SLOs, scale resources, check autoscale, caching, and app health.
- **Incident commander:** document impact, manage communications, and approve emergency changes if needed.

Under eligible plans and support terms, enterprises can engage Microsoft DDoS response/support channels per contracted entitlements and procedures. Never assume every tier includes identical dedicated response support.

### Step 5 — Take Evidence-Based Actions

Actions to consider:

- Keep DDoS Protection configuration intact while the service is actively mitigating, and monitor state.
- Tune WAF/rate limiting for HTTP/HTTPS when L7 evidence exists and false positives are assessed.
- Increase application capacity or shed expensive backend queries if needed, without relying blindly on autoscale alone.
- Lock down unintended direct paths to the origin while ensuring legitimate traffic continues flowing.
- Follow approved change processes for firewall/route updates to avoid broadly blocking real users.

**Never arbitrarily swap public IPs, delete gateways, or disable all Internet access in the middle of an attack.** Such actions can cause wider outages and destroy telemetry continuity.

### Step 6 — Recover and Conduct a Post-Incident Review

Once traffic and SLOs stabilize, document:

1. Detection time, mitigation start/end times, and service recovery time.
2. Public IPs, telemetry sources, dashboards, alerts, and related logs.
3. Business impact, traffic characteristics, and how each defense layer responded.
4. Actions taken, approvers, configuration changes, and outcomes.
5. Observability gaps, permission gaps, and recommended improvements.

Do not close an incident merely because the "under attack" metric drops back to 0 if the application still misses its SLOs.

## 10. Verifying Protection Effectiveness Safely

DDoS testing differs from standard application load testing. **Never generate flood traffic against a public IP yourself** just to see whether the platform blocks it. Doing so can cause outages or violate acceptable use policies.

### Verification Objectives

A practical verification plan should confirm:

- The right public IPs, VNets, and SKUs are covered in protection scope.
- Azure Monitor and Action Groups deliver signals as designed.
- SOC/NOC knows how to open dashboards, file tickets, and coordinate.
- The application has independent SLIs/SLOs and recovery checks alongside DDoS metrics.
- Runbooks clearly identify who approves WAF, firewall, routing, or scaling changes.
- Uncovered components are identified with their own defense plans.

### Non-Intrusive Testing Without Attack Traffic

Can be performed even in a lab environment:

1. **Configuration audit** via Azure portal/CLI, listing every public IP actually covered.
2. **Observability check:** confirm metrics exist at the right scope and diagnostic settings have valid destinations and permissions.
3. **Notification path test:** use Action Group test features or trigger a simulated non-load alert from an approved test source.
4. **Tabletop exercise:** responders walk through a hypothetical scenario and trace actions step-by-step from the runbook.
5. **Application resilience check:** run bounded, legitimate load tests separately within approved limits.

If live DDoS mitigation simulation is genuinely required, use only **procedures, simulation partners, and testing methods supported by Microsoft and approved by the service owner**, inside a coordinated test window. Never assume arbitrary load-testing tools can simulate DDoS or validate mitigation capacity.

### Post-Exercise Evaluation Criteria

| Criterion | Evaluation Question |
| --- | --- |
| Inventory accuracy | Were any public IPs or entry points missed in scope? |
| Detection | Did metrics/logs capture the expected events? |
| Notification | Did the right on-call team receive alerts with enough context? |
| Investigation | Could the team distinguish DDoS, HTTP flood, and backend faults? |
| Response | Who is authorized to apply changes, recover, and communicate? |
| Impact | Was legitimate user recovery measurably verified? |
| Cost | Can protection and supporting component costs be estimated accurately? |

## 11. Organizing Access Control and Costs

### 11.1. Least-Privilege Permissions

Viewing metrics, creating alerts, modifying DDoS plans, and updating VNets or public IPs may require **different Azure RBAC permissions**.

Recommended operational model:

| Team | Need | Suggested Scope |
| --- | --- | --- |
| Security/SOC | View alerts, logs, and assist investigations | Read/monitoring access on relevant resources and workspaces |
| Network team | Manage VNets, public IPs, DDoS plans | Network and protection plan permissions in approved scopes |
| Application/SRE | Track SLOs, handle app faults, and coordinate | App/monitoring permissions per environment |
| Cost owner/FinOps | Review cost reports, check budgets | Appropriate Cost Management permissions |

Someone viewing DDoS charts **does not need permission to modify** network configurations. Conversely, holding Contributor on one resource group does not imply permission to link resources across another resource group or subscription without access at that scope.

### 11.2. Cost Components to Account For

- **DDoS Network Protection:** plan pricing model and any additional charges per current terms.
- **DDoS IP Protection:** per-protected-public-IP pricing model and service terms.
- **Log Analytics/Azure Monitor:** ingestion, retention, queries, and alert rules per configuration.
- **Application Gateway/WAF/Front Door:** billed separately under each product's pricing model.
- **Traffic, app capacity, and redundancy:** autoscale, networking, compute, and storage costs can surge during incidents.

Certain cost-protection credits or dedicated response entitlements during a DDoS attack may be tied to specific tiers and conditions. **Never assume all damages or cost spikes are automatically reimbursed.** Review contracts, eligibility criteria, claim processes, and required incident documentation.

To estimate costs:

1. Inventory all eligible public IPs and VNets needing protection.
2. Select Network or IP Protection based on requirements and capabilities.
3. Check the **Azure Pricing Calculator** and terms for target regions.
4. Add WAF/Front Door, monitoring, and operational costs.
5. Set budgets and alerts in **Microsoft Cost Management**.
6. Track spend changes after enabling protection and when adding new public IPs.

### 11.3. Risks of Misconfiguration

| Mistake | Consequence |
| --- | --- |
| Enabling Network Protection on a VNet that holds no target Internet ingress | Cost and posture may not protect the intended system |
| Assuming one DDoS plan protects every PaaS endpoint automatically | Leaves real entry points uncovered or misapplied |
| Enabling L3/L4 DDoS alone while skipping WAF/app rate controls | Leaves HTTP/HTTPS abuse vectors unprotected |
| Failing to check whether backends are publicly exposed | Traffic can bypass the intended edge layer |
| Having no alerts or on-call contacts | Poor coordination even when automatic mitigation triggers |
| Making broad firewall changes in panic | Accidentally blocks legitimate customers |
| Ignoring plan fees and telemetry ingestion costs | Unbudgeted spend |
| Deleting a plan/link shared across multiple VNets | Unintentionally removes protection from other workloads |

## 12. Architecture Analysis Hands-On Exercise

**Simulated scenario:** An enterprise runs a commercial API system on Azure:

- `vnet-prod`: contains an Application Gateway with public IP `pip-appgw-prod`.
- Backend APIs use private IPs in a dedicated subnet.
- Azure SQL uses a Private Endpoint, with no public access by design.
- Front Door serves static content and routes part of user traffic to the application.
- The admin team wants to reduce DDoS risk and track user impact.

### Part A — Identify Ingress Paths and Protection Mechanisms

Complete the preliminary plan:

| Target | Internet Ingress? | Public IP in VNet? | Priority Defense |
| --- | --- | --- | --- |
| `pip-appgw-prod` | Yes | Yes, if configured | DDoS Network/IP Protection if eligible; WAF |
| Private-IP VM/API | Not directly | No | Upstream ingress protection, NSGs, auth, and SLOs |
| SQL via Private Endpoint | Not directly | No | Private network access, auth, and monitoring |
| Front Door endpoint | Yes | Not a VNet public IP | Front Door edge protection and WAF per config |

Explain why **linking a DDoS plan to `vnet-prod` does not automatically turn a Front Door endpoint into a VNet-owned public IP**.

### Part B — Inspect Configuration and Build a Plan

With read permissions, learners run:

~~~bash
az account show \
  --query "{subscription:name, id:id}" \
  --output json

az network vnet show \
  --resource-group rg-network-prod \
  --name vnet-prod \
  --query "{name:name, enabled:enableDdosProtection, plan:ddosProtectionPlan.id}" \
  --output json

az network public-ip show \
  --resource-group rg-network-prod \
  --name pip-appgw-prod \
  --output json
~~~

Names are examples; replace them with real names in an authorized lab. If resources do not exist, **do not create resources outside the exercise scope**; use the simulated output below to reason through the questions:

~~~json
{
  "vnet": "vnet-prod",
  "enableDdosProtection": true,
  "ddosProtectionPlan": {
    "id": "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-security-prod/providers/Microsoft.Network/ddosProtectionPlans/ddos-plan-prod"
  },
  "publicIp": "pip-appgw-prod",
  "publicIpSku": "Standard",
  "ingress": "Application Gateway"
}
~~~

**Questions:**

1. Which fields show that the VNet has Network Protection configured?
2. Why is it still necessary to verify which public IP the Application Gateway actually uses?
3. Does a private-IP VM in `vnet-prod` automatically receive a public IP?
4. Under which protection scopes should Front Door and the private SQL endpoint be evaluated?

**Hint:** `enableDdosProtection=true` and the plan ID prove VNet configuration, yet they do not prove all system traffic passes through that protected public IP.

### Part C — Investigate a Simulated Telemetry Table

The team observes these figures during a simulated event:

| Timestamp (UTC) | Inbound Traffic to Public IP | DDoS Status | HTTP 5xx | p95 Latency |
| --- | --- | --- | --- | --- |
| 09:00 | Normal | No | 0.2% | 180 ms |
| 09:05 | Sharp spike | Yes | 1.0% | 300 ms |
| 09:10 | High, mitigation active | Yes | 1.5% | 420 ms |
| 09:20 | Back near baseline | No | 0.3% | 190 ms |

From the table above:

1. What signals does the team have regarding DDoS and potential customer impact?
2. Can you confirm all anomalous traffic was successfully blocked?
3. Which metrics or logs should be added to evaluate mitigation effectiveness?
4. If HTTP 5xx keeps rising after 09:20 even though attack status returns to 0, what is the next investigation step?

**Reference answers:**

- DDoS status coincides in time with higher error rates and latency; verify correlation using raw logs.
- Not yet. You need forwarded/dropped telemetry, mitigation reports, and application telemetry to judge scrubbing quality.
- Gather DDoS logs, traffic volume, dropped/forwarded packet counts, WAF/application/gateway logs, and request success rates.
- Investigate app/backend health, DB connections, saturation, and recent system changes; never assume all remaining errors are caused by DDoS.

### Part D — Draft a 5-Step Runbook

Write a concise runbook for when **a production public IP reports an active DDoS attack**:

1. Confirm the affected resource and start timestamp.
2. Check DDoS status alongside application SLIs/SLOs.
3. Check for L7 attack indicators and backend overload.
4. Notify the appropriate teams and approve any necessary changes.
5. Confirm recovery, archive the timeline, and document lessons learned.

This exercise focuses on **observation and decision-making** without generating real DDoS traffic.

## 13. Self-Check Questions

**Question 1.** Can Azure DDoS Protection replace a WAF when an application is flooded with massive volumes of syntactically valid HTTP requests?

**Answer:** No. DDoS Protection focuses on L3/L4 mitigation; L7 defense requires WAF/rate limiting and resilient application design depending on behavior.

**Question 2.** A company enabled DDoS Network Protection on `vnet-prod`. Is a website running entirely behind Front Door automatically covered by that VNet's plan?

**Answer:** You cannot conclude that. Front Door is an edge service with its own protection model; verify actual ingress and origin exposure.

**Question 3.** What is the main difference between Network Protection and IP Protection?

**Answer:** Network Protection governs protection at the VNet level via a protection plan covering eligible public IPs; IP Protection is configured per individual eligible public IP. Actual features and fees must be verified against current plans.

**Question 4.** A public IP is protected, yet the application still returns HTTP 503 because the database is overloaded. Does that mean DDoS Protection failed?

**Answer:** Not necessarily. Inspect DDoS metrics alongside application metrics; 503 errors can stem from application-tier issues or backend resource exhaustion rather than L3/L4 scrubbing.

**Question 5.** Why enable diagnostic settings and alerts before an attack happens?

**Answer:** So the team receives timely signals and forensic data when an event hits. Setting up logs and alerts only after an incident begins misses data that was never recorded beforehand.

**Question 6.** Should you use Internet flood-generation tools to test a production public IP?

**Answer:** No. Test only through provider-supported mechanisms with proper approvals, coordination, and impact controls.

**Question 7.** Why review costs before creating a protection plan?

**Answer:** Protection tiers carry dedicated pricing alongside monitoring and application infrastructure costs. Deployment plans must accurately scope eligible resources and coverage needs.

## Takeaways

- **DDoS** threatens availability; attacks may target L3/L4, L7, or combine multiple vectors.
- **Azure DDoS Protection** focuses on L3/L4 defense for **supported Azure public IPs**; it does not replace WAF, NSGs, firewalls, or resilient application design.
- **Network Protection** attaches to VNets via a protection plan; **IP Protection** targets individual eligible public IPs. Always map real Internet ingress accurately.
- Monitor **attack status, mitigation metrics/logs, and application SLOs** together to assess real impact.
- Prepare **alerts, RBAC permissions, runbooks, and cost estimates** before an incident; test only through authorized, approved channels.
- During an attack, prioritize keeping the service running, coordinate evidence-based changes, and conduct a post-incident review after recovery.
