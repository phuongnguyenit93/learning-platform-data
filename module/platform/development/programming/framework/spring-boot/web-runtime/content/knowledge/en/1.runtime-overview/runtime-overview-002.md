# The relationship between the application, Spring Framework, and the web server

A Spring Boot application running on the Servlet stack consists of multiple components with distinct responsibilities. The **application** contains the product's configuration and business logic; **Spring Framework** manages objects, dependencies, and web handling using the Spring MVC model; **Spring Boot** bootstraps and auto-configures the appropriate components; and the **web server/Servlet container** accepts HTTP connections and invokes the application's Servlet Filters and Servlets.

Understanding this boundary clearly helps answer practical questions: who opens port 8080, who creates the controller, where requests travel, why adding a starter brings in Tomcat, whether DispatcherServlet is a web server, and what changes when packaging the application as a JAR or a WAR.

## 1. Four components and their responsibilities

| Component | Primary responsibility | Examples |
|---|---|---|
| Application | Declares configuration, endpoints, services, repositories, and business rules | DemoApplication, HelloController, OrderService |
| Spring Framework | Provides IoC/DI, ApplicationContext, AOP, events, Spring MVC, and abstractions | ApplicationContext, @Component, DispatcherServlet, @Transactional |
| Spring Boot | Bootstraps the application, manages dependencies, auto-configuration, externalized configuration, packaging, and running the embedded server | SpringApplication.run, @SpringBootApplication, spring-boot-starter-web |
| Web server / Servlet container | Opens sockets, receives HTTP, manages Servlet lifecycle, filter chain, worker threads, and sends responses | Tomcat, Jetty, Undertow |

You can view the dependency direction as:

~~~text
Our application
    |
    | declares beans, controllers, configuration
    v
Spring Framework
    |
    | provides container, Spring MVC, and abstractions
    v
Spring Boot
    |
    | bootstrap + auto-configure + server integration
    v
Web server / Servlet container
    |
    | accepts connections and invokes Servlet Filters / Servlets
    v
HTTP request and response
~~~

The diagram above illustrates responsibilities; it does not mean Spring Framework depends on Spring Boot in every application. Spring Framework can run standalone; Spring Boot builds on top of Spring Framework to reduce configuration and standardize startup and deployment.

## 2. The application holds configuration and business logic

A Spring Boot application is the code owned by the development team. It typically defines:

- **Entry point:** the class with `main()` that calls `SpringApplication.run(...)`.
- **Configuration:** beans, security configuration, datasources, serialization, caching, and integrations.
- **Web layer:** controllers, request mappings, validation, and HTTP data conversion.
- **Application/service layer:** use cases and business orchestration.
- **Persistence/integration layer:** repositories, database clients, message brokers, and external services.
- **Domain model:** core business state and rules.

For example, a controller simply describes the endpoint and delegates work to a service:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    public OrderResponse findById(@PathVariable long id) {
        return orderService.findById(id);
    }
}
~~~

The controller does not open sockets itself, does not parse the HTTP protocol itself, and does not create Spring beans itself. Those responsibilities belong to the web infrastructure and Spring container. The controller is only invoked once the request has passed through upstream layers and been routed by Spring MVC to the corresponding handler.

## 3. Spring Framework manages objects and processes requests

### 3.1. IoC container and Dependency Injection

Spring Framework provides an IoC container. The container creates, configures, wires, and manages the lifecycle of objects registered as beans.

ApplicationContext is the central interface commonly used to interact with the container. Beans can be declared via:

- `@Component`, `@Service`, `@Repository`, `@Controller`, and corresponding stereotypes.
- `@Bean` inside a `@Configuration` class.
- Other bean registration mechanisms provided by the framework or integrated libraries.

Dependency Injection allows objects to receive dependencies from the container instead of instantiating them everywhere with `new`. Constructor injection makes dependencies explicit and facilitates testing:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;

    public OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    public OrderResponse findById(long id) {
        Order order = orderRepository.findById(id)
            .orElseThrow(() -> new OrderNotFoundException(id));
        return OrderResponse.from(order);
    }
}
~~~

In this example, the Spring container creates `OrderRepository`, creates `OrderService` with that repository, and then creates the controller with the service. The application does not need to wire every object manually.

By default, many Spring beans have singleton scope: one shared instance within the ApplicationContext. Therefore, you should not store request-specific data in mutable fields of a singleton service/controller. Multiple requests can run concurrently on different threads; shared beans must be thread-safe and should keep request state in local variables or an appropriately scoped abstraction.

### 3.2. Spring MVC and DispatcherServlet

For Servlet applications using Spring MVC, DispatcherServlet is the Front Controller. The Servlet container invokes it when a request matches the registered mapping.

General steps inside Spring MVC:

1. DispatcherServlet receives the request.
2. HandlerMapping locates the appropriate handler, usually a controller method.
3. HandlerAdapter invokes the handler.
4. Argument resolvers read path variables, query parameters, headers, and body, converting them into Java parameters.
5. The controller calls the service and receives the result.
6. Return value handlers, HttpMessageConverter, or ViewResolver convert the result into a response body/view.
7. The Servlet container sends the HTTP response back to the client.

`@RestController` typically returns data converted via HttpMessageConverter—for example, Java objects to JSON using Jackson when the appropriate dependency is on the classpath.

DispatcherServlet **is not a web server**. It is a Servlet running inside a Servlet container. Tomcat or an equivalent container is what accepts HTTP connections at the server layer and manages the Servlet lifecycle.

### 3.3. Spring Framework is not just for web

Spring Framework also provides many capabilities that applications can use outside of HTTP handling:

- AOP and transaction abstractions.
- Validation and events.
- Resource abstractions.
- Scheduling and task execution.
- Integration with persistence, messaging, and other systems via appropriate modules.

A Spring Boot application does not have to be a web application. If it only runs batch jobs, command-line tasks, or workers, it can still use the Spring container without opening an HTTP server.

## 4. Spring Boot wires the components at startup

### 4.1. Role of Spring Boot

Spring Boot does not replace Spring Framework. It adds a way to initialize and configure applications based on the classpath, existing beans, and properties:

- **Starter dependencies** group libraries that commonly go together.
- **Auto-configuration** creates default configurations when matching conditions are met.
- **Externalized configuration** reads configuration from properties, YAML, environment variables, and supported sources.
- **Embedded server integration** creates and starts the web server right inside the application process.
- **Executable archive** packages the application along with its dependencies to run with Java.

For instance, `spring-boot-starter-web` puts Spring MVC and Boot's default embedded server on the classpath. If the application uses the default Tomcat, Boot configures the server and integrates Tomcat with the Spring ApplicationContext.

A starter is not a server; it is a dependency descriptor. Nor is Tomcat created by the `@RestController` annotation; it appears because of the web runtime and Boot's corresponding configuration.

### 4.2. @SpringBootApplication

This annotation combines three key features:

- `@SpringBootConfiguration`: marks the source configuration class of the application.
- `@EnableAutoConfiguration`: allows Boot to apply auto-configuration based on conditions.
- `@ComponentScan`: scans for components in the application class's package and subpackages according to default rules.

Entry point example:

~~~java
@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

`SpringApplication.run(...)` is the starting point of the bootstrap process. It prepares the Environment, creates the appropriate ApplicationContext, loads bean definitions, applies auto-configuration, and refreshes the context. For a Servlet web application, a specialized context creates and manages the web server. When startup completes, the application is ready to accept requests.

Do not assume that `@SpringBootApplication` itself contains the entire server or all controllers. The annotation enables configuration and bean-scanning mechanisms; the concrete components are created by the container and auto-configuration when the corresponding conditions hold.

### 4.3. Conditional auto-configuration

Auto-configuration is not simply "if a dependency is present, always create the bean." Configurations are typically based on conditions such as:

- Presence or absence of a class on the classpath.
- Whether the application is a web application.
- Whether a corresponding bean has already been declared by the user.
- Whether properties enable/disable a capability or specify a particular value.

For example, if the application declares its own `SecurityFilterChain` bean, Boot's default security configuration can back off for that part. Similarly, switching server implementations or configuring custom beans can cause default auto-configuration to no longer apply.

When a bean does not appear as expected, inspect the condition evaluation report, classpath, properties, and custom beans before concluding the framework does not support it.

## 5. What do the web server and Servlet container do?

### 5.1. Web server vs. Servlet container

The web server is responsible for accepting network connections and exchanging HTTP. The Servlet container is the runtime that executes Jakarta Servlets: managing Servlets, Filters, listeners, mappings, request/response objects, and lifecycles.

Tomcat combines the role of a web server with a Servlet container. Jetty can fulfill a similar role. In a Spring MVC application, the embedded server usually provides the Servlet container for DispatcherServlet and the application's filters.

Typical server/container responsibilities:

- Bind to the configured address and port.
- Accept TCP connections and read HTTP requests.
- Manage connectors, thread pools, and connection limits.
- Create `HttpServletRequest`/`HttpServletResponse`.
- Execute Servlet Filters in registration order.
- Invoke the mapped Servlet, such as DispatcherServlet.
- Send responses and manage network resources.
- Manage lifecycle during application startup or shutdown.

The server does not inherently understand "which customer owns order 42." That is the responsibility of the application/service/repository and business security policies.

### 5.2. Embedded server

With the executable JAR model, the web server runs embedded inside the same JVM as the application:

~~~text
Single JVM process
    |
    +-- Spring Boot
    |     |
    |     +-- ApplicationContext
    |     +-- Spring MVC
    |     +-- Controllers / Services / Repositories
    |
    +-- Embedded Tomcat
          |
          +-- Connector / HTTP handling
          +-- Servlet container
          +-- DispatcherServlet
          +-- Servlet Filters
~~~

Common run command:

~~~bash
java -jar application.jar
~~~

The application and server are started, monitored, and stopped as a single process. This simplifies deployment because you do not need to install a separate Tomcat and copy a WAR into it. An embedded server is still a real server, with ports, connectors, thread pools, TLS, and operational configuration.

### 5.3. External server

Another model is packaging a WAR and deploying it into a Servlet container managed by the operational environment:

~~~text
External Tomcat
    |
    +-- Application Context
          |
          +-- SpringBootServletInitializer
          +-- Spring ApplicationContext
          +-- Spring MVC / DispatcherServlet
          +-- Controllers / Services
~~~

When running this way, the server container is started independently and loads the WAR application. With Spring Boot, a WAR application typically extends `SpringBootServletInitializer` to provide the configuration source to the servlet container.

Both models share the same Spring MVC application code, but differ in who owns the web server lifecycle:

- Embedded: the Spring Boot application initializes and manages the embedded server.
- External: the environment/container starts the server, then loads the WAR application.

Do not assume an embedded-JAR application can simply be dropped directly into Tomcat's `webapps` directory. Proper WAR packaging and bootstrap setup are required.

## 6. From startup to receiving requests

### 6.1. Startup flow

General startup flow of a Servlet Spring Boot application:

~~~text
JVM runs main()
    |
SpringApplication.run(...)
    |
Prepare Environment and configuration
    |
Create ServletWebServerApplicationContext
    |
Register and create bean definitions
    |
Apply auto-configuration
    |
Refresh ApplicationContext
    |
Create EmbeddedWebServer via WebServerFactory
    |
Register Servlets, Filters, Listeners
    |
Start server and open port
    |
ApplicationReadyEvent / application ready
~~~

Exact names and ordering of events/hooks can vary by version and custom lifecycles. The key takeaway: the web server is integrated into the initialization of the web ApplicationContext; it is not a separate Tomcat process that Spring MVC discovers at runtime.

Components like `ServletWebServerApplicationContext`, `ServletWebServerFactory`, and the specific Tomcat implementation are the integration glue between Boot and the server. Normally, applications only need to use the starter and configure properties; customize the factory only when there is an explicit requirement.

### 6.2. Request flow

Once the server is ready, an MVC request typically follows this flow:

~~~text
Browser / API client
    |
TCP connection -> Tomcat Connector
    |
HTTP parsing -> Servlet container
    |
Servlet Filter chain
    |
DispatcherServlet
    |
HandlerMapping -> HandlerAdapter
    |
Controller
    |
Service -> Repository / external system
    |
Return value / HttpMessageConverter
    |
Servlet response -> Tomcat -> HTTP response
~~~

Example `GET /api/orders/42`:

1. Tomcat receives the request and creates request/response objects per the Servlet API.
2. Filters run: encoding, logging, security, tracing, or application filters as configured.
3. DispatcherServlet finds the controller method matching `/api/orders/{id}`.
4. Spring MVC converts path variable `42` to type `long` if valid.
5. The controller calls `OrderService`.
6. The service performs business validation and calls the repository.
7. The controller returns a DTO; the message converter serializes the DTO to JSON.
8. The container writes status, headers, and response body back to the client.

If a filter rejects the request, it may never reach DispatcherServlet. If the controller calls a service and the service raises an error, an exception resolver/exception handler can translate the error into a response. Not every error is generated by Tomcat.

### 6.3. Request threads and bean scope

In a standard synchronous Spring MVC configuration, requests are handled on threads managed by the server. Tomcat uses a thread pool to serve multiple requests; each request does not spin up a new JVM or a new Spring ApplicationContext.

Because singleton beans are shared across requests, you should:

- Not store request data in mutable fields of singleton controllers/services.
- Use local variables for per-invocation data.
- Use request scope or an appropriate context mechanism when per-request state is genuinely needed.
- Not spawn arbitrary threads that access the request object after the request has finished.
- Configure thread limits, queues, and connection timeouts according to actual load and resources.

Async processing, virtual threads, or reactive stacks have different execution models; do not mechanically apply the "one thread per request" assumption to every architecture.

## 7. Web runtime configuration

Some common settings in `application.yml`:

~~~yaml
server:
  port: 8081
  address: 0.0.0.0
  servlet:
    context-path: /shop
~~~

Meaning:

- `server.port`: the port the embedded server listens on. Usually defaults to 8080 if unchanged.
- `server.address`: the network interface address to bind; `0.0.0.0` allows binding all IPv4 interfaces in supported environments.
- `server.servlet.context-path`: the prefix of the entire web application. With the configuration above, a controller mapping `/api/orders` is accessed via `/shop/api/orders`.

Distinguish between:

| Value | Role | Example |
|---|---|---|
| Server port | Port opened by the server on the machine | 8081 |
| Context path | Prefix of the web application | /shop |
| Servlet mapping/path | Path handled by a specific Servlet | /mvc/* if configured separately |
| Controller mapping | Path declared by a Spring MVC handler | /api/orders/{id} |

Do not add or subtract prefixes by guesswork. When a request returns 404, inspect port, context path, servlet mapping, and controller mapping separately.

Server-specific properties such as `server.tomcat.*` only apply when using Tomcat. If switching to Jetty or Undertow, the corresponding property group may differ. Avoid deep coupling to a specific implementation unless the application has special requirements.

## 8. Why does adding a starter bring in a server?

For the Servlet/MVC stack, the commonly used dependency is:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

The web starter pulls in the components needed for Spring MVC and the default embedded server (Tomcat in standard configurations). When the application is detected as a Servlet web application, Boot applies the corresponding auto-configuration and creates the web server.

You can swap Tomcat for Jetty or another supported server by excluding the default server dependency and adding the appropriate alternative server starter/dependency. Check the dependency tree to avoid accidentally bringing in multiple server implementations simultaneously.

Do not conflate these concepts:

- `spring-boot-starter-web`: dependency group for MVC/Servlet web.
- `spring-webmvc`: the MVC web processing framework.
- `spring-boot-starter-tomcat`: Boot's Tomcat integration dependency.
- Tomcat: the server/Servlet container executing the application.
- DispatcherServlet: Spring MVC's Servlet running inside the container.

## 9. Servlet stack vs. Reactive stack

Spring MVC on Servlets and Spring WebFlux are two different web models:

| Topic | Spring MVC / Servlet | Spring WebFlux |
|---|---|---|
| Programming model | Servlet request/response, typically synchronous | Reactive streams, non-blocking |
| Common servers | Tomcat, Jetty, Undertow | Reactor Netty; can also run on supported servers |
| Main APIs | HttpServletRequest, HttpServletResponse, MVC controllers | Mono, Flux, reactive handlers |
| Best suited when | Traditional MVC apps, blocking libraries, common request/response models | End-to-end non-blocking processing is needed and workload fits |
| Threading | Typically uses request threads from the server pool | Event-loop and schedulers; avoid blocking the event loop |

Do not pick WebFlux just because you heard it is "faster." If controllers call JDBC/blocking HTTP clients, non-blocking benefits can vanish and misconfiguration can stall the event loop.

When both MVC and WebFlux starters are on the classpath, Spring Boot typically defaults to an MVC application unless a different web application type is configured. Therefore, manage dependencies explicitly and avoid pulling in both stacks inadvertently via a transitive library.

## 10. Runnable example: minimal Spring Boot Servlet app

The example below uses Java 21 and Spring Boot 3.3.x. It demonstrates the application declaring a controller, Boot initializing the context, and embedded Tomcat accepting an HTTP request.

Structure:

~~~text
web-runtime-demo/
├── pom.xml
└── src/main/java/com/example/demo/
    ├── DemoApplication.java
    └── HelloController.java
~~~

**pom.xml**

~~~xml
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

    <groupId>com.example</groupId>
    <artifactId>web-runtime-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>21</java.version>
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
~~~

**DemoApplication.java**

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

**HelloController.java**

~~~java
package com.example.demo;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {
    @GetMapping("/hello")
    public Map<String, String> hello() {
        return Map.of("message", "Hello from Spring MVC");
    }
}
~~~

Run the application:

~~~bash
mvn spring-boot:run
~~~

In the default configuration, Boot starts embedded Tomcat on port 8080. Open another terminal and call:

~~~bash
curl -i http://localhost:8080/hello
~~~

Response body:

~~~json
{"message":"Hello from Spring MVC"}
~~~

The status is 200 OK; headers may vary by version and configuration. What you observe is that the request was accepted by the server, passed by the Servlet container to Spring MVC, the controller was invoked, and the Java result was serialized to JSON.

You can also package and run the same application:

~~~bash
mvn package
java -jar target/web-runtime-demo-1.0.0.jar
~~~

Both approaches run the application with an embedded server. The difference is that one runs via the Maven plugin, while the other runs the packaged executable JAR.

## 11. When to choose an embedded JAR vs. a WAR?

| Criterion | Executable JAR + embedded server | WAR + external Servlet container |
|---|---|---|
| Server startup | Spring Boot starts the embedded server | Operational environment starts the server |
| Deployment unit | Single artifact containing app and dependencies | WAR deployed into the container |
| Operations | Each instance is typically its own app process | Multiple web applications can share one container |
| Server config | Usually alongside app config / environment variables | Part of config belongs to the external container |
| Best suited for | Containers/Kubernetes, independent deployment, simple pipelines | Environments standardized on external containers or matching operational requirements |

Embedded JAR is the common default for Spring Boot due to self-contained packaging and standalone execution. WAR remains useful when infrastructure requires deploying into a shared Servlet container. Choose based on operational environment, upgrade workflows, observability, security, and server administration ownership.

## 12. Testing the runtime layers

Each type of test verifies a different part:

- **Unit test:** tests services/domain logic without starting a web server. Suitable for pure business logic.
- **MockMvc:** sends requests through Spring MVC and integrated filters in the test context without opening a real socket. Useful for checking mappings, validation, security filters, and responses.
- **@SpringBootTest with WebEnvironment.RANDOM_PORT:** starts the application context with a real server on a random port; tests HTTP integration, connectors, and runtime configuration more realistically.
- **End-to-end test:** runs the application in a production-like deployment environment to verify reverse proxies, TLS termination, context paths, health checks, and network policies.

HTTP tests with a real server require declaring the appropriate test dependency and using the port injected via `@LocalServerPort`. Do not hard-code port 8080 in tests, as it may collide or be disallowed in CI environments.

If the application starts but requests return 404, distinguish between route/controller mapping errors and context path or reverse proxy issues. If the port fails to open, check startup logs, port conflicts, bind address, and web server state before investigating controllers.

## 13. Troubleshooting issues at the right layer

| Symptom | Layer to check first | Example causes |
|---|---|---|
| App fails to open port | Boot startup / server | Server cannot be created, port in use, wrong bind address |
| Server receives request but returns 404 | Context path / Servlet mapping / Spring MVC | Wrong URL, controller not scanned, mapping differs from expected |
| 401 or 403 | Filter/security chain | Request blocked by authentication, authorization, or CSRF |
| Controller runs but dependency is null / bean not found | Spring container | Bean not scanned, missing configuration, ambiguous multiple beans |
| JSON formatted incorrectly | Spring MVC message conversion | Missing converter, content negotiation, or DTO mapping issue |
| Requests slow down under load | Server pool / blocking work / database | Thread pool exhausted, slow queries, blocking service calls |
| Works in IDE but fails as JAR | Packaging/runtime config | Missing resources, different profile/environment, wrong dependency scope |
| WAR behaves differently from JAR | External container integration | Different Servlet version, context path, classloader, or server config |

An effective investigation strategy is identifying where the request stops: before reaching the server, in a filter, in DispatcherServlet, in the controller/service, or in an external dependency. Use structured logs, request correlation IDs, health/readiness endpoints, and metrics to distinguish between layers.

## 14. Key takeaways

- The **application** defines endpoints, beans, configuration, and business logic.
- **Spring Framework** manages objects/dependencies and provides Spring MVC to map HTTP requests to controllers.
- **Spring Boot** bootstraps the ApplicationContext, applies auto-configuration, reads configuration, and integrates the embedded server.
- The **web server/Servlet container** opens ports, receives HTTP, manages filters/servlets/threads, and sends responses.
- DispatcherServlet is a Spring MVC Servlet, not a web server.
- With an embedded JAR, the app and server run in the same JVM; with a WAR, an external container owns the server lifecycle.
- MVC requests travel from connector/container through the filter chain, to DispatcherServlet, controller, service, and back via message converters.
- Choose between the Servlet or Reactive stack based on your processing model and actual dependencies.

When debugging or designing a runtime, always identify which component is responsible for the observed behavior. That helps you make changes at the right layer, avoiding controller-level workarounds for server issues or swapping servers just to fix a Spring MVC mapping mistake.