# ACR Tasks and Automating the Image Build Process

When deploying containerized applications on Microsoft Azure, the release workflow usually begins by turning source code and a Dockerfile into a **container image**. Images must be built consistently, versioned for traceability, security-checked, and stored in a registry accessible to the runtime environment. If every developer manually builds and pushes images from personal machines, quality and reproducibility vary; credential rotation, base image updates, and build history tracking also become difficult to manage.

**Azure Container Registry (ACR)** is an Azure-managed registry service for storing and distributing container images and compatible artifacts. **ACR Tasks** adds the ability to build images on Azure infrastructure, run multi-step workflows, and trigger builds based on events such as source code updates, base image updates, or recurring schedules per supported features.

This lesson belongs to the **Container Registry and Container Apps** chapter of the CLOUD_PROVIDERS_AZURE module. The content connects ACR with subscriptions, resource groups, Microsoft Entra ID, managed identities, Azure Container Apps, Azure Monitor, and cost control for an application deployment workflow from source code to production.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain registry, repository, tag, digest, Dockerfile, and the role of ACR Tasks in the software supply chain.
2. Distinguish between a **quick task** (on-demand build), a trigger-based **automated task**, and a YAML-based **multi-step task**.
3. Execute an example image build from a source directory using Azure CLI without running a Docker daemon on the control machine.
4. Design triggers based on source commits, base image changes, and suitable schedules.
5. Configure practical ACR Tasks, monitor runs, read logs, and verify that images have been pushed.
6. Manage identities, push/pull permissions, secrets, provenance, scanning, and artifact immutability.
7. Connect build pipelines with controlled deployments to Azure Container Apps or another container hosting platform.
8. Diagnose errors such as unreachable source contexts, faulty Dockerfiles, denied pushes, untriggered tasks, or unrolled-out new images.

Examples use Bash and Azure CLI. Registry names, source repos, and images are illustrative only; resource creation, builds, or task runs may incur charges and require appropriate Azure permissions.

## 2. Fundamental Concepts Before Automating

### 2.1. A Container Image Differs from a Running Container

A **container image** is a data package containing layers, filesystem, metadata, and configuration needed for a runtime to instantiate a container. A **container** is a running instance created from an image; pushing a new image to ACR does not automatically alter existing running containers.

A common release flow:

~~~mermaid
flowchart LR
    S["Source code + Dockerfile"] --> T["ACR Task build"]
    B["Base image"] --> T
    T --> V["Testing / artifact verification"]
    V --> R["Azure Container Registry"]
    R --> D["CD approval / deployment"]
    D --> C["Azure Container Apps / AKS / App Service"]
    C --> M["Monitoring, rollback, cost"]
~~~

In practice, testing steps can run before or after building depending on the check type. The diagram only illustrates component responsibilities; it does not imply every step is automatically provided out of the box by ACR.

### 2.2. Key Terminology

| Term | Meaning | Example |
|---|---|---|
| Registry | Service storing and distributing images | myacr.azurecr.io |
| Repository | Group of images sharing a logical name in a registry | orders-api |
| Tag | Label pointing to a specific manifest/image; can be reassigned | orders-api:1.4.2 |
| Digest | Content-derived value uniquely identifying an immutable manifest | sha256:... |
| Dockerfile | Instructions for constructing layers and an image | FROM, COPY, RUN, USER, ENTRYPOINT |
| Build context | Set of input files sent to a build job | Source folder or Git repository |
| Base image | Image referenced in the FROM instruction | eclipse-temurin:21-jre |
| Task | Build/automation definition managed by ACR | orders-ci |
| Task run | A specific execution with an ID, status, and logs | Run ID assigned by ACR |
| Trigger | Condition causing a task to be scheduled/executed | Commit, base image update, cron |
| Service principal/managed identity | Workload identity used to access Azure or external services | Pipeline or task identity |

A fully qualified image name takes the form:

~~~text
<REGISTRY_NAME>.azurecr.io/orders-api:1.4.2
~~~

In this format, the registry login server, repository, and tag are distinct components. For production environments, record the **deployed digest** as well to avoid ambiguity if a tag is overwritten.

### 2.3. Why Are Tags Insufficient to Guarantee Reproducibility?

A tag like latest or stable can be re-pointed to a different image. If a pipeline overwrites the same tag, two deployments using the exact same image name string will fetch different contents.

Recommended strategy:

- Tags containing a semantic version like 1.4.2 for human readability.
- Tags containing a Git commit SHA or build run ID for exact traceability.
- Record the image digest in the release record; when strict immutability is needed, deploy by digest if the platform supports it.
- Retain release artifacts and build metadata according to retention policies.
- Do not treat relying solely on the latest tag as sufficient for production rollbacks.

## 3. What Problems Does ACR Tasks Solve?

Azure Container Registry stores images. **ACR Tasks** executes build workloads on ACR-managed build infrastructure and automates creating new image versions.

Example of an organization releasing orders-api:

1. A developer pushes a commit to the main branch.
2. The system triggers an ACR Task configured to connect to the source.
3. The task fetches the build context and Dockerfile, pulls the base image, and builds the new version.
4. The image is tagged, pushed to ACR, and run logs are recorded for traceability.
5. The release pipeline checks the image, test/security results, and approvals.
6. The CD system updates Azure Container Apps to use the new image.
7. Azure Monitor/Log Analytics and the application confirm the new version is healthy.

**ACR Tasks does not automatically equal a full CI/CD system.** ACR runs the configured steps; quality gates, reviews, signing, production deployment, rollback, and release management may still require Azure DevOps, GitHub Actions, or other tools.

### 3.1. Three Common Task Categories

| Type | How It Starts | Best Suited For |
|---|---|---|
| Quick task | User/CI invokes az acr build or az acr run | Trial builds, one-off builds, Dockerfile verification |
| Automated task | Pre-created task runs via trigger or manual invocation | Auto-building on code changes, base image updates, or schedules |
| Multi-step task | YAML task describing build, push, or command steps | Workflows with multiple images, preparation, checks, or sequential packaging |

A task can combine one or more of these mechanisms depending on its definition and supported features. Choosing a task type depends on the source code, trigger mechanism, security requirements, and release management model.

## 4. Prerequisites

To practice, you need:

- An Azure subscription with the correct tenant/resource group selected.
- Permission to create an ACR or work with an existing registry.
- Azure CLI installed, signed in, and supporting the az acr command group.
- A valid Dockerfile and build context.
- Ability for the task runner to fetch required base images and dependencies.
- Appropriate registry permissions to create tasks/builds and store images.
- If triggering from Git: permission to manage the Git repository and appropriate webhooks/tokens.
- If deploying to Container Apps: deploy permissions, a pull-capable identity, and a configured app/container environment.

Example names:

~~~text
Resource group: rg-container-lab
Azure region: southeastasia
Registry name: acrorderslab123
Registry login server: acrorderslab123.azurecr.io
Repository: orders-api
Task name: orders-ci
~~~

The ACR name must be valid and unique within the service scope; replace it with your own name. Choose a **registry SKU** based on features, storage needs, private networking, quotas, and cost. Limits for networking, task runs, and throughput can vary across Basic, Standard, and Premium.

Verify the subscription:

~~~bash
az account show --output table
az account set --subscription "<SUBSCRIPTION_ID>"
~~~

Do not run registry creation commands in production merely to follow a tutorial.

## 5. Practice 1: Quick Task Image Build on ACR

### 5.1. Create a Test Resource Group and Registry

In Bash:

~~~bash
az group create \
  --name rg-container-lab \
  --location southeastasia

az acr create \
  --resource-group rg-container-lab \
  --name acrorderslab123 \
  --sku Standard \
  --location southeastasia
~~~

If the name is already taken, pick another name. In practice, an existing registry may be used, so skip creation to avoid duplicate resources.

Retrieve the login server:

~~~bash
az acr show \
  --name acrorderslab123 \
  --query loginServer \
  --output tsv
~~~

Appropriate permissions are required for resource creation, building, and pushing. Signing in to Azure CLI does not imply every role has permission to create ACR Tasks or push data.

### 5.2. Example Dockerfile for a Java Application

Suppose a Spring Boot application has the following structure:

~~~text
orders-api/
  Dockerfile
  .dockerignore
  pom.xml
  src/
    main/
      java/
      resources/
~~~

Multi-stage Dockerfile example:

~~~dockerfile
# Build stage: compiles the JAR during image build.
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /src
COPY pom.xml .
RUN mvn -B -ntp dependency:go-offline
COPY src ./src
RUN mvn -B -ntp -DskipTests package

# Runtime stage: excludes Maven and source code from the running app image.
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /src/target/*.jar /app/app.jar
RUN chown -R 10001:10001 /app
USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

This snippet assumes Maven produces **a single runnable JAR** in target. If the build generates multiple JAR files (e.g., original and repackaged), specify the exact path to avoid copy failures. You also need to configure Spring Boot to listen on the right port and runtime for the Container Apps environment.

Include a .dockerignore to exclude .git directories, temporary files, unnecessary artifacts, credentials, .idea folders, target, and files outside the intended build context. However, if a Dockerfile copies a pre-built artifact from target, .dockerignore must match that build model; in this example, the JAR is built inside the container so sending target is unnecessary.

Never use COPY on an entire directory that might contain secrets or .env files from a developer machine into the image.

### 5.3. Build from a Local Directory Without a Local Docker Daemon

Navigate to the project directory containing the Dockerfile. Run:

~~~bash
az acr build \
  --registry acrorderslab123 \
  --image orders-api:1.0.0 \
  --file Dockerfile \
  .
~~~

Where:

- --registry specifies the target ACR.
- --image sets the repository name and tag for the built image.
- --file selects the Dockerfile.
- The trailing dot represents the current directory as the build context.

ACR receives the context and executes the build server-side. **You do not need a running local Docker daemon just to invoke az acr build**, though you still need Azure CLI, network connectivity, and permission to upload context/build. Actual builds can still fail due to Dockerfile, dependency, network, or quota issues.

After a successful build, the expected image name is:

~~~text
acrorderslab123.azurecr.io/orders-api:1.0.0
~~~

### 5.4. Verify the Image in the Registry

~~~bash
az acr repository list \
  --name acrorderslab123 \
  --output table

az acr repository show-tags \
  --name acrorderslab123 \
  --repository orders-api \
  --output table
~~~

To inspect the version more deeply, view image/manifest metadata and digest per current CLI or API capabilities. Record the verified digest in the release record. Seeing a tag proves an artifact was pushed; it does not automatically prove it is secure or runnable.

### 5.5. Test the Container Image Before Release

A successful build can still hide runtime bugs such as wrong ports, insufficient resources, Java startup errors, or unready health endpoints. You should:

1. Check dependencies and build outputs.
2. Run unit/integration tests in the pipeline.
3. Inspect image metadata, size, and software components.
4. Run the image in a test environment with appropriate networking and secrets.
5. Verify HTTP readiness/health and runtime configuration.
6. Record the build/run ID, commit SHA, digest, and gate outcomes.

Never treat a BUILD SUCCEEDED message as the sole acceptance criterion.

## 6. Creating an ACR Task for On-Demand Reruns

A quick task fits one-off builds. To re-invoke the same definition or attach triggers, create a **named task**.

### 6.1. Build Context Sources

A task can use multiple supported context forms, such as a Git repository or a source recognized by ACR Tasks. URL/ref syntax, private repository credentials, and file paths must match current CLI requirements.

Conceptual Git example:

~~~text
Git repo: https://github.com/EXAMPLE_ORG/orders-api
Branch: main
Dockerfile: Dockerfile
Output: orders-api:<run-id>
Task: orders-ci
~~~

Replace EXAMPLE_ORG and the repository with a source you manage. When using automated triggers from Git, ACR needs webhook/credential permissions matching the Git provider and repository type; do not assume public repositories can always configure triggers without an authorization step.

### 6.2. Create a Task Triggered by Git Commits

Bash example using a token retrieved from an approved secret management system:

~~~bash
az acr task create \
  --registry acrorderslab123 \
  --name orders-ci \
  --image 'orders-api:{{.Run.ID}}' \
  --context 'https://github.com/EXAMPLE_ORG/orders-api.git#main' \
  --file Dockerfile \
  --git-access-token "$GIT_ACCESS_TOKEN" \
  --commit-trigger-enabled true
~~~

Notes:

- {{.Run.ID}} is an ACR Tasks template variable used to tag by **run**; it is evaluated by the task engine, not Bash.
- Single quotes preserve template syntax when passed to the CLI.
- GIT_ACCESS_TOKEN must come from a secure secret store/pipeline, with minimal scopes and expiration/rotation.
- Never print the token with echo, commit it to source code, or paste real values into documentation.
- Passing secrets via CLI arguments risks exposure in process lists or logs depending on the environment; in production, prefer tool/pipeline-supported credential storage and avoid shell tracing.

Git trigger parameters, token types, and webhook permissions may vary across GitHub/Azure Repos and CLI updates. Before official deployment, check:

~~~bash
az acr task create --help
~~~

If your organization restricts PATs or webhooks from ACR, you can have GitHub Actions/Azure DevOps **invoke the ACR Task manually** using an OIDC-federated identity instead of setting up direct commit triggers with a long-lived token.

### 6.3. Run and Inspect the Task

~~~bash
az acr task run \
  --registry acrorderslab123 \
  --name orders-ci

az acr task show \
  --registry acrorderslab123 \
  --name orders-ci \
  --output json
~~~

Monitor runs:

~~~bash
az acr task list-runs \
  --registry acrorderslab123 \
  --output table
~~~

View logs for a specific run:

~~~bash
az acr task logs \
  --registry acrorderslab123 \
  --run-id "<RUN_ID>"
~~~

Obtain RUN_ID from the output of task run or list-runs. Logs may expose file paths, build context info, and dependency output; restrict log read access and avoid printing secrets during build steps.

When a manual run succeeds, also verify that the image tag was actually created and pushed. A running task configuration does not guarantee the current build context matches the commit you expect.

### 6.4. Separating Task Definition from Task Execution

- **Task definition:** holds source info, output image, triggers, run options, and step definitions.
- **Task run:** a single execution with start/end times, status, and logs.
- **Image artifact:** output of a build run, identified by tag and digest.
- **Deployment:** decision to roll out a verified image into a runtime environment; this is a separate step.

These objects should share clear ID links to audit the chain from commit → build → image → deploy.

## 7. Automated Trigger Mechanisms

### 7.1. Commit Trigger

When a source repository receives a new commit on the configured branch/ref, webhook/trigger integration can execute the ACR Task. Success requires:

1. Matching repository/branch.
2. Valid credentials or webhook integration.
3. Task is not disabled.
4. Valid build context and Dockerfile at the updated commit.
5. Registry/task runner has permission to read source, pull base images, and push output.
6. Available quota, network access, and connectivity to dependencies.

Do not let every push on every branch produce images eligible for production deployment. For critical codebases, enforce protected branches, reviews, testing, and approval gates before release.

### 7.2. Base Image Update Trigger

An application may rely on a base image containing OS/runtime layers, for example:

~~~dockerfile
FROM eclipse-temurin:21-jre
~~~

When the publisher updates the base image to patch a vulnerability, the application image **does not change automatically** just because the base tag was updated. To incorporate the fix, you must rebuild the application and push a new artifact.

ACR Tasks supports a **base image update trigger** in supported registry/base image scenarios. A task can re-execute when the system detects a qualifying base image change.

Things to verify:

- The base image is hosted on a registry and image type ACR Tasks can track.
- The task is configured with the relevant trigger enabled.
- The platform resolved the dependency between the Dockerfile and base image as expected.
- If the Dockerfile uses multiple stages, changes to which stage should trigger a rebuild?
- The task wrote a new output image, but has its deployment been approved?

**Do not assume ACR instantaneously tracks every public image or every dynamic FROM pattern.** Detection mechanisms and response intervals vary by registry, source, and feature support. Verify on a real system and keep a scheduled rebuild fallback.

### 7.3. Scheduled Trigger

Some images should be rebuilt on a schedule to pull updated components and catch security bugs or dependency drift even when source code has not changed.

Illustrative cron-scheduled task example:

~~~bash
az acr task create \
  --registry acrorderslab123 \
  --name orders-nightly \
  --image 'orders-api:nightly-{{.Run.ID}}' \
  --context 'https://github.com/EXAMPLE_ORG/orders-api.git#main' \
  --file Dockerfile \
  --schedule '0 2 * * *' \
  --git-access-token "$GIT_ACCESS_TOKEN" \
  --commit-trigger-enabled false
~~~

The cron expression here specifies the schedule understood under current ACR Tasks scheduler rules; check timezones and service cron capabilities before deploying. Do not infer schedule timing from a developer laptop's timezone. During periodic monitoring, record actual run times and check for skipped or failed runs.

A nightly build producing a new image should not necessarily deploy straight to production. Typically, vulnerability policies, integration tests, reviews, or CD approvals are required.

### 7.4. When to Choose Which Trigger?

| Trigger | Best-Fit Scenario | Pitfalls |
|---|---|---|
| Commit | Want a new image whenever code changes | Building unreviewed branches, expired webhooks/tokens |
| Base image | Want image updates when OS/runtime gets patched | Not all base sources are trackable; can produce untested images |
| Schedule | Want periodic rebuilds to catch dependency drift | Run costs and accumulation of old images |
| Manual/API/pipeline | Want explicit gates in CI/CD | Depends on external pipeline and task execution permissions |

Multiple triggers can be combined for the same system, provided you control **duplication**, prevent excessive concurrent builds, and prevent unintended tag overwrites.

## 8. Multi-Step ACR Tasks with YAML

For simple workflows, a Dockerfile and one output image suffice. When building multiple images, running preparation tools, or pushing sequentially, a **multi-step task** lets you define steps in YAML.

### 8.1. Example Structure

Suppose the source contains a Dockerfile. Create `acr-task.yaml`:

~~~yaml
version: v1.1.0
steps:
  - build: -t {{.Run.Registry}}/orders-api:{{.Run.ID}} .
  - push:
      - "{{.Run.Registry}}/orders-api:{{.Run.ID}}"
~~~

Meaning:

- version: ACR Task YAML syntax version in the example.
- steps: sequential list of execution steps.
- build: builds an image tagged with the run ID.
- push: pushes the image to the target registry.
- {{.Run.Registry}} and {{.Run.ID}}: runtime variables substituted by ACR Tasks in supported contexts.

ACR Tasks versions may add additional structures for steps, commands, dependencies, conditional execution, and task properties. When extending, follow the official schema documentation rather than assuming any shell command can be placed directly under build or push.

### 8.2. Running a Multi-Step Task On Demand

From the directory containing the Dockerfile and acr-task.yaml:

~~~bash
az acr run \
  --registry acrorderslab123 \
  --file acr-task.yaml \
  .
~~~

The command instructs ACR to execute the YAML definition using the current directory as the build context. This is a quick run of a YAML task; it does not create a persistent triggered task.

### 8.3. Extending with Quality Gates

A multi-step workflow can be logically structured as:

~~~mermaid
flowchart TD
    A["Fetch source and Dockerfile"] --> B["Build image"]
    B --> C["Check Dockerfile / image / dependencies"]
    C --> D{"Gate checks pass?"}
    D -->|No| E["Fail task, save logs"]
    D -->|Yes| F["Push image / record digest"]
    F --> G["Export metadata to CD pipeline"]
    G --> H["Separate approval and deployment"]
~~~

**Do not assume** capabilities such as vulnerability scanning, SBOM generation, image signing, or test frameworks are built-in automatic steps simply because you use ACR Tasks. Those capabilities typically require specific tools/steps/integrations, identities, and policies.

For example, a scan step might use a supported external tool to analyze image packages and vulnerabilities; if findings exceed thresholds, the task or release pipeline must block the image from reaching production. The organization must define thresholds, vulnerability feeds, and approved exception mechanisms.

### 8.4. Build Once, Deploy Across Environments

A critical principle:

~~~text
Source commit C
    ↓
ACR build / quality gates
    ↓
Image digest D
    ├── Dev
    ├── Staging
    └── Production (after approval)
~~~

Reusing the **same image digest** across environments eliminates the risk of rebuilds producing different artifacts while making releases and rollbacks easier to trace. Environment-specific settings such as DB URLs, Key Vault references, replica counts, and networking belong in runtime configuration, never baked as production secrets inside the Dockerfile.

## 9. Securing ACR Tasks and Managing Identities

### 9.1. Task Management Permissions Differ from Data Access Permissions

Distinguish at least three permission tiers:

| Need | Actor | Control Example |
|---|---|---|
| Create/modify ACR and tasks | Admin or Azure management automation | Azure RBAC at registry/resource group scope, task management permissions |
| Push images to registry | Build workload or task runner | Corresponding repository write permissions under the registry's RBAC/ABAC model |
| Pull images when running apps | Azure Container Apps/AKS/App Service | Appropriate repository pull permissions, typically via managed identity |

Do not grant registry administrative rights to an application runtime that only needs to pull images. A registry may use registry-level RBAC or repository-scoped ABAC permission modes; verify exact permissions and role names against current ACR settings.

### 9.2. Azure RBAC, Managed Identity, and Entra ID

Whenever possible, use:

- Microsoft Entra identities for administrators with MFA/PIM per policy.
- Managed identities for Azure Container Apps when pulling images from ACR in supported scenarios.
- Federated workload identity/OIDC for GitHub Actions or Azure DevOps when calling Azure CLI/ACR APIs.
- An ACR Task identity to access Azure resources like Key Vault per supported Task capabilities instead of hardcoded credentials.

Having a managed identity on a task **does not automatically grant** access to read every secret or push/pull across every repository. You must create role assignments at the exact resource/scope and verify them with actual builds.

### 9.3. Managing Git Source Credentials

An ACR task pulling context from a private repository may need read access to source code and permission to create webhooks. Principles:

1. Issue tokens with minimal scopes and appropriate expiration.
2. Separate source repository credentials from production deployment credentials.
3. Never commit PATs into Dockerfiles, YAML, Makefiles, or shell scripts.
4. Control who can view/edit task definitions, logs, and credentials.
5. Rotate/revoke tokens per procedure; test triggers after rotation.
6. Prefer OAuth/OIDC or integrations without long-lived secrets where supported.

### 9.4. Never Put Secrets Inside Images

Dangerous practices:

- COPYing a .env containing credentials into the build context.
- Using ARG or ENV to hold secrets while assuming they vanish after the build.
- Using RUN echo secret to create temporary files inside a layer.
- Printing connection strings or tokens in build logs.
- Pushing an image containing production configs into a broadly accessible repository.

If a build needs credentials to fetch private dependencies, use the build/task system's secret mechanism or a supported dependency provider following procedures that prevent leaks into layers and logs. Scan images/layers/configs after building to confirm no unauthorized data is present.

### 9.5. Registry and Build Network Isolation

ACR supports firewalls, private endpoints, and private networking depending on SKU. However, blocking public network access or restricting the registry to private endpoints can affect ACR Tasks' ability to read/write the registry or fetch source/base images via default execution infrastructure.

Before choosing a private networking architecture:

- Check how the task runner reaches the registry, Git sources, package feeds, and base images.
- Verify dedicated agent pool features or networking options supported by ACR Tasks in your current SKU/region if needed.
- Ensure proper DNS, private endpoints, and routing.
- Avoid permanently opening the registry to the public Internet just to fix a build error.
- Distinguish 401/403 permission errors from DNS failures, timeouts, or firewall-blocked connections.

## 10. Container Image Quality and Integrity

### 10.1. Choosing Trusted Base Images

Base images should come from trusted publishers with clear update policies, explicit versions, and matching CPU architectures. For Java apps, align JDK for builds and JRE for runtime (or a supported distro).

Example:

~~~dockerfile
FROM eclipse-temurin:21-jre
~~~

Tags can change when publishers push updates. For high **reproducibility**, you can pin digests in the Dockerfile per supply chain requirements. However, digest pinning means base image security updates must be actively managed: a task tracking a new tag may not suffice if the Dockerfile still locks an old digest.

Balance two goals:

- **Reproducibility:** same source, same dependencies, and same base digest for repeatable builds.
- **Freshness:** regularly receiving runtime/OS patches and reducing vulnerabilities.

Workflows can use automated bots to update digests, review PRs, rebuild, scan, and release rather than relying solely on the latest tag.

### 10.2. SBOM, Scanning, Signing, and Provenance

A critical release may require:

1. **SBOM:** inventory of components and dependencies inside the image.
2. **Vulnerability scan:** detecting OS and package CVEs using organization-approved vulnerability feeds.
3. **Image signing:** signatures verifying who published the image/manifest.
4. **Provenance:** attestation proving which source commit, pipeline, and builder created the artifact.
5. **Policy enforcement:** production accepts only images satisfying policy criteria.

ACR Tasks helps execute defined steps, yet **does not replace the entire supply chain toolset**. You can combine ACR capabilities, Microsoft Defender for Cloud, and appropriate CI/CD tools. Scanning features and coverage depend on licensing, configuration, artifact types, and tool capabilities.

### 10.3. Multi-Architecture Images

Images for linux/amd64 and linux/arm64 are not automatically interchangeable. If runtime environments span multiple architectures, use a manifest list or image index build/push strategy supported by your tooling and ACR Tasks. Do not assume a single quick task produces a multi-platform image unless the Dockerfile and runner are configured accordingly.

Verify image architecture against each runtime to prevent exec format errors during deployment.

## 11. From Image in ACR to Azure Container Apps

ACR Tasks and Azure Container Apps serve distinct responsibilities:

- **ACR Tasks:** build, tag, push, log, and automate images.
- **Azure Container Apps:** run containers, configure ingress, scaling, revisions, secrets, managed identities, and the application environment.

**Pushing a new image does not automatically mean Container Apps will roll out the new version.** An explicit deployment action or properly configured continuous deployment flow matching your model is required.

### 11.1. CI/CD Architecture Pattern

~~~mermaid
flowchart LR
    G["Git repository"] --> A["ACR Task"]
    A --> R["ACR: image + digest"]
    R --> Q["Testing, scanning, and release approval"]
    Q --> D["CD: update Azure Container App"]
    D --> V["Container App revision"]
    V --> O["Health / logs / rollback"]
~~~

In production, separate permissions:

- Build identity holds permissions needed to run tasks and push images.
- Deploy identity holds scoped permissions to update the Container App.
- Runtime identity only needs to pull images and access permitted target services.
- Approvers hold release approval authority without necessarily holding long-lived credentials.

### 11.2. Configuring Runtime Image Pulls

The Container App needs pull permissions from the registry. A common pattern uses a **managed identity** granted appropriate pull permissions on ACR. Exact permissions depend on the registry model (RBAC/ABAC) and feature version.

Illustrative configuration model (not a complete manifest):

~~~text
Container App: orders-api-prod
Registry: acrorderslab123.azurecr.io
Image: acrorderslab123.azurecr.io/orders-api:1.0.0
Identity: user-assigned or system-assigned managed identity
Registry permission: properly scoped pull
Ingress: HTTPS per policy
Secrets: Key Vault / Container Apps secret management
Environment variables: per environment
~~~

Do not use the registry's admin username/password as a default production solution when managed identity is suitable.

### 11.3. Controlled Container App Update Example

After the image is tested and approved:

~~~bash
az containerapp update \
  --resource-group rg-apps-prod \
  --name orders-api-prod \
  --image acrorderslab123.azurecr.io/orders-api:1.0.0
~~~

This command requires that the Container App already exists with registry authentication and pull permissions configured. How Container Apps creates revisions/rollouts depends on revision mode and app settings. After deploying, verify the active revision, endpoint health, logs, error rates, and traffic split if using multiple revisions.

Never treat a successful CLI update return status as sufficient proof that all requests are serving the new version.

### 11.4. Rollback

A safe rollback plan must retain:

- The image digest of the previous production release.
- That release's runtime parameters and secret references.
- Corresponding revision/traffic routing configuration.
- Backward-compatible database migrations.
- Logs, approvals, and rollback trigger criteria.

Rollback can use Container Apps revision management or update to the saved image; choose the method supported by the platform and matching your active revision mode. An overwritten old tag makes rollback hard to reproduce, which is why digests should be recorded.

## 12. Scheduling and Image Lifecycle Management

ACR accumulates artifacts over many builds. Building on every commit and every night can cause registry storage to grow rapidly.

Plan to:

- Retain approved production/staging images per retention policy.
- Tag by run/commit and record digests in release records.
- Clean up unreferenced tags or manifests via controlled workflows.
- Avoid deleting artifacts currently running in any environment or needed for rollback.
- Monitor storage usage, task runs, pull bandwidth, and costs.
- Check retention/purge features supported by ACR in your current tier.

**Deleting a tag does not always equal deleting manifest data or evicting images from running runtimes.** Garbage collection, retention, and purging behavior depend on the service. Before cleaning a registry, cross-check active deployed artifacts and security investigation needs.

In many organizations, only production-critical repositories retain artifacts long-term; experimental artifacts have shorter lifecycles. Express this through policies, owners, and audits.

## 13. Logging, Monitoring, and Build Auditing

### 13.1. Data to Record

Every task run should correlate with:

| Field | Meaning |
|---|---|
| Source repository/branch/commit | Which code was built |
| ACR task name and run ID | Which task and execution |
| Start/end time (UTC) | Execution timeframe |
| Trigger reason | Commit, base update, schedule, or manual |
| Build context/Dockerfile | Which inputs were used |
| Base image digest | Which base version was built from |
| Output image tag/digest | Which artifact was produced |
| Test/scan/signing results | Which verification checks passed |
| Builder/identity | Who executed it and with what permissions |
| Deployment/revision ID | Which environment the artifact reached |

Not every field is automatically present in ACR Tasks logs. Pipelines may need to collect and attach extra metadata in a build artifact store or release management system.

### 13.2. Common Monitoring Commands

~~~bash
# List task definitions
az acr task list \
  --registry acrorderslab123 \
  --output table

# List task runs
az acr task list-runs \
  --registry acrorderslab123 \
  --output table

# Details of a task
az acr task show \
  --registry acrorderslab123 \
  --name orders-ci \
  --output json

# Logs by run ID
az acr task logs \
  --registry acrorderslab123 \
  --run-id "<RUN_ID>"
~~~

To observe registry changes and Azure management-plane activity, use Azure Activity Log alongside ACR-supported metrics/diagnostics. Management-plane data alone does not replace full build output data or image provenance.

### 13.3. Recommended Alerts

- Consecutive build/task failures.
- No new runs despite expected source commits/triggers.
- Scheduled task missed its configured window.
- Abnormally long build durations.
- Base image updates left unaddressed past security SLAs.
- Sudden spikes in registry storage or cost.
- Access failures or registry administrative permission changes.
- Production image digest diverging from the approved artifact.

Distinguish build errors from deploy errors. A properly built new image that fails to start on Container Apps due to ports, memory limits, secrets, or configuration must be investigated at runtime, not just in ACR.

## 14. Build Cost and Performance

ACR Tasks may incur charges under current registry/task run/feature pricing models. Additionally:

- Registry SKU impacts storage capacity, throughput, networking features, and quotas.
- Frequent commits/schedules lead to more builds and more tags/manifests.
- Pulling large base images or heavy dependencies increases build duration.
- Large images lengthen runtime pulls and increase network transfer costs.
- Log ingestion, scanners, Key Vault, agent pools, or auxiliary resources may incur fees.
- Retaining many old images consumes registry storage.

### 14.1. Optimize the Dockerfile Before Upgrading SKUs

Measures to take:

1. Use multi-stage builds to strip compilers and build tools from the runtime image.
2. Order COPY/RUN instructions to leverage layer caching where supported by the builder.
3. Remove unused artifacts and dependencies.
4. Use .dockerignore to shrink context uploads.
5. Pin dependency versions and verify checksums where appropriate.
6. Use only the runtime base image needed, without increasing risk via stripped-down images lacking security patches.
7. Avoid unreliable network downloads in the Dockerfile if a controlled dependency cache solution is available.
8. Track build duration and image size across releases.

Do not assume every builder or ACR Task run always preserves layer cache between executions. Caching depends on build/task mode and infrastructure; verify with actual measurements.

### 14.2. Choosing a Build Schedule

If 50 commits are pushed per day and every commit builds a production-ready image, costs and artifact volume may exceed actual needs. You can:

- Build only on protected branches or after PR merges.
- Run fast tests on PRs and build release images at merge points.
- Use scheduled rebuilds aligned with security requirements rather than excessively often.
- Trigger base-image rebuilds aligned with scanning and policy workflows.
- Use tags/digests to promote a single artifact across dev/staging/prod instead of rebuilding per environment.

These choices must balance feedback speed and security reliability, not cost alone.

## 15. Practical Scenario: Spring Boot to Azure Container Apps

A team developing a Spring Boot orders application wants automated builds after every PR merged to main. The goal is to standardize builds and ensure images can be rolled back.

### 15.1. Proposed Workflow

1. Developer opens a PR; CI runs unit tests, static checks, and reviews.
2. PR merges to main under branch protection.
3. ACR Task triggers on commit or the pipeline invokes the task manually with an appropriate identity.
4. Task builds the multi-stage Dockerfile and tags with commit SHA/run ID.
5. Image is pushed to the registry; the system records digest, source commit, and task run.
6. Security scan/SBOM and integration tests run using chosen tools.
7. If gates pass, the pipeline updates the staging Container App to that exact approved digest.
8. QA verifies health, authentication, DB, messaging, and logs.
9. Production approval authorizes deploying the same artifact to production.
10. Azure Container Apps creates/adjusts the revision per configuration; the team monitors metrics.
11. If errors occur, roll back the revision/image and check database or background job impact.

### 15.2. Release Record Template

~~~yaml
application: orders-api
source:
  repository: "https://github.com/EXAMPLE_ORG/orders-api"
  branch: main
  commit: "<COMMIT_SHA>"
build:
  registry: acrorderslab123.azurecr.io
  task: orders-ci
  runId: "<ACR_RUN_ID>"
  dockerfile: Dockerfile
  image: "acrorderslab123.azurecr.io/orders-api:<VERSION_OR_RUN_ID>"
  digest: "sha256:<IMAGE_DIGEST>"
qualityGates:
  unitTests: passed
  vulnerabilityPolicy: passed
  sbom: recorded
release:
  environment: production
  approvedBy: "<APPROVER>"
  containerApp: orders-api-prod
  revision: "<REVISION_NAME>"
  deployedAtUtc: "<ISO_UTC_TIME>"
rollback:
  previousDigest: "sha256:<PREVIOUS_DIGEST>"
  procedure: "Use approved Container Apps revision/image rollback"
~~~

This YAML is a **metadata recording template**, not a schema meant to run directly in ACR Tasks or Azure DevOps. A passed value is only meaningful when backed by corresponding logs or test artifacts.

### 15.3. Common Failure Scenarios

**Build passes but deploy fails:** inspect revision logs, registry pull permissions, ingress ports, and secrets. Do not rush to rebuild if the image digest is already verified.

**Vulnerability discovered in image:** identify the base image and dependency, update version/digest, rebuild, scan, and release a new version. Never merely retag to mask a vulnerability.

**Commit trigger does not fire:** check webhook, branch, token, disabled task status, and run history. While remediating, you can run the task manually from an approved commit and document the reason.

**Production runs an overwritten tag:** inspect actual image digests, fix the pipeline to deploy immutable artifacts, and establish retention/rollback controls.

## 16. Troubleshooting ACR Tasks

| Symptom | Possible Cause | Investigation Direction |
|---|---|---|
| az acr build denied | Wrong subscription, registry, RBAC, or quota | az account show, registry show, role assignments, error code |
| Dockerfile not found | Wrong --file or build context | Check filename, case-sensitive path, .dockerignore |
| COPY cannot find file | File outside context or excluded by .dockerignore | Check context uploaded to ACR |
| Maven/npm build fails | Dependency, private repo, certificate, or network | Task logs, package feed access, tool version |
| Base image pull fails | Registry auth, DNS, rate limit, or wrong tag | Check FROM, registry, credentials, and network |
| Task created but Git trigger does not run | Wrong webhook/token/branch/ref or trigger setting | Task config, webhook, token scopes, list-runs |
| Base update does not trigger build | Unsupported registry/base format or incorrect tracking | Confirm trigger mechanism and use scheduled fallback |
| Scheduled task does not run | Cron, timezone, disabled task, or permissions | Check schedule config and run history |
| Push fails 401/403 | Identity lacks push/repository permission | Check role, ABAC scope, login server |
| Build finishes but tag missing | Task YAML lacks push, unexpected tag, or run failed | Inspect task logs, repositories, tags/digest |
| Image pull fails on Container Apps | Runtime identity lacks pull, bad networking or registry config | Check managed identity, roles, and Container App logs |
| Container App has new image but runs old code | Wrong revision deployed, runtime cache, or overwritten tag | Check active revision and actual digest |
| Build too slow | Huge context, dependency downloads, poor Dockerfile layer cache | Measure size, Dockerfile, network, and duration |
| Registry full or costs rising | Retaining too many images, unclear retention | Registry usage, tags/manifests, cleanup policy |
| Security scan does not run | Scanner/gate unconfigured, missing license or task step | Check pipeline/defender plan and job logs |

### 16.1. Ordered Troubleshooting Approach

1. **Azure account:** correct subscription, tenant, and resource group?
2. **Registry:** exists and supports the features being used?
3. **Task definition:** correct context, branch, Dockerfile, image tag, and trigger?
4. **Source access:** do tokens/webhooks and network access to read the repo work?
5. **Builder:** do logs show dependency, base image, CPU/memory, or Dockerfile errors?
6. **Output:** did the run succeed and did the image manifest/tag/digest appear?
7. **Security:** did scanning/signing/approval finish?
8. **Deployment:** was Container Apps updated to the new image digest/revision?
9. **Runtime:** are health, auth, networking, database, startup, and logs passing?

If a build fails, do not grant subscription-wide Owner or enable the registry admin account as a first resort. Diagnose the permission error at the exact scope and grant only the minimum required role.

## 17. Production Deployment Checklist

### Before Creating Tasks

- [ ] Registry SKU/region/quota and network policies are appropriate.
- [ ] Source repository/branch and Dockerfile are governed by code review.
- [ ] .dockerignore is present; no secrets enter the context.
- [ ] Tag/digest strategy and retention policy are defined.
- [ ] Identities for task management, image push, and runtime pull are separated.
- [ ] Git/webhook credentials are secured and rotated.
- [ ] Base image update plan and appropriate rebuild schedule exist.
- [ ] Baselines exist for build duration, image size, and budget.

### During Build and Verification

- [ ] Task runs record ID, commit SHA, and trigger reason.
- [ ] Logs do not expose secrets.
- [ ] Unit/integration tests pass.
- [ ] Base image and dependency provenance are recorded.
- [ ] Vulnerability scan/SBOM/signing run if required by policy.
- [ ] Image digest is recorded after push.
- [ ] Runtime tested with the built image, verifying ports and health endpoints.

### Before and After Deployment

- [ ] CD uses approved images without uncontrolled rebuilds.
- [ ] Container App or runtime platform holds least-privilege pull identity.
- [ ] Runtime secrets are not embedded inside the Docker image.
- [ ] Approval gate exists before production release.
- [ ] Monitor revisions/image digests, error rates, latency, and logs.
- [ ] Image/revision and data rollback plans are in place.
- [ ] Artifacts required for rollback have not been purged by cleanup policies.

## 18. Self-Check Questions

1. **How do ACR and ACR Tasks differ?** ACR stores/distributes images; ACR Tasks executes and automates builds/steps on managed infrastructure.
2. **Does a quick task require a local Docker daemon?** Usually no; az acr build uploads the context to the build service from Azure CLI.
3. **How does a named task differ from a task run?** A task is the definition; a run is one specific execution.
4. **Why not use only the latest tag in production?** Tags can be reassigned; digests identify exact artifacts.
5. **What conditions does a commit trigger depend on?** Repository/ref, webhook or provider integration, credentials/permissions, and the task being enabled.
6. **Does a base image update automatically patch CVEs in running containers?** No. You must rebuild and deploy a new artifact.
7. **Must a scheduled task immediately deploy to production?** No. Building and releasing are two separate workflows.
8. **Does ACR Tasks automatically scan and sign every image?** No. Appropriate tools, steps, and policies must be configured.
9. **Is a Dockerfile with ARG SECRET followed by RUN echo safe?** No. Secrets can leak through build logs, layers, and metadata.
10. **What permissions should be granted to Container Apps that only pull images?** Appropriate registry/repository pull permissions via a supported identity, not broad administrative rights.
11. **What does recording the image digest help with?** Traceability, redeployment, and rolling back to an exact artifact.
12. **Does a successful build mean the application will run properly?** No. Runtime behavior, health probes, network ports, secrets, and dependencies must still be tested.
13. **Does changing an image tag in ACR make Container Apps automatically roll out?** Not by default; an explicit deploy action or configured continuous deployment is needed.
14. **If a task fails to trigger from Git, what should you check?** Webhook, branch/ref, token, trigger enabled status, and task run history.
15. **When using private networking for a registry, do you need to check its impact on builders?** Yes. Task runners must have appropriate connectivity to the registry, sources, and base images.
16. **What is the benefit of building once and deploying across multiple environments?** Reduces artifact drift and helps prove the exact same tested image digest runs everywhere.
17. **Why must retention policies account for rollbacks?** Deleting old images too soon can make restoring a previous version impossible.

## 19. References

- [Azure Container Registry documentation](https://learn.microsoft.com/azure/container-registry/) — managing registries, repositories, images, and security.
- [ACR Tasks overview](https://learn.microsoft.com/azure/container-registry/container-registry-tasks-overview) — quick tasks, automation, and triggers.
- [Build and push images with ACR Tasks](https://learn.microsoft.com/azure/container-registry/container-registry-quickstart-task-cli) — quick builds and CLI tasks.
- [Automate image builds with ACR Tasks](https://learn.microsoft.com/azure/container-registry/container-registry-tutorial-build-task) — source-based task configuration and automation.
- [Multi-step ACR Tasks](https://learn.microsoft.com/azure/container-registry/container-registry-tasks-multi-step) — YAML syntax, steps, and task execution.
- [Automated base image updates](https://learn.microsoft.com/azure/container-registry/container-registry-tasks-base-images) — base image tracking and rebuilds.
- [Azure Container Registry authentication](https://learn.microsoft.com/azure/container-registry/container-registry-authentication) — identity and access permission options.
- [Azure Container Apps documentation](https://learn.microsoft.com/azure/container-apps/) — running images, revisions, ingress, scaling, and governance.
- [Azure Cost Management](https://learn.microsoft.com/azure/cost-management-billing/costs/) — tracking costs by resource and workload.

**Conclusion:** ACR Tasks helps standardize and automate container image builds via quick builds, Git-triggered tasks, base-image updates, schedules, and multi-step workflows. A reliable pipeline must tightly manage **source commit → build run → image digest → testing/security → approval → deployment/revision**. To deploy securely on Azure, use least-privilege identities, keep secrets out of images, separate builds from production releases, monitor logs and costs, and always retain artifacts needed for rollback.
