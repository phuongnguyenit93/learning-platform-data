# Setting the Application Type Explicitly When Needed

When starting a Spring Boot application, the framework needs to determine what type the application belongs to in order to select the right `ApplicationContext` and web infrastructure. An application can run under the Servlet/MVC model, the Reactive/WebFlux model, or as a non-web application. Spring Boot usually deduces this choice from libraries on the classpath, yet in certain situations you need to **set the application type explicitly**.

Spring Boot provides the `WebApplicationType` enum with three values:

- `SERVLET`: a web application based on the Servlet API, typically using Spring MVC.
- `REACTIVE`: a reactive web application, typically using Spring WebFlux.
- `NONE`: an application that does not run as a web application and does not initialize an embedded web server.

You can set the application type via the `SpringApplication` API, through `SpringApplicationBuilder`, or with the `spring.main.web-application-type` property.

This lesson belongs to the **SpringApplication** chapter of **Spring Boot Fundamentals**. We will explore how Boot deduces the application type automatically, when to override that choice, the effects on the ApplicationContext and web server, and how to apply this in batch, command-line, MVC, WebFlux, and integration-test applications.

## 1. What Is WebApplicationType?

`WebApplicationType` is a Spring Boot enum:

```java
import org.springframework.boot.WebApplicationType;
```

The enum has three values:

```java
public enum WebApplicationType {
    NONE,
    SERVLET,
    REACTIVE
}
```

Meaning of each value:

| Value | Application Model | Common Context and Infrastructure |
|---|---|---|
| `SERVLET` | Web application built on the Servlet API, typically Spring MVC | Servlet web application context and `ServletWebServerFactory` |
| `REACTIVE` | Reactive web application, typically Spring WebFlux | Reactive web application context and `ReactiveWebServerFactory` |
| `NONE` | Application not running as a web application | Non-web context, no embedded web server initialized |

The application type influences how `SpringApplication` creates the context, picks matching auto-configurations, and decides whether to initialize a web server.

### 1.1. Application type is not a bean type

`WebApplicationType` is not an annotation placed on a controller or service. It is a **SpringApplication/bootstrap-level** choice.

For example, a `@Service` class remains a Spring bean across Servlet, Reactive, or non-web applications if component scanning and registration conditions allow it.

Likewise, annotating a class with `@RestController` does not determine `WebApplicationType`. The application type is selected when Spring Boot prepares to create the ApplicationContext; web annotations are processed afterward within the resulting environment.

### 1.2. Do not equate WebApplicationType with dependencies

Having `spring-boot-starter-web` typically causes Boot to deduce `SERVLET`; having `spring-boot-starter-webflux` typically causes Boot to deduce `REACTIVE` when Spring MVC is absent from the classpath.

However, dependencies only supply the required classes and infrastructure. Selecting `WebApplicationType` is a separate `SpringApplication` decision. You can set the application type explicitly, provided you ensure compatible dependencies and server implementations accompany that choice.

## 2. How Does Spring Boot Deduce the Application Type Automatically?

If no application type is set, Spring Boot normally deduces it from classes present on the runtime classpath.

Conceptually:

```text
              Inspect runtime classpath
                         │
                         ▼
       Spring WebFlux DispatcherHandler present?
                         │
                         ▼
        Spring MVC DispatcherServlet present?
                         │
          ┌──────────────┴──────────────┐
          │                             │
          ▼                             ▼
 WebFlux yes, MVC no               MVC present
          │                             │
          ▼                             ▼
      REACTIVE                      SERVLET
          │
          │ If no web stack
          ▼
         NONE
```

Common primary rules:

- If WebFlux detection classes are present and Spring MVC detection classes are absent, Boot selects `REACTIVE`.
- If the Servlet API and required Servlet application classes are present, Boot selects `SERVLET`.
- If the corresponding web detection conditions are not met, Boot selects `NONE`.

This is a conceptual description. Exact classpath checks are implemented inside `WebApplicationType` and may evolve across Boot versions.

### 2.1. Spring MVC only

If the application has:

```groovy
implementation("org.springframework.boot:spring-boot-starter-web")
```

the runtime classpath typically contains Spring MVC and the Servlet API. Boot usually selects `SERVLET`.

The application uses components such as:

- `DispatcherServlet`.
- `ServletWebServerApplicationContext`.
- `ServletWebServerFactory`.
- Embedded Tomcat, Jetty, or Undertow depending on dependencies.

### 2.2. Spring WebFlux only

If the application has:

```groovy
implementation("org.springframework.boot:spring-boot-starter-webflux")
```

and Spring MVC is absent from the classpath, Boot usually selects `REACTIVE`.

The application uses components such as:

- `DispatcherHandler`.
- Reactive web application context.
- `ReactiveWebServerFactory`.
- Reactor Netty in common default setups, or another compatible reactive server.

### 2.3. Both Spring MVC and Spring WebFlux present

This is a common source of confusion.

If both Spring MVC and Spring WebFlux exist on the classpath, Spring Boot **prioritizes Spring MVC by default** and typically selects `SERVLET`.

Example:

```groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-webflux")
}
```

Perhaps the application only adds WebFlux to use `WebClient` inside an MVC application. Having the WebFlux dependency does not automatically switch the whole application to a reactive server.

If you want the application to run under WebFlux, you can set `REACTIVE` explicitly. Still, check configuration and compatible server dependencies; changing the enum alone does not turn blocking MVC code into reactive code.

### 2.4. No web dependencies

An application that only uses the Spring context, schedulers, batch jobs, or command-line runners without a web stack is typically deduced as `NONE`.

Dependency example:

```groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
}
```

In this case, the application can use `CommandLineRunner` or `ApplicationRunner` to perform work without opening an HTTP port.

### 2.5. Inspecting the deduced type

You can inspect the application type by configuring `SpringApplication` before running:

```java
SpringApplication application =
        new SpringApplication(BatchApplication.class);

System.out.println(application.getWebApplicationType());
```

The returned value shows which type the `SpringApplication` instance currently holds. This is a simple diagnostic technique when verifying what the current classpath leads to.

Never guess the application type with certainty from a single dependency; inspect the runtime classpath and the actual value.

## 3. Why Set the Application Type Explicitly?

Automatic deduction fits most applications, yet there are cases where the default choice does not match the program's intent.

Common scenarios:

1. An application includes both `spring-boot-starter-web` and `spring-boot-starter-webflux`, yet you want to run WebFlux.
2. An application has a web dependency brought in for a secondary library, yet the current process only runs a batch job or CLI task.
3. A single codebase has multiple entry points: one process runs a web server, another runs a batch job.
4. Tests or tools need a non-web ApplicationContext to avoid starting a server.
5. You want to eliminate ambiguity when transitive dependencies change the classpath.
6. A library or plugin unexpectedly introduces web APIs onto the classpath and alters Boot's deduction.

Setting it explicitly documents bootstrap intent right in code or configuration, making it clearer to read and operate.

### 3.1. Example: batch application with unexpected web dependencies

Suppose a project uses a library that transitively pulls in the Servlet API or Spring MVC. The actual application only needs to run a job:

```java
@SpringBootApplication
public class ImportJobApplication {

    public static void main(String[] args) {
        SpringApplication.run(ImportJobApplication.class, args);
    }
}
```

If Boot recognizes the classpath as a Servlet application, it can create a web context and attempt to initialize an embedded server—whereas the program only needs to run a data import task and exit.

You can set `NONE` to declare explicitly that this is a non-web process.

### 3.2. Example: wanting WebFlux when both stacks are present

If an application is genuinely built around the reactive stack, yet a dependency pulls Spring MVC onto the classpath, the default choice may be Servlet.

Setting `REACTIVE` explicitly tells Boot to create a reactive web context. Nevertheless, verify controllers, server dependencies, and corresponding auto-configurations to keep the application consistent.

### 3.3. Do not use WebApplicationType to mask architectural issues

Setting `NONE` does not turn a blocking application into a proper batch architecture; setting `REACTIVE` does not automatically make every `RestController` non-blocking. The enum only chooses the ApplicationContext/web bootstrap model.

If an application has unnecessary dependencies, review the dependency graph. Setting the application type explicitly clarifies bootstrap selection, but it does not replace dependency management and sound architecture.

## 4. Approach 1: Setting the Application Type with SpringApplication

The direct approach is instantiating `SpringApplication`, calling `setWebApplicationType(...)`, and then running the application.

Non-web example:

```java
package com.example.batch;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ImportJobApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ImportJobApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);

        application.run(args);
    }
}
```

Steps:

1. Create `SpringApplication` with configuration sources.
2. Call `setWebApplicationType(WebApplicationType.NONE)`.
3. Call `run(args)` to bootstrap the application.

For Servlet or Reactive, substitute the matching enum value:

```java
application.setWebApplicationType(WebApplicationType.SERVLET);
```

or:

```java
application.setWebApplicationType(WebApplicationType.REACTIVE);
```

### 4.1. Why not use static SpringApplication.run(...)?

The shorthand:

```java
SpringApplication.run(ImportJobApplication.class, args);
```

is convenient when accepting defaults. However, the static method exposes no instance on which to call `setWebApplicationType(...)` before `run`.

When setting the application type via API, instantiate `SpringApplication` as shown above.

### 4.2. A reusable helper

If you have multiple entry points, you can create a helper method to launch `SpringApplication`:

```java
public final class ApplicationLauncher {

    private ApplicationLauncher() {
    }

    public static ConfigurableApplicationContext runNonWeb(
            Class<?> source,
            String... args
    ) {
        SpringApplication application = new SpringApplication(source);
        application.setWebApplicationType(WebApplicationType.NONE);
        return application.run(args);
    }
}
```

Then:

```java
public static void main(String[] args) {
    ApplicationLauncher.runNonWeb(ImportJobApplication.class, args);
}
```

This is an optional organizational pattern. For small applications, configuring directly in `main` is usually easier to follow. Do not introduce a separate abstraction if you only have one entry point.

## 5. Approach 2: Using SpringApplicationBuilder

`SpringApplicationBuilder` provides a fluent API to configure and run the application.

Example:

```java
package com.example.batch;

import org.springframework.boot.WebApplicationType;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ImportJobApplication {

    public static void main(String[] args) {
        new SpringApplicationBuilder(ImportJobApplication.class)
                .web(WebApplicationType.NONE)
                .run(args);
    }
}
```

The `.web(...)` method accepts a `WebApplicationType`.

Options:

```java
new SpringApplicationBuilder(Application.class)
        .web(WebApplicationType.NONE)
        .run(args);
```

```java
new SpringApplicationBuilder(Application.class)
        .web(WebApplicationType.SERVLET)
        .run(args);
```

```java
new SpringApplicationBuilder(Application.class)
        .web(WebApplicationType.REACTIVE)
        .run(args);
```

This approach works well when chaining additional builder settings such as default properties, initializers, listeners, or parent/child contexts.

### 5.1. Combining with default properties

Example:

```java
new SpringApplicationBuilder(ImportJobApplication.class)
        .web(WebApplicationType.NONE)
        .properties(
                "app.import.batch-size=500",
                "app.import.dry-run=false"
        )
        .run(args);
```

`properties(...)` sets default properties for the application. Properties from higher-precedence sources can still override them according to Spring Boot's Environment rules.

The application type is set separately via `.web(...)`; the two settings serve distinct purposes.

## 6. Approach 3: Configuring via spring.main.web-application-type

If you want to switch the application type by environment without modifying Java code, use the property:

```properties
spring.main.web-application-type=none
```

Or YAML:

```yaml
spring:
  main:
    web-application-type: none
```

Common values:

| Property Value | Corresponding Enum |
|---|---|
| `none` | `WebApplicationType.NONE` |
| `servlet` | `WebApplicationType.SERVLET` |
| `reactive` | `WebApplicationType.REACTIVE` |

Running a JAR example:

```bash
java -jar application.jar --spring.main.web-application-type=none
```

You can also pass it via an environment variable using relaxed binding:

```bash
SPRING_MAIN_WEB_APPLICATION_TYPE=none
```

### 6.1. Using profiles to choose the application type

A single codebase can define different configurations per profile:

```yaml
# application-batch.yml
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

Run batch:

```bash
java -jar application.jar --spring.profiles.active=batch
```

Run web:

```bash
java -jar application.jar --spring.profiles.active=web
```

This works cleanly when profiles correspond to well-defined deployment modes. However, if the two modes have very different dependencies or lifecycles, splitting them into two application entry points or two artifacts may be easier to operate.

### 6.2. The property does not add dependencies automatically

Setting:

```properties
spring.main.web-application-type=reactive
```

does not automatically add WebFlux, Reactor Netty, or a reactive server implementation to the classpath.

Without compatible dependencies and infrastructure, the context may fail to start or lack the required server factory.

Likewise, setting `servlet` without a Servlet web stack and embedded server can lead to errors when Boot tries to create the web server.

### 6.3. Avoid setting the same choice in multiple places

In a project, the application type can be set via:

- `SpringApplication#setWebApplicationType(...)`.
- `SpringApplicationBuilder.web(...)`.
- `spring.main.web-application-type`.
- Startup configuration supplied by frameworks or tests.

Pick one primary place to configure it so operators can understand it easily. If you set conflicting values via both API and property, check the actual behavior of your Boot version rather than relying on assumptions about precedence.

## 7. Impact on ApplicationContext

`WebApplicationType` determines which context class Spring Boot creates.

### 7.1. SERVLET

With `SERVLET`, Boot creates a context suited for Servlet applications, typically `ServletWebServerApplicationContext`.

This context integrates with the Servlet API and embedded web server. Spring MVC can register components like `DispatcherServlet`, handler mappings, message converters, and related web beans when auto-configuration conditions match.

Conceptual flow:

```text
SpringApplication
      │
      ▼
WebApplicationType.SERVLET
      │
      ▼
ServletWebServerApplicationContext
      │
      ▼
ServletWebServerFactory
      │
      ▼
Embedded web server
      │
      ▼
DispatcherServlet / Spring MVC
      │
      ▼
HTTP requests
```

### 7.2. REACTIVE

With `REACTIVE`, Boot creates a context designed for reactive web applications, typically `ReactiveWebServerApplicationContext`.

The reactive stack uses abstractions such as `DispatcherHandler`, `WebHandler`, and `ReactiveWebServerFactory`. With the standard WebFlux starter, Reactor Netty is typically the default server unless overridden.

Conceptual flow:

```text
SpringApplication
      │
      ▼
WebApplicationType.REACTIVE
      │
      ▼
ReactiveWebServerApplicationContext
      │
      ▼
ReactiveWebServerFactory
      │
      ▼
Reactive web server
      │
      ▼
DispatcherHandler / WebFlux
      │
      ▼
Reactive HTTP requests
```

### 7.3. NONE

With `NONE`, Boot creates a non-web ApplicationContext and does not initialize an embedded web server.

Conceptual flow:

```text
SpringApplication
      │
      ▼
WebApplicationType.NONE
      │
      ▼
Non-web ApplicationContext
      │
      ▼
Bean definitions / dependency injection
      │
      ▼
ApplicationRunner / CommandLineRunner
      │
      ▼
Batch, CLI, or background task
```

The application still gets dependency injection, `@Configuration`, `@Bean`, `@Service`, `Environment`, events, and standard Spring context features. `NONE` only changes the web bootstrap model.

### 7.4. Context comparison table

| Aspect | SERVLET | REACTIVE | NONE |
|---|---|---|---|
| Web application context | Yes | Yes | No |
| Embedded web server | Yes, if a matching server factory exists | Yes, if a matching reactive server factory exists | No |
| Primary stack | Servlet/MVC | Reactive/WebFlux | Core Spring context |
| `DispatcherServlet` | Typically present with Spring MVC | Not the primary dispatcher | Not configured as an MVC web app |
| `DispatcherHandler` | Not the primary dispatcher | Typically present with WebFlux | Not configured as a reactive web app |
| Supports `CommandLineRunner` | Yes | Yes | Yes |
| Dependency injection | Yes | Yes | Yes |
| Suited for batch/CLI | Possible, though carries unnecessary web infrastructure | Possible, though carries unnecessary web infrastructure | Ideal when no web server is needed |

Specific components also depend on dependencies, conditions, and application configuration. This table outlines the bootstrap model rather than guaranteeing that every web bean is created in every project.

## 8. Complete Example: Batch Application Running with NONE

Suppose you have a job that imports data from a file and needs no HTTP port.

### 8.1. Project structure

```text
src/main/java/com/example/importer/
├── ImportJobApplication.java
├── service/
│   └── ImportService.java
└── config/
    └── ImportConfiguration.java
```

### 8.2. Main class

```java
package com.example.importer;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ImportJobApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ImportJobApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);

        application.run(args);
    }
}
```

### 8.3. Data processing service

```java
package com.example.importer.service;

import org.springframework.stereotype.Service;

@Service
public class ImportService {

    public void importData() {
        System.out.println("Importing data...");
        // Perform actual import logic.
        System.out.println("Data import completed.");
    }
}
```

### 8.4. Running the job after context initialization

```java
package com.example.importer;

import com.example.importer.service.ImportService;
import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

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

When run:

```bash
java -jar import-job.jar
```

The application creates a non-web context, injects `ImportService` into `ImportRunner`, and executes the task after context refresh. No embedded server is opened just to run the job.

### 8.5. Distinguishing NONE from closing the context immediately

`NONE` does not mean `SpringApplication` skips lifecycle management. The context is still refreshed, singleton beans are created according to configuration, runners execute, and the context is closed when the application terminates properly.

If the job must keep the process alive for ongoing background processing, you must design a waiting or lifecycle mechanism explicitly. Do not assume `NONE` automatically keeps a process running indefinitely.

## 9. Example: Forcing the Application to Run WebFlux When Both Stacks Are Present

Suppose the classpath contains both MVC and WebFlux:

```groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-webflux")
}
```

By default deduction, Boot normally picks Servlet because Spring MVC is present.

If the goal is a reactive application, you can configure:

```java
@SpringBootApplication
public class ReactiveApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ReactiveApplication.class);

        application.setWebApplicationType(WebApplicationType.REACTIVE);

        application.run(args);
    }
}
```

Or via property:

```yaml
spring:
  main:
    web-application-type: reactive
```

### 9.1. Verify the server implementation

A reactive web application requires an appropriate `ReactiveWebServerFactory`. For example, with Reactor Netty, the standard `spring-boot-starter-webflux` dependency supplies the default server runtime.

If you exclude Reactor Netty or swap the server implementation, make sure another dependency provides a compatible reactive server factory.

If only an MVC embedded server exists without a matching reactive server factory, forcing `REACTIVE` can prevent the context from starting.

### 9.2. Do not confuse WebClient with a WebFlux server

A Spring MVC application can use `WebClient` to invoke HTTP services asynchronously while still running on the Servlet stack.

Having the `WebClient` class or `spring-webflux` dependency does not force the application to be `REACTIVE`. What matters is the web application type Spring Boot selects and the server infrastructure the application intends to use.

This is why Spring Boot prefers MVC when both MVC and WebFlux are present: many applications only want `WebClient` rather than switching their server stack to reactive.

## 10. What NONE Does Not Do

When setting `WebApplicationType.NONE`, understand its exact scope.

`NONE`:

- Does not create a Servlet or Reactive web application context.
- Does not initialize an embedded web server as part of a web context.
- Does not turn the Spring container into a Spring-less Java program.
- Does not disable dependency injection.
- Does not exclude `@Controller` classes from component scanning automatically.
- Does not remove web dependencies from the runtime classpath.
- Does not act as a runtime business feature flag.
- Does not alter business logic inside services.

A `@RestController` class can still be discovered as a component if its package lies within the scan scope. However, because the application uses a non-web context, it is not wired as an active HTTP endpoint on an embedded server.

If a non-web application should not register controllers or web infrastructure, organize packages, scan configurations, or conditions to exclude those components.

### 10.1. NONE is not a way to remove dependencies

If your goal is shrinking artifact size or removing web libraries from a batch application, remove unnecessary dependencies from the module/build. Setting `NONE` only chooses a non-web context; the JARs still remain on the runtime classpath.

For example, if a batch module needs no MVC, separate its dependencies:

```groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
    // Do not add spring-boot-starter-web if the module needs no HTTP.
}
```

Separating modules makes the dependency graph and deployment intent clearer.

## 11. SpringApplicationBuilder and Multiple Entry Points

A single codebase can offer multiple startup programs.

Example:

```text
com.example.application
├── ApplicationConfiguration.java
├── WebApplication.java
└── BatchApplication.java
```

Both entry points can share services/configurations while choosing different web types.

### 11.1. Web entry point

```java
public class WebApplication {

    public static void main(String[] args) {
        new SpringApplicationBuilder(ApplicationConfiguration.class)
                .web(WebApplicationType.SERVLET)
                .run(args);
    }
}
```

### 11.2. Batch entry point

```java
public class BatchApplication {

    public static void main(String[] args) {
        new SpringApplicationBuilder(ApplicationConfiguration.class)
                .web(WebApplicationType.NONE)
                .run(args);
    }
}
```

This cleanly expresses two bootstrap modes. Ensure shared configurations do not depend on web-only beans. If a service uses `ServletRequest` or reactive server infrastructure, it cannot operate inside a non-web context where that dependency is absent.

### 11.3. When should you split into separate modules?

If web and batch have vastly different dependencies, configurations, security, and lifecycles, splitting into separate modules or artifacts is usually easier to manage:

```text
application-core
    ├── domain services
    ├── repositories
    └── shared configuration

application-web
    ├── spring-boot-starter-web
    └── WebApplication

application-batch
    ├── spring-boot-starter
    └── BatchApplication
```

Then each artifact has a tailored classpath, Boot needs little deduction in tricky setups, and operators can tell immediately which process needs a server.

## 12. Setting the Application Type in Integration Tests

When writing tests, you often do not want to open a real server if you only need to verify bean wiring or service logic.

With `@SpringBootTest`, you can specify the web environment:

```java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class ImportServiceIntegrationTest {
}
```

`WebEnvironment.NONE` tells the test context not to initialize a web environment. This fits integration tests that need a Spring context without a server.

Other `SpringBootTest.WebEnvironment` options include:

- `MOCK`: creates an appropriate web application context without starting a real server.
- `RANDOM_PORT`: starts a server on a random port.
- `DEFINED_PORT`: starts a server on the configured port.
- `NONE`: creates no web environment.

This is test bootstrap configuration. Its purpose is close to selecting a non-web context for tests, though it does not directly replace every `SpringApplication` setting in the main application.

### 12.1. When a real Servlet or Reactive test is needed

If you need to test HTTP integration, use `RANDOM_PORT` or `DEFINED_PORT` depending on your needs. With `MOCK`, you can test MVC/WebFlux infrastructure without opening a real network server.

Servlet example:

```java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class HttpIntegrationTest {
}
```

Non-web example:

```java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class ServiceIntegrationTest {
}
```

Match the test environment to your goal: testing service wiring needs no server; testing live endpoints needs an appropriate web environment.

## 13. Configuring Application Type via Properties and Configuration Sources

`spring.main.web-application-type` belongs to the `spring.main` property namespace. It can be set in any Spring Boot configuration source:

- `application.properties`.
- `application.yml`.
- Profile-specific configuration files.
- Environment variables.
- System properties.
- Command-line arguments.

`application.properties` example:

```properties
spring.main.web-application-type=none
```

System property:

```bash
java -Dspring.main.web-application-type=none -jar application.jar
```

Command-line argument:

```bash
java -jar application.jar --spring.main.web-application-type=none
```

Environment variable:

```bash
SPRING_MAIN_WEB_APPLICATION_TYPE=none
```

In containerized applications, you can pass the environment variable via deployment config instead of hardcoding the application type in code.

### 13.1. Properties and programmatic API

You can set the type via API:

```java
application.setWebApplicationType(WebApplicationType.NONE);
```

or via property:

```properties
spring.main.web-application-type=none
```

If both are configured, avoid setting conflicting values in multiple places. The cleanest practice is having one authoritative configuration source per deployment mode and checking the actual context type at startup.

Especially if a `SpringApplication` is created and configured programmatically inside a shared launcher, document which properties are allowed to override it under your application's policy. Do not leave operators guessing between multiple configuration sources.

## 14. Observing the Actual Context Type and Web Server

You can print the context type after the application starts:

```java
ConfigurableApplicationContext context =
        application.run(args);

System.out.println(context.getClass().getName());
```

Context classes you might encounter:

- `ServletWebServerApplicationContext`.
- `ReactiveWebServerApplicationContext`.
- `AnnotationConfigApplicationContext` or an equivalent non-web context.

Exact class names depend on the Boot version and configuration. Use type checks if inspecting programmatically:

```java
if (context instanceof WebServerApplicationContext webContext) {
    System.out.println("Web server: " + webContext.getWebServer().getPort());
} else {
    System.out.println("Application does not use WebServerApplicationContext");
}
```

Required imports:

```java
import org.springframework.boot.web.context.WebServerApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;
```

In business code, you rarely need to inspect the context class. This example is useful for learning and diagnosing bootstrap issues.

### 14.1. Observing via startup logs

When running a web application, Spring Boot typically logs that the embedded server started and which port it is listening on.

When set to `NONE`, you will not see Tomcat/Jetty/Netty startup logs for an application web server. The context can still print normal startup logs and runners are still called.

Do not treat “no Tomcat log seen” as the sole proof; verify the context type and web application configuration.

## 15. Common Errors When Setting WebApplicationType

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Batch app still opens an HTTP port | Boot deduced `SERVLET` from the classpath | Set `NONE` or remove web dependencies from the batch module |
| Wanted WebFlux but app runs MVC | Both MVC and WebFlux are present; Boot defaults to MVC | Set `REACTIVE` if a reactive server is truly intended and check dependencies |
| `No qualifying bean of type ServletWebServerFactory` | `SERVLET` selected without a compatible server factory | Add a compatible embedded servlet server dependency or choose a different type |
| `No qualifying bean of type ReactiveWebServerFactory` | `REACTIVE` selected without a reactive server implementation | Add a compatible reactive server dependency |
| Set `NONE` yet controller beans still appear | Component scan still discovers controllers as components | Adjust scan packages/conditions if those beans are unneeded |
| App has no HTTP endpoints after setting `NONE` | This is the expected result of a non-web context | Use `SERVLET` or `REACTIVE` if a web server is needed |
| IDE runs web while JAR runs non-web (or vice versa) | Classpaths or properties differ between the two environments | Compare runtime dependencies, profiles, and `spring.main.web-application-type` |
| Property set yet type is not as expected | Another config source or programmatic launcher overrides it | Print/check `SpringApplication` and Environment types; unify config sources |
| Selected `REACTIVE` yet code blocks request threads | Application is calling blocking APIs | Review reactive design; the enum does not make blocking code non-blocking |
| Tests accidentally start a server | Tests use `RANDOM_PORT`/`DEFINED_PORT` or default web environment | Choose `@SpringBootTest(webEnvironment = NONE)` if no server is needed |

### 15.1. Missing ServletWebServerFactory error

Example message:

```text
ApplicationContextException:
Unable to start web server

Caused by:
NoSuchBeanDefinitionException:
No qualifying bean of type
'org.springframework.boot.web.servlet.server.ServletWebServerFactory'
available
```

This usually indicates Boot is creating a Servlet web context without a factory to build the server. Check:

- Is an embedded servlet container dependency present?
- Was Tomcat excluded without adding Jetty/Undertow?
- Are you forcing `SERVLET` in a module that only includes the core starter?
- Does a dependency scope restrict the server to compile time without runtime presence?

### 15.2. Missing ReactiveWebServerFactory error

If you force `REACTIVE` without a server implementation, a similar error appears for `ReactiveWebServerFactory`.

Check `spring-boot-starter-webflux` and the matching server dependency. Having only the `spring-webflux` API is not always enough to start an embedded reactive server.

### 15.3. Errors are not always caused by WebApplicationType

If an application fails to start, the cause might be bean dependencies, properties, a port already in use, database connections, or init callbacks. Do not change `WebApplicationType` just because startup failed; read the root exception and confirm which context type is being created.

## 16. Distinguishing WebApplicationType from Related Settings

Several properties/annotations have similar names yet govern different aspects.

| Configuration | Role |
|---|---|
| `spring.main.web-application-type` | Selects application type at bootstrap: none, servlet, reactive |
| `server.port` | Selects server port when a web server is present |
| `spring.main.banner-mode` | Controls banner display at startup |
| `spring.main.lazy-initialization` | Controls application-wide lazy initialization |
| `@ConditionalOnWebApplication` | Configuration condition based on the web environment |
| `@EnableWebMvc` | Customizes/enables Spring MVC configuration in a specific way |
| `@EnableWebFlux` | Customizes/enables Spring WebFlux configuration in a specific way |
| `spring.webflux.base-path` | Configures base path for WebFlux where applicable |

`server.port=0` does not turn the application into `NONE`; it remains a web application, with the server picking a random port.

`@ConditionalOnWebApplication` does not choose the application type either. It checks the web environment Spring Boot already established to decide whether a configuration applies.

## 17. Choosing the Application Type by Architecture

### 17.1. REST API using Spring MVC

Choose `SERVLET` when the application is built around Spring MVC, Servlet filters, a servlet container, and standard blocking APIs.

```java
SpringApplication application =
        new SpringApplication(ApiApplication.class);

application.setWebApplicationType(WebApplicationType.SERVLET);
application.run(args);
```

If only `spring-boot-starter-web` is present, Boot usually deduces this correctly. Setting it explicitly helps when both web stacks exist on the classpath or when locking down deployment intent.

### 17.2. Reactive API using Spring WebFlux

Choose `REACTIVE` when the application is designed to handle requests on the reactive stack and has a matching reactive server runtime.

```java
SpringApplication application =
        new SpringApplication(ReactiveApiApplication.class);

application.setWebApplicationType(WebApplicationType.REACTIVE);
application.run(args);
```

Do not pick `REACTIVE` merely because you want to use `Mono` or `Flux` in a service. An MVC application can still use Reactor types where appropriate; web application type is a server/context-level choice.

### 17.3. Batch job or command-line tool

Choose `NONE` when no HTTP server is required:

```java
SpringApplication application =
        new SpringApplication(BatchApplication.class);

application.setWebApplicationType(WebApplicationType.NONE);
application.run(args);
```

`CommandLineRunner` or `ApplicationRunner` can execute the job once the context is initialized.

### 17.4. Scheduler / background worker

A process running only schedulers or consumers can use `NONE` if no HTTP endpoints are needed. However, if you require actuator or health endpoints for an orchestration platform to probe, clearly design how the health/management server is exposed and select the appropriate context type.

Do not set `NONE` and still expect an embedded server to expose HTTP `/actuator/health`. If an HTTP health endpoint is required, design a web/management context fitting your deployment target.

## 18. Considerations with Actuator and Management Servers

Spring Boot Actuator can provide health, metrics, and management endpoints. When an application is non-web, HTTP endpoints do not automatically have a server to serve them.

Depending on operational requirements:

- Batch process that runs and exits: `NONE` may be appropriate.
- Long-running worker needing HTTP health checks: consider an appropriate web context/management server.
- Long-running worker checked by the platform via process signals or files/sockets: keep `NONE` and use a dedicated health mechanism.

The primary application type and management endpoint configuration must be designed together. Do not assume adding `spring-boot-starter-actuator` turns a non-web application into an HTTP server.

## 19. How Explicit Configuration Affects Auto-Configuration

Auto-configuration can be gated on web application conditions:

```java
@ConditionalOnWebApplication(type = Type.SERVLET)
```

or:

```java
@ConditionalOnWebApplication(type = Type.REACTIVE)
```

When you set `WebApplicationType`, you change the environment observed by these conditions. Consequently, certain auto-configurations are enabled or skipped depending on the application type.

Conceptual illustration:

```text
WebApplicationType.SERVLET
      │
      ├── Servlet web auto-configurations can match
      └── Reactive-only auto-configurations do not match

WebApplicationType.REACTIVE
      │
      ├── Reactive web auto-configurations can match
      └── Servlet-only auto-configurations do not match

WebApplicationType.NONE
      │
      ├── Non-web auto-configurations can match
      └── Web-only auto-configurations typically do not match
```

This explains why changing the application type alters the list of registered beans. It is the result of conditional auto-configuration, not the enum directly deleting user beans.

### 19.1. Component scanning remains a separate mechanism

A `@Service` or `@Component` class can still be scanned across all three application types. Specialized web configurations are what typically depend on `WebApplicationType` or matching web conditions.

Thus, if you want a component to exist only in web mode, consider placing appropriate conditions or profiles on that configuration/component. Do not assume `NONE` automatically skips all classes carrying web annotations.

## 20. A Decision Process for Selecting the Application Type

When building a new application or resolving discrepancies between an IDE and a JAR, follow these steps:

### Step 1 — Determine whether the process needs an HTTP server

- Needs HTTP endpoints: consider `SERVLET` or `REACTIVE`.
- Needs no HTTP endpoints: consider `NONE`.

### Step 2 — Identify the web programming model

- Spring MVC, Servlet filters, servlet container: `SERVLET`.
- Spring WebFlux and reactive server: `REACTIVE`.
- No web stack: `NONE`.

### Step 3 — Inspect the runtime classpath

Check the dependency tree to see which MVC, WebFlux, and server implementations are present. Pay special attention to transitive dependencies.

### Step 4 — Compare the default selection with your goal

If the classpath already leads to the right type, you can let Boot deduce it. Otherwise, set it explicitly via API or property.

### Step 5 — Ensure compatible dependencies

`SERVLET` requires an appropriate Servlet web server factory; `REACTIVE` requires a reactive web server factory; `NONE` requires no embedded web server.

### Step 6 — Verify the actual context

Inspect the context type, startup logs, and server port. Confirm the application runs under the expected model.

### Step 7 — Inspect auto-configuration and the bean graph

If changing the application type causes a bean to disappear, inspect the condition report, component scan, and web conditions. Do not conclude the bean disappeared solely because of the enum.

### Step 8 — Test across execution environments

Compare IDE, Gradle/Maven, executable JAR, container deployment, and integration tests. Keep properties, profiles, and runtime classpaths consistent.

## 21. Example Comparing Three Application Types in One Codebase

A demo project can split into three entry points for observation:

```text
src/main/java/com/example/demo/
├── shared/
│   └── GreetingService.java
├── servlet/
│   └── ServletApplication.java
├── reactive/
│   └── ReactiveApplication.java
└── batch/
    └── BatchApplication.java
```

Shared service:

```java
package com.example.demo.shared;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    public String greet() {
        return "Hello from shared service";
    }
}
```

Servlet entry point:

```java
package com.example.demo.servlet;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(scanBasePackages = "com.example.demo")
public class ServletApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ServletApplication.class);

        application.setWebApplicationType(WebApplicationType.SERVLET);
        application.run(args);
    }
}
```

Reactive entry point:

```java
package com.example.demo.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(scanBasePackages = "com.example.demo")
public class ReactiveApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ReactiveApplication.class);

        application.setWebApplicationType(WebApplicationType.REACTIVE);
        application.run(args);
    }
}
```

Batch entry point:

```java
package com.example.demo.batch;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(scanBasePackages = "com.example.demo")
public class BatchApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(BatchApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.run(args);
    }
}
```

This example demonstrates the bootstrap API. In a real application, avoid packaging all three entry points with broad component scanning if they contain controllers or configurations unsuitable for each mode. Separate packages, configurations, or modules so each entry point loads only what it needs.

## 22. Common Misconceptions

### 22.1. “Having spring-webflux means Boot always chooses REACTIVE”

Not necessarily. If Spring MVC is also on the classpath, Boot usually selects `SERVLET`. If you want a reactive server in that situation, set `REACTIVE` explicitly and check server dependencies.

### 22.2. “Setting NONE removes all web beans”

No. `NONE` selects a non-web context and skips initializing an embedded web server. Component scanning can still pick up classes with stereotype annotations; web conditions and application configuration determine which beans are registered.

### 22.3. “Setting REACTIVE automatically turns MVC controllers reactive”

No. `WebApplicationType` does not convert blocking code into non-blocking code. Handlers, return types, I/O, and dependencies must follow the reactive programming model.

### 22.4. “Setting SERVLET automatically adds Tomcat”

No. The application type only picks the context model. The runtime classpath still needs a compatible embedded servlet server implementation.

### 22.5. “server.port=0 is equivalent to NONE”

No. `server.port=0` still starts a web server and asks the OS for an available port. `NONE` creates no web server.

### 22.6. “WebApplicationType is a per-controller property”

No. It is a `SpringApplication` bootstrap choice applying to the `ApplicationContext` created for that run.

### 22.7. “Using NONE is optimal for every batch application”

Not always. If a batch worker needs HTTP health endpoints, a management server, or other web communication, design an appropriate model. `NONE` fits when the process truly needs no web server.

## 23. Practice Exercises

### Exercise 1 — Observing default deduction

Create a project with only `spring-boot-starter`, run the app, and print `SpringApplication.getWebApplicationType()`. Then add `spring-boot-starter-web` and observe the change.

### Exercise 2 — Comparing MVC and WebFlux on the classpath

Add both `spring-boot-starter-web` and `spring-boot-starter-webflux`. Observe the default selection. Then explicitly set `REACTIVE` and verify which context/server is selected.

### Exercise 3 — Running batch with NONE

Create a `CommandLineRunner` performing a brief task. Set `WebApplicationType.NONE`, run the JAR, and confirm no embedded web server starts.

### Exercise 4 — Trying three configuration styles

Run the same application using:
- `SpringApplication#setWebApplicationType`.
- `SpringApplicationBuilder.web(...)`.
- `spring.main.web-application-type`.

Note which configuration takes effect in each environment and keep one authoritative configuration source.

### Exercise 5 — Observing context types

Print `context.getClass().getName()` after startup. Compare `SERVLET`, `REACTIVE`, and `NONE`. Note server-specific beans appearing only in matching context types.

### Exercise 6 — Testing properties by profile

Create `application-batch.yml` and `application-web.yml` with different web application types. Run each profile and verify the resulting context.

### Exercise 7 — Testing without a server

Write `@SpringBootTest(webEnvironment = NONE)` for a service integration test. Then use `RANDOM_PORT` for an HTTP integration test and compare startup behavior.

### Exercise 8 — Distinguishing NONE from removing dependencies

Set `NONE` while keeping `spring-boot-starter-web` on the classpath. Observe that the server does not start even though web classes remain in the dependency tree. Then remove the starter from the module and compare the artifact/runtime classpath.

## 24. Official References

- [Spring Boot API — WebApplicationType](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/WebApplicationType.html): the three values `NONE`, `SERVLET`, `REACTIVE` and how application types are deduced.
- [Spring Boot API — SpringApplication](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/SpringApplication.html): `setWebApplicationType(...)`, `getWebApplicationType()`, and application bootstrap.
- [Spring Boot API — SpringApplicationBuilder](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/builder/SpringApplicationBuilder.html): fluent configuration via `.web(...)`.
- [Spring Boot Reference — Developing Web Applications](https://docs.spring.io/spring-boot/reference/web/index.html): how Spring Boot configures Servlet and Reactive applications.
- [Spring Boot Reference — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@SpringBootTest` and web environments.

`WebApplicationType` lets you explicitly specify the bootstrap model Spring Boot should use. Let Boot deduce it when the classpath accurately reflects your architecture; set `SERVLET`, `REACTIVE`, or `NONE` explicitly when dependencies, entry points, or deployment environments cause the default selection to diverge from your application's intent. The key is picking the right enum value, ensuring matching infrastructure exists, and verifying the actual `ApplicationContext` after startup.
