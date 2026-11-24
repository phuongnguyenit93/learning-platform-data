# When the Server Is Created, Handlers Are Registered, and the Listening Port Opens in Spring Boot

## 1. Core Answer

When `SpringApplication.run(...)` is called to start a Spring Boot application with an embedded web server, **the following three tasks are related but are not the same operation**:

1. **Create the server:** Spring Boot selects a `WebServerFactory`, then creates and configures the server object such as Tomcat, Jetty, or Reactor Netty during `ApplicationContext.refresh()`.
2. **Register the HTTP handling mechanism (register/wire):** Boot connects the servlet/filter or reactive `HttpHandler` to the server; Spring MVC/WebFlux also builds routing metadata from `@GetMapping`, `@PostMapping`, handlers, and related configuration. There are **two distinct registration layers**: registering the HTTP entry point with the server and mapping URLs to framework handlers.
3. **Start the server and open the listening socket (start/listen):** the server is started during the context refresh lifecycle; the socket is bound to the appropriate address/port according to the server implementation. When Boot publishes `WebServerInitializedEvent`, the server is considered ready at the **web server level**, and the actual port can be queried.

Afterward, `ApplicationStartedEvent` is published, `ApplicationRunner`/`CommandLineRunner` beans execute, and only then do `ApplicationReadyEvent` and the `ACCEPTING_TRAFFIC` readiness state follow. **Opening the port does not mean all startup tasks are complete and the application is ready to receive traffic from the deployment platform.**

> Key takeaway: **never infer from "having a `@RestController`" that the port is open**, from "the server object was created" that the application is ready, or from "seeing the Tomcat initialization log" that HTTP is stably serving requests.

## 2. Four Concepts Very Easily Confused

| Concept | Practical Meaning | Evidence / How to Verify |
| --- | --- | --- |
| **Bean definition / dependency injection** | Spring knows it needs to create controllers, services, the server factory, and web infrastructure | Context is building; beans are discovered or initialized; not enough to conclude an HTTP listener exists |
| **WebServer object** | A server lifecycle object exists; the factory has configured connectors, addresses, and related resources | `ServletWebServerFactory` / `ReactiveWebServerFactory` creates `WebServer` |
| **Handler registration** | URLs/methods are mapped to handler functions; the transport layer is connected to `DispatcherServlet` or reactive `HttpHandler` | `RequestMappingHandlerMapping`, `ServletRegistrationBean`, `RouterFunction`, `HttpHandler` |
| **Listening / ready** | Listening: OS/server can accept connections on the port. Ready: application signals it is eligible to serve traffic | `WebServerInitializedEvent` to know the server has started; `ApplicationReadyEvent` and readiness to know startup is complete |

**"Handler" has two usages:** (a) the HTTP entry point invoked by the server (a Servlet or `HttpHandler`), and (b) the controller method or functional handler Spring selects for a route. These are wired at different stages; no single milestone applies to every kind of handler.

## 3. Spring Boot Timeline from `main()` to `ready`

The diagram below depicts the flow of a **typical embedded server** in Spring Boot 3.x/4.x. It is a logical sequence; internal server details, lazy initialization, and callbacks can change the order of sub-tasks.

```text
main()
  |
  +-- SpringApplication.run(args)
      |
      +-- prepare Environment, configuration, web application type
      +-- create appropriate ApplicationContext (Servlet / Reactive / None)
      +-- load bean definitions and auto-configuration
      |
      +-- ApplicationPreparedEvent
      |
      +-- context.refresh()
          |
          +-- prepare BeanFactory, process configuration/bean definitions
          +-- onRefresh(): create embedded WebServer via factory
          |   \-- set up HTTP layer / ServletContext / reactive adapter
          +-- initialize singletons and handler mapping infrastructure
          |   \-- map GET /hello -> controller method
          +-- finishRefresh(): start SmartLifecycle beans, including web server
          |   +-- server.start(), listen per server implementation
          |   +-- WebServerInitializedEvent (actual port available)
          |   \-- ContextRefreshedEvent
          |
      +-- ApplicationStartedEvent
      +-- Availability: LivenessState.CORRECT
      +-- ApplicationRunner / CommandLineRunner
      +-- ApplicationReadyEvent
      +-- Availability: ReadinessState.ACCEPTING_TRAFFIC
  |
  +-- SpringApplication.run(...) returns ApplicationContext
```

### Phase A — Before `refresh()`

`SpringApplication` reads the environment and configuration, detects the web application type from the classpath/configuration, creates the appropriate `ApplicationContext`, and registers bean definitions. For instance, `@RestController` is discovered by component scanning; at this step **there is no reason to assume an HTTP socket is bound**.

Some events published before refresh:

- `ApplicationStartingEvent`: very early, before `Environment` exists.
- `ApplicationEnvironmentPreparedEvent`: environment has been prepared.
- `ApplicationContextInitializedEvent`: context created and initializers run, before loading bean definitions.
- `ApplicationPreparedEvent`: right before refresh, after bean definitions are prepared.

These event names reflect **bootstrap progress**, not opening the listening port.

### Phase B — `refresh()` Creates the Server

In a Servlet application with an embedded server, `ServletWebServerApplicationContext.onRefresh()` creates the `WebServer` by obtaining the matching `ServletWebServerFactory` and calling the factory to build the server. For WebFlux, `ReactiveWebServerApplicationContext.onRefresh()` sets up `ReactiveWebServerFactory` and the corresponding HTTP handling.

Broadly speaking, **this is the server-creation milestone in the context lifecycle**. However, creating it may initialize internal server/connector structures, and even perform certain Tomcat/Jetty-specific network operations. Therefore, do not make an absolute claim that "every `bind()` call always happens only after all beans are complete."

Distinguish clearly:

- `factory.getWebServer(...)`: obtains/initializes the server per the Spring Boot contract.
- `webServer.start()`: transitions the server into the running state.
- `WebServerInitializedEvent`: the event Boot publishes once the server is ready, suitable for reading the actual port.

At the server-creation milestone, parts related to **ServletContext initialization** may need to be registered very early, even before ordinary singletons are created.

### Phase C — Wiring Requests to Handlers and Completing Bean Initialization

In **Spring MVC** there are at least two layers:

1. Boot prepares/registers `DispatcherServlet` and servlets/filters/listeners with the Servlet container via mechanisms such as `ServletRegistrationBean`, `FilterRegistrationBean`, and `ServletContextInitializer`. `DispatcherServlet` is typically mapped to `/`.
2. Spring MVC initializes `HandlerMapping` beans, discovers methods annotated with `@RequestMapping`/`@GetMapping`, and builds the route mapping table—for example, `GET /hello -> HelloController.hello()`. This layer is not a port-opening operation.

In **Spring WebFlux**:

1. The reactive server is wired to an `HttpHandler` (through an adapter/`HttpHandler` pipeline).
2. WebFlux builds the `WebHandler`, filter chain, `DispatcherHandler`, and handler mappings. Annotated controllers or `RouterFunction` beans determine which endpoint handles a request.

**Note on ordering:** Spring Boot can create the embedded server during `onRefresh()` **before all singletons finish initializing**; route mappings are typically completed as MVC/WebFlux infrastructure beans initialize during refresh. Therefore, saying "all controllers must finish registering before Tomcat is created" is an inaccurate description of the internal lifecycle. What matters is that all required components are fully wired before the application operates normally.

### Phase D — Server Running and Event Published, Yet App Not Necessarily Ready

During `finishRefresh()`, the lifecycle processor starts relevant `SmartLifecycle` beans, including the start/stop mechanism of the embedded web server. Boot publishes `WebServerInitializedEvent` after the server has started. This is the right observation point to read `event.getWebServer().getPort()`.

After context refresh completes, `SpringApplication` publishes `ApplicationStartedEvent`, then runs `ApplicationRunner`/`CommandLineRunner` beans. Finally, Boot publishes `ApplicationReadyEvent` and updates readiness to `ACCEPTING_TRAFFIC`.

This leads to a practical distinction:

- **Server listening:** a process may already own the TCP port and have running web infrastructure.
- **Application ready:** all startup runners have finished; health/readiness infrastructure can tell the orchestrator to route traffic to the application.

In container/Kubernetes environments, a readiness probe is used to **prevent the system from routing traffic too early**. Do not use "port is open" as the sole criterion for business readiness. How the server handles or defers requests during the transition state depends on the server and deployment configuration.

## 4. Which Milestones Belong to Spring MVC vs. WebFlux?

| Aspect | Spring MVC / Servlet | Spring WebFlux / Reactive |
| --- | --- | --- |
| Web context | `ServletWebServerApplicationContext` | `ReactiveWebServerApplicationContext` |
| Web server factory | `ServletWebServerFactory` | `ReactiveWebServerFactory` |
| Typical default server | Embedded Tomcat | Embedded Reactor Netty |
| HTTP entry point | Servlet container invokes `DispatcherServlet` | HTTP server/adapter invokes `HttpHandler` |
| Central handler | `DispatcherServlet` + `HandlerMapping` | `DispatcherHandler` + reactive `HandlerMapping` |
| Endpoint registration | `@GetMapping`, `@RequestMapping`, MVC functional routes | `@GetMapping` or `RouterFunction` |
| Server-ready milestone | `ServletWebServerInitializedEvent` | `ReactiveWebServerInitializedEvent` |
| Full app-ready milestone | `ApplicationReadyEvent`, readiness | Same as MVC |

Specific class and package names can change between **Spring Boot 3.x and 4.x**. The lifecycle mechanism and boundaries between server, handler, and readiness remain similar. WebFlux **does not require Netty**, and MVC **is not synonymous with Tomcat**: the framework decides how HTTP is processed; the server decides how connections are accepted.

## 5. Java 17+ Example: Observing Each Milestone on a Runnable MVC App

The example below uses **Spring Boot 3.5.x** to demonstrate with a standalone Maven application. Spring Boot 4.x changes some package and starter names, noted at the end of this section.

### 5.1. Create the Project

Create the `startup-timeline` directory with two files:

```text
startup-timeline/
├── pom.xml
└── src/main/java/com/example/startup/StartupTimelineApplication.java
```

Contents of `pom.xml`:

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
    <artifactId>startup-timeline</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

This is a **complete** POM, suitable for Java 17 and Maven. If generated via Spring Initializr, you can use the Maven wrapper (`mvnw`) instead of a pre-installed Maven binary.

### 5.2. Create the Application Class and Listeners

```java
package com.example.startup;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.web.context.WebServerInitializedEvent;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping;

@SpringBootApplication
@RestController
public class StartupTimelineApplication {

    public static void main(String[] args) {
        System.out.println("01 BEFORE_RUN");
        SpringApplication.run(StartupTimelineApplication.class, args);
        System.out.println("06 AFTER_RUN");
    }

    @GetMapping("/hello")
    public String hello() {
        return "Hello from MVC";
    }

    @EventListener
    public void whenWebServerInitialized(WebServerInitializedEvent event) {
        System.out.println("02 WEB_SERVER_INITIALIZED port="
                + event.getWebServer().getPort());
    }

    @EventListener
    public void whenApplicationStarted(ApplicationStartedEvent event) {
        System.out.println("03 APPLICATION_STARTED");
    }

    @Bean
    public ApplicationRunner inspectRoute(RequestMappingHandlerMapping mappings) {
        return args -> {
            boolean hasHello = mappings.getHandlerMethods().keySet().stream()
                    .anyMatch(info -> info.getPatternValues().contains("/hello"));
            System.out.println("04 RUNNER route /hello registered=" + hasHello);
        };
    }

    @EventListener
    public void whenApplicationReady(ApplicationReadyEvent event) {
        System.out.println("05 APPLICATION_READY");
    }
}
```

Explanation:

- `WebServerInitializedEvent`: reads the **port currently used by the server**, instead of guessing from a property.
- `ApplicationStartedEvent`: context refreshed successfully, but runners have not executed yet.
- `ApplicationRunner`: verifies that Spring MVC already has the `/hello` mapping.
- `ApplicationReadyEvent`: runners have completed; this is the application-ready milestone.
- `SpringApplication.run(...)` returns only after the startup sequence finishes or throws an error.

Run from the `startup-timeline` directory:

```bash
mvn spring-boot:run
```

If port `8080` is free, the lines **printed by the application** appear in this order:

```text
01 BEFORE_RUN
02 WEB_SERVER_INITIALIZED port=8080
03 APPLICATION_STARTED
04 RUNNER route /hello registered=true
05 APPLICATION_READY
06 AFTER_RUN
```

Spring/Tomcat log lines may interleave, and the port value changes if configured differently. The example does not print a "handler registered" line at the exact instant of registration; it **proves that by the time ApplicationRunner runs, the route is already registered**.

In another terminal, test:

```bash
curl -s http://localhost:8080/hello
```

Response body:

```text
Hello from MVC
```

Stop with Ctrl+C. If the port is occupied, run `mvn spring-boot:run -Dspring-boot.run.arguments=--server.port=8081` and call port `8081`. Do not assume a "port already in use" error means the controller failed to register.

**Version note:** the import `org.springframework.boot.web.context.WebServerInitializedEvent` in the example is for Boot **3.x**. In Boot **4.x**, the corresponding class is in `org.springframework.boot.web.server.context.WebServerInitializedEvent`; the main MVC starter is `spring-boot-starter-webmvc`. When switching versions, use consistent BOM/starter versions and imports, avoiding mixing 3.x and 4.x dependencies.

## 6. WebFlux Example: Swapping the HTTP Layer While Keeping the Overall Startup Order

In a **separate project** using `spring-boot-starter-webflux`, routes can be declared with `RouterFunction`. The snippet below is an **additional bean inside an `@Configuration` class** of a WebFlux project, not a standalone Java program:

```java
@Bean
RouterFunction<ServerResponse> routes() {
    return RouterFunctions.route(
            RequestPredicates.GET("/hello"),
            request -> ServerResponse.ok().bodyValue("Hello from WebFlux")
    );
}
```

Corresponding imports: `org.springframework.context.annotation.Bean`, `org.springframework.web.reactive.function.server.RouterFunction`, `RouterFunctions`, `RequestPredicates`, and `ServerResponse`.

In WebFlux, the server (typically Reactor Netty) accepts requests and invokes the `HttpHandler`/`WebHandler` pipeline. `DispatcherHandler` or the functional router selects the handler. Framework-managed handlers **do not open TCP sockets themselves**. The embedded server is still created and started during refresh, after which Boot publishes `ReactiveWebServerInitializedEvent`; `ApplicationReadyEvent` still arrives after the runners.

Do not put both the MVC starter and WebFlux starter into a project just to compare startup: Boot typically prioritizes **Servlet/MVC** when both are on the classpath. Two separate projects let you observe each stack accurately.

## 7. Reading Logs, Events, and Ports: Which Evidence Should You Trust?

| Observation | What You Can Conclude | What You Cannot Conclude Yet |
| --- | --- | --- |
| `main()` just started | The JVM has launched the program | Context has refreshed or HTTP is listening |
| Factory bean or controller bean created | Spring is setting up the application | Socket is open |
| Log "Tomcat initialized..." or similar message | Container has been initialized to some degree | Runners have completed or readiness is ACCEPTING |
| `WebServerInitializedEvent` and `getWebServer().getPort()` | That context's server is ready and provides the actual port | Business dependencies, startup tasks, or readiness have completed |
| `ApplicationStartedEvent` | Context refresh succeeded | `ApplicationRunner`/`CommandLineRunner` finished |
| `ApplicationReadyEvent` | Boot finished running runners and signaled ready | All external dependencies will remain healthy in the future |
| TCP connect or `curl` succeeds | Endpoint is reachable at the time of the check | Business readiness/health is sound |

**Logs are not a stable API**: wording and log line placement in Tomcat, Jetty, and Netty change across versions. For reliable logic, use lifecycle events and health/readiness; to investigate at the TCP layer, use `curl`, `ss`, `netstat`, or appropriate network tools.

If `server.port=0` is set, the operating system picks an **available port**. The configured port remains `0`, while the actual port must be retrieved from `WebServerInitializedEvent`/`WebServer.getPort()` after the server has started. Never try to access `localhost:0`.

When using `management.server.port` on a different port from the main application, Spring Boot may have **multiple web contexts/servers**; a listener can receive multiple `WebServerInitializedEvent` instances. Check `event.getApplicationContext()`, the context, or the namespace to identify the right server.

## 8. Readiness, Liveness, and Request Handling During Startup

Spring Boot supports availability states:

- **Liveness = CORRECT:** context has refreshed; the process is considered alive.
- **Readiness = REFUSING_TRAFFIC:** startup is not finished, or the application should not receive traffic.
- **Readiness = ACCEPTING_TRAFFIC:** Boot has completed runners, allowing the deployment platform to route traffic.

Example: an `ApplicationRunner` runs a cache-initialization task taking 10 seconds. The server may already be in the listening phase before that task finishes, yet readiness can still report **not accepting traffic**. Kubernetes readiness probes must rely on the readiness signal to avoid routing requests too early. Do not treat an open TCP port as a sufficient test of business readiness.

With Spring Boot Actuator and appropriate health probe configuration, endpoints like `/actuator/health/liveness` and `/actuator/health/readiness` can serve the orchestrator. You can use `/actuator/mappings` (when enabled and exposed) to inspect the list of routes recognized by Spring.

These probes only represent the **configured** state. They do not automatically guarantee that all external partners or databases are always operational. Evaluate readiness and dependencies according to system requirements; avoid putting external dependencies into liveness probes and causing cascading restarts.

## 9. Intervening in the Right Place to Customize Startup

| Need | Appropriate Extension Point | Why |
| --- | --- | --- |
| Change port, bind address | `server.port`, `server.address` | Configure the server before startup |
| Change connector/threads/TLS per server | `WebServerFactoryCustomizer` or server-specific properties | Customize before or when the factory creates the server |
| Register a specialized Servlet/Filter in MVC | `ServletRegistrationBean`, `FilterRegistrationBean`, `ServletContextInitializer` | Declare via proper Servlet container mechanisms |
| Register MVC/WebFlux endpoints | `@RestController` + `@GetMapping`, or functional routes | Let the framework build handler mappings; do not manage sockets manually |
| Need actual port after server start | `WebServerInitializedEvent` | Designed specifically to read `WebServer.getPort()` |
| Initialization work with a deadline before readiness | `ApplicationRunner` / `CommandLineRunner` with reasonable execution time | Runs before `ApplicationReadyEvent` |
| Load balancer should route requests only when ready | Readiness probe / availability state | Distinguishes open port from business readiness |
| Measure duration of each startup step | `ApplicationStartup`, `BufferingApplicationStartup`, Actuator `/actuator/startup` | Provides measured data instead of inferring from log line counts |

**Be careful with heavy work inside lifecycle callbacks**: slow listeners on `ApplicationStartedEvent`, `WebServerInitializedEvent`, or slow bean initialization can delay startup; if a listener throws an exception, the entire application may fail to start. Never try to open a port manually inside a controller's `@PostConstruct` to "start the server earlier"; that breaks Boot's lifecycle management.

## 10. Common Failure Scenarios and How to Diagnose Them

### 10.1. Server "Initialized" Yet `curl` Is Refused

The log may only describe a container initialization stage, the listener is not serving yet, startup subsequently failed, the port differs from expected, or the server bound only to an unreachable address. Check the **final logs**, `WebServerInitializedEvent`, `server.port`/`server.address`, and the process actually owning the port. If startup throws an exception, do not treat early logs as a sign of success.

### 10.2. `@GetMapping` Exists Yet HTTP Returns 404

The route may not have been component-scanned, may lie outside the root package, may have a different context path/prefix, may restrict the HTTP method, or the project may be using WebFlux/MVC unexpectedly. Inspect the actual mappings (`RequestMappingHandlerMapping` or Actuator `/actuator/mappings`) and the full URL; do not change the port when the cause is routing.

### 10.3. Port Is Open Yet Business Requests Fail

An `ApplicationRunner` may still be preparing data, a dependent service may not be ready, or readiness may not allow routing traffic yet. Inspect `ApplicationReadyEvent` and readiness state, and configure clear timeouts/failure policies and health checks. Never run infinite tasks in a runner: that can leave the application permanently unready.

### 10.4. `@PostConstruct` Runs Before/After Tomcat Logs Unexpectedly

`@PostConstruct` is an initialization callback for **a single bean**, not a master clock for the entire web server. It depends on when that bean is created; some beans may be created early, others late or lazily. Do not try to deduce when the socket starts listening solely from a service bean's callback.

### 10.5. `server.port=0` Yet Configuration Prints 0

`0` is a request for the operating system to allocate a port, not the HTTP serving port. Read the real value from `WebServerInitializedEvent` or from the runtime state updated by Boot. If the system has a separate management context, select the right event/server.

### 10.6. Switched Starters and Now There Is No Server

With `spring.main.web-application-type=none`, Boot runs as an application without a web server; there is no HTTP port or `WebServerInitializedEvent`. If HTTP is required, you need the right web starter and web application type. If you see "missing web server factory bean", check dependencies and excluded auto-configurations.

### 10.7. Server Is Listening Yet Firewall Blocks Access

Successful socket binding only confirms the process opened the address/port **inside the environment where it runs**; firewalls, Docker port mappings, Kubernetes Service/Ingress, or reverse proxies can still block external access. Inspect the network layer instead of confusing it with handler registration.

## 11. Self-Check Checklist

1. **When does server creation happen?** During `ApplicationContext.refresh()`, typically via the web application context's `onRefresh()` and `WebServerFactory`.
2. **Does `@GetMapping("/hello")` bind port 8080 itself?** No. It contributes to route mapping; the server factory and web server lifecycle manage the port.
3. **Is registering `DispatcherServlet` the same as mapping `/hello`?** No. They are two layers: the entry-point servlet and MVC's route mapping.
4. **Which event is appropriate for reading the actual port?** `WebServerInitializedEvent`, then `getWebServer().getPort()`.
5. **Does `ApplicationStartedEvent` mean runners have finished?** No. Runners execute **after** that event.
6. **What does `ApplicationReadyEvent` tell us beyond server initialized?** Boot has finished running the runners and is preparing to publish the readiness state accepting traffic.
7. **Must the WebFlux embedded server be Reactor Netty?** No; it is the common default, while other adapters/servers can be configured.
8. **Why might an app log "started" yet still receive no traffic from the load balancer?** The readiness probe may still be refusing; routing, firewall, health, and startup tasks must also be considered.

## 12. Official Documentation

- Spring Boot — [SpringApplication and application event order](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- Spring Boot — [Embedded Web Servers](https://docs.spring.io/spring-boot/how-to/webserver.html)
- Spring Boot — [Actuator Endpoints, lifecycle/probe states](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- Spring Boot — [Startup endpoint](https://docs.spring.io/spring-boot/api/rest/actuator/startup.html)
- Spring Framework — [Spring MVC DispatcherServlet](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet.html)
- Spring Framework — [WebFlux Reactive Core / HttpHandler](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- Spring Framework — [Bean lifecycle and SmartLifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- Spring Boot API — [ServletWebServerApplicationContext (3.5)](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/servlet/context/ServletWebServerApplicationContext.html)

**Technical conclusion to remember:** Spring Boot **creates the web server during refresh**, **sets up HTTP infrastructure and route mappings during context initialization**, and **starts the server within the refresh lifecycle**. `WebServerInitializedEvent` signals the server is ready with an actual port; `ApplicationReadyEvent`/readiness signals the entire application has finished startup. These are distinct milestones and must be observed with the corresponding tools.