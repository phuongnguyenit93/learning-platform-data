# Distinguishing Offline Builds, Dependency Refreshes, and Targeted Cache Purges

## 1. Objective and Problem to Solve

When building Spring Boot applications with Gradle or Maven, you may run into situations such as: the corporate network temporarily drops, a SNAPSHOT on a repository changed yet the build still uses an older one, a dependency JAR is corrupt, or a developer wants a "completely clean build." These situations **cannot all be solved with the same cache command**.

The three operations in the title serve three distinct purposes:

1. **Offline build**: avoids contacting remote repositories to fetch or check dependencies, using only metadata and artifacts already stored locally. In Gradle, use `--offline`; in Maven, use `-o`.
2. **Dependency refresh**: forces re-verification of dependency information against repositories even when cached data is still within its TTL. In Gradle, use `--refresh-dependencies`; Maven provides `-U` with different semantics.
3. **Targeted cache purge**: removes only the suspected corrupt or unneeded slice—such as one specific dependency in the Maven local repository, project build outputs, or an identified cache region—**avoiding deleting the entire user cache** without evidence.

All three differ from a **clean build** in the sense of deleting `build/` or `target/`. Likewise, the dependency download cache differs from Gradle's **configuration cache** and **task-output build cache**.

After this lesson, you should be able to:

- Explain how Gradle/Maven look up artifacts in local caches before using the network when allowed.
- Pick the right flag when building offline, checking repositories for updates, or recovering from a corrupt artifact.
- Understand offline-mode limits regarding plugins, parent/BOMs, SNAPSHOTs, and never-downloaded dependencies.
- Inspect `dependencies`, `dependencyInsight`/`dependency:tree`, metadata, and logs instead of "wiping everything to see."
- Perform minimal recovery steps safely alongside concurrent builds, CI caches, and private repositories.
- Distinguish commands that **change dependency resolution** from those that only **clean project outputs** or **bypass task/configuration caches**.
- Verify a runnable Java 17 Spring Boot application before and after the operation.

**Context:** application examples use Java 17, Spring Boot 3.3.13, Spring dependency-management plugin 1.1.7, and a compatible Gradle wrapper. These versions are consistent examples, not claims about the newest releases. Always keep build-tool versions approved by your repository and CI.

## 2. Quick Decision Tree

~~~text
Build cannot resolve a dependency / suspect stale artifact
                         |
             +-----------+------------------+
             |                              |
        Network down?                  Network available?
             |                              |
             v                              v
   Sufficient local data?        Identify exact GAV/repository
             |                     and dependency graph
         +---+---+                         |
         |       |                         v
        Yes      No            Stale snapshot/dynamic/metadata?
         |       |                  |               |
         v       v                 Yes              No
      offline   Must fetch          |               |
       build    online              v               v
                         Refresh dependencies    Check scope,
                         and verify graph        version conflict,
                                                 corrupt artifact
                                                     |
                                                     v
                                      Handle minimal cache slice
                                      or use isolated user home
~~~

**Do not confuse the branches:**

- Offline mode does not "update libraries."
- Refreshing is not "deleting the cache."
- `clean` does not delete downloaded artifact caches in Gradle User Home or the Maven local repository.
- Deleting all of `~/.gradle` or `~/.m2/repository` forces every other build on the machine to re-download everything, and can destroy Maven artifacts that exist only via local `install`.

First pinpoint whether the failure is in **dependency resolution**, **build configuration**, **task outputs**, **source code**, or the **application runtime**. Only touch the relevant cache.

## 3. Which Cache Are We Talking About?

| State/cache type | Gradle default or typical path | Maven equivalent | When to care? |
| --- | --- | --- | --- |
| Artifacts and dependency metadata | `GRADLE_USER_HOME/caches/modules-2` | `~/.m2/repository` or custom `localRepository` | Downloads, offline builds, SNAPSHOT/changing modules, repository errors |
| Gradle wrapper distribution | `GRADLE_USER_HOME/wrapper/dists` | Maven wrapper distribution per setup | Offline machine lacking the build tool itself |
| Configuration cache | `<root-project>/.gradle/configuration-cache` | No direct built-in equivalent in basic Maven workflows | Build script/task graph configuration |
| Task output build cache | Local under Gradle User Home; optional remote | Maven Build Cache Extension if explicitly installed | Outputs of cacheable compile/resource/processing tasks |
| Task local outputs and execution history | `build/` and project `.gradle/` | `target/` | `UP-TO-DATE`, rebuilds, leftover archives |
| IDE caches | Separate IntelliJ/Eclipse/VS Code caches | Same | IDE shows red errors or syncs differently from CLI |

Directory names can vary across Gradle versions. In particular, `GRADLE_USER_HOME` is not always `~/.gradle` if overridden by environment variables or `-g`. The Maven local repository can also be moved in `settings.xml`.

**Example:** when `./gradlew compileJava` prints `UP-TO-DATE`, that comes from checking task inputs/outputs in the workspace, not proof that the dependency download cache was just queried. When a task prints `FROM-CACHE`, that is the task-output cache, not libraries downloaded from Maven Central.

## 4. How Gradle Resolves a Dependency

With configuration:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Gradle performs steps that can include:

1. Reading declarations in build scripts or version catalogs.
2. Applying plugins, BOMs/constraints, and configurations.
3. Searching configured repositories for module metadata and artifacts.
4. Checking stored resolution data: version, descriptor, artifact metadata, and origin repository.
5. If needed and network is allowed, querying remote repositories or downloading artifacts.
6. Storing valid data in the dependency cache for subsequent builds.

Gradle's dependency cache consists of a **file store** (checksum-indexed JARs/POMs/artifacts) and a **metadata store** (resolved versions, module metadata, lookup results). Metadata can also record **that an artifact was not found** at a given repository to avoid repeated remote calls.

Gradle also tracks metadata per repository URL/type/layout and enforces "repository stickiness" so it does not silently switch artifact origins after resolution. As a result, **changing repositories** can require Gradle to re-check/re-download metadata even if the same JAR file was cached from another source. Never copy random cache files across repositories assuming the cache is complete.

### 4.1. Why does seeing a JAR in cache not guarantee an offline build works?

A single module can pull in dozens of transitive dependencies, platform BOMs, annotation processors, Gradle plugins, and plugin transitive dependencies. An offline build needs **all required data** for the requested task graph, including matching metadata and any uncached artifacts.

For example, a JAR may exist in `modules-2/files-2.1` while Gradle lacks resolution metadata for the requested repository/version; the offline build will still fail. Dependency resolution is not simply scanning a folder for a matching JAR filename.

### 4.2. Dynamic and changing dependencies

Gradle distinguishes:

- **Fixed release:** e.g., `com.example:sample-lib:1.2.3`, normally expected to remain immutable once published.
- **Dynamic version:** e.g., `com.example:sample-lib:1.+`; Gradle must resolve whether `1.7` or `1.8` is chosen.
- **Changing dependency:** e.g., `1.2-SNAPSHOT` or a dependency explicitly marked changing; contents can change without coordinates changing.

Per current Gradle dependency-caching docs, the default TTL for dynamic versions and changing modules is typically **24 hours**, configurable via `resolutionStrategy`. In offline mode, Gradle never checks remotes for updates, even if the TTL has expired.

**Groovy DSL — optional snippet when there is a valid reason to shorten TTL:**

~~~groovy
configurations.configureEach {
    resolutionStrategy.cacheDynamicVersionsFor 10, 'minutes'
    resolutionStrategy.cacheChangingModulesFor 4, 'hours'
}
~~~

**Kotlin DSL:**

~~~kotlin
configurations.configureEach {
    resolutionStrategy.cacheDynamicVersionsFor(10, "minutes")
    resolutionStrategy.cacheChangingModulesFor(4, "hours")
}
~~~

This is only a **snippet**, not a recommended default. Shortening TTL increases network checks and can hurt reproducibility. Releases and CI should prefer pinned versions, dependency locking, or explicit versioning policies over arbitrary dynamic/SNAPSHOT references.

## 5. Gradle Offline Builds: `--offline`

### 5.1. What does `--offline` do precisely?

Gradle `--offline` instructs dependency resolution **not to contact remote repositories**. Modules/artifacts with matching local data remain usable even when cached metadata would normally have expired. If required data is missing from the local cache, the build will **FAIL**.

Example:

~~~bash
./gradlew build --offline
~~~

Distinguish **offline dependency resolution** from "the built app/tests need no network." Custom tasks, integration tests, Docker image builders, HTTP clients in tests, or code generators can still make network calls if uncontrolled. `--offline` does not block every socket in every process.

### 5.2. Preparing an offline build properly

While still connected to repositories:

~~~bash
./gradlew --version
./gradlew clean build
./gradlew bootJar
~~~

Then test:

~~~bash
./gradlew build --offline
~~~

The online run downloads dependencies required by those executed tasks; `bootJar` may also pull `runtimeClasspath` artifacts that calling `dependencies` alone might not materialize. Even so, **it does not guarantee** every future task (integration tests, codegen, native image) will work offline if it has never run or populated its dependencies.

**Wrapper bootstrap is a separate case:** if the machine has not downloaded the Gradle distribution declared in `gradle/wrapper/gradle-wrapper.properties`, the wrapper may need network access **before Gradle ever sees `--offline`**. You cannot fix a missing Gradle distribution simply by appending `--offline`.

### 5.3. How to inspect the outcome

~~~bash
./gradlew dependencies --configuration runtimeClasspath --offline
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath --offline
~~~

- If they succeed, Gradle can resolve that configuration from local data.
- If they fail due to missing module/plugin metadata, download them in an online environment first or point to an accessible internal mirror.
- If the classpath resolves yet application tests call an external service, build/test failures come from test networking, not the Gradle dependency cache.

### 5.4. Never use offline mode to hide repository errors

A build that succeeds only offline while failing online may be relying on stale metadata or outdated repository permissions. It does not prove current remote artifacts are valid. Run an online build verifying sources, versions, and checksums to fix the root cause. Do not leave `--offline` permanently enabled to dodge auth/TLS/repository errors.

## 6. Gradle Dependency Refresh: `--refresh-dependencies`

### 6.1. Exact semantics

The command:

~~~bash
./gradlew build --refresh-dependencies
~~~

tells Gradle to **ignore prior dependency resolution cache results for this check**, perform a fresh resolve against current repositories, and update dynamic version listings, module metadata, and changing modules as needed.

However, it **does not force re-downloading every JAR**. Gradle typically uses metadata/checksum checks or HTTP HEAD requests to verify remote artifacts are unchanged. When a locally cached file still matches the remote checksum, Gradle reuses it and avoids wasted network transfers.

**Therefore:** "I passed `--refresh-dependencies` and didn't see every JAR re-download" **is not a bug**. The command may have refreshed everything properly.

### 6.2. Inspecting a specific configuration

If you suspect `spring-core` or a SNAPSHOT in the runtime classpath:

~~~bash
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath --refresh-dependencies
~~~

This simultaneously refreshes resolution and prints the chosen version. The refresh flag is **invocation-wide**, not scoped strictly to `spring-core`; resolution refreshes across whichever configurations/tasks are actually accessed. `--dependency spring-core` filters `dependencyInsight`'s report, **not which artifact gets refreshed**.

If the issue involves a test dependency:

~~~bash
./gradlew dependencyInsight --dependency junit-jupiter --configuration testRuntimeClasspath --refresh-dependencies
~~~

If the issue is plugin resolution, inspect `plugins` and `pluginManagement.repositories` in settings; do not add Maven Central to application `repositories` thinking it changes plugin resolution sources.

### 6.3. When is refresh helpful?

- A SNAPSHOT or changing module was just published and the cache still holds an older build.
- A dynamic version like `1.+` has a new release and you want Gradle to re-evaluate immediately.
- A repository or mirror just fixed broken metadata or artifact publications.
- Gradle previously cached a negative lookup (missing module/artifact) that now exists in the repository.
- You want to verify dependency resolution against live remotes after updating credentials or repository URLs.

### 6.4. When is refresh the wrong tool?

- Java compilation errors caused by broken source code.
- `NoSuchMethodError` caused by a BOM/version conflict choosing an incompatible version; refreshing will likely pick the same graph.
- `ClassNotFoundException` because a dependency is missing from `implementation`/`runtimeOnly` or in the wrong scope.
- `bootJar` has the wrong manifest or main class.
- `UP-TO-DATE` appears when you want to force recompilation; that is a task outcome, not the dependency cache.
- A remote artifact was **published broken** and a mirror still serves stale data; fix the publisher/repository rather than endlessly refreshing clients.

Do not make `--refresh-dependencies` the default on every CI job: it adds metadata requests, hurts performance, and can cause dynamic dependencies to drift unexpectedly.

## 7. Side-by-Side: Offline vs. Refresh

| Question | `--offline` | `--refresh-dependencies` |
| --- | --- | --- |
| Queries remote repositories during dependency resolution? | No | Yes, typically verifies remotes |
| Can pick up a newly published version? | Not from remotes | Yes, if repository serves it and resolution rules select it |
| Can reuse already-cached artifacts? | Yes | Yes, after verifying they remain valid |
| What if an artifact is not cached? | Build may fail | Gradle can download it if repository permits |
| Effect on dynamic/changing TTL | Uses local data without remote check | Re-verifies regardless of old TTL |
| Deletes all cached files? | No | No |
| Deletes project `build/`? | No | No |
| Disables task output cache? | No | No |
| Guarantees tests pass? | No | No |

**Never combine both flags expecting "offline yet updated from server."** Those intents conflict: fetching updates requires reachable repositories; true offline builds can use only locally cached data. Keep them as separate steps at different times.

## 8. "Clearing the Cache" Covers Many Different Targets

### 8.1. `clean` removes outputs, not the dependency cache

~~~bash
./gradlew clean
./gradlew clean build
~~~

The Gradle Java plugin's `clean` deletes the project's build output directory (typically `build/`). It **does not delete** `GRADLE_USER_HOME/caches/modules-2`, wrapper distributions, or reset metadata TTLs.

To clean only one subproject's outputs:

~~~bash
./gradlew :app:clean
~~~

This line is **valid only** when a multi-project build actually defines `:app`; the name is illustrative. Using `:app:clean` avoids wiping outputs across other modules when only one module has an issue.

### 8.2. `--rerun-tasks` forces task actions to re-run

~~~bash
./gradlew compileJava --rerun-tasks
~~~

This is an **execution** operation, not a dependency refresh. Useful when suspecting up-to-date checks or the task cache skipped a task erroneously. Avoid enabling it by default on every CI run because it discards incremental/up-to-date savings.

### 8.3. `--no-build-cache` disables the output cache for one invocation

~~~bash
./gradlew compileJava --no-build-cache
~~~

This flag **does not force tasks to re-run** if local outputs remain valid: `compileJava UP-TO-DATE` can still appear. `FROM-CACHE` is task-output restoration; `UP-TO-DATE` is valid local outputs. Nor does this flag make Gradle re-download dependency JARs.

### 8.4. `--no-configuration-cache` disables configuration reuse

~~~bash
./gradlew help --no-configuration-cache
~~~

This forces Gradle to re-configure for that invocation without deleting downloaded dependency caches or build caches. The configuration cache typically lives under `<root-project>/.gradle/configuration-cache`; do not manually delete subdirectories inside it without a clear root cause.

### 8.5. `./gradlew --stop` only stops daemons

~~~bash
./gradlew --stop
~~~

This stops Gradle daemons for the matching Gradle version; it **does not delete caches**. Helpful before approved cache maintenance, though it cannot guarantee other Gradle processes or CI agents are not sharing the same storage. For shared caches, verify concurrency and ownership before touching any files.

## 9. Targeted Cache Purge: Prioritized Strategy

**Tier 1 — Diagnose and try non-destructive options**

1. Record the failing command, exception, module coordinates (GAV), and active repositories.
2. Run `dependencyInsight` (Gradle) or `dependency:tree` (Maven).
3. Check offline flags, dynamic/changing settings, version locks/BOMs, and network/credentials.
4. If stale metadata is suspected, run **once** with `--refresh-dependencies` or Maven `-U`.
5. Rebuild the exact task and verify output/behavior.

**Tier 2 — Isolate instead of wiping shared caches**

If Gradle shows symptoms of a corrupt local cache that refreshing didn't fix, test with a **separate Gradle User Home**. This creates a fresh dependency metadata/artifact cache **without touching other projects' caches**. With the Gradle wrapper:

~~~bash
./gradlew -g .gradle-diagnostic-home clean build
~~~

Meaning: `-g`/`--gradle-user-home` points Gradle User Home to another local directory so Gradle re-downloads needed dependencies and plugin metadata cleanly. Ensure network/repository access and disk space exist, and never commit the diagnostic directory to source control. Wrapper bootstrapping has its own distribution download rules, so ensure the wrapper distribution is available too.

If the build passes with the fresh user home while failing with the old one under the same JVM/repositories/toolchain, that is **actionable evidence pointing to the old cache/environment**, though not proof of a single corrupt artifact yet. Compare dependency graphs, repository configs, credentials, wrapper, and daemon environments.

With Maven, you can use a **temporary local repository** instead of deleting `~/.m2/repository`:

~~~bash
mvn -Dmaven.repo.local=./.m2-diagnostic-repo clean verify
~~~

Run in a project with a `pom.xml` and Maven. The dot/slash denotes a path relative to the current working directory; ensure it is never committed. This tests clean resolution without disturbing your primary local repository.

**Advantage of isolation:** preserves existing caches for forensics and avoids breaking other builds. **Trade-off:** re-downloads dependencies/plugins, uses extra disk space, and hits mirrors/networks; do not use it routinely for normal builds.

**Tier 3 — Delete only the verified artifact or directory**

Only with solid evidence that a specific local artifact is corrupt and following team policy:

- Stop and verify no process is actively using that cache region.
- Determine the **exact path** from logs and GAV coordinates rather than guessing from a JAR name.
- Confirm it lives inside the intended user home/local repo, not a shared system directory.
- Prefer **moving it to a managed backup location** for quarantine over irreversible deletion.
- Remove/quarantine only that file/version, then re-resolve online.
- Delete the backup only after builds and runtime validation pass.

**Never run** commands like `rm -rf ~/.gradle` or `rm -rf ~/.m2/repository` just to fix one dependency. You risk wiping cached plugin artifacts, local-only Maven `install`s, and data required for offline work.

## 10. Does Gradle Have a Built-in "Purge One GAV" Command?

In standard Gradle CLI, there is no universal recommended flag like `--refresh-one-module=com.example:lib`. `--refresh-dependencies` is an **invocation-wide flag** affecting resolution across requested configurations.

Gradle's file store uses checksums and binary metadata with locking and per-repository references. Consequently, "find a folder by version name and delete it" is not an official cache maintenance operation, is unsafe during concurrent builds, and can leave metadata out of sync.

When you must resolve a bad artifact, the **preferred sequence** is:

1. Use `dependencyInsight` to confirm exact module/version and origin.
2. Run `--refresh-dependencies` to verify remote state and hashes.
3. Use an isolated `-g` user home to confirm whether the local cache is responsible.
4. Only when team maintenance procedures explicitly approve manual cache edits, quarantine/remove the specific artifact directory under `modules-2/files-2.1` after stopping cache-using processes and taking a backup.
5. Re-run an online build with refresh so Gradle rebuilds consistent state; never edit binary metadata files manually.

Example **path for identification only**, not a delete command:

~~~text
~/.gradle/caches/modules-2/files-2.1/
  com.example/
    demo-library/
      1.0.0/
        <checksum-folder>/
          demo-library-1.0.0.jar
~~~

`<checksum-folder>` is a placeholder, not a literal folder name. If the real dependency is a Spring Boot starter, it pulls in dozens of transitive artifacts, BOMs, and metadata. Deleting a single starter JAR rarely resolves version conflicts or missing classes in transitive libraries.

## 11. Maven: `-o`, `-U`, and Targeted Artifact Removal

Maven offers rough counterparts with different cache mechanics. Maven's local repository typically lives at `~/.m2/repository` and holds downloaded artifacts, metadata, and locally `mvn install`ed modules.

### 11.1. Maven offline

~~~bash
mvn -o verify
~~~

`-o` enables Maven offline mode using the local repository; the build fails if plugins, parent POMs, imported BOMs, artifacts, or transitive dependencies are missing. Like Gradle, Maven offline **does not block network calls made by test code itself**.

The Maven wrapper may also need to download the Maven distribution before `mvn` ever processes `-o`; a machine lacking the Maven wrapper distribution cannot run offline just by adding `-o`.

### 11.2. Maven update check

~~~bash
mvn -U verify
~~~

Per Maven CLI semantics, `-U` forces Maven to check updates for **SNAPSHOTs and previously missing releases** under Maven resolution rules. Do not describe this flag as "always re-downloading every release JAR." For a **fixed release artifact already present** in the local repo whose file is corrupt, use targeted purge/re-resolve instead of expecting `-U` to replace it.

Like Gradle, Maven `-U` performs remote lookups. If a repository proxy lacks permissions or the network is down, refresh can fail; never combine it with `-o` expecting both offline mode and remote updates.

### 11.3. Maven `purge-local-repository`: scoping the target

The Maven Dependency Plugin provides `dependency:purge-local-repository` to remove dependencies from the local repository. **Never run this goal carelessly with no parameters**: by default it can purge the project's entire dependency tree and re-resolve everything, generating heavy network traffic.

When the target dependency **belongs to the current dependency tree**, filter with `include`:

~~~bash
mvn dependency:purge-local-repository -Dinclude=org.slf4j:slf4j-api -DreResolve=false
~~~

The command above is a syntax example for the dependency plugin; substitute the actual GAV being investigated. `include` takes `groupId:artifactId` pairs; `-DreResolve=false` prevents the goal from immediately re-resolving. Afterward run online:

~~~bash
mvn -U verify
~~~

Maven re-downloads purged artifacts when the build requires them; fixed releases must still exist in the remote repository or mirror. If an upstream removed the artifact, purging can render the project **unbuildable**.

For artifacts **outside the current dependency tree**—such as a parent POM or Maven plugin—the Maven Dependency Plugin docs describe `manualInclude`:

~~~bash
mvn dependency:purge-local-repository -DmanualInclude=org.apache:apache
~~~

This is a **documentation syntax example**, not an instruction to purge an actual parent POM on your machine. When using `manualInclude`, specify the exact target GAV and remember purging does not restore the artifact until a subsequent online resolution runs. Do not mix `manualInclude` arbitrarily with `include/exclude`.

**Important:** the purge goal itself relies on the Maven Dependency Plugin and its metadata. If the local repo/plugin is broken enough that the goal cannot run, test with an isolated repository, fix the mirror, or follow team-approved maintenance procedures.

### 11.4. Deleting one specific version via filesystem in Maven — last resort

Maven local repository layout is straightforward to read:

~~~text
~/.m2/repository/
  com/example/demo-library/1.0.0/
    demo-library-1.0.0.jar
    demo-library-1.0.0.pom
    ... metadata / checksum ...
~~~

Even so, deleting the `1.0.0` folder remains risky when:

- The artifact was installed locally via `mvn install` and does not exist on any remote.
- Another Maven build is concurrently using the same local repository.
- Repository mirrors or networks prevent re-downloading it.
- The package/version was a fixed release later removed from the server.
- Other local projects depend on custom contents in that artifact.

Prefer `purge-local-repository` and resort to manual filesystem cleanup only after verifying the exact artifact, backing it up, and confirming a reliable remote source. **Never delete an entire `groupId` directory tree** to fix a single JAR.

## 12. Runnable Spring Boot Java 17 Example to Distinguish the Three Operations

Choose either Gradle Groovy or Kotlin DSL with the same Java source. No database or runtime network is needed for the demo.

Directory tree:

~~~text
dependency-cache-demo/
├── settings.gradle            # if using Groovy
├── build.gradle               # if using Groovy
│   or settings.gradle.kts   # if using Kotlin
│   or build.gradle.kts      # if using Kotlin
└── src/main/java/com/example/cache/
    └── DependencyCacheApplication.java
~~~

**Do not place both build-script pairs in the same module** expecting both to execute. If using Maven for comparison, create a separate project with a matching POM.

### 12.1. Gradle Groovy DSL — `settings.gradle`

~~~groovy
rootProject.name = 'dependency-cache-demo'
~~~

### 12.2. Gradle Groovy DSL — `build.gradle`

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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

### 12.3. Gradle Kotlin DSL — `settings.gradle.kts`

~~~kotlin
rootProject.name = "dependency-cache-demo"
~~~

### 12.4. Gradle Kotlin DSL — `build.gradle.kts`

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
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.named<Test>("test") {
    useJUnitPlatform()
}
~~~

Both scripts define the exact same Java/Spring Boot project, dependency scopes, toolchain, and task behavior. The Spring Boot plugin adds `bootJar` when combined with the Java plugin.

### 12.5. Complete main Java class

File `src/main/java/com/example/cache/DependencyCacheApplication.java`:

~~~java
package com.example.cache;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DependencyCacheApplication {

    public static void main(String[] args) {
        SpringApplication.run(DependencyCacheApplication.class, args);
    }

    @Bean
    CommandLineRunner runDemo() {
        return args -> System.out.println("DEPENDENCY_CACHE_DEMO_OK");
    }
}
~~~

This is a console app. At startup, Spring Boot logs may appear, while the exact line **printed by application code** is:

~~~text
DEPENDENCY_CACHE_DEMO_OK
~~~

Because there is no web starter or background service, the process exits after `CommandLineRunner` finishes. Do not mistake normal exit for a dependency-cache error.

### 12.6. Java test so the build actually runs JUnit

File `src/test/java/com/example/cache/DependencyCacheApplicationTest.java`:

~~~java
package com.example.cache;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class DependencyCacheApplicationTest {

    @Test
    void verifiesJavaRuntime() {
        assertEquals(4, 2 + 2);
    }
}
~~~

The `test` task relies on `useJUnitPlatform()` and `spring-boot-starter-test` in the build script. This simple test proves `./gradlew build` executes the JUnit task without hitting any remote network during test execution.

### 12.7. Build and run

~~~bash
./gradlew --version
./gradlew clean build
java -jar build/libs/dependency-cache-demo-0.1.0.jar
~~~

With the example project name/version and default Boot classifier, `bootJar` typically generates `build/libs/dependency-cache-demo-0.1.0.jar`. If your build overrides `archiveFileName`, run the actual generated file rather than hardcoding the name.

**Prerequisites:** a Gradle wrapper or compatible installed Gradle, Java 17 toolchain, network access for the initial resolution, and valid repositories. `build.gradle` does not generate the wrapper itself.

## 13. Four Repeatable Experiments

### Experiment A — Online then offline

Inside the sample project, while online:

~~~bash
./gradlew clean build
./gradlew dependencyInsight --dependency spring-boot --configuration runtimeClasspath
~~~

Then:

~~~bash
./gradlew clean build --offline
~~~

If the offline build succeeds, the dependencies/plugins needed for this workflow are cached locally and Gradle did not need remote access to resolve them. It **does not prove an entirely different task works offline**, nor does it prove test code makes no external network calls.

If offline fails, note the missing module/plugin name. Verify whether it was downloaded while online, which repository serves it, or whether another task has a distinct classpath. **Never delete caches when the cache is simply missing data**.

### Experiment B — Refresh metadata once

~~~bash
./gradlew dependencyInsight --dependency spring-boot --configuration runtimeClasspath --refresh-dependencies
~~~

Record the selected version before and after. Because the example pins Spring Boot via the plugin/BOM, refreshing will likely keep the exact same version. This is still a valid experiment showing refresh does not "auto-upgrade all dependencies."

In a real app with SNAPSHOTs or dynamic versions, you may see the selected version update depending on repository publications and resolution policy.

### Experiment C — Cleaning outputs vs. dependency cache

~~~bash
./gradlew clean
./gradlew build --offline
~~~

`clean` deletes local outputs under `build`, yet dependencies still resolve from Gradle User Home in the offline build. If `compileJava` re-runs after `clean`, that does not mean dependencies were re-downloaded.

### Experiment D — Isolated user home without touching current caches

With network access and sufficient disk space:

~~~bash
./gradlew -g .gradle-diagnostic-home clean build
~~~

Gradle uses a separate user home and resolves/downloads dependencies, plugins, and potentially the Gradle distribution per bootstrap rules. This clarifies whether the old cache caused a failure **without disturbing** the machine's `~/.gradle`. Afterward, verify the diagnostic directory before deleting it; never commit diagnostic artifacts or caches to Git.

When testing on CI, record build duration, cache hits, network calls, and the dependency graph. Never rely on a single run, as VM performance, network conditions, and daemon warm-up introduce variance.

## 14. Command Selection Matrix by Scenario

| Scenario | Recommended check / command | What not to do |
| --- | --- | --- |
| Network down, dependencies already downloaded | Gradle `--offline` / Maven `-o` | Pass `--refresh-dependencies` expecting new versions |
| Maven SNAPSHOT recently published | `mvn -U verify`, check effective dependencies | Delete all of `~/.m2/repository` |
| Stale Gradle changing/SNAPSHOT | `--refresh-dependencies`, inspect `dependencyInsight`/TTL | Run `clean` thinking it resets metadata cache |
| Stale Gradle dynamic version | Refresh, inspect version selection and locking | Expect an offline build to pick up a new release |
| Corrupt fixed JAR in Maven local repo | Purge exact GAV (`include`/`manualInclude`), then re-resolve | Delete entire group folder or plugin repo |
| Suspect corrupt Gradle local cache | Refresh; test with isolated `-g` user home | Delete shared `~/.gradle/caches` while builds run |
| `compileJava UP-TO-DATE`, want to recompile | `--rerun-tasks` | Use `--refresh-dependencies` to force compile |
| Need to remove old build JARs | `./gradlew clean` | Delete downloaded artifacts |
| Stale configuration cache or plugin error | `--no-configuration-cache` to isolate; fix plugin/build logic | Wipe all caches |
| Task output cache unsuitable | `--no-build-cache` or `--rerun-tasks` as needed | Try disabling task cache via `--offline` |
| Repository TLS/auth/HTTP 403 error | Fix credentials, mirror, truststore, or repo config | Repeatedly wipe caches without fixing server/auth |
| CI uses caches from untrusted branches | Enforce cache permissions and output validation | Pull/push shared remote caches indiscriminately |
| Corrupt Maven parent POM in local repo | Check effective settings; `manualInclude` when appropriate | Purge entire unrelated dependency tree |
| Gradle plugin missing on offline machine | Provision wrapper/plugin cache while online | Blame the main dependency starter |

Commands must be run from the **exact module/repository root**, using real project paths, plugin versions, and source files. For instance, `:app:clean` is only valid when `settings` defines `:app`.

## 15. Security and Reproducibility Consequences

### 15.1. Caching does not replace dependency verification

Having a JAR in a local cache does not prove the artifact:

- Came from an organization-approved repository.
- Matches approved checksums or signatures.
- Is free of vulnerabilities or supply-chain tampering.
- Matches the version actually selected by BOM/dependency constraints.

Gradle provides dependency verification/locking, and Maven provides checksum policies and repository controls; establish proper supply-chain safeguards instead of trusting cache hits blindly. Never hardcode remote repository credentials in `build.gradle`/`pom.xml` or print them in logs.

### 15.2. Re-publishing the same coordinates causes inconsistency

If a publisher mutates bytes of a fixed release `1.0.0` after publishing, Developer A and CI B may end up with different checksums and cached contents. Builds "succeed" while failing reproducibility. The durable fix is **immutable release artifacts**, publishing a new version, locking versions/checksums, and investigating the publisher. Habitual refreshes cannot substitute for artifact immutability policies.

SNAPSHOTs are designed to change over time, so you must accept that offline builds use the cached snapshot while online refreshes may pull a newer one. For reproducible deployments, pin timestamped snapshots or use managed release artifacts.

### 15.3. Shared caches and concurrency

Gradle's file/metadata store uses file locking; manually deleting files while Gradle daemons/builds are using the cache can trigger hard-to-reproduce errors. In CI containers, use only cache copy/read-only sharing patterns supported by Gradle/your CI provider, avoiding ad-hoc concurrent writes from multiple processes to one cache directory.

The Maven local repository can also be shared across processes. Running `purge` or manually deleting files while another Maven build is resolving can break builds. Before cleaning anything, confirm user-home/agent scope and ensure active workflows are not disrupted.

### 15.4. Distinguishing true offline resolution failures from app networking

If `./gradlew test --offline` fails because an integration test calls a database, HTTP API, Docker Hub, or container registry, that failure comes from test networking. It does not prove Gradle violated `--offline` by contacting a Maven repository; the test process has its own network activity. Check logs by process: Gradle resolution vs. test/app/Docker.

## 16. Common Errors and Step-by-Step Investigation

### 16.1. `Offline mode: No cached version available`

Common causes: the module or its metadata is missing from Gradle User Home, dynamic version listings lack matching cached entries, or a Gradle plugin distribution is missing.

Resolution: confirm exact module/version/repositories; run a full online workflow covering those tasks; re-test offline. Never delete local data when the root problem is **missing** local data.

### 16.2. `Could not resolve all files for configuration`

This is a broad wrapper error—inspect the stacktrace or run with `--info`. Possible causes:

- Wrong coordinates or version.
- Unauthorized repository access, or broken mirror/proxy.
- Version conflict or invalid metadata.
- Offline build missing an artifact.
- Corrupt artifact file or checksum mismatch.

Identify the configuration name (`compileClasspath`/`runtimeClasspath`/`testRuntimeClasspath`), artifact, and repository before choosing between refresh and purge.

### 16.3. Gradle refresh still picks the older build

Check repository policies: was the new build actually published to that exact URL? Are dynamic/changing semantics configured? Are dependency locks/BOM/platform constraints pinning the version? Gradle may revalidate checksums and keep the local file **because the remote still serves the identical artifact**. Test with an isolated user home to separate local-cache issues from repository-serving issues.

### 16.4. Maven `-U` does not replace a fixed release JAR

`-U` follows Maven's update-checking semantics and does not promise to re-download every fixed release. If a local artifact is suspected corrupt, use `purge` with `include` on its coordinates or test with an isolated local repo. If the artifact exists only via local `mvn install`, rebuild/restore it from trusted source rather than deleting it.

### 16.5. Build still shows `FROM-CACHE` after refreshing dependencies

`FROM-CACHE` is a **task output cache hit**. If the resolved effective task inputs did not change, cached outputs remain valid even though dependency metadata was re-checked. To force task actions to execute, use `--rerun-tasks`; never confuse dependency refresh flags with task execution flags.

### 16.6. CI cache hit, yet runtime JAR is missing a class

Possible causes include missing dependency scope, a task output cache missing declared inputs, copying `-plain.jar` into a container by mistake, or wrong artifact publication. Check `runtimeClasspath`, `bootJar` outputs, manifest, Boot archive contents, and task cache policy. Re-downloading dependencies will not fix broken runtime packaging.

## 17. Hands-On Exercises with Answers

### Exercise 1. Network drops after one online build

**Question:** A project already ran `./gradlew clean build` online, and now the network is down. Which command is best to rebuild from local cache?

**Answer:** `./gradlew build --offline`. If it fails due to an uncached plugin/metadata/artifact, populate it once network returns. Never pass `--refresh-dependencies` to fetch updates while offline.

### Exercise 2. Pulling a fresh Gradle SNAPSHOT

**Question:** A SNAPSHOT was just published and Gradle must check for the update immediately without waiting for TTL. What should you use?

**Answer:** `--refresh-dependencies`, then verify the graph and behavior. It forces remote verification without guaranteeing every JAR is re-downloaded.

### Exercise 3. Does `clean` delete `modules-2`?

**Answer:** No. `clean` normally clears only local build outputs. The dependency cache in Gradle User Home stays intact, so builds after `clean` can still run offline.

### Exercise 4. Distinguishing `UP-TO-DATE` from download caching

**Question:** Logs show `:compileJava UP-TO-DATE`. Can you conclude dependencies were refreshed?

**Answer:** No. That is a task up-to-date outcome; it says nothing about whether dependency metadata was re-queried.

### Exercise 5. Corrupt Maven fixed release

**Question:** A release library `org.slf4j:slf4j-api` in the local repository is suspected corrupt. Should you delete all of `~/.m2/repository`?

**Answer:** No. Inspect stacktraces/checksums first; use the Maven Dependency Plugin with `-Dinclude=org.slf4j:slf4j-api` and verify remote availability, or test in a temporary repo to prove the hypothesis. Only purge when a trusted remote source can restore it.

### Exercise 6. Isolated user home

**Question:** `./gradlew -g .gradle-diagnostic-home clean build` succeeds while the default build fails. Can you conclude everything under `~/.gradle` is corrupt?

**Answer:** No. It only proves state/environment differs between the two user homes. Compare repositories/credentials, metadata, daemon state, and task caches before touching the shared cache.

### Exercise 7. Offline mode and plugins

**Question:** The runtime starter JAR is cached, yet the Gradle wrapper has not downloaded its distribution and Gradle Plugin Portal metadata is absent. Will `--offline` let the build run right away?

**Answer:** Unlikely; wrapper bootstrap and plugin resolution also require local tools and metadata. Provision online or configure approved internal artifacts/mirrors first.

### Exercise 8. CI switches repositories

**Question:** With the same GAV, switching from mirror A to mirror B causes Gradle to make new network requests. Is the cache broken?

**Answer:** Not necessarily. Gradle stores metadata per repository identity to avoid mixing sources; switching mirrors can require re-resolution. Verify repository policy and artifact identity rather than copying cache files manually.

### Exercise 9. Maven manual purge

**Question:** A parent POM is not in the dependency tree yet needs targeted purging. Which Maven parameter fits?

**Answer:** `manualInclude` with exact `groupId`/`artifactId` per Maven Dependency Plugin docs, after confirming the parent/plugin artifact needs purging and a replacement source exists. Avoid purging all dependencies.

### Exercise 10. Does a "green offline build" guarantee a safe release?

**Answer:** No. Releases still require dependency verification/locking, tests, artifact inspection, security review, and provenance. Offline mode only says resolution avoided remote access during that run—not that cached data is trustworthy or QA is complete.

## 18. Decision Checklist Before Touching Caches

- [ ] Classified the error accurately: dependency resolution, plugin, configuration, task output, source code, or runtime.
- [ ] Recorded exact **group:artifact:version**, configuration, repository, and failing command.
- [ ] Inspected `dependencyInsight`/`dependency:tree` rather than relying on JAR filenames on disk.
- [ ] For offline builds, ensured wrappers, plugins, and dependencies for requested tasks are cached.
- [ ] For stale SNAPSHOT/dynamic versions, used `--refresh-dependencies` or Maven `-U` purposefully, knowing their limits.
- [ ] Never confused `clean` with wiping the Gradle dependency cache or Maven local repo.
- [ ] Never confused `--no-build-cache`/`--no-configuration-cache`/`--rerun-tasks` with dependency refreshing.
- [ ] Preferred an **isolated** user home/repository before deleting shared caches.
- [ ] If a purge is unavoidable, targeted the exact artifact/version with a backup and confirmed online restore source.
- [ ] Verified no concurrent processes are using the cache directory being modified.
- [ ] Avoided deleting local-only Maven `install` artifacts, unpublished internal JARs, or other projects' metadata.
- [ ] Never ran unchecked `rm -rf` scripts against absolute paths, especially on CI/shared agents.
- [ ] Re-ran a clean build and smoke-tested the production artifact afterward.
- [ ] Documented root cause, cache scope touched, and reproduction steps for CI.

**Conclusion:** **Offline** chooses **not to query remotes** and accepts local-data limits; **refresh** **re-verifies remote resolution** without necessarily re-downloading every file; **targeted cache purge** is a **last-resort** maintenance action scoped strictly to verified suspect data. Most issues are resolved cleanly by fixing configuration/repositories, running one verified refresh, or testing with an isolated user home instead of wiping everything.

## 19. Official Documentation

- Gradle — Dependency Caching: https://docs.gradle.org/current/userguide/dependency_caching.html
- Gradle — Command-Line Interface (`--offline`, `--refresh-dependencies`, `--rerun-tasks`, `-g`): https://docs.gradle.org/current/userguide/command_line_interface.html
- Gradle — Gradle User Home: https://docs.gradle.org/current/userguide/directory_layout.html
- Gradle — Dependency Insight: https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html
- Gradle — Configuration Cache: https://docs.gradle.org/current/userguide/configuration_cache.html
- Gradle — Build Cache: https://docs.gradle.org/current/userguide/build_cache.html
- Apache Maven — Maven CLI Options: https://maven.apache.org/ref/current/maven-embedder/cli.html
- Apache Maven — Local Repositories: https://maven.apache.org/repositories/local.html
- Apache Maven Dependency Plugin — Purging Local Repository Dependencies: https://maven.apache.org/components/plugins/maven-dependency-plugin/examples/purging-local-repository.html
- Apache Maven Dependency Plugin — purge-local-repository goal: https://maven.apache.org/plugins/maven-dependency-plugin/purge-local-repository-mojo.html
- Spring Boot 3.3 Gradle Plugin — Packaging: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html

When upgrading the Gradle wrapper, Maven version, or Spring Boot plugin, verify flag semantics against **documentation for your actual version**. Never default to "corrupt cache" as a diagnosis before checking which artifact Gradle/Maven resolved, from which repository, and what the build is actually missing.
