# Argument Resolution, Controller Invocation, and Return Value Handling in Spring MVC

A method in a Spring MVC controller can declare `@PathVariable long id`, `@RequestParam String sort`, `@RequestBody CreateBookRequest input`, `Model model`, or `HttpServletRequest request`. The client does not directly invoke the Java method, nor does it construct those objects itself. **Spring MVC selects a handler, resolves each parameter from the appropriate data source and rules, executes the method, and then converts the return value into an HTTP response or model/view.**

This lesson explains the three consecutive stages in **Spring MVC on the Servlet stack**: *argument resolution* → *controller invocation* → *return value handling*. This is the core mechanism behind annotation-based controllers in Spring Framework 6.x / Spring Boot 3.x using Java 17+. Spring WebFlux has a different pipeline and abstractions; do not apply MVC classes like `RequestMappingHandlerAdapter` or `ServletInvocableHandlerMethod` directly to WebFlux.

## 1. Goals and the Big Picture

After this lesson, you will be able to:

- Describe the roles of `DispatcherServlet`, `HandlerMapping`, `HandlerAdapter`, `RequestMappingHandlerAdapter`, and `HandlerMethod`.
- Explain how `HandlerMethodArgumentResolver` produces values for each parameter: path, query, header, cookie, request body, model, or context.
- Distinguish **simple type conversion**, **data binding**, **JSON deserialization**, and **validation**.
- Understand how `@Controller` + view name differs from `@RestController`/`@ResponseBody`.
- Know how `HandlerMethodReturnValueHandler`, `HttpMessageConverter`, `ModelAndView`, `ResponseEntity`, and exception resolvers affect the response.
- Read a real controller and predict status, headers, body, 400/404/406/415 errors, and the order of steps.

Diagram of a request passing through MVC:

~~~text
HTTP request
    |
    v
Servlet container → Filter chain → DispatcherServlet
                                      |
                                      v
                               HandlerMapping
                       find matching HandlerMethod
                                      |
                                      v
                      RequestMappingHandlerAdapter
                                      |
              +-----------------------+---------------------+
              |                                             |
              v                                             |
    HandlerMethodArgumentResolver(s)                        |
    + path/query/header/cookie                              |
    + body ↔ HttpMessageConverter                            |
    + @ModelAttribute ↔ DataBinder                           |
    + validation / BindingResult                             |
              |                                             |
              v                                             |
         Java arguments                                     |
              |                                             |
              v                                             |
     invoke controller method                               |
              |                                             |
              v                                             |
    HandlerMethodReturnValueHandler(s)                       |
    + @ResponseBody/ResponseEntity → converter → HTTP body   |
    + String/ModelAndView → model & view → ViewResolver      |
    + async wrapper → async request processing               |
              |                                             |
              +----------------------+----------------------+
                                     |
                                     v
                          HTTP status + headers + body
~~~

The diagram is a conceptual model. A `HandlerInterceptor`, `@ControllerAdvice`, exception resolver, security filter, async dispatch, or template engine can participate in each step depending on configuration. Do not infer that the controller is always invoked when a request produces an error status: many errors occur **before the method runs**.

## 2. Spring MVC Finds the Handler Before Resolving Parameters

### 2.1. HandlerMapping and HandlerAdapter Have Separate Responsibilities

`DispatcherServlet` receives the request dispatched by the Servlet container. It queries `HandlerMapping` beans to obtain a handler and associated interceptors. For annotation-based controllers, `RequestMappingHandlerMapping` typically identifies a `HandlerMethod` representing a Java method together with the corresponding controller bean.

Example:

~~~java
@RestController
@RequestMapping("/api/books")
class BookController {
    @GetMapping("/{id}")
    public String get(@PathVariable long id) {
        return "book-" + id;
    }
}
~~~

With `GET /api/books/42`, handler matching evaluates **HTTP method, URL path, and request mapping conditions**. `HandlerMethod` holds information such as the Java method `get` and the controller bean to invoke. `HandlerMapping` does not parse the request body into a DTO to call the method.

After finding the handler, `DispatcherServlet` picks a `HandlerAdapter` capable of executing it. For a `HandlerMethod` of annotated controllers, the typical adapter is **`RequestMappingHandlerAdapter`**. Thanks to the `HandlerAdapter` abstraction, `DispatcherServlet` does not need to know the invocation details of each handler style.

### 2.2. Responsibilities of RequestMappingHandlerAdapter

`RequestMappingHandlerAdapter` is responsible for preparing the invocation environment for an annotated controller, including:

1. Obtaining metadata of the matched controller method.
2. Preparing `ModelAndViewContainer`, model, related `@ModelAttribute`s, and the binding context.
3. Supplying the list of argument resolvers to build each Java argument.
4. Invoking the method through the invocable handler method layer.
5. Delegating to return-value handlers to process the object returned by the controller.
6. Providing a `ModelAndView` to `DispatcherServlet` when view rendering is needed, or marking the response as already handled.

Related classes in Spring MVC include `ServletInvocableHandlerMethod`, `InvocableHandlerMethod`, `HandlerMethodArgumentResolverComposite`, and `HandlerMethodReturnValueHandlerComposite`. These are **internal details useful for reading source code or debugging**; normal application code should program against supported annotations and extension interfaces.

**Ordering matters:** selecting a controller does not mean Spring has already resolved its arguments. For example, mapping `GET /books/{id}` can match path `/books/abc`, yet converting `abc` to `long` fails afterward and the method will not be invoked.

## 3. How HandlerMethodArgumentResolver Resolves Parameters

A `HandlerMethodArgumentResolver` has two main operations:

- `supportsParameter(MethodParameter parameter)`: does this resolver know how to produce a value for this parameter?
- `resolveArgument(...)`: extracts data from the request/model/context, converts it, or collaborates with other utilities to build the argument.

Spring maintains **multiple resolvers** in a composite. Each handler parameter is evaluated to find its corresponding resolver; the first matching resolver in configured order handles it. The result is placed at the right index in the argument array before the Java method is called. A resolver can inspect annotation metadata, not only the Java type.

Example signature:

~~~java
@GetMapping("/{id}")
public BookResponse read(
        @PathVariable long id,
        @RequestParam(defaultValue = "vi") String lang,
        @RequestHeader("X-Client-Version") String version,
        HttpServletRequest request) {
    // ...
}
~~~

With:

~~~http
GET /api/books/42?lang=en HTTP/1.1
Host: localhost:8080
X-Client-Version: 2

~~~

Arguments are built independently by source:

| Java argument | Representative resolver / mechanism | Result |
| --- | --- | --- |
| `@PathVariable long id` | URI-template variable + conversion | `42L` |
| `@RequestParam String lang` | Request parameter resolver | `"en"` |
| `@RequestHeader String version` | Header resolver | `"2"` |
| `HttpServletRequest request` | Servlet request argument resolver | Current request object |

The controller does not construct `HttpServletRequest` itself; the Servlet container creates the request and Spring passes the appropriate reference. Not every argument requires an annotation: types like `Model`, `Principal`, `Locale`, and `HttpServletResponse` have type-based resolvers. However, **explicit annotations** help avoid confusion about where data comes from.

### 3.1. Common Parameter Groups

| Parameter | Source | Key notes |
| --- | --- | --- |
| `@PathVariable` | Variable in matched URI template | Can convert `String` to `long`, `UUID`, `Enum`, ... |
| `@RequestParam` | Request parameters: query and depending on case form/multipart | `required`, `defaultValue`, and target type affect behavior. |
| `@RequestHeader` | HTTP header | Header names are case-insensitive; converts types when needed. |
| `@CookieValue` | Request cookies | Cookie may be absent; decide required/default handling. |
| `@RequestBody` | HTTP request content | Read via `HttpMessageConverter`, e.g., Jackson JSON. |
| `@RequestPart` | A part in a multipart request | A converter can process the part's payload. |
| `MultipartFile` | Parsed multipart upload | Does not imply every request body is multipart. |
| `@ModelAttribute` | Model + request parameters / binding | Uses `WebDataBinder`, typically for form/command objects. |
| `BindingResult`, `Errors` | Binding/validation errors of the preceding argument | Must be placed **immediately after** the validated argument. |
| `Model`, `ModelMap` | Current MVC model | Commonly used when rendering HTML views. |
| `HttpServletRequest`, `HttpServletResponse` | Servlet API | Lower-level request/response access. |
| `Principal` | Current principal info | Result depends on security/container mechanism. |
| `@RequestAttribute`, `@SessionAttribute` | Request/session attributes | Different from `@RequestParam`; not a query parameter. |
| `HttpEntity<T>` | Request headers + body | `T` is read through a message converter. |

`@RequestParam` is optional on certain simple-type parameters because Spring MVC has fallback mechanisms, yet clear API code should annotate the data source explicitly. `Optional<T>`, `required=false`, and `defaultValue` can handle missing parameters, with specific differences depending on the annotation.

### 3.2. Path Variables and Query Parameters Are Different

~~~java
@GetMapping("/books/{bookId}")
public String find(
        @PathVariable long bookId,
        @RequestParam(defaultValue = "full") String view) {
    return bookId + ":" + view;
}
~~~

Calling `GET /books/7?view=summary` produces `bookId=7`, `view="summary"`. If `view` is omitted, Spring uses `"full"` due to `defaultValue`. If the request is `/books/xyz`, matching can still select the method, but argument conversion `String → long` fails; Spring MVC typically responds with **400 Bad Request** via default exception handling.

**Query strings are not part of URI path matching**: `?view=summary` is read as a parameter, whereas `{bookId}` is a path segment.

### 3.3. Type Conversion Differs from JSON Deserialization

For `@PathVariable long id` and `@RequestParam int page`, data comes from short strings. Spring uses its conversion/formatting system (`ConversionService`, `Converter`, `Formatter`, `WebDataBinder` depending on the mechanism) to convert strings into Java types.

For `@RequestBody BookRequest request`, the data may be **multi-field JSON**. Spring selects an `HttpMessageConverter` compatible with the media type—typically the Jackson JSON converter when Jackson is present—to read the byte stream and deserialize JSON into an object.

| Data source | Example | Primarily goes through |
| --- | --- | --- |
| Path | `/books/42` → `long id` | Type conversion |
| Query | `?page=2` → `int page` | Type conversion |
| Header | `X-Limit: 10` → `int limit` | Header resolver + conversion |
| JSON request body | `{"title":"MVC"}` → `BookRequest` | `HttpMessageConverter` |
| Form parameters | `title=MVC&price=50` → command object | `@ModelAttribute` + `WebDataBinder` |

**Do not confuse `@RequestBody` with `@ModelAttribute`.** `@RequestBody` reads the HTTP body via a converter; `@ModelAttribute` creates/retrieves a model object and binds request parameters to its properties. With `application/x-www-form-urlencoded`, accessing Servlet request parameters can consume or affect reading the raw body, so do not assume both mechanisms can re-read the same form body together.

## 4. @RequestBody, HttpMessageConverter, and Content-Type

Example:

~~~java
@PostMapping(path = "/books", consumes = "application/json")
@ResponseBody
public BookResponse create(@RequestBody CreateBookRequest input) {
    return new BookResponse(1L, input.title());
}
~~~

This is an **illustrative method to place inside a Spring MVC `@Controller`**, along with the corresponding DTO record declarations. Flow:

1. The request enters the matched handler `POST /books`.
2. The resolver for `@RequestBody` detects the target Java type `CreateBookRequest`.
3. Spring selects an `HttpMessageConverter` capable of reading that type for `Content-Type: application/json`, such as the Jackson converter.
4. The converter deserializes JSON into a Java instance.
5. The controller receives the object and produces a return value.
6. The `@ResponseBody` return-value handler again selects a converter capable of writing `BookResponse` as the response content; `Accept`, `produces`, and converter capabilities can influence content negotiation.

Distinctions:

- `Content-Type` **in the request** describes the media type of the request content.
- `Accept` **in the request** describes the response media type the client wants.
- `Content-Type` **in the response** describes the representation sent back by the server.

Common errors:
- Malformed JSON or JSON that cannot be deserialized by the converter → typically **400 Bad Request** (`HttpMessageNotReadableException`).
- Request media type not supported by the handler/converter → typically **415 Unsupported Media Type**.
- Client only accepts a media type the server cannot produce → typically **406 Not Acceptable**.
- `@RequestBody(required=true)` with a missing required body → typically **400**.

Do not catch every converter exception and turn it into 500: 400/415/406 carry specific HTTP meanings. Furthermore, do not assume Jackson is installed simply because `spring-web` is present; the corresponding converter library must be on the runtime classpath or configured in the application.

## 5. @ModelAttribute, DataBinder, and Validation

In applications rendering HTML forms, Spring often receives data as request parameters. For a model attribute DTO, `WebDataBinder` binds data into the object, collaborates with converters/formatters for type handling, and can then run validation based on annotations or configuration.

Example method placed inside a `@Controller`:

~~~java
@PostMapping("/register")
public String register(
        @Valid @ModelAttribute RegistrationForm form,
        BindingResult bindingResult,
        Model model) {
    if (bindingResult.hasErrors()) {
        return "register-form";
    }
    model.addAttribute("message", "Registered " + form.getUsername());
    return "register-result";
}
~~~

This is an **illustrative method**: `RegistrationForm`, the validator/Bean Validation provider, and view templates must be defined in the application. The return values `"register-form"` and `"register-result"` are **logical view names** when `@ResponseBody` is absent. Spring does not write these strings directly into the HTTP body as JSON.

`BindingResult` / `Errors` must appear **immediately after the argument it describes**. If you use `@Valid @ModelAttribute RegistrationForm form` without the `BindingResult` parameter needed to handle errors yourself, validation failures may become an exception resolved by Spring, and the method will not enter the `if` branch as you expect.

### 5.1. Where Do @Valid and @Validated Fit in the Pipeline?

- **Binding/deserialization** populates data into Java objects.
- **Validation** evaluates constraints on objects or method parameters once suitable objects/values exist.
- **Business validation** checks complex business rules, which may require databases/services and usually belongs in the business layer.

`@Valid @RequestBody` can trigger Bean Validation, typically raising `MethodArgumentNotValidException` on failure, which is usually handled as 400. In Spring MVC 6.1+, when constraints are placed directly on method parameters and method validation applies, `HandlerMethodValidationException` may also be thrown. **Do not assume every validation error uses a single exception class**, and do not confuse validation with JSON deserialization.

For `@ModelAttribute`, control which properties can be bound; do not allow clients to set sensitive properties just because a setter exists, such as `role`, `isAdmin`, or `balance`. Use dedicated input DTOs, allow binding only valid fields, and enforce business validation/security independently.

### 5.2. BindingResult Is Error Data, Not a Response Status

`BindingResult` holds field/global errors for the controller to decide how to handle. Having a `BindingResult` does not automatically write HTTP status 400; if the controller returns the form view with status 200, the client may still receive 200. In REST APIs, you typically translate errors into an appropriate status such as 400/422 per your published contract. Distinguish **collecting errors** from **choosing an HTTP response**.

## 6. Actually Invoking the Controller Method

Once every argument is resolved, Spring invokes the selected Java method. Controllers are Spring-managed beans (singletons by default), so **multiple requests can invoke the same instance concurrently**. Method parameters are created per call, but mutable instance fields on a singleton controller are shared state; avoid using controller fields to store per-request temporary state.

Several key points:

1. **Time spent in resolvers is still request time.** Converters, validation, and binders can fail before entering the method.
2. **Interceptor preHandle** can stop the handler from proceeding. Exception filters/security can also return an early response.
3. **AOP proxies** may wrap controllers/services, affecting transactions, validation, security, or logging per configuration.
4. **Service calls** orchestrated by the controller are not automatically retried or turned async by Spring MVC.
5. **Exceptions** thrown in resolvers, controllers, or return-value handlers can be routed to the `HandlerExceptionResolver` chain.

Not every response from a URI is produced by the body of that controller method. For example, a request parsing error can yield 400 before the method runs; a filter can send 401; Spring Security can decide 403.

## 7. HandlerMethodReturnValueHandler Interprets Return Values

After the controller returns a Java value, Spring chooses a matching **`HandlerMethodReturnValueHandler`** based on return type and annotations. This handler can:

- Mark the response as handled and write status/headers/body.
- Populate data into `ModelAndViewContainer` so MVC can render a view.
- Register async processing so the request resumes in a later dispatch.
- Apply status/headers per `ResponseEntity` or corresponding annotations.

`HandlerMethodReturnValueHandler` and `HttpMessageConverter` have different roles. **The return-value handler decides how to interpret the Java return value** (body vs. view, headers/status, async...), while **the message converter transforms Java objects into HTTP representation bytes** when a body needs to be written.

| Controller returns | How Spring MVC interprets it | Example |
| --- | --- | --- |
| Object + `@ResponseBody` | Serializes object into response body | `BookResponse` → JSON |
| Object inside `@RestController` | Same, since `@RestController` includes `@ResponseBody` | JSON API |
| `ResponseEntity<T>` | Specifies HTTP status, headers, and body | 201 + `Location` + DTO |
| `HttpEntity<T>` | Response body + headers, without a dedicated status API like `ResponseEntity` | Result with headers |
| `String` in `@Controller` without `@ResponseBody` | Logical view name | `"books/list"` |
| `ModelAndView` | View name/object together with model | HTML rendering |
| `Model` / `Map` | Adds attributes to model; view name determined by MVC conventions | HTML page |
| `ProblemDetail` / `ErrorResponse` | Describes errors with problem-details support | Error response |
| `Callable<T>`, `DeferredResult<T>` | Async result; return value processed once ready | Long-running request |
| `ResponseBodyEmitter`, `SseEmitter` | Streaming response | SSE |
| `void` | Depends on annotations/context and whether response was already handled | Does not automatically mean 204 |

**Identical Java values can carry different HTTP semantics** if annotations differ.

### 7.1. @Controller with String: View Name

~~~java
@Controller
class PageController {
    @GetMapping("/books")
    public String books(Model model) {
        model.addAttribute("heading", "Book catalog");
        return "books/list";
    }
}
~~~

This is an illustrative method/controller that runs when the app has configured a view technology such as Thymeleaf with a corresponding template. The string `"books/list"` is resolved by a view resolver into a view/template to render. `Model` passes `heading` to the view. If the view does not exist, you may encounter a rendering error even though the handler method executed successfully.

With `return "redirect:/books";`, Spring MVC can interpret the `redirect:` prefix to produce an HTTP redirect instead of rendering a view by that name.

### 7.2. @RestController with String: Response Body

~~~java
@RestController
class TextController {
    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
~~~

With a stack having a suitable `StringHttpMessageConverter`, the response body is the string:

~~~text
pong
~~~

Here Spring does **not** look for a template named `pong`. `@RestController` is a meta-annotation combining `@Controller` and `@ResponseBody`. Depending on configuration/content negotiation, `Content-Type` may be `text/plain` or an appropriate type; do not assume the response is JSON merely because the controller has `@RestController`.

### 7.3. ResponseEntity Controls Status, Headers, and Body

~~~java
@PostMapping("/books")
public ResponseEntity<BookResponse> create(@RequestBody CreateBookRequest input) {
    BookResponse result = new BookResponse(42L, input.title());
    return ResponseEntity
            .created(URI.create("/api/books/42"))
            .body(result);
}
~~~

This snippet is an **illustrative method** requiring appropriate controller, DTO, and import definitions. The result has status `201 Created`, header `Location: /api/books/42`, and a body serialized by a converter. `ResponseEntity.ok(value)` produces 200, `ResponseEntity.noContent().build()` produces 204 with no body, and `ResponseEntity.notFound().build()` produces 404 with no body in typical usage.

**Do not try to return a JSON body with 204 No Content.** A 204 response per HTTP carries no message content. `ResponseEntity` does not override HTTP rules just because a generic type is declared.

### 7.4. @ResponseStatus, null, and void

`@ResponseStatus(HttpStatus.NO_CONTENT)` can set the status when a handler completes, but that does not mean every `void` method automatically returns 204. Return types `void` or `null` have semantics depending on annotations, Servlet response arguments, whether the response was already written, or model/view flow. In an HTML controller, Spring may infer a default view name; in a REST controller, there is typically no body.

If you write directly to `HttpServletResponse.getWriter()`, you are manipulating the response directly; do not simultaneously expect a message converter to write another object into the same stream. Once a response is committed, changing status/headers or rendering an error page may no longer be possible.

## 8. Runnable Spring Boot 3 Example: Observing All Three Stages

Create a **Spring Boot 3.x / Java 17+** project with dependencies:
- `spring-boot-starter-web`: Spring MVC, embedded servlet container, and common JSON converters.
- `spring-boot-starter-validation`: Bean Validation with Jakarta Validation, enabling `@NotBlank`/`@Valid`.

In a Gradle project configured with the Spring Boot plugin, the corresponding dependencies are:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Place all the code below in **`src/main/java/demo/mvc/MvcPipelineApplication.java`**. The example runs inside a Spring Boot application with the build/dependencies above, not as a standalone file compiled with `javac` without the Spring classpath.

~~~java
package demo.mvc;

import java.net.URI;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class MvcPipelineApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcPipelineApplication.class, args);
    }
}

@RestController
@RequestMapping("/api/books")
class BookController {

    private final AtomicLong sequence = new AtomicLong();
    private final Map<Long, Book> books = new ConcurrentHashMap<>();

    @GetMapping("/{id}")
    public ResponseEntity<BookResponse> get(
            @PathVariable long id,
            @RequestParam(defaultValue = "vi") String lang,
            @RequestHeader(value = "X-Trace-Id",
                           defaultValue = "none") String traceId) {

        Book book = books.get(id);
        if (book == null) {
            return ResponseEntity.notFound().build();
        }
        BookResponse response = new BookResponse(
                book.id(), book.title(), lang, traceId);
        return ResponseEntity.ok(response);
    }

    @PostMapping(consumes = "application/json",
                 produces = "application/json")
    public ResponseEntity<BookResponse> create(
            @Valid @RequestBody CreateBookRequest request) {

        long id = sequence.incrementAndGet();
        Book book = new Book(id, request.title());
        books.put(id, book);

        BookResponse response =
                new BookResponse(id, book.title(), "vi", "none");

        return ResponseEntity
                .created(URI.create("/api/books/" + id))
                .body(response);
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable long id) {
        if (books.remove(id) == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.noContent().build();
    }

    public record CreateBookRequest(@NotBlank String title) {}

    public record Book(long id, String title) {}

    public record BookResponse(
            long id, String title, String lang, String traceId) {}
}
~~~

**Why does this example illustrate the full pipeline?**

- `@PathVariable`, `@RequestParam`, and `@RequestHeader`: resolvers extract URI/query/header values and convert them to Java types.
- `@Valid @RequestBody`: converter reads JSON into the record; validation verifies `title` is non-empty and not whitespace-only.
- `get`, `create`, `delete`: controller methods are invoked after arguments have been prepared.
- `ResponseEntity<BookResponse>`: return-value handler reads status/headers/body; Jackson converter serializes the record to JSON.
- `ResponseEntity<Void>`: return-value handler produces 204 with no body.
- `ConcurrentHashMap` + `AtomicLong`: demo supports concurrent requests at an in-memory level; this is not a database and provides no transactions or durability.

A freshly started application has no data and `sequence` starts at 0; the HTTP examples below assume no other client has created books yet.

Run with Gradle wrapper from the project directory:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

After the application starts on default port `8080`, try creating a book:

~~~bash
curl -i -X POST "http://localhost:8080/api/books" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"title":"Spring MVC"}'
~~~

Expected response has status `201 Created`, `Location: /api/books/1`, and equivalent JSON:

~~~json
{"id":1,"title":"Spring MVC","lang":"vi","traceId":"none"}
~~~

Field ordering, whitespace, certain response headers, and `Transfer-Encoding`/`Content-Length` handling depend on the converter/container. ID = 1 holds only when this is the first creation in a fresh demo process.

Continue:

~~~bash
curl -i "http://localhost:8080/api/books/1?lang=en" \
  -H "X-Trace-Id: demo-001" \
  -H "Accept: application/json"
~~~

Expected response is 200 with equivalent body:

~~~json
{"id":1,"title":"Spring MVC","lang":"en","traceId":"demo-001"}
~~~

You can trace each argument in order: `id=1` comes from the path; `lang="en"` comes from the query; `traceId="demo-001"` comes from the header. The return value is `BookResponse`, which the converter then serializes to JSON.

Try delete:

~~~bash
curl -i -X DELETE "http://localhost:8080/api/books/1"
~~~

Expected response is **204 No Content** with no body. Calling `GET /api/books/1` again returns 404 because the book was removed.

Try invalid inputs:

~~~bash
curl -i "http://localhost:8080/api/books/abc"

curl -i -X POST "http://localhost:8080/api/books" \
  -H "Content-Type: application/json" \
  -d '{"title":""}'

curl -i -X POST "http://localhost:8080/api/books" \
  -H "Content-Type: text/plain" \
  -d 'just text'
~~~

| Invalid request | Failure point | Common HTTP status |
| --- | --- | --- |
| `GET /api/books/abc` | `"abc"` cannot convert to `long id` | 400 |
| POST JSON with `title=""` | Bean Validation `@NotBlank` | 400 |
| POST `Content-Type: text/plain` | `consumes="application/json"` does not match | 415 |
| GET a deleted id | Controller explicitly returns `notFound()` | 404 |

**Note:** Default error bodies (JSON/HTML/Problem Details) depend on Spring Boot version, `Accept`, error handler configuration, and Security. The table confirms status semantics rather than assuming a single error body format.

### 8.1. Unpacking One Request Step by Step

For `POST /api/books` with `{"title":"Spring MVC"}`:

1. Servlet container hands the request to `DispatcherServlet`.
2. `RequestMappingHandlerMapping` matches POST, path, `consumes`, `produces`, and finds `BookController.create`.
3. `RequestMappingHandlerAdapter` selects the argument resolver for `@RequestBody`.
4. `HttpMessageConverter` reads JSON bytes and builds `CreateBookRequest("Spring MVC")`.
5. Bean Validation checks `@NotBlank`; if invalid, stops before the controller method.
6. Spring invokes `create(request)`; the method creates `Book`, stores it in the map, and builds `ResponseEntity`.
7. Return-value handler receives `ResponseEntity`, sets status 201 and the `Location` header.
8. JSON converter serializes `BookResponse` into the response body.
9. Container sends the HTTP response. Interceptors/filters and request completion steps may also participate depending on configuration.

This is a **logical ordering** to understand the mechanism, not a claim that every step is always handled by a single class across all configurations.

## 9. Where Do Exceptions Occur and How Is the Response Formed?

A request can fail before, during, or after the method:

| Stage | Cause | Representative exception / component | Common status |
| --- | --- | --- | --- |
| Handler matching | No route for path | Mapping/static resource/no-handler mechanism | 404 |
| Handler matching | Method not allowed | `HttpRequestMethodNotSupportedException` | 405 |
| Handler matching/media type | `consumes` mismatch | `HttpMediaTypeNotSupportedException` | 415 |
| Argument resolution | Missing required `@RequestParam` | `MissingServletRequestParameterException` | 400 |
| Argument resolution | Path/query conversion failure | `MethodArgumentTypeMismatchException` | 400 |
| Message conversion | Unreadable JSON body | `HttpMessageNotReadableException` | 400 |
| Bean Validation | Invalid `@Valid @RequestBody` | `MethodArgumentNotValidException` or method validation error depending on case | 400 |
| Controller business | Resource not found | Controller returns 404 / mapped exception | 404 |
| Return conversion | Cannot produce media type requested by client | `HttpMediaTypeNotAcceptableException` | 406 |
| Any stage | Unhandled error | Exception mapping / container | Possibly 500 |

In MVC, `DispatcherServlet` coordinates `HandlerExceptionResolver`s. Common mechanisms include `ExceptionHandlerExceptionResolver` (handling `@ExceptionHandler`/advice), `ResponseStatusExceptionResolver` (e.g., `@ResponseStatus`, `ResponseStatusException`), and `DefaultHandlerExceptionResolver` (common MVC errors). Configuration order and customizations determine which resolver handles first.

**Do not wrap every exception and return HTTP 200** just to avoid errors on the frontend. When designing APIs, separate recoverable client errors, well-defined business errors, and unexpected infrastructure failures; use proper statuses with a stable error schema.

### 9.1. @RestControllerAdvice for Standardizing Errors

Illustrative example of an error handler in a Spring MVC app (must be within component scan):

~~~java
@RestControllerAdvice
class ApiErrors {

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<Map<String, String>> badInput(
            IllegalArgumentException ex) {
        return ResponseEntity.badRequest()
                .body(Map.of("error", ex.getMessage()));
    }
}
~~~

This class needs imports for `java.util.Map`, `ResponseEntity`, `@ExceptionHandler`, and `@RestControllerAdvice`. The example defines mapping for only one exception type for illustration. **Do not automatically return raw `ex.getMessage()` for every exception type in production**, as it can leak internal details; for untrusted errors, use safe messages and log details on the server.

`@RestControllerAdvice` selects exception handlers before the result is written. It **cannot guarantee** replacing a response that is already committed, nor does it handle errors inside security filters/containers outside MVC's exception resolution scope.

## 10. Asynchronous Return Value Handling

Spring MVC supports returning async wrappers while staying on the Servlet stack. Example **illustrative method**:

~~~java
@GetMapping("/reports/{id}")
public Callable<ResponseEntity<String>> report(@PathVariable long id) {
    return () -> ResponseEntity.ok("report-" + id);
}
~~~

Meaning:
1. The handler method initially returns a `Callable`, rather than the final body immediately.
2. Spring MVC initiates async processing with Servlet async support and an appropriate executor.
3. When the `Callable` finishes, the resulting `ResponseEntity<String>` is fed back into the return-value handling pipeline.
4. The final response can be written during the async dispatch phase.

This snippet must sit in a Spring MVC controller and import `Callable`, `ResponseEntity`, `@GetMapping`, `@PathVariable`; use an executor sized for real load. `DeferredResult<T>` can be completed by another callback/thread; neither guarantees all MVC I/O operations are non-blocking. If timeouts or exceptions occur during async processing, error handling must also account for the async lifecycle.

Do not treat `Callable<ResponseEntity<T>>` as a "weird unserializable return type": the async mechanism obtains the final result and then **continues using return-value handlers** for `ResponseEntity<T>`.

## 11. Custom Argument Resolvers: When Are They Needed?

If an application frequently extracts domain-specific request context (such as an authenticated tenant ID), you can write a custom `HandlerMethodArgumentResolver`:

~~~java
@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
public @interface CurrentTenant {}
~~~

The annotation requires imports `java.lang.annotation.ElementType`, `Retention`, `RetentionPolicy`, `Target` and belongs in **`CurrentTenant.java`** if declared as a public top-level annotation. Its resolver implements `supportsParameter` and `resolveArgument`, reading trusted context from the request, and is registered via `WebMvcConfigurer.addArgumentResolvers`.

Example usage once the **resolver is actually registered**:

~~~java
@GetMapping("/tenant-info")
public String tenant(@CurrentTenant String tenantId) {
    return tenantId;
}
~~~

This is **illustrative code, not a standalone runnable program**, as the resolver implementation and security configuration are not defined and it is not attached to a controller. Do not use `@CurrentTenant` without a supporting resolver. When code needs standard path/query/header values, use built-in resolvers; write custom resolvers only for genuinely meaningful abstractions.

Things to keep in mind when writing a resolver:
- Avoid overlapping with default resolvers or matching overly broad parameter types (e.g., matching every `String`).
- Rely only on **authenticated** tenant/principal information; do not trust a raw `X-Tenant` header from the Internet.
- Handle missing or invalid tenant errors explicitly using exceptions with clear HTTP mappings.
- Resolvers are typically shared across requests, so do not store per-request state in mutable instance fields.

## 12. Common Misconceptions to Correct

| Misconception | Correct understanding |
| --- | --- |
| "`@GetMapping` passes parameters directly into the Java method." | Handler mapping selects the method; argument resolvers prepare Java arguments. |
| "`@PathVariable long` always fails path matching when the URL has letters." | The handler path can match, and then failure occurs during `String → long` conversion. |
| "`@RequestBody` and `@ModelAttribute` are the same." | One reads message content via a converter; the other binds request parameters to a model object. |
| "With `@Valid`, the controller always runs before errors are seen." | Validation can stop during argument resolution before the method is invoked. |
| "`BindingResult` can be placed anywhere." | Place it immediately after the argument it describes. |
| "`@RestController` must return JSON." | Body serialization follows converters and content negotiation; `String` can be plain text. |
| "Returning `String` is always an HTTP body." | In a `@Controller` without `@ResponseBody`, `String` is typically a view name. |
| "Returning `void` is always 204." | Status/view/body depend on annotations, context, and whether the response was handled. |
| "`ResponseEntity` serializes objects to JSON itself." | Return-value handler applies status/headers; a message converter serializes the body. |
| "If a handler matched, the controller is guaranteed to run." | Resolvers, conversion, validation, interceptors, or filters can prevent invocation. |
| "Validation errors are always one exception type." | Spring MVC has different validation paths, notably method validation. |
| "Storing request fields in a singleton controller is safe." | Mutable fields are shared across requests and require thread-safe design. |

## 13. Self-Check Exercises and Answers

**Exercise 1.** Consider the method:

~~~java
@GetMapping("/books/{id}")
public ResponseEntity<BookResponse> get(
        @PathVariable long id,
        @RequestParam(defaultValue = "vi") String lang,
        @RequestHeader("X-Client") String client) {
    // ...
}
~~~

With `GET /books/7?lang=en` and no `X-Client` header, is the controller invoked? At which step does the error typically occur?

**Exercise 2.** An HTML controller returns `"books/index"`, and a REST controller returns `"books/index"`. Are the two responses necessarily identical?

**Exercise 3.** A client POSTs JSON with `Content-Type: application/json` but a syntactically broken body. Does Spring necessarily enter the controller and return 500?

**Exercise 4.** A controller accepts `@Valid @RequestBody CreateBookRequest body`; the body is valid JSON syntax, but the `title` field violates `@NotBlank`. Which step handles the error? Common HTTP status?

**Exercise 5.** With `ResponseEntity.created(URI.create("/api/books/42")).body(dto)`, which component sets status/headers, and which writes the JSON body?

**Exercise 6.** Why can `Callable<ResponseEntity<String>>` still return the right HTTP status and body, even though the method initially does not return `ResponseEntity` directly?

### Explanatory Answers

1. `@RequestHeader("X-Client")` is required by default. Without that header, argument resolution typically reports a missing request header, responding 400; the method is not invoked.
2. No. An HTML `@Controller` can treat the string as a **view name**; `@RestController` treats it as the **response body**.
3. No. The converter typically throws `HttpMessageNotReadableException` while reading `@RequestBody`; default handling usually returns 400 before the method runs.
4. After the converter builds the DTO, validation enforces constraints; Spring typically responds with 400 via exception handling if no `BindingResult` applies.
5. The `HandlerMethodReturnValueHandler` for `ResponseEntity` applies status 201 and `Location`; the selected `HttpMessageConverter` serializes `dto` to JSON.
6. Spring MVC recognizes the async wrapper, waits for completion, and then processes `ResponseEntity<String>` using the return-value mechanism during resumed handling.

## 14. Checklist When Reading or Building a Spring MVC Controller

When an endpoint does not respond as expected, inspect in order:

1. **Handler:** Do method/path/headers/consumes/produces match? Which method did `HandlerMapping` choose?
2. **Arguments:** Where does each argument come from? Are there required/default rules, conversions, or multipart/body converters?
3. **Binding and validation:** How is the DTO bound? Are there field/constraint errors before the method?
4. **Invocation:** Are there filter/interceptor/AOP/service exceptions? Does the singleton controller misuse mutable shared state?
5. **Return value:** Is `String` a view name or a body? Which status/headers does `ResponseEntity` set? Can converters write the client's requested media type?
6. **Errors and async:** Which exception resolver handles it; is the response already committed; are there async dispatches/timeouts?
7. **Empirical observation:** Inspect network status, headers, body, and logs/tracing; do not conclude from a single annotation alone.

Once you clearly understand the three stages **argument resolution → controller invocation → return-value handling**, you will know why a Java method was never called, why the same `String` becomes an HTML page or an HTTP body, and why a Java object requires a message converter before reaching the client.

**Official references:** Spring Framework MVC *Annotated Controllers – Method Arguments* (https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html), *Return Values* (https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/return-types.html), *@RequestBody* (https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html), *@ResponseBody* (https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responsebody.html), and *ResponseEntity* (https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html).