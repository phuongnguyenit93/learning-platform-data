# Installing and Configuring the Google Cloud CLI

> **Chapter:** GCP Tools and Development Environment  
> **Module:** CLOUD_PROVIDERS_GCP

The **Google Cloud CLI** is a command-line toolset for working with Google Cloud resources and services. Instead of operating solely through the Google Cloud Console, engineers can use commands to inspect projects, IAM, VPC, Compute Engine, GKE, Cloud Run, storage, and databases; and combine these commands in scripts and deployment workflows. It is a foundational tool for service selection, resource protection, release automation, and monitoring reliability and cost.

This lesson guides you through installing and configuring the CLI on a personal machine, selecting the right account/project/resource region, distinguishing CLI login from application credentials, and building the habit of verifying the environment before running commands that affect the system.

**Learning Outcomes:** After this lesson, learners will be able to:

1. Install the Google Cloud CLI on Windows, macOS, or Linux and verify the installation.
2. Run `gcloud init`, sign in, and set default project/region/zone.
3. Manage multiple configurations for environments such as development and production.
4. Distinguish `gcloud` command authentication, Application Default Credentials (ADC), and workload identity.
5. Use resource-reading commands, look up help, and troubleshoot common configuration errors.
6. Update the CLI and manage components appropriately according to the installation method.

## 1. What Does the Google Cloud CLI Include?

The primary command is `gcloud`. It is part of the Google Cloud CLI, providing command groups organized by resource or service.

| Tool | Role | Example |
| --- | --- | --- |
| `gcloud` | Configure the environment and manage GCP resources | `gcloud projects list`, `gcloud run services list` |
| `gcloud storage` | Work with Cloud Storage | `gcloud storage buckets list` |
| `bq` | Command-line tool for BigQuery | `bq ls` |
| `gsutil` | Legacy Cloud Storage tool | `gsutil ls`; for new operations refer to `gcloud storage` |
| `kubectl` | Interact with the Kubernetes API after configuring cluster connection | `kubectl get pods` |

`kubectl` may need to be installed separately; installing the Google Cloud CLI via a Linux package manager does not guarantee all extension components are included. The CLI tool is a *client*: each command sends a request to the corresponding API. Having the CLI installed **does not mean** the account has permissions on every resource, that APIs are enabled, or that billing is enabled.

### 1.1. How Is a `gcloud` Command Structured?

~~~text
gcloud <group> <resource> <action> [argument] [--flag=value]
       └──────────────┬──────────────┘
               full command name
~~~

Examples:

~~~bash
# List VMs in the selected project
gcloud compute instances list

# Explicitly specify a project for this command only
gcloud compute instances list --project=PROJECT_ID

# Look up options and examples
gcloud compute instances list --help
~~~

Common flags:

- `--project=PROJECT_ID`: specifies the project for a single command invocation.
- `--region=REGION` and `--zone=ZONE`: selects the deployment region/zone when supported by the command group.
- `--format=...`: selects the output data structure, such as `table(...)`, `value(...)`, `json`.
- `--filter=...`: filters the resource list.
- `--configuration=NAME`: uses a named configuration for the current command.
- `--help`: opens syntax documentation right in the terminal.

Not all commands accept the same set of service flags. Check the help of the specific command before automating.

## 2. Preparation Before Installation

You need:

- **Computer and terminal:** PowerShell or Command Prompt on Windows; Terminal/zsh on macOS; Bash or an equivalent shell on Linux.
- **Internet connection:** to download installer packages and call Google Cloud APIs; corporate proxies or firewalls may require separate configuration.
- **Appropriate account:** a Google Account or organization-managed identity granted IAM permissions for the resources to operate on.
- **Project ID:** illustrative example `demo-gcp-dev`; **Project ID** is used in most commands, distinct from display name and project number.
- **Billing if the lab uses billable resources:** some read operations and CLI configurations do not require creating resources; when deploying Compute Engine, Cloud SQL, or other services, check API enablement conditions, billing, and costs.

Just to install and check `gcloud --version`, you do not yet need a project. To work with an existing project, appropriate IAM permissions are required. Do not create projects or enable billable services in a shared environment if the lab does not ask for it.

### 2.1. Local Machine or Cloud Shell?

| Environment | When to Choose? | Key Points to Remember |
| --- | --- | --- |
| **Local install** | Developing on a personal machine alongside an IDE, scripts, and source control | Manage versions, executable paths, configurations, and local credentials yourself |
| **Google Cloud Shell** | Quick practice in a Google-provided terminal environment | CLI is usually preinstalled; authentication is integrated with the Cloud Shell session; some tab-level CLI config choices do not persist long-term |
| **CI/CD runner** | Automated execution during build/deploy | Requires workload authentication and explicit project configuration; do not copy user login credentials |

The material below focuses on a **local machine**. With Cloud Shell, you can skip installation and start by checking `gcloud config list`.

## 3. Installing on Windows

1. Open the official [Install the Google Cloud CLI](https://docs.cloud.google.com/sdk/docs/install-sdk) page, select the **Windows** section, and download the installer from Google.
2. Run the installer, confirm the publisher **Google LLC**, and follow the prompts. The installation usually bundles the required Python; use the bundled Python if you have no need for a custom Python setup.
3. Allow adding the CLI to `PATH` and enabling tools in the terminal if the installer offers those options.
4. Open a **new PowerShell window** after completion.

Verify in PowerShell:

~~~powershell
# Locate the command in PATH
Get-Command gcloud

# Check the installed version
gcloud version

# View the high-level command list
gcloud help
~~~

**Expected result:** `Get-Command` locates the executable or command wrapper for `gcloud`; `gcloud version` prints version information and does not report `command not found`.

If PowerShell cannot find `gcloud`, try the terminal created by the installer or close and reopen your terminal. Check the option to add the path to `PATH` before reinstalling.

## 4. Installing on macOS

Google provides installation packages for different machine architectures. First identify the architecture:

~~~bash
uname -m
~~~

Apple silicon machines typically return `arm64`; Intel machines typically return `x86_64`. On the [Install the Google Cloud CLI](https://docs.cloud.google.com/sdk/docs/install-sdk) page, choose the right macOS package or use the interactive installer.

Example of saving the official script locally and running it with Bash:

~~~bash
curl -fsSL https://sdk.cloud.google.com -o install-gcloud.sh
bash install-gcloud.sh
~~~

During installation, choose the install path and allow updating `PATH`/command completion as needed. Then open a new shell or restart the shell:

~~~bash
exec -l "$SHELL"
gcloud version
~~~

The installer may install or pick a compatible supported Python version. If the machine already has multiple Python versions configured, see [gcloud topic startup](https://docs.cloud.google.com/sdk/gcloud/reference/topic/startup) to manage the interpreter. Avoid modifying Python environment variables arbitrarily just to resolve a `gcloud` error.

## 5. Installing on Linux

### 5.1. Debian and Ubuntu with APT

On supported Debian/Ubuntu releases, you can add the official Google Cloud package repository and install the `google-cloud-cli` package.

~~~bash
# 1. Install required utilities
sudo apt-get update
sudo apt-get install ca-certificates gnupg curl

# 2. Install the repository signing key
curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
  | sudo gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg

# 3. Add the package source (run once)
echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
  | sudo tee /etc/apt/sources.list.d/google-cloud-sdk.list

# 4. Install the CLI
sudo apt-get update
sudo apt-get install google-cloud-cli

# 5. Verify
gcloud version
~~~

If the environment already has the repository configured, check first and avoid adding duplicate entries. Other Linux distributions have their own methods (RPM/DNF or tar archives); check the official guide to choose the corresponding package source.

### 5.2. Installing via Compressed Archive or Installer

For Linux distributions not using APT, you can download the `tar.gz` archive matching your CPU architecture from the install page, extract it, and run `./google-cloud-sdk/install.sh`. The following example only illustrates **after downloading and extracting the right archive**:

~~~bash
./google-cloud-sdk/install.sh
gcloud version
~~~

The installation method determines how updates and additional components are handled later. Record whether you installed via APT/DNF, installer, or archive.

## 6. Verifying the CLI After Installation

The commands below only inspect information and do not create GCP resources:

~~~bash
# CLI version and components
gcloud version

# CLI environment information
gcloud info

# Path to the active configuration directory
gcloud info --format="value(config.paths.global_config_dir)"

# Help for command groups
gcloud help
gcloud help config
~~~

**Three layers to keep separate:**

1. **Installation:** The operating system recognizes the `gcloud` command.
2. **Authentication:** The CLI has login credentials to call APIs.
3. **Authorization:** The account has the required IAM permissions on the project/resource.

A machine can pass step 1 yet fail at step 2 or 3. Therefore, a successful `gcloud version` does not prove that the user can list VMs or deploy applications.

## 7. Initializing Configuration with `gcloud init`

After installation finishes:

~~~bash
gcloud init
~~~

The wizard typically performs:

1. Selecting or creating a **named configuration**.
2. Signing in to a Google account if needed.
3. Selecting a default **Project ID** from the projects the account can access, or entering it directly.
4. Selecting a default Compute Engine region/zone if prompted and needed.

When running in a remote terminal environment where a browser cannot open directly:

~~~bash
gcloud init --console-only
~~~

The command displays browser-based authentication instructions instead of attempting to open a browser window on the remote machine. This is an interactive workflow for human users; for CI/CD, use workload authentication mechanisms.

After completion:

~~~bash
gcloud auth list
gcloud config list
gcloud config get-value project
~~~

Illustrative example (not a fixed output):

~~~text
[compute]
region = asia-southeast1
zone = asia-southeast1-a
[core]
account = engineer@example.com
project = demo-gcp-dev
~~~

In the example, `asia-southeast1` is the Singapore region. Choose region and zone based on data requirements, latency, service availability, and organization policy, rather than copying example values blindly.

## 8. Configuring Project, Region, Zone, and Account

You can set individual properties without re-running all of `gcloud init`:

~~~bash
# Use Project ID (not display name)
gcloud config set project PROJECT_ID

# Default values for commands using Compute Engine region/zone
gcloud config set compute/region REGION
gcloud config set compute/zone ZONE

# Review current configuration
gcloud config list
~~~

Practical example for a test environment in Singapore:

~~~bash
gcloud config set project demo-gcp-dev
gcloud config set compute/region asia-southeast1
gcloud config set compute/zone asia-southeast1-a
~~~

If the machine is signed in to multiple accounts, view stored accounts and select an already-authenticated account:

~~~bash
gcloud auth list
gcloud config set account USER_EMAIL
~~~

**Note:** `gcloud config set account` does not replace the login step. If `USER_EMAIL` does not yet have valid credentials, you need to run `gcloud auth login` for that account. Permissions on a project depend on IAM, not on setting the project in CLI configuration.

### 8.1. Defaults and Per-Command Flags

Suppose the active configuration currently selects `demo-gcp-dev`:

~~~bash
# Uses the project in the current configuration
gcloud projects describe demo-gcp-dev

# This command specifies a different project for this run only
gcloud run services list --project=demo-gcp-prod --region=asia-southeast1

# Check again: default project is still demo-gcp-dev
gcloud config get-value project
~~~

The `--project` flag usually takes precedence over the project in the configuration for the running command. Using the flag does not silently change the saved configuration on the machine. For commands involving resource locations, explicitly passing `--region` or `--zone` reduces the risk of operating in the wrong location.

### 8.2. Not Every Resource Uses the Same Scope

- **Project:** unit of management for resources, APIs, many IAM policies, and billing.
- **Region:** geographical location; Cloud Run and many databases use region when creating/listing resources.
- **Zone:** location inside a region; many Compute Engine commands are tied to a zone.
- **Global:** some VPC/Load Balancing resources have global scope; `compute/region` and `compute/zone` do not apply identically to every command.

Changing `compute/region` does not move existing resources to the new region. It only affects the default value of corresponding commands.

## 9. Multiple Configurations for Development and Production

A configuration holds properties such as account, project, region, and zone. When working with multiple projects, create easily recognizable names.

~~~bash
# Create development profile
gcloud config configurations create dev
gcloud config configurations activate dev
gcloud config set project demo-gcp-dev
gcloud config set compute/region asia-southeast1

# Create production profile
gcloud config configurations create prod
gcloud config configurations activate prod
gcloud config set project demo-gcp-prod
gcloud config set compute/region asia-southeast1

# View all configurations and the currently selected one
gcloud config configurations list
~~~

Afterward you can switch back and forth:

~~~bash
gcloud config configurations activate dev
gcloud config list

# Use the prod profile for one command only, without changing the active profile
gcloud projects describe demo-gcp-prod --configuration=prod
~~~

| Way to Select Environment | Scope of Application | When to Use |
| --- | --- | --- |
| `gcloud config configurations activate prod` | Subsequent commands use the newly active profile | Working session-wide in one environment |
| `--configuration=prod` | One specific command | Scripts or targeted checks |
| `--project=demo-gcp-prod` | One specific command | Operating on resources in another project |
| `CLOUDSDK_ACTIVE_CONFIG_NAME` | By shell/process environment variable | Automation or isolated environments |

**Important limitation:** `dev` and `prod` profiles do not automatically create separate credential stores per profile, do not create IAM guardrails, and do not prevent accidental production operations. Always verify account, project, flags, and IAM permissions, especially before `create`, `update`, `delete`, or `deploy` commands.

## 10. Distinguishing CLI Authentication and Application Default Credentials

This is a common point of confusion when learners start writing Java/Python/Node.js applications that call GCP APIs.

| Scenario | Typical Mechanism | Command / Action |
| --- | --- | --- |
| User runs `gcloud` commands locally | Google Cloud CLI credentials | `gcloud init` or `gcloud auth login` |
| App runs locally using Cloud Client Libraries | Application Default Credentials (ADC) | `gcloud auth application-default login` |
| App runs on Compute Engine/Cloud Run | Identity attached to the workload | Attach a service account and grant least-privilege IAM |
| CI/CD job outside Google Cloud | Federation or appropriate short-lived mechanism | Configure Workload Identity Federation for the runner |
| Engineer needs to run commands as a service account | Impersonation when properly authorized | `--impersonate-service-account` flag on supported commands |

### 10.1. Signing In for `gcloud` Commands

~~~bash
gcloud auth login
gcloud auth list
~~~

`gcloud auth login` lets the CLI use the user account. It does not mean every application using Google Cloud client libraries receives those credentials.

### 10.2. ADC Login for Local Application Development

~~~bash
gcloud auth application-default login
~~~

This command creates a credential file used by the libraries' ADC mechanism, separate from the credentials used by `gcloud`. This file typically lives in the user config directory:

- Linux/macOS: `~/.config/gcloud/application_default_credentials.json`.
- Windows: `%APPDATA%\gcloud\application_default_credentials.json`.

Applications using Google Cloud libraries search for credentials across sources in priority order, typically including the `GOOGLE_APPLICATION_CREDENTIALS` variable, the local ADC file, and then the identity attached to the runtime environment with a metadata server.

If a library reports a quota project error, check the service's authentication documentation and account permissions before setting it:

~~~bash
gcloud auth application-default set-quota-project PROJECT_ID
~~~

Choosing a quota project and permission to use quota depend on the API's billing/quota mechanism. Setting `gcloud config set project` does not guarantee that a quota project is configured for ADC.

### 10.3. Secure Authentication in Deployment Environments

For Cloud Run, Compute Engine, and many other managed services, it is standard practice to **attach a service account to the workload** and grant least-privilege IAM according to its function. For CI/CD systems outside Google Cloud, use Workload Identity Federation if supported by the provider and deployment flow.

Avoid committing or sharing service account JSON keys. Credentials, ADC files, tokens, and outputs containing secrets must be protected. Commands that print access tokens are not suitable to include directly in shared docs or build logs. Do not use a personal account stored locally in place of a production application's identity.

## 11. Using the CLI to Inspect GCP Resources

Once you have a valid account and project, these **read-only** commands help confirm the environment:

~~~bash
# Current CLI accounts and active profile
gcloud auth list
gcloud config configurations list
gcloud config list

# List projects the account has permission to view
gcloud projects list

# Inspect project metadata
gcloud projects describe PROJECT_ID

# List APIs enabled in the project
gcloud services list --enabled --project=PROJECT_ID

# List VPC networks
gcloud compute networks list --project=PROJECT_ID

# List Cloud Run services in a region
gcloud run services list --project=PROJECT_ID --region=REGION

# List Cloud Storage buckets
gcloud storage buckets list --project=PROJECT_ID
~~~

Some commands may error if the related API is not enabled, the account lacks IAM permissions, or the project/region has no resources. Returning an empty list is not necessarily an installation error.

### 11.1. Customizing Returned Output

~~~bash
# Print project IDs only (easy to use in scripts)
gcloud projects list --format="value(projectId)"

# Display information as a table
gcloud projects list --format="table(projectId,name)"

# Get JSON output for programmatic processing
gcloud projects describe PROJECT_ID --format=json

# View detailed descriptions of --format and --filter options
gcloud topic formats
gcloud topic filters
~~~

In scripts, prefer structured output or explicit field formatting. Avoid parsing column-aligned table output by character position, because columns, widths, and representations can change.

### 11.2. Reading Documentation Right in the Terminal

~~~bash
gcloud help
gcloud help compute
gcloud help compute instances list
gcloud run services list --help
gcloud topic configurations
~~~

When you need a new command, start from the reference syntax and check specific flags. Commands in the `alpha`/`beta` groups may have different stability and support conditions from generally available commands.

## 12. Updating the CLI and Installing Additional Components

The update mechanism depends on **how it was originally installed**.

| Installation Method | Appropriate Update Method |
| --- | --- |
| Installer/archive with component manager | `gcloud components update` |
| APT on Debian/Ubuntu | `sudo apt-get update` then `sudo apt-get install --only-upgrade google-cloud-cli` |
| DNF/YUM on RPM Linux | Update the `google-cloud-cli` package via the OS package manager |
| Cloud Shell | Use the CLI build provided by the Cloud Shell environment; check the available version |

For installations with component manager:

~~~bash
# View installed and available components
gcloud components list

# Update the CLI along with installed components
gcloud components update

# Example: add Kubernetes management tool if supported
gcloud components install kubectl
~~~

For APT/DNF installations, **`gcloud`'s component manager may be disabled**: use the corresponding OS packages instead of retrying `gcloud components install`. For example, on Debian/Ubuntu, the `google-cloud-cli-gke-gcloud-auth-plugin` package can be used when the GKE auth mechanism is needed; `kubectl` can be installed as a separate package.

Some tools and components have their own release lifecycles. For CI/CD pipelines, consider pinning an appropriate CLI/package version for repeatable deployment results, along with a schedule for updates and testing.

## 13. Pre-Work Configuration Workflow for GCP

Before performing deployments on Compute Engine, GKE, Cloud Run, or databases, follow this short workflow:

~~~mermaid
flowchart TD
    A["Open terminal"] --> B{"CLI installed?"}
    B -- "No" --> C["Install gcloud and check version"]
    C --> D["Check account and profile"]
    B -- "Yes" --> D
    D --> E{"Right account, project?"}
    E -- "No" --> F["Sign in / switch profile / set project"]
    F --> G["Confirm region, zone, and IAM permissions"]
    E -- "Yes" --> G
    G --> H["Run read command to verify"]
    H --> I{"Prerequisites met?"}
    I -- "No" --> J["Check API, IAM, network, billing"]
    J --> H
    I -- "Yes" --> K["Execute permitted operation and observe results"]
~~~

At any step, if permissions are insufficient, resolve them through the IAM process. Do not self-grant overly broad Owner or Editor roles just to bypass a permission error.

## 14. Troubleshooting Common Issues

| Symptom | Possible Cause | How to Check and Resolve |
| --- | --- | --- |
| `gcloud: command not found` / `not recognized` | Not installed or PATH not updated | Open a new terminal, run `gcloud version`, check install path |
| `You do not currently have an active account` | Not signed in or no account selected | `gcloud auth list`, `gcloud auth login`, `gcloud config set account ...` |
| `PERMISSION_DENIED` | Insufficient IAM permissions or resource is not in the project | Check actual account/project, check permissions on the resource |
| `The project property is not set` | Missing default project | `gcloud config set project PROJECT_ID` or `--project=...` |
| `API has not been used or is disabled` | Required service API is not enabled | Confirm project, corresponding API, and who has permission to enable it |
| Service/VM not visible | Wrong project, region/zone, or list permission | `gcloud config list`, pass `--project`, `--region`/`--zone` |
| Timeout / TLS error during `gcloud init` | Connectivity, proxy, firewall, or corporate CA | Check connectivity and [proxy configuration](https://docs.cloud.google.com/sdk/docs/proxy-settings) |
| `gcloud components update` unavailable | Installed via APT/DNF so component manager is inactive | Update via the package manager |
| App fails with `DefaultCredentialsError` despite CLI login | Missing ADC or ADC config overridden | Verify `gcloud auth application-default login`, `GOOGLE_APPLICATION_CREDENTIALS`, and runtime environment |
| Command requires selecting region/zone | Regional resource has no default or service uses its own location | Specify the command flag and read service documentation |

**Effective diagnostic sequence:** check `gcloud version` → `gcloud auth list` → `gcloud config list` → project/region passed to the command → IAM → API status → network/quota. Distinguish installation, authentication, and authorization errors before changing configuration.

### 14.1. Proxy Configuration

If a corporate network requires a proxy, the CLI has configuration properties such as `proxy/type`, `proxy/address`, `proxy/port`, and certificate options; settings depend on the enterprise proxy. Reference example **to be used only when the exact proxy server is known**:

~~~bash
gcloud config set proxy/type http
gcloud config set proxy/address PROXY_HOST
gcloud config set proxy/port PROXY_PORT
~~~

Do not put proxy usernames/passwords in public scripts. For TLS inspection and internal CAs, follow guidance from network administrators; avoid bypassing certificate verification to work around connection errors.

### 14.2. Managing Configurations on Shared Machines

The default CLI configuration is usually stored in the user directory, which can be located with:

~~~bash
gcloud info --format="value(config.paths.global_config_dir)"
~~~

The `CLOUDSDK_CONFIG` environment variable lets you specify a separate configuration directory when truly needed to isolate operational environments. This does not automatically grant IAM permissions; the directory must have appropriate write permissions and protection.

When you no longer use a machine, see [gcloud auth revoke](https://docs.cloud.google.com/sdk/gcloud/reference/auth/revoke) and [gcloud auth application-default revoke](https://docs.cloud.google.com/sdk/gcloud/reference/auth/application-default/revoke) to proactively revoke local credentials. The two mechanisms use different credential stores, so revocation actions differ as well.

## 15. Hands-On Lab: Setting Up Two GCP Profiles

**Scenario:** A development team manages a web service with testing and production environments. You are granted view permissions on both projects and need to inspect Cloud Run services without accidentally changing the default project in your working session.

> Replace `DEMO_DEV_PROJECT_ID`, `DEMO_PROD_PROJECT_ID`, and `REGION` with real values. The lab uses only local configuration and resource-reading commands; do not create VMs or deploy applications.

**Step 1 — Verify tool and identity:**

~~~bash
gcloud version
gcloud auth list
gcloud projects list --format="table(projectId,name)"
~~~

If not signed in yet, run `gcloud auth login`. If projects do not appear, check IAM permissions instead of creating a new project.

**Step 2 — Create the dev profile:**

~~~bash
gcloud config configurations create demo-dev
gcloud config configurations activate demo-dev
gcloud config set project DEMO_DEV_PROJECT_ID
gcloud config set compute/region REGION
gcloud config list
~~~

**Step 3 — Create the prod profile:**

~~~bash
gcloud config configurations create demo-prod
gcloud config configurations activate demo-prod
gcloud config set project DEMO_PROD_PROJECT_ID
gcloud config set compute/region REGION
gcloud config configurations list
~~~

**Step 4 — Set dev as active profile and view production for one command:**

~~~bash
gcloud config configurations activate demo-dev

# Check the dev project
gcloud projects describe DEMO_DEV_PROJECT_ID

# Run a single command under the prod profile
gcloud projects describe DEMO_PROD_PROJECT_ID --configuration=demo-prod

# Active profile is still demo-dev
gcloud config configurations list
gcloud config get-value project
~~~

**Step 5 — View dev Cloud Run (if API and IAM permit):**

~~~bash
gcloud run services list \
  --project=DEMO_DEV_PROJECT_ID \
  --region=REGION
~~~

If using Windows PowerShell, enter this command on **one line** or use PowerShell's line-continuation syntax; the trailing `\` in the example is Bash line continuation.

**Step 6 — Record results in the lab report:**

| Information | What to Record |
| --- | --- |
| CLI version | Output of `gcloud version` |
| Active account | Email marked active in `gcloud auth list` |
| Active profile | Profile name in `gcloud config configurations list` |
| Current Project ID | Output of `gcloud config get-value project` |
| Region | Value of `compute/region` |
| Cloud Run access status | Success/empty list/error with exact message |
| How right environment was verified | Project and region chosen via configuration or explicit flags |

If you re-run the lab, `gcloud config configurations create` may report that the profile already exists. In that case, simply `activate` the existing profile and check its properties; do not delete or overwrite an in-use profile without identifying its owner.

## 16. Self-Check Questions

1. `gcloud version` runs successfully, but `gcloud projects list` reports you are not logged in. Does this belong to the installation, authentication, or authorization layer?
2. Do the two configurations `dev` and `prod` guarantee that an account can only see resources of the corresponding environment? Why?
3. How does `gcloud auth login` differ from `gcloud auth application-default login`?
4. Why should `--project` and `--region` be specified explicitly in deployment scripts?
5. When the CLI is installed via APT, why is `gcloud components update` not the right way to update?
6. Should a Java application running on Cloud Run obtain credentials from a JSON file committed with source code or from an identity attached to the workload?

**Reference Hints:** (1) authentication; (2) no, a profile is a group of properties and permissions are determined by IAM; (3) CLI credentials and ADC serve two different authentication flows; (4) avoids relying on the active profile and default location on the runner machine; (5) the OS package manager owns the installation; (6) prefer an identity attached to Cloud Run with least privilege.

## 17. Google Cloud CLI Usage Checklist

- [ ] Can run `gcloud version` and `gcloud help`.
- [ ] Know whether the machine uses a local CLI or Cloud Shell, and how the CLI was installed.
- [ ] Can explain the currently selected account, project ID, region, and zone.
- [ ] Know how to use `gcloud config list`, `gcloud auth list`, and `--project` to verify the environment.
- [ ] Know how to create, activate, and select a profile per command.
- [ ] Distinguish CLI credentials from application ADC.
- [ ] Understand why production should use workload identity/service accounts and least-privilege IAM.
- [ ] Know how to view help, filter output, and verify permissions before acting.
- [ ] Know how to update the CLI and troubleshoot basic errors.

## 18. Official References

The links below are Google Cloud documentation. Before installing on an actual machine, verify the CLI version, OS architecture, and corresponding steps on the current pages.

- [Install the Google Cloud CLI](https://docs.cloud.google.com/sdk/docs/install-sdk) — OS-specific installation instructions.
- [Using the Google Cloud CLI installer](https://docs.cloud.google.com/sdk/docs/downloads-interactive) — interactive and automated installation.
- [Initialize the gcloud CLI](https://docs.cloud.google.com/sdk/docs/initialize) — `gcloud init` and initial setup.
- [Google Cloud CLI overview](https://docs.cloud.google.com/sdk/gcloud) — usage model and command groups.
- [Managing gcloud CLI configurations](https://docs.cloud.google.com/sdk/docs/configurations) — multiple profiles and properties.
- [Managing gcloud CLI components](https://docs.cloud.google.com/sdk/docs/components) — installing/updating components.
- [Authentication basics](https://docs.cloud.google.com/docs/get-started/authentication) — authentication principles.
- [How Application Default Credentials works](https://docs.cloud.google.com/docs/authentication/application-default-credentials) — credential search order and distinguishing ADC from CLI.
- [gcloud CLI reference](https://docs.cloud.google.com/sdk/gcloud/reference) — command syntax and flags.
- [Proxy configuration](https://docs.cloud.google.com/sdk/docs/proxy-settings) — configuring network environments with a proxy.

**Key Takeaway:** To work safely and reproducibly with Google Cloud, always know **which identity the command is running under, on which project, in which region, and with what permissions**. This is a prerequisite before using the CLI to manage IAM, VPC, Compute Engine, GKE, Cloud Run, databases, or release automation.
