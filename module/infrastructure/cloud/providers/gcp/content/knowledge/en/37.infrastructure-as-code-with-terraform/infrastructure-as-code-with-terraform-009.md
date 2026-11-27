# Importing Existing GCP Resources

In an organization, many Google Cloud resources were created before a project adopted Terraform: VPCs configured by the network team in the Console, buckets created by legacy pipelines, manually deployed VMs, or Cloud SQL instances set up by an earlier project. When bringing these resources under Infrastructure as Code (IaC) management, do not create a duplicate copy and migrate traffic to it. The right approach is to **import the existing resource into Terraform state**, then write and adjust the configuration so Terraform manages the desired state accurately.

Importing is the step of taking over management in state. It does not automatically redesign resources, nor does it guarantee the Terraform configuration already matches the real GCP configuration. Operators must identify the exact resource address, import ID, provider configuration, and backend state; then inspect the plan so an unintended apply does not modify or replace production resources.

## Learning Objectives

After this lesson, you can:

- Explain the role of Terraform state when adopting existing GCP resources.
- Distinguish between the CLI `import` command and declarative `import` blocks in configuration.
- Determine the resource address and import ID for different Google provider resource types.
- Prepare the backend, credentials, and required permissions before importing.
- Write Terraform configuration reflecting current resources and handle post-import drift.
- Use `plan`, `state show`, and `state list` to verify results.
- Recognize risks such as duplicate state management, wrong project/region, ForceNew attributes, and unintended production changes.

## 1. What Problem Does Import Solve?

Terraform manages resources through two components:

- **Configuration:** describes the desired state in HCL, such as a VPC with a specific name, routing mode, and subnet settings.
- **State:** maps resource addresses in the Terraform configuration to real objects on the provider, and stores attributes Terraform needs to plan changes.

When a VPC already exists on GCP but is not yet in state, Terraform does not know which resource address represents that VPC. If you simply write a resource block and run `apply`, Terraform may attempt to create a new VPC. If the name is already taken, creation fails; if the name differs, the system may create duplicate resources.

Importing establishes the mapping between a resource address and a remote object:

~~~text
Existing resource on GCP
          |
          | import
          v
Terraform state: google_compute_network.shared
          |
          | plan / refresh
          v
Compare HCL configuration with actual state
~~~

After importing, Terraform can read the resource and compare it against the configuration. If the configuration accurately describes the current state, `plan` usually shows no changes needed. If differences exist, Terraform proposes updates or replacements depending on the resource's attributes and schema.

**Importing is not a resource creation operation.** Its goal is to bring an existing object under the management scope of a state.

## 2. Concepts to Distinguish

| Component | Meaning | Example |
|---|---|---|
| Provider | Plugin communicating with GCP APIs | `hashicorp/google` |
| Resource type | Type of resource Terraform manages | `google_compute_network` |
| Resource address | Address of the resource in configuration/state | `google_compute_network.shared` |
| Import ID | Identifier the provider uses to locate the remote resource | `projects/my-project/global/networks/shared-vpc` |
| State | Mapping data and attributes of Terraform-managed resources | State in GCS backend |
| Drift | Difference between configuration/state and real resource | Console changed routing mode |
| Import block | Declarative import in HCL | `import { to = ... id = ... }` |
| CLI import | Command directly importing one resource into state | `terraform import ...` |

Resource address and import ID are two different values:

- The resource address tells Terraform where in the configuration the resource will be managed.
- The import ID tells the Google provider which object to look up on GCP.

For example, the same VPC can be managed at address `google_compute_network.shared` in the root module or `module.network.google_compute_network.shared` in a child module. The import ID still references the VPC on GCP.

## 3. Preparing Before Importing

Importing into the wrong state or wrong project can create long-term governance risks. Complete the following steps before starting.

### Identify Current Ownership

Gather information:

- Project ID, and folder/organization if applicable.
- Resource type, name, region, or zone.
- Business owner and current operating team.
- Whether the resource is already managed by another Terraform state.
- Dependencies such as subnets, firewall rules, service accounts, disks, IAM policies, or databases.
- Target environment: development, staging, or production.

A remote resource should only be managed by one Terraform state at a time. If another state already manages that object, agree on an ownership transfer plan before importing. Never create a second independent mapping for the same object, as two states could simultaneously propose modifying or destroying the resource.

### Check Terraform and Google Provider Versions

Import blocks are supported starting in Terraform 1.5.0. Configuration generation via `generate-config-out` is also available from Terraform 1.5.0. Check the CLI and provider versions used by your repository:

~~~bash
terraform version
terraform providers
~~~

Keep the provider version already tested by the project and commit `.terraform.lock.hcl`. Do not upgrade the provider inside a change intended solely for importing, because schemas and how the provider reads attributes can change across versions.

### Prepare Authentication and IAM Permissions

The Google provider can use Application Default Credentials (ADC), service account impersonation, or an organization-approved workload identity mechanism. Avoid putting service account keys in source code or configuration files.

The identity performing the import needs permission to read resource metadata via Google Cloud APIs. Depending on the resource type, additional permissions may be required to read related attributes. The GCS backend also needs permissions to read/write state objects and use locking.

Example provider configuration:

~~~hcl
provider "google" {
  project = var.project_id
  region  = var.region
}
~~~

Authentication settings should be configured outside HCL per execution environment. Verify project and region values before running commands.

### Prepare the Terraform Backend

For shared environments, use a remote backend so team members work against the same state. The Google Cloud Storage backend supports state locking. The state bucket should have versioning, least-privilege IAM, and appropriate protection policies since state can contain sensitive data.

Example:

~~~hcl
terraform {
  backend "gcs" {
    bucket = "company-terraform-state"
    prefix = "gcp/network/production"
  }
}
~~~

The backend bucket must be created and secured beforehand. Do not use an application data bucket to store state unless specifically designed for it. Separate state by management scope and environment to reduce blast radius.

After configuring the backend, initialize the working directory:

~~~bash
terraform init
~~~

If migrating a local state to a new backend, use a controlled state migration workflow and read Terraform's prompts carefully. Never initialize a brand-new empty state and import while an old state still manages the same resources.

### Back Up and Lock State

Before importing:

- Confirm the correct backend and workspace.
- Ensure no other pipeline or operator is modifying state concurrently.
- Inspect current state with `terraform state list`.
- Back up state following your organization's secure storage procedure.
- Never commit state backups to Git or paste state into public chats/tickets.

A remote backend with locking helps prevent concurrent writes, but does not replace team coordination. Never edit state JSON by hand.

## 4. Two Ways to Import Resources into Terraform

Terraform provides two primary methods.

| Method | Mechanism | When Appropriate |
|---|---|---|
| CLI import | Run `terraform import` to add the mapping to state immediately | Importing individual resources, controlled manual operations, or legacy workflows |
| Import block | Declare import in HCL, preview in plan, and execute via `terraform apply` | Recording import intent in code, reviewing via pull requests and CI |

Both methods require specifying the exact resource address and import ID. Import blocks make the process reviewable and reproducible from the repository; CLI import suits direct state operations.

## 5. Method 1: Importing with the Terraform CLI

Syntax:

~~~bash
terraform import RESOURCE_ADDRESS IMPORT_ID
~~~

For example, a VPC named `shared-vpc` already exists in project `my-project`. The configuration already contains the resource block:

~~~hcl
resource "google_compute_network" "shared" {
  project                 = "my-project"
  name                    = "shared-vpc"
  auto_create_subnetworks = false
}
~~~

Import the VPC into state:

~~~bash
terraform import google_compute_network.shared projects/my-project/global/networks/shared-vpc
~~~

Then verify:

~~~bash
terraform state list
terraform state show google_compute_network.shared
~~~

The `terraform import` command updates state, does not generate complete HCL automatically, and does not alter the VPC configuration on GCP. The resource block must exist in the configuration so Terraform knows the target address. After importing, run `terraform plan` to see whether the configuration matches the real resource.

### Importing into a Module

If the resource is inside a child module:

~~~bash
terraform import module.network.google_compute_network.shared projects/my-project/global/networks/shared-vpc
~~~

If the resource uses `for_each`, the address must include the key:

~~~bash
terraform import 'google_compute_network.vpc["production"]' projects/my-project/global/networks/prod-vpc
~~~

On PowerShell, Bash, or CI shells, quoting rules for addresses may differ. Check your shell so quotes and brackets are passed intact to Terraform.

### Limitations of CLI Import

- Each `import` command maps one remote object to one resource address.
- The command does not automatically generate complete configuration.
- Do not import the same object into multiple resource addresses or multiple independent states.
- Do not use `import` to replace an existing state migration workflow.
- The resource must support import in the Google provider; check the Import section of the specific resource documentation.

## 6. Method 2: Declaring an `import` Block in HCL

An `import` block lets you describe the object to import directly in configuration.

Example:

~~~hcl
resource "google_compute_network" "shared" {
  project                 = "my-project"
  name                    = "shared-vpc"
  auto_create_subnetworks = false
}

import {
  to = google_compute_network.shared
  id = "projects/my-project/global/networks/shared-vpc"
}
~~~

Run:

~~~bash
terraform init
terraform fmt -check
terraform validate
terraform plan
~~~

The plan shows which resource address Terraform intends to import into and whether any other changes are proposed. If the configuration matches the existing resource, the plan may consist solely of the import action without modifying the remote object.

After reviewing the plan, run:

~~~bash
terraform apply
~~~

The `import` block is processed during `apply`. If the plan includes unexpected updates or replacements, do not proceed with `apply`. Adjust HCL or investigate the differences first.

The `import` block can remain in the repository as part of declarative history. After import completes, you can remove the `import` block if the team prefers not to keep import directives in configuration; the resource block and state mapping continue managing the resource.

## 7. Generating Initial Configuration with `generate-config-out`

When no resource block exists yet, Terraform can generate a preliminary configuration from the imported object. This feature requires Terraform 1.5.0 or later.

Example declaring only the `import` block:

~~~hcl
import {
  to = google_compute_network.shared
  id = "projects/my-project/global/networks/shared-vpc"
}
~~~

Generate configuration:

~~~bash
terraform plan -generate-config-out=generated.tf
~~~

Terraform reads the resource via the provider and writes suggested configuration to `generated.tf`. Afterward:

1. Read the entire generated file.
2. Remove default or unnecessary attributes as appropriate for repository standards.
3. Introduce variables, modules, and project naming conventions.
4. Check attributes with sensitive values or environment dependencies.
5. Run `terraform fmt` and `terraform validate`.
6. Re-run `terraform plan` to see the exact changes that will occur.

Generated configuration is only a starting point. It may contain more attributes than needed, hardcoded values, or attributes not yet suited to module structure. Never promote a generated file straight to production without review.

## 8. Import IDs for Common Google Cloud Resources

The Google provider defines import IDs per resource type. Some resources accept a simple name; others require a full path including project, region, or zone.

Common examples:

| Terraform resource | Illustrative Import ID |
|---|---|
| `google_project` | `my-project` |
| `google_compute_network` | `projects/my-project/global/networks/shared-vpc` |
| `google_compute_subnetwork` | `projects/my-project/regions/asia-southeast1/subnetworks/app-subnet` |
| `google_compute_instance` | `projects/my-project/zones/asia-southeast1-a/instances/app-vm` |
| `google_compute_firewall` | `projects/my-project/global/firewalls/allow-internal` |
| `google_storage_bucket` | `company-archive-bucket` |
| `google_sql_database_instance` | `projects/my-project/instances/orders-db` |

These are common illustrative ID formats. Check the import documentation for the exact resource and locked Google provider version in your project before running. Never infer an ID solely from a display name in the Console.

### Why Are Project, Region, and Zone Needed?

Resource names are often unique only within a scope. For example:

- Compute Engine networks are global resources within a project.
- Subnetworks belong to a region.
- VMs belong to a zone.
- Cloud SQL instances belong to a project.
- Cloud Storage buckets have globally unique names in the bucket namespace.

If project or location is missing from the import ID, the provider may fail to find the resource or find a different object with the same name in another scope.

## 9. Hands-On Example: Adopting an Existing VPC and Subnet

Suppose project `my-project` has:

- VPC `shared-vpc`.
- Subnet `app-subnet` in region `asia-southeast1`.
- The VPC does not use auto-created subnetworks.
- The subnet has a primary IP range approved by the network team.

### Step 1: Configure Provider and Resources

~~~hcl
provider "google" {
  project = "my-project"
  region  = "asia-southeast1"
}

resource "google_compute_network" "shared" {
  project                 = "my-project"
  name                    = "shared-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "app" {
  project       = "my-project"
  name          = "app-subnet"
  region        = "asia-southeast1"
  network       = google_compute_network.shared.id
  ip_cidr_range = "10.20.0.0/20"
}
~~~

The CIDR and attributes in the example must be replaced with the actual configuration. Never choose a new CIDR if the subnet already has an address range serving workloads.

### Step 2: Declare Imports

~~~hcl
import {
  to = google_compute_network.shared
  id = "projects/my-project/global/networks/shared-vpc"
}

import {
  to = google_compute_subnetwork.app
  id = "projects/my-project/regions/asia-southeast1/subnetworks/app-subnet"
}
~~~

### Step 3: Generate and Review the Plan

~~~bash
terraform init
terraform fmt
terraform validate
terraform plan
~~~

Verify:

- Both resources are recognized as scheduled to be imported.
- No new resource with the same name is proposed for creation.
- Terraform does not propose unexpected CIDR or network configuration changes.
- The `network` reference in the subnet points to the right VPC.
- No out-of-scope destroy/replace actions appear.

### Step 4: Import and Verify State

After the plan is reviewed and approved according to project procedures:

~~~bash
terraform apply
terraform state list
terraform state show google_compute_network.shared
terraform state show google_compute_subnetwork.app
~~~

Finally run:

~~~bash
terraform plan
~~~

The goal is for the plan to show no unexpected changes. If Terraform proposes changes, determine the root cause before the next apply.

## 10. Hands-On Example: Importing a Cloud Storage Bucket

Suppose bucket `company-archive-bucket` already exists. The resource block must accurately describe its active attributes.

~~~hcl
resource "google_storage_bucket" "archive" {
  project                     = "my-project"
  name                        = "company-archive-bucket"
  location                    = "ASIA-SOUTHEAST1"
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
}
~~~

Import block:

~~~hcl
import {
  to = google_storage_bucket.archive
  id = "company-archive-bucket"
}
~~~

If using the CLI:

~~~bash
terraform import google_storage_bucket.archive company-archive-bucket
~~~

After importing, inspect attributes such as location, storage class, uniform bucket-level access, retention policy, versioning, lifecycle rules, encryption, and public access prevention. The bucket may hold production data; modifying retention or lifecycle rules can affect data accessibility and retention.

Do not add lifecycle rules or change public access settings merely to keep HCL shorter. Reflect the currently approved state and separate design changes from the import operation.

## 11. Handling Post-Import Drift

After importing, Terraform refreshes actual attributes and compares them with HCL. Some differences are normal because the legacy resource was created via the Console or another tool.

For example:

- The resource has labels added by another system.
- The VPC uses a routing mode different from the value in HCL.
- The bucket has versioning enabled, which is not yet declared in configuration.
- The VM has a different machine type, disk, or metadata than expected.
- Cloud SQL has backups, maintenance windows, or database flags configured outside Terraform.

### Classifying Differences

| Type of Difference | Action |
|---|---|
| Actual attribute is correct and should be kept | Add it to HCL or use the matching value |
| Attribute inferred/defaulted by the provider | Check schema and plan; avoid redundant declarations causing diffs |
| Unapproved manual change | Clarify with owner and decide whether to revert or accept |
| Sensitive or unmanaged attribute | Consider a data source or an appropriate management approach |
| Attribute forcing resource replacement | Evaluate downtime, data, and migration plan before acting |

### Understanding Actions in a Plan

- **No changes:** configuration and state/remote object match across Terraform-managed attributes.
- **Update in-place:** Terraform expects to update attributes the provider permits changing directly.
- **Destroy and create / replacement:** one or more attributes require replacing the resource; this can cause downtime or data loss without a plan.
- **Read:** Terraform only reads a data source or refreshes information.

After importing, never run `apply` just to make the plan "green." If replacement appears, check which attribute forces replacement, its impact, and migration options. Some resources have `ForceNew` fields; changing such a field causes Terraform to create a new resource and destroy the old one.

## 12. Importing Multiple Resources and Organizing Modules

When adopting an existing system, you often need to import multiple related resources. Group them by management boundary rather than importing everything into one giant state.

For example, a network group can manage:

- VPCs and subnets.
- Firewall rules.
- Cloud Router and Cloud NAT.
- Static external IPs.
- Load balancer components.

A compute group can manage:

- VMs and boot disks.
- Instance templates and Managed Instance Groups.
- Service accounts and related IAM bindings.
- Health checks and autoscaling policies.

### Import Order

Start with foundational resources referenced by other resources, such as projects, networks, and subnets; then import compute, databases, and dependent components. This ordering makes it easier to write references in HCL and read plans.

However, import order does not create dependencies by itself. Terraform determines dependencies from expression references and meta-arguments in the configuration. Declare explicit references rather than hardcoding IDs when resources are managed in the same module.

### Import Blocks with Multiple Resources

Multiple `import` blocks can be declared in the same configuration:

~~~hcl
import {
  to = google_compute_network.shared
  id = "projects/my-project/global/networks/shared-vpc"
}

import {
  to = google_compute_firewall.internal
  id = "projects/my-project/global/firewalls/allow-internal"
}

import {
  to = google_storage_bucket.archive
  id = "company-archive-bucket"
}
~~~

Each block needs a unique target address and an accurate import ID. When importing at scale, break the work into small groups by service or dependency to make reviews and state rollbacks easier.

## 13. Special Scenarios to Handle Separately

### Resource Already in Another Terraform State

Never import into a new state before identifying the current state and owner. If ownership must be transferred, plan a state migration with appropriate Terraform tooling and verify mappings before and after. Never let two pipelines apply to the same resource.

### Resource Not Supported for Import by the Provider

Check the resource documentation. If the provider does not support import, you may need an alternative resource, a data source, a tested provider upgrade, or a redesigned management approach. Never edit state JSON by hand to force a mapping.

### Resource Inside a Module or Using `count`/`for_each`

The address must match the configuration structure exactly, including module path and instance key/index. A wrong address can cause import to fail or attach the resource to an unintended location.

### Resource with External Dependencies Outside Terraform

A VM may depend on service accounts, subnets, disks, firewall rules, and metadata managed by another system. Importing the VM does not automatically import those dependencies. Decide which dependencies belong to this state, which belong to another state, and which only need to be read with data sources.

### Resources Holding Data or Hard-to-Reverse Impacts

Buckets, databases, disks, and IAM resources hold critical data or access controls. Importing does not modify the remote object, but a subsequent `apply` can alter retention, encryption, network access, or delete the resource. Check lifecycle rules, deletion protection, and backups before making changes.

## 14. Useful Terraform Commands When Importing

| Command | Purpose |
|---|---|
| `terraform version` | Confirm CLI version |
| `terraform init` | Initialize backend and providers |
| `terraform providers` | Inspect configured providers |
| `terraform fmt` | Standardize HCL |
| `terraform validate` | Validate configuration structure |
| `terraform plan` | Preview proposed changes |
| `terraform plan -generate-config-out=generated.tf` | Generate preliminary configuration for resources without blocks |
| `terraform import ADDRESS ID` | Import one resource into state |
| `terraform state list` | List resource addresses in state |
| `terraform state show ADDRESS` | Inspect state attributes of a resource |
| `terraform state pull` | Read the current state from backend |
| `terraform plan -refresh-only` | Preview plan updating only state to match remote |

Commands that read state may display sensitive attributes. Run them only in trusted environments and never share outputs containing secrets.

## 15. Pre- and Post-Import Production Checklist

**Before importing**

- [ ] Correct project, organization, region, and zone identified.
- [ ] Confirmed the resource is not already managed by another Terraform state.
- [ ] Service owner and scope of resources to adopt agreed upon.
- [ ] Terraform and Google provider versions verified.
- [ ] ADC/impersonation and least-privilege IAM permissions configured.
- [ ] GCS backend, prefix, locking, and versioning verified.
- [ ] Current state backed up following secure procedures.
- [ ] Resource block or `import` block written with exact address and import ID.
- [ ] Dependencies and critical attributes checked.

**After importing**

- [ ] `terraform state list` displays the expected resource addresses.
- [ ] `terraform state show` confirms the right project, name, and location.
- [ ] No resource was duplicated or managed by two states.
- [ ] `terraform plan` proposes no unexpected changes.
- [ ] Any update or replacement has been separately reviewed and approved.
- [ ] HCL is formatted, parameterized, and placed in appropriate modules.
- [ ] State backend has IAM, versioning, and backup procedures.
- [ ] CI/CD uses the right workspace/backend and provider lock file.
- [ ] Runbooks or operational docs updated when ownership changes.

## Conclusion

Importing is the step of bringing existing GCP resources under Terraform management via state mapping. CLI import suits direct operations; `import` blocks record import intent in HCL and enable review through plans. Success is more than the import command finishing: configuration must reflect real resources, state must reside in the right backend, dependencies and ownership must be clear, and post-import plans must contain no unexpected changes. By importing in small batches, maintaining backups, and reviewing plans carefully, organizations can bring manually created infrastructure into IaC while minimizing the risk of production disruption.

## References

- [Terraform: Import existing resources](https://developer.hashicorp.com/terraform/language/import)
- [Terraform CLI: import command](https://developer.hashicorp.com/terraform/cli/commands/import)
- [Terraform: Import block reference](https://developer.hashicorp.com/terraform/language/block/import)
- [Terraform: Generate configuration](https://developer.hashicorp.com/terraform/language/import/generating-configuration)
- [Terraform: State](https://developer.hashicorp.com/terraform/language/state)
- [Terraform: GCS backend](https://developer.hashicorp.com/terraform/language/backend/gcs)
- [Google provider: Resource documentation](https://registry.terraform.io/providers/hashicorp/google/latest/docs)
- [Google provider: Compute network resource](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_network)
- [Google provider: Compute subnetwork resource](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_subnetwork)
- [Google provider: Compute instance resource](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_instance)
- [Google provider: Storage bucket resource](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/storage_bucket)
