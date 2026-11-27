# Drift Detection and Adopting Existing Resources

> **Chapter:** Infrastructure as Code  
> **Module:** CLOUD_ARCHITECTURE  
> **Scope:** Designing cloud application architectures from business requirements through networking, compute, data, and deployment models; balancing reliability, security, scalability, cost, and operations under Well-Architected principles.

## Learning Objectives

After this lesson, you will be able to:

1. Explain infrastructure drift and distinguish among out-of-band changes outside IaC, state discrepancies, and intentional unrecorded changes.
2. Identify the causes and impacts of drift on security, reliability, cost, recoverability, and environment reproducibility.
3. Use `plan`/`refresh` and appropriate verification mechanisms to detect discrepancies without accidentally applying changes.
4. Classify drift that should be kept, reverted, or codified into standard configuration.
5. Adopt (`import`/`adopt`) existing cloud resources into IaC state without creating duplicates or disrupting workloads.
6. Design ownership, state boundaries, import workflows, reviews, and safeguards for the transition.
7. Handle dependent resources, stateful/data-bearing resources, immutable fields, and provider APIs without full import support.
8. Establish a recurring process so drift has an owner, priority, remediation SLA, and verification evidence.

## 1. What is infrastructure drift?

Infrastructure as Code (IaC) describes desired infrastructure using source code and deployment tooling. The IaC tool compares the desired configuration against provider-observed state or recorded state, then proposes actions to bring the system into alignment.

**Infrastructure drift** is the divergence between managed configuration/intent and the actual state of resources. Examples:

- An engineer edits an ingress rule directly in the console to mitigate an incident without updating code.
- An administrator scales up database size or changes backup retention outside the pipeline.
- An emergency operation adds an IAM permission that is later forgotten.
- A resource is deleted manually while IaC state still records it as existing.
- A setting changes due to updated provider defaults or a new API version.
- A resource was created by an ad-hoc script and has no state owner.
- A provider or controller mutates an observed attribute after reconciliation.

Drift is not merely cosmetic. It can cause the next deployment to overwrite a necessary hotfix, delete a resource serving live production traffic, or leave overly broad permissions intact unnoticed. It also causes staging and production to diverge without documentation explaining why.

### 1.1. Three states to distinguish

| State | Meaning | Example |
|---|---|---|
| **Desired configuration** | Target configuration in the IaC repository/modules | Firewall allows HTTPS only from the gateway |
| **IaC state** | Record used by the IaC tool mapping resource addresses to real resources and tracked attributes | Resource address mapped to provider-issued ID |
| **Actual infrastructure** | Live state currently enforced by the provider | Firewall currently has an extra SSH rule from the internet |

In Terraform, state stores resource mappings and metadata—not a complete, immutable snapshot of every cloud attribute. Terraform `refresh`/`plan` queries the provider to compare; exact details depend on the provider, resource schema, version, and configuration.

### 1.2. Drift differs from code changes and state changes

- **Code change:** editing HCL/YAML/JSON in the repository; this records desired intent, though it may not yet be deployed.
- **State change:** state updated after refresh/import/move/apply; actual infrastructure has not necessarily changed.
- **Infrastructure drift:** actual infrastructure changed relative to what IaC expects or records.
- **Provider normalization/defaults:** the provider returns normalized or default values; a plan may show diffs even without an explicit manual edit.

A plan showing a diff is not necessarily human-caused drift. Understand computed/default attributes, eventual consistency, provider bugs, and how APIs represent data.

## 2. Causes and impact severity

### 2.1. Common sources of drift

| Cause | Example | Risk |
|---|---|---|
| Direct console/CLI edits | Opening a port, modifying routes, scaling replicas | Unreviewed, risk of being overwritten |
| Emergency procedures | Firewall or quota hotfix during an incident | Forgotten code update post-recovery |
| Multiple tools managing one resource | IaC and automation scripts editing the same resource | Controllers continuously overwrite each other |
| Unclear ownership | Two modules declaring the same IAM role | Unstable plans, state conflicts |
| Provider/API changes | Defaults or output schemas change after upgrades | Unwanted diffs, resource replacement |
| Auto-scaling/controllers | Provider dynamically changes capacity or replica count | IaC may revert dynamic values |
| Manual bootstrapping | Resources created prior to IaC to launch a project | No state owner, easy to duplicate |
| Corrupted/stale state | Old state, lost locks, wrong backend version restored | Tool may treat live resources as new |
| Multi-environment management | Console edits in production without updating modules | Dev/stage/prod gradually diverge |

### 2.2. Drift impacts multiple pillars

- **Reliability:** routes, subnets, database parameters, backup schedules, or autoscaling policies change unexpectedly.
- **Security:** security groups widen, IAM policies grant extra privileges, public endpoints are enabled.
- **Cost:** database tiers, NAT, storage retention, or log volumes grow unmonitored.
- **Operations:** responders do not realize live config differs from code; rollbacks fail to reproduce the environment.
- **Performance:** CPU/memory limits, cache sizes, connection pools, or autoscaling thresholds diverge.
- **Compliance:** encryption, retention, region, or audit settings fall out of policy compliance.

Not all drift carries the same severity. A descriptive tag or provider-normalized attribute has far less impact than disabled encryption or a database exposed to the internet. Classify by real impact, exploitability, blast radius, and urgency.

## 3. How to detect drift

### 3.1. The detect–assess–reconcile loop

~~~mermaid
flowchart TD
    A[Desired config + IaC state] --> D[Refresh / Plan / Drift scan]
    B[Actual cloud resources] --> D
    D --> E{Difference found?}
    E -->|No| OK[Record clean result]
    E -->|Yes| F[Classify drift and impact]
    F --> G{Approved desired change?}
    G -->|No, accidental| R[Reconcile actual to code]
    G -->|Yes, retain| C[Update code to accepted reality]
    G -->|Unknown| I[Investigate owner / audit / incident]
    I --> F
    R --> V[Review plan and validate]
    C --> V
    V --> A
~~~

A drift scan only detects discrepancies; it does not decide which configuration is right. Reconciliation requires an owner, review, and impact analysis.

### 3.2. Terraform plan and refresh-only

In Terraform, a typical inspection workflow uses:

~~~bash
# View proposed changes after refreshing information from the provider.
terraform plan

# Propose updating state only to match the provider-observed state.
terraform plan -refresh-only
~~~

`plan` typically refreshes managed resource metadata before generating a change plan, depending on configuration and flags. `-refresh-only` creates a plan to update state and outputs to match actual infrastructure without proposing remote object changes as a normal apply plan would. Exact behavior depends on version and provider.

Do not treat `apply -refresh-only` as harmless without review. It writes actual state into state and outputs, making the drifted state what Terraform records—without **updating desired configuration in code**. If the drift violates policy, merely refreshing state can silence the discrepancy signal on subsequent plans.

Example of a non-mutating check:

~~~bash
terraform init
terraform validate
terraform plan -refresh-only -out=drift-review.tfplan
terraform show drift-review.tfplan
~~~

Run inside the exact target workspace/backend and pinned provider versions. Plan files can contain sensitive data and require proper storage and access control. `validate` checks syntax/structure but does not prove live infrastructure has not drifted.

### 3.3. Differences among refresh-only, normal plan, and apply

| Command/action | Purpose | Modifies infrastructure from the plan? |
|---|---|---|
| `plan` | Compare desired config with state/provider and propose actions | No, planning only |
| `plan` with `refresh-only` | Preview state/output updates needed to match actual | No |
| `apply` with `refresh-only` | Record refreshed changes into state/outputs | Does not intend to modify remote resources, but modifies state |
| Normal `apply` | Execute plan to create/update/replace/delete resources | Yes |
| `plan` with `refresh=false` | Skip provider refresh during that plan per supported version behavior | Will not detect new provider drift in that run |

`refresh=false` is not a drift-checking method; it is used in specific scenarios to skip refreshing, meaning output may rely on stale state. Understand state and intent before using it.

### 3.4. Automated drift detection

Depending on tooling and cloud provider, options include:

- Scheduled `plan`/drift scan runs in periodic pipelines.
- Cloud provider config/asset inventory and policy evaluation services.
- Audit logs detecting edits by principals, console sessions, or external automation.
- Security posture/configuration management finding baseline violations.
- Event notifications when resources are modified/deleted or policies change.
- Cross-checking IaC repositories, state inventories, and cloud inventories.

Periodic drift scans do not replace event-driven alerts for sensitive changes. For IAM, public exposure, encryption, and network boundaries, use near-real-time policy guardrails where supported by the platform.

### 3.5. Limitations of drift detection

- Resource schemas/providers may not expose every field.
- APIs may exhibit eventual consistency or return normalized values.
- Some attributes are computed/ephemeral or controlled by autoscalers.
- Data sources reading information do not give IaC ownership of that resource.
- Resources outside state will not appear in that state's plans.
- Drift scans can hit API quotas, read permission limits, or backend locks.
- Provider upgrades can alter diffs even when operators made no live changes.

Therefore, a "no drift" report is meaningful only within the scope of scanned resources, fields, providers, permissions, and states.

## 4. Assessing drift before fixing it

### 4.1. Four questions before reconciling

1. **Where does actual differ?** Identify the resource, attribute, timestamp, and old/new values.
2. **Who or what automation made the change?** Check audit events, change tickets, deployments, and incident timelines.
3. **Which state is right per business/policy?** Code may be outdated; actual may be an approved hotfix.
4. **Which action is safe?** Revert actual, update code, import the resource, adjust ignore/lifecycle rules, or run a migration?

Never run `apply` simply because a plan shows diffs. First check for replacements, destroy/create pairs, force-new attributes, data loss, downtime, and dependency graphs.

### 4.2. Classification and decisions

| Drift type | Example | Typical remediation |
|---|---|---|
| Unauthorized/unsafe | IAM grants admin, DB made public | Handle via incident/security process; restore safe baseline, record audit |
| Needed emergency hotfix | Capacity scaled to handle load | Confirm owner, codify in code/module, then plan |
| Approved desired change | Subnet/route added per change request | Update IaC, review, and reconcile |
| Provider/computed difference | Normalized output field | Check provider schema/version and diff semantics |
| Controller-owned dynamic field | Replica count managed by autoscaler | Pick one source of truth; scope ownership/ignores properly |
| Unknown/unowned resource | Console-created resource with no clear owner | Inventory, classify, find consumers and owner before importing/deleting |
| Broken/missing state mapping | Real resource exists but state lacks it | Check backend/workspace, back up state, and import safely |

### 4.3. `ignore_changes` is not a cure-all for drift

Terraform supports lifecycle `ignore_changes` for attributes intentionally controlled by external systems. Example:

~~~hcl
resource "example_service" "api" {
  name     = "booking-api"
  min_size = 2
  max_size = 20

  lifecycle {
    # The autoscaler owns desired capacity in this example.
    ignore_changes = [desired_capacity]
  }
}
~~~

Use this only after identifying which controller owns the attribute, how values are monitored, min/max guardrails, and how to recover if the controller fails. Overly broad ignores blind drift detection; avoid `ignore_changes = all` as a shortcut to silence confusing plans.

### 4.4. Revert to code or adopt actual?

**Reconciling actual back to code** fits unauthorized, unsafe, or unapproved changes. For example, a publicly exposed SSH rule must be removed through incident/security workflows.

**Updating code to reflect actual** fits approved changes that represent the new intended state. For example, a database tier upgraded for planned growth: update the module and input variables before the pipeline resumes management.

In both cases, changes must go through review, planning, proper approval, and post-change validation. Never use a standalone state refresh to mask drift while the source of truth in code remains wrong.

## 5. Adopting existing cloud resources into IaC

### 5.1. Why import/adopt?

Many systems do not start with IaC. An organization may already have VPCs/VNets, subnets, route tables, security groups, production databases, buckets holding customer documents, IAM roles, KMS keys, certificates, clusters, load balancers, DNS records, or queues created manually.

Deleting and recreating them is usually unviable: it risks data loss, endpoint changes, service outages, broken integrations, or high costs. **Import/adoption** brings existing resources under IaC management by mapping a resource identity to a resource address in configuration and state.

Importing does not mean tooling magically knows the full desired configuration and generates a complete module. Typically you must write the resource declaration, import the ID, inspect actual attributes, fill out modules/variables, and iterate on the plan until no unexpected changes remain.

### 5.2. What does importing require?

Before importing, verify:

- Exact provider, account/project/subscription, and region.
- Unique resource ID per API/provider.
- Target workspace/backend/state intended as owner.
- Resource address in code, including module path or instance key/index.
- Required fields versus computed/default fields.
- Dependencies and child resources managed independently vs. inline with the parent.
- Who currently owns changes and which pipelines can write to the resource.
- Backups, exports, or rollback steps if the import or next apply hits issues.

Importing mutates state; some workflows also generate config or plan files. Perform imports in controlled branches/workspaces and back up state beforehand.

## 6. Safe adoption workflow

### 6.1. Overall workflow

~~~mermaid
flowchart TD
    A[Inventory existing resource] --> B[Confirm owner, account, region and consumers]
    B --> C[Choose state boundary and resource address]
    C --> D[Back up state and lock change window]
    D --> E[Write matching IaC resource configuration]
    E --> F[Import resource identity into state]
    F --> G[Run refresh-only and normal plan]
    G --> H{Plan has unexpected actions?}
    H -->|Yes| I[Reconcile arguments, provider schema and dependencies]
    I --> G
    H -->|No, no-op or approved diff| J[Review and approve ownership]
    J --> K[CI/CD manages resource going forward]
~~~

The goal is usually achieving a plan with zero remote resource changes after import (no-op) before handing steady-state management to the pipeline. Intentional diffs may be accepted if operations, downtime, and data impacts are fully understood.

### 6.2. Step 1 — Inventory and confirm owners

Catalog existing resources:

| Field | Example |
|---|---|
| Resource | Production database instance |
| Provider identity | Account/project + region |
| Resource ID | ID retrieved from provider API |
| Current owner | Data Platform Team |
| Consumers | Booking API, reporting jobs |
| Data/risk | Customer data, backups enabled |
| Dependencies | KMS key, subnets, security groups |
| Change authority | Approved infrastructure pipeline |
| Import target | Resource address in data module |
| Criticality | Tier 0 |

Never import a resource just because you found it in an account. It may belong to another service, vendor, platform team, or be temporary. Confirm the owner and establish an ownership contract before making changes.

### 6.3. Step 2 — Choose state boundaries

Each state should have sensible responsibility boundaries and blast radius. Boundaries can align with environments, domain/service ownership, lifecycle/permission boundaries, regions/cells, or change frequency.

Do not lump every company resource into a single state if one faulty plan/apply can impact the whole platform or demand overly broad permissions. Equally, do not fragment so finely that dependency and output wiring becomes unmanageable.

### 6.4. Step 3 — Declare the resource before importing

Illustrative Terraform example:

~~~hcl
resource "aws_s3_bucket" "customer_documents" {
  bucket = "company-customer-documents-prod"

  # Other attributes must be declared according to
  # current configuration and approved policies.
}
~~~

This is an illustrative AWS provider example; real configurations must match your exact provider version and resource schema. Incomplete resource blocks can cause plans to propose modifying attributes or adding side resources. For buckets, verify encryption, versioning, public access, lifecycle, ownership controls, and bucket policies.

### 6.5. Step 4 — Import via CLI

With the classic Terraform CLI workflow:

~~~bash
terraform import aws_s3_bucket.customer_documents company-customer-documents-prod
~~~

This command binds the resource ID to the resource address in the selected workspace's state. It does not automatically write the full resource configuration into `.tf` files; operators must declare the matching block and verify the plan.

Before running:

- Verify the target workspace and backend.
- Confirm provider alias, account, and region.
- Back up state and confirm backend locking is active.
- Ensure the resource address is not already managed in state.
- Verify the exact ID and provider import syntax.

After importing:

~~~bash
terraform state show aws_s3_bucket.customer_documents
terraform plan -refresh-only
terraform plan
~~~

`state show` reveals the attributes recorded in state. A normal `plan` must still be reviewed carefully because undeclared fields, defaults, policies, and dependent resources can produce diffs.

### 6.6. Step 5 — Declarative import blocks

Modern Terraform versions support `import` blocks in configuration, allowing imports to be reviewed as part of the plan/apply workflow:

~~~hcl
import {
  to = aws_s3_bucket.customer_documents
  id = "company-customer-documents-prod"
}
~~~

Declare the matching resource and `import` block, then run `plan` to inspect what Terraform will import and any other proposed actions. Apply only after review. Syntax, config-generation support, and behavior depend on the Terraform version; check docs for your exact version.

`import` blocks improve Git review and auditability. Once import completes, blocks can be kept or removed per repository conventions; ownership resides in state and resource configuration.

### 6.7. Step 6 — Reach an intentional no-op state

After importing, a plan may show:

- **No changes:** configuration and actual match within what the provider observes.
- **In-place update:** certain configuration attributes differ from actual; verify whether intentional.
- **Replace:** immutable/force-new attributes differ; risks creating a new resource and destroying the old one.
- **Destroy:** resource exists in state while configuration was removed or omitted.
- **Create:** a new resource block was not imported to the right address or lacks state mapping.

For resources holding production data, never accept replace/destroy during adoption without an explicit migration plan, backups, endpoint/cutover plan, and approval. No-op is a strong initial target because it proves IaC can manage the resource without mutating live infrastructure.

## 7. Dependent resources and import ordering

### 7.1. Importing along the dependency graph

~~~mermaid
flowchart TD
    VPC[VPC / VNet] --> SUB[Subnets]
    VPC --> RT[Route Tables]
    RT --> ASSOC[Route Associations]
    VPC --> SG[Security Groups]
    SUB --> DB[(Database)]
    SG --> DB
    KMS[KMS Key] --> DB
    KMS --> BK[Backup Vault]
    DB --> APP[Application Service]
    SUB --> APP
~~~

Usually, foundational and network resources are imported first, followed by dependent resources. However, some providers/resources have independent IDs and can be imported in parallel once state boundaries are clear. Never assume every API relationship appears in the Terraform dependency graph; a string ID reference does not always imply graph ordering.

### 7.2. One parent resource may have multiple child resources

A parent cloud resource may manage attributes inline or via independent child resources. Study the provider model:

- Are children managed inline in the parent or as standalone resources?
- Is there a risk of two resource blocks managing the same setting?
- Does importing the parent pull in all child state?
- During `plan`, will the provider treat omitted children as needing deletion?

For example, a route table may contain inline routes or separate route resources depending on provider/version. Never declare both ways of managing the same route when the provider expects a single owner.

### 7.3. State import is not resource cloning

Importing does not copy a database, bucket, or network to a new region. It simply binds a resource address in state to an existing resource ID. Creating a new environment requires modules/configurations and an appropriate apply. Distinguish import from:

- **Data source:** reading info about a resource that state does not own.
- **State move:** changing a resource's address in state without importing a new resource.
- **Resource replacement:** destroying the old resource and provisioning a new one.
- **Migration:** moving data/workloads to a target resource.

## 8. Adopting stateful and high-risk resources

### 8.1. Production databases

Before importing a database:

- Verify provider ID, engine/version, parameter group, subnet group, and security boundary.
- Record backups/PITR, encryption/KMS, retention, replication, and maintenance window.
- Identify which fields are immutable/force-new.
- Do not unexpectedly alter identifiers, storage encryption, or network access.
- Reconcile endpoints and connection strings so applications are never misrouted.
- Prepare a change window, state backup, and rollback plan.

A successful import does not guarantee the database is fully protected. Verify backups, restores, monitoring, and IAM continue operating.

### 8.2. IAM and security groups

Importing security resources can expose overly permissive policies or introduce diffs that lock out access. Ensure:

- At least one verified administrative/break-glass path remains intact.
- Actual policy documents are compared semantically against code, not just syntactically.
- Policies owned by service teams are distinguished from policies attached by platform/security.
- Rules do not close management ports or endpoints required during migration.
- Principals actively using resources are checked before removing statements or attachments.
- Auditing is enabled and security changes receive independent review.

### 8.3. Resources with internal state or external data

Queues, brokers, secrets, keys, certificates, buckets, and managed databases hold state or data directly impacted by replace/delete actions. Some resources hold sensitive values or cannot be re-exported:

- Plaintext secrets may not be readable from the provider after creation.
- Private keys may be non-exportable from HSM/KMS.
- Certificates and DNS records may be bound to multiple consumers.
- Queues carry backlogs; recreating a queue can lose messages.
- Buckets hold versions/object locks; destroy may be blocked or erase data.

If a provider cannot read back a secret value, never put in a placeholder and apply—doing so can unexpectedly rotate the secret. Use appropriate secret manager resources/data sources and workflows, separating metadata from secret material.

## 9. When import is unavailable or inappropriate

### 9.1. Provider lacks import support

If a provider resource does not support import, options include:

- Use a data source to reference the external resource without taking lifecycle ownership.
- Use another provider/API/CLI that supports adoption.
- Provision a new resource if the business permits migration and downtime.
- Wait for or contribute provider support while managing other resources.
- Partially manage via a wrapper module while documenting manual ownership clearly.

Never fabricate state manually by hand-editing state JSON when the tool/provider does not support it. State is critical data; manual edits can corrupt mappings, lineage, and metadata. Use only documented, backed-up state manipulation procedures.

### 9.2. Data source or managed resource?

| Declaration approach | Ownership | Best suited when |
|---|---|---|
| Managed resource + import | IaC owns lifecycle/config per provider schema | Team wants to manage changes to the resource |
| Data source | IaC only reads metadata, does not own lifecycle | Resource is owned by another team or provider |
| External reference/ID input | Consumer receives ID from an external contract | Ownership sits with the platform or another account |

Do not import everything into one state just because you can. For shared DNS zones, central KMS keys, or platform-owned base networks, application teams may only need data sources/references and a dependency contract.

### 9.3. Resources managed by another tool

If a Kubernetes operator, autoscaler, policy controller, or cloud service controls a resource, establish clear field ownership:

- Which tool is the source of truth for each attribute?
- Does the controller continuously overwrite changes?
- Does IaC manage the full lifecycle or only bootstrap?
- Should you use `ignore_changes` or split resources?
- Who handles drift introduced by the controller?

Two controllers writing to the same field create reconciliation loops, unstable plans, and unpredictable behavior.

## 10. Managing state safely during adoption

### 10.1. State is a sensitive asset

State can hold resource IDs, endpoints, outputs, and in some cases sensitive values or secrets. Protect state using:

- A remote backend with encryption and access controls.
- Versioning/backups and change history.
- Locking to prevent two pipelines from writing concurrently.
- Least privilege per workspace/project/environment.
- Auditing and controls over who can read state.
- Never committing state or plans containing sensitive data to Git.

Never keep local state on a personal laptop and treat it as canonical. Before adoption, confirm the exact backend and workspace; importing into the wrong workspace creates broken mappings or leads to duplicate resources when other pipelines run.

### 10.2. State backup and recovery

Before state changes:

1. Pause pipelines that might concurrently apply to the same state.
2. Verify backend, workspace, lock, and version.
3. Create and verify a state backup per backend procedure.
4. Record `serial`/`lineage` or state metadata required by the tool.
5. Perform reviewed imports or moves.
6. Verify state mappings and run a normal plan.
7. Re-enable pipelines after owner confirmation.

Restoring an old state can make the tool forget imported resources or revert to prior mappings while actual infrastructure has changed. When restoring state, compare actual resources and run a plan before any apply.

### 10.3. Never let multiple states manage the same resource

A cloud resource should have one lifecycle owner in a single state unless tooling provides an explicitly designed delegation model. Two states importing the same resource will fight over changes and deletions. Maintain a resource ID → state address inventory to detect duplicate ownership.

When transferring ownership across states/modules:

- Use state move/remove/import workflows or official version-appropriate mechanisms.
- Confirm the source state no longer manages the resource before the destination takes over.
- Avoid windows where both pipelines hold apply permissions.
- Run `plan` on both states before and after.
- Never destroy the resource during ownership transfer.

## 11. Operational workflow for handling drift

### 11.1. Severity and remediation SLAs

| Level | Example | Response |
|---|---|---|
| Critical | Public database, disabled encryption, unintended IAM admin | Immediate incident/security response; isolate or restore per runbook |
| High | Reduced backup retention, wrong production route, changed quota risking outage | Fast owner confirmation, controlled change |
| Medium | Capacity/parameter skew, missing tags/monitoring, non-baseline policy | Tracked ticket with deadline and review |
| Low | Descriptive metadata/tags or discrepancies with no runtime impact | Batch cleanup/standardization |

Severity depends on risk policy and business impact. Never blindly auto-revert every drift before verifying whether it was a legitimate mitigation during an active incident.

### 11.2. Drift register

Each finding should record:

| Field | Purpose |
|---|---|
| `finding_id` | Finding identifier |
| `resource_id`/`address` | Real resource and IaC address |
| `attribute` | Drifted field |
| `desired`/`actual` | Redacted desired and actual values |
| `detected_at`/`source` | Detection timestamp and tool |
| `change_actor` | Principal/audit event if identifiable |
| `severity`/`impact` | Severity level and scope of impact |
| `decision` | Revert, accept/update code, ignore with owner, investigate |
| `owner`/`due_date` | Accountable person/team and deadline |
| `validation` | Plan, test, audit, or policy check post-remediation |

Never store secrets, tokens, or raw private values in drift tickets. Record only necessary metadata or hashed/redacted representations.

### 11.3. Reconciliation process

1. Confirm the finding is not a false positive from provider normalization or dynamic fields.
2. Identify the actor/change ticket and resource owner.
3. Assess risk, blast radius, downtime, and data loss.
4. Decide whether code or actual is the source of truth.
5. Open a change/incident record and update branch.
6. Run `plan` in the target environment and review destroy/replace/force-new actions.
7. Apply with approval; use a maintenance window or staged rollout if needed.
8. Verify actual state, SLIs, security policies, and dependencies.
9. Close the finding with evidence and update runbooks if needed.

### 11.4. Preventing recurrence

- Restrict production console write access; use audited JIT/break-glass access.
- Enforce policy-as-code and organization/account guardrails.
- Run scheduled drift scans and alert on events touching sensitive resources.
- Standardize modules and paved roads to reduce the need for out-of-band edits.
- Require emergency changes to have follow-up code reconciliation and owners.
- Separate read/plan/apply permissions; route production applies through reviewed pipelines.
- Track recurring drift by team and resource type to fix root causes.

The goal is not to prohibit emergency console actions entirely. During an incident, direct action may be the fastest way to reduce impact. What is mandatory is logging, approval, and bringing accepted state back into the source of truth afterward.

## 12. IaC pipelines for drift and import

### 12.1. Periodic inspection pipeline

~~~mermaid
flowchart LR
    SCHED[Scheduled trigger] --> INIT[Init pinned providers]
    INIT --> VAL[Validate + policy checks]
    VAL --> PLAN[Refresh-only / normal plan]
    PLAN --> REPORT[Store redacted report]
    REPORT --> GATE{Critical drift?}
    GATE -->|Yes| PAGE[Notify owner / incident policy]
    GATE -->|No| TICKET[Create or update drift finding]
    PAGE --> REG[Drift register]
    TICKET --> REG
    REG --> FIX[Reviewed reconciliation change]
~~~

Scan pipelines should hold only necessary read permissions and appropriate state access. Never allow a drift-scan job to auto-apply changes. For production, separate plan from apply and mandate reviews for high-risk changes.

### 12.2. Resource adoption pipeline

~~~text
1. Resource owner requests adoption.
2. Verify account / region / resource ID / consumers.
3. Verify target backend, workspace and state lock.
4. Back up state and freeze conflicting automation.
5. Add resource declaration and import mapping in a branch.
6. Run validate and plan; inspect import and any diff.
7. Apply import only after approval.
8. Run refresh-only and normal plan again.
9. Require no-op or explicitly approved changes.
10. Merge and register the new IaC owner.
~~~

This is a reference workflow, not an executable script. Import syntax, commands, and behavior must match your specific Terraform/provider version and resource.

### 12.3. Required gates

- Correct account/project, region, and workspace.
- Resource ID is not already managed by another state.
- State backup and lock are ready.
- Import address exists in code without conflicts.
- Plan contains no unexpected destroys or replacements.
- Owner, change ticket, and approval are present.
- Security policies, backups, and monitoring are verified.
- Post-import normal plan is no-op or remaining diffs are explicitly explained.

## 13. Common mistakes

| Mistake | Consequence | Remediation |
|---|---|---|
| Applying immediately whenever a diff appears | Can destroy/replace production resources | Classify diffs and check dependencies/data impact |
| Planning only one small state | Misses unmanaged resources outside state | Combine inventories, audits, and policy scans |
| Refreshing state and assuming drift is gone | State adopts actual while code stays wrong | Update source of truth or reconcile actual |
| Importing and applying immediately | Incomplete config modifies or replaces resource | Reach no-op/approved plan first |
| Importing into wrong workspace/account | State manages resources in wrong scope | Verify backend, workspace, alias, and region |
| Two states importing the same resource | Competing updates or accidental destroys | Single lifecycle owner and inventory mapping |
| Importing ownerless resources | Creates ambiguous accountability | Confirm owner and consumers first |
| Overly broad `ignore_changes` | Masks serious drift | Ignore only controller-owned fields |
| Skipping state backups | Hard to recover mappings after errors | Back up/lock/version before changes |
| Hand-editing state JSON | Breaks lineage/schema or mappings | Use supported state/import commands |
| Ignoring force-new/immutable fields | Plan replaces resource causing downtime/data loss | Review replacements and migration plans |
| Skipping policy/backups when importing DB/buckets | Resource is managed yet insecure | Enforce security/backup acceptance criteria |
| Importing resources managed by another tool | Two controllers overwrite each other | Clarify ownership and source of truth |
| No scheduled scans | Drift persists and accumulates | Scheduled scans, audit events, and owner SLAs |

## 14. Hands-on exercise: adopting live cloud infrastructure into IaC

**Scenario:** A booking platform is running in production on the cloud. Its VPC, subnets, security groups, relational database, object storage, and IAM roles were created via console early on. The team wants to standardize on Terraform but cannot recreate the database or buckets because they hold live data. Several emergency edits were applied directly and remain unrecorded.

Design an adoption and drift management plan:

1. **Inventory:** list resource IDs, accounts/regions, owners, consumers, classifications, dependencies, and criticality.
2. **State boundaries:** split states across networking, data, and application/platform; explain permissions and blast radius for each state.
3. **Drift discovery:** define how to use `plan`/`refresh-only`, cloud audit logs, inventories, and policy scans; distinguish drift from computed/default fields.
4. **Classification:** categorize public exposure, encryption, IAM, backup, capacity, and tag drift by severity.
5. **Import selection:** choose resources suitable for lifecycle management; use data sources/references for shared platform resources where appropriate.
6. **Terraform config:** write a resource block/import mapping for a test bucket or security group; match exact provider version and ID.
7. **State safety:** back up state, verify locking, confirm workspace, and check for duplicate resource ownership.
8. **No-op gate:** run `refresh-only` and normal `plan`; explain every in-place update, replace, or destroy.
9. **Reconciliation:** decide which drift to revert, which to adopt, and update code with approvals and evidence.
10. **Operations:** define scan schedules, drift register, owner SLAs, critical alerts, and post-emergency follow-up.

### Sample adoption table

| Resource | Decision | Owner/state | Pre-import checks |
|---|---|---|---|
| VPC and subnets | Managed resource if network team transitions ownership | Network state / Platform | CIDRs, peering, routes, endpoints |
| Security groups | Managed resource | Network/app state per boundary | Ingress/egress, active connections |
| Production DB | Controlled import | Data state / Data Platform | Backups, encryption, parameters, endpoints, force-new fields |
| Customer document bucket | Controlled import | Data state / Data Platform | Objects/versions, policies, lifecycle, encryption |
| Shared IAM role | Reference only if owned by platform | Platform state | Trust policies and consumers |

### Sample drift register table

| Finding | Actual vs. desired difference | Level | Decision | Owner/evidence |
|---|---|---|---|---|
| SG-01 | Public SSH rule from the internet | Critical | Verify incident then remove per security process | Network owner, audit event |
| DB-02 | Backup retention below baseline | High | Restore policy after checking business retention | Data owner, plan + backup check |
| APP-03 | Desired capacity scaled by autoscaler | Medium/expected | Define controller ownership; avoid broad ignores | Service owner, autoscaler metrics |
| BUCKET-04 | Missing `cost-center` tag | Low | Update code/tags via standard change | Data owner, policy scan |

**Completion criteria:** Reviewers understand which resources are adopted, which are only referenced, which state owns each lifecycle, and which drift items are fixed or retained and why. The plan contains no unapproved destroys or replacements; backups, state mappings, policies, and production operations are verified.

## 15. Well-Architected assessment

| Pillar | Drift and resource adoption questions | Evidence |
|---|---|---|
| **Operational Excellence** | Are inventories, owners, scheduled scans, drift registers, and adoption pipelines in place? | Plan reports, change logs, no-op proofs, runbooks |
| **Security** | Is IAM/network/encryption drift detected and prioritized quickly? | Policy scans, audit events, access reviews |
| **Reliability** | Does adoption avoid replacements/downtime; does state have backups/locks; can resources restore? | State backups, dependency plans, restore tests |
| **Performance Efficiency** | Does capacity/scale/network drift alter latency or saturation? | Before/after metrics, load tests, capacity reviews |
| **Cost Optimization** | Are out-of-band, orphaned, or oversized resources identified with owners? | Cloud inventories, cost tags, rightsizing reviews |
| **Sustainability** | Are orphaned resources and redundant configurations cleaned up per lifecycle? | Resource inventories, utilization, deletion approvals |

IaC improves operations only when the organization maintains a source of truth, clear ownership, and change controls. Importing is not a win if state holds a resource that a pipeline might accidentally delete; drift scans are ineffective if findings have no owners or are blindly accepted without evaluating correctness.

## 16. Summary framework

- **Drift** is divergence among desired configuration, state, and actual infrastructure; distinguish true drift from provider defaults/computed fields and controller-managed attributes.
- **Detection is not remediation:** plans/scans produce evidence; owners evaluate and choose how to reconcile.
- **`refresh-only`** updates state to match actual; it neither updates code nor proves actual state is secure.
- **Import/adoption** maps existing resources into IaC addresses/state; it does not clone resources or auto-generate complete configs.
- **State boundaries and a single lifecycle owner** prevent multiple pipelines or states from competing over one resource.
- **A no-op plan or approved diff** is a critical gate before handing a resource to steady-state pipeline management.
- **Stateful/data-bearing resources, keys, IAM, and networking** require special review because replacements or policy shifts can cause data loss or outages.
- **Drift registers, audits, scheduled scans, and post-emergency follow-ups** keep code and actual infrastructure aligned over time.

Drift detection and adopting existing resources are two sides of the same ownership problem: the organization must know what is running, who is accountable, and which configuration is authoritative. When inventory, state, code, and change processes connect cleanly, IaC can safely take over live infrastructure while ensuring new discrepancies are caught, assessed, and resolved before becoming incidents.
