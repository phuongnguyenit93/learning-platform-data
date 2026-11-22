# Reproducible Module Images and Build Cache

## 1. What Is a Reproducible Build?

A build is considered reproducible when the same source revision and the same set of declared inputs produce equivalent outputs according to chosen criteria. For packagable artifacts, the strongest goal is producing identical byte-for-byte contents when rebuilt in a controlled environment.

For the Java Platform Module System (JPMS), reproducibility needs to cover both module JARs and runtime images built with \`jlink\`. The result depends on many factors:

- Source code, resources, \`module-info.java\`, and generated sources.
- JDK version, vendor, compiler, and the \`jlink\` tool.
- Gradle/Maven version, build plugins, and dependency artifacts.
- Module path, dependency graph, service providers, and linker options.
- Operating system, CPU architecture, native libraries, and build environment.
- Timestamps, file ordering, locale, timezone, and environment variables used during the build.

If one of these inputs changes without the build tracking it, two builds can produce different images even from the same source revision. When that happens, a cache may return stale output or CI may produce artifacts different from a developer's machine.

**Reproducible** does not merely mean a build succeeds twice. You must define the comparison criteria: same dependency graph, same module list, same class/resource contents, same manifest hash, or identical bytes across the entire release package.

## 2. Distinguishing Gradle's Cache Types

Gradle has multiple caching mechanisms for different purposes. Do not refer to all of them collectively as the build cache.

| Mechanism | Stored Content | Effect |
| --- | --- | --- |
| Dependency cache | Downloaded dependency metadata and artifacts | Avoids re-downloading dependencies from repositories. |
| Build cache | Task outputs keyed by inputs and task implementation | Can restore outputs of previously executed tasks. |
| Configuration cache | Build configuration result and task graph | Reduces configuration time on subsequent runs. |
| Incremental build | Task input/output state in the workspace | Skips a task when inputs/outputs have not changed. |

### 2.1. Dependency Cache

Gradle stores metadata and artifacts downloaded from Maven/Ivy repositories. When running offline:

~~~bash
./gradlew --offline build
~~~

Gradle only uses dependencies already present in the local cache. If a required artifact or metadata is not cached yet, the build fails. Offline mode does not restore outputs from previously executed tasks; it only restricts repository access.

The dependency cache does not replace dependency locking or verification. If you declare dependencies with dynamic versions such as \`1.+\`, resolution results can change over time and with repository metadata.

### 2.2. Build Cache

The build cache stores outputs of cacheable tasks. When a task has the same implementation and the same declared inputs, Gradle can fetch outputs from the cache instead of executing the task.

Enable the build cache:

~~~bash
./gradlew --build-cache build
~~~

Or configure it in \`gradle.properties\`:

~~~properties
org.gradle.caching=true
~~~

The build cache is useful for compile, test, or packaging tasks when tasks are modeled properly and outputs can be reproduced from declared inputs.

A task only runs faster on a cache hit. If inputs change, the task implementation changes, or the task is not cacheable, Gradle must execute the task.

### 2.3. Configuration Cache

The configuration cache stores the build configuration result to reduce time spent on configuration steps in subsequent runs:

~~~bash
./gradlew --configuration-cache build
~~~

The configuration cache does not store task outputs. The build cache stores task outputs. Both mechanisms can be used together:

~~~bash
./gradlew --configuration-cache --build-cache build
~~~

If a build script or custom task is incompatible with the configuration cache, Gradle reports issues when saving or reusing configuration state. Address those issues following Gradle's guidance rather than assuming the configuration cache will fix tasks with undeclared inputs/outputs.

## 3. Locking Toolchains and Dependencies

To make builds reproducible, control tool and dependency versions before optimizing caches.

### 3.1. Gradle Wrapper

Commit the Wrapper files to the repository and pin the Gradle version. In \`gradle/wrapper/gradle-wrapper.properties\`, declare a specific distribution and checksum:

~~~properties
distributionUrl=https\\://services.gradle.org/distributions/gradle-8.5-bin.zip
distributionSha256Sum=<verified-sha256-of-the-distribution>
~~~

Replace the placeholder with the official verified checksum of the chosen distribution. Do not invent or guess a checksum. The Wrapper ensures developers and CI use the same Gradle version, while the checksum protects the integrity of the downloaded distribution file.

### 3.2. Java Toolchain and Release Target

Declare a toolchain instead of relying on whatever Java happens to be on PATH:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
        // You can specify a vendor if the organization requires a specific JDK vendor.
    }
}
~~~

Set the release target for the compiler:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.release = 21
}
~~~

The toolchain selects the JDK executing compilation/tests according to configuration. \`options.release\` constrains the target API and bytecode. The two settings serve different purposes; do not rely solely on \`JAVA_HOME\` on developer machines.

If the build creates a runtime image, lock the JDK containing \`jlink\` and the module files in \`jmods\` as well. The same major version 21 does not guarantee byte-for-byte identity if vendors or patch releases differ.

### 3.3. Locking Dependency Versions

Avoid dynamic versions and version ranges for release dependencies. Use dependency locking to record resolved versions:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Generate or update lock state with:

~~~bash
./gradlew dependencies --write-locks
~~~

Commit the lockfiles generated by Gradle. When the dependency graph changes intentionally, update lock state in a reviewed change.

### 3.4. Verifying Dependency Artifacts

Dependency locking controls which versions are resolved; dependency verification checks the contents of downloaded artifacts. You can initialize checksum metadata:

~~~bash
./gradlew --write-verification-metadata sha256 help
~~~

Review \`gradle/verification-metadata.xml\` and commit it. Do not blindly trust every new checksum without verifying the source and dependency change. CI should enforce verification to catch unexpected artifact tampering or changes.

For Gradle plugins, also pin plugin versions in \`plugins { }\` or a version catalog. Build logic and plugins are inputs to artifact creation, so plugin versions should not drift with repository updates.

## 4. Making Archive Outputs Deterministic

A JAR is an archive. If entry order or timestamps change, two JARs can differ in bytes even when classes/resources are identical.

For Gradle archive tasks:

~~~groovy
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

This configuration strips original file timestamps from the archive and enforces a stable entry order. It helps make JARs/ZIPs produced by supported archive tasks more consistently comparable.

However, this is not the sole guarantee of reproducibility. Manifests, generated resources, build metadata, plugins, the JDK, and custom tasks can still write timestamps or environment-dependent content into outputs.

Do not write the current time, absolute paths, or build machine hostnames into packaged resources unless those values are intentional inputs. If a build version or commit ID is needed, make it an explicit input and standardize how it is generated.

## 5. Building a Runtime Image with jlink

Example building an image from the application module and its dependent modules:

~~~bash
jlink \\
  --module-path "$JAVA_HOME/jmods:build/mods" \\
  --add-modules com.acme.app \\
  --bind-services \\
  --launcher app=com.acme.app/com.acme.app.Main \\
  --output build/runtime-image
~~~

Key inputs to control:

- JDK distribution containing \`jlink\` and the \`jmods\` directory.
- All modular JARs/exploded modules on the module path.
- Root modules in \`--add-modules\`.
- Service declarations and the \`--bind-services\` choice.
- Launcher name, main module/class, and linker options.
- Target OS, CPU architecture, and native environment.

\`jlink\` produces a platform-dependent image. Do not substitute a Linux runtime image for a Windows image or an image for another CPU architecture. Build the image on a JDK matching the target and test that image in the corresponding environment.

Size can be reduced with options such as:

~~~bash
--strip-debug
--no-header-files
--no-man-pages
--compress=2
~~~

Enable these options only after identifying runtime requirements and testing that the application still works. If the application uses locale data, fonts, service providers, or dynamically loaded modules, ensure the image still contains all required components.

### 5.1. Locking the Module Set

Use \`--add-modules\` with an intentional set of root modules and let the linker resolve dependencies. When the application uses service providers, verify that consumer modules declare \`uses\` and providers declare \`provides\`; \`--bind-services\` helps link observable providers on the module path.

Do not take a module list from an arbitrary run and hard-code it without understanding why. Modules used via reflection, JDBC drivers, logging providers, or plugins may not appear in a static dependency graph in an obvious way. Test realistic functional flows and configurations.

### 5.2. Verifying the Image

After linking:

~~~bash
build/runtime-image/bin/java -version
build/runtime-image/bin/java --list-modules
~~~

Use the Java executable inside the image. Invoking \`java\` from PATH may end up testing a different JDK on the build machine.

Test the launcher:

~~~bash
build/runtime-image/bin/app
~~~

Verify module resolution, service discovery, configuration, native dependencies, and minimal business flows. A successful image build only proves the linker produced output; it does not prove the image is production-ready.

## 6. Reproducibility of the Runtime Image

For two runtime image builds to be comparable, every linker input and module-path preparation step must be pinned.

A set of inputs to track:

| Input | How to Control |
| --- | --- |
| Source revision | Record commit SHA and working tree state. |
| Gradle distribution | Use a pinned Wrapper version and verified checksum. |
| JDK | Pin vendor, version/update, and platform. |
| Dependencies | Use lockfiles and dependency verification. |
| Module artifacts | Record hashes of each input modular JAR or artifact. |
| jlink arguments | Manage in build logic, not entered manually per environment. |
| OS/architecture | Separate caches/images by target platform. |
| Environment | Pin variables that affect generated content. |
| Output | Generate into a clean directory and compare manifest hashes. |

Do not claim all \`jlink\` outputs are byte-for-byte identical across different JDK vendors, patch releases, or OSes. Establish reproducibility within the same toolchain/platform first; if cross-platform comparison is needed, compare meaningful properties such as module list, versions, configuration, and behavior rather than expecting identical raw bytes.

### 6.1. Generating a Manifest Hash

You can generate a file list and SHA-256 digests to compare two images. Example on Linux:

~~~bash
find build/runtime-image -type f -print0 \\
  | sort -z \\
  | xargs -0 sha256sum > runtime-image.sha256
~~~

This manifest records file contents. If file modes, symbolic links, or other metadata also need verification, include those attributes in the manifest per project conventions.

To compare two images, generate manifests via the same process and diff them:

~~~bash
diff -u image-a.sha256 image-b.sha256
~~~

If hashes differ, locate the first differing file and identify the input that produced it. Do not compare only directory sizes, since two images can have the same size with different contents.

On Windows, use PowerShell to list files and \`Get-FileHash -Algorithm SHA256\`; normalize relative paths and ordering before generating the manifest.

## 7. Integrating the jlink Task into the Gradle Build Cache

Gradle can only cache outputs safely when a task declares complete inputs and outputs. For a custom task that creates a runtime image, model at minimum:

- Module artifacts and JDK \`jmods\` as file inputs.
- The \`jlink\` executable or toolchain identity as an input.
- Module names, launcher, linker arguments, OS/architecture, and options as scalar inputs.
- The runtime image directory as output.
- Task implementation and build logic as part of the cache key.

A custom task can use \`@CacheableTask\` when outputs truly depend only on the declared inputs. File input properties should declare appropriate path sensitivity; relative paths are typically used when absolute workspace paths do not affect results.

Example of a task input/output contract:

~~~kotlin
@CacheableTask
abstract class LinkRuntimeImage : DefaultTask() {
    @get:InputFiles
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val moduleArtifacts: ConfigurableFileCollection

    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val jlinkExecutable: RegularFileProperty

    @get:Input
    abstract val jlinkArguments: ListProperty<String>

    @get:Input
    abstract val targetPlatform: Property<String>

    @get:OutputDirectory
    abstract val imageDirectory: DirectoryProperty
}
~~~

This is the contract declaration; the task implementation must run the exact executable, use the declared module artifacts, and write output inside \`imageDirectory\`. If the toolchain depends on other JDK files such as \`jmods\`, declare them as inputs or model an equivalent toolchain input sufficient for the cache key to change when the JDK changes.

Do not declare only an executable path or JDK version string while ignoring toolchain contents. Two JDKs with the same version string but different vendors/builds can produce different outputs.

### 7.1. When Should a Task Not Be Cached?

Do not cache a task if it has side effects not represented in its outputs, such as:

- Sending requests or writing data to external systems.
- Reading real-time state without declaring inputs.
- Producing output dependent on random values or current timestamps.
- Writing to a directory outside the declared output directory.
- Relying on undeclared environment variables or configuration files.
- Producing different images per build machine while the cache key does not distinguish platform/toolchain.

A cache hit means Gradle skips the action and restores saved outputs. If the task also has side effects that must occur on every run, caching can cause incorrect behavior. Separate pure artifact-building tasks from deploy/publish tasks that have side effects.

## 8. Avoiding Broken Cache Keys or Unnecessary Cache Misses

### 8.1. Declare All Inputs

Every value capable of changing the output must be declared. For an image-building task, do not omit:

- Contents of module JARs and resources.
- Module path ordering if order is significant.
- JDK executable and JDK modules.
- Linker arguments.
- Environment variables affecting output.
- OS/architecture if output is platform-dependent.

If an input is missing, Gradle may return stale output for a build whose result should have differed. This is a cache correctness bug, more dangerous than a cache miss because the build still appears to succeed.

### 8.2. Avoid Unstable Inputs

Do not include absolute workspace paths, build timestamps, or machine hostnames in inputs if they do not affect output contents. Use proper relative path normalization so identical source checkouts in different directories can still reuse the cache.

However, never strip a path from the cache key if the output genuinely depends on that location. Path sensitivity must accurately reflect the task's semantics.

### 8.3. Outputs Must Be Produced Deterministically

The task must write outputs to the declared location, delete or replace old outputs according to clear rules, and leave no stale files behind. Do not write extra logs, temporary files, or generated artifacts outside the output directory unknown to Gradle.

If a task uses an output directory, ensure the final contents reflect only the inputs of the current run. A leftover stale file can make an image look complete even though the current task did not produce it.

## 9. Local and Remote Build Cache

The local build cache is useful when developers rebuild on the same machine. A remote build cache enables CI and multiple developers to share cached task outputs.

Example remote HTTP cache configuration in \`settings.gradle\`:

~~~groovy
buildCache {
    remote(HttpBuildCache) {
        url = uri("https://cache.example.internal/cache/")
        push = false
    }
}
~~~

Trusted CI can be configured to push:

~~~groovy
buildCache {
    remote(HttpBuildCache) {
        url = uri("https://cache.example.internal/cache/")
        push = System.getenv("CI") == "true"
    }
}
~~~

This is illustrative only; endpoints, authentication, and push/pull permissions must follow your organization's cache infrastructure. Do not hard-code credentials in the repository. Use a secret store or authentication mechanism supported by your build infrastructure.

A common pattern:

- CI on trusted branches builds and pushes to the cache.
- Pull requests can read from the cache but cannot write to the shared cache if contributors are untrusted.
- Developers read the remote cache and use the local cache for their own outputs.
- Cache retention and capacity are managed to avoid unbounded growth.
- Cache keys include platform/toolchain so Linux and Windows images do not mistakenly reuse each other's outputs.

A remote cache is a source of build artifacts. Permit only trusted writers; if an untrusted actor can write arbitrary outputs to the shared cache, other builds could restore unwanted artifacts.

## 10. Verifying the Cache Works Correctly

Run the first build:

~~~bash
./gradlew --build-cache clean build
~~~

Run again:

~~~bash
./gradlew --build-cache build
~~~

Gradle may display tasks restored from cache with the \`FROM-CACHE\` outcome. An \`UP-TO-DATE\` task means existing workspace outputs are still valid; it is not the same as a cache hit.

To verify cache correctness, change each key input one at a time and confirm the task must re-run:

- Modify a class/resource in an input module.
- Change a linker argument.
- Change the JDK/toolchain.
- Change the module set or service providers.
- Change the target OS/architecture.

After each change, verify the task does not restore output from the old inputs. When reverting to the original inputs, the cache can hit again if the corresponding key and output still exist.

Do not judge a cache solely by faster builds. Confirm that output after a cache hit matches the output of an actual execution with the same inputs.

## 11. Testing Reproducibility in CI

A pipeline can produce two independent outputs from the same commit in two clean workspaces:

1. Resolve dependencies using lockfiles and verification.
2. Use the exact Gradle Wrapper and JDK toolchain.
3. Build module JARs.
4. Create the runtime image from the same module set and jlink arguments.
5. Generate manifest hashes of the JARs and runtime image.
6. Compare the two manifests.
7. If they differ, archive the manifests and toolchain logs to identify omitted inputs.
8. Run smoke/integration tests on the image after verifying contents.

You can use two runners with the same OS/architecture and the same toolchain to check bit-for-bit identity. If runners differ, define upfront which properties must match and which are permitted to differ.

CI should also include a periodic build job with the build cache disabled to cross-check real outputs against cached outputs. This catches tasks with missing input declarations or stale cache entries. You do not need to disable caching on every build; you just need an independent verification path.

## 12. Diagnosing Reproducibility and Cache Failures

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| Two JARs have different hashes despite identical classes | Different timestamps, archive order, or manifests | Pin archive timestamps/order and inspect resource metadata. |
| Two runtime images have different module lists | Different JDK/module path or service binding | Compare JDK, module artifacts, \`--add-modules\`, \`--bind-services\`. |
| Cache hit yet wrong output | Task missing inputs or output has side effects | Check task annotations, inputs/outputs, and cache key. |
| Task always re-runs | Input path/metadata changes or task is not cacheable | Inspect build scan/task outcome and normalize inputs appropriately. |
| Developer hits cache, CI misses | Different toolchain, OS, absolute path, or plugin | Compare cache key inputs and build environment. |
| Offline build fails | Dependency not yet in dependency cache | Run online to download and verify locked dependencies. |
| Configuration cache cannot be reused | Build logic incompatible or configuration input changed | Read configuration cache problems report and fix build logic. |
| Runtime image missing provider | Module/provider not linked or different module path | Check \`uses\`, \`provides\`, \`--bind-services\`, and module list. |
| Image only runs on build machine | Image mismatches target OS/architecture or lacks native dependencies | Build/test on the target platform. |
| Remote cache contains untrusted output | Push permissions too broad | Restrict writers, authenticate sources, and isolate caches by trust boundary. |

## 13. Recommended Workflow for Cached Module Images

1. Lock Gradle Wrapper, plugins, JDK vendor/version, and dependency versions.
2. Enable dependency verification and commit lockfiles.
3. Configure archive tasks to strip unnecessary timestamps and order entries deterministically.
4. Define module roots, module path, service binding, and jlink arguments.
5. Build the runtime image in a clean output directory.
6. If caching the jlink task, declare the full JDK, jmods, module artifacts, arguments, target platform, and output.
7. Enable the build cache; configure remote cache with appropriate push/pull permissions.
8. Enable the configuration cache separately and resolve compatibility issues.
9. Build twice in clean workspaces on the same platform and compare manifest hashes.
10. Test the runtime image using the executable inside the image and inside the target container.
11. Archive toolchain identity, commit SHA, dependency verification state, and artifact hashes alongside the release.

The build cache accelerates reproducing outputs; reproducible builds verify whether outputs are truly generated from the same inputs. The two goals support each other rather than replacing one another. Caching is only safe when tasks have complete input/output contracts, while reproducibility requires locking the entire toolchain, dependencies, environment, and artifact generation rules.
