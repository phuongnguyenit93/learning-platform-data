# Application Picks the Wrong Web Stack Due to Transitive Dependencies

> **Context:** Spring Boot – **web-runtime** → **Debugging and Upgrades**. This Knowledge article focuses on the bug where an application intended to run **Spring WebFlux (REACTIVE)** instead starts **Spring MVC/Servlet (SERVLET)** because a library is brought in as a **transitive dependency**. It also covers the case where MVC properly uses `WebClient`, as well as batch/CLI applications that do not need a web server. Examples use **Java 17+, Spring Boot 3.3.x (lab version 3.3.13), Maven, and Gradle**. The lab uses two Maven modules: `gateway-lib` and `reactive-app`, with complete POMs, Java sources, integration tests, steps to reproduce the issue, dependency exclusion, and verification against a real HTTP server.

## 1. Learning Objectives

After this article, you will be able to:

1. Distinguish between **WebApplicationType.SERVLET**, **WebApplicationType.REACTIVE**, and **WebApplicationType.NONE**.
2. Understand the Boot 3.3 rule: if **Spring MVC and Spring WebFlux are both present**, MVC **takes precedence** when deducing the web application type.
3. Distinguish `spring-boot-starter-web`, `spring-webmvc`, `spring-boot-starter-webflux`, `spring-webflux`, `spring-boot-starter-tomcat`, and `spring-boot-starter-reactor-netty`.
4. Understand why an **outbound** `WebClient` does not automatically switch the **inbound HTTP server** to WebFlux.
5. Trace direct and transitive dependencies using `mvn dependency:tree` or Gradle `dependencyInsight` for the actual runtime classpath.
6. Verify which `ApplicationContext` type the app actually runs, rather than relying solely on Tomcat/Netty startup logs.
7. Understand Boot auto-configuration conditions such as `@ConditionalOnClass` and `@ConditionalOnWebApplication`, and use `--debug` to inspect the Conditions Evaluation Report.
8. Use narrowly scoped Maven `<exclusions>` or Gradle `exclude` rules, while knowing the limitations of exclusions when a library appears via multiple paths.
9. Write integration tests that start a real embedded web server, **fail before the fix**, and **pass after the fix**; see clearly why checking HTTP status 200 alone is insufficient.
10. Distinguish the `spring.main.web-application-type=reactive` workaround from fixing the **root cause** in the dependency graph.
11. Recognize that the wrong web stack can lead to mismatched filters, interceptors, reactive routing, security chains, timeouts, threading models, and metrics.
12. Establish a runbook for upgrades, regression tests, deployment artifacts, canary/rollback, and preventing shared libraries from pulling in an unnecessary web starter.

## 2. Typical Incident After Upgrading a Shared Library

A team develops a reactive service using WebFlux, WebClient, and non-blocking drivers. The application module only declares `spring-boot-starter-webflux` and a shared client library. After updating the shared library, the startup log suddenly shows Tomcat, a WebFlux router is not mapped, or a `WebFilter` has no effect.

~~~text
reactive-app
    |
    +-- spring-boot-starter-webflux
    |       +-- spring-webflux
    |       +-- spring-boot-starter-reactor-netty
    |
    +-- gateway-lib
            +-- spring-boot-starter-web      <-- transitive dependency
                    +-- spring-webmvc
                    +-- spring-boot-starter-tomcat
~~~

In the `reactive-app/pom.xml` source there is no direct `starter-web` dependency, yet Maven/Gradle brings it onto the **runtime classpath** via `gateway-lib`. When Boot 3.3 sees both `spring-webmvc` and `spring-webflux`, **MVC wins by default precedence**. This is not a random choice by Spring Boot; the algorithm uses classpath indicators and configuration overrides.

**What needs fixing:** find out who is pulling Spring MVC onto the classpath and whether that dependency is actually needed. Do not just add a reactive flag to tests and consider the problem solved: the production artifact may still contain MVC libraries, beans, and assumptions.

## 3. Distinguishing Stack, Web Server, HTTP Client, and Starter

| Layer | Example | Role |
|---|---|---|
| Web application type | `SERVLET` / `REACTIVE` / `NONE` | Selects the web-oriented Spring ApplicationContext |
| Servlet framework | Spring MVC, `DispatcherServlet` | Handles HTTP on the Servlet stack |
| Reactive framework | Spring WebFlux, `DispatcherHandler` | Reactive request handling |
| HTTP server | Tomcat, Jetty, Undertow, Reactor Netty | Engine listening on TCP/HTTP |
| HTTP client | `RestClient`, `WebClient`, Java `HttpClient` | Makes **outbound** API calls |
| Starter | `spring-boot-starter-web` | Bundles dependency/auto-config ecosystem |
| Dependency scope | compile, runtime, test, provided | Classpath by phase |
| Auto-configuration | `WebMvcAutoConfiguration`, `WebFluxAutoConfiguration` | Conditionally creates framework beans |

Do not equate "Tomcat definitely means MVC": Spring Boot WebFlux can use Servlet-compatible servers in certain configurations. Likewise, do not claim "a Netty JAR on the classpath means the app is reactive": Netty may simply be the HTTP client connector. **The actual ApplicationContext type + handler chain** tells you which inbound stack was selected.

### Deduction Table in Spring Boot 3.3

| Classpath/configuration | Default type or override | Commonly observed |
|---|---|---|
| Spring MVC present | `SERVLET` | MVC, embedded Tomcat if starter-web |
| WebFlux present, MVC absent | `REACTIVE` | WebFlux, Reactor Netty if starter-webflux |
| **Both MVC + WebFlux** | **`SERVLET`** | MVC takes precedence |
| No matching web indicators | `NONE` | Non-web context |
| Web libs present but `spring.main.web-application-type=none` | `NONE` | Non-web override |
| Both MVC + WebFlux but forced `reactive` | `REACTIVE` | Must verify all reactive beans/security |
| Custom `SpringApplication.setWebApplicationType` | Per Java configuration | No longer pure classpath deduction |

**Do not use this table as a substitute for runtime inspection.** Custom ApplicationContextFactory implementations, environment variables, and programmatic overrides can all change the outcome.

## 4. Why Does MVC Take Precedence When WebFlux Is Also Present?

The official Spring Boot 3.3 documentation states: adding both `spring-boot-starter-web` and `spring-boot-starter-webflux` auto-configures Spring MVC. The reason is that many MVC services need **reactive outbound `WebClient`** without wanting to switch their inbound Servlet handlers to a reactive server.

~~~text
MVC server (correct when the application intentionally chooses MVC)
    Incoming HTTP -> DispatcherServlet / Servlet Filters
                         |
                         +-- @RestController
                         |
                         +-- WebClient outbound -> API B
                                     (valid to use!)

Reactive server (correct when the application intentionally chooses WebFlux)
    Incoming HTTP -> DispatcherHandler / WebFilter
                         |
                         +-- RouterFunction or @RestController
                         |
                         +-- WebClient outbound -> API B
~~~

`WebClient` only determines how **remote HTTP APIs** are called. `spring-webflux` provides both the client API and the server stack, but the presence of the client does not automatically override MVC precedence. Conversely, if a shared starter accidentally brings Spring MVC into a WebFlux service, Boot will not infer "WebFlux because the code returns `Mono`".

## 5. Common Symptoms of the Wrong Web Stack

- The startup log switches from Reactor Netty to Tomcat by default. This is a **signal**, not sole proof.
- The actual `ApplicationContext` is `AnnotationConfigServletWebServerApplicationContext` even though the team wanted a reactive context.
- A `RouterFunction<ServerResponse>` is defined for WebFlux, but requests are not routed as expected.
- An `org.springframework.web.server.WebFilter` does not run because the inbound path is a Servlet `Filter` chain.
- A reactive `SecurityWebFilterChain` is not the active filter chain, whereas a Servlet `SecurityFilterChain` may be created or configured differently.
- The team sees `Mono` in a controller and assumes the app is reactive; Spring MVC supports certain reactive return types, so that does not prove the server stack.
- An HTTP route returns 200, but timeouts/exception handling/threading model do not behave according to the reactive design.
- After upgrading a library version, the dependency tree includes `spring-webmvc` even though the app does not declare `starter-web` directly.
- Running in a local IDE differs from the executable JAR/container due to build profiles, scopes, cached artifacts, or env overrides.
- A CLI/batch app unexpectedly opens port 8080 because web indicators appeared in the dependency graph.

Do not conclude that every 404/403 is caused by the wrong stack. Filter matchers, route registrations, proxy rewrites, authentication, and application code can also cause 404/403. You must **cross-check the classpath, context, auto-config, and HTTP behavior**.

## 6. Direct Dependency vs. Transitive Dependency

**Direct:** declared directly in `reactive-app/pom.xml`.  
**Transitive:** a dependency of a dependency; Maven/Gradle typically resolves it into the consumer runtime according to scope/rules.

~~~text
reactive-app
  |
  +-- starter-webflux               [direct]
  |
  +-- gateway-lib                   [direct]
        |
        +-- starter-web             [transitive]
              |
              +-- spring-webmvc
              +-- Tomcat
~~~

A client library sometimes only needs `spring-web` or `RestClient` yet declares `spring-boot-starter-web`, inadvertently dictating the inbound runtime of its consumers. This is a sign that the library's **dependency contract design** needs review. If the library intentionally provides Servlet filters/controller auto-config, an exclusion may break the library; instead, choose or split an appropriate adapter module.

**Do not guess the graph from Java imports.** A library that does not import `DispatcherServlet` in its main source can still declare `starter-web` in its published POM and pull transitive classes into the app.

## 7. Diagnosis: Gather Evidence Before Fixing

1. Record the expected type: `SERVLET`, `REACTIVE`, or `NONE`; and why? Contract, latency, thread/driver model, and business requirements.
2. Identify the Spring Boot version/BOM so you know the rules for the **exact version**.
3. Obtain the resolved **runtime dependency tree**, not just the direct POM.
4. Search for `spring-webmvc`, `spring-webflux`, `starter-web`/`starter-webflux`, Tomcat/Netty, and their paths.
5. Check externalized settings `spring.main.web-application-type`, env vars, command-line args, or programmatic `SpringApplication.setWebApplicationType`.
6. Observe the actual `ApplicationContext` and startup logs.
7. Inspect the `Conditions Evaluation Report` to see which Servlet/Reactive auto-configurations match.
8. Test actual incoming HTTP behavior and the security/filter stack; do not rely only on a 200 response body.
9. Compare dependency trees between the last good release and the broken release after the upgrade.
10. Choose the smallest fix, backed by a CI guard and a rollback path if acceptance criteria are not met.

**Do not hot-fix by deleting JARs from the Maven cache, removing imports, or immediately adding `@EnableWebFlux`.** The build tool will re-resolve dependencies; `@EnableWebFlux` changes framework configuration and does not remove MVC from the classpath.

## 8. Maven dependency:tree: Finding the Offending Path

In a Maven project:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dscope=runtime
mvn dependency:tree -Dincludes=org.springframework:spring-webmvc
mvn dependency:tree -Dincludes=org.springframework:spring-webflux
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-web
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-webflux
~~~

**Illustrative** tree example, not output captured from a real repository:

~~~text
example:reactive-app:jar:0.0.1-SNAPSHOT
+- spring-boot-starter-webflux:jar:3.3.13
|  +- spring-webflux:jar:<version-managed-by-boot>
|  \- spring-boot-starter-reactor-netty:jar:3.3.13
\- example:gateway-lib:jar:0.0.1-SNAPSHOT
   \- spring-boot-starter-web:jar:3.3.13
      +- spring-webmvc:jar:<version-managed-by-boot>
      \- spring-boot-starter-tomcat:jar:3.3.13
~~~

This is a **logical diagram**, not verbatim output, because Maven also prints groupIds, many other transitive dependencies, and real versions. When investigating, you must find the exact **path from the root app to `spring-webmvc`** rather than just spotting a single `spring-webmvc` line.

### Scopes to Read Accurately

| Scope | Included in a typical runtime executable JAR | Consequence |
|---|---|---|
| compile | Usually yes | Pulls transitive dependencies into the app |
| runtime | Yes | Web indicator can appear even if source never imports it |
| test | No | Can alter `@SpringBootTest` if the test classpath differs |
| provided | Depends on packaging/external container | WAR differs from a Boot executable JAR |
| optional | Consumers do not inherit transitively under Maven optional semantics | Useful for genuinely optional features |

Do not use `testRuntimeClasspath` instead of `runtimeClasspath` to draw conclusions about production. At the same time, if only **tests** fail, inspect test-scoped additions separately.

## 9. Gradle dependencyInsight

With Gradle, inspect the configuration of the running service:

~~~bash
./gradlew :reactive-app:dependencies \
  --configuration runtimeClasspath

./gradlew :reactive-app:dependencyInsight \
  --dependency spring-webmvc \
  --configuration runtimeClasspath

./gradlew :reactive-app:dependencyInsight \
  --dependency spring-boot-starter-web \
  --configuration runtimeClasspath
~~~

On Windows, use `gradlew.bat`. `dependencyInsight` shows who brought the module into the graph and why Gradle chose that version, unlike just reading `implementation` declarations.

**Groovy `build.gradle` snippet** example, assuming plugins and BOM are already declared in the project:

~~~groovy
dependencies {
    implementation "org.springframework.boot:spring-boot-starter-webflux"

    implementation("example:gateway-lib:0.0.1-SNAPSHOT") {
        exclude group: "org.springframework.boot",
                module: "spring-boot-starter-web"
    }
}
~~~

In multi-module Gradle you can use `implementation(project(":gateway-lib")) { exclude ... }`. Do not copy Groovy syntax verbatim into Kotlin DSL `build.gradle.kts`.

**Avoid global exclusions** before understanding all paths. A global `configurations.configureEach { exclude ... }` can break modules or tests that need Spring MVC. Fix the specific dependency edge causing interference and re-test the entire runtime graph.

## 10. How Is Spring Boot Auto-Configuration Affected?

A starter is not just a single JAR. It brings **transitive dependencies** onto the classpath, changing the conditions that Spring Boot evaluates:

- `@ConditionalOnClass`: is the framework class present?
- `@ConditionalOnWebApplication(type=SERVLET)`: is the app using the Servlet web type?
- `@ConditionalOnWebApplication(type=REACTIVE)`: is the app the Reactive web type?
- `@ConditionalOnMissingBean`: does an existing bean cause auto-config to back off?
- `@ConditionalOnProperty`: does configuration enable/disable the feature?

~~~text
Maven / Gradle dependency graph
       |
       v
Actual runtime classpath
       |
       v
SpringApplication: detect/override WebApplicationType
       |
       +-- SERVLET --> ServletWebServerApplicationContext
       |                WebMvcAutoConfiguration candidates
       |                DispatcherServlet, Servlet server
       |
       +-- REACTIVE --> ReactiveWebServerApplicationContext
       |                WebFluxAutoConfiguration candidates
       |                DispatcherHandler, Reactive server
       |
       +-- NONE ----> non-web ApplicationContext
       |
       v
Conditional auto-configuration + beans + properties
       |
       v
Actual listener and request/security/filter pipeline
~~~

If both MVC and WebFlux are present, having WebFlux APIs on the classpath **does not force** `WebFluxAutoConfiguration` to be chosen as the inbound server infrastructure. A `WebFlux RouterFunction` bean may exist yet **have no WebFlux handler adapter/router mapping** processing it as the author expected.

### Conditions Evaluation Report

Run:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

Or via JAR:

~~~bash
java -jar reactive-app/target/reactive-app-0.0.1-SNAPSHOT.jar --debug
~~~

The report shows matched/not-matched auto-configurations and reasons involving classes/beans/web type. Look for `WebMvcAutoConfiguration`, `WebFluxAutoConfiguration`, `ServletWebServerFactoryAutoConfiguration`, `ReactiveWebServerFactoryAutoConfiguration`, and `DispatcherServletAutoConfiguration` in the actual report; exact names and reasons may vary by version.

If Actuator is present, `/actuator/conditions` also provides the report when configured to be exposed **and secured**. Do not expose `management.endpoints.web.exposure.include=*` publicly just to debug; reports/configs/beans can leak internal details.

**The Conditions report is not a dependency tree.** It explains *why Boot configured a bean*; Maven/Gradle explains *who put the JAR onto the runtime classpath*.

## 11. Observing ApplicationContext: The Decisive Measurement

An integration test can do:

~~~java
// Snippet in a @SpringBootTest:
@Autowired
ApplicationContext context;

@Test
void expectedReactiveServer() {
    assertTrue(
        context instanceof ReactiveWebServerApplicationContext);
}
~~~

Relevant classes:

- `org.springframework.boot.web.reactive.context.ReactiveWebServerApplicationContext`.
- `org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext`.
- `org.springframework.context.ApplicationContext`.

In Boot 3.3, `AnnotationConfigReactiveWebServerApplicationContext` and `AnnotationConfigServletWebServerApplicationContext` are the typical concrete implementations. **Tests should assert the interface type**, rather than hardcoding the class simple name, because a custom `ApplicationContextFactory` may be in use.

**Just checking for "Tomcat" or "Netty" in logs is not enough:** a reactive web server can be configured with Tomcat/Jetty, and Reactor Netty may only be acting as an HTTP client. You should observe the context **and** real HTTP requests.

## 12. Two-Module Maven LAB: Reproducing the Transitive Bug

Full directory tree:

~~~text
stack-drill/
  pom.xml
  gateway-lib/
    pom.xml
    src/main/java/example/gateway/PartnerName.java
  reactive-app/
    pom.xml
    src/main/java/example/stack/ReactiveApplication.java
    src/main/resources/application.properties
    src/test/java/example/stack/ReactiveStackTests.java
~~~

`gateway-lib` contains only a plain Java class, yet its POM intentionally declares `spring-boot-starter-web` to demonstrate a library dependency design flaw. `reactive-app` declares `starter-webflux` and uses that class. The goal is to prove MVC is selected **via a transitive dependency**, not because of a controller mistake.

### 12.1. Root Maven pom.xml

Create `stack-drill/pom.xml`:

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
    <artifactId>stack-drill</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <packaging>pom</packaging>
    <modules>
        <module>gateway-lib</module>
        <module>reactive-app</module>
    </modules>
    <properties>
        <java.version>17</java.version>
    </properties>
</project>
~~~

The root is a Maven aggregator/parent (`packaging=pom`), not an executable application. Child modules inherit Spring Boot dependency management and the Java version from the parent.

### 12.2. gateway-lib/pom.xml — **intentionally unnecessary** dependency

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>example</groupId>
        <artifactId>stack-drill</artifactId>
        <version>0.0.1-SNAPSHOT</version>
    </parent>
    <artifactId>gateway-lib</artifactId>
    <dependencies>
        <!-- Intentionally wrong: the library does not need an HTTP server -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

When a consumer adds `gateway-lib` with `compile` scope, `starter-web` travels along the transitive path unless marked optional or excluded per Maven resolution rules. **Do not use this "wrong" POM for a production library**.

### 12.3. gateway-lib/PartnerName.java

Create `gateway-lib/src/main/java/example/gateway/PartnerName.java`:

~~~java
package example.gateway;

public final class PartnerName {
    private PartnerName() {
    }

    public static String label() {
        return "shared";
    }
}
~~~

There are no Spring MVC imports at all, yet the POM pulls in the entire server stack. This is why you must inspect the **published POM**, not just Java imports.

### 12.4. reactive-app/pom.xml — **before the fix**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>example</groupId>
        <artifactId>stack-drill</artifactId>
        <version>0.0.1-SNAPSHOT</version>
    </parent>
    <artifactId>reactive-app</artifactId>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>example</groupId>
            <artifactId>gateway-lib</artifactId>
            <version>0.0.1-SNAPSHOT</version>
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

This POM must have a valid XML schema declaration according to the Maven XSD. `xsi:schemaLocation` above only points to the XSD URL and omits the namespace pair, and also lacks `xmlns:xsi` in a standalone minimal form; **to avoid an invalid XML namespace declaration in the POM**, use the exact opening tag from root/`gateway-lib`: `<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">`. The inner contents remain valid. In a real project, apply this standard opening tag to both child modules.

`reactive-app` does not declare `starter-web`, yet it still receives it through the library. Do not force `spring.main.web-application-type` in the lab because we want to detect the bug automatically.

### 12.5. reactive-app/application.properties

Create `reactive-app/src/main/resources/application.properties`:

~~~properties
server.port=8080
server.error.include-message=never
server.error.include-stacktrace=never
~~~

Do not include `spring.main.web-application-type=reactive`, so we do not mask the regression. When running JUnit `RANDOM_PORT`, Spring Boot will pick a random port instead of binding 8080.

### 12.6. reactive-app/ReactiveApplication.java — runs on both MVC and WebFlux

Create `reactive-app/src/main/java/example/stack/ReactiveApplication.java`:

~~~java
package example.stack;

import example.gateway.PartnerName;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.reactive.context.ReactiveWebServerApplicationContext;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.context.ApplicationContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ReactiveApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveApplication.class, args);
    }

    public record StackInfo(
            String applicationContext,
            boolean servlet,
            boolean reactive,
            String gatewayContract) {
    }

    @RestController
    static class DiagnosticController {
        private final ApplicationContext context;

        DiagnosticController(ApplicationContext context) {
            this.context = context;
        }

        @GetMapping("/stack")
        public StackInfo stack() {
            return new StackInfo(
                context.getClass().getSimpleName(),
                context instanceof ServletWebServerApplicationContext,
                context instanceof ReactiveWebServerApplicationContext,
                PartnerName.label());
        }
    }
}
~~~

**Why choose `@RestController`?** Both Spring MVC and WebFlux support the controller annotation style. Thus `GET /stack` can return HTTP 200 **in both modes**; this is intentional to prove that a "200 endpoint" test **is not enough to confirm the right stack**.

After excluding the MVC dependency, the JSON output looks like:

~~~json
{
  "applicationContext": "AnnotationConfigReactiveWebServerApplicationContext",
  "servlet": false,
  "reactive": true,
  "gatewayContract": "shared"
}
~~~

In the broken pre-fix state, `servlet` is typically `true` and `reactive` is `false`. Do not hardcode the exact class simple name or JSON key order in tests, since an app may use a custom context implementation.

### 12.7. ReactiveStackTests.java — intentionally FAILS before the fix

Create `reactive-app/src/test/java/example/stack/ReactiveStackTests.java`:

~~~java
package example.stack;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.boot.web.reactive.context.ReactiveWebServerApplicationContext;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.context.ApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ReactiveStackTests {

    @Autowired
    ApplicationContext context;

    @LocalServerPort
    int port;

    @Test
    void inboundServerMustBeReactive() {
        assertTrue(
            context instanceof ReactiveWebServerApplicationContext,
            () -> "Expected REACTIVE, got "
                + context.getClass().getName());
        assertFalse(
            context instanceof ServletWebServerApplicationContext);
    }

    @Test
    void http200AloneDoesNotProveWebStack() throws Exception {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(
                    "http://localhost:" + port + "/stack"))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertTrue(response.body()
                .contains("\"gatewayContract\":\"shared\""));
    }
}
~~~

**Before the fix:** `inboundServerMustBeReactive` must **FAIL** because the app picks MVC; the GET 200 test may **PASS**.  
**After the fix:** both tests must **PASS** because `gateway-lib` still works, `spring-webflux` remains, and `spring-webmvc` has been excluded from runtime.

`java.net.http.HttpClient` in the test is only an HTTP **client**; it does not determine the Spring server type. `@SpringBootTest(RANDOM_PORT)` starts an actual TCP web server; it is not like a pure mock MVC test.

## 13. Step-by-Step Lab: Reproduce, Trace the Graph, Fix, Verify

### 13.1. Build initial artifacts

From the `stack-drill` directory:

~~~bash
mvn -DskipTests install
~~~

This compiles and installs the root/modules into the **local Maven repository** without running JUnit tests. It allows `mvn -pl reactive-app dependency:tree` commands to resolve `example:gateway-lib:0.0.1-SNAPSHOT` in the lab without needing a remote registry.

### 13.2. Find the transitive dependency

~~~bash
mvn -pl reactive-app dependency:tree
mvn -pl reactive-app dependency:tree \
  -Dincludes=org.springframework:spring-webmvc
mvn -pl reactive-app dependency:tree \
  -Dincludes=org.springframework.boot:spring-boot-starter-web
~~~

Expect to see the path `reactive-app → gateway-lib → spring-boot-starter-web → spring-webmvc`. Maven output must be read **from the actual command execution**; the example above is only a prediction based on the POM.

### 13.3. Run tests first — failing is intentional

~~~bash
mvn -pl reactive-app -am test
~~~

With the broken classpath, `ReactiveStackTests.inboundServerMustBeReactive` is expected to FAIL, while the HTTP GET test may pass. This demonstrates the regression bug: **the API still returns 200, yet the application type is wrong**.

If the test does not fail, check whether the web type is overridden via environment variables, a Maven profile, IDE arguments, or another file. Do not edit the assertion to make it pass.

### 13.4. Fix the exact dependency path in reactive-app/pom.xml

Replace **only** the `gateway-lib` dependency block with:

~~~xml
<dependency>
    <groupId>example</groupId>
    <artifactId>gateway-lib</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

This puts `<exclusions>` on the **consumer dependency path** without removing `gateway-lib`. `PartnerName.label()` still exists, so the business helper remains usable.

### 13.5. Re-run tests and dependency tree

~~~bash
mvn clean test
mvn -DskipTests install

mvn -pl reactive-app dependency:tree \
  -Dincludes=org.springframework:spring-webmvc
mvn -pl reactive-app dependency:tree \
  -Dincludes=org.springframework:spring-webflux
mvn -pl reactive-app -am package
~~~

After the exclusion, the app should have no `spring-webmvc` in its **runtime dependency tree** along that path; `spring-webflux` remains. Full-context tests must confirm a reactive web `ApplicationContext`.

### 13.6. Run the JAR and curl

~~~bash
java -jar reactive-app/target/reactive-app-0.0.1-SNAPSHOT.jar
~~~

In another terminal:

~~~bash
curl -i http://localhost:8080/stack
~~~

Expect 200 with `reactive:true` and `servlet:false`. Before the fix, the JAR normally runs Servlet/Tomcat and returns `servlet:true`. These are two outcomes of the **lab**, not a guarantee that every custom Spring Boot app classifies identically when overrides exist.

### 13.7. Inspect the packaged artifact

~~~bash
jar tf reactive-app/target/reactive-app-0.0.1-SNAPSHOT.jar
~~~

A Boot executable JAR stores dependencies under `BOOT-INF/lib`. Look for `spring-webflux` and verify whether `spring-webmvc` is gone. If an old/cached Docker image tag is run, the local tree looks fine while the runtime image still has MVC; use image digests/version metadata and check the context in the deployment itself.

## 14. Do Not Accidentally Exclude Required Libraries

An exclusion is not a "remove MVC everywhere" command. For example:

~~~text
reactive-app
    +-- gateway-lib -> spring-boot-starter-web   [excluded]
    +-- other-library -> spring-webmvc           [still present!]
    +-- spring-boot-starter-webflux
~~~

If `other-library` still pulls in an MVC indicator, Boot may continue selecting SERVLET. You must read **all paths** and address the root cause. A library that genuinely relies on Servlet filters/controller config or MVC classes will not automatically work in WebFlux simply by excluding dependencies: you may hit `ClassNotFoundException`, `NoClassDefFoundError`, or missing auto-configured features.

**Sustainable approach for shared libraries:** split into `gateway-core` (business/DTO/HTTP client), `gateway-mvc-adapter` (Servlet-specific), and `gateway-webflux-adapter` (reactive-specific) if needed. Core should not dictate a server framework for consumers. Maven exclusions can be a mitigation, but must be paired with regression tests and a plan to fix the upstream library.

## 15. BOM, dependencyManagement, and Scopes: Three Common Traps

The Spring Boot parent/BOM manages **versions**; it does not eliminate unwanted dependencies for you.

- A POM using the `spring-boot-dependencies` BOM can still pull in both `spring-webmvc` and `spring-webflux` if the graph declares both.
- `dependencyManagement` coordinates versions/scopes under Maven rules; it does not automatically exclude `starter-web`.
- Arbitrary version overrides of Spring Framework/Reactor/Jackson can cause `NoSuchMethodError` when Boot auto-config calls a different API.
- A compile-scoped library can show up at consumer runtime even if consumer code only calls one DTO.
- Test-scoped dependencies do not go into the packaged JAR, yet they can affect the test `ApplicationContext`.
- Gradle variant selection/`runtimeClasspath` differs from `compileClasspath`; always inspect the actual configuration.
- Application executable JARs and executable WARs/external containers load dependencies differently.
- `mvn dependency:analyze` may report libraries used via reflection, SPI, or Boot auto-config as "unused"; do not remove them blindly.

Keep versions managed by the Boot 3.3 BOM during the lab; for production, use a **security-supported Boot branch** per organization policy. This article is about **diagnosing Boot 3.3 semantics accurately**, not advice to stay on 3.3.13 forever.

## 16. Sometimes Having Both MVC and WebFlux Present Is Correct

An MVC app uses JDBC/JPA and a Servlet `SecurityFilterChain`, yet wants to call downstream HTTP services with the reactive `WebClient` API:

~~~text
Incoming HTTP client
     |
     v
Tomcat / DispatcherServlet / MVC Controller
     |
     +-- WebClient outbound -> HTTP partner
     |
     +-- JDBC / JPA (blocking)
~~~

Spring Boot prioritizing MVC in this case **matches the requirement**. Do not force `REACTIVE` just because you use `WebClient` or a few `Mono` return types. If you do not need reactive composition, Spring Framework 6.1 also provides the blocking `RestClient` API, which can be simpler for an MVC service.

**Rule of thumb:** which HTTP server accepts inbound requests is one decision; which HTTP client sends outbound requests is another. Do not treat the presence of WebFlux client classes as a bug in every MVC app.

### Verifying an MVC App Intending to Stay Servlet

~~~java
// Snippet in a @SpringBootTest of an MVC app:
assertTrue(context instanceof ServletWebServerApplicationContext);
~~~

When adding the WebFlux client dependency, this test should remain green. If the team truly wants to migrate the entire server to WebFlux, they must redesign filters/security/routing/I/O and verify every layer.

## 17. Overriding web-application-type: A Valid Tool, Not a Root-Cause Fix

When you want to force reactive:

~~~properties
spring.main.web-application-type=reactive
~~~

Or:

~~~java
// Alternative main method snippet; WebApplicationType import is required.
SpringApplication app = new SpringApplication(ReactiveApplication.class);
app.setWebApplicationType(WebApplicationType.REACTIVE);
app.run(args);
~~~

This override makes Boot choose a REACTIVE context even when MVC is on the classpath (provided configuration aligns). However:

- It does not remove `starter-web`/Tomcat/`spring-webmvc` JARs from the artifact.
- It does not convert a Servlet `Filter` into a `WebFilter`.
- It does not turn an MVC `HandlerInterceptor` into a reactive handler filter.
- It does not turn a `SecurityFilterChain` into a `SecurityWebFilterChain`.
- It does not convert blocking JDBC into a reactive driver.
- It can break a library that requires a Servlet `ApplicationContext`.
- It does not fix the library's transitive dependency design.

**Do not use a test override to mask a regression:**

~~~java
// Use this property only when production ALSO sets the corresponding property.
// If production does not force it, this test hides default classpath selection bugs.
@SpringBootTest(properties =
    "spring.main.web-application-type=reactive")
class ExplicitReactiveConfigTests {
}
~~~

If production intentionally overrides the type, tests must mirror deployment config and verify runtime thoroughly, while still reviewing the dependency graph. `@EnableWebFlux`/`@EnableWebMvc` are not replacements for `WebApplicationType`; they change framework customization/auto-config behavior and can introduce other issues.

## 18. The Wrong Stack Can Break Web/Security Boundaries

| Aspect to verify | MVC/SERVLET | WebFlux/REACTIVE |
|---|---|---|
| Dispatcher | `DispatcherServlet` | `DispatcherHandler` |
| Request filters | `jakarta.servlet.Filter` / `OncePerRequestFilter` | `WebFilter` / `WebFilterChain` |
| Security | `SecurityFilterChain` / `HttpSecurity` | `SecurityWebFilterChain` / `ServerHttpSecurity` |
| Handler intercept | `HandlerInterceptor` | WebFilter/reactive handler filters |
| Request abstraction | `HttpServletRequest` | `ServerWebExchange` |
| Test | `MockMvc` / `@WebMvcTest` | `WebTestClient` / `@WebFluxTest` |
| Async model | Servlet async, Callable/DeferredResult | Mono/Flux and reactive cancellation |
| Default server via starter | Tomcat | Reactor Netty |

A WebFlux `WebFilter` is not invoked in a Servlet filter chain. If the app unexpectedly runs MVC, authentication/authorization rules in a reactive Security chain **may not execute**; write negative tests for protected endpoints. Do not enable `permitAll()` as a temporary fix, and do not treat HTTP 200 as proof of security.

### Does Mono Mean a WebFlux Server?

No. MVC can adapt certain reactive controller return types:

~~~java
// Snippet that can be handled in either MVC or WebFlux:
@GetMapping("/hello")
Mono<String> hello() {
    return Mono.just("hello");
}
~~~

Returning 200 does not identify the stack. Assert the actual `ApplicationContext`, handler registration, and security filter chain.

## 19. Batch/CLI App Selecting the Wrong Web Type

A `CommandLineRunner` application without HTTP endpoints can inherit web dependencies from shared libraries and unexpectedly start a web server. Symptoms: the process does not exit as expected, or port 8080 collides with another service.

To declare the app **non-web**:

~~~properties
spring.main.web-application-type=none
~~~

Different from:

~~~properties
server.port=-1
~~~

`server.port=-1` can create a **web `ApplicationContext` without an HTTP listener**, whereas `spring.main.web-application-type=none` requests a non-web context. Use `NONE` for real CLI/batch apps and clean up unnecessary dependencies.

## 20. Library Upgrade Alters the Runtime Classpath

A common scenario:

~~~text
Before upgrade:
  shared-client v1 -> spring-web / client utilities only
  reactive-app -> starter-webflux
  result -> REACTIVE

After upgrade:
  shared-client v2 -> starter-web
  reactive-app -> starter-webflux + transitive starter-web
  result -> SERVLET (default)
~~~

Root-cause review steps:

1. Compare dependency trees between last-known-good and candidate.
2. Check direct/transitive scopes and Boot/BOM versions.
3. Read the published POM metadata/release notes of `shared-client`.
4. Check `ApplicationContext`/conditions report on the **exact versioned artifact**.
5. Check for config overrides in test/IDE/prod.
6. Add context/security/HTTP regression tests.
7. Fix the shared library or apply a narrow exclusion at the consumer; roll back the library version if needed.
8. Rebuild the executable JAR/image, canary deploy, and monitor 4xx/5xx, latency, and thread/Netty metrics.
9. Document the dependency contract and add a guard to prevent recurrence.

A library upgrade can alter **class loading and auto-config** without changing a single line of controller code. Reviewing the dependency graph is therefore part of reviewing behavior, not just licenses/security.

## 21. Classpath Differences Between CI, IDE, and Production

To avoid false conclusions:

- Test-scoped JARs are not packaged into an executable Boot JAR by default.
- IDE/run configurations may inject extra classpath entries/profiles/VM arguments.
- A custom `SpringApplicationBuilder` or environment variable can override the type unknown to local tests.
- Maven reactor dependency resolution and versions installed in `~/.m2` can differ when `-am` is omitted or builds are cached.
- Gradle `runtimeClasspath` differs from `testRuntimeClasspath`.
- WAR container-provided libraries can change the runtime graph and web server.
- A Docker image tag can be stale, still running an old artifact even after fixing the local POM.
- Shaded/fat JARs have a different dependency layout from standard Boot executable JARs.
- A library can arrive via **two paths**, so a single exclusion does not fully remove it.

Verify all three layers: **resolved dependency graph → packaged artifact → running ApplicationContext**. If they disagree, isolate the discrepancy in build/cache/profile/deployment before changing code.

## 22. Incident Runbook

When seeing unexpected startup/server types after a dependency upgrade:

1. Confirm the error and impact on users, security, request routing, and latency.
2. Capture the image digest, startup logs of the **running pod**, and active profiles.
3. Record the intended type (`SERVLET`/`REACTIVE`/`NONE`) and actual `ApplicationContext` type.
4. Print the runtime dependency tree for the exact commit/version.
5. Find the unexpected transitive path to `spring-webmvc` or `spring-webflux`.
6. Read the Conditions Evaluation Report, externalized properties, and programmatic web type overrides.
7. Test real HTTP endpoints/security; if there is a vulnerability or severe failure, roll back/isolate per procedure.
8. Diff the last-known-good vs. bad release dependency graphs.
9. Choose the fix: upstream library POM, targeted exclusion, right adapter module, or intentional override with tests.
10. Run JUnit full Boot integration tests, real HTTP, CORS/security, and load smoke tests.
11. Repackage, canary rollout, and monitor 5xx/latency/threads/security metrics.
12. Document the root cause, dependency path, regression guard, and owner responsible for cleaning up any temporary exclusion.

Do not make production changes outside authorized deploy/rollback workflows. This lab only operates on a local Maven project.

## 23. Common Anti-Patterns

| Anti-pattern | Why it is wrong | Right approach |
|---|---|---|
| "POM only lists webflux, so it must be REACTIVE." | Transitive `starter-web` may exist | Inspect the runtime dependency tree |
| "Having a reactor-netty JAR means the server is Netty." | It may only be the HTTP client connector | Assert `ApplicationContext` |
| "Returning Mono means the controller is WebFlux." | MVC has reactive adapters | Check `DispatcherHandler` vs `DispatcherServlet` |
| "WebClient turns MVC into a WebFlux server." | Outbound does not dictate inbound | Separate client vs server |
| Only changing `server.port` | Port does not determine web type | Fix the graph/override properly |
| Only adding `@EnableWebFlux` | Does not change web type deduction | Inspect classpath + Boot config |
| Deleting JARs from Maven cache | The build will re-resolve them | Exclude on the dependency path |
| Excluding `starter-web` when a library needs MVC | Runtime `ClassNotFoundException` | Split adapter / coordinate with library owner |
| Excluding one path while MVC remains on another | Exclusions are not global | Recheck the full runtime graph |
| Testing only HTTP 200 | The same `@RestController` runs on both stacks | Assert reactive/servlet context |
| `@WebFluxTest` passes => production is WebFlux | Slices do not prove real app type | `@SpringBootTest RANDOM_PORT` |
| Forcing reactive in tests but not in prod | Hides transitive regressions | Match actual config, guard default selection |
| Assuming BOM removes duplicate web starters | BOM manages versions | Practice dependency hygiene |
| Overriding all Spring dependencies | Invites version skew | Use Boot-managed versions |
| Disabling Security so the app boots | Masks runtime mismatch, exposes endpoints | Fix the Security chain for the right stack |
| Setting `server.port=-1` on a CLI app thinking it's NONE | Web context can still exist | `web-application-type=none` |
| Checking only the local tree | The image may contain an old artifact | Verify packaged/deployed runtime |

## 24. Post-Fix QA Matrix

| Check | Expected for a reactive-only service |
|---|---|
| `Context instanceof ReactiveWebServerApplicationContext` | true |
| `Context instanceof ServletWebServerApplicationContext` | false |
| Runtime tree contains `spring-webflux` | Yes |
| Runtime tree contains unwanted `spring-webmvc` | No |
| HTTP GET `/stack` | 200 + `reactive=true` |
| Library business helper | `gatewayContract=shared` |
| Reactive handlers/router functions | Mapped properly |
| Reactive `SecurityWebFilterChain` | Authentication/authorization work properly |
| Servlet `Filter` not confused with `WebFilter` | Correct |
| Error/CORS/CSRF policies | Tested through the reactive stack |
| Downstream `WebClient` | Executes properly, timeouts/cancellation work |
| Blocking I/O on event loop | None, or bounded offload |
| Test classpath vs `runtimeClasspath` | Distinguished |
| `BOOT-INF/lib` | No unexpected MVC JARs remaining |
| Docker image digest | Fresh, matching commit |
| Ingress/reverse proxy | Routes/security still honor contract |
| Latency/startup/resources | No regression |
| Rollback | Plan ready to revert to good release |

Key CI guard: **the context-type assertion test must fail if a library pulls MVC back in**, even if the HTTP controller still returns 200. Do not "fix" the test by removing the assertion.

## 25. Hands-On Exercises

**A.** Why can `gateway-lib` containing only a plain Java class change the server stack of `reactive-app`? Explain the transitive dependency path.

**B.** Run the Maven lab before applying the exclusion. Compare the outcomes of `inboundServerMustBeReactive` and `http200AloneDoesNotProveWebStack`. Explain why one passes and one fails.

**C.** Exclude `spring-boot-starter-web` at the consumer. Run the dependency tree and integration tests; state the evidence that the app switched to reactive.

**D.** Assume `other-library` also pulls in `spring-webmvc`. Is the exclusion on `gateway-lib` still enough? Design a plan to handle multiple paths.

**E.** Remove the exclusion, try `spring.main.web-application-type=reactive`, and compare the JAR dependencies. Distinguish a config override from a root-cause repair.

**F.** Build an MVC app using outbound `WebClient` and assert `SERVLET`. Explain why this is not a bug.

**G.** Create a `CommandLineRunner` CLI without web endpoints, use `web-application-type=none`, and compare it with `server.port=-1`.

**H.** Compare `shared-client` v1/v2, design a CI dependency guard, and explain why the shared library POM should be fixed rather than having every consumer add exclusions.

## 26. Review Questions with Answers

**1. Which stack does Boot 3.3 pick when both MVC and WebFlux are present?**  
By default, **SERVLET/MVC**.

**2. Does `WebClient` cause the incoming server to switch to Netty?**  
No. It is an outbound client API.

**3. A WebFlux `RouterFunction` does not work even though `spring-webflux` is present: what could be the cause?**  
Boot chose MVC because `spring-webmvc` is also on the runtime classpath.

**4. Which Maven command finds the path bringing `spring-webmvc` into runtime?**  
`mvn dependency:tree -Dincludes=org.springframework:spring-webmvc` along with the runtime tree.

**5. Which command does Gradle use?**  
`dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath`.

**6. Does a single exclusion remove a dependency from all paths?**  
No. Another path can still pull the artifact back in.

**7. Does seeing Tomcat in the startup log guarantee `SERVLET`?**  
It is a signal; the context type is decisive, because WebFlux can be configured to use Tomcat.

**8. Which property can force reactive?**  
`spring.main.web-application-type=reactive`.

**9. Does that property remove `spring-webmvc` from the artifact?**  
No. It only overrides the application web type.

**10. Does `@EnableWebFlux` replace Boot's `WebApplicationType`?**  
It is not a replacement switch; it affects framework configuration.

**11. Why is JUnit HTTP status 200 insufficient to identify the right stack?**  
`@RestController` works in both MVC and WebFlux.

**12. Why should you not force reactive in a regression test if production does not force it?**  
Because the test would mask the classpath regression you need to catch.

**13. Is an MVC app using `WebClient` wrong?**  
No. It is a valid use case.

**14. Does the BOM automatically exclude transitive `starter-web`?**  
No. The BOM manages dependency versions.

**15. Can a Servlet `SecurityFilterChain` replace a `SecurityWebFilterChain`?**  
No. The two stacks use different filter/security abstractions.

**16. What errors can excluding the wrong library cause?**  
`ClassNotFoundException`, missing beans/auto-config, or disabled features.

**17. Which web type should a batch app without an HTTP listener choose?**  
`NONE` if no web context is needed.

**18. Is `server.port=-1` the same as `web-application-type=none`?**  
No. One disables the HTTP listener; the other selects a non-web context.

**19. Why inspect the packaged JAR/container image?**  
Because the local dependency tree can differ from the actual deployed artifact.

**20. What is the sustainable way to prevent a client library from pulling in a Servlet server?**  
Separate core/client from the MVC adapter, manage the dependency contract, and add CI context/dependency guards.

## 27. Official Documentation

- [Spring Boot 3.3 – Reactive Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html): MVC takes precedence when both web and webflux are present.
- [Spring Boot 3.3 – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): detecting web application type and `@SpringBootTest`.
- [Spring Boot 3.3 – SpringApplication](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): web type/ApplicationContext/startup diagnostics.
- [Spring Boot 3.3 – Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): MVC/Servlet auto-configuration.
- [Spring Boot 3.3 – Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): Tomcat/Netty defaults, `web-application-type=none`, `server.port=-1`.
- [Spring Boot 3.3 – Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html): conditional classpath and conditions report.
- [Spring Boot 3.3 – Calling REST Services](https://docs.spring.io/spring-boot/3.3/reference/io/rest-client.html): `RestClient`/`WebClient` outbound APIs.
- [Spring Boot 3.3 – Gradle Managing Dependencies](https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html): BOM and version compatibility.
- [Maven – Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): transitive dependencies, exclusions/scopes.
- [Maven Dependency Plugin – dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): dependency paths.
- [Gradle – Viewing Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): `dependencyInsight` and `runtimeClasspath`.
- [Spring Framework – Spring Web MVC](https://docs.spring.io/spring-framework/reference/web/webmvc.html): `DispatcherServlet`/Servlet model.
- [Spring Framework – Spring WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): `DispatcherHandler`, `WebFilter`, and reactive model.
- [Spring Security – Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): `SecurityFilterChain`.
- [Spring Security – Reactive WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `SecurityWebFilterChain`.

**Conclusion:** The web stack must be proven by **resolved runtime dependencies + ApplicationContext + HTTP/security behavior**, not merely by the Maven starter name in the POM or a controller returning `Mono`. When a transitive library brings MVC into a reactive app, fix the exact dependency path, re-check the classpath, and keep tests that detect regressions.
