# Comparing the Same Program in NONE, SERVLET, and REACTIVE Modes in Spring Boot

Spring Boot can start the same set of Java code in three `WebApplicationType` modes: **`NONE`**, **`SERVLET`**, or **`REACTIVE`**. These three modes determine **the type of `ApplicationContext` and web infrastructure created**, rather than simply toggling an endpoint or renaming threads.

In this integrated practice lab, we **build a single Spring Boot project** without modifying `build.gradle` or source code between runs; we only change the `spring.main.web-application-type` configuration argument:

- **`NONE`:** Spring creates an application context without an embedded HTTP server; startup logic, dependency injection, runners, and bean lifecycle still work.
- **`SERVLET`:** Spring creates a servlet web application context, configuring Spring MVC and an embedded servlet server, typically **Tomcat** with the demo's dependencies.
- **`REACTIVE`:** Spring creates a reactive web application context, configuring Spring WebFlux and an embedded reactive web server, typically **Reactor Netty** with the demo's dependencies.

We will observe **the actual context type, conditionally created beans, HTTP serving capability, the Ready event, and context closing behavior**, and then use JUnit to automatically verify all three modes. The lab uses **Java 17+, Spring Boot 3.3.x, Spring Framework 6.1**. Statements below about Tomcat/Netty apply to **the demo project's classpath**, not as absolute definitions of SERVLET/REACTIVE.

## 1. Objectives and Target Results Table

After completing this lab, learners can:

1. Explain the differences between `WebApplicationType.NONE`, `SERVLET`, and `REACTIVE`.
2. Know how Spring Boot **infers the default mode from the classpath** and how to explicitly force a mode.
3. Identify the Spring `ApplicationContext` type inside the JVM instead of guessing from logs.
4. Distinguish between "having no HTTP server" and "having a server that does not open a port".
5. Use **the same `@RestController`** and observe endpoints in both SERVLET and REACTIVE.
6. Know that `ApplicationRunner` and lifecycle callbacks can run in **all three modes**.
7. Use `@ConditionalOnWebApplication` to configure beans that only apply to one web stack.
8. Understand implications for servlet filters, WebFlux filters, blocking I/O, testing, and production dependencies.

Reference table:

| Criterion | NONE | SERVLET | REACTIVE |
|---|---|---|---|
| WebApplicationType | `NONE` | `SERVLET` | `REACTIVE` |
| Typical ApplicationContext | `AnnotationConfigApplicationContext` | `AnnotationConfigServletWebServerApplicationContext` | `AnnotationConfigReactiveWebServerApplicationContext` |
| Embedded HTTP server | **Not created** | Yes | Yes |
| HTTP request handling configuration | No HTTP dispatch | Spring MVC/`DispatcherServlet` | Spring WebFlux/`DispatcherHandler` |
| Default server in demo | None | Tomcat | Reactor Netty |
| `@RestController` served automatically over HTTP? | No | Yes | Yes |
| `ApplicationRunner` | Can run | Can run | Can run |
| `ApplicationReadyEvent` | Can be published | Can be published | Can be published |
| Spring manages beans and `@PreDestroy` | Yes | Yes | Yes |
| Typical web thread model | No request workers | Servlet request threads | Event-loop/reactive callbacks |
| Suitable use cases | Batch, CLI, background worker | REST MVC, servlet stack | Reactive/non-blocking HTTP app |

The class names in the table are the typical types when Spring Boot uses its default context factory. Applications with a custom context factory configuration may create subclasses or different contexts; **do not check class names using hard-coded strings** when testing.

## 2. How Does Spring Boot Choose the Web Type?

`SpringApplication` determines `WebApplicationType` from the **classpath** if the application does not specify it explicitly:

~~~text
Spring MVC present?
   |
   +-- Yes -------------------> SERVLET
   |
   +-- No
         |
         +-- Spring WebFlux? -> REACTIVE
         |
         +-- No --------------> NONE
~~~

This is a simplified model of Boot's default policy for common starters:

- `spring-boot-starter-web` present → Spring MVC present → **SERVLET**.
- No MVC, but `spring-boot-starter-webflux` present → **REACTIVE**.
- Neither web framework present → typically **NONE**.
- **Both starters** present → **SERVLET takes precedence**, because many MVC applications add WebFlux to use `WebClient` without wanting to switch the server to WebFlux.

**Important:** *having Reactor on the classpath* is not enough to conclude the application is running REACTIVE. Likewise, merely seeing a Netty dependency does not mean the server is handling requests with Netty.

### How to Force a Mode

In `application.properties`:

~~~properties
spring.main.web-application-type=none
~~~

Or via startup arguments:

~~~bash
java -jar build/libs/three-modes-lab.jar \
  --spring.main.web-application-type=reactive
~~~

Or via the Java API before `run(...)`:

~~~java
SpringApplication application =
        new SpringApplication(ModeLabApplication.class);
application.setWebApplicationType(WebApplicationType.REACTIVE);
application.run(args);
~~~

The Java snippet is a **standalone API example** requiring the imports and `ModeLabApplication` class declared in section 4; the main program will **not hard-code** the mode so that it can be switched via CLI.

**Note:** do not force REACTIVE if the classpath lacks the appropriate WebFlux/server infrastructure, or force SERVLET when a servlet web server factory is missing. Choosing a `WebApplicationType` does not automatically download dependencies; missing configuration can cause context startup to fail.

## 3. At Which Layers Do the Three Modes Differ?

### NONE: Still Has Spring, but No HTTP Listener

With `NONE`, Boot typically creates `AnnotationConfigApplicationContext`. Parts that still work:

- `@Configuration`, `@Bean`, `@Component`, `@Service`, injection.
- `Environment`, configuration properties, profiles.
- `ApplicationRunner` and `CommandLineRunner`.
- `ApplicationStartedEvent`, `ApplicationReadyEvent`, and bean lifecycle.
- Datasource, HTTP **client**, message consumer, scheduled tasks, or executors **if declared/configured**, even without an HTTP server.

Parts **not** initialized by Boot as a web app:

- No application embedded HTTP server.
- No servlet request routing or WebFlux HTTP request routing.
- Cannot `curl http://localhost:8080/api/ping` into **this application**, unless you manually start a separate server outside auto-configuration.

**Do not confuse NONE with "the application cannot run anything".** A batch job `ApplicationRunner` can complete its entire business logic in NONE. For services consuming Kafka/Rabbit or running schedules, NONE can still stay alive long-term because background components keep the process alive.

### SERVLET: Spring MVC and Servlet Container

In SERVLET, Spring Boot uses a servlet web application context:

- Creates `ServletContext` infrastructure and an embedded servlet web server.
- Spring MVC typically dispatches requests through `DispatcherServlet`.
- Components such as `Filter`, `ServletRegistrationBean`, `HandlerInterceptor`, and `HttpServletRequest` belong to the servlet stack.
- The web starter in the demo pulls in **Tomcat**.
- MVC controllers are invoked under the servlet container's request handling model; for synchronous blocking code, a worker thread may be held for the duration of processing.

This **does not mean everything in a servlet app must be blocking**: Spring MVC supports async request processing and many reactive return adapters. However, the core request stack remains servlet/MVC.

### REACTIVE: Spring WebFlux and Reactive Server

In REACTIVE, Boot uses a reactive web application context:

- Creates Spring WebFlux's reactive HTTP handler chain.
- Annotated controllers can still use `@RestController`, `@GetMapping`; WebFlux uses `DispatcherHandler` instead of MVC's `DispatcherServlet`.
- Routing functions such as `RouterFunction<ServerResponse>` can be declared.
- The WebFlux starter in the demo pulls in Reactor Netty as the embedded server.
- Request/event processing typically uses **event loops** and reactive composition, targeting non-blocking I/O.

**Do not block an event-loop thread** with `Thread.sleep(...)`, long blocking JDBC, or calling `Mono.block()` inside a reactive request handler. A blocking I/O path does not magically become non-blocking just by enabling REACTIVE; if the client cannot be replaced yet, offload in a controlled manner to an appropriate scheduler and manage backpressure.

**REACTIVE does not mean Netty is always required.** Spring WebFlux can also run on certain compatible servlet containers when configured with the proper adapter/server. "REACTIVE" is a **web application stack** choice, while the server implementation is a separate factor.

## 4. A Single Project for All Three Modes

To make the comparison truly fair, keep **the exact same source code and classpath**. We intentionally declare **both** starters:

~~~text
three-modes-lab/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/modes/ModeLabApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/modes/ModeComparisonTest.java
~~~

### 4.1 build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}

springBoot {
    mainClass = 'com.example.modes.ModeLabApplication'
}

tasks.named('bootJar') {
    archiveFileName = 'three-modes-lab.jar'
}
~~~

In this project:

- `spring-boot-starter-web` brings Spring MVC and Tomcat by default dependency.
- `spring-boot-starter-webflux` brings WebFlux and Reactor Netty by default dependency.
- Both are baked into **the same JAR**.
- `spring-boot-starter-test` provides JUnit Jupiter and AssertJ for testing.
- The Java toolchain uses Java 17, compatible with Spring Boot 3.3.

**This configuration is for the comparison practice lab.** In production, you should usually **choose one primary web starter** to avoid unused dependencies and reduce maintenance complexity. A servlet app using `WebClient` can still keep the WebFlux starter, provided Boot's MVC precedence policy is understood.

### 4.2 application.properties

Create `src/main/resources/application.properties`:

~~~properties
spring.application.name=three-modes-lab
server.port=8080
spring.main.banner-mode=off
logging.level.root=WARN

# Do not set spring.main.web-application-type here.
# Each run will choose none / servlet / reactive via CLI.
~~~

No mode is set yet, because the practice lab requires switching via arguments **without editing the file**. The `server.port=8080` property only affects the **web server** created in SERVLET/REACTIVE; in NONE, it **does not start a server automatically**.

### 4.3 ModeLabApplication.java — complete file

Create `src/main/java/com/example/modes/ModeLabApplication.java`:

~~~java
package com.example.modes;

import org.springframework.beans.factory.DisposableBean;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.web.reactive.context.ReactiveWebServerApplicationContext;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.context.ApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ModeLabApplication {

    public static void main(String[] args) {
        // Do not hard-code WebApplicationType.
        // The --spring.main.web-application-type argument decides the mode.
        ConfigurableApplicationContext context =
                SpringApplication.run(ModeLabApplication.class, args);

        System.out.println("MAIN_RETURNED=true");

        // No HTTP server needed in NONE; proactively clean up context.
        // For SERVLET/REACTIVE, keep context/server alive for curl calls;
        // Spring Boot's JVM shutdown hook will close it on graceful shutdown.
        if ("NONE".equals(modeOf(context))) {
            context.close();
        }
    }

    static String modeOf(ApplicationContext context) {
        if (context instanceof ServletWebServerApplicationContext) {
            return "SERVLET";
        }
        if (context instanceof ReactiveWebServerApplicationContext) {
            return "REACTIVE";
        }
        return "NONE";
    }

    public record ModeMarker(String name) {
    }

    @Bean
    @ConditionalOnWebApplication(
            type = ConditionalOnWebApplication.Type.SERVLET)
    ModeMarker servletModeMarker() {
        return new ModeMarker("SERVLET");
    }

    @Bean
    @ConditionalOnWebApplication(
            type = ConditionalOnWebApplication.Type.REACTIVE)
    ModeMarker reactiveModeMarker() {
        return new ModeMarker("REACTIVE");
    }

    @Bean
    ApplicationRunner reportMode(
            ApplicationContext context,
            ObjectProvider<ModeMarker> markers) {

        return args -> {
            String mode = modeOf(context);
            ModeMarker marker = markers.getIfAvailable();

            System.out.println("MODE=" + mode);
            System.out.println("CONDITIONAL_MARKER="
                    + (marker == null ? "NONE" : marker.name()));
            System.out.println("HTTP_ENABLED="
                    + !"NONE".equals(mode));
        };
    }

    @Bean
    DisposableBean closeNotice() {
        return () -> System.out.println("CONTEXT_CLOSED=true");
    }

    @Component
    public static class ReadyNotice {

        @EventListener(ApplicationReadyEvent.class)
        public void ready() {
            System.out.println("READY_EVENT=true");
        }
    }

    @RestController
    public static class DemoController {

        private final ApplicationContext context;

        public DemoController(ApplicationContext context) {
            this.context = context;
        }

        @GetMapping(value = "/api/ping",
                produces = MediaType.TEXT_PLAIN_VALUE)
        public String ping() {
            return "pong";
        }

        @GetMapping(value = "/api/mode",
                produces = MediaType.TEXT_PLAIN_VALUE)
        public String currentMode() {
            return modeOf(context);
        }
    }
}
~~~

**Several intentional technical details in the example:**

1. `modeOf(...)` classifies by **the actual context type**, without relying on dependency presence on the classpath. Because both starters are present in every mode, checking the classpath would not distinguish the three runs.
2. Two `ModeMarker` beans are annotated with different `@ConditionalOnWebApplication` types. For a valid web mode, only the corresponding marker is created. For NONE, neither marker is created.
3. `ApplicationRunner` runs in all three modes and prints `MODE`, `CONDITIONAL_MARKER`, and `HTTP_ENABLED`.
4. `@RestController` uses **the same method and URL** for MVC and WebFlux. In NONE, the bean may still be created via component scanning, but **there is no HTTP mapping/server** to receive requests.
5. `@EventListener(ApplicationReadyEvent.class)` demonstrates that the Ready event is part of SpringApplication startup, **not strictly dependent on having an HTTP server**.
6. `DisposableBean` prints `CONTEXT_CLOSED=true` when the Spring context destroys beans along the normal close path. This cannot be guaranteed if the JVM receives SIGKILL.
7. In NONE, `main` closes the context after `SpringApplication.run(...)` returns. In both web modes, `main` finishes while the embedded server continues keeping the process alive to serve requests.

**There is no `Thread.sleep(...)`, database, or external API** in the controller. This keeps the comparison focused on startup context/HTTP stack rather than I/O noise. The `/api/mode` endpoint returns a short string that MVC and WebFlux can serialize consistently as `text/plain`.

## 5. Build Exactly Once

With JDK 17+ and the appropriate Gradle wrapper in the project:

~~~bash
./gradlew clean bootJar
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat clean bootJar
~~~

The artifact to run:

~~~text
build/libs/three-modes-lab.jar
~~~

If the project does not have a wrapper yet, set up Gradle or generate a compatible wrapper first. You cannot compile this Spring Boot application with a single `javac ModeLabApplication.java` command without putting the Spring libraries on the classpath.

**Comparison condition:** after building, **do not rebuild or change code** between the three trials. Only change `--spring.main.web-application-type` when launching that JAR.

## 6. Run 1 — Running in NONE Mode

Run in a terminal:

~~~bash
java -jar build/libs/three-modes-lab.jar \
    --spring.main.web-application-type=none
~~~

Lines **explicitly printed by the application code**, excluding Boot/JVM-specific logs:

~~~text
MODE=NONE
CONDITIONAL_MARKER=NONE
HTTP_ENABLED=false
READY_EVENT=true
MAIN_RETURNED=true
CONTEXT_CLOSED=true
~~~

Why do these lines appear?

1. `SpringApplication` selects a non-web application context.
2. No `@ConditionalOnWebApplication` marker matches.
3. `ApplicationRunner` is still invoked and prints the three properties.
4. `ApplicationReadyEvent` is still published when startup completes normally.
5. `main` receives the context, prints `MAIN_RETURNED`, and **explicitly calls `context.close()`**.
6. Spring destroys `DisposableBean` and prints `CONTEXT_CLOSED=true`.
7. No web server remains to keep the process alive; the program exits normally.

Do not infer "there is a Ready event so there must be an HTTP endpoint". `ApplicationReadyEvent` is not an HTTP response or a command to initialize network ports. In NONE, non-web services/beans can still operate normally.

**HTTP check:** if you try:

~~~bash
curl -i http://127.0.0.1:8080/api/ping
~~~

after running NONE, the connection will **not be served by this program**. If you still receive HTTP 200, another process may be listening on port 8080; inspect processes/ports instead of concluding NONE created a server.

**A CLI note:** `server.port=8080` in the configuration file **cannot enable a server** when `WebApplicationType.NONE` is active. Changing `--server.port=9090` also does not turn NONE into a servlet/reactive application.

## 7. Run 2 — Running in SERVLET Mode

Run in a separate terminal:

~~~bash
java -jar build/libs/three-modes-lab.jar \
    --spring.main.web-application-type=servlet
~~~

Lines printed by the program code when startup completes normally:

~~~text
MODE=SERVLET
CONDITIONAL_MARKER=SERVLET
HTTP_ENABLED=true
READY_EVENT=true
MAIN_RETURNED=true
~~~

**There is no `CONTEXT_CLOSED=true` yet** at this stage, because the context/server is running and waiting for requests. Other logs may include Tomcat startup messages; the example sets root logging to WARN to reduce noise, so **do not use the presence of a specific server log line as the sole measurement**.

From another terminal:

~~~bash
curl -i http://127.0.0.1:8080/api/ping
curl -i http://127.0.0.1:8080/api/mode
~~~

The two HTTP responses have bodies respectively:

~~~text
pong
~~~

and:

~~~text
SERVLET
~~~

HTTP headers such as `Content-Length`, `Date`, and `Connection` may vary by server/version; the `pong` and `SERVLET` bodies produced by the controller are what should be asserted.

**Processing flow:**

~~~text
TCP/HTTP client
       |
       v
Embedded Tomcat
       |
       v
Servlet filters / DispatcherServlet
       |
       v
Spring MVC handler mapping
       |
       v
DemoController.currentMode()
       |
       v
text/plain body: SERVLET
~~~

When pressing `Ctrl+C` in the terminal directly running the JVM on a typical Unix system (or sending SIGTERM to the right PID), Spring's shutdown hook has the chance to close the context. At that point the demo code prints:

~~~text
CONTEXT_CLOSED=true
~~~

This is the result of **a completed graceful shutdown path**. With a force kill/SIGKILL, destroy callbacks are not guaranteed.

## 8. Run 3 — Running in REACTIVE Mode

**Stop SERVLET before reusing port 8080**, or choose a different port to avoid conflicts.

Run:

~~~bash
java -jar build/libs/three-modes-lab.jar \
    --spring.main.web-application-type=reactive
~~~

Lines printed by the code at startup:

~~~text
MODE=REACTIVE
CONDITIONAL_MARKER=REACTIVE
HTTP_ENABLED=true
READY_EVENT=true
MAIN_RETURNED=true
~~~

Here, even though the JAR still contains Spring MVC and Tomcat classes, you forced Boot to use a **reactive application context**. With the demo's default dependencies, the HTTP server uses Reactor Netty.

Call the same endpoints:

~~~bash
curl -i http://127.0.0.1:8080/api/ping
curl -i http://127.0.0.1:8080/api/mode
~~~

The bodies are respectively:

~~~text
pong
~~~

and:

~~~text
REACTIVE
~~~

**Processing flow:**

~~~text
TCP/HTTP client
       |
       v
Reactor Netty (server)
       |
       v
Spring WebFlux HttpHandler / WebFilter chain
       |
       v
DispatcherHandler
       |
       v
DemoController.currentMode()
       |
       v
text/plain body: REACTIVE
~~~

**Same `@RestController`, different dispatcher.** `@GetMapping` is an annotation style supported in both MVC and WebFlux, so the controller source does not need to change. However, extensions of the two stacks **do not** share the same contract: Servlet `Filter`, `HttpServletRequest`, and MVC `HandlerInterceptor` do not automatically become `WebFilter` or `ServerWebExchange` in REACTIVE.

On graceful shutdown, the context is closed and the demo prints `CONTEXT_CLOSED=true` just like SERVLET. Context lifecycle is a shared concept, even when the web server and request processing model differ.

## 9. Why Do Both Web Modes Return the Same Body?

Key teaching point: **the controller's API contract does not necessarily change**, while the execution path at the framework layer differs:

~~~java
@GetMapping(value = "/api/ping",
        produces = MediaType.TEXT_PLAIN_VALUE)
public String ping() {
    return "pong";
}
~~~

The snippet above is the method from the project. Both MVC and WebFlux support annotation-based controllers. For a synchronous, lightweight method that simply returns `String`, the HTTP result can look identical.

**However, do not conclude from this that MVC and WebFlux are equivalent in everything**:

- MVC is built on the servlet stack; WebFlux organizes HTTP request handling via reactive types/handler chains.
- `@ExceptionHandler` and validation share similarities, yet error handling/filters/security stack configuration differs.
- Servlet request/session/thread-local context should not be used verbatim inside WebFlux event loops.
- `Mono`/`Flux` operators describe reactive processing flows; returning `Mono<String>` in Spring MVC can still be supported by adapters, so **looking solely at the return type is not enough to confirm the application type**.
- REACTIVE does not guarantee that every downstream API of the application is non-blocking; blocking JDBC/legacy SDKs still require dedicated design.

In the demo, `modeOf(context)` is a more reliable observation than "whether the endpoint responds", since both web stacks can serve that URL.

## 10. Comparing Conditionally Created Beans

Two factory methods in the demo:

~~~java
@Bean
@ConditionalOnWebApplication(
        type = ConditionalOnWebApplication.Type.SERVLET)
ModeMarker servletModeMarker() {
    return new ModeMarker("SERVLET");
}

@Bean
@ConditionalOnWebApplication(
        type = ConditionalOnWebApplication.Type.REACTIVE)
ModeMarker reactiveModeMarker() {
    return new ModeMarker("REACTIVE");
}
~~~

These conditions are evaluated during context construction, not when a request arrives. Hence:

| Mode | `servletModeMarker` | `reactiveModeMarker` |
|---|---|---|
| NONE | Absent | Absent |
| SERVLET | Present | Absent |
| REACTIVE | Absent | Present |

If a project needs a bean only for batch jobs, you can use an appropriate condition on a property/profile or a custom condition rather than trying to use `@ConditionalOnWebApplication` to represent "not web". Web-dependent conditions are a tool for auto-configuration and do not replace every kind of business condition.

**Do not confuse conditions with classpath presence:**

- `@ConditionalOnClass` asks: does the class exist on the classpath?
- `@ConditionalOnWebApplication(type=SERVLET)` asks: is this a servlet web application according to Boot's condition?
- With a JAR containing both MVC and WebFlux, a condition checking an MVC class will be **true in all three modes**, even though NONE does not create a servlet web context.

Thanks to the marker, the example proves the difference comes from **context type**, not "only SERVLET mode has the Spring MVC dependency".

## 11. JUnit Integration Test Running All Three Modes Without Modifying Source

The lab can be automatically verified using **a single test class** that launches each SpringApplication in its own context. Do not invoke `main()` so that the one-shot NONE cleanup logic does not close the context in a way tied to the CLI entrypoint; instead, test `SpringApplication.run(...)` directly and explicitly close each context.

Create `src/test/java/com/example/modes/ModeComparisonTest.java`:

~~~java
package com.example.modes;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.web.context.WebServerApplicationContext;
import org.springframework.boot.web.reactive.context.ReactiveWebServerApplicationContext;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

class ModeComparisonTest {

    @Test
    void noneStartsWithoutHttpServer() {
        try (ConfigurableApplicationContext context = start("none")) {
            assertThat(context)
                    .isNotInstanceOfAny(
                            ServletWebServerApplicationContext.class,
                            ReactiveWebServerApplicationContext.class);

            assertThat(context.getBeanProvider(
                    ModeLabApplication.ModeMarker.class)
                    .getIfAvailable()).isNull();

            assertThat(ModeLabApplication.modeOf(context))
                    .isEqualTo("NONE");
        }
    }

    @Test
    void servletStartsMvcHttpEndpoint() throws Exception {
        try (ConfigurableApplicationContext context = start("servlet")) {
            assertThat(context)
                    .isInstanceOf(ServletWebServerApplicationContext.class);

            assertThat(context.getBean(
                    ModeLabApplication.ModeMarker.class).name())
                    .isEqualTo("SERVLET");

            assertThat(get(context, "/api/ping"))
                    .isEqualTo("pong");
            assertThat(get(context, "/api/mode"))
                    .isEqualTo("SERVLET");
        }
    }

    @Test
    void reactiveStartsWebFluxHttpEndpoint() throws Exception {
        try (ConfigurableApplicationContext context = start("reactive")) {
            assertThat(context)
                    .isInstanceOf(ReactiveWebServerApplicationContext.class);

            assertThat(context.getBean(
                    ModeLabApplication.ModeMarker.class).name())
                    .isEqualTo("REACTIVE");

            assertThat(get(context, "/api/ping"))
                    .isEqualTo("pong");
            assertThat(get(context, "/api/mode"))
                    .isEqualTo("REACTIVE");
        }
    }

    private ConfigurableApplicationContext start(String mode) {
        SpringApplication application =
                new SpringApplication(ModeLabApplication.class);

        // Switch mode via CLI, just like running the JAR.
        // Port 0: OS assigns a free port, avoiding port 8080 conflicts.
        return application.run(
                "--spring.main.web-application-type=" + mode,
                "--server.port=0",
                "--logging.level.root=ERROR");
    }

    private String get(
            ConfigurableApplicationContext context, String path)
            throws Exception {

        int port = ((WebServerApplicationContext) context)
                .getWebServer().getPort();

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port + path))
                .GET()
                .build();

        HttpResponse<String> response =
                HttpClient.newHttpClient().send(
                        request,
                        HttpResponse.BodyHandlers.ofString(
                                StandardCharsets.UTF_8));

        assertThat(response.statusCode()).isEqualTo(200);
        return response.body();
    }
}
~~~

### Why Does This Test Accurately Verify All Three Modes?

1. Each test creates a fresh **SpringApplication**, passing its own mode via arguments.
2. Each test uses **the same `ModeLabApplication` class**, without changing the classpath.
3. `NONE` checks that there is no servlet/reactive web server context and no conditional marker.
4. `SERVLET` checks the servlet context, marker, and HTTP endpoints on an OS-assigned port.
5. `REACTIVE` checks the reactive context, marker, and **the same** HTTP endpoints.
6. `server.port=0` prevents port collisions. The test retrieves the actual port from `WebServerApplicationContext.getWebServer().getPort()`, rather than guessing 8080.
7. `try-with-resources` closes the context even when an assertion fails, preventing web servers from leaking across runs.
8. The test observes **actual behavior**, rather than just reading the `spring.main.web-application-type` property and assuming everything was configured properly.

Run:

~~~bash
./gradlew test
~~~

Expected result: **3 tests pass**, corresponding to `noneStartsWithoutHttpServer`, `servletStartsMvcHttpEndpoint`, and `reactiveStartsWebFluxHttpEndpoint`. Gradle may only print `BUILD SUCCESSFUL` and save detailed reports under `build/reports/tests/test/`; do not assert a fixed stdout string unless a test logger is configured.

**Note:** these are integration tests using real SpringApplication instances; they are slower than pure Java unit tests because they create/close contexts. Only a few smoke tests are needed to prove web modes; parsing/business logic should be tested separately without spinning up an entire server.

### How Does Testing with @SpringBootTest Differ?

When using `@SpringBootTest`, if both MVC and WebFlux are present, Boot usually selects servlet, even if you want to test WebFlux. To test reactive mode, you must specify the property explicitly:

~~~java
@SpringBootTest(
        properties = "spring.main.web-application-type=reactive",
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ReactiveModeSpringBootTest {
    // Verify ReactiveWebServerApplicationContext and HTTP endpoint.
}
~~~

This is an **illustrative skeleton**, not a standalone test class; imports and assertion methods are needed. For NONE, you can use `webEnvironment=NONE`, bearing in mind it explicitly selects a non-web test environment rather than exercising web defaults.

**Do not mix `MockMvc` and `WebTestClient` as if they always run on the same web stack**. `MockMvc` primarily tests Spring MVC; `WebTestClient` supports WebFlux and can also be used against a live server. Choose the right tool for the purpose and know whether the test spins up a servlet or reactive context.

## 12. Do Not Confuse Mode with Port or Selected HTTP Server

The three configurations below have **different meanings**:

~~~properties
spring.main.web-application-type=none
~~~

~~~properties
spring.main.web-application-type=servlet
server.port=0
~~~

~~~properties
spring.main.web-application-type=servlet
server.port=-1
~~~

- `NONE`: does not create a web ApplicationContext/server under normal auto-configuration.
- `SERVLET + server.port=0`: **has** a web server, with the OS picking an available port. This is a good choice for integration tests.
- `SERVLET + server.port=-1`: configures Boot's web server feature to disable HTTP endpoints while still keeping **the web ApplicationContext and related infrastructure**; not equivalent to NONE.

Furthermore, `server.port=0` does not mean "do not listen", it means "choose any available port". When testing, you cannot hard-code port 8080.

Switching to REACTIVE does not necessarily change the port; both servlet and reactive servers can serve port 8080 **if run sequentially**, or use different ports when running concurrently.

## 13. What Should Not Be Copied Verbatim Between SERVLET and REACTIVE?

A simple controller can be shared, but middleware/server APIs differ noticeably:

| Need | Servlet/MVC | Reactive/WebFlux |
|---|---|---|
| HTTP entry point | `DispatcherServlet` | `DispatcherHandler` |
| Per-request abstraction | `HttpServletRequest/Response` | `ServerWebExchange` |
| Filter | `jakarta.servlet.Filter`, `FilterRegistrationBean` | `org.springframework.web.server.WebFilter` |
| Interceptor | `HandlerInterceptor` | `WebFilter` or reactive handler infrastructure |
| Handler mapping | MVC `RequestMappingHandlerMapping` | WebFlux handler mappings |
| Security | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Error handling | Servlet/MVC exception resolver & error handling | Reactive error handler chain |
| Common HTTP client | `RestClient`, `RestTemplate`, or `WebClient` | Appropriate non-blocking `WebClient` |
| Blocking data access | Can typically use JDBC per thread-per-request | Avoid blocking event-loop; consider R2DBC/offloading |
| Request context | Servlet request attrs/thread-bound conventions | Reactive context propagation has different semantics |

A `Filter` bean defined in the same JAR does not automatically become a `WebFilter` when forcing REACTIVE. If you want to run all three modes in one app codebase, declare **separate configurations with appropriate conditions**.

### Do Not Think REACTIVE = "Faster at Everything"

An event loop suits many non-blocking I/O tasks, but:

- Heavy CPU-bound code still contends for CPU.
- Blocking JDBC/HTTP can stall the event loop if written improperly.
- Reactive publishers have their own backpressure and lifecycle, requiring proper understanding.
- Latency depends on workload, serialization, DB, network, and contention.
- A simple endpoint returning `String` is not a performance benchmark.

To compare throughput/latency, you need equivalent workloads, identical CPU/heap resources, warm-up, sample counts, and metrics on event-loop, queues, GC, and downstreams. Looking solely at the stack name is insufficient.

## 14. Lifecycle and Exit Behavior: NONE Can Exit Immediately, Web Modes Stay Alive Long-Term

In the example:

~~~text
NONE:
  SpringApplication.run(...)
      -> Runner
      -> Ready event
      -> return to main
      -> context.close()
      -> @Bean DisposableBean.destroy()
      -> JVM exits normally

SERVLET / REACTIVE:
  SpringApplication.run(...)
      -> Runner
      -> Ready event
      -> return to main
      -> HTTP server keeps process available
      -> Ctrl+C / SIGTERM
      -> Spring Boot shutdown hook closes context
      -> @Bean DisposableBean.destroy()
      -> JVM exits after shutdown
~~~

`ApplicationRunner` and `ApplicationReadyEvent` belong to the SpringApplication lifecycle, so they appear in both NONE and the two web modes. The major difference here is **whether an HTTP server is created and continues keeping the application alive to serve**.

**Do not assume every NONE app shuts itself down:** if there is a scheduler, a thread pool with non-daemon threads, a consumer, or an infinite loop, the JVM can still stay alive. The demo **explicitly closes the context**, avoiding letting another bean's lifecycle dictate when the program terminates.

**Do not assume every web app can keep closing its context indefinitely:** graceful shutdown has timeouts; in-flight tasks or external infrastructure can limit cleanup. The demo code does not guarantee callbacks run on a force kill.

## 15. Configuring Web Type via Java, Properties, and Command Line: Differences

There are three common configuration sources:

1. **Classpath inference** when nothing is specified.
2. **Spring configuration** via `spring.main.web-application-type` in properties/YAML or CLI.
3. **Java API** `SpringApplication.setWebApplicationType(...)` before run.

For this lab, only change the CLI:

~~~bash
java -jar build/libs/three-modes-lab.jar \
    --spring.main.web-application-type=none

java -jar build/libs/three-modes-lab.jar \
    --spring.main.web-application-type=servlet

java -jar build/libs/three-modes-lab.jar \
    --spring.main.web-application-type=reactive
~~~

Run **each command separately**, because servlet/reactive apps keep serving HTTP and will not return the shell prompt until stopped. If your Java setup **fixes** the mode via `setWebApplicationType(...)` or a custom application context factory, understand the precedence of configuration sources in your own app rather than assuming the CLI can always override every programmatic choice.

Do not add `application.setWebApplicationType(REACTIVE)` to the main demo and then pass `--spring.main.web-application-type=servlet` expecting the CLI to take effect unconditionally; the exercise intentionally **does not hard-code** it.

## 16. When to Choose Which Mode in Real Applications?

### Choose NONE

- CLI tools, migration runners, one-shot batch jobs.
- Background workers that do not receive HTTP requests.
- Scheduler tasks running in their own context.
- Integration tests needing only the DI/service layer, without HTTP.
- Spring config used as a library inside a larger process.

**Ensure:** you know who owns the context, when close is called, and whether any threads/consumers keep the JVM alive.

### Choose SERVLET

- REST APIs or MVC apps within the servlet ecosystem.
- Existing applications with many `Filter`s, servlet integrations, or synchronous blocking services.
- Integrating with blocking SDKs/JDBC with clear pools, timeouts, and concurrency limits.
- Organizations already stably operating Tomcat/Jetty/Undertow.

**Ensure:** thread pools, connection pools, and server shutdown are configured for load. Adding WebFlux to use `WebClient` is not necessarily a reason to migrate the entire server to REACTIVE.

### Choose REACTIVE

- High-concurrency I/O workloads that are predominantly non-blocking.
- Architectures already using Reactor, `Mono/Flux`, and reactive clients/drivers.
- Streaming, server-sent events, asynchronous request composition.
- Need to properly manage backpressure and reactive context.

**Ensure:** no long blocking I/O runs on event loops, monitor thread starvation, and use genuinely compatible clients/databases. A controller returning `Mono` does not automatically fix all blocking dependencies.

**All three can use Spring DI, configuration, event listeners, application runners, and lifecycle**. There is no single "best" mode for every application; the choice depends on **processing requirements, libraries in use, and load characteristics**.

## 17. Common Mistakes When Running the Lab

**Mistake 1 — "Adding spring-boot-starter-webflux makes the app automatically run REACTIVE."**

False if `spring-boot-starter-web` is also present: Boot typically prefers MVC/SERVLET by default. Force the mode via property if you truly want a WebFlux server.

**Mistake 2 — "NONE still serves controllers because @RestController is in the source."**

False. Controller beans may be scanned, but there is no web server/dispatcher to receive HTTP.

**Mistake 3 — "server.port=0 means NONE."**

False. Port 0 asks the OS to pick a random port for the created server.

**Mistake 4 — "server.port=-1 means no WebApplicationContext is created."**

False. In servlet mode, a web context can still exist without opening HTTP endpoints.

**Mistake 5 — "Having a Reactor Netty dependency means requests are running on Netty."**

Not necessarily. A project with both starters defaults to MVC/Tomcat unless reactive is forced.

**Mistake 6 — "SERVLET does not support async responses."**

False. MVC has async request APIs and adapters; it just differs from the reactive server model.

**Mistake 7 — "REACTIVE is always non-blocking even if the controller calls JDBC directly."**

False. Blocking calls still block the executing thread; this can negate event-loop benefits.

**Mistake 8 — "@ConditionalOnClass(WebFlux) is enough to detect REACTIVE mode."**

False in a project containing both starters. Use web application conditions or inspect the actual context.

**Mistake 9 — "If main() returns, the embedded server always disappears."**

Incorrect. The web server continues running under its lifecycle; the `main` method does not have to stay inside a loop.

**Mistake 10 — "ApplicationReadyEvent only exists in web apps."**

False. NONE still runs the SpringApplication lifecycle and can emit the Ready event.

**Mistake 11 — "Every time I run curl, it hits the newly started app."**

Not guaranteed. If an old process is still listening on port 8080, curl may hit that old process. Stop the old mode or use `server.port=0` and read the actual port when testing.

**Mistake 12 — "Same controller means MVC filters and WebFlux filters are identical."**

No. Servlet Filter/HttpServletRequest is not WebFilter/ServerWebExchange.

**Mistake 13 — "Just adding server.port chooses SERVLET or REACTIVE."**

False. Port is a server property; the mode is determined by `spring.main.web-application-type` and the classpath.

**Mistake 14 — "A default @SpringBootTest is testing WebFlux because WebClient is present."**

Not necessarily. When both MVC and WebFlux are present, it usually picks servlet. Specify reactive mode in the test or launch SpringApplication with an explicit property.

**Mistake 15 — "Forcing a mode lets any app run successfully even if starters are missing."**

No. Web modes require the appropriate framework and server factory; missing dependencies can cause bootstrapping to fail.

## 18. Extension Exercises

1. **Pass no mode**, run the JAR with both starters: verify whether it defaults to SERVLET. Explain why.
2. **Run NONE** and observe `ApplicationRunner`, `ApplicationReadyEvent`, `CONTEXT_CLOSED=true`. Explain why there is no port.
3. **Run SERVLET**, call `/api/mode`, prove the body is `SERVLET` and the corresponding marker bean is present.
4. **Run REACTIVE**, call the same route, prove the body is `REACTIVE`.
5. **Pass only `--server.port=9090`**, keeping servlet mode: does the endpoint change port, and does the context type change?
6. **Try `--server.port=0`** and inspect the web server/actual port logs; distinguish port 0 from having no server.
7. **Try `--server.port=-1`** in servlet mode, comparing web context creation and HTTP accessibility.
8. **Remove starter-web** from a **separate** build without forcing mode; verify WebFlux is inferred automatically when starter-webflux remains.
9. **Remove both web starters** from a **separate** build; verify Boot defaults to NONE when no other web stack exists.
10. **Create a conditional Servlet bean** for `Filter` and a conditional Reactive bean for `WebFilter`, verifying each mode creates only the appropriate bean.
11. **Add an endpoint returning Mono<String>**, test SERVLET and REACTIVE; explain why a reactive return type is not enough to identify context type.
12. **Add a CPU-bound service** and measure latency under light load on both web modes, without using a single request's result as a benchmark.
13. **Add blocking I/O** in REACTIVE and use thread dumps/metrics to observe the event loop; fix using a non-blocking API or bounded offloading.
14. **Try Spring Security**: compare `SecurityFilterChain` and `SecurityWebFilterChain`; do not use the same filter chain bean for both.
15. **Run the Gradle tests** for all three modes, verifying each test closes its context and causes no port conflicts.
16. **Attach `@PreDestroy` to a managed bean**, comparing cleanup when NONE closes itself versus when web modes receive SIGTERM.
17. **Try multiple ApplicationContexts in the same JVM**; ensure each created context is closed individually, without assuming closing one context closes all.
18. **Write a self-measured table** of startup time, thread counts, and heap usage; clearly state JVM/host/config, without fabricating benchmark results.

## 19. Self-Assessment Checklist

- **One** Gradle project and **one** JAR are used for all three trials.
- Mode is changed via `spring.main.web-application-type`, without accidentally changing code/classpath between runs.
- Know that **both MVC + WebFlux on classpath → defaults to SERVLET**.
- NONE creates a non-web ApplicationContext and does not create an embedded web server.
- SERVLET creates a servlet web context, handling requests via Spring MVC.
- REACTIVE creates a reactive web context, handling requests via Spring WebFlux.
- With the demo's dependencies, SERVLET uses Tomcat and REACTIVE uses Reactor Netty.
- `ApplicationRunner` and `ApplicationReadyEvent` are observed in all three modes.
- `@ConditionalOnWebApplication` controls beans by web stack, not merely by classpath.
- A simple controller returns the same API contract in both web modes.
- NONE does not serve HTTP even though the controller class exists in source code.
- `server.port=0/-1` does not mean choosing NONE.
- Tests retrieve the actual port from `WebServerApplicationContext` rather than relying on port 8080.
- Uncontrolled blocking I/O is not run on the WebFlux event loop.
- Cleanup and graceful shutdown have clear ownership in all three modes.
- Do not confuse a default `@SpringBootTest` with a reactive test when both starters are present.

### Official Documentation

- Spring Boot 3.3 — SpringApplication and Web Environment: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — Reactive Web Applications, MVC precedence when both starters are present: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- Spring Boot 3.3 — Embedded Web Servers and `server.port`: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Spring Boot 3.3 — Testing Spring Boot Applications, detecting web application type: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3 — `WebApplicationType` enum: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/WebApplicationType.html
- Spring Boot 3.3 — `WebServerApplicationContext` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/context/WebServerApplicationContext.html
- Spring Boot 3.3 — `ConditionalOnWebApplication`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnWebApplication.html
- Spring Framework — WebFlux reference: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Spring Framework — Spring MVC reference: https://docs.spring.io/spring-framework/reference/web/webmvc.html

**Conclusion:** `WebApplicationType.NONE`, `SERVLET`, and `REACTIVE` are **three distinct models for initializing the application context and web infrastructure**. With the same Spring Boot project containing the required dependencies, changing `spring.main.web-application-type` changes the context, server, and request dispatcher, while DI, runners, and lifecycle still remain. NONE suits running without an HTTP server; SERVLET typically uses Spring MVC/a servlet container; REACTIVE uses WebFlux/a reactive handler stack. Only assert which mode an application is running in after checking **the actual context and behavior** — do not rely on a single dependency, a thread name, or a single HTTP response.
