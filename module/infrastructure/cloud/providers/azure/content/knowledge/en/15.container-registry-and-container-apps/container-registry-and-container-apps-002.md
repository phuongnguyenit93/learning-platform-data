# Azure Container Registry, Repositories, and Image Tags

## 1. Context: How Are Container Applications Stored and Deployed?

In Azure, a Java, Node.js, or Python application can be packaged into a **container image** and run on Azure Container Apps, Azure Kubernetes Service (AKS), or another suitable container environment. However, an image should not exist only on a developer's laptop: the CI/CD system needs a place to push the image, the staging environment needs to download the exact tested version, and production needs to know precisely which artifact is running.

**Azure Container Registry (ACR)** is a managed registry service on Azure used to store and distribute container images and certain OCI-compliant artifacts. In the Azure ecosystem module, ACR connects the development workflow with subscriptions, resource groups, Microsoft Entra ID, networking, application deployment, monitoring, security, and cost control.

For example, a development team has a Java API named **orders-api**:

1. Build the application into a JAR file.
2. Build a Docker image from the JAR.
3. Push the image to Azure Container Registry.
4. Apply a version tag, for example **1.4.0**.
5. Configure Azure Container Apps to use the tested image.
6. When a bug fix is needed, create a new version or roll back to the exact previously deployed image.

These steps seem straightforward, yet they involve several easily confused concepts: **registry**, **repository**, **tag**, **manifest**, **digest**, push/pull permissions, and the fact that tags can change targets.

### Lesson Objectives

After this lesson, you will be able to:

- Explain the role of Azure Container Registry in the application deployment workflow.
- Distinguish between registry, repository, image, layer, manifest, tag, and digest.
- Correctly read an image reference containing hostname, repository path, and version.
- Create an ACR, log in, build, tag, push, pull, and inspect images using Docker and Azure CLI.
- Understand why using the **latest** tag or overwriting tags can cause discrepancies across environments.
- Design a release workflow based on image digests to improve reproducibility and rollback capability.
- Assign permissions to users or workloads using Microsoft Entra ID, managed identities, and appropriate RBAC mechanisms.
- Connect ACR to Azure Container Apps, AKS, or container hosting services without exposing credentials.
- Troubleshoot authentication, image name/tag, DNS, network, and platform errors.
- Account for image lifecycle management, security scanning, logging, and registry costs.

## 2. Where Do Registry, Repository, and Image Differ?

There are three primary levels to distinguish:

| Component | Meaning | Example |
|---|---|---|
| **Registry** | Service storing multiple repositories and artifacts | **acrlabexample.azurecr.io** |
| **Repository** | Logical name grouping multiple image versions of the same product or component | **apps/orders-api** |
| **Image** | Artifact containing filesystem layers, runtime configuration, and metadata to create containers | Image for orders-api |
| **Tag** | Human-readable reference name pointing to an image manifest | **1.4.0**, **staging**, **latest** |
| **Digest** | Content-hash identifier of a manifest or image index | **sha256:...** |

A registry can contain multiple repositories:

~~~text
acrlabexample.azurecr.io
├── apps/orders-api
│   ├── 1.3.0
│   ├── 1.4.0
│   └── release-2026-11
├── apps/customer-api
│   ├── 2.0.0
│   └── 2.1.0
└── workers/image-processor
    ├── 0.8.1
    └── 0.9.0
~~~

The lines **1.3.0**, **1.4.0**, or **0.9.0** represent **tags**, not independent directories holding full copies of the entire image. Multiple tags can point to the same manifest, and images can share identical layers.

**A repository is not an Azure resource group or an operating system directory.** A name like **apps/orders-api** creates a logical path inside the registry; it does not automatically create resource groups or a new authorization boundary. Repository-scoped permissions only exist when using an authorization model and features supported by ACR.

## 3. Full Structure of an Image Reference

An image is referenced through the registry hostname, repository name, and tag or digest:

~~~text
<registry-login-server>/<repository>:<tag>
~~~

Example:

~~~text
acrlabexample.azurecr.io/apps/orders-api:1.4.0
~~~

Breakdown:

| Segment | Example Value | Role |
|---|---|---|
| Registry login server | acrlabexample.azurecr.io | Registry holding the artifact |
| Repository path | apps/orders-api | Logical name of the application |
| Tag | 1.4.0 | Human-readable version label |

An image can also be referenced by **digest**:

~~~text
acrlabexample.azurecr.io/apps/orders-api@sha256:<manifest-digest>
~~~

In a digest-based image reference, the **sha256:** portion must be the actual hash string provided by the registry. Do not use placeholders when deploying.

### 3.1. What Happens If No Tag Is Specified?

Under common Docker behavior, an image reference without a tag may be interpreted with the default tag **latest**. This is convenient for experimentation but introduces risk: **latest does not prove it is the newest build by date, commit, or business version**. It is merely a tag name that can be changed by anyone with permission.

For staging and production, you should **specify tags explicitly**, or better yet, deploy by **digest** if the target tool supports it.

### 3.2. Registry Name and Login Server

When creating an ACR, you choose a registry name meeting Azure's naming and uniqueness rules. Azure provides a login server typically formatted as:

~~~text
<registry-name>.azurecr.io
~~~

However, in environments with custom domains or special DNS configurations, always retrieve **loginServer** from the registry resource instead of manually concatenating the name during deployment.

## 4. How Is a Container Image Structured?

A container image typically consists of multiple **filesystem layers**, runtime configuration, and a **manifest** describing the components required for the runtime to load the image.

~~~mermaid
flowchart TD
    SRC[Source code and Dockerfile] --> BUILD[Container build]
    BUILD --> L[Filesystem layers]
    BUILD --> CFG[Image configuration]
    L --> MAN[Image manifest]
    CFG --> MAN
    MAN --> REG[Azure Container Registry]
    REG --> TAG[Tag: 1.4.0]
    REG --> DIGEST[Digest: sha256...]
    TAG --> DEPLOY[Container App / AKS]
    DIGEST --> DEPLOY
~~~

An image can be built using a Dockerfile, BuildKit, OCI builder tools, or build services on Azure. When pushing, the client uploads the required layers and manifest to the registry; layers that already exist may not need to be re-uploaded.

**A container image is not a running container.** An image is an artifact stored in a registry; a container is a process instantiated from the image in a runtime environment. Deleting an image from a registry does not immediately stop running containers; however, the next pull, scale-out, or redeploy may fail if the image no longer exists.

### 4.1. Multi-Platform Images

Some images support multiple architectures, such as **linux/amd64** and **linux/arm64**. In that case, a reference may point to an **image index/manifest list** containing multiple child manifests for each platform.

Therefore, distinguish between:

- The digest of the **image index** covering the set of platforms.
- The digest of a **specific manifest** for a single platform.
- The CPU architecture and operating system of the machine running the container.

In deployments, verify that the image supports the exact platform used by Azure Container Apps, the AKS node pool, or the target host. A tag existing in the registry that only holds an **arm64** image may fail to run in an **amd64**-only environment.

## 5. Tags: Readable Names, Not Automatically Immutable

**Tags** help humans distinguish image versions:

~~~text
apps/orders-api:1.4.0
apps/orders-api:1.4.1
apps/orders-api:main-4f2c91a
apps/orders-api:latest
~~~

However, under the standard registry model, a tag can be **re-pointed** to a different manifest when someone with push permissions pushes the same tag name.

Example:

~~~text
Monday:
  apps/orders-api:1.4.0 -> digest AAA...

Wednesday (someone overwrites the same tag):
  apps/orders-api:1.4.0 -> digest BBB...
~~~

If staging pulled digest AAA, while production pulls tag 1.4.0 on Wednesday, the two environments can run **two different contents despite displaying the same tag**. This is a serious issue for traceability and rollback capability.

### 5.1. A Tag Is Not a Copy of the Image

Adding another tag usually only creates a new reference. It does not automatically duplicate all layers.

### 5.2. Avoid Using latest as Proof of Release

The **latest** tag has no enforced rule requiring it to point to the newest build. If used in dev, you must clearly understand who updates it and when. For production, do not rely on latest as proof of the running version.

### 5.3. When Should Version Tags Be Used?

Tags like **1.4.0** are useful for reading and cross-referencing with release notes. Tags containing a commit SHA help trace an image back to source code. Both can be combined as long as they are not arbitrarily overwritten and the digest is still recorded.

## 6. Digest: Referencing Exact Image Content

A **digest** is the content hash of a manifest or image index under the OCI/Docker distribution specification, typically displayed with the **sha256:** prefix.

Example:

~~~text
acrlabexample.azurecr.io/apps/orders-api@sha256:<64-hex-character-value>
~~~

When referencing an actual digest, the runtime requests the exact manifest/index carrying that hash. If a tag is later moved to another manifest, the old digest **does not change**.

| Comparison | Tag | Digest |
|---|---|---|
| Human readability | High | Low |
| Can be reassigned | Yes, if not locked or controlled | Content is identified by hash |
| Suitable for recording release version | Yes | Should be recorded alongside |
| Supports reproducible deploys | Insufficient if tag can change | Stronger, as long as artifact remains |
| Can point to multiple platforms | Yes | Yes, if digest is an image index |
| Guarantees artifact is never deleted | No | No |

**A digest is immutable as a content identifier, which does not mean the artifact exists forever.** If the manifest and layers are deleted under retention policies, digest-based deployments cannot pull successfully either.

**Recommendation:** the pipeline builds the image once, captures the digest after pushing, and promotes that exact digest through test, staging, and production. Do not rebuild from source in each environment and assume the results are identical.

## 7. Choosing a Repository Structure and Tagging Strategy

Suppose an organization has three Java services:

~~~text
acrlabexample.azurecr.io/commerce/orders-api:1.4.0
acrlabexample.azurecr.io/commerce/payments-api:2.2.1
acrlabexample.azurecr.io/workers/invoice-exporter:0.9.3
~~~

Good naming conventions should include:

- Consistent application names across repositories, source code, and deployments.
- Meaningful repository paths organized by team/product.
- Clear version tags, optionally attaching commit hashes or build IDs.
- Naming rules compatible with Docker/OCI registries.
- Separate authorization and lifecycle mechanisms if teams have different sensitivity levels.

### 7.1. One Repository for Multiple Versions of the Same Application

This is typically the easiest model to operate:

~~~text
commerce/orders-api
  1.4.0
  1.4.1
  1.5.0
~~~

### 7.2. Should Separate Repositories Be Created for Dev/Prod?

There is no universal answer. You can:

- Use a single repository, build one image, and **promote by digest** across environments.
- Use separate registries for production and non-production to isolate permission/network boundaries and costs.
- Use separate repositories per team if genuine authorization requirements exist and the feature is supported.

Do not duplicate or rebuild an image merely to assign a different name if the goal is to verify the same artifact. When registry separation is needed, you can copy/import the artifact via an appropriate ACR mechanism and verify the digest/manifest.

## 8. Azure Container Registry SKUs

ACR offers common service tiers such as **Basic**, **Standard**, and **Premium**. They differ in limits, performance, storage capacity, networking features, and resiliency.

| SKU | General Orientation | Considerations |
|---|---|---|
| **Basic** | Learning and workloads with small registry needs | Fewer capabilities or advanced features |
| **Standard** | Higher registry needs for scale and throughput | Suits many typical CI/CD workflows |
| **Premium** | Organizations needing advanced features | Consider private endpoints, geo-replication, and features depending on current support |

Specific parameters such as storage, pull/push throughput, webhooks, retention, network restrictions, geo-replication, or security may vary by SKU and region. Before selecting, consult the current Azure feature support matrix and pricing page.

### 8.1. When Is Geo-Replication Needed?

An organization running applications across multiple Azure regions may want images distributed close to where workloads run to reduce pull latency and improve availability options. **ACR geo-replication** is a feature to consider in supported SKUs, typically associated with Premium.

However, replicating a registry **does not automatically deploy or route multi-region application traffic**. Azure Container Apps/AKS, networking, data, and failover mechanisms must be designed separately.

### 8.2. When Is a Private Endpoint Needed?

If policy requires accessing the registry over a private network, verify the SKU's **Private Link/private endpoint** support and DNS/routing reachability everywhere images are pushed/pulled, including CI runners, AKS nodes, and Container Apps environments. A private endpoint does not automatically create network connectivity for a machine outside the VNet.

## 9. Preparing an ACR Lab Environment

The examples use Bash with Azure CLI and Docker. They are hands-on guides only and are not executed directly within the lesson.

Prerequisites:

1. An Azure subscription permitted to create resources.
2. Permission to create an Azure Container Registry in a test resource group.
3. Azure CLI and Docker CLI/engine installed, or an equivalent build tool.
4. Signed in with an identity having appropriate push/pull permissions.
5. A unique ACR name and awareness of registry costs.
6. Test source code and Dockerfile; do not use real secrets or customer data.
7. Knowledge of how to inspect and properly delete lab resources upon completion.

Examples use:

~~~text
Resource group: rg-acr-lab
Registry name: acrlabunique12345
Repository: apps/orders-api
Tag: 1.0.0
~~~

**The registry name is an example** and is not guaranteed to be available. Replace **acrlabunique12345** with a unique name you own. Registry names have specific character and length rules; do not arbitrarily insert hyphens and assume Azure will accept them.

## 10. Creating an Azure Container Registry with Azure CLI

Sign in to Azure and select the subscription:

~~~bash
az login
az account set --subscription "<subscription-id>"
~~~

Create the resource group and registry:

~~~bash
az group create \
  --name rg-acr-lab \
  --location southeastasia

az acr create \
  --resource-group rg-acr-lab \
  --name acrlabunique12345 \
  --sku Basic \
  --admin-enabled false
~~~

In the example, **admin-enabled false** expresses the intent not to use the registry's shared administrator account as the default method.

View registry information:

~~~bash
az acr show \
  --name acrlabunique12345 \
  --query "{name:name,loginServer:loginServer,sku:sku.name,adminUserEnabled:adminUserEnabled}" \
  --output json
~~~

Retrieve the login server:

~~~bash
ACR_NAME="acrlabunique12345"
ACR_LOGIN_SERVER="$(az acr show --name "$ACR_NAME" --query loginServer --output tsv)"
echo "$ACR_LOGIN_SERVER"
~~~

Expected output looks like:

~~~text
acrlabunique12345.azurecr.io
~~~

A registry is an Azure resource that can be governed by Azure RBAC and organizational policies. **Creating a registry does not automatically create a repository.** A repository typically appears once an image is successfully pushed or imported.

## 11. Registry Sign-In and Distinguishing Azure Login from Docker Login

Two systems are involved:

- **az login**: authenticates Azure CLI with Microsoft Entra ID.
- **az acr login**: obtains credentials/tokens allowing the Docker client to interact with Azure Container Registry using the active identity and permissions.

Example:

~~~bash
az acr login --name "$ACR_NAME"
~~~

This command typically integrates with the local Docker CLI/daemon on the development machine. If the Docker engine is not running, a standard login may fail even when Azure CLI is validly signed in.

When no Docker daemon is present but a token is needed for a compatible tool, Azure CLI offers an appropriate option:

~~~bash
az acr login --name "$ACR_NAME" --expose-token
~~~

This option returns a token and related details; **the token is still a sensitive credential**. Never output token contents into public CI logs, documentation, or chat. Use authentication methods supported by your build/deploy tooling.

**A successful login does not prove the account has push permission.** The identity may only hold pull permissions or lack repository data-plane permissions. When denied, inspect authorization settings and the registry's permission mode.

## 12. Dockerfile Example Packaging a Java Application

Suppose Maven has produced **target/orders-api.jar** and the application listens for HTTP on port 8080. A simple Dockerfile:

~~~dockerfile
FROM eclipse-temurin:21-jre

WORKDIR /app

COPY target/orders-api.jar /app/orders-api.jar

USER 10001

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/orders-api.jar"]
~~~

Explanation:

- **FROM** selects the base runtime image with Java.
- **WORKDIR** sets the working directory.
- **COPY** places the built artifact into the image.
- **USER 10001** runs the process under a non-root UID, provided application permissions allow it.
- **EXPOSE 8080** documents the port the application uses; it does not automatically open a public port.
- **ENTRYPOINT** declares the process executed when the container starts.

This is a learning example. In production, you should:

- Pin the base image by tested version or digest.
- Use a multi-stage build where appropriate.
- Minimize unnecessary packages.
- Run as a non-root user and verify log/temp write permissions.
- Never include **.env** files, credentials, or private keys in the image context.
- Use **.dockerignore** to exclude unneeded directories, secret files, and redundant build data.
- Scan dependencies and images before release.

If the JAR has not been built or has a different filename, the Docker build will fail at the COPY step; you must build the application first.

## 13. Building an Image Locally

From the directory containing the Dockerfile and JAR artifact:

~~~bash
docker build \
  -t orders-api:1.0.0 \
  .
~~~

Check the image list:

~~~bash
docker image ls
~~~

Run a test container locally:

~~~bash
docker run --rm \
  --name orders-api-test \
  -p 8080:8080 \
  orders-api:1.0.0
~~~

Open another terminal to test the actual API, for example:

~~~bash
curl -i http://127.0.0.1:8080/health
~~~

The **/health** path only exists if the application implements that endpoint. Otherwise, test with an endpoint the application actually provides.

Testing functionality before pushing prevents storing a broken image in the registry, yet **local testing does not replace testing on Container Apps/AKS** because networking, identities, CPU architecture, and resource limits may differ.

## 14. Docker Tag: Naming an Image for Pushing to ACR

The initial local image is named:

~~~text
orders-api:1.0.0
~~~

To push to the registry, attach the full name:

~~~bash
docker tag \
  orders-api:1.0.0 \
  "$ACR_LOGIN_SERVER/apps/orders-api:1.0.0"
~~~

Verify:

~~~bash
docker image ls
~~~

**docker tag does not upload the image.** It only creates an additional local image reference. Afterward, the image may appear under both **orders-api:1.0.0** and **acrlabunique12345.azurecr.io/apps/orders-api:1.0.0** in the local image list.

When users see a new Docker tag created locally while the Azure Portal does not show a repository yet, the usual cause is **not having run push yet**.

## 15. Docker Push: Uploading Image and Manifest to ACR

Once signed in to ACR with an identity that has push permissions:

~~~bash
docker push "$ACR_LOGIN_SERVER/apps/orders-api:1.0.0"
~~~

The Docker/OCI client checks which layers need uploading, pushes missing layers, and writes the manifest/tag to the registry.

After a successful push:

- The registry contains the **apps/orders-api** repository.
- Tag **1.0.0** is attached to the corresponding manifest.
- Azure Container Apps/AKS or other Docker clients can pull if they have appropriate permissions and network connectivity.
- The registry can share duplicate layers, so it does not necessarily store a full copy for every tag.

If **denied / unauthorized** is returned, do not immediately enable the registry admin account. Check Azure login, data-plane RBAC, repository permission mode, exact registry name, and push rights.

If a network error occurs, check DNS, proxy/firewall, private endpoint setup, and the registry endpoint; authorization and networking are two distinct error categories.

## 16. Inspecting Repositories and Image Tags with Azure CLI

List repositories:

~~~bash
az acr repository list \
  --name "$ACR_NAME" \
  --output table
~~~

List tags of a repository:

~~~bash
az acr repository show-tags \
  --name "$ACR_NAME" \
  --repository apps/orders-api \
  --orderby time_desc \
  --detail \
  --output table
~~~

Inspect an image's metadata by tag:

~~~bash
az acr repository show \
  --name "$ACR_NAME" \
  --image apps/orders-api:1.0.0 \
  --output json
~~~

Retrieve the digest from metadata if the field is available in the CLI/API version in use:

~~~bash
az acr repository show \
  --name "$ACR_NAME" \
  --image apps/orders-api:1.0.0 \
  --query digest \
  --output tsv
~~~

**Note:** CLI and ACR API commands or metadata fields may change across versions. If a command is marked deprecated or does not display expected data, use the manifest/repository commands supported by the current Azure CLI. Never guess a digest from a Docker image ID, as the image ID, manifest digest, and multi-platform index digest can differ.

Inspect in the Portal: go to **Azure Container Registry → Repositories** and select **apps/orders-api** to view tags, digests, and available metadata.

## 17. Pulling an Image from Another Machine or Environment

On an authorized machine:

~~~bash
az login
az acr login --name acrlabunique12345

docker pull \
  acrlabunique12345.azurecr.io/apps/orders-api:1.0.0
~~~

Run the image with appropriate environment configuration if needed:

~~~bash
docker run --rm \
  -p 8080:8080 \
  acrlabunique12345.azurecr.io/apps/orders-api:1.0.0
~~~

When pulling, the Docker client resolves the manifest from the tag and downloads required layers. If the image already exists in local cache, caching and refresh behavior depend on the command/runtime. Therefore, do not assume changing the content of a tag will update all running containers.

A deployment must **explicitly update revisions/pods/containers** via the service's mechanism. Pushing a new image to ACR does not automatically restart every container using that tag.

## 18. Building on Azure with ACR Tasks

Besides building with Docker on a laptop, ACR supports building images in a managed environment, commonly via **ACR Tasks**. With valid source code and a Dockerfile:

~~~bash
az acr build \
  --registry "$ACR_NAME" \
  --image apps/orders-api:1.0.0 \
  .
~~~

This command sends the appropriate build context to build on Azure, reducing reliance on a local Docker daemon for the build step per the service's mechanism.

Keep in mind:

- The build context may include unwanted files if **.dockerignore** is missing.
- If the Dockerfile expects **target/orders-api.jar**, the JAR must exist in the context beforehand or a multi-stage Dockerfile with a build step must be used.
- Builds still consume resources and may incur costs depending on ACR configuration/features.
- A successful build does not replace application testing or image scanning.
- If the source contains secrets or sensitive data, do not send them in the build context.

ACR Tasks also offers build/trigger automation capabilities within the scope supported by the SKU and configuration. For larger projects, designate one clear system responsible for building artifacts so two pipelines do not overwrite the same release tag.

## 19. Authentication and Authorization with Azure Container Registry

A secure system separates three roles:

1. **Build pipeline**: allowed to push images for the product.
2. **Runtime** (Container Apps, AKS, VM): only needs permission to pull images.
3. **Administrator**: manages registry configuration, networking, and policies.

### 19.1. Microsoft Entra ID and Azure RBAC

ACR integrates with Microsoft Entra ID and Azure role assignments. For registries using standard RBAC, familiar roles include:

- **AcrPull**: read/pull artifacts within the granted scope.
- **AcrPush**: push and perform related data operations within the granted scope.
- Registry administrative tasks require separate management roles tailored to the duty.

When using the **repository permissions/ABAC** mode supported by ACR, the model and corresponding role names may differ, such as repository-scoped reader/writer permissions. **Do not assume AcrPull/AcrPush behave identically across every registry authorization mode.** Before granting access, verify the registry's permission mode and supported roles.

### 19.2. Using Managed Identity to Pull

For Azure Container Apps, AKS, or supported Azure workloads, consider **managed identity** to avoid hardcoding Docker passwords or admin credentials.

Conceptual workflow:

1. Create or enable an identity for the workload.
2. Identify the identity principal ID and exact registry scope.
3. Grant **pull** permission according to the RBAC or repository authorization model the registry uses.
4. Configure the workload to use the identity when authenticating to ACR.
5. Verify networking/DNS and pull the image using that identity.
6. Allow time for role assignment propagation when needed.

Example creating a role assignment for a registry using standard RBAC, once actual values are known:

~~~bash
az role assignment create \
  --assignee-object-id "<workload-principal-object-id>" \
  --assignee-principal-type ServicePrincipal \
  --role AcrPull \
  --scope "<acr-resource-id>"
~~~

**The example above does not apply verbatim to all repository ABAC modes.** Choose the exact role and scope matching the registry's configuration.

### 19.3. Should the ACR Admin User Be Enabled?

The ACR admin account is a shared credential with broad permissions and is not tied to accountability for an individual workload. Enable it only for special, approved needs with adequate safeguards. Never use it as a default workaround just to bypass a temporary permission error.

If credentials must be used, store them in a secret manager, keep them out of Dockerfiles/source code, and establish a rotation process.

## 20. Connecting ACR to Azure Container Apps

**Azure Container Apps** can run container images stored in ACR. Connection flow:

~~~mermaid
flowchart LR
    DEV[Developer commit] --> CI[CI build/test]
    CI --> REG[Azure Container Registry]
    REG --> REPO[apps/orders-api:1.0.0]
    REPO --> APP[Azure Container App revision]
    ID[Managed identity and pull permissions] --> APP
    APP --> MON[Logs and metrics]
~~~

### 20.1. Prerequisites

- An Azure Container App or Container Apps environment deployed and properly configured.
- Image successfully pushed to the registry.
- Runtime identity/credential has pull permissions.
- Runtime has network connectivity and DNS resolution to the ACR login server/endpoints.
- Image has a supported architecture/OS.
- Application port and ingress are properly configured.
- Application secrets/connection strings are passed via secure configuration mechanisms.

### 20.2. Updating the Image

Once the app has registry authentication configured, the image can be updated with a reference command:

~~~bash
az containerapp update \
  --name orders-api \
  --resource-group rg-containerapps \
  --image acrlabunique12345.azurecr.io/apps/orders-api:1.0.0
~~~

This illustrative command **only swaps the image** and assumes the Container App already exists with valid pull authentication configured. Do not treat it as a complete procedure for creating the registry/identity/Container Apps environment.

After updating:

1. Check the revision and deployment status.
2. Inspect app logs.
3. Verify readiness/startup and business endpoints.
4. Confirm the actual image/digest used in the revision if the environment exposes that information.
5. Keep a rollback plan back to a tested release.

**Pushing to ACR does not mean Container Apps automatically updates.** The service requires an explicit, versioned, and tested deployment process.

## 21. Connecting ACR to Azure Kubernetes Service and VMs

In AKS, each node must fetch container images per pod specifications. If the ACR is private, the cluster must have appropriate pull permissions configured via a supported method.

Partial Kubernetes Deployment configuration example:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
        - name: orders-api
          image: acrlabunique12345.azurecr.io/apps/orders-api:1.0.0
          ports:
            - containerPort: 8080
~~~

This is a manifest structure example and **does not automatically grant pull permissions**. The AKS node/kubelet identity or a supported registry authentication mechanism must be able to access ACR. For registries with repository ABAC, review the appropriate integration and role assignment approach.

On a standard Docker VM, the Docker client/daemon can log in and pull using provided credentials. However, storing long-lived credentials on a VM increases risk; an appropriate identity and secret management solution is required.

## 22. CI/CD: Build Once, Deploy the Same Artifact

A production pipeline should guarantee that the image tested in staging is the exact same image used in production.

~~~mermaid
flowchart TD
    GIT[Source commit] --> TEST[Unit tests and static checks]
    TEST --> BUILD[Build image]
    BUILD --> SCAN[Scan, SBOM, policy checks]
    SCAN --> PUSH[Push to ACR]
    PUSH --> DIGEST[Read digest]
    DIGEST --> STAGE[Deploy staging by digest]
    STAGE --> VERIFY[Integration/E2E test]
    VERIFY --> APPROVE{Approval?}
    APPROVE -->|Yes| PROD[Promote exact digest to production]
    APPROVE -->|No| STOP[Do not release]
    PROD --> OBS[Monitoring and rollback plan]
~~~

### 22.1. Why Not Rebuild in Production?

Two builds from the same source code can still differ because:

- The base image tag changed.
- Dependencies were not version-locked.
- Timestamps or build metadata differ.
- Build tools pulled from non-deterministic resources.
- Compiler/package repositories released newer versions.

Therefore, **build once**, push one artifact, record the digest, and redeploy that exact artifact. If two separate registries are required, perform a verified promotion/copy rather than rebuilding.

### 22.2. Suggested Release Metadata

| Information | Example |
|---|---|
| Git commit | 4f2c91a... |
| Build ID | ci-20261120-142 |
| Repository | apps/orders-api |
| Human-readable tag | 1.4.0 |
| Immutable reference | sha256:... |
| Base image digest | sha256:... |
| SBOM/scan status | Passed per policy |
| Deployed environment | staging then production |
| Approval | Change request or release review |

Ensure you can trace back **from a running container to its image digest, pipeline run, and source commit**.

## 23. Image Tagging Strategies for Environments

Some teams use tags like **dev**, **staging**, and **prod** as moving pointers following releases. This is convenient, yet risky if a tag is overwritten without deployments clearly updating.

### Option A — Immutable Release Tags

~~~text
apps/orders-api:1.4.0
apps/orders-api:1.4.1
apps/orders-api:1.5.0
~~~

Each release tag points only to one approved content. This can be enforced through pipeline controls and tag/manifest locking capabilities supported by the registry.

### Option B — Commit Tags

~~~text
apps/orders-api:git-4f2c91a
apps/orders-api:git-a3b9d20
~~~

Useful for tracing source code. However, using only a short SHA may not suffice to prove a unique artifact if the pipeline rebuilds multiple times; still record the digest.

### Option C — Environment Pointer Tags

~~~text
apps/orders-api:dev
apps/orders-api:staging
apps/orders-api:prod
~~~

These are **mutable/moving** tags. If used, strictly control who updates them and when, and store release manifests/digests. Never use them as the sole source of truth for production content.

### Choice

**Prefer a non-overwritten release tag + recorded digest.** For sensitive workloads, deploy by digest and use tags for human communication.

## 24. Locking Tags and Protecting Release Images

Certain ACR capabilities support configuring manifest/tag attributes, such as restricting overwrites or deletions. However, specifics and locking scope depend on feature support and CLI version.

Concepts to distinguish:

- **Prevent overwrite**: keeps released tags/manifests from unintended modification.
- **Prevent delete**: avoids deleting an artifact still referenced by production.
- **Retention**: cleans up unneeded artifacts according to policy.
- **RBAC/ABAC**: restricts who can create, write, delete, or read within the registry.

Locking does not replace identity or image-source controls. If a build pipeline has overly broad permissions, it can still pose risks across other repositories.

Before deleting or locking a manifest, check:

1. Are any revisions/pods currently referencing the image/tag/digest?
2. Do DR or rollback systems need this artifact?
3. Does another registry already hold a verified copy?
4. Do other tags point to the same digest?
5. How long do retention and audit policies require keeping it?

## 25. Cleanup: Managing Repository and Image Lifecycles

When pipelines produce hundreds of tags weekly, registries can accumulate unused image manifests and layers.

A safe cleanup workflow:

1. Categorize **release**, **rollback**, **dev/test**, and **untagged artifacts**.
2. Define distinct retention durations for each group.
3. Cross-check versions currently deployed across staging, production, and DR.
4. Delete only images genuinely no longer referenced.
5. Test restoring an older release after cleanup.
6. Monitor storage usage and cost before/after.
7. Log deletion actions per organizational procedures.

ACR provides mechanisms supporting cleanup/retention in certain configurations and SKUs. Do not assume every automated cleanup policy behaves identically for **tagged**, **untagged**, **locked**, or **multi-platform images**.

**Warning:** deleting a tag or manifest from ACR can cause subsequent deployments to fail with **manifest unknown** or **not found**. Never test deletion commands on a production registry without verification.

## 26. Container Supply Chain Security

The registry is the artifact distribution hub, so treat it as part of **software supply chain security**.

### 26.1. Only Admit Trusted Images into the Registry

- Pin base images by tested version/digest.
- Verify provenance of base images.
- Scan dependencies and known vulnerabilities.
- Minimize image layers and unnecessary software.
- Use an SBOM (Software Bill of Materials) when required.
- Consider signing/attestation and pre-deployment verification where supported by the platform.
- Never upload secrets, private keys, or .env files into an image.

**Deleting a secret in a later layer does not guarantee the secret disappears from layer history.** Exclude secrets from the build context and use proper secret mechanisms in the build pipeline.

### 26.2. Separating Push and Pull Permissions

Build identities typically need scoped write permissions; runtime identities only need read permissions. A pipeline for the orders-api team should not automatically have permission to overwrite payments-api images if the organization enforces repository-level authorization policies.

### 26.3. Network Protection

For private registry access:

- Verify DNS resolves properly.
- Ensure CI runners have network routes to the registry.
- Verify nodes/Container Apps environments have routes to ACR and required endpoints for downloading layers.
- Evaluate firewalls, proxies, and private endpoints.
- Avoid opening broad public network access merely to troubleshoot an incident without risk assessment.

### 26.4. Monitoring and Incident Response

Monitor:

- Push/delete events or registry permission changes.
- Unusual authentication failures.
- Network restriction modifications.
- Image scan findings.
- Deployed artifact digests.
- Deployments occurring outside approval workflows.

Logging/metrics capabilities and export formats depend on Azure Monitor, diagnostic settings, and active ACR/Defender features.

## 27. Troubleshooting Common ACR Errors

| Symptom | Causes to Check | Resolution |
|---|---|---|
| **unauthorized / denied** on push | Missing push permission, wrong registry, invalid token | Check identity, permissions, and authorization mode |
| **unauthorized** on pull from Container Apps/AKS | Runtime identity lacks permission or is unconfigured | Check identity, role/scope, and registry config |
| **manifest unknown** | Tag/digest does not exist or was deleted | Verify actual repository/tags/digest |
| **repository not found** | Wrong path, image not pushed yet, different registry | Check login server and repository name |
| **Docker daemon unavailable** | Docker engine is not running | Start Docker or use ACR Tasks/appropriate tooling |
| **TLS/timeout/DNS failure** | Network, DNS, proxy, private endpoint | Check name resolution and network path from client |
| **exec format error** | Image does not support OS/CPU architecture | Check platform and manifest |
| **ImagePullBackOff** in Kubernetes | Pull, auth, network, or image reference failed | Inspect pod events/logs and check ACR |
| Container runs but app does not serve | Wrong port, config, missing secret, startup error | Check runtime logs, readiness, and app settings |
| Same tag but different behavior | Tag was overwritten or local cache differs | Compare actual digests in each environment |

### 27.1. Investigating in Order

1. Record the **full image reference** including registry, repository, and tag/digest.
2. Verify the registry/repository/tag exists.
3. Verify the role and identity actually used to pull/push.
4. Check DNS and network connectivity from the exact place the workload runs.
5. Check platform and manifest.
6. Check runtime startup logs if pull succeeded but the container fails.
7. Cross-check the digest against the pipeline's release manifest.

An **ImagePullBackOff** error is not necessarily an ACR outage; it could stem from tag naming, AKS permissions, private networking, or platform mismatch. Never enable the admin user and retry as a default step.

## 28. Designing Registry Cost and Operations

ACR costs may include:

- Registry SKU/tier.
- Storage consumed by layers/manifests.
- Build operations or advanced features under applicable billing models.
- Geo-replication and network/data transfer if used.
- Supporting services such as Azure Monitor, CI runners, image scanning, or private networking.

Optimization principles:

1. Do not create a new registry for every build or feature branch.
2. Separate registries by clear security or operational unit boundaries.
3. Limit old artifacts via controlled retention policies.
4. Structure image layers wisely to leverage caching and reduce download sizes.
5. Check image build and cross-region replication costs.
6. Set appropriate Azure Cost Management budgets and tags.
7. Never delete images still needed for rollbacks or DR environments.

**ACR is not runtime compute.** The registry stores artifacts; compute costs for Container Apps, AKS, or VMs are billed separately by the service running the application.

## 29. End-to-End Hands-On Exercise

**Scenario:** a development team has a Java API with a built JAR and wants to use Azure Container Registry as the image source for a test environment.

### Part A — Create the Registry

1. Sign in to Azure and select the test subscription.
2. Create resource group **rg-acr-lab**.
3. Create an ACR with a unique name, budget-appropriate SKU, and admin user disabled.
4. Retrieve the **loginServer** from Azure CLI.
5. Verify the permissions of the identity performing the push.

### Part B — Build and Push

1. Build the test JAR.
2. Create a Dockerfile without secrets.
3. Build **orders-api:1.0.0** and run it locally.
4. Use **docker tag** to create a full image reference pointing to ACR.
5. Sign in using **az acr login**.
6. **docker push** the image to the registry.
7. Verify the repository/tags in CLI or Portal.

### Part C — Verify Digest

1. Read metadata for image **apps/orders-api:1.0.0**.
2. Record the actual digest.
3. Add a release or commit descriptive tag if required by workflow.
4. Compare whether the tags share the same digest or have different digests.
5. Explain why tags can change while a digest identifies a specific manifest.

### Part D — Test Deployment

1. Prepare a Container App or authorized test runtime environment.
2. Grant the identity pull permissions matching the registry's authorization mode.
3. Configure the full image reference and application port.
4. Deploy, then inspect logs, readiness, and HTTP endpoints.
5. Record the image reference/digest of the running version.

### Part E — Test a New Version and Rollback

1. Make a small change in the application.
2. Build image **1.0.1** and push under the new tag.
3. Test and record its digest.
4. Transition the test app to the new version.
5. If errors occur, redeploy **1.0.0** or the exact saved digest.
6. Evaluate why overwriting an old tag can make rollbacks unpredictable.

### Part F — Cleanup

1. List resources created specifically for the lab.
2. Verify no Container Apps or other workloads are still using the image.
3. Delete the exact test resources per permitted rights and procedures.
4. Review costs for ACR, Container Apps, and related resources.
5. Do not delete shared registries or images still needed for production/rollback.

**Completion criteria:** you can accurately read a full image reference, verify an image was pushed to ACR, determine its digest, explain pull/push permissions, and perform deployments/rollbacks without using shared admin credentials.

## 30. Pre-Production Checklist for Using ACR

- [ ] Registry and SKU fit storage, performance, networking, and availability requirements.
- [ ] Clear repository naming with defined owners and consistent conventions.
- [ ] Release image tags are not arbitrarily overwritten.
- [ ] Release manifest records image digest, commit, and build provenance.
- [ ] Images are built/tested/scanned via controlled pipelines.
- [ ] No secrets or private keys in images or build contexts.
- [ ] CI identity has only necessary push permissions.
- [ ] Runtime identity has only necessary pull permissions.
- [ ] Verified registry RBAC/ABAC mode before assigning permissions.
- [ ] If using private access, CI runners and runtimes have proper DNS/networking.
- [ ] Artifacts match the runtime environment's platform.
- [ ] Container Apps/AKS deployment and health configs are managed independently of ACR.
- [ ] Retention/cleanup policies exist while preserving rollback artifacts.
- [ ] Auditing/monitoring and alerts for sensitive changes are enabled.
- [ ] Backup/geo-replication plan exists when HA/DR requirements apply.
- [ ] Storage usage, build usage, and overall costs are tracked.
- [ ] Deletion, tag-locking, and credential rotation procedures are clearly documented.

## 31. Self-Check Questions

1. How do a registry and a repository differ? Is a repository an Azure Resource Group?
2. In **acrlabexample.azurecr.io/apps/orders-api:1.4.0**, which parts are the hostname, repository, and tag?
3. Why is **docker tag** insufficient for an image to appear in the Azure Portal?
4. What is the difference between a Docker image, a running container, a filesystem layer, and an image manifest?
5. Can tag **1.4.0** be re-pointed to different content? How should that be controlled?
6. Why does a digest support reproducible deployments better than a mutable tag?
7. If an image supports multiple CPU architectures, can the digests of the image index and platform-specific manifest differ?
8. Why should the ACR admin user not be used as the default credential for CI/CD?
9. What roles do **AcrPull** and **AcrPush** serve in a standard RBAC registry?
10. When using repository ABAC, why must you inspect its specific role model?
11. Why does pushing a new image to ACR not cause Azure Container Apps to automatically update?
12. When encountering **manifest unknown** or **ImagePullBackOff**, what factors should be inspected?
13. Why should production deploy the same digest tested in staging instead of rebuilding?
14. If an artifact is deleted from the registry, what can happen during the next scale-out or rollback?
15. When restricting networking with a private endpoint, why do CI runners, DNS, and the runtime's pull path matter?

## 32. Summary

**Azure Container Registry** is the platform for storing and distributing container images/artifacts in Azure. A **registry** holds multiple **repositories**; each repository can hold multiple **image tags**; a tag is a human-readable name that can be reassigned, whereas a **digest** identifies specific manifest/index content. In operations, read image references accurately, distinguish **build → tag → push → pull → deploy**, and record digests for every release.

For production applications, a reliable workflow is **build once, test/scan image, push to ACR, record digest, and deploy the exact artifact across environments**, using managed identities with least-privilege pull/push permissions, while managing image retention and rollback readiness. Combining ACR with Azure Container Apps/AKS, Microsoft Entra ID, networking, Azure Monitor, and Cost Management creates a secure, traceable, and cost-controlled container delivery chain.
