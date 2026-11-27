# Managing VPC, Compute Engine, and Cloud Run with Terraform

Terraform is an Infrastructure as Code (IaC) tool that lets you describe infrastructure in configuration files, preview changes, and apply them repeatably. With Google Cloud, the Google provider maps resources in HCL to real resources such as VPC networks, subnets, firewall rules, Compute Engine VMs, and Cloud Run services.

In the `CLOUD_PROVIDERS_GCP` module, Terraform connects infrastructure pieces into a unified configuration. A single VPC can contain a subnet for VMs and a subnet for Cloud Run Direct VPC egress; firewall rules restrict traffic flows; VMs run workloads requiring continuous processing; Cloud Run deploys containers and scales by request. Terraform tracks relationships between resources via state and the dependency graph to determine creation, update, or deletion order.

After this lesson, you can:

- Initialize a Terraform project using the Google provider and authenticate with Application Default Credentials.
- Distinguish provider, resource, data source, variable, output, module, and state.
- Create a custom-mode VPC, regional subnets, and firewall rules.
- Create a Compute Engine VM in a private subnet without an external IP and allow SSH via IAP.
- Deploy a Cloud Run service with Terraform and connect egress to a VPC via Direct VPC.
- Store state remotely in Cloud Storage, review plans, manage drift, and organize `dev`/`staging`/`prod` environments.

## 1. The Terraform Model on Google Cloud

Terraform reads HCL configuration files in a working directory. The Google provider is responsible for calling Google Cloud APIs; each resource block describes a resource to manage.

Key concepts:

| Component | Role | Example |
|---|---|---|
| Provider | Connects Terraform to platform APIs | `hashicorp/google` |
| Resource | Creates and manages a resource | `google_compute_network` |
| Data source | Reads information about an existing resource | `google_project` |
| Variable | Accepts configurable input values | `project_id`, `region` |
| Local | Names reusable expressions | list of APIs to enable |
| Output | Exports information after applying | VM internal IP, Cloud Run URL |
| Module | Packages configuration for reuse | `network`, `compute`, `cloud-run` |
| State | Stores mapping between HCL resources and real resources | `terraform.tfstate` |

Terraform compares the current configuration against state and actual status from Google Cloud APIs to build an execution plan. The plan shows which resources will be created, updated in place, replaced, or destroyed.

~~~mermaid
flowchart TD
    HCL["HCL configuration"] --> TF["Terraform CLI"]
    TF --> P["Google provider"]
    TF <--> ST["Terraform state"]
    P --> API["Google Cloud APIs"]
    API --> RES["VPC / Subnet / Firewall"]
    API --> VM["Compute Engine"]
    API --> CR["Cloud Run"]
    TF --> PLAN["Plan: add / change / destroy"]
    PLAN --> REVIEW["Review and approval"]
    REVIEW --> APPLY["Apply"]
~~~

Terraform needs state to know which resource in configuration corresponds to which resource on Google Cloud. If state is lost or multiple operators write state without locking, Terraform can misidentify which resources need creation or modification. Therefore, state management is an essential part of IaC.

## 2. Preparing the Project, Tools, and Identity

### 2.1. Google Cloud Prerequisites

Before running Terraform, you need:

- An existing Google Cloud project.
- Billing enabled on the project.
- Permissions to create networks, subnets, firewall rules, VMs, service accounts, and Cloud Run services.
- Permissions to enable required APIs.
- Terraform CLI and Google Cloud CLI installed.

The Project ID is the project's identifier, not its display name. Region and zone must match your deployment location. Examples in this lesson use `asia-southeast1` and `asia-southeast1-b`; check machine types, images, and quotas in your chosen location.

### 2.2. Enabling the Service Usage API

Terraform can manage APIs with the `google_project_service` resource, but the Service Usage API itself must be enabled before Terraform creates that resource:

~~~bash
gcloud services enable serviceusage.googleapis.com --project=PROJECT_ID
~~~

Afterward, the Terraform configuration can enable APIs such as Compute Engine, Cloud Run, IAM, and Artifact Registry.

### 2.3. Authenticating with ADC

When running Terraform on a development machine, log in with Application Default Credentials:

~~~bash
gcloud auth application-default login
gcloud config set project PROJECT_ID
~~~

The Google provider discovers ADC automatically. For CI/CD, prefer Workload Identity Federation or service account impersonation. Avoid creating long-lived service account JSON keys and committing them to repositories or storing them in pipeline logs.

The identity running Terraform needs administrative permissions appropriate for the resources managed by the configuration. Separate permissions for the infrastructure creator, plan reviewer, and workload runtime. The VM or Cloud Run service account should not receive broad permissions just because Terraform has deployment permissions.

### 2.4. Initializing Directory Structure

A small layout can start as follows:

~~~text
terraform/
  environments/
    dev/
      main.tf
      variables.tf
      outputs.tf
      terraform.tfvars
    prod/
      main.tf
      variables.tf
      outputs.tf
      terraform.tfvars
  modules/
    network/
    compute/
    cloud-run/
~~~

Each environment directory is a root module with its own state. Shared modules contain reusable resources and outputs. For hands-on practice, you can start with a simple root module and split into modules once the configuration stabilizes.

Do not put credentials, state files, plan files, or the `.terraform` directory into Git. A basic `.gitignore`:

~~~gitignore
.terraform/
*.tfstate
*.tfstate.*
*.tfplan
crash.log
terraform.tfvars
~~~

If `terraform.tfvars` contains only non-sensitive values, an organization can decide to store templates or commit files under a separate review process. Never store passwords, tokens, or keys in this file.

## 3. Declaring the Google Provider and APIs

Create `versions.tf`:

~~~hcl
terraform {
  required_version = ">= 1.5.0, < 2.0.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.31"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}
~~~

Provider version constraints ensure the team uses a tested version range. Terraform records the selected provider version in `.terraform.lock.hcl`; commit this lock file so all environments install the exact same provider build.

Create `variables.tf`:

~~~hcl
variable "project_id" {
  description = "Google Cloud project ID"
  type        = string
}

variable "region" {
  description = "Region for deploying subnets and Cloud Run"
  type        = string
  default     = "asia-southeast1"
}

variable "zone" {
  description = "Zone for deploying the Compute Engine VM"
  type        = string
  default     = "asia-southeast1-b"
}

variable "container_image" {
  description = "Built and accessible container image"
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}
~~~

Enable required APIs in `apis.tf`:

~~~hcl
locals {
  required_apis = toset([
    "compute.googleapis.com",
    "run.googleapis.com",
    "iam.googleapis.com",
    "artifactregistry.googleapis.com"
  ])
}

resource "google_project_service" "required" {
  for_each = local.required_apis

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}
~~~

`disable_on_destroy = false` allows Terraform to remove the API management resource without automatically disabling the project's API. This is the right choice for long-lived shared projects where other systems may still need those APIs.

Infrastructure resources must depend on API enablement. You can declare `depends_on` on foundational resources. Terraform also creates dependencies automatically when one resource references another resource's output.

## 4. Managing Terraform State with Cloud Storage

### 4.1. Why Is Remote State Needed?

By default, Terraform stores state in `terraform.tfstate` in the working directory. This works for personal experiments, but not when multiple people or pipelines manage the same infrastructure.

A remote backend stores state in a shared location. The GCS backend has these characteristics:

- Stores state as objects in the configured bucket and prefix.
- Supports state locking to prevent concurrent state writes.
- Can enable Object Versioning to restore previous state versions after errors or accidental deletion.
- Uses ADC or service account impersonation for authentication.

### 4.2. Creating a Dedicated State Bucket

The bucket used as a backend must exist before Terraform initializes the GCS backend. You can create the bucket via an independent bootstrap configuration or have the platform team manage it:

~~~hcl
resource "google_storage_bucket" "terraform_state" {
  name                        = "company-terraform-state-unique"
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

Bucket names must be globally unique across Google Cloud. Restrict bucket read/write permissions to identities that need to run Terraform. State can contain sensitive information, so the bucket must not be public and must be protected as critical data storage.

Do not place the resource creating the state bucket itself inside the same root module using that bucket as its backend. Create the bucket in a separate bootstrap stack or use a bucket prepared by the platform team.

### 4.3. Declaring the GCS Backend

Once the bucket exists, declare the backend in `backend.tf`:

~~~hcl
terraform {
  backend "gcs" {
    bucket = "company-terraform-state-unique"
    prefix = "gcp/network-app/prod"
  }
}
~~~

The backend block cannot reference Terraform variables, locals, or data sources. Therefore, `bucket` and `prefix` must be declared directly or passed via backend configuration during initialization.

Initialize the backend:

~~~bash
terraform init
~~~

If state was previously local and needs to move to GCS:

~~~bash
terraform init -migrate-state
~~~

Before migrating, back up the state and verify the target bucket, prefix, and access permissions. Never edit the state file by hand; when adjustments are needed, use controlled `terraform state` commands.

### 4.4. Protecting State and Access Permissions

State is not a public configuration file. Values marked `sensitive` in Terraform are only hidden from normal outputs; the values can still reside in state and plan files.

Best practices:

- Use a dedicated bucket for state, with Object Versioning and public access prevention enabled.
- Restrict IAM on the bucket per environment group.
- Grant the Terraform execution identity object read/write permissions on the bucket, typically `roles/storage.objectAdmin` at the bucket scope.
- Use service accounts or impersonation for pipelines.
- Never commit state, plan files, or credentials.
- Never share plan files over unprotected channels.
- Only run `terraform force-unlock` after confirming the lock is abandoned and verifying the exact lock ID of the operation to release.

## 5. Creating a VPC and Subnets with Terraform

### 5.1. Custom-Mode VPC

A VPC network is a global resource; subnets reside in a region. One VPC can contain multiple subnets across different regions. When you need control over CIDRs and subnet placement, custom mode with `auto_create_subnetworks = false` is the clear choice.

Create `network.tf`:

~~~hcl
resource "google_compute_network" "app" {
  name                    = "tf-demo-vpc"
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"

  depends_on = [google_project_service.required]
}
~~~

If `auto_create_subnetworks` is enabled, Google Cloud automatically creates subnets across regions. For infrastructure requiring IP range control, disable this option and declare subnets explicitly.

### 5.2. Subnets for Compute Engine and Cloud Run

Create separate subnets for the VM and for Cloud Run Direct VPC egress:

~~~hcl
resource "google_compute_subnetwork" "vm" {
  name                     = "tf-demo-vm-subnet"
  region                   = var.region
  network                  = google_compute_network.app.id
  ip_cidr_range            = "10.40.0.0/24"
  private_ip_google_access = true
}

resource "google_compute_subnetwork" "run" {
  name                     = "tf-demo-run-subnet"
  region                   = var.region
  network                  = google_compute_network.app.id
  ip_cidr_range            = "10.40.1.0/24"
  private_ip_google_access = true
}
~~~

Both subnets reside in the same VPC with non-overlapping IP ranges. Separating subnets helps manage IP addressing, firewall rules, and traffic flows for each workload group.

Cloud Run Direct VPC egress requires an IPv4 subnet with a minimum size of `/26`. Cloud Run allocates IPs in blocks and may retain addresses after revisions scale down or update. Therefore, actual subnets should leave headroom for maximum instance counts and rollouts; the `/24` in the example provides plenty of addresses beyond the minimum.

Private Google Access allows resources with only internal IPs to reach supported Google APIs and services over private networking. This setting does not provide public Internet egress. If the VM needs to download packages or call Internet endpoints, consider Cloud NAT or an egress proxy.

## 6. Creating Firewall Rules and Securing Access Paths

A custom VPC network does not include application ingress rules by default. Ingress is blocked by default until an allow firewall rule permits it.

### 6.1. SSH via Identity-Aware Proxy

The example below permits SSH only from the IAP TCP forwarding range:

~~~hcl
resource "google_compute_firewall" "allow_iap_ssh" {
  name      = "tf-demo-allow-iap-ssh"
  network   = google_compute_network.app.name
  direction = "INGRESS"
  priority  = 1000

  source_ranges = ["35.235.240.0/20"]
  target_tags   = ["iap-ssh"]

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}
~~~

Operators also need IAM permissions to open an IAP tunnel, typically `roles/iap.tunnelResourceAccessor`, plus appropriate OS Login permissions if the VM enables OS Login. This rule does not expose SSH to the open Internet.

### 6.2. Allowing Cloud Run to Call the Backend VM

Suppose the backend on the VM listens on TCP port `8080`. Cloud Run Direct VPC egress allocates IPs from the Cloud Run subnet; source addresses change over revision lifecycles. Therefore, the firewall rule should use the entire subnet CIDR:

~~~hcl
resource "google_compute_firewall" "allow_run_to_backend" {
  name      = "tf-demo-allow-run-to-backend"
  network   = google_compute_network.app.name
  direction = "INGRESS"
  priority  = 1000

  source_ranges = [google_compute_subnetwork.run.ip_cidr_range]
  target_tags   = ["orders-backend"]

  allow {
    protocol = "tcp"
    ports    = ["8080"]
  }
}
~~~

This rule allows sources in the Cloud Run subnet to reach VMs with the `orders-backend` network tag on port `8080`. Narrow the CIDR and ports to match your actual design, and confirm the application on the VM actually listens on its internal address.

Do not assign an external IP to the VM if the workload only requires internal access. Administrative access can go through IAP; application traffic stays on private IPs inside the VPC.

## 7. Creating a Compute Engine VM with Terraform

### 7.1. Service Account for the VM

Each workload should have its own service account. For example:

~~~hcl
resource "google_service_account" "vm" {
  account_id   = "tf-demo-vm"
  display_name = "Terraform demo VM runtime"

  depends_on = [google_project_service.required]
}
~~~

The runtime service account only needs API permissions actually used by software on the VM. In this lesson, the VM illustrates internal network connectivity; do not grant Owner or Editor to the service account.

### 7.2. Declaring the VM

~~~hcl
resource "google_compute_instance" "backend" {
  name         = "tf-demo-backend"
  machine_type = "e2-small"
  zone         = var.zone
  tags         = ["iap-ssh", "orders-backend"]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 20
      type  = "pd-balanced"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.vm.id
  }

  metadata = {
    enable-oslogin = "TRUE"
  }

  service_account {
    email  = google_service_account.vm.email
    scopes = ["cloud-platform"]
  }

  depends_on = [google_project_service.required]
}
~~~

Key points to note:

- `zone` determines the zonal placement of the VM; the subnet's region must correspond to that zone.
- `boot_disk` defines the image, size, and persistent disk type.
- `network_interface` references the created subnet, so Terraform knows to create the subnet before the VM.
- There is no `access_config` in `network_interface`, so the VM is not assigned an external IPv4 address.
- `enable-oslogin` enables OS Login authentication. Users need `roles/compute.osLogin` to log in; `roles/compute.osAdminLogin` grants OS administrator permissions when `sudo` is needed.
- `cloud-platform` is a broad API OAuth scope, while IAM roles on the service account determine which APIs are actually permitted.

The VM above does not yet install a backend application automatically. In a real environment, you can use a startup script, a baked golden image, or a configuration management system to install the app and open port `8080`. Then verify connectivity from Cloud Run to the VM's private IP.

## 8. Deploying a Cloud Run Service and Connecting to the VPC

### 8.1. Cloud Run Using a Container Image

Cloud Run deploys container images from Artifact Registry or a supported registry. The image must exist and the deployment/runtime identities must have appropriate access permissions.

Create a service account for Cloud Run:

~~~hcl
resource "google_service_account" "run" {
  account_id   = "tf-demo-run"
  display_name = "Terraform demo Cloud Run runtime"

  depends_on = [google_project_service.required]
}
~~~

This service account is the revision's runtime identity. If the application needs to read Secret Manager, access a database, or call other APIs, grant the corresponding roles to this dedicated service account.

### 8.2. Cloud Run Direct VPC Egress

Direct VPC egress allows Cloud Run to send traffic to resources with private IPs inside a VPC without needing a Serverless VPC Access connector. With the Terraform Google provider, use the `google_cloud_run_v2_service` resource and the `vpc_access.network_interfaces` block.

~~~hcl
resource "google_cloud_run_v2_service" "orders" {
  name                = "tf-demo-orders"
  location            = var.region
  deletion_protection = true
  ingress             = "INGRESS_TRAFFIC_ALL"

  scaling {
    max_instance_count = 5
  }

  template {
    service_account = google_service_account.run.email

    containers {
      image = var.container_image

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }
    }

    vpc_access {
      egress = "PRIVATE_RANGES_ONLY"

      network_interfaces {
        network    = google_compute_network.app.id
        subnetwork = google_compute_subnetwork.run.id
      }
    }
  }

  depends_on = [google_project_service.required]
}
~~~

In this configuration:

- The Cloud Run service runs in the same region as the Direct VPC subnet.
- `service_account` specifies the runtime identity.
- The container image is a built and pushed image.
- `scaling` limits the maximum number of service instances to control capacity and cost.
- `PRIVATE_RANGES_ONLY` sends traffic destined for private addresses through the VPC; public Internet traffic does not automatically route through the VPC.
- `network_interfaces` attaches revisions to the declared VPC and subnet.

The Cloud Run service only uses Direct VPC egress for outbound traffic. This lets the service call the backend VM or internal services; it does not mean a VM can initiate connections to a Cloud Run instance via private IP like a regular VM.

The Direct VPC subnet must be in the same region as the Cloud Run service and at least `/26` in size. Cloud Run IPs are ephemeral; when creating firewall rules, use the subnet CIDR rather than hardcoding a single IP address. Monitor IP consumption when increasing `max_instance_count` or deploying new revisions.

The Cloud Run service agent needs the default `roles/run.serviceAgent` role to configure VPC connectivity. Do not remove this role from the service agent. The deployer also needs appropriate Cloud Run and Service Account User permissions on the service identity.

### 8.3. Ingress and Cloud Run Invocation Permissions

`ingress = "INGRESS_TRAFFIC_ALL"` allows requests to reach the service over network paths supported by Cloud Run. It does not automatically make the service public. Cloud Run still enforces IAM invoker checks by default.

If you intentionally want to open the service to everyone on the Internet, grant `roles/run.invoker` to `allUsers` using `google_cloud_run_v2_service_iam_member`. Only add this binding after deciding the service is genuinely public:

~~~hcl
resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  project  = var.project_id
  location = google_cloud_run_v2_service.orders.location
  name     = google_cloud_run_v2_service.orders.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
~~~

If the application requires authentication, do not create the `allUsers` binding. Use IAM principals, API Gateway, a load balancer, or an authentication mechanism suited to the architecture.

## 9. Connecting Resources into a Dependency Graph

Terraform automatically builds the deployment order from references between resources:

~~~mermaid
flowchart TD
    API["Project APIs"] --> VPC["VPC network"]
    VPC --> VMNET["VM subnet"]
    VPC --> RUNNET["Cloud Run subnet"]
    VPC --> FW1["IAP firewall"]
    VPC --> FW2["Cloud Run to VM firewall"]
    VMNET --> VM["Compute Engine VM"]
    SA1["VM service account"] --> VM
    RUNNET --> CR["Cloud Run service"]
    SA2["Cloud Run service account"] --> CR
    FW1 -.-> VM
    FW2 -.-> VM
~~~

For example, the subnet's `network` is referenced via `google_compute_network.app.id`. This is an implicit dependency: Terraform knows the VPC must exist before the subnet. Similarly, the VM references the subnet so Terraform creates the subnet before the VM.

Only use `depends_on` when there is a dependency an expression cannot represent, such as a resource needing to wait for an API to be enabled without referencing the API resource directly. Overusing `depends_on` makes the graph hard to read and can reduce parallel execution.

## 10. Variables, Outputs, and Environment Configuration

### 10.1. Assigning Input Values

`terraform.tfvars` can contain:

~~~hcl
project_id      = "my-gcp-project"
region          = "asia-southeast1"
zone            = "asia-southeast1-b"
container_image = "asia-southeast1-docker.pkg.dev/my-gcp-project/apps/orders-api:v1.4.0"
~~~

Avoid scattering project IDs, regions, or container images across many resources. Using variables lets you switch environments without modifying resource logic.

### 10.2. Exporting Post-Deployment Information

File `outputs.tf`:

~~~hcl
output "backend_internal_ip" {
  description = "Private IP of the Compute Engine backend"
  value       = google_compute_instance.backend.network_interface[0].network_ip
}

output "cloud_run_uri" {
  description = "URL of the Cloud Run service"
  value       = google_cloud_run_v2_service.orders.uri
}

output "vpc_name" {
  description = "Name of the VPC network"
  value       = google_compute_network.app.name
}
~~~

After applying, view outputs:

~~~bash
terraform output
~~~

Outputs give pipelines or operators resource addresses. Do not export passwords, tokens, or private keys; marking an output `sensitive` only hides terminal output and does not remove the value from state.

### 10.3. Separating Dev and Prod

Dev and prod can share modules but should have separate states, separate CIDRs, separate service accounts, and separate deployment permissions. For example:

| Component | Dev | Prod |
|---|---|---|
| Root module | `environments/dev` | `environments/prod` |
| State prefix | `gcp/network-app/dev` | `gcp/network-app/prod` |
| VPC | `tf-dev-vpc` | `tf-prod-vpc` |
| CIDR | `10.50.0.0/16` | `10.60.0.0/16` |
| Cloud Run max instances | `2` | Per production capacity |
| Apply permissions | Development team | Approved pipeline/operations team |

Do not use Terraform workspaces as the sole security boundary between production and non-production. Separating root directories, backend prefixes, and IAM permissions reduces the risk of accidentally applying a configuration to the wrong project or state.

## 11. Plan, Review, and Apply Workflow

### 11.1. Formatting and Validating

After creating the HCL files:

~~~bash
terraform fmt -recursive
terraform init
terraform validate
~~~

- `fmt` standardizes HCL formatting.
- `init` downloads providers and modules and initializes the backend.
- `validate` checks syntax and internal validity of the configuration.

`validate` does not confirm that every API, IAM permission, quota, or resource name on Google Cloud is valid. Those issues usually surface when `plan` or `apply` calls the provider.

### 11.2. Creating and Saving a Plan

Generate a plan file:

~~~bash
terraform plan -out=tfplan
~~~

Inspect plan details:

~~~bash
terraform show tfplan
~~~

Review resources to be created, modified, or destroyed. Pay particular attention to:

- Whether a VPC or subnet is being replaced.
- Whether a CIDR change impacts internal addressing.
- Whether a firewall rule widens source ranges or ports.
- Whether a VM's disk, machine type, or network interface is changing.
- Whether Cloud Run changes image, service account, ingress, or VPC egress.
- Whether resources have deletion protection or `lifecycle` `prevent_destroy`.

After the plan is reviewed and approved, apply the exact saved plan:

~~~bash
terraform apply tfplan
~~~

When applying from a saved plan, Terraform executes the exact actions in that plan. If configuration or state changes after the plan was generated, generate a new plan and review it again.

Do not use `terraform apply -auto-approve` in production if the process lacks an equivalent review step.

### 11.3. Post-Apply Verification

After Terraform reports `Apply complete`, verify on Google Cloud:

- VPC and subnets have the expected CIDRs, regions, and status.
- Firewall rules have the expected network, direction, target tags, source ranges, and ports.
- The VM resides in the intended subnet and has no external IP if designed as private.
- The Cloud Run service has a `Ready` revision, the right image, and the right VPC egress.
- Cloud Run can reach the private backend once the backend application is running.
- Workload IAM principals have the exact required permissions.

Terraform state confirms resource management linkage, while runtime verification confirms the application and network actually work.

## 12. Drift, Import, and Modifying Existing Resources

### 12.1. Detecting Drift

Drift occurs when actual resources are modified outside Terraform, such as someone editing a firewall rule in the Console. Terraform can detect differences when refreshing state during `plan`.

~~~bash
terraform plan
~~~

If you need to update state to match actual status without altering infrastructure, inspect a refresh-only plan:

~~~bash
terraform plan -refresh-only
~~~

Review before applying refresh-only. If the out-of-band change was intentional, update HCL to reflect the desired state. If the out-of-band change was unauthorized, a normal plan can restore the resource to the declared configuration.

### 12.2. Importing Existing Resources

If a VPC or VM was created manually and needs to be brought under Terraform, declare a resource block describing it and import it into state.

With Terraform 1.5 and later, you can use an `import` block:

~~~hcl
import {
  id = "projects/PROJECT_ID/global/networks/existing-vpc"
  to = google_compute_network.app
}
~~~

Run `plan` to inspect the import operation and configuration differences. After importing, adjust HCL to accurately reflect the real resource and continue managing it with Terraform.

Importing only links the existing resource to the resource address in state; it does not automatically ensure the HCL configuration is complete. Skipping review can cause the next apply to alter the resource unexpectedly.

### 12.3. Renaming Resource Addresses

When renaming a resource in HCL, Terraform may interpret the old resource as needing deletion and the new resource as needing creation. If you are only changing the management address, use a `moved` block to inform Terraform of the address change:

~~~hcl
moved {
  from = google_compute_instance.backend
  to   = google_compute_instance.orders_backend
}
~~~

After adding the `moved` block, run `plan` and confirm Terraform recognizes this as a state address move rather than creating a new VM.

## 13. Destroying Resources and Protecting Infrastructure

The `destroy` command deletes all resources managed in the current root module:

~~~bash
terraform plan -destroy
terraform destroy
~~~

Only run `destroy` when certain of the exact project, backend, and workspace. Accidentally destroying a production VPC or subnet can disrupt many workloads.

In the Cloud Run example, `deletion_protection = true` prevents Terraform from deleting the service while protection remains enabled. When you need to delete a service in a test environment, change the value to `false`, review the plan, apply the protection change, and only then run `destroy`. For critical resources such as the state bucket or shared networks, consider `lifecycle` `prevent_destroy` and a dedicated approval process.

When deleting according to the dependency graph, Terraform generally destroys dependent resources before foundational resources. For example, a Cloud Run service using a subnet must be destroyed before deleting that subnet. With Direct VPC egress, Google Cloud may retain allocated IP addresses for a period after the service/revision stops using the subnet; wait for resources to be released before deleting the subnet.

## 14. Organizing Modules and CI/CD

### 14.1. When Should You Split Modules?

Modules can be split when a group of resources has a clear responsibility and interface:

- A `network` module takes project, region, and CIDRs; outputs VPC ID and subnet IDs.
- A `compute` module takes subnet, machine type, image, and service account; outputs instance name and private IP.
- A `cloud-run` module takes region, image, service account, and VPC subnet; outputs the service URI.

Modules should have clear inputs/outputs and avoid depending on internal resource names of other modules. There is no need to create a module for every small resource if doing so makes the configuration harder to follow.

### 14.2. CI/CD for Terraform

A safe deployment pipeline typically includes:

1. Checking formatting with `terraform fmt -check`.
2. Initializing providers and backend with `terraform init`.
3. Checking configuration with `terraform validate`.
4. Running policy checks, security scans, or module tests per organizational standards.
5. Generating a plan file and storing the artifact with controlled access.
6. Reviewing the plan; production requires approval per operations team procedures.
7. Applying the exact approved plan.
8. Verifying resources and workloads after deployment.
9. Recording results and provider/module version details for traceability.

The CI identity should use Workload Identity Federation or impersonation. Do not let pipelines download static JSON keys and reuse them long-term.

## 15. Common Errors and Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Error 403 during plan/apply | ADC or service account lacks IAM permissions | Check actual principal, required roles, and selected project |
| API not enabled | API not enabled or Service Usage API not enabled first | Enable `serviceusage.googleapis.com`, then manage APIs with `google_project_service` |
| Backend bucket does not exist | GCS bucket has not been bootstrapped | Create the bucket first, then run `terraform init` |
| State lock is held | Another Terraform operation is running or an old lock was not released | Check running pipelines/sessions; only `force-unlock` when confirmed stale |
| Resource already exists | Resource was created manually or by another stack | Check ownership; import the exact resource or choose a new name |
| VM has no Internet connectivity | VM has no external IP and no Cloud NAT/proxy | Configure Cloud NAT or an appropriate egress path; Private Google Access only serves supported Google APIs |
| SSH to VM fails | Missing IAP firewall rule, IAP IAM role, or OS Login permission | Check IAP range `35.235.240.0/20`, `roles/iap.tunnelResourceAccessor`, and OS Login |
| Cloud Run cannot call VM | Wrong region/subnet, firewall missing source CIDR, or backend not listening on port | Check Direct VPC egress, source subnet CIDR, target tag, and service port |
| Cloud Run deploy fails to pull image | Wrong image or missing Artifact Registry permissions | Check image URI, repository location, and image access permissions |
| Plan wants to replace subnet or VM | Attribute change forces resource recreation or configuration differs from reality | Read `forces replacement` details, evaluate downtime and migration before applying |
| Cloud Run Direct VPC out of IPs | Subnet too small or high revision scale | Expand CIDR plan, monitor IP allocation, and set an appropriate `max_instance_count` |

## 16. Pre-Production Deployment Checklist

- [ ] Project, billing, quotas, and APIs are ready.
- [ ] Terraform CLI and Google provider are pinned to tested versions.
- [ ] Authentication uses ADC, Workload Identity Federation, or service account impersonation.
- [ ] State is stored in a dedicated GCS bucket with Object Versioning and state locking enabled.
- [ ] State bucket has uniform bucket-level access, public access prevention, and restricted IAM.
- [ ] Each environment has its own root module and state prefix.
- [ ] VPC uses custom subnets, non-overlapping CIDRs, and explicitly chosen regions.
- [ ] Firewalls open only required source ranges, targets, and ports.
- [ ] Private VMs have no external IP unless public ingress is required.
- [ ] Cloud Run uses a dedicated runtime service account with clearly designed ingress/auth.
- [ ] Direct VPC subnet has sufficient IPs for scaling and revision rollouts.
- [ ] Resource dependencies rely on references; `depends_on` is used only for hidden dependencies.
- [ ] Plans are saved, reviewed, and applied from the exact approved artifact.
- [ ] State, plans, and credentials are never committed or shared publicly.
- [ ] Procedures exist for import, drift review, rollback, and resource deletion.
- [ ] Runtime verification is performed after apply rather than relying solely on Terraform success messages.

## 17. Self-Check Questions

**1. Why is Terraform state needed?**

State maps resource addresses in HCL to real resources on Google Cloud. Terraform uses state to calculate changes, avoid duplicate resource creation, and identify resources to update or delete.

**2. How do VPC and subnet scopes differ on Google Cloud?**

A VPC network is a global resource, whereas a subnet is a regional resource. A single VPC can contain multiple subnets across different regions.

**3. Why use a custom-mode VPC with `auto_create_subnetworks = false`?**

Custom mode allows intentionally choosing CIDRs, regions, and separate subnets for each workload group. This makes IP management and firewall configuration clearer.

**4. What does Cloud Run Direct VPC egress use a subnet for?**

Cloud Run allocates IP addresses from the subnet to send traffic to internal resources inside the VPC. The subnet must be in the same region as the service and at least `/26`; reserve extra addresses based on instance scale and rollouts.

**5. Why use the GCS backend instead of keeping state on a personal machine?**

The GCS backend lets teams and pipelines share state, supporting state locking and Object Versioning to recover prior versions.

**6. How does `terraform plan` differ from `terraform apply`?**

`plan` computes and displays proposed changes. `apply` executes those changes on infrastructure after review and approval.

**7. When is `terraform import` needed?**

When a resource already exists on Google Cloud but is not yet managed by Terraform. Import links the resource to a resource address in state; the HCL configuration still needs to be verified and completed.

## 18. References

- [Terraform on Google Cloud](https://cloud.google.com/docs/terraform)
- [Getting started with the Google Cloud provider](https://registry.terraform.io/providers/hashicorp/google/latest/docs/guides/getting_started)
- [Google provider: google_compute_network](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_network)
- [Google provider: google_compute_subnetwork](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_subnetwork)
- [Google provider: google_compute_firewall](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_firewall)
- [Google provider: google_compute_instance](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_instance)
- [Google provider: google_cloud_run_v2_service](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/cloud_run_v2_service)
- [Google provider: google_project_service](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/google_project_service)
- [Store Terraform state in Cloud Storage](https://cloud.google.com/docs/terraform/resource-management/store-state)
- [Terraform GCS backend](https://developer.hashicorp.com/terraform/language/backend/gcs)
- [Terraform operations best practices](https://cloud.google.com/docs/terraform/best-practices/operations)
- [Cloud Run Direct VPC egress](https://cloud.google.com/run/docs/configuring/vpc-direct-vpc)
- [Connect Cloud Run to a VPC network](https://cloud.google.com/vpc/docs/configure-serverless-vpc-access)
