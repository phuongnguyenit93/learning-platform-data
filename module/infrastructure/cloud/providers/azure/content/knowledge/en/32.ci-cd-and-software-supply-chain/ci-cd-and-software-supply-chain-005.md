# Managing Artifacts, Packages, and Container Images

In a CI/CD workflow, finishing compilation does not mean the application is ready for deployment. The development team must still store build outputs in a trusted location, identify exact versions, verify provenance, grant permissions to consuming systems, and decide when old data can be purged. Those outputs typically appear in three forms: **pipeline artifacts**, **packages**, and **container images**.

This lesson belongs to the **CI/CD and Software Supply Chain** chapter of the Microsoft Azure learning path. The knowledge applies to applications running on Azure Kubernetes Service (AKS), Azure Container Apps, App Service, virtual machines, or systems consuming internal libraries. The focus is managing the full lifecycle of build outputs—from commit to production—using Azure Pipelines, Azure Artifacts, and Azure Container Registry (ACR).

## 1. Learning objectives

After this lesson, you will be able to:

1. Distinguish pipeline artifacts, packages, and container images by format, intended use, and storage location.
2. Design versioning rules, commit tagging, digest recording, and build-once promotion across multiple environments.
3. Use Azure Pipelines to publish artifacts, Azure Artifacts to distribute packages, and ACR to distribute images.
4. Apply least-privilege access, vulnerability scanning, SBOMs, signing, and pre-deployment approval policies.
5. Operate promotion, rollback, retention, and troubleshooting workflows.

## 2. Three types of build outputs to manage

| Type | Typical content | Target consumer | Common storage | How identified |
| --- | --- | --- | --- | --- |
| **Pipeline artifact** | JAR files, build directories, test reports, deployment manifests, generated configs | Next stage in the same or another pipeline | Azure Pipelines / Azure DevOps | Pipeline run, artifact name, commit metadata |
| **Package** | NuGet, npm, Maven, Python libraries, Universal Packages | Other applications, dependency managers, dev teams | Azure Artifacts feed | Package name + version |
| **Container image** | OCI manifest, filesystem layers, startup configuration | AKS, Container Apps, App Service, container hosts | Azure Container Registry | Registry + repository + tag or digest |

A **pipeline artifact** is the output of a specific pipeline run. For example, a Java build job creates a JAR file and a deploy job downloads that exact file. Artifacts are tied to a concrete run, making them convenient for passing data between stages or aiding incident investigation. Azure Pipelines has **Pipeline Artifacts** and legacy **Build Artifacts**; on Azure DevOps Services, Pipeline Artifacts are typically the right choice for new flows.

A **package** is an identifiable, versioned unit shared across multiple projects. For instance, a platform team publishes the Maven library **com.example:telemetry-core:2.3.1** to an Azure Artifacts feed. Consuming projects declare a dependency on that version without needing to know which pipeline built it. Azure Artifacts supports major package ecosystems as well as **Universal Packages** for content outside standard package formats.

A **container image** bundles an application and its required runtime dependencies in OCI/Docker format. ACR stores repositories, image manifests, and layers. For example, an application image may reside at **acrdemo.azurecr.io/orders/api:1.4.0**. Tags are convenient for humans, whereas **sha256** digests identify exact manifest content.

One pipeline can produce all three types. For example:

- Store the JAR and test reports as pipeline artifacts for downstream stages to download.
- Publish a shared library as a Maven package in Azure Artifacts.
- Package an API service as a container image and push it to ACR for deployment.

Never dump every output into a single registry just because all of them are loosely called "artifacts." Choose storage based on **how the output is consumed** and its access, retention, and release policies.

## 3. Management architecture on Azure

~~~mermaid
flowchart TD
    A["Git commit / pull request"] --> B["CI: build, test, analyze"]
    B --> C["Generate SBOM, metadata, evidence"]
    C --> D["Quality and security gates"]
    D --> E["PublishPipelineArtifact"]
    D --> F["Azure Artifacts feed"]
    D --> G["Azure Container Registry"]
    E --> H["Deployment stage consumes build files"]
    F --> I["Other apps resolve dependencies"]
    G --> J["Staging references image digest"]
    J --> K["Approval / verification"]
    K --> L["Production uses exact same image digest"]
~~~

Key components to recognize:

| Component | Responsibility |
| --- | --- |
| **Azure Repos or GitHub** | Manages source code, pull requests, branches, commits, and change verification policies |
| **Azure Pipelines or GitHub Actions** | Runs builds, tests, packaging, scanning, signing, publishing, and deployments |
| **Azure Artifacts** | Manages package feeds, read/write permissions, versions, upstream sources, and feed views |
| **Azure Container Registry** | Manages repositories, image manifests, layers, tags, digests, push/pull permissions, and registry tasks |
| **Microsoft Entra ID** | Provides identities for users, service principals, workload identities, and managed identities |
| **Azure RBAC / feed permissions** | Restricts who can read, publish, administer, and deploy artifacts |
| **AKS, Container Apps, App Service** | Pulls and runs images or consumes build outputs via the corresponding deployment mechanism |

An Azure DevOps organization/project, an Azure subscription, and an ACR instance are distinct governance boundaries. Having permission to edit a pipeline **does not automatically** grant permission to push images to ACR; having ACR push permissions does not grant rights to manage Azure Artifacts feeds.

## 4. Designing identity, versioning, and immutability

### 4.1. Linking build outputs to provenance

Every release should trace at least:

- Repository, commit SHA, and source branch/tag.
- Pipeline run ID, build timestamp, toolchain, and build environment.
- Package name and version, or container repository, tag, and digest.
- Test results, security scans, SBOM, signatures, or attestations (where applicable).
- Target environments deployed and the approver or policy rule that authorized them.

**Example release mapping:**

| Field | Illustrative value |
| --- | --- |
| Source | Repository `orders-api`; commit `8f73c1a…` |
| CI run | Azure Pipelines run 4281 |
| Pipeline artifact | `orders-api-jar` from run 4281 |
| Shared Maven package | `com.example:orders-client:1.4.0` |
| Container image tag | `orders/api:1.4.0` and `orders/api:8f73c1a` |
| Container image digest | `sha256:…` (value returned by the registry after push) |
| Environments | staging → production, referencing the exact same digest |

This is a **cross-system mapping**, not an implication that the JAR, Maven package, and image contain identical bytes. Each artifact type has its own integrity identifier; proving correspondence requires pipeline metadata and provenance.

### 4.2. Package versioning

For libraries consumed by others, follow the ecosystem's versioning rules—typically **Semantic Versioning**:

- **MAJOR** for incompatible API changes.
- **MINOR** for backward-compatible feature additions.
- **PATCH** for backward-compatible bug fixes.

Examples: **2.5.0** or prerelease **2.6.0-rc.1**. Check exact conventions for npm, NuGet, Maven, or Python since tools treat versions, prereleases, and build metadata differently.

In Azure Artifacts, published package versions are generally treated as **immutable**: do not plan to overwrite the same name and version when content changes. If **2.5.0** has a bug, publish **2.5.1** or deprecate/unlist the faulty version per process; never rebuild and overwrite label **2.5.0**.

### 4.3. Container image tags and digests

One image may carry multiple tags: **1.4.0**, **commit-8f73c1a**, **build-4281**. A tag is a reference pointer that can move to a different manifest depending on registry policy; hence **a tag is not immutable proof of content**.

A digest references manifest or OCI index content. Illustrative example:

~~~text
acrdemo.azurecr.io/orders/api:1.4.0
acrdemo.azurecr.io/orders/api@sha256:<64-hex-char-digest>
~~~

The second line uses a placeholder to show structure; in operations, replace it with the actual digest returned by the registry. For multi-architecture images (**linux/amd64** and **linux/arm64**), the OCI index digest can differ from each per-architecture manifest digest. Record the exact digest used by your deployment system to resolve the image.

Practical rules:

1. Build and push once in CI after verification.
2. Record the actual digest immediately after push, linking it to the commit and run ID.
3. Deploy staging and production using the **same digest**; promotion means transferring authorization to use a verified artifact.
4. Use tags for lookup, version display, and governance where helpful; always store the digest in the release record.
5. To roll back, select a previously verified digest.

**Never rebuild separately for production** just to change an environment label. The same source code can yield different binaries when dependencies, base images, timestamps, or toolchains shift. Building once and promoting that exact output reduces drift between staging and production.

### 4.4. Release manifest

A standalone manifest tells deployment exactly what content to deploy:

~~~yaml
release: "orders-api-1.4.0"
source:
  commit: "8f73c1a..."             # illustrative; replace with full SHA
  pipelineRunId: 4281
artifacts:
  pipeline:
    name: "java-output"
    runId: 4281
  package:
    name: "com.example:orders-client"
    version: "1.4.0"
  container:
    registry: "acrdemo.azurecr.io"
    repository: "orders/api"
    tag: "1.4.0"
    digest: "<actual-sha256-digest>"
checks:
  tests: "passed"
  vulnerabilityPolicy: "passed"
  sbom: "attached"
~~~

This manifest is a **structural template** for your own system; it is not a mandatory Azure format. In automated pipelines, generate the manifest from real values, store it alongside evidence, and prevent unauthorized edits.

## 5. Managing pipeline artifacts in Azure Pipelines

### 5.1. Publishing and downloading

Suppose a Java Maven project produces a JAR and test reports. After **mvn clean verify**, the pipeline can publish the **target** directory:

~~~yaml
steps:
  - task: Maven@4
    displayName: "Build and test Java app"
    inputs:
      mavenPomFile: "pom.xml"
      goals: "clean verify"

  - task: PublishPipelineArtifact@1
    displayName: "Store build output"
    inputs:
      targetPath: "$(Build.SourcesDirectory)/target"
      artifact: "java-output"
~~~

A subsequent job or stage can download that artifact:

~~~yaml
steps:
  - task: DownloadPipelineArtifact@2
    displayName: "Fetch build output from current run"
    inputs:
      buildType: "current"
      artifactName: "java-output"
      targetPath: "$(Pipeline.Workspace)/java-output"

  - bash: |
      find "$(Pipeline.Workspace)/java-output" -type f
    displayName: "Verify received files"
~~~

These are YAML snippets for **Azure Pipelines on Azure DevOps Services**. In multi-stage pipelines, ensure the artifact-producing stage succeeds before the downloading stage runs. The **find** command only checks file presence; in production, verify exact filenames, checksums, or required metadata before using them.

### 5.2. Rules for storing pipeline artifacts

**Package only necessary files.** Build directories often contain temporary files, caches, and bulky reports unnecessary for deployment stages. Separate **deployables** (for release) from **reports** (for diagnostics). Never upload private keys, tokens, passwords, secret-bearing env files, or logs containing sensitive data.

**Tie artifacts to the run ID.** An artifact named **java-output** exists across many runs; the name alone does not identify a version. To make a release reproducible, record both the run ID and commit.

**Set retention to match needs.** Pipeline artifact lifespans depend on Azure DevOps retention policies and run lifecycles. Do not assume build outputs live forever or treat pipeline artifacts as a long-term release repository for internal consumers. To distribute libraries across projects, use a package feed; to run containers, push images to a registry.

**Do not treat an artifact as proof of testing.** Files qualify for release only when test results and quality gates tied to the exact commit/run satisfy team policy.

## 6. Managing packages with Azure Artifacts

### 6.1. Feeds, packages, and views

A **feed** is a namespace for managing packages and access permissions. Feeds can be project-scoped or organization-scoped depending on creation settings. A feed can hold packages across all formats supported by Azure Artifacts; name feeds clearly by product, business domain, or access policy.

**Feed views** control package readiness levels, commonly:

- **@Local**: all packages currently present in the feed.
- **@Prerelease**: versions approved for testing or early integration.
- **@Release**: versions approved for broad adoption.

When promoting from **@Local** to **@Release**, the exact same package version receives the higher view label; **no library recompilation is needed**. Before configuring clients, verify the feed/view URL and read permissions for that package type.

**Upstream sources** allow a feed to fetch and cache packages from public registries or other feeds as configured. While this improves dependency stability, it also requires governing trusted sources, checking licenses, and preventing unwanted packages with colliding names.

### 6.2. Example: publishing an internal npm package

Suppose a team develops **@platform/date-utils**. In source:

~~~json
{
  "name": "@platform/date-utils",
  "version": "1.3.0",
  "private": false,
  "main": "dist/index.js",
  "files": ["dist"]
}
~~~

The package **.npmrc** points to the internal feed. Replace the example URL below with the actual feed URL shown under **Connect to feed** in Azure Artifacts:

~~~ini
@platform:registry=https://pkgs.dev.azure.com/ORG/PROJECT/_packaging/FEED/npm/registry/
always-auth=true
~~~

The pipeline uses an authentication task instead of committing tokens into the repo:

~~~yaml
steps:
  - task: NodeTool@0
    inputs:
      versionSpec: "24.x"

  - task: npmAuthenticate@0
    inputs:
      workingFile: "packages/date-utils/.npmrc"

  - bash: |
      cd packages/date-utils
      npm ci
      npm test
      npm run build
      npm publish
    displayName: "Test and publish npm package"
~~~

**Conditions to run this example:**

- The feed must exist; URL, scope name, and package folder must match the real project.
- The build service identity must hold permissions to publish into the feed; if the feed lives in another project, grant explicit cross-project permissions.
- The **build** script must exist and produce **dist**; a lockfile must be committed so **npm ci** works.
- Version **1.3.0** can be published only if that name/version does not already exist in the feed; every new release must bump the version.
- Place publishing on a trusted release path—such as after PR approval and security checks pass—never from arbitrary untrusted pull requests.

The same principles apply to NuGet, Maven, and Python: use ecosystem tooling, the exact feed URL, and the appropriate authentication task. Creating a package version must remain separate from approving that version for production consumption.

### 6.3. Package policies

| Decision | Recommended practice | Rationale |
| --- | --- | --- |
| Naming | Use owner-scoped namespaces/prefixes | Prevents confusion between internal and public packages |
| Permissions | Reader for consumers; publisher for trusted pipelines | Limits who can alter dependency sources |
| Versioning | Never overwrite published versions | Supports build reproducibility and incident investigation |
| Promotion | Elevate to release view only after sufficient evidence | Separates package creation from consumption approval |
| External sources | Configure controlled upstreams, pin dependencies/lockfiles | Reduces surprise changes or dependency confusion |
| Retention | Retain active, rollback-needed, and audit-required versions | Balances storage cost against recovery capability |

## 7. Managing container images with Azure Container Registry

### 7.1. Registry, repository, tag, and manifest

ACR is a private registry for storing OCI-compliant images and artifacts. Standard address format:

~~~text
<registry-login-server>/<repository>:<tag>
~~~

Example: **acrdemo.azurecr.io/orders/api:1.4.0**, where:

- **acrdemo.azurecr.io** is the login server.
- **orders/api** is the repository.
- **1.4.0** is a tag pointing to a manifest.
- **sha256:…** is the digest of that manifest or index.

Images typically consist of reusable layers. Deleting a tag does not always immediately purge underlying layer data, since other manifests may still reference those layers. When cleaning a registry, account for manifests, tags, dependencies, and retention policies together.

### 7.2. Preparing the registry and testing a push

This example assumes Azure CLI is logged in with an authorized subscription, permissions to create an ACR, and an existing resource group **rg-ci**. Azure registry names must be valid and globally unique; **acrteamdemo12345** is illustrative.

~~~bash
ACR_NAME=acrteamdemo12345
RESOURCE_GROUP=rg-ci
REPOSITORY=orders/api
TAG=1.4.0

az acr create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$ACR_NAME" \
  --sku Basic

ACR_SERVER=$(az acr show \
  --name "$ACR_NAME" \
  --query loginServer -o tsv)

az acr login --name "$ACR_NAME"

docker build --pull -t "$ACR_SERVER/$REPOSITORY:$TAG" .
docker push "$ACR_SERVER/$REPOSITORY:$TAG"
~~~

**Minimal Dockerfile** for a pre-packaged Java application:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY target/app.jar /app/app.jar
USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

This example requires **target/app.jar** to exist, a base image supporting UID **10001**, and the app listening on port **8080**. In real systems, pin the base image digest, verify write permissions required by the app, minimize unnecessary layers, and scan the built image. Build and test the JAR and its dependencies from trusted sources before creating the image.

To inspect the digest stored by the registry, query metadata via Azure CLI (with registry read permissions):

~~~bash
az acr manifest show-metadata \
  --registry "$ACR_NAME" \
  --name "$REPOSITORY:$TAG" \
  --query digest -o tsv
~~~

Save this digest in the release manifest or pipeline outputs. When verifying image contents across environments, always compare digests rather than relying on tags alone.

### 7.3. Building and pushing images with Azure Pipelines

The CI sample below uses a Docker Registry service connection authorized to push to ACR. Replace **sc-acr-push** with a real service connection. The pipeline tests the app before pushing:

~~~yaml
trigger:
  - main

pool:
  vmImage: "ubuntu-latest"

steps:
  - task: Maven@4
    displayName: "Build and test"
    inputs:
      mavenPomFile: "pom.xml"
      goals: "clean verify"

  - task: PublishPipelineArtifact@1
    displayName: "Store Java artifacts"
    inputs:
      targetPath: "$(Build.SourcesDirectory)/target"
      artifact: "java-output"

  - task: Docker@2
    displayName: "Build and push image to ACR"
    inputs:
      containerRegistry: "sc-acr-push"
      repository: "orders/api"
      command: "buildAndPush"
      Dockerfile: "$(Build.SourcesDirectory)/Dockerfile"
      buildContext: "$(Build.SourcesDirectory)"
      tags: |
        $(Build.SourceVersion)
        $(Build.BuildId)
~~~

These two tags provide traceability by commit and run ID; **they do not replace the digest**. For production, add a stage querying the digest from ACR, recording metadata, generating an SBOM, scanning, and verifying the image before permitting deployment. The digest-lookup stage needs an Azure/ACR authentication mechanism with read access; do not assume a Docker service connection automatically authenticates Azure CLI for subsequent steps.

**Versioning note:** CI can often run multiple times on the same commit, allowing commit-based tags to be overwritten if registry settings permit. To guarantee a unique reference per build, include the run ID or enforce immutable tags, and always pin the digest for releases.

### 7.4. Deploying by digest

In AKS, Container Apps, or other container platforms, image references can specify the digest directly:

~~~text
acrdemo.azurecr.io/orders/api@sha256:<actual-digest>
~~~

Example container spec in a Kubernetes Deployment:

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
        - name: api
          image: "acrdemo.azurecr.io/orders/api@sha256:<actual-digest>"
          ports:
            - containerPort: 8080
~~~

This YAML only illustrates image selection; replace the placeholder digest before applying. The AKS cluster must be able to reach ACR, and the **image-pull identity** must hold matching read permissions. On Container Apps or App Service, configure registry access and managed identity on the target resource itself.

**Promotion** means updating the next environment's deployment configuration to the exact image digest that passed testing. During a production incident, roll back to the previous stable manifest/digest while checking database schema compatibility, migrations, and runtime configuration. Rolling back an image does not automatically undo database changes.

## 8. Securing the software supply chain

An artifact is the output of a process; securing the registry alone is insufficient if dependencies or build runners are compromised. Policies must span **source → build → publish → promotion → runtime**.

### 8.1. Identities and least-privilege permissions

| Subject | Required permissions | Permissions to avoid |
| --- | --- | --- |
| CI image-building pipeline | Push to designated ACR repository, read needed metadata | Subscription Owner just to publish |
| AKS kubelet / workload runtime | Pull images from authorized repositories | Push or delete image permissions |
| Package-publishing pipeline | Publish packages to scoped feed | Admin across all projects/feeds |
| Package-consuming pipeline | Read packages and metadata | Publish new versions |
| Release approver | Inspect evidence, approve environment | Shared, ungoverned registry credentials |

For ACR configured with **registry-level RBAC**, common roles are **AcrPull** and **AcrPush**. For ACR using **ABAC repository permissions**, role names and scoping differ by repository; match the registry's actual permission mode rather than assuming one role assignment works everywhere.

For Azure Artifacts, assign feed roles (Reader, Collaborator, Contributor/Owner) appropriately; ensure the Azure DevOps build service identity has explicit permissions, especially when feeds live in another project.

Prefer:

- **Managed identities** for long-running Azure services pulling images where supported.
- **Workload identity federation / OIDC** for CI/CD jobs to avoid long-lived client secrets, with trust policies scoped by repository, branch, and environment.
- Tightly scoped service connections; separate build/push identities from deploy identities.
- Never enable the ACR admin account as the default method; never put passwords into Dockerfiles, public build args, source code, or pipeline artifacts.
- Restrict ACR networking where required by security policy; verify connectivity from hosted agents, self-hosted agents, and runtimes when firewalls or private endpoints are enabled.

### 8.2. Pre-publish and pre-deploy checks

A release gate may require:

1. Reviewed source code and controlled pipeline configuration.
2. Passing unit tests, integration tests, and build.
3. Dependency, secret, image, and license scans passing policy.
4. Generating a **Software Bill of Materials (SBOM)** listing build components and dependencies.
5. Creating provenance/attestations recording who built it, from what source, via which workflow, linked to the digest.
6. Signing artifacts or attestations where adopted; **verifying signatures, signer identity, and trust policy** prior to deployment.
7. Approving promotion, deploying by digest, and archiving evidence.

Tools such as **Syft** (SBOM), **Trivy** (scanning), **Cosign** (signing/verification), or approved alternatives can participate in this workflow; they **do not run automatically** just by pushing an image to ACR. Microsoft Defender for Cloud offers container vulnerability assessment depending on tier, configuration, and support scope; confirm actual capabilities before relying on it as a release gate.

A useful SBOM lists packages, versions, dependencies, and links back to the build output. However, **an SBOM is not a signature**, and **a "zero findings" scan does not prove an image is unconditionally trustworthy**. Enforce source controls, tool security, least-privilege permissions, and evidence verification together.

### 8.3. Attacks and countermeasures

| Risk | Scenario | Mitigation |
| --- | --- | --- |
| **Dependency confusion** | Internal package name collides with public registry package | Clear namespaces, source pinning, controlled upstreams, and publish controls |
| **Tag substitution** | Production tag repointed to a different manifest | Deploy by digest, restrict push access, and monitor tag changes |
| **Secret leakage in layers** | Token copied or echoed in build commands persists in layer history | Use secure build secret mechanisms; never copy secrets into images; scan for secrets |
| **Compromised runner** | Untrusted job accesses publish credentials | Separate permissions by branch, conditional OIDC, isolate runners, and review PRs |
| **Poisoned dependency** | External library contains malicious code | Lockfiles, version/hash pinning where supported, scanning, and upstream controls |
| **Unbound evidence** | Signing a tag or scanning one image while deploying another | Generate, sign, and verify evidence bound to the actual digest |
| **Accidental deletion of active image** | Cleanup purges manifests referenced only by digest | Inventory active digests, rollback targets, and held releases before deleting |

## 9. Release flow from staging to production

Practical design for **orders-api**:

| Stage | Activity | Promotion condition |
| --- | --- | --- |
| 1. Commit | Merge after code review; CI checks out exact commit | Satisfies branch policy |
| 2. Build | Restore dependencies, test, produce JAR and image | Tests and build pass |
| 3. Publish | Push image to ACR, save pipeline artifact and digest | Publish succeeds, metadata complete |
| 4. Security gate | Scan image/dependencies, verify SBOM and provenance | Meets policy or has approved timebound exception |
| 5. Staging | Deploy by digest, run smoke/integration tests | Metrics and tests pass |
| 6. Approval | Review release manifest and staging results | Approved per environment policy |
| 7. Production | Deploy the exact digest verified in staging | Health checks, metrics, and error budget within bounds |
| 8. Observe | Record deployment, monitor alerts, trigger rollback if failing | Clear recovery path ready |

When distributing the same image across multiple registries, **copy/import the image preserving exact content** with supported registry tools, verify the destination digest, and record source/destination mappings. Never assume matching tags across two registries hold identical bytes. Signing and verification must also bind to the actual deployed manifest.

For packages, the analogous flow is **build → publish immutable version to feed → test from feed → promote view → consumers upgrade dependencies cleanly**. For pipeline artifacts, the typical flow is **publish from build job → download in deploy job → verify run/commit match → deploy**.

## 10. Retention, cleanup, recoverability, and cost

### 10.1. Retention by artifact type

**Pipeline artifacts:** check pipeline run retention policies, retained releases, and audit requirements. Never delete runs holding needed forensic evidence or recovery files without an alternative archive.

**Packages in Azure Artifacts:** keep versions actively used by applications, supported stable releases, and versions needed for rollback. Verify retention rules and delete/unlist behavior per package format; promotion views, feed permissions, and upstreams can affect deletion. Never treat automated cleanup as proof that no consumer still depends on a package.

**Images in ACR:** inventory digests running in production/staging, rollback candidates, and compliance-retained builds. Inspect repositories, manifests/tags, and retention policies before deleting. Test **untagged** image cleanup or automated purge policies on a small dataset with explicit exclusion criteria first.

### 10.2. Cost and availability

Costs typically come from storage capacity, data transfer, and per-service features. ACR offers different tiers/features; requirements like private endpoints, throughput scale, or geo-replication influence tier selection. Azure DevOps and Azure Artifacts enforce distinct storage and retention limits that should be monitored against actual usage.

Operational cost-control decisions:

- Trim unnecessary files from pipeline artifacts and optimize image layers.
- Tailor retention policies by environment tier and audit requirements.
- Retain enough builds for rollback before enabling automated cleanup.
- Inventory dependencies to avoid storing every version indefinitely.
- Measure real storage and bandwidth; balance registry replication against incident recovery goals.

**Incident recovery** requires more than a tag: retain release manifests, digests, approval history, deployment configs, and database recovery procedures. Periodically test pulling older images and redeploying them in a controlled environment.

## 11. Troubleshooting common issues

| Symptom | Causes to check | Resolution |
| --- | --- | --- |
| **401 Unauthorized** on push/pull | Not logged in, expired token, wrong auth config | Verify job/runtime identity and login method |
| **403 Forbidden** on publish/pull | Authenticated but lacks feed, registry, or repo permissions | Check publisher/reader permissions and Azure RBAC or ABAC at exact scope |
| **ImagePullBackOff** on AKS | Pull credentials, network/DNS/private endpoint, wrong image/tag/digest, wrong arch | Inspect Pod events, kubelet identity, ACR reachability, and image reference |
| **Package version already exists** | Pipeline republishes existing version | Bump version; design idempotency into release pipelines |
| **Manifest unknown / image not found** | Missing tag/digest, wrong repository, purged digest | Verify registry address, repository name, recorded digest, and retention |
| **Local build works, production image fails** | Runtime config drift, missing files, wrong architecture or base image | Inspect Dockerfile, runtime env, health checks, and logs using exact digest |
| **Staging passes, production behaves differently** | Production pulled an overwritten tag or rebuilt image | Compare digests and release manifests; promote exact digest |
| **CI cannot connect to ACR** | Firewall, private endpoint, DNS, or agent config | Verify real network path from agent and access configuration |
| **Cannot roll back to old version** | Retention purged artifact/image, or incompatible migration | Maintain list of rollback digests and data rollback playbooks |

Following an ordered diagnostic sequence locates root causes quickly: **artifact address → version/digest → identity → permissions → network → policy → runtime**. Never work around permission errors by granting subscription Owner or enabling ACR admin accounts for every pipeline.

## 12. Practice exercise: one image, two environments

**Context:** A team has a Java service **orders-api**, an Azure DevOps project, an ACR instance, and two environments: **staging** and **production**. The goal is to prove both environments can run the **exact same build output**.

### Step 1 — Preparation

Create or select an ACR, configure a CI service connection with push permission, and configure a runtime identity with pull permission. Define a valid Dockerfile and configure Maven to produce **target/app.jar**. If using an internal package feed, grant read permission to the build job and lock dependency versions with appropriate config/lockfiles.

### Step 2 — Build and publish

Run the pipeline from Section 7.3 on an authorized branch. Confirm the Maven job succeeds, the **java-output** artifact appears in the run, and the **orders/api** repository in ACR receives the corresponding tags. Record the actual **run ID, commit SHA, and image digest**. Accept the release only if all checks defined in Section 8 pass.

### Step 3 — Deploy to staging

Create a release manifest containing the captured digest. Configure staging to deploy by that digest and run verification: clean startup, healthy status endpoint, one core business call, and key metrics checked.

### Step 4 — Promote to production

After staging passes checks and receives approval, update production to **that exact digest**. Record deployment history. Query the runtime to verify the live image; on Kubernetes, inspect Pod `imageID`/digest alongside rollout status rather than relying solely on reading back deployment config.

### Step 5 — Rehearse rollback

Simulate a failing health check. Revert production to the previous release's digest, watch rollout status, and verify application health. If the release included a data migration, follow the pre-designed recovery or backward-compatibility plan.

**Deliverables for this exercise:**

- Recorded commit SHA, pipeline run ID, and digests for both image versions.
- Release manifest used for staging/production.
- Evidence that staging and production ran the exact same digest before rollback.
- Rollback log and assessment of whether data or secrets were impacted.

## 13. Decision-making scenarios

**Scenario A:** A team deploys using the **latest** tag. Staging passes in the morning, but production pulls the tag in the afternoon and runs different code. **Solution:** bind builds to commits/runs, pin the digest after push, promote that digest across environments, and restrict tag overwrite permissions.

**Scenario B:** Two services share a library, and the owning team wants to patch **1.1.0** without bumping the version. **Solution:** keep published versions immutable, release **1.1.1** (or appropriate SemVer bump), run compatibility tests, and let consumers explicitly upgrade.

**Scenario C:** An ACR grows rapidly; a cleanup schedule plans to delete all untagged images, while an older deployment references its image by digest. **Solution:** inventory all actively referenced digests and rollback targets, set retention windows, dry-run cleanup on a small subset first, and only then automate.

**Scenario D:** A GitHub Actions or Azure Pipelines job pushes images using an ACR admin password stored in a shared variable. **Solution:** separate CI identities, adopt OIDC/workload identity federation or a proper service connection, grant scoped push rights under ACR RBAC/ABAC, retire the shared credential, and audit usage.

## 14. Self-check

**Question 1.** When sharing a Java library across multiple services, should you prefer a pipeline artifact or a Maven package in Azure Artifacts?  
**Answer:** A Maven package, because it provides stable coordinates and versions managed directly by dependency tools, and feeds support permissions, distribution, and promotion views.

**Question 2.** Why should tag **1.4.0** not be treated as proof that staging and production run the identical image?  
**Answer:** Tags can be repointed to a different manifest. You must compare digests and release evidence.

**Question 3.** Should you rebuild an image for production after staging passes tests?  
**Answer:** No. Promote the exact verified digest while verifying production configuration and policies.

**Question 4.** What do Azure Artifacts feed promotion and ACR image promotion share?  
**Answer:** Both promote an already-built, verified artifact to a higher readiness tier using an immutable identity—name/version for packages, and digest for production container images.

**Question 5.** Does an SBOM replace image signing and provenance verification?  
**Answer:** No. An SBOM inventories components and dependencies; signatures and provenance verify integrity, signer identity, and build origin. They complement each other.

## 15. Project adoption checklist

- [ ] Choose the proper storage for pipeline artifacts, packages, and container images.
- [ ] Trace every released artifact back to its commit SHA and pipeline run.
- [ ] Enforce immutable package versions; record image digests in release manifests.
- [ ] Publish from CI only after required build, test, and security checks pass.
- [ ] Separate permissions for publishers, consumers, and deployers.
- [ ] Prefer managed identities/OIDC and keep secrets out of source, images, and artifacts.
- [ ] Promote the exact verified artifact across environments.
- [ ] Enforce post-deploy observability, rollback playbooks, and safe retention policies.
- [ ] Verify SBOM, provenance, and signature evidence where required by policy.

Effective artifact management means **knowing exactly what was produced, who can alter or consume it, how it was verified, and which version can be restored during an incident**. On Azure, combining Azure Pipelines, Azure Artifacts, and ACR under these principles builds a resilient foundation for CI/CD and software supply-chain security.
