# Behavior When Both Spring MVC and WebFlux Are on the Classpath

## 1. Key takeaway to remember

In a standard Spring Boot application, if both spring-boot-starter-web and spring-boot-starter-webflux are on the runtime classpath, **Spring Boot prioritizes Spring MVC and starts a Servlet-based web application by default**. Having WebFlux libraries present does not automatically switch the application to a reactive web server, nor does it launch two independent HTTP request processors side by side by default.

This rule is intentional: many Spring MVC applications add WebFlux to use the WebClient HTTP client and Reactor while keeping their existing controllers and Servlet runtime.

You can explicitly choose WebFlux as the server stack by configuring spring.main.web-application-type=reactive or via SpringApplication.setWebApplicationType(WebApplicationType.REACTIVE), provided that the dependencies and configuration for a reactive server are compatible.

This lesson focuses on **the web stack selection mechanism when both frameworks are on the classpath**, which components actually run at runtime, how to share libraries, and how to verify the outcome. Examples apply to Spring Boot 3.3.x and Java 17+.

## 2. Getting the concepts right

### 2.1 Classpath does not equal active runtime

The runtime classpath is the set of libraries that the JVM can load when the application runs. Both direct dependencies and transitive dependencies can contribute classes to the classpath.

Adding spring-boot-starter-web typically brings Spring MVC, the Servlet API, and embedded Tomcat. Adding spring-boot-starter-webflux typically brings Spring WebFlux, Reactor, and Reactor Netty.

The mere presence of a class such as DispatcherServlet or DispatcherHandler in a library only proves that the class **is available**. It does not prove that Spring Boot created the corresponding web application context, registered its request dispatcher, or selected that framework's HTTP server.

Distinguish three questions:

1. **What is on the classpath?** Which libraries are available to use?
2. **Which application type does Spring Boot choose?** SERVLET, REACTIVE, or NONE?
3. **What does the runtime actually initialize?** Which context, auto-configurations, web server, dispatcher, security chain, and endpoints are serving requests?

Accurate conclusions must be based on the second and third questions. You cannot simply look at starter names or the presence of Mono, Flux, Netty, or WebClient and conclude that the server is running WebFlux.

### 2.2 Where do the two web stacks differ?

| Aspect | Spring MVC on Servlet stack | Spring WebFlux on reactive stack |
| --- | --- | --- |
| HTTP dispatcher | DispatcherServlet | DispatcherHandler |
| Underlying runtime | Servlet API | Reactive Streams and HTTP abstractions independent of the Servlet API |
| Typical web filters | jakarta.servlet.Filter; optionally Spring Security FilterChainProxy | org.springframework.web.server.WebFilter; optionally Spring Security WebFilterChainProxy |
| Request mapping handling | MVC HandlerMapping and HandlerAdapter | Reactive HandlerMapping and HandlerAdapter |
| Body conversion | HttpMessageConverter | HttpMessageReader and HttpMessageWriter |
| Typical starter default server | Tomcat with spring-boot-starter-web | Reactor Netty with spring-boot-starter-webflux |
| Common return types | DTO, ResponseEntity; also supports async/reactive returns | Mono, Flux, and types supported by reactive adapters |

Spring MVC supports asynchronous requests and reactive return types in certain scenarios. Therefore, an MVC controller returning Mono does not turn DispatcherServlet into DispatcherHandler.

## 3. Behavior table when combining dependencies

The following table assumes a typical Spring Boot application with default starters, no special manual customization, and no forced web application type unless stated otherwise:

| Runtime classpath / configuration | WebApplicationType | Web stack configured by Boot |
| --- | --- | --- |
| Has spring-boot-starter-web | SERVLET | Spring MVC |
| Has spring-boot-starter-webflux, no MVC | REACTIVE | Spring WebFlux |
| Has both starters | SERVLET | Spring MVC |
| Has both, forced spring.main.web-application-type=servlet | SERVLET | Spring MVC |
| Has both, forced spring.main.web-application-type=reactive | REACTIVE | Spring WebFlux |
| Forced spring.main.web-application-type=none | NONE | Boot does not start a web server automatically |

This is the **default** behavior, not a guarantee that every arbitrary combination of libraries or custom configurations will start up cleanly. For instance, forcing REACTIVE while excluding dependencies required for a reactive HTTP server can prevent the application from starting.

### What if only WebFlux is present?

If spring-webflux along with the necessary reactive server components are present and competing MVC/Servlet indicators do not dominate, Boot typically deduces REACTIVE. The exact condition is based on the classes checked by SpringApplication, not merely on a dependency having "webflux" in its name.

### What if both starters are present?

spring-boot-starter-web brings Spring MVC, while spring-boot-starter-webflux brings Spring WebFlux and client/reactive libraries. With both standard starters present, Boot deduces SERVLET; thus MVC handles incoming HTTP requests. This behavior is documented by Spring Boot and is the most important case to remember from this lesson.

## 4. How does Spring Boot make the selection?

When SpringApplication is created and run, Spring Boot determines WebApplicationType from the classpath unless the application specifies another type.

Conceptually, Spring Boot 3.3 detection works as follows:

1. Boot checks for indicators of a reactive HTTP framework, such as DispatcherHandler.
2. If only the reactive framework is detected without the checked competing MVC or Servlet framework indicators, Boot can deduce REACTIVE.
3. If reactive is not chosen, Boot checks the classes required for a Servlet web application.
4. When full Servlet indicators are present, Boot deduces SERVLET; if insufficient to build a web runtime, the application type may be NONE.
5. The chosen application type governs ApplicationContext creation and auto-configuration conditions.

Treat this as a **rule description**, not a line-by-line copy of Spring Boot source code. The outcome is also influenced by explicit configuration and classpath packaging.

Once the application type is determined, Boot picks the matching context:

- SERVLET: uses a Servlet web application context, typically AnnotationConfigServletWebServerApplicationContext.
- REACTIVE: uses a reactive web application context, typically AnnotationConfigReactiveWebServerApplicationContext.
- NONE: creates a non-web application context without automatically exposing HTTP endpoints.

The exact context class name may differ if the application customizes context creation. What matters is checking the **actual context type and dispatcher**, not just an implementation class name.

## 5. Which auto-configurations will actually take effect?

Spring Boot uses conditions such as @ConditionalOnClass, @ConditionalOnWebApplication, and @ConditionalOnMissingBean to decide whether to activate each group of auto-configurations.

For **SERVLET**:

- ServletWebServerFactoryAutoConfiguration and Servlet web components are evaluated against their respective conditions.
- DispatcherServletAutoConfiguration and WebMvcAutoConfiguration configure the Spring MVC pipeline where applicable.
- Endpoints use MVC components; Servlet Filters can wrap DispatcherServlet.
- Auto-configurations specific to a reactive web application do not become the HTTP pipeline merely because WebFlux libraries are present.

For **REACTIVE**:

- ReactiveWebServerFactoryAutoConfiguration and WebFluxAutoConfiguration are evaluated against their respective conditions.
- DispatcherHandler and WebFlux components handle HTTP requests.
- WebFilters are applied in the reactive pipeline.
- MVC components meant strictly for Servlet web applications do not become the server dispatcher.

Each auto-configuration also has additional conditions. For example, declaring custom beans or manual configurations can cause an auto-configuration to back off. Therefore, when debugging, inspect the Condition Evaluation Report instead of assuming every bean in a group is always created.

## 6. What happens at runtime if both MVC and WebFlux are present?

Suppose a project declares:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Without a configuration forcing reactive:

1. Boot selects SERVLET.
2. An embedded Servlet web server, typically Tomcat, accepts connections.
3. Requests pass through the Servlet Filter chain to DispatcherServlet.
4. Spring MVC locates the controller, binds parameters, and handles the response.
5. Reactor and WebFlux libraries remain on the classpath so application code can use appropriate APIs, especially WebClient.

The request-receiving flow can be illustrated as follows:

~~~mermaid
flowchart TD
    A["HTTP client"] --> B["Tomcat / Servlet connector"]
    B --> C["Servlet Filter chain"]
    C --> D["DispatcherServlet (Spring MVC)"]
    D --> E["MVC HandlerMapping / HandlerAdapter"]
    E --> F["Controller / Service"]
    F --> G["HTTP response"]
    H["WebClient / Mono / Flux on classpath"] -. "Can be used by the application" .-> F
~~~

**There is no rule** that automatically routes some URLs to MVC and others to WebFlux just because both dependencies are present. If you want two independent HTTP applications using different stacks, you must design, configure, and deploy them explicitly; that is a separate architectural problem.

### What if Reactor Netty is on the classpath?

starter-webflux typically pulls in Reactor Netty for both HTTP client and HTTP server capabilities. Seeing Reactor Netty in the dependency tree does not mean Netty is listening on the application port. In the default dual-starter combination, the HTTP server serving MVC is still typically Tomcat. When forcing reactive, reactive server selection depends on actual server dependencies and configuration; do not rely solely on a dependency's name.

## 7. WebClient can be used in Spring MVC

Yes. This is a common use case and a key reason Boot prioritizes MVC when both starters appear.

Spring Boot can provide a pre-configured WebClient.Builder when WebClient is on the classpath. An MVC service can inject this builder to construct an HTTP client for calling external services.

Example of using WebClient in a service, where the input URI is the actual target address decided by the application:

~~~java
package com.example.dualstack;

import java.net.URI;

import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Service
public class RemoteTextClient {

    private final WebClient client;

    public RemoteTextClient(WebClient.Builder builder) {
        this.client = builder.build();
    }

    public Mono<String> fetch(URI uri) {
        return client.get()
                .uri(uri)
                .retrieve()
                .bodyToMono(String.class);
    }
}
~~~

This class compiles in a Spring Boot project with the noted dependencies; it does not emit an HTTP request at startup by itself. Only when code calls fetch with a valid URI does WebClient perform the call upon subscription of the reactive pipeline.

Do not confuse:

- **WebClient** is an HTTP client for calling another service.
- **WebFlux web server stack** is the framework handling incoming requests to the application.
- Using WebClient does not dictate whether the server uses DispatcherHandler.

If you call .block() directly on an MVC request thread, the code waits for the result and can hold the Servlet thread while waiting on I/O. This may be necessary at a synchronous boundary, though it forfeits non-blocking benefits during that wait. If an MVC controller returns a Mono instead of calling .block(), Spring MVC can adapt the reactive return value via Servlet async support; it is still Spring MVC.

## 8. Mono or Flux in a controller does not prove WebFlux is used

Both Spring MVC and Spring WebFlux can handle certain reactive return types. For example:

~~~java
package com.example.dualstack;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ReactiveValueController {

    @GetMapping("/message")
    public Mono<String> message() {
        return Mono.just("Hello");
    }
}
~~~

In a Boot application that selects SERVLET, this endpoint is still mapped by Spring MVC and served through DispatcherServlet. Spring MVC adapts the single-value Mono to an appropriate asynchronous processing mechanism; writing the final HTTP response still relies on the Servlet stack.

In a Boot application that selects REACTIVE, the same return type can be handled by the WebFlux pipeline. Because @RestController, @GetMapping, and HTTP annotations are supported by both frameworks, looking at annotations alone is not enough to identify the stack.

For Flux and streaming, you must consider Content-Type, streaming support, backpressure, and how each stack writes the response body. MVC can integrate with reactive return values, yet that does not give it WebFlux's non-blocking I/O model.

## 9. How to force WebFlux as the server stack

### 9.1 Configuring via application.properties

~~~properties
spring.main.web-application-type=reactive
~~~

Valid values for this property are servlet, reactive, or none. Use reactive when you genuinely want Boot to create a reactive application context, rather than merely using WebClient.

You can pass it directly at startup:

~~~bash
gradle bootRun --args='--spring.main.web-application-type=reactive'
~~~

If the project has the Gradle wrapper, replace gradle with ./gradlew on Linux/macOS or gradlew.bat on Windows.

### 9.2 Specifying in Java

~~~java
package com.example.dualstack;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DualStackApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(DualStackApplication.class);
        application.setWebApplicationType(WebApplicationType.REACTIVE);
        application.run(args);
    }
}
~~~

This is an **alternative** for configuring the web application type; in the complete runnable example in the next section, the default main method is kept so both modes can be observed via startup arguments.

Forcing REACTIVE changes the application context type and eligible auto-configuration group. It does not automatically rewrite Servlet API-based code, convert every Filter into a WebFilter, make blocking libraries non-blocking, or ensure the application has proper security configuration for the reactive stack.

If a Servlet dependency remains on the classpath, its classes can still be loaded by the JVM; what matters is that Boot selected the reactive web application runtime.

## 10. Runnable example: same classpath, two startup modes

The following minimal example lets you directly observe which context type Boot chooses. Requires Java 17+ and Gradle compatible with Spring Boot 3.3.x.

Project structure:

~~~text
dual-stack-classpath/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/dualstack/DualStackApplication.java
~~~

settings.gradle file:

~~~groovy
rootProject.name = 'dual-stack-classpath'
~~~

build.gradle file:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

src/main/java/com/example/dualstack/DualStackApplication.java file:

~~~java
package com.example.dualstack;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.reactive.context.ReactiveWebServerApplicationContext;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DualStackApplication {

    public static void main(String[] args) {
        SpringApplication.run(DualStackApplication.class, args);
    }
}

@RestController
class RuntimeEndpoint {

    private final ApplicationContext context;

    RuntimeEndpoint(ApplicationContext context) {
        this.context = context;
    }

    @GetMapping(value = "/runtime", produces = MediaType.TEXT_PLAIN_VALUE)
    public String runtime() {
        if (context instanceof ServletWebServerApplicationContext) {
            return "SERVLET";
        }
        if (context instanceof ReactiveWebServerApplicationContext) {
            return "REACTIVE";
        }
        return "NONE";
    }
}
~~~

All required imports, package declarations, and classes for the endpoint are included in the file above. RuntimeEndpoint is a package-private class discovered by Spring component scanning because it is in the same package as DualStackApplication.

### 10.1 Running with defaults

~~~bash
gradle bootRun
~~~

In another terminal:

~~~bash
curl -s http://localhost:8080/runtime
~~~

Expected body:

~~~text
SERVLET
~~~

Reason: both starters are on the classpath, so Spring MVC is prioritized. The returned value comes from the ApplicationContext type rather than guessing from thread names or dependencies.

### 10.2 Running in reactive mode

Stop the previous process holding port 8080, then restart:

~~~bash
gradle bootRun --args='--spring.main.web-application-type=reactive'
~~~

Call again:

~~~bash
curl -s http://localhost:8080/runtime
~~~

Expected body:

~~~text
REACTIVE
~~~

Now Boot creates a reactive web application context and handles the annotated endpoint on the WebFlux pipeline. To verify in a real system, confirm startup completes and check which server is listening; custom dependencies or beans can cause forcing reactive to fail in other projects.

The results above are the expected behavior of the example project with the stated configuration; they are not logs from an actual execution performed in this article.

## 11. Implications for RouterFunction, Filter, Security, and configuration

### 11.1 Two similarly named functional routing APIs

Spring MVC has functional routing APIs in the org.springframework.web.servlet.function package, while WebFlux has corresponding APIs in org.springframework.web.reactive.function.server.

They are different types. A RouterFunction from the reactive package is not automatically recognized by MVC as a Servlet route when Boot selects SERVLET. This can cause developers to see a declared bean yet receive 404 when calling the URL.

When reading code, check the **import package names**, web application type, and which HandlerMappings are actually created.

### 11.2 Filters and security chains

- On the Servlet/MVC stack, HTTP request processing uses Servlet Filters and Servlet-based Spring Security, such as SecurityFilterChain.
- On the reactive/WebFlux stack, HTTP processing uses WebFilters and reactive Spring Security, such as SecurityWebFilterChain.
- Just because both classes can be imported does not mean both protect the same HTTP request.

Security configuration must match the stack actually running. Switching the web-application-type property without reviewing security configuration can cause missing beans, startup errors, or unexpected authentication/authorization behavior.

### 11.3 Do not use @EnableWebMvc or @EnableWebFlux to replace Boot's selection

@EnableWebMvc and @EnableWebFlux allow the application to take manual control over parts of their respective framework configurations. They can cause Boot's default auto-configurations to back off.

They are **not standard switches** for deciding whether SpringApplication uses SERVLET or REACTIVE. To choose the web stack, use dependencies/classpath and SpringApplication web application type; only add Enable annotations when intentionally taking control of framework configuration.

### 11.4 Configuration and supporting libraries

Some components can work regardless of server stack, such as plain Java business services, Repositories, or HTTP clients. Components that depend directly on the Servlet API, reactive ServerWebExchange, or framework-specific beans require the matching runtime.

When writing shared auto-configurations, you can combine conditions like @ConditionalOnWebApplication(type = SERVLET) and @ConditionalOnWebApplication(type = REACTIVE) to create beans per application type. Do not use @ConditionalOnClass alone to infer the stack, since both MVC and WebFlux can coexist on the classpath.

## 12. Debugging when the application runs differently than expected

### 12.1 Short verification workflow

1. Inspect the actual runtimeClasspath, including transitive dependencies, to see whether starter-web and starter-webflux are present.
2. Check the value of spring.main.web-application-type from configuration files and startup arguments.
3. Check whether the actual ApplicationContext is ServletWebServerApplicationContext or ReactiveWebServerApplicationContext.
4. Check startup logs to identify the embedded server and port; remember that a library name on the classpath is not enough to conclude which server is running.
5. If needed, enable the Condition Evaluation Report to see why WebMvcAutoConfiguration or WebFluxAutoConfiguration matched or did not match.
6. Inspect specific imports and beans: servlet RouterFunction, reactive RouterFunction, Filter/WebFilter, SecurityFilterChain/SecurityWebFilterChain.
7. Send an HTTP request and verify the endpoint works through the expected runtime.

Gradle command to inspect dependencies:

~~~bash
gradle dependencies --configuration runtimeClasspath
~~~

To view the auto-configuration condition report in a debug run:

~~~bash
gradle bootRun --args='--debug'
~~~

Rely on the report's output to verify actual conditions; do not guess which beans exist based on starter names.

### 12.2 Common symptoms

| Symptom | Possibility to check |
| --- | --- |
| Added starter-webflux, but server still logs Tomcat | Normal if starter-web is also present and Boot selects SERVLET |
| Have WebClient.Builder, but controllers still go through DispatcherServlet | Normal: WebClient is an HTTP client, it does not select the server stack |
| Controller returns Mono, but runtime is still MVC | Normal: MVC supports certain reactive return types |
| Reactive functional route does not appear | The application may be SERVLET while the bean uses reactive RouterFunction |
| WebFilter configuration does not intercept MVC requests | WebFilter belongs to the reactive pipeline, not Servlet Filters |
| Startup fails after forcing reactive | Check reactive server dependencies, stack-conditional beans, security, and Servlet-specific config |
| Both Tomcat and Netty appear in the dependency tree | Inspect the actual context and server rather than inferring from classpath |
| Test intends to test WebFlux, but always gets MVC | Must explicitly set spring.main.web-application-type=reactive in the test when both stacks are present |

## 13. Testing stack selection

In Spring Boot tests, when both frameworks are present, MVC is still prioritized by default. Therefore, a test targeting a reactive application must explicitly force the intended application type.

Example illustrating annotations for a reactive test:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "spring.main.web-application-type=reactive"
)
class ReactiveModeTest {
    // You can inject ApplicationContext and assert the matching context type.
}
~~~

This snippet illustrates the annotations; you must add imports, the spring-boot-starter-test dependency, and assertion code to make it a standalone test. MockMvc can be used for MVC tests and WebTestClient for reactive tests; WebTestClient can also test Servlet application HTTP endpoints in certain setups, so the presence of WebTestClient **does not by itself prove** the application uses WebFlux.

Prefer testing based on the initialized context type, actual mappings, and expected responses; do not write tests that merely check whether the WebFlux library exists on the classpath.

## 14. Choosing in real-world projects

If the existing application uses Spring MVC controllers, Servlet Filters, Spring Security Servlet, or many blocking libraries, and only needs a reactive HTTP client to call other services, you can keep MVC as the server stack and use WebClient on the client side. Just be clear on handling subscriptions, timeouts, cancellation, and whether or not to call .block() at synchronous boundaries.

If the goal is end-to-end WebFlux with non-blocking I/O, choose a reactive web application intentionally, ensuring clients, data access layers, security chains, and blocking-handling rules align. Changing just a starter or a property will not automatically make an entire service non-blocking.

When maintaining multiple modules, explicitly define the web stack per module and avoid transitive dependencies that introduce ambiguity. In Spring Boot, **web application type determines how Boot initializes the HTTP server framework**, while the classpath determines which libraries are available to use.

## 15. Misconceptions to avoid

- "Having both starters makes Spring Boot open two HTTP servers": false under default configuration; MVC is prioritized.
- "Having Reactor Netty means requests go through WebFlux": false; Netty may simply be the runtime for an HTTP client.
- "Using WebClient means you have built a reactive application": false; WebClient can live inside a Spring MVC application.
- "Returning Mono guarantees the controller is handled by WebFlux": false; MVC supports async/reactive return values.
- "When both frameworks are present, all Filter configurations apply": false; Servlet Filters and WebFlux WebFilters belong to different pipelines.
- "@EnableWebFlux is enough to change how Boot selects ApplicationContext": false; choose the stack via web application type or consistent classpath configuration.
- "Forcing REACTIVE makes all processing non-blocking": false; blocking libraries and code can still stall reactive runtime resources.
- "Checking the dependency tree is enough to know the runtime": false; verify against actual context, auto-configuration conditions, and live endpoints.

## 16. Summary

In Spring Boot 3.3, when both spring-boot-starter-web and spring-boot-starter-webflux appear on the classpath, **Spring MVC/Servlet is selected by default**. WebFlux can still provide WebClient and reactive APIs for client calls or appropriate processing, without automatically becoming the HTTP server pipeline.

To run a WebFlux server, explicitly select REACTIVE and re-verify dependencies, configuration, security, and blocking behavior. The most reliable confirmation is inspecting WebApplicationType, ApplicationContext, auto-configurations, and the live serving path rather than inferring from library names.

## 17. References

- Spring Boot 3.3 — Reactive Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- Spring Boot 3.3 — Testing Spring Boot Applications, Detecting Web Application Type: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3 — Servlet Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Spring Framework — Spring MVC Asynchronous Requests: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
