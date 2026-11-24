# Resolving Library Conflicts When Packaging or Deploying a WAR

A Spring Boot application that runs smoothly in an IDE or via `java -jar` can still fail when packaged as a WAR and deployed to Tomcat, Jetty, or an enterprise application server. The cause usually lies in the **dependency graph**, **packaging scope**, **Servlet API version**, or **container classloader**. Errors like `NoSuchMethodError`, `NoClassDefFoundError`, `ClassCastException`, and warnings about multiple SLF4J providers signal that you must investigate the actual classpath rather than dropping random JARs into the server directory.

This lesson uses **Java 17, Spring Boot 3.3.13**, and a Spring MVC application packageable as an **executable WAR**. You will understand WAR structure, distinguish `WEB-INF/lib` from `WEB-INF/lib-provided`, configure Maven/Gradle properly for external servlet containers, locate conflicting library versions, distinguish `javax.servlet` from `jakarta.servlet`, inspect classloaders, and resolve errors by root cause. The build commands, WAR checks, and smoke tests apply directly to similar projects.

## 1. “Library Conflicts” Take Different Forms

Not every runtime failure is caused by two JARs sharing a name. Classify the issue before fixing:

| Conflict Type | Example | Where to Inspect |
| --- | --- | --- |
| **Version conflict in dependency graph** | Two libraries request different versions of `spring-core` | Maven dependency mediation or Gradle resolution |
| **Duplicate class** | Two artifacts with different coordinates both contain `com.example.Helper` | JAR/WAR contents, shaded JARs, vendor libraries |
| **Container vs. application library** | WAR carries embedded Tomcat in `WEB-INF/lib` while the server already supplies the Servlet container | WAR scopes and classloaders |
| **Namespace/API mismatch** | App uses `jakarta.servlet` while an older container/library still uses `javax.servlet` | Spring Boot, Servlet API, and container versions |
| **Multiple implementations for one role** | Both Tomcat and Jetty present; multiple SLF4J providers | Dependency tree and runtime classpath |
| **Classloader mismatch** | Same class name loaded by two different classloaders | Class-loading logs, server shared libraries |
| **Binary incompatibility** | Compiled against a newer API while runtime loads an older JAR | Actual versions in WAR and server |

Two situations must be clearly distinguished:

- **Version conflict**: multiple versions of the same module coordinates (group/artifact) are requested; the build tool applies rules to pick one version per configuration.
- **Duplicate class**: two different artifacts can both contain the same class. Maven/Gradle do not necessarily treat them as a module conflict, so the build succeeds yet runtime loads an unintended class.

A WAR can build green while still containing dependencies incompatible with the server. Therefore, inspect both the **dependency graph and the actual packaged archive**, then test on the exact type of container targeted for deployment.

## 2. What Classpath Regions Does a WAR Have?

A WAR per the Servlet specification typically has this structure:

```text
war-conflict-demo.war
└── WEB-INF/
    ├── classes/              # Application classes and resources
    ├── lib/                  # Application runtime libraries
    │   ├── spring-core-*.jar
    │   ├── spring-webmvc-*.jar
    │   └── ...
    └── web.xml               # May be absent with Spring Boot
```

The servlet container loads the application from `WEB-INF/classes` and the JARs in `WEB-INF/lib`. It also has shared libraries on the server's own classpath. Apache Tomcat documents that the Web application classloader reads `WEB-INF/classes`, `WEB-INF/lib`, and resources provided by Catalina.

A Spring Boot executable WAR adds a dedicated directory:

```text
WEB-INF/
├── classes/
├── lib/                      # Application dependencies
└── lib-provided/             # Provided runtime dependencies for Boot launcher
```

`WEB-INF/lib-provided` is Spring Boot's mechanism to hold dependencies marked `provided` for running the WAR via `java -jar`. When deploying the WAR to an external servlet container, the container uses `WEB-INF/classes` and `WEB-INF/lib` per the WAR spec; `lib-provided` dependencies are not placed onto the web application classpath as regular libraries. This allows keeping the embedded container inside the executable WAR without competing with the external server.

**This is the key point when resolving conflicts:** servlet container dependencies must be marked properly as `provided`/`providedRuntime`. If mistakenly packaged into `WEB-INF/lib`, the application may carry its own copy of Tomcat/Servlet API and collide with the server.

## 3. Executable WAR vs. Container-Deployed WAR

Spring Boot supports running the same WAR in two ways when configured properly:

1. **Standalone execution:** `java -jar war-conflict-demo-1.0.0.war`. The Boot launcher uses application dependencies and `lib-provided` to start the embedded server.
2. **Servlet container deployment:** copy the WAR into the deploy mechanism of Tomcat/Jetty/application server. The container initializes the app via the Servlet API and supplies its own server runtime.

To support traditional deployment, the app needs a class extending `SpringBootServletInitializer` and overriding `configure`. The `main` method can remain for standalone execution:

```java
package com.example.warconflict;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class WarConflictApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application) {
        return application.sources(WarConflictApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(WarConflictApplication.class, args);
    }
}
```

`SpringBootServletInitializer` allows the servlet container to discover and configure the Spring application context when the WAR is deployed. `main` serves executable WAR mode. You do not need two separate Spring applications for the two launch modes.

**Note:** Spring WebFlux does not support traditional WAR deployment in this manner because WebFlux uses embedded Reactor Netty by default and does not rely on the Servlet API. Examples in this lesson use Spring MVC with `spring-boot-starter-web`.

## 4. Java, Spring Boot, and Servlet Container Versions Must Be Compatible

This example selects Spring Boot **3.3.13**. Notable requirements of this line:

| Component | Requirement/Version in Example |
| --- | --- |
| Java | Java 17 or higher |
| Maven | 3.6.3 or higher |
| Gradle | 7.5+ in 7.x or 8.x |
| Spring Framework | 6.1.21 or higher per Boot 3.3.13 BOM |
| Servlet container | Servlet 5.0 or higher compatible |
| Reference Tomcat | Tomcat 10.1.x; Boot 3.3 supports Tomcat 10.1.25 or higher |

Tomcat 10.1 implements Servlet 6.0 and uses the Jakarta namespace. Tomcat 9 implements Servlet 4.0 from the legacy Java EE generation. **Tomcat 9 is not a compatible container for directly deploying a Spring Boot 3.3 WAR** due to the Servlet API generation mismatch.

Before building a WAR, know the target server:
- Container name and version (Tomcat, Jetty, Undertow, WebLogic, WebSphere...).
- Servlet specification version.
- JDK running the server.
- Shared libraries installed in server directories.
- Container classloader policies and delegation configuration.

Do not look solely at the Java version. Java 17 can run many servers, yet a server using an older Servlet API still cannot satisfy a Boot 3 application.

## 5. Common Symptoms When Deploying a WAR

| Error/Log | Possible Cause | First Investigation Step |
| --- | --- | --- |
| `NoSuchMethodError` | Class compiled against newer API, runtime loads older version | Identify which JAR actually provides the class |
| `NoSuchFieldError` | Two versions of the same library are incompatible | Compare dependency tree and WAR |
| `NoClassDefFoundError: javax/servlet/...` | Legacy library needs Java EE Servlet API while app uses Jakarta | Check `javax.servlet` dependencies and container |
| `NoClassDefFoundError: jakarta/servlet/...` | Container too old or Jakarta API absent at runtime | Check Servlet version and provided scope |
| `ClassCastException: X cannot be cast to X` | Same class name loaded by different classloaders | Check server shared libs and app libs |
| `LinkageError` | Incompatible class/API or duplicate class | Check class-loading logs and dependency graph |
| Multiple SLF4J providers/bindings | Multiple logging implementations present | Check SLF4J, Logback, Log4j2 |
| WAR runs with `java -jar`, fails on server deploy | Embedded container in `lib-provided` works, external container is incompatible or configured differently | Check target server and classloaders |
| Deploy succeeds, returns 404 | Wrong context path, servlet mapping, or component scan | Check WAR name, controller, and deployment logs |
| `UnsupportedClassVersionError` | Bytecode compiled higher than server JDK | Check Java target and runtime JDK |

An exception is a **symptom**, not a conclusion. For instance, `NoClassDefFoundError` can result from a missing JAR, wrong scope, wrong namespace, or a prior class initialization failure. Read both the root cause and the source class loaded by the JVM.

## 6. Java 17 Spring Boot Project for Practice

Project structure:

```text
war-conflict-demo/
├── pom.xml                         # Maven option
├── settings.gradle                 # Gradle option
├── build.gradle                    # Gradle option
└── src/
    ├── main/java/com/example/warconflict/
    │   ├── WarConflictApplication.java
    │   └── DiagnosticController.java
    └── test/java/com/example/warconflict/
        └── DiagnosticControllerTest.java
```

Maven and Gradle are **two alternative build options**. The Java source is shared.

### 6.1. Main Class Supporting Both Launch Modes

File `src/main/java/com/example/warconflict/WarConflictApplication.java`:

```java
package com.example.warconflict;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class WarConflictApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application) {
        return application.sources(WarConflictApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(WarConflictApplication.class, args);
    }
}
```

Package `com.example.warconflict` is chosen as the root package so component scan discovers controllers in the same package and subpackages.

### 6.2. Endpoint to Verify the WAR

File `src/main/java/com/example/warconflict/DiagnosticController.java`:

```java
package com.example.warconflict;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DiagnosticController {

    @GetMapping("/diagnostic")
    public String diagnostic() {
        return "war-conflict-demo-ok";
    }
}
```

When running, HTTP `GET /diagnostic` returns the body:

```text
war-conflict-demo-ok
```

This is the HTTP response body, not the entire startup log. A simple endpoint separates deployment/container issues from complex business logic errors.

### 6.3. Testing the Endpoint with MockMvc

File `src/test/java/com/example/warconflict/DiagnosticControllerTest.java`:

```java
package com.example.warconflict;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class DiagnosticControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void diagnosticEndpointReturnsExpectedBody() throws Exception {
        mockMvc.perform(get("/diagnostic"))
                .andExpect(status().isOk())
                .andExpect(content().string("war-conflict-demo-ok"));
    }
}
```

This test verifies Spring MVC mapping in the test context. It does not replace smoke testing on an actual servlet container because an external container has its own classloader, Servlet API, and server configuration.

## 7. Maven: Packaging a WAR and Marking Embedded Tomcat as `provided`

Complete `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>war-conflict-demo</artifactId>
    <version>1.0.0</version>
    <packaging>war</packaging>

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
            <artifactId>spring-boot-starter-tomcat</artifactId>
            <scope>provided</scope>
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
```

Key points:

1. `<packaging>war</packaging>` tells Maven to create a WAR.
2. `spring-boot-starter-web` provides Spring MVC and the embedded servlet container starter.
3. `spring-boot-starter-tomcat` is explicitly declared with `<scope>provided</scope>` so Maven treats Tomcat as a runtime supplied by the deployment environment.
4. `spring-boot-starter-test` is used only in tests.
5. The Spring Boot starter parent manages dependency versions and pre-configures the `repackage` execution for the plugin. When using this parent, do not add a duplicate `repackage` execution.

The Spring Boot Maven Plugin handles `provided` dependencies of an executable WAR by placing them in `WEB-INF/lib-provided`. That way the WAR can still run via `java -jar`, while an external servlet container will not pick up embedded Tomcat from `WEB-INF/lib`.

**Do not mark all libraries as `provided`.** Spring Framework, Jackson, logging, and business libraries still belong in the WAR unless the container genuinely supplies them under an explicit version contract. Normally, mark only the embedded servlet container and container-supplied APIs as `provided`.

## 8. Maven: Building and Inspecting WAR Contents

From the root directory:

```bash
java -version
./mvnw clean verify
```

If there is no Maven Wrapper, use a compatible installed Maven. On Windows PowerShell, use `.\mvnw.cmd clean verify`.

Expected artifact:

```text
target/war-conflict-demo-1.0.0.war
```

Inspect structure:

```bash
jar tf target/war-conflict-demo-1.0.0.war
```

Find classpath regions:

```bash
jar tf target/war-conflict-demo-1.0.0.war | grep '^WEB-INF/'
```

Key entries to look for:
- `WEB-INF/classes/com/example/warconflict/WarConflictApplication.class`.
- `WEB-INF/classes/com/example/warconflict/DiagnosticController.class`.
- `WEB-INF/lib/spring-webmvc-*.jar` and application dependencies.
- `WEB-INF/lib-provided/tomcat-embed-core-*.jar` along with embedded Tomcat libraries marked `provided`.

These are the **expected entry groups**; exact versions and file counts depend on the dependency graph. If embedded Tomcat appears in `WEB-INF/lib` instead of `WEB-INF/lib-provided`, check scopes in the effective POM and dependency tree.

### 8.1. Running the Executable WAR Standalone

```bash
java -jar target/war-conflict-demo-1.0.0.war
```

Another terminal:

```bash
curl -fsS http://localhost:8080/diagnostic
```

Result:

```text
war-conflict-demo-ok
```

If this step works yet deploying to Tomcat fails, the issue most likely lies in the **container version, classloader, or server-provided libraries**. If both fail, inspect the artifact and dependency graph first.

## 9. Gradle: Using the `war` Plugin and `providedRuntime`

File `settings.gradle`:

```groovy
rootProject.name = 'war-conflict-demo'
```

Complete `build.gradle` (Groovy DSL):

```groovy
plugins {
    id 'java'
    id 'war'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

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

    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

springBoot {
    mainClass = 'com.example.warconflict.WarConflictApplication'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The `war` plugin creates the `providedRuntime` configuration. The Spring Boot Gradle plugin creates the `bootWar` task for executable WARs and places `providedRuntime` dependencies into `WEB-INF/lib-provided`.

**`providedRuntime` is preferred over `compileOnly`** for the embedded servlet container in this scenario. `compileOnly` does not include the dependency on the test runtime classpath, which can cause web integration tests to fail. Do not add both Tomcat and Jetty as independent embedded servers to the same application unless you have explicitly configured which server is used.

Build:

```bash
./gradlew clean test bootWar
```

On Windows PowerShell, use `.\gradlew.bat clean test bootWar`.

The artifact from `bootWar` resides in `build/libs/`, for example:

```text
build/libs/war-conflict-demo-1.0.0.war
```

Inspect **the `bootWar` artifact**, not a plain WAR generated by the standard `war` task if the directory contains multiple files with similar names/classifiers.

### 9.1. Inspecting the Gradle WAR

```bash
jar tf build/libs/war-conflict-demo-1.0.0.war | grep '^WEB-INF/'
java -jar build/libs/war-conflict-demo-1.0.0.war
```

While running via `java -jar`, call from a second terminal:

```bash
curl -fsS http://localhost:8080/diagnostic
```

The expected body remains `war-conflict-demo-ok`. When deploying to a container, use the exact WAR from `bootWar` to preserve Spring Boot's executable/deployable packaging.

## 10. How Does Maven Resolve Version Conflicts?

Maven automatically collects both direct and transitive dependencies. When the same artifact is requested at multiple versions, Maven applies the **nearest definition** rule:
- The version on the dependency path closest to the project is chosen.
- If two versions are at the same depth, the declaration appearing first wins.
- A dependency version declared directly in the project can override a version requested on a transitive branch.
- `dependencyManagement` controls a dependency's version when it appears in the graph, yet **does not automatically add the dependency to the classpath**.

Example:

```text
war-conflict-demo
├── client-a
│   └── spring-core:6.1.x
└── client-b
    └── helper
        └── spring-core:6.0.x
```

In this illustrative example, the path to `spring-core:6.1.x` is closer to the project, so Maven picks that version. Maven does not inherently know which version best fits the entire Spring Boot platform; hence using a BOM/parent for coordinated version management is critical.

A dangerous situation is manually declaring an older Spring module:

```xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-webmvc</artifactId>
    <version>5.3.39</version>
</dependency>
```

This is **incompatible** with Spring Boot 3.3 because Boot 3.3 uses Spring Framework 6.1.x and the Jakarta namespace. Forcing `spring-webmvc` down to 5.3 while other Spring modules follow the 6.1 BOM creates binary incompatibility and mixes two API generations. The right fix is usually to **remove the version override** and let the Spring Boot BOM manage the entire Spring family.

## 11. Maven: Finding Which Version Was Actually Packaged

Diagnostic commands:

```bash
./mvnw dependency:tree
./mvnw dependency:tree -Dverbose
./mvnw dependency:tree -Dincludes=org.springframework:*
./mvnw help:effective-pom -Doutput=target/effective-pom.xml
```

Meaning:
- `dependency:tree` displays the resolved Maven dependency graph.
- `-Dverbose` reveals nodes omitted due to mediation, useful for tracing version conflicts.
- `-Dincludes` filters by group/artifact pattern to focus on Spring or a suspect library.
- `help:effective-pom` shows the POM after inheritance, profiles, and dependency management.

When looking for a specific JAR:

```bash
./mvnw dependency:tree -Dverbose -Dincludes=org.springframework:spring-core
./mvnw dependency:tree -Dverbose -Dincludes=org.slf4j:*
```

If the dependency tree shows the right version selected yet the WAR still behaves wrongly, inspect **the archive and classloader**. Maven's dependency tree does not reflect JARs manually copied into global server directories or classes shaded inside another JAR under different coordinates.

### 11.1. Excluding a Transitive Dependency in Maven

When an older library pulls in an unwanted dependency, you can exclude it on **that specific path**:

```xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>legacy-client</artifactId>
    <version>1.2.0</version>
    <exclusions>
        <exclusion>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-simple</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

`com.acme:legacy-client` is an example coordinate. Exclusions attach to that declared dependency; if another dependency also pulls in `slf4j-simple`, the artifact can still enter via the other branch. After excluding, re-run `dependency:tree` and test runtime logging.

**Do not exclude blindly.** If the library genuinely calls the excluded artifact's API, the app may build yet fail with `NoClassDefFoundError` when that code path executes. Replace it with a compatible implementation or upgrade the originating library.

## 12. How Does Gradle Resolve Version Conflicts?

Gradle selects the highest version by default when a module with the same group/name is requested at multiple versions within the same configuration. Actual decisions are also influenced by:
- Platform/BOM and dependency constraints.
- Strict version constraints.
- Variant attributes/capabilities.
- Resolution rules, substitution, and dependency forcing.
- The configuration being resolved (compile, runtime, provided, test).

For example, a direct dependency specifies an older version while another library requests a newer version:

```groovy
dependencies {
    implementation 'com.acme:client-a:1.0.0'
    implementation 'com.acme:client-b:1.0.0'
}
```

If both branches request `org.example:codec` at different versions, Gradle normally chooses the higher version per conflict resolution rules. However, a higher version is not automatically binary-compatible with every consumer. Inspect the selection reasons and test the app.

You can make the build fail immediately when a configuration sees multiple requested versions:

```groovy
configurations.configureEach {
    resolutionStrategy {
        failOnVersionConflict()
    }
}
```

This is an **optional guardrail** for projects wanting to manage conflicts explicitly. It can fail builds on graphs Gradle previously resolved automatically; enable it only when the team is ready to manage those conflicts. It does not catch every duplicate class coming from two distinct artifact coordinates.

## 13. Gradle: Diagnosing with `dependencies` and `dependencyInsight`

Run from the root project:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration providedRuntime
./gradlew dependencies --configuration testRuntimeClasspath
```

Use `dependencyInsight` for suspected modules:

```bash
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath
./gradlew dependencyInsight --dependency tomcat-embed-core --configuration providedRuntime
```

`dependencyInsight` explains:
- Which dependencies request that module.
- Which version was selected.
- Which versions were rejected/not selected.
- Selection reasons from constraints, conflict resolution, or rules.

In multi-module projects, run against the exact project path, e.g., `./gradlew :webapp:dependencyInsight --dependency spring-core --configuration runtimeClasspath`. Do not use a library module's configuration output to conclude the application module's WAR has the same classpath.

### 13.1. Excluding a Transitive Dependency in Gradle

Groovy DSL:

```groovy
dependencies {
    implementation('com.acme:legacy-client:1.2.0') {
        exclude group: 'org.slf4j', module: 'slf4j-simple'
    }
}
```

Kotlin DSL:

```kotlin
dependencies {
    implementation("com.acme:legacy-client:1.2.0") {
        exclude(group = "org.slf4j", module = "slf4j-simple")
    }
}
```

Both examples remove the module from that dependency branch. If another branch still pulls in that module, it can continue appearing. Always re-inspect `runtimeClasspath`/`providedRuntime` after changes and run tests.

## 14. BOM and Dependency Management: Avoid Mixing Spring Versions Manually

The Spring Boot starter parent or BOM manages versions aligned with one another. The POM example in section 7 inherits `spring-boot-starter-parent` 3.3.13, so starters and Spring modules need no individual versions.

If using a corporate parent instead of the Boot parent, import the Boot BOM in `dependencyManagement`:

```xml
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
```

This is a **snippet to merge into an existing POM**, not a complete POM. The BOM manages versions for declared dependencies; it does not automatically add `spring-boot-starter-web` or plugins to the project.

With Gradle, the Spring Boot plugin paired with the dependency-management plugin imports the Boot BOM automatically. If using a Gradle `platform` manually, declare the platform explicitly and consistently. Do not import multiple overlapping BOMs while also adding numerous explicit versions without checking selection reasons.

**Rule:** when upgrading Spring Boot, upgrade via the release's BOM/parent. Do not bump `spring-core`, `spring-webmvc`, `spring-context`, or Jackson individually without verifying the compatibility matrix.

## 15. Distinguishing `provided`, `runtime`, and `test` When Packaging a WAR

Scope dictates where a library lands:

| Scope/Configuration | Compile code | Test runtime | App runtime | Standard WAR |
| --- | --- | --- | --- | --- |
| Maven `compile` | Yes | Yes | Yes | `WEB-INF/lib` |
| Maven `runtime` | Not needed to compile | Yes | Yes | `WEB-INF/lib` |
| Maven `provided` | Yes | Yes | Provided by container | Excluded from normal `WEB-INF/lib`; Boot executable WAR puts in `lib-provided` |
| Maven `test` | No | Yes | No | No |
| Gradle `implementation` | Yes | Yes | Yes | `WEB-INF/lib` |
| Gradle `runtimeOnly` | Not needed to compile | Yes | Yes | `WEB-INF/lib` |
| Gradle `providedRuntime` | Suitable for provided runtime | Present on test runtime | Provided by container on external deploy | Boot WAR puts in `WEB-INF/lib-provided` |
| Gradle `compileOnly` | Yes | Not automatically on test runtime | Provided by environment | Not packaged |

For WARs deployed to external Tomcat:
- Embedded Tomcat starter is marked `provided` (Maven) or `providedRuntime` (Gradle).
- Spring MVC, Spring Context, Jackson, and application libraries remain in the WAR if the application needs them.
- The servlet container supplies the Servlet API to the application.
- Do not mistakenly mark business libraries as `provided` if the server does not supply them.

**Why doesn't Gradle use `compileOnly`?** Spring Boot recommends `providedRuntime` because it stays on the test runtime classpath, whereas `compileOnly` can cause web integration tests to lack container classes.

## 16. `javax.servlet` and `jakarta.servlet` Are Not Interchangeable

This is a major source of errors when upgrading applications to Spring Boot 3:

- Spring Boot 2 / Spring Framework 5 belong to the legacy Java EE generation and typically use `javax.servlet.*`.
- Spring Boot 3 / Spring Framework 6 moved to Jakarta EE and use `jakarta.servlet.*`.
- These are **two distinct namespaces**. A class implementing `javax.servlet.Filter` is not a `jakarta.servlet.Filter`, even though class and method names look alike.

Boot 3 code must import:

```java
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
```

Do not use:

```java
import javax.servlet.Filter;
```

if the class is compiled for Spring Boot 3.3/Jakarta Servlet.

When encountering `ClassNotFoundException: javax.servlet...` or `NoClassDefFoundError: javax/servlet/...` in a Boot 3 app, find the older dependency or vendor library not yet migrated. Adding both Servlet APIs to the WAR **does not** make a `javax` library Jakarta-compatible; you must upgrade or replace the library.

If deploying a Boot 3 WAR to Tomcat 9, the issue cannot be solved merely by changing dependency scopes. Use a container supporting Servlet 5.0+ and the Jakarta namespace, such as Tomcat 10.1, or keep the app on a generation compatible with the server until the container can be upgraded.

## 17. Do Not Package Multiple Servlet Containers Together

A Spring Boot web starter normally pulls in embedded Tomcat. If you simultaneously add Jetty/Undertow or another container starter without excluding the existing one, the WAR can contain competing implementations.

Configuration that should not coexist:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-tomcat'
    implementation 'org.springframework.boot:spring-boot-starter-jetty'
}
```

This is an intentionally wrong example. Pick **one** embedded container for executable WAR mode, mark it `provided` for external deployment, and ensure the WAR does not pull in another implementation inadvertently.

With external Tomcat:
- Keep `spring-boot-starter-tomcat` in `provided` scope/configuration.
- Do not manually drop embedded Tomcat JARs into `WEB-INF/lib`.
- Do not copy embedded Tomcat JARs into the server's shared lib directory.
- Do not add legacy Servlet APIs to the WAR.

If switching to Jetty or Undertow, swap the starter/container dependency properly and check matching versions/Servlet APIs. Do not exclude just one JAR while leaving other modules of the old container in the graph.

## 18. Logging Conflicts: Multiple SLF4J Providers or Logging Bridges

Spring Boot uses Logback by default via `spring-boot-starter-logging`. If the app switches to Log4j2, exclude the default logging starter as Spring Boot documents and add the Log4j2 starter.

Common issues:
- Multiple SLF4J providers present simultaneously.
- Both Logback and Log4j2 configured as backends.
- `slf4j-simple` or `slf4j-reload4j` pulled in by an older library.
- `commons-logging` packaged alongside conflicting bridges.
- Container server supplies a shared logging implementation conflicting with the app.

Check:

```bash
./mvnw dependency:tree -Dverbose -Dincludes=org.slf4j:*,ch.qos.logback:*,org.apache.logging.log4j:*
```

Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency slf4j-simple --configuration runtimeClasspath
```

An app should have **one explicitly chosen logging backend** and the required bridges for its stack. Do not add another provider just to silence warnings; that can drop logs, duplicate output, or pick different implementations locally vs. in the container.

## 19. Servlet Container Classloader and Shared Libraries

Build tools govern only the dependency graph inside the application. When the WAR runs, the container also brings the server's classpath:

```text
Container / parent classloader
├── Java platform classes
├── Container implementation and shared libraries
└── Web application classloader
    ├── WEB-INF/classes/
    └── WEB-INF/lib/*.jar
```

Tomcat defaults to a web application classloader that prioritizes the webapp's own libraries for most classes, yet certain API groups and core classes follow specific delegation rules. Other containers may have different policies or configurable parent-first delegation.

Server directories like `$CATALINA_BASE/lib` and `$CATALINA_HOME/lib` supply shared JARs across multiple web applications. Placing Spring, Jackson, logging, or business libraries here exposes them to other WARs and invites version/classloader collisions.

**Recommendations:**
- Keep application-specific libraries inside `WEB-INF/lib`.
- Let the server supply only the APIs/runtime it owns (Servlet/JSP/JNDI and explicitly governed components).
- Avoid copying application JARs into shared lib as a “quick fix” for missing classes.
- If an enterprise application server requires package preference/delegation configuration, follow that container's documentation and assess impact on other deployed apps.
- Do not flip the entire server to parent-first or local-first just to fix one WAR without evaluating the blast radius.

`ClassCastException: com.acme.Type cannot be cast to com.acme.Type` typically indicates two classes of the same name loaded by different classloaders. Two classes with identical fully-qualified names in different classloaders are still two distinct runtime types.

## 20. Checking Where the JVM Loads a Class From

When the dependency tree and WAR look clean yet the server still loads the wrong class, temporarily enable Java class-loading logs.

With Java 17:

```bash
java -Xlog:class+load=info -jar target/war-conflict-demo-1.0.0.war
```

Logs can reveal which JAR or source loaded the class. When running inside external Tomcat, add the same flag to `CATALINA_OPTS` or the container service's JVM options and restart the server per operational procedures.

Bash example:

```bash
export CATALINA_OPTS="$CATALINA_OPTS -Xlog:class+load=info"
```

Class-loading logs can be huge. Enable them only for a single diagnostic run, filter for relevant packages like `org.springframework`, `org.slf4j`, `jakarta.servlet`, or the failing class, and disable afterward.

Another diagnostic check is inspecting a class's code source in Java:

```java
private static void printClassOrigin(Class<?> type) {
    var source = type.getProtectionDomain().getCodeSource();
    String location = source == null
            ? "<container, bootstrap, or unknown source>"
            : source.getLocation().toString();

    System.out.println(type.getName()
            + " -> " + location
            + " | loader=" + type.getClassLoader());
}
```

This is an **illustrative diagnostic method**, not a standalone Java file. Some JVM/container classes return `null` for `CodeSource`; in that case, use class-loading logs and container diagnostics.

## 21. Ordered Conflict Resolution Workflow

When a WAR fails, proceed step by step instead of changing multiple dependencies at once:

1. **Record the failing environment:** Java, Spring Boot, Maven/Gradle, container and version, context path, JVM flags.
2. **Classify the exception:** missing class, incompatible method, duplicate provider, namespace mismatch, or classloader mismatch.
3. **Inspect the dependency graph:** Maven `dependency:tree -Dverbose` or Gradle `dependencyInsight`.
4. **Verify scopes:** are container dependencies properly marked `provided`?
5. **Inspect the actual WAR:** check `WEB-INF/classes`, `WEB-INF/lib`, and `WEB-INF/lib-provided`.
6. **Check container version:** Servlet specification, Jakarta namespace, and runtime JDK.
7. **Check server shared libraries:** `CATALINA_BASE/lib`, `CATALINA_HOME/lib`, or equivalent application server mechanism.
8. **Identify class origin:** temporarily enable class-loading logs if the graph alone is inconclusive.
9. **Fix one root cause:** align BOM/version, remove duplicate, adjust scope, upgrade container, or migrate library.
10. **Rebuild and re-test:** unit/integration tests, run `java -jar`, and deploy to the exact target container type.
11. **Compare the new WAR:** confirm only the intended JARs changed, with no unintended libraries added.
12. **Document the change:** selected version, excluded dependencies, rationale, and smoke test results.

Do not bump all versions to latest at once. One upgrade may solve `NoSuchMethodError` while introducing an API mismatch for another dependency.

## 22. Scenario-Based Fixes

### 22.1. Two Versions of Spring Framework

**Symptom:** `NoSuchMethodError` in `org.springframework` or multiple Spring versions in dependency reports.

**Resolution:**
- Remove manually declared Spring versions.
- Let the Spring Boot BOM manage all Spring modules.
- If using a corporate parent, import the right Boot BOM.
- Verify with Maven effective POM/Gradle `dependencyInsight`.
- Do not upgrade `spring-core` alone while keeping `spring-webmvc` or `spring-context` on a different version.

### 22.2. Embedded Tomcat Packaged Wrongly

**Symptom:** Externally deployed WAR throws Servlet/container errors, or classes load from embedded Tomcat instead of the server.

**Resolution:**
- Maven: mark `spring-boot-starter-tomcat` as `provided`.
- Gradle: place `spring-boot-starter-tomcat` in `providedRuntime`.
- Rebuild the executable WAR.
- Verify embedded Tomcat is in `WEB-INF/lib-provided`, not `WEB-INF/lib`.
- Confirm the target server meets Boot's Servlet API requirement.

### 22.3. Legacy Library Using `javax` in a Boot 3 App

**Symptom:** `NoClassDefFoundError: javax/servlet/...` or incompatible filter/listener classes.

**Resolution:**
- Identify which library still imports `javax.servlet`.
- Upgrade to a Jakarta-supporting release or swap to another library.
- Remove legacy Java EE APIs from the dependency graph.
- Recompile and test on a Jakarta-compatible Servlet container.
- Do not attempt to add both `javax.servlet-api` and `jakarta.servlet-api` to the WAR as a fix.

### 22.4. Multiple Logging Providers

**Symptom:** SLF4J reports multiple providers/bindings, or logs duplicate/disappear.

**Resolution:**
- Inspect the dependency tree for `org.slf4j`, Logback, and Log4j2.
- Pick one backend.
- Exclude the provider pulled in by the legacy library on that specific dependency path.
- Also check server shared libraries if the container supplies its own logging implementation.

### 22.5. `ClassCastException` with the Same Class Name

**Symptom:** `X cannot be cast to X` despite identical package/class names.

**Resolution:**
- Inspect the classloaders of both objects.
- Check class-loading logs to find the JAR/source.
- Check whether the JAR sits in both server shared lib and `WEB-INF/lib`.
- Remove the redundant copy or adjust container-specific configuration carefully.
- Avoid hacking around it with casts or class renames when the root cause is classloader isolation.

## 23. Quick Troubleshooting Table

| Symptom | Check | Priority Resolution |
| --- | --- | --- |
| `NoSuchMethodError` in Spring | Versions of `spring-core`, `spring-web`, `spring-context` | Align via Boot BOM |
| `NoClassDefFoundError: jakarta.servlet` | Container Servlet version, WAR scopes | Use Servlet 5.0+ container and proper `provided` config |
| `NoClassDefFoundError: javax.servlet` | Legacy dependency or wrong container generation | Upgrade library to Jakarta or use compatible platform |
| Embedded Tomcat in `WEB-INF/lib` | POM scope/Gradle configuration | Move Tomcat starter to `provided`/`providedRuntime` |
| WAR fails with `java -jar` | Missing Boot `repackage`/`BootWar` or picked plain WAR | Build with Spring Boot plugin and select executable artifact |
| WAR runs standalone, fails on server deploy | Container version, classloader, shared libs | Test on target container and inspect class origins |
| `ClassCastException` with same class name | Classloader identity | Locate class loaded from two sources |
| SLF4J reports multiple providers | Logging dependency tree | Keep only one backend/bridge stack |
| Two library versions in Maven tree | Nearest mediation, direct override, BOM | Use `dependencyManagement` and remove bad overrides |
| Gradle selects unexpectedly high version | `dependencyInsight`, constraints | Manage platform/constraints with clear rationale |
| WAR contains unused libraries | Runtime graph, transitive dependencies | Analyze, safely exclude unused dependencies, and test |
| Deploy 404 | WAR name/context path/mapping | Check URL against actual context path |
| App fails to load due to Java bytecode | Server JDK lower than target | Align Java toolchain and runtime JDK |
| Container has Spring JAR in global lib | Server shared library path | Remove or govern shared versions per policy |
| Build fails on duplicate archive entry | Plugin/packaging resources, shaded dependencies | Locate duplicate entry, handle source JAR properly |

## 24. CI/CD Checks for WARs

A pipeline should validate multiple layers:

```bash
./mvnw -B clean verify
./mvnw dependency:tree -Dverbose
jar tf target/war-conflict-demo-1.0.0.war
```

With Gradle:

```bash
./gradlew clean test bootWar
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration providedRuntime
jar tf build/libs/war-conflict-demo-1.0.0.war
```

Important checks:
- Java/toolchain and Spring Boot plugin versions comply with policy.
- Dependency graph contains no unexpected overrides.
- Embedded container resides in `provided` scope/configuration.
- WAR contains application classes and required runtime dependencies.
- Neither `javax.servlet-api` nor multiple embedded containers are packaged accidentally.
- No unintended duplicate SLF4J providers exist.
- Executable WAR runs via `java -jar` if that mode is supported.
- WAR deploys to a container of the same type/version as production.
- Health/smoke endpoints return expected responses.
- Image/artifact is scanned and checksum/provenance recorded per policy.

**Do not test only with `java -jar`.** Standalone execution uses the embedded container in `lib-provided`; an external container may have different classloaders, APIs, and server configurations. Perform at least one integration/deployment test on the target container or an equivalent staging environment.

## 25. Pre-Release Checklist

- [ ] Spring Boot, Spring Framework, Java, and servlet container fall within the compatibility matrix.
- [ ] Application extends `SpringBootServletInitializer` to support traditional WAR deployment.
- [ ] `main` method is retained if executable WAR mode is needed.
- [ ] Maven specifies `<packaging>war</packaging>` or Gradle applies the `war` plugin.
- [ ] Embedded servlet container is marked `provided`/`providedRuntime`.
- [ ] Gradle uses `providedRuntime` instead of `compileOnly` for container runtime needed in tests.
- [ ] WAR contains `WEB-INF/classes` and needed application libraries in `WEB-INF/lib`.
- [ ] Executable WAR's provided runtime sits in `WEB-INF/lib-provided`.
- [ ] No wrong-generation Servlet API or incompatible mix of `javax` and `jakarta` is packaged.
- [ ] No unintended competing Tomcat/Jetty/Undertow starters exist.
- [ ] Spring modules and Jackson are managed via the Boot BOM or an approved platform.
- [ ] Dependency tree and `dependencyInsight` have been reviewed.
- [ ] No duplicate logging providers exist.
- [ ] No application libraries were manually copied into server shared libs.
- [ ] Checked class-loading logs when unexplained runtime errors occurred.
- [ ] Unit/integration tests and WAR smoke tests pass.
- [ ] Tested deployment on a servlet container matching production.
- [ ] Deployed artifact is the proper executable/deployable WAR, not a plain WAR.
- [ ] Recorded version graph, container/JDK versions, and artifact checksum for rollback.

**Conclusion:** Resolving WAR conflicts requires checking three layers: **dependency resolution** (which version is selected), **archive packaging** (which JARs land in `WEB-INF/lib` vs. `lib-provided`), and **runtime classloading** (where the container actually loads classes from). Maven uses nearest-definition mediation; Gradle defaults to the higher version on version conflicts; both still require BOMs/constraints and archive inspection. With Spring Boot 3, use a Jakarta-compatible servlet container and place the embedded server in `provided` scope when deploying WARs externally. Consider an issue resolved only once the WAR builds cleanly, runs standalone as required, and deploys successfully on the actual target container.

## Official References

- [Spring Boot 3.3 — Traditional Deployment](https://docs.spring.io/spring-boot/3.3/how-to/deployment/traditional-deployment.html)
- [Spring Boot 3.3.13 — System Requirements](https://docs.spring.io/spring-boot/3.3/system-requirements.html)
- [Spring Boot 3.3 — Maven Plugin: Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html)
- [Spring Boot 3.3 — Gradle Plugin Packaging](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)
- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — Optional and Excluded Dependencies](https://maven.apache.org/guides/introduction/introduction-to-optional-and-excludes-dependencies)
- [Apache Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
- [Gradle — Dependency Constraints and Conflict Resolution](https://docs.gradle.org/current/userguide/dependency_constraints_conflicts.html)
- [Gradle — Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html)
- [Gradle — The War Plugin](https://docs.gradle.org/current/userguide/war_plugin.html)
- [Apache Tomcat 10.1 — Class Loader How-To](https://tomcat.apache.org/tomcat-10.1-doc/class-loader-howto.html)
- [Apache Tomcat 10.1 — Loader Component](https://tomcat.apache.org/tomcat-10.1-doc/config/loader.html)
- [Spring Boot 3 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide)