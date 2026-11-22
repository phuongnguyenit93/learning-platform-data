# Source Sets in Gradle

A **source set** is a logical group of source files and resources that Gradle processes as a build unit. For Java, a source set defines the directories containing source code and resources, the classpath used for compilation, the classpath used at runtime, and the output directories containing compiled classes and processed resources.

Source sets help separate parts of code that have different purposes or dependencies. A Java project typically has a `main` source set for production code and a `test` source set for unit tests. When you need integration tests, generated code, benchmarks, or an independent group of sources with its own classpath, you can create additional source sets such as `integrationTest`, `benchmark`, or `codegen`.

In Gradle, a source set is more than just a directory name. When the Java Plugin creates a source set, Gradle also creates corresponding dependency configurations and compilation/resource-processing tasks. As a result, a single project can compile multiple groups of sources with separate classpaths and outputs.

## 1. What problem do source sets solve?

A Java project often contains several kinds of source code:

- Application or library code packaged for release.
- Fast-running unit tests, typically testing a single class or a small group of classes.
- Integration tests that need to connect to a database, HTTP service, message broker, or multiple components together.
- Functional tests or acceptance tests running system-level scenarios.
- Benchmarks that require separate dependencies and execution settings.
- Sources generated from schemas, protocol definitions, or annotation processors.
- Build helper code or internal tools that should not go into the production artifact.

If everything is placed into `src/main/java`, test dependencies can leak into the production classpath, test code can be packaged into the JAR, and the build becomes hard to control. If you simply create arbitrary directories without declaring them to Gradle, the compiler may not see those files.

Source sets establish clear boundaries between source groups. Each group can have its own source roots, resource roots, dependency configurations, compile tasks, and outputs.

## 2. What components make up a source set?

A Java source set has the following main components:

| Component | Meaning |
|---|---|
| `java` | Java source files to be compiled |
| `resources` | Resource files copied/processed into the output |
| `allJava` | All Java sources of the source set |
| `allSource` | All sources and resources |
| `compileClasspath` | Classpath used during compilation |
| `runtimeClasspath` | Classpath used at runtime |
| `output` | Output directories, including compiled classes and processed resources |
| `name` | Name of the source set |

For example, a source set named `integrationTest` might have:

- Source root: `src/integrationTest/java`.
- Resource root: `src/integrationTest/resources`.
- Compile classpath: `main` output and dependencies for integration tests.
- Runtime classpath: compiled classes, resources, and dependencies needed when running integration tests.
- Output: separate classes and resources in the `build` directory.

The sources and resources of a source set can reside in multiple different directories. Not all files are required to share a single root.

## 3. Default source sets of the Java Plugin

When applying the Java Plugin or Application Plugin, Gradle creates two source sets by default:

| Source set | Role | Default source | Default resources |
|---|---|---|---|
| `main` | Production code | `src/main/java` | `src/main/resources` |
| `test` | Test code | `src/test/java` | `src/test/resources` |

Common project structure:

```text
source-set-demo/
├── settings.gradle.kts
├── build.gradle.kts
└── src/
    ├── main/
    │   ├── java/
    │   └── resources/
    └── test/
        ├── java/
        └── resources/
```

`main` is a special source set: Gradle shortens its task and configuration names, using `compileJava`, `processResources`, `classes`, `implementation`, and `runtimeOnly` instead of `compileMainJava`, `processMainResources`, or `mainImplementation`.

`test` has its own tasks and configurations such as `compileTestJava`, `processTestResources`, `testClasses`, `testImplementation`, and `testRuntimeOnly`.

The Java Plugin automatically wires the `test` task into the `check` lifecycle task. The `jar` task packages the `main` output and does not automatically include sources or classes from other source sets in the production JAR.

## 4. Tasks created for each source set

When you create a custom source set named `integrationTest`, the Java Plugin creates tasks named after the source set:

| Task | Purpose |
|---|---|
| `compileIntegrationTestJava` | Compiles the Java sources of the source set |
| `processIntegrationTestResources` | Copies/processes resources |
| `integrationTestClasses` | Prepares class and resource outputs |
| `integrationTestImplementation` | Configuration for declaring compile/runtime dependencies |
| `integrationTestCompileOnly` | Dependencies needed only at compile time |
| `integrationTestRuntimeOnly` | Dependencies needed only at runtime |
| `integrationTestAnnotationProcessor` | Annotation processors for the source set |

The compile task name follows the pattern `compileSourceSetJava`; the resource-processing task is `processSourceSetResources`; the task that assembles classes and resources is `sourceSetClasses`.

A source set automatically creates compilation tasks and dependency configurations, but **does not automatically create a `Test` task to execute test cases**. If a source set contains integration tests, you must register a `Test` task and configure the appropriate test class directories and runtime classpath.

## 5. Compile classpath and runtime classpath

The two classpaths serve different purposes:

**Compile classpath**

Contains the classes and dependencies the compiler needs to check types, methods, and symbols when compiling sources. For example, integration tests need to see production classes to call application APIs.

**Runtime classpath**

Contains the classes and dependencies required when the JVM executes the program or tests. It typically includes the source set's output along with runtime dependencies.

The `main` source set has a compile classpath based on production configurations. The `test` source set has its own compile/runtime classpath, configured so tests can use production outputs and test dependencies.

For a custom source set, if tests need to call classes from `main`, you must add `sourceSets.main.output` to the compile classpath and runtime classpath of that source set. Without this, integration tests may fail with missing production class errors at compile time or runtime.

Do not overwrite the entire default classpath if you only need to append to it. Use `+=` to add outputs or file collections to the existing classpath.

## 6. Dependency configurations per source set

The Java Plugin creates configurations named after each source set. For `integrationTest`, some important configurations are:

| Configuration | Used when |
|---|---|
| `integrationTestImplementation` | Dependencies needed for both compiling and running integration tests |
| `integrationTestCompileOnly` | Dependencies needed only for compilation |
| `integrationTestRuntimeOnly` | Dependencies needed only when running tests |
| `integrationTestAnnotationProcessor` | Annotation processors run when compiling the source set |
| `integrationTestCompileClasspath` | Resolved classpath for the compiler |
| `integrationTestRuntimeClasspath` | Resolved classpath for execution |

For the `main` source set, common configurations are `implementation`, `compileOnly`, `runtimeOnly`, and `annotationProcessor`. For `test`, common configurations are `testImplementation`, `testCompileOnly`, `testRuntimeOnly`, and `testAnnotationProcessor`.

Distinguish between configurations used to declare dependencies and the resolved classpaths used by tasks. For example, `integrationTestImplementation` is where dependencies are declared; `integrationTestCompileClasspath` is the file collection used when the compiler runs.

If integration tests need the same dependencies as production code and the test framework, you can configure `integrationTestImplementation` to extend from `implementation` and `testImplementation`; `integrationTestRuntimeOnly` can extend from `runtimeOnly` and `testRuntimeOnly`.

Create the source set before accessing the configurations it generates. Gradle creates these configurations automatically; do not manually create a configuration with the same name for a different role.

## 7. Creating a custom source set with Kotlin DSL

Example of creating an `integrationTest` source set:

```kotlin
plugins {
    java
}

sourceSets {
    create("integrationTest") {
        compileClasspath += sourceSets.main.get().output
        runtimeClasspath += sourceSets.main.get().output
    }
}
```

This configuration snippet:

1. Creates a source set named `integrationTest`.
2. Tells Gradle to look for Java sources in `src/integrationTest/java` by default.
3. Tells Gradle to look for resources in `src/integrationTest/resources` by default.
4. Adds the `main` output to the compile classpath and runtime classpath.
5. Creates the corresponding compile/resource/classes tasks and dependency configurations.

You can access the source set after creating it:

```kotlin
val integrationSources = sourceSets["integrationTest"]

println(integrationSources.name)
println(integrationSources.java.srcDirs)
println(integrationSources.resources.srcDirs)
```

You do not need to manually declare `compileIntegrationTestJava` or `processIntegrationTestResources`; the Java Plugin creates those tasks based on the source set.

## 8. Creating a custom source set with Groovy DSL

If the project uses `build.gradle`, the equivalent configuration is:

```groovy
plugins {
    id 'java'
}

sourceSets {
    integrationTest {
        compileClasspath += sourceSets.main.output
        runtimeClasspath += sourceSets.main.output
    }
}
```

Gradle creates tasks and configurations using the same conventions. The main difference is DSL syntax; the `SourceSet` model and task graph remain unchanged.

Do not mix Kotlin DSL and Groovy DSL syntax in the same build script. The file name determines the DSL: `build.gradle.kts` uses Kotlin DSL, while `build.gradle` uses Groovy DSL.

## 9. Adding dependencies to a custom source set

After creating the source set, you can declare dependencies for it:

```kotlin
configurations["integrationTestImplementation"].extendsFrom(
    configurations["implementation"],
    configurations["testImplementation"]
)

configurations["integrationTestRuntimeOnly"].extendsFrom(
    configurations["runtimeOnly"],
    configurations["testRuntimeOnly"]
)

dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.12.2")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher:1.12.2")
}
```

In this example:

- `integrationTestImplementation` inherits production and test framework dependencies.
- `integrationTestRuntimeOnly` inherits production and test runtime dependencies.
- The JUnit Jupiter API/engine is used for test sources.
- The JUnit Platform launcher is added to the test runtime.

Declare dependencies after the source set has been created so that the `integrationTestImplementation` and `integrationTestRuntimeOnly` configurations exist.

Integration tests do not necessarily have to inherit all unit test dependencies. If integration tests use their own framework or clients, declare only the dependencies needed for that source set.

## 10. Creating a task to run integration tests

A source set only describes sources, classpaths, and outputs. To run test classes, create a task of type `Test`:

```kotlin
val integrationTest = tasks.register<Test>("integrationTest") {
    description = "Runs integration tests."
    group = "verification"

    testClassesDirs = sourceSets["integrationTest"].output.classesDirs
    classpath = sourceSets["integrationTest"].runtimeClasspath

    shouldRunAfter("test")
    useJUnitPlatform()
}

tasks.named("check") {
    dependsOn(integrationTest)
}
```

Two key properties:

- `testClassesDirs`: directories containing the compiled test classes.
- `classpath`: classpath used when running tests, including test classes, production output, and runtime dependencies.

`shouldRunAfter("test")` requests that integration tests run after unit tests when both tasks are selected. This is a soft ordering constraint; Gradle still retains the ability to optimize the task graph and execute in parallel when appropriate.

`dependsOn(integrationTest)` attaches integration tests to the `check` lifecycle. As a result, `./gradlew check` will run both unit tests and integration tests.

If you do not attach the task to `check`, the default `check` command will not know to run the newly created integration test task.

## 11. Complete Java 17+ example with main, test, and integrationTest

This example uses Gradle Kotlin DSL, a Java 17 toolchain, and JUnit 5. The project has the default `main` and `test` source sets along with a custom `integrationTest` source set.

Directory structure:

```text
source-set-demo/
├── settings.gradle.kts
├── build.gradle.kts
└── src/
    ├── main/
    │   └── java/
    │       └── com/example/App.java
    ├── test/
    │   └── java/
    │       └── com/example/AppTest.java
    └── integrationTest/
        └── java/
            └── com/example/AppIntegrationTest.java
```

File `settings.gradle.kts`:

```kotlin
rootProject.name = "source-set-demo"
```

File `build.gradle.kts`:

```kotlin
plugins {
    application
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

application {
    mainClass.set("com.example.App")
}

sourceSets {
    create("integrationTest") {
        compileClasspath += sourceSets.main.get().output
        runtimeClasspath += sourceSets.main.get().output
    }
}

configurations["integrationTestImplementation"].extendsFrom(
    configurations["implementation"],
    configurations["testImplementation"]
)

configurations["integrationTestRuntimeOnly"].extendsFrom(
    configurations["runtimeOnly"],
    configurations["testRuntimeOnly"]
)

dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.12.2")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher:1.12.2")
}

tasks.named<Test>("test") {
    useJUnitPlatform()
}

val integrationTest = tasks.register<Test>("integrationTest") {
    description = "Runs integration tests."
    group = "verification"

    testClassesDirs = sourceSets["integrationTest"].output.classesDirs
    classpath = sourceSets["integrationTest"].runtimeClasspath

    shouldRunAfter("test")
    useJUnitPlatform()
}

tasks.named("check") {
    dependsOn(integrationTest)
}
```

File `src/main/java/com/example/App.java`:

```java
package com.example;

public final class App {
    private App() {
    }

    public static String message() {
        return "source-set-demo";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

File `src/test/java/com/example/AppTest.java`:

```java
package com.example;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AppTest {
    @Test
    void returnsApplicationMessage() {
        assertEquals("source-set-demo", App.message());
    }
}
```

File `src/integrationTest/java/com/example/AppIntegrationTest.java`:

```java
package com.example;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AppIntegrationTest {
    @Test
    void integrationTestCanUseProductionClasses() {
        assertEquals("source-set-demo", App.message());
    }
}
```

### Creating the Gradle Wrapper and running the project

If the project does not have a wrapper yet, use an installed Gradle to generate one:

```sh
gradle wrapper --gradle-version 9.9.0
```

Then run the application:

Linux/macOS:

```sh
./gradlew run
```

Windows:

```powershell
.\gradlew.bat run
```

Application stdout:

```text
source-set-demo
```

Run unit tests and integration tests:

```sh
./gradlew clean test integrationTest
```

Run the full verification lifecycle:

```sh
./gradlew check
```

`check` includes the default `test` task and the `integrationTest` task wired into the lifecycle. The integration test demonstrates that a separate source set can compile and run tests with the production output on the classpath.

This example test only verifies source set wiring and access to production classes. A real integration test typically connects to a database, HTTP service, or out-of-process component and requires its own environment configuration.

## 12. Changing source and resource directories

If a project uses a non-standard layout, you can add or replace source roots.

Add a Java directory to `main`:

```kotlin
sourceSets {
    main {
        java.srcDir("legacy-src")
        resources.srcDir("legacy-resources")
    }
}
```

`srcDir()` appends a directory to the existing list. This works well when you need to keep both the default directories and legacy directories.

Replace the entire list of source roots:

```kotlin
sourceSets {
    main {
        java.setSrcDirs(listOf("app/java", "shared/java"))
        resources.setSrcDirs(listOf("app/resources"))
    }
}
```

`setSrcDirs()` replaces the existing list. When using it, re-add any default directories the project still needs; otherwise, Gradle will no longer scan the replaced roots.

You can configure custom source sets in the same way:

```kotlin
sourceSets {
    integrationTest {
        java.srcDir("src/it/java")
        resources.srcDir("src/it/resources")
    }
}
```

Avoid moving sources just to make the build script shorter if the standard layout already fits. The `src/<sourceSet>/java` and `src/<sourceSet>/resources` convention makes the project easier for IDEs, plugins, and team members to understand.

## 13. Filtering sources with include and exclude

Source sets support include/exclude patterns to control which files are included in compilation:

```kotlin
sourceSets {
    main {
        java {
            include("com/example/api/**")
            exclude("com/example/api/internal/**")
        }
    }
}
```

Patterns apply to paths relative to the source root. Use include/exclude when you need to keep the current layout but compile only a subset of sources.

Do not use `exclude` to hide package errors or unclear source organization. If two groups of sources have different dependencies or lifecycles, creating a separate source set is usually easier to maintain.

## 14. Resources in source sets

Each source set has its own resource roots. Gradle copies/processes resources into the corresponding output directory and places that output on the source set's runtime classpath.

For example:

```text
src/main/resources/app.properties
src/test/resources/test-data.json
src/integrationTest/resources/it-config.properties
```

These files are processed by:

- `processResources` for `main`.
- `processTestResources` for `test`.
- `processIntegrationTestResources` for `integrationTest`.

Code running in `main` can read resources using the class loader:

```java
try (var input = App.class.getResourceAsStream("/app.properties")) {
    if (input == null) {
        throw new IllegalStateException("Missing app.properties");
    }
}
```

`integrationTest` resources are only on the runtime classpath of the corresponding source set/task when configured as in the example. Do not assume test resources are production resources; `jar` only packages `main` output unless the build script is customized.

## 15. Generated sources and annotation processors

Generated sources are Java code produced during the build, for example from schemas, OpenAPI, Protocol Buffers, or internal code generators.

If generated sources are part of production code, add the output directory to the `main` source set and wire the generator task to the compile task:

```kotlin
sourceSets {
    main {
        java.srcDir(layout.buildDirectory.dir(
            "generated/sources/schema/main/java"
        ))
    }
}

tasks.named("compileJava") {
    dependsOn("generateSchema")
}
```

This example assumes a plugin or build logic has already registered the `generateSchema` task. If the task does not exist yet, you need to create it or apply the plugin that provides it.

Generated directories should live under `build/` rather than overwriting developer-managed sources. Gradle can delete `build/` when running `clean`; therefore, never store handwritten source code there.

For annotation processors, declare processors in their dedicated configurations:

```kotlin
dependencies {
    annotationProcessor("com.example:my-processor:1.0.0")
    testAnnotationProcessor("com.example:test-processor:1.0.0")
}
```

Custom source sets have their own annotation processor configuration, such as `integrationTestAnnotationProcessor`. Choose the right configuration so the processor runs only for the source set that needs it.

## 16. Source sets and the Java module system

A Gradle `SourceSet` is not synonymous with the Java Platform Module System (JPMS).

- A **Gradle source set** is a group of sources/resources and classpaths/outputs used for building.
- A **Java module** is a language/runtime-level module unit, typically declared with `module-info.java`.
- A **Gradle project/subproject** is a unit in the project graph, with its own build script, dependencies, and artifacts.

A source set can contain `module-info.java`, but creating a source set does not automatically create a new Java module. If you need module boundaries, `requires`, `exports`, or a module path, you must configure JPMS separately.

Unit tests in the `test` source set can run on the traditional classpath if there is no `module-info.java` in the test sources. If you need to test module boundaries or run white-box tests, you must configure the module path / patch-module appropriately; that is a separate concern from placing sources in a separate directory.

## 17. When should you create a custom source set?

A custom source set is appropriate when a group of sources:

- Has its own compilation or execution lifecycle.
- Needs a different compile/runtime classpath from `main` or `test`.
- Produces class outputs that are processed or packaged differently.
- Is a natural part of the same project, such as integration tests for production code.

Common examples:

| Need | Suggested source set |
|---|---|
| Production code | `main` |
| Unit tests | `test` |
| Integration tests with separate dependencies | `integrationTest` |
| JMH benchmarks | `benchmark` |
| Post-deploy smoke tests | `smokeTest` |
| Code generator tool with its own classpath | `codegen` |

Not every directory needs its own source set. If you only need to add a few Java files to the same compilation, you can add a source directory to an existing source set. If an API and its implementation need to be published as separate artifacts or have separate dependency graphs, consider splitting them into Gradle subprojects instead of adding source sets.

## 18. Source sets in multi-project builds

A Gradle multi-project build consists of multiple projects/subprojects, each of which can have its own source sets.

Example:

```text
root/
├── settings.gradle.kts
├── app/
│   ├── build.gradle.kts
│   └── src/main/java/
└── core/
    ├── build.gradle.kts
    └── src/main/java/
```

`core` and `app` are two different Gradle projects. Each project has its own `main` and `test` source sets if the Java Plugin is applied.

Declaring a project dependency:

```kotlin
dependencies {
    implementation(project(":core"))
}
```

Use subprojects when you need separate module boundaries, artifacts, versioning, publication, or ownership. Use source sets when source groups belong to the same project but need different compile/runtime classpaths or tasks.

Do not create source sets to replace dependencies between projects. Source sets do not automatically create project dependencies and do not publish independent artifacts.

## 19. Source sets and Maven source directories

Both Gradle and Maven follow common source directory conventions:

| Purpose | Gradle Java Plugin | Maven default |
|---|---|---|
| Production Java | `src/main/java` | `src/main/java` |
| Production resources | `src/main/resources` | `src/main/resources` |
| Test Java | `src/test/java` | `src/test/java` |
| Test resources | `src/test/resources` | `src/test/resources` |
| Separate integration tests | Custom source set + `Test` task | Additional plugins/configurations or separate module |

In Gradle, a source set is a build model with an API: source roots, resource roots, compile/runtime classpaths, outputs, dependency configurations, and tasks are all wired together.

In Maven, default directories are managed by the lifecycle/plugins. When you need additional test sources or separate compilations, you typically configure plugins such as `build-helper-maven-plugin`, `maven-compiler-plugin`, `maven-surefire-plugin`, or `maven-failsafe-plugin`. A Maven profile is not automatically equivalent to a Gradle source set; profiles primarily adjust build configuration based on environment or execution flags.

When migrating a build from Maven to Gradle, map the purpose of each source group and its dependencies first, then create the corresponding source sets and tasks. Do not simply copy directory names while ignoring classpaths and lifecycles.

## 20. Inspecting source sets and the task graph

The following commands help verify whether Gradle recognizes your source sets and tasks:

List tasks:

```sh
./gradlew tasks --all
```

Run individual compile tasks:

```sh
./gradlew compileJava
./gradlew compileTestJava
./gradlew compileIntegrationTestJava
```

Inspect a dependency configuration:

```sh
./gradlew dependencies --configuration integrationTestRuntimeClasspath
```

Inspect a specific dependency:

```sh
./gradlew dependencyInsight --dependency junit-jupiter --configuration integrationTestRuntimeClasspath
```

Preview the task graph before running:

```sh
./gradlew integrationTest --dry-run
```

If a task does not appear, check that the Java Plugin is applied and the source set is created in the build script. If the task exists but cannot find classes, check the source roots and compile classpath. If tests do not run, check `testClassesDirs`, `classpath`, the test framework, and test naming/filters.

## 21. IDEs and custom source sets

IntelliJ IDEA and Eclipse read the project model from Gradle. After adding a source set:

1. Reload/Refresh the Gradle project.
2. Verify that the IDE recognizes the correct source roots and dependencies.
3. Check that custom test directories are marked as test sources if the IDE does not detect them automatically.
4. Run tests via Gradle if the IDE runner does not use the custom source set's classpath properly.
5. Whenever the build script changes, re-sync the Gradle model before concluding the IDE has a bug.

IDEs may store their own metadata in the workspace. Do not manually edit `.classpath` or module configurations if Gradle is the primary source of configuration and can regenerate metadata.

## 22. Common errors when configuring source sets

| Symptom | Common cause | Fix |
|---|---|---|
| `compileIntegrationTestJava` finds no sources | Sources are in the wrong root or the source set name differs from expected | Check `src/integrationTest/java` and `sourceSets` |
| Cannot resolve production classes in integration tests | Missing `sourceSets.main.output` on the classpath | Add `main` output to compile and runtime classpaths |
| Compiles fine, but running tests fails with missing dependencies | Dependency is only on the compile classpath | Declare the dependency in `integrationTestRuntimeOnly` or `integrationTestImplementation` |
| `integrationTest` task does not appear | `Test` task not registered | Create `tasks.register<Test>("integrationTest")` |
| Task runs, but no tests are detected | `testClassesDirs` or `classpath` is wrong, or tests do not match the framework | Assign the source set's output classes and runtime classpath; check JUnit/TestNG |
| `check` does not run integration tests | Custom test task is not wired into the lifecycle | Add `dependsOn(integrationTest)` to `check` |
| JUnit classes not found during compilation | Dependency placed in the wrong configuration or source set not yet created | Declare in `integrationTestImplementation` after creating the source set |
| Resources missing at runtime | Resources in the wrong root or missing from runtime classpath | Check `src/<sourceSet>/resources` and source set output |
| Generated classes not found | Compilation runs before the code-generation task | Add the generated source directory and `dependsOn` the generator |
| JAR contains test code | Customized `jar` task accidentally includes test output in the archive | Package only production output if the artifact is a production JAR |
| IDE does not recognize new test directory | Gradle model not refreshed or IDE has not marked the test root | Reload the project and verify source root classification |
| Configuration does not exist | Accessed before creating the source set or wrong name | Create the source set first, then use the convention-based configuration name |
| Duplicate or redundant dependencies | Custom source set extends too many configurations | Extend only the dependencies actually needed |

## 23. Performance and maintainability

Separate source sets can make a build clearer, but each new source set also creates additional tasks and configurations. Too many small, overlapping source sets can make the build script harder to understand and increase configuration overhead.

Some guiding principles:

- Keep `main` and `test` following the default conventions.
- Create a source set only when you need a separate classpath, task, or lifecycle.
- Use separate dependency configurations to prevent test dependencies from leaking into production.
- Do not add generated sources into handwritten source directories.
- Have generator tasks declare explicit inputs/outputs and wire them properly to compile tasks.
- Avoid overwriting compile/runtime classpaths when you only need to append outputs.
- Wire verification tasks into `check` if CI builds must execute them.
- Use project dependencies when separate artifact/module boundaries are needed.
- Keep the DSL consistent and name source sets to clearly describe their purpose.

Source sets help Gradle understand what needs to be compiled, which resources need processing, which dependencies need resolving, and which outputs are used at runtime. A good build script makes these relationships explicit rather than simply listing many paths.

## 24. Checklist

- [ ] Distinguished a source set from a source directory, Gradle project, and Java module.
- [ ] Understood the Java Plugin's default `main` and `test` source sets.
- [ ] Learned that a source set consists of Java sources, resources, classpaths, and outputs.
- [ ] Understood how the compile classpath differs from the runtime classpath.
- [ ] Learned the `compileSourceSetJava`, `processSourceSetResources`, and `sourceSetClasses` tasks.
- [ ] Created custom source sets before declaring their dependency configurations.
- [ ] Added `main.output` to classpaths when custom tests need production classes.
- [ ] Declared dependencies in the appropriate `Implementation`, `CompileOnly`, `RuntimeOnly`, and `AnnotationProcessor` configurations.
- [ ] Created a dedicated `Test` task for custom test source sets.
- [ ] Wired custom verification tasks into `check` if they need to run in CI.
- [ ] Configured generated source directories and dependencies on generator tasks.
- [ ] Verified that resources are on the correct runtime classpath.
- [ ] Reloaded the Gradle model in the IDE.
- [ ] Checked the task graph and dependency configurations.
- [ ] Confirmed that the production JAR contains only the expected outputs.

## 25. References

- Gradle User Manual — Building Java & JVM Projects, Source Sets: https://docs.gradle.org/current/userguide/building_java_projects.html
- Gradle User Manual — Testing in Java & JVM Projects, Integration Tests: https://docs.gradle.org/current/userguide/java_testing.html
- Gradle Java Plugin — Tasks and Dependency Configurations: https://docs.gradle.org/current/userguide/java_plugin.html
- Gradle DSL Reference — SourceSet: https://docs.gradle.org/current/dsl/org.gradle.api.tasks.SourceSet.html
- Gradle User Manual — Managing Dependencies of JVM Projects: https://docs.gradle.org/current/userguide/dependency_management_for_java_projects.html

Source sets are the Gradle model for grouping sources and resources together with their corresponding classpaths, dependencies, and outputs. Start with `main` and `test`; create `integrationTest` or other source sets only when you need a separate compilation/runtime setup or task lifecycle. When classpaths are configured properly and tasks are wired into the lifecycle, Gradle can build and test each group of sources independently, repeatably, and predictably.