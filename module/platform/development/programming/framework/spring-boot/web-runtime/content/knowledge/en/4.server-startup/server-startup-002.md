# The Role of Auto-Configuration in Creating `WebServerFactory` (Spring Boot 3.3.x)

## 1. The Core Problem to Understand at Server Startup

In a Spring Boot web application, developers typically only declare `spring-boot-starter-web` or `spring-boot-starter-webflux`, write a class annotated with `@SpringBootApplication`, and call `SpringApplication.run(...)`. The HTTP server is still created and started even though the application never explicitly writes `new Tomcat()`, `new Jetty()`, or `new Netty()`.

The bridge connecting the two sides is **auto-configuration**: based on the web application type, libraries on the classpath, existing beans, and configuration properties, Spring Boot registers **an appropriate `WebServerFactory` bean**. Then the **web application context** uses that factory to create and manage the **actual `WebServer` object**.

Three components must be distinguished:

| Component | Responsibility | Examples |
| --- | --- | --- |
| Auto-configuration | Decides which factory bean to register and provides related customizers | `ServletWebServerFactoryAutoConfiguration`, `ReactiveWebServerFactoryAutoConfiguration` |
| `WebServerFactory` | Holds necessary configuration and **creates** the server when requested by the context | `TomcatServletWebServerFactory`, `NettyReactiveWebServerFactory` |
| `WebServer` | Represents the created server, with `start()`/`stop()` lifecycle and active port | Embedded server adapter returned by the factory |

**The factory is not the server listening on the port.** Having a factory bean does not mean the server has opened a socket yet; creation and startup still happen within the refresh/start lifecycle of the application context.

## 2. Startup Sequence: Who Creates the Factory and Who Uses It?

For a typical embedded web application, the conceptual flow is:

```text
SpringApplication.run(...)
    |
    +--> Infer WebApplicationType (SERVLET / REACTIVE / NONE)
    |
    +--> Create the corresponding ApplicationContext type
    |
    +--> Read application configuration and process auto-configuration
    |      |
    |      +--> Evaluate conditions (classpath, web type, existing beans)
    |      +--> Register ServletWebServerFactory or ReactiveWebServerFactory
    |      +--> Bind server.* and apply WebServerFactoryCustomizer beans
    |
    +--> Context refresh: look up the appropriate factory
    |      |
    |      +--> factory.getWebServer(...) creates the embedded WebServer
    |      +--> Attach corresponding handler / ServletContextInitializer
    |
    +--> Complete the server startup lifecycle
           |
           +--> Server begins accepting HTTP requests
           +--> Publish the appropriate WebServerInitializedEvent
```

This is a **flow of responsibilities**, not a literal list of Java methods called consecutively with those exact names.

Key milestones:

1. `@SpringBootApplication` includes enabling auto-configuration. Spring Boot loads the list of auto-configuration classes provided by the framework and evaluates their conditions.
2. `SpringApplication` selects the web application type; the matching context type is created, such as `AnnotationConfigServletWebServerApplicationContext` or `AnnotationConfigReactiveWebServerApplicationContext`.
3. During context refresh, auto-configuration bean definitions and customizer beans are processed. The factory must exist before the context uses it to build the server.
4. For Servlet, `ServletWebServerApplicationContext` looks up **one** `ServletWebServerFactory` and calls `getWebServer(...)` with the `ServletContextInitializer` instances. For Reactive, `ReactiveWebServerApplicationContext` uses `ReactiveWebServerFactory` with `HttpHandler`.
5. The context manages the server lifecycle; server readiness is announced via `ServletWebServerInitializedEvent` or `ReactiveWebServerInitializedEvent` (both belong to the `WebServerInitializedEvent` family).

**Key point:** auto-configuration mainly **registers and customizes the factory bean**; the application context is what **asks the factory to create the `WebServer`** and coordinates its lifecycle. Do not attribute the entire server startup to a single auto-configuration class.

## 3. How Does Spring Boot Decide Between Servlet and Reactive?

| Application Type | Typical Scenario | Context | Factory Type Required |
| --- | --- | --- | --- |
| `SERVLET` | Spring MVC/Servlet stack present, typically via `spring-boot-starter-web` | `ServletWebServerApplicationContext` | `ServletWebServerFactory` |
| `REACTIVE` | WebFlux present without Spring MVC, typically via `spring-boot-starter-webflux` | `ReactiveWebServerApplicationContext` | `ReactiveWebServerFactory` |
| `NONE` | Non-web application or explicitly configured non-web mode | Regular context | No embedded HTTP server factory needed |

If both Spring MVC and WebFlux are on the classpath, Spring Boot typically chooses **SERVLET** by default inference. You cannot look only at Reactor Netty in dependencies and conclude the application is running in Reactive mode.

You can explicitly configure this:

```properties
# Do not create a web application context or run an embedded HTTP server
spring.main.web-application-type=none
```

This setting differs from `server.port=-1`: `-1` disables opening HTTP endpoints while still allowing a web application context to be created when needed. Meanwhile, `server.port=0` requests an available ephemeral port; it does not disable the server.

## 4. The Servlet Branch: `ServletWebServerFactoryAutoConfiguration`

In Spring Boot 3.3.x, the main auto-configuration class is located in package:

```java
org.springframework.boot.autoconfigure.web.servlet.ServletWebServerFactoryAutoConfiguration
```

Important conditions and mechanisms:

- `@ConditionalOnWebApplication(type = SERVLET)`: applies only to Servlet applications.
- `@ConditionalOnClass(jakarta.servlet.ServletRequest.class)`: applies only when the required Servlet API is on the classpath.
- `@EnableConfigurationProperties(ServerProperties.class)`: enables binding server settings from `server.*`.
- Imports embedded server configurations for Tomcat, Jetty, and Undertow; child configurations use classpath conditions and **back off when a matching `ServletWebServerFactory` already exists**.
- Registers infrastructure so `WebServerFactoryCustomizer` beans are applied to the factory, along with Spring Boot's default customizers.

With the default dependencies of `spring-boot-starter-web`:

```text
spring-boot-starter-web
    -> spring-boot-starter-tomcat
       -> required Tomcat/Servlet libraries
    -> Servlet + Tomcat conditions match
    -> TomcatServletWebServerFactory bean
    -> ServletWebServerApplicationContext uses the bean
    -> Embedded WebServer based on Tomcat
```

If Tomcat is properly replaced with Jetty or Undertow in the dependency graph, the corresponding factory can be created without rewriting the application's startup logic.

Examples of common factory types:

| Container on Classpath | Servlet Branch Factory |
| --- | --- |
| Tomcat | `TomcatServletWebServerFactory` |
| Jetty | `JettyServletWebServerFactory` |
| Undertow | `UndertowServletWebServerFactory` |

**Do not confuse `DispatcherServlet` with `ServletWebServerFactory`.** `DispatcherServlet` handles request routing in Spring MVC; the factory creates the HTTP container and deals with port, connector, context path, SSL, etc. Spring MVC auto-configuration and web-server-factory auto-configuration are two cooperating parts with distinct responsibilities.

## 5. The Reactive Branch: `ReactiveWebServerFactoryAutoConfiguration`

In Spring Boot 3.3.x, the corresponding class is:

```java
org.springframework.boot.autoconfigure.web.reactive.ReactiveWebServerFactoryAutoConfiguration
```

This class applies only when `@ConditionalOnWebApplication(type = REACTIVE)` and the required Reactive APIs are present, while also providing `ServerProperties`, customizers, and appropriate embedded server configurations.

`spring-boot-starter-webflux` includes Reactor Netty by default. In that case, the typical path is:

```text
spring-boot-starter-webflux
    -> spring-boot-starter-reactor-netty
    -> ReactiveWebServerFactoryAutoConfiguration
    -> NettyReactiveWebServerFactory
    -> ReactiveWebServerApplicationContext
    -> WebServer serving WebFlux's HttpHandler
```

The Reactive branch also has corresponding factories when using Tomcat, Jetty, or Undertow instead of Reactor Netty:

| Container | Reactive Branch Factory |
| --- | --- |
| Reactor Netty | `NettyReactiveWebServerFactory` |
| Tomcat | `TomcatReactiveWebServerFactory` |
| Jetty | `JettyReactiveWebServerFactory` |
| Undertow | `UndertowReactiveWebServerFactory` |

`ReactiveWebServerFactory` is not a kind of `ServletWebServerFactory`. Putting a factory from the other stack into the current context does not satisfy that context's bean requirement. Similarly, using WebFlux **does not guarantee** the server is always Netty; you must inspect both dependencies and the web application type.

## 6. Conditional Mechanism and the "Back-Off" Principle

Auto-configuration is **conditional**; it does not force every application to use Tomcat.

Suppose the application already provides its own `ServletWebServerFactory` bean. Boot's default factory configuration will **back off** according to `@ConditionalOnMissingBean`, rather than trying to create a second default bean for the same role. Boot's customizers can still apply to that custom factory.

Three decision layers must be distinguished:

1. **Web application type:** does the current context need a Servlet factory, a Reactive factory, or no factory at all?
2. **Classpath:** which server libraries are present so the corresponding configuration satisfies its conditions?
3. **Bean registry:** is a factory bean already defined by the application or another library, and is there a single suitable factory?

Example scenarios:

| Scenario | Expected Outcome |
| --- | --- |
| `starter-web` with default Tomcat; no custom factory declared | Boot provides `TomcatServletWebServerFactory` |
| `starter-web` with Tomcat properly replaced by Jetty | Boot provides the Jetty factory |
| `starter-webflux` with Reactor Netty and Reactive web type | Boot provides `NettyReactiveWebServerFactory` |
| Custom Servlet factory bean declared in a Servlet application | Default factory configuration backs off; context uses the provided bean |
| Forced `web-application-type=none` | No embedded web server needs to be created |
| Servlet context used, but all suitable Servlet web-server factories are missing | Startup may fail due to missing required factory bean |
| Multiple factories of the same type unexpectedly registered | Context cannot pick a single factory and startup may fail |

`@ConditionalOnMissingBean` does not mean "Spring Boot always resolves every conflicting dependency automatically." If you include multiple containers simultaneously or register multiple beans for the same role, you must inspect the actual condition matches and bean registry results.

## 7. When Do `ServerProperties` and Customizers Affect the Factory?

Settings from `application.properties`, `application.yml`, environment variables, or command-line arguments are merged in the `Environment`. Boot binds the `server.*` property group into `ServerProperties` and uses `WebServerFactoryCustomizer` beans to apply common and server-specific settings to the factory **before the factory is used to create the server**.

Example for a Spring MVC application:

```yaml
# src/main/resources/application.yml
server:
  port: 9090
  servlet:
    context-path: /api
```

Then a controller route `@GetMapping("/ping")` is accessed at `http://localhost:9090/api/ping`. `server.servlet.context-path` belongs to Servlet; do not mechanically apply it to WebFlux running on Netty.

Configuration approaches in order of preference:

1. Use `server.*` for common needs: port, bind address, SSL, HTTP compression, and server-specific settings like `server.tomcat.*`.
2. Add a `WebServerFactoryCustomizer<T>` when you need to modify the factory in Java, especially for options not exposed via `server.*`.
3. Provide your own factory bean only when you need to replace server creation at a deeper level. This increases maintenance responsibility for configuration and interaction with default customizers.

`WebServerFactoryCustomizerBeanPostProcessor` is the mechanism that applies customizers to the factory bean when the bean is initialized. Therefore, a customizer is not simply code that runs after the HTTP server is already accepting requests.

## 8. Hands-On Exercise: Observing the Factory Created by Boot

The example below uses **Java 21 and Spring Boot 3.3.13** (compatible with Java 17+). This is a standalone application runnable with the Gradle Wrapper, without declaring a factory manually.

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

**`src/main/java/com/example/demo/WebRuntimeApplication.java`**

```java
package com.example.demo;

import java.util.Map;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.context.WebServerApplicationContext;
import org.springframework.boot.web.servlet.server.ServletWebServerFactory;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class WebRuntimeApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebRuntimeApplication.class, args);
    }

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }

    @Bean
    ApplicationRunner inspectWebServerFactory(ApplicationContext context) {
        return args -> {
            Map<String, ServletWebServerFactory> factories =
                    context.getBeansOfType(ServletWebServerFactory.class);

            System.out.println("Factory count: " + factories.size());
            factories.values().forEach(factory ->
                    System.out.println("Factory: "
                            + factory.getClass().getSimpleName()));

            int actualPort =
                    ((WebServerApplicationContext) context).getWebServer().getPort();
            System.out.println("Port: " + actualPort);
        };
    }
}
```

**`src/main/resources/application.properties`**

```properties
server.port=9090
server.servlet.context-path=/api
```

**Run and call HTTP** (in the project directory with Gradle Wrapper):

```bash
./gradlew bootRun
```

Among other Spring Boot log lines, the program prints the following lines upon startup with the default Tomcat dependency and port 9090 unoccupied:

```text
Factory count: 1
Factory: TomcatServletWebServerFactory
Port: 9090
```

In another terminal:

```bash
curl -s http://localhost:9090/api/ping
```

The exact HTTP response body is `pong` (without a trailing newline because the endpoint returns the string `"pong"`).

**Result explanation:** `starter-web` provides the Servlet/Tomcat libraries; auto-configuration registers a `TomcatServletWebServerFactory`; the context uses the factory to create embedded Tomcat; `ApplicationRunner` runs once the context has started, so it can read the factory type and actual port. The `curl` command verifies the server is serving requests.

Note: `Factory count: 1` is the result of this example configuration, not a guarantee that every application has only one factory bean in all cases. To determine the port when using `server.port=0`, read `WebServer.getPort()` after the server starts or listen for `WebServerInitializedEvent`, rather than inferring from the configured value 0.

### Practice: Modifying the Factory Without Replacing the Factory Bean

Add the following class to the same `com.example.demo` package:

**`src/main/java/com/example/demo/ServerTuning.java`**

```java
package com.example.demo;

import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.boot.web.servlet.server.ConfigurableServletWebServerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ServerTuning {

    @Bean
    WebServerFactoryCustomizer<ConfigurableServletWebServerFactory>
            useAnotherPort() {
        return factory -> factory.setPort(9191);
    }
}
```

Because Boot's default customizers typically run before custom-declared customizers without an explicit order, this example overrides port 9090 from `application.properties`; after restarting, `Port: 9191` is printed and the endpoint is at `http://localhost:9191/api/ping`. Do not copy hardcoding a fixed port in two places into real projects without a reason: using properties alone is usually easier to maintain.

If you need to explicitly control the ordering among multiple customizers, use `@Order`/`Ordered` intentionally and verify the final effect. Auto-configured customizers have order `0`; the order of user-defined customizers depends on their actual order configuration.

## 9. Swapping Containers While Keeping the Same Startup Model

Example with Gradle, replacing the default Tomcat in the Servlet stack with Jetty:

```groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }
    implementation 'org.springframework.boot:spring-boot-starter-jetty'
}
```

After refreshing dependencies and restarting, the expected factory is `JettyServletWebServerFactory`. There is no need to modify the controller, `SpringApplication.run(...)`, or manually call `factory.getWebServer(...)`: auto-configuration handles selecting the factory, and the Servlet context still coordinates the lifecycle.

Unused containers must be excluded consistently from the dependency graph; simply adding the Jetty starter while keeping Tomcat easily leads to confusing classpath behavior. Container versions are managed via Spring Boot's compatible dependency management.

## 10. Diagnosing When the Server Is Not Created or Fails to Start

Check in the order: **application type → libraries → conditions → factory bean → port configuration → server error**.

| Symptom | Common Cause | How to Check and Fix |
| --- | --- | --- |
| Application runs as a console program, no HTTP port opened | `WebApplicationType.NONE` or missing web starter | Check `spring.main.web-application-type`, `starter-web`/`starter-webflux`, and dependency tree |
| Servlet context reports missing `ServletWebServerFactory` | No suitable embedded container; Tomcat excluded without adding Jetty/Undertow; auto-config excluded | Check classpath and condition report; add a valid container or review exclusions |
| WebFlux context reports missing `ReactiveWebServerFactory` | Missing reactor-netty or compatible reactive container | Check reactive starter, dependencies, and web application type |
| Context reports multiple factories or cannot pick a unique factory | Multiple factory beans registered manually or library added an unexpected factory | List beans of the corresponding interface; keep exactly one usable factory |
| Factory exists but HTTP startup fails | Port already in use, bind permission denied, misconfigured SSL/connector | Read root cause (`BindException`, SSL errors, etc.) and actual port/address values |
| Changed `server.port` but application uses another port | Higher-precedence profile/env/CLI or a customizer overriding it | Check effective configuration and `WebServerFactoryCustomizer` beans |
| Added WebFlux but application still runs Servlet | Spring MVC is on the classpath so Boot defaults to Servlet | Check dependency tree and WebApplicationType, choose stack intentionally |

How to enable the condition evaluation report in development:

```bash
./gradlew bootRun --args='--debug'
```

In the `CONDITIONS EVALUATION REPORT`, look for `ServletWebServerFactoryAutoConfiguration` or `ReactiveWebServerFactoryAutoConfiguration` under positive/negative matches. Examine **why conditions matched or did not match**, not just which container name appears in the logs. You can also use Actuator `/actuator/conditions` when installed and intentionally exposed in an appropriate environment.

When writing tests, note that `@SpringBootTest(webEnvironment = RANDOM_PORT)` typically starts a real server on a random port, whereas mock web context tests do not open a socket. The existence of controller beans or passing mock HTTP tests does not by itself prove the factory created a real server.

## 11. Misconceptions to Avoid

1. **"`@SpringBootApplication` directly initializes Tomcat."** Inaccurate: the annotation activates the configuration mechanism; the factory is registered conditionally, and the context uses the factory to create the server.
2. **"`WebServerFactory` and `WebServer` are the same thing."** The factory is the tool for creating/configuring; `WebServer` is the created object whose lifecycle is managed.
3. **"Adding WebFlux always means using Netty."** False if Spring MVC is also present and Boot chooses Servlet, or if the reactive stack swaps the container.
4. **"Declaring `server.port` creates the factory bean."** The property only supplies configuration data; the factory still requires auto-configuration or a bean definition whose conditions are met.
5. **"Declaring your own factory means Boot no longer participates in configuration."** Default factories may back off, but auto-configured customizers can still apply to the user-provided bean.
6. **"`@EnableWebMvc` is required to run embedded Tomcat."** False. `@EnableWebMvc` changes how Spring MVC is configured; creating the embedded server is the responsibility of web-server-factory configuration and the application context.
7. **"Once context refresh finishes, every port is guaranteed to be usable."** Startup can fail on port binding or server configuration; verify via initialization success events, logs, and root causes.

## 12. Self-Check Questions

- If `spring-boot-starter-tomcat` is excluded without adding an equivalent server, which bean does the Servlet auto-configuration branch require, and why might startup fail?
- Why can a `TomcatServletWebServerFactory` bean exist before the `WebServer` begins accepting HTTP requests?
- How does changing `server.port=8080` to `server.port=0` affect customizers and the actual port value?
- Why is `WebServerFactoryCustomizer` usually a better choice than writing a new factory bean just to change the port?
- When both `starter-web` and `starter-webflux` are present, what will you check before concluding which factory is used?

**Core takeaway:** auto-configuration ensures a web application receives the appropriate factory conditionally and applies configuration; the **web application context** uses that factory to create, start, and manage the embedded server. Simply distinguishing *selecting the factory*, *customizing the factory*, and *operating the server* allows you to trace most failures during HTTP startup.

### References (Spring Boot 3.3 APIs and Guides)

- Servlet web applications: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Embedded web servers: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Servlet factory auto-configuration API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/servlet/ServletWebServerFactoryAutoConfiguration.html
- Reactive factory auto-configuration API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/reactive/ReactiveWebServerFactoryAutoConfiguration.html