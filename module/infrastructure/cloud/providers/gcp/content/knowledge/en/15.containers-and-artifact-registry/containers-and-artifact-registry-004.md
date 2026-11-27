# Storing Maven Artifacts for Java Projects with Artifact Registry

> **Chapter:** Containers and Artifact Registry  
> **Lesson:** Storing Maven artifacts for Java projects  
> **Module:** CLOUD_PROVIDERS_GCP

In the **CLOUD_PROVIDERS_GCP** module, learners explore Google Cloud from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage services, and databases. Through deployment scenarios, learners learn how to select services, protect resources, automate releases, and monitor reliability and cost. An essential capability of Java release workflows is **storing, versioning, and distributing built libraries**, rather than copying JARs manually or rebuilding the same package in every application.

**Artifact Registry** supports repositories in multiple formats; **Maven-format repositories** store JARs, POMs, and Java artifacts used with Maven or Gradle. This hands-on lesson publishes the `order-common` library to a **standard Maven repository**, then consumes it from the `orders-api` application as a Maven dependency. We also cover authentication via **Application Default Credentials (ADC)**, CI/CD permissions, version policies, and dependency governance.

**Do not confuse a Maven repository with a Docker repository**: a Maven repo stores Java packages by groupId/artifactId/version; a Docker repo stores OCI container images for Cloud Run or GKE deployments. Both live inside Artifact Registry, yet **each repository has only one artifact format**. Publishing a JAR to a Maven repository **does not automatically deploy** an application to Cloud Run.

All project IDs, repositories, packages, and service accounts in this lesson are examples. Commands to create repositories, modify IAM, publish, or delete packages can change infrastructure and incur charges; run them only in an **approved sandbox**.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Distinguish Maven artifacts, Maven coordinates, POMs, repositories, versions, snapshots, and releases.
2. Choose the right **standard, remote, or virtual repository** for internal publishing and dependency downloads.
3. Create a standard Maven repository via the Console/`gcloud`, selecting an appropriate location and version policy.
4. Configure `pom.xml` to **publish** via `distributionManagement` and **consume** via `repositories`.
5. Use the **Artifact Registry Maven wagon** or **Gradle plugin** with ADC instead of storing private keys in source code.
6. Run `mvn deploy` or `gradle publish`, then verify packages and versions in Artifact Registry.
7. Consume an internal Java library from another project and diagnose unresolved parent POMs/plugins.
8. Assign Reader/Writer/Admin permissions for developers, CI publishers, and consumers.
9. Design release workflows, build reproducibility, snapshot management, cleanup, supply-chain security, and cost controls.
10. Isolate 401/403/404 errors, `artifactregistry://` protocol issues, policy mismatches, Maven caching, and networking issues.

## 2. What Role Do Maven Artifacts Play in Java Architecture?

~~~mermaid
flowchart LR
    Git["Git: order-common<br/>Java source"]
    CI["CI: Maven verify<br/>package + test"]
    MavenRepo["Artifact Registry<br/>Maven standard"]
    Consumer["orders-api<br/>Maven dependency"]
    Build["App build<br/>JAR or OCI image"]
    Docker["Artifact Registry<br/>Docker repository"]
    Runtime["Cloud Run / GKE"]
    VM["Compute Engine"]
    Git --> CI
    CI -->|"Writer / publish"| MavenRepo
    MavenRepo -->|"Reader / download"| Consumer
    Consumer --> Build
    Build --> Docker
    Docker --> Runtime
    Build --> VM
~~~

**Each component has a distinct responsibility:**

- **Java library**: reusable code, such as an order-code normalizer, API client, or internal company SDK.
- **Maven build**: resolves the dependency graph, compiles, tests, packages artifacts, and generates POM metadata.
- **Maven repository**: the place where a package at a specific version can be retrieved.
- **Docker repository**: the place storing container images after the application is packaged with its runtime.
- **Cloud Run/GKE**: runs container images; does not directly execute Maven packages in the registry.
- **Compute Engine**: can run Java JARs via systemd or images/instance templates; Docker is not mandatory.

### 2.1. When Should You Have an Internal Maven Repository?

| Case | Benefit |
|---|---|
| Shared library for Orders, Billing, and Inventory | Each consumer depends on a tested version |
| Internal SDK or API integration client | Controlled contract reuse |
| Company parent POM or BOM | Centralized version and build-convention management |
| Non-public libraries | Internal IAM, auditing, and publishing control |
| Pipelines requiring reproducible artifacts | Stores GAVs and build metadata for rollback |
| Spring Boot app storing a JAR before building an image | Can store JARs and containers in separate repository formats |

If an application has only a single codebase and always builds/deploys a self-contained image, creating a dedicated Maven repository is **optional**. Weigh the number of consumers against operational overhead.

## 3. Maven Coordinates and Package Layout

Maven typically identifies artifacts via **GAV**:

~~~text
groupId    : com.example.platform
artifactId : order-common
version    : 1.0.0-SNAPSHOT

GAV = com.example.platform:order-common:1.0.0-SNAPSHOT
~~~

| Property | Role | Example |
|---|---|---|
| `groupId` | Organization namespace | `com.example.platform` |
| `artifactId` | Module identifier | `order-common` |
| `version` | Version | `1.0.0-SNAPSHOT` |
| `packaging` | Artifact type | `jar` or `pom` |
| `classifier` | File variant, if published | `sources`, `javadoc` |
| `dependency scope` | How consumers use it | `compile`, `runtime`, `test` |

Example release layout:

~~~text
com/example/platform/order-common/1.0.0/
  order-common-1.0.0.pom
  order-common-1.0.0.jar
  order-common-1.0.0-sources.jar     (if published)
  order-common-1.0.0-javadoc.jar     (if published)
~~~

**A POM is not decorative.** It contains coordinates, dependencies, metadata, and packaging details. Publishing a JAR without an appropriate POM can prevent Maven consumers from resolving transitive dependencies or yield incorrect metadata.

### 3.1. Snapshots and Releases

| Type | Example | Meaning | Practice |
|---|---|---|---|
| Snapshot | `1.0.0-SNAPSHOT` | Under active development; may change on subsequent builds | Use in dev/test |
| Release | `1.0.0` | Finalized build per release process | Use in production |
| Convention pre-release | `1.1.0-rc.1` | Release candidate prior to final release | Requires clear team policy |

Maven 3 uses **timestamped unique snapshots** when deploying. Multiple builds published under the same base version `1.0.0-SNAPSHOT` get distinct timestamps/build numbers; consumers may pick up newer builds per Maven metadata and update policies. **Never use unpinned snapshots for a production release requiring strict reproducibility.**

### 3.2. Artifact Registry Maven Version Policies

Artifact Registry supports three policies at repository creation time:

- **None**: stores both snapshots and releases; the default.
- **Snapshot**: stores snapshots only.
- **Release**: stores releases only.

There is an option allowing non-unique snapshot overwrites on Snapshot repositories; Maven 3 should use **unique snapshot versions** to avoid cache conflicts. If a repository has a Release policy, `mvn deploy` with a version ending in `-SNAPSHOT` will be rejected even if IAM and the URL are correct.

## 4. Standard, Remote, and Virtual Repositories

| Mode | Purpose | Publish internal JARs? |
|---|---|---|
| **Standard** | Primary repository storing organization-built packages | **Yes** |
| **Remote** | Proxies/caches an upstream source such as Maven Central | **No**, used for reading/caching |
| **Virtual** | Unified read endpoint aggregating multiple standard/remote upstreams | **Not a direct publish target** |

~~~mermaid
flowchart TD
    Dev["Developer / CI publish"]
    Release["Standard: java-release"]
    Snap["Standard: java-snapshot"]
    Remote["Remote: maven-central-cache"]
    Virtual["Virtual: java-dependencies"]
    Apps["Maven / Gradle consumers"]
    Central["Maven Central"]
    Dev --> Release
    Dev --> Snap
    Central --> Remote
    Release --> Virtual
    Snap --> Virtual
    Remote --> Virtual
    Virtual --> Apps
~~~

In an enterprise model:

1. **CI publisher** writes to the standard repository matching the version type.
2. **Consumers** can read through the virtual repository once upstreams and IAM are configured.
3. **Remote Maven Central** downloads packages from upstream on cache miss and serves cached copies thereafter.
4. **Virtual** resolves upstream precedence by priority when a coordinate/version exists in multiple sources.
5. **Dependency confusion** can occur if internal GAVs collide with packages from external repositories. Choose collision-resistant namespaces, control priorities, and test resolution.

Remote repositories do not automatically proxy arbitrary private repositories inside a VPC or on-premises; upstream type and reachability must meet service requirements. For learning how to publish, this lab uses only the **standard repository `java-libs-lab`**.

## 5. Preparing the Project, API, Network, and IAM

### 5.1. Lab Parameters

| Property | Assumed value |
|---|---|
| Repository project | `PROJECT_ID` |
| Location | `asia-southeast1` |
| Artifact Registry API | `artifactregistry.googleapis.com` |
| Repository ID | `java-libs-lab` |
| Format / Mode | Maven / Standard |
| Version policy | None (accepts snapshots and releases) |
| Maven GAV | `com.example.platform:order-common:1.0.0-SNAPSHOT` |
| Java | JDK 17 |
| Build tool | Maven 3.x, Gradle in the extension section |
| CI publisher | Dedicated service account with Writer |
| Consumer | User or workload with Reader |

Read-only status checks (no resource mutations):

~~~bash
gcloud auth list
gcloud config get-value project

gcloud services list --enabled \
  --project=PROJECT_ID \
  --filter="NAME:artifactregistry.googleapis.com"

gcloud artifacts repositories list \
  --project=PROJECT_ID \
  --location=asia-southeast1
~~~

If the API is not enabled, an authorized administrator must enable it per process; do not grant yourself Owner to "make it work." In a private VPC, also verify DNS/HTTPS egress or the organization's designed path to Google APIs.

### 5.2. Role-Based IAM Matrix

| Group / identity | Appropriate role | Scope |
|---|---|---|
| Person or pipeline only downloading dependencies | `roles/artifactregistry.reader` | Maven repository to read |
| CI publishing libraries | `roles/artifactregistry.writer` | Target standard repository |
| Package manager deleting versions | `roles/artifactregistry.repoAdmin` | Assigned repository |
| Project-level administrator creating repositories | `roles/artifactregistry.admin` | Approved scope |

**Repository Writer is not Repository Administrator.** Publishers generally do not need to create repositories, delete repositories, or alter project-wide IAM. Pipelines running from another project must be granted permissions **in the repository project**.

### 5.3. Security Boundaries

- Never embed service account JSON/private keys in `pom.xml` or `build.gradle`.
- Consumers only downloading dependencies do not need upload/delete permissions.
- Cloud Run/GKE/VM runtimes do not need Writer if they consume prebuilt artifacts.
- Protect repositories with IAM, TLS, and provenance workflows; never assume internal artifacts are automatically safe.
- Include storage, egress, Cloud KMS, logging, and CI/CD costs in estimates.

## 6. Step 1 — Create a Standard Maven Repository

**The commands below create real resources and may incur charges. Run only in a sandbox.**

### 6.1. Using Google Cloud Console

1. Open **Artifact Registry → Repositories** in an approved project.
2. Select **Create repository**, name `java-libs-lab`.
3. Select **Format: Maven**, **Mode: Standard**.
4. Select location `asia-southeast1` or a supported region/multi-region.
5. Select Maven version policy **None** for this lab.
6. Review encryption (Google-managed by default; CMEK if policy requires), labels, and cleanup.
7. Create the repository and verify format/mode/location fields.

### 6.2. Using gcloud

~~~bash
gcloud artifacts repositories create java-libs-lab \
  --project=PROJECT_ID \
  --repository-format=maven \
  --location=asia-southeast1 \
  --description="Java Maven package repository for training" \
  --version-policy=none

gcloud artifacts repositories describe java-libs-lab \
  --project=PROJECT_ID \
  --location=asia-southeast1
~~~

Inspect the output to confirm `format: MAVEN`, standard mode, and the corresponding `mavenConfig`. Exact field names may vary depending on CLI/API version.

### 6.3. Separating Releases and Snapshots for Production

~~~bash
gcloud artifacts repositories create java-libs-snapshot \
  --project=PROJECT_ID \
  --location=asia-southeast1 \
  --repository-format=maven \
  --version-policy=snapshot

gcloud artifacts repositories create java-libs-release \
  --project=PROJECT_ID \
  --location=asia-southeast1 \
  --repository-format=maven \
  --version-policy=release
~~~

This is a reference pattern; align on naming, owners, and retention policies. **Do not grant broad Writer permissions across both release and snapshot repositories** if a pipeline's only job is publishing snapshots.

### 6.4. Reading the Repository URL

~~~text
artifactregistry://asia-southeast1-maven.pkg.dev/PROJECT_ID/java-libs-lab
                   └─ location ─┘      project    repository
~~~

The `artifactregistry://` scheme requires a transport helper provided by the Maven wagon or Gradle plugin. HTTPS endpoints can be used with other authentication mechanisms, but **do not switch the scheme without addressing authentication**.

## 7. Step 2 — Create the Java Library and POM

Example package `order-common` containing a function that normalizes order codes.

~~~text
order-common/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/example/platform/OrderCode.java
~~~

### 7.1. Java Source

~~~java
package com.example.platform;

import java.util.Locale;
import java.util.Objects;

public final class OrderCode {
    private OrderCode() { }

    public static String normalize(String raw) {
        String value = Objects.requireNonNull(raw, "raw").trim();
        if (value.isEmpty()) {
            throw new IllegalArgumentException("order code must not be empty");
        }
        return value.toUpperCase(Locale.ROOT);
    }
}
~~~

This is a pure Java library requiring no Google Cloud APIs or credentials at runtime.

### 7.2. Publisher POM

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example.platform</groupId>
  <artifactId>order-common</artifactId>
  <version>1.0.0-SNAPSHOT</version>
  <packaging>jar</packaging>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <distributionManagement>
    <snapshotRepository>
      <id>artifact-registry</id>
      <url>artifactregistry://asia-southeast1-maven.pkg.dev/PROJECT_ID/java-libs-lab</url>
    </snapshotRepository>
    <repository>
      <id>artifact-registry</id>
      <url>artifactregistry://asia-southeast1-maven.pkg.dev/PROJECT_ID/java-libs-lab</url>
    </repository>
  </distributionManagement>

  <build>
    <extensions>
      <extension>
        <groupId>com.google.cloud.artifactregistry</groupId>
        <artifactId>artifactregistry-maven-wagon</artifactId>
        <version>2.2.5</version>
      </extension>
    </extensions>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Replace `PROJECT_ID` with your real project before running. Plugin versions shown are concrete examples fitting the walkthrough; **check compatibility with your Maven/JDK versions and current release notes** when upgrading.

### 7.3. Three Distinct Configuration Sections

| POM section | Function | Question |
|---|---|---|
| `<distributionManagement>` | Defines where `mvn deploy` **uploads artifacts** | Where do we publish? |
| `<repositories>` | Defines where Maven **downloads dependencies** | Where does the build fetch libraries from? |
| `<build><extensions>` | Loads the Maven wagon for `artifactregistry://` | Which transport/auth helper does Maven use? |

A **consumer-only** project does not need `distributionManagement`. A **publishing** project with only `<repositories>` typically fails with a missing deploy repository error.

### 7.4. Use `print-settings` Instead of Guessing XML

~~~bash
gcloud artifacts print-settings mvn \
  --project=PROJECT_ID \
  --repository=java-libs-lab \
  --location=asia-southeast1
~~~

This command **prints the configuration** recommended by Google Cloud for that repository. In projects with complex POMs, merge the snippets into existing `distributionManagement`, `repositories`, and `build` blocks rather than creating duplicate root-level elements.

## 8. Step 3 — Authenticate Maven Safely

### 8.1. Credential Helper and ADC

The Artifact Registry Maven wagon can obtain credentials from **Application Default Credentials** and an appropriate Google Cloud CLI context. Preferences:

| Environment | Recommended mechanism |
|---|---|
| Developer laptop | User ADC per organizational policy |
| Cloud Shell | Active identity; verify actual permissions |
| Cloud Build | Build service account with appropriate Reader/Writer IAM |
| Compute Engine | VM-attached service account if the build pipeline runs on a VM |
| GKE/Cloud Run workloads | Workload identity or appropriate service identity |
| CI outside Google Cloud | Workload Identity Federation/short-lived credentials |

Verify:

~~~bash
gcloud auth list
gcloud config get-value project
~~~

On a **local development machine** following approved procedures, you can initialize ADC:

~~~bash
gcloud auth application-default login
~~~

`gcloud auth login` and `gcloud auth application-default login` **can manage separate credential contexts**. Someone seeing the right account in `gcloud auth list` may still have Maven using a different ADC identity. In non-interactive CI, **never run human interactive login commands**; use service identities/federation.

Never print or paste access tokens into logs just to debug. Run a read-only repository command or build a non-sensitive package and inspect the HTTP status code.

### 8.2. Wagon and Plugin Resolution

Maven wagon example:

~~~xml
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

If a project references a **private parent POM** or needs to resolve **plugin dependencies** from Artifact Registry before Maven parses the project POM, use the core extension `.mvn/extensions.xml`:

~~~xml
<extensions xmlns="http://maven.apache.org/EXTENSIONS/1.0.0"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
            xsi:schemaLocation="http://maven.apache.org/EXTENSIONS/1.0.0
            http://maven.apache.org/xsd/core-extensions-1.0.0.xsd">
  <extension>
    <groupId>com.google.cloud.artifactregistry</groupId>
    <artifactId>artifactregistry-maven-wagon</artifactId>
    <version>2.2.5</version>
  </extension>
</extensions>
~~~

Core extensions load early, allowing Maven to fetch the parent POM from `artifactregistry://`. You do not need core extensions for every simple project; choose one consistent management pattern to avoid redundant configuration.

### 8.3. Avoid Long-Lived JSON Service Account Keys

Google Cloud provides compatibility options for tools supporting only HTTPS username/password with JSON keys, but **long-lived keys carry leakage risk**. Never put them into `pom.xml`, committed `settings.xml`, source code, Dockerfiles, or CI logs. If unavoidable, store them in an approved secret manager with rotation/revocation and least privilege. **Credential helpers + short-lived identities** are the preferred default.

## 9. Step 4 — Build and Publish the Library

Inside the `order-common` directory:

~~~bash
java -version
mvn -version

# Compile, test, and package.
mvn clean verify

# Publish via distributionManagement to the Maven repository.
mvn deploy
~~~

With `1.0.0-SNAPSHOT` and policy `None`, Maven publishes the JAR/POM files along with version metadata per Maven conventions. Never use `-DskipTests` to hide build failures; skip tests only when the pipeline has another approved testing stage.

File generated on the build machine:

~~~text
target/order-common-1.0.0-SNAPSHOT.jar
~~~

Inside the repository, Maven 3 may use **timestamped unique snapshot filenames**. `mvn deploy` does not necessarily store the exact local filename verbatim in the server storage path.

### 9.1. Verify Packages and Versions

~~~bash
gcloud artifacts packages list \
  --project=PROJECT_ID \
  --repository=java-libs-lab \
  --location=asia-southeast1

gcloud artifacts versions list \
  --project=PROJECT_ID \
  --repository=java-libs-lab \
  --location=asia-southeast1 \
  --package=com.example.platform:order-common
~~~

Expect to see a package named `groupId:artifactId` and at least one version corresponding to the published artifact. You can also use the Console to inspect versions/files. If nothing appears, verify the exact project/location/repository and IAM before publishing again.

### 9.2. Moving to Release Publishing

When an approved release version is ready, update the POM:

~~~xml
<groupId>com.example.platform</groupId>
<artifactId>order-common</artifactId>
<version>1.0.0</version>
~~~

If production has separate repositories, `distributionManagement/repository` must point to the **release standard repo**, while `snapshotRepository` points to the **snapshot standard repo**. The lab uses `java-libs-lab` with policy `None`, so both URLs point to the same repository.

**Do not assume renaming a JAR to `1.0.0` is enough.** The POM, GAV, build metadata, and consumer dependency declarations must match. Never reuse a release version for different contents, to avoid cache and provenance conflicts.

### 9.3. Publishing External Artifacts with `deploy-file`

If a JAR was built outside Maven and has a matching POM:

~~~bash
mvn deploy:deploy-file \
  -Durl=artifactregistry://asia-southeast1-maven.pkg.dev/PROJECT_ID/java-libs-lab \
  -DrepositoryId=artifact-registry \
  -Dfile=dist/order-common-1.0.0.jar \
  -DpomFile=dist/pom.xml
~~~

This requires the file to exist, the Maven wagon to be loaded, accurate POM metadata, and Writer permission on the principal. Do not use this example to publish "unknown-origin JARs" by fabricating a dummy POM to bypass checks.

## 10. Step 5 — Consumer Downloads the Internal Dependency

Suppose `orders-api` needs `order-common:1.0.0-SNAPSHOT`. Add to the consumer's `pom.xml`:

~~~xml
<repositories>
  <repository>
    <id>company-maven</id>
    <url>artifactregistry://asia-southeast1-maven.pkg.dev/PROJECT_ID/java-libs-lab</url>
    <releases><enabled>true</enabled></releases>
    <snapshots><enabled>true</enabled></snapshots>
  </repository>
</repositories>

<dependencies>
  <dependency>
    <groupId>com.example.platform</groupId>
    <artifactId>order-common</artifactId>
    <version>1.0.0-SNAPSHOT</version>
  </dependency>
</dependencies>
~~~

The consumer also needs the **Artifact Registry Maven wagon** in `<build><extensions>` or `.mvn/extensions.xml`, plus **Reader IAM**. `distributionManagement` is not required if the consumer only downloads dependencies.

Consuming code:

~~~java
package com.example.orders;

import com.example.platform.OrderCode;

public class OrdersApp {
    public static void main(String[] args) {
        System.out.println(OrderCode.normalize(" od-123 "));
    }
}
~~~

Test:

~~~bash
mvn -U clean verify
mvn dependency:tree
~~~

`-U` forces Maven to check for updated snapshots/metadata, useful if a newly published snapshot has not been fetched yet. Production should use **explicitly pinned release versions** and a controlled dependency graph.

### 10.1. Why Does the Build Work on a Laptop but Fail in CI?

Maven keeps a local cache in `~/.m2/repository`. A developer with a previously cached artifact can still compile even when a freshly initialized CI environment lacks Reader permission. Avoid concluding from "it works on my machine" that repository and IAM settings are right.

Test builds in a clean environment/CI, verifying exact dependency GAVs and the active identity. **Do not wipe the entire cache on a shared machine** when diagnosing a single artifact.

### 10.2. If the POM Has a Private Parent

Maven must resolve `<parent>` early before reading extensions inside the child POM. If you see:

~~~text
Non-resolvable parent POM
Unsupported repository transport artifactregistry
~~~

Check the **core extension in `.mvn/extensions.xml`**, repository URL, Reader IAM, and parent GAV. Never publish a private parent POM to public Maven Central just to make builds pass.

## 11. Publishing/Consuming Maven Artifacts with Gradle

Artifact Registry supports Maven-format packages produced by **Gradle Maven Publish** and Google Cloud's authentication plugin.

### 11.1. Example `build.gradle` Groovy DSL

~~~groovy
plugins {
    id 'java-library'
    id 'maven-publish'
    id 'com.google.cloud.artifactregistry.gradle-plugin' version '2.2.5'
}

group = 'com.example.platform'
version = '1.0.0-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
    maven {
        url "artifactregistry://asia-southeast1-maven.pkg.dev/PROJECT_ID/java-libs-lab"
    }
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
        }
    }
    repositories {
        maven {
            url "artifactregistry://asia-southeast1-maven.pkg.dev/PROJECT_ID/java-libs-lab"
        }
    }
}
~~~

Example commands:

~~~bash
./gradlew clean test
./gradlew publish
~~~

In Windows PowerShell, use the matching wrapper `gradlew.bat publish` if the project includes a wrapper. Do not assume Gradle is preinstalled or a wrapper exists if the project has not been initialized.

### 11.2. Differences from Maven

- Gradle's `repositories` block is for **reading dependencies**.
- `publishing.repositories` is for **uploading artifacts**.
- `publications` defines what gets published from `components.java`; omitting a publication may cause `publish` not to upload the expected JAR/POM.
- The `com.google.cloud.artifactregistry.gradle-plugin` plugin provides protocol/auth support.
- If using private plugins during configuration, `settings.gradle` or `init.gradle` may need plugin/helper configuration distinct from `build.gradle`.

**Do not let both Maven and Gradle arbitrarily publish to the same release GAV.** Assign one authoritative pipeline to own each version and its metadata.

## 12. CI/CD and IAM Service Accounts

### 12.1. Build and Deploy Flow

~~~mermaid
flowchart LR
    Git["Git commit + PR review"] --> CI["Cloud Build / CI<br/>test + package"]
    CI -->|"Writer"| Maven["Maven standard<br/>order-common"]
    Maven -->|"Reader"| App["orders-api build"]
    App --> Image["Build OCI image"]
    Image --> Docker["Docker repository"]
    Docker --> Run["Cloud Run / GKE"]
    App --> VM["Compute Engine<br/>if running JAR"]
~~~

**Separate permissions by stage**:

| Stage | Identity | Permissions |
|---|---|---|
| Build and publish library | CI publisher SA | Writer on Maven standard repo |
| Build consumer | CI consumer SA | Reader on required Maven/remote/virtual repos |
| Build/push container | Image builder SA | Push permissions on Docker repository |
| Deploy Cloud Run/GKE | Deployer SA | Corresponding deploy/runtime permissions |
| Run application | Runtime SA | Data service permissions only; **no Maven Writer needed** |

**The Cloud Build service account can differ by project and trigger configuration.** Never hardcode a default account. Identify the actual build-executing account, then grant least-privilege permissions on the artifact repository—even when builds run in another project.

### 12.2. Example Granting Writer on the Right Repository

This command **modifies IAM** and should run only with approval:

~~~bash
gcloud artifacts repositories add-iam-policy-binding java-libs-lab \
  --project=PROJECT_ID \
  --location=asia-southeast1 \
  --member=serviceAccount:ci-publisher@PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/artifactregistry.writer
~~~

The service account above is a **placeholder** and must exist. Inspect the policy afterward:

~~~bash
gcloud artifacts repositories get-iam-policy java-libs-lab \
  --project=PROJECT_ID \
  --location=asia-southeast1
~~~

CI running in another project does not automatically gain access to the repository project. The Artifact Registry owner controls the IAM scope.

### 12.3. Auditable and Rollback-Ready Releases

A release pipeline can include:

1. Pull requests, code reviews, and protected branches.
2. CI with standardized JDK/Maven/Gradle versions.
3. Unit/integration tests, linting, SCA/dependency/license reviews.
4. Generating SBOMs or provenance metadata where required.
5. Publishing snapshots from development branches to the snapshot repo.
6. Finalizing releases from approved commits/tags, publishing to the right release repository.
7. Recording **GAV, source SHA, build ID, checksum**, and approver.
8. Consumers pin the version, run compatibility tests, and build container images if needed.
9. Deploying to Cloud Run/GKE/Compute Engine with health checks, monitoring, and rollback.

**A successful Maven deploy does not mean the artifact passed security checks.** The registry does not replace CI security gates. Do not claim Maven packages automatically receive vulnerability scanning identical to Docker images; the scope of each Artifact Analysis feature must be verified separately.

## 13. Remote Maven Central and Virtual Repositories

### 13.1. What Does a Remote Cache Solve?

A remote repository can use Maven Central as its upstream. On the first request for a version, Artifact Registry downloads and caches the artifact from upstream; subsequent requests can be served from cache. Benefits:

- Organization-managed dependency access endpoint.
- Easier policy enforcement, observability, and standardized consumer configuration.
- Reduced external network dependency once artifacts are cached.

**A cached package is not automatically "certified safe."** Dependency reviews and updates for CVEs/advisories are still required.

### 13.2. What Does Virtual Do?

A virtual repository provides a single read endpoint across multiple standard/remote upstreams. When the same GAV exists in multiple places, **upstream priority** controls which source is selected. If a private package name is published on a public repository with the same version, poor priority design can lead to **dependency confusion**.

Checklist:

1. Use a clearly governed internal namespace.
2. Order upstreams so internal packages receive appropriate precedence.
3. Allow only administrators to modify virtual upstreams/priorities.
4. Test dependency resolution and lock versions.
5. Never use a virtual repository as a publish target for internal artifacts.

### 13.3. Maven Central Super POM

When configuring Maven to use a remote Artifact Registry repo instead of the default Maven Central, Google Cloud guides show configuring repository ID **`central`** to override the URL inherited from the Maven Super POM. Otherwise, Maven may continue downloading directly from Maven Central despite having a remote proxy.

For build plugins, there is also **`<pluginRepositories>`** and the early wagon-loading requirement. Do not update only `<repositories>` and assume all plugin dependencies automatically route through the virtual endpoint.

## 14. Version Management and Artifact Provenance

### 14.1. Release Rules

| Rule | Why |
|---|---|
| Never reuse a release version for new contents | Prevents cache and provenance conflicts |
| Build only from controlled commits/tags | Maintains artifact traceability |
| Pin dependency and plugin versions | Improves reproducibility |
| Never deploy SNAPSHOTs indiscriminately to production | Versions can drift across builds |
| Retain versions still needed for rollback | Prevents cleanup from breaking incident recovery |
| Govern transitive dependencies too | One library can pull in many others |
| Maintain release notes and compatibility tests | Reduces breaking changes |
| Protect Writer permissions | Prevents unauthorized artifact uploads |

### 14.2. Incident Scenario from Inconsistent Versioning

Suppose `order-common:1.0.0` is released and the team later replaces the JAR without bumping the version. One consumer keeps the older copy in `~/.m2`, while a fresh CI run downloads the newer copy. Both appear to use the exact same version yet behave differently. Incident investigation becomes painful.

Solution: **publish a new version**, never mutate already-published release contents, verify checksums/GAVs, and record release provenance. When rolling back an application, pin to an **older stored and tested version**.

### 14.3. Maven Local Cache and Reproducibility

Maven caching speeds up builds, but can mask IAM or configuration errors:

- A passing offline build does not prove the registry is working.
- An older cached snapshot may differ from a newer published snapshot.
- Prior download failures can be cached by Maven, requiring `-U` refresh checks.
- Run controlled clean builds to confirm CI resolves packages from the intended source.

Never delete the entire local Maven repository on a shared machine without understanding the impact.

## 15. Supply Chain Security, Auditing, and Access Control

Artifact Registry is a **storage layer**, not a replacement for an end-to-end software trust pipeline.

- **Source trust:** PR checks, branch protection, code reviews.
- **Build trust:** CI uses trusted containers/toolchains without long-lived secrets.
- **Dependency trust:** pinned versions, SCA, license checks, upstream verification.
- **Artifact identity:** recorded GAVs, checksums, provenance/SBOMs as required.
- **Publication control:** Writer reserved for approved builds.
- **Consumption control:** appropriately scoped Readers for services and CI.
- **Deployment control:** approved image digests/versions and separate deployment pipelines.
- **Auditing:** track IAM changes, package publishes/deletions, and repository settings.

Never include sensitive data such as customer records, credentials, or signing private keys inside published JARs; even a private Maven repo may have more readers than expected.

## 16. Cost Management and Cleanup

### 16.1. Where Do Costs Come From?

| Category | Examples |
|---|---|
| Storage | JARs/POMs, numerous snapshot/release versions |
| Download/network | Fetching dependencies from another location or out to the Internet |
| Remote cache | Artifacts cached from Maven Central |
| CI compute | Build/test/package/dependency scanning |
| CMEK if used | Cloud KMS keys and cryptographic operations |
| Logging/Monitoring | Audit logs, metrics, and retention |

Use **Cloud Billing Reports** and **Artifact Registry pricing** to inspect data by project/location/SKU. Do not assume an empty repository and one holding thousands of snapshots cost the same.

### 16.2. Cleanup Policies

For repositories accumulating many versions, organizations can use **cleanup policies** (conditional delete, keep most recent, etc.):

1. Inventory versions currently used by consumers or deployments.
2. Define separate retention rules for snapshots and releases.
3. Run **dry run** to preview impact before deleting.
4. Keep versions needed for rollback and auditing.
5. Account for remote caches and consumers pinned to older versions.
6. Review results after policies run and alert on unexpected repository growth.

**Deleting a Maven package/version can be irreversible.** Never automatically delete all artifacts older than 7 days in a repository holding production releases.

### 16.3. Cleaning Up Lab Resources

If you created `java-libs-lab` yourself and verified no other consumers exist, the deletion command (mutating, causes data loss) is:

~~~bash
gcloud artifacts repositories delete java-libs-lab \
  --project=PROJECT_ID \
  --location=asia-southeast1
~~~

Do not run this command if the repository is shared or contains packages that must be kept. Afterward, verify via list/read commands and check storage/CI/network charges as well as any IAM or build artifacts created.

## 17. Troubleshooting Common Errors

| Symptom | Possible cause | How to check |
|---|---|---|
| `401 Unauthorized` | Missing/expired token, helper not working | ADC, wagon/plugin, refresh credentials |
| `403 Permission Denied` | Valid identity but lacks Reader/Writer | Repository IAM, actual principal |
| `404 Not Found` | Wrong project/location/repo/GAV or visibility | `repositories describe`, `packages/versions list` |
| `mvn deploy` reports missing repository | Only `<repositories>` configured, missing `distributionManagement` | Set proper repository/snapshotRepository |
| `Unsupported transport protocol artifactregistry` | Maven wagon not loaded | `build extensions` or core extension |
| `Non-resolvable parent POM` | Parent must resolve before POM extensions load | `.mvn/extensions.xml` |
| Snapshot publish rejected | Release version policy | Use the proper snapshot repo |
| Release publish rejected | Snapshot version policy | Use the proper release repo |
| Gradle publish skips JAR/POM | Missing Maven publication | Check `publishing.publications` |
| Dev builds succeed, CI fails | Different credentials/caches | Inspect CI service account and clean build |
| App misses new version | Maven local cache/update policy | `mvn -U`, version, and metadata |
| Dependencies download straight from Maven Central | Remote/virtual config hasn't overridden `central` | Configure `central` and `pluginRepositories` |
| CI cannot reach endpoint | Restricted DNS/TLS/proxy/egress | Verify HTTPS network and cert trust |
| Package landed in unexpected repository | Wrong POM URL or default project | Inspect `distributionManagement`/CLI flags |
| Cleanup removed old release | Retention too short, consumers unchecked | Dry run and rollback plan |
| Maven repo rejects Docker image | One format per repository | Create a separate Docker repo |

### 17.1. Procedure for Investigating a `403` Error

1. Determine whether the request is a **publish** or **download**.
2. Record the actual project, location, repository, and GAV.
3. Identify the exact identity Maven/Gradle uses via ADC/CI service account—never infer from Git username.
4. Check IAM on the **repository** and inherited permissions: Writer to publish, Reader to consume.
5. Check the wagon/Gradle plugin, credentials, and network setup.
6. Cross-check version policy, package metadata, and detailed error messages.
7. Retry in a sandbox; fix only the missing permission instead of granting broad `Owner` or `Artifact Registry Admin`.

### 17.2. How Auth Errors Differ from Network Errors

- **Timeout/DNS/TLS handshake:** investigate connectivity, proxies, CA certificates, networking/egress.
- **401/403:** typically occurs once the endpoint received the request but authentication/policy rejected it.
- **404:** re-verify resource names, GAV, URL, and visibility; do not assume the package does not exist.
- **Conflict/version validation:** inspect snapshot/release policy or already-published versions.

**Never paste JSON keys, bearer tokens, `settings.xml` containing passwords, or CI secrets into public support tickets.**

## 18. Case Study: RetailOne Managing Shared Java Libraries

**Context:** `RetailOne` has an internal library `com.retailone.platform:order-common` used by two services:

- `orders-api` running on Cloud Run.
- `billing-worker` running on Compute Engine.
- Build pipelines located in a separate CI project.
- Artifacts stored in project `retail-build-prod`.
- Production must use release versions, supporting rollback and auditing.

### 18.1. Proposed Design

~~~mermaid
flowchart TD
    Source["Git: order-common"]
    Build["CI verify, SCA, versioning"]
    Snap["Maven standard: snapshot"]
    Release["Maven standard: release"]
    Virtual["Virtual: java-dependencies"]
    Remote["Remote: Maven Central"]
    C1["orders-api build"]
    C2["billing-worker build"]
    Container["Docker repository"]
    CloudRun["Cloud Run"]
    VM["Compute Engine"]
    Source --> Build
    Build --> Snap
    Build --> Release
    Release --> Virtual
    Remote --> Virtual
    Virtual --> C1
    Virtual --> C2
    C1 --> Container
    Container --> CloudRun
    C2 --> VM
~~~

Rules:

1. Snapshots are used for integration and testing.
2. Releases are published only by a CI SA with Writer on the release repository.
3. Consumers hold only Reader on the required standard/virtual repositories.
4. CI records GAV, source commit, checksum, dependency graph, and test results.
5. `orders-api` builds a container image and pushes it to a separate Docker repository.
6. The Cloud Run runtime does not need Writer on Maven repos; Compute Engine does not need the publisher's private keys.
7. Clean up snapshots per expiry; retain release versions actively deployed or needed for rollback.

### 18.2. Incident: Breaking Library Interface Change

Suppose `order-common:1.1.0` removes a public method used by Billing Worker. If the team republishes under GAV `1.0.0`, some builds keep the stale cache while others pick up new code; CI becomes irreproducible. The right approach is to **publish a new version**, document breaking changes, and run compatibility tests for both consumers.

### 18.3. Evidence for a Valid Release

| Question | What to verify |
|---|---|
| Which source commit? | SHA/tag and build provenance |
| Did tests pass? | CI report |
| Does the artifact match GAV? | POM + repository version |
| Who holds Writer permissions? | Repo IAM policy |
| Did consumers pull the right release? | Maven dependency tree and build logs |
| Was the right image deployed? | Docker digest + revision |
| Can we roll back? | Old version retained, restore/redeploy tested |
| Are costs reasonable? | Billing + cleanup dry run |

## 19. Hands-on Exercises and Self-Assessment

### Exercise 1 — Placing the Right Artifact

You have two outputs: `order-common-1.0.0.jar` (a Java library) and OCI image `orders-api:1.0.0` (for running on Cloud Run). **Which repository formats should store them?** Explain why both cannot go into the same repo.

### Exercise 2 — Maven GAV

A project has:

~~~xml
<groupId>com.example.payments</groupId>
<artifactId>risk-sdk</artifactId>
<version>2.3.1</version>
<packaging>jar</packaging>
~~~

**Write out** the GAV, an example `<dependency>` block a consumer needs, and the standard Maven layout path of the JAR.

### Exercise 3 — Snapshot Rejected

A developer publishes `1.4.0-SNAPSHOT` to a `Release` repository and gets an error. Why? Should they strip the `-SNAPSHOT` suffix just to bypass the error without testing/approval?

### Exercise 4 — CI Gets `403`

A developer can upload from their laptop, while the Cloud Build publisher gets 403. Identify the **actual CI service account**, ADC, Writer permission, and which repository scope to inspect. Why shouldn't a JSON key be put in `pom.xml`?

### Exercise 5 — Parent POM in a Private Maven Repo

A consumer uses `<parent>` pointing to `com.example.platform:company-parent:3.0.0`; the wagon is in `<build><extensions>`, yet Maven fails reading the parent. What is missing? Why does `.mvn/extensions.xml` help?

### Exercise 6 — Single Endpoint for Internal + Public Dependencies

An enterprise wants CI to reach Maven Central via cache and internal libraries through one endpoint. Draw **standard + remote + virtual**, describe upstream priority, and explain dependency confusion risks.

### Exercise 7 — Cleanup Without Breaking Rollbacks

A repository has thousands of snapshots and the team plans to delete all artifacts older than 7 days. Which release versions might need to be kept? Draft a cleanup policy with **dry run** and consumer checks.

### Exercise 8 — Investigating a Missing Package in Consumer Builds

A team published `com.example.platform:order-common:1.0.0`, yet a new CI run reports a missing dependency. List the verification sequence: **GAV → project/location/repo → package/versions → Reader IAM → repositories → wagon/core extension → Maven cache → network**.

### Exercise 9 — Supply Chain Control

A virtual repository returns a public package matching the GAV of an internal library. Point out the risk and propose changes to namespace, upstream priority, permissions, and release provenance.

## 20. Operational Checklist

- [ ] Distinguished Maven packages from OCI images and chose the right repository format.
- [ ] Selected appropriate location, mode, version policy, IAM owner, and naming convention.
- [ ] Defined valid GAV/packaging/POM and versioning strategy.
- [ ] Granted **Reader** to consumers, **Writer** to CI publisher, Admin/RepoAdmin only where needed.
- [ ] Verified the ADC/service account used by Maven/Gradle.
- [ ] No service account JSON keys/tokens stored in source code, images, or build logs.
- [ ] Publisher has proper `distributionManagement`; consumers have proper `repositories`.
- [ ] Maven wagon or Gradle helper loaded; core extension present if resolving parents/plugins.
- [ ] Ran `mvn verify` or `gradle test` before publishing.
- [ ] Confirmed packages/versions using `gcloud artifacts packages/versions list`.
- [ ] An independent consumer can download the exact version and build cleanly.
- [ ] Separated snapshots/releases and never reused release versions for new content.
- [ ] Controlled remote/virtual upstream priorities if proxying dependencies.
- [ ] Recorded commit SHA, build ID, checksum, and test results for auditing/rollback.
- [ ] Implemented dependency scanning/SBOMs and do not treat the registry as the sole security control.
- [ ] Dry-ran cleanup policies and protected versions needed for rollback/auditing.
- [ ] Monitored access, storage growth, IAM changes, and costs.
- [ ] For Cloud Run/GKE deployments, pipeline builds an OCI image and pushes to a separate Docker repository.

## 21. Official Reference Documentation

Plugin versions, authentication methods, and repository features may change over time. Before deploying to production, verify:

- [Artifact Registry — Get started with Java packages](https://docs.cloud.google.com/artifact-registry/docs/java)
- [Quickstart: Store Java packages](https://docs.cloud.google.com/artifact-registry/docs/java/store-java)
- [Configure authentication for Maven and Gradle](https://docs.cloud.google.com/artifact-registry/docs/java/authentication)
- [Manage Java packages](https://docs.cloud.google.com/artifact-registry/docs/java/manage-packages)
- [Create standard repositories](https://docs.cloud.google.com/artifact-registry/docs/repositories/create-repos)
- [Remote repository overview](https://docs.cloud.google.com/artifact-registry/docs/repositories/remote-overview)
- [Virtual repositories](https://docs.cloud.google.com/artifact-registry/docs/repositories/virtual-repo)
- [Artifact Registry access control](https://docs.cloud.google.com/artifact-registry/docs/access-control)
- [Repository cleanup policies](https://docs.cloud.google.com/artifact-registry/docs/repositories/cleanup-policy)
- [Integrate Cloud Build](https://docs.cloud.google.com/artifact-registry/docs/configure-cloud-build)
- [Maven POM reference](https://maven.apache.org/pom.html)
- [Maven settings reference](https://maven.apache.org/settings.html)
- [Gradle Maven Publish plugin](https://docs.gradle.org/current/userguide/publishing_maven.html)
- [Artifact Registry pricing](https://cloud.google.com/artifact-registry/pricing)

**Key takeaway:** Storing Maven artifacts in Artifact Registry gives Java projects **versioned, permission-controlled, and auditable shared libraries**. Start with a standard Maven repository, configure **publish and dependency paths** properly, use **credential helpers + least-privilege IAM**, and verify with an independent consumer. At scale, separate snapshots/releases, govern remote/virtual upstreams, record build provenance, and control cleanup and costs. For applications running on Cloud Run/GKE, the Maven artifact is a **build input**, while the **OCI image** must be stored in a separate Docker repository.
