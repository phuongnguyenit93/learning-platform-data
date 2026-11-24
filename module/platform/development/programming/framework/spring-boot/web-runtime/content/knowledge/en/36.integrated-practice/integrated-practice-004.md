# Replacing Tomcat with Another Server and Verifying Actual Configuration in Spring Boot

## 1. Practice Goal: Swap the **HTTP Server**, Not the Web Framework by Mistake

Spring Boot MVC normally boots with **embedded Tomcat** because `spring-boot-starter-web` pulls in `spring-boot-starter-tomcat`. When an application needs to evaluate or run on **Jetty** or **Undertow**, you can swap the container by **excluding the Tomcat starter from the dependency graph and adding exactly one replacement server starter**. Controllers, services, Jakarta Servlets, and most Spring MVC configuration stay unchanged.

However, a successful dependency change **does not prove** that the runtime configuration is still valid:

- Is the app actually running Jetty/Undertow, or did a transitive dependency pull Tomcat back in?
- Have previous `server.tomcat.*` properties been migrated to equivalent `server.jetty.*`/`server.undertow.*` settings?
- Do HTTP request header limits, max form size, worker threads, compression, keep-alive, access logs, and encoded-path rules still match security/performance policies?
- Is HTTP/2 (TLS `h2` or cleartext `h2c`) actually negotiated by clients/proxies, rather than merely toggling a property?
- Do servlet filters, handler mappings, error handlers, cookies/sessions, and Actuator still work after the container swap?
- Is the new server included in the **supported platform matrix** of your Spring Boot version?
- Do you have real HTTP tests, load tests, a rollback plan, and before–after metrics?

This lesson belongs to **Integrated Practice** in the **Spring Boot - web-runtime** module. Examples use **Spring Boot 3.5.16, Java 17+, Maven, Spring MVC/Jakarta Servlet**: starting with **Jetty 12.0**, switching to **Undertow 2.3**, and having a path back to Tomcat 10.1. Application Java code remains unchanged across all three steps. It includes unit tests, `@WebMvcTest`/`MockMvc`, `@SpringBootTest(RANDOM_PORT)` with a real HTTP client, an endpoint inspecting the **actual server object**, a non-MVC Servlet test, `curl` checks for routing/compression, and server-specific profiles.

> **Scope:** this lesson covers **swapping the embedded HTTP server** in Spring MVC. It is not a guide for migrating MVC `@RestController`s to Spring WebFlux or deploying a WAR to an external Tomcat. For reactive apps, the default is Reactor Netty; server selection and APIs differ from Servlet MVC.

### Objectives After This Lesson

1. Understand the boundaries: MVC framework, Servlet engine, transport, and proxy.
2. Replace Tomcat with Jetty using Maven/Gradle with proper dependency scoping, without having two containers on the classpath.
3. Switch from Jetty to Undertow **only when supported by your target Spring Boot version**.
4. Inspect the running server via `ServletWebServerApplicationContext` instead of guessing from JAR filenames or HTTP `Server` headers.
5. Distinguish common vs server-specific config, and separate "property read by Environment" from "setting enforced by the server."
6. Properly compare HTTP behaviors: mappings, JSON, statuses, headers, compression, URL/encoding, sessions, filters, Actuator, and HTTP/2.
7. Run tests, measure performance in a controlled manner, and execute evidence-based rollbacks.

## 2. Drawing the System Layers Accurately

A Spring Boot MVC request passes through:

```text
Client / browser / HTTP load generator
            |
            v
Ingress / gateway / TLS termination (if present)
            |
            v
Embedded HTTP Server
    [Tomcat or Jetty or Undertow]
            |
            v
Jakarta ServletContext
  -> Container dispatch / Servlet Filter chain
  -> DispatcherServlet
  -> Spring MVC HandlerMapping/HandlerAdapter
  -> JSON converter, validation, @ControllerAdvice
  -> @RestController, service, repository
            |
            v
HTTP response / headers / bytes
```

**Spring MVC does not turn into WebFlux** when you run Jetty or Undertow as the Servlet container. `@GetMapping`, `@RequestBody`, `@Valid`, and `@RestControllerAdvice` still execute through `DispatcherServlet`. What changes are the HTTP connector, Servlet implementation, thread/executor/buffer pools, access logging, and server-specific defaults.

| Component | Changes on Swap? | Consequence |
| --- | --- | --- |
| Spring MVC `DispatcherServlet` | No, while still using `starter-web` | Preserves MVC tests and contracts |
| Jakarta Servlet API | Same generation supported by Boot | Custom Servlets/Filters still need testing |
| Server implementation | Yes | Thread pools, connectors, limits, access logs |
| Spring `server.port` | Common config | Supported across all servers |
| `server.tomcat.threads.max` | **No longer affects Jetty/Undertow** | Must review equivalent properties |
| `server.compression.*` | Common config API | Verify actual responses |
| SSL/HTTP/2 | Common abstraction, different implementations | Requires wire/protocol testing |
| Actuator & Micrometer | Base meters remain; server-specific ones change | Review dashboards and alerts |
| External reverse proxy | Unchanged by app swap | Though upstream protocol/redirects may differ |
| Application business logic | Should remain untouched | Unit tests help isolate regressions |

An app can *return HTTP 200 correctly* yet silently lose access logs or alter thread limits with no helpful warning; that is why this lesson checks **dependency graph + runtime identity + effective configuration + HTTP evidence**.

## 3. Version Matrix: Do Not Use Boot 3 Guides to Configure Boot 4

### 3.1. Spring Boot 3.5.16

Per [Spring Boot 3.5 system requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html):

| Embedded Servlet Server | Supported Version in Boot 3.5 | Servlet Spec |
| --- | --- | --- |
| Tomcat | **10.1** (minimum patch per docs) | 6.0 |
| Jetty | **12.0** | 6.0 |
| Undertow | **2.3** | 6.0 |

Boot 3.5.16 requires **Java 17+** and Spring Framework 6.2.19+ as its baseline. External WAR deployments require a Servlet 5.0+ compatible container. This lab uses an **embedded** server; external WARs are discussed separately in section 20.

Do not pin an arbitrary Jetty/Tomcat/Undertow version outside the Spring Boot BOM merely because a patch looks newer. Verify compatible versions, APIs, security advisories, and companion dependencies. Stick to your target Boot line's parent/BOM.

### 3.2. Spring Boot 4.x No Longer Supports an Undertow Starter

The Spring Boot 4.0 migration guide confirms a **Servlet 6.1 baseline**, support for **Tomcat 11 / Jetty 12.1**, and **removal of Undertow support** because it did not meet the baseline at release time. Therefore this lesson **uses Boot 3.5 to practice both Jetty and Undertow**, rather than demonstrating Undertow on Boot 4.

| Need | Approach |
| --- | --- |
| Boot 3.5 + Jetty | Jetty 12.0 starter |
| Boot 3.5 + Undertow | Undertow 2.3 starter |
| Boot 3.5 + Tomcat | Default Tomcat 10.1 starter |
| Boot 4 + Jetty | Read Boot 4 guide and use Jetty 12.1 |
| Boot 4 + Tomcat | Read Boot 4 guide and use Tomcat 11 |
| Boot 4 + Undertow | **Do not assume a Boot-supported Undertow starter exists** |

**Version note:** `spring-boot-starter-web` is the Spring MVC starter in Boot **3.5**. Boot 4 introduces modular starter naming (`spring-boot-starter-webmvc`) and test/auto-configuration package changes; do not just bump `<version>` to 4.x and expect every example to run verbatim.

## 4. Maven Steps: Tomcat → Jetty

In Spring Boot 3.5 Maven, `spring-boot-starter-web` pulls in `spring-boot-starter-tomcat` transitively. Add an **exclusion** to that dependency:

```xml
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
```

This is a POM snippet (the **complete** POM is in section 10). Keep `spring-boot-starter-web` because it provides Spring MVC, Jackson, and integrations. **Do not remove `starter-web` entirely** just to replace Tomcat.

Maven resolves Jetty versions through Spring Boot dependency management. The build should include **one embedded server choice**. If another dependency also pulls in the Tomcat starter or a servlet engine, inspect the dependency tree and exclude it at the right source—do not guess from `pom.xml` alone.

### Inspecting the Dependency Graph

```bash
mvn clean package
mvn dependency:tree
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-tomcat
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-jetty
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-undertow
```

Expected state for Jetty:

- The Jetty starter appears in the runtime tree.
- The Tomcat starter **no longer** appears in the application dependency graph after exclusion.
- The Undertow starter is absent.
- Spring MVC and Jakarta Servlet APIs align with Boot 3.5.

Keep in mind that **test-only** Tomcat dependencies or Boot plugin packaging nuances may exist; inspect **runtime scope** and `jar tf` on the artifact rather than grepping for `tomcat` anywhere and assuming the app runs on Tomcat.

## 5. Maven Steps: Jetty → Undertow

In Spring Boot 3.5, starting from the Jetty setup with Tomcat excluded, swap **one starter**:

```xml
<!-- Remove the spring-boot-starter-jetty dependency from the POM. -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-undertow</artifactId>
</dependency>
```

Keep `spring-boot-starter-web` with the Tomcat exclusion. Never declare Jetty and Undertow simultaneously expecting Boot to "pick one" by dependency order; having both causes bean ambiguity or fragile auto-configuration condition behavior.

Run:

```bash
mvn clean test
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-undertow
mvn clean package
```

After swapping, **remove or disable Jetty-specific properties** and enable reviewed Undertow properties. `server.jetty.threads.max` can still appear in `Environment` without **configuring Undertow worker threads**. That "green startup with altered performance" trap is very common.

### Rolling Back to Tomcat

Restore `spring-boot-starter-web` **without the Tomcat exclusion**, and remove the Jetty/Undertow starter. Then build, test, and verify the runtime server name. Never just add the Tomcat starter into a POM that still has Jetty or Undertow, as that creates two server choices.

## 6. Gradle Equivalent: Remember to Exclude Transitive Tomcat

Groovy DSL with Spring Boot 3.5:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }
    implementation 'org.springframework.boot:spring-boot-starter-jetty'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

This is a **build.gradle** alternative to the Maven POM; do not use both build tools at once. To try Undertow, change `spring-boot-starter-jetty` to `spring-boot-starter-undertow` on Boot **3.5** while keeping the Tomcat exclusion.

```bash
./gradlew clean test bootJar
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-boot-starter-tomcat
./gradlew dependencyInsight --dependency spring-boot-starter-jetty
```

If the project uses custom BOM plugins or other dependencies that pull in Tomcat, inspect the resolved Gradle configurations; a single local exclusion will not stop every transitive path. Never use `compileOnly` to strip the servlet engine from an executable JAR.

## 7. Layering Configuration: Common, Server-Specific, and Effective Environment

### 7.1. Common Boot 3.5 Properties

| Key | Meaning | Works with Jetty/Undertow/Tomcat? |
| --- | --- | --- |
| `server.port` | Main HTTP listener port | Yes |
| `server.address` | Bind address | Yes |
| `server.servlet.context-path` | Embedded Servlet context path | Yes |
| `server.compression.enabled` | Enable/disable response compression | Yes |
| `server.compression.min-response-size` | Response length threshold for compression | Yes, verify implementation behavior |
| `server.compression.mime-types` | Content types eligible for compression | Yes |
| `server.max-http-request-header-size` | Request header limit | Yes, calculation varies by server |
| `server.http2.enabled` | Request HTTP/2 if supported by runtime | Yes, needs deps/TLS/protocol test |
| `server.ssl.*` | SSL configuration | Common abstraction, details may differ |
| `server.forward-headers-strategy` | How forwarded headers are handled | Yes, requires defining trusted proxy |
| `server.shutdown` | Shutdown mode | Yes, verify graceful behavior |
| `spring.lifecycle.timeout-per-shutdown-phase` | Lifecycle phase timeout | Yes |

Example common configuration for the lab:

```properties
server.port=8080
server.compression.enabled=true
server.compression.min-response-size=1KB
server.compression.mime-types=text/plain,application/json
server.max-http-request-header-size=16KB
server.http2.enabled=false
server.forward-headers-strategy=none
management.endpoints.web.exposure.include=health,info
management.endpoint.health.show-details=never
```

**This is declared configuration**, not proof that 16KB is enforced identically across containers. Per Boot 3.5 property docs, request-header size has server-specific interpretations; for instance, Tomcat counts the request line plus headers together, while other runtimes count differently.

### 7.2. Server-Specific Properties Do NOT Auto-Convert

| Tomcat | Jetty | Undertow | Notes |
| --- | --- | --- | --- |
| `server.tomcat.threads.max` | `server.jetty.threads.max` | `server.undertow.threads.worker` | **Not** 1:1 equivalents in thread model |
| `server.tomcat.threads.min-spare` | `server.jetty.threads.min` | No exact one-to-one minimum | Different models |
| `server.tomcat.max-connections` | `server.jetty.max-connections` | See Undertow socket/server options | Different semantics |
| `server.tomcat.accesslog.enabled` | `server.jetty.accesslog.enabled` | `server.undertow.accesslog.enabled` | Different paths/pattern syntax |
| `server.tomcat.max-http-response-header-size` | `server.jetty.max-http-response-header-size` | Do not guess an equivalent key | Test server-specific limits |
| `server.tomcat.connection-timeout` | `server.jetty.connection-idle-timeout` | `server.undertow.no-request-timeout` | Do not substitute keys mechanically |
| `server.tomcat.relaxed-path-chars` | Check Jetty URI compliance | `server.undertow.decode-slash` and options | Path canonicalization/security risks |

**Never** take `server.tomcat.threads.max=200`, set `server.undertow.threads.worker=200`, and call that "preserving capacity." Undertow separates **I/O threads** from **worker threads** for blocking tasks; Jetty uses a `QueuedThreadPool` with selectors and acceptors. Benchmark under the same workload to draw meaningful conclusions.

### 7.3. Profile-Based Jetty Configuration

Example `application-jetty.properties`:

```properties
# Activate only when actually running Jetty in the lab.
server.jetty.threads.min=8
server.jetty.threads.max=64
server.jetty.accesslog.enabled=true
server.jetty.accesslog.filename=./logs/jetty-access.log
```

These are **experimental lab values**, not production sizing. Ensure the logs directory is writable and log retention/rotation is configured. If running Undertow with the `jetty` profile accidentally active, these keys are still read into `Environment` yet have zero effect on the running server.

### 7.4. Profile-Based Undertow Configuration

Example `application-undertow.properties`:

```properties
# Activate only when actually running Undertow (Boot 3.5).
server.undertow.threads.io=2
server.undertow.threads.worker=32
server.undertow.accesslog.enabled=true
server.undertow.accesslog.dir=./logs/undertow
server.undertow.accesslog.pattern=%t %a %r %s (%D milliseconds)
server.undertow.options.server.record-request-start-time=true
```

Per Boot docs, for `%D` to record response time in Undertow access logs, enable `server.undertow.options.server.record-request-start-time=true`. Do not translate Tomcat `%D` pattern units blindly: Tomcat may use microseconds/milliseconds depending on token, while Boot's Undertow docs show milliseconds. Check the engine docs and verify real log output.

### 7.5. Profiles and Runtime Environment

Profiles separate **engine-specific configuration**, but **do not pick the engine**. The engine is selected by the classpath/starters and auto-configuration, while `spring.profiles.active` activates conditional config sources and beans.

| Built Artifact | Profile | Outcome |
| --- | --- | --- |
| Jetty starter | `lab,jetty` | Jetty + Jetty settings |
| Undertow starter | `lab,undertow` | Undertow + Undertow settings |
| Jetty starter | `lab,undertow` | **Still Jetty**; Undertow properties do not turn it into Undertow |
| Undertow starter | `lab,jetty` | **Still Undertow**; Jetty properties do not apply |
| Tomcat default | `lab` | Tomcat, if no alternative server starter is present |

To avoid "right profile name, wrong engine," this lesson tests the **runtime server class** alongside the dependency graph.

## 8. How to Verify the Real Server Instead of Relying on Weak Signals

Do not rely solely on these weak signals:

- A filename like `jetty-app.jar`: artifact names do not determine runtime behavior.
- A Spring Boot `Started ...` log line: does not prove which connector serves requests.
- `Server: Jetty(...)` HTTP header: servers may hide/modify it or a proxy may overwrite it.
- Seeing the Jetty starter in `pom.xml`: transitive Tomcat or another starter may still exist.
- Seeing `server.jetty.threads.max=64` in `Environment`: proves **configured**, not that Jetty is running.

A stronger check in an embedded servlet app is injecting `ServletWebServerApplicationContext` and inspecting the live **`WebServer` object**:

```java
String implementation =
        servletWebServerApplicationContext.getWebServer()
                .getClass().getSimpleName();
```

In Spring Boot 3.5 embedded MVC, the implementations are typically:

- `TomcatWebServer`
- `JettyWebServer`
- `UndertowWebServer`

The class name is a useful diagnostic for the **demo version**, not a public production API contract. Never make production clients depend on that string. This lesson guards the runtime endpoint with `@Profile("lab")` so ports, server implementation, and configuration are not exposed in production.

### Three Levels of Configuration Verification

1. **Declared:** what keys are actually in `application*.properties`, env vars, or Helm/CI configs?
2. **Bound/effective:** what values are resolved by Spring `Environment`/`@ConfigurationProperties` and active profiles?
3. **Applied/observed:** what do the Jetty/Undertow objects, HTTP responses, access logs, thread metrics, and performance tests show?

For example, seeing `server.max-http-request-header-size=16KB` in `Environment` only proves the key bound in the **Spring property source**. To verify how the container enforces the request limit, send controlled synthetic request headers over real TCP, observe the status, and cross-check server docs. Never flood headers against a production host.

## 9. Pre-Swap Checklist: Baseline to Capture

To compare Tomcat, Jetty, and Undertow cleanly, capture a baseline first:

- Boot version, Java version, build tool, and dependency tree.
- Actual server object, Servlet version, HTTP port/bind address/context path.
- Endpoint, method, status, body, and header contracts.
- Multipart uploads, sessions/cookies, CORS/CSRF/security filters.
- Request header limits/sizes, form parameters, URL decoding, encoded slashes.
- Response compression headers/bytes under `Accept-Encoding`.
- HTTP/1.1 vs HTTP/2, TLS/mTLS/ALPN if enabled.
- Access logs: directory, pattern, rotation, request IDs.
- Active profiles and **non-secret** effective configuration.
- Actuator health/metrics, JVM/thread/connection measurements.
- Load test with identical workload, dataset, duration, p95/p99, and error counts.
- Rollback artifact, deployment flags, and expected startup time.

If a different server default alters statuses or limits, **do not rush to "fix" it by relaxing security policies**. First confirm the desired behavior per application contract, then configure equivalent settings (if supported) and add a regression test.

## 10. Runnable Java 17+, Maven, Spring Boot 3.5.16 Practice Project

We build a small app whose **code stays unchanged** across Jetty, Undertow, and Tomcat. Endpoints:

- `GET /api/products/pen`: product JSON with header `X-Lab-Contract: v1`.
- `POST /api/quotes`: accepts `@Valid` JSON and computes total price.
- `GET /api/blob?size=8192`: compressible repeating text for testing response compression.
- `GET /raw/ping`: standalone Servlet outside Spring MVC, verifying container dispatch.
- `GET /lab/server`: diagnostic endpoint active **only when profile `lab` is enabled**, returning server class, port/context, and a few **non-secret** properties.
- `GET /actuator/health`: health endpoint via Spring Boot Actuator.
- `X-Lab-Filter: active`: added to HTTP responses by a Servlet filter.

### 10.1. Project Structure

```text
server-swap-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/serverswap/
    │   │   ├── ServerSwapApplication.java
    │   │   ├── CatalogService.java
    │   │   ├── CatalogController.java
    │   │   ├── ApiErrorHandler.java
    │   │   ├── ResponseMarkerFilter.java
    │   │   ├── RawServletConfiguration.java
    │   │   └── RuntimeDiagnosticsController.java
    │   └── resources/
    │       ├── application.properties
    │       ├── application-jetty.properties
    │       └── application-undertow.properties
    └── test/
        └── java/com/example/serverswap/
            ├── CatalogServiceTest.java
            ├── CatalogControllerMvcTest.java
            └── LiveHttpServerTest.java
```

Each Java file has one `public class` matching its filename. Supporting DTOs, exceptions, or Servlets in the same package can be nested classes/records or package-private; no hidden extra files are needed.

### 10.2. Complete `pom.xml` — Jetty as the Lesson's Default Engine

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

    <groupId>com.example</groupId>
    <artifactId>server-swap-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
            <artifactId>spring-boot-starter-validation</artifactId>
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

Purpose of each dependency:

- `starter-web` keeps Spring MVC/JSON while explicitly excluding transitive Tomcat.
- `starter-jetty` provides embedded Jetty compatible with Boot 3.5.
- `starter-validation` enables Jakarta Bean Validation.
- `starter-actuator` provides health endpoints.
- `starter-test` provides JUnit, Mockito, Spring Test/MockMvc, and `TestRestTemplate`.
- Boot Maven plugin builds the executable JAR.

Do not add WebFlux just to swap Tomcat for Jetty; that is a **different problem**.

### 10.3. `ServerSwapApplication.java`

```java
package com.example.serverswap;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ServerSwapApplication {

    public static void main(String[] args) {
        SpringApplication.run(ServerSwapApplication.class, args);
    }
}
```

`@SpringBootApplication` sits in root package `com.example.serverswap` so controllers, services, and configurations are scanned.

### 10.4. `CatalogService.java`

```java
package com.example.serverswap;

import org.springframework.stereotype.Service;

@Service
public class CatalogService {

    public record Product(String sku, long unitPriceVnd) {
    }

    public record Quote(
            String sku,
            int quantity,
            long unitPriceVnd,
            long totalVnd) {
    }

    public Product product(String sku) {
        return switch (sku) {
            case "pen" -> new Product("pen", 12_000L);
            case "book" -> new Product("book", 35_000L);
            default -> throw new ProductNotFoundException(sku);
        };
    }

    public Quote quote(String sku, int quantity) {
        if (quantity < 1 || quantity > 100) {
            throw new IllegalArgumentException(
                    "quantity must be between 1 and 100");
        }
        Product found = product(sku);
        long total = Math.multiplyExact(
                found.unitPriceVnd(), (long) quantity);
        return new Quote(
                found.sku(),
                quantity,
                found.unitPriceVnd(),
                total);
    }
}

class ProductNotFoundException extends RuntimeException {
    ProductNotFoundException(String sku) {
        super("Unknown SKU: " + sku);
    }
}
```

`Math.multiplyExact` guards against silent overflow. The service has zero dependency on Jetty, Tomcat, or Undertow. When only the server swaps, service unit tests should remain untouched and green.

### 10.5. `CatalogController.java`

```java
package com.example.serverswap;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class CatalogController {

    public record QuoteRequest(
            @NotBlank String sku,
            @Min(1) @Max(100) int quantity) {
    }

    private final CatalogService catalog;

    public CatalogController(CatalogService catalog) {
        this.catalog = catalog;
    }

    @GetMapping(
            value = "/products/{sku}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<CatalogService.Product> product(
            @PathVariable String sku) {
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .header("X-Lab-Contract", "v1")
                .body(catalog.product(sku));
    }

    @PostMapping(
            value = "/quotes",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public CatalogService.Quote quote(
            @Valid @RequestBody QuoteRequest body) {
        return catalog.quote(body.sku(), body.quantity());
    }

    @GetMapping(
            value = "/blob",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> blob(
            @RequestParam(defaultValue = "8192") int size) {
        int n = Math.min(Math.max(size, 0), 32_768);
        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .cacheControl(CacheControl.noStore())
                .body("x".repeat(n));
    }
}
```

`GET /api/blob?size=8192` returns **8192 `x` characters**, exceeding `server.compression.min-response-size=1KB`. Inspect HTTP `Content-Encoding` using a gzip-capable client; never equate `enabled=true` with every response being compressed (it depends on content type, `Accept-Encoding`, response size, and server).

### 10.6. `ApiErrorHandler.java`

```java
package com.example.serverswap;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrorHandler {

    @ExceptionHandler(ProductNotFoundException.class)
    public ResponseEntity<Map<String, String>> notFound(
            ProductNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(Map.of("code", "PRODUCT_NOT_FOUND"));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, String>> validation(
            MethodArgumentNotValidException ex) {
        return ResponseEntity.badRequest()
                .body(Map.of("code", "INVALID_REQUEST"));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<Map<String, String>> unreadable(
            HttpMessageNotReadableException ex) {
        return ResponseEntity.badRequest()
                .body(Map.of("code", "INVALID_JSON"));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> illegal(
            IllegalArgumentException ex) {
        return ResponseEntity.badRequest()
                .body(Map.of("code", "INVALID_REQUEST"));
    }
}
```

A well-defined public error schema is far cleaner than relying on each container's default error HTML/JSON. Unknown SKUs return 404 and validation failures return 400; tests protect this contract across swaps.

### 10.7. `ResponseMarkerFilter.java`

```java
package com.example.serverswap;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class ResponseMarkerFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {
        response.setHeader("X-Lab-Filter", "active");
        chain.doFilter(request, response);
    }
}
```

This Filter bean is registered by Boot in the embedded Servlet container. Live tests on Jetty and Undertow verify `X-Lab-Filter` is present; MockMvc can execute configured filters too, yet is **not enough to prove container registration over TCP**.

### 10.8. `RawServletConfiguration.java`

```java
package com.example.serverswap;

import java.io.IOException;

import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.web.servlet.ServletRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class RawServletConfiguration {

    @Bean
    ServletRegistrationBean<RawPingServlet> rawServlet() {
        ServletRegistrationBean<RawPingServlet> bean =
                new ServletRegistrationBean<>(
                        new RawPingServlet(), "/raw/*");
        bean.setName("rawPingServlet");
        return bean;
    }
}

class RawPingServlet extends HttpServlet {

    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response)
            throws IOException {
        if (!"/ping".equals(request.getPathInfo())) {
            response.sendError(HttpServletResponse.SC_NOT_FOUND);
            return;
        }
        response.setCharacterEncoding("UTF-8");
        response.setContentType("text/plain");
        response.getWriter().write("raw-servlet-ok\n");
    }
}
```

`/raw/*` belongs to **Servlet container dispatch**, not `@GetMapping`. If after swapping servers `/api/products/pen` passes while `/raw/ping` returns 404, the issue likely involves Servlet registration, URL mapping, or container incompatibility—not business logic.

### 10.9. `RuntimeDiagnosticsController.java` — Verifying Server Class and Config

```java
package com.example.serverswap;

import java.util.Map;

import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.core.env.Environment;
import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Profile("lab")
@RestController
@RequestMapping("/lab")
public class RuntimeDiagnosticsController {

    private final ServletWebServerApplicationContext context;
    private final Environment environment;

    public RuntimeDiagnosticsController(
            ServletWebServerApplicationContext context,
            Environment environment) {
        this.context = context;
        this.environment = environment;
    }

    @GetMapping("/server")
    public Map<String, Object> server() {
        return Map.of(
                "server",
                context.getWebServer().getClass().getSimpleName(),
                "port",
                context.getWebServer().getPort(),
                "contextPath",
                context.getServletContext().getContextPath(),
                "compressionProperty",
                environment.getProperty(
                        "server.compression.enabled", "unset"),
                "requestHeaderLimitProperty",
                environment.getProperty(
                        "server.max-http-request-header-size", "unset"),
                "http2Property",
                environment.getProperty(
                        "server.http2.enabled", "unset"));
    }
}
```

`@Profile("lab")` ensures the endpoint is **not created** when the `lab` profile is off. This is a diagnostic helper for the learning project; never expose it publicly in production. `server` is the running `WebServer` class; `compressionProperty`/`requestHeaderLimitProperty`/`http2Property` only reflect **configuration values visible to Spring**, not proof that the web engine applies identical semantics.

In `RANDOM_PORT` tests, `port` is the real bound port rather than `server.port=8080` from main config. Use this to cross-check instead of guessing the server from startup logs or HTTP headers.

### 10.10. `application.properties`

```properties
spring.application.name=server-swap-lab
server.port=8080

server.compression.enabled=true
server.compression.min-response-size=1KB
server.compression.mime-types=text/plain,application/json

server.max-http-request-header-size=16KB
server.http2.enabled=false
server.forward-headers-strategy=none

management.endpoints.web.exposure.include=health,info
management.endpoint.health.show-details=never
```

Set `server.forward-headers-strategy=none` in the direct-HTTP lab so **client-supplied `X-Forwarded-*` headers are ignored**. In production behind a trusted proxy, configure `native`/`framework` deliberately and test paths/redirects—never blindly trust forwarded hosts from the Internet.

### 10.11. `application-jetty.properties`

```properties
server.jetty.threads.min=8
server.jetty.threads.max=64
server.jetty.accesslog.enabled=true
server.jetty.accesslog.filename=./logs/jetty-access.log
```

### 10.12. `application-undertow.properties`

```properties
server.undertow.threads.io=2
server.undertow.threads.worker=32
server.undertow.accesslog.enabled=true
server.undertow.accesslog.dir=./logs/undertow
server.undertow.accesslog.pattern=%t %a %r %s (%D milliseconds)
server.undertow.options.server.record-request-start-time=true
```

Thread counts here are **lab settings**; measure and size them for CPU, blocking workload, concurrency, and platform limits. Both Jetty and Undertow access logs need writable paths, permissions, and rotation; avoid logging query tokens or PII into raw access logs in production.

## 11. Unit Test — Business Logic Independent of HTTP Server

File `src/test/java/com/example/serverswap/CatalogServiceTest.java`:

```java
package com.example.serverswap;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class CatalogServiceTest {

    private final CatalogService service = new CatalogService();

    @Test
    void correctQuote() {
        assertEquals(
                new CatalogService.Quote(
                        "pen", 2, 12000L, 24000L),
                service.quote("pen", 2));
    }

    @Test
    void invalidQuantity() {
        assertThrows(IllegalArgumentException.class,
                () -> service.quote("pen", 0));
    }

    @Test
    void unknownSku() {
        assertThrows(ProductNotFoundException.class,
                () -> service.product("not-found"));
    }
}
```

These three tests require no Spring context, Servlet API, Jetty, Undertow, or Tomcat. If they fail after a swap, you likely changed business code or dependencies outside scope and should investigate separately.

## 12. MockMvc Test — Verifying the MVC Contract, Not the HTTP Server

File `src/test/java/com/example/serverswap/CatalogControllerMvcTest.java`:

```java
package com.example.serverswap;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(CatalogController.class)
class CatalogControllerMvcTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    CatalogService catalog;

    @Test
    void itemMappingAndSerialization() throws Exception {
        given(catalog.product("pen"))
                .willReturn(
                        new CatalogService.Product("pen", 12000L));

        mvc.perform(get("/api/products/pen")
                .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "X-Lab-Contract", "v1"))
                .andExpect(jsonPath("$.sku").value("pen"))
                .andExpect(jsonPath("$.unitPriceVnd")
                        .value(12000));
    }

    @Test
    void invalidRequestIs400() throws Exception {
        mvc.perform(post("/api/quotes")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"sku":"pen","quantity":0}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_REQUEST"));
    }

    @Test
    void unknownMethodIs405() throws Exception {
        mvc.perform(post("/api/products/pen"))
                .andExpect(status().isMethodNotAllowed());
    }
}
```

`@MockitoBean` comes from Spring Framework 6.2 in package `org.springframework.test.context.bean.override.mockito`. This test uses mock MVC servlet objects, **not a live Jetty/Undertow socket**. It verifies routes, JSON, `@Valid`, and error responses; the next test layer verifies the actual server swap.

## 13. Live HTTP Test — Verifying the Right Server Implementation

File `src/test/java/com/example/serverswap/LiveHttpServerTest.java`:

```java
package com.example.serverswap;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("lab")
class LiveHttpServerTest {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate http;

    private String url(String path) {
        return "http://127.0.0.1:" + port + path;
    }

    @Test
    void selectedServerIsReallyRunning() {
        assertTrue(port > 0);
        ResponseEntity<Map> response =
                http.getForEntity(url("/lab/server"), Map.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());

        String expected = System.getenv().getOrDefault(
                "EXPECTED_SERVER", "JettyWebServer");
        assertEquals(expected, response.getBody().get("server"));

        assertEquals(port,
                ((Number) response.getBody().get("port"))
                        .intValue());
        assertEquals("true",
                response.getBody().get("compressionProperty"));
        assertEquals("16KB",
                response.getBody().get(
                        "requestHeaderLimitProperty"));
    }

    @Test
    void catalogContractWorksThroughTcp() {
        ResponseEntity<Map> response =
                http.getForEntity(
                        url("/api/products/pen"), Map.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("pen", response.getBody().get("sku"));
        assertEquals(12000,
                ((Number) response.getBody()
                        .get("unitPriceVnd")).intValue());
        assertEquals("v1",
                response.getHeaders()
                        .getFirst("X-Lab-Contract"));
        assertEquals("active",
                response.getHeaders()
                        .getFirst("X-Lab-Filter"));
    }

    @Test
    void jsonValidationWorksThroughTcp() {
        ResponseEntity<Map> response =
                http.postForEntity(
                        url("/api/quotes"),
                        new CatalogController.QuoteRequest("pen", 0),
                        Map.class);

        assertEquals(HttpStatus.BAD_REQUEST,
                response.getStatusCode());
        assertEquals("INVALID_REQUEST",
                response.getBody().get("code"));
    }

    @Test
    void servletRegistrationIsNotJustMvc() {
        ResponseEntity<String> response =
                http.getForEntity(
                        url("/raw/ping"), String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("raw-servlet-ok\n", response.getBody());
        assertEquals("active",
                response.getHeaders()
                        .getFirst("X-Lab-Filter"));
    }

    @Test
    void actuatorHealthWorks() {
        ResponseEntity<Map> response =
                http.getForEntity(
                        url("/actuator/health"), Map.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("UP", response.getBody().get("status"));
    }

    @Test
    void largePayloadIsReturned() {
        ResponseEntity<String> response =
                http.getForEntity(
                        url("/api/blob?size=8192"), String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals(8192, response.getBody().length());
    }
}
```

**Test purpose:** `ServletWebServerApplicationContext.getWebServer()` is exposed over HTTP and checked against the expected implementation. With the **Jetty POM**, the default expected class is `JettyWebServer`. When switching to Undertow, set `EXPECTED_SERVER=UndertowWebServer` before running tests; when rolling back to Tomcat, use `TomcatWebServer`. This is an **explicit assertion**, never "pass regardless of which server started."

Here `@ActiveProfiles("lab")` enables the diagnostic controller in tests. `RANDOM_PORT` boots the real embedded server on an OS-assigned port instead of fixed 8080. These tests do **not** yet verify compression on the wire; section 17 gives dedicated `curl` commands. `TestRestTemplate` may transparently decompress responses depending on the underlying HTTP client, so `largePayloadIsReturned` only verifies no payload bytes were truncated.

### Boundaries of Live HTTP Tests

| Test | Verifies | Does Not Verify |
| --- | --- | --- |
| Unit | Business rules | HTTP stack |
| `@WebMvcTest` + MockMvc | MVC mappings/JSON/validation | Jetty/Undertow listener |
| `@SpringBootTest(RANDOM_PORT)` | Real embedded server, TCP, Servlet dispatch/filter | External proxy/TLS, browser |
| `curl` with `Accept-Encoding` | Response compression on the wire if active | p95 under load |
| Deployment smoke | Container image, networking, ingress | All scenarios |
| Load/soak | Throughput/latency/resources for workload | Every security edge case |

## 14. Step 1: Build and Run Real Jetty

Inside `server-swap-lab`:

```bash
java -version
mvn -version
mvn clean test
mvn clean package
```

While the POM selects Jetty, the live test expects `JettyWebServer`. Built JAR:

```text
target/server-swap-lab-1.0.0.jar
```

Create the access log directory if running the `jetty` profile:

```bash
mkdir -p logs
```

Run:

```bash
java -jar target/server-swap-lab-1.0.0.jar \
  --spring.profiles.active=lab,jetty
```

In another terminal:

```bash
curl -sS http://127.0.0.1:8080/lab/server
curl -i http://127.0.0.1:8080/api/products/pen
curl -i http://127.0.0.1:8080/raw/ping
curl -i http://127.0.0.1:8080/actuator/health
```

**Sample output derived from code/config**, not an actual run in the reader's environment:

`GET /lab/server` (JSON key order not guaranteed):

```json
{
  "server": "JettyWebServer",
  "port": 8080,
  "contextPath": "",
  "compressionProperty": "true",
  "requestHeaderLimitProperty": "16KB",
  "http2Property": "false"
}
```

`GET /api/products/pen`:

```json
{"sku":"pen","unitPriceVnd":12000}
```

The response includes `X-Lab-Contract: v1` and `X-Lab-Filter: active`. `GET /raw/ping` returns text body:

```text
raw-servlet-ok
```

There is a trailing newline after `raw-servlet-ok` from `write("raw-servlet-ok\n")`. `/actuator/health` returns `{"status":"UP"}` when health contributors are UP.

**If `/lab/server` does not return `JettyWebServer`, stop and inspect the dependency tree/classpath before claiming the swap succeeded.**

### Checking the Jetty Access Log

When `application-jetty.properties` is active and the path is writable, Jetty writes access logs to the configured file. Send a few requests and inspect `./logs/jetty-access.log`. No log? Check active profiles, folder permissions, startup warnings, log filename, and property version. Access logs **differ** from application logs (`logging.level.*`); seeing startup logs does not prove access logging works.

## 15. Step 2: Switch to Undertow Properly

Update the POM per section 5: **remove the Jetty starter, add the Undertow starter**, keeping Tomcat excluded. Do not modify Java sources. Check:

```bash
mvn clean package
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-undertow
```

To run tests with the expected server on Bash/macOS/Linux:

```bash
EXPECTED_SERVER=UndertowWebServer mvn clean test
```

PowerShell:

```powershell
$env:EXPECTED_SERVER = 'UndertowWebServer'
mvn clean test
Remove-Item Env:EXPECTED_SERVER
```

**Note:** tests read the environment variable directly inside the test JVM. In CI, set it on the test process; do not set it on the app process and forget the test runner.

Create the log folder and launch Undertow:

```bash
mkdir -p logs/undertow
java -jar target/server-swap-lab-1.0.0.jar \
  --spring.profiles.active=lab,undertow
```

Note with Maven: if you run `mvn clean package` **before** setting `EXPECTED_SERVER`, Maven runs tests expecting Jetty by default and fails. Proper sequence:

```bash
EXPECTED_SERVER=UndertowWebServer mvn clean package
```

PowerShell:

```powershell
$env:EXPECTED_SERVER = 'UndertowWebServer'
mvn clean package
Remove-Item Env:EXPECTED_SERVER
```

Expect `/lab/server` to return `"server":"UndertowWebServer"` while all HTTP contracts match Jetty:

- `/api/products/pen`: 200, product JSON, `X-Lab-Contract: v1`.
- `/api/quotes` valid: 200, quantity/total JSON.
- `/api/quotes` invalid: 400 with stable error code.
- `/raw/ping`: 200 from the non-MVC Servlet.
- `/actuator/health`: UP when healthy.
- `X-Lab-Filter: active` on HTTP responses.

If the app only starts when both Jetty and Undertow are present, that indicates a broken POM/config—not a solution. The goal is **one clearly verified server choice**.

### Inspecting Undertow Access Logs

Per the Undertow profile, logs write under `./logs/undertow`. Pattern `%D` includes timing when `record-request-start-time` is enabled. Verify the generated file after requests and check units rather than comparing numbers directly against Tomcat or Jetty without normalizing units.

## 16. Step 3: Roll Back to Tomcat for a Baseline

To A/B compare all three engines, restore default `starter-web`:

- Remove the Tomcat `<exclusions>` from `spring-boot-starter-web`.
- Remove `spring-boot-starter-jetty`/`spring-boot-starter-undertow`.
- If Tomcat-specific settings are needed, configure **`server.tomcat.*`** rather than leaving Jetty/Undertow keys behind.

Run:

```bash
EXPECTED_SERVER=TomcatWebServer mvn clean package
```

Launch the artifact with `--spring.profiles.active=lab` so only common properties apply. Expect `/lab/server` to return `"TomcatWebServer"`.

**Why test the rollback path too?** When production hits a rare Jetty/Undertow issue, rollback must restore a consistent artifact, classpath, and configuration. Changing only one dependency while leaving old server settings behind can shift limits or performance away from baseline.

## 17. Verifying REAL Configuration via HTTP, Logs, and Metrics

### 17.1. Verify HTTP Statuses, Headers, and JSON

```bash
curl -i http://127.0.0.1:8080/api/products/pen

curl -i -X POST http://127.0.0.1:8080/api/quotes \
  -H "Content-Type: application/json" \
  -d '{"sku":"pen","quantity":2}'

curl -i -X POST http://127.0.0.1:8080/api/quotes \
  -H "Content-Type: application/json" \
  -d '{"sku":"pen","quantity":0}'

curl -i -X POST http://127.0.0.1:8080/api/quotes \
  -H "Content-Type: text/plain" \
  --data 'sku=pen&quantity=2'
```

Expected in the demo without security or a proxy in front:

| Request | Status | Content |
| --- | --- | --- |
| GET `/api/products/pen` | 200 | JSON `{"sku":"pen","unitPriceVnd":12000}` |
| POST quote quantity 2 | 200 | JSON totalVnd 24000 |
| POST quote quantity 0 | 400 | `{"code":"INVALID_REQUEST"}` |
| POST quote Content-Type text/plain | 415 | Unsupported Media Type |
| GET `/api/products/missing` | 404 | `{"code":"PRODUCT_NOT_FOUND"}` |
| GET `/raw/ping` | 200 | `raw-servlet-ok` + newline |

Successful quote body:

```json
{"sku":"pen","quantity":2,"unitPriceVnd":12000,"totalVnd":24000}
```

JSON key ordering is not guaranteed; use JSONPath or schema-aware assertions instead of comparing raw string order. If 415 becomes 403 when Security/CSRF is enabled, the request was blocked before the controller; analyze the filter chain rather than disabling security just to get 415.

### 17.2. Verify Compression via Actual Bytes

Lab config:

```properties
server.compression.enabled=true
server.compression.min-response-size=1KB
server.compression.mime-types=text/plain,application/json
```

Send a request with `Accept-Encoding`:

```bash
curl -sS -D - -o /dev/null \
  -H "Accept-Encoding: gzip" \
  http://127.0.0.1:8080/api/blob?size=8192

curl -sS --compressed -D - -o /dev/null \
  http://127.0.0.1:8080/api/blob?size=8192
```

Check `Content-Encoding: gzip` when the server chooses gzip; `curl --compressed` transparently decompresses the body if saved/printed. Actual behavior depends on the HTTP engine, response metadata, transfer encoding, and request. Never conclude "compression is active" merely because `/lab/server` returned `"true"`.

**When comparing bandwidth:** inspect raw compressed bytes, `Content-Length`, and transfer encoding carefully; `curl -w '%{size_download}'` reports downloaded payload bytes, not full on-wire TCP overhead. Never run a test without `Accept-Encoding` and conclude gzip is broken.

### 17.3. Verify Request Header Limits

`server.max-http-request-header-size=16KB` is a shared property, yet limit calculation and error handling **differ by implementation**. Boot 3.5 docs note Tomcat applies the limit across request line + headers combined, whereas other runtimes enforce it differently.

Safe verification steps:

1. Run the app on localhost or staging—never test directly in production.
2. Send synthetic headers just below and above the threshold, containing no secrets.
3. Observe 200 vs 4xx status, startup logs, and access logs.
4. Note whether 400, 431, or connection close is returned by that server; do not hardcode a single status across all containers.
5. Check ingress/proxy header limits because upstream may reject before the backend.
6. Record the actual threshold **in bytes** and request-line inclusion, not just `"16KB"`.

Use controlled `curl`/HTTP clients without flooding concurrent connections to exhaust resources. **Seeing a bound header-limit property does not mean Jetty, Undertow, and Tomcat enforce the exact same byte boundary.**

### 17.4. Access Logs: Three Servers, Three Namespaces

- Tomcat: `server.tomcat.accesslog.enabled`, `server.tomcat.accesslog.pattern`, `server.tomcat.basedir`.
- Jetty: `server.jetty.accesslog.enabled`, `server.jetty.accesslog.filename`, `server.jetty.accesslog.format`.
- Undertow: `server.undertow.accesslog.enabled`, `server.undertow.accesslog.dir`, `server.undertow.accesslog.pattern`, plus `server.undertow.options.server.record-request-start-time` when `%D` timing is needed.

Capture **config, file path, sanitized sample line, and rotation** as evidence. Never log full request URIs if URIs contain tokens or PII; pick safe formats and redaction rules. Tomcat, Jetty, and Undertow differ in timing units and pattern syntax.

### 17.5. Micrometer/Actuator and Meter Names

Micrometer/Spring Boot Actuator records HTTP request observations, JVM memory/GC/threads, and server-specific meters when supported. **Do not assume `tomcat.*` metrics still exist after switching to Jetty.** Jetty exposes its own ThreadPool/Connector metrics; Undertow uses different instrumentation, and exported meters depend on the active registry and instrumentation.

For Tomcat, `server.tomcat.mbeanregistry.enabled=true` may be needed for certain Tomcat MBeans/metrics; that setting **does nothing for Jetty MBeans**. Check registered meters and update dashboards/alerts after swapping.

The lab exposes only `/actuator/health` and `info` by default. If enabling `/actuator/metrics` for diagnostics, do so only in a protected environment:

```properties
management.endpoints.web.exposure.include=health,info,metrics
```

Narrow it back down afterward. Never expose `/actuator/env`, `configprops`, `mappings`, `heapdump`, `loggers`, or `shutdown` publicly for convenience. `configprops` values require sanitization and role-based access to avoid dumping secrets.

## 18. HTTP/2: More Than `server.http2.enabled=true`

Spring Boot 3.5 offers:

```properties
server.http2.enabled=true
```

Documentation states this supports **h2** (HTTP/2 over TLS) and **h2c** (cleartext HTTP/2) on capable runtimes. Actual negotiation depends on server-specific modules, ALPN, TLS, clients, and proxies:

- **Tomcat 10.1:** supports h2/h2c with compatible Boot setup.
- **Jetty 12:** HTTP/2 over TLS may require `org.eclipse.jetty.http2:jetty-http2-server` and ALPN support (`org.eclipse.jetty:jetty-alpn-java-server` for JDK ALPN per docs); h2c has its own dependency requirements—check your exact target version.
- **Undertow 2.3:** Boot 3.5 docs state h2c/h2 support; still verify negotiated protocol directly.
- **Reactor Netty:** belongs to the reactive stack, not Servlet MVC Jetty/Undertow here.

Example Jetty HTTP/2 dependencies when **actually** enabling TLS h2 (supplemental snippet for the Jetty POM, not needed for the HTTP/1.1 demo):

```xml
<dependency>
    <groupId>org.eclipse.jetty.http2</groupId>
    <artifactId>jetty-http2-server</artifactId>
</dependency>
<dependency>
    <groupId>org.eclipse.jetty</groupId>
    <artifactId>jetty-alpn-java-server</artifactId>
</dependency>
```

Let the Boot BOM manage versions where possible. Configure `server.ssl.*`/certificates properly and test with an HTTP/2-capable client; never commit fake TLS private keys to the repository. To verify:

```bash
curl -V
curl -vk --http2 https://localhost:8443/api/products/pen
```

This command only **illustrates testing after you configure an HTTPS listener on 8443**; it does not match the default demo POM. Inspect the negotiated HTTP version and TLS trust result. If a proxy terminates TLS, the client may speak h2 to the proxy while the proxy speaks HTTP/1.1 to the backend; measure each **hop**. For h2c, use an h2c-capable client end-to-end rather than treating `server.http2.enabled` as proof.

## 19. Security, URL Parsing, and Session Differences Across Containers

### 19.1. Encoded Slashes and Special Paths

Servers differ in defaults for percent-encoded characters, `/%2F`, `;`, path parameters, request lines, and invalid UTF-8. Undertow provides `server.undertow.decode-slash` and related options; docs warn that decoding encoded slashes introduces **security risks** if the reverse proxy does not apply the exact same normalization.

Test path traversal, URL canonicalization, encoded slashes, duplicate slashes, semicolons/matrix params, and security path matchers against your policy. **Never enable relaxed path chars or slash decoding just to turn a 404 test into 200.** Ingress and application server must normalize URLs identically to prevent authorization bypasses.

### 19.2. Cookies and Sessions

Verify `Set-Cookie`, `JSESSIONID` Path/Domain/Secure/HttpOnly/SameSite, session creation, redirects, CSRF, and login callbacks. Servers may serialize or track session IDs differently if left implicit. If using Spring Session/Redis, test repository integration and multi-replica behavior; local live tests do not replace browser/staging E2E tests.

### 19.3. Servlet Filters and Non-MVC Routes

Custom Servlets, Filters, or Jersey integrations can register differently depending on config. The lab's `GET /raw/ping` confirms container Servlet routing independently of MVC `DispatcherServlet`. `X-Lab-Filter` on `/raw/ping` confirms the Filter bean applies to the actual HTTP request path.

### 19.4. Multipart, Form Posts, and Large Headers

Tomcat, Jetty, and Undertow have different form-post limits, multipart limits, and temp directories. In the Boot 3.5 appendix, documented keys include `server.jetty.max-http-form-post-size`, `server.undertow.max-http-post-size`, and `server.tomcat.max-http-form-post-size` (with non-identical semantics). For large uploads, reverse proxy body size/timeouts, disk quotas, temp dirs, and Servlet multipart settings also apply. Test size boundaries with synthetic data, not sensitive files or destructive floods.

### 19.5. Graceful Shutdown and Keep-Alive

Engines differ in connector timeouts, keep-alive handling, and connection draining. After swapping servers, test `SIGTERM` shutdown, readiness transition, in-flight request completion, thread pool/socket closure, and Kubernetes grace periods. Never gauge safety solely from `/actuator/health` returning 200 right after startup.

## 20. Servlet MVC, WebFlux, and External WAR: Three Different Questions

### 20.1. If You Are Using Spring MVC

Swap servers by swapping the Servlet starter dependency:

```text
spring-boot-starter-web -> exclude spring-boot-starter-tomcat
                        -> add spring-boot-starter-jetty
                         OR spring-boot-starter-undertow (Boot 3.5)
```

`DispatcherServlet` and Jakarta APIs remain the active web stack.

### 20.2. If Your App Uses Spring WebFlux

`spring-boot-starter-webflux` defaults to **Reactor Netty**. Boot 3.5 docs allow swapping the reactive HTTP server to Tomcat/Jetty/Undertow with compatible reactive dependencies/adapters, by **excluding `spring-boot-starter-reactor-netty`**, adding a reactive-compatible server, and verifying application type. Do not apply the MVC `exclude starter-tomcat` recipe to a WebFlux app.

If both web and webflux starters are present, Boot usually selects MVC inbound; having `WebClient` does not prove inbound traffic runs on WebFlux. When intentionally targeting reactive runtime, verify `spring.main.web-application-type` and WebFlux tests/metrics.

### 20.3. If You Want to Deploy a WAR to an External Server

That is **traditional WAR deployment**, distinct from an embedded swap. It requires `SpringBootServletInitializer`, `<packaging>war</packaging>`, `provided` container scope, matching Jakarta Servlet version, and external context paths. External Tomcat/Jetty/app servers own their connectors; embedded `server.jetty.*` properties do not configure an external Jetty server.

**Do not change web framework, packaging, and server engine all in one change unless forced to.** Separate PRs or feature flags and keep a baseline per boundary.

## 21. Measuring Performance and Choosing a Server Using Data

No statement like "Jetty is always faster than Tomcat" or "Undertow always uses less RAM" holds across all workloads. Differences depend on CPU cores, Java version, allocation/GC, blocking JDBC, response size, TLS, HTTP/2, request rates, and thread/buffer tuning.

### Designing a Fair Experiment

1. Lock Java/OS/container image, CPU/RAM limits, and dependency versions.
2. Keep the same app/service/DB, dataset, GET/POST mix, and validation errors.
3. Keep the same request path (direct HTTP or through proxy) and network conditions.
4. Warm up first, then measure steady-state, peak/burst, and soak phases.
5. Compare **achieved RPS**, p50/p95/p99 latency, error rate, throughput, CPU, RSS, heap/GC, active threads/sockets, and pool waits.
6. Run repeated trials with confidence intervals when deltas are small; never make architectural choices from random noise.
7. Measure one configuration change at a time (never swap server + add CPU + rewrite SQL together).
8. Factor in SLOs, operational cost, maintainability, and security update cadence of the target server.

### Thread Tuning Is Not Unit Conversion

- Tomcat: connector threads, max connections, accept queue.
- Jetty: thread pool max/min, selector/acceptor threads, max connections.
- Undertow: I/O threads and worker threads, XNIO options/direct buffers.

A blocking JDBC servlet handler needs appropriate worker concurrency; too many workers increase context-switching, memory, and DB pressure. Never "raise threads to 1000" instead of analyzing pools, CPU, and DB. With Java virtual threads, several server-specific pool keys lose their traditional effect; consult target version docs.

### Signs of Production Regression After a Swap

- 4xx/5xx spikes from parser, header, or path-handling changes.
- Peak p95/p99 jumps even while average latency looks fine.
- `Queue full`, connection resets, or proxy timeouts.
- Multipart upload 413/400 errors due to different form limits.
- Broken session redirects or cookie paths.
- Disappearing Actuator metrics or server-specific dashboards.
- Missing or mis-rotated access logs.
- Unusual growth in native/direct buffers or thread counts.
- HTTP/2 or TLS handshake failures.
- Graceful shutdown failing to finish in-flight requests.

## 22. Troubleshooting: Diagnosing Layer by Layer

| Symptom | Hypothesis | Action |
| --- | --- | --- |
| POM adds Jetty but `/lab/server` returns Tomcat | Tomcat starter not fully excluded | Run `mvn dependency:tree`, exclude from source |
| Both Jetty and Undertow present | Two starters declared | Keep only one, clean build |
| Runtime server is Undertow while `jetty` profile is active | Profiles do not pick the engine | Align active profile with classpath |
| Server starts while `server.tomcat.*` appears in `Environment` | Legacy properties have no effect on Jetty | Migrate properties to current namespace |
| Jetty threads still default to 200 | `application-jetty.properties` inactive | Check active profiles and effective bindings |
| Undertow access log lacks timing | Missing `record-request-start-time` | Enable option, verify `%D` |
| Access log missing | Directory, filename, profile, or permissions | Check config, log path, and whether requests ran |
| Compression property true but no gzip | `Accept-Encoding`, size, MIME, or buffering | Test `/api/blob` with gzip request header |
| Gzip works on Jetty but not Undertow | Different server behavior/config or proxy | Compare headers, actual bytes, and server docs |
| HTTP/2 fails to negotiate | Missing SSL/Jetty modules/ALPN/client support | Verify h2/h2c, use HTTP/2-capable curl |
| `/raw/ping` returns 404 while MVC works | Servlet registration/mapping issue | Live HTTP test the Servlet path |
| Invalid JSON returns 500 instead of 400 | Advice/converter/server filter mismatch | Test negative contract and logs |
| Header limit status differs | Container parser semantics differ | Verify actual policy, do not hardcode 431 |
| Encoded slashes behave differently | URL decoder / Servlet container policy | Standardize routing/security, do not relax blindly |
| Security 403 appears only after swap | Session/cookie/filter/CSRF/proxy path | Compare auth chain and cookies |
| Startup fails with Jetty `NoSuchMethodError` | Jetty module/BOM version mismatch | Remove manual pins, inspect dependencies |
| Undertow missing on Boot 4 | Starter support removed | Stay on Boot 3.5 or use supported Boot 4 engine |
| `RANDOM_PORT` test passes despite wrong engine | Test failed to assert actual server | Assert `/lab/server` against expected class |
| Production `tomcat.*` metrics vanish | Server changed | Update monitoring for Jetty/Undertow |
| App works directly yet ingress returns 502 | Port readiness or proxy connector mismatch | Run deployed smoke test via gateway |
| Load test worsens as workers increase | Blocking DB/CPU/GC contention | Profile entire system |
| `Server` header still says Tomcat behind proxy | Proxy/header cache or wrong upstream target | Probe backend class and port directly |
| Tests pass under MOCK context | No real HTTP listener started | Use `@SpringBootTest(RANDOM_PORT)` |

Do not tweak global settings blindly when seeing 400/404/500. Confirm which server processed the request, whether it reached MVC or failed at container/proxy, and correlate logs/traces with a request ID.

## 23. Hands-On Exercises and Guided Answers

### Exercise A — Changed Dependency but Forgot Exclusion

Add the Jetty starter to a default `starter-web` project without excluding Tomcat. Predict the dependency tree and runtime state. Answer: two server starters sit on the classpath, violating "one clearly selected server"; add the exclusion and check `/lab/server`.

### Exercise B — Passed Profile for the Wrong Engine

Build with Undertow, then run `--spring.profiles.active=lab,jetty`. Check `/lab/server` and access logs. Answer: the server **remains Undertow**; Jetty properties cannot "switch" the engine or tune Undertow workers. Match the profile to the built engine and verify config.

### Exercise C — Testing the 16KB Header Limit

Send two HTTP requests with synthetic headers just below and above the threshold. Compare Tomcat, Jetty, and Undertow on status code, connection close, and error timing. Answer: threshold units and request-line + header accounting can differ; do not assert identical status/byte counts unless target docs guarantee them.

### Exercise D — Checking the Jetty Access Log

Enable `server.jetty.accesslog.enabled`, choose a writable filename, call `/api/products/pen`, and inspect the file. Answer: startup logs are not access logs; verify the request line was written.

### Exercise E — Checking Undertow `%D`

Enable an Undertow access log pattern containing `%D` without `server.undertow.options.server.record-request-start-time=true`. Observe timing, then enable the option and re-test. Answer: `record-request-start-time` is required for duration logging per docs.

### Exercise F — Server Swap and Servlet Registration

Delete `RawServletConfiguration` and re-run `LiveHttpServerTest`. `@WebMvcTest` still passes for MVC, yet live `/raw/ping` fails. Answer: tests must cover container-level routing too.

### Exercise G — `Server` Header Overwritten by Proxy

Place a simulated reverse proxy injecting `Server: gateway`. Compare the HTTP header against `/lab/server`. Answer: the header does not prove backend identity; keep diagnostic endpoints local/secured.

### Exercise H — Enabling HTTP/2

Read Jetty HTTP/2 and ALPN docs, add the required modules, configure a test TLS certificate, and test with `curl -V` and `curl --http2` to check the real protocol. Answer: `server.http2.enabled=true` alone does not prove clients negotiated `h2`.

### Exercise I — Fair Load Comparison

Given Jetty max threads 64 and Undertow I/O=2/worker=32, plan a load test with identical request mix, CPU, DB, and duration measuring p95/p99 and errors. Answer: never infer faster/slower from raw thread counts with different semantics.

### Exercise J — Upgrading Boot 3.5 → Boot 4

Restate the matrix: Boot 4 targets Servlet 6.1, Jetty 12.1 / Tomcat 11, and removes Undertow starter support. Answer: do not copy Boot 3.5's `spring-boot-starter-undertow` into Boot 4 expecting supported startup.

### Exercise K — Rolling Back to Tomcat

Remove Jetty/Undertow, restore default Tomcat, set `EXPECTED_SERVER=TomcatWebServer`, and run Maven tests plus HTTP smoke checks. Answer: rollback must synchronize both dependencies **and** server-specific properties.

### Exercise L — Testing Encoded Slashes

Send a URL containing `%2F` to a local test environment and observe server, proxy, and app routing. Answer: parser and security normalization must stay consistent across hops; never allow encoded slashes loosely due to bypass risks.

## 24. Server Swap Delivery Checklist

### Build / Dependencies

- [ ] Java, Spring Boot, and Servlet engine versions fall within the supported matrix.
- [ ] Only one embedded servlet server starter appears in the dependency graph.
- [ ] `starter-web` remains for MVC, with Tomcat properly excluded.
- [ ] No transitive Jetty/Tomcat/Undertow versions pinned outside the Boot BOM.
- [ ] Clean build completed and executable JAR / dependency tree inspected.
- [ ] If targeting Boot 4, Undertow is not assumed as a supported starter.
- [ ] Rollback artifact, commit ID, JDK, and image digest recorded.

### Runtime / Configuration

- [ ] Actual HTTP server class matches expectations via live test.
- [ ] Port, context path, and bind address verified; not relying on the `Server` header.
- [ ] Common `server.*` properties bound and actual runtime behavior verified.
- [ ] No stale `server.tomcat.*` keys left inactive under Jetty/Undertow.
- [ ] Jetty/Undertow threads, queues, buffers, and keep-alive have a capacity plan.
- [ ] Access logs actually write and rotate under a privacy policy.
- [ ] Compression verified via `Accept-Encoding`, body size, and content type.
- [ ] HTTP/2 (if required) verified over the right TLS/proxy hop.
- [ ] Header/form/upload limits, URL encoding, and sessions/cookies tested.
- [ ] Actuator health, metrics/alerts, readiness, and graceful shutdown verified.
- [ ] `@Profile("lab")` diagnostic endpoint is disabled/not exposed in production.

### QA and Rollout

- [ ] Business logic unit tests pass.
- [ ] MVC MockMvc tests for validation/JSON/statuses pass.
- [ ] Live HTTP `RANDOM_PORT` tests assert the **actual server class**, Servlet, and Filter registration.
- [ ] `curl` negative checks for 400/404/405/415, compression, and context path verified.
- [ ] Security auth, CSRF, CORS, and proxy headers tested in staging if applicable.
- [ ] Representative load tests compare p95/p99/error rate plus CPU/GC/memory/pools.
- [ ] Canary/blue-green rollout has health/smoke checks, logs/metrics, and clear rollback triggers.
- [ ] Rollback to the previous server actually tested, not merely planned on paper.

## 25. Official References

- [Spring Boot 3.5 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): swapping server starters, HTTP compression, HTTP/2, access logs, forwarded headers, `WebServerFactoryCustomizer`.
- [Spring Boot 3.5.16 — System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html): Java 17+, Tomcat 10.1 / Jetty 12.0 / Undertow 2.3, and Servlet 6.0.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `server.*`, `server.jetty.*`, `server.undertow.*`, `server.tomcat.*`.
- [Spring Boot 3.5 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): MVC and servlet/filter registrations.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): MockMvc, `RANDOM_PORT`, `TestRestTemplate`.
- [Spring Boot 3.5 — Actuator Metrics](https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html): JVM/HTTP/Jetty/Tomcat metric capabilities.
- [Spring Boot 3.5 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html): health, exposure, metrics/security.
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): Servlet 6.1 baseline, Undertow removal.
- [Spring Boot 4.0 — System Requirements](https://docs.spring.io/spring-boot/4.0/system-requirements.html): Jetty 12.1, Tomcat 11, supported Servlet 6.1.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): testing MVC requests/responses without opening a port.
- [Jetty 12 Documentation](https://jetty.org/docs/jetty/12/): Jetty connectors, thread pool, HTTP/2, and ALPN.
- [Undertow Documentation](https://undertow.io/): handlers, XNIO workers, HTTP options.
- [Maven Dependency Plugin](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): inspecting the dependency graph.
- [Jakarta Servlet Specification](https://jakarta.ee/specifications/servlet/): URL mapping, filters, sessions, and lifecycle.

**Conclusion:** Replacing Tomcat with Jetty or Undertow in Spring Boot MVC is a combined **dependency + runtime configuration + verification** change. A POM listing Jetty is not enough; you must prove Jetty/Undertow is **actually listening for HTTP**, engine-specific config is migrated properly, Servlet/Filter/JSON/error contracts remain intact, logs/metrics/limits/HTTP2 are safe, and performance meets SLOs. Practice on Boot **3.5.16** since all three engines are available; if upgrading to Boot **4**, check the server support matrix first before choosing.