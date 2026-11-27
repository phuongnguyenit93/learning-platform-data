# Shared Accounts for Security, Connectivity, and Logging

As a cloud environment grows from a single application into multiple environments, teams, and products, placing all resources in one account becomes hard to control. One team needs to deploy applications; another must investigate incidents; security needs to inspect access trails; the platform team must manage Internet connectivity, internal networking, and links to on-premises systems. When all permissions and resources are mixed together, a misconfiguration or compromised account can impact many workloads at once.

A common pattern in a **cloud landing zone** is creating shared accounts or governance units (*shared accounts*) for cross-cutting capabilities: **security**, **network connectivity**, and **centralized log archiving**. Workloads retain their own accounts and remain accountable for their applications, while consuming platform services through published interfaces and policies.

In this lesson, the term **account** refers to a cloud resource governance boundary, not "a shared login username." On AWS this may be an account; on Azure it is typically a subscription within a management group and tenant hierarchy; on Google Cloud it is typically a project inside an organization/folder. These models share similarities in access control, but are **not strictly equivalent in service limits, security boundaries, and billing**.

This lesson sits in the **Resource Organization** section of the cloud architecture design module: turning business requirements into networking, compute, data, and deployment choices, and balancing reliability, security, scalability, cost, and operations under Well-Architected principles.

After this lesson, you can:

- Explain the roles and scopes of **Security**, **Network/Connectivity**, and **Log Archive** accounts.
- Distinguish between organization management accounts, shared platform service accounts, and workload accounts.
- Sketch connectivity flows, logging pipelines, and cross-account access workflows.
- Design least-privilege boundaries that reduce the ability to alter or delete investigative logs.
- Identify shared points of failure, cost drivers, complexity, and how to validate each decision.
- Evaluate a landing zone design using Well-Architected questions and practical tests.

## 1. Why Organize Resources Across Multiple Accounts?

A cloud account holds resources, access policies, quotas, and specific governance settings. Placing production, development, security tooling, and logging systems inside the same account can cause:

- **Large blast radius:** accidentally modifying a route, policy, key, or quota can impact unrelated services.
- **Coarse permissions:** administering one component may grant users broader permissions than their job requires.
- **Weak separation of duties:** application operators might also be able to alter auditing mechanisms or delete forensic trails.
- **Opaque costs:** hard to separate workload budgets from shared platform spend.
- **Inconsistent controls:** newly created resources may lack logging, security policies, and standard network configurations.

The goal of a **multi-account organization** is to establish clear governance and accountability boundaries. In a sound architecture, a compromised production workload **does not automatically have permission** to disable organization-wide auditing or modify archived logs. The networking team can modify assigned connectivity, without thereby gaining permission to read application data.

Separating accounts **does not automatically guarantee absolute isolation**. Organization-level admin rights, cross-account trust relationships, encryption keys, shared networks, policy configurations, and identity provisioning still must be designed and tested.

### Comparing Three Organization Models

| Model | Pros | Limitations and considerations |
| --- | --- | --- |
| **One account for everything** | Fast initialization, minimal governance steps | Hard to contain blast radius, permissions, and costs as scale grows |
| **Separate workload accounts, shared services grouped into one platform account** | Basic workload separation, fewer platform accounts | SecOps, networking, and logging can still affect one another or share overly broad permissions |
| **Dedicated accounts for security, connectivity, and log archiving** | Separates duties and permissions; easier to standardize shared services | Requires designing cross-account permissions, connectivity, deployment, monitoring, and coordination |

There is no "standard" account count for every business. An experimental app may not need all platform accounts yet, whereas a production system processing sensitive data typically needs security controls and audit trails isolated from application-team permissions.

## 2. Reference Diagram: A Cloud Organization with Shared Accounts

Consider an enterprise running a booking app, an admin portal, and a reporting service. It can be organized as follows:

~~~mermaid
flowchart TB
    ORG["Organization / Management hierarchy<br/>Org governance, guardrails, billing"]
    ID["Identity provider / SSO<br/>Individual identities, MFA, permission groups"]
    ORG --> SEC["Security account<br/>Risk detection, security monitoring"]
    ORG --> NET["Network account<br/>Hub, DNS, shared connectivity"]
    ORG --> LOG["Log Archive account<br/>Ingest and preserve audit logs"]
    ORG --> P1["Workload: Booking Prod"]
    ORG --> P2["Workload: Admin Prod"]
    ORG --> NP["Workload: Nonprod"]
    ID -. "Issue least-privilege sessions and roles" .-> SEC
    ID -. "Issue least-privilege sessions and roles" .-> NET
    ID -. "Issue least-privilege sessions and roles" .-> LOG
    ID -. "Issue least-privilege sessions and roles" .-> P1
    ID -. "Issue least-privilege sessions and roles" .-> P2
    ID -. "Issue least-privilege sessions and roles" .-> NP
    P1 -. "Telemetry and audit" .-> LOG
    P2 -. "Telemetry and audit" .-> LOG
    NP -. "Telemetry and audit" .-> LOG
    SEC -. "Scoped read/investigation" .-> LOG
    P1 -. "Connect via allowed routes" .-> NET
    P2 -. "Connect via allowed routes" .-> NET
    NP -. "Connect via allowed routes" .-> NET
~~~

The diagram illustrates **logical relationships**; it does not imply every application packet must traverse the Network account or that every log type always takes a network hop into Log Archive. Cloud services may provide provider-managed log delivery paths; internal read/write traffic within the same workload can stay on local routes.

### Roles to Distinguish

| Account group | Primary function | Who typically administers? | What should not be granted by default |
| --- | --- | --- | --- |
| Organization / Management | Manage organization, accounts, baseline policies, billing, or service enrollments | Very restricted platform group | Day-to-day app operations or querying customer data |
| Security | Monitor posture, vulnerabilities, threat findings, investigations, and response coordination | SecOps, cloud security | Modifying app business logic or arbitrarily deleting archive logs |
| Network / Connectivity | Inter-workload connectivity, DNS, hybrid links, egress, and shared network resources | Platform/network team | Reading secrets, database records, or sensitive logs unrelated to network ops |
| Log Archive | Receive and preserve logs under retention/audit policies | Platform logging with restricted rights; monitored retention controls | Granting workloads permission to delete stored logs |
| Workload Prod | Production compute, databases, queues, storage, and app configuration | Product teams and SREs within scope | Editing org policies, deleting centralized audit logs |
| Workload Nonprod | Dev/test/staging or other experimental environments | Development teams within scope | Accessing live data or default production permissions |

In some organizations, **Security Tooling** and **Log Archive** are two separate accounts so detection/investigation teams do not implicitly hold full control over raw log data. In smaller organizations, both functions may share an account, provided roles, keys, and policies remain separated. Separation should match real risk and operational capacity.

## 3. Shared Security Account: Organization-Wide Monitoring and Response

The Security account is where shared security capabilities are deployed or coordinated. The objective is **cross-workload visibility** without granting broad admin access to every SecOps engineer inside every product account.

### 3.1. Commonly Centralized Capabilities

- **Security posture:** aggregates findings on misconfigurations, non-compliant policies, public resources, and problematic keys or certificates.
- **Threat detection:** alerts on anomalous behavior across identity, network, or supported service activity.
- **Vulnerability management:** consolidates vulnerabilities in images, workloads, VMs, libraries, or configurations based on the tools used.
- **Security findings and workflows:** triages, assigns owners, prioritizes, tracks remediation, and links supporting evidence.
- **Incident response:** procedural emergency access, ability to isolate malicious sources or capture forensic evidence when needed.
- **Compliance reporting:** periodic reporting on guardrails, encryption, logging, configurations, and approved exceptions.

Not every tool has to *run* inside the Security account; some services are enabled per workload account and **send findings centrally**. What matters is clear ownership and access control.

### 3.2. Separation of Duties Under Least Privilege

The design should specify:

1. **Detection/read permissions:** SecOps reads findings, configs, and investigation-relevant logs; this does not mean permission to read all customer data.
2. **Modification permissions:** certain runbooks may need to isolate an instance, enforce a blocking policy, or revoke credentials; use tightly scoped permissions per action, preferring approval gates for high-impact steps.
3. **Evidence storage and protection:** detection teams should not be able to arbitrarily edit/delete raw audit logs. Maintain chain-of-custody and retention procedures.
4. **Organization admin permissions:** keep within a tightly restricted group; never grant broadly just for integration convenience.

For example, a SecOps engineer can view Booking Prod security findings and file a remediation ticket; that engineer **does not need** permission to drop the booking database. Likewise, a compromised application account must never have permission to disable logging in other accounts.

### 3.3. Organizing Cross-Account Identities and Permissions

Use an appropriate identity provider / SSO, multi-factor authentication (MFA), short-lived roles, and job-function permission groups. Avoid sharing root, owner, or static credentials across multiple people.

Core principles:

- **Least privilege:** humans and workloads receive only the actions on resources they genuinely need.
- **Separation of duties:** app deployment teams, network admins, security auditors, and log retention admins hold distinct permission scopes.
- **Just-in-time or session-scoped access:** elevate privileges only for the duration needed, with logging and expiration.
- **Break-glass:** emergency access path that is protected, monitored, and rehearsed; never turn it into a daily driver account.
- **Guardrails:** org-level constraints preventing risky configurations where supported by the platform; a mis-scoped guardrail can disrupt production.

**Technical examples:** AWS can use AWS Organizations, IAM roles, service control policies (SCPs), and delegated administrators for supported security services; Azure uses Entra ID, management groups, Azure RBAC, and policies; Google Cloud uses organization/folder/project, IAM, and organization policies. Exact integration varies by service and region—you cannot simply "translate" role names across clouds.

### 3.4. Risks of Centralizing Security

Because the Security account holds broad visibility and permissions, **it is itself a high-value target**. Strictly control role assumptions, automation permissions, secrets, and keys, and audit all administrative actions. Even an automated playbook isolating the wrong target can cause a production outage.

A sound design validates environment, resource, finding confidence, and blast radius before triggering high-impact actions. Security automation must support halting, monitoring, and recovery.

## 4. Shared Connectivity Account: Managing Paths, Not Business Logic

The Network account centralizes **shared connectivity capabilities** across multiple workloads: network hubs, gateways, DNS services, IP management, egress, or cloud-to-office/data-center links.

### 4.1. Hub-and-Spoke Model

~~~mermaid
flowchart TD
    OFF["On-premises / partner systems"] --- VPN["VPN / dedicated private connectivity"]
    VPN --- HUB["Network hub<br/>Routing, traffic control, shared DNS"]
    HUB --- PROD["Spoke VPC/VNet: Booking Prod"]
    HUB --- ADMIN["Spoke VPC/VNet: Admin Prod"]
    HUB --- TEST["Spoke VPC/VNet: Nonprod"]
    PROD --- DB["Booking private database"]
    HUB --- EGRESS["Policy-based egress/inspection"]
    EGRESS --> INTERNET["Internet / external APIs"]
~~~

The network hub can leverage provider connectivity services such as transit gateways, virtual WAN/hubs, network connectivity centers, or Shared VPCs depending on the model. They are **not directly interchangeable services**; evaluate routes, connection limits, bandwidth, DNS, permission boundaries, and scalability.

In a hub-and-spoke approach, workloads own their dedicated networks or segments while the platform team coordinates shared connectivity. Traffic **only traverses the hub when routes and architecture require it**. Traffic from an application to a database in the same VPC/VNet can stay local. Do not force all internal communication through a central gateway without a specific control requirement.

### 4.2. Decisions to Make Up Front

| Decision | Design questions | Risk if skipped |
| --- | --- | --- |
| IP addressing | Do CIDRs overlap when connecting multiple workloads or on-premises? | Unroutable networks or complex NAT workarounds |
| Segmentation | Can Prod reach Nonprod? Over which protocols can Workload A call Workload B? | Lateral movement during a compromise |
| Routing | Which flows go direct, via hub, via firewall, or via private endpoints? | Asymmetric routing, added latency, broken connectivity |
| DNS | Who owns private zones, resolvers, and shared records? | Wrong name resolution, hard-to-debug failures |
| Egress | Where can workloads reach the Internet, and under what limits? | Data exfiltration, high NAT/egress bills |
| Ingress | Which public endpoints need WAF/CDN/LB, and where is TLS terminated? | Unnecessary attack surface exposure |
| Hybrid | Does on-premises connectivity use VPN or private circuits, and is it redundant? | A single link becomes a single point of failure |
| Observability | Are flow logs, route change logs, network metrics, alerts, and runbooks in place? | Hard to isolate faults across app, DNS, or routing |

**IPAM (IP Address Management)** is valuable as organizations grow and frequently provision new networks. Use a CIDR allocation plan, approval workflow, and appropriate automated allocation to prevent range collisions across accounts and environments.

### 4.3. Shared VPC, Hub-and-Spoke, and Network Accounts Are Not Identical Concepts

With **Google Cloud Shared VPC**, a host project owns the shared network and service projects consume subnets based on granted permissions. With **Azure**, hub-and-spoke typically places a hub VNet in a connectivity subscription and spoke VNets in workload subscriptions. With **AWS**, a network account may own central connectivity like a transit gateway while workloads own separate VPCs connected by policy. Some platforms also support sharing subnets or network resources at varying scopes.

Choose a model based on **who owns network configuration**, **product team autonomy**, **how prod/nonprod are isolated**, and **service limits**. Never assume "all services share the same subnet, routing, or IAM model" when switching providers.

### 4.4. Avoiding Central Bottlenecks and Single Points of Failure

A shared firewall, NAT gateway, DNS resolver, or VPN link can become a **single point of failure** or a cost/bandwidth bottleneck. Design redundancy across availability zones, regions, and actual routing policies; measure failover and alerting. Using a highly available managed service does not guarantee your customer-configured routes, tunnel pairs, or deployment zones are properly redundant.

Do not treat the Network account as giving the network team full access to workload databases. Permission to alter routes and inspect flow logs is distinct from permission to read transaction payloads, secrets, or source code.

## 5. Centralized Log Archive Account: Preserving Evidence and Supporting Investigations

The Log Archive account ingests and stores logs requiring long-term retention for **auditing, investigations, security obligations, and incident context reconstruction**. It is typically separated from the log search/analytics platform to limit modification or deletion of original evidence.

### 5.1. Log Categories to Consider

| Log category | Example contents | Goal |
| --- | --- | --- |
| Control plane audit | Resource creation/deletion, role/policy edits, network config changes | Trace who did what, when, and where |
| Identity & authentication | Logins, session grants, permission changes, failed attempts | Detect account takeovers and privilege abuse |
| Network | Flow logs, DNS query logs, firewall decisions if needed | Investigate traffic, anomalous egress, connectivity failures |
| Security findings | Posture alerts, threats, vulnerabilities, response actions | Track risk and handle incidents |
| Application & database audit | Sensitive API access, business state changes, DB audit logs | Audit application behavior per requirements |
| Deployment & configuration | Deploy events, IaC changes, verification check results | Correlate incidents with system changes |

Not every debug log, trace, or metric needs long-term retention in the same audit store. You can maintain an **observability account/workspace** for fast querying and a **separate log archive** for raw records retained under policy. Separating **usage purposes** optimizes access controls, retention, and cost.

### 5.2. Log Collection and Protection Pipeline

~~~mermaid
flowchart LR
    W1["Workload Prod"] --> PIPE["Log collection / forwarding service"]
    W2["Workload Nonprod"] --> PIPE
    CONTROL["Organization audit / Security events"] --> PIPE
    PIPE --> STORE["Log Archive<br/>Storage, encryption, retention"]
    STORE -. "Controlled read access" .-> SEC["Security investigation"]
    PIPE --> QUERY["Observability / SIEM<br/>Search, analysis, alerting"]
    SEC --> CASE["Incident record / evidence"]
~~~

Some logging services can deliver directly to an authorized destination without a custom `PIPE` system. The diagram depicts the **responsibility flow**: event sources → collection/forwarding → archive storage and analysis tools.

For critical logs:

- **Enable collection at the appropriate organization or account scope**, automatically covering new accounts where supported; verify required regions, event types, and data events.
- **Restrict write permissions:** senders can only append events through authorized paths, never delete or alter older events.
- **Restrict archive admin permissions:** configure retention policies, versioning, and immutability/object lock where needed and supported; separate configurators from consumers.
- **Encrypt in transit and at rest:** control both key policies and decryption rights. If using customer-managed keys, ensure rotation, recovery procedures, and permissions for the log-writing service.
- **Tag clear provenance:** organization, account/project/subscription, region, resource, timestamp, event type, and request/trace ID where available.
- **Monitor the pipeline itself:** alert when sources stop emitting, deliveries fail, backlogs grow, sinks are modified, or log volume drops against baseline.
- **Manage lifecycle:** separate data needing fast queries from long-term archives, with defined retention periods and valid deletion mechanisms.

Use the word "immutable" precisely: a bucket with versioning does not automatically satisfy WORM requirements or stop a privileged owner from deleting early. Effectiveness depends on object lock/retention settings, permissions, legal policies, and whether keys can be altered. Test actual behavior using high-privilege roles within a safe scope.

### 5.3. Access Controls Preventing Workloads from Deleting Evidence

A permission model might look like:

| Role | Send new logs | Read logs | Change retention | Delete logs early |
| --- | --- | --- | --- | --- |
| Workload runtime | Via designated permissions and channel | Only assigned scope; usually no org-wide raw logs | No | No |
| Central log ingestion | Yes | Only metadata/status needed to operate | No | No |
| Security analyst | Not needed | Yes, scoped to investigations with sensitivity controls | No | No |
| Log platform admin | As needed operationally | Restricted | Allowed under approved change workflow | Blocked by retention/guardrails |
| Auditor | No | Read-only, with query audit trail | No | No |

Actual permissions depend on the service, retention policies, encryption keys, and access model. **Separating accounts alone is not enough**: if an org-level role can still remove retention or disable logging, apply special controls to that role.

### 5.4. Logs Can Contain Sensitive Data

Logs sometimes accidentally capture tokens, emails, phone numbers, IP addresses, request payloads, or personal data. A central store can therefore accumulate large amounts of sensitive information.

Before shipping logs, define data classification, redact sensitive fields, and specify retention periods, query rights, and storage regions. For a booking app, log **event IDs**, **request IDs**, **controlled booking IDs**, **timestamps**, and **outcomes**, avoiding logging full personal details or raw tokens by default.

Centralizing logs from multiple regions must not violate data residency constraints. An organization may need **regional log stores or data-type-specific stores**, plus an aggregation tier holding only permitted metadata.

## 6. How Should Duties Be Separated Across the Three Accounts?

A core rule: **Security detects and investigates; Network provides connectivity; Log Archive preserves audit trails.** The three functions coordinate, but do not administer one another by default.

Example when an alert triggers for the booking API sending anomalous traffic:

1. The workload emits application logs and network flow logs. Collection pipelines ship data to Log Archive or analytics systems as configured.
2. The Security account aggregates the finding with source resource, account, timestamp, and impact, opening an incident.
3. A security analyst queries authorized logs and confirms indicators. The incident coordinator evaluates business impact before isolating the workload.
4. The Network team implements egress blocking or segment isolation **if that is the approved remediation**; the application team may revoke credentials or update configuration.
5. Log Archive retains the evidence under retention rules; investigative access and emergency actions are logged.
6. Post-incident, teams review guardrails, alerts, network settings, and recovery readiness to prevent recurrence.

If a single identity can alter routes, disable logging, delete raw logs, and wipe application resources without additional checks, separation of duties is undermined even across three separate accounts.

### Cross-Account Permission Matrix for Discussion

| Principal / resource | Security | Network | Log Archive | Workload Prod |
| --- | --- | --- | --- | --- |
| SecOps analyst | Read findings, coordinate incidents | View configs needed for investigation | Read logs within investigation scope | Read approved metadata |
| Network engineer | View related tickets | Administer assigned connectivity | View needed flow logs | No database administration |
| Log platform operator | View pipeline health | Only required network access | Administer ingestion and storage per procedure | No application deployment |
| Application team | View own findings | Submit route change requests | Ship logs, view own log scope | Deploy and operate per role |
| Organization administrator | Govern org-level protections per delegation | Controlled emergency permissions | Privileged access per procedure | Privileged access per procedure |

This table is a **desired policy blueprint**, not a directly deployable IAM matrix. When implementing, specify exact resource IDs, actions, conditions, trust policies, permission boundaries, session durations, and audit evidence.

## 7. High-Level Policies and Account Vending

A landing zone works well when every new workload account receives **a consistent baseline configuration from creation**.

An *account vending* workflow typically includes:

1. Request an account with required metadata: workload name, environment, owner, data tier, region, budget, and operational targets.
2. Create the account/subscription/project under the right organizational unit, never leaving production resources outside governed scopes.
3. Attach baseline policies: allowed regions, public resource restrictions, encryption, tags/labels, identity setup, and change tracking.
4. Enroll in central security: threat detection, posture, inventory, and routing findings to Security.
5. Enable required audit/log forwarding and verify test events reach Log Archive.
6. Provision network connectivity if needed: CIDRs/subnets, routes, DNS, private endpoints, firewalls; default-deny unapproved flows.
7. Set budgets, alerts, dashboards, and permissions for the application team; store configs in IaC.
8. Run automated checks or configuration reconciliation, recording handover status and owner.

**Preventive guardrails** block dangerous configurations from taking effect; **detective guardrails** catch non-compliant changes after they happen. Both are usually needed. Some controls cannot be expressed as org-level policies and require workflows, scanners, or application-level configuration.

Policies must include an **exception process**: business justification, resource scope, approver, expiration date, and compensating controls. Otherwise, app teams may work around controls to meet deadlines.

## 8. Illustrative Mapping on AWS, Azure, and Google Cloud

All three ecosystems support multi-boundary governance models, though implementation details differ. The table below is a **conceptual mapping**, not a verbatim configuration guide.

| Capability | AWS (example) | Microsoft Azure (example) | Google Cloud (example) |
| --- | --- | --- | --- |
| Organization structure | AWS Organizations, organizational units, accounts | Entra tenant, management groups, subscriptions, resource groups | Organization, folders, projects |
| Baseline access control | IAM/roles, SCPs, and corresponding service controls | Azure RBAC, Azure Policy, purpose-scoped Entra roles | IAM, organization policies |
| Centralized security | Delegated admin/aggregation for supported security services; Security Hub, GuardDuty | Defender for Cloud, Defender plans, Sentinel, and appropriate workspaces | Security Command Center and organization findings |
| Shared connectivity | Network account, VPC, Transit Gateway, Route 53 Resolver, private connectivity | Connectivity subscription, hub VNet/Virtual WAN, Private DNS, ExpressRoute | Host project/Shared VPC, Cloud DNS, Network Connectivity Center, Cloud Interconnect |
| Audit/logging | Organization CloudTrail and CloudWatch/S3 as needed | Activity Log, diagnostic settings, Azure Monitor, Log Analytics or storage | Cloud Audit Logs, Cloud Logging aggregated sinks/buckets |
| IaC and automation | CloudFormation/Terraform/CDK as chosen | Bicep/ARM/Terraform as chosen | Terraform/Infrastructure Manager as chosen |

Key points to remember:

- **AWS:** the organization management account must be strictly protected. Dedicated Security and Log Archive accounts are common; the network account owns connectivity components shared across workloads. Check regional scope and log types when configuring.
- **Azure:** management groups layer policies over subscriptions; identities bind to the Entra tenant. An Azure subscription is a key governance and billing boundary, whereas a resource group organizes resources **inside a subscription**. Observability workspaces and log archives can live in appropriate dedicated subscriptions.
- **Google Cloud:** projects are the primary governance and quota boundary; Shared VPC uses a host project and service projects. Organization/folder-level logging sinks can aggregate logs as needed, provided destination permissions, log scope, and org policies are verified.

Service names and capabilities evolve over time. During real implementation, verify provider documentation for regions, quotas, IAM, cross-account features, and applicable service terms.

## 9. Complete Example: Multi-Team Booking Platform

Suppose a company operates three products: Booking, Admin Portal, and Analytics. The system has production and nonproduction environments, booking data is business-critical, the security team must investigate suspicious logins, and the platform team manages links from the cloud to an on-premises accounting system.

### Input Requirements

| Requirement | Implications for resource organization |
| --- | --- |
| Each product team deploys independently | Separate workload accounts; scoped deployment permissions |
| Production must not arbitrarily depend on test | Separate accounts/networks/permissions between prod and nonprod |
| Must investigate suspicious admin actions | Cross-account auditing, Log Archive preserving evidence |
| Needs secure connectivity to on-premises | Network account managing VPN/private links, DNS, routes |
| Block unauthorized access and detect misconfigurations | Security account aggregating findings; org guardrails |
| Track cost per product and platform cost | Cost allocation via accounts, tags, shared-service rules |
| Clear incident handling and recovery process | Cross-account runbooks and tests; clear accountability |

### Reference Account Split

~~~text
Organization / Tenant
├── Management / Governance
├── Security Tooling
├── Log Archive
├── Network / Connectivity
├── Workloads / Production
│   ├── Booking Prod
│   ├── Admin Prod
│   └── Analytics Prod
└── Workloads / Nonproduction
    ├── Booking Nonprod
    ├── Admin Nonprod
    └── Analytics Nonprod
~~~

This is an example, not a mandatory list. Additional accounts may be needed for backups, observability, sandboxes, or compliance-isolated workloads. Conversely, a small company may start with fewer accounts while still defining production permissions and auditing clearly.

### Booking Flow in Normal Operations

1. Customers call the Booking API deployed in **Booking Prod**; public ingress exposes only published endpoints with TLS and proper access controls.
2. The Booking API writes transactions to the database owned by Booking Prod. The API → DB flow does not have to traverse the Network hub when inside the same network with appropriate routes.
3. Workloads calling the on-premises accounting system traverse connectivity provisioned by the **Network account**—only permitted routes and ports.
4. Cloud control-plane actions, policy changes, and required audit events ship to **Log Archive**. Debug logs for app teams can be stored/queried separately per policy.
5. The **Security account** receives findings from product accounts; security staff access authorized logs for investigations.
6. Finance receives per-workload cost reports alongside allocated shares of networking, security, and centralized logging costs.

### When a Workload Account Is Compromised

Suppose a workload credential leaks. The design must contain damage:

- The workload's role holds only permissions needed for Booking; it has no permission to modify org-wide IAM.
- The workload continues generating audit events under existing mechanisms, and cannot delete raw logs in Log Archive.
- Security has signals to detect the event and runbooks to isolate identities/resources; emergency actions are audited.
- Network controls restrict connectivity between Booking Prod and other networks by policy, limiting lateral movement.
- Post-incident, raw logs and before/after configurations help assess blast radius.

**Limitation to recognize:** if an attacker controls the log-emitting source or kills a service before logs ship, the central archive cannot reconstruct events that were never generated or transmitted. Therefore, combine source controls, organization-level audit services, log lag/drop monitoring, and multi-source investigation.

## 10. Designing Reliability, Performance, and Scalability for Shared Services

Centralizing administrative governance does not mean **funneling every data path through one server or region**. A shared-service outage can impact many apps, so distinguish the **management plane** from the **data plane**.

| Component | Hypothetical failure | What must be verified |
| --- | --- | --- |
| Central network connectivity | A gateway/tunnel/zone becomes unavailable | Which workloads lose connectivity? Do backup routes and failover times meet targets? |
| Shared DNS | Resolver or forwarding rules fail | Which services fail name resolution? Are redundancy, caching, or fallbacks adequate? |
| Log ingestion | Pipeline delay or quota exceeded | Are logs buffered/retried? Are there lag alerts and event-count reconciliations? |
| Log archive | Destination failure or altered write/key permissions | Are there data-loss alerts, temporary buffering, and recovery when writes resume? |
| Security tools | Aggregation or notification fails | Do workloads keep running? How do responders learn findings are delayed? |
| Identity/SSO | SSO outage | Do operators have a safe, tested break-glass mechanism? |
| Organization policies | Rule applied to wrong scope | Are there sandbox tests, staged rollouts, and revert mechanisms? |

**Illustrative target:** the platform team might set an audit pipeline SLO such as "99.9% of eligible events reach the ingestion store within 5 minutes over a month," paired with per-source alerts if logs stop arriving. This is an SLO example, **not a default guarantee of any service**; you must measure total input events, latency, and failure rates.

If the business requires restoring connectivity within 30 minutes (RTO), the network team must prove it through drills. If logs must not be lost, build durable delivery/buffering and document semantics (such as at-least-once with potential duplicates) rather than assuming "logging is enabled so we are safe."

### The Multi-Region Challenge

Shared accounts can manage resources across multiple regions if the platform supports it; however, a network hub in Region A does not automatically provide optimal paths or redundancy for Region B. Likewise, centralizing logs into one region can run into data residency rules, transfer fees, and recovery constraints. You may need **regional collection points**, **regional storage archives**, and a **security summary tier** holding only permitted metadata.

## 11. Costs of Shared Accounts

Splitting accounts typically does not incur a fixed per-account flat fee; bills primarily reflect **services and actual consumption**. However, a multi-account architecture adds management effort and can introduce always-on shared infrastructure services.

Commonly overlooked cost categories:

- **Networking:** transit/attachments, VPNs, gateways, NAT, firewall inspection, DNS resolvers, cross-zone/cross-region data transfer, and Internet egress.
- **Logging:** ingestion, forwarding, storage, replication, archiving, retention, queries, SIEM, and data transfer.
- **Security:** scanning, threat detection, configuration monitoring, event analysis, and incident response staffing.
- **Operations:** account vending, IaC, policy testing, patching self-managed tools, on-call coverage, runbook maintenance.
- **Nonprod and testing:** environments for rehearsing routing, log delivery, DR, and incident response.

### Estimating Log Storage Before Picking Retention

Suppose an organization generates **20 GB of logs/day**, keeping **30 days** in a hot queryable tier and another **335 days** in archive storage. Assuming constant volume and excluding compression, replicas, indexes, and overhead:

~~~text
Hot storage:       20 GB/day × 30 days   = 600 GB
Archive storage:   20 GB/day × 335 days  = 6,700 GB
Total raw data kept for 365 days         = 7,300 GB ≈ 7.3 TB
~~~

This is only a **raw volume estimate**, not a price forecast. Actual bills depend on pricing for storage, ingestion, queries, replication, compression, and data transfer. In particular, evaluate the impact of noisy debug logs and duplicate writes across multiple pipelines.

### Allocating Shared Costs

Costs can be allocated by:

| Cost category | Possible allocation method | Things to note |
| --- | --- | --- |
| Logging | Log volume per account/workload or ingestion tier | Avoid creating incentives to disable critical audit logs to save money |
| Network egress | Measured traffic per workload/path via telemetry | Some shared fees are difficult to attribute precisely |
| Security tooling | Resource count, usage tier, or central platform budget | Do not create incentives to bypass security controls |
| Shared operations | Platform budget or internal chargeback rules | Publish the allocation formula and accountable owners |

Product teams should see the costs driven by their decisions. The platform team should maintain dashboards for **total shared infrastructure spend**, anomaly alerts, and optimization policies grounded in real metrics.

## 12. Common Design Pitfalls

**1. Confusing "shared account" with "shared credentials."** A shared account is a governance boundary housing platform services; every human and workload still needs its own identity and scoped permissions.

**2. Splitting accounts while granting overly broad cross-account admin roles.** Letting every workload assume a role that can delete archive logs defeats evidence protection.

**3. Routing all traffic through a single hub.** Increases failure domains, latency, and cost; decide routing paths based on actual data flows and control requirements.

**4. Centralizing logs without checking completeness.** Seeing data in a dashboard does not prove every account, region, and event type is arriving. Maintain source inventories and missing-log alerts.

**5. Retaining logs long-term without data classification.** Tokens, personal info, and data restricted from cross-region storage can create greater risk than investigative value.

**6. Assuming managed security services equal complete security.** You still must configure onboarding, permissions, coverage, alerting, finding triage, and response workflows.

**7. Organization policies unexpectedly breaking production.** Test guardrails in sandboxes, roll out incrementally, and designate owners to evaluate exceptions.

**8. Failing to distinguish log analytics tools from evidence archives.** A SIEM for rapid investigation may allow different operational permissions than an evidence archive with immutable retention.

**9. Forgetting platform cost accountability.** Without allocation or visibility, log volumes and network egress can balloon with nobody accountable.

**10. Drawing account diagrams without cross-team runbooks.** During an incident, app, SecOps, and network teams must know who can run which actions, who decides, and whom to notify.

## 13. Practice: Building a Landing Zone for a Booking System

**Prompt:** You are the cloud architect for a company preparing to take a booking application to production. There are three development teams (Booking, Admin, Analytics), a two-person platform team, and a part-time security team. The system needs to connect to an on-premises accounting service; cloud control-plane actions and permission changes must be logged for 12-month investigations. There are two environments: production and nonproduction.

The following figures are for practice only and must be validated in real projects:

- Booking serves roughly 300 requests/second at peak.
- The booking flow requires a 99.9%/month success-rate SLO.
- The accounting link RTO target is 60 minutes; without connectivity, a temporary business fallback must exist.
- Audit logs are projected at 20 GB/day with 365-day retention.
- Customer data and logs containing identifiers must obey defined storage region constraints.

### Task 1 — Design the Account Hierarchy

Draw an account/subscription/project diagram showing Management/Governance, Security, Network, Log Archive, Booking Prod, Admin Prod, Analytics Prod, and Nonprod environments. Record the **owner** and **permission scope** for each group.

**Question:** Should Log Archive be separated from Security Tooling? Answer based on evidence preservation, permissions, and operational staffing rather than citing a rigid template.

### Task 2 — Draw Two Critical Flows

Draw the connectivity flow from Booking Prod → on-premises and the control-plane audit flow from workloads → Log Archive → Security. For each path, document policies for:

- Allowed destinations/ports/routes; DNS and redundancy.
- Who can change routes versus who can only inspect status?
- Which log sources must ship, storage regions, retention, and authorized readers?
- What happens if log shipping or the on-premises link fails?

### Task 3 — Build a Permission Matrix and Guardrails

Define at least five roles: Organization Admin, SecOps Analyst, Network Engineer, Log Operator, Booking Developer. For each role, list **allowed actions** and **denied actions** across four account groups: Security, Network, Log Archive, and Booking Prod.

Propose at least three guardrails—for example, blocking workloads from disabling org-level audit sources, restricting deployment regions, and enforcing log forwarding for production accounts. Specify which guardrails are preventive versus detective.

### Task 4 — Prove the Design with Tests

| Test | Scenario simulated | Expected evidence |
| --- | --- | --- |
| Log deletion rights | Use a Booking Prod role to attempt deleting an audit object in the central archive | Denied; failed attempt logged with proper trail |
| Audit coverage | Trigger a role-change event in both Prod and Nonprod | Event received with accurate source, timestamp, and region |
| Log pipeline outage | Pause/inject a pipeline failure in a test environment | Alert fires; delayed/dropped event counts and recovery steps verified |
| Network access block | Attempt unauthorized connection from Nonprod to Booking Prod DB | Traffic blocked per policy, with test evidence |
| Hybrid connectivity | Simulate one tunnel/gateway failure | Reroutes or degrades per RTO/design |
| Emergency identity | Simulate an SSO outage under authorized procedure | Break-glass works, is monitored, and revoked post-test |
| New guardrail | Deploy policy to sandbox before production | Unintended impacts caught and rollback verified |

Never use real customer data or destructive operations in production for testing. Use clearly scoped and controlled test resources.

### Task 5 — Review Against the Six Well-Architected Pillars

| Pillar | Questions to evaluate the shared-accounts design |
| --- | --- |
| **Operational Excellence** | Are new accounts provisioned repeatably with owners, runbooks, and policy tests? |
| **Security** | Are separation of duties, least privilege, audit protection, MFA, and privileged monitoring enforced? |
| **Reliability** | Do hub, DNS, log ingestion, and identity have single points of failure? Have RTO and log-loss handling been tested? |
| **Performance Efficiency** | Do network routes and log pipelines handle peak load? Are latency, throughput, and quotas measured? |
| **Cost Optimization** | Are gateway, egress, log retention costs, and workload allocation rules forecasted? |
| **Sustainability** | Are duplicate log streams, idle resources, and unnecessary cross-region copies minimized? |

### Minimum Exercise Deliverables

A reviewable design package includes:

1. Account hierarchy diagram with owners.
2. Networking and log-flow diagrams with access boundaries.
3. Role permission matrix; list of guardrails and exceptions.
4. Assumed SLOs/RTOs, failure scenarios, and test evidence.
5. Cost estimates for logging/network/security by load, retention, and environment count.
6. Well-Architected findings table listing evidence, impact, actions, owners, and acceptance criteria.

Reviewers should look for answers to three questions: **who owns the shared capability; what are workloads permitted to do with it; and if it is compromised or unavailable, which systems are impacted?** When those answers rest on diagrams, configurations, permissions, and real tests, the design has a solid foundation to move into implementation.

## 14. Pre-Production Checklist for Shared Accounts

- [ ] Organization, security, network, log archive, and workload accounts have clear owners and dependency lists.
- [ ] Production/nonproduction groups are separated by risk level, data sensitivity, and required permissions.
- [ ] Individual user identities, MFA, short-lived credentials, least privilege, and controlled break-glass access are configured.
- [ ] Guardrails are scoped properly, tested in sandboxes, and paired with exception/rollback mechanisms.
- [ ] Connectivity diagrams detail CIDRs, routes, DNS, ingress/egress, hybrid links, and single points of failure.
- [ ] Critical audit sources are inventoried and verified to deliver logs from expected accounts and regions.
- [ ] Log Archive enforces retention, encryption, tamper/delete protection, and scoped read permissions.
- [ ] Application teams cannot arbitrarily disable org-wide auditing or delete stored raw logs.
- [ ] Alerts exist for degradation in logging, security finding aggregation, or shared network links.
- [ ] Network/DNS/logging have failure tests, recovery procedures, and measurable quality targets.
- [ ] Data classification and data residency constraints apply to both logs and business data.
- [ ] Gateway, egress, ingestion, retention, and security tooling costs are tracked, forecasted, and allocated.
- [ ] IaC, inventory, handover docs, incident runbooks, and a Well-Architected review cadence are in place.

Shared accounts establish an **operational and control foundation for many workloads**, so the design must remain balanced. Separating Security, Network, and Log Archive clarifies permissions, shrinks blast radius, and preserves forensic evidence—while making cross-account connectivity, redundancy, cost governance, and cross-team coordination even more important. The value of this structure is proven when a new workload can be provisioned safely, an incident is detected and thoroughly investigated, and a shared component fails with understood and contained impact.
