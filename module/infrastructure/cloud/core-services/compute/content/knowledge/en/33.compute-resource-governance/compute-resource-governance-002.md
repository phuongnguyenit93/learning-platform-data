# Organizing Resources by Account, Subscription, Project, and Environment

A cloud platform can host hundreds of applications, multiple engineering teams, multiple deployment environments, and thousands of compute resources. If everything resides in a single governance scope, operations teams struggle to restrict permissions, allocate costs, set quotas, control networking, and handle incidents without affecting other workloads. Conversely, splitting into too many small scopes without shared standards creates duplicated configurations, increases management difficulty, and drives up operational overhead.

Resource organization must establish clear boundaries across multiple levels:

- **Account or cloud account:** a top-level administrative boundary, typically tied to identity, billing, quotas, and resource scope.
- **Subscription:** a scope for managing resources, permissions, quotas, and billing in some cloud platforms.
- **Project:** a grouping of resources serving an application, workload, or business unit; in some clouds, this is the direct boundary for APIs, IAM, quotas, and billing.
- **Environment:** distinguishes development, test, staging, and production by trust level, data, access permissions, and deployment lifecycle.

Terminology and hierarchy order differ across providers. Do not assume account, subscription, and project share the exact same meaning on every cloud. Understand the platform's actual boundaries first, then design a model suited to your organization.

This lesson covers how to design a resource hierarchy, choose account/subscription/project/environment boundaries, separate production from non-production, manage identity and policies, organize networking and shared services, allocate costs, set quotas and budgets, and operate the compute resource lifecycle.

## 1. Why Organize Resources Across Multiple Levels?

An organization typically has multiple governance dimensions simultaneously:

- Who owns the workload?
- Who is allowed to create, modify, or delete resources?
- Which team or product owns the costs?
- Which workloads require security isolation?
- Which data is permitted in which region?
- Which environments are allowed to access production data?
- Which quotas need to be reserved for critical workloads?
- Which scope can an incident or change impact?

A sound structure answers these questions with enforceable boundaries. Organizing resources is not merely naming folders or grouping resources; it affects identity, networking, billing, quotas, policies, automation, and incident response.

### Key Objectives

1. **Isolation:** limit the blast radius when a misconfiguration, credential leak, or runaway workload occurs.
2. **Least privilege:** grant permissions by team, workload, and environment.
3. **Cost ownership:** define who is accountable for costs and budgets.
4. **Policy enforcement:** apply consistent guardrails for regions, networks, encryption, images, and resource types.
5. **Quota management:** prevent one workload from exhausting account capacity or quotas.
6. **Lifecycle management:** create, upgrade, archive, and delete resources through defined processes.
7. **Scalability of governance:** onboard new teams, applications, and environments without redesigning the entire structure.

### Organizing Too Coarse vs. Too Fine

| Organization Approach | Benefits | Risks |
|---|---|---|
| One account/project for everything | Easy to start, minimal setup | Broad permissions, hard chargeback, large blast radius |
| One scope per workload | Better isolation, easier permissions | Many configurations and quotas to manage |
| One scope per environment | Clear production/non-production split | Can be hard to manage with many applications |
| Hierarchy by org, product, and environment | Easy to apply policies at multiple levels | Requires ownership conventions and automation |
| Too many small scopes without standards | Superficial isolation | Drift, inconsistent policies, complex operations |

The goal is to choose just enough levels and boundaries to reflect security, cost, operational, and ownership requirements.

## 2. Distinguishing Account, Subscription, Project, and Environment

Concepts may be similar in intent yet differ in implementation.

| Concept | Common Role | Control Scope |
|---|---|---|
| Organization / tenant | Governance root of the organization | Identity, billing agreement, policy hierarchy |
| Account | Cloud account unit or billing/administrative boundary | IAM, quotas, resource visibility, billing depending on provider |
| Subscription | Container managing resources and billing in some platforms | RBAC, quotas, policy assignment, billing scope |
| Folder / management group | Group of accounts or subscriptions | Inheritance of policies, IAM, and governance |
| Project | Scope of a workload or group of services | API enablement, IAM, quotas, billing, and resource grouping depending on provider |
| Resource group | Group of resources with a shared lifecycle or ownership | Managing, deploying, and deleting resources within a subscription |
| Environment | Development, test, staging, production | Trust level, data class, release lifecycle, access policy |
| Resource | VM, disk, network, cluster, function | Configuration and permissions at the resource level |

### Account Is Not Synonymous with Environment

One account can contain multiple environments if the platform and risk model permit, but production and non-production should generally have stronger boundaries when:
- Production data is sensitive.
- Administrative permissions differ.
- Compliance or audit requirements apply.
- Independent quotas and billing are needed.
- Non-production has broader user access or automation.

### Project Is Not Always an Absolute Security Boundary

A project may provide separate IAM and quotas while still sharing top-level organization, networking, logging, billing, or policies. Identify what is truly isolated versus what remains shared.

### Environment Is an Operational Attribute

An environment can be represented by:
- A dedicated account or subscription.
- A dedicated project.
- A dedicated namespace or resource group.
- A label/tag on resources.
- A workspace or deployment stage.

Using an environment tag for reporting is helpful, but tags do not create isolation by themselves. Production and development can carry different tags while still sharing the same IAM roles, network, and quotas.

## 3. How Cloud Providers Structure Hierarchies

Naming and semantics vary by service. The examples below illustrate common models rather than a single mandatory hierarchy for every organization.

### AWS

A common model:
- AWS Organization is the multi-account governance root.
- Organizational Units (OUs) group accounts by function or environment.
- An AWS account is a critical boundary for IAM, quotas, billing visibility, and resource isolation.
- Regions and VPCs organize networking inside an account.
- Resource groups/tags support grouping resources and reporting.

Example:

~~~text
Organization
├── OU: Production
│   ├── Account: prod-payments
│   └── Account: prod-commerce
├── OU: NonProduction
│   ├── Account: dev-shared
│   └── Account: test-commerce
└── OU: Security
    ├── Account: audit-logging
    └── Account: security-tools
~~~

Service Control Policies can establish guardrails at the organization/OU/account level. IAM roles and resource policies further control permissions inside the account.

### Microsoft Azure

A common model:
- Microsoft Entra tenant holds identities.
- Management groups organize subscriptions.
- Subscriptions serve as administrative, quota, and billing scopes.
- Resource groups bundle resources with a shared lifecycle/ownership.
- Resources are VMs, VNets, disks, AKS clusters, or other services.

Example:

~~~text
Entra tenant
└── Management group: Company
    ├── Management group: Production
    │   ├── Subscription: prod-core
    │   └── Subscription: prod-data
    └── Management group: NonProduction
        ├── Subscription: dev
        └── Subscription: test
~~~

Azure Policy and RBAC can be assigned at multiple scopes and inherited downward according to platform semantics.

### Google Cloud

A common model:
- Organization is the root.
- Folders group projects by team, environment, or business unit.
- Projects are the key scope for resources, IAM, APIs, quotas, and billing.
- Resources reside within a project and its corresponding region/zone.

Example:

~~~text
Organization
├── Folder: Production
│   ├── Project: prod-payments
│   └── Project: prod-analytics
└── Folder: NonProduction
    ├── Project: dev-platform
    └── Project: test-payments
~~~

Organization Policies, IAM, and billing accounts support cross-project governance. Shared VPC allows workload projects to use centrally managed networks.

### Conceptual Comparison

| Need | AWS | Azure | Google Cloud |
|---|---|---|---|
| Organization root | Organization | Entra tenant / management hierarchy | Organization |
| Scope grouping | OU | Management group | Folder |
| Common workload boundary | Account | Subscription | Project |
| Resource grouping within scope | Tags/resource groups as needed | Resource group | Labels/folders do not replace projects |
| High-level guardrails | SCP | Azure Policy | Organization Policy |
| Identity | IAM and federation | Entra ID/RBAC | Cloud IAM |

Do not copy one cloud's hierarchy verbatim to another cloud. Map governance requirements onto the actual semantics of each platform.

## 4. Choosing Account or Subscription Boundaries

Dedicated accounts/subscriptions are typically appropriate when one or more of the following apply:

- Clear security or compliance boundaries.
- Teams require independent administrative permissions.
- Workloads have large or dedicated quotas.
- Costs must be tracked and charged back separately.
- Independent lifecycles exist.
- Dedicated network boundaries exist.
- Workloads have distinct trust levels.
- Blast radius must be limited.
- Production must be separated from sandboxes.

### When Can They Be Shared?

An account/subscription can be shared among workloads with:
- The same owner and trust level.
- The same policies and network boundary.
- The same billing owner.
- The same quota profile or sufficient existing quotas.
- The same lifecycle and operational processes.
- No requirement for account-level permission isolation.

For example, multiple microservices of a single product can share a production subscription while being separated by project/resource group, network segment, and workload identity if the risk model allows.

### When Must They Be Separated?

Consider dedicated scopes for:
- Production vs. non-production.
- Security/audit tooling.
- Shared networking.
- Regulated workloads or those handling sensitive data.
- Sandboxes with broad resource-creation permissions.
- GPU workloads with large quotas and billing.
- Independent teams needing separate administrative rights.

### Do Not Split Just Because Application Names Differ

Two services may share the same trust boundary and owner. Splitting every service into its own account/subscription creates networking, IAM, quota, and logging overhead. Base decisions on actual control requirements.

## 5. Choosing Projects and Resource Groups

Projects are typically well suited for grouping resources by:
- An application or product.
- A workload with its own owner and budget.
- An environment.
- A data domain.
- A compute pipeline.
- A group of APIs or services sharing the same lifecycle.

Resource groups are typically suited for grouping resources with a shared lifecycle—such as the VM, disk, NIC, public IP, and load balancer of a single deployment. Do not treat a resource group as the sole security boundary unless IAM and network policies are designed accordingly.

### One Project per Workload

Pros:
- IAM and quotas are easy to restrict.
- Billing is easy to allocate.
- API/service enablement has a clear scope.
- Resource inventory is easy to query.
- Can be deleted or archived by lifecycle.

Cons:
- Many projects increase management overhead.
- Shared resources require cross-project design.
- Deployment pipelines must manage multiple targets.
- Can hit project count quotas or service quotas.

### One Project for Multiple Workloads

Pros:
- Fewer scopes to manage.
- Easy to share networks and platform services.
- Less bootstrap configuration.

Cons:
- Hard to allocate costs if tagging is weak.
- IAM and quotas can become overly broad.
- A noisy-neighbor workload can impact others.
- Lifecycle and ownership become unclear if resources are unlabeled.

## 6. Organizing by Environment

Common environments:

| Environment | Purpose | Governance Characteristics |
|---|---|---|
| Development | Feature development | Flexible, synthetic data, low cost |
| Test / QA | Functional and integration testing | Test data, production-like config where needed |
| Staging / Preproduction | Release rehearsal and production parity checks | Tighter access controls and capacity |
| Production | Serving real users | High availability, security, audit, and change control |
| Sandbox | Technology experimentation | Strict quotas/TTL, no production data |
| Performance test | Load/stress testing | Clear load, time, and budget limits |

### Production vs. Non-Production

Production typically requires:
- Least-privilege access and change approvals.
- Classified and protected data.
- Backup, recovery, and monitoring.
- Controlled network ingress/egress.
- Dedicated quotas/capacity.
- Deployments with canary/rollback.
- Durable audit logs.

Non-production can be more flexible but still requires:
- No production secrets.
- No copying sensitive data without masking/tokenization.
- Automated off-hours shutdown where appropriate.
- Budgets and quotas.
- TTLs for sandboxes.
- Restricted network access to production.
- Image and patch baselines.

### Staging Does Not Need to Be Identical to Production

Staging should mirror production closely enough on factors under test—such as runtime, network path, identity pattern, storage class, autoscaling, and deployment process. However, it can use smaller capacity, masked data, and some mocked dependencies. Document differences clearly to avoid misleading test results.

## 7. Common Hierarchy Patterns

### Pattern A: Split by Environment First

Suited for organizations with multiple applications requiring strong production isolation.

~~~text
Organization
├── Production
│   ├── Account/Subscription: prod-platform
│   ├── Account/Subscription: prod-payments
│   └── Account/Subscription: prod-data
└── NonProduction
    ├── Account/Subscription: dev
    ├── Account/Subscription: test
    └── Account/Subscription: staging
~~~

The advantage is easy policy and access enforcement per environment. The drawback is that a single application has resources spread across multiple accounts/subscriptions, requiring pipeline and shared-services support.

### Pattern B: Split by Workload, Each with Its Own Environments

~~~text
Organization
├── Workload: payments
│   ├── prod account/project
│   ├── staging account/project
│   └── dev account/project
└── Workload: analytics
    ├── prod account/project
    ├── staging account/project
    └── dev account/project
~~~

Suited when teams own products end-to-end and need per-workload budgets and quotas. Production policies can be inherited from a parent group.

### Pattern C: Combine Environment and Business Unit

~~~text
Organization
├── Business Unit: Commerce
│   ├── Production
│   └── NonProduction
├── Business Unit: Data
│   ├── Production
│   └── NonProduction
└── Platform
    ├── Shared Services
    ├── Security
    └── Network
~~~

Suited for large organizations with multiple business units and a platform team. Avoid hierarchies that are overly deep and hard to understand.

### Criteria for Choosing a Pattern

- Number of teams and workloads.
- Level of owner autonomy.
- Security and data regulations.
- Billing and chargeback practices.
- Quotas and regions.
- Number of shared services.
- Automation capability.
- Account/subscription operational capacity.

No single pattern fits every company. Start from security and ownership boundaries, then optimize the structure to reduce overhead.

## 8. Designing Landing Zones and Baselines

A landing zone is a pre-configured cloud foundation ready for new workloads to deploy within shared guardrails. It typically includes:
- Account/subscription/project hierarchy.
- Identity federation and permission groups.
- Hub/spoke or shared networking.
- Centralized logging/auditing.
- Security baselines.
- Policy and compliance controls.
- Billing, budgets, and cost allocation.
- Image/registry and CI/CD.
- Backup and disaster recovery.
- Automation to provision new scopes.

### Account Factory or Project Factory

A factory workflow provisions new scopes from templates:
1. Receive workload request.
2. Identify owner, environment, data classification, and region.
3. Select OU/folder/management group.
4. Create account/subscription/project.
5. Assign baseline policies and IAM.
6. Connect networking/shared services.
7. Enable logging, monitoring, and security.
8. Create budgets, quotas, and tags.
9. Grant deployment role permissions.
10. Record inventory and owner.
11. Run compliance checks.
12. Authorize workload deployment.

Do not create accounts manually without an owner or outside the governance hierarchy. A factory prevents every team from provisioning scopes differently.

## 9. Identity and Access Permissions Across the Hierarchy

Access should be granted according to role and required scope.

### Common Permission Groups

- Organization/platform administrator.
- Account/subscription owner.
- Security auditor.
- Network administrator.
- Billing/cost analyst.
- Workload owner.
- Developer.
- CI/CD deployment identity.
- Read-only observer.
- Incident responder.

### Permission Inheritance

Some platforms allow assigning permissions at the organization/folder/management group level and inheriting them downward. This is convenient for baselines, but can grant overly broad access if large groups are assigned at high scopes.

Principles:
- Assign high-level permissions to small administrative groups.
- Assign workload permissions at the appropriate account/subscription/project.
- Separate read, deploy, operate, and administer permissions.
- Use short-lived workload identities/roles for automation.
- Avoid shared long-lived credentials.
- Review permissions periodically and when owners change.

### Production Access

Production should have dedicated access paths:
- Developers are not owners by default.
- CI/CD uses dedicated identities scoped strictly to the target workload.
- Emergency access is time-bound, audited, and approved.
- Read-only production access can be separated from write access.
- Never use personal accounts as the sole identity for automation.

### Service Identity

Each workload should have its own task-scoped service identity. For example, an image-processing worker only needs to read input objects and write to an output prefix; it does not need project admin rights or access to the billing database.

## 10. Policies and Guardrails by Level

Policies help enforce uniform rules across large scopes. They can control:
- Allowed regions.
- Allowed machine families/SKUs.
- Public IPs and public endpoints.
- Encryption requirements.
- Disk types and snapshot policies.
- Approved OS images.
- Mandatory tags.
- Network exposure.
- Logging and monitoring.
- Backup requirements.
- GPU quotas or accelerator types.
- Resource naming and locations.

### Policy Inheritance

Policies at the organization/folder/subscription/project level can inherit down to resources. Understand:
- Which policies are deny/explicit restrictions.
- Which policies only audit or alert.
- At which scope exceptions are granted.
- Who is authorized to create exceptions.
- Whether exceptions have an expiration date.
- How policy conflicts are resolved.

Do not create indefinite exceptions. Record owner, justification, risk, expiration time, and review evidence.

### Preventive vs. Detective Controls

- **Preventive:** blocks non-compliant resources before creation or update.
- **Detective:** detects issues after resources exist, generating alerts or tickets.
- **Corrective:** automatically remediates configuration or requires owner remediation.

For example, a policy can block creating VMs with public IPs in production; a scanner can detect unencrypted disks; a remediation workflow can add missing owner tags or open a ticket for the team.

### Policy as Code

Put policies in version control, review via pull requests, and deploy via pipelines. Test policies against:
- Compliant resources.
- Non-compliant resources.
- Permitted exceptions.
- Existing resources.
- Changes that might cause downtime.

High-level policy changes can affect hundreds of workloads. Rollouts should use canary scopes or audit mode before enforcement when supported by the platform.

## 11. Network Boundaries and Shared Connectivity

The resource hierarchy must align with network architecture.

Centrally managed components may include:
- Hub VPC/VNet.
- Transit gateway or peering.
- VPN/private connectivity.
- DNS resolvers.
- NAT/egress gateways.
- Firewalls.
- Private endpoints.
- Load balancers.
- Network flow logs.

### Hub-and-Spoke

A common model:
- The hub hosts shared network services and connectivity.
- Spokes host workloads by account/subscription/project.
- Routes, firewalls, and DNS control connectivity between spokes.
- Production and non-production can use separate hubs or distinct policies.

~~~mermaid
flowchart TB
    HUB["Network hub: firewall, DNS, VPN, egress"] --> PROD["Production spokes"]
    HUB --> NONPROD["Non-production spokes"]
    HUB --> SHARED["Shared services"]
    PROD --> P1["Payments workload"]
    PROD --> P2["Compute platform"]
    NONPROD --> D1["Development"]
    NONPROD --> T1["Test / staging"]
~~~

The hub must not become a bottleneck or single point of failure. Ensure HA, capacity, route segmentation, and change control processes.

### Do Not Share Networks by Default

Shared networks reduce duplication but can introduce:
- Lateral movement.
- Route conflicts.
- DNS coupling.
- Hard-to-allocate egress costs.
- Blast radius during firewall changes.
- Difficulty isolating regulated workloads.

Segment subnets, route tables, firewall policies, security groups, and private endpoints by trust boundary. Dedicated VNets/VPCs do not replace identity controls.

## 12. Shared Services and Ownership Responsibilities

Several services are consumed by multiple workloads:
- Central logging and auditing.
- Metrics/tracing.
- Container registries.
- Artifact repositories.
- DNS.
- CI/CD runners.
- Secrets management.
- Security scanning.
- Backup vaults.
- Network hubs.
- Shared Kubernetes platforms.

Define:
- Owning team for the service.
- Authorized consumers.
- Data classification.
- SLAs and quotas.
- Cost allocation.
- Incident escalation.
- Change/upgrade windows.
- DR strategy.

### Shared Services Account/Project

Create dedicated scopes for platform services and grant controlled access. Avoid giving shared services a single broad administrative identity across all workloads. Use cross-account roles or tightly scoped service identities.

### Shared Services Costs

Allocate using appropriate drivers:
- Log ingest by bytes/team.
- Registry storage by image/project.
- Network egress by flow or bytes.
- Backup by capacity/retention.
- CI/CD by build minutes or runner time.
- Kubernetes control/worker overhead by requests or usage.

If exact allocation is not feasible, explicitly record it as shared platform overhead and publish the policy.

## 13. Standard Naming, Tagging, and Metadata

Naming and tagging aid search, automation, and cost allocation. They do not replace IAM or resource hierarchy.

### Naming Convention

Names can include:
- Organization or business unit.
- Workload/service.
- Environment.
- Region.
- Resource type.
- Instance ordinal if needed.

Readable example: `commerce-payments-prod-vm-01`. Avoid packing volatile information into resource names; metadata belongs in tags/labels.

### Mandatory Tags/Labels

| Key | Purpose | Example |
|---|---|---|
| owner | Responsible person/team | platform-team |
| service | Workload name | payments-api |
| environment | Environment | production |
| cost_center | Cost center | CC-410 |
| business_unit | Business unit | commerce |
| data_classification | Data classification | confidential |
| managed_by | Management tool | terraform |
| lifecycle | Lifecycle type | long-lived |
| expiry_date | Cleanup deadline for temporary resources | 2026-12-15 |
| repository | Code/IaC source | payments-infra |

Use a dictionary of valid values and consistent lowercase rules. Do not put personal emails or secrets in tags.

### Tag Coverage

Track:
- Percentage of resources with an owner.
- Percentage of cost tagged with `cost_center`.
- Resources missing `environment`.
- Invalid tag values.
- Stale tags after a workload changes owners.
- Orphan resources no longer linked to a project/repository.

Policies can block or audit untagged resources. For services that do not support tags, use inventory mapping or parent scopes.

## 14. Billing, Budgets, and Cost Allocation

The resource hierarchy directly affects billing visibility. Accounts/subscriptions/projects often serve as the scopes shown in billing exports or cost management reports.

### Cost Allocation Dimensions

Costs can be aggregated by:
- Organization.
- Account/subscription/project.
- Business unit.
- Team/owner.
- Service/workload.
- Environment.
- Region.
- SKU/machine family.
- Cost center.
- Shared platform.

### Direct vs. Shared Costs

- Direct costs can be attributed directly to a resource/workload.
- Shared costs require an allocation driver.
- Unallocated costs must be reported and assigned to an owner for investigation.

Do not use an environment tag as proof that costs are accurately allocated if a resource is shared across multiple environments.

### Budgets by Scope

Budgets can be set per:
- Account/subscription/project.
- Team or cost center.
- Environment.
- Workload.
- Shared services.
- Migrations or performance tests.

Budget alerts can trigger at 50%, 75%, 90%, and forecasted overruns. Thresholds should align with criticality and billing cycles.

### Budgets Are Not a Production Kill Switch

When a budget is reached, production should not automatically shut down if doing so causes an outage or data loss. Actions should follow policy:
- Notify the owner.
- Investigate anomalies.
- Clean up dev/test resources.
- Restrict creating new sandboxes.
- Scale down non-essential workloads.
- Request a budget adjustment if demand is legitimate.
- Preserve SLOs and availability of critical services.

## 15. Quota and Capacity Management

Quotas limit the count or usage of resources within a scope. Examples:
- vCPUs per region.
- VM count per family.
- GPU quota.
- Public IPs.
- Disks/volumes.
- Network addresses.
- Managed Kubernetes clusters.
- API request rates.

Quotas may be set at the account, subscription, project, region, or service scope. Do not assume quotas are identical across scopes.

### Quota Allocation

A workflow:
1. Estimate baseline and peak demand.
2. Identify quotas by region/SKU.
3. Reserve headroom for failover and upgrades.
4. Partition quotas between production and non-production.
5. Assign owners and quota usage alerts.
6. Request quota increases ahead of high-load events.
7. Review unused quotas.

### Avoiding Quota Starvation

A development project can accidentally consume all GPU or vCPU quota in a subscription. You can:
- Separate production quotas.
- Use dedicated subscriptions/projects.
- Enforce policies restricting machine families.
- Apply internal quotas per team.
- Keep quota reserves for incidents/failover.

Provider quotas and internal quotas are two separate layers. Kubernetes `ResourceQuota` does not automatically increase cloud quotas; cloud quotas do not automatically cap requests inside a namespace.

## 16. Managing Compute Across the Hierarchy

A compute workload typically comprises multiple resources:
- VMs or node pools.
- Boot/data disks.
- NICs, subnets, and public/private IPs.
- Load balancers.
- Autoscaling groups.
- Container registries/images.
- Monitoring/logging.
- Backups/snapshots.
- IAM roles/service identities.
- Key management.
- DNS and network gateways.

When selecting account/project boundaries, account for dependencies. If a VM sits in project A while disk backups, keys, and logging live in project B, permissions and lifecycles must be clearly designed.

### Resource Dependency Map

Every workload should maintain an inventory with:
- Resource ID.
- Parent scope.
- Owner.
- Environment.
- Region/zone.
- Dependencies.
- Data classification.
- Managed-by.
- Lifecycle/expiry.
- Backup/DR classification.

### Compute Pools and Environments

Production node pools can use stable machine families, hardened images, and appropriate autoscaling minimums. Development can use smaller machine types, scheduled stops, and TTLs. Performance testing can temporarily raise quotas within an approved window and then auto-clean up.

Do not let temporary resources persist indefinitely simply because they sit inside a test project.

## 17. Safely Organizing Production and Non-Production

A secure structure typically includes:
- Separate identities or distinct roles per environment.
- Distinct network boundaries and egress policies.
- Separate secrets.
- Separate datasets or masked data.
- Centralized logging/auditing with controlled access.
- Separate budgets and quotas.
- Deployment pipelines with promotion gates.
- Backups/retention aligned with criticality.

### Never Use Production Secrets in Dev

Development/test should use separate credentials and keys. If production-like data is required, use masked or synthetic datasets. Never grant production permissions just to make testing easier.

### Promotion Between Environments

An artifact is built once, then promoted through dev → test → staging → production. Do not rebuild different binaries per environment without good reason. Config and secrets are injected per environment.

### Drift Between Environments

Track differences in:
- IaC modules/versions.
- OS images.
- Runtime/container images.
- Network routes/firewalls.
- IAM roles/policies.
- Quotas.
- Observability agents.
- Autoscaling.
- Encryption/backups.

Staging does not necessarily need production capacity, but it must reflect the critical characteristics under test. Uncontrolled drift can cause staging to pass while production fails.

## 18. Lifecycle of Accounts, Subscriptions, and Projects

Governance scopes also have a lifecycle.

### Creation

- Assign a business owner.
- Assign a technical owner.
- Select the parent scope.
- Attach baseline policies.
- Set up identity and networking.
- Enable auditing/logging.
- Create budgets/quotas.
- Enforce mandatory tags.
- Register in inventory.
- Verify compliance before deployment.

### Operations

- Review access periodically.
- Monitor budgets and quotas.
- Patch images/runtimes.
- Audit orphan resources.
- Check for policy drift.
- Test backup/restore.
- Manage exceptions and expirations.
- Re-verify owners when teams change.

### Decommissioning

Before closing an account/project:
1. Confirm owner and approvals.
2. Inventory resources and dependencies.
3. Verify retention/legal holds.
4. Back up or archive data that must be retained.
5. Migrate DNS, traffic, and workloads.
6. Revoke identities and secrets.
7. Delete resources in dependency order.
8. Confirm billing stops or check residual charges.
9. Save audit evidence.
10. Close the scope and update inventory.

Do not delete a project/account just because no VMs are visible. Disks, snapshots, IPs, logs, keys, reservations, or managed services may still exist and accrue charges.

## 19. Infrastructure as Code and Account Vending

Provisioning resource scopes via IaC ensures repeatable baselines and reviewable changes.

A pipeline may include:
- Request form or service catalog.
- Policy validation.
- Provisioning the account/subscription/project.
- Applying IAM, networking, and logging baselines.
- Creating budgets/quotas/tags.
- Registering inventory.
- Running compliance scans.
- Publishing the deployment target.

### Repository Structure

Can be organized into:
- Organization baseline.
- Account/subscription/project factory.
- Network/shared services.
- Workload infrastructure.
- Environment overlays.
- Policy as code.
- CI/CD pipelines.

Do not copy-paste configurations across dozens of projects. Use versioned modules with clear inputs and tests.

### Declarative Configuration Example

~~~yaml
workload:
  name: payments
  owner: commerce-platform
  business_unit: commerce
  data_classification: confidential
  environments:
    - name: development
      scope: nonprod-payments-dev
      region: region-a
      budget: dev-budget
    - name: production
      scope: prod-payments
      region: region-a
      budget: prod-budget
  guardrails:
    public_ip: false
    encryption_required: true
    approved_images_only: true
    owner_tag_required: true
~~~

This is an illustrative internal configuration example, not a standard schema of any cloud provider. Pipelines must map fields to the platform's actual APIs and policies.

### Do Not Let IaC Become a Bypass Path

If pipelines hold overly broad administrative permissions, users can deploy policy-violating resources via IaC. Control this with:
- Change reviews.
- Policy validation.
- Workload-scoped identities.
- Protected branches/environments.
- Drift detection.
- Pipeline auditing.
- Production approvals.
- Short-lived secrets/federated identity.

## 20. Multi-Team and Multi-Tenant Governance

As the organization scales, a clear ownership model is essential.

### Reference RACI

| Activity | Platform | Security | Finance/FinOps | Workload team |
|---|---|---|---|---|
| Hierarchy and landing zone | Responsible | Consulted | Consulted | Informed |
| IAM baseline | Responsible | Accountable | Informed | Consulted |
| Policy compliance | Consulted | Accountable | Informed | Responsible remediation |
| Network hub | Responsible | Consulted | Informed | Consumer |
| Budget | Consulted | Informed | Accountable | Responsible forecast |
| Workload deployment | Platform support | Guardrail | Cost visibility | Accountable |
| Resource cleanup | Automation | Audit | Cost review | Owner |
| Incident response | Shared | Shared | Informed | Responsible for app |

RACI should be tailored to the organization. Every resource scope must have a reachable owner.

### Multi-Tenant Platforms

If a platform serves multiple teams/tenants:
- Do not treat project names as identity boundaries.
- Use dedicated service identities.
- Apply quotas per namespace/project.
- Isolate networks and secrets.
- Record tenant attribution in job/resource metadata.
- Prevent tenants from accessing another tenant's billing or logs.
- Enforce policies for noisy neighbors and fair share.

## 21. Tracking Governance with Metrics

A governance dashboard should include:

| Metric | Meaning |
|---|---|
| Scope count by environment | Number of accounts/subscriptions/projects per environment |
| Owner coverage | Percentage of scopes/resources with an owner |
| Tag compliance | Percentage of resources with mandatory tags |
| Policy compliance | Percentage of resources meeting guardrails |
| Exception age | Age of policy exceptions |
| Budget utilization | Budget consumption level |
| Forecast overrun | Forecasted budget overrun |
| Quota utilization | Percentage of quota consumed |
| Orphan resource cost | Cost of resources lacking an owner/dependency |
| Unallocated cost | Costs not yet attributed |
| Access review coverage | Percentage of permissions reviewed |
| Drift count | Number of deviations from baseline |
| Decommission backlog | Scopes/workloads awaiting closure |

### Alerts

- New scope lacking an owner.
- Production scope missing audit/logging.
- Resource with policy-violating public exposure.
- Budget forecast exceeding threshold.
- Quotas nearing exhaustion.
- Expired exceptions.
- Declining tag coverage.
- Resources not managed by IaC.
- Inactive projects still incurring spend.
- Unused or overly broad access keys/roles.

Alerts should attach an owner and a concrete action. Do not merely send summary reports with no one responsible for acting on them.

## 22. Design Example for a Compute Organization

A company has three groups:
- Commerce runs payment and order APIs.
- Data runs batch analytics.
- Platform manages Kubernetes, networking, and logging.

A possible structure:

~~~text
Organization
├── Production
│   ├── prod-commerce
│   │   ├── payments project
│   │   └── orders project
│   ├── prod-data
│   │   └── analytics project
│   └── prod-platform
│       ├── kubernetes platform
│       └── observability
├── NonProduction
│   ├── dev-commerce
│   ├── test-commerce
│   ├── dev-data
│   └── staging-platform
└── Governance
    ├── security-audit
    ├── central-logging
    └── network-hub
~~~

### Rationale for Separation

- Production and non-production have different trust levels.
- Commerce and Data have different owners, quotas, and cost centers.
- Platform shared services have dedicated lifecycles and administrative rights.
- Security/audit needs centralized log storage with restricted access.
- The network hub is managed by the platform/network team.

### Implementation Steps

1. Create the organization hierarchy and parent policies.
2. Create production/non-production scopes.
3. Create workload scopes by owner and billing.
4. Create shared network/logging/security scopes.
5. Assign roles by team and environment.
6. Apply allowed-region, encryption, and public-access policies.
7. Assign production and non-production quotas.
8. Create budgets and cost tags.
9. Bootstrap IaC pipelines.
10. Deploy workloads through the promotion flow.
11. Verify policies, access, billing, and inventory.

You do not need to match the exact project count in this example. As workloads grow, split further when new requirements arise around permissions, quotas, billing, or isolation.

## 23. How to Decide Whether a Workload Needs Its Own Scope

Use a decision matrix:

| Question | If the Answer Is Yes |
|---|---|
| Different owner or billing owner? | Consider a separate project/account/subscription |
| Different trust level or data classification? | Consider a stronger boundary and dedicated policies |
| Need separate quotas or regions? | Split scope if current quota controls are insufficient |
| Need network isolation? | Design VPC/VNet/subnet/firewall; a separate account may be needed |
| Different lifecycle? | Separate project/resource group by lifecycle |
| Need independent audit/compliance? | Consider an account/subscription boundary |
| Noisy-neighbor or blast-radius risk? | Separate capacity and quotas |
| Only the application name differs? | Not sufficient reason to create a new scope |

### Decision Process

1. Identify the owner.
2. Identify data classification and trust boundary.
3. Identify required administrative permissions.
4. Identify billing and budgets.
5. Identify quotas and regions.
6. Identify network dependencies.
7. Identify lifecycle.
8. Choose the smallest scope level that satisfies requirements.
9. Apply baseline policies and tags.
10. Review once the workload is operational.

## 24. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Using environment tags instead of isolation | Dev can access production resources | Separate identities, networks, and scopes appropriately |
| One account for the entire organization | Overly broad blast radius and permissions | Split by trust boundary and owner |
| One account per service unnecessarily | Network/IAM and governance overhead | Group workloads sharing trust/owner |
| Projects without an owner | Nobody handles costs or incidents | Require owner metadata and reviews |
| Allocating costs by tags alone | Shared resources are miscalculated or omitted | Combine billing scopes and allocation drivers |
| Audit-only policies with no remediation | Violations persist | Add owners, SLAs, and corrective workflows |
| Non-expiring exceptions | Guardrails stay disabled indefinitely | Add expiration dates and reviews |
| Unsegmented shared networks | Lateral movement and blast radius | Route/firewall segmentation |
| Non-production using production secrets | Credential leaks and data exposure | Dedicated identities/secrets |
| Viewing quotas only at total account level | One team consumes all capacity | Internal quotas per team/workload |
| Creating scopes manually | Drift and missing baselines | Account/project factory |
| Deleting a project without inventorying | Data loss or residual charges | Dependency scan and decommission workflow |
| IaC using shared admin permissions | Pipelines become a policy bypass path | Federated identity and least privilege |
| Undocumented staging differences from production | Tests fail to reflect release risk | Drift reports and documented differences |

## 25. Governance Implementation Checklist

### Hierarchy and Ownership
- [ ] Organization/tenant and parent hierarchy defined.
- [ ] Account, subscription, and project semantics defined per provider.
- [ ] Every scope has a business owner and technical owner.
- [ ] Rules exist for selecting scope levels for new workloads.
- [ ] Production and non-production are separated according to risk.
- [ ] Shared services have owners and a consumer model.

### Identity and Policy
- [ ] Permission groups exist for platform, security, finance, and workloads.
- [ ] Production access is separately controlled.
- [ ] Automation uses workload identities/federation.
- [ ] Least privilege and access reviews are in place.
- [ ] Policies for allowed regions, encryption, public access, and images are applied.
- [ ] Exceptions have owners, justifications, and expiration dates.
- [ ] Audit logs are centrally stored and protected.

### Network and Data
- [ ] Network hub/spoke or equivalent model has an owner.
- [ ] Routes, DNS, firewalls, and egress are controlled.
- [ ] Shared networks do not allow unintended lateral access.
- [ ] Secrets are separated by environment.
- [ ] Production data is not arbitrarily copied to non-production.
- [ ] Backup, retention, and decommissioning are defined.

### Cost and Quotas
- [ ] Billing scopes map to workloads/teams.
- [ ] Mandatory `owner`/`service`/`environment`/`cost_center` tags exist.
- [ ] Shared costs have an allocation policy.
- [ ] Budgets by scope and workload have owners.
- [ ] Quotas by region/SKU are tracked.
- [ ] Headroom is reserved for production failover and upgrades.
- [ ] Alerts exist for budgets, forecasts, and quotas.

### Automation and Lifecycle
- [ ] Account/subscription/project factory exists.
- [ ] IaC modules are versioned and reviewed.
- [ ] Pipelines use dedicated identities and least privilege.
- [ ] Compliance scans and drift detection are in place.
- [ ] Sandboxes have TTLs or expiration dates.
- [ ] Decommissioning includes inventory, backup, and residual-cost checks.
- [ ] Governance dashboards have owners and remediation workflows.

## Conclusion

Organizing compute resources by account, subscription, project, and environment establishes governance boundaries for identity, policies, networking, quotas, billing, and lifecycles. Accounts/subscriptions generally suit broad administrative or isolation boundaries; projects group workloads by owner, APIs, quotas, and costs depending on the provider; environments express trust levels and release lifecycles. Tags help classify and allocate resources but do not replace IAM or network isolation. Landing zones and account/project factories ensure every new scope receives a consistent baseline. An effective hierarchy balances isolation against overhead, maintains clear owners, automates policies, tracks quotas and budgets, and verifies both dependencies and residual charges during decommissioning.
