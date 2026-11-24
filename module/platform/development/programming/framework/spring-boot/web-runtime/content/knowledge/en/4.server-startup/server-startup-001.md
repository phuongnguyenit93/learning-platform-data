# From `SpringApplication.run` to a Web Application's `ApplicationContext`

In a Spring Boot application, calling `SpringApplication.run(...)` kicks off a sequence of tasks: preparing configuration, selecting the web application type, creating the `ApplicationContext`, loading and processing bean definitions, initializing the required beans, creating the embedded web server, running post-startup tasks, and then signaling that the application is ready. Understanding this sequence helps you determine where beans are created, when the server starts accepting requests, and where initialization logic should be placed.

## 1. Distinguishing SpringApplication, ApplicationContext, and the Web Server

**SpringApplication** is the orchestrator of Spring Boot's startup process. It accepts one or more primary sources (usually a class annotated with `@SpringBootApplication`), prepares the Environment and ApplicationContext, invokes refresh, publishes lifecycle events, and runs the runners.

**ApplicationContext** is Spring's IoC container. It manages bean definitions, creates and holds bean instances, and provides the Environment, resource loading, event publishing, message source, and parent-child context relationships.

Keep these distinctions in mind:
- **Bean definition** is the metadata describing how to create a bean: class, constructor, scope, dependencies, and related attributes.
- **Bean instance** is the actual Java object created from the definition.
- **BeanFactory** is the underlying foundation that manages creating and dispensing beans.
- **ApplicationContext** extends BeanFactory and adds events, resources, Environment, and application-level services.

**Embedded web server** accepts HTTP connections and forwards requests into Spring's web infrastructure. For Servlet applications, Tomcat is typically the default server when using `spring-boot-starter-web`; it can be replaced with Jetty or Undertow if the corresponding dependencies are configured. For WebFlux, Reactor Netty is typically the default choice of `spring-boot-starter-webflux`.

ApplicationContext is not synonymous with the web server. The context manages the application; the web server is a runtime component created and managed within the web ApplicationContext. When the context closes, the server is stopped as well.

## 2. Entry Point: The Application Class and SpringApplication.run

A Spring Boot application typically has a main class:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebRuntimeApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebRuntimeApplication.class, args);
    }
}
~~~

`@SpringBootApplication` combines three roles:
- `@SpringBootConfiguration`: marks the main configuration of the application.
- `@EnableAutoConfiguration`: enables the auto-configuration mechanism.
- `@ComponentScan`: scans for components starting from the main class's package and its subpackages according to the default configuration.

The class passed to `SpringApplication.run` is the primary source from which Spring Boot begins loading configuration. The `args` parameter represents the process's command-line arguments. Spring Boot parses them into `ApplicationArguments` and puts `--key=value` options into the Environment.

For example:

~~~bash
java -jar app.jar --server.port=8081 --spring.profiles.active=local
~~~

`SpringApplication.run` returns a `ConfigurableApplicationContext`. When the call returns normally, a standard startup has already executed the runners and published `ApplicationReadyEvent`.

## 3. Which Type of ApplicationContext Does Spring Boot Choose?

Spring Boot determines `WebApplicationType` based on the classpath and configuration:

| WebApplicationType | Purpose | Common Context |
|---|---|---|
| `SERVLET` | Servlet applications, such as Spring MVC | `AnnotationConfigServletWebServerApplicationContext` |
| `REACTIVE` | Reactive applications, such as Spring WebFlux | `AnnotationConfigReactiveWebServerApplicationContext` |
| `NONE` | Applications that do not initialize a web server | `AnnotationConfigApplicationContext` |

Spring Boot infers the application type from the web classes present on the classpath. If both Spring MVC and WebFlux are present, Spring Boot typically chooses the Servlet/MVC model by default. You can explicitly specify the application type using a property:

~~~properties
spring.main.web-application-type=servlet
~~~

The corresponding valid values are `servlet`, `reactive`, and `none`. You can also configure it programmatically:

~~~java
SpringApplication app = new SpringApplication(WebRuntimeApplication.class);
app.setWebApplicationType(WebApplicationType.SERVLET);
app.run(args);
~~~

Specifying `SERVLET` or `REACTIVE` does not automatically add missing dependencies. The application still needs the corresponding starter and runtime libraries.

Not every `SpringApplication.run` call creates a web server. When the application type is `NONE`, Spring Boot still creates an ApplicationContext and manages beans, but does not open an HTTP port.

## 4. Overview of the SpringApplication.run Lifecycle

The startup process can be divided into the following phases:

1. Initialize SpringApplication, the bootstrap context, and the run listeners.
2. Prepare the Environment: property sources, profiles, external configuration, and command-line arguments.
3. Create the ApplicationContext according to WebApplicationType.
4. Prepare the context: attach the Environment, run initializers, and load the primary sources.
5. Refresh the context: process bean definitions, auto-configuration, and instantiate the required singletons.
6. Create and then start the embedded web server if this is a web application.
7. Publish ApplicationStartedEvent, and run ApplicationRunner and CommandLineRunner beans.
8. Publish ApplicationReadyEvent and return the ApplicationContext to the caller.

This is the conceptual order of the standard startup flow. Several internal events and auxiliary operations occur between phases; applications can extend this flow with listeners, initializers, or customizers.

## 5. The Environment Preparation Phase

The Environment holds the configuration sources accessible to the application, for example:
- Configuration files such as `application.properties` or `application.yml`.
- Profile-specific files such as `application-local.yml`.
- Operating system environment variables.
- Java system properties.
- Command-line arguments.
- Property sources added by the application or libraries.

Spring Boot processes Config Data and profiles during the Environment preparation phase. Configuration values are subsequently used by beans, auto-configurations, and configuration conditions.

For example:

~~~yaml
server:
  port: 8081

spring:
  application:
    name: order-service
  profiles:
    active: local
~~~

A bean can read configuration via the Environment or `@ConfigurationProperties`:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(String baseUrl, Duration timeout) {}
~~~

When using `@ConfigurationProperties`, you need to register the class via an appropriate mechanism, such as `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.

The Environment is prepared before the context refreshes. Therefore, profiles and configuration that affect loading Config Data must be defined via an appropriate configuration source during the Environment preparation phase, such as environment variables, command-line arguments, or configuration files.

## 6. Creating and Preparing the ApplicationContext

After the Environment is prepared, SpringApplication creates the context matching the application type.

For Servlet web applications, the context is a web ApplicationContext capable of integrating a `ServletWebServerFactory`. For reactive applications, the context integrates a `ReactiveWebServerFactory`.

During the context preparation phase, Spring Boot performs the following main tasks:
- Attaches the prepared Environment to the context.
- Sets context-specific attributes and customizers.
- Runs the registered `ApplicationContextInitializer` instances.
- Registers and loads the primary sources, usually the class annotated with `@SpringBootApplication`.
- Notifies listeners that the context has been prepared and the sources have been loaded.

`ApplicationContextInitializer` allows customizing the context before refresh. It is suitable for registering context-level settings or adjusting the context structure before beans are initialized. You should not use an initializer to execute business logic that requires full dependency injection, because regular singletons have not been created at this stage.

Example of registering an initializer:

~~~java
SpringApplication app = new SpringApplication(WebRuntimeApplication.class);

app.addInitializers(context ->
    context.setId("order-service-context")
);

app.run(args);
~~~

The initializer above illustrates customizing context metadata before refresh. If you need to configure the Environment for loading profiles or Config Data, place that configuration in the Environment preparation phase rather than waiting until an initializer.

## 7. Refresh: Where Spring Builds the Container

`refresh()` is the central step. This is when the context transitions from its prepared state to having its infrastructure and required beans initialized.

The main steps of `AbstractApplicationContext.refresh()` include:

1. **prepareRefresh**: marks the context as refreshing, validates state, and prepares internal structures.
2. **obtainFreshBeanFactory**: obtains a fresh BeanFactory or refreshes the context's BeanFactory.
3. **prepareBeanFactory**: registers foundational components and configures the environment for the BeanFactory.
4. **postProcessBeanFactory**: allows specialized contexts to perform additional processing on the BeanFactory.
5. **invokeBeanFactoryPostProcessors**: runs BeanFactoryPostProcessors to process or modify bean definitions before regular beans are instantiated.
6. **registerBeanPostProcessors**: registers BeanPostProcessors, which intercept bean instance creation, such as processing annotations and proxies.
7. **initMessageSource**: initializes the message source for message/i18n functionality.
8. **initApplicationEventMulticaster**: prepares the event publishing mechanism in the context.
9. **onRefresh**: allows specialized contexts to initialize additional infrastructure; the web context creates the web server from its factory at this stage.
10. **registerListeners**: registers known listeners with the event multicaster.
11. **finishBeanFactoryInitialization**: instantiates the remaining non-lazy singletons and completes BeanFactory initialization.
12. **finishRefresh**: starts lifecycle components, publishes `ContextRefreshedEvent`, and completes the refresh.

Not every bean is created immediately when `SpringApplication.run` is called. Regular singleton beans are created during the completion of refresh; beans marked with `@Lazy` may only be created when first requested. Prototype beans are created each time they are requested from the container.

### 7.1. Configuration Classes and Component Scan

During BeanFactoryPostProcessor processing, Spring analyzes configuration classes, component scans, and imports. Annotations such as `@Configuration`, `@Bean`, `@Component`, `@Service`, `@Repository`, and `@Controller` contribute bean definitions to the context.

The package location of the class annotated with `@SpringBootApplication` is very important. Default component scanning starts from this class's package and descends into subpackages. If the main class is placed too deep, scanning might not cover the required packages. Place the application class in the root package of your application code.

### 7.2. Auto-configuration

`@EnableAutoConfiguration` allows Spring Boot to bring in configurations based on the classpath, properties, and existing beans. These configurations commonly use conditions such as:
- Whether a class is present or absent on the classpath.
- Whether a property has a specific value.
- Whether a bean is already present or missing in the context.
- Whether the application is running with the corresponding web context type.

Auto-configuration does not create every possible bean. Each configuration only applies when its conditions match. Many configurations also have a back-off mechanism: if the application already provides a suitable bean itself, the default configuration may avoid creating a replacement bean.

For example, when Spring MVC and embedded server dependencies are present, Boot can configure DispatcherServlet and the web server factory. If the application declares certain infrastructure beans itself, the auto-configuration outcome may change depending on the conditions.

## 8. The Web ApplicationContext Creates and Starts the Server

For Servlet applications, `ServletWebServerApplicationContext` integrates `ServletWebServerFactory`. For reactive applications, `ReactiveWebServerApplicationContext` integrates `ReactiveWebServerFactory`.

Two tasks must be distinguished:
- In the web context's `onRefresh()` hook, Spring Boot creates the web server from the factory and configures the required servlets, filters, and initializers.
- In `finishRefresh()`, after the core refresh steps complete, the web context starts the web server and publishes an event notifying that the server has been initialized.

For Servlet applications, the specific event is `ServletWebServerInitializedEvent`; for reactive applications, the corresponding event is `ReactiveWebServerInitializedEvent`. The event contains the web server and the associated context. This is the point where the actual port can be read, especially when `server.port=0` is configured so the operating system assigns a random port.

Creating the server and starting to accept requests is part of refreshing the web context. `SpringApplication.run` only proceeds to subsequent steps after refresh completes. Therefore, on a successful startup, the server has already started before `ApplicationStartedEvent` is published.

The `spring-boot-starter-web` dependency typically brings embedded Tomcat into a Servlet application. If you swap the embedded server, the corresponding factory will be auto-configured based on dependencies and configuration. For WebFlux, the server factory belongs to the reactive stack.

## 9. Important Lifecycle Events

Spring Boot publishes events so listeners can observe startup progress:

| Event | Timing | Useful For |
|---|---|---|
| `ApplicationStartingEvent` | Very early, before Environment and ApplicationContext are ready | Tracking startup initiation; registering listeners before run |
| `ApplicationEnvironmentPreparedEvent` | Environment has been prepared | Observing loaded configuration and profiles |
| `ApplicationContextInitializedEvent` | Context has been created and initializers have run, before loading sources | Observing the context in the preparation phase |
| `ApplicationPreparedEvent` | Context has been prepared and sources loaded, before refresh | Observing the context before refresh |
| `ContextRefreshedEvent` | Context has completed core refresh | Knowing the context has refreshed |
| `ServletWebServerInitializedEvent` or `ReactiveWebServerInitializedEvent` | Embedded web server has started | Retrieving the port and web server information |
| `ApplicationStartedEvent` | After refresh, before runners | Acting at the application started milestone |
| `ApplicationReadyEvent` | After runners have completed | Starting work that requires the application to be ready |
| `ApplicationFailedEvent` | Startup failed | Recording startup failures |

`ApplicationStartingEvent` and `ApplicationEnvironmentPreparedEvent` occur before a regular ApplicationContext can manage listener beans. To receive early events, register listeners with `SpringApplication` before calling `run` or use an appropriate global listener registration mechanism. A bean with `@EventListener` inside the context cannot retroactively receive events published before that bean existed.

Do not confuse `ContextRefreshedEvent` with `ApplicationReadyEvent`. A refreshed context does not mean all startup tasks have finished. `ApplicationRunner` and `CommandLineRunner` still execute after `ApplicationStartedEvent` and before `ApplicationReadyEvent`.

## 10. ApplicationRunner and CommandLineRunner

Spring Boot runs beans implementing `ApplicationRunner` or `CommandLineRunner` after the ApplicationContext refreshes successfully and before `ApplicationReadyEvent`.

Key difference:
- `ApplicationRunner` receives `ApplicationArguments`, which provides an API to access option and non-option arguments.
- `CommandLineRunner` receives the raw `String... args` array directly.

Example:

~~~java
@Component
class StartupTasks implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Application arguments: "
            + args.getOptionNames());
    }
}
~~~

You can also declare a runner with `@Bean`:

~~~java
@Configuration
class StartupConfiguration {

    @Bean
    ApplicationRunner verifyStartupConfiguration() {
        return args -> {
            // Verify required configuration or load small initial data.
        };
    }
}
~~~

If there are multiple runners, use `Ordered` or `@Order` to specify the execution order. Unhandled exceptions in a runner can cause startup to fail; runners should have a clear scope, reasonable execution time, and intentional error handling.

Avoid putting long-running initialization tasks into a runner. Calling external services, syncing large datasets, or waiting on long operations can delay `ApplicationReadyEvent`. Consider timeouts, retries, idempotency, and recovery when tasks fail.

## 11. Example: Observing the Lifecycle of a Servlet Application

The following example uses Spring Boot 3.x and Java 17+ (also compatible with Java 21). Place the classes in the same package as or a subpackage of the application class. The project needs the `spring-boot-starter-web` dependency.

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.web.servlet.context.ServletWebServerInitializedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class WebRuntimeApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebRuntimeApplication.class, args);
    }
}

@Component
class StartupObserver implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("ApplicationRunner executed");
    }

    @EventListener
    public void onWebServerInitialized(
            ServletWebServerInitializedEvent event) {
        System.out.println("Web server port: "
            + event.getWebServer().getPort());
    }

    @EventListener
    public void onApplicationReady(ApplicationReadyEvent event) {
        System.out.println("Application is ready: "
            + event.getApplicationContext().getId());
    }
}

@RestController
class HelloController {

    @GetMapping("/hello")
    public String hello() {
        return "Hello from Spring Boot";
    }
}
~~~

Run the application in a Spring Boot project:

~~~bash
./gradlew bootRun
~~~

On Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Call the endpoint:

~~~bash
curl -i http://localhost:8080/hello
~~~

The response body is:

~~~text
Hello from Spring Boot
~~~

The port information in the logs depends on server configuration. If `server.port=0` is configured, use the port printed by `ServletWebServerInitializedEvent` to send the request. Log order can interleave with internal Spring Boot and embedded server logs; do not rely on arbitrary log line ordering as a lifecycle contract.

## 12. Customizing SpringApplication Before Running

You can instantiate `SpringApplication` instead of using the static method to customize startup:

~~~java
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;

public class CustomBootstrap {

    public static void main(String[] args) {
        SpringApplication app =
            new SpringApplication(WebRuntimeApplication.class);

        app.setWebApplicationType(WebApplicationType.SERVLET);
        app.setBannerMode(Banner.Mode.OFF);
        app.setApplicationStartup(
            new BufferingApplicationStartup(2048)
        );

        app.run(args);
    }
}
~~~

Some customization points include:
- `setWebApplicationType`: choose Servlet, Reactive, or None.
- `setDefaultProperties`: provide default configuration; higher-precedence property sources can override it.
- `addInitializers`: register ApplicationContextInitializer instances.
- `addListeners`: register ApplicationListener instances.
- `setBannerMode`: enable/disable the banner.
- `setApplicationStartup`: collect startup step information to analyze startup time.

Customize only when there is a clear requirement. Forcing WebApplicationType can cause the application to fail at startup if the corresponding stack's dependencies are missing.

## 13. When Startup Fails

Startup can stop at different phases:

| Symptom | Usually Related Phase | Where to Check |
|---|---|---|
| Unable to read configuration or profile | Environment preparation | File names, profiles, environment variables, command-line arguments, and property source precedence |
| Bean not found | Configuration/component scan processing or bean creation | Package scan, auto-configuration conditions, qualifiers, and dependencies |
| Bean initialization throws an exception | Refresh, singleton creation | Constructor, `@PostConstruct`, infrastructure connections, and bean configuration |
| Unable to create web server | Web context onRefresh | WebApplicationType, starters, server factories, and conflicting dependencies |
| Port already in use | Starting embedded server | Value of server.port, process occupying the port, and bind permissions |
| Runner fails | After ApplicationStartedEvent | Runner logic, external data, timeouts, and exceptions |
| Not receiving requests despite context creation | Web server or mappings | Whether server started, port, context path, controller mappings, and network |

When startup fails, Spring Boot publishes `ApplicationFailedEvent` when possible, records the exception, and closes the created context to release resources. If the server had already started before a runner failed, closing the context stops the server.

### 13.1. Viewing Applied Auto-configurations

Run the application with the `--debug` option to inspect the condition evaluation report:

~~~bash
./gradlew bootRun --args="--debug"
~~~

The report helps identify which auto-configurations were applied, which were excluded, and which conditions did not match. Combine this with logs from the relevant packages to pinpoint why a bean is missing or unexpectedly created.

### 13.2. Measuring Startup Time

You can use `BufferingApplicationStartup` to collect startup steps. For applications with Spring Boot Actuator, you can configure the appropriate startup endpoint to inspect the recorded steps. Management endpoints should be configured and secured according to the application's policies.

Do not conclude that startup is slow from a single total-time log line alone. Analyze individual startup steps, especially bean creation, configuration loading, connection pool initialization, external service calls, and web server startup.

## 14. Closing the ApplicationContext and Stopping the Web Server

When the application terminates, the context must be closed to release resources. `ConfigurableApplicationContext.close()` triggers the shutdown sequence:
- Publishes the context closed event.
- Stops beans participating in the lifecycle.
- Stops the embedded web server.
- Invokes bean destruction callbacks, such as `@PreDestroy` or `DisposableBean`.
- Releases resources managed by the context.

Spring Boot registers a shutdown hook by default to close the context when the JVM exits normally. In deployment environments, ensure the process can receive the stop signal and has sufficient time to shut down.

You can enable graceful shutdown:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

Graceful shutdown allows the server to stop accepting new requests and wait for in-flight requests to complete within the configured duration before lifecycle components are stopped. Actual timing also depends on the server, the requests, and deployment configuration.

## 15. Common Misconceptions

1. **Assuming `SpringApplication.run` only creates an ApplicationContext.** In reality, it orchestrates the Environment, context, refresh, web server, runners, and lifecycle events.
2. **Assuming that because the context exists, every bean has been created.** Bean definitions may be loaded, but bean instances are only created in the appropriate phase; lazy and prototype beans follow their own rules.
3. **Assuming ApplicationContext is Tomcat or Netty.** The context manages the server and beans; the server is a runtime component belonging to the web context.
4. **Assuming `ContextRefreshedEvent` means the application is ready to accept traffic.** Runners still execute after this event; the typical startup completion milestone is `ApplicationReadyEvent`.
5. **Putting business logic in constructors or initializers.** These phases can run before all dependencies and infrastructure are ready. Choose a runner or event suited to your needs.
6. **Assuming auto-configuration always creates default beans.** Classpath conditions, properties, and existing beans can cause configurations not to apply or to back off.
7. **Forcing WebApplicationType without checking dependencies.** The application type must be compatible with the actual starters and runtime stack.
8. **Using runners for unbounded tasks.** Runners complete before ApplicationReadyEvent, so a hung task can keep the application in an unready state.
9. **Assuming a successfully started server means endpoints are working properly.** The server can be listening on a port while controller mappings, security filters, databases, or external dependencies are still failing.

## 16. Step-by-Step Debugging Checklist for Startup

When you need to identify where the application stopped during startup, follow this sequence:

1. Verify the primary source and the class annotated with `@SpringBootApplication`.
2. Verify web dependencies and the actual WebApplicationType.
3. Check the Environment, profiles, and properties affecting the server.
4. Verify that the context is created with the expected type.
5. Check component scanning, bean definitions, and the condition evaluation report.
6. Find the first exception during refresh; subsequent errors may just be cascading consequences.
7. Check web server factory creation and port binding.
8. Confirm ApplicationStartedEvent, then check the runners.
9. Confirm ApplicationReadyEvent and send an HTTP request to a test endpoint.
10. Check the shutdown hook and graceful shutdown when handling termination lifecycle behavior.

In integration tests, `@SpringBootTest` can initialize the ApplicationContext according to the test configuration. The `webEnvironment` attribute lets you choose mock web, random port, defined port, or no web environment. Testing with a random port is useful to verify that the server actually starts and endpoints receive HTTP requests; mock context tests are suitable when you only need to verify configuration and beans.

## 17. Key Takeaways

- `SpringApplication` orchestrates startup; `ApplicationContext` is the container managing beans and infrastructure; the embedded web server handles HTTP.
- The Environment is prepared before the context refreshes, so profiles and settings affecting Config Data must be provided in the right phase.
- `WebApplicationType` determines whether the context is Servlet, Reactive, or None.
- `refresh()` processes bean definitions, auto-configuration, BeanFactoryPostProcessors, BeanPostProcessors, and initializes singletons.
- The web context creates the server during refresh and starts the server as refresh finishes.
- `ApplicationStartedEvent` is published after refresh and before runners; `ApplicationReadyEvent` is published after runners complete.
- Runners are suited for bounded startup tasks with proper error handling; event listeners are suited for reacting to specific lifecycle milestones.
- Closing the ApplicationContext stops lifecycle components, stops the web server, and invokes resource cleanup callbacks.

Understanding the boundaries between Environment preparation, context creation, refresh, web server startup, and runner completion helps you read startup logs systematically, place initialization code at the right time, and troubleshoot failures without guessing.
