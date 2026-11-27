# Designing Reusable Terraform Modules for GCP

A Terraform module is a collection of configuration files packaged together to create and manage a group of infrastructure resources. On Google Cloud, modules help standardize how VPCs, subnets, service accounts, buckets, Cloud Run services, or other platform components are provisioned. Instead of copying large blocks of resources across projects, teams can build modules with clear inputs and outputs and call them from different environment configurations.

A well-designed reusable module is more than a folder holding multiple resources. It needs sensible responsibility boundaries, a stable interface, safe defaults, input validation, and controlled versioning. This design enables teams to share infrastructure standards while still adapting to individual workload requirements.

## 1. Distinguishing Root Modules and Child Modules

In Terraform, any directory containing a set of configuration files loaded together is a module. When running Terraform commands in a directory, that configuration is the root module. A root module can call other modules using `module` blocks; the called modules are called child modules.

| Component | Responsibility | GCP Example |
| --- | --- | --- |
| Root module | Combines components, selects the environment, and configures providers, backend, and state | Production infrastructure configuration for an application |
| Child module | Encapsulates a reusable infrastructure capability, accepting inputs and returning outputs | VPC module, Cloud Run service module, GCS bucket module, or service account module |
| Provider configuration | Provides connection and authentication details for Google Cloud | Project, region, and Google credentials or authentication mechanism |
| State | Records the mapping between Terraform configuration and real resources | Separate state for production networking or staging workloads |

The root module is typically where teams select the project, region, environment, and wire modules together. A child module should focus on creating a component with a clear responsibility. Backends and state belong to the root module; child modules should not declare their own backend.

## 2. Defining Module Boundaries

Good boundaries start with an infrastructure capability that can be described in a single sentence. For example: a VPC module creates a custom network and subnets; a Cloud Run module deploys a service with runtime, ingress, and service account settings; a bucket module creates a bucket with standardized access policies and lifecycle rules.

When deciding how to split modules, consider:

- **A single clear responsibility:** a module should solve one closely related infrastructure concern. Avoid creating a monolithic module with excessive options to manage an entire project.
- **Caller-focused interface:** expose only the inputs that module consumers need to decide. Implementation details can remain internal.
- **Practical reusability:** only abstract patterns that already repeat or are likely to be used across multiple workloads. Avoid creating a module solely to wrap a single resource without adding standards or value.
- **Clear ownership:** define which team maintains the module, who approves changes, and how new releases are communicated.
- **Moderate coupling:** a module can create resources sharing a lifecycle, but should limit dependencies on unrelated modules.

For instance, a VPC module can manage a network and subnets. Firewall policies, Cloud NAT, VPN, or Shared VPC can live in separate modules if they have independent lifecycles, administrative permissions, or usage patterns. The root module connects them using outputs and inputs.

Avoid mechanically creating a separate module for every single resource. If a module merely forwards every attribute of a single resource without providing naming standards, validation, security defaults, or useful structure, callers are better off using the resource directly.

## 3. Organizing Directory Structure

A repository can organize shared modules and deployment configurations as follows:

~~~text
terraform-gcp/
├── modules/
│   ├── vpc/
│   │   ├── versions.tf
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   ├── outputs.tf
│   │   ├── README.md
│   │   └── examples/
│   │       └── basic/
│   ├── cloud-run-service/
│   └── gcs-bucket/
├── environments/
│   ├── dev/
│   ├── staging/
│   └── prod/
└── README.md
~~~

Inside the VPC module, files can be divided by role:

| File | Contents |
| --- | --- |
| versions.tf | Minimum Terraform version and provider requirements |
| main.tf | Primary resources |
| variables.tf | Inputs, data types, descriptions, validation, and default values |
| outputs.tf | Values the module exposes to the calling module |
| README.md | Purpose, usage, inputs, outputs, examples, and operational notes |
| examples/ | Small root modules demonstrating how to use the module |

Terraform loads all `.tf` files in the same directory as a single unified configuration; splitting across multiple files makes it easier for humans to read and maintain. There is no need to create a separate file per resource if the count is small or if splitting makes the configuration harder to follow.

## 4. Designing the Inputs and Outputs Interface

Inputs form the contract between a module and its callers. A good input has a meaningful name, an explicit type, a clear description, and validation for important constraints. Avoid using many free-form string variables when a structured `object` or `map` can model the data cleanly.

For a VPC module, typical inputs include:

| Input | Suggested Type | Purpose |
| --- | --- | --- |
| project_id | string | Project owning the network |
| network_name | string | VPC name |
| routing_mode | string | GLOBAL or REGIONAL |
| subnets | map(object(...)) | List of subnets, regions, and CIDRs |

Outputs should expose information that other modules genuinely need, such as network ID, self-link, or a map of subnets by name. Do not export every internal attribute simply because it is available; outputs are part of the public API and changing them can impact callers.

When a Cloud Run module needs a network created by the VPC module, the root module can pass the network output into the Cloud Run module's input. This wiring creates a clear dependency in Terraform's graph and helps Terraform determine execution order.

### Validation and Default Values

Use concrete types and `validation` blocks to catch configuration mistakes early. For example, project ID and network name must not be empty, `routing_mode` only accepts valid values, and CIDRs must have valid network formatting.

Defaults should only be set for options with safe, common behavior. Never default critical values like project, region, IAM principals, or important CIDRs to placeholder assumptions that could create resources in the wrong scope.

With Terraform 1.3 and later, object types can use `optional` attributes to define optional fields with defaults. Document default values clearly in `README.md` so callers understand what configuration the module will create.

## 5. Example: Building a VPC Module for Google Cloud

The following example creates a custom-mode VPC and multiple subnets. Its goal is to illustrate module structure, data passing, and output exposure. Project names, regions, and CIDR ranges are sample values and must be replaced to match the actual architecture.

**File versions.tf**

~~~hcl
terraform {
  required_version = ">= 1.6.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 6.0.0"
    }
  }
}
~~~

The module declares the providers it requires and the minimum Terraform version. A module should not configure credentials or a default project itself. The root module configures the provider and passes the appropriate configuration down to child modules.

**File variables.tf**

~~~hcl
variable "project_id" {
  description = "Project ID owning the VPC and subnets."
  type        = string
  nullable    = false

  validation {
    condition     = length(trimspace(var.project_id)) > 0
    error_message = "project_id must not be empty."
  }
}

variable "network_name" {
  description = "Name of the VPC to create."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[a-z]([-a-z0-9]{0,61}[a-z0-9])?$", var.network_name))
    error_message = "network_name must start with a lowercase letter, contain only lowercase letters, numbers, or hyphens, and be at most 63 characters long."
  }
}

variable "routing_mode" {
  description = "Routing mode of the VPC."
  type        = string
  default     = "GLOBAL"

  validation {
    condition     = contains(["GLOBAL", "REGIONAL"], var.routing_mode)
    error_message = "routing_mode only accepts GLOBAL or REGIONAL."
  }
}

variable "subnets" {
  description = "Subnets keyed by name, each with a region and CIDR."
  type = map(object({
    region                   = string
    ip_cidr_range            = string
    private_ip_google_access = optional(bool, true)
  }))
  nullable = false

  validation {
    condition = alltrue([
      for subnet in values(var.subnets) :
      length(trimspace(subnet.region)) > 0 &&
      can(cidrhost(subnet.ip_cidr_range, 0))
    ])
    error_message = "Each subnet must have a non-empty region and a valid ip_cidr_range."
  }
}
~~~

**File main.tf**

~~~hcl
resource "google_compute_network" "this" {
  project                 = var.project_id
  name                    = var.network_name
  auto_create_subnetworks = false
  routing_mode            = var.routing_mode
}

resource "google_compute_subnetwork" "this" {
  for_each = var.subnets

  project                  = var.project_id
  name                     = each.key
  region                   = each.value.region
  network                  = google_compute_network.this.id
  ip_cidr_range            = each.value.ip_cidr_range
  private_ip_google_access = each.value.private_ip_google_access
}
~~~

**File outputs.tf**

~~~hcl
output "network_id" {
  description = "ID of the created VPC."
  value       = google_compute_network.this.id
}

output "network_self_link" {
  description = "Self-link of the VPC."
  value       = google_compute_network.this.self_link
}

output "subnetwork_self_links" {
  description = "Map of subnet self-links keyed by name."
  value = {
    for name, subnet in google_compute_subnetwork.this :
    name => subnet.self_link
  }
}
~~~

Here, `for_each` creates one subnet per entry in the map. The subnet name becomes a stable key, allowing callers to reference subnets by name rather than by list index. Using a map also makes it possible to add a subnet without shifting references to other subnets.

The VPC is created in custom mode because `auto_create_subnetworks` is set to `false`. Each subnet declares its own region. The module can be extended to support secondary IP ranges or flow logs when an actual need arises; avoid adding every networking feature to the base module from day one.

## 6. Calling the Module from a Root Module

The root module is responsible for configuring the Google provider, selecting the project, and passing environment-specific values. The following example calls the VPC module from `modules/vpc`:

~~~hcl
terraform {
  required_version = ">= 1.6.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 6.0.0"
    }
  }
}

variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "environment" {
  type = string
}

provider "google" {
  project = var.project_id
  region  = var.region
}

module "network" {
  source = "../../modules/vpc"

  project_id   = var.project_id
  network_name = format("%s-network", var.environment)
  routing_mode = "GLOBAL"

  subnets = {
    app = {
      region        = var.region
      ip_cidr_range = "10.20.0.0/20"
    }
    data = {
      region        = var.region
      ip_cidr_range = "10.20.16.0/20"
    }
  }
}

output "network_id" {
  value = module.network.network_id
}
~~~

With the directory structure shown earlier, the relative `source` from `environments/prod` to `modules/vpc` is `../../modules/vpc`. In real environments, distinct values such as project ID, region, environment, and CIDRs can be stored in separate `.tfvars` files. Do not put credentials or secrets into `.tfvars` files committed to the repository.

If multiple environments use the same module, each `dev`, `staging`, and `prod` root module supplies its own input set. The module keeps the same logic; the root module determines environment values and backend state. This keeps shared logic changes centrally controlled while keeping access permissions and state lifecycles isolated.

## 7. Provider Configuration and Multiple Projects

Provider configuration should reside in the root module so the deployment team controls the project, region, and authentication mechanism. Child modules declare `required_providers` so Terraform knows the provider source and version, but usually do not contain their own `provider` block.

The default provider from the root module is passed down to child modules via inheritance. When a provider alias is needed, the root module can pass the alias explicitly:

~~~hcl
provider "google" {
  alias   = "shared"
  project = var.network_project_id
  region  = var.region
}

module "shared_network" {
  source = "../../modules/vpc"

  providers = {
    google = google.shared
  }

  project_id   = var.network_project_id
  network_name = "shared-network"
  subnets      = var.subnets
}
~~~

This example uses a provider alias to create a network in a shared project. If a child module requires multiple distinct provider configurations, the module must declare the corresponding `configuration_aliases` in `required_providers` and the root module must pass the complete mapping. Only use aliases when the architecture truly spans multiple projects or distinct provider configurations.

Never place credentials directly inside module source code. In development environments you can use Application Default Credentials; in CI/CD, use an appropriate workload authentication mechanism such as Workload Identity Federation when supported by the runner platform. The deployment service account or principal should only have necessary permissions on target projects and resources.

## 8. Composing Multiple Modules into an Architecture

Modules are reused effectively when the root module wires components together via outputs and inputs. For example, a workload might consist of:

- A VPC module creating the network and subnets.
- A service account module creating the application's runtime identity.
- A Cloud Run module deploying the container and receiving the service account and ingress configuration.
- An IAM module granting the required permissions to the workload.
- A GCS bucket module creating data storage with appropriate policies and lifecycles.

The root module connects the components:

~~~hcl
module "runtime_identity" {
  source       = "../../modules/service-account"
  project_id   = var.project_id
  account_id   = "orders-api"
  display_name = "Orders API runtime"
}

module "orders_service" {
  source = "../../modules/cloud-run-service"

  project_id         = var.project_id
  region             = var.region
  service_name       = "orders-api"
  image              = var.orders_image
  service_account_id = module.runtime_identity.email
}
~~~

This module call snippet illustrates passing the `email` output of the service account module into the input of the Cloud Run module. Inputs and outputs must match the actual interfaces of those modules. Do not copy this snippet into a root module if the repository does not yet contain the referenced modules.

If an IAM module grants permissions to a service account, select an IAM resource type with appropriate semantics. `member` resources typically manage a single member binding; `binding` resources can manage the entire membership list for a role at that scope. Mixing resources that manage the same role at the same scope can cause unexpected policy overwrites. Module documentation should clearly state which permissions are created and what scope is managed.

## 9. Module Versioning and Releases

A shared module is an infrastructure API. When changing inputs, outputs, or resource behavior, assess the impact on every root module using it. Apply disciplined versioning and release changes through pull requests, reviews, testing, and release notes.

For modules stored in the Terraform Registry or a private registry, callers can specify a version:

~~~hcl
module "network" {
  source  = "app.terraform.io/example-org/gcp-vpc/google"
  version = "~> 1.2"

  project_id   = var.project_id
  network_name = "prod-network"
  subnets      = var.subnets
}
~~~

The registry address above is an illustrative example. In your organization, replace it with your actual hostname and namespace. For modules sourced from Git, you can pin a tag or commit:

~~~hcl
module "network" {
  source = "git::https://example.com/platform/terraform-gcp.git//modules/vpc?ref=v1.2.0"

  project_id   = var.project_id
  network_name = "prod-network"
  subnets      = var.subnets
}
~~~

The Git source demonstrates the structure; replace the URL with your actual repository. With Git sources, `ref` identifies the tag or commit to use. Avoid referencing a continuously changing branch in production because the same configuration could pull different code on subsequent `init` runs.

A module release workflow can include:

1. Creating a branch and pull request for the change.
2. Running formatting, validation, static checks, and module tests.
3. Using an example root module to verify the public interface.
4. Reviewing the impact on resources, state, and existing callers.
5. Bumping the version according to change severity, creating a tag, or publishing to the registry.
6. Updating callers on a schedule, running `plan`, and reviewing before `apply`.

Breaking changes such as removing an input, changing a type, renaming an output, or changing resource addresses should be treated as major changes. If a resource address must change, evaluate using `moved` blocks or an appropriate state migration procedure so Terraform does not mistake the old resource as needing destruction and recreation.

## 10. State, Environments, and Protecting Sensitive Data

Child modules do not have independent state. State belongs to the active root module and stores the linkage between resource addresses and real resources. Consequently, the same module can be called across multiple root modules with isolated states.

For GCP production, teams commonly use the GCS backend to store state remotely. The state bucket must be created and protected according to dedicated policies, with versioning enabled where appropriate, restricted IAM, and controlled read/delete permissions. The backend is configured in the root module, never inside a child module. Separate state by environment or administrative boundary to limit blast radius in case of failures or mistakes.

Example backend in the root module:

~~~hcl
terraform {
  backend "gcs" {
    bucket = "org-terraform-state-prod"
    prefix = "gcp/network/prod"
  }
}
~~~

The bucket and prefix are sample values. The backend bucket must exist before initializing the backend. Do not share the same state prefix across multiple independent root modules. Sharing state between dev and prod increases the risk of applying to the wrong resources and complicates access control.

Variables marked `sensitive` help limit display of values in certain Terraform outputs, but do not guarantee secrets are excluded from state. Never hardcode passwords, private keys, or tokens in modules, outputs, `.tfvars` files committed to Git, or pipeline logs. Use Secret Manager or proper secret injection mechanisms, restrict state read permissions, and avoid exposing sensitive values through outputs.

## 11. Testing and Quality Checks for Modules

Modules should include runnable examples so consumers understand how to call them and reviewers can verify the interface. Basic verification steps:

~~~bash
terraform fmt -check -recursive
terraform -chdir=modules/vpc/examples/basic init -backend=false
terraform -chdir=modules/vpc/examples/basic validate
terraform -chdir=modules/vpc/examples/basic plan
~~~

Running `plan` requires valid sample variables and corresponding provider read permissions. A non-secret `.tfvars` file can be used to supply project, region, and CIDRs in a test environment.

With Terraform 1.6 and later, `terraform test` lets you write tests in `.tftest.hcl` files. Tests can validate conditions, outputs, and configuration behavior; some tests may create real resources depending on how `run` blocks are declared. Only run integration tests in an isolated test project with appropriate permissions and budgets, and verify cleanup afterward.

Beyond Terraform tests, review:

- Resource names are stable and avoid unintended address changes.
- Inputs have validation and clear descriptions.
- Outputs expose only necessary information.
- IAM follows the principle of least privilege.
- No secrets appear in source code, sample state, or logs.
- Required APIs are enabled and resource prerequisites are documented.
- `README.md` includes examples, provider requirements, inputs, outputs, and upgrade notes.
- Module changes include release notes and migration instructions when needed.

## 12. Common Design Mistakes

| Mistake | Impact | How to Improve |
| --- | --- | --- |
| Oversized module managing unrelated resource domains | Hard to reuse and changing one part can affect everything | Split by capability and resource lifecycle |
| Exposing every resource attribute as an input | Complex interface, hard to maintain and hard to enforce standards | Expose only options meaningful to callers |
| Declaring providers or credentials inside a child module | Hard to use the module across multiple projects and environments | Configure providers at root and pass aliases when needed |
| Using unstable resource names or `for_each` keys | Input changes can trigger unintended destroy/create | Use meaningful, stable, documented keys |
| Using wildcard IAM or broad permissions so the module runs easily | Increases blast radius if a workload is compromised | Design roles and principals for exact requirements |
| Changing outputs or inputs without versioning | Existing root modules can break or alter infrastructure unexpectedly | Release versioned updates, migrations, and release notes |
| Sharing state across multiple environments | Can apply to wrong resources and over-grant permissions | Separate root modules, backend prefixes, and permissions per environment |
| Assuming `sensitive` keeps secrets out of state | Secrets can still be stored in state or backend | Protect state and use Secret Manager or secret injection |

## 13. Checklist for Designing Reusable GCP Modules

Before publishing a shared module, verify:

- The module has a single purpose and clear responsibility boundaries.
- Inputs have types, descriptions, validation, and safe defaults.
- Outputs form a small, stable, well-documented public interface.
- The module declares `required_providers` and a minimum Terraform version.
- Provider configuration, backend, and state are managed by the root module.
- The module has an example root module and appropriate tests.
- IAM permissions, API prerequisites, region, and project scope are documented.
- Resource addresses and `for_each` keys are designed to be stable.
- Module versions are pinned in production environments with an upgrade process.
- State, credentials, and secrets are protected according to organizational policy.
- Breaking changes include a migration plan and review before applying.

Designing reusable Terraform modules for GCP is about identifying the right infrastructure layers to standardize, publishing an understandable interface, and keeping control at the root module. When modules have clear responsibilities, providers and state are managed at the proper layer, inputs are validated, and versions are released with discipline, multiple teams can deploy infrastructure consistently while still meeting the specific needs of each project and workload.
