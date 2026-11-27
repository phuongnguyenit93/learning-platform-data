# Caching Gradle, Maven, Metadata, and Buildpacks by Appropriate Inputs

## 1. Why Design Caching by Layer?

In the **SPRING_BOOT_NATIVE_IMAGE** module, pipelines handle several expensive operations: downloading dependencies, running Spring AOT, compiling a Native Image, collecting reachability metadata, and packaging an OCI image with Cloud Native Buildpacks. Caching at the right layer avoids re-downloading or recomputing unchanged inputs.

No single cache directory covers all of these tasks. Gradle, Maven, Native Image, and buildpacks each have their own storage mechanisms, validity rules, and lifecycles. If you lump them under one shared cache key, a small change invalidates the entire cache; conversely, an overly broad cache can return outputs built under a different profile, toolchain, or platform.

A well-designed pipeline separates:

- **Dependency cache:** artifacts, plugins, wrappers, and metadata downloaded from repositories.
- **Build output cache:** task results reusable when all inputs match.
- **Configuration cache:** Gradle's computed build configuration model.
- **AOT and reachability metadata:** generated outputs and metadata tied to sources, classpath, profiles, and toolchain versions.
- **Buildpack cache:** layers created by buildpacks during image build and launch.
- **OCI/Docker cache:** image layers and container engine state.

These layers complement one another but do not substitute for one another. A Gradle dependency cache does not store buildpack layers; a buildpack cache does not replace the Maven local repository; reachability metadata cannot be shared across two library versions if the metadata contents differ.

## 2. Cache Map

| Cache | Contents | Managing tool | Primary invalidation unit |
| --- | --- | --- | --- |
| Gradle User Home | Wrapper, dependencies, artifact transforms, local build cache, and Gradle state | Gradle, CI action | Gradle version, OS, build files, dependency graph, job/commit |
| Gradle build cache | Outputs of cacheable tasks | Gradle local/remote build cache | Task implementation, input properties, classpath, and output declarations |
| Gradle configuration cache | Computed build configuration state | Gradle | Build logic, settings, environment, and configuration inputs |
| Maven local repository | Downloaded dependencies, plugins, POMs, and repository metadata | Maven Resolver | GAV, repository origin, release/snapshot metadata |
| Maven build cache | Outputs of eligible lifecycle/plugin executions | Maven Build Cache Extension | Source files, plugin parameters, and declared build environment |
| Spring AOT output | Generated sources, classes, resources, and initializers | Spring Boot Maven/Gradle plugin | Classpath, sources, AOT profile/arguments, and condition inputs |
| Native reachability metadata | Reflection, JNI, resource, serialization, and other metadata | GraalVM Native Build Tools/Native Image | Dependency version, metadata files, build tool, and Native Image version |
| Buildpack build cache | Layers used by buildpacks during image building | Cloud Native Buildpacks/Spring Boot plugin | Builder, buildpacks, dependencies, and application inputs |
| Buildpack launch cache | Layers used by buildpacks for image launch | Cloud Native Buildpacks/Spring Boot plugin | Run image, launch layers, and buildpack metadata |
| Build workspace | Temporary files used by builder/buildpacks during image builds | Spring Boot plugin/Docker daemon | Single build or workspace lifecycle |
| Docker/OCI layer cache | Image layers and base images | Docker/OCI engine | Layer contents, Dockerfile/build context, and image digest |

~~~mermaid
flowchart TB
    S["Source, build scripts, lock files"] --> G["Gradle or Maven"]
    G --> D["Dependency / wrapper cache"]
    G --> B["Build output cache"]
    G --> A["Spring AOT output"]
    A --> R["Reachability metadata + Native Image"]
    R --> N["Native executable"]
    N --> P["Cloud Native Buildpacks"]
    P --> C["Build cache + launch cache"]
    P --> I["OCI image layers"]
~~~

## 3. Cache Keys Must Reflect Every Input Affecting the Output

A cache is only valid when two builds share the exact meaningful inputs and outputs can be safely reused. Before enabling caching, identify every factor that can alter the resulting artifact.

For Spring Boot Native Image, these inputs typically include:

- source code and resources;
- `pom.xml`, parent POM, `settings.gradle(.kts)`, build scripts, and convention plugins;
- Maven/Gradle Wrapper and plugin versions;
- dependency lock files, version catalogs, BOMs, and dependency constraints;
- JDK vendor/version, compiler toolchain, and annotation processors;
- Spring Boot/Spring Framework versions and profiles used for AOT;
- GraalVM distribution/version, Native Build Tools version, and `native-image` options;
- OS, CPU architecture, libc, compiler, sysroot, and native libraries;
- builder image, run image, buildpack order/versions, and `BP_*` environment variables;
- configuration variables that alter generated sources or task outcomes.

Gradle and build-cache extensions can fingerprint many inputs automatically. However, custom tasks must declare their inputs and outputs completely. If a task reads an environment variable without declaring it as an input, the cache can return stale results even after the environment changes.

### 3.1. Distinguishing Stable vs. Volatile Inputs

| Input | How to include in cache key |
| --- | --- |
| Wrapper version | Hash wrapper properties files or partition caches per wrapper |
| Dependency versions | Hash lock files, version catalogs, POMs, and dependency constraints |
| JDK/GraalVM version | Include version/vendor in the key or partition the cache |
| OS/architecture/libc | Split caches by platform/architecture/ABI when outputs depend on them |
| AOT profile/arguments | Declare as task inputs and separate output variants |
| Builder/run image | Pin immutable tags or digests; include digest in build identity |
| Secrets/tokens | Never place secret values in keys; use a secret store and exclude from caches |
| Commit SHA | Can serve as a cache generation/version, but does not replace input fingerprinting |

Do not key caches solely on branch name or job name. Two commits on the same branch can differ in dependencies, JDK, or AOT profiles. Similarly, do not include the current timestamp in task inputs if the output does not depend on timestamps; needlessly volatile inputs hurt cache hit rates.

### 3.2. Cache Key vs. Restore Key

An exact cache key fetches the exact cache. Prefix-based restore keys can fetch the closest cache when no exact match exists. This is useful for dependency caches because previously downloaded artifacts can still be reused after a POM changes.

For build outputs, do not use loose restore prefixes to force-restore stale artifacts. Gradle/Maven build caches must validate fingerprints themselves; never unpack an output directory from another commit directly and bypass that validation.

CI caches are typically immutable per key. When inputs change, compute a new key and let the system store a new entry rather than trying to overwrite an existing cache entry with different content.

## 4. Caching for Gradle

### 4.1. Gradle User Home

Gradle User Home defaults to `~/.gradle`. It stores several reusable assets:

- Gradle distributions downloaded by the Wrapper;
- dependency artifacts and module metadata;
- artifact transform outputs;
- compiled build scripts and plugin-related state;
- local build cache;
- configuration cache if enabled by the project and persisted by CI.

On ephemeral CI runners, caching Gradle User Home significantly reduces wrapper and dependency download time. You do not need to manually cache the project's entire `build/` directory to achieve this.

### 4.2. Enabling Task Output Build Cache

In `gradle.properties`:

~~~properties
org.gradle.caching=true
~~~

Or enable for a single build:

~~~bash
./gradlew --build-cache clean build
~~~

Gradle uses task input/output fingerprints to locate reusable outputs. When a task is restored from cache, logs typically show `FROM-CACHE`.

The build cache only helps tasks that are cacheable and declare complete inputs/outputs. Custom tasks must describe:

- task implementation;
- input files and properties;
- classpath/toolchain;
- output files/directories;
- appropriate path sensitivity and normalization.

If a task produces non-deterministic outputs, depends on absolute paths, or reads undeclared environment variables, do not mark it as cacheable.

### 4.3. Local and Remote Build Cache

A local build cache fits runners or workspaces that are reused. A remote build cache fits setups where multiple agents need to share outputs. Gradle Groovy DSL example:

~~~groovy
buildCache {
    local {
        enabled = true
    }
    remote(HttpBuildCache) {
        url = 'https://gradle-cache.example.internal/cache/'
        credentials {
            username = System.getenv('GRADLE_CACHE_USER')
            password = System.getenv('GRADLE_CACHE_PASSWORD')
        }
        push = System.getenv('CI') == 'true' &&
            System.getenv('GITHUB_REF') == 'refs/heads/main'
    }
}
~~~

This is an illustrative configuration for a remote HTTP cache. The backend must support the Gradle build cache protocol. Only trusted runners on the main branch should have push access; pull requests from forks or untrusted branches should only read allowed public/shared caches.

### 4.4. Configuration Cache Is a Separate Cache

You can enable the Gradle configuration cache:

~~~properties
org.gradle.configuration-cache=true
~~~

The configuration cache stores the build configuration phase results to skip re-evaluating configuration on subsequent invocations. It does not store outputs of `compileJava`, `test`, or native compilation; that is the build cache's role.

The configuration cache can contain information read from the environment or credentials by build logic. When persisting it across CI jobs, follow the cache provider's security guidance. With `gradle/actions/setup-gradle`, if you want to cache configuration cache across jobs, supply a Base64 `cache-encryption-key` as required by the action and store the key in a CI secret. Never cache state that may contain credentials using uncontrolled plaintext storage.

## 5. GitHub Actions with Gradle

`gradle/actions/setup-gradle@v6` manages restoring and saving parts of Gradle User Home, including wrapper distributions, dependency caches, and the local build cache. The action also validates the Gradle Wrapper. For non-main branches, you can configure the cache as read-only:

~~~yaml
name: Gradle build

on:
  push:
  pull_request:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v5
        with:
          distribution: temurin
          java-version: '21'

      - uses: gradle/actions/setup-gradle@v6
        with:
          cache-read-only: ${{ github.ref != 'refs/heads/main' }}

      - name: Build and test
        run: ./gradlew --build-cache clean test
~~~

This example uses Java 21; replace it with the JDK/GraalVM version chosen for your project. `cache-read-only` lets PR branches read existing caches without writing outputs back into the shared cache. For native builds, the runner still needs GraalVM and the appropriate toolchain prepared; Gradle caching does not install those toolchains for you.

If configuration cache is enabled and you want to share it across jobs, provide `cache-encryption-key` from a secret per the action's documentation. Never print the secret to logs or include it in build scans.

## 6. Caching for Maven

### 6.1. Maven Local Repository

The Maven local repository defaults to `~/.m2/repository`. It stores:

- dependency JARs/WARs and POMs;
- Maven plugin artifacts;
- parent POMs and BOMs;
- repository metadata such as `maven-metadata.xml`;
- resolver tracking info for validating downloaded artifacts.

Maven checks the local repository before downloading artifacts from remote repositories. Caching this directory is therefore well suited to ephemeral CI runners.

Do not manually manipulate or modify the internal layout of the local repository via scripts. Maven Resolver manages locking, origins, and metadata; let Maven manage its contents.

### 6.2. Caching Dependencies with `setup-java`

GitHub Actions example:

~~~yaml
name: Maven build

on:
  push:
  pull_request:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v5
        with:
          distribution: temurin
          java-version: '21'
          cache: maven
          cache-dependency-path: |
            **/pom.xml
            .mvn/wrapper/maven-wrapper.properties
            .mvn/extensions.xml

      - name: Verify
        run: ./mvnw -B verify
~~~

`setup-java` keys the dependency cache by OS, architecture, package manager, and hashes of the specified dependency files. Depending on repository setup, the Maven wrapper distribution may also have its own cache. For multi-module projects, include all relevant POMs in `cache-dependency-path`.

Do not include `settings.xml` containing tokens/passwords in cache keys or cached paths. If mirror/repository configuration changes, consider versioning the cache name or separating runners/caches by repository identity; credentials must still come from secrets.

### 6.3. SNAPSHOTs and Dynamic Metadata

`SNAPSHOT`s, version ranges, and dependencies declared with dynamic versions can cause resolution results to change over time even without source changes. Maven metadata helps locate versions and snapshot timestamps; this data can change on remote repositories.

For release CI, prefer:

- fixed versions for dependencies and plugins;
- reviewed BOMs and dependency management;
- an appropriate dependency locking/verification strategy;
- scheduled or policy-governed snapshot checks;
- never assuming an old cache holds the newest snapshot.

When snapshots or metadata must be refreshed from remotes, use the appropriate Maven policy—such as `-U` when intentionally checking for snapshot/release metadata updates. Do not pass `-U` on every build unnecessarily, as it reduces cache effectiveness and increases network traffic.

### 6.4. Maven Build Cache Extension

The Maven local repository only caches downloaded artifacts. It does not automatically cache every `compile`, `test`, or `package` result the way Gradle's task output cache does.

When build output reuse is needed, Apache Maven provides the Maven Build Cache Extension. Current documentation requires Maven 3.9.0 or newer, including Maven 4. The extension can be declared in `.mvn/extensions.xml`:

~~~xml
<extensions>
    <extension>
        <groupId>org.apache.maven.extensions</groupId>
        <artifactId>maven-build-cache-extension</artifactId>
        <version>1.3.0</version>
    </extension>
</extensions>
~~~

Pin the extension version to a project-verified release. You can add `.mvn/maven-build-cache-config.xml` to customize file selectors, exclude temporary/environment files, and declare critical plugin parameters. A remote cache is optional and requires backend storage supporting get/put.

After enabling the extension, run a normal build and inspect the logs to confirm cache initialization. Check the module's `buildinfo.xml` to verify that source files and output-affecting plugin parameters are fingerprinted.

Do not treat this extension as a replacement for the Maven local repository. The two caches serve different goals:

- `~/.m2/repository`: avoids re-downloading already available dependencies/plugins;
- Maven build cache: avoids re-running lifecycle phases/plugin executions whose outputs are valid to restore.

## 7. Caching Metadata for Native Image and Spring AOT

### 7.1. Repository Metadata and Reachability Metadata Are Two Different Things

The word "metadata" can refer to very different data:

| Metadata type | Examples | Where it is cached |
| --- | --- | --- |
| Maven repository metadata | `maven-metadata.xml`, snapshot version mapping | Maven local repository/Resolver |
| Gradle module metadata | POM, `.module`, version/artifact descriptors | Gradle dependency cache |
| Spring AOT output | Generated initializers, sources, classes, and resources | Build output/task cache |
| GraalVM reachability metadata | Reflection, JNI, resource, serialization | Dependency JARs or source resources under `META-INF/native-image` |
| Native build metadata | Build arguments, toolchain, target, and build report | Build artifacts/logs; fingerprint relevant inputs |

Do not create a single shared "metadata cache" directory and copy metadata from all dependencies into it. Reachability metadata is tied to a specific library and version; metadata for a dependency can change when you upgrade its version.

### 7.2. Reachability Metadata in Dependencies

Native Image can read `reachability-metadata.json` from the classpath under:

~~~text
META-INF/native-image/<groupId>/<artifactId>/reachability-metadata.json
~~~

Metadata may live inside dependency JARs or in the application's source resources. When dependency JARs are stored in the Gradle/Maven dependency cache, the metadata inside the JAR is retained along with that artifact. The dependency/version cache key therefore determines the accompanying metadata as well.

If the application uses the GraalVM Reachability Metadata Repository via Native Build Tools, the plugin can download required metadata during native image generation. In Gradle, the `collectReachabilityMetadata` task can download metadata to `build/native-reachability-metadata`. If another packaging step needs that metadata, you can include the task output in the JAR per plugin guidance:

~~~kotlin
tasks.named("jar") {
    from(tasks.named("collectReachabilityMetadata"))
}
~~~

Only add this step when the pipeline genuinely needs repository metadata packaged into the JAR—for example, when a buildpack or a separate downstream system performs Native Image compilation later. If the Gradle plugin runs the native build directly, you do not need to repackage metadata just to create an extra copy.

### 7.3. Which Inputs Invalidate Metadata Caches?

At a minimum, consider:

- dependency coordinates and versions;
- GraalVM Native Build Tools version;
- GraalVM/JDK version;
- application-managed metadata files;
- Native Image options;
- target OS/architecture and ABI if metadata/build outputs depend on them;
- Spring Boot version, AOT output, and classpath.

Metadata inside JARs is versioned alongside the dependency. Custom files in `src/main/resources/META-INF/native-image` are source inputs, so they must be included in source/build fingerprints. Do not reuse generated metadata from another branch if the dependency graph or native build flags differ.

### 7.4. Caching Spring AOT Output

Spring AOT generates sources, classes, and resources. These outputs depend on the classpath and conditions evaluated at build time. For example, a profile or property that alters the bean graph can produce different outputs.

Use Gradle/Maven task/build caching only when the task declares complete inputs. Do not cache the generated output directory separately by source hash alone. If an AOT profile, system property, or environment variable affects bean conditions without being in the cache key, the build can restore an incompatible initializer.

For multiple AOT variants, separate output directories or cache namespaces by profile/target. Never allow two concurrent jobs to write to the same generated output directory.

## 8. Caching Cloud Native Buildpacks

### 8.1. Build Cache, Launch Cache, and Workspace

The Spring Boot Maven/Gradle plugin uses Cloud Native Buildpacks to create OCI images. Buildpacks split an application into layers; caches are managed separately:

| Component | Purpose | Behavior |
| --- | --- | --- |
| Build cache | Stores layers used while building the image | Allows buildpacks to reuse dependency/build layers across builds |
| Launch cache | Stores layers related to launching the image | Used by the buildpack lifecycle when creating/launching the image |
| Build workspace | Temporary files used by builder/buildpacks during the build | Not a long-term output cache; needs its own workspace lifecycle |
| OCI image layers | Layers of the resulting image | Can be reused by container registries/daemons by digest |

This is not the same cache as Gradle/Maven. Buildpack caches are managed by the lifecycle and buildpacks; do not manually unpack, modify, or stitch layers together.

### 8.2. Default Volume Names Can Invalidate Caches

By default, the Spring Boot plugin derives cache volume names from the full image name. If the image tag changes per version or commit, the volume name can also change and previous caches will not be reused.

Use stable volume names per application and platform, while separating caches between untrusted environments and release environments:

- cache names must not embed commit SHAs;
- partition by application, architecture, and builder/stack when needed;
- do not share writable caches between untrusted pull requests and release pipelines;
- proactively purge caches when the builder/stack or layer format is no longer compatible.

### 8.3. Configuring Gradle Buildpack Caching

Kotlin DSL example:

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootBuildImage

tasks.named<BootBuildImage>("bootBuildImage") {
    imageName.set("registry.example.internal/billing-service:ci")

    buildCache {
        volume {
            name.set("billing-service-linux-amd64.build")
        }
    }
    launchCache {
        volume {
            name.set("billing-service-linux-amd64.launch")
        }
    }
}
~~~

The volume names in this example stay stable across commits. If building both x86-64 and ARM64, use separate cache volumes per architecture. If changing the builder image or stack, consider rotating the cache namespace to avoid reusing incompatible layers.

If a runner uses an ephemeral Docker daemon, named volumes disappear when the runner is destroyed. You can use a bind mount on a runner with persistent disk or configure the build cache as an OCI image pushed/pulled via a registry:

~~~kotlin
tasks.named<BootBuildImage>("bootBuildImage") {
    buildCache {
        image {
            name.set("registry.example.internal/cache/billing-service:build")
        }
    }
}
~~~

Spring Boot supports build cache images for sharing caches across hosts. The launch cache and build workspace still have their own lifecycles; do not assume configuring a build cache image alone persists all buildpack data.

### 8.4. Configuring Maven Buildpack Caching

Maven plugin example with named volumes:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <image>
            <buildCache>
                <volume>
                    <name>billing-service.build</name>
                </volume>
            </buildCache>
            <launchCache>
                <volume>
                    <name>billing-service.launch</name>
                </volume>
            </launchCache>
        </image>
    </configuration>
</plugin>
~~~

You can configure the build cache using an image for cross-host sharing:

~~~xml
<image>
    <buildCache>
        <image>
            <name>registry.example.internal/cache/billing-service:build</name>
        </image>
    </buildCache>
</image>
~~~

Place this configuration inside `<configuration>` of `spring-boot-maven-plugin`. If configuring both build cache and launch cache, keep both blocks inside the same `<image>` element.

### 8.5. Builder, Run Image, and Buildpacks Are Also Inputs

Buildpack caches do not guarantee compatible outputs if the builder or buildpacks change. Pin:

- builder image by version or digest;
- run image by version or digest;
- buildpack order and versions;
- buildpack environment variables such as `BP_NATIVE_IMAGE`, `BP_JVM_VERSION`, and related flags;
- target architecture and OS;
- Spring Boot plugin version.

If the buildpack produces a Native Image, native compiler flags, GraalVM version, libc, and target architecture must also match. Never reuse an x86-64 native executable on ARM64 or a glibc binary on a musl runtime just because of a cache hit.

## 9. GitHub Actions with Maven and Buildpacks

Example Maven pipeline with dependency caching and buildpack named volumes:

~~~yaml
name: Native image container

on:
  push:
  pull_request:

jobs:
  package:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v5
        with:
          distribution: temurin
          java-version: '21'
          cache: maven
          cache-dependency-path: |
            **/pom.xml
            .mvn/wrapper/maven-wrapper.properties
            .mvn/extensions.xml

      - name: Build OCI image
        run: ./mvnw -B -Pnative spring-boot:build-image
~~~

Buildpack named volumes live only within the lifecycle of the Docker daemon. If a fresh GitHub-hosted runner is provisioned for each job, volumes do not automatically carry over to the next runner. To share across runners, use a build cache image in a registry or a self-managed runner with persistent Docker storage.

If a workflow runs `package` followed by `build-image`, inspect the lifecycle to avoid running the same phase twice unnecessarily. `build-image` can fork the lifecycle to ensure `package` has run; in complex pipelines, choose the appropriate goals and configure execution order explicitly.

## 10. Caching in Multi-Stage Native Image Pipelines

A pipeline typically has these stages:

1. Resolve dependencies.
2. Compile and test on JVM.
3. Spring AOT processing.
4. Native Image compilation.
5. Build OCI image with buildpacks.
6. Container test and publish.

Not every cache should be shared across all stages:

| Stage | Appropriate cache | Condition |
| --- | --- | --- |
| Resolve dependencies | Gradle User Home or Maven local repository | Partition by OS/tool version/repository trust |
| Compile/test JVM | Gradle build cache or Maven Build Cache Extension | Deterministic task outputs, complete inputs |
| Spring AOT | Task/build cache | Profile, classpath, and build-time conditions included in fingerprint |
| Reachability metadata | Dependency cache and task output cache | Dependency/version and GraalVM plugin match |
| Native Image compile | Build cache if task supports it and fingerprint is complete; cache tool downloads | Separate by OS, architecture, libc, GraalVM, and compiler |
| Buildpack | CNB build/launch cache | Builder, buildpacks, app layers, and platform match |
| Container test | Usually consume image artifact by digest | Test the exact built image; do not restore old binaries |

For native compilation, do not assume the task can be safely cached across different environments. The native executable depends on OS, architecture, libc, compiler, and many toolchain components. Only enable remote output caching when the plugin/task supports it and output reusability has been verified.

## 11. Cache Security and Artifact Integrity

Caches can hold executables, class files, generated sources, metadata, and dependency artifacts. A poisoned cache can cause CI to execute outputs produced by an untrusted job.

Apply these principles:

- only trusted jobs may write to shared remote build caches used for releases;
- pull requests from forks must not push to shared caches;
- separate caches by repository, trust boundary, platform, and builder where appropriate;
- never cache files containing credentials such as Maven `settings.xml`, Docker `config.json`, or secrets;
- never persist configuration cache containing credentials unless encrypted via a supported mechanism;
- pin dependency/plugin/builder versions and verify checksums/signatures per policy;
- restrict read/write permissions on remote caches;
- set retention/eviction policies and monitor capacity;
- when cache poisoning is suspected, rotate the namespace/key and rebuild from trusted sources.

Never treat a cache as the final release source of truth. Released artifacts must have provenance, checksums/digests, and be produced by a controlled pipeline.

## 12. Measuring Cache Effectiveness

Caching does not automatically make a pipeline faster. Restoring, uploading, compressing, and decompressing caches also consume time and network bandwidth.

Track:

- cache hit/miss rates by cache type;
- restore and save durations;
- cache size and eviction rates;
- count of `FROM-CACHE` tasks;
- dependency resolution duration;
- Spring AOT and Native Image compilation durations;
- buildpack lifecycle duration;
- image layer reuse and image size;
- total pipeline duration from checkout to artifact.

Examples of how to interpret metrics:

| Observation | Likely meaning | Action |
| --- | --- | --- |
| High dependency cache hit rate, but build is still slow | Compile/test/native compilation dominates total time | Inspect build output cache and task profiling |
| Gradle build cache misses on every job | Cache key or task inputs changed; remote cache unused | Check task fingerprints and cache backend |
| Maven re-downloads plugins despite dependency cache | Plugin/version/repository metadata not cached or key misses relevant files | Check cache paths and `cache-dependency-path` |
| AOT task always re-runs | AOT inputs changed or task is not cacheable | Check profiles, arguments, and task outputs |
| Buildpack cache misses on every commit | Cache volume depends on image tag or daemon is ephemeral | Use stable volume names or a cache image |
| Cache restore takes longer than the build | Cache is too large or hit rate is low | Narrow cache scope, split caches, and re-measure |
| Native binary restored from cache fails on another runner | Cache is not partitioned by architecture/ABI/toolchain | Partition cache by target and rebuild |

Measure both cold builds and warm builds. Cold builds reveal the true cost when caches are empty; warm builds show the benefit once caches are populated. Report each stage separately instead of publishing only total duration.

## 13. Troubleshooting

| Symptom | Common cause | Remediation |
| --- | --- | --- |
| Gradle shows no `FROM-CACHE` | Task is not cacheable, inputs changed, or build cache is disabled | Check `org.gradle.caching`, task annotations, and fingerprints |
| Gradle cache hits, but output is wrong | Task under-declared inputs or reads un-fingerprinted environment | Fix task inputs/outputs; disable caching for non-deterministic tasks |
| Configuration cache misses repeatedly | Incompatible build logic or changing configuration inputs | Read the Gradle configuration-cache report and fix inputs |
| Maven downloads dependencies on every run | Wrong cache path, mismatched key, or runner fails to restore | Check `~/.m2/repository` and CI configuration |
| Maven Build Cache Extension does not work | Maven version too old, missing extension/config, or unreconciled plugin parameters | Check Maven 3.9+, `.mvn/extensions.xml`, logs, and `buildinfo.xml` |
| Maven uses stale snapshot | Local repository still holds old snapshot/metadata | Check repository policy and run an intentional update |
| Native Image misses metadata after cache hit | Dependency metadata changed or AOT/native task inputs incomplete | Rebuild from matching dependency graph and metadata versions |
| Buildpack always recreates layers | Image name/tag changes volume name or daemon does not persist volumes | Use stable cache volume names or a cache image |
| Buildpack reports invalid cache layer | Builder/buildpack/stack changed | Separate cache namespace or refresh cache cleanly |
| Image builds, but fails on target architecture | Cache/native artifact built for wrong platform | Partition caches by OS/architecture/ABI |
| Remote cache cannot be written | Job lacks push permissions or cache is read-only | Check branch policy and backend credentials/permissions |
| CI cache contains sensitive data | Accidentally cached settings/credentials/configuration state | Exclude files from cache, rotate secrets, and purge/refresh cache |

## 14. Step-by-Step Cache Setup Procedure

Assume a billing service uses Gradle, Spring AOT, GraalVM Native Image, and `bootBuildImage`.

**Step 1 — Inventory the caches**

- Gradle User Home for wrapper/dependencies.
- Gradle build cache for cacheable task outputs.
- Configuration cache if the build is compatible and it is needed.
- Reachability metadata tied to dependencies or task outputs.
- Buildpack build/launch caches.

**Step 2 — Fix the inputs**

- Pin Gradle Wrapper, JDK/GraalVM, Spring Boot, and Native Build Tools.
- Use dependency locking/version catalogs.
- Specify explicit AOT profiles and `native-image` arguments.
- Pin builder/run images and target architecture.

**Step 3 — Enable the dependency cache**

Add `gradle/actions/setup-gradle@v6` or `setup-java` with Maven caching. Run a cold build to warm the cache.

**Step 4 — Enable the build output cache**

Enable `org.gradle.caching=true` or the Maven Build Cache Extension. Inspect task hits/misses and verify outputs after a `clean` build.

**Step 5 — Verify AOT and reachability metadata**

Confirm cache fingerprints include profiles, classpath, dependency versions, plugins, and Native Image options. Run native tests to confirm metadata is included in the executable.

**Step 6 — Enable the buildpack cache**

Set stable build/launch volume names. On ephemeral runners, use a build cache image or persistent Docker daemon/storage.

**Step 7 — Verify trust boundaries**

Only the main branch/release pipeline has write access to shared caches. Untrusted PRs only read permitted caches.

**Step 8 — Measure cold/warm builds**

Compare dependency resolution, compile, AOT, native compile, and buildpack durations. Keep a cache only when actual time savings exceed restore/save overhead.

## 15. Pre-CI Caching Checklist

- [ ] Dependency cache, build output cache, configuration cache, and buildpack cache are clearly separated.
- [ ] Gradle Wrapper/Maven Wrapper and JDK/GraalVM versions are pinned.
- [ ] Cache keys reflect OS, architecture, build files, and dependency locks/versions.
- [ ] AOT profiles, arguments, and build-time conditions are declared as task inputs.
- [ ] Reachability metadata is versioned alongside dependencies or source resources.
- [ ] Generated AOT/native outputs are never cached under a branch-only key.
- [ ] Gradle build cache applies only to tasks with complete input/output declarations.
- [ ] Maven local repository is cached separately from the Maven Build Cache Extension.
- [ ] Maven Build Cache Extension is enabled only when Maven version and plugin configurations are compatible.
- [ ] Buildpack build cache and launch cache use stable names, partitioned by platform/trust boundary.
- [ ] Ephemeral runners have a strategy for persisting buildpack caches via a registry or durable storage.
- [ ] Builder/run images and buildpack versions are pinned.
- [ ] Credentials, tokens, and sensitive configs are never cached in plaintext.
- [ ] Only trusted runners have write access to remote caches.
- [ ] Cache hit/miss rates, restore/save times, and artifact correctness have been verified.
- [ ] Both cold builds and warm builds have been measured on the same target.
- [ ] The native executable is tested inside the final runtime container.

**Remember:** effective caching means caching the right inputs at the right layer. Gradle/Maven dependency caches store downloaded artifacts; build caches store task outputs with valid fingerprints; Spring AOT and reachability metadata depend on classpath/profiles/toolchains; buildpack caches retain layers according to the builder lifecycle. Separate caches, pin inputs, restrict write permissions, and verify outputs after cache hits so the pipeline runs faster while staying reproducible.

## References

- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): task output cache, local/remote build cache, and input/output declaration requirements.
- [Gradle — Gradle on GitHub Actions](https://docs.gradle.org/current/userguide/github-actions.html): `setup-gradle`, Gradle User Home caching, and CI cache configuration.
- [GitHub Actions — actions/setup-java](https://github.com/actions/setup-java): caching Maven/Gradle dependencies, wrappers, and JDKs in workflows.
- [Apache Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html): local/remote repositories and offline builds.
- [Apache Maven — Maven Build Cache Extension](https://maven.apache.org/extensions/maven-build-cache-extension/): Maven version requirements, extension setup, cache config, and remote cache.
- [Apache Maven — Repository Metadata](https://maven.apache.org/repositories/metadata.html): `maven-metadata.xml` and version/snapshot metadata.
- [Spring Boot Maven Plugin — Packaging OCI Images](https://docs.spring.io/spring-boot/maven-plugin/build-image.html): buildpack build/launch caches, workspaces, volumes, and cache images.
- [Spring Boot Gradle Plugin — Packaging OCI Images](https://docs.spring.io/spring-boot/gradle-plugin/packaging-oci-image.html): configuring `bootBuildImage` caches and the Docker daemon.
- [Spring Boot — Ahead-of-Time Processing](https://docs.spring.io/spring-boot/reference/packaging/aot.html): generated AOT code and conditions for running AOT-processed applications.
- [GraalVM Native Image — Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/): reflection, JNI, resource, and serialization metadata.
- [GraalVM Native Build Tools — Gradle Plugin](https://graalvm.github.io/native-build-tools/latest/gradle-plugin): Native Image integration, metadata repository, and metadata collection tasks.
