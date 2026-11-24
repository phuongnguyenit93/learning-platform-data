# ErrorWebExceptionHandler, DefaultErrorWebExceptionHandler, and ErrorAttributes in Spring WebFlux

In a **Spring Boot WebFlux** application, when an error is not resolved by a controller, functional handler, or local error-handling mechanism, Spring Boot can route it through the global error-handling layer to build an HTTP response. Three similar-sounding names carry distinct responsibilities:

- **ErrorAttributes**: supplies information about the error, such as HTTP status, request path, timestamp, error code, safe message, and auxiliary metadata.
- **DefaultErrorWebExceptionHandler**: Spring Boot's built-in implementation for rendering error responses, typically as JSON for API clients or HTML when a client requests HTML and a matching error page exists.
- **ErrorWebExceptionHandler**: marker interface extending `WebExceptionHandler` for components dedicated to **rendering errors**. The default implementation can be replaced when global response control is needed.

This lesson uses **Spring Boot 3.5.16, Spring Framework 6.2.x, and Java 17+**. The main example uses **spring-boot-starter-webflux** and Reactor Netty, not Spring MVC/Servlet. Package APIs must be clearly distinguished:

~~~text
Reactive WebFlux (Spring Boot 3.5.x):
org.springframework.boot.web.reactive.error.ErrorAttributes
org.springframework.boot.web.reactive.error.DefaultErrorAttributes
org.springframework.boot.web.reactive.error.ErrorWebExceptionHandler
org.springframework.boot.autoconfigure.web.reactive.error.DefaultErrorWebExceptionHandler
org.springframework.boot.autoconfigure.web.reactive.error.AbstractErrorWebExceptionHandler

Servlet Spring MVC (DIFFERENT):
org.springframework.boot.web.servlet.error.ErrorAttributes
org.springframework.boot.autoconfigure.web.servlet.error.BasicErrorController
~~~

The name `ErrorAttributes` exists in both web stacks, but **they do not share the same interface method signatures**. In WebFlux, the attribute-lookup method takes `ServerRequest`. In Servlet MVC, it takes `WebRequest`. Copying the wrong import can cause compilation failures or prevent auto-configuration from picking up the bean.

## 1. Overview: Where Does an Error Travel to Become a Response?

Spring WebFlux provides `DispatcherHandler` along with `HandlerMapping`/`HandlerAdapter`/`HandlerResultHandler` for annotated controllers and WebFlux.fn. When a pipeline emits an error signal, multiple layers have an opportunity to handle it before it reaches the global `WebExceptionHandler`.

Mental model:

~~~text
HTTP request
  |
  v
Reactive HTTP server (usually Reactor Netty)
  |
  v
WebExceptionHandler chain wrapping WebHandler
  |
  +--> WebFilter / SecurityWebFilterChain
  |          |
  |          v
  |      DispatcherHandler
  |          |
  |          +--> @RestController
  |          |      -> @ExceptionHandler / @RestControllerAdvice
  |          |      -> may handle error and return response directly
  |          |
  |          +--> RouterFunction + HandlerFunction
  |                 -> onErrorResume / router filter may handle it
  |
  +--> Unhandled error with response not yet committed
             |
             v
       ErrorWebExceptionHandler
             |
             v
       DefaultErrorWebExceptionHandler (Boot default)
             |
             +--> ErrorAttributes: status, path, error data...
             |
             +--> JSON or HTML error view
             |
             v
       HTTP 4xx/5xx response
~~~

The diagram illustrates **handling opportunities**, not every exact decorator or callback in each implementation. Note:

1. An error handler can only handle an error that is **propagated to it**; if a controller already converted the error into a normal response, the global layer cannot infer that an error is still pending.
2. Once an HTTP response has begun writing headers/body, status and headers may no longer be changeable. A mid-stream Flux error is not guaranteed to become a fresh JSON 500.
3. Certain errors are handled by WebFlux or Security before reaching Boot's fallback. Do not assume every 400/401/403/404 automatically passes through the same custom `ErrorAttributes`.
4. A reactive error signal differs from calling `subscribe()` or throwing an exception on a thread unrelated to the request. Errors are handled while remaining within the publisher/chain managed by the framework.

## 2. Role of ErrorWebExceptionHandler

Spring Framework defines the interface:

~~~java
org.springframework.web.server.WebExceptionHandler
~~~

with one core method:

~~~java
Mono<Void> handle(ServerWebExchange exchange, Throwable ex);
~~~

In Spring Boot, **ErrorWebExceptionHandler** in package `org.springframework.boot.web.reactive.error` is a marker interface extending `WebExceptionHandler` to identify implementations intended for **WebFlux error rendering**.

An implementation can:

- Read the request, response, and exception.
- Choose an appropriate HTTP status.
- Select media type, headers, and response content.
- Write the response via reactive publishers and return `Mono<Void>`.
- Or decline handling and forward the error to another handler in the chain.

**Implementing the lowest-level interface directly is not always advisable.** Writing directly to `ServerHttpResponse` requires managing many details: content negotiation, encoding, committed responses, logging, statuses, response headers, and cancellation. If you only want to add error codes to JSON, **a custom `ErrorAttributes` is usually simpler and safer**.

### 2.1. Ordering in the Exception Handler Chain

In Spring Boot 3.5.16, `ErrorWebFluxAutoConfiguration` registers the default `ErrorWebExceptionHandler` with **@Order(-1)** when no application-provided `ErrorWebExceptionHandler` bean exists. Other WebFlux framework exception handlers typically sit after it in priority.

If an application registers its own `ErrorWebExceptionHandler`, Boot **backs off** and does not create the default error renderer. The application then owns responsibility for constructing error responses for requests handled by that new handler.

A handler with a lower order value runs earlier in the ordered chain, but **ordering alone does not guarantee a handler receives every error**: exceptions already handled locally or detached from the pipeline never reach it.

Do not tweak `@Order` blindly to fix bugs. Decide upfront which handler owns which errors, which errors propagate onward, and how to test globally.

## 3. What Does DefaultErrorWebExceptionHandler Do?

**DefaultErrorWebExceptionHandler** is Spring Boot's global implementation. It extends **AbstractErrorWebExceptionHandler** and uses `ErrorAttributes` to populate response data.

Core responsibilities:

- Retrieve error data via `ErrorAttributes`.
- Apply the appropriate HTTP status from error attributes.
- Distinguish requests wanting HTML from those suited for JSON.
- Locate error views per Boot conventions and fall back to the Whitelabel error page for HTML.
- Produce JSON responses for machine clients.
- Participate in WebFlux's codecs and message readers/writers system.
- Respect error properties controlling inclusion of message, stack trace, binding errors, and path.

Extension methods in the Boot 3.5 API include:

| Method | Purpose |
|---|---|
| `getRoutingFunction(ErrorAttributes)` | Creates internal `RouterFunction` choosing how to render the error |
| `renderErrorResponse(ServerRequest)` | Renders the JSON error body |
| `renderErrorView(ServerRequest)` | Renders the HTML error view |
| `acceptsTextHtml()` | Predicate checking whether the client accepts HTML |
| `getErrorAttributeOptions(ServerRequest, MediaType)` | Determines which data is permitted inside error attributes |
| `getHttpStatus(Map<String,Object>)` | Extracts HTTP status from the error map |
| `isIncludeMessage` / `isIncludeStackTrace` ... | Decides whether sensitive data may enter the response |

These are **version-dependent extension hooks**, not application service methods. When upgrading Boot, inspect Javadocs and migration guides before overriding them.

### 3.1. DefaultErrorWebExceptionHandler Is Not a @RestController

Although Boot uses a `RouterFunction` inside its error handler, it is not a public functional endpoint for clients to call directly to simulate errors. It is part of the exception-handling chain.

Spring MVC has `BasicErrorController` and Servlet container error dispatch. **Do not port MVC's `BasicErrorController` or `ErrorController` patterns directly to reactive WebFlux** expecting identical behavior. In the reactive stack, the interfaces and lifecycle are different.

### 3.2. JSON or HTML?

Boot supports rendering HTML by default when the client **explicitly accepts `text/html`** and a matching error view exists, while API clients typically receive JSON when requesting `Accept: application/json`.

A request:

~~~http
GET /api/unknown HTTP/1.1
Host: localhost:8080
Accept: application/json
~~~

usually receives a JSON error body if the error was not handled elsewhere. A browser sending `Accept` with `text/html` may receive an HTML error page. **Do not test a single content type without controlling `Accept`**, because the same 404 status can return different bodies.

Error views can be placed at:

~~~text
src/main/resources/public/error/404.html
src/main/resources/public/error/4xx.html
src/main/resources/templates/error/5xx.html
~~~

Spring Boot resolves views in order matching exact status, series, and generic error page. A template engine is required when using dynamic templates. In WebFlux, the fallback template path is typically `error/error`; lookup rules differ from Servlet MVC. Having HTML files does not guarantee all error requests receive HTML: content negotiation still applies.

## 4. What Information Does ErrorAttributes Contain?

The reactive interface **org.springframework.boot.web.reactive.error.ErrorAttributes** provides:

~~~java
Throwable getError(ServerRequest request);

Map<String, Object> getErrorAttributes(
        ServerRequest request,
        ErrorAttributeOptions options);

void storeErrorInformation(
        Throwable error,
        ServerWebExchange exchange);
~~~

These are **abbreviated API signatures for illustration**, not a standalone Java class.

Boot's **DefaultErrorAttributes** can supply:

- timestamp: time when error data was gathered.
- status: HTTP code, e.g., 400, 404, 500.
- error: status name or error reason.
- path: request path, per options/configuration.
- requestId: ID associated with the request when available.
- message: error message if permitted.
- exception: exception class name if permitted.
- errors: binding/method validation errors if permitted.
- trace: stack trace if permitted.

**Keys are not guaranteed to appear in all cases.** The data depends on the error, options, `server.error.*` properties, Boot version, and whichever handler rendered the response.

### 4.1. ErrorAttributeOptions and Data Exposure Rules

Spring Boot's `ErrorAttributeOptions` allows including/excluding items such as:

~~~text
ErrorAttributeOptions.Include.MESSAGE
ErrorAttributeOptions.Include.STACK_TRACE
ErrorAttributeOptions.Include.BINDING_ERRORS
ErrorAttributeOptions.Include.EXCEPTION
ErrorAttributeOptions.Include.PATH
~~~

Internal errors can contain upstream URLs, database table names, SQL snippets, object IDs, system paths, or authentication credentials. Therefore, **never open stack traces, exception class names, or raw exception messages to all production clients**.

`ErrorAttributes` may receive raw server data, yet public responses must follow a **safe contract**: status, stable code, vetted message, and request ID if appropriate. True technical details belong in access-controlled logs and traces.

### 4.2. Why Extend DefaultErrorAttributes?

By overriding `getErrorAttributes` on **DefaultErrorAttributes**, you preserve default behavior for extracting the exception, resolving status, storing the error on `ServerWebExchange`, and populating standard fields.

Implementing `ErrorAttributes` from scratch requires fulfilling the full `getError` and `storeErrorInformation` contract; missing details can easily prevent the default renderer from locating the error or status.

## 5. Strategy for Choosing the Right Customization Level

| Need | Preferred Extension Point | Why |
|---|---|---|
| Only customize JSON content, add code/correlation ID | `ErrorAttributes` bean extending `DefaultErrorAttributes` | Keeps default renderer and content negotiation |
| Only toggle message/trace inclusion | `server.error.*` properties | Minimal code and easy per-environment tuning |
| Want RFC 9457 Problem Details for built-in exceptions | `spring.webflux.problemdetails.enabled` and WebFlux exception handling | Uses framework standard before rolling your own |
| Handle exceptions for one annotated controller or group | `@ExceptionHandler`, `@RestControllerAdvice` | Clear scope, close to API contract |
| Handle errors for a specific functional route | `onErrorResume` or WebFlux.fn handler/filter | Router-scoped, avoids affecting entire app |
| Change global JSON/HTML selection or error routing logic | Extend `DefaultErrorWebExceptionHandler` or `AbstractErrorWebExceptionHandler` | Reuses builder and codec infrastructure |
| Write output bytes/headers manually with full lifecycle control | Lowest-level `ErrorWebExceptionHandler` | Flexible but complex and error-prone |
| Render custom 404/5xx HTML | Static/template error pages | Avoids writing a global low-level handler |

**Rule of thumb:** customize data before customizing flow; customize flow only when a concrete requirement demands it and tests verify critical default behaviors remain intact.

## 6. Runnable Java 17+ Project: Custom ErrorAttributes, Keeping Boot Handler

We will build a WebFlux application with:

1. `GET /api/demo/ok` returning 200.
2. `GET /api/demo/bad-request` explicitly emitting `ResponseStatusException(400)`.
3. `GET /api/demo/failure` emitting `IllegalStateException` to simulate a server error.
4. An unmapped URL such as `/api/no-such-resource`, typically returning 404.
5. Custom **SanitizedErrorAttributes** adding a safe `code`/`message` and removing unwanted internal error attributes.
6. `DefaultErrorWebExceptionHandler` still auto-configured by Spring Boot; **no** custom `ErrorWebExceptionHandler` is added.
7. Integration tests over real HTTP using `WebTestClient` and `RANDOM_PORT`.

**Example scope:** no database, messaging, or external HTTP calls. This lesson covers error boundaries, not a full enterprise error catalog.

### 6.1. Directory Structure

~~~text
webflux-error-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/errors/
    │   │   ├── ErrorsApplication.java
    │   │   ├── DemoController.java
    │   │   └── SanitizedErrorAttributes.java
    │   └── resources/application.yml
    └── test/
        └── java/com/example/errors/
            └── ErrorContractTest.java
~~~

### 6.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>webflux-error-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>webflux-error-demo</name>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

Do not add `spring-boot-starter-web`, since the goal is Spring WebFlux's reactive server rather than Spring MVC. The parent manages matching dependency versions. Maven requires Internet/cache/mirror access for dependencies when building.

### 6.3. application.yml

~~~yaml
server:
  port: 8080
  error:
    include-message: never
    include-stacktrace: never
    include-binding-errors: never

spring:
  application:
    name: webflux-error-demo
~~~

These `server.error.*` properties act as the first line of defense against accidentally leaking exception details into responses. The example also uses a custom `ErrorAttributes` to standardize safe output.

`spring.webflux.problemdetails.enabled` is intentionally left off in **this demo** so we can observe `DefaultErrorWebExceptionHandler` and Boot's JSON error map directly. Another application may enable Problem Details, provided its interactions and actual format are tested.

### 6.4. ErrorsApplication.java

~~~java
package com.example.errors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ErrorsApplication {

    public static void main(String[] args) {
        SpringApplication.run(ErrorsApplication.class, args);
    }
}
~~~

The class lives in root package `com.example.errors` so `DemoController` and `SanitizedErrorAttributes` are component-scanned. `@EnableWebFlux` is unnecessary because Boot auto-configures the reactive web stack.

### 6.5. DemoController.java

~~~java
package com.example.errors;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/demo")
public class DemoController {

    @GetMapping("/ok")
    public Mono<Map<String, String>> ok() {
        return Mono.just(Map.of("result", "ok"));
    }

    @GetMapping("/bad-request")
    public Mono<Map<String, String>> badRequest() {
        return Mono.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "Internal diagnostic details must stay private"));
    }

    @GetMapping("/failure")
    public Mono<Map<String, String>> failure() {
        return Mono.error(new IllegalStateException(
                "Internal failure details must stay private"));
    }
}
~~~

The code returns `Mono.error` so errors **stay inside the reactive pipeline**, rather than calling `subscribe` outside the request lifecycle. In real projects, errors may come from R2DBC, `WebClient`, or services; security and logging requirements remain the same.

`ResponseStatusException` expresses an intentional HTTP error with a status. `IllegalStateException` carries no HTTP status itself, so the global handler treats it as a 500 server error when no custom mapping exists.

### 6.6. SanitizedErrorAttributes.java: Main Extension Point

~~~java
package com.example.errors;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.web.error.ErrorAttributeOptions;
import org.springframework.boot.web.reactive.error.DefaultErrorAttributes;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;

@Component
public class SanitizedErrorAttributes extends DefaultErrorAttributes {

    @Override
    public Map<String, Object> getErrorAttributes(
            ServerRequest request,
            ErrorAttributeOptions options) {

        Map<String, Object> attributes = new LinkedHashMap<>(
                super.getErrorAttributes(request, options));

        int status = ((Number) attributes
                .getOrDefault("status", 500)).intValue();

        attributes.remove("trace");
        attributes.remove("exception");
        attributes.remove("errors");
        attributes.remove("message");

        String code = switch (status) {
            case 400 -> "BAD_REQUEST";
            case 404 -> "NOT_FOUND";
            default -> status >= 500
                    ? "INTERNAL_ERROR" : "HTTP_ERROR";
        };

        String message = switch (status) {
            case 400 -> "Invalid request";
            case 404 -> "Resource not found";
            default -> status >= 500
                    ? "Unexpected server error" : "Request failed";
        };

        attributes.put("code", code);
        attributes.put("message", message);
        return attributes;
    }
}
~~~

This is a complete Java class that can be copied into the project following the layout above.

**Why do it this way?**

- `@Component` creates an `ErrorAttributes` bean, so `ErrorWebFluxAutoConfiguration` does not create a second `DefaultErrorAttributes` bean.
- Extending `DefaultErrorAttributes` keeps status extraction and error metadata required by the default renderer.
- `LinkedHashMap` creates a mutable copy without directly mutating the superclass map.
- Do not delete `status`: **`DefaultErrorWebExceptionHandler` uses `status` to set the response status**.
- Remove old `trace`/`exception`/`errors`/`message` entries to avoid depending on raw messages.
- Add `code` as a stable machine-readable code; `message` is a safe public sentence.
- Never use `exception.getMessage()` to build client-facing messages for 500s, because exceptions can carry sensitive data.

**Demo limitation:** every 4xx other than 400/404 receives code `HTTP_ERROR` and message `Request failed`. Production APIs should maintain a stable error catalog by status/business type, support i18n, and test 401/403/405/409/422 separately. Never treat all 400 statuses as a single business error type.

## 7. Integration Testing with WebTestClient

File **src/test/java/com/example/errors/ErrorContractTest.java**:

~~~java
package com.example.errors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ErrorContractTest {

    @Autowired
    private WebTestClient client;

    @Test
    void successfulRequestIsNotRewritten() {
        client.get()
                .uri("/api/demo/ok")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.result").isEqualTo("ok");
    }

    @Test
    void badRequestHasSafePublicError() {
        client.get()
                .uri("/api/demo/bad-request")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.status").isEqualTo(400)
                .jsonPath("$.code").isEqualTo("BAD_REQUEST")
                .jsonPath("$.message").isEqualTo("Invalid request");
    }

    @Test
    void serverErrorDoesNotLeakInternalReason() {
        client.get()
                .uri("/api/demo/failure")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().is5xxServerError()
                .expectBody(String.class)
                .value(body -> {
                    assertThat(body)
                            .contains("INTERNAL_ERROR")
                            .contains("Unexpected server error")
                            .doesNotContain(
                                    "Internal failure details must stay private");
                    assertThat(body).doesNotContain("stackTrace");
                });
    }

    @Test
    void unknownRouteProduces404() {
        client.get()
                .uri("/api/no-such-resource")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isNotFound()
                .expectBody()
                .jsonPath("$.status").isEqualTo(404)
                .jsonPath("$.code").isEqualTo("NOT_FOUND");
    }
}
~~~

This is an **HTTP integration test**: the application runs on a random port, testing WebFlux codecs, error handler auto-configuration, and wire-level response payloads—not merely checking that the `SanitizedErrorAttributes` bean exists.

Keep in mind: with custom security/filters or other error handlers, a 404 may be constructed before reaching Boot's fallback. Because the demo registers no extra security or advice, unmapped routes flow through the default error mechanism.

### 7.1. Running and Interpreting

~~~bash
mvn test
mvn spring-boot:run
~~~

The first command runs JUnit tests. When tests pass, Maven exits with code 0. The second starts the embedded server per `application.yml`; avoid running two Maven processes simultaneously on the fixed port.

Once the server is up, test:

~~~bash
curl -i \
  -H "Accept: application/json" \
  http://localhost:8080/api/demo/ok

curl -i \
  -H "Accept: application/json" \
  http://localhost:8080/api/demo/bad-request

curl -i \
  -H "Accept: application/json" \
  http://localhost:8080/api/demo/failure

curl -i \
  -H "Accept: application/json" \
  http://localhost:8080/api/no-such-resource
~~~

Key expected outcomes:

| Request | HTTP Status | What to Verify |
|---|---|---|
| GET `/api/demo/ok` | 200 | JSON with `result=ok` |
| GET `/api/demo/bad-request` | 400 | `status=400`, `code=BAD_REQUEST`, `message=Invalid request` |
| GET `/api/demo/failure` | 500 | `code=INTERNAL_ERROR`, no internal exception message |
| GET `/api/no-such-resource` | 404 | `code=NOT_FOUND` when handled by Boot fallback |

**Illustrative content example**, key ordering is not fixed:

~~~json
{
  "status": 500,
  "error": "Internal Server Error",
  "code": "INTERNAL_ERROR",
  "message": "Unexpected server error"
}
~~~

`DefaultErrorAttributes` may add `timestamp`, `path`, and `requestId`. Do not assert key ordering, specific timestamps, or request IDs in tests. Actual headers and error bodies can differ when adding Spring Security, custom response handlers, or changing versions.

## 8. Why Keeping DefaultErrorWebExceptionHandler Is Better

In this example, we changed only the **error data**, not **how the response is built**. Doing so lets Boot continue managing:

- Status extraction from the error map.
- JSON writing via configured codecs.
- JSON/HTML content negotiation.
- WebFlux error view conventions.
- `include-message`, `include-stacktrace`, and `include-binding-errors` property handling.
- Integration with the application's auto-configuration.

Even so, a custom `ErrorAttributes` returning an invalid map (such as removing the `status` key, setting `status` to an invalid String, or inserting unserializable objects) can still break the default renderer.

**Good rule:** preserve essential baseline keys; add clear custom codes; never put `Throwable`, `StackTraceElement[]`, or unsafe domain objects into attributes. Custom `ErrorAttributes` is for standardizing **response metadata**, not running database queries.

## 9. DefaultErrorWebExceptionHandler and Content Negotiation

For browsers, `Accept` may include `text/html`. Boot prefers rendering HTML error views in matching cases.

For API clients, send:

~~~http
Accept: application/json
~~~

and check the response `Content-Type`. If a client receives a Whitelabel HTML page instead of JSON, check the **actual `Accept` header**, proxies, and error handler selection before blaming `ObjectMapper`.

### 9.1. 404 Errors Can Be Rendered with Static HTML

Create file:

~~~text
src/main/resources/public/error/404.html
~~~

with illustrative content:

~~~html
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Not Found</title></head>
<body>
  <h1>404 - Page Not Found</h1>
</body>
</html>
~~~

When a browser requests HTML and Boot resolves views by convention, this content can be served for 404. Do not add this file to the API demo if your goal is verifying pure JSON responses for machine clients; it belongs to website UI customization.

If a static page displays user data or internal errors, review security policies. Error pages should provide simple guidance, never stack traces.

## 10. Advanced Customization of DefaultErrorWebExceptionHandler

When you need to **alter rendering selection**—for instance, an API gateway requires error responses to always be JSON even if `Accept` includes `text/html`—you can **extend `DefaultErrorWebExceptionHandler`** and override `getRoutingFunction`.

**Scope note:** the snippet below is an **alternative to the default rendering mechanism** and should not be dropped into the main demo as an ordinary class without replacing the corresponding bean configuration. It alters Boot's HTML/JSON selection, so verify browser and template view contracts.

Example subclass using the exact **Spring Boot 3.5.16** constructor:

~~~java
package com.example.errors;

import org.springframework.boot.autoconfigure.web.ErrorProperties;
import org.springframework.boot.autoconfigure.web.WebProperties;
import org.springframework.boot.autoconfigure.web.reactive.error.DefaultErrorWebExceptionHandler;
import org.springframework.boot.web.reactive.error.ErrorAttributes;
import org.springframework.context.ApplicationContext;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

public class JsonOnlyErrorHandler extends DefaultErrorWebExceptionHandler {

    public JsonOnlyErrorHandler(
            ErrorAttributes errorAttributes,
            WebProperties.Resources resources,
            ErrorProperties errorProperties,
            ApplicationContext applicationContext) {

        super(errorAttributes, resources, errorProperties,
                applicationContext);
    }

    @Override
    protected RouterFunction<ServerResponse> getRoutingFunction(
            ErrorAttributes errorAttributes) {

        return RouterFunctions.route(
                request -> true,
                this::renderErrorResponse);
    }
}
~~~

Here a lambda `RequestPredicate` always matches the error request and invokes the superclass's `renderErrorResponse`. Thus default HTML error views are no longer selected within this handler.

**Important:** the subclass must be **registered as an `ErrorWebExceptionHandler` bean**. Defining the class without declaring a bean does not make Spring Boot use it automatically. Additionally, when registering the handler manually, configure message readers/writers and view resolvers appropriately.

A separate configuration for this advanced option:

~~~java
package com.example.errors;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.autoconfigure.web.ServerProperties;
import org.springframework.boot.autoconfigure.web.WebProperties;
import org.springframework.boot.web.reactive.error.ErrorAttributes;
import org.springframework.boot.web.reactive.error.ErrorWebExceptionHandler;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.result.view.ViewResolver;

@Configuration(proxyBeanMethods = false)
public class JsonOnlyErrorConfiguration {

    @Bean
    @Order(-2)
    ErrorWebExceptionHandler jsonOnlyErrorHandler(
            ErrorAttributes attributes,
            WebProperties webProperties,
            ServerProperties serverProperties,
            ApplicationContext applicationContext,
            ServerCodecConfigurer codecs,
            ObjectProvider<ViewResolver> viewResolvers) {

        JsonOnlyErrorHandler handler = new JsonOnlyErrorHandler(
                attributes,
                webProperties.getResources(),
                serverProperties.getError(),
                applicationContext);

        handler.setMessageReaders(codecs.getReaders());
        handler.setMessageWriters(codecs.getWriters());
        handler.setViewResolvers(
                viewResolvers.orderedStream().toList());

        return handler;
    }
}
~~~

If you try this approach, add **both** `JsonOnlyErrorHandler` and `JsonOnlyErrorConfiguration` to the project and re-test every status. They are **not part of the default runnable version** in Sections 6–7. Because a custom `ErrorWebExceptionHandler` bean now exists, Boot stops auto-configuring `DefaultErrorWebExceptionHandler`. Order `-2` is a specific choice for this example, not a universal constant for all projects.

Because this configuration alters HTML/JSON rendering, test:

- API clients with `Accept: application/json`.
- Browser clients with `Accept: text/html`.
- 404, 400, and 500 from different sources.
- Whether response body or headers are already committed.
- Whether codecs for the desired response format are ready.
- Whether all error attributes remain valid with accurate statuses.

**When you only need safe codes/messages, you do NOT need these advanced classes; `SanitizedErrorAttributes` from Section 6 is enough.**

## 11. AbstractErrorWebExceptionHandler: Between Low-Level and High-Level

Spring Boot provides **AbstractErrorWebExceptionHandler** to build error responses in a functional WebFlux style. It sits between the two extremes:

- Lowest-level `ErrorWebExceptionHandler`: you handle `ServerWebExchange` and `Mono<Void>` yourself.
- `DefaultErrorWebExceptionHandler`: Boot implements nearly everything for JSON/HTML, and you override parts.
- `AbstractErrorWebExceptionHandler`: Boot provides `ErrorAttributes`, routing, message writers/readers, and view resolvers; you define `getRoutingFunction` and how responses are built.

When extending `AbstractErrorWebExceptionHandler`, you must provide an appropriate `RouterFunction`; if the router does not match an error request, the original exception can propagate to subsequent `WebExceptionHandler`s.

This is an important property: **an error handler's internal `RouterFunction` can choose not to handle an error**, so do not assume it always returns a `ServerResponse`.

If you want to replace the entire body format while still working with `ServerRequest`/`ServerResponse`, `AbstractErrorWebExceptionHandler` is usually simpler than implementing `WebExceptionHandler` from scratch. If only changing a status/message, prefer `ErrorAttributes` or local handling.

## 12. What Happens If You Implement ErrorWebExceptionHandler Directly?

A lowest-level implementation has the signature:

~~~java
public interface ErrorWebExceptionHandler
        extends WebExceptionHandler {
}
~~~

This is a structural description of the interface, not a source file to create; the framework already defines it.

A custom handler must handle:

1. Checking `response.isCommitted()` before attempting to modify status/headers.
2. Setting an appropriate HTTP status for the exception rather than returning 500 for all 4xx errors.
3. Selecting `Content-Type`, charset, and codec.
4. Producing a safe body and reactive `Mono<Void>`.
5. Never blocking the event loop with `block()`, `Thread.sleep`, or synchronous JDBC/database calls.
6. Never calling `subscribe()` manually and returning `Mono.empty()` before writing finishes.
7. Never ignoring cancellation or errors while encoding/writing the body.
8. Preserving essential headers such as `Allow` for 405 or relevant security/caching headers.
9. Recording tracing/metrics without double-logging or swallowing errors.
10. Writing integration tests verifying the exact ordering of exception handlers.

A handler returning `Mono.empty()` after handling and completing the response behaves differently from one returning `Mono.error(original)` to forward the error to the next handler. Never alter propagation mechanics without fully understanding the `WebExceptionHandler` contract.

When a response is already committed, constructing a fresh JSON error may be impossible. Especially with Server-Sent Events or Flux streaming, status has already been sent before a publisher emits a late error.

## 13. Where Do @RestControllerAdvice and @ExceptionHandler Fit?

An **annotated WebFlux controller** application can use `@ExceptionHandler` or `@RestControllerAdvice`:

~~~java
@RestControllerAdvice
public class ApiExceptionAdvice {

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> handle(
            IllegalArgumentException ex) {

        return ResponseEntity.badRequest().body(
                Map.of("code", "BAD_INPUT"));
    }
}
~~~

This snippet is standalone; it requires importing `org.springframework.web.bind.annotation.RestControllerAdvice`, `ExceptionHandler`, `org.springframework.http.ResponseEntity`, and `java.util.Map`.

An exception handled by advice **does not necessarily reach `DefaultErrorWebExceptionHandler`**, because WebFlux has already turned it into a valid response at the handler-result layer. Therefore:

- If the error contract must be unified, clearly assign ownership for each error category.
- Do not expect `ErrorAttributes` to automatically inject `code` into responses built manually by `@ExceptionHandler`.
- Test both advice-handled errors and unhandled errors.
- For functional WebFlux.fn, use `onErrorResume` or `HandlerFilterFunction`; never assume exceptions thrown by functional handlers enter `@RestControllerAdvice` like annotated controllers.
- With Spring Security, authentication/authorization failures have their own response mechanisms; 401/403 errors do not always pass through Boot's error renderer.

In the main demo, no advice is registered so simulated errors flow through the global fallback.

## 14. WebFlux.fn: Local Error Handling

A functional handler accepts `ServerRequest` and returns `Mono<ServerResponse>`. Errors can be mapped inline:

~~~java
public Mono<ServerResponse> find(ServerRequest request) {
    return service.findById(request.pathVariable("id"))
            .flatMap(value ->
                    ServerResponse.ok().bodyValue(value))
            .switchIfEmpty(
                    ServerResponse.notFound().build())
            .onErrorResume(
                    IllegalArgumentException.class,
                    error -> ServerResponse.badRequest().build());
}
~~~

This is a standalone snippet assuming `service` is injected and returns a `Mono` of a suitable object. It is not part of the runnable demo in Section 6. Note:

- `switchIfEmpty` returning 404 is a normal response, not a propagating error. `DefaultErrorWebExceptionHandler` **does not need to run** to produce that response.
- `onErrorResume` turns the error signal into a 400 response; no error remains for global handlers.
- If you want the central global handler to handle an unmapped error, preserve the error signal with `Mono.error` and avoid subscribing manually.
- If an error arrives after response streaming has started, the handler may no longer be able to change status/body.

Standardize error encoding across annotated and functional endpoints, though avoid forcing every error through one global handler if doing so makes the design unnecessarily complex.

## 15. Problem Details per RFC 9457

Before hand-rolling all error JSON, consider Spring Framework's **ProblemDetail** and Spring Boot's support:

~~~properties
spring.webflux.problemdetails.enabled=true
~~~

This option lets Boot auto-configure Problem Details support for built-in WebFlux exceptions per documentation. Standard responses typically use:

~~~http
Content-Type: application/problem+json
~~~

with key fields:

~~~json
{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "A requested resource does not exist",
  "instance": "/api/items/999"
}
~~~

This is an **illustrative contract example**, not a guarantee that Spring Boot's default errors always emit this exact `detail` sentence.

**Important:** enabling the property does not mean every `Throwable` in every layer—including security errors and errors handled by functional handlers—uniformly turns into `ProblemDetail`. Some exceptions pass through `ResponseEntityExceptionHandler`/`ControllerAdvice`, some hit the global fallback, and some are direct responses.

If you adopt Problem Details, commit to it as the API's primary format and **test every error category**. Avoid maintaining two different JSON schemas simultaneously without documentation.

### 15.1. Can ErrorAttributes and ProblemDetail Coexist?

Both mechanisms can exist in an application, though you should not assume their fields merge automatically. Depending on the error source, whichever handler receives the error first determines the response format. To standardize, design a shared error-mapping layer at the appropriate boundaries and avoid duplicating logic.

## 16. Error Properties Usually Worth Checking

In Spring Boot WebFlux 3.5, properties under **`server.error.*`** control which error data is displayed. For example:

~~~yaml
server:
  error:
    include-message: never
    include-stacktrace: never
    include-binding-errors: never
~~~

Some environments support parameter-based inclusion (`on_param`), which must never be enabled in production if arbitrary clients could append a query parameter to extract stack traces or internal info.

Distinctions:

- **server.error.include-message**: whether the exception message is included in error attributes/responses by the active renderer.
- **server.error.include-stacktrace**: whether `trace` is included.
- **server.error.include-binding-errors**: whether binding/validation error details are included.
- **server.error.path**: config related to the default error path; does not turn a global `WebExceptionHandler` into an application REST controller.
- **spring.webflux.problemdetails.enabled**: enables Problem Details support for built-in WebFlux exception handling in Boot.

Never treat these properties as a **global filter protecting every custom error handler**. If your own code calls `response.writeWith` and embeds `exception.getMessage()` in JSON, Boot cannot strip secrets from that string.

## 17. Propagating Accurate HTTP Statuses and Headers

`ErrorAttributes` typically carries `status`. `DefaultErrorWebExceptionHandler` reads `status` to build the response. When customizing the map, **do not delete `status` or replace it with an invalid data type**.

Statuses requiring care:

| HTTP Status | Scenario | Notes |
|---|---|---|
| 400 | Invalid request input | Do not return 500 for clear client errors |
| 401 | Unauthenticated | May be handled by security entry point; preserve `WWW-Authenticate` when needed |
| 403 | Unauthorized or CSRF failure | Security filter may own response |
| 404 | Route/resource does not exist | Distinguish routing 404 from business 404 |
| 405 | Method not allowed | `Allow` header has HTTP meaning and must not be dropped |
| 409 | Business state conflict | API layer/service mapping must be explicit |
| 415 | Unsupported Media Type | From request body `consumes`/codec |
| 422 | Semantic input error per API contract | Do not apply blindly to all validation |
| 500 | Unexpected server error | Must hide internal details |
| 503 | Upstream unavailable / overload per policy | Can include `Retry-After` appropriately |

**Note:** looking at a `Throwable` alone is not enough to determine status system-wide. Spring Framework has `ResponseStatusException`, `ErrorResponse`, and dedicated exception handling; Spring Security/Gateways also have their own mechanisms. Custom global handlers must respect HTTP semantics and preserve required headers.

## 18. Observability, Logging, and Correlation IDs

A server error usually requires two views:

**Client-facing:** status, stable error code, safe message, and a request ID/correlation ID useful when reporting incidents.

**Server-side:** exception type, stack trace, tracing span, request ID, upstream latency, and system context complying with logging policy.

Never put server-side error data into public JSON. For instance, instead of `"Database socket timeout to internal-host:5432"`, return `"Unexpected server error"` and record the details in secure logs/traces.

### 18.1. requestId vs. Business Correlation ID

WebFlux `DefaultErrorAttributes` may include a `requestId` tied to the HTTP exchange. Multi-service systems may also use a distributed tracing `traceId` or a gateway-controlled correlation ID. These are not necessarily identical.

If adding a request identifier to error responses:

- Identify where the ID is generated and verified.
- Avoid blindly trusting arbitrary client-sent headers.
- Avoid logging payloads, `Authorization` headers, cookies, and PII.
- Verify that the ID in JSON matches what support/logs can actually look up.
- With Reactor Context, do not rely unconditionally on `ThreadLocal` across scheduler boundaries.

### 18.2. Handled Errors May Not Show Up in Metrics as Expected

When a controller/advice catches an exception and returns a 4xx/5xx response, framework observation may not automatically capture the original exception in all cases. Depending on observability tools and Spring version, record handled exceptions on the observation context or emit explicit metrics.

Never use “count of `ErrorWebExceptionHandler` invocations” as the total error count for the system. It misses every error handled locally.

## 19. Reactive Safety and Streaming Responses

In WebFlux, `Mono` and `Flux` represent asynchronous work subscribed and cancelled along the request lifecycle. A global error handler can only respond while the error signal stays in the chain and the response remains writable.

### 19.1. Do Not Use block() in Error Handlers

Wrong:

~~~java
String detail = webClient.get()
        .uri("/diagnostics")
        .retrieve()
        .bodyToMono(String.class)
        .block();
~~~

This is an illustrative anti-pattern. It can block the event loop and even trigger cascading errors inside the global error handler.

An error handler should do minimal work, preferring data already on `ServerWebExchange` or the exception object. If I/O is unavoidable to enrich an error response, design strict timeouts, fallbacks, and reactive composition carefully; normally, never make network calls from a global error renderer.

### 19.2. Do Not Manually Call subscribe() and Complete the Request

Wrong:

~~~java
Mono<Void> writing = response.writeWith(bodyPublisher);
writing.subscribe();
return Mono.empty();
~~~

This code detaches the write work from the publisher returned to the framework. It can finish the response prematurely, lose backpressure/cancellation, and drop write errors.

Instead, when implementing `WebExceptionHandler`, **return the response-writing publisher directly**:

~~~java
return response.writeWith(bodyPublisher);
~~~

These snippets illustrate reactive semantics, not a complete `ErrorWebExceptionHandler` class.

### 19.3. When the Response Is Already Committed

Suppose a `text/event-stream` endpoint has already emitted several events before `Flux.error` occurs. You cannot guarantee converting the response into HTTP 500 JSON because the client has already received HTTP 200 and part of the body.

Appropriate strategies include:

- Terminating the stream and letting the client retry per contract.
- Emitting a schema-defined error event if the protocol supports it.
- Logging/tracing the error and releasing resources.
- Placing timeout/retry policies at the right layer.
- Testing disconnects and cancellation.

A global error renderer does not replace protocol-level error handling for streams.

## 20. Testing Cases That Are Commonly Missed

Beyond the four tests in Section 7, extend coverage to:

1. **`Accept: application/json`** receiving the JSON error schema.
2. **`Accept: text/html`** receiving an error page if default HTML rendering is kept.
3. 400 errors from `ResponseStatusException`.
4. 404 errors from unmatched routes.
5. Business errors mapped directly to a `ResponseEntity` 404; verify global `ErrorAttributes` is not falsely expected to apply.
6. 500 errors hiding internal messages and stack traces.
7. Spring Security 401/403 with realistic rules.
8. `@Valid` validation errors in annotated controllers.
9. WebFlux.fn errors handled via `onErrorResume` and unhandled errors.
10. Requests from a gateway/proxy carrying forwarded prefixes and request IDs.
11. Wrong request body media type, malformed JSON, and unsupported method ensuring statuses do not turn into 500.
12. Streaming publishers emitting errors after the response is committed.
13. Custom handlers with verified ordering, message readers/writers, and error attributes.
14. Responses where error paths contain odd characters or PII are governed by policy.

`WebTestClient` fits WebFlux well. When testing global handlers and auto-configuration, prefer `@SpringBootTest` `RANDOM_PORT` or full-context app tests; an isolated `bindToController` test may not activate Boot's global error handler.

Do not assert internal exception class names or JSON key order unless genuinely part of your public contract.

## 21. Common Mistakes and How to Investigate

| Symptom | Common Cause | Fix |
|---|---|---|
| Custom `ErrorAttributes` not called | Bean not scanned, error already handled by `@ExceptionHandler`, or app runs MVC | Check context, MVC/WebFlux stack, and error location |
| Compilation error on method signature after importing `ErrorAttributes` | Imported Servlet package instead of Reactive | Use `org.springframework.boot.web.reactive.error.ErrorAttributes` |
| Browser shows HTML while test expects JSON | Browser `Accept` contains `text/html` | Test with `Accept: application/json` or customize renderer per contract |
| JSON error includes internal message/trace | `server.error.*` open or custom handler outputs exception text | Disable includes, sanitize attributes, test sensitive strings |
| All errors become 500 | Custom handler hardcodes status | Preserve status mapping and check `ResponseStatusException` |
| `@RestControllerAdvice`-handled error lacks `ErrorAttributes` custom code | Advice built response before global fallback | Standardize error contract in advice or share a mapping helper |
| Custom `DefaultErrorWebExceptionHandler` does not run | Bean not registered or Boot uses another handler | Register `ErrorWebExceptionHandler` bean; check order and auto-configuration |
| JSON serialization fails after registering custom handler | Missing message writers/readers or codec | Configure `ServerCodecConfigurer` as in Section 10 |
| Error handler fails initialization | Missing resources/context or uninitialized infrastructure | Use version-matching constructor and verify bean dependencies |
| Empty response body after mid-stream error | Response already committed | Design a stream error contract; do not attempt fresh JSON |
| Service returns `Mono.empty` when client expects 404 | `Mono.empty` does not automatically mean 404 | Explicitly map empty to an appropriate status/exception |
| Reactive pipeline exception vanishes | Code manually subscribed or swallowed with `onErrorComplete` | Return publisher to framework; handle errors intentionally |
| Health check returns HTML 404 after changing base path | URL mismatch through proxy or server stack | Align external paths and internal mappings |
| `ProblemDetail` and error map output two formats | Some errors go via advice, others via Boot fallback | Standardize schemas and test every error source |
| 405 loses `Allow` header after customization | Handler creates fresh response and drops original headers | Preserve HTTP semantics or let the framework handle it |
| Errors missing from metrics despite client seeing 500 | Error handled before observation captures exception | Adjust observation/tracing for handled errors |

## 22. Practical Investigation Procedure

When a WebFlux system returns unexpected errors:

1. Record the **actual request**: method, URL after proxy, `Accept`, `Content-Type`, request ID, status, and response headers.
2. Verify whether **Spring WebFlux reactive** or Spring MVC with `WebClient` is running; never guess packages from dependency names alone.
3. Identify whether the exception originated in an annotated controller, functional handler, filter/security, router, or codec.
4. Check whether `@ExceptionHandler`, `@RestControllerAdvice`, `onErrorResume`, or security already converted the error into a response.
5. If the error still enters the global chain, verify which `ErrorWebExceptionHandler` bean ran and its order.
6. Inspect the map returned by `ErrorAttributes#getErrorAttributes`, checking status validity and data safety.
7. Check whether `DefaultErrorWebExceptionHandler` chose JSON or HTML and which codec wrote the response.
8. Test without custom handlers in an isolated test environment to compare with Boot defaults; never experiment on production unchecked.
9. Check for already-committed responses or streaming behavior.
10. Confirm Problem Details/security/gateway behavior if enabled.
11. Write an integration regression test covering status, headers, error code, safe message, and no stack-trace leaks.
12. After fixing, monitor error rates, latency, and traces instead of relying on a single curl output.

Start from HTTP evidence, not by guessing from a single log line. Never alter global status mapping for all exceptions just to fix one endpoint.

## 23. Pre-Merge Checklist

- [ ] Confirmed application runs Spring WebFlux and did not import Servlet `ErrorAttributes` by mistake.
- [ ] Understood the roles of `ErrorWebExceptionHandler`, `DefaultErrorWebExceptionHandler`, and `ErrorAttributes`.
- [ ] Used `ErrorAttributes` when only modifying error response data.
- [ ] Avoided deleting `status` or placing unserializable objects in the error map.
- [ ] Prevented exposing exception messages, traces, validation `rejectedValue`, or secrets in public responses.
- [ ] Defined clear JSON schemas, HTTP statuses, business codes, and headers to preserve.
- [ ] Added tests for 400/404/500 as well as success paths.
- [ ] Distinguished errors handled by advice/`onErrorResume` from errors reaching the global fallback.
- [ ] If replacing Boot's default with a custom handler: configured bean registration, order, readers, writers, and view resolvers.
- [ ] Tested JSON/HTML responses according to real `Accept` headers.
- [ ] Defined a ProblemDetail strategy if `spring.webflux.problemdetails.enabled` is enabled.
- [ ] Avoided `block()` or `subscribe()` inside reactive error handling.
- [ ] Avoided modifying status/body after response commit.
- [ ] Tested through gateway, Spring Security, and Actuator if used.
- [ ] Ensured tracing/logging keeps sensitive data safe and supports correlation IDs.
- [ ] Verified APIs against the target Spring Boot version when upgrading major releases.

## 24. Conclusion

**`ErrorAttributes` supplies error data; `DefaultErrorWebExceptionHandler` builds JSON/HTML responses; `ErrorWebExceptionHandler` is the extension contract for replacing global WebFlux error rendering.**

In most Spring Boot apps, **keep the default handler and add an `ErrorAttributes` bean** when you only need error codes, safe messages, or metadata. Use `@RestControllerAdvice` or WebFlux.fn handling for errors belonging clearly to an API or route. Only extend `DefaultErrorWebExceptionHandler`, `AbstractErrorWebExceptionHandler`, or implement `ErrorWebExceptionHandler` directly when global rendering, status selection, or formatting must change and is thoroughly tested.

Preserve HTTP semantics, never leak exception internals, never block the event loop, and never confuse handled errors with errors awaiting the global fallback. Those are the core principles for building a reliable error contract on the reactive stack.

## Official References

- [Spring Boot 3.5 — Reactive Web Applications: Error Handling](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html)
- [Spring Boot 3.5.16 — DefaultErrorWebExceptionHandler API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/reactive/error/DefaultErrorWebExceptionHandler.html)
- [Spring Boot 3.5.16 — AbstractErrorWebExceptionHandler API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/reactive/error/AbstractErrorWebExceptionHandler.html)
- [Spring Boot 3.5.16 — Reactive DefaultErrorAttributes API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/reactive/error/DefaultErrorAttributes.html)
- [Spring Boot 3.5.16 — Reactive ErrorAttributes API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/reactive/error/ErrorAttributes.html)
- [Spring Boot 3.5.16 — ErrorWebFluxAutoConfiguration API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/reactive/error/ErrorWebFluxAutoConfiguration.html)
- [Spring Framework 6.2 — WebFlux Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/ann-rest-exceptions.html)