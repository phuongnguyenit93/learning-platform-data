# HTML Error Pages, Whitelabel, and Default JSON Responses in Spring Boot

## Objectives and Scope

This lesson belongs to the **Error Handling** group of the **Spring Boot - web-runtime** module. After completing it, you will be able to:

1. Distinguish HTTP status, HTML error pages, JSON error responses, and RFC 9457 Problem Details.
2. Explain the default **Spring MVC** mechanism: Servlet error dispatch, the `/error` path, BasicErrorController, ErrorAttributes, ErrorViewResolver, and Whitelabel Error Page.
3. Explain the **Spring WebFlux** mechanism: DefaultErrorWebExceptionHandler instead of Servlet BasicErrorController.
4. Verify why the same 404 or 500 status can return text/html or application/json depending on the request Accept header.
5. Use the server.error.* properties of **Spring Boot 3.3.x** without accidentally exposing exception messages, validation data, or stack traces.
6. Replace the Whitelabel page with custom HTML for 404, 4xx, and 5xx while keeping JSON error handling for APIs.
7. Understand when @ExceptionHandler, @RestControllerAdvice, ResponseStatusException, Spring Security, or a reverse proxy returns a response different from the default fallback.
8. Build a **Java 17+ / Spring Boot 3.3.x** example, test with curl, and run integration tests over real HTTP.
9. Recognize limitations around HTTP streaming, committed responses, proxy caching, CORS, and logging.

**Versions:** Spring Boot 3.3.x, Spring Framework 6.1.x, and Java 17+. Do not use packages or properties from Boot 4.x to replace the code in this lesson.

## 1. What Happens When an HTTP Request Fails?

An HTTP response has at least two critical pieces of information: the **status** at the HTTP layer and the **body representation** described by Content-Type.

An API client sends:

~~~http
GET /duong-dan-khong-co HTTP/1.1
Host: localhost:8080
Accept: application/json
~~~

In a default Spring Boot MVC application, the response is usually equivalent to:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/json

{"timestamp":"2026-01-01T00:00:00.000+00:00","status":404,"error":"Not Found","path":"/duong-dan-khong-co"}
~~~

**Note:** The timestamp and JSON formatting are only illustrative examples, not fixed output. Fields may differ due to configuration, Spring Boot version, or custom ErrorAttributes. In Boot 3.3, common fields are timestamp/status/error/path; message and trace are typically hidden by default.

A browser requesting HTML:

~~~http
GET /duong-dan-khong-co HTTP/1.1
Host: localhost:8080
Accept: text/html
~~~

may receive:

~~~http
HTTP/1.1 404 Not Found
Content-Type: text/html

<!doctype html>
<html><head><title>Whitelabel Error Page</title></head>
<body><h1>Whitelabel Error Page</h1></body></html>
~~~

The HTML shown here is only a **simplified sketch**, not Spring Boot's exact markup. The invariant in this case is that **the status is still 404**, even though the body is HTML instead of JSON.

| Property | Example | Question It Answers |
|---|---|---|
| HTTP status | 404, 500 | Did the request succeed or fail? |
| Response Content-Type | text/html, application/json | What format is the body in? |
| Response body | HTML page, JSON map, ProblemDetail | What error information does the client see? |

An HTTP 404 can have an HTML body, JSON, plain text, or even no body at all; you cannot infer the response structure from the status alone.

## 2. What Is the Whitelabel Error Page?

The **Whitelabel Error Page** is a generic HTML error page provided by Spring Boot as a **fallback** when a request asks for HTML and no application-defined error view matches.

It is not:
- A Java exception type.
- An HTTP status code.
- A controller that you are required to write yourself.
- Definitive proof that the server failed to start.

It usually indicates that **the application received the request and is responding with an error**, but does not yet have a branded or custom user-facing error page.

The Whitelabel page can appear for 404, 400, 500, or other statuses depending on the cause. It may not appear if the app has a custom error view, a custom @ExceptionHandler, Spring Security generating its own response, or a proxy replacing the body.

### Meaning of “no explicit mapping for /error”

In some versions, the Whitelabel page contains the text:

~~~text
This application has no explicit mapping for /error,
so you are seeing this as a fallback.
~~~

This is **not** an instruction that every project must add a `@GetMapping("/error")`. Spring Boot already auto-configures error processing; the line simply states that the application has not provided a dedicated HTML error view to replace the fallback.

Arbitrarily creating an `/error` controller can alter routing, HTTP status, content negotiation, and the JSON error contract. Most projects only need to add HTML error files to the right directory or use an advice when a different API error schema is needed.

## 3. Spring MVC: Servlet Error Dispatch and BasicErrorController

In Servlet-based Spring MVC, Spring Boot registers **/error** by default as the global error page for the embedded Servlet container.

~~~text
HTTP client
     |
     v
Embedded Tomcat / Jetty / Undertow
     |
     v
Servlet Filters / Spring Security (if present)
     |
     v
DispatcherServlet / Controller
     |
     +----> Success ------------------------> Response
     |
     +----> Error or exception
                  |
                  +--> HandlerExceptionResolver / @ExceptionHandler
                  |         |
                  |         +--> Can handle and return response directly
                  |
                  +--> When Servlet ERROR dispatch is needed
                             |
                             v
                          /error
                             |
                             v
                     BasicErrorController
                             |
                    +--------+----------+
                    |                   |
                HTML view           JSON/fallback
                    |                   |
            ErrorViewResolver     ErrorAttributes
                    |                   |
            Whitelabel/custom     JSON response
~~~

The diagram reflects a **typical processing path**; not every 4xx/5xx must pass through /error.

Components:

| Component | Responsibility |
|---|---|
| ErrorMvcAutoConfiguration | Auto-configuration for error handling in Spring MVC |
| BasicErrorController | Fallback controller for /error |
| ErrorAttributes | Contract supplying error information |
| DefaultErrorAttributes | Default implementation recording basic details |
| ErrorViewResolver | Resolves an appropriate view or HTML page |
| Whitelabel view | HTML fallback when no custom view exists |
| HandlerExceptionResolver | Resolves exceptions inside MVC |
| Servlet error page | Triggers ERROR dispatch to the error path when needed |

Package of BasicErrorController in Spring Boot 3.3:

~~~java
org.springframework.boot.autoconfigure.web.servlet.error.BasicErrorController
~~~

Two prominent branches:

~~~java
@RequestMapping(produces = "text/html")
ModelAndView errorHtml(HttpServletRequest request,
                       HttpServletResponse response);

@RequestMapping
ResponseEntity<Map<String, Object>> error(HttpServletRequest request);
~~~

These are API signatures for reading comprehension, **not a standalone Java file**. The `errorHtml` branch returns a view for HTML, while the `error` branch returns a Map of details for a converter to write the response, typically as JSON.

## 4. Why Shouldn't You Call GET /error Directly for Testing?

In MVC, an error dispatch carries internal Servlet request attributes, such as the original status and the request URI that caused the error. That differs from a client sending `GET /error` as an ordinary URL.

~~~text
Client -> GET /khong-ton-tai
  -> MVC/Servlet determines 404
  -> internal ERROR dispatch to /error
  -> BasicErrorController reads status and original path
Client <- HTTP 404, JSON/HTML matching Accept
~~~

When a client calls `GET /error` directly, the request does not necessarily have Servlet ERROR dispatch metadata, so the status and body do not match a real error.

Default configuration property:

~~~properties
server.error.path=/error
~~~

It can be changed:

~~~yaml
server:
  error:
    path: /failure
~~~

but only do so with a clear purpose after testing the Servlet container, Security, reverse proxy, and monitoring. Changing the error path does not add authentication or reduce data exposure.

To test, call **an unmapped path** or an endpoint that intentionally throws an exception in a lab environment.

## 5. Accept and Content-Type Decide Different Things

- **Request Content-Type** describes the body sent by the client, e.g., POST application/json.
- **Request Accept** describes the response media types the client wants to receive.
- **Response Content-Type** describes the body the server actually returns.

Example of a POST sending JSON but requesting HTML:

~~~http
POST /api/items HTTP/1.1
Content-Type: application/json
Accept: text/html

{"name":"pen"}
~~~

If the request fails and the fallback handler picks HTML, the error response can be `text/html`. There is no rule stating a JSON request must receive a JSON error.

To test clearly:

~~~bash
curl -i -H 'Accept: application/json' http://localhost:8080/khong-ton-tai
curl -i -H 'Accept: text/html' http://localhost:8080/khong-ton-tai
~~~

When a client sends `Accept: */*` or omits `Accept`, multiple representations may match. Do not lock a test to one body type if the request does not specify a clear response preference.

**Do not confuse CORS errors with HTML/JSON error bodies.** Browser JavaScript may be blocked by CORS policy from reading a response where the server actually sent status 404/500.

## 6. What Does the Default JSON Error Body Contain?

A typical error representation:

~~~json
{
  "timestamp": "2026-01-01T00:00:00.000+00:00",
  "status": 404,
  "error": "Not Found",
  "path": "/khong-ton-tai"
}
~~~

Fields:

| Field | Meaning | Typical Boot 3.3 Behavior |
|---|---|---|
| timestamp | Time when error was recorded | Usually present |
| status | Numeric HTTP status | Usually present |
| error | Reason phrase | Usually present |
| path | Path causing the error | include-path=always |
| message | Exception message | include-message=never |
| errors | Binding/validation details | include-binding-errors=never |
| trace | Stack trace | include-stacktrace=never |
| exception | Exception class name | include-exception=false |

**Do not expose message or stack trace in public JSON by default.** You may see older online examples displaying message/trace, but those may be from older Boot versions or configurations that enabled detailed fields.

Default JSON is a framework fallback, **not a versioned API contract**. If clients need machine-readable error codes, support IDs, field errors, and linked documentation, define responses according to an application contract.

## 7. Spring Boot 3.3 server.error.* Properties

| Property | Boot 3.3 Default | Meaning |
|---|---|---|
| server.error.path | /error | Error controller path in MVC |
| server.error.whitelabel.enabled | true | Enables Whitelabel HTML fallback |
| server.error.include-message | never | Condition for exposing message |
| server.error.include-stacktrace | never | Condition for exposing trace |
| server.error.include-binding-errors | never | Condition for exposing binding/validation errors |
| server.error.include-exception | false | Whether to include exception class name |
| server.error.include-path | always | Condition for including request path in error attributes |

The “when to include” properties accept `never`, `always`, or `on_param` where supported; for public APIs, restrict information by default.

Conservative YAML example:

~~~yaml
server:
  error:
    whitelabel:
      enabled: true
    include-message: never
    include-stacktrace: never
    include-binding-errors: never
    include-exception: false
    include-path: always
~~~

These values are close to Boot 3.3 defaults. When serving an HTML frontend, add custom error views instead of Whitelabel for a better user experience.

### Enabling message for Local Debugging

~~~properties
server.error.include-message=always
~~~

This can make the error map include `message` when the error handler uses that property. There is no guarantee every exception has a message or every error goes to `/error`. In production, messages can contain class names, SQL, paths, file names, hosts, or user data.

### Risks of include-stacktrace=always or on_param

Stack traces can reveal code structure, dependencies, versions, exception messages, file paths, and sensitive details. Never let callers trigger traces on public endpoints. Write stack traces to **internal server logs** with redaction and correlate via request ID.

### Does Disabling Whitelabel Disable Default JSON?

~~~yaml
server:
  error:
    whitelabel:
      enabled: false
~~~

This property mainly **disables the Whitelabel HTML view**. In MVC, `BasicErrorController` JSON handling can continue to work. Without a custom HTML view, the Servlet container or another fallback may display an error page depending on the environment. **Do not treat disabling Whitelabel as a way to create a nice 404 page.**

## 8. Not Every HTTP 4xx/5xx Goes Through /error

Example of a controller returning a status directly:

~~~java
@GetMapping("/api/items/example")
ResponseEntity<String> demo() {
    return ResponseEntity.status(404).body("not found");
}
~~~

This is a snippet in a REST controller. The controller built the response directly; Servlet error dispatch or BasicErrorController does not necessarily participate.

The framework has exception resolvers for request mapping, body parsing, and validation. Spring Security can intercept and return 401/403 or redirect. Proxies can return 502/503/504 when upstream is unreachable.

### ResponseStatusException

~~~java
@GetMapping("/api/items/{id}")
Object item(@PathVariable long id) {
    throw new ResponseStatusException(
            HttpStatus.NOT_FOUND, "Item is unavailable");
}
~~~

This is an illustrative controller snippet. Spring handles the status of `ResponseStatusException`; there is **no guarantee** the `message` field is returned in default JSON when `include-message=never`.

### Recognizing Common HTTP Statuses

| Status | Common Causes |
|---|---|
| 400 | Invalid request parameters/body, malformed JSON |
| 401 | Authentication missing/invalid, security handler |
| 403 | Insufficient permissions, security handler |
| 404 | No handler/resource or object does not exist |
| 405 | HTTP method not allowed |
| 406 | Accept incompatible with response representation |
| 415 | Request body Content-Type unsupported |
| 500 | Unhandled server exception |
| 502/503/504 | Gateway/proxy or dependency availability |

Do not infer from 404 that it was caused by controller mapping; an API may intentionally return 404. Likewise, do not infer from 500 that users saw the Whitelabel page: API clients normally request JSON.

## 9. Customizing HTML Error Pages Without Writing an /error Controller

Spring Boot supports error pages by **exact status** and **status series**.

### Static 404 Page

Create file:

~~~text
src/main/resources/public/error/404.html
~~~

Example content:

~~~html
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Not Found</title>
</head>
<body>
  <main>
    <h1>404 — Page Not Found</h1>
    <p>The path does not exist or has changed.</p>
    <a href="/">Back to home</a>
  </main>
</body>
</html>
~~~

When a 404 needs HTML rendering, Boot can pick this file instead of Whitelabel. If a client sends `Accept: application/json`, the default JSON branch can still work normally.

### Error Series

~~~text
src/main/resources/public/error/404.html
src/main/resources/public/error/4xx.html
src/main/resources/public/error/5xx.html
~~~

An exact-status page like `404` takes precedence over `4xx`; a `500` error without its own page can use `5xx`.

### HTML Templates

With Thymeleaf or another Boot auto-configured template engine, you can place:

~~~text
src/main/resources/templates/error/404.html
src/main/resources/templates/error/5xx.html
src/main/resources/templates/error.html
~~~

In **Spring MVC**, the default error view name is **error**. Dynamic templates can display edited status or informational messages, but must not expose raw stack traces, SQL, or internal exception messages to users.

If a template/static resource is not picked up, check JAR resources, folder paths, template engine dependencies, view resolver priority, caching, custom advice, and `ErrorViewResolver` beans.

## 10. Whitelabel Disabled vs. Custom HTML

Three options:

| Option | Goal | Consequence |
|---|---|---|
| Default Whitelabel | Prototyping and local testing | Minimal HTML fallback |
| public/error/404.html | Branded 404 experience | Only replaces HTML for matching status |
| server.error.whitelabel.enabled=false | Disable Whitelabel | Does not create a new HTML page automatically |

An application serving both an HTML frontend and a REST API may need **two separate contracts**:
- User-friendly 404/5xx HTML pages without internal leaks.
- JSON errors with stable statuses and codes for API clients.

Do not force API clients to parse HTML for errors; also do not force browsers to display raw JSON if the app primarily serves end users.

## 11. Runnable Spring MVC Example: Default HTML and JSON

Create a **Spring Boot 3.3.x / Java 17+** project with `starter-web`. Do not add custom error pages or `@RestControllerAdvice` on the first run so you can observe the raw fallback.

In a Boot project `build.gradle` with plugins/repositories already declared:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

This is only the dependencies block, not the entire `build.gradle`.

### Complete Java Code

Create **src/main/java/com/example/errors/ErrorViewsApplication.java**:

~~~java
package com.example.errors;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class ErrorViewsApplication {

    public static void main(String[] args) {
        SpringApplication.run(ErrorViewsApplication.class, args);
    }

    @RestController
    static class ExampleController {

        @GetMapping("/api/ok")
        Map<String, String> ok() {
            return Map.of("result", "ok");
        }

        @GetMapping("/api/items/{id}")
        Map<String, Object> find(@PathVariable long id) {
            if (id != 7) {
                throw new ResponseStatusException(
                        HttpStatus.NOT_FOUND,
                        "Item is unavailable");
            }
            return Map.of("id", id, "name", "pen");
        }

        @GetMapping("/api/crash")
        String crash() {
            throw new IllegalStateException(
                    "Internal diagnostic details: do not expose");
        }
    }
}
~~~

This is a **complete Java file inside a Spring Boot project**; it will not compile with plain `javac` without Spring/Jackson on the classpath.

Endpoint purposes:
- `/api/ok`: works normally, JSON 200.
- `/api/items/{id}`: demo data; any id other than 7 triggers 404.
- `/api/crash`: intentionally throws an exception to observe the 500 fallback, **for local lab/testing only**.
- `/khong-ton-tai`: clients will test a URL with no handler.

### Configuration

Create **src/main/resources/application.yml**:

~~~yaml
server:
  port: 8080
  error:
    whitelabel:
      enabled: true
    include-message: never
    include-stacktrace: never
    include-binding-errors: never
    include-exception: false
~~~

### Run

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

If port 8080 is busy, change `server.port` and update the URL in all test commands.

## 12. Using curl to Demonstrate Content Negotiation

Successful endpoint:

~~~bash
curl -i -H 'Accept: application/json' \
  http://localhost:8080/api/ok
~~~

An equivalent JSON body:

~~~json
{"result":"ok"}
~~~

Non-existent URL error requesting JSON:

~~~bash
curl -i -H 'Accept: application/json' \
  http://localhost:8080/khong-ton-tai
~~~

Expected HTTP 404, Content-Type `application/json`, field `status=404`. Do not try to predict the exact timestamp.

Same URL requesting HTML:

~~~bash
curl -i -H 'Accept: text/html' \
  http://localhost:8080/khong-ton-tai
~~~

Expected 404 `text/html`. Without a custom error view, the body is typically the Whitelabel HTML.

Unhandled server error:

~~~bash
curl -i -H 'Accept: application/json' \
  http://localhost:8080/api/crash

curl -i -H 'Accept: text/html' \
  http://localhost:8080/api/crash
~~~

Expected 500 for both requests. With `include-message=never`, the JSON fallback should not contain the exception's “Internal diagnostic details” string. Internal logs may contain the stack trace for debugging.

### After Observing Defaults, Add HTML 404

Add `public/error/404.html` from Section 9, then restart/repackage if needed. Requests with `Accept: text/html` can now receive the custom page, while `Accept: application/json` still receives the fallback JSON error. This is a key test proving that **HTML customization does not automatically alter the JSON contract**.

### PowerShell

On Windows PowerShell use `curl.exe` to avoid the alias:

~~~powershell
curl.exe -i -H "Accept: application/json" "http://localhost:8080/khong-ton-tai"
curl.exe -i -H "Accept: text/html" "http://localhost:8080/khong-ton-tai"
curl.exe -i -H "Accept: application/json" "http://localhost:8080/api/crash"
~~~

## 13. Testing /error Over Real HTTP, Not Just MockMvc

MockMvc runs Spring MVC infrastructure **without opening an embedded Servlet container**; it does not fully reproduce Servlet error-page dispatch. An unhandled exception in MockMvc can bubble out in the test instead of forwarding to `/error` as when running real Tomcat.

For this fallback, use **@SpringBootTest(webEnvironment=RANDOM_PORT)** + an HTTP client. Example using `TestRestTemplate` provided by `starter-test`.

Create **src/test/java/com/example/errors/ErrorViewsIntegrationTests.java**:

~~~java
package com.example.errors;

import java.util.List;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class ErrorViewsIntegrationTests {

    @Autowired
    TestRestTemplate http;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void missingUrlReturns404JsonWithoutTrace() throws Exception {
        HttpHeaders headers = new HttpHeaders();
        headers.setAccept(List.of(MediaType.APPLICATION_JSON));

        ResponseEntity<String> response = http.exchange(
                "/khong-ton-tai",
                HttpMethod.GET,
                new HttpEntity<>(headers),
                String.class
        );

        assertEquals(404, response.getStatusCode().value());
        assertNotNull(response.getHeaders().getContentType());
        assertTrue(response.getHeaders().getContentType()
                .isCompatibleWith(MediaType.APPLICATION_JSON));

        JsonNode error = objectMapper.readTree(response.getBody());
        assertEquals(404, error.path("status").asInt());
        assertEquals("/khong-ton-tai", error.path("path").asText());
        assertFalse(error.has("trace"));
        assertFalse(error.has("exception"));
    }

    @Test
    void missingUrlReturnsHtmlWith404Status() {
        HttpHeaders headers = new HttpHeaders();
        headers.setAccept(List.of(MediaType.TEXT_HTML));

        ResponseEntity<String> response = http.exchange(
                "/khong-ton-tai",
                HttpMethod.GET,
                new HttpEntity<>(headers),
                String.class
        );

        assertEquals(404, response.getStatusCode().value());
        assertNotNull(response.getHeaders().getContentType());
        assertTrue(response.getHeaders().getContentType()
                .isCompatibleWith(MediaType.TEXT_HTML));
        assertNotNull(response.getBody());
    }

    @Test
    void unhandledExceptionReturns500Json() throws Exception {
        HttpHeaders headers = new HttpHeaders();
        headers.setAccept(List.of(MediaType.APPLICATION_JSON));

        ResponseEntity<String> response = http.exchange(
                "/api/crash",
                HttpMethod.GET,
                new HttpEntity<>(headers),
                String.class
        );

        assertEquals(500, response.getStatusCode().value());
        JsonNode error = objectMapper.readTree(response.getBody());
        assertEquals(500, error.path("status").asInt());
        assertFalse(error.has("trace"));
        assertFalse(error.has("message"));
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

This lesson avoids locking timestamps or literal Whitelabel markup. The HTML test checks only status/media type so HTML can be customized while tests remain valid. The 500 test assumes the project has no dedicated advice catching `IllegalStateException`.

## 14. When to Use @RestControllerAdvice Instead of Default JSON

Boot's fallback JSON map may suffice for prototypes, but public APIs typically need a dedicated error contract: business error codes, safe messages, correlation IDs, validated field errors, and API docs.

Define a business exception in **ProductUnavailableException.java**:

~~~java
package com.example.errors;

public class ProductUnavailableException extends RuntimeException {
    public ProductUnavailableException(long id) {
        super("Product unavailable: " + id);
    }
}
~~~

Add advice **ProductErrorAdvice.java**:

~~~java
package com.example.errors;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ProductErrorAdvice {

    @ExceptionHandler(ProductUnavailableException.class)
    public ResponseEntity<ProblemDetail> handle(
            ProductUnavailableException ex) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND,
                "The requested product is unavailable");
        problem.setTitle("Product not found");
        problem.setProperty("code", "PRODUCT_NOT_FOUND");

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(problem);
    }
}
~~~

These are **optional supplementary Java files**, not replacements for the main class. The advice only handles `ProductUnavailableException`; other exceptions, such as `IllegalStateException` from the demo endpoint, can still pass through the default fallback.

A response may look like:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{"type":"about:blank","title":"Product not found","status":404,"detail":"The requested product is unavailable","code":"PRODUCT_NOT_FOUND"}
~~~

This is **Problem Details** (RFC 9457), distinct from the default JSON map schema. Never return raw exception messages if they contain sensitive data.

### Advice Can Affect the HTML Frontend

`@RestControllerAdvice` returns a response body for matching exceptions. A browser requesting HTML may still receive JSON if the advice is not scoped. In apps serving both MVC views and REST APIs, scope advice to specific controller groups to avoid accidentally turning HTML frontend errors into JSON.

## 15. ProblemDetail and Default JSON Map Are Not Identical

Spring Framework 6 supports ProblemDetail/ErrorResponse, and Spring Boot 3.3 has the property:

~~~yaml
spring:
  mvc:
    problemdetails:
      enabled: true
~~~

A typical Problem Details response:

~~~json
{
  "type": "https://example.org/problems/missing-product",
  "title": "Not Found",
  "status": 404,
  "detail": "Product was not found",
  "instance": "/api/items/7"
}
~~~

These values merely illustrate a contract you can design. Enabling Problem Details adds support for certain MVC framework errors, **without guaranteeing every unhandled exception or every Servlet error dispatch becomes the exact same ProblemDetail**.

Comparison:

| Response Type | Body and Content-Type |
|---|---|
| BasicErrorController JSON | timestamp/status/error/path..., application/json |
| Whitelabel or custom HTML | HTML, text/html |
| @RestControllerAdvice returning DTO | JSON per your contract |
| ProblemDetail | type/title/status/detail/instance, application/problem+json |
| Spring Security error | Determined by entry point/denied handler |

Do not simply switch `Accept` to `application/problem+json` and assume the server provides `ProblemDetail` across every endpoint.

## 16. WebFlux: Does Not Use Servlet BasicErrorController

Spring WebFlux on Reactor Netty has its own global error-handling infrastructure. In Spring Boot 3.3, the primary handler is:

~~~java
org.springframework.boot.autoconfigure.web.reactive.error.DefaultErrorWebExceptionHandler
~~~

It is a **WebExceptionHandler** capable of rendering HTML error views for clients accepting HTML or JSON error payloads for API clients.

~~~text
HTTP request
     |
     v
Reactive server / WebFilter / DispatcherHandler
     |
     +----> Controller succeeds -> response
     |
     +----> Unhandled reactive error
                       |
                       v
             DefaultErrorWebExceptionHandler
                       |
                 +-----+------+
                 |            |
           HTML error view   JSON error data
                 |            |
              text/html   application/json
~~~

Differences:

| Topic | MVC | WebFlux |
|---|---|---|
| Runtime | Servlet/Tomcat | Reactive/Reactor Netty |
| Global fallback | BasicErrorController | DefaultErrorWebExceptionHandler |
| Error metadata | Servlet ErrorAttributes | Reactive ErrorAttributes |
| HTML view | ErrorViewResolver/Whitelabel | Reactive error view/Whitelabel |
| JSON writing | HttpMessageConverter | HttpMessageWriter/codec |
| Servlet ERROR dispatch | Yes when needed | Different mechanism |
| ProblemDetail property | spring.mvc.problemdetails.enabled | spring.webflux.problemdetails.enabled |

In WebFlux, do not describe every error as a Servlet forward to `/error`. The reactive error handler has its own pipeline.

### Error HTML Views in WebFlux

Boot 3.3 can resolve:

~~~text
src/main/resources/public/error/404.html
src/main/resources/public/error/5xx.html
src/main/resources/templates/error/404.html
src/main/resources/templates/error/5xx.html
~~~

**Important difference:** the default error view name in WebFlux is **error/error**, whereas in Spring MVC it is **error**. For exact-status files like `public/error/404.html`, both stacks can use similar paths.

## 17. Runnable WebFlux Project to Test Errors

Create a **separate project** using only `starter-webflux`, Java 17+:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Do not add `starter-web` to this project if you want Boot to choose the reactive server by default, because when both starters are present Boot 3.3 normally prefers MVC.

Create **src/main/java/com/example/reactiveerrors/ReactiveErrorViewsApplication.java**:

~~~java
package com.example.reactiveerrors;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class ReactiveErrorViewsApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveErrorViewsApplication.class, args);
    }

    @RestController
    static class DemoController {

        @GetMapping("/api/ok")
        Mono<Map<String, String>> ok() {
            return Mono.just(Map.of("result", "ok"));
        }

        @GetMapping("/api/crash")
        Mono<String> crash() {
            return Mono.error(new IllegalStateException(
                    "Internal diagnostic details: do not expose"));
        }
    }
}
~~~

This is a **complete Java file** in a project with dependencies; it cannot run standalone with bare `javac`. `/api/crash` intentionally produces a reactive error for learning and must not be deployed publicly in production.

application.yml:

~~~yaml
server:
  port: 8081
  error:
    whitelabel:
      enabled: true
    include-message: never
    include-stacktrace: never
    include-binding-errors: never
~~~

Port 8081 is used so it can run alongside the MVC example on 8080; adjust if needed.

Run:

~~~bash
./gradlew bootRun
~~~

Test JSON/HTML for a missing URL and a 500 error:

~~~bash
curl -i -H 'Accept: application/json' \
  http://localhost:8081/khong-ton-tai

curl -i -H 'Accept: text/html' \
  http://localhost:8081/khong-ton-tai

curl -i -H 'Accept: application/json' \
  http://localhost:8081/api/crash

curl -i -H 'Accept: text/html' \
  http://localhost:8081/api/crash
~~~

Expected status 404 for the missing URL, 500 for `/api/crash`; HTML/JSON selected according to `Accept` and the actual error handler.

## 18. Testing WebFlux with WebTestClient

Create **src/test/java/com/example/reactiveerrors/ReactiveErrorViewsIntegrationTests.java**:

~~~java
package com.example.reactiveerrors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class ReactiveErrorViewsIntegrationTests {

    @Autowired
    WebTestClient client;

    @Test
    void missingUrlReturnsJson404() {
        client.get()
            .uri("/khong-ton-tai")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isNotFound()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_JSON);
    }

    @Test
    void missingUrlReturnsHtml404() {
        client.get()
            .uri("/khong-ton-tai")
            .accept(MediaType.TEXT_HTML)
            .exchange()
            .expectStatus().isNotFound()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.TEXT_HTML);
    }

    @Test
    void crashReturnsJson500() {
        client.get()
            .uri("/api/crash")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().is5xxServerError()
            .expectBody()
            .jsonPath("$.status").isEqualTo(500);
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

`WebTestClient` with `RANDOM_PORT` sends requests to a real reactive HTTP server. The tests do not pin Whitelabel markup or timestamps.

You can enable WebFlux ProblemDetail support:

~~~yaml
spring:
  webflux:
    problemdetails:
      enabled: true
~~~

However, this property does not turn **every** reactive error into `application/problem+json`; `DefaultErrorWebExceptionHandler` still retains its own fallback scope.

## 19. Security and Proxies Often Explain “Unexpected” JSON/HTML

### Spring Security

Security can generate 401, 403, or login page redirects right inside the filter chain. Thus, those responses may bypass `BasicErrorController`/`DefaultErrorWebExceptionHandler`. When an error page is accidentally blocked by Security, check permissions for the `ERROR` dispatch and error resources rather than **opening permissions on all APIs just to fix error page rendering**.

### Reverse Proxy

~~~text
Browser/API client
        |
        v
CDN / Load balancer / Nginx / Gateway
        |
        v
Spring Boot
~~~

A proxy can:
- Generate 502/503/504 on its own when the backend is down.
- Intercept 404/500 and replace the HTML page.
- Modify/strip `Accept`, causing the backend to choose a different representation.
- Mistakenly cache HTML/JSON under the same URL.
- Block requests before the backend using a WAF or authentication.

When an error looks different from Spring Boot's default, determine **whether the request actually reached the backend**. Compare logs, status, and Content-Type at each hop between gateway and backend.

### Vary and Caching

Because the same URL can return JSON or HTML depending on `Accept`, consider cache keys and `Vary: Accept`:

~~~http
Vary: Accept
~~~

Do not assume every error path automatically attaches `Vary`; verify actual responses and configure the gateway/cache. Avoid caching an HTML error and serving it to an API client expecting JSON.

## 20. Streaming and Committed Responses

With Server-Sent Events, Flux streaming, or large file downloads, an exception can occur **after the server has already sent status/headers and part of the body**.

~~~text
Server sends HTTP 200 + headers + a few chunks
          |
          +--> Exception occurs
          |
          +--> Cannot guarantee rewriting committed response
               into Whitelabel HTML or intact 500 JSON error
~~~

The client may observe an interrupted stream, truncated data, or a protocol-specific error frame if designed by the application. Do not promise that Spring Boot turns every exception into a 500 page; observability and stream protocols require their own strategies.

## 21. Operations and Security: Separating Public Errors from Server Logs

Debug data can include SQL, class names, file paths, dependency versions, request payloads, tokens, or stack traces. Never put all of this into public HTML/JSON.

A production system should have:

- Accurate HTTP statuses and stable error codes for clients.
- Correlation/request IDs that tie back to internal logs.
- Structured exception logs with redaction of `Authorization`, `Cookie`, tokens, and PII.
- Metrics/alerts for 4xx, 5xx, latency, and dependency failures.
- Friendly custom 404/5xx HTML pages with no internal information.
- `include-message`/`stacktrace`/`binding-errors` disabled on public endpoints unless risk-assessed.
- Practice-example endpoints that intentionally throw exceptions never exposed to the Internet.
- Path/query details restricted if they contain sensitive data.

An error already handled by `@ExceptionHandler` may no longer be treated by some metrics/observations as an unhandled exception. If operations need to track exceptions, record observations inside the handler rather than returning status=200.

## 22. Common Configuration Mistakes

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Browser sees Whitelabel 404 | Missing route or resource | Path, context path, controller scan |
| Curl sees JSON at the same URL | `Accept: application/json` | Response Content-Type |
| JSON lacks message | `include-message=never` | `server.error` properties |
| JSON lacks trace | `include-stacktrace=never` | Check server logs instead of public body |
| Whitelabel disabled, error page still shows | Container/proxy/custom view fallback | Servlet runtime, error templates |
| `error/404.html` added but unused | Wrong location, not packaged/restarted, view priority | Resource classpath and template engine |
| `ResponseEntity` 404 differs from default JSON | Controller builds body directly | Controller/advice logic |
| MockMvc does not produce default 500 | Lacks real container ERROR dispatch | `RANDOM_PORT` integration test |
| WebFlux lacks `BasicErrorController` | WebFlux handler differs from Servlet | Selected web stack |
| 401/403 lacks Whitelabel | Spring Security responds separately | `AuthenticationEntryPoint`/`DeniedHandler` |
| 502 HTML instead of JSON | Proxy generated the error | Gateway logs |
| Browser reports CORS instead of reading error | CORS policy blocks JS | Preflight and `Access-Control` headers |
| Streaming lacks 500 JSON | Response already committed | Server logs/stream protocol |
| Error exposes raw exception | Custom `ErrorAttributes`/trace enabled | Redaction and security config |

### Short Debugging Workflow

1. Confirm whether MVC or WebFlux is actually running.
2. Call a 200 endpoint to verify the server is listening on the right port.
3. Send failing requests with `Accept: application/json` and `Accept: text/html` separately.
4. Inspect status + Content-Type + body.
5. Check Security, proxies, and controller advice before blaming `/error`.
6. For MVC, inspect `BasicErrorController`, `ErrorAttributes`, and `ErrorViewResolver`.
7. For WebFlux, inspect `DefaultErrorWebExceptionHandler`/codecs.
8. Check `server.error.*` and `ProblemDetail` settings.
9. Verify static/template error resources inside the packaged artifact.
10. Test over real HTTP when behavior depends on container dispatch.

## 23. Hands-On Exercises

**Exercise 1 — Two representations:** Using the same URL `/khong-ton-tai`, send two requests with different `Accept` headers. Record the status, Content-Type, and differences in body. Explain why the status remains 404.

**Exercise 2 — 500 without internal leaks:** Call `/api/crash` with `Accept: application/json`; verify status 500, and verify JSON omits the raw exception message and trace when `include-message`/`stacktrace=never`.

**Exercise 3 — Custom HTML 404:** Add `public/error/404.html`, verify browsers see the new UI while clients sending `Accept: application/json` still receive the JSON error map.

**Exercise 4 — Disable Whitelabel:** Set `whitelabel.enabled=false`, restart, and compare HTML responses. Do not assume all Servlet containers share the exact same fallback.

**Exercise 5 — Domain exception:** Add `ProductUnavailableException` and the advice from Section 14; compare `application/problem+json` with default `ErrorAttributes` JSON.

**Exercise 6 — MockMvc vs. real HTTP:** Trigger an unhandled exception in MockMvc and via `RANDOM_PORT`; explain the role of Servlet ERROR dispatch.

**Exercise 7 — WebFlux:** Run on port 8081, send 404 and 500 with `Accept` HTML/JSON, and compare the reactive error handler with MVC `BasicErrorController`.

**Exercise 8 — Gateway:** Simulate a backend 404 error and a proxy 502 error in a demo environment; compare headers/body/logs to identify which layer generated each response.

## 24. Self-Check Questions

**Question 1.** Is Whitelabel an HTTP status?

**Answer:** No. It is an HTML fallback. The HTTP status can be 404, 500, or another code.

**Question 2.** Why do a browser and curl see different error bodies for the same URL?

**Answer:** Different `Accept` headers and content negotiation/error view selection mechanisms.

**Question 3.** Does `server.error.whitelabel.enabled=false` automatically disable default JSON?

**Answer:** No. That property mainly disables the Whitelabel HTML fallback.

**Question 4.** In Boot 3.3, do `message` and `trace` appear in default JSON errors?

**Answer:** No. `include-message` and `include-stacktrace` default to `never`.

**Question 5.** Where does a static 404 HTML file go?

**Answer:** `src/main/resources/public/error/404.html`.

**Question 6.** Does a controller returning `ResponseEntity.status(404)` always go through `/error`?

**Answer:** No. It can be returned as a direct response.

**Question 7.** Does WebFlux use the Servlet `BasicErrorController`?

**Answer:** No. It uses `DefaultErrorWebExceptionHandler` in the reactive layer.

**Question 8.** Does Boot's JSON map have the same schema as `ProblemDetail`?

**Answer:** No. Boot's JSON map typically has `timestamp`/`status`/`error`/`path`; `ProblemDetail` follows RFC 9457.

**Question 9.** Does an exception after a streaming response has committed always become a 500 JSON page?

**Answer:** No. Status/headers/body already sent may no longer be changeable.

**Question 10.** Can Nginx returning 502 due to upstream unavailability be fixed with `server.error.whitelabel.enabled`?

**Answer:** No. The error may be created by the proxy before the request even reaches Boot.

**Question 11.** Why shouldn't stack traces be enabled publicly?

**Answer:** They can leak internal details, SQL, code paths, dependency versions, and sensitive data; keep them in controlled internal logs.

## 25. Implementation Checklist

- [ ] Identified MVC vs. WebFlux and its corresponding global error handler.
- [ ] Tested 404/500 with both HTML and JSON `Accept` headers.
- [ ] Checked status, Content-Type, and body together.
- [ ] Avoided calling `GET /error` directly to simulate full Servlet ERROR dispatch.
- [ ] Prevented exposing unnecessary exception messages, stack traces, class names, or binding errors.
- [ ] Provided branded 404/4xx/5xx error pages for HTML frontends.
- [ ] Established a stable error schema and accurate HTTP statuses for REST APIs.
- [ ] Scoped `@ControllerAdvice` properly so HTML web pages are not accidentally turned into JSON.
- [ ] Added real-HTTP-server integration tests for the `/error` fallback.
- [ ] Configured structured logs, metrics, correlation IDs, and redaction of sensitive data.
- [ ] Checked Security, proxies, caching, and CORS when responses differ from expectations.
- [ ] Ensured lab endpoints that intentionally throw exceptions are never shipped to production.
- [ ] Designed error handling for cases when streaming has already committed.

## Official References

- [Spring Boot 3.3 — Servlet Web Applications: Error Handling](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
- [Spring Boot 3.3 — Reactive Web Applications: Error Handling](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html)
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
- [Spring Boot 3.3 — BasicErrorController Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/servlet/error/BasicErrorController.html)
- [Spring Boot 3.3 — DefaultErrorWebExceptionHandler Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/reactive/error/DefaultErrorWebExceptionHandler.html)
- [Spring Framework — MVC Error Responses and ProblemDetail](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)
- [Spring Framework — WebFlux Error Responses](https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html)