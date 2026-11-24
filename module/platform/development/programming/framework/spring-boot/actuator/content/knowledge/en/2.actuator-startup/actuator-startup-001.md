# Adding spring-boot-starter-actuator with Maven or Gradle

## 1. Adding the starter to give an application operational capabilities

A Spring Boot application that already runs does not necessarily have Actuator capabilities. To add them, the standard approach is to declare the dependency:

~~~text
org.springframework.boot:spring-boot-starter-actuator
~~~

A **Starter** is a dependency declaration entry point: the build tool fetches the relevant libraries and places them into the application's library set. As a result, the application author does not have to manually select each Actuator component and its corresponding auto-configuration.

Once the libraries are present, Spring Boot also evaluates conditions to auto-configure the appropriate capabilities. Adding the starter does not mean every endpoint is exposed or that the application already has a centralized monitoring system.

The official syntax for adding the starter is presented in [Spring Boot 3.3 — Enabling Production-ready Features](https://docs.spring.io/spring-boot/3.3/reference/actuator/enabling.html).

This lesson uses Spring Boot **3.3.13** as the concrete example version and JDK **21**. Spring Boot 3.3.13 requires Java 17 or higher, and supports Maven 3.6.3 or higher and Gradle 7.x lines from 7.5 or 8.x. For Gradle examples running on JDK 21, wrapper 8.5 can be used, which already supports running Gradle on Java 21. See [Gradle 8.5 — Release Notes](https://docs.gradle.org/8.5/release-notes.html). When working on an existing project, keep the version line and wrapper already established by the project. See [Spring Boot 3.3 — System Requirements](https://docs.spring.io/spring-boot/3.3/system-requirements.html).

## 2. Distinguishing dependency, BOM, and plugin

These three components have different responsibilities:

| Component | Role | Does it automatically add the Actuator starter to the application? |
| --- | --- | --- |
| Dependency `spring-boot-starter-actuator` | Instructs the build tool to fetch the starter and required dependencies | Yes, when declared in the appropriate scope |
| BOM `spring-boot-dependencies` | Provides a managed set of versions for dependencies | No; version management does not replace a usage declaration |
| Spring Boot Maven/Gradle plugin | Adds capabilities to build, package, and run a Boot application | Does not automatically add all starters to the application |

A **BOM (Bill of Materials)** is a version management catalog. Spring Boot provides one BOM per version so that libraries are selected consistently. When a project already uses that management mechanism, the starter declaration usually does not need a separate version. See [Spring Boot 3.3 — Build Systems](https://docs.spring.io/spring-boot/3.3/reference/using/build-systems.html).

For example, setting the Boot version in the parent to 3.3.13 while forcing Actuator alone onto a different line can create an inconsistent dependency graph. Let the shared management mechanism choose the version, unless the project has an intentional, verified override.

In a multi-module project, identify the **application module that actually runs** and where its dependencies are managed. Adding the starter only to a module not used by the application, or only listing it in a version catalog, will not make the starter appear in the running application.

## 3. Maven option

### 3.1. Projects already using a Spring Boot parent or BOM

Add to the `<dependencies>` section of the application module:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

This is a dependency element to merge into an existing POM, not a complete file. There is no need to add `<version>` if the parent/BOM already manages the starter. Do not place the starter in the `test` scope if you want it present when running the main application.

It is also unnecessary to directly declare `spring-boot-actuator` and `spring-boot-actuator-autoconfigure` just to "enable enough". The starter already brings in the related components through the dependency graph.

### 3.2. Complete POM for a sample project

If you need a small project to observe Actuator over HTTP, you can use the following `pom.xml`. Choose either this Maven option or the Gradle option in the next section for the same example.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>actuator-start-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
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

Roles of the sections:

- The parent manages common versions and build configurations.
- `java.version` selects the Java level for the sample project; the build machine needs a compatible JDK.
- The Web starter provides the Servlet web foundation for the HTTP call example.
- The Actuator starter adds the operational libraries.
- The Boot Maven plugin supports running and packaging the application.

The Boot parent provides dependency management and plugin defaults; therefore, the POM above does not repeat versions for each starter or for the Boot Maven plugin. See [Spring Boot 3.3 — Using the Maven Plugin](https://docs.spring.io/spring-boot/3.3/maven-plugin/using.html).

### 3.3. When the project must keep its own parent

If the project already inherits from another parent, there is no need to replace that parent just to use Actuator. You can import the Boot BOM in `dependencyManagement`:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.13</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

This is a snippet to merge into an existing POM. You still must declare the starter in the application's `<dependencies>`.

Importing the BOM only provides dependency management; it does not carry over all plugin management and compiler defaults of `spring-boot-starter-parent`. A project keeping its own parent needs appropriate Java/compiler configuration and the Boot plugin if it wants to use the corresponding run or packaging commands. Do not treat this BOM snippet alone as a complete project.

## 4. Gradle option

### 4.1. Projects that already have Spring Boot version management

With Groovy DSL in `build.gradle`, add to the existing dependencies block:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

With Kotlin DSL in `build.gradle.kts`, the corresponding syntax is:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
}
~~~

Both snippets assume the version is already provided by the dependency-management plugin or a BOM. Do not omit the version and expect Gradle to guess it when the project has no management mechanism yet.

`implementation` is the usual choice for an application example. If only `testImplementation` is used, the dependency belongs only to testing; if `compileOnly` is used, it is not included on the main application's runtime classpath.

### 4.2. Complete example using Groovy DSL

In `settings.gradle`:

~~~groovy
rootProject.name = 'actuator-start-demo'
~~~

In `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

When applying both the Boot plugin and `io.spring.dependency-management`, the Boot plugin integrates to import the BOM corresponding to the Boot version in use. That is why the two starters do not need separate versions.

The Gradle wrapper must be available and compatible, such as 8.5 for this example. JDK 21 needs to be installed or have a toolchain provisioning mechanism configured; declaring a toolchain alone does not guarantee a machine without a JDK will automatically download it.

### 4.3. If the project uses Gradle's native BOM support

Another option is to keep the `java` plugin and the Boot plugin without `io.spring.dependency-management`, and declare a platform:

~~~groovy
dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

This is a variant of the **version management mechanism**; there is no need to add both approaches simultaneously just for the starter to work. In this variant, keep the BOM version consistent with the Boot plugin version.

Gradle `platform` introduces version constraints into the dependency graph; other declarations or constraints can still influence the actual version selected. Therefore, inspect the resolution result rather than looking only at a single BOM line. Both mechanisms are explained in [Spring Boot 3.3 — Managing Dependencies with Gradle](https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html).

## 5. What does the starter bring into the application?

The main relationships can be visualized as follows:

~~~text
Application
└── spring-boot-starter-actuator
    ├── common starter foundation
    ├── spring-boot-actuator-autoconfigure
    │   └── spring-boot-actuator
    └── related Micrometer components
~~~

The diagram only shows the relationships you need to understand, not the full dependency tree. The published POM of starter 3.3.13 lists the direct dependencies, while downstream libraries continue to be resolved by the build tool. You can cross-reference at [Maven Central — spring-boot-starter-actuator 3.3.13](https://central.sonatype.com/artifact/org.springframework.boot/spring-boot-starter-actuator/3.3.13).

From the user's perspective:

- **Starter** is a convenient declaration entry point.
- **Actuator** contains the operational components.
- **Actuator auto-configuration** integrates them according to the application's conditions.
- **Version management mechanism** helps keep components compatible with the chosen Boot line.

There is no need to manually extract JARs and copy libraries into the source. Maven/Gradle are responsible for downloading and organizing dependencies based on declarations.

### Having Actuator does not automatically mean having an HTTP server

The Actuator starter does not replace the Web starter. If the project lacks an appropriate web foundation, adding Actuator alone will not turn it into an HTTP application on port 8080.

The sample example in this lesson adds the Web starter because it needs to call health over HTTP. If the application already uses WebFlux and is designed around the reactive model, keep that foundation; do not add Web MVC just because you want to use Actuator. Non-HTTP applications can still use operational capabilities appropriate for their configuration.

## 6. Sample application shared by both options

After choosing Maven or Gradle, create the file:

~~~text
src/main/java/example/actuatorstarter/ActuatorStarterApplication.java
~~~

Full Java content:

~~~java
package example.actuatorstarter;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ActuatorStarterApplication {
    public static void main(String[] args) {
        SpringApplication.run(ActuatorStarterApplication.class, args);
    }
}
~~~

There is no need to write your own controller for health, and there is no mandatory separate annotation such as "EnableActuator" in this Boot 3.3 example.

In `src/main/resources/application.yml`:

~~~yaml
server:
  address: 127.0.0.1
  port: 8080
~~~

The configuration listens only on loopback for local testing. The example assumes no Spring Security, no context path change, no separate management port, and no configuration disabling health.

There is no need to expose all endpoints for initial verification: in Spring Boot 3.3, health is exposed over HTTP by default. Enabling an endpoint, exposing it over HTTP, and granting access permissions are distinct decisions. See [Spring Boot 3.3 — Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

### 6.1. Running with Maven

If the project already has the Maven wrapper:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

If using an installed Maven instead of the wrapper, the corresponding command is `mvn spring-boot:run`, run inside the directory containing the application POM. The run goal is provided by the Spring Boot Maven plugin. See [Spring Boot 3.3 — Running with Maven](https://docs.spring.io/spring-boot/3.3/maven-plugin/run.html).

### 6.2. Running with Gradle

If the project already has the Gradle wrapper:

~~~powershell
.\gradlew.bat bootRun
~~~

Run inside the appropriate project directory; in a multi-module project, invoke the task for the right application module. BootRun uses the runtime classpath of the main application code. See [Spring Boot 3.3 — Running with Gradle](https://docs.spring.io/spring-boot/3.3/gradle-plugin/running.html).

Run only one option at a time if both use the same port 8080.

### 6.3. Calling health and reading the right evidence

After the application starts successfully, open another PowerShell window:

~~~powershell
curl.exe --silent --show-error --include http://127.0.0.1:8080/actuator/health
~~~

When existing health checks are healthy, the status code is usually 200 and the minimal body is:

~~~json
{"status":"UP"}
~~~

This is the HTTP body; it is not a line printed to stdout by the main method. Headers, timestamps, and startup logs can vary, so do not treat them as fixed output.

If calling `/` returns 404 in the minimal example, that does not prove Actuator is broken: the code above declares no controller or home page for the root path.

Also do not use the fact that another endpoint is not yet accessible to conclude that the starter was not loaded. Check the dependency, startup state, and configuration of that specific endpoint separately.

## 7. Verifying that the dependency was actually resolved

Editing the build file is only the declaration step. You need to reload the Maven/Gradle model in the IDE, then rebuild or rerun the application with the new classpath.

### 7.1. Maven: viewing the dependency tree

~~~powershell
.\mvnw.cmd dependency:tree "-Dincludes=org.springframework.boot:spring-boot-starter-actuator"
~~~

Look for a node with the corresponding coordinates:

~~~text
org.springframework.boot:spring-boot-starter-actuator:jar:3.3.13:compile
~~~

The snippet above is the **coordinate to recognize**, not the entire console output. If the project uses a different Boot version, read the project's actual version.

To inspect the underlying components as well:

~~~powershell
.\mvnw.cmd dependency:tree "-Dincludes=org.springframework.boot:spring-boot-actuator,org.springframework.boot:spring-boot-actuator-autoconfigure"
~~~

The Maven Dependency Plugin supports the `dependency:tree` goal and the `includes` filter. See [Apache Maven — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html).

### 7.2. Gradle: viewing the selected version and reason

~~~powershell
.\gradlew.bat dependencyInsight --dependency spring-boot-starter-actuator --configuration runtimeClasspath
~~~

Check:

1. Is there a dependency matching the starter name?
2. What version was selected?
3. Was it re-selected due to a constraint or conflict with another declaration?
4. Are you inspecting the right configuration of the main application?

You can view more broadly using:

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
~~~

The `dependencies` and `dependencyInsight` reports let you inspect the actual graph instead of guessing from the build file. See [Gradle — Viewing Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html).

### 7.3. Checking across three layers of evidence

| Verification layer | Evidence to look for | What is it not enough to conclude? |
| --- | --- | --- |
| Declaration | Starter is properly located in the application's POM/build.gradle | Does not prove dependencies were downloaded successfully |
| Resolution | Dependency tree/runtimeClasspath has the starter and appropriate version | Does not prove the application started successfully |
| Running application | Process starts and the expected endpoint responds under the right conditions | One successful call does not prove every endpoint is exposed |

The first build may require network access to download the parent, BOM, plugins, Gradle distribution, and JARs. Offline mode works only when the required components are already in the appropriate cache.

If the tool cannot download a dependency, distinguish wrong coordinates/versions from network, proxy, repository, or offline-mode issues. Do not randomly switch to a different starter version just to make the error message go away.

## 8. Common mistakes when adding the starter

| Symptom | What to check |
| --- | --- |
| Maven reports dependency missing version | Is the parent/BOM actually applied to the application module? |
| Gradle cannot find version for starter without version | Is there a dependency-management plugin or BOM in the appropriate configuration? |
| Starter is in version management but absent from dependency tree | Was the starter declared for use in dependencies? |
| IDE recognizes library but running application lacks Actuator | Did you rebuild/rerun the right module with the new runtime classpath? |
| Only tests have Actuator | Was it mistakenly placed in `test` or `testImplementation`? |
| Project has no HTTP server | Does it have an appropriate web foundation, or is this a non-web application? |
| Health is not at the default address | Check port, context path, management base path, exposure, and security |
| Adding multiple Actuator dependencies with explicit versions "to be sure" | Review the starter and shared version management mechanism first |
| Task bootRun does not exist where invoked | Is the Boot plugin applied to the right application project? |
| Multi-module project but added to an unused module | Check the dependency graph of the module that actually launches |

There is no need to open `management.endpoints.web.exposure.include=*` to fix a dependency download error. Exposure controls the operational interface exposed over HTTP; it does not fix a POM, download JARs, or resolve version conflicts.

### Practice on your own

1. For a Boot application that already has a parent/BOM, write the minimal Actuator declaration using the build tool in use.
2. Point out which line manages the version and which line actually adds the starter in the Maven or Gradle example.
3. Use dependency tree/insight to find the selected version; if the version changed, read the reason instead of looking only at the declared version.
4. Run the sample project and call health. If unreachable, classify the issue as library loading, application startup, HTTP mapping, or access permissions.
5. Explain why adding Actuator to `testImplementation` or only importing the BOM does not satisfy using Actuator when running the main application.

**Reference hint:** you need all three at once: a usage declaration in the right scope, a properly resolved version, and a runtime configuration that meets the conditions of the desired capability. Maven/Gradle fetch the libraries; Spring Boot creates the appropriate configuration; HTTP endpoints appear only according to the corresponding environment and configuration.
