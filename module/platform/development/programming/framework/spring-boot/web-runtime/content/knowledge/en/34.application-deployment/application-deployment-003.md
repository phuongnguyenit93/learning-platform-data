# WebFlux Packaging and Deployment Limitations by Server and Version in Spring Boot

## 1. Objective: Distinguishing “Which Server WebFlux Runs On” from “How It Is Packaged and Deployed”

A team has a Spring WebFlux application running well on **Reactor Netty** via `java -jar`, but the operations environment requires submitting a `.war` file to drop into an **external Tomcat**. Someone argues: “WebFlux supports Tomcat, so switching to a WAR and deploying to Tomcat will definitely work.” That conclusion is **incorrect under the supported Spring Boot 3.3 deployment model**.

Four independent questions must be separated:

1. **Web programming model:** does the app use Spring MVC/Servlet or Spring WebFlux/reactive?
2. **HTTP server runtime:** does the WebFlux app run on Reactor Netty, Tomcat, Jetty, or Undertow?
3. **Application packaging:** executable JAR, Docker/OCI image, native executable, or traditional WAR?
4. **Version contract:** are Java/Jakarta Servlet API, Spring Boot/Spring Framework, and container/Netty versions compatible?

Foundational conclusions for Spring Boot 3.3:

- `spring-boot-starter-webflux` uses **embedded Reactor Netty** by default.
- You can **swap the embedded server** to Tomcat, Jetty, or Undertow via appropriate dependencies while keeping the WebFlux programming model.
- Spring Boot **does not support traditional WAR deployment for WebFlux applications**, even though the WebFlux framework has a servlet adapter and embedded WebFlux can run on Tomcat. If you want a `.war` deployed via `SpringBootServletInitializer` into an external servlet container, that is the path Boot documents for **Servlet/MVC applications**, not a WebFlux WAR recipe.
- **Executable JAR and container image** are the standard, Spring Boot-supported deployment paths for WebFlux applications.
- Different Boot versions have different Java/Jakarta and server requirements; **do not copy server configurations across Boot 2.7, 3.3, and 4.x without verifying**.

Examples and build instructions here use **Spring Boot 3.3.13, Spring Framework 6.1.x, Java 21, Gradle**; Java 17 is the minimum for the Spring Boot 3.3 branch. Mentions of Boot 2.7 or 4.x are only to highlight compatibility boundaries, not as drop-in replacement configs.

## 2. Four Layers to Keep Separate

```text
[Web programming model]
  Spring MVC                        Spring WebFlux
  DispatcherServlet                 HttpHandler / WebHandler
  Servlet handlers                  Reactive Streams / Publisher
           |                                     |
           v                                     v
[HTTP server runtime / embedded adapter]
  Tomcat / Jetty / Undertow          Reactor Netty (default)
                                     Tomcat / Jetty / Undertow
           |                                     |
           v                                     v
[Packaging and lifecycle]
  Executable JAR or traditional WAR  Executable JAR / OCI image / native
  Boot Servlet initializer          Boot starts embedded reactive server
           |                                     |
           v                                     v
[Platform / version]
  JDK, Servlet/Jakarta, HTTP/TLS     JDK, adapter, server, Netty
  server and deployment platform     native transports and dependencies
```

Do not conflate:

- “**Tomcat supports WebFlux**” with “**Boot WebFlux can deploy as a WAR on external Tomcat**”.
- “Adding `spring-webflux` to use `WebClient`” with “The app has switched entirely to WebFlux”.
- “Gradle builds a `.war`” with “That artifact has a **Spring Boot-supported deployment lifecycle**”.
- “A library has reactive in its name” with “The HTTP runtime is actually non-blocking end-to-end”.
- “Compiles on Java 21” with “Any old servlet container will accept Boot 3.3's Jakarta API/classpath”.

Decide **web stack → embedded server → artifact → target runtime/version** in order, then write smoke tests proving all four are right.

## 3. Selection Matrix for Spring Boot 3.3

| Need | Stack/server | Deployment artifact | Status/limitations |
| --- | --- | --- | --- |
| Standard WebFlux | WebFlux + embedded Reactor Netty | `bootJar`, OCI image | **Default recommended path** |
| WebFlux needing embedded Tomcat | WebFlux + Tomcat reactive adapter | `bootJar`, OCI image | **Supported**, must swap dependencies |
| WebFlux needing embedded Jetty | WebFlux + Jetty reactive adapter | `bootJar`, OCI image | **Supported**, must test server-specific features |
| WebFlux needing embedded Undertow | WebFlux + Undertow adapter | `bootJar`, OCI image | **Supported on Boot 3.3**, does not apply by default to Boot 4.x |
| Boot WebFlux and external Tomcat `.war` | WebFlux + traditional servlet WAR | WAR deployed to external container | **Not supported by Spring Boot** |
| Spring MVC on external Tomcat | Servlet/MVC + `SpringBootServletInitializer` | WAR | **Boot-supported model** when version/API match |
| WebFlux needing fast/small startup | WebFlux + compatible native image | Native executable/OCI | Can use AOT; many reflection/dynamic config limits |
| Only need a reactive HTTP client | MVC + `WebClient` | MVC JAR/WAR per stack | No need to convert entire app to WebFlux |

**Difference between “supported” and “possible”:** at the Spring Framework level, you can manually wire `HttpHandler` into a Servlet adapter and manage the lifecycle yourself. That does not make the traditional `.war` path supported by Spring Boot for a Boot WebFlux application. Avoid presenting a manual workaround as a product guarantee.

## 4. What Spring Framework Supports at the HTTP Adapter Layer

Spring WebFlux has a foundational abstraction:

```java
public interface HttpHandler {
    Mono<Void> handle(ServerHttpRequest request,
                      ServerHttpResponse response);
}
```

This is a **conceptual signature** of Spring WebFlux's `HttpHandler`, not a standalone Java file; imports reside in `org.springframework.http.server.reactive` and Reactor. Handlers/adapters convert server HTTP requests into `ServerHttpRequest` and `ServerHttpResponse`.

A simplified model:

```text
HTTP socket
    |
    +--> Reactor Netty server API
    |      -> ReactorHttpHandlerAdapter
    |
    +--> Tomcat Servlet non-blocking I/O
    |      -> Servlet HttpHandler adapter
    |
    +--> Jetty Servlet non-blocking I/O
    |      -> Servlet HttpHandler adapter
    |
    +--> Undertow server API
           -> UndertowHttpHandlerAdapter
                   |
                   v
              HttpHandler
                   |
                   v
            Spring WebFlux WebHandler
                   |
                   v
        HandlerMapping / HandlerAdapter
        WebFilter / codecs / controller
```

WebFlux `@RestController` code generally does not need to know whether the server is Reactor Netty or Jetty. However, behavior for HTTP/2, TLS, connection flow control, WebSocket, compression, thread model, shutdown, and request limits **is not guaranteed to be identical** because adapters and server implementations differ.

Spring Framework provides the abstraction, while **Spring Boot auto-configuration** chooses and manages the **embedded reactive server**. Those are two distinct support layers.

## 5. Reactor Netty: Default Server of `spring-boot-starter-webflux`

Gradle for a pure WebFlux app:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
```

The WebFlux starter pulls in `spring-boot-starter-reactor-netty` by default in Spring Boot 3.3. The server is typically a `NettyWebServer` instance created by Boot's `NettyReactiveWebServerFactory`.

Practical advantages:

- Spring Boot's default path, requiring less configuration for `WebFlux`.
- Non-blocking I/O based on Reactor Netty and an event-loop model.
- The Reactor Netty ecosystem provides connection pooling, timeouts, native transport options, and metrics when configured properly.
- Suited for high connection concurrency when handlers do not block the event loop and backpressure/limits are designed properly.
- Boot provides integrations for graceful shutdown, SSL, HTTP/2, compression, and Actuator per supported features/versions.

However, **Netty is not a Servlet container**. You cannot drop an executable Netty JAR into `webapps/` of an external Tomcat like a WAR Servlet app. Netty also does not automatically make an application non-blocking if resolvers/services call JDBC, `Thread.sleep`, or a synchronous HTTP client directly on the event loop.

**Do not confuse the `WebClient` runtime with the HTTP server runtime:** both may use Reactor Netty, but they are separate roles that can be configured to share or use different resources.

## 6. Tomcat: Embedded WebFlux Works, But It Does Not Become Spring MVC

When substituting `spring-boot-starter-tomcat` for Netty in WebFlux, Spring Boot runs a **reactive web application** on embedded Tomcat using the Servlet non-blocking I/O adapter. This is **not** converting a WebFlux `@GetMapping` into Spring MVC's `DispatcherServlet`.

| Aspect | WebFlux + embedded Tomcat | Spring MVC + embedded Tomcat |
| --- | --- | --- |
| HTTP stack | WebFlux | MVC |
| Handler abstraction | `HttpHandler`, WebFlux `WebHandler` | `DispatcherServlet`, `HandlerAdapter` |
| Controller return type | `Mono`, `Flux`, POJO | POJO, `ResponseEntity`, can support reactive types |
| Servlet API in business handlers? | Should not be used directly | Can be used per MVC design |
| Server transport | Tomcat non-blocking Servlet adapter | Tomcat Servlet request handling |
| Artifact | Boot executable JAR/OCI | Executable JAR or MVC WAR |
| Traditional WAR from Boot | Not supported for WebFlux | Supported with proper configuration |

Because WebFlux uses an adapter underneath the Servlet API, **do not attach Servlet `Filter`s or manipulate `HttpServletRequest` directly in WebFlux handlers** the way you would in Spring MVC. Use `WebFilter`, `ServerWebExchange`, reactive security, and WebFlux codecs.

Similarly, `TomcatServletWebServerFactory` is for Servlet applications; when choosing WebFlux with embedded Tomcat, the right factory belongs to the **reactive** group (`TomcatReactiveWebServerFactory`).

## 7. Jetty: An Embedded Reactive Server Alternative to Reactor Netty

Spring Boot 3.3 supports `spring-boot-starter-jetty` for WebFlux when replacing the Netty starter. Spring Framework uses Jetty's **Servlet non-blocking API** through the adapter to serve reactive pipelines.

Therefore:

- `Mono`/`Flux` controllers do not need to be rewritten just to switch to Jetty.
- You must verify that the Jetty version is compatible with the **Spring Boot BOM**, JDK, and Jakarta Servlet.
- TLS/ALPN, HTTP/2, WebSocket, timeouts, threading, headers, and compression must be tested against the real Jetty runtime.
- Do not apply Netty-specific examples like `LoopResources`, `HttpServer.create`, `reactor.netty.*` server metrics, or event-loop thread names to Jetty.
- Do not use `JettyServletWebServerFactory` in a reactive-specific customizer expecting the callback to affect the reactive server.

A “Jetty works” deployment requires real HTTP smoke tests and inspecting the artifact dependency graph. Netty libraries might still be on the classpath for an **HTTP client**, which is not proof that the embedded **HTTP server** is Netty.

## 8. Undertow: Supported in 3.3, But Adapter Characteristics Differ

Spring Boot 3.3 lists Undertow as an embedded server option for the reactive stack. When using Spring WebFlux + Undertow, Spring Framework uses an adapter built on **Undertow APIs** rather than relying on a Servlet adapter like Tomcat/Jetty.

This implies:

- Do not write a Servlet filter chain just because Undertow can run a Servlet stack in other contexts.
- Undertow-specific configs and server metrics differ from Reactor Netty.
- HTTP protocol features must be verified against the exact version and dependency tree.
- `undertow-servlet` classes may appear in some other applications' dependencies, but the WebFlux Undertow adapter should not be mistaken for a `DispatcherServlet`.

**Version boundary:** Spring Boot 4.1 documentation no longer lists Undertow among supported embedded servers in the same way as Boot 3.3. When upgrading, check the docs for **the exact target release** rather than assuming the starter/adapter remains supported. Do not force an older Undertow version into a new BOM just to make the app compile and call that a supported deployment.

## 9. Difference Between the Servlet Adapter and a Traditional WAR

The most common source of confusion:

```text
Case A — SUPPORTED:
  java -jar webflux-app.jar
        |
        v
  Spring Boot starts embedded Tomcat
        |
        v
  WebFlux HttpHandler via Servlet non-blocking adapter

Case B — NOT SUPPORTED BY BOOT:
  external-tomcat/webapps/webflux-app.war
        |
        v
  external Tomcat owns servlet lifecycle
        |
        v
  Expect SpringBootServletInitializer to bootstrap WebFlux
  as if it were a traditional MVC WAR
```

The **Spring Boot 3.3 Traditional Deployment** documentation explicitly states that WAR deployment **is not supported for WebFlux applications**. This remains true even though Tomcat is an **embedded** option for WebFlux.

`SpringBootServletInitializer` is a bridge for Spring Boot's traditional Servlet WAR model, not a trick to convert a `NettyReactiveWebServerFactory` into an external WAR. Adding the Gradle `war` plugin or generating a `.war` file on disk **does not prove** the artifact has a proper Boot WebFlux runtime in an external container.

If infrastructure strictly requires `.war` and forbids services from opening their own HTTP listeners, consider **Spring MVC WAR**, or change the deployment contract to run a WebFlux executable JAR/container. Do not choose a manual Servlet bridge unless the organization accepts building, maintaining, and testing the entire lifecycle outside Boot-supported WebFlux WAR scope.

## 10. Version Matrix: Java, Jakarta Servlet, and Servers Are Not Fixed Forever

Release documentation defines distinct compatibility boundaries:

| Branch | Minimum Java | Framework | Notable embedded servlet servers | Servlet namespace |
| --- | --- | --- | --- | --- |
| Spring Boot 2.7.18 | Java 8 | Spring Framework 5.3.x | Tomcat 9, Jetty 9.4/10, Undertow 2.x | `javax.servlet.*` |
| Spring Boot 3.3.13 | Java 17 | Spring Framework 6.1.x | Tomcat 10.1, Jetty 12, Undertow 2.3 | `jakarta.servlet.*` |
| Spring Boot 4.1.x | Java 17+ per system requirements | Spring Framework 7.x | Tomcat 11, Jetty 12.1 in current docs | Jakarta Servlet 6.1 |

These reflect **Boot capabilities and respective system requirements**, not that Spring WebFlux external WAR is supported in those versions. For Spring Boot 3.3.13, system requirements specify **Servlet 6.0** for embedded Tomcat 10.1/Jetty 12/Undertow 2.3, along with the ability to deploy **Servlet applications** to compatible Servlet 5.0+ containers. The “Servlet 5.0+” line **does not override the “WebFlux WAR not supported” notice** in traditional deployment docs.

In Boot 4.x, the server list and starter conventions change; for instance, Undertow is no longer listed as an embedded option in current docs. Therefore every major/minor upgrade must verify: **Boot BOM → Framework → servlet API → container → native/HTTP client library**. Do not change only the `org.springframework.boot` version number.

## 11. Why `javax.servlet` and `jakarta.servlet` Frequently Break Deployments

Starting with Spring Framework 6 / Spring Boot 3, the Servlet ecosystem moved to **Jakarta EE**:

```java
// Older Servlet app, Spring Boot 2.x family:
import javax.servlet.http.HttpServletRequest;

// Newer Servlet app, Spring Boot 3.x family:
import jakarta.servlet.http.HttpServletRequest;
```

These are **different** packages/classes and are not binary-compatible. A Boot 3 WAR cannot simply be dropped into Tomcat 9 (`javax.servlet`) expecting the Servlet API to translate automatically to Jakarta. Conversely, an older dependency still referencing `javax.servlet.*` can throw `ClassNotFoundException`/`NoClassDefFoundError` when the app uses the Jakarta stack.

With **WebFlux Reactor Netty**, business handlers should not depend on the Servlet API; however, some pulled-in authentication/filter/observability libraries can still bring the old API and cause classpath conflicts.

Verify `gradlew dependencies`/`dependencyInsight` before switching servers. Do not add both `javax.servlet-api` and `jakarta.servlet-api` to “fix” errors without knowing which library belongs to which version.

## 12. Use the Spring Boot BOM Instead of Pinning Individual Libraries

A consistent reactive classpath might look like:

```text
spring-boot-autoconfigure 3.3.x
spring-webflux 6.1.x
reactor-core 3.6.x
reactor-netty 1.1.x
netty 4.1.x
```

These are **illustrative branches**; exact patches are selected by the Spring Boot 3.3 BOM. Jetty/Tomcat/Undertow starters must also use the versions managed by the BOM.

Do not arbitrarily bump `reactor-netty-http` or Netty independently while keeping Boot 3.3 starters just for an advisory without evaluating compatibility; follow supported patches, dependency management, or a **thoroughly tested** override. In urgent security fixes, overrides require review and regression tests for HTTP/2, TLS, WebSocket, SSE, and connection pools.

Lock verified versions using lockfiles/SBOMs and artifact digests in the pipeline. Successful compilation does not guarantee zero binary incompatibilities at runtime.

## 13. Runnable WebFlux Project: Structure and Goal

This complete example lets you select the embedded server via Gradle property `-PwebServer=netty|tomcat|jetty|undertow` in **Spring Boot 3.3.13**. The entire app uses the same WebFlux controller; only the **server starter dependency** changes.

```text
build.gradle
src/main/java/com/example/reactivedeploy/
    ReactiveDeployApplication.java
    RuntimeController.java
src/main/resources/application.properties
src/test/java/com/example/reactivedeploy/
    ReactiveServerHttpTest.java
```

Requirements:

- JDK 21 and a Java 21-compatible Gradle Wrapper.
- Build dependencies accessible from Maven Central.
- `java -jar` only uses the executable `bootJar` output.
- Do not add `spring-boot-starter-web` to the runtime classpath of this example.
- Tests make real HTTP calls via `@SpringBootTest(RANDOM_PORT)`.

**Test goal:** verify two separate facts: (a) `ReactiveWebServerApplicationContext` is genuinely created, and (b) the HTTP server serves the endpoint over the network rather than relying on dependency names in source files.

## 14. `build.gradle`: Choosing an Embedded Reactive Server

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

def serverStarters = [
        netty: 'spring-boot-starter-reactor-netty',
        tomcat: 'spring-boot-starter-tomcat',
        jetty: 'spring-boot-starter-jetty',
        undertow: 'spring-boot-starter-undertow'
]

def chosenServer = providers.gradleProperty('webServer')
        .getOrElse('netty')

if (!serverStarters.containsKey(chosenServer)) {
    throw new GradleException(
            "webServer must be netty, tomcat, jetty or undertow")
}

dependencies {
    // Exclude default Netty server so two server factories are not selected.
    implementation('org.springframework.boot:spring-boot-starter-webflux') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-reactor-netty'
    }

    // Add the single chosen server starter.
    implementation "org.springframework.boot:${serverStarters[chosenServer]}"

    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
    systemProperty 'expectedWebServer', chosenServer
}
```

**How to read it:**

- When `-PwebServer` is omitted, the project uses `netty`.
- To pick Tomcat/Jetty/Undertow, e.g. `./gradlew -PwebServer=jetty test`.
- `exclude` removes WebFlux's transitive Netty **server starter** before selecting one server.
- Do not rely on `server.type=tomcat` or `spring.main.web-application-type` to automatically pull in Tomcat when the dependencies are absent.
- `systemProperty expectedWebServer` is only for test assertions; it is not a Spring Boot production property.

**Important note about WebClient:** Boot 3.3 docs note that `spring-boot-starter-reactor-netty` is needed for `WebClient` when using the default **Netty connector**. After removing the Netty server starter, check which HTTP client connector the project uses. `WebClient` is multi-connector, so if business code requires Reactor Netty `HttpClient` or Reactor Netty-specific options, configure the client dependency/connector separately and verify you do not accidentally create **two reactive server factories**. Do not “fix WebClient” by adding the full server starter back and bypassing server selection.

## 15. `ReactiveDeployApplication.java`

```java
package com.example.reactivedeploy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveDeployApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveDeployApplication.class, args);
    }
}
```

This is the Boot entrypoint for every embedded server option. **Do not extend `SpringBootServletInitializer`**, because this example targets **WebFlux executable deployment**, not a traditional WAR. Boot auto-configures `ReactiveWebServerApplicationContext` based on the classpath/runtime stack.

Do not manually register `DispatcherServlet` or create a `ServletRegistrationBean` in a WebFlux project just to get the app discovered. With WebFlux, use annotated controllers/functional routes and WebFlux infrastructure.

## 16. `RuntimeController.java`: Same HTTP Contract Across Four Servers

```java
package com.example.reactivedeploy;

import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
public class RuntimeController {

    @GetMapping(path = "/api/ping",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> ping() {
        return Mono.just("reactive-ok");
    }

    @GetMapping(path = "/api/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> events() {
        return Flux.range(1, 3)
                .delayElements(Duration.ofMillis(30))
                .map(n -> ServerSentEvent.<String>builder()
                        .event("tick")
                        .id(Integer.toString(n))
                        .data("tick-" + n)
                        .build());
    }
}
```

`GET /api/ping` returns the text `reactive-ok` and completes. `GET /api/events` emits three SSE events and completes so integration tests do not keep an infinite stream open.

- `Mono`/`Flux` are reactive values; they **do not by themselves prove** which non-blocking server handles the HTTP request—real context/server tests are needed.
- `ServerSentEvent` is Spring WebFlux's encoder contract; different servers must still return `text/event-stream`.
- `delayElements(30 ms)` makes the stream observable over time; it is not a timing guarantee for HTTP tests in CI environments.
- In production, SSE streams may stay open long-term; add cancellation cleanup, heartbeats/backpressure, and proxy idle timeout policies.

The same controller works on Netty/Tomcat/Jetty/Undertow on Boot 3.3 with the matching dependencies. Other features like WebSocket, TLS, and HTTP/2 require separate per-server integration tests.

## 17. `application.properties`: Port and Health Probes

```properties
# Runtime config: can be overridden via the PORT environment variable.
server.port=${PORT:8080}

# Expose only health; other management endpoints need their own policy.
management.endpoints.web.exposure.include=health
management.endpoint.health.probes.enabled=true

# Graceful shutdown for the executable runtime.
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

In tests, bind only local loopback via annotation properties. When running in Docker/Kubernetes, the app must bind an appropriate container interface address (not `127.0.0.1` if external host/pods need access via a published port).

Notes:

- `EXPOSE 8080` in a Dockerfile **does not automatically change `server.port`**; align configuration with published/container ports.
- Actuator readiness/liveness only help orchestration if probes are configured properly and the actual endpoints respond appropriately.
- `server.shutdown=graceful` coordinates stopping new request intake and closing the server per Spring Boot; for infinite SSE/WebSocket streams, **application-owned session cleanup** is needed rather than expecting shutdown to wait forever.
- If TLS is managed at ingress, distinguish direct server SSL from TLS termination at the proxy.

## 18. `ReactiveServerHttpTest.java`: Verifying the Real Server and Endpoints

```java
package com.example.reactivedeploy;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.boot.web.reactive.context.ReactiveWebServerApplicationContext;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "server.address=127.0.0.1")
class ReactiveServerHttpTest {

    private static final Map<String, String> SERVER_CLASSES = Map.of(
            "netty", "NettyWebServer",
            "tomcat", "TomcatWebServer",
            "jetty", "JettyWebServer",
            "undertow", "UndertowWebServer");

    @LocalServerPort
    int port;

    @Autowired
    ReactiveWebServerApplicationContext context;

    @Test
    void expectedEmbeddedServerWasSelected() {
        String expected = System.getProperty("expectedWebServer");
        assertThat(SERVER_CLASSES).containsKey(expected);
        assertThat(context.getWebServer().getPort()).isEqualTo(port);
        assertThat(context.getWebServer()
                .getClass().getSimpleName())
                .isEqualTo(SERVER_CLASSES.get(expected));
    }

    @Test
    void respondsOverARealHttpSocket() throws Exception {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build();

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port + "/api/ping"))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.body()).isEqualTo("reactive-ok");
        assertThat(response.headers().firstValue("content-type")
                .orElse(""))
                .contains("text/plain");
    }

    @Test
    void emitsFiniteServerSentEvents() throws Exception {
        HttpClient client = HttpClient.newHttpClient();

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port + "/api/events"))
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.headers().firstValue("content-type")
                .orElse(""))
                .contains("text/event-stream");
        assertThat(response.body()).contains(
                "data:tick-1", "data:tick-2", "data:tick-3");
    }
}
```

**Two-layer verification:**

- Injecting `ReactiveWebServerApplicationContext` fails if the application actually booted as a **Servlet MVC context**. Thus the test cannot be fooled merely by a controller returning `Mono`.
- `context.getWebServer().getClass().getSimpleName()` verifies the factory/server selected for each Gradle variant. The class name map is an **assertion tied to the Spring Boot 3.3 implementation**, appropriate for an intentional regression test, not a public SPI guaranteed across major versions.
- JDK 21 `HttpClient` sends real HTTP to the random port, not a mock environment.
- The SSE test checks HTTP content type/serialization, not just unit-testing `Flux` logic.
- This test **does not** prove TLS/HTTP2/WebSocket or proxy routing; add tests when those features are used.

The test code imports `java.net.http.*` from JDK 11+, avoiding adding a WebClient connector to the test classpath to call the endpoint. That avoids confusing a **Netty-backed WebClient** with verifying the **chosen HTTP server**.

## 19. Running the Server Matrix with Gradle and Reading Results Correctly

Run the options **one at a time**, because each Gradle invocation resolves a single dependency graph:

```bash
./gradlew clean test -PwebServer=netty
./gradlew clean test -PwebServer=tomcat
./gradlew clean test -PwebServer=jetty
./gradlew clean test -PwebServer=undertow
```

The `-P` flag is a Gradle project property, not a JVM option. If CI runs variants in parallel, use isolated build workspaces or coordinate task outputs instead of having multiple builds run `clean`/`build` into the same directory.

Expected result **when dependencies/runtime are compatible and loopback networking is available** is that tests PASS. Do not hardcode fixed stdout because Gradle logs, ports, and server startup messages vary.

To build the JAR:

```bash
./gradlew clean bootJar -PwebServer=netty
```

Gradle builds the executable artifact in `build/libs/`; the default name depends on project/Gradle settings. **Do not copy an assumed JAR name** when the project defines `archiveFileName`, classifiers, or multiple artifacts; use the actual output path of `bootJar`.

To run embedded Jetty:

```bash
./gradlew clean bootRun -PwebServer=jetty
```

Then:

```bash
curl -i http://127.0.0.1:8080/api/ping
curl -N http://127.0.0.1:8080/api/events
```

The `/api/ping` response body is:

```text
reactive-ok
```

SSE includes `id:`, `event:`, `data:` lines; payload order per `Flux.range` is `tick-1`, `tick-2`, `tick-3`, though line formatting/header timing depends on the HTTP client/server. Do not assert that Netty and Jetty emit the exact same startup log line or thread names.

## 20. Watch the Dependency Graph: Compiling Code Does Not Determine the Server

Inspect dependencies when switching servers:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency spring-boot-starter-reactor-netty \
  --configuration runtimeClasspath
```

Run with `-PwebServer=tomcat` or `jetty` as well to inspect the actual dependency graph; do not just look at `build.gradle` and assume. When multiple starters sit on the classpath, auto-config outcome and precedence may not match intent.

Review questions:

1. Are both `spring-boot-starter-web` and `spring-boot-starter-webflux` being pulled into runtime?
2. Is `spring-boot-starter-reactor-netty` coming from another dependency besides WebFlux?
3. Are there multiple `ReactiveWebServerFactory` beans?
4. Is `spring.main.web-application-type` overridden by a profile/environment?
5. Are there auto-configuration exclusions or custom server factories?
6. Is there a custom `WebClient` connector depending on Reactor Netty after changing servers?
7. Are Netty/Tomcat/Jetty/Undertow versions consistently managed by the BOM?

**Do not conclude from a starter name alone.** Smoke tests must verify the actual `ReactiveWebServerApplicationContext` and server class.

## 21. The `spring-boot-starter-web` + `spring-boot-starter-webflux` Trap

Misleading dependency example:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
```

When both MVC and WebFlux starters are on the runtime classpath, Spring Boot **normally prioritizes the Servlet web application type**. A controller returning `Mono<String>` does not prove the app is running WebFlux; Spring MVC also supports reactive return types.

If a project only wants `WebClient` inside an MVC service, having WebFlux libraries on the classpath **is not necessarily an error**, since `WebClient` is useful in MVC apps. However, if you truly need the HTTP server to be WebFlux, remove `spring-boot-starter-web` when unnecessary.

You can force it with:

```properties
spring.main.web-application-type=reactive
```

when there is an intentional reason to use the reactive web stack despite Servlet libraries being present. Still, this property **does not remove blocking Servlet filters, MVC-only auto-configurations, or dependency conflicts**, nor does it make a WebFlux WAR Boot-supported. Prefer cleaning up the dependency graph over relying long-term on this override.

## 22. Maven: Same Principle for Excluding and Swapping Server Starters

A `pom.xml` using the appropriate Boot parent/BOM for WebFlux + embedded Jetty can declare:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
        <exclusions>
            <exclusion>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-starter-reactor-netty</artifactId>
            </exclusion>
        </exclusions>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jetty</artifactId>
    </dependency>
</dependencies>
```

This is an **integration dependencies snippet**, not a standalone POM. You need the project's Maven coordinates, `spring-boot-starter-parent` or BOM import, Java/toolchain, and Maven plugin.

Similarly:

- Tomcat: `spring-boot-starter-tomcat`.
- Undertow on Boot 3.3: `spring-boot-starter-undertow`.
- Default Reactor Netty: omit the exclusions/Jetty starter and use the WebFlux starter normally.

Do not build a POM with **all 4 server starters at once** assuming Spring Boot will pick one via `application.properties`. Choose one server, or use explicit conditional build profiles/modules accompanied by smoke tests.

## 23. Executable JAR Packaging: How Boot WebFlux Is Commonly Deployed

With the Spring Boot Gradle plugin:

```bash
./gradlew clean bootJar
```

Conceptual structure of the executable JAR:

```text
META-INF/
BOOT-INF/
  classes/
    com/example/reactivedeploy/...
    application.properties
  lib/
    spring-webflux-...
    reactor-core-...
    <selected server dependencies>
org/springframework/boot/loader/...
```

Class/JAR dependency names are illustrative; the real artifact contains the Boot loader, nested JARs, and Gradle plugin metadata. You can inspect it:

```bash
jar tf build/libs/<actual-jar-name>.jar
```

`<actual-jar-name>` is a placeholder to replace with the generated filename, not a literal shell command.

To run:

```bash
java -jar build/libs/<actual-jar-name>.jar
```

`java -jar` activates the Spring Boot launcher to load nested dependencies; unlike `java -cp ordinary.jar com.example.Main` for an ordinary JAR. If the Gradle plain `jar` task is enabled, a **plain jar lacks runtime dependencies** and cannot run standalone; distinguish `jar`, `bootJar`, and `bootRun`.

To verify the selected server, check the dependency graph **and** HTTP runtime. Do not assume `jar tf` containing `reactor-netty` proves the HTTP server is Netty; the library could only be serving an outbound client.

## 24. Why `jar` and `war` Differ Beyond File Extensions

| Attribute | Executable Boot JAR | Traditional external WAR |
| --- | --- | --- |
| Server lifecycle | Application starts embedded server itself | External servlet container owns lifecycle |
| Launcher | Boot nested-jar launcher | Container deploy mechanism |
| Deployment | `java -jar`, Docker, orchestrator | Copy WAR to container/webapps or deploy API |
| App context startup | Boot `main`/auto-configuration | Servlet initialization bootstrap |
| Port/config | App's embedded server config | External server connector config |
| Reactive WebFlux Boot 3.3 | **Supported** | **Not supported** |
| MVC Boot 3.3 | Supported | Supported when configured properly |

For a Servlet/MVC WAR, `SpringBootServletInitializer`, the `war` plugin, and `providedRuntime`/`provided` scope make sense. Applying this exact recipe to WebFlux may produce an artifact, but it is not a **supported path**.

If an organization demands “WAR for a shared server runtime”, consider discussing switching the platform deployment model to a **container image running an executable JAR**, while standardizing ports, TLS, logs, deployment metadata, metrics, graceful shutdown, and autoscaling at the orchestration layer.

## 25. Framework-Level `ServletHttpHandlerAdapter` Does Not Become a Boot WAR

Spring WebFlux `HttpHandler` has an adapter for Servlet non-blocking I/O. At the framework layer, an application can manually register this adapter in a Servlet container in a custom integration.

```text
Custom external Servlet container integration
    |
    v
Servlet registration + async/non-blocking support
    |
    v
ServletHttpHandlerAdapter(HttpHandler)
    |
    v
WebFlux HttpHandler / WebHandler
```

However, when wiring it manually like this, the application itself must handle:

- Creating and closing the application context.
- Servlet initialization and async/non-blocking settings.
- Classloader boundaries and Jakarta Servlet version.
- Dependency scope, resource duplication, logging lifecycle.
- HTTP session/security/filter integration.
- Graceful shutdown, monitoring, startup failures.
- WebSocket/SSE support on each container.
- Testing across real target servers/versions.

This is **custom framework-level integration**, very different from Boot MVC's automatic `SpringBootServletInitializer` startup. Spring Boot 3.3 still explicitly documents that **WebFlux WAR is not supported**; do not use the framework adapter to rewrite that statement into “Boot WebFlux WAR is supported if Tomcat is new enough”.

## 26. When Should You Choose MVC WAR Instead of WebFlux?

If the deployment environment strictly provides only:

```text
Shared external Tomcat 10.1
  -> deploy .war only
  -> application must not own listener
  -> standard Servlet filters and container session
```

and the organization does not accept custom framework-level integration, the right choice is usually **Spring MVC WAR**. Evaluate blocking dependencies, security filters, servlet requirements, and test on the container version. Do not pick WebFlux under the assumption that “reactive is always faster”.

You can still use **`WebClient`** in an MVC app to call other HTTP services reactively as a client; that does not turn the whole web server into WebFlux. If the business genuinely needs a WebFlux non-blocking server, propose a **separate executable JAR/OCI runtime** instead of forcing it into a WAR.

Choose between WebFlux and MVC based on concurrency model, workloads, team, libraries, and measurements; choose the artifact based on the deployment platform. These two decisions are related, not identical.

## 27. OCI Container for WebFlux: Executable JAR Inside an Image

WebFlux does not need a WAR when running in Docker/Kubernetes. You can package an executable JAR and run a single Java process:

```dockerfile
FROM eclipse-temurin:21-jre

WORKDIR /app
COPY build/libs/reactivedeploy-0.0.1-SNAPSHOT.jar /app/app.jar

USER 10001:10001
EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

This is an **integration Dockerfile template**; the JAR filename must match the actual `bootJar` output. In production, pin the base image by digest, use security-patched images, and avoid requiring writable filesystems for the non-root process. Choose `linux/amd64`/`linux/arm64` per runtime and verify JDK/native dependencies accordingly.

Before building the image, produce the JAR for **one** server variant:

```bash
./gradlew clean bootJar -PwebServer=netty
docker build -t webflux-demo:local .
docker run --rm -p 8080:8080 webflux-demo:local
```

Then:

```bash
curl -i http://127.0.0.1:8080/api/ping
```

`EXPOSE` only records metadata, while `-p` publishes the port when running the container. `server.port=${PORT:8080}` must align with `containerPort` and service/ingress. Do not bind the server only to `127.0.0.1` **inside the container** if traffic needs to arrive from the host/pod network; container loopback is not host loopback.

## 28. Spring Boot Buildpacks: `bootBuildImage` Also Produces a Standalone Runtime

The Spring Boot Gradle plugin supports creating OCI images with buildpacks when the environment/container engine supports it:

```bash
./gradlew bootBuildImage --imageName=webflux-demo:local
```

This command is an illustrative workflow; it requires a Docker daemon/buildpack environment, registry access, and appropriate buildpack support. Buildpacks produce an image that runs the Boot app; they **do not** turn WebFlux into a WAR to copy into an external Tomcat.

If using runtime images generated by buildpacks, still check:

- Actual JDK/JRE version.
- Arch/OS/libc and matching Netty native transports.
- Selected HTTP server starter inside the artifact.
- Container user/permissions, layers, SBOM, and vulnerabilities.
- Startup probes, memory limits, and graceful termination.

Do not run `bootBuildImage` and assume build success is enough: smoke test HTTP requests, health, SSE/WebSocket if used, and the shutdown lifecycle of the real image.

## 29. GraalVM Native Image: Another Deployment Option, Not a WAR

Spring Boot 3.3 supports Spring AOT and GraalVM native images. A native executable often has faster startup and a smaller memory footprint than its JVM equivalent for many workloads, but carries **closed-world analysis** limitations:

- The bean graph and certain dynamic configurations must be determined at build time.
- Reflection, resources, dynamic proxies, and serialization may require hints.
- Not all runtime classpath/lazy class-loading capabilities of the JVM are available.
- Not every third-party library is native-image compatible.
- The native binary is OS/arch-dependent and must be built for the target platform.
- Container TLS, DNS, and Netty native transport dependencies must be tested in the actual native binary.

When using the Gradle native plugin:

```groovy
plugins {
    id 'org.graalvm.buildtools.native' version '0.10.6'
}
```

This is an **addition** to a `build.gradle` project with the Spring Boot plugin, not a standalone `build.gradle` file. A supported and configured GraalVM `native-image` toolchain is required. Build:

```bash
./gradlew nativeCompile
```

Native image output goes to `build/native/nativeCompile/` per the build plugin and actual settings. Run smoke/integration tests against the **deployed binary**, not only on JVM `bootRun`. AOT may change behavior of conditional beans/configuration; do not treat JVM test results as complete proof for a native build.

Native image supports WebFlux with compatible dependencies/configuration, and **does not change the traditional WebFlux WAR limitation**.

## 30. Platform Deployment: Ports, Readiness, Liveness, and Shutdown

In Kubernetes or similar platforms, an executable WebFlux service typically has:

```text
OCI image
  -> one Java/native process
  -> embedded HTTP server listening :8080
  -> Service / ingress routes requests
  -> readiness determines new traffic eligibility
  -> graceful shutdown/draining on termination
```

**Partial** container/probes manifest example:

```yaml
containers:
  - name: webflux-app
    image: registry.example.test/webflux-demo:release
    ports:
      - name: http
        containerPort: 8080
    readinessProbe:
      httpGet:
        path: /actuator/health/readiness
        port: http
      initialDelaySeconds: 2
      periodSeconds: 5
    livenessProbe:
      httpGet:
        path: /actuator/health/liveness
        port: http
      initialDelaySeconds: 5
      periodSeconds: 10
    terminationMessagePolicy: File
```

This is an **integration manifest snippet**, not a complete Deployment YAML. Configure Actuator health probes to actually be exposed, along with TLS/port mapping and application-appropriate `readiness` policies. `registry.example.test` is a placeholder; use a real image/version when deploying.

**Do not expose** an unauthenticated public business endpoint in production solely for readiness. Use network-restricted Actuator health groups with dedicated monitoring access controls.

Graceful shutdown is supported on embedded servers per Boot, though semantics for SSE, WebSocket, or long-lived connections vary by server/proxy. Do not expect all infinite streams to finish naturally before `terminationGracePeriodSeconds`; the application may need to proactively close subscriptions and release resources.

## 31. HTTP/2, TLS/ALPN, and Compression Differ Across Servers

When swapping Netty for Jetty/Tomcat/Undertow, controllers can still return `Mono<String>`, but HTTP server capabilities depend on the implementation:

| Feature | What to check |
| --- | --- |
| HTTP/1.1 | Routing, body/headers, keep-alive, timeouts |
| HTTP/2 TLS (`h2`) | TLS/ALPN, server version, JDK/provider/native libs |
| HTTP/2 cleartext (`h2c`) | Actually enabled and supported by proxy |
| HTTPS | Keystore/certificates, trust chain, SNI, cipher policy |
| Compression | `server.compression.*`, proxy buffering, and SSE |
| SSE | Flush timing, async lifecycle, proxy idle timeout |
| WebSocket | Upgrade handshake, auth, ping/pong, close handling |
| Large uploads | Max body/multipart limits, backpressure, buffer size |
| Graceful shutdown | In-flight streams, server shutdown policy |
| Metrics | Metric names and adapter-specific labels |

Example:

```properties
server.http2.enabled=true
server.compression.enabled=true
```

Properties enable features **when the HTTP server supports them and prerequisites are met**, rather than guaranteeing every server/proxy negotiates HTTP/2 identically. Use `curl --http2`/an appropriate HTTP/2 tool to verify the negotiated protocol, not just startup logs.

Similarly, do not assume a Reactor Netty-specific `HttpServer` customizer affects Tomcat/Jetty. Use `WebServerFactoryCustomizer` for the exact **reactive factory type** or server-specific API.

## 32. Native Netty Transports and OS Dependencies

Reactor Netty offers I/O transport choices (NIO, epoll on Linux, kqueue on macOS/BSD when applicable). Native transports or TLS providers like Netty `tcnative` can improve efficiency in some environments, but depend on platform/architecture and version.

Do not write deployment checklists saying “every Linux Netty instance requires epoll” or “without native libraries startup is guaranteed to fail”. Reactor Netty can fall back to Java NIO when native transport is unselected/unavailable, depending on config/dependencies/runtime.

When moving images from x86_64 to ARM64 or from glibc to musl, test:

- Native library classifier/availability.
- TLS/ALPN negotiation and supported ciphers.
- DNS resolver behavior.
- JVM architecture and JDK vendor.
- Container/seccomp permissions.
- HTTP/2/WebSocket/SSE behavior under real load.

A native image binary must also match the target OS/arch/libc. **JARs are more cross-platform than native binaries**, though internal native dependencies can still impose platform constraints.

## 33. HTTP Client Is Not the HTTP Server: Avoid Mistakenly Testing `WebClient`

In WebFlux:

```text
Spring WebFlux HTTP server:
  Reactor Netty / Tomcat / Jetty / Undertow

Outbound WebClient:
  ClientHttpConnector
  Reactor Netty HttpClient / Jetty client / JDK client / another supported adapter
```

The two roles can use different backends. Removing `spring-boot-starter-reactor-netty` to swap the server can affect the app's **default `WebClient` connector**. Conversely, keeping Netty **client libraries** does not prove the server is still Netty.

If a module uses `WebClient`, separate the tests:

1. **Server test:** `ReactiveWebServerApplicationContext` and a real HTTP socket verify which embedded server is running.
2. **Client test:** call a managed mock upstream/server, verifying TLS, timeouts, pooling, backpressure, and connector resource shutdown.
3. **End-to-end test:** verify both when `WebClient` calls a downstream service during a real request.

Do not manually close a global HTTP client connection provider or Reactor schedulers after each HTTP request completes. That can cause subtle failures, especially when client and server share resources under default Netty setups.

## 34. Thread Model and Blocking Code Remain Constraints Regardless of Server

WebFlux is a programming model based on Reactive Streams; scalability benefits depend on I/O and CPU steps being handled appropriately. Switching Reactor Netty to Tomcat does not turn synchronous JDBC or `Thread.sleep` into non-blocking calls.

Anti-pattern:

```java
@GetMapping("/api/slow")
public Mono<String> slow() {
    return Mono.fromSupplier(() -> legacyBlockingSdk.fetch());
}
```

This is an **integration illustration snippet** where `legacyBlockingSdk` is a hypothetical SDK; it is not standalone source. `Mono.fromSupplier` is lazy, but does not move blocking work onto a separate scheduler.

When forced to call a synchronous SDK:

```java
return Mono.fromCallable(() -> legacyBlockingSdk.fetch())
        .subscribeOn(Schedulers.boundedElastic());
```

This is also an integration snippet requiring Reactor `Schedulers`, the SDK bean, and timeout/concurrency limits. `boundedElastic()` has bounded threads/queues and does not cure a slow backend or an exhausted Hikari connection pool.

On Tomcat/Jetty non-blocking adapters, blocking callbacks can still tie up workers or stall I/O progression. On Reactor Netty, blocking the event loop can slow down many concurrent connections. **Do not treat swapping the HTTP server as a fix for blocking calls in business pipelines.**

## 35. Startup Failure Modes When Changing the WebFlux Server

| Symptom | Possible cause | Verification step |
| --- | --- | --- |
| `No qualifying bean of type ReactiveWebServerFactory` | Missing suitable embedded reactive server starter | Runtime dependency tree, Boot autoconfiguration |
| MVC `ServletWebServerApplicationContext` instead of reactive | `spring-boot-starter-web` present or web type overridden | Check classpath, `spring.main.web-application-type` |
| `ClassNotFoundException jakarta.servlet...` | Servlet API/server/library version mismatch | Boot BOM, Tomcat/Jetty versions, exclusions |
| `NoClassDefFoundError javax.servlet...` | Legacy Boot 2.x/Java EE library still in Boot 3.x | Upgrade dependency to Jakarta |
| Two server factory beans / startup conflict | Both Netty and Tomcat/Jetty server starters pulled in | `dependencyInsight` and factory beans |
| Netty-specific customizer has no effect | App switched to Jetty/Tomcat | Target the right reactive server factory |
| Endpoint 404 after switching servers | Different path/context/base-path/filter behavior | Real HTTP test, WebFlux route mapping |
| Outbound HTTP client fails after excluding Netty | `WebClient` connector/dependency affected | Configure `ClientHttpConnector`, test outbound separately |
| WAR artifact builds but fails on deploy | Boot WebFlux WAR unsupported | Choose JAR/OCI or MVC WAR |
| `UnsupportedClassVersionError` | Runtime JDK older than compile target | Java/toolchain version |
| Netty/Reactor `NoSuchMethodError` | Binary dependency version mismatch | BOM, dependency tree, locks |
| TLS/HTTP2 fails when swapping servers | Different ALPN/native/dependency/config | Server-specific HTTP2/TLS integration tests |
| SSE buffered/timed out | Different server/proxy flush/idle behavior | Streaming test through ingress |
| WebSocket handshake error | Upgrade/proxy/server feature mismatch | WebSocket test and headers |
| Native image fails on reflection/config | Missing reachability hints/AOT limits | Native tests/hints, supported dependencies |

**Do not “fix” this by adding all 4 HTTP server starters.** Pick one factory for the build/deployment and verify it with tests.

## 36. What to Consider When Upgrading from Boot 2.7 to 3.3

A Boot 2.7 project may have been running:

```text
Java 8 / Spring Framework 5.3
Tomcat 9 / Jetty 9/10 / Undertow 2.x
javax.servlet.* for Servlet components
Reactor/Netty versions managed by Boot 2.7
```

Moving to Boot 3.3:

```text
Java 17+ / Spring Framework 6.1
Tomcat 10.1 / Jetty 12 / Undertow 2.3 in embedded stack
jakarta.servlet.* for Servlet-related dependencies
Reactor Core 3.6.x / Reactor Netty 1.1.x via BOM
```

This is a **framework + runtime migration**, not just changing a single version property:

- Audit Jakarta migration for security/filter/session libraries.
- Update Spring Security configurations/APIs for compatibility.
- Check Reactor operators/backpressure behavior and Netty connection settings.
- Review codec defaults, Jackson versions, problem details, and error handling.
- Run real HTTP/SSE/WebSocket tests per server.
- If using custom `HttpHandler` or low-level server adapters, inspect API/SPI changes.
- Ensure JDK/toolchain versions match across build, test, and production.
- **Do not infer** from Boot 3's Servlet container requirements that WebFlux WAR is supported.

In particular, if you must keep an older external Tomcat 9, you cannot use a standard Boot 3.x Servlet WAR based on the Jakarta Servlet API and expect it to run on Tomcat 9. For WebFlux, the sound path remains a standalone executable server.

## 37. When Upgrading from Boot 3.3 to the 4.x Branch

Spring Boot 4.x changes Spring Framework versions, starter modules, server requirements, and Java/Servlet API baselines by release. Per **Boot 4.1** system requirements, embedded Servlet servers listed are **Tomcat 11 and Jetty 12.1**, differing from Boot 3.3 (**Tomcat 10.1, Jetty 12, Undertow 2.3**).

Upgrade procedure:

1. Pin the exact target Boot release and review that release's **System Requirements**.
2. Verify whether the server starter still exists/is supported; do not assume Undertow remains listed.
3. Confirm Jakarta Servlet version, Java version, and Gradle/Maven compatibility.
4. Read the release notes/migration guide for Boot/Framework/Netty/Reactor.
5. Generate the dependency graph and SBOM after upgrading.
6. Build the executable JAR/native image for the new release.
7. Run server selection tests and the HTTP protocol regression suite.
8. Measure latency, RSS, CPU, GC, connection pools, and shutdown before/after.

Do not copy `Gradle plugin version '3.3.13'` or `spring-boot-starter-undertow` from the examples into 4.1 assuming every build variant still works. **Every support claim must be tied to the version actually operated.**

## 38. CI Compatibility Matrix: What to Check Before Release

A solid pipeline should verify these cells:

| Axis | Variants tested | Mandatory check |
| --- | --- | --- |
| Boot version | Current release, upgrade target | Build + dependency tree + smoke test |
| Java runtime | Boot-supported JDKs | Compile target, startup, runtime tests |
| Server | Netty/Tomcat/Jetty/Undertow (per release) | Reactive context + server class + HTTP request |
| Packaging | Boot JAR, OCI, native if selected | Artifact runs and responds |
| HTTP protocol | HTTP/1, HTTP/2 when used | Negotiated protocol/TLS |
| Streaming | SSE, WebSocket when used | Events, cancellation, proxy, idle timeout |
| Security | Auth/CSRF/CORS/headers | Stack-appropriate integration tests |
| Shutdown | SIGTERM/drain | In-flight cleanup, readiness |
| Resources | Memory/CPU limits | Load tests, error rates, p99, GC |
| Upgrade | Old vs new | Contract regression, rollbacks |

You do not need an infinite full cross-product. Pick the servers/artifacts actually used in production; add a minimal smoke matrix to protect the server-swapping flexibility the docs allow.

To test an external servlet container—if the enterprise still has an MVC WAR—use a dedicated CI step deploying the WAR onto the **exact container version**. Never use “Netty bootJar test PASS” to imply “external Tomcat WAR test PASS”.

## 39. Decision Scenarios: Which Deployment Model to Pick?

**Scenario A — Cloud/Kubernetes with no external container constraint**

Pick default WebFlux + Reactor Netty as a Boot executable JAR/OCI. Configure health, metrics, TLS gateway, backpressure, rate limits, and shutdown. Swap servers only for a concrete reason (policy/security/feature/compatibility).

**Scenario B — Enterprise standardized on embedded Tomcat**

Use WebFlux + embedded Tomcat on Boot 3.3, swap the starter, and still deploy JAR/OCI. Run tests to ensure a reactive context and accurate HTTP behavior. Do not switch to an external WAR just because the server is named Tomcat.

**Scenario C — Shared external Tomcat requiring `.war`**

Spring Boot WebFlux WAR **is not supported**. Well-grounded options are a Spring MVC WAR on the supported path, or requesting an isolated runtime to deploy a WebFlux executable JAR. Do not promote a custom Servlet `HttpHandler` adapter as an out-of-the-box Boot feature.

**Scenario D — Jetty mandated in production**

Use the Jetty starter matching the Boot release, exclude the Netty server starter, and keep WebFlux controllers. Test Jetty TLS/HTTP2/WebSocket/proxy behavior and the client connector, not just the Gradle dependency change.

**Scenario E — Upgrading runtime to Boot 4.1**

Check the supported HTTP server list in the 4.1 docs. If currently using Undertow on Boot 3.3, plan to migrate servers or move to a supported option instead of overriding library versions and looking only at compilation.

**Scenario F — Serverless/scale-to-zero**

Consider a native image/short startup if the workload fits, but check AOT/third-party support, cold starts, probes, and timeout behavior. WebFlux does not eliminate platform request timeouts or connection lifetime caps.

## 40. A Small Java 17 Program to Separate Artifact Name from Runtime

The program below is **not Spring Boot** and does not inspect a real server; it illustrates why you cannot deduce a deployment contract from an artifact name alone. Use it purely to reinforce the mental model.

**`PackagingDecisionDemo.java`:**

```java
public class PackagingDecisionDemo {

    static String supportedPath(String stack, String artifact) {
        if ("webflux".equals(stack) && "war".equals(artifact)) {
            return "unsupported Boot WebFlux WAR";
        }
        if ("webflux".equals(stack) && "jar".equals(artifact)) {
            return "supported executable WebFlux";
        }
        if ("mvc".equals(stack) && "war".equals(artifact)) {
            return "supported MVC WAR with servlet setup";
        }
        return "check runtime and Boot version";
    }

    public static void main(String[] args) {
        System.out.println(supportedPath("webflux", "jar"));
        System.out.println(supportedPath("webflux", "war"));
        System.out.println(supportedPath("mvc", "war"));
    }
}
```

Run:

```bash
javac PackagingDecisionDemo.java
java PackagingDecisionDemo
```

**Exact stdout:**

```text
supported executable WebFlux
unsupported Boot WebFlux WAR
supported MVC WAR with servlet setup
```

This is a compact decision table encoding three **Spring Boot 3.3** cases for memory, not a runtime compatibility checker. For other Boot versions, server setups, native images, and deployment platforms, evaluate against official docs and actual integration tests.

## 41. Common Anti-Patterns to Avoid

1. **Seeing WebFlux run on Tomcat and concluding external WAR is Boot-supported.** Wrong: an embedded adapter differs from traditional WAR deployment.
2. **Merely renaming `.jar` to `.war`.** Does not provide the proper launcher/lifecycle/dependencies.
3. **Adding `SpringBootServletInitializer` to WebFlux and expecting it to deploy.** Does not turn an unsupported WAR path into a supported one.
4. **Adding `spring-boot-starter-web` to “use Tomcat WebFlux”.** Can switch the auto-detected stack to MVC.
5. **Forcing `spring.main.web-application-type=reactive` and ignoring dependency conflicts.** Overriding the type does not remove incompatibilities.
6. **Keeping two server starters assuming a property picks one.** Verify the actual reactive factory.
7. **Copying a Netty `HttpServer`/`LoopResources` customizer into a Jetty build.** Wrong HTTP server API layer.
8. **Assuming `WebClient` cannot work if the server is not Netty.** Client and server connectors are separate; configure/test the client properly.
9. **Assuming a non-blocking server makes JDBC non-blocking.** Blocking business I/O still must be managed.
10. **Using Tomcat 9 with a Boot 3.x Jakarta Servlet application.** Incompatible servlet namespace/API.
11. **Using Boot 3.3's Undertow starter on Boot 4.x without checking support.** Likely outside the release contract.
12. **Using the `jar` task instead of `bootJar` and expecting `java -jar` to load nested dependencies.** Needs the Boot executable artifact.
13. **Treating `EXPOSE 8080` as publishing the port.** Docker needs run/network mapping, and the server must bind the proper interface.
14. **Enabling HTTP/2 config and assuming TLS/ALPN succeeds on all servers.** Negotiated behavior must be tested.
15. **Treating a passing JVM test as a passing native-image test.** AOT/reflective resource restrictions differ.
16. **Ignoring proxy buffering for SSE and WebSocket idle timeouts.** Swapping servers can surface runtime bugs.
17. **Testing only ping without testing errors/cancellation/large bodies.** One 200 endpoint does not guarantee real workloads.
18. **Pinning Netty/Tomcat JAR versions outside the BOM without testing.** Easily causes binary incompatibilities.
19. **Using standard Tomcat access logs and accidentally logging secrets/paths/queries.** Requires an observability security policy.
20. **Relying on a single startup log line to prove server type.** Test `ReactiveWebServerApplicationContext` and actual HTTP requests.

## 42. Pre-Ship Checklist for a WebFlux Artifact

- [ ] Documented **Boot release**, Java runtime, Spring Framework, and dependency BOM.
- [ ] Confirmed HTTP stack is **WebFlux reactive** (not accidentally MVC).
- [ ] Selected **embedded server** proven via dependency tree and runtime test.
- [ ] Artifact is an executable `bootJar`/OCI/native on a supported path.
- [ ] Not claiming `.war` is a supported WebFlux deployment on Boot 3.3.
- [ ] Tomcat/Jetty/Undertow cross-checked against the **exact Boot version**.
- [ ] Distinguished external servlet containers from embedded servers.
- [ ] Checked `server.port`, `containerPort`, ingress, TLS, and readiness probes.
- [ ] HTTP/1.1 JSON, SSE/WebSocket, HTTP/2/TLS (if used) have regression tests on the target server.
- [ ] Outbound `WebClient` connector and connection pool still work after swapping servers.
- [ ] Blocking operations handled per concurrency/timeout policy, never blocking I/O loops.
- [ ] Graceful shutdown and per-connection cancellation cleanup tested.
- [ ] Logs/metrics/tracing do not leak tokens/cookies/PII.
- [ ] OCI/native image has the right platform architecture, security updates, and build reproducibility.
- [ ] Upgrade/downgrade and rollback plan measures p99, throughput, and error rate.

## 43. Review Questions and Hands-On Exercises

1. Why does “WebFlux has a Tomcat adapter” **not** prove WebFlux WAR is Boot-supported?
2. Which embedded HTTP server does Spring Boot 3.3 use when only `spring-boot-starter-webflux` is added?
3. Which starters replace Reactor Netty to use embedded Tomcat, Jetty, and Undertow?
4. At which layer does `HttpHandler` sit in WebFlux relative to the TCP socket and controllers?
5. How does Tomcat + WebFlux differ from Tomcat + Spring MVC even though both use Servlet-related infrastructure underneath?
6. Does WebFlux's Undertow adapter rely on the Servlet API like Tomcat?
7. If both `starter-web` and `starter-webflux` are on the runtime classpath, which stack does Boot usually select?
8. Does `spring.main.web-application-type=reactive` fix a classpath containing `javax.servlet.*` libraries?
9. When excluding `spring-boot-starter-reactor-netty`, what else must be checked for outbound `WebClient`?
10. How does Boot 2.7/Tomcat 9/`javax.servlet` differ from Boot 3.3/Tomcat 10.1/`jakarta.servlet`?
11. Why does the ability to deploy a Boot **Servlet** app onto Servlet 5.0+ not invalidate “WebFlux WAR unsupported”?
12. Do `bootJar`, `jar`, traditional WAR, and native image share the same launcher/lifecycle?
13. If running a Docker image with `EXPOSE 8080` while binding `127.0.0.1` inside the container, what happens to clients outside the container?
14. Why must SSE/WebSocket be tested through ingress/proxy rather than only a 200 HTTP ping?
15. From a `ReactiveWebServerApplicationContext` test, how do you confirm the actual server type?
16. Why should you use the BOM to align Reactor Core/Netty/Servlet server versions?
17. Does Boot 4.1 still list Undertow among supported embedded servlet servers?
18. What limitations does native image AOT impose on reflection/dynamic beans?
19. Does blocking JDBC inside WebFlux on embedded Jetty automatically become non-blocking?
20. If infrastructure mandates submitting a WAR while the product truly needs WebFlux, what are the two deployment options to discuss?

**Exercise A:** Run the project in sections 13–19 across all 4 `-PwebServer` variants. Record the dependency tree, server class, HTTP response, and SSE body. If a variant fails, classify whether it is a dependency/version or protocol/runtime error rather than forcing a pass.

**Exercise B:** Intentionally add `spring-boot-starter-web` to the project's runtime in a local test and observe the difference between Servlet/Reactive application contexts. Revert the dependency after the experiment.

**Exercise C:** Build `bootJar`, inspect `BOOT-INF/classes`/`BOOT-INF/lib`, run `java -jar`, then build a Docker image and hit the endpoint via `-p 8080:8080`. Distinguish JAR packaging from container runtime.

**Exercise D:** For a service running Boot 3.3 Undertow, write an upgrade checklist to Boot 4.1 based on the target release's system requirements and server support list. Do not try overriding the Undertow version while ignoring docs.

**Exercise E:** Given an external WAR requirement, compare Spring MVC WAR and a WebFlux executable image across lifecycle, traffic routing, auth/security, readiness, and rollback.

## 44. Conclusion

In Spring Boot 3.3, **WebFlux can run on multiple embedded HTTP servers**, but that **does not** mean every packaging/deployment mechanism is supported. Maintain the boundary:

```text
Spring WebFlux programming model
       |
       v
Spring Boot reactive server auto-configuration
       |
       +-- Reactor Netty (default)
       +-- Tomcat / Jetty / Undertow (embedded, Boot 3.3)
       |
       v
Executable JAR / OCI image / compatible native executable
       |
       v
Test real server, protocols, startup and shutdown

Traditional external WAR deployment of Boot WebFlux:
  NOT SUPPORTED in Boot 3.3
```

Choose your stack and server according to **the exact release**, use the BOM to manage versions, verify with real HTTP tests, and package according to a lifecycle supported by Spring Boot. If an organization mandates a WAR, clearly discuss **MVC WAR** versus **standalone WebFlux** rather than relying on the misconception that the shared name “Tomcat” makes every deployment model equivalent.

### Official References

- Spring Boot 3.3 — Embedded Web Servers; replacing Reactor Netty with Tomcat/Jetty/Undertow: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Spring Boot 3.3 — Traditional Deployment; note on WebFlux WAR not supported: https://docs.spring.io/spring-boot/3.3/how-to/deployment/traditional-deployment.html
- Spring Boot 3.3 — System Requirements (Java, Servlet containers, GraalVM): https://docs.spring.io/spring-boot/3.3/system-requirements.html
- Spring Boot 3.3 — Reactive Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- Spring Framework — WebFlux Overview, Servers and Thread Model: https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html
- Spring Framework — Reactive Core/HttpHandler/Server Adapters: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Boot 3.3 — Packaging Executable Archives/Gradle: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot 3.3 — Native Images/AOT Limitations: https://docs.spring.io/spring-boot/3.3/reference/packaging/native-image/introducing-graalvm-native-images.html
- Spring Boot 2.7.18 — System Requirements: https://docs.spring.io/spring-boot/docs/2.7.18/reference/html/getting-started.html
- Spring Boot 4.1 — System Requirements: https://docs.spring.io/spring-boot/4.1/system-requirements.html
- Project Reactor — Schedulers and Threading: https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html