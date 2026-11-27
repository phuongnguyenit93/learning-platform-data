# Plan Review, Policy Checks, and Destruction Protection

Terraform helps describe Google Cloud infrastructure in code and generates a change plan before applying. However, a single `terraform apply` can create, update, replace, or delete resources serving production. Therefore, reading and approving plans is a critical control step in the Infrastructure as Code (IaC) workflow.

A strong workflow combines three layers: **plan review to understand impact**, **policy checks to automatically block non-compliant configurations**, and **destruction protections to reduce the risk of accidentally deleting resources or data**. On GCP, these controls must work alongside IAM, Organization Policies, service-level protection settings, the Terraform state backend, and CI/CD pipelines.

This lesson covers how to analyze a Terraform plan, export and inspect plan JSON, build policy gates, manage state and change approvals, and design safe destroy procedures for resources such as Compute Engine, Cloud SQL, and Cloud Storage.

## 1. The Terraform Change Lifecycle

An IaC workflow typically includes these steps:

1. Write or edit Terraform configuration.
2. Format and validate syntax, modules, and providers.
3. Initialize the working directory and download required providers/modules.
4. Generate a plan to compare desired configuration against state and current infrastructure.
5. Review the plan and run policy checks.
6. Approve the change according to environment and risk level.
7. Apply the exact approved plan.
8. Verify results, update state, and store deployment evidence.

Overview diagram:

~~~mermaid
flowchart TD
    A[Terraform configuration change] --> B[fmt and validate]
    B --> C[terraform plan -out]
    C --> D[Review human-readable plan]
    D --> E[Policy checks on plan JSON]
    E --> F{Checks passed?}
    F -->|No| G[Fix configuration or request exception]
    G --> B
    F -->|Yes| H[Approval gate]
    H --> I[Apply the reviewed saved plan]
    I --> J[Verify GCP resources and outputs]
    J --> K[Record deployment evidence]
~~~

Do not treat a plan as a simple summary. A plan is Terraform's calculation at a point in time based on configuration, state, providers, and information read from APIs. It may contain values unknown until apply time, and it can become stale when state or infrastructure changes.

### Three Control Layers

| Layer | Question to Answer | Mechanism |
|---|---|---|
| Plan review | Which changes will occur and what is their impact? | Manual review, diffs, saved plans, plan JSON |
| Policy checks | Does the change violate organizational standards? | OPA/Conftest, Sentinel, custom rules, CI policies |
| Destroy protection | Can we prevent or require approval before deleting critical resources? | `lifecycle`, deletion protection, IAM, approvals, backups, and retention |

Each layer addresses a distinct type of risk. Policies can block a public configuration, but cannot replace confirming that an approver understands a database is about to be replaced.

## 2. Reading a Terraform Plan Properly

Generate a saved plan:

~~~bash
terraform init
terraform fmt -check -recursive
terraform validate
terraform plan -out=tfplan
~~~

Inspect the saved plan:

~~~bash
terraform show -no-color tfplan
~~~

A plan typically shows these actions:

| Symbol | Meaning | What to Watch |
|---|---|---|
| `+` | Create resource | New costs, new IAM, new endpoints, quotas |
| `~` | Update in place | Potential disruption, security or data changes |
| `-` | Destroy resource | Impact on services, data, and dependencies |
| `-/+` | Destroy and recreate (replace) | Potential downtime or data loss |
| `+/-` | Create new before destroying old | Capacity, resource naming, and traffic shifting |
| `<=` | Read data source | Values read from infrastructure or external sources |

Some changes look minor in HCL yet trigger replacement. For example, changing an immutable attribute of a VM or Cloud SQL instance can force the provider to delete the old resource and create a new one. Reviewers must look for the note specifying which attribute forces replacement, rather than scanning only resource names.

### Questions to Ask During Review

For each resource in the plan, check:

- Are the Terraform address and containing module right?
- Are project, region, zone, network, subnet, and environment right?
- Will the resource be created, updated, replaced, or destroyed?
- Did any attributes change unexpectedly?
- Are there new IAM bindings or broader permissions?
- Does it unintentionally expose a public IP, public bucket, firewall ingress, or endpoint?
- Are encryption, CMEK, retention, backups, or logging altered?
- Do changes impact quotas, costs, autoscaling, or SLAs?
- Will any dependent resources be cascade-deleted?
- Which values remain unknown and must be verified after apply?

### Distinguishing Update vs. Replace

An in-place update can still cause disruption. For example, modifying database, firewall, or load balancer settings can cause brief connection drops. Replacement usually carries higher risk because Terraform must establish a new resource lifecycle.

For stateful resources, identify where data lives. Replacing a VM does not necessarily lose data if persistent disks are managed separately and preserved, whereas deleting a Cloud SQL instance or bucket can cause data loss without proper backups, versioning, or retention.

## 3. Generating Reviewable Plans and Applying Consistently

In CI/CD, create a saved plan and carry that exact artifact through review and apply steps:

~~~bash
terraform plan -out=tfplan
terraform show -no-color tfplan
terraform show -json tfplan > tfplan.json
~~~

After policy checks and approval succeed, apply the saved plan:

~~~bash
terraform apply tfplan
~~~

This guarantees applying the exact reviewed plan. Running `terraform apply` without a plan file causes Terraform to generate a new plan, and changes may differ from what reviewers approved.

A saved plan is tied to the state and conditions at creation time. If state changes, locks no longer match, or infrastructure drifts such that the plan is no longer valid, Terraform may reject the apply. In that event, generate a new plan and review again; never force an outdated plan.

### Plan Exit Codes in CI

Use `-detailed-exitcode` to distinguish three states:

~~~bash
terraform plan -detailed-exitcode -out=tfplan
~~~

- Exit code `0`: no changes.
- Exit code `1`: error creating plan.
- Exit code `2`: plan has changes.

The pipeline must treat exit code 2 as a state requiring review, not a command execution failure. Only exit code 1 is a plan generation failure.

### Never Apply Unreviewed Plans

Do not use `-auto-approve` as a way to skip review in production. Even in test environments that allow automation, policies and guardrails must still run before apply. Approvals must be tied to commit, workspace, project, plan artifact, and approver for traceability.

## 4. Exporting Plan JSON and Handling Sensitive Data

Terraform can convert a saved plan to JSON:

~~~bash
terraform show -json tfplan > tfplan.json
~~~

Plan JSON suits policy-as-code tools because it provides a machine-readable structure of resource changes, actions, values, dependencies, and metadata.

Commonly inspected fields:

| Field | Contents |
|---|---|
| `resource_changes` | Proposed resource changes |
| `address` | Resource address in the Terraform configuration |
| `type` | Resource type, e.g. `google_compute_instance` |
| `change.actions` | List of actions such as create, update, delete |
| `change.before` | Values before the change |
| `change.after` | Proposed values after the change |
| `change.after_unknown` | Attributes unknown at plan time |
| `change.before_sensitive` and `after_sensitive` | Metadata marking sensitive values |

### Protecting Plan Artifacts

Plan JSON and saved plans can contain sensitive data. Terminal views often mask values marked `sensitive`, yet JSON or binary plans may still contain actual values. Therefore:

- Never upload plan artifacts to public repositories or unprotected issue trackers.
- Restrict artifact read permissions to people and service accounts involved in review.
- Set retention limits aligned with organizational policy.
- Never print full JSON into CI logs.
- Never attach plans containing secrets to regular emails or chats.
- Delete temporary artifacts after the required retention window per storage policy.
- Use mock data in lab environments to demonstrate policies.

Do not treat `sensitive = true` as data encryption. It mainly affects how Terraform displays values; protecting state, plans, and artifacts remains the pipeline's responsibility.

### Reading JSON Selectively

You can use `jq` to inspect changes by resource type and action:

~~~bash
jq -r '
  .resource_changes[]
  | [.address, .type, (.change.actions | join(","))]
  | @tsv
' tfplan.json
~~~

The command above prints only the address, resource type, and actions. When attribute details are needed, generate filtered reports and sanitize sensitive data before sharing.

## 5. Risk Review by GCP Resource Type

Reviewers should focus on the impact of changes on availability, security, data, and cost.

| GCP Resource | Items to Check in Plan |
|---|---|
| Compute Engine | Machine type, boot disk, attached disks, service account, network interfaces, external IP, deletion protection |
| GKE | Cluster location, node pools, version, release channel, workload identity, private cluster, node upgrades |
| Cloud SQL | Database version, HA, backups, PITR, authorized networks, private IP, deletion protection |
| Cloud Storage | Public access prevention, uniform bucket-level access, versioning, retention, `force_destroy`, encryption |
| IAM | Principal, role, project/folder scope, custom roles, service account keys, impersonation permissions |
| VPC/Firewall | CIDRs, ingress/egress, source ranges, target tags/service accounts, routes |
| KMS | Key ring, key version, rotation, protection level, encrypt/decrypt permissions |
| Cloud Run | Revisions, traffic split, ingress, service identity, secret references, min/max instances |

### IAM Changes

An added role may open permissions across an entire project instead of a single resource. Check whether the principal is a user, group, or service account; whether the role is predefined or custom; and whether the binding is at the organization, folder, or project level. Scrutinize broad roles like Owner, Editor, or IAM admin roles.

### Network Changes

Firewall ingress from `0.0.0.0/0`, opening SSH/RDP, changing routes, or assigning external IPs requires clear justification. Cross-check source ranges, targets, and environment. A rule appearing to target one workload can affect many VMs if selectors or target tags are overly broad.

### Storage and Data Changes

When a plan modifies buckets, databases, disks, or keys, reviewers must verify:

- Is any resource being replaced or destroyed?
- Does a recent backup/PITR or snapshot exist, and has restore been tested?
- Are object versioning or required retention policies in place?
- Can encryption keys still decrypt historical data?
- Do consumers, services, or pipelines depend on old names and endpoints?
- Is a migration or phased traffic cutover needed?

## 6. Policy as Code for Terraform Plans

Policy as code turns governance rules into automated checks. Instead of relying solely on human reviewers, pipelines can block non-compliant plans before reaching apply.

Options include:

- **Open Policy Agent (OPA) and Conftest:** evaluate plan JSON against policies written in Rego.
- **Terraform Sentinel:** enforce policies in Terraform Cloud/Enterprise workflows supporting Sentinel.
- **Checkov or IaC static analyzers:** detect risky configurations in HCL or plans per supported frameworks.
- **Custom CI checks:** validate project, region, actions, IAM, public access, and critical resources against internal standards.

Not every tool evaluates the same input. Clarify whether a tool checks HCL, plan JSON, or runtime status. For example, Google Cloud Organization Policy enforces constraints at the organization/folder/project level for supported resources; it is not a general Terraform plan reviewer.

### Common Policy Categories

| Policy Category | Example |
|---|---|
| Location | Allow only organization-approved regions |
| Network | Prohibit wide ingress firewalls without approved exceptions |
| Storage | Buckets must enable public access prevention and uniform bucket-level access |
| Encryption | Sensitive data resources must use CMEK as required |
| IAM | Disallow overly broad roles or out-of-scope bindings |
| Identity | Disallow long-lived service account keys without an exception |
| Reliability | Critical Cloud SQL instances must have backups/HA per tier |
| Cost | Block oversized machine types or excessive resource counts |
| Destruction | Warn or block delete/replace on protected resources |

Policies must distinguish create, update, and destroy. For example, a bucket with public access prevention may be blocked if a plan turns that setting off. A deleted resource has `change.after = null`; policies must handle that case rather than attempting to read post-change attributes.

### Example Policy for Cloud Storage

Illustrative Rego rule verifying created or updated buckets enforce public access prevention. The policy inspects only resources with a post-change state:

~~~rego
package terraform.plan

deny contains msg if {
  some rc in input.resource_changes
  rc.type == "google_storage_bucket"
  rc.change.after != null
  rc.change.after.public_access_prevention != "enforced"

  msg := sprintf(
    "%s must enforce public access prevention",
    [rc.address]
  )
}
~~~

Run Conftest on the plan JSON:

~~~bash
conftest test tfplan.json --policy policy/
~~~

If policy detects violations, the pipeline must halt before approval/apply. In practice, verify the JSON schema of your active Terraform and provider versions, write tests covering create/update/destroy, and ensure policies do not mishandle unknown values.

### Example Policy Blocking Deletion of Critical Resources

Maintain a list of protected resource addresses in policy data or a reviewed configuration file. Illustrative rule:

~~~rego
package terraform.plan

protected_addresses := {
  "google_sql_database_instance.orders",
  "google_storage_bucket.audit_archive",
}

deny contains msg if {
  some rc in input.resource_changes
  rc.address in protected_addresses
  rc.change.actions[_] == "delete"

  msg := sprintf(
    "destruction of protected resource %s requires an approved exception",
    [rc.address]
  )
}
~~~

This is a minimal example. In real pipelines, exceptions need an approver, change request ID, rationale, expiration, and exact scope. Never allow broad wildcard exceptions covering an entire module or project.

### Handling Unknown Values

Some attributes only receive values after apply, such as dynamically allocated IPs or API-generated IDs. Policies must not assume unknown values are safe by default. For critical security attributes, require explicit declaration in configuration or block the plan until the value is determined. Document how unknown values are handled to avoid false positives or false negatives.

## 7. Integrating Policy Checks into CI/CD

A pipeline can run the following steps:

~~~bash
terraform init -input=false
terraform fmt -check -recursive
terraform validate
terraform plan -input=false -out=tfplan
terraform show -json tfplan > tfplan.json
conftest test tfplan.json --policy policy/
terraform show -no-color tfplan
~~~

Next, the system creates an approval gate. Once reviewers approve, the pipeline applies the exact saved plan:

~~~bash
terraform apply -input=false tfplan
~~~

Ensure all steps use the exact same commit, workspace, and artifact. Do not allow the pipeline to regenerate a new plan after approval while retaining the old approved status.

### Separating Permissions Across Stages

| Identity | Appropriate Permissions |
|---|---|
| Pull request validation | Read modules/providers and generate plans with limited permissions |
| Plan reviewer | Read sanitized plans and policy results |
| Apply service account | Permissions to modify only target projects/resources being deployed |
| Destroy approver | Authorization to approve destructive operations per separate procedure |
| Break-glass operator | Controlled emergency privileges, logged and audited after use |

Do not use one service account with Owner across the whole organization for every pipeline. Separate identities by environment and module, grant least-privilege permissions, and prefer Workload Identity Federation for CI/CD over long-lived service account keys.

### Approvals Must Bind to Artifacts

Approval records should retain:

- Commit SHA and pull request.
- Terraform workspace or stack.
- Impacted project, folder, and region.
- Hash or identifier of the saved plan.
- Policy check results.
- List of resources created/updated/deleted/replaced.
- Reviewer, approver, and timestamps.
- Exception ID if applicable.
- Apply timestamp and outcome.

When the plan changes, the previous approval no longer applies. Generate a new plan and review again.

## 8. Protecting Terraform State and the GCS Backend

Terraform state maps resources in configuration to real resources. State can contain sensitive attributes, IDs, endpoints, and secret values. If state is modified or lost, Terraform can miscalculate changes and take unintended actions.

On GCP, the GCS backend is a common choice:

~~~hcl
terraform {
  backend "gcs" {
    bucket = "ORG_TERRAFORM_STATE"
    prefix = "gcp/production/network"
  }
}
~~~

The backend bucket should have:

- IAM restricting which users and service accounts can read/write state.
- Uniform bucket-level access and public access prevention.
- Versioning to support recovering state objects during incidents.
- Retention and backups matching organizational policy.
- Logging and monitoring of access activity.
- Encryption as required, optionally using CMEK when key control is needed.

The GCS backend supports state locking to limit concurrent state modifications. Do not disable locking hastily to work around conflicts. If a pipeline stops and a lock remains, verify no apply process is still running before running `force-unlock`; record the lock ID and reason.

### Never Edit State Manually to "Fix a Plan"

When state drift or broken mappings occur, use appropriate Terraform procedures such as `import`, `moved` blocks, `state mv`, or `state rm` per guidelines and careful review. State commands alter how Terraform manages resources without directly changing GCP resources; mistakes can still trigger destroy/create on the next plan.

Never push state files, state backups, or plan JSON to the repository. Add them to appropriate ignore rules and protect artifacts in CI.

## 9. Deletion Protections in Terraform and GCP

No single toggle protects every resource type. Combine Terraform `lifecycle` rules with GCP-side protection attributes and operational policies.

### Terraform `lifecycle` `prevent_destroy`

Example protecting a critical Cloud SQL instance:

~~~hcl
resource "google_sql_database_instance" "orders" {
  name             = "orders-prod"
  region           = "asia-southeast1"
  database_version = "POSTGRES_15"

  deletion_protection = true

  settings {
    tier = "db-custom-2-7680"
  }

  lifecycle {
    prevent_destroy = true
  }
}
~~~

`prevent_destroy = true` instructs Terraform to reject any plan attempting to destroy the resource while the resource block remains in the configuration. This is a useful guardrail for stateful or critical resources.

Limitations to understand:

- It does not stop someone with permissions from calling the API directly to delete outside Terraform.
- It is not a backup and does not recover data deleted out-of-band.
- Removing the resource block completely from configuration removes the lifecycle rule as well; Terraform can then propose deleting the resource.
- It does not replace IAM permissions or service-side deletion protection.

Therefore, policy gates must detect when critical resources disappear from configuration or are marked for destruction, even when the `lifecycle` block is no longer present.

### Deletion Protection on GCP Resources

Some resources expose dedicated API/provider-level deletion protection attributes. For example:

~~~hcl
resource "google_compute_instance" "bastion" {
  name         = "admin-bastion"
  machine_type = "e2-small"
  zone         = "asia-southeast1-a"

  deletion_protection = true

  boot_disk {
    initialize_params {
      image = "projects/debian-cloud/global/images/family/debian-12"
    }
  }

  network_interface {
    network = "default"
  }
}
~~~

For Cloud SQL, `deletion_protection` can block deleting the instance via API when enabled and supported by the provider version. For Compute Engine, `deletion_protection` protects the instance from delete calls. Check the schema of your project's pinned provider version before using these attributes, as names and behavior can vary across resources and provider versions.

Terraform `prevent_destroy` and GCP deletion protection complement each other: one protects at plan time, the other protects at the resource API. Check both in plans and after apply.

### Cloud Storage and `force_destroy`

For buckets storing logs or business data, do not enable `force_destroy` by default:

~~~hcl
resource "google_storage_bucket" "audit_archive" {
  name                        = "org-audit-archive"
  location                    = "ASIA"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  versioning {
    enabled = true
  }

  lifecycle {
    prevent_destroy = true
  }
}
~~~

`force_destroy = false` prevents bucket deletion from automatically deleting all objects inside. It is not an absolute anti-deletion mechanism. `prevent_destroy` protects the plan while the resource block exists; retention policies and Bucket Lock protect objects for the configured retention period.

Bucket Lock can make a retention policy irreversible once locked. Only lock after the duration, compliance requirements, and deletion process are approved. Never test Bucket Lock on a production bucket.

## 10. Safe Destroy Workflow

Destruction may be necessary when retiring a test environment, replacing a stack, or decommissioning unused resources. For critical resources, destruction requires a dedicated procedure rather than running as an automated cleanup step.

### Before Generating a Destroy Plan

1. Confirm the exact project, workspace, backend, and environment.
2. Inspect the list of resources in state.
3. Identify data, dependencies, and business owners.
4. Verify backups, snapshots, PITR, exports, and retention.
5. Check resource protections, policy exceptions, and IAM permissions.
6. Assess downtime, user impact, and dependency teardown order.
7. Record the change request and approver.

### Create a Dedicated Destroy Plan

~~~bash
terraform plan -destroy -out=destroy.tfplan
terraform show -no-color destroy.tfplan
terraform show -json destroy.tfplan > destroy-plan.json
~~~

Review every resource with a delete or replace action. Use a dedicated policy gate to block protected resource addresses or require time-bound exceptions. Carefully check databases, buckets, KMS keys, disks, backups, networking, and IAM.

Only after approval, apply that exact plan:

~~~bash
terraform apply destroy.tfplan
~~~

Never run `terraform destroy -auto-approve` in production pipelines. Never treat typing `yes` as a complete approval workflow without clear records, reviewers, and scope.

### Guardrails Against Accidental Deletion

Guardrails to combine:

- `prevent_destroy` on critical resources.
- GCP resource deletion protection where available.
- Policies checking delete/replace resource actions.
- IAM restricting delete permissions for the apply identity.
- Independent approval for destroy operations.
- Tested backup/restore procedures.
- Retention and Bucket Lock per data requirements.
- Audit logs for modifications and deletions.
- Project/workspace verification before execution.

Some services have delayed deletion or scheduled waiting periods—for example, Cloud KMS key versions may enter a scheduled destruction period before being permanently destroyed. Understand each service's disable/destroy states and recoverability before including it in teardown procedures.

## 11. Handling Drift, Imports, and Policy Exceptions

Plans can detect discrepancies between state/configuration and real infrastructure. Terraform typically refreshes status from the provider before building a plan. If someone changes IAM, firewalls, or instances directly on GCP, the plan may propose reverting them to match configuration.

### When a Plan Detects Drift

- Verify whether the out-of-band change is legitimate or an incident.
- Identify the owner and timestamp from Cloud Audit Logs.
- Update Terraform code if the change is intentional.
- If a resource is unmanaged, evaluate importing instead of creating a duplicate.
- Generate a new plan and review impacts after adjustments.

Never use `-refresh=false` to mask drift in normal deployments. This flag skips refresh and can produce plans that fail to reflect actual state. Only use it in special diagnostic cases where its limits are understood.

### Managing Policy Exceptions

Some legacy systems may need temporary exceptions. Each exception should document:

- Policy ID and violated rule.
- Affected resource address and project.
- Business justification and accepted risk.
- Compensating controls.
- Requester and approver.
- Expiration date.
- Link to the ticket or change request.

Exceptions must be narrow in resource scope and duration. Never weaken a global policy just so a single workload can deploy a risky configuration.

## 12. Hands-On Scenario: Reviewing Production Cloud SQL and Bucket Changes

A team needs to update infrastructure for the orders system. The intended plan includes:

- Creating a new service account for the application.
- Updating IAM bindings for the Cloud SQL client.
- Changing the Cloud SQL tier.
- Updating the log bucket.
- An unexpected change proposing deletion of an old archive bucket.

### Step 1 — Generate and Save the Plan

~~~bash
terraform plan -out=tfplan
terraform show -no-color tfplan
terraform show -json tfplan > tfplan.json
~~~

### Step 2 — Review by Resource

| Resource | Planned Action | Review Question |
|---|---|---|
| Service account | Create | Are project and purpose right? |
| IAM binding | Update | Are principal and scope properly restricted? |
| Cloud SQL | Update or replace | Does the tier change in-place or force replacement? Is there downtime? |
| Log bucket | Update | Are retention, versioning, and public access prevention preserved? |
| Archive bucket | Delete | Who requested this? Has data been migrated and verified? |

### Step 3 — Run Policy Checks

Run Conftest on the plan JSON. Policies should:

- Block buckets without public access prevention enabled.
- Block overly broad IAM roles without an exception.
- Block destroying the protected archive bucket.
- Require production Cloud SQL instances to have deletion protection and standard backups.

If policy blocks the archive bucket deletion, the pipeline stops. Reviewers inspect the plan, tickets, and data before deciding on an exception or fixing the configuration.

### Step 4 — Approve and Apply

After removing the unexpected bucket deletion or completing a valid exception, generate a new plan. Never reuse an old approval. Reviewers confirm commit, project, saved plan, and policy results before allowing apply of the exact inspected plan file.

### Step 5 — Post-Apply Verification

- Confirm the service account and IAM binding have the right scope.
- Check Cloud SQL health, application connectivity, and backups.
- Confirm buckets retain retention policies, versioning, and public access prevention.
- Check Cloud Audit Logs and deployment records.
- Archive plans, policy reports, approvals, and apply results per policy.

## 13. Plan Review and Destruction Protection Checklist

### Before Reviewing a Plan

- [ ] Correct commit, workspace, backend, project, and environment.
- [ ] `terraform fmt` and `terraform validate` succeeded.
- [ ] Saved plan generated from current state.
- [ ] Plan artifact stored with controlled access.
- [ ] Reviewers can inspect diffs and policy reports.

### During Review

- [ ] Create, update, delete, and replace actions categorized.
- [ ] IAM, firewalls, public access, and encryption checked.
- [ ] Stateful resources, backups, retention, and dependencies inspected.
- [ ] Unknown attributes addressed.
- [ ] Unexpected changes and drift verified.
- [ ] Policy checks executed against the exact plan JSON.
- [ ] Exceptions have an owner, rationale, scope, and expiration.

### Before Apply

- [ ] Approval bound to the exact commit and saved plan.
- [ ] Apply identity holds least-privilege permissions.
- [ ] Plan has not changed or become stale.
- [ ] Appropriate rollback or recovery plan exists.
- [ ] Operators know how to halt on unexpected impact.

### Before Destroy

- [ ] Project, workspace, and resource addresses confirmed.
- [ ] All delete/replace actions reviewed.
- [ ] Backups and restore capability verified.
- [ ] `prevent_destroy`, deletion protection, and retention checked.
- [ ] Dedicated destroy policy gate executed.
- [ ] Independent approval and change request obtained.
- [ ] Dedicated destroy plan generated and saved plan reviewed.
- [ ] Observer and recovery procedures identified.

Plan review, policy checks, and destruction protection form a unified control workflow for Terraform on GCP. When teams understand every action, enforce policies on saved plans, protect state, and require independent approval for destructive changes, infrastructure changes become far more traceable and the risk of accidentally deleting resources or data drops sharply.
