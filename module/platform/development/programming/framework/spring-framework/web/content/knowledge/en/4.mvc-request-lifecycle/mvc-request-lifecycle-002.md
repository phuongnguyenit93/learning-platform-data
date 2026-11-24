# HandlerMapping: Finding the Matching Request Handler in Spring MVC

## 1. Goals and Position in the MVC Flow

An HTTP request entering `DispatcherServlet` does not inherently know which controller method should run. **`HandlerMapping`** is the strategy that helps Spring MVC locate **the handler matching the current request**, while also providing the associated interceptor chain. Each type of `HandlerMapping` understands a different style of route declaration: annotations, manual URL mappings, functional endpoints, or static resources.

After this lesson, you will be able to:

1. Accurately explain the responsibility of `HandlerMapping` inside `DispatcherServlet` and distinguish it from `HandlerAdapter`.
2. Understand `HandlerExecutionChain`, `HandlerMethod`, and their relationship with `HandlerInterceptor`.
3. Read and predict which endpoint is selected from `@RequestMapping`, `@GetMapping`, `@PostMapping`, and conditions on path, HTTP method, params, headers, consumes, and produces.
4. Understand more-specific mapping selection rules, ordering across multiple `HandlerMapping` beans, and duplicate or missing-handler scenarios.
5. Run a Spring MVC Java 17+ example, observe results via HTTP requests, inspect registered routes, and debug 404/405/406/415 errors.

**Scope:** Spring MVC running on the Servlet stack (`spring-webmvc`), illustrating common behavior in Spring Framework 6.x / Spring Boot 3.x. Spring WebFlux has corresponding reactive dispatch classes and pipelines, which cannot be used interchangeably.

## 2. What Does `HandlerMapping` Do Inside `DispatcherServlet`?

Let us trace a request:

```text
Client: GET /api/books/42
               |
          Servlet container
               |
         DispatcherServlet
               |
      [Query HandlerMappings in turn]
               |
      HandlerExecutionChain
       + selected handler
       + 0..n interceptors
               |
        matching HandlerAdapter
               |
      invoke controller method
               |
      process return value,
      write HTTP body / render view
               |
          HTTP response
```

`HandlerMapping` performs **lookup**, and does not directly invoke business methods. At runtime, `DispatcherServlet` iterates through the configured `HandlerMapping` beans in priority order. For each mapping, it calls:

```java
HandlerExecutionChain getHandler(HttpServletRequest request)
        throws Exception;
```

This is a **conceptual signature from the `org.springframework.web.servlet.HandlerMapping` interface**, not a method you normally call directly in a controller. The result takes two main forms:

- A `HandlerExecutionChain` containing the found handler and the interceptors attached to the request.
- `null` if that specific mapping does **not** claim the request, allowing the dispatcher to ask the next mapping.

A handler may be a `HandlerMethod` representing a `@Controller` method, or another type such as an `HttpRequestHandler`, a legacy `Controller`, or a `HandlerFunction` for MVC functional endpoints. Because handlers come in multiple types, `DispatcherServlet` delegates the result to a **compatible `HandlerAdapter`** to invoke the handler.

**Core distinctions:**

| Component | Question it answers | Example |
| --- | --- | --- |
| `DispatcherServlet` | Who coordinates the entire HTTP request in Spring MVC? | Front controller |
| `HandlerMapping` | Which handler does this request belong to? | `RequestMappingHandlerMapping` |
| `HandlerExecutionChain` | Which handler was selected and which interceptors accompany it? | `HandlerMethod` + a `HandlerInterceptor` |
| `HandlerAdapter` | How to invoke the right kind of handler, resolve parameters, and handle the result? | `RequestMappingHandlerAdapter` |
| `HttpMessageConverter` | How to read/write request or response bodies by media type? | Converting a Java object to JSON |
| `ViewResolver` | If the result is a view name, how to find the view to render? | Resolving an HTML template |

Therefore, a "handler not found" error occurs at a stage before any business method is invoked; binding errors, JSON converter errors, or business exceptions can occur at other stages.

## 3. Common `HandlerMapping` Implementations

### 3.1. `RequestMappingHandlerMapping`: Annotation-Based Mapping

This is the most important mapping for annotation-based REST controllers. When the application context initializes, Spring discovers handler methods from controller beans and registers mapping metadata; during request processing, it compares the incoming request against registered conditions.

Example controller:

```java
package example.routes;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/books")
public class BookController {

    @GetMapping("/latest")
    public String latest() {
        return "latest book";
    }

    @GetMapping("/{id}")
    public String byId(@PathVariable String id) {
        return "book:" + id;
    }
}
```

Class-level `@RequestMapping("/api/books")` combines with method-level `@GetMapping`:

- `GET /api/books/latest` → `BookController.latest()`.
- `GET /api/books/42` → `BookController.byId("42")`.

When `GET /api/books/latest` arrives, both the literal pattern `/latest` and the variable `/{id}` could match that path segment, but **the more specific literal pattern takes precedence**, so handler `latest()` is chosen. This is not because `latest()` appears earlier in the source file.

The shorthand annotations `@GetMapping`, `@PostMapping`, `@PutMapping`, `@PatchMapping`, and `@DeleteMapping` are specialized forms of `@RequestMapping` scoped by HTTP method.

### 3.2. `BeanNameUrlHandlerMapping` and `SimpleUrlHandlerMapping`

These strategies are commonly encountered in traditional Spring MVC code or infrastructure:

- `BeanNameUrlHandlerMapping` can bind a URL to a bean carrying a URL-shaped name or alias; today it is rarely used directly in annotation-based REST code.
- `SimpleUrlHandlerMapping` maps URL patterns to explicitly configured handlers. Spring MVC may use mappings of this style for certain infrastructure tasks, such as serving static resources or forwarding to the default servlet depending on configuration.

The `SimpleUrlHandlerMapping` configuration snippet below is meant to help recognize the API, **not as a standalone runnable application**:

```java
SimpleUrlHandlerMapping mapping = new SimpleUrlHandlerMapping();
mapping.setUrlMap(java.util.Map.of("/health-legacy",
        (org.springframework.web.HttpRequestHandler) (request, response) -> {
            response.setContentType("text/plain;charset=UTF-8");
            response.getWriter().write("ok");
        }));
mapping.setOrder(1);
```

This snippet requires Spring MVC and Servlet imports/dependencies and must be registered by Spring as an appropriate bean. To invoke `HttpRequestHandler`, `DispatcherServlet` will need `HttpRequestHandlerAdapter`. Do not replace the entire `RequestMappingHandlerMapping` mechanism just to define a simple REST endpoint.

### 3.3. `RouterFunctionMapping`: Spring MVC Functional Endpoints

Spring MVC also provides WebMvc.fn, allowing routes to be declared with functions. `RouterFunctionMapping` finds a `RouterFunction` whose predicate matches and selects the corresponding `HandlerFunction`; `HandlerFunctionAdapter` then executes the handler.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.ServerResponse;

import static org.springframework.web.servlet.function.RouterFunctions.route;

@Configuration
public class FunctionalRouteConfig {
    @Bean
    RouterFunction<ServerResponse> greetingRoute() {
        return route()
                .GET("/functional/hello",
                        request -> ServerResponse.ok().body("hello fn"))
                .build();
    }
}
```

This is an **additional configuration class**, requiring an existing MVC application. Functional routes on the **Servlet stack** do not turn the server into WebFlux. Distinguish the two selection models:

- With annotated controllers, `RequestMappingHandlerMapping` selects the best-matching mapping based on conditions and corresponding comparators.
- Within **a composed `RouterFunction`**, functional routes are evaluated in definition order; place specific conditions before broad ones.

## 4. Criteria Spring MVC Uses to Match Requests

`@RequestMapping` and its specialized annotations can express multiple conditions. A method is selected only when **all required conditions** match, not merely because the URL looks similar.

| Condition | Example | What does it check? |
| --- | --- | --- |
| Path pattern | `@GetMapping("/{id}")` | Matching path within the application |
| HTTP method | `@GetMapping`, `@PostMapping` | GET vs POST, etc. |
| Query params | `params = "view=compact"` | Query parameters and values |
| Headers | `headers = "X-Client=mobile"` | HTTP header conditions |
| Consumes | `consumes = "application/json"` | Request body media type, typically from `Content-Type` |
| Produces | `produces = "application/json"` | Response media types producible, negotiated with `Accept` |
| Custom request condition | Extended HandlerMapping | Application-specific condition when genuinely needed |

**Important:** `Content-Type` and `Accept` have different meanings:

- `Content-Type: application/json` describes the format of **the body sent by the client**. It primarily interacts with `consumes`.
- `Accept: application/json` expresses the format **the client wants to receive**. It primarily interacts with `produces`.

Example:

```java
@PostMapping(
    path = "/orders",
    consumes = "application/json",
    produces = "text/plain"
)
public String create(@RequestBody CreateOrderRequest input) {
    return "created:" + input.id();
}
```

This is a **fragment** inside a `@RestController` with a `CreateOrderRequest(String id)` record and appropriate message converters configured. The mapping conditions require a JSON request body and a client accepting a text response. If `Content-Type` does not match, 415 may be returned; if the response media type cannot satisfy `Accept`, 406 may be returned.

### 4.1. Query Parameter Conditions

Consider:

```java
@GetMapping(path = "/reports", params = "mode=compact")
public String compact() {
    return "compact";
}

@GetMapping(path = "/reports", params = "!mode")
public String normal() {
    return "normal";
}
```

These are **two methods in the same controller**. For `GET /reports?mode=compact`, the first method matches. For `GET /reports` (without query param `mode`), the second method matches. For `GET /reports?mode=full`, neither condition above matches; in this configuration Spring may return a parameter condition error (typically HTTP 400), so **do not automatically conclude that every failure to pick a method is a 404**.

Other forms of expression:

- `params = "debug"`: parameter `debug` must be present.
- `params = "!debug"`: parameter `debug` must not be present.
- `params = "mode=compact"`: parameter must be present and match the value.
- `params = "mode!=compact"`: negation condition, following Spring's request condition semantics.

### 4.2. Header Conditions and Content Negotiation

`headers = "X-Tenant=alpha"` matches header values; `headers = "X-Tenant"` requires the header to be present. Avoid casually using `headers` instead of `consumes`/`produces` to describe media types, because the two dedicated attributes clearly represent request body format and response content negotiation.

For instance, the same URL can register different result representations using `produces`, provided no ambiguous runtime mapping is created. Clients should send an explicit `Accept` header when response format matters.

## 5. Path Matching: Literals, Variables, Wildcards, and Specificity

Spring MVC 6.x uses `PathPatternParser` by default to parse and match URL patterns. The older `AntPathMatcher` mechanism still exists in suitable configuration contexts, but **do not assume old rules automatically apply** in Spring 6.x.

Common path syntax:

| Pattern | Meaning | Matching example |
| --- | --- | --- |
| `/users/new` | Literal path | `/users/new` |
| `/users/{id}` | Single path segment capturing `id` | `/users/42` |
| `/assets/*.png` | Wildcard within one segment | `/assets/icon.png` |
| `/orders/{id:[0-9]+}` | Variable with regex constraint | `/orders/123` |
| `/assets/**` | Zero or more segments at the **end** of the pattern | `/assets/css/site.css` |
| `/files/{*path}` | Captures the remaining path at the **end** of the pattern | `/files/a/b.txt` |

With `PathPatternParser`, `**` and `{*path}` may only appear at the end of a pattern. Patterns like `/a/**/b` are invalid under that parser's rules. The regex form `{id:[0-9]+}` prevents an endpoint intended for numeric IDs from accidentally accepting arbitrary strings; **conversion from String to long** happens later during argument resolution/conversion.

Routing example:

```text
Registered:
  GET /api/products/latest  -> latest()
  GET /api/products/{id}    -> getById(id)
  GET /api/products/**      -> fallback(...)

Receive GET /api/products/latest
  -> literal /latest beats variable and wildcard patterns.

Receive GET /api/products/123
  -> /{id} is more specific than /**.

Receive GET /api/products/123/reviews
  -> /** pattern can match if a fallback is configured.
```

When comparing paths, more specific patterns generally win based on wildcards, number of URI variables, and length. However, this is **not** a "whichever method is higher in the Java file runs first" rule; comparing `RequestMappingInfo` also evaluates other request conditions.

### 5.1. External URL, Context Path, and Servlet Path

A request may pass through multiple prefixes:

```text
http://localhost:8080/catalog/api/products/42
                      |       |
                 context path  controller mapping

If DispatcherServlet is mapped to "/":
  context path: /catalog
  controller mapping: /api/products/{id}
  captured id: 42
```

If `DispatcherServlet` is mapped under a different prefix or the application changes its base path via server configuration, inspect the path as seen by MVC under that configuration. Do not put the context path into `@RequestMapping` out of habit, as it belongs to the external deployment URL.

### 5.2. Path Variables and Query Params Are Not the Same

`/books/42` can capture `id=42` via `@PathVariable`. `/books?id=42` has query parameter `id=42`, retrieved via `@RequestParam`. If a controller only declares `@GetMapping("/books/{id}")`, Spring does not automatically substitute a query param for a path variable.

## 6. `HandlerExecutionChain` and Interceptors

After finding a handler, `HandlerMapping` typically returns a `HandlerExecutionChain`. The chain holds the handler and the list of `HandlerInterceptor` instances applicable to the request. An interceptor has three common callbacks:

- `preHandle(request, response, handler)`: runs before the handler; returns `true` to continue or `false` to stop remaining execution.
- `postHandle(request, response, handler, modelAndView)`: runs after handler execution in applicable cases.
- `afterCompletion(request, response, handler, exception)`: callback when request processing finishes for participating interceptors under the corresponding semantics.

Simple synchronous flow:

```text
HandlerMapping.getHandler(request)
       |
HandlerExecutionChain
       |
interceptor A: preHandle
interceptor B: preHandle
       |
HandlerAdapter: invoke handler
       |
interceptor B: postHandle
interceptor A: postHandle
       |
rendering (if view)
       |
interceptor B: afterCompletion
interceptor A: afterCompletion
```

If `preHandle` returns `false`, the handler does not run and remaining callbacks follow the executed-chain rules. For async requests, callbacks do not behave identically to the synchronous diagram; use `AsyncHandlerInterceptor` when specialized async behavior is needed.

In particular with `@ResponseBody` and `ResponseEntity`, the response body may already be written inside `HandlerAdapter` before `postHandle`. Therefore, do not design an interceptor assuming you can always modify the response body in `postHandle`; consider `ResponseBodyAdvice` for that kind of requirement. For security, Spring recommends integrating protection with the Servlet filter chain / Spring Security rather than treating interceptors as the sole security layer.

### 6.1. Example Observing the Selected Handler

A practical interceptor can print the name of the selected handler method. The following Java class **runs inside the Spring Boot MVC project in Section 8**, using the same package as the application:

```java
package example.mapping;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.method.HandlerMethod;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class MappingTraceConfiguration implements WebMvcConfigurer {

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new SelectedHandlerInterceptor());
    }

    static class SelectedHandlerInterceptor implements HandlerInterceptor {
        @Override
        public boolean preHandle(HttpServletRequest request,
                                 HttpServletResponse response,
                                 Object handler) {
            if (handler instanceof HandlerMethod method) {
                System.out.println("Selected "
                        + method.getBeanType().getSimpleName()
                        + "#" + method.getMethod().getName());
            }
            return true;
        }
    }
}
```

For example, when the selected handler is `ItemsController.latest()`, the console line for that request will look like:

```text
Selected ItemsController#latest
```

Because the class is registered via `WebMvcConfigurer`, the interceptor receives requests handled by MVC mappings within the current configuration scope. A handler is not guaranteed to always be a `HandlerMethod`, so check `instanceof` before casting.

## 7. Multiple `HandlerMapping` Beans and Precedence Order

`DispatcherServlet` can receive multiple `HandlerMapping` beans. They are sorted by order; Spring tries them in turn until one mapping returns a matching chain. Under `Ordered` semantics, **a smaller `order` number means higher priority**.

Architectural illustration:

```text
DispatcherServlet
  |
  +-- RequestMappingHandlerMapping  -> annotated controllers
  |
  +-- RouterFunctionMapping         -> MVC.fn routes
  |
  +-- resource mappings             -> static assets
  |
  +-- default servlet forwarding    -> fallback if enabled
```

**Classification diagram, not fixed `order` numbers**: actual ordering and beans depend on the framework version, MVC configuration, Spring Boot, and customizations. Within a single `HandlerMapping`, route selection is a matter of **request mapping specificity**; across different `HandlerMapping` beans, the dispatcher relies on **mapping bean order**. Do not conflate the two concepts.

A very broad fallback such as `/**` can shadow endpoints or static resources if priorities are misconfigured. Conversely, static resource mappings can be checked after annotation mappings so controllers take precedence when properly configured. Do not assign an overly high priority `order` to a custom handler mapping before understanding all existing mappings.

## 8. Complete Spring MVC Example with Java 17+

The example uses **Spring Boot 3.4.0**, Java 17, and Spring MVC. This is a standalone project demonstrating how `RequestMappingHandlerMapping` selects methods across HTTP requests. Only the Spring Web starter is required; Spring Boot provides an embedded Servlet container and `DispatcherServlet` out of the box.

### 8.1. Structure

```text
mapping-demo/
├── pom.xml
└── src/
    ├── main/java/example/mapping/
    │   ├── MappingDemoApplication.java
    │   ├── ItemsController.java
    │   └── MappingTraceConfiguration.java
    └── test/java/example/mapping/
        └── ItemsMappingTest.java
```

`MappingTraceConfiguration` is the class from Section 6.1. If you do not want handler logs printed, you can omit that file; controller route selection behavior remains the same.

### 8.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>mapping-demo</artifactId>
    <version>1.0.0</version>
    <name>mapping-demo</name>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
```

Boot manages compatible Spring dependency versions for Boot 3.4.0. Run with Maven from the directory containing `pom.xml`. Do not manually add `@EnableWebMvc` to the demo because Boot already auto-configures MVC appropriately.

### 8.3. Entry Point

File `src/main/java/example/mapping/MappingDemoApplication.java`:

```java
package example.mapping;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MappingDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(MappingDemoApplication.class, args);
    }
}
```

### 8.4. Explicit Routes and Conditions

File `src/main/java/example/mapping/ItemsController.java`:

```java
package example.mapping;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/items")
public class ItemsController {

    @GetMapping(path = "/latest", produces = MediaType.TEXT_PLAIN_VALUE)
    public String latest() {
        return "item:latest";
    }

    @GetMapping(path = "/{id}", produces = MediaType.TEXT_PLAIN_VALUE)
    public String byId(@PathVariable String id) {
        return "item:" + id;
    }

    @GetMapping(params = "!view", produces = MediaType.TEXT_PLAIN_VALUE)
    public String listDefault() {
        return "list:default";
    }

    @GetMapping(params = "view=compact",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String listCompact() {
        return "list:compact";
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE,
                 produces = MediaType.TEXT_PLAIN_VALUE)
    public String create(@RequestBody NewItem input) {
        return "created:" + input.name();
    }

    public record NewItem(String name) {
    }
}
```

Explanation:

- Class-level `@RequestMapping("/api/items")` serves as the shared prefix.
- `latest()` and `byId(...)` share the same HTTP method and prefix; the literal `/latest` wins when matched.
- `listDefault()` requires the **absence** of parameter `view`, while `listCompact()` requires `view=compact`; they do not conflict when matching the intended requests.
- `create(...)` handles only **POST** with `Content-Type: application/json`; the body is parsed into the `NewItem` record if the JSON is valid. It returns plain text, and the default success response is HTTP 200 because the demo does not use `@ResponseStatus`.
- `@RequestBody` and Jackson run after the mapping selection step when `HandlerAdapter` executes the method; `HandlerMapping` does not deserialize into `NewItem` itself.

### 8.5. Running and Verifying with HTTP Requests

Requirements: JDK 17+, Maven, port 8080 free. From the `mapping-demo` directory:

```bash
mvn test
mvn spring-boot:run
```

The run command keeps the terminal open; open another terminal to invoke:

```bash
curl -s http://localhost:8080/api/items/latest
curl -s http://localhost:8080/api/items/42
curl -s http://localhost:8080/api/items
curl -s "http://localhost:8080/api/items?view=compact"
curl -s -X POST http://localhost:8080/api/items \
  -H "Content-Type: application/json" \
  -H "Accept: text/plain" \
  -d '{"name":"Lan"}'
```

Corresponding to each command above, the expected **body** outputs:

```text
item:latest
item:42
list:default
list:compact
created:Lan
```

These are five results from **five separate requests**, and each response body does not necessarily end with a trailing newline. If `MappingTraceConfiguration.java` was also created, server stdout will also show lines like `Selected ItemsController#...`, helping observe which method was selected.

Try sending requests with incompatible methods or media types:

```bash
curl -i -X PUT http://localhost:8080/api/items/42

curl -i -X POST http://localhost:8080/api/items \
  -H "Content-Type: text/plain" \
  -d 'Lan'

curl -i http://localhost:8080/api/items/42 \
  -H "Accept: application/xml"
```

In the demo and default configuration:

- `PUT /api/items/42` → typically HTTP **405 Method Not Allowed** (a matching pattern exists, but the HTTP method is unsupported).
- POST with `Content-Type: text/plain` → typically HTTP **415 Unsupported Media Type** because `consumes` does not match.
- GET requesting XML when the handler only has `produces=text/plain` → typically HTTP **406 Not Acceptable**.

Error bodies may differ across Spring Boot versions/configurations; the **status code** is the focus in these cases. These error statuses are the outcome of mapping lookup and condition evaluation, and do not indicate that the controller business method executed.

### 8.6. `MockMvc` Test Verifying Mapping

File `src/test/java/example/mapping/ItemsMappingTest.java`:

```java
package example.mapping;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ItemsMappingTest {

    @Autowired
    MockMvc mvc;

    @Test
    void picksLiteralPathBeforeVariable() throws Exception {
        mvc.perform(get("/api/items/latest"))
                .andExpect(status().isOk())
                .andExpect(content().string("item:latest"));

        mvc.perform(get("/api/items/42"))
                .andExpect(status().isOk())
                .andExpect(content().string("item:42"));
    }

    @Test
    void matchesQueryConditions() throws Exception {
        mvc.perform(get("/api/items"))
                .andExpect(status().isOk())
                .andExpect(content().string("list:default"));

        mvc.perform(get("/api/items").param("view", "compact"))
                .andExpect(status().isOk())
                .andExpect(content().string("list:compact"));
    }

    @Test
    void honorsHttpMethodAndMediaType() throws Exception {
        mvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.TEXT_PLAIN)
                        .content("{\"name\":\"Lan\"}"))
                .andExpect(status().isOk())
                .andExpect(content().string("created:Lan"));
    }
}
```

`MockMvc` simulates requests through the Spring MVC infrastructure inside the test context, **without opening a real network port**. The assertions compel the application to choose the right handler, process the request, and produce the expected body. Run `mvn test` standalone; Maven is expected to report passing tests, while exact test counts/runtime logs depend on plugins and environment.

## 9. Observing Registered Handler Mappings at Startup

You can inspect registered mappings instead of guessing from annotations. In the demo application from Section 8, add this optional class:

```java
package example.mapping;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping;

@Component
public class MappingInspector implements ApplicationRunner {
    private final RequestMappingHandlerMapping mapping;

    public MappingInspector(RequestMappingHandlerMapping mapping) {
        this.mapping = mapping;
    }

    @Override
    public void run(ApplicationArguments args) {
        mapping.getHandlerMethods().forEach((info, method) ->
                System.out.println(info + " -> "
                        + method.getBeanType().getSimpleName()
                        + "#" + method.getMethod().getName()));
    }
}
```

At startup, this code lists the `RequestMappingInfo` metadata and `HandlerMethod` entries present in `RequestMappingHandlerMapping`. The `toString()` syntax of `RequestMappingInfo` may vary across Spring versions, and traversal order is not an API contract; **do not compare stdout verbatim or rely on line ordering**. What matters is observing that every URL/method/condition from `ItemsController` is present in the registry.

If you want to debug via logger:

```properties
logging.level.org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping=TRACE
logging.level.org.springframework.web.servlet.DispatcherServlet=DEBUG
```

This is **sample content for `src/main/resources/application.properties`**, not a Java file. TRACE/DEBUG levels can produce verbose logs; use them temporarily for learning and restore appropriate levels for deployment. Reading startup logs, mappings, and request logs together provides much stronger evidence than looking only at HTTP status codes.

## 10. Handler Not Found or Not Selected: Distinguishing Errors

Do not lump every mapping issue together as "404":

| Symptom | Meaning to investigate | Direction to check |
| --- | --- | --- |
| 404 Not Found | No suitable handler for path, or request handled/fallen back by another configuration | Context path, servlet mapping, controller scan, URL pattern |
| 405 Method Not Allowed | Path has a mapping, but HTTP method does not match | `@GetMapping` / `@PostMapping`, client method |
| 415 Unsupported Media Type | Request body media type does not match `consumes` or converter | `Content-Type`, `consumes`, message converters |
| 406 Not Acceptable | Cannot produce a format acceptable to the client | `Accept`, `produces`, converters |
| 400 Bad Request | May be due to `params` conditions or invalid request parameter/body | Query params, type conversion, JSON/binding |
| 500 or startup failure | Conflicting mappings, invalid handler/bean configuration, runtime error | Root cause in startup/runtime logs |

These codes are **typical possibilities** in Spring MVC; fallback handlers, exception resolvers, security filters, or custom error handlers can alter the observed behavior. Seeing one status code alone is insufficient to deduce a single cause.

### 10.1. Controller Not Registered

`@RestController` does not guarantee the class gets scanned. With Boot, `@SpringBootApplication` includes component scanning starting from its package. If `ItemsController` resides outside the scanned package, `RequestMappingHandlerMapping` will have none of its mappings. The fix is organizing packages sensibly or configuring explicit scanning, avoiding indiscriminate scanning of the entire classpath.

### 10.2. Duplicate Mappings or Ambiguous Handler Methods

For example, two methods in the same context both declaring `@GetMapping("/orders/{id}")` with indistinguishable conditions:

```java
@GetMapping("/orders/{id}")
public String first(@PathVariable String id) {
    return "first:" + id;
}

@GetMapping("/orders/{id}")
public String second(@PathVariable String id) {
    return "second:" + id;
}
```

This is an **intentionally erroneous fragment**: within the same controller, Spring typically detects duplicate mappings at registration time and fails startup. With two different-string patterns of equal specificity (e.g., `/{id}` and `/{name}`), a request can match both and trigger **ambiguous handler methods** at runtime. Renaming the Java method, renaming the URI variable, or moving methods around in the file is **not a reliable way to resolve ambiguity**. Design meaningful paths, methods, params, headers, or consumes/produces to avoid creating competing mappings.

### 10.3. Overly Broad Path Patterns

A `/**` fallback can match many requests. Within annotation mappings, more specific patterns generally win; across different mapping beans, precedence order also determines which mapping is tried first. If static assets or health endpoints hit the wrong handler, inspect the `HandlerMapping` list, resource configuration, and actual `Ordered` values.

### 10.4. Confusing `HandlerMapping` with `HandlerInterceptor`

An interceptor only runs within the execution chain after the corresponding mapping selects a handler. A request that never reaches the dispatcher, is blocked by a Servlet filter, or is not handled by the mapping may not trigger the interceptor you expect. If cross-cutting security or logging is needed before dispatch, evaluate Servlet filters or Spring Security according to their responsibilities.

### 10.5. Confusing MVC Routing with WebFlux

Both stacks have `@GetMapping`, but MVC uses `DispatcherServlet`, `RequestMappingHandlerMapping` in package `org.springframework.web.servlet...`, and the Servlet stack's `RequestMappingHandlerAdapter`. WebFlux uses `DispatcherHandler` and reactive components in `org.springframework.web.reactive...`. Even if class names look similar, they **cannot be swapped merely because annotations look identical**.

## 11. HandlerMapping Reasoning Exercises

### Exercise 1 — Literal vs. Path Variable Selection

Suppose:

```java
@GetMapping("/customers/new")
public String newCustomer() { return "new"; }

@GetMapping("/customers/{id}")
public String customer(@PathVariable String id) { return id; }
```

Predict the handler for `GET /customers/new` and `GET /customers/123`. Why does the order of the two methods in the file not determine precedence? **Hint:** a literal pattern is more specific than a path segment variable.

### Exercise 2 — Distinguishing Path and HTTP Method

A controller only has `@GetMapping("/invoices/{id}")`. Predict the behavior when a client sends `POST /invoices/10`. Why is this typically 405 rather than 404? Changing it to `@RequestMapping("/invoices/{id}")` is not just renaming the annotation: without declaring a method condition, the accepted HTTP methods become broader, potentially unintended.

### Exercise 3 — Distinguishing `consumes` and `produces`

An endpoint accepts JSON and returns plain text. Write `@PostMapping` with `consumes="application/json"` and `produces="text/plain"`. Predict the consequence when a client sends `Content-Type:text/plain`, and when a client sends `Accept:application/xml`. Which case relates to the request body, and which to the response media type?

### Exercise 4 — Analyzing the Execution Chain

Explain why a request can successfully select a handler yet still fail before the response body is completed. Give two causes occurring **after HandlerMapping**, such as a conversion error on `@PathVariable long` or an exception thrown by the service/controller.

### Exercise 5 — Designing Routes to Avoid Ambiguity

Suppose you want a default `GET /reports` and `GET /reports?view=compact`. Design two mappings with explicit query conditions, then test the `?view=full` case. Is another fallback endpoint needed? Decide based on the desired API contract.

## 12. Official Documentation for Deeper Study

- `DispatcherServlet` overview and processing sequence: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/sequence.html
- Annotated controller mapping, request conditions, and path patterns: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-requestmapping.html
- Servlet MVC `HandlerMapping` and special bean types: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/special-bean-types.html
- Interceptors in Servlet MVC: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/handlermapping-interceptor.html
- Functional endpoints on the Servlet stack: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-functional.html
- `RequestMappingHandlerMapping` API: https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/RequestMappingHandlerMapping.html

**Key takeaway:** `HandlerMapping` decides **which handler** and associated interceptors apply; `HandlerAdapter` decides **how to execute that handler**. With annotated controllers, handler selection depends on **all request conditions**, not just the path; Spring uses explicit specificity and precedence rules so decisions do not depend on code order.
