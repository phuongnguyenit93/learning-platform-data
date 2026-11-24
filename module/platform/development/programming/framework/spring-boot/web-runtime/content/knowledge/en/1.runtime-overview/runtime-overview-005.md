# Spring Boot auto-configuration and application-owned behavior

> **Context:** Spring Boot web runtime, focusing on Spring MVC on the Servlet stack. Practical examples use Spring Boot 4.1.2, Java 17, and Maven. Principles of auto-configuration conditions also apply across many Spring Boot 3.x versions; starter names and some APIs may vary by version.

## Learning objectives

After this lesson, you will be able to:

1. Distinguish **Spring Boot infrastructure auto-configuration** from **application-defined decisions and behavior**.
2. Explain why dependencies, environment properties, and existing beans alter auto-configuration outcomes.
3. Trace the path of an HTTP request: web server → Spring MVC → controller → service → response.
4. Customize Spring MVC while preserving Boot's convenient configuration and diagnose why a configuration is not applied.

## 1. Responsibility boundary: Boot establishes capabilities, the application decides behavior

**Auto-configuration** is the mechanism by which Spring Boot inspects libraries on the classpath, application type, configuration properties, and already-registered beans to **conditionally** declare appropriate infrastructure beans. The goal is to reduce repetitive setup—for example, creating an embedded web server and configuring Spring MVC when the application has the corresponding web dependency.

**Application-owned behavior** is the business contract and policies that the development team decides: which URLs exist, what data is returned, input validation rules, error handling, access permissions, data operations, custom HTTP policies, and specific integrations.

For example, when adding the Spring MVC starter, Boot can configure Tomcat and HTTP routing infrastructure. However, Boot cannot know on its own that `GET /api/greetings/{name}` should exist, what greeting message is right, or who is allowed to call that API. Those decisions only exist when the application declares the corresponding controller, service, and configuration.

| Component/decision | Who provides or decides? | Practical significance |
| --- | --- | --- |
| Dependency `spring-boot-starter-webmvc` | Application chooses; starter provides libraries | Enables Boot to detect web MVC and auto-configure infrastructure |
| Embedded Tomcat, Servlet integration, `DispatcherServlet`, default MVC config | Spring Boot + Spring Framework when conditions match | Provides the runtime to accept and dispatch HTTP requests |
| `@RestController`, `@GetMapping`, `@Service`, and business algorithms | Application | Determines the API and actual output |
| `server.port=8090` | Application declares; Boot reads and applies | Application chooses the value; Boot handles how the server is configured |
| `WebMvcConfigurer`, interceptors, or custom config beans | Application | Extends or replaces specific behavior via supported extension points |
| Logging, JSON, HTTP errors, security | Framework/starter may provide infrastructure or defaults; application decides specific requirements | Framework defaults must not be treated as complete business specs or security policies |

Three mechanisms are easy to confuse:

- **Component scan:** `@ComponentScan` discovers application classes annotated with `@Component`, `@Service`, `@Controller`, `@RestController`, `@Configuration`, etc. within the scan scope. This is how **application-written components** enter the `ApplicationContext`.
- **Auto-configuration:** `@EnableAutoConfiguration` imports configuration classes provided by Boot or libraries, then evaluates conditions to create **appropriate default beans/infrastructure**. It does not scan or generate business logic.
- **Explicit configuration:** `@Bean`, `@Configuration`, `application.properties`/`application.yaml` properties, and extension points express the **application's choices**. Some choices cause auto-configuration to apply differently.

Typically, place only **one** `@SpringBootApplication` on the startup class. This annotation combines `@SpringBootConfiguration`, `@EnableAutoConfiguration`, and `@ComponentScan`. Placing the startup class in the root package of application code lets component scan discover controllers/services in subpackages.

## 2. What happens when the web runtime starts up?

For a typical Servlet MVC application:

1. `main()` calls `SpringApplication.run(...)`.
2. Spring Boot prepares the `Environment`, reads configuration, and determines the `ApplicationContext` type matching the classpath/configuration.
3. Spring processes the `@SpringBootApplication` class, registers application-declared components, and loads auto-configuration candidates.
4. Each auto-configuration checks conditions: is the library present, is the web application type right, is the property enabled, does a corresponding bean already exist, etc.
5. During context refresh, the framework creates/wires necessary beans. For a Servlet application with the MVC starter, the embedded web server, `DispatcherServlet`, mapping components, argument resolution, message conversion, etc. are set up according to configuration.
6. The web server begins accepting requests; startup lifecycle finishes when the application is ready to serve according to the corresponding readiness mechanisms.

Key point: **auto-configuration primarily determines application structure when the context is initialized**. It does not rewrite controller logic every time an HTTP request arrives. When a request runs, the already-configured beans and pipeline are used.

Typical REST request flow:

~~~text
HTTP client
    |
    v
Tomcat (Servlet container)
    |
    v
Servlet Filter chain (if any)
    |
    v
DispatcherServlet (Spring MVC)
    |
    +--> HandlerMapping finds matching route
    +--> HandlerInterceptor before handler (if registered)
    +--> HandlerAdapter invokes application controller
                         |
                         v
                  Application service/business logic
                         |
                         v
                    Controller returns data
    |
    +--> HttpMessageConverter writes response, e.g., JSON
    +--> Complete corresponding interceptor/filter steps
    |
    v
HTTP response
~~~

The actual path may include exception resolvers, argument resolvers, validation, security filters, and more. **Spring MVC handles dispatching; the application's controllers/services decide business semantics.** When using WebFlux, the reactive pipeline and server may differ (e.g., Reactor Netty), so do not apply this Servlet diagram verbatim to WebFlux.

## 3. Why can the same source code yield different auto-configuration?

Auto-configuration uses conditions such as:

| Condition | Question checked | Example meaning |
| --- | --- | --- |
| `@ConditionalOnClass` | Is a required class/library on the classpath? | Enable integration only if the corresponding technology was added |
| `@ConditionalOnWebApplication` | Is this a Servlet or reactive web application? | Choose configuration branch according to web stack |
| `@ConditionalOnBean` | Is a prerequisite bean already present? | Additional configuration runs only when the right dependency exists |
| `@ConditionalOnMissingBean` | Has a bean not yet been provided by the user or another config? | Defaults can yield to beans declared by the application |
| `@ConditionalOnProperty` | Does the environment config have the matching value? | Conditionally enable/disable a feature |

**"Back off" has a narrow meaning:** when the condition for **a specific piece of auto-configuration** is no longer satisfied, the corresponding default bean/configuration is not created. It does not mean declaring any `@Bean` disables all of Spring Boot. Which bean is replaced depends on **the exact bean type and that auto-configuration's conditions**. With `@ConditionalOnMissingBean`, bean definition registration order also matters; Boot documentation recommends this condition inside auto-configuration because user configuration is processed first.

Examples of cause and effect:

- **Adding the MVC starter:** the classpath contains web classes; web MVC conditions match, and Boot creates the related components.
- **Changing `server.port`:** server infrastructure is still configured by Boot, but the application decides the listening port.
- **Adding a `@RestController`:** the application gains a new route; Boot does not "discover" endpoints from lesson names or auto-generate business logic.
- **Providing a custom bean at the right extension point:** that bean can supplement infrastructure or cause the corresponding default bean to back off.
- **Excluding a specific auto-configuration via `exclude`/`spring.autoconfigure.exclude`:** only do this when you know the exact configuration class to exclude and its consequences, as you may need to supply the missing infrastructure yourself.

Modern auto-configuration candidates are listed in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` inside the corresponding JAR. This is a configuration-loading mechanism, **not a business API list** for the application to call directly.

## 4. Runnable example: Boot builds the runtime, the application owns the API

The example uses **Spring Boot 4.1.2**, **JDK 17+**, and **Maven 3.6.3+**. In Spring Boot 4, `spring-boot-starter-webmvc` is the direct starter for Spring MVC/Tomcat; in Spring Boot 3.x projects, `spring-boot-starter-web` is typically used with a compatible Boot 3.x version. To keep the code easy to follow, the demo uses just one JSON API and an interceptor adding a response header.

Directory structure:

~~~text
ownership-demo/
  pom.xml
  src/main/java/com/example/ownership/
    OwnershipApplication.java
    GreetingService.java
    GreetingController.java
    HttpPolicyConfig.java
  src/main/resources/
    application.properties
~~~

**`pom.xml`**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>ownership-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Boot's parent manages compatible dependency versions. The MVC starter provides the components needed for Spring MVC, Tomcat, and JSON according to the illustrated version's dependency set; the application does not need to instantiate `DispatcherServlet` manually.

**`src/main/java/com/example/ownership/OwnershipApplication.java`**

~~~java
package com.example.ownership;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OwnershipApplication {
    public static void main(String[] args) {
        SpringApplication.run(OwnershipApplication.class, args);
    }
}
~~~

This is the entry point and contains no greeting logic. Package `com.example.ownership` encloses the remaining classes so component scan finds them.

**`src/main/java/com/example/ownership/GreetingService.java`**

~~~java
package com.example.ownership;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

The string `Hello, ...!` is a **business rule owned by the application**, unrelated to Spring Boot defaults.

**`src/main/java/com/example/ownership/GreetingController.java`**

~~~java
package com.example.ownership;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/greetings")
public class GreetingController {
    private final GreetingService service;

    public GreetingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping("/{name}")
    public GreetingResponse greet(@PathVariable String name) {
        return new GreetingResponse(service.greet(name));
    }

    public record GreetingResponse(String message) {}
}
~~~

The application defines the URL, HTTP method, parameter name, and JSON shape via `GreetingResponse`. Spring MVC maps requests to this method and the properly configured HTTP/JSON converter serializes the record into the response. Constructor injection uses the `GreetingService` bean discovered by component scan.

**`src/main/java/com/example/ownership/HttpPolicyConfig.java`**

~~~java
package com.example.ownership;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class HttpPolicyConfig implements WebMvcConfigurer {
    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        HandlerInterceptor addHeader = new HandlerInterceptor() {
            @Override
            public boolean preHandle(HttpServletRequest request,
                                     HttpServletResponse response,
                                     Object handler) {
                response.setHeader("X-App-Policy", "greeting-demo");
                return true;
            }
        };
        registry.addInterceptor(addHeader).addPathPatterns("/api/**");
    }
}
~~~

This is an **application HTTP policy**. `WebMvcConfigurer` adds an interceptor to Spring MVC while preserving most of Boot's convenient MVC configuration. `preHandle` returns `true` to continue invoking the controller. The header above only illustrates ownership; it does not replace authentication, authorization, or security mechanisms.

**`src/main/resources/application.properties`**

~~~properties
server.port=8090
~~~

The port is the application's choice; actually configuring Tomcat's connector is infrastructure's job. If this line is omitted, the default HTTP port is typically `8080`, provided no other configuration source overrides it.

**Run and verify**

In the `ownership-demo` directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Open a second terminal and call:

~~~bash
curl -i http://localhost:8090/api/greetings/Lan
~~~

On Windows PowerShell 5.1, you can use `curl.exe -i http://localhost:8090/api/greetings/Lan` to invoke the actual curl executable. Expect **HTTP 200**, header `X-App-Policy: greeting-demo`, JSON Content-Type, and the following body (headers like Date/Connection may vary):

~~~json
{"message":"Hello, Lan!"}
~~~

You can package and run the JAR:

~~~bash
mvn package
java -jar target/ownership-demo-0.0.1-SNAPSHOT.jar
~~~

Maven downloads dependencies and compiles sources; running `javac` alone without Spring's classpath will not suffice to build this example.

**Separating each observed step:**

| Observation | Origin |
| --- | --- |
| Application has an HTTP web server on port `8090` | Boot configures the server based on dependencies and application-set properties |
| `GET /api/greetings/Lan` finds a handler | Spring MVC dispatches based on application-declared mappings |
| Response body contains `Hello, Lan!` | Application's `GreetingService` and `GreetingController` |
| Response has `X-App-Policy: greeting-demo` | Interceptor registered by the application |
| Response is serialized as JSON | Message conversion infrastructure + properly configured JSON library |

Try modifying `GreetingService.greet()` to `return "Welcome, " + name + "!";` and rerunning: the body changes, while the server/MVC remains supported by Boot. Conversely, change `server.port=8091` and restart: the access address changes, while the business logic needs no rewriting. This lets you directly observe the **ownership boundary**.

## 5. Choosing the right level of customization

Ordered from least intrusive to most intrusive:

1. **Accept conditional defaults:** use the appropriate starter and write only the necessary controllers/services.
2. **Set supported properties:** e.g., `server.port`, request size limits, or appropriate session policies; check exact property names for your version.
3. **Add components/extension points:** declare `WebMvcConfigurer`, `Converter`, `Filter`, `HandlerInterceptor`, `@ControllerAdvice`, or framework-supported custom beans. Pick the mechanism at the right layer: Servlet filters run at the Servlet layer, MVC interceptors run around handlers, services execute business logic.
4. **Provide a bean replacing a default:** only do this when documentation or the condition report confirms that bean type is conditionally created by auto-config; check compatibility and dependencies of the replacement bean.
5. **Take full control over a group of infrastructure:** for example, using `@EnableWebMvc` when you want complete control over MVC configuration. This is a major decision: Spring Boot MVC auto-configuration will no longer apply as before; the application must handle the conveniences it needs itself.
6. **Exclude specific auto-configurations:** an intentional measure when you completely want to disable a configuration branch. Never use exclude merely to "fix" an uninvestigated error.

Do not use `@EnableWebMvc` just to add an interceptor, formatter, or mapping: in that case, `WebMvcConfigurer` is the proper extension point.

An important note on **Spring Security**: adding the security dependency can activate framework-configured security defaults. However, policies on who can access which routes, which sources authenticate, and which roles authorize still need to be designed, tested, and owned by the application. Do not assume an application is secure merely because a starter or auto-configuration is present.

## 6. Diagnosing when Boot does not configure as expected

Do not guess from starter names. Check the causal chain:

1. **Classpath:** are dependencies on the right version and right web stack? MVC and WebFlux are two different request-serving models; Servlet controllers/interceptors in this example belong to Spring MVC.
2. **Property sources:** are `application.properties`, profiles, environment variables, and command-line arguments setting the same key? The effective value may come from a higher-precedence source.
3. **Bean definitions:** did the application declare a bean that caused a `@ConditionalOnMissingBean` condition to stop matching? Is there an explicit configuration taking over MVC?
4. **Component scan:** is the `@SpringBootApplication` class in a parent package of the controllers/services/configs? Was the bean registered into the context?
5. **Condition report:** start with `--debug` to see why auto-configurations were or were not applied. For example, run `mvn spring-boot:run -Dspring-boot.run.arguments=--debug` with shell-compatible argument syntax.
6. **Actuator when needed:** if `spring-boot-starter-actuator` is added, the `conditions` endpoint can show matched/unmatched conditions. Configure appropriate access control and exposure; do not expose sensitive diagnostic endpoints to the Internet.

When reading the report, look for relevant auto-configuration names (e.g., MVC/Servlet web server) and distinguish:

- **Positive matches:** the corresponding conditions passed.
- **Negative matches:** conditions did not pass; the reason typically indicates a missing class, wrong application type, missing bean, or existing replacement bean.
- **Exclusions:** auto-configurations explicitly excluded by configuration.

The condition report describes **configuration decisions**; it does not prove the business API is correct. To know what an endpoint actually returns, you still must run request tests or integration tests.

| Symptom | First thing to check | Who needs to fix it? |
| --- | --- | --- |
| Application runs but `/api/greetings/Lan` returns 404 | Mappings, component scan, context path, port being called | Primarily application code/configuration |
| Startup fails with missing bean | Dependencies, annotations, constructor injection, condition report | Application declarations and Boot conditions must be understood together |
| Port differs from `application.properties` | Higher-precedence config source, active profile, run arguments | Application/deployment |
| Interceptor does not run | Was `HttpPolicyConfig` scanned; does path pattern match; is there an unexpected `@EnableWebMvc` | Application |
| Malformed JSON or type fails serialization | JSON dependency, message converter, response type, and actual error | Both configured infrastructure and application code |
| Adding a library changes runtime behavior | Classpath, web app type, conditions whose evaluation just changed | Review dependency policies and auto-configuration |

## 7. Common misconceptions

- **"Having the web starter means APIs exist automatically."** False. The starter makes HTTP infrastructure available; routes must still be registered in the application.
- **"`@SpringBootApplication` is just component scan."** False. It also enables auto-configuration and marks the application's primary configuration.
- **"Every `@Bean` overrides auto-configuration."** False. Only conditions tied to specific beans back off; duplicate or mismatched declarations can cause startup failures.
- **"Spring Boot owns responses because Boot runs the web server."** False. Boot/Framework executes the pipeline; route contracts and processing logic belong to the application.
- **"To customize MVC you must add `@EnableWebMvc`."** False in most Boot projects. Prefer `WebMvcConfigurer` and supported extension points.
- **"Changing a property hot-reconfigures every request automatically."** Not by default. Many bean/server decisions are applied at context initialization; a restart is usually required to apply changes.
- **"If the condition report matches, the application is right."** False. It confirms configuration conditions, not business behavior, security, or API results.

## 8. Self-check questions

**Scenario A:** You have the MVC dependency and a `@GetMapping("/orders")` controller, but no service yet. Who is responsible for defining `/orders` data?

**Answer:** The application. Boot can supply the web server and mapping mechanism, but controllers/services must define the data and HTTP contract; missing business dependencies may cause context startup to fail.

**Scenario B:** You only want to add a header to API responses. Should you add `@EnableWebMvc` or `WebMvcConfigurer`?

**Answer:** Use an appropriate extension point such as `WebMvcConfigurer` with a `HandlerInterceptor` if tied to MVC handlers, or a Servlet filter if it must apply at the Servlet layer. No need to take over all MVC configuration.

**Scenario C:** A default bean disappears after you add a custom `@Bean`. Is "Boot turned off" a valid quick conclusion?

**Answer:** No. Check the exact bean type, related `@ConditionalOnMissingBean` condition, and condition report. One auto-configuration branch can back off while other branches keep working.

**Scenario D:** Change `server.port` from 8090 to 8091. What belongs to Boot, and what belongs to the application?

**Answer:** The application owns the configuration value and deployment decision; Boot applies that value to the configured web server. Routes and business logic can remain unchanged.

## Official references

- [Spring Boot — Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html)
- [Spring Boot — Servlet Web Applications / Spring MVC Auto-configuration](https://docs.spring.io/spring-boot/reference/web/servlet.html)
- [Spring Boot — Creating Your Own Auto-configuration (explaining conditions)](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
- [Spring Boot — Embedded Web Servers](https://docs.spring.io/spring-boot/how-to/webserver.html)
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — Build Systems and System Requirements](https://docs.spring.io/spring-boot/reference/using/build-systems.html)

**Principle to remember:** Spring Boot conditionally selects and assembles default infrastructure; Spring Framework executes the pipeline; the application owns its APIs, business rules, and the configuration/policy choices it declares.