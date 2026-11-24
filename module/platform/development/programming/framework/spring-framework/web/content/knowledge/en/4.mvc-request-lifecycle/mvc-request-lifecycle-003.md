# HandlerAdapter: Invoking Handlers and Supporting Method Signatures in Spring MVC

## 1. What Problem Does HandlerAdapter Solve?

When an HTTP request arrives at a **Spring Web MVC** application, `DispatcherServlet` is the central coordinator. It finds the matching *handler* for the request and then needs to invoke that handler. However, a handler can be represented in multiple ways: a controller method annotated with `@GetMapping`, an object implementing `HttpRequestHandler`, or a legacy controller implementing `Controller`.

`DispatcherServlet` should not hardcode separate invocation logic for every handler type. Spring separates two responsibilities:

- **`HandlerMapping`:** decides *which handler does this request match?*; typically returns a `HandlerExecutionChain` containing the handler and associated interceptors.
- **`HandlerAdapter`:** decides *can this handler be invoked and how should it be invoked?*; if supported, it performs the invocation with the appropriate HTTP context and returns the result for the next processing step.

For modern annotated controllers, the most common implementation is **`RequestMappingHandlerAdapter`**. It supports flexible controller method signatures: parameters from URI, query, header, body, model, session, and Servlet API; type conversion, binding, and validation; and handling return values into views, response bodies, or asynchronous responses.

**Core idea:** `HandlerAdapter` is the bridge between the handler selected by mapping and the mechanism that executes it. It is not responsible for finding URL mappings or performing business logic in place of the controller.

## 2. Position in the Lifecycle of an MVC Request

Example:

~~~http
GET /api/orders/42?details=true HTTP/1.1
Host: localhost:8080
Accept: application/json
~~~

Basic flow:

~~~text
HTTP client
    |
    v
Servlet container
    |
    v
Filter chain
    |
    v
DispatcherServlet
    |
    | (1) ask HandlerMappings
    v
RequestMappingHandlerMapping
    |
    | return HandlerExecutionChain:
    |   HandlerMethod + HandlerInterceptors
    v
DispatcherServlet
    |
    | (2) pick HandlerAdapter with supports(handler) == true
    v
RequestMappingHandlerAdapter
    |
    | (3) resolve parameters:
    |     @PathVariable id       <- "42" -> long
    |     @RequestParam details   <- "true" -> boolean
    |     HttpServletRequest...  <- request context
    | (4) invoke controller method
    | (5) handle return value:
    |     record/Object -> JSON body, or ModelAndView -> view
    v
DispatcherServlet
    |
    | finalize interceptors, exception handling/rendering if needed
    v
HTTP response
~~~

This is a *logical flow* diagram; it omits branches such as multipart, async dispatch, errors, and HTTP cache optimizations. With `@ResponseBody` or `@RestController`, the adapter and return-value handler typically write the response body directly via converters; no HTML view lookup is needed.

A clearer breakdown:

| Component | Question it answers | Example |
| --- | --- | --- |
| `Filter` (Servlet) | What request/response processing is needed before entering MVC? | Security filter, logging |
| `DispatcherServlet` | Who coordinates the request pipeline? | `doDispatch(...)` |
| `HandlerMapping` | Which handler matches the URI, HTTP method, headers...? | `RequestMappingHandlerMapping` |
| `HandlerInterceptor` | Is pre/post-handler processing needed? | `preHandle`, `postHandle` |
| `HandlerAdapter` | How is the selected handler invoked? | `RequestMappingHandlerAdapter` |
| `HandlerMethodArgumentResolver` | Where does each method argument come from? | `@PathVariable`, `@RequestParam` |
| `HandlerMethodReturnValueHandler` | Where does the method's result go? | JSON response, view/model |
| `HttpMessageConverter` | How are HTTP bodies ↔ Java objects converted? | JSON converter using Jackson |
| `HandlerExceptionResolver` | If an error occurs, how is it translated into handling/response? | `@ExceptionHandler`, default resolvers |
| `ViewResolver` | Which view corresponds to a view name? | Thymeleaf template |

**Do not confuse `HandlerMapping` and `HandlerAdapter`:** "finding the controller method" and "preparing arguments then invoking the method" are two separate jobs. `HandlerAdapter` receives an already-selected handler rather than choosing endpoints by URL.

## 3. The HandlerAdapter Contract

In Spring MVC, the main contract resides in `org.springframework.web.servlet.HandlerAdapter`. A simplified form to grasp its meaning:

~~~java
public interface HandlerAdapter {
    boolean supports(Object handler);

    ModelAndView handle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) throws Exception;

    long getLastModified(HttpServletRequest request, Object handler);
}
~~~

The snippet above illustrates the contract shape on the Spring Framework 6.x branch; it is not a file to copy into an application. Corresponding Jakarta Servlet and `ModelAndView` imports are required.

- **`supports(handler)`:** reports whether the adapter supports the handler type returned by the mapping. `DispatcherServlet` may have multiple adapters and picks the matching one.
- **`handle(request, response, handler)`:** executes handler processing. For an annotated method, this covers preparing arguments, invoking the method, and handling the return value.
- **`getLastModified(...)`:** an extension point related to HTTP caching/`Last-Modified` for the handler; it is not an API for selecting mappings. For annotated `@RequestMapping` methods, Spring typically uses dedicated conditional request mechanisms such as `WebRequest.checkNotModified(...)`.

The `ModelAndView` return value of `handle` may be **null** when the response has already been handled directly (for example, a controller returning JSON via `@ResponseBody`). This **does not mean the request failed**.

Do not implement `HandlerAdapter` yourself for a normal `@RestController`. Spring MVC already configures standard adapters. Customizing method signatures normally only requires adding an **argument resolver** or other supporting components.

## 4. Common HandlerAdapters

| Handler returned by HandlerMapping | Supporting adapter | Purpose |
| --- | --- | --- |
| `HandlerMethod` of `@RequestMapping` / `@GetMapping` ... method | `RequestMappingHandlerAdapter` | Modern annotated controller flow |
| Object implementing `HttpRequestHandler` | `HttpRequestHandlerAdapter` | Invokes `handleRequest(request, response)` contract |
| Legacy object implementing `org.springframework.web.servlet.mvc.Controller` | `SimpleControllerHandlerAdapter` | Invokes legacy `handleRequest(...)` contract |

`RequestMappingHandlerMapping` typically maps to a **`HandlerMethod`**, an object describing the bean/controller together with the discovered Java method. That differs from "passing the whole controller class into the adapter."

For example, the same application can have annotated REST controllers alongside a specialized resource handler. `DispatcherServlet` uses the adapter abstraction so both styles are invoked uniformly. When first learning Spring MVC, however, the focus is `RequestMappingHandlerAdapter`; the other two adapters explain why the interface exists.

### Is Selecting an Adapter the Same as Selecting a Controller?

No. Endpoint selection based on mapping has already happened earlier. If you have:

~~~java
@GetMapping("/items/{id}")
public Item getItem(@PathVariable long id) { ... }
~~~

then `RequestMappingHandlerMapping` matches the path and method and returns a `HandlerMethod` pointing to `getItem`. `RequestMappingHandlerAdapter` receives that `HandlerMethod`, determines how to supply `id`, and invokes the method. It **does not run the URL-matching algorithm again**.

### One Adapter Can Serve Many Method Signatures

All of the following methods can use the same `RequestMappingHandlerAdapter`:

~~~java
@GetMapping("/hello")
String hello(@RequestParam(defaultValue = "Guest") String name) { ... }

@PostMapping("/orders")
ResponseEntity<Order> create(@Valid @RequestBody NewOrder request) { ... }

@GetMapping("/report")
ModelAndView report(Model model) { ... }
~~~

The `...` bodies are illustrative placeholders and **cannot compile standalone**. Diversity in parameters and return types is handled by specialized lists of resolvers and handlers, rather than needing a separate `HandlerAdapter` implementation per method signature.

## 5. Inside RequestMappingHandlerAdapter

A typical branch for an annotated method:

~~~text
HandlerMethod
    |
    v
RequestMappingHandlerAdapter
    |
    v
ServletInvocableHandlerMethod / invocation mechanism
    |
    +-- Argument resolvers (per parameter)
    |     @PathVariable -> URI template variable
    |     @RequestParam  -> query/form parameter
    |     @RequestHeader -> HTTP header
    |     @RequestBody   -> HttpMessageConverter -> Java object
    |     @ModelAttribute -> binder/converter/validator
    |     Servlet request/model/session -> framework context
    |
    +-- Controller method invoked with resolved arguments
    |
    +-- Return-value handlers (by return type/annotation)
          @ResponseBody -> HttpMessageConverter -> HTTP body
          ResponseEntity -> status + headers + body
          String view name -> ModelAndView/view rendering
          Callable / DeferredResult -> corresponding async processing
~~~

Internal class names are useful when reading stack traces, but **are not APIs applications should call directly**. Spring manages them for nearly all annotated controllers.

### 5.1 How Are Argument Resolvers Selected?

A `HandlerMethodArgumentResolver` has two main operations:

~~~java
boolean supportsParameter(MethodParameter parameter);

Object resolveArgument(
        MethodParameter parameter,
        ModelAndViewContainer mavContainer,
        NativeWebRequest webRequest,
        WebDataBinderFactory binderFactory) throws Exception;
~~~

This is an excerpt of the signatures for comprehension; it is not a complete interface file.

`supportsParameter` asks whether the resolver knows how to produce a value for a given parameter based on its annotations, Java type, and metadata. `resolveArgument` extracts data from the HTTP request and/or binder to produce the object passed into the controller method.

Concrete examples:

| Controller signature | Source and argument resolution step |
| --- | --- |
| `@PathVariable long id` | Extracts path variable and converts String → long |
| `@RequestParam int page` | Extracts query/form parameter and converts to int |
| `@RequestHeader("X-Trace-ID") String traceId` | Reads HTTP header |
| `@RequestBody OrderRequest input` | Chooses message converter by content type and target type; parses body into object |
| `@Valid @RequestBody OrderRequest input` | After deserialization, runs validation when a corresponding provider is configured |
| `Model model` | Supplies model for views or request processing |
| `HttpServletRequest request` | Accesses the native Servlet request |

**Resolver selection happens per parameter.** A single method can simultaneously accept `@PathVariable`, `@RequestParam`, `@RequestBody`, and other context dependencies.

For simple **unannotated** parameter types, MVC may fall back to treating them as request parameters; complex types may be treated as model attributes. For maintainability, use explicit annotations whenever the data source matters.

### 5.2 Where Do Binding, Conversion, and Validation Fit?

Suppose a request arrives:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json

{"item":"Notebook","quantity":2}
~~~

The controller declares:

~~~java
public ResponseEntity<OrderResponse> create(
        @Valid @RequestBody CreateOrderRequest input) { ... }
~~~

General sequence:

1. A resolver recognizes the parameter has `@RequestBody`.
2. Based on `Content-Type: application/json` and the target Java type, an appropriate `HttpMessageConverter` (typically Jackson JSON converter) converts bytes into `CreateOrderRequest`.
3. With `@Valid` and an appropriate Bean Validation provider, constraints on the data are checked.
4. If there are no errors, the controller method receives the populated object.
5. If deserialization/conversion/validation fails, the framework may raise an exception before the method body runs; the exception resolver pipeline decides the response.

**Do not confuse roles:** `HandlerAdapter` coordinates; argument resolvers understand parameter sources; `HttpMessageConverter` reads/writes HTTP bodies; `WebDataBinder` and the conversion/validation system handle binding/validation as applicable.

`@Valid` requires a Jakarta Bean Validation dependency/provider in the project (with Spring Boot, typically adding `spring-boot-starter-validation`). If omitted, do not assume constraints like `@NotBlank`/`@Min` are enforced.

### 5.3 How Are Return Values Interpreted?

| Controller returns | Common handling |
| --- | --- |
| `OrderResponse` inside `@RestController` | Serializes object into response body (usually JSON) |
| `ResponseEntity<OrderResponse>` | Writes status/headers/body per the response entity |
| `String` from `@Controller` method without `@ResponseBody` | Typically a logical view name |
| `String` from `@RestController` | Text response body, not a view name |
| `ModelAndView` | Model and view for the rendering step |
| `void` / certain empty values | Depends on annotations, response state, and method contract |
| `Callable<T>`, `DeferredResult<T>` | Servlet async integration, with a later dispatch processing the result |

Return-value handlers choose how to interpret results **based on annotations and types**, so looking only at the Java type `String` is insufficient to deduce whether the server returns a view name or a raw string body.

Some classes helpful for exploring internals: `HandlerMethodReturnValueHandler`, `RequestResponseBodyMethodProcessor`, and `HttpEntityMethodProcessor`.

## 6. Runnable Example: Multiple Method Signatures and Custom Argument Resolver

The standalone example below uses **Java 17**, **Spring Boot 3.3.5** (Spring Framework 6.1.x), the **Spring MVC** web stack, Jackson, and Bean Validation.

Endpoints:

- `GET /api/orders/{id}?verbose=true`: `@PathVariable`, `@RequestParam`, and a custom `@CurrentRequestId` parameter read from a header.
- `POST /api/orders`: `@Valid @RequestBody` creates an object, returning `ResponseEntity` with status `201`, a `Location` header, and a JSON body.
- The custom parameter demonstrates the natural extension point of `RequestMappingHandlerAdapter`: **`HandlerMethodArgumentResolver`**.

The demo keeps data static with no database so MVC mechanics can be observed in isolation.

### 6.1 Gradle configuration

Create a separate Spring Boot project, e.g. `handler-adapter-demo`.

File `settings.gradle`:

~~~groovy
rootProject.name = 'handler-adapter-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Requires JDK 17+ and a Gradle version compatible with the Spring Boot plugin. If the project includes a Gradle Wrapper, use the wrapper to run it.

### 6.2 Complete Java Source

Create file `src/main/java/example/web/HandlerAdapterDemoApplication.java`:

~~~java
package example.web;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.net.URI;
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.MethodParameter;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.bind.support.WebDataBinderFactory;
import org.springframework.web.context.request.NativeWebRequest;
import org.springframework.web.method.support.HandlerMethodArgumentResolver;
import org.springframework.web.method.support.ModelAndViewContainer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@SpringBootApplication
public class HandlerAdapterDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(HandlerAdapterDemoApplication.class, args);
    }

    @Target(ElementType.PARAMETER)
    @Retention(RetentionPolicy.RUNTIME)
    public @interface CurrentRequestId {
    }

    public record OrderInfo(long id, String requestId, boolean verbose) {
    }

    public record CreateOrderRequest(
            @NotBlank String item,
            @Min(1) int quantity) {
    }

    public record CreatedOrder(long id, String item, int quantity) {
    }

    @RestController
    @RequestMapping("/api/orders")
    public static class OrderController {

        @GetMapping("/{id}")
        public OrderInfo get(
                @PathVariable long id,
                @RequestParam(defaultValue = "false") boolean verbose,
                @CurrentRequestId String requestId) {

            return new OrderInfo(id, requestId, verbose);
        }

        @PostMapping
        public ResponseEntity<CreatedOrder> create(
                @Valid @RequestBody CreateOrderRequest input) {

            CreatedOrder created = new CreatedOrder(
                    101L, input.item(), input.quantity());

            return ResponseEntity
                    .created(URI.create("/api/orders/101"))
                    .body(created);
        }
    }

    @Configuration
    public static class MvcConfiguration implements WebMvcConfigurer {

        @Override
        public void addArgumentResolvers(
                List<HandlerMethodArgumentResolver> resolvers) {
            resolvers.add(new CurrentRequestIdResolver());
        }
    }

    public static class CurrentRequestIdResolver
            implements HandlerMethodArgumentResolver {

        @Override
        public boolean supportsParameter(MethodParameter parameter) {
            return parameter.hasParameterAnnotation(CurrentRequestId.class)
                    && parameter.getParameterType() == String.class;
        }

        @Override
        public Object resolveArgument(
                MethodParameter parameter,
                ModelAndViewContainer mavContainer,
                NativeWebRequest webRequest,
                WebDataBinderFactory binderFactory) {

            String id = webRequest.getHeader("X-Request-ID");
            if (id == null || id.isBlank()) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST,
                        "Missing X-Request-ID");
            }
            return id;
        }
    }
}
~~~

**Key observation:** the controller contains no manual header-parsing code in the `get` method. `RequestMappingHandlerAdapter` uses its list of argument resolvers, including the one we registered via `WebMvcConfigurer#addArgumentResolvers`. When it sees `@CurrentRequestId String`, the resolver reads the header and supplies the third parameter.

This custom resolver operates **inside Spring MVC annotated controllers**. It is not a Servlet filter, does not alter URL mapping, and does not require writing a new `HandlerAdapter`.

### 6.3 Running the Application

In the project directory, with Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

If there is no wrapper, a compatible Gradle installation is needed; the equivalent command is `gradle bootRun`. By default the server listens on `http://localhost:8080` if the port is not used by another application.

**Test GET:**

~~~bash
curl -i -H "X-Request-ID: abc-123" \
  "http://localhost:8080/api/orders/42?verbose=true"
~~~

On Windows PowerShell, you can write it on one line with `curl.exe` to avoid shell aliases and line continuation:

~~~powershell
curl.exe -i -H "X-Request-ID: abc-123" "http://localhost:8080/api/orders/42?verbose=true"
~~~

Expected response body when the request succeeds:

~~~json
{"id":42,"requestId":"abc-123","verbose":true}
~~~

The status is `200 OK` and the body is JSON. Steps coordinated by the adapter:

1. `@PathVariable` produces `long id = 42L`.
2. `@RequestParam` produces `boolean verbose = true`.
3. Custom `CurrentRequestIdResolver` produces `String requestId = "abc-123"`.
4. Method `OrderController#get` is invoked with these three arguments.
5. Because of `@RestController`, the return-value handler writes the JSON for `OrderInfo`.

**Test missing header:**

~~~bash
curl -i "http://localhost:8080/api/orders/42"
~~~

The custom resolver throws `ResponseStatusException(HttpStatus.BAD_REQUEST, ...)`, so the expected status is `400 Bad Request`. The exact error body depends on how Spring Boot configures error responses; do not assume a fixed JSON shape.

**Test valid POST:**

~~~bash
curl -i -X POST "http://localhost:8080/api/orders" \
  -H "Content-Type: application/json" \
  -d '{"item":"Notebook","quantity":2}'
~~~

Expected status: `201 Created`, header `Location: /api/orders/101`, body:

~~~json
{"id":101,"item":"Notebook","quantity":2}
~~~

This is hardcoded demo data; no real database write occurs. `@RequestBody` is deserialized and then `@Valid` checks the record according to its annotations.

**Test invalid POST:**

~~~bash
curl -i -X POST "http://localhost:8080/api/orders" \
  -H "Content-Type: application/json" \
  -d '{"item":"","quantity":0}'
~~~

Both `@NotBlank` and `@Min(1)` are violated. When the validation starter is configured as above, the request must be rejected with status `400 Bad Request` before entering the `create` method body. Do not assume the order or format of error messages: they can change depending on error-handling configuration.

### 6.4 Why Not Invoke Controllers Yourself via Java Reflection?

The framework uses reflection/method invocation internally, but also handles many things before and after the call, such as argument creation, type conversion, validation, async state, writing status/headers/body, and exception routing. If you call directly:

~~~java
// Illustrates the idea, NOT how HTTP is handled in an application:
controller.get(42L, true, "abc-123");
~~~

it merely executes the Java method directly with already-available arguments; it does **not** automatically read `@PathVariable`, `@RequestParam`, or headers from `HttpServletRequest`. That is precisely the value of the pipeline coordinated by `RequestMappingHandlerAdapter`.

## 7. Common Errors When Controller Signatures Cannot Be Resolved

Not every parameter type is resolved the way a developer expects. The table below helps distinguish mapping errors, argument resolution errors, body conversion errors, and validation errors.

| Symptom | Possible Cause | Where to investigate first |
| --- | --- | --- |
| `404 Not Found` | Request did not match a handler mapping; or static resources handled it differently | URI, HTTP method, path pattern, mapping registration |
| `405 Method Not Allowed` | Path has a mapping, but HTTP method does not match | `@GetMapping`/`@PostMapping` and client method |
| `400` due to unreadable query/path value | Missing required parameter or type conversion failure | `@RequestParam`, `@PathVariable`, and converters |
| `400` due to malformed/missing JSON body | Jackson parse/conversion error or missing required body | `@RequestBody` and `HttpMessageConverter` |
| `400` due to validation | Constraint on bean/request failed | `@Valid`, Bean Validation provider, error handling |
| `415 Unsupported Media Type` | Body `Content-Type` is not supported by endpoint/converter | `consumes`, content type, converters |
| `406 Not Acceptable` | Cannot produce a response matching `Accept` | `produces`, converters, response negotiation |
| Returns view name instead of text | Method belongs to `@Controller` without `@ResponseBody` | Return-value handler / view resolver |
| Custom resolver does not run | Annotation/type not accepted by `supportsParameter`; wrong web stack or config | `WebMvcConfigurer` and resolver registration |
| Exception before entering method | Adapter failed to resolve an argument | Exception logs, argument resolvers, binder/converter |

**Distinguish carefully:** `HandlerMapping` selects the method first; errors during **handler selection** differ from errors while **the adapter prepares arguments or processes the return value**. The final status can also be affected by `HandlerExceptionResolver` or `@ControllerAdvice`.

### The BindingResult Case

In MVC, if you want to collect binding/validation errors inside the controller rather than letting an exception follow the default handling path, `BindingResult` / `Errors` must be placed **immediately after** the corresponding argument:

~~~java
@PostMapping("/forms")
String submit(@Valid @ModelAttribute OrderForm form,
              BindingResult result) {
    if (result.hasErrors()) {
        return "order-form";
    }
    return "order-success";
}
~~~

This snippet only illustrates method structure; `OrderForm` and the two view templates are not defined, so it is not a standalone runnable program.

## 8. Choosing the Right Extension Point

When you want to support new method signatures, choose the appropriate extension point:

- **Add a custom argument type:** implement `HandlerMethodArgumentResolver` and register it via `WebMvcConfigurer.addArgumentResolvers(...)`. Examples: `@CurrentTenant`, `@CurrentRequestId`, values read from a verified security context.
- **Add conversion between data types:** use `Converter`, `Formatter`, or `ConversionService` when transforming strings/parameters into application types.
- **Add binding/validation rules:** use `@InitBinder`, Bean Validation, and appropriate binder configurations.
- **Handle special request/response bodies:** configure or add an `HttpMessageConverter` when media types and serialization require it.
- **Customize controller errors:** `@ExceptionHandler`, `@RestControllerAdvice`, or a suitable exception resolver.
- **Add logic before/after handlers:** `HandlerInterceptor` if scoped to MVC, `Filter` if acting at the Servlet layer.
- **Support an entirely different handler type:** only then consider writing a custom `HandlerAdapter`/`HandlerMapping`; this is a very rare infrastructure need in typical applications.

**An important boundary:** adding a `HandlerMethodArgumentResolver` may not suffice if a built-in resolver is selected first for that same type/annotation. Choose a sufficiently distinct custom annotation/type and test resolution order. Do not arbitrarily replace the entire list of argument resolvers/return-value handlers, as doing so can break default framework support.

## 9. Do Async Return Values Still Go Through HandlerAdapter?

**Yes.** Spring MVC uses Servlet async for certain return types such as `Callable<T>` or `DeferredResult<T>`. The adapter handles the initial result and integrates async management; the request can be dispatched again once data is ready. Distinguish:

- Which thread the controller method executes on and whether it returns early.
- Whether async processing releases the initial Servlet thread while waiting.
- Work inside `Callable` may still block on a worker thread.
- The response is not necessarily complete at the moment the controller method first returns.

Symbolic example:

~~~java
@GetMapping("/slow")
Callable<String> slow() {
    return () -> service.loadResult();
}
~~~

This is an illustrative snippet depending on an undeclared `service`. It expresses that Spring MVC can handle async return types; it does not prove `service.loadResult()` is non-blocking.

**Do not confuse with Spring WebFlux.** WebFlux uses a reactive model with publisher pipelines; although it also supports annotated controllers, WebFlux's internal request handling does not use the Servlet MVC `RequestMappingHandlerAdapter` discussed in this lesson. Similar concept names do not mean identical classes or execution models.

## 10. Relationship with Interceptor, Filter, and ExceptionResolver

An MVC request can have many extension points, each in a different position:

~~~text
Servlet Filter (outermost)
    |
    v
DispatcherServlet
    |
    +-- HandlerMapping finds handler + interceptor chain
    |
    +-- interceptor.preHandle(...)
    |
    +-- HandlerAdapter.handle(...)
    |      +-- argument resolution
    |      +-- controller invocation
    |      +-- return-value handling
    |
    +-- interceptor.postHandle(...) (if applicable)
    |
    +-- render View (if any)
    |
    +-- interceptor.afterCompletion(...) (when processing completes)
    |
    v
Filter chain finishes
~~~

If an exception occurs, `HandlerExceptionResolver` may step in and handle the error; in async flows, callbacks and dispatch passes also differ from the simplified synchronous flow above. `postHandle` may be unable to alter a JSON body already written by the response-body handler.

An application guideline: if you need a **request ID** in a controller, prefer `@RequestHeader` or a custom argument resolver (as in Section 6); if you need **system-wide security**, use the appropriate security filter chain; if you need **handler-level condition checks**, an interceptor can work; if you need **consistent API errors**, `@RestControllerAdvice` can be used.

Do not place critical authentication/authorization logic in a custom argument resolver simply because reading headers is easy: raw client-supplied headers are not trustworthy by default.

## 11. Debugging HandlerAdapter with Observable Evidence

When encountering "mapping matched, but the method did not run", debug in order:

1. **Verify URL/method is mapped:** check endpoint mappings and appropriate request logs/details. If there is no mapping, focus on `HandlerMapping`, not the adapter.
2. **Verify handler type:** for annotated controllers, the handler is typically `HandlerMethod`; the typical adapter is `RequestMappingHandlerAdapter`.
3. **Verify each argument:** compare `@PathVariable`, `@RequestParam`, `@RequestHeader`, `@RequestBody` against the URL, headers, content type, and actual payload.
4. **Check converters/validation:** type conversion, Jackson, Jakarta Bean Validation constraints, early error messages.
5. **If the method ran but the response is wrong:** check `@ResponseBody`/`@RestController`, `ResponseEntity`, `Accept`/`produces`, message converters, view resolvers.
6. **If an exception was thrown:** trace `HandlerExceptionResolver` or `@ControllerAdvice`; the final status may differ from the status originating directly from the controller.
7. **If async:** distinguish the initial request, task execution, and the completion dispatch.

Some helpful class names when reading Spring MVC 6.x stack traces:

~~~text
DispatcherServlet
RequestMappingHandlerMapping
RequestMappingHandlerAdapter
ServletInvocableHandlerMethod
InvocableHandlerMethod
HandlerMethodArgumentResolverComposite
HandlerMethodReturnValueHandlerComposite
RequestResponseBodyMethodProcessor
HttpEntityMethodProcessor
HandlerExceptionResolver
~~~

You do not need to memorize every class name. What matters is knowing whether the error occurred during **mapping**, **argument conversion/binding**, **invocation**, **return-value conversion**, or **exception rendering**.

### Testing at the Right Level

- **`@WebMvcTest` + `MockMvc`:** tests mappings, built-in argument resolvers, validation, and response codes; import custom resolver configurations if needed.
- **Integration tests with a server:** verifies Servlet filters/security, JSON converters, validation providers, and production-like wiring.
- **Unit tests for custom resolvers:** `supportsParameter` with matching/non-matching annotations and types, present/missing headers.
- **Negative tests:** missing headers, invalid numbers, malformed JSON, failed validation, and unacceptable media types.

Assert HTTP status and body contents according to your application contract; avoid testing against default error strings that may change across Spring Boot versions and configurations.

## 12. Misconceptions to Avoid

| Misconception | Correct rule to remember |
| --- | --- |
| "DispatcherServlet directly invokes all controller types" | DispatcherServlet selects a `HandlerAdapter`; the adapter knows how to invoke that handler type |
| "HandlerAdapter decides which URL matches" | `HandlerMapping` determines the handler |
| "Each method signature needs its own HandlerAdapter" | `RequestMappingHandlerAdapter` uses argument resolvers/return-value handlers |
| "`@PathVariable` reads the request inside the controller" | Resolvers prepare arguments before the controller is invoked |
| "`@RequestBody` is just reflection casting" | It typically uses `HttpMessageConverter` to deserialize the HTTP body, optionally with validation |
| "A controller returning `String` always returns JSON/text" | With `@Controller` it is typically a view name; with `@RestController` it is typically a response body |
| "JSON responses must go through ViewResolver" | `@ResponseBody` is written directly by return-value handlers/converters |
| "HTTP 400 from @Valid is logic inside the method" | Validation can fail before the method is invoked |
| "Custom resolvers always run first" | Resolvers are chosen by support and configuration order |
| "To add a parameter you must write a custom HandlerAdapter" | Usually `HandlerMethodArgumentResolver` is all you need |
| "WebFlux also runs this Servlet RequestMappingHandlerAdapter" | WebFlux has its own stack and adapter implementation |
| "Async means no I/O is blocking anymore" | Async Servlet and non-blocking I/O are two different concepts |

## 13. Applied Exercises

**Exercise 1 — Classify responsibilities.** Given request `GET /api/products/9?currency=VND` and controller:

~~~java
@GetMapping("/api/products/{id}")
ProductView read(@PathVariable long id,
                 @RequestParam String currency) { ... }
~~~

Identify which component (a) determines the `read` method, (b) supplies `id` and `currency`, and (c) serializes `ProductView` when the method is inside a `@RestController`.

**Hint:** (a) `RequestMappingHandlerMapping`, (b) argument resolvers coordinated by `RequestMappingHandlerAdapter`, (c) return-value handler + HTTP message converter.

**Exercise 2 — Diagnose status 400.** A client sends `GET /api/products/abc` while the method requires `@PathVariable long id`. Why might the method body not run?

**Hint:** the path matches, but the argument resolver cannot convert `"abc"` to `long`, leading to exception handling before invocation.

**Exercise 3 — Extend a method signature.** You want every endpoint to receive `@CurrentTenant Tenant tenant`. List the minimal parts required to support this in MVC.

**Hint:** a parameter-targeted annotation, a resolver selecting by annotation/type, reading the tenant from an authenticated context, registering the resolver with `WebMvcConfigurer`, and testing both present/missing tenant cases. Do not trust a tenant value sent directly in an unauthenticated header.

**Exercise 4 — Choose extension points.** You want to log requests before controllers run, return a uniform JSON error format, and convert query `sort=NEWEST` into an enum. Should you write one custom HandlerAdapter or use three appropriate extension points?

**Hint:** Filter/Interceptor for logging depending on scope, `@RestControllerAdvice` or exception resolver for errors, and converter/enum conversion for the query param. No custom adapter is needed.

## 14. Checklist When Reading an MVC Controller Signature

- [ ] Mapping unambiguously identifies the handler and HTTP method.
- [ ] Handler fits `RequestMappingHandlerAdapter` or another adapter.
- [ ] Each parameter has a clear data source (path/query/header/body/model/context).
- [ ] Type conversion and binding are accurate, without relying on ambiguous fallbacks.
- [ ] `@Valid` has a corresponding provider and error handling has been tested.
- [ ] Request `Content-Type` matches input converters; `Accept` matches response output.
- [ ] Return type and annotations are properly understood: view, body, status/headers, or async.
- [ ] Custom argument resolvers are registered and tested for support ordering.
- [ ] Business logic or arbitrary authentication is not placed inside adapters/resolvers.
- [ ] When errors occur, distinguish `HandlerMapping`, `HandlerAdapter`, converters, validators, and exception resolvers.

**Practical conclusion:** `HandlerAdapter` lets `DispatcherServlet` invoke multiple handler styles without depending directly on how each handler receives data or returns results. In modern Spring MVC, `RequestMappingHandlerAdapter` is the execution hub for annotated controllers: it coordinates **argument resolvers → controller invocation → return-value handlers**. Understanding these three steps helps you design clear method signatures, add parameters at the right extension points, and quickly debug why a controller did not run or why a response was converted incorrectly.

### Official References

- [Spring Framework — DispatcherServlet Processing](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/sequence.html)
- [Spring Framework — Special Bean Types](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/special-bean-types.html)
- [Spring Framework — MVC Method Arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html)
- [Spring Framework — MVC Return Values](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/return-types.html)
- [Spring Framework — MVC HTTP Message Converters](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html)
- [Spring Framework — MVC Config](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config.html)
- [Spring Framework — RequestMappingHandlerAdapter API](https://docs.spring.io/spring-framework/docs/6.1.15/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/RequestMappingHandlerAdapter.html)
