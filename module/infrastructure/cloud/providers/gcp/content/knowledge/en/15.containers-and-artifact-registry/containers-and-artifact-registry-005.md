# Remote Repositories and Virtual Repositories

## Learning Objectives

After this lesson, learners will be able to:

1. Distinguish the three primary modes of **Google Cloud Artifact Registry**: **standard**, **remote**, and **virtual repositories**; and recognize **connector** mode where applicable.
2. Explain **remote proxy/cache** mechanics for container images and packages, including upstream authentication, cache freshness, repository location, and network restrictions.
3. Design a **virtual repository** aggregating multiple standard/remote upstreams by **priority**, distinguishing resolving a specific package-version from selecting the newest version.
4. Mitigate **dependency confusion** risks by giving private repositories higher priority and configuring clients to use only the virtual endpoint.
5. Work hands-on with **gcloud Artifact Registry**, **Docker**, and **Maven/Gradle** to create standard/remote/virtual repositories, test downloads, and manage access.
6. Operate safely across **Cloud Build, GKE, Cloud Run**, and Java pipelines: IAM/service agents, Secret Manager, caching, vulnerability scanning, cleanup policies, VPC Service Controls, monitoring, and cost.

## 1. The Problem: One Pipeline Needs Both Internal and Public Dependencies

A company develops **Java/Spring Boot** applications on GCP:

- Uses **com.company:order-core** libraries published internally by the company.
- Uses public libraries **org.slf4j:slf4j-api**, **com.fasterxml.jackson.core:jackson-databind**, and related dependencies from Maven Central.
- Builds containers with base images from **Docker Hub**, then pushes self-built images to Artifact Registry.
- Deploys images to **Google Kubernetes Engine (GKE)**, **Cloud Run**, or VMs on **Compute Engine**.

If Maven/Gradle, Docker, pip, and npm hit multiple sources directly, the organization runs into problems:

- Every developer machine and CI runner has different repository lists, credentials, and proxies.
- Public upstreams can be slow, flaky, rate-limited, or temporarily unavailable.
- A package with the same name as an internal package can appear on a public registry and get selected mistakenly by clients (**dependency confusion**).
- It is hard to audit dependency origins or apply centralized access control, scanning, and retention rules.
- Repeated downloads from the Internet increase latency, network dependency, and potentially cost.

**Artifact Registry** solves format-specific artifact management for Docker/OCI images, Maven packages, npm, Python, and other supported formats. Three repository modes have complementary responsibilities:

- **Standard:** where organizational artifacts are **published/uploaded**.
- **Remote:** where artifacts from an upstream source are **proxied and cached**.
- **Virtual:** **a single read endpoint** combining multiple repositories of the same format under governed priorities.

Within the **CLOUD_PROVIDERS_GCP** module, this lesson connects project, IAM, VPC, Compute Engine, GKE, Cloud Run, storage, and CI/CD concepts to design a controlled artifact path from **dependency resolution → build → image → deploy → cost and reliability monitoring**.

## 2. Choosing the Right Repository Mode

### 2.1. High-Level Comparison

| Mode | Where do artifacts come from? | Stores artifacts in repo? | Direct upload/push allowed? | Purpose |
|---|---|---|---|---|
| **Standard** | Published by CI/CD or developers | **Yes** | **Yes**, if authorized | Internal artifacts, release versions |
| **Remote** | One public/private/standard upstream as supported | **Yes**, cached on demand | **No** (read-only) | Proxy/cache external dependencies |
| **Virtual** | One or more standard/remote upstreams | **No** | **No** (read-only) | Single endpoint applying priority across repositories |
| **Connector** (Preview, dedicated support scope) | Upstream configured for the connector | **Does not cache** | **No**, proxy model | Forward to upstream when caching is unwanted |

A repository has **one format**, such as Maven or Docker. A virtual Maven repository **cannot simultaneously** aggregate Docker images; a separate virtual Docker repository is required.

### 2.2. Typical Java Structure

~~~mermaid
flowchart LR
    DEV["Maven / Gradle<br/>Java developers and Cloud Build"] --> V["maven-all<br/>VIRTUAL"]
    V -->|"priority 100"| P["java-private<br/>STANDARD"]
    V -->|"priority 20"| R["maven-central-cache<br/>REMOTE"]
    R -->|"cache miss: HTTPS"| C["Maven Central<br/>PUBLIC UPSTREAM"]
    P --> J["Internal JAR/POM"]
~~~

**java-private** holds libraries published by the company. **maven-central-cache** fetches dependencies from Maven Central and caches them. **maven-all** is the single URL build tools read from; it does not store a separate copy of data.

### 2.3. Typical Container Structure

~~~mermaid
flowchart LR
    DO["Docker / GKE / Cloud Run pull"] --> V["docker-all<br/>VIRTUAL"]
    V -->|"priority 100"| S["images-private<br/>STANDARD"]
    V -->|"priority 10"| R["dockerhub-cache<br/>REMOTE"]
    R -->|"cache miss / metadata refresh"| HUB["Docker Hub"]
    CI["Cloud Build pushes built image"] --> S
~~~

Pipelines **push** to **images-private**, never to **docker-all**. Clients **pull** via `docker-all` when a unified URL is desired. For production deployments, you may target private images directly by digest or use the virtual endpoint per organizational policy; both still require IAM and provenance controls.

## 3. How Does a Remote Repository Work?

### 3.1. First Download: Cache Miss

~~~mermaid
sequenceDiagram
    participant CLI as Maven / Docker
    participant AR as Artifact Registry Remote
    participant UP as Public/private upstream
    CLI->>AR: GET package version / image digest
    AR->>AR: Check cache
    alt Artifact not cached
        AR->>UP: Fetch artifact from upstream
        UP-->>AR: Artifact + metadata
        AR->>AR: Cache downloaded copy
        AR-->>CLI: Return artifact
    else Matching copy already cached
        AR-->>CLI: Return cached copy
    end
~~~

A remote repository acts as a **read-only caching proxy**. It **does not mirror the entire upstream upon creation**; only requested versions are fetched into the cache.

### 3.2. Cache Hit, Upstream Outages, and Never-Downloaded Artifacts

Once an artifact/version is cached, requests can continue serving the cached copy even if the upstream is temporarily unreachable. However:

- **Uncached** artifacts/versions can still fail to download during an upstream outage.
- **Metadata, package indexes, and mutable tags** have refresh mechanisms; the cache cannot be assumed permanently immutable or always up to date.
- If the upstream lacks a requested name/version, the remote repository will not synthesize it.
- If the repo is deleted, cache cleanup removes it, or requests fail IAM checks, there is no guarantee the artifact remains downloadable.

**A remote cache improves availability; it is not a complete offline mirror or backup strategy.**

### 3.3. Metadata Refresh Thresholds to Know

Per current remote repository documentation, different index/metadata types have different **default update ages**:

| Format | Metadata component | Default age |
|---|---|---|
| **Maven** | `maven-metadata.xml` | **5 minutes** |
| **Maven** | `archetype-catalog.xml` | **1 hour** |
| **npm** | Package manifest files | **5 minutes** |
| **Python** | Package index files | **1 hour** |
| **Docker** | List/Get tags cache | **1 hour** |
| **Apt/Yum** (Preview) | Index files | **2 minutes** |
| **Apt/Yum** (Preview) | Package files | **72 hours** |

These are **staleness limits for the listed metadata/file types**, not a guarantee that every artifact is revalidated to the minute or that a newly pushed Docker tag appears instantaneously. Metadata refresh behavior may differ from artifact content caching. For critical releases, **pin versions and digests** rather than relying on mutable tags like **latest**.

### 3.4. Location, Upstream, and Network Constraints

When creating a remote repository, you choose **format, location, upstream source, and encryption**. These settings cannot be changed arbitrarily after creation; changing upstream or location usually requires **creating a new repo and migrating clients**.

With custom upstream URLs, **HTTPS is mandatory**. Remote repositories **do not support upstreams with only private IPs inside on-premises networks or VPCs** that are unreachable from the Internet. If you want to mirror an internal Nexus repository, evaluate an accessible HTTPS upstream endpoint and authentication mechanism, or choose a different architecture.

If a remote repository sits inside a **VPC Service Controls perimeter**, accessing external upstreams outside the perimeter is **blocked by default**. Configure Artifact Registry-supported egress exceptions and undergo security review; do not assume VPC peering or Cloud NAT resolves this requirement.

### 3.5. Public and Private Upstream Authentication

Some upstreams such as Docker Hub enforce rate limits and support authentication. When using remote repositories:

1. Docker/Maven clients **authenticate to Artifact Registry** using a Google identity.
2. Artifact Registry **authenticates to the upstream** using dedicated credentials if required.
3. Upstream credentials should be stored in **Secret Manager** as a secret version.
4. The **Artifact Registry service agent** needs appropriately scoped read access to the secret; grant `secretAccessor` only on the required secret.

**Do not confuse the two credential layers:** the gcloud Docker credential helper authenticates the client to **REGION-docker.pkg.dev**; the upstream Docker Hub username/token are credentials **Artifact Registry uses to pull artifacts from Docker Hub**.

## 4. Virtual Repositories: Single Endpoint, Multiple Upstreams, and Priority

### 4.1. Virtual Repositories Do Not Store Artifacts

A virtual repository is a **logical aggregation** used to route **artifact read** requests to the right standard/remote upstreams.

- Clients use **one virtual URL** to download container images or packages.
- Virtual holds an **upstream policy list** containing repository resource names and priorities.
- Physical artifacts reside in **standard repositories** or **remote repository caches**.
- Listing images directly on a virtual repo or viewing it in the Console may show an **empty repo**, because virtual **does not keep its own artifact copies**.
- You cannot upload images/JARs to a virtual repo, nor expect running cache cleanup on the virtual repo itself to free storage.

### 4.2. Priority: **Higher Number Wins**, Unlike Many Other Systems

Suppose:

| Upstream | Mode | Priority | Has `com.company:order-core:1.4.0`? |
|---|---|---:|---|
| `java-private` | Standard | **100** | Yes |
| `maven-central-cache` | Remote | **20** | Possibly |
| `java-legacy` | Standard | **10** | Yes |

If a client requests **specifically `com.company:order-core:1.4.0`**, virtual prioritizes **java-private**. If that package/version does not exist in `java-private` but exists in `maven-central-cache`, the system can serve it from remote per policy.

**Rules to remember:**

- **100** takes precedence over **20**, not the reverse.
- **Equal priority:** if an artifact exists in multiple tied upstreams, Artifact Registry **may return it from any upstream in that tier**. Do not design provenance around JSON array ordering.
- **Priority only takes effect when resolving a matching artifact/version.** If a client asks only for a package name and lets the resolver pick **latest**, the result can still tilt toward the highest version regardless of priority.

### 4.3. Version Pinning Matters as Much as Priority

Suppose private has **order-core:1.2.0**, while a public source has a same-named package **order-core:99.0.0**. If a client asks for the "latest" version without pinning, a resolver may pick the higher public version.

Therefore, you should:

- **Pin versions** for Maven/Gradle, npm, Python, and Go using appropriate strategies.
- For production container images, prefer **image digests** over mutable tags.
- For Python, use lockfiles or fully pinned requirements combined with **hash verification** where supported.
- Configure only a single **virtual endpoint** so resolvers do not reach out directly to client-discovered public sources.
- Separate **private package names/scopes** and review dependency supply-chain changes.

### 4.4. Dependency Confusion Risk

**Dependency confusion** occurs when an attacker publishes a public package sharing the same name as a private package and tricks clients into pulling the wrong one.

Unsafe example:

~~~text
pip index-url       → Private repository
pip extra-index-url → Public PyPI

Client compares candidates from both,
picks the newest version, with no guarantee of preferring private.
~~~

Better architecture:

~~~text
pip index-url → Artifact Registry virtual Python
  priority 100: python-private (standard)
  priority 20:  pypi-cache (remote)

Do not configure a parallel public extra-index-url.
~~~

This is a **risk-mitigation measure**, not an absolute guarantee against malicious packages. Dependency reviews, version/hash pinning, scanning, provenance, and IAM are still necessary.

### 4.5. Location, Format, and Permission Rules

- **Upstreams must match the format** of the virtual repository.
- **Upstreams must match the location** (corresponding region or multi-region) of the virtual repository; projects can differ.
- Virtual uses the **Artifact Registry Service Agent** to access upstreams; the service agent must be granted required read permissions, especially when an upstream belongs to another project.
- A high-priority source that denies read access to the service agent **does not equate to a safe automatic fallback**. Upstream IAM errors must be treated as misconfigurations, not expected to silently skip a private source.
- Apt/Yum virtual repositories are in **Private Preview** and upstreams must be **standard Artifact Registry** repos per current restrictions.

## 5. Format and Upstream Type Support

| Format | Remote repository | Virtual repository | Example upstream or use case |
|---|---|---|---|
| **Docker / OCI** | Yes | Yes | Docker Hub, GHCR, standard Docker repo |
| **Maven** | Yes | Yes | Maven Central, internal standard Maven |
| **npm** | Yes | Yes | npmjs.org, internal private npm |
| **Python** | Yes | Yes | PyPI, private wheels |
| **Go** | Yes via supported public presets | Yes | `proxy.golang.org` and Go modules |
| **Apt** | **Preview** | **Private Preview** | Debian/Ubuntu presets; standard virtual upstreams |
| **Yum** | **Preview** | **Private Preview** | Rocky/EPEL/CentOS presets; standard virtual upstreams |
| **Ruby/Conda/Kubeflow templates/generic** | Not in the remote/virtual list above by default | Not in the list above by default | Typically used as standard per current features |

Formats supported by Artifact Registry **at the standard level** do not automatically support **remote and virtual modes**. Check **Supported formats** and **Remote/Virtual overview** at implementation time; Preview features have access conditions and evolve quickly.

### What Can a Remote Upstream Be?

| Format | Common preset | Custom upstream | Standard Artifact Registry upstream |
|---|---|---|---|
| Docker | **DOCKER-HUB** | HTTPS registries, GHCR, `public.ecr.aws`... | Supported |
| Maven | **MAVEN-CENTRAL** | HTTPS Maven repositories | Supported |
| npm | **NPMJS** | HTTPS registries or private upstreams | Supported |
| Python | **PYPI** | HTTPS Python package repositories | Supported |
| Go | `proxy.golang.org` | Per supported presets; do not assume custom Go | Check format limits |
| Apt/Yum | Base upstreams listed in Preview | Preset-specific rules, not arbitrary URLs like Maven | Per Preview conditions |

When a remote upstream is a **standard Artifact Registry** repo in another project, grant permissions to the **remote project's service agent**, not just the client's build service account. This is **service-to-service authorization between repositories**, separate from a user's read permission on the remote endpoint.

## 6. Deployment Architecture and Permission Model

### 6.1. Single-Project Lab Model

| Resource | Type | Format | Purpose |
|---|---|---|---|
| **java-private** | Standard | Maven | Organization-published Java packages |
| **maven-central-cache** | Remote | Maven | Maven Central proxy |
| **maven-all** | Virtual | Maven | Dependency downloads via one endpoint |
| **images-private** | Standard | Docker | Images released by Cloud Build |
| **dockerhub-cache** | Remote | Docker | Docker Hub base image proxy/cache |
| **docker-all** | Virtual | Docker | Pull images via one endpoint |

The illustrative project is **shop-dev-001**, location **asia-southeast1**. All names/IDs in this lesson are uncreated examples; run them only in an authorized practice environment with appropriate budget/quotas.

### 6.2. Multi-Project Model

~~~mermaid
flowchart TB
    APP["Project app-ci<br/>Cloud Build"] --> V["Project platform-registry<br/>maven-all virtual"]
    V --> I["Project java-team<br/>java-private standard"]
    V --> P["Project platform-registry<br/>maven-central-cache remote"]
    P --> C["Maven Central"]
    SA["Artifact Registry service agent<br/>of virtual project"] -->|"read upstream"| I
    SA -->|"read upstream"| P
~~~

If upstream repositories live in **different projects**, grant the virtual project's service agent permissions such as **roles/artifactregistry.reader** on the upstreams (or a narrower custom role with **artifactregistry.repositories.readViaVirtualRepository** per documentation). **Do not grant all virtual readers direct access to the project holding private packages** if the goal is only centralized endpoint downloads.

### 6.3. Different Principals, Different Permissions

| Principal | Where to grant | Recommended role | Avoid |
|---|---|---|---|
| Java developer / build runner | Maven virtual | **roles/artifactregistry.reader** | Writer on virtual, project-wide Admin |
| Docker runtime/GKE node/Cloud Run deploy identity | Docker virtual or image source | Matching Reader | Hardcoded container registry credential keys |
| Maven publisher | **java-private standard** | **roles/artifactregistry.writer** | Publishing to virtual or remote |
| Cloud Build image publisher | **images-private standard** | Writer | Admin just to push images |
| Virtual's Artifact Registry service agent | Upstream repos | Reader or appropriate `readViaVirtualRepository` | Project-wide Editor/Owner |
| Remote service agent | Private upstream registry/Secret Manager | Required upstream access and **secretAccessor** on exact secret | Storing upstream tokens in source |
| Platform registry admin | Repositories/projects needing management | Artifact Registry Admin | Using Admin unnecessarily in builds/runtimes |

For **GKE** or **Cloud Run**, identify the **actual identity performing image pulls** per product/deployment model rather than blindly granting Reader to the application's Java service account. Pulling images at deploy time is often handled by service agents or identities distinct from the identity running Java code.

## 7. Prerequisites Before Hands-on Practice

You need:

1. Project **shop-dev-001** with **billing** and the **Artifact Registry API** enabled.
2. A recent gcloud CLI logged in as a principal authorized to administer repositories for the lab.
3. A valid location for the product format; verify via **gcloud artifacts locations list**.
4. Repo admin rights (**roles/artifactregistry.admin**) in the practice project; in production use least-privilege IAM.
5. Maven/Gradle or Docker client for testing, with appropriate plugins/credential helpers.
6. If upstreams require authentication, **Secret Manager API, secret versions, and Service Agent IAM**.
7. Check whether the organization enforces **VPC Service Controls**, CMEK, scanning, or mandatory policies.

~~~bash
# Read-only checks or enabling API per assigned permissions.
gcloud config get-value project
gcloud artifacts locations list
gcloud artifacts repositories list \
  --project=shop-dev-001 \
  --location=asia-southeast1

# Mutating administrative operation; run only when permitted.
gcloud services enable artifactregistry.googleapis.com \
  --project=shop-dev-001
~~~

**Never run labs directly against production.** Creating repositories, caching artifacts, granting IAM, scanning, or downloading packages can incur charges and create resources requiring planned cleanup.

## 8. Hands-on A — Maven Standard + Remote + Virtual

**Goal:** Java builds read dependencies only through **maven-all**, where private Maven has higher priority than the Maven Central proxy.

### 8.1. Create the Standard Maven Repository

~~~bash
gcloud artifacts repositories create java-private \
  --project=shop-dev-001 \
  --repository-format=maven \
  --mode=standard-repository \
  --location=asia-southeast1 \
  --description="Private Java packages"
~~~

The **java-private** repo is the publish target for internal JARs/POMs. It will not contain **com.company:order-core** until a publisher deploys the package using Maven/Gradle.

### 8.2. Create the Remote Maven Central Repository

~~~bash
gcloud artifacts repositories create maven-central-cache \
  --project=shop-dev-001 \
  --repository-format=maven \
  --mode=remote-repository \
  --remote-mvn-repo=MAVEN-CENTRAL \
  --location=asia-southeast1 \
  --description="Cached dependencies from Maven Central"
~~~

This is a **read-only** remote repository. Build accounts authenticate to **Artifact Registry** when reading. Public Maven Central does not require a username/password, though authenticated upstreams require configuring a secret as shown later.

### 8.3. Verify Created Upstreams

~~~bash
gcloud artifacts repositories describe java-private \
  --project=shop-dev-001 --location=asia-southeast1

gcloud artifacts repositories describe maven-central-cache \
  --project=shop-dev-001 --location=asia-southeast1
~~~

Confirm **format=MAVEN**, **mode=STANDARD_REPOSITORY/REMOTE_REPOSITORY**, the right location, and **remoteRepositoryConfig** pointing to Maven Central.

### 8.4. Define the Upstream Policy JSON

In a CLI directory you control, create **maven-upstreams.json**:

~~~json
[
  {
    "id": "internal",
    "repository": "projects/shop-dev-001/locations/asia-southeast1/repositories/java-private",
    "priority": 100
  },
  {
    "id": "public-maven-central",
    "repository": "projects/shop-dev-001/locations/asia-southeast1/repositories/maven-central-cache",
    "priority": 20
  }
]
~~~

This is **JSON input for the gcloud command**, not Terraform or a Kubernetes manifest:

- **id** is a unique identifier for an upstream policy entry.
- **repository** must be the full resource path of a repo with the **same format/location**.
- **priority** is an integer; **100 > 20**, so private takes precedence if both repos hold the exact requested artifact/version.

Store policy files in source control **without secrets** to review priority changes or upstream additions/removals via IaC. Never put passwords/tokens directly into JSON.

### 8.5. Create the Virtual Maven Repository

~~~bash
gcloud artifacts repositories create maven-all \
  --project=shop-dev-001 \
  --repository-format=maven \
  --mode=virtual-repository \
  --location=asia-southeast1 \
  --description="Maven dependencies via private-first routing" \
  --upstream-policy-file=maven-upstreams.json

gcloud artifacts repositories describe maven-all \
  --project=shop-dev-001 \
  --location=asia-southeast1
~~~

Inspect **virtualRepositoryConfig.upstreamPolicies** to confirm both resource paths and priorities. The virtual repo stores no copies of packages; listing packages on virtual may appear empty.

### 8.6. Configure the Maven Client to Read Only via `maven-all`

Artifact Registry supports the **Maven wagon credential helper**. First inspect the official configuration generated by the CLI:

~~~bash
gcloud artifacts print-settings mvn \
  --project=shop-dev-001 \
  --location=asia-southeast1 \
  --repository=maven-all
~~~

Example snippet placed inside a Java project's **pom.xml**:

~~~xml
<repositories>
  <repository>
    <id>central</id>
    <name>Company Maven virtual repository</name>
    <url>artifactregistry://asia-southeast1-maven.pkg.dev/shop-dev-001/maven-all</url>
    <releases><enabled>true</enabled></releases>
    <snapshots><enabled>true</enabled></snapshots>
  </repository>
</repositories>
<build>
  <extensions>
    <extension>
      <groupId>com.google.cloud.artifactregistry</groupId>
      <artifactId>artifactregistry-maven-wagon</artifactId>
      <version>2.2.5</version>
    </extension>
  </extensions>
</build>
~~~

These are **sections belonging inside a complete `pom.xml`**, not a standalone XML file since there are multiple root elements. The plugin version shown is illustrative per current docs; in real projects, pull settings from **gcloud artifacts print-settings mvn** and pin versions per organizational process.

**Why `id=central`?** Maven's Super POM defines Maven Central by default. When overriding the Central repository with an internal endpoint, use the matching ID and inspect the **effective POM/settings**. Check **pluginRepositories**, Maven profiles, and CI init settings too so builds do not retain another direct path to Maven Central.

### 8.7. Test Maven Resolution

Suppose `pom.xml` has a pinned dependency:

~~~xml
<dependency>
  <groupId>org.slf4j</groupId>
  <artifactId>slf4j-api</artifactId>
  <version>2.0.16</version>
</dependency>
~~~

In an environment with Maven and valid ADC authentication:

~~~bash
mvn -U dependency:tree
~~~

Watch the Maven logs: artifacts should download from **asia-southeast1-maven.pkg.dev/.../maven-all**, not silently fall back directly to `repo.maven.apache.org`. Ensure the runner holds **roles/artifactregistry.reader** and valid ADC tokens.

### 8.8. Test Private-First Resolution

After a publisher releases a test version of **com.company:order-core:1.4.0** into **java-private**, verify:

1. Request **exact version 1.4.0** through Maven virtual.
2. Confirm it is served from the private upstream per policy.
3. Test a package absent from private but present on Maven Central: remote is used.
4. For a dependency missing from both sources, resolution must fail.
5. Check entitlement: a caller lacking Reader on virtual must be denied.

**Never upload test artifacts to public Maven Central** to simulate an attack; use a controlled lab repository if you want to safely test same-package/version collisions.

## 9. Hands-on B — Docker Hub Remote and Docker Virtual

**Goal:** a pipeline uses base images from Docker Hub and self-published images in **images-private**, while runtimes can pull through one endpoint **docker-all**.

### 9.1. Create the Standard Docker Repository

~~~bash
gcloud artifacts repositories create images-private \
  --project=shop-dev-001 \
  --repository-format=docker \
  --mode=standard-repository \
  --location=asia-southeast1 \
  --description="Private container images"
~~~

This is the repository publishers **push** to. For a Java API image:

~~~text
asia-southeast1-docker.pkg.dev/shop-dev-001/images-private/orders-api:1.0.0
~~~

A tag is a readable reference name; the actual image content also has a **sha256 digest**. For production releases, record the digest to guarantee exact deployment reproducibility.

### 9.2. Create the Remote Docker Hub Repository

~~~bash
gcloud artifacts repositories create dockerhub-cache \
  --project=shop-dev-001 \
  --repository-format=docker \
  --mode=remote-repository \
  --remote-docker-repo=DOCKER-HUB \
  --location=asia-southeast1 \
  --description="Docker Hub proxy and cache"
~~~

The command above illustrates a public upstream. If Docker Hub authentication is needed to avoid anonymous pull rate limits or reach private repositories, use **--remote-username** and **--remote-password-secret-version** with a Secret Manager secret; **never pass plaintext passwords on the command line or in source**.

### 9.3. Create the Priority-Ordered Docker Virtual Repository

File **docker-upstreams.json**:

~~~json
[
  {
    "id": "company-images",
    "repository": "projects/shop-dev-001/locations/asia-southeast1/repositories/images-private",
    "priority": 100
  },
  {
    "id": "docker-hub",
    "repository": "projects/shop-dev-001/locations/asia-southeast1/repositories/dockerhub-cache",
    "priority": 10
  }
]
~~~

~~~bash
gcloud artifacts repositories create docker-all \
  --project=shop-dev-001 \
  --repository-format=docker \
  --mode=virtual-repository \
  --location=asia-southeast1 \
  --description="Private-first Docker image pulls" \
  --upstream-policy-file=docker-upstreams.json

gcloud artifacts repositories describe docker-all \
  --project=shop-dev-001 \
  --location=asia-southeast1
~~~

### 9.4. Log Docker In to Artifact Registry

~~~bash
gcloud auth list
gcloud auth configure-docker asia-southeast1-docker.pkg.dev
~~~

The **configure-docker** command writes credential helper settings for the active Docker client. On Linux when running Docker via **sudo**, the user and root may read different Docker config files; ensure the Docker runner and credential helper share the right identity.

**Do not confuse:** this step only authenticates **Docker client → Artifact Registry**. Docker Hub upstream authentication, if needed, is managed separately by the remote repo.

### 9.5. Pull Base Images Through Remote and Virtual

~~~bash
# Pull directly via remote to warm the cache
docker pull \
  asia-southeast1-docker.pkg.dev/shop-dev-001/dockerhub-cache/busybox:1.36

# Pull via virtual: selects upstream per policy
docker pull \
  asia-southeast1-docker.pkg.dev/shop-dev-001/docker-all/busybox:1.36
~~~

Because **images-private** does not contain **busybox:1.36**, virtual resolves it from **dockerhub-cache**, which fetches from Docker Hub on cache miss. Once cached, remote can serve it without re-downloading blobs on every request.

**Replace image tags with versions/digests approved by your organization.** If an upstream tag changes, metadata and content caching can yield different results over time; never use **latest** as an immutable release key.

### 9.6. Push an Internal Image to Standard

Assuming you built **orders-api:1.0.0** from trusted source:

~~~bash
docker tag orders-api:1.0.0 \
  asia-southeast1-docker.pkg.dev/shop-dev-001/images-private/orders-api:1.0.0

docker push \
  asia-southeast1-docker.pkg.dev/shop-dev-001/images-private/orders-api:1.0.0
~~~

This requires **roles/artifactregistry.writer** or equivalent permissions on **images-private**. You cannot change the push target to **docker-all** or **dockerhub-cache**, because both are **read-only**.

Then test:

~~~bash
docker pull \
  asia-southeast1-docker.pkg.dev/shop-dev-001/docker-all/orders-api:1.0.0
~~~

Virtual resolves the image from the private standard repository according to priority. For production, it is best to record the **digest of the built and verified image** before deploying; re-pulling a tag does not guarantee nothing changed during build/release.

### 9.7. Inspect Packages in Remote and Virtual

~~~bash
gcloud artifacts packages list \
  --project=shop-dev-001 \
  --location=asia-southeast1 \
  --repository=dockerhub-cache

gcloud artifacts docker images list \
  asia-southeast1-docker.pkg.dev/shop-dev-001/images-private
~~~

**Do not look at virtual listing results and assume the repository is empty:** virtual has no storage of its own, so `gcloud artifacts docker images list` or the Console UI may not show upstream images. Inspect the standard and remote repositories, then run an **actual pull via the virtual endpoint** to confirm routing.

### 9.8. Container Deployments Using the Right Identity

When GKE or Cloud Run uses images in Artifact Registry, verify:

- The product's **image-pulling identity** has read access on the repository.
- The image URL and **location** match; **docker-all** is only a virtual endpoint, not a backend service.
- The Cloud Run service account running the app holds runtime data permissions (e.g., Cloud Storage/Cloud SQL), which are **separate** from deployment/image-pull permissions.
- If a private image is deleted or repo permissions change, **scale-outs, rollouts, and restarts** can fail even while existing containers remain running.
- Allow production to pull only controlled images using **digests**, attestations/provenance, or Binary Authorization if adopted by the organization.

## 10. Hands-on C — Configuring Python, npm, and Go with the Same Principles

The main labs used Maven and Docker, yet virtual repositories are especially valuable for **Python pip** because of how pip resolves multiple indexes.

### 10.1. Python: A Single `index-url`

Suppose an organization has:

- **python-private** (standard).
- **pypi-cache** (remote, upstream PyPI).
- **python-all** (virtual, private priority 100, remote priority 20).

Illustrative **pip.conf** file:

~~~ini
[global]
index-url = https://asia-southeast1-python.pkg.dev/shop-dev-001/python-all/simple/
~~~

Crucially, **do not add `extra-index-url=https://pypi.org/simple`** if your goal is to enforce upstream ordering at Artifact Registry. With multiple indexes, **pip does not guarantee private-first preference** and may pick a higher version from the public index.

For workstations, Google Cloud recommends **keyrings.google-artifactregistry-auth** for refreshing credentials; for automation, use **short-lived access tokens** or compatible authentication. Avoid embedding access tokens into a `pip.conf` committed to source control.

~~~bash
# Test after configuring Python credential helper and IAM.
python -m pip index versions requests
python -m pip install "requests==2.32.3"
~~~

These commands only test with a common public package; the version shown is an **example**, not a recommendation for the newest or safest version. In production, rely on lockfiles, vulnerability reviews, and tested versions.

### 10.2. npm: A Single Registry Endpoint and Lockfiles

Example **.npmrc** configuration for virtual npm:

~~~ini
registry=https://asia-southeast1-npm.pkg.dev/shop-dev-001/npm-all/
always-auth=true
~~~

Configure npm authentication following **gcloud artifacts print-settings npm**, and never commit npm auth tokens to repositories. For internal packages, prefer **scoped package names** like **@company/order-client** and lockfiles.

If `.npmrc` also maps another scope directly to `npmjs.org`, some packages will still bypass the virtual endpoint. Inspect **npm config get registry**, per-scope mappings, and run **npm ci** in a clean CI environment.

### 10.3. Go: `GOPROXY` and Module Versions

For Go modules, a virtual Go repository can serve downloads across supported upstreams. Clients must configure **GOPROXY** for Artifact Registry, authentication, and checksum/version verification.

Do not treat `GOPROXY=proxy.golang.org,direct` as a strict virtual-only policy; the **direct** fallback can allow reaching uncontrolled external sources when the proxy fails. For private modules, properly configure **GOPRIVATE**, checksum policies, and module server permissions.

### 10.4. Do Not Mix Package Formats

Maven, npm, pip, Go, and Docker have distinct URLs, authentication mechanisms, and caching semantics. Never use **docker-all** as a Maven repository or vice versa, even within the same project and location. For polyglot Java/Node/Python applications, create a **separate virtual repository for each format** needed.

## 11. Updating Upstream Policies When Adding or Changing Sources

A virtual repository can **add/remove upstreams or adjust priorities** after creation.

Suppose the organization adds a standard Maven repo **java-security-reviewed** holding vetted packages:

~~~json
[
  {
    "id": "security-reviewed",
    "repository": "projects/shop-dev-001/locations/asia-southeast1/repositories/java-security-reviewed",
    "priority": 200
  },
  {
    "id": "internal",
    "repository": "projects/shop-dev-001/locations/asia-southeast1/repositories/java-private",
    "priority": 100
  },
  {
    "id": "public-maven-central",
    "repository": "projects/shop-dev-001/locations/asia-southeast1/repositories/maven-central-cache",
    "priority": 20
  }
]
~~~

After actually creating **java-security-reviewed**, granting service agent access, and reviewing impact, save the file as **maven-upstreams.json**, then run:

~~~bash
gcloud artifacts repositories update maven-all \
  --project=shop-dev-001 \
  --location=asia-southeast1 \
  --upstream-policy-file=maven-upstreams.json

gcloud artifacts repositories describe maven-all \
  --project=shop-dev-001 \
  --location=asia-southeast1
~~~

**The `update` command affects every client using the virtual repository.** If the same package/version exists in multiple upstreams, changing priorities can alter which source new builds download from. You should:

1. Diff the old and new policy files.
2. Check which artifact/version names might be shadowed.
3. Run staging builds/tests with **clean dependency caches** when needed.
4. Verify checksums/digests of downloaded artifacts.
5. Roll out in a controlled way and keep the previous policy file ready for rollback.

To remove all upstreams, the policy file can contain **[]**, though clients querying the virtual endpoint will no longer find any artifacts. Never use this as a cleanup routine.

## 12. IAM, Service Agents, and Secret Manager

### 12.1. Two Separate Read Paths

A virtual read request traverses two permission layers:

~~~text
Client (Maven/Docker)
  ├─ IAM read permission on the virtual repository
  ↓
Artifact Registry virtual service
  ├─ Artifact Registry Service Agent has read permission on upstreams
  ↓
Upstream standard/remote repository
  ↓
Artifact
~~~

The client needs Reader on **virtual**, while the **service agent** needs access to the upstreams. If you only grant Reader to the client on virtual, but the service agent cannot read a cross-project upstream, requests can fail even though the client did nothing wrong.

### 12.2. What Does the Service Agent Look Like?

Artifact Registry's service agent format:

~~~text
service-PROJECT_NUMBER@gcp-sa-artifactregistry.iam.gserviceaccount.com
~~~

**PROJECT_NUMBER** is the numeric project number, not the project ID. With a virtual repo in **platform-registry-001** and an upstream in **java-team-001**, grant accordingly:

~~~bash
# Example retrieving the numeric project number hosting virtual.
gcloud projects describe platform-registry-001 \
  --format="value(projectNumber)"

# After replacing VIRTUAL_PROJECT_NUMBER with the actual value:
gcloud artifacts repositories add-iam-policy-binding java-private \
  --project=java-team-001 \
  --location=asia-southeast1 \
  --member="serviceAccount:service-VIRTUAL_PROJECT_NUMBER@gcp-sa-artifactregistry.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.reader"
~~~

This example grants Reader on **one upstream repository**. If there are many upstreams, you could grant Reader on the upstream project, though that has a wider blast radius; consider a custom role with **artifactregistry.repositories.readViaVirtualRepository** per documentation to minimize privileges.

### 12.3. Remote with a Cross-Project Standard Artifact Registry Upstream

When a **remote repo** uses a standard Artifact Registry repo in another project as its upstream, the remote documentation describes granting permissions to the **remote project's Artifact Registry service agent** on the upstream. In examples, the role may be **roles/artifactregistry.serviceAgent** per remote upstream instructions, which **differs** from the role/permission recommended for virtual upstreams.

**Do not copy-paste virtual IAM bindings verbatim to remote or vice versa** simply because both say "upstream." Check documentation for the exact repository mode, principal, and permission; prefer the narrowest permission that actually works.

### 12.4. Secret Manager for Private Docker Hub Upstreams

Suppose an enterprise has a Docker Hub username **DOCKERHUB_USER** and an access token stored in Secret Manager:

~~~text
projects/shop-dev-001/secrets/dockerhub-token/versions/1
~~~

Command to create an authenticated remote repository:

~~~bash
gcloud artifacts repositories create dockerhub-auth-cache \
  --project=shop-dev-001 \
  --repository-format=docker \
  --mode=remote-repository \
  --remote-docker-repo=DOCKER-HUB \
  --remote-username=DOCKERHUB_USER \
  --remote-password-secret-version=projects/shop-dev-001/secrets/dockerhub-token/versions/1 \
  --location=asia-southeast1
~~~

**Never enter tokens directly on the command line**; the token must already exist as a **secret version**, and the Artifact Registry service agent must hold Secret Manager Secret Accessor on the right secret.

Operational notes:

- Secrets in docs/code must never contain real passwords.
- When rotating the Docker Hub token, you may need to update the remote repo config with the **new secret version** per supported features.
- Do not share one broad personal Docker Hub token across an entire enterprise if better account/permission options exist.
- If Secret Manager IAM is missing, repo creation may succeed while upstream fetches fail depending on validation/config; check the service agent and Cloud Audit Logs.
- **Docker clients do not need to know the Docker Hub token** when using an Artifact Registry remote repo—only a Google Cloud identity authorized to read the remote repo.

## 13. Security and the Software Supply Chain

### 13.1. Remote Caching Does Not Automatically Make Artifacts Safe

A malicious package on a public registry can still be downloaded and cached by a remote repository. Caching reduces network dependency; **it does not automatically verify signatures, licenses, or software behavior**.

Apply defense in depth:

| Layer | Appropriate control |
|---|---|
| **Source selection** | Private-first virtual, allowing only approved upstreams |
| **Version identity** | Pin package versions, checksums/hashes, Docker image digests |
| **Provenance** | Build attestations, signed artifacts/SBOMs per supported tools and scope |
| **Vulnerability awareness** | Artifact Analysis, vulnerability scanning per format and repository policy |
| **Deployment policy** | Binary Authorization for GKE/Cloud Run if supported by deployment model |
| **Identity** | Least-privilege Reader/Writer IAM, Workload Identity Federation for external CI |
| **Secrets** | Secret Manager, never hardcode registry tokens |
| **Governance** | Change reviews, cleanup retention, audit logs, dependency reviews |

### 13.2. Priority Does Not Stop Malicious Artifacts Already in Private

If **java-private** has priority 100, yet an internal publisher is compromised and pushes a bad JAR, virtual will still pick the artifact from the **highest-priority** source. Therefore:

- Protect **Writer** permissions on standard repositories.
- Separate **publisher identities** per pipeline/team.
- Enable provenance/signature checks and scanning as required.
- Use compatibility testing and release approvals.
- Restrict delete/overwrite permissions on published versions where formats allow.

### 13.3. Docker Tags and Digests

~~~text
Image by tag:
asia-southeast1-docker.pkg.dev/shop-dev-001/docker-all/orders-api:1.0.0

Image by digest (illustrative, not a real digest):
asia-southeast1-docker.pkg.dev/shop-dev-001/docker-all/orders-api@sha256:<64-HEX-CHARS>
~~~

**Tags** can be mutable per policy; **digests** represent a specific content-addressed artifact. For images from a remote Docker Hub repo, pinning digests reduces risk from upstream tag mutation. You still need to verify the digest comes from an approved source and passes scanning so you do not "pin a malicious artifact" permanently.

### 13.4. SBOMs, Vulnerability Scanning, and Artifact Analysis

Artifact Registry can integrate with **Artifact Analysis** to collect metadata and scan supported artifact types depending on capabilities and enablement. Remote cached artifacts can also be analyzed where scanning scope supports them.

**Do not assume all Maven/npm/Python packages and all remote artifacts are scanned on the same schedule or at the same depth.** Check supported formats, scan policies, permissions, pricing, and actual outputs. A result showing "no findings" **does not prove there are no vulnerabilities**.

### 13.5. Dependency Licenses and Data Governance

A remote cache stores third-party artifacts inside an enterprise project. Review:

- Licenses/compliance around redistributing or storing cached copies.
- Data residency/location of the repository.
- Retention, cleanup, and sensitive contents inside private packages.
- Secrets accidentally built into images/JARs or metadata.
- Team access scopes through virtual endpoints and IAM.

Choosing a region close to runtimes reduces latency and data transfer, provided it complies with data policies and product availability.

## 14. VPC Service Controls, Networking, and Availability

### 14.1. How Does an Artifact Registry Remote Reach Upstreams?

A remote repo is a Google Cloud managed service, not a VM inside your VPC. Therefore:

- Creating **Cloud NAT** for build VMs does not automatically let the remote service reach a private upstream.
- A remote upstream **must have an endpoint supported and reachable by Artifact Registry**; private VPC-only endpoints are not supported per remote limitations.
- If the remote repo is inside a **VPC SC perimeter**, configure **egress rules allowing external upstreams** per Artifact Registry/VPC SC documentation.

### 14.2. Cached Artifacts Do Not Guarantee Unconditional Offline Availability

Suppose Maven Central has an outage:

| Scenario | Expected behavior |
|---|---|
| Build uses a cached version, cache still valid | Can continue downloading |
| Build requests an uncached version | May fail |
| Package index/metadata needs refresh while upstream is down | May error or serve cached data per rules |
| Artifact was deleted by cleanup | No cached copy left to serve |
| Client lacks IAM or token expired | Still fails even if cache has the data |

Operational solutions:

1. **Pin dependencies** and test builds against the cache.
2. For production-critical artifacts, consider **publishing/mirroring vetted copies into a standard repo** via a Writer-authorized workflow with proper retention, rather than relying solely on remote cache.
3. Monitor HTTP errors, repository request counts, upstream availability, and quotas.
4. Keep known-good rollback versions/deployments.

### 14.3. Cloud Build, GKE, and Cloud Run

- **Cloud Build:** the build service account needs Reader to pull dependencies/base images and Writer to push outputs to standard. If using **custom worker pools** or restricted networks, check connectivity and Artifact Registry endpoint config.
- **GKE:** nodes or image-pull principals need Reader on the matching Docker repo; do not confuse this with Kubernetes ServiceAccounts/RBAC used by the application API.
- **Cloud Run:** deploys images from authorized repositories; check cross-project access, pull identities, and separate runtime service accounts.
- **Compute Engine:** build/pull VMs need appropriate OAuth scopes/IAM or environment credential helpers/tokens; avoid legacy service account keys when workload identity/ADC is available.

### 14.4. Do Not Treat Virtual as a Full-Featured HTTP Load Balancer

Virtual does not perform arbitrary path rewriting, application health checks, or network failover. It handles **artifact lookup/routing** across repositories; it does not replace Application Load Balancers, Private Service Connect, CDN, Cloud NAT, or VPC peering.

## 15. Cleanup Policies, Version Retention, and Cost

### 15.1. Distinguishing Storage Across Modes

| Mode | Costs to watch | Capacity considerations |
|---|---|---|
| **Standard** | Stored artifact bytes, read/write operations, network/analysis per pricing | Published artifacts can accumulate over years |
| **Remote** | Cache storage, egress/operations, scanning, and related upstream usage | Cache grows based on requested packages |
| **Virtual** | Stores no separate blobs; read requests/operations and upstream services per pricing | No "virtual cache" to clean up like standard/remote |

Exact costs depend on **region, egress paths, artifact sizes, pull counts, refresh frequency, vulnerability scanning**, and current Artifact Registry pricing. Do not assume a remote cache is always cheaper than every alternative.

### 15.2. Cleanup Policies

Artifact Registry provides **cleanup policies** to delete unneeded versions by age/tag conditions or retain a set count, with **dry-run** support depending on configuration.

Principles:

- For **standard**, retain releases/digests actively deployed or needed for rollback.
- For **remote**, purging unused cache saves space, though subsequent requests may need to re-fetch from upstream.
- For **virtual**, manage **upstream policies** rather than trying to clean up a non-existent physical artifact store.
- If reliable offline artifacts are required, avoid cleanup rules that purge the only scanned/approved copy.
- Review retention, immutable tags, constraints, and dry-run results before enabling destructive cleanup.

### 15.3. Pruning Unused Data

Periodically:

1. Inventory repositories, formats, modes, locations, and owners.
2. Inspect package counts/sizes and pull frequency.
3. Identify artifacts actively deployed, pinned in lockfiles, or needed for recovery.
4. Review policies before deleting; never delete an entire repository backing a virtual endpoint.
5. Monitor impacts on build latency, cache misses, upstream errors, and post-cleanup costs.

## 16. Troubleshooting: Repository Exists, Yet Artifacts Fail to Download

| Symptom | Common cause | How to check |
|---|---|---|
| **401 Unauthorized** on Docker pull | Credential helper not configured or expired token | `gcloud auth list`, `configure-docker`, Docker config, identity |
| **403 Forbidden** on virtual pull | Client lacks Reader on virtual or service agent lacks upstream access | Virtual IAM, upstream IAM, and service agent |
| **403** when build pushes to virtual | Virtual is **read-only** | Push to **standard** with Writer role |
| **403** on Docker Hub remote fetch | Invalid upstream token or missing Secret Manager permissions | Remote config, secret version, service agent, Docker Hub account |
| **404 Not Found** via virtual | Package/version absent from all eligible upstreams | Version pin, upstream contents, policy, location/format |
| **404** despite package existing in private upstream | Service agent cannot read it, wrong resource name in policy, or stale metadata | Upstream IAM, repository paths, and logs |
| Docker pull **429 Too Many Requests** | Upstream Docker Hub rate limit, frequent cache misses | Configure upstream authentication, monitor quotas, cache policy |
| Java build picks unexpected public copy | Maven still hits Central directly, unpinned version, or wrong priority | Effective POM/settings, priority, resolved dependency tree |
| pip picks newer public package over private | Public `extra-index-url` present, unpinned `latest` | pip config, requirements/lockfiles, virtual-only index |
| Maven downloads plugins from Internet | Unmanaged `pluginRepositories`, Super POM, or another profile | Effective settings/POM, build logs |
| Docker virtual shows "empty" | Virtual stores no blobs | Inspect standard/remote and test pulling via virtual |
| Cache returns stale tag/metadata | Metadata update age, mutable Docker tags, client cache | Digest pinning, cache freshness, retry after interval |
| Remote cannot reach private Nexus | Upstream has only a private IP inside VPC/on-prem | Remote requires a supported internet-accessible HTTPS upstream |
| Remote fetch fails inside VPC SC | Upstream egress outside perimeter blocked | VPC SC policies and Artifact Registry remote access exceptions |
| Region change breaks virtual creation | Upstream in different location from virtual | Match format and location; create/migrate repo properly |
| Package missing after cleanup | Cache/standard artifact deleted | Cleanup policy, audit logs, upstream availability |
| IAM looks right, yet image deploy fails | Image-pull identity differs from runtime identity, quota, or missing digest | GKE/Cloud Run deploy logs, image URL/digest, Reader role |

### 16.1. Step-by-Step Diagnosis

1. **Repository:** inspect **format, mode, project, and location** via `gcloud describe`.
2. **Client identity:** verify which user/service account actually sends the request; check token expiration.
3. **Endpoint:** is the client hitting **virtual**, **remote**, **standard**, or a public registry directly?
4. **Upstream policy:** if virtual, inspect **resource paths and priorities**; do formats and locations match?
5. **Service agent:** can it read the upstreams? For private external upstreams, are Secret Manager credentials valid?
6. **Artifact version:** do the package and version truly exist upstream? If asking for latest, is the version pinned?
7. **Upstream/cache:** has remote cached the artifact, is metadata fresh, is the upstream rate-limited or down?
8. **Security perimeter:** IAM deny policies, VPC SC, org policies, CMEK, or license restrictions?
9. **Logs/metrics:** Artifact Registry request logs, audit logs, Cloud Build/GKE/Cloud Run errors, and request counts.
10. **Rollback:** if priority was just edited, restore the prior policy file or revert to a vetted image/library version.

### 16.2. A Useful Read-Only Command Sequence

~~~bash
gcloud artifacts repositories list \
  --project=shop-dev-001 --location=asia-southeast1

gcloud artifacts repositories describe maven-all \
  --project=shop-dev-001 --location=asia-southeast1

gcloud artifacts repositories describe maven-central-cache \
  --project=shop-dev-001 --location=asia-southeast1

gcloud artifacts repositories get-iam-policy maven-all \
  --project=shop-dev-001 --location=asia-southeast1

gcloud artifacts packages list \
  --project=shop-dev-001 \
  --location=asia-southeast1 \
  --repository=maven-central-cache
~~~

When debugging permission errors, do not assume upstream repos live in the same project. Inspect the **projects/.../locations/.../repositories/...** resource paths in the virtual policy and check IAM bindings in those respective projects.

## 17. Deployment Scenario: Shared Java and Container Platform

**Hung Thinh** Enterprise operates 30 services:

- 15 Java/Spring Boot services using Maven and internal company libraries.
- 10 APIs running on Cloud Run; 5 workers running on GKE.
- Base images from Docker Hub and approved public registries.
- Internal Java packages published by a dedicated CI pipeline, never made public.
- Security requires **preventing dependency confusion, controlling IAM, scanning, and saving traffic**.

### 17.1. Proposed Design

~~~mermaid
flowchart LR
    BUILD["Java build / Cloud Build"] --> MAV["maven-all virtual"]
    MAV -->|"100"| JPR["java-private standard"]
    MAV -->|"20"| MRC["maven-central-cache remote"]
    MRC --> CENTRAL["Maven Central"]
    BASE["Docker build / deploy"] --> DOC["docker-all virtual"]
    DOC -->|"100"| IPR["images-private standard"]
    DOC -->|"10"| DRC["dockerhub-cache remote"]
    DRC --> HUB["Docker Hub"]
    BUILD -->|"publish JAR"| JPR
    BUILD -->|"push image"| IPR
    DOC --> RUNTIME["GKE / Cloud Run"]
~~~

### 17.2. Access Control Policy

| Actor | Permitted action | Repository |
|---|---|---|
| Java build runner | Download dependencies | `maven-all` Reader |
| Internal Java publisher | Publish CI-approved versions | `java-private` Writer |
| Container build publisher | Push built and scanned images | `images-private` Writer |
| GKE/Cloud Run image-pull identities | Pull images | `docker-all` or `images-private` Reader per deploy model |
| Artifact Registry service agent | Read upstreams per policy | `java-private`, `maven-central-cache`, `images-private`, `dockerhub-cache` |
| Platform admin | Manage modes/upstream policies | Admin-scoped repositories |

Do not grant **Artifact Registry Admin** to all jobs just because they share one virtual URL. When external pipelines access GCP, use **Workload Identity Federation** and bind principals to the minimum repo role.

### 17.3. Release Objectives

1. **Reproducible releases:** Maven versions/locks and Docker digests recorded in build manifests.
2. **Private-first:** all Java builds access only **maven-all**, with no parallel public repos.
3. **Caching:** public dependencies fetched on first miss via remote and reused from cache.
4. **No direct publishing to virtual:** pipelines hold Writer on standard, only Reader on virtual.
5. **Security:** vulnerability reviews, image provenance, IAM/access logs, and Secret Manager.
6. **Operations:** cleanup with dry-run, alerts on cache/upstream failures, upstream policy rollback.
7. **Cost:** monitor cached bytes, pulls, storage growth, network, and scanning within budget.

### 17.4. Acceptance Matrix

| Test | Expectation |
|---|---|
| Maven fetches pinned internal JAR | Selects `java-private` per policy |
| Maven fetches uncached Maven Central package | Remote fetches and caches |
| Rebuild cached version during brief upstream outage | Continues if cache is valid |
| Package/version missing from both upstreams | Fails cleanly, never silently pulls from a third source |
| pip configured with public `extra-index-url` | Detected and remediated to virtual-only |
| Docker pulls approved base image | Succeeds via `docker-all` |
| Push image to `docker-all` | Rejected as read-only |
| Push image to `images-private` with Writer | Succeeds |
| Client without Reader on virtual | Denied |
| Service agent upstream permission revoked | Test catches misconfiguration to fix IAM, not disable security |
| Update priority then roll back | Restores prior policy and expected version/digest |
| Scan finds critical vulnerability | Workflow blocks promotion and replaces dependency |
| Purge old cache | Does not break rollback releases or offline builds |

### 17.5. When NOT to Use Remote/Virtual?

If an enterprise has only **one private repository**, clients always pull exact versions from it, and no upstream aggregation is needed, a **standard repo** may be enough. Do not create a virtual repo just to add extra configuration layers.

If a private upstream **lives only inside a VPC/on-premises without a public endpoint**, a remote repo cannot reach it directly; use a different design (sync packages into standard via pipeline, or products/proxies supporting the required network path).

If policy requires checking **every request** directly against the upstream and forbids caching, consider **connector mode (Preview)** per supported formats/features, while evaluating latency, upstream availability, and cost.

## 18. Practice Exercises

### Exercise A — Classifying Standard, Remote, and Virtual

Choose the mode:

1. A pipeline needs to **push** JAR **com.company:billing-core:2.0.1**.
2. Builds need public packages from Maven Central with caching.
3. All Maven builds need a single shared URL for private and public packages.
4. Security policy forbids caching upstream artifacts and the format supports connector mode.
5. Built images must become official rollback-capable artifacts.

**Answers:** (1) Standard Maven; (2) Remote Maven; (3) Virtual Maven; (4) consider Connector (Preview); (5) Standard Docker.

### Exercise B — Reading Virtual Priority

A virtual repo has:

| Upstream | Priority | Has `com.company:client:1.0.0`? |
|---|---:|---|
| `private` | 100 | Yes |
| `central-cache` | 20 | Yes |
| `legacy` | 100 | Yes |

**Questions:**

1. If a client requests exact version **1.0.0**, is it guaranteed to come from `private`?
2. Why are two sources tied at priority 100 risky?
3. How do you fix this if only `private` should serve that package?

**Answers:** (1) Not guaranteed, because `private` and `legacy` tie; (2) the system may return from either one; (3) assign distinct priorities per policy, remove unauthorized sources, pin versions/digests, and verify provenance.

### Exercise C — Dependency Confusion via pip

A client has:

~~~ini
[global]
index-url = https://asia-southeast1-python.pkg.dev/shop-dev-001/python-private/simple/
extra-index-url = https://pypi.org/simple
~~~

**Questions:**

1. Will pip definitely pick the private package if a same-named public package has a higher version?
2. How should you fix the configuration so private gets priority?
3. What additional controls prevent accidentally pulling malicious code?

**Answers:** (1) No; pip selects candidates by version and resolver rules without guaranteeing private-first; (2) use a **python-all virtual** repo combining high-priority private standard and low-priority PyPI remote, and remove the public `extra-index-url`; (3) version pinning/lockfiles/hashes, scanning, dependency reviews, and IAM.

### Exercise D — Remote Cache During an Upstream Outage

Docker Hub is temporarily unavailable. Inside **dockerhub-cache**:

- Image **busybox:1.36** was cached earlier.
- Image **some-image:2.0.0** has never been cached.

**Question:** Are all pulls guaranteed to succeed? Why does caching not replace backups?

**Answer:** No. Already-cached artifacts can continue serving, while uncached ones will fail; deleted/expired caches, metadata refreshes, or IAM errors can also break pulls. For production-critical versions, mirror/approve copies in a standard repo and pin digests.

### Exercise E — Multi-Project Service Agent Permissions

Virtual Maven lives in **platform-registry-001**; standard Maven lives in **java-team-001**.

**Questions:**

1. Where does the Java build client need Reader?
2. Which principal reads the upstream?
3. Why is granting Reader only on virtual insufficient?
4. Which permission/role grants narrow upstream access?

**Answers:** The build client needs Reader on virtual; the **virtual project's Artifact Registry Service Agent** reads the upstream. Grant `roles/artifactregistry.reader` on the upstream or a custom role with **artifactregistry.repositories.readViaVirtualRepository** per guidance, avoiding broad Editor/Owner.

### Exercise F — Reviewing a Priority Change

A team updates `maven-all` from:

~~~text
java-private priority 100
maven-central-cache priority 20
~~~

to:

~~~text
java-private priority 10
maven-central-cache priority 100
~~~

**Question:** What risk arises if both sources share a package/version? What steps are required before release?

**Answer:** The public remote repo takes precedence over private, changing package origins. Review the change, test clean builds, compare checksums/artifact sources, prepare a policy rollback, and deploy to staging first.

### Exercise G — Designing a Java/GKE System

Design a setup where:

- Private Maven libs are published by the Java team.
- Maven Central packages are read only through cache.
- Base images from Docker Hub are controlled.
- Built Java images are pushed to a private Docker repo.
- Production GKE pulls only approved images.

**Expected output:** repository mode diagram, IAM table, client URL config, policy JSON, dependency/image digest pinning strategy, monitoring, and cleanup. Explicitly note that **pushes must target standard**, never virtual or remote.

## 19. Operational Checklist and Runbook

### 19.1. Before Creating Repositories

1. Determine the **format**: Docker, Maven, npm, Python, Go, or other.
2. List private packages and approved public upstreams.
3. Choose **location** and verify availability/pricing.
4. Name repos by function: **private**, **cache**, **all/virtual**.
5. Identify caller identities, service agents, and least-privilege IAM.
6. Check Secret Manager credentials if upstreams require authentication.
7. Check VPC SC/CMEK/org policies.
8. Define cached data scope, retention, and scanning needs.

### 19.2. Before Using Virtual in CI/CD

1. All upstreams share the same format/location and already exist.
2. Virtual policy JSON uses **distinct priorities** where deterministic precedence is needed.
3. The service agent can read all upstreams, including cross-project ones.
4. Clients point strictly to the virtual endpoint, with no leftover public registries in configs.
5. Dependency versions and Docker images are pinned per policy.
6. Staging builds succeed with both warm and cold caches.
7. 401/403/404 error handling is verified before rollout.
8. A prior version of the policy JSON is saved for rollback.

### 19.3. When a Production Build Cannot Find a Package

~~~mermaid
flowchart TD
    E["Build / pull failure"] --> ID{"401/403?"}
    ID -->|Yes| AUTH["Check client auth, Reader/Writer,<br/>service agent, Secret Manager"]
    ID -->|No| N{"404 / missing version?"}
    N -->|Yes| SRC["Check actual package/version,<br/>policy priority, upstream location"]
    N -->|No| UP{"429/5xx/timeout?"}
    UP -->|Yes| CACHE["Upstream rate limit/outage,<br/>VPC SC, remote cache, quota"]
    UP -->|No| OTHER["Inspect build client/proxy logs"]
    AUTH --> RETEST["Retry in controlled environment"]
    SRC --> RETEST
    CACHE --> RETEST
    OTHER --> RETEST
~~~

**Never fix this by granting Artifact Registry Admin to all build runners** or embedding public tokens in source code. Identify which layer is rejecting the request.

### 19.4. Post-Incident Actions

- Record **package/version or image digest**, endpoint URL, project/location, and caller identity.
- Record **HTTP code, resolution stage, upstream state, and repository mode**.
- If cache-related, check whether the artifact was cached and who/what removed it.
- If IAM-related, adjust roles/service agents at the narrowest scope.
- If dependency-confusion-related, isolate potentially affected packages and inspect build provenance.
- Update lockfiles, upstream policies, runbooks, and alerts as needed.

## 20. Summary and Reference Documentation

**Eight core principles:**

1. **Standard** stores and receives **internal artifact publishes**; **remote** **proxies/caches** an upstream; **virtual** provides a **single read endpoint** without storing blobs.
2. Remote caches **only requested artifacts** rather than pre-mirroring the entire upstream; caching aids reliability but does not replace offline mirrors or backups.
3. In virtual repos, **higher priority numbers win**; tied priorities may return from any tied source. **Pin versions** because priority alone does not override a client requesting "latest."
4. **Mitigate dependency confusion** by prioritizing private standard repos and configuring package managers to use only the virtual endpoint—never querying PyPI/Maven Central/npm directly in parallel.
5. **Client Reader**, **publisher Writer**, and **Artifact Registry service agent upstream Reader** are distinct roles; private remote credentials belong in Secret Manager.
6. Virtual upstreams must share **format and location**; custom remote upstream URLs require **HTTPS** and do not support VPC-only/on-prem-only endpoints without public reachability.
7. **VPC SC, scanning, provenance, digest pinning, IAM, cleanup, and monitoring** remain essential; proxying/caching does not make packages safe by itself.
8. A sound architecture balances performance, security, rollback readiness, and cost across Compute Engine, GKE, Cloud Run, Cloud Build, and Java workloads.

**Official Google Cloud documentation:**

1. [Artifact Registry overview](https://docs.cloud.google.com/artifact-registry/docs/overview) — repository modes and GCP ecosystem integration.
2. [Repository overview](https://docs.cloud.google.com/artifact-registry/docs/repositories) — standard, remote, connector, virtual.
3. [Remote repositories overview](https://docs.cloud.google.com/artifact-registry/docs/repositories/remote-overview) — caching, metadata freshness, upstream formats, and limitations.
4. [Create remote repositories](https://docs.cloud.google.com/artifact-registry/docs/repositories/remote-repo) — gcloud remote flags, private upstreams, Secret Manager.
5. [Virtual repositories overview](https://docs.cloud.google.com/artifact-registry/docs/repositories/virtual-overview) — priority, dependency confusion, and limits.
6. [Create virtual repositories](https://docs.cloud.google.com/artifact-registry/docs/repositories/virtual-repo) — upstream policy JSON, gcloud create/update, service agent IAM.
7. [Supported formats](https://docs.cloud.google.com/artifact-registry/docs/supported-formats) — container, package, and pipeline formats.
8. [Create standard repositories](https://docs.cloud.google.com/artifact-registry/docs/repositories/create-repos) — publishing private artifacts.
9. [Maven/Gradle authentication](https://docs.cloud.google.com/artifact-registry/docs/java/authentication) — credential helpers and package resolvers.
10. [Python authentication](https://docs.cloud.google.com/artifact-registry/docs/python/authentication) — pip `index-url` and avoiding `extra-index-url`.
11. [Python package management](https://docs.cloud.google.com/artifact-registry/docs/python/manage-packages) — virtual priorities and dependency resolution.
12. [Quickstart: Docker Hub remote repository](https://docs.cloud.google.com/artifact-registry/docs/repositories/create-dockerhub-remote-repository) — image caching, Secret Manager, and Docker authentication.
13. [Cleanup policies](https://docs.cloud.google.com/artifact-registry/docs/repositories/cleanup-policy) — managing versions/caches with retention rules.
14. [gcloud artifacts repositories create](https://docs.cloud.google.com/sdk/gcloud/reference/artifacts/repositories/create) — command flags and formats.
15. [Artifact Registry access control](https://docs.cloud.google.com/artifact-registry/docs/access-control) — Reader/Writer/Service Agent permissions.
