# Distinguishing Dependency Cache, Configuration Cache, and Task Output Build Cache in Spring Boot Build Tooling

## 1. Goal and Big Picture

When running `./gradlew build` multiple times, a Spring Boot application can build faster even when you have not touched any source code. However, saying "Gradle used the cache" is imprecise. At least three distinct mechanisms exist:

1. **Dependency cache**: avoids re-downloading dependency artifacts and metadata from Maven Central, the Gradle Plugin Portal, or internal repositories while cached data remains valid.
2. **Configuration cache**: stores the result of build configuration (the task graph, configured task state, and required dependency information) so compatible subsequent runs can skip re-evaluating build scripts and plugins.
3. **Build cache (task output cache)**: reuses **outputs of cacheable tasks** when their corresponding inputs have not changed, instead of re-running work such as Java compilation or processing certain outputs.

These three caches do not replace one another, can operate simultaneously, and have different validity rules. **`UP-TO-DATE` is not `FROM-CACHE`**, and "dependencies are already downloaded" does not prove Gradle reused configuration or task outputs.

After this lesson, you will be able to:

- Map the initialization → configuration → execution flow and place each cache in the right step.
- Read logs to distinguish download reuse, configuration cache reuse, `UP-TO-DATE`, and `FROM-CACHE`.
- Enable/disable each cache via CLI or `gradle.properties`, and understand the effects of `clean`, `--offline`, `--refresh-dependencies`, and `--rerun-tasks`.
- Practice on a Java 17 + Spring Boot 3.3.13 project using either Gradle Groovy DSL or Kotlin DSL.
- Know when a task is not cached and why input/output declarations and deterministic builds matter.
- Contrast these with the **Maven local repository** and **Maven Build Cache Extension**, without confusing them with Gradle's built-in mechanisms.
- Diagnose cache misses, stale dependencies, plugin incompatibilities, and CI security/correctness risks.

**Version scope:** the examples use Spring Boot 3.3.13 and Java 17 for consistency across the module. This is an illustrative baseline, not a claim that it is the latest Spring Boot release. Some flags and configuration-cache support levels vary across Gradle/plugin versions, so use the repository's Gradle Wrapper and consult the corresponding documentation.

## 2. Which Lifecycle Phase Does Each Cache Optimize?

Gradle typically has three main phases:

~~~text
Initialization
  └─ Determine build, settings, root/subprojects

Configuration
  ├─ Read settings.gradle(.kts), build.gradle(.kts)
  ├─ Apply plugins, create/configure tasks
  ├─ Determine task graph and related dependencies
  └─ Produce the configured build model

Execution
  ├─ Check each task's inputs/outputs
  ├─ Resolve artifacts as needed by tasks/build
  ├─ Run compiler, tests, packaging if needed
  └─ Produce build/classes, build/resources, build/libs...
~~~

This is a conceptual diagram. **Dependency resolution can occur during configuration or execution**, depending on build logic and how Gradle stores the configuration cache; it should not be taught as belonging exclusively to one phase.

The three caches sit at the following points:

~~~text
Remote repositories (Maven Central, mirror, Plugin Portal)
          |
          v
[DEPENDENCY CACHE] ──> Maven/Gradle modules, metadata, JARs
          |
          v
Gradle build model / task classpath
          |
[CONFIGURATION CACHE] ──> configured task graph + task state
          |
          v
Task execution decisions
          |
          +── Workspace inputs/outputs already valid ──> UP-TO-DATE
          |
          +── Cacheable task + matching cache key ───> FROM-CACHE
          |
          +── Cannot reuse ───────────────────────────> EXECUTED
                                                         |
                                                         v
                                                 Outputs in build/
~~~

A project can have every dependency cached and still need to recompile code; reuse configuration and still need to run tests; or reuse cached task outputs and still re-evaluate configuration because the configuration cache is disabled.

## 3. Comparison of the Three Mechanisms

| Criterion | Dependency cache | Configuration cache | Build cache |
| --- | --- | --- | --- |
| Optimizes | Downloads and metadata resolution | Gradle configuration phase | Task computation/outputs |
| Primary data | Modules, artifacts, POM/metadata, resolution results | Task graph, configured task state, and configuration info | Outputs of cacheable tasks / certain transforms |
| Common storage location | `GRADLE_USER_HOME/caches/modules-2` | `.gradle/configuration-cache` in build root | Local build cache under Gradle User Home; remote optional |
| Reuse condition | Valid module/repository metadata and TTL/checksums | Same kind of task invocation and valid configuration inputs | Task cache key matches declared inputs, implementation, and output metadata |
| How to enable | Gradle uses dependency cache by default | `--configuration-cache` or corresponding property | `--build-cache` or corresponding property |
| Temporarily disable/bypass | `--refresh-dependencies` requests re-verification; `--offline` uses local data only | `--no-configuration-cache` | `--no-build-cache` |
| Shared across projects/machines | Local artifact cache; sharing requires careful setup | Not a general remote shared cache | Local or configured remote shared cache |
| Verification signal | Fewer/no downloads; accurate dependency graph | Logs showing configuration cache stored/reused | `FROM-CACHE` in task output |
| Effect of `clean` | Does not delete Gradle User Home caches | Does not automatically delete configuration cache | Deletes outputs in `build` but keeps build cache entries |
| Means tests ran? | No | No | No; a cached task result is not a fresh test execution |

**Distinguish "file exists" from "cache hit":** a package already downloaded into Gradle User Home does not mean the compilation task was cached. Similarly, an intact `build/libs/app.jar` archive does not prove a task read from the build cache; Gradle may simply have marked the task `UP-TO-DATE` based on local outputs and execution history.

## 4. Dependency Cache

### 4.1. What does the cache contain?

Gradle stores dependency resolution data and downloaded artifacts in Gradle User Home, by default typically:

~~~text
~/.gradle/
└── caches/
    └── modules-2/
        ├── files-2.1/      # artifact files/checksums
        └── metadata-.../   # resolution/metadata results, name varies by Gradle version
~~~

The paths illustrate the convention; on Windows it is usually under the user directory and can be changed via `GRADLE_USER_HOME`. **Do not write build logic that depends on internal cache file layouts**: Gradle may change directory organization across versions.

Example:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Gradle must resolve the dependency graph, BOM/constraints, and metadata, and download the required JARs. Those artifacts can be reused across subsequent builds. However, if Java sources change, `compileJava` may still need to run even though the download cache is completely valid.

Gradle also caches resolution results for dynamic versions, module metadata, and even negative lookups (module not found in a repository). Metadata caches are tied to repository sources; changing a URL, layout, or repository configuration can cause Gradle to re-resolve. The dependency cache is **not an arbitrary folder where you manually drop JARs and expect them to be trusted**.

### 4.2. Fixed, dynamic, and changing versions

Three cases must be distinguished:

| Declaration | Example | Rule |
| --- | --- | --- |
| Fixed version | `spring-core:6.1.20` | Typically treated as an immutable artifact; Gradle prefers reuse via metadata/checksums |
| Dynamic version | `1.+` or `latest.release` | Gradle caches the resolved concrete version according to TTL |
| Changing module | SNAPSHOT or dependency marked changing | Metadata/artifact may change without changing coordinates; uses an appropriate TTL |

By default, Gradle caches **dynamic versions** and **changing modules** for roughly **24 hours** (per current Gradle documentation) unless the resolution strategy is adjusted. This does not mean every fixed version is "refreshed after 24 hours"; fixed releases are normally expected not to change content.

**Groovy DSL**, snippet to tune TTL in a build:

~~~groovy
configurations.configureEach {
    resolutionStrategy.cacheDynamicVersionsFor 10, 'minutes'
    resolutionStrategy.cacheChangingModulesFor 4, 'hours'
}
~~~

**Kotlin DSL** equivalent:

~~~kotlin
configurations.configureEach {
    resolutionStrategy.cacheDynamicVersionsFor(10, "minutes")
    resolutionStrategy.cacheChangingModulesFor(4, "hours")
}
~~~

This is an **optional snippet**, not needed for the default example. Lowering TTL causes more network checks; setting it to 0 or refreshing constantly only makes sense when SNAPSHOTs genuinely need rapid updates. Production applications should favor pinned versions and explicit dependency control to avoid non-reproducible builds.

### 4.3. `--offline` and `--refresh-dependencies` do not mean the same thing

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration runtimeClasspath --offline
./gradlew dependencies --configuration runtimeClasspath --refresh-dependencies
~~~

- `--offline`: uses no network for resolution; relies strictly on locally available artifacts/metadata. If a required dependency or metadata is missing from the cache, the build may **FAIL**. Offline does not invent missing dependencies and does not guarantee cached artifacts are the "latest."
- `--refresh-dependencies`: asks Gradle to re-verify resolution/metadata and artifacts against repositories. It **does not necessarily re-download every JAR file**; if checksums/remote metadata show the cached file is still valid, Gradle can reuse it.
- Normal command: uses the cache per TTL/resolution policy and downloads when needed.

**Do not confuse them:** `--refresh-dependencies` does not "wipe the build cache," and `--offline` does not enable the configuration cache or task output cache. Also do not combine `--offline` and `--refresh-dependencies` expecting Gradle to simultaneously use and not use the network.

### 4.4. When should you inspect the dependency cache?

When encountering:

- Dependency resolution is intermittently slow or repeatedly downloading.
- A snapshot/dynamic version does not reflect the version you expect.
- A repository/mirror, credentials, or network changed and the build reports a missing module.
- An ephemeral CI agent has to re-download dependencies.
- Classpath errors occur despite files existing from a previous build.

Start with `--info`/`dependencyInsight` and inspect repository configs; **do not immediately delete all of `~/.gradle/caches`**. A missing artifact is usually a coordinate, mirror, policy, or network error, not a "corrupt cache."

## 5. Configuration Cache: Avoiding Re-Configuring the Entire Build

### 5.1. What does the configuration phase do?

During configuration, Gradle reads settings/build scripts, applies plugins (such as `java` and `org.springframework.boot`), creates/configures tasks like `compileJava`, `test`, and `bootJar`, and computes the task graph for the requested tasks.

In multi-module repositories, configuration can take significant time even when task execution afterward takes only a few seconds. **Configuration cache** saves the configured state so repeating the same kind of build avoids re-running the full configuration phase.

Example (depending on Gradle version):

~~~bash
./gradlew help --configuration-cache
./gradlew help --configuration-cache
~~~

On the first run, Gradle typically writes/stores the configuration cache; on the second run, if conditions match, it may print **reusing configuration cache**. The `help` task is used to learn the configuration mechanism without pulling full compilation/tests into the measurement. Check the logs of your **actual wrapper version**: exact wording may vary.

### 5.2. Enable per invocation or in the project

Once:

~~~bash
./gradlew help --configuration-cache
~~~

Enable persistently in `gradle.properties`:

~~~properties
org.gradle.configuration-cache=true
~~~

Temporarily disable for the current command:

~~~bash
./gradlew help --no-configuration-cache
~~~

Do not blindly enable it across all modules if plugins/tasks/build logic are not compatible yet. Configuration cache imposes rules on **configuration-time dependencies, task state serialization, and avoiding direct `Project` API access at execution time**. Run verification and resolve warnings/errors at their root cause.

### 5.3. What state does the configuration cache store?

Gradle records the configured task graph and task state needed for the requested tasks. Cache keys/fingerprints can consider:

- Task names and relevant invocation parameters.
- Settings/build scripts, `buildSrc`/included build logic.
- `gradle.properties`, version catalogs, dependency verification/lock files.
- Relevant Gradle/JVM environment details.
- Environment variables/system properties/files read during configuration.
- Filesystem state or inputs checked by build logic during configuration.

**Changing Java source files** does not necessarily cause a configuration cache miss if those files are not read during configuration and the task graph/configuration remains unchanged. In that case, configuration cache still hits, while `compileJava` processes the new source input during execution. Conversely, touching `build.gradle` alone can cause a configuration cache miss even when Java sources are unchanged.

### 5.4. Configuration cache differs from remote build cache

Configuration cache is typically stored at:

~~~text
<root-project>/.gradle/configuration-cache/
~~~

It is a **local cache per build/configuration**. It is not identical to a remote build cache. Zipping this directory and uploading it to a server for other CI agents to reuse is **not a standard sharing workflow** and carries environment/compatibility and sensitive-data risks. Cache management products may offer dedicated mechanisms; only use verified policies.

A configuration cache hit does not guarantee task outputs already exist. Gradle may still compile/test/package after restoring the task graph from cache.

### 5.5. Security warning

The configuration cache can store configured task state and input fingerprints, including environment/system properties or credentials read by build logic. Modern Gradle includes mechanisms to protect cache data, but **that does not make writing secrets directly into build scripts/task state safe**.

- Never hardcode credentials in `build.gradle`/`gradle.properties` committed to Git.
- Use the Providers API, secret management, and proper lazy wiring; avoid resolving secrets during configuration when unnecessary.
- Do not share the configuration cache directory across machines/keys in an uncontrolled manner.
- Never print tokens/private repository credentials in `--info` logs or artifacts.

If Gradle reports a configuration-cache problem, fix the task/plugin/build logic or temporarily disable configuration cache for that workflow. Do not use `configuration-cache-problems=warn` as a long-term default because it can mask task-state serialization bugs.

## 6. Build Cache: Reusing Task Outputs

### 6.1. Conditions for reusing task output

A task like `compileJava` produces `.class` files from Java sources, compiler options, classpath, and tooling. If a task supports output caching, Gradle can compute a **cache key** from:

- The task's implementation and action implementation.
- Declared task inputs: source files, classpath, compiler flags, options, toolchain, etc.
- Output property names and related factors.

When the key matches an entry in the build cache, Gradle **restores the output** instead of re-running the compiler. This requires the task to be cacheable and inputs/outputs to be properly modeled; not every custom task is cacheable.

Gradle Build Cache can be:

- **Local**: reused across multiple builds/workspaces on the same machine.
- **Remote**: shares outputs via a configured build cache server when task cache keys and environments permit.

Distinguish **task output caching** from Gradle **incremental compilation**: incremental compilation reduces which sources are compiled when the task must run; build cache can skip the entire task action using stored outputs.

### 6.2. Enabling the build cache

Via CLI:

~~~bash
./gradlew compileJava --build-cache
~~~

In `gradle.properties`:

~~~properties
org.gradle.caching=true
~~~

Temporarily disable:

~~~bash
./gradlew compileJava --no-build-cache
~~~

This flag controls the **task output cache**, not the dependency cache or configuration cache. In some Gradle setups, the build cache is off by default; check your wrapper/repository configuration.

### 6.3. `UP-TO-DATE` and `FROM-CACHE`: fundamental difference

Suppose task `compileJava` already produced `build/classes/java/main`. Next time, with unchanged inputs and outputs still present, Gradle can skip the task via **up-to-date checks**. The log may show:

~~~text
> Task :compileJava UP-TO-DATE
~~~

This does not require the build cache. It simply indicates that task inputs/outputs and local execution history allow reusing **outputs already present in this workspace**.

If you delete `build` with `clean` while the build cache still holds valid outputs, Gradle can restore them from the cache:

~~~text
> Task :compileJava FROM-CACHE
~~~

`FROM-CACHE` signals that **task outputs were retrieved from the build cache**. If the log shows `> Task :compileJava` with no reuse label, the task likely ran its action normally. Depending on task/version, you may also see `NO-SOURCE`, `SKIPPED`, `FROM-CACHE`, or `UP-TO-DATE`; do not infer outcomes from speed alone.

### 6.4. The clearest illustrative experiment

On a project with Java sources and a valid Gradle wrapper:

~~~bash
./gradlew clean compileJava --build-cache
./gradlew compileJava --build-cache
./gradlew clean compileJava --build-cache
~~~

Purpose of each step:

1. **Clean + compile**: the task needs to produce outputs; it may execute for real or report `FROM-CACHE` if a prior cache entry already exists.
2. **Compile immediately afterward**: usually `UP-TO-DATE` if inputs/outputs are unchanged.
3. **Clean + compile again**: opportunity for `FROM-CACHE` because workspace outputs were deleted while a valid cache entry remains.

This is the **expected scenario**, not guaranteed output on every machine. If a task is not cacheable, inputs differ, toolchain/Gradle versions differ, or the cache entry was evicted, Gradle executes the task. Use `--info` to see why a task was or was not cached.

### 6.5. `--rerun-tasks` differs from `--no-build-cache`

~~~bash
./gradlew compileJava --rerun-tasks
./gradlew compileJava --no-build-cache
~~~

- `--rerun-tasks`: tells Gradle to re-execute task actions instead of skipping via up-to-date or build-cache reuse; useful when verifying fresh execution.
- `--no-build-cache`: disables build cache lookups/stores for that invocation, **without disabling up-to-date checks**. Therefore a task can still report `UP-TO-DATE`.
- `clean`: deletes build outputs under `build`, without deleting Gradle User Home caches.

Do not treat these three mechanisms as synonyms. To force tasks to run without reusing cached outputs, `--rerun-tasks` is the directly relevant option, though check flag behavior for your Gradle version when using custom build logic.

### 6.6. Not every Spring Boot task is guaranteed to be cacheable

`compileJava`, certain resource processing/archive tasks, and transforms have caching rules depending on Gradle/plugin versions. Test or packaging tasks may be conditionally cacheable or non-cacheable depending on implementation, settings, and outputs.

**In particular:** never assume `bootJar FROM-CACHE` will always appear when `--build-cache` is enabled. Check the task implementation/cacheability and actual logs. Seeing `bootJar` produce identical files across two builds is not proof of cached output.

A custom task written with `doLast` that fails to declare inputs/outputs properly may:

- Always execute because Gradle does not know valid outputs.
- Be falsely marked `UP-TO-DATE` if an undeclared hidden input changed.
- Return incorrect results when reusing a remote cache if outputs embed timestamps/random values/absolute paths.

**Build correctness comes before speed:** a cacheable task must be deterministic with respect to declared inputs; declare sources, classpath, and relevant environment/task properties properly. Avoid embedding the current timestamp into generated files unless truly required and declared as an input.

## 7. Sample Spring Boot Java 17 Project for Experiments

We use a small console application—enough to demonstrate compilation and packaging without needing a database or HTTP server.

Directory tree:

~~~text
cache-demo/
├── settings.gradle                # if using Groovy DSL
├── build.gradle                   # if using Groovy DSL
│  or settings.gradle.kts        # if using Kotlin DSL
│  or build.gradle.kts           # if using Kotlin DSL
├── gradle.properties              # optional, initially empty
└── src/
    └── main/
        └── java/
            └── com/example/cache/
                └── CacheDemoApplication.java
~~~

**Choose one matching settings/build pair**; do not create both build scripts expecting Gradle to "run both Groovy and Kotlin." If the project already has a Gradle wrapper (`gradlew`/`gradlew.bat`/`gradle/wrapper`), use it; otherwise prepare a wrapper with an appropriate Gradle version.

### 7.1. Groovy DSL — settings.gradle

~~~groovy
rootProject.name = 'cache-demo'
~~~

### 7.2. Groovy DSL — complete build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.1.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

`java` provides Java compilation tasks; the Spring Boot plugin creates `bootJar` with executable packaging when the Java plugin is present. The dependency management plugin alongside the Spring Boot plugin provides the compatible BOM so managed starter versions can be omitted.

### 7.3. Kotlin DSL — settings.gradle.kts

~~~kotlin
rootProject.name = "cache-demo"
~~~

### 7.4. Kotlin DSL — complete build.gradle.kts

~~~kotlin
plugins {
    id("java")
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "0.1.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
}
~~~

Using `build.gradle.kts` does not require writing the application in Kotlin. This is still a Java 17 project.

### 7.5. Runnable Java main class

File `src/main/java/com/example/cache/CacheDemoApplication.java`:

~~~java
package com.example.cache;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CacheDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CacheDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner printDemo() {
        return args -> System.out.println("CACHE_DEMO_OK");
    }
}
~~~

Output line printed by the code itself when run successfully:

~~~text
CACHE_DEMO_OK
~~~

Other Spring Boot logs may also appear. Because there is no web starter or background thread, the process exits after startup; this is normal demo behavior, not the cache stopping the application.

With the Java 17 toolchain, the build machine must have an appropriate JDK 17 or Gradle configured to provision toolchains. The machine running the JAR needs a compatible Java runtime.

### 7.6. Build and run the application

~~~bash
./gradlew --version
./gradlew clean build
java -jar build/libs/cache-demo-0.1.0.jar
~~~

Once `build` succeeds and `bootJar` creates the default file, the app prints `CACHE_DEMO_OK`. `build` in the Java lifecycle normally wires `assemble` and `check`. For a demo without JUnit test sources, the `test` task may be skipped or `NO-SOURCE`; **do not call that proof that tests ran and passed when no tests exist**.

## 8. Lab A — Demonstrating the Dependency Cache

Goal: focus solely on dependency resolution, not measuring compilation.

First run online:

~~~bash
./gradlew dependencies --configuration runtimeClasspath --info
~~~

Gradle resolves the Spring Boot starter and transitive dependencies if not yet cached, downloading artifacts/metadata from repositories. On the next run:

~~~bash
./gradlew dependencies --configuration runtimeClasspath --info
~~~

If the cache is still valid, Gradle can reuse metadata and artifacts, with fewer or no network downloads. **Do not rely solely on the command running faster**: the daemon, filesystem cache, or network proxy also affect timing.

Try offline after the cache is populated:

~~~bash
./gradlew dependencies --configuration runtimeClasspath --offline
~~~

If everything needed is already present, it can resolve. If any artifacts/plugin metadata were not stored, the offline build may fail—this **does not prove the dependency cache is corrupt**, only that offline lacks sufficient data to resolve the build.

When you suspect a changing/snapshot artifact has been updated on the server:

~~~bash
./gradlew dependencies --configuration runtimeClasspath --refresh-dependencies
~~~

Inspect the logs and resolution result. `--refresh-dependencies` requests re-verification, without re-downloading files whose cached checksums still match. Do **not** add `clean` and call that a way to clear the dependency cache.

One note: the `dependencies` task primarily displays the graph; to ensure required binary JARs are downloaded and the compiler has the full classpath, run `compileJava`/`bootJar` while online. Gradle can resolve metadata without necessarily downloading every artifact file during a graph-only command.

## 9. Lab B — Demonstrating the Configuration Cache

In the sample project:

~~~bash
./gradlew help --configuration-cache
./gradlew help --configuration-cache
~~~

Both commands request the same `help` task. When build logic/configuration inputs are unchanged and plugins are compatible, the first run usually stores an entry and the second reuses it. If the configuration cache reports an error with a plugin or build logic, inspect the report; do not repeatedly delete the cache to hide incompatibility.

To observe the difference between **configuration changes** and **source changes**:

1. Run `help --configuration-cache` twice until you see reuse.
2. Change a comment or property in `build.gradle`/`build.gradle.kts` and run again. Gradle usually invalidates the entry because the build script input changed.
3. Run again without editing anything; configuration cache can be reused again.
4. Edit the body of `CacheDemoApplication.java` and run `help --configuration-cache`. If build logic does not read source contents during configuration, source edits **do not necessarily** cause a configuration cache miss.

Do not run a different task and expect it to reuse the exact entry from `help`: requested tasks are part of the cache key/validation context. `help`, `compileJava`, `bootJar`, and `build` have different graphs.

To disable temporarily:

~~~bash
./gradlew help --no-configuration-cache
~~~

Disabling the configuration cache does not delete dependency JARs and does not delete task outputs.

## 10. Lab C — Distinguishing UP-TO-DATE and FROM-CACHE

Use the Java source from Section 7.5 without editing between commands.

~~~bash
./gradlew clean compileJava --build-cache
./gradlew compileJava --build-cache
./gradlew clean compileJava --build-cache
~~~

Observe and record task outcomes:

| Run | Expected for a cacheable task with identical inputs | Why |
| --- | --- | --- |
| Run 1: clean + compile | `EXECUTED`, or `FROM-CACHE` if already cached | No local outputs after clean; may hit cache from an earlier build |
| Run 2: compile | Usually `UP-TO-DATE` | Local class files still exist and inputs are unchanged |
| Run 3: clean + compile | Potentially `FROM-CACHE` | Local outputs were deleted, but a valid cache entry can be restored |

If `FROM-CACHE` does not appear, run with `--info` to see whether the task is non-cacheable, task inputs changed, or caching is disabled/disallowed.

A control command:

~~~bash
./gradlew compileJava --no-build-cache
~~~

The task **can still** be `UP-TO-DATE`; therefore `--no-build-cache` is not "force recompilation." To force task actions to re-run for investigation:

~~~bash
./gradlew compileJava --rerun-tasks
~~~

Compile tasks can still report `NO-SOURCE` if the project has no Java code; this is why the example requires creating `CacheDemoApplication.java`.

### 10.1. Scenario with both caches enabled

~~~bash
./gradlew build --configuration-cache --build-cache
./gradlew build --configuration-cache --build-cache
~~~

On the second run, you may see **reusing configuration cache** and several `UP-TO-DATE` tasks. That does not prove the task-output build cache was fetched; when outputs still exist, Gradle usually prefers up-to-date. If you run `clean build --configuration-cache --build-cache`, some cacheable tasks have a chance to report `FROM-CACHE`, though `clean build` has a different requested task graph so its configuration cache entry may also differ from `build`.

**Each mechanism has its own verification signal**; do not equate "faster build" with hitting all three caches.

## 11. Change Matrix: Which Cache Is Likely Affected?

| Action | Dependency cache | Configuration cache | Task output / UP-TO-DATE |
| --- | --- | --- | --- |
| Edit a Java file's contents | Can still reuse artifacts | Can reuse if sources are not read at config time | `compileJava` input changed, needs reprocessing |
| Edit `build.gradle` | Dependencies may still be cached | Usually invalidated | May be invalidated if task config/classpath/inputs changed |
| Change Spring Boot starter/plugin version | Must resolve new metadata/artifacts | Usually invalidated | Classpath/tooling changed, cache keys may change |
| Run `clean` | Does not delete Gradle User Home module cache | Does not necessarily delete config entry | Deletes local outputs, yet build cache entries can still be reused |
| Run `--offline` | Uses locally cached data only | Does not toggle it on/off | Task behavior still follows inputs/outputs; may fail if a dependency is missing |
| Run `--refresh-dependencies` | Requests fresh dependency verification | May affect resolution/config validity depending on Gradle | If resolved artifacts differ, task inputs/cache keys may change |
| Run `--no-configuration-cache` | Not directly | Disables configuration reuse for that run | Does not disable task output cache |
| Run `--no-build-cache` | Not directly | Not directly | No task-output cache lookup/store; local `UP-TO-DATE` can still occur |
| Run `--rerun-tasks` | Does not force re-downloading deps | Not a config-cache wipe switch | Forces task actions to re-run instead of reusing outcomes |
| Run on a fresh CI machine | Must populate/restore dependency cache | Has no prior local entry automatically | May reuse remote build cache if configured/permitted |

These outcomes are **likely behaviors** based on standard inputs and configuration; when custom plugins read sources during configuration or have hidden task inputs, behavior can differ. Measure via real logs/stats rather than guessing from flag names.

## 12. Correlation with Maven: Repository Cache and Build Cache Extension

### 12.1. Which mechanism is `~/.m2/repository` closest to?

Maven has a **local repository**, typically located by default at:

~~~text
~/.m2/repository/
~~~

It stores artifacts downloaded from remote repositories **and** artifacts built/installed locally. It is therefore closest to the **Gradle dependency cache**, though not completely identical: the local Maven repository is also where `mvn install` writes project artifacts, while the Gradle dependency cache has its own structure and metadata model.

Related Maven commands:

~~~bash
mvn dependency:tree
mvn -o package
mvn -U package
~~~

- `mvn -o` uses offline mode without downloading new dependencies.
- `mvn -U` forces update checks for SNAPSHOT/missing releases per Maven semantics, not Gradle `--refresh-dependencies`.
- `mvn dependency:tree` prints the resolved graph.

Do not delete all of `~/.m2/repository` just because of a dependency error; you might wipe internal artifacts that were `install`ed locally and not published. Check coordinates, mirrors, `settings.xml`, local repo config, and POMs first.

### 12.2. Does Maven have a Configuration Cache like Gradle?

Do not call the Maven local repository a configuration cache. Maven's `pom.xml`/lifecycle/plugin execution does not have a direct built-in flag equivalent to Gradle's `--configuration-cache` in the baseline usage covered by this lesson. Maven has other optimizations, but they should not be equated with Gradle's caches.

### 12.3. Maven Build Cache Extension is a separate mechanism

Apache Maven offers the **Maven Build Cache Extension** (requiring a compatible Maven version; current docs note Maven 3.9+). It can fingerprint module inputs and restore outputs from a local/remote cache, which is useful for multi-module builds. It is an **extension that must be enabled/configured**, not an automatic effect of having `~/.m2/repository`.

Example extension declaration (only use if the team decides to adopt it, with a verified version):

~~~xml
<extensions>
    <extension>
        <groupId>org.apache.maven.extensions</groupId>
        <artifactId>maven-build-cache-extension</artifactId>
        <version>1.3.0</version>
    </extension>
</extensions>
~~~

Its usual location is `.mvn/extensions.xml` in a Maven project; this is **not a complete `pom.xml`** and does not need to be added to a Spring Boot app just to learn about caching. Before using it in CI, verify Maven/plugin compatibility, cache key config, reproducibility, test policies, and remote cache trust.

### 12.4. Quick comparison

| Concept | Gradle | Maven |
| --- | --- | --- |
| Cache downloaded artifacts | Dependency cache under Gradle User Home | Local repository `~/.m2/repository` |
| Cache configuration/task graph | Gradle Configuration Cache | No built-in equivalent in standard Maven workflow |
| Cache outputs | Gradle Build Cache (local/remote) | Maven Build Cache Extension if installed/verified |
| Disable network usage | `--offline` | `-o` |
| Force dependency refresh | `--refresh-dependencies` | `-U` (different semantics) |
| Clean project outputs | `clean` task | `mvn clean` |
| Standard build | `./gradlew build` | `mvn package`/`mvn verify` |

When a Spring Boot module uses Maven, **do not copy Gradle flags** like `--build-cache` into `mvn`. Choose the appropriate tool, set accurate expectations, and inspect the logs.

## 13. CI/CD: Which Caches Should Be Shared?

### 13.1. Dependency cache on CI

Fresh CI agents typically lack a Gradle dependency cache, so the first run must download artifacts. You can cache/restore Gradle User Home data following your CI provider's official guidance, keyed on Gradle version, dependency lock/config, and system policy. Watch out for:

- Avoid caching untrusted artifacts or credentials/tokens.
- Do not copy a Gradle cache while processes are actively writing to it and ignore concurrency/corruption risks.
- Cache only necessary data using supported mechanisms; some directories in Gradle User Home hold machine/process-specific state and should not be shared wholesale.
- If using a private Maven mirror/proxy, verify artifact provenance and policy.

### 13.2. Configuration cache on CI

Configuration cache is local build state, not a shared remote cache across multiple agents. For pipelines running strictly on ephemeral machines, storing an entry on the first run may not help the next run unless an official, properly secured save/restore mechanism is used. Using `--configuration-cache` in CI requires verifying plugin/task compatibility and actual benefit.

Do not upload raw `.gradle/configuration-cache` to a public artifact store because it may contain configuration or secret-derived state.

### 13.3. Remote build cache

A remote Gradle Build Cache can bring significant benefits when multiple developers/CI builds work on the same code and tasks are designed to be cacheable/relocatable. However:

- Connect only to endpoints with proper authorization, TLS, and authentication.
- Control who **can push** vs. who can only **pull**; many teams allow only trusted CI branches to write to the remote cache.
- Do not accept outputs from an untrusted cache, as outputs may be binaries/scripts that get executed or packaged.
- Cache keys must accurately reflect compiler options, runtime/toolchains, generated-source config, annotation processors, and environment.
- Run cold-build validation and artifact comparisons during initial rollout; never prioritize speed over correctness.

A build cache cuts redundant work; **it does not replace testing, supply-chain security, artifact signing, and provenance**.

## 14. Why Isn't the Cache Used Even When Enabled?

### 14.1. Configuration cache miss

Common reasons:

- Build scripts, settings, version catalogs, or `buildSrc` changed.
- Requested tasks differed between two invocations.
- Environment/Gradle/JVM inputs affecting configuration changed.
- A plugin/task violated configuration-cache requirements.
- Logic reading the filesystem/environment at configuration time caused fingerprints to change.

How to investigate:

~~~bash
./gradlew help --configuration-cache --info
~~~

Read the configuration cache report and invalidation reasons. If a plugin is incompatible, upgrade the plugin or fix custom build logic; temporarily disable configuration cache for incompatible tasks rather than wiping the cache in an endless loop.

### 14.2. Build cache miss

Common reasons:

- The task is not declared cacheable or caching is disabled.
- Inputs changed: Java sources, classpath, compiler options, toolchain, resources, or task implementation.
- Outputs are non-deterministic or embed time/machine-dependent data.
- The task fails to declare all inputs/outputs or outputs are not cacheable.
- Remote cache is unreachable or no entry has been stored yet.

How to check:

~~~bash
./gradlew compileJava --build-cache --info
~~~

Gradle can explain why caching is disabled or why the key changed. Not seeing `FROM-CACHE` when a task is `UP-TO-DATE` is normal and not an error.

### 14.3. Dependency cache miss

Possible causes:

- Dynamic/changing dependency reached its TTL.
- Repository URL/layout/mirror changed.
- New artifact not yet cached.
- Different Gradle wrapper/version changing metadata format/cache context.
- Cache eviction or fresh CI agent.
- Blocked proxy/credentials/repository or checksum mismatch.

Check resolution logs, `dependencyInsight`, settings, and network before touching any cache directory.

## 15. Common Troubleshooting Table

| Symptom | Mechanism to inspect | Worthwhile action |
| --- | --- | --- |
| Gradle re-downloads JARs on every run | Dependency cache/repository | Check TTL, changing modules, mirrors, and Gradle User Home |
| Offline run reports missing module | Dependency cache | Run a full online build once; verify cached JARs/metadata |
| `--refresh-dependencies` does not re-download every file | Expected dependency cache behavior | Gradle may verify checksums and reuse unchanged artifacts |
| Build script re-evaluated every run | Configuration cache off/miss | Use `--configuration-cache`; inspect invalidations/compatibility |
| `--configuration-cache` reports invalid plugin task | Configuration-cache requirements | Fix plugin/build logic or disable temporarily for that workflow |
| Task `compileJava UP-TO-DATE` even with build cache off | Local up-to-date checks | Normal; `--no-build-cache` does not force execution |
| Task reports `FROM-CACHE` after `clean` | Task output cache | Output was restored from cache outside the workspace |
| Still downloading dependencies after `clean`? | Not necessarily caused by clean | Check whether cache expired/was missing and inspect repo resolution |
| Task executes despite `--build-cache` | Cache miss or non-cacheable task | Run `--info` and check inputs/cache policy |
| `bootJar` is fast, but tests didn't run | Task graph, not caching | Run `build`/`test` as appropriate; packaging is not JUnit testing |
| Two machines produce different bytes for same source | Determinism, environment, toolchain | Check task inputs/reproducible archives and plugin versions |
| CI receives wrong artifact version | Cache correctness/trust | Check remote cache provenance, keys, and publish workflow |
| Maven local repo has JAR, yet `mvn package` still compiles | Two different caches | Local repo resolves dependencies; it does not cache module outputs |
| Deleted `build` yet dependencies still work offline | Dependency cache persists in user home | Expected; `clean` only clears project outputs |
| Task `FROM-CACHE` followed by failing tests | Cached output does not replace tests or environment changed | Investigate test runner, test inputs, and integration environment |

**Never use "wipe all caches" as a first resort.** It destroys diagnostic evidence, wastes network/CPU, and rarely fixes root causes like version conflicts, plugin incompatibility, or undeclared inputs.

## 16. Exercises with Answers

### Exercise 1. Download speed vs. compile speed

**Scenario:** after the first run, Gradle no longer downloads Spring Boot starter, yet editing one Java file makes `compileJava` run again. Which cache is active?

**Answer:** the dependency cache is likely reusing artifacts; editing source code changes the compile task's inputs. There is no contradiction.

### Exercise 2. Task UP-TO-DATE

**Scenario:** running `./gradlew compileJava --no-build-cache` still shows `UP-TO-DATE`. Is Gradle ignoring the cache-off flag?

**Answer:** no. `--no-build-cache` disables the task output cache, while local up-to-date checks can still skip task execution when inputs and outputs have not changed.

### Exercise 3. FROM-CACHE after clean

**Scenario:** after running `./gradlew clean compileJava --build-cache`, the log shows `compileJava FROM-CACHE`. Did Gradle re-run the compiler?

**Answer:** not if the task was restored from the build cache; outputs matching the key were already stored and restored. An output file having a new timestamp does not prove the compiler just ran.

### Exercise 4. Configuration cache still hits after editing Java source

**Scenario:** after changing code in `src/main/java`, running `build --configuration-cache` still reuses the configuration cache, and then `compileJava` executes.

**Answer:** expected if build logic does not read source contents during configuration. The cached task graph/configuration remains valid; compilation inputs changed so execution must re-run.

### Exercise 5. Offline cannot find plugin

**Scenario:** `./gradlew build --offline` fails because a plugin/version is not resolved locally, even though some starter JARs are present.

**Answer:** offline mode requires all relevant metadata/artifacts (including build plugins) to be cached locally. Run online in a properly configured repository environment first; do not assume a few JARs in the cache suffice.

### Exercise 6. Remote cache on CI

**Scenario:** builds from untrusted branches can push binary outputs to a remote cache that release branches read from.

**Answer:** this setup carries supply-chain and correctness risks. Separate push/pull permissions, allow only trusted CI jobs to write, and secure endpoint/keys/output validation.

### Exercise 7. Maven local repo

**Scenario:** `~/.m2/repository` already contains Spring Boot dependencies, yet Maven still recompiles modules.

**Answer:** the local repository supports dependency resolution/downloads and installed artifacts; it **is not a task output cache**. Output caching in Maven requires a dedicated configured extension such as the Maven Build Cache Extension.

### Exercise 8. Fixing stale dependencies

**Scenario:** a team uses SNAPSHOTs and Gradle is not picking up a newly published build.

**Answer:** check changing-dependency TTL, the dependency graph, and repositories; you can use `--refresh-dependencies` to ask Gradle to re-verify. Do not delete `build` expecting it to reset the download cache.

### Exercise 9. Both flags enabled

**Scenario:** a team sets `org.gradle.caching=true` and `org.gradle.configuration-cache=true`. Does that mean running `build` will never run any tasks?

**Answer:** no. Configuration cache only saves configuration time when it hits; build cache only applies to cacheable task outputs when keys match. Tasks can still be `EXECUTED`, `NO-SOURCE`, `SKIPPED`, or `UP-TO-DATE`.

### Exercise 10. Verifying real build results

**Scenario:** a second build is 50% faster, but the person measuring recorded no logs or breakdown. Can they conclude "remote build cache saved 50%"?

**Answer:** no. The daemon, filesystem page cache, dependency downloads, configuration cache, incremental compilation, up-to-date checks, and task output cache all influence timing. Controlled measurements and outcome inspection are required before attributing the cause.

## 17. Checklist for Applying Cache Optimizations

- [ ] Consistent Gradle wrapper/JDK; build succeeds **without relying on caches**.
- [ ] Stable dependency versions/repositories/BOM; minimize dynamic versions in releases.
- [ ] Dependency cache verified using resolution logs and controlled offline tests.
- [ ] Configuration cache piloted on clear workflows with compatibility issues resolved.
- [ ] Build cache enabled when tasks are cacheable, inputs/outputs are complete, and reproducibility is ensured.
- [ ] Clear distinction in logs between `UP-TO-DATE`, `FROM-CACHE`, `NO-SOURCE`, and actual task execution.
- [ ] Tested `clean compileJava --build-cache` to see how it differs from local outputs.
- [ ] Not using `--refresh-dependencies` as a substitute for invalidating configuration/task outputs.
- [ ] Not using `--no-build-cache` when aiming to disable configuration cache, and vice versa.
- [ ] Custom tasks do not read clock/secrets/environment arbitrarily without input declarations.
- [ ] CI remote cache enforces permissions and trust; raw configuration cache is not shared.
- [ ] Tests, packaging, and security checks still run per policy even when cache hits save work.
- [ ] Cache invalidation and misses are tracked via logs/diagnostics rather than blindly "wiping everything."

**Summary:** **Dependency cache** saves downloading and resolving libraries; **Configuration cache** saves recomputing configuration/task graphs; **Build cache** saves executing cacheable tasks by restoring outputs. All three can work together, yet **they cache three different kinds of data and do not by themselves prove a build is correct**. Optimize only after securing reliable dependency resolution, inputs/outputs, and testing.

## 18. Official Documentation

- Gradle — Dependency Caching: https://docs.gradle.org/current/userguide/dependency_caching.html
- Gradle — Configuration Cache: https://docs.gradle.org/current/userguide/configuration_cache.html
- Gradle — Enabling and Configuring Configuration Cache: https://docs.gradle.org/current/userguide/configuration_cache_enabling.html
- Gradle — Build Cache: https://docs.gradle.org/current/userguide/build_cache.html
- Gradle — Build Cache Concepts / Cache Keys: https://docs.gradle.org/current/userguide/build_cache_concepts.html
- Gradle — Command-Line Interface, performance flags: https://docs.gradle.org/current/userguide/command_line_interface.html
- Maven — Local Repositories: https://maven.apache.org/repositories/local.html
- Maven — Maven Build Cache Extension, Overview: https://maven.apache.org/extensions/maven-build-cache-extension/concepts.html
- Maven — Maven Build Cache Extension, Getting Started: https://maven.apache.org/extensions/maven-build-cache-extension/
- Spring Boot — Gradle Plugin 3.3, Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html

In production environments, consult documentation matching your **active Gradle wrapper, Spring Boot Plugin, and Maven versions**. The CLI examples above demonstrate how to learn and verify caching behavior, not a directive to enable every cache in an untested CI pipeline.
