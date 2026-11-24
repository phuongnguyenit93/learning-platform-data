# Deploying on a Servlet Container and Distinguishing WAR from an Embedded Server

## 1. The Problem: Where Does a Spring MVC Application Actually Run?

Spring MVC processes HTTP requests through the **Servlet API**, yet application code does not open sockets or implement the HTTP protocol itself. A **Servlet container** (such as Apache Tomcat or Jetty) accepts connections, creates request/response objects, manages Servlet/Filter lifecycles, and invokes Spring MVC's `DispatcherServlet` to dispatch to controllers.

There are two common deployment styles:

1. **Embedded server**: a Spring Boot application is packaged as an executable JAR and starts Tomcat/Jetty itself when running `java -jar`. The application's Java process owns the HTTP server and its lifecycle.
2. **External/traditional Servlet container**: operators start Tomcat/Jetty beforehand; the application is packaged as a **WAR** and deployed into that container. The container manages the web application, context path, and Servlet lifecycle per the deployment contract.

They can serve the exact same REST endpoint and both use Spring MVC. The differences lie in **startup mechanism, dependency packaging, ownership of HTTP ports, context paths, and operations**.

```text
Approach A — Spring Boot executable JAR + embedded Tomcat

shell / systemd / container runtime
             |
             v
     java -jar app.jar
             |
             v
  SpringApplication.run(...)
             |
             v
 ApplicationContext + embedded Tomcat
             |
             v
    DispatcherServlet -> Controller

Approach B — WAR on external Tomcat

shell / systemd / container runtime
             |
             v
        Start Tomcat
             |
             v
   Tomcat deploys app.war
             |
             v
   SpringBootServletInitializer
             |
             v
 ApplicationContext + DispatcherServlet
             |
             v
          Controller
```

**Important:** Spring MVC is the web framework; the **Servlet container** is the request-serving runtime; **WAR/JAR** is the artifact format. "WAR" does not mean "legacy Spring MVC"; a properly configured WAR can still run modern Spring Boot.

## 2. What Is the Servlet Container Responsible For?

A Servlet container implements the Jakarta Servlet specification and provides the runtime environment for one or more web applications. Primary responsibilities:

- Opening HTTP/HTTPS listeners, receiving requests, and converting them into `HttpServletRequest`/`HttpServletResponse`.
- Creating and managing `ServletContext`, Servlets, Filters, and Listeners across the deployment lifecycle.
- Handling Servlet-level request mapping, dispatcher types, sessions, timeouts, async servlets, and other requirements within the Servlet specification.
- Isolating applications by **context path** (such as `/shop` and `/admin`), typically using separate application classloaders.
- When undeploying/redeploying, stopping the web application, releasing resources where possible, and loading the new version. Connections, threads, or static state mismanaged by application code can still leak resources.

Spring MVC adds the dispatch layer:

```text
HTTP request
    |
    v
Servlet container
    |
    v
Filter chain
    |
    v
DispatcherServlet (a Spring MVC Servlet)
    |
    +--> HandlerMapping
    +--> HandlerAdapter -> @Controller / @RestController
    +--> MessageConverter / ViewResolver
    +--> ExceptionResolver
    |
    v
HTTP response
```

`DispatcherServlet` itself does not replace the container: it is a component **registered inside the container**, whether the container is embedded or started by a separate server.

## 3. What Is an Embedded Server?

An embedded server is a **Servlet container library included in the application's dependencies/runtime** and created when the application process runs.

With Spring Boot 3.5:

- `spring-boot-starter-web` typically brings in `spring-boot-starter-tomcat` by default.
- Spring Boot auto-configuration creates a `ServletWebServerApplicationContext` and uses the appropriate `ServletWebServerFactory` to start embedded Tomcat/Jetty/Undertow.
- `SpringApplication.run(...)` creates the application context, registers DispatcherServlet along with Servlets/Filters/Listeners, and the server begins serving requests.
- `server.port`, `server.address`, `server.servlet.context-path`, and other server properties control the **embedded server** within supported capabilities.

Configuration example:

```yaml
# src/main/resources/application.yml
server:
  port: 8085
  servlet:
    context-path: /catalog
```

With an executable JAR containing a `@GetMapping("/books")` controller, the external endpoint is `http://localhost:8085/catalog/books`. The `/catalog` context path belongs to the Servlet context, while `/books` is the controller path.

Practical advantages: single self-contained artifact, each application owns its container and dependency versions, easy packaging into container images or running under a service manager; scaling horizontally by running more instances behind a load balancer. This **does not force** every system to adopt microservices.

Operational trade-offs: each process manages its own resources/ports/server lifecycle; operations must standardize configuration, logs, shutdown, health checks, and applying embedded container security patches via dependency/build updates.

## 4. What Are a WAR and an External Servlet Container?

A **WAR (Web Application Archive)** is a web application package structured per Java/Jakarta EE conventions understood by Servlet containers. With traditional deployment:

1. Build `app.war`.
2. Place the artifact into Tomcat/Jetty's deployment directory or use the server's deployment tooling.
3. The container detects the archive, sets up the web application context, loads classes/resources, and initializes Spring MVC.
4. Requests to the WAR's context path pass through the filter chain to `DispatcherServlet`.

Tomcat can run multiple WARs inside the same process, for example:

```text
Tomcat process (HTTP :8080)
  |
  +-- /shop    -> shop.war    -> Spring MVC app A
  |
  +-- /admin   -> admin.war   -> Spring MVC app B
  |
  +-- /reports -> reports.war -> Spring MVC app C
```

Each WAR usually gets its own web application classloader and its own `ServletContext`. However, they still **share the same JVM/container process**: CPU, memory, thread capacity, container policies, ports, and cross-application blast radius. Thus "multiple WARs in one Tomcat" does not automatically provide the isolation of separate processes/containers.

Advantages: fits organizations with an operations-managed Java application server platform, deploying/redeploying apps onto existing servers, and enforcing shared container policies. Trade-offs: managing compatibility between WARs and the container, deployment configuration, classloading, shared libraries, and server lifecycle; upgrading the container affects multiple applications on the same instance.

**WAR does not mean all libraries are supplied by the container.** Containers typically supply the Servlet API and container implementation; business dependencies, Spring Framework, and most application dependencies are still packaged inside the WAR. Exactly what uses `provided` must be decided against the target environment's contract.

## 5. Comparing Executable JAR, Deployable WAR, and Executable WAR

| Criterion | Executable JAR + Embedded Server | WAR on External Container | Spring Boot Executable WAR |
| --- | --- | --- | --- |
| Who starts the HTTP server? | Application's `main`/Spring Boot | External Tomcat/Jetty | With `java -jar`: Spring Boot; when deployed: external container |
| Artifact | `.jar` with Boot loader and dependencies | `.war` with web application structure | `.war` repackaged by Spring Boot |
| Command/model | `java -jar app.jar` | Deploy WAR to server, start server | `java -jar app.war` **or** deploy WAR |
| Servlet container runtime | Packaged for execution | Supplied by external server | `WEB-INF/lib-provided` for execution; externally uses server's container |
| HTTP port | Usually from `server.port` | Configured by external container | Depends on run mode |
| Context path | Embedded server's `server.servlet.context-path` | Usually determined by server deployment/context | Depends on run mode |
| Process isolation | Typically one app per JVM/process | Multiple WARs can share a JVM | Depends on mode |
| Container upgrades | Update dependency and rebuild artifact | Operations team upgrades server | Whichever mode uses that container |
| Operational risks to verify | JVM/process, ports, image builds, and lifecycle | Shared server, classloading, context path, server patches | Must test **both modes** if supporting both |

**Crucial distinction:** WAR is a **format**; embedded/external is a **run mode**. Spring Boot can build an **executable WAR** deployable to external Tomcat that also runs via `java -jar app.war` when container dependencies are packaged properly.

## 6. Packaging Structure and Classpath

A Spring Boot executable JAR typically looks like:

```text
catalog.jar
├── META-INF/MANIFEST.MF
├── BOOT-INF/
│   ├── classes/             # application classes and resources
│   └── lib/                 # dependencies
└── ...                      # Spring Boot loader
```

A WAR deployed to a Servlet container has the basic structure:

```text
catalog.war
├── META-INF/
└── WEB-INF/
    ├── classes/             # application classes and resources
    ├── lib/                 # libraries running in external container
    └── lib-provided/        # Boot executable WAR portion, if present
```

`WEB-INF/lib-provided` is a helpful detail of **executable WARs packaged by the Spring Boot plugin**, not a general requirement of all WARs: it lets `java -jar catalog.war` find embedded Tomcat, while an external Servlet container does not load libraries from this folder into the app in the standard way.

Packing embedded Tomcat implementation into `WEB-INF/lib` when deploying a WAR to an external Tomcat can cause duplicate implementations, classloader issues, or dependency conflicts. In Maven, place the Tomcat starter in scope `provided`; the Spring Boot plugin can still package it into `lib-provided` for an executable WAR. In Gradle, use `providedRuntime` matched with the WAR/Boot plugins.

**Do not confuse** `provided` with "Servlet API not needed at compile time": the application still needs the appropriate API on the compile classpath. It means that dependency is supplied by the **external** runtime environment when deploying the WAR.

## 7. Complete Example: One Codebase Running as a WAR on External Tomcat or Directly via java -jar

The example uses **Java 17+, Spring Boot 3.5.16, Maven 3.6.3+, and Tomcat 10.1**. This is a compatible combination in the Boot 3.5 line: Spring Framework 6.x uses `jakarta.servlet.*`, and Tomcat 10.1 implements Jakarta Servlet 6.0. Readers do not need to install a separate standalone Servlet API JAR.

**Project structure:**

```text
deploy-demo/
├── pom.xml
└── src/main/java/example/deploy/
    ├── DeployDemoApplication.java
    └── HelloController.java
```

### 7.1. Maven pom.xml: WAR Packaging and Provided Tomcat

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>deploy-demo</artifactId>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-tomcat</artifactId>
            <scope>provided</scope>
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

`spring-boot-starter-web` brings in Spring MVC and references the Tomcat starter by default. Explicitly declaring `spring-boot-starter-tomcat` as `provided` keeps the container implementation out of standard runtime deployment dependencies for external containers. The parent and Boot Maven Plugin handle executable WAR packaging appropriately.

### 7.2. Application Class and the Second Entry Point

**`src/main/java/example/deploy/DeployDemoApplication.java`:**

```java
package example.deploy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class DeployDemoApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(SpringApplicationBuilder builder) {
        return builder.sources(DeployDemoApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(DeployDemoApplication.class, args);
    }
}
```

The two entry points serve distinct roles:

- **Direct `java -jar` execution:** `main(String[])` is invoked by the Spring Boot launcher and starts SpringApplication along with embedded Tomcat.
- **External Tomcat deployment:** the container integrates with Servlet `WebApplicationInitializer`; `SpringBootServletInitializer` acts as the bridge to create the Spring ApplicationContext from the Servlet container's lifecycle. `configure(SpringApplicationBuilder)` specifies the source configuration.

`SpringBootServletInitializer` supports **traditional WAR deployment**. For ordinary executable JARs, extending this class is unnecessary; keeping it in a codebase supporting both modes works fine.

### 7.3. Controller Unaware of Packaging Type

**`src/main/java/example/deploy/HelloController.java`:**

```java
package example.deploy;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public String hello() {
        return "Hello from Spring MVC";
    }

    @GetMapping("/servlet")
    public String servlet(HttpServletRequest request) {
        int major = request.getServletContext().getMajorVersion();
        int minor = request.getServletContext().getMinorVersion();
        return "Servlet " + major + "." + minor;
    }
}
```

The controller is identical in both deployment modes. `HttpServletRequest` is the **Jakarta** type, compatible with Spring 6/Tomcat 10.1. The `/servlet` endpoint reads the Servlet specification version reported by the runtime container.

### 7.4. Building and Running the WAR in Embedded Mode

From the directory containing `pom.xml`:

```bash
java -version
mvn -version
mvn clean package
java -jar target/deploy-demo-0.0.1-SNAPSHOT.war
```

Test from another terminal:

```bash
curl -s http://localhost:8080/hello
curl -s http://localhost:8080/servlet
```

Body output with Boot 3.5's default embedded Tomcat 10.1:

```text
Hello from Spring MVC
Servlet 6.0
```

The two lines are the output **of two consecutive `curl` commands**, not a single combined response. Use `curl.exe` in PowerShell if the `curl` alias does not behave as expected.

Because the artifact is a Boot-repackaged executable WAR, `java -jar ...war` is supported; this is a Spring Boot build plugin feature and does not apply by default to plain Java WARs.

### 7.5. Deploying the Same WAR to External Tomcat 10.1

Assume you have **Tomcat 10.1** installed and running on Java 17+. Stop the embedded instance on `:8080` first to avoid port conflicts. Steps on a standard local Tomcat:

1. Build `mvn clean package` and locate `target/deploy-demo-0.0.1-SNAPSHOT.war`.
2. Place it at `$CATALINA_BASE/webapps/catalog.war`, or use the container's official deployment interface/mechanism. `CATALINA_BASE` is the Tomcat instance configuration path (not necessarily identical to `CATALINA_HOME`).
3. Start Tomcat using its provided script (for example `bin/catalina.sh run` on Linux/macOS or `bin\catalina.bat run` on Windows), depending on instance setup.
4. Check deployment logs; if the default context path derived from the WAR filename is `catalog` and Tomcat listens on `:8080`, call:

```bash
curl -s http://localhost:8080/catalog/hello
curl -s http://localhost:8080/catalog/servlet
```

Expected body output:

```text
Hello from Spring MVC
Servlet 6.0
```

Why does the URL include `/catalog` in this mode? With Tomcat's standard auto-deploy mechanism, `catalog.war` is typically deployed under context path `/catalog`. If deployed as `ROOT.war` or configured with a different context descriptor/virtual host, the path changes per container configuration. Do not hardcode `/catalog` into `@GetMapping` just to "match the WAR".

Port `8080` in the external WAR example belongs to **Tomcat config**. Setting `server.port=8085` in the WAR's Spring Boot application properties should not be expected to change external Tomcat's listening port; the port belongs to the target container.

### 7.6. Same Controller Switched Back to Executable JAR

When you only want to run embedded Tomcat via an executable JAR, change packaging in `pom.xml` to:

```xml
<packaging>jar</packaging>
```

At the same time, remove the `spring-boot-starter-tomcat` dependency with `scope` `provided`, keeping `spring-boot-starter-web` with Tomcat at normal runtime. `DeployDemoApplication` still compiles and runs (though `SpringBootServletInitializer` is then unnecessary). Then:

```bash
mvn clean package
java -jar target/deploy-demo-0.0.1-SNAPSHOT.jar
```

With the default `:8080` server, `/hello` still returns:

```text
Hello from Spring MVC
```

The difference lies in packaging and container lifecycle. Spring MVC endpoints and business logic need no changes across artifact types unless they depend on deployment configuration.

## 8. If Using Gradle Instead of Maven

Conceptual example for Spring Boot **3.5** with Gradle Groovy DSL, matching `repositories`, plugin versions, and Java setup to your active project:

```groovy
plugins {
    id 'java'
    id 'war'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
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
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
}
```

With the WAR plugin and Boot plugin, the `bootWar` task produces an executable WAR:

```bash
./gradlew bootWar
java -jar build/libs/deploy-demo-0.0.1-SNAPSHOT.war
```

The exact artifact name depends on project name/archive name configuration, so verify under `build/libs` before running. To build an executable JAR instead of a WAR, configure Java/Boot appropriately, drop `war`/`providedRuntime`, use `bootJar`, and keep Tomcat in normal runtime.

**Do not replace `providedRuntime` with `compileOnly` out of habit**: a `compileOnly` dependency can disappear from the test runtime classpath, breaking web integration tests; `providedRuntime` is designed for cases where an external runtime supplies the container while Boot still needs to build an executable WAR.

## 9. Why Does a WAR Need SpringBootServletInitializer While a JAR Usually Does Not?

This comes down to **who activates the Spring ApplicationContext**:

```text
Executable JAR / executable WAR via java -jar
    |
    +--> main(String[])
          |
          +--> SpringApplication.run(...)
                |
                +--> creates ApplicationContext and embedded Servlet container


External Tomcat deploying WAR
    |
    +--> discovers Servlet WebApplicationInitializer
          |
          +--> SpringBootServletInitializer.configure(...)
                |
                +--> creates ApplicationContext in existing ServletContext
                      |
                      +--> registers DispatcherServlet/Filter beans
```

When an external container already supplies `ServletContext` and HTTP listeners, Spring should not spin up a second Tomcat. Likewise, when running an embedded server, Spring Boot must create the container so requests can arrive.

If a Spring MVC app **does not use Spring Boot**, the author can still build a WAR and register `DispatcherServlet` via `web.xml` or Java configuration such as `AbstractAnnotationConfigDispatcherServletInitializer`. `SpringBootServletInitializer` is a **Spring Boot**-specific tool bridging the traditional WAR model with `SpringApplication`.

**Not every `@SpringBootApplication` app can be deployed under an external Servlet container merely by renaming `.jar` to `.war`.** You must actually build a properly structured WAR with the right initializer, container dependency scope, and compatible runtime versions.

## 10. Spring / Jakarta Servlet / JDK / Container Compatibility

The Servlet container and WAR must use **the same API family required by Spring**.

| Illustrative Combination | Servlet API/Namespace | Key Conditions |
| --- | --- | --- |
| Spring Boot 2.7 / Spring Framework 5.3 + Tomcat 9 | Servlet 4.0, `javax.servlet.*` | Legacy line using Java EE/`javax`. |
| Spring Boot 3.5 / Spring Framework 6.2 + Tomcat 10.1 | Servlet 6.0, `jakarta.servlet.*` | Java 17+ for Boot 3.5; container implements Jakarta Servlet 6.0. |
| Spring Boot 3.5 deployed to other Servlet 5.0+ containers | `jakarta.servlet.*` | Spring Boot 3.5 documents support for Servlet 5.0+ compatible containers; still verify exact server/vendor/version. |

**Tomcat 9 is incompatible with Spring 6/Boot 3 WARs** because Tomcat 9 supplies `javax.servlet`, whereas Spring 6 requires `jakarta.servlet`. This is a compile-time and bytecode package/type change; it cannot be resolved by merely upgrading Java or bundling both Servlet API JARs.

**Minimum Java version** is not dictated solely by Tomcat. Spring Boot 3.5.16 requires Java 17+. The machine running external Tomcat must satisfy the **highest requirement** among the server, application, and libraries. A project compiled for Java 21 running on a production JVM with only Java 17 will hit `UnsupportedClassVersionError` unless an appropriate compiler target is configured.

Supported containers documented by Spring Boot 3.5.16 for embedded mode include **Tomcat 10.1 (Servlet 6.0)**, **Jetty 12.0 (Servlet 6.0)**, and **Undertow 2.3 (Servlet 6.0)**. Do not extrapolate these versions to Spring Boot 4.x without reading the new generation's documentation.

## 11. Context Path, Port, Profiles, and Environment-Specific Configuration

### Context Path

- **Executable JAR/embedded container:** typically controlled via `server.servlet.context-path=/catalog`, combined with controller mappings.
- **WAR on external Tomcat:** the context path is typically determined by the WAR filename, context descriptor, or container deployment config. Do not treat `server.servlet.context-path` as the source of truth for an external container's context path.
- **Reverse proxy:** may expose the app at `https://site.example/catalog` while the internal container uses a different context. Path rewriting, forwarded prefixes, and URL generation must be coordinated; WAR/JAR packaging alone does not resolve public URLs.

### Port and Listener

- **Embedded:** `server.port=8085` changes the app's listening port when the embedded web server is enabled.
- **External:** external Tomcat opens listeners via `conf/server.xml`, environment/container config, or that instance's tooling; port configuration belongs to the Tomcat layer, not individual WARs.
- Two WARs in the same Tomcat share the HTTP listener yet typically have distinct context paths.

### Profiles, Environment, and Resources

`application.properties`/`application.yml`, Spring profiles, and externalized configuration work in both modes, yet configuration sources, environment variables, logging, filesystems, and resource paths are shaped by the deployment environment. Do not rely on relative file paths as if the application always launches from the directory containing the artifact.

With WARs, JSPs or `ServletContext`-based resources may behave differently from executable JARs. Spring Boot documentation explicitly notes that JSPs **are not supported in executable JARs**; with Tomcat/Jetty, use compatible WAR deployment when JSPs are needed. REST projects returning JSON rarely depend on JSPs.

## 12. Operations: Deployment, Scaling, Shutdown, and Failure Observation

### Deployment and Upgrades

**Executable JAR:** ship a new artifact/container image to a new process/instance; use a reliable service manager/orchestrator or script to control the process. Rolling deployments are performed at the load balancer/orchestrator level across multiple instances.

**WAR on external container:** deploy/undeploy/redeploy the WAR inside the Tomcat/Jetty instance per container mechanisms; a single Tomcat may be serving multiple applications. Rollbacks must also consider shared dependencies, caches, and out-of-process resources.

Do not promise "zero-downtime WAR redeploys" merely because Tomcat is not restarted: in-flight requests, sessions, async jobs, and web application resources can still be disrupted depending on strategy/container.

### Memory, Threads, Sessions, Classloaders

- Running multiple WARs in one JVM can save some overhead, yet applications compete for threads, heap, GC, and native memory. A memory leak in one WAR can impact the whole server.
- Each embedded JAR usually has its own JVM/process, isolating process failures and allowing independent runtime upgrades; in exchange, process count and total resource overhead can increase.
- In-memory HTTP sessions are not automatically shared across JVMs/instances. When scaling horizontally, evaluate sticky sessions or an external session store (such as Spring Session) as needed.
- Do not leave threads, schedulers, connection pools, or global singletons unclosed when an application stops; repeated WAR redeploys can trigger classloader leaks.

### Logs and Health

In embedded mode, Spring Boot logs and lifecycle attach directly to the app process. In external mode, inspect **both container logs and application logs** (deployment startup, classloading, request mappings). For readiness/liveness probes or metrics, use environment-appropriate health/observability mechanisms; do not equate "Tomcat process is alive" with "all deployed WARs are healthy".

## 13. Common Deployment Errors

| Symptom | Common Cause | Check and Remediation |
| --- | --- | --- |
| `java -jar app.war` reports missing main manifest/loader | Plain WAR was not repackaged by Spring Boot into an executable archive | Check Spring Boot build plugin, package/task, and manifest. |
| WAR deploys yet endpoint 404s at `/hello` | Context path is not root | Try `/catalog/hello` if deployed as `catalog.war`; check deployment logs/context config. |
| `ClassNotFoundException: javax.servlet...` or `jakarta.servlet...` | Spring/framework/library and Servlet container disagree on namespace/version | Align Spring, Servlet API, and container; locate legacy dependencies. |
| `NoSuchMethodError` / `LinkageError` at startup | Conflict between libraries inside the WAR and server APIs/implementations | Inspect dependency tree, `WEB-INF/lib`, server shared libs, and version compatibility. |
| External Tomcat listens on `:8080` despite `server.port=9090` in WAR | Port belongs to external container | Configure connector/listener in Tomcat rather than inside the WAR. |
| `Address already in use: bind` when running executable JAR | Embedded port already occupied by another process | Change `server.port` or stop the occupying process. |
| WAR deploy does not invoke `@SpringBootApplication` | Missing or wrong `SpringBootServletInitializer`/initializer discovery, bad packaging | Check application class, `configure`, WAR packaging, and startup logs. |
| WAR startup hits `UnsupportedClassVersionError` | Production JVM is older than Spring/app/dependency bytecode | Check Java runtime of the **Tomcat process** and compiler target. |
| REST works yet JSPs fail to render in JAR | Executable JAR JSP limitations | Check Spring Boot guidance; when JSPs are needed with Tomcat/Jetty, use WAR. |
| App behind reverse proxy redirects to wrong host/HTTP | Forwarded headers and public URL misconfigured/untrusted | Check proxy, context path, and forwarded-header strategy; not tied to artifact extension. |
| Repeated WAR redeploys increase heap/class count | Thread/resource/classloader leak | Shut down thread executors, close pools/listeners, inspect memory/thread dumps and Tomcat logs. |

### Useful Diagnostic Commands

```bash
# Check Java/Maven used for the build
java -version
mvn -version

# Package and verify newly built files
mvn clean package

# Inspect archive structure without extracting
jar tf target/deploy-demo-0.0.1-SNAPSHOT.war

# Locate Tomcat dependency in Maven tree
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-tomcat

# Call HTTP endpoints; do not auto-follow redirects
curl -i http://localhost:8080/hello
curl -i http://localhost:8080/catalog/hello
```

The final two `curl` commands illustrate **two different modes/contexts**; do not assume both return HTTP 200 simultaneously. With an external Tomcat WAR, if the context is not `/catalog`, substitute the actual deployment path.

To verify the exact artifact Maven built, use `jar tf` to check `WEB-INF/classes/`, `WEB-INF/lib/`, and `WEB-INF/lib-provided/`; inspect Spring/Servlet container logs to confirm whether the initializer ran and the context path was established.

## 14. When to Choose Which Approach?

**Choose executable JAR + embedded Tomcat** when you want a unified runtime bundled with the artifact, standalone container images/services, flexible instance scaling, or have no requirement to use a shared application server. This is the common path for new Spring Boot REST applications.

**Choose WAR on an external container** when the organization/system mandates WAR deployment to existing Tomcat/Jetty servers, centralized multi-app hosting on one server, or specific Servlet deployment/JSP/classloader integration. Prioritize testing on the exact target container vendor and version.

**Choose executable WAR** when you must support **both modes** (traditional deploy and standalone execution for testing/operations) from a single artifact; test both `java -jar .war` and WAR deployment. Avoid maintaining both modes long-term if only one is used, as it multiplies configurations and test scenarios.

Base decisions on concrete criteria: operational contracts, isolation, JVM management, JSP/WAR requirements, deployment workflow, scaling model, network environment, and Servlet container version; not on the assumption that WAR is always legacy and JAR is always modern.

## 15. Self-Assessment

**Question 1.** Does a Spring Boot executable JAR use the Servlet API?  
**Answer:** Yes, if it is a Spring Web MVC app running on embedded Tomcat/Jetty/Undertow. The container runs inside the application process yet still implements the Servlet API.

**Question 2.** Why is `SpringBootServletInitializer` needed when deploying a WAR?  
**Answer:** The external container is already running; the initializer bridges the Servlet deployment lifecycle to creating the Spring Boot ApplicationContext. With `java -jar`, `main` performs startup.

**Question 3.** Why shouldn't `spring-boot-starter-tomcat` be kept at regular runtime scope in a WAR?  
**Answer:** The external container already supplies the Servlet implementation. Marking it `provided`/`providedRuntime` prevents packaging the container runtime as an ordinary deployment dependency; Boot's executable WAR uses `lib-provided` separately.

**Question 4.** If a WAR is named `catalog.war` and Tomcat listens on `:8080`, where is a controller mapped to `/hello` normally reached?  
**Answer:** With Tomcat's default auto-deploy and no other context config: `http://localhost:8080/catalog/hello`. Deployment determines the context path.

**Question 5.** Can a Spring Boot 3.5 WAR be deployed to Tomcat 9 if Java 21 is used?  
**Answer:** No. Java 21 does not fix the Jakarta Servlet mismatch: Tomcat 9 uses `javax.servlet`, while Spring Boot 3.x uses `jakarta.servlet`.

**Question 6.** Does an executable WAR running via `java -jar` automatically prove that deploying it to external Tomcat will succeed?  
**Answer:** No. External mode has a different container version, context path, shared libraries, and lifecycle; you must test on the exact target container.

## 16. Official References

- [Spring Boot 3.5 — Traditional Deployment](https://docs.spring.io/spring-boot/3.5/how-to/deployment/traditional-deployment.html): `SpringBootServletInitializer`, `<packaging>war</packaging>`, Maven `provided`, Gradle `providedRuntime`, and executable WARs.
- [Spring Boot 3.5 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): choosing Tomcat/Jetty/Undertow and server configuration.
- [Spring Boot 3.5 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): Servlet model, DispatcherServlet, and JSP limitations.
- [Spring Boot 3.5 — System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html): JDK, Servlet container versions, and deployment support.
- [SpringBootServletInitializer API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/servlet/support/SpringBootServletInitializer.html): bridge between traditional WAR and SpringApplication.
- [Spring Boot 3.5 — Running Your Application](https://docs.spring.io/spring-boot/3.5/reference/using/running-your-application.html): running artifacts and application lifecycle.
- [Apache Tomcat — Which Version?](https://tomcat.apache.org/whichversion.html): mapping Tomcat and Servlet/Jakarta EE versions.

**Key takeaway:** Spring MVC controllers can stay unchanged across deployment modes, yet you must clearly determine **who creates the Servlet container, who manages ports/context paths, and which classpath is used inside the artifact versus the actual runtime**.