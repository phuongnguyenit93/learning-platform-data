# Managing gcloud Configurations by Account and Environment

## Learning Objectives

After this lesson, learners will be able to:

1. Explain what a **gcloud configuration** is, what settings it stores, and how it differs from login credentials, IAM, a Google Cloud project, and Application Default Credentials (ADC).
2. Create, name, inspect, activate, and delete configurations for working across multiple **accounts** and **development, staging, production** environments.
3. Proactively select a configuration per command, terminal session, or working context; understand the precedence order among command flags, environment variables, and configuration values.
4. Detect and prevent operating on the wrong project, wrong account, or wrong GKE cluster before deploying Compute Engine, Cloud Run, GKE, and data resources.
5. Establish safe `gcloud` usage rules for personal development and automation workflows.

## 1. Why Are Multiple gcloud Configurations Needed?

In Google Cloud, an engineer may simultaneously work with:

- **Development**: testing APIs, creating Cloud Run services, and validating changes.
- **Staging**: running integration tests with a configuration closely resembling production.
- **Production**: operating live systems, critical data, and restricted access permissions.
- **Multiple identities**: a personal account for development, a corporate account for operations, and a delegated service account for certain tasks.

If you only use one project and one account, the default Google Cloud CLI configuration is usually enough. When working across multiple environments, repeatedly changing the project manually increases the risk of running a command against the wrong environment. **Named configurations** help group default values under a meaningful name, then select the right group when working.

For example, the same command to view virtual machines can list VMs in development or production depending on the **effective project and account**. Creating two separate configurations makes it easy to verify context before operating.

This capability is part of the **CLOUD_PROVIDERS_GCP** module: learners will go on to use projects, IAM, VPC, Compute Engine, GKE, Cloud Run, storage, databases, CI/CD, operational observability, and cost optimization. Managing command context properly is a preparatory step before touching those resources.

## 2. Conceptual Model: Configuration, Account, Project, and Credentials

A **gcloud configuration** is a **named collection of properties** used to control the default behavior of the Google Cloud CLI. Each property consists of a grouped name and a value; for example:

| Property | Role | Illustrative Value |
|---|---|---|
| **core/account** | Identity that gcloud selects by default | dev@example.com |
| **core/project** | Default Project ID for commands that support a project | shop-dev-123 |
| **compute/region** | Default region for applicable Compute commands | asia-southeast1 |
| **compute/zone** | Default zone for applicable Compute commands | asia-southeast1-b |
| **core/disable_prompts** | Whether to ask for interactive confirmation | false |
| **auth/impersonate_service_account** | Service account to impersonate in supported commands | deployer@shop-prod-123.iam.gserviceaccount.com |

All values, IDs, and emails in this lesson are **examples**. When applying in practice, replace them with existing, authorized accounts, projects, and regions.

### 2.1. A Configuration Name Does Not Create Google Cloud Resources

For instance, creating a **shop-prod** configuration locally does not create the **shop-prod-123** project in Google Cloud. The configuration only stores a reference value pointing to that project. Likewise, setting **core/account** does not sign the user in and does not grant IAM permissions to the account.

A successful API call simultaneously requires:

1. **Right target**: the project, region, zone, and resource to operate on.
2. **Right identity**: an authenticated gcloud account or an identity used through another mechanism.
3. **Actual permissions**: IAM, organization policies, and access conditions must permit the action.

### 2.2. Configurations Differ from the Credential Store

When you run **gcloud auth login**, the Google Cloud CLI stores credentials in the local user configuration area. Multiple named configurations can **reference logged-in accounts** through the **core/account** property. They do not create independent login sessions on their own and do not replace IAM.

For example, if the same engineer has permissions on two projects, two configurations can use the **same account** with **different projects**. Conversely, two configurations can point to two different accounts that both have permissions on a single project.

~~~mermaid
flowchart TD
    A["Named configuration: shop-dev"] --> B["core/account: dev@example.com"]
    A --> C["core/project: shop-dev-123"]
    A --> D["compute/region: asia-southeast1"]
    B --> E["gcloud credential store"]
    E --> F["Google Cloud API and IAM check"]
    C --> F
    D --> F
    G["Java Application / Client Libraries"] --> H["Application Default Credentials (ADC)"]
    H --> F
~~~

**ADC (Application Default Credentials)** is the mechanism many Google Cloud Client Libraries—such as Java libraries accessing Cloud Storage or BigQuery—use to locate an identity. ADC's resolution path can differ from the identity used by `gcloud` commands. This distinction is critical when the terminal can run a command successfully yet a Java program reports an authentication error.

## 3. Designing a Configuration Set by Account and Environment

Suppose an e-commerce project has three environments. A consistent naming scheme:

| Local Configuration Name | Intended Account | Project ID | Purpose |
|---|---|---|---|
| **shop-dev** | dev@example.com | shop-dev-123 | Coding and testing |
| **shop-staging** | dev@example.com | shop-staging-123 | Integration testing |
| **shop-prod** | ops@example.com | shop-prod-123 | Production observation and operations |

These are **team-chosen environment names**, not built-in configuration types in Google Cloud. Project IDs must be verified from the real system. Production should have least-privilege IAM permissions, change approval workflows, and clear context identification.

### Naming Guidelines

- Use lowercase letters, numbers, and hyphens per configuration naming syntax; choose descriptive names such as **shop-dev**, **shop-prod**.
- Include the **product/service** and **environment** in the name when managing multiple systems.
- Do not name configurations after secrets, passwords, or tokens.
- Do not assume a configuration name determines access level. Actual permissions are still governed by IAM and policies.
- When an individual manages projects across multiple organizations, you can include an org or team code in the name to avoid confusion.

## 4. Basic Operations with Named Configurations

The examples below use an installed **Google Cloud CLI (gcloud)**. Commands can be run in a standard terminal, Cloud Shell, or development machine. Before running examples that access resources, replace illustrative IDs and emails with real values.

### Step 1 — Check the CLI and Existing Configurations

~~~bash
# Check installed CLI
gcloud version

# Existing configurations and active configuration
gcloud config configurations list

# View effective properties of the active configuration
gcloud config list

# View accounts authenticated on the machine
gcloud auth list

# View details of the default configuration if it exists
gcloud config configurations describe default
~~~

The **gcloud init** command is suitable for initial setup: the wizard guides you through selecting or creating a configuration, signing in, and choosing a project. Once you already have multiple configurations, be cautious with **re-initialize** operations because they may overwrite existing properties.

In the output of **gcloud config configurations list**, the **IS_ACTIVE** column shows the current default configuration. The output of **gcloud auth list** shows authenticated accounts; cross-check both when you suspect the wrong account is active.

### Step 2 — Sign In to the Needed Accounts

~~~bash
# Run once and select dev@example.com in the browser
gcloud auth login

# Run again if you also need ops@example.com
gcloud auth login

# Check the accounts actually signed in
gcloud auth list
~~~

The two emails above are illustrative. The sign-in flow depends on your organization's SSO/MFA setup. The login command may change the account marked active in the current configuration; therefore, **check and set core/account explicitly** after this step.

**Do not share your personal credentials directory**, do not push tokens or auth files to Git, and do not use interactive user logins to run long-lived automated jobs.

### Step 3 — Create Three Configurations Without Activating Them

~~~bash
gcloud config configurations create shop-dev --no-activate
gcloud config configurations create shop-staging --no-activate
gcloud config configurations create shop-prod --no-activate

gcloud config configurations list
~~~

In current gcloud CLI versions, **create** may activate the new configuration by default; the **--no-activate** flag keeps the current context unchanged. If a configuration name already exists, use **describe** to inspect it first to avoid unintended overwrites.

### Step 4 — Assign Account, Project, and Region per Configuration

The global **--configuration** flag lets you edit a named configuration without activating it for all commands.

~~~bash
# Development
gcloud config set core/account dev@example.com --configuration=shop-dev
gcloud config set core/project shop-dev-123 --configuration=shop-dev
gcloud config set compute/region asia-southeast1 --configuration=shop-dev
gcloud config set compute/zone asia-southeast1-b --configuration=shop-dev

# Staging
gcloud config set core/account dev@example.com --configuration=shop-staging
gcloud config set core/project shop-staging-123 --configuration=shop-staging
gcloud config set compute/region asia-southeast1 --configuration=shop-staging
gcloud config set compute/zone asia-southeast1-b --configuration=shop-staging

# Production
gcloud config set core/account ops@example.com --configuration=shop-prod
gcloud config set core/project shop-prod-123 --configuration=shop-prod
gcloud config set compute/region asia-southeast1 --configuration=shop-prod
gcloud config set compute/zone asia-southeast1-b --configuration=shop-prod
~~~

**core/account** must point to an authenticated account with appropriate permissions. If you have not signed in to **ops@example.com**, merely setting the property will not make that account usable. **compute/region** and **compute/zone** support applicable Compute commands; some other services like Cloud Run require an explicit **--region** or have service-specific properties.

### Step 5 — Read Back Each Configuration

~~~bash
gcloud config configurations describe shop-dev
gcloud config configurations describe shop-staging
gcloud config configurations describe shop-prod

# Read the effective project value in a specific configuration
gcloud config get-value core/project --configuration=shop-dev

# View all configurations and active status
gcloud config configurations list
~~~

**Verify before using production**: check whether the account, project ID, and deployment region are right; whether any environment variables are overriding them; and whether the identity has permissions for the intended purpose.

### Step 6 — Activate a Configuration and Run Commands

~~~bash
# Switch default context to development
gcloud config configurations activate shop-dev

gcloud config list
gcloud config get-value core/account
gcloud config get-value core/project

# Inspect project info only (requires appropriate permission)
gcloud projects describe shop-dev-123

# Run a single command against production without switching the active default
gcloud projects describe shop-prod-123 --configuration=shop-prod
~~~

When you **activate**, you change the default configuration in the active gcloud config area. When you use **--configuration=shop-prod**, only that command invocation selects the production configuration. The two approaches serve two different needs: switching a working session or making a single context-explicit call.

## 5. Three Ways to Select a Configuration and Their Scope of Impact

| Mechanism | Usage | Scope | When It Fits |
|---|---|---|---|
| **activate** | gcloud config configurations activate shop-dev | Changes the active configuration in the local gcloud config set | Working for a relatively long period in one environment |
| **--configuration** | gcloud projects list --configuration=shop-prod | One command only | Scripts or operations that must declare the environment explicitly |
| **CLOUDSDK_ACTIVE_CONFIG_NAME** | Set environment variable before running gcloud | Terminal process and child processes inheriting the variable | Each terminal window or project directory uses its own environment |

### 5.1. Selecting a Configuration for a Single Command

~~~bash
gcloud compute instances list --configuration=shop-dev
gcloud compute instances list --configuration=shop-prod

# For services requiring a region, specify the location explicitly as well
gcloud run services list --region=asia-southeast1 --configuration=shop-staging
~~~

This approach is easy to verify during script review: the command explicitly states the environment. For production resources, proper IAM access controls and change approval procedures are still required.

### 5.2. Selecting a Configuration in a Linux/macOS Terminal

~~~bash
# Affects only the current terminal and child processes
export CLOUDSDK_ACTIVE_CONFIG_NAME=shop-staging
gcloud config list
gcloud projects describe shop-staging-123

# Unset in the terminal
unset CLOUDSDK_ACTIVE_CONFIG_NAME
~~~

### 5.3. Selecting a Configuration in Windows PowerShell

~~~powershell
# Select configuration for the current PowerShell session only
$env:CLOUDSDK_ACTIVE_CONFIG_NAME = "shop-dev"
gcloud config list
gcloud projects describe shop-dev-123

# Remove the environment variable in the current session
Remove-Item Env:CLOUDSDK_ACTIVE_CONFIG_NAME
~~~

**Note about multiple terminals:** **activate** changes the active configuration value in the shared gcloud config area, so other terminal windows can be affected if they share that config area and have no override set. Per-terminal environment variables or the **--configuration** flag help isolate each context.

## 6. Precedence Order: Command Flags, Environment Variables, Saved Configuration

Several gcloud commands allow overriding configuration properties. For example, for **project**:

1. **Command flags** such as **--project** have the highest precedence for that execution.
2. **Environment variables** such as **CLOUDSDK_CORE_PROJECT** can override the value saved in the configuration.
3. **The core/project property** in the selected named configuration is the default value when not overridden.

~~~bash
# Example: the property saved in shop-dev is shop-dev-123
gcloud config configurations describe shop-dev

# Override project for this command only
gcloud compute instances list --configuration=shop-dev --project=shop-staging-123
~~~

The command above **still selects configuration shop-dev**, but **--project** directs the VM listing to **shop-staging-123**. This shows that **the configuration name does not guarantee the target execution project** when an override is present.

Terminal examples:

~~~bash
# Linux/macOS
export CLOUDSDK_ACTIVE_CONFIG_NAME=shop-dev
export CLOUDSDK_CORE_PROJECT=shop-staging-123

# Effective core/project value can be shop-staging-123
gcloud config get-value core/project

# Remove override to return to the value saved in the configuration
unset CLOUDSDK_CORE_PROJECT
~~~

~~~powershell
# Windows PowerShell
$env:CLOUDSDK_ACTIVE_CONFIG_NAME = "shop-dev"
$env:CLOUDSDK_CORE_PROJECT = "shop-staging-123"

gcloud config get-value core/project

Remove-Item Env:CLOUDSDK_CORE_PROJECT
~~~

Environment variables corresponding to properties typically take the form **CLOUDSDK_SECTION_PROPERTY**. For example: **CLOUDSDK_CORE_PROJECT**, **CLOUDSDK_CORE_ACCOUNT**, **CLOUDSDK_COMPUTE_ZONE**. Always check both terminal environment variables and saved configurations before concluding where a command will take effect.

**Do not confuse three different variables/flags:**

- **CLOUDSDK_ACTIVE_CONFIG_NAME** selects the **configuration name** for the session.
- **CLOUDSDK_CORE_PROJECT** overrides the **project** of the effective configuration.
- **CLOUDSDK_CONFIG** selects the **directory containing all local gcloud state**, including configurations and auth data; it is not the name of a named configuration.

Changing **CLOUDSDK_CONFIG** may cause the CLI not to find configuration names or credentials set up in the old directory. This value must point to a suitable writable directory. Changing the config directory should be deliberate, especially on shared machines or in CI environments.

## 7. Separating gcloud CLI Authentication and ADC for Applications

### 7.1. Accessing APIs via `gcloud` Commands

With the Google Cloud CLI, verify the account selected by the configuration:

~~~bash
gcloud auth list
gcloud config get-value core/account --configuration=shop-dev
gcloud config get-value core/account --configuration=shop-prod
~~~

**gcloud auth login** adds or refreshes credentials for gcloud. **gcloud config set core/account** only specifies which account gcloud intends to use; it does not create an identity or grant IAM.

### 7.2. Accessing APIs from Java Libraries and Other Client Libraries

Java applications using Google Cloud Client Libraries commonly use **Application Default Credentials (ADC)**. In a personal development environment, one setup method is:

~~~bash
# Log in ADC for locally running applications
gcloud auth application-default login

# When needed, set a quota project for ADC using an appropriately authorized project
gcloud auth application-default set-quota-project shop-dev-123
~~~

ADC information is managed separately from `gcloud` command credentials. **Activating shop-prod** does not mean a locally running Java application automatically switches to production. If the **GOOGLE_APPLICATION_CREDENTIALS** variable is used, ADC can load credentials from the specified file path; that path may contain federation settings or another supported credential type. Do not put sensitive files or service account keys into source repositories.

Common scenarios:

| Symptom | Cause to Check |
|---|---|
| gcloud reads Cloud Storage successfully, Java app reports missing credentials | The app uses ADC, which has not been configured in the runtime environment |
| gcloud currently selects dev project, Java library accesses data in another project | The project passed by the app to the SDK and ADC can be independent of the gcloud configuration |
| Works on dev machine, CI reports authentication error | CI needs its own workload identity mechanism; no personal login session exists |

On Google Cloud, workloads should use a **service account attached to the running resource** when appropriate; for CI/CD outside Google Cloud, prefer **Workload Identity Federation** or an organization-approved short-lived identity approach. Avoid creating long-lived service account keys.

### 7.3. Impersonation: Using a Delegated Identity

In some tasks, operators need to call APIs using a deployment service account with restricted permissions. Google Cloud CLI supports the **--impersonate-service-account** flag when the calling account has been granted corresponding impersonation permission.

~~~bash
# Use only when the current account has been granted impersonation permission
gcloud run services list --region=asia-southeast1 \
  --configuration=shop-prod \
  --impersonate-service-account=deployer@shop-prod-123.iam.gserviceaccount.com
~~~

The example uses **Bash** line continuation. In PowerShell, write it on one line or use PowerShell line-continuation syntax. Impersonation **does not bypass IAM**: the source account needs permission to mint tokens for the service account, and the target service account needs permissions on the resources being operated on.

If used frequently, you can configure **auth/impersonate_service_account** specifically for a named configuration:

~~~bash
gcloud config set auth/impersonate_service_account \
  deployer@shop-prod-123.iam.gserviceaccount.com \
  --configuration=shop-prod

# Unset the property when no longer needed
gcloud config unset auth/impersonate_service_account --configuration=shop-prod
~~~

The impersonation setting is also a property subject to overrides; inspect it when analyzing the **effective identity** of a command.

## 8. Safe Practices Before Deploying or Modifying Production

### 8.1. Context Checklist Before Impactful Commands

Before operations such as deploying Cloud Run, modifying VMs, changing IAM, running database migrations, or deleting a Cloud Storage bucket:

1. **Confirm configuration name** via the list or by using **--configuration** explicitly.
2. **Confirm project**: inspect **core/project**, environment variables, and the command's **--project** flag.
3. **Confirm identity**: **core/account**, credential list, and any impersonation flag/property.
4. **Confirm location and resource**: ensure the region/zone/cluster/service/bucket actually exists in the target environment.
5. **Check beforehand with read commands** and change documentation; only execute changes with proper permissions and approvals.
6. **Prepare recovery capability** for risky changes: for example, Cloud Run revision rollback, restore testing, or snapshots per policy.

Example **read-only verification** workflow before a Cloud Run release:

~~~bash
gcloud config configurations describe shop-prod
gcloud auth list

# Use explicit project and region
gcloud run services list \
  --configuration=shop-prod \
  --project=shop-prod-123 \
  --region=asia-southeast1
~~~

Writing the project explicitly in the command helps reviewers see the intended target. Still, the operator must verify identity and other overrides; **--project** alone does not prevent someone from choosing the wrong project ID.

### 8.2. For GKE, `kubectl` Has Its Own Context

Take special note: **kubectl** reads **kubeconfig** with its own **current-context**. Switching from **shop-dev** to **shop-prod** in gcloud does not mean `kubectl` automatically selects the corresponding production cluster.

~~~bash
# Identify the cluster kubectl is currently targeting
kubectl config current-context
kubectl config get-contexts

# Run the command below only when you want to update kubeconfig for the target cluster
# and have verified project, region, and access permissions
gcloud container clusters get-credentials shop-cluster \
  --project=shop-staging-123 \
  --location=asia-southeast1 \
  --configuration=shop-staging

# Re-verify after get-credentials
kubectl config current-context
~~~

The **get-credentials** command updates kubeconfig and can set a new `current-context` for `kubectl`. Always inspect **kubectl config current-context** before any operation that modifies Kubernetes namespaces, deployments, or secrets.

### 8.3. For Terraform and Pipelines, Pass the Project Explicitly

Do not assume **gcloud config configurations activate** controls the project used by Terraform, Docker, Java apps, `kubectl`, or every other tool. Each tool has its own configuration/credentials mechanism.

In automation, you should:

- Pass **project, environment, and region** explicitly via pipeline variables or reviewed infrastructure configs.
- Use a **least-privilege service account** and short-lived identity mechanisms; avoid relying on personal login sessions on build machines.
- Separate deployment details for dev/staging/prod, with appropriate review and approval steps for production.
- Record **execution target, artifact version, test results, and deployment history**; do not log access tokens.
- Check for gcloud **overrides** if the pipeline invokes gcloud.

## 9. Lifecycle Management and Configuration Cleanup

### 9.1. Updating or Unsetting a Property

~~~bash
# Change the default project of a configuration
gcloud config set core/project shop-dev-123 --configuration=shop-dev

# Remove default zone if the workflow does not use Compute Engine zonally
gcloud config unset compute/zone --configuration=shop-dev

# Re-verify after making changes
gcloud config configurations describe shop-dev
~~~

**unset** removes a property; subsequent runs may require passing the corresponding flag or falling back to another CLI default.

### 9.2. Deleting an Unused Named Configuration

~~~bash
# Switch to another configuration first if shop-staging is active
gcloud config configurations activate shop-dev

# Inspect the configuration intended for deletion
gcloud config configurations describe shop-staging

# Delete once confirmed no longer in use
gcloud config configurations delete shop-staging

gcloud config configurations list
~~~

You cannot delete the **currently active** configuration using `delete`. Deleting a configuration name **does not revoke IAM** and **does not automatically delete saved credentials** for the account; those are separate administrative actions.

If a personal account is no longer permitted for use, coordinate with your organization to revoke access in IAM/IdP. Cleaning up local credentials can use the appropriate **gcloud auth revoke** command after checking whether other configurations still need that account.

### 9.3. Where gcloud Configurations Are Stored

Typically, the Google Cloud CLI stores user configuration at:

| Operating System | Common Path |
|---|---|
| Linux/macOS | ~/.config/gcloud |
| Windows | %APPDATA%\\gcloud |

The exact path may vary due to installation, **CLOUDSDK_CONFIG**, or runtime environment. Check with:

~~~bash
gcloud info --format="value(config.paths.global_config_dir)"
gcloud info --format="value(config.paths.active_config_path)"
~~~

This directory can contain credentials, so do not copy it indiscriminately to other machines and do not commit it to repositories. In **Cloud Shell**, depending on session context, gcloud settings in a tab's temporary area may not persist across sessions; verify the actual storage location rather than assuming.

## 10. Common Errors and How to Diagnose Them

| Symptom | Possible Cause | Check / Resolution |
|---|---|---|
| Command sees VMs from another project | **--project** or **CLOUDSDK_CORE_PROJECT** override | Check full command, environment variables, and **core/project** |
| Wrong account despite running **activate shop-prod** | **core/account** unset, override active, or another account logged in recently | **gcloud auth list**, **gcloud config configurations describe shop-prod** |
| **PERMISSION_DENIED / 403** error | Effective account lacks IAM or is blocked by policy | Check principal, project, per-action permissions, impersonation |
| Created configuration not found | Different **CLOUDSDK_CONFIG** in use | Check paths with **gcloud info** and environment variables |
| **gcloud config list** differs from saved file values | Environment variable or command flag override | Compare **describe** against terminal overrides |
| Java program reports ADC error while gcloud works | gcloud credentials and ADC are two separate systems | Inspect the application's ADC mechanism and identity |
| kubectl operates on wrong cluster | kubeconfig's current-context differs from expectation | **kubectl config current-context**, select intended context deliberately |
| GKE/Compute command asks for zone or region | Location not configured or workload is in another location | Identify resource location and pass **--location**, **--zone**, or **--region** |
| Configuration deleted yet account still has access | Deleting a configuration does not revoke credentials or IAM | Check **gcloud auth list**, revoke local credentials and actual permissions if required |

When troubleshooting, start with the question: **"Under which identity is the command running, which project is it targeting, and from which source is it getting that value?"** The answer usually explains most configuration errors.

## 11. Scenario Exercise

A company builds a Java/Spring API running on **Cloud Run**, stores data in **Cloud SQL**, images in **Cloud Storage**, and plans to add GKE for another group of services. The team has two user accounts and three Google Cloud projects: **catalog-dev-001**, **catalog-stg-001**, **catalog-prod-001**.

### Practice Tasks

1. Propose a naming scheme for **three configurations** so the environment is immediately recognizable in commands.
2. Write the commands to create the configurations in an **inactive** state and set **core/project**, **core/account**, and **compute/region** for each environment.
3. Write two ways to list Cloud Run services in staging **without changing the default configuration**: one using **--configuration**, and one using a terminal environment variable.
4. Explain why an account already logged into gcloud can still cause a Java application using the Cloud Storage Client Library to fail authentication.
5. State why switching configuration from dev to prod is not sufficient to ensure **kubectl** points to the production cluster.
6. Propose safety verification steps before modifying a Cloud SQL instance configuration in production.

### Guided Answers

- You can use **catalog-dev**, **catalog-stg**, **catalog-prod** and the corresponding project IDs; the accounts must have credentials and appropriate IAM permissions.
- Use **gcloud config configurations create NAME --no-activate**; run **gcloud config set ... --configuration=NAME** commands to configure each without changing the active context.
- Example viewing staging:

~~~bash
gcloud run services list \
  --configuration=catalog-stg \
  --project=catalog-stg-001 \
  --region=asia-southeast1
~~~

- If configuring the terminal session, set **CLOUDSDK_ACTIVE_CONFIG_NAME=catalog-stg** using the OS-appropriate syntax and run the command; unset the variable when done.
- Client Libraries typically use **ADC**, not depending directly on the active configuration.
- `kubectl` maintains its own **current-context** in kubeconfig.
- Before modifying a live database, verify **project/region/instance/account/IAM**, backup and restore plan, downtime impact, deployment window, and approval authorization.

## 12. Takeaways and References

**Five things to remember:**

1. A named configuration is a **local property group**, not a project or an IAM granting mechanism.
2. **core/account** selects the default gcloud identity; credentials must exist and be authorized. **ADC** serves applications with a separate lifecycle.
3. Use **--configuration** for one command, **CLOUDSDK_ACTIVE_CONFIG_NAME** for a terminal, or **activate** to change gcloud's default configuration.
4. **--project**, **CLOUDSDK_CORE_PROJECT**, and other overrides can make a command target something different from the project stored in the configuration.
5. Before any change in production, verify **context, identity, project, region/zone, resource, and recovery capability**.

**Official Google Cloud Documentation:**

1. [Managing gcloud CLI configurations](https://docs.cloud.google.com/sdk/docs/configurations) — creating, selecting, viewing, and deleting named configurations.
2. [Managing gcloud CLI properties](https://docs.cloud.google.com/sdk/docs/properties) — properties and overriding environment variables.
3. [gcloud config configurations create — CLI reference](https://docs.cloud.google.com/sdk/gcloud/reference/config/configurations/create) — syntax and **--no-activate** flag.
4. [Authenticate for the gcloud CLI](https://docs.cloud.google.com/sdk/docs/authenticate) — user, workload, and service account impersonation authentication.
5. [How Application Default Credentials works](https://docs.cloud.google.com/docs/authentication/application-default-credentials) — Client Libraries credential sources.
6. [Install kubectl and configure cluster access](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/cluster-access-for-kubectl) — configuring **kubeconfig** and **current-context** when using GKE.
