# HandlerAdapter and Request Handler Invocation in Spring MVC

## 1. Big Picture

In Spring MVC, **DispatcherServlet** is the central coordinator for HTTP requests, **HandlerMapping** locates the matching handler object, and **HandlerAdapter** knows how to *execute* that handler according to the framework contract. For controllers using `@RequestMapping`, `@GetMapping`, `@PostMapping`, or similar annotations, the adapter commonly used is **RequestMappingHandlerAdapter**.

Thanks to the adapter layer, `DispatcherServlet` does not need to know how many parameters a controller accepts, whether it uses `@PathVariable` or `@RequestBody`, or whether it returns a JSON DTO or a `ModelAndView`. It simply finds a `HandlerAdapter` that supports the handler object returned by `HandlerMapping`, then asks the adapter to handle the request.

Key distinctions:

- **Mapping** decides "which handler owns this request?"
- **Adapter** decides "how does the framework invoke that handler?"
- **HandlerMethod** describes the selected bean and method, not the result of executing the method.
- **Argument resolver** produces Java parameter values from the request/context.
- **Return value handler** interprets the returned Java value to produce a model/view, HTTP body, status/headers, or async mechanism.
- **HttpMessageConverter** reads/writes the body, typically between JSON requests/responses and Java objects; it does not replace `HandlerAdapter`.

This lesson covers Spring MVC on the Servlet stack with runnable examples using **Java 17+, Spring Boot 3.3.x / Spring Framework 6.1.x**. Spring WebFlux has a dispatcher and handler adapters built on a different reactive architecture; do not mix them up just because controller annotations look identical.

## 2. Where HandlerAdapter Sits in the HTTP Request Flow

Simplified diagram:

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Servlet Filter chain / Security filters"]
    B --> C["DispatcherServlet"]
    C --> D["HandlerMapping"]
    D --> E["HandlerExecutionChain: handler + interceptors"]
    E --> F["DispatcherServlet selects HandlerAdapter"]
    F --> G["HandlerInterceptor.preHandle"]
    G --> H["HandlerAdapter.handle"]
    H --> I["Resolve arguments / bind / validate"]
    I --> J["Invoke controller method"]
    J --> K["Handle return value"]
    K --> L["Response body or ModelAndView"]
    L --> M["DispatcherServlet finalizes response"]
    M --> N["HandlerInterceptor.afterCompletion"]
~~~

This diagram depicts the **successful synchronous** flow. In practice, exception handling, early responses, caching/conditional requests, and asynchronous dispatches also exist. Not every request follows every arrow above.

A typical sequence when calling `GET /api/books/42`:

1. Tomcat/Servlet container accepts the request and passes it through Servlet Filters (such as Spring Security if configured).
2. `DispatcherServlet` queries the `HandlerMapping`s in order.
3. `RequestMappingHandlerMapping` finds the `HandlerMethod` matching `@GetMapping("/api/books/{id}")`.
4. `DispatcherServlet` receives a `HandlerExecutionChain` containing the handler and interceptors.
5. `DispatcherServlet` finds a `HandlerAdapter` supporting `HandlerMethod`; normally `RequestMappingHandlerAdapter`.
6. `HandlerInterceptor.preHandle` methods are called; if one returns `false`, execution does not continue to the controller along the normal flow.
7. The adapter resolves `id` to a `long`, prepares any remaining arguments, and invokes the controller method.
8. The return value is processed by the appropriate handler: `ResponseEntity`, `@ResponseBody`, model/view, or async.
9. `DispatcherServlet` completes the request/response; for view-based MVC it may render a view. The interceptor lifecycle concludes according to execution status.

An HTTP response may be written directly during return-value handling, such as a JSON body via `HttpMessageConverter`, in which case there is no traditional template rendering step afterward.

## 3. How Do HandlerMapping, HandlerExecutionChain, and HandlerAdapter Differ?

### 3.1 HandlerMapping

`HandlerMapping` answers "which handler matches this request?" For annotated controllers, **RequestMappingHandlerMapping** builds a map of routes from `@RequestMapping` and specialized annotations like `@GetMapping`.

It evaluates matching criteria such as HTTP method, path, params, headers, `consumes`, and `produces`. If the method does not match, the framework can return 405; if `Content-Type` does not match, 415; if `Accept` does not satisfy `produces`, 406. Do not lump all mismatch cases into "missing HandlerAdapter."

Example:

~~~java
@GetMapping(path = "/api/books/{id}", produces = "application/json")
public BookResponse find(@PathVariable long id) {
    return service.find(id);
}
~~~

The annotation declares how to **select the method** for a request; resolving `id` and calling the method happen during the adapter stage.

### 3.2 HandlerExecutionChain

`HandlerMapping` typically returns a **HandlerExecutionChain**, containing:

- The actual handler (for annotated controllers, usually a `HandlerMethod`).
- The list of `HandlerInterceptor`s applicable to the request.
- Metadata for invoking `preHandle`, `postHandle`, and `afterCompletion`.

Interceptors sit inside the execution chain, **not inside `HandlerAdapter`**. They provide hooks before and after the handler; `DispatcherServlet` coordinates those hooks around the adapter.

### 3.3 HandlerAdapter

`HandlerAdapter` is the execution layer for a handler type supported by the framework. Its core methods conceptually look like:

~~~java
boolean supports(Object handler);

ModelAndView handle(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler) throws Exception;
~~~

This is an **illustrative API excerpt**, not the full interface definition or a separately compilable Java file. The `HandlerAdapter` contract also includes an API for last-modified/conditional request handling in corresponding versions.

- `supports` confirms the adapter understands this handler type.
- `handle` runs the necessary logic and returns a `ModelAndView` (which can be `null` if the response was already handled or the request switched to async).
- `DispatcherServlet` scans its adapter list to find the first adapter that supports the handler.

**`DispatcherServlet` does not directly use Java reflection to invoke every controller method**. Support for `HandlerMethod` and method invocation mechanics are implemented inside the dedicated adapter.

## 4. Common HandlerAdapters in Spring MVC

| HandlerAdapter | Primary handler type | When commonly encountered |
| --- | --- | --- |
| `RequestMappingHandlerAdapter` | `HandlerMethod` from `@RequestMapping` annotations | Most modern REST controllers and annotated MVC controllers |
| `HttpRequestHandlerAdapter` | `org.springframework.web.HttpRequestHandler` | Infrastructure handlers, resource serving, or handlers implementing that specific interface |
| `SimpleControllerHandlerAdapter` | `org.springframework.web.servlet.mvc.Controller` | Traditional Controller-interface style |
| Application-provided adapter | Custom handler types defined by libraries or apps | Special framework integrations or legacy cases |

Do not confuse **SimpleControllerHandlerAdapter** with the `@Controller` annotation. `SimpleControllerHandlerAdapter` serves the legacy `org.springframework.web.servlet.mvc.Controller` interface, whereas `@Controller` using `@RequestMapping` normally goes through `RequestMappingHandlerAdapter`.

Do not write a custom `HandlerAdapter` for everyday needs like reading a new header, converting JSON, pagination, validating data, or customizing responses. Spring MVC already provides **argument resolvers**, **converters**, **return value handlers**, **ControllerAdvice**, **WebMvcConfigurer**, and narrower, better-suited extension points.

## 5. RequestMappingHandlerAdapter: From HandlerMethod to Java Invocation

In the annotated controller flow, the key component is **org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerAdapter**.

Conceptually:

~~~text
DispatcherServlet
  -> HandlerMapping returns HandlerMethod
  -> RequestMappingHandlerAdapter.handle(...)
     -> prepare WebDataBinderFactory and ModelFactory
     -> create ServletInvocableHandlerMethod
     -> resolve method arguments
     -> bind/convert/validate input data when needed
     -> invoke controller Java method
     -> process return value
     -> ModelAndView or response already written/async
  -> DispatcherServlet completes request
~~~

At the implementation level in Spring Framework 6.1, `RequestMappingHandlerAdapter` extends `AbstractHandlerMethodAdapter` and uses **ServletInvocableHandlerMethod** to invoke request-handling methods. It integrates with `HandlerMethodArgumentResolverComposite` and `HandlerMethodReturnValueHandlerComposite`.

Avoid the misconception that the adapter simply calls `handlerMethod.invoke(...)` with a prebuilt array of arguments. Before invoking, Spring MVC must figure out which parameters come from URLs, query strings, HTTP headers, body, model, session, Servlet request/response, and other contexts; afterward, it must decide how the return value is represented.

## 6. What Is HandlerMethod?

`HandlerMethod` describes the binding between:

- The Spring-managed **bean/controller**.
- The Java **method** to invoke.
- **Method parameters**, annotations, return type, and metadata supporting request processing.

Example:

~~~java
@RestController
@RequestMapping("/api/books")
class BookController {

    @GetMapping("/{id}")
    public BookDto get(@PathVariable long id,
                       @RequestParam(defaultValue = "false") boolean upper) {
        return service.get(id, upper);
    }
}
~~~

Given `GET /api/books/42?upper=true`, `HandlerMapping` selects the `HandlerMethod` representing `BookController.get(long, boolean)`. At that moment, the method has not yet executed. The adapter must produce arguments `42` and `true`, invoke the actual method, and then process the returned `BookDto`.

Spring normally manages controllers as singleton beans. Each HTTP request carries its own argument values; therefore, never store path variables, request bodies, or per-request state in mutable fields of a singleton controller.

## 7. Resolving Parameters: HandlerMethodArgumentResolver

### 7.1 General Rules

Spring MVC uses **HandlerMethodArgumentResolver** implementations to answer:

> "For a specific Java parameter, can the framework construct a value from the current request/context?"

Each resolver has two conceptual operations:

~~~java
boolean supportsParameter(MethodParameter parameter);

Object resolveArgument(
        MethodParameter parameter,
        ModelAndViewContainer mavContainer,
        NativeWebRequest webRequest,
        WebDataBinderFactory binderFactory) throws Exception;
~~~

The snippet shows the core signatures of `HandlerMethodArgumentResolver`, is not a standalone Java file, and omits nullable annotations from the Javadoc.

`RequestMappingHandlerAdapter` coordinates multiple resolvers and selects the one matching a parameter. If no resolver supports it, the request can fail while preparing the method call; some unannotated types can be handled by default binding mechanisms, so you cannot assume every unannotated parameter will fail.

### 7.2 Common Parameters

| Controller parameter | Data source | Typical mechanism |
| --- | --- | --- |
| `@PathVariable long id` | Variable in route `/books/{id}` | Path variable resolver and type conversion |
| `@RequestParam int page` | Query/form parameter | Request-param resolver and type conversion |
| `@RequestHeader String traceId` | HTTP header | Header resolver |
| `@CookieValue String token` | HTTP cookie | Cookie-value resolver |
| `@RequestBody CreateBookRequest request` | HTTP body, usually JSON | `RequestResponseBodyMethodProcessor` + `HttpMessageConverter` |
| `@ModelAttribute SearchForm form` | Query/form fields and model binding | Model-attribute resolver + `WebDataBinder` |
| `HttpServletRequest`, `HttpServletResponse` | Servlet request/response | Servlet-specific argument resolver |
| `Model`, `ModelMap` | MVC model | Model argument resolver |
| `Principal` | Servlet/security principal when present | Principal resolver |
| `BindingResult` | Binding/validation result of the immediately preceding object | `BindingResult`-related resolver |
| `@RequestPart MultipartFile file` | Multipart request | Request-part/multipart resolution |

This table shows typical flows; some annotations have additional rules regarding `required`, default values, multipart handling, and request content.

### 7.3 Where Do Values Come From?

Given:

~~~java
@GetMapping("/books/{id}")
public ResponseEntity<BookDto> get(
        @PathVariable long id,
        @RequestParam(defaultValue = "false") boolean upper,
        @RequestHeader(name = "X-Trace-Id", required = false) String traceId) {
    // ...
}
~~~

Request:

~~~http
GET /books/42?upper=true HTTP/1.1
Host: localhost:8080
X-Trace-Id: req-7
~~~

Conceptually, the Java arguments become:

~~~text
id      = 42L
upper   = true
traceId = "req-7"
~~~

Converting `"42"` to `long` and `"true"` to `boolean` normally uses the built-in conversion/binding system. If `id` cannot be converted to `long`, the controller method is not invoked as a valid request; Spring MVC can produce a 400 response via default exception handling.

Do not manually parse all request parameters with `request.getParameter` inside a controller when Spring MVC already provides suitable resolvers.

## 8. @RequestBody, JSON, and HttpMessageConverter

When a parameter is annotated with `@RequestBody`, Spring MVC typically uses **RequestResponseBodyMethodProcessor** and an appropriate **HttpMessageConverter** to read the HTTP body.

Typical flow:

~~~text
POST /api/books
Content-Type: application/json
body: {"title":"Spring MVC"}

@RequestBody CreateBookRequest input
  -> select converter supporting media type and Java type
  -> read bytes / JSON into Java object
  -> check @Valid when requested
  -> pass object as method argument
~~~

With Spring Boot's default web starter and Jackson on the classpath, `MappingJackson2HttpMessageConverter` usually handles JSON.

**`HttpMessageConverter` does not invoke controller methods itself**: it only converts between HTTP bodies and Java objects. `RequestMappingHandlerAdapter` orchestrates argument resolution and invocation, while the message converter is a component used by resolvers and return-value handlers.

Cases to distinguish:

- **Content-Type** indicates the format of the body sent by the client; when unsupported, it can result in `415 Unsupported Media Type`.
- A body that is invalid JSON or fails deserialization can result in `400 Bad Request`.
- Missing body when `@RequestBody(required = true)` can result in `400`.
- `@Valid` applies Bean Validation to eligible objects; if validation fails without handling `BindingResult` directly, `MethodArgumentNotValidException` is normally raised.
- Do not manually read the Servlet request input stream beforehand and expect `@RequestBody` to read it again without a wrapper; standard body streams cannot be arbitrarily reread.

**`@RequestBody` and `@ModelAttribute` are not equivalent.** `@RequestBody` reads the payload through a message converter; `@ModelAttribute` binds from request parameters and the model, typically suited for forms/queries.

## 9. WebDataBinder, @InitBinder, and Bean Validation

Once an argument resolver locates the data source, binding/conversion may use **WebDataBinder** and `ConversionService`. `@InitBinder` lets you customize binding or validators within a controller or `@ControllerAdvice` when there is a clear reason.

Example:

~~~java
@InitBinder
public void configureBinder(WebDataBinder binder) {
    binder.setDisallowedFields("admin");
}
~~~

This snippet only illustrates a binding hook and **is not a standalone class**. It is also not the only defense against mass assignment; designing request DTOs containing only editable fields is usually clearer and safer. Do not bind directly onto domain objects containing sensitive fields and rely solely on a blacklist.

Bean Validation:

~~~java
public record CreateBookRequest(@NotBlank String title) {
}
~~~

When used:

~~~java
@PostMapping
public ResponseEntity<BookDto> create(
        @Valid @RequestBody CreateBookRequest input) {
    // ...
}
~~~

Spring MVC validates input via Jakarta Validation if a provider and required dependencies are present. Spring Boot 3.x typically needs **spring-boot-starter-validation** if the application wants full `@NotBlank` and validation provider support.

When validation fails:

- **MethodArgumentNotValidException** typically applies when validating `@RequestBody` or `@ModelAttribute` without handling errors via an adjacent `BindingResult`.
- **HandlerMethodValidationException** can relate to method validation in Spring Framework 6.1, such as constraints placed directly on method parameters or return values.
- **BindingResult** must be placed immediately after the parameter receiving binding/validation results in supported cases.

Do not collapse all validation errors into a single fixed exception class; the framework version, annotations, and constraint types determine the exact path.

## 10. Invoking the Actual Handler Method

Once parameters are resolved, `ServletInvocableHandlerMethod` (in the annotated MVC controller infrastructure) invokes the selected Java method. That invocation may pass through proxies and other Spring mechanisms when the bean is managed with AOP, depending on configuration.

Example:

~~~java
@GetMapping("/books/{id}")
public BookDto find(@PathVariable long id) {
    return catalog.find(id);
}
~~~

Here:

1. `DispatcherServlet` has already identified the `HandlerMethod`.
2. `RequestMappingHandlerAdapter` selects and resolves the `id` parameter.
3. The framework invokes `BookController.find(42L)` on the managed controller instance.
4. The controller may call services, repositories, or other clients.
5. `BookDto` is handed to a return value handler.
6. Because the controller is annotated with `@RestController`, the return value is processed with `@ResponseBody` semantics and usually serialized to JSON.

If the service throws an exception, the adapter cannot finish the normal success path; the exception is handed to `DispatcherServlet`'s error handling chain. Do not assume every exception is caught by a `try/catch` inside the controller.

### Singleton Beans and Thread Safety

Controller beans are normally singletons: multiple requests can invoke the same instance concurrently. Per-request data should live in method parameters, local variables, or an appropriately scoped abstraction. A shared field like `currentId` across all requests can cause race conditions.

Depending on the stack and Servlet async, initial method invocation usually runs on the Servlet request thread; if the controller returns an async type, completion may happen on another thread. Do not assume a single thread always handles every request from start to finish.

### @Transactional and Proxies

`@Transactional` is not a step built into `HandlerAdapter` itself. If a controller method calls a Spring service proxy with a transaction interceptor, the transaction boundary wraps the service method via AOP. Argument binding and JSON serialization do not automatically fall inside that transaction just because the controller called the service. Place transactions at the required application layer and avoid holding blocking logic/transactions open across slow I/O.

## 11. Processing Return Values: HandlerMethodReturnValueHandler

After the method returns a value, Spring MVC uses an appropriate **HandlerMethodReturnValueHandler** to decide how to build the HTTP response.

Scenarios:

| Return type or annotation | How it is interpreted |
| --- | --- |
| `@ResponseBody BookDto`, or `BookDto` in `@RestController` | Serialize object to HTTP body via `HttpMessageConverter` |
| `ResponseEntity<BookDto>` | Apply status/headers/body from `ResponseEntity`, usually using a converter for the body |
| `String` from `@Controller` without `@ResponseBody` | Usually a view name for `ViewResolver` to process |
| `ModelAndView` | Provides model + view to `DispatcherServlet` |
| `void` + already wrote to `HttpServletResponse` | Can be treated as a handled response; depends on annotations/context |
| `Callable<T>`, `DeferredResult<T>` | Initiates asynchronous processing on the Servlet stack |
| `CompletionStage<T>`, framework-supported reactive types | Can be adapted into Spring MVC async processing |
| `@ResponseStatus` | Sets HTTP status per annotation configuration when applicable |

Distinguish:

~~~java
@Controller
class PageController {

    @GetMapping("/home")
    public String home() {
        return "home"; // view name, not necessarily HTTP body "home"
    }
}
~~~

from:

~~~java
@RestController
class ApiController {

    @GetMapping("/home")
    public String home() {
        return "home"; // HTTP body "home"
    }
}
~~~

These two snippets only illustrate semantics, not two standalone compilable files with full imports. `@RestController` is equivalent to `@Controller` combined with `@ResponseBody` at the return-value handling level.

For JSON, **RequestResponseBodyMethodProcessor** can handle both `@RequestBody` parameters and `@ResponseBody` return values. For `ResponseEntity`, **HttpEntityMethodProcessor** is a common return-value/argument handler.

For REST APIs, the response body is usually already written by return-value handling; `DispatcherServlet` does not proceed to render JSP/Thymeleaf. For view-based web MVC, the adapter can return a `ModelAndView` for `DispatcherServlet` to pick a `ViewResolver` and render.

## 12. HTTP Status, Headers, and Content Negotiation

Example:

~~~java
return ResponseEntity
        .created(URI.create("/api/books/101"))
        .header("X-Source", "catalog")
        .body(book);
~~~

Semantically:

- Status is `201 Created`.
- `Location` header contains the URI `/api/books/101`.
- `X-Source` is a custom response header.
- `book` is serialized according to the converter and negotiated media type.

`RequestMappingHandlerAdapter` does not decide URL paths for requests by itself. `HandlerMapping` evaluates `consumes`/`produces` conditions; return-value handling and message converters also participate in choosing the body media type. If `Accept: application/xml` is sent when the app only has a JSON converter and cannot satisfy it, the result can be `406 Not Acceptable`.

Adding `@ResponseStatus(HttpStatus.CREATED)` can also declare status in suitable cases; `ResponseEntity` is useful when you want explicit control over both headers and body.

## 13. How Are Interceptors Called Before and After the Adapter?

`HandlerInterceptor` provides three familiar hooks:

~~~java
boolean preHandle(HttpServletRequest request,
                  HttpServletResponse response, Object handler);

void postHandle(HttpServletRequest request,
                HttpServletResponse response, Object handler,
                ModelAndView modelAndView);

void afterCompletion(HttpServletRequest request,
                     HttpServletResponse response, Object handler,
                     Exception ex);
~~~

These are conceptual signatures (omitting `throws`/annotations), not a complete Java file.

- **preHandle**: after finding the handler, before the adapter executes the controller. Return `false` to halt the execution chain along the normal path; the interceptor must ensure an appropriate response if it blocks the request.
- **postHandle**: after the adapter handles the handler successfully, before `DispatcherServlet` renders a view. `ModelAndView` may be `null`, especially for REST body responses.
- **afterCompletion**: completion callback at the end of synchronous processing for interceptors whose `preHandle` succeeded; invoked even when exceptions occur during dispatch per framework rules.

If an interceptor's `preHandle` returns `false`, not all hooks on that same interceptor will run as in a successful flow. If the controller switches to Servlet async, **AsyncHandlerInterceptor.afterConcurrentHandlingStarted** runs instead of the synchronous completion hooks on the initial dispatch; a subsequent dispatch can trigger hooks again at different points.

**Security note:** `HandlerInterceptor` does not replace the Servlet Filter chain or Spring Security. Requests such as static resources, preflight, error dispatches, or other paths can have different scopes; authentication/authorization should use security mechanisms designed for the Servlet stack.

## 14. Handling Exceptions from the Adapter/Controller

A controller can throw an exception during service execution, parameter validation, request body parsing, or response writing. `DispatcherServlet` coordinates registered **HandlerExceptionResolver**s to convert the exception into an appropriate response or view.

Common components:

- **ExceptionHandlerExceptionResolver**: supports `@ExceptionHandler` inside controllers and `@ControllerAdvice`/`@RestControllerAdvice`.
- **ResponseStatusExceptionResolver**: supports status signals from annotations or `ResponseStatusException`.
- **DefaultHandlerExceptionResolver**: handles standard Spring MVC exceptions with corresponding HTTP statuses where possible.

Example:

~~~java
@RestControllerAdvice
class ErrorAdvice {

    @ExceptionHandler(BookNotFoundException.class)
    ResponseEntity<Map<String, String>> notFound(BookNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(Map.of("error", ex.getMessage()));
    }
}
~~~

This snippet is presented as part of the example application below, where full classes, imports, and dependencies are provided.

Common errors:

| Error | Typical stage | Possible response |
| --- | --- | --- |
| Route not found | `HandlerMapping` | 404 |
| HTTP method unsupported by mapping | Mapping conditions | 405 |
| `Content-Type` unsupported | Mapping/message conversion | 415 |
| `Accept` has no matching representation | Negotiation/return handling | 406 |
| `@PathVariable long id` receives unparseable string | Argument conversion | 400 |
| Malformed JSON body | `HttpMessageConverter` reading request | 400 |
| `@Valid @RequestBody` violates constraint | Argument validation | 400 |
| Controller explicitly throws `BookNotFoundException` | Handler invocation | Depends on `@ExceptionHandler`; 404 in the example |
| No `HandlerAdapter` supports handler type | `DispatcherServlet` adapter selection | Framework/handler configuration error; not fixed with `@RequestBody` |

Do not catch every exception and return `200 OK` to avoid "HTTP errors." HTTP status codes must reflect actual outcomes; internal logs should not leak stack traces or sensitive details to clients.

## 15. Async Handlers and How They Alter the DispatcherServlet Flow

Spring MVC supports asynchronous processing on top of Servlets. `HandlerAdapter` can initiate async processing when a controller returns `Callable`, `DeferredResult`, or other adapter-supported types.

Illustrative example:

~~~java
@GetMapping("/slow")
public Callable<ResponseEntity<String>> slow() {
    return () -> ResponseEntity.ok("done");
}
~~~

This method can be placed inside a `@RestController` with appropriate imports. The framework can start Servlet async, release the initial request thread, execute the `Callable` via a task executor, and re-dispatch when the result is ready. The method still belongs to **Spring MVC/DispatcherServlet**, not WebFlux.

Points to remember:

1. Thread and timing of `HandlerInterceptor` callbacks may differ from synchronous requests.
2. Return-value handlers and `WebAsyncManager` collaborate in orchestration.
3. Async timeouts and exception resolvers still need to be designed and tested.
4. The thread pool for `Callable` must be sized appropriately for blocking work; async does not automatically convert blocking operations into non-blocking I/O.
5. Do not assume `postHandle` and `afterCompletion` always run on the first dispatch.
6. For reactive return types like `Mono`/`Flux` supported in MVC, Spring MVC uses adapters for async integration; the Servlet stack remains the HTTP processing stack.

Distinguish **async request handling** from **Spring WebFlux**: MVC async is built on Servlet async processing; WebFlux uses reactive HTTP abstractions and `DispatcherHandler`.

## 16. Complete Runnable Example with Spring Boot 3.3 and Java 17

Let us build a simple book API to verify each step end-to-end:

- `GET /api/books/{id}` accepting `@PathVariable`, `@RequestParam`, `@RequestHeader`.
- `POST /api/books` accepting `@Valid @RequestBody` JSON.
- Controller calls a service; the service returns a DTO or throws a custom exception.
- Return value is a `ResponseEntity` with status/header/body.
- `@RestControllerAdvice` handles exceptions.
- `HandlerInterceptor` adds a header to observe `preHandle`.
- Integration test uses `MockMvc` to verify mapping/binding/response.

### 16.1 Directory Structure

~~~text
mvc-handler-adapter-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/mvcdemo/
    │   ├── MvcDemoApplication.java
    │   ├── BookController.java
    │   ├── BookCatalog.java
    │   ├── ErrorAdvice.java
    │   └── WebFlowConfig.java
    └── test/java/com/example/mvcdemo/
        └── BookControllerTest.java
~~~

### 16.2 settings.gradle

~~~groovy
rootProject.name = 'mvc-handler-adapter-demo'
~~~

### 16.3 build.gradle

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
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-web` provides Spring MVC and standard embedded Tomcat; `spring-boot-starter-validation` provides Jakarta Bean Validation; `spring-boot-starter-test` provides JUnit 5, Spring Test, and `MockMvc`. If you use the Gradle wrapper, substitute `gradle` with `./gradlew` on Linux/macOS or `gradlew.bat` on Windows.

### 16.4 MvcDemoApplication.java

~~~java
package com.example.mvcdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MvcDemoApplication.class, args);
    }
}
~~~

### 16.5 BookCatalog.java

~~~java
package com.example.mvcdemo;

import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;

@Service
public class BookCatalog {

    private final Map<Long, String> books =
            new ConcurrentHashMap<>(Map.of(42L, "Spring MVC"));
    private final AtomicLong nextId = new AtomicLong(100);

    public BookResponse find(long id, boolean upper, String traceId) {
        String name = books.get(id);
        if (name == null) {
            throw new BookNotFoundException(id);
        }
        String displayName = upper ? name.toUpperCase(Locale.ROOT) : name;
        return new BookResponse(id, displayName, traceId);
    }

    public BookResponse create(CreateBookRequest request) {
        long id = nextId.incrementAndGet();
        books.put(id, request.title());
        return new BookResponse(id, request.title(), null);
    }
}

class BookNotFoundException extends RuntimeException {

    BookNotFoundException(long id) {
        super("Book " + id + " not found");
    }
}

record BookResponse(long id, String title, String traceId) {
}
~~~

`ConcurrentHashMap` and `AtomicLong` are only for concurrent in-memory demonstration; production applications require a database and proper ID allocation strategy. The `BookResponse` record is serialized to its corresponding fields by Jackson in Spring Boot 3.3.

### 16.6 BookController.java

~~~java
package com.example.mvcdemo;

import java.net.URI;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/books")
public class BookController {

    private final BookCatalog catalog;

    public BookController(BookCatalog catalog) {
        this.catalog = catalog;
    }

    @GetMapping("/{id}")
    public ResponseEntity<BookResponse> find(
            @PathVariable long id,
            @RequestParam(defaultValue = "false") boolean upper,
            @RequestHeader(name = "X-Trace-Id", required = false)
                    String traceId) {

        BookResponse book = catalog.find(id, upper, traceId);
        return ResponseEntity.ok()
                .header("X-Source", "catalog")
                .body(book);
    }

    @PostMapping
    public ResponseEntity<BookResponse> create(
            @Valid @RequestBody CreateBookRequest request) {

        BookResponse created = catalog.create(request);
        return ResponseEntity
                .created(URI.create("/api/books/" + created.id()))
                .body(created);
    }
}

record CreateBookRequest(@NotBlank String title) {
}
~~~

`@PathVariable long id` asks Spring MVC to resolve `id` from the route; `@RequestParam boolean upper` reads and converts the query parameter; `@RequestHeader` extracts the optional header. For `POST`, `@RequestBody` + Jackson converts JSON into the `CreateBookRequest` record and `@Valid` runs the validator before calling `create`.

### 16.7 ErrorAdvice.java

~~~java
package com.example.mvcdemo;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ErrorAdvice {

    @ExceptionHandler(BookNotFoundException.class)
    public ResponseEntity<Map<String, String>> bookNotFound(
            BookNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(Map.of("error", ex.getMessage()));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, String>> invalidBody(
            MethodArgumentNotValidException ex) {
        return ResponseEntity.badRequest()
                .body(Map.of("error", "title must not be blank"));
    }
}
~~~

Because the example has only one `@NotBlank` constraint, a fixed error message makes testing easy. In a real system, build an error response with stable error codes, necessary field errors, and avoid exposing sensitive data.

### 16.8 WebFlowConfig.java

~~~java
package com.example.mvcdemo;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebFlowConfig implements WebMvcConfigurer {

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new HandlerTraceInterceptor())
                .addPathPatterns("/api/**");
    }

    static class HandlerTraceInterceptor implements HandlerInterceptor {

        @Override
        public boolean preHandle(
                HttpServletRequest request,
                HttpServletResponse response,
                Object handler) {
            response.addHeader("X-Handler-Interceptor", "preHandle");
            return true;
        }
    }
}
~~~

This demonstrates the `preHandle` hook in the execution chain, not a production tracing system. The header appears when the interceptor participates in `/api/**` requests and the response is not yet committed; with a regular controller, it lets you observe that the request passed through the interceptor step before the handler call.

### 16.9 Build and Run

In the project directory:

~~~bash
gradle clean test bootRun
~~~

In another terminal, call:

~~~bash
curl -i -H 'X-Trace-Id: req-7' \
  'http://localhost:8080/api/books/42?upper=true'
~~~

Expect HTTP 200, headers `X-Source: catalog`, `X-Handler-Interceptor: preHandle`, and a JSON body equivalent to:

~~~json
{"id":42,"title":"SPRING MVC","traceId":"req-7"}
~~~

JSON field order and infrastructure headers may vary, so do not compare the entire response byte-for-byte.

Create a new book:

~~~bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  -d '{"title":"Web Layer"}'
~~~

Against a fresh instance with no prior POSTs, expected response is HTTP 201, header `Location: /api/books/101`, and body equivalent to:

~~~json
{"id":101,"title":"Web Layer","traceId":null}
~~~

If the application already handled prior POST requests, `id` may differ from 101 due to the in-memory counter.

Invalid input:

~~~bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  -d '{"title":""}'
~~~

Expected HTTP 400 and body:

~~~json
{"error":"title must not be blank"}
~~~

Because `@Valid` rejects the input before controller `create` runs, `@ExceptionHandler` in `ErrorAdvice` produces the 400 response.

Non-existent book:

~~~bash
curl -i 'http://localhost:8080/api/books/9999'
~~~

Expected HTTP 404 and body equivalent to:

~~~json
{"error":"Book 9999 not found"}
~~~

These outputs are **expected results derived from the example code**, not captured execution logs.

### 16.10 BookControllerTest.java

~~~java
package com.example.mvcdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BookControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void resolvesArgumentsAndWritesResponse() throws Exception {
        mockMvc.perform(get("/api/books/{id}", 42L)
                .param("upper", "true")
                .header("X-Trace-Id", "test-1"))
            .andExpect(status().isOk())
            .andExpect(header().string("X-Source", "catalog"))
            .andExpect(header().string(
                    "X-Handler-Interceptor", "preHandle"))
            .andExpect(jsonPath("$.title").value("SPRING MVC"))
            .andExpect(jsonPath("$.traceId").value("test-1"));
    }

    @Test
    void validatesRequestBodyBeforeInvocation() throws Exception {
        mockMvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"\"}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error")
                    .value("title must not be blank"));
    }

    @Test
    void resolvesControllerException() throws Exception {
        mockMvc.perform(get("/api/books/{id}", 9999L))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.error")
                    .value("Book 9999 not found"));
    }
}
~~~

Run:

~~~bash
gradle test
~~~

`MockMvc` invokes the Spring MVC dispatcher and handler pipeline via mock Servlet request/response objects, **without starting a listening socket on port 8080** in this test configuration. The tests verify mapping, argument resolution, validation, controller invocation, exception resolution, and response processing. To test real TCP traffic, use `@SpringBootTest(webEnvironment = RANDOM_PORT)` with an appropriate HTTP client/test utility.

## 17. Extension Point: Adding a Custom Argument Resolver

An application may want controllers to accept a custom type, such as `ClientTag` from the `X-Client-Tag` header:

~~~java
record ClientTag(String value) {
}
~~~

You can implement `HandlerMethodArgumentResolver` supporting specifically `ClientTag`, then register it via `WebMvcConfigurer#addArgumentResolvers`.

Illustrative logic pattern:

~~~java
@Override
public boolean supportsParameter(MethodParameter parameter) {
    return parameter.getParameterType().equals(ClientTag.class);
}

@Override
public Object resolveArgument(
        MethodParameter parameter,
        ModelAndViewContainer container,
        NativeWebRequest request,
        WebDataBinderFactory binderFactory) {
    String header = request.getHeader("X-Client-Tag");
    return new ClientTag(header == null ? "anonymous" : header);
}
~~~

These methods are **illustrative implementation excerpts only**, not a self-compiling Java file: you need a class implementing `HandlerMethodArgumentResolver`, imports, and bean/config registration. `WebMvcConfigurer` provides the hook:

~~~java
@Override
public void addArgumentResolvers(
        List<HandlerMethodArgumentResolver> resolvers) {
    resolvers.add(new ClientTagArgumentResolver());
}
~~~

This snippet is also just an illustrative method inside `WebMvcConfigurer`, not a complete class.

Note on ordering: `WebMvcConfigurer#addArgumentResolvers` appends resolvers alongside standard resolvers; built-in annotation-based resolvers and other groups may have higher priority per framework ordering. If you want to completely change the list or override standard resolvers, `RequestMappingHandlerAdapter` provides `setArgumentResolvers`/`setCustomArgumentResolvers`, though replacing the entire list can drop support for `@PathVariable`, `@RequestBody`, or `@RequestParam`.

Only build a custom resolver when many endpoints repeat the same custom data extraction logic. For a simple single parameter from a header, `@RequestHeader` is usually clearer and less risky.

## 18. Extension Point: Customizing Return Values

`HandlerMethodReturnValueHandler` has two conceptual operations:

~~~java
boolean supportsReturnType(MethodParameter returnType);

void handleReturnValue(
        Object returnValue,
        MethodParameter returnType,
        ModelAndViewContainer mavContainer,
        NativeWebRequest webRequest) throws Exception;
~~~

This illustrates the API while omitting nullable annotations. Customizing return handlers makes sense when an application has a specialized response wrapper type that the framework truly needs to understand as a return type.

However, in most REST APIs:

- Use `ResponseEntity` to control status/headers/body.
- Use `@RestControllerAdvice` to standardize errors.
- Use `ResponseBodyAdvice` to modify bodies in appropriate scenarios.
- Use `HttpMessageConverter` or Jackson configuration for serialization.
- Use Filters/interceptors when the goal is the request lifecycle rather than a return type.

`RequestMappingHandlerAdapter` can register custom return-value handlers, but ordering relative to built-in handlers is critical. Do not replace the entire list without understanding the impact on HTTP entities, `@ResponseBody`, view names, async return types, and special handlers.

## 19. How to Debug HandlerAdapter and Method Invocation

### 19.1 Enable Selective Logging

In `application.properties` for local/test environments:

~~~properties
logging.level.org.springframework.web.servlet.DispatcherServlet=DEBUG
logging.level.org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping=TRACE
logging.level.org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerAdapter=TRACE
~~~

`TRACE` level can generate substantial log volume. Enable it selectively and avoid logging sensitive data in production. Depending on version/config, mapping and argument details may be masked by Spring; do not force full request body logging without proper data protection measures.

### 19.2 Check Whether the Endpoint Is Mapped

When `GET /api/books/42` returns 404:

1. Check if the controller is within component scan.
2. Verify `@RequestMapping` on the class and `@GetMapping` on the method.
3. Compare request path, Servlet context path, path matching, and HTTP method.
4. Check whether an interceptor or filter blocked the request before the controller.
5. Check mapping logs or Actuator mappings if Actuator is installed and the endpoint is enabled.
6. Only once a handler is found should you investigate adapter/argument resolution.

A missing `HandlerAdapter` is rarely the cause of a 404 in a normal annotated-controller project.

### 19.3 Controller Mapped, But Method Doesn't Run?

Check:

- Did `preHandle` return `false`?
- Did an argument resolver throw an exception before invoking the method?
- Is `@RequestBody` JSON properly formatted with the right `Content-Type`?
- Did binding/validation reject the input?
- Is the controller bean proxied as expected?
- Did an `ExceptionHandler` swallow an exception and return a different status?
- Did an async dispatch move breakpoints/logs onto another thread?

### 19.4 Breakpoints to Understand the Real Pipeline

With the matching Spring Framework source code in your IDE, set breakpoints at these points:

~~~text
DispatcherServlet.doDispatch
DispatcherServlet.getHandler
DispatcherServlet.getHandlerAdapter
RequestMappingHandlerAdapter.handleInternal
RequestMappingHandlerAdapter.invokeHandlerMethod
ServletInvocableHandlerMethod.invokeAndHandle
InvocableHandlerMethod.getMethodArgumentValues
HandlerMethodArgumentResolverComposite.resolveArgument
HandlerMethodReturnValueHandlerComposite.handleReturnValue
~~~

Not every method is called with the exact same stack frame or strict order across versions; these are **suggested observation points**. Attach a debugger matching your runtime library version and inspect `HandlerMethod`, argument values, return value, and exceptions.

## 20. FAQ and Common Misconceptions

**Q1. If HandlerMapping already picked the controller, what is left for HandlerAdapter?**

`HandlerMapping` only chooses the handler. `HandlerAdapter` turns that handler into an invocation with bound/validated arguments and interprets the return value. For annotated controllers, `RequestMappingHandlerAdapter` performs this orchestration.

**Q2. Is HandlerAdapter an HttpMessageConverter?**

No. Converters read/write bodies, whereas the adapter orchestrates the entire invocation pipeline and delegates to converters when argument resolvers or return-value handlers need them.

**Q3. Does @GetMapping invoke the Java method directly?**

No. `@GetMapping` contributes mapping metadata; the method is invoked through `HandlerMethod`/`RequestMappingHandlerAdapter` infrastructure after the request matches and arguments are prepared.

**Q4. Do @RestController and @Controller use different HandlerAdapters?**

Not necessarily. Both typically go through `RequestMappingHandlerAdapter` when using `@RequestMapping`. The crucial difference lies in `@ResponseBody` semantics and return-value handling.

**Q5. Why does a matched method still return 400?**

Argument conversion, JSON deserialization, or validation can fail before the method is invoked. Inspect the root exception and the controller parameters.

**Q6. Can Mono/Flux be used in Spring MVC?**

Certain reactive return types can be adapted by Spring MVC onto the Servlet async mechanism. Doing so does not switch the server from `DispatcherServlet` to WebFlux `DispatcherHandler`.

**Q7. Why didn't postHandle modify the JSON response as expected?**

With `@ResponseBody`, the body may already have been written by the return-value handler before `postHandle` runs. Use `ResponseBodyAdvice` or an appropriate response layer instead of trying to alter bytes in `postHandle`.

**Q8. Should you replace the default RequestMappingHandlerAdapter bean to log every request?**

Usually no. Use targeted logging/tracing, Servlet Filters, `HandlerInterceptor`, `ControllerAdvice`, or an observation framework. Replacing core beans can break Boot's resolver/converter/async pipeline.

**Q9. When does HandlerExceptionResolver run?**

When an exception occurs during the dispatch chain and reaches the exception resolution mechanism. Not every error passes through it: some errors are intercepted at Servlet Filters, the container, proxies, or happen after the response is committed.

**Q10. What happens if no adapter supports a handler?**

`DispatcherServlet` cannot invoke that handler type through the MVC pipeline and reports the corresponding configuration/dispatch error. For `HandlerMethod`s from `@RequestMapping` in a normal Boot MVC app, `RequestMappingHandlerAdapter` is registered automatically, so this situation is rare unless custom configuration drops standard components.

## 21. Practical Checklist

1. Confirm the application actually runs **Spring MVC/Servlet** rather than a WebFlux server.
2. Verify the request passed through Servlet Filters/Security to `DispatcherServlet`.
3. Verify `HandlerMapping` selects the expected `HandlerMethod`.
4. Check whether any interceptor in `HandlerExecutionChain` blocks with `preHandle` returning `false`.
5. Verify `DispatcherServlet` finds an adapter supporting the handler.
6. Trace parameters produced by argument resolvers from path/query/header/body.
7. Check `ConversionService`, `WebDataBinder`, and `@Valid` when conversion/validation errors occur.
8. Set a breakpoint inside the controller/service to confirm the method actually runs.
9. Trace `HandlerMethodReturnValueHandler` and converters to check status/header/body or view.
10. When an exception occurs, inspect `@ExceptionHandler` and `HandlerExceptionResolver` rather than looking only at the HTTP code.
11. For async, inspect the Servlet async lifecycle and threads/timeouts.
12. Test using `MockMvc` and an HTTP client for both the happy path and 400/404/415/406 as needed.

## 22. Summary

Spring MVC separates **routing** from **executing** HTTP handlers. `DispatcherServlet` receives the request; `HandlerMapping` selects the handler along with its interceptor chain; `HandlerAdapter`—usually `RequestMappingHandlerAdapter` for annotated controllers—prepares input data, invokes the controller method, and processes the return value. Argument resolvers, data binding/validation, message converters, return-value handlers, and exception resolvers work together to turn an HTTP request into a safe, extensible, and testable Java invocation.

**To debug "whether a controller method was called," trace `HandlerMapping` → `HandlerExecutionChain`/`preHandle` → `HandlerAdapter` → argument resolvers → method invocation → return-value/exception handling.** Do not modify another layer before identifying which layer produced the error.

## 23. References

- Spring Framework 6.1 — `DispatcherServlet` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/DispatcherServlet.html
- Spring Framework 6.1 — `RequestMappingHandlerAdapter` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/RequestMappingHandlerAdapter.html
- Spring Framework — MVC DispatcherServlet: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet.html
- Spring Framework — Annotated Controllers: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller.html
- Spring Framework — Handler Method Arguments: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html
- Spring Framework — Handler Method Return Values: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/return-types.html
- Spring Framework — Asynchronous Requests: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Boot 3.3 — Servlet Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html