# Using Gradle Up-to-Date Checks and Incremental Compilation

## Objectives

In a Spring Boot project, every time we change a few lines of Java or an `application.properties` file, we do not want Gradle to recompile all source code, re-run unnecessary steps, or re-package an identical JAR. Gradle provides **work avoidance** and **incremental execution** mechanisms to shorten the edit → test → run feedback loop.

This lesson focuses on two primary mechanisms:

- **Up-to-date checking:** Gradle **skips an entire task** when its relevant inputs, outputs, and execution state have not changed since the last successful run.
- **Incremental Java compilation:** when `compileJava` **actually needs to execute**, Gradle can compile **only the affected Java classes** instead of compiling the entire source set.

Related but distinct concepts include **compilation avoidance** (avoiding recompilation of dependent modules when the ABI has not changed), **build cache** (restoring task outputs with matching cache keys), **configuration cache** (restoring configuration/task graphs), and **dependency cache** (reusing downloaded libraries).

After this lesson, you will be able to:

1. Accurately read `UP-TO-DATE`, `FROM-CACHE`, `NO-SOURCE`, `SKIPPED`, and normally executed task outcomes.
2. Explain how Gradle uses input/output fingerprints, classpaths, task implementations, and execution history to decide whether to run a task.
3. Set up a Spring Boot Java 17+ application, build twice, make controlled Java/resource edits, and explain `compileJava`/`processResources`/`test`/`bootJar` outcomes.
4. Compare editing a **method body** versus editing a **public API/ABI**, as well as the impact of annotation processors.
5. Declare complete inputs/outputs for custom tasks and values used during resource filtering.
6. Measure incremental effectiveness via `--info` logs without confusing it with `clean`, `--rerun-tasks`, or skipped tests.
7. Troubleshoot builds that always re-run or falsely report up-to-date, keeping released artifacts accurate.

**Example context:** Spring Boot **3.3.13**, Java **17**, compatible Gradle **8.x**, primarily Groovy DSL. Features are referenced against official Gradle Java Plugin/Incremental Build documentation; exact syntax should be verified against your project's Gradle Wrapper. This is a hands-on lesson and does not require upgrading versions or modifying a production repository.

---

## 1. Four Different Questions in a Single Build

A project may contain these tasks:

```text
src/main/java/*.java --> compileJava ------------> build/classes/java/main/
src/main/resources/  --> processResources -------> build/resources/main/
                                  \                  /
                                   +--- classes ----+
                                            |
                                            +-- bootJar --> build/libs/*-SNAPSHOT.jar

src/test/java/      --> compileTestJava
src/test/resources/ --> processTestResources
                                  |
                                  v
                                 test
                                  |
                                  v
                                 check

                         assemble + check --> build
```

This is a **conceptual diagram**: the actual task graph depends on plugins and configuration. `bootJar` is added by the Spring Boot Gradle plugin when the Java plugin is applied; `compileJava` and `processResources` come from the Gradle Java plugin.

When reading a task line in the console, ask:

1. **Was the task selected into the graph?** For instance, running `classes` differs from running `build`.
2. **Did the task execute its actions?** `UP-TO-DATE` means no work was needed.
3. **If it executed, did it process everything or incrementally?** `compileJava` can run incrementally.
4. **If it did not execute, where did the output come from?** Local execution history differs from the build cache.

Example command:

```bash
./gradlew build --console=plain --info
```

The first run typically executes many tasks; the second run, if sources/resources/config did not change, can skip many tasks. When one Java file is modified, `compileJava` is **no longer up-to-date**, yet the compiler may only compile a very small slice. That is the main optimization target.

## 2. Reading Task Outcomes Accurately

| Console label | Definition | What not to infer |
| --- | --- | --- |
| `UP-TO-DATE` | Task did not execute because Gradle determined existing outputs remain valid for current inputs/history. | Does not mean "compiler ran incrementally"; the task was skipped. |
| `FROM-CACHE` | Gradle restored task outputs from the build cache instead of running actions. | Does not necessarily mean local history existed from the previous run. |
| `NO-SOURCE` | A source-based task had no matching input files to process. | Does not mean it compiled a source and skipped because nothing changed. |
| `SKIPPED` | Task was skipped due to a condition like `onlyIf` or otherwise excluded from execution. | Does not mean tests ran or passed. |
| No label | The task executed. | Does not mean full recompilation; it may have been incremental. |
| `FAILED` | The task failed. | Read the actual cause; do not immediately blame caching. |

**Illustrative** output example (**not an actual log**):

```text
> Task :compileJava UP-TO-DATE
> Task :processResources UP-TO-DATE
> Task :classes UP-TO-DATE
> Task :bootJar UP-TO-DATE
> Task :test UP-TO-DATE
BUILD SUCCESSFUL
```

Not every Gradle version/plugin produces these exact lines. `processResources` may report `NO-SOURCE` if there are no resource files; lifecycle tasks may have no actions. The set of displayed tasks also changes when invoking `bootJar` instead of `build`.

**Essential distinction:**

- `compileJava UP-TO-DATE` → **no classes compiled**.
- `compileJava` runs because one `.java` file changed → **may** compile only affected classes.
- `compileJava FROM-CACHE` → outputs were **restored**, no compiler run needed.
- `compileJava SKIPPED` → skipped by another condition; insufficient basis to assume outputs are fresh.

## 3. Up-to-Date Checking: Inputs, Outputs, and History

### 3.1 How it works

Every optimizable task has:

- **Inputs:** source files, dependency classpath, task options, and configuration values affecting output.
- **Outputs:** files/directories created or updated by the task.
- **Task implementation:** the task's logic and the classpath containing the implementation/plugin.
- **Execution history:** fingerprints of inputs/outputs from the previous successful run.

For `compileJava`, inputs can include `.java` files, compile classpath, Java toolchain, and compiler flags. Outputs include `.class` files and related build data. Gradle fingerprints inputs/outputs; next time, if everything matches, the task can be marked `UP-TO-DATE` and its actions skipped.

```text
Run 1: Java sources A.java, B.java + compile classpath X
        --> compileJava executes --> A.class, B.class
        --> Gradle records fingerprints

Run 2: inputs/outputs unchanged
        --> compileJava UP-TO-DATE, javac not invoked

Run 3: B.java modified
        --> compileJava must execute
        --> incremental compiler determines affected classes

Run 4: code unchanged, compile classpath changed
        --> may require compilation task to run
```

When **outputs are deleted or altered externally**, Gradle may need to re-run because output fingerprints are no longer valid. However, if outputs exist in an enabled build cache, they can be restored `FROM-CACHE` without running the compiler.

Do not simulate changes by modifying file bytes while artificially preserving both `lastModified` and file size: Gradle may leverage file metadata to optimize hashing. Perform normal edits and inspect contents and logs.

### 3.2 Undeclared inputs: a common bug

Suppose a task generates `build-info.properties` from environment variable `BUILD_LABEL`, but only declares a source file and not the environment value. When `BUILD_LABEL` changes, Gradle may consider the task `UP-TO-DATE` and keep stale outputs.

**Fix:** register that value as a task input, e.g., `inputs.property('buildLabel', ...)` or an `@Input`-annotated property in a custom task type. If outputs are undeclared, Gradle likewise lacks full information to perform up-to-date checks or caching.

**Do not overuse inputs:** setting the current timestamp or a random value as an input when the output does not need it will invalidate the task every time. Every input should have a genuine relationship to the output.

### 3.3 Output directories, target files, and task dependencies

Gradle tracks declared task outputs and can infer task dependencies when another task consumes outputs via a provider/task object. If a custom task writes into `build/classes/java/main` without declaring a relationship with `compileJava`, it can cause race conditions and corrupted up-to-date state.

In a well-structured build:

- A task should **own its own outputs**.
- A task consuming another task's output should use `TaskProvider`/`Provider` or appropriate `dependsOn`.
- Never let two custom tasks write to the same path without explicit design.
- Do not edit files inside `build/libs` after `bootJar` and expect Gradle to know the artifact is still valid.

Optimizations must safeguard **output correctness first**.

## 4. Incremental Java Compilation and ABI

### 4.1 Incremental compile differs from task skipping

`JavaCompile` in modern Gradle has **incremental compilation enabled by default**. When the task needs to run, Gradle analyzes which classes are affected by code/ABI changes.

Example:

```text
DemoApplication  ----uses----> Calculator
Unrelated           (does not use Calculator)
```

If only a **method body** in `Calculator` changes while its signature and public API remain unchanged, the compiler can avoid recompiling `DemoApplication` or `Unrelated`. If the public API changes, consumers may be affected.

Saying "**incremental compilation**" does not mean "**strictly one class file is compiled**": one source file can produce multiple class files, inner classes, or generated code; annotation processors and classpath changes can widen the scope.

### 4.2 Method body vs. API/ABI

Before:

```java
public int add(int left, int right) {
    return left + right;
}
```

Change the body while keeping the signature:

```java
public int add(int left, int right) {
    int result = left + right;
    return result;
}
```

In many cases this change is **ABI-compatible**, because consumers still call `int add(int,int)`. `Calculator.java` changed so `compileJava` may need to run, but not every consumer needs recompilation.

Change the signature:

```java
public long add(int left, int right) {
    return (long) left + right;
}
```

Changing the public return type from `int` to `long` is an ABI change. Consumers must be checked/recompiled against the new signature. Some public method changes cause compilation errors if call sites become incompatible—for example, renaming `add` to `sum` without updating callers.

**ABI** covers more than just "public vs. non-public": accessible signatures, superclasses/interfaces, constants that can be inlined, and elements consumers need to link against at compile time. Exact rules also depend on bytecode and the compiler.

### 4.3 Compile avoidance across projects

In a Gradle multi-project build:

```text
:core:compileJava  --> :core:jar
                            |
                            v
                   :app:compileJava --> :app:bootJar
```

If module `:core`'s implementation changes without changing its ABI, `:app:compileJava` **can remain UP-TO-DATE** via compile avoidance. However, `:app:bootJar` **may need to run again** because `:core`'s runtime JAR has new bytes that must be packaged into the executable Spring Boot archive.

Therefore:

> "Not recompiling the app" **does not mean** "not repackaging the app."

If `:core` changes a public interface or compile-classpath ABI, consumer compile tasks may need to re-run. This is why Gradle's `java-library` plugin with `api` and `implementation` helps maintain boundaries between public API and internal dependencies, reducing unnecessary invalidations.

### 4.4 When incremental compilation is no longer narrow

Cases to investigate:

- Public ABI changed in a way affecting consumers.
- Compile-time constants such as `public static final int LIMIT = 10` are inlined into consumer classes; changing the constant can force wider recompilation.
- An annotation processor is not incremental, or reads undeclared inputs.
- Source-retention annotations are difficult to infer from bytecode.
- Significant changes in compiler flags, Java toolchain, or classpath.
- Previous compilation failed, no suitable history exists, or compile state was recently deleted.
- Using custom `javaHome`/`executable` instead of Java toolchains makes some optimizations harder to apply.
- Unusual source/package layouts or other plugins modifying compiler inputs.

Do not observe a full recompilation and immediately scatter `options.incremental=true` across every task; modern Gradle `JavaCompile` enables it by default. Read `--info` to find the **actual cause**.

## 5. Hands-On Spring Boot Java 17+ Project

### 5.1 Structure

```text
gradle-incremental-demo/
├── settings.gradle
├── build.gradle
├── gradlew / gradlew.bat                 (if Wrapper is generated)
├── gradle/wrapper/...
└── src/
    ├── main/
    │   ├── java/com/example/demo/
    │   │   ├── DemoApplication.java
    │   │   ├── Calculator.java
    │   │   └── Unrelated.java
    │   └── resources/build-info.properties
    └── test/java/com/example/demo/CalculatorTest.java
```

Use a **lab** project—no extra modules are needed to start. If the project does not yet have a Wrapper, generate one with a compatible Gradle version: `gradle wrapper --gradle-version 8.5`. The `./gradlew` commands below only work once the Wrapper exists; on Windows PowerShell use `.\gradlew.bat`.

### 5.2 `settings.gradle`

```groovy
rootProject.name = 'gradle-incremental-demo'
```

### 5.3 Complete `build.gradle` (Groovy DSL)

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
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
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

- `java` provides `compileJava`, `processResources`, `classes`, `test`, and standard archive tasks.
- `org.springframework.boot` combined with Java creates `bootJar`/`bootRun`.
- `io.spring.dependency-management` imports the BOM supported by the Spring Boot plugin; it is **not** an incremental compilation mechanism.
- The Java toolchain directs Gradle to use an appropriate Java 17 for compilation/testing; the JDK running the Gradle daemon and the compiler toolchain can differ.
- `test` is configured for JUnit Platform.

No need to force `options.incremental=true`; use the Gradle Java plugin default for this exercise.

### 5.4 `Calculator.java`

Path `src/main/java/com/example/demo/Calculator.java`:

```java
package com.example.demo;

public final class Calculator {

    public int add(int left, int right) {
        return left + right;
    }
}
```

This is plain Java with no Spring dependencies. `DemoApplication` below uses it.

### 5.5 `DemoApplication.java`

Path `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
        System.out.println("SUM=" + new Calculator().add(2, 3));
    }
}
```

The project has one main class, so `bootJar` can determine the startup class under standard configuration. After `java -jar` on a valid Boot JAR, the application prints the line generated by the code itself:

```text
SUM=5
```

In addition to that line, Spring Boot banners/logs may appear. Do not invoke `javac DemoApplication.java` standalone without supplying Spring Boot dependencies; use Gradle.

### 5.6 `Unrelated.java`

```java
package com.example.demo;

public final class Unrelated {

    public String message() {
        return "unrelated";
    }
}
```

This class does not reference `Calculator`, illustrating how the incremental compiler can avoid touching unrelated classes.

### 5.7 `CalculatorTest.java`

Path `src/test/java/com/example/demo/CalculatorTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CalculatorTest {

    @Test
    void addsTwoIntegers() {
        assertEquals(5, new Calculator().add(2, 3));
    }
}
```

JUnit 5 test verifying the result. `./gradlew test` runs tests using the Gradle config above; **passing tests do not prove the executable JAR is correct**—the artifact must be built and verified separately.

### 5.8 `build-info.properties`

Path `src/main/resources/build-info.properties`:

```properties
app.label=demo
```

This is a simple resource to observe `processResources`. With no filtering yet, Gradle defaults to copying it to `build/resources/main/build-info.properties`.

## 6. Experiment 1 – Two Builds Without Changing Inputs

Run on macOS/Linux:

```bash
./gradlew --version
./gradlew build --console=plain --info
./gradlew build --console=plain --info
```

Windows PowerShell:

```powershell
.\gradlew.bat --version
.\gradlew.bat build --console=plain --info
.\gradlew.bat build --console=plain --info
```

**How to measure properly:**

1. The first run may execute `compileJava`, `processResources`, `compileTestJava`, `test`, and `bootJar`.
2. Do not edit sources, resources, Gradle scripts, dependencies, or environment settings between the two runs.
3. The second run typically marks tasks `UP-TO-DATE` if outputs remain intact and execution history is valid.
4. If any task still executes, read the explanation in `--info` rather than assuming Gradle is broken.
5. Record Gradle/JDK versions, command, outcomes, and durations if benchmarking.

You can save logs in the practice workspace:

```bash
./gradlew build --console=plain --info > first-build.log 2>&1
./gradlew build --console=plain --info > second-build.log 2>&1
```

Log files may contain machine paths, repository URLs, or internal configuration; inspect them before sharing.

**Conditional illustrative output**:

```text
# First run (with sources)
> Task :compileJava
> Task :processResources
> Task :test
> Task :bootJar

# Subsequent run (no input changes)
> Task :compileJava UP-TO-DATE
> Task :processResources UP-TO-DATE
> Task :test UP-TO-DATE
> Task :bootJar UP-TO-DATE
```

This is not actual stdout captured from a learner's environment. `classes`/`build` or test task states may vary based on task lifecycle and inputs.

## 7. Experiment 2 – One Java Source Changes Without Changing ABI

In `Calculator.java`, edit only the method body:

```java
public int add(int left, int right) {
    int result = left + right;
    return result;
}
```

Run:

```bash
./gradlew compileJava --console=plain --info
```

This edit makes `Calculator.java` differ from before, so `compileJava` generally must run instead of `UP-TO-DATE`. However, the public signature `int add(int,int)` did not change, so the incremental compiler can process only affected classes and avoid unnecessary consumer recompilation.

**Do not draw conclusions from the task label alone**: when a task runs, the console only shows that it executed. To know whether compilation was incremental or full, read `--info` and observe which sources/classes Gradle processed according to that version's logs. Exact log wording can vary across Gradle versions.

### 7.1 Changing the public API

On a copy/experimental branch, change the signature to:

```java
public long add(int left, int right) {
    return (long) left + right;
}
```

Consumer `DemoApplication` must see the new binary contract; compilation scope may widen. Java can still concatenate a `long` into a `String`, so `java -jar` adding 2+3 will still print `SUM=5`. If you rename `add` to `sum` without updating the caller, the compiler reports a missing method error—a valid error because the call site is now wrong.

After the experiment, revert `Calculator.java` to returning `int` to continue the lesson.

### 7.2 Changing an unrelated class

Change `Unrelated.message()` from `"unrelated"` to `"independent"` and run `compileJava --info`. The task runs because that file changed; the incremental compiler can avoid reprocessing `Calculator` and `DemoApplication` since they are unaffected. Do not promise "always strictly one `.class` file" due to inner classes, annotation processors, state history, and other factors.

### 7.3 Build only the task you want to observe

When checking the compiler, run `./gradlew compileJava` instead of `build` so test and packaging time are not mixed in. When ready to verify the artifact, run `bootJar` or `build` and test with `java -jar`. A successful `compileJava` **does not prove the executable JAR is updated**.

## 8. Experiment 3 – Editing a Resource: Does the Java Compiler Re-Run?

Edit `src/main/resources/build-info.properties`:

```properties
app.label=release-candidate
```

Then run:

```bash
./gradlew classes --console=plain --info
./gradlew bootJar --console=plain --info
```

Conditional predictions:

- `processResources` re-runs because a resource input changed.
- `compileJava` can remain `UP-TO-DATE` because Java sources and the compiler classpath did not change.
- `bootJar` may repackage because the classpath output contains the updated resource.
- The processed file lives at `build/resources/main/build-info.properties`; inside a standard executable Spring Boot JAR it lives at `BOOT-INF/classes/build-info.properties`.

You can inspect it with:

```bash
jar tf build/libs/gradle-incremental-demo-0.0.1-SNAPSHOT.jar
```

The path follows the example's `rootProject.name`/`version`. If you changed archive basename/classifier, use the actual filename under `build/libs`.

**Do not register all resources as inputs to `JavaCompile`** when the compiler does not use them. Doing so triggers needless recompilation whenever an image or Spring config file changes. If an annotation processor reads a resource to generate code, declare that input appropriately—that is a different case.

## 9. Declaring Inputs for `processResources` to Avoid Stale Outputs

A common scenario is injecting `project.version` into a resource during the build. If Gradle does not know which value changes the file, the task may falsely report `UP-TO-DATE`.

### 9.1 Resource template file

Update `src/main/resources/build-info.properties` to:

```properties
app.version=${appVersion}
```

Add at the **end of `build.gradle`** from Section 5:

```groovy
def appVersionValue = project.version.toString()

tasks.named('processResources') {
    inputs.property('appVersion', appVersionValue)

    filesMatching('build-info.properties') {
        expand(appVersion: appVersionValue)
    }
}
```

- `filesMatching` selects only the template file to expand.
- `expand` uses Groovy template syntax to replace `${appVersion}` with the version string.
- `inputs.property` registers this value as a task input; if the version changes, Gradle knows to re-run.
- Other resources continue to be copied normally; avoid batch-filtering binary files like PNGs or Spring runtime configs.

With `version='0.0.1-SNAPSHOT'`, `build/resources/main/build-info.properties` after `processResources` is expected to be:

```properties
app.version=0.0.1-SNAPSHOT
```

**Watch out for Spring placeholders:** `application.properties` may contain `server.port=${PORT:8080}` for Spring to resolve at runtime. Gradle's `expand` also parses `${...}` syntax and can conflict. Only expand `build-info.properties` or escape properly if you must filter Spring config. Never call `expand(project.properties)` across all resources.

### 9.2 Kotlin DSL equivalent

Snippet for `build.gradle.kts` in a project with the Java plugin:

```kotlin
val appVersionValue = project.version.toString()

tasks.processResources {
    inputs.property("appVersion", appVersionValue)

    filesMatching("build-info.properties") {
        expand(mapOf("appVersion" to appVersionValue))
    }
}
```

Do not paste Groovy syntax like `expand(appVersion: appVersionValue)` into Kotlin DSL. This is only the `processResources` customization; plugins/dependencies/toolchains for the full project must be configured separately.

### 9.3 Test up-to-date behavior and changing version values

```bash
./gradlew processResources --console=plain --info
./gradlew processResources --console=plain --info
```

With unchanged inputs, the second run can report `UP-TO-DATE`. On an experimental branch, change `version` to `0.0.2-SNAPSHOT` and re-run. Because `appVersion` is a declared input, Gradle should produce:

```properties
app.version=0.0.2-SNAPSHOT
```

When a real project changes `version`, other tasks such as `bootJar` may also need to run because the archive name and contents change. Do not look only at the task outcome: **open the actual output file** to verify the contents were substituted.

## 10. Custom Tasks: Inputs/Outputs and the Provider API

### 10.1 Example creating a file from an environment input

Add to the end of `build.gradle`:

```groovy
def buildChannel = providers.environmentVariable('BUILD_CHANNEL')
    .orElse('local')

def outputFile = layout.buildDirectory.file('generated/build-channel.txt')

tasks.register('writeBuildChannel') {
    inputs.property('buildChannel', buildChannel)
    outputs.file(outputFile)

    doLast {
        def target = outputFile.get().asFile
        target.parentFile.mkdirs()
        target.setText(buildChannel.get() + '\n', 'UTF-8')
    }
}
```

This is a **working custom task in a Gradle Groovy DSL project** with or without Java. It reads `BUILD_CHANNEL` via a Provider defaulting to `local`, and writes a dedicated output at `build/generated/build-channel.txt`.

Run:

```bash
./gradlew writeBuildChannel --console=plain --info
./gradlew writeBuildChannel --console=plain --info
```

The second run can report `UP-TO-DATE`. In Bash, run `BUILD_CHANNEL=qa ./gradlew writeBuildChannel`; in Windows PowerShell, set `$env:BUILD_CHANNEL = 'qa'` then run `.\gradlew.bat writeBuildChannel`. When the input changes, the output file should change to `qa` followed by a newline.

This custom task output is **standalone** and not automatically placed in the JAR. To include generated files in `processResources`, wire the task output with `TaskProvider`/`from(taskProvider)` or an equivalent mechanism so dependencies are inferred or declared. Never write directly into `src/main/resources` on every build assuming Gradle automatically treats it as a task output.

### 10.2 Why not read environment variables in `doLast` without declaring them?

Common mistake:

```groovy
tasks.register('badTask') {
    outputs.file(layout.buildDirectory.file('bad.txt'))

    doLast {
        file("$buildDir/bad.txt")
            .text = System.getenv('BUILD_CHANNEL')
    }
}
```

This is an **anti-pattern to avoid**, never to be used in release builds: the task uses an environment variable to produce output without declaring it as an input, and uses APIs/paths poorly suited for `Provider` and the configuration cache. Results may go stale or lack information needed for Gradle validation. **Fix the input/output modeling** instead of relying on `--rerun-tasks` permanently to mask the bug.

### 10.3 `InputChanges` for incremental custom tasks

A task with complete inputs/outputs can achieve **UP-TO-DATE**, yet when one input file changes and the task **runs**, it will not automatically process only that file. For **incremental execution inside a custom task**, a task type can use:

- `@InputFiles` or `@InputDirectory` for source collections.
- `@Incremental` on supported file input properties.
- `@PathSensitive` to define how paths affect fingerprints.
- `@OutputDirectory` or `@OutputFile` for outputs.
- An `InputChanges` parameter in `@TaskAction` and `getFileChanges(...)` to inspect `ADDED`, `MODIFIED`, and `REMOVED` files.

The task must also handle **REMOVED** entries (deleting corresponding outputs) and fall back to a valid **full rebuild** when `InputChanges.isIncremental()` is false. This API is meant for **custom task/plugin authors**, not something to add to `compileJava` (`JavaCompile` already uses Gradle's incremental engine).

Do not hand-roll single-file processing if built-in `Copy`/`Sync` tasks already fit the requirement. For custom generators, design incremental output mapping before optimizing.

### 10.4 Output determinism

Tasks that read wall-clock time, random values, unstable networks, or external secrets without modeling them will produce invalid cache entries. For a task to be cacheable, **its outputs must be fully determined by declared inputs and task implementation**; adding `outputs.file` alone does not make a task safe for remote caching.

Do not add the current timestamp as an input to every task just to "force a fresh build." That defeats Gradle optimizations and can produce non-reproducible artifacts.

## 11. Multi-Project: Avoiding Consumer Recompilation When ABI Is Unchanged

### 11.1 Simple layout

```text
multi-project/
├── settings.gradle
├── core/
│   ├── build.gradle
│   └── src/main/java/com/example/core/Formatter.java
└── app/
    ├── build.gradle
    └── src/main/java/com/example/app/AppApplication.java
```

`settings.gradle`:

```groovy
rootProject.name = 'multi-project'
include 'core', 'app'
```

`core/build.gradle`:

```groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

`core/src/main/java/com/example/core/Formatter.java`:

```java
package com.example.core;

public final class Formatter {

    public String format(String value) {
        return "message=" + value;
    }
}
```

`app/build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation project(':core')
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

`app/src/main/java/com/example/app/AppApplication.java`:

```java
package com.example.app;

import com.example.core.Formatter;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AppApplication {

    public static void main(String[] args) {
        SpringApplication.run(AppApplication.class, args);
        System.out.println(new Formatter().format("ok"));
    }
}
```

Run:

```bash
./gradlew :app:bootJar --console=plain --info
```

With a console app and resolved dependencies, running the executable JAR prints the code-generated line:

```text
message=ok
```

This is not the entire stdout (Spring Boot may also print logs).

### 11.2 Modifying `:core`'s implementation

Change the method body:

```java
public String format(String value) {
    String result = "message=" + value;
    return result;
}
```

When `Formatter`'s ABI has not changed, Gradle can:

- Run `:core:compileJava` because its source changed.
- Keep `:app:compileJava UP-TO-DATE` via compilation avoidance.
- Re-run `:app:bootJar` because the runtime `core` library has new bytes to package into the archive.

**Those are three separate decisions**, with no contradiction. Changing a method signature or public interface in `:core` may invalidate `:app:compileJava` and trigger recompilation.

### 11.3 `api`/`implementation` boundary

In a `java-library` module, declare a dependency as `api` if its types appear in the public API required by consumers at compile time; use `implementation` for internal-only libraries. Narrowing downstream compile classpaths can improve compile avoidance when internal dependencies change.

Do not switch everything to `implementation` if public methods actually expose types from that library; consumers could miss required classes at compile time. Optimizations must align with API boundaries.

## 12. Annotation Processors and Impact on Incremental Compilation

### 12.1 Separate processor classpath configuration

Lombok example:

```groovy
dependencies {
    compileOnly 'org.projectlombok:lombok:1.18.36'
    annotationProcessor 'org.projectlombok:lombok:1.18.36'

    testCompileOnly 'org.projectlombok:lombok:1.18.36'
    testAnnotationProcessor 'org.projectlombok:lombok:1.18.36'
}
```

This is a **snippet** from a project with `repositories` and appropriate dependencies. `compileOnly` provides the annotation API to the compiler; `annotationProcessor` supplies the processor to generate code. Never add a processor to `implementation` just so "the compiler can find it" if it is not needed at runtime.

### 12.2 Isolating, aggregating, and non-incremental

Gradle supports incremental annotation processing when processors follow the contract:

- **Isolating:** generated files depend on a single annotated element, allowing narrow handling of edits.
- **Aggregating:** a generated file aggregates data from multiple annotated elements, potentially requiring wider reprocessing.
- **Non-incremental/improperly declared:** can force full recompilation.
- **Processors reading external resources:** those resources must be declared as inputs. When they change, Gradle may perform a full recompile depending on input/processor type.

Run `./gradlew compileJava --info` to see whether Gradle reports any processor as not supporting incremental processing. **Do not assume from an online support table that your exact version is incremental**, as support can change across Gradle/JDK/processor versions.

### 12.3 Conditions that force wider recompilation

Changing compile-time constants, source-retention annotations, compiler options, custom Java home/executable, lost history from `clean`, or a prior failed compile can all reduce incremental compiler effectiveness. When compilation is slow, read the exact logs before increasing memory or disabling processors.

If a project uses Kotlin/Groovy/Scala alongside Java, `compileKotlin`, `compileGroovy`, and `compileScala` maintain their own compiler state. Do not take `compileJava UP-TO-DATE` as proof of optimization for the other languages.

## 13. Build Cache, Configuration Cache, and Dependency Cache Differ

### 13.1 Build cache and `FROM-CACHE`

**Up-to-date** relies on output state and prior execution history in the **current workspace**. **Build cache** stores cacheable task outputs keyed by cache key, reusable across builds or agents if a shared cache is configured.

Try local cache:

```bash
./gradlew build --build-cache --console=plain
./gradlew clean
./gradlew build --build-cache --console=plain
```

After `clean`, some tasks **may report `FROM-CACHE`**, not because sources never changed, but because the cache holds matching outputs. Do not promise that every task (`test`/`bootJar`) is cached across all plugins/versions; cacheability and inputs govern actual behavior.

**`clean` does not guarantee a full recompile from scratch** while the build cache is enabled. To separate the two mechanisms, try `--no-build-cache`; even then, local `UP-TO-DATE` can still occur.

### 13.2 Configuration cache

Gradle has initialization, configuration, and execution phases. **Configuration cache** saves the task graph/configuration to avoid re-running configuration when configuration inputs have not changed. It does **not** replace up-to-date checking or the Java incremental compiler.

```bash
./gradlew help --configuration-cache
./gradlew help --configuration-cache
```

With compatible plugins/build logic, the second run can reuse the configuration cache. If a custom task accesses `Project` from a task action in an unsupported way, Gradle may report a configuration cache problem. On Gradle 8.x, use this flag intentionally and verify against your Gradle version's documentation.

### 13.3 Dependency cache

The Gradle dependency cache (such as artifacts/metadata in `GRADLE_USER_HOME/caches/modules-2`) reduces library downloads from Maven repositories. It differs from the task-output build cache and local execution history.

| Mechanism | Scope | Signal |
| --- | --- | --- |
| Up-to-date | Skips task in current workspace | `UP-TO-DATE` |
| Incremental Java compile | When `JavaCompile` runs, compiles affected classes | Compiler diagnostics/`--info` logs |
| Compilation avoidance | Skips compiling consumer modules if upstream ABI is unchanged | Consumer `compileJava UP-TO-DATE` |
| Build cache | Restores outputs of cacheable tasks | `FROM-CACHE` |
| Configuration cache | Skips recalculating configuration/task graph | Configuration cache reused logs |
| Dependency cache | Reuses dependency artifacts/metadata | Dependency resolution/download logs |

`--offline`/`--refresh-dependencies` relate to dependency resolution, not "toggling the Java incremental compiler." Keep targets distinct when troubleshooting.

## 14. Gradle Diagnostic Flags—Not for Indiscriminate Use

### 14.1 `--info --console=plain`

```bash
./gradlew compileJava --info --console=plain
./gradlew processResources --info --console=plain
./gradlew bootJar --info --console=plain
```

Shows why tasks executed or were skipped, inputs, compiler diagnostics, and cleanly comparable logs. Exact messages vary across Gradle versions.

### 14.2 `--rerun-tasks`

```bash
./gradlew compileJava --rerun-tasks --console=plain --info
```

Forces relevant tasks to re-execute for diagnosing suspected stale outputs or bad up-to-date checks. It usually slows builds down rather than improving performance. If a build only works when adding this flag, fix the **task input/output model**.

### 14.3 `--no-build-cache`

```bash
./gradlew build --no-build-cache --console=plain
```

Skips retrieving task results from the build cache. However, `compileJava UP-TO-DATE` can still appear because local up-to-date checking is a separate mechanism.

### 14.4 `clean`

```bash
./gradlew clean build
```

Deletes outputs in `build/` (per project/config), establishing a clean-output baseline; **do not run it on every edit-build cycle** because it destroys incremental history. The build cache may still restore outputs. Use only in workspaces you are allowed to clean; never interfere with a build directory used by another job.

### 14.5 `--dry-run`

```bash
./gradlew build --dry-run
```

Prints the planned task graph without running normal actions. Do **not** use `--dry-run` to conclude `compileJava` will be up-to-date or incremental in a real run; run a normal build to verify outcomes.

### 14.6 `--debug` and Build Scans

`--debug` produces verbose logs that can expose paths/repositories/configuration; use only when needed and sanitize data. Build scans/profiling improve performance visibility, but do not upload internal data to external services without authorization; local `--info` logs are sufficient for this lesson.

## 15. Specific Impact on Spring Boot Tasks

### 15.1 `bootJar` may re-run even when `compileJava` does not

Spring Boot's `bootJar` packages **classes + processed resources + runtime dependencies** into an executable JAR. Accordingly:

- Edit Java source: `compileJava` may run incrementally, and `bootJar` may update.
- Edit `application.properties`: `processResources` changes, `compileJava` can stay up-to-date, and `bootJar` updates.
- Change runtime dependency version: `compileJava` may not change if compile ABI is unchanged, but `bootJar` must package the new nested dependency.
- Edit only test sources: `compileTestJava` and `test` may run, while `bootJar` usually needs no update if main artifact inputs stayed the same.
- Change version/classifier/manifest: archive inputs/naming may change, invalidating packaging.

**Do not apply a wrong fix like `bootJar.outputs.upToDateWhen { true }` to skip packaging on every build**, as it can release a stale JAR. Declare accurate inputs and outputs so Gradle decides properly.

### 15.2 `bootRun` is not `bootJar`

`bootRun` runs the app from compiled classes, resources, and the development runtime classpath; with a web server, it keeps the JVM alive. It does not necessarily produce an executable JAR. An app that runs via `bootRun` does not prove the file in `build/libs` is fresh or contains everything needed for `java -jar`.

If optimizing the coding loop, `classes`/`bootRun` fits well; if verifying a release artifact, you must build `bootJar` and inspect the artifact itself.

### 15.3 `test` has up-to-date status, yet test quality must be preserved

Test task inputs can include test bytecode, runtime classpath, declared JVM args/properties, and fixture files. If tests depend on network/database/clock/randomness without modeling those inputs, caching/up-to-date checks can return results **that do not reflect a fresh run**.

Do not enable caching blindly for integration tests with side effects; instead make them deterministic, isolated, or define a dedicated re-run policy for the integration stage. `test SKIPPED` via `-x test` is not passing unit tests.

### 15.4 Optimizing archive metadata

If a build script injects the current timestamp into a manifest or generated file on every run, archives may be invalidated constantly even when sources have not changed. In release pipelines, consider stable versions, SCM commit IDs, and appropriate reproducible-archive settings. Never emit random outputs just to "prove the build ran."

## 16. Common Errors and Diagnostics

| Symptom | Possible cause | How to investigate |
| --- | --- | --- |
| `compileJava` always runs despite unchanged sources | Classpath/toolchain/plugin/options changed, missing outputs/history | Run `--info` twice in a row, compare inputs |
| `compileJava` runs after a small edit | Normal: source changed so task is out-of-date | Check whether incremental compiler compiled narrowly or in full |
| `compileJava` full recompilation | ABI/constant/processor changed, compiler error, lost state | `--info`, `annotationProcessor`, toolchain |
| `:app:compileJava` runs after editing a body in `:core` | Actual ABI changed, compile classpath or custom inputs affected | Compare public API, dependency graph, `--info` |
| Resource changed, yet Java task stays up-to-date | Resource files do not affect Java compiler | Check `processResources` and `bootJar` |
| Resource `build-info.properties` keeps old version | Expanded value undeclared as input, wrong file filter | Check `inputs.property`, inspect actual output |
| `processResources NO-SOURCE` | No resources in the sourceSet | Check `src/main/resources`, includes/excludes |
| `test SKIPPED` yet CI passes | Tests excluded via `-x test`/`onlyIf` | Inspect CI/task config; never treat `SKIPPED` as `PASS` |
| `test FROM-CACHE` after clean | Build cache stored previous outputs | Check cache settings and test determinism |
| `bootJar` `UP-TO-DATE` when expecting new class | Wrong module edited or file outside sourceSet, missing input | Check task inputs, archive, and `jar tf` |
| `bootJar` runs on every invocation | Timestamp/manifest/property/random version/runtime deps changing | Inspect `--info`, archive config |
| Still `FROM-CACHE` after `clean` | Build cache works independently | Use `--no-build-cache` if isolating behavior |
| `--no-build-cache` still shows `UP-TO-DATE` | Local task history remains valid | Expected behavior, not a bug |
| Custom task produces stale output | Missing `@Input`/`inputs.property` or output declaration | Fix task model, re-run tests |
| Java compile not incremental with annotation processor | Processor lacks isolating/aggregating support or reads external files | `--info`, processor version docs |
| Fresh CI agents recompile a lot | No local history, no shared build cache configured | Evaluate remote cache per policy |
| Broken build cache output | Non-deterministic task/missing inputs or insufficient cache key | Fix task, disable caching on faulty task while investigating |
| Old code persists after editing file | Stale output, wrong task dependency, wrong artifact picked | Check sourceSets, outputs, archives; verify in clean lab |
| Using Gradle 8 while reading newer Gradle 9 docs | Syntax/task/plugin behavior differences | Match docs to your actual Wrapper version |
| Green build with no Java classes | `compileJava NO-SOURCE` from wrong source path | Verify `src/main/java` and module layout |
| Gradle build slow in configuration | Heavy plugins/configuration | Measure config phase separately; evaluate configuration cache |
| Multi-project compile avoidance ineffective | Over-exporting dependencies via `api`, frequent ABI churn | Audit `java-library` boundaries and compile classpath |

### 7-step troubleshooting workflow

1. Identify the exact slow task and its module.
2. Record the command, Gradle Wrapper version, JDK/toolchain, and plugin versions.
3. Run the same task **twice without changing inputs** using `--info --console=plain`.
4. Distinguish `UP-TO-DATE`/`FROM-CACHE`/`SKIPPED`/executed outcomes.
5. If `compileJava` executed, check whether it was incremental or full and why.
6. If `bootJar` executed, identify which class/resource/dependency/manifest input changed.
7. Fix unstable sources or input/output declarations, run tests, and verify the archive before claiming an improvement.

Never start by deleting all cache directories or adding `--rerun-tasks` permanently to CI. Those workarounds destroy optimization benefits without fixing root causes.

## 17. Benchmark: Measuring Three Build Types

| Scenario | Conditions | Observations to record |
| --- | --- | --- |
| First build | Workspace has no outputs; build cache explicitly on/off | Executed tasks, `FROM-CACHE`, duration |
| Rebuild with no changes | Same command/inputs/outputs | Which tasks are `UP-TO-DATE` and total time |
| Edit one Java method body | ABI unchanged | How incrementally `compileJava` ran |
| Edit public API | ABI changed | Which consumers/modules had to compile |
| Edit only a resource | No Java edits | `processResources`/`bootJar`, `compileJava` |
| After `clean` + build cache | Outputs deleted, cache intact | Which tasks are `FROM-CACHE` |
| Change build-time version | `appVersion` is a declared input | Whether output properties and archive updated |

**There is no fixed second count across all machines.** Measure at least several runs under identical conditions, accounting for daemon/JVM warm-up, dependency downloads, filesystem cache, config cache, and CPU load. If using `--profile` or profiling tools, verify availability on your current Gradle version.

Only count a build as "fast" when **outputs are accurate, required tests ran or were validly verified, and the final artifact reflects current sources/dependencies**. Skipping tests or reusing a stale JAR may be fast, but fails requirements.

## 18. Practice Exercises with Verifiable Outcomes

### A. Prove `UP-TO-DATE`

Set up the project from Section 5 and run `./gradlew build --info` twice without edits. Record task outcomes and explain why the compiler did not execute on the second run if `compileJava` was up-to-date.

### B. Prove incremental compilation

Edit only the body of `Calculator.add`, run `compileJava --info`, and observe the task running with narrow compilation scope. Try changing the signature on a lab branch, comparing logs and compile scope. Revert afterward.

### C. Separate resource and class compilation

Edit only `build-info.properties` and run `classes` and `bootJar`. Use `jar tf` to check `BOOT-INF/classes/build-info.properties`. Explain why a resource change does not force Java recompilation.

### D. Declare inputs properly

Use `inputs.property('appVersion', appVersionValue)` with `filesMatching/expand`. Change `version` on an experimental branch and verify the output updates from `0.0.1-SNAPSHOT` to `0.0.2-SNAPSHOT`. Explain why you should not filter all of `application.properties` containing Spring runtime placeholders.

### E. Compare cache vs. up-to-date

Enable `--build-cache`, build, clean, and rebuild. Record which tasks report `FROM-CACHE` if any. Use `--no-build-cache` on another run and explain why `UP-TO-DATE` can still appear.

### F. Multi-project compile avoidance

Set up `:core`/`:app` from Section 11. Edit the body in `Formatter` while preserving ABI, and observe `:core:compileJava`, `:app:compileJava`, and `:app:bootJar`. Change the public method signature on a copy to see the wider invalidation scope.

### G. Critique a broken fix

A teammate writes:

```groovy
tasks.named('bootJar') {
    outputs.upToDateWhen { true }
}
```

and says "I optimized it so it doesn't rebuild the JAR anymore." Explain why this can produce a stale artifact and is not legitimate incremental behavior. Whenever resources or compiled classes change, the packaging task must detect the change and update.

### H. Write a reproducible report

Record at minimum:

```text
Gradle Wrapper version:
JDK/toolchain version:
Spring Boot plugin version:
Task command:
Run 1 outcome / duration:
Run 2 outcome / duration:
One source change made:
Which file was edited:
compileJava executed or UP-TO-DATE:
If executed, incremental or full and evidence:
processResources outcome:
bootJar outcome:
Artifact/build output contents after change:
Lesson learned about cache/inputs-outputs:
```

This is a **template for learners to record real evidence**, not a completed run report. Passing criteria: distinguishing **skipping an entire task** from **incremental compilation within a task**, understanding ABI and compilation avoidance, distinguishing `FROM-CACHE`, knowing how to use `--info`, and verifying the Spring Boot output updates accurately.

## 19. Official References

- Gradle – Incremental Build (task inputs/outputs, fingerprints, up-to-date checks): https://docs.gradle.org/current/userguide/incremental_build.html
- Gradle – Java Plugin (Incremental Java compilation, compilation avoidance, and annotation processing): https://docs.gradle.org/current/userguide/java_plugin.html
- Gradle – Build Cache: https://docs.gradle.org/current/userguide/build_cache.html
- Gradle – Configuration Cache: https://docs.gradle.org/current/userguide/configuration_cache.html
- Gradle – Advanced Tasks / InputChanges: https://docs.gradle.org/current/userguide/custom_tasks.html
- Gradle – Gradle Optimizations & Task Outcome Labels: https://docs.gradle.org/current/userguide/gradle_optimizations.html
- Gradle – Improve the Performance of Gradle Builds: https://docs.gradle.org/current/userguide/performance.html
- Gradle – Java Library Plugin, `api` vs `implementation`: https://docs.gradle.org/current/userguide/java_library_plugin.html
- Spring Boot 3.3 – Gradle Plugin, Packaging Executable Archives (`bootJar`): https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot 3.3 – Gradle Plugin, Running Your Application (`bootRun`): https://docs.spring.io/spring-boot/3.3/gradle-plugin/running.html

**Remember:** `UP-TO-DATE` = **task skipped**; incremental Java compilation = **task `compileJava` runs, potentially compiling only affected classes**; compilation avoidance = **skipping downstream compilation when upstream ABI is unchanged**; `FROM-CACHE` = **restoring outputs from build cache**. For Spring Boot, check `compileJava`/`processResources`/`test`/`bootJar` individually and always verify the executable artifact contains the right changes rather than sacrificing correctness for a nice cache label.
