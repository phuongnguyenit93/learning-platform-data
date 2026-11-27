# Artifact Registry Repositories and Artifact Formats on Google Cloud

> **Chapter:** Containers and Artifact Registry  
> **Module:** **CLOUD_PROVIDERS_GCP** — Explore Google Cloud from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage services, and databases. Through deployment scenarios, learners learn how to choose services, protect resources, automate releases, and monitor reliability and cost.

A Java development team might produce a **container image** to run on GKE or Cloud Run, a **JAR** for other Maven/Gradle projects to consume, and a configuration bundle to release alongside the application. These artifacts should not sit on a developer's laptop or in a shared folder lacking versioning, permissions, and traceability.

**Artifact Registry** is Google Cloud's service for managing **packaged artifacts**: container images, language packages, OS packages, and other versioned files/bundles. Artifact Registry helps organizations manage storage locations, formats, identifiers/versions, read/write permissions, dependency sources, vulnerability scanning, and cleanup policies. This lesson focuses on **repositories and artifact formats**, then connects them into the build, deployment, and security workflows of the **CLOUD_PROVIDERS_GCP** module.

## Learning Objectives

After this lesson, learners will be able to:

1. Distinguish between **repository, package, version, tag, digest, artifact file**, and **image manifest**.
2. Choose the right **repository format** for Docker/OCI, Maven, npm, Python, Go, Debian Apt, RPM Yum/DNF, Generic, and other supported artifact types.
3. Compare **standard, remote, and virtual** repositories and explain the **connector (Preview)** use case.
4. Design names, locations, projects, IAM permissions, encryption, retention, and cleanup policies per environment.
5. Create a **Docker standard repository**, configure Docker authentication, tag/push/pull images, and inspect metadata using gcloud.
6. Configure access for Maven/Gradle, Python, npm, and Generic artifacts without embedding long-lived credentials in source code.
7. Distinguish **mutable tags** from **immutable digests**, building reproducible release and rollback pipelines.
8. Analyze remote/upstream dependencies, **dependency confusion** risks, software vulnerabilities, cross-project access, and costs.
9. Troubleshoot 401/403 errors, missing tags, wrong locations, quotas, upstream outages, and accidental version deletion by cleanup.

## 1. What Problem Does Artifact Registry Solve?

An artifact is a **distributable output of a build or packaging process**, for example:

- The **checkout-api** image containing the Java runtime, JAR, and default configuration.
- Package **com.example:payment-common:1.8.0** used in Maven or Gradle.
- npm package **@commerce/ui-kit@2.2.0** owned by the frontend team.
- Python wheel **risk_scoring-1.3.0-py3-none-any.whl**.
- Go module **example.com/team/ledger**.
- Debian **.deb**, RPM **.rpm**, or pipeline templates.
- Generic bundles containing versioned ZIP, YAML, or binary files.

A properly managed artifact must answer:

| Question | Component that answers |
|---|---|
| Where is it stored? | Project, location, repository, format |
| What software is this? | Package/image name |
| Which exact version? | Version or immutable image digest |
| Who created it and from which commit? | CI/CD, build provenance, metadata |
| Who can read/write/delete it? | Repository/project IAM roles |
| Are there security issues? | Vulnerability analysis, SBOM, policy |
| When does retention expire? | Retention and cleanup policies |
| Which workloads are using it? | Deployment manifests, Cloud Run revisions, GKE workloads, VM startups |

**Artifact Registry is an artifact distribution repository, not a CI server and not an orchestrator.** It does not build Docker images or deploy services by itself; Cloud Build/GitHub Actions/Jenkins build artifacts, while Cloud Run/GKE/Compute Engine pull artifacts to run them. These services must be combined to build a release pipeline.

~~~mermaid
flowchart LR
    GIT["Git source"] --> CI["CI: build + test"]
    CI --> SCAN["Dependency / image checks"]
    SCAN --> AR["Artifact Registry repository"]
    AR --> RUN["Cloud Run"]
    AR --> GKE["GKE"]
    AR --> VM["Compute Engine"]
    AR --> MVN["Maven/Gradle consumers"]
    LOG["Provenance, SBOM, logs"] -. "Attached to artifact" .-> AR
~~~

### 1.1. A Repository Is Not a Self-Managed Cloud Storage Folder

Artifact Registry has dedicated registry and package manager APIs and protocols. A Docker client uses the Docker Registry API, Maven resolves **groupId/artifactId/version** coordinates, npm queries package metadata, and Generic artifacts use package/version/file operations.

You should not create a Cloud Storage bucket and treat it as an Artifact Registry repository. Cloud Storage is suited for objects/datasets/backups; Artifact Registry adds **package formats, versioning, IAM, tooling, and artifact governance**.

## 2. Data Model: Repository, Package, Version, Tag, and File

~~~mermaid
flowchart TD
    P["Project: commerce-build"] --> L["Location: asia-southeast1"]
    L --> R["Repository: checkout-images\nFormat: Docker; mode: Standard"]
    R --> PKG["Package/image: checkout-api"]
    PKG --> V1["Version: sha256:AAA..."]
    PKG --> V2["Version: sha256:BBB..."]
    V1 --> T1["Tag: 1.2.0"]
    V2 --> T2["Tag: 1.3.0"]
    V2 --> T3["Tag: stable"]
    V2 --> B["Manifest/layers/metadata"]
~~~

General relationships:

- **Project**: administrative, billing, and IAM boundary.
- **Location**: supported region or multi-region, affecting storage locality, latency, and data transfer.
- **Repository**: store with **one artifact format** and one repository mode; has IAM, cleanup, and encryption.
- **Package**: logical name of an artifact, such as an image or module name.
- **Version**: a specific packaged or released content version.
- **Tag**: a convenient reference name for a version in formats that support tags.
- **File/manifest/blob**: physical content and metadata belonging to a version.

Not every format uses tags like Docker does. In Maven, versions are primarily strings such as **1.8.0**; in Generic, versions are explicit package identifiers; in Docker, the actual version can be referenced by its **sha256 digest**.

### 2.1. Repository Name and Fully Qualified Path

For Docker/OCI, the common path format is:

~~~text
LOCATION-docker.pkg.dev/PROJECT_ID/REPOSITORY/IMAGE:TAG
LOCATION-docker.pkg.dev/PROJECT_ID/REPOSITORY/IMAGE@sha256:DIGEST

Example:
asia-southeast1-docker.pkg.dev/commerce-build/checkout-images/checkout-api:1.3.0
~~~

Distinctions:

| Component | Example value | Notes |
|---|---|---|
| LOCATION | asia-southeast1 | Must exist and support the format |
| PROJECT_ID | commerce-build | Project containing the repository, not necessarily the deployment project |
| REPOSITORY | checkout-images | Unique name within project + location |
| IMAGE | checkout-api | Can contain subpaths |
| TAG | 1.3.0 | Mutable by default unless immutable tags are enabled |
| DIGEST | sha256:... | Content identifier of the image manifest |

**Do not confuse the deployment project with the repository project.** A Cloud Run service in project **commerce-prod** can use an image from a repository in **commerce-build** if cross-project read permissions have been granted properly.

### 2.2. Container Image vs. Running Container

- **Image**: packaged data containing layers, filesystem, and metadata.
- **Container instance**: a running process launched by the runtime from an image.
- **Repository**: the place storing images.
- **Deployment**: declares which image runs, resources, environment variables, secrets, networking, and autoscaling.

Editing Java code without building and pushing a new version will not automatically update the image in Artifact Registry. Pushing a new image also **does not automatically** update all running revisions or Pods; a concrete deployment process is required.

## 3. Supported Artifact Formats

A standard repository typically selects **one** format at creation time. Artifact Registry supports the following groups, though individual format capabilities and product stages may vary.

| Format | Artifact/manager | Typical use |
|---|---|---|
| **Docker** | Docker/OCI images, OCI-packaged Helm charts | Cloud Run, GKE, container-running VMs |
| **Maven** | JAR, POM, Java libraries; Maven/Gradle | Internal Java libraries |
| **npm** | Node.js packages | Frontend/component libraries |
| **Python** | Python wheels and source distributions | Python services, tooling, ML dependencies |
| **Go** | Go modules | Go services/backends |
| **Apt** | Debian packages (.deb), apt | Distributing OS packages for Debian/Ubuntu as supported |
| **Yum** | RPM packages (.rpm), yum/dnf | RHEL-compatible Linux |
| **GooGet** | Windows GooGet packages | Distributing certain Windows packages |
| **Kubeflow Pipelines (KFP)** | Pipeline templates | Reusing ML/Vertex AI workflows |
| **Generic** | Arbitrary files with package and version | ZIPs, binaries, configs/artifacts without a dedicated package manager |
| **Ruby (Preview)** | Ruby gems / Bundler | Ruby libraries |
| **Conda (Preview)** | Conda packages | Python/data science environment dependencies |

**Preview/pre-GA** means support scope and operational terms may be limited or subject to change; do not assume every Preview feature has GA-level SLAs, support, and capabilities. Do not assume all formats support **remote** or **virtual** repositories.

### 3.1. Docker Repositories Also Store Helm OCI Charts

Artifact Registry can store **OCI-packaged Helm charts** in a **Docker-format** repository. It is not a Maven-style repository or a separate Helm format in the main format table.

For example, a Helm client can use the registry hostname **LOCATION-docker.pkg.dev** once authenticated and push/pull OCI charts using the corresponding Helm syntax. A chart stored in Artifact Registry **is not automatically deployed to GKE**; Helm upgrade/install or a GitOps system is still required.

### 3.2. Generic Is Not the Default Format for Every Package Manager

**Generic artifacts** fit when a build output does not follow Docker/Maven/npm/Python/Go. Examples include ZIP archives containing config files, internal CLI binaries, or custom-formatted data bundles. Generic packages/versions are immutable upon upload; do not treat it like a bucket where you repeatedly overwrite a file named **latest.zip**.

If an ecosystem manager like Maven or npm already exists, use the dedicated format to get proper dependency resolution and standard metadata.

### 3.3. Distinguishing File Format from Repository Format

For example, a JAR can be:

- A **Maven package** with group/artifact/version coordinates.
- A file stored inside a **Generic artifact**.

Both storage options may contain the exact same bytes, but Maven/Gradle **will not automatically infer dependency metadata** if you simply drop a JAR into a Generic repository. Conversely, a Docker repository is not a target for running **pip install** directly.

## 4. Repository Modes: Standard, Remote, Virtual, and Connector

~~~mermaid
flowchart LR
    BUILD["Build pipeline"] -->|"Direct publish"| STANDARD["Standard\nprivate artifacts"]
    PUB["Public registries\nDocker Hub / Maven Central / PyPI"] --> REMOTE["Remote\nproxy + cache"]
    STANDARD --> VIRTUAL["Virtual\nsingle access point"]
    REMOTE --> VIRTUAL
    CLIENT["Build clients / runtimes"] --> VIRTUAL
    CLIENT2["Direct consumers"] --> STANDARD
    CLIENT3["Direct consumers"] --> REMOTE
~~~

| Mode | Nature | Stores/caches? | When to use? |
|---|---|---|---|
| **Standard** | Primary repository for publishing/uploading artifacts directly | Yes | Releasing internal images/JARs/packages |
| **Remote** | Proxies an upstream and **caches artifacts** on request | Caches fetched upstream items | Controlling external dependency access, reducing repeated downloads |
| **Virtual** | Aggregated endpoint over multiple standard/remote upstreams by priority | Not a direct publish store | Clients want a single registry endpoint with clear source ordering |
| **Connector (Preview)** | Proxies upstream **without caching** | No | Must observe upstream directly or caching is not permitted |

**The connector feature** is in Preview. It is not a standard repository and should not be treated as equivalent to remote (because remote caches artifacts).

### 4.1. Standard Repository

Characteristics:

- Upload/push artifacts into a repository controlled by the owning team.
- Assign **reader/writer/repository admin** permissions directly.
- Choose a single format such as docker, maven, python, or generic.
- Can enable **immutable Docker tags**, cleanup policies, CMEK, and vulnerability scanning depending on capability.
- Suited for internally built software or artifacts promoted across environments.

Example: the checkout pipeline builds an image and pushes **checkout-api:1.3.0** into a standard Docker repository; Cloud Run pulls the image from there to deploy.

### 4.2. Remote Repository

A remote repository uses a supported upstream, for example:

- Docker Hub or external Docker registries.
- Maven Central.
- npmjs.
- Python Package Index (PyPI).
- Go public module proxy.
- Certain OS package sources (Preview) or custom/private upstreams per supported format.

When a client requests a package version not yet in the cache, Artifact Registry can fetch it from upstream and cache it. Subsequent requests use the cached copy per product behavior. The upstream must meet **public HTTPS/internet reachability** requirements, authentication credentials if needed, and supported format criteria. Do not assume it can reach registries inside a private VPC or on-premises site without a public endpoint.

**Remote does not guarantee the upstream is always available or that every public package is safe.** Rate limits, licenses, dependency provenance, vulnerabilities/poisoning, and version pinning must be evaluated. If the upstream changes or the cache misses during an outage, builds can still fail.

### 4.3. Virtual Repository

A virtual repository is **a single access endpoint for multiple upstreams** consisting of standard and remote repositories of the same supported format. You can assign **priority** values to control package lookup order. For example:

~~~text
Maven / Gradle client
      |
      v
maven-unified (VIRTUAL)
      |
      +-- high priority: maven-internal (STANDARD)
      |
      +-- low priority: maven-central-cache (REMOTE)
~~~

When the same package/version appears in both internal and public sources, a priority policy is needed to avoid pulling an unapproved copy. For formats supporting virtual repositories, this helps reduce **dependency confusion** risks compared to configuring package managers to scan unordered URLs.

**Virtual is not a publish target.** Release pipelines must write to a **standard repository**, while consumers use the virtual endpoint if policy permits.

### 4.4. Modes Are Not Supported Equally Across All Formats

Per current documentation, virtual repositories support **Docker, Go, Maven, npm, Python**; Apt/Yum are in **Private Preview** in certain cases. Remote repositories have upstream presets and custom sources that vary by format. Do not infer that GooGet, Generic, or Ruby Preview have full mode parity.

When designing for production, verify **supported formats for repository mode**, regions, and tier conditions. A repository **cannot simply be converted from Docker to Maven** or have its mode changed by renaming: format and mode are structural decisions made at creation time.

## 5. Choosing Location, Project, and Naming Conventions

### 5.1. Location Is an Architectural Decision

Artifact Registry allows creating repositories in supported **regional** and selected **multi-regional locations**. Deciding factors:

- **Data residency:** which country/geographic region artifacts must remain in per policy.
- **Latency/pull:** which region Cloud Run/GKE/Compute Engine primarily run in.
- **Network transfer:** fetching images or packages across regions can incur charges and add latency.
- **Resiliency:** if infrastructure runs in multiple regions, plan appropriate artifact copying/replication.
- **KMS:** if using CMEK, select key/location and permissions as required.
- **VPC Service Controls**, organization policies, and service limits.

**Multi-region does not mean an automatic copy exists in every user-desired region.** Verify location semantics and fallback strategies. If an artifact must exist independently in two regions, build a copy/promotion pipeline and verify digests, rather than assuming one Docker URL works with every location prefix.

### 5.2. Separating Projects and Repositories by Permissions

Example enterprise layout:

| Project | Repository | Format | Permissions/Characteristics |
|---|---|---|---|
| commerce-build | checkout-images | Docker | CI writer, prod runtime reader |
| commerce-build | java-libs | Maven | Java build publisher, dev reader |
| platform-deps | maven-central-cache | Maven remote | Controlled build consumers |
| platform-deps | maven-unified | Maven virtual | Read endpoint for build clients |
| tools-internal | scripts-bundles | Generic | Internal release pipelines |
| commerce-prod | Repo not required | — | Runs Cloud Run/GKE, pulls cross-project |

You do not need a separate repository for every microservice; one repository can serve a group of images sharing the same policy. Conversely, if two groups differ significantly in **IAM/retention/CMEK**, splitting repositories usually reduces risk.

### 5.3. Naming Conventions

Naming examples:

~~~text
Project: commerce-build
Location: asia-southeast1

Repository IDs:
- checkout-images
- java-shared-libs
- npm-internal
- python-internal
- generic-release-bundles

Docker image paths:
- checkout-api:1.3.0
- billing-worker:2026.11.19-commitsha
~~~

Prefer readable names and never put **credentials, PII, or sensitive customer names** in repository descriptions, image names, or tags. Descriptive metadata is typically not encrypted as a secret and can surface in logs or dashboards.

## 6. Preflight: Permissions, APIs, and CLI Environment

To run the gcloud/Docker examples below, you need:

1. An authorized project with the **Artifact Registry API** enabled.
2. Appropriate billing/quotas for storage and retrieval operations.
3. gcloud CLI, Docker client, or package managers installed and logged into the right identity.
4. A supported repository location.
5. Sufficient IAM permissions for each operation: **Reader** to pull, **Writer** to push, **Repository Administrator** to delete artifacts, and **Administrator** to create/manage repositories.
6. Never use a production repository to test tagging/deletion/cleanup without review.
7. Distinguish identities of the **gcloud user**, **Docker credential helper**, **CI service account**, and **runtime service agent**.

### 6.1. Read-Only Checks

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
LOCATION="asia-southeast1"

gcloud auth list
gcloud config list
gcloud services list --enabled --project="$PROJECT_ID"

# List locations supported by Artifact Registry.
gcloud artifacts locations list

# List repositories visible in the project.
gcloud artifacts repositories list --project="$PROJECT_ID"

# Inspect metadata of an existing repository.
gcloud artifacts repositories describe "REPOSITORY_ID" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --format=yaml
~~~

If a user lacks permission to list repositories, do not assume the project has no repositories. A permission granted only at the **repository** level may allow accessing that specific repo without permitting project-wide listing. Check IAM and resource paths rather than "fixing" it by granting `roles/owner`.

## 7. Hands-on A — Creating a Docker Standard Repository

**The commands in this section modify Google Cloud resources and may incur charges.** Run them only in an authorized learning project; do not create or delete production repositories for testing.

### 7.1. Choose Lab Parameters

| Field | Lab value | Must verify |
|---|---|---|
| Project | YOUR_PROJECT_ID | Has billing and repo creation permission |
| Location | asia-southeast1 | Supported by Artifact Registry |
| Repository | app-images-lab | Does not already exist in project/location |
| Format | docker | Docker/OCI images |
| Mode | standard | CI has push permission |
| Image name | checkout-api | Optional subpath |
| Tag | 1.0.0 | Build-identifying version |
| Runtime | Cloud Run or GKE in lab project | Has pull permission via proper identity |

### 7.2. Create the Repository

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
LOCATION="asia-southeast1"
REPOSITORY="app-images-lab"

# MUTATING — create a standard Docker repository.
gcloud artifacts repositories create "$REPOSITORY" \
  --project="$PROJECT_ID" \
  --repository-format=docker \
  --location="$LOCATION" \
  --description="Docker images for the training application"

# READ-ONLY — verify format, mode, location, and encryption.
gcloud artifacts repositories describe "$REPOSITORY" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --format=yaml
~~~

**Standard is the default mode** if remote/virtual is not selected. If tags must never change after release, consider the **--immutable-tags** flag when creating the repository or updating settings per proper permissions and workflow. Before enabling it, check the impact on pipelines currently reusing mutable tags like **latest** or **staging**.

### 7.3. Prepare Docker Client Authentication

~~~bash
# UPDATE CLIENT CONFIG on the machine running Docker.
gcloud auth configure-docker "$LOCATION-docker.pkg.dev"
~~~

This command configures the **Docker credential helper** for the Artifact Registry hostname in the Docker config. It **does not grant IAM permissions by itself**. The user must hold the corresponding push/pull permissions, such as Writer for push and Reader for pull.

Docker typically reads credentials from the user's **~/.docker/config.json**. If you run **sudo docker**, Docker may read root's config instead of the user's; this is a common cause of 401 errors even when `gcloud auth` succeeded.

For automation, prefer **Workload Identity Federation**, workload-attached service accounts, and short-lived tokens. Never commit JSON service account keys or plaintext Docker passwords to Git.

### 7.4. Build and Push a Java Image

Assume the Java project has a **Dockerfile** and builds/tests cleanly. Minimal Dockerfile example:

~~~dockerfile
# Example requires target/checkout-api.jar to be built beforehand.
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY target/checkout-api.jar app.jar
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Notes:

- Use a **verified base image** and pin by digest when reproducibility is required.
- A **non-root USER** reduces the blast radius of application flaws.
- Create a **.dockerignore** to avoid copying `.git`, credentials, and unnecessary build files.
- **EXPOSE** is metadata; it does not automatically open VPC firewalls or Cloud Run ingress.
- In production, CI must run unit/integration tests, inspect dependencies, and generate provenance before pushing.

Example commands:

~~~bash
# Assume you are in a Java project directory with a Dockerfile.
# mvn verify runs phases/tests according to the project configuration.
mvn -B verify

IMAGE_BASE="$LOCATION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/checkout-api"
TAG="1.0.0"

# MUTATING on local Docker daemon: build the container image.
docker build -t "checkout-api:$TAG" .

# Tag the image with the Artifact Registry path.
docker tag "checkout-api:$TAG" "$IMAGE_BASE:$TAG"

# MUTATING on Artifact Registry: upload image/layers.
docker push "$IMAGE_BASE:$TAG"
~~~

Avoid using **latest** as the sole identifier for a release. If a tag is reused in a repository allowing mutable tags, **latest** can silently point to a different digest without the deployer noticing. A release should carry a version/commit tag and record the digest returned after pushing.

### 7.5. Read Back the Image and Digest

~~~bash
# READ-ONLY — list images/packages in the repo.
gcloud artifacts docker images list \
  "$LOCATION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY"

# READ-ONLY — view versions and tags of an image.
gcloud artifacts docker images list "$IMAGE_BASE" \
  --include-tags

# READ-ONLY/LOCAL DOWNLOAD — pull the exact version to test.
docker pull "$IMAGE_BASE:$TAG"
~~~

Output showing **DIGEST sha256:...** identifies a specific content version. For production deployments requiring reproducibility, consider **deploying by image@sha256:DIGEST** rather than tag alone. For example:

~~~text
Mutable tag (if immutable tags are not enabled on the repository):
asia-southeast1-docker.pkg.dev/commerce-build/checkout-images/checkout-api:stable

Content-specific reference:
asia-southeast1-docker.pkg.dev/commerce-build/checkout-images/checkout-api@sha256:<FULL_DIGEST>
~~~

Do not use the literal string **sha256:<FULL_DIGEST>** as an image reference because it is a placeholder. The digest must be taken from the actual build/push/Artifact Registry output of the real image.

### 7.6. Tags Are Not Digests

| Property | Docker tag | Digest |
|---|---|---|
| Example | 1.3.0, stable | sha256:... |
| Identifier | Logical name pointing to an image version | Hash of the image manifest |
| Can the target change? | **Yes**, if mutable | A digest cannot be changed to point to different content |
| Human-friendly? | Very convenient | Long, hard to memorize |
| Reliable for exact deployments? | Requires policy controls | Better suited |
| Guarantees bug-free app? | No | No; scanning/testing/review are still needed |

**Immutable tags** is a setting **on a Docker repository**. When enabled, a tag cannot be repointed to another digest, and tagged images have deletion/untagging restrictions. Cleanup and rollback strategies must be compatible: do not overwrite an existing tag—use new release tags and verified digests.

## 8. IAM for Repositories and Release Pipelines

IAM governs who can view, download, upload, or delete artifacts. Do not confuse the ability to **log in with gcloud** with actual permissions on a repository.

| Role | Role ID | Typical usage |
|---|---|---|
| Artifact Registry Reader | **roles/artifactregistry.reader** | View metadata and pull/download |
| Artifact Registry Writer | **roles/artifactregistry.writer** | Read and publish/upload |
| Artifact Registry Repository Administrator | **roles/artifactregistry.repoAdmin** | Read, write, and delete artifacts |
| Artifact Registry Administrator | **roles/artifactregistry.admin** | Create/manage repositories and artifacts |

### 8.1. Grant Permissions at the Repository or Project Level?

- **Repository-level IAM**: fits when `checkout-ci` may push only to **checkout-images**, not modify **java-libs**.
- **Project-level IAM**: fits when a service account genuinely needs identical permissions across **every repository** in the project.
- **Cross-project IAM**: a runtime in project B pulls from a repository in project A; grant Reader on **repository A** to the **actual principal performing the pull**.
- **Virtual repositories**: a Reader can read upstreams through the virtual endpoint per service mechanics; review the expanded access scope.

Example assignment principles:

~~~text
build/checkout-ci:
  Writer on checkout-images
  No project Admin

deploy/production:
  Reader on checkout-images
  No Writer

platform/registry-admin:
  Admin on approved repositories or scope
  Permitted to configure cleanup/CMEK/visibility appropriately

developer:
  Reader on needed repositories
  Writer only on dev repos if permitted
~~~

### 8.2. gcloud IAM Binding Example (Mutating)

~~~bash
# MUTATING IAM — execute only with the right principal and approval.
READER_SERVICE_ACCOUNT="deployer@YOUR_RUNTIME_PROJECT.iam.gserviceaccount.com"

gcloud artifacts repositories add-iam-policy-binding "$REPOSITORY" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --member="serviceAccount:$READER_SERVICE_ACCOUNT" \
  --role="roles/artifactregistry.reader"

# READ-ONLY — verify who has permissions on the repository.
gcloud artifacts repositories get-iam-policy "$REPOSITORY" \
  --project="$PROJECT_ID" \
  --location="$LOCATION"
~~~

Be careful: in certain Cloud Run or GKE cross-project deployments, the **image-pulling identity** is a **service agent or node service account**, which may **differ from the container's runtime service account**. Check the product/deployment documentation and inspect the actual principal performing the pull; do not guess and grant Reader to every service account.

### 8.3. Authentication on Workstations, CI, and Runtime

| Environment | Implementation direction |
|---|---|
| Developer laptop | gcloud user login, Docker credential helper, Maven/Gradle credential helper |
| Cloud Build | Identify exact build service account and Writer/Reader permissions |
| GitHub Actions/Jenkins outside GCP | Workload Identity Federation and appropriate service account impersonation |
| GKE | Node/cluster image pull identity with Reader; separate workload IAM |
| Cloud Run | Deployment/image pull path and project service agent permissions; runtime identity is not automatically the same |
| Compute Engine | VM service account, legacy scopes/configs, and required repo permissions |

Avoid releasing from CI using **long-lived JSON service account keys** when short-lived identities are available. If keys must be used, store them outside the repo with Secret Manager controls, rotation, and auditing.

### 8.4. Rule of Separating Builders from Deployers

Build pipelines need **Writer** and do not necessarily need **Repository Administrator**. Runtimes only need **Reader**. Those with **Delete** permissions or ability to toggle immutable tags/cleanup belong to the registry administration group. This separation reduces the risk of:

- Compromised runtime tokens injecting malicious images.
- A buggy CI job wiping all release artifacts.
- A developer accidentally overwriting a production tag.
- An untested cleanup policy deleting actively deployed artifacts.

## 9. Maven/Gradle Repositories for Java

For Java modules, Artifact Registry **Maven format** is useful for publishing shared libraries under **groupId:artifactId:version** coordinates.

### 9.1. Java Package Model

~~~text
Project: commerce-build
Repository: java-shared-libs
Format: maven
Location: asia-southeast1

Package coordinates:
com.example.platform:payment-sdk:1.8.0

Maven repository endpoint:
artifactregistry://asia-southeast1-maven.pkg.dev/commerce-build/java-shared-libs
~~~

A Maven package includes POM metadata, a JAR, optionally sources/javadoc, and related files. Maven/Gradle use that metadata to resolve dependencies and transitive dependencies; do not use a Generic repository when the primary goal is **mvn dependency resolution**.

### 9.2. Create a Maven Repository

~~~bash
# MUTATING — create a Maven standard repository.
gcloud artifacts repositories create "java-shared-libs" \
  --project="$PROJECT_ID" \
  --repository-format=maven \
  --location="$LOCATION" \
  --description="Java libraries for internal builds"

# READ-ONLY — print Maven configuration for the repo.
gcloud artifacts print-settings mvn \
  --project="$PROJECT_ID" \
  --repository="java-shared-libs" \
  --location="$LOCATION"

# READ-ONLY — print Gradle configuration.
gcloud artifacts print-settings gradle \
  --project="$PROJECT_ID" \
  --repository="java-shared-libs" \
  --location="$LOCATION"
~~~

The **print-settings** output shows how to configure Maven **distributionManagement/repositories** or Gradle **publishing/repositories** and credential helpers. Use the CLI output matching your installed version rather than copying hardcoded plugin versions from tutorials.

### 9.3. Maven and Gradle Authentication

Artifact Registry supports **Maven wagon** and **Gradle plugin** integrations to retrieve credentials via Application Default Credentials (ADC)/gcloud where appropriate. Principles:

- Developers sign in with personal accounts granted appropriate Reader/Writer roles.
- CI uses a service account with explicit permissions, preferring short-lived credentials.
- Never place passwords/JSON keys into **pom.xml, settings.xml, or build.gradle** and commit them.
- Specify repository ID/location and package version policy clearly.
- Release artifacts should be published from tested builds with provenance.

### 9.4. What Do SNAPSHOT and RELEASE Mean?

Maven **1.9.0-SNAPSHOT** represents an in-development version that may be rebuilt multiple times. Maven **1.9.0** is typically a release. When creating a Maven repository, you can configure a corresponding **version policy** per product options; remote Maven repositories have limitations around snapshot/release policies.

Organizations should:

- Separate releases and snapshots if IAM/retention requirements differ.
- Never treat SNAPSHOTs as stable artifacts for production deployment.
- Prevent overwriting release versions when workflows require immutability.
- Clean up old SNAPSHOTs using tested cleanup policies without breaking active dependencies.

### 9.5. Kotlin/Gradle Does Not Change the Format

Java/Kotlin projects built with Gradle can still publish **Maven-compatible artifacts** to a **maven** format repository. The format is chosen by artifact distribution protocol, not necessarily the source code language.

## 10. npm, Python, Go, and Generic Artifacts

### 10.1. npm Repository

Node.js packages have names and versions such as **@commerce/ui-kit@2.2.0**. You can create a standard npm repo:

~~~bash
gcloud artifacts repositories create "npm-internal" \
  --project="$PROJECT_ID" \
  --repository-format=npm \
  --location="$LOCATION"

# READ-ONLY — retrieve .npmrc / scope setup instructions.
gcloud artifacts print-settings npm \
  --project="$PROJECT_ID" \
  --repository="npm-internal" \
  --location="$LOCATION" \
  --scope="@commerce"
~~~

After configuring authentication and **package.json** properly, you can run **npm publish** to the authorized repository. Never put real tokens in a **.npmrc** committed to Git. Avoid defining arbitrary multiple registry URLs that cause private dependencies to be fetched mistakenly from public registries.

### 10.2. Python Repository

The Python format fits wheels and source distributions. Tools like **pip**, **twine**, and keyring backends can be configured for install/upload.

~~~bash
gcloud artifacts repositories create "python-internal" \
  --project="$PROJECT_ID" \
  --repository-format=python \
  --location="$LOCATION"

# READ-ONLY — instructions for index-url, twine, and auth.
gcloud artifacts print-settings python \
  --project="$PROJECT_ID" \
  --repository="python-internal" \
  --location="$LOCATION"
~~~

For pip, the private simple index URL has the form:

~~~text
https://LOCATION-python.pkg.dev/PROJECT_ID/REPOSITORY/simple/
~~~

Using **keyrings.google-artifactregistry-auth** and appropriate helpers avoids embedding passwords in pip configs. Per Google recommendations, when both private and public dependencies are needed, use a **virtual repository** instead of listing a private index alongside PyPI via **extra-index-url**, because pip does not enforce private-index preference; an attacker can publish a public package with the same name and a higher version (**dependency confusion**).

### 10.3. Go Repository

Go modules follow a module path/version structure and use **GOPROXY**. Example:

~~~bash
gcloud artifacts repositories create "go-internal" \
  --project="$PROJECT_ID" \
  --repository-format=go \
  --location="$LOCATION"

# READ-ONLY — inspect module repository info.
gcloud artifacts repositories describe "go-internal" \
  --project="$PROJECT_ID" \
  --location="$LOCATION"
~~~

To consume private modules, configure **GOPROXY**, credential helpers, and **GONOSUMDB** matching the private module paths. Be careful with **GOPROXY** configurations that fall back to public proxies: this can leak private module names or fetch from unintended sources. For organizations requiring strict control, prefer proxy/virtual endpoints and approved policies.

### 10.4. Generic Repositories and Versioned File Uploads

~~~bash
gcloud artifacts repositories create "generic-bundles" \
  --project="$PROJECT_ID" \
  --repository-format=generic \
  --location="$LOCATION"

# MUTATING — use only built and approved files.
gcloud artifacts generic upload \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --repository="generic-bundles" \
  --package="deploy-manifests" \
  --version="1.0.0" \
  --source="./deploy-manifests.zip"

# READ-ONLY — verify files in the repo.
gcloud artifacts files list \
  --project="$PROJECT_ID" \
  --repository="generic-bundles" \
  --location="$LOCATION"
~~~

Generic packages/versions enforce **immutable versions**; an existing version cannot be overwritten. To publish a new build, publish under a **new version**. Do not use Generic as a place to repeatedly overwrite files at the same version.

### 10.5. Apt/Yum, GooGet, KFP, Ruby, and Conda

- **Apt** serves Debian packages, requiring apt source configuration and package manager authentication per documentation.
- **Yum/DNF** serves RPM packages, requiring repository configuration and appropriate package signatures/sources.
- **GooGet** applies to certain Windows packages.
- **KFP** stores Kubeflow pipeline templates for suitable ML/Vertex AI workflows.
- **Ruby gems and Conda packages** are available in **Preview** per supported formats documentation.

Never put **unverified-source** `apt`/`yum` or `pip` commands into production startup scripts. Pin versions, authenticate repositories, verify signatures/checksums, and plan fallbacks when upstreams are unavailable.

## 11. Hands-on B — Remote and Virtual Repositories for Dependencies

This is an advanced section. Before using remote/virtual repositories, clearly define **upstream sources, location, format, IAM, and priority rules**. The commands below can create real resources; do not run them in a production project without approval.

### 11.1. Remote Repository Fetching Dependencies from Maven Central

Suppose a Java team wants to cache public packages from Maven Central so all build clients access them through Artifact Registry.

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
LOCATION="asia-southeast1"

# MUTATING — create a remote Maven repository using a preset upstream.
gcloud artifacts repositories create "maven-central-remote" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --repository-format=maven \
  --mode=remote-repository \
  --remote-mvn-repo=MAVEN-CENTRAL \
  --description="Cache of Maven Central packages"

# READ-ONLY — verify mode, format, and remote config.
gcloud artifacts repositories describe "maven-central-remote" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --format=yaml
~~~

This is not a standard Maven repository for a build pipeline to **publish internal JARs** into. It acts as an **upstream proxy/cache** per policy. If a package is not yet cached and Maven Central is unavailable, fetching can fail. Verify dependency pinning and build recovery plans.

### 11.2. Remote Docker Repository for Base Images

Suppose a team wants to pull base images from Docker Hub through Artifact Registry instead of clients reaching out directly.

~~~bash
# MUTATING — create a remote Docker repository.
gcloud artifacts repositories create "dockerhub-remote" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --repository-format=docker \
  --mode=remote-repository \
  --remote-docker-repo=DOCKER-HUB \
  --description="Docker Hub proxy cache"
~~~

Depending on Docker Hub policies and rate limits, **upstream credentials** stored in **Secret Manager** may be needed. Never pass raw passwords/tokens on the shell command line or write them into documentation. Remote repositories also have private-upstream connectivity limits: upstreams without a public HTTPS endpoint or residing solely inside a VPC/on-premises network are not automatically proxied directly.

**Note:** when using remote images, clients must reference the **remote repository path**, not **docker.io** directly. If a Dockerfile still uses **FROM docker.io/library/...** without a matching rewrite/mirror mechanism, builds may keep reaching Docker Hub directly and bypass the enterprise cache.

### 11.3. Virtual Repository with Upstream Priorities

Assume in the same location/format you have:

- **java-shared-libs** — standard Maven repository containing internal packages.
- **maven-central-remote** — remote Maven repository caching Maven Central.

Creating the virtual repository **maven-unified** provides a single endpoint for Gradle/Maven consumers.

~~~json
[
  {
    "id": "internal",
    "repository": "projects/YOUR_PROJECT_ID/locations/asia-southeast1/repositories/java-shared-libs",
    "priority": 100
  },
  {
    "id": "public-cache",
    "repository": "projects/YOUR_PROJECT_ID/locations/asia-southeast1/repositories/maven-central-remote",
    "priority": 50
  }
]
~~~

Save this JSON as **upstream-policies.json** in your deployment working directory once approved. This is an **example configuration file in the lesson**, not an instruction to alter your learning module's working repository.

~~~bash
# MUTATING — create a virtual repository with the reviewed JSON.
gcloud artifacts repositories create "maven-unified" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --repository-format=maven \
  --mode=virtual-repository \
  --upstream-policy-file="upstream-policies.json" \
  --description="Unified Maven dependencies"

# READ-ONLY — verify upstream policies.
gcloud artifacts repositories describe "maven-unified" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --format=yaml
~~~

**Priority in a virtual repository: LARGER numbers have higher priority.** In this example, **100** is searched before **50**. Do not confuse this with **VPC firewall rule priority**, where **smaller numbers** have higher priority. If two upstreams share the same priority and both contain a package/version, the server may choose either one.

**Important condition:** virtual repository upstreams must have the **same format** and **same location** as the virtual repository, though they may reside in a different project if IAM and policy permit. Virtual repositories can point to standard, remote, or virtual upstreams per product rules.

### 11.4. Distinguishing Source Priority from Version Selection

When requesting a **specific version** present in multiple upstreams, a virtual repository can prefer the higher-priority source. However, when a package manager is allowed to pick the "latest/highest version" without version pinning, results may differ from expectations: a lower-priority repository containing a higher version can still influence dependency resolution.

Therefore, you should:

- Pin dependencies via lockfiles, exact versions, and digests/hashes per ecosystem.
- Use one consistent virtual endpoint instead of arbitrarily configuring multiple public sources.
- Establish internal package naming conventions to avoid collisions with public packages.
- Verify upstream priorities, provenance, licenses, and approved dependencies.
- For Python, **do not use extra-index-url** to mix public PyPI with a private index when strict private-source priority is required; pip does not enforce URL priority the way many people assume.

## 12. Artifact Lifecycle, Immutability, and Release Promotion

### 12.1. Mutable Image Tags Can Cause Non-Reproducible Deployments

Suppose build A is pushed as:

~~~text
checkout-api:stable -> sha256:AAA
~~~

The next day build B overwrites the tag:

~~~text
checkout-api:stable -> sha256:BBB
~~~

A new deployment referencing **stable** may pull B, while a running Pod or an older rollback uses A. If operations only recorded the tag, they may be unable to reproduce the exact running build.

A sound release policy:

1. CI builds and tests from a known **commit SHA**.
2. Assign clear version/commit image tags.
3. Push to an authorized standard repository.
4. Capture the **full sha256 digest** after pushing.
5. Scan/attest per policy.
6. Promote **that exact verified digest** to staging/production.
7. Store artifact provenance and deployment revisions for rollback.

### 12.2. Docker Immutable Tags

A repository can enable **immutable tags** to prevent updating a tag to point to a different image digest. Example:

~~~bash
# MUTATING — use only when the release design is ready.
# At repository creation time:
gcloud artifacts repositories create "prod-images" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --repository-format=docker \
  --immutable-tags
~~~

Enabling immutable tags has lifecycle consequences:

- You cannot push an existing tag onto a new digest.
- You cannot arbitrarily untag an already-tagged image.
- Deleting tagged images is restricted while immutable tags are enabled.
- Cleanup policies must be designed to be compatible with those constraints.

Do not enable immutable tags on a repository still using a **latest overwrite** release model without updating the pipeline and rollback plan. Use versioned tags and deploy by digest instead.

### 12.3. Promotion vs. Rebuilding

Across dev, staging, and prod, promote the **verified artifact** (same content digest) instead of rebuilding from source and assuming the bytes will match. Rebuilding can change:

- A base image tag resolving to a different digest.
- New dependency snapshots/public packages.
- Build tools, timestamps, and CI environment.
- Compilers/OS packages or build configurations.

Reproducible builds are an important goal, but a straightforward way to avoid environment drift is **promoting the same digest**. When copying images across repositories/locations, verify digests/signers/provenance with supported tools; do not assume copying preserves every manifest/metadata detail in all cases.

### 12.4. Artifact Registry Does Not Automatically Roll Back Cloud Run/GKE

- **Cloud Run:** releases a new revision based on the chosen image; rollback requires shifting traffic/revisions via Cloud Run tooling.
- **GKE:** deployment manifests/Helm/GitOps specify the image; rollback requires updating the Deployment/StatefulSet appropriately and verifying readiness.
- **Compute Engine:** VM startup scripts/container runtimes must specify the image reference and restart/update properly.

If you delete a digest still needed by a runtime pull or rollback, the next deployment can fail. This ties directly into retention and cleanup policies.

## 13. Cleanup Policies and Retention

Artifact Registry can automatically remove unneeded artifact versions using **cleanup policies**. This helps reduce storage usage, but accidental deletion can break build/deployment pipelines or rollbacks.

### 13.1. Common Policy Types

| Policy type | Purpose | Risk to avoid |
|---|---|---|
| **Conditional delete** | Deletes versions matching conditions like age or untagged state | Deleting still-used versions or artifacts in formats without tag support |
| **Conditional keep** | Protects versions matching tag/version/package prefixes | Over-protecting too broad a set, inflating costs |
| **Keep most recent versions** | Keeps the latest N versions per package | Insufficient for older rollbacks or long-lived releases |

Conditions can be based on **tagState, tagPrefixes, versionNamePrefixes, packageNamePrefixes, olderThan/newerThan** per documentation, depending on format. For formats that do not support tags, artifacts may be treated as **untagged** in cleanup semantics. Repositories with **immutable Docker tags** have specific constraints on deleting tagged images.

### 13.2. Safe Workflow for Creating Cleanup Policies

~~~mermaid
flowchart TD
    REQ["Need to cut cost / retain releases"] --> INVENT["Inventory image versions + consumers"]
    INVENT --> RULE["Design keep/delete policies"]
    RULE --> DRY["Dry run, inspect audit/logs"]
    DRY --> REVIEW{"Owner & SRE approved?"}
    REVIEW -- "No" --> RULE
    REVIEW -- "Yes" --> APPLY["Apply cleanup"]
    APPLY --> VERIFY["Verify rollback digests still exist"]
    VERIFY --> COST["Monitor storage and cost"]
~~~

Do not treat version cleanup as instantaneous. Per documentation, cleanup jobs run periodically, and changes may take **roughly a day** to take effect. Cleanup policies apply to **standard repositories**, not directly to virtual repositories or an entire project.

**Special caution:** keeping the "5 most recent versions" does not guarantee that a production image running from six months ago will be preserved. Maintain an inventory of deployed digests or explicit retention policies for approved releases and recovery.

### 13.3. Illustrative Policy Example

~~~json
[
  {
    "name": "delete-untagged-old",
    "action": {"type": "Delete"},
    "condition": {
      "tagState": "untagged",
      "olderThan": "30d"
    }
  },
  {
    "name": "keep-prod-tags",
    "action": {"type": "Keep"},
    "condition": {
      "tagState": "tagged",
      "tagPrefixes": ["prod-", "release-"]
    }
  }
]
~~~

This is an **example configuration for analysis**; do not apply it before verifying format support, interaction between keep/delete rules, and actual tag states. Administrators must use **dry run** before enabling real deletion and ensure deployed digests and rollback requirements are protected.

### 13.4. Why a Registry Is Not a Backup System by Itself

A repository can be deleted due to misconfigured IAM, accidental admin actions, or aggressive retention policies. Artifact Registry manages artifact distribution; it does not automatically provide an independent backup isolated from all changes.

If **disaster recovery** is required, consider:

- Keeping reproducible source code and build recipes.
- Replicating critical artifacts to another location/repository per policy.
- Storing SBOMs, signatures/provenance, and release manifests.
- Practicing pulling images from the DR repository and redeploying.
- Restricting IAM Administrator/Repo Admin, deletion, and cleanup policy permissions.

Even a signed and scanned artifact can lose availability if a repository or region suffers an outage. Operational plans must match RTO and compliance requirements.

## 14. Software Supply Chain Security

Artifact Registry is a key link in the **software supply chain**, but a successful push does not prove an artifact is safe or trustworthy.

### 14.1. Common Risks

| Risk | Example | Appropriate control |
|---|---|---|
| **Dependency confusion** | Public package with the same name as an internal package resolves first | Virtual repository, upstream priority, version pinning |
| **Typosquatting** | Package name closely resembling a legitimate library | Allowlists, dependency review, provenance checks |
| **Mutable tag** | `stable` gets overwritten with a different digest | Immutable tags, digest pinning |
| **Vulnerable image** | Base image contains critical CVEs | Vulnerability scanning, base image updates, remediation SLAs |
| **Secrets in image** | ENV/build layers contain API keys | Secret scanning, never COPY credentials |
| **Malicious build pipeline** | Compromised CI service account holds Writer | WIF, least privilege, signed provenance, branch protection |
| **Deleting critical artifacts** | Cleanup removes an actively running release | Dry runs, keep policies, deployed digest inventory |
| **Untrusted upstream** | Remote automatically fetches a poisoned version | Pin versions, signatures/hashes, source policy |
| **Overly broad IAM** | Runtime service account has `repoAdmin` | Separate Reader/Writer/RepoAdmin/Admin |
| **Wrong location boundary** | Build runs in a region outside allowed data boundaries | Location policies, egress controls, repo replication |

### 14.2. Artifact Analysis and Vulnerability Scanning

Artifact Registry integrates with **Artifact Analysis** and supported vulnerability scanning mechanisms for container images. You can inspect images for OS/language packages with reported CVEs, severity levels, and scan timestamps.

However, keep these distinctions in mind:

- A **scan result** is a point-in-time snapshot, not a certificate of zero vulnerabilities.
- A new CVE may be disclosed after an image is already deployed; continuous monitoring and base image rebuilds are required.
- A package vulnerability does not always mean it is exploitable in your workload; assess reachability/exposure and risk appetite.
- Enabling the **Container Scanning API** can incur scanning charges; check project status and repository settings.
- Scanning does not detect everything—such as business logic flaws, accidentally embedded secrets, misconfigured IAM, or missing network policies.

### 14.3. SBOMs, Provenance, Signatures, and Binary Authorization

An **SBOM (Software Bill of Materials)** lists the software components inside an artifact, helping assess impact when new CVEs appear. **Build provenance** describes which source/commit, builder, and workflow produced an artifact. OCI attachments can store image-related metadata such as SBOMs and scan outputs when supported by tooling.

You can use **Binary Authorization** and appropriate policy enforcement on GKE/Cloud Run or supported environments to allow deploying only approved images. Do not conflate:

- Image exists in Artifact Registry.
- Image passed vulnerability scanning.
- Image has signed/verified provenance.
- Image is authorized by policy for deployment.

These are **four separable conditions**. Production pipelines should combine required verification layers rather than assuming Artifact Registry blocks dangerous images automatically.

### 14.4. Encryption and Key Governance

Repository artifacts are encrypted at rest using Google Cloud mechanisms. For specific compliance needs, you can configure a **Cloud KMS Customer-Managed Encryption Key (CMEK)** when creating a repository within supported scopes/features.

Before using CMEK:

1. Verify KMS key location and repository location compatibility per product rules.
2. Grant appropriate permissions for the Artifact Registry service agent to use the key.
3. Define key rotation/disable/destroy policies and understand their impact on artifact pulls.
4. Separate KMS Admin permissions from CI operators.
5. Rehearse key-access loss scenarios without destroying production artifacts.

**Never casually disable or destroy a KMS key** protecting a repository: data can become inaccessible. Repository metadata such as descriptions/tags are not a place to store secrets.

### 14.5. VPC Service Controls and Private Access

Organizations use **VPC Service Controls**, private network egress, and organization policies to reduce data exfiltration risk. Even so, Artifact Registry is an API-endpoint service: clients still need DNS, routes/Private Google Access if applicable, credentials, and IAM. Placing a repository in a region does not automatically mean "only that VPC network can read it."

With remote repositories, external upstream connections must also satisfy product-supported egress/upstream policies. Do not apply a single VPC firewall rule set to VMs and assume every package retrieval path through Artifact Registry is covered.

## 15. Observability, Auditing, and Cost

### 15.1. Signals to Monitor

| Category | Metrics/Data | Meaning |
|---|---|---|
| Repository inventory | Repo format/mode/location, IAM, artifact versions | Asset and permission inventory |
| Build/deploy | Build ID, commit SHA, pushed digest, deployment revision | Release traceability |
| Security | Vulnerability findings, SBOMs, attestations | Risk detection |
| Availability | Pull/push failures, upstream timeouts, error responses | Ability to deliver artifacts to CI/runtime |
| Storage | Bytes/versions, tagged vs. untagged, cleanup results | Capacity management |
| Cost | Storage, egress, scanning, build, and KMS charges | FinOps |
| Audit | IAM changes, repository create/update/delete, cleanup changes | Investigation and compliance |
| Cross-project | Service agents/readers accessing another project's repo | Least privilege |

**Cloud Audit Logs** help determine who created/deleted/modified repositories and permissions across supported log/API types. Registry activity must be read through the corresponding logging mechanisms; do not assume every pull request appears in a single table without checking Data Access logging and log viewing permissions.

### 15.2. Cost Is More Than Just Image Size

Artifact Registry can incur costs from:

- Volume of **stored artifacts and remote cached content**.
- **Network transfer/egress** traffic depending on location/destination and pricing.
- Number of requests or operations per the applicable pricing model.
- **Vulnerability scanning** when billable APIs/features are enabled.
- Cloud Build/GKE/Cloud Run, KMS, Pub/Sub, Cloud Logging, or services outside Artifact Registry.
- CI retries, large image layers, cache invalidation, and unoptimized cross-region pulls.

Do not assume deleting a tag immediately frees the entire image size; layers may still be shared or versions still referenced. Inspect actual billing/storage metrics, wait for cleanup jobs to run, and reconcile invoices by **Service/SKU** rather than estimating from tag counts alone.

### 15.3. Sensible Optimization

- Use multi-stage Docker builds, minimal base images, and **.dockerignore**.
- Pin dependencies and base image digests for stable builds.
- Choose a region aligned with runtimes/CI and data residency rules.
- Use policy-governed remote caches to avoid redundant upstream downloads.
- Clean up untagged/old versions in a controlled way, preserving actively deployed or rollback digests.
- Tag owners/cost centers using repository labels/metadata where supported.
- Periodically review unused repositories, Writer/RepoAdmin bindings, and scanning charges.

**Never trade away security for savings by disabling vulnerability scanning or deleting rollback versions** without an explicit risk and recovery decision.

## 16. Troubleshooting: Common Errors

### 16.1. Diagnostic Matrix

| Symptom | Common cause | How to check |
|---|---|---|
| **401 Unauthorized** on Docker pull/push | Docker credential helper wrong hostname, expired token, or not logged in | docker config, `gcloud auth list`, location hostname |
| **403 Permission Denied** | Identity lacks Reader/Writer or policy blocks access | Repository IAM, right project/SA, service agent |
| **Repository not found** | Wrong project, location, repo ID, or missing view permission | `gcloud artifacts repositories describe`, image path |
| **Unsupported format** | Pushing Docker image to Maven repo or wrong npm registry URL | Describe repository format/mode |
| **Cannot push to virtual/remote** | Using a pull/aggregation-only endpoint | Publish to standard repository |
| **Tag push rejected** | Immutable tags, tag already exists, or naming policy | Describe immutable settings, version naming |
| **Maven dependency won't resolve** | Wrong repo URL/credentials, snapshot/release policy, or missing version | `print-settings mvn/gradle`, artifact version, auth helper |
| **Python pip installs wrong public package** | Multiple indexes configured, higher public version picked | Check pip config, use virtual endpoint and pinning |
| **npm publish 403** | Scope, `.npmrc`, credentials, or Writer IAM | `print-settings npm`, package scope, and token |
| **First remote pull fails** | Upstream timeout, rate limit, credentials, unsupported URL | Remote config, Secret Manager, upstream health |
| **Virtual returns wrong package** | Priority/name/version collision across upstreams, unpinned | Policy JSON, version lock, source logs |
| **GKE image pull failed** | Node SA lacks Reader, missing secret, or wrong image path | Pod events, node/project IAM, image digest |
| **Cloud Run deploy image failed** | Cross-project pull lacks service agent permission or missing image | Cloud Run deploy errors, Artifact Registry IAM |
| **No CVE scan results** | Scanning API/option disabled, unsupported asset, or scan pending | Artifact Analysis config, scan status |
| **Cleanup didn't delete immediately** | Periodic schedule / dry-run mode | Repo cleanup settings, wait for job/inspect logs |
| **Cleanup deleted wrong version** | Wrong condition/tagState/keep rule | Incident response, find copy/restore/rebuild |
| **Storage charges don't drop** | Shared layers, other versions retained, billing lag | Version inventory, storage metrics, Billing |
| **CMEK repo unreadable** | Key disabled, wrong KMS IAM, or location mismatch | KMS key status, service agent access |
| **Cannot pull over private network** | DNS, private access/VPC-SC, proxy, or perimeter policy | API endpoint connectivity and corresponding logs |

### 16.2. Investigation Procedure Without Broadening Permissions Recklessly

1. Confirm the **operation**: create repo, list, push, pull, delete, or deploy.
2. Identify the **actual identity**: gcloud user, Docker helper, CI service account, GKE node SA, or Cloud Run service agent.
3. Verify **project/location/repository/format/mode/image/version**.
4. Read the exact HTTP error (401 differs from 403), timestamps, logs, and IAM policy.
5. Check upstreams if remote/virtual; verify priority/versions.
6. Check tags/digests and confirm the artifact version actually exists.
7. Retry with the **correct identity and path** in the lab project; never grant Owner just to "make it work quickly."
8. Document the root cause, minimal fix, impact, and steps to prevent recurrence.

### 16.3. Read-Only Command Set for Investigation

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
LOCATION="asia-southeast1"
REPOSITORY="app-images-lab"

gcloud auth list

gcloud artifacts repositories describe "$REPOSITORY" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --format=yaml

gcloud artifacts repositories get-iam-policy "$REPOSITORY" \
  --project="$PROJECT_ID" \
  --location="$LOCATION"

gcloud artifacts packages list \
  --project="$PROJECT_ID" \
  --repository="$REPOSITORY" \
  --location="$LOCATION"

gcloud artifacts docker images list \
  "$LOCATION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY" \
  --include-tags
~~~

Never share raw Docker configs or access tokens when filing support tickets: credential helper files can contain endpoints or sensitive authentication data. Provide only the masked hostname and necessary identity details.

## 17. Case Study: Releasing checkout-api and an Internal Java Library

**Hypothetical scenario:** an e-commerce company operates the following components:

- **checkout-api** written in Java, deployed on Cloud Run.
- **payments-worker** deployed on GKE.
- Shared Java library **payment-sdk** used across multiple Git repositories.
- Frontend **storefront-ui** consuming internal npm packages.
- Public base images/dependencies requiring source governance.

### 17.1. Repository Design

| Repository | Format/mode | Source and consumers |
|---|---|---|
| **checkout-images** | Docker standard | Cloud Build pushes; Cloud Run/GKE pull |
| **java-shared-libs** | Maven standard | Java release pipeline publishes |
| **maven-central-remote** | Maven remote | Proxies/caches Maven Central |
| **maven-unified** | Maven virtual | Maven/Gradle resolve internal before public |
| **npm-internal** | npm standard | Frontend publishes internal packages |
| **dockerhub-remote** | Docker remote | Controlled pull of base images |
| **generic-bundles** | Generic standard | Versioned release manifests/CLI bundles |

Repositories use locations aligned with corporate policy. Production runtimes may live in separate projects, so IAM grants **Reader to the image-pulling principal**, **Writer to CI**, and separate administrative rights to the security/platform team.

### 17.2. Build and Release Pipeline

~~~mermaid
flowchart TD
    COMMIT["Git commit + PR review"] --> TEST["Java tests / SAST / deps"]
    TEST --> BUILD["Build image + JAR"]
    BUILD --> PUSH["Push standard repositories"]
    PUSH --> DIG["Record immutable digest/version"]
    DIG --> SCAN["Vulnerability checks / SBOM / provenance"]
    SCAN --> APPROVE{"Release gate PASS?"}
    APPROVE -- "No" --> FIX["Fix and create new version"]
    APPROVE -- "Yes" --> STAGE["Deploy staging by digest"]
    STAGE --> VERIFY["Integration tests and SLO"]
    VERIFY --> PROD["Promote same digest to production"]
    PROD --> OBS["Monitor / audit / inventory deployed digests"]
    OBS --> CLEAN["Cleanup dry run and retention review"]
~~~

A release workflow can use Cloud Build to build and push, Artifact Analysis to scan, and Cloud Deploy/GitOps/Cloud Run revisions to orchestrate rollouts; the final deployment mechanism depends on the target runtime platform.

### 17.3. Incident 1: Image Pull Failure After Splitting Projects

After separating the production project, the Cloud Run deployment pipeline fails with **403** when pulling images from **commerce-build**. The application team granted Reader to the runtime service account, yet it still failed.

**Investigation direction:** identify the **principal actually pulling the image** during Cloud Run deployment—which may be the runtime project's service agent rather than the runtime SA. Inspect source repository IAM, project/region/path/digest, and organization policies. Do not make the repository public as a temporary workaround.

### 17.4. Incident 2: Internal Package Pulled Accidentally from Public Registry

A Python build installed a higher version of **internal-risk-utils** from PyPI because pip was configured with multiple indexes, including both the private index and public PyPI. Even though the private package existed, pip picked the public copy by version.

**Resolution direction:** use a virtual repository with proper private upstream priority, configure only one approved index endpoint, pin dependencies, verify hashes/provenance, and review internal package naming.

### 17.5. Incident 3: Cleanup Deleted an Actively Running Release

A policy keeping only the 5 most recent image versions deleted the digest of a running version for a rarely released GKE service. Running Pods did not immediately crash, but when rescheduling or rollback was needed, the image could no longer be pulled.

**Resolution direction:** maintain a deployed digests inventory, production/rollback retention policies, dry run before applying, and DR replication when required. If the image is gone, rebuild from source and reconcile provenance; do not claim an old digest can be bit-for-bit reconstructed if the build environment has changed.

### 17.6. Post-Deployment Verification

- Cloud Run/GKE deployments reference an approved **digest**.
- Image pulls succeed using the proper principal in both staging and production.
- Java packages have the right Maven coordinates/versions and consumers resolve them.
- The virtual dependency endpoint prioritizes internal sources per policy.
- Vulnerability findings are within approved tolerance thresholds.
- SBOM/provenance/CI logs provide build traceability.
- Cleanup rules do not delete active or rollback digests.
- Storage, scanning, transfer, and repo IAM costs are reviewed periodically.

## 18. Exercises and Self-Check Questions

### 18.1. Choose the Format and Repository Mode

| Need | Guiding answer |
|---|---|
| Push a Java container image for Cloud Run | **Docker standard** |
| Publish a Java library for Maven resolution | **Maven standard** |
| Single endpoint for internal Maven + Maven Central | **Maven virtual**, with standard and remote upstreams |
| Proxy/cache images from Docker Hub | **Docker remote** |
| Store release ZIP files with package/version | **Generic standard** |
| Distribute Debian OS packages | **Apt** format |
| Store Helm charts packaged as OCI | **Docker** format |
| Store Ruby gems or Conda packages | Matching format, noting **Preview** status |
| Proxy an upstream when policy forbids caching | **Connector (Preview)** where supported |
| Distribute Python wheels for pip | **Python** format |

### 18.2. Reasoning Questions

1. Does Artifact Registry automatically build an image when Git code changes?
2. Can a Docker-format repository be converted to Maven by changing its description?
3. How does a **remote repository** differ from a **virtual repository**?
4. With virtual upstream priorities **100** and **50**, which upstream takes precedence when the same version exists in both?
5. Why does configuring pip's **extra-index-url** fail to guarantee private package priority?
6. Is the **stable** tag inherently an immutable build?
7. Why should images be deployed by digest for exact rollbacks?
8. Does a CI account that needs to push require **roles/artifactregistry.admin**?
9. If a cross-project Cloud Run image pull fails with 403, which principal should be checked?
10. Is a cleanup policy keeping only the 5 newest versions sufficient for all production rollbacks?
11. Can a Generic artifact version be overwritten by uploading a new file with the same version?
12. If vulnerability scanning is enabled, does that guarantee no logic bugs, embedded secrets, or IAM flaws remain?
13. Once the Docker credential helper is configured, can a user without Reader IAM pull images?
14. If a repository's location differs from where GKE runs, what impacts must be evaluated?
15. Why might deleting a tag not immediately reduce storage charges?

**Short answers:** (1) No; CI handles building. (2) No. (3) Remote proxies/caches one upstream; virtual aggregates multiple upstreams into one endpoint. (4) 100. (5) pip may pick the newest version across any configured index. (6) No, if mutable. (7) A digest uniquely identifies the manifest content. (8) No; Writer is usually sufficient. (9) The service agent/identity actually performing the pull. (10) No. (11) No. (12) No. (13) No. (14) Network/egress/latency/data residency/DR. (15) Shared layers, remaining versions, cleanup job schedule, and billing lag.

### 18.3. Hands-on Exercise: Inspecting an Existing Repository

Use only a repository you are authorized to access:

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
LOCATION="asia-southeast1"
REPOSITORY="YOUR_REPOSITORY"

# Read-only.
gcloud artifacts repositories describe "$REPOSITORY" \
  --project="$PROJECT_ID" --location="$LOCATION" \
  --format=yaml

gcloud artifacts packages list \
  --project="$PROJECT_ID" --location="$LOCATION" \
  --repository="$REPOSITORY"

gcloud artifacts repositories get-iam-policy "$REPOSITORY" \
  --project="$PROJECT_ID" --location="$LOCATION"
~~~

Write a report:

~~~text
PROJECT / LOCATION:
REPOSITORY / FORMAT / MODE:
UPSTREAMS AND PRIORITIES (IF ANY):
IAM READER / WRITER / ADMIN:
NUMBER OF PACKAGES / VERSIONS:
DEPLOYED IMAGE DIGEST (IF DOCKER):
IMMUTABLE TAGS ENABLED?:
CLEANUP / RETENTION DRY RUN?:
VULNERABILITY SCANNING STATUS:
CMEK / ENCRYPTION POLICY:
DATA RESIDENCY / CROSS-REGION CONSUMERS:
ESTIMATED COST / OWNER:
RISK / RECOMMENDED ACTION:
~~~

If permissions are insufficient or a format/mode does not support a command, record **NOT OBSERVED/UNKNOWN**; never mark "PASS" without verification.

## 19. Common Misconceptions

| Misconception | Accurate understanding |
|---|---|
| "Artifact Registry is just Google's Docker Hub." | Supports multiple package formats and repository modes, not just Docker. |
| "One repo can hold any format." | A repository selects a specific format and cannot mix Maven/npm/Docker arbitrarily. |
| "Virtual is where you push artifacts." | Virtual is an aggregated access point; publish to standard repositories. |
| "Remote stores internal original artifacts." | Remote proxies/caches an upstream; standard is used to upload internal artifacts. |
| "Connector and remote both cache the same way." | Connector (Preview) proxies **without caching**. |
| "Artifact Registry builds and deploys code automatically." | CI/CD and runtimes perform builds and deployments. |
| "An image tag is a content hash." | Tags can be mutable; digests are content-addressable identifiers. |
| "If immutable tags are enabled, artifacts live forever." | It only restricts tag mutation; lifecycle, retention, and admin actions still apply. |
| "Granting Reader to the runtime SA always enables cross-project pulls." | Check the actual principal pulling the image, which may be a service agent/node SA. |
| "A virtual repo with higher priority always picks an older internal version." | Client version resolution still matters; pin versions/hashes. |
| "pip extra-index-url prioritizes private indexes in declaration order." | No; it exposes a dependency confusion risk. |
| "An Artifact Analysis scan is enough to approve production deploys." | Tests, provenance, policy, IAM, and risk review are still required. |
| "Generic is for overwriting files at the same version." | Generic versions are immutable; publish a new version. |
| "Cleanup dry run deletes artifacts." | Dry run is for previewing impact before enabling actual deletion. |
| "Keeping just tag 1.0.0 is enough for backup/rollback." | Preserve digests, artifacts, pipelines/provenance, and DR plans. |
| "Deleting a tag immediately cuts storage cost by the image size." | Layers may still be referenced; cleanup and billing have lag. |
| "A repository in asia-southeast1 guarantees free pulls from that region." | Check network transfer, destination, and current pricing. |
| "Putting tokens in a Dockerfile is safe if the image is private." | Secrets persist in build layers; use secret management instead. |

## 20. Google Cloud Reference Documentation

Official documentation to verify when updating this lesson or deploying to production:

- [Artifact Registry overview](https://docs.cloud.google.com/artifact-registry/docs/overview)
- [Repository overview](https://docs.cloud.google.com/artifact-registry/docs/repositories)
- [Supported formats](https://docs.cloud.google.com/artifact-registry/docs/supported-formats)
- [Create standard repositories](https://docs.cloud.google.com/artifact-registry/docs/repositories/create-repos)
- [Remote repositories overview](https://docs.cloud.google.com/artifact-registry/docs/repositories/remote-overview)
- [Create remote repositories](https://docs.cloud.google.com/artifact-registry/docs/repositories/remote-repo)
- [Virtual repositories overview](https://docs.cloud.google.com/artifact-registry/docs/repositories/virtual-overview)
- [Create virtual repositories](https://docs.cloud.google.com/artifact-registry/docs/repositories/virtual-repo)
- [Connector repositories overview (Preview)](https://docs.cloud.google.com/artifact-registry/docs/repositories/connector-overview)
- [Access control with IAM](https://docs.cloud.google.com/artifact-registry/docs/access-control)
- [Docker image push and pull](https://docs.cloud.google.com/artifact-registry/docs/docker/pushing-and-pulling)
- [Maven and Gradle authentication](https://docs.cloud.google.com/artifact-registry/docs/java/authentication)
- [Python package authentication](https://docs.cloud.google.com/artifact-registry/docs/python/authentication)
- [npm authentication](https://docs.cloud.google.com/artifact-registry/docs/nodejs/authentication)
- [Generic artifacts](https://docs.cloud.google.com/artifact-registry/docs/generic)
- [Configure cleanup policies](https://docs.cloud.google.com/artifact-registry/docs/repositories/cleanup-policy)
- [Artifact Registry pricing](https://cloud.google.com/artifact-registry/pricing)

Preview formats, repository modes, upstream configurations, vulnerability scanning, IAM, and pricing may change over time. When applying in practice, verify against the **format, mode, location, Google Cloud project, CLI version, and assigned permissions**.

---

**Connection to the CLOUD_PROVIDERS_GCP track:** Artifact Registry bridges **source code/CI-CD** and workload runtimes such as **Compute Engine, GKE, and Cloud Run**. Repository format and mode govern how **Docker images, Java JARs, and dependencies** are managed, while **projects/IAM, VPC/networking, Cloud KMS, Cloud Logging/Monitoring, and Cloud Billing** govern operational security and cost. A reliable workflow is **verify sources → build/test → publish to a standard repository → record version/digest, run security scans → deploy with least-privilege identity → retain rollback candidates → clean up artifacts per tested policies**.
