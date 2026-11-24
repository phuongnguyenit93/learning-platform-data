# The Three `WebApplicationType` Modes in Spring Boot: `NONE`, `SERVLET`, and `REACTIVE`

## 1. What Problem Does `WebApplicationType` Solve?

A Spring Boot application can be a data-processing program that runs and exits, an HTTP service using Spring MVC, or an HTTP service using Spring WebFlux. All three can use dependency injection, `@SpringBootApplication`, configuration via `application.yml`, beans, lifecycle events, and `ApplicationRunner`. The major difference lies in the **type of web environment that `SpringApplication` creates at startup**.

`org.springframework.boot.WebApplicationType` is an enum with exactly three values:

- `NONE` — creates no web environment and starts no embedded HTTP server.
- `SERVLET` — creates a **Jakarta Servlet**-based web environment, typically paired with Spring MVC and embedded Tomcat.
- `REACTIVE` — creates a **Spring WebFlux**-based web environment, typically paired with Reactor Netty.

This is an **application-level choice at startup**. It affects the `ApplicationContext` type, web-related auto-configuration branches, HTTP request-receiving infrastructure, and the corresponding request handler. It does **not** directly indicate how many threads the application has, whether Reactor is used in every method, or whether a given method is actually non-blocking.

Memorable examples:

- A tool that exports a report from a database at 2:00 AM: needs Spring for configuration and bean organization, does not need to receive HTTP requests → usually `NONE`.
- A REST API returning data from JPA/JDBC with the Spring MVC model → usually `SERVLET`.
- A gateway/streaming service with end-to-end asynchronous I/O using WebFlux/Reactor → usually `REACTIVE`.

Choosing the right type lets Boot build the right "runtime skeleton" for the application, avoiding unnecessary web server startup and avoiding confusion between the two HTTP processing models.

## 2. Map of the Three Types and Their Accompanying Components

| Aspect | `NONE` | `SERVLET` | `REACTIVE` |
| --- | --- | --- | --- |
| Embedded HTTP web server by default? | No | Yes, when a suitable server factory is present | Yes, when a suitable reactive server factory is present |
| Context type typically created by Boot | `AnnotationConfigApplicationContext` | `AnnotationConfigServletWebServerApplicationContext` | `AnnotationConfigReactiveWebServerApplicationContext` |
| Typical HTTP stack | None | Spring MVC, `DispatcherServlet` | Spring WebFlux, `DispatcherHandler` |
| Common starter | `spring-boot-starter` | `spring-boot-starter-web` | `spring-boot-starter-webflux` |
| Default HTTP server per starter in Spring Boot 3.3 | None | Tomcat | Reactor Netty |
| Typical programming model | `CommandLineRunner`, `ApplicationRunner`, jobs, consumers | `@RestController`, Spring MVC, Servlet filters | `@RestController` + `Mono`/`Flux`, router functions, `WebFilter` |
| Typical scenarios | CLI, batch, scheduled workers | CRUD REST, MVC, traditional backends | Streaming, non-blocking I/O, reactive pipelines |

The context class names in the table are Spring Boot's **usual defaults**, not a guarantee that every application using a custom context factory will have that exact class. `ApplicationContextFactory` can be replaced when specialized requirements exist.

**Distinction to keep clear:** `WebApplicationType` selects the **application model**; Tomcat, Jetty, Undertow, and Reactor Netty are **HTTP server implementations**. Do not equate "`REACTIVE` = mandatory Netty" or "`SERVLET` = Tomcat only". WebFlux can also run on compatible Servlet containers.

```text
                        SpringApplication
                               |
                    determine WebApplicationType
                               |
           +-------------------+-------------------+
           |                   |                   |
         NONE                SERVLET             REACTIVE
           |                   |                   |
 ApplicationContext    ServletWebServer       ReactiveWebServer
 without web server    ApplicationContext     ApplicationContext
           |                   |                   |
   runner / batch /      Servlet container       Reactive server
   job / consumer         + Spring MVC            + Spring WebFlux
                               |                   |
                       DispatcherServlet      DispatcherHandler
                               |                   |
                           HTTP endpoint       HTTP endpoint
```

## 3. `NONE`: Spring Boot Without a Web Environment

### 3.1. The Program Is Still a Spring Boot Application

With `NONE`, Boot still loads configuration, applies matching auto-configurations, creates beans, injects dependencies, and invokes lifecycle callbacks and `ApplicationRunner`/`CommandLineRunner` beans. The difference is that Boot **does not build a web application context or an embedded HTTP server to accept requests**.

This fits:

- A CLI that performs a business task and returns an exit code to the OS.
- Batch/ETL jobs that read data, process it, and write to a destination.
- Migration tools or internal administrative utilities.
- Workers consuming events from a queue without needing an HTTP endpoint.
- Scheduled applications running on a schedule and requiring no web port.

A `NONE` application **does not necessarily exit immediately**: if a scheduler, listener, non-daemon thread, or background infrastructure remains active, the JVM may keep running. Conversely, if only runners execute and finish with no thread keeping the process alive, the JVM may terminate. You must define the job's termination policy, exit code, and resource cleanup yourself.

### 3.2. How to Select `NONE`

When you want to force the program not to start a web server even though web libraries are on the classpath:

```properties
# src/main/resources/application.properties
spring.main.web-application-type=none
```

Or in YAML:

```yaml
spring:
  main:
    web-application-type: none
```

Or configure via Java before running:

```java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setWebApplicationType(WebApplicationType.NONE);
app.run(args);
```

The Java snippet above is an **illustration inside the `main` method** of a Spring Boot application and requires importing `SpringApplication` and `WebApplicationType`. It is not a standalone file if placed outside a class.

When using `NONE`, do not expect `@RestController`, `@GetMapping`, or Actuator HTTP endpoints to work merely because the corresponding beans or dependencies exist. To expose an HTTP health endpoint, redesign the web requirement or choose the appropriate web type.

### 3.3. `NONE` vs. `server.port=-1`

The two settings look similar in that neither serves HTTP from an application port, but their purposes differ:

- `spring.main.web-application-type=none`: **creates no web environment**; does not start an embedded HTTP server.
- `server.port=-1` in a web application: Boot still creates a **web application context**, but does not open the usual HTTP endpoint. Certain tests or setups that need to keep the web environment without accepting traffic may use this approach.

Use `NONE` when the program is inherently not a web application. Do not substitute the two options mechanically, because the context type and auto-configuration branches differ.

## 4. `SERVLET`: Spring MVC Web Application

### 4.1. Path of an HTTP Request

`SERVLET` builds an environment based on the Jakarta Servlet API. With `spring-boot-starter-web`, the most common setup is Spring MVC running on embedded Tomcat.

```text
HTTP client
    |
Embedded Servlet container (e.g., Tomcat)
    |
Servlet Filter chain
    |
DispatcherServlet (Spring MVC)
    |
HandlerMapping -> Controller / HandlerAdapter
    |
Service -> Repository / other systems
    |
HTTP response
```

A `@RestController` with a `@GetMapping` method is normally registered by Spring MVC and served via `DispatcherServlet`; in `NONE` mode, this same request path does not exist.

Spring MVC's common model handles requests on Servlet container threads. Synchronous APIs such as JDBC/JPA or blocking HTTP clients integrate naturally with this model. Spring MVC also supports asynchronous processing via `Callable`, `DeferredResult`, and certain reactive return types; therefore **`SERVLET` does not mean every operation must be synchronous**.

### 4.2. Minimal Configuration and Default Server

In a Boot 3.3 project that already has the plugin and dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

This starter brings in Spring MVC and Tomcat by default. You can replace Tomcat with Jetty or Undertow by excluding the corresponding dependency and adding the appropriate server starter. Switching Tomcat to Jetty **does not turn** `WebApplicationType.SERVLET` into `REACTIVE`.

Under default classpath detection, when Spring MVC is present, Boot chooses a servlet environment. You can specify it explicitly:

```properties
spring.main.web-application-type=servlet
server.port=8080
```

Usually you do not need the first line if the project only uses `spring-boot-starter-web`. If a suitable embedded servlet server factory is missing while `SERVLET` is forced, startup can fail; setting the enum does not automatically download missing server libraries.

### 4.3. When to Choose Servlet?

Suitable for CRUD REST, server-rendered MVC, APIs relying heavily on blocking libraries, most applications using JPA/JDBC, Servlet-based Spring Security filter chains, and integrations built around the request/thread model. There is no rule that "Servlet cannot scale": system capacity also depends on databases, pooling, caching, architecture, and operations.

## 5. `REACTIVE`: Spring WebFlux Web Application

### 5.1. Request Processing Path

`REACTIVE` builds a web environment based on Spring WebFlux. With `spring-boot-starter-webflux`, Boot 3.3 typically uses Reactor Netty as the embedded server. WebFlux's central dispatcher is `DispatcherHandler`.

```text
HTTP client
    |
Reactive HTTP server (typically Reactor Netty)
    |
WebFilter chain
    |
DispatcherHandler (Spring WebFlux)
    |
Annotated controller / RouterFunction
    |
Publisher: Mono<T> / Flux<T>
    |
Reactive response
```

WebFlux is built on Reactive Streams, suited to a non-blocking model and backpressure when all participating components cooperate properly. `Mono<T>` represents a sequence emitting at most one result (or completion/error); `Flux<T>` represents a sequence of zero or more results. This is a **programming model**, not a guarantee that arbitrary code inside the pipeline will automatically become asynchronous.

**Common pitfall:** calling `Thread.sleep(...)`, blocking JDBC, or `block()` directly on a Netty event-loop can stall the thread handling many requests. You must choose appropriate reactive libraries/drivers, or offload blocking work to a managed scheduler with clear resource limits; switching schedulers does not automatically turn blocking I/O into end-to-end non-blocking I/O.

### 5.2. Minimal Configuration

In a Boot 3.3 project with build configuration set up:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
```

When WebFlux is present without Spring MVC, Boot typically selects `REACTIVE`. You can configure it explicitly:

```properties
spring.main.web-application-type=reactive
server.port=8080
```

Not every application that adds `spring-boot-starter-webflux` automatically becomes a reactive web server. If Spring MVC is also present, Boot defaults to **preferring `SERVLET`**; the next section explains why.

WebFlux is not locked to Reactor Netty: Spring WebFlux can run on supported servers like Tomcat/Jetty/Undertow via the appropriate adapter. Therefore, identifying the application type by spotting the words "Tomcat" or "Netty" in logs is an error-prone guess.

### 5.3. When to Choose Reactive?

Valuable when the application must sustain many concurrent I/O connections, streaming, SSE, proxies/gateways, long-lived connections, or when downstream processing actually has suitable reactive/non-blocking APIs. Weigh pipeline complexity, error observability, backpressure, and library integration. A WebFlux application performing many blocking operations can still perform worse than expected.

## 6. How Does Spring Boot Decide the Type When You Do Not Specify It?

`SpringApplication` infers `WebApplicationType` from **the classes present on the runtime classpath**. It is not a count of `@RestController` annotations, is not based on package names, and is not based on whether the application opened a port in a previous run.

In typical Boot 3.3 scenarios:

1. Spring MVC (`spring-webmvc`, usually via `spring-boot-starter-web`) is present → selects `SERVLET`.
2. No Spring MVC, Spring WebFlux (`spring-webflux`, usually via the WebFlux starter) is present → selects `REACTIVE`.
3. None of the web infrastructure the algorithm looks for is present → selects `NONE`.

At the implementation level, Boot checks indicator classes, including WebFlux/MVC dispatchers and Servlet classes. Cases where the Servlet API is present without sufficient MVC/WebFlux require checking the exact classpath; the three bullet points are practical rules for typical project setups, not a verbatim copy of the algorithm's source code.

### 6.1. When Both Starters Are Present

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
```

**Default result: `SERVLET`.** Spring Boot prefers MVC. Having both dependencies is quite common: the server still serves via Spring MVC while internal clients use WebFlux's `WebClient` to call other services.

Practical consequences:

- Using `WebClient` does **not** prove inbound HTTP requests are being handled by WebFlux.
- A controller returning `Mono` does **not** automatically prove the server is running with `REACTIVE`.
- Seeing `spring-webflux` in the dependency tree does **not** mean `DispatcherHandler` is the active inbound dispatcher.
- To **force** an application with both on the classpath to run on the WebFlux branch, you can set `spring.main.web-application-type=reactive`, but you must verify that existing dependencies/auto-configuration, server, security, and MVC libraries are still appropriate.

The simplest solution if the application only needs WebFlux for inbound HTTP is to **keep only the WebFlux starter** and add needed libraries individually. If the application only needs inbound Spring MVC and outbound `WebClient`, keep `SERVLET` as intended and use `WebClient` as an HTTP client.

### 6.2. Quick Decision Diagram

```text
                 SpringApplication.run(...)
                            |
               Type explicitly configured?
                   /                 \
                 Yes                  No
                  |                    |
        Use configured type   Inspect runtime classpath
                                       |
                             Spring MVC present?
                                /          \
                              Yes           No
                               |             |
                            SERVLET      WebFlux present?
                                           /       \
                                         Yes        No
                                          |          |
                                       REACTIVE     NONE
```

The diagram shows typical starter scenarios. Depending on special classpath setups, Boot performs additional indicator checks. If a type is forced while dependencies do not provide the corresponding infrastructure, startup can still fail.

## 7. Three Ways to Set the Runtime Type

### 7.1. Let Boot Infer from Dependencies

The usual, lowest-configuration option: simply choose the appropriate starter:

```groovy
// Plain app, no HTTP:
implementation 'org.springframework.boot:spring-boot-starter'

// Spring MVC app:
implementation 'org.springframework.boot:spring-boot-starter-web'

// Spring WebFlux app:
implementation 'org.springframework.boot:spring-boot-starter-webflux'
```

The three lines above are **three alternatives**, not advice to put all three into the same project.

### 7.2. Configure via `application.properties`

```properties
# Choose exactly one type based on your purpose:
spring.main.web-application-type=none
# spring.main.web-application-type=servlet
# spring.main.web-application-type=reactive
```

This property is mapped by Boot onto `SpringApplication` during startup. The enum values in Java are `NONE`/`SERVLET`/`REACTIVE`; in configuration they are typically written in lowercase.

You can switch modes when launching a JAR via configuration arguments, provided the necessary libraries are already packaged in the JAR:

```bash
java -jar build/libs/my-app.jar --spring.main.web-application-type=none
```

The command above assumes `my-app.jar` is the **actual built file name**; replace it with your project's JAR path.

### 7.3. Set Programmatically in Java

```java
package com.example.webtype;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ForcedNoneApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(ForcedNoneApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.run(args);
    }
}
```

This is a **complete file** at `src/main/java/com/example/webtype/ForcedNoneApplication.java`, running in a project with `spring-boot-starter`. If you later want to choose Servlet/Reactive via the API, change the enum argument and add the corresponding web/server dependency.

An equivalent option is `new SpringApplicationBuilder(...).web(WebApplicationType.NONE).run(args)`. Set the value in Java when code needs to decide; if operations need to vary it by environment, externalized configuration is usually easier to manage. Avoid setting conflicting values in multiple places simultaneously and guessing which has higher priority; verify the runtime outcome instead.

## 8. Hands-On: One Application to Observe the Actual Mode

The following example uses **one Java class** that works with all three configurations. It prints the `ApplicationContext` class name and lets you verify the inferred mode at runtime. The code creates no HTTP controller; therefore running a web server in `SERVLET`/`REACTIVE` mode will open the server, though there is no business endpoint to call yet.

**File:** `src/main/java/com/example/webtype/WebTypeDemoApplication.java`

```java
package com.example.webtype;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class WebTypeDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebTypeDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner reportContext(ApplicationContext context) {
        return args -> {
            System.out.println("CONTEXT_CLASS="
                    + context.getClass().getSimpleName());
            System.out.println("RUNNER_EXECUTED=true");
        };
    }
}
```

Explanation:

- `SpringApplication.run` builds and refreshes the appropriate context.
- `@Bean` creates an `ApplicationRunner` shared across all three types, executing after `ApplicationStartedEvent` and before `ApplicationReadyEvent`.
- `getClass().getSimpleName()` observes the **actual context** created. Do not guess the mode from the `@SpringBootApplication` annotation.
- The program prints the two lines above; Spring Boot startup logs may appear before, after, or interleaved.

Assume you have a **Spring Boot 3.3.x project with Java 17+**, the Gradle Boot plugin, and matching dependency management. Run the three experiments in turn **in three separate dependency configurations**, using the same class above:

**Experiment A: `NONE`**

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

Run:

```bash
./gradlew bootRun
```

Lines to look for:

```text
CONTEXT_CLASS=AnnotationConfigApplicationContext
RUNNER_EXECUTED=true
```

There is no embedded HTTP server listening on port 8080. If no background task keeps the JVM alive, the program can exit once startup/runner finishes.

**Experiment B: `SERVLET`**

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

Run `./gradlew bootRun` again. Lines to look for:

```text
CONTEXT_CLASS=AnnotationConfigServletWebServerApplicationContext
RUNNER_EXECUTED=true
```

Boot normally starts Tomcat on port 8080 (if the port is free and unchanged). Because **no controller has been written yet**, a request to a non-existent path normally receives HTTP 404; a 404 does not prove the web server is not running. Shut down the instance between experiments to avoid port conflicts.

**Experiment C: `REACTIVE`**

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
```

Run `./gradlew bootRun` again. Lines to look for:

```text
CONTEXT_CLASS=AnnotationConfigReactiveWebServerApplicationContext
RUNNER_EXECUTED=true
```

Boot typically uses Reactor Netty to open HTTP port 8080. If you still leave `spring-boot-starter-web` present in dependencies, the result may fall back to a servlet context because MVC takes precedence. Before comparing the three experiments, verify that the dependency was swapped as instructed and the previous process was stopped.

On Windows, replace `./gradlew bootRun` with `gradlew.bat bootRun` or `.\gradlew.bat bootRun` in PowerShell. For Maven projects, run with `./mvnw spring-boot:run` if Maven Wrapper is present.

### 8.1. Adding an HTTP Endpoint for Experiments B/C

Only when using the MVC or WebFlux starter, create a second file `src/main/java/com/example/webtype/PingController.java`:

```java
package com.example.webtype;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
```

Run `SERVLET` or `REACTIVE` mode and call:

```bash
curl -i http://localhost:8080/ping
```

When the server is running and no configuration blocks the request, the expected HTTP status is `200 OK`, body:

```text
pong
```

The controller annotations above are supported by both Spring MVC and WebFlux, though the underlying dispatch path differs. **Do not add `PingController.java` to the `NONE` experiment using only the base starter**: that dependency lacks the web annotations, so Java will fail to compile if you keep the `org.springframework.web.bind.annotation` imports.

## 9. How to Observe and Diagnose When the Mode Is Unexpected

### 9.1. Inspecting Context and Dependencies

Check the class printed by `WebTypeDemoApplication`. With default configuration, it reflects the context matching the mode in the opening table. When a custom context factory is used, check the context-creation code instead of inferring solely from the class name.

List runtime dependencies:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Look for `spring-webmvc`, `spring-webflux`, Servlet API, and HTTP server starters; do not look solely at the dependency lines you declared yourself, because transitively pulled libraries can also affect mode detection.

This Gradle command assumes the project has a Gradle Wrapper and the corresponding Java/Boot configuration.

### 9.2. Common Errors

| Symptom | Likely Cause | How to Handle |
| --- | --- | --- |
| Added WebFlux, yet Boot still creates a servlet context | `spring-webmvc`/web starter is also present | Inspect the dependency tree; remove MVC if unneeded or configure reactive explicitly. |
| `WebClient` works, yet endpoints still go through `DispatcherServlet` | `WebClient` is an HTTP **client** and does not decide the inbound server | Distinguish a reactive client from the server's mode. |
| Set `spring.main.web-application-type=none` and HTTP requests fail to connect | Web infrastructure was turned off by design | Choose `SERVLET`/`REACTIVE` if an endpoint is genuinely needed. |
| Forced `SERVLET`/`REACTIVE`, yet startup fails with missing web server factory | Classpath lacks a suitable server factory or exclusions are wrong | Add the appropriate starter/server and check the root cause in startup logs. |
| WebFlux is slow under high load despite `Mono`/`Flux` | Calling JDBC, `Thread.sleep`, or `block()` on the event loop | Check blocking calls, schedulers, drivers, and timeouts. |
| `server.port=-1` yet a web context still appears | This property only disables HTTP endpoints without changing the mode | Use `spring.main.web-application-type=none` if a non-web context is needed. |
| A `NONE` program exits right after the runner | No remaining work or thread keeping the JVM alive | If CLI: behavior may be expected; if worker: initialize the processing loop/listener with the right lifecycle. |
| REST endpoint returns 404 in the example without a controller | Server opened, but no matching route exists | Add `PingController` for web mode and call `/ping`. |
| Test using `@SpringBootTest` differs from production mode | Tests may pick their own `webEnvironment` or properties | Verify test configuration and production mode independently. |

### 9.3. Distinguishing `WebApplicationType` from `SpringBootTest.WebEnvironment`

`WebApplicationType` is the application type used by `SpringApplication`. In testing, `@SpringBootTest(webEnvironment = ...)` uses a **different** enum (`SpringBootTest.WebEnvironment`) with values like `MOCK`, `RANDOM_PORT`, `DEFINED_PORT`, and `NONE`. Do not assign the two enums to each other or assume `RANDOM_PORT` is a new `WebApplicationType`.

When both MVC and WebFlux are present, the Spring Boot documentation suggests:

```java
@SpringBootTest(properties = "spring.main.web-application-type=reactive")
class WebFluxApplicationTests {
    // Test with a reactive web application context
}
```

This is an **annotation illustration inside a test class**, not a complete test file; the project needs test dependencies and appropriate JUnit/`SpringBootTest` imports. The goal is to force the application type in tests, since Boot normally prefers MVC when both are present.

## 10. Design Selection Rules

Ask these questions in order:

1. **Does the application need to receive HTTP requests?** If no, `NONE` is a sensible starting point. If yes, pick one of the two web modes.
2. **Are the downstream processing components blocking and designed for Servlet?** If primarily using JDBC/JPA and standard synchronous APIs, `SERVLET` is usually simpler and easier to integrate.
3. **Is there a clear benefit from non-blocking I/O/reactive streams?** If it is a streaming service, has high concurrent connection counts, and downstream systems support reactive APIs, consider `REACTIVE`.
4. **Are both web starters genuinely needed at once?** Usually only one is needed. If it is an MVC server using outbound `WebClient`, keeping MVC as the inbound mode makes sense.
5. **Do you need to override via configuration?** Configure explicitly when your intent differs from classpath inference; otherwise let Boot auto-detect and verify via the runtime context.

Do not choose `REACTIVE` merely because the word "reactive" sounds more modern, and do not assume `SERVLET` cannot handle heavy loads. Evaluate based on I/O characteristics, operability, library fit, and actual measurements.

## 11. Self-Check Questions

**1. An application has `spring-boot-starter-web` and `spring-boot-starter-webflux`. No mode is configured. What does Boot choose?** — `SERVLET` in typical configurations, because Spring MVC has higher priority than WebFlux.

**2. Must a CLI with `@SpringBootApplication` and `ApplicationRunner` open an HTTP server?** — No. With `NONE`, lifecycle beans and runners still run without starting a web server.

**3. If you see `Mono<String>` in a controller method, is that enough to conclude the app uses `REACTIVE`?** — No. You must check the context and dispatch system; Spring MVC can also interoperate with reactive types.

**4. To disable the HTTP server completely while still using Boot, which property expresses the intent most clearly?** — `spring.main.web-application-type=none`. `server.port=-1` keeps the web application context, so it carries a different meaning.

**5. Does WebFlux strictly require Reactor Netty?** — No. Netty is the default choice of the WebFlux starter in Boot 3.3, while the reactive stack has other server adapters.

**6. Does switching the enum from `SERVLET` to `REACTIVE` automatically fix all blocking libraries?** — No. The context type, auto-configuration, and dispatcher change, but blocking code stays blocking; you must inspect drivers, clients, and scheduler usage.

**7. What is a more reliable observation point than the starter name?** — The actual runtime context, created beans/web server, auto-configuration, and dependency tree.

## 12. Official Documentation for Reference

- [Spring Boot 3.3 — SpringApplication and Selecting Web Environment](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html).
- [Spring Boot 3.3 — Embedded Web Servers, Default Server, and Disabling the Web Server](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html).
- [Spring Boot 3.3 — Detecting Web Application Type in Tests](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html).
- [Spring Boot 3.3 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html).
- [Spring Framework — Spring WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html).
