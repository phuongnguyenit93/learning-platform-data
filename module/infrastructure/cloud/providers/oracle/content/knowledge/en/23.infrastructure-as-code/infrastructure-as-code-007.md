# Storing Terraform Configurations in Git and Connecting Resource Manager

## Lesson Objectives

In the **Infrastructure as Code** chapter of the **CLOUD_PROVIDERS_ORACLE** module, this lesson walks through putting Terraform configurations into Git and using Oracle Cloud Infrastructure Resource Manager to execute them. This bridges infrastructure code managed by the engineering team and live resources in an OCI tenancy.

After this lesson, you can:

- Organize a repository so Resource Manager executes the right Terraform directory.
- Distinguish Git access permissions, stack/job management permissions, and permissions acting on OCI resources.
- Create a configuration source provider, connect a repository to a stack, and run plan before apply.
- Track changes through commits, jobs, and state; troubleshoot common connection errors.
- Apply the same workflow when expanding from VCN to Compute, storage, or Oracle databases, taking cost and availability into account.

The running example is a private GitHub repository containing a configuration that creates **one VCN for a practice lab**. The lesson does not require creating VMs, volumes, gateways, or databases to verify connectivity.

## 1. What Do Git and Resource Manager Handle?

Git stores the history of the **desired configuration**: which resources must exist, their attributes, and why changes were made. Resource Manager provides a managed OCI service to run Terraform, managing stacks, jobs, and state.

| Component | Role | Example in This Lesson |
| --- | --- | --- |
| Git repository | Stores code, commit history, and review process | `oci-iac-lab` |
| Branch | Selects the development line used by the stack | `main` |
| Working directory | Root module directory where Terraform runs inside the repository | `environments/dev` |
| Configuration source provider | Stores connection and authentication details for the Git service | `github-iac-lab` |
| OCI Terraform provider | Plugin that understands OCI resources and calls OCI APIs | `oracle/oci` |
| Stack | Binds configuration with input variables, Terraform version, and state | `oci-iac-dev` |
| Job | A single execution of plan, apply, or destroy | A plan job awaiting review |
| State | Maps Terraform addresses to managed resources | `oci_core_vcn.lab` ↔ VCN OCID |

**A configuration source provider and a Terraform provider are two different concepts.** The first lets Resource Manager pull code from Git; the second lets Terraform interact with OCI.

Resource Manager generates and updates state for a stack itself. Git does not replace state storage. Having a VCN's code in Git does not mean a new stack automatically knows about a VCN already existing in reality. See [Resource Manager Overview](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Concepts/resourcemanager.htm).

~~~mermaid
flowchart LR
    A["Edit code on working branch"] --> B["Review and merge into main"]
    B --> C["Repository: environments/dev"]
    C --> D["Resource Manager pulls code via configuration source provider"]
    D --> E["Stack and input variables"]
    E --> F["Plan job"]
    F --> G["Review changes"]
    G --> H["Apply using selected plan"]
    H --> I["VCN in target compartment"]
    H --> J["State and job history"]
~~~

The arrow from Git to Resource Manager represents fetching code when executing a relevant operation. **Merely connecting Git to a stack does not set up a trigger to auto-run apply on every push.** In this lesson, the operator explicitly triggers jobs; a pipeline calling the API/CLI is an additional automation layer.

## 2. Preparing Lab Scope and Access Permissions

### 2.1. Information to Lock Down First

Prepare a tenancy, a region subscribed by the tenancy, and a dedicated compartment for this lab. Record:

| Information | Meaning |
| --- | --- |
| Resource Manager operating region | Where you create and look up stacks, configuration source providers, and jobs |
| OCID of compartment holding the stack | Management location of the stack object |
| OCID of compartment holding the VCN | Target of `var.compartment_ocid` |
| Git server URL | Endpoint of the Git service, not the URL of a single Terraform file |
| Repository URL | Path of the repository the stack will read |
| Branch and working directory | Pair of values identifying the root module to run |

To keep things easy to follow, the example uses the same region for Resource Manager and the VCN, and places the stack, configuration source provider, and VCN in the same lab compartment. In real systems, these can be separated; when they are, IAM must cover each involved compartment.

**The compartment containing the stack does not automatically determine the VCN's compartment.** The `oci_core_vcn` resource uses the `compartment_id` value in code. Similarly, the resource's region is determined by the provider configuration; always cross-check with the region selected in the Console.

### 2.2. Three Independent Permission Layers

| Layer | What It Controls | Typical Error |
| --- | --- | --- |
| Git | Can Resource Manager read the repository and branch? | Expired token, repository not listed |
| Resource Manager IAM | Can the operator create stacks, read source providers, and run jobs? | Denied creating stacks or jobs |
| IAM for target resources | Can Terraform operations manage VCNs in the target compartment? | Code fetch succeeds, but OCI denies VCN creation |

Example policies **for the operations group in the lab compartment**:

~~~text
Allow group 'Default'/'IacOperators' to read orm-config-source-providers in compartment IacLab
Allow group 'Default'/'IacOperators' to manage orm-stacks in compartment IacLab
Allow group 'Default'/'IacOperators' to manage orm-jobs in compartment IacLab
Allow group 'Default'/'IacOperators' to manage virtual-network-family in compartment IacLab
~~~

The team assigned to administer Git connections needs corresponding permissions, such as:

~~~text
Allow group 'Default'/'IacSourceAdmins' to manage orm-config-source-providers in compartment IacLab
~~~

Replace the identity domain, group names, and compartment with actual objects. Policies must be placed by an administrator at an appropriate effective scope. `manage virtual-network-family` covers more network resources than a VCN; here it is bounded to the lab compartment and is not a minimal permission template for every system.

Resource Manager permissions do not automatically grant Compute, Object Storage, or Database permissions. When extending this lesson, add permissions for the exact resource types and target compartments. Oracle describes these two permission groups in [Securing Resource Manager](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/resourcemanager_security.htm); relationships between stack and job permissions are listed in [Details for Resource Manager](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/resourcemanagerpolicyreference.htm).

## 3. Designing the Repository So Resource Manager Runs the Right Configuration

### 3.1. One Root Module per State Scope

Recommended layout for the practice lab:

~~~text
oci-iac-lab/
├── .gitignore
├── README.md
└── environments/
    └── dev/
        ├── versions.tf
        ├── providers.tf
        ├── variables.tf
        ├── main.tf
        ├── outputs.tf
        ├── terraform.tfvars.example
        └── .terraform.lock.hcl
~~~

`README.md` should document the purpose, root module, required variables, owners, and resource cleanup instructions. `.terraform.lock.hcl` is generated after initializing Terraform; do not hand-write checksums.

In this layout, the stack's working directory is **`environments/dev`**, not `/environments/dev` and not a GitHub URL like `.../tree/main/environments/dev`.

Resource Manager requires the working directory to contain at least one `.tf` file; the configuration must not contain state or the `.terraform` directory. If the repository root is selected by mistake, Terraform files nested inside `environments/dev` do not automatically become the root module. See [Terraform configuration requirements for Resource Manager](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Concepts/terraformconfigresourcemanager.htm).

When adding production, create a separate root module and stack for production, with its own state, compartment, and permissions. Never point two independent stacks at the same live resources expecting Git to synchronize state between them.

### 3.2. Which Files Belong in Git?

Put `.tf` code, documentation, non-secret sample variable files, and the root module's lock file into Git. Exclude downloaded provider/module directories, state, saved plans, and credentials.

Example `.gitignore` at the repository root:

~~~gitignore
# Working directory data and state
**/.terraform/
*.tfstate
*.tfstate.*
.terraform.tfstate.lock.info

# Saved plans per team convention
*.tfplan
tfplan
plan.out
crash.log
crash.*.log

# Environment-specific values
*.tfvars
*.tfvars.json

# Keys and local authentication configs
*.pem
*.key
.oci/
.env
.env.*

# Do not ignore .terraform.lock.hcl
~~~

`terraform.tfvars.example` does not match the `*.tfvars` pattern, so it can be committed. Terraform also does not auto-load files with this `.example` suffix.

HashiCorp recommends committing code and dependency lock files while excluding state, `.terraform` directories, saved plans, and variable files containing sensitive data from version control. See [Terraform Style Guide](https://developer.hashicorp.com/terraform/language/style).

`.gitignore` only affects untracked files. If a secret has already entered Git history, revoke or rotate that secret first, then clean history per team procedure. Deleting the file in a newer commit does not remove the value from older commits.

## 4. Minimal Terraform Configuration for the VCN Lab

Create the files under `environments/dev`. The snippets below are sample contents for learners to add to their repository.

### 4.1. Version Constraints

`versions.tf`:

~~~hcl
terraform {
  required_version = ">= 1.2.0, < 2.0.0"

  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "~> 7.0"
    }
  }
}
~~~

`~> 7.0` permits provider versions from `7.0.0` up to before `8.0.0`. This is an illustrative choice to bound a major version, not a claim that provider 7.x is the latest release. When applying to a real project, teams pick a verified version range and a compatible Terraform runtime provided by Resource Manager.

The lock file records the exact selected provider version along with package verification hashes. It does not replace version constraints in code and does not lock versions of all remote modules. See [Dependency Lock File](https://developer.hashicorp.com/terraform/language/files/dependency-lock).

### 4.2. Provider and Input Variables

`providers.tf`:

~~~hcl
provider "oci" {
  region = var.region
}
~~~

In Resource Manager, the OCI provider does not need user OCID, fingerprint, or private key embedded in code; `region` is the required configuration field noted by Oracle for this execution mode. Configuring authentication when running Terraform directly on a personal machine is separate and personal keys must never be copied into Git. See [Terraform Configurations for Resource Manager](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Concepts/terraformconfigresourcemanager.htm).

`variables.tf`:

~~~hcl
variable "region" {
  description = "OCI region subscribed by the tenancy."
  type        = string
}

variable "compartment_ocid" {
  description = "Target compartment OCID containing the lab VCN."
  type        = string
}

variable "environment" {
  description = "Environment name used in resource names and tags."
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "test", "prod"], var.environment)
    error_message = "environment must be dev, test, or prod."
  }
}

variable "vcn_cidr" {
  description = "IPv4 CIDR for the VCN; avoid overlapping connected networks."
  type        = string
  default     = "10.42.0.0/16"
}

variable "owner" {
  description = "Responsible team name; do not use secret data."
  type        = string
  default     = "platform-lab"
}
~~~

`terraform.tfvars.example`:

~~~hcl
region           = "ap-singapore-1"
compartment_ocid = "ocid1.compartment.oc1..REPLACE_WITH_LAB_COMPARTMENT"
environment      = "dev"
vcn_cidr         = "10.42.0.0/16"
owner            = "platform-lab"
~~~

Region and OCID here are examples, not a pre-existing account. When creating the stack, enter real values into the variable configuration screen. Committing the sample file does not make Resource Manager automatically use the values inside it.

### 4.3. Resources and Outputs

`main.tf`:

~~~hcl
resource "oci_core_vcn" "lab" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = [var.vcn_cidr]
  display_name   = format("iac-lab-%s", var.environment)
  dns_label      = "iaclab"

  freeform_tags = {
    Environment = var.environment
    Owner       = var.owner
    ManagedBy   = "Terraform"
  }
}
~~~

`outputs.tf`:

~~~hcl
output "vcn_ocid" {
  description = "OCID used to verify the VCN managed by the stack."
  value       = oci_core_vcn.lab.id
}

output "vcn_display_name" {
  value = oci_core_vcn.lab.display_name
}
~~~

The configuration declares only a single VCN resource. OCI automatically creates accompanying default network objects such as a route table, security list, and DHCP options; they are not three separate Terraform resources in this example. The `cidr_blocks` attribute and default behaviors are documented in [oci_core_vcn resource documentation](https://docs.oracle.com/en-us/iaas/tools/terraform-provider-oci/latest/docs/r/core_vcn.html).

Do not add database passwords or private keys to outputs. When extending this workflow to Database services, design secret provisioning and state controls separately; marking a value sensitive does not remove the secret from state.

## 5. Validating Code and Creating the Initial Git History

The commands below are for learners to run inside a repository checkout. They do not run apply from a personal machine.

From the repository root:

~~~powershell
terraform fmt -recursive
terraform -chdir=environments/dev init -backend=false
terraform -chdir=environments/dev validate
~~~

`init` downloads providers/modules and creates the lock file; `validate` checks configuration without proving IAM, quotas, or OCI resource availability. `-backend=false` keeps this initialization strictly for local validation rather than configuring a backend to deploy in place of the stack.

If both Windows workstations and Linux runners use the root module, you can pre-populate checksums for those platforms:

~~~powershell
terraform -chdir=environments/dev providers lock -platform=windows_amd64 -platform=linux_amd64
~~~

Review the generated lock file and commit it alongside the code. Resource Manager manages the dependency lock file itself for new or updated stacks; therefore, verify the provider version in job logs and manage upgrades intentionally rather than assuming the local lock file is the service's entire locking mechanism. Lock file behavior and upgrade options are described by Oracle in [Creating a Plan Job](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Tasks/create-job-plan.htm).

If this is a fresh Git directory, initialize and inspect the file list:

~~~powershell
git init -b main
git status --short
git add .gitignore README.md environments/dev
git diff --cached --stat
git diff --cached
git commit -m "Add OCI lab VCN configuration"
git remote add origin https://github.com/YOUR_ACCOUNT/oci-iac-lab.git
git push -u origin main
~~~

Replace `YOUR_ACCOUNT` and create the target repository before pushing. If the repository already has history or an `origin` remote, use your existing checkout and remote instead of re-running initialization steps.

Before committing, confirm there is no state, PAT, OCI signing key, or saved plan in the staging area. Never embed tokens into the `git remote` URL. Authenticate personal pushes using your organization's Git mechanism, which is independent of the PAT used by Resource Manager.

## 6. Creating the Configuration Source Provider on OCI

### 6.1. Choosing the Right Connection Type

Resource Manager supports configuration source providers for GitHub, GitLab, and Bitbucket; OCI DevOps has its own stack creation flow. Specific products and endpoints are listed in [Managing Configuration Source Providers](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Tasks/managingconfigurationsourceproviders.htm).

This lab uses **GitHub on a public host with a private repository**. These two properties are distinct:

- A private repository requires authentication and code read permissions.
- A Git server inside a private network additionally requires network routing, DNS resolution, and TLS trust from Resource Manager.

A personal laptop reaching a Git server over VPN does not prove that Resource Manager runners can reach it too.

### 6.2. Preparing an Appropriate PAT for GitHub Integration

In the Oracle documentation referenced for this lesson, GitHub prerequisites include admin/owner permissions on the repository and a PAT with the `repo` scope. For GitHub Enterprise Cloud, Oracle also notes an SSO requirement for the PAT. Do not assume every type of fine-grained PAT is compatible with this integration.

The `repo` scope is broader than pure read-only access, even though Resource Manager only reads the repository and does not push changes. Use an integration account with controlled repository scope, set a token expiration, and assign an owner responsible for rotation.

Console steps:

1. Navigate to **Resource Manager → Configuration source providers** and check the region and compartment.
2. Click **Create configuration source provider** and name it `github-iac-lab`.
3. Select **GitHub** and enter the appropriate server URL. For personal GitHub accounts, for example, this is `https://github.com`; this field differs from the repository URL.
4. Enter the PAT into the connection's authentication field.
5. Create the provider, open its details, and click **Validate connection**.

Source for prerequisites, endpoints, and steps: [Creating a GitHub Configuration Source Provider](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Tasks/create-csp-github.htm).

Never save the PAT in `variables.tf`, `terraform.tfvars`, README, outputs, or screenshots. For internal Git servers, prepare a Resource Manager private endpoint, DNS, routes, network rules, and appropriate certificates before use; never disable TLS verification to work around connection errors.

A successful Validate connection only proves the connection can authenticate to the endpoint; you still need to confirm access to the specific repository and branch when creating the stack.

## 7. Creating a Stack from the Git Repository

On the **Stacks** page, click **Create stack** and configure:

| Field | Value for the Practice Lab |
| --- | --- |
| Origin | Source code control system |
| Source code management type | GitHub |
| Configuration source provider | `github-iac-lab` |
| Repository | Your `oci-iac-lab` repository |
| Branch | `main` |
| Working directory | `environments/dev` |
| Stack name | `oci-iac-dev` |
| Compartment | Compartment managing the lab stack |
| Terraform version | Supported service runtime satisfying `required_version` |

Proceed to variables, enter the right `region`, `compartment_ocid`, `environment`, `vcn_cidr`, and `owner`. Review the full configuration and create the stack. In this lesson, **leave the Run apply option unchecked** so you can inspect the plan first.

Selecting repository/branch/working directory and entering variables follows the official flow at [Creating a Stack from Git](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Tasks/create-stack-git.htm).

If the repository does not appear, check Git permissions and the endpoint. If the source provider is missing, check region, compartment, and IAM before recreating the connection. Never paste personal keys into variables to try to fix it.

### Creating a Stack via OCI CLI When Automation Is Needed

Once a configuration source provider exists, the same stack can be created via CLI. The PowerShell example below assumes OCI CLI is configured with authentication and appropriate permissions:

~~~powershell
$stackCompartmentOcid = "ocid1.compartment.oc1..REPLACE_STACK_COMPARTMENT"
$sourceProviderOcid = "ocid1.ormconfigsourceprovider.oc1..REPLACE_SOURCE_PROVIDER"
$targetCompartmentOcid = "ocid1.compartment.oc1..REPLACE_TARGET_COMPARTMENT"

$stackVariables = @{
    region           = "ap-singapore-1"
    compartment_ocid = $targetCompartmentOcid
    environment      = "dev"
    vcn_cidr         = "10.42.0.0/16"
    owner            = "platform-lab"
} | ConvertTo-Json -Compress

$variablesPath = Join-Path $env:TEMP "oci-iac-lab-variables.json"
[System.IO.File]::WriteAllText(
    $variablesPath,
    $stackVariables,
    [System.Text.UTF8Encoding]::new($false)
)

oci resource-manager stack create-from-git-provider `
    --compartment-id $stackCompartmentOcid `
    --config-source-configuration-source-provider-id $sourceProviderOcid `
    --config-source-repository-url "https://github.com/YOUR_ACCOUNT/oci-iac-lab.git" `
    --config-source-branch-name "main" `
    --config-source-working-directory "environments/dev" `
    --display-name "oci-iac-dev" `
    --variables ("file://" + $variablesPath)
~~~

Replace placeholders and region before running. The example omits `--terraform-version` to use the service default; in real pipelines, pick an approved runtime and pass this option explicitly. Inspect the created stack, save the returned OCID, and delete the temporary variables file when no longer needed.

Note that the working directory flag for this command is `--config-source-working-directory`. See [OCI CLI: create-from-git-provider](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/resource-manager/stack/create-from-git-provider.html).

## 8. Running Plan, Reviewing, and Applying

### 8.1. Plan Is the Change Control Gate

Open the stack, click **Plan**, give the job a name clearly linked to the Git change, and wait for results. A successfully created job does not mean Terraform has finished running.

With a new stack and sample configuration, the plan is expected to propose adding one `oci_core_vcn.lab` resource. Verify:

- Compartment and region match the target environment.
- CIDR falls within the planned network range.
- Name and tags match the responsible team.
- No unexpected destroy or resource replacement actions appear.
- Provider and runtime match the verified selections.

A `SUCCEEDED` plan state only means planning finished. It does not confirm that every change is approved by the team or that apply will definitely succeed.

### 8.2. Apply Referencing the Reviewed Plan

On the stack, click **Apply**, select the recently reviewed plan job under **Apply job plan resolution**, and run. The Console offers only the most recently created plan; if the plan changes, reviewers must inspect the exact plan to be applied.

Monitor until apply reaches `SUCCEEDED`, inspect outputs, and verify the VCN in the target compartment. If it fails, read the logs and identify what was already executed before retrying; failure does not guarantee no resources were created. Apply options are documented by Oracle in [Creating an Apply Job](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Tasks/create-job-apply.htm).

Equivalent CLI commands for creating jobs:

~~~powershell
$stackOcid = "ocid1.ormstack.oc1..REPLACE_STACK"

oci resource-manager job create-plan-job --stack-id $stackOcid
~~~

Save the plan job OCID from the output. Once the job finishes and the plan is reviewed:

~~~powershell
$planJobOcid = "ocid1.ormjob.oc1..REPLACE_REVIEWED_PLAN"

oci resource-manager job create-apply-job `
    --stack-id $stackOcid `
    --execution-plan-strategy $planJobOcid
~~~

The `--execution-plan-strategy` parameter in this shorthand form accepts the plan job OCID to reference a plan. Do not pass the string `FROM_PLAN_JOB_ID` while omitting the ID. See [create-apply-job CLI reference](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/resource-manager/job/create-apply-job.html).

### 8.3. Controlling Branch Changes Between Plan and Apply

Oracle notes that jobs use the latest commit for configurations stored in a source code management system. Therefore, **pointing a stack at `main` does not lock it to a fixed commit**. See [plan job code-fetching behavior](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Tasks/create-job-plan.htm).

Operational procedures should:

1. Record the intended deployment commit and stack source settings before running plan.
2. Restrict changes on the deployment branch during the review/apply window.
3. Keep stack variables, dependencies, and providers unchanged between both steps.
4. Select the reviewed plan instead of running an auto-approved apply.
5. If code, variables, or dependencies change, generate a new plan and review again.

Referencing a saved plan specifies the exact plan chosen; it does not turn a Git branch into an immutable identifier or automatically freeze dependencies outside Git. If evidence is required, check the actual configuration attached to the job and source metadata provided by the service; do not simply read current HEAD and retroactively attribute it to a previously executed job.

## 9. Delivering a Change Through Git and Verifying Repeatability

After the first apply, try updating the owner tag in `main.tf` by changing:

~~~hcl
Owner = format("%s-team", var.owner)
~~~

Perform this on a working branch:

~~~powershell
git switch -c change/lab-owner-tag
terraform fmt -recursive
terraform -chdir=environments/dev validate
git add environments/dev/main.tf
git diff --cached
git commit -m "Clarify owner tag for OCI lab VCN"
git push -u origin change/lab-owner-tag
~~~

Create a pull request, review, and merge into `main`. After merging, explicitly run a new plan on the stack. The expected change is updating the VCN's tags; if the plan proposes creating an extra VCN or replacing the VCN, stop to inspect state, resource addresses, and source configuration.

After apply succeeds, run another plan with no changes to code, variables, or out-of-band resources. Expect zero remaining changes. If a diff still appears, check for drift, service-normalized attributes, or uncontrolled inputs.

`git revert` creates another configuration version; it **does not automatically roll back infrastructure**. Applying reverted code still requires plan and apply. For Compute with data, volumes, or Oracle databases, rolling back code must also consider compatibility, backups, and outage impact.

## 10. Managing Multiple Environments, Secrets, and Operational Evidence

### 10.1. Separating State by Environment and Responsibility

| Item | Dev | Production |
| --- | --- | --- |
| Root module | `environments/dev` | `environments/prod` |
| Stack/state | Separate dev stack | Separate production stack |
| Target compartment | Lab or dev | Production compartment |
| Git changes | Reviewed per team workflow | Stricter review and merge permissions |
| Apply | Assigned dev operator | Separately authorized deployment identity |

This is a recommended design, not an automatic environment inference from branch names. Setting `environment = "prod"` only alters how code uses the variable; it does not automatically move resources into the production compartment.

A new stack created from the same repository gets its own state. Never use creating a new stack as a fix for a stack already managing live resources; if ownership must be transferred, follow an appropriate state migration/import workflow.

### 10.2. Keeping Secrets Out of Code and Controlling State

A PAT for reading Git and OCI credentials for the CLI caller are two distinct secrets. Revoking one does not automatically revoke the other. Assign owners, track expiration dates, and re-test connections after rotating the PAT.

Do not treat stack variables as a secret vault. In this lesson, they hold only region, compartment, and non-secret configuration strings. When expanding to Databases, use an organization-approved secret management mechanism while evaluating which data Terraform persists in state.

Job read permissions must also be restricted: per [Resource Manager policy reference](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/resourcemanagerpolicyreference.htm), the `read orm-jobs` permission set covers downloading job logs, configuration, plans, and state. Never share those downloads as public documents.

### 10.3. Linking Code Changes to Resources and Cost

For every deployment, record in the team's change tracking system:

- Pull request and commit intended for deployment.
- Repository, branch, working directory, and stack OCID.
- Reviewed plan job OCID, apply job OCID, and outcome.
- Region, target compartment, Terraform/provider versions.
- Executor, reviewer, and notable resource changes.

Job logs assist diagnostics; Git history explains intent behind changes; OCI Audit traces API operations. They complement rather than replace one another.

When reusing this workflow for Compute, storage, and databases, review shapes, counts, capacity, and redundancy designs too. A plan describes infrastructure actions, not a complete cost quote or proof of high availability. A commit adding replicas or increasing capacity incurs cost even when the pipeline succeeds cleanly.

## 11. Troubleshooting Layer by Layer

| Symptom | What to Check | Resolution Approach |
| --- | --- | --- |
| Validate connection fails | Endpoint, PAT, token expiry, SSO | Fix the connection, reissue token per procedure, and re-validate |
| Connection valid but repository not visible | Account/token scope, owning organization | Grant access to the specific repository; distinguish server URL from repo URL |
| Source provider or stack not found | Region, compartment, IAM permissions | Re-select the right scope and verify required permissions |
| Terraform configuration not found | Branch and working directory | Verify the chosen directory contains `.tf`; use a relative path |
| Internal Git times out or fails TLS | DNS, private endpoint, routes, network rules, certificates | Check service connectivity path; keep TLS verification enabled |
| Root repo clones fine but module fails to load | Module URL/ref and access to module repo | Inspect each dependency source; never embed credentials in URLs |
| Plan/apply reports NotAuthorizedOrNotFound | Target resource permissions, OCID, region | Check both permissions and resource existence/location |
| Apply fails after partial creation | Logs, existing resources, state | Identify the failing step, fix root cause, and re-plan on the same stack |
| New code missing from plan | Not pushed/merged, wrong branch, or wrong stack | Compare actual source and job configuration |
| Unexpected provider version | Version constraints, lock, and upgrade option | Review version in logs; upgrade via controlled change |

For modules in private Git repositories on a public Git server, Oracle describes loading modules without credentials in the source URL when the configuration source provider has access to that repository. Do not generalize this to assume every SSH model or every private Git server works identically. See [Modules from Private Git Repositories](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Tasks/create-stack-git.htm#).

Avoid fixing errors by granting `manage all-resources in tenancy`, deleting state, or spinning up duplicate stacks to retry. Those actions obscure root causes and can leave unmanaged resources behind.

## 12. Completion Criteria and Lab Cleanup

A complete practice run shows all of the following:

- Repository holds code, sample variable file, and lock file; no tokens, personal keys, state, or saved plans.
- Configuration source provider connects successfully and stack reads the right branch/directory.
- First plan was reviewed; apply referenced that plan and succeeded.
- Output OCID matches the live VCN in the target compartment/region.
- Tag change went through Git, was planned/applied, and is traceable to the job.
- Final plan shows zero changes when code, variables, and infrastructure stay unchanged.

At the end of the lab, use the **Destroy** workflow on that same lab stack after verifying resource scope and dependencies. Execute only when the VCN is not used by other workloads. Monitor the job, confirm resources were cleaned up, and only then consider deleting the stack and any unshared source provider.

Deleting the repository or configuration source provider does not destroy infrastructure. Deleting the stack must also not be used in place of confirming resource cleanup. Retain sufficient deployment history and evidence until operational wrap-up is complete.

After this lesson, any OCI infrastructure change should be identifiable by **code version, stack configuration, and job outcome** together. As scope expands to Compute, storage, and Databases, keep that same discipline while adding corresponding authorization, monitoring, cost controls, and service continuity plans.
