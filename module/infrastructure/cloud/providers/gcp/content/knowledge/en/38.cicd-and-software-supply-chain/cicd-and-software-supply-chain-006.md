# Caching, Artifacts, and Java Build Time Optimization

A Java pipeline can spend most of its time downloading dependencies, recompiling unchanged code, re-running redundant tests, or packaging containers with layers that are constantly rebuilt. When teams release frequently, a few minutes of delay per build accumulate into long wait times and slow down feedback during bug fixes.

Optimizing builds on Google Cloud requires distinguishing three concerns: **caching** to avoid recomputing or re-downloading existing data, **artifacts** to store and distribute versioned build outputs, and **pipelines** to execute steps in the proper order with appropriate resources. Cloud Build provides the pipeline execution environment; Artifact Registry stores packages and container images; Maven or Gradle manages Java dependencies and builds. Combined properly, teams can reduce build times while preserving reproducibility, inspectability, and software supply chain security.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish between dependency cache, build cache, Docker layer cache, and artifact repositories.
- Design caching for Maven and Gradle when building on Cloud Build.
- Use Artifact Registry to proxy dependencies and store packages/container images.
- Structure Java Dockerfiles with layer ordering that leverages caching.
- Measure per-step duration and select high-impact optimization targets.
- Protect caches from cache poisoning and keep secrets out of artifacts.
- Produce artifacts with stable versions/digests that are traceable and promotable across environments.
- Balance speed, cost, reproducibility, and security in CI/CD pipelines.

## 1. Understanding Caching and Artifacts Properly

Caches and artifacts are often mentioned together, yet they have different lifecycles.

| Component | Purpose | Can Be Deleted and Recreated? | Example |
|---|---|---|---|
| Dependency cache | Retains downloaded libraries to avoid re-fetching from upstream | Yes, if dependencies remain accessible | Maven local repository, Gradle dependency cache |
| Build cache | Retains reusable task outputs when inputs match | Yes, if tasks can re-run | Gradle task output cache |
| Docker layer cache | Reuses image layers when instructions and inputs are unchanged | Yes, if layers can be rebuilt | JRE or dependency installation layers |
| Artifact | Built output that must be stored and distributed | Should not be treated as temporary cache | JAR, WAR, container image |
| Artifact repository | Stores artifacts with versioning, permissions, and retention policies | Managed by release lifecycle | Artifact Registry Maven/Docker repository |

Caching is a performance optimization. An artifact is a build deliverable and requires a stable identity for deployment, inspection, or recovery.

A deleted dependency cache does not lose a release if the artifact is stored in a repository. Conversely, if a cache is treated as the sole storage for production JARs, cache expiration or overwrites can leave the team without a reliable release artifact.

## 2. Measuring Build Times Before Optimizing

Do not start by bumping CPU or enabling every cache type. First, identify where time is being spent.

A typical Java build may include:

1. Provisioning the Cloud Build worker and checking out source code.
2. Initializing the JDK, Maven/Gradle Wrapper, and plugins.
3. Resolving dependencies.
4. Compiling source and generating code.
5. Running unit tests and integration tests.
6. Packaging the JAR/WAR.
7. Building the container image.
8. Pushing the image or package to Artifact Registry.
9. Generating provenance, SBOM, and running security checks.

Record the duration of each step, bytes downloaded, cache hits/misses, CPU, memory, disk I/O, and test counts. Cloud Build displays per-step durations in build details; combine logs and metrics to compare across runs.

### Metrics to Track

| Metric | Meaning |
|---|---|
| Total build duration | Time from build start to completion |
| Queue/wait time | Time waiting for a worker or build slot |
| Dependency download time | Time spent resolving and fetching dependencies |
| Compile/test duration | Time spent compiling and testing |
| Cache hit rate | Proportion of data or tasks reused |
| Image build duration | Time spent building the container image |
| Artifact upload duration | Time spent pushing packages/images |
| Build success rate | Percentage of builds completing successfully |
| Cost per successful build | Average cost per successful build |

For example, if a build takes 8 minutes and 5 minutes are spent in integration tests spinning up a database, speeding up the dependency cache will not address the main bottleneck. If 3 minutes are spent downloading Maven dependencies from the Internet on every run, an Artifact Registry remote repository and build caching can make a significant difference.

Measure both cold builds (empty cache) and warm builds (populated cache). Compare multiple runs to avoid drawing conclusions from a single outlier run with atypical networking or worker behavior.

## 3. Dependency Caching for Maven

Maven stores downloaded artifacts in a local repository, typically the **.m2/repository** directory inside the home directory of the user running the build. The local repository holds resolved dependencies, plugins, and metadata.

When a fresh Cloud Build worker is provisioned, the local repository normally starts empty. Consequently, every build may re-download dependencies unless caching is designed.

### Sharing the Local Maven Repository Across Steps

Cloud Build shares the **/workspace** directory across build steps within the same build. You can declare a volume to share another path, such as **/root/.m2**, across steps. This volume exists within the scope of the current build; it does not automatically persist across separate builds.

Example Cloud Build configuration with two Maven steps sharing a volume:

~~~yaml
steps:
  - id: resolve-dependencies
    name: maven:3.9-eclipse-temurin-21
    entrypoint: mvn
    args:
      - -B
      - -ntp
      - dependency:go-offline
    volumes:
      - name: maven-repository
        path: /root/.m2

  - id: verify
    name: maven:3.9-eclipse-temurin-21
    entrypoint: mvn
    args:
      - -B
      - -ntp
      - verify
    volumes:
      - name: maven-repository
        path: /root/.m2
~~~

The first step prefetches required dependencies and plugins; the second step reuses the local repository within the same build. The `dependency:go-offline` goal prefetches many dependencies, though it does not guarantee every plugin or dependency activated by dynamic profiles is cached. The verify step still needs repository access if additional dependencies are resolved.

### Using the Maven Wrapper

Commit the Maven Wrapper and configure the Maven version explicitly. Builds should run via **./mvnw** so local environments and CI use the exact same Maven version.

Example:

~~~bash
./mvnw -B -ntp verify
~~~

Options:

- **-B:** runs in batch mode, suitable for CI.
- **-ntp:** disables transfer progress output for cleaner logs.
- **verify:** executes necessary lifecycle phases before treating the artifact as verified.

Do not blindly add **-T 1C** to every pipeline. Maven parallel builds can accelerate multi-module projects, but plugins or tests may not be thread-safe. Benchmark and verify memory/CPU limits first.

### Caching Dependencies Across Multiple Builds

A Cloud Build volume only shares data between steps of a single build. To avoid downloading dependencies from upstream on every build, use an Artifact Registry remote repository for Maven. A remote repository proxies upstream repositories like Maven Central and caches fetched artifacts inside Artifact Registry.

A common setup:

- Remote repository: proxies public dependencies, reduces upstream reliance, and centralizes download source control.
- Standard repository: stores internal packages published by the organization.
- Virtual repository: exposes a single unified endpoint across multiple repositories and controls resolution priority order.

Maven can access Artifact Registry using repository configuration and appropriate authentication. Use the following command to print sample settings for an existing repository:

~~~bash
gcloud artifacts print-settings mvn \
  --project=PROJECT_ID \
  --repository=MAVEN_REPOSITORY \
  --location=LOCATION
~~~

The command prints the required Maven settings for the repository and location. Integrate that configuration into your POM or Maven settings per Artifact Registry documentation. Never commit access tokens or passwords into `pom.xml` or `settings.xml`.

### When to Use Offline Mode?

Maven provides an offline flag:

~~~bash
./mvnw -o -B verify
~~~

Use it only when all required dependencies and plugins are already present in the local repository. If the cache is missing a single artifact, the build will fail. Offline mode is not a substitute for stable repository and dependency management.

## 4. Dependency Cache and Build Cache in Gradle

Gradle has multiple distinct caches:

- Dependency cache stores resolved modules and artifacts.
- Build cache stores reusable task outputs when inputs are identical.
- Configuration cache stores build configuration results to reduce configuration time on subsequent runs.

These three caches solve three different problems. The dependency cache does not automatically give compile tasks output cache hits; the build cache does not replace a dependency repository; the configuration cache can cut configuration overhead but requires compatible plugins and build scripts.

### Enabling the Gradle Build Cache

The build cache can be enabled on the command line:

~~~bash
./gradlew --build-cache test bootJar
~~~

Or configured in `gradle.properties`:

~~~properties
org.gradle.caching=true
org.gradle.parallel=true
org.gradle.jvmargs=-Xmx2g -Dfile.encoding=UTF-8
~~~

Gradle only reuses outputs for cacheable tasks that fully declare their inputs and outputs. For custom tasks, use proper annotations and APIs so Gradle knows which files, properties, and tools the task depends on. If a task reads an environment variable without declaring it as an input, the cache can return stale outputs for a different environment.

### Configuration Cache

The configuration cache avoids re-executing the build's configuration phase when build configuration is unchanged and plugins are compatible.

Test enabling it on a separate branch:

~~~bash
./gradlew --configuration-cache --build-cache test
~~~

If Gradle reports incompatible tasks or plugins, resolve those issues before enabling it across the entire pipeline. Do not ignore warnings just to achieve cache hits.

### Remote Build Cache

Cloud Build workers are typically ephemeral environments. The local Gradle cache inside a worker is lost when the build ends. To reuse task outputs across multiple workers/builds, you need a remote build cache with a Gradle-compatible protocol, such as Gradle Enterprise/Develocity or an organization-operated HTTP build cache server.

Example configuration in `settings.gradle.kts`:

~~~kotlin
buildCache {
    remote<HttpBuildCache> {
        url = uri("https://gradle-cache.example.internal/cache/")
        isPush = providers.gradleProperty("trustedBuild").orNull == "true"
    }
}
~~~

The URL above is a placeholder. Production endpoints require TLS, authentication, and controlled access. Only trusted builds, such as pipelines running from protected branches after checks, should have permission to push to a shared cache. Builds from untrusted pull requests should be read-only or use an isolated namespace to prevent cache poisoning.

An Artifact Registry Maven repository caches dependencies using the repository protocol; it does not automatically act as a Gradle task-output build cache. Do not configure a Maven repository URL as a Gradle remote build cache endpoint.

### Dependency Locking and Verification

For reproducible builds, lock dependency versions and verify checksums.

Example in Gradle:

~~~kotlin
dependencyLocking {
    lockAllConfigurations()
}
~~~

Generate or update lockfiles according to project procedures:

~~~bash
./gradlew dependencies --write-locks
~~~

Gradle dependency verification can record checksum metadata:

~~~bash
./gradlew --write-verification-metadata sha256 help
~~~

Review and commit changes to lock/verification metadata. Never automatically accept new checksums in every build, as doing so could validate a substituted dependency.

## 5. Cloud Build Cache: Lifespan and Strategy

A common misconception is that Cloud Build volumes automatically cache data across builds. In reality:

- **/workspace** is shared across steps of the same build.
- Named volumes declared in Cloud Build are likewise shared across steps mounting that volume within the same build.
- A new worker/build does not automatically inherit the local filesystem cache from a prior build.
- Artifact Registry and remote build caches are external storage services that persist according to their own policies.

Therefore, design in layers:

| Layer | How to Leverage | Scope |
|---|---|---|
| Workspace | Store intermediate outputs or files shared across steps | Single build |
| Named volume | Share `.m2` or `.gradle` across steps | Single build |
| Artifact Registry remote repo | Cache upstream dependencies | Multiple builds |
| Gradle remote build cache | Reuse task outputs | Multiple builds |
| Docker registry cache | Reuse image layers | Multiple builds |
| Artifact Registry standard repo | Store released packages/images | By retention/version |

### Example Maven and Docker Image Pipeline

~~~yaml
steps:
  - id: dependencies
    name: maven:3.9-eclipse-temurin-21
    entrypoint: mvn
    args: ["-B", "-ntp", "dependency:go-offline"]
    volumes:
      - name: m2
        path: /root/.m2

  - id: verify
    name: maven:3.9-eclipse-temurin-21
    entrypoint: mvn
    args: ["-B", "-ntp", "verify"]
    volumes:
      - name: m2
        path: /root/.m2

  - id: build-image
    name: gcr.io/cloud-builders/docker
    args:
      - build
      - -t
      - asia-southeast1-docker.pkg.dev/$PROJECT_ID/java-services/checkout:$SHORT_SHA
      - .

images:
  - asia-southeast1-docker.pkg.dev/$PROJECT_ID/java-services/checkout:$SHORT_SHA
~~~

This example illustrates a Maven volume shared between two steps and an image pushed to Artifact Registry. Ensure the Cloud Build service account has read permissions on dependency repositories and write permissions on the Docker repository. Tagging with the commit SHA aids traceability; for production deployments, record the digest after pushing.

In real pipelines, resolving dependencies and verifying can be combined if there is no reason to split them. Each extra step adds container startup and artifact handoff overhead; measure total build time rather than optimizing steps in isolation.

## 6. Optimizing Java Dockerfiles with Layer Caching

Docker builds create layers per instruction. When an instruction and all its relevant inputs are unchanged, Docker can reuse the existing layer. Copying the entire source tree before resolving dependencies causes any small source change to invalidate the dependency layer and force Maven to re-download libraries.

### Unoptimized Dockerfile

~~~dockerfile
FROM maven:3.9-eclipse-temurin-21
WORKDIR /app
COPY . .
RUN mvn -B -ntp package
~~~

This approach is simple, yet changing any file in the build context invalidates the COPY layer, triggering full dependency resolution and packaging again.

### Dockerfile Ordered by Layer Stability

~~~dockerfile
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /workspace

COPY pom.xml .
COPY .mvn/ .mvn/
COPY mvnw .
RUN chmod +x mvnw && ./mvnw -B -ntp dependency:go-offline

COPY src/ src/
RUN ./mvnw -B -ntp verify

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /workspace/target/app.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Dependencies are resolved before copying source code. When only files under `src/` change, the dependency layer can be reused. Adjust the JAR path and resource directories to match your real project.

Create a `.dockerignore` file to exclude unnecessary files:

~~~text
.git
.gradle
.m2
target
build
.idea
*.iml
.env
*.pem
*.key
~~~

Never include credentials, production environment files, or private keys in the build context. If a build requires secrets, use the builder's secret mount mechanism or pass credentials via Secret Manager per pipeline design; never use Docker `ARG` or `ENV` to embed secrets into image layers.

### BuildKit Registry Cache

If your builder uses Docker BuildKit/buildx, image layer caches can be stored in Artifact Registry so fresh build workers pull cache from previous runs.

Example:

~~~bash
docker buildx build \
  --cache-from=type=registry,ref=asia-southeast1-docker.pkg.dev/PROJECT_ID/java-services/checkout:buildcache \
  --cache-to=type=registry,ref=asia-southeast1-docker.pkg.dev/PROJECT_ID/java-services/checkout:buildcache,mode=max \
  --tag=asia-southeast1-docker.pkg.dev/PROJECT_ID/java-services/checkout:COMMIT_SHA \
  --push .
~~~

This requires a builder supporting buildx/BuildKit and appropriate Artifact Registry permissions. Keep cache images and release images under distinct tags. Never deploy the `buildcache` tag to production. For concurrent pipelines, consider multiple builds writing to the same cache reference; separate caches by branch or enforce controlled cache updates.

## 7. Artifact Registry: Proxying Dependencies and Storing Release Artifacts

Artifact Registry stores, manages, and distributes packages and container images. For Java, the Maven repository format can store internal packages and proxy dependencies from upstream.

### Three Common Repository Types

| Type | Role | Example |
|---|---|---|
| Standard | Stores artifacts published by the organization | `com.company:checkout:1.4.0` |
| Remote | Proxies and caches artifacts from upstream | Maven Central |
| Virtual | Unifies multiple repositories behind one endpoint | Prioritize internal repository before remote |

A deployment model:

~~~text
Maven / Gradle build
        |
        v
Artifact Registry virtual repository
        |
        +---- Internal standard repository
        |
        +---- Maven Central remote repository
        |
        v
Dependencies resolved
        |
        v
Compile / test / package
        |
        v
Artifact Registry standard repository
        |
        +---- Maven package
        |
        +---- Container image
~~~

A virtual repository centralizes endpoint configuration and prioritizes package sources. Configure priorities explicitly so internal packages cannot be shadowed by packages with matching coordinates from untrusted upstream sources.

### Publishing Maven Packages

After a successful build, Maven can publish packages via the `deploy` phase:

~~~bash
./mvnw -B -ntp deploy
~~~

The POM must configure `distributionManagement` pointing to the Artifact Registry Maven repository along with appropriate authentication. Use the following command to print sample settings:

~~~bash
gcloud artifacts print-settings mvn \
  --project=PROJECT_ID \
  --repository=MAVEN_RELEASES \
  --location=LOCATION
~~~

Artifacts are identified by `groupId`, `artifactId`, and `version`. Never overwrite an already-published release version. Use a new version for each release; if using `SNAPSHOT` during development, understand snapshot repository metadata and update behavior.

### Publishing Gradle Artifacts

With the Gradle Maven Publish plugin, configure publications and repositories per project standards. Command to print Artifact Registry settings:

~~~bash
gcloud artifacts print-settings gradle \
  --project=PROJECT_ID \
  --repository=GRADLE_RELEASES \
  --location=LOCATION
~~~

Then publish via the project's task:

~~~bash
./gradlew publish
~~~

Separate permission to read dependencies from permission to publish packages. Pull request build pipelines should not have write access to release repositories.

## 8. Managing Artifacts by Version and Digest

A release artifact requires a stable identifier. For Java packages, the identifier typically comprises group, artifact, and version. For container images, the SHA-256 digest is the exact content identifier; a tag is merely a reference name that can change depending on repository policies.

Image examples:

~~~text
asia-southeast1-docker.pkg.dev/my-project/java-services/checkout:8f3a2c1
asia-southeast1-docker.pkg.dev/my-project/java-services/checkout@sha256:...
~~~

Commit SHA tags help trace back to the source commit, but digests uniquely identify the exact image content. When promoting an image from staging to production, deploy the exact same tested digest rather than rebuilding the image per environment.

A release flow:

1. Build from a verified commit.
2. Run tests, scans, and policy checks.
3. Push the image or package to Artifact Registry.
4. Record the version, digest, build ID, and source commit.
5. Generate SBOM and provenance according to pipeline capabilities.
6. Promote the verified artifact to the next environment.
7. Deploy by digest and record the outcome.

Never use mutable tags like `latest` as the sole identifier for production releases. If a tag is repointed to different content, it becomes difficult to prove the environment is running the exact verified artifact.

## 9. Reproducible Builds and Supply Chain Integrity

Fast builds only matter if the results are trustworthy. A reproducible build controls its inputs:

- Source commit and repository state.
- JDK, Maven/Gradle Wrapper, and plugin versions.
- Dependency versions and source repositories.
- Base images and builder images.
- Environment variables affecting outputs.
- Locale, timezone, and timestamps if they alter the artifact.

### Pinning the Toolchain

Use the Maven Wrapper or Gradle Wrapper and fix the JDK version via toolchains or builder images. For container images, pin base images by digest when high reproducibility is required.

For example, Maven Wrapper properties should specify the distribution URL and distribution checksum. The Gradle Wrapper also supports distribution checksums. Do not rely on arbitrary pre-installed tool versions on workers.

### SBOM and Provenance

An SBOM (Software Bill of Materials) describes the components included in an artifact. Provenance records the origin and process that built the artifact, such as source, builder, and build details. This data aids vulnerability investigation, auditing, and verifying that artifacts came from a trusted pipeline.

Cloud Build and Artifact Registry integrate with provenance, Artifact Analysis, and supply chain security capabilities depending on project configuration. Store build metadata and link it to the image digest or package version.

### Caches Are Not the Source of Truth

Caches can be evicted, stale, or written by untrusted builds. Never use a cache as the sole store for releases. For shared remote caches:

- Separate read and write permissions.
- Allow only trusted pipelines to write to shared caches.
- Enforce TLS and authentication for cache servers.
- Never store credentials or secrets in cache outputs.
- Isolate caches by branch, trust level, or toolchain where needed.
- Maintain the ability to wipe caches and rebuild cleanly from controlled dependency/artifact sources.

Cache poisoning occurs when untrusted outputs are written into a shared cache and reused by other builds. Builds from forks or external pull requests must not be granted write access to caches used by trusted protected branches.

## 10. Optimizing Maven and Gradle Beyond Caching

Caching only solves part of build duration. Other techniques include:

### Maven

- Use the Maven Wrapper and fixed dependency/plugin versions.
- Separate fast unit tests from integration tests requiring infrastructure.
- Use multi-module builds with an explicit dependency graph.
- Run only affected modules when changes do not impact the whole project, if the build structure permits.
- Use Maven parallel builds after verifying plugins and tests are thread-safe.
- Avoid re-running packaging across multiple steps if artifacts can be passed between steps.
- Use `dependency:go-offline` for prefetching in suitably structured builds.

### Gradle

- Enable build cache and configuration cache when tasks/plugins are compatible.
- Declare task inputs/outputs completely for accurate cache hits.
- Use incremental compilation and incremental annotation processing if supported by plugins.
- Use parallel execution for independent subprojects.
- Limit workers based on actual CPU and memory.
- Use dependency locking and verification to prevent unstable version resolution.
- Do not enable configuration cache broadly before validating plugins and build scripts.

### Running Tests Efficiently

- Run independent unit tests in parallel when possible.
- Use test selection or module-level testing when changes do not affect the entire system.
- Keep integration tests representative of real dependencies.
- Quarantine flaky tests and fix root causes rather than retrying indefinitely.
- Use appropriate service emulators or test containers to reduce infrastructure startup time, while still scheduling integration tests against real services.
- Archive test reports and logs so builds do not have to be re-run just to inspect a past failure.

### Choosing Cloud Build Workers and Resources

If a build is CPU-bound, increasing CPU can reduce compile time. If a build is memory-bound, increasing memory or tuning JVM heap can reduce GC and OOM failures. If a build is download-bound, improving repositories/caches may be more effective than provisioning larger workers.

Cloud Build lets you choose machine type and disk size in the build config. Benchmark on a representative sample of builds, comparing cost per successful build and queue time before changing organization-wide defaults.

## 11. Complete Java Pipeline Design Example

A reference pipeline for a Spring Boot service:

~~~text
Commit / Pull Request
        |
        v
Checkout + verify JDK/Wrapper
        |
        v
Resolve dependencies via Artifact Registry
        |
        v
Compile + unit tests
        |
        v
Integration tests
        |
        v
Package JAR
        |
        v
Build container image with layer cache
        |
        v
Scan + SBOM + provenance
        |
        v
Push Artifact Registry
        |
        v
Promote same digest to staging
        |
        v
Canary / verify / promote production
~~~

Key principles:

- Pull requests only have permission to read necessary dependencies and caches.
- Only protected branches or release pipelines have permission to publish packages/images.
- Artifact versions are tied to commits and digests.
- Build caches are shared only among builds within the same trust boundary.
- Test, scan, and provenance results are linked to the produced artifact.
- Staging and production deployments use the exact same artifact digest.

A pipeline does not need to split every operation into a separate step. Split steps when isolation, cache mounts, separate permissions, or independent retries are needed; otherwise, container startup overhead can slow builds down.

## 12. Measuring Effectiveness After Optimization

After every change, compare against the baseline:

| Before/After | What to Verify |
|---|---|
| Cold build | Does the build still succeed when the cache is empty? |
| Warm build | Does caching actually reduce wall-clock duration? |
| Cache hit rate | Does it increase without producing incorrect outputs? |
| Artifact digest | Is it stable given identical source/toolchain/inputs? |
| Test results | Are test coverage and test quality preserved? |
| Failure rate | Do cache misses, timeouts, or races cause more failures? |
| Cost | Do time savings justify the cost of remote caches or larger workers? |
| Security | Can untrusted PRs write to caches or publish artifacts? |

Internal measurement targets might aim to cut median build duration by 30%, maintain build success rate, and avoid increasing post-publish artifact changes. Targets should be grounded in each project's baseline rather than applying one uniform number across all teams.

## 13. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Mistaking Cloud Build volumes for cross-build caches | New workers still re-download dependencies | Use Artifact Registry remote repos or a remote build cache |
| Caching only dependencies while expecting faster compilation | Compile tasks still re-run | Use Gradle build cache or optimize tasks |
| Using an Artifact Registry Maven repo as a Gradle build cache | Incompatible protocols | Separate dependency repository from Gradle remote build cache |
| Copying all source before resolving dependencies in Dockerfile | Source edits invalidate dependency layer cache | Copy build descriptor files first |
| Caches without keys tied to toolchain/lockfile | Risk of reusing outputs from the wrong environment | Lock inputs and use appropriate cache keys |
| Allowing untrusted builds to write to shared remote cache | Cache poisoning | Separate cache write permissions by trust boundary |
| Writing secrets into Docker layers or caches | Credentials can leak via images or caches | Use secret mounts and exclude secrets from build context |
| Republishing the same release version | Artifact content changes while version stays identical | Use immutable versions and record digests |
| Relying solely on the `latest` tag | Cannot identify exact deployed artifact | Deploy by digest |
| Increasing worker size without profiling | Higher cost while bottleneck remains unchanged | Profile each build step first |

## 14. Java Build Optimization Checklist on GCP

- [ ] Baselines established for cold builds, warm builds, and per-step durations.
- [ ] JDK, Maven/Gradle Wrapper, and builder image versions are pinned.
- [ ] Dependency versions are controlled; Gradle lock/verification metadata is enabled where appropriate.
- [ ] Maven local repository or Gradle dependency cache is used effectively.
- [ ] Artifact Registry remote repositories proxy upstream dependencies where appropriate.
- [ ] Cloud Build workspaces/volumes are relied upon only within a single build.
- [ ] Gradle build cache/configuration cache enabled after validating tasks/plugins.
- [ ] Remote build caches enforce TLS, auth, read/write separation, and trust boundaries.
- [ ] Dockerfiles order layers by stability; `.dockerignore` excludes unneeded files.
- [ ] Docker BuildKit registry cache uses a distinct reference from release images.
- [ ] Artifact Registry stores versioned packages/images with retention policies.
- [ ] Verified artifacts are promoted across environments using the same digest.
- [ ] SBOM/provenance/scans are linked to artifacts per pipeline capabilities.
- [ ] Secrets are excluded from source, Docker layers, logs, and caches.
- [ ] Build time, success rate, and cost compared before and after optimization.

## Conclusion

Optimizing Java build times on GCP requires coordinating caching layers and artifact storage properly. Maven/Gradle dependency caches reduce library downloads; Gradle build caches skip re-running tasks with unchanged inputs; Docker layer caches speed up image creation; Artifact Registry proxies dependencies and stores released packages/images. Cloud Build workspaces and volumes support sharing within one build, whereas cross-build reuse requires remote repositories or appropriate remote caches. By pinning toolchains, locking dependencies, securing caches, and deploying by artifact digest, teams can accelerate pipelines while preserving reproducibility and supply chain trustworthiness.

## References

- [Cloud Build documentation](https://docs.cloud.google.com/build/docs)
- [Cloud Build: Build configuration file schema](https://docs.cloud.google.com/build/docs/build-config-file-schema)
- [Cloud Build: Use volumes](https://docs.cloud.google.com/build/docs/configuring-builds/pass-data-between-steps)
- [Artifact Registry overview](https://docs.cloud.google.com/artifact-registry/docs/overview)
- [Artifact Registry: Remote repositories](https://docs.cloud.google.com/artifact-registry/docs/repositories/remote-overview)
- [Artifact Registry: Virtual repositories](https://docs.cloud.google.com/artifact-registry/docs/repositories/virtual-overview)
- [Artifact Registry: Maven packages](https://docs.cloud.google.com/artifact-registry/docs/java)
- [Artifact Registry: Configure Gradle](https://docs.cloud.google.com/artifact-registry/docs/java/gradle)
- [Gradle: Build Cache](https://docs.gradle.org/current/userguide/build_cache.html)
- [Gradle: Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html)
- [Gradle: Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html)
- [Maven: Local repository](https://maven.apache.org/guides/introduction/introduction-to-repositories.html)
- [Docker: Build cache optimization](https://docs.docker.com/build/cache/optimize/)
- [Docker: Cache backends](https://docs.docker.com/build/cache/backends/)
- [SLSA: Provenance](https://slsa.dev/spec/v1.1/provenance)
