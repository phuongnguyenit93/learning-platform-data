# `SpringApplication` Instances, Setters, and `SpringApplicationBuilder`

In a simple Spring Boot application, you normally start the program with a single line:

```java
SpringApplication.run(DemoApplication.class, args);
```

This is convenient because Spring Boot creates and configures a `SpringApplication` object automatically, then calls `run()`. However, when you need finer control over startup—such as picking the web application type, enabling profiles, setting default properties, disabling the banner, adding initializers, or building multiple application contexts—you can create **a `SpringApplication` instance**, configure it with setters, and then call `run()`.

When you want a fluent configuration API, or need to build contexts in a parent-child hierarchy, Spring Boot also provides **`SpringApplicationBuilder`**.

This lesson focuses on three approaches:

- Using static `SpringApplication.run(...)` for simple applications.
- Creating and configuring a `SpringApplication` instance via constructor, setters, and `run(...)`.
- Using `SpringApplicationBuilder` to chain configuration via a fluent API and organize context hierarchies.

## 1. What Is `SpringApplication` Responsible For?

`SpringApplication` is the central class orchestrating Spring Boot application startup. It accepts primary sources (typically the class annotated with `@SpringBootApplication`), prepares the environment, creates the application context, applies initializers and listeners, loads configuration, refreshes the context, and invokes appropriate startup runners.

Conceptual flow:

```text
SpringApplication
       |
       v
Prepare Environment and property sources
       |
       v
Create appropriate ApplicationContext
       |
       v
Apply ApplicationContextInitializers
       |
       v
Load primary sources and process configuration
       |
       v
Refresh ApplicationContext
       |
       v
Instantiate required beans
       |
       v
Invoke ApplicationRunner / CommandLineRunner
       |
       v
Application ready
```

This is a conceptual diagram omitting several internal events and steps. Exact sequencing depends on the Spring Boot version and application configuration.

### 1.1. Static `run()` is a shorthand

Example startup class:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

The static call above creates and runs a Spring Boot application based on the provided source. For small projects, this is readable and sufficient.

When you need to tweak settings before startup, create an instance:

```java
SpringApplication application =
        new SpringApplication(DemoApplication.class);

application.run(args);
```

Both approaches perform the Spring Boot startup process. The difference is that the second gives you an object you can configure before calling `run()`.

## 2. Creating a `SpringApplication` Instance

The constructor typically takes one or more primary sources:

```java
SpringApplication application =
        new SpringApplication(DemoApplication.class);
```

The primary source is usually a configuration class, such as the class bearing `@SpringBootApplication`. You can pass multiple sources if the application has several root configuration classes:

```java
SpringApplication application =
        new SpringApplication(
                DemoApplication.class,
                SharedConfiguration.class
        );
```

These sources are fed into configuration processing. Still, do not add configuration classes indiscriminately: distinguish between primary sources, component scanning, `@Import`, and auto-configuration.

### 2.1. Configuring before calling `run()`

Example:

```java
package com.example.demo;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(DemoApplication.class);

        application.setBannerMode(Banner.Mode.OFF);
        application.setWebApplicationType(WebApplicationType.SERVLET);
        application.setAdditionalProfiles("dev");
        application.setLogStartupInfo(true);

        application.run(args);
    }
}
```

Setters are called **before** `run()`, because they configure how `SpringApplication` prepares and starts the context. Once `run()` has begun, do not keep calling setters expecting them to reconfigure an already running context.

### 2.2. `run()` returns the application context

You can retain the context to access beans or close the context in a non-web application:

```java
ConfigurableApplicationContext context =
        application.run(args);

GreetingService greetingService =
        context.getBean(GreetingService.class);

System.out.println(greetingService.greet("Lan"));
```

In a web application, the context usually stays alive alongside the web server after `run()` returns. In a console application with no server, the `main` thread may finish once its work completes. When you need to close the context explicitly, call `context.close()` or use try-with-resources with a suitable context.

## 3. Common Setters on `SpringApplication`

`SpringApplication` provides numerous setters to customize startup. The setters below are common options; exact APIs may be added or adjusted across Spring Boot versions.

| Setter | Purpose | Example |
| --- | --- | --- |
| `setBannerMode(...)` | Chooses how the banner is displayed | `Banner.Mode.OFF` |
| `setBanner(...)` | Provides a custom banner | `application.setBanner(myBanner)` |
| `setWebApplicationType(...)` | Selects the web application context type | `SERVLET`, `REACTIVE`, `NONE` |
| `setAdditionalProfiles(...)` | Adds profiles for the run | `"dev"` |
| `setDefaultProperties(...)` | Sets default properties | `Map<String, Object>` |
| `setInitializers(...)` | Sets context initializers | `ApplicationContextInitializer` |
| `addInitializers(...)` | Appends initializers | `ApplicationContextInitializer` |
| `setListeners(...)` | Sets application listeners | `ApplicationListener` |
| `addListeners(...)` | Appends listeners | `ApplicationListener` |
| `setHeadless(...)` | Configures AWT headless mode | `true` |
| `setLogStartupInfo(...)` | Enables/disables startup info logging | `true` |
| `setRegisterShutdownHook(...)` | Registers a JVM shutdown hook to close context | `true` |
| `setLazyInitialization(...)` | Enables default lazy initialization for beans | `true` |
| `setApplicationStartup(...)` | Attaches a recorder for startup steps | `BufferingApplicationStartup` |
| `setAddCommandLineProperties(...)` | Controls whether command-line args are added to Environment | `false` |

You do not need to call every setter in every application. Configure only the settings you have a clear reason to change.

## 4. Choosing the Application Type with `setWebApplicationType`

Spring Boot can deduce the application type from the classpath, yet you can specify it explicitly:

```java
application.setWebApplicationType(WebApplicationType.SERVLET);
```

Three common values:

| Value | Meaning |
| --- | --- |
| `WebApplicationType.SERVLET` | Web application based on the Servlet API, typically Spring MVC |
| `WebApplicationType.REACTIVE` | Reactive web application, typically Spring WebFlux |
| `WebApplicationType.NONE` | Does not initialize a web application context |

### 4.1. Servlet applications

```java
SpringApplication application =
        new SpringApplication(DemoApplication.class);

application.setWebApplicationType(WebApplicationType.SERVLET);
application.run(args);
```

This is the common choice for REST APIs using Spring MVC with an embedded servlet container.

### 4.2. Reactive applications

```java
application.setWebApplicationType(WebApplicationType.REACTIVE);
```

Used when the application is designed around a reactive web stack, such as Spring WebFlux. Changing the enum alone does not convert blocking controllers into reactive ones; dependencies and application code must still match WebFlux.

### 4.3. Non-web applications

```java
application.setWebApplicationType(WebApplicationType.NONE);
```

Non-web applications suit command-line tasks, batch jobs, or background programs that need no embedded HTTP server. If code still demands web-specific beans, choosing `NONE` can leave dependencies unconfigured and cause startup to fail.

### 4.4. Why shouldn't you change the application type arbitrarily?

The application context type affects which auto-configurations apply, which web server is created, and which infrastructure beans are present. If a project uses Spring MVC, switching to `REACTIVE` without updating dependencies and architecture can create an unexpected context.

Select the application type based on your project's actual web stack. When there is no special reason to override, letting Spring Boot deduce it from the classpath is the simplest option.

## 5. Banner and Startup Information

### 5.1. Disabling the banner

```java
application.setBannerMode(Banner.Mode.OFF);
```

Modes:

| Value | Behavior |
| --- | --- |
| `Banner.Mode.CONSOLE` | Prints the banner to console |
| `Banner.Mode.LOG` | Writes the banner via logger |
| `Banner.Mode.OFF` | Does not display the banner |

Disabling the banner is often useful in CI environments or when keeping logs concise.

### 5.2. Custom banner

You can supply a `Banner` implementation:

```java
import java.io.PrintStream;
import org.springframework.boot.Banner;
import org.springframework.core.env.Environment;

public class CompanyBanner implements Banner {

    @Override
    public void printBanner(
            Environment environment,
            Class<?> sourceClass,
            PrintStream out) {
        out.println("=== SHOP APPLICATION ===");
        out.println("Starting: " + sourceClass.getSimpleName());
    }
}
```

Registering it:

```java
application.setBanner(new CompanyBanner());
application.setBannerMode(Banner.Mode.CONSOLE);
```

A banner is purely for startup display. It is neither an application listener nor a bean configuration component.

### 5.3. Enabling/disabling startup info

```java
application.setLogStartupInfo(false);
```

This setter toggles certain startup info messages logged by Spring Boot. It does not turn off all application logging and does not replace logging configuration in `application.properties`.

## 6. Profiles and Default Properties

### 6.1. Adding profiles with `setAdditionalProfiles`

```java
application.setAdditionalProfiles("dev");
```

The `dev` profile is added to the environment when the application starts. Spring Boot can then load `application-dev.properties` or `application-dev.yml` if those files exist.

Example:

```text
src/main/resources/
├── application.properties
├── application-dev.properties
└── application-prod.properties
```

`application-dev.properties`:

```properties
server.port=8081
logging.level.com.example.demo=DEBUG
```

Adding the profile via setter avoids hardcoding `spring.profiles.active=dev` in the shared configuration file.

**Note:** `setAdditionalProfiles` appends profiles to the environment for the run. It is not an API to remove active profiles or guarantee that only those profiles are active. If the application also receives profiles via environment variables or the command line, inspect the resulting active profile set.

### 6.2. Setting default properties

```java
Map<String, Object> defaults = new HashMap<>();
defaults.put("server.port", 8081);
defaults.put("features.reports.enabled", false);

application.setDefaultProperties(defaults);
```

Default properties are useful for providing fallback values. They generally have lower precedence than other property sources like config files, environment variables, or command-line arguments. Therefore, defaults can be overridden by environment-specific configuration.

For example, if the default is `server.port=8081` yet the command line passes `--server.port=9090`, the command-line value takes higher precedence under standard property source ordering.

### 6.3. Distinguishing default properties from application properties

| Source | Role |
| --- | --- |
| `setDefaultProperties(...)` | Fallback values supplied by startup code |
| `application.properties` | Application configuration by environment/profile |
| Environment variables | Configuration from the deployment environment |
| Command-line arguments | Configuration passed to the process at launch |

Never place passwords, API keys, or secrets directly inside default properties in source code. Retrieve secrets from a secret manager or appropriate deployment environment.

### 6.4. Example combining profiles and default properties

```java
Map<String, Object> defaults = Map.of(
        "server.port", 8080,
        "features.audit.enabled", false
);

SpringApplication application =
        new SpringApplication(DemoApplication.class);

application.setDefaultProperties(defaults);
application.setAdditionalProfiles("dev");
application.run(args);
```

The application gets fallback values for port and audit. Settings in `application-dev.properties`, environment variables, or the command line can override those defaults according to Spring Boot precedence.

## 7. Initializers and Listeners

`SpringApplication` allows adding callbacks at various stages of startup. Two common types are `ApplicationContextInitializer` and `ApplicationListener`.

### 7.1. `ApplicationContextInitializer`

An initializer is called on the application context before the context is refreshed. It fits customizing the context or environment during the preparation phase.

Example:

```java
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;

public class StartupContextInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(
            ConfigurableApplicationContext context) {
        System.out.println("ApplicationContext is being prepared");
    }
}
```

Registration:

```java
application.addInitializers(new StartupContextInitializer());
```

An initializer should not be used to instantiate business services manually. It serves to customize the context prior to refresh; beans should still be created and injected through the container.

### 7.2. `ApplicationListener`

Listeners receive application events during startup and runtime.

Example:

```java
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationListener;

public class ReadyListener
        implements ApplicationListener<ApplicationReadyEvent> {

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        System.out.println("Application is ready");
    }
}
```

Registration:

```java
application.addListeners(new ReadyListener());
```

The listener receives the matching event when Spring Boot publishes it. `ApplicationReadyEvent` is published once the application is ready, including after runners execute in Spring Boot's startup sequence.

### 7.3. Some common startup events

| Event | General Timing |
| --- | --- |
| `ApplicationStartingEvent` | When startup begins, before Environment and context are fully prepared |
| `ApplicationEnvironmentPreparedEvent` | When the Environment has been prepared |
| `ApplicationContextInitializedEvent` | When the context has been created and initializers have run |
| `ApplicationPreparedEvent` | When the context has been prepared, before refresh |
| `ContextRefreshedEvent` | When the application context has been refreshed |
| `ApplicationStartedEvent` | After context refresh and before runners are invoked |
| `ApplicationReadyEvent` | After runners finish; application is ready for traffic per startup flow |
| `ApplicationFailedEvent` | When startup fails |

Event names and timing details may vary across Spring Boot generations; consult the API documentation for your project's version.

### 7.4. Adding multiple initializers/listeners

```java
application.addInitializers(
        new StartupContextInitializer(),
        new AnotherContextInitializer()
);

application.addListeners(
        new ReadyListener(),
        new StartupMetricsListener()
);
```

Using `setInitializers(...)` or `setListeners(...)` replaces the list via that setter. When you want to append while keeping previously configured items, `addInitializers(...)` and `addListeners(...)` express that intent clearly.

## 8. Lazy Initialization and Startup Tracking

### 8.1. Enabling default lazy initialization

```java
application.setLazyInitialization(true);
```

Lazy initialization defers creating eligible beans until they are needed. This can shorten startup time, yet bean creation failures may surface later when a bean is first used.

Example:

```java
@Service
@Lazy
public class ExpensiveReportService {
    public ExpensiveReportService() {
        System.out.println("Creating report service");
    }
}
```

If a non-lazy singleton directly injects `ExpensiveReportService`, the dependency still must be created to satisfy that singleton. Lazy initialization does not defer a bean when a mandatory dependency requires it early.

Enable lazy initialization only when you understand its impact on error detection timing and how the application accesses beans.

### 8.2. Tracking startup with `ApplicationStartup`

Spring Boot supports attaching an `ApplicationStartup` to record startup steps. Example using `BufferingApplicationStartup`:

```java
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;

SpringApplication application =
        new SpringApplication(DemoApplication.class);

application.setApplicationStartup(
        new BufferingApplicationStartup(2048)
);

application.run(args);
```

`BufferingApplicationStartup` records startup steps into a bounded buffer. It is useful for analyzing startup duration and spotting slow steps. How startup data is read or exposed depends on observability tools and application setup.

## 9. Command-Line Properties and Environment Configuration

By default, Spring Boot can add command-line arguments of the form `--key=value` into the Environment:

```bash
java -jar app.jar --server.port=8085 --features.audit.enabled=true
```

If you need to disable adding command-line arguments as a property source:

```java
application.setAddCommandLineProperties(false);
```

This does not strip arguments from `main` or runners. It only stops Spring Boot from using property-formatted arguments to configure the Environment.

Normally you should keep the default for convenient environment configuration. Disable it only when you have a clear reason, such as an application handling command-line arguments itself without wanting them to override property sources.

## 10. What Is `SpringApplicationBuilder`?

`SpringApplicationBuilder` offers a fluent API to configure and construct `SpringApplication`. Instead of instantiating an object and calling multiple setters, you can chain calls:

```java
new SpringApplicationBuilder(DemoApplication.class)
        .bannerMode(Banner.Mode.OFF)
        .web(WebApplicationType.SERVLET)
        .profiles("dev")
        .properties("server.port=8081")
        .run(args);
```

The builder typically helps with:

- Writing startup configuration as a readable chain.
- Setting profiles and properties.
- Selecting the web application type.
- Adding initializers and listeners.
- Building application context hierarchies.

`SpringApplicationBuilder` does not replace the IoC container; it is a way to configure and coordinate creating and running `SpringApplication`.

### 10.1. Basic builder example

```java
package com.example.demo;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplicationBuilder;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        new SpringApplicationBuilder(DemoApplication.class)
                .bannerMode(Banner.Mode.OFF)
                .web(WebApplicationType.SERVLET)
                .profiles("dev")
                .properties(
                        "server.port=8081",
                        "features.audit.enabled=false"
                )
                .run(args);
    }
}
```

Many builder methods return the builder itself, enabling method chaining. `run(args)` starts the application and returns the application context.

### 10.2. Common builder methods

| Method | Purpose |
| --- | --- |
| `sources(...)` | Sets source classes for the application |
| `profiles(...)` | Adds profiles |
| `properties(...)` | Supplies properties for the run |
| `web(...)` | Selects `WebApplicationType` |
| `banner(...)` / `bannerMode(...)` | Configures the banner |
| `initializers(...)` | Adds application context initializers |
| `listeners(...)` | Adds application listeners |
| `headless(...)` | Configures headless mode |
| `logStartupInfo(...)` | Controls startup info logging |
| `registerShutdownHook(...)` | Enables/disables shutdown hook |
| `lazyInitialization(...)` | Controls lazy initialization |
| `parent(...)` | Declares configuration for a parent context |
| `child(...)` | Creates a child context |
| `sibling(...)` | Creates a context at the same level as the current context in the hierarchy |
| `run(...)` | Starts the application and returns the context |

Exact method names and overloads should be checked against your Spring Boot version. Not every setter on `SpringApplication` has an identically named or identical-signature counterpart on the builder.

## 11. When to Use Instance Setters vs. Builder?

| Scenario | Suitable Choice |
| --- | --- |
| Simple application, no startup customization | `SpringApplication.run(...)` |
| A few setters needed and clear step-by-step setup preferred | `new SpringApplication(...)` |
| Fluent startup configuration chain preferred | `SpringApplicationBuilder` |
| Parent-child contexts needed | `SpringApplicationBuilder` |
| Deep manipulation of the `SpringApplication` instance needed | Direct instance creation |

Both direct instance creation and the builder serve many overlapping needs. Choose whichever makes startup configuration cleanest and easiest to control.

## 12. Context Hierarchies with `SpringApplicationBuilder`

A standout capability of the builder is creating **parent-child application contexts**. This pattern is useful when an application has shared configuration alongside multiple separate web areas or modules.

Example:

```text
Parent ApplicationContext
    ├── Shared services
    ├── Common configuration
    └── Shared infrastructure
           |
           +---------------------+
           |                     |
           v                     v
     Child context A        Child context B
     (Web/API A)            (Web/API B)
```

Basic rules:

- Child contexts can look up beans from the parent context.
- The parent context cannot see beans that exist only in a child.
- Each context has its own registry; a bean of the same name in a child shadows the parent's bean when resolved from that child.
- Each context has its own lifecycle and must be closed appropriately.

### 12.1. Creating a parent and child

Example:

```java
import org.springframework.boot.SpringApplicationBuilder;
import org.springframework.boot.WebApplicationType;

new SpringApplicationBuilder()
        .parent(SharedConfiguration.class)
        .web(WebApplicationType.NONE)
        .child(ApiApplication.class)
        .web(WebApplicationType.SERVLET)
        .run(args);
```

In this example, the parent context holds shared configuration, while the child context hosts the API application. Exact layout must be designed carefully so component scanning does not accidentally register the same component in multiple contexts.

### 12.2. Parent supplies shared beans

```java
@Configuration
public class SharedConfiguration {

    @Bean
    public Clock sharedClock() {
        return Clock.systemUTC();
    }
}
```

The child can inject the `Clock` bean from the parent:

```java
@RestController
public class TimeController {
    private final Clock clock;

    public TimeController(Clock clock) {
        this.clock = clock;
    }
}
```

If the child context has no local `Clock` bean, it resolves the bean from the parent context. This is one way to share common infrastructure.

### 12.3. A child can define its own bean with the same name

Suppose the parent defines a `clock` bean and the child also registers a `clock` bean. The child context uses its own bean when looking up within the child; the parent's bean still exists inside the parent context.

This is lookup shadowing across contexts, not bean definition overriding within a single registry.

### 12.4. Do not create a hierarchy without a clear need

Context hierarchies add complexity:

- You must track bean visibility between parent and child.
- You must control component scanning and auto-configuration per context.
- You must manage each context's lifecycle.
- Duplicate beans or repeated configuration application can occur.
- Debugging dependency injection becomes harder.

A standard Spring Boot application only needs a single application context. Use a hierarchy when genuine module boundaries or multiple sub-applications must share infrastructure.

## 13. Sibling Contexts and Multiple Child Applications

`SpringApplicationBuilder` can also create sibling contexts sharing a common parent.

Model:

```text
              Parent context
             /              \
            /                \
           v                  v
      Sibling A           Sibling B
      API module          Admin module
```

Conceptual example:

```java
new SpringApplicationBuilder()
        .parent(SharedConfiguration.class)
        .web(WebApplicationType.NONE)
        .child(ApiApplication.class)
        .web(WebApplicationType.SERVLET)
        .sibling(AdminApplication.class)
        .web(WebApplicationType.SERVLET)
        .run(args);
```

`sibling(...)` creates a context at the same level as the current child context in the builder structure. Consult the documentation for your Boot version to verify how the builder propagates shared configuration and manages the created contexts.

Do not assume siblings see each other's beans. They share a parent, while beans defined privately inside one sibling do not become visible to another sibling.

## 14. Managing Shutdown and Lifecycle

### 14.1. Shutdown hook

Spring Boot normally registers a shutdown hook to close the application context gracefully when the JVM exits.

Configurable via:

```java
application.setRegisterShutdownHook(true);
```

Or with the builder:

```java
new SpringApplicationBuilder(DemoApplication.class)
        .registerShutdownHook(true)
        .run(args);
```

When the context closes, Spring invokes applicable destruction callbacks such as `@PreDestroy`, `DisposableBean`, or declared destroy methods on singleton beans.

If the application is managed by a specialized environment, external container, or separate lifecycle coordinator, decide who owns closing the context to prevent double closing or failing to close.

### 14.2. Closing the context manually

```java
ConfigurableApplicationContext context =
        new SpringApplication(DemoApplication.class).run(args);

try {
    // Perform console application work
} finally {
    context.close();
}
```

In a long-running web application, do not close the context right after `run()` if you want the web server to keep serving requests. The pattern above fits console programs or workflows with a clear end point.

### 14.3. Parent-child lifecycle

When using the builder to create a hierarchy, manage both the root context and child contexts. Closing the parent context can affect child contexts depending on lifecycle relationships; closing approach and order should follow the actual API and context hierarchy of the application. Do not leave contexts alive indefinitely once an application has finished.

## 15. Common Mistakes

### 15.1. Calling setters after calling `run()`

Misguided example:

```java
SpringApplication application =
        new SpringApplication(DemoApplication.class);

application.run(args);
application.setAdditionalProfiles("dev");
```

Setters called after startup has already occurred cannot be expected to alter the profiles of the already-created context. Configure before `run()`.

### 15.2. Confusing `setDefaultProperties` with mandatory properties

Default properties have low precedence. When configuring a specific environment, place properties in an appropriate source and verify precedence. Do not treat default properties as a way to force an un-overridable value.

### 15.3. Choosing the wrong web application type

If an application uses Spring MVC yet sets `WebApplicationType.NONE`, a servlet web server is not created. If an application uses WebFlux yet forces servlet, runtime configuration may behave unexpectedly.

Override manually only when you understand the dependencies and required application context type.

### 15.4. Using `@Order` to control bean instantiation

`@Order` orders supported extension points such as list injection or startup runners. It does not guarantee constructor or `@PostConstruct` order across arbitrary singletons.

If bean B needs bean A, use constructor injection. If A only needs to initialize before B for a side effect, consider `@DependsOn`.

### 15.5. Using a hierarchy that causes duplicate component registration

If parent and child both component-scan the same package, components can be registered in both contexts. That creates two instances or two identically named beans at two levels.

Separate packages and configurations clearly:

- The parent holds shared configuration and shared beans.
- Each child scans only its own module.
- Do not let both parent and child scan the entire application package unintentionally.

### 15.6. Calling `getBean()` too early in an initializer

`ApplicationContextInitializer` executes before the context is completely refreshed. Do not assume business beans are ready inside an initializer. Use initializers to customize the environment/context; use bean lifecycle, events, or runners for later-stage tasks.

## 16. Comparing the Three Startup Approaches

| Criterion | Static `run()` | `SpringApplication` instance | `SpringApplicationBuilder` |
| --- | --- | --- | --- |
| Syntax | Shortest | Create object, then call setters | Fluent chain |
| Startup customization | Limited before invocation | Many direct setters | Corresponding builder methods |
| Configuration readability | Fits minimal customization | Explicit step-by-step | Clean for chained configuration |
| Context hierarchy | Not its main purpose | Manual construction is more complex | Supports parent/child/sibling |
| Use when | Standard applications | Instance-level control needed | Fluent setup or multiple contexts needed |

Examples:

**Static shorthand:**

```java
SpringApplication.run(DemoApplication.class, args);
```

**Instance approach:**

```java
SpringApplication app =
        new SpringApplication(DemoApplication.class);
app.setBannerMode(Banner.Mode.OFF);
app.setAdditionalProfiles("dev");
app.run(args);
```

**Builder approach:**

```java
new SpringApplicationBuilder(DemoApplication.class)
        .bannerMode(Banner.Mode.OFF)
        .profiles("dev")
        .run(args);
```

## 17. Practice Exercises

### Exercise 1 — Switching from static run to instance

Create a simple Spring Boot application currently using:

```java
SpringApplication.run(DemoApplication.class, args);
```

Switch to:

```java
SpringApplication application =
        new SpringApplication(DemoApplication.class);
application.run(args);
```

Observe startup logs and endpoints. Explain why both startup forms behave identically at a basic level.

### Exercise 2 — Disabling the banner and changing web type

Create a `SpringApplication` instance, turn off the banner, and specify `WebApplicationType.SERVLET`. Start the web app and confirm the server still works. Then try `NONE` in an app that does not need HTTP.

### Exercise 3 — Adding a profile with a setter

Create `application-dev.properties` with `server.port=8081`. Call `setAdditionalProfiles("dev")`, start up, and verify the port. Try adding another profile via an environment variable to observe the active profile set.

### Exercise 4 — Default properties and precedence

Use `setDefaultProperties` to set `server.port=8080`. Then pass `--server.port=8082` when running.

**Question:** which value takes effect and why?

### Exercise 5 — Adding an initializer and listener

Write an `ApplicationContextInitializer` that logs when the context is prepared and an `ApplicationListener<ApplicationReadyEvent>` that logs when the application is ready.

Compare when each callback is invoked. Explain why an initializer should not be used to call business services.

### Exercise 6 — Using `SpringApplicationBuilder`

Rewrite Exercise 1 using the builder:

```java
new SpringApplicationBuilder(DemoApplication.class)
        .bannerMode(Banner.Mode.OFF)
        .profiles("dev")
        .run(args);
```

Compare configuration readability against the setter style.

### Exercise 7 — Trying a parent-child context

Create `SharedConfiguration` in the parent providing a `Clock` bean. Create a child context containing a controller or service that injects `Clock`. Verify the child can use the parent's bean.

Then declare a bean of the same type in the child and observe lookup behavior. Explain why the parent cannot see beans registered solely in the child.

### Exercise 8 — Tracking startup

Attach `BufferingApplicationStartup` to `SpringApplication`. Start the application and inspect startup steps via supported tooling. Identify which step takes the most time and explain why startup data helps optimize applications.

## 18. Takeaways

`SpringApplication` is the object orchestrating Spring Boot startup. Static `run()` fits simple applications; creating an instance allows configuring via setters prior to startup; `SpringApplicationBuilder` offers a fluent API and support for context hierarchies.

Pick setters according to your goal: `setWebApplicationType` chooses the context type, `setAdditionalProfiles` adds profiles, `setDefaultProperties` supplies fallback values, initializers and listeners hook into startup phases, and the shutdown hook closes the context with the JVM lifecycle.

`SpringApplicationBuilder` is particularly helpful when chaining settings or constructing parent-child-sibling contexts. Still, standard applications only need a single context; use a hierarchy only when bean sharing and module boundaries clearly warrant it. Above all, perform all startup configuration before `run()` and verify it through properties, logs, registered beans, and actual runtime behavior.
