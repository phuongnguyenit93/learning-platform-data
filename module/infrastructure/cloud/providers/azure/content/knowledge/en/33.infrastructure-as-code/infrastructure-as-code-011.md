# Drift Detection, Resource Import, and Change Control

## 1. The Problem: Azure Infrastructure Changing Outside Source Code

A team deploys a Java/Spring Boot application **`orders-api`** onto Azure Container Apps. Infrastructure is declared in **Bicep** or **Terraform**: a resource group, virtual network, private endpoint, Azure Storage, Key Vault, managed identity, and Azure Monitor. During a midnight incident, an on-call engineer enables public network access on the Storage account to test connectivity and forgets to revert it. Another engineer creates a database through the Azure Portal, while the IaC pipeline does not declare it yet. A few months later:

- Source code says Storage uses private-only access, yet live Azure allows public access.
- The Terraform pipeline proposes recreating or deleting a resource holding critical data.
- Bicep `what-if` shows hard-to-explain diffs between desired state and live configuration.
- Nobody knows whether a change came from CI/CD, Azure Policy, or a human operator.
- Pre-existing resources have not been brought under the IaC lifecycle.
- Emergency hotfixes turn into silent drift, causing staging and production to diverge.

That is why you need **drift detection**, **adopting/importing existing resources**, and **change control**. The goal is not merely getting tools to report "no diff"—it is ensuring production state is managed intentionally, auditable, recoverable, and traceable without data loss.

This lesson belongs to the **Infrastructure as Code** chapter of the **CLOUD_PROVIDERS_AZURE** module. The broader module explores Azure from subscriptions, resource groups, Microsoft Entra ID, networking, compute, storage, and data services through deployment, observability, security, and cost. The examples below connect directly to Azure CLI, Resource Manager, Bicep, Terraform, Azure Policy, Azure Activity Log, and CI/CD pipelines. Resource names and numbers are **illustrative placeholders for learning**; never run any production-mutating command without authorization.

## 2. Learning Objectives

After this lesson, you will be able to:

1. Explain **desired state**, **actual state**, **IaC state**, and the categories of configuration drift.
2. Distinguish drift caused by manual edits, other tools, default/computed attributes, and external automation.
3. Interpret **`az deployment group what-if`** for ARM/Bicep and **`terraform plan`** for Terraform.
4. Understand the limitations of `what-if`/`plan` and avoid assuming every diff is safe.
5. Use Azure Activity Log, Azure Policy, and Azure Resource Graph as corroborating evidence to trace drift root causes.
6. Contrast **Bicep `existing` resources** with importing resources into Terraform state.
7. Design a workflow to adopt pre-existing Azure resources into IaC without accidentally recreating or deleting them.
8. Understand **`terraform import`**, **`import` blocks**, **`state list`/`show`**, **`plan -refresh-only`**, **`moved` blocks**, and when each applies.
9. Propose reconciliation steps when code, Terraform state, and live Azure diverge.
10. Protect stateful data resources from unintended replacement or deletion.
11. Enforce change control via reviews/approvals, least-privilege RBAC, PIM, Azure Policy, and CI/CD gates.
12. Build a scheduled drift-detection workflow with severity triage, exception tracking, rollbacks, and auditing.
13. Run labs validating drift, imports, and change control strictly against **dedicated lab resources**.

## 3. Three Perspectives on an Azure Resource

With Bicep/ARM, the two primary views are the **desired declaration** and **existing Azure resources**. With Terraform, there is a third view—**state**—binding configuration resource addresses to live Azure object IDs.

~~~mermaid
flowchart LR
    CODE[Git: desired IaC configuration] --> PLAN[Plan / what-if]
    STATE[(Terraform state if using Terraform)] --> PLAN
    AZURE[(Azure resources: actual state)] --> PLAN
    PLAN --> REVIEW[Review and approval]
    REVIEW --> APPLY[Controlled deployment]
    APPLY --> AZURE
    AZURE --> AUDIT[Activity Log / Policy / Monitor]
    AUDIT --> REVIEW
~~~

| Component | What Does It Hold? | Common Misconception |
|---|---|---|
| **Desired state** | Bicep/Terraform code and intended parameters | Treating Git files as a complete record of every live Azure property |
| **Actual state** | Live configuration/resources read from Azure APIs | Assuming the Portal displays every setting or historical edit |
| **Terraform state** | Tracked mapping of resource addresses, IDs, and attributes | Treating state as a full backup of an Azure database |
| **Deployment history** | Results of past `apply`/deploy runs | Treating a successful deploy as proof that runtime meets SLOs |
| **Activity Log** | Partial history of management-plane operations | Assuming it records all data-plane ops or proves zero drift |
| **Policy compliance** | Resource evaluation against Azure Policy rules | Equating policy compliance with matching specific IaC source code |

### 3.1. What Does "No Changes" Mean?

A `terraform plan` or Bicep `what-if` reporting **no changes** only means that **given current inputs, scope, provider/API versions, and the properties the tool compares**, no significant diff was detected. It does not prove the application is healthy, secrets are safe, business data is intact, or undeclared resources are governed.

### 3.2. Drift Is Not a Single Azure Status Flag

"Drift" is a configuration-management concept. You can simultaneously experience drift across:

- Resource settings (firewalls, SKUs, tags).
- IaC state mappings.
- RBAC roles and managed identities.
- Policies, exemptions, and diagnostic settings.
- Runtime app settings or container image digests.
- Data schemas, database state, and migration history.

Each category requires different evidence sources and remediation procedures.

## 4. Classifying Drift by Root Cause

| Category | Example | Analysis |
|---|---|---|
| **Manual drift** | Operator enables public access on Storage | Often an emergency hotfix never backported |
| **Out-of-band automation** | Another script updates resource tags | Two management sources out of sync |
| **Provider/API default** | Azure applies a default differing from IaC | Can create plan noise despite no intentional edit |
| **Computed/read-only** | Properties known only by Azure at runtime | Not every difference can be forced verbatim in code |
| **Policy remediation** | Azure Policy `Modify`/`DeployIfNotExists` adds config | IaC must align with policy owners and desired config |
| **Unmanaged resource** | Engineer creates a Key Vault absent from IaC | Outside IaC management; may not show up as a "diff" |
| **State drift** | Terraform state lacks an ID or points to the wrong object | Requires controlled state review, import, or move |
| **Intentional exception** | Firewall opened temporarily during an incident | Time-bound with an owner; decide whether to backport or revert |
| **Runtime drift** | Running image differs from approved digest | Check deploy config and runtime revision |
| **Data drift** | SQL schema altered outside migration tools | Never rely solely on `terraform plan` to diagnose |

### 4.1. Intentional Drift Still Requires Closure

A change made by on-call engineers to restore service is not automatically a "violation". However, it must carry an **incident/change ID, an owner, an expiration window, and a resolution**: either adopt the change by updating IaC or revert it back to desired state.

### 4.2. Some Differences Are Just Noise

Field ordering, letter casing, API defaults, computed/unknown attributes, or serialization quirks can produce confusing diffs. Verify against Azure API/provider docs and a test lab—never mute all drift alerts just because a few false positives exist.

## 5. Is Drift a Security Bug?

Not every drift event is a security incident, yet certain types demand urgent priority:

- Public network access enabled on Storage, SQL, or Key Vault.
- Role assignments granting Owner or overly broad data-plane access.
- Logging, auditing, or diagnostic settings disabled.
- Key Vault soft-delete/purge protection or TLS settings weakened.
- Unapproved Azure Policy exemptions.
- Altered encryption or access rules.
- Private endpoints, routes, or NSG/firewall rules creating unintended paths.
- Container images running an unverified digest.

Cost-increasing or low-impact drift (such as an extra tag) needs a different response workflow than a data-exposure vulnerability. **Prioritize risk by impact**, not alphabetically.

## 6. Scope and Source of Truth

Organizations should establish explicit resource ownership:

~~~text
Azure Landing Zone Platform Team:
  management groups, policy assignments, hub network,
  shared DNS, subscription-level IAM

Application Team:
  app runtime, application managed identity,
  application Storage container, monitoring config

Database Team:
  production database provisioning, backups,
  schema/migration workflow

Security Team:
  policy baseline, role exceptions, incident response
~~~

### 6.1. One Resource Should Not Have Multiple Tools Running `apply`

If Terraform stack A and Bicep pipeline B both independently declare and update the same Azure Storage account, they will overwrite each other. Assign a single **owner / source of truth**, or define strictly disjoint property/resource scopes with an explicit integration contract.

### 6.2. IaC Is Not the Source of Truth for All Data

IaC describes resource configuration and management relationships—it is not a transactional database state store or secret backup. Checking data drift requires migration records, DB schema tools, and business validation.

### 6.3. Resource Tags Are Just Metadata

A tag like **`managedBy=terraform`** aids inventory, yet does not stop an operator from editing the resource. Enforce governance with RBAC, Azure Policy, IaC pipelines, and audits.

## 7. Managing Drift Across the Lifecycle

~~~mermaid
flowchart TD
    BASE[Approved IaC baseline] --> SCAN[Scheduled plan / what-if]
    SCAN --> DIFF{Significant difference?}
    DIFF -- No --> LOG[Record clean scan]
    DIFF -- Yes --> CLASS[Classify severity and ownership]
    CLASS --> ROOT[Investigate Activity Log, policy, config]
    ROOT --> DEC{Desired direction?}
    DEC -- Restore approved baseline --> FIX[Reviewed IaC apply]
    DEC -- Accept authorized change --> BACK[Update code + tests + approvals]
    DEC -- Unknown or unsafe --> HOLD[Freeze + incident / escalation]
    FIX --> VERIFY[Readback + health checks]
    BACK --> VERIFY
    HOLD --> VERIFY
    VERIFY --> BASE
~~~

### 7.1. Scan Output Must Be Structured

Record **subscription, resource group, resource IDs, IaC commit, stack/module, tool/provider versions, plan ID/timestamp, change summary, and severity**. Never log sensitive Terraform state or secrets in scan reports.

### 7.2. Detection Does Not Mean Auto-Remediation

A scanner flagging a firewall mismatch does not authorize running `apply` automatically. Auto-remediation suits only low-risk, narrowly scoped policies with full observability and safe rollback.

### 7.3. Two Directions for Reconciliation

- **Azure → match Git:** revert the out-of-band edit via IaC.
- **Git → match Azure:** if the edit is authorized, update code/parameters and validate it as the new baseline.

Never blindly update IaC to match live state, as that can codify insecure configurations.

## 8. Limitations of Drift Detection

No single command can scan "all Azure drift" completely.

### 8.1. Unmanaged Resources May Stay Invisible

Bicep `what-if` evaluates the supplied template; Terraform `plan` compares resources tracked in configuration and state. A brand-new resource created manually out of scope will not show up as drift without separate inventory reconciliation.

### 8.2. Providers and APIs Do Not See Everything

Some attributes are computed, write-only, or service-specific. Secret values generally cannot be read back verbatim, and dynamic platform state does not always map cleanly into IaC.

### 8.3. Some Diffs Have Indirect Impact

Changing an SKU or network setting can trigger a restart or recreate, shift IP addresses, cause downtime, or break compatibility even though the plan shows only a few lines changed. Assess **blast radius** and service-specific behavior.

### 8.4. Data-Plane Drift Needs Dedicated Tools

`AzureActivity` captures management-plane events, not every SQL DDL edit or Cosmos DB item change. Rely on data-plane audit logs, migration checksums, and database diagnostics.

## 9. Before Scanning: Verify Subscription and Environment

**Read-only** Azure CLI checks:

~~~bash
az account show \
  --query '{subscription:id,name:name,tenant:tenantId}' \
  -o table

az resource list \
  --resource-group rg-orders-dev \
  --query '[].{name:name,type:type,location:location}' \
  -o table
~~~

### 9.1. Do Not Rely Unconditionally on `az account` Defaults

Your local CLI may point to a different subscription than your pipeline or Terraform provider. Before running `apply` or `import`, pin the approved subscription ID and verify environment tags.

### 9.2. Read Access Does Not Equal Write Access

A drift-scan runner may need only read permissions on Azure resources and state access; deployment and role-assignment permissions belong in a separate, approval-gated job.

### 9.3. Keep Resource Identity Unambiguous

Identical names for certain services can exist across different subscriptions or regions. Always reconcile using the **full ARM resource ID**, never just a display name.

## 10. Bicep/ARM: Viewing Desired vs. Actual State

**Bicep** compiles into ARM templates deployed via **Azure Resource Manager**. In this model, Bicep does not manage a separate **Terraform-like state file**. Azure Resource Manager and its resource providers hold live resource state, while templates and parameters express the desired state to deploy.

~~~text
main.bicep + environment parameters
        |
ARM what-if API
        |
Current Azure resources
        |
Predicted change set
        |
Reviewed deployment
~~~

### 10.1. Role of `what-if`

**`what-if`** predicts deployment changes for a given scope and template—create, modify, delete, no change, or ignore/unsupported diagnostics depending on API and tool versions. It does not replace CI/security gates or guarantee every runtime side effect is predicted accurately.

### 10.2. ARM Deployments Do Not Always Delete Unlisted Resources

In **incremental deployment mode**, a resource omitted from a template is not automatically deleted. Lifecycle features like Deployment Stacks carry their own semantics and options. Never rely on "deleting lines from Bicep" as a deletion strategy without understanding the active mode and tooling.

### 10.3. Templates May Declare a Subset of Properties

If a template omits a property, redeployment behavior depends on the resource provider, API version, and defaults—never assume an omitted property is preserved untouched or reset. Check `what-if` and resource-specific documentation.

## 11. Example Baseline Bicep for a Lab Storage Account

~~~bicep
targetScope = 'resourceGroup'

@description('Storage name must be globally unique and valid.')
param storageAccountName string

param location string = resourceGroup().location

param envTag string = 'dev'

resource storage 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: storageAccountName
  location: location
  tags: {
    environment: envTag
    managedBy: 'bicep'
  }
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
  }
}

output storageId string = storage.id
~~~

**This is illustrative code—never run it verbatim against production.** Verify API versions, subscription policies, naming, replication, networking, encryption, and backup requirements for real workloads.

### 11.1. Why Set `allowBlobPublicAccess`?

This setting blocks anonymous blob access at the account level. It **does not disable the public network endpoint**. Those are two separate properties; pair them with firewall/network rules and Entra authentication/RBAC to restrict network exposure.

### 11.2. Separate Parameter Files

A lab parameter file can hold non-sensitive names and tags; never store storage account keys or key-bearing connection strings in Git.

### 11.3. Goal of Drift Testing

First deploy the approved baseline into your lab, then make a non-destructive edit (such as a tag) in the Portal during testing, and run `what-if` to observe the diff. Always confirm the resource belongs strictly to your lab.

## 12. Bicep `what-if`: Previewing Changes

In an authorized resource group, run via Azure CLI:

~~~bash
RG='rg-iac-drift-lab'
STORAGE='iacdriftlab001'

az account show \
  --query '{subscription:id,name:name}' -o table

az deployment group what-if \
  --resource-group "$RG" \
  --template-file main.bicep \
  --parameters storageAccountName="$STORAGE"
~~~

**These commands are illustrative only.** `main.bicep` must exist in your own lab project; this lesson does not create it. Run only after verifying the right subscription and resource group. ARM `what-if` may require more than pure Reader rights depending on the resource API.

### 12.1. Interpreting Predicted Changes

- **Create:** resource predicted to be created.
- **Modify:** properties differ from the baseline.
- **Delete:** depending on mode/feature and scope; inspect very carefully.
- **NoChange:** no differences detected within the evaluated scope.
- **Ignore/diagnostic:** tool cannot evaluate certain fields under that API/version.

### 12.2. `what-if` Does Not Apply

`what-if` makes no template deployment changes; it returns a diff for review. However, it still triggers API calls requiring permissions and is never a 100% guarantee that a subsequent deploy will match identically.

### 12.3. Never Assume "0 Diff" Means All of Azure Is Clean

It evaluates only the current template, scope, API, and inputs. Unmanaged resources, undeclared properties, data-plane state, and runtime health require separate checks.

## 13. Reading Bicep `what-if` Diffs Without Misinterpretation

Suppose the template sets tag **`environment=dev`**, and someone manually changed the live Storage account tag to **`environment=temporary`**. `what-if` predicts restoring the tag back to baseline. Before approving:

1. Confirm the exact **ARM resource ID**.
2. Check whether any other properties changed—not just the tag.
3. Distinguish an intentional emergency edit from unauthorized drift.
4. Check service/API conditions for possible restarts or downtime.
5. Query Activity Log for timestamp, caller, and change correlation.
6. Confirm region, subscription, and template parameters.
7. Approve the change before running a controlled deploy.
8. Read back live resource properties and run smoke tests.

### 13.1. Diffs From Unresolved Runtime Expressions

Bicep/ARM supports runtime reference functions and provider-computed properties; `what-if` cannot always evaluate exact values ahead of time. Cross-check live resource state and known tool limits when noise appears.

### 13.2. If `Delete` or `Replace` Is Predicted

Halt automated jobs and require owner review plus a backup/data-impact assessment—even if the PR looked like a harmless tag edit. A Storage account holding data must never be treated as disposable.

### 13.3. Never Suppress All `what-if` Output with One Flag

Filtering noisy fields can help readability, yet must never hide security-relevant changes. Any allowlist for frequently changing properties needs an owner and documented audit rationale.

## 14. What Does "Importing" an Existing Resource into Bicep Mean?

**Bicep has no state-import command equivalent to `terraform import`.** There are two common ways to bring an existing Azure resource into a Bicep design:

1. **Reference an existing resource** using **`existing`** to consume its ID/properties and wire other resources without creating or modifying it.
2. **Adopt as a managed resource** by authoring a full resource declaration matching the live ID, scope, API version, and permissions, then running `what-if` + review before deploying the desired definition.

### 14.1. `existing` Resource Example

~~~bicep
targetScope = 'resourceGroup'

param storageName string

resource existingStorage 'Microsoft.Storage/storageAccounts@2023-01-01' existing = {
  name: storageName
}

output existingStorageResourceId string = existingStorage.id
~~~

### 14.2. `existing` Does Not Manage Resource Properties

The **`existing`** keyword creates a read reference—it **does not** "import the resource into Bicep management" and does not enforce TLS, firewalls, tags, or SKUs. To manage properties, declare the resource normally and deploy with change control.

### 14.3. Same Name in a Different Scope Is a Different Resource

An ARM resource ID encodes subscription, resource group, provider, type, and name. Always verify target scope and resource ID, especially for cross-subscription references.

## 15. Controlled Workflow to Adopt a Resource into Bicep

Suppose a production Storage account was created manually earlier, and now the team wants it managed by IaC.

### Step 1 — Assign Ownership

Identify the target IaC repository/module, owning team, environment, and approvers. Verify no Terraform stack, Deployment Stack, or other pipeline already manages the resource.

### Step 2 — Snapshot Metadata and Dependencies

Capture the Azure resource ID, type, API-relevant properties, tags, RBAC, private endpoints, retention, encryption, locks, diagnostic settings, data lifecycle, and application dependencies. Never copy keys or secret-bearing connection strings into source control.

### Step 3 — Author Bicep Matching Approved Live Properties

Declare the resource and critical security/availability properties using an appropriate API version. Parameterize non-secret environment inputs; never "adopt" by pasting secrets into Bicep.

### Step 4 — Run `what-if` Against the Exact Scope

Preview changes; confirm the resource matches the existing ID and review every proposed property create/modify/delete. **Never ignore a predicted `Create` on an already-existing production resource**—that signals a scope, name, or type mismatch.

### Step 5 — Reconcile Desired vs. Actual and Classify Diffs

Classify every difference as:
- Keep as part of the approved baseline.
- Remediate to match security policy.
- Defer due to downtime or data-migration requirements.
- Outside this IaC owner's scope.

### Step 6 — Review, Apply, and Read Back

Deploy through a protected pipeline, inspect activity/deployment records, verify runtime/config behavior, metrics, and security posture. Keep a rollback/restore plan ready for risky edits.

### Step 7 — Guard Against Future Drift

Establish owners, IaC pipeline gates, matching Azure Policies, least-privilege roles, and scheduled `what-if` reviews.

## 16. Are Template Export / Decompile Automatic Import Solutions?

Azure provides ARM template export and **decompile ARM JSON to Bicep** utilities to jumpstart authoring, yet exported code often:

- Omits certain properties, child/extension resources, or dependencies.
- Includes read-only or server-computed fields that fail direct redeployment.
- Pins outdated or suboptimal API versions.
- Hardcodes production names and IDs.
- Misses full networking, RBAC, secrets, or data-plane context.
- Generates verbose files that are hard to modularize and govern.

### 16.1. Use as a Starting Point, Never Copy Verbatim

Gather inventory, choose target schemas/API versions, modularize, extract parameters, strip secrets and computed noise, add policies, run validate/`what-if`, and review every resource before treating the template as a source of truth.

### 16.2. Never Use Export to Back Up Secrets

An ARM template export is not a backup of Key Vault secrets, SQL records, or full runtime state. Never substitute export for real backup and restore plans.

### 16.3. Strengths and Limits of Bicep's Stateless Model

You avoid managing a Terraform state backend, yet you still need deployment history, resource ownership tracking, an IaC baseline, unmanaged-resource detection, and change control. "No state file" does not mean "no drift".

## 17. Terraform: Three Things That Must Stay Aligned

Terraform coordinates **configuration**, **state**, and **remote infrastructure**.

~~~text
Terraform configuration (resource addresses + desired attributes)
            |
           Plan
            |
Terraform state (tracked Azure IDs, attributes)
            |
Azure Resource Manager / provider reads actual resource
~~~

### 17.1. Resource Address vs. Azure Resource ID

Example:

- Terraform address: **`azurerm_resource_group.lab`**
- Azure ARM ID: **`/subscriptions/SUB_ID/resourceGroups/rg-iac-lab`**

The address is the identifier inside Terraform configuration/state; the ARM ID identifies the Azure object. Importing links those two for a pre-existing resource.

### 17.2. Plans Rely on Refreshed State

Normally, **`terraform plan`** queries remote objects via the provider to refresh state, then compares against desired HCL. Provider behavior, permissions, and flags shape the output—never treat a plan as a complete dump of every Azure setting.

### 17.3. State Contains Sensitive Data

State can store sensitive attributes and secrets depending on the resource and provider, even when CLI masks them. Store state in an encrypted, access-controlled, audited, backed-up, and locked remote backend—never paste state into tickets or chat.

## 18. Terraform Configuration for a Lab Resource Group

Illustrative sample using the AzureRM provider; the provider version is a placeholder requiring an approved release line.

~~~hcl
terraform {
  required_version = ">= 1.5.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
}

variable "subscription_id" {
  type = string
}

variable "location" {
  type    = string
  default = "southeastasia"
}

resource "azurerm_resource_group" "lab" {
  name     = "rg-iac-drift-lab"
  location = var.location

  tags = {
    environment = "lab"
    managedBy   = "terraform"
  }
}
~~~

### 18.1. Version and Authentication

AzureRM provider releases have differing requirements. This example illustrates provider 4.x and `subscription_id`. In real projects, pin exact versions and configure Entra/OIDC/managed identity per the selected provider version's documentation.

### 18.2. Do Not Assume the Resource Group Isn't Already Created

Terraform configuration merely declares desired state; **`terraform plan`** shows the proposal. Never run `apply` without confirming whether the resource already exists, the subscription is right, and permissions are scoped.

### 18.3. What If the RG Already Exists?

Never run `apply` just to confirm an "already exists" error. Follow a proper import workflow and review configuration before bringing it under Terraform management.

## 19. Terraform Drift Detection with `plan`

Inside a prepared Terraform lab directory:

~~~bash
terraform init
terraform fmt -check
terraform validate
terraform plan -out=drift.tfplan
terraform show drift.tfplan
~~~

### 19.1. What Can `terraform plan` Propose?

- **Create (+):** resource declared in config but missing from state.
- **Update in-place (~):** Terraform predicts modifying fields in place.
- **Destroy (-):** resource present in state yet removed from config/logic.
- **Replace (-/+ or +/-):** Terraform predicts destroying and recreating the resource to satisfy a change.
- **No changes:** no differences detected under current provider, config, and state.

### 19.2. Plans Can Contain Sensitive Data

Saved plan files can retain attributes and values that must stay private, regardless of CLI display masking. Protect `drift.tfplan` and **never commit** it to Git. In labs, delete temporary plan files when finished.

### 19.3. Review for Risk, Not Just Diff Count

A minor tag update may be benign; replacing a database or exposing a network must be blocked and escalated. Always inspect exact attribute paths and resource IDs.

### 19.4. Never Auto-Apply from Untrusted PRs

`terraform plan` on PRs should run with read-only or tightly limited identities; `apply` must run only in protected environments with approved permissions and trusted sources.

## 20. `terraform plan -detailed-exitcode` in CI

Useful command for detecting diffs:

~~~bash
terraform plan \
  -detailed-exitcode \
  -no-color \
  -out=drift.tfplan
~~~

Standard exit codes:

| Exit Code | Meaning | Interpretation |
|---|---|---|
| **0** | No changes in plan | Clean for that scope |
| **1** | Error during plan | Scan failed—do not report clean |
| **2** | Changes present in plan | Requires review and classification |

### 20.1. CI Shells with `set -e` Must Handle Code 2 Properly

In Bash with **`set -e`**, exit code 2 aborts the script before reporting. Illustrative pattern:

~~~bash
set +e
terraform plan -detailed-exitcode -no-color -out=drift.tfplan
code=$?
set -e

case "$code" in
  0) echo "No planned changes" ;;
  2) echo "Differences detected; review required" ;;
  *) echo "Terraform plan error"; exit "$code" ;;
esac
~~~

### 20.2. Exit Code 2 Does Not Mean Every Diff Is Drift

A legitimate PR modifying IaC also makes `plan` return exit code 2. True drift detection compares the approved baseline against live state when no code change was introduced—otherwise pipelines label every valid deployment as "drift".

### 20.3. Always Inspect the Diff on Code 2

Classify updates, replacements, deletions, RBAC/network/data edits, and production impact. Never treat a passing `plan` with diffs as permission to `apply`.

## 21. `terraform plan -refresh-only`: How It Differs from a Regular Plan

**`terraform plan -refresh-only`** focuses strictly on differences **between tracked state and live remote objects** after refresh, without proposing changes to force remote resources back to HCL configuration.

~~~bash
terraform plan -refresh-only
~~~

### 21.1. When Is It Useful?

- Investigating manual or out-of-band changes.
- Checking whether state contains stale attributes.
- Reconciling remote objects against stored state.
- Filtering out planned HCL changes while isolating drift sources.

### 21.2. Does Not Modify Infrastructure

**`plan -refresh-only`** only previews state updates. It never modifies Azure resources and does not judge whether remote edits are authorized.

### 21.3. Be Careful with `apply -refresh-only`

**`terraform apply -refresh-only`** updates state to match remote reality without touching Azure resources, shifting your tracking baseline. Never use it as a shortcut to "make drift vanish"; require owner review and a plan so unauthorized manual edits aren't silently blessed into state.

### 21.4. Never Use `-refresh=false` to Hide Drift

Disabling refresh forces `plan` to compare against stale state. A zero-diff plan produced without reading live Azure state proves nothing.

## 22. `terraform import` (CLI): Binding an Existing Object to State

Suppose RG **`rg-iac-drift-lab`** already exists in Azure outside Terraform state, and HCL already declares **`azurerm_resource_group.lab`**.

~~~bash
terraform import \
  azurerm_resource_group.lab \
  "/subscriptions/SUBSCRIPTION_ID/resourceGroups/rg-iac-drift-lab"
~~~

### 22.1. What Does CLI Import Do?

It records the live Azure resource inside Terraform state at the chosen address using provider import semantics. **It does not verify or generate complete HCL** matching every desired attribute.

### 22.2. Import vs. Apply

Import does not "create a new RG". It attaches Terraform state tracking to the existing RG. Immediately after importing, **`terraform plan`** may still propose updates or replacements if your HCL mismatches live fields.

### 22.3. Prerequisites

- Correct subscription, tenant, and provider configuration.
- Target Terraform address is not already tracking another object.
- Target Azure object actually exists.
- Operator holds resource read rights and state backend write rights.
- Resource is not already managed by another Terraform workspace or stack.
- State backup/snapshot taken per policy.
- Owner approval for adoption.

### 22.4. Verify Immediately After Importing

~~~bash
terraform state list
terraform state show azurerm_resource_group.lab
terraform plan
~~~

If `plan` predicts replacement or deletion, stop and fix configuration or migration plans. Never blindly run `apply` just because `import` succeeded.

## 23. Terraform `import` Block: Declarative Adoption in Code

Since Terraform 1.5, **`import` blocks** in HCL bring imports into the reviewed `plan`/`apply` workflow:

~~~hcl
import {
  to = azurerm_resource_group.lab
  id = "/subscriptions/SUBSCRIPTION_ID/resourceGroups/rg-iac-drift-lab"
}
~~~

Target resources require matching **resource configuration**, except in workflows using supported config generation under review.

### 23.1. Advantages Over CLI Import

- Import intent is visible in pull requests.
- `plan` previews import actions for review and approval.
- Fits formal change control and audit trails.
- Pairs with config generation where supported by Terraform and provider versions.

### 23.2. `import` Blocks Are Not Automatic Data Protection

If HCL declares the wrong location, SKU, or name, `plan` will still propose modifying or replacing the resource. Review imports against live state and business risk like any other IaC change.

### 23.3. Never Duplicate Ownership

Never import the same Azure resource into two independent Terraform states and run `apply` from both. Two stacks will overwrite each other or attempt to destroy the shared resource.

## 24. Terraform Generated Config: Starting Point, Not Production Code

On supported Terraform versions, you can combine an `import` block with **`terraform plan -generate-config-out=...`** to scaffold resource HCL for imported objects.

Illustrative example:

~~~bash
terraform plan \
  -generate-config-out=generated-resources.tf
~~~

### 24.1. Run Only When Preparing a Valid Import

`generated-resources.tf` is an output **in your lab project**, not a file created by this lesson. The flag carries version- and provider-specific constraints; inspect errors if config already exists or the provider omits fields.

### 24.2. Generated Config Contains Noise and Unwanted Attributes

Review live properties, strip unnecessary read-only or computed defaults, extract variables and modules, check for secrets, and verify provider/API compatibility. Never commit raw generated files unreviewed.

### 24.3. A Clean Post-Import Plan Does Not Prove Policy Compliance

The live resource might allow anonymous access or lack diagnostic settings. "Adopt as-is" is only step one—follow up with approved changes to align with organizational baselines.

### 24.4. Never Use `import` Blocks to Change Resource IDs

Import binds an address to an existing ID; if the live ID differs from your target, check scope and ownership. Changing IDs or scopes requires a separate migration, not importing random objects.

## 25. `terraform state list`/`show` vs. Live Resource Reality

~~~bash
terraform state list
terraform state show azurerm_resource_group.lab
~~~

### 25.1. What Does `state show` Display?

It prints attributes currently recorded in Terraform state. It does not guarantee every Azure property was freshly queried at that moment—run `plan`/refresh or Azure API reads to confirm live state.

### 25.2. Use Azure APIs to Verify Critical IDs and Properties

Azure CLI example:

~~~bash
az group show \
  --name rg-iac-drift-lab \
  --query '{id:id,name:name,location:location,tags:tags}' \
  -o json
~~~

### 25.3. Never Edit State Manually to Silence Diffs

State mutations carry ownership risks. Stick to reviewed `import`, `moved`, and refactor workflows with backups; manually deleting or hacking state addresses can orphan critical live infrastructure.

### 25.4. Terraform State Is Confidential Data

Restrict backend access, enforce encryption, locking, auditing, and controlled backups, and never paste sensitive outputs into issues or public CI artifacts.

## 26. Refactoring Terraform Addresses: `moved` Blocks vs. `import`

Suppose a Storage account lived at **`azurerm_storage_account.data`** and is refactored into **`module.storage.azurerm_storage_account.this`**, while the live Azure resource stays unchanged.

### 26.1. This Is Not a New Resource

Changing the address without guiding state migration makes Terraform propose destroying the old address and creating a new one. Handle **resource address moves** with a `moved` block or controlled state move:

~~~hcl
moved {
  from = azurerm_storage_account.data
  to   = module.storage.azurerm_storage_account.this
}
~~~

### 26.2. `moved` vs. `import`

- **`moved`**: relocates an object already tracked in state to a new HCL address.
- **`import`**: brings an existing Azure object not yet tracked in the current state under an address.
- **`data` source**: reads an existing object without taking management ownership.

### 26.3. `state mv` Still Has Special Cases

**`terraform state mv`** works in controlled state-ops runbooks, whereas `moved` blocks codify refactoring intent directly in PRs for cleaner `plan` reviews. Watch out for module addresses, `for_each`/`count` keys, imports, and ownership boundaries.

### 26.4. Switching State Backends Is a Separate Migration

Moving resource addresses within the same state is not migrating backends or splitting stacks. Backend migrations require separate locks, backups, permissions, and reconciliation—never run parallel writers during a switch.

## 27. `terraform state rm`: Why Exercise Extreme Caution?

**`terraform state rm`** stops tracking a resource address in the current state without directly deleting the Azure resource. It is **not** a normal drift-remediation tool.

### 27.1. If You Remove State Tracking While Config Remains

The next `plan` will propose creating a new resource. If the Azure object already exists and the provider rejects implicit adoption, `apply` fails or causes unintended side effects. Never use `state rm` just to "make `plan` stop complaining".

### 27.2. Transferring Ownership Between Stacks

Required process:

1. Identify source/destination states and owners.
2. Snapshot both states and verify locking.
3. Freeze all related applies during the migration window.
4. Update HCL configs confirming the Azure resource ID stays intact.
5. Execute reviewed state transfer / `import` / `moved` steps.
6. Run `plan` on **both stacks** to confirm zero unintended destroys or creates.
7. Confirm the source stack no longer tracks it and the destination stack tracks it cleanly.
8. Lift the freeze and record the change.

### 27.3. Never Drop a Resource From State and Leave It Ownerless

That creates an unmanaged resource and increases drift rather than reducing it. If migrating ownership to Bicep, confirm the owning Bicep module and owner before removing Terraform tracking.

## 28. Remote Terraform State on Azure Storage

An AzureRM backend can store remote state in Azure Blob Storage. **Illustrative backend configuration:**

~~~hcl
terraform {
  backend "azurerm" {
    resource_group_name  = "rg-tfstate-platform"
    storage_account_name = "tfstateplatform001"
    container_name       = "state"
    key                  = "orders/prod.tfstate"
    use_azuread_auth     = true
  }
}
~~~

**Use only after** securely provisioning the Storage account/container and configuring backend auth/role assignments compatible with your Terraform version. Storage names must be valid, globally unique, and verified.

### 28.1. State Locking

Azure Blob Storage backends use Azure Blob leases to lock state, preventing concurrent Terraform applies against the same state. Never disable locking in production to bypass an error without investigating active sessions and owners first.

### 28.2. State Encryption and Access Control

Enforce private endpoints/network restrictions where needed, Entra data-plane RBAC, encryption, and backup/versioning per policy. **Simply reading or editing state can expose sensitive data**—never grant backend access to anyone who doesn't need it.

### 28.3. Isolate Dev and Prod State Properly

Use separate keys, containers, accounts, and identities aligned with trust boundaries. Separate blob keys alone do not isolate permissions if one principal can read every blob in the account.

### 28.4. When a State Lock Appears Stuck

Verify which job is still running, check the Azure resource/lease, and contact the owner. Never run `force-unlock` while an `apply` is still active, or concurrent writers will corrupt state.

## 29. Using Azure Activity Log to Investigate Root Causes

Azure Activity Log captures **management-plane events** across an Azure subscription, helping answer who or what modified a resource or role.

Read-only Azure CLI query when authorized:

~~~bash
az monitor activity-log list \
  --resource-group rg-iac-drift-lab \
  --offset 7d \
  --query '[].{time:eventTimestamp,operation:operationName.value,caller:caller,status:status.value}' \
  -o table
~~~

### 29.1. Correlate the Timeline From Authoritative Sources

When `terraform plan` flags a changed network property, search write operations near the drift window. Correlate correlation/activity IDs, callers, deployment names, and pipeline runs.

### 29.2. Activity Log Does Not Tell the Whole Story

It does not record all data-plane edits like every SQL DDL change or Key Vault secret read, and retention/searchability depend on export settings. Long-term auditing requires dedicated logging architecture.

### 29.3. Distinguish Users from Managed Identities

The caller might be a service principal, managed identity, automation job, or human user. Trace credentials, CI runs, and approvals rather than assuming a generic principal name points to a specific person.

### 29.4. Clock Skew and Eventual Consistency

Ingestion lag can occur between an action and its appearance in logs. Keep timelines in UTC and cross-check multiple sources during investigations.

## 30. Azure Policy: Preventing Drift, Not Just Detecting It

**Azure Policy** evaluates resource compliance and enforces effects per assignment, such as **Audit, Deny, Modify, and DeployIfNotExists** where supported.

### 30.1. `Audit` vs. `Deny`

- **`Audit`**: logs/flags noncompliant resources without blocking operations.
- **`Deny`**: blocks operations violating policy conditions.
- **`Modify`/`DeployIfNotExists`**: patches or appends configuration when supported by conditions and managed identity permissions.

### 30.2. Policy Does Not Replace IaC

Policy enforces broad guardrails like "disallow public blob access"; Bicep/Terraform declares exact SKUs, subnets, and tags for each resource. A resource can be policy-compliant yet still drifted from IaC.

### 30.3. Exemptions Must Be Controlled Exceptions

Policy exemptions require justification, an owner, a narrow scope, an expiration date, and monitoring. Never exempt an entire subscription just to let a CI test resource pass without finding root cause.

### 30.4. `Modify` Effects Can Introduce Out-of-Band Changes

When Azure Policy injects tags or settings, Terraform/Bicep sees diffs on the next run. Align your IaC baseline with policy effects to avoid tug-of-war overwrites.

## 31. Azure Resource Graph and Inventorying Unmanaged Resources

IaC drift detection can miss **unmanaged resources**. Azure Resource Graph enables fast cross-subscription inventory queries by permissions, tags, types, and resource IDs.

Example Azure Resource Graph KQL:

~~~kusto
Resources
| where type =~ 'microsoft.storage/storageaccounts'
| project id, name, resourceGroup, subscriptionId, location, tags
| order by subscriptionId asc, resourceGroup asc
~~~

### 31.1. Inventory Alone Does Not Prove Unmanaged Drift

A Storage account lacking a `managedBy` tag might be a legacy owned resource or simply missing a tag. Cross-reference against your CMDB, IaC ownership catalog, and approved exceptions before classifying it as unmanaged.

### 31.2. Workflow for Finding Unmanaged Objects

1. Query resources across authorized subscriptions/scopes.
2. Extract IDs, types, RGs, owner tags, and creation/update indicators where available.
3. Reconcile against Git IaC declarations and Terraform state.
4. Investigate ownerless resources—never delete automatically.
5. Decide whether to import/adopt, reassign ownership, or decommission with approval.
6. Track remediation and budget impact of unmanaged resources.

### 31.3. Resource Graph May Omit Nested Properties

When verifying firewalls, diagnostic settings, or data-plane access, query the exact resource provider API or dedicated diagnostics instead of assuming a `Resources` query returns everything.

## 32. RBAC and PIM: Reducing Out-of-Band Changes

**Microsoft Entra ID** and **Azure RBAC** govern who can manage resources at subscription, resource group, and resource scopes. **Privileged Identity Management (PIM)** enforces just-in-time privileged elevation where licensed and configured.

### 32.1. Role Separation

| Role | Appropriate Permissions | Should Not Hold by Default |
|---|---|---|
| Developer | Scoped dev/test deploys; read diagnostics | Production Owner |
| SRE on-call | Read logs; PIM/approval-gated emergency rights | Unrestricted permanent prod write |
| Platform engineer | Scoped IaC/network/policy rights | Unneeded business data-plane secrets |
| Security engineer | Policy/RBAC review and incident response | Unneeded artifact-publishing rights |
| CI/CD identity | Deploy scoped resources/stages | Management-group-wide Owner |
| Runtime managed identity | Workload-specific data-plane permissions | Resource management Contributor |

### 32.2. Reduce Manual Write Access in Production

Protected pipelines with dedicated service principals/managed identities, approvals, and audit trails keep production traceable. Emergency break-glass paths may still be needed, yet must be time-bound, justified, and reconciled back into IaC.

### 32.3. Separate Role-Assignment Permissions

A CI job deploying a Container App rarely needs permission to create IAM role assignments. Letting one pipeline both build code and grant itself Owner creates severe supply-chain escalation risk.

### 32.4. Data-Plane RBAC Differs from Management-Plane

Permission to edit a Storage account's ARM properties does not automatically grant access to read blobs. Conversely, data-plane Reader does not allow changing firewalls or policies.

## 33. Azure Resource Locks: Preventing Accidental Deletion

Azure Resource Manager provides **resource locks** such as **`CanNotDelete`** and **`ReadOnly`** at supported scopes.

### 33.1. How Does `CanNotDelete` Help?

It reduces accidental resource deletions, even by identities holding write permissions. However, anyone authorized to manage locks can remove them—locks are not an independent security perimeter.

### 33.2. `ReadOnly` Can Break Legitimate Operations

Many Azure services perform management-plane writes during routine operations, backups, or reads. Applying `ReadOnly` locks indiscriminately can break deployments, backups, and integrations.

### 33.3. Locks Do Not Replace Backups

Delete locks do not protect against data corruption or data-plane deletes. Pair them with tested backups/restores, service-level versioning/immutability, and DR plans.

### 33.4. IaC Modifying a Locked Resource

If a plan proposes destroying/recreating a locked resource, `apply` fails—**never reflexively remove the lock and re-run `apply`**. Investigate why replacement is triggered, protect data, and approve the migration first.

## 34. Change Control: Who May Change What, and When?

An IaC change request should capture:

~~~text
Change ID:
Resource / subscription / RG:
IaC repository + commit:
Reason / business impact:
Expected plan (create, update, replace, delete):
Security/network/RBAC implications:
Data loss and backup assessment:
Cost/quota implications:
Approvers and maintenance window:
Verification / success criteria:
Rollback or forward-fix plan:
Owner / due date:
~~~

### 34.1. Risk-Based Approvals

- **Low:** low-impact tag updates with tests and optional auto-approval per policy.
- **Medium:** SKU, service settings, or scaling edits with budget impact.
- **High:** enabling public access, privileged IAM edits, database replacements, resource deletions, or DR changes.

### 34.2. Review the Plan Before Apply

A two-line diff can open public access or wipe an entire database. Evaluate **semantic impact**, scope, and blast radius—never line count alone.

### 34.3. Approval Does Not Guarantee Every Subsequent Apply Matches the Plan

If live Azure state or Git source changes between approval and execution, the saved plan/`what-if` becomes stale. Enforce revalidation or apply the exact saved artifact matching pinned versions within controlled time windows.

### 34.4. Closing the Change Loop

Post-apply, read back live properties, verify metrics/health/security controls, log the deployment ID, and monitor for recurring drift.

## 35. Protected CI/CD Pipeline for Drift Detection

Reference architecture:

~~~mermaid
flowchart LR
    SCHED[Scheduled drift scan] --> READ[Read-only Azure identity / state]
    READ --> PLAN[Terraform plan / Bicep what-if]
    PLAN --> REPORT[Redacted diff + severity]
    REPORT --> APPROVE{Reviewed and approved?}
    APPROVE -- No --> TICKET[Ticket and investigation]
    APPROVE -- Yes --> APPLY[Protected apply identity]
    APPLY --> VERIFY[Resource readback + smoke/security checks]
    VERIFY --> AUDIT[Change record / alert]
~~~

### 35.1. Separate Scan Jobs from Apply Jobs

Scanners need read/`plan` permissions only—**never production write permissions** unnecessarily. Applies run under a separate identity in a protected environment with human reviewers.

### 35.2. Scheduled Scan Cadence

Depending on risk, run daily for security-critical production IaC, weekly for stable environments, and immediately after emergency changes. Match cadence to policy and SLOs rather than one rigid schedule.

### 35.3. Reports Must Never Leak State or Secrets

Export only summaries, access-controlled resource IDs, change types, severity, tool versions, and links to private run artifacts. Never upload raw Terraform plans or state into public tickets.

### 35.4. Prevent Drift Alert Noise

Assign owners, deduplication keys, severity tiers, expiring suppressions, and failure alerts. A `plan` exiting with code 1 must alert **"scan failed"**, never **"no drift"**.

## 36. Structured Drift Scan Output and Auditing

Sample report:

~~~json
{
  "environment": "production",
  "subscription": "SUBSCRIPTION_ID",
  "iacCommit": "COMMIT_SHA",
  "stack": "orders-platform",
  "tool": "terraform",
  "scanStatus": "DIFFERENCES_FOUND",
  "scannedAtUtc": "2026-11-20T10:00:00Z",
  "counts": {
    "update": 2,
    "replace": 0,
    "delete": 0
  },
  "highestSeverity": "HIGH",
  "reviewRequired": true
}
~~~

This is an **example schema**, not a guaranteed native JSON format from Azure or Terraform. Your report generator must parse plans accurately, redact secrets, and compute counts/risks per organizational rules.

### 36.1. Never Store Secrets in Resource Details

Terraform JSON plans can hold `sensitive` blocks. Restrict parsing to trusted jobs and never dump raw output into Slack or public issues.

### 36.2. Link Reports to Code and Environment

Recording commit SHA, resource group, subscription, tool/provider versions, and plan run ID helps investigators separate legitimate Git changes from out-of-band drift.

### 36.3. Recording Clean Scans Matters Too

Periodic "no changes" logs prove the scanner is alive. Still configure dead-man alerts if scans stop running or lose Azure permissions.

## 37. Pipeline Policies: Blocking Data-Destructive Changes

Recommended pre-production-apply gates:

- Block destroy/replace on production databases or storage without explicit data-impact approval.
- Block enabling public network access or invalid anonymous blob access.
- Block privileged role assignments lacking security sign-off.
- Block deleting critical diagnostics, alerts, or backup policies.
- Block regions, SKUs, or tags outside the Azure Policy baseline.
- Require import/ownership review when adopting existing resources.
- Require plan refresh if too much time elapsed or infrastructure changed since approval.
- Require post-deploy smoke and readback checks.

### 37.1. Use Policy-as-Code Where Appropriate

OPA/Rego, Terraform policy tools, or custom JSON plan validators enforce pipeline gates, complementing Azure Policy's control-plane guardrails. Combine layers instead of trusting a single check.

### 37.2. Avoid False Confidence

Policy parsers can misinterpret unknown values, module boundaries, or provider semantics. Write regression tests for policy rules and keep manual review on high-risk replacements.

### 37.3. Handling Exceptions

Record change ID, risk acceptance, compensating controls, owner, expiration, and rollback plan. Never add an unbounded "skip all policies" flag for production.

## 38. Runbook: Terraform Plan Wants to Replace a Production Database

**Scenario:** a PR only edits tags, yet `terraform plan` on Azure SQL or Storage shows **`-/+` replacement**.

### Step 1 — Halt Apply

Do not merge or apply before investigating. For production, escalate to resource owners and the data team. Never remove a resource lock just to "unblock the job".

### Step 2 — Verify Target Environment

Check subscription ID, RG, Terraform backend key, workspace/stack, provider configuration, module address, and CI identity.

### Step 3 — Identify What Forces Replacement

Which field in the plan is marked **`forces replacement`**? Did location, name, resource group, subnet, SKU, storage account type, or an immutable property change? Check provider and service implications.

### Step 4 — Inspect State Mapping

Compare **`terraform state show`** against the live Azure resource ID. Was a resource address refactored without a `moved` block? Was an object imported from the wrong subscription? Did a provider version upgrade alter schema behavior?

### Step 5 — Check Data and Dependencies

Capture backup and restore readiness per policy. Inspect Private Endpoints, DNS, connected apps, database clients, Key Vault references, and RPO/RTO.

### Step 6 — Choose Remediation Path

- If IaC config is wrong: restore baseline config and re-plan.
- If an address was refactored: add a `moved` block or run controlled state migration.
- If an intentional change truly forces replacement: design parallel provisioning, data copy/sync, cutover, and rollback.
- If re-import is required: review ownership and state; never wipe state hastily.

### Step 7 — Review the Updated Plan

Confirm only authorized changes remain with zero unintended deletes/recreates; attach the sanitized plan summary and approvals—never secrets.

### Step 8 — Controlled Apply and Validation

Execute within the maintenance window; verify resource IDs, app connectivity, health, logs/alerts, data integrity, billing, and follow-up drift scans.

## 39. Runbook: Portal Hotfix Causes Out-of-Band Drift

**Scenario:** during an incident, on-call edits an Azure firewall or scales a VM directly in the Portal. Afterward, Terraform/Bicep reports drift.

### Step 1 — Document the Change

Record incident ID, UTC timestamp, operator/principal, resource ID, before/after properties, rationale, and impact.

### Step 2 — Determine Whether the Change Is Still Needed

A 30-minute temporary mitigation can be reverted to baseline. A long-term fix needs an IaC update and formal review.

### Step 3 — Cross-Check Policy and Security

Did the firewall open public access? Were Key Vault or Storage diagnostics disabled? Were overly broad roles added? For high-risk exposures, trigger security incident response rather than treating it as a minor diff.

### Step 4 — Inspect the IaC Diff

Run `what-if`/`plan` at the exact scope. Check whether other diffs appear alongside the hotfix property.

### Step 5 — Choose Reconciliation Path

- **Revert Azure to Git:** apply baseline if safe.
- **Backport Azure change to Git:** open a PR, test, approve, and apply to codify desired state.
- **Temporary exception:** record expiration, owner, and monitoring alerts.

### Step 6 — Close the Incident

Read back live properties, validate network and service SLIs, and confirm drift is cleared or tracked as a time-bound exception—never stop at "plan exited 0" without checking logs and health.

## 40. Runbook: Imported Wrong Resource or Wrong State Backend

**Scenario:** after `terraform import`, `plan` targets a resource in another subscription or tries to delete a newly created object.

### Step 1 — Do Not Run `apply`

Likely causes include a wrong ARM ID, wrong provider alias, wrong resource address, or wrong backend key.

### Step 2 — Freeze Writes

Halt all related Terraform applies to prevent race conditions. Identify whoever holds any active state lock.

### Step 3 — Snapshot and Inspect

Back up state from the backend per policy. Inspect config addresses, `state list`/`show`, ARM IDs, and provider/subscription bindings. Never paste secrets into chat or tickets.

### Step 4 — Determine True Mapping

One address must track only its intended object. If the wrong object was imported, follow a reviewed ownership removal/migration procedure—never delete the live Azure object.

### Step 5 — Fix Configuration and Plan

Correct the import target, address, ARM ID, module references, or role/scope; re-import cleanly if needed. Run `plan` confirming zero unexpected destroys or recreates.

### Step 6 — Read Back

Verify state and live Azure point to the exact intended ID and no old source stack still writes to it. Run policy and health checks before lifting the freeze.

### Step 7 — Prevent Recurrence

Add pipeline cross-checks for subscription, backend key, and ARM ID, require reviewed `import` blocks, narrow identity scopes, and enforce state-ops runbooks.

## 41. Cost, Quotas, and Performance of Drift Detection

Operating drift detection also carries real costs:

- CI runners/agents executing scheduled plans.
- Azure API requests, Resource Graph queries, and diagnostics.
- Storage backend capacity, versioning, and backups for Terraform state.
- Log Analytics ingestion/retention and ticketing/alert integrations.
- Engineering review time.
- Remediation side effects: SKU, network, backup, or logging changes altering bills.

### 41.1. Drift Scans Do Not Scale Per Pod

Scan IaC at subscription, stack, or resource-group scope—never per AKS Pod. Align scan boundaries with modules, stacks, environments, and ownership.

### 41.2. Signal Quality Matters More Than Scan Frequency

An hourly scan flooding 10,000 duplicate tickets causes alert fatigue so SREs miss real incidents. Tune cadence by risk, deduplicate findings, classify severity, and alert when scans fail.

### 41.3. Cost Drift Matters

Someone upgrading an SKU, enabling multi-region replication, or leaving preview resources behind spikes spend outside the IaC baseline. Pair **Azure Cost Management budgets/alerts** with tag ownership and resource inventories.

### 41.4. A Drift Diff Is Not a Bill

`what-if` and `plan` project configuration changes, not exact billing figures. Estimate costs with the pricing calculator, usage baselines, billing scopes, and service-specific pricing drivers.

## 42. Testing Change Control: Happy Paths and Failure Paths

IaC governance must prove not only that valid deployments succeed, but that **invalid deployments are blocked**.

| Test Case | Expected Behavior |
|---|---|
| PR edits tag in non-prod | Plan reviewed and applied to target scope |
| PR enables public blob access | Policy/security gate blocks or demands approved exception |
| PR deletes production database | Destructive change blocked pending data-impact plan |
| Drift scan when Azure is unreachable | Scan reports FAILED, never "no drift" |
| `terraform plan` returns exit code 2 | Generates diff report, never auto-applies |
| Terraform backend lock active | Job waits or fails cleanly; never runs `force-unlock` |
| Import uses wrong ARM ID | Halted pre-apply; state and resource mapping inspected |
| New unmanaged resource created | Inventory flags it and opens an ownership ticket |
| Emergency Portal edit | Incident + drift review + backport or revert |
| Azure Policy `Modify` updates tag | Trace policy source and align baseline |
| Code edited between `plan` and `apply` | Forces replan and re-approval per policy |
| App unhealthy post-IaC | Halts rollout; triggers rollback or forward-fix |

### 42.1. Test in Labs, Never Rehearse Destruction in Prod

To test forced replacements, use a stateless lab resource or feed mock JSON plans to policy parsers. Never risk production downtime just to verify a gate.

### 42.2. Audit Logs and Evidence

Record test run ID, resource ID, plan summary, approval/rejection decision, and final state. Never dump full state or secrets into reports.

## 43. Lab 1: Detecting Bicep Drift with `what-if`

**Work strictly in your own lab subscription and resource group.** This exercise neither requires nor permits touching production infrastructure.

### A. Preparation

1. Select your lab subscription and verify with **`az account show`**.
2. Create a dedicated resource group, e.g., **`rg-iac-drift-lab`**.
3. Prepare a Bicep template matching Section 11.
4. Pick a valid, globally unique Storage name you can delete after the lab.
5. Verify your identity holds deployment permissions on that lab RG.
6. Ensure zero real business data resides in the Storage account.

### B. Establish Baseline

In your lab directory containing **`main.bicep`**:

~~~bash
RG='rg-iac-drift-lab'
STORAGE='replacewithuniquelabname'

az account show --query '{id:id,name:name}' -o table

az deployment group what-if \
  --resource-group "$RG" \
  --template-file main.bicep \
  --parameters storageAccountName="$STORAGE"

# Only after reviewing and confirming lab resources:
az deployment group create \
  --resource-group "$RG" \
  --template-file main.bicep \
  --parameters storageAccountName="$STORAGE"
~~~

**Do not run these commands until the RG and Storage are confirmed to be lab-only.** Bicep files are not pre-created in this lesson repository; these are instructions for your own lab project.

### C. Introduce a Low-Risk Out-of-Band Edit

In the Azure Portal, change **only the `environment` tag** on the lab Storage account from **`dev`** to **`manual-test`**. Do not enable public access, delete resources, or alter firewalls or encryption to test drift.

### D. Detect Drift

Re-run **`az deployment group what-if`** with the same inputs and inspect the tag diff and resource ID. Record:

| Field | Expected |
|---|---|
| Subscription/RG | Matches lab environment |
| Resource ID | Exact lab Storage account |
| Current tag | `manual-test` |
| Desired tag | `dev` |
| Planned change | Update tag back to baseline |
| Risk | Low, no delete or replace |
| Review | Approve revert or update code with justification |

### E. Reconcile

After lab approval, deploy to restore the baseline tag (or update the template if the change were legitimate). Read back live tags in Portal/Azure CLI, then re-run `what-if` to confirm no diff remains.

### F. Cleanup

Delete resources **only after confirming they are isolated lab resources you are authorized to remove**. Never use wildcards to delete resource groups, and never delete shared resource groups.

### G. Completion Criteria

Demonstrate why Bicep **`existing`** does not manage tags, why `what-if` is a pre-apply prediction, and why even tag edits must be triaged and approved rather than blindly overwritten in production.

## 44. Lab 2: Importing an Existing Resource Group into Terraform

### A. Scenario

Resource group **`rg-iac-drift-lab`** was created beforehand in the Portal. The team wants Terraform to manage it while keeping the exact resource ID and leaving inner resources untouched.

### B. Preflight

1. Confirm the RG belongs to your lab subscription via Azure CLI/Portal.
2. Record its full ARM resource ID.
3. Verify no other state backend or stack manages this RG.
4. Choose resource address **`azurerm_resource_group.lab`**.
5. Write matching Terraform config for provider, RG name, location, and tags.
6. Verify Azure read rights, backend rights, and state locking.
7. Snapshot state if using a shared backend with existing resources.

### C. CLI Import

Run inside your configured lab Terraform directory:

~~~bash
terraform init
terraform fmt -check
terraform validate

terraform import \
  azurerm_resource_group.lab \
  "/subscriptions/SUBSCRIPTION_ID/resourceGroups/rg-iac-drift-lab"

terraform state list
terraform state show azurerm_resource_group.lab
terraform plan
~~~

### D. Post-Import Review

If the live RG has **tags differing from HCL**, `plan` reports an update—that is expected for review, not a failed import. If `plan` predicts **replace or delete**, stop immediately and verify resource address, ID, provider alias, location, and configuration.

### E. Alternative: `import` Block

Instead of CLI import, declare an **`import` block** as in Section 23 on a reviewed branch and run `plan`/`apply` through your workflow. **Never run both methods sequentially for the same address** once the object is already imported.

### F. Expected Results

| Check | Must Confirm |
|---|---|
| Azure resource ID | Unchanged |
| Terraform resource address | Maps to exact RG |
| State backend | Correct project/env |
| Second owner | None |
| Unexpected replacement | None |
| Drift assessment | Only explainable diffs |
| Approval | Recorded before `apply` |

### G. Completion Criteria

A successful import **does not** mean the config is complete. Learners must verify Terraform state, HCL code, and live Azure align post-import, with zero instructions to delete data or recreate the RG.

## 45. Lab 3: Refactoring a Terraform Address with a `moved` Block

### A. Scenario

Terraform state already manages **`azurerm_resource_group.lab`**. The team refactors into modules and wants the new address **`module.foundation.azurerm_resource_group.this`** without touching the live Azure RG.

### B. Steps

1. Create the `foundation` module containing an equivalent RG resource.
2. Move the RG block from the root module into the child module.
3. Write a **`moved` block** with exact old/new addresses as in Section 26.
4. Run **`terraform fmt`**, **`terraform validate`**, and **`terraform plan`**.
5. Confirm `plan` reports a resource move per your tool version—**no destroy or create** of the RG.
6. Review provider configurations and module parameters.
7. Apply only after lab review.
8. Read back `state list` and the Azure RG ID.

### C. Failure Mode

If `plan` predicts destroy/create, inspect the `moved` block, provider alias, module resource type, `for_each`/`count` keys, and configuration mismatches—never run `apply` just to "see what happens".

### D. Key Takeaway

Refactoring Terraform code can change **logical addresses** without changing **Azure resource IDs**. Use `moved` blocks to declare state migrations; use `import` when a resource is not yet tracked in state.

## 46. Lab 4: Building CI Drift Scanning and Change Gates

**Objective:** build a pipeline that detects differences without granting PR jobs production `apply` permissions.

### A. Pipeline Design

~~~text
Scheduled trigger / protected PR
      |
Checkout approved IaC commit
      |
Authenticate read-only identity
      |
Validate source / provider versions
      |
Terraform plan -detailed-exitcode
  or ARM/Bicep what-if
      |
Parse/redact findings
      |
Classify high-risk changes
      |
Open private report / approval
      |
Protected apply job (separate identity)
      |
Readback + smoke/security checks
~~~

### B. Test Cases

- Clean plan → scan succeeds, zero diff.
- Plan returns 2 → diff report generated, no auto-apply.
- Plan returns 1 → scanner error, incident/alert raised.
- High-risk delete → blocked until explicit approval.
- Unknown plan attributes → flagged for review, never silently ignored.
- Backend locked by another job → no `force-unlock`.
- Wrong subscription in env vars → fail fast before any writes.
- Resource created outside IaC → inventory reconciliation ticket opened.
- Scheduled job stops running → dead-man monitoring detects missed scan.

### C. Reporting Fields

| Input | Expected |
|---|---|
| Git commit hash | Traceable |
| Subscription/RG | Explicit, verified |
| Terraform/provider/CLI versions | Recorded |
| Plan status | Clean / difference / error |
| Diff summary | Sanitized |
| Risk score | Derived from approved policy |
| Approver | Named role/change record |
| Apply status | Protected, separate identity |
| Post-apply verification | Azure state + app health |

### D. Completion Criteria

The pipeline leaks zero state or secrets; unauthenticated/untrusted jobs cannot `apply`; scan errors are never reported as clean; and reviews focus on destructive and security-impacting diffs.

## 47. Case Study: Importing a User-Created Production Storage Account

Suppose a Storage account holding real data was created in the Portal with private endpoints, soft delete, backups, diagnostic settings, and SAS consumers. The team decides to bring it under IaC.

### 47.1. What Not to Do

- Paste a raw ARM export and `apply` unreviewed.
- See `-/+` in `terraform plan` and approve anyway because "we're onboarding to IaC".
- Use **`terraform state rm`** to hide errors.
- Remove a `CanNotDelete` lock just to make the deploy green.
- Disable a firewall or commit an account key to Git to make a build pass.
- Import the object into Terraform while leaving an old Bicep stack managing the same resource.
- Assume successful import verified backups, retention, or networking.
- Run labs or migrations against live user-data resources without change approvals.

### 47.2. Recommended Process

1. Build an inventory and owner/source-of-truth catalog.
2. Inspect ARM resource ID, config, tags, networking, encryption, backups, auth, RBAC, and dependencies.
3. Choose the owning IaC engine, state, module, and deployment identity.
4. Capture backups and state snapshots per policy.
5. Author HCL/Bicep matching live state while logging any security gaps separately.
6. Run `what-if`/`plan`/`import` blocks inside a protected workflow.
7. Review every create, replace, delete, and unknown diff.
8. Adopt cleanly via process—avoid bundling major security-property changes into the adoption step if doing so complicates rollback.
9. Read back and test apps, Storage ops, logs, private DNS, and costs.
10. Open follow-up PRs to remediate approved drift and security gaps.
11. Enable scheduled drift detection, restrict manual writes, and document ownership.
12. Validate backup/restore and update change-control documentation.

### 47.3. Why Separate Adoption from Remediation?

Separating the two steps makes it obvious whether an issue stems from state/ownership onboarding or a new security setting. Changing state, networking, identity, and SKUs simultaneously in production makes root-cause analysis far harder.

### 47.4. Success Criteria

Post-adoption, one clear IaC owner exists, every diff is explained, zero unexpected resource replacements occurred, applications retain private-path access, zero data was lost, and all future edits flow through reviewed CI/CD.

## 48. Production Checklist: Drift, Import, and Change Control

- [ ] Every resource/stack has a defined owner and IaC source of truth.
- [ ] Verified no two IaC stacks write to the same Azure resource.
- [ ] Subscription ID, RG, tenant, and resource IDs verified before scan/apply.
- [ ] CI scan and apply jobs use separate identities and scopes.
- [ ] Subscription-wide Owner is never granted to app deployment jobs.
- [ ] Terraform state backend enforces encryption, RBAC, backups, and versioning per policy.
- [ ] State locking is active; never disable locks or run `force-unlock` casually.
- [ ] State files, saved plans, and build logs never expose secrets.
- [ ] Bicep/ARM `what-if` runs before significant changes.
- [ ] `terraform plan` runs with pinned provider and toolchain versions.
- [ ] Plan exit code 1 is treated as an error, never "no drift".
- [ ] Plan exit code 2 enters review and risk classification—never auto-applies.
- [ ] Operators distinguish regular plans from `-refresh-only` plans.
- [ ] Never pass `-refresh=false` to mask drift.
- [ ] Never run `apply -refresh-only` to silently bless unauthorized remote edits.
- [ ] Every replace/delete diff undergoes data-impact assessment and owner sign-off.
- [ ] Stateful Database/Storage resources have verified backup/restore plans pre-migration.
- [ ] Never remove resource locks merely to turn a pipeline green.
- [ ] Bicep `existing` is used strictly for references, never mislabeled as full adoption.
- [ ] Bicep adoption verifies exact resource ID, scope, API version, and `what-if` readback.
- [ ] Terraform import specifies exact ARM ID, resource address, provider, and backend.
- [ ] Every import is followed by `state list`/`show` and a full `terraform plan`.
- [ ] Never import an object already tracked by another state/stack without transferring ownership.
- [ ] Terraform address refactors use `moved` blocks or reviewed state migrations.
- [ ] Never use `state rm` to silence drift without understanding side effects.
- [ ] IaC uses non-secret parameters and an Azure security baseline.
- [ ] Unmanaged resources are inventoried via Azure Resource Graph or CMDB.
- [ ] Azure Activity Log and Policy records support root-cause analysis.
- [ ] Policy guardrails cover public access, networking, IAM, and diagnostics.
- [ ] Azure Policy exemptions carry owners, expirations, and audit trails.
- [ ] PIM/break-glass privileges are time-bound and reviewed post-incident.
- [ ] PRs enforce CODEOWNERS/reviewers alongside tests and policy checks.
- [ ] Prod applies enforce protected environments, exact scopes, and approvals.
- [ ] Plans/sources are revalidated if modified after approval.
- [ ] Drift scans have schedules, owners, reports, and dead-man failure alerts.
- [ ] False positives and known exceptions are tracked—never suppressed indefinitely.
- [ ] Severity classification reflects security, data, and cost impact.
- [ ] Diff reports record commit SHA, provider versions, timestamps, and resource IDs.
- [ ] Raw state/secrets are never posted to tickets, Slack, or public CI artifacts.
- [ ] Emergency Portal edits have incident tickets and backport/revert plans.
- [ ] Post-apply includes live Azure property readback and smoke tests.
- [ ] Monitoring covers data-plane health, app SLIs, and cost shifts.
- [ ] Cleanup scripts delete only explicitly authorized lab/preview resources.
- [ ] Runbooks cover mistaken state imports, wrong subscriptions, and planned replacements.
- [ ] Recovery, rollback, or forward-fix procedures have been rehearsed in non-prod.
- [ ] Periodic reviews audit IaC ownership, access permissions, and drift exceptions.

## 49. Self-Check Questions

1. How do desired state, actual state, and Terraform state differ?
2. Why can a resource outside IaC fail to appear in a drift plan?
3. How does manual drift differ from out-of-band automation drift?
4. How do computed/read-only properties cause plan noise?
5. Can Azure Policy `Modify` cause IaC and Azure to diverge?
6. Does "No changes" guarantee an Azure configuration is completely secure?
7. Why must you use the full ARM resource ID when importing?
8. What does Bicep/ARM `what-if` predict, and what are its limits?
9. Does Bicep maintain a separate Terraform-like state file?
10. Does Bicep's `existing` keyword manage firewalls and tags?
11. How do you adopt a pre-existing resource into Bicep?
12. Why don't ARM export/decompile tools produce production-ready IaC right away?
13. Does an incremental ARM deployment delete every resource missing from the template?
14. When Bicep `what-if` reports `Delete`, what checks are required?
15. How does a Terraform resource address differ from an Azure ARM resource ID?
16. What do `+`, `~`, `-`, and `-/+` mean in `terraform plan`?
17. When `plan` shows 0 diffs, does that mean every Azure resource is managed?
18. How do exit codes 0, 1, and 2 of `terraform plan -detailed-exitcode` differ?
19. Why must exit code 2 be handled explicitly when a script uses `set -e`?
20. How does `terraform plan -refresh-only` differ from a regular `plan`?
21. Does `terraform apply -refresh-only` modify live Azure resources?
22. Why can `-refresh=false` hide drift?
23. Does `terraform import` automatically write complete HCL configuration?
24. After importing, why might Terraform still propose resource replacement?
25. What audit/review advantages do `import` blocks have over CLI `import`?
26. When can `-generate-config-out` be used?
27. Should one Azure resource belong to two independent Terraform states?
28. How does a Terraform `moved` block differ from an `import` block?
29. Does `terraform state rm` delete the Azure resource directly, and what is its risk?
30. Can a Terraform state backend contain secrets?
31. Why is locking required when multiple Terraform pipelines exist?
32. Why should a saved plan file never be made public?
33. How does Azure Activity Log help investigate drift?
34. Does `AzureActivity` record every data-plane operation inside Azure SQL?
35. How does Azure Resource Graph help find unmanaged resources?
36. How does Azure Policy compliance differ from IaC drift detection?
37. How do `Audit`, `Deny`, `Modify`, and `DeployIfNotExists` differ in purpose?
38. Does an Azure Resource Lock replace a backup/restore plan?
39. When should PIM/break-glass access be used, and what follow-up is required post-incident?
40. Should a CI `plan` job hold production `apply` permissions?
41. Why can an approved plan become stale before `apply` runs?
42. Which changes must be blocked without explicit data-impact approval?
43. If `plan` proposes replacing a database on a tag-only PR, what should you do?
44. If you accidentally import a Resource Group into the prod state backend, what is step one?
45. When should you backport a manual hotfix into Git vs. revert it to baseline?
46. How do you verify a scheduled drift scan is genuinely running reliably?
47. Why isn't cost drift always obvious from a tiny code diff?
48. How do you stop an auto-remediation pipeline from amplifying blast radius?
49. After applying drift fixes, what must you verify beyond a clean `plan`?
50. What constitutes complete IaC change control?

## 50. Conclusion

**Drift detection, resource import, and change control** are tightly linked practices for governing Azure infrastructure as code. Drift detection compares an **approved baseline** against **live Azure resources** within tool boundaries and limits; not every diff is an error, yet changes affecting **network exposure, IAM, data, backups, logging, and cost** must be triaged by risk.

With **Bicep/ARM**, use **`what-if`** to preview deployment changes; **`existing`** creates read references only, whereas adopting an existing resource requires writing matching declarations, comparing configuration, and deploying under review. With **Terraform**, align configuration, state, and remote objects using **`plan`**, **`refresh-only`**, **`import`**, **`import` blocks**, **`moved` blocks**, and backend locking so mappings stay reliable without accidentally destroying or recreating stateful resources.

A mature production workflow never auto-fixes every diff blindly. It combines **clear sources of truth and ownership, Entra RBAC/PIM, Azure Policy, protected CI/CD, plan reviews, approvals, audit trails, readback/health checks, and rollback or forward-fix runbooks**. Pairing these with Azure Monitor, Activity Log, Resource Graph, and Cost Management helps catch unintended edits, trace root causes, and sustain repeatable, secure, cost-controlled Azure architectures.
