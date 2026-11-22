# Incremental Compilation, Changed Dependencies, and When a Clean Build Is Needed in Java

## 1. Objectives and Context

In a Java project, every edit to a line of source code does not necessarily require deleting all compilation artifacts and re-running every task. Build tools can determine which parts are actually affected, skip tasks whose inputs have not changed, or recompile only the necessary classes. Understanding this mechanism helps shorten development time, troubleshoot “still running old code” bugs, and design reliable CI pipelines.

After this lesson, you should be able to distinguish:

- **Incremental build:** skips tasks whose inputs/outputs are still valid and processes only changed parts.
- **Incremental compilation:** within a single compilation task, recompiles only the affected subset of sources when supported by the compiler/build tool.
- **Compilation avoidance:** skips compiling a dependent module when the input library's API/ABI has not changed.
- **Build cache:** reuses outputs previously produced with equivalent inputs; caching does not mean compiling only a few files.
- **Clean build:** deletes build-managed outputs and recreates them; useful for eliminating stale state, yet time-consuming and cannot fix faulty configuration.

These optimizations can work together, yet they have different scopes. Both conclusions “a file was edited so every module must recompile” and “the build succeeded so every class is fresh” can be false.

## 2. Mental Model: What Invalidates a Compilation Result?

A build can be viewed as a transformation pipeline:

```text
Java source + generated source + compile classpath
       + compiler/JDK + options + annotation processors
                           |
                           v
                     JavaCompile
                           |
                           v
                    *.class / outputs
                           |
                           v
                  jar / tests / packaging
```

To know whether work needs to re-run, the build tool compares **declared inputs**, output state, and dependency rules. Important inputs can include:

1. Added, modified, or deleted Java source files.
2. `.class` files or JARs on the **compile classpath** and the consumed API/ABI surface.
3. JDK/toolchain version, `--release`, `-parameters`, warning flags, or compilation configuration affecting bytecode.
4. Annotation processors, their configurations, and resources they read; code generated during the build.
5. Outputs that were deleted, modified outside the build, or overwritten by another task.
6. Relationships between tasks/modules; for instance, `:app:compileJava` needs the right artifacts from `:lib:compileJava`.

A system that only checks “is the .java file modification date newer than .class?” will miss cases where a public method changes its signature while a file calling it does not change. A reliable system must track dependencies and invalidate the exact affected outputs.

**Two levels of dependency must be separated:**

- **Source/class dependency:** `OrderService` calls `Pricing.calculate()`; changing `calculate`'s signature may require `OrderService` to be recompiled.
- **Task/module dependency:** `:app:compileJava` consumes classes from `:core`; the app task might not need to run when the library only changes internal calculation logic while keeping the ABI intact.

How precise dependency information is depends on the tool, version, annotation processor type, and configuration. Not every change recompiles strictly a single file.

## 3. API, ABI, and Propagation Scope

**API** is the interface other source code can use: classes, methods, constructors, fields, and corresponding types/accessibility. **ABI (Application Binary Interface)** here is the part of the interface in the class file that affects how compiled code links against and interacts with that class. Gradle analyzes ABI on the compile classpath to decide whether to avoid downstream compilation.

| Change in library | Typical impact |
|---|---|
| Changing only a method body, signature unchanged | Source containing the change must compile; consuming modules usually avoid compilation because ABI is unchanged |
| Changing parameter names or types, return type, public visibility | ABI changes; corresponding dependent sources may need recompilation and may report errors |
| Adding/removing public methods, superclass, interface | May change call resolution or type contracts; classes using the API need evaluation |
| Changing `private` implementation | Usually does not affect ABI of consuming modules |
| Changing value of a compile-time constant `public static final int` | Risk of **constant inlining** in already-compiled classes; must ensure consuming code is properly refreshed |
| Changing annotations or metadata used by a processor | May require code regeneration or broader recompilation, even when ordinary Java signatures do not change |
| Changing dependencies/compiler flags | May invalidate tasks; scope depends on tool tracking capability |
| Deleting/renaming a class | Old outputs must be removed and referencing classes refreshed; if old classes remain, “ghost” behavior can occur |

Do not confuse “ABI unchanged” with “the application runs identically”. For example, changing a calculation inside a method alters runtime results even though the module calling it does not have to recompile. That module will load the new implementation from the classpath at runtime.

**Compile-time constants are an exception to watch out for.** Given the declaration:

```java
package example.api;

public final class Limits {
    private Limits() {}

    public static final int MAX_RETRIES = 3;
}
```

Another class using `Limits.MAX_RETRIES` may have the value `3` copied directly into its bytecode by `javac`. If changed to `5` while only recompiling `Limits.class`, old consumer bytecode may still hold `3`. This is why the compilation tracker must understand constant dependencies; do not arbitrarily compile individual files manually.

## 4. Java 17+ Example: Why Must Dependent Classes Be Recompiled?

Create the directory tree:

```text
src/
└── main/
    └── java/
        └── example/
            ├── api/
            │   └── Price.java
            └── app/
                └── Main.java
```

**File `src/main/java/example/api/Price.java`:**

```java
package example.api;

public final class Price {
    private Price() {}

    public static int total(int unitPrice, int quantity) {
        return unitPrice * quantity;
    }
}
```

**File `src/main/java/example/app/Main.java`:**

```java
package example.app;

import example.api.Price;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Price.total(20, 3));
    }
}
```

Create directory `out` (Unix/macOS: `mkdir -p out`; PowerShell: `New-Item -ItemType Directory -Force out`) and run in the project directory:

```bash
javac -d out src/main/java/example/api/Price.java src/main/java/example/app/Main.java
java -cp out example.app.Main
```

Output:

```text
60
```

Now change only the **return type** of `Price.total` to `long`, keeping the parameters and method body:

```java
public static long total(int unitPrice, int quantity) {
    return (long) unitPrice * quantity;
}
```

After editing `Price.java`, intentionally compile only the API-providing class while the old `Main.class` remains:

```bash
javac -cp out -d out src/main/java/example/api/Price.java
java -cp out example.app.Main
```

The second run will fail with **`java.lang.NoSuchMethodError`** because the old `Main.class` still calls a method with a descriptor returning `int`, whereas the new `Price.class` only provides a descriptor returning `long`. The exact error message may vary across JVM versions, yet the essence is linking against an old binary signature.

Recompile the consumer and run:

```bash
javac -cp out -d out src/main/java/example/app/Main.java
java -cp out example.app.Main
```

The output is again:

```text
60
```

The experiment demonstrates two distinct things: *where source code changed* and *which classes need updating due to dependencies*. Modern build tools are designed to compute this relationship automatically. `javac` invoked to compile specified files as above does not by itself provide a cross-run task/build-graph tracking system like Gradle.

**Note:** `NoSuchMethodError`, `NoSuchFieldError`, and `ClassNotFoundException` can also come from JAR version conflicts or runtime classpaths; do not automatically blame every such error on incremental compilation.

## 5. How Does Gradle Track Changes?

With the Java plugin, two related yet independent mechanisms:

**(A) Task up-to-date / incremental build.** If declared inputs and outputs of `:compileJava` match the previous run, Gradle can report `UP-TO-DATE` and skip running the task. If valid outputs already exist in the build cache, `FROM-CACHE` may appear. If the task runs, it may still compile only an affected subset of classes.

**(B) Incremental Java compilation and compile avoidance.** `JavaCompile` can detect changed source classes and affected dependencies. Between modules, Gradle can avoid compiling consumers if library changes do not affect the ABI. Incremental compilation is enabled by default in modern Gradle versions.

A simple configuration for Java 17 and above using a Java toolchain:

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

This file is `build.gradle`. Commands run with Gradle Wrapper from the project root (Unix/macOS; on Windows use `gradlew.bat`):

```bash
./gradlew compileJava --console=verbose
./gradlew compileJava --console=verbose
```

After a successful first build, the second run *typically* shows `:compileJava UP-TO-DATE` if no relevant inputs/outputs changed. Do not interpret a re-running task as always meaning “full compilation”; inspect `--info` to see the invalidation reason and actual compilation activity.

Multi-module project example:

```text
:core  (Pricing.java)
   |
   v
:app   (OrderApplication.java uses core)
```

- If only the body of `Pricing.calculate()` is edited: `:core:compileJava` needs to update its output; `:app:compileJava` can usually avoid running because core's ABI remains compatible.
- If an API signature called by app changes: app needs to be checked and may have to recompile or fail because the API is no longer compatible.
- If a source unrelated to app changes, recompilation within the module still depends on class dependency analysis and processors.

Gradle dependency declaration example:

```groovy
dependencies {
    implementation project(':core')
}
```

This declaration goes inside `app/build.gradle` of a multi-project build that declared `:core` and `:app` in settings. This is an illustrative configuration snippet, not a standalone runnable project in one line.

### 5.1. Annotation Processing and Generated Code

Tools like MapStruct, Lombok, or custom processors can generate Java sources/classes from multiple inputs. Accuracy depends on the build tool's ability to see all inputs of the processor.

In Gradle, processor dependencies should be placed on a separate configuration:

```groovy
dependencies {
    annotationProcessor 'org.example:sample-processor:1.0'
}
```

The line above only illustrates **configuration placement**: coordinate `org.example:sample-processor:1.0` is an example, not an artifact to download and run. Real processors must use existing coordinates.

Gradle distinguishes **isolating** processors (outputs tied to individual inputs), **aggregating** processors (outputs aggregating multiple inputs), and processors that do not support incremental execution. If a processor does not satisfy the incremental contract, a small change can force broader recompilation. When a processor reads YAML/JSON/resource files or environment variables that the task did not declare as inputs, an “up-to-date” result can be wrong. That is a dependency/input declaration bug, not a long-term reason to always run `clean`.

### 5.2. Easily Confused Statuses

| Indicator from Gradle | Actual meaning |
|---|---|
| `UP-TO-DATE` | Task did not run because current input and output states are already valid |
| `FROM-CACHE` | Output was restored from an appropriate cache |
| Task runs normally | Changes occurred or optimization did not apply; cannot yet conclude it compiled every source |
| `NO-SOURCE` | Task has no input sources to process |
| `SKIPPED` | Task did not execute due to skip condition/setting; not equivalent to outputs having been verified as up-to-date |

When analyzing failures, inspect specific tasks (`compileJava`, `compileTestJava`, `processResources`, `jar`, code generation tasks) instead of treating the overall “BUILD SUCCESSFUL” text as proof that every source class was just compiled.

## 6. Maven: Same Goal, Decision Mechanisms May Differ

Maven also has change-detection mechanisms via the Maven Compiler Plugin and lifecycle, yet **you should not assume it has the same ABI tracking, compile avoidance, and recompilation scope algorithms as Gradle**. Capabilities depend on plugin version and configuration.

With Maven Compiler Plugin 3.x, `useIncrementalCompilation=true` is the default for the javac compiler: the plugin inspects changes in sources and dependency JARs; when needed, it may recompile all sources in the module. The `false` option relies more on newer file timestamps and risks missing consumers when APIs change. The Maven Compiler Plugin 4.x line introduces more granular `incrementalCompilation` strategy options. Therefore, to draw accurate conclusions you must check **the exact plugin version in use**.

Java 17 configuration example with Maven Compiler Plugin 3.x:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

This is a `pom.xml` fragment, not full POM content. Common commands:

```bash
mvn compile
mvn test
mvn clean verify
```

`mvn compile` executes phases up to `compile`; `mvn test` runs further through testing; `mvn clean verify` executes the clean lifecycle followed by the default lifecycle up to verify. In multi-module projects, the Maven reactor orders modules by dependencies; recompilation scope within each module is managed by the compiler plugin.

**Checkpoint:** If module A's API changed yet module B still runs old bytecode, check whether B was actually built against the newly created A, which modules the Maven reactor is selecting, whether `-am` was used when using `-pl`, and whether the classpath contains an old JAR in the local repository.

## 7. When Is an Incremental Build Enough?

In normal development workflows, first **rebuild the relevant target** and let the tool manage outputs itself:

- Editing a method body, fixing logic bugs, adding tests, updating resources with properly declared inputs: running the corresponding task is normally sufficient.
- Changing a public API in a multi-module build: run a build including consuming modules and relevant tests; no need to delete every output by default.
- Changing dependency version/JDK/compiler options: standard build tools can detect and invalidate appropriately if configured properly; verify logs and outputs.
- Changing an annotation processor or generated source: re-run the related codegen/compile tasks and check declared inputs.

Normal builds after an API change still have to compile required consumers; *accurate* incremental building means selecting the exact affected set, not always compiling as little as possible regardless of safety.

## 8. When Is a Clean Build Needed?

`clean` normally deletes output directories managed by the build tool (`build/` for Gradle, `target/` for Maven). It is not a “wipe the entire machine” command: dependency caches, IDE caches, Gradle user home, Maven local repository, and published artifacts are generally not deleted by default `clean`.

Prioritize clean when there is **credible evidence that output state has lost consistency**, such as:

1. **Classes generated from deleted/renamed sources remain in output** and are mistakenly packaged/executed; code generators or custom tasks failed to clean stale outputs properly.
2. **Multiple build/plugin/toolchain versions or custom tasks wrote directly to the same output directory**, making output history untrustworthy.
3. **An incremental build differs from a build from clean state** (e.g., on the same commit the JAR artifact or test results differ); clean is needed to confirm and isolate the cause.
4. **Major structural migrations** (changing source sets, artifact layouts, processors, or generators) where stale-output cleanup contracts are not yet guaranteed.
5. **Creating releases or CI verification needing to prove buildability from scratch**, according to project policy.

Gradle command:

```bash
./gradlew clean build
```

Maven command:

```bash
mvn clean verify
```

After clean, compilation is redone from an empty local output state; **Gradle build cache** separately may still reuse valid outputs if enabled. If verification genuinely requires tasks to execute without using the build cache, you can try:

```bash
./gradlew clean build --no-build-cache
```

Depending on investigation goals, `--rerun-tasks` forces Gradle tasks to re-execute even when normal up-to-date checks would skip them. These flags are for **intentional diagnosis**, and should not be configured as a habit for every build.

### Cases Where Clean Does Not Solve the Root Cause

- Missing `inputs` or `outputs` in a custom task: clean may hide the bug once, yet the next build can still use wrong outputs.
- Wrong dependency version or duplicate classes on the classpath: must fix dependency resolution, not just delete `build/`.
- App is running an old process/JAR: must restart the right artifact and verify runtime classpath.
- Differing JDK configurations across terminal, IDE, and CI: must standardize toolchain/`--release` and inspect the runtime environment.
- Unstable annotation processor or non-deterministic generated output: must fix the processor and its input/output contract.

Therefore “just run `clean` to fix errors” is not a reliable build strategy; it slows builds down and masks change-tracking configuration bugs.

## 9. Distinguishing Refresh Levels for Quick Diagnosis

| Goal | Reasonable choice | What gets checked |
|---|---|---|
| Edited a Java file and want to re-run the program | `./gradlew classes` or `mvn compile` | Build updates necessary outputs |
| Checking why a task did not run | `./gradlew compileJava --info` | Task up-to-date/invalidation reason and compiler activity |
| Checking tests after an API change | `./gradlew test` or `mvn test` | Compiles main/test and runs corresponding tests |
| Suspecting build cache gives unexpected output | `./gradlew build --no-build-cache` | Neither reads nor writes build cache in this check run |
| Suspecting a task was mistakenly skipped | `./gradlew build --rerun-tasks` | Forces task execution instead of relying on up-to-date state |
| Suspecting stale classes/resources remain | `./gradlew clean build` or `mvn clean verify` | Regenerates outputs after deleting project outputs |
| Verifying release from clean state | Clean build in an isolated CI environment | Reproducibility from locked/controlled code and dependencies |

Commands are Unix/macOS examples with Gradle Wrapper; Windows uses `gradlew.bat`, and Maven requires an installation/Wrapper accordingly. Do not reflexively prepend `clean` to every command.

## 10. Investigation Workflow When Build Results Look Wrong

**Step 1 — Confirm the right artifact and environment.** Check whether you are running outputs from `build/classes`, `target/classes`, a freshly built JAR, or a JAR from a repository. Check `java -version`, compiler toolchain, current module/branch, and runtime classpath.

**Step 2 — Identify which files, inputs, or APIs changed.** Ask: is the change only in a method body or also in the API? Are there compile-time constants, annotations, generators, dependency JARs, compiler options, or resources involved? Note the tasks consuming those inputs.

**Step 3 — Observe a non-clean build.** With Gradle:

```bash
./gradlew compileJava --info
./gradlew test --console=verbose
```

In multi-project builds, use namespaced task paths like `:core:compileJava` or `:app:test`. Inspect task statuses `UP-TO-DATE`, `FROM-CACHE`, recompilation, and reasons. With Maven:

```bash
mvn -X compile
```

Debug logs can be large; find the Maven Compiler Plugin section and related dependencies/classpaths. Read logs according to the exact tool version in use, without extrapolating from a single keyword.

**Step 4 — Try the smallest isolation.** If suspecting cache, disable build cache for one run; if suspecting up-to-date, intentionally re-run the task; if suspecting stale generated classes, inspect the exact task's output directory. Do not delete the entire Maven repository or Gradle user cache without supporting evidence.

**Step 5 — Compare against a clean build.** Only when needed, run a clean build and compare errors, JAR contents, tests, and classpaths. If clean fixes the issue while incremental remains wrong, look for **undeclared inputs/outputs**, uncleaned old classes, non-incremental processors, or missing task dependencies.

**Step 6 — Fix the root cause and add meaningful verification.** For instance, a source-generating task must declare the configuration file it reads as input, the generated output directory as output, and link the compile task to depend on the source-generating task. A test that changes an API and rebuilds consumers can catch real regressions.

## 11. Common Misconceptions and Errors

**“Only edited implementation, so no build is needed.”** False: the new implementation still must be compiled and packaged. What is typically *avoided* is recompiling consumers whose dependency ABI did not change.

**“Every public change makes the whole repo compile.”** Not necessarily: only dependent affected parts need evaluation; exact granularity depends on the build tool, processors, and configuration. Some compilers/plugins may choose to recompile an entire module for safety.

**“`UP-TO-DATE` means the new code is definitely correct.”** It only means the tool considers the task valid per declared inputs/outputs. Omitted inputs can cause false conclusions.

**“`clean` also deletes the dependency cache.”** Normal clean clears project outputs, not the entire Maven/Gradle cache in the user directory.

**“Checking timestamps alone is enough.”** Timestamps do not understand the full dependency graph, ABI, constants, generated outputs, compiler flags, or classpaths.

**“Rebuilding `lib` is enough after changing an API signature.”** Consumers compiled against the old descriptor must also be updated; the `Price` and `Main` experiment demonstrates the linkage risk.

**“Maven and Gradle have identical incremental compilation.”** Algorithms/scopes differ depending on plugin/version. Verify actual behavior instead of inferring from feature names.

## 12. Self-Check Exercises

**Scenario A.** In module `:core`, only change `return price * quantity;` to `return Math.multiplyExact(price, quantity);`; the method signature is unchanged. What should happen?

*Answer hint:* Core needs to recompile the affected portion; app consumer may have compilation avoided by Gradle because the ABI did not change. Runtime behavior can change because `Math.multiplyExact` throws `ArithmeticException` on overflow.

**Scenario B.** Change `public static int total(int, int)` to `public static long total(int, int)`, then compile only the defining file. Why can the old app throw `NoSuchMethodError`?

*Answer hint:* The return type is part of the JVM method descriptor. Consumer bytecode still links to descriptor `(II)I`, while the new provider has `(II)J`. Dependent consumers of the changed API must be recompiled.

**Scenario C.** Running `clean build` passes tests; the next incremental build fails when editing YAML for a code generator. What should be done?

*Answer hint:* Check whether the YAML is declared as an input to the generation/compile task, whether outputs are declared and properly removed when inputs change, and whether task dependencies are wired correctly. Fix the build contract; clean is only a test to reveal the discrepancy.

**Scenario D.** Java compilation reports `UP-TO-DATE`, yet the application still runs old logic. What are three places to check?

*Answer hint:* (1) Whether you are running the new class/JAR or an old process; (2) whether the modified source sits in the right source set/module/task input; (3) whether the runtime classpath has duplicate JARs/classes or an old dependency version.

## 13. Checklist for Applying in Real Projects

- Clearly identify source sets, tasks, modules, and compile/runtime classpaths.
- Use Java toolchains/`--release` consistently; lock compatible versions of build tools, plugins, and dependencies.
- Declare exact inputs/outputs for custom tasks and code generators; separate the annotation processor path.
- Verify that API changes trigger compiling/testing of affected consumers.
- Use task logs to distinguish up-to-date, cache hit, incremental compilation, and compilation avoidance.
- Only clean when verifying clean state or investigating suspected stale outputs; then fix the root cause if incremental builds are broken.
- For CI and releases, ensure builds are reproducible from a controlled environment, even when local builds leverage incremental execution and caching.

## Official Documentation for Further Reading

- [Gradle — The Java Plugin: incremental compilation, compilation avoidance, annotation processing](https://docs.gradle.org/current/userguide/java_plugin.html)
- [Gradle — Incremental Builds](https://docs.gradle.org/current/userguide/incremental_builds.html)
- [Gradle — Build Cache Concepts](https://docs.gradle.org/current/userguide/build_cache_concepts.html)
- [Apache Maven Compiler Plugin 3.x — compile goal](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html)
- [Apache Maven Compiler Plugin 4.x — incrementalCompilation](https://maven.apache.org/plugins/maven-compiler-plugin-4.x/compile-mojo.html)

Gradle/Maven documentation may update across versions; when diagnosing a specific system, prioritize documentation matching the exact build tool and plugin versions of the project itself.