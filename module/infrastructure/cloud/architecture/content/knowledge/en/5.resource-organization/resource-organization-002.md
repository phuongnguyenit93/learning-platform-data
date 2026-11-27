# Organization Hierarchy, Accounts, Subscriptions, and Projects

When designing a cloud application architecture, the first question is often which networks, servers, containers, databases, and services the application needs. However, before deploying those resources, the team needs to answer a question with long-term impact: **which governance scope will each resource belong to?**

Cloud providers offer multiple organizational tiers such as **organization**, **account**, **subscription**, **project**, **folder**, **management group**, and **resource group**. They help manage access permissions, security policies, costs, quotas, and environment lifecycles. Placing resources at the right level from the beginning enables an application to scale without turning access control, auditing, and budget allocation into an unmanageable pile of exceptions.

This lesson belongs to the **Resource Organization** chapter of the **CLOUD_ARCHITECTURE** module. The goal is to design a hierarchy that serves business requirements and cloud infrastructure choices, understand the trade-offs across reliability, security, scalability, cost, and operations, and validate the design using Well-Architected questions.

## 1. Why Is a Resource Hierarchy an Architectural Decision?

Suppose a company has an online booking application with development (**dev**), testing (**staging**), and production (**prod**) environments. If all resources share a single governance scope, the following risks easily arise:

- Developers are granted broad permissions to experiment and accidentally modify or delete the prod database.
- A test system consumes excessive resources, competing for service quotas with the production system.
- Compute, database, and network traffic costs are difficult to allocate to individual products or teams.
- A misapplied network or encryption policy can simultaneously impact multiple workloads.
- Handing over ownership, decommissioning an environment, or meeting audit requirements becomes complex.

Resource organization establishes **intentional management boundaries**. For example, separating prod from dev at an appropriate account, subscription, or project level typically creates a much stronger boundary than merely naming resources differently within the same scope.

However, a hierarchy **does not automatically create security or availability**. If two environments still share secrets, networks, administrative accounts, or critical data systems, risks can still propagate. Organizational boundaries must be paired with access control, network design, policy configuration, and real operational practices.

### Key Terms to Distinguish

| Term | General meaning | What not to assume |
|---|---|---|
| **Organization** | Top-level organizational management tier, usually containing multiple lower-level resource units and serving as the point for centralized governance | Not synonymous with a single deployment region or a single network |
| **Account** | In AWS, an important boundary for resources, identities, service limits, and billing/costs | Not the same concept as an individual employee's login account |
| **Subscription** | In Azure, a scope for deploying resources, managing access, applying policies, tracking consumption, and billing | Not a one-to-one equivalent of an Azure resource group |
| **Project** | In Google Cloud, the foundational scope containing resources, enabling APIs, granting permissions, and linking billing | Not merely a software project name or a Git branch |
| **Folder / Organizational Unit (OU)** | A grouping of subordinate units for management or policy inheritance, depending on the provider | Usually not a container that directly holds all workload resource types |
| **Management group** | A management tier above Azure subscriptions for applying consistent access and policies | Not a group of virtual machines or a networking system |
| **Resource group** | A scope for grouping and managing resources in Azure, usually by application or lifecycle | Not a new tenant or a new subscription |

Key point: terminology differs across providers. Do not try to build a strict equivalence table claiming "one account = one subscription = one project" in an absolute sense. They play similar roles in workload isolation design, but their identity structures, billing models, quotas, and policy scopes are not identical.

## 2. Typical Hierarchies of AWS, Azure, and Google Cloud

### 2.1. AWS: Organization → OU → account → resources

AWS Organizations enables centralized management of multiple AWS accounts. An organization has a **management account**, **member accounts**, a **root**, and optionally nested **organizational units (OUs)**. An account resides at a position in the organization tree; services and resources run within that account, often scoped to a Region or Availability Zone depending on the service.

~~~mermaid
flowchart TD
    ORG["AWS Organization"] --> ROOT["Root"]
    ROOT --> SEC["OU: Security"]
    ROOT --> W["OU: Workloads"]
    ROOT --> S["OU: Sandbox"]
    SEC --> LOG["Account: Central logging"]
    SEC --> AUDIT["Account: Security audit"]
    W --> PROD["OU: Production"]
    W --> NONPROD["OU: Non-production"]
    PROD --> APPP["Account: Booking prod"]
    PROD --> PAYP["Account: Payment prod"]
    NONPROD --> APPD["Account: Booking dev/staging"]
    S --> EXP["Account: Experiments"]
    APPP --> R1["VPC, compute, database, logs..."]
~~~

The **account layer** is a critical boundary for separating permissions, resources, and many service limits. **OUs** primarily group accounts and attach governance policies; an OU does not itself become a network or a database. Accounts can be managed consistently for access via AWS IAM Identity Center, auditing, logging, and organization policies.

Key points to remember:

- **Service Control Policies (SCPs)** in AWS Organizations restrict the maximum permissions available in member accounts within their target scope; SCPs **do not grant permissions**. Effective permissions still depend on IAM and related evaluation mechanisms.
- The **management account** holds organizational privileges and must be strictly protected; daily application workloads are typically kept out of this account.
- **Consolidated billing** aggregates billing across an organization, but you still need account structure, cost allocation tags, and reporting to determine per-workload costs.
- **Region** and **Availability Zone** are infrastructure deployment dimensions, not tiers replacing OUs or accounts.

### 2.2. Microsoft Azure: tenant → management group → subscription → resource group → resources

Azure has multiple tiers to distinguish. A **Microsoft Entra tenant** is the identity and directory boundary for users and applications. In resource management via Azure Resource Manager, **management groups** form a governance tree above **subscriptions**, followed by **resource groups** and resources. A subscription is associated with one Entra tenant at a time; the **billing account/billing profile** hierarchy belongs to the billing system and does not necessarily mirror the management group tree.

~~~mermaid
flowchart TD
    TEN["Microsoft Entra tenant: identity"] -. "directory association" .-> MG["Tenant root management group"]
    MG --> P["Management group: Production"]
    MG --> N["Management group: Non-production"]
    P --> SP1["Subscription: Booking prod"]
    P --> SP2["Subscription: Payments prod"]
    N --> SD["Subscription: Development"]
    N --> ST["Subscription: Staging"]
    SP1 --> RG1["Resource group: app"]
    SP1 --> RG2["Resource group: data"]
    RG1 --> APP["App service, container, network..."]
    RG2 --> DB["Database, storage..."]
~~~

Access and policy management scopes generally inherit down **management group → subscription → resource group → resource**. Azure RBAC defines who can perform actions; Azure Policy defines governance rules such as required tags, allowed locations, or permitted configurations. There are also additional mechanisms such as deny assignments and resource locks, with specific behaviors that must be verified.

Key points to remember:

- A **subscription** is typically the primary unit for separating environments, quotas, and cost governance. Not all quotas are tracked identically: their scope may be subscription, Region, service type, or a combination thereof.
- A **resource group** groups resources by management or lifecycle needs. A resource group has a location field for its metadata, but **resources inside the group can be deployed in different Regions** when the resource type allows.
- **Entra tenant** relates to identity; **subscription** relates to resources/consumption; **billing scopes** relate to payment. They are connected, but they are not the same hierarchy.
- Permissions assigned at high scopes have broad impact. Changes at the root management group require strict governance and testing procedures.

### 2.3. Google Cloud: organization → folders → projects → resources

Google Cloud provides an **organization resource**, optional **folders** to group and manage projects, and **projects** that contain most service resources. Many services require enabling their API in a project before use. A **billing account** is linked to projects under the billing model; the billing account is not a branch of the organization → folder → project tree.

~~~mermaid
flowchart TD
    O["Google Cloud Organization"] --> F1["Folder: Production"]
    O --> F2["Folder: Non-production"]
    O --> FS["Folder: Security"]
    F1 --> BP["Project: booking-prod"]
    F1 --> PP["Project: payments-prod"]
    F2 --> BD["Project: booking-dev"]
    F2 --> BS["Project: booking-staging"]
    FS --> LP["Project: central-logging"]
    BP --> RES["Compute, VPC, database, storage..."]
    BILL["Cloud Billing account"] -. "billing link" .-> BP
    BILL -.-> PP
    BILL -.-> BD
~~~

Google Cloud IAM and Organization Policy support governance at appropriate scopes, with inheritance from the organization/folder down to projects and resources. Folders are useful for applying shared policies across a group of projects. A **project** is the central unit for IAM, API enablement, resource limits, and cost allocation; the **project ID** is a stable identifier, so follow a naming convention from the start.

Key points to remember:

- **Organization Policy** sets governance constraints; whether an action can actually be performed still depends on IAM permissions and related restrictions.
- A **Cloud Billing account** pays for linked projects. A project must be linked to a valid billing account to use billable services as required by the platform.
- A **Shared VPC** configuration allows service projects to use networks from a host project based on IAM permissions, but sharing a network requires evaluating isolation and operational responsibilities.
- Some projects can exist outside an organization in specific scenarios; for enterprises, keep projects under a controlled organization for consistent policies and inventory visibility.

### 2.4. Purpose-Based Comparison

| Architectural need | AWS | Azure | Google Cloud |
|---|---|---|---|
| Governing multiple environments/workloads | AWS Organizations | Management groups and subscriptions | Organization and folders |
| Primary scope for workload isolation | Account | Subscription | Project |
| Grouping child units for governance | OU | Management group | Folder |
| Grouping related resources at a granular level | Resource tags, service-level constructs, and management tools; no exact Resource Group entity equivalent | Resource group | Project, labels, service groups, and resource management mechanisms |
| Centralized governance policies | SCPs and Organizations policy types | Azure Policy, scoped Azure RBAC | Organization Policy, scoped IAM |
| Centralized billing management | Consolidated billing | Billing account/profile and subscriptions per agreement model | Cloud Billing account linked to projects |

**Do not use this table as an automatic conversion map.** For example, an Azure resource group is not an isolation boundary equivalent to an AWS account; a Google Cloud project also differs from an AWS account in IAM, networking, and quota behavior. Before deciding on boundaries, verify the exact mechanisms of the platform you are using.

## 3. Governance Hierarchy and Deployment Topology Are Two Different Dimensions

A governance hierarchy describes **who owns and controls resources**; a deployment topology describes **which Region/AZ resources reside in, how networks connect, and which services depend on one another**. They are related, but one does not replace the other.

For example, a single AWS account for Booking prod can contain a private network, subnets across multiple Availability Zones, multiple API instances, and a managed database. Conversely, one Azure subscription can contain resource groups with resources across multiple Regions. A Google Cloud project can contain zonal, regional, multi-regional, or global resources depending on the service.

Therefore, **separating accounts/subscriptions/projects does not automatically isolate networks**, and **deploying across multiple Availability Zones does not automatically separate administrative permissions**. When evaluating blast radius (the scope of impact from a failure or misconfiguration), consider all of the following simultaneously:

1. **Identity and access:** Who can modify which resources or data?
2. **Networking:** Where can workloads connect? Do they share DNS, NAT, endpoints, or core networks?
3. **Data:** In which scope do databases, backups, encryption keys, and secrets reside?
4. **Quotas:** Can one workload exhaust quotas that another workload depends on?
5. **Change management:** How many environments can a single pipeline or administrative role modify at once?
6. **Operational dependencies:** If shared logging, identity, CI/CD, or shared services fail, which systems are affected?

This is why resource hierarchy is part of architecture design, not just tidying up folder names.

## 4. Choosing Boundaries for Environments, Products, and Teams

A generally effective rule is to prioritize **isolating prod and non-prod**, then consider splitting by product, owning team, data sensitivity, and operational requirements.

| Criterion | When to separate at account/subscription/project level | When controlled grouping may work |
|---|---|---|
| **Environment** | Prod requires independent permissions, quotas, and change control from dev/test | Multiple small test environments with the same risk level and clear policies |
| **Ownership** | Two teams have independent operational responsibilities or budgets | One team manages the same lifecycle, regulations, and processes |
| **Data** | Different data sensitivity levels or regulatory/legal jurisdictions | Workloads share the same data classification and appropriate controls |
| **Blast radius** | A misconfiguration could disrupt another critical system | Test systems can tolerate shared impact |
| **Quotas/limits** | Load or scoped limits risk contention | Small workloads with monitoring and quota controls |
| **Cost** | Separate budgets, chargeback, or financial accountability are required | Minor spend, adequately tracked via tags/labels |
| **Lifecycle** | A product/environment has an independent creation, deletion, and release schedule | Resources are always deployed and decommissioned together |

### Three Common Patterns

**Pattern A — Separate by environment.** One prod scope, one staging scope, and one dev scope. Suitable for small teams with a few workloads under the same owner. Advantage: simplicity; disadvantage: products inside prod may still share permissions, quotas, and policies.

**Pattern B — Separate by product × environment.** For example, Booking-prod, Booking-dev, Payments-prod, and Payments-dev. Increases isolation and cost attribution, fitting organizations where multiple products have different scale or security requirements. Trade-off: accounts/subscriptions/projects, roles, networks, and pipelines must be automated to avoid operational overload.

**Pattern C — Combine functional zones and sensitivity tiers.** Dedicated scopes for security/logging, shared networking, sandboxes, and per-product workloads. Suitable for large organizations or audited environments, but requires managing dependencies on shared services and avoiding an over-engineered platform relative to team size.

There is no single right model. The decision must balance **isolation risk** against **governance and operational overhead**. Putting every microservice into a new account is not automatically better; nor should you keep every critical system in a single account just to have fewer management units.

## 5. Tiered Access and Policies: Top-Down Control

A hierarchy proves its value when shared rules are enforced consistently and execution permissions at lower levels are delegated with clear accountability.

~~~mermaid
flowchart TD
    POL["Organization-level policies"] --> GRP["Account/subscription/project groups by environment"]
    GRP --> U1["Prod workloads"]
    GRP --> U2["Non-prod workloads"]
    POL -. "shared guardrails" .-> U1
    POL -. "shared guardrails" .-> U2
    IAM["Identities, roles, and least privilege"] --> U1
    IAM --> U2
    AUD["Centralized auditing and alerting"] -. "event ingestion" .-> U1
    AUD -. "event ingestion" .-> U2
~~~

A governance design typically distinguishes three layers:

- **Mandatory guardrails:** Restrict deployment regions when data residency is required; block disallowed resource types or configurations; require audit logging, encryption, and data protection policies according to platform capabilities.
- **Operational permissions:** Define which employees, operations teams, workload identities, or pipelines can create/modify/read/delete which resources, in which scope, and for how long.
- **Detection and response:** Collect logs, evaluate configurations, detect violations, and remediate drift—including issues that cannot or should not be blocked at resource creation time.

For example, in an organization running a Booking service:

1. The **platform** team has permissions to build infrastructure templates and operate shared components.
2. The **Booking** team can deploy services within Booking-dev and deploy to prod through an approved pipeline; they do not need manual admin rights over the entire prod scope.
3. The **security** team inspects configurations, access events, and central policies; only a small number of privileged accounts can perform sensitive actions.
4. The **application** identity only has the permissions required to read secrets, write logs, and access assigned data; application permissions are separated from developers' personal permissions.

The **principle of least privilege** applies to both humans and workloads. Permissions granted at the organization/root level are far broader than at the project or resource level; prefer the narrowest scope sufficient to complete the task. Temporary privilege elevation needs expiration, logging, and auditing; emergency (*break-glass*) accounts must be protected, monitored, and rehearsed according to procedure.

Note on mechanics: AWS SCPs and Google Cloud Organization Policies primarily constrain allowed actions; they do not replace the IAM permissions required to act. In Azure, Azure Policy and Azure RBAC also address different questions. Never assume that an "allow" policy by itself grants access.

## 6. Shared Networking and Services: Intentional Sharing

Splitting governance scopes leads to the next question: should workloads use shared networks and services, or own their own?

**Distributed approach:** Each account/subscription/project creates its own network, supporting network services, logging, and pipelines. Ownership boundaries are clear, but repeating components increases cost and management effort.

**Centralized approach:** A central resource group or scope manages core networking, DNS, connectivity to internal systems, logging, security, or CI/CD. Workloads connect through approved mechanisms such as hub-and-spoke, peering, transit, or shared networks depending on the provider.

Examples:

- AWS can use a multi-account model with per-workload VPCs connected through a governed shared network mechanism.
- Azure can use a hub-and-spoke virtual network with a central connectivity subscription and workload subscriptions.
- Google Cloud can use Shared VPC with a host project and service projects when its permission model and limits meet requirements.

These choices are **not mandatory** and are not exact out-of-the-box equivalents across clouds. You must design the actual traffic paths and access controls, including routes, DNS, private endpoints, firewalls, logging, IP address planning, and data transfer costs.

### Blast Radius Trade-Offs

A misconfigured central DNS or core connectivity service can disconnect multiple workloads simultaneously, even across different accounts. Conversely, duplicating every infrastructure service for every workload causes waste and multiplies patching targets. Therefore, distinguish between:

- **Components safe to share** thanks to sufficient isolation, redundancy, and operational maturity.
- **Components better kept separate** due to sensitive data, specialized privileges, heavy load, or differing availability requirements.
- **Components that require redundancy and recovery testing** because multiple workloads depend on them.

## 7. Billing, Budgets, Tags/Labels, and Quotas

The hierarchy is also part of cost architecture. However, **billing scopes are not identical to resource scopes**:

- AWS Organizations can consolidate billing across many accounts; granular costs must be analyzed by account, service, and eligible cost allocation tags.
- Azure has multiple billing tiers depending on agreement type, while subscriptions are usually a practical unit for allocating budgets and consumption accountability.
- Google Cloud has Cloud Billing accounts linked to multiple projects; the project is a primary dimension for cost tracking, combined with labels and billing export fields.

### Minimum Metadata Conventions

For resources that support tags/labels, apply a centrally governed key set:

| Illustrative key | Example values | Purpose |
|---|---|---|
| environment | dev, staging, prod | Classify environments and policies |
| application | booking-api | Locate resources by application |
| owner | team-booking | Identify accountable person/team |
| cost-center | product-platform | Cost allocation |
| data-classification | internal, confidential | Attach data protection requirements |
| managed-by | terraform, platform | Identify management mechanism |
| lifecycle | permanent, temporary | Define expected lifespan |

This is a **recommended convention**, not a built-in default tag list applied verbatim across all providers. Some resources or services do not support full metadata; key names, case sensitivity, and character rules also vary. For untaggable resources, use other cost attribution methods such as separate management scopes and reporting rules.

### Quotas Do Not All Follow One Tier

Quotas and rate limits can apply at the account, subscription, project, Region, service type, API, or combined-scope level. Some limits can be increased upon request, while others are fixed or depend on service conditions. When separating workloads, answer:

1. How much compute, IP addresses, network connections, storage capacity, and requests is each system expected to use?
2. Which limits could block scale-out during peak hours?
3. Are quotas shared with other workloads?
4. Does a failover scenario to another Region require pre-allocating quotas or capacity?
5. Are there near-threshold alerts, increase request procedures, and load-shedding plans?

For example, moving prod to a separate subscription/project can help governance and reduce contention for **some** quotas, but it does not guarantee every quota is independent. Check the exact scope of each specific quota.

## 8. Landing Zone: Standardizing from the Moment a Scope Is Created

When an organization has many accounts/subscriptions/projects, creating each manually quickly leads to configuration drift. A **landing zone** is a set of designs and mechanisms for provisioning cloud environments under governance standards. It typically covers hierarchy, identity, permissions, networking, logging, security, billing, quotas, and automation.

A workload provisioning workflow can be described as follows:

~~~mermaid
flowchart LR
    R["Request to create workload"] --> C["Classify: owner, data, environment, RTO/RPO"]
    C --> H["Select account/subscription/project and parent group"]
    H --> B["Apply baseline policies, IAM, audit, network"]
    B --> I["Deploy resources via IaC"]
    I --> V["Verify policies, security, cost, and operations"]
    V --> O["Hand over to team, monitor, and iterate"]
~~~

A **baseline** should ensure minimum conditions for any new environment:

- Resource structure and naming follow conventions; owner, application, and environment are clearly identifiable.
- Identities integrate with centralized login where appropriate; roles are granted based on need.
- Essential audit and security logs are collected, protected from unauthorized deletion/modification, and retained per policy.
- Secure default network configuration; connectivity paths to shared services are clearly defined.
- Data protection policies, encryption, and secrets management on appropriate services.
- Budgets, cost alerts, and quota monitoring tied to the right owner.
- Infrastructure managed as code (*infrastructure as code — IaC*) with a change review process.

Do not turn the baseline into a "one-size-fits-all" configuration. For example, a lab environment may need a short TTL, low quotas, and freedom to create experimental resources; prod handling sensitive data needs stricter change control, logging, and higher redundancy. Exceptions require a justification, an approver, an expiration date, and a review process.

### Example Logical Structure Declaration

The file below only illustrates the concept of a **provider-agnostic organizational blueprint**. It is not Terraform code or YAML directly accepted by any cloud provider.

~~~yaml
organization: example-company
groups:
  - name: security
    purpose: centralized-audit-and-logging
    units:
      - id: security-logs
        owner: team-security
        environment: shared
  - name: production
    guardrails: restrictive
    units:
      - id: booking-prod
        owner: team-booking
        data_classification: confidential
        cost_center: commerce
      - id: payment-prod
        owner: team-payments
        data_classification: restricted
        cost_center: commerce
  - name: non-production
    guardrails: development
    units:
      - id: booking-dev
        owner: team-booking
        environment: dev
      - id: booking-staging
        owner: team-booking
        environment: staging
~~~

When implemented, a **unit** can map to an AWS account, Azure subscription, or Google Cloud project under different parent grouping structures. Policies, networking, and billing must be defined using the mechanisms supported by the chosen platform.

## 9. End-to-End Example: Resource Organization for a Booking Platform

Suppose a company is building a booking platform with two business domains: **Booking** (search and reservations) and **Payments** (collections and refunds). The system runs on the cloud, aims to protect personal data, deploys multiple versions, and tracks costs per product.

Architectural requirements:

1. Prevent dev-environment developers from having direct permission to modify prod data.
2. Enable independent releases for Booking and Payments, with proper change control and rollback.
3. Allocate costs per product team and identify unowned resources.
4. Store audit logs and critical security alerts centrally, with restricted modification/deletion permissions.
5. Apply stricter access and network controls to the payment system than to standard business services.
6. Ensure each workload has appropriate quotas, budgets, and overload handling plans.

A **proposed hierarchy**:

~~~text
Company cloud organization / tenant
|
+-- Security / Audit
|   +-- Central logging and security monitoring
|
+-- Shared platform
|   +-- Network connectivity, DNS or CI/CD shared services
|
+-- Production
|   +-- Booking prod
|   +-- Payments prod
|
+-- Non-production
|   +-- Booking staging
|   +-- Booking dev
|   +-- Payments staging
|   +-- Payments dev
|
+-- Sandbox
    +-- Temporary experiments with budgets and expiry
~~~

This is a **logical model**; not every line must be a distinct physical unit in every provider. For example, it can be implemented as follows:

| Logical component | AWS | Azure | Google Cloud |
|---|---|---|---|
| Production | OU Production | Management group Production | Folder Production |
| Booking prod | AWS member account | Azure subscription | Google Cloud project |
| Payments prod | Separate AWS member account | Separate Azure subscription | Separate Google Cloud project |
| Non-production | OU Non-production | Management group Non-production | Folder Non-production |
| Logging/security | Dedicated account in OU Security | Dedicated subscription in appropriate management group | Dedicated project in folder Security |
| Shared network/platform | Shared Services account where appropriate | Connectivity/Platform subscription where appropriate | Host project for Shared VPC or shared services project where appropriate |

### Sample Access and Operations Flows

**Booking developers:** Have least-privilege permissions to work in Booking-dev. For prod, they open pull requests and deploy through a controlled pipeline/role; they do not need manual admin permissions over the entire prod scope.

**Deployment pipelines:** Have separate identities per environment; use short-lived tokens/roles or federation where supported. The Booking-prod pipeline does not inherently have permission to modify Payment-prod.

**Security:** Can read audit data and configurations across units as needed; privileged modification permissions are restricted and logged. Centralized logging must not allow workloads to arbitrarily delete or disable historical logs.

**Platform:** Operates shared network components and central governance systems; publishes connectivity provisioning mechanisms and change policies to reduce manual bottlenecks.

**Product owners:** Monitor budgets, quotas, availability, and data within their scope. When security levels or unit structures need to change, record the decision, accountable owner, and cascading impact.

### Which Decisions Should Be Recorded?

Example of an Architecture Decision Record (*ADR*):

> **Context:** Booking and Payments have independent deployment lifecycles. Payments handles more sensitive data and must not grant broad access to other teams.
>
> **Decision:** Separate Booking-prod and Payments-prod into two workload units at the account/subscription/project level. Each unit has controlled permissions, policies, quotas, and budgets. Security logging is centralized in a dedicated unit.
>
> **Rationale:** Reduce the blast radius of misconfigurations; clarify ownership, cost accountability, and operational responsibility.
>
> **Trade-offs:** Increases the number of units to provision, network links, roles, and pipelines; requires automation and consistent configuration tracking.
>
> **Verification:** Test that dev accounts are denied access to prod; verify cross-pipeline permissions; rehearse shared-service failures; inspect cost reports and audit logs.

Regarding networking and data, Booking and Payments may still need APIs or events between them. **Separating governance units does not replace API contracts, service authentication, connection controls, idempotency, or transaction design.** Treat every cross-boundary link as an integration with specific security and reliability rules.

## 10. Evaluating the Architecture with Well-Architected Principles

Well-Architected question sets help evaluate whether the hierarchy actually serves the running system:

| Pillar | Questions to evaluate | Expected evidence |
|---|---|---|
| **Operational excellence** | Can a workload scope be created, updated, handed over, or decommissioned using a consistent process? | IaC, pipelines, ownership diagram, runbooks, exception management workflow |
| **Security** | Can dev impact prod? How are elevated privileges and cross-boundary access controlled? | IAM/RBAC reviews, policy tests, audit logs, emergency identity controls |
| **Reliability** | How much functionality can a misconfiguration in a workload or shared service break? | Dependency map, blast radius analysis, failover and recovery tests |
| **Performance efficiency** | Do quotas, bandwidth, and shared services meet traffic demands? | Load tests, quota dashboards, p95/p99, connectivity and latency metrics |
| **Cost optimization** | Are costs known per product, environment, and unowned resources? | Cost allocation reports, budgets, tag/label coverage, alerts |
| **Sustainability** | Are unused resources or long-lived sandboxes cleaned up? | TTLs, reclamation schedules, right-sizing, utilization tracking |

For example, the requirement "a misconfiguration in dev must not modify prod resources" must be verified via **effective permissions** and access-denied tests; naming resources differently or separating visual folders is not enough. The requirement "know costs per product" must be verified with reproducible billing reports, not just seeing tags in a console UI.

### Measurable Acceptance Criteria Examples

The following thresholds are **illustrative assumptions** and must be adjusted to real needs:

- **100%** of new workload scopes have a clear owner, environment, and cost center at creation time.
- **100%** of privileged permissions in prod go through an approval workflow, audit logging, and periodic review.
- **100%** of prod resources fall under mandatory audit log collection per defined policy.
- **Zero** cross-deployment permissions from Booking-dev to Payments-prod without authorization.
- Budget and quota alerts exist at thresholds agreed upon by each product team.

Do not treat a neat governance diagram as proof that policies work. Criteria must be measured via configuration checks, access tests, billing queries, and incident drills.

## 11. Common Pitfalls and How to Fix Them

**Pitfall 1 — One account/subscription/project for both prod and dev.** A single action permission or quota can impact both. Fix: separate environments with different risk profiles at the appropriate scope and apply independent permissions.

**Pitfall 2 — Granting admin permissions at high scopes just to save time.** Inherited permissions can reach many workloads. Fix: grant at the smallest scope, use task-specific roles, and prefer temporary elevation for special tasks.

**Pitfall 3 — Treating an OU, folder, or management group as a private network.** They support governance and policies, not network segmentation. Fix: design network topology, routing, firewalls, and service access controls separately.

**Pitfall 4 — Treating an Azure resource group like a subscription.** Resource groups organize resource lifecycles and lower-level management, but do not provide subscription-level billing and quota boundaries. Fix: split subscriptions when stronger boundaries are needed; use resource groups for application lifecycles.

**Pitfall 5 — Using tags instead of security boundaries.** Metadata is useful for reporting or policy conditions, but does not isolate permissions or data on its own. Fix: enforce IAM, policies, networking, and test actual permissions.

**Pitfall 6 — Splitting into too many units without automation.** Manual provisioning causes drift across IAM, logging, networking, and budgets. Fix: design a landing zone, templates, IaC, and automated provisioning/decommissioning workflows.

**Pitfall 7 — Centralizing all platform services while ignoring blast radius.** A bad change in shared DNS, networking, or identity can impact many products. Fix: analyze dependencies, restrict change permissions, add redundancy, and test shared-service recovery.

**Pitfall 8 — Assuming project/account separation satisfies compliance.** Data can still leak through broad IAM permissions, shared secrets, or uncontrolled integrations. Fix: review full data flows, key management, auditing, and security processes.

**Pitfall 9 — Naming things without ownership and lifecycle.** Nobody takes responsibility for stale resources, causing rising costs and accumulated misconfiguration risks. Fix: require owners, budgets, expiration dates, and periodic reviews.

## 12. Process for Designing a Practical Hierarchy

You can proceed in this order:

1. **Inventory workloads and data:** Identify products, environments, responsible teams, data sensitivity, and compliance requirements.
2. **Define required isolation boundaries:** Focus on prod/non-prod, user permissions, data, risk levels, quotas, and lifecycle.
3. **Select parent-child structure by cloud:** AWS root/OU/account, Azure management group/subscription/resource group, or Google Cloud organization/folder/project; account for provider differences in the design.
4. **Build the baseline:** Identity, IAM/RBAC, policies, logging, networking, billing, tags/labels, and quotas.
5. **Design shared services:** Specify what is centralized versus distributed; assess impact when shared services fail.
6. **Automate:** Provision and decommission workload units through peer-reviewed mechanisms; manage configurations with IaC where appropriate.
7. **Verify:** Run access-denied tests, inspect configs and logs, reconcile bills, measure quotas, and rehearse misconfigurations and incidents.
8. **Maintain:** Periodically review access permissions, owners, budgets, parent group structures, and expired exceptions.

**Do not start with a deeply nested tree.** Start with boundaries that have a clear purpose, establish simple conventions, and expand as workload count and control requirements grow. Every new branch must justify what governance, reliability, cost attribution, or lifecycle boundary it provides.

## 13. Practice Exercise and Solution Approach

### Scenario

A company runs on the cloud and currently has:

- A prod booking API with a database containing customer information.
- A dev booking API owned by the same team, frequently creating/deleting experimental resources.
- A prod payments service managed by another team, requiring strict access control.
- An observability dashboard and centralized audit log storage.
- Three short-lived sandbox environments for technology experiments.

Currently, all resources sit in a single governance scope. Dev developers have broad create/delete permissions. Costs cannot be broken down by product, and sandboxes are often left uncleaned.

**Requirement:** Propose a corresponding hierarchy on AWS, Azure, or Google Cloud; specify isolation boundaries, owner permissions, cost controls, and shared components.

### Solution Approach

1. Separate **Booking-prod**, **Payments-prod**, and **Booking-dev** into appropriate workload units at the account/subscription/project level. Add a dedicated staging unit as needs grow.
2. Place units under **Production**, **Non-production**, and **Sandbox** parent groups where supported. On Azure, consider using resource groups for application lifecycle management inside subscriptions.
3. Place **logging/security** in a dedicated scope. Clearly define who can send logs, who can read them, who manages policies, and who can delete logs per procedure.
4. Create **separate roles** for the Booking, Payments, Platform, and Security teams. Restrict developers to dev; use dedicated pipelines/roles for prod deployments. Unauthorized cross-access attempts must be denied.
5. Configure **owner, cost center, environment, data classification** metadata and per-product billing reports. Set budgets/alerts and reclamation deadlines for sandboxes.
6. Identify required shared networking, such as links to payment processors or internal networks. Evaluate routing, security, data transfer costs, and central-component blast radius.
7. Establish the baseline via automation and verify: complete audit logs, every new resource has an owner, no unauthorized cross-boundary access, auditable cost reports, and timely sandbox reclamation.

### Self-Check Questions

1. Why does separating Booking-prod from Booking-dev merely by resource naming fail to reduce blast radius?
2. What is the difference between an **AWS OU**, **Azure management group**, **Google Cloud folder**, and the workload deployment scopes beneath them?
3. Why should an **Azure resource group** not be treated as equivalent to an AWS account?
4. What benefits does centralizing permission and logging governance bring? When does a shared component become a single point of failure?
5. If leadership wants per-product cost reporting, which data and processes must be combined with the resource structure?
6. In the proposed design, who can deploy Payments-prod? How do you prove Booking-dev cannot modify Payments-prod?

A good cloud hierarchy is an **enforceable responsibility map**: it shows who owns each workload, who can operate it, which policies apply, how tightly data and networks are isolated, who is billed, and how far an incident can spread. From that map, the architecture team can select networking, compute, data, and deployment models aligned with business requirements and Well-Architected trade-offs.
