# The Role of Gradle or Maven Around the Java Compiler

## 1. Clearly Separating Two Responsibilities: Compilation and Build Process Orchestration

A `javac` command receives Java source files, resolves dependencies via the classpath/module path, checks syntax/semantics, and then creates `.class` files. However, a real-world project must also:

- Select the right sets of application sources, tests, and generated sources.
- Download, select versions for, and pass dependency JARs to the compiler.
- Use an appropriate JDK, set `--release`, encoding, and compiler flags.
- Compile prerequisite modules/libraries that downstream modules need first.
- Run annotation processors or code generation steps, and process resources.
- Run tests, quality analysis, package, and publish artifacts.
- Reuse valid results in incremental builds or cache.
- Execute the same workflow on development machines and CI.

**Gradle and Maven are build orchestration tools; `javac` is the compiler that actually checks and converts Java source into bytecode** (in standard Java configurations). A build tool does not invent a different Java language, does not replace javac's semantic analysis, and does not turn a syntactically invalid program into a valid one.

~~~text
                   Build configuration
                    Gradle / Maven
                           |
          +----------------+----------------+
          |                |                |
      source sets       dependencies     JDK/toolchain
          |                |                |
          +----------------+----------------+
                           |
                compiler arguments
                           |
                       javac
                           |
                         .class
                           |
          +----------------+----------------+
          |                |                |
       resources          tests           package
          |                |                |
          +----------------+----------------+
                           |
                  JAR / distribution
~~~

The diagram is a logical model. The actual path and order of tasks/goals depend on plugins, project configuration, and the dependency graph; not every build command executes every branch.

**Key takeaway:** when a Java source reports `cannot find symbol`, the compiler emits the diagnostic; whether that type is found or not may be because the *build tool* has not yet provided the right dependency to the compiler. Diagnosis requires knowing whether the error lies in the Java code or in the command/configuration prepared by Gradle/Maven.

## 2. Comparing a Manual javac Command with a Build Tool

Plain Java commands to compile and run a class:

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 -d out src/main/java/demo/App.java
java -cp out demo.App
~~~

You need to manually prepare `-cp` when the program has dependencies; you must manually update the command when adding sources, tests, generated sources, or multiple modules. For a standalone file, this approach is still useful for understanding the compiler and reproducing minimal errors.

Gradle/Maven typically translate higher-level intent into an equivalent compiler invocation:

| Need | With manual javac/java | With a build tool |
| --- | --- | --- |
| Source files | List files/create input list | Source sets or project layout |
| Compiler JDK | Choose `javac` executable | Toolchain/compiler plugin |
| Java version | `--release 17` | Gradle `options.release`, Maven `maven.compiler.release` |
| Binary dependencies | `-classpath` or `--module-path` | Resolve artifacts, build compile classpath |
| Annotation processors | `-processorpath` and related options | Processor dependencies/paths, compile task config |
| Class output | `-d out` | Output directory per task/plugin |
| Resources | Copy manually | Gradle `processResources`, Maven resources plugin |
| Tests | Compile tests and run test runner separately | Task/goal via corresponding framework/plugin |
| JAR | Invoke `jar` | Gradle `jar`, Maven package lifecycle/plugin |
| Incremental/cache | Manage manually | Gradle incremental task + build cache, Maven/plugins have separate mechanisms |

**Do not say Gradle/Maven “replace javac”.** In normal Java builds, Gradle `JavaCompile` or the Maven Compiler Plugin invokes the compiler beneath an abstraction layer. A project may use an alternative compiler, Kotlin/Scala, or another code generation task, so the actual mechanism must be read from the configured plugins.

## 3. Shared Java 17+ Example for Both Gradle and Maven

Use **one** source file for two independent build approaches:

~~~text
sample-project/
├── src/
│   └── main/
│       └── java/
│           └── demo/
│               └── App.java
├── build.gradle             # choose when using Gradle
├── settings.gradle          # choose when using Gradle
└── pom.xml                  # choose when using Maven
~~~

File **src/main/java/demo/App.java**:

~~~java
package demo;

public final class App {
    private App() {}

    public static int total(int left, int right) {
        return Math.addExact(left, right);
    }

    public static void main(String[] args) {
        System.out.println("SUM=" + total(2, 5));
    }
}
~~~

This is a normal Java application; it does not import any Gradle or Maven APIs. Therefore **the source code does not need to be rewritten when switching from Gradle to Maven**. Both only change how compilation inputs, options, and steps around the compiler are prepared.

### 3.1. Baseline Check with javac, Without a Build Tool

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 -d out src/main/java/demo/App.java
java -cp out demo.App
~~~

Application stdout:

~~~text
SUM=7
~~~

You can inspect the bytecode:

~~~bash
javap -classpath out -verbose demo.App
~~~

The header section of the class file has:

~~~text
major version: 61
~~~

Java 17 uses class-file major version 61. The `SUM=7` output and major 61 were verified using `javac 21` with `--release 17` in a separate test environment. This verifies the Java source, **not** a confirmation of Gradle/Maven commands in an environment that does not have them yet.

## 4. Gradle: Java Plugin, Task Graph, and Compiler Task

Gradle is a build system based on **tasks** and dependency relationships between tasks. For Java, the `java` plugin registers common source sets, configurations, and tasks:

| Task | Role |
| --- | --- |
| `compileJava` | Uses the Java compiler for `main` sources |
| `processResources` | Copies `main` resources into output |
| `classes` | Aggregate task depending on compile/resources |
| `compileTestJava` | Compiles `test` sources with the test compile classpath |
| `processTestResources` | Processes test resources |
| `testClasses` | Aggregates test outputs |
| `test` | Runs tests according to the configured test framework/engine |
| `jar` | Packages production classes/resources into a JAR |
| `assemble` | Aggregates packaged artifacts |
| `check` | Aggregates verification steps |
| `build` | Typically depends on `assemble` and `check` |

The **task graph** matters more than the order of lines in the configuration file. When `build` is requested, Gradle builds the graph and runs the necessary prerequisite tasks, avoiding re-running tasks that do not need work if inputs/outputs satisfy up-to-date conditions.

### 4.1. Complete Gradle Groovy DSL Example

File **settings.gradle**:

~~~groovy
rootProject.name = 'compiler-build-demo'
~~~

File **build.gradle**:

~~~groovy
plugins {
    id 'application'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}

application {
    mainClass = 'demo.App'
}
~~~

The `application` plugin applies the required Java functionality and adds the `run`/distribution tasks. `mainClass` is the fully qualified name of the class containing `main`. No `implementation` dependency needs to be added for the `App` example because it only uses the Java standard library.

**Separate the two properties:**

- `java.toolchain.languageVersion = 17`: instructs Gradle to use an appropriate Java 17 toolchain for compilation and JVM tools managed by the plugin.
- `options.release = 17`: instructs the compiler to enforce Java 17 rules for syntax, class-file version, and public platform APIs.

If the goal is to compile using JDK 21 while producing an artifact that runs on Java 17, you can request toolchain 21 and `options.release = 17`, provided that Gradle/toolchain/compiler all support that combination. Do not replace `--release` with `-source`/`-target` and accidentally call APIs newer than the target runtime.

### 4.2. Gradle Commands

On a project with **Gradle Wrapper**:

~~~bash
./gradlew clean build
./gradlew run
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean build
.\gradlew.bat run
~~~

Wrapper files (`gradlew`, `gradlew.bat`, and `gradle/wrapper/...`) must have already been generated/committed according to project workflow. **The build.gradle example above does not automatically generate wrapper files.** If there is no wrapper yet, you can use a compatible installed Gradle version to run `gradle build`/`gradle run` or generate the wrapper via the standard workflow. Do not promise that `./gradlew` can run if the project does not yet have that script.

The stdout line **printed by App itself** during `run` is:

~~~text
SUM=7
~~~

Gradle's output also includes task/build information; therefore do not assume the entire terminal output consists of only one line. The `build` task packages and executes configured check steps; it **does not automatically invoke App.main()**. Only the Application Plugin's `run` task executes the main class. The `test` task runs tests if present and if a test framework is properly configured.

Default outputs of the Gradle Java plugin typically reside in `build/classes/java/main`, resources in `build/resources/main`, and the JAR under `build/libs`. These are **conventions**, which can be changed via build configuration, and should not be hardcoded in integration tools.

## 5. Maven: Lifecycle, Phases, Goals, and Compiler Plugin

Maven operates on **lifecycles** and **phases**; plugin goals are bound to phases. For a typical project with `jar` packaging:

| Phase/goal | Typical meaning |
| --- | --- |
| `validate` | Validates basic project model/configuration |
| `process-resources` | Copies/filters resources via the resources plugin |
| `compile` | Compiler plugin compiles main sources |
| `process-test-resources` | Prepares test resources |
| `test-compile` | Compiler plugin compiles test sources |
| `test` | Surefire plugin may run unit tests |
| `package` | Packages into a JAR or corresponding packaging |
| `verify` | Performs additional checks after packaging if configured |
| `install` | Installs the artifact into the local Maven repository |
| `deploy` | Deploys the artifact to an appropriate remote repository |

When invoking `mvn package`, Maven executes the necessary phases **from the start of the default lifecycle up to package** according to the project/plugins bindings; it is not just a single `jar` command. Specific goals may differ depending on packaging, plugin config, and extensions.

### 5.1. Complete pom.xml to Compile Java 17

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>compiler-build-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The Maven Compiler Plugin reads the `maven.compiler.release` property and controls the compiler accordingly. This lesson chooses the specific plugin version **3.13.0** so the configuration is reproducible; real projects should update plugin versions according to tested JDK/Maven compatibility, rather than blindly using an uncontrolled “latest”.

This POM **does not configure the Maven Toolchains Plugin**: Maven uses whatever JDK the environment/plugin actually selects, so you need to check `mvn -version` and ensure the JDK supports release 17. Maven running on JDK 8 cannot understand `--release 17`; a POM having property 17 does not automatically download JDK 17 for every machine.

### 5.2. Compile, Package, Run

From the project root when Maven 3 and an appropriate JDK are available:

~~~bash
mvn clean package
java -cp target/classes demo.App
~~~

Stdout printed by `App`:

~~~text
SUM=7
~~~

Maven will print many lines of build logs; `mvn clean package` does not invoke `App.main` by default. The JAR is usually located at a path like `target/compiler-build-demo-1.0.0.jar` (a convention based on artifactId/version), and can be run via the classpath:

~~~bash
java -cp target/compiler-build-demo-1.0.0.jar demo.App
~~~

In this example without external libraries, the command using the JAR can run if packaging succeeded. However, **`java -jar target/compiler-build-demo-1.0.0.jar` does not necessarily work by default**: by default a JAR does not necessarily have `Main-Class` in its manifest. To get an executable JAR you must configure the appropriate manifest/packaging; if there are runtime dependencies you must bundle them or provide a valid classpath.

**The Gradle and Maven configurations here are two alternatives.** There is no need to run both builds in one pipeline if the project chooses only one tool. When keeping both configuration files in the same directory for comparison purposes, Gradle outputs are in `build/` and Maven outputs are in `target/`; do not use outputs from one system to evaluate a build of the other.

## 6. Dependency Resolution: The Biggest Responsibility Beyond javac

`javac` does not read Maven POMs or Gradle module metadata to go out onto the Internet and select dependencies by itself. It needs an already-prepared **compile classpath** or **module path**.

Example source:

~~~java
import org.example.api.Widget;
~~~

This is an **illustrative import** (not part of the runnable App.java): if the compiler does not receive the `org.example.api.Widget` class, it reports an error even though the source file has the import. The build tool is responsible for choosing the right artifact version, fetching the JAR, and placing the class output/JAR paths into the compiler invocation.

Declaring dependencies has different meanings depending on scope/configuration:

| Intent | Gradle Java plugin | Maven |
| --- | --- | --- |
| Used at compile and runtime | `implementation` | Default `compile` scope |
| Needed only at compile time | `compileOnly` | `provided` has distinct distribution/container semantics, **not fully equivalent** |
| Needed only at runtime | `runtimeOnly` | `runtime` |
| Used in tests | `testImplementation` / `testRuntimeOnly` | `test` |
| Annotation processor | `annotationProcessor` | Appropriate processor path/plugin configuration |
| Expose API to consumer library | `api` from `java-library` | Dependency contract/version in POM |

**Scope does not only affect the library download step.** It determines which types the compiler sees, what test compilation sees, and which JARs are present at runtime. In Maven, `provided` means the runtime environment/container is expected to supply the dependency, so it must not be treated as a synonym for Gradle's `compileOnly` in every packaging type.

With Java modules (JPMS), the build tool must also prepare `--module-path` and the corresponding module graph: a JAR being in the dependency graph does not mean code is allowed to access a package if the module does not `exports` it or the client does not `requires` it.

### 6.1. Why Do Transitive Dependencies Need Management?

Suppose App depends on A, and A depends on B. The build tool can resolve B according to appropriate metadata and scopes, choosing a version when multiple graph paths conflict. `javac -cp lib/A.jar` alone does not automatically download B from a repository.

Diagram:

~~~text
App
 |
 +--- library A v2
 |         |
 |         +--- library B v4
 |
 +--- library C v1
           |
           +--- library B v3

Build tool --> dependency resolution --> B is selected according to rules
Compiler   --> actual classpath containing the resolved artifact
~~~

Do not assume Gradle and Maven always select **the exact same version** when a graph has conflicts: each tool has its own metadata, scopes, and dependency resolution rules. Inspect the actual graph and enforce/lock appropriate versions.

Do not add every JAR you can find to the classpath just to clear `cannot find symbol`. Doing so can add duplicate classes, incompatible ABIs, wrong-version classes, or libraries not licensed for distribution.

### 6.2. How to Investigate the Dependency Graph

In Gradle, from a project with the Java plugin:

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencyInsight --dependency example --configuration compileClasspath
~~~

The word `example` above is an **illustrative search string**, which needs to be replaced with the actual group/artifact. These commands do not modify Java source; they help identify which dependencies the compiler task will see. In a multi-project build, select the corresponding project/task/configuration.

With Maven:

~~~bash
mvn dependency:tree
~~~

This command requires the corresponding Maven Dependency Plugin to be resolvable, and you must inspect the right module/scope. It helps identify transitive dependencies and unintended versions. Simply having a dependency listed does not guarantee the desired class is inside the artifact: you may need to inspect the JAR contents.

## 7. Toolchain and --release: Build-Running JDK vs Target JDK

There are three versions to distinguish:

1. **JVM running the Gradle daemon or Maven**: affects the ability to run the build tool/plugins themselves.
2. **Compiler JDK/toolchain selected for the compile task**: determines the javac implementation and supported releases.
3. **Minimum target runtime**: the lowest JVM that the artifact must support.

Gradle allows explicit toolchain configuration, even when the JDK used to run Gradle differs from the JDK used to compile. Maven has the Maven Toolchains Plugin or ways to select the executable/compiler depending on plugin/version and environment; a POM that only sets `maven.compiler.release` has **not yet** locked the compiler JDK for CI.

`--release 17` instructs the compiler to generate Java 17 bytecode and restricts public Java 17 platform APIs, but does not verify that every binary dependency JAR is compatible with JVM 17. A third-party JAR compiled with a newer class-file version may fail to run on Java 17.

| Configuration | What does it control? | What it does not automatically guarantee |
| --- | --- | --- |
| Gradle Java 17 toolchain | Selects JDK/tools to compile/test per task config | That code does not use newer APIs than the target if the compiler target differs |
| `options.release = 17` | Source, class version, Java 17 platform APIs | Selecting the right compiler executable or compatible dependency JARs |
| Maven `maven.compiler.release=17` | Equivalent to compiler `--release 17` when toolchain/plugin supports it | That the JVM running Maven and compiler JDK are pinned |
| `sourceCompatibility/targetCompatibility` | Language level/class format as supported | Old APIs being fully checked like `--release` |

**If you want to confirm the application runs on Java 17**, at a minimum you must compile with the appropriate target/release, select dependency JARs with an appropriate minimum Java version, and **run tests on a real Java 17 runtime**. Compiling successfully under JDK 21 is not enough to prove every Java 17 runtime behaves the same.

## 8. Compiler Options: Configured by Build Tool, Executed by javac

Some compiler options passed by the build tool to the Java compiler:

| Option | Purpose | What the build tool must additionally handle |
| --- | --- | --- |
| `--release N` | Language, class version, public JDK API level | Toolchain javac supports N |
| `-encoding UTF-8` | Charset for reading sources | Files are actually saved with the appropriate charset |
| `-cp` / `--class-path` | Compile-dependent classes/JARs | Resolving the right artifacts and scopes |
| `--module-path` | Named modules | Resolving module graph and module-info |
| `-processorpath` | Specifies annotation processors path | Tasks/source sets and processor versions |
| `-processor` | Selects processor when declared explicitly | Processor class exists and is compatible |
| `-s` | Where to write annotation processor generated sources | Tracking generated output as task output |
| `-Xlint` | Warning diagnostics | Policy for checking warnings/CI |
| `-Werror` | Turns warnings into build failures | Ensuring root-cause warnings are understood and fixed |

Both Gradle and Maven have configuration layers suitable for common options. When a very specific javac flag is needed, you can pass explicit compiler args via plugin APIs, but you must check versions to avoid duplicate flags or conflicts with options auto-generated by the plugin.

**Do not think that a build tool can fix compiler diagnostics by changing wording.** If Java source violates overload resolution, access control, or definite assignment, the compiler still rejects it. The build tool helps the compile command run in the right environment and lets tasks fail early when outputs are invalid.

## 9. Annotation Processing and Generated Sources

A processor can generate new source code during compilation, such as mappers, DTO helpers, or metadata classes. If a processor is missing or runs incorrectly, many other sources may simultaneously report `cannot find symbol` for generated types.

~~~text
Annotations / schema
        |
        v
Processor / generate task
        |
        v
Generated source
        |
        v
JavaCompile / compiler plugin
        |
        v
Consumer classes
~~~

The build tool's work includes:

- Placing the annotation API on the **compile classpath** under the appropriate scope.
- Placing the annotation processor implementation on the **processor path** instead of accidentally pulling it into runtime.
- Creating proper producer/consumer task relationships, and defining output/generated source directories.
- Ensuring the dependency graph and compiler JDK are suitable for the processor.
- Tracking inputs/outputs so incremental/caching does not return stale generated code.

Gradle fragment example, requiring real artifacts to run:

~~~groovy
dependencies {
    compileOnly 'example:annotations:1.0'
    annotationProcessor 'example:processor:1.0'
}
~~~

The two coordinates `example:...` only illustrate configuration; they are **not real dependencies guaranteed to be downloadable**. In the Maven Compiler Plugin, configure annotation processor paths or processor dependencies according to the required version/plugin. Different JDK and plugin versions may have different auto-discovery policies; it is best to configure processors explicitly when the build requires generated code.

When using libraries like Lombok or MapStruct, do not assume declaring a single compile dependency is enough for every version/plugin. You need to check each processor's specific rules, module opens when genuinely needed, and test a clean build.

## 10. Multi-module: Compilation Order Is a Dependency Relationship

Large projects often split into `core`, `service`, `app`, or multiple modules released together. The compiler for the `app` module cannot create `core` classes by itself if the build tool does not yet have valid core output/JAR.

A Gradle multi-project uses a `settings.gradle` listing projects:

~~~groovy
rootProject.name = 'workspace'
include 'core', 'app'
~~~

In `app/build.gradle`, fragment:

~~~groovy
plugins {
    id 'java'
}

dependencies {
    implementation project(':core')
}
~~~

These snippets are **not a complete multi-project**: you need to add `core/build.gradle`, sources, and appropriate Java plugin/toolchain config. The purpose is to show the dependency edge between tasks/products, so that core is compiled before app uses core's binary output.

A Maven multi-module build uses an aggregator POM with modules:

~~~xml
<modules>
    <module>core</module>
    <module>app</module>
</modules>
~~~

This is a **fragment** inside a valid aggregator `pom.xml`, not a standalone POM. App needs to declare a dependency on the core artifact with the right coordinates/version. The Maven reactor will use dependency relations to determine the build order; simply listing names in `modules` without a dependency edge is not enough to express all compilation dependencies.

**Distinguishing Gradle multi-project and JPMS named modules:** they may overlap in organization, but they are not the same concept. JPMS is Java's module model with `module-info.java`, `requires`, and `exports`; Gradle/Maven can manage modules while sources still belong to the unnamed module on the classpath.

## 11. Incremental Build, Up-to-date Check, Cache, and Clean

Gradle has task input/output tracking, incremental compilation for supported configurations, and build caching; Maven has incremental behaviors depending on the compiler plugin/version along with output tracking. Do not claim that every Maven or Gradle build recompiles the entire project, nor promise that every task is always cached.

**Distinguish:**

- **Up-to-date task:** inputs/outputs do not require re-executing the task according to Gradle's check.
- **Incremental compilation:** the compiler/task only processes affected portions of sources according to change-analysis capability, not necessarily every file.
- **Build cache:** reuses previously computed outputs when the cache key and configuration allow.
- **Clean build:** deletes generated outputs via the build tool mechanism to rebuild from scratch and detect stale outputs.

Gradle example:

~~~bash
./gradlew compileJava
./gradlew compileJava
./gradlew clean compileJava
~~~

Under the same stable conditions, the second run **may** be marked up-to-date; the actual result depends on plugins, inputs, compiler arguments, cache, and Gradle's ability to track outputs. `clean` removes the build directory's outputs for the corresponding tasks, helping verify whether a leftover artifact was masking an error.

Maven:

~~~bash
mvn compile
mvn clean compile
~~~

Maven's incremental mechanism and logs depend on the compiler plugin version, environment, and project configuration. Do not automatically equate `mvn compile` with the Gradle `compileJava` task in terms of cache/incrementality.

A build succeeding due to old `.class` files or sources left behind by a generator does not prove a reproducible build. Test from a clean checkout, pin toolchain/dependencies, and check source generation. However, **do not manually delete directories someone else is using** if you do not own the workspace.

## 12. Packaging and Testing Are Not javac's Job Alone

`javac` creates `.class` files, but a distribution also needs:

1. Resources (config, templates, service descriptors) accompanying classes when needed.
2. An appropriate manifest or entrypoint; not every JAR is executable.
3. Runtime dependencies available via classpath/module path or a specific packaging strategy.
4. Tests with a properly configured framework/engine and test-scoped dependencies.
5. Packaging plugins that know which outputs are needed, exclude files not belonging to the distribution, and avoid duplicate classes/resources.

**Regular JAR vs executable/fat JAR**:

- Gradle `jar` or Maven `jar:jar` by default can package classes/resources into a **library JAR**.
- Manifest `Main-Class` needs to be configured if you want `java -jar` to run directly.
- Even with `Main-Class`, external dependencies are not automatically bundled into a standard archive. You may need a distribution, manifest classpath, or a plugin creating a runnable/fat JAR, with policies for handling duplicate resources/licenses.
- `java -cp app.jar:dependencies/* demo.App` is a different execution mechanism (the separator on Windows is `;`) and must not be equated with `java -jar`.

The compiler will not know whether the final product needs a Docker image, native launcher, WAR, or a plugin distribution. This is a build/packaging/deployment responsibility separate from checking Java source.

## 13. Reproducibility and CI: Conditions for “Works on My Machine” to Be Meaningful

A reliable build needs to control:

- **Gradle/Maven version**: use an appropriate Wrapper, such as a Gradle Wrapper or Maven Wrapper configured/committed in the project.
- **Compiler JDK/toolchain**: exact Java version and compiler provider; build logs should show the actual toolchain.
- **Dependency versions**: pin or lock according to policy; avoid depending on uncontrolled dynamic versions.
- **Plugin versions**: Maven Compiler Plugin, Surefire, resources/JAR, Gradle plugins according to compatibility policies.
- **Repositories and metadata**: configure mirrors, authentication, offline mode, and artifact integrity when needed.
- **Encoding/locale/timezone**: avoid environment-dependent outputs; especially resource filtering, source encoding, and generated files.
- **Annotation processors/generated sources**: outputs clearly regenerated from source, avoiding stale files.
- **Tests**: run under the actual target runtime JDK and with the runtime dependency graph.
- **Build artifact**: record version, checksums, and provenance when delivering products.

A CI job might perform steps like:

~~~text
Clean checkout
  |
Setup JDK 17 + Gradle/Maven Wrapper
  |
Resolve pinned dependencies
  |
Compile sources + process resources
  |
Compile/run unit tests
  |
Package artifact
  |
Smoke test under target runtime
  |
Publish if all checks succeed
~~~

This is a conceptual pipeline; real organizations may add security scans, integration tests, signed artifacts, and staging environments.

## 14. How to Read Errors to Tell Whether javac or the Build Tool Is Failing

| Symptom | Layer to inspect first |
| --- | --- |
| `cannot find symbol` when code uses a real type | Compiler diagnostic + compile classpath/source roots |
| `package ... does not exist` | Import, actual JAR, dependency scope, module path |
| `invalid target release` | Compiler JDK and `--release`/toolchain |
| `UnsupportedClassVersionError` at runtime | Runtime JVM lower than application/dependency bytecode |
| `NoSuchMethodError` at runtime | Runtime binary API/JAR differs from compile time |
| Processor-generated type disappears | Annotation processor config, generated source task/output |
| `Could not resolve ...` from Gradle/Maven | Repository, dependency coordinates/metadata, proxy/network |
| `Task :compileJava FAILED` | Read the **javac diagnostic content** inside the task |
| Maven compiler goal failure | Read javac diagnostics and plugin/compiler parameters |
| Source compile passes but `java -jar` fails | Main-Class, packaging, runtime dependencies |
| CI passes via cache but clean build fails | Missing declared inputs, stale generated output, cache config |
| Main compile passes, testCompile fails | Test-specific source set, dependencies, and test toolchain |

**Do not fix imports by arbitrarily renaming packages when the real error is an unresolved dependency.** Conversely, do not blame Gradle/Maven when the source has ambiguity or violates the Java type system. The build tool and compiler provide two complementary layers of information.

With Gradle, if you need to see more task details, you can use `--info`; with Maven use `-X` to debug. Build tool debug logs help locate compiler invocations/dependency resolution but do not replace compiler error messages at file and line.

## 15. Common Misconceptions

1. **“Using Maven means you don't need javac.”** False: the compiler plugin still needs a Java compiler/toolchain to create class files for Java source.
2. **“Just installing JDK 17 guarantees the artifact runs on Java 17.”** False: you must verify release, class-file version, dependencies, and runtime.
3. **“Declaring a dependency means every scope sees it.”** False: compile, runtime, test, and annotation processor paths have distinct responsibilities.
4. **“`mvn package` runs the main class.”** False in standard configurations; package creates the artifact, it does not invoke `App.main()`.
5. **“`gradle build` is just another way to call `javac`.”** False: it has a task graph consisting of other steps according to plugins.
6. **“Given the same source, Gradle and Maven definitely produce byte-for-byte identical JARs.”** False: metadata, manifest, timestamps, plugin config, resource ordering, and reproducible archive settings may differ.
7. **“Adding a JAR to the lib folder makes the build tool use it automatically.”** Not necessarily: the dependency must be declared in an appropriate configuration.
8. **“Cleaning every time is the fastest way to build.”** Clean discards the ability to reuse valid outputs; use it when verifying/reproducing errors, not by default for every development cycle.
9. **“Plugins automatically execute in the order written in build.gradle/pom.xml.”** Task/phase/binding relationships are the actual execution basis.
10. **“An annotation processor is a Java source runtime library.”** Processors run during the compile phase; they usually need a separate processor path and do not automatically belong to the runtime distribution.
11. **“Toolchain and `--release` are the same flag.”** Toolchain selects the compiler JDK; release defines the compilation target.
12. **“Compile passing means the build is ready for release.”** Not yet: there are still tests, resources, packaging, runtime dependencies, compatibility, and deployment checks.

## 16. Study and Hands-on Verification Workflow

**Exercise 1 — Comparing unchanged Java source:** create `App.java` from section 3 and compile it manually with `javac`. Run it to produce `SUM=7`, and use `javap -verbose` to verify major 61.

**Exercise 2 — Using Gradle:** choose `settings.gradle` + `build.gradle` from section 4. With an appropriate Gradle version and JDK, run `gradle clean build` and then `gradle run` (or Wrapper if available). Read the task graph, find the output `build/classes/java/main/demo/App.class`, and distinguish task logs from App stdout.

**Exercise 3 — Using Maven:** use `pom.xml` from section 5 and JDK 17+. Run `mvn clean package`; observe the output `target/classes/demo/App.class` and JAR. Run `java -cp target/classes demo.App` instead of expecting package to run the program automatically.

**Exercise 4 — Creating an intentional error:** change `Math.addExact` to a call to a non-existent method. Both build systems must report a `javac` error even though their task/goal execution paths differ. Restore the code and rebuild.

**Exercise 5 — Reading the dependency graph:** in a project with real dependencies, inspect Gradle `dependencies` / `dependencyInsight` or Maven `dependency:tree`. Compare compile and runtime paths, and identify a dependency brought in only for tests.

**Exercise 6 — Observing toolchains:** compile with a newer JDK and `--release 17`, and verify class major 61. Run tests on a real Java 17 runtime if claiming Java 17 as the minimum runtime.

**Exercise 7 — Clean vs incremental:** run compile twice and note whether the task is skipped/up-to-date; run clean compile to see the difference. Do not interpret a single test run as a universal guarantee for every project.

## 17. Configuration Checklist Before Committing a Java Build

- Is the project choosing Gradle or Maven as the build source of truth? Are Wrapper/plugin versions managed?
- Are `main` / `test` / generated source roots accurate and separated?
- Are compiler JDK, `--release`, and encoding clear and consistent with supported runtimes?
- Are compile classpath, runtime classpath, test path, and processor path properly separated?
- Are dependencies, versions, and conflict-resolution rules controlled?
- Are multi-module/project dependencies declared via graph edges, rather than merely hoping for script order?
- Do generated sources and resources have proper producer tasks, inputs/outputs, and task dependencies?
- Does `build` or `package` actually run the necessary tests, rather than just compiling?
- Does the JAR need to be executable, and how are manifest/runtime dependencies packaged?
- Does CI reproduce from a clean checkout and run with the target toolchain/runtime?

**Conclusion:** Gradle/Maven organize everything *around* `javac`: sources, dependencies, toolchains, task order, processors, tests, resources, packaging, and reproducibility. `javac` remains where syntax/semantics are checked and bytecode is generated in a standard Java compilation. Understanding that boundary helps fix bugs at the right layer and keep builds maintainable.

## References

- [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html): tasks, source sets, compile/runtime configurations.
- [Gradle — Toolchains for JVM projects](https://docs.gradle.org/current/userguide/toolchains.html): JDK toolchain, `options.release`, and reproducibility.
- [Gradle — Build Lifecycle](https://docs.gradle.org/current/userguide/build_lifecycle.html): initialization, configuration, execution, and task graph.
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): phases, goals, and bindings.
- [Apache Maven Compiler Plugin — Setting the --release of the Java Compiler](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html): `maven.compiler.release`.
- [Oracle Java SE 17 — javac Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): compiler options configured by build tools.
