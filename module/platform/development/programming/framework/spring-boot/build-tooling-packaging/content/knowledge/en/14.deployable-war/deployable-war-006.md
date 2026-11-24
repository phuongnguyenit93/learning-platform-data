# Managing the Embedded Server via Maven `provided` and Gradle `providedRuntime` in Spring Boot WAR Packaging

## 1. Scenario: One Application, Two WAR Startup Styles

A **Spring Boot Servlet Web** application may need to be deployed in two ways:

- **Standalone execution:** `java -jar war-demo.war`. The application must include embedded server libraries, such as embedded Tomcat, to start a web server itself.
- **Deployment to an external Servlet server:** place `war-demo.war` into a compatible Tomcat or container. The external container already provides the servlet engine, thread pools, HTTP connectors, and parts of the related APIs; the app should not force the container to load a competing embedded engine inside `WEB-INF/lib`.

These two requirements seem contradictory: **the embedded server must be present when running `java -jar`, yet must not conflict when an external container deploys the WAR**. Spring Boot resolves this with a **special WAR layout** and a dependency marking rule:

- Maven: `<scope>provided</scope>` on `spring-boot-starter-tomcat`.
- Gradle: `providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'` when using the `war` plugin.

When packaged properly by the Spring Boot Maven Plugin or Gradle Plugin, those dependencies are placed into **`WEB-INF/lib-provided/`**, not `WEB-INF/lib/`. The standalone path via **`WarLauncher`** still sees them; external containers do not treat `WEB-INF/lib-provided` as a standard application library directory, avoiding a competing embedded Tomcat.

**Goal:** distinguish scopes/configurations properly, write matching POM and Gradle builds, produce a WAR that is both executable and deployable, verify `WEB-INF/lib-provided` via `jar tf`, run `java -jar`, and know how to verify deployment onto an external Servlet container. Do not accept "the build is green, so the WAR is safe to deploy" without real verification.

### 1.1. What `provided` Does NOT Mean

- **It does not mean** "remove the library everywhere": a Spring Boot executable WAR **still contains** the library inside `WEB-INF/lib-provided`.
- **It does not mean** "skip tests": Maven `provided` is present on compile/test classpaths; Gradle `providedRuntime` is specifically preferred because it works cleanly with test runtime.
- **It does not mean** "turn off embedded Tomcat with one property": development run commands and standalone execution require the corresponding runtime classpath.
- **It does not mean** Spring Boot automatically knows every third-party container is compatible: Servlet API, `jakarta.*`, Tomcat/Jetty versions, logging, and shared server libraries still must be verified.
- **It does not mean** a JAR and a WAR share the same layout: an executable JAR uses `BOOT-INF`, whereas a WAR uses `WEB-INF`.

In this article, we use **Java 17, Spring Boot 3.3.13**, and a compatible Maven or Gradle setup for illustration. These are **intentionally pinned illustrative versions**, not a claim of the latest or supported versions at the time of reading. Confirm your project's actual version and support policy before choosing a toolchain.

## 2. Distinguishing an Embedded Server from an External Servlet Container

### 2.1. Running Standalone with Embedded Tomcat

With `spring-boot-starter-web`, Spring Boot 3.3 typically includes Spring MVC and defaults to the Tomcat Servlet web server. When the app runs via `java -jar` or `spring-boot:run`/`bootRun` with the proper classpath:

1. `main(String[] args)` calls `SpringApplication.run(...)`.
2. Spring Boot creates the application context, auto-configures the web server factory, and initializes embedded Tomcat.
3. Tomcat binds the port specified by `server.port` (for example, 18085).
4. HTTP requests enter the application's JVM process directly.

With an executable WAR, `WarLauncher` beforehand prepares the classpath from `WEB-INF/classes`, `WEB-INF/lib`, **and** `WEB-INF/lib-provided`. Thus the embedded server in `lib-provided` can serve standalone traffic.

### 2.2. Deploying the WAR to an External Tomcat

With an external container:

1. You supply `war-demo.war` to Tomcat/the container's deployment mechanism.
2. The container manages the lifecycle, thread pools, HTTP connectors, and classloaders according to Servlet rules.
3. The application's `SpringBootServletInitializer` participates in bootstrapping the Spring `ApplicationContext` from the Servlet container.
4. HTTP port, virtual hosts, HTTPS connectors, and context path are primarily **container configuration**, not embedded Tomcat configuration.
5. Application classes and web-application libraries are read by the container from `WEB-INF/classes` and `WEB-INF/lib`.

Standard containers **do not treat `WEB-INF/lib-provided` as part of the webapp library classpath**. Consequently, the embedded Tomcat JARs sitting there do not directly collide with the Tomcat engine the container runs.

**Do not confuse runtimes:** invoking `java -jar xxx.war --server.port=18085` is completely different from copying the WAR into an external Tomcat's `webapps/`. In the second case, Spring Boot's `server.port` does not configure the external Tomcat connector; you must check the container's configuration and server logs.

### 2.3. Why Does `SpringBootServletInitializer` Matter?

A `main()` method only handles the entry point of a **standalone Java process**. An external Servlet container **does not invoke `main()`** when deploying a WAR. Spring Boot provides `SpringBootServletInitializer` to connect Spring's lifecycle to how a Servlet container initializes a webapp.

A full Java 17 sample will look like:

~~~java
@SpringBootApplication
public class WarDemoApplication extends SpringBootServletInitializer {
    @Override
    protected SpringApplicationBuilder configure(SpringApplicationBuilder builder) {
        return builder.sources(WarDemoApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(WarDemoApplication.class, args);
    }
}
~~~

The snippet above is an **illustrative skeleton without imports**; the complete Java file is in section 6. If you only add `<packaging>war</packaging>` or the `war` plugin without the proper bootstrap, the WAR may package cleanly yet fail to start inside an external Servlet container.

### 2.4. Spring Boot 3.3 Compatibility Requirements

Spring Boot 3.3.13 requires **Java 17+**, supports embedded Tomcat **10.1**, Jetty **12.0**, and Undertow **2.3**, and can deploy to Servlet containers compatible with **Servlet 5.0+** per the release documentation. In practice, using **Jakarta Servlet-compatible Tomcat 10.1.x** makes comparisons straightforward. Tomcat **9.x / `javax.servlet.*`** belongs to pre-Jakarta Java EE and is not a "drop in a Boot 3.3 WAR and run" target.

**Warning:** Servlet API compatibility is only one requirement. You must also check the Servlet container vendor, Java runtime, logging/classloading policies, server-wide shared libraries, security, and operational support. Pick a container release approved by your organization rather than inferring solely from the word "Tomcat."

## 3. Looking Inside the WAR: How Do `WEB-INF/lib` and `WEB-INF/lib-provided` Differ?

Here is a **conceptual diagram** of a properly built Spring Boot 3.3 executable WAR. Actual versions and library names vary with dependency resolution:

~~~text
war-demo-0.0.1-SNAPSHOT.war
|
+-- META-INF/
|   +-- MANIFEST.MF
|
+-- org/springframework/boot/loader/
|   +-- launch/
|   |   +-- WarLauncher.class
|   |   +-- ...
|   +-- ...
|
+-- WEB-INF/
    +-- classes/
    |   +-- com/example/war/WarDemoApplication.class
    |   +-- com/example/war/PingController.class
    |   +-- application.properties
    |
    +-- lib/
    |   +-- spring-boot-3.3.13.jar
    |   +-- spring-webmvc-<resolved-version>.jar
    |   +-- ...            # application runtime libraries
    |
    +-- lib-provided/
        +-- tomcat-embed-core-<resolved-version>.jar
        +-- tomcat-embed-el-<resolved-version>.jar
        +-- ...            # provided container runtime libraries
~~~

Some archives also contain `WEB-INF/layers.idx` or an index depending on plugin/layout version; **do not** treat having an index as the sole condition for a runnable WAR. The core elements are the manifest, launcher, classes, `lib`, and `lib-provided`.

| Location | Who uses it? | Role |
| --- | --- | --- |
| `META-INF/MANIFEST.MF` | JVM on `java -jar`. | `Main-Class` points to Boot `WarLauncher`; `Start-Class` points to the main app class. |
| `org/springframework/boot/loader/` | JVM launching executable WAR. | Bootstraps the loader and builds the nested classpath. |
| `WEB-INF/classes` | Standalone launcher **and** external servlet container. | App's production classes and resources. |
| `WEB-INF/lib` | Standalone launcher **and** external servlet container. | Standard webapp runtime dependencies. |
| `WEB-INF/lib-provided` | Boot's standalone launcher; not an external container's standard library path. | Servlet engine/runtime supplied externally on deployment. |

**Key idea:** Tomcat files are still **packaged inside the WAR** for standalone execution, simply placed where **the external container does not load them as regular webapp JARs**.

### 3.1. Note on Loader Version

With Spring Boot 3.3.13, an executable WAR typically has:

~~~text
Main-Class: org.springframework.boot.loader.launch.WarLauncher
Start-Class: com.example.war.WarDemoApplication
~~~

Some older Boot tutorials reference a different loader package name. **Do not edit the manifest based on old tutorials**; read `META-INF/MANIFEST.MF` from the actual WAR you build. Main class and packaging settings should be handled by the Spring Boot plugin rather than manually tweaking bootloader fields as a "quick fix."

### 3.2. A WAR Is Not a JAR, and a Plain WAR Differs from an Executable WAR

- **Plain WAR:** has `WEB-INF/classes`/`WEB-INF/lib` for container deployment, but may **lack** the Boot loader/`Main-Class` to run via `java -jar`.
- **Boot executable WAR:** includes the loader and `WEB-INF/lib-provided` layout to support both standalone and traditional deployment.
- **Boot executable JAR:** typically uses `BOOT-INF/classes`/`BOOT-INF/lib` and `JarLauncher`, and does not apply `WEB-INF/lib-provided` rules for WAR deployment.
- **Gradle WAR task `war`** and **Boot task `bootWar`** can emit **two different artifacts**. Always pick the output matching your goal.

## 4. Maven `provided`: Avoiding Container Conflicts While Preserving Standalone Execution

### 4.1. Typical Declaration

In a Spring Boot Maven app using the Web starter and WAR packaging, for example:

~~~xml
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
</dependencies>
~~~

`spring-boot-starter-web` provides Spring MVC and transitively pulls in the Tomcat starter by default. Declaring `spring-boot-starter-tomcat` **directly** with `provided` tells Maven the intended scope for the server starter rather than leaving it as a transitive `compile` dependency. Run `dependency:tree` to verify the effective scope instead of guessing from a single XML snippet.

With Boot starter parent, the starter version is managed by the BOM so no `<version>` is needed on the Tomcat starter. **Do not** pin an incompatible Tomcat version outside the BOM just to "make one module provided."

### 4.2. Which Classpaths Actually Include Maven `provided`?

In Maven convention:

- **Compile:** `provided` is present so code can compile against API/container dependencies promised at runtime.
- **Test:** `provided` is present when running unit/integration tests with Maven, supporting Spring Web context tests.
- **Standard Maven runtime classpath:** `provided` is excluded from runtime transitive resolution unlike `compile`/`runtime`.
- **WAR distribution by Spring Boot Plugin `repackage`:** a special case. The plugin **still processes provided dependencies**, placing them under **`WEB-INF/lib-provided`** in the WAR layout rather than the webapp's `WEB-INF/lib`.

This is a common point of confusion when applying generic Maven intuition to predict executable WAR contents. `provided` **does not mean** "Tomcat vanishes completely from the WAR." Spring Boot intentionally preserves it along a separate path so `java -jar` continues to work.

### 4.3. Maven `provided` vs. `test` and `optional`

| Declaration | Meaning for the build | Result in a Boot WAR |
| --- | --- | --- |
| `compile` (default) | Needed for compile + runtime. | Usually goes into `WEB-INF/lib`. |
| `runtime` | Needed at runtime, not directly for compile. | Usually goes into `WEB-INF/lib`. |
| `provided` | Available at compile/test; supplied by container/JDK on deploy. | With `repackage`, usually goes into `WEB-INF/lib-provided`. |
| `test` | For tests only. | Not included in standard executable WARs. |
| `optional=true` | Prevents pulling the dependency transitively into consuming projects. | **Does not automatically** exclude it from an executable archive; check rules for your version/plugin. |
| `system` | Relies on a local file path; hard to reproduce. | Excluded by default when `includeSystemScope=false`; avoid in real projects. |

**Exact scope:** the results above describe **Spring Boot `repackage` with the WAR layout**, not every Maven plugin's handling of `provided`. If you build a **plain WAR** or use a custom plugin, inspect the actual archive.

### 4.4. Why Not Exclude the Tomcat Starter Entirely?

If the goal is **strictly external Tomcat deployment and never running standalone**, some teams consider excluding the embedded engine altogether. However, if the requirement is **one WAR that both deploys externally and runs via `java -jar`**, removing Tomcat artifacts from the dependency graph defeats that goal: the executable WAR will lack the libraries to start a web server. Putting `provided` in the right place is the clean solution.

Do not use Boot plugin `<excludes>`/`<excludeGroupIds>` to strip all `org.apache.tomcat.embed` artifacts unless you have confirmed standalone mode is not needed; that behaves differently from `provided` and can cause packaged smoke tests to fail.

## 5. Gradle `providedRuntime`: Why Not Use `compileOnly`?

### 5.1. Configuration for the War Plugin

When a project applies the Gradle `war` plugin, the `providedRuntime` configuration marks dependencies **present at runtime in the external server container**. With the Spring Boot Gradle Plugin, they are placed into **`WEB-INF/lib-provided`** of the executable WAR:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
}
~~~

Even though `spring-boot-starter-web` pulls in Tomcat transitively, declaring `providedRuntime` for the Tomcat starter is the documented Spring Boot pattern for recognizing container-provided runtimes. When verifying, inspect the **`bootWar` archive** and configuration reports rather than looking only at `implementation` and assuming all transitive dependencies land in `WEB-INF/lib`.

### 5.2. Why Does `compileOnly` Sound Like Maven `provided` Yet Fail Here?

Gradle's `compileOnly` places a library on the **main compile classpath** but generally leaves it off the **main runtime classpath** and **does not propagate it to the test classpath** the way `providedRuntime` does. That creates real issues for tests that start a Spring Web context or need an embedded servlet engine.

| Criterion | Gradle `compileOnly` | Gradle `providedRuntime` |
| --- | --- | --- |
| Primary intent | Needed at compile time only, not in main runtime. | Supplied by an external web container, yet handled in WAR packaging/tests. |
| On main compile? | Yes. | Follows WAR plugin configuration relations and actual declarations; do not swap for `compileOnly`. |
| On test runtime? | **Not by default.** | Participates in test runtime per WAR plugin purpose. |
| Placed by `bootWar` into `WEB-INF/lib-provided`? | **Not the standard mechanism.** | **Yes**, per Spring Boot Gradle Plugin. |
| Recommended for marking a WAR's embedded servlet container? | Not recommended. | **Recommended.** |

If you write `compileOnly 'org.springframework.boot:spring-boot-starter-tomcat'`, Gradle may compile classes using Tomcat APIs, yet web tests lose the engine and `bootWar` will not receive the dependency under the desired `lib-provided` rules. **Use `providedRuntime` for the embedded container**, rather than "patching" around it by putting Tomcat into `testImplementation` or `implementation` (which breaks WAR semantics).

### 5.3. `providedRuntime` Is Not `developmentOnly`

The Spring Boot Gradle Plugin also offers `developmentOnly` to keep development tools (like DevTools) out of the executable archive by default. **Do not confuse them:**

- `providedRuntime`: library **stays inside the WAR**, in `WEB-INF/lib-provided`, so the standalone launcher can use it while external containers skip it.
- `developmentOnly`: dev-only library, **excluded from the executable archive** by default.
- `runtimeOnly`: regular runtime dependency, usually goes into `WEB-INF/lib`.
- `testImplementation`: test-only, not treated as an application runtime dependency.

When a dependency is only for tests, use a test configuration; when it is genuinely provided by an external container yet needed for standalone execution, use `providedRuntime`.

### 5.4. BOMs and Version Catalogs Do Not Replace `providedRuntime`

The Spring Boot BOM or a Gradle version catalog can manage the version of the Tomcat starter, yet **cannot choose the runtime configuration on its own**. In the build script:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-web'
providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
~~~

`providedRuntime` expresses the packaging intent. Even when the starter's version comes from the BOM, you must still declare the right configuration. An alias like `libs.spring.boot.starter.tomcat` in a version catalog does not automatically assign it to `providedRuntime`.

## 6. Java 17 Example: One Source Working for Both Standalone WAR and External Tomcat

A minimal program layout keeping the exact same Java code whether you choose Maven or Gradle:

~~~text
war-demo/
  pom.xml                                  # CHOOSE Maven
  # or:
  settings.gradle
  build.gradle                             # CHOOSE Gradle
  src/main/java/com/example/war/WarDemoApplication.java
  src/main/java/com/example/war/PingController.java
  src/main/resources/application.properties
  src/test/java/com/example/war/WarDemoApplicationTest.java
  (Maven Wrapper OR Gradle Wrapper generated by repository)
~~~

### 6.1. Entry Points for Both Run Modes

`src/main/java/com/example/war/WarDemoApplication.java`:

~~~java
package com.example.war;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class WarDemoApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(SpringApplicationBuilder builder) {
        return builder.sources(WarDemoApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(WarDemoApplication.class, args);
    }
}
~~~

**Two entry points in the same class:**

- `main(String[] args)`: runs when Boot's `WarLauncher` starts the application via `java -jar`.
- `configure(SpringApplicationBuilder)`: specifies the application sources when an external Servlet container initializes the web app through `SpringBootServletInitializer`.

No `web.xml` is needed for a typical Boot Servlet 3.0+ style example; legacy projects with custom Servlet/Filter/XML configs must migrate or preserve needed components. For specialized Servlet containers, consult the vendor's compatibility guide.

### 6.2. HTTP-Testable Controller

`src/main/java/com/example/war/PingController.java`:

~~~java
package com.example.war;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
~~~

Spring Boot component scanning starting from package `com.example.war` discovers `PingController`. The endpoint returns the exact body `pong` with no database dependency, making it ideal for isolating bootstrap, classpath, and server issues.

### 6.3. Application Properties

`src/main/resources/application.properties`:

~~~properties
spring.application.name=war-demo
# Standalone HTTP port can be overridden via command-line argument
server.port=8080
~~~

When running standalone, `server.port` is used by the embedded server. **When deployed to an external Tomcat, the Tomcat server configures its own connector port**; this value in `application.properties` does not force an external Tomcat to listen on 8080. Avoid storing hostnames, passwords, or private keys inside the WAR; environments should inject sensitive config from a secret store or authorized server mechanism.

### 6.4. JUnit Test with MockMvc

`src/test/java/com/example/war/WarDemoApplicationTest.java`:

~~~java
package com.example.war;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class WarDemoApplicationTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void pingRespondsWithPong() throws Exception {
        mvc.perform(get("/ping"))
           .andExpect(status().isOk())
           .andExpect(content().string("pong"));
    }
}
~~~

This test loads the Spring context and checks mappings/responses using MockMvc; it **does not deploy the WAR to an external server** and does not open a real HTTP listener. It requires test dependencies and a Spring Web application context. Thus `providedRuntime`/`provided` supports the test classpath, yet a passing test **does not replace** verifying `WEB-INF/lib-provided` and both run modes.

## 7. Complete Maven `pom.xml` with `provided`

This POM works with the Java sources from section 6, assuming Maven Wrapper and JDK 17 are available:

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

    <groupId>com.example</groupId>
    <artifactId>war-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <packaging>war</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <!-- Server container available at compile/test, supplied externally on deploy -->
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
            <!-- Spring Boot Parent configures repackage version/execution -->
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Layer-by-layer breakdown:**

1. `<packaging>war</packaging>` switches the lifecycle/package type from JAR to WAR.
2. `spring-boot-starter-web` keeps Spring MVC and web app dependencies.
3. `spring-boot-starter-tomcat` in `provided` changes the runtime intent for the embedded container rather than "deleting Tomcat everywhere."
4. `spring-boot-starter-parent` manages dependency and build plugin versions; declaring `spring-boot-maven-plugin` binds `repackage` to the `package` phase.
5. The test starter in `scope=test` stays out of the regular runtime WAR.
6. `SpringBootServletInitializer` in the Java source provides the external Servlet container bridge outside the POM.

### 7.1. Why No Explicit `maven-war-plugin` Configuration Is Needed Here?

Spring Boot starter parent already configures sensible Maven WAR/plugin defaults in this version. In a corporate parent or a POM importing only the BOM, you may need to explicitly manage plugin versions, `maven-war-plugin`, and the `spring-boot:repackage` execution. **Importing the `spring-boot-dependencies` BOM alone does not bring in all build defaults.**

Do not add another `repackage` execution with a different ID when the parent already defines one, as that can cause duplicate goal runs. When customizing config, inspect `help:effective-pom` so you edit the right place in the inheritance chain.

### 7.2. Maven Commands and Expected Output

~~~bash
./mvnw -version
./mvnw clean verify

# Show resolved dependencies and scopes:
./mvnw dependency:tree

# Filename per example GAV:
jar tf target/war-demo-0.0.1-SNAPSHOT.war
~~~

Expected archive entries include:

~~~text
META-INF/MANIFEST.MF
org/springframework/boot/loader/launch/WarLauncher.class
WEB-INF/classes/com/example/war/WarDemoApplication.class
WEB-INF/classes/com/example/war/PingController.class
WEB-INF/classes/application.properties
WEB-INF/lib/<Spring-runtime-libs>.jar
WEB-INF/lib-provided/tomcat-embed-core-<resolved-version>.jar
WEB-INF/lib-provided/<other-container-libs>.jar
~~~

`war-demo-0.0.1-SNAPSHOT.war` is the sample name; check the actual name in `target/`. Library names containing `<resolved-version>` are placeholders for reading; **never** copy angle-bracket placeholders literally into the CLI.

### 7.3. Do Not Treat `dependency:tree` Output as the Packaged File List

`dependency:tree` describes the dependency graph and scopes at the Maven level. The Spring Boot Plugin additionally **relocates** provided dependencies into `WEB-INF/lib-provided` during `repackage`. Thus `dependency:tree` and `jar tf` provide complementary evidence; never conclude Tomcat "disappeared" merely because it is not under `WEB-INF/lib`.

## 8. Complete Gradle `build.gradle` with `providedRuntime`

File `settings.gradle`:

~~~groovy
rootProject.name = 'war-demo'
~~~

File `build.gradle` (Groovy DSL, matching the illustrative versions):

~~~groovy
plugins {
    id 'java'
    id 'war'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
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

    // WAR will place embedded Tomcat under WEB-INF/lib-provided:
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**Breakdown:**

- The `war` plugin creates the Gradle WAR lifecycle and configurations, including `providedRuntime`.
- The Spring Boot plugin adds the `bootWar` task when the WAR plugin is applied, rather than creating only `bootJar` as in a `java`-only application.
- The dependency management plugin manages versions per the matching Spring Boot BOM; it does not choose the provided scope by itself. `providedRuntime` is the build script's explicit choice.
- `testImplementation` and `testRuntimeOnly` supply test tooling; do not treat them as production runtime dependencies.
- `java.toolchain` requests Java 17 for compilation; if no matching JVM toolchain is installed, Gradle needs toolchain provisioning or an appropriate JDK installed.
- Plugin versions here are pinned for the example; real projects must verify Gradle Wrapper/JDK/plugin version compatibility.

### 8.1. Gradle `bootWar` vs. `war`

~~~bash
./gradlew --version
./gradlew tasks --all
./gradlew clean build

# Invoke the executable WAR task directly:
./gradlew bootWar
~~~

`bootWar` creates the **Spring Boot executable WAR** and is wired into `assemble`/`build`. Gradle's `war` task creates a **plain WAR**. Under Boot 3.3 plugin conventions, when both plain and executable WARs are built, the plain WAR normally gets the `plain` classifier, for instance:

~~~text
build/libs/war-demo-0.0.1-SNAPSHOT.war
build/libs/war-demo-0.0.1-SNAPSHOT-plain.war
~~~

**Never deploy or run by picking a random first `*.war` file.** Which file is right must be determined from task output, archive name, manifest, and `jar tf`. A plain WAR can deploy to an external container under servlet rules, but does not necessarily support standalone `java -jar`.

### 8.2. When `compileOnly` Breaks Tests

The snippet below is an **anti-example** for an app that must be both deployable and executable:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    // DO NOT use as a replacement for providedRuntime in the WAR case:
    compileOnly 'org.springframework.boot:spring-boot-starter-tomcat'
}
~~~

Instead:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
}
~~~

`compileOnly` neither supplies Tomcat to the test runtime nor signals `bootWar` to place Tomcat into `lib-provided`. If integration tests require a Spring Web context, they may fail with missing server classes. Do not "fix" this by disabling tests; use the proper configuration and inspect `testRuntimeClasspath`.

### 8.3. Equivalent Kotlin DSL

For `build.gradle.kts` (dependency declaration fragment; requires the `war`/Boot plugins applied and dependency management active):

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    providedRuntime("org.springframework.boot:spring-boot-starter-tomcat")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}
~~~

This is a Kotlin DSL snippet, **not a standalone file**. Do not copy Groovy single quotes/syntax into Kotlin expecting Gradle to translate it automatically.

## 9. Why Can You Have `spring-boot-starter-web` Together with `provided` Tomcat?

Many people ask:

> "The Web starter already pulls in Tomcat. If I add the Tomcat starter a second time, will two copies of Tomcat be downloaded?"

In Maven/Gradle dependency resolution, one coordinate appearing along multiple paths **does not create two runtime copies**. The build tool resolves the graph and applies version/scope/configuration rules; declaring it again under `provided`/`providedRuntime` **adjusts where it belongs during build/deploy**, rather than adding a second server.

Still, do not merely guess. In projects with exclusions, dependency overrides, or multiple web starters, check:

- Maven `./mvnw dependency:tree`: which starter brings in Tomcat, and what is its effective scope?
- Gradle `./gradlew dependencies --configuration runtimeClasspath` and `testRuntimeClasspath`: which classpaths include Tomcat?
- `jar tf executable.war`: are embedded Tomcat JARs in **`WEB-INF/lib-provided`** as expected, and **not** leaking into `WEB-INF/lib`?
- Boot runtime: does `java -jar` start and serve HTTP?
- External deployment: does the webapp start cleanly in server container logs without duplicate Servlet/Tomcat class errors?

If you spot **embedded Tomcat in both `WEB-INF/lib` and `lib-provided`** under a custom build path, investigate immediately: another dependency or configuration may be pulling it into the webapp runtime. Do not manually delete a nested JAR from the WAR and release it; fix the graph/build logic and rebuild cleanly.

### 9.1. Gradle and Maven Resolve Scopes Differently

Do not treat `Maven provided == Gradle compileOnly` merely because both sound like "needed at compile time." A **Spring Boot executable WAR** requires **all at once**:

1. A servlet engine for the standalone app.
2. No embedded engine mixed into standard webapp libs on external deployment.
3. A suitable classpath for unit/integration tests to run.
4. A reproducible artifact packaged with the right layout by the Boot plugin.

Maven uses `provided` + Spring Boot `repackage`; Gradle uses `providedRuntime` + `bootWar`. They are **equivalent in packaging goal**, not identical across every dependency scope semantic of the two build systems.

## 10. Inspecting the WAR with `jar tf` and the Manifest

The most important QA step is **inspecting the actual artifact** before deployment. `jar` (from the JDK) can list a WAR because a WAR is a ZIP/JAR-compatible archive.

### 10.1. Checking the Entry List

Maven:

~~~bash
jar tf target/war-demo-0.0.1-SNAPSHOT.war
~~~

Gradle:

~~~bash
jar tf build/libs/war-demo-0.0.1-SNAPSHOT.war
~~~

On macOS/Linux, with `grep`:

~~~bash
WAR=target/war-demo-0.0.1-SNAPSHOT.war

jar tf "$WAR" | grep '^WEB-INF/classes/'
jar tf "$WAR" | grep '^WEB-INF/lib/'
jar tf "$WAR" | grep '^WEB-INF/lib-provided/'
jar tf "$WAR" | grep '^org/springframework/boot/loader/'
~~~

When filtering, **`^WEB-INF/lib/` does not match `^WEB-INF/lib-provided/`**, letting you distinguish the two branches cleanly. Names like `tomcat-embed-core-*.jar`, `tomcat-embed-el-*.jar`, and `tomcat-embed-websocket-*.jar` are typical markers, though exact library counts and modules depend on the resolved graph.

### 10.2. Executable WAR Manifest

If `unzip` is available:

~~~bash
unzip -p "$WAR" META-INF/MANIFEST.MF
~~~

Expect keys such as:

~~~text
Main-Class: org.springframework.boot.loader.launch.WarLauncher
Start-Class: com.example.war.WarDemoApplication
~~~

Do not force the entire manifest to have only two lines; build metadata and manifest line wrapping also appear. If no suitable `Main-Class` is present, `java -jar` may report `no main manifest attribute`. With a plain WAR, that is not necessarily an external deployment bug; it simply lacks a standalone launcher unlike a Boot executable WAR.

### 10.3. Automated Check (Bash)

Below is a script that checks for the **presence** of app classes and Tomcat in the right branch while flagging mispackaged layouts. Requires JDK `jar` and Bash/`grep`; **adjust the path for Gradle** when using it.

~~~bash
#!/usr/bin/env bash
set -euo pipefail

WAR="target/war-demo-0.0.1-SNAPSHOT.war"
LIST="$(jar tf "$WAR")"

# App classes must exist
grep -q '^WEB-INF/classes/com/example/war/WarDemoApplication.class$' <<< "$LIST"
grep -q '^WEB-INF/classes/com/example/war/PingController.class$' <<< "$LIST"

# Embedded Tomcat must be placed in the provided branch of the executable WAR
grep -Eq '^WEB-INF/lib-provided/tomcat-embed-core-[^/]+\.jar$' <<< "$LIST"

# Prevent app's Tomcat engine from leaking into regular webapp lib
if grep -Eq '^WEB-INF/lib/tomcat-embed-(core|el|websocket)-[^/]+\.jar$' <<< "$LIST"; then
    echo "FAIL: embedded Tomcat found in WEB-INF/lib" >&2
    exit 1
fi

# Test classes are not runtime application classes
if grep -Eq 'WarDemoApplicationTest.class' <<< "$LIST"; then
    echo "FAIL: test class packaged into WAR" >&2
    exit 1
fi

echo "PASS: WAR classes and container layout verified"
~~~

**Expected stdout when all checks pass (exit code 0):**

~~~text
PASS: WAR classes and container layout verified
~~~

If a class is missing, Tomcat is missing from `lib-provided`, or Tomcat leaks into `lib`, the script exits non-zero (`grep` assertions do not necessarily print a message). This script is only a **structural assertion set**; it does not prove the JVM or external container will actually run, nor that all dependencies are compatible.

**Why use a here-string `<<< "$LIST"`?** It avoids `jar tf | grep -q` pipelines under `set -o pipefail` being tripped by `SIGPIPE` on large archives. The here-string searches the captured output; for huge WARs, CI can use a dedicated ZIP API tool instead of holding the full listing in shell memory.

### 10.4. Windows PowerShell

You can inspect entries without Bash:

~~~powershell
$war = "target/war-demo-0.0.1-SNAPSHOT.war"
jar tf $war | Select-String '^WEB-INF/classes/'
jar tf $war | Select-String '^WEB-INF/lib/'
jar tf $war | Select-String '^WEB-INF/lib-provided/'
~~~

Change `$war` to `build/libs/...war` if using Gradle. In PowerShell CI, write explicit assertions with `Select-String -Quiet` and non-zero exit codes rather than relying on visual inspection as QA.

## 11. Running `java -jar`: Verifying Embedded Tomcat Is Still Sufficient

Once you have the executable WAR, test the **exact binary just packaged**:

~~~bash
# Maven WAR:
java -jar target/war-demo-0.0.1-SNAPSHOT.war --server.port=18085

# Or Gradle WAR, in another session:
# java -jar build/libs/war-demo-0.0.1-SNAPSHOT.war --server.port=18085
~~~

When the app logs show ready, in another terminal:

~~~bash
curl -i http://localhost:18085/ping
~~~

**Expected:** HTTP status **200** and exact body **`pong`**. Startup logs, HTTP headers, and port-bind timing vary by environment; do not report them as observed stdout unless actually executed.

If `WEB-INF/lib-provided` lacks the complete Tomcat engine, standalone launch can fail due to missing `ServletWebServerFactory` or Tomcat/Servlet classes. That **does not imply** external-container deployment will also fail: the two runtime paths are distinct. However, if the requirement is a dual-mode WAR, that is a QA failure to fix.

### 11.1. Using the Wrong Artifact Gives the Wrong Result

If Gradle produces both:

~~~text
war-demo-0.0.1-SNAPSHOT.war
war-demo-0.0.1-SNAPSHOT-plain.war
~~~

only the **executable** file produced by Spring Boot `bootWar` is expected to run with `java -jar`. Do not use `*.war` wildcards or "grab the newest file" without checking classifiers. With Maven, `repackage` may keep the original WAR as `*.war.original`; that original file is not the binary to test the standalone launcher.

### 11.2. Distinguishing Ports and URLs Across Environments

| Run Type | Who opens the HTTP port? | Example endpoint access |
| --- | --- | --- |
| `java -jar ...war --server.port=18085` | Embedded Tomcat in the app JVM. | `http://localhost:18085/ping`. |
| WAR deployed on external Tomcat on port 8080, context `/war-demo` | External Tomcat server (connector 8080). | `http://localhost:8080/war-demo/ping`. |
| WAR deployed on external Tomcat at root context `/` | External Tomcat server. | `http://localhost:8080/ping`. |

External server port and context path are **illustrative only**. Tomcat may use an HTTPS connector, host, reverse proxy, or virtual context path; obtain real values from container configuration/logs and deployment descriptors. Spring's `server.port` does not dictate the external Tomcat socket.

## 12. Deploying the WAR to External Tomcat Without Mixing Engines

Before deploying, confirm the external Servlet container/JDK is approved and has a clear deployment path. With Spring Boot 3.3, Java 17+ and Jakarta Servlet form the baseline; Tomcat 10.1 is the illustrative match closest to this line's embedded container.

A controlled local procedure:

1. Prepare a **standalone external Tomcat** already running with deploy permissions. Never use a production machine for a first test.
2. Build the executable WAR from the right source version and inspect with `jar tf` to confirm Tomcat JARs live in `WEB-INF/lib-provided`.
3. Use Tomcat Manager or the `webapps` folder per environment policy; the WAR file may be named `war-demo.war`, typically yielding context path `/war-demo` (unless Tomcat configures another path).
4. Watch the **external Tomcat logs** to verify whether the webapp deployed or failed, rather than reading only Maven/Gradle logs.
5. Call the URL containing the **external Tomcat's port and context path**, e.g. `http://localhost:8080/war-demo/ping`.
6. After testing, undeploy through the container management mechanism rather than killing the entire JVM on the host.

Example copy command (only when you actively manage a **local test Tomcat** with `CATALINA_BASE` pointing to the exact instance):

~~~bash
# Illustrative only; Tomcat Manager/CI deploy is generally preferred.
# Ensure $CATALINA_BASE is configured accurately; never guess paths.
cp target/war-demo-0.0.1-SNAPSHOT.war "$CATALINA_BASE/webapps/war-demo.war"
~~~

If external Tomcat is already running, it may auto-deploy depending on `autoDeploy` configuration. There is no guarantee every instance auto-deploys; read container/ops docs. Do not consider an app deployed just because `cp` exited 0.

### 12.1. Why Does the Servlet Container Not Call Spring Boot `main()`?

The external server controls the webapp lifecycle. `SpringBootServletInitializer.configure(...)` configures the Spring Boot `ApplicationContext` sources for the container to bootstrap. Therefore, when debugging "WAR deployed with no endpoints," check the initializer, component scanning, servlet registration, and container logs. Tweaking only `main()`/`server.port` will not necessarily affect the external path.

### 12.2. Why Not Drop `providedRuntime` Because "External Tomcat Already Has It"?

If you remove the provided dependency from the build while still wanting standalone execution:

- `java -jar` can lose embedded Tomcat and fail to open an HTTP port.
- The test classpath can miss server classes.
- The WAR structure may still contain other webapp libs, yet fail the executable + deployable criteria.

If an organization **only** needs external deployment and will never run standalone, a container-managed-only dependency architecture can be considered; even then, document the revised artifact contract and test strategy. This lesson maintains the **dual-mode WAR** target.

## 13. Real-World Errors: Finding the Fault at the Right Layer

| Symptom | Common Cause | Verification and Resolution |
| --- | --- | --- |
| `java -jar app.war` reports `no main manifest attribute`. | Using a plain WAR or Boot `repackage`/`bootWar` never ran. | Check manifest, Boot loader, build task, and exact artifact. |
| WAR has `WEB-INF/lib` but no `WEB-INF/lib-provided`. | Missing `provided`/`providedRuntime` or Boot packaging didn't use the right layout. | Check POM/config, resolved graph, executable WAR task, and archive contents. |
| Embedded Tomcat still lands in `WEB-INF/lib`. | Dependency declaration/config didn't adjust scope properly; custom packaging. | Read dependency graph, confirm direct Tomcat starter is provided, and clean rebuild. |
| Standalone WAR fails with missing `TomcatServletWebServerFactory`/Tomcat classes. | Container runtime was excluded from archive or absent from launcher classpath. | Check `WEB-INF/lib-provided` and `WarLauncher`/manifest. |
| External Tomcat deploy fails with `ClassNotFoundException: jakarta.servlet...`. | Container lacks Jakarta/Servlet version support or classloading policy conflicts. | Check container version, Jakarta namespace, Java runtime; use a compatible container. |
| Deploying Boot 3.3 WAR on Tomcat 9 fails. | Tomcat 9 uses legacy Javax Servlet; Boot 3.3 uses Jakarta. | Pick a container supporting the right Servlet/Jakarta version, e.g., Tomcat 10.1 per policy. |
| `@SpringBootApplication` has `main` yet WAR deploy does not start webapp. | Missing `SpringBootServletInitializer`/external bootstrap; wrong context path. | Check initializer, logs, context-path URL, and WAR class locations. |
| `java -jar` returns 200 on 18085, external WAR missing at `localhost:18085/ping`. | External Tomcat port/context differs; `server.port` does not control external connector. | Check Tomcat `server.xml`/logs, real context path, and connector port. |
| Gradle tests fail with missing servlet classes when using `compileOnly`. | `compileOnly` is not added to test runtime as needed. | Switch to `providedRuntime` and check `testRuntimeClasspath`/`bootWar`. |
| Maven `provided` is still present inside the WAR. | This is the **intended** behavior in `WEB-INF/lib-provided`. | Distinguish `lib-provided` from `lib`; do not try to remove everything. |
| Unit tests pass yet external deploy fails. | MockMvc does not test external container lifecycle, servlet compatibility, or context path. | Add a deployment smoke test in external Tomcat and inspect server logs. |
| Build outputs multiple `*.war` files, CI deploys wrong one. | `plain` classifier or `.original` artifact. | Specify exact artifact name/pattern; verify manifest and `WarLauncher`. |
| App fails with `ClassCastException`/duplicate servlet container classes. | Same engine/API library in both container and `WEB-INF/lib`, or version mismatch. | Compare archive, container shared libs, scope, and classloader policy. |
| Code uses `javax.servlet.*` in a Boot 3.3 project. | Not migrated to Jakarta namespace. | Switch to compatible `jakarta.servlet.*` APIs or revise upgrade plan. |
| App behaves differently between `java -jar` and external deploy. | Classpath order, profiles, context path, or server-specific config differs. | Compare startup logs/active profiles, resource/property sources, servlet mappings, and runtime graph. |
| `bootWar` task not found. | Missing `war` plugin or invoked on the wrong module. | `./gradlew tasks --all` and check `plugins`/module path. |
| `mvn package` builds only a plain WAR. | Boot Maven plugin not declared, or missing `repackage` execution when not using starter parent. | Check `help:effective-pom` and packaging output; add proper execution/plugin config. |
| App starts yet `/ping` returns 404 on external deploy. | Unexpected context path, controller not scanned, or webapp deploy failed. | Check context root, Servlet mappings, container logs, and app class package. |

### 13.1. Cause-Ordered Diagnostic Sequence

1. **Project type:** Servlet Spring MVC or WebFlux? This article applies to Servlet WARs.
2. **Build type:** Are Maven `packaging=war` / Gradle `war` + Boot plugin configured?
3. **Dependency graph:** Is the Tomcat starter scope/configuration right?
4. **Archive:** Is Tomcat in `WEB-INF/lib-provided` or accidentally in `WEB-INF/lib`?
5. **Launcher:** Does the executable WAR have the right `WarLauncher`/`Start-Class`?
6. **External bootstrap:** Are `SpringBootServletInitializer` and container/Jakarta/JDK compatibility right?
7. **Server configuration:** Port, context path, HTTPS, profiles, logs.
8. **Behavior:** HTTP smoke checks and test reports actually pass in both modes.

Do not "fix" issues by moving every dependency to `implementation` or deleting `lib-provided`: either shortcut can mask a bug in one run mode while breaking the other.

## 14. Variants and Scope Boundaries

### 14.1. Tomcat, Jetty, Undertow

The examples use Tomcat because `spring-boot-starter-web` in Spring Boot 3.3 defaults to Tomcat. If you want Jetty or Undertow:

- **First**, exclude the Tomcat starter from the Web starter using your build tool's syntax.
- **Next**, declare the alternative engine dependency matching your Boot version, using the scope/configuration matching standalone/external goals.
- **Finally**, check WAR layout, test classpath, container API compatibility, and packaged smoke tests.

Do not merely swap `artifactId` on one line and assume the WAR will deploy to every servlet server. For example, keeping external Tomcat while packaging Jetty for standalone can raise compatibility differences compared to a Tomcat/Tomcat setup.

### 14.2. WebFlux Does Not Share the Traditional WAR Model

Spring WebFlux does not depend tightly on the Servlet API and defaults to Reactor Netty; Spring Boot 3.3 documentation notes that **traditional WAR deployment is not supported for WebFlux applications** in this model. Do not mechanically apply `providedRuntime` Tomcat and `SpringBootServletInitializer` to turn a WebFlux-only app into a Servlet WAR.

### 14.3. Multi-Module Maven/Gradle

If a repository has a `core` library module and a `webapp` application module:

- Apply WAR packaging and the provided servlet container only in the **webapp module**, not across all modules.
- `core` only needs to publish a library JAR per standard Java/Maven conventions.
- Internal project dependencies of `webapp` go into `WEB-INF/lib` as runtime libraries; do not exclude them due to a shared `groupId`.
- Parent/BOM manages versions, yet does not decide provided scope per module automatically.
- Target the right module when building/verifying, e.g. Gradle `:webapp:bootWar`; Maven supports `-pl webapp`, ensuring internal reactor dependencies are built as needed.

### 14.4. Container Images, Native Images, and Executable JARs

If a system runs on OCI images/Kubernetes or native executables, the JAR vs. WAR decision can differ. This lesson covers **WARs run via embedded/external Servlet containers**; do not apply all `WEB-INF/lib-provided` assertions to executable JARs or native images. A Boot executable **JAR** does not produce `WEB-INF/lib-provided` in the same way.

### 14.5. Security and Dependency Hygiene

Placing Tomcat JARs under `lib-provided` does not eliminate Tomcat vulnerabilities. Standalone execution still uses the Tomcat version **packaged inside the WAR**; external deployment uses the **external host's** Tomcat. Therefore you must:

- Manage and patch **both environments separately** (packaged Tomcat vs. external Tomcat).
- Record tested versions of the Spring Boot plugin, BOM, and servlet container.
- Never bake credentials or sensitive logs into the WAR.
- Scan dependencies and artifacts, and store SBOM/provenance if required by your organization.
- Check licenses, Servlet APIs, and classloader conflicts during upgrades.

## 15. Exercises and Verification Criteria

### Exercise A — Maven `provided`

1. Use the Java sources/tests from section 6 and `pom.xml` from section 7.
2. Run `./mvnw -version`, `./mvnw clean verify`, and inspect `target/surefire-reports` to verify `pingRespondsWithPong` actually ran and passed.
3. Run `./mvnw dependency:tree` and confirm the Tomcat starter has the chosen scope.
4. Use `jar tf target/war-demo-0.0.1-SNAPSHOT.war` to verify `WEB-INF/classes`, `WEB-INF/lib`, and `WEB-INF/lib-provided`.
5. Run the script in section 10.3 (with the right path) to verify Tomcat is in `lib-provided` and absent from `lib`.
6. Run `java -jar ...war --server.port=18085`, call `GET /ping`, and record status/body.
7. If a compatible external Tomcat is available, deploy this WAR to a test environment and call the URL matching the real context/connector. Record logs and HTTP output.

### Exercise B — Gradle `providedRuntime`

1. Use the same Java sources/tests with `build.gradle` from section 8.
2. Run `./gradlew --version` and `./gradlew tasks --all` to confirm `bootWar` appears.
3. Run `./gradlew clean build` and inspect the test report under `build/reports/tests/test`.
4. Inspect `runtimeClasspath`/`testRuntimeClasspath`, and run `jar tf build/libs/war-demo-0.0.1-SNAPSHOT.war`.
5. Prove Tomcat sits in `WEB-INF/lib-provided`. Compare with an **experimental, non-release** copy replacing `providedRuntime` with `compileOnly`; explain why test/package classpaths are not equivalent.
6. Run the executable WAR and, if available, deploy to a test external Tomcat as in Exercise A.

### Exercise C — Evaluating Evidence Across Both Runtimes

Complete the table based on **observed results**:

| Verification Item | Standalone Executable WAR | External Tomcat Deployment |
| --- | --- | --- |
| Who opens the HTTP connector/port? | Embedded Tomcat inside the app JVM. | External Tomcat server. |
| Where does runtime classpath get provided libs? | `WEB-INF/lib-provided` via Boot Launcher. | External container classpath; `lib-provided` is not a standard webapp lib dir. |
| Entry point / bootstrap | `WarLauncher` + `main()`. | `SpringBootServletInitializer` + Servlet container. |
| `GET /ping` URL | Per `server.port`/app config. | Per container connector port and context root. |
| What constitutes PASS? | `java -jar` starts, HTTP 200 / `pong`. | Deployment startup log succeeds, HTTP 200 / `pong` at the right context. |

### Self-Check Questions

1. Why must `spring-boot-starter-tomcat` be marked `provided` when Maven builds a WAR for external Tomcat deployment?
2. Why doesn't Spring Boot completely omit Tomcat from the WAR instead of placing it in `WEB-INF/lib-provided`?
3. How do `WEB-INF/lib` and `WEB-INF/lib-provided` differ during `java -jar` vs. external container deployment?
4. Why can't Gradle `compileOnly` replace `providedRuntime` when you need both tests and an executable WAR?
5. When the POM's Web starter already pulls in Tomcat, why declare Tomcat directly with `scope=provided`?
6. How does `WarLauncher` differ from `SpringBootServletInitializer` in when each executes?
7. Why doesn't `server.port` change an external Tomcat's port?
8. When a build emits `*-plain.war` and executable `*.war`, how do you distinguish them?
9. Why can't a passing MockMvc test prove a WAR deploys cleanly onto an external container?
10. If a WAR runs on Tomcat 10.1 yet fails on Tomcat 9, which API/namespace should you check?

### Lesson Completion Checklist

- [ ] Clearly state the role of the embedded server vs. an external servlet container.
- [ ] Distinguish `spring-boot-starter-web`, `spring-boot-starter-tomcat`, and Spring Boot Maven/Gradle plugins.
- [ ] Maven POM has `<packaging>war</packaging>` and Tomcat starter `<scope>provided</scope>`.
- [ ] Gradle applies the `war` plugin and configures the Tomcat starter via `providedRuntime`, without equating it to `compileOnly`.
- [ ] Java app extends `SpringBootServletInitializer` and keeps `main()` to support both entry points.
- [ ] Understand Spring Boot 3.3 requires Java 17+ and a compatible Jakarta/Servlet container.
- [ ] Distinguish `WEB-INF/classes`, `WEB-INF/lib`, and `WEB-INF/lib-provided`.
- [ ] Verify launcher manifest and runtime dependency placement with `jar tf`.
- [ ] Real JUnit/MockMvc tests execute and report pass.
- [ ] `java -jar executable.war` starts and `GET /ping` returns 200/`pong`.
- [ ] External container deployment tested at the right connector/context path without confusing `server.port`.
- [ ] Do not accidentally deploy a plain WAR or Maven `.original`.
- [ ] Know how to diagnose duplicate Tomcat classes, wrong Servlet namespace, and missing provided runtime.
- [ ] Understand that server versions and security must be managed separately for standalone and external deployment.

**Completion criteria:** produce a WAR capable of **running standalone and deploying to a compatible external Servlet container**; verify `WEB-INF/lib-provided` contains embedded Tomcat, `WEB-INF/lib` is free of mixed Tomcat engine JARs, test reports pass, and real HTTP responses are observed in both modes (when an external server is available). When no external server is available, explicitly mark external deployment as **unverified** rather than inferring from a green build that it will surely succeed.

## Official References

- [Spring Boot 3.3.13 — Traditional Deployment](https://docs.spring.io/spring-boot/3.3/how-to/deployment/traditional-deployment.html)
- [Spring Boot 3.3.13 — System Requirements and Servlet Containers](https://docs.spring.io/spring-boot/3.3/system-requirements.html)
- [Spring Boot 3.3 — Maven Plugin: Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html)
- [Spring Boot 3.3 — Gradle Plugin: Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)
- [Spring Boot 3.3.13 API — WarLauncher](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/loader/launch/WarLauncher.html)
- [Spring Boot — Executable Archive Format](https://docs.spring.io/spring-boot/specification/executable-jar/nested-jars.html)
- [Apache Maven — Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Gradle — War Plugin](https://docs.gradle.org/current/userguide/war_plugin.html)
- [Gradle — Dependency Configurations](https://docs.gradle.org/current/userguide/declaring_configurations.html)

**Key takeaway:** Maven `provided` and Gradle `providedRuntime` do not "strip Tomcat from the WAR"; they **place embedded Tomcat into `WEB-INF/lib-provided`** so an executable WAR can still run via `java -jar`, while an external Servlet container avoids conflicts with the server it already provides. That behavior must be verified via WAR structure and **both live execution paths**, not merely by reading build files.