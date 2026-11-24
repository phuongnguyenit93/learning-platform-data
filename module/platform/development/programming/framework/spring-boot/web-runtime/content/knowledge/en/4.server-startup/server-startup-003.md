# ServletWebServerFactory and ReactiveWebServerFactory in Spring Boot

## 1. What Problem Does This Lesson Solve?

When running a Spring Boot Web application, we usually just call `SpringApplication.run(...)` and see Tomcat or Reactor Netty start up. So who creates the HTTP server, translates the `server.port` setting into a listening port, and connects the server to Spring MVC or WebFlux?

Two core interfaces answer that question:

- **`ServletWebServerFactory`**: creates an embedded web server for applications based on **Servlet / Spring MVC**.
- **`ReactiveWebServerFactory`**: creates an embedded web server for **Reactive / Spring WebFlux** applications.

Both are *factories*: they create a `WebServer` instance for the `ApplicationContext`, while Spring Boot manages when it starts, stops, is configured, and attaches the HTTP processing pipeline.

**Goals after this lesson:** recognize the two server startup paths; distinguish the "web stack" from the "HTTP server product"; understand the parameters of `getWebServer(...)`; know when to edit `application.yml` versus when to use `WebServerFactoryCustomizer`; and diagnose errors caused by the wrong factory, wrong dependencies, or port conflicts.

> **Example version:** the standalone runnable code below uses Spring Boot **4.1.x**, Java 17 or later. Spring Boot 3.5 shares the same concepts, but **the package names of the factories differ**; the comparison table in section 9 highlights the differences. Do not mix imports between the two major versions.

## 2. Factory, WebServer, and Web Stack Are Three Distinct Roles

- **Web stack** defines the HTTP intake and processing model: Spring MVC relies on Servlet, while WebFlux relies on `HttpHandler` and reactive mechanisms.
- **Web server** is the process/component that opens the network port and accepts connections: Tomcat, Jetty, Reactor Netty, etc. A server such as Tomcat can serve both MVC and WebFlux applications via different integration mechanisms.
- **Factory** is the interface for Spring Boot to create, customize, and wire the server matching the selected stack. It is not a `@RestController`, does not define routes itself, and does not handle individual business requests.

Both factories extend `WebServerFactory` and return `org.springframework.boot.web.server.WebServer`. A `WebServer` object provides lifecycle operations such as `start()`, `stop()`, and `getPort()`. In a standard Boot application, **do not call** `factory.getWebServer(...)` yourself in `main`: the `ApplicationContext` is responsible for creating and managing that object.

### Core Signatures

~~~java
// Conceptual API signatures in Spring Boot 4.x, not a standalone Java program:
public interface ServletWebServerFactory extends WebServerFactory {
    WebServer getWebServer(ServletContextInitializer... initializers);
}

public interface ReactiveWebServerFactory extends WebServerFactory {
    WebServer getWebServer(HttpHandler httpHandler);
}
~~~

The two signatures differ in **what gets attached to the server**:

1. `ServletContextInitializer...` initializes the Servlet context, allowing Boot to register Servlets, Filters, and Listeners, such as Spring MVC's `DispatcherServlet`. Multiple initializers may be present.
2. `HttpHandler` is the unified HTTP entry point of Spring WebFlux. Boot creates/provides the handler and passes it into the reactive factory; the specific server forwards requests to this handler.

The factory returns a configured server, but that is not yet a guarantee that "requests can be served immediately." Boot coordinates `start()` during the context refresh lifecycle; HTTP traffic can only be served normally once the server is ready.

## 3. Two Parallel Startup Flows

~~~text
Servlet: SpringApplication
   -> WebApplicationType.SERVLET
   -> ServletWebServerApplicationContext
   -> ServletWebServerFactory (Tomcat/Jetty...)
   -> getWebServer(ServletContextInitializer...)
   -> ServletContext + DispatcherServlet + Filter
   -> WebServer.start() -> HTTP request -> Spring MVC

Reactive: SpringApplication
   -> WebApplicationType.REACTIVE
   -> ReactiveWebServerApplicationContext
   -> ReactiveWebServerFactory (Netty/Tomcat/Jetty...)
   -> getWebServer(HttpHandler)
   -> WebFlux HttpHandler / WebHandler chain
   -> WebServer.start() -> HTTP request -> WebFlux
~~~

General startup sequence:

1. `SpringApplication` infers `WebApplicationType` from the classpath, unless the application explicitly configures or sets the type.
2. Boot creates the appropriate `ApplicationContext` type and activates auto-configuration for the active stack.
3. Auto-configuration creates **one matching factory** if no user-provided bean exists and the classpath conditions are satisfied.
4. Boot binds `server.*` properties, applies `WebServerFactoryCustomizer` beans, and then the context invokes `getWebServer(...)`.
5. The Servlet path registers Servlet components; the Reactive path attaches `HttpHandler`; the context starts `WebServer` during refresh.
6. Once the server is ready, Boot can publish `WebServerInitializedEvent`. When closing the context, Boot stops the server; in a normal application, there is no need to manage `start()/stop()` manually.

Implementation details vary by version and specific server, but the division of responsibility **context → factory → web server → HTTP handler** remains the key to reading logs and debugging.

## 4. Accurate Comparison Table

| Criterion | `ServletWebServerFactory` | `ReactiveWebServerFactory` |
|---|---|---|
| Primary stack | Servlet / Spring MVC | Reactive / Spring WebFlux |
| Context creating the server | `ServletWebServerApplicationContext` | `ReactiveWebServerApplicationContext` |
| Method | `getWebServer(ServletContextInitializer...)` | `getWebServer(HttpHandler)` |
| Object passed to the server | Initializers registering Servlets/Filters/Listeners | `HttpHandler` forwarding requests to WebFlux |
| Common servers in Boot 4.x | Tomcat, Jetty | Reactor Netty, Tomcat, Jetty |
| Illustrative concrete factories | `TomcatServletWebServerFactory`, `JettyServletWebServerFactory` | `NettyReactiveWebServerFactory`, `TomcatReactiveWebServerFactory`, `JettyReactiveWebServerFactory` |
| Common customization approach | `WebServerFactoryCustomizer<ConfigurableServletWebServerFactory>` | `WebServerFactoryCustomizer<ConfigurableReactiveWebServerFactory>` |

**Do not equate "reactive" with "Netty."** Netty is the default HTTP server of the WebFlux starter, not the definition of ReactiveWebServerFactory. WebFlux can also run on Tomcat or Jetty through adapters. Similarly, "Tomcat" does not by itself prove the application is using MVC: you must inspect the context type, stack, and factory.

### Which Type Does Boot Choose?

- With an MVC starter and corresponding libraries, Boot typically selects `SERVLET`.
- With a WebFlux starter and no basis for Boot to select MVC, Boot typically selects `REACTIVE`.
- When **both Spring MVC and WebFlux appear** on the classpath, Boot defaults to preferring **MVC / SERVLET**. Many MVC projects add WebFlux solely to use `WebClient`; that does not automatically switch the server to reactive.
- You can set `spring.main.web-application-type=reactive`, `servlet`, or `none` (or use `SpringApplication.setWebApplicationType(...)`), provided the corresponding libraries and beans are present. Forcing the web type does not automatically supply missing dependencies.

## 5. Typical Configuration: Prefer Properties First

Example `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8085
  address: 127.0.0.1
  shutdown: graceful
spring:
  main:
    web-application-type: servlet
~~~

`server.port` and `server.address` apply to the running server regardless of whether the underlying factory is servlet or reactive. `shutdown: graceful` requests graceful shutdown where supported by the version and server. The `spring.main.web-application-type` field is only needed when you truly want to override auto-detection.

Different port values carry different meanings:

- `server.port=8080`: default for standalone web applications if nothing is configured.
- `server.port=0`: asks the operating system to allocate an available port; retrieve the **actual port** from `WebServerInitializedEvent` or the test environment after the server initializes. Do not guess the port from the configured 0.
- `server.port=-1`: disables HTTP endpoints while still allowing the web application context to be created; distinct from `web-application-type=none`, which creates no application web server.
- If the port is already occupied by another process, the server may fail with a bind error / `PortInUseException`; that is not necessarily a factory error.

For server-specific options, use the namespaces supported by your version's documentation, such as `server.tomcat.*`, `server.jetty.*`, or `server.netty.*`. Do not assume every Tomcat property exists for Netty.

## 6. Hands-On A — Factory of a Servlet/MVC Application

Create a **separate project** using Spring Boot 4.1.x, Java 17+, and Gradle, adding the MVC dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
}
~~~

In a project with the Spring Boot Gradle plugin and dependency management generated by Spring Initializr, place the following file at `src/main/java/demo/servlet/ServletFactoryDemo.java`:

~~~java
package demo.servlet;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.boot.web.server.servlet.ConfigurableServletWebServerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ServletFactoryDemo {

    public static void main(String[] args) {
        SpringApplication.run(ServletFactoryDemo.class, args);
    }

    @GetMapping("/stack")
    public String stack() {
        return "SERVLET: Spring MVC";
    }

    @Bean
    WebServerFactoryCustomizer<ConfigurableServletWebServerFactory> servletPort() {
        return factory -> factory.setPort(9091);
    }
}
~~~

Run from the project root using `./gradlew bootRun` on macOS/Linux or `gradlew.bat bootRun` on Windows. Once the server has started, open another terminal:

~~~bash
curl -s http://localhost:9091/stack
~~~

The expected **HTTP response body** is:

~~~text
SERVLET: Spring MVC
~~~

Explanation:

- The MVC starter brings the Servlet stack and matching embedded server onto the classpath (Tomcat by default).
- Boot creates the corresponding `ServletWebServerFactory` and provides `ServletContextInitializer` instances, including the mechanism that registers `DispatcherServlet`.
- The `WebServerFactoryCustomizer<ConfigurableServletWebServerFactory>` bean receives the factory **before the server runs** and sets port 9091. It does not open sockets directly and does not create a second server.
- `@GetMapping` runs through Spring MVC; the response is the text string returned by the handler.

Here the port value is intentionally set in code to observe the customizer; in real applications, **`server.port` is usually simpler and easier to configure per environment**. If you both configure the port in a file and override it in a customizer, understand customizer ordering and pick one clear source of truth.

## 7. Hands-On B — Factory of a Reactive/WebFlux Application

Create **another project** also using Spring Boot 4.1.x, Java 17+, and Gradle, but using only the WebFlux starter:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Place the file `src/main/java/demo/reactive/ReactiveFactoryDemo.java`:

~~~java
package demo.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.boot.web.server.reactive.ConfigurableReactiveWebServerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@RestController
public class ReactiveFactoryDemo {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveFactoryDemo.class, args);
    }

    @GetMapping("/stack")
    public Mono<String> stack() {
        return Mono.just("REACTIVE: Spring WebFlux");
    }

    @Bean
    WebServerFactoryCustomizer<ConfigurableReactiveWebServerFactory> reactivePort() {
        return factory -> factory.setPort(9092);
    }
}
~~~

Run `./gradlew bootRun` or `gradlew.bat bootRun`, then send a request:

~~~bash
curl -s http://localhost:9092/stack
~~~

Expected response body:

~~~text
REACTIVE: Spring WebFlux
~~~

Explanation:

- The WebFlux starter uses Reactor Netty by default; Boot creates `NettyReactiveWebServerFactory`, an implementation of `ReactiveWebServerFactory`.
- WebFlux builds an `HttpHandler` and the factory attaches it to the reactive HTTP server. When a request arrives, WebFlux dispatches it to the handler returning `Mono<String>`.
- The customizer uses `ConfigurableReactiveWebServerFactory` to set port 9092 via the common API. Only Netty-specific customization requires `WebServerFactoryCustomizer<NettyReactiveWebServerFactory>` and the corresponding Netty APIs.
- `Mono` represents an asynchronous result at the handler layer; a method returning `Mono` **does not by itself prove** the application uses a reactive web server if the application is still configured for MVC.

**The two programs in sections 6–7 are two independent applications.** Do not put both starters and both `main` classes into the same project when the goal is simply to compare factories. In Boot 3.5, update the imports as shown in section 9 and use `spring-boot-starter-web` as the MVC starter.

## 8. When to Use a Customizer vs. Declaring Your Own Factory?

Safe, maintainable order of preference:

1. **`application.properties` or `application.yml`** for port, bind address, compression, TLS, and options already supported by Boot.
2. **`WebServerFactoryCustomizer<T>`** when programmatic configuration is needed or when a Tomcat/Jetty/Netty-specific feature is not exposed via properties. Choose `T` according to the stack or specific factory type.
3. **Declaring your own `ServletWebServerFactory` or `ReactiveWebServerFactory` bean** only when you need to completely replace server creation or choose a special implementation. This bean may cause default auto-configuration to back off; Boot's customizers can still be applied to your provided factory.

Illustrative configuration snippet only, **not a standalone runnable program**:

~~~java
// Bean placed in an @Configuration class of an MVC application:
@Bean
WebServerFactoryCustomizer<ConfigurableServletWebServerFactory> commonServerSettings() {
    return server -> server.setPort(9091);
}
~~~

**Lifecycle note:** customizers are typically invoked via a `BeanPostProcessor` relatively early before the context finishes initializing. Avoid depending on late-initializing beans or performing complex network I/O inside `customize(...)`. Never start the server manually inside a customizer; starting/stopping is Boot's responsibility.

If you attempt to declare multiple factories compatible with the same context, or a factory incompatible with the web application type, the application may fail when looking up the factory to initialize. Let auto-configuration do its work unless you have a real reason to replace it.

## 9. Important When Reading Docs or Code Across Boot 3.5 and 4.x

Interface names and concepts are similar, **but package names changed in Spring Boot 4**:

| Component | Spring Boot 3.5 | Spring Boot 4.x |
|---|---|---|
| `ServletWebServerFactory` | `org.springframework.boot.web.servlet.server.ServletWebServerFactory` | `org.springframework.boot.web.server.servlet.ServletWebServerFactory` |
| `ConfigurableServletWebServerFactory` | `org.springframework.boot.web.servlet.server.ConfigurableServletWebServerFactory` | `org.springframework.boot.web.server.servlet.ConfigurableServletWebServerFactory` |
| `ReactiveWebServerFactory` | `org.springframework.boot.web.reactive.server.ReactiveWebServerFactory` | `org.springframework.boot.web.server.reactive.ReactiveWebServerFactory` |
| `ConfigurableReactiveWebServerFactory` | `org.springframework.boot.web.reactive.server.ConfigurableReactiveWebServerFactory` | `org.springframework.boot.web.server.reactive.ConfigurableReactiveWebServerFactory` |
| `TomcatServletWebServerFactory` | `org.springframework.boot.web.embedded.tomcat.TomcatServletWebServerFactory` | `org.springframework.boot.tomcat.servlet.TomcatServletWebServerFactory` |
| `NettyReactiveWebServerFactory` | `org.springframework.boot.web.embedded.netty.NettyReactiveWebServerFactory` | `org.springframework.boot.reactor.netty.NettyReactiveWebServerFactory` |
| Common MVC starter | `spring-boot-starter-web` | `spring-boot-starter-webmvc` (old `-web` starter forwards/has been superseded) |

Boot 3.5 also includes an Undertow implementation; the list of supported servers may change across major versions. When copying specialized configuration code, check your project's **actual starter version and packages** before changing imports or swapping servers.

## 10. Observing and Diagnosing When the Server Fails to Start

| Symptom | What to Check | How to Fix |
|---|---|---|
| `Missing ServletWebServerFactory bean` or message about missing servlet web server factory | Application is in `SERVLET` mode without a suitable factory; starter/container excluded or auto-configuration disabled | Check dependency tree, MVC starter, auto-config conditions, and `spring.main.web-application-type` |
| `Missing ReactiveWebServerFactory bean` | `REACTIVE` selected without matching starter/server or auto-configuration disabled | Verify `spring-boot-starter-webflux` and reactive HTTP server; find why the factory bean was excluded |
| Using WebFlux but logs show `ServletWebServerApplicationContext`/Tomcat servlet | Both MVC and WebFlux starters are present; Boot prioritizes MVC | Review architecture goal; remove MVC starter if only WebFlux is needed, or explicitly choose type with matching dependencies |
| Unable to bind `8080`/`9091` | Port already in use or invalid bind address | Change `server.port`, free the port, or use port 0 in tests |
| Set `server.port=8085` but runs on a different port | Another customizer overrides it, or an environment variable / CLI arg has higher precedence | Check configuration sources and customizer ordering |
| `getWebServer()` returns a server but requests cannot reach it | Factory only provides the server; `start()` phase not reached yet or context startup failed | Check startup exceptions, lifecycle, "Started" log, and readiness |
| `ClassNotFoundException` for factory imports | Copied code from a different major version or missing server module/starter | Check the Boot 3.5/4.x package table, fix dependencies, and do not mix imports across versions |

**How to inspect the actual port once the server is ready:** check the logs or register a `WebServerInitializedEvent` listener and read `event.getWebServer().getPort()`. In web tests running on a random port, you can use `@LocalServerPort` per your version's test API. Avoid reading the actual port too early during bean creation.

**Recommended debugging order:** identify `WebApplicationType` → identify starters and servers on the classpath → verify factory bean/context matches the stack → inspect configuration/customizers → check bind errors and lifecycle. Read the stack trace from the **root cause** before replacing factory beans.

## 11. Self-Check Exercises

1. An application includes both the MVC and WebFlux starters just to use `WebClient`: which factory does Boot usually choose? **Answer:** the Servlet factory, because MVC takes precedence when both stacks are present.
2. Is Reactor Netty a mandatory requirement for `ReactiveWebServerFactory`? **No.** Reactive factories also have implementations for Tomcat/Jetty in supported versions.
3. Why does the servlet signature accept `ServletContextInitializer...`, while reactive accepts `HttpHandler`? **Because** one initializes the Servlet context and components registered via the Servlet API, while the other passes WebFlux's HTTP processing pipeline into the server.
4. You want to change 8080 to 9090 across environments without recompiling; what should you change? **`server.port`** in configuration or environment variables, rather than creating a custom factory.
5. When do you need to know about `WebServer.start()`? **When explaining the lifecycle and debugging** when the server becomes ready; typical Boot application code does not call it directly.

## 12. References

- Spring Boot — [Embedded Web Servers](https://docs.spring.io/spring-boot/how-to/webserver.html): choosing servers, ports, customizers, factory beans.
- Spring Boot — [Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): WebFlux, HTTP servers, and customizers.
- Boot 4.x Javadoc — [ServletWebServerFactory](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/web/server/servlet/ServletWebServerFactory.html), [ReactiveWebServerFactory](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/web/server/reactive/ReactiveWebServerFactory.html).
- Boot 3.5 Javadoc — [ServletWebServerApplicationContext](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/servlet/context/ServletWebServerApplicationContext.html), [ConfigurableReactiveWebServerFactory](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/reactive/server/ConfigurableReactiveWebServerFactory.html).