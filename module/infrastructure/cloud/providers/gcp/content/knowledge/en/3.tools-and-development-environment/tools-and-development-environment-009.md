# Cloud Workstations and Managed Development Environments

In a development team, each engineer often installs Java, Node.js, Docker, IDEs, SDKs, and libraries in their own way. Version mismatches make a feature work on one machine and fail on another; new hires spend a lot of time on setup; and security teams struggle to govern access paths to cloud resources. A **managed development environment** standardizes tools, compute resources, permissions, and environment lifecycles.

Within the **CLOUD_PROVIDERS_GCP** module, **Google Cloud Workstations** is the service that provides cloud-based development environments on Google Cloud with centrally managed configurations. This lesson belongs to the **GCP Tools and Development Environment** chapter, supporting learners as they develop and test applications before deploying to Compute Engine, GKE, or Cloud Run, connecting to Cloud Storage/databases, and managing IAM, VPC, cost, and reliability.

After this lesson, you will be able to:

- Explain when Cloud Workstations is a good fit for a development team.
- Distinguish **workstation cluster**, **workstation configuration**, and **workstation**.
- Set up a coding environment and access it via a browser-based IDE or local editor.
- Design container images, machine types, persistent directories, networking, and IAM permissions.
- Operate Start/Stop lifecycles, update environments, and control costs.
- Propose a safe onboarding and application deployment workflow from a workstation.

## 1. What Problems Do Managed Development Environments Solve?

A development environment includes the IDE, compiler, build tools, package managers, CLI, container tooling, credentials, and connectivity to dependent systems. If every developer configures their own machine, projects easily suffer from "works on my machine" bugs caused by missing dependencies or version drift.

A managed service provides **reproducible environment templates**, provisioned on demand, with controlled access identities and shared cost policies. With Cloud Workstations, a platform team can maintain templates for Java backend, frontend, or data work; each developer creates their own workstation from that template.

| Option | When It Fits | Points to Consider |
|---|---|---|
| Local machine | Need offline work or dependence on local hardware | Prone to config drift and hard to govern centrally |
| **Cloud Shell** | Running quick `gcloud` commands, learning GCP, short experiments | Not primarily designed to provide long-term workstations with custom team templates |
| **Cloud Workstations** | Multiple developers needing consistent IDEs/tools and centrally managed permissions/networking | Requires managing configuration, IAM, networking, and service costs |
| Self-managed Compute Engine VM | Need specialized VM-level control | Team must handle provisioning and lifecycle operations themselves |
| Local dev containers | Want consistent dependencies while running on a laptop | Does not by itself provide Google Cloud VM, access, and network management layers |

Cloud Workstations is a **place for development and testing**, not a service for running production workloads in place of GKE, Cloud Run, or Compute Engine.

## 2. Architecture: Cluster → Configuration → Workstation

Cloud Workstations has three primary resource types:

| Component | Function | Example |
|---|---|---|
| **Workstation cluster** | A group of workstations in a region, managing VPC connectivity and the service gateway | `dev-cluster` |
| **Workstation configuration** | Template defining VM, image, IDE, persistent disk, timeouts, and operational settings | `java-backend` |
| **Workstation** | Personal environment created from a configuration; can Start, Stop, and Launch | `alice-java` |

~~~text
Google Cloud project: team-dev-tools
└── Region: chosen based on users and workloads
    └── Workstation cluster: dev-cluster
        ├── VPC / subnet / gateway connectivity
        ├── Configuration: java-backend
        │   ├── Machine type / quota
        │   ├── IDE + JDK + build tools in container image
        │   ├── Persistent home directory
        │   ├── IAM / service account / idle timeout
        │   ├── Workstation: alice-java
        │   └── Workstation: bob-java
        └── Configuration: frontend
            ├── IDE + Node.js in a different image
            └── Workstation: carol-frontend
~~~

**A workstation cluster is not a GKE cluster.** It is a Cloud Workstations resource that manages development environments at a regional level. Workstations run on Compute Engine VMs in the project, and inside the VM is a container holding the editor and tools specified by the configuration.

One configuration is shared by multiple workstations. When the team updates the container image or machine type in a configuration, workstations pick up the new configuration on their next start per the service's mechanism. Therefore, template changes must be tested, especially when multiple people rely on them.

### Project, Region, Network, and Team Separation

- **Project:** where APIs are enabled and IAM, billing, and Workstations resources are managed.
- **Region:** cluster location. Choose based on latency, regional service availability, data requirements, and services to connect to.
- **VPC/subnet:** network path for accessing required data sources or services.
- **Configuration:** the unit separating machine types, software environments, and usage policies.

You do not need one cluster per developer. Consider a separate cluster when you need a different region or VPC connection; create separate configurations when Java and frontend teams need different dependencies, machine types, or permissions.

## 3. Lifecycle and Data Persistence

Workstations run on **ephemeral VMs**. Developers start the environment while working and stop it when finished; the development environment can use a centrally managed image and a persistent home directory to preserve data across sessions.

~~~mermaid
flowchart LR
    A[Platform creates cluster] --> B[Platform creates configuration]
    B --> C[Grant developer permissions]
    C --> D[Create workstation]
    D --> E[Start and Launch]
    E --> F[Write code, build, test]
    F --> G[Stop or auto-stop]
    G --> E
    G --> H[Delete when no longer used]
~~~

On **Stop**, the ephemeral VM is destroyed and in-memory state in RAM is lost. If a **persistent home directory** is configured, the disk is reattached on the next Start to retain source code and files in home. Without persistent storage, session data can be lost. Whether the persistent disk is deleted or retained on **Delete workstation** is determined by the `reclaim policy`.

| Data or State | After Stop/Start |
|---|---|
| Source code in home on persistent disk | Retained if a persistent directory is configured |
| Editor settings and working files in home | Retained if saved inside the persistent area |
| Changes in the container's writable temp layer or non-persistent paths | May be lost |
| Running processes, active terminals, RAM | Not retained |
| Commits pushed to a remote Git repository | Still present on the remote repo |
| Persistent disk after deleting the workstation | Depends on `DELETE` vs. `RETAIN` |

**A persistent disk does not replace Git or backups.** Keep fixed dependencies in the container image, store code in a repository, and do not place passwords/tokens into home or the image without proper controls.

### Idle Timeout, Running Timeout, and Quick Start

- **Idle timeout:** automatically stops the workstation after a configured period with no interactive activity.
- **Running timeout:** automatically stops the workstation after a configured maximum runtime duration.
- **Quick start pool:** keeps a number of standby VMs ready to reduce startup wait time; incurs additional cost.

Test timeouts with long test/build workflows; background jobs can still be interrupted if the workstation stops per policy. When onboarding a team, clearly explain where data is persisted so developers avoid losing work.

## 4. Standardizing IDEs and Dependencies with Container Images

Cloud Workstations provides base images with editors and basic tools. **Cloud Workstations Base Editor** is based on Code OSS, supporting a terminal, extensions, and Cloud Code; the service also supports several IDE options or access from a local IDE/SSH depending on configuration.

For a Java project, a `java-backend` configuration might include an appropriate JDK, Git, Gradle/Maven, `gcloud` CLI, and Java extensions. The platform team picks a suitable base image and customizes it via a Dockerfile so every developer's environment is consistent.

**Illustrative** example of extending an organization-approved base image (image path/name must be configured at build time):

~~~dockerfile
ARG BASE_IMAGE
FROM $BASE_IMAGE

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       git curl unzip openjdk-21-jdk-headless \
    && rm -rf /var/lib/apt/lists/*

# Do not embed secrets, tokens, or private keys in the image.
# Do not write user configs into /home during build:
# home is mounted when the workstation starts a session.
~~~

This is a template to adapt: the base image must support `apt-get`, and entrypoint and user permissions must remain compatible; before rolling it out to the team, pin the image by digest, verify the JDK, and test editor configuration. If the custom image lives in a private Artifact Registry, the workstation VM's service account must have permission to pull the image.

A sound image maintenance loop includes: managing the Dockerfile in Git, building via pipeline, scanning for vulnerabilities, testing on a canary workstation, then updating the configuration and instructing members to restart. Avoid relying on unpinned `latest` tags and avoid installing ad-hoc dependencies into temporary layers that vanish on the next start.

## 5. Creating a Workstation in Google Cloud Console

Prerequisites before creation:

- A project with **billing** enabled, sufficient quota, and appropriate admin permissions.
- The **Cloud Workstations API** (`workstations.googleapis.com`) enabled.
- A region selected that supports the service and planned machine types.
- VPC/subnet, gateway, IAM, container image, and home disk size defined.
- A Google Group or identities to be granted create and usage permissions.

**Step 1: Create a cluster.** In Console, go to **Cloud Workstations → Cluster management → Create**. Enter a name and select a region; when private networking is needed, select the VPC/subnet and appropriate public or private gateway.

**Step 2: Create a configuration.** Go to **Cloud Workstations → Workstation configurations → Create**. Select the cluster, VM type, IDE/image, persistent directory, reclaim policy, and auto-stop timeouts. Consider disabling the quick start pool to reduce costs in test environments.

**Step 3: Grant permissions.** In the users/permissions section, add the Google Group of developers allowed to create workstations. Verify the service account's permissions if pulling a private custom image or accessing GCP APIs.

**Step 4: Developer creates a workstation.** Go to **Cloud Workstations → Workstations → Create**, choose the configuration, and enter a personal environment name.

**Step 5: Launch and verify.** The developer clicks **Launch** to open the browser IDE. Test the terminal, clone a repository, run a build; then Stop, Start again, and verify files in home persisted.

Creating a cluster and configuration can take some time. If creation fails, inspect IAM errors, quotas, APIs, networking, or Organization Policy constraints. Private cluster designs must align with the network team's architecture; choosing a private endpoint may require DNS, Private Service Connect, and dedicated private access paths.

## 6. CLI Example: Creating a Basic Workstation

The snippet below uses **Bash** as an experimental template. Replace the project ID and region with appropriate values; real commands can provision billable resources.

~~~bash
PROJECT_ID="my-dev-tools-project"
REGION="us-central1"
CLUSTER="dev-cluster"
CONFIG="java-dev"
WORKSTATION="dev-alice"

# Select project and enable the Workstations API.
gcloud config set project "$PROJECT_ID"
gcloud services enable workstations.googleapis.com

# Create cluster (default gateway configuration for practice).
gcloud workstations clusters create "$CLUSTER" \
  --region="$REGION"

# Create configuration: Code OSS, 4 vCPU machine, 50 GB home disk,
# auto-stop after 1 hour of inactivity and keep no quick start VMs.
gcloud workstations configs create "$CONFIG" \
  --cluster="$CLUSTER" \
  --region="$REGION" \
  --machine-type=e2-standard-4 \
  --container-predefined-image=codeoss \
  --pd-disk-type=pd-balanced \
  --pd-disk-size=50 \
  --idle-timeout=3600 \
  --pool-size=0

# Create a personal environment from the configuration.
gcloud workstations create "$WORKSTATION" \
  --cluster="$CLUSTER" \
  --config="$CONFIG" \
  --region="$REGION"

# Start when ready to use.
gcloud workstations start "$WORKSTATION" \
  --cluster="$CLUSTER" \
  --config="$CONFIG" \
  --region="$REGION"
~~~

After Start, open Console to Launch. These commands do not replace granting permissions to others: an administrator must assign the necessary IAM roles at the proper scope. Learners should inspect `gcloud workstations ... --help` before running, because configuration flags and default values may be updated over time.

## 7. IAM: Separating Admin, Usage, and GCP Access Permissions

Permission to use the IDE is separate from permission to access Google Cloud resources from the terminal or applications inside the workstation.

| Role / Group | Permission or Usage | Recommended Scope |
|---|---|---|
| Platform Admin | `roles/workstations.admin`: manage clusters, configurations, and workstations | Dedicated dev-tools project, granted sparingly |
| Developer creating environments | `roles/workstations.workstationCreator`: create workstations from allowed configurations | Appropriate configuration or project |
| Developer using environments | `roles/workstations.user`: Start/Stop/use a workstation | That developer's workstation |
| Operation viewing | `roles/workstations.operationViewer` when needed per IAM docs | Project |
| Identity running code | Service account or Google Cloud-supported identity | Only needed dev services and resources |

In standard creation flows, a user creating a workstation via the Creator role is granted User permission on the workstation they created. This does not automatically grant permission to deploy Cloud Run or read data in Cloud Storage.

Key principles:

1. Assign permissions to a **Google Group** rather than individuals when managing larger teams.
2. Give developers creator/user roles, not project-wide admin by default.
3. Grant the VM's service account **least privilege**; if the image is in a private Artifact Registry, it needs image-pull permissions.
4. Separate developer identities from **production CI/CD deployment identities**; do not assign production permissions just to run a demo.
5. Do not write service-account keys, tokens, or passwords into images, repositories, or scripts in home.
6. Review workstation port access settings when running an internal web server; do not leave public access open automatically.

With libraries calling Google Cloud APIs, understand which credential the application uses (for example Application Default Credentials) and verify IAM on the **target resource**. Having access to a workstation does not guarantee access to a database or bucket.

## 8. Network and Security Design

A workstation may need to download dependencies from the Internet, pull images from Artifact Registry, or call databases and microservices inside a VPC. Choosing the gateway, VPC, and egress path is therefore an important architectural decision.

| Configuration | Purpose | What to Check |
|---|---|---|
| **Public gateway** | Access via service endpoint from public networks when permitted | Google authentication/IAM, port restrictions, and egress controls |
| **Private gateway/cluster** | Access gateway over a private network path | VPC, DNS, Private Service Connect, routing/VPN, or corporate interconnect |
| **Disable public IP for VMs** | Reduce direct Internet exposure surface | Cloud NAT or Private Google Access depending on API/service access needs |

A public gateway **does not mean anyone can open the IDE**: access still requires authentication and authorization. Conversely, a private gateway does not make the whole system secure on its own if firewalls, service accounts, or data permissions are overly broad.

Example of a backend needing a database with only a private IP:

- Place the workstation in a VPC/subnet with routing to the database.
- Configure firewall rules allowing only genuinely required sources and ports.
- Use appropriate DNS and network access for Google Cloud APIs and Artifact Registry.
- Grant database access only to the right identity; separate dev and production credentials.
- Avoid copying production data onto a workstation without explicit safeguards and usage authorization.

Some Organization Policy constraints can affect VM image creation and Private Service Connect. Check Cloud Workstations requirements before setting up clusters in organizations with strict network policies.

## 9. From Development Environment to Cloud Run / GKE Deployment

Example of a team building a Java REST API and deploying to Cloud Run:

~~~text
Developer
  → Cloud Workstations (code, debug, unit tests)
  → Git repository + pull request
  → CI/CD (build, security checks, tests)
  → Artifact Registry (reviewed image)
  → Cloud Run: dev → staging → production
  → Cloud Logging / Cloud Monitoring
~~~

Once the platform team has prepared the JDK and build tools:

~~~bash
java -version
git clone https://github.com/example-org/sample-java-api.git
cd sample-java-api

# Example when the repository includes the Gradle Wrapper.
./gradlew test
./gradlew bootRun
~~~

The URL and repository name are illustrative only. If using Maven Wrapper, the team can run `./mvnw test`. When previewing a web app running inside the workstation, use preview/port-forwarding features according to permitted configuration.

Workstations are for **writing and testing code**; Git stores history; CI/CD handles reproducible builds and releases using its own identity; Cloud Run or GKE runs workloads. Do not treat an individual developer's workstation as the sole builder of production artifacts or holder of deployment secrets.

## 10. Costs, Auto-Stop, and Budget Allocation

Workstations costs consist of several components, not just the running VM:

| Cost Item | When It Accrues | Mitigation |
|---|---|---|
| Compute Engine VM | While the workstation is running | Choose right-sized machines, use Start/Stop |
| Workstation management fee per vCPU | While the workstation is active | Idle/running timeouts and appropriate VM types |
| Persistent disk | May continue accruing even while the workstation is Stopped | Right-size capacity; delete unused disks |
| Cluster / control plane | While the cluster exists, even when all workstations are stopped | Avoid creating redundant clusters |
| Quick start pool | Standby VMs kept ready for fast startup | Set pool size small or 0 when unneeded |
| Networking, image registry, and other services | Depends on supporting infrastructure | Track billing by SKU, project, and labels |

~~~text
Total cost (estimated)
  = VM compute active hours
  + per-vCPU management fee × workstation active hours
  + persistent disk
  + hourly cluster existence fee
  + quick start pool, networking, and supporting services (if any)
~~~

Suppose 10 developers only use workstations during work hours: if left unstopped, each machine could run overnight and over weekends. Auto-sleep cuts active machine hours **but does not eliminate persistent disk and cluster fees**. To reduce costs further, review leftover disks, VM sizes, test-only clusters, and quick start pool VM counts.

You can attach labels for cost analysis:

~~~yaml
team: backend
environment: development
service: java-api
cost_center: engineering
~~~

Set up Cloud Billing budgets and alerts; remember that **a budget alert does not stop resources by default**. Exact pricing depends on region, machine type, SKU, and current rates, so consult the official pricing table before finalizing configurations.

## 11. Common Issues and Where to Check

| Symptom | Likely Cause | Check |
|---|---|---|
| Developer cannot see configuration | Wrong project, region, or missing IAM | Check project/cluster and Creator/Operation Viewer roles |
| Cannot create workstation | Missing permissions, API disabled, quota, or bad config | Check API errors and Compute Engine quotas |
| Slow or failed Start | Large image, unable to pull image, capacity shortage | Check image URI, service account, region/zone |
| Custom image rejected | VM service account lacks Artifact Registry Reader | Check image pull permissions |
| Cannot reach private environment | DNS, private endpoint, PSC, or network route | Trace path from user network to gateway |
| Cannot connect to database | Firewall/VPC/DNS or IAM/credentials | Check each network layer and authentication step |
| Files lost after Stop/Start | Saved outside persistent directory | Check mount path and storage policy |
| IDE disconnects during long build | Idle/running timeout or network drop | Check timeout configuration and logs |
| Stopped yet still incurring charges | Disk or cluster is still billed | Check billing by SKU and remaining resources |

The operations team should define who creates/deletes workstations, who maintains images, how resources are reclaimed when staff transfer teams, how data remaining on persistent disks is handled, and how quotas are raised as demand grows.

## 12. Design Scenario: Onboarding 20 Backend Developers

An enterprise develops Java APIs on Cloud Run. New developers spend a lot of time installing JDK/Gradle and configuring machines; everyone ends up with different versions. The team must access a test database over a VPC, while never reaching the production database.

Proposed solution:

1. Create a `dev-tools` project governed by IAM and billing.
2. Create a cluster in an appropriate region connected to the VPC hosting the dev database.
3. Build a `java-backend` configuration with a vetted image, JDK, Gradle, Code OSS, persistent home, and timeouts.
4. Grant Creator to the backend Google Group at the proper scope; each engineer creates a personal workstation.
5. Configure a service account with least-privilege dev permissions; CI/CD uses its own identity to release to Cloud Run.
6. Manage the image via Git/pipeline, run vulnerability scans, and test updates before rolling out.
7. Monitor active workstation counts, cluster/VM/disk costs, quotas, and access permissions.

This shortens onboarding and reduces tooling drift. Even so, the team must still review permissions, operate networking, control costs, and clean up resources when developers leave the project.

**When Cloud Workstations is not needed yet:** a very small team running only a few `gcloud` commands may fit Cloud Shell; projects requiring continuous offline work may prefer local environments; workloads needing specialized VM setups may choose self-managed VMs. Decisions should be driven by governance, security, networking, and total cost requirements.

## 13. Checklist and Exercise

- [ ] Project has APIs enabled, billing active, sufficient quota, and a clear owner.
- [ ] Region/cluster/VPC/gateway align with users and target services.
- [ ] Configuration specifies machine type, image, IDE, and persistent directory.
- [ ] Image has a build workflow, version pinning, vulnerability scanning, and update process.
- [ ] IAM Admin, Creator, User, and service account are granted at the right scope.
- [ ] No secrets stored in images or code; no default production permissions.
- [ ] Tested Start, Launch, Stop, Restart, and file persistence in home.
- [ ] Idle timeout, running timeout, quick start pool, and reclaim policy decided.
- [ ] Cost monitoring, allocation labels, and workstation offboarding workflow in place.

**Applied Exercise:** Design Cloud Workstations for 8 Java backend developers and 4 frontend developers. Backend needs to connect to a dev database with a private IP; frontend only needs to run and preview a web app. Propose the number of clusters, configurations, VM types, images, persistent disks, IAM, VPC, idle timeouts, and cost-optimization plan. Then describe the path from code on a workstation through CI/CD to Cloud Run without granting individual developers production deployment rights.

## Official References

- [Cloud Workstations overview](https://cloud.google.com/workstations/docs/overview) — concepts and lifecycle.
- [Create a workstation cluster](https://cloud.google.com/workstations/docs/create-cluster) — networking and regions.
- [Create a workstation configuration](https://cloud.google.com/workstations/docs/create-configuration) — VMs, images, disks, authorization.
- [Customize container images](https://cloud.google.com/workstations/docs/customize-container-images) — building and updating images.
- [Access control with IAM](https://cloud.google.com/workstations/docs/access-control) — user authorization.
- [Cloud Workstations pricing](https://cloud.google.com/workstations/pricing) — billing components.
- [gcloud workstations reference](https://cloud.google.com/sdk/gcloud/reference/workstations) — current command syntax.
