# Provider Authentication, Variables, Outputs, and Data Sources

In the **Infrastructure as Code** chapter of the **CLOUD_PROVIDERS_ORACLE** module, these four components determine which identity Terraform uses to connect to OCI, where it receives configuration from, what data it can read, and what results it provides for subsequent deployments.

The overarching scenario is preparing network information for a Java application: the infrastructure team already has a VCN in an assigned compartment; the Terraform configuration needs to read the correct VCN and the region's Availability Domains, verify scope, and then output a result object for a pipeline or subsequent Compute deployment module. Through this, learners practice tenancy, compartment, IAM, and VCN fundamentals before automating other OCI services.

The main hands-on lab only declares the provider, variables, locals, data sources, and outputs. It does not create Compute, databases, or new network resources. The extension sections at the end only illustrate how to use the results in a resource or child module.

## 1. Distinguishing the Role of Each Component

| Component | Question Answered | OCI Example |
| --- | --- | --- |
| Provider requirement | Which plugin and version constraints are needed? | `source = "oracle/oci"` |
| Provider configuration | Under which identity and region are OCI calls made? | `auth`, profile, region |
| Input variable | What is the caller allowed to vary in the configuration? | Compartment OCID, VCN OCID, environment |
| Local value | Which internal expressions need to be computed and reused? | Common tag set, standardized names |
| Data source | Where is existing information read from? | VCN details, Availability Domain list |
| Managed resource | Which objects does Terraform manage the lifecycle of? | A subnet declared with `resource` |
| Output | Which results does the module expose to consumers? | VCN OCID and deployment context |

Do not confuse `provider "oci"` with an OCI user. The provider is the plugin that communicates with the service; the principal used by the provider's authentication mechanism is the identity that IAM evaluates.

Do not confuse a `variable` named `compartment_ocid` with "logging into a compartment." A compartment defines resource scope; it does not grant permissions. Two people running the same variable file can get different results if IAM grants them different permissions.

~~~mermaid
flowchart LR
    A["Profile or runner identity"] --> P["OCI Provider"]
    V["Variables: target region and OCIDs"] --> P
    V --> D["Data sources"]
    P --> D
    D --> L["Locals and expressions"]
    L --> O["Outputs"]
    D --> R["Resource or module consuming data"]
    V --> R
    R --> O
~~~

Terraform builds dependency relationships from references; it does not execute `.tf` files sequentially by filename. Splitting `providers.tf`, `variables.tf`, or `outputs.tf` primarily helps organize code within the same module.

## 2. Provider Requirement vs. Provider Configuration

### 2.1. Declaring the Plugin and Version

Example `versions.tf`:

~~~hcl
terraform {
  required_version = ">= 1.10.0, < 2.0.0"

  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "~> 9.14.0"
    }
  }
}
~~~

In the example:

- `required_version` applies to the Terraform CLI.
- `source` identifies the provider in the registry, not credentials.
- `version` constrains the plugin version. `~> 9.14.0` allows from `9.14.0` up to before `9.15.0`.
- `.terraform.lock.hcl` records the selected provider version and checksums for consistent installation.

The example selects the 9.14 provider branch to illustrate a specific version constraint; it does not require every project to upgrade to this branch. When applying this to an existing repository, use the version approved by the project and review changes when upgrading. References: [OCI provider release v9.14.0](https://github.com/oracle/terraform-provider-oci/releases/tag/v9.14.0), [Provider requirements](https://developer.hashicorp.com/terraform/language/providers/requirements), and [Dependency lock file](https://developer.hashicorp.com/terraform/language/files/dependency-lock).

`terraform init` downloads and installs plugins according to the configuration. In a lab using local state, a successful `init` does not prove the principal has permission to read the VCN. You must actually evaluate the data sources in a plan.

Store the root configuration's lock file in version control. Do not run `init -upgrade` on every deployment if the goal is to reuse a controlled set of dependencies.

### 2.2. Connection Configuration

Provider configuration selects the authentication method and region:

~~~hcl
provider "oci" {
  auth                = var.oci_auth
  region              = var.region
  config_file_profile = var.oci_auth == "InstancePrincipal" ? null : var.oci_config_profile
}
~~~

This is the provider used in the lab. The variables will be fully declared in section 5. When using `InstancePrincipal`, an API key profile is not the runner's credential source; the example passes `null` for the profile attribute in that case.

Do not set a default `compartment_id` for every resource through the provider. Each resource or data source has its own schema; many OCI operations still require an explicit compartment argument.

Region is where regional APIs are called, not a home region inferred from a compartment name. Whichever region a VCN belongs to, the provider reading that VCN must point to that same region.

## 3. Choosing an Authentication Mechanism for Where Terraform Runs

### 3.1. Main Options

| `auth` | Appropriate Context | Prerequisites |
| --- | --- | --- |
| `APIKey` | Developer workstation or runner provisioned with a signing key | User, tenancy, fingerprint, and protected private key |
| `SecurityToken` | Interactive user session using an OCI CLI token | Profile with a valid, unexpired token and corresponding signing data |
| `InstancePrincipal` | Runner executing on OCI Compute | Instance in an appropriate dynamic group with matching policies |
| `ResourcePrincipal` | OCI environment providing a resource principal | Runtime and IAM configured for that resource type |
| `OKEWorkloadIdentity` | OKE workload configured with workload identity | Corresponding cluster, namespace, service account, and policy |

This choice depends on the execution environment; an arbitrary container outside OCI does not automatically have an instance principal. Temporary tokens must also remain valid for the duration of the job. Reference: [Configuring the OCI Terraform Provider](https://docs.oracle.com/en-us/iaas/Content/dev/terraform/configuring.htm).

The lab allows three values: `APIKey`, `SecurityToken`, and `InstancePrincipal`. The remaining two mechanisms require dedicated runtime configuration, not merely changing a string in a variable file.

### 3.2. Developer Workstation: Using an OCI Profile

For an API key, store the configuration outside the repository, for example at `~/.oci/config`:

~~~ini
[LEARNING]
user=ocid1.user.oc1..<user-id>
tenancy=ocid1.tenancy.oc1..<tenancy-id>
fingerprint=<fingerprint-of-registered-public-key>
key_file=C:/Users/<account>/.oci/oci_api_key.pem
region=ap-singapore-1
~~~

Placeholders must be replaced with real values. Register the public key on the OCI user; the private key stays on the machine or in the runner's credential store. `key_file` is the attribute name inside an OCI profile; `private_key_path` is the corresponding attribute name when configuring the provider directly.

If the key has a passphrase, use the passphrase-supplying mechanism appropriate for the environment's profile/provider. Do not remove the passphrase or copy the private key into `.tfvars` just to avoid configuring credentials.

To use a Security Token session established via OCI CLI, set `oci_auth = "SecurityToken"` and the name of that session's profile. Do not assume a profile containing only an API signing key also contains a valid security token.

### 3.3. OCI Compute: Using Instance Principal

A runner on OCI Compute can use:

~~~hcl
provider "oci" {
  auth   = "InstancePrincipal"
  region = var.region
}
~~~

This configuration is an **alternative** to the provider in section 2, not a second default block added concurrently.

The runner must belong to a suitably scoped dynamic group, such as one matching the specific instance running the job. IAM policies must grant permission to read data or manage the resources the job actually uses. No long-lived user API signing key needs to be stored on the runner with this mechanism.

The principal's permissions should match the task. A job that only reads a VCN does not need permission to create/delete all resources in the tenancy. When separating plan and apply jobs, keep in mind that plan still needs to read OCI state and data.

### 3.4. Authentication Does Not Replace Authorization

For the lab, the principal needs to read the target VCN and call the API to list Availability Domains at the corresponding scope. Example reference policy for a user group:

~~~text
Allow group id <GROUP_OCID> to read vcns in compartment id <COMPARTMENT_OCID>
Allow group id <GROUP_OCID> to inspect compartments in compartment id <COMPARTMENT_OCID>
~~~

The second policy relates to operations such as `ListAvailabilityDomains` in the IAM permission matrix. An administrator must place the policy where it takes effect on the target compartment and replace all placeholders. For instance principal, use policies targeting the runner's dynamic group. References: [Core Services policy reference](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/corepolicyreference.htm) and [IAM policy reference](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/iampolicyreference.htm).

This is not a policy for creating subnets or Compute. When expanding the exercise to provisioning, identify the additional manipulation and usage permissions for the related resources.

### 3.5. Avoiding Mixed Credential Configuration Sources

There are two layers to keep separate:

1. Terraform receives variable values, such as `TF_VAR_region` assigned to the `region` variable.
2. The OCI Provider resolves the arguments and credential sources it supports, such as profiles or `OCI_*` variables.

`TF_VAR_project_name` only becomes a Terraform input if the module declares a corresponding variable; it does not automatically become an OCI attribute. Conversely, variables such as `OCI_USER_OCID` are configuration sources specific to the provider, not variables referenced in HCL as `var.OCI_USER_OCID`.

The OCI provider also supports certain `TF_VAR_*` and `OCI_*` names for its own configuration. Therefore, leftover credential variables in the environment can prevent the chosen profile from being the sole source. Inventory **variable names and sources**, while avoiding printing credential values to logs.

In practice, select one explicit authentication mechanism per job, pass the region explicitly, and remove redundant credential configurations from the runner environment. Do not rely on a personal machine happening to have an active default profile.

## 4. Variables as the Module's Input Contract

### 4.1. Declaration vs. Value Assignment

~~~hcl
variable "region" {
  description = "Region containing the VCN to read."
  type        = string
  nullable    = false

  validation {
    condition     = length(trimspace(var.region)) > 0
    error_message = "region must not be empty."
  }
}
~~~

A `variable` block declares the name, type, and constraints. The value used in expressions is `var.region`. In a `.tfvars` file, only assign values:

~~~hcl
region = "ap-singapore-1"
~~~

Do not place `provider`, `resource`, or `variable` blocks in `.tfvars` files. Do not write `var.region = ...` in that file.

A variable without a `default` requires the caller to supply a value. In CI, use `-input=false` so the job does not hang waiting for input when a variable is missing. Reference: [Input variables](https://developer.hashicorp.com/terraform/language/values/variables).

### 4.2. Data Types and Null Values

| Type | Example Data |
| --- | --- |
| `string` | `"ap-singapore-1"` |
| `number` | `3` |
| `bool` | `true` |
| `list(string)` | Ordered list of AD names |
| `set(string)` | Unordered collection of unique values, not indexable |
| `map(string)` | Tag set with flexible keys |
| `object({...})` | A structure with explicit attribute names and types |

`nullable = false` does not mean a string cannot be empty. It forbids `null` at the variable level; forbidding empty strings requires a separate validation rule.

For objects, `optional` can be used for attributes with defaults. The following snippet illustrates a different input contract and does not need to be added to the VCN-reading lab:

~~~hcl
variable "workload" {
  description = "Workload operational specifications."
  type = object({
    name     = string
    replicas = number
    tags     = optional(map(string), {})
  })
  nullable = false

  validation {
    condition     = var.workload.replicas >= 1 && floor(var.workload.replicas) == var.workload.replicas
    error_message = "replicas must be an integer greater than or equal to 1."
  }
}
~~~

Choose `object` when you want fixed field names and types. Choose `map` when keys are caller-supplied data. Avoid using `any` merely to bypass designing inputs. Reference: [Type constraints](https://developer.hashicorp.com/terraform/language/expressions/type-constraints).

### 4.3. Precedence Order When Running Terraform CLI Locally

For a root module run via standard CLI, the order from lowest to highest precedence is:

1. `default` in the variable declaration.
2. Environment variable `TF_VAR_<variable_name>`.
3. `terraform.tfvars`.
4. `terraform.tfvars.json`.
5. `*.auto.tfvars` and `*.auto.tfvars.json` files in lexical order.
6. `-var` and `-var-file` command-line arguments in order of appearance; later values win.

For example, even if the environment has `TF_VAR_region=us-ashburn-1`, a file passed via `-var-file` can still set `region = "ap-singapore-1"`. Naming a file `dev.tfvars` does not make it auto-load; it must be passed with `-var-file` since it does not match the auto-loading rules above.

HCP Terraform and remote execution platforms also have their own variable management mechanisms; account for those platform variable sources. Reference: [Assign values to variables](https://developer.hashicorp.com/terraform/language/values/variables#assign-values-to-variables).

Do not place both `dev.auto.tfvars` and `prod.auto.tfvars` in the same working directory expecting Terraform to pick based on environment. A clear approach is to put normally named files in an `environments` directory and always pass the exact file set for the job.

### 4.4. Local Values Are Not Another Input Variable

~~~hcl
locals {
  common_tags = merge(
    var.freeform_tags,
    {
      Project     = "java-learning"
      Environment = var.environment
    }
  )
}
~~~

`local.common_tags` is an internally computed result. Callers cannot set it directly using `TF_VAR_common_tags`.

In the `merge` call above, keys in later arguments win on collision. Thus, callers can add tags but cannot override `Project` or `Environment` via `freeform_tags`. This is a module contract decision, not an IAM policy. Reference: [Local values](https://developer.hashicorp.com/terraform/language/values/locals).

## 5. Complete Lab: Reading a VCN and Exporting Network Context

### 5.1. Prerequisites and Structure

Prepare:

- An existing VCN in a child compartment of the tenancy.
- Real OCIDs for the VCN, compartment, and the region containing the VCN.
- A principal with permissions to call the APIs used.
- A workstation or runner with HTTPS connectivity to OCI endpoints and a Terraform version meeting requirements.
- An OCI profile outside the repository if using `APIKey` or `SecurityToken`.

Example structure:

~~~text
oci-network-context/
├── versions.tf
├── providers.tf
├── variables.tf
├── locals.tf
├── data.tf
├── outputs.tf
└── environments/
    └── dev.tfvars
~~~

Use `versions.tf` from section 2.1 and the provider configuration from section 2.2 for `providers.tf`. The remaining files are presented below. Only sections 5.2 through 5.5 belong to the main lab configuration; the extension snippets afterward clearly note their separate purposes.

### 5.2. Declaring variables.tf

~~~hcl
variable "region" {
  description = "Region containing the VCN to read."
  type        = string
  nullable    = false

  validation {
    condition     = length(trimspace(var.region)) > 0
    error_message = "region must not be empty."
  }
}

variable "oci_auth" {
  description = "Authentication mechanism for the lab runner."
  type        = string
  default     = "APIKey"
  nullable    = false

  validation {
    condition     = contains(["APIKey", "SecurityToken", "InstancePrincipal"], var.oci_auth)
    error_message = "oci_auth must be APIKey, SecurityToken, or InstancePrincipal."
  }
}

variable "oci_config_profile" {
  description = "Profile in OCI config; not used as credential for InstancePrincipal."
  type        = string
  default     = "LEARNING"
  nullable    = false

  validation {
    condition     = length(trimspace(var.oci_config_profile)) > 0
    error_message = "oci_config_profile must not be empty."
  }
}

variable "compartment_ocid" {
  description = "Child compartment containing the existing VCN."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^ocid1[.]compartment[.]", var.compartment_ocid))
    error_message = "compartment_ocid must have a child compartment OCID format."
  }
}

variable "vcn_ocid" {
  description = "OCID of the existing VCN to read."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^ocid1[.]vcn[.]", var.vcn_ocid))
    error_message = "vcn_ocid must have a VCN OCID format."
  }
}

variable "environment" {
  description = "Environment used to build the deployment context."
  type        = string
  default     = "dev"
  nullable    = false

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be dev, staging, or prod."
  }
}

variable "freeform_tags" {
  description = "Additional tags recommended for resources created in later steps."
  type        = map(string)
  default     = {}
  nullable    = false
}
~~~

The two OCID checks only verify format prefixes. They do not prove the resource exists, resides in the expected tenancy, or is accessible. Those conditions require data read from OCI and actual permissions.

The lab intentionally requires a child compartment. If you want to use the root compartment, redesign the input contract and validations accordingly; do not substitute a tenancy OCID into a variable that only accepts child compartment OCIDs and ignore the error.

`oci_auth` only accepts exact spellings of values in the allowlist. Choosing the provider and profile is non-sensitive configuration data; private key contents must not be turned into lab variables.

### 5.3. Computing locals.tf and Reading data.tf

`locals.tf`:

~~~hcl
locals {
  common_tags = merge(
    var.freeform_tags,
    {
      Project     = "java-learning"
      Environment = var.environment
    }
  )
}
~~~

`data.tf`:

~~~hcl
data "oci_core_vcn" "selected" {
  vcn_id = var.vcn_ocid

  lifecycle {
    postcondition {
      condition     = self.compartment_id == var.compartment_ocid
      error_message = "The VCN does not belong to the compartment assigned to this configuration."
    }
  }
}

data "oci_identity_availability_domains" "available" {
  compartment_id = var.compartment_ocid

  lifecycle {
    postcondition {
      condition     = length(self.availability_domains) > 0
      error_message = "No Availability Domains returned for the current OCI context."
    }
  }
}
~~~

The `oci_core_vcn` data source looks up a VCN by OCID. After a successful read, the postcondition blocks continued use of a VCN outside the declared compartment. If the VCN does not exist or lacks read permissions, the provider may return an error before this condition is evaluated. Reference: [oci_core_vcn data source](https://docs.oracle.com/en-us/iaas/tools/terraform-provider-oci/latest/docs/d/core_vcn.html).

`oci_identity_availability_domains` reads the AD list for the provider/region context. Its argument can be a tenancy OCID or a compartment; here the lab's compartment is used. AD names are tied to the tenancy and region and should not be hardcoded from another account. Reference: [oci_identity_availability_domains](https://docs.oracle.com/en-us/iaas/tools/terraform-provider-oci/latest/docs/d/identity_availability_domains.html).

Postconditions are well suited for validating attributes returned by the API. `terraform validate` does not replace reading OCI to check these conditions. Reference: [Custom conditions](https://developer.hashicorp.com/terraform/language/expressions/custom-conditions).

### 5.4. Exposing outputs.tf

~~~hcl
output "vcn_id" {
  description = "OCID of the VCN read and verified for compartment scope."
  value       = data.oci_core_vcn.selected.id
}

output "network_context" {
  description = "Network context for subsequent deployment pipelines or modules."
  value = {
    region           = var.region
    environment      = var.environment
    compartment_ocid = data.oci_core_vcn.selected.compartment_id
    vcn_id           = data.oci_core_vcn.selected.id
    vcn_name         = data.oci_core_vcn.selected.display_name
    ipv4_cidrs       = data.oci_core_vcn.selected.cidr_blocks
    availability_domains = sort([
      for domain in data.oci_identity_availability_domains.available.availability_domains :
      domain.name
    ])
    recommended_tags = local.common_tags
  }
}
~~~

`recommended_tags` is only a proposed tag set for later deployment steps. The lab does not write tags onto the existing VCN. `vcn_name` and `ipv4_cidrs` come from OCI; `environment` comes from input and therefore must not be treated as proof that the VCN is properly classified by environment in a governance system.

Sorting the AD name list makes outputs easier to compare, but it does not establish a contract that index `0` will always be the same AD across all tenancies or over time. If you need to pin where workloads run, explicitly choose a verified AD name and verify that name remains in the list.

The `vcn_id` output is a small string for scripts to consume directly. `network_context` is a structured object for integrations needing multiple attributes. Do not export the entire provider-returned object when consumers only need a few fields. Reference: [Output values](https://developer.hashicorp.com/terraform/language/values/outputs).

### 5.5. Values in environments/dev.tfvars

~~~hcl
region             = "ap-singapore-1"
oci_auth           = "APIKey"
oci_config_profile = "LEARNING"

compartment_ocid = "ocid1.compartment.oc1..<compartment-id>"
vcn_ocid         = "ocid1.vcn.oc1.ap-singapore-1.<vcn-id>"

environment = "dev"

freeform_tags = {
  Owner      = "platform"
  CostCenter = "learning"
}
~~~

Replace the placeholders with real OCIDs. To run with instance principal on Compute, set `oci_auth = "InstancePrincipal"` in that runner's variable set and configure the dynamic group/policies beforehand.

Files without secrets can still contain internal identifying information. Decide whether to store OCIDs, region, and CostCenter in Git according to project policies; do not assume all infrastructure metadata is safe to make public.

## 6. Running the Lab and Reading Outputs

The commands below guide learners to execute in their own OCI environment. There is no need to create a new VCN if an assigned VCN already exists.

### 6.1. Initializing and Validating Configuration

In the lab directory, run:

~~~powershell
terraform init
terraform fmt -check
terraform validate
~~~

`fmt -check` checks formatting; `validate` verifies configuration validity against schemas. If formatting normalization is needed, run `terraform fmt` and re-check. Proceed only after the preceding steps succeed.

Verify that environment variables and the profile are provided to the right terminal session. There is no need to print private key contents or tokens to confirm a profile name.

### 6.2. Creating a Reviewable Plan

~~~powershell
terraform plan -input=false -var-file="environments/dev.tfvars" -out="dev.tfplan"
~~~

Once the plan succeeds, inspect the saved plan:

~~~powershell
terraform show "dev.tfplan"
~~~

With the correct lab configuration:

- Terraform reads the VCN and the AD list.
- No OCI resources are proposed for creation, update, or deletion.
- Outputs may appear as changes to be saved.
- Permission errors, wrong region, or failed postconditions must be resolved before continuing.

If the plan proposes creating or deleting resources, check whether the lab directory contains `resource` blocks from extension examples or other configurations. Terraform reads all matching configuration files in the root module, not just the file you just edited.

A saved plan captures the inputs and data needed for that apply. Do not reuse an old plan to deploy another environment by swapping `.tfvars` files after the plan has been generated.

### 6.3. Applying to Record Results in State

After reviewing the plan thoroughly, run:

~~~powershell
terraform apply -input=false "dev.tfplan"
~~~

Do not pass `-var-file` again when applying a saved plan; the variable set is already locked into the plan. OCI call permissions and credentials must still be available as required for provider execution.

In this lab, apply records data and outputs into state; it does not take ownership of the VCN merely because the VCN was read via a data source. If managed resources are added later, the meaning of apply changes according to the actions in the plan.

### 6.4. Using Outputs in PowerShell or Pipelines

~~~powershell
terraform output
terraform output -raw vcn_id
terraform output -json network_context
~~~

For scripts, use structured data rather than parsing text from the plan screen:

~~~powershell
$contextJson = terraform output -json network_context | Out-String

if ($LASTEXITCODE -ne 0) {
    throw "Failed to read network_context from state"
}

$networkContext = $contextJson | ConvertFrom-Json

if ([string]::IsNullOrWhiteSpace($networkContext.vcn_id)) {
    throw "Output is missing vcn_id"
}

$deploymentRegion = $networkContext.region
$deploymentVcnId = $networkContext.vcn_id
~~~

`-raw` suits simple values convertible to strings; `-json` suits objects and collections. Calling `terraform output -json network_context` returns that output's value. Calling `terraform output -json` without specifying a name returns a structure containing metadata such as `value`, `type`, and `sensitive` per output. Reference: [terraform output command](https://developer.hashicorp.com/terraform/cli/commands/output).

`terraform output` reads outputs already stored in state; it does not re-run data sources to query OCI. If information in OCI changes, re-run the plan/apply workflow or the project's chosen refresh workflow before treating outputs as up-to-date data.

## 7. Data Sources: Reading Data Does Not Mean Managing Lifecycle

### 7.1. Data Source, Resource, and Import

| Usage | What Terraform Is Doing | Consequence |
| --- | --- | --- |
| `data "oci_core_vcn"` | Reads an existing VCN | Does not bring VCN lifecycle management into configuration |
| `resource "oci_core_vcn"` | Describes a VCN managed by Terraform | Can create, update, or delete according to the plan |
| Import into a resource address | Links an existing resource to a managed resource in state | Requires matching resource configuration and proper management permissions |

Deleting a data source block does not delete the VCN in OCI. Conversely, switching from reading a VCN to managing it cannot be done merely by changing the keyword `data` to `resource`. It requires proper import, configuration, and plan review procedures. References: [Data sources](https://developer.hashicorp.com/terraform/language/data-sources) and [Import resources](https://developer.hashicorp.com/terraform/language/import).

Data read from a data source can be stored in state. "Read-only" here describes the operation against the source object, not that the data is never saved.

### 7.2. When Does Terraform Read a Data Source?

Normally, a data source whose arguments are all known is read during the plan phase. If an argument depends on a resource not yet created or not yet known, reading may be deferred until apply.

Conceptual example:

~~~hcl
data "oci_core_vcn" "after_creation" {
  vcn_id = oci_core_vcn.created_elsewhere_in_this_module.id
}
~~~

This snippet only illustrates dependency behavior and requires the referenced resource to be declared appropriately; do not add it to the main lab. For a VCN managed by the same module, you can usually use the resource's attributes directly rather than re-reading the same object.

Do not add `depends_on` to every data source to "guarantee it runs later." Broad dependencies can delay data reads and cause many values in the plan to become `known after apply`. Prefer direct references to needed values; only use explicit dependencies when a real relationship cannot be expressed via expressions.

### 7.3. Do Not Select Resources Arbitrarily by Index

Lookup by OCID is appropriate when you need to select an exact approved VCN. When you must look up by name, handle both zero results and multiple results.

Standalone example replacing OCID-based VCN selection:

~~~hcl
data "oci_core_vcns" "by_name" {
  compartment_id = var.compartment_ocid
  display_name   = "shared-network"
  state          = "AVAILABLE"

  lifecycle {
    postcondition {
      condition     = length(self.virtual_networks) == 1
      error_message = "Exactly one AVAILABLE VCN named shared-network is required."
    }
  }
}

locals {
  selected_vcn_by_name_id = one([
    for network in data.oci_core_vcns.by_name.virtual_networks :
    network.id
  ])
}
~~~

`display_name` filters results; it does not guarantee name uniqueness. `one` expresses the requirement of at most one element; the postcondition adds the requirement of **exactly one** result. Do not replace this with `virtual_networks[0]` and ignore remaining VCNs. Reference: [oci_core_vcns data source](https://docs.oracle.com/en-us/iaas/tools/terraform-provider-oci/latest/docs/d/core_vcns.html).

Similarly, do not rely on the return order of an AD list to choose where to place machines. For Compute images, criteria like "first image" or "latest" can change the image version between runs. Reproducible environments should store selected IDs through a release process or use strict criteria rather than assuming discovery data is immutable.

## 8. Outputs as the Consumption Interface

### 8.1. Root Output and Child Module Output

An output in a child module is accessed by the parent using:

~~~hcl
module.network_context.vcn_id
~~~

Terraform CLI only displays outputs of the root module. To re-export a value from a child module, the root must declare a corresponding output:

~~~hcl
output "application_vcn_id" {
  description = "VCN ID provided by the child module."
  value       = module.network_context.vcn_id
}
~~~

These snippets illustrate the interface when a `network_context` module already exists; they do not add a child module to the current lab.

Treat output names, types, and field meanings as part of a contract. Changing a `vcn_id` string into an object without notifying consumers can break pipelines even though nothing changed in OCI resources.

When a module only needs to provide a subnet's ID, export the ID. Do not force consumers to know the internal structure of the entire resource. For composite results like `network_context`, keep fields stable and clearly document which fields are live data and which are configuration proposals.

### 8.2. Sensitive Is Not State Encryption

An example of declaring sensitive data, not part of the VCN-reading lab:

~~~hcl
variable "database_admin_password" {
  description = "Password supplied from the pipeline secret management channel."
  type        = string
  sensitive   = true
  nullable    = false
}
~~~

`sensitive = true` helps mask values in standard display interfaces. If a value enters a resource attribute, data source, or output stored in state, adding only the sensitive flag does not remove the value from state or encrypt it there. You must protect state, saved plans, artifacts, and runner permissions. Reference: [Manage sensitive data](https://developer.hashicorp.com/terraform/language/manage-sensitive-data).

Do not create outputs for private keys or passwords just to "make debugging easier." Sensitive outputs can still be revealed in plaintext when queried by name or using `-raw`/`-json` modes. A pipeline masking a secret in its UI does not guarantee every artifact file or downstream tool masks it too.

Data like OCIDs and VCN names are not signing credentials, yet they can still fall within internal information scope. `sensitive` should reflect actual data classification and must not be used as a substitute for state read access control.

### 8.3. Do Not Share Full State by Default Just to Fetch One ID

`terraform_remote_state` allows reading root outputs from another state snapshot. However, snapshot access permissions can extend to far more data than the outputs a consumer cares about. Do not treat referencing a single output as an access restriction mechanism for the entire state. Reference: [terraform_remote_state](https://developer.hashicorp.com/terraform/language/state/remote-state-data).

If a system only needs a few approved IDs, consider publishing those IDs separately through an appropriately permissioned configuration channel or looking up resources directly with OCI data sources. Choose based on consistency needs, access controls, and cross-team coordination.

## 9. Provider Aliases for Multiple Regions and Passing Them into Modules

A provider configuration typically represents one connection context. When you need to read another region, add an alias instead of mutating the default configuration's region at runtime.

The following extension example uses a second region variable:

~~~hcl
variable "secondary_region" {
  description = "Second region from which to read the AD list."
  type        = string
  nullable    = false
}

provider "oci" {
  alias               = "secondary"
  auth                = var.oci_auth
  region              = var.secondary_region
  config_file_profile = var.oci_auth == "InstancePrincipal" ? null : var.oci_config_profile
}

data "oci_identity_availability_domains" "secondary" {
  provider       = oci.secondary
  compartment_id = var.compartment_ocid
}

output "secondary_availability_domains" {
  value = sort([
    for domain in data.oci_identity_availability_domains.secondary.availability_domains :
    domain.name
  ])
}
~~~

Keep the default provider from section 2 when adding this alias, and supply `secondary_region`. The `provider = oci.secondary` attribute is a provider configuration reference, not the string `"oci.secondary"`.

If a child module uses a default provider named `oci`, the parent can map the desired configuration via the module block's `providers` argument:

~~~hcl
providers = {
  oci = oci.secondary
}
~~~

This snippet is part of an existing `module` block, not a standalone top-level block. The child module still declares its `source = "oracle/oci"` requirement. If the child needs to reference multiple aliases internally, it must declare the corresponding `configuration_aliases`. References: [Provider configuration](https://developer.hashicorp.com/terraform/language/providers/configuration) and [Providers within modules](https://developer.hashicorp.com/terraform/language/modules/develop/providers).

With reusable modules, let the root choose credentials and provider configurations. Pass business inputs such as compartment, VCN, or workload name into the module; avoid requiring every child module to accept a private key and construct its own provider.

Do not use a value available only after apply to construct the provider configuration needed by those very resources. For instance, using data created by an OCI provider to determine initialization credentials for that same provider can cause dependency cycles or unplannable configurations.

## 10. Operating in CI, Scope Control, and Cost

A reliable job must explicitly know the variable set, principal, region, state, and provider version it uses. Having the same HCL files does not prove two runs share the same context.

| Component | Control Mechanism |
| --- | --- |
| Principal | Dedicated job identity; read/write permissions scoped to the task |
| Environment variables | Explicitly selected value set, without mixing environments |
| Provider version | Intentional constraints and managed lock file |
| Saved plan | Tied to the appropriate commit, environment, and reviewer |
| State | Environment-matched backend and access controls, with appropriate concurrency locking |
| Outputs | Stable schema; no arbitrary exposure of secrets |
| Logs | Record failed steps and request IDs when available; do not print tokens, keys, or full sensitive data |

Items commonly excluded from Git in practice configurations:

~~~gitignore
.terraform/
*.tfstate
*.tfstate.*
*.tfplan
crash.log
crash.*.log
environments/*.local.tfvars
~~~

Keep `.terraform.lock.hcl` in the root configuration's repository. With a remote backend, credentials for backend access may be a separate configuration flow from OCI provider credentials. Configuring a provider does not automatically mean state protection or locking is configured.

The lab only reads data, yet it still makes API calls and writes state on apply. When expanding to billable Compute, databases, or gateways, review variable values governing counts, shapes, capacity, and regions before applying. The `CostCenter` tag in the proposed output does not automatically enforce budgets or spending limits.

Data sources help discover the environment; turning those results into resource selections still requires explicit criteria. Do not use "first resource found" as the basis for availability or cross-region recovery plans.

## 11. Diagnosing Common Errors

| Symptom | What to Check |
| --- | --- |
| `init` succeeds but data source fails | OCI permissions, credentials, network path, and region; `init` does not verify these conditions |
| Profile not found | Profile name, home directory, and config file of the exact user running the process |
| Private key/fingerprint error | Key format, whether public key is registered to the right user, matching fingerprint and passphrase |
| Security token is no longer usable | Session expiration and token issuance/refresh mechanism before or during the job |
| Instance principal does not work on a workstation | Runner is not in a supported Compute environment or lacks IAM configuration |
| `NotAuthorizedOrNotFound` when reading VCN | OCID, region, tenancy, and policies; do not immediately assume the VCN was deleted |
| OCID validation passes but API rejects it | Validation only checks format, not existence or permissions |
| VCN is readable but postcondition fails | Compare the VCN's actual compartment against the input |
| Wrong region selected despite env var | Check higher-precedence variable sources and actual provider configuration |
| Changing `dev.tfvars` does not change output | Whether that file was loaded, which state was applied, and which snapshot output reads |
| Data source read is deferred | Check unknown arguments and unnecessary `depends_on` |
| Name lookup returns multiple results | Narrow criteria or use OCID; do not take the first element arbitrarily |
| Pipeline fails to parse output | Distinguish named output from full JSON outputs; do not parse plan output text |
| Sensitive value appears in artifacts | Check data export paths, state, saved plans, and invoked CLI outputs |

When supporting operations, collect provider version, Terraform version, authentication type, region, failing step, and OCI request ID if present. Share only permitted identifying data; never ask someone to send private keys or dump the entire environment.

## 12. Scenarios Learners Should Verify Themselves

After completing the lab, make one small change at a time and observe the plan or error:

1. Use valid OCIDs and region: receive the VCN and AD list; no OCI resources are created.
2. Set `environment = "production"`: validation rejects it because it is not in the allowlist.
3. Set an empty region: validation rejects it before relying on VCN read results.
4. Provide a readable VCN OCID belonging to a different compartment: the postcondition must catch the scope mismatch.
5. Set `TF_VAR_environment` and then set a different value in `-var-file`: confirm the higher-precedence source wins.
6. Omit `-var-file` without another source for required variables and use `-input=false`: the job fails cleanly instead of hanging for input.
7. Read `terraform output -json network_context` after apply: the parser receives an object with the exposed fields.
8. Compare the proposed tag set with the VCN's actual tags: understand that outputs do not automatically update resources.
9. Re-run with an under-privileged principal: distinguish authorization errors from syntax or validation errors.
10. If using the lookup-by-name example, test behavior when zero or multiple results exist.

These scenarios are exercises for the learner's environment; this document does not claim they were executed against a specific tenancy.

The four decisions to keep clear are: provider determines the OCI call context, variables determine what configuration can vary, data sources read current state, and outputs expose the result interface. When these boundaries are clearly designed, the same codebase can be operated under control across multiple compartments, regions, and environments.
