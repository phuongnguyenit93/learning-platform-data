# Getting Started with Google Cloud Console and Cloud Shell

> **Chapter:** GCP Tools and Development Environment  
> **Lesson:** Getting Started with Google Cloud Console and Cloud Shell

In the **CLOUD_PROVIDERS_GCP** module, you will explore Google Cloud from organizational structure and projects, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage, and databases. You also need to know how to choose services, protect resources, automate releases, and monitor reliability and cost. Two tools that start this journey are **Google Cloud Console** and **Cloud Shell**.

Console helps you observe, configure, and administer Google Cloud using a web interface. Cloud Shell provides a command-line environment running in the cloud, with preinstalled tools such as the Google Cloud CLI (`gcloud`). Mastering both helps you understand project structure visually, then repeat and automate operations consistently.

## 1. Learning Outcomes

After this lesson, you will be able to:

- Explain the different roles of Google Cloud Console, Cloud Shell, and Google Cloud CLI.
- Select the right **project** before observing or modifying resources; distinguish between project name, project ID, and project number.
- Locate the areas for managing projects, IAM, APIs, billing, Compute Engine, Cloud Run, and monitoring in Console.
- Open Cloud Shell, use the terminal and Cloud Shell Editor, and inspect accounts, project configuration, and resources via `gcloud`.
- Identify the boundary between a practice environment and infrastructure running real applications.
- Spot common errors related to access permissions, disabled APIs, wrong project/region selection, and cost risks.

## 2. Three Easily Confused Concepts

| Component | Nature | When to Use | Key Thing to Remember |
|---|---|---|---|
| **Google Cloud Console** | Web interface for administering Google Cloud | Exploring resources, checking configuration, monitoring logs/metrics/billing, infrequent operations | Subject to IAM and organization policy controls |
| **Cloud Shell** | Terminal and editor environment running on a Google-managed VM | Practicing commands, checking status, running small scripts, working with repos | Session VM may be recreated; not a production server |
| **Google Cloud CLI (`gcloud`)** | Command-line toolset for calling Google Cloud APIs | Querying resources, configuring, and automating operations | Can run in Cloud Shell, on a personal machine, or in CI/CD |

In other words, **Cloud Shell is where commands run; `gcloud` is the tool that executes commands**. Console and CLI usually interact with the same resources via APIs, so a change made in one tool can be observed in the other.

~~~mermaid
flowchart LR
    U["Learner / Administrator"] --> Console["Google Cloud Console<br/>Browser Interface"]
    U --> Shell["Cloud Shell<br/>Terminal + Editor"]
    Shell --> CLI["gcloud and command-line tools"]
    Console --> API["Google Cloud APIs"]
    CLI --> API
    API --> IAM["Identity, IAM, and<br/>organization policy checks"]
    IAM --> Resources["Projects and resources<br/>Compute, GKE, Cloud Run, Storage..."]
~~~

*Conceptual diagram: access permissions are checked when calling services. Signing in to Console or opening Cloud Shell does not automatically grant administrative permissions over every project.*

### 2.1. Cloud Shell Is Not Compute Engine for Production Deployment

Cloud Shell provides a temporary virtual machine intended for interactive tasks, development, and administration. Compute Engine is the service for creating VMs where you design real workloads and manage configuration, lifecycle, and reliability. Do not place production databases or APIs inside Cloud Shell and expect the terminal session to run continuously.

Cloud Shell has memory, resource, session duration, and usage limits under current policies. Contents in the home directory usually persist across sessions within service limits, but the VM and temporary directories can be replaced. **Important source code must be stored in Git or an appropriate repository**, not treating Cloud Shell as the sole backup.

## 3. Preparation and Understanding Access Scope

You need a Google account that can use Google Cloud, a browser, and access to at least one suitable project for practice. Depending on your organization, you may need an administrator to grant permissions to view projects, use Cloud Shell, or list services.

Before operating, record the following information:

| Information | Meaning | Illustrative Example |
|---|---|---|
| **Organization** | Top-level administration tier for organizational resources, if present | `example.com` |
| **Folder** | Project grouping for governance structure, if used by the organization | `Engineering / Sandbox` |
| **Project name** | Human-readable name, which can be duplicated across projects | `GCP Training` |
| **Project ID** | Unique identifier of the project, commonly used in `gcloud` and APIs | `gcp-training-12345` |
| **Project number** | Numeric identifier assigned by Google, used in many service identities/configurations | `123456789012` |
| **Billing account** | Billing account linked to an eligible project | Check status only; do not disclose the ID to others |
| **Region / Zone** | Regional deployment location / availability zone | `asia-southeast1` / `asia-southeast1-a` |

The values above are examples only. **Project name, project ID, and project number are three different values.** When a command requires `--project`, you typically need the **project ID**.

### 3.1. A Project Is Not Synonymous with a Google Account

One user can access multiple projects; one project can be used by multiple people or service accounts. A project establishes a boundary for managing APIs, quotas, resources, logging, and many policies; billing can be linked from a billing account.

The resource management hierarchy is typically:

~~~text
Organization (if present)
└── Folder (if present)
    ├── Project: development
    │   ├── Cloud Run service
    │   ├── Cloud SQL instance
    │   └── Cloud Storage bucket
    └── Project: production
        ├── Cloud Run service
        └── Cloud SQL instance
~~~

When learning, use an **organization-approved sandbox project** to reduce the risk of affecting real resources. If you do not yet have a project or lack permissions, ask an administrator to provide a practice project and appropriate roles; do not escalate permissions on your own.

## 4. Basic Operations in Google Cloud Console

Open [Google Cloud Console](https://console.cloud.google.com/) and sign in with an authorized account. Item names and menu positions may vary by UI version; the search bar at the top is a fast way to find the right service.

### 4.1. Selecting a Project

1. Find the **project selector** in the top bar; open the project list.
2. Select the project intended for the lab exercise.
3. Go to **Dashboard** or the project info area to confirm the **project ID** and **project number**.
4. Record the project ID. Double-check this selection before any resource creation/deletion operation.

If the list does not contain the expected project, you may be signed in to the wrong account, the project may not have been shared, or your permissions may be insufficient to see the resource.

### 4.2. Getting Familiar with Key Areas

| Area to Find in Console | What Do You Observe? | Connection to Subsequent Lessons |
|---|---|---|
| **IAM & Admin → IAM** | Principals and roles granted on the project | Least privilege, user identities, and service accounts |
| **APIs & Services** | Enabled APIs, API Library, quotas, and usage info | Prerequisite for operating services and investigating API errors |
| **Billing** | Whether the project is linked to billing; costs and budgets if permitted | Cost tracking, budgets, and alerts |
| **VPC network** | Networks, subnets, firewalls, and related routes | Organizing private/public connectivity |
| **Compute Engine → VM instances** | Existing VMs and deployment locations | IaaS model |
| **Kubernetes Engine** | GKE clusters (if any) | Operating containers with Kubernetes |
| **Cloud Run** | Services/jobs and deployment info (if any) | Serverless container platform |
| **Cloud Storage → Buckets** | Buckets, locations, permissions, and storage configuration | Object storage |
| **SQL** | Cloud SQL instances if the project already uses them | Managed relational databases |
| **Logging / Monitoring** | Logs, metrics, dashboards, and alerts | Monitoring reliability and operations |

These pages may be empty in a new project. **An empty page is not necessarily an error:** there may be no resources yet, the API may not be enabled, the location filter may be wrong, or view permissions may be insufficient.

### 4.3. Observing IAM and APIs

In **IAM**, distinguish:

- **Principal**: a user, group, service account, or identity granted permissions.
- **Role**: a set of permissions that a principal has within a given scope.
- **Resource scope**: the organization, folder, project, or specific resource where the role is assigned.
- **Policy/organization policy**: governance constraints that can block an action even when a role appears to allow it.

In **APIs & Services**, identify enabled APIs and disabled APIs. Enabling an API is **a project configuration change** and may require separate permissions; this first exercise only observes status.

### 4.4. Safely Observing Billing

If permitted, check which billing account the project is linked to and whether a **budget/alert** exists. A budget alert helps detect costs, **but is not by default an automatic mechanism to stop spending**. Creating VMs, databases, buckets, public IPs, or running workloads can incur costs depending on configuration and usage duration.

You do not need to create billable resources to complete this introductory lesson.

## 5. Starting Cloud Shell

From Console, select the **Activate Cloud Shell** button (terminal icon at the top of the interface). Accept the authorization/initialization prompt if requested by organization policy. The terminal window will appear in the browser.

Cloud Shell typically provides a Linux environment with Google Cloud CLI and many familiar development tools. Tool lists and versions may change, so verify them directly.

~~~bash
pwd
echo "$HOME"
command -v gcloud
gcloud version
command -v git
git --version
~~~

**Explanation:**

- `pwd`: current working directory location.
- `$HOME`: user's home path in the shell session.
- `command -v`: locates the executable path of a tool.
- `gcloud version`: confirms the Google Cloud CLI version.
- `git --version`: confirms the Git tool.

These commands only observe the environment and **do not create Google Cloud resources**.

### 5.1. Terminal, Editor, and Web Preview

- **Terminal:** suitable for `gcloud`, `git`, checking configurations, and running utilities and scripts.
- **Cloud Shell Editor:** edit source code/configuration using an editor interface tied to the Cloud Shell environment; can be opened from the Cloud Shell interface depending on version.
- **Web Preview:** preview a web application running on a compatible port in the development environment; this is a preview tool and does not replace production deployment.

A typical workflow: pull code from Git into Cloud Shell, edit in Editor, run checks, preview, then commit/push back to the repository as permitted. Do not store tokens, passwords, or private keys in the repo.

### 5.2. Sessions and Files

Distinguish two types of data:

| Storage Location | How It Is Used | Things to Watch Out For |
|---|---|---|
| **Cloud Shell Home** | Source code and configuration for practice; persisted across sessions per service policy | Subject to quotas and retention conditions; not a long-term backup |
| **Temporary directories and VM session processes** | Builds, caches, experimental services | May be lost when the VM is reinitialized or the session terminates |
| **Cloud Storage/Git/Artifact Registry** | Intentional storage for objects, source, and artifacts | Has its own IAM, lifecycle, pricing, and governance rules |

If the Shell suddenly disconnects, prioritize checking the session status and recovering from Git. Do not conclude that Google Cloud resources were deleted just because the terminal closed.

## 6. Working with `gcloud`: Accounts, Projects, and Configuration

Cloud Shell is usually pre-integrated with authentication for the signed-in user; you do not need to run a login command repeatedly in every normal session. However, **authentication** (who you are) and **authorization** (what you are allowed to do) are two different things.

### 6.1. Checking the Current Session

~~~bash
gcloud auth list
gcloud config list
gcloud config get-value project
gcloud config configurations list
~~~

Meaning:

- `gcloud auth list` shows the accounts with credentials in the CLI and which account is currently active. Do not post screenshots containing personal emails or sensitive information unnecessarily.
- `gcloud config list` displays active configuration properties such as account, project, and default region/zone if set.
- `gcloud config get-value project` prints the default project ID; if unconfigured, it may return an unset state.
- `gcloud config configurations list` lists CLI configurations, useful when working across multiple environments.

**Important:** The project selected in Console and the CLI default project may not match in some sessions or after configuration changes. Verify **both** before running resource-writing commands.

### 6.2. Specifying the Project Explicitly

Once you know the appropriate project ID, you have two options:

~~~bash
# Option A: set the default project for the current CLI configuration.
gcloud config set project YOUR_PROJECT_ID

# Option B: specify a dedicated project for a specific command.
gcloud projects describe YOUR_PROJECT_ID \
  --project=YOUR_PROJECT_ID
~~~

Replace `YOUR_PROJECT_ID` with the real project ID; do not use the literal placeholder string.

`gcloud config set project` only changes the **CLI configuration**; it does not create or rename a project. For scripts operating across multiple environments, passing `--project` in each command usually helps avoid mistakes compared to relying on implicit configuration.

You can also set defaults for regional services when needed:

~~~bash
# Illustrative; changes CLI configuration only.
gcloud config set compute/region asia-southeast1
gcloud config set compute/zone asia-southeast1-a
~~~

Here `asia-southeast1` is the Singapore region; `asia-southeast1-a` is a zone in that region. The actual location must be chosen based on latency, data, service availability, fault tolerance, and cost requirements. Many Cloud Run or other service commands still require an explicit `--region`/`--location`.

### 6.3. Observing Projects with Read-Only Commands

~~~bash
# Projects that the current identity can list.
gcloud projects list \
  --format="table(projectId,name,projectNumber)"

# Details of the project being practiced on.
gcloud projects describe YOUR_PROJECT_ID \
  --format="yaml(projectId,name,projectNumber,lifecycleState)"

# Enabled APIs in the project (if view permission is available).
gcloud services list \
  --enabled \
  --project=YOUR_PROJECT_ID \
  --format="table(config.name)"
~~~

The commands above do not create VMs, APIs, or databases. The `projects list` output only reflects the scope that the current identity is allowed to list; it does not necessarily include every project in an organization.

If `services list` reports `PERMISSION_DENIED`, you need to check service listing permissions; do not grant broad administrative roles to "fix it quickly."

## 7. From Console to Cloud Shell: Same Resource, Two Perspectives

Suppose you have selected `YOUR_PROJECT_ID` in Console and want to know whether the project has any VMs or Cloud Run services.

| Task | In Console | In Cloud Shell |
|---|---|---|
| View identity and access permissions | **IAM & Admin → IAM** | `gcloud auth list` only shows CLI identity; does not replace viewing IAM policy |
| View current project | Project selector / dashboard | `gcloud config get-value project` and `gcloud projects describe` |
| View enabled APIs | **APIs & Services → Enabled APIs** | `gcloud services list --enabled --project=YOUR_PROJECT_ID` |
| View VMs | **Compute Engine → VM instances** | `gcloud compute instances list --project=YOUR_PROJECT_ID` |
| View Cloud Run services | **Cloud Run → Services** | `gcloud run services list --project=YOUR_PROJECT_ID --region=asia-southeast1` |
| Observe logs | **Logging → Logs Explorer** | `gcloud logging read` with appropriate filter and project |
| Check costs | **Billing → Reports/Budgets** | Console is easier to inspect in the introductory lesson; billing view permissions may be independent of the project |

The following two practice commands only **list** existing resources:

~~~bash
gcloud compute instances list \
  --project=YOUR_PROJECT_ID

gcloud run services list \
  --project=YOUR_PROJECT_ID \
  --region=asia-southeast1
~~~

If a service has no resources yet, you will see an empty list. If an API is not enabled or permissions are insufficient, the command may return an error; that is an opportunity to distinguish **API**, **IAM**, and **selecting the wrong project**, rather than guessing that the project is broken.

### 7.1. Filters and Reading Output

Google Cloud CLI supports output formatting and filtering to read results faster:

~~~bash
# View only the needed columns of the project list.
gcloud projects list \
  --format="table(projectId,name,projectNumber)"

# JSON output suitable for script integration.
gcloud projects describe YOUR_PROJECT_ID \
  --format=json
~~~

When scripting, rely on structured fields (`--format=json` or an explicit format expression) rather than parsing free-form printed columns. You can explore command parameters with:

~~~bash
gcloud help
gcloud projects --help
gcloud run services list --help
~~~

`--help` displays help without modifying resources. Command names and flags may change as the CLI is updated; check the documentation/`--help` of the version in use.

## 8. Guided Practice: Exploring a Project Without Creating Resources

**Goal:** complete one Console ↔ Cloud Shell verification cycle using read-only operations. If you lack permission at a step, record the result and reason; there is no need to request broad roles just to complete the exercise.

### Step 1 — Verify in Console

1. Sign in to Console and select the assigned sandbox project.
2. Record the **project name**, **project ID**, and **project number** from the project info page.
3. Open **IAM** to observe how principals are assigned roles; do not edit policies.
4. Go to **APIs & Services** to view the list of enabled APIs.
5. Check **Compute Engine**, **Cloud Run**, or **Cloud Storage** to see if any resources already exist.

### Step 2 — Open Cloud Shell and Cross-Check Identity

~~~bash
gcloud version
gcloud auth list
gcloud config get-value project
~~~

Compare the active account and default CLI project with the Console information. If the project does not match, you can pass `--project=YOUR_PROJECT_ID` to subsequent commands instead of modifying the global configuration.

### Step 3 — Confirm the Project via API

~~~bash
gcloud projects describe YOUR_PROJECT_ID \
  --format="table(projectId,name,projectNumber,lifecycleState)"
~~~

Cross-check the **project ID** and **project number** against Console. If the information does not match, stop any impactful commands and re-confirm the right project.

### Step 4 — Observe Existing Services

~~~bash
gcloud services list \
  --enabled \
  --project=YOUR_PROJECT_ID \
  --format="table(config.name)"

gcloud run services list \
  --project=YOUR_PROJECT_ID \
  --region=asia-southeast1
~~~

Compare the list of APIs and services with the corresponding pages. Note that Cloud Run is a regional resource: finding no services in `asia-southeast1` **does not prove** that the project has no Cloud Run services in another region.

### Step 5 — Look Broader at Cost and Reliability

In Console, locate **Billing → Budgets**, **Logging → Logs Explorer**, and **Monitoring**. Observe the signals if the project already has workloads. Do not conclude that a system lacks monitoring when a new project is empty or your permissions only allow partial viewing.

### Step 6 — Record Results

You can use this short verification template:

| Verified Item | Value to Record | Result |
|---|---|---|
| Console Project ID | Actual Project ID | Matches/differs from CLI |
| `gcloud` Project ID | `gcloud config get-value project` | Correct/unset/needs fixing |
| CLI Identity | Active account from `gcloud auth list` | Authorized/insufficient permissions |
| Project number | From dashboard and `projects describe` | Matches/differs |
| Enabled APIs | Names of 2–3 observed APIs | Viewable/lacks permission |
| Cloud Run in checked region | List of services or empty | Success/error with explanation |
| Billing and monitoring | Located corresponding pages | Viewable/lacks permission |

Finish the exercise when you can explain **which project** the observed data belongs to, **which identity** the query ran under, and **what impact** it has.

## 9. IAM, Security, and Notes in a Learning Environment

### 9.1. Principle of Least Privilege

- Only use authorized accounts and projects; separate sandbox from production whenever possible.
- Grant **roles appropriate to the task**; do not grant `Owner`/`Editor` just to work around read-only command errors.
- Use an appropriate **service account** for applications/CI; do not default to personal identities for production workloads.
- Do not copy access tokens, service account keys, passwords, or secrets into practice files, Git, or screenshots.
- Verify the project and region before any resource creation, update, or deletion command.

In Cloud Shell, the CLI session integrates with your account; running commands remains subject to IAM constraints. An account that can view the project page does not necessarily have permission to create VMs, enable APIs, or manage billing.

### 9.2. Distinguishing Three Groups of Operations

| Operation Group | Examples | Impact Level |
|---|---|---|
| **Observation** | `gcloud projects describe`, `gcloud services list`, viewing dashboards | Usually does not modify resources; still requires read permissions |
| **Changing local CLI config** | `gcloud config set project`, changing default region | Changes context for subsequent commands; does not modify the cloud project itself |
| **Changing the cloud** | `gcloud services enable`, `gcloud run deploy`, creating VMs/buckets, editing IAM | May alter security, quotas, or incur costs |

When moving from exploration to deploying Compute Engine, GKE, or Cloud Run, clearly identify the third group and your organization's change control process.

### 9.3. Cloud Shell and Application Default Credentials

`gcloud` uses credentials managed by the CLI. **Application Default Credentials (ADC)** is the mechanism application libraries use to locate credentials. The two flows are related but should not be treated as identical. When writing applications with client libraries or running code on Cloud Run/GKE/VM, choose the appropriate identity mechanism and avoid embedding JSON keys in source code.

In this introductory lesson, you only need the identity already present in Cloud Shell to run query commands. Granting permissions to applications will be covered when studying IAM and deploying workloads.

## 10. Troubleshooting Common Issues

| Symptom | Possible Cause | Safe Way to Check |
|---|---|---|
| Project not visible in Console | Wrong account, missing permissions, or project not shared | Check signed-in account, project selector, and ask the project administrator |
| `gcloud config get-value project` has no value | No default project selected in CLI | Pass `--project=YOUR_PROJECT_ID` or set config after confirming the ID |
| `PERMISSION_DENIED` | Identity lacks IAM permissions or is blocked by organization policy | Check `gcloud auth list`, correct project, and specific required role |
| `API has not been used / is disabled` | Service API is not enabled | Check **APIs & Services**; enable only when authorized and needed |
| VM/service not visible as in Console | Wrong project, region, filter, or list permission | Compare project ID and location between the two tools |
| `NOT_FOUND` or invalid project | Typo in project ID, using project name instead of ID, or missing access | Use `gcloud projects list`/`describe` and cross-check dashboard |
| Cannot use Cloud Shell | Organization policy, access permission, quota, or session error | Check Console messages; contact admin or try a new session if appropriate |
| Terminal disconnected, test process stopped | Cloud Shell session expired or VM changed | Restart shell; recover code from Git, check data stored in persistent locations |
| Created resources incur unexpected costs | Active workloads/DBs/IPs/storage or scaling configuration still running | Check Billing, resource labels, budgets, usage, and handle unnecessary resources |

Some APIs return similar errors for missing permissions or nonexistent resources. **Do not conclude for certain that a resource does not exist from a single error message.** Verify identity, project, location, API, and role in order.

## 11. Connection to Real-World Google Cloud Deployment

You will use Console and Cloud Shell throughout the module:

| Upcoming Topic | Use Console To | Use Cloud Shell/CLI To |
|---|---|---|
| **Projects and IAM** | View project structure, principals, and roles | Inspect projects, policies, and CLI config with appropriate permissions |
| **VPC** | Observe subnets, routes, and firewalls | List network configurations, support scripts, and check status |
| **Compute Engine** | View VMs, boot disks, zones, metrics | Automate queries, create/configure VMs when authorized |
| **GKE** | View clusters and workloads | Use `gcloud` to get cluster info, `kubectl` when authorized |
| **Cloud Run** | View services, revisions, traffic, and logs | Deploy containers, inspect services or jobs via CLI |
| **Storage / Database** | View buckets, instances, backup configs | Manage configuration and operations with appropriate commands |
| **Operations / Cost** | View dashboards, logs, alerts, and budgets | Create repeatable operations, inspect configs, and support pipelines |

For example, a development team deploying an API on Cloud Run might start in Console to check the project, IAM, and budget; use Cloud Shell to run test commands in a sandbox; move those same CLI principles into CI/CD with a service account and least privilege; and finally return to Console to inspect logs, latency, errors, and cost.

Cloud Shell is very useful for learning and experimentation, but **production pipelines** should run from a managed CI/CD environment with dedicated identities, version control, approvals, and change logs.

## 12. Self-Assessment Exercises

1. **A project has name `Training` and project ID `gcp-training-12345`.** When running a `gcloud` command, which value should you use for `--project`? Why?
2. **You select project A in Console, but the CLI returns project B.** How will you check and fix the command context?
3. **The Cloud Run page in Console shows no services in the Singapore region.** Can you conclude the entire project does not use Cloud Run? What else should you check?
4. **Sign-in succeeds, yet `gcloud services list` is denied.** Is this necessarily an authentication error, or could it be an authorization error?
5. **You want to run a long-lived API for real users.** Why should you not use Cloud Shell? Which services within this module's scope are more suitable?
6. **Why must you still monitor costs even after setting up a budget alert?** Point out the difference between an alert and a spending cap.
7. **Why should you confirm the project ID, identity, and region before a deployment command?** State one consequence of choosing each factor incorrectly.

**Answer Hints:** (1) Use the project ID; (2) compare the selector and `gcloud config get-value project`, pass `--project` or update the CLI config; (3) no, check other regions and permissions; (4) usually requires verifying IAM/organization policy; (5) Cloud Shell is an interactive environment, look at Cloud Run, GKE, or Compute Engine depending on needs; (6) budget alerts do not block billing by default; (7) wrong project may touch production, wrong identity may violate permissions, wrong region affects latency, data residency, and cost.

## 13. Completion Checklist

- [ ] Accessed the right Google Cloud Console and selected the sandbox project.
- [ ] Distinguished between project name, project ID, and project number.
- [ ] Located IAM, APIs & Services, Billing, Compute Engine, Cloud Run, Logging, and Monitoring.
- [ ] Opened Cloud Shell, learned how to use the terminal and editor, and understood session limits.
- [ ] Ran and explained `gcloud auth list`, `gcloud config list`, and `gcloud projects describe`.
- [ ] Cross-checked the project between Console and CLI; understood how to use `--project` and `--region`.
- [ ] Performed at least one read-only API or resource observation.
- [ ] Explained the principle of least privilege, environment boundaries, and cost risks.

**Key Takeaway:** Console helps you **see** resources and policies; Cloud Shell helps you **operate via command line**; `gcloud` connects those operations to Google Cloud APIs. Before any real change, know clearly **who is acting**, **on which project**, **in which location**, and **what the operation affects**.
