# Selecting Default Project, Region, and Zone for gcloud

## 1. Purpose and Context

When working with the **Google Cloud CLI (`gcloud`)** on a personal machine, in Cloud Shell, or in automation workflows, almost every operation requires specifying a **project**, and some operations also require a **region** or **zone**. If you have to retype these parameters for every command, it is easy to make typos, especially when managing both test and production environments.

For example, a team is learning **Compute Engine, GKE, Cloud Run, IAM, VPC, storage, and databases** on Google Cloud. The team has a development project and a production project, with virtual machine resources placed in a chosen region. Proper default configuration helps:

- Shorten commonly used commands and standardize deployment locations within a working session.
- Reduce the risk of creating or inspecting resources in the wrong project or wrong zone.
- Easily switch context between development, testing, and production environments.
- Establish a clear starting point for controlling IAM, costs, operations, and reliability.

After this lesson, you will know how to **choose, set, view, override, and unset** default values for project, region, and zone; and understand why these values do not automatically apply to every Google Cloud service.

> **Important:** Setting defaults in `gcloud` only changes how **the command-line tool picks parameters for supported commands**. It does not move resources, does not change the location of already-created resources, does not automatically grant IAM permissions, and does not guarantee that other services use the same location.

## 2. Distinguishing Project, Region, and Zone

These three concepts sit at different levels in the Google Cloud resource model:

| Concept | Role | Example | Impact When Chosen Incorrectly |
| --- | --- | --- | --- |
| **Project** | Management boundary for resources, APIs, IAM, and cost/billing tracking | `acme-dev-123` | Commands may run against an unintended environment or dataset |
| **Region** | Geographical area containing zones, used for many regional resources | `asia-southeast1` (Singapore) | May affect latency, data residency, availability, and pricing |
| **Zone** | A deployment domain within a region, suited for zonal resources | `asia-southeast1-a` | Zonal resources may not land in the desired location |

Their relationship can be visualized as follows:

```text
Google Cloud
└── Project: acme-dev-123
    ├── Region: asia-southeast1 (Singapore)
    │   ├── Zone: asia-southeast1-a
    │   ├── Zone: asia-southeast1-b
    │   └── Zone: asia-southeast1-c
    └── Other Region...
```

This is a **context diagram**, not the full governance hierarchy: in practice, one project can contain resources across multiple regions and zones. Google Cloud also has the **Organization → Folder → Project** hierarchy for governing IAM and policies. **Region and zone are deployment locations**, not tiers that replace Folder or Project.

### Project Name, Project ID, and Project Number

A project has three pieces of information that are easily confused:

- **Project name:** display name, mutable, not necessarily unique.
- **Project ID:** string identifier, commonly used for `--project` and `gcloud config set project`; globally unique across Google Cloud.
- **Project number:** Google-assigned numeric identifier, often appearing in resource paths and service identities.

In the examples below, `acme-dev-123` is an **illustrative Project ID**, not a real project available in your account. Replace it with the Project ID assigned to your learning or work environment.

## 3. Preparing Google Cloud CLI and Checking Context

You can run `gcloud` on a machine with **Google Cloud CLI** installed or in **Cloud Shell**. Cloud Shell usually has the CLI and login context ready; a local environment may require initial setup:

```bash
# Check that the CLI is installed on the machine
gcloud version

# Interactive initialization/configuration if needed
gcloud init

# Check accounts signed in to gcloud CLI
gcloud auth list

# List projects the account has permission to view
gcloud projects list
```

If using a personal machine and not yet signed in, you can use `gcloud auth login` according to your organization's policy. **The authenticated account and default project are two separate settings**: signing in successfully does not mean the account has permissions to operate on the selected project.

Also note: `gcloud auth login` serves the **gcloud CLI**, whereas programs using **Application Default Credentials (ADC)** have a separate authentication mechanism. Changing the CLI's default project does not automatically change every ADC configuration or application quota project.

To check the current context right away:

```bash
gcloud config list
gcloud config get-value project
gcloud config get-value compute/region
gcloud config get-value compute/zone
```

If a property is not yet configured, `get-value` may display `(unset)`. This is a valid state: the CLI may prompt for the value, infer it from another option, or report a missing parameter depending on the command being run.

## 4. How to Select a Default Project

### Step 1: Identify the Exact Project ID

In the Google Cloud Console UI, select the project and check its **Project ID**. If using the CLI, you can list the projects you are allowed to view:

```bash
gcloud projects list --format="table(projectId,name,projectNumber)"
```

Not seeing a project in the list may be due to listing permissions or access rights; do not assume the project does not exist. When unsure, confirm the Project ID with an administrator.

### Step 2: Save the Project ID in the Active `gcloud` Configuration

```bash
gcloud config set project acme-dev-123
```

Verify:

```bash
gcloud config get-value project
```

Expected output:

```text
acme-dev-123
```

From this point on, commands that support the project property will use the newly set project **unless overridden by a higher-precedence parameter or configuration**. For example, the following resource-reading command targets the default project:

```bash
gcloud compute instances list
```

The command above only lists VMs. It may require the Compute Engine API to be enabled and the account to have appropriate permissions; getting zero VMs does not prove the project does not exist.

### Overriding the Project for a Single Command

You do not need to modify the saved configuration when you just want to inspect another project:

```bash
gcloud compute instances list --project=acme-test-456
```

In this command, `--project=acme-test-456` applies to **that command only**; the default project remains `acme-dev-123`. The habit of explicitly passing `--project` is especially helpful in scripts, when working with production, and when sharing commands among teammates.

## 5. Selecting a Default Region for Compute Engine Commands

A region typically contains multiple zones. Before choosing, consider:

1. **User location and latency:** an application serving users in Vietnam can test latency to `asia-southeast1` (Singapore) and other suitable regions.
2. **Data residency and compliance requirements:** do not assume the nearest region meets all data storage requirements.
3. **Services, machine types, quotas, and features:** not every service, machine type, or feature is supported in every region.
4. **Reliability and recovery:** consider zone distribution, multi-region architecture if required, as well as RTO/RPO.
5. **Cost:** resource pricing, inter-region data transfer, storage, and networking vary by architecture.

Look up available regions for Compute Engine:

```bash
gcloud compute regions list
```

Set the default region:

```bash
gcloud config set compute/region asia-southeast1
```

Verify:

```bash
gcloud config get-value compute/region
```

Expected output:

```text
asia-southeast1
```

The `compute/region` property is used by supported `gcloud compute` commands as the **default region**. Commands of some other services also have a parameter named `--region` yet use a **separate configuration property** or require specifying the region explicitly. Do not treat `compute/region` as a "Google Cloud-wide region."

For example, when working with **Cloud Run**, you can specify `--region` explicitly on the command and set the dedicated `run/region` property if you use Cloud Run frequently:

```bash
# Read the list of Cloud Run services in the specified region
gcloud run services list --project=acme-dev-123 --region=asia-southeast1

# Dedicated default for Cloud Run commands that support this property
gcloud config set run/region asia-southeast1
gcloud config get-value run/region
```

With **Cloud Storage**, bucket location is selected via `location` when creating the bucket; with **Cloud SQL**, the deployment region must be evaluated via the service's own parameters. Setting `compute/region` does not change the data location of an existing bucket or database.

## 6. Selecting a Default Zone for Zonal Resources

**Zonal** resources, such as many Compute Engine VMs and zonal persistent disks, require specifying a zone. The chosen zone must **belong to the corresponding region**.

List available Compute Engine zones:

```bash
gcloud compute zones list
```

For example, if the region is `asia-southeast1`, one zone in this region is `asia-southeast1-a`:

```bash
gcloud config set compute/zone asia-southeast1-a
gcloud config get-value compute/zone
```

Expected output:

```text
asia-southeast1-a
```

Now you can inspect the related properties in the active configuration:

```bash
gcloud config list
```

Example partial output (other fields may appear):

```ini
[core]
project = acme-dev-123
[compute]
region = asia-southeast1
zone = asia-southeast1-a
```

### When Should You Not Set a Fixed Zone?

If your work is mostly with **regional services** or you frequently switch among multiple zones, you can keep only the default region and specify `--zone` when a command truly needs it:

```bash
gcloud config unset compute/zone
```

For commands targeting a specific VM, specifying the zone avoids location mistakes:

```bash
# Read-only command; replace VM name, project, and zone with real values
gcloud compute instances describe VM_NAME \
  --project=acme-dev-123 \
  --zone=asia-southeast1-a
```

The example above uses **Bash** line-continuation syntax. If using **PowerShell** on Windows, enter the entire command on one line:

```powershell
gcloud compute instances describe VM_NAME --project=acme-dev-123 --zone=asia-southeast1-a
```

When creating a **regional GKE** cluster, resources are managed at the region level and may span multiple zones depending on configuration; therefore, do not assume that "having a default zone means every GKE cluster will reside in that exact zone." When writing deployment scripts, always specify `--region` or `--zone` according to the cluster type.

## 7. Quick Workflow: Configuring a Learning Environment

If you already have an appropriate project, account, and permissions, the following commands form a minimal configuration for Compute Engine labs. All values are **examples**; substitute your real Project ID:

```bash
# 1. Set project for commands that do not specify --project
gcloud config set project acme-dev-123

# 2. Set default region for supported Compute Engine commands
gcloud config set compute/region asia-southeast1

# 3. Set a zone belonging to the selected region
gcloud config set compute/zone asia-southeast1-a

# 4. Verify all three properties are saved
gcloud config get-value project
gcloud config get-value compute/region
gcloud config get-value compute/zone
```

A safe workflow is **read config first → execute command → verify resources/output after the command**. For newly created resources, also check permissions, quotas, estimated costs, and service type before deploying.

## 8. Managing Multiple Projects with Named Configurations

Users often need to work across multiple environments at once. `gcloud` supports **named configurations**: each configuration stores a set of properties such as project, region, and zone. Only one configuration is active as the default in the current CLI context at any given time.

Example of creating a configuration for learning:

```bash
# Create a new configuration and activate it
gcloud config configurations create training

# Set properties for the training configuration
gcloud config set project acme-dev-123
gcloud config set compute/region asia-southeast1
gcloud config set compute/zone asia-southeast1-a

# Check created configurations and the active configuration
gcloud config configurations list
gcloud config list
```

The name `training` is only an example; if a configuration with the same name already exists, use another name or activate the existing one.

If a `production` configuration was created and configured separately beforehand, switch context with:

```bash
gcloud config configurations activate production
gcloud config list

# Switch back to the learning configuration
gcloud config configurations activate training
```

In read-only scripts, you can select a configuration per command via `--configuration` without changing the active configuration:

```bash
gcloud --configuration=training config list
```

**Tip for multi-project environments:** choose clear configuration names such as `training`, `staging`, `production`; verify the project before commands capable of modifying resources. Named configurations help reduce mix-ups, **but they are not an access control mechanism**; IAM and organization policies still determine what an account can do.

## 9. Precedence Order: Command Flags, Environment Variables, and Saved Configurations

For commands that support the corresponding properties, understand the usual precedence order:

1. **Flags explicitly passed on the command** such as `--project`, `--region`, `--zone`.
2. **Corresponding Cloud SDK environment variables**.
3. **Properties of the active `gcloud` configuration**.
4. When no value is set, the default handling of the command or service itself: prompting for input, inferring a value, or raising an error.

Example of setting the project only for the **current Bash session** without writing to the configuration file:

```bash
export CLOUDSDK_CORE_PROJECT=acme-test-456
gcloud config get-value project
```

Similarly in **PowerShell**:

```powershell
$env:CLOUDSDK_CORE_PROJECT = "acme-test-456"
gcloud config get-value project
```

Both examples change an environment variable of the current shell (and child processes). Because environment variables can **override saved properties**, a command's result may differ from what the user remembers setting via `gcloud config set`.

Common related variables:

| `gcloud` Property | Environment Variable | Commonly Used Command Flag |
| --- | --- | --- |
| `core/project` (set via `project`) | `CLOUDSDK_CORE_PROJECT` | `--project` |
| `compute/region` | `CLOUDSDK_COMPUTE_REGION` | `--region` on applicable commands |
| `compute/zone` | `CLOUDSDK_COMPUTE_ZONE` | `--zone` on applicable commands |

**Note:** not every command uses these three properties. For example, Cloud Run's `--region` belongs to the Cloud Run context; do not rely on `CLOUDSDK_COMPUTE_REGION` to locate a Cloud Run service. Check `gcloud <command-group> <command> --help` whenever default behavior is unclear.

For **CI/CD and Infrastructure as Code (IaC)**, specify project and location explicitly in pipeline variables or managed configuration files rather than relying on personal configuration on a developer machine. This makes deployments reproducible and helps control service permissions, costs, and resources by environment.

## 10. Common Errors and Self-Checks

| Symptom | Possible Cause | How to Check and Resolve |
| --- | --- | --- |
| Command operates on the wrong project | Active configuration differs from expected; `--project` flag or environment variable override | Run `gcloud config configurations list`, `gcloud config get-value project`, and inspect flags/env vars |
| Reports VM not found despite appearing in Console | Wrong project or zone | Verify Project ID, VM name, and zone; run `gcloud compute instances list --project=PROJECT_ID` |
| Missing region/zone error | Property not set or command requires a specific location | Run `gcloud config list` then supply `--region`/`--zone` for the right context |
| Zone does not belong to the desired region | For example, picking `asia-southeast1` with zone `us-central1-a` | Check the zone list and align region/zone before creating resources |
| `PERMISSION_DENIED` or `403` | Account lacks IAM, API is not enabled, or policy blocks it | Check `gcloud auth list`, project, APIs, and permissions; default configs do not grant extra rights |
| Cloud Run still asks for region | `compute/region` is not a global default region | Pass `--region` explicitly or check `run/region` |
| Desired location does not support the service/machine type | Differences in product catalog, quotas, or location | Check availability, quotas, machine types, and service config in the intended region |
| Command in a new terminal produces different output | Different environment variables, active configuration, or account | Check active configuration, `gcloud auth list`, and `CLOUDSDK_*` variables in that terminal |

If you want to remove defaults saved in the active configuration:

```bash
gcloud config unset compute/zone
gcloud config unset compute/region
gcloud config unset project
```

These commands only remove CLI configuration properties; **they do not delete projects, VMs, VPCs, or any cloud resources**. If an overriding environment variable is set, the effective value may still appear until that variable is removed from the shell session.

## 11. Verification Lab

Perform these steps on a learning project you have permission to access. This exercise only requires changing **CLI configuration and reading resource lists**, without creating billable services.

**Exercise 1 – Identify Context**

1. Run `gcloud auth list`, `gcloud projects list`, and identify the Project ID you are allowed to use.
2. Run `gcloud config list`, and note the current project, compute/region, and compute/zone.
3. Distinguish the Project ID from the Project name displayed in Console.

**Exercise 2 – Set Defaults**

1. Choose a region supporting Compute Engine, such as `asia-southeast1` if aligned with your permissions and goals.
2. Use `gcloud compute zones list` to pick a zone within that region.
3. Set all three properties with `gcloud config set`, then read each value back using `get-value`.

**Exercise 3 – Test Override Behavior**

1. Run `gcloud compute instances list` against the default project.
2. Run `gcloud compute instances list --project=OTHER_PROJECT_ID`, using another Project ID you have permission to view.
3. Re-check `gcloud config get-value project` and explain why the saved configuration did not change.

**Exercise 4 – Working with Multiple Environments**

1. Create a separate named configuration for the learning environment; set the project, region, and zone again.
2. Run `gcloud config configurations list` to confirm the active configuration.
3. Propose a way to organize dev/prod configurations to reduce the risk of mistaken operations and explain why IAM is still necessary.

You complete this lab when you can answer three questions: **Which project do the resources of the upcoming command belong to? Which parameter determines their location? Is that value coming from a command flag, an environment variable, or the `gcloud` configuration?**

## 12. Official Google Cloud Documentation

- [Google Cloud CLI – Install and Initialize](https://cloud.google.com/sdk/docs/install)
- [Managing gcloud CLI Configurations](https://cloud.google.com/sdk/docs/configurations)
- [gcloud config set](https://cloud.google.com/sdk/gcloud/reference/config/set)
- [gcloud config get-value](https://cloud.google.com/sdk/gcloud/reference/config/get-value)
- [gcloud config configurations](https://cloud.google.com/sdk/gcloud/reference/config/configurations)
- [Regions and zones – Compute Engine](https://cloud.google.com/compute/docs/regions-zones)
- [Cloud Run locations](https://cloud.google.com/run/docs/locations)
- [Resource hierarchy – Organization, Folder, Project](https://cloud.google.com/resource-manager/docs/cloud-platform-resource-hierarchy)

When practicing with Google Cloud, check `--help` syntax and service documentation at the time of operation because support for regions, zones, flags, and configuration properties can change across versions.
