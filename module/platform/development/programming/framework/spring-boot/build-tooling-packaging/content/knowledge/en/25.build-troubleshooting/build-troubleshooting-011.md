# Resolving Stale Caches, Unregenerated Outputs, and Non-Reproducible Builds in Spring Boot

## 1. Goals and Diagnostic Principles

When code or dependencies are updated yet the JAR/image looks identical to the old version, generated files remain unchanged, or two builds of the same source yield different digests, the root cause can reside at several layers. A blanket `clean` command may make the symptom vanish temporarily without revealing where the bug actually lies.

This lesson uses **Java 17, Spring Boot 3.3.13**, Maven or Gradle, Docker BuildKit, and Cloud Native Buildpacks (CNB). Versions are chosen for illustration; real projects should verify against their actual plugins, wrappers, and builders. Commands below serve as instructions rather than output from an executed build.

Upon completion, you will be able to:

1. Distinguish dependency caches, task-output caches, incremental build state, Docker layer caches, CNB caches, and runtime caches.
2. Identify why Maven/Gradle skipped re-running a required task or goal.
3. Verify which JAR/WAR/image file is actually produced and currently in use.
4. Fix tasks generating outputs with missing input/output declarations that cause Gradle to skip regeneration.
5. Refresh dependencies cleanly without wiping the entire local repository.
6. Verify whether a build is byte-for-byte reproducible and identify sources of divergence.

**Principle:** identify where the output is wrong, which task produces it, and which inputs affect that output. Only then pick a remediation.

## 2. Distinguishing Cache Types

| Mechanism | What It Stores | Symptoms | Scoped Refresh |
| --- | --- | --- | --- |
| Maven local repository | Resolved dependency/plugin artifacts and metadata. | Maven uses an old version or un-updated SNAPSHOT. | Inspect dependency tree; use `-U` purposefully; purge only the corrupted artifact. |
| Gradle dependency cache | Module dependency metadata and artifacts. | Dependency resolution uses stale metadata/version. | `--refresh-dependencies`; inspect locks and `dependencyInsight`. |
| Gradle incremental state | Task inputs/outputs state in the workspace. | Task shows `UP-TO-DATE` even though developer thinks inputs changed. | Fix input/output declarations; `--rerun-tasks` for diagnosis. |
| Gradle build cache | Cacheable task outputs, local or remote. | Task shows `FROM-CACHE` and restores previously built outputs. | `--no-build-cache` to test without cached outputs; `clean` deletes only project outputs. |
| Docker BuildKit cache | Results of Dockerfile instructions/layers. | A `RUN` step reuses old results even though an external package repo has a newer version. | `--no-cache` or `--no-cache-filter`; `--pull` to update base images. |
| CNB build cache | Cached layers contributed by buildpacks. | Image build restores old layers or fails to reuse cache. | Spring Boot plugin `cleanCache` or pack/CNB cache policy. |
| CNB launch layers/previous image | Layers reusable from a previous image or registry. | Image export reuses runtime layers when metadata matches. | Inspect previous image and metadata; do not confuse with build cache volumes. |
| Build workspace | Temporary files in builder/buildpacks. | Workspace volume bloats or retains stale temp files. | Manage workspaces per project/image and separate lifecycles. |
| Runtime cache | Redis, HTTP cache, local cache, sessions, app data. | New container still returns stale data despite the right image. | Investigate app cache contracts; do not run Maven/Gradle `clean`. |

### 2.1. Incremental Build vs. Build Cache

- **UP-TO-DATE:** Gradle compares task inputs/outputs in the current workspace and skips the task when there are no changes to process.
- **FROM-CACHE:** Gradle looks up task outputs by cache key and restores outputs from the local/remote build cache.
- **Dependency cache:** stores library metadata and binaries; it is not the output of compile/package tasks.
- **Configuration cache:** stores build configuration results; it does not cache JARs/classes.

Maven has a local repository for dependencies/plugins and a `clean` lifecycle to delete generated project outputs. Do not assume Maven shares Gradle's task-output cache model.

### 2.2. Stale Output Is Not Necessarily a Cache Bug

Common causes include:

- Inspecting a plain JAR instead of the Boot JAR, the wrong module, or the wrong build directory.
- The goal/task producing the artifact was never invoked or is absent from the lifecycle/task graph.
- A Maven profile is inactive, or a Gradle task is excluded or guarded by `onlyIf`.
- Generated sources/resources sit outside source sets or are not wired into `compile`/`processResources`.
- The app/container is still running an older image ID even though the tag was updated.
- The artifact was copied to a deploy folder before the build finished.
- The actual resolved dependency version differs from the version visible in the declaration file.
- Runtime cache or browser cache serves stale data while the binary is already updated.

## 3. Evidence-Based Diagnostic Workflow

Before clearing any cache, gather:

1. Git commit and working tree status.
2. Java/JDK, Maven, or Gradle Wrapper versions.
3. Build command, profiles, properties, and invoked tasks/goals.
4. Expected artifact name and path.
5. Whether the artifact exists, its size, modified time, and SHA-256.
6. Task outcomes or Maven plugin goals in logs.
7. Resolved dependency graph/versions.
8. If an image: image reference, immutable digest, container ID, and Docker context.
9. If suspecting reproducibility issues: logs and artifacts from two independent builds.

~~~bash
git status --short
git rev-parse HEAD
java -version
./mvnw -version
# Or:
./gradlew --version
~~~

Check actual output:

~~~bash
# Maven
ls -l target
sha256sum target/*.jar

# Gradle
ls -l build/libs
sha256sum build/libs/*.jar
~~~

On PowerShell, you can use `Get-ChildItem` and `Get-FileHash -Algorithm SHA256`. Do not hash paths that do not exist. Modified time alone is not sufficient proof: files can be copied preserving timestamps, archive timestamps can be normalized, or build tools can restore outputs from cache.

Inspect JAR contents:

~~~bash
jar tf target/release-demo.jar
~~~

For a Spring Boot executable JAR, look for `META-INF/MANIFEST.MF`, `org/springframework/boot/loader/`, `BOOT-INF/classes/`, and `BOOT-INF/lib/`. If you see `*-plain.jar`, that may be a plain Java archive not repackaged by Spring Boot.

## 4. Maven: Checking Lifecycle, Plugin Execution, and Dependencies

### 4.1. Phases and Goals

Maven has three main lifecycles: `clean`, `default`, and `site`. In the default lifecycle, common phases include:

- `validate`: validates the project.
- `generate-sources` / `generate-resources`: generates sources/resources.
- `process-resources`: copies/filters resources.
- `compile`: compiles main sources.
- `test-compile` / `test`: compiles and runs tests.
- `package`: packages JAR/WAR.
- `verify`: runs quality checks after packaging.

Running `mvn verify` executes preceding phases in order. Running `mvn compile` alone does not create a new packaged artifact. A plugin goal only runs if bound to a phase or invoked directly.

~~~bash
./mvnw --batch-mode clean verify
~~~

### 4.2. What Does `clean` Do and Not Do?

The Maven Clean Plugin deletes project output directories such as `target/`, classes, test classes, and reporting output by default. It **does not delete the entire Maven local repository** (`~/.m2/repository`), Docker/BuildKit caches, or CNB volumes.

If a generator writes outputs outside `target/`, `mvn clean` may not remove those files. Place generated outputs under `target/` or configure a dedicated fileset in the Maven Clean Plugin. Avoid scattering generated outputs across the source tree.

### 4.3. Checking Effective POM and Profiles

~~~bash
./mvnw help:active-profiles
./mvnw help:effective-pom -Doutput=target/effective-pom.xml
~~~

Read the effective POM to inspect plugin versions, execution/phase bindings, profiles, skip properties, `finalName`, output directory, classifiers, and resource filtering. A parent POM or `pluginManagement` may override configurations.

### 4.4. Debugging Skipped Goals

~~~bash
./mvnw --batch-mode -X clean package
~~~

`-X` produces very long debug logs; enable only when needed and avoid sharing logs containing credentials or sensitive repository URLs. Look for the relevant plugin/goal, invoked phase, skip messages, and output paths.

Common skip flags:

| Property | Typical Effect |
| --- | --- |
| `-DskipTests` | Skips running tests; typically still compiles test sources. |
| `-Dmaven.test.skip=true` | Skips both test compilation and execution. |
| `-Dspring-boot.repackage.skip=true` | Skips Spring Boot `repackage` if supported by the plugin version. |
| `-Dspring-boot.build-image.skip=true` | Skips the image build goal if supported by the plugin version. |

Verify property names against your project's plugin version. If a pipeline reports success yet tests/packaging/repackage/image builds did not run, inspect the command line and logs.

### 4.5. Stale Dependencies

~~~bash
./mvnw dependency:tree -Dverbose
./mvnw help:effective-pom
~~~

Check dependency mediation, exclusions, `dependencyManagement`, profiles, and repositories. The version in a single dependency declaration is not always the final resolved version.

When using SNAPSHOTs or repositories updated over time:

~~~bash
./mvnw -U clean verify
~~~

`-U` instructs Maven to check for updates to SNAPSHOTs and certain missing artifacts per the resolver. It **does not** force the compiler to recompile if outputs have not changed, and it does not delete all of `~/.m2`. If a local artifact is corrupted, locate its exact group/artifact/version and purge selectively; never wipe the entire local repository reflexively.

### 4.6. Generated Sources/Resources Missing

Verify generators are bound to the proper phase:

- Java source generators normally run in `generate-sources`.
- Resource generators normally run in `generate-resources`.
- Generated sources/resources must be registered in Maven compile/resource roots.
- `clean` should delete generated outputs so subsequent builds regenerate them.
- Generators run manually outside the lifecycle may not be invoked by CI.

Multi-module build:

~~~bash
./mvnw -pl :service-api -am clean verify
~~~

Replace `service-api` with the actual `artifactId`. `-pl` selects the module; `-am` also builds required dependent modules.

## 5. Gradle: Read Task Outcomes Before Deleting the Build Directory

### 5.1. Meaning of Task Outcomes

| Outcome | Meaning | How to Interpret |
| --- | --- | --- |
| `EXECUTED` or unlabeled | Task actions ran. | Inspect logs and output path. |
| `UP-TO-DATE` | Inputs/outputs are considered unchanged in the workspace. | If inputs actually changed, the task may have undeclared inputs or read the wrong file. |
| `FROM-CACHE` | Outputs were restored from the build cache. | Cache key matched previously stored outputs for those task inputs. |
| `NO-SOURCE` | No source inputs to process. | Check source sets and generated source dependencies. |
| `SKIPPED` | Task was skipped by condition/command. | Check `onlyIf`, `enabled`, `-x`, and skip properties. |
| `FAILED` | Task executed and failed. | Read the first failure and related dependency tasks. |

~~~bash
./gradlew clean build --info
./gradlew bootJar --dry-run
./gradlew tasks --all
./gradlew help --task bootJar
~~~

In multi-project builds, use full task paths like `:api:bootJar` or `:web:bootBuildImage` to avoid running the wrong subproject.

### 5.2. Diagnosing Up-To-Date and Build Cache Separately

~~~bash
./gradlew bootJar --rerun-tasks --no-build-cache --info
~~~

- `--rerun-tasks` bypasses up-to-date checks and forces the task graph to re-execute.
- `--no-build-cache` disables restoring task outputs from the Gradle build cache for that run.
- `clean` clears project outputs such as `build/`, without automatically deleting Gradle User Home or the remote build cache.

If forcing execution yields the right output, investigate why the task previously resolved as `UP-TO-DATE`/`FROM-CACHE`. Do not leave `--rerun-tasks` permanently in release pipelines to mask a broken task model.

### 5.3. Dependency Cache and `--refresh-dependencies`

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-core
./gradlew clean build --refresh-dependencies
~~~

`--refresh-dependencies` tells Gradle to refresh dependency resolution state. Gradle can still check checksums/metadata and keep existing artifacts if the repository confirms they have not changed; it does not mean re-downloading every JAR unconditionally.

Use it when dynamic/changing dependencies or repository metadata need refreshing. For fixed-version release dependencies, inspect the dependency graph and lockfiles before assuming a bad cache.

### 5.4. Custom Task Missing Input Declarations Causing Stale Output

Wrong example: a task creates `build-info.properties` from the project version yet declares only the output.

~~~groovy
tasks.register('generateBuildInfo') {
    def output = layout.buildDirectory.file('generated/resources/build-info.properties')
    outputs.file(output)

    doLast {
        def target = output.get().asFile
        target.parentFile.mkdirs()
        target.setText("version=¤{project.version}\n", 'UTF-8')
    }
}
~~~

If `project.version` changes yet Gradle is not informed that it is an input, the task may stay `UP-TO-DATE` and the file keeps the old version.

Fix: declare every value affecting output as an input, and declare outputs explicitly.

~~~groovy
def generatedResources = layout.buildDirectory.dir('generated/resources')

tasks.register('generateBuildInfo') {
    def output = generatedResources.map { it.file('build-info.properties') }

    inputs.property('appVersion', project.version.toString())
    inputs.file(layout.projectDirectory.file('src/main/templates/build-info.properties.template'))
    outputs.file(output)

    doLast {
        def target = output.get().asFile
        target.parentFile.mkdirs()
        def template = file('src/main/templates/build-info.properties.template').getText('UTF-8')
        target.setText(template.replace('@version@', project.version.toString()), 'UTF-8')
    }
}

sourceSets {
    main {
        resources.srcDir(generatedResources)
    }
}

tasks.named('processResources') {
    dependsOn tasks.named('generateBuildInfo')
}
~~~

Template `src/main/templates/build-info.properties.template`:

~~~properties
application.version=@version@
~~~

`appVersion` is an input property, the template is an input file, `build-info.properties` is an output file, and `processResources` depends on the generator. When the version/template changes, Gradle has grounds to re-run the generator.

If a task depends on environment variables, external files, JDKs/tools, or external systems, declare any values affecting output as inputs. Do not blindly declare every environment variable.

### 5.5. Overlapping Outputs and the Task Graph

Two cacheable tasks should not write to the same output directory/file unless designed to coordinate. Check:

- Is the producer task a dependency of the consumer task?
- Were generated sources/resources added to the source set?
- Does `dependsOn` target the right task path?
- Do `onlyIf`/`enabled`/`-x` skip the task?
- Are two tasks writing to the same file?
- Does the output path vary by project/module/profile?

Do not rely on command-line task ordering to implicitly ensure the producer runs before the consumer; declare explicit dependencies in the build graph.

## 6. Spring Boot Build Output and `build-info` Timestamp

### 6.1. Verify the Task/Goal Creating the Boot Archive

Maven:

~~~bash
./mvnw clean package
ls -l target/*.jar
jar tf target/release-demo.jar
~~~

Gradle:

~~~bash
./gradlew clean bootJar
ls -l build/libs/*.jar
jar tf build/libs/release-demo.jar
~~~

Filenames depend on `finalName`, `archiveFileName`, `classifier`, and module. Maven Spring Boot `repackage` turns the packaged archive into an executable archive; Gradle `bootJar` creates the Boot executable JAR. A project may simultaneously produce a plain JAR and a Boot JAR.

### 6.2. `build-info` Can Make Every Build Differ

Spring Boot Gradle `bootBuildInfo` includes `build.time` (the build timestamp) in `META-INF/build-info.properties` by default. Consequently, the task may always re-run and outputs vary. If prioritizing performance/reproducibility, exclude `time`:

~~~groovy
springBoot {
    buildInfo {
        excludes = ['time']
    }
}
~~~

Spring Boot Maven Plugin provides the `time` property and `excludeInfoProperties`. You can exclude `time`:

~~~xml
<configuration>
    <excludeInfoProperties>
        <excludeInfoProperty>time</excludeInfoProperty>
    </excludeInfoProperties>
</configuration>
~~~

This configuration belongs inside the `build-info` plugin execution. If release policy requires a timestamp, keep it and accept that the artifact changes over time; do not call two differing digests a cache bug when the cause is build metadata.

### 6.3. Resource Metadata and CNB

Paketo/Spring Boot buildpacks may normalize metadata such as `last-modified` timestamps on application resources to aid image caching/reproducibility. Do not let runtime logic depend on file timestamps inside archives/images if the buildpack can alter that metadata.

If static resource caching requires `Last-Modified`, inspect Spring Web resource handling configuration and buildpack behavior. Differing timestamps alone do not prove resource bytes changed.

## 7. Docker BuildKit: Instruction Caching Does Not Check Network State

### 7.1. Dockerfile Caching Rules

Docker inspects each instruction to decide whether to reuse a layer. For `COPY`/`ADD`, checksums depend on metadata/contents of referenced files; `mtime` alone is not used for invalidation. For `RUN`, Docker typically keys off the command string and preceding layer, and does not re-run a command merely because an external package repository now has a newer version.

~~~dockerfile
FROM eclipse-temurin:17-jdk
RUN apt-get update && apt-get install -y curl
COPY pom.xml .
RUN ./mvnw dependency:go-offline
COPY src ./src
RUN ./mvnw package
~~~

If `RUN apt-get update` hits cache, Docker does not automatically know the apt repository changed. To refresh the base image, use `--pull`; to bypass layer cache, use `--no-cache` or `--no-cache-filter` for a specific stage.

### 7.2. Diagnostic Commands

~~~bash
docker build -t demo:local .
docker build --pull -t demo:local .
docker build --no-cache -t demo:local .
docker build --pull --no-cache -t demo:local .
~~~

`--no-cache` does not imply pulling the latest base images; `--pull` is a separate flag. Combine both only when you need fresh base images and to re-execute Dockerfile instructions.

BuildKit supports `--no-cache-filter` to invalidate cache for a specific stage. Use it once you have identified which stage needs re-running, avoiding rebuilding unrelated stages.

### 7.3. Build Secrets Do Not Automatically Invalidate Cache

Secret mount contents do not participate in cache checksums. If a secret value changes while the command and other inputs remain unchanged, the `RUN` step may still hit cache. If results genuinely depend on a secret version, use a non-secret cache-version input changing with credential/config versions, or redesign so outputs do not depend on secrets. Never pass the secret itself in `ARG` just to bust cache.

### 7.4. `SOURCE_DATE_EPOCH` and Cache

Docker supports `SOURCE_DATE_EPOCH` to normalize timestamps for files/build metadata. A changing value can invalidate `WORKDIR` and subsequent instructions. If set to the Git commit timestamp, cache may miss on every commit; that is a trade-off between provenance timestamps and cache reuse.

Choose an explicit timestamp policy: a fixed value for reproducible artifacts across identical release inputs, or commit timestamps when provenance markers are needed and cache invalidation is acceptable.

## 8. Cloud Native Buildpacks: Build Cache, Launch Cache, and Workspace

Spring Boot Maven `spring-boot:build-image` and Gradle `bootBuildImage` use CNB to build OCI images. When an image does not reflect a new JAR or old layers are still reused, distinguish:

- **Build cache:** cached layers contributed by buildpacks for subsequent builds.
- **Launch layers / previous image:** layers reusable when metadata is compatible, including from images in a registry.
- **Build workspace:** temporary area where the builder/buildpacks operate.
- **Docker image store:** images/builders/run images pulled or built on the daemon.

Clear CNB cache for a single build:

Maven:

~~~bash
./mvnw spring-boot:build-image -Dspring-boot.build-image.cleanCache=true
~~~

Gradle:

~~~bash
./gradlew bootBuildImage --cleanCache
~~~

`cleanCache` affects buildpack caches for that image build. It does not wipe the Maven local repository, Gradle dependency cache, Docker BuildKit cache, all Docker images, or runtime application caches.

### 8.1. Image Name and Cache Identity

By default, Spring Boot plugins store CNB caches in Docker named volumes whose names derive from the full target image name. If the image tag changes per version/commit, the cache volume identity may also change and reduce reuse.

Inspect image name/tag, Docker context/daemon, builder/run image and buildpack versions, configured cache volume names, and analyze/restore/build/export logs. Do not prune all Docker volumes just because a single build missed cache.

### 8.2. A Stale Image May Come from a Stale Build Input

Before cleaning CNB cache, verify the input executable JAR is fresh: Maven ran `package`/`repackage`; Gradle ran `bootJar`; the plugin reads the right archive; no plain JAR was accidentally selected; the post-build image tag/digest is right; and the container was recreated from the new image.

If the input JAR is already stale, cleaning CNB cache cannot fix a Maven/Gradle layer bug.

## 9. Non-Reproducible Builds: Definition and Causes

A **reproducible build** is the ability to produce byte-for-byte identical artifacts given the same source code, build environment, and build instructions. Two files of the same version having different digests are not necessarily a cache bug; build timestamps, archive ordering, toolchains, or environment inputs may differ.

### 9.1. Common Sources of Divergence

| Source | Example | How to Control |
| --- | --- | --- |
| Timestamp | ZIP/JAR entry times, `build-info` time, generated file time. | Fixed output timestamp; exclude build time if unneeded. |
| File ordering | Entry order in JAR/ZIP depends on filesystem traversal. | Reproducible file order and deterministic packaging. |
| Toolchain | JDK vendor/patch, Maven/Gradle/plugin versions. | Pin Wrapper, JDK distribution/version, and plugin versions. |
| Dependency resolution | SNAPSHOTs, dynamic versions, version ranges, changing metadata. | Pin versions, dependency locking/verification, and repository policies. |
| Environment | Locale, timezone, OS, architecture, environment variables. | Standardize build container/toolchain; declare required inputs. |
| Workspace path | Generator embeds absolute paths in files/debug metadata. | Use relative paths or strip machine-specific paths. |
| Git metadata | Commit timestamp/hash or branch embedded in archive. | Define clear source metadata rules; avoid embedding unnecessary changing values. |
| Docker base image | `latest` tag or mutable tags. | Pin digest and builder/run image digests. |
| Network downloads | Package manager fetches newer versions from external repos. | Pin versions/checksums and use controlled mirrors. |
| Custom task | Task reads files/env without declaring inputs. | Declare complete inputs/outputs and deterministic task actions. |
| Build cache | Cacheable task with non-deterministic output or missing cache key input. | Fix task model; test no-cache and independent rebuilds. |

### 9.2. Gradle Archive Reproducibility

Gradle archive tasks support normalizing timestamps and file order:

~~~groovy
tasks.withType(org.gradle.api.tasks.bundling.AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

In Gradle 9, these values are already the defaults for Java plugin archive tasks; configuring them explicitly remains helpful to state policy or support older Gradle versions. Check whether other plugins generate their own archives.

### 9.3. Maven Reproducible Output Timestamp

Maven recommends setting the property:

~~~xml
<properties>
    <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

The value above is only a fixed example. In a release process, choose a timestamp per project policy. Ensure active archive plugins support reproducible builds; a Maven property cannot fix custom plugins that emit non-deterministic outputs.

You can use the Maven Artifact Plugin to check the build plan and compare artifacts:

~~~bash
./mvnw artifact:check-buildplan
./mvnw clean install
./mvnw clean verify artifact:compare
~~~

Comparing on the same machine catches basic differences yet does not prove an independent build is reproducible; rebuild from another workspace/environment.

### 9.4. Spring Boot `build-info` Time

Spring Boot Gradle `bootBuildInfo` generates `build.time` from the build instant by default. Thus the task may re-run and outputs vary. If reproducibility is required, exclude `time` via `springBoot.buildInfo.excludes`.

Maven `build-info` supports `time` and `excludeInfoProperties`; you can use `project.build.outputTimestamp` to supply a stable timestamp or disable `time` per plugin configuration. Do not demand bit-for-bit identity while embedding the current wall-clock timestamp inside the JAR.

### 9.5. Container Image Reproducibility

To improve reproducibility: pin builder/run images by digest, pin buildpack/dependency versions, control image metadata/created dates, normalize archive timestamps/order, specify architecture/platform, and avoid depending on uncontrolled changing network resources.

Images can have different digests even with identical JARs if base/run images or image metadata differ. Compare the JAR first, then compare image layers/config to pinpoint which layer diverged.

## 10. Distinguishing the Three Symptoms by Signs

| Symptom | Signs | First Diagnostic Focus |
| --- | --- | --- |
| Output not generated | File missing or task/goal absent from logs. | Task graph/lifecycle, profile, skip flags, output path, and generator binding. |
| Stale output retained | File exists yet content/digest fails to reflect new source/dependencies. | Wrong artifact path, `UP-TO-DATE`/`FROM-CACHE` task, undeclared input, source set, or stale image/container. |
| Non-reproducible build | Two clean builds on the same commit/toolchain yield different digests. | Compare JAR entries, timestamps, generated metadata, dependencies, environment, and base image digest. |

Missing outputs point to tasks/goals; stale outputs point to inputs/task graph; non-reproducible builds require comparing two independent builds.

## 11. Controlled Experiments: Change One Variable at a Time

### A. Baseline

1. Choose a commit and record `git rev-parse HEAD`.
2. Record Java/Maven/Gradle versions.
3. Record command, active profiles, build tasks/goals, and artifact paths.
4. Run a normal build and save logs.
5. Record JAR size/SHA-256 and image digest if applicable.

### B. Rebuild in Current Workspace

Maven:

~~~bash
./mvnw clean verify
~~~

Gradle:

~~~bash
./gradlew clean build --info
~~~

Compare output with baseline. If different, inspect which input changed (timestamps, generated `build-info`, dependency metadata) before blaming cache bugs.

### C. Force Task Re-Execution and Disable Gradle Build Cache

~~~bash
./gradlew bootJar --rerun-tasks --no-build-cache --info
~~~

If the new output is right, review task outcomes and input/output declarations. If output is still wrong, the cause may lie in sources, generators, plugins, or artifact paths.

### D. Refresh Dependency Resolution

Maven:

~~~bash
./mvnw -U clean verify
./mvnw dependency:tree -Dverbose
~~~

Gradle:

~~~bash
./gradlew clean build --refresh-dependencies
./gradlew dependencies --configuration runtimeClasspath
~~~

Compare resolved dependency versions before/after. Do not alter dependency versions in the same experiment when measuring cache behavior.

### E. Clean CNB Cache Once

Only after confirming the input JAR is fresh:

~~~bash
# Maven
./mvnw spring-boot:build-image -Dspring-boot.build-image.cleanCache=true

# Gradle
./gradlew bootBuildImage --cleanCache
~~~

Compare logs/layers with a normal build. If the image is still stale, inspect the input archive, builder image, output tag, and running container.

### F. Controlled Docker Layer Cache Clean

~~~bash
docker build --pull --no-cache -t demo:diagnostic .
~~~

If the new image is right while the normal build was stale, identify which instruction hit cache and which input that instruction failed to observe. Fix Dockerfile/input pinning; do not keep `--no-cache` as a permanent default workaround.

### G. Independent Reproducibility Check

Create two clean workspaces from the same commit, using identical locked JDK/build tool/dependencies:

~~~bash
git worktree add --detach ../repro-a <COMMIT_SHA>
git worktree add --detach ../repro-b <COMMIT_SHA>

cd ../repro-a
./mvnw clean verify
sha256sum target/release-demo.jar

cd ../repro-b
./mvnw clean verify
sha256sum target/release-demo.jar
~~~

Substitute the real `COMMIT_SHA` and artifact name. With Gradle, run `./gradlew clean bootJar --no-build-cache` in each workspace and compare `build/libs/*.jar`.

If digests differ, use `diffoscope`, `cmp`, `jar tf`, and inspect metadata. Ensure both workspaces share identical wrapper/JDK/dependency locks and no differing dynamic inputs. Independent rebuilds in separate containers/machines are stronger evidence than two builds in the same workspace.

## 12. Finding Divergence Inside the JAR

### 12.1. Compare Entry Lists

~~~bash
jar tf build-a/release-demo.jar > build-a.entries.txt
jar tf build-b/release-demo.jar > build-b.entries.txt
diff -u build-a.entries.txt build-b.entries.txt
~~~

If entry lists differ, check which resources/generated classes were added/dropped or whether archive ordering changed. If lists match, internal bytes can still differ.

### 12.2. Compare Metadata and Manifests

~~~bash
unzip -p build-a/release-demo.jar META-INF/MANIFEST.MF
unzip -p build-b/release-demo.jar META-INF/MANIFEST.MF
~~~

Check `Implementation-Version`, `Build-Time`, `Start-Class`, `Main-Class`, classpath, and custom attributes. If `META-INF/build-info.properties` includes `build.time`, two builds can differ purely because of timestamps.

### 12.3. Compare Bytecode

~~~bash
javap -classpath build-a/release-demo.jar -c com.example.demo.OrderService
javap -classpath build-b/release-demo.jar -c com.example.demo.OrderService
~~~

For executable Boot JARs, classes under `BOOT-INF/classes` may require extracting the archive or setting an appropriate classpath. `javap` reveals the actual bytecode inside the class rather than relying solely on source file timestamps.

### 12.4. Using `diffoscope`

`diffoscope` inspects nested archives and presents differences at the file/metadata level. It is helpful when two JARs differ in digest while having nearly identical entry lists. Run it in a secure environment because diff output can expose internal source/configuration.

## 13. Checking Whether Running Containers Use the New Image

Even after an image tag is rebuilt, existing containers can keep running the old image ID. A tag is a mutable pointer; a container is created from a specific image.

~~~bash
docker image inspect demo:local
docker ps --no-trunc
docker inspect <CONTAINER_ID>
~~~

Compare the current tag's image ID, the container's active image ID, container creation time, registry digest, and the endpoint being called. Once the new image is verified, recreate the container per deployment procedures. Do not wipe caches to fix traffic still hitting an old container.

## 14. Common Errors Table

| Symptom | Possible Cause | Action |
| --- | --- | --- |
| Maven `BUILD SUCCESS` yet JAR unchanged. | Only ran `test`/`compile`; `repackage` skipped; checking wrong artifact. | Run `clean verify`/`package`, inspect effective POM and JAR path. |
| Generated files remain after `mvn clean`. | Generator writes outside default output directories. | Move outputs into `target` or configure clean fileset. |
| Maven still uses old SNAPSHOT. | Update policy/metadata cache or repository lacks newer build. | Check dependency tree and repository; run `-U` purposefully. |
| Maven dependency version differs from declaration. | Dependency mediation, BOM, parent/profile, or transitive dependency. | `dependency:tree -Dverbose` and effective POM. |
| Gradle `UP-TO-DATE` despite version change. | Task lacks `inputs.property` for version. | Declare proper inputs and re-test. |
| Gradle `FROM-CACHE` returns stale output. | Cache key missing an input or non-deterministic task. | Fix task inputs/outputs, try `--no-build-cache` and `--rerun-tasks`. |
| Gradle `NO-SOURCE`. | Wrong source set or generated sources not created yet. | Check `sourceSets` and producer task dependencies. |
| Gradle `SKIPPED`. | `onlyIf` false, task disabled, or excluded via `-x`. | Check task configuration and command line. |
| Generated sources fail to compile. | Generator not wired to `compileJava`/source directory. | Declare `dependsOn`/`sourceSets` and output directory. |
| IDE build differs from CLI. | IDE uses different JDK/Gradle/Maven/profile/environment. | Compare toolchains, wrapper, active profiles, and command line. |
| Docker `RUN` reuses old packages. | `RUN` instruction cache hit; unchanged command skips network check. | Pin package versions or use `--no-cache-filter`/`--no-cache` to diagnose. |
| Docker base image still stale. | Base image tag served from local cache. | Use `--pull`; pin digests for releases. |
| Docker `COPY` does not invalidate on `mtime`-only change. | Docker does not key cache solely on `mtime`. | Check file bytes/metadata; do not touch files just to bust cache. |
| CNB image lacks new code. | Stale input JAR or build goal/task did not run. | Verify `package`/`bootJar` first, then inspect image. |
| CNB cache fails to reuse across tags. | Cache volume identity derives from full image name. | Configure stable cache volume names. |
| Two JARs differ in digest despite same code. | Timestamps, ordering, manifest/`build-info`, or environment metadata differ. | `diffoscope`, inspect archive metadata, normalize timestamp/order. |
| Two images differ in digest despite identical JAR. | Base/run image, builder, buildpack, or image metadata differ. | Compare image layers, builder/run digests, and created date. |
| Developer build passes, CI fails. | Differing JDK/OS/locale/env/dependency resolution or uncommitted generated output. | Compare toolchains/inputs, use wrapper and lock dependencies. |
| Clean build still uses old dependency. | Local/remote repository serves the same version. | Check checksum, repository URL, and resolved version; `clean` does not purge dependency repos. |
| Cache disabled yet output still stale. | Wrong build input/path, old app/container, or task never invoked. | Check commit, task graph, artifact digest, and container image ID. |
| Independent rebuilds do not match. | Non-deterministic task, timestamps, dynamic dependencies, environment leaks. | `diffoscope`, pin inputs/toolchain, normalize archives, and fix task. |

## 15. Safe and Scoped Cleaning

Before deleting a cache, note the exact cache directory/volume, owning tool/project/module, whether other jobs share it, whether data can be recreated, and whether the cache is shared across CI runners/remote caches.

| Goal | Command/Measure |
| --- | --- |
| Delete generated Maven output | `./mvnw clean` |
| Re-run Gradle task ignoring up-to-date | `./gradlew <task> --rerun-tasks` |
| Disable Gradle task build cache once | `./gradlew <task> --no-build-cache` |
| Refresh Gradle dependency resolution | `./gradlew <task> --refresh-dependencies` |
| Check Maven SNAPSHOT updates | `./mvnw -U <phase>` |
| Clean CNB buildpack cache once | Maven `cleanCache=true` or Gradle `--cleanCache` |
| Bypass Docker layer cache | `docker build --no-cache` |
| Pull newer base image | `docker build --pull` |

Never delete all of `~/.m2`, `~/.gradle`, Docker volumes, or remote caches on a shared runner merely to test a hypothesis. If a remote cache holds bad outputs, identify the cache key/task, fix the task model first, and then invalidate only the exact namespace/key per policy. Deleting an entry without fixing task inputs risks re-caching bad output.

## 16. Root-Cause Verification Checklist

### Source and Toolchain

- [ ] Recorded commit SHA and working tree status.
- [ ] Recorded Java/JDK, Wrapper, Maven/Gradle, and plugin versions.
- [ ] Identified profiles, environment, and build properties.
- [ ] Checked dependency versions from the resolved graph.

### Output Generation

- [ ] Identified the right module, goal/task, and output path.
- [ ] Plugin execution/task is present in the lifecycle/task graph.
- [ ] No unintended skip flags, `onlyIf`, or excluded tasks.
- [ ] Generated sources/resources are wired into `compile`/`processResources`.
- [ ] Custom tasks declare complete inputs and outputs.
- [ ] No overlapping output directories across tasks.

### Cache

- [ ] Distinguished dependency cache, Gradle task cache, Docker cache, and CNB cache.
- [ ] Checked task outcomes/logs before cleaning.
- [ ] Cleaned only the specific cache under test.
- [ ] Tested controlled no-cache/forced rerun if needed.
- [ ] Confirmed new output is not just an old file copied to a different location.

### Reproducibility and Runtime

- [ ] Both builds use the same source commit and build instructions.
- [ ] JDK/toolchain, plugins, and dependencies are pinned.
- [ ] Archive timestamps and file order are normalized.
- [ ] `build-info` timestamps/dynamic metadata are handled per policy.
- [ ] Docker base/builder/run images are pinned by digest when required.
- [ ] Compared digests and used `diffoscope`/entry inspection when diverging.
- [ ] Deployed JAR/image matches the right digest and running containers use the new image.
- [ ] Investigated runtime caches separately if responses remain stale.

## 17. Practice Exercises and Acceptance Criteria

### Exercise A — Stale Maven Output

1. Create a Java 17 Spring Boot Maven project with an endpoint returning a version string.
2. Build the JAR and record SHA-256.
3. Modify the response code and run `clean verify` or `clean package`.
4. Inspect `target/classes`, JAR manifest, and bytecode with `javap`.
5. Try running only `test` and explain why the packaged JAR may remain unchanged.
6. Check active profiles/effective POM and dependency tree.

### Exercise B — Gradle Task Missing Input

1. Create a custom task generating `build-info.properties` from `project.version`.
2. Declare only the output and run the first build.
3. Change the version and observe the task outcome.
4. Add `inputs.property('appVersion', project.version.toString())`.
5. Change the version again and confirm the task re-runs and the generated file updates.
6. Add the generated resources directory to the source set and wire the task into `processResources`.

### Exercise C — Distinguishing Dependency Cache and Task Cache

1. Build the Gradle app twice and observe `UP-TO-DATE`/`FROM-CACHE`.
2. Run `clean build --no-build-cache`.
3. Run `--refresh-dependencies` and compare the resolved dependency graph.
4. Explain why `clean`, `--no-build-cache`, and `--refresh-dependencies` affect different states.

### Exercise D — Stale Docker/CNB Image

1. Build a container image from a Spring Boot JAR.
2. Modify code, package a new JAR, and rebuild the image.
3. Check the image digest and container image ID.
4. Try `docker build --pull --no-cache` with a separate Dockerfile workflow.
5. For CNB, try `cleanCache` once after confirming the input JAR is fresh.
6. Record which layers/tasks rebuilt and why.

### Exercise E — Reproducible Build

1. Pin commit, JDK, wrapper, and dependency versions.
2. Create two independent workspaces from the same commit.
3. Build with task caches disabled and identical environments.
4. Compare JAR SHA-256 hashes.
5. If different, use `diffoscope`, `jar tf`, manifest/`build-info`, and archive timestamps to find the cause.
6. Normalize output timestamps/file order and repeat.
7. If comparing container images, pin builder/run/base image digests and compare the JAR separately from image layers.

**Acceptance criteria:** learners can explain a case where output fails to regenerate, prove which task/goal was skipped or hit cache, fix a missing input/output declaration, distinguish dependency caches from task-output/image caches, and perform two independent clean builds to evaluate reproducibility. If Docker/CNB or an isolated environment has not been run yet, document the verification limitation; do not mark cache/reproducibility as PASS based solely on one successful build.

## Official References

- [Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Maven Clean Plugin — clean:clean](https://maven.apache.org/plugins/maven-clean-plugin/clean-mojo.html)
- [Maven Clean Plugin — FAQ](https://maven.apache.org/components/plugins/maven-clean-plugin/faq.html)
- [Maven — Configuring for Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html)
- [Gradle — Understanding Tasks and Task Outcomes](https://docs.gradle.org/current/userguide/more_about_tasks.html)
- [Gradle — Incremental Builds](https://docs.gradle.org/current/userguide/incremental_build.html)
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html)
- [Gradle — Solving Common Caching Problems](https://docs.gradle.org/current/userguide/common_caching_problems.html)
- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html)
- [Gradle — Dependency Caching](https://docs.gradle.org/current/userguide/dependency_caching.html)
- [Gradle — AbstractArchiveTask](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.bundling.AbstractArchiveTask.html)
- [Spring Boot 3.3 — Maven Plugin: Packaging OCI Images](https://docs.spring.io/spring-boot/3.3/maven-plugin/build-image.html)
- [Spring Boot 3.3 — Gradle Plugin: Packaging OCI Images](https://docs.spring.org/spring-boot/3.3/gradle-plugin/packaging-oci-image.html)
- [Spring Boot — Maven build-info](https://docs.spring.io/spring-boot/3.3/maven-plugin/build-info.html)
- [Spring Boot — Gradle build-info and Actuator](https://docs.spring.io/spring-boot/3.3/gradle-plugin/integrating-with-actuator.html)
- [Cloud Native Buildpacks — Caching Strategies](https://buildpacks.io/docs/for-buildpack-authors/concepts/caching-strategies/)
- [Docker — Build Cache Invalidation](https://docs.docker.com/build/cache/invalidation/)
- [Reproducible Builds — diffoscope](https://diffoscope.org/)

**Remember:** `clean` handles only generated outputs within the build tool's scope; dependency caches, Gradle task caches, Docker layer caches, and CNB caches are separate mechanisms. When output is stale, trace it back to the task/goal, inputs, and artifact path. When two builds diverge, compare from the JAR up to the image, normalize timestamps/toolchains/dependencies, and rebuild in an independent environment to prove reproducibility.