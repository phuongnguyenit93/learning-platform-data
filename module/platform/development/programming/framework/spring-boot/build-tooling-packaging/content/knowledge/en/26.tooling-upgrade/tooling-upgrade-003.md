# Reading Plugin, Task, Goal, and Default Configuration Changes

## 1. Why Can Upgrading a Tool Version Change Build Behavior?

When upgrading a Maven plugin, Gradle plugin, or Spring Boot build plugin, the change is not limited to the version number. A new plugin may:

- Add, remove, or rename a goal/task.
- Change the phase to which a goal is bound or change task dependencies.
- Add, remove, change the type of, or rename a configuration parameter.
- Change the default value of a parameter.
- Change how values are inferred from the project, source sets, toolchain, or environment.
- Change artifact location/name, manifest, classifier, archive layout, or output directory.
- Change skip conditions, incremental build, caching, validation, or error reporting.
- Drop support for an older Maven/Gradle/JDK version or legacy configuration.

A build can still report **BUILD SUCCESS** after a plugin upgrade yet produce a different artifact than before. For example, a task still runs while the archive classifier changes; a goal is still invoked while its default parameter changes; a main class previously discovered automatically is no longer inferred the same way after upgrading the plugin.

When reviewing tooling changes, answer four questions:

1. **Which plugin version is being resolved?**
2. **Which goals/tasks are registered and actually run?**
3. **Which configuration comes from the POM/build script, parent, settings, version catalog, or command line?**
4. **Which values are supplied automatically by the plugin/task when the project does not explicitly configure them?**

This guide focuses on Maven, Gradle, and Spring Boot 3.5.x, with Java 17 examples. Versions in the examples are illustrative only; read the documentation for the exact version you are using rather than taking defaults from the latest version's docs.

## 2. Distinguishing Plugin, Goal, Task, Phase, and Default

| Concept | Maven | Gradle | Meaning |
|---|---|---|---|
| **Build tool** | Maven | Gradle | Program orchestrating the build and dependencies |
| **Plugin** | Maven plugin | Gradle plugin | Extends the build tool, adding goals/tasks and configuration |
| **Goal** | Maven plugin Goal/Mojo | No direct equivalent concept | Functional unit of a Maven plugin, e.g., `repackage` |
| **Task** | Maven lifecycle executes goals by phase | Gradle task | Unit of work in the task graph, e.g., `bootJar` |
| **Phase** | `compile`, `test`, `package`, `verify` | No equivalent Maven phase sequence | Milestone in the Maven lifecycle to bind goals |
| **Task dependency** | Phase/execution and reactor relationships | `dependsOn` and task graph relationships | Determines what must run first |
| **Configuration** | XML configuration in the POM | DSL, extension, and task properties | Values supplied by the user to the plugin/task |
| **Default/convention** | Default value of a Mojo parameter | Convention/provider value of a task or extension | Value used when the project does not override it |

### 2.1. A Maven Plugin Goal Is Not a Maven Phase

A Maven plugin can provide multiple goals. For example, the Spring Boot Maven Plugin provides the **repackage** goal. That goal can be bound to the **package** phase via an execution:

```xml
<execution>
    <id>repackage-executable-archive</id>
    <phase>package</phase>
    <goals>
        <goal>repackage</goal>
    </goals>
</execution>
```

When running **mvn package**, Maven walks through the lifecycle and invokes goals bound to each corresponding phase. When invoking a goal directly, such as **mvn spring-boot:repackage**, you are asking that goal to run directly; do not assume all prior phases automatically run as they do with **mvn package**.

### 2.2. A Gradle Task Is a Node in the Task Graph

A Gradle plugin can register tasks such as **bootJar**, **bootWar**, **bootRun**. A task has:

- **Type:** the task implementation class, e.g., `BootJar`.
- **Inputs:** sources, classpath, configuration, and input files.
- **Outputs:** archives, reports, or generated files.
- **Dependencies:** tasks that must complete before it.
- **Properties:** configuration values such as main class, archive name, or classpath.

When running **./gradlew bootJar**, Gradle configures the project, constructs the task graph, and executes the necessary tasks. The task graph can change depending on plugins, project structure, and configuration.

### 2.3. Defaults and Conventions Do Not Always Appear in the Build File

If the POM does not declare `mainClass`, the Spring Boot Maven Plugin can auto-detect the main class according to plugin rules. If the Gradle build does not set a main class for `bootRun`, the Spring Boot Gradle Plugin can automatically find a class with a `public static void main(String[])` method in the main source set.

These are **values inferred/defaulted by the plugin**. The absence of a configuration line in the POM or `build.gradle` does not mean the value is null, empty, or unset.

> **Effective configuration** shows what configuration the build received; **plugin descriptors/documentation** show which parameters the plugin has and how defaults are defined; **logs or resolved task values** show what a specific build run actually used.

## 3. Multiple Configuration Layers Affect a Single Plugin

Before comparing two versions, locate where versions and configurations are declared. If you only look at the current module's `pom.xml` or `build.gradle`, you may miss inherited configuration.

### 3.1. Maven: Where Plugin Versions and Configurations Are Declared

Common sources:

1. Module POM: `build/plugins`.
2. Parent POM: inherited plugin configuration.
3. `pluginManagement`: manages default versions/configurations for plugins when those plugins are declared for use.
4. Super POM and lifecycle mappings: default plugins/goals attached to packaging types such as `jar` or `war`.
5. Active profiles: profiles can add plugins or override configuration.
6. Command line: `-Dproperty=value` arguments can override parameters if the plugin exposes a matching user property.

Example:

```xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <version>3.5.16</version>
                <configuration>
                    <mainClass>com.example.demo.DemoApplication</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </pluginManagement>

    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
```

In this example, `pluginManagement` provides the managed version and configuration; `plugins` declares that the plugin is used in the build. **Merely placing a plugin in `pluginManagement` does not mean the plugin executes automatically.**

If using `spring-boot-starter-parent`, the parent already provides many helpful plugin management settings and executions. If only importing the `spring-boot-dependencies` BOM in `dependencyManagement`, you are managing dependency versions; a BOM does not automatically perform the Spring Boot parent's role for all plugin executions.

### 3.2. Maven: Plugin-Level and Execution-Level Configuration

Plugin-level configuration can apply across the plugin's goals; execution-level configuration can fine-tune a single execution.

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <mainClass>com.example.demo.DemoApplication</mainClass>
    </configuration>
    <executions>
        <execution>
            <id>repackage-executable-jar</id>
            <phase>package</phase>
            <goals>
                <goal>repackage</goal>
            </goals>
            <configuration>
                <classifier>exec</classifier>
            </configuration>
        </execution>
    </executions>
</plugin>
```

In this example, `mainClass` is declared at the plugin level; `classifier` belongs to the `repackage` execution. When upgrading a plugin, check whether parameters still exist, whether their data types changed, and whether merge/inheritance rules changed.

Some Maven configurations support advanced merge attributes such as `combine.children` and `combine.self`. Use them only when you truly need to control merging between parent and child; inspect the effective POM first to understand the result.

### 3.3. Gradle: Plugin Versions Can Live in Multiple Files

Common sources:

- The `plugins` block in `build.gradle` or `build.gradle.kts`.
- The `pluginManagement` block in `settings.gradle(.kts)`.
- Plugin aliases and versions in `gradle/libs.versions.toml`.
- `buildscript` classpath in older builds.
- Convention plugins in `buildSrc` or an included build.

Groovy DSL example:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
}
```

Kotlin DSL example:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.16"
}
```

Version catalog example:

```toml
[versions]
springBoot = "3.5.16"

[plugins]
spring-boot = { id = "org.springframework.boot", version.ref = "springBoot" }
```

Modules can then use the alias instead of writing the version directly. When reviewing a version upgrade, read `settings.gradle(.kts)` and the version catalog as well, not just the module build script.

### 3.4. Gradle: Extensions and Task Properties Have Different Roles

Plugins often provide an **extension** for project-wide configuration and **task properties** to configure a specific task.

Spring Boot DSL example:

```groovy
springBoot {
    mainClass = 'com.example.demo.DemoApplication'
}
```

Configuring the task directly:

```groovy
tasks.named('bootJar') {
    mainClass = 'com.example.demo.DemoApplication'
}
```

Extension configuration can act as a convention source for tasks; configuring the task directly can override that value. When upgrading the plugin, check the new version's documentation for how the extension propagates values to tasks and which properties have been deprecated.

## 4. Defaults in Maven: Using help:describe

The Maven Help Plugin is a key tool for inspecting the goals and parameters of a specific plugin.

### 4.1. Listing Goals and Plugin Details

Example with Spring Boot Maven Plugin 3.5.16:

```bash
mvn help:describe \
  -Dplugin=org.springframework.boot:spring-boot-maven-plugin:3.5.16 \
  -Ddetail
```

This command displays the plugin's goals, implementation details, and parameters supported by each goal. To inspect the `repackage` goal specifically:

```bash
mvn help:describe \
  -Dplugin=org.springframework.boot:spring-boot-maven-plugin:3.5.16 \
  -Dgoal=repackage \
  -Ddetail
```

Read the fields:

- **Parameter:** parameter name.
- **Type:** data type.
- **Required:** whether it is mandatory.
- **User Property:** property that can be passed via `-D`.
- **Default:** default value described by the plugin.
- **Description:** meaning and constraints of the parameter.

Illustrative snippet of output from an arbitrary Mojo:

```text
Parameter: skip
Type: boolean
Required: No
User Property: example.skip
Default: false

Parameter: outputDirectory
Type: File
Required: No
Default: expression referring to the Maven project build directory
```

This is illustrative output explaining how to read the fields, not an assertion that these values are the defaults for every goal or every Spring Boot version. Capture the output from the exact plugin/version your project resolves.

### 4.2. Defaults Can Be Literals or Expressions

A plugin descriptor can define:

- Literal: `false`, `true`, a number, string, or enum.
- Expression: reference to project/session, e.g., the project build directory.
- Value computed by plugin code at runtime.
- Value injected by another component.

Therefore, when output shows an expression, understand the context in which it will be resolved. Do not copy an expression as a literal path or conclude the final value solely from the descriptor string.

### 4.3. Do Not Confuse the Help Plugin's Defaults with the Inspected Plugin's Defaults

The `help:describe` command involves two plugins:

- `maven-help-plugin`: the plugin executing the `help:describe` goal.
- The plugin passed in `-Dplugin=...`: the plugin you want to inspect.

The Help plugin version and the Spring Boot plugin version are two different things. For reliable comparisons, specify the exact target plugin version in `-Dplugin=groupId:artifactId:version`.

## 5. Maven: Inspecting Effective Configuration with the Effective POM

### 5.1. What Does the Effective POM Include?

The effective POM is the result Maven computes after applying:

- Current POM.
- Parent POM and inheritance.
- Properties/interpolation.
- Active profiles.
- Dependency management and plugin management.
- Merged build configuration.

Generate the file:

```bash
mvn help:effective-pom \
  -Dverbose \
  -Doutput=target/effective-pom.xml
```

`-Dverbose` asks the Help Plugin to add comments showing the origin of each XML element when available. This helps identify whether a configuration came from the module POM, parent, or a profile.

List active profiles:

```bash
mvn help:active-profiles
```

List all available profiles:

```bash
mvn help:all-profiles
```

### 5.2. The Effective POM Does Not Contain Every Default Injected by Plugins

This is a very easy mistake to make.

**The effective POM shows the merged Maven configuration**, such as plugin versions, executions, phases, and nodes inside `<configuration>`. It does not necessarily list every default value the plugin injects into the Mojo at execution time.

For example:

- The effective POM may not contain `mainClass`.
- The plugin descriptor may describe `mainClass` as optional.
- At runtime, the Spring Boot plugin can auto-detect the main class from compiled output.

These three facts do not contradict each other. They belong to three different layers: declared configuration, plugin metadata/defaults, and the actual value resolved at runtime.

To get the full picture, combine:

1. Effective POM.
2. `help:describe` for the exact plugin/version.
3. Plugin documentation and migration notes for that version.
4. Build logs and the resulting artifact after execution.

### 5.3. Checking Which Lifecycle Phase a Plugin/Goal Binds To

Use the Help Plugin to inspect lifecycle mappings:

```bash
mvn help:describe -Dcmd=package
mvn help:describe -Dcmd=verify
```

The output helps identify goals bound to phases based on the packaging type. If the project has custom executions, cross-check the effective POM and build logs since a single phase can run multiple goals.

### 5.4. Reading Actual Configuration in Debug Logs

When you need to confirm what Maven passes to a Mojo, use debug logging:

```bash
mvn -X -Dstyle.color=never package
```

Look for the plugin/goal name, execution id, and the configuration/mojo execution section. Debug logs can contain internal URLs, properties, paths, and credentials; protect logs and redact sensitive information before sharing.

**Do not rely solely on debug logs:** some values are computed inside plugin code or appear only in the output archive. Inspect the final artifact to confirm behavior.

## 6. Maven: Understanding User Properties, POM Configuration, and Executions

A plugin parameter can receive values from multiple sources. Exact precedence depends on how the plugin declares the parameter, user property, and Maven model.

### 6.1. Finding the Exact User Property

If `help:describe` displays:

```text
User Property: example.skip
Default: false
```

You can test overriding it with:

```bash
mvn package -Dexample.skip=true
```

This is a generic example. Only use properties actually published by the plugin. Do not guess property names; read the descriptor/documentation for the exact version.

### 6.2. Separating Configuration by Execution ID

A plugin can be invoked multiple times with different execution IDs. Example:

```xml
<executions>
    <execution>
        <id>repackage-service-jar</id>
        <phase>package</phase>
        <goals>
            <goal>repackage</goal>
        </goals>
        <configuration>
            <classifier>exec</classifier>
        </configuration>
    </execution>
</executions>
```

When logs show a goal running multiple times, read the execution ID to know which configuration applied. Do not just search for the goal name `repackage`, because the same goal can appear in another execution or be invoked directly.

### 6.3. Distinguishing Plugin Configuration from Dependency Versions

Maven has two areas that are easy to confuse:

- `dependencyManagement` manages dependency versions.
- `pluginManagement` manages plugin versions and plugin configuration.

Upgrading the Spring Boot dependency BOM does not necessarily upgrade the Maven plugin. Upgrading `spring-boot-maven-plugin` also does not automatically change all dependency versions in the application.

When upgrading Spring Boot, check the parent/BOM, plugin version, and Java baseline together. When using the parent, versions are typically aligned by release; when separating the parent and BOM, you must manage the plugin separately.

## 7. Spring Boot Maven Plugin: Checking Repackage Changes

### 7.1. What Does the repackage Goal Do?

The `repackage` goal takes the archive produced by Maven `package` and transforms it into an executable archive compatible with the Spring Boot Loader. For an executable JAR, the layout typically contains:

```text
META-INF/MANIFEST.MF
org/springframework/boot/loader/...
BOOT-INF/classes/...
BOOT-INF/lib/...
```

The manifest contains launcher information and the application entry point. For an executable WAR, the layout uses `WEB-INF` according to Spring Boot rules.

### 7.2. Configurations to Compare When Upgrading the Plugin

| Parameter/Aspect | Question When Upgrading Version |
|---|---|
| `mainClass` | Has main class auto-detection changed? Does it need to be explicitly declared? |
| `classifier` | Does the executable artifact still replace the main artifact or create a separate artifact? |
| `attach` | Is the repackaged archive still attached to the project/deployment? |
| `layout` | Is the archive type still inferred appropriately for the packaging? |
| `includes` / `excludes` | Has the set of dependencies packaged into the archive changed? |
| `layers` | Have the layer index and dependency grouping changed? |
| `outputDirectory` / `outputFilename` | Have the archive location and filename changed? |
| `skip` | Are there any conditions causing repackage to be skipped? |
| `requiresUnpack` | Which dependencies need to be unpacked at runtime? |

Parameter names, types, defaults, and version support must be confirmed using `help:describe` together with version-specific documentation. This table is a review checklist, not a claim that every parameter changes on every upgrade.

### 7.3. Checking Main Class and Artifact After Repackage

If the plugin is not configured with a main class, it may attempt to detect the main class from compiled classes. When multiple matching classes exist or none is found, `repackage` can fail or produce unexpected results.

You can configure it explicitly:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <mainClass>com.example.demo.DemoApplication</mainClass>
    </configuration>
</plugin>
```

After building, inspect:

```bash
jar tf target/demo-1.0.0.jar
unzip -p target/demo-1.0.0.jar META-INF/MANIFEST.MF
```

If the environment lacks `unzip`, use `jar` to extract the manifest:

```bash
mkdir -p target/manifest-check
cd target/manifest-check
jar xf ../demo-1.0.0.jar META-INF/MANIFEST.MF
cat META-INF/MANIFEST.MF
```

Read `Main-Class` and `Start-Class` if present. Cross-check the filename, classifier, and `BOOT-INF/lib` to make sure you are looking at the actual executable artifact.

## 8. Gradle: Inspecting Plugin Versions, Tasks, and the Task Graph

### 8.1. Check the Gradle Wrapper First

The Gradle Wrapper pins the project's Gradle version, independent of the Spring Boot Gradle Plugin version.

Check:

```bash
./gradlew --version
```

Read the file:

```text
gradle/wrapper/gradle-wrapper.properties
```

Example wrapper configuration:

```properties
distributionUrl=https\://services.gradle.org/distributions/gradle-8.14.3-bin.zip
```

The version here is just an example. The plugin version and Gradle Wrapper version must fall within the compatibility range of the Spring Boot Gradle Plugin in use.

### 8.2. Finding Where Plugin Versions Are Declared

Check in order:

1. `settings.gradle` or `settings.gradle.kts` and the `pluginManagement` block.
2. `gradle/libs.versions.toml` if using plugin aliases.
3. `build.gradle` or `build.gradle.kts` of root/module.
4. `buildSrc` or included builds if using convention plugins.
5. `buildscript` if the project uses the legacy plugin mechanism.

Commands:

```bash
./gradlew tasks --all
./gradlew help --task bootJar
./gradlew help --task bootRun
```

- `tasks --all` lists callable tasks, including tasks not in the default group.
- `help --task` describes the task, path, group, and usage.
- These commands help identify tasks registered by plugins; they do not necessarily print all resolved properties/defaults.

### 8.3. Viewing the Task Graph Without Running Task Actions

```bash
./gradlew bootJar --dry-run
./gradlew build --dry-run
```

`--dry-run` configures the build and prints which tasks would run without executing task actions. Use it to compare the task graph before and after a plugin upgrade.

For example, a new plugin version may add a task or change task dependencies. If you only look at `BUILD SUCCESS`, you might miss this change. Compare the task list with the baseline before concluding the upgrade does not affect the build flow.

### 8.4. Do Not Confuse buildEnvironment with the Entire Plugin DSL

```bash
./gradlew buildEnvironment
```

This command is useful for viewing the `buildscript` classpath in builds using the `buildscript` mechanism. For plugins declared via the `plugins` block and `pluginManagement`, versions may be resolved through plugin markers; `buildEnvironment` is not always a complete inventory of every DSL plugin. Always read the actual place where versions are declared.

## 9. Gradle: Understanding Defaults, Conventions, and Explicit Values

Gradle uses `Property`, `Provider`, and conventions to configure tasks lazily.

### 9.1. A Convention Is the Value Used When No Explicit Value Is Set

Generic example:

```kotlin
val outputLabel = objects.property(String::class)

outputLabel.convention("default-name")
println(outputLabel.get())

outputLabel.set("custom-name")
println(outputLabel.get())
```

When `set` has not been called, the property retrieves its value from the convention. Once an explicit value is set, the convention is no longer the final value.

This explains why:

- A build script does not mention a property yet the task still has a value.
- A new plugin changes a convention and output changes even though the build script was not edited.
- An extension supplies conventions to a task.
- A provider reads a value from the project or another file and only resolves it when the task needs it.

### 9.2. Order of Tracing Task Values

When you need to determine an actual property value, trace:

1. Value set directly in the task configuration.
2. Value passed from the project extension or a convention plugin.
3. Provider/Convention supplied by the plugin.
4. Default in the task type/plugin.
5. Value computed from the project model or environment at resolution time.

This is an investigative heuristic, not a universal precedence order applying to every plugin. Specific task/property documentation is the authoritative source.

### 9.3. Example: Reading BootJar Values

The Spring Boot Gradle Plugin provides the `bootJar` task of type `BootJar`. To verify resolved values, you can temporarily add logging to a Groovy build script:

```groovy
tasks.named('bootJar') {
    doFirst {
        logger.lifecycle("bootJar.archiveFileName={}", archiveFileName.get())
        logger.lifecycle("bootJar.archiveClassifier={}", archiveClassifier.orNull)
        logger.lifecycle("bootJar.mainClass={}", mainClass.orNull)
    }
}
```

Then run:

```bash
./gradlew bootJar
```

Example log output:

```text
bootJar.archiveFileName=demo-1.0.0.jar
bootJar.archiveClassifier=
bootJar.mainClass=com.example.demo.DemoApplication
```

This is an **illustrative example**, not fixed output for every project. Archive name, classifier, and main class depend on project/plugin configuration. The `doFirst` snippet is for diagnostics only; remove it after recording values and do not commit debug logging unnecessarily.

If using Kotlin DSL, you can configure the task by type:

```kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    doFirst {
        logger.lifecycle("archiveFileName={}", archiveFileName.get())
        logger.lifecycle("archiveClassifier={}", archiveClassifier.orNull)
        logger.lifecycle("mainClass={}", mainClass.orNull)
    }
}
```

If a property does not exist in the plugin version being used, the Kotlin DSL compiler will flag the incompatible API; check the API docs for the exact version.

### 9.4. help --task Is Not a Tool for Reading Every Default

The command:

```bash
./gradlew help --task bootJar
```

helps identify what a task is and how to invoke it. It does not guarantee printing the final value of every `Property`. To find defaults:

- Read the API/docs for the exact plugin version.
- Inspect the task type and property descriptions.
- Look up `convention(...)` or providers in the plugin source when needed.
- Print resolved values during task execution as shown above.
- Inspect the actual artifact after the task runs.

Do not use `./gradlew properties` to infer all task defaults; that command mainly prints project properties.

## 10. Reading Version and Default Changes Layer by Layer

When upgrading, build a before/after comparison table rather than changing multiple things and debugging afterward.

| Layer to Compare | Pre-Upgrade Baseline | Post-Upgrade | Evidence |
|---|---|---|---|
| Build tool version | Maven/Gradle Wrapper | New version | `mvn -version`, `gradlew --version` |
| Plugin version | Old version | New version | POM, settings, version catalog, plugin DSL |
| Goals/tasks | Old list and bindings | New list/bindings | `help:describe`, `tasks --all`, build log |
| Configuration | Explicit values and inheritance | Explicit values after merge | Effective POM, settings/build scripts |
| Plugin defaults | Old descriptor/docs | New descriptor/docs | `help:describe`, versioned docs |
| Task conventions | Old task types/properties | New conventions | API docs, plugin source, resolved property log |
| Task graph | Old dependencies | New dependencies | Gradle `--dry-run` |
| Artifact | Filename, classifier, manifest, layout | New artifact | `jar tf`, manifest, checksum |
| Runtime | How app starts | New behavior | `java -jar`, smoke test |

### 10.1. Comparing Maven Effective POMs

Create a pre-upgrade baseline:

```bash
mvn help:effective-pom -Dverbose -Doutput=target/effective-pom-before.xml
mvn help:active-profiles
```

After upgrading the parent/plugin version:

```bash
mvn help:effective-pom -Dverbose -Doutput=target/effective-pom-after.xml
mvn help:active-profiles
```

Compare:

```bash
git diff --no-index target/effective-pom-before.xml target/effective-pom-after.xml
```

If the files are outside Git or the diff command does not suit the environment, use your IDE's diff tool. Focus on plugins, versions, executions, phases, goals, configuration, and active profiles.

Then describe the goal for each version:

```bash
mvn help:describe \
  -Dplugin=org.springframework.boot:spring-boot-maven-plugin:3.5.16 \
  -Dgoal=repackage -Ddetail

mvn help:describe \
  -Dplugin=org.springframework.boot:spring-boot-maven-plugin:3.5.17 \
  -Dgoal=repackage -Ddetail
```

Version 3.5.17 here is only an example of comparing two releases; substitute your project's real version. Compare parameter names, types, user properties, defaults, and descriptions.

### 10.2. Comparing Gradle Task Graphs

Before upgrading:

```bash
./gradlew clean build --dry-run --console=plain > tasks-before.txt
```

After upgrading:

```bash
./gradlew clean build --dry-run --console=plain > tasks-after.txt
```

Compare:

```bash
git diff --no-index tasks-before.txt tasks-after.txt
```

The task graph can change due to plugins or project configuration changes. When the diff shows differences, look for added/removed tasks, dependency edges, skipped tasks, and task outputs. Then run a real build to confirm behavior, because dry-run does not check task actions or artifacts.

### 10.3. Do Not Compare Outputs If Environments Differ

For meaningful results, hold constant:

- Commit/source tree.
- JDK/toolchain.
- Maven/Gradle Wrapper.
- Active profiles and project properties.
- OS/architecture when builds are platform-dependent.
- Dependency repositories/caches.
- Environment variables affecting the build.
- Same build command and same modules.

If the baseline used JDK 17 while post-upgrade used JDK 21, you cannot conclude that output changes came solely from the plugin version.

## 11. Maven Example: Pinning Plugin Version and Reading Repackage Defaults

Here is a small POM illustrating how to manage the plugin version separately and enable `repackage`. Spring Boot versions are pinned to avoid relying on implicit environment versions.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>plugin-default-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
            <version>3.5.16</version>
        </dependency>
    </dependencies>

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-maven-plugin</artifactId>
                    <version>3.5.16</version>
                </plugin>
            </plugins>
        </pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <executions>
                    <execution>
                        <id>repackage</id>
                        <goals>
                            <goal>repackage</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

This example pins dependency and plugin versions for illustration. This minimal POM does not declare source code; a real application needs a main class and corresponding source tree. In larger projects, prefer using the Boot parent/BOM per project policy to keep dependency versions synchronized.

Verification commands:

```bash
mvn help:effective-pom -Dverbose -Doutput=target/effective-pom.xml

mvn help:describe \
  -Dplugin=org.springframework.boot:spring-boot-maven-plugin:3.5.16 \
  -Dgoal=repackage -Ddetail

mvn help:active-profiles
mvn package
```

After building, inspect the archive and manifest. Do not rely solely on the effective POM to conclude the final `mainClass` or output filename if the plugin uses auto-inference logic.

## 12. Gradle Example: Managing Plugin Version and Task Configuration

### 12.1. Version in Settings and Plugin DSL

`settings.gradle`:

```groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
    plugins {
        id 'org.springframework.boot' version '3.5.16'
    }
}
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.named('bootJar') {
    mainClass = 'com.example.demo.DemoApplication'
}
```

The version is declared in settings, and the plugin is applied in the build script. When upgrading the plugin, change the version in the corresponding management source and inspect the task graph and output.

### 12.2. Do Not Confuse Wrapper and Plugin

A change may upgrade:

- `gradle-wrapper.properties`: Gradle distribution.
- Spring Boot plugin in `pluginManagement`/version catalog.
- Java toolchain.
- Dependency BOM/platform.

These are four separate axes. Upgrading them together may be necessary, but when a build breaks, compare the release notes and compatibility matrix of each axis to tell which change caused the new behavior.

## 13. Common Types of Default Changes

### 13.1. Default Shifts from Inference to Requiring Explicit Declaration

An older plugin version might find the main class automatically; a newer version might require explicit configuration in a given situation or change its detection algorithm. Symptoms:

- Plugin reports no main class found.
- Multiple main classes exist and the plugin cannot choose.
- `bootRun` works, yet `bootJar` lacks the expected `Start-Class`.

How to handle:

1. Check docs/migration notes for the exact version.
2. Confirm compiled output contains the main class.
3. Identify which task/goal is inferring the main class.
4. Declare the main class explicitly if the project has multiple entry points.
5. Check the manifest and run the artifact.

### 13.2. Default Output/Classifier Changes

A plugin can change how it produces the main artifact, secondary artifacts, or filenames. Symptoms:

- CI fails to find `target/*.jar` using an old glob.
- Dockerfile copies the wrong file.
- Publication pushes the plain JAR instead of the executable JAR.
- Checksum differs even though source code did not change.

How to handle:

- Check `classifier`, `finalName`, archive name, and output directory.
- Check which task/goal produces each file.
- Use specific filenames in the pipeline or configure a stable archive name.
- Inspect JAR contents, not just file existence.

### 13.3. Default Skip or Execution Binding Changes

Symptoms:

- Build succeeds without producing the expected report/archive.
- Goal/task appears in configuration but does not run.
- CI passes `-D...skip` or a project property causing the plugin to skip.
- Gradle task is skipped due to an `onlyIf` condition or missing inputs.

Check:

- Maven execution id, phase, goal, and user property.
- Gradle task graph, task dependencies, `onlyIf`, `enabled`, `NO-SOURCE`, `UP-TO-DATE`.
- Whether logs report the task/goal as skipped.

Do not conclude a plugin is working just because old output remains in the build directory. Run `clean` and verify the artifact was generated in the current build.

### 13.4. Default Dependency/Classpath Changes

A plugin can change dependencies packaged into the archive, test runtime, or compiler classpath. Symptoms:

- `ClassNotFoundException`/`NoClassDefFoundError`.
- Tests behave differently than before.
- Artifact is unexpectedly smaller/larger.
- Duplicate or missing dependencies in `BOOT-INF/lib`.

Use Maven `dependency:tree`, Gradle `dependencies`/`dependencyInsight`, and compare the actual archive. Do not blame plugin defaults if the dependency graph also changed due to the BOM.

### 13.5. Default Caching/Incremental Behavior Changes

A Gradle plugin/task may declare different inputs/outputs or cacheability. A Maven plugin may change incremental logic. Symptoms:

- Task does not run because of `UP-TO-DATE` or `FROM-CACHE`.
- Report/artifact is not refreshed as expected.
- Clean build succeeds while incremental build fails, or vice versa.

Diagnose with a `clean` build to eliminate stale outputs, then compare with an incremental build. Do not disable caching globally to hide a task with broken input/output declarations.

## 14. Review Checklist When Upgrading Plugins/Tasks/Goals

### 14.1. Before Upgrading

- [ ] Recorded Maven/Gradle Wrapper and JDK/toolchain.
- [ ] Identified currently resolved plugin versions.
- [ ] Recorded plugin versions declared in parent, `pluginManagement`, settings, or version catalog.
- [ ] Exported effective POM and active profiles.
- [ ] Saved Gradle task list and task graph for main build commands.
- [ ] Recorded key values: main class, archive name, classifier, output path, skip flags.
- [ ] Saved baseline artifact and manifest.
- [ ] Recorded test reports and build commands.

### 14.2. After Upgrading

- [ ] Read release notes/migration guides for each plugin and build tool.
- [ ] Verified plugin compatibility with Maven/Gradle/JDK.
- [ ] Compared whether goals/tasks still exist or were renamed.
- [ ] Compared phase bindings/task dependencies.
- [ ] Compared parameters/properties, types, and defaults.
- [ ] Compared effective POMs and active profiles.
- [ ] Compared Gradle task graphs.
- [ ] Confirmed resolved defaults via logs or task properties.
- [ ] Built from a clean state.
- [ ] Compared artifact filename, classifier, manifest, layout, and checksum.
- [ ] Ran unit/integration tests and executable archive smoke test.
- [ ] Verified CI scripts, Dockerfile, and publication pull the right artifact.
- [ ] Documented explicitly added configurations to avoid relying on fragile defaults.

## 15. Common Issues When Reading Defaults and How to Handle Them

| Symptom | Common Cause | How to Check |
|---|---|---|
| Plugin version in POM differs from execution log version | Parent, `pluginManagement`, or profile overrides it | Effective POM, active profiles, and debug log |
| Effective POM does not show plugin defaults | Defaults are declared in plugin descriptor or computed at runtime | `help:describe -Ddetail`, docs, and execution log |
| `help:describe` cannot find goal | Wrong plugin coordinates/version or goal does not exist | Check `groupId`, `artifactId`, `version`, and `goal` |
| `mvn package` does not run `repackage` | Plugin not active or execution/phase not bound | `build/plugins`, parent, and effective POM |
| `pluginManagement` lists plugin but it does not run | Plugin is only managed, not activated in the build | Add plugin to `build/plugins` or use parent with matching execution |
| `-Dskip...` has no effect | Wrong User Property or property unsupported by plugin | `help:describe`, version-specific docs |
| Gradle `help --task` does not show defaults | Task help does not print all resolved properties | API docs, task type, and property log |
| `buildEnvironment` does not list plugin DSL | Plugin resolved via plugins DSL/`pluginManagement` | Check settings, version catalog, and `plugins` block |
| Gradle task disappears after upgrade | Plugin not applied, task renamed, or compatibility failure | `tasks --all`, plugin version, and migration guide |
| Task graph changes | Plugin changed task dependencies or project config | `--dry-run` before/after |
| JAR has a different name after upgrade | Archive name/classifier/default output changed | `bootJar`, `jar`, Maven `repackage` config, and manifest |
| Main class no longer found | Source set/compiled output or default discovery changed | Main class, plugin docs, task/goal configuration |
| Build succeeds but archive lacks loader | Viewing plain JAR or `repackage`/`bootJar` did not run | Manifest, `BOOT-INF`, and exact output file |
| Build fails only in CI | Different JDK, profile, environment, property, or wrapper | Compare environments and command lines |
| Incremental build differs from clean build | Cache/input/output or stale output | Clean build, task inputs/outputs, and cache diagnostics |

## 16. Safe and Traceable Tool Upgrade Strategy

A solid tool upgrade requires a baseline, a diff, and behavioral evidence. Follow this sequence:

1. **Pin versions:** do not let critical plugins depend on dynamic versions or unclear prefixes.
2. **Upgrade in a controlled way:** prefer changing one axis at a time; if wrapper, plugin, and JDK must upgrade together, record each change.
3. **Read version-specific docs:** release notes, migration guides, plugin descriptors/API docs.
4. **Export effective configuration:** Maven effective POM/profiles; Gradle plugin declarations/task graph.
5. **Compare defaults:** Maven `help:describe`; Gradle convention/property docs and resolved values.
6. **Clean build:** avoid confusing stale outputs with outputs from the new plugin.
7. **Inspect the artifact:** filename, classifier, manifest, archive layout, and dependencies.
8. **Run tests/smoke tests:** confirm behavior, not just task success.
9. **Update CI/Docker/publication:** point to the exact post-upgrade artifact.
10. **Record decisions:** plugin versions, wrapper, JDK, explicitly pinned properties, and rationale.

For defaults that affect releases, configure them explicitly when doing so makes behavior clearer and more stable. You do not need to copy every default into the POM/build script: only pin values meaningful to the build contract, such as main class, archive classifier, or output name when pipelines depend on them.

## 17. Official Documentation

- [Apache Maven Help Plugin — Plugin details and goals](https://maven.apache.org/plugins/maven-help-plugin/plugin-info.html)
- [Maven Help Plugin — help:describe configuration](https://maven.apache.org/plugins/maven-help-plugin/examples/describe-configuration.html)
- [Maven Help Plugin — help:describe goal reference](https://maven.apache.org/components/plugins/maven-help-plugin/describe-mojo.html)
- [Maven Help Plugin — help:effective-pom goal reference](https://maven.apache.org/components/plugins/maven-help-plugin/effective-pom-mojo.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven — Plugin Configuration](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
- [Spring Boot Maven Plugin 3.5 — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html)
- [Spring Boot Gradle Plugin 3.5 — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html)
- [Spring Boot Gradle Plugin — Running Applications](https://docs.spring.io/spring-boot/gradle-plugin/running.html)
- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html)
- [Gradle — Configuring Tasks Lazily and Property Conventions](https://docs.gradle.org/current/userguide/lazy_configuration.html)
- [Gradle — Plugins](https://docs.gradle.org/current/userguide/plugins.html)
- [Gradle — Version Catalogs](https://docs.gradle.org/current/userguide/version_catalogs.html)
- [Gradle — Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html)

**Conclusion:** To read configuration changes when upgrading tools, separate three things: merged project configuration, defaults/conventions supplied by the plugin, and actual values after building. Maven uses `help:describe`, effective POM, and lifecycle mappings to inspect goals/parameters; Gradle uses plugin declarations, task types, task graphs, and resolved properties to inspect tasks/conventions. Finally, inspect the real artifact to confirm whether default changes altered the filename, manifest, classifier, or executable JAR/WAR contents.
