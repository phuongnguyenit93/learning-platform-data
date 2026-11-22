# Upgrading build plugins, internal plugins, and scripts that are no longer compatible

A Java project can have valid source code, the right runtime dependencies, and a matching compiler target, yet still **fail to build after changing the JDK or upgrading Maven/Gradle**. The cause often lies in the tooling layer: compiler plugins, test plugins, packaging plugins, annotation processors, internal plugins, Groovy/Kotlin scripts, CI shell scripts, or configurations relying on old build-tool APIs and behaviors.

For example, an application is migrating from JDK 17 to 21, yet the Gradle Wrapper does not yet support running on JDK 21; a bytecode enhancement plugin does not recognize the new class-file version; a custom script calls a removed Gradle API; or a Maven plugin is compiled for a higher JDK than the JVM running Maven. All of these can fail **before the application is ever executed**. Some failures surface only on a clean CI run, when configuration cache is enabled, on Windows, inside Docker, or during a packaging task.

In Java Advance Compatibility Migration, treat the **build system as an independent software program with its own runtime, dependency graph, and upgrade lifecycle**. This lesson guides you through inventorying, upgrading, and verifying build plugins, internal plugins, and legacy scripts on Maven/Gradle without confusing them with application runtime compatibility.

## 1. Version layers that must be separated

A real-world Java build typically involves multiple independent versions:

| Layer | Example | Question to answer |
|---|---|---|
| JDK running the build tool | JVM running the Gradle Daemon or Maven | Can the build tool and plugins run on this JDK? |
| Maven/Gradle distribution | Maven Wrapper, Gradle Wrapper | Does the build tool version support the new JVM, DSL, and plugin APIs? |
| Compiler/toolchain | JDK selected by `javac` or the compiler task | Which compiler is compiling the source? |
| Target language/API | `--release 17` or `--release 21` | Which runtime must the output artifact support? |
| Build plugins | Compiler, test, codegen, shading, publishing | Are plugins compatible with the build tool and the JVM running them? |
| Internal plugins | Convention plugins, internal JAR-published plugins | Do they depend on internal APIs or target too new a JDK? |
| Build scripts | `pom.xml`, `build.gradle`, `build.gradle.kts` | Are the DSL and task wiring still valid? |
| Plugin/tool dependencies | ASM, Groovy, Kotlin, generators, formatters | Is each plugin's own runtime classpath right? |
| Test JVM | JVM used by Surefire/Failsafe or the Gradle Test task | Do tests run on the target JDK? |
| Production JVM | JRE/container running the application | Are the artifact and runtime dependencies compatible? |

Key point: **Upgrading the JDK used to compile source code does not automatically upgrade Gradle, Maven, or plugins**. Conversely, upgrading the Gradle Wrapper does not automatically upgrade the application runtime.

If the Gradle Daemon is running on JDK 17, an internal plugin compiled into Java 21 class files can throw `UnsupportedClassVersionError` as soon as the plugin is loaded, even if the project intends to compile the application using a JDK 21 toolchain. This is a *plugin runtime* issue, not an application bytecode issue.

## 2. Build execution models: how Maven and Gradle differ

### 2.1. Maven: core, plugin realms, and forked processes

Maven runs on a JVM selected via `JAVA_HOME`, the Maven Wrapper, or the execution environment. Maven core parses the POM, resolves the lifecycle, and loads plugins through dedicated class realms.

A plugin such as `maven-compiler-plugin`, `maven-surefire-plugin`, or an internal Mojo can:

- Run inside Maven's JVM.
- Load dependencies belonging only to its plugin realm.
- Launch another process/forked JVM to compile or test.
- Use Toolchains to select a different JDK for a specific step.

Therefore, inspect the JVM running Maven, the compiler JDK, the test JVM, and plugin dependencies separately. Checking `java -version` in a terminal alone does not necessarily tell you which JDK Maven uses when forking or testing.

### 2.2. Gradle: client, Daemon, plugins, and toolchains

The Gradle Wrapper selects the distribution; the Gradle Daemon runs on a specific JVM. Gradle plugins are loaded into the build runtime, using the Gradle API and their own dependency classpath as declared. Java toolchains can select a compiler, test launcher, or executable different from the Daemon's JDK.

Example:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

The configuration above can allow the JDK 21 compiler to produce bytecode and constrain APIs to Java 17, **yet it does not prove the Gradle Daemon is running on JDK 21**. Conversely, if the Daemon runs JDK 21 while an internal plugin is only compatible with an older Gradle API, the plugin can still fail during the configuration phase.

The Gradle Wrapper, plugin portal, settings plugins, convention plugins, and application dependencies are distinct layers that require separate investigation.

### 2.3. Failure lookup table by phase

| When the error appears | Area to inspect first | Example symptoms |
|---|---|---|
| Before Gradle configures the project | Wrapper/JDK/Gradle distribution | Unsupported Java runtime or Groovy/Kotlin init error |
| Immediately upon applying a plugin | Plugin binary, Gradle API, plugin dependencies | `NoSuchMethodError` in a Gradle internal class |
| During Maven plugin execution | Mojo, plugin realm, plugin dependencies | `PluginExecutionException`, `ClassNotFoundException` |
| During a compile task | Compiler/toolchain, processors, source level | `invalid target release` or processor failure |
| During a test task | Test runner, mocking/agents, test JVM | Discovery failure, bytecode instrumentation error |
| During code generation | Generator/tooling and schema inputs | Main class not found, outputs not registered |
| During package/shadow/shade | Archive API, resource merging, bytecode tooling | Lost service metadata, unrecognized class version |
| Only on CI | JDK/OS/scripts/cache/environment | `JAVA_HOME`, path quoting, credentials, daemon |
| Only in production | Application runtime/dependencies | Linkage error from the packaged JAR |

An error message may surface at a later task while originating from an earlier configuration phase. Read the *first stack trace* and the full `Caused by` chain rather than looking only at the last line.

## 3. Inventorying the build before changing versions

### 3.1. Files to identify

For Maven, typically:

```text
.mvn/wrapper/maven-wrapper.properties
.mvn/maven.config
.mvn/jvm.config
pom.xml
parent-pom/pom.xml
module-a/pom.xml
module-b/pom.xml
settings.xml (if managed separately in CI/user)
```

For Gradle:

```text
gradle/wrapper/gradle-wrapper.properties
settings.gradle or settings.gradle.kts
build.gradle or build.gradle.kts
gradle.properties
gradle/libs.versions.toml
buildSrc/
build-logic/ or included builds
convention-plugins/
init scripts in CI/user Gradle home
```

In addition, inspect shell scripts, PowerShell, batch files, Dockerfiles, CI pipelines, container images, code generation tasks, publication configs, and quality gates.

This is a methodological checklist of places to survey. In each real task, read/touch only files within authorized permissions and appropriate scope; do not assume every repository has this structure.

### 3.2. Plugin inventories must describe multiple dimensions

A useful inventory table:

| Plugin/task | Current version | Declaration source | Running JVM | API dependencies | Owner |
|---|---|---|---|---|---|
| Compiler plugin | From parent/pluginManagement | Maven build | Maven JVM or compiler fork | Maven Compiler API, `javac` | Build team |
| Test runner | Pinned directly | Maven/Gradle | Forked test JVM | JUnit, agents, instrumentation | QA |
| Shadow/shade | Plugin portal/repo | Build runtime | Gradle Daemon/Maven JVM | Archives, transformers | Platform |
| XJC/OpenAPI codegen | Build plugin | Generator JVM | External tool | JAXB, schemas | Domain team |
| Internal conventions | Included build or artifact | Gradle Daemon | Gradle API, Kotlin/Groovy DSL | Build platform |
| Release/publish | CI profile | Build runtime/CI | Repository credentials, signing | Release team |

Record plugins that are **applied indirectly** as well. A parent POM may automatically configure lifecycle plugins; a Gradle settings plugin or convention plugin may apply other plugins. A version catalog may define aliases, yet actual resolved versions still depend on the plugin management strategy.

### 3.3. Reference investigation commands

Maven:

```bash
./mvnw -version
./mvnw help:effective-pom
./mvnw help:effective-settings
./mvnw dependency:tree
```

Gradle:

```bash
./gradlew --version
./gradlew projects
./gradlew help --stacktrace
./gradlew buildEnvironment
```

Note that these are illustrative commands for use in the migration process, **not instructions to run immediately while authoring documentation**. On Windows, use `mvnw.cmd` or `gradlew.bat` as appropriate. `buildEnvironment` reflects some buildscript classpaths, yet is insufficient to describe all plugins from the Plugin DSL or included builds; inspect `pluginManagement` and each plugin declaration to complete the inventory.

## 4. Upgrade ordering: do not change everything at once

One way to reduce risk is to split the progression:

1. **Capture baseline:** old JDK, Wrapper, plugin versions, dependency graph, tests/reports, and artifact checksums.
2. **Define target matrix:** build-running JDK, compiler JDK, runtime JDK, Maven/Gradle, and plugins.
3. **Upgrade Wrapper if needed:** choose a distribution supporting the target JVM and approved by the organization.
4. **Upgrade external plugins:** compiler, test, codegen, shading, quality/security, publish.
5. **Fix internal plugins and build scripts:** replace deprecated/removed APIs/DSL, lifecycle hooks, and lazy configuration.
6. **Verify configuration and compilation:** main modules, tests, and generated sources.
7. **Verify packaging and runtime:** run the real artifact on the target JDK.
8. **Add CI matrix, rollback, and guardrails:** preserve evidence per commit.

Some steps may have to be combined because a new plugin requires a newer build tool, and a newer build tool only supports certain JDKs. Document **dependencies between upgrade steps** before deciding the order; do not assume plugins can be upgraded independently in every scenario.

The goal is reducing the number of variables changing simultaneously, not rigidly retaining an end-of-life old tool.

## 5. Upgrading the Gradle Wrapper and JDK compatibility

### 5.1. The Wrapper anchors the Gradle version

The `gradle/wrapper/gradle-wrapper.properties` file defines the distribution URL:

```properties
distributionUrl=https\://services.gradle.org/distributions/gradle-<approved-version>-bin.zip
```

`<approved-version>` is a placeholder. Do not blindly replace it with an arbitrary version number and assume it works. Cross-check the support matrix for the **JDK running Gradle** against **toolchain/compiler JDKs supported** by the target Gradle version.

Across Gradle releases, support for using a JDK as a toolchain can arrive before support for running the Gradle Daemon itself on that JDK. Therefore, the questions "Can this Gradle compile Java 21?" and "Can this Gradle run on Java 21?" may have different answers.

### 5.2. Wrapper update process

In environments where builds can be executed, typically use the Wrapper task provided by Gradle:

```bash
./gradlew wrapper --gradle-version <approved-version>
```

Depending on the old Wrapper's state, you may need a compatible JDK to boot the old Gradle before updating. Inspect and commit the generated Wrapper changes (scripts, JAR, and properties) according to repository policy; do not commit only the URL if the process requires keeping Wrapper files in sync.

In environments with supply-chain policies, configure and verify distribution checksums (for example `distributionSha256Sum` if supported) per official documentation, verify the source URL, and avoid using distributions not approved by the organization.

### 5.3. Do not force Daemon and compiler to always share the same JDK

A safe configuration when needing to support a Java 17 application while using a JDK 21 compiler can be:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

Verify that the Gradle version runs on the selected Daemon JDK while also supporting a Java 21 toolchain. `options.release` constrains language/bytecode/platform APIs for that Java source compilation, yet does not adjust plugin binaries or separate Kotlin/Groovy compiler tasks.

### 5.4. Signs the Gradle Wrapper is too old

- The build fails as soon as the daemon starts on the new JDK.
- Groovy/ASM inside the distribution does not understand the JDK's class-file major version.
- The Plugin DSL or Kotlin DSL fails to compile due to an unsupported Gradle/JDK combination.
- Java toolchains fail to recognize the new JDK.
- Warnings or errors for APIs removed across multiple major versions.
- Configuration cache or property validation is incompatible with current scripts/plugins.

Do not fix these errors by lowering the application's source/target compatibility; they reside in the build runtime and build tool API layer.

## 6. Maven Wrapper, Maven runtime, and plugin compatibility

### 6.1. Maven Wrapper and Maven core

The Maven Wrapper helps the repository lock down the selected Maven version. However, Maven core has a minimum supported Java version, and individual plugins have their own minimum Java/Maven versions. Verify three conditions:

1. The Maven distribution can run on the target JDK.
2. The plugin version supports the Maven core in use.
3. The plugin and its dependencies can run on Maven's JVM.

For example, a new Maven plugin compiled with Java 21 cannot run inside a Java 17 Maven JVM merely because the application compiler uses a Java 21 toolchain.

### 6.2. PluginManagement is not dependencyManagement

A Maven dependency BOM typically manages project dependencies; plugin versions belong in `pluginManagement` or `build/plugins`.

```xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>${compiler.plugin.version}</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>${surefire.plugin.version}</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
```

These properties are placeholders that must be defined, with versions chosen according to the JDK/Maven/framework compatibility matrix. If a plugin is not activated under `build/plugins` or a matching lifecycle binding, merely declaring `pluginManagement` does not guarantee all goals will run.

### 6.3. Compiler Plugin: decoupling build JDK from target release

Example:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

When the compiler runs on an appropriate JDK supporting `--release`, this configuration targets Java 17 class files and APIs. However, the compiler plugin version still needs Maven/JDK compatibility, and annotation processors may execute inside the compiler process with their own compatibility constraints.

If the application needs Java 21 APIs, select release 21 and verify consumer modules. Do not set `release=17` and try to call `Thread.ofVirtual()` by hacking the bootclasspath.

### 6.4. Surefire and Failsafe

Maven Surefire/Failsafe need versions supporting the test framework, target JVM, and fork mechanism. Common issues include:

- Tests are not discovered due to a mismatched JUnit Platform/provider.
- The forked JVM fails as soon as it loads test agents or bytecode instrumentation.
- Old plugins do not understand new JVM options or class-file versions.
- The test process unexpectedly uses a different JDK than Maven's JVM.
- `argLine` is not passed properly after adding JaCoCo or instrumentation.
- Integration tests do not run because execution phases or plugin configurations changed.

A "SUCCESS" build running **0 tests** does not prove compatibility. Inspect test reports, test counts, skipped tests, and which tasks/goals actually executed.

## 7. Upgrading external Gradle plugins

### 7.1. Plugin DSL and plugin repositories

A Gradle project may declare:

```groovy
plugins {
    id "com.example.static-analysis" version "2.4.0"
}
```

The plugin/version example is hypothetical. Plugin resolution can go through the Gradle Plugin Portal, a corporate mirror, or custom repositories configured in `settings.gradle(.kts)` under `pluginManagement`:

```groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
        maven {
            url = uri("https://repo.example.org/gradle-plugins")
        }
    }
}
```

The repository URL in the example is purely illustrative. In practice, use official URLs, credentials, and policies. If a plugin marker artifact is not published or a mirror lacks the marker/module, Gradle may report the plugin missing even though the implementation JAR exists.

### 7.2. Version catalogs for plugin aliases

```toml
[versions]
quality-plugin = "2.4.0"

[plugins]
quality = { id = "com.example.static-analysis", version.ref = "quality-plugin" }
```

In the build script:

```kotlin
plugins {
    alias(libs.plugins.quality)
}
```

Version catalogs reduce how many places versions are typed; they do not automatically solve Gradle API compatibility, runtime JDK requirements, or version conflicts inside the plugin classpath.

### 7.3. When upgrading a plugin across major versions

Read release notes and verify:

- Minimum Gradle version and JDK running the plugin.
- Whether the plugin ID changed.
- Whether extension/task/property names changed.
- Whether old tasks were removed or replaced.
- Whether configuration names and default behaviors changed.
- Whether the plugin migrated from eager to lazy property APIs.
- Whether report paths/output types, publication formats, or cache behavior changed.
- Whether the plugin still supports multi-module projects and the configuration cache.

Do not simply change the version and apply every "quick fix" suggested online without knowing how the plugin participates in the lifecycle.

## 8. Legacy Gradle APIs and migration to the Provider API

### 8.1. Errors caused by deprecated or removed Gradle APIs

Gradle evolves its DSL and APIs across releases; custom plugins may use legacy properties, methods, or conventions that are no longer supported. Common patterns:

- Accessing `Project` and the task model at inappropriate configuration times.
- Using `afterEvaluate` to patch tasks created by another plugin.
- Using deprecated task/property APIs.
- Creating tasks eagerly across many subprojects.
- Reading environment state and files during configuration without declaring inputs.
- Writing outputs directly into source directories without declaring outputs.
- Manually building the task graph via `dependsOn` with hardcoded task names or paths.

Not every pattern is strictly forbidden. However, when upgrading Gradle, migrate to recommended APIs and clearly separate **configuration time** from **execution time**.

### 8.2. Avoiding eager task creation when unnecessary

Old style:

```groovy
task generateInfo {
    doLast {
        println "Generating..."
    }
}
```

A more modern approach:

```groovy
tasks.register("generateInfo") {
    group = "generation"
    description = "Generate a build-info file"

    doLast {
        println "Generating..."
    }
}
```

`tasks.register` creates a task provider and generally enables lazy configuration. When code needs to reference a task, prefer providers rather than forcing early task realization.

Example:

```groovy
def generateInfoTask = tasks.register("generateInfo") {
    doLast {
        println "Generating..."
    }
}

tasks.named("processResources") {
    dependsOn(generateInfoTask)
}
```

This illustrates a task dependency. If a task produces a file and another task consumes it, model the output/input providers instead of only using `dependsOn` without specifying the artifact.

### 8.3. Explicit task inputs/outputs

An internal plugin that creates a file can define a task type:

```java
import org.gradle.api.DefaultTask;
import org.gradle.api.file.RegularFileProperty;
import org.gradle.api.provider.Property;
import org.gradle.api.tasks.Input;
import org.gradle.api.tasks.OutputFile;
import org.gradle.api.tasks.TaskAction;

public abstract class GenerateBuildInfo extends DefaultTask {
    @Input
    public abstract Property<String> getApplicationName();

    @OutputFile
    public abstract RegularFileProperty getOutputFile();

    @TaskAction
    public void generate() throws java.io.IOException {
        java.io.File file = getOutputFile().get().getAsFile();

        java.nio.file.Files.createDirectories(
            file.toPath().getParent()
        );

        String value = getApplicationName().get() + System.lineSeparator();

        java.nio.file.Files.writeString(
            file.toPath(),
            value,
            java.nio.charset.StandardCharsets.UTF_8
        );
    }
}
```

When applying the plugin:

```java
project.getTasks().register(
    "generateBuildInfo",
    GenerateBuildInfo.class,
    task -> {
        task.getApplicationName().set("order-service");
        task.getOutputFile().set(
            project.getLayout()
                .getBuildDirectory()
                .file("generated/build-info.txt")
        );
    }
);
```

This pattern tells Gradle about inputs and outputs for better change tracking. However, to make the task compatible with configuration cache/build cache, check all state, filesystem interactions, and how providers are passed into the task. A task with valid inputs/outputs is not automatically cacheable.

### 8.4. Why `project` inside a task action causes problems

A closure/task action directly referencing `project`, the script instance, or non-serializable objects can violate Gradle configuration cache requirements. Modern plugins should pass needed data through typed properties and providers rather than accessing the model at execution time.

Instead of:

```groovy
tasks.register("badTask") {
    doLast {
        println project.name
    }
}
```

produce input values during the configuration phase and use properties on the task type or providers according to supported APIs. Implementation details should be checked against the Gradle version, as certain closure forms and implicit captures behave differently across Groovy DSL, Kotlin DSL, and plugin code.

## 9. Configuration cache, build cache, and incremental builds

### 9.1. Three different concepts

- **Configuration cache** saves the build configuration outcome so compatible subsequent runs do not have to reconfigure the entire project.
- **Build cache** can reuse outputs of cacheable tasks given equivalent inputs.
- **Incremental build** skips or processes only changed portions when task inputs/outputs meet conditions unchanged.

A plugin may run fine normally yet fail when configuration cache is enabled because it holds references to `Project`, reads untracked environment state, or accesses configuration state inside a task action.

### 9.2. Plugin behaviors prone to breaking caching

- Reading environment variables or configuration files during configuration without declaring proper dependencies.
- Using static mutable state to store information across builds.
- Retaining `Project`, `Gradle`, or unsupported services inside task actions.
- Executing external processes without declaring inputs/outputs.
- Creating files during the configuration phase.
- Writing directly to source directories or another task's outputs.
- Depending on unmanaged timestamps or network responses.
- Using listeners/callbacks incompatible with the Gradle version/cache mode.

Do not fix this by permanently disabling all caching if the long-term goal is reproducibility and speed. You may temporarily disable it with documented risk to unblock migration, while keeping a backlog item to upgrade the plugin and re-verify per policy.

### 9.3. Modeling external tool execution

If a task invokes XJC, protoc, OpenAPI Generator, or another CLI, explicitly model:

- Executable/tool version.
- Tool classpath or executable location.
- Input schemas/configs.
- Output directory.
- JDK or runtime used to run the tool.
- Environment variables affecting output.
- Working directory and encoding.
- Unavoidable external network sources.

A task with undeclared side effects may be cached incorrectly or execute unexpectedly when Gradle reshapes the task graph.

## 10. Upgrading internal Gradle plugins

### 10.1. Three common forms

| Form | Characteristics | Migration risk |
|---|---|---|
| `buildSrc` | Automatically participates in repository build logic | Changes can affect every project; separate compile JDK |
| Included build `build-logic` | Separate build supplying convention plugins | Own plugin API/JDK and dependencies |
| Published binary plugin | Artifact with plugin marker and implementation JAR | Binary compatibility, repository, classloader, release management |

Precompiled script plugins are also build logic. Kotlin/Groovy DSL inside them may need syntax or dependency upgrades when embedded Gradle/Kotlin versions change.

### 10.2. Build logic needs its own version matrix

For example, an organization runs the Gradle Daemon on JDK 17 while using a JDK 21 toolchain for the application. If build logic is compiled to bytecode 21, the JDK 17 Gradle Daemon cannot load the plugin.

Therefore, for published internal plugins, record:

- Minimum JDK to run the plugin.
- Supported Gradle version range.
- Java/Groovy/Kotlin bytecode target of the plugin.
- Gradle API version the plugin is compiled/tested against.
- Internal dependencies of the plugin, especially ASM, Kotlin, and Groovy.
- Whether Gradle internal APIs are used.
- Test matrix against supported Gradle versions.

Do not conflate the application's Java target with the plugin's Java target. They may differ, and plugin policies often need to support multiple projects/runtimes.

### 10.3. Plugin IDs and semantic versioning

If an internal plugin is published:

```groovy
plugins {
    id "com.example.build.java-conventions" version "3.0.0"
}
```

then the plugin ID and version form the interface with consumers. Changing the plugin ID prevents consumers from resolving the plugin without updating build scripts; renaming tasks/extensions is also a source/build-script breaking change.

Plugin versioning requires migration notes much like a library API:

- Plugin ID and marker artifact.
- Minimum Gradle/JDK requirements.
- Old/new extension DSL.
- Task names, arguments, and lifecycle changes.
- Default configurations.
- Binary compatibility with build logic consumers.
- Publishing/mirror requirements.

### 10.4. Avoiding reliance on Gradle internal APIs

Plugins may have used classes under `org.gradle.internal.*` or unstabilized private APIs. When Gradle increments major versions, these classes/methods may change or be removed, throwing `NoClassDefFoundError`/`NoSuchMethodError` right at apply time.

The durable fix is moving to public Gradle APIs or supported extension points. Using reflection into internal APIs or `--add-opens` to force an old plugin to run is a high-risk stopgap, not a long-term strategy.

### 10.5. Convention plugins instead of repeated scripts

If multiple modules copy the same build script blocks, extract the configuration into a convention plugin:

```groovy
// Illustrative structure in an internal plugin
class JavaConventionsPlugin implements Plugin<Project> {
    void apply(Project project) {
        project.getPluginManager().apply("java");

        project.getTasks().withType(JavaCompile.class)
            .configureEach(task ->
                task.getOptions().getRelease().set(17)
            );
    }
}
```

Import the Gradle API classes and configure plugin packaging properly. The example code illustrates the concept, not a complete implementation for every Gradle version.

The benefit is a single place controlling JDK policy, compiler flags, test conventions, and report outputs. The risk is that all modules depend on this plugin simultaneously; changes need test fixtures and versioned rollout.

## 11. Upgrading internal Maven plugins

### 11.1. A Maven Mojo is code running in a plugin runtime

An internal plugin typically uses the Maven Plugin API/annotations to declare goals (Mojos). Example:

```java
import org.apache.maven.plugin.AbstractMojo;
import org.apache.maven.plugin.MojoExecutionException;
import org.apache.maven.plugins.annotations.Mojo;
import org.apache.maven.plugins.annotations.Parameter;

@Mojo(name = "report-build-info")
public class ReportBuildInfoMojo extends AbstractMojo {
    @Parameter(property = "app.name", defaultValue = "unknown")
    private String applicationName;

    @Override
    public void execute() throws MojoExecutionException {
        getLog().info("Application: " + applicationName);
    }
}
```

The example code must reside in a Maven plugin project with appropriate packaging, annotations, and plugin descriptor generation.

When upgrading Maven/JDK, an internal plugin may fail because:

- The plugin's compile target is higher than the JVM running Maven.
- It uses incompatible Maven core/internal APIs.
- The plugin descriptor is not generated or does not match the goal.
- Plugin dependencies conflict inside the plugin realm.
- Reflective access to JDK internals is blocked.
- How projects/sessions/repositories are read changed.
- Generators or process invocations depend on an old OS/JDK.

### 11.2. Managing plugin-specific dependencies

Example of a Maven plugin with its own `pom.xml` containing:

```xml
<packaging>maven-plugin</packaging>

<dependencies>
    <dependency>
        <groupId>org.apache.maven</groupId>
        <artifactId>maven-plugin-api</artifactId>
        <version>${maven.plugin.api.version}</version>
        <scope>provided</scope>
    </dependency>
    <dependency>
        <groupId>org.apache.maven.plugin-tools</groupId>
        <artifactId>maven-plugin-annotations</artifactId>
        <version>${plugin.annotations.version}</version>
        <scope>provided</scope>
    </dependency>
</dependencies>
```

This is only an illustrative structure; versions must be chosen based on supported Maven core/plugin tooling. Do not grab an arbitrary `maven-plugin-api` version solely because the production application uses JDK 21.

Plugin dependencies run inside the plugin realm, distinct from the dependencies of the consuming project. A library missing in the plugin realm is not necessarily resolved by adding it to the project `<dependencies>`.

### 11.3. Plugin tests and Invoker tests

An internal plugin should have:

- Unit tests for standalone logic.
- A plugin testing harness or suitable fixture creating mock Maven projects/sessions.
- Maven Invoker-style integration tests running the plugin on a real fixture project.
- Tests across declared supported Maven/JDK versions.
- Tests for malformed/missing configs, multi-module setups, inherited POMs, and execution phases.
- Artifact publication/plugin descriptor tests.

Do not merely test `execute()` with mocks and conclude the plugin will load properly on a new Maven release. Run at least one real consumer fixture.

## 12. Groovy and Kotlin DSL when upgrading Gradle

### 12.1. Groovy DSL can mask errors until configuration runtime

Groovy build scripts have dynamic dispatch capabilities. An old property or method is sometimes only caught when the script executes on a new Gradle version:

```text
Could not find method someOldConfiguration() for arguments ...
```

When seeing this error, check changed task/plugin DSLs, owner objects, plugin application order, and version compatibility. Do not assume this is a Java source error.

### 12.2. Kotlin DSL has static typing yet still depends on Gradle APIs

Kotlin DSL is compiled with the embedded Kotlin compiler/APIs of the Gradle distribution. When Gradle is upgraded, Kotlin DSL type-safe accessors, APIs, or old imports may stop compiling.

Example idiom using a task provider:

```kotlin
tasks.register("showBuildInfo") {
    group = "help"

    doLast {
        println("Build info generated")
    }
}
```

If an accessor fails to appear, a plugin may not have been applied in the right place or a dynamically created extension may not support expected accessors. Do not assume every Kotlin DSL failure is a Kotlin language version error.

### 12.3. Avoid directly referencing DSL implementation details

If scripts access internal objects, private extensions, or global variables tied to plugin application order, a new build tool release may change behavior. Migrate to:

- Public extension/task APIs.
- Typed providers/properties.
- Lazy task registration.
- Explicit plugin dependencies and plugin application.
- Convention plugins instead of duplicated script magic.
- Version catalogs and version-pinned build logic.

There is no need to convert all Groovy DSL to Kotlin DSL during the same JDK upgrade. Migrating the DSL is a separate change that should only be combined if justified and verifiable.

## 13. Shell scripts, PowerShell, and CI pipelines

### 13.1. Scripts outside the build system can be sources of incompatibility

A project may not use any special plugins yet still have CI scripts hardcoding the JDK:

```bash
export JAVA_HOME=/opt/jdk8
$JAVA_HOME/bin/xjc ...
$JAVA_HOME/bin/wsimport ...
```

On JDK 11+, JAXB/JAX-WS tools are no longer bundled in the JDK; scripts must use external generators with managed versions. Similarly, scripts calling `jre/bin/java` or legacy Java tools may no longer fit the new JDK layout.

Other warning signs:

- `JAVA_HOME` or `PATH` gets overwritten in one stage.
- Using Linux commands inside PowerShell or `cmd.exe`.
- Unquoted paths containing spaces.
- Scripts assuming `bash` is available on Windows.
- Hardcoding Gradle cache/distribution paths.
- Renamed Gradle tasks while the pipeline still calls old names.
- Removed Maven goals/profiles or changed executions.
- Scripts passing unsupported Java options.
- Dockerfiles using a base JDK image while the runtime stage lacks CAs/certs/tools.

### 13.2. Consistent Wrapper usage

In repositories containing a Wrapper, prefer:

```bash
./gradlew build
./mvnw verify
```

On Windows:

```powershell
.\gradlew.bat build
.\mvnw.cmd verify
```

Wrappers pin the build tool distribution per repository. They do not automatically pin the JDK; the JDK must be managed via CI, Toolchains, or container images.

### 13.3. Quoting paths and handling exit codes

A well-written script passes paths as discrete arguments rather than concatenating shell strings arbitrarily. PowerShell example:

```powershell
$env:JAVA_HOME = "C:\Program Files\Java\jdk-21"
& "$env:JAVA_HOME\bin\java.exe" -version

if ($LASTEXITCODE -ne 0) {
    throw "Java command failed"
}
```

Note that `$LASTEXITCODE` reflects the most recent native process; in long scripts, check it immediately after the command being monitored. In Bash, `set -euo pipefail` can be used in appropriate contexts, while still managing expected non-zero exits, pipelines, and cleanup.

### 13.4. Do not hardcode secrets in scripts

Plugin publishing, artifact uploads, and signing require credentials. When upgrading plugins, authentication configurations may change. Never place tokens in `build.gradle`, `pom.xml`, CI logs, or source scripts.

Use secret stores, CI credentials, and appropriate provider/environment mechanisms. With Gradle, use the provider API to avoid reading credentials prematurely. With Maven, use settings/server credentials per organizational policy.

## 14. Code generation plugins and annotation processing

### 14.1. Generators are a separate toolchain

XJC, JAX-WS, OpenAPI Generator, Protobuf, Avro, MapStruct, and annotation processors can each have:

- Plugin/CLI version.
- Runtime JDK requirement.
- Input schema/API version.
- Generated source language level.
- Runtime dependencies of generated code.
- Build plugin execution phase/task.
- Generated output directory.

Upgrading the JDK can prevent old generators from running, or cause new generators to emit sources using APIs/annotations mismatched with the runtime. For instance, a Jakarta generator emits `jakarta.*` imports while application dependencies still use `javax.*`.

### 14.2. Generated sources must reside in source roots

Maven plugins can attach generated sources to compile source roots; Gradle tasks should supply the output directory to a source set or compiler task.

In Gradle, the idea:

```groovy
def generateApi = tasks.register("generateApi") {
    def outDir = layout.buildDirectory.dir("generated/sources/api/main")
    outputs.dir(outDir)

    doLast {
        // Invoke the code generation tool at execution time,
        // and write to the declared outDir.
    }
}

sourceSets {
    main {
        java.srcDir(layout.buildDirectory.dir("generated/sources/api/main"))
    }
}

tasks.named("compileJava") {
    dependsOn(generateApi)
}
```

This is merely a task dependency model; actual implementations need defined inputs, tool classpaths, and no `project` access inside task actions if configuration cache compatibility is desired. Prefer maintained generator plugins with public APIs.

### 14.3. Do not keep dirty generated outputs

A build that previously generated old files may continue compiling because outputs were never cleared. Clean CI fails because the new generator no longer emits those files. During migration, test a clean build in an isolated environment.

If generated sources are committed to the repository, enforce the tool version and a reproducible regeneration workflow, avoiding direct edits to generated files that get overwritten on the next build.

## 15. Testing and instrumentation plugins on newer JDKs

### 15.1. Bytecode libraries that cannot parse new class-file versions

Mocking frameworks, JaCoCo, Byte Buddy, ASM, Groovy/Kotlin compilers, coverage/instrumentation plugins, and agents can read or rewrite bytecode. When the JDK is upgraded, new class-file major versions may exceed older tooling capabilities.

Symptoms can appear as:

```text
Unsupported class file major version 65
```

Java 21 uses class-file major version 65. However, this error may occur because the **tool reading the class file** does not yet support major version 65, not necessarily because the runtime JVM lacks support for that class.

How to handle:

1. Identify which library/plugin is reading class files.
2. Check actual versions on the plugin/test classpath.
3. Choose a tooling version supporting the target JDK/bytecode.
4. Check for transitive dependency conflicts on ASM/Byte Buddy.
5. Re-run coverage/mocking/test instrumentation on real class files.

Do not force application bytecode down to Java 17 just to avoid upgrading a plugin if the product genuinely needs Java 21 features.

### 15.2. Java agents and dynamic attach

Modern JDKs introduce policies and warnings around dynamic agent loading. On JDK 21, JEP 451 warns about dynamic loading of agents in certain scenarios. Some test libraries rely on dynamic attach for inline mocking or instrumentation.

Distinguish:

- Startup agents configured via `-javaagent`.
- Dynamic agent attachment while the JVM is already running.
- Whether the agent library supports the target JDK version/bytecode level.
- Whether CI/container policies allow attachment.

Do not suppress security warnings or broadly grant attach permissions without verifying actual test framework requirements. Prefer compatible framework/agent versions and configure startup agents when recommended by the vendor.

### 15.3. Java 21 test compatibility is more than just JUnit

If the new JUnit Platform works while old JaCoCo fails, or coverage passes while the Mockito agent errors out, upgrade those components individually. Plugins do not share a single release lifecycle and cannot be solved solely by an application BOM if plugin realms differ.

## 16. Quality, formatting, linting, and publishing plugins

### 16.1. Static analysis

Checkstyle, PMD, SpotBugs, Error Prone, Sonar tooling, and similar tools vary in how they analyze source and bytecode. As the source level increases:

- Tool parsers may not recognize new language syntax.
- Bytecode analyzers may not understand new class-file versions.
- Legacy rule configurations may be deprecated/removed.
- Baseline suppression files may no longer be accepted.
- Minimum runtime JDK requirements of the tool change.

Do not turn off the entire quality gate just because an old tool does not yet support the JDK. Separate the roadmap for updating rules and tool versions, capture warning baselines, and address identified changes.

### 16.2. Formatting

A formatter major-version bump may alter the output of hundreds of files even though source semantics remain unchanged. Separate format-only commits from compatibility commits when feasible; pin the formatter version, IDE integrations, and CI hooks consistently.

If separation is impossible, document the formatting scope clearly and avoid conflating massive formatting diffs with logic changes.

### 16.3. Shading, shadowing, and packaging

Plugins building fat JARs/uber-JARs may:

- Change task names or archive property APIs.
- Change `META-INF/services` merging behavior.
- Cause duplicate class conflicts.
- Relocate packages differently than before.
- Strip `Signature`, module metadata, or manifest attributes.
- Fail to recognize new class-file versions during transformation.
- Overwrite artifact/publishing configurations.

After upgrading a packaging plugin, inspect the actual artifact: JAR contents, classpaths, services, module descriptors, startup behavior, and integration tests. A successful build does not prove the runtime JAR is valid.

### 16.4. Publishing and signing

Publishing plugins can change default repositories, credential APIs, publication metadata, POM/BOM conversions, or signing behaviors. Confirm:

- Group/artifact/version and classifiers.
- Generated Gradle Module Metadata/Maven POMs.
- Checksums/signatures and SBOM if applicable.
- Repository URLs, staging, and release/snapshot policies.
- Consumers' ability to resolve artifacts from mirrors.
- Not accidentally publishing test/generated files or files containing secrets.

Do not assume the publish step is safe merely because the script worked previously. Use staging/test repositories per procedure when changing release plugins.

## 17. Diagnosing common failures

| Symptom | Common root-cause area | First step to take |
|---|---|---|
| Gradle fails to start on JDK 21 | Wrapper/distribution does not support the JVM running Gradle | Check Gradle-JDK support table, use an approved Wrapper |
| `UnsupportedClassVersionError` when applying plugin | Plugin compiled for a newer JDK than Daemon/Maven JVM | Check plugin major version and executing JVM |
| `NoSuchMethodError` with `org.gradle.*` | Plugin calls old/mismatched Gradle API | Identify plugin, upgrade or fix to use public APIs |
| `NoClassDefFoundError` in Maven plugin | Missing dependency in plugin realm or mismatched plugin binary | Read full `Caused by` and plugin dependencies |
| `Could not find method ...` in Gradle | Outdated DSL/API/plugin extension | Check release notes and plugin apply order |
| `UnknownPluginException` | Wrong plugin ID/marker/repository | Check `pluginManagement` and repository mirrors |
| `invalid target release: 21` | Actual compiler is not JDK 21 | Check toolchains and process JDK |
| `Unsupported class file major version 65` in coverage | Old bytecode tool | Upgrade agent/ASM/Byte Buddy/coverage plugin |
| Zero tests execute | Wrong test provider/framework/lifecycle | Check test reports, tasks/goals, and test count |
| `Permission denied` on `gradlew` | Script executable bit or environment | Check file mode and CI shell |
| `xjc`/`wsimport` not found | Newer JDK no longer bundles tool | Use a version-pinned external generator |
| Configuration cache failure | Task/plugin retains invalid state | Fix Provider API usage and task inputs |
| CI fails, local passes | Different JDK/OS/environment/credentials | Compare environment matrix, wrapper, and clean build |
| Fat JAR fails at runtime yet unit tests pass | Packaging/shading/provider metadata | Inspect final artifact and runtime classpath |
| Plugin publish authentication error | Credential/repository config changed | Check secret injection and policies, never log tokens |

These are investigative starting points, not absolute root-cause mappings. Always read the exact error and check actual versions.

## 18. Process for handling an incompatible plugin

### Step 1: Identify the exact plugin causing the failure

Capture the first exception with its full stack trace. Identify the plugin ID, group/artifact/version, task/goal, plugin realm/classloader, and the JDK running it.

Gradle typically supports:

```bash
./gradlew <task> --stacktrace --info
```

Maven typically supports:

```bash
./mvnw <goal> -e
```

More verbose debug modes can expose paths, repositories, metadata, and sometimes secrets, so use them only in controlled environments.

### Step 2: Check the plugin's compatibility matrix

Read minimum/maximum Gradle/Maven/JDK requirements, release notes, and migration guides. Do not pick a version solely by the highest number; pick a version **supported by the targeted stack**.

### Step 3: Classify the failure category

- Binary plugin cannot load.
- Plugin loads, yet configuration DSL fails.
- Task execution fails.
- Generated output is incorrect.
- Test/package/publish output changed.

Each category requires a different fix. For instance, a plugin binary failing to load cannot be fixed by changing the main module's `sourceCompatibility`.

### Step 4: Evaluate patching directly vs. replacing the plugin

If a third-party plugin is unmaintained:

1. Is there a fork/vendor-patched version supported by the organization?
2. Is there a maintained replacement plugin supporting the target stack?
3. Can the logic move to standard Gradle/Maven APIs?
4. Which output contracts must remain intact so consumers are unaffected?
5. Are there legal, copyright, licensing, or security risks to using a fork?

If replacing a plugin, treat it as a **tooling and output semantics change**, not just swapping coordinates.

### Step 5: Define build script changes

Update extensions/properties/tasks/goals, remove deprecated APIs, and adopt lazy configuration and updated build logic. With Gradle, prefer public Provider/Property APIs. With Maven, update plugin executions and lifecycle bindings.

### Step 6: Verify layer by layer

- Plugin resolution.
- Plugin apply/configure.
- Task/goal execution.
- Outputs generated accurately.
- Source/generated source compilation.
- Test framework/coverage execution.
- Artifact packaging.
- Runtime smoke/integration tests.
- Publication metadata if applicable.

### Step 7: Document migration notes and rollback

Record old/new versions, reasons for change, breaking DSL changes, altered outputs, renamed tasks, test reports, and rollback instructions. Plugins are typically shared by many modules, so notify internal consumers.

## 19. End-to-end example: internal Gradle plugin after a JDK upgrade

Suppose a repository contains multiple services using the `com.example.build.java-conventions` plugin. Baseline: older Gradle, Daemon on JDK 17, application target Java 17. Goal: build on JDK 21 while targeting Java 21 for some services.

### 19.1. Symptom

After updating the Gradle Wrapper/JDK, the build reports an error similar to:

```text
java.lang.NoSuchMethodError:
  '... org.gradle.api.internal...someOldMethod(...)'
```

The method name in the example is a placeholder. The stack trace points to the internal plugin's JAR. This indicates the plugin is calling an internal/version-mismatched Gradle API.

### 19.2. Resolution approach

1. Identify the internal plugin version and the Gradle API it was compiled against.
2. Check for `org.gradle.internal.*` or deprecated APIs in the plugin source.
3. Replace them with public APIs, typed task properties, and provider wiring.
4. Pin the **plugin runtime** JDK/bytecode target separately from applications.
5. Test the plugin across declared supported Gradle distribution/JDK combinations.
6. Create a consumer fixture containing `compileJava`, `test`, `jar`, and custom codegen tasks.
7. Publish the new plugin version with migration notes.
8. Upgrade consumer services in batches, verifying clean CI builds and packaged artifacts.

If task names/extension properties must transition, keep aliases or deprecation bridges across a transition release. However, do not keep code calling removed Gradle internal APIs just to avoid updating consumers.

### 19.3. Separating plugin JDK from application JDK

Some services still need to run on Java 17. The Gradle plugin executes inside the selected Daemon JDK, while compiler tasks can use a JDK 21 toolchain with `options.release=17`. Ensure the plugin does not accidentally force every service to target Java 21 simply because the Daemon runs on 21.

Have the convention plugin read the release configuration from an explicit extension or convention rather than hardcoding versions based on the JVM running Gradle.

## 20. End-to-end example: legacy Maven plugin and code generator

A SOAP/JAXB project used to build on JDK 8 with a Maven plugin or script invoking `JAVA_HOME/bin/wsimport`. When moving to JDK 21, this tool no longer ships in the JDK and generated sources fail to appear.

A migration path:

1. Capture WSDL/XSD files, binding files, and the generated source baseline.
2. Select external tools such as JAX-WS RI tools or CXF codegen matching the framework.
3. Choose the `javax.*` or `jakarta.*` generation consistently with the runtime.
4. Configure the Maven plugin goal in the `generate-sources` phase.
5. Pin plugin/tool versions and generator dependencies.
6. Verify generated source roots, imports, and class names.
7. Recompile with the target JDK and run SOAP contract tests.
8. Check plugin publication and artifact dependency metadata if a shared client is published.

Switching generators can alter Java method signatures, annotations, or WSDL bindings; inspect diffs and consumer compatibility. Do not edit generated sources directly to hide the root cause.

## 21. CI matrix and release gates for build tool migration

### 21.1. Choosing a practical matrix

You do not need to test every combination of JDK/Maven/Gradle/plugins. However, include at least:

| Combination | Purpose |
|---|---|
| Old build tool + old JDK | Baseline for reproduction |
| New build tool + supported JDK | Verify plugins/DSL/tooling |
| New compiler JDK + old target release (if needed) | Maintain runtime compatibility |
| Target test JVM | JUnit/agent/coverage integration |
| Production runtime JDK | Run the final artifact |
| Windows/Linux (if both supported) | Shell/path/script portability |

If an internal plugin claims support for multiple Gradle releases, test it against every committed release line, not just the Gradle version of the plugin's own repository.

### 21.2. Gates before accepting an upgrade

1. Wrapper checksum/version and JDK are recorded.
2. Plugin resolution succeeds from approved repositories.
3. No plugin binary class-version errors occur.
4. Configuration phase is valid and uses no removed APIs.
5. Main, test, and generated sources compile cleanly.
6. Test counts/reports are valid; no silent skips occur.
7. Coverage/quality gates execute properly.
8. Artifacts package cleanly without losing `META-INF/services` or resources.
9. Runtime smoke/integration tests succeed on the target JDK.
10. Publication metadata/repositories are verified if the pipeline publishes.
11. No credentials/tokens are written to logs.
12. Release notes, rollback plans, or remediation plans exist.

### 21.3. Do not turn every deprecation warning into an infinite blocker

While upgrading Gradle or Maven, warnings may appear from third-party plugins lacking newer releases yet. Track warnings by owner, deadline, and severity. If a warning states an API will be removed in the next release, plan a replacement before the next upgrade.

Do not ignore warnings merely because the build passes; they provide crucial data for estimating the cost of the next migration cycle.

## 22. Plugin dependencies and supply-chain security

Build plugins have permission to execute code on the build machine, read files, use credentials, and access the network with process privileges. Therefore, upgrading plugins is not purely a compatibility decision, but also a supply-chain decision.

Apply:

- Deliberate plugin/version pinning.
- Repository allowlists and corporate mirrors.
- Checksum/signature verification when tooling supports it.
- Review of plugin source, maintenance status, and vulnerability history.
- Restricting CI runner privileges and secret exposure.
- Never executing uncontrolled remote scripts just to install a plugin.
- Build reproducibility from Wrapper/plugin/dependency versions.
- Separating publish credentials from compile/test-only jobs.

A new plugin that solves Java 21 compatibility yet has not had its provenance verified is not automatically a safe choice. Changes to plugin dependencies also require inspection, especially if a plugin pulls down additional toolchains or executes external binaries.

## 23. Checklist for upgrading plugins and scripts

### Inventory

- [ ] Identified the JDK running Maven/Gradle, compiler JDK, test JDK, and runtime JDK.
- [ ] Recorded Maven/Gradle Wrapper versions and distribution sources.
- [ ] Listed directly and indirectly declared plugins, including settings and convention plugins.
- [ ] Identified internal plugins in `buildSrc`, included builds, or artifact repositories.
- [ ] Checked CI scripts, shell scripts, PowerShell, Dockerfiles, and process JDKs.
- [ ] Documented the Gradle/Maven/JDK/plugin version compatibility matrix.

### Upgrading configuration and build code

- [ ] Selected Wrapper version supports the build-running JDK.
- [ ] Compiler, Surefire/Failsafe, test agents, and bytecode tools support the target JDK.
- [ ] Gradle plugins do not call removed internal/deprecated APIs.
- [ ] Tasks use lazy configuration and declare inputs/outputs where appropriate.
- [ ] Internal plugin configuration cache issues are recorded and addressed.
- [ ] Maven plugin realms/dependencies are verified separately from project dependencies.
- [ ] Generated sources and task wiring work from a clean checkout.
- [ ] Plugin IDs, extensions, and task/goal names have migration notes when changed.
- [ ] Shell scripts quote paths, handle exit codes, and do not hardcode removed tools.
- [ ] Credentials are managed via secret stores, never inside source code.

### Verification

- [ ] Verified actual tool/plugin versions on CI.
- [ ] Tested configuration/plugin application before running the application.
- [ ] Compiled main, test, and generated sources with the right compiler and target release.
- [ ] Checked test counts, reports, coverage, and quality gates.
- [ ] Inspected JAR/WAR/container artifacts after shading/packaging.
- [ ] Ran smoke/integration tests on the target runtime JDK.
- [ ] Ran plugin consumer fixtures for internal plugins.
- [ ] Verified builds across all supported OSes.
- [ ] Reviewed dependency/plugin repositories and artifact provenance.
- [ ] Archived baseline, build logs, versions, risk owners, and rollback plans.

## 24. Handoff record for the Prime/build platform team

A plugin/script upgrade cycle should include the following evidence:

1. **Version matrix:** old/new Maven/Gradle Wrapper, build/toolchain/test/runtime JDKs, framework, and plugin versions.
2. **Plugin inventory:** direct, transitive/applied, internal, settings, and generation/publish plugins.
3. **Compatibility rationale:** cross-checked JVM/build-tool support docs and release notes.
4. **Build script diff:** changed tasks/extensions/goals, replaced deprecated APIs.
5. **Internal plugin evidence:** plugin binary target, Gradle/Maven API usage, consumer fixtures, and test matrix.
6. **Generated code evidence:** tool versions, inputs, output snapshots, source roots.
7. **Resolved dependency graphs:** project runtime, plugin realms/classpaths, processor/tool configurations.
8. **Verification records:** clean configuration, compilation, test count, coverage, packaging, and runtime.
9. **Supply-chain review:** repositories, distribution/plugin verification, secret handling.
10. **Release plan:** owner, compatibility restrictions, rollout, rollback, and deadlines for removing workarounds.

**Conclusion:** Build plugins, internal plugins, and build scripts are software components that must be upgraded alongside Java, not mere "secondary configs." Maven/Gradle have their own runtimes; plugins have separate classpaths, versions, and API lifecycles; code generators, test agents, and CI scripts carry independent requirements. Separating these layers clearly, locking down a compatibility matrix, upgrading Wrappers/plugins in a controlled sequence, and verifying the **final artifact on the target JDK** prevents scenarios where source code is compatible yet build or release pipelines break.
