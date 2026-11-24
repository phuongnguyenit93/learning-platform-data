# Importing a Spring Boot Project into an IDE and Determining the Effective Build Configuration

## 1. Objectives and Problem Statement

After generating or receiving a Spring Boot project, being able to open the source folder in an IDE does not guarantee that the IDE has imported the build model properly. This lesson explains how to identify a Maven/Gradle project, import it into IntelliJ IDEA, Eclipse/Spring Tools, or VS Code, and determine the configuration **actually applied** when compiling, testing, and packaging.

After this lesson, you will be able to:

- Identify the root directory to import, build tool, wrapper, modules, and required JDK.
- Distinguish between configuration declared in files and configuration after inheritance, activation, and dependency resolution.
- Inspect Maven effective POM, active profiles, and dependency tree; or Gradle project model, tasks, and dependency graph.
- Compare the IDE configuration against the project's standard build commands to diagnose discrepancies in Java, plugins, profiles, repositories, and libraries.
- Confirm the project can build and produce the right artifact type before starting feature development.

**Principle:** the build configuration files along with the wrapper and project build invocation are the source of truth for verification. IDE settings are part of the execution environment and can introduce differences if out of sync.

## 2. Identifying the Project and Choosing the Right Root Directory

Before importing, examine the files directly inside the folder received from Git or the Spring Boot initializer:

| Indicator | Maven | Gradle |
| --- | --- | --- |
| Project configuration file | pom.xml | build.gradle or build.gradle.kts |
| Declaration of participating projects/modules | Aggregator pom.xml and modules declarations | settings.gradle or settings.gradle.kts, usually containing include |
| Wrapper on Linux/macOS | mvnw | gradlew |
| Wrapper on Windows | mvnw.cmd | gradlew.bat |
| Wrapper configuration | .mvn/wrapper/ | gradle/wrapper/ |
| Downloaded dependencies | Maven local repository, usually in ~/.m2/repository | Gradle cache, usually in ~/.gradle/caches |
| Common build outputs | target/ | build/ |

The **Wrapper** is a project script for selecting the exact prepared version of Maven/Gradle. Prefer the wrapper if the repository provides it and the script works; a globally installed mvn or gradle command may use a different version. The wrapper does not automatically pick the right JDK in every case: you must check the JDK separately.

For a **single-module project**, import the directory containing pom.xml or settings.gradle(.kts)/build.gradle(.kts). For a **multi-module project**, you generally need to import the root directory of the Maven reactor or Gradle root build to preserve module links, dependency substitution, and related tasks. If a repository contains both Maven and Gradle, check the repository's README or CI configuration to pick the actively maintained build system; do not assume both are authoritative build sources.

Minimal illustrative structures:

~~~text
demo/
├── pom.xml                  # Maven project
├── mvnw
├── mvnw.cmd
├── .mvn/wrapper/
└── src/main/java/...
~~~

Or:

~~~text
demo/
├── settings.gradle          # Gradle root project
├── build.gradle             # Gradle Groovy DSL
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
└── src/main/java/...
~~~

A Gradle project using Kotlin DSL will have settings.gradle.kts and build.gradle.kts. Both Groovy and Kotlin DSLs express similar concepts in many cases, but you cannot copy syntax verbatim from one language's file to the other.

## 3. Preparing the Environment Before Importing

1. Check the Git branch and root directory; read the Java, Maven/Gradle, and Spring Boot versions declared in the build.
2. Install a JDK compatible with the project's Spring Boot version and plugins. Distinguish **JDK running Maven/Gradle**, **JDK/toolchain used for compilation**, and **JDK running the application**: these three values can differ.
3. Run verification commands in a terminal at the exact root. On Linux/macOS:

~~~bash
java -version
./mvnw -version
# Or, for a Gradle project:
./gradlew --version
~~~

On Windows PowerShell:

~~~powershell
java -version
.\mvnw.cmd -version
# Or:
.\gradlew.bat --version
~~~

Only run the command for the **actual build tool**. If no wrapper exists, use mvn -version or gradle --version after verifying the installed version is compatible. On Linux/macOS, if the script lacks execute permission, check the executable bit in Git before adjusting permissions per project workflow.

4. Ensure access to permitted repositories (Maven Central, internal repository, proxy/mirror if any). The first import may need to download the Gradle distribution, plugins, and libraries.
5. If using an untrusted repository, review build scripts before letting the IDE auto-sync or run tasks: build scripts and plugins can execute code.

Do not conclude a project is broken just because the IDE shows red errors right after opening. Import tools may still be downloading dependencies, have the wrong JDK selected, or not have finished indexing; inspect the specific sync errors first.

## 4. Importing in Popular IDEs

### 4.1. IntelliJ IDEA

- Choose **File → Open**, open the **root directory** of the project; when prompted, confirm opening it as a Maven/Gradle project. If only individual files are open, use the action to add a Maven/Gradle project from pom.xml or build.gradle(.kts).
- Wait for Maven/Gradle sync. Check **Project Structure → Project SDK** and the module JDK; for Gradle also check **Settings → Build, Execution, Deployment → Build Tools → Gradle → Gradle JVM**, preferring the wrapper distribution. Menu names may vary slightly across IDE versions.
- For Maven, check the Maven home/wrapper, user settings, local repository, and active profiles in the Maven tool window.
- For Gradle, open the Gradle tool window to see root, subprojects, and tasks. Check whether the IDE is set to use **Gradle** or IntelliJ to build/run; this choice can cause IDE run results to differ from ./gradlew.
- Use **Reload All Maven Projects** or **Reload All Gradle Projects** after modifying build files; only clear caches/re-import completely when a specific sync cannot recover via normal reload.

### 4.2. Eclipse / Spring Tools (STS)

- Maven: **File → Import → Maven → Existing Maven Projects**, select the root containing pom.xml, and confirm detected modules. Maven integration is typically m2e.
- Gradle: **File → Import → Gradle → Existing Gradle Project** (Buildship), select the Gradle root and configure the appropriate Java/Gradle distribution.
- Check **Installed JREs / Execution Environment**, Java compiler compliance, and the project's classpath. For Maven, use **Maven → Update Project** when POM changes; for Gradle, use **Refresh Gradle Project**.
- If the project still reports errors, inspect **Problems**, **Maven/Gradle Console**, and dependency download progress before manually editing Build Path; direct edits to build-tool-generated classpaths are usually overwritten on refresh.

### 4.3. Visual Studio Code

- Install a JDK and appropriate Java extensions, typically **Extension Pack for Java**, along with **Spring Boot Extension Pack** if Spring Boot features are needed.
- Use **File → Open Folder** on the root. To let extensions recognize pom.xml or the Gradle build, wait for **Java Projects**, **Maven for Java**, or **Gradle for Java** to complete importing.
- Select the Java runtime for the workspace and the JDK that extensions/build tools will run with. Inspect the Java/Maven/Gradle **Output** and **Problems** panels if import fails.
- After changing build files, refresh the project/dependencies using the extension's corresponding command. For complex builds, running the wrapper in a terminal is the reliable reference point to verify whether the IDE is applying the same configuration.

**Common takeaway across all three IDEs:** source folders being colored properly or classes showing a Run button does not prove the build is consistent. Stronger evidence is the wrapper executing the same task with the same environment variables, JDK, profiles/properties, and dependency resolution.

## 5. What Does "Effective Build Configuration" Mean?

The configuration you see in a single file is only the **input**. When running a build, the tool also combines inheritance, plugins, parent module configuration, user/machine settings, environment variables, command-line options, and dependency version resolution. Therefore, you must answer three separate questions:

1. **What is the resulting project model after configuration?** Which group/artifact/version, modules, plugins, tasks/goals, Java target, repositories, active profiles, or properties apply?
2. **Which actual library versions are selected?** A declared version may differ from a BOM-managed version, be altered by a rule, or be chosen via transitive dependency conflict resolution.
3. **What actually executes?** Which wrapper, which JVM, which task/goal, which runtime arguments, and which output artifact?

No single IDE screen answers all three questions completely. You need to combine IDE inspection with direct reports from Maven/Gradle.

### 5.1. Maven: Effective POM and Dependency Tree

In Maven, the effective model combines the current pom.xml, parent POM, Super POM, dependencyManagement, pluginManagement, and active profiles. User/global settings and command-line flags can affect repositories, mirrors, credentials, profiles, and execution behavior. The Spring Boot BOM manages many library versions, but it does **not** turn every transitive dependency into a direct dependency in the POM.

An **illustrative POM** for a Spring Boot module (versions are concrete examples; follow the version selected by your project):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Here, the spring-boot-starter-web dependency does not declare a version in dependencies because the parent/BOM provides version management. That does not mean the full dependency map is visible in the root POM. To inspect the actual result, run in the Maven root:

~~~bash
./mvnw -version
./mvnw help:active-profiles
./mvnw help:effective-pom -Doutput=target/effective-pom.xml
./mvnw help:effective-settings
./mvnw dependency:tree
./mvnw dependency:tree -Dincludes=org.springframework:spring-core
./mvnw test
~~~

Meaning of each command:

- **-version:** the Maven version and Java runtime used to launch Maven; not necessarily the bytecode release target.
- **help:active-profiles:** Maven profiles actually activated by POM, settings, environment/activation rules, and command-line flags.
- **help:effective-pom:** the POM after inheritance, profiles, and configuration merging; useful for finding applied Java properties, plugin versions/goals, or repositories. target/effective-pom.xml is a **diagnostic output** and should not be edited in place of pom.xml.
- **help:effective-settings:** merged Maven settings, helpful when inspecting mirrors and repositories; be careful not to expose secrets/credentials from logs or configuration.
- **dependency:tree:** the resolved dependency graph, including transitive dependencies and selected versions; the includes filter helps trace a single library.
- **test:** verifies compile/test along the Maven lifecycle under current configuration; outcomes depend on actual code and environment.

For specific profiles, re-run both diagnostic and build commands with the exact selection, for example:

~~~bash
./mvnw -Pdev help:active-profiles
./mvnw -Pdev help:effective-pom -Doutput=target/effective-dev.xml
./mvnw -Pdev test
~~~

**Only use -Pdev when the project has a valid dev profile.** Compare profiles enabled in IntelliJ/Eclipse against command-line profiles. Beyond the POM, Maven also has .mvn/maven.config, .mvn/jvm.config, settings.xml (typically in ~/.m2), Maven toolchains, and -D flags that can alter results; read the exact sources used by the project when investigating mismatches.

### 5.2. Gradle: Evaluated Model and Dependency Resolution

Gradle does not have an equivalent "effective POM" file. The post-configuration model comes from settings.gradle(.kts), root/subproject build.gradle(.kts), plugins and convention plugins, init scripts, gradle.properties, version catalogs, project properties, and selected tasks. Gradle then resolves versions/dependencies per **configuration** (e.g., compileClasspath or runtimeClasspath).

An **illustrative Groovy DSL** build.gradle for Spring Boot:

~~~groovy
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Accompanying settings.gradle example:

~~~groovy
rootProject.name = 'demo'
~~~

The Spring Boot plugin provides specialized tasks like bootJar; in the example, io.spring.dependency-management is also included so dependency versions are managed via the Spring Boot BOM. **Applying the Spring Boot plugin alone does not automatically mean all starter dependencies are version-managed**; a project may alternatively declare a Gradle platform/enforcedPlatform for the BOM. You must not overlook the actual version-management mechanism in the build.

To inspect the effective configuration, run from the Gradle root:

~~~bash
./gradlew --version
./gradlew projects
./gradlew tasks --all
./gradlew properties
./gradlew javaToolchains
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
./gradlew test
~~~

Interpretation:

- **--version:** the Gradle distribution and JVM running Gradle.
- **projects:** root/subprojects included in the build by settings (crucial in multi-module builds).
- **tasks --all:** Gradle tasks declared or generated by plugins; seeing bootJar does not guarantee the task will succeed.
- **properties:** evaluated project properties; be cautious because properties or plugin logs may expose internal details.
- **javaToolchains:** Java toolchains detected by Gradle; check whether the JVM used to compile differs from the JVM running the daemon.
- **dependencies:** the dependency graph of the selected configuration; configuration names may differ in other projects/plugins.
- **dependencyInsight:** why a module version was chosen and which rules/constraints or dependencies led to that choice.
- **test:** runs the test task under the actual configuration.

In multi-project Gradle builds, target the exact subproject if configuration is not at the root:

~~~bash
./gradlew :service:dependencies --configuration runtimeClasspath
./gradlew :service:dependencyInsight --dependency spring-core --configuration runtimeClasspath
./gradlew :service:test
~~~

Only use the commands above when the actual project has a module named service. Do not confuse **Gradle project properties** (e.g., -Penv=dev handled by a build script) with **Maven profiles**: Gradle does not automatically provide Maven's profile mechanism. Inspect what properties or environment variables the plugin/build logic reads, and pass those exact values in comparison runs.

Beyond repository files, Gradle can read user-level gradle.properties, init scripts, environment variables, and -P/-D flags; thus two machines with the same build.gradle can still behave differently. Version catalogs in gradle/libs.versions.toml manage aliases/versions per project configuration, but the actually selected versions still must be verified via the dependency graph.

## 6. Determining the Exact Java Version and Compiler Configuration

Three easily confused concepts:

| Component | Verification Question | Where to Check |
| --- | --- | --- |
| JVM running the IDE | Which Java is the IDE launched with? | IDE About/Runtime |
| JVM running the build tool | Which Java runs the Maven/Gradle daemon/client? | ./mvnw -version or ./gradlew --version; Gradle JVM in IDE |
| Java used for compilation | Which bytecode version does the compiler/toolchain emit? | maven-compiler-plugin release/source/target or Gradle java.toolchain/options.release |

For example, the Gradle daemon may run on JDK 21 while java.toolchain is set to 17: code can still be compiled using a JDK 17 compiler. Similarly, Maven running on JDK 21 with maven.compiler.release=17 can emit Java 17-compatible classes (with --release API checks). Conversely, merely setting "Project SDK=17" in the IDE **does not guarantee** the wrapper in a terminal also runs JDK 17.

If a Spring Boot project requires Java 17 while the terminal still uses Java 11, import/build may fail because plugins or class files need a newer runtime. Check JAVA_HOME, PATH, IDE Gradle JVM/Maven runner, Gradle toolchain, or Maven toolchains.xml depending on the project; do not tweak only the "language level" and consider the issue solved.

To confirm the exact class bytecode version after a build, you can run javap on a compiled class:

~~~bash
javap -verbose -classpath target/classes com.example.demo.DemoApplication
# With Gradle, typically:
javap -verbose -classpath build/classes/java/main com.example.demo.DemoApplication
~~~

Only use the example above when the actual class is named com.example.demo.DemoApplication and the output paths match; look for the **major version** line. For instance, major 61 corresponds to Java 17, and major 65 corresponds to Java 21. Runtime compatibility also depends on dependencies and the actual JVM.

## 7. Comparing IDE Builds Against Terminal Builds

A repeatable workflow:

1. **Pick a baseline:** identify the root, Git branch, wrapper, JDK, profiles/properties, and the command used by CI or the team.
2. **Run the build via the wrapper outside the IDE:** for Maven use ./mvnw test or ./mvnw package; for Gradle use ./gradlew test or ./gradlew build. Record the first failing task/goal and detailed cause.
3. **Inspect the effective model:** Maven effective POM + active profiles + dependency tree; Gradle projects/tasks/properties + dependencyInsight for the suspect library.
4. **Compare IDE screens:** project/module import, Gradle JVM/Maven runner, selected profiles, offline mode, settings.xml/Gradle user home, build delegation, and run configurations.
5. **Re-sync the build project**, then run the **same** goal/task with the same JDK and parameters in the IDE. Do not alter source code to mask dependency errors before identifying the root cause.
6. **Verify outputs:** successful compilation/tests and the right artifact type if packaging is required; if IDE and CLI differ, preserve the command log, Java/build tool versions, and selected dependency coordinates as evidence of the discrepancy.

Practical example: a Spring Boot project's pom.xml uses Java 17, yet IntelliJ opens the root with JDK 21 while Maven runs with JDK 11. If a Maven plugin reports it does not support a Java 11 runtime, the fault lies in the JVM **launching Maven**, even though the IDE reports Project SDK 21. Point the Maven runner/JAVA_HOME JDK to a version supported by the project, verify with ./mvnw -version, then reload. If a version conflict remains, use dependency:tree to inspect selected dependencies.

Another example: build.gradle requires a Spring Boot plugin matching the chosen wrapper version, while the IDE uses an older local Gradle installation. IDE sync reports a plugin error, whereas ./gradlew projects succeeds. Switch the IDE to the Gradle Wrapper and re-sync; if both sides already use the same wrapper/JDK and results still differ, inspect init scripts, gradle.properties, and tasks/arguments.

## 8. Does a Successful Build Produce the Right Spring Boot Artifact?

**Compile/test**, **regular jar**, and **executable Spring Boot jar** are distinct outputs.

- Maven: the package lifecycle creates artifacts according to packaging and configured plugins. With spring-boot-maven-plugin properly integrated, the repackage goal turns the JAR into an executable Spring Boot archive. Check plugin configuration/effective POM and files in target/.
- Gradle: when the org.springframework.boot plugin and Java plugin are properly applied, bootJar usually builds the executable JAR; the regular jar task serves a different purpose. Inspect actual tasks and files in build/libs/ for the specific subproject.
- If the built module is a **library**, do not expect a bootJar; packaging must follow the module's role and declared tasks/lifecycle.

Verification commands when the module has a valid Spring Boot entrypoint:

~~~bash
# Maven:
./mvnw package

# Gradle:
./gradlew bootJar
~~~

Do not combine both commands for the same project. Inspect the goal/task logs and generated artifacts; filenames depend on group, project name, version, classifier, and build configuration. In a sample build script without a Spring Boot main class yet, the executable packaging task may fail even when import and dependency resolution are completely healthy.

## 9. Common Errors and How to Verify Before Fixing

| Symptom | Possible Cause | Verification and Resolution |
| --- | --- | --- |
| IDE does not see modules or tasks | Imported src/ by mistake or only imported a subproject instead of root | Confirm root POM/settings, check Maven projects or ./gradlew projects, then re-import root |
| IDE shows red dependencies, terminal builds fine | IDE not synced, offline mode, different mirror/repository, or build tool/JDK | Reload project; compare wrapper version, settings.xml, Gradle JVM, repositories, and sync logs |
| Terminal build fails while IDE runs fine | IDE compiler and build tool use different settings, cached classes, or custom flags | Run the same goal/task via wrapper with the same profile and JDK; compare build delegation |
| "Unsupported class file major version" | JDK/Gradle/plugin/runtime incompatible with bytecode being read | Read major version, run ./gradlew --version or ./mvnw -version; check toolchain/plugin compatibility |
| Library version differs from declaration | BOM, dependency management, transitive conflict, constraints, or resolution rules | Maven dependency:tree; Gradle dependencyInsight on the right configuration |
| Missing plugin/task | Wrong root imported, plugin not applied to module, or configuration error | Maven effective POM or Gradle tasks --all; inspect plugin resolution logs |
| Profile or environment has no effect | Maven profile not active; Gradle property not read by script; IDE not passing args | Maven help:active-profiles; check -P/-D handling and run configurations |
| Dependency download fails | Proxy, mirror, credentials, repository, network, or offline mode | Read specific repository error message; check effective settings/Gradle repositories, avoid leaking secrets in public logs |
| JAR exists but fails with java -jar | Built plain JAR instead of bootJar/repackage, missing main class, or wrong manifest | Check task/goal, Spring Boot entrypoint, and packaging configuration |
| IDE/CI builds differ across machines | Different JDK, wrapper, user-level properties/settings, environment, or cache | Record versions and reproduction commands; standardize configuration sources in repository/CI |

Do not wipe the entire ~/.m2 or ~/.gradle directory as a first step. Doing so can trigger large re-downloads without fixing version, profile, or Java errors. Use logs and diagnostic commands to pinpoint the exact configuration first.

## 10. Practice Exercise with Completion Criteria

Pick an existing Spring Boot project and perform these steps in both the terminal and IDE:

1. Identify whether the project uses Maven or Gradle; locate the root, wrapper, and list all modules.
2. Import the root into the IDE, wait for sync to succeed, and record the JDK/Gradle JVM/Maven runtime.
3. Run -version with the wrapper and record the actual build tool and JDK.
4. For Maven, capture the effective POM, active profiles, and dependency:tree; for Gradle, inspect projects, tasks, and runtimeClasspath.
5. Find the actual resolved version of spring-core (or a dependency present in the project) along with why that version was selected.
6. Run tests with the wrapper, then package appropriately for the module type; confirm the path and type of the generated artifact.
7. Toggle a valid configuration following team conventions (e.g., enabling an existing Maven profile or a Gradle property supported by the build script), re-run diagnostics, and pinpoint exactly what changed. Revert the configuration afterward if it was only an experiment.

**Completion criteria:** you can explain which root the project is imported from, which build tool and wrapper versions are used, which JDK runs the build and which JDK compiles code, which profiles/properties are in effect, how library versions are selected, which task/goal creates the artifact, and whether the IDE reproduces the exact terminal result.

Whenever discrepancies occur, save the **command executed + environment conditions + relevant error log snippet**. That provides the evidence needed to fix the true cause while helping others import and build the project consistently.