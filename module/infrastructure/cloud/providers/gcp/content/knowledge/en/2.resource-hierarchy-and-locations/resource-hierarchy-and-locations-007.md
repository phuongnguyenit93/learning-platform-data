# Labels, tags, and resource lifecycle management on Google Cloud

> **Chapter:** Resource Hierarchy and Locations  
> **Learning scope:** The **CLOUD_PROVIDERS_GCP** module covers organizing projects, IAM, and VPCs; choosing Compute Engine, GKE, Cloud Run, storage, and databases; securing resources, automating releases, and monitoring reliability and costs. In this chapter, labels, Resource Manager tags, and lifecycle management workflows are the tools that enable consistent resource governance across those scopes.

## Learning Objectives

After this lesson, learners will be able to:

1. Explain the differences between **labels**, **Resource Manager tags**, and **Compute Engine network tags**.
2. Build a metadata convention usable for searching, classification, cost allocation, and policy enforcement.
3. Describe **TagKey**, **TagValue**, **TagBinding**, tag inheritance, and their relationship to organizations, folders, and projects.
4. Analyze creating, operating, modifying, retaining, retiring, and deleting resources safely.
5. Practice reading labels and managing selected labels via the Google Cloud CLI; verify alignment with permissions, services, and existing policies.
6. Design a governance workflow for dev, staging, and production environments with cost and security controls.

## 1. Why do cloud resources need clear metadata and lifecycle management?

Imagine an enterprise with hundreds of VMs, buckets, Cloud Run services, and databases across multiple projects. An operations on-call team receives a cost spike alert and needs immediate answers:

- Which resources belong to the payments system?
- Which resources are production, and which are only for testing?
- Who is responsible for approving changes or deleting resources?
- Which resources require stricter protection policies?
- Which experimental resources have expired yet are still generating charges?
- Can we determine the impact when a project, region, or service is changed?

Resource names and project IDs help, but they are not enough for long-term governance. You need **standardized metadata**, **permission boundaries**, and **lifecycle workflows**. Google Cloud provides several mechanisms; they do not replace one another.

A helpful mental model:

~~~mermaid
flowchart LR
    H["Resource hierarchy: organization / folder / project"] --> R["Cloud resources"]
    L["Labels: classification and reporting"] -. "Attach metadata where supported" .-> R
    T["Resource Manager tags: classification for policies"] -. "TagBinding and inheritance" .-> R
    N["Network tags: target selection for VM firewall/routing"] -. "Compute Engine scope" .-> R
    P["Lifecycle: create → operate → decommission"] --> R
~~~

Attaching metadata does not automatically make an application secure, lower bills, or delete old resources. The organization must establish usage rules for metadata and appropriate enforcement tooling.

## 2. Labels: lightweight metadata for classification and cost allocation

A **Label** is a key–value pair attached to Google Cloud resource types that support labels. For example, a VM might carry:

~~~yaml
labels:
  environment: production
  application: checkout
  team: payments
  cost_center: fin001
  managed_by: terraform
~~~

Here, **environment=production** describes intended usage, **team=payments** identifies the operating team, and **cost_center=fin001** supports cost analysis.

### 2.1. What are labels used for?

| Need | How to leverage labels | Limitations to remember |
|---|---|---|
| Search and inventory | Filter resources with application=checkout or environment=dev | Only supported and labeled resources carry searchable data |
| Cost allocation | Group billing data by cost_center, application, or team | Depends on each service's label export support and when charges accrue |
| Operational reporting | Identify accountable unit, classify resources | Labels do not replace IAM, Cloud Monitoring, or a CMDB |
| Cleaning up test environments | Use expires_on or lifecycle=temporary to populate review lists | Labels do not automatically delete, stop, or release resources |
| Enforcing naming standards | Validate completeness of required labels via pipelines | Requires verification/remediation steps since not all resource types support labels |

**Core point:** labels serve **description and governance**. Attaching **environment=production** does not automatically make a resource production-safe; IAM, backups, networking, and release controls must still be configured.

### 2.2. Conventions for keys and values

Exact rules depend on the resource type/API, but a safe, broadly compatible convention across services is:

- Short, lowercase, descriptive keys such as **environment**, **application**, **team**, **cost_center**.
- Values from a bounded vocabulary: **production**, **staging**, **development** instead of mixing variants like **prod**, **prd**, **production**.
- Use lowercase letters, digits, hyphens, or underscores as supported by the service; avoid spaces and special characters in your shared convention.
- Many APIs limit key/value length and maximum number of labels per resource. Check target resource limits before bulk application.
- Never place passwords, keys, tokens, personal information, or sensitive data in keys/values. Metadata may be visible to many admin roles and included in reports.

**Example standardized vocabulary:**

| Key | Sample values | Meaning |
|---|---|---|
| environment | development, staging, production | Deployment environment |
| application | checkout, catalog, inventory | Service or application |
| team | payments, platform, data | Accountable team |
| cost_center | fin001, ops002 | Cost center |
| managed_by | terraform, pipeline, manual | How the resource is managed |
| lifecycle | permanent, temporary | Expected lifecycle classification |
| expires_on | 20261231 | Review date; YYYYMMDD format per internal convention |

The value **expires_on=20261231** has no automatic deletion effect. Another process must read the expiration date, confirm with the owner, check dependencies, and obtain approval if needed.

### 2.3. Labels are not automatically inherited down the resource tree

Suppose folder **commerce** contains project **shop-prod**. Attaching **team=payments** to the project does not mean every bucket, VM, and service inside the project automatically receives that label. Distinguish:

- **Project labels:** metadata on the project itself.
- **Resource labels:** metadata on each label-supporting resource.
- **Cost reports:** may contain separate fields for project and resource labels, represented differently depending on data source and service.

Therefore, if reports need breakdown by resource labels, pipelines or infrastructure modules must attach labels at the **right level**. Never assume “labeling the project once gives all resources the same labels.”

## 3. Resource Manager tags: metadata for policy enforcement

In Google Cloud, **Resource Manager tags** are also key–value pairs, but with a dedicated structure and integration with **IAM Conditions**, **Organization Policy**, and certain other supported features. They are useful when an organization wants to apply conditional policies based on resource classification.

### 3.1. Three components of a tag

| Component | Role | Conceptual example |
|---|---|---|
| **TagKey** | Defines the governance attribute; created under a supported parent such as an organization or project | environment |
| **TagValue** | A value defined under a TagKey | production, development |
| **TagBinding** | Associates a TagValue with a supported resource | Binding environment/production to project shop-prod |

These are not merely arbitrary strings. TagKey and TagValue are resources with their own identifiers, and TagBinding represents the association with a target resource. In admin tools, they can appear in full names or IDs such as **tagKeys/…**, **tagValues/…**. Human-readable display names and technical identifiers should not be confused.

Example:

~~~text
Organization
  └── TagKey: environment
        ├── TagValue: development
        ├── TagValue: staging
        └── TagValue: production

Project: shop-prod
  └── TagBinding → environment/production
~~~

### 3.2. Tag inheritance along the resource hierarchy

For supported resources, features, and evaluation methods, tags bound to an organization, folder, or project can be **inherited** by child resources. This mechanism differs from standard labels.

~~~mermaid
flowchart TD
    O["Organization"]
    F["Folder: commerce"]
    P["Project: shop-prod"]
    VM["Compute Engine: payment-vm"]
    CR["Cloud Run: checkout-api"]
    TG["TagBinding at project: environment=production"]
    O --> F --> P
    P --> VM
    P --> CR
    TG -. "Directly bound" .-> P
    P -. "Inherits effective tag when supported" .-> VM
    P -. "Inherits effective tag when supported" .-> CR
~~~

If an IAM policy has a condition checking effective tags, binding a tag at the project level lets the policy apply consistently to child resources without attaching a separate binding to every service. However:

1. The resource type must **support tags/tag bindings** or the feature's inherited-tag evaluation.
2. The policy using the tag must **actually be created and applied**; a tag by itself neither grants nor denies permissions.
3. You must check **precedence when both inherited tags and directly bound tags exist** for the same key in your scenario.
4. Appropriate permissions are needed to manage TagKey, TagValue, TagBinding, and parent resources—do not assume Editor on the project suffices.

### 3.3. Example of tags in an IAM condition

A conditional IAM policy can use an expression similar to the following example to check a classification tag:

~~~cel
resource.matchTag('123456789012/environment', 'production')
~~~

**Illustrative meaning:** the condition checks a tag key with namespace **123456789012/environment** and value **production** on the resource within IAM-supported context. The numeric string is an example and must be replaced with the actual namespace.

Before using in a live system, determine: the permissions being granted, target resource types, policy attachment point, service tag support, tag management permissions, and how to test with a limited-privilege account. A single condition does not guarantee the entire system is protected.

### 3.4. Using Resource Manager tags for Organization Policy

An organization can design policies with tag-based conditions, such as classifying production resources to enforce stricter governance constraints. Not every constraint or service supports the same form of tag-based condition. Before deploying:

- Verify the **specific constraint** supports conditions or handles tags as intended.
- Check whether the policy is attached at the organization, folder, or project; determine scope and inheritance.
- Assess impact on running resources and dev/staging environments.
- Pilot the policy in a limited scope, with a rollback path and an accountable owner.

A tag **data_classification=restricted** is only a classification signal; the organization must still configure encryption, IAM, networking, data residency, and corresponding information-handling processes.

## 4. Distinguishing Resource Manager tags from Compute Engine network tags

In Google Cloud documentation and interfaces, the word **tag** can refer to several different mechanisms.

**Compute Engine network tags** are strings attached to VMs, commonly used as target selectors for certain firewall rules and routes. They are not Resource Manager TagKey/TagValue/TagBinding, not labels, and should not be used for cost allocation.

For example: a VM has the network tag **web-frontend**, and a VPC firewall rule can use that network tag to select the target VM group. Actual traffic control depends on firewall rule configuration, rule priority, traffic direction, and related network rules. Attaching a network tag by itself does not mean a port is open.

| Criterion | **Labels** | **Resource Manager tags** | **Compute Engine network tags** |
|---|---|---|---|
| Data form | Key–value pairs attached directly to supported resources | TagKey/TagValue and TagBinding | Tag strings on VMs |
| Primary purpose | Classification, inventory, cost reporting | Classification used in supported policies | Selecting VMs for supported firewall rules/routes |
| Hierarchy inheritance | Not automatically inherited | Supports inheritance in supported contexts | Not inherited via organization/folder/project |
| Value set management | Mainly via conventions and custom tooling | Values defined under TagKey | Managed via VM config and conventions |
| IAM/Org Policy impact | Not an access-control mechanism | Can participate in supported policy conditions | Not a Resource Manager tag for IAM evaluation |
| Used as billing labels | Possible, depending on service and export data | Not a direct substitute for billing labels | Not used for cost allocation via billing labels |

Beyond traditional network tags, modern firewall features may support **secure tags** or other target identifiers. When writing network rules, always confirm the exact **tag type** supported by that firewall product; never generalize across terms to infer identical behavior.

## 5. Connecting to organization, folder, project, and resource location

A cloud governance model is designed in layers:

- **Organization / folder:** separates governance units and establishes permissions and policies at appropriate levels.
- **Project:** critical boundary for APIs, quotas, billing, and many IAM permissions; typically split by environment or product.
- **Resource location:** region/zone or service-specific location, determining latency, data residency, redundancy, and part of cost.
- **Labels/tags:** clarify owner, environment, application, classification, and policy conditions.
- **Lifecycle workflow:** governs when resources are created, tested, modified, retained, retired, or deleted.

Governance example:

~~~text
Organization: example-company
  Folder: commerce
    Project: commerce-dev
      Effective Resource Manager tag: environment=development
      VM labels: environment=development, team=payments
    Project: commerce-prod
      Effective Resource Manager tag: environment=production
      Cloud Run labels: environment=production, application=checkout
      Cloud SQL: region per HA/data residency design
~~~

**Note:** deployment location **is not inferred from labels or tags**. Attaching **region=asia-southeast1** does not move a resource to that region. Location constraints must be enforced through resource creation configs, appropriate organization policies, and pipeline checks.

Similarly, a production tag does not replace separating IAM permissions or separating production projects from test environments. Permissions inherited from organization/folders must be reviewed independently of labels/tags.

## 6. Designing a consistent metadata schema

### 6.1. Pick a small but high-value standard set

Start with questions that come up constantly: **who owns it, which app does it serve, which environment is it, who pays for it, how was it created, when should it be reviewed?**

Example enterprise convention:

| Field | Recommended mechanism | Sample requirement |
|---|---|---|
| environment | Label and Resource Manager tag if needed for policies | development / staging / production |
| application | Label | Application code registered in internal catalog |
| team | Label | Operating team code with an accountable owner |
| cost_center | Label | Valid cost center code |
| managed_by | Label | terraform / pipeline / manual |
| lifecycle | Label | permanent / temporary |
| expires_on | Label for temporary resources | Review date in YYYYMMDD format |
| data_classification | Resource Manager tag if used in policies | public / internal / restricted |

None of the key/value pairs above are mandatory by default in Google Cloud. This is a **sample convention**; organizations should tailor it to supported resources, data standards, and enforcement tooling.

### 6.2. Preventing metadata drift

Metadata drift happens when tags/labels on resources no longer reflect reality. For instance, a VM transfers from the platform team to payments yet still carries **team=platform**; next month's bill will be misallocated.

A preventive workflow:

1. **Authoritative source:** define the key/value catalog and owners in managed configuration.
2. **Enforce at creation:** pipelines or IaC templates check all applicable labels before creating resources.
3. **Periodic audits:** inventory resources missing labels, carrying invalid values, or lacking an owner.
4. **Change approval:** when changing team/cost center, synchronize billing info, runbooks, and labels.
5. **Track exceptions:** log resources that do not yet support labels/tags or cannot yet be updated, along with an assignee and due date.

Do not automatically assign **production** merely because a resource lives in a project with **prod** in its name. Values should come from authoritative config and verifiable governance decisions.

### 6.3. Treating “metadata as a contract”

You can define a simple data contract:

~~~yaml
# Internal convention, not a Google Cloud API manifest
required_labels:
  environment: [development, staging, production]
  team: [platform, payments, data]
  managed_by: [terraform, pipeline, manual]

conditional_labels:
  lifecycle_temporary_requires: [expires_on, team]

resource_manager_tag_keys_for_policy:
  environment: [development, staging, production]
  data_classification: [public, internal, restricted]
~~~

This contract can be enforced via IaC checks, CI/CD configs, inventory rules, and approval workflows. It must allow well-justified exceptions because **label/tag support varies by service**.

## 7. Resource lifecycle: from proposal to deletion

Lifecycle governance is more than "create and delete." A resource can pass through stages: **proposal → provisioning → operation → change/scaling → retirement → required data retention → deletion/verification**.

~~~mermaid
flowchart TD
    A["Proposal: purpose, owner, environment, cost"] --> B["Design: IAM, region, data, backup"]
    B --> C["Create via API / IaC / pipeline"]
    C --> D["Attach labels, tags, logging, and monitoring"]
    D --> E["Operate and audit drift/cost"]
    E --> F{"Still needed?"}
    F -- "Yes" --> G["Update versions, configs, permissions"]
    G --> E
    F -- "No" --> H["Assess dependencies, retention, and recovery"]
    H --> I["Disable/scale down when appropriate"]
    I --> J["Controlled deletion"]
    J --> K["Verify data, access, billing, and inventory"]
~~~

### 7.1. Proposal and design phase

Before provisioning, define:

- **Purpose and owner:** which system uses it, who is on call, who approves costs and changes.
- **Organizational scope:** which project it belongs to, whether IAM/Organization Policy permits it.
- **Location:** region/zone or storage location matching latency, data residency, HA, and recovery requirements.
- **Service model:** whether Compute Engine, GKE, Cloud Run, or a data service fits the workload profile.
- **Security plan:** service account, least privilege, private vs. internet access, secrets, and logs.
- **Operational targets:** uptime/SLO, RTO, RPO, data retention period, and expected budget.
- **Metadata:** applicable labels, Resource Manager tags needed for policies, and review date.

For experimental resources, set an **expiration date and owner at request time**. Ownerless resources are notoriously difficult to approve for deletion later.

### 7.2. Provisioning phase

Prefer **Infrastructure as Code** or reviewed pipelines. Resource creation configs should attach metadata alongside security and location attributes. That way, reviewers immediately see the rationale and owner right in the code change.

Conceptual Terraform example:

~~~hcl
locals {
  common_labels = {
    environment = "production"
    application = "checkout"
    team        = "payments"
    cost_center = "fin001"
    managed_by  = "terraform"
  }
}

# For each resource type that supports labels, pass local.common_labels
# into the labels attribute of that resource.
# Resource Manager tags are declared using separate resources and bindings.
~~~

This is an **illustrative metadata structure snippet**, not a complete Terraform configuration for creating infrastructure. When applying, check the provider, resource schema, and version used. For resources that do not support labels or Resource Manager tags, the pipeline must record them in a tracked exception list.

### 7.3. Operations phase

Periodic reviews should answer:

- Are any production resources missing an owner or cost_center?
- Do tags accurately reflect data classification, environment, and active policies?
- Are any services no longer receiving traffic yet still incurring charges for instances, storage, or networking?
- Are backup, restore, log, alert, and quota configs still aligned with current load and SLO targets?
- Are any temporary resources past their review date?
- Have out-of-band changes outside IaC caused live state to drift from standard config?

Inventory reports should not automatically delete every resource labeled **lifecycle=temporary**: there may still be data to preserve, network dependencies, or running analytics jobs.

### 7.4. Change and migration phase

Changing owner, team, or environment requires updating labels/tags and supporting systems. **Region migration** is not merely editing a label: many services require creating new resources, copying data, updating endpoints, verifying connectivity, and cutting over traffic.

Changes to tags used in IAM/Organization Policy must be evaluated as **security policy changes** because a binding can affect permission conditions or resource constraints. Record who made the change, target object, reason, and expected impact.

### 7.5. Retirement and deletion phase

Before deleting, distinguish three separate decisions:

1. **Application no longer in use:** stop traffic or jobs; data and configs may still need to be retained.
2. **Running compute no longer needed:** stop, scale down, or delete compute resources depending on service and technical limits.
3. **Data eligible for disposal:** must satisfy retention windows, audit requirements, backup policies, contracts, and dependencies.

A verification sequence:

| Step | Content | Evidence to retain |
|---|---|---|
| Confirm owner | Who approved retirement and effective from when? | Ticket/PR with accountable owner |
| Check dependencies | Are DNS, URLs, VPCs, IAM, batch jobs, databases, buckets, or other services still referencing it? | Dependency list and test results |
| Check data | Are there retention policies, holds, backups, RTO/RPO, or archival mandates? | Decision on data to preserve |
| Block new creation | Halt resource-creation flows or transactions per procedure | Deployment/schedule/config change record |
| Revoke access | Remove unneeded roles, secrets, keys, bindings; avoid impacting shared systems | IAM and secret update history |
| Decommission and delete | Execute in dependency order with a recovery option if needed | Pipeline or ticket logs |
| Confirm completion | Inventory, billing status, monitoring, alerts, and related resources | Post-deletion report |

Never assume every resource has **soft delete** or can be restored within a fixed number of days. Recovery mechanics, retention locks, backups, and reversibility depend on the service and configuration. For critical data, **test restoration before deciding to delete**.

## 8. Cost: connecting labels with FinOps

Labels are valuable for **FinOps**: breaking down cloud spend by consumer, application, and budget. Cost data can be exported via **Cloud Billing export to BigQuery** and aggregated by metadata present in the records.

Three limitations to understand:

1. Not every service's charges or billing line items carry equally granular **resource labels**.
2. Changing a label today generally does not retroactively rewrite historical cost data.
3. Policy tags should not be assumed to serve as cost-export labels; inspect the actual billing export schema in use.

### 8.1. Example cost analysis by cost_center

Illustrative query on a **Cloud Billing detailed/standard export** table containing a repeated `labels` field:

~~~sql
-- Replace BILLING_PROJECT.BILLING_DATASET.EXPORT_TABLE with the actual export table.
-- Report costs grouped by the cost_center label when records have that label.
SELECT
  COALESCE(
    (SELECT label.value
     FROM UNNEST(labels) AS label
     WHERE label.key = 'cost_center'
     LIMIT 1),
    'unallocated'
  ) AS cost_center,
  ROUND(SUM(cost), 2) AS gross_cost
FROM `BILLING_PROJECT.BILLING_DATASET.EXPORT_TABLE`
WHERE usage_start_time >= TIMESTAMP('2026-01-01')
  AND usage_start_time < TIMESTAMP('2026-02-01')
GROUP BY cost_center
ORDER BY gross_cost DESC;
~~~

The query sums **cost before credits**, so this represents gross cost from the export data rather than necessarily the final invoice amount. To calculate net cost, account for credits, adjustments, data types, and reporting rules. An **unallocated** value is a signal to investigate: records may lack labels, the resource may not support labels, or the export data may not include that label.

### 8.2. Budgets and alerts

Budgets can be created per billing account/project and filters supported by Cloud Billing. From there, teams track spend rates and cost growth trends.

**A budget alert is not automatically a billing cap or auto-deletion mechanism.** If automated action is needed upon crossing a threshold, the organization must design the event flow, permissions, exception checks, and safe actions. Never let a cost signal automatically delete a production database or data subject to retention requirements.

### 8.3. Example governance targets

A weekly report can surface:

- Total cost by **team**, **application**, **environment**.
- Unallocated cost under **cost_center**.
- Idle VMs, unattached disks, overdue temporary resources.
- Data volume and retention impacting storage charges.
- Notable internet egress or cross-region network charges.

Data must be reconciled with owners and live load before applying stop/delete actions.

## 9. IAM and policy: who is allowed to attach metadata?

Labels and tags can create significant **indirect impact**. For instance, if a pipeline uses a label to select resources for cleanup, anyone permitted to edit labels can influence the deletion list. If a Resource Manager tag participates in IAM Conditions, anyone permitted to modify TagBindings can affect access evaluation outcomes.

Separation of duties should include:

| Role | Permissions to consider | Risk if overly broad |
|---|---|---|
| Platform team | Manage TagKey/TagValue sets, organization policies, and scoped binding rights | Altering classifications and policies across many projects |
| Application team | Label team-owned resources; modify bindings when delegated | Skewing cost allocation or mislabeling environments |
| IaC pipeline | Create resources and metadata from approved configs | If overly broad, a pipeline bug impacts many systems |
| FinOps team | Read billing exports, inventory metadata | Exposing business details in reports or queries |
| Security team | Review IAM Conditions, Organization Policies, and audit logs | Misjudging impact of inherited tags/policies |

Exact permissions depend on the operation, resource type, and API. For Resource Manager tags, check tag administration roles/permissions and binding permissions on **both the tag value and target resource** as required by the API. Do not assign broad admin roles just so a pipeline can update labels.

Audit logs, IaC versions, and change histories enable traceability. If a cleanup workflow relies on labels, include a **report-only (dry run) mode**, owner confirmation, and explicit safeguards for production.

## 10. Hands-on with Google Cloud CLI

This lab uses an **already provisioned** project and VM. Read commands inspect metadata; write commands should only be run when the learner has authorization and permission to modify resources.

### 10.1. Reading project and VM labels

~~~bash
# Display the project currently configured in gcloud.
gcloud config get-value project

# View metadata and labels of a project.
gcloud projects describe PROJECT_ID \
  --format="yaml(projectId,name,labels)"

# View labels on an actual VM in the project.
gcloud compute instances describe VM_NAME \
  --zone=ZONE \
  --project=PROJECT_ID \
  --format="yaml(name,zone,labels,tags)"

# List VMs with labels supported by the Compute Engine API.
gcloud compute instances list \
  --project=PROJECT_ID \
  --format="table(name,zone,labels)"
~~~

In VM output, **labels** and **tags** are two distinct structures; the Compute Engine VM **tags** field generally relates to network tags and does not represent Resource Manager tags.

Read commands still require appropriate view permissions and enabled APIs. If denied, do not expand permissions yourself or enable APIs on a production project.

### 10.2. Updating and verifying labels

Example adding labels to a test VM:

~~~bash
# Replace placeholder values and verify the exact VM before running.
# This command modifies the VM's live metadata.
gcloud compute instances add-labels VM_NAME \
  --labels=environment=development,team=platform,cost_center=ops002 \
  --zone=ZONE \
  --project=PROJECT_ID

# Re-read labels to confirm.
gcloud compute instances describe VM_NAME \
  --zone=ZONE \
  --project=PROJECT_ID \
  --format="yaml(labels)"
~~~

One notable scenario: changing a VM's **team** label can make cost allocation reports from that point onward differ from prior periods. Record the timestamp and new owner. For Terraform-managed resources, direct CLI edits can cause **drift**; align your source configuration and release workflow consistently.

### 10.3. Exploring Resource Manager tags

Example **read-only** operations on existing TagKeys and TagValues:

~~~bash
# List TagKeys under an organization if authorized.
gcloud resource-manager tags keys list \
  --parent=organizations/ORG_ID

# List TagValues under the selected TagKey.
gcloud resource-manager tags values list \
  --parent=tagKeys/TAG_KEY_ID
~~~

Learners must distinguish TagKey/TagValue identifiers from labels sharing the same names. To view or modify TagBindings on a resource, you must use the **exact full resource name**, syntax/scope, and location required by the tag binding API. Because tagging support varies by resource type, consult documentation for the specific object before running binding creation/deletion commands.

### 10.4. Observation questions

1. A project carries the label **team=payments**, while a VM lacks that label. Does a query filtering by VM resource labels automatically treat the VM as belonging to team payments?
2. A VM has the network tag **web**. Is this tag equivalent to the Resource Manager TagKey **environment**?
3. If a Resource Manager tag is bound at the project level, how can a policy evaluation feature supporting inheritance use that information?
4. Does adding **expires_on=20261231** automatically schedule VM deletion?
5. When changing the `cost_center` label, are historical cost reports automatically rewritten?

**Hints:** respectively: no; no; uses the effective tag to evaluate compatible conditions; no; do not assume so.

## 11. Design scenario: governing three environments of an ordering app

A team responsible for an ordering application manages three projects: **shop-dev**, **shop-staging**, **shop-prod**. The system uses Cloud Run, Cloud SQL, Cloud Storage, and occasionally Compute Engine for internal tooling. The team sets four goals:

- Allocate costs by application and operating team.
- Enforce stricter policies for production without guessing from project IDs.
- Find and review time-bound development resources.
- Ensure verifiable cleanup when owners change or test environments end.

### 11.1. Initial design

| Target | Metadata or governance approach | Rationale |
|---|---|---|
| Three projects | **environment** tag with matching value; project labels as needed | Environment classification and conditional policy support where compatible |
| Label-supporting resources | **application=checkout**, **team=payments**, **cost_center=fin001** | Inventory, cost allocation, owner identification |
| Temporary resources | **lifecycle=temporary**, **expires_on=YYYYMMDD** | Generate review list, not an automatic deletion schedule |
| Production Cloud Run | Restricted IAM, dedicated service account, logs/metrics/SLOs | Access control and reliability |
| Cloud SQL | Decisions on backups, recovery, location, and access | Transactional data protected independently of labels/tags |
| Network firewall for VMs | Use network tags or firewall-supported selectors | Separate network logic from billing metadata |
| Pipeline | Validate metadata and configuration before provisioning | Reduce missing labels, wrong environments, or manual edits |
| FinOps | Billing export, unallocated reports, and budget alerts | Identify missed charges and anomalies |

### 11.2. Handling an expired test environment

A dev VM's expiration date arrives. Inventory finds **lifecycle=temporary** and **expires_on** past today's date. Instead of deleting immediately:

1. Generate a report and route it to the owner indicated by the `team` label.
2. Check whether the machine still hosts workloads, disks, IP addresses, or data worth keeping.
3. Reconcile dependencies, utilization, snapshots/backups, and retention mandates.
4. Once retirement is confirmed, apply the change through an approved pipeline.
5. Verify the resource no longer exists, no longer accrues charges, and update inventory/tickets.

If the VM was repurposed from dev to serve a production task without updating its labels, this workflow catches the risk only when **owner and dependency verification** is included. That is why metadata and automation must pair with operational processes.

### 11.3. When should a label be replaced by a tag?

Not all metadata needs to be a Resource Manager tag. Use tags only for attributes genuinely consumed by **supported policies or governance mechanisms**, with standardized value sets and controlled edit permissions. Reporting attributes like `cost_center` or `application` typically start as labels. Both can exist for **environment**, provided you define an **authoritative source** and guard against conflicting states.

For example: a project carries the tag **environment=production** while a VM carries the label **environment=development**. Access decisions cannot rely on reading labels; policies evaluate configured tags or conditions. Conversely, a label-based cost report may group the VM under development. This discrepancy must be detected and fixed as a metadata quality bug.

## 12. Common pitfalls and principles to remember

| Misconception or mistake | Accurate understanding |
|---|---|
| Labeling a project labels all children | Labels do not inherit automatically; label the exact resources needed for filtering/reporting |
| Labels are an access-control tool | IAM and policies determine access; labels are descriptive |
| Every “tag” in Google Cloud is the same type | Resource Manager tags, Compute Engine network tags, and firewall tags must be distinguished |
| A production tag enforces security automatically | Policy effect requires configuring and testing supported policies |
| Every resource supports labels/tags identically | Support depends on product, API, and attachment method |
| Changing a label updates past invoices | Historical billing data is not automatically rewritten |
| Having expires_on stops the machine automatically | Labels are just data; execution requires processes and tooling |
| Deleting a project is a simple cleanup shortcut | Can impact data, dependencies, and recovery; requires scoped decommissioning |
| Budgets block all overspend | Budget alerts primarily support observation and alerting |
| Every resource type can be recovered after deletion | Recoverability, retention, and backups depend on service and configuration |

## 13. Design self-check exercise

Suppose you take over a project with no metadata conventions. Propose:

1. Five minimum labels to identify environment, application, owning team, cost center, and provisioning method.
2. One TagKey and a set of TagValues suited for environment-based policy conditions.
3. How to handle a case where the project has a production tag while a resource reports a development label.
4. A cleanup workflow for a resource whose `expires_on` has passed yet still has active users.
5. A billing report highlighting unallocated costs and input data limitations.

A sound approach: define labels **environment, application, team, cost_center, managed_by**; use Resource Manager TagKey **environment** with TagValues **development/staging/production** when policy features require it; validate consistency in pipelines; handle expired resources via owner, dependency, data, and approval verification; use billing export grouped by `cost_center` while tracking the **unallocated** portion.

---

**Takeaways for upcoming lessons:** the resource hierarchy defines **which governance scope a resource belongs to**; region/zone defines **where it is deployed**; labels describe **whom it serves and how costs are attributed**; Resource Manager tags provide **classification for supported policies**; and lifecycle workflows ensure resources are provisioned, operated, and retired responsibly. When building systems with Compute Engine, GKE, Cloud Run, Cloud Storage, or databases, design these layers alongside IAM, networking, automated releases, and monitoring from the outset.
