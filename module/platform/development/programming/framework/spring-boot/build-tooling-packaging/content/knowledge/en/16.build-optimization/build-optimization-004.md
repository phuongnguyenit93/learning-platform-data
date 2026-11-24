# Applying the Gradle Build Cache and Controlling Task Inputs

## 1. Problem and Objectives

In a Spring Boot project using Gradle, a build typically compiles Java, processes resources, runs tests, performs quality checks, and packages the application. Some expensive steps **have already run with the exact same inputs** on another machine or in a previous CI run. The **Gradle Build Cache** lets you reuse **outputs of cacheable tasks** instead of re-running the operation when Gradle determines the previous result is still valid.

The key is not merely passing `--build-cache`: if **task inputs/outputs are under-declared or declared inaccurately**, the cache can return stale results, become non-reproducible, or introduce subtle bugs. That is why this topic combines two practices: **enabling the build cache** and **modeling inputs/outputs accurately**.

After this lesson, you will be able to:

1. Distinguish `UP-TO-DATE`, `FROM-CACHE`, and normal task execution; understand how the build cache differs from the dependency cache and configuration cache.
2. Enable the local build cache via `--build-cache` or `org.gradle.caching=true`; know when a remote cache is warranted for CI and development teams.
3. Declare `@Input`, `@InputFile`, `@InputFiles`, `@OutputFile`, `@OutputDirectory`, and normalized paths for a custom Gradle task.
4. Use `@CacheableTask` safely, build a deterministic file-generating task, and observe cache hits/misses via Gradle Wrapper commands.
5. Identify hidden inputs such as clocks, environment variables, network calls, file ordering, Java toolchains, or system properties and either model them on the task or opt the task out of caching.
6. Diagnose why a cache miss occurred and design local/CI policies aligned with security, quality, and reproducibility.

**Example scope:** Spring Boot 3.3.5, Java 17, and a Gradle Wrapper compatible with the chosen plugin versions. These are **illustrative versions**, not a recommendation for every current project. Real projects should use an appropriate Spring Boot/Gradle/JDK compatibility matrix and check APIs if using a very old Gradle release.

## 2. Four Mechanisms Commonly Lumped Together as "Cache"

| Mechanism | What does it store or remember? | Question it answers | Common signal |
| --- | --- | --- | --- |
| **Up-to-date checks / incremental build** | Task input/output fingerprints and output state in the workspace | "Has this task already completed with unchanged inputs/outputs in this workspace?" | `UP-TO-DATE` |
| **Gradle Build Cache** | **Task output artifacts** indexed by cache key of inputs/task implementation | "Is there an equivalent result from an earlier build to restore?" | `FROM-CACHE` |
| **Dependency cache** | Module metadata and artifacts from Maven/Gradle repositories | "Has this JAR/POM already been downloaded or does its metadata exist in cache?" | Repository resolution may skip re-downloading |
| **Configuration Cache** | Result of the **configuration** phase: task graph and related configured state | "Can we skip re-configuring the build?" | Configuration cache reused log message |

Additionally, the **Gradle Daemon** keeps a JVM running and holds certain in-memory state to cut startup time, which is also not a task-output build cache.

### Example of two different states

~~~text
Run 1: :compileJava                  (executed)
Run 2: :compileJava UP-TO-DATE       (outputs still exist in workspace)
Run 3: :compileJava FROM-CACHE       (outputs removed, restored from cache)
~~~

This is an **illustrative state sequence**, not guaranteed output on every project. Gradle only prints `FROM-CACHE` if the task is eligible, caching is enabled, and a matching entry exists. A task might not be cacheable, or caching might be enabled yet still execute because no entry exists for that key.

**Do not equate them:** the Maven local repository (`~/.m2/repository`), Gradle dependency cache, or IDE "Download dependencies" **does not replace** the Gradle Build Cache. Fetching Spring Boot starters from the dependency cache only avoids downloads; it does not turn `JavaCompile` or `Test` into cache hits.

## 3. How Does Gradle Decide Whether to Reuse Task Outputs?

A task has a set of **inputs**, an **implementation**, **outputs**, and optionally conditions governing when caching is safe. For tasks with caching enabled, Gradle computes a **build cache key** from the information needed to determine output equivalence.

Logic flow:

~~~text
Input values + input files + normalized paths
           + relevant classpath/implementation/plugin/toolchain
           |
           v
     fingerprint + build cache key
           |
           +--> Existing outputs valid? ----------> UP-TO-DATE
           |
           +--> Matching entry in cache? ---------> FROM-CACHE
           |
           +--> No -------------------------------> EXECUTE task
                                                       |
                                                       v
                                                Verify outputs
                                                       |
                                                       v
                                              Store in cache if allowed
~~~

**The cache key is not based on task name alone.** For custom tasks, Gradle also considers annotated properties, task type, implementation classpath, and build logic affecting the result. Two runs of `generateBuildLabel` with different inputs are not treated as equivalent.

Key rules:

- **Inputs changed**: Gradle must execute or look up the cache entry matching the new fingerprint.
- **Outputs deleted**: Gradle cannot say `UP-TO-DATE`; if the cache has a matching entry, it can restore outputs via `FROM-CACHE`.
- **Outputs intact**: Gradle can report `UP-TO-DATE` without reading the build cache, even if caching is enabled.
- **Task not opted in**: a custom task type is **not cacheable by default** merely by having `@OutputFile`; `@CacheableTask` is an explicit opt-in.
- **Task with no declared outputs**: Gradle generally cannot optimize it with the standard task-output cache.
- **Some built-in Gradle tasks are already cacheable**, such as `JavaCompile` and `Test`, but do not assume **every** `Jar`, `Copy`, `bootJar`, or third-party plugin task is cached automatically.

**Cache value depends on reproducibility:** identical inputs and task implementation must yield the same observable result. If a task reads a value Gradle does not know about, identical keys can no longer guarantee identical outputs.

## 4. Enabling Local Build Cache with the Wrapper

### 4.1. Enable for a single run

At the project root where `gradlew` and `gradlew.bat` reside.

Linux/macOS:

~~~bash
./gradlew --version
./gradlew --build-cache build
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat --build-cache build
~~~

The `--build-cache` option activates the build cache for this invocation. The default local cache is managed by Gradle under **Gradle User Home**; you do not need to create a cache directory manually to use the default setup.

### 4.2. Enable persistently via `gradle.properties`

In the project's `gradle.properties` file, add:

~~~properties
org.gradle.caching=true
~~~

Then run:

~~~bash
./gradlew build
~~~

When you want to temporarily disable the build cache for an investigation:

~~~bash
./gradlew --no-build-cache build
~~~

`--no-build-cache` does not delete stored cache entries. Also, do not delete all of `~/.gradle` just to test whether a task hits the cache: that directory also holds dependency caches, Wrapper distributions, Gradle state, and other data.

### 4.3. How to verify a cache hit properly

A sound observation sequence:

~~~bash
./gradlew --build-cache build --info
./gradlew --build-cache build --info
./gradlew --build-cache clean build --info
~~~

- First run: many tasks execute because neither outputs nor cache entries exist yet.
- Second run: with unchanged inputs/outputs, many tasks can report `UP-TO-DATE`.
- Third run: `clean` removes outputs in the build directory; **cacheable** tasks can restore results from the local/remote cache and show `FROM-CACHE`.

**Not every task is guaranteed to report `FROM-CACHE`.** A task may be non-cacheable, depend on time/network, or lack a matching entry. Read `--info` output to see why.

**Do not use `--rerun-tasks` to "test cache hits"**: this option forces tasks to re-execute, bypassing normal reuse. It is helpful for investigating outputs or task behavior, not for measuring outputs loaded from the build cache.

## 5. Controlling Inputs and Outputs: Foundational Rules

Gradle must know **every value that can alter a task's output**. For custom task types, use Gradle's supported properties and annotations.

| Annotation | Declared data | Meaning |
| --- | --- | --- |
| `@Input` | String, number, boolean, enum, or matching property value | A scalar value controlling the result |
| `@InputFile` | A single input file | Gradle fingerprints the file, detecting content/relevant path changes |
| `@InputFiles` | A collection of input files | Tracks multiple sources; requires proper path sensitivity/normalization |
| `@InputDirectory` | An input directory | Tracks enclosed files and relative paths when configured |
| `@Classpath` | JVM classpath | Normalization tailored to JARs/classpaths, order-sensitive |
| `@CompileClasspath` | Compile classpath | Normalization for compilation API where appropriate |
| `@OutputFile` | A single generated file | Tells Gradle which artifact the task owns |
| `@OutputDirectory` | A generated directory | Lets Gradle manage the task's output set |
| `@Nested` | An object structure with annotated properties | Composes multi-property models |
| `@Internal` | Property that is not a tracked input/output | Use only if it truly does not affect the result |

**Never mark a property `@Internal` to hide an input that changes output.** Gradle could treat the task as valid when the actual result should differ. That produces an **incorrect cache**, not just a slow cache.

### Path sensitivity and relocatability

Gradle can include **file paths** in fingerprints. If Machine A checks out at `/home/dev/project` while Machine B checks out at `/agent/work/project`, differing absolute paths cause cache misses even with identical source contents.

Options to understand:

- `PathSensitivity.ABSOLUTE`: considers the full absolute path; usually unsuitable for remote caches shared across workspaces.
- `PathSensitivity.RELATIVE`: considers paths relative to the input root; suited for directories whose file layout carries meaning.
- `PathSensitivity.NAME_ONLY`: considers only the filename, not its directory location; use only when filename alone affects output.
- `PathSensitivity.NONE`: ignores input file path; suited for **a single file** when the task reads content only and ignores filename/path.

Per Gradle task best practices, `NONE` is usually preferred for a single input file if filename does not affect output, and `RELATIVE` for directories/file trees where relative paths matter. For classpaths, **`@Classpath` or `@CompileClasspath`** is usually better than applying generic path normalization.

**Do not pick normalization merely to boost cache hits** if paths actually affect output. For example, if a task generates an index containing filenames, the filenames are meaningful inputs and must not be ignored.

## 6. Runnable Example: Custom Task Generating a Resource from an Input File

This example uses **Gradle Groovy DSL** to define a cacheable custom task type `GenerateBuildLabel`. The task reads `src/main/build-label.txt`, writes `build/generated/build-label.properties`, and registers it as an application resource. A Spring Boot main class prints the value from that resource when running the executable JAR.

Advantages of this setup: you can **prove the exact output is reproduced** after `clean`, observe updated values when inputs change, and inspect both the file on disk and the resource packaged inside the Boot JAR.

### 6.1. Project structure

~~~text
cache-demo/
├── settings.gradle
├── build.gradle
├── gradle.properties
├── gradlew, gradlew.bat, gradle/wrapper/
└── src/
    └── main/
        ├── build-label.txt
        └── java/com/example/cache/CacheDemoApplication.java
~~~

The example assumes the project has a valid Gradle Wrapper and Java 17. Gradle must be able to resolve Spring Boot plugins/dependencies from organization-approved repositories. You do not need Maven files since this lesson covers the Gradle Build Cache.

### 6.2. `settings.gradle`

~~~groovy
rootProject.name = 'cache-demo'
~~~

### 6.3. `gradle.properties`

~~~properties
org.gradle.caching=true
~~~

This is the **project build-cache flag**, not the Configuration Cache flag. If an organization prefers enabling it only in CI or via CLI, omit this file and pass `--build-cache` to commands.

### 6.4. `src/main/build-label.txt`

~~~text
alpha
~~~

This is a UTF-8 text file you create explicitly. The task below calls `trim()`, so a trailing newline does not affect the printed value. Changing `alpha` to `beta` alters **input file content**, forcing Gradle to compute a new fingerprint.

### 6.5. Complete `build.gradle` for the example

~~~groovy
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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

tasks.named('test') {
    useJUnitPlatform()
}

@CacheableTask
abstract class GenerateBuildLabel extends DefaultTask {

    @InputFile
    @PathSensitive(PathSensitivity.NONE)
    abstract RegularFileProperty getInputFile()

    @Input
    abstract Property<String> getLabelPrefix()

    @OutputFile
    abstract RegularFileProperty getOutputFile()

    @TaskAction
    void generate() {
        String name = inputFile.get().asFile.getText('UTF-8').trim()
        File target = outputFile.get().asFile
        target.parentFile.mkdirs()
        target.setText('build.label=' + labelPrefix.get()
                + name + '\n', 'UTF-8')
    }
}

def buildLabelTask = tasks.register('generateBuildLabel', GenerateBuildLabel) {
    inputFile.set(layout.projectDirectory.file('src/main/build-label.txt'))
    labelPrefix.set(providers.gradleProperty('labelPrefix').orElse('demo-'))
    outputFile.set(layout.buildDirectory.file('generated/build-label.properties'))
}

tasks.named('processResources') {
    from(buildLabelTask)
}

springBoot {
    mainClass = 'com.example.cache.CacheDemoApplication'
}
~~~

This snippet is the **complete `build.gradle`** for the sample project, not Java source. In an existing project with a different `build.gradle`, **do not overwrite the whole build file**; integrate the task type and wiring into existing build logic after checking plugins/versions/repositories.

### 6.6. Why is this task safely cacheable?

1. **`@CacheableTask`** marks the custom task type as eligible to store/restore outputs when Gradle build cache is enabled. Simply declaring inputs/outputs does not automatically make a custom task cacheable.
2. **`@InputFile`** points to `build-label.txt`; Gradle tracks file contents. Because the code ignores input filename/path, `@PathSensitive(PathSensitivity.NONE)` fits this task.
3. **`@Input`** on `labelPrefix`; when invoked with `-PlabelPrefix=release-`, the value contributes to the fingerprint, ensuring `release-alpha` never mistakenly reuses a `demo-alpha` cache entry.
4. **`@OutputFile`** defines **a single output file** under `build/generated`. Gradle knows where to store/restore results, and the task never mutates checked-in source files.
5. **`@TaskAction`** reads only declared inputs, builds a deterministic string, and writes UTF-8. It uses no system clock, network, randomness, hostname, or secrets.
6. **`tasks.register`** registers the task lazily; `processResources.from(buildLabelTask)` consumes the task output as a resource and lets Gradle infer the producer/consumer task dependency. The metadata-generating task runs only when required by the task graph.
7. **Spring Boot `bootJar`** pulls resources from the main source set via `processResources`, so `build-label.properties` gets packaged inside `BOOT-INF/classes` of the executable JAR.
8. The generated resource is verified **by file content and runtime output**, not merely by Gradle's `UP-TO-DATE` line.

**Limitation:** the input is a single file, so `PathSensitivity.NONE` is right. If you change the task to read **an entire directory** and emit outputs preserving relative paths, switch to `@InputFiles` or `@InputDirectory` with `RELATIVE` and implement the mapping accordingly. If output selection depends on filename, include the filename in the input model.

### 6.7. `src/main/java/com/example/cache/CacheDemoApplication.java`

~~~java
package com.example.cache;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CacheDemoApplication {

    public static void main(String[] args) throws IOException {
        Properties props = new Properties();

        try (InputStream in = CacheDemoApplication.class.getClassLoader()
                .getResourceAsStream("build-label.properties")) {
            if (in == null) {
                throw new IllegalStateException("Missing build-label.properties");
            }
            props.load(in);
        }

        System.out.println("BUILD_LABEL=" + props.getProperty("build.label"));
        SpringApplication.run(CacheDemoApplication.class, args);
    }
}
~~~

This is a complete Java 17+ class with a valid `main` method. Because the basic Spring Boot Starter has no web server, the app starts and exits after printing logs; **that is normal**. The printed value comes from the **resource file generated by the custom Gradle task**, not from external environment variables.

This file compiles/runs once Spring Boot dependencies are resolved via Gradle. **Do not run `javac CacheDemoApplication.java` standalone** without Spring Boot on the classpath; use the Wrapper as shown in Section 7 to compile and package completely.

## 7. Testing Three States: EXECUTED, UP-TO-DATE, FROM-CACHE

### 7.1. First run — generate output

Linux/macOS:

~~~bash
./gradlew --version
./gradlew --build-cache generateBuildLabel --info
cat build/generated/build-label.properties
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat --build-cache generateBuildLabel --info
Get-Content .\build\generated\build-label.properties
~~~

Exact expected output file content:

~~~properties
build.label=demo-alpha
~~~

The task log shows `> Task :generateBuildLabel` without `UP-TO-DATE` or `FROM-CACHE` on a first run with an empty cache. If the cache already holds an entry from an earlier run, even the first run of **this exercise** may report `FROM-CACHE`. Do not assume status from command count alone.

### 7.2. Second run — unchanged workspace

~~~bash
./gradlew --build-cache generateBuildLabel --info
~~~

When inputs/outputs and task implementation have not changed, Gradle can display:

~~~text
> Task :generateBuildLabel UP-TO-DATE
~~~

This means **no action execution needed** because the output file is already present with a valid fingerprint. Do not mistake this for proof that the task loaded data from the build cache; no cache restoration occurred.

### 7.3. Third run — delete outputs and restore from cache

~~~bash
./gradlew --build-cache clean generateBuildLabel --info
cat build/generated/build-label.properties
~~~

On PowerShell:

~~~powershell
.\gradlew.bat --build-cache clean generateBuildLabel --info
Get-Content .\build\generated\build-label.properties
~~~

`clean` deletes the `build` output directory without deleting the local build cache managed by Gradle. If a cache entry exists and the task is eligible, the log can show:

~~~text
> Task :generateBuildLabel FROM-CACHE
~~~

The restored file still contains:

~~~properties
build.label=demo-alpha
~~~

If Gradle executes the task instead of `FROM-CACHE`, use `--info` to read why. Likely causes include a differing key, an uncached prior run, disabled caching, or an unstable implementation classpath. **Never force an expected outcome**: actual observed state is the verification data.

### 7.4. Mutate an input and observe a cache miss

On Linux/bash, write new content:

~~~bash
printf 'beta\n' > src/main/build-label.txt
./gradlew --build-cache generateBuildLabel --info
cat build/generated/build-label.properties
~~~

PowerShell:

~~~powershell
Set-Content -Path .\src\main\build-label.txt -Value 'beta'
.\gradlew.bat --build-cache generateBuildLabel --info
Get-Content .\build\generated\build-label.properties
~~~

New output file:

~~~properties
build.label=demo-beta
~~~

Gradle must not reuse the `demo-alpha` entry for the new inputs. It either **executes the task** or restores a **separate cached entry** for `beta` if one was created previously.

To test the non-file `@Input` property:

~~~bash
./gradlew --build-cache generateBuildLabel -PlabelPrefix=release- --info
cat build/generated/build-label.properties
~~~

Expected output:

~~~properties
build.label=release-beta
~~~

When switching back to `labelPrefix=demo-` while keeping `beta`, Gradle can restore the corresponding earlier cache entry. **Do not assume Gradle tracks files only:** `@Input` values are equally critical parts of the cache key.

## 8. Verifying the Generated File Reaches the Spring Boot Executable JAR

After resetting the input file to `alpha` (if you want to compare against the baseline), build the application:

~~~bash
./gradlew --build-cache clean bootJar
jar tf build/libs/cache-demo-0.0.1-SNAPSHOT.jar |
  grep 'BOOT-INF/classes/build-label.properties'
java -jar build/libs/cache-demo-0.0.1-SNAPSHOT.jar
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --build-cache clean bootJar
jar tf .\build\libs\cache-demo-0.0.1-SNAPSHOT.jar |
    Select-String 'BOOT-INF/classes/build-label.properties'
java -jar .\build\libs\cache-demo-0.0.1-SNAPSHOT.jar
~~~

If the input is `alpha` with default prefix `demo-`, the line printed by application code is:

~~~text
BUILD_LABEL=demo-alpha
~~~

If the input is `beta` or another prefix, the value reflects **the current build's inputs**. Spring Boot banners/logs that vary by environment and timing will also appear.

**Key takeaway:** do not check only that `generateBuildLabel` reported `FROM-CACHE`; verify that consumer `processResources` uses the **producer's exact output** and `bootJar` packages the generated/restored file. A useful build-cache hit must yield the **correct artifact**, not just finish fast.

If Gradle reports duplicate resources or multiple tasks writing `build-label.properties`, locate the other output declaration and separate the paths. Two tasks **must not overwrite the same output file/directory** without explicit ownership modeling.

## 9. Hidden Inputs That Cause Unsafe Cache Hits

**Cache correctness** outweighs cache hit rate. Check every data source read by a task against properties known to Gradle.

| Task reads or uses | Risk if undeclared | How to control |
| --- | --- | --- |
| Source file or template | Content changes while Gradle keeps the old cache key | `@InputFile`/`@InputFiles` with suitable normalization |
| CLI/build property parameters | Flag changes yet output comes from old key | `@Input` or `Provider` wired into an annotated property |
| Dependency/tool classpath | Library/compiler changes yield different output | `@Classpath`/`@CompileClasspath` or standard plugin tasks |
| JDK/toolchain affecting bytecode | Compiled with a different Java version missing from fingerprint | Declare toolchain and let standard plugins track compiler config |
| Environment variable | CI and local use different values unknown to Gradle | Model output-affecting vars as inputs; never cache unsafe secrets |
| Current time/clock | Every run embeds a different timestamp despite identical inputs | Omit timestamps from outputs or pass a fixed time as an explicit input |
| Random/UUID | Output changes without key changing | Pass a declared seed if needed; do not cache non-deterministic output |
| Hostname/IP/user home | Cache is non-relocatable across developers/CI | Avoid embedding paths/hostnames in outputs; declare input or disable cache if needed |
| Network request/remote API | Responses change outside Gradle's control | Snapshot data as a managed input or disable caching for the task |
| System property/locale/timezone | Alters formatting/test behavior | Declare affecting properties; pin locale/timezone |
| Input file list ordering | Output differs when iteration order changes | Use order-aware inputs and iterate deterministically |
| File outside declared inputs | Task reads a "secret" file Gradle does not watch | Declare the file or redesign task to avoid hidden state |

Bad example:

~~~groovy
tasks.register('generateBadVersion') {
    outputs.file(layout.buildDirectory.file('generated/version.txt'))
    doLast {
        def f = layout.buildDirectory.file('generated/version.txt').get().asFile
        f.parentFile.mkdirs()
        f.text = 'built-at=' + new Date().toString()
    }
}
~~~

This task emits clock-dependent contents while **the clock is not modeled as an input**. Declaring outputs alone can cause the task to be marked `UP-TO-DATE` when its result should change; adding caching carelessly makes the bug worse. This snippet is **intentionally an anti-pattern**—do not use it in production pipelines.

The right fix depends on business needs. If `built-at` metadata is unnecessary, omit the timestamp. If the release pipeline needs a timestamp, pass an explicit, stable one like `-PreleaseTimestamp=...`, declare it via `@Input`, and manage it via version/CI. If output truly must reflect the current wall clock, **do not opt that task into the Build Cache**.

## 10. Choosing the Right Normalization for Input Files

### 10.1. Single input file independent of name

In `GenerateBuildLabel`:

~~~groovy
@InputFile
@PathSensitive(PathSensitivity.NONE)
abstract RegularFileProperty getInputFile()
~~~

The task only reads **UTF-8 content**. Moving the checkout from `/home/dev/cache-demo` to `/agent/cache-demo` with identical file content preserves the same cache-key contribution for that input file.

### 10.2. Directory of multiple files preserving relative paths

For a task reading a file tree like `src/main/templates` whose output depends on each template's relative location, use this pattern:

~~~groovy
@InputDirectory
@PathSensitive(PathSensitivity.RELATIVE)
abstract DirectoryProperty getTemplateDirectory()
~~~

This is a **snippet belonging to another custom task class**, not standalone code. You must add `import org.gradle.api.file.DirectoryProperty`, output properties, a task action, and task registration before use. `RELATIVE` prevents different checkout root paths from causing useless misses, while moving `a/index.html` to `b/index.html` remains a meaningful change.

### 10.3. Java classpath

An analyzer or compiler task operating on dependencies might need:

~~~groovy
@Classpath
abstract ConfigurableFileCollection getAnalysisClasspath()
~~~

This is a **declaration snippet**; import `org.gradle.api.file.ConfigurableFileCollection` and `org.gradle.api.tasks.Classpath`. Gradle applies classpath/JAR-specific normalization instead of raw absolute paths. For Java compile classpaths, `@CompileClasspath` is often appropriate because it ignores changes irrelevant to compilation APIs. Prefer standard Java plugin tasks whenever possible rather than writing custom compiler tasks with incomplete inputs.

**Never annotate the same input file with conflicting path annotations.** Choose the annotation based on the data's **actual meaning** for the output.

## 11. Remote Build Cache: Sharing Results Across Teams or CI

**Local cache** helps a single developer switch branches, re-run tasks after `clean`, or iterate repeatedly. **Remote cache** lets multiple machines share outputs of cacheable tasks, especially useful when CI builds on clean workers and developers need the same outputs.

Gradle configuration can go in `settings.gradle[.kts]` inside a `buildCache` block. Conceptual Groovy DSL example:

~~~groovy
// settings.gradle: cache config portion only, combined with rootProject.name
import org.gradle.caching.http.HttpBuildCache

buildCache {
    local {
        enabled = true
    }
    remote(HttpBuildCache) {
        url = uri('https://build-cache.example.org/cache/')
        push = System.getenv('CI') == 'true'
        credentials {
            username = providers.gradleProperty('cacheUser').orNull
            password = providers.gradleProperty('cachePassword').orNull
        }
    }
}
~~~

**This example targets a hypothetical server and will not run without a real cache service.** Replace the placeholder URL with your organization's approved remote build cache address; supply credentials through a CI secret store or secure environment—**never commit passwords to the repository**. The server must implement the Gradle HTTP Build Cache protocol.

Recommended sharing model:

- Developers **read** from the remote cache (pull) but **do not push** to the shared cache.
- Trusted, tested CI jobs in clean environments may **push** when organization policy permits.
- CI and developers use compatible Gradle Wrapper/JDK/plugin versions; differing implementations/inputs produce different keys.
- Protect the remote cache with TLS, authentication, and least-privilege access control; partition namespaces or services across trust levels.
- Monitor cache hit rates, network/storage costs, and data security. A slow remote cache can make builds slower if outputs are tiny or misses are frequent.

**Security warning:** the build cache can hold compiled outputs, generated resources, or test reports. Never cache tasks that embed **secrets** into outputs; never let untrusted branches/jobs push results that critical projects trust. A remote cache is not merely a speedup tool—it is an **artifact source** requiring governance.

If you only want to use the local cache, **omit** the `remote` block. `--build-cache` or `org.gradle.caching=true` is sufficient to practice all task input/output mechanics.

## 12. Build Cache in Spring Boot Gradle: What Should You Expect?

A typical Spring Boot project includes tasks such as:

| Task | Role | Caching behavior to understand |
| --- | --- | --- |
| `compileJava` | Compiles Java sources | Gradle `JavaCompile` supports caching when properly configured; compiler args, sources/classpath/toolchain are key inputs |
| `compileTestJava` | Compiles Java tests | Cacheable; test source/classpath changes produce a new key |
| `test` | Runs declared unit/integration tests | Gradle `Test` can be cacheable when inputs, test runtime, JVM args, and affecting environment are modeled accurately |
| `processResources` | Copies/filters resources | Simple copy tasks are rarely worth task-output caching; up-to-date checks often suffice |
| `bootJar` | Packages the Spring Boot executable JAR | Do not assume `bootJar` is cacheable by default in every plugin version; check logs and metadata for your version |
| `bootRun` | Runs the application | Long-lived process task with side effects; generally should not treat running an app as cached output |
| `generateBuildLabel` | Sample custom task | Cacheable only when inputs/outputs and `@CacheableTask` are declared as in Section 6 |

**Caching does not replace testing.** When Gradle reports `test FROM-CACHE`, it trusts that the task has valid outputs for identical inputs; if tests read the network, secrets, or an external database without declaring them properly, reuse may be unsafe. For integration tests tied to live environments, consider isolation, state snapshotting, or disabling caching so they always execute.

Similarly, `bootRun` starts a Spring Boot application as a runtime operation with external side effects (connecting to databases, binding ports, sending messages). Never try to cache "running an application" like a deterministic file-producing task.

### Reproducible builds

For local and CI cache hits to remain both high and correct:

1. Use a version-controlled **Gradle Wrapper**, not arbitrary global Gradle installs.
2. Use **Java Toolchains** for compiler/test tasks when the project requires a specific JDK.
3. Manage dependency versions intentionally and consider locking/verification if required by policy; avoid dynamic/changing versions that hurt reproducibility.
4. Do not embed absolute checkout paths or arbitrary timestamps into generated files.
5. Separate build-state inputs (sources, version, config, flags) from runtime secrets and production data.
6. Test both **cache-cold builds** and **cache-hit builds** to catch undeclared inputs.

## 13. Diagnosing Cache Misses: Useful Commands

### 13.1. Enable reason logging

Linux/bash:

~~~bash
./gradlew --build-cache generateBuildLabel --info
./gradlew --build-cache clean generateBuildLabel --info
./gradlew --build-cache build --info
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --build-cache generateBuildLabel --info
.\gradlew.bat --build-cache clean generateBuildLabel --info
.\gradlew.bat --build-cache build --info
~~~

Gradle typically explains non-cacheable tasks, input/implementation changes, cache keys, or disabled caching under `--info` or `--debug`. `--debug` emits massive output that may include sensitive data; use only when needed and sanitize logs before sharing.

### 13.2. Investigation table

| Symptom | Common explanation / origin | How to address |
| --- | --- | --- |
| Task stays `UP-TO-DATE`, never `FROM-CACHE` | Outputs still exist in workspace, no need to load from cache | Run `clean` before the task and read `--info` |
| Task always executes after `clean` | No cache entry yet, cache disabled, task non-cacheable, or key changed | Confirm `--build-cache`, `@CacheableTask`, inputs/outputs, and logs |
| Gradle reports caching disabled due to missing outputs | Task declares no real outputs or produces no file artifacts | Declare `@OutputFile`/`@OutputDirectory` where appropriate |
| Cache miss when changing checkout directory | Absolute input paths or hardcoded paths in output | Use `PathSensitivity.NONE/RELATIVE` as appropriate; avoid absolute paths |
| Cache miss despite unchanged sources | JDK/plugin/Gradle version, build script, compiler args, or classpath changed | Compare Wrapper, toolchain, dependency graph, cache keys, and logs |
| Task reports `UP-TO-DATE` with stale/wrong output | An output-affecting input was undeclared | Add `@Input`/`@InputFile`, remove bad assumptions, add tests |
| Task `FROM-CACHE`, yet JAR has old resource | Missing producer/consumer wiring or packaging uses a different resource | Use `from(taskProvider)` and inspect `BOOT-INF/classes` |
| Cache hit, yet integration test misses current DB state | Test depends on undeclared mutable external state | Pin test fixture/container versions or disable caching for that task |
| Remote cache returns 401/403 | Missing credentials or lacking push/pull permissions | Check CI secrets, read/write policy, TLS, and endpoint |
| Remote cache slower than running the task | High network latency/serialization overhead, tiny outputs | Use local cache, disable remote for tiny tasks, or tune cache service |
| Cache entry exists but fails to load | Corrupt entry, key mismatch, or differing metadata/implementation | Read error logs and clean only the affected entry per guidance; do not wipe Gradle home |
| Overlapping task output directories | Two producers writing to the same path | Assign distinct output ownership, separate paths, or fix dependencies |
| Build passes with `--offline` | Local artifacts/caches were sufficient | Do not conclude remote cache/repository connectivity is healthy |
| Tasks re-run due to `--rerun-tasks` | User explicitly forced execution instead of reuse | Remove the flag when evaluating cache hits |

**Rule of thumb:** a cache miss can be the **correct behavior** when inputs change. Do not treat every miss as a bug to force into a hit.

## 14. CI Cache Correctness Verification Workflow

Before sharing a remote cache across developers:

1. **Capture baseline:** Gradle Wrapper/JDK/Boot plugin versions, build command, cache flags, and tasks expected to be cached.
2. **Cold build:** run on a clean workspace with an empty cache if possible; record test results and checksums of generated artifacts.
3. **Local reuse:** re-run unchanged; verify `UP-TO-DATE`, then after `clean` verify eligible tasks report `FROM-CACHE`.
4. **Input mutation:** change **one** declared input such as `build-label.txt` or `-PlabelPrefix`; confirm new outputs and a new cache key.
5. **Change back:** revert the input to baseline and delete outputs; verify the original cached result restores accurately if cached.
6. **Cross-workspace:** use a different checkout path with identical source/config; verify path normalization allows cache hits.
7. **Compare outputs:** compare actual generated files/resources, not just logs. For artifacts with varying metadata, understand and normalize the cause.
8. **Run tests:** critical unit and integration tests must pass on both fresh execution and cache-loaded runs.
9. **Security review:** scan outputs for secrets, tokens, keys, or personal endpoints; never push sensitive data to a shared cache.
10. **Remote rollout:** start with developers pulling and trusted CI pushing; monitor hit/miss rates and transfer errors before expanding.
11. **Document:** record inputs/outputs, normalization choices, cache opt-ins, and how to invalidate/bypass cache during incidents in the PR.

**One green build is not enough to declare caching safe.** Only after proving that changing inputs produces updated outputs and identical inputs restore exact outputs can you trust a custom cacheable task.

## 15. Hands-On Exercise and Expected Results

Perform in an experimental branch of a Spring Boot Gradle project with Java 17+:

1. Create the files in Section 6: `settings.gradle`, `gradle.properties`, `build.gradle`, `src/main/build-label.txt`, and `CacheDemoApplication.java`.
2. Run `./gradlew --build-cache generateBuildLabel --info`; open `build/generated/build-label.properties` and confirm `build.label=demo-alpha`.
3. Re-run the same command to observe `UP-TO-DATE` while outputs remain.
4. Run `./gradlew --build-cache clean generateBuildLabel --info`; check for `FROM-CACHE` and verify the output file remains accurate.
5. Change input `alpha` to `beta` and re-run the task; confirm `build.label=demo-beta`.
6. Run with `-PlabelPrefix=release-`; confirm `build.label=release-beta` and explain why Gradle had to compute a different key.
7. Run `./gradlew --build-cache clean bootJar`, inspect `BOOT-INF/classes/build-label.properties` inside the JAR, and run `java -jar`; verify `BUILD_LABEL` matches the source value.
8. Intentionally break the task on a test branch (for example, remove `@Input` from the prefix), observe the risk of stale results, then **restore the correct annotation**.
9. Explain why `UP-TO-DATE` does not equal `FROM-CACHE`, and why `--rerun-tasks` does not verify cache restoration.
10. Write a short report including commands, inputs, key/miss/hit log lines if available, output file contents, JDK/Gradle versions, and app run results.

**Completion criteria:** you can enable the cache with the Wrapper, author a deterministic and cacheable custom task, declare complete file/value inputs and outputs, verify the packaged resource accurately, and explain why Gradle **does not reuse** a task output when inputs or config change.

## Official Documentation

- [Gradle – Build Cache](https://docs.gradle.org/current/userguide/build_cache.html)
- [Gradle – Build Cache Use Cases](https://docs.gradle.org/current/userguide/build_cache_use_cases.html)
- [Gradle – Incremental Build](https://docs.gradle.org/current/userguide/incremental_build.html)
- [Gradle – Declaring Task Inputs and Outputs](https://docs.gradle.org/current/userguide/incremental_builds.html)
- [Gradle – Best Practices for Tasks](https://docs.gradle.org/current/userguide/best_practices_tasks.html)
- [Gradle – More About Tasks](https://docs.gradle.org/current/userguide/more_about_tasks.html)
- [Gradle – Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html)
- [Gradle – Performance](https://docs.gradle.org/current/userguide/performance.html)
- [Gradle – Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html)
- [Spring Boot – Gradle Plugin: Getting Started](https://docs.spring.io/spring-boot/3.3/gradle-plugin/getting-started.html)
