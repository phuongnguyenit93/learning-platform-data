# Choosing WebApplicationType: NONE, SERVLET, and REACTIVE

## 1. What is WebApplicationType?

In Spring Boot, `WebApplicationType` determines the type of application environment that `SpringApplication` initializes. It affects the type of `ApplicationContext`, web server configuration, and web-related auto-configurations.

The enum resides in the `org.springframework.boot` package and has three values:

- **`NONE`**: the application does not run as a web server. Spring still creates the ApplicationContext, initializes beans, and runs callbacks such as `ApplicationRunner` or `CommandLineRunner`.
- **`SERVLET`**: a web application based on the Servlet API, typically using Spring MVC and an embedded servlet container such as Tomcat.
- **`REACTIVE`**: a web application following the reactive model of Spring WebFlux, typically using Reactor Netty or a compatible server adapter.

You can think of this as an application-level architectural choice. It determines how Spring Boot initializes the web environment; it is not a property for enabling or disabling individual endpoints.

## 2. How does Spring Boot automatically determine the application type?

If not explicitly configured, Spring Boot deduces `WebApplicationType` from the classes present on the classpath. The general rules are:

1. If the foundational classes of Spring WebFlux are present and the characteristic classes of Spring MVC are absent, Boot chooses `REACTIVE`.
2. If the required classes for Servlet/Spring MVC are present, Boot chooses `SERVLET`.
3. If the conditions for neither a Servlet nor a Reactive application are met, Boot chooses `NONE`.

A common source of confusion is a project that has both `spring-boot-starter-web` and `spring-boot-starter-webflux`. When both Spring MVC and WebFlux are present, Spring Boot prioritizes Spring MVC by default and chooses `SERVLET`. If you intend to build a WebFlux application, you must explicitly choose `REACTIVE` and verify the accompanying dependencies and auto-configurations.

Classpath-based deduction provides convenient default configuration, but it can also cause the application type to change when a starter is added. Therefore, review the dependency tree if an application unexpectedly starts a web server or selects the wrong web stack.

## 3. NONE — Spring application without a web server

### 3.1. How it works

With `WebApplicationType.NONE`, Spring Boot initializes an ApplicationContext that is not intended for a web server. The application can still use dependency injection, configuration properties, component scanning, appropriate auto-configurations, bean lifecycle management, and core Spring features.

The difference is that Boot does not start an embedded web server to accept HTTP requests. The application has no request/response processing flow like a web application.

Common use cases:

- Command-line programs that accept arguments and perform a task.
- Batch jobs that read data, process it, and write results.
- Workers that run background tasks or process messages.
- Migration, import/export, or data synchronization tools.
- A scheduled process, if the application is configured with an appropriate scheduler.

A NONE application can still call external services via an HTTP client such as `RestClient` or `WebClient`. Using an HTTP client does not turn the application into a web server; the application type refers to the process's role in receiving requests.

### 3.2. Configuring with application.properties

```properties
spring.main.web-application-type=none
```

Or in `application.yml`:

```yaml
spring:
  main:
    web-application-type: none
```

This configuration is useful when a project has web dependencies on the classpath but the current execution purpose is batch or command-line. However, if the application does not need a web stack, consider removing unused web starters to reduce dependencies and avoid unnecessary auto-configuration.

### 3.3. Spring Boot NONE example

The example below is a minimal Spring Boot application. It creates an ApplicationContext and then runs an `ApplicationRunner` without opening an HTTP port.

```java
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class BatchApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(BatchApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.run(args);
    }

    @Bean
    ApplicationRunner batchRunner() {
        return args -> System.out.println("Batch job started");
    }
}
```

With a project already configured with Spring Boot and the appropriate dependencies, you can run the application using Maven:

```bash
./mvnw spring-boot:run
```

The output printed by the application code is:

```text
Batch job started
```

Spring Boot may also print a banner and startup logs. The line above is the output of `ApplicationRunner`, not the entire process log.

You can write this more concisely by setting the `spring.main.web-application-type=none` property in configuration and using `SpringApplication.run(BatchApplication.class, args)`. Calling `setWebApplicationType` in the example directly demonstrates the API being used.

### 3.4. When should you not choose NONE?

Do not choose NONE if the process needs to accept HTTP requests, expose REST APIs, serve a web UI, or run WebSocket endpoints. In those cases, an appropriate web application type is required. If it only needs to call another system's API, NONE can still be appropriate because an outbound HTTP client does not require an embedded web server.

## 4. SERVLET — Servlet- and Spring MVC-based web applications

### 4.1. How it works

`WebApplicationType.SERVLET` uses the web model based on the Java Servlet API. In common configurations, Spring Boot uses Spring MVC and embedded Tomcat as the default web server when the corresponding dependencies are present.

At startup, Boot creates a Servlet web application context and configures the web server. An HTTP request enters the server, passes through the Servlet filter chain, and reaches `DispatcherServlet`. `DispatcherServlet` coordinates with Spring MVC components such as handler mappings, controllers, argument resolvers, and message converters to process the request and produce a response.

General flow:

```text
HTTP Client
    |
Embedded Servlet Container
    |
Servlet Filters
    |
DispatcherServlet
    |
Controller / Service
    |
HTTP Response
```

The Spring MVC model is commonly used in a synchronous processing style: a request is handled on a container thread and the controller returns a result. However, the Servlet API and Spring MVC also support asynchronous processing; therefore, you should not assume that every request in every configuration must occupy a thread until completion.

### 4.2. Common dependency

For a standard Spring MVC application, the typical dependency is:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
```

This starter brings Spring MVC and the default embedded servlet container onto the classpath. You can replace the default container with another Spring Boot-supported server if needed and configured appropriately.

### 4.3. Configuring the application type

If you want to specify the application type explicitly:

```properties
spring.main.web-application-type=servlet
server.port=8080
```

In many projects that only have `spring-boot-starter-web`, Boot automatically deduces SERVLET. Explicit declaration is useful when multiple web starters exist on the classpath or when you want clearer, more predictable configuration.

### 4.4. Spring MVC controller example

Here is an annotated-style controller:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public String hello() {
        return "Hello from Servlet";
    }
}
```

When the SERVLET application runs on port 8080, the request:

```http
GET /hello HTTP/1.1
Host: localhost:8080
```

will receive the body:

```text
Hello from Servlet
```

In real-world applications, controllers typically call services to handle business logic rather than placing business logic directly inside controller methods.

### 4.5. When should you choose SERVLET?

SERVLET is suitable when:

- The project uses Spring MVC, REST APIs, or server-rendered web pages.
- The application has many libraries, filters, or integrations based on the Servlet API.
- Most processing operations are synchronous and can use the familiar request/thread model.
- The team wants to use the Spring MVC ecosystem and embedded servlet containers.

Spring MVC can still handle high loads when designed and deployed properly. Do not choose REACTIVE just because you heard reactive is always faster; consider workload patterns, I/O wait times, dependencies, and operational capabilities.

## 5. REACTIVE — Web applications with Spring WebFlux

### 5.1. How it works

`WebApplicationType.REACTIVE` initializes a reactive web environment. Spring Boot uses Spring WebFlux instead of Spring MVC as the primary web stack. In the common default configuration, the embedded server is Reactor Netty.

WebFlux is built on Reactive Streams and Project Reactor. Two commonly encountered data types are:

- `Mono<T>`: represents an asynchronous result that can emit at most one element.
- `Flux<T>`: represents an asynchronous sequence of zero, one, or many elements.

WebFlux typically uses an event loop and non-blocking I/O processing. Instead of holding a request thread while waiting for I/O, the runtime can use that thread to process other work while the I/O operation is incomplete.

General flow:

```text
HTTP Client
    |
Reactive Web Server (typically Reactor Netty)
    |
WebFlux Handler / DispatcherHandler
    |
Controller or Functional Endpoint
    |
Mono / Flux pipeline
    |
HTTP Response
```

This model is suitable for applications with high concurrent I/O operations and dependencies that provide non-blocking APIs.

### 5.2. Common dependency

For Spring WebFlux:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
```

This starter brings Spring WebFlux and the appropriate default reactive server runtime onto the classpath. WebFlux can also run on several other server adapters, including compatible Servlet containers; using WebFlux does not necessarily require Netty in every deployment.

### 5.3. Configuring the application type

```properties
spring.main.web-application-type=reactive
server.port=8080
```

If the project has both `spring-boot-starter-web` and `spring-boot-starter-webflux`, explicitly select REACTIVE when you truly intend to use WebFlux. Better yet, remove the unnecessary starter to avoid auto-configuration selecting the wrong stack and complicating the dependency tree.

### 5.4. Reactive controller example

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ReactiveHelloController {

    @GetMapping("/hello")
    public Mono<String> hello() {
        return Mono.just("Hello from Reactive");
    }
}
```

The controller returns `Mono<String>`. WebFlux subscribes and writes the result when the publisher emits data, rather than requiring the method to immediately return a String in the traditional synchronous manner.

The response body is:

```text
Hello from Reactive
```

This example illustrates the reactive return type. In real-world applications, non-blocking benefits become clearer when subsequent processing steps also use non-blocking APIs, such as WebClient or a reactive database driver.

### 5.5. Avoiding blocking in a reactive pipeline

A common mistake is choosing REACTIVE while still calling blocking APIs on an event-loop thread. For example, calling synchronous JDBC, `Thread.sleep()`, or a blocking HTTP client directly in a reactive pipeline can hold the event-loop thread while waiting. This reduces concurrency capacity and can cause bottlenecks.

Practical guidelines:

- Prefer reactive drivers and clients when the entire business flow needs to be non-blocking.
- Do not call `block()` arbitrarily in a controller or event-loop pipeline.
- Do not use `Thread.sleep()` to wait inside a reactive chain.
- If you must integrate a blocking operation, isolate it on an appropriate scheduler, typically `Schedulers.boundedElastic()`, and bound the load according to system capacity.
- Measure latency, throughput, thread usage, and errors under realistic load.

Example illustrating how to isolate a blocking task:

```java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<String> result = Mono.fromCallable(() -> legacyBlockingCall())
        .subscribeOn(Schedulers.boundedElastic());
```

This snippet illustrates an existing blocking call; `legacyBlockingCall()` must be defined in the application. Offloading to boundedElastic should not be treated as a reason to turn the entire application into blocking calls without evaluating concurrency and resource limits.

### 5.6. When should you choose REACTIVE?

REACTIVE is suitable when:

- The application handles many concurrent connections and spends significant time waiting on I/O.
- Clients, database drivers, and integrated services support reactive/non-blocking operations.
- Data streaming or asynchronous stream processing is needed.
- The development team understands Reactor, backpressure, schedulers, and how to debug reactive pipelines.

Reactive does not automatically make every task faster. CPU-bound work still consumes CPU; blocking dependencies can still cause bottlenecks; complex pipelines can be harder to debug. Choose based on workload and dependency ecosystem capabilities.

## 6. Comparing the three WebApplicationType values

| Criterion | NONE | SERVLET | REACTIVE |
|---|---|---|---|
| Purpose | Application that does not accept HTTP requests as a web server | Web application based on the Servlet API | Web application based on the reactive stack |
| Web server | Does not start an embedded web server | Yes, typically Tomcat by default | Yes, typically Reactor Netty by default |
| ApplicationContext | Non-web context | Servlet web application context | Reactive web application context |
| Common web framework | MVC/WebFlux not required | Spring MVC | Spring WebFlux |
| Common processing model | Runner, batch, command-line, worker | Synchronous request/response, with async support | Reactive, non-blocking I/O |
| Common return types | No web controllers | Object, String, ResponseEntity, and MVC-supported types | Mono, Flux, and compatible publishers |
| Common starter | No web starter needed | spring-boot-starter-web | spring-boot-starter-webflux |
| Suitable use cases | Jobs, CLI, background processes | REST API, MVC, Servlet applications | High concurrent I/O, streaming, reactive integrations |

The enum name and the web framework are closely related, but they are not the same thing. `SERVLET` describes the web application context type; Spring MVC is the framework Boot typically configures in this model. Similarly, `REACTIVE` is the reactive application type; Spring WebFlux is the web framework commonly used.

## 7. How to choose WebApplicationType in code

### 7.1. Using SpringApplication.setWebApplicationType

You can configure it directly before calling `run`:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;

SpringApplication application = new SpringApplication(MyApplication.class);
application.setWebApplicationType(WebApplicationType.REACTIVE);
application.run(args);
```

Replace `REACTIVE` with `SERVLET` or `NONE` depending on your goal. This approach is useful when the application type is decided in code or when creating multiple startup configurations.

### 7.2. Using SpringApplicationBuilder

```java
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.builder.SpringApplicationBuilder;

new SpringApplicationBuilder(MyApplication.class)
        .web(WebApplicationType.NONE)
        .run(args);
```

The builder is convenient when configuring parent/child contexts or multiple application sources. For simple applications, `SpringApplication` is sufficient.

### 7.3. Using external configuration

```properties
spring.main.web-application-type=servlet
```

You can replace the value with `none` or `reactive`. Properties are often managed per profile or via environment variables when deploying across different environments. Ensure the active profile matches the intended environment.

## 8. Common misconceptions

| Misconception | Accurate explanation |
|---|---|
| NONE means not using Spring | NONE only disables starting a web server; the Spring ApplicationContext and beans still run |
| NONE cannot call external APIs | NONE can still use RestClient, WebClient, or other clients to send outbound requests |
| Having WebFlux on the classpath guarantees REACTIVE | If Spring MVC is also present, Boot defaults to SERVLET; explicit configuration is required for REACTIVE |
| REACTIVE is always faster than SERVLET | Performance depends on workload, dependencies, blocking I/O, CPU, and deployment |
| REACTIVE means Netty | Netty is the common default server; WebFlux can use other compatible server adapters |
| SERVLET is always blocking | Servlet/Spring MVC supports asynchronous processing; the common model does not mean every request is synchronous |
| Changing the property completely switches the architecture | You must check controllers, dependencies, server, data access, and the APIs being used |
| Using Mono or Flux in any application turns it into a reactive server | Publisher types can be used in many places; the web application type is determined by configuration and runtime |

## 9. Selection and verification workflow in a project

When creating or modifying a Spring Boot project, you can follow this sequence:

1. **Identify the process role:** Does the application need to accept HTTP requests or only run background tasks?
2. **Choose the web stack:** If no web server is needed, choose NONE; if using Servlet/MVC, choose SERVLET; if using WebFlux, choose REACTIVE.
3. **Check dependencies:** Verify whether `spring-boot-starter-web`, `spring-boot-starter-webflux`, and the embedded server match your goal.
4. **Check configuration:** Inspect `spring.main.web-application-type`, profiles, and related properties.
5. **Start up and inspect logs:** Check whether the server starts, the context type, and the listening port.
6. **Verify behavior:** Call endpoints if it is a web application; for NONE, confirm that the runner/job executes and the process exits or continues as designed.
7. **Evaluate under load:** If choosing reactive, inspect blocking calls, schedulers, backpressure, and resource limits.

Useful commands for inspecting dependencies:

```bash
./mvnw dependency:tree
```

With Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

If a project has both web starters, inspect the dependency tree to see which dependency pulls Spring MVC or WebFlux onto the classpath. Do not look only at directly declared dependencies, because transitive dependencies can also affect deduction.

## 10. Practical summary

- Choose **NONE** for CLIs, batch jobs, workers, or processes that do not need to receive HTTP requests.
- Choose **SERVLET** for Spring MVC applications and the familiar Servlet ecosystem.
- Choose **REACTIVE** when you need WebFlux and plan to use non-blocking I/O across critical dependencies.
- Check the classpath because Spring Boot deduces the application type automatically when not explicitly configured.
- If both MVC and WebFlux are present, MVC is prioritized by default; explicitly configure `spring.main.web-application-type=reactive` when intending to use the reactive stack.
- Do not choose based solely on intuition about performance. Measure the real workload and weigh operational complexity.

## 11. References

- Spring Boot Reference Documentation — Web: https://docs.spring.io/spring-boot/reference/web/index.html
- Spring Boot API — WebApplicationType: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/WebApplicationType.html
- Spring Boot Reference Documentation — Developing with Spring Boot: https://docs.spring.io/spring-boot/reference/using/index.html
- Spring Framework Reference — Spring Web MVC: https://docs.spring.io/spring-framework/reference/web/webmvc.html
- Spring Framework Reference — Spring WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Project Reactor Reference Guide: https://projectreactor.io/docs/core/release/reference/
