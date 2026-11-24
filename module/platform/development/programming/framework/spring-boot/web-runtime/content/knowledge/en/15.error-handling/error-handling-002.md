# The /error Mechanism, BasicErrorController, and ErrorAttributes in Spring Boot Servlet

## Learning Objectives

In a **Spring Boot Servlet/Spring MVC** application, not every HTTP error is created directly by a controller. When a request causes an error that MVC does not finish handling, the **Servlet container** can perform an internal **error dispatch** to an error page. Spring Boot automatically registers the default path **/error**, places a **BasicErrorController** to receive it, and retrieves data from **ErrorAttributes** to produce an appropriate HTML or JSON response.

After this lesson, you will be able to:

- Distinguish exceptions handled at the controller, DispatcherServlet, and Servlet container levels.
- Describe the flow: initial request → error dispatch → /error → BasicErrorController.
- Explain the roles of ErrorMvcAutoConfiguration, ErrorController, ErrorAttributes, and DefaultErrorAttributes.
- Understand the differences between JSON error responses, HTML error views, the whitelabel page, and custom error pages.
- Know the `server.error.*` properties in Spring Boot 3.5 and the `spring.web.error.*` naming in Spring Boot 4.x.
- Add a safe property to the error body without replacing the entire error controller.
- Handle business errors with `@RestControllerAdvice`/`ProblemDetail` before considering replacing the `/error` mechanism.
- Properly test Servlet error page mechanisms using a real embedded server, avoiding misunderstandings with MockMvc.
- Recognize the risks of leaking stack traces, error dispatch loops, 404 errors replaced by proxies, and committed responses.

**Scope:** This lesson focuses on the **Servlet stack** (Spring MVC with Tomcat/Jetty/Undertow), not Spring WebFlux's reactive error handler mechanism. Runnable examples use **Spring Boot 3.5.x, Java 17+**, and a section near the end highlights differences in Boot 4.x.

## 1. Three Error-Handling Layers to Distinguish

An incoming HTTP request to a Servlet application can encounter errors in different places.

| Layer | Component | Example | Typical Handling Approach |
|---|---|---|---|
| Controller/service | Business methods and exceptions | Product not found, invalid data | `@ExceptionHandler`, `ResponseEntity`, or `ResponseStatusException` |
| Spring MVC | DispatcherServlet and HandlerExceptionResolver | Binding error, missing route, unsupported method | MVC resolver returns response/sendError or lets error propagate |
| Servlet container | Tomcat/Jetty/Undertow | Unhandled exception, applicable HTTP error status | Error-page mapping → error dispatch to `/error` |

**Not every 4xx/5xx response goes through `/error`.** For example:

~~~java
@GetMapping("/api/items/{id}")
public ResponseEntity<Void> find(@PathVariable long id) {
    return ResponseEntity.notFound().build();
}
~~~

The controller above already created a 404 ResponseEntity. It does not require the container to open an error dispatch. Conversely, an exception unhandled by MVC can cause the container to perform an error dispatch and let BasicErrorController build the response.

This is why debugging requires asking **who created the final response**, rather than assuming every HTTP 404 or 500 comes from BasicErrorController.

## 2. Default Flow of /error in Servlet

Conceptual diagram:

~~~text
HTTP client
     |
     v
Embedded Servlet container (Tomcat/Jetty/Undertow)
     |
     v
Servlet filters (REQUEST dispatch)
     |
     v
DispatcherServlet
     |
     +----> HandlerMapping finds controller
     |
     +----> HandlerAdapter invokes controller
     |           |
     |           +-- success -> normal response
     |           |
     |           +-- error -> HandlerExceptionResolver chain
     |                         |
     |                         +-- handled -> response/status
     |                         |
     |                         +-- unhandled / sendError
     |                                    |
     v                                    v
Container error-page processing <---------+
     |
     | ERROR dispatch (if needed and still handleable)
     v
Configured error path (default /error)
     |
     v
DispatcherServlet / BasicErrorController
     |
     +-- ErrorAttributes -> status, error, timestamp, path...
     |
     +-- Accept: text/html -> error view / HTML fallback
     |
     +-- Accept: application/json -> JSON error body
     |
     v
HTTP response to client
~~~

The diagram illustrates a **typical** flow, not an invariant law for every exception. A HandlerExceptionResolver may handle the error immediately with a response, the Servlet container may refuse to dispatch if the response is already committed, and a reverse proxy may even generate its own error page.

### Key Events to Remember

1. The Servlet container receives the initial request with `DispatcherType.REQUEST`.
2. DispatcherServlet finds and invokes the mapped handler.
3. If an exception occurs, Spring MVC tries the `HandlerExceptionResolver` list.
4. For unhandled errors or errors reported through the Servlet error status mechanism, the container may trigger an error dispatch.
5. The Servlet container uses the error-page registration provided by Boot/configuration to select `/error`.
6. The new dispatch carries `DispatcherType.ERROR` and request attributes containing error details.
7. BasicErrorController reads data via ErrorAttributes, determines status, and selects a representation.
8. The container sends the response to the client while headers/body can still be written.

Most importantly: **`/error` is not just a URL for clients to send manual GET requests to.** It is primarily the target of an **internal Servlet error dispatch**, accompanied by error metadata provided by the container.

## 3. What Does ErrorMvcAutoConfiguration Set Up?

Spring Boot auto-configures error handling for Servlet applications via **ErrorMvcAutoConfiguration** when conditions match. In Spring Boot 3.5, the class belongs to package:

~~~java
org.springframework.boot.autoconfigure.web.servlet.error.ErrorMvcAutoConfiguration
~~~

This auto-configuration can:

- Provide a `DefaultErrorAttributes` bean if the application has not provided a suitable `ErrorAttributes` bean.
- Create `BasicErrorController` if no replacement `ErrorController` exists.
- Set up error page integration for the Servlet container.
- Configure `ErrorViewResolver` to resolve HTML error views when needed.
- Provide a whitelabel error page fallback when applicable and enabled.

Auto-configuration conditions matter greatly. If the application declares its own `ErrorAttributes`, Boot can keep `BasicErrorController` while using the attribute source you provided. If the application declares its own `ErrorController`, Boot may no longer create the default `BasicErrorController`.

### Three Easily Confused Roles

| Component | Question It Answers |
|---|---|
| ErrorMvcAutoConfiguration | At startup, should default error-handling beans be created and registered? |
| BasicErrorController | When a request reaches the error mapping, how should status, headers, body, or view be returned? |
| ErrorAttributes / DefaultErrorAttributes | What data describes the current error and which fields are allowed to be exposed? |

Do not add a custom controller with mapping `/error` just to add a JSON field if `ErrorAttributes` can do it. Duplicate `/error` routes can cause ambiguous mappings or disable `BasicErrorController` without adequate replacement code.

## 4. What Is BasicErrorController?

**BasicErrorController** is Spring Boot's default `ErrorController` implementation for the Servlet stack. In Spring Boot 3.5, the package is:

~~~java
org.springframework.boot.autoconfigure.web.servlet.error.BasicErrorController
~~~

In terms of annotations, its path is controlled by the error path configuration; if unchanged, the endpoint is `/error`.

It has two primary response-generation paths:

- **errorHtml(...)** mapped with `produces = text/html`: returns a **ModelAndView**, allowing HTML error pages to be resolved.
- **error(...)** for responses not preferring HTML: returns a **ResponseEntity<Map<String,Object>>** from ErrorAttributes, typically serialized by a JSON converter.

When a client sends:

~~~http
GET /api/unknown HTTP/1.1
Accept: application/json
~~~

and the request enters the container's error dispatch mechanism, BasicErrorController can return a JSON error body:

~~~json
{
  "timestamp": "2026-11-07T10:15:30.000+00:00",
  "status": 404,
  "error": "Not Found",
  "path": "/api/unknown"
}
~~~

**This is illustrative JSON, not a guaranteed snapshot.** Timestamp values, path, fields, and serialization depend on version, `include-*` properties, cause, and error handling. By default, Boot 3.5 does not include message or stacktrace in JSON.

### HTML and the Accept Header

If a browser requests HTML:

~~~http
GET /api/unknown HTTP/1.1
Accept: text/html
~~~

BasicErrorController usually picks the HTML branch. It tries to locate a matching error view/template, then falls back to the whitelabel page if enabled and no suitable view exists.

**Accept is not Content-Type.** Accept indicates which response format the client wants to receive; Content-Type usually describes the body format the client sent. If the same URL sometimes returns HTML and sometimes JSON, inspect the `Accept` request header before concluding the server is inconsistent.

Do not rely on `User-Agent` as the sole mechanism for deciding response type. API clients should explicitly send **Accept: application/json** when they want JSON.

## 5. ErrorAttributes and DefaultErrorAttributes

In Spring Boot 3.5 Servlet:

~~~java
org.springframework.boot.web.servlet.error.ErrorAttributes
org.springframework.boot.web.servlet.error.DefaultErrorAttributes
org.springframework.boot.web.error.ErrorAttributeOptions
~~~

**ErrorAttributes** is the contract for reading error data from the current request:

~~~java
Map<String, Object> getErrorAttributes(
    WebRequest webRequest,
    ErrorAttributeOptions options
);
~~~

It also has `getError(WebRequest)` to retrieve the underlying `Throwable` if available. `ErrorAttributeOptions` lets BasicErrorController decide whether to include message, exception, binding errors, trace, or path in the response data.

**DefaultErrorAttributes** is the default implementation. It typically provides these fields when determinable and permitted for display:

| Field | Meaning | Notes |
|---|---|---|
| timestamp | Time when error attributes were retrieved | Not a business timestamp or trace ID |
| status | HTTP status | E.g., 404, 500 |
| error | Summary name/reason of status | E.g., Not Found |
| exception | Exception class name | Can be hidden by config |
| message | Error description | Can be hidden to prevent data leaks |
| errors | Binding/validation error details | Can be hidden and requires handling sensitive content |
| trace | Exception stack trace | Should not be public in production |
| path | Request path causing the error | Depends on `include-path`/version policy |

**ErrorAttributes does not necessarily set the HTTP status.** It supplies data for the response/error view to use. The actual status may come from Servlet error attributes and controller logic.

In Spring Boot 3.5, `DefaultErrorAttributes` also acts as a high-priority `HandlerExceptionResolver` to record exceptions. Do not infer that it automatically turns every error into a JSON response: recording an exception and rendering a response can occur in separate steps.

### ErrorAttributeOptions

Useful options include:

~~~java
ErrorAttributeOptions options =
    ErrorAttributeOptions.defaults()
        .including(ErrorAttributeOptions.Include.MESSAGE);
~~~

The snippet above only demonstrates the API, not advice to enable MESSAGE in production. Spring Boot application properties and BasicErrorController determine which options actually reach the response. If a custom `ErrorAttributes` ignores `options`, you may accidentally expose content configured to stay hidden.

## 6. What Request Attributes Does Servlet Error Dispatch Carry?

The Servlet API defines attributes used when the container dispatches to an error page. In Spring Boot 3.5/Spring Framework 6 based on Jakarta Servlet, read them from:

~~~java
import jakarta.servlet.RequestDispatcher;
~~~

Common keys:

| Constant | Meaning |
|---|---|
| `RequestDispatcher.ERROR_STATUS_CODE` | HTTP status code of the error |
| `RequestDispatcher.ERROR_MESSAGE` | Error description from container |
| `RequestDispatcher.ERROR_EXCEPTION` | Throwable attached to error dispatch, if any |
| `RequestDispatcher.ERROR_EXCEPTION_TYPE` | Exception type |
| `RequestDispatcher.ERROR_REQUEST_URI` | URI of original failing request |
| `RequestDispatcher.ERROR_SERVLET_NAME` | Related servlet name |

Example **illustrative snippet inside a servlet/error handler**, not a full controller:

~~~java
Object status = request.getAttribute(
    RequestDispatcher.ERROR_STATUS_CODE
);

Object originalUri = request.getAttribute(
    RequestDispatcher.ERROR_REQUEST_URI
);
~~~

Not every error dispatch carries every attribute. For instance, a 404 due to a missing route may have no corresponding `Throwable` unlike an error throwing `IllegalStateException`.

### DispatcherType.REQUEST vs. DispatcherType.ERROR

The initial request typically carries `DispatcherType.REQUEST`. The container's forward to the error page typically uses `DispatcherType.ERROR`.

A Servlet Filter may be registered for `REQUEST`, `ERROR`, or both. Thus, filter logs may appear twice for a single failing request, or not run at all on the `ERROR` pass if the filter mapping excludes that dispatcher type.

Do not jump to “the controller was called twice” solely from seeing two log lines. Log the path, dispatcher type, and correlation ID to distinguish them.

## 7. How Does /error Differ from @ExceptionHandler and @RestControllerAdvice?

**@ExceptionHandler** and **@RestControllerAdvice** are error-handling points within Spring MVC. They are typically suited for business errors or exceptions requiring a specific schema:

~~~java
@RestControllerAdvice
public class ApiErrorAdvice {

    @ExceptionHandler(ItemNotFoundException.class)
    public ResponseEntity<ProblemDetail> notFound(
            ItemNotFoundException error) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND, "Item does not exist"
        );
        problem.setTitle("Item not found");

        return ResponseEntity
            .status(HttpStatus.NOT_FOUND)
            .body(problem);
    }
}
~~~

This is an illustrative class; it requires `ItemNotFoundException` and Spring MVC imports. When the resolver handles the exception successfully, the request can end **directly in MVC**, without going through BasicErrorController.

Comparison:

| Criterion | @ExceptionHandler / @RestControllerAdvice | BasicErrorController /error |
|---|---|---|
| Location | Spring MVC exception resolution | Error-page fallback in Servlet stack |
| Best used for | Specifically classifiable business errors | Remaining errors, app-wide HTTP status/error dispatch |
| Response schema | Application-chosen DTO/ProblemDetail | ErrorAttributes + default HTML/JSON |
| Status control | Inside the handler | From error status and controller logic |
| Covers errors outside MVC | Not all errors | Can handle many errors dispatched by Servlet container |
| Requires error dispatch | Not necessarily | Usually involved for container-routed errors |

**Actual precedence depends on error type and how MVC/controller/container process it.** Do not force every exception into `/error` when `@RestControllerAdvice` already produces a valid response.

### Do Not Confuse ResponseStatusException with /error

~~~java
throw new ResponseStatusException(
    HttpStatus.NOT_FOUND, "Item not found"
);
~~~

Spring MVC has resolvers to process `ResponseStatusException`. Depending on handling, the resolver may set the status or invoke `sendError`, leading to another error-handling pass. There is no rule saying “every ResponseStatusException definitely returns JSON from BasicErrorController”.

### Returning ResponseEntity 404 Directly

~~~java
return ResponseEntity.notFound().build();
~~~

This specifies an HTTP 404 with no body. If the API needs a standard error body, write the response explicitly or use an exception handler rather than relying on `/error` to fill in a body for a `ResponseEntity` already completed by the controller.

## 8. Configuring server.error.* in Spring Boot 3.5

Spring Boot 3.5 supports these properties:

~~~properties
server.error.path=/error
server.error.include-exception=false
server.error.include-message=never
server.error.include-stacktrace=never
server.error.include-binding-errors=never
server.error.include-path=always
server.error.whitelabel.enabled=true
~~~

This is an illustrative set matching Boot 3.5 defaults, not advice to copy all of them into every application. If no changes are needed, letting Boot use defaults is simpler.

| Property | Purpose |
|---|---|
| `server.error.path` | Default error controller path, typically `/error` |
| `server.error.include-exception` | Whether to output the exception class name |
| `server.error.include-message` | When to include `message` in the error body |
| `server.error.include-stacktrace` | When to include `trace` in the body |
| `server.error.include-binding-errors` | When to include binding/validation errors in the body |
| `server.error.include-path` | When to output `path` |
| `server.error.whitelabel.enabled` | Enable/disable whitelabel HTML fallback |

### never, always, and on_param

Properties like `include-message`, `include-stacktrace`, and `include-binding-errors` typically support three modes:

- **never**: do not output the corresponding data.
- **always**: always output the corresponding data if present.
- **on_param**: output when the request includes a supported query parameter.

`on_param` is useful for debugging in restricted environments, but it is **not a secret-protection mechanism**. External users can try adding query parameters too. Never enable `on_param` for stacktraces on public production endpoints without real safeguards.

### Safe Policy for Production

Typically:

~~~properties
server.error.include-exception=false
server.error.include-message=never
server.error.include-stacktrace=never
server.error.include-binding-errors=never
~~~

Detailed information should be written to server logs per security policy, tagged with a correlation/request ID, while only a stable error code and safe message are returned to clients. Never use stacktraces as response bodies just for debugging convenience.

### What Does server.error.whitelabel.enabled=false Mean?

The configuration:

~~~properties
server.error.whitelabel.enabled=false
~~~

primarily **disables the whitelabel HTML fallback view**; it does not disable `/error`, BasicErrorController, or error dispatch. Without a matching HTML view, users may see another response or the container's error page depending on configuration. Do not use this property to claim the API always returns JSON to every client.

## 9. Spring Boot 4.x Package and Configuration Namespace Changes

This is an important difference when upgrading projects from Boot 3.5 to Boot 4.x.

| Component | Spring Boot 3.5 | Spring Boot 4.x |
|---|---|---|
| MVC error auto-config | `org.springframework.boot.autoconfigure.web.servlet.error.ErrorMvcAutoConfiguration` | `org.springframework.boot.webmvc.autoconfigure.error.ErrorMvcAutoConfiguration` |
| BasicErrorController | `org.springframework.boot.autoconfigure.web.servlet.error.BasicErrorController` | `org.springframework.boot.webmvc.autoconfigure.error.BasicErrorController` |
| ErrorAttributes | `org.springframework.boot.web.servlet.error.ErrorAttributes` | `org.springframework.boot.webmvc.error.ErrorAttributes` |
| DefaultErrorAttributes | `org.springframework.boot.web.servlet.error.DefaultErrorAttributes` | `org.springframework.boot.webmvc.error.DefaultErrorAttributes` |
| Error settings prefix | `server.error.*` | `spring.web.error.*` |
| Error path property | `server.error.path` | `spring.web.error.path` |
| Whitelabel property | `server.error.whitelabel.enabled` | `spring.web.error.whitelabel.enabled` |

Boot 4.x example:

~~~properties
spring.web.error.path=/error
spring.web.error.include-message=never
spring.web.error.include-stacktrace=never
spring.web.error.include-binding-errors=never
spring.web.error.whitelabel.enabled=true
~~~

Do not copy Boot 3.5's `server.error.*` configuration verbatim into Boot 4 assuming it still takes effect. Check the **Common Application Properties** and **Spring Boot 4.0 Configuration Changelog** for your running version.

Other components such as `ProblemDetail`, `HandlerExceptionResolver`, and Spring Security also have package/API changes across major versions. The runnable example in this article is pinned to Boot 3.5 so imports remain consistent.

## 10. Lightweight Customization with ErrorAttributes: Prefer Keeping BasicErrorController

If you only need to add a safe field to JSON errors, **there is no need to rewrite ErrorController**. In Boot 3.5, you can subclass `DefaultErrorAttributes`.

Example adding a static application name:

**File src/main/java/com/example/errors/SafeErrorAttributes.java**

~~~java
package com.example.errors;

import java.util.Map;

import org.springframework.stereotype.Component;
import org.springframework.boot.web.error.ErrorAttributeOptions;
import org.springframework.boot.web.servlet.error.DefaultErrorAttributes;
import org.springframework.web.context.request.WebRequest;

@Component
public class SafeErrorAttributes extends DefaultErrorAttributes {

    @Override
    public Map<String, Object> getErrorAttributes(
            WebRequest webRequest,
            ErrorAttributeOptions options) {

        Map<String, Object> attributes =
            super.getErrorAttributes(webRequest, options);

        attributes.put("application", "error-demo");
        return attributes;
    }
}
~~~

Key takeaways:

1. This is a bean of type `ErrorAttributes`, so Boot does not create a second `DefaultErrorAttributes` bean.
2. The default `BasicErrorController` still uses the `ErrorAttributes` supplied by the Spring container.
3. `super.getErrorAttributes(webRequest, options)` preserves how Boot applies `include-*` settings.
4. We only add `application` as a fixed string, without exposing unapproved exception messages or stacktraces.
5. Only HTML or JSON bodies generated by `BasicErrorController` reflect this data as appropriate; it is not imposed on every `ResponseEntity` returned by other controllers.

### Adding a Correlation ID

You can add a request ID when it is generated by a trusted filter. Do not treat an arbitrary client-sent header as a verified ID. When reading the ID from MDC or request attributes, verify filter lifecycle, sanitization, length, and consistency across `REQUEST`/`ERROR` dispatches.

The example above deliberately avoids depending on a correlation ID to demonstrate a custom `ErrorAttributes` that compiles and tests cleanly in a Spring Boot 3.5 app.

### Why Not Return Raw Exception Messages by Default?

Exceptions can contain SQL statements, table names, internal class names, file paths, credential fragments, or system details. If responses expose all details, external clients and logs may store sensitive values. Separate:

- **Stable error codes, statuses, and correlation IDs** for clients.
- **Root causes and stacktraces** for controlled logging/observability.

## 11. Creating Custom HTML Error Pages

When serving browsers, you can add HTML error pages instead of the whitelabel page.

In an MVC project with a template engine like Thymeleaf, place:

~~~text
src/main/resources/templates/error/404.html
src/main/resources/templates/error/5xx.html
src/main/resources/templates/error.html
~~~

How the resolver picks a view depends on the status and available resources/templates. The names `404`, `5xx`, and `error` are common conventions in Spring Boot. **Simply placing files in `templates` will not render them if a template engine is missing.**

If not using a template engine, you can add static HTML error pages in Boot-supported locations, for example:

~~~text
src/main/resources/public/error/404.html
src/main/resources/public/error/5xx.html
~~~

Depending on version and resource handling configuration, the resolver selects the appropriate error page. To avoid surprises, test actual requests with `Accept: text/html` after packaging the application JAR.

### Distinguishing HTML Views from JSON Fallbacks

An HTML page placed at `templates/error/404.html` does not make every API 404 turn into HTML. `BasicErrorController` still uses branches matching `Accept` and content negotiation; JSON clients still receive the default JSON error unless you have replaced the mechanism.

### Do Not Put Sensitive Logic Inside Error Templates

Error pages may receive error metadata. Never print exception classes, request params, stacktraces, SQL queries, or user input into HTML. If support info is needed, show a friendly message and a safe correlation ID.

## 12. When Should You Replace ErrorController?

Replacing `ErrorController` means taking ownership of Servlet-stack fallback error responses. Consider this when:

- The entire system API must obey a proprietary error envelope, including errors dispatched by the container.
- Additional media types beyond HTML/JSON are required.
- Full control over error view/status is required by an integrated framework.

If you only need to change messages for business errors, use `@RestControllerAdvice`. If you only need to add fields to the default error body, use `ErrorAttributes`. If you need custom web pages, use template/static error views first.

### Responsibilities of a Custom ErrorController

A custom `ErrorController` must:

- Register the `/error` mapping (or configured error path).
- Distinguish HTML and JSON if serving both browsers and APIs.
- Read Servlet error metadata and produce the right status.
- Never return 200 for 404/500 errors.
- Avoid logging or returning sensitive data.
- Avoid creating exception → `/error` → exception loops.
- Be compatible with Spring Security, filters, `DispatcherType.ERROR`, context path, and gateways.
- Have integration tests running on a real server.

**Do not declare two controllers mapping `/error`** without knowing which bean Boot creates. Spring Boot backs off when a custom `ErrorController` bean exists per auto-config conditions, but your application's own mappings still require control.

### Extending BasicErrorController

In Spring Boot 3.5, `BasicErrorController` can be subclassed to add a `@RequestMapping` with **produces** for a new media type. However, once a custom class becomes the replacement `ErrorController`, you must verify constructors, mappings, and both HTML/JSON branches. This capability is documented by Spring Boot; do not use inheritance just to change a field that `ErrorAttributes` already handles.

## 13. Runnable Java 17+ Example: Servlet /error and ErrorAttributes

This demo uses **Spring Boot 3.5.x**, Java 17+, and Spring MVC with these goals:

- `GET /api/ok` returns 200.
- `GET /api/boom` throws an unhandled exception, leading to error dispatch and status 500.
- `GET /missing-url` with `Accept: application/json` returns 404 via the error-handling mechanism.
- Custom `ErrorAttributes` adds the `application` field if the request is actually handled by `BasicErrorController`.
- `@RestControllerAdvice` handles a specific business error without needing `/error`.

### 13.1. Dependencies

Create a Spring Boot 3.5 project from Spring Initializr with Spring Web and Spring Boot Test. Using Maven, the dependencies are:

~~~xml
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
~~~

Do not add the WebFlux starter to this demo. To test Servlet error dispatch, the project must run as a **Servlet web application**.

### 13.2. Application Class

**File src/main/java/com/example/errors/ErrorApplication.java**

~~~java
package com.example.errors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ErrorApplication {
    public static void main(String[] args) {
        SpringApplication.run(ErrorApplication.class, args);
    }
}
~~~

### 13.3. Controller

**File src/main/java/com/example/errors/DemoController.java**

~~~java
package com.example.errors;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/ok")
    public Map<String, String> ok() {
        return Map.of("result", "ok");
    }

    @GetMapping("/api/boom")
    public String boom() {
        throw new IllegalStateException(
            "internal-debug-message-do-not-expose"
        );
    }

    @GetMapping("/api/business")
    public String business() {
        throw new IllegalArgumentException("invalid business input");
    }

    @GetMapping("/api/direct")
    public ResponseEntity<Map<String, String>> direct() {
        return ResponseEntity
            .status(HttpStatus.CONFLICT)
            .body(Map.of("code", "ALREADY_EXISTS"));
    }
}
~~~

The `ResponseEntity`/`HttpStatus` imports are from Spring Framework. `GET /api/boom` intentionally throws a server error to test the fallback—it is **not** a production pattern for leaving intentional exceptions in place. The test message merely confirms internal details do not appear in the default response.

### 13.4. Custom ErrorAttributes

**File src/main/java/com/example/errors/SafeErrorAttributes.java**

Use the exact full class from Section 10. It has `@Component`, extends `DefaultErrorAttributes`, calls `super`, and adds the `application` field.

### 13.5. @RestControllerAdvice for Business Errors

**File src/main/java/com/example/errors/BusinessErrorAdvice.java**

~~~java
package com.example.errors;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class BusinessErrorAdvice {

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ProblemDetail> invalidInput(
            IllegalArgumentException ex) {

        ProblemDetail body = ProblemDetail.forStatusAndDetail(
            HttpStatus.BAD_REQUEST,
            "Invalid request"
        );
        body.setTitle("Invalid input");

        return ResponseEntity
            .badRequest()
            .body(body);
    }
}
~~~

Here `body` has a safe fixed detail rather than echoing input via `ex.getMessage()`. The handler only catches `IllegalArgumentException`, so `IllegalStateException` from `/api/boom` is not caught by it.

If Spring Security is added, ensure error handling does not accidentally bypass or repeat authentication; see Section 17 for details.

### 13.6. application.properties

**File src/main/resources/application.properties**

~~~properties
server.port=8080
server.error.include-exception=false
server.error.include-message=never
server.error.include-stacktrace=never
server.error.include-binding-errors=never
server.error.include-path=always
~~~

Keep the default `server.error.path=/error` and do not replace `BasicErrorController`.

### 13.7. Running the Project

From the directory containing Maven Wrapper:

~~~bash
./mvnw spring-boot:run
~~~

On Windows:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Try:

~~~bash
curl -i -H "Accept: application/json" http://localhost:8080/api/ok
curl -i -H "Accept: application/json" http://localhost:8080/api/boom
curl -i -H "Accept: application/json" http://localhost:8080/missing-url
curl -i -H "Accept: application/json" http://localhost:8080/api/business
curl -i -H "Accept: application/json" http://localhost:8080/api/direct
~~~

Results **to verify**:

| Endpoint | Expected HTTP Status | Handling Path |
|---|---|---|
| `/api/ok` | 200 | Normal controller |
| `/api/boom` | 500 | Unhandled exception → container error dispatch → `/error` |
| `/missing-url` | 404 | Missing route → MVC/container error handling → `/error` in demo config |
| `/api/business` | 400 | `@RestControllerAdvice` |
| `/api/direct` | 409 | Controller returns `ResponseEntity` directly |

For `/api/boom` and `/missing-url`, the JSON error generated by `BasicErrorController` typically includes `application: "error-demo"`, the corresponding status, and safe metadata per config. For `/api/business`, `@RestControllerAdvice` directly returns `ProblemDetail`; do not expect `ErrorAttributes`'s `application` field automatically. For `/api/direct`, the controller returns `code=ALREADY_EXISTS` and does not need to go through `/error`.

**Do not assert rigidly against the entire JSON error** because timestamps, path fields, and Boot properties can vary across versions. Assert only the fields you control and required statuses.

## 14. Testing Error Dispatch: Why MockMvc Is Not Enough

This is an easily missed point. `MockMvc` simulates the Spring MVC layer **without starting a full Servlet container**. Spring Boot explicitly notes that error-page mechanisms depend on the container, so `MockMvc` cannot directly test forwarding to custom error pages or the entire `/error` flow.

| Test Type | What It Tests Well | What You Should Not Assume It Covers |
|---|---|---|
| `ErrorAttributes` unit test | Map fields and options given a suitable `WebRequest` | Real Servlet dispatch |
| `MockMvc` | Controller mapping, `@ExceptionHandler`, MVC status/body | Container error-page registration/forward |
| `@SpringBootTest RANDOM_PORT` | Real Servlet container, error dispatch, end-to-end HTTP | External proxies by default |
| Browser/curl | HTML/JSON negotiation, real status and headers | Business rollback/transaction assertions |

Therefore, use `RANDOM_PORT` for the most important test in this lesson.

### 14.1. Integration Test with TestRestTemplate

With Spring Boot 3.5, file:

**src/test/java/com/example/errors/ErrorDispatchIntegrationTest.java**

~~~java
package com.example.errors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class ErrorDispatchIntegrationTest {

    @Autowired
    private TestRestTemplate restTemplate;

    private ResponseEntity<String> getJson(String path) {
        HttpHeaders headers = new HttpHeaders();
        headers.setAccept(List.of(MediaType.APPLICATION_JSON));

        return restTemplate.exchange(
            path,
            HttpMethod.GET,
            new HttpEntity<>(headers),
            String.class
        );
    }

    @Test
    void missingRouteGoesThroughDefaultErrorController() {
        ResponseEntity<String> response = getJson("/missing-url");

        assertThat(response.getStatusCode())
            .isEqualTo(HttpStatus.NOT_FOUND);
        assertThat(response.getBody())
            .contains("\"status\":404")
            .contains("\"application\":\"error-demo\"");
    }

    @Test
    void unhandledExceptionDoesNotExposeInternalMessage() {
        ResponseEntity<String> response = getJson("/api/boom");

        assertThat(response.getStatusCode())
            .isEqualTo(HttpStatus.INTERNAL_SERVER_ERROR);
        assertThat(response.getBody())
            .contains("\"status\":500")
            .contains("\"application\":\"error-demo\"")
            .doesNotContain("internal-debug-message-do-not-expose");
    }

    @Test
    void controllerAdviceHandlesBusinessException() {
        ResponseEntity<String> response = getJson("/api/business");

        assertThat(response.getStatusCode())
            .isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(response.getBody())
            .contains("Invalid request")
            .doesNotContain("\"application\":\"error-demo\"");
    }

    @Test
    void directResponseEntityDoesNotNeedErrorDispatch() {
        ResponseEntity<String> response = getJson("/api/direct");

        assertThat(response.getStatusCode())
            .isEqualTo(HttpStatus.CONFLICT);
        assertThat(response.getBody())
            .contains("ALREADY_EXISTS")
            .doesNotContain("\"application\":\"error-demo\"");
    }
}
~~~

Assertions deliberately avoid checking timestamp, key ordering, or media-type parameters. Error status values and `application` are the key parts of the demo contract. If a server enables global JSON pretty-printing, checking the exact substring `"\"status\":404"` may need to switch to JSONPath/JsonNode; the demo disables pretty-printing by default.

### 14.2. Testing Browser HTML

Run the application, then call:

~~~bash
curl -i -H "Accept: text/html" http://localhost:8080/missing-url
~~~

If no template/static error page exists and whitelabel is enabled, you normally see the HTML fallback. If `error/404.html` is placed, the result may switch to your custom view.

Do not test HTML by hitting `/error` directly without error metadata and treating it as a real 404 request. Request a URL that triggers an error and let the container dispatch.

## 15. Can You Customize /error via Error Page Registration?

Servlet containers allow defining error pages by status or exception type. Spring Boot provides extension points to register error pages with the embedded server. For example, container-level APIs include **ErrorPage** and container factory customizers.

However, manually adding error pages can alter processing order and prevent requests from flowing through `BasicErrorController` by default. If your requirement is just a custom HTML page for 404 while keeping JSON error defaults, start with **error views** instead of changing error-page mappings.

An advanced pseudocode configuration example:

~~~text
HTTP 404 -> custom /not-found page
HTTP 500 -> /error
~~~

If applied, verify: exception context, status code, security filter dispatcher type, static resources, redirect/forward behavior, and client `Accept`. Do not use this configuration just to change a message in a 404 JSON response.

### WAR Deployment and ErrorPageFilter

For WAR applications deployed into an external Servlet container, Spring Boot may use **ErrorPageFilter** to forward error requests to the appropriate error page. Its mechanism and limits differ from embedded-server error page registration.

`ErrorPageFilter` can only forward if the response has not yet been committed. Thus, errors occurring after data has been flushed may no longer produce a clean HTML/JSON error page. If the app runs behind a reverse proxy, the proxy may also overwrite backend bodies/statuses with its own 502/503 pages.

## 16. Cases That Do Not Go Through /error as You Might Expect

### 16.1. @ExceptionHandler Already Handled the Error

When an advice returns `ResponseEntity<ProblemDetail>`, Spring MVC can consider the exception resolved. `BasicErrorController` does not need to participate.

### 16.2. Controller Actively Returns 400/404/409

Returning `ResponseEntity.status(...).body(...)` is a valid HTTP response. An error-range status **does not by itself prove** the container ran an error dispatch.

### 16.3. Response Already Committed

If a servlet/controller has already sent headers or part of the body before throwing an exception, there is no guarantee the server can construct a new error response. Overwriting status/body after commit may be impossible.

### 16.4. Spring Security Returns Errors in the Filter Chain

Spring Security has its own mechanisms for authentication (401) and authorization (403) via filters/entry points/access denied handlers. These responses may be produced without reaching `BasicErrorController`. When configuring the `ERROR` dispatcher type, check security matchers so error dispatches are not rejected a second time.

### 16.5. Errors Originating from a Reverse Proxy

A gateway or load balancer can return 404/502/503/504 before the request reaches Boot. The application's `ErrorAttributes` cannot modify a response it had no part in creating.

### 16.6. Errors from Static Resources or Unmapped URLs

Spring MVC and Boot have multiple resolvers/resource handlers. Missing static resources, missing routes, unsupported methods, and converter exceptions may traverse different processing branches before reaching fallback. Inspect both the request path and actual exception type rather than guessing from the final status alone.

## 17. Security and Observability of /error

### Protecting Error Metadata

In production, never allow clients to request stacktraces simply by appending a query parameter. Avoid `include-message=always` when exception messages can contain sensitive data.

A safe error response might provide:

~~~json
{
  "status": 500,
  "code": "INTERNAL_ERROR",
  "message": "The system could not process the request",
  "requestId": "a1b2c3d4"
}
~~~

This is an **illustrative application-designed schema**, not `BasicErrorController`'s default schema. Achieving a consistent schema across all errors requires coordinating advice, `ErrorAttributes`, and security/gateway layers.

### ERROR Dispatcher Type and Security Filters

In Servlet applications, filters are registered for specific dispatcher types. Sometimes an error dispatch gets re-evaluated by security filters, causing:

- An original 404 turning into 401/403.
- An HTML error page getting blocked.
- A 500 error being masked by a different response.
- Logs showing two passes of filter processing.

Do not solve this by opening permissions across the entire application. With modern Spring Security, define permissions for **DispatcherType.ERROR** or error routes under controlled policy, opening only what is needed to render error responses while keeping business APIs authenticated.

### Avoiding Loops When Customizing /error

A custom `ErrorController` might throw an exception itself, call a failing service, or forward back to `/error`. The container then hits another error while handling the first, obscuring the original root cause.

Therefore, a custom error handler should:

- Have minimal dependencies and avoid external I/O.
- Not read from the database to render a 500 message.
- Not share fragile components with business paths.
- Log the cause at a controlled layer and produce a minimal response.
- Be tested even for failures inside the handler itself.

### Attaching a Request ID

Use a correlation ID generated at the gateway or server per trust policy and pass it through logging/observability. Never output stacktraces to clients; return `requestId` so support teams can look it up in logs. Do not store emails/tokens/raw bodies in `ErrorAttributes` or MDC without protection policies.

## 18. Troubleshooting by Symptom

| Symptom | Possible Cause | How to Verify |
|---|---|---|
| API error returns HTML instead of JSON | Client sent `Accept: text/html` or browser default | Run `curl -H "Accept: application/json"` against a genuinely failing URL |
| `/error` returns 200 or odd data when called manually | Missing Servlet error dispatch attributes | Trigger a real 404/500 request and check final status |
| Status 404 lacks `application` field from custom `ErrorAttributes` | Controller/advice/security returned response directly | Check controller path, filters, and error dispatch |
| Custom `ErrorAttributes` is not used | Bean not scanned, another bean takes precedence, wrong classpath/version | Inspect bean types in `ApplicationContext` and condition report |
| Stacktrace appears in public response | `include-stacktrace=always/on_param` or controller serializes stacktrace | Inspect properties and custom error serialization |
| Whitelabel disabled yet HTML error still appears | Custom error view or container page still serves HTML | Check view resolvers and container defaults |
| App on Boot 4 ignores `server.error.path` | Config prefix changed to `spring.web.error.*` | Check version-specific application properties |
| MockMvc test does not hit custom `/error` page | Lacks full Servlet container error dispatch | Use `@SpringBootTest(RANDOM_PORT)` with real HTTP client |
| Context fails to start after adding custom `ErrorController` | Duplicate mapping or bean/config conflict | Read startup failure and remove duplicate controller |
| A 500 error turns into 403 | Security filter re-processes `ERROR` dispatch | Check `DispatcherType.ERROR`, filter order, and logs |
| Error response replaced with 502/503 | Proxy/gateway emitted error instead of backend | Compare gateway logs, backend status, and request ID |
| Error page fails to write after exception | Response already committed or stream flushed | Find flush/write point and root cause in server logs |
| Error view template does not render | Missing template engine, wrong path, or packaging issue | Check classpath, `templates/error/404.html`, and JAR contents |
| Error body leaks raw exception message | Advice/custom `ErrorAttributes` directly outputs `ex.getMessage` | Use fixed public messages and log root cause separately |

### Quick Triage Workflow

1. Record method, path, `Accept`, and actual status.
2. Determine whether the request reached Boot or was answered by a proxy.
3. Check whether a controller/advice actively created the response.
4. Inspect Servlet error dispatch, `RequestDispatcher.ERROR_STATUS_CODE`, and `ERROR_REQUEST_URI` when needed.
5. Check `BasicErrorController`/`ErrorAttributes` beans if using defaults.
6. Check `server.error.*` or `spring.web.error.*` according to Boot version.
7. Inspect security filters and `DispatcherType.ERROR`.
8. Use HTTP integration tests with `RANDOM_PORT` to verify real 404/500 behavior.

## 19. Self-Check Exercises

1. What is `/error` used for in Servlet applications? Is it a business API endpoint for clients to call directly?
2. What does `BasicErrorController` decide, and what does `ErrorAttributes` provide?
3. Why does the same error sometimes return HTML and sometimes JSON?
4. Once `@RestControllerAdvice` returns 400, must the request still go through `/error`?
5. Does `ResponseEntity.notFound().build()` guarantee `DefaultErrorAttributes` is called?
6. In Boot 3.5, what property configures the error controller path?
7. In Boot 4.x, how do the property and `BasicErrorController` package change?
8. Why shouldn't `include-stacktrace=on_param` be enabled in public production?
9. What `DispatcherType` does an error dispatch have, and what `DispatcherType` does the original request usually have?
10. To add an `application` field to default JSON while keeping `BasicErrorController`, which extension point should you use?
11. Why is `MockMvc` insufficient to test the Servlet container's error-page registration?
12. If an HTTP 500 has already committed headers, can the server always render a different error page?
13. When a 404 is turned into a 403 by Spring Security, what should you check?
14. Which deployment type is `ErrorPageFilter` typically associated with?
15. If you want to customize business error bodies without touching the default 500 fallback, which mechanism should you use?

### Suggested Answers

1. It is an error mapping registered by Boot for the Servlet container to route errors to a common handler; not a standard business API.
2. `BasicErrorController` chooses the response status and view/media type; `ErrorAttributes` supplies the map of error data and cause if available.
3. Content negotiation/`Accept` for HTML or JSON and configured error views.
4. No; MVC can complete the response through an exception resolver.
5. No; a response created directly by a controller may not trigger an error dispatch.
6. `server.error.path` (default `/error`).
7. `spring.web.error.path`; `BasicErrorController` moves to `org.springframework.boot.webmvc.autoconfigure.error`.
8. Clients can supply the query parameter themselves, leaking traces and internal info.
9. `ERROR` and `REQUEST`.
10. An `ErrorAttributes` bean, e.g., subclassing `DefaultErrorAttributes` and overriding `getErrorAttributes`.
11. It does not start or fully execute the embedded Servlet container; use `RANDOM_PORT`.
12. No, a committed response cannot easily change status/body.
13. Filter mappings, `DispatcherType.ERROR`, and security authorization/entry points.
14. WAR deployment in an external Servlet container.
15. `@RestControllerAdvice` and `@ExceptionHandler`; optionally paired with `ProblemDetail`/`ResponseEntity`.

## 20. Official References

- [Spring Boot 3.5 — Servlet Web Applications: Error Handling](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): `/error`, `BasicErrorController`, `ErrorAttributes`, HTML/JSON, custom views, and WAR deployment.
- [Spring Boot 3.5 — BasicErrorController Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/servlet/error/BasicErrorController.html): mappings, `errorHtml`, `error`, and `ErrorAttributeOptions`.
- [Spring Boot 3.5 — DefaultErrorAttributes Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/servlet/error/DefaultErrorAttributes.html): error fields and `getErrorAttributes` contract.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): `server.error.*` and default values.
- [Spring Boot 4.0 — Servlet Web Applications](https://docs.spring.io/spring-boot/4.0/reference/web/servlet.html): `/error` mechanism and `spring.web.error.*`.
- [Spring Boot 4.0 — BasicErrorController Javadoc](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/webmvc/autoconfigure/error/BasicErrorController.html): new package and mapping property.
- [Spring Boot 4.0 Configuration Changelog](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Configuration-Changelog): replacing `server.error.*` with `spring.web.error.*`.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `MockMvc` vs. real Servlet server when testing error pages.
- [Spring Framework — MVC Exceptions](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html): `@ExceptionHandler` and resolver flow.
- [Spring Framework — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): `ProblemDetail`, HTTP API error responses.
- [Jakarta Servlet API — RequestDispatcher](https://jakarta.ee/specifications/servlet/): dispatcher types and `ERROR_*` request attributes.