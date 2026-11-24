# The Roles of pom.xml, settings.gradle, and build.gradle in a Spring Boot Project

## 1. Overview

When initializing a Spring Boot project, we typically choose **Maven** or **Gradle** as the build tool. The build tool is responsible for resolving and downloading libraries, compiling Java, running tests, packaging the application, and providing development-time run commands. Three commonly encountered file names serve distinct roles:

| File | Belongs to | Primary Role |
| --- | --- | --- |
| **pom.xml** | Maven | Describes the project (Project Object Model): artifact coordinates, Java level, libraries, plugins, build configuration, and packaging. |
| **settings.gradle** | Gradle (Groovy DSL) | Initializes the build structure: root project name, list of subprojects; can also configure plugin lookup locations and repository policies. |
| **build.gradle** | Gradle (Groovy DSL) | Configures how each project is built: plugins, dependencies, Java toolchain, repositories, tasks, tests, and packaging. |

**Key distinction:** A Maven project typically has **pom.xml**. A Gradle project typically has **settings.gradle** and **build.gradle**. These are **two alternative build systems**; you do not need to create all three files for one application. If a repository intentionally supports both Maven and Gradle, each system has an independent configuration and does not automatically synchronize dependencies or tasks.

In this lesson, the Spring Boot **3.3.5** and **Java 17** example is simply a consistent illustrative version pair. When creating a real project, pick compatible versions from Spring Initializr and verify the Maven/Gradle wrapper version.

## 2. File Locations at Project Initialization

Two example projects share the same Java code but use different build files:

~~~text
demo-maven/
├── pom.xml
├── mvnw / mvnw.cmd
├── .mvn/wrapper/...
└── src/
    └── main/java/com/example/demo/DemoApplication.java

demo-gradle/
├── settings.gradle
├── build.gradle
├── gradlew / gradlew.bat
├── gradle/wrapper/...
└── src/
    └── main/java/com/example/demo/DemoApplication.java
~~~

- **src/main/java** holds application code; **src/main/resources** holds configuration such as application.properties or application.yml; **src/test/java** holds tests. Both build systems recognize this layout by convention.
- **Maven Wrapper (mvnw)** and **Gradle Wrapper (gradlew)** run the tool version specified by the project, reducing differences between personal machines and CI. On Windows use **mvnw.cmd** or **gradlew.bat**; on macOS/Linux use **./mvnw** or **./gradlew**.
- The **target/** (Maven) and **build/** (Gradle) directories hold build-generated outputs, not places to write source code.

Spring Initializr lets you pick Maven or Gradle and pre-generates the corresponding structure. Inspecting the build files right after extraction tells you exactly which commands to run.

## 3. pom.xml: The Project Descriptor for Maven

Maven reads **pom.xml** to construct the project model and determine what to execute in each phase of the build lifecycle. The three elements **groupId**, **artifactId**, and **version** identify the artifact, for example com.example:demo-maven:0.0.1-SNAPSHOT.

A **complete, minimal pom.xml** for a Spring Boot web application:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>demo-maven</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

Sections to understand:

1. **parent**: Spring Boot starter parent inherits useful Maven configuration, including dependency management and plugin management. Therefore, the two starters in the example do not need explicit versions.
2. **properties/java.version**: declares the target Java version according to Spring Boot parent conventions; the build machine still needs a compatible JDK.
3. **dependencies**: describes libraries needed by the application. spring-boot-starter-web provides components for building web/APIs; spring-boot-starter-test is for testing thanks to the test scope. Maven resolves transitive dependencies as well.
4. **build/plugins**: spring-boot-maven-plugin adds goals for running and packaging Spring Boot; with the starter parent, the **repackage** goal is bound to the package phase to produce a JAR runnable via java -jar.
5. **packaging**: if omitted, Maven defaults to jar. You can set **war** if the project genuinely needs a WAR and corresponding configuration.

Maven has sequential lifecycle phases such as **compile → test → package → verify**. Invoking a later phase executes all preceding required phases. Some practical commands (run inside demo-maven):

~~~bash
./mvnw clean verify
./mvnw spring-boot:run
java -jar target/demo-maven-0.0.1-SNAPSHOT.jar
~~~

The first command deletes previous build outputs, compiles, runs tests, packages, and proceeds through the verify phase. The second runs directly during development; the third executes the artifact packaged by the Spring Boot plugin. On Windows, replace **./mvnw** with **mvnw.cmd**. If no wrapper is present, use an appropriately installed **mvn** on the machine.

**Maven BOM and version management:** Dependency management provided by the Spring Boot parent ensures libraries in the Boot ecosystem use a synchronized set of versions. You should not manually pin different versions on individual starters without a clear reason. Projects that do not use the starter parent can still import the **spring-boot-dependencies** BOM in dependencyManagement and configure plugins themselves; that is an alternative organization style.

## 4. settings.gradle: Declaring *Which Projects* Belong to the Gradle Build

Gradle's main phases are **initialization → configuration → execution**. During initialization, Gradle reads **settings.gradle** before build scripts to determine the root project and member projects.

For a single-module Spring Boot application, its content may only need:

~~~groovy
rootProject.name = 'demo-gradle'
~~~

This line sets the root project name, contributing to the default artifact name. **settings.gradle is not the primary place to declare application dependencies or compile/test tasks.** In newer Gradle versions, settings can also contain **pluginManagement { ... }** (plugin sources and resolution) and **dependencyResolutionManagement { ... }** (repository policies, version catalogs), though those configurations are only added when needed.

For a multi-module build, settings.gradle might contain:

~~~groovy
rootProject.name = 'learning-app'
include 'api', 'core'
~~~

This tells Gradle there are three projects: the root **learning-app**, **:api**, and **:core**. Each subproject typically has its own build.gradle, for example:

~~~text
learning-app/
├── settings.gradle
├── build.gradle
├── api/build.gradle
└── core/build.gradle
~~~

**include does not automatically create a dependency relationship.** If the api module uses code from core, build.gradle in api must declare the appropriate dependency, such as the following snippet:

~~~groovy
dependencies {
    implementation project(':core')
}
~~~

The snippet above is **one part** of build.gradle in the api module, not a standalone runnable build script. If the core module is an ordinary Java library, it typically uses the **java-library** plugin and does not need the Spring Boot plugin applied to every module.

## 5. build.gradle: Describing *How Each Project Is Built*

**build.gradle** uses Groovy DSL to configure plugins, tasks, repositories, dependencies, Java version, and build rules for the corresponding project. Here is a **complete, minimal build.gradle** for the demo-gradle example (paired with the single-module settings.gradle above):

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

Meaning of each block:

- **plugins**: the java plugin provides compilation, testing, and JAR creation; the Spring Boot plugin provides **bootRun**, **bootJar**, and Boot packaging behavior; the io.spring.dependency-management plugin enables importing the compatible BOM when paired with the Spring Boot plugin.
- **group/version**: specifies metadata and artifact version. The project name defaults from settings.gradle.
- **java.toolchain**: requests a Java 17 toolchain for Java tasks. A matching JDK must be available, or Gradle must be configured to auto-download toolchains when the environment supports it.
- **repositories**: mavenCentral() is where Gradle looks for application dependencies. **Plugin** repositories can be configured separately in settings.gradle.
- **dependencies**: implementation is for dependencies used by application code; testImplementation is for test code. Spring Boot's version set is managed by the BOM through the plugin configuration shown.
- **tasks.named('test')**: enables JUnit Platform to run JUnit 5 with the test configuration in the example.

When executing a task, Gradle builds a task graph and runs required dependent tasks. Common commands (in the demo-gradle directory):

~~~bash
./gradlew clean build
./gradlew bootRun
java -jar build/libs/demo-gradle-0.0.1-SNAPSHOT.jar
~~~

**build** invokes required steps such as compilation, testing, and assembly. With the Spring Boot configuration above, **bootJar** creates an executable JAR runnable with java -jar. Gradle may also generate **demo-gradle-0.0.1-SNAPSHOT-plain.jar** from the regular jar task; the **-plain.jar** file lacks the launcher/dependencies of an executable Boot JAR and is not used in place of bootJar. On Windows use **gradlew.bat**.

The Kotlin DSL equivalents are **settings.gradle.kts** and **build.gradle.kts**; they use Kotlin syntax, so you cannot copy the Groovy snippets above verbatim into .kts files.

## 6. Common Example: The Same Application Run via Maven or Gradle

To verify the configurations in sections 3 and 5, create the file:

**src/main/java/com/example/demo/DemoApplication.java**

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @RestController
    static class GreetingController {
        @GetMapping("/hello")
        public String hello() {
            return "Hello Spring Boot";
        }
    }
}
~~~

This is a **complete Java file**, usable in **either** example project. The **@SpringBootApplication** annotation enables auto-configuration and component scanning in the application's package; the nested controller is discovered and exposes the HTTP GET /hello endpoint. After running with **spring-boot:run** or **bootRun**, access:

~~~bash
curl http://localhost:8080/hello
~~~

HTTP response body:

~~~text
Hello Spring Boot
~~~

To run the JAR, execute the build command first, then use the exact executable JAR path shown for Maven or Gradle. This example requires a compatible JDK, ability to download dependencies from repositories, and port 8080 being free; it does not assert that all startup logs will be identical across every environment.

## 7. Maven and Gradle Handle Multi-Module Builds Differently

| Question | Maven | Gradle |
| --- | --- | --- |
| List of modules? | In the aggregator's **pom.xml**, declare **modules/module**; the aggregator usually has packaging pom. | In **settings.gradle**, declare **include**. |
| Where is each module configured? | Separate **pom.xml** for each module. | Separate **build.gradle** for each subproject; shared configuration can be placed in the root build or convention plugins. |
| Inter-module dependency? | The consuming module must declare a dependency using the target module's Maven coordinates. | The consuming module declares a project dependency, e.g., **implementation project(':core')**. |
| Build execution? | The Maven reactor determines build order based on dependency relationships. | Gradle builds a task graph from dependencies and the requested task. |

Example **illustrative XML snippet** in a Maven aggregator POM (not a full pom.xml file):

~~~xml
<packaging>pom</packaging>
<modules>
    <module>api</module>
    <module>core</module>
</modules>
~~~

As with Gradle include, listing Maven modules does not automatically mean the api module depends on core. Having multiple modules also does not require every module to be a Spring Boot application: a library module can produce a regular JAR, while the Boot startup module produces an executable JAR.

## 8. Build and Packaging: Distinguishing a Regular JAR from a Spring Boot Executable JAR

1. **Compilation** turns .java into .class, but compilation alone does not produce a standalone application runnable with java -jar.
2. **Testing** runs tests as configured. Maven's package phase and Gradle's build task usually include the test step; intentionally skipping tests can hide failures and should not be the default.
3. **Packaging** bundles classes/resources into an artifact. Spring Boot packaging typically adds a loader and dependent libraries so the executable JAR runs on any machine with a compatible Java runtime.
4. **Running** uses java -jar for the executable JAR. During development, Maven **spring-boot:run** and Gradle **bootRun** are more convenient when running from source.

| Need | Maven Wrapper | Gradle Wrapper |
| --- | --- | --- |
| Clean old build outputs | **./mvnw clean** | **./gradlew clean** |
| Run tests | **./mvnw test** | **./gradlew test** |
| Build with tests | **./mvnw clean verify** | **./gradlew clean build** |
| Run app from source | **./mvnw spring-boot:run** | **./gradlew bootRun** |
| Inspect dependencies | **./mvnw dependency:tree** | **./gradlew dependencies --configuration runtimeClasspath** |
| View build structure | **./mvnw help:effective-pom** (effective POM) | **./gradlew projects** (included projects) |

The artifact name depends on name/version/classifier settings. By default, the Maven example above creates **target/demo-maven-0.0.1-SNAPSHOT.jar**; the Gradle example uses **build/libs/demo-gradle-0.0.1-SNAPSHOT.jar** for the Boot JAR. When changing artifactId, rootProject.name, or version, the file name may change.

If you need a **WAR**, Maven uses war packaging with matching dependency/container configuration; Gradle applies the war plugin and uses the **bootWar** task. Do not switch to WAR just because you are using Spring Boot: an executable JAR is usually the simpler choice for standalone services.

## 9. Common Errors and How to Find the Cause

**Error 1 — Putting dependencies in settings.gradle and expecting build.gradle to pick them up automatically.** settings.gradle mainly defines structure and resolution policies. Direct application dependencies must be placed in the appropriate project's dependency configuration (or an intentionally designed shared configuration mechanism).

**Error 2 — Having include ':core' yet api still cannot import classes from core.** include only brings core into the build. You must declare the dependency **project(':core')** in api and ensure core applies an appropriate Java plugin to produce artifacts.

**Error 3 — Maintaining both pom.xml and build.gradle, editing one side and expecting the other to update.** Maven and Gradle have separate dependency/plugin management rules. Determine the primary build tool from the project's wrapper and CI commands.

**Error 4 — Missing dependency repository or using incompatible plugin/JDK versions.** Check **repositories**, plugin resolution sources, **java -version**, Gradle wrapper version, and Spring Boot version. Do not misdiagnose network errors as build syntax errors.

**Error 5 — Running the wrong plain JAR or skipping the packaging step.** With Gradle, favor the output of **bootJar** for java -jar; with Maven, check **spring-boot-maven-plugin** and the executable JAR after package. If you use a plain library JAR, it may lack the launcher or dependencies needed for a standalone Spring Boot application.

**Error 6 — Wrong source directory or main package/class.** The class with main must compile; the package declaration should match the conventional directory path. In the example, **com.example.demo.DemoApplication** resides under **com/example/demo/**, with `@SpringBootApplication` and a valid main method.

**Error 7 — Using Groovy syntax in build.gradle.kts.** .gradle.kts files are Kotlin DSL: string literals, plugins, and configuration syntax differ. Before copying snippets, check the file extension.

**Error 8 — Confusing build with deployment.** pom.xml/build.gradle describe the artifact and how to build it; they do not automatically decide whether the app runs on a server, Docker, or Kubernetes. Dockerfiles, runtime configuration, and deployment pipelines are subsequent steps outside the core responsibility of these three files.

## 10. How to Self-Check After Initialization

1. Choose **Maven** or **Gradle** on Spring Initializr; verify you have either pom.xml or the settings.gradle/build.gradle pair.
2. Open the file(s) to identify **project/artifact name, Java version, Spring Boot version, dependencies, and plugins**.
3. Create DemoApplication.java as shown in the example, use the wrapper to run tests/build, and inspect **target/** or **build/libs/**.
4. Run using the command for your chosen tool; call **GET /hello** and verify the response body.
5. If moving to multi-module, identify **where modules are declared** and **where inter-module dependencies are declared**; these are two separate responsibilities.

**Remember:** **pom.xml** describes how Maven builds the project; **settings.gradle** tells Gradle which projects participate in a build; **build.gradle** describes the plugins, dependencies, and tasks of those projects. Understanding this boundary helps you read Spring Boot project structures, fix initialization issues, and choose the right build/package commands.