# Jersey and JAX-RS as an HTTP Handling Alternative to Spring MVC in Spring Boot

Spring Boot is usually learned together with Spring MVC: an HTTP request arrives at `DispatcherServlet`, is routed to a `@RestController`, and returns JSON via `HttpMessageConverter`. However, Spring Boot does not require Spring MVC to build REST APIs. When you want to write REST services following the **Jakarta RESTful Web Services (formerly JAX-RS)** specification, you can choose **Jersey**, an implementation of that specification. Jersey has its own resource router, providers, exception mappers, and servlet, which Spring Boot automatically registers when configured properly.

This lesson belongs to **Spring Boot - web-runtime → Extending the Web Platform**. The hands-on section uses **Java 17, Spring Boot 3.3.13, Jersey 3.x, Maven, and embedded Tomcat**. All code in the main project uses the Jakarta **jakarta.ws.rs.*** package appropriate for Spring Boot 3; the **javax.ws.rs.*** package generally belongs to the older Jersey/JAX-RS generation and should not be mixed.

The focus is on understanding **how to choose Jersey instead of Spring MVC**, configuring **ResourceConfig**, handling routes/statuses/JSON, using Spring dependency injection, testing the real servlet instead of only MockMvc, avoiding servlet mapping conflicts, and understanding the limits of package scanning in executable JARs/WARs.

## 1. Learning Objectives and Prerequisites

After this lesson, you will be able to:

1. Distinguish that **Jakarta REST/JAX-RS is a specification**, **Jersey is an implementation**, **Spring MVC is another web framework**, and **Spring Boot provides auto-configuration/embedded runtime**.
2. Use **@Path, @GET, @POST, @PathParam, @QueryParam, @DefaultValue, @Produces, @Consumes, @Context** to write HTTP resources.
3. Create a Spring Boot Jersey REST project with **spring-boot-starter-jersey**, **ResourceConfig**, and resources annotated with **@Component**.
4. Explain why **register(MyResource.class)** is safer than package scanning via packages(...) when running executable archives.
5. Distinguish the default Jersey servlet **/*, @ApplicationPath, spring.jersey.application-path, server.servlet.context-path**, as well as servlet mode versus filter mode.
6. Produce JSON responses with status 200, **HTTP 201 Created**, 400, 404, and **Location**; map business errors with **ExceptionMapper**.
7. Write integration tests using **@SpringBootTest(RANDOM_PORT) + Java 17 HttpClient** to exercise the real Servlet/Jersey path.
8. Understand the boundary between MVC HandlerMapping/ControllerAdvice/HttpMessageConverter and Jersey resources/providers.
9. Know how to use Spring Security, CORS, validation, observations, and OpenAPI when an application runs Jersey.
10. Choose Jersey or MVC based on practical needs, not on unmeasured performance claims.

Prerequisites: Java 17, Spring Boot Maven, JSON, HTTP statuses/methods, REST, Dependency Injection, and embedded Servlet containers.

## 2. How Do Jersey, JAX-RS, and Spring MVC Differ?

### 2.1. Frequently Confused Layers

| Component | Responsibility | Example API |
| --- | --- | --- |
| **Jakarta REST (JAX-RS)** | REST programming model specification, annotations, context/provider APIs | jakarta.ws.rs.Path, GET, POST, Response |
| **Jersey** | Implementation that executes Jakarta REST | org.glassfish.jersey.server.ResourceConfig |
| **Spring MVC** | Spring's web framework for the Servlet stack | RestController, RequestMapping, DispatcherServlet |
| **Spring Boot** | Auto-configures dependencies, web server, lifecycle, and beans | SpringBootApplication, starter-jersey |
| **Servlet container** | HTTP connector, request/response, filters, and servlet lifecycle | Tomcat, Jetty, Undertow |
| **Spring Security** | Authentication/authorization at the Servlet filter and method layers | SecurityFilterChain, method security |

Flow diagram:

~~~text
Browser / curl / HTTP client
              |
              v
Embedded Tomcat / Servlet container
              |
              +-- Servlet Filter chain (security, logging, etc.)
              |
              +-- Jersey Servlet (JAX-RS path)
              |     +-- ResourceConfig registration
              |     +-- @Path resources / @GET / @POST
              |     +-- JSON providers / ExceptionMapper
              |
              +-- Spring MVC DispatcherServlet (if MVC is used)
                    +-- @RestController / @GetMapping
                    +-- HandlerMapping / HttpMessageConverter
~~~

Jersey and MVC can coexist in one JVM, but **they do not share an endpoint routing pipeline**. A Jersey `@Path` class does not automatically become a `DispatcherServlet` controller. Conversely, `@RestController` does not automatically become a Jersey JAX-RS resource without being registered.

### 2.2. JAX-RS Is the Specification; Jersey Is the Runtime

Jakarta REST defines HTTP method annotations, parameter binding, resource paths, `Response`, providers, request filters, and exception mapping. Jersey implements those rules: it receives requests from the Servlet, selects the matching resource method, processes the body, invokes the method, and builds the response.

Jersey is not the only implementation: Apache CXF and other implementations can also provide JAX-RS. Spring Boot provides a **direct starter and auto-configuration for Jersey**, whereas other implementations may require custom servlet/filter configuration.

### 2.3. Why the Jakarta Namespace Matters So Much

Spring Boot 3 is built on Jakarta EE APIs with packages **jakarta.servlet.*** and **jakarta.ws.rs.***. Legacy JAX-RS applications may still import **javax.ws.rs.Path** or Jersey 2 extensions. Annotations and types in the two namespaces are **different**, even when the class names look identical. When upgrading from Boot 2/Jersey 2 to Boot 3/Jersey 3, you must upgrade all JAX-RS imports, extensions, validation providers, and related dependencies.

~~~java
// Spring Boot 3 / Jersey 3: correct namespace.
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.core.Response;
~~~

Do not add both `javax.ws.rs-api` and `jakarta.ws.rs-api` to "fix" a `ClassNotFoundException` without understanding compatibility; doing so usually pollutes the classpath.

### 2.4. Quick Annotation Comparison

| Requirement | Spring MVC | Jakarta REST/Jersey |
| --- | --- | --- |
| HTTP handler class | @RestController | @Path |
| GET | @GetMapping | @GET |
| POST | @PostMapping | @POST |
| URL path variable | @PathVariable | @PathParam |
| Query string | @RequestParam | @QueryParam, @DefaultValue |
| Request header | @RequestHeader | @HeaderParam |
| Request cookie | @CookieValue | @CookieParam |
| JSON body | @RequestBody | Parameter + @Consumes + MessageBodyReader |
| JSON response body | Return POJO/ResponseEntity | Return POJO/Response + MessageBodyWriter |
| Status/header | ResponseEntity | jakarta.ws.rs.core.Response |
| Media type | mapping consumes/produces | @Consumes / @Produces |
| Exception mapping | @ControllerAdvice / @ExceptionHandler | ExceptionMapper / @Provider |
| Request filter | HandlerInterceptor, Servlet Filter | ContainerRequestFilter, Servlet Filter |
| Context | HttpServletRequest, Model | @Context UriInfo, HttpHeaders, SecurityContext |
| Dependency injection | Spring beans | Spring integration or HK2/Jersey |
| Testing web runtime | MockMvc or random port | Real HTTP / Jersey test framework, random port |

**Do not simply put `@ControllerAdvice` on Jersey and expect the framework to understand it**: it belongs to MVC's mechanism. With Jersey, use `ExceptionMapper` and register the provider.

## 3. Choosing Jersey or Spring MVC?

### 3.1. Reasons to Choose Jersey

Jersey is worth considering when:
- The organization or system has standardized on **JAX-RS resources** and wants uniform API code across multiple Java platforms.
- The project already has Jakarta REST providers, filters, exception mappers, and resource models.
- There is a requirement to migrate or share some endpoints on a Jersey/Jakarta EE runtime.
- The team understands Jersey/HK2/Spring integration, and the test/deployment pipeline supports it.

### 3.2. Reasons to Prefer Spring MVC

MVC is usually convenient when:
- The codebase already uses `@RestController`, `@ControllerAdvice`, Spring MVC validation, formatters, and message converters.
- The application uses server-side HTML templates, view resolution, static resource handling, or MVC-specific libraries.
- Observability, security, testing, OpenAPI, and logging tooling in the organization are already standardized on Spring MVC.
- The main requirement is simply standard JSON REST endpoints with no clear benefit from switching programming models.

### 3.3. Do Not Infer Performance from the Framework Name

There is no general conclusion that Jersey is always faster than MVC or vice versa. Benchmarks require the same JVM, Tomcat version, thread count, payload, JSON library, routing complexity, TLS, warmup, and deployment. You must measure **throughput, p95/p99 latency, CPU, GC, and memory** on realistic workloads. An endpoint returning "hello" does not reflect full application performance when running database queries and external HTTP calls.

**The architectural question to ask:** is there a portability benefit or reuse of JAX-RS APIs significant enough to outweigh the cost of introducing another web programming model?

## 4. Spring Boot Jersey Auto-Configuration

### 4.1. Starter and ResourceConfig

In Spring Boot 3.3, add the dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jersey</artifactId>
</dependency>
~~~

Spring Boot provides auto-configuration for Jersey, but you still need a **ResourceConfig bean** to register resources:

~~~java
@Component
public class JerseyConfig extends ResourceConfig {
    public JerseyConfig() {
        register(HelloResource.class);
        register(ItemsResource.class);
    }
}
~~~

This is an **illustrative skeleton**; the complete files are in the hands-on section. Spring Boot automatically registers the servlet/filter from `ResourceConfig` when the starter and web runtime conditions match.

### 4.2. Why Explicit Registration Is Crucial

Jersey has limitations when **scanning packages inside executable JARs and WARs** due to nested archives/classloaders. The Spring Boot 3.3 documentation warns that Jersey `packages(...)` may fail to discover resources inside a package of a fully executable JAR or inside **WEB-INF/classes** of an executable WAR. Therefore:

~~~java
register(GreetingResource.class);
register(ItemResource.class);
register(ItemNotFoundMapper.class);
~~~

is the recommended approach. It makes the path of resources/providers explicit and easy to verify during code review.

**Do not assume** Spring `@ComponentScan` automatically guarantees Jersey registers all `@Path` classes. Spring manages the bean lifecycle; Jersey needs to know about resource classes/providers through `ResourceConfig`. These two jobs are related but distinct.

### 4.3. ResourceConfig and Spring @Component

Declare `ResourceConfig` as **@Component** and the resources as **@Component**. Jersey has Spring integration, so resources can inject **Spring @Service/@Repository** via constructors:

~~~java
@Component
@Path("/hello")
class HelloResource {
    private final GreetingService service;

    public HelloResource(GreetingService service) {
        this.service = service;
    }
}
~~~

This is a **skeleton**, not a standalone class, because `GreetingService` is not defined here. When using Spring-managed resources, Spring determines singleton/proxy/transactional behavior. Jersey also has an HK2 injector for its providers; do not manually `new` a Spring component and expect `@Autowired` to work.

### 4.4. Jersey Is a Servlet by Default

Spring Boot 3.3 by default registers Jersey in a **ServletRegistrationBean** named **jerseyServletRegistration**, mapped to **/* unless changed**. Servlet initialization is normally lazy; you can configure **spring.jersey.servlet.load-on-startup** to catch errors early at startup.

~~~yaml
spring:
  jersey:
    type: servlet
    servlet:
      load-on-startup: 1
~~~

Spring Boot also supports registering Jersey as a **filter** via **spring.jersey.type=filter** with bean **jerseyFilterRegistration** and adjusting **spring.jersey.filter.order**. This option matters when running Jersey alongside MVC, but you should not switch to filter mode unless needed.

### 4.5. Jersey Application Path and Servlet Context Path

You can use the **@ApplicationPath("/api")** annotation on `ResourceConfig`, or the **spring.jersey.application-path: /api** property. If both are declared, the property can override the annotation value; it is best to have a single clear source of configuration.

The final URL is:

~~~text
Servlet context path + Jersey application path
  + resource class @Path + resource method @Path

Example:
/shop + /api + /items + /42
  = /shop/api/items/42
~~~

Do not repeat `/api` in every `@Path` when `@ApplicationPath` is already declared. If you use **server.servlet.context-path: /shop**, the URL gets the `/shop` prefix; do not add `/shop` into `ResourceConfig`.

## 5. A Runnable Spring Boot Jersey REST API

The demo includes:
- **GET /api/hello?name=Lan** → 200 JSON greeting.
- **GET /api/items** → 200 JSON list.
- **POST /api/items** → 201 Created and Location header.
- **GET /api/items/{id}** → 200 JSON item; non-existent ID → 404 JSON.
- POST JSON with a blank name → 400 JSON.
- Resource with **Spring DI**, Jersey **ExceptionMapper**, JSON **JacksonFeature**, and **real HTTP server** tests.

Data is stored in a `ConcurrentHashMap` inside a single JVM for learning convenience; **do not use this in place of a production database**.

### 5.1. Creating the Project

Requirements:
- Java 17+.
- Maven 3.6+ or Maven wrapper.
- Port 8080 available.
- Package **com.example.jerseydemo**.

Directory tree:

~~~text
jersey-runtime-demo/
  pom.xml
  mvnw
  mvnw.cmd
  src/main/java/com/example/jerseydemo/
    JerseyRuntimeApplication.java
    JerseyConfiguration.java
    GreetingResource.java
    Item.java
    NewItemRequest.java
    ErrorResponse.java
    ItemNotFoundException.java
    ItemNotFoundMapper.java
    ItemService.java
    ItemResource.java
  src/main/resources/
    application.yml
  src/test/java/com/example/jerseydemo/
    JerseyHttpIntegrationTest.java
~~~

Do not use `spring-boot-starter-web` in the main project: **spring-boot-starter-jersey** is the REST alternative and already brings in the corresponding Servlet web runtime. Do not use `@RestController` to avoid mixing pipelines.

### 5.2. Complete pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>jersey-runtime-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jersey</artifactId>
        </dependency>
        <dependency>
            <groupId>org.glassfish.jersey.media</groupId>
            <artifactId>jersey-media-json-jackson</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

**jersey-media-json-jackson** ensures Jersey has the corresponding Jackson JSON provider for DTOs. In some starters/versions, the provider may already be pulled in transitively; declaring it explicitly keeps the lesson transparent. Spring Boot's parent/BOM manages dependency versions; do not mix Jersey 2 into Jersey 3.

### 5.3. Main Class

**src/main/java/com/example/jerseydemo/JerseyRuntimeApplication.java**

~~~java
package com.example.jerseydemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JerseyRuntimeApplication {
    public static void main(String[] args) {
        SpringApplication.run(JerseyRuntimeApplication.class, args);
    }
}
~~~

### 5.4. ResourceConfig: The Bridge Between Jersey and Boot

**src/main/java/com/example/jerseydemo/JerseyConfiguration.java**

~~~java
package com.example.jerseydemo;

import jakarta.ws.rs.ApplicationPath;
import org.glassfish.jersey.jackson.JacksonFeature;
import org.glassfish.jersey.server.ResourceConfig;
import org.springframework.stereotype.Component;

@Component
@ApplicationPath("/api")
public class JerseyConfiguration extends ResourceConfig {

    public JerseyConfiguration() {
        register(GreetingResource.class);
        register(ItemResource.class);
        register(ItemNotFoundMapper.class);
        register(JacksonFeature.class);

        property("jersey.config.server.response.setStatusOverSendError",
                true);
    }
}
~~~

- **@Component** gives Spring Boot a `ResourceConfig` bean.
- **@ApplicationPath("/api")** sets the prefix for all Jersey resources.
- **register(...)** lists resources and providers explicitly so it does not rely on package scanning in executable JARs/WARs.
- **JacksonFeature** uses Jersey's Jackson JSON provider, not Spring MVC `HttpMessageConverter`.
- **setStatusOverSendError** helps interoperability with certain Spring Security method security behaviors if the project enables Security later; it does not add Security to the project by itself.
- Do not create multiple `ResourceConfig` beans arbitrarily; when modular configuration is needed, you can use **ResourceConfigCustomizer** per the Boot documentation.

### 5.5. GET Resource

**src/main/java/com/example/jerseydemo/GreetingResource.java**

~~~java
package com.example.jerseydemo;

import jakarta.ws.rs.DefaultValue;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.QueryParam;
import jakarta.ws.rs.core.MediaType;
import org.springframework.stereotype.Component;

@Component
@Path("/hello")
@Produces(MediaType.APPLICATION_JSON)
public class GreetingResource {
    public record Greeting(String message) { }

    @GET
    public Greeting hello(
            @DefaultValue("Java") @QueryParam("name") String name) {
        return new Greeting("Hello, " + name);
    }
}
~~~

The resource path **/hello** is appended after the application path **/api** → URL **/api/hello**. `@DefaultValue` applies when the `name` query parameter is absent; it does not mean a blank `name` is always replaced with `Java`. `@Produces` declares the JSON response media type.

### 5.6. Item.java

**src/main/java/com/example/jerseydemo/Item.java**

~~~java
package com.example.jerseydemo;

public record Item(long id, String name) { }
~~~

### 5.7. NewItemRequest.java

**src/main/java/com/example/jerseydemo/NewItemRequest.java**

~~~java
package com.example.jerseydemo;

public record NewItemRequest(String name) { }
~~~

Java records are built into Java 17. The Jersey Jackson provider converts the JSON body into a record and vice versa when the Jackson version is compatible.

### 5.8. ErrorResponse.java

**src/main/java/com/example/jerseydemo/ErrorResponse.java**

~~~java
package com.example.jerseydemo;

public record ErrorResponse(String code, String message) { }
~~~

### 5.9. ItemNotFoundException.java

**src/main/java/com/example/jerseydemo/ItemNotFoundException.java**

~~~java
package com.example.jerseydemo;

public class ItemNotFoundException extends RuntimeException {
    public ItemNotFoundException(long id) {
        super("Item " + id + " was not found");
    }
}
~~~

### 5.10. ItemService.java

**src/main/java/com/example/jerseydemo/ItemService.java**

~~~java
package com.example.jerseydemo;

import java.util.Comparator;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;

@Service
public class ItemService {
    private final ConcurrentMap<Long, Item> items =
            new ConcurrentHashMap<>();
    private final AtomicLong nextId = new AtomicLong();

    public Item create(String name) {
        long id = nextId.incrementAndGet();
        Item item = new Item(id, name);
        items.put(id, item);
        return item;
    }

    public Item find(long id) {
        Item item = items.get(id);
        if (item == null) {
            throw new ItemNotFoundException(id);
        }
        return item;
    }

    public List<Item> list() {
        return items.values().stream()
                .sorted(Comparator.comparingLong(Item::id))
                .toList();
    }
}
~~~

This is a **Spring @Service**. The Jersey resource will have this service injected by Spring. `ConcurrentHashMap` and `AtomicLong` only solve minimal concurrent access issues; state is lost on restart, is not shared across replicas, and does not guarantee transactions or persistence. Real data requires a repository, DB, constraints, and authorization.

### 5.11. ItemResource.java: JSON GET, POST 201, Location

**src/main/java/com/example/jerseydemo/ItemResource.java**

~~~java
package com.example.jerseydemo;

import java.net.URI;
import java.util.List;

import jakarta.ws.rs.Consumes;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.POST;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.PathParam;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.Context;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import jakarta.ws.rs.core.UriInfo;
import org.springframework.stereotype.Component;

@Component
@Path("/items")
@Produces(MediaType.APPLICATION_JSON)
public class ItemResource {
    private final ItemService service;

    public ItemResource(ItemService service) {
        this.service = service;
    }

    @GET
    public List<Item> list() {
        return service.list();
    }

    @GET
    @Path("/{id}")
    public Item find(@PathParam("id") long id) {
        return service.find(id);
    }

    @POST
    @Consumes(MediaType.APPLICATION_JSON)
    public Response create(
            NewItemRequest request,
            @Context UriInfo uriInfo) {

        if (request == null || request.name() == null
                || request.name().isBlank()) {
            return Response.status(Response.Status.BAD_REQUEST)
                    .type(MediaType.APPLICATION_JSON)
                    .entity(new ErrorResponse(
                        "INVALID_NAME", "name must not be blank"))
                    .build();
        }

        Item item = service.create(request.name().trim());
        URI location = uriInfo.getAbsolutePathBuilder()
                .path(Long.toString(item.id()))
                .build();

        return Response.created(location)
                .type(MediaType.APPLICATION_JSON)
                .entity(item)
                .build();
    }
}
~~~

**Key explanations:**
1. `@Path("/items")` after `@ApplicationPath("/api")` creates the URL `/api/items`.
2. `@GET list()` uses `ItemService.list()` to return `List<Item>`, serialized by the JSON provider.
3. `@GET @Path("/{id}")` receives the path ID via JAX-RS `@PathParam`.
4. `@POST @Consumes` JSON requires `Content-Type: application/json`; Jersey's `MessageBodyReader` converts the body into `NewItemRequest`.
5. `@Context UriInfo` provides the absolute request URI to generate `Location` for the newly created item.
6. `Response.created(location)` returns **HTTP 201 Created** and the **Location** header, with the `Item` entity as JSON when the provider is active.
7. Blank input is rejected with **400 Bad Request** and `ErrorResponse`, without leaking a stack trace.
8. The class is a Spring `@Component` and constructor-injects `ItemService`; do not manually instantiate the service.
9. Place validation in a separate service/validator as the app grows; it is kept inside the method here for readability.
10. Production must add size limits, auth, transactions, data persistence, and avoid exposing raw internal URLs behind a reverse proxy.

### 5.12. ExceptionMapper for 404

**src/main/java/com/example/jerseydemo/ItemNotFoundMapper.java**

~~~java
package com.example.jerseydemo;

import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import jakarta.ws.rs.ext.ExceptionMapper;
import jakarta.ws.rs.ext.Provider;

@Provider
public class ItemNotFoundMapper
        implements ExceptionMapper<ItemNotFoundException> {

    @Override
    public Response toResponse(ItemNotFoundException ex) {
        return Response.status(Response.Status.NOT_FOUND)
                .type(MediaType.APPLICATION_JSON)
                .entity(new ErrorResponse(
                    "ITEM_NOT_FOUND", ex.getMessage()))
                .build();
    }
}
~~~

**@Provider** is a JAX-RS extension annotation. **register(ItemNotFoundMapper.class)** in `ResourceConfig` is the essential step for the mapper to be used. Do not use Spring `@ControllerAdvice` and expect it to automatically catch Jersey resource errors. This mapper handles the exact type `ItemNotFoundException`; it does not replace all servlet error handling.

### 5.13. application.yml

**src/main/resources/application.yml**

~~~yaml
spring:
  application:
    name: jersey-runtime-demo
  jersey:
    type: servlet
    servlet:
      load-on-startup: 1

server:
  port: 8080
~~~

We set the application path using **@ApplicationPath("/api")**; do not also declare `spring.jersey.application-path` in YAML to avoid duplicate configuration. `load-on-startup=1` makes Jersey initialize at startup, which helps catch provider/registration errors before receiving requests. Boot registers Jersey as a Servlet by default; `type: servlet` simply makes the choice explicit.

### 5.14. Building and Running

Linux/macOS/Git Bash:

~~~bash
./mvnw clean package
java -jar target/jersey-runtime-demo-0.0.1-SNAPSHOT.jar
~~~

Windows CMD/PowerShell:

~~~text
mvnw.cmd clean package
java -jar target/jersey-runtime-demo-0.0.1-SNAPSHOT.jar
~~~

If you do not have the Maven wrapper, use:

~~~bash
mvn clean package
mvn spring-boot:run
~~~

Do not run the JAR and `spring-boot:run` simultaneously when both bind port 8080. A Jersey-only REST application does not need `@EnableWebMvc`.

## 6. Testing the API with curl and Checking Output

### 6.1. GET with a Query Parameter

~~~bash
curl -i "http://localhost:8080/api/hello?name=Lan"
~~~

Expected **200 OK**, `Content-Type: application/json`, body:

~~~json
{"message":"Hello, Lan"}
~~~

### 6.2. GET with DefaultValue

~~~bash
curl -i http://localhost:8080/api/hello
~~~

Body:

~~~json
{"message":"Hello, Java"}
~~~

If you send an empty `?name=`, do not confuse it with omitting the parameter; `DefaultValue` does not necessarily replace a blank value.

### 6.3. Initial List

~~~bash
curl -i http://localhost:8080/api/items
~~~

If the application has just started and no POST has occurred, the JSON body is typically:

~~~json
[]
~~~

### 6.4. POST to Create an Item

~~~bash
curl -i -X POST http://localhost:8080/api/items \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{"name":"Notebook"}'
~~~

When this is the first item after a fresh startup, expect **201 Created** with a `Location` similar to:

~~~http
Location: http://localhost:8080/api/items/1
~~~

and body:

~~~json
{"id":1,"name":"Notebook"}
~~~

If items already exist, the ID may be 2, 3...; do not write tests that always assert `id=1`. Host/scheme in `Location` come from request `UriInfo`; behind a reverse proxy you must configure trusted forwarded headers so internal URLs are not leaked.

### 6.5. GET Item

~~~bash
curl -i http://localhost:8080/api/items/1
~~~

If ID 1 exists, it returns **200** and JSON. In real applications, the frontend should follow the URI in `Location` rather than guessing the ID.

### 6.6. Invalid POST

~~~bash
curl -i -X POST http://localhost:8080/api/items \
  -H 'Content-Type: application/json' \
  -d '{"name":"   "}'
~~~

Expected **400 Bad Request**:

~~~json
{"code":"INVALID_NAME","message":"name must not be blank"}
~~~

### 6.7. GET Not Found

~~~bash
curl -i http://localhost:8080/api/items/-99
~~~

Expected **404 Not Found** and JSON:

~~~json
{"code":"ITEM_NOT_FOUND","message":"Item -99 was not found"}
~~~

Do not send stack traces or internal filesystem/database error details to clients.

### 6.8. Content Negotiation

When sending a POST request with **Content-Type: text/plain** to a method that only `@Consumes` JSON, Jersey may return **415 Unsupported Media Type**. When sending a GET with **Accept: application/xml** where the method only `@Produces` JSON, it may return **406 Not Acceptable**. An unsupported HTTP verb (for example PUT on `/api/items`) may return **405 Method Not Allowed**.

**Accept** is the response type the client accepts; **Content-Type** is the request body type being sent. Both belong to JAX-RS provider selection, not to an MVC `HttpMessageConverter` in this demo project. Default error body formats can vary by Jersey version; test the status contract and the app-defined public error schema rather than matching raw server headers verbatim.

## 7. Testing Jersey with a Real Embedded HTTP Server

### 7.1. Why Not Use MockMvc as the Primary Test?

**MockMvc** runs **Spring MVC DispatcherServlet** logic and does not execute Jersey Servlet routing. `@WebMvcTest`/`MockMvc` tests can return 404 for a `@Path` resource even when the production Jersey application works properly. Proper Jersey tests should start a real Servlet runtime, such as **@SpringBootTest(webEnvironment=RANDOM_PORT)**, and send HTTP requests using Java `HttpClient` or `TestRestTemplate`.

Real server tests help detect:
- `ResourceConfig` missing resource/provider registration.
- Wrong servlet mapping or duplicated application path.
- Missing JSON `MessageBodyReader`/`Writer`.
- Incorrect 201/`Location` responses.
- Servlet filters/security/proxy-related behavior when configured.

### 7.2. Complete Test Class

**src/test/java/com/example/jerseydemo/JerseyHttpIntegrationTest.java**

~~~java
package com.example.jerseydemo;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class JerseyHttpIntegrationTest {

    @LocalServerPort
    int port;

    private final HttpClient http = HttpClient.newHttpClient();
    private final ObjectMapper mapper = new ObjectMapper();

    private URI uri(String path) {
        return URI.create("http://localhost:" + port + path);
    }

    private HttpResponse<String> send(HttpRequest request)
            throws Exception {
        return http.send(request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
    }

    @Test
    void helloReturnsJson() throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                uri("/api/hello?name=Lan"))
                .header("Accept", "application/json")
                .GET().build();

        HttpResponse<String> response = send(request);
        assertEquals(200, response.statusCode());

        JsonNode body = mapper.readTree(response.body());
        assertEquals("Hello, Lan",
                body.path("message").asText());
    }

    @Test
    void postCreatesItemAndGetReadsIt() throws Exception {
        HttpRequest create = HttpRequest.newBuilder(
                uri("/api/items"))
                .header("Content-Type", "application/json")
                .header("Accept", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(
                        "{\"name\":\"Notebook\"}"))
                .build();

        HttpResponse<String> created = send(create);
        assertEquals(201, created.statusCode());

        JsonNode body = mapper.readTree(created.body());
        long id = body.path("id").asLong();
        assertTrue(id > 0);
        assertEquals("Notebook", body.path("name").asText());

        String location = created.headers()
                .firstValue("Location").orElseThrow();
        assertTrue(location.endsWith("/api/items/" + id));

        HttpRequest read = HttpRequest.newBuilder(
                URI.create(location)).GET().build();
        HttpResponse<String> found = send(read);

        assertEquals(200, found.statusCode());
        JsonNode item = mapper.readTree(found.body());
        assertEquals(id, item.path("id").asLong());
        assertEquals("Notebook", item.path("name").asText());
    }

    @Test
    void blankNameReturns400() throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                uri("/api/items"))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(
                        "{\"name\":\"  \"}"))
                .build();

        HttpResponse<String> response = send(request);
        assertEquals(400, response.statusCode());

        JsonNode error = mapper.readTree(response.body());
        assertEquals("INVALID_NAME",
                error.path("code").asText());
    }

    @Test
    void missingItemUsesJerseyExceptionMapper()
            throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                uri("/api/items/-99")).GET().build();

        HttpResponse<String> response = send(request);
        assertEquals(404, response.statusCode());

        JsonNode error = mapper.readTree(response.body());
        assertEquals("ITEM_NOT_FOUND",
                error.path("code").asText());
    }
}
~~~

**Test notes:**
- `@LocalServerPort` in Boot 3.3 belongs to package **org.springframework.boot.test.web.server**.
- Java 17 includes `HttpClient`; no extra HTTP test library is needed.
- The item creation test reads the ID/`Location` from the response instead of depending on test execution order.
- Negative ID `-99` cannot be generated by `AtomicLong` incrementing from 1 in the lab.
- Test the body with Jackson parsing rather than asserting raw `Date`, `Content-Length`, or header ordering.
- `RANDOM_PORT` starts a real server; the test client and HTTP server run on different threads. Do not rely on `@Transactional` on the test to automatically roll back server-side changes.
- The demo project has no DB, so in-memory state can persist across tests; tests avoid assuming the list is always empty.
- With an external proxy/HTTPS in production, you must also test the `Location` scheme/host and TLS/security behavior on the real deployment.

Run tests:

~~~bash
./mvnw test
~~~

Then test the executable JAR runtime:

~~~bash
./mvnw package
java -jar target/jersey-runtime-demo-0.0.1-SNAPSHOT.jar
~~~

Jersey package scanning can differ between the IDE, Maven, and the executable JAR. The advantage of explicit registration is that the resource list remains fixed even when the deployment classloader differs.

## 8. JSON Providers, Media Types, and DTOs

### 8.1. Jersey Does Not Use Spring MVC HttpMessageConverter

JAX-RS selects a **MessageBodyReader** to parse the request body and a **MessageBodyWriter** to write the response. Jersey's `JacksonFeature`/Jersey JSON dependency is the provider implementation. Spring MVC instead has **HttpMessageConverter**, which is a different mechanism. Even though the application uses a Spring Boot `ObjectMapper`, **do not assume every MVC ObjectMapper customization automatically applies to Jersey**.

~~~text
HTTP Content-Type + Accept
          |
          v
Jersey @Consumes / @Produces
          |
          v
MessageBodyReader / MessageBodyWriter
          |
          v
JAX-RS resource method, DTO, Response
~~~

If you need date/time modules, enum serialization, schema naming, null policies, or polymorphic types, configure the Jersey JSON provider for your exact version and write HTTP contract tests. Do not assume that merely adding an MVC-style `@JsonComponent` makes Jersey discover everything.

### 8.2. 400, 405, 406, and 415 Belong to Different Layers

- **400 Bad Request**: invalid client input or unparseable request according to the contract.
- **405 Method Not Allowed**: URL/resource exists but does not accept the HTTP method.
- **406 Not Acceptable**: `Accept` is incompatible with the response media type.
- **415 Unsupported Media Type**: request `Content-Type` is incompatible with `@Consumes`/reader.
- **404 Not Found**: no matching resource/route, or domain item does not exist.

Do not write a global `ExceptionMapper<Throwable>` that returns HTTP 400 for every exception, because that masks server bugs as client errors. Map controlled domain exceptions and keep HTTP 500 for unexpected failures, with safe logging.

### 8.3. Jakarta Bean Validation

Jersey can integrate with Jakarta Bean Validation, but **it requires a compatible implementation and Jersey validation integration/provider**, such as the appropriate Jersey validation modules. Merely putting `@NotBlank` on `NewItemRequest` does not guarantee the runtime automatically invokes the validator the way you expect. The demo project validates `name` manually so no hidden dependency is assumed. Production should have:
- bean validation/constraint mapping;
- consistent message structure and i18n;
- uniform 400 responses for field errors;
- payload size limits;
- tests for invalid JSON, missing fields, Unicode, and special characters.

### 8.4. Returning JSON Does Not Guarantee a Secure API

Returning JSON can expose data if authentication/authorization is missing. You must control sensitive fields, logging, cache policies, CSRF when using session cookies, CORS for cross-origin browsers, and output sanitation. `MediaType.APPLICATION_JSON` is merely a data representation, not a security control.

## 9. ExceptionMapper, Providers, and Filters

### 9.1. Replacing @ControllerAdvice with ExceptionMapper

Jersey **@Provider ExceptionMapper<T>** handles exceptions thrown from the JAX-RS resource pipeline. In the demo project, `ItemNotFoundMapper` returns 404 JSON. Each mapper must be registered in `ResourceConfig` when reliable discovery is absent. In MVC, `@ControllerAdvice`/`@ExceptionHandler` serve an analogous purpose in a different framework; **do not use `@ControllerAdvice` to handle Jersey requests**.

### 9.2. ContainerRequestFilter

JAX-RS defines **ContainerRequestFilter** to handle requests at the Jersey layer. It can be used to record non-sensitive metadata or attach correlation context:

~~~java
@Provider
public class AuditFilter implements ContainerRequestFilter {
    @Override
    public void filter(ContainerRequestContext context)
            throws IOException {
        String method = context.getMethod();
        String path = context.getUriInfo().getPath();
        // Only log approved metadata.
    }
}
~~~

**This is a non-standalone snippet**; when adding it to a project you must import **jakarta.ws.rs.container.ContainerRequestFilter/ContainerRequestContext**, **jakarta.ws.rs.ext.Provider**, **java.io.IOException**, and register **register(AuditFilter.class)** in `ResourceConfig`. Do not log cookies, `Authorization` headers, user secrets, or full payloads.

### 9.3. ContainerResponseFilter

A provider can add response headers:

~~~java
@Provider
public class MarkerFilter implements ContainerResponseFilter {
    @Override
    public void filter(ContainerRequestContext request,
                       ContainerResponseContext response)
            throws IOException {
        response.getHeaders().add(
                "X-Demo-Framework", "jersey");
    }
}
~~~

**This is also a snippet**, requiring imports from `jakarta.ws.rs.container.*`, `jakarta.ws.rs.ext.Provider`, and `java.io.IOException`. Do not register it into the demo project if unused. Servlet Filters live outside Jersey and can apply to both MVC and Jersey; `ContainerResponseFilter` belongs solely to the Jersey pipeline.

### 9.4. Filter Ordering and @PreMatching

JAX-RS provides **@PreMatching** and **@Priority** for providers, which are different from Spring `@Order` and Servlet filter order. An HTTP request can pass through the Spring Security Servlet Filter before Jersey request filters, and only then reach the JAX-RS resource. To have a filter enforce authentication or CORS, pick the right layer and test with real requests; do not assume `@Priority(HIGH)` means running before `SecurityFilterChain`.

## 10. Dependency Injection, Lifecycle, and Thread Safety

### 10.1. @Component Matters

Spring Boot Jersey integration supports resources as **Spring @Component** beans, injected with Spring `@Service` beans. `ItemResource` receiving `ItemService` via constructor is a complete example. However, Jersey also has HK2/service locator for non-Spring providers. A provider instantiated by HK2 is not guaranteed to receive all Spring `@Autowired` injections unless properly integrated.

**Do not manually `new`** a Jersey resource that has Spring dependencies inside `ResourceConfig`. If you call `register(new Resource())`, you are responsible for its lifecycle/state/injection. Prefer `register(Resource.class)` and Spring-managed beans.

### 10.2. Singleton Resources Must Not Hold Request State

Spring `@Component` beans are normally singletons. Never keep mutable instance fields holding `currentUser` or `currentRequest`:

~~~java
@Component
@Path("/danger")
public class UnsafeResource {
    private String currentUser;
}
~~~

This is an **anti-pattern**; concurrent requests can overwrite it. Retrieve user information from the security context/request context inside the method, using local variables or properly scoped beans. Do not store `HttpServletRequest` in a singleton field for use after the request.

### 10.3. Spring @Transactional and Proxies

If a Spring service is injected through a Spring proxy, `@Transactional` works on service methods. However, internal/self-invocation calls on the same bean bypass the proxy according to Spring AOP rules. Do not assume every class created by Jersey/HK2 is managed by Spring AOP; verify transactions, caching, and method security on the real application.

### 10.4. JAX-RS Context Objects

**@Context UriInfo** provides URI and path information, used above to build the `Location` header. Other types such as `HttpHeaders`, `SecurityContext`, and Servlet request can also be injected when supported by the runtime. This is JAX-RS context injection, not Spring `@RequestParam`/`@PathVariable`, and it does not exist automatically in a plain Java program or reactive WebFlux.

## 11. Jersey Alongside Spring MVC: Managing URL Ownership

### 11.1. Default Jersey Servlet /* Can Intercept Requests

If you use `spring-boot-starter-jersey` with the default **/*** servlet mapping while also having MVC `DispatcherServlet`, Jersey can capture paths you expected Spring MVC to handle. The usual symptom is **MVC @RestController unexpectedly returning 404** or static assets never reaching the expected handler.

An easy-to-control approach is **separating namespaces**:
- Jersey: **/jaxrs/**.
- MVC: **/ui/** or **/mvc-api/**.
- Management: dedicated private port/path.
- Static resources: explicitly designed servlet/static mapping.

Set **@ApplicationPath("/jaxrs")** or `spring.jersey.application-path` as needed. **Servlet mapping is decided before framework method mapping**; the two frameworks do not divide routes automatically based on who has matching annotations.

### 11.2. Filter Mode for Fallback Coordination

If Jersey needs to run alongside another web framework using a forward-on-404 model, Spring Boot recommends:

1. Set **spring.jersey.type: filter**.
2. In `ResourceConfig`, set **ServletProperties.FILTER_FORWARD_ON_404: true**.
3. Have another Servlet (such as MVC `DispatcherServlet`) to receive requests Jersey does not handle.
4. Test filter order, forward dispatch, security, and error handling.

Example config **for the coexistence variant only**, not the main project file:

~~~yaml
spring:
  jersey:
    type: filter
    filter:
      order: 0
~~~

The corresponding `ResourceConfig` needs to import **org.glassfish.jersey.servlet.ServletProperties** and declare:

~~~java
property(ServletProperties.FILTER_FORWARD_ON_404, true);
~~~

In an app without another servlet to handle remaining requests, the Boot docs note you can enable **server.servlet.register-default-servlet: true**, though you must verify it does not accidentally expose static files. When a custom `ExceptionMapper` handles 404s, forwarding behavior can differ; test the real routes.

### 11.3. Do Not Unintentionally Mix Two JSON/Error Pipelines

When both MVC and Jersey exist in the same app:
- MVC uses `HttpMessageConverter`; Jersey uses `MessageBodyReader`/`Writer`.
- MVC `@ControllerAdvice` does not catch Jersey exceptions.
- CORS configured via `WebMvcConfigurer` does not automatically apply to the Jersey servlet.
- MVC argument converters do not automatically apply to JAX-RS `@QueryParam`.
- MVC route metrics/tags may not match Jersey route metrics.
- An OpenAPI adapter that only scans MVC controllers can miss Jersey resources.

Define a shared public API contract (statuses, JSON schema, error codes) and test both pipelines. Unless there is a specific migration or module requirement, using a single web framework is usually simpler.

## 12. Spring Security and CORS/CSRF with Jersey

### 12.1. Servlet Security Filters Can Still Protect Jersey

In a Servlet application, **Spring SecurityFilterChain** sits at the Servlet filter layer, so it can protect Jersey URLs when request matchers and filter registrations are configured properly. **@Component @Path** does not automatically make a resource an authorized endpoint; you still need authentication and authorization by path/method/resource.

Example **reference snippet** if the application has added `spring-boot-starter-security` and an authentication provider:

~~~java
@Bean
SecurityFilterChain security(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .requestMatchers("/api/**").authenticated()
            .anyRequest().denyAll())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

This snippet omits imports, user stores, and CSRF policies; do not copy it as a complete Spring Security project. When adding security to the main project, verify 401/403 responses with HTTP tests, especially with Jersey servlet/filter registration.

### 12.2. Method-Level Security Requires Attention to setStatusOverSendError

The Spring Boot Jersey how-to documentation recommends setting the Jersey property:

~~~java
property("jersey.config.server.response.setStatusOverSendError",
        true);
~~~

When using Spring Security method security, having Jersey call **setStatus** instead of **sendError** prevents committing the response too early, giving security a chance to handle authentication/authorization failures. The demo already sets this property in `ResourceConfig`, though **without `spring-boot-starter-security`** it does not enable security by itself.

If you use `@EnableMethodSecurity` and `@PreAuthorize` on Spring-managed Jersey resources/services, verify that proxies/advice actually work. Do not assume an annotation in source code protects an endpoint if Jersey instantiated the resource outside Spring's proxy.

### 12.3. CORS Does Not Replace Authentication

A request with a valid CORS `Origin` still has to pass authentication. Preflight `OPTIONS` requests usually do not carry session cookies, so CORS must handle `OPTIONS` appropriately before security authentication. **Access-Control-Allow-Origin: *** is invalid for credentialed requests carrying cookies. Never blindly reflect every `Origin` just to silence browser errors. With Jersey, CORS can live in a servlet filter, gateway, or suitable provider/filter; Spring MVC `CorsRegistry` does not automatically apply to Jersey routes.

### 12.4. CSRF When Using Cookie Sessions

If a Jersey API is called by a browser using session cookies, unsafe `POST`/`PUT`/`PATCH`/`DELETE` requests can suffer from CSRF just like in MVC. Do not disable CSRF globally just because a Jersey `POST` returns 403. Choose a synchronizer token or equivalent mechanism for session-based browser flows; if the API only uses stateless bearer tokens, evaluate the threat model separately. Spring Security is the protection layer; Jersey `@POST` does not automatically defend against CSRF.

## 13. Executable JARs, WARs, and Reverse Proxies

### 13.1. Executable JAR

Spring Boot executable JARs contain nested dependencies. Jersey package scanning is not guaranteed to find resources in every packaged layout. Therefore **explicitly registering resource classes** is an important QA safeguard, even when the app runs fine in the IDE. Test both **mvn spring-boot:run** and **java -jar** to catch differences in classloaders or servlet registration.

### 13.2. WAR and Jakarta Servlet

When packaging as a WAR:
- Switch to the appropriate packaging and manage the Servlet container dependency/scope.
- If deploying to an external servlet container, you may need **SpringBootServletInitializer** in the main application.
- The container must support **Jakarta Servlet**; do not use Tomcat 9/`javax.servlet` with Boot 3.
- Classes may reside under **WEB-INF/classes**, where Jersey package scanning still has limitations.
- Verify the final URL = deployment context + Jersey path + resource path.

The runnable project uses an executable JAR; do not assume a WAR configuration has been pre-tested.

### 13.3. Reverse Proxies and Location

HTTP 201 `Location` is constructed from `UriInfo` on the request. When Nginx/ingress terminates external HTTPS and forwards internal HTTP, the URI can have the wrong scheme/host unless forwarded headers are handled properly. Only trust **Forwarded / X-Forwarded-Proto / X-Forwarded-Host** from a trusted proxy; external clients must never be allowed to spoof headers to alter `Location` or redirects. Test against real public staging URLs.

### 13.4. Blocking Behavior

Jersey REST on an embedded Servlet container normally uses request threads. A method making blocking database or network calls holds a thread. JAX-RS provides async/SSE APIs depending on the runtime, but that does not mean every Jersey resource is non-blocking by default or equivalent to WebFlux. Analyze thread pools, connection pools, timeouts, streaming, graceful shutdown, and backpressure realistically.

## 14. Observability and API Documentation

### 14.1. Actuator/Metrics

Spring Boot Actuator can provide health, metrics, and tracing for the Servlet stack even when Jersey handles the routes. You can add the dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

This is an **extension** and is not in the demo `pom.xml`. HTTP server tags such as URI templates may differ between Jersey and MVC because `HandlerMapping` differs. Do not assume Jersey automatically attaches all MVC observation conventions. Measure metrics/traces on the real runtime, and protect Actuator endpoints with network/auth rules.

### 14.2. OpenAPI Adapters

OpenAPI is a framework-independent contract, yet endpoint scanning tools have framework-specific adapters. A starter designed to scan Spring `@RestController`/`@RequestMapping` **does not automatically scan Jersey `@Path`/`@GET`**. With Jersey, choose the appropriate JAX-RS/Jakarta integration and test that generated docs include all paths, request/response schemas, error codes, auth schemes, and versions.

### 14.3. Do Not Log Secrets in Jersey Filters

Request/response filters and tracing instrumentation should only record controlled metadata such as method, route template, status, and request ID. Avoid logging `Authorization`, cookies, bearer tokens, sensitive payloads, or unnecessary user identities. CORS/logging filters are not a place to hide security flaws.

## 15. Quick Troubleshooting

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| **404 on all Jersey routes** | `ResourceConfig` is not a bean, wrong `@ApplicationPath`, missing register | Check `@Component`, starter, `ResourceConfig` registrations, and URL. |
| **Works in IDE, 404 in packaged JAR** | `packages(...)` scanning misses classes in archive | Explicitly `register(Resource.class)`. |
| **/api/api/items** | Doubled application path | Remove duplicate prefix from `@Path`/config. |
| **MVC endpoints disappear after adding Jersey** | Jersey servlet `/*` captures routes | Separate paths, inspect servlet mappings, consider filter forwarding. |
| **POST JSON returns 415** | `Content-Type`/`@Consumes`/JSON provider mismatch | Check Jersey JSON provider and `Content-Type`. |
| **GET returns 406** | `Accept` does not match `@Produces` | Adjust `Accept` or supported representations. |
| **500 when serializing DTO** | `JacksonFeature`/provider/schema error | Register the provider and write JSON contract tests. |
| **Service is null in resource** | Resource is not a Spring bean or manually instantiated with `new` | `@Component` resource, constructor injection, register class. |
| **javax.ws.rs.Path does not work** | Legacy Jersey namespace/version | Use `jakarta.ws.rs.*` and inspect dependency tree. |
| **@ControllerAdvice does not catch errors** | Jersey does not use MVC exception resolvers | Use `@Provider ExceptionMapper`. |
| **MVC CORS config has no effect** | Jersey servlet does not use `WebMvcConfigurer` CORS pipeline | Use appropriate servlet/gateway/Jersey CORS filter. |
| **Spring Security returns unexpected 401/403** | Filter matchers, session/CSRF, method proxy, or preflight | HTTP integration tests and `ResourceConfig` property. |
| **MockMvc test misses @Path routes** | MockMvc runs MVC dispatcher | Use `@SpringBootTest(RANDOM_PORT)` + real HTTP client. |
| **Location header has wrong host/scheme** | Proxy/forwarded headers | Configure trusted proxy and test public URL. |
| **Resource works only when unpackaged** | Classloader/servlet configuration | Explicit registration and packaged smoke test. |
| **Static assets/Actuator 404** | Overlapping servlet mappings | Partition namespaces and inspect Servlet registrations. |
| **Metrics differ from MVC** | Different observability conventions | Inspect actual instrumentation/URI tags. |
| **Filter/ExceptionMapper does not run** | Provider not registered or wrong lifecycle | Register each provider and test over HTTP. |

### 15.1. Ordered Debugging Workflow

1. Check the **spring-boot-starter-jersey** dependency and Java/Jakarta API versions.
2. Verify one **ResourceConfig bean** is created by Spring.
3. Verify resource `@Component` annotations and matching class registrations.
4. Check context path + application path + class/method `@Path`.
5. Check Jersey servlet or filter registration and conflicts with MVC.
6. Check HTTP verb, `Content-Type`, `Accept`, and `@Consumes`/`@Produces`.
7. Check JSON provider and DTO serialization/deserialization.
8. Check exception mappers, providers, and filters.
9. Check Spring Security, CORS, CSRF, and authentication before the resource.
10. Build the JAR and test on a production-like deployment.

Do not try to fix Jersey routing errors by randomly tweaking `spring.mvc.pathmatch` or adding `@EnableWebMvc`: those belong to MVC and will not resolve Jersey servlet mapping causes.

## 16. Exercises

### Exercise 1: Migrate from @RestController

Convert a Spring MVC GET `/customers/{id}` using `@PathVariable` into a JAX-RS resource with `@Path`, `@GET`, and `@PathParam`. Preserve the URL and JSON contract. Convert `@ControllerAdvice` error handling into an `ExceptionMapper`, and test 200/404 via `RANDOM_PORT`.

### Exercise 2: Compare Scan vs. Register

In a copy of the lab, try replacing `register(ItemResource.class)` with `packages("com.example.jerseydemo")`. Run in IDE, Maven, and then executable JAR, comparing routes. After the experiment, restore explicit registration. Explain why scanning inside nested JARs can miss resources.

### Exercise 3: Verify 201

POST to create an item, read the `Location` response header, and use that exact URL to GET the item. Do not hardcode `ID=1`. Test `Location` when adding a Servlet context-path or running behind a reverse proxy.

### Exercise 4: Content Negotiation

Try GET with `Accept=application/xml` and POST with `Content-Type=text/plain`, observing 406/415. Distinguish `@Produces` and `@Consumes`. Write tests asserting only the HTTP status if the default error body is not part of the application contract.

### Exercise 5: Security

Add Spring Security and block POST when unauthenticated or lacking the `EDITOR` authority. If using cookie sessions, test CSRF. Do not use CORS as authorization. Test `@PreAuthorize` on the Spring-managed service over real HTTP.

### Exercise 6: Coexistence with MVC

Add a Spring MVC `@Controller` serving `/ui/hello` in an experimental copy of the lab. Determine how to make Jersey handle only `/api/*` and MVC handle `/ui/*`. If you want Jersey fallback via a filter, enable `type=filter` and `FILTER_FORWARD_ON_404` and test both. Only use the approach that fits the real architecture.

## 17. Pre-Deployment Checklist

- [ ] Clear justification for choosing JAX-RS/Jersey; team understands tradeoffs vs. Spring MVC.
- [ ] Uses Jersey 3/Jakarta namespace compatible with Boot 3; no `javax.ws.rs.*` mixing.
- [ ] `ResourceConfig` is Spring-managed, with explicit resource/provider registration.
- [ ] `@Component` and Spring service DI work; no manual `new` breaking proxies.
- [ ] `@ApplicationPath`/Servlet `context-path` do not collide or get added twice.
- [ ] Jersey servlet/filter mappings do not hijack MVC/static/management routes unexpectedly.
- [ ] JSON `MessageBodyReader`/`Writer`, `@Consumes`, `@Produces`, and DTO records are tested.
- [ ] HTTP 200, 201/`Location`, 400, 404, 405, 406, 415 are verified.
- [ ] `ExceptionMapper` and providers are registered rather than relying on MVC `@ControllerAdvice`.
- [ ] Bean lifecycles/scopes, `@Transactional`, concurrency, and request state are reviewed.
- [ ] Authentication, authorization, CORS, CSRF, and cookie policies fit the Servlet stack.
- [ ] `@SpringBootTest(RANDOM_PORT)` tests run over real HTTP, not only MockMvc.
- [ ] Tests re-run on packaged JAR/WAR and external containers if used.
- [ ] Proxy trusted forwarded headers, public `Location`, HTTPS, and context prefix are verified.
- [ ] Actuator and tracing/metrics are verified, without exposing management endpoints.
- [ ] OpenAPI tooling supports JAX-RS and generated API docs match the contract.
- [ ] No secrets logged and no stack traces returned in API responses.
- [ ] Appropriate thread/resource limits, timeouts, performance, and load tests are in place.

## 18. Self-Check Questions

**1. Are JAX-RS and Jersey the same thing?** No. Jakarta REST/JAX-RS is the specification; Jersey is the runtime implementation.

**2. Is adding the Jersey starter and writing a `@Path` class enough?** You need a `ResourceConfig` to register the resource; `@Component` should be used for Spring-managed endpoints.

**3. Why use `register(Resource.class)` instead of `packages(...)`?** Jersey package scanning has limitations in nested archives/executable WARs; explicit registration is more reliable.

**4. Is Jersey a servlet or a filter by default?** In Boot 3.3, it defaults to a servlet mapped to `/*`; switch to filter with `spring.jersey.type`.

**5. Can `@ControllerAdvice` catch `ItemNotFoundException` in Jersey?** Not by default; use an `ExceptionMapper` registered in `ResourceConfig`.

**6. Do `@GetMapping` and `@GET` share `DispatcherServlet`?** No. MVC uses `DispatcherServlet`; Jersey has its own servlet/filter and router.

**7. Is a MockMvc test enough to prove the Jersey servlet runs properly?** No; use `@SpringBootTest(RANDOM_PORT)` and a real HTTP client.

**8. When creating a resource via POST, which JAX-RS API supports status 201/`Location`?** `jakarta.ws.rs.core.Response.created(location)`.

**9. If you only need `spring-boot-starter-jersey`, is `spring-boot-starter-web` still mandatory?** No. The Jersey starter is an alternative to the Spring MVC web starter when using Jersey alone.

**10. Why might static resources or MVC endpoints 404 after adding Jersey?** Check Jersey servlet `/*` and overlapping Servlet mappings instead of only checking controller annotations.

## 19. Official Documentation

1. [Spring Boot 3.3 — Servlet Web Applications, JAX-RS and Jersey](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): ResourceConfig, @Component, explicit register, servlet/filter mapping, and executable archive scanning.
2. [Spring Boot 3.3 — Jersey How-to](https://docs.spring.io/spring-boot/3.3/how-to/jersey.html): Spring Security setStatusOverSendError and coexistence with MVC via filter-forward.
3. [Spring Boot 3.3 — Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): spring.jersey.application-path, type, filter order, load-on-startup.
4. [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): @SpringBootTest(RANDOM_PORT), embedded server, testing beyond MockMvc.
5. [Jakarta RESTful Web Services Specification](https://jakarta.ee/specifications/restful-ws/): @Path, @GET, @POST, Response, providers, filters, standard behavior.
6. [Eclipse Jersey Documentation](https://eclipse-ee4j.github.io/jersey.github.io/documentation/latest/): Jersey server runtime, resource methods, JSON, HK2, and Spring integration.
7. [Spring Security Servlet Reference](https://docs.spring.io/spring-security/reference/servlet/index.html): security filter chain, authentication/authorization.
8. [Spring Boot 3.3 — JSON](https://docs.spring.io/spring-boot/3.3/reference/features/json.html): Jackson in Spring Boot and a basis for comparing with Jersey providers.

**Conclusion:** Jersey/Jakarta REST is an **alternative to Spring MVC for REST HTTP endpoints** when a team needs the JAX-RS programming model. Spring Boot provides the starter and servlet integration, but you must explicitly register **ResourceConfig**, **@Component JAX-RS resources**, and providers, avoiding package scanning in executable archives. To build a reliable API, test over real HTTP, distinguish MVC/Jersey pipelines, manage URL ownership and filters clearly, and safeguard security, JSON contracts, packaging, and observability before deployment.