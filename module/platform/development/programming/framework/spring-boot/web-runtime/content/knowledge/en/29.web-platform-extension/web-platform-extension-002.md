# Configuring ResourceConfig, Jersey Servlet or Filter, and Application Paths in Spring Boot

## 1. Lesson Objectives

When building APIs on Spring Boot, not every application uses Spring MVC `@RestController`. A project may choose **Jersey**, an implementation of **Jakarta RESTful Web Services (JAX-RS/Jakarta REST)**, to write resources with `@Path`, `@GET`, `@POST`, `@Produces`, and `@Consumes`. Spring Boot supports Jersey integration on the **Servlet web runtime**, typically using Tomcat.

Four questions determine the exact configuration:

1. **Which resources and providers does `ResourceConfig` register?**
2. **Is Jersey placed into the Servlet container as a `Servlet` or a `Filter`?**
3. **What is Jersey's base URI?** Distinguish `@ApplicationPath`, `spring.jersey.application-path`, context path, and `@Path`.
4. **Does Jersey run alongside Spring MVC/`DispatcherServlet`?** If so, you must avoid capturing all URLs or configure the filter to forward requests Jersey does not handle.

This lesson uses Spring Boot **3.x**, **Java 17+**, and Jersey with the **`jakarta.ws.rs.*`** namespace. The main example runs standalone with Gradle, followed by a Spring MVC + Jersey filter variant. Properties and bean names are verified against the Spring Boot 3.3 documentation.

### Example of a Common Problem

A developer writes:

~~~java
@Path("/hello")
public class HelloResource {
    @GET
    public String hello() {
        return "hello";
    }
}
~~~

yet `GET http://localhost:8080/hello` returns 404. The code itself may not be wrong: the resource was not registered via `ResourceConfig.register`, Jersey is mounted at `/api/*`, the application has `server.servlet.context-path=/shop`, or the request was routed elsewhere by `DispatcherServlet`/a reverse proxy.

**Core lesson:** you must derive the URL from **all path layers**, not just look at `@Path` on the resource.

## 2. Different Roles of Jersey, Spring MVC, and the Servlet Container

~~~text
HTTP client
    |
    v
Embedded Tomcat / Servlet container
    |
    +--> Servlet mapping: Jersey ServletContainer
    |       |
    |       v
    |    Jersey ResourceConfig -> JAX-RS @Path/@GET/@POST
    |
    +--> Servlet mapping: Spring DispatcherServlet
            |
            v
         @RestController/@GetMapping
~~~

In **Jersey servlet** mode, the Servlet container picks a servlet by **Servlet URL mapping**. If Jersey maps `/*` by default, it can receive nearly all requests, conflicting with `DispatcherServlet` and static resources. Another servlet mapped to `/` will not automatically run after Jersey returns 404.

In **Jersey filter** mode, requests pass through the Filter chain before reaching the selected servlet. Jersey can handle JAX-RS requests, or (when configured) **forward unmatched requests** so another servlet, such as Spring MVC `DispatcherServlet`, handles them.

| Component | Technology | Responsibility |
| --- | --- | --- |
| `Tomcat` / Servlet container | Jakarta Servlet | Opens HTTP port, matches servlet mapping, invokes filters, manages request/response |
| `ResourceConfig` | Jersey | Declares resources, providers, features, and Jersey-specific properties |
| `ServletContainer` | Jersey | Adapter implementing Jersey as a `Servlet` **or** `Filter` |
| `@Path` and `@GET` | JAX-RS | Defines resource path and HTTP method inside Jersey |
| `DispatcherServlet` | Spring MVC | Dispatches `@Controller` / `@RestController` |
| `ServletRegistrationBean` | Spring Boot | Registers servlet + URL pattern + load-on-startup |
| `FilterRegistrationBean` | Spring Boot | Registers filter + URL pattern + order |
| `server.servlet.context-path` | Spring Boot | Shared context path prefix for servlets in the application |
| `spring.jersey.application-path` | Spring Boot/Jersey | Base path serving Jersey; **takes precedence over `@ApplicationPath`** |

**Do not equate `ResourceConfig` with `WebMvcConfigurer`.** Configuring a Jersey resource with `@Path` does not make it a Spring MVC controller; a `@GetMapping` is not registered via `ResourceConfig.register` as a JAX-RS endpoint.

## 3. Creating a Jersey Application on Spring Boot 3.x

Basic dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jersey'
}
~~~

`spring-boot-starter-jersey` is the starting point for Jersey integration provided by Spring Boot. In Boot 3.x, JAX-RS annotations live in `jakarta.ws.rs`, not `javax.ws.rs` from older Java EE/Jersey 2.

| Modern Spring Boot | Role |
| --- | --- |
| `org.glassfish.jersey.server.ResourceConfig` | Declares the Jersey app |
| `org.glassfish.jersey.servlet.ServletContainer` | Servlet/filter adapter |
| `jakarta.ws.rs.Path` | Resource path |
| `jakarta.ws.rs.GET`, `POST`, `PUT`, `DELETE` | HTTP method |
| `jakarta.ws.rs.Produces`, `Consumes` | Media type |
| `jakarta.ws.rs.PathParam`, `QueryParam` | URI variables/parameters |
| `jakarta.ws.rs.core.Response` | JAX-RS status, headers, entity |
| `jakarta.ws.rs.ApplicationPath` | Base path for the JAX-RS app |
| `org.springframework.stereotype.Component` | Registers resource/config in the Spring context |

Do not mix Jersey 2/`javax.ws.rs` artifacts with Spring Boot 3/`jakarta.*`. When migrating code from Boot 2, check imports, dependencies, and Jakarta-compatible JAX-RS providers.

### ResourceConfig Must Be a Spring Bean

Typical Spring Boot pattern:

~~~java
import jakarta.ws.rs.ApplicationPath;
import org.glassfish.jersey.server.ResourceConfig;
import org.springframework.stereotype.Component;

@Component
@ApplicationPath("/api")
public class JerseyConfig extends ResourceConfig {
    public JerseyConfig() {
        register(HelloResource.class);
    }
}
~~~

Spring Boot looks for a bean of type `ResourceConfig` and auto-configures Jersey. Another option is declaring a `@Bean ResourceConfig` inside a `@Configuration` class, but **use only one clear Jersey configuration** and avoid registering multiple competing `ResourceConfig` beans.

Registering resources with `register(SomeResource.class)` lets Jersey know explicitly which resources to handle. Spring Boot documentation recommends **registering each resource explicitly** because Jersey's package scanning has limitations in executable JARs and some executable WARs, especially for classpath entries under `BOOT-INF/classes` or `WEB-INF/classes`. Do not assume `packages("com.example.api")` always behaves the same way when packaged as it does in an IDE.

### A Resource Can Also Be a Spring @Component

~~~java
@Component
@Path("/hello")
public class HelloResource {
    private final GreetingService greetingService;

    public HelloResource(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GET
    @Produces(MediaType.TEXT_PLAIN)
    public String hello() {
        return greetingService.hello();
    }
}
~~~

With the starter's Jersey-Spring integration, Spring manages resources annotated with `@Component` to support dependency injection. Constructor-injected services pass through the Spring container like other Spring beans.

**Do not mix two instantiation mechanisms:** a Jersey resource instantiated directly by Jersey is not guaranteed to receive all Spring dependencies if integration is missing. Following the Spring Boot pattern, `@Component` on the resource + `register(ResourceClass.class)` is the transparent approach. Test injection in a real executable JAR.

## 4. What Parts Compose the Complete URL?

For a Servlet application, an external client URL typically has the structure:

~~~text
http://host:port
  + server.servlet.context-path
  + Jersey application path (servlet/filter URL mapping)
  + JAX-RS resource @Path
  + JAX-RS method @Path (if any)
  + ?query-parameters

Example:
  http://localhost:8080
  + /shop
  + /api
  + /greetings
  + /Linh
  = http://localhost:8080/shop/api/greetings/Linh
~~~

Separate the layers clearly:

1. **`server.port=8080`**: network port where the embedded server listens.
2. **`server.servlet.context-path=/shop`**: servlet context path, preceding URL mappings of servlets in that context.
3. **`@ApplicationPath("/api")`** on `ResourceConfig`: Jersey base path.
4. **`@Path("/greetings")`** on the JAX-RS class: resource path relative to the base.
5. **`@Path("/{name}")`** on the method: additional path segment.
6. A reverse proxy can publish an external URL with a different prefix; rewriting paths at the proxy **does not automatically alter** the application's servlet/Jersey mapping.

`spring.mvc.servlet.path` configures the path of **Spring MVC DispatcherServlet**, not Jersey's base path. If you want to move Jersey to `/rest`, use `@ApplicationPath` or `spring.jersey.application-path`, not `spring.mvc.servlet.path`.

### URL Table Examples

Assuming a resource `@Path("/greetings")` and a `@GET` method:

| server.servlet.context-path | @ApplicationPath | spring.jersey.application-path | Expected URL |
| --- | --- | --- | --- |
| unset | unset | unset | `/greetings` (default Jersey servlet `/*`) |
| unset | `/api` | unset | `/api/greetings` |
| `/shop` | `/api` | unset | `/shop/api/greetings` |
| `/shop` | `/api` | `/rest` | `/shop/rest/greetings` |
| `/shop` | `/jaxrs` | `/v2/api` | `/shop/v2/api/greetings` |

**Precedence order:** if `spring.jersey.application-path` is configured, Spring Boot uses that property **instead of** the `@ApplicationPath` value. The two prefixes are not concatenated. Given `@ApplicationPath("/api")` and `spring.jersey.application-path=/rest`, the final path uses **`/rest`**, not `/api/rest`.

Recommendation: dedicate **a separate base path** such as `/rest` or `/jaxrs` when Jersey runs alongside Spring MVC to avoid competing over shared URLs.

## 5. Runnable Project A: Standalone Jersey Servlet + ResourceConfig + @ApplicationPath

Project A uses only Jersey + an embedded Servlet container. The API has 3 operations: GET greeting, GET by name, and POST echo. It uses `text/plain` to stay focused on mappings; JSON serialization is covered by provider configuration.

### 5.1. Structure

~~~text
jersey-servlet-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/jersey/
    │   │   ├── JerseyApplication.java
    │   │   ├── JerseyConfig.java
    │   │   ├── GreetingResource.java
    │   │   └── GreetingService.java
    │   └── resources/application.properties
    └── test/
        └── java/demo/jersey/JerseyServletTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jersey-servlet-lab'
~~~

`build.gradle` (Java 17, Spring Boot 3.3.13 as an example):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jersey'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`src/main/resources/application.properties`:

~~~properties
server.port=8080
server.servlet.context-path=/shop

# Jersey is a servlet by default. Make the lab choice explicit.
spring.jersey.type=servlet

# Eagerly initialize the Jersey servlet in this demonstration.
spring.jersey.servlet.load-on-startup=1

# Application base path is taken from @ApplicationPath("/api")
# on JerseyConfig in this first run.
~~~

Only when you want to **override** `@ApplicationPath("/api")`, add `spring.jersey.application-path=/rest`; omit this property initially in the lab so the annotation's effect is clear.

### 5.2. Main Class

`src/main/java/demo/jersey/JerseyApplication.java`:

~~~java
package demo.jersey;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JerseyApplication {
    public static void main(String[] args) {
        SpringApplication.run(JerseyApplication.class, args);
    }
}
~~~

### 5.3. ResourceConfig Bean

`src/main/java/demo/jersey/JerseyConfig.java`:

~~~java
package demo.jersey;

import jakarta.ws.rs.ApplicationPath;
import org.glassfish.jersey.server.ResourceConfig;
import org.springframework.stereotype.Component;

@Component
@ApplicationPath("/api")
public class JerseyConfig extends ResourceConfig {
    public JerseyConfig() {
        register(GreetingResource.class);
    }
}
~~~

`@ApplicationPath("/api")` means the resource root `/api` *inside the servlet context*. `register(GreetingResource.class)` registers the JAX-RS resource; it does not change the path and does not add a Spring MVC controller.

### 5.4. Spring Service Injected into a JAX-RS Resource

`src/main/java/demo/jersey/GreetingService.java`:

~~~java
package demo.jersey;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String defaultGreeting() {
        return "Hello from Jersey";
    }

    public String greetingFor(String name) {
        return "Hello, " + name;
    }
}
~~~

`src/main/java/demo/jersey/GreetingResource.java`:

~~~java
package demo.jersey;

import jakarta.ws.rs.Consumes;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.POST;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.PathParam;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;

import org.springframework.stereotype.Component;

@Component
@Path("/greetings")
public class GreetingResource {
    private final GreetingService service;

    public GreetingResource(GreetingService service) {
        this.service = service;
    }

    @GET
    @Produces(MediaType.TEXT_PLAIN)
    public String hello() {
        return service.defaultGreeting();
    }

    @GET
    @Path("/{name}")
    @Produces(MediaType.TEXT_PLAIN)
    public String helloName(@PathParam("name") String name) {
        return service.greetingFor(name);
    }

    @POST
    @Consumes(MediaType.TEXT_PLAIN)
    @Produces(MediaType.TEXT_PLAIN)
    public Response echo(String body) {
        return Response.ok("Echo: " + body).build();
    }
}
~~~

Note:

- `@Path` on the class defines `/greetings`; `@Path("/{name}")` on the method appends `/Linh`.
- `@GET` and `@POST` are JAX-RS annotations, **not** Spring MVC `@GetMapping` or `@PostMapping`.
- `@Produces(TEXT_PLAIN)` controls response representation/content negotiation.
- `@Consumes(TEXT_PLAIN)` specifies that POST only accepts an appropriate plain text body.
- `@PathParam("name")` reads the path variable; it is not Spring MVC `@PathVariable`.
- `Response.ok(...).build()` creates a 200 JAX-RS response. The echo example **does not persist real data**, so it does not return 201 Created.
- The constructor receiving `GreetingService` proves the Jersey resource is a Spring-managed component, unlike a plain Jersey POJO without Spring integration.

### 5.5. Running the Project

If the project already has a Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

If there is no wrapper yet, generate one with a compatible Gradle version or use `gradle bootRun` from an installed Gradle. The server listens on port 8080.

#### Default GET

~~~bash
curl -i http://localhost:8080/shop/api/greetings
~~~

Expected:

~~~http
HTTP/1.1 200
Content-Type: text/plain

Hello from Jersey
~~~

Other headers and `charset` details may vary. What is certain is **HTTP 200** and body `Hello from Jersey`.

#### GET with @PathParam

~~~bash
curl -i http://localhost:8080/shop/api/greetings/Linh
~~~

Expected HTTP 200 and body:

~~~text
Hello, Linh
~~~

#### POST text/plain

~~~bash
curl -i -X POST http://localhost:8080/shop/api/greetings \
  -H "Content-Type: text/plain" \
  -H "Accept: text/plain" \
  --data "hello"
~~~

Expected HTTP 200 with body:

~~~text
Echo: hello
~~~

#### A URL with the Wrong Base Path

~~~bash
curl -i http://localhost:8080/greetings
~~~

Expect it not to reach the resource because **`/shop/api` is missing**. Typically this is HTTP 404; the status/body of an unmapped path can be influenced by container fallback/error handlers.

### 5.6. Overriding @ApplicationPath via Property

Add **one line** to `application.properties`:

~~~properties
spring.jersey.application-path=/rest
~~~

Restart the application. The same `@Path("/greetings")` now has the endpoint:

~~~text
http://localhost:8080/shop/rest/greetings
~~~

Meanwhile `/shop/api/greetings` is no longer the intended Jersey base URL. **Do not concatenate `/api` and `/rest`**; the Spring Boot property overrides the annotation.

If you do not need the annotation in code, you can remove `@ApplicationPath` and use the property as the **single source of truth** across environments. If you need a fixed module-level base path, the annotation helps document the URL contract. When both exist simultaneously, document the precedence in operations docs.

## 6. HTTP Integration Tests: Verifying the Real Jersey Servlet and Context Path

`@WebMvcTest`/`MockMvc` are for Spring MVC controllers and do not prove that JAX-RS `ResourceConfig`, Jersey `ServletContainer`, and servlet URL mapping are enabled properly. With Jersey, write tests that run a **real embedded server and HTTP**.

Add `src/test/java/demo/jersey/JerseyServletTest.java`:

~~~java
package demo.jersey;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class JerseyServletTest {
    @Autowired
    TestRestTemplate rest;

    @Test
    void applicationAndResourcePathsCompose() {
        ResponseEntity<String> result = rest.getForEntity(
                "/shop/api/greetings", String.class);

        assertThat(result.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(result.getBody())
                .isEqualTo("Hello from Jersey");
    }

    @Test
    void methodPathParamIsResolved() {
        ResponseEntity<String> result = rest.getForEntity(
                "/shop/api/greetings/Linh", String.class);

        assertThat(result.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(result.getBody()).isEqualTo("Hello, Linh");
    }

    @Test
    void postUsesJaxRsConsumesAndProduces() {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.TEXT_PLAIN);
        headers.setAccept(java.util.List.of(MediaType.TEXT_PLAIN));
        HttpEntity<String> request =
                new HttpEntity<>("hello", headers);

        ResponseEntity<String> result = rest.postForEntity(
                "/shop/api/greetings", request, String.class);

        assertThat(result.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(result.getBody()).isEqualTo("Echo: hello");
    }
}
~~~

Run:

~~~bash
./gradlew test --tests demo.jersey.JerseyServletTest
~~~

`RANDOM_PORT` avoids needing a fixed port 8080; `TestRestTemplate` sends HTTP requests to the real server in the test context. The tests above assume **`spring.jersey.application-path=/rest` is not set**; if you enabled the override in the previous section, update the test URIs to match the new contract or use test properties to select an explicit profile.

**What the test proves:** Jersey is registered as a servlet, `ResourceConfig` sees the resource, Spring DI works, context path + `@ApplicationPath` + `@Path` compose correctly, and content types are handled. It does not yet verify production proxies or certificates.

## 7. Jersey Is a Servlet by Default: The ServletRegistrationBean Mechanism

When a `ResourceConfig` bean and `spring-boot-starter-jersey` are present, Spring Boot 3.3 auto-configuration by default creates a bean of type:

~~~text
ServletRegistrationBean<org.glassfish.jersey.servlet.ServletContainer>
bean name: jerseyServletRegistration
default Jersey mapping: /*
~~~

Jersey `ServletContainer` is the Servlet adapter receiving HTTP requests from the container and passing them into the Jersey runtime/`ResourceConfig`. The default `/*` mapping is very broad if no explicit base path is configured.

Related properties:

~~~properties
spring.jersey.type=servlet
spring.jersey.servlet.load-on-startup=1
spring.jersey.application-path=/api
~~~

- `spring.jersey.type=servlet`: selects Servlet mode (default).
- `spring.jersey.servlet.load-on-startup`: Servlet initialization order/priority; default `-1` means lazy initialization in the documented Boot setup. Set a non-negative value for startup loading when you want to catch Jersey errors early.
- `spring.jersey.application-path`: base path, taking precedence over `@ApplicationPath`.
- `spring.jersey.init.*`: supplies init parameters for the registration when needed.

**Do not use `spring.jersey.servlet.load-on-startup` to configure timeouts or thread pools.** It only controls when the servlet is initialized.

### Servlet Mapping and Spring MVC

Suppose the same app has:

~~~text
DispatcherServlet: mapping /
Jersey ServletContainer: mapping /*
~~~

`/*` is a prefix servlet mapping that can be chosen ahead of the default servlet mapping `/`. Consequently, `@RestController` URLs, static resources, or other routes may go to Jersey instead of reaching MVC. Jersey returning 404 **does not mean** the container automatically runs `DispatcherServlet` next; Servlet dispatch chooses one servlet first and then processes the request.

**Two ways to avoid contention:**

1. If Jersey and MVC **do not need to share the same prefix**, place Jersey at `/jaxrs/*` via `@ApplicationPath("/jaxrs")` or `spring.jersey.application-path=/jaxrs`. MVC continues handling `/mvc/...` through `DispatcherServlet`.
2. If you want Jersey **to sit in front of MVC and yield unmatched requests**, switch to **Jersey Filter mode** and enable `FILTER_FORWARD_ON_404` as shown in the next section.

A project using mostly JAX-RS can keep the Jersey servlet with its own mapping, which is simpler than filter/fallback.

## 8. Jersey Filter Mode: Coexisting with Spring MVC

Jersey `ServletContainer` also implements Jakarta Servlet `Filter`. Spring Boot selects filter mode via:

~~~properties
spring.jersey.type=filter
~~~

In this mode auto-configuration creates a registration bean named:

~~~text
jerseyFilterRegistration
type: FilterRegistrationBean<ServletContainer>
~~~

The filter's order can be set via:

~~~properties
spring.jersey.filter.order=0
~~~

**This is the order in the servlet filter chain**, not the matching order between JAX-RS resources and Spring MVC controllers. If the app has security, encoding, tracing, or request wrapper filters, test the actual order; do not tweak `order` arbitrarily just to "make 404 go away."

### 8.1. ResourceConfig Must Enable fallback-on-404 When Filter Is at /*

Following Spring Boot's guide for running Jersey alongside Spring MVC, configure:

~~~java
import org.glassfish.jersey.server.ResourceConfig;
import org.glassfish.jersey.servlet.ServletProperties;
import org.springframework.stereotype.Component;

@Component
public class JerseyConfig extends ResourceConfig {
    public JerseyConfig() {
        register(GreetingResource.class);
        property(ServletProperties.FILTER_FORWARD_ON_404, true);
    }
}
~~~

When Jersey handles a request in the filter and the result is a **404 with no entity body**, this property allows forwarding the request to the **next filter/underlying servlet** so another framework can process it. Before forwarding, Jersey may reset the response status as described in Jersey's documentation.

**Important limitations:**

- Only meaningful when Jersey runs as a **Filter**, not as a Servlet.
- The default of `FILTER_FORWARD_ON_404` is `false`.
- It is **not** a fallback for every 404 response: if a resource/`ExceptionMapper` produces a 404 with an entity body, behavior can differ.
- JAX-RS sub-resource locators or application code may have already executed before Jersey decides there is no match; do not attach side effects to pure routing operations.
- If no servlet behind it handles the request, forwarding still cannot produce an endpoint; a Spring MVC `DispatcherServlet` or suitable default servlet is needed.

### 8.2. Variant B: Running Jersey Filter Alongside Spring MVC

Starting from Project A, add the Spring MVC dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jersey'
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Update `application.properties` so the Jersey filter applies to the application root, allowing MVC to receive URLs Jersey does not handle:

~~~properties
server.port=8080
server.servlet.context-path=/shop

spring.jersey.type=filter
spring.jersey.application-path=/
spring.jersey.filter.order=0
~~~

In `JerseyConfig` (which had `@ApplicationPath("/api")` from Project A), the Spring Boot property `spring.jersey.application-path=/` **overrides** it to root. Add `property(ServletProperties.FILTER_FORWARD_ON_404, true)` to the config constructor:

~~~java
// Snippet inside existing JerseyConfig constructor:
register(GreetingResource.class);
property(ServletProperties.FILTER_FORWARD_ON_404, true);
~~~

Resource `@Path("/greetings")` now has the route:

~~~text
http://localhost:8080/shop/greetings
~~~

Create a new Spring MVC controller inside a component-scanned package:

`src/main/java/demo/jersey/MvcHelloController.java`:

~~~java
package demo.jersey;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MvcHelloController {
    @GetMapping("/mvc/hello")
    public String hello() {
        return "Hello from Spring MVC";
    }
}
~~~

With `FILTER_FORWARD_ON_404=true`, when calling:

~~~bash
curl -i http://localhost:8080/shop/mvc/hello
~~~

Jersey has no JAX-RS resource `/mvc/hello`; the Jersey filter yields the request to `DispatcherServlet`. Expected HTTP 200:

~~~text
Hello from Spring MVC
~~~

Whereas:

~~~bash
curl -i http://localhost:8080/shop/greetings
~~~

is handled by the Jersey filter, body:

~~~text
Hello from Jersey
~~~

**This is a mode/config change to the same project, not running both registration modes at once.** After switching to Filter, Project A's servlet test URLs (`/shop/api/greetings`) are no longer valid; update test profiles/URIs accordingly. If Spring Security or custom filters are present, re-test auth/CSRF, filter order, and error responses.

### 8.3. When Is forward-on-404 Not Needed?

If the Jersey filter is mapped only to a **separate** prefix like `/jaxrs/*` and Spring MVC handles URLs outside that prefix, `/mvc/hello` requests do not pass through the Jersey filter. In that case `FILTER_FORWARD_ON_404` is not necessary for separating the two namespaces.

With a `/*` filter mapping where Jersey and MVC share the root, forward-on-404 is the model to consider. The tradeoff is more complex routing, namespace collision risk, and harder-to-predict error cases.

### 8.4. When Only Jersey Filter Is Present Without a Downstream Servlet

According to Spring Boot documentation, the Jersey filter requires **a servlet to handle requests that Jersey does not accept**. If the app has no suitable servlet, you can enable the container's default servlet when genuinely needed:

~~~properties
server.servlet.register-default-servlet=true
~~~

This is unnecessary if Spring MVC `DispatcherServlet` is already present. Do not enable the default servlet merely to "get rid of 404s" without reviewing static-resource exposure and security policies.

## 9. Comparing Three Path Configuration Techniques

A system can configure paths via code, properties, or registration beans:

### 9.1. @ApplicationPath

~~~java
@Component
@ApplicationPath("/jaxrs")
public class JerseyConfig extends ResourceConfig {
    public JerseyConfig() {
        register(GreetingResource.class);
    }
}
~~~

Use when you want the base URI defined at the code/module level. At container root, `@Path("/greetings")` becomes `/jaxrs/greetings`. With context path `/shop`, it becomes `/shop/jaxrs/greetings`.

### 9.2. spring.jersey.application-path

~~~properties
spring.jersey.application-path=/api/v2
~~~

When present, this property **overrides** `@ApplicationPath` on `ResourceConfig`. Useful for staging, versioned routing, migrations, or per-environment paths. Remember to test reverse proxies and client SDKs, since changing the path changes the public API contract.

### 9.3. Custom ServletRegistrationBean/FilterRegistrationBean

When default auto-registration is insufficient, you can register `ServletContainer` manually. Spring Boot supports overriding exact bean names:

- `jerseyServletRegistration` in Servlet mode;
- `jerseyFilterRegistration` in Filter mode.

**Advanced illustrative example**: only use when intentionally **replacing** auto-registration; do not combine with Example A if already using properties/annotations as the mapping source.

~~~java
import org.glassfish.jersey.server.ResourceConfig;
import org.glassfish.jersey.servlet.ServletContainer;

import org.springframework.boot.web.servlet.ServletRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ManualJerseyServletRegistration {
    @Bean(name = "jerseyServletRegistration")
    ServletRegistrationBean<ServletContainer> jerseyServletRegistration(
            ResourceConfig config) {

        ServletContainer servlet = new ServletContainer(config);

        ServletRegistrationBean<ServletContainer> registration =
                new ServletRegistrationBean<>(servlet, "/custom/*");

        registration.setName("customJerseyServlet");
        registration.setLoadOnStartup(1);
        return registration;
    }
}
~~~

Assuming servlet context `/shop` and resource `@Path("/greetings")`, the custom mapping `/custom/*` produces a URL like `/shop/custom/greetings`.

**Warning:** when registering manually, you are responsible for mapping, initialization, URL ownership, security, and duplicate registrations. Do not add this bean if you are already using `@ApplicationPath` + property to create the same registration at another path without understanding Boot's backoff behavior. Prefer auto-config and properties first.

Similarly, for Filter mode you can provide a `FilterRegistrationBean<ServletContainer>` named `jerseyFilterRegistration` to set URL patterns/order in code. However, to switch Servlet ↔ Filter in most applications, `spring.jersey.type` and `spring.jersey.filter.order` suffice; avoid manual registration unless truly required.

## 10. ResourceConfig: Registering Resources, Providers, and Features

`ResourceConfig` does not just hold endpoints. It is also where you register:

- JAX-RS resources with `@Path`.
- `ExceptionMapper<T>` to return controlled error responses.
- `ContainerRequestFilter` / `ContainerResponseFilter` for Jersey request/response logic.
- `MessageBodyReader` / `MessageBodyWriter` and JSON providers when needed.
- Jersey/JAX-RS features, properties, and resource lifecycle customizations.

Example:

~~~java
@Component
@ApplicationPath("/api")
public class JerseyConfig extends ResourceConfig {
    public JerseyConfig() {
        register(GreetingResource.class);
        register(TraceHeaderFilter.class);
    }
}
~~~

`TraceHeaderFilter` must be an implemented provider. The following is a standalone provider file:

~~~java
package demo.jersey;

import java.io.IOException;

import jakarta.ws.rs.container.ContainerRequestContext;
import jakarta.ws.rs.container.ContainerResponseContext;
import jakarta.ws.rs.container.ContainerResponseFilter;
import jakarta.ws.rs.ext.Provider;

@Provider
public class TraceHeaderFilter implements ContainerResponseFilter {
    @Override
    public void filter(
            ContainerRequestContext request,
            ContainerResponseContext response) throws IOException {

        response.getHeaders().add("X-Jersey-Lab", "active");
    }
}
~~~

With `register(TraceHeaderFilter.class)`, responses from Jersey resources include `X-Jersey-Lab: active`. This is a **JAX-RS response filter inside Jersey**, distinct from a container-registered Jakarta Servlet `Filter` and from Spring MVC `HandlerInterceptor`.

**Distinguishing filters by layer:**

| Filter | Type | Registration |
| --- | --- | --- |
| `ContainerRequestFilter` / `ContainerResponseFilter` | Jersey/JAX-RS | `ResourceConfig.register` |
| `jakarta.servlet.Filter` | Servlet web runtime | Servlet `FilterRegistrationBean`/`@WebFilter` |
| Jersey `ServletContainer` when `spring.jersey.type=filter` | Jersey acting as Servlet Filter | Spring Boot `jerseyFilterRegistration` |
| Spring Security `FilterChainProxy` | Servlet security filter group | Spring Security integration |

Do not use `ResourceConfig.register` to "install" a Servlet Filter without a matching adapter mechanism.

### 10.1. Registering a JSON Provider

If the API returns JSON DTOs instead of `text/plain`, ensure Jersey has a suitable **JAX-RS MessageBodyWriter** (for example Jersey Jackson integration). Having Jackson via `spring-boot-starter-web` does not mean every JAX-RS serialization setup automatically matches Spring MVC `MappingJackson2HttpMessageConverter`.

You can add the Jersey JSON provider dependency/`JacksonFeature` matching the Spring Boot–managed version and register it in `ResourceConfig`. When testing, verify `Content-Type: application/json`, POJO/record serialization, 406/415 errors, custom modules, and date/locale fields. **Do not mix Jersey/Jackson versions by forcing an older Jakarta-incompatible artifact.**

### 10.2. ResourceConfigCustomizer

Spring Boot 3.x allows beans implementing `org.springframework.boot.autoconfigure.jersey.ResourceConfigCustomizer` to add customizations before Jersey uses the config. **Illustrative snippet**:

~~~java
import org.glassfish.jersey.server.ResourceConfig;
import org.springframework.boot.autoconfigure.jersey.ResourceConfigCustomizer;
import org.springframework.stereotype.Component;

@Component
public class JerseyLabCustomizer implements ResourceConfigCustomizer {
    @Override
    public void customize(ResourceConfig config) {
        config.property("jersey.config.server.response.setStatusOverSendError",
                        true);
    }
}
~~~

This adds properties without modifying the original `ResourceConfig` class directly. Only choose `ResourceConfigCustomizer` when modular customization is needed; in small applications, registering directly in the constructor is usually clearer. Imports/packages in Spring Boot 4.x may differ from Boot 3.x, so keep dependencies/versions consistent.

## 11. Security When Combining Jersey and Spring Security

Spring Security can protect **both Jersey Servlet/Filter and Spring MVC** at the Servlet filter layer if registrations and matching are configured properly. However:

- Jersey `@Path` **is not equivalent** to `@GetMapping` for Spring MVC security matchers inferring path ownership.
- Jakarta REST `@RolesAllowed` should not be assumed to act as Spring method security automatically without explicit integration.
- Do not rely on CORS/Servlet mappings as authorization mechanisms. Non-browser clients can call APIs directly.
- User/token/session authentication must occur before processing data; services must still check owner/tenant/resource permissions.

**Illustrative** configuration example when adding `spring-boot-starter-security`, assuming Jersey base `/api` and public URL `/api/greetings`:

~~~java
@Bean
SecurityFilterChain security(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/greetings").permitAll()
            .requestMatchers("/api/**").authenticated()
            .anyRequest().denyAll());

    http.httpBasic(Customizer.withDefaults());
    return http.build();
}
~~~

This is a **snippet**, not part of runnable Lab A. Running it requires a `@Configuration` class, imports, `@Bean`, and identity provider/password encoder setup. Matchers in Spring Security typically evaluate paths **relative to the Servlet context path**, so `/shop` must not be arbitrarily included in `requestMatchers("/api/**")`. When multiple servlets exist, MVC-specific matchers may need explicit servlet path/matcher types: **test over HTTP using the exact path**.

For Spring Security method-level authorization on Jersey endpoints, Spring Boot documentation highlights configuring response handling so Jersey uses `setStatus(int)` rather than `sendError(int)`, allowing Spring Security to handle authentication/authorization errors before the response commits:

~~~java
// Snippet inside ResourceConfig constructor:
property("jersey.config.server.response.setStatusOverSendError", true);
~~~

Do not treat this property as a replacement for authentication/authorization; it ensures **compatibility between Jersey status/error handling and Spring Security**.

### CORS and CSRF

If a frontend at `https://app.example.test` calls a Jersey API at `https://api.example.test`, browsers enforce CORS. CORS policy can be configured on Jersey resources/providers, servlet filters, reverse proxies, or a suitable Spring component — **choose one policy owner** to avoid emitting duplicate or conflicting `Access-Control-Allow-Origin` headers.

When browsers use cookies/sessions, CSRF still requires evaluation (`SameSite`, `Secure`, CSRF tokens). `spring.jersey.type=filter` does not automatically make CORS preflight or CSRF safe. If the Jersey filter handles `OPTIONS` before Spring Security, filter ordering can interfere; test both preflight and actual requests through the proxy/security chain.

## 12. Context Path, Forwarded Headers, and Reverse Proxies

### Context Path Is Not Application Path

~~~properties
server.servlet.context-path=/shop
spring.jersey.application-path=/rest
~~~

Given `@Path("/greetings")`:

~~~text
URL inside the application:
    /shop/rest/greetings

server.servlet.context-path:
    /shop

Jersey base path:
    /rest

Resource @Path:
    /greetings
~~~

If a reverse proxy exposes:

~~~text
https://example.test/services/rest/greetings
~~~

but forwards to Spring at:

~~~text
http://localhost:8080/shop/rest/greetings
~~~

then public/internal mapping is determined by the reverse proxy rewrite. **Do not automatically add `/services` to `server.servlet.context-path`** if the proxy already strips or rewrites the prefix, or you will get a double prefix.

Spring Boot supports handling `Forwarded`/`X-Forwarded` headers via:

~~~properties
# Only enable according to a trusted proxy design:
server.forward-headers-strategy=framework
~~~

or `native` depending on the container/proxy. Never trust arbitrary `X-Forwarded-Host`/`X-Forwarded-Proto` headers from Internet clients; the edge gateway must strip/overwrite them before the app trusts them. Redirects, absolute URLs, OAuth2 callbacks, and `Secure` cookies can all break if scheme/host are wrong.

### Routing Multiple Applications Under the Same Hostname

A common architecture:

~~~text
https://example.test/mvc/**     -> Spring MVC DispatcherServlet
https://example.test/rest/**    -> Jersey ServletContainer
https://example.test/assets/**  -> static resource handler/CDN
~~~

This is an easily observable way to separate namespaces. When Jersey runs as a Servlet, trying to map `/*` for everything and hoping MVC handles 404s afterward is risky. If a shared root prefix with fallback is truly required, use a filter + `FILTER_FORWARD_ON_404` and test the exact semantics.

## 13. Executable JAR/WAR Packaging and Scanning Risks

Jersey has limited package scanning capabilities in certain Spring Boot executable archives. In an IDE, class files sit directly on the filesystem; once built, they may reside under `BOOT-INF/classes` and nested JARs inside a Boot executable JAR. In an executable WAR, they can also sit under `WEB-INF/classes`. Calling `packages("demo.jersey")` may work in the IDE yet miss resources when packaged.

Recommendation:

~~~java
public class JerseyConfig extends ResourceConfig {
    public JerseyConfig() {
        register(GreetingResource.class);
        register(TraceHeaderFilter.class);
    }
}
~~~

Register resource/provider classes explicitly. For large projects, create a registry module containing a reviewed class list or an organized `ResourceConfigCustomizer`; do not rely on unsupported reflection classpath scanning in the target packaging.

Test both paths:

~~~bash
./gradlew test
./gradlew bootJar
java -jar build/libs/jersey-servlet-lab-1.0.0.jar
~~~

With `version = '1.0.0'` and `rootProject.name = 'jersey-servlet-lab'`, the filename usually follows `jersey-servlet-lab-1.0.0.jar`; if Gradle configures a different artifact name/version, use the actual JAR name.

After starting the packaged JAR, call:

~~~bash
curl -i http://localhost:8080/shop/api/greetings
~~~

If IDE tests pass while the JAR returns 404, inspect `ResourceConfig.register` and classpath/packaging before changing controller paths.

## 14. 404, 405, 406, 415 Errors and Servlet Mapping Conflicts

| HTTP status | Common Meaning | Check in Jersey |
| --- | --- | --- |
| **404 Not Found** | URL does not match resource or handled by another servlet/framework | context path, application path, `@Path`, registered classes, servlet/filter mode |
| **405 Method Not Allowed** | Resource path matches but HTTP method is unsupported | `@GET`/`@POST`/`@PUT`, method selection |
| **406 Not Acceptable** | Cannot satisfy client `Accept` | `@Produces`, Jersey providers |
| **415 Unsupported Media Type** | Request content type is incompatible | `@Consumes` and `Content-Type` |
| **400 Bad Request** | Input/parameter conversion or validation failed | `@PathParam`, query, DTO/body |
| **500 Internal Server Error** | Jersey init/provider/DI/business exception | server stack trace, DI, missing serializer |
| **401 Unauthorized** | Unauthenticated, possibly from Spring Security | `SecurityFilterChain`, entry point |
| **403 Forbidden** | Authorization/CSRF/CORS/filter denial | security filter order, policies |

**A 404 does not always have the same cause.** If Jersey Servlet mapping `/*` captures `/mvc/hello`, Jersey can return 404 before `DispatcherServlet` ever runs. If the Jersey filter has forward-on-404 enabled, the request can continue to MVC and return 200. If the base path is wrong, the request never reaches Jersey at all.

### Three Classic URL Mistakes

**Mistake A — forgetting the context path.**

~~~properties
server.servlet.context-path=/shop
spring.jersey.application-path=/rest
~~~

Calling `/rest/greetings` omits `/shop` → fails to match context.

**Mistake B — doubling the prefix.**

~~~java
@ApplicationPath("/api")
@Path("/api/greetings")
~~~

The actual URL becomes `/api/api/greetings`, not `/api/greetings`. For a single `/api` prefix, the resource should be `@Path("/greetings")`.

**Mistake C — property overrides annotation unexpectedly.**

~~~java
@ApplicationPath("/v1")
~~~

~~~properties
spring.jersey.application-path=/v2
~~~

Spring Boot picks `/v2`. Requests to `/v1/...` no longer match as expected.

### 404 with a Body and Filter Fallback

According to Jersey's `ServletProperties.FILTER_FORWARD_ON_404`, only when Jersey produces a **404 with no entity body** does it forward to the next filter/servlet. If the application writes an `ExceptionMapper<NotFoundException>` returning a JSON error alongside 404, it can **prevent fallback**. Do not "fix" this by swallowing all 404s and forwarding if doing so leaks unintended endpoints; separating namespaces clearly is much better.

## 15. When to Choose Servlet vs. Filter?

| Criterion | Jersey Servlet | Jersey Filter |
| --- | --- | --- |
| Property | `spring.jersey.type=servlet` | `spring.jersey.type=filter` |
| Auto bean | `jerseyServletRegistration` | `jerseyFilterRegistration` |
| Servlet/filter layer | Jersey is a container-dispatched servlet | Jersey executes inside the filter chain |
| Mapping | Default `/*`, should set prefix | Filter URL patterns/order per configuration |
| Alongside Spring MVC | Easiest when separating Jersey and MVC prefixes | Can yield requests via forward-on-404 |
| Fallback after Jersey 404 | Servlet does not auto-dispatch to another servlet | Can forward if `FILTER_FORWARD_ON_404=true` and 404 has no entity |
| Filter ordering | Not an issue for the Jersey adapter as a servlet | `spring.jersey.filter.order` and interactions with security/other filters |
| Init property | `spring.jersey.servlet.load-on-startup` | `spring.jersey.filter.order` |
| Resource/provider definitions | `ResourceConfig` | Same `ResourceConfig` |
| Downstream servlet needed | Not in the fallback sense | Yes; requires MVC/default servlet for paths Jersey does not handle |
| Simplicity | Usually simple for JAX-RS APIs with their own namespace | More complex when sharing root with MVC |

**Practical guidance:**

- A standalone Jersey API: **Servlet mode**, explicit base path `/api`.
- Alongside Spring MVC with separate namespaces: use a dedicated Jersey Servlet mapping like `/jaxrs/*` and Spring MVC at `/mvc/**`.
- Need Jersey in front of routes with fallback to Spring MVC: **Filter mode** + `FILTER_FORWARD_ON_404`, backed by strong integration tests.
- No specific reason to switch to filter: keep the default servlet, fewer moving parts.

## 16. Debugging with Logging and HTTP Integration Tests

You can enable logging on the `web` group to inspect registered servlet/filter patterns, per Spring Boot docs:

~~~properties
logging.level.web=debug
~~~

For deeper troubleshooting, temporarily enable logs for these packages:

~~~properties
logging.level.org.springframework.boot.autoconfigure.jersey=DEBUG
logging.level.org.glassfish.jersey=DEBUG
logging.level.org.springframework.web=DEBUG
~~~

Only enable DEBUG temporarily in dev/staging and control logging of PII/tokens. Do not assume every Jersey module emits identical messages across all versions.

Debugging checklist:

1. Is the `spring-boot-starter-jersey` dependency present?
2. Is **one `ResourceConfig` Spring bean** loaded by Boot?
3. Does `ResourceConfig` register the right resource/provider classes?
4. Does the JAX-RS resource have appropriate `@Path` and `@GET`/`@POST`/`@Produces`/`@Consumes`?
5. Is `jakarta.ws.rs` used instead of `javax.ws.rs` on Boot 3?
6. Is Jersey type servlet or filter? Which auto registration bean was created?
7. What are the current servlet context path and Jersey application path? Does a property override `@ApplicationPath`?
8. Does the actual HTTP URL from browser/proxy have the right prefix and trailing slash?
9. If Jersey + MVC, is there a conflict between `/*` and `DispatcherServlet` `/`?
10. In filter mode, are `FILTER_FORWARD_ON_404`, a target servlet, and an entity-less 404 all present?
11. Is a filter/security rule blocking `OPTIONS`, `GET`, or `POST` before Jersey handles it?
12. Does the executable JAR discover resources the same way as in the IDE?
13. If 406/415 occurs, inspect media types and JSON providers instead of changing URLs randomly.
14. Are there regression tests running through an embedded HTTP server, not only Spring MVC controller tests?

### cURL for Wrong POST or Media Type

Lab resource `@Consumes(TEXT_PLAIN)`:

~~~bash
curl -i -X POST http://localhost:8080/shop/api/greetings \
  -H "Content-Type: application/json" \
  --data '{"message":"hi"}'
~~~

Expected **415 Unsupported Media Type**, because the POST resource accepts `text/plain`, not JSON. Do not fix this by removing `@Consumes` to accept arbitrary bodies if the app requires strict schemas/validation.

`@Produces(TEXT_PLAIN)` while client sends:

~~~bash
curl -i http://localhost:8080/shop/api/greetings \
  -H "Accept: application/xml"
~~~

may receive **406 Not Acceptable** when no acceptable representation exists. `curl` without an explicit `Accept` header typically accepts any media type; when debugging, always record exact headers.

## 17. Testing When Deployed Alongside Spring MVC

An integration test running a real container should prove:

~~~text
Jersey:
  GET /shop/greetings -> 200, "Hello from Jersey"

Spring MVC:
  GET /shop/mvc/hello -> 200, "Hello from Spring MVC"

Jersey has no route:
  GET /shop/other -> not wrongly held by Jersey;
                     resolved ultimately by MVC/default servlet

Invalid:
  POST /shop/greetings with application/json -> 415

Security:
  Private APIs are not bypassed when using filter mode
~~~

JUnit example with Spring Boot random port (using the **filter variant/profile** from Section 8):

~~~java
@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class MixedRoutingTest {
    @Autowired
    TestRestTemplate rest;

    @Test
    void jerseyAndMvcBothRespond() {
        ResponseEntity<String> jersey =
                rest.getForEntity("/shop/greetings", String.class);

        ResponseEntity<String> mvc =
                rest.getForEntity("/shop/mvc/hello", String.class);

        assertThat(jersey.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(jersey.getBody()).isEqualTo("Hello from Jersey");

        assertThat(mvc.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(mvc.getBody()).isEqualTo("Hello from Spring MVC");
    }
}
~~~

This is a **test snippet** requiring the package/imports from `JerseyServletTest` in Section 6 and the MVC starter in Gradle. Do not drop it into servlet-only Project A expecting the MVC controller to exist; it is intended for the **variant switched to filter with `MvcHelloController` added**.

Testing both frameworks thoroughly matters more than verifying a single HTTP 200 from Jersey. When `spring.jersey.application-path` varies across environments, use dedicated test profiles/configs and assert the expected URL for each profile.

## 18. Manual Filter/Servlet Registration: Avoiding Double Registration

Servlet `ServletContainer` and Filter `ServletContainer` both package the same Jersey runtime, and Spring Boot supports picking **one mode**. Common mistakes when customizing:

- Creating both a `ServletContainer` bean and a separate `ServletRegistrationBean`, causing the same servlet to be registered twice.
- Letting Boot auto-create `jerseyServletRegistration` while also registering a custom one on the same URL.
- Naming a custom bean something other than `jerseyServletRegistration`/`jerseyFilterRegistration` so Boot does not back off as expected.
- Combining `@ApplicationPath`, property path, and custom URL patterns without knowing which actually controls the mapping.
- Registering the same JAX-RS resource class multiple times under different scopes, causing confusing DI, lifecycle, or provider behavior.
- Changing filter order ahead of Spring Security without testing authorization/CORS/CSRF.
- Switching Servlet to Filter while forgetting to ensure `DispatcherServlet`/default servlet sits behind it.

**Prefer a maintainable workflow:** starter → one `ResourceConfig` bean → explicit registrations → one base path → one mode → HTTP tests. Only use manual `ServletRegistrationBean`/`FilterRegistrationBean` for special URL/lifecycle needs that properties cannot satisfy.

If you only need to adjust init parameters, simple properties work:

~~~properties
# Jersey init-param key/value supplied through Boot configuration:
spring.jersey.init.example-key=example-value
~~~

This merely illustrates the `spring.jersey.init.*` syntax, **not** a meaningful Jersey option unless a module handles `example-key`. Real features require valid keys from the Jersey documentation.

## 19. Self-Check Questions

**1.** You have `@Path("/hello")`, yet `/hello` returns 404. Can you conclude the resource was not compiled?

**Answer:** No. Check `ResourceConfig.register`, context path, application path, servlet/filter mapping, Spring MVC conflicts, and packaged JAR behavior.

**2.** Are `@ApplicationPath("/api")` and `spring.jersey.application-path=/rest` concatenated into `/api/rest`?

**Answer:** No. The property overrides the annotation; with context path `/shop` and resource `@Path("/hello")`, the URL is `/shop/rest/hello`.

**3.** Does `spring.mvc.servlet.path=/mvc` automatically move Jersey resources to `/mvc`?

**Answer:** No. It configures Spring MVC's `DispatcherServlet`. Jersey has its own base path.

**4.** What registration bean name does Spring Boot create by default for the Jersey servlet?

**Answer:** `jerseyServletRegistration`, of type `ServletRegistrationBean<ServletContainer>`. Jersey's default mode is servlet.

**5.** Can you just set `spring.jersey.type=filter` and assume MVC handles every unmatched Jersey route?

**Answer:** Never assume that. With a filter intercepting root, you need `FILTER_FORWARD_ON_404=true` for eligible 404s, plus a downstream servlet to receive the request.

**6.** When Jersey handles a request as a servlet at `/*` and returns 404, does it automatically fall through to `DispatcherServlet` mapped at `/`?

**Answer:** No. The Servlet container already selected a servlet by mapping; there is no automatic fallback to another servlet just because of a 404.

**7.** Why does Spring Boot recommend `register(MyResource.class)` over `packages(...)`?

**Answer:** Jersey package scanning has limitations in Boot executable archives and may miss resources inside packaged JARs/WARs.

**8.** Does `FILTER_FORWARD_ON_404` apply when Jersey runs in Servlet mode?

**Answer:** No. Per Jersey, it applies only to Filter mode.

**9.** A Jersey resource uses `@GET` and `@PathParam`; is it dispatched by Spring MVC `@GetMapping`?

**Answer:** No. Jersey/JAX-RS dispatches it; Spring MVC has its own `DispatcherServlet` and annotations. Spring can manage the bean/resource without being the HTTP dispatch framework for that resource.

**10.** After switching from Servlet to Filter, which test matters most?

**Answer:** Both Jersey and MVC paths (HTTP 200 with expected bodies), denied/missing routes, security, error handling, and proxy integration. Testing only a Jersey endpoint does not prove fallback works.

**11.** If Spring Security method-level denial in Jersey commits an early error response, which property should you inspect?

**Answer:** Per Spring Boot docs, `jersey.config.server.response.setStatusOverSendError=true` tells Jersey to use `setStatus` instead of `sendError`, allowing proper security exception translation.

**12.** Should you use a Servlet `FilterRegistrationBean` to register a Jersey `ContainerResponseFilter`?

**Answer:** Not directly: those are two different filter layers. `ContainerResponseFilter` belongs to JAX-RS and is normally registered via `ResourceConfig.register`.

## 20. Practical Project Checklist

- [ ] Clearly chose Jersey Servlet or Jersey Filter without accidentally registering both?
- [ ] `spring-boot-starter-jersey` dependency matches Boot major version/Jakarta namespace?
- [ ] `ResourceConfig` is a Spring bean and explicitly registers all resources/providers?
- [ ] Not relying on `packages(...)` where executable JARs/WARs have scanning limitations?
- [ ] JAX-RS resources have correct `@Path`, `@GET`/`@POST`, `@Produces`/`@Consumes`?
- [ ] Single primary source manages application path; team knows property overrides annotation?
- [ ] Context path + Jersey base path + resource path + method path compose correctly?
- [ ] `spring.mvc.servlet.path` clearly distinguished from Jersey base path?
- [ ] When coexisting with Spring MVC, namespaces are separated or filter fallback-on-404 is configured?
- [ ] In filter mode, downstream servlet, filter order, and error behavior are tested?
- [ ] No duplicate `ServletContainer`/registration beans?
- [ ] Real HTTP integration tests exist, covering both servlet and filter profiles if used?
- [ ] Tested from the packaged executable JAR?
- [ ] Tested auth, CSRF, CORS, and request/response filters under realistic deployment?
- [ ] Proxy path rewrites, forwarded headers, context path, and public URLs documented?
- [ ] Observed 404/405/406/415 responses without changing mappings for the wrong reason?

## 21. Official References

- [Spring Boot 3.3 — Servlet Web Applications: Jersey](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): ResourceConfig bean, registering resources, default servlet `/*`, servlet/filter registrations, init params, executable JAR scanning.
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): `spring.jersey.application-path`, `spring.jersey.type`, `spring.jersey.filter.order`, `spring.jersey.servlet.load-on-startup`, and `spring.jersey.init.*`.
- [Spring Boot 3.3 — JerseyAutoConfiguration API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jersey/JerseyAutoConfiguration.html): bean names `jerseyServletRegistration`/`jerseyFilterRegistration`, conditional auto-configuration.
- [Spring Boot 3.x — Jersey How-to](https://docs.spring.io/spring-boot/docs/3.2.x/reference/html/howto.html): `FILTER_FORWARD_ON_404` when combining with Spring MVC, `setStatusOverSendError` with Spring Security.
- [Jersey 3.x — ServletProperties API](https://eclipse-ee4j.github.io/jersey.github.io/apidocs/latest3x/jersey/org/glassfish/jersey/servlet/ServletProperties.html): `FILTER_FORWARD_ON_404`, `FILTER_CONTEXT_PATH`, `FILTER_STATIC_CONTENT_REGEX`, and 404 handling conditions.
- [Jersey 3.x — ServletContainer API](https://eclipse-ee4j.github.io/jersey.github.io/apidocs/latest3x/jersey/org/glassfish/jersey/servlet/ServletContainer.html): adapter acting as both Servlet and Filter.
- [Jersey 3.1 User Guide](https://eclipse-ee4j.github.io/jersey.github.io/documentation/latest31x/user-guide.html): deployment models, Servlet integration, and JAX-RS resources.
- [Spring Boot 3.3 — Spring Security](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html): security auto-config and method-level security.
- [Jakarta RESTful Web Services](https://jakarta.ee/specifications/restful-ws/): JAX-RS API and HTTP resource semantics.

**Key takeaway:** `ResourceConfig` decides **which resources/providers Jersey knows about**. `spring.jersey.type` decides whether Jersey is a **Servlet** or a **Filter**. `@ApplicationPath` or `spring.jersey.application-path` decides the **base path** (property takes precedence over annotation), while `server.servlet.context-path` adds the web application prefix. When coexisting with Spring MVC, prefer **separating URL namespaces** or using **Filter + FILTER_FORWARD_ON_404** with end-to-end testing.