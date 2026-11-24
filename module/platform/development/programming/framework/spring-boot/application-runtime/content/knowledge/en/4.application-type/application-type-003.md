# When Spring MVC and Spring WebFlux Are Both Present in Spring Boot

## 1. The Problem to Understand

Spring Boot can use either **Spring Web MVC** or **Spring WebFlux** to handle HTTP requests. Both frameworks belong to the Spring Framework, yet they operate under different models:

- **Spring MVC** is based on the **Servlet API**, using **DispatcherServlet**, servlet filters, and a servlet container such as Tomcat. The common style is synchronous controllers, with support for asynchronous processing when needed.
- **Spring WebFlux** is a reactive web framework, using **DispatcherHandler**, Reactive Streams, and Reactor's **Mono**/**Flux** types. It is designed to support non-blocking processing along with backpressure mechanisms in a reactive pipeline.
- **WebClient** is an HTTP client with a reactive API located in the Spring WebFlux module. An MVC application can still use WebClient to call other APIs.

**Core takeaway:** when Spring MVC and Spring WebFlux **are both present on the classpath**, Spring Boot **prefers starting the application in SERVLET/Spring MVC mode by default**. The presence of the WebFlux library does not mean Boot will automatically switch the HTTP server to reactive or open both frameworks simultaneously to handle the same request.

This is intentional behavior in Spring Boot: many MVC systems need to use WebClient while keeping MVC's existing model for receiving and handling HTTP requests.

## 2. How Is WebApplicationType Inferred?

**SpringApplication** detects web libraries on the classpath to determine the application type when none is explicitly specified.

| Components Present | Type Boot Selects by Default | Server-Side Framework |
| --- | --- | --- |
| Spring MVC, no WebFlux | **SERVLET** | Spring MVC |
| WebFlux, no Spring MVC | **REACTIVE** | Spring WebFlux |
| **Both Spring MVC and WebFlux present** | **SERVLET** | **Spring MVC wins** |
| Neither present | **NONE** | Non-web |
| Both present and REACTIVE explicitly forced | **REACTIVE** | WebFlux if a compatible server runtime is present |

Default detection diagram:

~~~text
                   SpringApplication
                           |
                   Classpath detection
                           |
              +------------+------------+
              | Is Spring MVC present?  |
              +------------+------------+
                | Yes            | No
                v                v
            SERVLET      Is Spring WebFlux present?
          Spring MVC         | Yes       | No
                             v           v
                          REACTIVE      NONE
                          WebFlux      Non-web
~~~

In SERVLET mode, Boot typically creates an **AnnotationConfigServletWebServerApplicationContext** and configures Spring MVC. In REACTIVE mode, Boot typically creates an **AnnotationConfigReactiveWebServerApplicationContext** and configures WebFlux. These ApplicationContexts represent two distinct runtime models.

Note: the table describes **default** behavior. You can actively override it using **SpringApplication.setWebApplicationType(WebApplicationType.REACTIVE)**, **SpringApplicationBuilder.web(WebApplicationType.REACTIVE)**, or the property **spring.main.web-application-type=reactive**. Adequate dependencies and matching configuration must be present for startup to succeed.

## 3. When Both Are Present, Server and HTTP Client Handle Separate Jobs

A common application structure looks like this:

~~~text
HTTP client calls the application's endpoint
                  |
                  v
    Embedded servlet server (Tomcat)
                  |
                  v
      Spring MVC DispatcherServlet
                  |
                  v
             Controller
                  |
                  v
               Service
                  |
               WebClient
                  |
                  v
         External HTTP API
~~~

In this model:

1. Requests **entering the server** are received and dispatched by Spring MVC.
2. When business logic needs to call another system, the service can use **WebClient** as an outbound HTTP client.
3. Boot still chooses **SERVLET**; using WebClient does not turn the server into WebFlux.
4. WebClient can use a non-blocking API, yet whether the application thread is blocked depends on how it is invoked, such as whether **block()** is called.
5. MVC's servlet filters, MVC interceptors, exception handling, and security configuration continue to apply to the MVC server.

Do not confuse **having the WebFlux dependency** with **serving requests via WebFlux**. These are two separate properties of the application.

## 4. Complete Example: Both Starters Coexist, MVC Takes Precedence

### 4.1. Project Setup

Use Spring Initializr to create a Maven project, Java 17 or newer, Spring Boot **3.3.x**, package **com.example.demo**. Select both dependencies:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
</dependencies>
~~~

This is the **dependencies section** inside a complete POM generated by Initializr; it is not a standalone pom.xml file. The Boot parent/BOM manages compatible library versions. Starter Web typically provides Spring MVC and Tomcat; Starter WebFlux provides reactive web classes, WebClient, and the corresponding Reactor infrastructure.

### 4.2. Runnable Java Program

Create **src/main/java/com/example/demo/MixedWebApplication.java**:

~~~java
package com.example.demo;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.context.ApplicationContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;

@SpringBootApplication
@RestController
public class MixedWebApplication {

    private final ApplicationContext context;
    private final WebClient.Builder webClientBuilder;

    public MixedWebApplication(
            ApplicationContext context,
            WebClient.Builder webClientBuilder) {
        this.context = context;
        this.webClientBuilder = webClientBuilder;
    }

    public static void main(String[] args) {
        SpringApplication.run(MixedWebApplication.class, args);
    }

    @GetMapping("/stack")
    public Map<String, Boolean> stack() {
        return Map.of(
                "servletContext",
                context instanceof ServletWebServerApplicationContext,
                "webClientAvailable",
                webClientBuilder != null);
    }
}
~~~

**Analysis:**

- **@SpringBootApplication** declares the application's configuration source.
- **@RestController** and **@GetMapping** declare the endpoint. Both annotations are used in both MVC and WebFlux; looking only at the annotations is not enough to identify the web stack.
- **ApplicationContext** is the running context, injected to confirm the application type.
- **ServletWebServerApplicationContext** is the servlet context type in Spring Boot 3.x. Since both starters are present, Boot prefers SERVLET, so the **instanceof** check evaluates to **true**.
- **WebClient.Builder** is provided by Boot via auto-configuration when the corresponding conditions are met. Successful injection demonstrates that an MVC server can still use WebClient.
- The endpoint makes no external network calls; it simply inspects two runtime characteristics so the exercise is easy to reproduce.

### 4.3. Run and Observe

In the project root directory:

~~~bash
# Linux/macOS
./mvnw spring-boot:run

# Windows:
# .\mvnw.cmd spring-boot:run
~~~

Open another terminal:

~~~bash
curl http://localhost:8080/stack
~~~

Expected response body:

~~~json
{
  "servletContext": true,
  "webClientAvailable": true
}
~~~

Key order, whitespace, and actual logging may differ. The two boolean values in the response are what to observe. Startup logs typically show Tomcat starting under starter-web's default configuration.

**Interpreting the result:** true for **servletContext** proves this is a servlet web application; true for **webClientAvailable** shows the reactive client component is also available. The two results do not contradict each other at all.

If the default port is occupied, configure **server.port** to another port and adjust the URL when calling curl. Stop the application with **Ctrl+C** in the terminal.

## 5. When You Want WebFlux as the Server Despite MVC Still Being on the Classpath

### 5.1. Selecting REACTIVE in Java Code

In the example application from section 4, you can **replace the main method** with the following snippet:

~~~java
public static void main(String[] args) {
    new org.springframework.boot.builder.SpringApplicationBuilder(
            MixedWebApplication.class)
            .web(org.springframework.boot.WebApplicationType.REACTIVE)
            .run(args);
}
~~~

This snippet illustrates replacing **a single method**, not a standalone program. **SpringApplicationBuilder.web(...)** instructs Boot to select a reactive web application context. When existing dependencies are compatible, Boot configures a WebFlux server runtime; with the default starter-webflux, the common reactive server is Reactor Netty.

If you keep the same class from the example above, **@GetMapping** remains a valid HTTP handler annotation in WebFlux. Once the application starts in REACTIVE mode, **servletContext** is expected to switch to **false**, because the ApplicationContext is no longer a ServletWebServerApplicationContext.

Selecting REACTIVE does not automatically convert servlet filters, MVC interceptors, MVC-specific argument resolvers, or servlet security configurations into reactive equivalents. Every Servlet-coupled component must be reviewed when switching.

### 5.2. Selecting via Runtime Configuration

Instead of modifying main, set:

~~~properties
spring.main.web-application-type=reactive
~~~

in **src/main/resources/application.properties** or pass the argument when running the executable JAR:

~~~bash
# After running ./mvnw package
java -jar target/actual-file-name.jar --spring.main.web-application-type=reactive
~~~

Replace **actual-file-name.jar** with the actual built JAR filename. You can specify **servlet**, **reactive**, or **none** according to your needs and available dependencies.

If the project's goal is a pure WebFlux server, the more maintainable approach is usually to declare only **spring-boot-starter-webflux** and omit **spring-boot-starter-web** if unneeded. Boot will then infer REACTIVE automatically.

## 6. How WebFlux and Spring MVC Differ in the Server Pipeline

| Criterion | MVC / SERVLET | WebFlux / REACTIVE |
| --- | --- | --- |
| HTTP dispatcher | **DispatcherServlet** | **DispatcherHandler** |
| Programming foundation | Servlet API | Reactive Streams, non-blocking API |
| Controller | @Controller / @RestController | @Controller / @RestController |
| Functional routes | **org.springframework.web.servlet.function** | **org.springframework.web.reactive.function.server** |
| Web configuration | **WebMvcConfigurer** | **WebFluxConfigurer** |
| Interception/filtering | Servlet Filter, HandlerInterceptor | WebFilter and reactive filter chain |
| Server security | SecurityFilterChain (servlet) | SecurityWebFilterChain (reactive) |
| Common servers | Tomcat, Jetty | Reactor Netty and other compatible adapters |
| WebClient HTTP client | Can be used | Can be used |
| Target use case | Traditional servlet services, blocking code managed via threads | Reactive-designed pipelines, avoiding blocking the event loop |

**WebFlux does not exclusively mean Netty**. WebFlux can run on several other runtimes, including Servlet-compatible adapters. You cannot determine the framework solely from the server name or port; inspect the ApplicationContext/auto-configuration type and the actual dispatch path.

### Does an MVC Controller Returning Mono Make the Server WebFlux?

**No.** Spring MVC can adapt certain reactive return types into its async Servlet mechanism. For instance, a method inside an MVC **@RestController** can look like:

~~~java
@GetMapping("/hello")
public reactor.core.publisher.Mono<String> hello() {
    return reactor.core.publisher.Mono.just("Hello");
}
~~~

This is an **illustrative method** that needs to be placed inside an appropriate controller. Returning Mono does not make DispatcherServlet disappear. It simply shows that MVC accepts a reactive type in the signature.

Similarly, when a WebFlux controller uses **@GetMapping**, that annotation does not mean the server is MVC. The annotation name is identical, while the dispatcher/context depends on the selected runtime type.

### Does WebClient Guarantee End-to-End Non-Blocking Behavior?

**No.** WebClient builds a reactive pipeline, yet code can turn the operation into a blocking one by calling **block()**:

~~~java
String body = webClient.get()
        .uri("https://example.com/data")
        .retrieve()
        .bodyToMono(String.class)
        .block();
~~~

The snippet above illustrates client syntax (the **webClient** variable and endpoint are hypothetical), not a standalone runnable program. **block()** blocks the calling thread until data or an error arrives. In MVC, it can tie up a servlet request thread. In WebFlux, calling it directly on an event-loop thread can cause errors or degrade concurrency.

A WebFlux server performing blocking JDBC, blocking file I/O, or heavy CPU work on the event loop still needs scheduler management and resource limits. **Choosing REACTIVE does not automatically make every dependency non-blocking**.

## 7. Configurations Easily Confused When Both Libraries Are Present

### 7.1. Do Not Use @EnableWebFlux as a Switch Replacing the Web Type

**@EnableWebFlux** is a framework configuration annotation. It is not the right way to choose the ApplicationContext type during Spring Boot bootstrap. It can also alter how Boot auto-configures WebFlux because framework components are then provided directly by the application.

Similarly, **@EnableWebMvc** affects MVC configuration and can alter default auto-configuration. Prefer letting Boot infer the web type, or explicitly setting **spring.main.web-application-type** / **SpringApplicationBuilder.web(...)** when another type is deliberately needed.

### 7.2. Do Not Confuse the Two RouterFunction Types

Spring MVC functional endpoints use the package **org.springframework.web.servlet.function**. WebFlux functional endpoints use the package **org.springframework.web.reactive.function.server**. Both share names like **RouterFunction** and **ServerResponse**, yet the types belong to two different packages and two different HTTP pipelines.

Therefore, before copying a **RouterFunction** example from documentation, check the imports and which server stack the application actually runs.

### 7.3. Do Not Blindly Copy Security, Filters, and Config Between the Two Stacks

In MVC, **jakarta.servlet.Filter**, **HandlerInterceptor**, and **SecurityFilterChain** serve the servlet model. In WebFlux, **WebFilter** and **SecurityWebFilterChain** belong to the reactive stack. The two security models use distinct runtime objects.

Having both dependencies present does not turn a servlet filter into a reactive WebFilter or vice versa. If you change the web type, test authentication, authorization, error handling, CORS, validation, and tracing against the exact pipeline in use.

## 8. How to Diagnose When Runtime Differs from Expectations

**Step 1: inspect the dependency tree.**

~~~bash
./mvnw dependency:tree
~~~

Check **spring-webmvc**, **spring-webflux**, and which starter brings them in (including transitive dependencies). Do not look only at direct dependencies in the POM.

**Step 2: check ApplicationContext.** In Boot 3.x, **ServletWebServerApplicationContext** indicates SERVLET. Reactive contexts typically belong to the **ReactiveWebServerApplicationContext** family. This is more reliable evidence than spotting a WebClient or Flux class in code.

**Step 3: check startup logs** for the web server, port, and auto-configuration errors. With a typical starter-web, Tomcat logs align with default MVC; however, because some servers can run with multiple adapters, combine this with step 2.

**Step 4: inspect the Condition Evaluation Report** using **--debug** mode or the Spring Boot Actuator **conditions** endpoint if the project has the dependency and appropriate security configured. Focus on auto-configurations for MVC, WebFlux, and web application type.

**Step 5: check the test context.** If the application has both starters, **@SpringBootTest** can also pick MVC from the classpath. When a test intentionally targets the reactive runtime, you can specify:

~~~java
@SpringBootTest(
        properties = "spring.main.web-application-type=reactive")
class ReactiveApplicationTests {
    // Add test methods and the corresponding imports/dependencies.
}
~~~

This is an illustrative skeleton, not a standalone runnable test. It requires importing **org.springframework.boot.test.context.SpringBootTest**, the **spring-boot-starter-test** dependency, test methods, and suitable environment conditions. Do not set REACTIVE in tests if the production application is still intended to be MVC, unless specifically testing that configuration.

## 9. When to Keep MVC + WebClient vs. Choose WebFlux?

### Keep MVC and Use WebClient When

- The application already relies on MVC, servlet filters, JDBC/JPA, or blocking libraries.
- The primary need is **making outbound HTTP calls** with a reactive client API.
- The team has no requirement to migrate the entire request pipeline to reactive.
- There is a plan to manage timeouts, connections, concurrency, and **block()** usage appropriately.

For purely synchronous HTTP calls, you can also evaluate Spring Framework's modern **RestClient** if it fits the existing stack.

### Choose WebFlux as the Server When

- The application is deliberately designed around a reactive pipeline.
- Critical dependencies offer non-blocking APIs or have dedicated handling for blocking work.
- The team needs async/reactive mechanisms to handle many I/O-bound requests appropriately.
- Backpressure, cancellation, event-loop blocking, security, and observability have been properly tested.

Do not treat WebFlux as a default way to get higher performance in every scenario. The workload and dependencies determine actual efficiency.

### If MVC Appears Unexpectedly

First identify which dependency brings **spring-webmvc** onto the classpath. If MVC is unneeded, you can exclude or remove that dependency; if both are needed, set **REACTIVE** explicitly and test the entire configuration. Both options must be grounded in actual requirements and system state.

## 10. Common Mistakes

1. **"Adding spring-boot-starter-webflux makes Boot prefer WebFlux."** False when MVC is also present: MVC wins by default.
2. **"Two starters start two HTTP servers."** Not standard auto-configuration behavior; Boot chooses one web application type.
3. **"WebClient only works in a WebFlux server."** False: MVC validly uses WebClient.
4. **"A controller returning Mono means the server is reactive."** Not conclusive; MVC can also handle reactive return types.
5. **"WebFlux must always run on Netty."** False: WebFlux has multiple server adapters.
6. **"Switching to REACTIVE automatically adapts all servlet-specific components."** False: filters, interceptors, security, and blocking code must be re-evaluated.
7. **"@EnableWebFlux is a replacement for setWebApplicationType."** Wrong about the responsibilities of the two mechanisms.
8. **"Having both MVC and WebFlux is always a bad configuration."** Incorrect: an MVC server using WebClient is an intentionally supported Spring Boot pattern.

## 11. Exercises and Suggested Answers

**Exercise 1.** An application has starter-web and starter-webflux, and main simply calls **SpringApplication.run**. Which type does Boot choose? Why?

**Exercise 2.** A Spring MVC controller injects **WebClient.Builder**. Do incoming requests go through DispatcherServlet or DispatcherHandler by default?

**Exercise 3.** A team wants the web server to actually run WebFlux, yet the dependency tree includes Spring MVC. Name two approaches and what needs to be verified.

**Exercise 4.** Is returning **Mono<String>** from a controller proof that the entire stack is non-blocking?

**Exercise 5.** After changing SERVLET to REACTIVE, why must the application's filter/security configuration be re-verified?

**Answers:** (1) SERVLET/Spring MVC because Boot prefers MVC when both are present; (2) DispatcherServlet by default; (3) remove the unneeded MVC dependency or force REACTIVE when a compatible server runtime is present, while testing all components; (4) no, MVC supports certain reactive return types and code may still block; (5) the two frameworks have different HTTP filter/security pipelines.

## 12. Takeaways and Official Documentation

**By default MVC takes precedence if both MVC and WebFlux are present. WebClient can be used inside an MVC application. Choosing a WebFlux server requires configuring REACTIVE or a classpath without MVC, along with compatibility of runtime components.**

Documentation to cross-check with your project's Spring Boot version:

- Spring Boot Reference — Reactive Web Applications (explains MVC precedence when both starters are present): https://docs.spring.io/spring-boot/reference/web/reactive.html
- Spring Boot Reference — SpringApplication, Web Environment, and WebApplicationType: https://docs.spring.io/spring-boot/reference/features/spring-application.html
- Spring Framework Reference — Spring Web MVC: https://docs.spring.io/spring-framework/reference/web/webmvc.html
- Spring Framework Reference — Spring WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux.html

Across different Spring Boot major versions, some packages, starters, auto-configurations, and default dependencies may change. The Java examples above target Spring Boot 3.3.x and Java 17+; consult the exact version's Javadoc when moving to another project.