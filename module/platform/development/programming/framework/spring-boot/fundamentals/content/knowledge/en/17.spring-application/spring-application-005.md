# WebApplicationType NONE, SERVLET, REACTIVE

`SpringApplication` is the common entry point of a Spring Boot application. When creating the application context, Spring Boot needs to determine which model the application will run under: a non-web application, a Servlet-based web application, or a reactive web application. This choice is represented by the `WebApplicationType` enum with three values:

- **`NONE`**: the application does not run as a web application and does not start an embedded web server.
- **`SERVLET`**: a web application based on the Servlet API, typically using Spring MVC.
- **`REACTIVE`**: a web application following the reactive model, typically using Spring WebFlux.

These three values determine the `ApplicationContext` type, how Spring Boot configures web infrastructure, and how the server is started. They are not merely three syntax options for controllers. Choosing the wrong one can prevent HTTP endpoints from being served, start the wrong server context type, or omit the request handling stack your code relies on.

## 1. WebApplicationType During Startup

In a Spring Boot application, `SpringApplication.run(...)` initializes and refreshes the application context. Before the context is ready, Boot needs to know the application type in order to choose the matching infrastructure.

```java
@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

If not specified explicitly, Spring Boot attempts to **deduce WebApplicationType from the classpath**. After selecting the type, Boot creates the matching context type and applies the corresponding auto-configurations.

```text
SpringApplication.run(...)
          │
          ▼
Determine WebApplicationType
          │
     ┌────┼─────────┐
     ▼    ▼         ▼
    NONE SERVLET  REACTIVE
     │    │         │
     ▼    ▼         ▼
Non-web Servlet   Reactive
context  web      web context
         context
     │    │         │
     ▼    ▼         ▼
Runner  Servlet   Reactive
        server    server
        startup   startup
```

The application type affects how the context is created from the very start. This is why you should decide your application's web model before configuring controllers, servers, or related dependencies.

## 2. NONE: Applications Not Running as Web Applications

`WebApplicationType.NONE` fits programs that use the Spring container without needing to accept HTTP requests through an embedded web server.

Common use cases:

- Batch jobs that read data, process it, and exit.
- Command-line applications.
- Workers consuming messages from queues or brokers.
- Schedulers running periodic tasks.
- Data migration or import/export tools.
- Applications initializing a Spring context for dependency injection, configuration properties, and lifecycle callbacks without exposing HTTP endpoints.

Example:

```java
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.SpringApplication;

@SpringBootApplication
public class BatchApplication {
    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(BatchApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.run(args);
    }
}
```

When running as NONE, Spring Boot creates a non-web application context. The application still has beans, dependency injection, configuration properties, events, and Spring lifecycles. It simply does not create a web server context to serve HTTP.

### 2.1. NONE still uses the Spring container

A common misconception is that NONE means a plain Java program without Spring. In reality, the Spring container still operates fully within its non-web scope.

Example of a batch task:

```java
@Service
public class ImportService {
    public void importData() {
        System.out.println("Importing records...");
        // Read file, validate, and write data.
    }
}
```

```java
@Component
public class ImportRunner implements CommandLineRunner {
    private final ImportService importService;

    public ImportRunner(ImportService importService) {
        this.importService = importService;
    }

    @Override
    public void run(String... args) {
        importService.importData();
    }
}
```

When the application context starts, Spring instantiates `ImportService` and `ImportRunner`, injects the dependency, and calls `CommandLineRunner.run(...)`. The task runs without needing any controller or HTTP server.

`ApplicationRunner` plays a similar role, except it receives parsed `ApplicationArguments`:

```java
@Component
public class StartupTask implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Application started without a web server");
    }
}
```

Either `CommandLineRunner` or `ApplicationRunner` can be used for work after the context is initialized. If the task must run long-term, manage shutdown, retries, and completion status properly; NONE does not automatically decide when a batch job should exit.

### 2.2. NONE does not start an embedded web server

With NONE, Spring Boot does not create a Servlet web server context or a Reactive web server context. Consequently:

- No embedded Tomcat/Jetty/Undertow is started for the application.
- No `DispatcherServlet` acts as a front controller for Spring MVC.
- No `DispatcherHandler` acts as a WebFlux server request handler.
- Controller endpoints are not served over HTTP in that application context.

If the application has web dependencies on the classpath yet explicitly sets NONE, those dependencies still reside on the runtime classpath. However, having web classes on the classpath does not mean a web server will be started.

### 2.3. NONE fits workers and batch jobs

A message-consuming worker can use Spring Boot to configure broker clients and services:

```java
@SpringBootApplication
public class MessageWorkerApplication {
    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(MessageWorkerApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.run(args);
    }
}
```

The worker can still maintain connections to a message broker, run listener containers, or run schedulers. NONE only states that the application is not a web application in Boot's model; it does not mean the application cannot use the network or external connections.

## 3. SERVLET: Web Applications Based on the Servlet API

`WebApplicationType.SERVLET` is used for web applications built on the Servlet API. This is the familiar Spring MVC model.

Common components:

- Servlet API and Servlet web application context.
- Spring MVC's `DispatcherServlet`.
- Controllers using `@Controller` or `@RestController`.
- Embedded servers such as Tomcat, Jetty, or Undertow when dependencies and configuration match.
- Servlet filters, listeners, and other Servlet web components.

Controller example:

```java
@RestController
@RequestMapping("/api/orders")
public class OrderController {
    @GetMapping("/{id}")
    public String getOrder(@PathVariable long id) {
        return "Order " + id;
    }
}
```

In a Servlet web application, HTTP requests are received by the Servlet container. With Spring MVC, `DispatcherServlet` dispatches requests to the matching controller.

```text
HTTP request
     │
     ▼
Servlet container
(Tomcat / Jetty / Undertow)
     │
     ▼
DispatcherServlet
     │
     ▼
HandlerMapping
     │
     ▼
Controller method
     │
     ▼
HTTP response
```

### 3.1. Spring MVC and the Servlet context

With SERVLET, Boot typically creates `ServletWebServerApplicationContext`. This context integrates the Spring container with an embedded Servlet web server.

When the context refreshes, the web server is created and started according to context lifecycle. Hence, if server configuration is invalid or the port is already in use, the application can fail during startup.

Common properties:

```properties
server.port=8080
server.servlet.context-path=/shop
```

YAML example:

```yaml
server:
  port: 8080
  servlet:
    context-path: /shop
```

With this configuration, the endpoint `/api/orders/1` can be accessed via base path `/shop` on port `8080`, provided the controller and server are configured properly.

### 3.2. Embedded servers and external Servlet containers

Spring Boot commonly packages an embedded server inside an executable JAR so it can be run with:

```bash
java -jar app.jar
```

Servlet applications can also be packaged as a WAR and deployed into an external Servlet container, depending on build and configuration. `WebApplicationType.SERVLET` describes the Servlet web model; it does not force you to run only on embedded Tomcat.

### 3.3. When should you choose SERVLET?

Choose SERVLET when:

- The application uses Spring MVC.
- APIs or websites are based on Servlet requests/responses.
- You rely on libraries requiring the Servlet API, Servlet filters, or Servlet container integration.
- The application already follows traditional MVC architecture and has no reason to switch to a reactive server stack.

Spring MVC can still handle certain reactive return types like `Mono` or `Flux`, depending on features and configuration. That does not turn an MVC application into a WebFlux application. The application context type and request processing stack remain Servlet if Boot selects SERVLET.

## 4. REACTIVE: Web Applications Following the Reactive Model

`WebApplicationType.REACTIVE` is for reactive web applications, typically built with Spring WebFlux.

WebFlux is designed for non-blocking execution and reactive streams. Typical components:

- `DispatcherHandler` as WebFlux's central request dispatcher.
- `Mono` and `Flux` representing Reactor publishers.
- A reactive server runtime, typically Reactor Netty in common default setups.
- A reactive web application context.
- Adapters supporting compatible reactive servers/runtimes.

Controller example:

```java
@RestController
@RequestMapping("/api/products")
public class ProductController {
    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @GetMapping("/{id}")
    public Mono<Product> getProduct(@PathVariable String id) {
        return productService.findById(id);
    }
}
```

This example assumes `ProductService` exposes a method returning `Mono<Product>` and is injected via constructor.

High-level processing flow:

```text
HTTP request
     │
     ▼
Reactive web server
(Reactor Netty or compatible server)
     │
     ▼
DispatcherHandler
     │
     ▼
HandlerMapping / HandlerAdapter
     │
     ▼
Reactive controller
     │
     ▼
Mono / Flux publisher
     │
     ▼
Reactive response
```

### 4.1. Reactive application context

With REACTIVE, Spring Boot creates `ReactiveWebServerApplicationContext`. This context integrates the Spring container with a reactive web server.

There is no `DispatcherServlet` acting as the main front controller like in Spring MVC. WebFlux uses `DispatcherHandler` alongside reactive adapters to route requests.

Endpoints can still use annotations like `@RestController`, `@GetMapping`, and `@PostMapping`. The difference lies in the web runtime, request processing model, and input/output types.

### 4.2. Reactive does not mean Reactor Netty only

Reactor Netty is the popular default choice when applicable, but WebFlux can run on other supported servers depending on dependencies and configuration.

Therefore, do not equate:

- REACTIVE with Reactor Netty exclusively.
- SERVLET with Tomcat exclusively.
- NONE with the absence of any network dependencies.

`WebApplicationType` describes the web application context type; the concrete server is determined by runtime dependencies and configuration.

### 4.3. Reactive does not automatically make all code non-blocking

Choosing REACTIVE does not turn blocking JDBC calls, blocking file I/O, or synchronous methods into non-blocking operations.

Unsuitable example if a blocking call runs directly on an event-loop thread:

```java
@GetMapping("/report")
public Mono<Report> getReport() {
    Report report = blockingRepository.loadReport();
    return Mono.just(report);
}
```

If `blockingRepository.loadReport()` performs blocking I/O, it can block the thread driving the reactive pipeline. You need proper reactive data access or to isolate blocking work onto an appropriate scheduler/executor while accounting for resource limits.

Reactive is an end-to-end programming model. Merely switching the enum to REACTIVE while leaving all code blocking delivers no non-blocking benefit.

## 5. Comparing NONE, SERVLET, and REACTIVE

| Criterion | NONE | SERVLET | REACTIVE |
|---|---|---|---|
| Application type | Non-web | Servlet web | Reactive web |
| Common application context | Non-web context, e.g. `AnnotationConfigApplicationContext` | `ServletWebServerApplicationContext` | `ReactiveWebServerApplicationContext` |
| Embedded web server | Not started | Started when server configuration matches | Started when reactive server configuration matches |
| Request handling | No Boot HTTP server | Servlet API, usually Spring MVC | Reactive web stack, usually Spring WebFlux |
| Front controller/dispatcher | No web dispatcher | `DispatcherServlet` | `DispatcherHandler` |
| Typical controller style | Does not serve HTTP endpoints | MVC controller, can return objects or supported types | WebFlux controller, typically returns `Mono`/`Flux` |
| Use cases | Batch, CLI, worker, scheduler | Websites, MVC REST APIs, Servlet integrations | Reactive APIs, streaming, non-blocking I/O |
| Main prerequisite | No web runtime needed | Requires Servlet web runtime | Requires reactive web runtime |

No single choice is universally superior. Choose based on your application's actual request-handling model and dependencies.

## 6. Spring Boot Deduces WebApplicationType from the Classpath

If the application type is not specified, Spring Boot inspects key classes on the classpath to deduce it.

At a high level:

- If WebFlux is present without Spring MVC or the Jersey Servlet stack, Boot usually selects REACTIVE.
- If a compatible Servlet web stack is present, Boot selects SERVLET.
- If neither Servlet nor reactive web application indicators are found, Boot selects NONE.

One noteworthy point: **if both Spring MVC and Spring WebFlux are on the classpath, Spring MVC normally takes precedence and Boot selects SERVLET**. Some MVC applications add the WebFlux dependency solely to use `WebClient`, with no intention of switching the entire server to reactive.

Illustrative scenario table:

| Classpath / Characteristics | Commonly Deduced Type |
|---|---|
| No Servlet web stack and no WebFlux | NONE |
| Spring MVC / Servlet stack present | SERVLET |
| WebFlux present without MVC / Jersey Servlet stack | REACTIVE |
| Both Spring MVC and WebFlux present | SERVLET by default precedence |

This is classpath-based deduction, not inspection of controller contents. A class annotated with `@RestController` is not enough to determine whether the application is SERVLET or REACTIVE.

### 6.1. Why can an application using WebClient still be SERVLET?

`WebClient` is a reactive HTTP client. A Spring MVC application can use `WebClient` to call external APIs while still receiving inbound requests via the Servlet stack.

Example:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
```

When both starters are present, Boot typically selects SERVLET because MVC takes precedence in the deduction rules. You can still use `WebClient` on the client side without turning the server into WebFlux.

If you genuinely want a reactive server, specify dependencies, application type, and configuration explicitly. Do not add the WebFlux starter and assume Boot will automatically switch to REACTIVE.

## 7. Explicitly Selecting the Application Type in Java

You can set the type directly on `SpringApplication`:

```java
@SpringBootApplication
public class WorkerApplication {
    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(WorkerApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.run(args);
    }
}
```

Other values:

```java
application.setWebApplicationType(WebApplicationType.SERVLET);
```

```java
application.setWebApplicationType(WebApplicationType.REACTIVE);
```

This is useful when you want to decide explicitly in bootstrap code—for instance, when the same module provides separate entry points for a worker and a web server.

### 7.1. Using SpringApplicationBuilder

`SpringApplicationBuilder` also supports choosing the web application type:

```java
new SpringApplicationBuilder(DemoApplication.class)
        .web(WebApplicationType.NONE)
        .run(args);
```

Similarly, you can pass SERVLET or REACTIVE.

Do not configure multiple entry points running together for one application without a clear purpose. Keep source classes, properties, and builder calls consistent.

## 8. Selecting the Application Type via Property

Spring Boot provides a property:

```properties
spring.main.web-application-type=none
```

Valid values are `none`, `servlet`, and `reactive`.

YAML:

```yaml
spring:
  main:
    web-application-type: none
```

This can be varied by profile:

```yaml
# application-worker.yml
spring:
  main:
    web-application-type: none
```

```yaml
# application-web.yml
spring:
  main:
    web-application-type: servlet
```

Then activate the desired profile:

```bash
java -jar app.jar --spring.profiles.active=worker
```

Or:

```bash
java -jar app.jar --spring.profiles.active=web
```

This property works well when a single artifact can run in different roles and the decision is made by the deployment environment.

If you both set the property and call `setWebApplicationType(...)` in code, check the behavior for your Boot version and bootstrap setup. To avoid confusing configuration, keep a single clear source of truth and verify the actual startup log/context type.

## 9. How Starter Dependencies Affect Deduction

Common starters:

| Starter | Primary Stack | Typical WebApplicationType When Used Alone |
|---|---|---|
| `spring-boot-starter` | Core Spring / Boot foundation | NONE |
| `spring-boot-starter-web` | Spring MVC, Servlet | SERVLET |
| `spring-boot-starter-webflux` | Spring WebFlux | REACTIVE |
| `spring-boot-starter-web` and `spring-boot-starter-webflux` | Both MVC and WebFlux present | SERVLET by default precedence |

Artifact names and dependency management can evolve across Spring Boot lines; use starters managed by your project version's BOM or plugin.

A transitive dependency can also pull Servlet or WebFlux indicator classes onto the classpath. When the deduced application type surprises you, inspect the runtime dependency graph rather than looking only at direct dependencies.

With Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

With Maven:

```bash
./mvnw dependency:tree
```

Look for web starters and related libraries. The goal is to pinpoint which class causes Boot to deduce SERVLET or REACTIVE.

## 10. Choosing SERVLET When Both MVC and WebFlux Are Present

This is a common scenario:

- An application uses `spring-boot-starter-web` to serve REST APIs with Spring MVC.
- It adds `spring-boot-starter-webflux` to use `WebClient`.
- Boot sees both stacks on the classpath.

By default, Boot prioritizes MVC and chooses SERVLET. This is usually the desired behavior because adding WebFlux for a client does not mean wanting to replace the server stack.

If a genuine WebFlux server is required, select it explicitly:

```java
@SpringBootApplication
public class ReactiveApplication {
    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(ReactiveApplication.class);

        app.setWebApplicationType(WebApplicationType.REACTIVE);
        app.run(args);
    }
}
```

However, selecting REACTIVE does not guarantee every Servlet/MVC bean in the application becomes compatible. Review dependencies, auto-configurations, and libraries that only work with the Servlet API. For a reactive server application, keep the classpath and integrations aligned with the WebFlux model.

## 11. NONE with Web Dependencies Can Still Have Unexpected Beans

Suppose a project includes `spring-boot-starter-web` yet wants to run a batch job. You can set:

```properties
spring.main.web-application-type=none
```

This selects a non-web context and does not start an embedded Servlet server. Nevertheless, the web dependencies remain on the classpath and their Java classes can still be loaded if referenced by code.

Moreover, beans declared via component scanning or application configuration can still be registered. If the application has components requiring a bean that only exists in a Servlet web context, startup can fail.

When converting an app from SERVLET to NONE:

1. Check beans with dependencies on `ServletContext`, `HttpServletRequest`, or web-specific scopes.
2. Check configurations using `@ConditionalOnWebApplication` or similar conditions.
3. Ensure runners/workers do not depend on controllers or server lifecycle.
4. If the batch module needs no web dependencies, consider splitting dependencies/modules for a cleaner classpath.

**NONE is not a filter that strips all web classes from the classpath.** It selects a non-web application context.

## 12. Conditional Configuration by Web Application Type

Spring Boot provides conditions to apply configuration only to a specific web application type.

Example:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnWebApplication(
    type = ConditionalOnWebApplication.Type.SERVLET
)
public class ServletOnlyConfiguration {
    @Bean
    public ServletFeature servletFeature() {
        return new ServletFeature();
    }
}
```

Similarly, you can check for reactive:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnWebApplication(
    type = ConditionalOnWebApplication.Type.REACTIVE
)
public class ReactiveOnlyConfiguration {
    @Bean
    public ReactiveFeature reactiveFeature() {
        return new ReactiveFeature();
    }
}
```

For non-web-only configuration:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnNotWebApplication
public class WorkerOnlyConfiguration {
    @Bean
    public WorkerFeature workerFeature() {
        return new WorkerFeature();
    }
}
```

These conditions are useful when authoring libraries shared across multiple application types. For example, a starter can provide a Servlet filter in SERVLET mode and a reactive web filter in REACTIVE mode.

Do not rely solely on `@ConditionalOnClass` if your real intent is to distinguish application context types. A class might exist on the classpath while the web application type is explicitly set to NONE.

## 13. Server Lifecycle by Application Type

With NONE, Spring creates a non-web context, initializes beans, and executes runners. There is no embedded web server listening for HTTP requests. The application terminates when the program lifecycle finishes—for example, once runners finish and no non-daemon threads or active resources keep the process alive.

With SERVLET, the context integrates a Servlet web server. When the context refreshes, the server is created and started; when the context closes normally, the server is stopped as part of the lifecycle.

With REACTIVE, the context integrates a reactive web server. The server starts during refresh and stops when the context closes.

```text
                         ApplicationContext
                                  │
                ┌─────────────────┼─────────────────┐
                ▼                 ▼                 ▼
               NONE            SERVLET           REACTIVE
                │                 │                 │
         Create non-web    Create Servlet     Create Reactive
            context          web context        web context
                │                 │                 │
         Initialize beans   Start server       Start server
                │                 │                 │
         Run Application   Accept HTTP req    Accept HTTP req
         Runner/Command    via Servlet stack  via reactive stack
                │                 │                 │
         No web server     Close context:     Close context:
         lifecycle         stop server        stop server
```

Do not use `CommandLineRunner` as a blocking loop to keep a server alive under NONE. If a worker must run continuously, use an appropriate listener/scheduler or lifecycle component and design graceful shutdown.

## 14. Impact on Controllers and Endpoints

Controller annotations compile normally across all three application types, but only SERVLET or REACTIVE contexts with matching web infrastructure actually serve HTTP endpoints.

| Code / Controller | NONE | SERVLET | REACTIVE |
|---|---|---|---|
| `@RestController` | No HTTP server to receive requests | Handled by Spring MVC if configured properly | Handled by WebFlux if configured properly |
| `@GetMapping` | Does not expose an HTTP endpoint | Mapped in MVC | Mapped in WebFlux |
| `HttpServletRequest` | No active Servlet request | Available in Servlet request lifecycle | Not WebFlux's primary request API |
| `Mono`/`Flux` return type | Does not create a reactive HTTP endpoint | MVC may support certain reactive return types | WebFlux uses reactive pipelines as its primary model |

If a bean under NONE invokes code requiring `HttpServletRequest`, no request context exists to supply it. Likewise, do not inject Servlet-specific components into a reactive application without an appropriate Servlet web context.

## 15. WebApplicationType in Testing

Spring Boot Test offers different web environment modes. Distinguish **application type** from **how tests create a server**.

Example test without a web environment:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class BatchServiceTests {
    // Test services and Spring beans without a web server.
}
```

`WebEnvironment.NONE` fits tests that need no web server. If you need to test Servlet or reactive endpoints, choose an appropriate test environment such as `MOCK`, `RANDOM_PORT`, or `DEFINED_PORT` depending on your goal.

Example test starting an embedded server on a random port:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class ApiIntegrationTests {
    // Send HTTP requests to the server started by the test.
}
```

`MOCK` creates a mock web application context matching the detected/configured stack without starting a real embedded server. `RANDOM_PORT` and `DEFINED_PORT` start a real server in the test context.

When writing tests, match the mode to what you want to verify:

- Plain Java service unit tests: usually need no Spring context.
- Testing dependency injection/configuration without HTTP: NONE or an appropriate context runner.
- Testing MVC controllers: use MockMvc or a Servlet mock web environment.
- Testing WebFlux: use WebTestClient and a reactive web test setup.
- End-to-end tests against a real server: use RANDOM_PORT/DEFINED_PORT.

### 15.1. Checking the ApplicationContext type

You can inspect the context type during an integration test or debug session:

```java
ConfigurableApplicationContext context =
        SpringApplication.run(DemoApplication.class, args);

System.out.println(context.getClass().getName());
```

This snippet is for observation; the context returned by `SpringApplication.run(...)` is the initialized application context.

Common classes:

- Non-web context: `AnnotationConfigApplicationContext` or an appropriate non-web context implementation.
- Servlet: `ServletWebServerApplicationContext`.
- Reactive: `ReactiveWebServerApplicationContext`.

Exact implementation class names can vary across versions or custom application contexts. Use the context type as a debugging signal, not as an API contract for business logic.

## 16. Common Errors When Choosing WebApplicationType

| Symptom | Possible Cause | What to Check |
|---|---|---|
| App has controllers but is unreachable over HTTP | WebApplicationType is NONE or no matching web server runtime is present. | Check `spring.main.web-application-type` and context type. |
| App intended for WebFlux starts MVC/Tomcat instead | MVC/Servlet stack is on the classpath and takes precedence during deduction. | Check runtime dependency tree; set REACTIVE explicitly if intended and verify compatibility. |
| Batch app still tries to start a web server | Classpath causes Boot to deduce SERVLET/REACTIVE. | Set NONE via property or `setWebApplicationType`. |
| Bean requiring `ServletContext` fails under NONE | Non-web context provides no Servlet web infrastructure. | Guard Servlet config with `@ConditionalOnWebApplication`. |
| WebFlux code fails or stalls due to blocking calls | REACTIVE does not make blocking APIs non-blocking. | Use reactive clients/repositories or isolate blocking work. |
| Port already in use | SERVLET/REACTIVE server cannot bind port. | Check `server.port`, listening processes, and startup logs. |
| Test exposes no endpoints even though controller compiles | Test context uses NONE or does not create a web environment. | Pick an appropriate `@SpringBootTest` web environment. |
| App has both MVC and WebFlux with unexpected behavior | Boot chooses SERVLET by default or dependency stacks conflict. | Inspect classpath and selected application type. |

### 16.1. Do not fix errors by blindly removing starters

If an application starts with the wrong type, check:

1. Which runtime dependencies are present.
2. Which type Boot deduced.
3. Whether properties or code override that type.
4. Which auto-configurations were applied.
5. Which actual context type and server were created.

Only then decide whether to remove a starter, set an explicit `WebApplicationType`, or split modules. A starter may provide classes your code needs even when its server stack is unused; removing it blindly can break compilation or runtime classes.

## 17. Example: One Artifact Serving Two Roles

A project can contain shared business services while exposing two entry points: a web application and a batch worker.

Illustrative layout:

```text
com.example.platform/
├── shared/
│   └── OrderService.java
├── web/
│   ├── WebApplication.java
│   └── OrderController.java
└── worker/
    ├── WorkerApplication.java
    └── OrderImportRunner.java
```

Web entry point:

```java
package com.example.platform.web;

@SpringBootApplication(scanBasePackages = "com.example.platform")
public class WebApplication {
    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(WebApplication.class);

        app.setWebApplicationType(WebApplicationType.SERVLET);
        app.run(args);
    }
}
```

Worker entry point:

```java
package com.example.platform.worker;

@SpringBootApplication(scanBasePackages = "com.example.platform")
public class WorkerApplication {
    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(WorkerApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.run(args);
    }
}
```

Both can share `OrderService`. However, not every bean should be scanned and initialized in both contexts. Controllers, Servlet filters, and request-scoped components should be gated or organized by package/configuration so they load only in the web application. Worker runners should likewise be gated so they do not execute inside the web process.

Example condition for web configuration:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnWebApplication(
    type = ConditionalOnWebApplication.Type.SERVLET
)
public class WebOnlyConfiguration {
    // Beans needed only in the Servlet application.
}
```

In production architectures, separating modules or artifacts often yields a cleaner dependency graph. This example illustrates code-sharing capabilities; it does not mean two main classes should always be packaged and scanned wholesale together.

## 18. Selection Guidelines

Choose `NONE` when the application only needs the Spring container to run tasks, workers, or command-line flows without an HTTP server.

Choose `SERVLET` when the application serves HTTP via the Servlet stack, especially with Spring MVC and Servlet libraries.

Choose `REACTIVE` when the application is designed for the reactive web stack, typically Spring WebFlux, and dependencies/request handling follow the non-blocking model.

Before deciding, answer:

- Does the application accept HTTP requests?
- If yes, do requests flow through the Servlet API or a reactive web stack?
- Does the runtime dependency graph contain both MVC and WebFlux?
- Does the application have beans depending on `ServletContext`, `HttpServletRequest`, or a reactive context?
- Does a single artifact need to run in multiple roles?
- Should the application type be deduced automatically or set explicitly?

## 19. Practice Exercises

### Exercise A — Running a NONE application

1. Create a Spring Boot app with a service and a `CommandLineRunner`.
2. Set `spring.main.web-application-type=none`.
3. Run the application and observe the runner.
4. Verify no embedded web server starts.
5. Add a controller and explain why its endpoint is not served over HTTP.

### Exercise B — Running a Servlet application

1. Add the Spring MVC dependency.
2. Create a `@RestController` with a GET endpoint.
3. Run the application as SERVLET.
4. Observe embedded server logs and call the endpoint.
5. Change `server.port` and verify the new port.

### Exercise C — Running a Reactive application

1. Create a project using WebFlux.
2. Create a controller returning `Mono<String>` or `Flux<String>`.
3. Choose REACTIVE and start the server.
4. Observe the context/server runtime.
5. Try adding a blocking call and explore how to handle it properly in the reactive model.

### Exercise D — Testing classpath detection

1. Run a project with only the base starter.
2. Add the Spring MVC starter.
3. Add the WebFlux starter alongside MVC.
4. Observe the type Boot deduces in each case.
5. Call `setWebApplicationType(REACTIVE)`, compare results, and check bean compatibility.

### Exercise E — Two roles in the same project

Create a web entry point and a worker entry point sharing a business service. Use SERVLET for the web app and NONE for the worker. Conditionally gate web-only and worker-only beans and verify each context initializes only the components it needs.

### Exercise F — Testing web environments

Write a test using `WebEnvironment.NONE` to verify a service, an MVC test using MockMvc, and a reactive test using WebTestClient. Compare contexts and request handling across the tests.

## 20. Takeaways

1. `WebApplicationType.NONE` creates a non-web application context and does not start an embedded web server.
2. `WebApplicationType.SERVLET` creates a Servlet web application context, typically used with Spring MVC and `DispatcherServlet`.
3. `WebApplicationType.REACTIVE` creates a reactive web application context, typically used with Spring WebFlux and `DispatcherHandler`.
4. Spring Boot normally deduces the type from the classpath; when both MVC and WebFlux are present, SERVLET usually takes precedence.
5. You can set it explicitly via `SpringApplication.setWebApplicationType(...)`, `SpringApplicationBuilder.web(...)`, or the `spring.main.web-application-type` property.
6. NONE still provides Spring beans, dependency injection, runners, and lifecycle; it just omits the web server.
7. REACTIVE does not automatically convert blocking code into non-blocking code.
8. Application context type affects web-specific beans, scopes, and auto-configuration conditions.
9. Dependencies can still reside on the classpath after choosing NONE; check beans requiring Servlet/reactive infrastructure.
10. Tests must select a web environment matching the behavior under test.

When reading startup logs or designing an entry point, identify whether **Spring Boot is running NONE, SERVLET, or REACTIVE**, then match that against the context type, dependency graph, and created web infrastructure. Picking the right type at bootstrap ensures controllers, servers, lifecycle, and auto-configurations align with your application model.
