# Configuring Tasks with `tasks.named` and the Provider API in Gradle with Spring Boot

In a Spring Boot application using Gradle, you often want to rename the executable JAR, adjust how `bootRun` executes, configure tests, or wire the output of a custom task into the input of another task. Two key APIs address this:

- **`tasks.named(...)`** locates and configures an **already-registered task** lazily, returning a `TaskProvider`. It neither creates a new task nor executes the task.
- **Provider API** represents a **value that can be computed or supplied later**, such as a project property, a file in the build directory, or another task's output. `Provider<T>` and `Property<T>` connect data without needing to read values eagerly.

Combining both APIs properly lets Gradle avoid creating/configuring unrelated tasks, preserves inter-task dependency metadata, tracks inputs/outputs, and supports reproducible builds. This is the modern way to customize Spring Boot tasks such as `bootJar` and `bootRun`.

## 1. Distinguishing Task Registration, Configuration, and Execution

Gradle organizes a build into initialization, configuration, and execution. During the **configuration phase**, Gradle reads build scripts, applies plugins, registers tasks, and constructs the task graph. During the **execution phase**, Gradle executes selected tasks along with their dependencies.

Not every registered task needs to be instantiated immediately. The Task Configuration Avoidance API avoids *realizing* tasks that are not needed for the current build invocation.

| Operation | Meaning | Immediate effect |
| --- | --- | --- |
| `tasks.register('report')` | Registers a new task, returning `TaskProvider` | Does not run; does not necessarily create the Task object |
| `tasks.named('bootJar')` | Retrieves provider of an already-registered task | Does not run; does not force realization |
| `tasks.named('bootJar') { ... }` | Registers task configuration logic | Configuration can be deferred |
| `tasks.getByName('bootJar')` | Retrieves the task object directly | May realize the task eagerly |
| `taskProvider.get()` | Retrieves the task object from the provider | May realize the task eagerly |
| `./gradlew bootJar` | Requests task execution | Runs the task and its dependencies unless skipped/up-to-date |

Example:

~~~bash
./gradlew bootJar
~~~

This command normally makes Gradle compile, process resources, and package the executable JAR. By contrast, a statement in the build script:

~~~groovy
tasks.named('bootJar') {
    archiveFileName.set('service.jar')
}
~~~

only describes **how to configure** the task when needed; it does not trigger `bootJar` and does not immediately generate a file.

**Common misconception:** lazy configuration does not mean every property is read only during execution. When a task is realized, `named`'s configuration action may run during the configuration phase; if code calls `get()` inside it, the provider's value will be queried early.

## 2. Choosing `register`, `named`, or `configureEach`

### Creating a New Task: `tasks.register`

~~~groovy
def reportTask = tasks.register('printBuildStatus') {
    group = 'verification'
    description = 'Prints the build status.'
    doLast {
        logger.quiet('BUILD_STATUS=READY')
    }
}
~~~

When run:

~~~bash
./gradlew -q printBuildStatus
~~~

Output printed by the task:

~~~text
BUILD_STATUS=READY
~~~

This is a project-defined task, distinct from `bootJar` registered by the Spring Boot Gradle plugin.

### Configuring an Existing Task: `tasks.named`

~~~groovy
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named('bootJar', BootJar) {
    archiveFileName.set('service.jar')
}
~~~

The configuration above assumes the project has applied compatible `java` and `org.springframework.boot` plugins. `named` searches for the task in the **current project**. If `bootJar` has not been registered, Gradle may throw `UnknownTaskException`; `named` does not create tasks.

Eager style to avoid when you do not need the task object immediately:

~~~groovy
// May realize the task immediately during configuration:
tasks.getByName('bootJar').archiveFileName.set('service.jar')
~~~

Configuration-avoidance style:

~~~groovy
tasks.named('bootJar') {
    archiveFileName.set('service.jar')
}
~~~

### Configuring Multiple Tasks of the Same Type: `configureEach`

~~~groovy
tasks.withType(Test).configureEach {
    useJUnitPlatform()
    testLogging {
        events 'failed', 'skipped'
    }
}
~~~

This is Groovy DSL syntax in a project with the Java plugin and JUnit Platform when you want to apply a policy to every `Test` task. `configureEach` defers applying the logic until each task needs configuration, including tasks of that type registered later.

By contrast, `tasks.withType(Test) { ... }` is an eager configuration form. If you only want to configure a single known task by name, use `tasks.named('test', Test)`. There is no need to configure all tasks when only one task needs changing.

### Passing `TaskProvider` Directly to `dependsOn`

~~~groovy
def reportTask = tasks.register('printBuildStatus') {
    doLast { logger.quiet('BUILD_STATUS=READY') }
}

tasks.named('check') {
    dependsOn(reportTask)
}
~~~

This standalone example assumes the Java plugin created `check`. When running `check`, `printBuildStatus` enters the task graph. You do not need to write `dependsOn(reportTask.get())`. `dependsOn` requires the dependency task to execute, whereas `mustRunAfter` only specifies ordering **if both tasks are already scheduled**.

## 3. Provider API: Connecting Data Before Values Are Available

Gradle distinguishes two categories:

- **`Provider<T>`:** read-only access to a value (e.g., `get()`, `map`, `flatMap`, `orElse`); cannot set the underlying source value itself.
- **`Property<T>`:** extends `Provider` and lets you configure the value via `set` or a default via `convention`.

Common types:

| Type | Holds what? | Use case |
| --- | --- | --- |
| `Provider<String>` | String supplied when needed | Artifact name from `-P` |
| `Property<String>` | Configurable string | Task input, archive name |
| `RegularFileProperty` | Configurable file path | `@InputFile`, `@OutputFile` |
| `DirectoryProperty` | Configurable directory path | Output folder |
| `ListProperty<T>`, `MapProperty<K,V>` | Configurable collection | Parameter list or map |
| `TaskProvider<T>` | Lazy reference to a task | Return value from `register`/`named` |

### `providers.gradleProperty` Instead of Eager Resolution

~~~groovy
def nameProvider = providers.gradleProperty('bootJarName')
    .orElse('service.jar')

tasks.named('bootJar') {
    archiveFileName.set(nameProvider)
}
~~~

When running `./gradlew bootJar`, the file defaults to `service.jar`; when running `./gradlew bootJar -PbootJarName=release.jar`, the file is named `release.jar`. `orElse` provides a fallback if the property is not set. `set(Provider)` wires the target property to the source provider without reading the string immediately.

Avoid resolving too early:

~~~groovy
// Unnecessary in this case:
def fileName = providers.gradleProperty('bootJarName')
    .orElse('service.jar')
    .get()

tasks.named('bootJar') {
    archiveFileName.set(fileName)
}
~~~

The code may still run, but it loses the ability to defer querying. Especially with providers tied to another task's output, converting early to a `String` or `File` can discard producer task metadata.

### `set` vs. `convention`

~~~groovy
tasks.named('bootJar') {
    archiveFileName.convention('fallback.jar')
    archiveFileName.set(
        providers.gradleProperty('bootJarName').orElse('release.jar')
    )
}
~~~

`convention(...)` sets a **default value**, effective only when the property has no explicit value. `set(...)` specifies an **explicit value**, which can be a `Provider`. If a plugin already sets a reasonable convention, normally just call `set` when overriding it. Do not call `finalizeValue` or `disallowChanges` indiscriminately, because other plugins may still need to configure the property before Gradle locks it.

`get()` can fail if the provider has no value. Use `orElse` when a missing value is valid; for required inputs, letting Gradle fail with a clear error is appropriate.

### `map` and `flatMap`

~~~groovy
def channel = providers.gradleProperty('channel').orElse('dev')
def jarName = channel.map { value -> 'service-' + value + '.jar' }

tasks.named('bootJar') {
    archiveFileName.set(jarName)
}
~~~

With `-Pchannel=prod`, `jarName` represents `service-prod.jar`. `map { T -> R }` creates a new provider by transforming a plain value; `flatMap { T -> Provider<R> }` is used when the transformation result is itself a provider. Using `flatMap` is particularly valuable for extracting a **task's file output property** while preserving producer metadata.

Transformations inside providers should be pure: do not open network connections, mutate external state, or write files inside `map`. Gradle may evaluate providers at various times; side effects belong inside modeled task actions.

### Providers for Files and Directories

~~~groovy
def markerFile = layout.buildDirectory.file(
    'generated/build-marker.txt'
)
~~~

`markerFile` is a `Provider<RegularFile>` bound to the build layout, replacing manual path concatenation such as `new File(project.buildDir, '...')`. For task inputs/outputs, prefer `RegularFileProperty`, `DirectoryProperty`, and wiring providers so Gradle tracks dependencies and caching.

## 4. Spring Boot: Configuring `bootJar` and `bootRun`

### `bootJar` — Executable Archive

~~~groovy
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named('bootJar', BootJar) {
    archiveFileName.set(
        providers.gradleProperty('bootJarName').orElse('service.jar')
    )
}
~~~

`bootJar` is registered by the Spring Boot Gradle plugin when an appropriate Java plugin is applied. This task packages an executable Spring Boot JAR containing app classes, the launcher, and runtime dependencies. The Java plugin's `jar` task creates a regular Java archive, which differs from the executable Boot JAR. These are distinct build tasks.

You can change the classifier:

~~~groovy
tasks.named('bootJar') {
    archiveClassifier.set('exec')
}
~~~

This is a **separate example** when changing the classifier. If you also explicitly set `archiveFileName`, that exact filename dictates the output name; do not assume the classifier will automatically append onto a fixed filename you set. Archive options must be chosen consistently.

### `bootRun` — Running the Application via Gradle

~~~groovy
import org.springframework.boot.gradle.tasks.run.BootRun

tasks.named('bootRun', BootRun) {
    systemProperty 'demo.mode', 'training'
}
~~~

`BootRun` extends `JavaExec`, so you can customize JVM/system properties and arguments passed to the application. `bootRun` uses the project's runtime classpath to run during development. Configuring `systemProperty` here applies only to the JVM launched by `bootRun`; it does not embed that value into the JAR artifact.

When running with `java -jar` on a server, JVM/application arguments are supplied separately. For example, `java -Ddemo.mode=training -jar app.jar` passes the corresponding JVM system property. Do not expect settings configured only on `bootRun` to travel inside the JAR upon deployment.

### Tasks Do Not Always Exist

| Task | Basic prerequisite | Role |
| --- | --- | --- |
| `bootJar` | Spring Boot plugin + Java plugin | Executable Spring Boot JAR |
| `bootRun` | Spring Boot plugin + Java plugin | Runs app from classpath |
| `jar` | Java plugin | Plain Java JAR |
| `bootWar` | Spring Boot plugin + `war` plugin | Executable WAR |
| `test` | Java plugin | Test execution |

`tasks.named('bootWar')` will fail if the module has no WAR task. In multi-project builds, task configuration must go into the **exact project** that owns the task. The root project does not automatically have `bootJar` just because a subproject applies the Spring Boot plugin.

## 5. Complete Example: Running the App and Creating Wired Custom Tasks

This example pins **Spring Boot 3.3.5**, **Gradle 8.7**, and **Java 17** for practice, without claiming these are the latest versions. When starting new projects, verify currently supported and compatible versions. It uses Groovy DSL in `build.gradle`.

Project structure:

~~~text
provider-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/demo/DemoApplication.java
~~~

### File `settings.gradle`

~~~groovy
rootProject.name = 'provider-demo'
~~~

### Complete `build.gradle` File

~~~groovy
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.springframework.boot.gradle.tasks.bundling.BootJar
import org.springframework.boot.gradle.tasks.run.BootRun

plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

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

// Customize tasks registered by the Spring Boot plugin.
def chosenJarName = providers.gradleProperty('bootJarName')
    .orElse('provider-demo.jar')

tasks.named('bootJar', BootJar) {
    archiveFileName.set(chosenJarName)
}

tasks.named('bootRun', BootRun) {
    systemProperty 'demo.mode', 'training'
}

// Define custom tasks with properly typed inputs/outputs.
abstract class WriteBuildMarker extends DefaultTask {
    @Input
    abstract Property<String> getMessage()

    @OutputFile
    abstract RegularFileProperty getOutputFile()

    @TaskAction
    void generate() {
        File target = outputFile.get().asFile
        target.parentFile.mkdirs()
        target.setText(message.get() + '\n', 'UTF-8')
    }
}

abstract class PrintBuildMarker extends DefaultTask {
    @InputFile
    @PathSensitive(PathSensitivity.RELATIVE)
    abstract RegularFileProperty getSourceFile()

    @TaskAction
    void show() {
        String value = sourceFile.get().asFile.getText('UTF-8').trim()
        logger.quiet('MARKER=' + value)
    }
}

// tasks.register returns a TaskProvider, without requiring immediate task creation.
def markerTask = tasks.register('writeBuildMarker', WriteBuildMarker) {
    message.convention(
        providers.gradleProperty('buildMessage').orElse('READY')
    )
    outputFile.convention(
        layout.buildDirectory.file('generated/build-marker.txt')
    )
}

// flatMap wires producer output to consumer input.
tasks.register('printBuildMarker', PrintBuildMarker) {
    sourceFile.set(markerTask.flatMap { task -> task.outputFile })
}
~~~

**Role of each part:**

1. Java/Spring Boot plugins provide `compileJava`, `bootJar`, `bootRun`, etc. `tasks.named` only configures existing tasks.
2. `chosenJarName` is a `Provider<String>` from a project property with a fallback. `archiveFileName.set(chosenJarName)` maintains a lazy connection to the value source.
3. `bootRun` sets `demo.mode=training` on the development process Gradle launches.
4. `WriteBuildMarker` has `@Input Property<String>` and `@OutputFile RegularFileProperty`. These annotations help Gradle track inputs/outputs for up-to-date checks.
5. `PrintBuildMarker` takes `@InputFile` with `@PathSensitive(PathSensitivity.RELATIVE)`; its only job is to read the file and log the message.
6. `markerTask.flatMap { task -> task.outputFile }` connects the producer task's output provider to the consumer task's input property. Gradle retains file-producer metadata and infers the execution order automatically, without needing a separate `dependsOn`.
7. Calling `get()` inside `@TaskAction` is appropriate because at execution time the task needs the actual value/file. Do not query output files prematurely during build configuration.

### File `src/main/java/com/example/demo/DemoApplication.java`

~~~java
package com.example.demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CommandLineRunner showMode() {
        return args -> System.out.println(
                "BOOT_MODE=" + System.getProperty("demo.mode", "none")
        );
    }
}
~~~

This is a valid Java 17+ program with matching package and filename. `spring-boot-starter` does not start a web server; once the app starts successfully, `CommandLineRunner` prints the system property value and exits.

### Verifiable Commands and Outputs

The following Gradle commands assume the project **already has a Gradle Wrapper**. On Linux/macOS:

~~~bash
./gradlew -q printBuildMarker
~~~

Line printed by `PrintBuildMarker`:

~~~text
MARKER=READY
~~~

`build/generated/build-marker.txt` contains `READY` followed by a newline. Gradle runs producer `writeBuildMarker` before consumer `printBuildMarker` thanks to input/output provider wiring.

Change input via a CLI project property:

~~~bash
./gradlew -q printBuildMarker -PbuildMessage=CI
~~~

Line printed by the task:

~~~text
MARKER=CI
~~~

Because `message` is `@Input`, Gradle detects the change from `READY` to `CI` and re-executes the file-generating task. If inputs and outputs are unchanged, the producer can report `UP-TO-DATE` and skip rewriting the file.

Build the executable Boot JAR:

~~~bash
./gradlew -q bootJar
~~~

The filename from the default `chosenJarName` is `build/libs/provider-demo.jar`. Rename without editing the build script:

~~~bash
./gradlew -q bootJar -PbootJarName=release.jar
~~~

The artifact is configured as `build/libs/release.jar`. Files from previous builds may still sit in the output directory; when checking, pay attention to the artifact from the current build run.

Run the application via Gradle:

~~~bash
./gradlew bootRun --args='--spring.main.banner-mode=off --logging.level.root=OFF'
~~~

Line **printed by the application** (other Gradle/Boot logs may vary):

~~~text
BOOT_MODE=training
~~~

Run the artifact directly via the JVM after building `provider-demo.jar`:

~~~bash
java -jar build/libs/provider-demo.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Line printed by the application:

~~~text
BOOT_MODE=none
~~~

Pass the same system property for direct runtime execution:

~~~bash
java -Ddemo.mode=training -jar build/libs/provider-demo.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Line printed by the application:

~~~text
BOOT_MODE=training
~~~

Note that `-Ddemo.mode=training` must appear **before `-jar`** so the JVM recognizes it as a system property; Spring Boot application arguments go after the JAR filename. This experiment shows `bootRun` is a **development task**, while `java -jar` runs the artifact with independent runtime configuration.

If there is no wrapper yet but a compatible Gradle is installed on the machine, from the project directory you can generate the wrapper with `gradle wrapper --gradle-version 8.7`; then use `./gradlew`. On Windows PowerShell, use `.\gradlew.bat` and adjust argument quoting for the shell.

## 6. Wiring Output-to-Input with `flatMap` Instead of Concatenating Path Strings

This is the key relationship in the example:

~~~text
tasks.register('writeBuildMarker')
         |
         v
TaskProvider<WriteBuildMarker>
         |
         | flatMap { it.outputFile }
         v
Provider<RegularFile> (output with producer metadata)
         |
         | sourceFile.set(...)
         v
tasks.register('printBuildMarker') — @InputFile
         |
         v
Gradle infers: writeBuildMarker must run before printBuildMarker
~~~

Error-prone approach:

~~~groovy
// Knows the file path, but does not state who creates the file.
tasks.register('printBuildMarker', PrintBuildMarker) {
    sourceFile.set(
        layout.buildDirectory.file('generated/build-marker.txt')
    )
}
~~~

This snippet only knows **where the file lives**, not **which task creates it**. Calling the consumer when the file does not yet exist and no other dependency is declared may fail with a missing input file error. You could add an explicit `dependsOn(markerTask)`, but when the output file is the primary data passed between two tasks, wiring `TaskProvider.flatMap { it.outputFile }` keeps data flow and the task graph consistent.

Avoid doing:

~~~groovy
// May realize the producer early while extracting only a raw File.
def file = markerTask.get().outputFile.get().asFile
~~~

and using that raw `File` to configure the consumer. Doing so loses task dependency metadata and forces reading outputs prematurely. Pass the `Provider` directly into `RegularFileProperty`.

### When Is `dependsOn` Needed?

- Use `dependsOn(otherTaskProvider)` when one task must finish before another by **workflow ordering**, even without output/input properties to wire.
- Wire a producer's output property to a consumer's input property when the relationship is **data flow**.
- Use `mustRunAfter` to constrain ordering **when both are already in the graph**; it does not pull the other task in.
- Use `finalizedBy` for teardown/finalizer semantics in Gradle, not as a substitute for data dependencies.

There is no rule saying every task dependency must use `flatMap`. Pick the API that reflects the actual dependency reason.

## 7. Understanding Exactly When a Provider Is Evaluated

The Provider API **defers computation until the value is queried**, rather than promising every provider is only evaluated during the execution phase. In this case:

~~~groovy
def outputName = providers.gradleProperty('bootJarName')
    .orElse('service.jar')

tasks.named('bootJar') {
    archiveFileName.set(outputName)
}
~~~

Gradle can hold the provider until the filename is actually needed to set the task output. However, if you write `outputName.get()` inside a configuration action, the value is queried when that action runs (usually before execution).

Similarly, `tasks.named('bootJar')` does not make Gradle instantiate the task object at lookup time; yet if another piece of code calls `tasks.named('bootJar').get()`, the task can still be realized early. Configuration avoidance only succeeds when **the entire chain of build logic** avoids unnecessary eager APIs.

### Providers from Environment Variables

~~~groovy
def label = providers.environmentVariable('BUILD_LABEL')
    .orElse('local')
~~~

This is modeled better by Gradle than calling `System.getenv('BUILD_LABEL')` arbitrarily inside task configuration. However, not every older API accepts a `Provider<T>` directly. If an API requires resolving immediately, resolve intentionally and evaluate the impact on the configuration cache. Do not write secrets into manifests, archives, or build logs just to experiment with the Provider API.

### `convention`, `set`, and Finalized Values

`Property<T>` can be configured by plugins, convention plugins, and build scripts. `convention` means default; `set` is an explicit value selection. APIs like `finalizeValue()` and `finalizeValueOnRead()` lock values after configuration, but calling them at the wrong moment can prevent other plugins from adding configuration. For foundational learning, understanding `set`/`convention`/`get` is sufficient; deeper property lifecycle control matters when authoring advanced plugins.

### Easy-to-Miss Eager APIs

| Pattern that may cause eager configuration | Replace with |
| --- | --- |
| `tasks.create('x')` | `tasks.register('x')` |
| `tasks.getByName('x') { ... }` | `tasks.named('x') { ... }` |
| `tasks.all { ... }` | `tasks.configureEach { ... }` when appropriate |
| `tasks.withType(Test) { ... }` | `tasks.withType(Test).configureEach { ... }` |
| `taskProvider.get()` just to pass a dependency | Pass `taskProvider` directly |
| `taskProvider.get().outputFile.get()` at configuration time | `taskProvider.flatMap { it.outputFile }` |

Do not replace every API mechanically: sometimes you genuinely need a task object or immediate value, but that should be an intentional choice after understanding the configuration consequences.

## 8. Kotlin DSL and Groovy DSL: Same Model, Different Syntax

The main practice exercise is written in **Groovy DSL `build.gradle`**. In `build.gradle.kts`, the ideas are identical, while API calls use generics:

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar
import org.springframework.boot.gradle.tasks.run.BootRun

val archiveName = providers.gradleProperty("bootJarName")
    .orElse("service.jar")

tasks.named<BootJar>("bootJar") {
    archiveFileName.set(archiveName)
}

tasks.named<BootRun>("bootRun") {
    systemProperty("demo.mode", "training")
}
~~~

This is a **configuration snippet for a Kotlin DSL project that has already applied the required plugins**, not a standalone `build.gradle.kts` file. Do not copy generic syntax `named<BootJar>` into Groovy `build.gradle`. In Kotlin DSL, a custom task can use `abstract val message: Property<String>` with `@get:Input`; in Groovy DSL the example uses abstract getter `getMessage()`.

## 9. Debugging at the Right Layer

| Symptom | Cause to inspect | Resolution |
| --- | --- | --- |
| `Task with name 'bootJar' not found` | Boot/Java plugin has not created the task, or configuring wrong subproject | Check plugins, task list, and target project |
| `Task with name 'bootWar' not found` | No WAR plugin/task in the module | Configure only when the project has `bootWar` |
| Provider `get()` reports no value present | Missing `set`/`convention` or missing project property | Use `orElse` for optional values or declare required input |
| Consumer task reports `@InputFile` missing | Missing producer dependency or wrong path | Wire `TaskProvider.flatMap` to output property or add needed dependency |
| Custom task always re-runs | Missing input/output metadata or outputs keep changing | Declare `@Input`/`@OutputFile`/`@InputFile` properly; avoid hidden inputs |
| Task is `UP-TO-DATE` when you expected it to run | Inputs/outputs did not change | Inspect `--info` logs; try `--rerun-tasks` when diagnosing |
| `bootRun` configured but `java -jar` differs | Standalone runtime is independent from the Gradle task | Pass JVM args/application args at deployment |
| Output JAR has a different name | `archiveFileName`, classifier, destination, or another script overrides it | Inspect effective task properties and files in `build/libs` |
| Configuration time takes too long | Many `getByName`, `create`, `tasks.all`, or eager code | Use `register`/`named`/`configureEach` appropriately |
| Configuration cache error | Action/closure captures `Project` or accesses resources improperly | Read exact cause, use `Provider`/`Property` and proper task types |

Useful diagnostic commands:

~~~bash
./gradlew tasks --all
./gradlew help --task bootJar
./gradlew bootJar --dry-run
./gradlew bootJar --info
./gradlew printBuildMarker --rerun-tasks
./gradlew help --configuration-cache
~~~

`tasks --all` shows registered tasks but may realize some tasks to list them; do not use task realization counts from listing to measure normal build configuration avoidance. `--dry-run` only previews the task graph and **does not produce artifacts**. `--info` gives more detailed up-to-date check logs; `--rerun-tasks` forces re-execution for diagnostics. `--configuration-cache` tests storing and reusing configuration; read exact warnings if the cache cannot be used.

## 10. Workflow for Applying in Real Spring Boot Projects

1. **Identify task ownership.** `bootJar` and `bootRun` are provided by the Spring Boot plugin; for custom tasks, use `tasks.register`.
2. **Verify the task exists in the right project.** Do not use `tasks.named` to create tasks, and do not configure `bootWar` in a JAR-only project.
3. **Configure tasks lazily.** Use `tasks.named('bootJar', BootJar) { ... }` and `withType(...).configureEach` when setting policies across multiple tasks.
4. **Use typed Properties and Providers.** Read project properties via `providers.gradleProperty`, file outputs via `layout.buildDirectory.file`; wire `set(Provider)` instead of calling `get()` early.
5. **Model inputs/outputs on custom tasks.** Use `@Input`, `@OutputFile`, `@InputFile`, and proper path sensitivity so Gradle knows when to re-run.
6. **Wire producers and consumers via data.** If a consumer task needs a file from a producer, obtain the output via `taskProvider.flatMap` to preserve metadata and dependencies.
7. **Distinguish build and runtime.** `bootRun` is only for running through Gradle; verify the packaged executable JAR with `java -jar`.
8. **Verify via task graph, artifacts, and actual outputs.** Do not assume code is "lazy" solely from syntax; check whether other code realizes tasks or resolves Providers early.

## 11. Self-Check Questions

**Question 1.** Does `tasks.named('bootJar')` create or execute the `bootJar` task?

**Answer:** No. It retrieves the `TaskProvider` of an already-registered task and can attach lazy configuration logic.

**Question 2.** Why is `tasks.register` generally recommended over `tasks.create`?

**Answer:** `register` avoids creating/configuring the task until needed. `create` instantiates the task eagerly, increasing configuration cost for tasks that do not need to run.

**Question 3.** How does `Property<String>.set(provider)` differ from calling `provider.get()` and then `set(value)`?

**Answer:** The first keeps a lazy link to the provider; the second queries the value immediately at the moment `get()` is called.

**Question 4.** When should you use `map` vs. `flatMap`?

**Answer:** Use `map` when transforming a plain value into another plain value; use `flatMap` when the transformation returns another `Provider`, especially when extracting an output property from a `TaskProvider`.

**Question 5.** Why does `PrintBuildMarker` automatically run after `WriteBuildMarker` without `dependsOn` in the practice exercise?

**Answer:** The input file is wired to the producer's output provider, so Gradle carries the producer task information and establishes the necessary dependency.

**Question 6.** Are JVM system properties configured in `bootRun` saved inside the executable Boot JAR?

**Answer:** No. The `bootRun` task only configures the JVM launched by Gradle; `java -jar` in deployment receives its own runtime configuration.

**Question 7.** Why is `tasks.named('bootJar').get()` discouraged if you only want to change `archiveFileName`?

**Answer:** `get()` can realize the task unnecessarily early; `tasks.named('bootJar') { archiveFileName.set(...) }` keeps configuration lazy.

## Official Documentation

- Gradle — [Avoiding Unnecessary Task Configuration](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): `register`, `named`, `configureEach`, and eager APIs.
- Gradle — [Configuring Tasks Lazily](https://docs.gradle.org/current/userguide/lazy_configuration.html): `Provider`, `Property`, `map`/`flatMap`, and wiring task inputs/outputs.
- Gradle — [Properties and Providers](https://docs.gradle.org/current/userguide/properties_providers.html): provider chaining and fallbacks.
- Spring Boot — [Packaging Executable Archives](https://docs.spring.io/spring-boot/gradle-plugin/packaging.html): `bootJar`, `bootWar`, and archive options.
- Spring Boot — [Running Your Application with Gradle](https://docs.spring.io/spring-boot/gradle-plugin/running.html): `bootRun` and `JavaExec`.

**Remember:** `tasks.named` **configures tasks only when needed**; the Provider API **supplies values only when needed**; typed input/output properties let Gradle **understand data flow and inter-task dependencies**. Together, all three produce build logic that is clear, verifiable, and configuration-cache friendly.
