# Using the Configuration Cache with Compatible Plugins in Spring Boot and Gradle

## 1. What Problem Does the Configuration Cache Solve?

A Spring Boot project using Gradle often involves multiple plugins, dependencies, Java toolchain setup, testing, `bootJar` packaging, and sometimes multiple modules. Every time you run `./gradlew test` or `./gradlew bootJar`, Gradle must locate the build, read configuration, and construct the task graph before executing tasks. In large repositories, the **configuration phase** can take significant time even when no source code has changed.

The **Configuration Cache** stores the output of the configuration phase: selected tasks, their configured state, dependencies, and data required for execution. When a subsequent run requests the same task set and configuration inputs remain valid, Gradle can **restore the task graph and skip re-evaluating build scripts and plugin configuration**.

This is **not** a mechanism for skipping unit tests, compilation, or security scans. It only avoids repeated configuration work; Gradle still checks task inputs/outputs and re-runs tasks whenever source code or input data changes.

Lesson goals:

1. Understand how the Configuration Cache differs from the Build Cache, incremental compilation, the daemon, and `UP-TO-DATE`.
2. Pilot it via `--configuration-cache`, inspect **stored → reused** logs, and only then enable it by default in `gradle.properties`.
3. Verify compatibility with the Spring Boot Gradle Plugin, third-party plugins, and custom tasks; never assume a plugin's existence means all its tasks are compatible.
4. Identify errors such as accessing `Project` at execution time, reading environment variables broadly, script listeners, side effects, and non-serializable task state.
5. Fix tasks using `Provider`, explicit properties, and Gradle services; use `notCompatibleWithConfigurationCache` when a controlled exception is needed.
6. Measure real gains, apply to multi-module/CI setups, and secure cache data.

**Illustrative versions:** Java 17, Spring Boot Gradle Plugin `3.5.16`, Gradle Wrapper `8.14.3`. "Gradle current" documentation at other times may describe Gradle 9.x or 10.x; **do not upgrade the Wrapper to a new major version** before verifying compatibility with Spring Boot and active plugins.

## 2. Understanding the Three Build Phases

```text
./gradlew test
       |
       v
INITIALIZATION
- Identify settings.gradle and subprojects
       |
       v
CONFIGURATION
- Apply plugins
- Evaluate build.gradle / build.gradle.kts
- Configure tasks, dependencies, and execution graph
       |
       v
EXECUTION
- compileJava, processResources, test...
- Tasks may be EXECUTED / UP-TO-DATE / FROM-CACHE
```

Without Configuration Cache, Gradle re-evaluates configuration on every invocation. When enabled:

```text
Run A: ./gradlew test --configuration-cache
    -> no valid entry
    -> configuration runs and task graph snapshot is stored
    -> execute test graph

Run B: ./gradlew test --configuration-cache
    -> same task request, matching configuration inputs
    -> restore configuration cache entry
    -> skip configuration phase
    -> execute restored test graph
```

Initialization still locates the build/cache entry. The **configuration phase** is the primary portion skipped on a hit. Execution tasks do not vanish automatically: if `GreetingService.java` changes, `compileJava` and `test` will still run even when the configuration cache is reused.

### 2.1. Differences across caches

| Mechanism | What is reused | Signal | Do not misunderstand |
|---|---|---|---|
| **Configuration Cache** | Task graph and post-configuration state | `Configuration cache entry stored/reused` | Does not store compile/test outputs in place of Build Cache |
| **Build Cache** | Outputs of tasks/transforms with properly declared inputs | `FROM-CACHE` | Does not automatically skip configuration |
| **Up-to-date check** | Existing outputs match current task input state | `UP-TO-DATE` | Does not mean configuration cache hit |
| **Incremental compile** | Compiles only affected sources when compiler supports it | Compile task still runs, doing less work | Does not cache the task graph |
| **Gradle daemon** | Long-lived Gradle JVM reducing startup overhead | Daemon reused | Does not equal configuration reuse |

Two independent properties:

```properties
# gradle.properties (enable in repo only after verification):
org.gradle.configuration-cache=true
org.gradle.caching=true
```

The first configures **configuration caching**; the second configures the **task-output Build Cache**. Both can be combined, though each has separate requirements and overhead. `--offline` is not a Configuration Cache toggle either: it only changes repository network access policy.

## 3. When to Enable: Checking Requirements and Plugins

Per official documentation, **Spring Boot Gradle Plugin 3.5** works with the Configuration Cache. The 3.5 plugin line documents support for Gradle **7.6.4+ in the 7.x line**, or **8.4+ in the 8.x line**. That documentation **does not guarantee** compatibility for every combination of Spring Boot 3.5 with Gradle 9.x or every third-party plugin.

Before enabling by default:

- Check wrapper version with `./gradlew --version` and `gradle/wrapper/gradle-wrapper.properties`.
- Confirm Java version and Java toolchain; distinguish the JDK running Gradle from the compiler/test JDK.
- Inventory plugins in `settings.gradle`, `build.gradle`, every subproject, and convention plugins—including quality, test, generation, publish, and container plugins.
- Read compatibility docs for your **exact plugin version**, not just the plugin ID.
- Audit custom tasks in `buildSrc`, `build-logic`, and any `doFirst`/`doLast` blocks.
- Test tasks **actually used by the team**: `help`, `test`, `check`, `bootJar`, `bootRun`, and `publish` if present.
- Compare actual test results and artifacts with Configuration Cache on vs. off.

A build may pass `help` cleanly yet fail on a code-generation task because Gradle touches a live `Project`/`Gradle` object only during execution. Compatibility is a property **of the build logic and task graph for a given invocation**, not a permanent badge on a repository.

Even though core Java/Java Library plugins support Configuration Cache well, that **does not imply** a code-generation plugin or in-house custom plugin is compatible.

## 4. Testing via Command Line Before Editing the Repository

### 4.1. First test: `help`

Run from the root directory containing the Gradle Wrapper:

```bash
./gradlew help --configuration-cache
```

On Windows:

```powershell
.\gradlew.bat help --configuration-cache
```

`help` is the task Gradle commonly recommends for initial adoption: it runs configuration with minimal execution. If no valid entry exists, logs look similar to:

```text
Calculating task graph as no cached configuration is available for tasks: help
...
Configuration cache entry stored.
```

Re-run **the exact same command**:

```bash
./gradlew help --configuration-cache
```

When inputs match and the graph is compatible, logs can show:

```text
Reusing configuration cache.
...
Configuration cache entry reused.
```

That is the direct cache-hit signal. Exact wording and placement vary by Gradle version, but **stored/reused** is what to look for. If it prints **discarded** or links to `configuration-cache-report.html`, the build is not ready yet.

### 4.2. Test real tasks twice

```bash
./gradlew test --configuration-cache
./gradlew test --configuration-cache

./gradlew bootJar --configuration-cache
./gradlew bootJar --configuration-cache
```

Each **task request** may use a different cache entry. `help` reuse **does not guarantee** `bootJar` will reuse immediately because it has a different graph. Even if tasks report `UP-TO-DATE`, configuration reuse still applies normally; do not look only at `UP-TO-DATE`.

### 4.3. Enable by default after verification

Root `gradle.properties`:

```properties
org.gradle.configuration-cache=true
```

From then on, running `./gradlew test` or `./gradlew bootJar` suffices. Once the team commits this property, both developer and CI Gradle commands can use the Configuration Cache; that is why plugins and tasks must be verified before broad rollout.

Disable for a single invocation, such as when a publish plugin fails:

```bash
./gradlew publish --no-configuration-cache
```

This command still runs the task while bypassing Configuration Cache for that run. You do not need to delete disk caches to disable the feature temporarily.

**Do not enable `org.gradle.configuration-cache.problems=warn` long-term**: warning mode can store/restore incomplete or broken serialized state when incompatibilities exist. Fix the root cause or mark specific incompatible tasks.

## 5. A Hands-On Spring Boot Java 17 Project

This example uses **Gradle Groovy DSL** and chooses a **native Gradle platform** to import the Spring Boot BOM, requiring only the Java plugin and Spring Boot Gradle Plugin. Using a native BOM **does not mean** projects already using `io.spring.dependency-management` must drop it immediately; test compatibility of your existing plugin stack before redesigning dependency management.

### 5.1. Directory tree

```text
cc-demo/
├── settings.gradle
├── build.gradle
├── gradle.properties
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/cc/
    │   ├── CcApplication.java
    │   └── GreetingService.java
    └── test/java/com/example/cc/
        └── GreetingServiceTest.java
```

The wrapper scripts/JAR must be generated via Gradle or Spring Initializr and committed properly—**do not just create empty files matching the diagram**.

### 5.2. `settings.gradle`

```groovy
rootProject.name = 'cc-demo'
```

### 5.3. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
}

group = 'com.example'
version = '0.1.0-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )
    testImplementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )

    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Explanation:

- `java` provides compile/test tasks, and `org.springframework.boot` adds `bootJar`/`bootRun` alongside the Java plugin.
- `SpringBootPlugin.BOM_COORDINATES` supplies the BOM matching the Spring Boot plugin version; `platform(...)` gives Gradle dependency constraints so starter versions can be omitted.
- `java.toolchain` selects Java 17 for compiler/tests; if the JDK is not installed or no toolchain resolver is configured, the build can fail **before Configuration Cache is even involved**.
- `testRuntimeOnly` provides the JUnit Platform launcher matching test dependencies.
- There is no `configuration-cache` plugin because it is a built-in Gradle feature.

`gradle/wrapper/gradle-wrapper.properties` may contain:

```properties
distributionUrl=https\://services.gradle.org/distributions/gradle-8.14.3-bin.zip
```

This shows only the relevant wrapper property; real projects may include checksums/timeouts/paths. Use Wrapper 8.x compatible with Spring Boot 3.5 for this example; do not jump to Gradle 9+ without checking the plugin compatibility matrix.

### 5.4. Application class

File `src/main/java/com/example/cc/CcApplication.java`:

```java
package com.example.cc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CcApplication {
    public static void main(String[] args) {
        SpringApplication.run(CcApplication.class, args);
    }
}
```

Uses the basic `spring-boot-starter` with no embedded web server; when running the executable JAR, the Spring context starts and the process normally exits if no background thread/task keeps it alive.

### 5.5. Pure Java logic

File `src/main/java/com/example/cc/GreetingService.java`:

```java
package com.example.cc;

public final class GreetingService {
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

### 5.6. JUnit test

File `src/test/java/com/example/cc/GreetingServiceTest.java`:

```java
package com.example.cc;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class GreetingServiceTest {
    @Test
    void greetsByName() {
        assertEquals("Hello, Java",
                new GreetingService().greet("Java"));
    }
}
```

These Java files require classpaths from Spring Boot/JUnit resolved by Gradle; plain `javac` cannot compile `CcApplication.java` or `GreetingServiceTest.java` without supplying dependencies. The sources here form a complete program and test built via the Gradle script above.

### 5.7. Verification build runs

```bash
# Baseline with cache off
./gradlew clean test
./gradlew bootJar

# Test Configuration Cache:
./gradlew help --configuration-cache
./gradlew help --configuration-cache
./gradlew test --configuration-cache
./gradlew test --configuration-cache
./gradlew bootJar --configuration-cache
./gradlew bootJar --configuration-cache

# Run the packaged artifact
java -jar build/libs/cc-demo-0.1.0-SNAPSHOT.jar
```

The default JAR filename comes from the root project name and version; if your build customizes the archive name, inspect `build/libs` first. `java -jar` tests the application and takes **no** Configuration Cache flag, because the cache applies to the Gradle build process rather than the app's runtime JVM.

There is no fixed stdout from `test` beyond Gradle's reports; check **BUILD SUCCESSFUL**, test results, and cache **stored/reused** lines. Do not assume a configuration cache hit just because a compile task printed `UP-TO-DATE`.

## 6. Kotlin DSL Project: Equivalent Syntax

If using `settings.gradle.kts`:

```kotlin
rootProject.name = "cc-demo"
```

And `build.gradle.kts`:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.16"
}

group = "com.example"
version = "0.1.0-SNAPSHOT"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation(platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    ))
    testImplementation(platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    ))

    implementation("org.springframework.boot:spring-boot-starter")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}
```

The Java code and `gradlew` commands stay the same. **Do not copy Groovy syntax** like `id 'java'` or `implementation '...'` into `.kts` files; and do not create both `build.gradle` and `build.gradle.kts` in the same module.

## 7. Conditions for Cache Hits, Misses, and Invalidation

Gradle keys/checks entries by task request and inputs affecting configuration. Factors that **can** cause a miss:

- Running different tasks or task/argument combinations, e.g., `help` vs. `test`, or `test` vs. `clean test`.
- Editing `settings.gradle(.kts)`, `build.gradle(.kts)`, `gradle.properties`, init scripts, or convention plugin code.
- Changing plugin versions, Gradle Wrapper, or build-logic classpath.
- Changing Gradle/system properties, environment variables, or files **read by build logic at configuration time**.
- Entry is invalid, deleted, or has not yet been stored for that task graph.

When a property is read during configuration, Gradle includes it in the configuration fingerprint. For example, if a build script reads `providers.gradleProperty('build.mode').get()` to select tasks during configuration, changing `-Pbuild.mode=...` invalidates the entry. **Do not assume every `-P` property causes a miss**, as it depends on whether configuration reads it.

### 7.1. Does editing Java sources cause a cache miss?

**Not necessarily.** If you edit a method in `GreetingService.java` without changing build logic, Gradle can still reuse configuration and re-run `compileJava`/`test` because task inputs changed. That is expected: reusing configuration **never hides source changes**.

### 7.2. Where is the Configuration Cache stored?

The project-local cache normally lives at:

```text
<root-build>/.gradle/configuration-cache/
```

It is distinct from `build/` (task outputs), Gradle User Home caches, and Maven repositories. `./gradlew clean` deletes build outputs and **must not be treated as a command that clears the Configuration Cache**. Delete only the exact cache directory if diagnosing a state issue, after stopping any Gradle builds using it, and in the right checkout. Never put an unchecked delete of all of `.gradle` into CI scripts.

## 8. Tasks to Test Beyond `help`

| Task | Why it needs testing |
|---|---|
| `help` | Quickly catches general plugin/build-script configuration problems |
| `test` | Test plugins, JVM args, coverage agents, custom listeners, Java toolchains |
| `check` | Beyond `test`, may trigger PMD, Checkstyle, Spotless, or quality tasks |
| `bootJar` | Spring Boot packaging, manifests, custom archive configuration |
| `bootWar` | WAR plugin and `providedRuntime` (only if the project has this task) |
| `bootRun` | `JavaExec`/`BootRun`, system properties, devtools/run customizations |
| `publish` | Publishing plugins, signing, credentials, and custom upload tasks |
| `:module:integrationTest` | Custom test suites and inputs/outputs, database fixtures |

**Do not test `help` alone.** A plugin can configure cleanly yet trigger a Configuration Cache problem when its task enters the graph. Invoke **each real task twice**, observe stored on the first run and reused on the second, then verify outputs, test reports, and artifacts match.

`bootRun` may launch a server that blocks the terminal until stopped; test it with a controlled start/stop workflow rather than invoking two overlapping runs on the same port and blaming the plugin for "Port already in use."

## 9. Key Anti-Pattern: Accessing `Project` Inside Task Actions

Task actions run **during the execution phase**. At that point, model objects like `Project`, `Gradle`, or `Settings` cannot be accessed freely as in configuration, because they cannot be safely serialized/restored in the Configuration Cache.

### 9.1. Intentionally broken example

Snippet added to Groovy `build.gradle`:

```groovy
tasks.register('showBad') {
    doLast {
        println 'Project = ' + project.name
    }
}
```

Run:

```bash
./gradlew showBad --configuration-cache
```

Gradle may report an error along the lines of:

```text
Invocation of 'Task.project' by task ':showBad'
at execution time is unsupported with the configuration cache.
```

This is an **intentionally failing example**—run it only on an experimental branch. Never use it in production builds.

### 9.2. Fix by capturing simple data at configuration time

```groovy
tasks.register('showName') {
    def capturedName = project.name
    doLast {
        println 'Project = ' + capturedName
    }
}
```

`capturedName` is a **String**, captured during task configuration; the action does not touch the `Project` object. With `rootProject.name = 'cc-demo'`, stdout from the task prints:

```text
Project = cc-demo
```

You can run `./gradlew showName --configuration-cache` twice to confirm stored/reused. For other variables, avoid capturing the enclosing build script instance from outer scope; capture plain local values inside task configuration or use typed properties.

## 10. Typed Task + Property/Provider: The Sustainable Pattern

### 10.1. Custom Gradle task in Groovy DSL

Place this in the project's `build.gradle` (imports at the top of the script); this is an **additive snippet**, not a full build file:

```groovy
import org.gradle.api.DefaultTask
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.TaskAction

abstract class PrintMessageTask extends DefaultTask {
    @Input
    abstract Property<String> getMessage()

    @TaskAction
    void printMessage() {
        logger.lifecycle('message=' + message.get())
    }
}

tasks.register('printMessage', PrintMessageTask) {
    message.set(providers.gradleProperty('demo.message').orElse('hello'))
}
```

Gradle manages `Property<String>`, `@Input` declares the task's input value, and `providers.gradleProperty(...)` wires the value without eagerly scanning all Gradle properties at configuration time. `@TaskAction` does not read a live `Project` object.

Run:

```bash
./gradlew printMessage --configuration-cache
./gradlew printMessage --configuration-cache
./gradlew printMessage --configuration-cache -Pdemo.message=bonjour
```

Task stdout is `message=hello` on the first two runs and `message=bonjour` on the last. Because the property is wired lazily through a Provider, changing the value may not even require invalidating the configuration entry, while the task still sees the new value when running; exact behavior depends on the task request and other build inputs.

### 10.2. Custom task in Kotlin DSL

Equivalent in `build.gradle.kts`:

```kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.TaskAction

abstract class PrintMessageTask : DefaultTask() {
    @get:Input
    abstract val message: Property<String>

    @TaskAction
    fun printMessage() {
        logger.lifecycle("message=" + message.get())
    }
}

tasks.register<PrintMessageTask>("printMessage") {
    message.set(providers.gradleProperty("demo.message").orElse("hello"))
}
```

This is a **Kotlin DSL replacement**—do not put both Groovy and Kotlin task classes into the same project.

### 10.3. When a task produces output files

For tasks that read files and generate resources (JSON manifests, generated code, schemas, package metadata), also include:

- `@InputFile` / `@InputFiles` for source files.
- `@OutputFile` / `@OutputDirectory` for outputs.
- `@Input` for scalar settings.
- Normalization/path sensitivity if file inputs depend on paths.
- Injected `FileSystemOperations` or equivalent service instead of `project.copy` inside the task action.
- Provider wiring from one task's output to another task's input so Gradle infers dependencies.

**Configuration Cache compatibility ≠ task cacheability ≠ correctness.** A task can serialize cleanly yet still produce wrong outputs if it relies on hidden inputs, undeclared environment reads, or writes to the same file as another task.

## 11. Anti-Patterns and Fixes

| Problematic pattern | Why | Better alternative |
|---|---|---|
| `doLast { project.copy { ... } }` | Uses `Project` model during execution | Inject `FileSystemOperations` into a typed task |
| `doLast { println project.version }` | Accesses `project` inside task action | Capture value at configuration or store in a typed property |
| Task stores `Project`/`Gradle`/`Configuration` fields | Live state unsuitable for serialization | Replace with `Property`, `Provider`, file collections, or injected Gradle services |
| `gradle.taskGraph.whenReady { ... }` for late config | Configuration callback does not re-run the same way on CC hit | `tasks.named`, `configureEach`, `Provider`s, and task dependencies |
| Reading all of `System.getenv()` in configuration | Many unrelated env vars become configuration inputs | `providers.environmentVariable('KEY')` for the exact variable needed |
| `"git ...".execute()` during configuration | Hard-to-track external process/side effect | `providers.exec`/`ValueSource` or pass metadata via CI |
| Writing files at top level of `build.gradle` | Side effect does not repeat on cache hit | Create a task with `@OutputFile` and `@TaskAction` |
| Tasks writing to shared output without dependency | Race conditions and non-deterministic output | Define explicit inputs/outputs and task dependency graph |
| Leaving `problems=warn` on permanently | Broken serialized state may be reused | Fix root cause or mark the specific task incompatible |
| Unpinned plugin/Wrapper versions | New releases change behavior and compatibility | Pin versions and re-test on each upgrade |
| Thinking `UP-TO-DATE` means CC hit | Two different mechanisms | Read CC stored/reused logs |
| Testing only `help` | Misses plugin execution-time logic | Run `test`, `bootJar`, quality, and publish tasks |

### 11.1. Reading environment variables

Avoid reading or enumerating all environment variables during configuration:

```groovy
// Illustrative anti-pattern:
def allEnv = System.getenv()
println allEnv.keySet()
```

In modern Gradle, this can turn numerous env vars into fingerprints, causing constant invalidations and leaking sensitive metadata. Prefer fetching **only the required variable** via `providers.environmentVariable('APP_MODE')` and wiring it into a typed task property. Read secrets only when truly needed and never print them to logs.

## 12. Configuration Cache Reports and Debugging

When an incompatibility occurs, logs may say:

```text
1 problem was found storing the configuration cache.
- Task ':legacyTask' ... Invocation of 'Task.project' ...
Configuration cache entry discarded with 1 problem.
```

An HTML report is usually written to a path like:

```text
build/reports/configuration-cache/<hash>/configuration-cache-report.html
```

Open the report and inspect problems grouped by **message**, **task**, stacktrace, and **configuration inputs**. It helps distinguish issues in custom scripts, third-party plugins, Gradle APIs, or changing inputs.

Troubleshooting workflow:

1. Run `./gradlew --version` to verify exact Wrapper/JDK.
2. Reproduce the same task with `--configuration-cache --stacktrace`.
3. Open the report; locate the plugin/task and script line.
4. Fix build logic or upgrade the plugin per its compatibility changelog.
5. Verify the task **stores** on the first run, **reuses** on the second, and produces matching outputs/test results.
6. If a third-party plugin cannot be fixed yet, apply the temporary workaround in Section 13 and file an issue/assign an owner.
7. Never mark the entire project ready if deploy/publish tasks still have untested incompatibilities.

Commands:

```bash
./gradlew help --configuration-cache --stacktrace
./gradlew test --configuration-cache --info
./gradlew bootJar --configuration-cache --info
./gradlew test --no-configuration-cache
```

`--info`/`--debug` and stacktraces may contain environment details; scrub secrets and sensitive paths before sharing outside the team.

## 13. When a Plugin Is Not Compatible Yet: Mark the Task or Disable per Invocation

Gradle provides `Task.notCompatibleWithConfigurationCache(reason)`. If a build has a `legacyGenerate` task from an older plugin, you can mark it **temporarily**:

```groovy
tasks.named('legacyGenerate') {
    notCompatibleWithConfigurationCache(
        'Uses Project model at execution time; awaiting plugin update'
    )
}
```

This is a **snippet** for a project that already defines that task; it does not create a new task. In Kotlin DSL:

```kotlin
tasks.named("legacyGenerate") {
    notCompatibleWithConfigurationCache(
        "Uses Project model at execution time; awaiting plugin update"
    )
}
```

Effect: whenever the graph includes a task marked incompatible, Gradle **does not store a reusable entry for that graph**. Invocations that do not pull that task into the graph can still benefit from Configuration Cache. Marking a task does not fix its implementation or prove it safe for parallel execution, and should come with a removal plan once the plugin is updated.

Do not confuse this with global `--configuration-cache-problems=warn`: warning mode is a short-term troubleshooting tool, not an adoption policy. Gradle versions differ in how they handle warnings and incompatible tasks, yet **you should never rely on warning mode to force-cache a known-incompatible task**.

When you need to unblock a publish pipeline while awaiting a plugin fix:

```bash
./gradlew publish --no-configuration-cache
```

This is a deliberate trade-off for a **specific invocation**—do not delete tests, drop security scans, or quietly switch to untested artifacts.

## 14. Measuring Configuration Cache Impact

### 14.1. Controlled benchmark

1. Use the same source commit, Gradle Wrapper, JDK/toolchain, plugin versions, and environment.
2. Resolve dependencies beforehand and warm the daemon as appropriate so network/JVM startup is not confused with configuration time.
3. Run the same task multiple times **without CC** as the baseline.
4. Run once with CC to **store**, then multiple runs to **reuse**.
5. Record total duration and task states, using profiling/build scans where permitted by security policy.
6. Take the median across multiple warmed runs rather than quoting a single "BUILD SUCCESSFUL in 0s" result.
7. Separate time saved from compilation/tests/build cache/up-to-date checks from skipped configuration time.

Example:

```bash
./gradlew help --no-configuration-cache --console=plain
./gradlew help --no-configuration-cache --console=plain

./gradlew help --configuration-cache --console=plain
./gradlew help --configuration-cache --console=plain
./gradlew help --configuration-cache --console=plain
```

`help` helps isolate configuration overhead clearly. Afterward, measure `test`/`bootJar`, because those represent actual workflows. Do not insert `clean` between two runs and attribute all timing differences to the Configuration Cache.

### 14.2. Hypothetical sample figures

| Measurement run | CC state | Hypothetical total time |
|---|---|---:|
| `help`, no CC and warmed | Off | 3.3 seconds |
| `help`, first CC run | Stored | 3.7 seconds |
| `help`, subsequent CC run | Reused | 0.9 seconds |

These are **illustrative figures**, not benchmarks from a real repository. The first run can be slower because Gradle must serialize the cache entry. On tiny projects, savings may be negligible; on multi-module projects with heavy plugins, skipped configuration time can be substantial.

## 15. Multi-Module Builds: Cache per Task Request and Real Plugins

Suppose:

```text
platform/
├── settings.gradle
├── gradle.properties
├── build.gradle
├── shared-core/build.gradle
├── orders-api/build.gradle
└── batch-worker/build.gradle
```

`settings.gradle`:

```groovy
rootProject.name = 'platform'
include 'shared-core', 'orders-api', 'batch-worker'
```

The following invocations have distinct task graphs:

```bash
./gradlew help --configuration-cache
./gradlew :shared-core:test --configuration-cache
./gradlew :orders-api:bootJar --configuration-cache
./gradlew :batch-worker:test --configuration-cache
./gradlew check --configuration-cache
```

Gradle can store a separate entry per request. **Library modules** might apply only the Java Library plugin while app modules apply the Spring Boot plugin. Do not apply the Boot plugin to every module just for caching: Configuration Cache belongs to **Gradle**, independent of the Boot plugin.

In multi-module builds, verify real task dependencies. Configuration Cache often enables greater task execution isolation/parallelism, so two tasks writing to the same undeclared output or lacking ordering can expose race conditions. Use `@Input...`, `@Output...`, `Provider`s, and `dependsOn` or task-output wiring instead of relying on accidental log order.

**Note:** `mustRunAfter` only orders tasks **when both are already selected**; it does not pull the other task into the graph. When sharing resources across tasks, Gradle's Shared Build Service and `usesService(...)` help coordinate access.

## 16. IDE, CI, and Security

### 16.1. IDE

Gradle documentation explicitly notes that **IDE sync/import is not sped up by the Configuration Cache**. However, when an IDE delegates **task invocations** to Gradle with the cache enabled, those tasks can reuse entries just like from a terminal. Do not use "Sync Project" duration to judge Configuration Cache effectiveness.

### 16.2. CI

Roll out in stages:

- Developers test locally with `help`, `test`, `check`, and `bootJar`.
- A CI job runs the same task twice in the **same workspace** to verify stored/reused behavior.
- Compare artifacts, test results, and reports with CC on vs. off.
- Commit `org.gradle.configuration-cache=true` only after main tasks show no unacceptable incompatibilities.
- Whenever upgrading Gradle/plugin versions, re-verify compatibility rather than assuming prior results carry over.

Example commands on the same CI workspace:

```bash
./gradlew --no-daemon --configuration-cache test
./gradlew --no-daemon --configuration-cache test
./gradlew --no-daemon --configuration-cache bootJar
./gradlew --no-daemon --configuration-cache bootJar
```

`--no-daemon` is a runner policy choice, **not** a prerequisite for Configuration Cache. If runners are destroyed after every job, the local cache from a previous job **does not persist automatically** to the next. Saving/restoring caches across jobs requires dedicated design and data protection; never upload raw `.gradle` or Gradle User Home directories to public storage.

### 16.3. Secrets

Task state and configuration fingerprints may contain values read during configuration; never treat the cache as a safe credential store to share. Avoid `System.getenv('TOKEN')` during configuration unless needed. Use the Provider API, secret managers/CI variables, and Gradle credential APIs; read secrets only in the specific task that needs them, and never log them. Restrict access to project caches and Gradle User Home. Even when a Gradle version encrypts the cache, **never use that as a substitute for proper secret management**.

## 17. Common Errors and Diagnostic Guide

| Symptom | Likely explanation | Action |
|---|---|---|
| `help` fails immediately when CC is enabled | Incompatible build script/plugin configuration | Open CC report and fix early |
| `help` hits, yet `bootJar` fails | Packaging task or custom action only exercised when that task is in the graph | Inspect Boot plugin and custom archive actions |
| `Task.project at execution time unsupported` | Task action reads `Project` | Switch to captured local values, typed tasks, or injected services |
| `Configuration cache entry discarded` | Serialization error or task marked incompatible | Do not claim cache was stored; read the reason |
| `Calculating task graph ... cannot be reused` | Configuration inputs changed or different task request | Read the invalidation line; do not wipe caches blindly |
| `UP-TO-DATE` without `reused` | Task outputs are still current, Configuration Cache missed/disabled | Distinguish the two mechanisms |
| `FROM-CACHE` yet re-configured | Build Cache hit while CC was off/missed | Check properties for both caches separately |
| Build fails on `--configuration-cache` in CI | Plugin/task only runs in CI, or JDK/plugin versions differ | Compare plugin lists, task graphs, init scripts, and environment |
| Cache invalidated on every CI run | Reading build number, timestamp, env, or volatile files at config time | Switch to `Provider`s/explicit task inputs |
| `warn` succeeds, yet next run produces wrong output | Incompatibility ignored; serialized state incomplete | Turn off warning mode and fix the task |
| Race condition in multi-module build | Shared mutable state or undeclared output file | Enforce task isolation, distinct output dirs, and dependencies |
| Artifacts differ with CC on vs. off | Build logic relies on side effects or hidden inputs | Fix correctness before optimizing performance |
| IDE sync did not get faster | Sync does not use CC | Measure delegated Gradle task invocations |
| Wrapper upgrade breaks many tasks | Plugins incompatible with new Gradle major version | Pin valid prior version and upgrade incrementally |
| Deleting `build/` still gives CC hits | Cache lives in `.gradle/configuration-cache`, not `build/` | Do not treat `clean` as clearing CC |

Diagnostic commands:

```bash
./gradlew --version
./gradlew help --configuration-cache --stacktrace
./gradlew test --configuration-cache --info
./gradlew bootJar --configuration-cache --info
./gradlew test --no-configuration-cache
```

Before sharing `--info`/`--debug` logs or stacktraces, check for internal URLs, private paths, or secrets.

## 18. Comparative Lab Exercise and Completion Criteria

**A. Baseline:** run `./gradlew clean test` and `./gradlew bootJar` with cache off; verify unit tests and the executable JAR.

**B. Store:** run `./gradlew help --configuration-cache`; look for `Configuration cache entry stored`. If errors appear, open the HTML report to fix them.

**C. Reuse:** re-run the exact `help` command; look for `Reusing configuration cache` and `Configuration cache entry reused`.

**D. Real tasks:** run `test` and `bootJar` **twice per task request** without modifying build scripts, recording outcomes.

**E. Source change:** edit `GreetingService.greet` and the expected value in the test, then re-run `test`. While compilation/testing must run again, Configuration Cache can still be reused; confirm the updated test runs properly.

**F. Configuration change:** change `version = '0.1.0-SNAPSHOT'` in the build script to another value and run `bootJar`; Gradle must re-evaluate configuration appropriately and the archive name may change. Restore the original value afterward.

**G. Incompatibility:** temporarily add the `showBad` task from Section 9 on a test branch, run with CC, and inspect the problem report. Refactor to `showName`/`PrintMessageTask` and run twice to confirm stored/reused; do not commit the broken task.

**H. Rollout:** test code generation, Checkstyle/Spotless, publish, and multi-module tasks as well. Record owners, remaining issues, and a plugin update plan; only then enable by default in `gradle.properties` if team workflows qualify.

### Checklist

- [ ] Java/Gradle Wrapper/Spring Boot plugin versions are pinned with a verified compatibility matrix.
- [ ] `help`, `test`, and `bootJar` achieve **stored → reused** when inputs are unchanged.
- [ ] Warning mode is not used to hide Configuration Cache problems in CI.
- [ ] Custom tasks never access live `Project`/`Gradle` objects at execution time.
- [ ] `Provider`s, task inputs/outputs, and task dependencies are declared properly.
- [ ] Test results and artifacts match with Configuration Cache enabled vs. disabled.
- [ ] `UP-TO-DATE`/`FROM-CACHE` are not confused with configuration reuse.
- [ ] Third-party plugin tasks and critical subprojects have been tested.
- [ ] Benchmarks use a baseline and multiple warm runs, isolating downloads/daemon startup.
- [ ] CI caches/secrets have proper access controls; cache directories are never committed.
- [ ] `--no-configuration-cache` is available as an escape hatch for single incompatible invocations.
- [ ] A re-verification plan exists for Wrapper or plugin upgrades.

### Official Documentation

- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html)
- [Gradle — Enabling and Configuring the Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache_enabling.html)
- [Gradle — Adopting the Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache_adoption.html)
- [Gradle — Configuration Cache Requirements](https://docs.gradle.org/current/userguide/configuration_cache_requirements.html)
- [Gradle — Debugging the Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache_debugging.html)
- [Gradle — Supported Plugins and Status](https://docs.gradle.org/current/userguide/configuration_cache_status.html)
- [Gradle — Task API, notCompatibleWithConfigurationCache](https://docs.gradle.org/current/javadoc/org/gradle/api/Task.html)
- [Spring Boot 3.5 — Gradle Plugin](https://docs.spring.io/spring-boot/3.5/gradle-plugin/)

**Remember:** Configuration Cache speeds up builds only when **every plugin and task in an invocation is compatible** and configuration inputs are tracked accurately. Prove it with **stored → reused** and identical test/artifact outputs; when errors arise, fix build logic or isolate incompatible tasks rather than suppressing checks with long-term warning mode.
