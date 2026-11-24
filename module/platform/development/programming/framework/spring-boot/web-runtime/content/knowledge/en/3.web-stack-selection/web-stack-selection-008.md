# ServletWebServerApplicationContext and ReactiveWebServerApplicationContext in Spring Boot

## 1. The problem to understand

When SpringApplication.run(...) is called, Spring Boot must decide whether the application runs as a web application and, if so, whether it belongs to the Servlet stack or the Reactive stack. That decision affects the ApplicationContext type created, the embedded web server factory required, how HTTP handlers are registered, the request-processing chain, which auto-configurations are enabled, and the application's concurrency model.

The two central classes are:

- org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext
- org.springframework.boot.web.reactive.context.ReactiveWebServerApplicationContext

Both are ApplicationContext implementations capable of managing the lifecycle of an embedded web server. They are foundational context classes, not names of web servers and not annotations placed on controllers. Selecting the right context is an essential part of web stack selection.

This lesson focuses on Spring Boot 3.x, especially the 3.3.x branch, and Java 17+. Newer Spring Boot versions may change API and package details.

### Expected outcomes

After this lesson, you should be able to:

1. Explain the roles of ApplicationContext and WebServerApplicationContext.
2. Know the conditions under which Spring Boot selects SERVLET, REACTIVE, or NONE.
3. Distinguish the two contexts by superclass, factory, web layer, request pipeline, and lifecycle.
4. Understand when the embedded web server is created, started, emits events, and stops.
5. Build two small applications to verify the context and HTTP responses yourself.
6. Diagnose root causes when Spring Boot launches the wrong web stack or cannot find a web server factory.

## 2. Conceptual layers: Spring container, web context, web server

Do not merge these four concepts into one:

| Concept | Role |
| --- | --- |
| ApplicationContext | Container managing Spring Beans, dependencies, configuration, events, and lifecycle |
| Web application context | ApplicationContext augmented with environment, Beans, and capabilities for web applications |
| WebServerApplicationContext | Contract for a context that creates and manages an embedded WebServer |
| WebServer | Object representing an embedded HTTP server, capable of start, stop, and reporting its port |

The org.springframework.boot.web.context.WebServerApplicationContext interface extends ApplicationContext and provides getWebServer() along with the web server's namespace information. getWebServer() can return null before the server is created; do not assume the server is already available inside a Bean's constructor.

Both ServletWebServerApplicationContext and ReactiveWebServerApplicationContext implement ConfigurableWebServerApplicationContext, which in turn implements WebServerApplicationContext. The difference lies in how they prepare the web environment, which WebServerFactory type they require, and how they connect the web server to HTTP handlers.

These two contexts are usually chosen automatically by Spring Boot. Developers mostly work with @SpringBootApplication, starters, controllers, and configuration; there is rarely a need to instantiate either context manually.

## 3. ServletWebServerApplicationContext

### 3.1. Nature and role

ServletWebServerApplicationContext is a class in the org.springframework.boot.web.servlet.context package. It extends Spring Framework's GenericWebApplicationContext and adds discovering ServletWebServerFactory, creating the embedded WebServer, setting up ServletContext, and registering Servlet API components.

An application bootstrapped via annotation configuration typically uses the subclass AnnotationConfigServletWebServerApplicationContext. Therefore, when printing the actual class name, you will usually see this subclass rather than ServletWebServerApplicationContext directly.

This context fits Servlet-based applications, typically Spring MVC. It can also serve other Servlets; the presence of ServletWebServerApplicationContext does not guarantee the application must have MVC controllers.

### 3.2. Relationship with ServletWebServerFactory

The context looks up a Bean of type ServletWebServerFactory to create the web server. Common implementations:

- TomcatServletWebServerFactory: embedded Tomcat.
- JettyServletWebServerFactory: embedded Jetty.
- UndertowServletWebServerFactory: embedded Undertow.

With spring-boot-starter-web, the default choice is typically Tomcat. You can change the server by adjusting dependencies and compatible configurations.

The context needs one matching factory inside the container itself. If no factory exists or multiple ambiguous factories exist, server creation can fail. You cannot fix a missing factory error simply by adding @RestController.

### 3.3. ServletContext and registration mechanism

The Servlet stack uses jakarta.servlet.ServletContext, Servlet, Filter, and their corresponding registration mechanisms. ServletWebServerApplicationContext prepares ServletContext so components can operate with the embedded server.

Components that can participate in registration:

- Servlet: component accepting requests at the Servlet layer; DispatcherServlet is Spring MVC's main Servlet.
- Filter: processes before and after a Servlet; for example filters for security, logging, or CORS.
- ServletContextInitializer: customizes initialization and registration.
- ServletRegistrationBean and FilterRegistrationBean: explicitly register Servlets/Filters.

Spring Boot supports automatically registering suitable Servlet and Filter Beans. When mapping paths, filter ordering, or specific configurations are needed, use registration beans and understand registration rules to avoid duplicates.

Spring MVC typically maps DispatcherServlet to receive matching requests and then uses HandlerMapping and HandlerAdapter to invoke controllers. Servlet Filters run at the container layer, outside the execution scope of Spring MVC's HandlerInterceptor.

### 3.4. Typical HTTP flow

~~~text
HTTP client
    |
    v
Embedded Servlet server (e.g., Tomcat)
    |
    v
jakarta.servlet.Filter chain
    |
    v
DispatcherServlet
    |
    +--> HandlerMapping
    +--> HandlerAdapter
    +--> @Controller / @RestController
    |         |
    |         v
    |       Service -> Repository / downstream service
    |
    v
HttpMessageConverter / response
    |
    v
Servlet server -> HTTP client
~~~

This illustrates the flow when Spring MVC is used. A Servlet other than DispatcherServlet can receive requests according to its own mapping; ServletWebServerApplicationContext is still the appropriate context.

### 3.5. Execution model

In typical synchronous Servlet processing, the server uses threads to execute requests; blocking database or HTTP calls can hold a thread until completion. The Servlet stack also supports async processing, so you should not state that every Servlet request is always blocking from start to finish.

When operating MVC, understand thread pool sizes, connection pools, timeouts, queues, and the rule that singleton Beans must not hold mutable per-request state without proper synchronization.

## 4. ReactiveWebServerApplicationContext

### 4.1. Nature and role

ReactiveWebServerApplicationContext is a class in the org.springframework.boot.web.reactive.context package. It extends GenericReactiveWebApplicationContext and uses ReactiveWebServerFactory to create an embedded WebServer serving the reactive HTTP processing model.

In an annotation-configured application, the implementation commonly seen is AnnotationConfigReactiveWebServerApplicationContext.

This class does not use ServletContext as its core web programming model. Spring WebFlux's primary abstractions are HttpHandler, WebHandler, WebFilter, ServerWebExchange, HandlerMapping, and reactive result-handling components. Applications can use annotated controllers or functional routing.

### 4.2. Relationship with ReactiveWebServerFactory

The context looks up a Bean of type ReactiveWebServerFactory. Implementations include:

- NettyReactiveWebServerFactory: Reactor Netty; typical default for spring-boot-starter-webflux.
- TomcatReactiveWebServerFactory, JettyReactiveWebServerFactory, UndertowReactiveWebServerFactory: corresponding reactive server options when dependencies and adapters support them.

This is crucial: ReactiveWebServerApplicationContext does not necessarily mean running Netty; and seeing Tomcat in logs is not enough to conclude the application is using Spring MVC. Context type and HTTP server implementation are two distinct axes of choice.

### 4.3. HttpHandler and reactive pipeline

WebFlux builds an HttpHandler from WebHandler infrastructure, WebFilters, exception handlers, and adapters to connect the application to the HTTP server. With annotated controllers, DispatcherHandler is WebFlux's front controller, distinct from MVC's DispatcherServlet.

~~~text
HTTP client
    |
    v
Reactive HTTP server (e.g., Reactor Netty)
    |
    v
HttpHandler / server adapter
    |
    v
WebFilter chain
    |
    v
DispatcherHandler (Spring WebFlux)
    |
    +--> HandlerMapping
    +--> HandlerAdapter
    +--> @RestController / RouterFunction
    |         |
    |         v
    |      Mono<T> / Flux<T> or compatible return type
    |
    v
HandlerResultHandler + encoder
    |
    v
Reactive HTTP response
~~~

Mono represents a stream with at most one element; Flux represents a stream that can have many elements. WebFlux can handle results asynchronously and support backpressure in supported pipeline segments. You should not assume that merely returning Mono from a method automatically turns all underlying I/O into non-blocking operations.

### 4.4. Execution model and practical constraints

Reactor Netty typically uses event-loop threads to handle connections and I/O signals. The benefits of the reactive model emerge when most of the pipeline, including service and data access, does not block threads.

For example, calling Thread.sleep(), blocking JDBC, or a synchronous HTTP SDK directly on the event loop can impact many other requests. When blocking libraries must be integrated, evaluate isolating the work on an appropriate scheduler, bounding concurrency, and load capacity; switching schedulers does not turn a blocking API into a non-blocking API.

With Servlet MVC, HttpSession and Servlet request scope are familiar concepts. WebFlux has ServerWebExchange, WebSession, and its own abstractions. Do not copy Servlet Filters or HttpServletRequest verbatim into reactive controllers expecting the same semantics.

## 5. How does Spring Boot choose the context?

### 5.1. WebApplicationType

Spring Boot uses WebApplicationType with three values:

- SERVLET: runs as a Servlet-based web application.
- REACTIVE: runs as a reactive web application.
- NONE: application does not run an embedded web server.

At startup, SpringApplication determines the web application type, typically by deducing from classes present on the classpath, and then uses the corresponding context creation mechanism. This deduction is not based simply on module names or whether you wrote a controller returning Mono.

In Spring Boot 3.x, common scenarios include:

| Dependency / configuration | Typically chosen WebApplicationType | Typically received context type |
| --- | --- | --- |
| spring-boot-starter-web, no WebFlux | SERVLET | AnnotationConfigServletWebServerApplicationContext |
| spring-boot-starter-webflux, no MVC | REACTIVE | AnnotationConfigReactiveWebServerApplicationContext |
| Both Spring MVC and WebFlux | SERVLET by default | Servlet context |
| No matching web infrastructure | NONE | AnnotationConfigApplicationContext |
| Configured spring.main.web-application-type=reactive with full reactive infrastructure | REACTIVE | Reactive context |
| Configured spring.main.web-application-type=none | NONE | No embedded web server created |

If both Spring MVC and WebFlux are present, Spring MVC is prioritized by Boot 3.x's default rule. This is why an MVC application can still use WebClient while its context remains a Servlet context.

### 5.2. Explicit selection configuration

Example application.properties:

~~~properties
spring.main.web-application-type=reactive
server.port=8081
~~~

This configuration requests the application to select REACTIVE. However, compatible dependencies, controllers/filters, and a web server factory are still required. Forcing the web application type does not automatically convert a Servlet MVC project into a complete WebFlux architecture.

Disabling the embedded web server:

~~~properties
spring.main.web-application-type=none
~~~

The NONE option fits CLIs, batch jobs, certain workers, or applications that do not accept HTTP. An application with a web starter that intentionally sets NONE will not create an embedded HTTP server in the main context.

You can set the type programmatically with WebApplicationType when configuring SpringApplication. Only use this when genuinely required; for typical applications, clear dependency management and configuration are easier to maintain.

### 5.3. Auto-configuration responds to this choice

Auto-configuration typically checks web application type, classpath, Bean presence, and properties.

On the Servlet stack, you commonly encounter:

- ServletWebServerFactoryAutoConfiguration
- DispatcherServletAutoConfiguration
- WebMvcAutoConfiguration

On the Reactive stack, you commonly encounter:

- ReactiveWebServerFactoryAutoConfiguration
- HttpHandlerAutoConfiguration
- WebFluxAutoConfiguration

These configurations are not activated just because the class names exist in a repository; they must satisfy actual conditions. Use the condition evaluation report when you need to determine exactly why an auto-configuration took effect or was excluded.

## 6. Direct comparison of the two contexts

| Criterion | ServletWebServerApplicationContext | ReactiveWebServerApplicationContext |
| --- | --- | --- |
| WebApplicationType | SERVLET | REACTIVE |
| Superclass | GenericWebApplicationContext | GenericReactiveWebApplicationContext |
| Common contract | ConfigurableWebServerApplicationContext | ConfigurableWebServerApplicationContext |
| Web server factory | ServletWebServerFactory | ReactiveWebServerFactory |
| Typical starter | spring-boot-starter-web | spring-boot-starter-webflux |
| Common default server | Tomcat | Reactor Netty |
| Alternative servers | Jetty, Undertow | Tomcat, Jetty, Undertow depending on dependencies |
| HTTP entry point | Servlet / DispatcherServlet (if MVC) | HttpHandler / DispatcherHandler (if WebFlux) |
| Primary filter | jakarta.servlet.Filter | org.springframework.web.server.WebFilter |
| Common request objects | HttpServletRequest, HttpServletResponse | ServerWebExchange, ServerHttpRequest, ServerHttpResponse |
| Common return types | Object, ResponseEntity, CompletableFuture, MVC async types | Mono, Flux, Object, ResponseEntity, reactive wrappers |
| Common security chain | SecurityFilterChain | SecurityWebFilterChain |
| Typical request model | Servlet thread model and async if used | Reactive I/O with event loop when using Netty |
| Session abstraction | HttpSession | WebSession |

Some APIs share identical names across both stacks yet behave differently. For instance, @RestController and @GetMapping work in both MVC and WebFlux; the annotation alone does not tell you for sure which stack the app is running on.

The most important difference is not merely performance. It lies in the programming contract: request abstractions, filters/security, error handling, concurrent data, I/O models, and library integration.

## 7. Lifecycle of an embedded web server

### 7.1. Startup

Conceptual process:

1. JVM invokes main and SpringApplication.run(...).
2. SpringApplication prepares Environment, properties, and active profiles.
3. SpringApplication creates the ApplicationContext matching WebApplicationType.
4. The context loads Bean definitions and refreshes.
5. Auto-configuration supplies ServletWebServerFactory or ReactiveWebServerFactory when conditions match.
6. The context creates the embedded WebServer; Servlet registers Servlets/Filters, while Reactive sets up HttpHandler.
7. Spring executes lifecycle steps to start the server and accept connections.
8. Spring Boot publishes a stack-specific WebServerInitializedEvent once the server is initialized.
9. Runners complete and the application reaches ApplicationReadyEvent.

This is a conceptual flow, not a guarantee that every internal step occurs within a single callback. In Boot 3.x, server creation is tied to context refresh, while server start/stop involves lifecycle infrastructure.

Do not equate web server initialized with the entire application being ready. The server initialized event helps retrieve the web server's actual port; ApplicationReadyEvent signals that SpringApplication startup has reached the ready milestone.

### 7.2. Events to know

- ServletWebServerInitializedEvent: event for the Servlet web server, in package org.springframework.boot.web.servlet.context.
- ReactiveWebServerInitializedEvent: event for the Reactive web server, in package org.springframework.boot.web.reactive.context.
- WebServerInitializedEvent: common event base class containing the newly initialized WebServer.
- ApplicationReadyEvent: the application has completed startup per SpringApplication's lifecycle.

When running with server.port=0, the operating system assigns an available port. Retrieve the port from the event or actual WebServer after initialization rather than assuming the configured value 0 is the listening port.

### 7.3. Shutting down the application

Closing the ApplicationContext triggers the lifecycle stop of the web server and related Beans/resources. Graceful shutdown can allow in-flight requests to complete within a configured grace period before stopping completely.

Servlet/Reactive differences also affect how pending requests, subscriptions, connections, and executors are stopped. Creating custom threads or event loops without proper shutdown hooks can prevent the process from exiting even after the context closes.

## 8. Hands-on A: create a Servlet application and verify the context

Create a Spring Boot 3.x (Java 17+) project using Spring Initializr, selecting only the Spring Web (spring-boot-starter-web) dependency. Place the main class under package com.example.servletdemo. If using Gradle, the core dependencies are typically:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

The snippet above is the dependencies block of build.gradle, not a complete build file; plugins and Spring Boot version are managed by the Initializr-generated project.

Create src/main/java/com/example/servletdemo/ServletDemoApplication.java:

~~~java
package com.example.servletdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ServletDemoApplication {

    public static void main(String[] args) {
        var context = SpringApplication.run(ServletDemoApplication.class, args);
        System.out.println(
                "SERVLET_CONTEXT=" +
                (context instanceof ServletWebServerApplicationContext));
    }
}

@RestController
class PingServletController {

    @GetMapping(value = "/ping", produces = "text/plain")
    public String ping() {
        return "pong";
    }
}
~~~

Run from the Gradle project directory:

~~~shell
./gradlew bootRun
~~~

On Windows, use gradlew.bat bootRun. After startup log lines, the console should print:

~~~text
SERVLET_CONTEXT=true
~~~

The concrete class name is typically AnnotationConfigServletWebServerApplicationContext. Startup logs may display Tomcat and port 8080 under default configuration, though exact log lines depend on version and environment.

In another terminal:

~~~shell
curl -i http://localhost:8080/ping
~~~

Expected: HTTP 200, Content-Type text/plain, and exact body pong. Curl may display additional headers depending on the server; only assert the status/body and core content type.

Why is the result a Servlet context? Starter Web brings Spring MVC and Servlet web infrastructure onto the classpath; Spring Boot detects WebApplicationType.SERVLET, creates a Servlet context, and uses the matching ServletWebServerFactory.

## 9. Hands-on B: create a Reactive application and verify the context

Create a separate Spring Boot project, Java 17+, selecting only Spring Reactive Web (spring-boot-starter-webflux). Do not include Spring Web (MVC) on the classpath for this exercise.

Typical Gradle dependency snippet:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Create src/main/java/com/example/reactivedemo/ReactiveDemoApplication.java:

~~~java
package com.example.reactivedemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.reactive.context.ReactiveWebServerApplicationContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class ReactiveDemoApplication {

    public static void main(String[] args) {
        var context = SpringApplication.run(ReactiveDemoApplication.class, args);
        System.out.println(
                "REACTIVE_CONTEXT=" +
                (context instanceof ReactiveWebServerApplicationContext));
    }
}

@RestController
class PingReactiveController {

    @GetMapping(value = "/ping", produces = "text/plain")
    public Mono<String> ping() {
        return Mono.just("pong");
    }
}
~~~

Run:

~~~shell
./gradlew bootRun
~~~

After startup logs, the console should print:

~~~text
REACTIVE_CONTEXT=true
~~~

With default starter-webflux, logs typically show Reactor Netty. Send a request:

~~~shell
curl -i http://localhost:8080/ping
~~~

Expected result: HTTP 200, Content-Type text/plain, and body pong. The difference lies in the context, HTTP server adapter, and handling Mono inside the WebFlux pipeline.

Do not run both exercises simultaneously on port 8080; stop one application before starting the other, or configure different server.port values. To use a separate port for the reactive demo, add to application.properties:

~~~properties
server.port=8081
~~~

Then call http://localhost:8081/ping.

### Comparing results

Both controllers can return the same response, yet identical output does not prove identical runtimes. Checking instanceof right after SpringApplication.run and inspecting dependencies provides direct evidence.

If the line prints REACTIVE_CONTEXT=false, check whether the classpath pulls in Spring MVC or whether the web application type setting was overridden. Do not fix it by casting the context to ReactiveWebServerApplicationContext; an invalid cast only throws ClassCastException.

## 10. Inspecting the server and port via a common API

To read server information, use the WebServerApplicationContext contract when the application runs in web mode:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.context.WebServerApplicationContext;

@SpringBootApplication
public class ContextInspectorApplication {

    public static void main(String[] args) {
        var context = SpringApplication.run(ContextInspectorApplication.class, args);

        System.out.println("CONTEXT_TYPE=" + context.getClass().getSimpleName());
        if (context instanceof WebServerApplicationContext webContext) {
            var server = webContext.getWebServer();
            if (server != null) {
                System.out.println("ACTUAL_PORT=" + server.getPort());
            }
        }
    }
}
~~~

This is an example replacing the main class in a project that already has Spring Web or Spring Reactive Web and a matching web server; do not create multiple main classes to run simultaneously. The snippet uses Java 17 pattern matching for instanceof.

CONTEXT_TYPE depends on the stack and concrete implementation; ACTUAL_PORT depends on configuration and can be dynamically assigned if server.port=0. Therefore, no fixed stdout port number is assumed.

Note: getWebServer() is designed to return null if the server has not been created yet. If you need to observe the exact initialization moment, listen for WebServerInitializedEvent instead of accessing the server too early.

Example shared listener usable in both application types:

~~~java
package com.example.demo;

import org.springframework.boot.web.context.WebServerInitializedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class WebServerPortListener {

    @EventListener
    public void onWebServerInitialized(WebServerInitializedEvent event) {
        System.out.println("WEB_SERVER_PORT=" + event.getWebServer().getPort());
    }
}
~~~

Place the file in a package covered by component scanning. If the application also has a separate management web context on its own port, multiple web-server events may fire; inspect the event's context/namespace before assigning a port to the main application.

## 11. Troubleshooting wrong web stack selection

### Scenario A: expected Reactive, got Servlet context

Symptom: prints AnnotationConfigServletWebServerApplicationContext or REACTIVE_CONTEXT=false.

Steps:

1. Check runtime dependencies for spring-boot-starter-web / spring-webmvc.
2. If both MVC and WebFlux exist, remember Boot 3.x prioritizes MVC by default.
3. If the goal is pure WebFlux, remove unnecessary MVC dependencies and use spring-boot-starter-webflux.
4. If intentionally keeping both stacks, configure spring.main.web-application-type=reactive and verify auto-configuration conditions.
5. Verify Beans, controllers, filters, and I/O libraries are all compatible with WebFlux.

Do not treat the presence of WebClient or Mono in source code as proof that the application uses ReactiveWebServerApplicationContext.

### Scenario B: No ServletWebServerFactory bean

Symptom: startup fails when the Servlet context cannot find a suitable ServletWebServerFactory.

What to check: whether the servlet container dependency was excluded from the starter, whether the app was forced to SERVLET with only reactive infrastructure, whether auto-configurations were excluded, or whether custom factory Beans conflict.

Do not manually define a new factory just to mask the symptom without understanding the application's dependencies and deployment mode.

### Scenario C: No ReactiveWebServerFactory bean

Symptom: the Reactive context cannot find a ReactiveWebServerFactory.

What to check: reactive server dependencies (typically spring-boot-starter-reactor-netty), dependency exclusions, active configuration, and auto-configuration conditions. If you swapped the server for reactive Tomcat or Jetty, verify the dependencies actually provide the matching reactive factory.

Merely having spring-webflux or Mono on the classpath does not guarantee the required web server factory is available.

### Scenario D: controller returns 404

What to check:

- Does component scanning cover the controller's package?
- Do the request path and method match @GetMapping/@PostMapping?
- Is there a context path or base path altering the URL?
- Is the application running MVC or WebFlux, and does the controller belong to the initialized pipeline?
- Is a Filter, WebFilter, or security rule blocking the request?

A 404 is not enough to conclude the wrong ApplicationContext is used; always check the runtime class and mapping logs.

### Scenario E: 401/403 after switching stacks

Spring Security for MVC uses servlet SecurityFilterChain and Filters; reactive security uses SecurityWebFilterChain and WebFilters. When switching from Servlet to Reactive, do not copy Servlet security configuration over verbatim and expect it to work.

Write security configuration matching the chosen stack, verify authentication/authorization, and test protected endpoints directly.

### Scenario F: startup succeeds, yet processing is slow

Servlet MVC: inspect thread pools, connection pools, timeouts, slow queries, and blocking requests.

Reactive WebFlux: check for blocking operations on the event loop, schedulers, downstream clients, database drivers, and concurrency limits. Switching starters to WebFlux does not automatically improve performance if dependencies remain blocking.

### Scenario G: ClassCastException when casting context

Mistake:

~~~java
// Illustrates the error only when the application actually uses a Reactive context:
ServletWebServerApplicationContext servletContext =
        (ServletWebServerApplicationContext) context;
~~~

This cast fails if the runtime context is ReactiveWebServerApplicationContext. The proper solution is determining WebApplicationType from dependencies/configuration; use the common interface when you only need to inspect the server, or check instanceof before stack-specific operations.

## 12. Tests to distinguish context types

In each project, you can create an integration test with @SpringBootTest(webEnvironment = RANDOM_PORT) to ensure the ApplicationContext and web server are fully created. With JUnit 5:

Servlet project:

~~~java
package com.example.servletdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.context.ApplicationContext;

import static org.junit.jupiter.api.Assertions.assertInstanceOf;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ServletContextTest {

    @Autowired
    ApplicationContext context;

    @Test
    void shouldUseServletContext() {
        assertInstanceOf(ServletWebServerApplicationContext.class, context);
    }
}
~~~

Reactive project:

~~~java
package com.example.reactivedemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.web.reactive.context.ReactiveWebServerApplicationContext;
import org.springframework.context.ApplicationContext;

import static org.junit.jupiter.api.Assertions.assertInstanceOf;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ReactiveContextTest {

    @Autowired
    ApplicationContext context;

    @Test
    void shouldUseReactiveContext() {
        assertInstanceOf(ReactiveWebServerApplicationContext.class, context);
    }
}
~~~

Each test is a separate file in its respective project; do not combine both test classes into a single project. Run ./gradlew test with the test runtime configured from Spring Boot starter test.

Context-type tests verify the bootstrap decision. They do not replace tests for HTTP endpoints, Filters/WebFilters, validation, security, or downstream integration.

## 13. Design decisions to weigh

### When to prefer the Servlet stack?

Typically suitable when:

- The application uses many blocking libraries such as JDBC, certain HTTP SDKs, or synchronous APIs.
- The team already has a Spring MVC and Servlet Filter/Security setup.
- The primary need is synchronous REST APIs with an easy-to-follow imperative programming model.
- Existing middleware ecosystems require the Servlet API.

The Servlet stack supports asynchronous processing; choosing it does not inherently mean a lack of scalability.

### When to prefer the Reactive stack?

Typically suitable when:

- I/O flows use genuinely reactive APIs, such as reactive clients and R2DBC where needed.
- There are many I/O-bound requests, long-lived connections, or data streams needing backpressure management.
- The team controls blocking operations and understands Reactor, WebFlux, and scheduler semantics.
- Observability, security, testing infrastructure, and integrated libraries are reactive-compatible.

Reactive is not automatically faster in every scenario; for CPU-bound work or blocking integrations, complexity may increase without commensurate benefits.

### Do not decide based on server name

A web server such as Tomcat can be the engine of the Servlet stack or act as a reactive server when configured accordingly. Choose the web stack by application contract, context type, I/O model, and dependency ecosystem; then choose the matching server implementation.

## 14. Practical checklist

Before asserting whether an application uses Servlet or Reactive, check:

- [ ] Do runtime dependencies include Spring MVC or WebFlux?
- [ ] Are both stacks present? If so, which one does Boot pick and is there an explicit override?
- [ ] Is spring.main.web-application-type configured?
- [ ] Is the actual ApplicationContext a ServletWebServerApplicationContext or ReactiveWebServerApplicationContext?
- [ ] Is the corresponding factory registered cleanly and uniquely?
- [ ] Does the request pipeline use DispatcherServlet or DispatcherHandler?
- [ ] Do filters and security chains belong to the right stack?
- [ ] Do data access libraries and HTTP clients match the intended blocking/non-blocking model?
- [ ] Did the embedded server bind to the expected port? Can the port be obtained from WebServerInitializedEvent?
- [ ] Are tests in place for context type, HTTP responses, errors, and shutdown/health where needed?

## 15. Self-check questions

1. What capabilities does WebServerApplicationContext add over ApplicationContext?
2. Which class does ServletWebServerApplicationContext extend? Which class does ReactiveWebServerApplicationContext extend?
3. Which WebServerFactory type does each context require?
4. Why does a project with both spring-boot-starter-web and spring-boot-starter-webflux typically start on the Servlet stack?
5. How do DispatcherServlet and DispatcherHandler differ?
6. In which pipelines are Servlet Filters and WebFlux WebFilters used?
7. Does ReactiveWebServerApplicationContext require using Reactor Netty?
8. In the lifecycle, when should you use WebServerInitializedEvent vs. ApplicationReadyEvent?
9. Why is a controller returning Mono not enough to prove the application uses a reactive context?
10. When startup reports a missing ReactiveWebServerFactory, which configurations and dependencies should you check?
11. Why can switching to WebFlux while still using blocking JDBC cause problems?
12. How do you write an integration test confirming the context type without relying on log text?

## 16. Reference documentation

- [Spring Boot 3.3 API — ServletWebServerApplicationContext](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/servlet/context/ServletWebServerApplicationContext.html)
- [Spring Boot 3.3 API — ReactiveWebServerApplicationContext](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/reactive/context/ReactiveWebServerApplicationContext.html)
- [Spring Boot 3.3 API — WebServerApplicationContext](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/context/WebServerApplicationContext.html)
- [Spring Boot 3.3 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html)

Key takeaway: both contexts manage embedded web servers in Spring Boot, yet ServletWebServerApplicationContext ties to the Servlet API and ServletWebServerFactory, while ReactiveWebServerApplicationContext ties to the reactive HTTP pipeline and ReactiveWebServerFactory. The selection is decided at bootstrap according to WebApplicationType and auto-configuration conditions; inspect the actual context itself to know which stack the application is running on.
