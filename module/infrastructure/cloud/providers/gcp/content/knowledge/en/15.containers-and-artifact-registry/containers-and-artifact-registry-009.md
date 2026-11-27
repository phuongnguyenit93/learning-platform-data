# Optimizing Java Images with Multi-Stage Builds and Buildpacks

A team deploying Java services to Google Kubernetes Engine (GKE) or Cloud Run often starts by asking, "How should I package a JAR into a Docker image?" If you include the entire JDK, Maven/Gradle, source code, build caches, and debugging tools inside the production image, the image carries many components **unnecessary at runtime**, slows down pushes/pulls, and expands the security maintenance surface.

Two main approaches address this:

- **Docker multi-stage builds:** compile in an image containing the JDK and build tools, then **copy only the artifact** into a smaller runtime image.
- **Cloud Native Buildpacks (CNB):** detect Java/Maven/Gradle and construct an OCI image with appropriate runtime layers **without requiring a Dockerfile**.

This lesson belongs to the **Containers and Artifact Registry** chapter in the `CLOUD_PROVIDERS_GCP` module. Combining organization/project setup, IAM, VPC, Compute Engine, GKE, Cloud Run, storage services, and databases, image packaging techniques must align with **resource protection, release automation, reliability, supply chain security, and cost**.

Examples assume a **Java 21, Spring Boot, Maven** application producing `target/orders-api-1.0.0.jar`. Filenames, projects, repositories, image tags, and environment properties are illustrative only; never run resource-mutating commands in a production project without approval.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish build images, runtime images, image layers, tags, and digests.
2. Write a **multi-stage** Dockerfile for a Java 21 application with a non-root runtime.
3. Optimize the build context with `.dockerignore`, dependency caching, and BuildKit.
4. Choose a JRE/distroless or specialized runtime based on real workload requirements.
5. Explain Cloud Native Buildpacks and the detect–build–export lifecycle.
6. Use `pack` or `gcloud builds submit --pack` to build Java images.
7. Store images in Artifact Registry, verify digests, and deploy to Cloud Run/GKE.
8. Protect pipelines with least-privilege IAM, secrets management, and vulnerability scanning.
9. Measure image size, build/pull speed, startup time, memory usage, and cost.
10. Choose between Buildpacks and multi-stage builds based on team and workload constraints.

## 1. Source Code, Executable JAR, and Container Runtime

A simple Java Maven project has the structure:

~~~text
orders-api/
├── pom.xml
├── src/
│   ├── main/java/...
│   └── test/java/...
├── Dockerfile
├── .dockerignore
└── project.toml       # Needed only when using buildpacks and custom configuration
~~~

To build a Spring Boot executable JAR, Maven requires a JDK and the dependencies/plugins defined in `pom.xml`. Once running the JAR, however, the container typically **needs neither a compiler, nor Maven, nor source code**.

~~~mermaid
flowchart LR
    SRC["Source + pom.xml"] --> B["Build stage: Maven + JDK"]
    B --> J["Executable JAR"]
    J --> R["Runtime stage: Java runtime"]
    R --> OCI["OCI image"]
    OCI --> AR["Artifact Registry"]
    AR --> DEP["Cloud Run / GKE / VM"]
~~~

| Component | At build time | At runtime |
| --- | --- | --- |
| **JDK** | Compiles and tests Java | Usually no compiler/tooling needed |
| **Maven/Gradle** | Downloads dependencies and packages artifacts | Not needed |
| **JRE/Java runtime** | Included in the JDK | Needed to execute bytecode |
| **Source/test files** | Needed for build/test | Usually not needed |
| **Build cache `~/.m2`/`~/.gradle`** | Saves build time | Not needed |
| **Executable JAR** | Build output | Needed |
| **CA certs/native libraries** | Depends on build | Needed if app uses TLS/JNI/fonts/timezones |

**Note:** not every `*.jar` can be executed with `java -jar`. For example, the Spring Boot plugin is required to produce an **executable/fat JAR**; a plain library JAR may lack a main manifest attribute or bundled dependencies.

## 2. Image Layers, Tags, and Digests

A container image consists of filesystem layers and metadata. `COPY`/`RUN` instructions in a Dockerfile create layers that can be reused when inputs do not change.

- **Tags** such as `orders-api:v1.2.0` are human-readable names that **can be reassigned**.
- **Digests** such as `orders-api@sha256:<FULL_DIGEST>` identify image manifest contents and are suited for deploying verified artifacts.
- **Layer caching** avoids rebuilding or re-downloading unchanged layers.
- **Image manifests/indexes** describe the image and can span multiple CPU architectures; an index digest differs from each platform-specific manifest digest.

~~~mermaid
flowchart TD
    A["Application JAR layer"] --> B["Java runtime layer"]
    B --> C["OS base / CA libs"]
    C --> D["Image manifest"]
    D --> E["Digest sha256:..."]
~~~

**"Image size" is not a single metric.** Local size from `docker inspect` differs from the compressed payload transferred during push/pull; registries and nodes can also reuse shared layers. Cloud Run startup depends on Java class loading, frameworks, memory, CPU, and application initialization—not image size alone.

## 3. Anti-Pattern: Single-Stage Image Containing All of Maven

~~~dockerfile
FROM maven:3.9-eclipse-temurin-21
WORKDIR /workspace
COPY . .
RUN mvn -B -ntp -DskipTests package
EXPOSE 8080
CMD ["java", "-jar", "target/orders-api-1.0.0.jar"]
~~~

This Dockerfile works if the JAR name matches, yet production must carry Maven, the JDK, source code, build outputs, and extraneous files. `COPY . .` can also leak `.git`, `.env`, logs, or private keys into the image if the build context is unfiltered.

**This does not mean using a JDK image is always unsafe**; some workloads need JDK tooling or JNI. The point is to deliberately decide what the runtime actually requires rather than running the build image in production by default.

## 4. Docker Multi-Stage Build with Maven and Java 21

Complete Dockerfile example:

~~~dockerfile
# syntax=docker/dockerfile:1

# Stage 1: compile/package
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /workspace

# Copy descriptor before source so dependencies can be cached.
COPY pom.xml ./
RUN --mount=type=cache,target=/root/.m2 \
    mvn -B -ntp dependency:go-offline

COPY src ./src
RUN --mount=type=cache,target=/root/.m2 \
    mvn -B -ntp -DskipTests package

# Stage 2: minimal runtime without Maven or source code.
FROM gcr.io/distroless/java21-debian13:nonroot AS runtime
WORKDIR /app
COPY --from=build /workspace/target/orders-api-1.0.0.jar /app/app.jar
EXPOSE 8080
# Distroless Java has an entrypoint equivalent to "java -jar".
CMD ["/app/app.jar"]
~~~

**Precondition:** this example assumes `target/orders-api-1.0.0.jar` is the actual executable JAR. If your project uses a different version/artifact name, adjust the copy path to match build output; avoid sloppy wildcards when multiple JARs exist (`-sources.jar`, `-javadoc.jar`, or plain/original JARs).

### 4.1. Breaking Down Each Part

| Instruction | Purpose |
| --- | --- |
| `FROM maven:... AS build` | Keeps JDK/Maven strictly in the build stage |
| `COPY pom.xml` before source | When code changes without dependency changes, resolution cache can be reused |
| `--mount=type=cache,target=/root/.m2` | Keeps Maven downloads in builder cache instead of the runtime image |
| `mvn ... package` | Packages the JAR; tests should run separately in CI |
| `FROM gcr.io/distroless/java21-debian13:nonroot` | Minimal Java 21 runtime with a non-root user |
| `COPY --from=build` | Copies only the runnable artifact |
| `CMD ["/app/app.jar"]` | Passes the JAR to the distroless Java default entrypoint |

**Important:** `gcr.io/distroless/java21-debian13` is configured with an entrypoint equivalent to **`java -jar`**, so `CMD ["/app/app.jar"]` is valid. If you switch to `eclipse-temurin:21-jre`, you need `ENTRYPOINT ["java","-jar","/app/app.jar"]`; do not copy `CMD` verbatim across different base images.

### 4.2. Non-Root Runtime and Writable Paths

The `:nonroot` image runs the process as a non-root user. The JAR needs appropriate read permissions; temporary files must go to an allowed directory, typically `/tmp` or a runtime-mounted volume. Never embed secrets in the JAR and never use the container filesystem for long-lived business data.

### 4.3. `EXPOSE` Does Not Create an HTTP Endpoint

`EXPOSE 8080` is metadata only; it **does not open firewalls** or force Java to listen on that port. Cloud Run enforces a `PORT` runtime contract; configure the app to listen on `0.0.0.0` and the corresponding port.

### 4.4. Why Are Tests Skipped in the Dockerfile?

`-DskipTests` in the example separates packaging from testing—it is **not a recommendation to skip testing**. CI must enforce a gate such as:

~~~bash
mvn -B -ntp verify
docker build -t orders-api:multi-local .
docker run --rm -p 8080:8080 orders-api:multi-local
~~~

If the build stage relies on generated code or profiles where `verify` and `package` behave differently, align Maven profiles, environments, and dependencies.

## 5. Shrinking the Docker Build Context with `.dockerignore`

~~~dockerignore
.git
.github
.idea
.vscode
*.log
.env
.env.*
*.pem
*.key
target/
build/
.gradle/
node_modules/
tmp/
.DS_Store
~~~

Benefits:

1. Avoids sending unnecessary build/test files to the builder.
2. Reduces churn in the build context that invalidates caches.
3. Lowers the risk of accidentally copying secrets, logs, and Git history into image layers.

**Never rely solely on `.dockerignore` to protect secrets.** Files exposed in Git or CI logs remain a risk. If using Maven Wrapper, keep `mvnw` and `.mvn/` as needed; the Section 4 example uses Maven preinstalled in the builder image.

## 6. Docker/BuildKit Caching Cuts Time, Not Necessarily Image Size

There are two caching layers:

- **Docker layer cache**: reuses `COPY pom.xml` and dependency resolution steps when inputs stay unchanged.
- **BuildKit cache mount**: e.g., `/root/.m2`, retaining downloaded Maven artifacts across builds in compatible builder environments.

~~~mermaid
flowchart TD
    P["pom.xml"] --> D["Resolve dependencies"]
    D --> S["COPY src"]
    S --> C["Package JAR"]
    C --> OUT["Runtime image"]
    CACHE["BuildKit cache mount ~/.m2"] -.-> D
    CACHE -.-> C
~~~

`mvn dependency:go-offline` warms the cache but does not guarantee every dynamic plugin/dependency in every project is fetched; `package` may still contact repositories. Pin plugin/dependency versions and govern repository mirrors.

**CI note:** a cache mount on an ephemeral worker is not automatically shared between two Cloud Build jobs. For cross-build caching, configure supported remote caching/builder strategies while weighing security and cache storage costs.

To benchmark fairly, measure separately:

- **Cold build:** builder starts with empty layer and dependency caches.
- **Warm build:** only one source file changes, allowing cache reuse.

Never compare a cold multi-stage build against a warm Buildpacks build and claim one tool is faster.

## 7. Using Gradle Instead of Maven

The principle remains **JDK/Gradle in the build stage; only Java and the JAR in runtime**. Example for Gradle Groovy DSL with wrapper:

~~~dockerfile
# syntax=docker/dockerfile:1
FROM eclipse-temurin:21-jdk AS build
WORKDIR /workspace

COPY gradlew settings.gradle build.gradle ./
COPY gradle ./gradle
RUN chmod +x ./gradlew
RUN --mount=type=cache,target=/root/.gradle \
    ./gradlew --no-daemon dependencies

COPY src ./src
RUN --mount=type=cache,target=/root/.gradle \
    ./gradlew --no-daemon bootJar

FROM gcr.io/distroless/java21-debian13:nonroot
WORKDIR /app
COPY --from=build /workspace/build/libs/orders-api-0.0.1-SNAPSHOT.jar /app/app.jar
EXPOSE 8080
CMD ["/app/app.jar"]
~~~

Kotlin DSL projects use `settings.gradle.kts`/`build.gradle.kts`; multi-module projects must copy multiple descriptors/sources and match the output path. Do not assume every Gradle project has a `bootJar` task—that comes from applying the Spring Boot plugin.

## 8. Choosing a Runtime: JDK, JRE, Distroless, and `jlink`

| Option | Strengths | Considerations |
| --- | --- | --- |
| JDK image | Includes compiler and diagnostic tools; easy debugging | Many components unneeded at runtime |
| JRE image | Contains Java runtime; usually fewer components than JDK | Size and OS packages vary by base |
| Distroless Java | No shell or package manager, nonroot variant, minimal OS surface | Harder to debug; verify JNI, fonts, TLS, timezones |
| `jlink` custom runtime | Includes only needed Java modules | Reflection/JNI/dynamic loading can cause missing modules |
| Native image | Can improve startup/memory for suitable workloads | Build workflow and compatibility differ from standard JVM |

Distroless images **have no default shell**; avoid:

~~~dockerfile
FROM gcr.io/distroless/java21-debian13:nonroot
COPY app.jar /app/app.jar
CMD ["sh", "-c", "java -jar /app/app.jar"]
~~~

This fails because `/bin/sh` does not exist. Use the JSON/exec form of `CMD/ENTRYPOINT` and inspect the base image's built-in entrypoint. When debugging is required, use a debug image or out-of-container observability tools per environment policy.

**A small image does not guarantee zero CVEs**: Java dependencies inside the JAR still need patching, and distroless base images still need updates.

## 9. Layered Executable JARs for Spring Boot

A fat JAR bundles dependencies and application code in one file. With a single `COPY app.jar`, changing one Java class rebuilds the entire JAR layer.

Spring Boot supports **layered JARs**: separating infrequently changing parts (dependencies, loader) from application classes/resources. An advanced optimization flow:

1. Configure the Spring Boot Maven/Gradle plugin to produce a layered JAR.
2. Extract layers using the mechanism supported by your Spring Boot version.
3. `COPY` dependency layers first and application classes last.
4. Measure layer reuse and push/pull speed when only one class changes.

`-Djarmode=...` flags and layer extraction syntax vary across framework versions; never copy old extraction commands without checking documentation for your plugin version.

**Buildpacks** automatically optimize layers for Java/Spring Boot on supported builders, making them worth evaluating before maintaining a complex custom layered-JAR Dockerfile.

## 10. What Are Cloud Native Buildpacks (CNB)?

**Cloud Native Buildpacks** use a builder image containing buildpacks to detect and build applications into OCI-compliant container images.

~~~mermaid
flowchart LR
    S["Java source + pom.xml/Gradle"] --> DET["Detect"]
    DET --> BUILD["Build"]
    BUILD --> EXPORT["Export image layers"]
    EXPORT --> IMG["OCI image"]
    BUILDER["Builder: buildpacks + run image"] -.-> DET
    BUILDER -.-> BUILD
~~~

| Component | Function |
| --- | --- |
| **Buildpack** | Detects and handles part of the build/runtime setup |
| **Builder image** | Bundles buildpacks, detection order, and build/run images |
| **Lifecycle** | Orchestrates detect, analyze/restore, build, and export |
| **Build image** | Ephemeral compilation environment |
| **Run image** | Runtime base of the final image |
| **`pack` CLI** | Runs CNB against a compatible Docker engine/CI |
| **`project.toml`** | Defines build-time environment and project config |
| **Rebase** | Swaps run image layers when compatible without rebuilding app layers |

Buildpacks **do not eliminate dependency management**. You still govern the JDK version, Maven/Gradle dependencies, builder/run image versions, and security updates.

### 10.1. Rebase Has Limits

`pack rebase` can replace run-image layers under compatibility conditions. It **does not patch CVEs inside JAR dependencies**, does not alter Java business logic, and is not guaranteed to work for every image. After rebasing, re-test, re-scan, and deploy the new digest.

### 10.2. How Do Buildpacks Differ from Dockerfiles?

Multi-stage builds let you control every `FROM/COPY/RUN/CMD`. Buildpacks delegate many steps to the builder/buildpacks, trading explicit control for standardization—though you still must pin and review builders. Both produce OCI images deployable to Artifact Registry, Cloud Run, or GKE.

## 11. Google Cloud Buildpacks for Java 21

Google Cloud Buildpacks support Java projects using Maven or Gradle. You can select the JDK using the build-time variable `GOOGLE_RUNTIME_VERSION`.

### 11.1. `project.toml`

Create `project.toml` at the application root:

~~~toml
[[build.env]]
name = "GOOGLE_RUNTIME_VERSION"
value = "21"
~~~

This is **build configuration**, not Cloud Run's runtime `PORT`. Never place secrets or database passwords inside `project.toml`.

### 11.2. Local Build with `pack`

Requires a Docker engine/daemon, `pack` CLI, and valid Maven/Gradle source:

~~~bash
pack build orders-api:pack-local \
  --builder=gcr.io/buildpacks/builder:google-24 \
  --env GOOGLE_RUNTIME_VERSION=21
~~~

`gcr.io/buildpacks/builder:google-24` is an example Google Cloud builder; before production, verify the supported builder, runtime, and versions, and manage digests/updates. For the default builder, you can specify `--builder=gcr.io/buildpacks/builder`.

### 11.3. Test and Inspect Locally

~~~bash
docker image inspect orders-api:pack-local \
  --format '{{.Size}}'

docker run --rm -p 8080:8080 orders-api:pack-local

# Another terminal, if Spring Boot Actuator is enabled:
curl -i http://localhost:8080/actuator/health
~~~

If the app uses `/healthz` instead of Actuator, change the test endpoint. Inspect HTTP responses, startup logs, TLS/JDBC certificates, and memory usage.

### 11.4. When Are Buildpacks a Good Fit?

- Standard Spring Boot/Maven/Gradle build pipelines.
- Multiple teams wanting standardized image builds without maintaining dozens of Dockerfiles.
- Wanting built-in layering/rebase and build metadata from supported builders.
- Teams using Cloud Run source deployments as a streamlined release flow.

Limitations: you must understand detection logic, builder support, native OS dependencies, and entrypoints. Generated images are **not automatically the smallest or safest**; measure and scan them.

## 12. Remote Cloud Build: Buildpacks vs. Dockerfile

Cloud Build can package Java source using buildpacks and push to Artifact Registry. Example (target repository must already exist):

~~~bash
gcloud builds submit . \
  --pack image=asia-southeast1-docker.pkg.dev/PROJECT_ID/java-images/orders-api:pack-v1 \
  --project=PROJECT_ID
~~~

Cloud Build defaults to `gcr.io/buildpacks/builder` if no builder is specified. To choose explicitly:

~~~bash
gcloud builds submit . \
  --pack builder=gcr.io/buildpacks/builder:google-24,image=asia-southeast1-docker.pkg.dev/PROJECT_ID/java-images/orders-api:pack-v1 \
  --project=PROJECT_ID
~~~

The multi-stage Dockerfile alternative:

~~~bash
gcloud builds submit . \
  --tag=asia-southeast1-docker.pkg.dev/PROJECT_ID/java-images/orders-api:multi-v1 \
  --project=PROJECT_ID
~~~

| Command | Build instruction source | Output |
| --- | --- | --- |
| `gcloud builds submit --pack ...` | Buildpacks/builder/source descriptors | OCI image pushed to Artifact Registry |
| `gcloud builds submit --tag ...` | Dockerfile in the build context | OCI image pushed to Artifact Registry |
| `gcloud run deploy --source=.` | Buildpacks via Cloud Build per Cloud Run features | Builds from source and deploys service |
| `gcloud run deploy --image=...` | Already built/pushed image | Deploys image by specified tag/digest |

Every real build/push/deploy operation can incur **Cloud Build, registry storage, network, and runtime charges**. Build identity and repository IAM permissions must be prepared properly; never run in an unauthorized project.

### 12.1. Do Not Confuse Local Build Cache with Cloud Build

Cloud Build runs on its own worker/CI environment; local Docker/BuildKit caches are not automatically shared across runs. Buildpacks have their own caching/lifecycle depending on how Cloud Build invokes the builder. When benchmarking build times, measure in the actual target environment and design caching accordingly.

## 13. Artifact Registry: Storing and Distributing Java Images

**Artifact Registry** stores images by project, location, repository, and IAM. Cloud Run/GKE pull images via authorized identities.

### 13.1. Create a Docker Repository

Run only in an authorized lab project with appropriate billing where the repository does not already exist:

~~~bash
gcloud services enable artifactregistry.googleapis.com \
  --project=PROJECT_ID

gcloud artifacts repositories create java-images \
  --repository-format=docker \
  --location=asia-southeast1 \
  --description="Java application images" \
  --project=PROJECT_ID

gcloud artifacts repositories describe java-images \
  --location=asia-southeast1 \
  --project=PROJECT_ID
~~~

Image address:

~~~text
asia-southeast1-docker.pkg.dev/PROJECT_ID/java-images/orders-api:multi-v1
| LOCATION             | PROJECT  | REPO      | IMAGE:TAG
~~~

### 13.2. Build/Push with Local Docker

~~~bash
gcloud auth configure-docker asia-southeast1-docker.pkg.dev

docker build -t orders-api:multi-local .

docker tag orders-api:multi-local \
  asia-southeast1-docker.pkg.dev/PROJECT_ID/java-images/orders-api:multi-v1

docker push \
  asia-southeast1-docker.pkg.dev/PROJECT_ID/java-images/orders-api:multi-v1
~~~

`gcloud auth configure-docker` only configures the credential helper; **it does not grant IAM permissions**. The pushing identity needs a role such as `roles/artifactregistry.writer` on the target repository.

### 13.3. Record the Digest After Pushing

~~~bash
gcloud artifacts docker images list \
  asia-southeast1-docker.pkg.dev/PROJECT_ID/java-images/orders-api \
  --include-tags \
  --project=PROJECT_ID
~~~

An image can be deployed by digest:

~~~text
asia-southeast1-docker.pkg.dev/PROJECT_ID/java-images/orders-api@sha256:FULL_DIGEST
~~~

`FULL_DIGEST` must be replaced with the real digest. `:latest` or `:multi-v1` are **reassignable tags**, not immutable artifact identifiers. For multi-platform OCI images, distinguish the image index digest from per-architecture manifest digests.

### 13.4. Role-Based Permissions

| Identity | Permissions to consider | Rationale |
| --- | --- | --- |
| Cloud Build service account | Artifact Registry Writer on repo | Push images |
| Cloud Run service agent / GKE node pull identity | Artifact Registry Reader where needed | Pull images |
| CI/CD deployer | Revision/deploy creation rights and `iam.serviceAccounts.actAs` for runtime SA | Release |
| Runtime service account | Business IAM such as Secret Manager, Storage, Pub/Sub | Run app; does not need Writer |
| Auditor | Read image metadata and vulnerability findings | Security review |

The **image-pulling identity** may differ from the identity running the **Java application**. Exact bindings depend on same-project vs. cross-project setups and Cloud Run/GKE architecture.

## 14. Deploying the Java Image to Cloud Run

With a tested digest and valid repository:

~~~bash
gcloud run deploy orders-api \
  --image=asia-southeast1-docker.pkg.dev/PROJECT_ID/java-images/orders-api@sha256:FULL_DIGEST \
  --region=asia-southeast1 \
  --service-account=orders-runtime@PROJECT_ID.iam.gserviceaccount.com \
  --no-allow-unauthenticated \
  --port=8080 \
  --project=PROJECT_ID
~~~

**Mutating command**: creates or updates a Cloud Run service, requires IAM, and may incur charges. The hypothetical service account `orders-runtime` must exist, be authorized for use by the deployer, and hold least-privilege runtime permissions.

### 14.1. Cloud Run Injects `PORT`

Cloud Run injects the `PORT` environment variable and requires ingress containers to listen on `0.0.0.0` at that port. Spring Boot example:

~~~properties
server.address=0.0.0.0
server.port=${PORT:8080}
management.endpoint.health.probes.enabled=true
~~~

`EXPOSE 8080` is image metadata and **does not force the application to listen**. If the app binds `127.0.0.1` or ignores `PORT`, the revision can fail startup and reject requests.

### 14.2. Deploying Directly from Source with Buildpacks

~~~bash
gcloud run deploy orders-api \
  --source=. \
  --region=asia-southeast1 \
  --no-allow-unauthenticated \
  --project=PROJECT_ID
~~~

Cloud Run source deployment uses **Google Cloud Buildpacks/Cloud Build** by default and deploys the resulting image. While convenient, it triggers a **fresh build**. When an enterprise requires promoting the **exact same digest** from staging to production, building once and deploying by digest is easier to audit.

## 15. Deploying the Image to GKE

Kubernetes Deployment referencing an Artifact Registry image:

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
          image: asia-southeast1-docker.pkg.dev/PROJECT_ID/java-images/orders-api@sha256:FULL_DIGEST
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            initialDelaySeconds: 10
            periodSeconds: 5
          resources:
            requests:
              cpu: "250m"
              memory: "512Mi"
            limits:
              memory: "1Gi"
~~~

This example assumes Spring Boot Actuator exposes the matching readiness endpoint. If the readiness URL returns 404, Pods will not receive traffic even though the JVM is running. You also need a Kubernetes Service, namespace, IAM/image pull permissions, networking, network policies, and cluster deployment controls.

**Java memory:** heap is only part of process memory; metaspace, thread stacks, and native memory also consume RAM. Setting `-Xmx` right up against a `1Gi` limit can trigger `OOMKilled`.

## 16. Multi-Stage vs. Buildpacks: When to Use Which?

| Criterion | Docker multi-stage | Buildpacks |
| --- | --- | --- |
| Dockerfile required | Yes | Usually no |
| OS/runtime control | Very granular | Driven by builder/run image |
| Custom native/JNI libraries | Easy to add specific packages | May require a custom builder |
| Standard Java/Spring Boot | Must maintain Dockerfile | Easy to get started |
| Caching | Layers, BuildKit, remote cache | CNB lifecycle/cache |
| Layered JAR | Configured manually when needed | Builder may handle layering |
| Rebase run image | Typically requires rebuild/other tools | Can rebase if compatible |
| Pin/rebuild/update base | Team manages directly | Team must track builder/run image updates |
| Runtime debugging | Depends on base; distroless harder | Depends on run image |
| OCI deployment | Cloud Run/GKE/VM | Cloud Run/GKE/VM |
| Image size | Can be small, not guaranteed smallest | Can be efficient, not guaranteed |

**Choose Buildpacks** for standard Java/Maven/Gradle apps when you want standardized CI/CD and less Dockerfile maintenance. **Choose multi-stage** when you need explicit control over native packages, distroless, runtime flags, and image composition. Both still require scanning, testing, dependency pinning, and monitoring.

## 17. Reproducibility and Supply Chain Security

### 17.1. Pin Versions and Update Under Control

Tags like `maven:3.9-eclipse-temurin-21`, `gcr.io/distroless/java21-debian13:nonroot`, and `gcr.io/buildpacks/builder:google-24` update over time. In production:

1. Record Git commit SHA, builder version/digest, Java version, dependency lockfiles, and image digest.
2. Pin builder/base images by **digest** per approved release policy.
3. Pin Maven/Gradle plugin and dependency versions, avoiding dynamic versions where reproducibility matters.
4. Govern Maven repository mirrors, signatures, and checksums per supply chain rules.
5. **Update base images/JDKs periodically.** Pinning a digest forever without patching also creates risk.

### 17.2. Never Pass Secrets via Docker Build Args

Bad example:

~~~dockerfile
ARG MAVEN_PASSWORD
RUN echo "$MAVEN_PASSWORD" > /root/.m2/settings.xml
~~~

Secrets can leak in build history, caches, or logs. For private Maven repositories, use BuildKit secrets or CI-supported secret injection:

~~~dockerfile
RUN --mount=type=secret,id=maven_settings,target=/root/.m2/settings.xml \
    mvn -B -ntp -DskipTests package
~~~

This Dockerfile instruction expects `maven_settings` to be supplied by the pipeline through an approved channel. Never hardcode credentials in source code, Dockerfiles, or `project.toml`.

### 17.3. SBOMs and Vulnerability Scanning

**Artifact Analysis** provides container vulnerability scanning in Artifact Registry when enabled/configured. Some buildpacks generate **SBOMs** depending on the builder, though you should never assume every image automatically carries a complete SBOM.

Workflow:

- Scan the **final image**, covering both OS layers and Java dependencies.
- Review CVE severity, patch availability, exploit scope, and release policy.
- When a CVE comes from the base image, update/rebuild or rebase if compatible.
- When a CVE comes from a JAR library, update the dependency and rebuild.
- Record source commit, provenance, scan results, SBOM, and image digest.
- Check scanning pricing and enablement; **do not assume every repo has auto-scan enabled**.

**Distroless does not eliminate vulnerabilities in Spring/Jackson/Log4j.** Shrinking OS packages is only one part of security hygiene.

### 17.4. Runtime Identity

- Run non-root where supported; verify writable paths.
- Use ADC, Workload Identity Federation, or runtime service accounts; avoid JSON service account keys.
- Grant IAM only for Cloud Storage, Pub/Sub, Secret Manager, or Cloud SQL resources actually used.
- Keep image pull/deploy identities separate from the app service account.
- Never put tokens, private keys, `.env`, or PII into images or logs.

## 18. CI/CD: Build Once, Deploy the Same Digest

~~~mermaid
flowchart TD
    COMMIT["Git commit SHA"] --> TEST["Unit/integration tests"]
    TEST --> BUILD["Multi-stage or Buildpacks"]
    BUILD --> SCAN["Scan + SBOM/provenance"]
    SCAN --> PUSH["Push Artifact Registry"]
    PUSH --> DIGEST["Record image digest"]
    DIGEST --> STG["Deploy staging by digest"]
    STG --> SMOKE["Smoke/performance tests"]
    SMOKE --> APPROVE{"Release gate passed?"}
    APPROVE -->|Yes| PROD["Deploy production same digest"]
    APPROVE -->|No| STOP["Halt release and remediate"]
    PROD --> MON["Monitor, roll back if needed"]
~~~

Checklist:

- `mvn verify` or Gradle tests run prior to packaging if the Dockerfile skips tests.
- CI identity has push permission without blanket production admin rights.
- Untrusted PRs never access production credentials.
- Promotion uses the **same digest**, never rebuilding with dynamic tags.
- Retain prior revisions/digests for rollback.
- Require approvals, audit logs, and scan gates.

**Rebasing does not fix application dependencies:** swapping compatible run-image layers does not patch vulnerable JARs; update Maven/Gradle dependencies and rebuild.

## 19. Measuring Outcomes: Size, Time, Startup, and Memory

| Metric | How to capture | What to understand |
| --- | --- | --- |
| Local size | `docker image inspect --format '{{.Size}}' IMAGE` | Not necessarily equal to compressed pull bytes |
| Layer history | `docker history --no-trunc IMAGE` | Which layers changed; whether build commands leaked |
| Cold build | Build in an environment with empty caches | Baseline build cost |
| Warm build | Rebuild after a small code edit | Actual cache hit behavior |
| Push/pull time | Build/registry/runtime logs | Network, compressed layers, and cache |
| Startup/ready | Cloud Run revision/GKE logs | Java/framework initialization |
| First request latency | Timestamped HTTP smoke test | Experience right after readiness |
| CPU/memory | JVM/Cloud Monitoring metrics | Runtime efficiency |
| CVE findings | Artifact Analysis/scanner | Base and app risk |
| Cost | Billing Reports | Build, registry, network, runtime |

### 19.1. Controlled Benchmarking

Use the **exact same commit, JDK 21, CPU architecture, builder machine size, memory, and network conditions**. Measure cold and warm builds separately, run multiple trials, and record cache state.

| Measure | Single-stage | Multi-stage | Buildpacks |
| --- | --- | --- | --- |
| Image size | Measure directly | Measure directly | Measure directly |
| Cold build time | Measure directly | Measure directly | Measure directly |
| Warm build time | Measure directly | Measure directly | Measure directly |
| Push duration | Measure directly | Measure directly | Measure directly |
| Startup to ready | Measure directly | Measure directly | Measure directly |
| Memory | Measure directly | Measure directly | Measure directly |
| Critical CVEs | Scan directly | Scan directly | Scan directly |

**Never claim an image is "70% smaller" or "2x faster on cold starts" without measuring.** Impact varies across frameworks, dependencies, base images, and runtimes.

## 20. Troubleshooting

| Symptom | Cause | Check |
| --- | --- | --- |
| `COPY --from=build ...jar` fails | Wrong JAR path/version | `target/`, Maven plugin, build logs |
| `no main manifest attribute` | JAR is not executable | Spring Boot packaging/plugin |
| `UnsupportedClassVersionError` | Java runtime older than compile target | JDK release/target vs. JRE |
| `sh: not found` | Distroless lacks a shell | JSON-form `CMD`/`ENTRYPOINT` |
| `Permission denied` | Non-root lacks read/write access | File permissions, writable paths |
| Cloud Run not ready | App not listening on `0.0.0.0:$PORT` or slow startup | Logs, Spring Boot port/host |
| `OOMKilled`/137 | Heap + native memory exceed limit | JVM memory, Pod/Cloud Run limits |
| TLS/JNI failure after switching base | Missing CA certs/native libs/timezones | Runtime dependencies/integration tests |
| Buildpacks fails to detect | Wrong source root/`pom.xml` | Detection logs and builder support |
| Buildpacks picks wrong Java | Missing `GOOGLE_RUNTIME_VERSION` | `project.toml`/build logs |
| Local `pack build` fails | Docker daemon/builder pull/architecture | Engine, credentials, network |
| Artifact Registry push `403` | Auth/IAM Writer or wrong repo URL | Configure Docker, IAM, repo |
| Cloud Run image pull fails | Wrong digest, cross-project IAM | Service agent/Reader, image URL |
| Slow CI build | Cache not reused or `COPY . .` too early | Layer order, cache mounts |
| Slow startup despite small image | Java classpath/framework/DB init | JVM profiling, metrics |
| Scan reports many CVEs | App dependencies or stale base | SBOM, update JAR/runtime |

~~~mermaid
flowchart TD
    A["Build/deploy failure"] --> B{"Did JAR build?"}
    B -->|No| C["Maven/Gradle/JDK logs"]
    B -->|Yes| D{"Image artifact/runtime right?"}
    D -->|No| E["COPY, CMD/ENTRYPOINT, platform"]
    D -->|Yes| F{"Does docker run work locally?"}
    F -->|No| G["Java, permissions, libraries"]
    F -->|Yes| H{"Push/pull Artifact Registry works?"}
    H -->|No| I["IAM, registry URL, digest"]
    H -->|Yes| J{"Cloud Run/GKE ready?"}
    J -->|No| K["PORT, probes, memory, IAM, VPC"]
    J -->|Yes| L["Monitor SLOs and cost"]
~~~

## 21. Cost and Image Lifecycle

| Component | Potential costs |
| --- | --- |
| **Cloud Build** | Build time, builder machine tier, run count |
| **Artifact Registry** | Image/layer storage, data transfer, and operations |
| **Cloud Run** | CPU/memory, requests, concurrency, min instances, billing model |
| **GKE** | Node/cluster resources, image pulls/autoscaling |
| **Network** | Data transfer across locations and services |
| **Artifact Analysis** | Scanning per enabled features and configuration |
| **Logging/Monitoring** | Logs, metrics, and retention |

**A smaller image does not automatically cut your Cloud Run bill by the same percentage.** Runtime CPU/memory, request duration, and application behavior still drive most application costs.

### 21.1. Cleanup and Rollback

- Manage tags by release/commit and record deployed digests.
- Use Artifact Registry cleanup policies to prune unused artifacts.
- Never delete digests still referenced by Cloud Run revisions, GKE deployments, or rollback plans.
- Periodically review untagged images and registry storage.
- After labs, delete resources only after confirming no workloads depend on them.

## 22. Comprehensive Scenario: Orders API

The Commerce team runs a Java 21 Spring Boot service on Cloud Run calling Cloud SQL, Pub/Sub, and Cloud Storage. They want an easy-to-maintain pipeline, non-root runtime, and reproducible releases.

| Need | Option worth testing |
| --- | --- |
| Standard Maven/Spring Boot | Google Cloud Buildpacks |
| Minimal runtime and custom dependencies | Multi-stage + distroless |
| Multi-environment CI/CD | Build once, deploy same digest |
| Secrets and DB credentials | Runtime identity / Secret Manager |
| Vulnerability policy | Artifact Analysis + Maven dependency scanning |
| Rollback | Cloud Run revisions and image digests |
| Cost review | Build time, image storage, startup, runtime bill |

**Evaluation lab steps:**

1. Run `mvn -B -ntp verify` on the same commit.
2. Build with multi-stage; record image size, digest, and duration.
3. Build with `pack` using `GOOGLE_RUNTIME_VERSION=21` and record the same metrics.
4. Run identical HTTP smoke tests locally.
5. Push both images to the same Artifact Registry region; capture real digests.
6. Deploy two private Cloud Run test services with identical CPU/memory/concurrency settings.
7. Measure startup, p95 latency, errors, memory, and TLS/JDBC behavior.
8. Scan and inspect SBOMs and vulnerabilities.
9. Choose an approach based on **evidence + maintainability**.
10. Clean up test services/images safely once no longer needed.

If Buildpacks yields a slightly larger image yet is easier to operate with comparable runtime behavior, the team may choose Buildpacks. If specialized JNI/OS packages are required, multi-stage may fit better. **No single approach wins in every scenario.**

## 23. Self-Check Exercises

**Q1.** Why can a single-stage Maven image be unsuitable for production?

*Answer:* It carries compilers, build tools, caches, and source code unnecessary at runtime.

**Q2.** Why should `COPY pom.xml` come before `COPY src`?

*Answer:* So the dependency cache can be reused when only source code changes.

**Q3.** Does BuildKit `--mount=type=cache,target=/root/.m2` bake the Maven cache into the runtime image?

*Answer:* No. It is a builder-side cache, not a copied artifact.

**Q4.** With the Java distroless base, why is `CMD ["/app/app.jar"]` valid?

*Answer:* The image has an entrypoint equivalent to `java -jar`; `CMD` supplies the JAR argument.

**Q5.** Why can `CMD ["sh","-c","..."]` fail on distroless?

*Answer:* Distroless images lack a default shell.

**Q6.** Is `EXPOSE 8080` enough for Cloud Run readiness?

*Answer:* No; the application must actively listen on `0.0.0.0` and the right `PORT`.

**Q7.** How do Buildpacks know an app uses Maven?

*Answer:* Builder detection checks source descriptors such as `pom.xml`.

**Q8.** How do you select Java 21 for Google Cloud Buildpacks?

*Answer:* `GOOGLE_RUNTIME_VERSION=21` in build env/`project.toml`.

**Q9.** How does deploying from source differ from deploying by digest?

*Answer:* Source deployment triggers a new build; digest deployment runs the exact already-built/tested artifact.

**Q10.** Is `:latest` immutable?

*Answer:* No. Digests are better suited for pinning images.

**Q11.** Does distroless eliminate all Java vulnerabilities?

*Answer:* No. Application dependencies and the runtime still require scanning and patching.

**Q12.** Does CNB `rebase` automatically patch Spring dependencies?

*Answer:* No; rebase only swaps compatible run-image layers.

**Q13.** Does an app's runtime service account need Artifact Registry Writer to run?

*Answer:* Usually no; the pushing identity needs Writer, while the pulling identity needs Reader where applicable.

**Q14.** Is a 100 MB local image guaranteed to push twice as fast as a 200 MB image?

*Answer:* No; compression, layer caching, and network conditions also determine speed.

**Q15.** Does a smaller image guarantee fast cold starts?

*Answer:* No; JVM initialization, dependencies, and resource allocation also affect startup.

**Q16.** A JNI driver breaks after switching to distroless—how do you handle it?

*Answer:* Inspect OS/native library dependencies and choose a runtime meeting workload requirements.

**Q17.** Why should secrets never go into Docker `ARG`?

*Answer:* They can leak through build history, caches, or logs; use secret mounts instead.

**Q18.** When should you try Buildpacks first?

*Answer:* Standard Java/Maven/Gradle projects aiming to minimize Dockerfile maintenance, while still benchmarking and scanning.

## 24. Pre-Production Checklist

- [ ] Locked Java version, Maven/Gradle, plugins, and dependencies; tests run in CI.
- [ ] Multi-stage copies only runtime artifacts, excluding Maven/Gradle/source/caches.
- [ ] `.dockerignore` excludes unnecessary files and anything potentially holding secrets.
- [ ] Caching works in the real CI environment; never assume CI nodes share local caches.
- [ ] Java compile target matches the Java runtime version.
- [ ] Non-root, filesystem permissions, CA certs/JNI/timezones meet requirements.
- [ ] Distroless exec-form `CMD`/`ENTRYPOINT` configured properly without requiring a shell.
- [ ] Java listens properly on `0.0.0.0:$PORT` on Cloud Run.
- [ ] Builder/base images pinned with a scheduled security update cadence.
- [ ] No secrets in image layers, Docker build args, or source code.
- [ ] Artifact Registry repo, location, and Writer/Reader IAM verified.
- [ ] Final image scanned; SBOM/provenance generated where policy requires.
- [ ] Staging/production deploy the **exact same verified digest**.
- [ ] Smoke tests, readiness probes, CPU/memory/latency metrics, and rollbacks in place.
- [ ] Measured cold/warm builds, push/pull, startup, vulnerabilities, and cost.
- [ ] Retention/cleanup policies preserve rollback artifacts.
- [ ] Budget and owner assigned for lab/CI/CD projects.

## 25. Key Takeaways

- **Multi-stage builds** separate build tools/JDK from runtime and copy only the runnable artifact.
- **Buildpacks** auto-detect Maven/Gradle and build OCI images via a builder, reducing Dockerfile maintenance.
- **`.dockerignore`, layer ordering, and BuildKit caches** improve build efficiency, though they do not guarantee fast runtimes by themselves.
- **Distroless Java** includes a `java -jar` entrypoint and lacks a default shell; verify `CMD`, non-root permissions, and OS dependencies.
- **A smaller image does not automatically mean safer, faster cold starts, or a lower bill.**
- **Artifact Registry** stores images with IAM/location controls; tags are for naming, while **digests** enable immutable releases.
- **Build once, test, scan, and promote the same digest** strengthens traceability and rollbacks.
- **SBOMs, scanning, and dependency/base/JDK updates** remain necessary for both Dockerfiles and Buildpacks.
- **Cost** spans builds, storage, transfer, scanning, and runtime—not merely the megabytes of a JAR.

When deploying Java to GKE, Compute Engine, or Cloud Run, ask: **"Does the final image contain only what the app needs to run? If only code changes, which steps must rebuild? How are the builder, JDK, and CVEs managed? Is production running the exact tested digest?"** Multi-stage builds and Buildpacks offer two distinct ways to solve the same controlled packaging problem.

## Official References

- [Docker multi-stage builds](https://docs.docker.com/build/building/multi-stage/)
- [Docker build cache optimization](https://docs.docker.com/build/cache/optimize/)
- [Docker Build secrets](https://docs.docker.com/build/building/secrets/)
- [Google Cloud Buildpacks overview](https://cloud.google.com/docs/buildpacks/overview)
- [Building Java with Google Cloud Buildpacks](https://cloud.google.com/docs/buildpacks/java)
- [Build application with buildpacks](https://cloud.google.com/docs/buildpacks/build-application)
- [Use a specific builder](https://cloud.google.com/docs/buildpacks/use-a-specific-builder)
- [Cloud Build: Build container images](https://cloud.google.com/build/docs/building/build-containers)
- [Cloud Run: Deploy from source](https://cloud.google.com/run/docs/deploying-source-code)
- [Cloud Run: Container runtime contract](https://cloud.google.com/run/docs/container-contract)
- [Artifact Registry: Push and pull images](https://cloud.google.com/artifact-registry/docs/docker/pushing-and-pulling)
- [Artifact Analysis and vulnerability scanning](https://cloud.google.com/artifact-registry/docs/analysis)
- [Distroless Java runtime README](https://github.com/GoogleContainerTools/distroless/blob/main/java/README.md)
- [Cloud Native Buildpacks documentation](https://buildpacks.io/docs/)
- [Artifact Registry pricing](https://cloud.google.com/artifact-registry/pricing)
