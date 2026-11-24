# Version Relationships Between Spring Boot, Spring Framework, and the JDK

When starting or upgrading a Spring Boot application, there are three versions that must be considered together:

- **Spring Boot:** the integration platform, auto-configuration, starters, build plugins, and managed dependency set.
- **Spring Framework:** the core foundation providing the IoC container, dependency injection, AOP, transactions, web, and Spring APIs.
- **JDK:** the Java environment used to build, compile, and run the application.

These three components have compatibility relationships, but **they do not share the same version number and are not interchangeable**. For example, a project may use Spring Boot 3.x, Spring Framework 6.x, and JDK 17 or a newer JDK supported by that release.

Version mismatches can cause errors right at build time, startup errors, class/method linkage errors, or errors that only appear when executing a specific feature. Understanding how Spring Boot manages Spring Framework and how the JDK affects bytecode is the foundation for choosing a stable configuration.

## 1. Three components, three responsibilities

The overall relationship can be visualized as follows:

~~~text
                  JDK
      compile / bytecode / runtime
                    |
                    v
             Spring Framework
      IoC / DI / AOP / transaction / web
                    |
                    v
               Spring Boot
  auto-configuration / starters / BOM / plugins
                    |
                    v
           Actual application
~~~

A Spring Boot application uses Spring Framework APIs and runs on the JVM provided by the JDK. Spring Boot assembles and configures these components to reduce manual integration work.

| Component | Role | What does the version determine? |
|---|---|---|
| Spring Boot | Application integration platform | Dependency set, auto-configuration, plugins, and Java requirements |
| Spring Framework | Core framework | Container API, AOP, transactions, MVC, WebFlux, and related modules |
| JDK | Toolchain and JVM | Compilation capabilities, Java APIs, bytecode, and execution environment |
| Maven/Gradle | Build tool | How dependencies are resolved, compiled, tested, and packaged |
| Spring Cloud or extensions | Additional integration projects | Release train compatible with the Spring Boot line |

Spring Boot typically manages the Spring Framework version through dependency management. Developers should start from **a chosen Spring Boot release line**, let Boot manage the corresponding Spring modules, and then select a JDK within the supported range of that Boot line.

## 2. Spring Boot is not Spring Framework

The two names often appear together, but they refer to two different products.

**Spring Framework** provides foundational capabilities:

- IoC container and dependency injection.
- Bean lifecycle.
- AOP and transaction abstraction.
- Spring MVC and WebFlux.
- Resource abstraction.
- Event publishing.
- Data binding and validation integration.
- Abstractions supporting system integration.

**Spring Boot** builds an application development and operations experience on top of Spring Framework:

- Auto-configuration based on classpath and properties.
- Starter dependencies to group commonly used libraries.
- Dependency management through a BOM.
- Maven/Gradle plugins to build executable JAR/WAR files.
- Externalized configuration.
- Actuator and production-ready utilities.
- Mechanisms for running standalone applications and integrating with containers.

For example, `spring-context` belongs to Spring Framework. `spring-boot-autoconfigure` and `spring-boot-starter-web` belong to Spring Boot.

When declaring:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

the starter brings in a group of dependencies suitable for a web application. It does not mean Spring Framework is packaged as a single product with the same version number as Spring Boot.

### 2.1. Boot and Framework version numbers can differ

Illustrative example:

~~~text
Spring Boot       3.3.x
Spring Framework  6.1.x
JDK               17
~~~

These are three different version lines. When using Spring Boot's dependency management, the corresponding Spring Framework version is managed by Boot.

Do not assume that Boot 3.3 must use Framework 3.3 or JDK 3.3. The version numbers of the three components have their own release schedules and rules.

## 3. Spring Boot manages the Spring Framework version with a BOM

Spring Boot provides a **BOM (Bill of Materials)** named `spring-boot-dependencies`. The BOM declares the dependency versions recommended and tested together for a Spring Boot line.

Framework modules are usually part of the dependency set managed by the BOM, for example:

- `spring-core`
- `spring-beans`
- `spring-context`
- `spring-aop`
- `spring-expression`
- `spring-web`
- `spring-webmvc`
- `spring-tx`

Instead of manually setting versions for each module, the application declares dependencies and lets the BOM choose compatible versions.

~~~text
Spring Boot release
       |
       v
spring-boot-dependencies BOM
       |
       +-- Spring Framework modules
       +-- Jackson
       +-- Logging libraries
       +-- Hibernate / persistence libraries
       +-- Embedded server
       +-- Other managed dependencies
~~~

Benefits:

1. Modules belonging to the same ecosystem have aligned versions.
2. Reduces the risk of combining a new Spring module with an old Spring module.
3. Easier upgrades along a release line.
4. Shorter and more readable POM or build files.
5. A single central point for version management instead of scattered versions.

**A BOM is not a single runtime library.** It is dependency management metadata that tells the build tool which versions to select for declared dependencies.

## 4. Why shouldn't you manually set versions for individual Spring modules?

Suppose a project uses Spring Boot 3.x but manually declares:

~~~xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-context</artifactId>
    <version>5.3.30</version>
</dependency>
~~~

Meanwhile, other modules managed by Boot may belong to Spring Framework 6.x.

The result can be a classpath containing Framework modules from different lines. They may have different APIs and internal expectations.

Possible errors:

- `NoSuchMethodError` when code calls a method missing in the actual loaded version.
- `NoClassDefFoundError` when a required class is missing on the runtime classpath.
- `ClassNotFoundException` when a requested class does not exist.
- Bean initialization errors due to incompatible APIs or behavior.
- Errors occurring only on a specific code branch because the related method was not called during startup.

Not every override is guaranteed to fail, but **manually mixing Spring modules from multiple release lines breaks the compatibility assumptions provided by the Boot BOM**.

Practical principles:

- Use the Boot BOM as the primary version source.
- Do not declare separate versions for individual Spring modules without a specific reason.
- If an override is needed for a patch or special compatibility, understand the dependency graph and inspect the entire related module group.
- Document the reason for the override so it can be revisited during the next upgrade.

## 5. The JDK is a separate compatibility dimension

The JDK is not a dependency like Spring Framework. It provides:

- The `javac` compiler.
- The JVM to execute bytecode.
- The Java standard libraries.
- Tools such as `jar`, `javadoc`, `jlink`.
- Runtime modules and development utilities.

Spring Boot has minimum Java requirements and a supported Java range per release. Spring Framework also has its own Java requirements. An application must choose a JDK that satisfies **Boot, Framework, and all other dependencies**.

General example:

~~~text
Spring Boot 3.x
      |
      +-- Based on Spring Framework 6.x
      |
      +-- Requires Java 17 baseline
      |
      v
Application needs compatible JDK/runtime
~~~

Spring Boot 3.0 marked a major change: requiring Java 17 or higher and using Spring Framework 6.0. This prevents an application on Boot 2.x/Framework 5.x from simply changing the Boot version and continuing to build with Java 8 as before.

Subsequent minor/patch releases may expand the supported JDK range, so consult the documentation for **the exact release line** rather than applying a single number across all versions.

## 6. Distinguishing between the build JDK and the runtime Java version

A project may use multiple Java versions across its pipeline:

1. The JDK running Maven or Gradle.
2. The JDK toolchain used to compile source code.
3. The Java release/target of the bytecode.
4. The JRE/JDK on the machine running the application.

These versions can be identical, but they do not always have to be.

Example:

~~~text
Build agent:
  JDK 21
      |
      v
Compiler toolchain:
  Java 17, --release 17
      |
      v
Artifact:
  Java 17 bytecode/API target
      |
      v
Production runtime:
  Java 17 or compatible newer JDK
~~~

JDK 21 can compile source targeting release 17 if the build is configured properly. The resulting artifact can then run on Java 17, provided that:

- Code and dependencies do not use APIs introduced in Java 18 or later.
- Generated bytecode is compatible with release 17.
- Plugins/annotation processors do not generate bytecode or require a runtime exceeding the target.
- Spring Boot and all dependencies support Java 17.

If compiled to Java 21 bytecode, a Java 17 runtime cannot run that artifact.

### 6.1. Checking the active Java version

~~~bash
java -version
javac -version
~~~

In a Maven build environment:

~~~bash
./mvnw -version
~~~

With Gradle:

~~~bash
./gradlew --version
~~~

These commands help identify which JVM the shell or build tool is using. Gradle may use a different daemon JVM than the default Java in a terminal if a toolchain or daemon configuration is set separately; inspect the build configuration as well.

## 7. How do Java source, target, and release differ?

When compiling Java, distinguish between:

- **Source level:** the Java syntax accepted by the compiler.
- **Target bytecode:** the class file format generated.
- **Release:** restricts syntax, bytecode, and Java platform APIs to a specific Java release.

Depending on the build tool and plugin, older configurations may use `source` and `target`, while modern configurations generally prefer `--release` or a Java toolchain combined with release.

Example:

~~~bash
javac --release 17 -d out src/main/java/com/example/App.java
~~~

`--release 17` instructs the compiler to compile compatibly with Java 17, including the corresponding platform APIs, rather than merely emitting older bytecode while accidentally calling newer APIs.

If you only set a low target bytecode while compiling against a newer JDK's APIs, the application may build successfully but throw `NoSuchMethodError` or `NoClassDefFoundError` for Java APIs when running on the older JDK.

## 8. Configuring Maven with the Spring Boot parent

A common approach is using `spring-boot-starter-parent`.

Illustrative POM example:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
</parent>

<groupId>com.example</groupId>
<artifactId>orders-api</artifactId>
<version>1.0.0</version>

<properties>
    <java.version>17</java.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

`3.3.5` is an illustrative version to explain the configuration, not a recommendation that every new project should pick that exact version. Choose a release line that is supported for your project and compatible with your target JDK.

### 8.1. What does the parent do?

The Spring Boot parent provides:

- Dependency management via the Boot BOM.
- Default plugin configuration.
- Suitable Maven compiler configuration.
- Default resource filtering and encoding according to its configuration.
- Plugin management conventions that keep builds consistent.

When using the parent, many dependencies do not need their own version declared:

~~~xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-context</artifactId>
</dependency>
~~~

However, in a Boot application, it is generally better to prefer appropriate starters and abstractions rather than declaring internal modules directly just because they are available.

### 8.2. java.version is not the Spring Boot version

In the example:

~~~xml
<properties>
    <java.version>17</java.version>
</properties>
~~~

This property configures the Java version used for compilation via the mechanism supported by the parent/plugin. It does not change Spring Boot to version 17, nor does it automatically install JDK 17 on the build machine.

The build machine still needs a compatible JDK and may require toolchain configuration if a specific compiler must be selected.

## 9. Maven without the Spring Boot parent can still use the BOM

Some projects have their own organization parent POM. In that case, the Boot dependency BOM can be imported under `dependencyManagement`.

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.5</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Then declare dependencies without versions if the BOM manages them:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

Key differences:

| Using Boot parent | Importing Boot BOM |
|---|---|
| Provides dependency management | Provides dependency management |
| Inherits plugin management and many default configurations | Does not automatically inherit all parent configurations |
| Usually requires less configuration | Suitable when an organization parent POM already exists |
| Parent hierarchy allows only one direct parent | Can import multiple BOMs following Maven rules |

If you do not use the Boot parent, you must configure the build/compile plugins and the Spring Boot Maven Plugin according to project requirements.

## 10. Maven compiler plugin and Java toolchain

For Maven projects that need to specify the release explicitly, the compiler plugin can be configured:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

When using the Spring Boot parent, the `java.version` property is usually the convenient configuration supported by the parent. Avoid declaring conflicting properties such as `java.version=17` alongside `maven.compiler.release=21` unless intentional.

### 10.1. Maven Toolchains

If a machine runs Maven on one JDK but the project needs a different compiler JDK, Maven Toolchains can select the compiler JDK.

~~~text
Maven process JVM
       |
       v
Maven Toolchains selects compiler JDK
       |
       v
Compile with configured release
~~~

Toolchain configuration usually lives in the build environment's Maven settings/toolchains and is supported by the compiler plugin. Avoid hardcoding a single developer's local JDK path into a shared POM.

Importantly, the pipeline must verify that the right JDK was selected, rather than only looking at `java -version` in the terminal.

## 11. Configuring Gradle with the Spring Boot plugin

Groovy DSL example:

~~~groovy
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

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

The plugin versions in this example merely illustrate a synchronized setup. When creating a new project or upgrading, choose a Boot plugin and dependency-management plugin compatible with the project's Gradle Wrapper.

When the Spring Boot Gradle plugin is combined with `io.spring.dependency-management`, the Boot BOM is imported to manage dependency versions for that Boot release.

### 11.1. Gradle does not automatically use a JDK toolchain just because multiple JDKs are installed

The configuration:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

instructs Gradle to choose a Java 17 toolchain for tasks supporting Java toolchains, such as compile/test. It does not guarantee that the Gradle daemon itself runs on JVM 17.

The Gradle daemon JVM is the environment running the build tool. The toolchain JVM is the compiler/test environment selected by the task. They can differ.

### 11.2. The Gradle Wrapper also has JDK requirements

The Gradle Wrapper pins the Gradle distribution used by the project. That Gradle version has its own minimum JVM requirement.

A project may have:

- A Spring Boot plugin version compatible with the Gradle Wrapper.
- A Gradle Wrapper requiring a JVM to run.
- A Java toolchain selecting a different JDK to compile/test.
- A runtime image using a JRE compatible with the bytecode and Spring Boot.

Therefore, when a build fails right as Gradle starts, the cause is not necessarily Spring Framework; the Gradle Wrapper may simply not run on the current JVM.

## 12. Compatibility tables must be read by release line

There is no single rule like "any Spring Boot runs on any JDK." Each release line has its own baseline and support limits.

Some useful historical milestones:

| Platform line | Corresponding Spring Framework | Key Java milestone |
|---|---|---|
| Spring Boot 2.7.x | Spring Framework 5.3.x | The 2.7 line can support Java 8 and up per its release matrix |
| Spring Boot 3.0.x | Spring Framework 6.0.x | Requires Java 17 or higher |
| Subsequent Spring Boot 3.x | Framework 6.x per each release's BOM | Java 17 is the baseline for the 3 line; supported JDK range changes by minor release |
| Newer Boot/Framework lines | Framework pair managed by the Boot release | Must check the system requirements table of that exact release |

The table above highlights major milestones and **does not replace the official compatibility matrix** for a specific patch/minor release. When choosing concrete versions, check simultaneously:

1. System Requirements of the Spring Boot release.
2. System Requirements of the corresponding Spring Framework.
3. JDK support of critical dependencies.
4. Gradle/Maven version and plugin compatibility.
5. Whether the container runtime image has an appropriate JRE.

### 12.1. Why is Boot 3 a major upgrade step?

Spring Boot 3 is based on Spring Framework 6 and requires Java 17 or higher. Along with this, the ecosystem migrated from many legacy Java EE APIs to the Jakarta EE namespace.

Example:

~~~java
// Previously in many Boot 2.x applications
import javax.servlet.Filter;
~~~

~~~java
// Applications based on Spring Framework 6 / Boot 3
import jakarta.servlet.Filter;
~~~

This is a servlet API example. Do not mechanically replace every package starting with `javax` with `jakarta`: several `javax.*` packages belonging to Java SE remain unchanged, such as `javax.sql` or `javax.crypto`.

When upgrading Boot 2 to Boot 3, check:

- Java 17 or higher in build and runtime.
- Spring Framework 6.
- Jakarta namespace in converted APIs.
- Whether third-party dependencies support Jakarta.
- Compatible servlet container, persistence provider, and validation provider.
- Legacy configurations that were removed or changed.

This is a clear example showing that Boot, Framework, and the JDK must be upgraded under a coordinated plan.

## 13. Spring Framework version should be decided by the Boot BOM

In a normal Boot application, do not choose a Spring Framework version independently without a specific requirement.

For example, a project uses:

~~~text
Spring Boot BOM: 3.3.5
Spring Framework: managed by BOM
~~~

If you manually override a module:

~~~xml
<properties>
    <spring-framework.version>...</spring-framework.version>
</properties>
~~~

or declare a separate version for `spring-context`, you may produce a classpath that no longer matches the configuration tested by Boot.

When an override is genuinely required:

1. Identify the reason, such as a confirmed security patch or bug fix.
2. Check synchronized versions across all Spring Framework modules.
3. Verify compatibility with Boot modules and integration dependencies.
4. Run an appropriate test suite.
5. Inspect the dependency tree to confirm resolved versions.
6. Record the date and reason to remove the override later.

Do not change only `spring-core` while leaving `spring-beans`, `spring-context`, and `spring-expression` on a different version.

## 14. What dependencies does the Spring Boot BOM manage?

The BOM does not only manage Spring Framework. It also manages many dependencies used transitively by starters.

For example, a web application may have:

~~~text
spring-boot-starter-web
       |
       +-- spring-web
       +-- spring-webmvc
       +-- JSON libraries
       +-- embedded servlet container
       +-- logging
       +-- ...
~~~

A data application may add:

~~~text
spring-boot-starter-data-jpa
       |
       +-- Spring Data JPA
       +-- Hibernate
       +-- JDBC-related dependencies
       +-- transaction integration
       +-- ...
~~~

Manually bumping a transitive library without inspecting the dependency graph can introduce conflicts that are not immediately obvious at compile time.

The BOM helps mitigate this by managing a set of versions tested together.

### 14.1. The BOM does not guarantee compatibility for every external library

If a project adds a third-party SDK, an internal library, or a Spring extension not included in the Boot BOM, developers must still verify compatibility separately.

Spring Cloud is an important example: Spring Cloud release trains have a compatibility matrix with Spring Boot lines. Do not pick a Spring Cloud version simply because it has the highest version number or because Maven/Gradle can download it.

## 15. Spring Cloud and extension projects

An application may additionally use:

- Spring Cloud Config.
- Spring Cloud Gateway.
- Spring Cloud Circuit Breaker.
- Spring Cloud OpenFeign.
- Spring Cloud Stream.
- Other Spring Integration projects.

These projects have their own release trains. A release train is designed to work with one or more specific Spring Boot lines.

When adding the Spring Cloud BOM, select a release train compatible with the application's Boot version:

~~~text
Spring Boot release line
          |
          v
Spring Cloud compatibility matrix
          |
          v
Spring Cloud BOM/release train
          |
          v
Spring Cloud modules
~~~

Do not simply add a `spring-cloud-starter-*` dependency with an arbitrary version. If the two version management systems are not aligned on the matrix, the application may compile yet fail in auto-configuration, API integration, or at runtime.

## 16. Checking resolved versions with Maven

A POM file might declare one version, while the final dependency graph resolves another due to transitive dependencies or dependency management precedence.

Using the Maven Wrapper:

~~~bash
./mvnw dependency:tree
~~~

To focus on Spring Framework:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework
~~~

To inspect the resolved POM:

~~~bash
./mvnw help:effective-pom
~~~

`effective-pom` shows the POM after applying parent inheritance, properties, and dependency management. This is helpful when a project has multiple parents/BOMs.

To inspect the Maven environment:

~~~bash
./mvnw -version
~~~

To confirm where a specific dependency comes from, filter the dependency tree by group/artifact or inspect the transitive paths in the output.

**Do not just read the version written in the POM; inspect the version Maven actually resolves.**

## 17. Checking resolved versions with Gradle

Gradle provides commands to inspect the dependency graph:

~~~bash
./gradlew dependencies
~~~

Inspect the runtime configuration:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Inspect why a version was selected for a module:

~~~bash
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
~~~

Replace `spring-core` with the dependency under investigation.

Check toolchains:

~~~bash
./gradlew javaToolchains
~~~

Check the Gradle version and daemon JVM:

~~~bash
./gradlew --version
~~~

These commands help answer:

- Which module pulled in the dependency?
- Are multiple versions being requested?
- Which version was selected?
- Why did Gradle select that version?
- Which JDKs are available as toolchains?

When encountering `NoSuchMethodError`, dependency insight is usually more useful than guessing and upgrading everything to the latest version.

## 18. Signs of version mismatch errors

Some common errors:

| Symptom | Likely cause | Investigation direction |
|---|---|---|
| `UnsupportedClassVersionError` | Bytecode newer than runtime JVM | Compare compile release and `java -version` on the server |
| `NoSuchMethodError` | Runtime loads a class version missing the method expected by caller | Dependency tree, BOM, and version overrides |
| `NoClassDefFoundError` | Required class is missing or class initialization failed | Runtime classpath and root cause |
| `ClassNotFoundException` | Class not found via classloader | Dependency scope, module/classpath, and namespace |
| `javax.*` / `jakarta.*` errors | Libraries from different API generations | Check Boot 2/3 and Jakarta dependencies |
| Gradle fails to start | Incompatible Gradle Wrapper/JVM | Gradle version and daemon JDK |
| Maven compiler failure | Compiler plugin or JDK does not match configuration | Maven version, toolchain, `release` |
| Auto-configuration does not work | Incompatible dependency/version or API condition | Condition report and dependency graph |
| Method/constructor error at startup | Unaligned Spring modules or related libraries | BOM, effective POM, runtime classpath |

Some exceptions may originate from application bugs or wrong dependency scopes rather than version skew. Confirm the cause from the actual loaded class and dependency graph.

### 18.1. UnsupportedClassVersionError

Example:

~~~text
java.lang.UnsupportedClassVersionError:
... has been compiled by a more recent version of the Java Runtime
~~~

Meaning: the running JVM does not understand the bytecode of the loaded class.

For example, the project was compiled with Java 21, while the container runtime is Java 17. Resolutions:

- Upgrade the runtime to a compatible JDK/JRE if that is the application's target.
- Or compile targeting a lower Java release if all code and dependencies support it.
- Inspect the Docker base image and deployment environment.
- Do not fix the Java version only on a developer machine while ignoring CI/servers.

### 18.2. NoSuchMethodError

Example:

~~~text
java.lang.NoSuchMethodError:
'void org.springframework....someMethod(...)'
~~~

This is typically a linkage error: code was compiled against one API, while runtime loaded a class version without that method.

Investigation steps:

1. Identify the class containing the method.
2. Find the actual JAR providing that class.
3. Inspect the dependency tree.
4. Look for dependency overrides or transitive conflicts.
5. Align the modules to a compatible version set.
6. Rebuild and retest the artifact.

Do not try to patch this by manually dropping a new JAR into runtime without understanding which version the classpath is selecting.

## 19. Checking the JDK of the build agent and runtime container

A pipeline often spans multiple environments:

~~~text
Developer workstation
       |
       v
CI build agent
       |
       +-- Maven / Gradle JVM
       +-- Java compiler toolchain
       |
       v
Executable JAR
       |
       v
Container image / server
       |
       +-- Runtime JVM
       |
       v
Application
~~~

A build may succeed on a workstation yet fail to run in a container because the runtime JRE is older than the bytecode. Or the Gradle daemon may fail to start because the wrapper requires a newer JDK than installed.

An illustrative Dockerfile:

~~~dockerfile
FROM eclipse-temurin:17-jre

WORKDIR /app

COPY target/orders-api.jar /app/app.jar

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

This example assumes the artifact was compiled compatibly with Java 17 and the chosen Spring Boot release supports this runtime.

If the project compiles targeting Java 21, a matching runtime must be chosen. Picking an image tag based on the JDK on a developer's laptop without checking bytecode is a common source of failure.

## 20. Process for choosing a new version set for a project

Before creating a project or upgrading, follow this sequence:

### Step 1 — Choose a Spring Boot release line

Select a release line matching the support lifecycle, feature requirements, and organizational policy.

Do not pick solely by the highest version number. Consider the support window, dependency compatibility, security fixes, and upgrade path of the application.

### Step 2 — Check Boot's Java requirements

Read the system requirements for that exact release. Identify the minimum Java version and supported JDK range.

### Step 3 — Let Boot manage Spring Framework

Use the Boot parent or Boot BOM. Avoid picking a Framework version independently without justification.

### Step 4 — Check extension projects

If using Spring Cloud or other Spring integration libraries, select a release train compatible with Boot.

### Step 5 — Choose the build tool and wrapper

Check that the Maven/Gradle version supports the build JDK and the selected Boot plugin.

### Step 6 — Pin the compiler toolchain/release

Select a Java API/bytecode target matching the production runtime. Record the configuration in the build file so the whole team and CI use it consistently.

### Step 7 — Check the runtime image

Ensure the JRE/JDK on the container or server is within the supported range and capable of running the bytecode and dependencies.

### Step 8 — Verify the dependency graph

Run dependency tree/insight to detect version overrides and conflicting dependencies.

### Step 9 — Run tests and package the artifact

Build, run unit/integration tests, and smoke test the artifact in a deployment-like environment.

## 21. Patch, minor, and major upgrades

Different upgrade types carry different levels of impact.

| Upgrade type | General example | Approach |
|---|---|---|
| Patch | 3.3.4 to 3.3.5 | Usually focused on bug/security fixes; still requires testing |
| Minor | 3.2.x to 3.3.x | May introduce new features, behavior changes, or deprecations |
| Major | 2.x to 3.x | May change Java/API/namespace baselines and introduce breaking changes |

Do not assume a patch update carries zero risk, or that a minor update cannot change behavior. Read the release notes and migration guidance for the exact version.

### 21.1. Upgrading Spring Boot usually brings Framework upgrades along

If you upgrade the Boot BOM, the Spring Framework version managed by the BOM may change accordingly.

This is why you should upgrade along the Boot release line rather than updating a single Framework module. A Boot release is built and tested against a specific dependency set; keeping some older Spring modules can break consistency.

### 21.2. Major upgrades require checking code and external dependencies

When moving from Boot 2 to Boot 3, pay attention to:

- Java 17 baseline.
- Spring Framework 6.
- Jakarta EE namespace.
- Servlet container and persistence provider.
- Validation, security, serialization, and integration libraries.
- Deprecated/removed properties or APIs.
- Maven/Gradle plugins and build scripts.

Do not consider the migration done once compile errors are resolved. Some changes affect runtime or configuration behavior and require integration and smoke tests.

## 22. Dependency overrides: when are they acceptable?

Cases may arise where a dependency override is necessary due to:

- A security patch not yet included in the release line's Boot BOM.
- A confirmed bug with a specific workaround version.
- A third-party dependency requiring a minimum version.
- An organizational policy mandating a vetted version.

When overriding, you should:

1. Identify the overridden module and related modules.
2. Check the framework/library compatibility matrix.
3. Inspect the dependency tree to verify the final resolved version.
4. Document the reason and decision source.
5. Add tests covering affected functionality.
6. Set a review point to drop the override once a new Boot release manages an appropriate version.

Do not override an entire group of dependencies just to silence a scanner warning without knowing whether the patched version is compatible with your current release line.

## 23. Maven dependency management precedence

In Maven, the final selected version is influenced by dependency management, parent POMs, imported BOMs, and direct declarations.

When multiple BOMs exist, import order and precedence rules can affect the selected version. A dependency with a directly declared version can also produce a different result than the version managed by the Boot BOM.

Therefore, if a POM contains:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>...</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

you must understand why that version was set and whether it overrides the version provided by the Boot BOM.

The command:

~~~bash
./mvnw help:effective-pom
~~~

shows the configuration after Maven merges parents and dependency management. The command:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework
~~~

shows the actual resolved dependencies.

**The source POM does not always tell the full story about the final classpath.**

## 24. Gradle version conflicts and dependency constraints

Gradle resolves the dependency graph according to its own rules. When multiple dependencies request different versions, Gradle selects a version using its resolution strategy and configuration metadata/constraints.

For example, a transitive dependency may request a `spring-core` version different from the one managed by the Boot BOM. You can run:

~~~bash
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
~~~

to see:

- Which version was selected.
- Which dependencies requested that module.
- Which constraints or platforms participated.
- Why a particular version was chosen.

When using a Gradle platform/BOM, keep dependencies in the same ecosystem aligned to the platform. Avoid adding global resolution rules without understanding their impact on other modules.

## 25. Spring Boot plugin version vs. starter version

Another common misconception is thinking the Spring Boot Gradle plugin version and starter version must be written on every dependency.

Example:

~~~groovy
plugins {
    id 'org.springframework.boot' version '3.3.5'
}
~~~

When combined with appropriate dependency management, you can declare:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

There is no need to add a version to each starter when the BOM manages them.

The same applies in Maven with the Boot parent/BOM.

The **Boot plugin version** controls build integration. The **starter dependency version** is chosen by dependency management. The two concepts are related, but they are not a single field.

## 26. Spring Framework modules must stay synchronized

Spring Framework is split into multiple modules. An application may pull them in via starters or directly.

Example:

~~~text
spring-core
spring-jcl
spring-beans
spring-context
spring-aop
spring-expression
spring-tx
spring-web
spring-webmvc
~~~

These modules have internal dependencies and relationships. Do not upgrade an individual module without checking the requirements of the rest.

A quick check:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework
~~~

or:

~~~bash
./gradlew dependencyInsight --dependency spring-context --configuration runtimeClasspath
~~~

The goal is to confirm that the resolved Framework modules follow the consistent version set managed by the Boot release.

## 27. Verifying in CI to avoid "works on my machine"

A version configuration is only useful if CI actually uses it.

Pin the following:

- Maven Wrapper or Gradle Wrapper in the repository.
- JDK/toolchain for compile and test.
- Java release target.
- Spring Boot plugin/parent version.
- Dependency BOM.
- Container runtime image.
- Critical build plugins.

A pipeline can run:

~~~text
Checkout source
      |
      v
Select supported build JDK
      |
      v
Run Maven/Gradle Wrapper
      |
      v
Resolve dependencies
      |
      v
Compile with configured release
      |
      v
Run unit/integration tests
      |
      v
Package executable artifact
      |
      v
Run artifact smoke test
      |
      v
Build runtime image with compatible JRE
~~~

If a developer uses JDK 21 while CI uses JDK 17, the build may fail due to compiler/plugin or API differences. Conversely, if CI builds with JDK 21 targeting 17, a container runtime on JDK 11 is still incompatible with a Boot 3 application.

## 28. Choosing a Java version based on the deployment lifecycle

The target JDK is not merely a personal choice. It affects:

- Container images.
- Server operating systems.
- Organizational runtime policies.
- Third-party libraries.
- Performance and garbage collectors.
- Security update cadence.
- Monitoring tools and APM agents.
- Operability in cloud environments.

If an organization runs Java 17, picking a dependency requiring Java 21 can prevent the application from deploying even if it compiles on a developer's machine.

Before upgrading Java:

1. Verify Boot and Framework support for the target JDK.
2. Check build plugins and annotation processors.
3. Check all dependencies.
4. Check runtime images and APM agents.
5. Run integration tests.
6. Verify startup, memory, TLS, and operational behavior in staging.

## 29. Example: a version-mismatched configuration

Suppose a project has:

~~~text
Spring Boot BOM: 3.3.x
Spring Framework: one module forced to 5.3.x
Build JDK: 21
Java release target: 17
Runtime JRE: 17
~~~

The Java side may be valid: building with JDK 21 while producing Java 17-compatible bytecode/APIs if release is configured properly and all dependencies support it.

However, a Spring Framework module forced to 5.3.x may be incompatible with the 6.x modules managed by the Boot BOM. When the application calls newer APIs or Framework modules interact, linkage/runtime errors can appear.

Fix:

- Remove unnecessary overrides.
- Let the Boot BOM manage Framework modules uniformly.
- Inspect effective POM/dependency insight.
- Rebuild and test against the target JDK/runtime.

This example shows that **JDK 21/17 can be a valid choice while the Framework version is still wrong**. All three compatibility dimensions must be evaluated independently and then combined.

## 30. Example: Boot 2 to Boot 3

An older application:

~~~text
Spring Boot 2.7.x
Spring Framework 5.3.x
Java 8 or Java 11 (depending on configuration)
javax.servlet / Java EE namespace
~~~

Upgrade target:

~~~text
Spring Boot 3.x
Spring Framework 6.x
Java 17+
jakarta.servlet / Jakarta EE namespace
~~~

This is not a simple version bump. Check:

- Do the build agent and runtime have Java 17?
- Which dependencies still use `javax.servlet`?
- Does the servlet container support the Jakarta namespace?
- Are validation and persistence providers compatible?
- Did Spring Security configuration APIs change?
- Do third-party starters have releases supporting Boot 3?
- Do tests cover critical integrations?

Depending on project state, you can upgrade through an intermediate step following migration guidance to separate handling deprecations from major changes. The goal is to reduce simultaneous large changes and make issues easier to trace.

## 31. A checklist for reading a compatibility matrix

When reading a release's compatibility table, do not search only for the word "Java." Check:

| Item | Question |
|---|---|
| Spring Boot version | Is this the exact patch/minor line the project intends to use? |
| Spring Framework version | Which Framework modules does the Boot BOM manage? |
| Java baseline | What is the minimum JDK to build/run? |
| Java support range | Which JDKs are supported by that release? |
| Maven/Gradle | Which build tool and wrapper versions are supported? |
| Servlet container | Is the embedded/external container compatible? |
| Spring Cloud | Which release train matches? |
| Persistence provider | Are Hibernate/JPA versions compatible? |
| Security | Are Spring Security and API namespaces compatible? |
| Third-party starters | Do they support this Boot line? |
| Runtime image | Does the JRE in the image match the bytecode and Boot? |

A compatibility matrix must match the specific release. Do not use an old blog post about Boot 2 as the basis for choosing a JDK for Boot 3 or a newer line.

## 32. Team version management principles

A development team should agree on:

1. A single central version source for Spring Boot.
2. Spring Framework managed by the Boot BOM.
3. Other BOMs such as Spring Cloud chosen via compatibility matrices.
4. Java toolchain/release recorded in the build file.
5. Maven/Gradle Wrapper committed with the repository.
6. Runtime images with explicit JDK/JRE tags.
7. Version overrides requiring justification and an owner.
8. CI verifying the dependency graph and testing the artifact.
9. Upgrades accompanied by changelogs and migration notes.
10. No uncontrolled dynamic dependency versions in production builds.

An internal README table might state:

~~~text
Spring Boot:        3.3.5
Spring Framework:   managed by Spring Boot BOM
Build JDK:          21
Java release:       17
Runtime JRE:        17
Gradle Wrapper:     version pinned in gradle-wrapper.properties
Spring Cloud:       compatible release train selected
~~~

These values are only examples. What matters is stating clearly **when the build JDK differs from the Java release target**, so others do not confuse the compiler environment with the runtime requirement.

## 33. Common misconceptions

**"Spring Boot 3 means Spring Framework is also version 3."** False. Boot 3.x is based on Framework 6.x.

**"JDK 21 installed on the machine means the application definitely runs on Java 21."** No. The build may target Java 17, and production runtime may differ from the build machine.

**"Just changing `java.version` automatically installs that JDK."** False. The property only configures the build; the machine/CI must still have a matching JDK or a toolchain configured to download/select it.

**"A BOM is a runtime dependency."** False. A BOM is version management metadata, not a library added to the classpath like a starter.

**"Starters automatically pick every third-party version."** Only dependencies managed by the BOM receive versions from it; external dependencies must be checked separately.

**"You can upgrade `spring-core` alone to get a patch."** That can produce mismatched Framework modules; inspect the whole group and dependency graph.

**"Compiling successfully means the runtime is compatible."** False. Bytecode, APIs, and classpath may differ at runtime.

**"Low `sourceCompatibility` or `target` guarantees using only old APIs."** Not necessarily. Use `--release` or equivalent configuration to control Java APIs as well.

**"Boot parent and Boot BOM are identical."** No. The BOM manages dependency versions; the parent also provides Maven/plugin management configurations.

**"`@Primary` or switching starters fixes linkage errors."** No. Version errors require inspecting the classpath and actual resolved versions.

**"Upgrading Java means upgrading Spring Boot."** No. The JDK and Spring Boot are independent versioned components that must be compatible.

**"Building on a newer JDK lets the container use an older JRE."** Only if bytecode and all APIs/dependencies are truly compatible with that older JRE, and the Boot release supports that runtime.

## 34. Practical exercises

### Exercise 1 — Identify the three versions

Given the configuration:

~~~text
Spring Boot 3.3.5
Spring Framework 6.1.x
JDK 17
~~~

Explain:

- How do Boot and Framework differ in role?
- Why are their version numbers not the same?
- What manages the Framework version?
- What does the JDK provide to build and runtime?

### Exercise 2 — Find an overridden dependency

Suppose a POM uses the Boot parent but declares a custom version for `spring-context`.

Run:

~~~bash
./mvnw help:effective-pom
./mvnw dependency:tree -Dincludes=org.springframework
~~~

Identify the final resolved version and dependency path. Explain the risks when `spring-context` is not on the same release as other Framework modules.

### Exercise 3 — Distinguish build JDK and runtime JDK

Suppose:

~~~text
Build JDK: 21
Java release: 17
Runtime: 17
~~~

Answer when this configuration can run, what conditions could cause it to fail, and why checking only `java -version` on a developer's machine is insufficient.

### Exercise 4 — Diagnose UnsupportedClassVersionError

An artifact runs fine on a developer's machine, but the container reports `UnsupportedClassVersionError`.

Identify:

- Compiler JDK and `--release` used.
- Java runtime in the container.
- Base image of the Dockerfile.
- Whether any dependency contains bytecode requiring a newer Java version.

Propose changes to make both environments compatible.

### Exercise 5 — Plan a Boot 2 to Boot 3 upgrade

List the change groups:

- Java 17 baseline.
- Framework 6.
- Jakarta namespace.
- Third-party dependencies.
- Servlet container.
- Spring Security, validation, and persistence.
- Maven/Gradle wrapper and plugins.
- Runtime image.
- Integration tests.

The goal is a plan broken down into reviewable steps, not just changing a version number in the POM.

## Conclusion

Spring Boot, Spring Framework, and the JDK are three closely related components with distinct responsibilities.

- **Spring Boot** selects and integrates a set of dependencies, including a compatible Spring Framework version.
- **Spring Framework** provides the container, AOP, transactions, web, and foundational APIs.
- **The JDK** determines the compiler, Java APIs, bytecode, and JVM used to run the application.

In a typical Spring Boot project, let the **Boot parent/BOM manage the Framework version**, select a JDK meeting the Boot release's system requirements, pin the Java toolchain/release in the build, and verify a compatible runtime container. When upgrading, also verify Maven/Gradle, Spring Cloud, and third-party libraries.

When errors occur, inspect the actual versions in the dependency tree, the build/runtime JVMs, and the bytecode target. **A successful build proves only one stage; a sound version set must be compatible from compiler to runtime and across the entire dependency graph.**
