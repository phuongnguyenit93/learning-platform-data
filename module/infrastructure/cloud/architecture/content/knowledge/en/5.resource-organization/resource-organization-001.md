# Designing a Landing Zone and Minimum Platform Capabilities

## 1. What Is a Landing Zone and What Problems Does It Solve?

When a development team starts using the cloud, the simplest approach seems to be creating an account, a network, a few servers, and a database. The system may get up and running quickly, but as the number of teams, environments, and data grows, many questions emerge: who is allowed to create resources, who can view logs, which account pays the bill, how is production data isolated from test environments, how do we connect to internal systems, and who handles things when administrative access is lost?

A **cloud landing zone** is an **intentionally prepared and governed foundational environment** in which applications can be deployed under shared rules for resource organization, identity, networking, security, management, activity logging, and cost. A landing zone consists of **structure, controls, operational processes, and automation**; it is not just a VPC/VNet, a Kubernetes cluster, or a set of Terraform modules.

In the **CLOUD_ARCHITECTURE** module, the landing zone is the foundation that connects business requirements to choices of networking, compute, data, and deployment models. Since architecture design must consider reliability, security, scalability, cost, and operations, a landing zone ensures those requirements are enforced consistently from the start, rather than leaving each application team to solve them independently.

**Example:** a booking platform needs a production environment with strict monitoring, backups, and permissions; the development environment needs flexibility while still enforcing budget limits. A landing zone establishes shared boundaries and capabilities so the two environments can evolve without accidentally sharing all permissions, networks, or data.

### Learning Outcomes

After this lesson, you can:

1. Explain what a landing zone is, and distinguish between the **platform foundation**, **application workloads**, and **shared services**.
2. Sketch a resource organization structure based on teams, environments, risk, cost, and governance scope.
3. Identify the minimum platform capabilities required before moving a critical workload to the cloud.
4. Describe the flow for provisioning a new environment using Infrastructure as Code (IaC) and policy guardrails.
5. Evaluate landing zone trade-offs using Well-Architected thinking, from reliability and security to operations and cost.

## 2. Design Scope: Platform, Workloads, and Responsibilities

A landing zone is effective when ownership is clearly defined:

| Scope | Who is typically responsible? | Typical decisions |
|---|---|---|
| **Cloud organization and central governance** | Cloud platform, security, IT governance | Account/subscription/project structure, identity, organization policies, environment provisioning rules |
| **Shared platform capabilities** | Platform/network/security/operations | Connectivity, DNS, centralized audit, baseline monitoring, secrets/keys, IaC tooling and provisioning workflows |
| **Application workloads** | Product team, developers, service SREs | Compute selection, DB design, APIs, caches, queues, scaling, SLOs, backups aligned with business requirements |
| **Controls and compliance assurance** | Security/compliance in coordination with owners | Data classification, retention policies, encryption, access control, audit evidence, risk acceptance |
| **Finance and resource optimization** | Finance/FinOps together with workload owners | Tags/labels, budgets, cost allocation, alerts, quotas, utilization reviews |

In a small team, one person may wear multiple hats. What matters is not having many departments, but ensuring **every decision and every alert has an accountable owner**.

A landing zone does **not** automatically guarantee that an application meets every requirement. For example, configuring encryption at the storage layer does not fix a missing authorization check in an API; creating a backup does not mean a restore test has succeeded. The platform provides the baseline and tooling, while the workload must implement correct application behavior.

## 3. Inputs to Clarify Before Designing

You should not choose an account structure or network model before understanding the scale and constraints. At a minimum, answer the following groups of questions:

| Question group | Examples to clarify | Impact on the landing zone |
|---|---|---|
| **Business** | Is this an internal system, customer-facing product, or transaction-processing application? How critical is it? | Isolation level, protection controls, and change management process |
| **Teams and ownership** | How many product teams exist, who administers the tenant/cloud organization, and who is on-call for incidents? | Permission hierarchy, self-service privileges, alert routing |
| **Environments** | How do dev, test, staging, and production differ in data and access requirements? | Account/subscription/project boundaries, access policies |
| **Security and data** | Is there personal/sensitive data? What are the storage regions, retention periods, and audit requirements? | Data residency, region policies, logging, KMS, permissions, and data egress controls |
| **Connectivity** | What offices, data centers, third parties, and public/private services are involved? | CIDR/IPAM, DNS, routing, VPN/private circuits, ingress/egress |
| **Reliability and recovery** | What are the application SLOs, RTO/RPO for each failure scenario, and acceptable downtime? | Deployment zones, backups, failover, recovery testing |
| **Finance** | What is the initial budget, projected growth, and cost allocation method? | Billing hierarchy, tags/labels, quotas, alerts, and automated resource cleanup |
| **Automation** | Where is IaC managed, who approves changes, and who receives new environments? | Bootstrap, pipelines, policy as code, standard templates |

Targets such as SLO, RPO, or RTO must be confirmed by business owners based on concrete measurement scenarios. You should not treat a generic "best practice" as a commitment for every application.

## 4. Resource Organization: Core Boundaries and Naming Conventions

Most cloud platforms have multiple tiers of resource management. Equivalent concepts are not completely identical, but they all help apply permissions, policies, billing, and isolation within a defined scope.

| Logical need | AWS (example) | Azure (example) | Google Cloud (example) |
|---|---|---|---|
| Organization and governance root | AWS Organizations | Microsoft Entra tenant with Azure management groups | Organization resource |
| Governance scope grouping | Organizational Unit (OU) | Management group | Folder |
| Resource ownership boundary and usually limits/billing | AWS account | Subscription | Project |
| Grouping resources within a boundary | Tags, service-specific constructs | Resource group | Resource hierarchy/labels and service-scoped resources |
| High-level policy enforcement | Service Control Policies (SCP) and complementary mechanisms | Azure Policy and RBAC | Organization Policy and IAM |

**Note:** this is a comparison by design intent, not a one-to-one mapping of behavior or capabilities. AWS accounts, Azure subscriptions, and Google Cloud projects differ in permissions, quotas, billing, policy inheritance, and certain technical boundaries; verify the actual documentation and services before implementation.

### 4.1. Separating Production, Non-Production, and Platform

A **reference** structure for an organization with several product teams:

~~~mermaid
flowchart TD
    Org["Cloud organization / Tenant"]
    Org --> Sec["Security & Audit"]
    Org --> Platform["Shared Platform"]
    Org --> Workloads["Workloads"]
    Sec --> Log["Centralized logging"]
    Sec --> Security["Security tooling"]
    Platform --> Network["Connectivity & DNS"]
    Platform --> Tooling["IaC / CI-CD platform"]
    Workloads --> Prod["Production boundary"]
    Workloads --> NonProd["Non-production boundary"]
    Prod --> BookingProd["Booking prod"]
    Prod --> CatalogProd["Catalog prod"]
    NonProd --> BookingDev["Booking dev/test"]
    NonProd --> CatalogDev["Catalog dev/test"]
~~~

*The diagram shows a **logical** model. A box may correspond to different accounts/subscriptions/projects or resource groups depending on the provider and isolation requirements.*

Design principles:

1. **Separate boundaries by risk level:** production and non-production environments must not share administrative privileges or sensitive data without a documented reason and approved controls.
2. **Reduce blast radius:** a misconfiguration, quota exhaustion, or compromise in one workload should not inherently grant permission to disrupt another workload.
3. **Clear ownership:** each boundary has an owner responsible for cost, operations, access control, and lifecycle.
4. **Intentional policy inheritance:** baselines are applied from the organization or governance group; exceptions are recorded, time-bound, and approved.
5. **Do not over-fragment:** every new account/project introduces overhead for permission management, logging, networking, quotas, and operations. Only split further when risk or independence requirements justify it.

If a company has a single application and a small team, the landing zone can be much simpler. What matters is preserving the critical boundaries, not creating every organizational tier shown in the diagram.

### 4.2. Naming Conventions, Tags/Labels, and Lifecycle

Names help humans identify resources; tags/labels support automation, reporting, and cost management. A convention should be concise, stable, free of sensitive data, and machine-validatable:

~~~yaml
# Example of logical metadata for a workload; not a universal
# resource declaration syntax across all cloud providers.
workload: booking
environment: prod
region: primary-region
owner_team: reservations
technical_contact: platform-oncall
cost_center: product-booking
data_classification: confidential
criticality: high
managed_by: infrastructure-as-code
~~~

Depending on the system, you can add `service`, `application`, `business_unit`, or `expiry_date` for sandboxes. Avoid putting specific person names, personal emails, or sensitive information in tags if billing or visibility mechanisms allow users outside the need-to-know scope to view them.

Do not assume all resource types support tags in the same way. Establish a **list of required fields**, valid values, and validation checks at creation time; for resources that do not support tags, use an inventory/CMDB or equivalent metadata source. Tags are not a security mechanism and do not replace IAM or policies.

## 5. Identity and Permissions: The First Capability Needed

Before a team can create production resources, you need to answer: **which people, which workloads, and which pipelines receive what permissions, for how long, and in what scope**?

### 5.1. Access Baseline

- **Federation/SSO:** integrate with enterprise identity if available, avoiding unnecessary proliferation of long-lived administrative accounts.
- **MFA:** require multi-factor authentication for users, especially for sensitive privileges, aligned with provider capabilities and organizational policy.
- **Least privilege:** grant the minimum permissions required for each role; separate read, deploy, operate, and organization-policy modification permissions.
- **Distinguish humans from workloads:** applications/pipelines should use workload identities, roles, or short-lived tokens as supported; minimize static access keys.
- **Privileged access:** elevated permissions should be time-bound whenever possible, with action logging and an approval workflow.
- **Emergency access:** maintain a protected, separately controlled, and rehearsed break-glass access path; avoid sole dependency on an SSO system that could experience an outage.
- **Lifecycle management:** when employees change roles or leave, revoke permissions promptly; review privileged roles periodically.

### 5.2. Example Permission Model

| Role | Typical permissions | Permissions to restrict |
|---|---|---|
| Platform administrator | Manage organization structure, baselines, and environment provisioning workflows | Access to business data unless required |
| Security auditor | View security logs, posture, and compliance evidence per policy | Ad-hoc workload modifications or deleting audit logs |
| Application developer | Operate assigned non-prod resources, view filtered metrics/logs | Modifying organization settings, central policies, or prod resources outside the pipeline |
| Deployment pipeline | Deploy resource types for the designated workload and environment | Organization-wide permissions, granting privileges beyond scope |
| Production operator | Operate services, view telemetry, and execute approved runbooks | Deleting security resources, altering guardrails |
| Finance/FinOps analyst | Read cost reports and allocation metadata | Accessing application secrets or transaction data |

A separate account boundary does not automatically guarantee security if everyone holds an organization-wide admin role. You must evaluate **permission paths**, trust relationships, inherited policies, and existing credentials.

## 6. Guardrails: Protecting While Enabling Self-Service

A **guardrail** is a mechanism that restricts or detects behavior that violates organizational standards. A well-designed landing zone distinguishes between:

| Type | How it works | Example |
|---|---|---|
| **Preventive** | Blocks violating actions before the configuration takes effect | Deny resource creation outside approved regions; block public storage based on criteria |
| **Detective** | Inspects configurations/events and reports violations | Detect publicly exposed storage, overly permissive security groups, or missing logging |
| **Corrective** | Automatically remediates or triggers a remediation workflow | Remove unauthorized public access, isolate a resource, open a ticket for the owner |

Guardrails can be enforced through organization policies, IAM, policy as code in pipelines, standard templates, drift checks, and security posture tools. A **detective** policy only alerts; it does not block the action itself. A **preventive policy** can break legitimate application operations if poorly targeted or overly broad. You need an exception process with a clear approver, justification, scope, and expiration date.

### Minimum Policy Baseline

1. Allow only deployment regions that match confirmed data residency and legal requirements.
2. Prevent unauthorized public exposure on sensitive data/storage; control network entry points by design.
3. Protect audit log sources, event logging policies, and permissions to delete or modify logs.
4. Ensure appropriate encryption for data at rest and in transit; define key management responsibilities.
5. Control administrative privileges, sensitive permission grants, and static credential creation.
6. Validate ownership metadata, data classification, and cost allocation where supported.
7. Record and track configuration drift; define remediation plans based on risk severity.

For example, a "no public IP for any compute" policy may fit a strict internal network, but not a component that must expose a public entry point. Distinguish between **approved entry points**, protective layers, and whether backend compute actually needs a public IP.

## 7. Foundation Network Design: Connectivity, Isolation, and Name Resolution

The landing zone must establish a network strategy early because changing CIDRs, routing, and DNS after many workloads depend on them is usually costly.

### 7.1. Mandatory Network Decisions

| Component | What needs to be decided? | Risk if skipped |
|---|---|---|
| **IP addressing / CIDR** | Non-overlapping address ranges, growth headroom, IPAM, and relationship with on-prem | IP conflicts, difficult hybrid connectivity |
| **DNS** | Public/private zones, ownership, forwarders, cross-network resolution | Applications connect to wrong endpoints, hard-to-diagnose failures |
| **Ingress** | Entry points from the Internet/partners, TLS, authentication, WAF where appropriate | Expanded attack surface, lack of control |
| **Egress** | Where workloads exit to external networks, how traffic is logged and restricted | Data exfiltration, uncontrolled dependencies or traffic costs |
| **East-west** | Inter-workload communication, micro-segmentation, and network permissions | Lateral movement of failures or compromises |
| **Private service access** | Private connectivity to managed databases/storage/services per cloud capabilities | Unintended reliance on public endpoints |
| **Hybrid connectivity** | VPN, leased/private connections, redundancy, routing, DNS, and operations | A single link failure disrupts multiple services |

A reference design:

~~~mermaid
flowchart TD
    Internet((Internet)) --> Edge["Public ingress: DNS / WAF / Load Balancer"]
    Edge --> App["Application workload network"]
    App --> DB[("Private managed database")]
    App --> Endpoint["Private endpoint to cloud services"]
    Office["On-prem / Office"] <-->|"VPN / private link"| Hub["Connectivity hub"]
    Hub <--> App
    Hub <--> Other["Other workload network"]
    App --> Egress["Controlled outbound access"]
    Egress --> Internet
~~~

*The diagram illustrates logical flows only. Routing rules, firewalls, NAT, subnets, redundancy, and private endpoint capabilities depend on the service and cloud provider.*

A **hub-and-spoke model** can fit well when centralized connectivity, DNS, and firewall management are needed. However, a central hub can also become a bottleneck, introduce cross-zone traffic costs, and create a shared blast radius. Some organizations are better suited to a distributed or hybrid network model with shared guardrails and per-workload ownership.

### 7.2. Do Not Confuse "Private" with "Secure"

Private networks reduce direct Internet exposure but do not replace authentication, authorization, TLS, secrets management, and application behavior validation. Services on an internal network can still be compromised through workload permissions or permitted network paths.

In addition, **do not force all traffic through a central appliance** without clear security requirements and performance/cost benchmarks. Verify the actual traffic paths for logging, monitoring, DNS, and cloud services using private connectivity.

## 8. Logging, Data Security, and Observability

At a minimum, a landing zone needs to **know who changed resources, how the system is running, and what happened when an incident occurred**.

### 8.1. Platform Audit and Application Telemetry

Distinguish between:

- **Control-plane audit:** who logged in, created/deleted resources, modified IAM, changed network policies, rotated keys, or altered cloud configurations.
- **Data-plane audit:** who accessed data and performed which data operations; capture capability varies by service, configuration, and cost.
- **Platform metrics:** quotas, network health, shared resources, policy violations, and health of shared services.
- **Workload observability:** SLIs/SLOs, metrics, logs, traces, and specific business journeys; this is the application's responsibility with platform support.

Minimum requirements for logs:

1. Have an appropriate destination to collect and retain audit logs; separate permissions between log producers and those who can delete/modify logs where feasible.
2. Protect log data with access control, encryption, retention policies, and access auditing; apply immutability controls when required.
3. Monitor **loss of log streams** and collection configuration errors, not just events inside the logs.
4. Enforce filtering/redaction policies for sensitive data: logs should not contain secrets, tokens, payment details, or personal data without a justified purpose.
5. Separate actionable alerts from reference-only data; ensure alerts have designated recipients and runbooks.

Collecting all logs without limits does not automatically mean good observability: logs can contain sensitive data requiring protection, incur high storage and query costs, and create noisy signals. Decide log types, granularity, and retention periods based on risk and business needs.

### 8.2. Example Detection and Incident Handling Flow

Suppose a new account has a storage bucket configured as public in violation of policy:

1. A preventive guardrail blocks the configuration if the action falls within supported enforcement scope.
2. A detective scan re-checks actual state to detect drift or misconfiguration.
3. An alert goes to the owner and security team with evidence: resource, scope, timestamp, and violated policy.
4. If pre-approved, a corrective workflow isolates or remediates the resource with audit logging and without destroying data.
5. The responsible team reviews the root cause, updates IaC or guardrails, and verifies the issue does not recur.

Key takeaway: **controls have a lifecycle**, encompassing deployment, drift detection, remediation, and effectiveness measurement.

## 9. Key Management, Secrets, and Foundation Data

Minimum required capabilities:

- **Encryption key management:** define when to use provider-managed keys versus customer-managed keys; specify who can create, use, rotate, disable, and delete keys.
- **Secrets management:** store secrets in a dedicated secrets service, never in repositories, container images, IaC state, or logs; define rotation and revocation procedures.
- **Certificate management:** issue and renew TLS certificates, protect private keys, and alert before expiration.
- **Data governance:** classify data, define data residency, storage purpose, sharing rules, retention, and deletion aligned with requirements.
- **Backup and recovery:** critical data has backup schedules, tested restore procedures, and access controls protecting backup copies.

Do not assume that "using a managed service" means the system automatically meets all RPO/RTO targets. Restore capability depends on service type, configuration, retention length, failure scenarios, and team procedures. Improperly revoking or deleting an encryption key can render data undecryptable even when backups still exist.

## 10. IaC, Bootstrap, and New Environment Provisioning

A landing zone built solely by hand easily leads to accounts/projects drifting in configuration and becoming hard to recover. Therefore, shared governance components should be defined using **Infrastructure as Code (IaC)** and repeatable processes.

### 10.1. Bootstrap: The "Who Creates the Initial Platform?" Problem

Before IaC pipelines can run, foundational capabilities must be established: the organization/tenant, administrative identities, state storage, deployment permissions, access controls, and a recovery path if the pipeline fails.

Reference sequence:

1. **Protect the governance root:** set up initial administrative accounts, MFA, privilege management, and emergency access.
2. **Create the IaC execution and state backend:** remote state with access control, encryption, state locking against concurrent writes, and appropriate backups.
3. **Provision pipeline identities:** prefer identity federation and short-lived credentials; restrict permission scope.
4. **Build the organization structure:** governance groupings and boundaries for platform, logging, security, and non-prod/prod.
5. **Apply guardrails and audit:** organization policies, log pipelines, control alerts, and log source protection.
6. **Create shared networking/connectivity as needed:** IPAM, DNS, routes, VPN/private connectivity, and observability.
7. **Provision workload environments from templates:** roles, quotas, tags, budgets, network attachments, and baseline observability.
8. **Validate and hand over:** test policies, permissions, pipelines, logs, backups, and incident recovery procedures.

Bootstrapping often involves some initial manual steps; document them, minimize them over time, and protect them carefully. Never hardcode secrets directly in IaC code or state if a safer reference mechanism exists.

### 10.2. The "Account/Subscription/Project Vending" Model

**Vending** is the process of provisioning a standardized, governed environment from a structured request. Example:

~~~mermaid
flowchart LR
    Request["Product team requests environment"] --> Validate["Validate owner / environment / data / budget"]
    Validate --> Approval{"Approval required?"}
    Approval -->|Yes| Review["Authorized approver reviews"]
    Approval -->|No| Plan["IaC plan + policy checks"]
    Review --> Plan
    Plan --> Provision["Create boundary and baseline config"]
    Provision --> Verify["Verify IAM, audit, network, tags, budget"]
    Verify --> Handover["Hand over owner + runbook + inventory"]
    Verify -->|Failed| Remediate["Fix or roll back per procedure"]
    Remediate --> Plan
~~~

*Approval rules depend on environment type and risk level: creating a standard sandbox can be self-service, whereas creating a production environment handling sensitive data may require additional review.*

A request template should include at least: workload, owner, environment, region, data sensitivity level, network connectivity, budget, deployer scope, and time-to-live for temporary resources. Once provisioned, the application team receives an **official access path** to deploy their compute/DB/queues and knows where to view status, costs, and alerts.

### 10.3. CI/CD and Drift Management

Embed policies and standards into the pipeline:

- IaC is peer-reviewed, linted, and checked against policies before apply.
- Separate permissions between viewing a plan and executing changes where appropriate; production changes are controlled.
- Version platform modules with an upgrade process and migration guides.
- Monitor **configuration drift** (actual state diverging from IaC) and evaluate impact before auto-remediating.
- Maintain recovery procedures in case changes to IAM, routes, or DNS lock out the pipeline or break connectivity.

Note: **rolling back IaC does not guarantee data rollback**. If a change affects databases, storage, or stateful resources, you need a dedicated migration, backup, and recovery plan.

## 11. Cost, Quotas, and Resource Lifecycle

Cloud architecture is shaped by cost constraints starting from resource organization. Basic cost management should not wait until bills spike unexpectedly.

### FinOps Baseline

| Capability | Initial implementation | Rationale |
|---|---|---|
| **Billing and ownership** | Associate resources with owners/cost centers via org structure and tags/labels | Identify accountable teams and allocate costs |
| **Budgets** | Set budgets/alerts per workload and environment | Detect overspending before it persists |
| **Quotas / service limits** | Track and adjust limits based on expected load | Prevent accidental over-provisioning and quota exhaustion failures |
| **Cost visibility** | Dashboards by account/project, service, workload, and trend | Spot forgotten resources or network/logging costs |
| **Lifecycle** | Expiration and cleanup for temporary sandboxes; scheduled shutdown for dev resources where appropriate | Reduce idle spend |
| **Periodic review** | Compare actual spend against forecasts, SLOs, and traffic | Optimize with evidence, avoiding cuts that harm reliability |

**Budget alerts typically only notify**, they do not automatically halt all spending. **Quotas are not budgets either**: some services charge per request or traffic volume that quotas do not adequately cap. Understand the exact alert behavior and automated actions supported by your specific cloud provider.

For example, traffic through NAT gateways, cross-region replication, log ingestion, and message traffic can account for significant costs even when VMs are small. Consider **end-to-end journey costs** rather than just compute pricing.

## 12. Reliability and Recovery in a Landing Zone

A landing zone is shared infrastructure; if IAM, DNS, or connectivity is misconfigured, multiple workloads can fail together. Therefore, it also needs reliability targets and recovery procedures.

### Distinguishing Failure Scenarios

| Scenario | Design questions |
|---|---|
| Single VM/node failure | Does the workload have health checks, replacement mechanisms, and spare capacity? |
| Single zone failure | Are components distributed appropriately, with failover and DB support? |
| Single region failure | Does the business truly require multi-region? What costs do data, DNS, failover, and operations incur? |
| Misconfigured account/project | What is the blast radius, permission impact, audit trail, and recovery workflow? |
| IAM/SSO or pipeline failure | Have emergency access, alternative change control paths, and break-glass been tested? |
| Hybrid connectivity / DNS loss | Which workloads depend on on-prem, how do they degrade, and what is the backup routing? |
| Accidental data deletion or corruption | Are backups protected and restore-tested against target RTO/RPO? |

**RTO** is the target time to recover a service after a defined incident; **RPO** is the acceptable amount of data loss measured in time. These values must be agreed upon for each corresponding workload and scenario. Daily backups do not guarantee a 15-minute RPO; running across multiple zones does not automatically protect against accidental data deletion.

### Validating Platform Reliability

- Test logging in and operating with an emergency role in a simulated SSO outage scenario.
- Verify that audit logs still reach their retention store when a workload is misconfigured.
- Rehearse DNS, routing, and IaC state recovery for selected failure scenarios.
- Test restoring resources/data from backups, measure elapsed time, and update runbooks.
- Verify that an overloaded workload does not implicitly exhaust quotas or connectivity for the entire shared environment.

You do not need to rehearse every scenario weekly. Prioritize based on business impact, rate of change, and real observability coverage.

## 13. Defining "Minimum" Based on Risk Level

A **minimum viable** landing zone should be sufficient to deploy the first workload in a controlled manner while providing an upgrade path as the company scales. Do not try to build an entire internal platform before you have a product.

| Capability group | **Before the first production workload** | **When scaling / requirements grow more complex** |
|---|---|---|
| **Resource structure** | Clear owners, prod/non-prod environments, and governance scopes | Tiered by multiple products/teams/data domains; automated environment vending |
| **Identity** | SSO/MFA where feasible, least privilege, workload identity, emergency access | JIT access, automated access reviews, large-scale privileged access management |
| **Security baseline** | Essential guardrails, encryption, secrets management, audit | Broader policy as code, auto-remediation, continuous posture management |
| **Networking** | Planned CIDRs/DNS, sensible ingress/egress, critical network isolation | Hub-and-spoke or multi-network topologies, hybrid connectivity, automated IPAM |
| **Observability** | Central audit, dashboards/alerts for critical components with clear owners | Centralized correlation/tracing, platform SLOs, cross-team incident analysis |
| **IaC** | Version-controlled management for platform and critical workload resources | Self-service vending, module catalogs, drift management at scale |
| **Data protection/DR** | Backups, retention, and at least one risk-appropriate restore test | More frequent drills, multi-zone/multi-region scenarios if required |
| **Cost** | Billing owner, tags/labels, budget alerts, and quota tracking | Showback/chargeback, unit economics, automated optimization policies |

Implementation order still depends on the organization: if the system requires on-prem connectivity before going live, **hybrid networking cannot wait for a later phase**. If the business handles data subject to strict compliance obligations, several advanced capabilities may become baseline requirements from day one.

## 14. Implementation Example: A Booking Platform Moving Its First Application to the Cloud

Assume a company has a **Booking API**, **Search**, a relational database, an email-sending worker, and an operations dashboard. The engineering organization has a few technical teams aiming to launch dev/test and production environments in one primary region, with plans to expand in the future.

These are practice assumptions, not a template to copy verbatim for every system.

### 14.1. Minimum Design Blueprint

| Component | Initial decision | Rationale and verification |
|---|---|---|
| **Organization** | One governance root, separate boundaries for prod, non-prod, and shared audit capability | Limit change blast radius and scope permissions |
| **Identity** | SSO, group-based roles, workload identity for pipelines, break-glass access | Test least privilege and emergency access |
| **Network** | Planned address space; public ingress through a TLS-terminated entry point; private access for app/DB | Verify network paths, DNS, and test blocking unauthorized connections |
| **Security** | Encryption, secrets manager, restricted public storage, guardrails on permission changes | Test policies and access audit logs |
| **Logging** | Centralized control-plane audit; per-owner app metrics/logs/traces | Test alerting and trace a booking creation incident |
| **Data** | Managed relational DB, backup/restore with business-confirmed targets | Perform restore test, check data loss and restore permissions |
| **Delivery** | Reviewed IaC, isolated environments, controlled production pipeline | Test recreating a sandbox, verify policy gates |
| **FinOps** | Owners and cost centers; budget alerts; quotas and review of test resources | Verify cost dashboard and test alert delivery |

### 14.2. Feature Release Flow

1. The product team updates Booking API code and IaC configuration in a peer-reviewed repository.
2. CI runs build/tests, IaC checks, and environment-specific guardrails.
3. The dev pipeline deploys using a role restricted to the non-prod boundary.
4. Load, security, and data tests validate the changes.
5. The production pipeline can only assume the prod role through an approved mechanism; every change generates an audit log.
6. Post-release, metrics, logs, and SLOs confirm the booking journey still meets targets.
7. During an incident, the owner uses runbooks, rollout/rollback, or appropriate recovery; lessons learned are captured to improve platform templates.

The benefit of a landing zone lies in **controlled repeatability**: when creating another workload, teams do not have to redesign IAM, auditing, cost ownership conventions, and deployment pipelines from scratch.

### 14.3. Three Challenge Scenarios

**Scenario A — The development team requests admin rights in production.** Clarify the specific actions needed, the corresponding least-privilege permissions, emergency support procedures, and self-service mechanisms. Do not grant blanket admin access just because the request process is slow; conversely, do not design a process so heavy that incidents cannot be resolved in time.

**Scenario B — All workloads share one VPC/VNet and a single NAT.** Examine isolation needs, routing, traffic costs, quotas, failure propagation, and network permissions; compare against splitting networks by environment/team. Base the decision on risk and cost, not just network count.

**Scenario C — Desire to deploy multi-region from day one.** Ask for the full-region failure scenario, SLO/RTO/RPO, and revenue impact. Account for replication, access permissions, configuration synchronization, routing, failover drills, and cost. Without clear requirements, focus first on validating recovery within an appropriate scope.

## 15. Evaluating a Landing Zone with Well-Architected Thinking

Cloud providers frame Well-Architected with different scopes and terminology. You can use the following common perspectives to challenge a platform design:

| Perspective | Verification questions | Evidence |
|---|---|---|
| **Operational excellence** | Is provisioning new environments repeatable, is drift checked, and is it clear who handles failures? | IaC repository, pipelines, runbooks, owners, environment provisioning test results |
| **Security** | Do policies actually block risky configurations, enforce least privilege, and capture audit trails? | Policy tests, role permissions, access logs, configuration scan results |
| **Reliability** | What single points of failure exist in the platform? Can IAM, DNS, state, and data be recovered? | Failure scenarios, restore tests, drill logs, failover results |
| **Performance efficiency** | Can networking, quotas, and platform capacity handle projected load? | Load tests, connection latency measurements, saturation and quota headroom |
| **Cost optimization** | Are costs visible per environment/workload, and are idle resources and hidden traffic addressed? | Cost allocation reports, budgets, inventory, and cost reviews |
| **Sustainability** | Are resource provisioning and retention aligned with actual utilization? | Utilization metrics, retention policies, sandbox reclamation schedules |

Neither "block as much as possible" nor "centralize as much as possible" applies to every situation. Centralizing logging and guardrails can improve consistency; routing all network traffic through one point can create a bottleneck. Splitting workloads increases isolation but also increases resource counts, accounts, and platform overhead. **Architectural decisions must explicitly state trade-offs and how they are verified.**

## 16. Common Pitfalls

| Pitfall | Consequence | How to avoid |
|---|---|---|
| **Creating only a network and calling it a landing zone** | Missing identity, guardrails, audit, cost controls, and operational processes | Use a capability matrix and readiness criteria |
| **All workloads sharing one administrative privilege** | One compromised account or misconfiguration causes widespread impact | Scope permissions by boundary, enforce MFA, workload identity, and controlled privilege elevation |
| **Every action must go through the platform team** | Platform becomes a bottleneck; app teams look for workarounds | Provide self-service templates and policy gates |
| **Resources created manually without IaC** | Configuration drift, hard recovery, inconsistent environments | Use IaC, drift checks, and change control workflows |
| **Too many accounts/projects from the start** | Unnecessary governance, connectivity, and operational overhead | Start from real risk boundaries with a plan to split when needed |
| **Enabling audit with nobody monitoring the log pipeline** | Events can be lost unnoticed | Monitor ingestion completeness and collection latency |
| **Storing secrets in state/pipeline logs** | Unintended exposure of credentials | Issue short-lived credentials, use a secrets manager, secure state files |
| **Treating budget alerts as hard spending caps** | Bills can continue climbing even after alerts fire | Understand alert semantics, quotas, available hard limits, and response actions |
| **Having backups without restore tests** | RTO/RPO remain untested assumptions | Run recovery drills and record restore results |
| **Blocking all exceptions without a process** | Blocks valid features or encourages shadow workarounds | Implement a risk-assessed exception workflow with an owner and expiration |

## 17. Minimum Landing Zone Acceptance Checklist

Evaluate based on **verifiable evidence**, not just a diagram or verbal confirmation:

- [ ] Governance scope diagram, production/non-production boundaries, owners, and cost allocation method are documented.
- [ ] New environment provisioning process, required inputs, and decommissioning workflow are defined.
- [ ] Root/privileged administrative accounts are protected; an emergency access path has been tested.
- [ ] User and workload identities are configured with least privilege; permission revocation mechanisms exist.
- [ ] Essential guardrails are enforced and tested against violation cases.
- [ ] Sensitive resources use appropriate encryption, secrets management, and access policies.
- [ ] CIDR, DNS, routing, ingress/egress, and hybrid connectivity (if needed) are planned.
- [ ] Control-plane audit is active; logs are protected, retained, and monitored for collection interruptions.
- [ ] Workloads have baseline observability, designated alert recipients, and minimum runbooks.
- [ ] IaC/pipelines include peer review, secure state management, policy checks, and drift handling.
- [ ] Backup/restore plans, per-scenario RTO/RPO targets, and at least one relevant restore test are completed.
- [ ] Tags/labels or alternative metadata exist for owner, environment, data classification, and cost center.
- [ ] Budget alerts, quotas, and cost reports are verified; an escalation process exists for threshold breaches.
- [ ] Responsibilities across platform, security, operations, and application teams are clearly handed over.
- [ ] Current limitations, residual risks, and triggers for future landing zone expansion are documented.

## 18. Practice Exercise

**Context:** A company has two development teams, a search/booking platform, and dev and production environments. Production data contains customer information; the application needs to connect to an on-premises accounting system at the office. They plan to add three more workloads within six months, but the platform team consists of only one person and has a limited budget.

Create a landing zone design addressing these requirements:

1. Propose a minimum resource organization structure, explaining why you separate production, non-production, audit, or shared platform.
2. Sketch the login flow, deployment roles, operational permissions, and emergency access.
3. Choose network boundaries, DNS, office connectivity, and where public application entry points sit.
4. List at least five required guardrails and one verification method for each.
5. Describe how new workloads are provisioned with IaC; identify where review is needed versus where self-service applies.
6. State assumptions for backups, observability, and cost management, then list questions the business must confirm.
7. Compare two options: (A) a centralized network with a hub connecting to the office; (B) separate networks per environment with managed direct connections. Detail cost/complexity and selection criteria.

**Self-check hints:** If your design only has a VPC/VNet diagram, add permissions, guardrails, audit, cost, and lifecycle. If you choose multi-region or many accounts/projects, state the reliability/isolation benefits and justify that the team can operate them. If there is no fallback plan when IAM pipelines or VPNs fail, the landing zone is still missing a critical piece.

## 19. Key Takeaways

A landing zone is a **repeatable cloud governance and operations foundation**: organizing resources, defining permissions, building guardrails, designing connectivity, protecting audit/data, automating environment provisioning, and managing costs. These capabilities enable application teams to choose compute, data, and deployment models suited to business requirements.

A good landing zone does not need the most components; it needs the **right risk boundaries, sufficient minimum capabilities, clear accountability, and tests proving that controls work**. As demand grows, expand the platform based on incident metrics, cost, reliability, and delivery velocity, while continuously re-evaluating decisions with Well-Architected thinking.
