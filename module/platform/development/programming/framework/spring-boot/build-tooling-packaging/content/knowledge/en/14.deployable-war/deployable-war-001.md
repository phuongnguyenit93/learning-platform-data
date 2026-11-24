# When to Choose a WAR vs. a JAR with an Embedded Server in Spring Boot?

## 1. The Decision Problem

Spring Boot lets you package a web application to run **standalone** with an embedded HTTP server, or deploy it as a **WAR into an external servlet container**. The choice is not merely changing the file extension from `.jar` to `.war`. It affects where the servlet server lives, who is responsible for upgrading the server, the startup command, which libraries are packaged, and how the application is operated.

There are **three cases** worth distinguishing:

1. **Executable JAR + embedded server**: the JAR file contains application code, dependencies, and embedded server libraries such as Tomcat. Operations runs `java -jar app.jar`; the application JVM starts the HTTP server itself.
2. **Executable WAR + embedded server**: a WAR file properly packaged by Spring Boot, including `provided`/`providedRuntime` dependencies in `WEB-INF/lib-provided`. It can run as `java -jar app.war` as a standalone process.
3. **Deploy WAR to an external servlet container**: a Tomcat/Jetty/compatible Servlet server is installed and managed **outside** the WAR file. The container receives the WAR and initializes the application; typically you do **not** run `java -jar` for this deployment path.

**Starting principle:** Unless there is a requirement to use an external container, an **executable JAR with an embedded server is usually the simplest choice for a new Spring Boot service**. A WAR is appropriate when deployment compatibility with an existing servlet container infrastructure or certain organizational constraints are required.

This article uses **Spring Boot 3.5.x and Java 17** examples; the Spring Boot 4.x ecosystem has Servlet/container version changes, so consult the documentation for the exact **major/minor version** of your real project. The configuration examples below are illustrated with Spring Boot `3.5.16`.

## 2. Components: Archive, Boot Loader, and Embedded Server

**JAR/WAR are archive types and layouts**, whereas Tomcat/Jetty/Undertow are **servlet servers**. The two pairs of concepts are not identical.

In a Servlet Spring MVC application with the `spring-boot-starter-web` starter:

- Spring Boot includes `spring-boot-starter-tomcat` in the dependency graph by default, unless you have swapped the starter.
- **Embedded Tomcat** is a library started by the application inside the same JVM process, not a separately installed Tomcat service.
- With **external Tomcat**, the container is installed and run independently; the WAR provides the web application and the container provides the servlet runtime.
- Settings such as `server.port`, `server.ssl.*`, or `server.tomcat.*` primarily control the embedded server; when deploying to an external container, the container determines runtime mechanisms, ports, connectors, and partly the context path.

**Spring Boot Loader** supports launching an executable archive containing nested dependency JARs:

```text
Executable JAR                  Executable WAR
+------------------+            +---------------------------+
| META-INF/        |            | META-INF/                 |
| Boot Loader      |            | Boot Loader               |
| BOOT-INF/classes |            | WEB-INF/classes           |
| BOOT-INF/lib     |            | WEB-INF/lib               |
+------------------+            | WEB-INF/lib-provided      |
   java -jar app.jar             +---------------------------+
      |                            java -jar app.war
      v                                  |
  JarLauncher                            v
      |                              WarLauncher
      +----------- Spring application --+
                        |
                        v
               Embedded servlet server

External container:
    Tomcat service -> deploy app.war -> Servlet initializer
                -> application context
                (does not run WarLauncher with java -jar)
```

This is a logical model, not a byte-for-byte ZIP diagram. `WEB-INF/lib-provided` is used by Boot Loader when running an **executable WAR**; it is placed so that it **does not become a regular WEB-INF/lib** when an external container deploys the WAR.

## 3. Comparison Table of Options

| Criterion | JAR + embedded server | WAR run via `java -jar` | WAR into external container |
|---|---|---|---|
| Release artifact | Executable `.jar` | Executable `.war` | Deployable `.war` (may also be executable) |
| Who starts the HTTP server? | Spring Boot inside the application JVM | Spring Boot inside the application JVM | External container, e.g., an already-running Tomcat |
| Typical run command | `java -jar app.jar` | `java -jar app.war` | Deploy/undeploy WAR via container mechanism |
| Class/library layout | `BOOT-INF/classes`, `BOOT-INF/lib` | `WEB-INF/classes`, `WEB-INF/lib`, `WEB-INF/lib-provided` | Container loads `WEB-INF/classes` and `WEB-INF/lib`; servlet runtime is provided by the container |
| Launcher on `java -jar` | `JarLauncher` | `WarLauncher` | Does not invoke Boot launcher in traditional deployment |
| Updating the servlet server | Usually upgrade Boot/Tomcat dependency and rebuild image/artifact | Same when run standalone | Operations team upgrades/patches the external container |
| Port and TLS configuration | Application process or proxy/ingress | Application process or proxy/ingress | External container, proxy/ingress |
| Process isolation | One application JVM that can be deployed/scaled independently | Same as JAR when run standalone | May share JVM/container with other WARs |
| Common CI/CD pattern | Container image containing app + JVM; roll out per instance | Image/process running `java -jar` WAR | Copy/deploy WAR into managed servlet container |
| Simplicity for a new service | Usually high | Useful only when the same WAR is needed for both run modes | Depends on infrastructure, container config, and compatibility |
| Default reactive stack | Well suited for WebFlux + Reactor Netty | Should not be chosen just to "have a WAR extension" | Spring Boot 3.5 **does not support WAR deployment for WebFlux** per traditional deployment docs |

**Do not infer performance from the file extension:** a JAR is not inherently faster than a WAR, and a WAR does not inherently save RAM. Speed and resource usage depend on the workload, server, thread/connection pools, JVM flags, scaling strategy, and deployment technology. The critical difference is the **boundary of operational responsibility**.

## 4. When Should You Choose an Executable JAR + Embedded Server?

A JAR is the best fit if:

- You are starting a new **microservice**, REST API, new Spring MVC application, job/webhook processor service, or a default WebFlux application running Reactor Netty.
- You want each service to have its **own deployment lifecycle**: build one artifact/image, run one JVM, check health, and scale across multiple instances.
- You use Docker/Kubernetes, systemd, VMs, or a platform that supports running processes/containers directly.
- You want to control the application's Tomcat/Jetty/Undertow version through dependency management and the build pipeline, instead of depending on a shared container administered by another team.
- You want a consistent command across local, CI, and production runtime: `java -jar`.
- There is no policy mandating WAR submission to an application server.

**Strengths:** configuration, dependencies, and server version travel together with the application artifact; it is easy to achieve immutable deployments and image-version rollbacks. Deployments are less affected by other WARs when each app has its own JVM.

**Trade-offs:** you must **update the embedded server yourself** when vulnerabilities arise; multiple JVMs/instances mean each app has its own heap, thread pools, and runtime overhead. You should not claim that a one-container/JVM-per-service architecture is always cheaper than a shared environment.

**Note:** an executable JAR is **not** a prerequisite for using Spring Boot; you can run `bootRun`/`spring-boot:run` directly during development. For release, building `bootJar` or `spring-boot:repackage` produces the artifact for the `java -jar` path.

## 5. When Should You Choose a WAR Deployed to an External Servlet Container?

A WAR is appropriate when the organization already has clear constraints, such as:

- Production systems only support deploying **WARs via centrally managed Tomcat/Jetty/Servlet servers**, with release/rollback procedures following that infrastructure.
- You are **modernizing a traditional Spring MVC application** and want to migrate incrementally to Spring Boot without yet being allowed to change the deployment method.
- The platform team owns the container version, connectors, TLS, thread pools, and operational policies, and wants to manage them at the shared server level.
- Multiple servlet applications currently share an application server; migration needs to preserve the deployment mechanism to limit infrastructure changes in a given phase.
- Contracts or integration systems require a standard-structured `.war` artifact.

**Trade-offs:**

1. The external servlet container/JDK version must be **compatible** with the Spring Boot version in use; Boot 3.x code compiled against `jakarta.servlet` will not fit an environment supporting only the legacy `javax.servlet`.
2. When multiple WARs share one JVM/container, there can be conflicts in classloaders, logging, resource/thread pools, configuration, and mutual impact during container restarts.
3. Rolling back a single WAR may be constrained by undeploy/redeploy mechanics and container state; it is not identical to restarting an independent container image.
4. Several `server.*` application properties do not govern an external container the way they do an embedded server.
5. Bugs that only appear in an external container (context path, servlet initialization, JNDI, container-provided APIs) require real deployment testing; simply running `java -jar app.war` is not enough.

**Warning:** Choosing a WAR because "an external server is definitely more secure" or "WAR is always faster" is an unfounded assumption. An external server requires its own patching policy, application isolation, logging, and monitoring.

## 6. Executable WAR Does Not Mean the WAR Must Use an External Container

A **properly repackaged Spring Boot WAR** can serve both paths:

```text
same app.war file
    |
    +--> java -jar app.war
    |    -> WarLauncher
    |    -> reads WEB-INF/lib-provided
    |    -> starts embedded Tomcat
    |
    +--> Deploy to external Tomcat
         -> Tomcat reads standard WAR structure
         -> uses Servlet initializer
         -> does not load provided libraries as WEB-INF/lib
```

This is useful during migration: operations runs the WAR in the existing container, while developers can still test quickly with `java -jar`. However, you must **test both paths** because the classpath, context path, server configuration, and servlet runtime version differ.

**How it is packaged matters more than the `.war` extension:** a plain WAR that has not gone through Spring Boot repackaging can deploy to Tomcat, yet `java -jar` reports no entry point. Conversely, an executable WAR with the wrong initializer or wrong servlet dependency scope may run via `java -jar` but fail to deploy to an external Tomcat.

## 7. Support Scope: Servlet, WebFlux, and Versions

### 7.1. Servlet MVC and Embedded Servers

In Spring Boot 3.5, embedded servlet container options include Tomcat 10.1, Jetty 12, and Undertow 2.3 compatible with the Servlet 6.0 line. By default, `spring-boot-starter-web` uses Tomcat; you can swap in the Jetty/Undertow starter if appropriate.

For **external containers**, the Spring Boot 3.5 documentation states that you can deploy to Servlet **5.0+** compatible servlet containers. In practice, you must also check the JDK, Jakarta namespace, API/security, and vendor support; using a **compatible Tomcat 10.1** is a safe illustrative choice for Boot 3.5. Avoid deploying Boot 3.x onto Tomcat 9.x based on `javax.servlet` and expecting it to work.

Do not apply Spring Boot 3.5's Tomcat/Servlet versions to Spring Boot 4.x without checking the 4.x documentation; the packaging strategy is similar, but library baselines may differ.

### 7.2. WebFlux Does Not Use Traditional WAR

The Spring Boot 3.5 documentation warns that **WAR deployment is not supported for Spring WebFlux applications**. For reactive WebFlux applications typically using `spring-boot-starter-webflux` and Reactor Netty, the straightforward choice is an executable JAR running an embedded server. Although some reactive libraries can integrate with a servlet foundation in other scenarios, **do not** assume that merely changing `<packaging>war</packaging>` makes Spring Boot WebFlux deployable as a traditional WAR.

### 7.3. Do Not Confuse an Embedded Server with a Proxy

Both standalone JARs and WARs can still sit behind **Nginx, Apache HTTP Server, an ingress controller, or a cloud load balancer**. A reverse proxy handles HTTP routing/TLS/traffic, and **is not necessarily a servlet container**. Having Nginx in front **does not require** building a WAR.

## 8. Shared Java 17 Example When Switching Between JAR and WAR

Suppose an application named `deployment-demo` uses Spring Boot 3.5.x, Java 17, and the `spring-boot-starter-web` dependency. We will use an entry-point class that can run via `main` and support traditional WAR deployment so that the comparison is not skewed by business code changes.

### 8.1. Source Structure

```text
deployment-demo/
├── pom.xml                       # if using Maven
│   or
├── settings.gradle               # if using Gradle Groovy
├── build.gradle
├── src/main/java/com/example/deploy/
│   ├── DeployApplication.java
│   └── HelloController.java
├── src/main/resources/application.properties
└── src/test/java/com/example/deploy/
    └── HelloControllerTest.java
```

Only create the build files for **one** tool per project. In real deployments, the Maven Wrapper or Gradle Wrapper is committed alongside the source (e.g., `mvnw` or `gradlew`).

### 8.2. Main Class for Both Startup Paths

File `src/main/java/com/example/deploy/DeployApplication.java`:

```java
package com.example.deploy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class DeployApplication extends SpringBootServletInitializer {

    public static void main(String[] args) {
        SpringApplication.run(DeployApplication.class, args);
    }

    @Override
    protected SpringApplicationBuilder configure(SpringApplicationBuilder application) {
        return application.sources(DeployApplication.class);
    }
}
```

The two entry points serve different roles:

- `main(...)` is for the **java -jar** path. Spring Boot Loader invokes the main class specified by `Start-Class`, and then `SpringApplication.run` starts the application and embedded server.
- `configure(...)` from `SpringBootServletInitializer` is for the **external servlet container** path. External Tomcat initializes the application context via Servlet startup **without calling `main`**.

Extending `SpringBootServletInitializer` in the JAR example is **not required**; it just keeps the shared source easy to switch. If a new JAR project has no plans for a WAR, a simple main class with `@SpringBootApplication` and `main` is enough.

### 8.3. Controller

File `src/main/java/com/example/deploy/HelloController.java`:

```java
package com.example.deploy;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public String hello() {
        return "Hello from Spring Boot";
    }
}
```

File `src/main/resources/application.properties`:

```properties
spring.application.name=deployment-demo
server.port=8080
```

When run as a **standalone executable JAR/WAR** with no other configuration, HTTP GET `http://localhost:8080/hello` returns the body:

```text
Hello from Spring Boot
```

This is the **HTTP response body**, not the entire stdout; startup logs and `curl` trailing newlines depend on the terminal/environment. If port 8080 is already taken, pass `--server.port=8081` after the JAR/WAR name and access 8081.

In an **external Tomcat**, the URL is usually `http://localhost:8080/<context-path>/hello`, where the context path is determined by the WAR/application name and container configuration. The `server.port` value in `application.properties` **does not control** the external Tomcat's HTTP listener port.

### 8.4. Smoke Test Independent of Port or WAR Context Path

File `src/test/java/com/example/deploy/HelloControllerTest.java`:

```java
package com.example.deploy;

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
class HelloControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void helloEndpointWorks() throws Exception {
        mockMvc.perform(get("/hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello from Spring Boot"));
    }
}
```

This test uses JUnit Jupiter and `spring-boot-starter-test` (added in the build files below). It verifies Spring MVC behavior in the **test application context**, without needing to deploy a WAR into an external Tomcat. **It does not replace a deployment integration test** on the target container, because the classpath and servlet lifecycle differ.

### 8.5. Conditions to Run the Code

The Java files in section 8 use Java 17 syntax, but they cannot be compiled with a bare `javac` command missing Spring/JUnit dependencies. Maven/Gradle will download the corresponding classpath. Running only `javac DeployApplication.java` will fail because the Spring APIs cannot be found; that is not an error in the example.

## 9. Maven: Default Executable JAR

### 9.1. Full POM for JAR

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>deployment-demo</artifactId>
    <version>0.1.0-SNAPSHOT</version>
    <packaging>jar</packaging>

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
```

Explanation:

1. `<packaging>jar</packaging>` is the output archive type. If omitted in a standard Maven project, the default is also `jar`.
2. `spring-boot-starter-web` brings Spring MVC and embedded Tomcat into the default dependency graph.
3. `spring-boot-maven-plugin` performs `repackage` to produce the **executable JAR** (for POMs inheriting the Boot starter parent, the execution is already configured). It creates the `BOOT-INF` layout and appropriate manifest.
4. `spring-boot-starter-test` in test scope does not put JUnit into the runtime application as a production dependency.
5. The Boot parent manages starter versions; do not assign individual starter versions arbitrarily.

### 9.2. Build and Run

```bash
# Unix/macOS, from the Maven project directory with Maven Wrapper
./mvnw clean verify

# Check the actual artifact in target/
java -jar target/deployment-demo-0.1.0-SNAPSHOT.jar

# Another terminal after the app starts
curl -s http://localhost:8080/hello
```

Expected response body: `Hello from Spring Boot`. On Windows use `mvnw.cmd clean verify`; the JAR file in `target` keeps the default naming when built.

**`clean` is not required every time:** `./mvnw package` is usually sufficient for packaging, while `verify` runs through the verification phase. `clean` is helpful when you suspect stale outputs are causing confusion.

A Spring Boot 3.5 executable JAR manifest typically contains:

```text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.deploy.DeployApplication
```

In addition, the archive contains `BOOT-INF/classes/com/example/deploy/DeployApplication.class` and nested JARs in `BOOT-INF/lib`.

## 10. Maven: Switching to Executable/Deployable WAR

### 10.1. Minimal Meaningful Changes

Keep the Java source from section 8 and most of the POM from section 9, but:

1. Change `<packaging>jar</packaging>` to `<packaging>war</packaging>`.
2. Mark embedded Tomcat as `provided`.
3. Keep `spring-boot-maven-plugin` so Spring Boot repackages it into an executable WAR.
4. Keep `SpringBootServletInitializer` so an external container initializes the application.

Required fragment in the WAR POM:

```xml
<packaging>war</packaging>

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
```

**This is a replacement snippet** for `<packaging>` and `<dependencies>` in the section 9 POM—**do not paste a second `<dependencies>` block** into the existing POM. Keep `<parent>`, project coordinates, properties, and `<build><plugins>` as in the JAR example.

Even though `spring-boot-starter-web` pulls in Tomcat transitively, declaring `spring-boot-starter-tomcat` directly in `provided` scope lets Maven apply the intended scope; that is Spring Boot's traditional WAR configuration.

### 10.2. What Does `provided` Mean?

In Maven, `provided` states that the dependency is needed for compile/test but is **supplied by the external container/runtime** in the traditional deployment model. For a Spring Boot **executable WAR**, Boot's repackager still places `provided` dependencies into `WEB-INF/lib-provided`:

- **External Tomcat** does not load them as regular `WEB-INF/lib` libraries, avoiding clashes with the existing Tomcat container.
- **WarLauncher** during `java -jar app.war` can put them on the classpath to start embedded Tomcat on its own.

Do not assume `provided` means **completely deleting Tomcat from the WAR file**; Spring Boot's executable WAR model needs to keep them in a special location. And do not assume `provided` in a WAR means the exact same thing for every provided dependency across all packaging types.

### 10.3. Build and Run Both Paths

```bash
./mvnw clean verify
java -jar target/deployment-demo-0.1.0-SNAPSHOT.war
```

The executable path serves `http://localhost:8080/hello` (unless overridden).

External deployment path: copy/deploy `target/deployment-demo-0.1.0-SNAPSHOT.war` to a compatible Tomcat according to your tools and infrastructure policy. For example, if Tomcat sets the context based on the WAR filename, the URL may be:

```text
http://localhost:8080/deployment-demo-0.1.0-SNAPSHOT/hello
```

**This is only a context path example**, not guaranteed to match if operations sets a different context name, uses `ROOT.war`, a reverse proxy, host configuration, or API deployment.

Spring Boot 3.5 documentation notes that an executable WAR's `Main-Class` uses `org.springframework.boot.loader.launch.WarLauncher`. **External Tomcat does not invoke this launcher**; instead it initializes the application through the Servlet container lifecycle and initializer.

## 11. Gradle: Executable JAR with `bootJar`

A Gradle Groovy DSL project needs `settings.gradle`:

```groovy
rootProject.name = 'deployment-demo'
```

And `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.1.0-SNAPSHOT'

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
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is a **JAR** build script; the `war` plugin is not applied. The Spring Boot Gradle plugin creates the `bootJar` task when using the Java plugin to produce an executable JAR; `jar` typically creates a plain Java JAR.

```bash
./gradlew clean test bootJar
java -jar build/libs/deployment-demo-0.1.0-SNAPSHOT.jar
```

On Windows: `gradlew.bat clean test bootJar`. The archive name assumes the `rootProject.name` and `version` above; if a different classifier/name is configured, check `build/libs` to pick the right file.

The `bootRun` task is **not** the executable JAR path: it runs directly against the source set's runtime classpath during development. To verify the Boot Loader and packaged contents, you must run `java -jar` on the actual artifact.

## 12. Gradle: Executable/Deployable WAR with `bootWar`

### 12.1. Differences in `build.gradle`

Convert the `JAR` build in section 11 into a `WAR` configuration. The following is the **complete `build.gradle` file**:

```groovy
plugins {
    id 'java'
    id 'war'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.1.0-SNAPSHOT'

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

    // Needed when running executable WAR, but the external container will provide Tomcat
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

When the `war` plugin is applied alongside the Spring Boot plugin, the `bootWar` task packages the executable WAR. The `providedRuntime` configuration is provided by the `war` plugin; Boot's `bootWar` places these dependencies into `WEB-INF/lib-provided`.

**Use `providedRuntime` instead of `compileOnly`** for the embedded container: Spring Boot documentation explains that `compileOnly` does not appear on the test classpath, which can cause web-based integration tests to fail; `providedRuntime` is better suited for the deployable WAR model.

Gradle may generate multiple archive tasks such as `war`, `bootWar`, or `bootJar` depending on plugins/config; **do not guess** which file was produced solely from the extension or from `build`. Invoke the `bootWar` task directly when you need an executable/deployable WAR.

### 12.2. Build, Run Standalone, and Deploy Externally

```bash
./gradlew clean test bootWar
java -jar build/libs/deployment-demo-0.1.0-SNAPSHOT.war
```

Even though `providedRuntime` is used, `java -jar` still has embedded Tomcat via `lib-provided`. For external deployment, hand this `.war` file to a compatible servlet container; do not copy a `.jar` file and expect Tomcat to read it as a WAR web application.

When you only want to inspect the structure:

```bash
jar tf build/libs/deployment-demo-0.1.0-SNAPSHOT.war
```

Look for `WEB-INF/classes/com/example/deploy/DeployApplication.class`, `WEB-INF/lib`, `WEB-INF/lib-provided`, and the loader classes. Exact starter/Tomcat filenames depend on the build version.

### 12.3. Equivalent Kotlin DSL

If the project uses `build.gradle.kts`, the key changes are:

```kotlin
plugins {
    java
    war
    id("org.springframework.boot") version "3.5.16"
    id("io.spring.dependency-management") version "1.1.7"
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    providedRuntime("org.springframework.boot:spring-boot-starter-tomcat")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}
```

This is a **fragment** to place in `build.gradle.kts` together with `group`, `version`, `java { toolchain { ... } }`, and `repositories { mavenCentral() }` from the Groovy sample converted to Kotlin syntax. Do not mix Groovy single quotes `id 'war'` with Kotlin DSL.

## 13. Where Dependencies Live in the Archive: Reading the Layout Correctly

### 13.1. Executable JAR

```text
deployment-demo-0.1.0-SNAPSHOT.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/com/example/deploy/DeployApplication.class
    ├── classes/com/example/deploy/HelloController.class
    ├── classes/application.properties
    └── lib/
        ├── spring-boot-*.jar
        ├── tomcat-embed-*.jar
        └── ... other runtime dependencies
```

When the JVM reads the manifest, `Main-Class` is typically `org.springframework.boot.loader.launch.JarLauncher` and `Start-Class` is `com.example.deploy.DeployApplication`. The embedded server is loaded as a runtime library of the app.

### 13.2. Executable WAR

```text
deployment-demo-0.1.0-SNAPSHOT.war
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...
└── WEB-INF/
    ├── classes/com/example/deploy/DeployApplication.class
    ├── classes/com/example/deploy/HelloController.class
    ├── classes/application.properties
    ├── lib/
    │   ├── spring-webmvc-*.jar
    │   └── ... application dependencies
    └── lib-provided/
        ├── tomcat-embed-*.jar
        └── ... provided dependencies
```

The JAR names with `*` are illustrative only; actual contents depend on artifacts and versions. For an executable WAR, `Main-Class` is `org.springframework.boot.loader.launch.WarLauncher` and `Start-Class` is the application main class.

**Do not mistake** `WEB-INF/lib-provided` for something external Tomcat actively reads: this packaging keeps dependencies available to **WarLauncher** when running standalone while preventing an external container from loading them twice as a regular `WEB-INF/lib`.

## 14. Configuration Scope Differences Between the Two Server Types

### 14.1. Port, Context Path, TLS

In an executable JAR/WAR, configuring:

```properties
server.port=8081
server.servlet.context-path=/api
```

normally makes Spring Boot configure the embedded servlet server to listen on port 8081 and mount the application under `/api` (assuming no overrides). The demo endpoint is then `http://localhost:8081/api/hello`.

When **deploying a WAR to an external Tomcat**, port 8081, TLS/HTTP connectors, and the context path may be set by Tomcat/server administrators. Do not assume `server.port` or `server.servlet.context-path` will override external Tomcat deployment configuration. Consult the container admin console, `server.xml`/context descriptors, reverse proxy, and actual Tomcat version.

### 14.2. JVM and Shared Resources

A standalone JAR/WAR runs in its own application JVM. Therefore `-Xmx`, GC, and system properties belong to this process and are usually managed by the app's deployment spec/script.

An external Tomcat uses the **container's** JVM. WARs deployed to the same JVM may share heap/GC settings, process uptime, some shared libraries, and the startup/shutdown lifecycle. This can bring centralized management, but also carries the risk of mutual interference and harder per-WAR resource allocation and monitoring.

### 14.3. Logging, Thread Pools, and Databases

- With an embedded server, Spring Boot configures the server and logger within app scope via properties, starters, and custom beans.
- With an external servlet container, the container has its own logging/access logs, thread pools, connectors, and classloader policies. The application also has Spring loggers; avoid binding conflicts or duplicate logs.
- If using a container-provided JNDI DataSource, Spring Boot must be configured to reference the resource with the exact name/location; some traditional WAR projects have this requirement.
- Operational requirement differences cannot be solved merely by changing the artifact extension.

## 15. CI/CD, Docker/Kubernetes, and Patch Management

**JAR with embedded server:** the pipeline builds the JAR, runs tests, builds an image containing the appropriate JDK/JRE and artifact, and deploys multiple instances behind a load balancer. Tomcat is updated by bumping the Spring Boot-managed dependency, rebuilding the artifact/image, testing, and rolling out.

**Executable WAR in a container:** can still be packaged in an image and run via `java -jar app.war`. If the goal is solely standalone execution, this WAR option offers no inherent advantage over a JAR; it is usually chosen when the **same artifact** also needs to support external deployment.

**Externally deployed WAR:** the pipeline builds the WAR, publishes the artifact to a repository, and deploys it to an existing Tomcat/Servlet container; the infrastructure team manages the server, runtime, patches, and restarts according to policy. **Container version compatibility** must be managed in the release process.

### 15.1. Illustrative Dockerfile for JAR

```dockerfile
# Use a Java runtime 17 base image that fits your organization's policy.
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/deployment-demo-0.1.0-SNAPSHOT.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

This example assumes Maven has built the **JAR**, the base image is pullable, and image scanning policies are applied. `EXPOSE 8080` is just Docker metadata; the actual port can be changed via configuration and must be published/mapped/routed at runtime. Avoid running the container with unnecessarily broad privileges or baking secrets into the image; a production system typically configures a non-root user, memory limits, health checks, and logging.

With Gradle, change `COPY` from `target` to the corresponding output path under `build/libs`. A Dockerfile **does not turn an external-deployment WAR into a JAR**; it only illustrates the standalone path.

### 15.2. Health Checks and Rollback Operations

Whether packaging as JAR or WAR, the pipeline should verify:

- The artifact matches the exact **version/commit** and the tested dependency set.
- Readiness/liveness health via Spring Boot Actuator if appropriately configured; do not rely on a health endpoint that does not exist.
- Startup logs have no `ClassNotFoundException`, `NoSuchMethodError`, or binding/port errors.
- An HTTP smoke test hits the environment's actual URL/context path.
- There is a rollback recipe for the **JVM/instance** (JAR) or **container/WAR** (external deployment).

An external container must be patched independently of the WAR; an embedded server must be patched by shipping a new artifact/image. Neither strategy is automatically immune to vulnerabilities.

## 16. Hands-On Comparison of the Three Run Modes on the Same Source

**Prerequisites:** JDK 17+, a properly versioned Maven Wrapper or Gradle Wrapper, Spring Boot 3.5.x, the Java files and test from section 8, port 8080 free, and a compatible external Tomcat if testing WAR deployment.

### 16.1. Run A: Standalone JAR

Maven: use the JAR POM from section 9.

```bash
./mvnw clean verify
java -jar target/deployment-demo-0.1.0-SNAPSHOT.jar
```

Or Gradle: use the JAR build from section 11.

```bash
./gradlew clean test bootJar
java -jar build/libs/deployment-demo-0.1.0-SNAPSHOT.jar
```

In another terminal, call `curl -s http://localhost:8080/hello`. The body is `Hello from Spring Boot`. Observe the server logs started by Spring Boot in the same JVM.

### 16.2. Run B: Standalone WAR

Stop Run A. Use the Maven WAR config from section 10 or Gradle from section 12:

```bash
# Maven
./mvnw clean verify
java -jar target/deployment-demo-0.1.0-SNAPSHOT.war
```

```bash
# Gradle (if your project uses Gradle)
./gradlew clean test bootWar
java -jar build/libs/deployment-demo-0.1.0-SNAPSHOT.war
```

With an executable WAR, the endpoint can still be at `http://localhost:8080/hello` because **embedded Tomcat** is handling requests. Distinguish it from external Tomcat by the launch command and process origin.

### 16.3. Run C: WAR into External Tomcat

Stop any standalone processes first to avoid port conflicts. Start a compatible external Tomcat and deploy the **newly built WAR** using the container's mechanism.

- Do not run `java -jar app.war` in this run.
- Check Tomcat logs to verify the application is initialized via `SpringBootServletInitializer`.
- Determine the WAR's context path per the deploy config; try `/deployment-demo-0.1.0-SNAPSHOT/hello` if the container uses the WAR filename as the context without overrides.
- Returns body `Hello from Spring Boot` if deployment and routing are correct.
- Changing `server.port` inside the WAR does not by default change the external Tomcat's listener port.

**Fair comparison criteria:** same source, compatible JDK/Servlet API, same business properties, database, and environment; only change the packaging/launcher or container deployment path. If differences appear, check the classpath, provided dependencies, context path, profiles, and container logs.

## 17. Symptom-Based Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `no main manifest attribute` on `java -jar` | Running a plain JAR/WAR or missing Boot `repackage` | Build properly with `package`/`bootJar`/`bootWar`; inspect manifest and artifact |
| `JarLauncher`/`WarLauncher` not found | Archive/manifest malformed by custom packaging | Use the right Spring Boot build plugin version; inspect loader classes |
| JAR runs, but WAR does not start in external Tomcat | Missing `SpringBootServletInitializer` subclass or incompatible Servlet runtime | Add initializer; check JDK/Jakarta/Servlet versions and container logs |
| `ClassNotFoundException: jakarta.servlet.*` | Incompatible Servlet API dependency/container | Check external container and embedded server scope |
| `ClassCastException`/`LinkageError` on WAR deploy | Duplicate/mismatched server library or shared library versions | Check `WEB-INF/lib`, `lib-provided`, classloader policies, and server version |
| `server.port` has no effect in external Tomcat | Port is managed by Tomcat | Edit connector/container config, not just `application.properties` |
| `/hello` returns 404 in external Tomcat | Wrong context path or routing/scan issue | Try `/<context>/hello` matching deployment name; check logs |
| `java -jar app.war` fails due to missing embedded Tomcat | Wrong `provided`/`providedRuntime` or packaging, or excluded | Check `lib-provided` and Spring Boot repackaging |
| `providedRuntime` does not exist in Gradle | `war` plugin not applied or wrong DSL used | Add `id 'war'`/`war` and use `providedRuntime` |
| WAR has only `WEB-INF/lib`, no `lib-provided` | Might be a plain WAR, didn't run Boot repackager, or has no provided deps | Check build task/goal and Tomcat provided declaration |
| WebFlux cannot be deployed as a WAR | Traditional WAR deployment does not support WebFlux in Spring Boot 3.5 | Use an executable JAR + embedded reactive runtime |
| Standalone JAR works, but container webapp fails on JNDI | External Tomcat's context/resource naming differs | Configure JNDI and Spring properties to match the environment |
| JAR/WAR filename differs from sample command | Project version, artifact ID, classifier, or archive name changed | List `target`/`build/libs` instead of guessing |
| CI calls `bootJar` but WAR is missing | `bootJar` task does not produce `bootWar` | Invoke `bootWar`/`package` with the right packaging |
| External WAR accidentally committed Tomcat `provided` as normal runtime | Duplicate embedded servlet library in `WEB-INF/lib` | Set `provided`/`providedRuntime` scope; inspect the archive |

### 17.1. Quick Inspection Commands

```bash
# Check that the archive has application classes and dependencies in the right layout
jar tf target/deployment-demo-0.1.0-SNAPSHOT.war

# Equivalent Gradle WAR
jar tf build/libs/deployment-demo-0.1.0-SNAPSHOT.war

# Maven dependency graph (in a Maven project)
./mvnw dependency:tree

# Gradle runtime dependency graph (in a Gradle project)
./gradlew dependencies --configuration runtimeClasspath
```

Run only the command matching your build tool and artifact type. If the terminal lacks `jar`, use a full JDK or a reliable ZIP reader. `jar tf` verifies entry presence but **does not prove the archive starts successfully**; always test `java -jar` or a real deployment.

## 18. Decision Tree for Choosing JAR or WAR

```text
Spring Boot app needs deployment
              |
              v
Is there a MANDATORY requirement to deploy
into an external Servlet container?
        /                  \
       No                  Yes
       |                    |
       v                    v
Using reactive WebFlux?   Servlet MVC app?
   /        \               /          \
 Yes         No           Yes          No
  |           |            |            |
  v           v            v            v
JAR +       JAR +       WAR +        Re-examine
embedded    embedded    Servlet      architecture/WAR
reactive    servlet     initializer  feasibility first
runtime     server          |
                            v
                  Compatible external Tomcat
                            |
                            v
                 Need to run same WAR standalone?
                           /  \
                         Yes   No
                          |     |
                          v     v
                     Boot executable WAR
                     with providedRuntime/
                     provided dependency
                     (can still deploy externally)
```

In the **no external container needed** branch, you can still use an executable WAR if the organization requires a WAR-type artifact, though you should understand this is a special release requirement rather than a natural technical need of a new microservice. When both JAR and WAR meet the requirements, the option with **fewer infrastructure differences and fewer special steps** is usually easier to operate.

## 19. Decision and Acceptance Checklist

1. **Runtime model:** Dedicated JVM or shared servlet container? Who provides the HTTP server?
2. **Infrastructure constraints:** Is there a WAR-only policy? Is there CI/CD for JAR/containers?
3. **Application type:** Spring MVC/Servlet or WebFlux/reactive? With Boot 3.5, WebFlux does not use traditional WAR deployment.
4. **Versions:** Are Java, Spring Boot, embedded/external servlet container, and Jakarta Servlet API compatible?
5. **Packaging:** Are Maven `jar/war` and `repackage` or Gradle `bootJar/bootWar` configured properly?
6. **Initializer:** If external WAR, are `SpringBootServletInitializer` and the Boot application source configured properly?
7. **Dependency scope:** Does an external WAR have `provided`/`providedRuntime` for the servlet container dependency and `WEB-INF/lib-provided`?
8. **Artifacts:** Do the actual manifest and layout match `JarLauncher`/`WarLauncher` and `BOOT-INF`/`WEB-INF`?
9. **Port/context:** Is the endpoint tested against the standalone route or the external container's context path?
10. **Patching process:** Who is responsible for updating Tomcat/JDK? Is independent rollback possible?
11. **Resources and logs:** Are there any conflicts with shared logging, JDBC, JNDI, connectors, or classloaders?
12. **CI/CD:** Do build/test and smoke tests run on the **exact production deployment path**?
13. **Observability:** Are health/metrics/logging and alerting appropriate for the JVM/app/container?
14. **Migration risk:** If moving from a legacy WAR system to Boot, can you stage the path as traditional WAR → executable WAR → JAR if operations allows?

### Official Documentation

- [Spring Boot 3.5 — Traditional Deployment](https://docs.spring.io/spring-boot/3.5/how-to/deployment/traditional-deployment.html)
- [Spring Boot 3.5 — System Requirements (Java and Servlet containers)](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
- [Spring Boot 3.5 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html)
- [Spring Boot 3.5 — Maven Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html)
- [Spring Boot 3.5 — Gradle BootWar API](https://docs.spring.io/spring-boot/3.5/gradle-plugin/api/java/org/springframework/boot/gradle/tasks/bundling/BootWar.html)
- [Spring Boot 3.5 — SpringBootServletInitializer API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/servlet/support/SpringBootServletInitializer.html)

**Key takeaway:** **JAR + embedded server** is the convenient default choice for most new Spring Boot applications. **WAR** should have a clear reason — especially when deploying to an **external servlet container** is required. An **executable WAR** can also run standalone via `java -jar` thanks to `WarLauncher` and `WEB-INF/lib-provided`, but that does not eliminate the need for real testing on an external container.
