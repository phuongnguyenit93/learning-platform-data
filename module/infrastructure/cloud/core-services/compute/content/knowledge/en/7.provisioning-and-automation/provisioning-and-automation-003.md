# Declarative Templates, Input Variables, and Reusing Machine Configurations

When a team must create multiple virtual machines for development, staging, and production, configuring each machine manually easily leads to discrepancies. One machine might miss patches, another might open overly broad network ports, or production might accidentally use the wrong machine size. **Declarative templates** help describe the desired infrastructure state in code. **Input variables** allow customizing the values that vary by workload or environment, while **reusable modules and templates** enable multiple teams to deploy according to the same standard.

In cloud compute, machine configuration encompasses more than just CPU and RAM counts. A virtual machine also includes the OS image, region and subnet, security groups, disks, identity, metadata, initialization scripts, governance labels, and monitoring policies. When these values are explicitly declared, teams can review changes before applying them, recreate environments, and trace configurations across versions.

This lesson belongs to the **CLOUD_CORE_SERVICES_COMPUTE** module and focuses on how to describe, parameterize, and reuse machine configurations in provisioning and automation workflows. The primary examples use Terraform to illustrate variables, local values, outputs, and modules; cloud-init is used to illustrate initialization templates inside a VM. These concepts also apply to other IaC tools and cloud platforms, even though specific syntax may differ.

## 1. Why Do We Need Machine Configuration Templates?

A virtual machine is typically built from many decisions:

- Image and operating system version.
- Instance type, vCPU count, and RAM capacity.
- Region, subnet, IP address, and security groups.
- Boot disk, storage type, capacity, and encryption.
- Machine identity or instance role for calling cloud services.
- User-data or cloud-init for first-boot configuration.
- Environment, owner, application, and cost center labels.
- Monitoring, logging, backup, and update configurations.

If every engineer creates machines from memory, important parameters are easily overlooked. Configuration templates solve this by specifying mandatory attributes and allowed customization points.

For example, an organization might require every application VM to use an approved image, encrypted disks, no SSH/RDP exposed to the Internet, owner and environment tags, and an instance identity instead of static access keys. Development teams can still pick a machine size suited to their load from an allowed list.

Well-designed templates deliver these benefits:

1. **Consistency:** environments adhere to the same baseline.
2. **Reproducibility:** machines or environments can be recreated from saved code.
3. **Pre-deployment review:** changes are inspected via diffs and plans before deployment.
4. **Traceability:** clarity on who changed a configuration, what changed, and why.
5. **Reusability:** the same module can serve multiple applications.
6. **Reduced human error:** minimizes typos or forgotten configuration steps.
7. **Scale management:** common policies can be applied across many VMs and environments.

Automation does not automatically make a configuration secure. A flawed template can replicate a mistake across hundreds of machines. Therefore, testing, code review, version control, and access controls are required before broad adoption.

## 2. Declarative vs. Imperative Descriptions

There are two common ways to describe infrastructure provisioning.

**Imperative description** lists the steps to execute in sequence—for example, calling an API to create a VM, attaching a disk, configuring networking, and adding tags. The author must manage execution order, current state, and what happens when a step is re-run.

**Declarative description** states the desired end state—for example, a VM with a chosen image, two vCPUs, 4 GiB RAM, an encrypted disk, and placement in a private subnet. The tool reads the desired state, compares it with the actual state, and determines which operations to execute.

| Criterion | Imperative | Declarative |
|---|---|---|
| Focus | Steps to execute | Target end state to achieve |
| State management | Usually handled by scripts or the author | IaC tools typically track resource state |
| Re-running | Must be designed manually to avoid duplicates or errors | Typically converges toward the declared state |
| Previewing changes | Must be built manually | Tool can generate a plan or diff |
| Best suited for | Sequential tasks, bootstrapping, or specialized operations | Repeatable, structured infrastructure management needing review |

Declarative does not mean the tool skips underlying steps. The tool still invokes APIs in dependency order, while the user focuses on describing the desired outcome. Imperative scripts remain useful for certain initialization or integration tasks; keep them within a clear, controlled scope.

A declarative provisioning workflow typically follows this flow:

~~~mermaid
flowchart TD
    A["Workload requirements"] --> B["Select baseline and image"]
    B --> C["Provide input variables"]
    C --> D["Render modules and templates"]
    D --> E["Validate and run policy checks"]
    E --> F["Generate plan / diff"]
    F --> G{"Reviewed and approved?"}
    G -- "No" --> H["Adjust configuration"]
    H --> C
    G -- "Yes" --> I["Apply infrastructure"]
    I --> J["Bootstrap and verify VM"]
    J --> K["Monitor drift and lifecycle"]
~~~

## 3. Components of a Declarative Template

A machine provisioning template can be broken down into the following parts:

| Component | Purpose | Example |
|---|---|---|
| Resource | Declares a resource to create or manage | VM, disk, NIC, security group |
| Input variable | Accepts values from callers or environments | image ID, instance type, subnet ID |
| Local value | Creates derived values for internal use | machine name, common tags, resource naming |
| Output | Publishes information needed by other components | instance ID, private IP |
| Data source | Reads information about existing resources | approved image, existing subnet |
| Module | Packages a group of resources with an input/output interface | compute instance creation module |
| Template | Content template with placeholders substituted by values | cloud-init, user-data, or config file |

A good template has a clear interface. Users need to know which variables are required, which have defaults, what values are valid, which outputs are provided, and which resources will be created.

### 3.1. Input Variables

Input variables (or parameters) separate shared structural definitions from values that change per deployment.

Commonly parameterized values:

- Image ID or image version.
- Instance type or CPU/RAM configuration tier.
- Subnet, security groups, and deployment region.
- Disk capacity and volume type.
- Machine name, environment, owner, and application.
- Replica count or VM count.
- Non-secret initialization configuration.

Avoid turning every string in a template into an input. If a value must always follow an organizational standard, keep it inside the module or shared policy. Too many variables complicate the interface and allow callers to accidentally break the baseline.

### 3.2. Data Types, Defaults, and Descriptions

Type declarations help the tool catch invalid values before calling APIs. Common types include string, number, bool, list, map, object, and set.

Example:

~~~hcl
variable "instance_type" {
  description = "Approved compute machine type for the workload"
  type        = string
  default     = "t3.small"
}

variable "root_volume_gib" {
  description = "Boot disk capacity in GiB"
  type        = number
  default     = 30
}

variable "security_group_ids" {
  description = "List of security groups attached to the machine"
  type        = list(string)
}

variable "enable_monitoring" {
  description = "Enable detailed monitoring if supported by the platform"
  type        = bool
  default     = true
}
~~~

Variables with a default are optional for the caller; variables without a default generally must be supplied. Defaults should be safe and sensible. Do not set a production subnet, outdated image, or broad access permissions as a general default just to make the template easy to run.

### 3.3. Input Value Validation

Validation helps catch configuration errors early. You can validate numeric ranges, allowed choice lists, naming formats, or relationships between variables.

~~~hcl
variable "environment" {
  description = "Deployment environment"
  type        = string

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be dev, staging, or prod."
  }
}

variable "root_volume_gib" {
  description = "Boot disk capacity in GiB"
  type        = number
  default     = 30

  validation {
    condition     = var.root_volume_gib >= 20 && var.root_volume_gib <= 500
    error_message = "root_volume_gib must be between 20 and 500 GiB."
  }
}
~~~

Validation inside a module checks value validity, but it does not replace organization-level policies. For example, a well-formed security group ID does not prove that the rules inside only open necessary ports.

### 3.4. Local Values

A local value is a named derived value used to avoid repeating expressions and keep configurations readable. Locals are not user inputs.

~~~hcl
locals {
  name_prefix = "${var.environment}-${var.application}"

  common_tags = {
    Environment = var.environment
    Application = var.application
    ManagedBy   = "Terraform"
  }
}
~~~

If a machine name, tag map, or expression is used in multiple places, locals let you update it in one spot. However, avoid creating multiple layers of locals just to obscure simple expressions.

### 3.5. Outputs

Outputs publish information that other modules or downstream workflows need to consume. For example, a VM module can return the instance ID, private IP, and DNS name. Never output private keys, passwords, or secret data.

~~~hcl
output "instance_id" {
  description = "ID of the created virtual machine"
  value       = aws_instance.this.id
}

output "private_ip" {
  description = "Private IP address of the machine"
  value       = aws_instance.this.private_ip
}
~~~

Outputs establish a clear contract between a module and its caller. The caller does not need to know every internal detail of the module.

## 4. Input Variables and Environment Management

One infrastructure structure can serve multiple environments. The structural definition should stay the same, while values like image, subnet, instance type, machine count, and tags can differ.

Example:

| Attribute | Development | Staging | Production |
|---|---|---|---|
| Instance type | Small, cost-optimized | Close to production for testing | Based on load and SLO |
| Image | Latest approved build in test channel | Tested build | Approved release build |
| Subnet | Separate dev network | Separate staging network | Production private subnet |
| Count | One or few replicas | Close to production config | Based on load and HA |
| Logging | Sufficient for debugging | Retain test logs | Per retention and audit requirements |
| Backup | Per test data needs | Per recovery test procedures | Per RPO/RTO |
| Permissions | Scoped to dev team | Scoped to QA team | Per production procedures |

Separate variable files can be used, such as dev.tfvars, staging.tfvars, and prod.tfvars. These files contain only the differing values; the resource structure remains in the same module.

Example dev.tfvars file:

~~~hcl
environment        = "dev"
application        = "catalog"
ami_id             = "ami-0123456789abcdef0"
instance_type      = "t3.small"
subnet_id          = "subnet-0123456789abcdef0"
security_group_ids = ["sg-0123456789abcdef0"]
hostname           = "catalog-dev-01"
root_volume_gib    = 30
~~~

The IDs above are illustrative values using a familiar AWS format, not real resources. When deploying, use IDs belonging to the right account, region, and environment. For production, review variable files and plans before applying.

Avoid copying entire configuration directories per environment and editing them manually. That approach easily causes copies to drift over time. Share common modules and provide environment-specific inputs.

## 5. Packaging Configurations into Reusable Modules

A module is a packaged unit of configuration performing a clear responsibility. In Terraform, a directory containing one or more .tf files is treated as a module. A root module calls child modules to organize the system into parts with distinct responsibilities.

For example, a compute-instance module can accept an image, machine type, subnet, security groups, hostname, and tags; the module is responsible for creating the VM with an encrypted disk. Multiple applications can invoke that module with different values.

An illustrative directory structure:

~~~text
infrastructure/
├── environments/
│   ├── dev/
│   │   ├── main.tf
│   │   └── dev.tfvars
│   ├── staging/
│   │   ├── main.tf
│   │   └── staging.tfvars
│   └── prod/
│       ├── main.tf
│       └── prod.tfvars
└── modules/
    └── compute-instance/
        ├── main.tf
        ├── variables.tf
        ├── outputs.tf
        └── cloud-init.yaml.tftpl
~~~

The root module holds an environment's configuration and calls shared modules. Child modules define resources, variables, and outputs. Directory layouts may vary with project scale; the goal is to clearly separate shared components from environment-specific configuration.

### 5.1. Designing Module Interfaces

A module should be scoped tightly enough to represent a single responsibility, yet not so granular that users must wire together dozens of tiny modules. For example, a compute-instance module might create one complete virtual machine; a larger module might create a web server group and load balancer if they are always managed as one unit.

A module interface should provide:

- Variable names reflecting business meaning, not just provider API field names.
- Clear data types and descriptions.
- Safe defaults for inputs that genuinely can have defaults.
- Validation for critical values and relationships.
- Minimal but sufficient outputs.
- Module versioning and backward-compatible change guidelines.

Avoid embedding excessive application-specific logic into shared modules. Specialized parts can be passed through controlled inputs or kept in the root module.

### 5.2. Reusing While Preserving Differences

Reusability does not mean every VM must be identical. Modules provide the shared structure, while input variables express legitimate differences.

Examples:

- An API needs more CPU than a file-processing worker.
- Production requires more replicas and stricter backups than dev.
- A data-processing VM needs large disks, whereas a proxy VM needs high network bandwidth.
- One application needs a Linux image while another needs Windows Server.

Create inputs for intentional differences. When a rare exception arises, consider a specialized module or a well-bounded optional variable rather than adding complex conditional branches into a shared module.

## 6. Example: Terraform Module Creating a Virtual Machine

The following example uses the AWS provider to illustrate a VM resource. The module structure and variable usage apply similarly to other providers, though resource names, configuration fields, and security rules will differ. The template assumes the subnet and security groups are already created elsewhere; the module only creates the EC2 instance.

### 6.1. variables.tf

~~~hcl
variable "ami_id" {
  description = "ID of the approved image"
  type        = string
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.small"
}

variable "subnet_id" {
  description = "Subnet where the instance is placed"
  type        = string
}

variable "security_group_ids" {
  description = "Security groups attached to the instance"
  type        = list(string)
}

variable "hostname" {
  description = "Hostname configured inside the guest OS"
  type        = string
}

variable "environment" {
  description = "Deployment environment name"
  type        = string

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be dev, staging, or prod."
  }
}

variable "root_volume_gib" {
  description = "Root volume capacity"
  type        = number
  default     = 30

  validation {
    condition     = var.root_volume_gib >= 20 && var.root_volume_gib <= 500
    error_message = "root_volume_gib must be between 20 and 500 GiB."
  }
}

variable "tags" {
  description = "Additional tags for the instance"
  type        = map(string)
  default     = {}
}
~~~

Required variables such as ami_id, subnet_id, and security_group_ids have no defaults. Callers must supply them, preventing the module from silently picking the wrong network or image.

### 6.2. main.tf

~~~hcl
locals {
  common_tags = {
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

resource "aws_instance" "this" {
  ami                    = var.ami_id
  instance_type          = var.instance_type
  subnet_id              = var.subnet_id
  vpc_security_group_ids = var.security_group_ids

  user_data = templatefile("${path.module}/cloud-init.yaml.tftpl", {
    hostname    = var.hostname
    environment = var.environment
  })

  root_block_device {
    volume_size = var.root_volume_gib
    volume_type = "gp3"
    encrypted   = true
  }

  metadata_options {
    http_tokens = "required"
  }

  tags = merge(local.common_tags, var.tags, {
    Name = var.hostname
  })
}
~~~

The resource uses inputs to configure the machine. Local values construct common tags; merge combines common tags with caller-supplied tags. In this example, the Name tag is placed last so the hostname value takes final precedence. The module enables root volume encryption and requires IMDSv2 tokens on AWS instances. These attributes are AWS provider examples; verify provider versions and organizational policies before use.

### 6.3. cloud-init.yaml.tftpl

~~~yaml
#cloud-config
preserve_hostname: false
hostname: ${hostname}
package_update: true
packages:
  - nginx
  - curl
write_files:
  - path: /etc/motd
    permissions: "0644"
    content: |
      Environment: ${environment}
runcmd:
  - [systemctl, enable, --now, nginx]
~~~

This is a cloud-init template rendered by Terraform using templatefile. The hostname and environment placeholders receive values from the passed map. The template file contains only non-secret initialization configuration. Never put passwords, private keys, or tokens inside templates or user-data.

### 6.4. outputs.tf

~~~hcl
output "instance_id" {
  description = "ID of the instance"
  value       = aws_instance.this.id
}

output "private_ip" {
  description = "Private IP address of the instance"
  value       = aws_instance.this.private_ip
}

output "instance_arn" {
  description = "ARN of the instance"
  value       = aws_instance.this.arn
}
~~~

### 6.5. Calling the Module from the Root Module

~~~hcl
module "catalog_vm" {
  source = "../../modules/compute-instance"

  ami_id             = var.catalog_ami_id
  instance_type      = var.catalog_instance_type
  subnet_id          = var.private_subnet_id
  security_group_ids = [aws_security_group.catalog.id]
  hostname           = "catalog-${var.environment}-01"
  environment        = var.environment
  root_volume_gib    = 40

  tags = {
    Application = "catalog"
    Owner       = "commerce-platform"
  }
}
~~~

The root module passes environment- and workload-specific values. The module can be invoked multiple times for different VMs without duplicating resource blocks. If multiple identical instances are needed, for_each or count can be used at the call site, provided stable keys are chosen to avoid unintended resource replacement when the list changes.

## 7. Creating Machine Configurations from Lists or Matrices

A system can have multiple machine groups with distinct roles: web, worker, batch, and monitoring. Each group can be described as an object containing count, instance type, image, and tags.

Example configuration data schema:

~~~hcl
variable "node_pools" {
  description = "Configuration of machine groups by role"
  type = map(object({
    instance_type = string
    desired_count = number
    ami_id         = string
    volume_gib     = number
  }))
}
~~~

A variable file can declare:

~~~hcl
node_pools = {
  web = {
    instance_type = "t3.small"
    desired_count = 2
    ami_id         = "ami-0123456789abcdef0"
    volume_gib     = 30
  }
  worker = {
    instance_type = "t3.medium"
    desired_count = 3
    ami_id         = "ami-0123456789abcdef0"
    volume_gib     = 50
  }
}
~~~

Object structures clearly show readers the required attributes for each machine group. You can use for_each to create resources or call modules per element. However, consider whether the groups share the same lifecycle and policies. If web and worker have different deployment, scaling, and backup approaches, manage them with separate modules even if both share an underlying compute module.

Do not allow arbitrary user-supplied lists into every configuration field. Restrict allowed values, such as lists of permitted instance types, approved images, and valid subnets per environment.

## 8. Reusing Images and Initialization Configurations

IaC modules describe cloud resources; machine images supply the operating system and foundational software; cloud-init or bootstrap scripts configure the instance at boot time. These three layers complement each other:

| Layer | Responsibility | Example |
|---|---|---|
| Machine image | Standardized OS, base packages, and agents | Linux image with monitoring agent and tested patches |
| IaC module/template | Cloud resources and connections between them | VM, subnet, security group, disk, and instance role |
| Bootstrap/configuration | Instance- and application-specific configuration | hostname, extra packages, services, and runtime config |

Avoid reinstalling the entire OS and large packages on every VM boot when a pre-tested image can be prepared. Bootstrapping should focus on per-instance configuration or steps that vary by environment.

For Windows, you can use EC2Launch, cloudbase-init, PowerShell, or the provider's bootstrap agent. For Linux, cloud-init is a common choice. Ensure scripts run safely across reboots or implement execution-once controls.

## 9. Separating Configuration from Secrets

A critical mistake is placing passwords, access keys, private keys, or tokens directly inside .tf files, tfvars files, user-data, or templates. Those values can end up stored in Git, logs, plans, or state.

Apply these principles:

- Store only non-sensitive configuration values in code.
- Use IAM roles, instance profiles, or managed identities to grant permissions to workloads.
- Store secrets in an organization-approved secret manager or vault.
- Have VMs retrieve secrets at runtime using their own identity and least-privilege permissions.
- Avoid outputting secrets from modules.
- Protect state files and plan artifacts because they may contain sensitive data.
- Never commit tfvars files containing secrets to repositories.

In Terraform, the sensitive = true attribute masks values in certain CLI outputs, but it does not automatically encrypt or remove the value from state. Use a secure state backend, encryption at rest, read access controls, state locking where supported, and policy-compliant backups.

## 10. Managing State and Infrastructure Changes

For stateful IaC tools like Terraform, state links the declared configuration to real-world resources. It tells the tool which resources have been created, their IDs, and which attributes to track.

State is a critical component:

- Use a remote backend when multiple people manage infrastructure.
- Enable state locking if supported by the backend to prevent concurrent applies.
- Encrypt state at rest and restrict access permissions.
- Back up state and maintain a recovery procedure.
- Do not manually edit state without understanding the impact and taking a backup first.
- Do not share a single state across environments that require independent permission boundaries and lifecycles.

### 10.1. Plan and Apply Workflow

A basic Terraform workflow:

~~~bash
# Initialize the directory and providers
terraform init

# Check syntax and formatting
terraform fmt -check
terraform validate

# Preview planned changes for the dev environment
terraform plan -var-file="dev.tfvars" -out="dev.tfplan"

# Review the plan, then apply the exact saved plan
terraform apply "dev.tfplan"

# View published outputs
terraform output
~~~

Do not auto-apply to production simply because the plan completed without errors. Review changes that could replace or destroy VMs, disks, security groups, and dependent resources. Whenever the tool indicates a resource will be destroyed and recreated, verify data impact and outage windows.

### 10.2. Drift Detection

Configuration drift occurs when live state differs from declared code—for instance, an operator modifies a security group directly in the console. The next plan can detect part of the discrepancy and propose returning the resource to the declared configuration.

Not every out-of-band change is wrong; sometimes emergency changes must be legitimized. Update source code after an approved change so code and infrastructure return to a single source of truth. Ignoring drift long-term can cause subsequent applies to produce unexpected changes.

## 11. Module Versioning, Compatibility, and Releases

Shared modules become interfaces that many teams depend on. Changing variable names, data types, defaults, or outputs can impact numerous workloads.

Key principles:

1. Assign versions to modules or releases.
2. Pin provider and module versions according to project policy.
3. Document changes in a changelog or release notes.
4. Prefer backward-compatible changes whenever possible.
5. When removing a variable is necessary, provide a deprecation period and migration guide.
6. Test modules with both a minimal example config and a production-representative config.
7. Run security and policy reviews before releasing shared modules.

When referencing a module from a registry or Git repository, pin to a specific version or tag rather than always pulling the latest branch. This ensures future deployments can reproduce the exact tested version.

## 12. Quality and Policy Checks for Templates

A configuration template must be validated before widespread adoption. Verification layers typically include:

- **Format and syntax:** consistent code formatting and valid structure.
- **Validation:** variables have valid types, values, and constraints.
- **Static analysis:** detects risky configurations or deprecated attributes.
- **Policy as code:** enforces rules such as encrypted disks, no publicly open management ports, required tags, and approved images.
- **Plan review:** inspects resources to be created, modified, replaced, or deleted.
- **Integration test:** deploys into a test environment and verifies connectivity, bootstrapping, and monitoring.
- **Security scan:** inspects images, packages, configurations, and permissions.

For example, a policy may require every production machine to have Environment, Owner, and Application tags; encrypted root disks; and no public IP on VMs unless the workload has an approved exception. Policies must be enforced in pipelines or governance platforms rather than existing only in documentation.

Do not rely solely on validation inside a module to protect the entire cloud environment. Security groups may be created elsewhere, IAM permissions may live in another module, and organizational policies may apply at the account or subscription level.

## 13. End-to-End Workflow Example: From Request to Virtual Machine

Suppose a development team needs a Linux VM running the catalog API in the dev environment. The team already has an approved image, a private subnet, and a security group allowing only necessary traffic.

The workflow can proceed as follows:

1. The team selects the released compute-instance module.
2. They provide ami_id, instance_type, subnet_id, security_group_ids, hostname, and environment.
3. The module validates input types and values.
4. Terraform generates a plan showing the VM, encrypted disk, and tags to be applied.
5. Reviewers confirm there are no unexpected changes.
6. The pipeline applies the plan using a deployment identity with restricted permissions.
7. The VM boots, cloud-init sets the hostname, installs required packages, and starts the service.
8. The instance registers with the monitoring system and retrieves secrets via instance identity if needed.
9. The pipeline checks the health endpoint and stores the output instance ID and private IP.
10. All subsequent changes are made through code and the review workflow.

When the team needs staging, they can invoke the same module with a staging variable file. The resource structure remains shared; environment values are controlled separately.

## 14. Common Mistakes

- **Hardcoding environment values:** causes dev, staging, and production to easily use the wrong subnet, image, or permissions.
- **Creating too many variables:** complicates module interfaces and exposes unnecessary customizations.
- **Skipping input validation:** can create VMs with invalid sizes, images, or regions.
- **Copying modules per application:** causes copies to diverge and makes security baseline updates hard.
- **Using an oversized module:** bundles too many responsibilities and gives every change a wide blast radius.
- **Putting secrets in code or user-data:** exposes secrets through repositories, logs, plans, or state.
- **Treating sensitive as encryption:** sensitive mainly hides display output; state still requires protection.
- **Not pinning versions:** a module or provider update can make the next deployment differ from the previous one.
- **Applying without reviewing the plan:** can destroy or replace machines and volumes holding data.
- **Ignoring drift:** live configuration and declared code gradually fall out of sync.
- **Testing syntax only:** a template may be syntactically valid yet lack permissions, networking, backups, or monitoring.

## 15. Process for Building a Shared Configuration Template

Follow this process when creating a machine provisioning module:

1. **Gather requirements:** determine workload type, OS, CPU/RAM, storage, networking, security, and availability needs.
2. **Define the baseline:** distinguish mandatory attributes from values allowed to vary.
3. **Design inputs/outputs:** choose data types, defaults, validations, and required outputs.
4. **Separate responsibilities:** decide what belongs in the image, IaC module, and bootstrap/configuration layer.
5. **Write the module:** use clear names and organize resources and local values legibly.
6. **Check security:** keep secrets out of code, protect state, restrict permissions, and enforce policies.
7. **Test:** format, validate, plan, deploy to a test environment, and verify the application.
8. **Release with versioning:** maintain a changelog, pin versions, and provide usage documentation.
9. **Operate and improve:** monitor drift and periodically update images, providers, modules, and policies.

## 16. Takeaways

Declarative templates describe the desired infrastructure state; input variables capture legitimate differences across workloads and environments; local values reduce expression duplication; outputs define interfaces for other components; and modules package configurations for reuse. Images and cloud-init complement this by providing the OS and in-VM initialization configuration.

To automate compute safely and repeatably, design modules with small, clear interfaces, validate inputs, separate configuration from secrets, manage state and versions, review plans before applying, and verify policy compliance and recoverability. When code becomes the source of infrastructure description, teams can recreate machines consistently and control changes throughout the operational lifecycle.
