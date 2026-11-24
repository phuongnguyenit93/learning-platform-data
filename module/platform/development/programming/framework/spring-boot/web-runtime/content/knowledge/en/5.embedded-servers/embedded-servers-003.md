# Replacing Spring Boot's Default Embedded Server with Jetty or Undertow

> **Scope:** Spring Boot **3.5.0**, **Java 17+**, Spring MVC application running as an executable JAR. This guide walks through switching from **embedded Tomcat** (the default of `spring-boot-starter-web`) to **embedded Jetty** or **embedded Undertow** by excluding the default dependency and adding the starter for the desired server. Maven and Gradle examples rely on Spring Boot's dependency management to select compatible versions.

## 1. How Does Spring Boot Choose an Embedded Server?

When adding the dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

a Spring MVC application usually pulls in the **`spring-boot-starter-tomcat`** starter as a transitive dependency. When the application starts, Spring Boot autoconfiguration detects web server libraries on the classpath and creates the appropriate embedded servlet container. Consequently, running a program with `@SpringBootApplication` and `SpringApplication.run(...)` can open an HTTP port without manually configuring or deploying an external Tomcat.

Distinguish between:

- **`spring-boot-starter-web`:** aggregates dependencies for Spring MVC, HTTP, JSON, and by default a servlet container.
- **`spring-boot-starter-tomcat`:** starter for embedded Tomcat; pulled in by the Spring Web starter by default.
- **`spring-boot-starter-jetty`:** starter for embedded Jetty.
- **`spring-boot-starter-undertow`:** starter for embedded Undertow.
- **Servlet API and Spring MVC:** the application's request-handling layer, which generally stays unchanged when swapping the embedded servlet container.

Server selection is primarily driven by **the classpath after Maven or Gradle resolves all dependencies**, not by a property like `server.type=jetty`. Changing a value in `application.properties` is not enough to swap the container.

### Before and After Model

~~~text
Before:
spring-boot-starter-web
    |
    +-- spring-webmvc, Spring MVC ...
    |
    +-- spring-boot-starter-tomcat
            |
            +-- embedded Tomcat

After (Jetty):
spring-boot-starter-web
    |
    +-- spring-webmvc, Spring MVC ...
    |
    +-- (exclude spring-boot-starter-tomcat)
    |
    +-- add spring-boot-starter-jetty
            |
            +-- embedded Jetty
~~~

To switch servers properly, **both exclude Tomcat from the web starter's dependency path and add the new server's starter**. Then inspect the dependency tree and startup to make sure the classpath contains only the intended container.

## 2. Complete Maven Example: Replacing Tomcat with Jetty

Create a project with the structure:

~~~text
embedded-server-demo/
  pom.xml
  src/
    main/
      java/
        com/
          example/
            serverdemo/
              ServerDemoApplication.java
              HelloController.java
      resources/
        application.properties
    test/
      java/
        com/
          example/
            serverdemo/
              HelloControllerIntegrationTest.java
~~~

### 2.1. `pom.xml`

The file below is a standalone Maven project using **Spring Boot 3.5.0**. The parent manages versions and plugins; **you do not need to pin a separate version** for the Jetty starter.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>embedded-server-demo</artifactId>
    <version>1.0.0</version>
    <name>embedded-server-demo</name>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
            <exclusions>
                <exclusion>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-starter-tomcat</artifactId>
                </exclusion>
            </exclusions>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jetty</artifactId>
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

**Configuration meaning:**

1. The `spring-boot-starter-web` dependency keeps Spring MVC and the required web application pieces.
2. The `<exclusions>` block removes `spring-boot-starter-tomcat` from `spring-boot-starter-web`'s transitive branch.
3. Adding `spring-boot-starter-jetty` brings the necessary Jetty components onto the classpath.
4. Sharing the Spring Boot parent's dependency management keeps Spring Framework, servlet server, and related library versions compatible.
5. `spring-boot-maven-plugin` creates an executable JAR; when run via `java -jar`, embedded Jetty lives inside the application without requiring a separate Jetty installation.

**Note:** an exclusion applies to **a specific dependency path**. If another dependency also brings Tomcat onto the classpath, Tomcat may remain. Therefore, checking the dependency tree is mandatory, especially in multi-module projects or projects with multiple web starters.

### 2.2. Runnable Java Source

`src/main/java/com/example/serverdemo/ServerDemoApplication.java`:

~~~java
package com.example.serverdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ServerDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ServerDemoApplication.class, args);
    }
}
~~~

`src/main/java/com/example/serverdemo/HelloController.java`:

~~~java
package com.example.serverdemo;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public Map<String, String> hello() {
        return Map.of("message", "Hello from Spring MVC");
    }
}
~~~

`src/main/resources/application.properties`:

~~~properties
server.port=9090
server.servlet.context-path=/api
~~~

These are application-level and servlet-context-level settings and continue to take effect after switching Tomcat to Jetty. The controller handles the same `/hello` path, but externally it will be accessed via `/api/hello` due to `server.servlet.context-path=/api`.

### 2.3. Running and Verifying Results

From the directory containing `pom.xml`:

~~~bash
mvn clean package
java -jar target/embedded-server-demo-1.0.0.jar
~~~

Or in a development environment:

~~~bash
mvn spring-boot:run
~~~

In the startup logs, look for information showing that **Jetty** was initialized and the server is listening on port **9090**. The exact log message depends on version and logging configuration; do not verify by demanding an exact word-for-word match on a log line.

Call HTTP:

~~~bash
curl -i http://localhost:9090/api/hello
~~~

When the server starts successfully and nothing else interferes, the JSON body contains:

~~~json
{"message":"Hello from Spring MVC"}
~~~

With Spring Boot 3.x, `@RestController` and `Map` return JSON via message converters on the classpath. Response header order and status line formatting may vary across curl and server versions.

If port `9090` is already in use by another application, Spring Boot may fail at the bind step. Changing the servlet container **does not automatically resolve port conflicts**; change `server.port` or stop the process holding the port.

## 3. Replacing Jetty with Undertow in Maven

To switch from the Jetty version in section 2 to Undertow, keep the Java source, `application.properties`, and web/test dependencies intact. In `pom.xml`, **remove the `spring-boot-starter-jetty` dependency and replace it with**:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-undertow</artifactId>
</dependency>
~~~

At the same time, keep the Tomcat exclusion inside `spring-boot-starter-web`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-tomcat</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

These two XML blocks are **dependency fragments** to place inside the same `<dependencies>` tag of `pom.xml`; keep the remaining elements from the complete Maven example above.

Run again:

~~~bash
mvn clean package
java -jar target/embedded-server-demo-1.0.0.jar
~~~

The `server.port`, `server.servlet.context-path`, and MVC controller configurations continue to work under the same contract. Check startup logs and the dependency tree to confirm the new build actually uses Undertow.

Do not keep both Jetty and Undertow in the same project unless you have a special configuration and clearly understand how the web server factory is created. If you only want **one** embedded server, keep only **one** corresponding container starter on the classpath.

## 4. Gradle Groovy DSL Configuration

If the project uses Gradle, the switch is similar to Maven: exclude Tomcat from the web starter and then add Jetty or Undertow.

Complete `build.gradle` example for Jetty with Spring Boot 3.5.0 and Java 17:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
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
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }

    implementation 'org.springframework.boot:spring-boot-starter-jetty'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Use the same Java source and `application.properties` file from the Maven section. If Gradle Wrapper is already present:

~~~bash
./gradlew clean bootJar
java -jar build/libs/embedded-server-demo-1.0.0.jar
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat clean bootJar
java -jar build/libs/embedded-server-demo-1.0.0.jar
~~~

If switching to Undertow, replace the exact line:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-jetty'
~~~

with:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-undertow'
~~~

**Do not remove the Tomcat exclusion line**.

### Gradle Kotlin DSL

In a project that already has appropriate plugins and repositories, the `dependencies` block in `build.gradle.kts`:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web") {
        exclude(
            group = "org.springframework.boot",
            module = "spring-boot-starter-tomcat"
        )
    }

    implementation("org.springframework.boot:spring-boot-starter-jetty")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

This is a **Kotlin DSL fragment**, not a complete build file. To switch to Undertow, replace `spring-boot-starter-jetty` with `spring-boot-starter-undertow` and keep the same exclusion.

## 5. Verifying the Dependency Tree: Avoid Thinking You Switched While Tomcat Remains

Run the Maven command:

~~~bash
mvn dependency:tree
~~~

Look for relevant dependencies:

- For the **Jetty** build: expect `spring-boot-starter-jetty` and Jetty libraries; **do not expect `spring-boot-starter-tomcat`** or embedded Tomcat pulled in by another branch.
- For the **Undertow** build: expect `spring-boot-starter-undertow` and Undertow libraries; **do not expect `spring-boot-starter-tomcat`**.
- If `spring-boot-starter-tomcat` or `tomcat-embed-*` still appears, inspect the parent branches in the dependency tree to find the exact dependency pulling it in.

With Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

To find why a dependency is present:

~~~bash
./gradlew dependencyInsight --dependency spring-boot-starter-tomcat --configuration runtimeClasspath
~~~

When another dependency pulls Tomcat in, exclude it on that corresponding branch, choose an appropriate alternative dependency, or configure the dependency graph intentionally. Do not assume that placing an exclusion on `spring-boot-starter-web` removes Tomcat from **every** branch of the system.

### Runtime Cross-Check

At runtime, three checks complement one another:

1. **Dependency tree:** verifies build composition.
2. **Startup log:** observes which web server factory actually initializes and which server is opened.
3. **HTTP integration test:** confirms the endpoint is reachable and processes requests properly.

Merely seeing a `200 OK` response does not prove the server changed: Tomcat, Jetty, and Undertow can all serve the same endpoint. Therefore, verify both build and runtime.

## 6. Automated Testing When Swapping Embedded Servers

Changing the server usually does not require changing controllers, but it can expose differences in HTTP parsing, header size, timeouts, compression, WebSocket, or file uploads. Run integration tests with a real server and a dynamic port.

Create `src/test/java/com/example/serverdemo/HelloControllerIntegrationTest.java`:

~~~java
package com.example.serverdemo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class HelloControllerIntegrationTest {

    @LocalServerPort
    private int port;

    @Test
    void helloEndpointWorksWithEmbeddedServer() throws Exception {
        assertTrue(port > 0);

        URI uri = URI.create("http://localhost:" + port + "/api/hello");
        HttpRequest request = HttpRequest.newBuilder(uri)
                .GET()
                .build();

        HttpResponse<String> response = HttpClient.newHttpClient()
                .send(request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertEquals(
                "{\"message\":\"Hello from Spring MVC\"}",
                response.body()
        );
    }
}
~~~

Run:

~~~bash
mvn test
~~~

Or with Gradle:

~~~bash
./gradlew test
~~~

Explanation:

- `@SpringBootTest(webEnvironment = RANDOM_PORT)` starts a **real** web server and picks an available port, reducing port conflicts in CI.
- `@LocalServerPort` receives the HTTP port of the initialized server. This is a test annotation that avoids hardcoding port 9090.
- Spring Boot still reads `server.servlet.context-path=/api`; the test URL must include `/api/hello`.
- Java `HttpClient` sends real HTTP; verifies both status code and body content.
- `@WebMvcTest` and MockMvc are useful for controllers, but **do not replace** a test verifying that the embedded container actually starts.

In this example, the JSON body has **exactly one property**, so the expected string is stable under default JSON settings. If a response has multiple properties, compare JSON content structurally to avoid key-order sensitivity.

After switching servers, re-run regression tests for features the application actually uses: sessions/cookies, redirects, error handling, uploads, streaming/SSE, WebSocket, and TLS if applicable.

## 7. Components That Typically Do Not Change

Switching the embedded server **does not mean switching web frameworks**. Within the same Spring MVC application, the components below typically stay the same:

| Component | After Tomcat → Jetty/Undertow |
|---|---|
| `@RestController`, `@GetMapping`, `@PostMapping` | Keep controllers/mappings |
| `@RequestParam`, `@RequestBody`, `@ModelAttribute` | Still handled by Spring MVC |
| Bean validation and Jackson | Keep usage if dependencies remain intact |
| `server.port` | Still configures the listening port |
| `server.servlet.context-path` | Still defines the context path |
| `@SpringBootTest(RANDOM_PORT)` | Still works with compatible embedded servers |
| `WebServerInitializedEvent` | Still usable to observe when the server has initialized |
| Spring Boot executable JAR | Still runnable via `java -jar` |

What changes is the **servlet container implementation** and certain behaviors underneath Spring MVC: connectors/threading, connection management, HTTP limits, malformed request handling, TLS/HTTP2, WebSocket, session serialization, and performance.

Therefore, you do not need to rewrite controllers just for swapping containers. However, you should not claim that every request behaves identically at the wire protocol level or under non-default configurations.

## 8. Configurations to Review After Swapping Containers

### 8.1. Common vs. Server-Specific Configuration

Some Spring Boot properties apply generally across servers, for example:

~~~properties
server.port=9090
server.servlet.context-path=/api
server.compression.enabled=true
~~~

However, many detailed configuration properties **are tied to a specific server**. For instance, `server.tomcat.*` settings apply only to Tomcat and do not implicitly control Jetty or Undertow. When switching servers, review relevant settings:

- worker thread counts and thread pool configuration;
- connection, keep-alive, and idle timeouts;
- header/request-line limits and request size limits;
- TLS certificates, HTTPS, and HTTP/2;
- compression, connection limits;
- access logs, error pages, and request encoding;
- sessions, servlet filters, and multipart uploads;
- graceful shutdown, health checks, and readiness.

Look up the property list for the **exact Spring Boot version in use**. Do not blindly copy `server.tomcat.threads.max` to a guessed name like `server.jetty.threads.max`: property names, value types, and underlying mechanisms can differ.

### 8.2. Deployment Environment Conditions

If the application runs behind a proxy/load balancer, the internal container port and the public port may differ. Switching the embedded server does not automatically update Docker `EXPOSE`, Kubernetes Service/Ingress, firewalls, or reverse proxies. Verify that:

1. the process opens the right port and bind address;
2. the container image/Deployment publishes the right port;
3. Services and ingress route to the right target;
4. readiness/health endpoints work;
5. telemetry, access logs, and tracing still capture the expected requests.

In production, successful startup is a necessary condition; you must test with real traffic and have rollback capability when updating dependencies.

## 9. Spring MVC Differs from Spring WebFlux

**Do not copy Spring MVC dependencies verbatim for a reactive application.**

- `spring-boot-starter-web` targets **Spring MVC**, defaulting to embedded **Tomcat**.
- `spring-boot-starter-webflux` targets **Spring WebFlux**, defaulting to **Reactor Netty** via `spring-boot-starter-reactor-netty`.

With WebFlux, the server-swap pattern is likewise to exclude the default server starter on the WebFlux branch and choose a **web server compatible with the reactive stack**, though dependencies and custom server configuration can differ. Do not just exclude `spring-boot-starter-tomcat` in a pure WebFlux project: Tomcat is not the default server of `spring-boot-starter-webflux`.

Example identifying the default starter in WebFlux:

~~~text
spring-boot-starter-webflux
    |
    +-- spring-boot-starter-reactor-netty
~~~

If both `spring-boot-starter-web` and `spring-boot-starter-webflux` are added together, Spring Boot usually chooses **Servlet MVC** mode under default auto-detection rules. Do not add both just to change the server. The decision between MVC and WebFlux must be based on the request-processing model, not preference for a server name.

## 10. Transitive Exclusions, Dependency Management, and Version Compatibility

### 10.1. Why Not Add All Server JARs Manually?

Spring Boot starters bundle the required server artifacts and integrations. When writing:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jetty</artifactId>
</dependency>
~~~

and using the Spring Boot BOM/parent, Maven resolves compatible Jetty artifacts automatically. If you manually add multiple Jetty modules with arbitrary versions, the project easily runs into API mismatches, classpath conflicts, or startup failures.

Likewise, Gradle projects should use Spring Boot dependency management/BOM to align versions. Avoid pinning an arbitrary Jetty/Undertow version unless there is a clearly tested compatibility reason.

### 10.2. Multi-Module Projects

Suppose an API module depends on another module that pulls in Tomcat; excluding Tomcat on the `spring-boot-starter-web` branch **might not** remove the old container entirely. Check the actual `runtimeClasspath` of **the module that packages the executable JAR**.

A common mistake is inspecting only the API module's `pom.xml` or `build.gradle` while overlooking dependencies brought in by an infrastructure module. `dependency:tree` or `dependencyInsight` reveals the actual path.

### 10.3. Packaging and Operations

- **Executable JAR:** contains embedded server dependencies and runs directly via `java -jar`. This is the main scenario of this lesson.
- **WAR deployed to an external container:** the external container manages the server lifecycle. Swapping embedded starters does not mean the same thing as changing the operating server. Do not switch `packaging` from JAR to WAR just to change Tomcat → Jetty.
- **Spring Boot version:** examples are verified against Boot 3.5.0's dependency structure. For Boot 4.x or other versions, cross-check supported starter artifacts and Servlet APIs before copying configuration; do not arbitrarily mix version lines.

## 11. Common Errors and How to Fix Them

### 11.1. Added Jetty but Logs Still Mention Tomcat

**Possible cause:** forgot to exclude `spring-boot-starter-tomcat` or another transitive branch still pulls Tomcat in.

**How to check:** `mvn dependency:tree` or `./gradlew dependencies --configuration runtimeClasspath`. Find the exact dependency branch; fix the corresponding exclusion, rebuild from scratch, and check the new startup logs.

### 11.2. Missing `ServletWebServerFactory` / Web Server Does Not Start

If you excluded default Tomcat yet **forgot to add a replacement starter**, Spring Boot may lack an embedded server factory. Add **one** compatible Jetty/Undertow starter and re-verify the classpath.

If the project has a custom `ServletWebServerFactory` bean, it can affect autoconfiguration. Check those custom configurations before concluding that swapping dependencies alone is enough.

### 11.3. `NoSuchMethodError`, `NoClassDefFoundError`, Servlet API Conflicts

Usually related to inconsistent dependency versions or manually added old JARs. Use unified dependency management, remove incompatible server and servlet API modules, and inspect the stack trace at the failure point alongside the actual dependency tree. Do not try to patch it by randomly adding another JAR.

### 11.4. App Starts but Endpoints Return 404

Check `server.servlet.context-path=/api`: an endpoint `@GetMapping("/hello")` is actually at `/api/hello`, not directly at `/hello`. Also check class-level `@RequestMapping` and whether a reverse proxy is adding or stripping prefixes.

### 11.5. HTTP 400/413 Differs from Before or Uploads Fail

The new server may enforce different request limits or old Tomcat properties no longer take effect. Check Jetty/Undertow limits, common multipart configuration, proxies, and upload sizes; test with real requests rather than testing only controllers.

### 11.6. MVC Tests Pass but New Deployment Fails

`@WebMvcTest`/MockMvc tests the MVC layer without opening an embedded HTTP socket. Add at least one `@SpringBootTest(RANDOM_PORT)` test making real HTTP calls, then test specific features such as TLS, WebSocket, cookies, and graceful shutdown if used by the application.

### 11.7. Application Has Multiple Web Server Factories

When multiple embedded server starters or manual factory beans exist, Spring Boot may choose an unintended implementation or fail at startup. Keep only the one desired starter or configure the factory explicitly; do not rely on accidental classpath ordering.

## 12. Safe Migration Checklist

1. Identify the **stack**: Spring MVC or WebFlux; for MVC, note that Tomcat is the default embedded server.
2. Pick **one** target embedded servlet container: Jetty or Undertow; verify compatibility with your Spring Boot/Java version.
3. Exclude `spring-boot-starter-tomcat` from `spring-boot-starter-web`; add `spring-boot-starter-jetty` or `spring-boot-starter-undertow`.
4. Keep dependency management and avoid pinning unsuitable server versions manually.
5. Run `mvn dependency:tree` or inspect Gradle `runtimeClasspath` to eliminate all paths pulling in the old server.
6. Build and start the executable JAR; read startup logs to verify the actual container.
7. Call HTTP endpoints via curl and run integration tests on `RANDOM_PORT`.
8. Review old `server.tomcat.*` properties, HTTP limits, TLS, sessions, uploads, and thread handling for the new server.
9. Verify image/container/service/proxy, health endpoints, and logging.
10. Deploy to a test environment, measure performance under realistic traffic, and only then roll out broadly.

## References

- Spring Boot Reference, [How to Change the HTTP Port and Configure the Embedded Web Server](https://docs.spring.io/spring-boot/how-to/webserver.html).
- Spring Boot Reference, [Build Systems and Starters](https://docs.spring.io/spring-boot/reference/using/build-systems.html).
- Maven Dependency Plugin, [dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html).
- Gradle User Manual, [DependencyInsight](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html).

**Remember:** For a Spring MVC application on Spring Boot 3.x, changing the embedded server is a **dependency graph** change: remove default Tomcat, add Jetty or Undertow, confirm with the dependency tree, and test the real running server. The Spring MVC layer does not need rewriting, but container configuration and behavior must be tested.