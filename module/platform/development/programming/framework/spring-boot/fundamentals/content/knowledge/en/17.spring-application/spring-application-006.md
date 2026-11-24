# How the Classpath Affects Application Type Selection

When calling `SpringApplication.run(...)`, Spring Boot needs to determine which web model the application will run under. An application can use the Servlet stack (typically Spring MVC), the Reactive stack (Spring WebFlux), or run as an application without a web server. Unless specified explicitly, Spring Boot **relies on classes visible on the runtime classpath** to deduce the application type.

Therefore, adding or removing a starter can change how Spring Boot starts up even when your application class code remains untouched. For example, `spring-boot-starter-web` typically brings Spring MVC and a Servlet container onto the classpath, so the application is recognized as a Servlet application. `spring-boot-starter-webflux` puts Spring WebFlux on the classpath, which can lead to a Reactive application. If both MVC and WebFlux are present, Spring Boot defaults to preferring Servlet/MVC.

This lesson traces how Spring Boot chooses `WebApplicationType`, the marker classes used for detection, the effect of transitive dependencies, how to override the choice via configuration or Java API, which `ApplicationContext` type is created, and how this affects auto-configuration.

## 1. The Three WebApplicationType Values

Spring Boot defines the `WebApplicationType` enum with three values:

| Value | Meaning | Typical Applications |
| --- | --- | --- |
| `SERVLET` | Web application based on the Servlet API | Spring MVC, Servlet/Jersey applications |
| `REACTIVE` | Web application based on the reactive web stack | Spring WebFlux |
| `NONE` | Not a web application | Batch jobs, command-line tools, workers, or background apps |

Visualized:

~~~mermaid
flowchart TD
    A["SpringApplication starts"] --> B["Determine WebApplicationType"]
    B --> C{"Application type"}
    C -->|SERVLET| D["Servlet web context"]
    C -->|REACTIVE| E["Reactive web context"]
    C -->|NONE| F["Non-web ApplicationContext"]
    D --> G["Servlet web server / DispatcherServlet"]
    E --> H["Reactive web server / DispatcherHandler"]
    F --> I["No embedded web server initialized"]
~~~

The application type influences how Spring Boot creates the context, selects web auto-configurations, initializes the web server, and handles requests. It is not merely a label printed in logs.

### 1.1. SERVLET

`SERVLET` is typically chosen when the application has Spring MVC and Servlet API infrastructure. A typical Spring MVC application has:

- `DispatcherServlet` as the front controller.
- A Servlet container such as Tomcat, Jetty, or Undertow.
- `ServletWebServerApplicationContext` as the web context in standard Boot configuration.
- Controllers using `@Controller` or `@RestController`.

Common dependency example:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

This starter brings Spring MVC components and the default embedded Servlet server onto the runtime classpath according to the dependency management of the Spring Boot version in use.

### 1.2. REACTIVE

`REACTIVE` is for reactive web applications, usually using Spring WebFlux. This stack is designed for asynchronous processing and backpressure with Reactor.

Common components:

- `DispatcherHandler` as WebFlux's request dispatcher.
- Reactor types such as `Mono<T>` and `Flux<T>`.
- A reactive server such as Reactor Netty in the default starter configuration.
- `ReactiveWebServerApplicationContext` in standard Boot configuration.

Common dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

WebFlux is not required to run on Reactor Netty in every setup. Other reactive servers can be used if corresponding dependencies and configuration are supplied.

### 1.3. NONE

`NONE` means Spring Boot does not initialize the application as a Servlet or Reactive web application. This type fits:

- Command-line applications.
- Batch processing.
- Scheduled workers.
- Migration tools.
- Message consumers that do not serve HTTP.
- Applications needing Spring IoC, configuration, and auto-configuration without an embedded web server.

For instance, the application can still use `@Service`, `@Repository`, `ApplicationRunner`, and `@ConfigurationProperties` inside a non-web context. `NONE` does not disable the Spring container; it simply selects a non-web application context model.

## 2. What Is the Classpath in This Decision?

The classpath is the set of classes and resources visible to the class loader when the application runs. In a Spring Boot application, the runtime classpath typically includes:

- Classes compiled by the application itself.
- Direct dependency JARs.
- Transitive dependencies pulled in by starters.
- Resources in output directories or inside JARs.
- Libraries provided by the runtime/container depending on deployment style.

When deducing the application type, Spring Boot checks whether specific marker classes can be loaded. It does not read dependency names from Gradle/Maven build files, nor does it scan your controllers to decide.

Example:

~~~text
Application
├── spring-boot-starter-web
│   ├── spring-webmvc
│   ├── spring-web
│   └── embedded Servlet server
└── spring-boot-starter-webflux
    ├── spring-webflux
    └── Reactor libraries
~~~

Starters are convenience dependencies. Their transitive dependencies are what place the actual classes onto the classpath. Adding or removing a starter changes the set of classes Spring Boot sees.

### 2.1. Declaring a dependency does not mean its classes are always present at runtime

Distinguish classpaths by phase:

| Classpath | Purpose |
| --- | --- |
| Compile classpath | Supplies types needed to compile source code |
| Runtime classpath | Supplies classes and resources when running the application |
| Test compile/runtime classpath | Used for compiling and running tests; may hold extra dependencies |
| Annotation processor path | Holds processors run during compilation; not automatically on the runtime classpath |

SpringApplication deduces the application type based on classes loadable in the runtime environment. A dependency present only on the compile classpath and absent at runtime will not allow its marker classes to be detected when the application starts.

For example, a Gradle dependency declared as `compileOnly` is normally excluded from the runtime classpath. If it holds marker classes Spring Boot needs to detect a web stack, successful compilation does not guarantee the corresponding web type is chosen.

### 2.2. Transitive dependencies matter too

You might not declare `spring-webmvc` directly, yet another starter pulls it in transitively. Spring Boot still sees the MVC classes on the runtime classpath.

Conversely, removing `spring-boot-starter-web` from your build might not eliminate MVC if another dependency still pulls `spring-webmvc` in.

Therefore, when the deduced application type is unexpected, inspect the **actual runtime dependency graph**, including transitive dependencies.

## 3. Spring Boot Detects Web Stacks Using Marker Classes

In Spring Boot 3.x, the deduction logic checks several representative marker classes:

| Detection Purpose | Marker Class |
| --- | --- |
| WebFlux reactive dispatcher | `org.springframework.web.reactive.DispatcherHandler` |
| Spring MVC dispatcher | `org.springframework.web.servlet.DispatcherServlet` |
| Jersey Servlet container | `org.glassfish.jersey.servlet.ServletContainer` |
| Servlet API | `jakarta.servlet.Servlet` |
| Spring Servlet web context | `org.springframework.web.context.ConfigurableWebApplicationContext` |

These are implementation details to help understand the detection mechanism, not a list of dependencies an application must declare manually. Class names and namespaces can differ across Spring Boot generations; for example, Spring Boot 2 used the `javax.servlet` namespace whereas Spring Boot 3 uses `jakarta.servlet`.

Spring Boot checks whether these classes can be loaded via the class loader. If a marker is absent, a detection branch is not taken.

### 3.1. Conceptual deduction logic

Spring Boot 3.x's rules can be described as follows:

1. If `DispatcherHandler` is present, and neither `DispatcherServlet` nor Jersey's `ServletContainer` is present, select `REACTIVE`.
2. If the Reactive condition above is not met, Spring checks for the required Servlet markers.
3. If any required Servlet marker is missing, select `NONE`.
4. If all required Servlet markers are present, select `SERVLET`.

Diagram:

~~~mermaid
flowchart TD
    A["Check DispatcherHandler"] --> B{"WebFlux marker present?"}
    B -->|No| E["Check Servlet markers"]
    B -->|Yes| C{"MVC DispatcherServlet or Jersey ServletContainer present?"}
    C -->|No| D["REACTIVE"]
    C -->|Yes| E
    E --> F{"All Servlet markers present?"}
    F -->|Yes| G["SERVLET"]
    F -->|No| H["NONE"]
~~~

Notice that the Reactive branch is evaluated before the Servlet branch. Thus, if WebFlux is present and no MVC/Jersey marker exists, Spring Boot can choose `REACTIVE` even if some Servlet API classes happen to appear on the classpath.

This is a classpath-based heuristic for inferring application type. It is not a deep analysis of whether your code actually defines MVC or WebFlux controllers.

### 3.2. Why is MVC preferred when both stacks are present?

If both `DispatcherHandler` and `DispatcherServlet` are present, the condition for selecting Reactive is not satisfied. Assuming the required Servlet markers are present, Spring Boot chooses `SERVLET`.

This is intentional so applications can add WebFlux purely to use reactive APIs like `WebClient` without accidentally switching their entire server from Spring MVC to WebFlux.

When you need to run a WebFlux server despite MVC also being on the classpath, set the application type explicitly to `REACTIVE`.

## 4. Example 1: Only spring-boot-starter-web

Build:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

The runtime classpath typically contains Spring MVC, the Servlet API, and an embedded Servlet container.

Relevant markers:

| Marker | Expected Status |
| --- | --- |
| `DispatcherHandler` | Absent if WebFlux is not included |
| `DispatcherServlet` | Present |
| Jersey `ServletContainer` | Absent unless Jersey is added |
| Servlet markers | Present |

Deduced result: `SERVLET`.

Spring Boot creates a Servlet web application context, registers the appropriate MVC web infrastructure, and initializes an embedded Servlet server under standard server configuration.

Example:

~~~java
@SpringBootApplication
public class MvcApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcApplication.class, args);
    }
}
~~~

Wait—let's check exact code fence in source file 006 lines 216-223: it uses `~~~java` and `~~~`. Let's make sure we preserve `~~~`! Let's check carefully and fix that line before calling write_file.
Let's continue checking and writing accurately with `~~~`.

MVC Controller:

~~~java
@RestController
@RequestMapping("/api")
public class GreetingController {

    @GetMapping("/hello")
    public String hello() {
        return "Hello from Spring MVC";
    }
}
~~~

When the application runs, HTTP requests are accepted by the Servlet container and routed to Spring MVC infrastructure.

## 5. Example 2: Only spring-boot-starter-webflux

Build:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Without an MVC dispatcher or Jersey Servlet marker, the WebFlux marker causes Spring Boot to select `REACTIVE`.

| Marker | Expected Status |
| --- | --- |
| `DispatcherHandler` | Present |
| `DispatcherServlet` | Absent |
| Jersey `ServletContainer` | Absent |
| Servlet markers | May or may not be present; does not alter the Reactive branch once the Reactive condition matches |

Deduced result: `REACTIVE`.

WebFlux controller:

~~~java
@RestController
@RequestMapping("/api")
public class ReactiveGreetingController {

    @GetMapping("/hello")
    public Mono<String> hello() {
        return Mono.just("Hello from WebFlux");
    }
}
~~~

`Mono` belongs to Reactor Core and is a publisher emitting at most one item. For this snippet to compile, the project needs the WebFlux dependency containing Reactor and an import for `reactor.core.publisher.Mono`.

In WebFlux, requests are processed via the reactive web stack. With the starter's default configuration, Reactor Netty is typically used unless another reactive server is configured.

## 6. Example 3: Both Spring MVC and WebFlux Are Present

Build:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

At this point the classpath includes:

- Spring MVC's `DispatcherServlet`.
- Spring WebFlux's `DispatcherHandler`.
- Servlet API and related web dependencies.
- Required Reactor libraries.

Even though the WebFlux marker is present, the condition for selecting Reactive is not satisfied because the MVC marker is also present. Spring Boot defaults to `SERVLET`.

This is helpful when an application is an MVC server yet wants to use `WebClient` to call external services:

~~~java
@Service
public class PartnerLookupService {
    private final WebClient webClient;

    public PartnerLookupService(WebClient.Builder builder) {
        this.webClient = builder
                .baseUrl("https://partner.example.test")
                .build();
    }

    public Mono<String> lookup(String id) {
        return webClient.get()
                .uri("/partners/{id}", id)
                .retrieve()
                .bodyToMono(String.class);
    }
}
~~~

The application remains a Servlet/MVC application while a service uses `Mono` and `WebClient` for asynchronous HTTP calls.

### 6.1. Using WebClient does not mean the server switched to WebFlux

Distinguish:

- **WebClient:** HTTP client API usable from either MVC or WebFlux applications.
- **WebFlux server:** reactive web stack handling inbound requests.
- **Mono/Flux:** reactive publisher types; they do not decide the application context type.
- **WebApplicationType:** Spring Boot's choice of application model when creating the context.

If your only goal is calling another API with `WebClient`, you do not need to switch the server to Reactive. If you genuinely want the inbound server to run WebFlux, select `REACTIVE` and ensure compatible dependencies and configuration.

### 6.2. Wanting a WebFlux server when both starters are present

You can override the default selection:

~~~yaml
spring:
  main:
    web-application-type: reactive
~~~

Or using the Java API:

~~~java
SpringApplication application =
        new SpringApplication(DemoApplication.class);

application.setWebApplicationType(WebApplicationType.REACTIVE);
application.run(args);
~~~

Once `REACTIVE` is selected, Spring Boot creates a reactive web context. However, overriding the application type does not eliminate dependency conflicts or guarantee every MVC library is compatible with WebFlux. Keep configuration and auto-configurations aligned with the desired stack.

## 7. Example 4: Application Without Web Dependencies

Build:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

If the runtime classpath lacks the markers required for WebFlux or Servlet, Spring Boot selects `NONE`.

The application can still use Spring IoC:

~~~java
@SpringBootApplication
public class BatchApplication {
    public static void main(String[] args) {
        SpringApplication.run(BatchApplication.class, args);
    }
}
~~~

Service:

~~~java
@Service
public class ImportService {
    public void importData() {
        // Read and process data.
    }
}
~~~

Running a task on startup:

~~~java
@Component
public class ImportRunner implements ApplicationRunner {
    private final ImportService importService;

    public ImportRunner(ImportService importService) {
        this.importService = importService;
    }

    @Override
    public void run(ApplicationArguments args) {
        importService.importData();
    }
}
~~~

This application needs no HTTP server. Spring still builds the context, injects the service, and invokes the runner according to Boot's startup lifecycle.

If you want the application to exit after finishing the batch job, design an appropriate process shutdown strategy. Choosing `NONE` alone does not cause the JVM to exit immediately when runners finish if non-daemon threads or active resources remain open.

## 8. Application Type Determines Which ApplicationContext Is Created

After determining `WebApplicationType`, Spring Boot selects the corresponding application context class.

In common default configurations:

| WebApplicationType | Commonly Created Context |
| --- | --- |
| `SERVLET` | `AnnotationConfigServletWebServerApplicationContext` |
| `REACTIVE` | `AnnotationConfigReactiveWebServerApplicationContext` |
| `NONE` | `AnnotationConfigApplicationContext` |

This context determines available capabilities:

- The Servlet context integrates with the Servlet API and embedded Servlet web server.
- The Reactive context integrates with a reactive web server and WebFlux infrastructure.
- The Non-web context has no default web server infrastructure.

You can observe the context class after the application starts:

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(DemoApplication.class, args);

System.out.println(context.getClass().getName());
~~~

For example, Servlet and Reactive applications print different context class names. If an application configures a custom `ApplicationContextFactory`, the concrete context type can be customized; the names above describe Spring Boot's common defaults.

Do not rely solely on the “Started ...” log message to infer the context type. Inspect the actual context class or web type configuration when verification is needed.

## 9. Application Type Affects Auto-Configuration

Many auto-configurations are conditional on the web application type.

Annotation example:

~~~java
@Configuration
@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.SERVLET)
public class ServletOnlyConfiguration {
    // Beans applicable only to Servlet web applications.
}
~~~

Reactive configuration:

~~~java
@Configuration
@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.REACTIVE)
public class ReactiveOnlyConfiguration {
    // Beans applicable only to Reactive web applications.
}
~~~

Non-web configuration:

~~~java
@Configuration
@ConditionalOnNotWebApplication
public class BatchOnlyConfiguration {
    // Beans applicable only when not running as a web application.
}
~~~

Spring Boot evaluates conditions to decide which auto-configurations match the context. Consequently, the same dependency graph can produce different beans depending on the chosen `WebApplicationType` and other conditions.

### 9.1. ConditionalOnClass vs. ConditionalOnWebApplication

The two conditions check different things:

| Condition | Checks |
| --- | --- |
| `@ConditionalOnClass` | Is a specific class present on the classpath? |
| `@ConditionalOnWebApplication` | Which web application type is the context configured as? |
| `@ConditionalOnProperty` | Does a property satisfy the condition? |
| `@ConditionalOnMissingBean` | Is a matching bean already absent from the context? |

A marker class can exist on the classpath while the application still does not select the corresponding web type due to another marker or an explicit override. Conversely, explicitly choosing `REACTIVE` cannot conjure up missing dependency classes.

### 9.2. Not every web bean appears automatically just by selecting SERVLET/REACTIVE

`WebApplicationType` sets the context model and influences conditions. Specific beans still require auto-configuration or user configuration to register them. A Servlet context does not automatically discover controllers outside the component-scan scope; likewise, a Reactive context does not create endpoints unless the application declares matching handlers.

## 10. Overriding Selection with spring.main.web-application-type

Spring Boot lets you configure the application type explicitly via `spring.main.web-application-type`.

Valid values correspond to the enum:

~~~yaml
spring:
  main:
    web-application-type: none
~~~

Options:

| Property Value | Selected Type |
| --- | --- |
| `servlet` | `WebApplicationType.SERVLET` |
| `reactive` | `WebApplicationType.REACTIVE` |
| `none` | `WebApplicationType.NONE` |

Example running an application as non-web even though web dependencies remain on the classpath:

~~~yaml
spring:
  main:
    web-application-type: none
~~~

This can be useful for a command-line mode sharing a module with a web application. However, if web beans or other web auto-configurations remain on the classpath, verify whether they are compatible with a non-web context.

### 10.1. Passing the property via command line

Spring Boot supports command-line properties:

~~~bash
java -jar app.jar --spring.main.web-application-type=none
~~~

Wait—check line 531-533 of 006: it uses `~~~bash` and `~~~`. Let's make sure we use `~~~`!

You can use the same approach for `servlet` or `reactive`. Command-line properties typically take high precedence in the Environment under Boot's property source rules.

When running via an IDE, container, or deployment script, verify which arguments are actually passed to the process. A property in a configuration file may be overridden by an environment variable, system property, or command-line argument.

### 10.2. Setting via Java API

You can configure it directly before calling `run`:

~~~java
SpringApplication application =
        new SpringApplication(DemoApplication.class);

application.setWebApplicationType(WebApplicationType.NONE);

ConfigurableApplicationContext context =
        application.run(args);
~~~

This is useful when the application type is decided by a launcher or specific execution mode. Set the application type before starting the context.

### 10.3. Using SpringApplicationBuilder

Another option:

~~~java
new SpringApplicationBuilder(DemoApplication.class)
        .web(WebApplicationType.REACTIVE)
        .run(args);
~~~

`SpringApplicationBuilder` is useful when configuring multiple contexts or parent/child contexts. For a simple application, `SpringApplication.setWebApplicationType` is usually clear enough.

## 11. Precedence Between Classpath Deduction and Explicit Configuration

You can think of the selection process in two stages:

1. Spring Boot derives a default value deduced from the classpath.
2. Application configuration or the Java API can set a specific application type before the context is created.

Thus, reading the dependency graph tells you the **likely deduced default**. To know which type the application actually runs as, check explicit configuration and launcher code as well.

Examples:

- Classpath has both MVC and WebFlux → defaults to `SERVLET`.
- Configuration file sets `spring.main.web-application-type=reactive` → selects `REACTIVE`.
- Launcher calls `setWebApplicationType(NONE)` → selects `NONE`.
- If no override is provided, the classpath heuristic result is used.

Never conclude the application type from the dependency list alone without checking properties and `SpringApplication` Java configuration.

## 12. Classpath Changed by Transitive Dependencies: How to Investigate

Suppose a team adds a client library and suddenly the application starts as an MVC application. That library might have pulled a web starter into the dependency graph.

With Gradle, inspect the runtime dependency tree:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Search for a specific dependency:

~~~bash
./gradlew dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath
~~~

Or:

~~~bash
./gradlew dependencyInsight --dependency spring-webflux --configuration runtimeClasspath
~~~

With Maven:

~~~bash
mvn dependency:tree -Dscope=runtime
~~~

These commands help answer:

- Which dependency pulled in `spring-webmvc`?
- Which version was selected after conflict resolution?
- Is `spring-webflux` present directly or transitively?
- Which starter brought in the Servlet container?
- Is any dependency excluded or scoped to test only?

Once you identify the dependency introducing the unwanted stack, consider removing or excluding that starter or transitive dependency at the declaration site. Do not blindly exclude a marker class that another library genuinely needs.

### 12.1. Excluding a transitive dependency

Gradle allows excluding a module from a dependency:

~~~groovy
dependencies {
    implementation('com.acme:legacy-client:2.0.0') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-web'
    }
}
~~~

Use this only when you understand whether the library requires that dependency at runtime. Excluding a starter might remove dependencies the client actually uses. If you only want to swap the embedded server or change the web stack, adjust dependencies according to Spring Boot and library documentation.

### 12.2. Test dependencies can alter test results

The test classpath can differ from production runtime. For instance, a test source set might add the web starter for MVC test support while the production application omits it.

When a test initializes its own `SpringApplication`, it can deduce the web type from the test runtime classpath. Hence, a test context does not always mirror the exact runtime dependency graph of the deployed artifact.

When verifying production behavior, test with a classpath and profile close to actual deployment or set the web application type explicitly in the test.

## 13. Inspecting Application Type in Code

You can print the context class after startup:

~~~java
@SpringBootApplication
public class ApplicationTypeDemo {
    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(ApplicationTypeDemo.class, args);

        System.out.println(
                "ApplicationContext: " + context.getClass().getName()
        );
    }
}
~~~

This directly observes the context created by Spring Boot. If an application closes the context manually in a launcher or test, manage the lifecycle appropriately; server applications typically keep the context open for the lifetime of the process.

You can also print the web type from the `SpringApplication` instance before running if the launcher controls that instance, though you should not rely on non-public internal APIs or infer from log formats that may change across versions.

## 14. Testing Application Types

A clean way to test is creating an application with an explicit web type and asserting the context class. For example, non-web:

~~~java
@SpringBootTest(
        properties = "spring.main.web-application-type=none"
)
class NonWebApplicationTest {
    // Verify services and configurations that do not depend on a web server.
}
~~~

For Servlet or Reactive applications, use the corresponding Spring Boot test slice and web environment configuration. When using `@SpringBootTest(webEnvironment = MOCK)`, Boot still selects the web application type based on the web type; the mock environment changes how the test server/environment is set up rather than turning MVC into WebFlux.

Things to verify:

- Is the context class the expected type?
- Do web-type auto-configurations match?
- Are Servlet-only/Reactive-only beans registered appropriately?
- Does the application try to inject Servlet APIs into a Reactive context or vice versa?
- Does the test runtime classpath have different dependencies from production?

You do not need to start a real embedded server for every test. If you only want to test pure services, use a non-web context or a unit test without Spring.

## 15. Difference Between Selecting Application Type and Embedded Server

`WebApplicationType` determines Servlet, Reactive, or non-web context. It does not uniquely determine the final server implementation.

Examples:

| Application Type | Possible Servers |
| --- | --- |
| SERVLET | Tomcat, Jetty, Undertow, or a compatible Servlet container |
| REACTIVE | Reactor Netty, Tomcat reactive adapter, Jetty reactive adapter, or a compatible reactive server |
| NONE | No embedded web server by default |

With `spring-boot-starter-web`, Tomcat is typically the default embedded Servlet server. With `spring-boot-starter-webflux`, Reactor Netty is usually the default. Changing dependencies or configuration can swap the server implementation without changing the application context type.

For instance, switching Tomcat to Jetty in an MVC app still leaves it as `SERVLET`. Choosing a server is not the same as choosing between the Servlet and Reactive stacks.

## 16. What Problems Can Selecting the Wrong Application Type Cause?

### 16.1. Application wants MVC yet runs NONE

Perhaps the Servlet marker is missing at runtime, the web starter was excluded, or a property sets `none`. Then the application lacks a Servlet web context as expected and MVC auto-configuration does not operate as intended.

Check:

- Is `spring-boot-starter-web` on the runtime classpath?
- Are the Servlet API and MVC dispatcher present?
- Is a property or Java API overriding to `NONE`?
- Does build configuration restrict the dependency to compile/test scope?

### 16.2. Application wants WebFlux yet runs SERVLET

The usual cause is that `spring-webmvc` is also present, possibly pulled in directly or transitively via `spring-boot-starter-web`.

If you genuinely want a WebFlux server:

- Inspect the dependency graph.
- Remove the MVC starter if unneeded.
- If you must retain the MVC dependency for a specific purpose, intentionally set `spring.main.web-application-type=reactive`.
- Verify remaining auto-configurations and libraries are compatible with a Reactive context.

### 16.3. Application wants MVC yet runs REACTIVE

Perhaps `spring-webflux` is present, the MVC dispatcher is absent, and the reactive marker is detected. Add Servlet/MVC dependencies if the application truly needs MVC, or override the application type accordingly.

### 16.4. Forcing an application type does not add missing dependencies

Setting `spring.main.web-application-type=servlet` does not automatically add `DispatcherServlet`, the Servlet API, or an embedded server to the classpath. Similarly, forcing `reactive` does not add WebFlux or a Reactor server.

Explicit configuration only chooses the context model. Required dependencies and implementations must still exist on the runtime classpath.

## 17. Distinguishing WebApplicationType from Related Concepts

| Concept | Question Answered |
| --- | --- |
| `WebApplicationType` | Does the app run Servlet, Reactive, or non-web? |
| `ApplicationContext` | Which container manages beans and lifecycle? |
| `spring.main.web-application-type` | Explicit configuration of which application type to use? |
| `spring.main.lazy-initialization` | Should bean initialization be deferred? |
| `server.port` | Which port does the web server listen on? |
| `spring.main.banner-mode` | How is the startup banner displayed? |
| `@ConditionalOnWebApplication` | Does a configuration match the current web type? |
| `@ConditionalOnClass` | Is a required class present on the classpath? |

For example, `server.port=0` does not make the application `NONE`; it tells the web server to pick a random available port within the configured range. `spring.main.lazy-initialization` does not change Servlet/Reactive/None either; it alters when beans are instantiated.

## 18. A Practical Workflow to Determine Which Type an Application Will Run

When taking over a Spring Boot project, follow these steps:

1. Find direct application dependencies in Gradle or Maven.
2. Inspect the runtime dependency graph to see which transitive starters are pulled in.
3. Check for the presence of Spring MVC, WebFlux, Jersey, and Servlet API markers.
4. Search for the `spring.main.web-application-type` property in configuration files, environment variables, and command-line arguments.
5. Check launcher code for calls to `setWebApplicationType` or `SpringApplicationBuilder.web(...)`.
6. Predict the classpath-based default and apply any overrides.
7. Observe the context class when the application starts.
8. Inspect the auto-configuration condition report if expected web beans do not appear.

You can run Gradle commands:

~~~bash
./gradlew dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-webflux --configuration runtimeClasspath
~~~

And run the application with the debug condition report:

~~~bash
java -jar app.jar --debug
~~~

Combining dependency insight and the condition report separates two distinct causes: what the classpath leads Boot to choose as the application type, and which conditions enable or skip a particular auto-configuration.

## 19. Practice Exercises

### Exercise 1 — Using Spring MVC only

Create a project with only `spring-boot-starter-web`. Run the application, record the context class, and verify that a controller can receive HTTP requests.

### Exercise 2 — Using WebFlux only

Create a project with only `spring-boot-starter-webflux`. Create an endpoint returning `Mono<String>`. Compare the context class and server with the MVC exercise.

### Exercise 3 — Adding both starters

Add both `spring-boot-starter-web` and `spring-boot-starter-webflux`. Predict the application type before running, then inspect the context class. Explain why MVC takes precedence by default.

### Exercise 4 — Forcing Reactive via property

Keep both starters and set:

~~~yaml
spring:
  main:
    web-application-type: reactive
~~~

Run the application again and observe the context. Identify which dependencies/configurations are needed for the application to actually serve requests with WebFlux.

### Exercise 5 — Running non-web

Keep the web starter but run with:

~~~bash
java -jar app.jar --spring.main.web-application-type=none
~~~

Observe the context class and identify which beans can still be created. Explain why choosing NONE does not remove web classes from the classpath.

### Exercise 6 — Finding transitive dependencies

Add a third-party library and use `dependencyInsight` to check whether it pulls in `spring-webmvc` or `spring-webflux`. Identify which direct dependency caused the change.

### Exercise 7 — Distinguishing compile and runtime classpaths

Place a web dependency into a compile-only configuration and inspect the runtime classpath. Explain why source code can compile while Spring Boot fails to detect the corresponding marker at runtime.

## 20. Takeaways

Spring Boot uses the runtime classpath to deduce the default `WebApplicationType`. The WebFlux marker can lead to `REACTIVE` when the MVC dispatcher and Jersey Servlet markers are absent. If the Reactive branch is not taken, Spring Boot checks Servlet markers to select `SERVLET`; if markers are missing, the application defaults to `NONE`.

When both Spring MVC and WebFlux exist on the classpath, Spring Boot prioritizes `SERVLET` by default. That is why an MVC application can add WebFlux to use `WebClient` without automatically switching to a reactive server. If a different selection is needed, set `spring.main.web-application-type` or call `SpringApplication.setWebApplicationType` before running.

The chosen application type determines the web context and influences auto-configurations gated on Servlet, Reactive, or non-web conditions. However, choosing an application type does not add missing dependencies or substitute for inspecting the runtime dependency graph.

When an application starts with the wrong stack, trace the runtime classpath, transitive dependencies, property overrides, launcher code, and context class. Distinguishing classpath detection from explicit configuration helps you understand why the same codebase can run MVC, WebFlux, or non-web across different environments.
