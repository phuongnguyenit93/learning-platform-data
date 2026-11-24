# Comparing ApplicationContext Types Corresponding to Spring Boot Application Types

## 1. From Application Type to ApplicationContext: Understanding the Relationship

When a program calls `SpringApplication.run(...)`, Spring Boot does not merely scan beans and instantiate objects from `@Configuration`, `@Component`, or `@Bean`. It must also decide **whether the application operates as a web server and, if so, which web model to use**. This decision directly determines **the concrete `ApplicationContext` type** created.

In the Spring Framework, `ApplicationContext` is the interface holding components that manage beans, configuration, events, and resources. `ConfigurableApplicationContext` adds operations related to context lifecycle and configuration. Spring Boot uses different `ApplicationContext` implementations to support standard, Servlet-based web, and reactive web applications.

Three conceptual layers should be separated:

1. **`WebApplicationType`**: the enum describing the Spring Boot application type, consisting of `NONE`, `SERVLET`, and `REACTIVE`.
2. **`ApplicationContext`**: the Spring object managing beans, dependency injection, configuration, events, and application lifecycle. This is the shared core across all three types.
3. **Web server**: the component that can listen for HTTP, such as Tomcat, Jetty, or Reactor Netty depending on the model and configured dependencies. The web server **is not synonymous** with `ApplicationContext`; certain contexts are responsible for creating and managing that server.

Most importantly: **`WebApplicationType` is the runtime model choice; the `ApplicationContext` class name is a concrete expression of that choice**. Do not infer the application type backward solely because the project has an HTTP library or a `Mono` return type.

## 2. Spring Boot 3.3 Default Mapping Table

In the default startup flow, with a `SpringApplication` whose `ApplicationContextFactory` has not been customized, we have:

| `WebApplicationType` | `ApplicationContext` Typically Created | Purpose |
| --- | --- | --- |
| `NONE` | `AnnotationConfigApplicationContext` | Application without an embedded web server; still has the Spring container and beans |
| `SERVLET` | `AnnotationConfigServletWebServerApplicationContext` | Servlet API-based HTTP application, typically with Spring MVC |
| `REACTIVE` | `AnnotationConfigReactiveWebServerApplicationContext` | Spring WebFlux/reactive web application, with a suitable web server |

Fully qualified class names in Spring Boot 3.3:

```text
NONE:
  org.springframework.context.annotation
      .AnnotationConfigApplicationContext

SERVLET:
  org.springframework.boot.web.servlet.context
      .AnnotationConfigServletWebServerApplicationContext

REACTIVE:
  org.springframework.boot.web.reactive.context
      .AnnotationConfigReactiveWebServerApplicationContext
```

Both Spring Boot web classes implement `WebServerApplicationContext`. They are responsible for coordinating with an appropriate `WebServerFactory` to create, start, and manage the lifecycle of the embedded HTTP server.

This is the **default mapping**, not a claim that every Spring application in the world has only these three context types. Spring Framework provides many other implementations; Spring Boot allows customizing context creation, and tests may use a context different from production applications.

Conceptual relationship diagram:

```text
                        SpringApplication
                              |
                   select WebApplicationType
                              |
         +--------------------+--------------------+
         |                    |                    |
        NONE                SERVLET              REACTIVE
         |                    |                    |
 AnnotationConfig-   AnnotationConfig-    AnnotationConfig-
 ApplicationContext  ServletWebServer-    ReactiveWebServer-
                     ApplicationContext   ApplicationContext
         |                    |                    |
    Manage beans         Manage beans         Manage beans
   and lifecycle         + Servlet web       + Reactive web
                            server               server
```

All of them still share the same foundations such as `ApplicationContext`, `BeanFactory`, constructor injection, `Environment`, and lifecycle events. The difference lies in **the accompanying web capabilities**.

## 3. NONE: AnnotationConfigApplicationContext

### Nature

`WebApplicationType.NONE` corresponds to a Spring application that does not start an embedded web server under Spring Boot's automatic mechanism. The default context class is `AnnotationConfigApplicationContext`, from the Spring Framework.

It can still:

- Load beans from `@Configuration`, `@ComponentScan`, `@Service`, and `@Bean`.
- Perform dependency injection, read `Environment` and externalized configuration.
- Run `CommandLineRunner` / `ApplicationRunner` after the context is initialized.
- Manage bean lifecycle and publish `ApplicationStartedEvent` / `ApplicationReadyEvent` via `SpringApplication`'s mechanism.
- Connect to databases, call APIs from clients, process files, or run jobs when the corresponding dependencies are configured.

It **does not open an HTTP port merely because a Spring container exists**. If you use `spring-boot-starter` without web components that alter application type inference, the default outcome is `NONE`. Common examples: batch CLIs, data-conversion tools, initialization tasks, background apps needing only Spring beans.

### Example of Explicitly Selecting NONE

```java
package demo.context;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContextDemoApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(ContextDemoApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.run(args);
    }
}
```

Equivalent configuration when setting the type via a property source:

```properties
spring.main.web-application-type=none
```

**This does not disable all of Spring.** It is a way to keep the container mechanism without running the application with a web context. For instance, a program using `spring-boot-starter-web` to obtain HTTP libraries can still be configured to run as `NONE`, though web server auto-configuration conditions will no longer apply.

**Does a non-web application exit immediately on its own?** Do not make an absolute claim. If only runners complete and no non-daemon thread keeps the JVM alive, the process may exit; if a scheduler, background thread, listener, or long-running work remains, the process may stay alive. Context existence and JVM lifecycle are two different matters. When you want to shut down an application in a controlled way, use the context stop APIs and return an appropriate exit code.

## 4. SERVLET: AnnotationConfigServletWebServerApplicationContext

### Nature

`WebApplicationType.SERVLET` represents a Servlet API-based application, the common model when using `spring-boot-starter-web` with Spring MVC.

`AnnotationConfigServletWebServerApplicationContext` extends `ServletWebServerApplicationContext`. Beyond general bean management, this web context integrates with:

- A `ServletWebServerFactory`, usually auto-configured by Spring Boot when a matching server implementation is present.
- An embedded Servlet container, such as Tomcat or Jetty depending on the dependencies.
- The `ServletContext`, servlet/filter/listener mechanisms, and Servlet web integrations.
- Spring MVC, when the project includes and uses `DispatcherServlet` to dispatch HTTP requests to controllers.
- Web server settings such as `server.port`, `server.address`, and related features.

With `spring-boot-starter-web` under Spring Boot 3.3's default setup, embedded Tomcat is the standard choice. However, **Servlet does not mandate Tomcat**: Jetty or another supported, properly configured compatible server can be used.

A typical Spring MVC request chain looks like:

```text
HTTP request
     |
Embedded Servlet container
     |
DispatcherServlet (Spring MVC)
     |
HandlerMapping / HandlerAdapter
     |
@Controller / @RestController
     |
HTTP response
```

`ApplicationContext` manages the beans involved in this diagram and the web server lifecycle; it does not handle each request itself in place of `DispatcherServlet`.

### Minimal Configuration Example

With Gradle dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

You can declare:

```properties
spring.application.name=context-servlet-demo
server.port=8080
```

A test controller:

```java
package demo.context;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public String hello() {
        return "hello-servlet";
    }
}
```

When running the `@SpringBootApplication` class in package `demo.context` or a parent package containing the controller, Spring scans this bean; with the web starter and no application type override, the default context belongs to the `SERVLET` branch. If the server starts successfully and the port is unchanged, calling `GET http://localhost:8080/hello` returns:

```text
hello-servlet
```

The example assumes the project already has the Spring Boot Gradle plugin and matching Java build configuration. If the port is occupied, set `server.port=0` to obtain a random port and read the actual port from the context when verifying.

## 5. REACTIVE: AnnotationConfigReactiveWebServerApplicationContext

### Nature

`WebApplicationType.REACTIVE` describes a web application built on reactive infrastructure, typically using `spring-boot-starter-webflux`.

`AnnotationConfigReactiveWebServerApplicationContext` extends `ReactiveWebServerApplicationContext`, providing the environment for WebFlux constructs. When sufficient dependencies are present, Spring Boot can auto-configure a matching `ReactiveWebServerFactory`.

The WebFlux model typically uses `DispatcherHandler` or functional routing (`RouterFunction` / `HandlerFunction`). Asynchronous data can flow through Reactor `Mono` and `Flux`:

```text
HTTP request
     |
Reactive web server / HTTP adapter
     |
WebFlux DispatcherHandler or functional RouterFunction
     |
Handler / @RestController
     |
Mono<T> / Flux<T> or supported return type
     |
HTTP response
```

Example controller:

```java
package demo.context;

import reactor.core.publisher.Mono;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReactiveHelloController {

    @GetMapping("/hello")
    public Mono<String> hello() {
        return Mono.just("hello-reactive");
    }
}
```

Gradle dependency for the WebFlux example **when not simultaneously adding the MVC starter**:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
```

With Spring Boot 3.3, the WebFlux starter typically brings in Reactor Netty as the default web server. Distinguish:

- `REACTIVE` does not mean "Reactor Netty is mandatory in every setup". WebFlux has other supported HTTP adapter and server runtime options.
- Using `Mono` or `Flux` in an arbitrary method **does not automatically change the ApplicationContext type**.
- Adding `WebClient` to call other services also **does not automatically turn a Spring MVC application into a reactive web server**.
- Blocking code running on the event loop without proper handling can degrade serving capacity; merely choosing `REACTIVE` does not guarantee every operation is non-blocking.

The design difference is **the HTTP processing model and web infrastructure**, not just a dependency name or one controller's return type.

## 6. How Does SpringApplication Infer WebApplicationType?

When creating `SpringApplication`, Spring Boot has a mechanism to **infer the web type from the classpath**. Practical rules for Spring Boot 3.3:

1. When suitable Spring MVC/Servlet infrastructure is present, Boot normally selects `SERVLET`.
2. When no prioritized MVC option is present but suitable WebFlux infrastructure is present, Boot selects `REACTIVE`.
3. When no suitable web infrastructure is present, Boot selects `NONE`.

The default context factory then creates the corresponding `ApplicationContext` implementation. This model is described in the `SpringApplication` documentation.

| Project's Main Dependencies | Usual Default Type | Corresponding Context |
| --- | --- | --- |
| `spring-boot-starter`, no added web infrastructure | `NONE` | `AnnotationConfigApplicationContext` |
| `spring-boot-starter-web` | `SERVLET` | `AnnotationConfigServletWebServerApplicationContext` |
| `spring-boot-starter-webflux`, no MVC added | `REACTIVE` | `AnnotationConfigReactiveWebServerApplicationContext` |
| Both `spring-boot-starter-web` and `spring-boot-starter-webflux` | `SERVLET` | `AnnotationConfigServletWebServerApplicationContext` |
| Only an HTTP client without required web server infrastructure | Possibly `NONE` | Depends on actual classpath |

The "only an HTTP client" row must be evaluated by **which classes actually appear on the classpath**, not solely by directly declared dependency names. Transitive dependencies can still affect web type inference.

One of the key traps:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
```

**The default outcome is Servlet/MVC.** This is a valid configuration when an MVC application wants to use `WebClient` to call external services. Having Spring WebFlux on the classpath **is not proof** that the program is running with `AnnotationConfigReactiveWebServerApplicationContext`.

If you genuinely want to run `REACTIVE` when both stacks are present, you can specify the application type explicitly, while also ensuring the corresponding reactive web server dependencies and auto-configurations work. Do not assume changing the enum alone automatically swaps every component in the application.

## 7. Forcing the Application Type via Configuration or Java

### Option A: application.properties

```properties
# Choose one of none, servlet, reactive
spring.main.web-application-type=reactive
```

This is a Spring Boot property; place it in a valid configuration source at startup, or pass it when running:

```bash
java -jar build/libs/app.jar --spring.main.web-application-type=none
```

`app.jar` is an example name; use the actual built JAR file.

### Option B: Java API

```java
package demo.context;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContextDemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ContextDemoApplication.class);

        application.setWebApplicationType(WebApplicationType.REACTIVE);
        application.run(args);
    }
}
```

Replace `REACTIVE` with `NONE` or `SERVLET` when that is the intent. Note that calling the setter alone **does not change existing dependencies**: if `SERVLET` is selected without a Servlet web server factory, or `REACTIVE` without a reactive server factory, startup can fail.

Note that `spring.main.web-application-type` from configuration sources is bound onto `SpringApplication` by Spring Boot. When set both in Java and via a property in `Environment`, configuration precedence order can affect the result. Keep one clear source of control and verify at runtime instead of silently assuming the setter always overrides all config.

### Option C: SpringApplicationBuilder

```java
new SpringApplicationBuilder(ContextDemoApplication.class)
        .web(WebApplicationType.NONE)
        .run(args);
```

The code above requires importing `org.springframework.boot.builder.SpringApplicationBuilder` and `org.springframework.boot.WebApplicationType`. This is an alternative startup style; do not use all three approaches in the same `main()` just to experiment.

**When should you force `NONE`?** For example, running a batch command or testing bean startup without opening a port, even though the application's classpath includes a web starter. **When should you force `REACTIVE`?** When you want to guarantee reactive mode in an environment with both MVC and WebFlux, and have already prepared the right web runtime and configuration.

## 8. Verifying the Running ApplicationContext Type in Java

Do not guess the context type solely from dependency names. You can inspect **the context object returned by `SpringApplication.run`** directly.

File `src/main/java/demo/context/ContextProbeApplication.java`:

```java
package demo.context;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.context.WebServerApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class ContextProbeApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(ContextProbeApplication.class, args);

        System.out.println("context=" + context.getClass().getSimpleName());

        if (context instanceof WebServerApplicationContext webContext) {
            System.out.println("webServer=true");
            System.out.println("port=" + webContext.getWebServer().getPort());
        } else {
            System.out.println("webServer=false");
        }
    }
}
```

Because the check runs **after `SpringApplication.run(...)` returns**, this is the right moment to observe a successful startup result. The code uses pattern matching for `instanceof`, compatible with Java 17 and newer.

Try with three **mutually exclusive** dependency sets in a project with the Spring Boot Gradle plugin configured:

**NONE option:**

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

Probe lines look like:

```text
context=AnnotationConfigApplicationContext
webServer=false
```

**SERVLET option:**

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

With the default port and no port-binding conflict:

```text
context=AnnotationConfigServletWebServerApplicationContext
webServer=true
port=8080
```

**REACTIVE option:**

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
```

With the default port:

```text
context=AnnotationConfigReactiveWebServerApplicationContext
webServer=true
port=8080
```

These are **the key lines printed by the probe code**, not the entire stdout. Spring Boot also prints the banner and logs; specific class names can differ if the developer replaces `ApplicationContextFactory` or applies a custom startup mechanism. The actual port may differ due to configuration or OS-assigned random ports.

A few notes for the hands-on exercise:

- Use only **one** web dependency set per default test pass. After changing dependencies, reload Gradle and rerun so the classpath is genuinely updated.
- If the package containing `@SpringBootApplication` does not cover other classes, adjust the package structure. The example above does not depend on any controller, so it can be run standalone to inspect the context.
- Do not instantiate `AnnotationConfigServletWebServerApplicationContext` manually or call `refresh()` yourself; `SpringApplication` executes the bootstrap flow.
- You can pass `--server.port=0` when running a web app, then inspect `getWebServer().getPort()` to avoid fixed port collisions. In that case, do not predict the port number before running.
- To test forcing NONE mode with the web starter, pass `--spring.main.web-application-type=none`. The result should be a non-web context and `webServer=false`, provided other beans do not cause startup failures.

The probe uses the `WebServerApplicationContext` interface (in package `org.springframework.boot.web.context`) to query server capability; this is more useful than comparing class names with `equals(...)`.

## 9. Comparing Capabilities That Truly Differ

| Criterion | `NONE` | `SERVLET` | `REACTIVE` |
| --- | --- | --- | --- |
| Has Spring IoC container | Yes | Yes | Yes |
| Auto-creates embedded HTTP server by default | No | Yes, when suitable factory/runtime is present | Yes, when suitable factory/runtime is present |
| Default context | `AnnotationConfigApplicationContext` | `AnnotationConfigServletWebServerApplicationContext` | `AnnotationConfigReactiveWebServerApplicationContext` |
| Primary HTTP handling API | No default web runtime | Servlet / Spring MVC | WebFlux reactive |
| Typical dispatcher | No HTTP dispatcher | `DispatcherServlet` | `DispatcherHandler` or functional routing |
| Depends on Servlet API for web dispatch model | No | Yes | Not mandatory under WebFlux model |
| HTTP `server.port` applies | Not under default embedded web server mechanism | Yes | Yes |
| Can use DB, scheduler, HTTP client calls | Yes if dependencies declared | Yes | Yes |
| Can use `ApplicationRunner` | Yes | Yes | Yes |
| Can run background jobs | Yes | Yes | Yes |

Two misconceptions to avoid:

1. `NONE` **does not mean** "no beans" or "no networking". It only means not using Spring Boot's automatic embedded web server mode. An HTTP client can still call external APIs.
2. `REACTIVE` **does not mean** "every piece of code is asynchronous" or "the application cannot run on a Servlet container". WebFlux defines a web programming model; the HTTP runtime choice and avoidance of blocking still depend on the concrete implementation.

## 10. Why Does Context Type Affect Auto-Configuration?

Spring Boot decides many beans based on conditions that may include:

- `@ConditionalOnClass`: a class or library set is present on the classpath.
- `@ConditionalOnMissingBean`: no bean of the corresponding type/name exists yet.
- `@ConditionalOnWebApplication`: running inside a matching web context.
- `@ConditionalOnNotWebApplication`: running outside a web context.

For instance:

```java
package demo.context;

import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class WebOnlyConfiguration {

    @Bean
    @ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.SERVLET)
    String servletOnlyMarker() {
        return "servlet";
    }
}
```

The code above is a conditional illustration: the bean named `servletOnlyMarker` is only registered when the Servlet web condition is satisfied. This is not an endpoint. Similarly, a configuration can use:

```java
@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.REACTIVE)
```

to apply only in a reactive environment. These conditions are evaluated while building the context. The outcome can change if `WebApplicationType` changes even when source classes and many dependencies remain unchanged.

Therefore, "just changing `spring.main.web-application-type`" can change **which auto-configured beans get created**. Do not view it merely as an on/off toggle for the web port.

**The difference between classpath and context:** the classpath provides evidence that a technology **can be used**; the web context type and configuration conditions decide whether that technology **is actually initialized for the running application**.

## 11. How Does WebServerApplicationContext Differ from WebApplicationType?

`WebApplicationType` is a Spring Boot enum used during bootstrap decision-making. Once created, the context is a Java object with concrete types and interfaces.

For example:

```java
if (context instanceof WebServerApplicationContext webContext) {
    int actualPort = webContext.getWebServer().getPort();
    System.out.println(actualPort);
}
```

This statement queries the context's capability **at runtime**, not the enum previously passed to `SpringApplication`. Under default contexts, both Servlet and reactive web contexts implement `WebServerApplicationContext`. Thus, checking `instanceof WebServerApplicationContext` alone **cannot distinguish** between the two web models.

To distinguish accurately, you can check specialized interfaces or context types, for example:

```java
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.boot.web.reactive.context.ReactiveWebServerApplicationContext;

if (context instanceof ServletWebServerApplicationContext) {
    System.out.println("kind=SERVLET");
} else if (context instanceof ReactiveWebServerApplicationContext) {
    System.out.println("kind=REACTIVE");
} else {
    System.out.println("kind=NON_WEB_OR_CUSTOM");
}
```

This is a **Java snippet inserted into a method that already has a `context` variable of type `ApplicationContext`/`ConfigurableApplicationContext`**. It is not a standalone compilable program. Both checked classes belong to Spring Boot 3.3; when bootstrapping with a custom factory or running specialized test scenarios, the default classification above is not an absolute contract.

When you only need beans, depend on the general `ApplicationContext` interface or direct constructor injection rather than writing multiple class-name branches. Only use specific web classes when specialized web capabilities are genuinely needed.

## 12. Can You Choose a Custom ApplicationContextFactory?

Yes. `SpringApplication` provides the `setApplicationContextFactory(...)` extension point to customize the context creation strategy. In Spring Boot 3.3, the default factory selects an appropriate context based on `WebApplicationType`.

The purpose of this factory is to create an **unrefreshed context**, after which `SpringApplication` proceeds with configuring, loading beans, and completing bootstrap. It differs from manually creating an `ApplicationContext` and bypassing Boot's startup flow.

API illustration only, when you are **certain** the application is non-web:

```java
import org.springframework.boot.ApplicationContextFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

// Set before application.run(args):
application.setApplicationContextFactory(
        ApplicationContextFactory.ofContextClass(
                AnnotationConfigApplicationContext.class));
```

This snippet requires an already-created `application` variable of type `SpringApplication`. Do not use a fixed factory returning a non-web context in an application requiring `SERVLET` or `REACTIVE`: auto-configurations and web server factories may no longer be compatible. When the goal is simply enabling/disabling the web server, `setWebApplicationType(...)` or `spring.main.web-application-type` is the better configuration point.

An easy point of confusion: **one `ApplicationContext` type does not necessarily mean a single instance in every scenario**. There can be parent-child contexts built by the developer, contexts for test slices, or customized contexts. The default table in section 2 describes standard Spring Boot startup, not every custom container topology.

## 13. Differences During Testing

In tests, the context can differ from running an executable JAR because `@SpringBootTest`, `@WebMvcTest`, `@WebFluxTest`, test slices, mock web environments, and test frameworks can change how the context is created/loaded.

For example, if a test only needs to check beans or runners without running a real server:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class SimpleContextTest {
    // Bean tests that do not need a real HTTP port.
}
```

This illustrates the `org.springframework.boot.test.context.SpringBootTest` annotation; it requires the `spring-boot-starter-test` dependency and the corresponding test framework. If full Spring Boot integration is unneeded, `ApplicationContextRunner` or plain unit tests may be a better fit.

With `@SpringBootTest(webEnvironment = RANDOM_PORT)`, Spring Boot can create a server listening on an OS-chosen port; that differs from the simulated context in `MOCK`. Therefore:

- Do not rely on the context class name in one test to conclude production definitely runs the same type.
- Do not use `@WebMvcTest` and conclude the whole application has only Spring MVC; that is a test slice.
- When both MVC and WebFlux are present in tests and the target is WebFlux, you may need `spring.main.web-application-type=reactive` and matching dependencies.
- If a test needs to ensure a real web server exists, verify `webEnvironment` and the actual port. Seeing `@SpringBootTest` alone is not enough to conclude a listening server exists.

These differences are why you should verify in both **an actual run** and **purpose-built test classes**.

## 14. Common Errors and How to Diagnose

| Symptom | Cause Worth Checking | Action |
| --- | --- | --- |
| Added `spring-boot-starter-webflux` yet still see a Servlet context | Spring MVC is also on the classpath and takes precedence by default | Inspect dependency tree; clarify whether the goal is MVC + WebClient or a WebFlux server |
| Only have `spring-boot-starter`, want to open an HTTP endpoint | App is `NONE` and lacks a web stack | Add the appropriate web starter and ensure a web server factory works |
| Selected `SERVLET`, yet startup fails with missing web server factory | Missing/excluded embedded Servlet server runtime or misconfiguration | Check starter, dependency exclusions, and `ServletWebServerFactory` bean |
| Selected `REACTIVE`, yet startup fails with missing reactive server factory | Missing suitable reactive HTTP runtime or incompatible config | Check `spring-boot-starter-webflux`, HTTP runtime, and exclusions |
| Forced `NONE`, then received 404 on the old port | No web server is auto-created by Boot anymore under default behavior | Use `SERVLET` or `REACTIVE` when HTTP serving is needed |
| `server.port=8080`, yet no port opens | Context is `NONE`, startup failed, or server was not created | Print the context type and inspect startup logs |
| `Mono<String>` in controller, yet context is still Servlet | Both MVC and WebFlux are present; return type does not decide context | Check startup mode, dispatcher, and dependencies |
| Unit test prints a different context class name from production | Test uses its own context, slice, or mock environment | Compare using the same launch method and same webEnvironment |
| Called `setWebApplicationType(NONE)` yet still created a web context | Another startup property rebound it, or a custom factory exists | Check `spring.main.web-application-type`, config sources, and factory |
| Startup logs web server yet still fails | Web server starts during refresh, while later steps can fail | Check the full exception and readiness events, not just the context type |

Sequential diagnostic steps:

1. Confirm the **actual classpath** via the dependency tree, as transitive dependencies can pull in MVC/Servlet or WebFlux.
2. Locate every source setting `spring.main.web-application-type`: Java, `application.properties` / YAML, environment variables, and command-line arguments.
3. Print the context type and check `instanceof WebServerApplicationContext` using the code in section 8.
4. When a web context exists, inspect the web server factory, actual bound port, listening address, and error logs.
5. Inspect auto-configured beans conditioned on Servlet/Reactive; if needed, enable the condition evaluation report with `--debug` and read which conditions matched or did not match.
6. For test-specific issues, check the test annotation and selected web environment.

## 15. Hands-On Comparison of the Three Types with the Same Codebase

Keep the `ContextProbeApplication` class from section 8 and follow these steps:

1. **NONE:** keep only `spring-boot-starter`, run and record the context class name, `webServer=false`, and process exit status after runners finish.
2. **SERVLET:** replace the dependency with `spring-boot-starter-web`, run and record the context name and actual port. Add a `/hello` controller if you want to test requests.
3. **REACTIVE:** replace the dependency with `spring-boot-starter-webflux` without leaving MVC on the classpath, run and record the context name and actual port. You can try a controller returning `Mono<String>`.
4. **Both starters present:** enable both web and webflux again, predict which context will be created **before running**, then verify via logs and context class name.
5. **Forcing the type:** in the setup with the web starter, run with `--spring.main.web-application-type=none`. Check why no HTTP port opens even though web libraries remain present.
6. **Counterexample experiment:** force `REACTIVE` without preparing the proper web runtime to see the difference between "choosing the enum" and "meeting server initialization conditions". Run only in a test environment.

To verify the HTTP endpoint output, use `curl` while the server is running:

```bash
curl http://localhost:8080/hello
```

This command only fits when the server is listening on port 8080 and the `/hello` controller from the exercise is declared. If using port `0`, read the actual port from logs or context before calling.

Explain the outcome via these questions: **Where was the application type inferred from? Which context did Spring Boot choose? Is there a web server? Which framework dispatches requests?** Answering all four means you understand the connection between `WebApplicationType` and `ApplicationContext`.

## 16. Takeaways for Real Projects

- `ApplicationContext` is the shared IoC foundation; a web app is also a Spring app, just with added web infrastructure.
- Spring Boot 3.3's default mapping is `NONE → AnnotationConfigApplicationContext`, `SERVLET → AnnotationConfigServletWebServerApplicationContext`, `REACTIVE → AnnotationConfigReactiveWebServerApplicationContext`.
- Default selection is governed by the classpath. When both Spring MVC and WebFlux are present, **Servlet/MVC takes precedence by default**.
- Use `spring.main.web-application-type` or `setWebApplicationType(...)` when you need to select a mode deliberately, but ensure compatible dependencies and web server factories.
- Use `SpringApplication.run(...)` and context interfaces to observe runtime; do not infer solely from starter names or controller return types.
- `NONE` still has Spring beans and can perform background work; `SERVLET` and `REACTIVE` differ in HTTP infrastructure and web configuration conditions.
- Custom `ApplicationContextFactory` implementations and test environments can change context class names; treat the mapping table as **the standard behavior of the default flow**, not an immutable law for every Spring application.

### References

- [Spring Boot 3.3 — SpringApplication API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html): `getWebApplicationType`, `setWebApplicationType`, `setApplicationContextFactory`, and context creation rules.
- [Spring Boot — SpringApplication / Web Environment](https://docs.spring.io/spring-boot/reference/features/spring-application.html): how the web environment is inferred when MVC/WebFlux is present.
- [Spring Boot 3.3 — Servlet context](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/servlet/context/AnnotationConfigServletWebServerApplicationContext.html).
- [Spring Boot 3.3 — Reactive context](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/reactive/context/AnnotationConfigReactiveWebServerApplicationContext.html).
