# WebServerFactoryCustomizer and When Configuration Is Applied

## 1. Objectives and Context

Spring Boot can automatically create an embedded HTTP web server when an application runs on the Servlet or Reactive web stack. Usually, `server.*` properties in `application.properties` or `application.yml` are all you need to configure the port, bind address, HTTPS, HTTP/2, compression, and supported capabilities.

When factory-level intervention is needed, Spring Boot provides the interface:

```java
org.springframework.boot.web.server.WebServerFactoryCustomizer<T extends WebServerFactory>
```

This is a functional interface with a single method:

```java
void customize(T factory);
```

A bean implementing this interface receives a compatible web server factory to adjust its configuration **before the web server is created and started**. The focus of this lesson is understanding precisely which object the customizer mutates, when it runs, how its ordering interacts with `server.*` configuration, and how to use and verify it safely.

## 2. Distinguishing WebServerFactory, WebServer, and WebServerFactoryCustomizer

| Component | Role | Key timing |
|---|---|---|
| `WebServerFactory` | Factory that creates the embedded server, such as Tomcat or Reactor Netty | Instantiated as a bean during context refresh |
| `ConfigurableWebServerFactory` | Interface extending the factory with common settings like port, address, SSL, error pages | Setters must be applied before the factory creates the server |
| `WebServerFactoryCustomizer<T>` | Callback modifying a factory matching type `T` | Invoked when BeanPostProcessor processes the factory bean, before the server is created |
| `WebServer` | Object representing the configured server, providing start/stop operations and reading the port | Created by the factory and managed within the web context lifecycle |
| `WebServerInitializedEvent` | Event signaling the server is ready; can read the actual port | After the server is initialized, suitable for observing results |

Core point: **A customizer modifies the factory, not directly a running server**. Calling `factory.setPort(9090)` affects the configuration the factory uses when creating the server; it is not equivalent to changing the port of an already-bound socket at runtime.

A customizer is not a Spring MVC `HandlerInterceptor`, a Servlet `Filter`, or a WebFlux `WebFilter`. Those components execute when handling HTTP requests; a customizer runs during bootstrap.

## 3. Startup Flow and Application Timing

Conceptual diagram:

```text
SpringApplication.run(...)
        |
Prepare Environment / read application.properties, profiles, env vars
        |
Create ApplicationContext and register bean definitions
        |
Register required BeanPostProcessors
        |
Create web server factory bean
        |
WebServerFactoryCustomizerBeanPostProcessor
  -> locate matching WebServerFactoryCustomizers
  -> sort by order
  -> invoke customize(factory)
        |
Customized factory
        |
Web application context uses the factory to create WebServer
        |
Server binds/listens/starts per Spring Boot lifecycle
        |
WebServerInitializedEvent (actual port known)
        |
ApplicationReadyEvent once application startup completes
```

`WebServerFactoryCustomizerBeanPostProcessor` is the key mechanism. It is a dedicated `BeanPostProcessor` that applies customizers to beans of type `WebServerFactory`. Customizer callbacks run during **initialization of the factory bean**, very early in the Spring lifecycle.

Practical consequences:

1. When `customize(factory)` runs, the web server is not yet ready to serve requests. It is suitable for changing port, address, connectors, error pages, or server creation options.
2. Business beans, databases, JPA, and some other auto-configurations may not yet be fully initialized. Customizers should not depend on heavy beans.
3. If you want to adjust values before Spring binds `server.*`, handle them in an appropriate configuration or Environment layer. If you want to know **the actual port after binding**, listen for the server-initialized event.
4. Changing configuration after the server has already been created generally does not automatically apply to the running server. Changing port, SSL, or connectors typically requires an operational restart.

The milestones in the diagram generalize normal Spring Boot startup; exact steps may vary by embedded server, Boot version, web stack, and auto-configuration.

## 4. Basic Example with ConfigurableWebServerFactory

`ConfigurableWebServerFactory` is a shared abstraction across many Servlet and Reactive factory types. For simple configuration needs, using the common type avoids coupling to a specific server.

Create `WebServerConfiguration.java` in a package scanned by Spring Boot component-scan:

```java
package com.example.demo;

import org.springframework.boot.web.server.ConfigurableWebServerFactory;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class WebServerConfiguration {

    @Bean
    WebServerFactoryCustomizer<ConfigurableWebServerFactory> portCustomizer() {
        return factory -> factory.setPort(9090);
    }
}
```

The example above applies to Spring Boot 3.x and 4.x with the shared imports shown. The `@Bean` method returns a lambda as a `WebServerFactoryCustomizer<ConfigurableWebServerFactory>`. When Boot prepares the factory, the callback sets port 9090 before the server is created.

To test with a Spring Boot application that has a web dependency and a simple controller, you can use:

```java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class PingController {

    @GetMapping("/ping")
    String ping() {
        return "pong";
    }
}
```

Start with the command matching a Maven Spring Boot project:

```bash
./mvnw spring-boot:run
```

After the application starts:

```bash
curl -s http://localhost:9090/ping
```

Expected response body:

```text
pong
```

The Java snippets above are classes placed inside a **Spring Boot project that already has a `@SpringBootApplication` main class and the matching web dependency**; they are not standalone Java programs compiled directly with `javac`. If another server configuration overrides the same property in a later customizer order, the actual port can differ; in that case, check customizer ordering.

Note: using a customizer to change the port is solely to illustrate the API. For normal port changes, configuring `server.port=9090` is simpler and easier to maintain.

## 5. Prefer Properties Before Writing a Customizer

Start with standard properties:

```properties
server.port=9090
server.address=127.0.0.1
server.compression.enabled=true
```

This example asks the server to bind to loopback (accessible only from the local machine) on port 9090 and enable compression as supported by the server. In production, `server.address` must align with network architecture and reverse proxies.

Some common configuration groups:

- `server.port`: primary HTTP port.
- `server.address`: network address the server listens on.
- `server.ssl.*`: TLS configuration when HTTPS is terminated directly at the application.
- `server.http2.enabled`: requests enabling HTTP/2 when supported by the web server and transport.
- `server.compression.*`: enables and configures response compression.
- `server.tomcat.*`, `server.jetty.*`: server-specific options, depending on Boot version.

`WebServerFactoryCustomizer` is useful when you need an embedded-server-specific API that available properties do not expose, such as adding a connector, tuning server resources, or deeper configuration hooks. Avoid writing multiple customizers for work already solved cleanly by properties.

## 6. Customizer Ordering and Configuration Conflicts

Spring Boot also uses internal `WebServerFactoryCustomizer` beans to apply `server.*` properties. Per embedded web server documentation, Boot-registered customizers have order **0**; normally they run before user customizers unless you explicitly specify another order.

You can control order via `@Order` or `Ordered`. Convention: **smaller order numbers run earlier**. When customizers modify the same field, the value set by the callback executing **last** usually remains on the factory, unless another configuration step overwrites it later.

Illustrative example:

```java
package com.example.demo;

import org.springframework.boot.web.server.ConfigurableWebServerFactory;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(100)
public class ExplicitPortCustomizer
        implements WebServerFactoryCustomizer<ConfigurableWebServerFactory> {

    @Override
    public void customize(ConfigurableWebServerFactory factory) {
        factory.setPort(9090);
    }
}
```

Suppose `application.properties` has:

```properties
server.port=8080
```

In a typical setup, Boot's order-0 customizer applies port 8080 first; `ExplicitPortCustomizer` at order 100 runs later and changes the factory to 9090. This demonstrates ordering relationships, not a recommended way to manage environment configuration.

Conversely, if a customizer runs before the default customizer, `server.port` can overwrite the value set earlier. Therefore, when a property appears ineffective or the server binds an unexpected port, check:

1. The property sources and final `server.port` value in `Environment`.
2. How many `WebServerFactoryCustomizer` beans match the factory.
3. `@Order` or `Ordered` on each customizer.
4. Whether multiple customizers mutate port or address.
5. Which server or context is actually being initialized.

If multiple customizers share the same order, do not rely on accidental ordering to decide which writes last. Define explicit ordering or consolidate the configuration logic.

## 7. Server-Specific Embedded Customizers

Abstractions and detailed APIs vary depending on the selected server:

| Environment | Common factory | Notes |
|---|---|---|
| Spring MVC + Tomcat | `TomcatServletWebServerFactory` | Has dedicated APIs for customizing Tomcat |
| Spring MVC + Jetty | `JettyServletWebServerFactory` | Has dedicated APIs for Jetty |
| Spring WebFlux + Reactor Netty | `NettyReactiveWebServerFactory` | Configures the Reactor Netty reactive server |
| Spring WebFlux + Tomcat/Jetty | Corresponding reactive factory | Depends on server adapter and starter/configuration |

The generic type `T` of `WebServerFactoryCustomizer<T>` matters: a customizer for a Tomcat factory is not a callback for every server type. If the application moves from Tomcat to Jetty, Tomcat-coupled customizers must be reviewed or replaced.

For Spring Boot 3.x, the Tomcat factory import is usually:

```java
import org.springframework.boot.web.embedded.tomcat.TomcatServletWebServerFactory;
```

In Spring Boot 4.x, the Tomcat factory package was reorganized, for example:

```java
import org.springframework.boot.tomcat.servlet.TomcatServletWebServerFactory;
```

Project source code must use imports matching the running Spring Boot version. Do not copy a version-specific import without checking dependencies.

Example illustrating the essence of a Tomcat customizer, with `TomcatServletWebServerFactory` imported for your corresponding version:

```java
@Component
class TomcatContextPathCustomizer
        implements WebServerFactoryCustomizer<TomcatServletWebServerFactory> {

    @Override
    public void customize(TomcatServletWebServerFactory factory) {
        factory.setContextPath("/internal");
    }
}
```

The matching Spring imports are `org.springframework.stereotype.Component` and `org.springframework.boot.web.server.WebServerFactoryCustomizer`. For context path configuration, normal applications should prefer `server.servlet.context-path=/internal`; the example uses Tomcat's API simply to show how to target a single factory. This snippet illustrates the specified imports and is not a full Java file.

## 8. Lifecycle and Dependency Limitations

### 8.1. BeanPostProcessor Runs Very Early

The `WebServerFactoryCustomizer` Javadoc warns that customizers are typically called by `WebServerFactoryCustomizerBeanPostProcessor` very early in the `ApplicationContext` lifecycle. Injecting heavy-to-initialize beans into a customizer constructor can force their premature initialization.

Pattern to avoid:

```java
@Component
class RiskyServerCustomizer
        implements WebServerFactoryCustomizer<ConfigurableWebServerFactory> {

    private final ExpensiveDatabaseService databaseService;

    RiskyServerCustomizer(ExpensiveDatabaseService databaseService) {
        this.databaseService = databaseService;
    }

    @Override
    public void customize(ConfigurableWebServerFactory factory) {
        // Query database to decide server configuration.
    }
}
```

This snippet illustrates a design smell; `ExpensiveDatabaseService` is a hypothetical class. Server assembly should not depend on database connections or JPA components that need to initialize later.

A safer approach is using `Environment`, a simple `@ConfigurationProperties` bean, or configuration provided at startup. If you must look up another dependency, consider lazy lookup per the API guidelines, while still avoiding initializing complex beans inside the callback.

### 8.2. @PostConstruct Is Not Guaranteed for Changing Server Configuration

`@PostConstruct` runs when a specific bean is initialized, with no guarantee that it runs before the factory is processed by customizers. Therefore, do not use `@PostConstruct` on a controller/service to change port, connectors, or SSL belonging to embedded server initialization.

Similarly, `ApplicationRunner`, `CommandLineRunner`, and `ApplicationReadyEvent` occur late relative to factory configuration. They are suited for post-bootstrap application tasks, not for deciding foundational properties of the listening socket.

### 8.3. Calling customize Does Not Equal Live Runtime Reconfiguration

Once the server has been created and bound to a port, mutating a factory object or updating `Environment` does not automatically update the running listener. Whether settings can change dynamically depends on the specific server and API; for the primary port and TLS settings, the safe and standard approach is deploying new configuration and restarting.

## 9. Port 0, Port -1, and When to Read the Actual Port

Two special values for `server.port`:

```properties
server.port=0
```

Value 0 asks the operating system to allocate an available ephemeral port. Before the server binds, a customizer only sees the configured value 0 and cannot predict the exact port that will be assigned.

```properties
server.port=-1
```

Value -1 is used by Spring Boot to disable the primary HTTP endpoint while still creating a web application context. Unlike `spring.main.web-application-type=none`, this value does not convert the entire application into a non-web context.

When you need to read the actual port, listen for `WebServerInitializedEvent`, for example with Spring Boot 4.x:

```java
package com.example.demo;

import org.springframework.boot.web.server.context.WebServerInitializedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ListeningPortReporter {

    @EventListener
    public void onWebServerReady(WebServerInitializedEvent event) {
        System.out.println("HTTP port: " + event.getWebServer().getPort());
    }
}
```

In Spring Boot 3.x, the corresponding event import is:

```java
import org.springframework.boot.web.context.WebServerInitializedEvent;
```

This example is intended for a running Spring Boot web project. When port 0 is configured, the output looks like `HTTP port: <actual port>`; the exact number depends on the OS at runtime and cannot be hardcoded.

If a project has both an application web server and a separate management web server (Actuator with a different `management.server.port`), there may be multiple contexts or corresponding events. Distinguish the server/context before concluding which port belongs to the main application.

In tests with `@SpringBootTest(webEnvironment = RANDOM_PORT)`, `@LocalServerPort` is a convenient way to receive the actual HTTP port. Do not try to inject the runtime port while a customizer is executing, as the server has not yet finished initializing.

## 10. Servlet, Reactive, NONE, and Non-Applicable Cases

- **SERVLET:** Boot typically creates a `ServletWebServerFactory`. Customizers matching that factory can configure Tomcat, Jetty, and supported servlet servers.
- **REACTIVE:** Boot typically creates a `ReactiveWebServerFactory`. You can customize via the common abstraction or a specialized reactive factory, depending on the runtime.
- **NONE:** no embedded web server needs to be built in the context. Thus customizers have no matching web server factory to run against.
- **WAR deployed to an external servlet container:** external infrastructure manages the server/listeners. Customizers for embedded factories are not the tool to configure externally operated Tomcat/Jetty.

If the application sits behind an ingress, reverse proxy, or load balancer, the public gateway port can differ from the embedded server's port. Calling `factory.setPort(...)` changes the application's listening port, not the gateway's listener or routing.

## 11. Testing and Debugging

### 11.1. Post-Startup Verification

- Inspect embedded server logs to check the bound port and server type.
- Call a real endpoint with `curl` or an HTTP test client.
- With port 0, read the port from `WebServerInitializedEvent` or use `@LocalServerPort` in integration tests.
- To verify startup code enters your customizer, place a breakpoint in `customize(factory)` and inspect the actual factory type.

Example:

```bash
curl -i http://localhost:9090/ping
```

If the sample application has `PingController` and the actual port is 9090, the response must have body `pong`. If connection fails, check startup logs, port binding, host, and profile configuration.

### 11.2. Common Errors

| Symptom | Common cause | Resolution |
|---|---|---|
| Customizer not invoked | Class not scanned, bean not declared, generic type does not match running factory, app has no embedded factory | Check component scan, bean registration, classpath, and web application type |
| `server.port` not as expected | Multiple customizers writing the same property; ordering or profile/config differences | Determine which customizer runs last and check actual Environment value |
| Startup error due to unready dependency | Customizer depends early on DataSource, JPA, or heavy beans | Use simple configuration or appropriate lazy lookup |
| Changing port in `ApplicationReadyEvent` has no effect | Server already created and listener already bound | Move configuration to properties or a factory customizer before startup |
| Listening on port 0 without knowing the port | Port is only assigned when binding the socket | Use `WebServerInitializedEvent` or `@LocalServerPort` in tests |
| Switching Tomcat to Jetty loses customization | Customizer generic tied to a specific Tomcat type | Write customizer against common abstraction or matching Jetty factory |
| Public port differs from `factory.setPort` | Reverse proxy, container mapping, ingress, or load balancer | Inspect each network hop and deployment configuration |
| New config does not affect running server | Customizer only applies when creating the embedded server | Restart/redeploy per system procedure |

### 11.3. Choosing the Right Solution for the Need

| Need | Appropriate place to configure |
|---|---|
| Change port, bind address, standard compression | `application.properties` or `application.yml` |
| Adjust factory options not exposed as properties | `WebServerFactoryCustomizer<T>` |
| Register servlet filters/servlets | `FilterRegistrationBean`, `ServletRegistrationBean`, or matching annotation mechanisms |
| Handle requests/controllers | Spring MVC/WebFlux handlers, filters, interceptors per stack |
| Observe actual port once server is ready | `WebServerInitializedEvent` |
| Run tasks after app startup finishes | `ApplicationRunner`, `CommandLineRunner`, `ApplicationReadyEvent` |
| Configure externally managed server | Configure reverse proxy, ingress, servlet container, or deployment runtime |

## 12. Design Checklist

1. Determine whether the project uses Servlet or Reactive and which embedded server.
2. Check whether a `server.*` property already exists for the requirement.
3. Only create a customizer when you need to affect the factory before server creation.
4. Use the common factory generic when common APIs suffice; use a server-specific class when specialized tuning is needed.
5. Ensure the bean is scanned/registered; check `@Order` when multiple customizers mutate the same setting.
6. Avoid depending on heavy-to-initialize beans inside customizers.
7. If you need the actual port, retrieve it after the server is initialized; do not read it while `customize` is running.
8. Check package compatibility between Spring Boot 3.x and 4.x.
9. Verify the server bound per configuration and works via HTTP tests.
10. Document clearly which port is the embedded server port and which is the reverse proxy/management port.

## 13. Key Takeaways

`WebServerFactoryCustomizer` is a hook in the **embedded web server initialization phase**, applied to the **factory bean** via `WebServerFactoryCustomizerBeanPostProcessor` **before the server starts running**. Callback ordering determines the outcome when multiple customizers change the same value. For common settings, prefer `server.*`; to observe the actual port after startup, use `WebServerInitializedEvent`. Avoid early dependencies on JPA, DataSource, or heavy beans, and do not treat customizers as a dynamic reconfiguration mechanism for a running listener.

## 14. References

- Spring Boot Reference — Embedded Web Servers: https://docs.spring.io/spring-boot/how-to/webserver.html
- WebServerFactoryCustomizer Javadoc: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/web/server/WebServerFactoryCustomizer.html
- WebServerFactoryCustomizerBeanPostProcessor Javadoc: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/web/server/WebServerFactoryCustomizerBeanPostProcessor.html
- ConfigurableWebServerFactory Javadoc: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/web/server/ConfigurableWebServerFactory.html
- WebServerInitializedEvent Javadoc (Spring Boot 4.x): https://docs.spring.io/spring-boot/api/java/org/springframework/boot/web/server/context/WebServerInitializedEvent.html
- WebServerInitializedEvent Javadoc (Spring Boot 3.x): https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/context/WebServerInitializedEvent.html