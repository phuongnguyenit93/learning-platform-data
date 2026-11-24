# Distinguishing Spring Framework, Spring MVC, Spring WebFlux, and Spring Boot

When building Java applications, these four names often appear together, yet they are **not four peer alternatives**. Spring Framework is the foundation; Spring MVC and Spring WebFlux are two web-application models belonging to Spring Framework; Spring Boot helps configure, bootstrap, package, and operate applications built with those components.

Understanding this relationship correctly helps you choose technologies, read dependencies, diagnose configuration issues, and avoid confusing how HTTP is handled with how an application is started.

## 1. Concept map: what contains what?

~~~text
                          Java Application
                                 |
                          Spring Framework
                    (IoC/DI, beans, AOP, data,
                     transactions, validation, ...)
                                 |
                      +----------+-----------+
                      |                      |
                Spring MVC              Spring WebFlux
              (Servlet stack)          (Reactive stack)
                      |                      |
                 HTTP API / UI          HTTP API / stream
                      \                      /
                       \                    /
                        Spring Boot (optional)
               auto-configuration, starters, server runner,
                 external config, packaging, Actuator
~~~

The diagram above shows **functional relationships**, not inheritance: Spring Boot is not a layer underneath Spring MVC/WebFlux in source code. Boot sits at the **setup and operations** layer and can use MVC, WebFlux, other Spring libraries, or no HTTP at all.

You can think of them as:

- **Spring Framework:** the core foundation for an application to manage objects and implement cross-cutting concerns.
- **Spring MVC:** Spring's way of receiving and handling HTTP based on the Servlet API.
- **Spring WebFlux:** Spring's way of receiving and handling HTTP using the reactive model, supporting non-blocking I/O and Reactive Streams.
- **Spring Boot:** a way to bootstrap a Spring application with less manual configuration, selecting configurations based on the classpath and conditions.

A common application stack is **Spring Boot + Spring MVC + Spring Framework**. Another is **Spring Boot + Spring WebFlux + Spring Framework**. Spring Framework or Spring MVC can still be used **without Spring Boot**.

## 2. Comparison table by responsibility

| Aspect | Spring Framework | Spring MVC | Spring WebFlux | Spring Boot |
|---|---|---|---|---|
| Nature | Core platform/libraries for Java apps | Servlet-based web framework | Reactive web framework | Tooling to configure and run Spring apps |
| Question it answers | How are beans created, wired, and managed? | How are HTTP requests mapped and handled via Servlets? | How are HTTP and async data streams handled non-blockingly? | How to set up, configure, and run an application conveniently? |
| Typical components | IoC container, DI, AOP, transactions, events | DispatcherServlet, HandlerMapping, HandlerAdapter, HttpMessageConverter | DispatcherHandler, WebHandler, WebFilter, codecs, Reactor | SpringApplication, auto-configuration, starters, embedded server, Actuator |
| Common modules/libraries | spring-context, spring-beans, spring-core | spring-webmvc (with spring-web) | spring-webflux, Reactor | spring-boot, spring-boot-autoconfigure, starters |
| Request handling model | Does not prescribe a web model | Servlet; typically each request uses a thread in a synchronous model | Reactive; I/O operations can be non-blocking, suited for event loops | Depends on the chosen web stack |
| Typical controller style | HTTP controllers are not required | @Controller, @RestController, @RequestMapping | Same controller annotations or RouterFunction/HandlerFunction | Uses MVC or WebFlux controllers; does not define a separate controller model |
| Runs a web server directly? | The container itself does not open an HTTP server by default | Requires a servlet container and deployment config | Requires an HTTP runtime/server and deployment config | Can configure and run an embedded server automatically |
| Best suited for | Most Spring apps, including non-web apps | REST CRUD, MVC views, JPA/JDBC, blocking libraries | Streaming, many I/O-bound connections, end-to-end non-blocking chains | Most Spring apps wanting convenient setup/deployment |

**Two independent decision axes:**

1. **Use Spring Boot or not?** This is a choice about how to configure, bootstrap, and operate the app.
2. **If building web, use Spring MVC or WebFlux?** This is a choice of HTTP processing model.

You should not frame "Spring MVC or Spring Boot?" as two mutually exclusive alternatives.

## 3. Spring Framework: the shared foundation

Spring Framework provides an **IoC container** that manages beans. With **Dependency Injection (DI)**, business code declares the dependencies it needs, and the container creates/injects beans according to configuration rather than having every class instantiate and wire objects itself. This reduces direct coupling, centralizes configuration, and simplifies testing.

Example of an application component shared across MVC, WebFlux, and even console apps:

~~~java
package example.core;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

**Meaning:** @Service marks the class to be registered as a bean if it falls within an appropriate component scan scope. Spring does not automatically turn GreetingService into an HTTP endpoint; receiving HTTP requires additional configuration and a web stack, such as an MVC or WebFlux controller.

Other capabilities of Spring Framework:

- **@Configuration, @Bean, @Component, @Autowired:** registering/configuring and wiring beans (constructor injection is usually preferred in practice).
- **AOP, transactions:** separating cross-cutting concerns such as transactions from business code.
- **ApplicationContext, events, resources, conversion, validation:** supporting application lifecycle and infrastructure.
- **Data integration and testing:** abstraction layers and utilities connecting various technologies; each feature requires corresponding dependencies/configuration.

Spring Framework is **not synonymous** with Spring MVC: an application running batch jobs, a command-line app, or a library using a Spring context is still a Spring application even without HTTP controllers.

### Does Spring Framework require Spring Boot?

No. You can manually create an ApplicationContext, register beans, configure Spring MVC on a servlet container, or configure a WebFlux server. However, you must actively manage libraries, baseline configuration, server integration, and deployment. Spring Boot is popular because it automates most of this repetitive work.

## 4. Spring MVC: the Servlet-based web stack

Spring MVC (Spring Web MVC, module **spring-webmvc**) is built on the **Servlet API**. The central entry point is **DispatcherServlet**, a front controller that receives requests and coordinates components to select a handler, bind parameters, invoke the controller, and produce an HTTP response.

Simplified request flow:

~~~text
Client sends HTTP
    -> Servlet container (usually Tomcat or Jetty)
    -> Servlet Filter chain
    -> DispatcherServlet
    -> HandlerMapping: find controller method
    -> HandlerAdapter: invoke method, binding/validation
    -> Controller -> Service -> Repository
    -> Return value / exception resolution
    -> HttpMessageConverter (JSON, text...) or ViewResolver (HTML view)
    -> HTTP response
~~~

Familiar features:

- **@GetMapping, @PostMapping, @PathVariable, @RequestParam, @RequestBody:** mapping HTTP requests and binding data to parameters.
- **@RestController:** combines @Controller and @ResponseBody; return values are typically converted to JSON via a message converter when returning objects.
- **@Controller:** can return a view name along with a model to render HTML on the server.
- **@ExceptionHandler, @ControllerAdvice:** centralized error handling.
- **@Valid, conversion, data binding:** validating and converting data when properly configured.
- **Servlet Filter, HandlerInterceptor:** cross-cutting request processing at their respective layers.

MVC often uses a **thread-per-request** model for synchronous processing: when code waits on JDBC or a blocking HTTP client, the processing thread is held while waiting. This model is straightforward and integrates naturally with the blocking Java ecosystem, especially **JPA/Hibernate and JDBC**.

**Do not assume MVC is "synchronous-only".** Spring MVC supports asynchronous processing via Callable, DeferredResult, CompletableFuture, and certain reactive return types. Servlet async can release the request thread while waiting and dispatch again when the result is ready. However, that async support **does not automatically turn the entire Servlet/MVC layer into WebFlux non-blocking I/O**.

## 5. Spring WebFlux: the reactive web stack

Spring WebFlux (module **spring-webflux**) was introduced in Spring Framework 5 and builds web APIs on reactive contracts, supporting **non-blocking I/O** and **Reactive Streams backpressure**. The corresponding dispatcher is **DispatcherHandler**. A WebFlux application can run on Reactor Netty or other supported servers, including servlet containers via an appropriate adapter layer; WebFlux **does not require running on Netty**.

Two styles of declaring endpoints:

1. **Annotated controllers:** uses @RestController/@GetMapping similar to MVC syntax, but methods can return Mono<T> or Flux<T>.
2. **Functional endpoints:** RouterFunction routes requests to a HandlerFunction, e.g., ServerRequest and ServerResponse.

### What do Mono and Flux signify?

- **Mono<T>:** a publisher that emits at most one element, completes empty, or signals an error.
- **Flux<T>:** a publisher that can emit 0 to many elements, complete, or signal an error.
- Publishers describe a pipeline; **cold** publishers typically execute only when subscribed to. In WebFlux, the framework subscribes to the controller's return value to produce the response.
- **Backpressure:** consumers can signal demand upstream in Reactive Streams pipelines that support it. Backpressure does not mean every external source (such as a third-party API) automatically throttles itself.

Simplified request flow:

~~~text
HTTP Client
    -> Reactive HTTP server (usually Reactor Netty)
    -> WebFilter / WebHandler
    -> DispatcherHandler
    -> Select annotated controller or functional handler
    -> Mono / Flux pipeline
    -> Reactive codec writes response, driven by data signals
    -> Client receives HTTP response / stream
~~~

WebFlux typically uses a small number of **event-loop threads** to serve many connections waiting on I/O. This is effective when most of the processing chain is also non-blocking, such as WebClient and reactive database drivers. A request may still cross different schedulers/threads depending on operations and configuration; you should not reduce all of WebFlux to "every request runs on a single thread".

### Blocking is a risk you must understand

Calling **Thread.sleep**, blocking JDBC/JPA, synchronous HTTP clients, or **Mono.block()** directly on an event loop can block other requests sharing that event loop. The following example only illustrates how to **isolate blocking work** when forced to use a legacy library:

~~~java
Mono<Result> source = Mono.fromCallable(() -> blockingRepository.load())
    .subscribeOn(Schedulers.boundedElastic());
~~~

The example assumes a Result class, a blockingRepository variable, and the corresponding Reactor imports; it is an **illustrative snippet, not a standalone compilable program**. boundedElastic moves the blocking work to a thread pool designed to hold such tasks; the repository I/O operation **is still blocking**, does not become truly non-blocking, and remains resource-bounded.

WebFlux fits when a system has a large number of waiting connections and an end-to-end non-blocking I/O pipeline, such as many service calls with WebClient, streaming/SSE, long-lived connections, or data access via a reactive driver like R2DBC. However, **reactive is not inherently faster** for simple business logic or CPU-bound tasks: complexity, context, and actual benchmarks determine the outcome.

### Similar syntax does not mean identical runtime

Both MVC and WebFlux can use @RestController, @GetMapping, @RequestBody, and the same Spring service. Identical annotation names **do not tell you whether the application runs on the servlet stack or the reactive stack**. To determine that, you must inspect dependencies, ApplicationContext type, auto-configuration, and the actual server.

## 6. Spring Boot: building and running Spring applications

Spring Boot adds **opinionated defaults** and **conditional auto-configuration** on top of Spring Framework. Boot inspects libraries on the classpath, existing beans, properties, and other conditions to register the appropriate infrastructure.

Core features:

- **SpringApplication.run(...):** starts the ApplicationContext and bootstrapping process.
- **@SpringBootApplication:** combines @SpringBootConfiguration, @EnableAutoConfiguration, and @ComponentScan. Component scanning defaults to starting from the application class's package downward.
- **Starters:** curated groups of dependencies (web stack, logging, testing...) to reduce manual configuration.
- **Embedded HTTP server:** web apps typically run as a JAR process with an embedded server; deploying a WAR to an external server is not mandatory.
- **Externalized configuration:** application.properties/application.yml, environment variables, command-line arguments... for environment-specific settings.
- **Actuator (optional dependency):** health, metrics, and operational/observability endpoints; endpoints must be enabled and secured per environment.
- **Dependency management, packaging, testing support:** manages compatible versions according to the chosen Boot line.

**Spring Boot does not automatically replace application architecture:** you still use Spring Framework beans, MVC/WebFlux controllers, services, repositories, and transactions. Boot also does not turn an API reactive by default.

### Watch out for starter name differences across Boot lines

For Servlet web applications using MVC:

- **Spring Boot 3.x:** the common starter is **spring-boot-starter-web**.
- **Spring Boot 4.x:** official documentation uses the more explicitly separated starter **spring-boot-starter-webmvc**.

For WebFlux, the common starter is **spring-boot-starter-webflux**. When copying older guides, check the **Spring Boot version line in use**; avoid assuming one starter name applies identically to every version. If creating a project with Spring Initializr, choose **Spring Web** (MVC) or **Spring Reactive Web** (WebFlux) appropriate to the selected version.

The difference between a **starter** and a **framework module**: spring-webmvc is the module implementing MVC functionality in Spring Framework; spring-boot-starter-webmvc is the convenience dependency bundle provided by Spring Boot to pull in required components and corresponding configuration.

## 7. Two runnable comparison applications

This example illustrates two HTTP endpoints with the same goal, where one uses MVC and the other returns a WebFlux Mono. **Create two separate projects** from Spring Initializr using **Java 17+**, a stable Spring Boot version compatible with your installed JDK, and Maven. When selecting dependencies on Initializr:

- Project **mvc-demo**: choose **Spring Web** (mapped to the MVC starter matching your Boot version).
- Project **webflux-demo**: choose **Spring Reactive Web**.
- Each project has a Maven wrapper generated by Initializr; below is the **complete Java code** to add or replace in each respective project.

### 7.1. Project A — Spring Boot + Spring MVC

File **src/main/java/example/mvc/MvcApplication.java**:

~~~java
package example.mvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcApplication.class, args);
    }
}
~~~

File **src/main/java/example/mvc/GreetingController.java**:

~~~java
package example.mvc;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    @GetMapping("/greeting")
    public Greeting greet(@RequestParam(defaultValue = "friend") String name) {
        return new Greeting("Hello, " + name);
    }

    public record Greeting(String message) {
    }
}
~~~

The **example.mvc** package structure must fall under component scanning starting from MvcApplication. If Initializr generated a different package, change the **package** in both files consistently and place them in the matching directories.

In the **mvc-demo** root directory:

~~~bash
# macOS/Linux
./mvnw spring-boot:run

# Windows PowerShell or Command Prompt: use instead of the command above
mvnw.cmd spring-boot:run
~~~

Open another terminal:

~~~bash
curl -s "http://localhost:8080/greeting?name=Lan"
~~~

HTTP body (JSON format, shown on one line):

~~~json
{"message":"Hello, Lan"}
~~~

**Explanation:** the request arrives at DispatcherServlet, is mapped to greet(), creates a Greeting record, and is serialized by the JSON message converter. With the default MVC starter, Boot typically configures embedded Tomcat. The controller returns an object directly; you do not need to write a Servlet or configure DispatcherServlet manually.

### 7.2. Project B — Spring Boot + Spring WebFlux

File **src/main/java/example/reactive/ReactiveApplication.java**:

~~~java
package example.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveApplication.class, args);
    }
}
~~~

File **src/main/java/example/reactive/GreetingController.java**:

~~~java
package example.reactive;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class GreetingController {
    @GetMapping("/greeting")
    public Mono<Greeting> greet(
            @RequestParam(defaultValue = "friend") String name) {
        return Mono.fromSupplier(
                () -> new Greeting("Hello, " + name));
    }

    public record Greeting(String message) {
    }
}
~~~

In the **webflux-demo** root directory, run:

~~~bash
# macOS/Linux
./mvnw spring-boot:run

# Windows: use instead of the command above
mvnw.cmd spring-boot:run
~~~

From another terminal:

~~~bash
curl -s "http://localhost:8080/greeting?name=Lan"
~~~

HTTP body:

~~~json
{"message":"Hello, Lan"}
~~~

**Explanation:** the WebFlux framework subscribes to the Mono returned by the controller and emits JSON when the publisher supplies Greeting. Mono.fromSupplier defers object creation until subscription; the example itself is too small to **prove reactive performance benefits**. With default configuration, Reactor Netty is typically used.

**Important:** both projects expose the /greeting path and produce the same output. The difference lies in the **web stack, execution contract, and I/O chain**, not in the JSON body or annotation names. Run each project one at a time on port 8080 or configure different server.port values if running them in parallel.

### 7.3. Checking Maven dependencies

With Spring Boot 4.x, a characteristic MVC dependency in pom.xml is:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webmvc</artifactId>
</dependency>
~~~

With Spring Boot 3.x, use **spring-boot-starter-web** instead of the artifactId in the MVC example above. For WebFlux on the corresponding lines:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

These are **dependency snippets** to place inside the dependencies tag of a pom.xml that already has a compatible Spring Boot parent/BOM, **not a complete standalone pom.xml**. Starter versions are usually determined by Boot's dependency management; do not arbitrarily mix Spring Framework 6/7, Boot 3/4, or Reactor versions.

## 8. Illustrating the execution model with the same request

Suppose an endpoint both fetches a customer from a database and calls another API:

~~~text
MVC:     HTTP → Servlet thread → JDBC (waiting) → RestClient (waiting) → JSON
WebFlux: HTTP → reactive pipeline → R2DBC / WebClient → signals → JSON
~~~

With synchronous MVC, a thread typically waits on JDBC or the HTTP client. With WebFlux using **truly non-blocking drivers and connectors**, the event loop can serve other work while waiting on I/O. This is only a simplified model: Servlet async can release the request thread, while WebFlux can switch threads across schedulers and still gets blocked if a blocking library is called.

**Important condition:** `Mono` does not make JDBC non-blocking; Reactive Streams backpressure does not automatically throttle every external API; CPU-bound work still consumes CPU. Therefore, choose a stack based on the **entire I/O chain**, not by looking at annotations or server names. Tabulating each I/O stage, benchmarking, and specific architectural choices are explored in depth in a separate article on Servlet/MVC versus WebFlux.

## 9. How to choose a stack for a project

A rule of thumb to start with: **MVC** is usually suitable for Servlet/HTML/REST applications with JPA, JDBC, and blocking SDKs; **WebFlux** is worth considering if there is streaming or many I/O-waiting connections and an end-to-end reactive client/driver chain. For batch jobs or console apps without HTTP, you can use Spring Framework/Boot without a web stack. If a system is already running MVC stably, measure bottlenecks before migrating.

Key distinctions to avoid picking the wrong runtime:

### Can WebClient be used in Spring MVC?

**Yes.** WebClient is a non-blocking HTTP client from the WebFlux ecosystem and can be used in an MVC application. Adding the library to use WebClient **does not mean all MVC controllers automatically become WebFlux**. You need to understand how to integrate async results into MVC to avoid inadvertently calling block() and holding threads unnecessarily.

### Should both MVC and WebFlux starters be included in the same project?

Usually **there is no need** for handling the same server API. When both MVC and WebFlux modules are on the classpath, Spring Boot by default **prioritizes the Servlet/MVC application type**; this behavior is helpful for MVC projects using WebClient, but can easily confuse developers who assume controllers are running on WebFlux. If you genuinely want a reactive web application, recheck dependencies and explicitly verify WebApplicationType.REACTIVE according to actual requirements.

### Are Spring Security, Spring Data, and Spring Cloud part of Spring Boot?

No. They are **separate projects in the Spring ecosystem** that integrate with the Framework and are often supported by Boot via starters/auto-configuration. Distinguish *Spring Framework* (foundation), *Spring Boot* (bootstrapping/configuration), *MVC/WebFlux* (web stacks), and *supporting projects* by responsibility rather than mistaking them for the same framework.

## 10. Common misconceptions and mistakes

1. **"Spring Boot replaces Spring Framework."** False. Boot builds on Spring Framework and auto-configures many of its components.
2. **"Spring Boot is always Spring MVC."** False. Boot can run MVC, WebFlux, or no web server at all.
3. **"Spring MVC is the old name for Spring Boot."** False. MVC addresses web handling with Servlets; Boot addresses bootstrapping and configuration.
4. **"Using @RestController definitely means MVC."** False. WebFlux supports the same annotations; you must inspect which web stack is activated.
5. **"WebFlux is always faster than MVC."** False. Workload, clients/databases, I/O latency, CPU limits, and deployment determine performance.
6. **"Returning Mono makes every call non-blocking."** False. A Mono can wrap a blocking call; the return type does not change the underlying I/O nature.
7. **"WebFlux only runs with Netty."** False. Reactor Netty is common with Boot, but WebFlux supports other suitable runtimes.
8. **"MVC does not support asynchronous processing."** False. MVC has Servlet async and async return types, even though the underlying infrastructure differs from WebFlux.
9. **"Adding both starters automatically switches everything to reactive."** False. Check Boot's Servlet/MVC precedence and auto-configuration.
10. **"@EnableWebMvc is always required when using Spring Boot MVC."** Incorrect in standard Boot setups: Boot already auto-configures MVC; @EnableWebMvc hands MVC configuration control back to the application and can disable default auto-configuration conveniences. For small customizations, prefer WebMvcConfigurer.
11. **"Spring Boot automatically finds every @Service in every package."** False. Component scanning has scope; place the application class in an appropriate root package or configure scanning explicitly.
12. **"Demonstrating Spring Framework requires HTTP."** False. IoC/DI, transactions, or events remain useful in non-web tasks.

## 11. Diagnosing when an application runs the wrong stack

When controllers are not mapped or the application uses an unexpected web model, check in order:

1. **Dependency tree:** which of spring-webmvc, spring-webflux, and starters does the application have, and for which Boot version? With Maven you can run **mvn dependency:tree**.
2. **Component scan:** is the @SpringBootApplication class in a package that encompasses the controllers and services?
3. **Auto-configuration:** run with **--debug** or inspect the condition evaluation report / Actuator conditions when appropriately configured; identify which MVC or WebFlux config actually activated.
4. **HTTP server and context:** is Tomcat/Jetty/Reactor Netty starting? Have server.port, servlet context path, or base path been changed?
5. **I/O style in services:** are threads waiting on blocking JDBC/HTTP, or does the pipeline use non-blocking drivers and clients? Do not judge merely by seeing Mono/Flux.
6. **Common error:** if port 8080 is already used by the other example project, stop that server first or change the port, such as **--server.port=8081** when running the Boot app.

## 12. Summary and self-check

**Identification formula:** *Spring Framework = foundation; Spring MVC = Servlet web; Spring WebFlux = reactive web; Spring Boot = bootstrap and auto-configuration.*

Try answering:

1. A project uses **@SpringBootApplication + spring-boot-starter-webmvc**; is it using Framework, MVC, or Boot? **All three**: Boot bootstraps, MVC handles HTTP, and Spring Framework provides the foundational components.
2. A project has only **spring-boot-starter-webflux**, controllers return **Mono<Greeting>**, and it runs on Reactor Netty: which stack is used? **Boot + Spring WebFlux** (along with Spring Framework infrastructure).
3. A REST API uses **JPA/JDBC** with good throughput and no streaming need yet: is switching to WebFlux mandatory? **No**; MVC is usually the natural choice, and metrics are needed before changing.
4. An MVC app adds the WebFlux dependency to call **WebClient**: do the app's endpoints automatically switch to WebFlux? **No**; you must check the actual web application type and configuration.
5. An app only needs DI to run from the command line: must Spring MVC be added? **No**.

## Official documentation for deeper reading

- [Spring Framework — Spring Web MVC](https://docs.spring.io/spring-framework/reference/web/webmvc.html): DispatcherServlet, annotated controllers, Servlet async, message conversion.
- [Spring Framework — Spring WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): reactive contract, annotated/functional endpoints, runtimes, and comparison with MVC.
- [Spring Framework — Core Technologies](https://docs.spring.io/spring-framework/reference/core.html): IoC container, beans, dependency injection.
- [Spring Boot — Web](https://docs.spring.io/spring-boot/reference/web/index.html): choosing MVC/WebFlux and starters by version line.
- [Spring Boot — Using @SpringBootApplication](https://docs.spring.io/spring-boot/reference/using/using-the-springbootapplication-annotation.html): auto-configuration, component scan, and application configuration.
- [Spring Boot — Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): WebFlux auto-configuration and notes when MVC/WebFlux coexist.
