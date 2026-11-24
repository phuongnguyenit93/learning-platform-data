# CharacterEncodingFilter, FormContentFilter, and HiddenHttpMethodFilter in Spring MVC

## 1. Three Servlet Filters Solving Three Different Problems

In the Spring MVC **Servlet stack**, data from the client does not go straight to the controller. Before `DispatcherServlet`, a chain of `jakarta.servlet.Filter` components can adjust encoding, wrap requests, attach information, and even change the HTTP method seen by downstream code.

Three filters in `org.springframework.web.filter` solve three distinct problems:

| Filter | Problem It Solves | Core Effect |
| --- | --- | --- |
| **`CharacterEncodingFilter`** | Text/form data is decoded incorrectly because the request/response charset has not been set properly | Calls `setCharacterEncoding` on the request and optionally on the response; configurable via `forceRequestEncoding`/`forceResponseEncoding` |
| **`FormContentFilter`** | The Servlet API only requires `getParameter*` form parameters for POST; PUT/PATCH/DELETE with a form-urlencoded body may fail to bind | Reads the `application/x-www-form-urlencoded` body of PUT/PATCH/DELETE and wraps the request to expose form fields via `getParameter*` |
| **`HiddenHttpMethodFilter`** | Browser HTML forms send GET/POST, while Spring handlers want `@PutMapping`, `@PatchMapping`, or `@DeleteMapping` | For a POST containing form parameter `_method=PUT/PATCH/DELETE`, wraps the request so `getMethod()` returns the requested method |

**One filter does not replace the other two.** Fixing encoding does not turn a PUT body into Servlet parameters; reading a PUT form body does not change the HTTP method; turning POST into DELETE does not make authorization/CSRF checks unnecessary.

Three example requests:

```http
POST /demo/form HTTP/1.1
Content-Type: application/x-www-form-urlencoded; charset=UTF-8

text=Ph%E1%BB%9F
```

```http
PUT /demo/form HTTP/1.1
Content-Type: application/x-www-form-urlencoded; charset=UTF-8

text=Ph%E1%BB%9F
```

```http
POST /demo/items/7 HTTP/1.1
Content-Type: application/x-www-form-urlencoded; charset=UTF-8

_method=DELETE
```

In the demo app in Section 8:

- The first request goes to `@PostMapping` with `text="Phở"`. The request charset must be determined **before the Servlet container reads form parameters**.
- The second request goes to `@PutMapping` with `text="Phở"` thanks to `FormContentFilter` supporting Servlet-style `@RequestParam` from the PUT body.
- The third request **remains a POST on the HTTP wire**, but `HiddenHttpMethodFilter` wraps the request so downstream MVC sees method DELETE and selects `@DeleteMapping`.

This article focuses on **Spring Framework 6.x/Spring Boot 3.x, Java 17+, Servlet MVC**, explaining differences with Boot 2 and 4. With Spring WebFlux/reactive stack, these Servlet filters are not used as part of a `WebFilter` chain.

## 2. Where Do They Sit in HTTP Processing?

```text
Client sends HTTP bytes
        |
        v
Servlet container: request, response, FilterChain
        |
        +--> CharacterEncodingFilter
        |      sets request/response charset per policy
        |
        +--> FormContentFilter
        |      PUT/PATCH/DELETE + application/x-www-form-urlencoded?
        |      parses body and wraps HttpServletRequest.getParameter*()
        |
        +--> HiddenHttpMethodFilter
        |      POST with _method=PUT/PATCH/DELETE?
        |      wraps HttpServletRequest.getMethod()
        |
        +--> other app-specific filters (logging, Security, CORS...)
        |
        v
DispatcherServlet
        |
        v
HandlerMapping selects @PostMapping / @PutMapping / @DeleteMapping ...
        |
        v
HandlerAdapter:
  @RequestParam / @ModelAttribute -> reads Servlet request parameters
  @RequestBody                -> uses HttpMessageConverter when applicable
        |
        v
Controller / View / ResponseEntity
        |
        v
Response flows back through FilterChain
```

This is a **functional diagram**; it does not assert that every application has these exact three filters in this exact order and no others. The container selects registrations, URL patterns, dispatcher types, and order; Boot auto-configuration provides defaults depending on version/properties. For `HiddenHttpMethodFilter`, relative ordering with Spring Security and multipart processing has major impact.

Do not confuse:

- `HttpServletRequest#getMethod()` is a Servlet API method seen by wrappers. The hidden filter **does not rewrite the transmitted HTTP packet** and does not convert a POST into a DELETE on the wire between browser and proxy.
- `request.getParameter("text")` retrieves query/form parameters per Servlet semantics; it does not mean reading a JSON body.
- `Content-Type` states what media type the body uses. `Accept` only describes response representations accepted by the client; it does not trigger these filters.
- `@Valid` / `@Validated` performs Bean Validation after data binding; it is not a filter feature.
- `Filter` operates at the Servlet layer **before** MVC; `HandlerInterceptor` is called only during MVC handler selection and execution.

## 3. How Does `CharacterEncodingFilter` Work?

Class: `org.springframework.web.filter.CharacterEncodingFilter`; extends `OncePerRequestFilter`.

Servlet request parameters may be strings decoded from HTTP bytes. If the input charset is not established in time, characters such as “Đắk Lắk”, “Phở”, “Hà Nội” can turn into question marks or mojibake characters.

This filter allows configuring:

- **`encoding`**: charset such as `UTF-8`.
- **`forceRequestEncoding`**: enforces the charset on the request even if the request specifies a different encoding.
- **`forceResponseEncoding`**: enforces the charset on the response per policy.
- **`forceEncoding`**: shortcut applying the force setting to both request and response in the relevant API.

Example manual Java configuration fragment:

```java
import org.springframework.web.filter.CharacterEncodingFilter;

CharacterEncodingFilter filter = new CharacterEncodingFilter();
filter.setEncoding("UTF-8");
filter.setForceRequestEncoding(true);
filter.setForceResponseEncoding(false);
```

The fragment above **only creates and configures the object**; it does not register it with the Servlet container. In typical Spring Boot applications, prefer Boot-managed properties to avoid duplicate registrations.

### 3.1. Set Encoding Before Reading Parameters/Body

A common mistake:

```java
String text = request.getParameter("text");
request.setCharacterEncoding("UTF-8"); // May already be too late.
```

If the container already decoded the form parameter using the wrong encoding, calling `setCharacterEncoding` afterward **does not rebuild** the already-corrupted Java string. Therefore, `CharacterEncodingFilter` must run before any custom filter, controller, or Servlet component that reads request parameters/body.

In Spring Boot 3, the encoding filter typically has an early order. If you add a custom body-reading filter and put it at `Ordered.HIGHEST_PRECEDENCE`, you risk running **before the encoding filter**. Verify actual filter order with logs and integration tests.

### 3.2. Forcing Request Encoding Is Not Equivalent to “Accepting Any Charset”

Suppose a client explicitly sends:

```http
Content-Type: application/x-www-form-urlencoded; charset=ISO-8859-1
```

If you configure **force-request UTF-8**, the request may be read as UTF-8 instead of the charset declared by the client. This is right when the API contract **mandates UTF-8**, but wrong when the system genuinely needs to support multiple charsets. Publish the accepted charset rather than turning on “force” arbitrarily and corrupting data.

### 3.3. Request Encoding and Response Encoding Are Two Separate Decisions

- For form-urlencoded input, the focus is **request charset before parsing**.
- For HTML/text responses, `response.setCharacterEncoding(...)` only takes effect if applied before response body/headers are committed and before the writer is obtained.
- For JSON, Spring MVC uses `HttpMessageConverter` (typically Jackson) and media type rules. `CharacterEncodingFilter` does not replace the JSON decoder or converter selection.
- URI path/query decoding, connector settings, DB collation/charset, Java source file encoding, and HTML meta charset are **separate layers**; this filter does not fix all of them automatically.

When debugging corrupted Vietnamese text, inspect the actual bytes sent by the client, `Content-Type`/charset, Servlet request decoding, filter order, converter, response charset, and client rendering.

## 4. `FormContentFilter` — Letting PUT/PATCH/DELETE Read Form Parameters

Class: `org.springframework.web.filter.FormContentFilter`; extends `OncePerRequestFilter`.

Per the Servlet specification, `getParameter*()` is required to support parsing `application/x-www-form-urlencoded` **for POST** under valid conditions. You cannot rely on every Servlet container having identical behavior for PUT, PATCH, and DELETE. `FormContentFilter` fills that gap:

1. Receives the Servlet request in the filter chain.
2. Checks whether the method is **PUT/PATCH/DELETE** and the body has an appropriate form-urlencoded media type.
3. Uses a form HTTP message converter to read the key-value pairs.
4. Wraps `HttpServletRequest` so `getParameter`/`getParameterMap`/`getParameterNames`/`getParameterValues` expose body data as request parameters.
5. Forwards the wrapped request to MVC or downstream filters.

Example:

```http
PATCH /api/products/7 HTTP/1.1
Content-Type: application/x-www-form-urlencoded; charset=UTF-8

title=S%E1%BB%95+tay&quantity=2
```

The handler can read:

```java
@PatchMapping(
        path = "/api/products/{id}",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
String patch(
        @PathVariable long id,
        @RequestParam String title,
        @RequestParam int quantity) {

    return id + ":" + title + ":" + quantity;
}
```

This is a controller method fragment requiring `MediaType` and MVC annotation imports. With `FormContentFilter` enabled and a valid request, expected parameters are `id=7`, `title="Sổ tay"`, `quantity=2`.

### 4.1. What Does This Filter Not Do?

- **Does not change the HTTP method.** PUT remains PUT, PATCH remains PATCH.
- **Does not parse JSON into form parameters.** An `application/json` body needs `@RequestBody`/a JSON message converter.
- **Does not guarantee support for all form types.** `multipart/form-data` requires separate multipart resolution; do not treat it like `application/x-www-form-urlencoded`.
- **Does not perform business validation.** `quantity=0` can bind to int 0 unless other validation/rules exist.
- **Is unnecessary if the controller reads the body directly through another suitable mechanism.** For example, `@RequestBody MultiValueMap<...>` can use an appropriate form message converter, which is a different code path from `@RequestParam`.

### 4.2. Query Parameters and Body Parameters with the Same Name

Example:

```http
PUT /api/products/7?title=from-query HTTP/1.1
Content-Type: application/x-www-form-urlencoded

title=from-body
```

When the Servlet request wrapper merges parameter sources, do not design a contract relying ambiguously on “which value wins” or “value ordering” for the same name. It is better to avoid duplicate keys or define explicit locations: path ID in URI, form fields only in body, pagination via query.

### 4.3. InputStream May Be Consumed

`FormContentFilter` must read the body to parse key-value data. If another filter or controller later tries to read the raw `ServletInputStream`, do not assume the body remains intact for a second read. If the application strictly must inspect the raw body alongside form binding, design a controlled caching wrapper and test on the real container; **never log passwords, tokens, or sensitive data** just for debugging.

Placing a body-reading filter too early or stacking multiple body-caching filters easily alters parsing, request size, and performance unexpectedly.

## 5. `HiddenHttpMethodFilter` — Emulating PUT/PATCH/DELETE from HTML POST

Class: `org.springframework.web.filter.HiddenHttpMethodFilter`; extends `OncePerRequestFilter`.

Standard HTML forms support submitting via **GET or POST**. A RESTful MVC controller, however, may want:

```java
@PutMapping("/products/{id}")
@PatchMapping("/products/{id}")
@DeleteMapping("/products/{id}")
```

To bridge the two, an HTML form can actually submit a POST containing a hidden field:

```html
<form action="/demo/items/7" method="post">
  <input type="hidden" name="_method" value="DELETE">
  <button type="submit">Delete</button>
</form>
```

The browser sends:

```http
POST /demo/items/7 HTTP/1.1
Content-Type: application/x-www-form-urlencoded

_method=DELETE
```

`HiddenHttpMethodFilter` reads the `_method` request parameter, verifies it is an allowed method, and wraps the request. Components **after the filter** (such as `DispatcherServlet`) see `request.getMethod() == "DELETE"`, matching `@DeleteMapping`.

**Only three methods are allowed for override: PUT, DELETE, and PATCH.** This is not a mechanism for clients to arbitrarily turn POST into GET/HEAD/OPTIONS/TRACE or any random method.

### 5.1. Configuring a Field Name Other Than `_method`

The default field name is `_method` (`HiddenHttpMethodFilter.DEFAULT_METHOD_PARAM`). It can be customized:

```java
HiddenHttpMethodFilter filter = new HiddenHttpMethodFilter();
filter.setMethodParam("_httpMethod");
```

This fragment only creates the object. Register the filter exactly once; if you rename the field, HTML must submit the new name. In Boot, if the default `_method` suffices, enabling the corresponding property is usually simpler.

### 5.2. Why Only Process POST?

Because the goal is to support HTML forms sending **POST over the wire** when the MVC handler expects an update/delete method. For native PUT/PATCH/DELETE requests, `HiddenHttpMethodFilter` **does not need to alter the method**.

Downstream filters may see DELETE even though the wire packet was POST. Consequently, when analyzing reverse proxy access logs and application logs, distinguish the **wire method** from the **method presented by the Servlet request wrapper**.

### 5.3. Hidden Method Is Not Permission or Authorization

Clients can submit `_method=DELETE` on their own without clicking a button in the HTML view. Therefore:

- Separate authentication, authorization, and ownership checks are required.
- When using cookie authentication, protect state-changing requests with an appropriate CSRF policy.
- Spring Security can use method-based matchers. Arrange and integrate filters so the authorization layer sees the intended method by design.
- Do not treat rendering the DELETE button only for admins in a template as server-side protection.
- Do not record or execute a deletion solely because the `_method` key exists; the request must pass through the entire MVC/security/business validation pipeline.

## 6. Default Configuration in Spring Boot 3.x

**Distinguish Spring Framework classes from Spring Boot auto-configuration.** Just because a filter exists in `spring-web` does not mean Boot enables that filter in every app.

For **Spring Boot 3.5** on Servlet MVC, the properties/auto-configuration documentation shows:

| Component | What Does Boot 3.5 Usually Do? | Property |
| --- | --- | --- |
| `CharacterEncodingFilter` | Boot auto-configures when applicable for a Servlet web app and encoding support is enabled | `server.servlet.encoding.enabled`, `server.servlet.encoding.charset`, `server.servlet.encoding.force-*` |
| `FormContentFilter` | **Enabled by default** when auto-configuration conditions and classpath match | `spring.mvc.formcontent.filter.enabled=true` |
| `HiddenHttpMethodFilter` | **Disabled by default**; must be enabled if the app uses HTML `_method` | `spring.mvc.hiddenmethod.filter.enabled=false` |

An illustrative configuration for a Boot 3 learning project:

```properties
# src/main/resources/application.properties
server.servlet.encoding.enabled=true
server.servlet.encoding.charset=UTF-8
server.servlet.encoding.force-request=true

spring.mvc.formcontent.filter.enabled=true
spring.mvc.hiddenmethod.filter.enabled=true
```

- `CharacterEncodingFilter` gets the UTF-8 charset before form parameter parsing (with appropriate registration order).
- `FormContentFilter` is configured by Boot to read form-urlencoded bodies on PUT/PATCH/DELETE.
- `HiddenHttpMethodFilter` is enabled so HTML form POST `_method=...` routes to the corresponding method endpoints.
- This is a **configuration chosen for the demo**, not advice that every API should enable hidden-method override. If an API only accepts JSON with native HTTP PUT/DELETE from mobile/SPA clients, `HiddenHttpMethodFilter` is usually unnecessary.
- `force-request=true` reflects the example contract using only UTF-8. For a service accepting multiple charsets, design accordingly.

**If you also want response encoding forced**, Boot 3 has `server.servlet.encoding.force-response=true`; consider the content types being sent, server/container, and media types. Do not set “force all” by default if valid clients use other charsets.

### 6.1. Do Not Manually Register a Second Time

When Boot already creates the corresponding filter, **do not simultaneously create another `@Bean CharacterEncodingFilter` / `FilterRegistrationBean` for the same purpose** just because you saw an example online. The result can be duplicate execution, double request wrapping, unpredictable ordering, or a bean causing Boot auto-configuration to back off unexpectedly.

Preferred approach in normal applications:

1. Choose the appropriate Boot properties.
2. Inspect registrations in startup logs.
3. Use integration tests to confirm form binding and hidden overrides.
4. Create a custom `FilterRegistrationBean` only when you genuinely need non-default URL patterns/dispatcher types/order/constructor.

### 6.2. How to Inspect Filter Registrations

```properties
logging.level.web=debug
```

In Boot 3, logs in the `web` group generally print filter registrations, URL patterns, and order at startup. With many auto-configured filters (encoding, request wrappers, Spring Security, observation...), the actual order **does not consist of only the three filters** in this article. Inspect in an isolated test environment so enabling DEBUG does not leak sensitive request metadata in production.

## 7. A Runnable Example: Java 17 + Spring Boot 3.5

The demo app simultaneously illustrates:

- Form-urlencoded POST with Vietnamese text.
- Form-urlencoded PUT where `@RequestParam` still receives fields from the body.
- Similar form-urlencoded PATCH.
- HTML POST with `_method=DELETE` handled by `@DeleteMapping`.

**Baseline:** Java 17+, Spring Boot **3.5.x**, Spring Framework 6.2.x, embedded Servlet MVC (default Tomcat in web starter). The example omits Spring Security, databases, and Thymeleaf to avoid out-of-scope interactions; the HTML demo is a plain form.

### 7.1. Gradle Dependencies

In a project with the Spring Boot Gradle plugin and repositories/dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is a **`build.gradle` fragment**. The project should be created/configured via Spring Initializr or a standard Spring Boot build file. The sample has no Spring Security dependency; in a real app with Spring Security, configure auth/CSRF/tests accordingly.

### 7.2. Properties

Create **`src/main/resources/application.properties`**:

```properties
server.servlet.encoding.charset=UTF-8
server.servlet.encoding.force-request=true
spring.mvc.formcontent.filter.enabled=true
spring.mvc.hiddenmethod.filter.enabled=true
```

Do not manually add `CharacterEncodingFilter`, `FormContentFilter`, or `HiddenHttpMethodFilter` beans in this demo. Let Boot perform auto-registration per the properties.

### 7.3. Java Controller

Create **`src/main/java/demo/builtinfilters/BuiltinFiltersApplication.java`**:

```java
package demo.builtinfilters;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class BuiltinFiltersApplication {

    public static void main(String[] args) {
        SpringApplication.run(BuiltinFiltersApplication.class, args);
    }
}

@RestController
@RequestMapping("/demo")
class FormDemoController {

    @PostMapping(
            path = "/form",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    String post(@RequestParam("text") String text) {
        return "POST:" + text;
    }

    @PutMapping(
            path = "/form",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    String put(@RequestParam("text") String text) {
        return "PUT:" + text;
    }

    @PatchMapping(
            path = "/form",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    String patch(@RequestParam("text") String text) {
        return "PATCH:" + text;
    }

    @DeleteMapping(
            path = "/items/{id}",
            produces = MediaType.TEXT_PLAIN_VALUE)
    String delete(@PathVariable long id) {
        // Simulation only; a real app must check auth and delete from DB.
        return "DELETE:" + id;
    }
}
```

**Compiles against the stated baseline**: the file has only one `public` class, `BuiltinFiltersApplication`; `FormDemoController` is non-public so placing it in the same file is valid. The controller is component-scanned from package `demo.builtinfilters`.

The endpoints return plain text only to keep focus on Servlet filtering, without Jackson, persistence, or Bean Validation. Response body `POST:Phở` proves form decoding; `PUT:Phở` proves GET/POST are not the only methods able to receive `@RequestParam` from a form body once `FormContentFilter` is active; `DELETE:7` proves method override.

### 7.4. Run and Send curl

Start via the Gradle wrapper:

```bash
./gradlew bootRun
```

**Form-urlencoded POST with UTF-8:**

```bash
curl -i -X POST 'http://localhost:8080/demo/form' \
  -H 'Content-Type: application/x-www-form-urlencoded; charset=UTF-8' \
  --data-urlencode 'text=Phở'
```

Expected response body (status 200):

```text
POST:Phở
```

**Form-urlencoded PUT:**

```bash
curl -i -X PUT 'http://localhost:8080/demo/form' \
  -H 'Content-Type: application/x-www-form-urlencoded; charset=UTF-8' \
  --data-urlencode 'text=Phở'
```

Expected response body:

```text
PUT:Phở
```

**Form-urlencoded PATCH:**

```bash
curl -i -X PATCH 'http://localhost:8080/demo/form' \
  -H 'Content-Type: application/x-www-form-urlencoded; charset=UTF-8' \
  --data-urlencode 'text=Phở'
```

Expected response body:

```text
PATCH:Phở
```

**POST emulating DELETE:**

```bash
curl -i -X POST 'http://localhost:8080/demo/items/7' \
  -H 'Content-Type: application/x-www-form-urlencoded; charset=UTF-8' \
  --data '_method=DELETE'
```

Expected response body:

```text
DELETE:7
```

In this example, the controller has only `@DeleteMapping("/items/{id}")` and **no** `@PostMapping` for that route. If `HiddenHttpMethodFilter` is disabled, POST `_method=DELETE` **does not automatically match** `@DeleteMapping` and usually returns 405 Method Not Allowed, depending on app/error handling. If `FormContentFilter` is disabled, PUT/PATCH form parameters from the body may not be exposed by the Servlet container as expected, leaving `@RequestParam("text")` unresolved and typically producing HTTP 400. Do not rely on “a container happening to support it” because the Servlet spec does not mandate it.

The curl examples assume the server is on port 8080 with no custom filter/proxy/security. Actual headers (date, length, charset...) may vary; what matters is testing status, the controller method chosen, and proper Unicode text.

### 7.5. HTML Form Using `_method`

HTML sample suitable for a template or static page (adjust URL for the app's context path):

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Delete resource demo</title>
</head>
<body>
  <form method="post" action="/demo/items/7"
        accept-charset="UTF-8">
    <input type="hidden" name="_method" value="DELETE">
    <button type="submit">Delete item 7</button>
  </form>
</body>
</html>
```

The browser actually sends POST. With `HiddenHttpMethodFilter` enabled, MVC can invoke the `@DeleteMapping` method. In a real application with cookie-based login, **you must include the CSRF token according to your Spring Security setup**, verify permission to delete item 7, and never leave this path open as a public demo endpoint.

## 8. Integration Testing: Verifying Real Filters via Embedded Server

Use `@SpringBootTest(webEnvironment=RANDOM_PORT)` instead of only unit-testing the controller to verify the Servlet container and Boot auto-registered filters actually participate. `MockMvc` can test MVC bindings and filters attached to the test context, but it does not necessarily reflect all embedded container registration/dispatcher ordering.

Create **`src/test/java/demo/builtinfilters/BuiltinFiltersApplicationTests.java`**:

```java
package demo.builtinfilters;

import java.nio.charset.StandardCharsets;
import java.net.URLEncoder;
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

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class BuiltinFiltersApplicationTests {

    @Autowired
    TestRestTemplate http;

    private HttpHeaders formHeaders() {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_FORM_URLENCODED);
        return headers;
    }

    @Test
    void postFormDecodesUtf8() {
        String value = URLEncoder.encode(
                "Phở", StandardCharsets.UTF_8);
        HttpEntity<String> request = new HttpEntity<>(
                "text=" + value, formHeaders());

        ResponseEntity<String> response = http.postForEntity(
                "/demo/form", request, String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("POST:Phở", response.getBody());
    }

    @Test
    void putFormBodyBecomesRequestParameter() {
        HttpEntity<String> request = new HttpEntity<>(
                "text=Notebook", formHeaders());

        ResponseEntity<String> response = http.exchange(
                "/demo/form", HttpMethod.PUT, request, String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("PUT:Notebook", response.getBody());
    }

    @Test
    void patchFormBodyBecomesRequestParameter() {
        HttpEntity<String> request = new HttpEntity<>(
                "text=Notebook", formHeaders());

        ResponseEntity<String> response = http.exchange(
                "/demo/form", HttpMethod.PATCH, request, String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("PATCH:Notebook", response.getBody());
    }

    @Test
    void hiddenMethodChangesPostToDeleteForMvc() {
        HttpEntity<String> request = new HttpEntity<>(
                "_method=DELETE", formHeaders());

        ResponseEntity<String> response = http.postForEntity(
                "/demo/items/7", request, String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("DELETE:7", response.getBody());
    }

    @Test
    void postWithoutHiddenOverrideRemainsPost() {
        HttpEntity<String> request = new HttpEntity<>(
                "text=Notebook", formHeaders());

        ResponseEntity<String> response = http.postForEntity(
                "/demo/form", request, String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("POST:Notebook", response.getBody());
    }
}
```

Run:

```bash
./gradlew test
```

**These tests are expected to reflect the behavior described above on the Boot 3.5 baseline with the filter config enabled.** However, note a caveat about `PATCH`: `TestRestTemplate` uses the underlying HTTP client request factory; some `RestTemplate`/`HttpURLConnection` setups **do not support HTTP PATCH**. If the PATCH test fails with `Invalid HTTP method: PATCH` **before reaching the server**, that is a limitation of the **test's HTTP client**, not proof that `FormContentFilter` or the controller is wrong. To test PATCH over real HTTP, configure `TestRestTemplate` with a PATCH-capable request factory (such as Apache HttpComponents with the proper dependency), or use `curl -X PATCH` as above. Do not record the PATCH test as “PASS” without checking whether the client actually sent the request.

**Important note to keep the test suite runnable:** if the test environment lacks a PATCH-capable HTTP client, **do not assume the five tests above pass verbatim**. You can replace the PATCH test method with a request via Java's `java.net.http.HttpClient` (Java 17) as shown next, because that client supports arbitrary methods including PATCH.

### 8.1. PATCH via Java 17 HttpClient (No HttpComponents Needed)

In the test class above, to remove reliance on `TestRestTemplate`'s PATCH support, add the port field and replace **only the `patchFormBodyBecomesRequestParameter` test method** with:

```java
@org.springframework.boot.test.web.server.LocalServerPort
int port;

@Test
void patchFormBodyBecomesRequestParameter() throws Exception {
    java.net.http.HttpClient client =
            java.net.http.HttpClient.newHttpClient();

    java.net.http.HttpRequest request =
            java.net.http.HttpRequest.newBuilder()
                .uri(java.net.URI.create(
                        "http://localhost:" + port + "/demo/form"))
                .header("Content-Type",
                        "application/x-www-form-urlencoded; charset=UTF-8")
                .method(
                        "PATCH",
                        java.net.http.HttpRequest.BodyPublishers
                                .ofString("text=Notebook"))
                .build();

    java.net.http.HttpResponse<String> response =
            client.send(
                    request,
                    java.net.http.HttpResponse.BodyHandlers.ofString());

    assertEquals(200, response.statusCode());
    assertEquals("PATCH:Notebook", response.body());
}
```

This snippet is a **fragment replacing one method in the test class**, using Java 17 `HttpClient` and `LocalServerPort`, not added alongside a duplicate method in the same class. This replacement sends the PATCH request to the **real embedded server**, independent of `RestTemplate`'s request factory. If desired immediately, you can use `HttpClient` for all five tests or keep `TestRestTemplate` for the other methods.

**The tests in this article only describe expected results and have not been executed**; to confirm passes, run `./gradlew test` inside a configured Spring Boot project.

## 9. Manual Filter Configuration When Explicit Order Control Is Truly Needed

If an application wants explicit order and dispatcher mappings instead of auto-registration, it can create `FilterRegistrationBean` beans. **This is an alternative to Section 7's property-based Boot auto-configuration and must not be enabled simultaneously as-is.**

Example fragment (placed inside a `@Configuration` class in Boot 3):

```java
@Bean
FilterRegistrationBean<CharacterEncodingFilter> encodingRegistration() {
    CharacterEncodingFilter filter = new CharacterEncodingFilter(
            "UTF-8", true);
    FilterRegistrationBean<CharacterEncodingFilter> bean =
            new FilterRegistrationBean<>(filter);
    bean.setName("myEncodingFilter");
    bean.setOrder(10);
    bean.addUrlPatterns("/*");
    bean.setDispatcherTypes(DispatcherType.REQUEST);
    return bean;
}

@Bean
FilterRegistrationBean<FormContentFilter> formRegistration() {
    FilterRegistrationBean<FormContentFilter> bean =
            new FilterRegistrationBean<>(new FormContentFilter());
    bean.setName("myFormContentFilter");
    bean.setOrder(20);
    bean.addUrlPatterns("/*");
    bean.setDispatcherTypes(DispatcherType.REQUEST);
    return bean;
}

@Bean
FilterRegistrationBean<HiddenHttpMethodFilter> hiddenMethodRegistration() {
    FilterRegistrationBean<HiddenHttpMethodFilter> bean =
            new FilterRegistrationBean<>(new HiddenHttpMethodFilter());
    bean.setName("myHiddenMethodFilter");
    bean.setOrder(30);
    bean.addUrlPatterns("/*");
    bean.setDispatcherTypes(DispatcherType.REQUEST);
    return bean;
}
```

This is a **fragment**, requiring imports `org.springframework.boot.web.servlet.FilterRegistrationBean`, `org.springframework.web.filter.*`, `jakarta.servlet.DispatcherType`, and `@Bean`. If you actually use these three registrations, **disable or remove Boot's corresponding auto-registrations** and verify no other servlet filter bean serves the same role:

```properties
# Illustrates MANUAL registration mode only, differing from Section 7's demo project.
server.servlet.encoding.enabled=false
spring.mvc.formcontent.filter.enabled=false
spring.mvc.hiddenmethod.filter.enabled=false
```

The `10/20/30` order expresses only **relative ordering among Boot-managed registrations**; it does not guarantee encoding always runs before Spring Security or every infrastructure filter. If a body-reading filter is needed, check the actual order of the preceding encoding filter. With `web.xml`/`@WebFilter` or external WAR deployments, ordering also follows Servlet specs/external config; do not blindly rely on Boot's `setOrder` for registrations it does not manage.

### 9.1. Why Check Servlet DispatcherType?

`FilterRegistrationBean#setDispatcherTypes(DispatcherType.REQUEST)` in the example above means the filter runs for the **initial request dispatch**; it does not automatically participate in `FORWARD`, `ERROR`, `ASYNC`, or `INCLUDE`. If a filter needs async/error support, choose dispatcher types deliberately and keep in mind that all three filters extend `OncePerRequestFilter`, which skips async/error by default. Do not enable all dispatcher types indiscriminately just because the enum exists.

For `HiddenHttpMethodFilter`, overriding the method once during REQUEST before MVC chooses a handler is usually the clear goal; repeating method override in an ERROR dispatch is unnecessary. For form data, avoid reading the body a second time after a wrapper has processed the request and another Servlet dispatch occurs.

### 9.2. Multipart Forms and HiddenHttpMethodFilter

`HiddenHttpMethodFilter` must read `_method` as a request parameter, so for `multipart/form-data` POSTs, **multipart processing must happen before it** so the field can be retrieved as expected. The Javadoc recommends placing `MultipartFilter` before `HiddenHttpMethodFilter` when using filter-based multipart resolution.

**Do not conclude you must always add `MultipartFilter` in Boot.** In Spring MVC apps, multipart can be configured for `DispatcherServlet` to handle; when `HiddenHttpMethodFilter` runs before `DispatcherServlet`, whether multipart parameters can be read depends on the Servlet container and multipart config. Therefore, integration-test **multipart POST + `_method=PATCH/DELETE`** on your target container, or stick to simple form-urlencoded for hidden methods.

Avoid combining `MultipartFilter` with incompatible Servlet-specific multipart resolution. If custom ordering requires multipart before hidden, verify exactly which filter resolves multipart in your architecture.

## 10. Spring Security, CSRF, and HTTP Method Override

When `HiddenHttpMethodFilter` is enabled, security must see the transformed method on the Servlet request wrapper **if authorization policies depend on the HTTP method**.

A desired flow:

```text
Browser sends POST /items/7 + _method=DELETE
      |
      +-- character encoding
      +-- parse form params if needed
      +-- hidden method wrapper -> getMethod() = DELETE
      +-- Spring Security authentication/authorization/CSRF
      +-- DispatcherServlet -> @DeleteMapping
```

This is a **design requirement diagram**, not a guaranteed auto-registration order across all Boot/Security versions. `Spring Security FilterChainProxy` sits in its own Servlet filter registration; if ordered differently, Security may evaluate POST while MVC later evaluates DELETE. Inspect the startup filter list or security debug output and test both authorized and unauthorized requests.

**CSRF:** for state-changing requests using cookie sessions, CSRF protection is critical. HTML form method override does not bypass CSRF. Spring Security can process the `_csrf` request parameter; ensure hidden method filter, encoding/multipart, and CSRF token processing work together on applicable requests. If the initial POST contains `_method=DELETE`, CSRF must still be validated per application policy.

**Authorization:** never rely on the UI rendering the delete button only for admins. Clients can submit POST forms or native DELETE directly; the server must verify the resource, identity, and operation permissions.

### 10.1. How Do Native DELETE and Hidden DELETE Differ?

| Aspect | Native DELETE | POST + `_method=DELETE` |
| --- | --- | --- |
| HTTP method on the wire | DELETE | POST |
| Servlet method after hidden filter | DELETE | DELETE (if filter enabled/mapped properly) |
| Upstream proxy/WAF/access logs | Sees DELETE | Sees POST |
| MVC handler | `@DeleteMapping` | `@DeleteMapping` |
| Browser HTML form without JS | Does not support DELETE directly | Supported |
| Security/filter order | Must be applied properly | Especially requires consistent method after override |
| Caching, idempotency, and retries | Follows semantics of the actual HTTP method sent | Proxies/clients see POST; do not assume idempotency on the network |

If an API serves SPAs/mobile apps that already send native HTTP methods, **hidden method override is usually unnecessary**. Enable the filter only when HTML forms or legacy clients genuinely require this pattern.

## 11. Encoding Bugs: Distinguishing Form Body, URL, and Response

### 11.1. Form-Urlencoded Follows Percent-Encoding Rules

With UTF-8, the string `Phở` is encoded into a form-urlencoded body as percent-encoded bytes. Example:

```text
Java String:       Phở
UTF-8 bytes:       50 68 E1 BB 9F
Form encoded:      Ph%E1%BB%9F
```

When receiving the request with the right charset, the Servlet container and `FormContentFilter` (depending on method) reconstruct the Java `String "Phở"`. If bytes are decoded with the wrong charset, the text will be garbled even though the controller still runs.

### 11.2. URL Query/Path Are Not Solely Controlled by CharacterEncodingFilter

`/products?title=...` and `/products/{slug}` are affected by URL percent-encoding, container connector settings, and URI decoding policy. For example, Tomcat has `server.tomcat.uri-encoding=UTF-8` in applicable configurations. **Do not** assume enabling `CharacterEncodingFilter` controls all URL path/query decoding across every Servlet container.

### 11.3. JSON Does Not Need FormContentFilter

Client:

```http
PUT /api/products/7 HTTP/1.1
Content-Type: application/json

{"title":"Phở"}
```

Controller:

```java
@PutMapping("/api/products/{id}")
ResponseEntity<Void> update(
        @PathVariable long id,
        @RequestBody ProductUpdateRequest request) {

    // ...
}
```

This is a fragment; `ProductUpdateRequest` must be defined in the project. Spring MVC reads JSON via `HttpMessageConverter`, usually Jackson, **not** through `FormContentFilter` or `_method`.

If an endpoint accepts only JSON, do not enable form parsing/hidden overrides just to “make sure requests work.” Select the right converter, validation, and API contract for JSON.

### 11.4. Garbled Response Text

If input is correct but output is garbled, inspect the response `Content-Type` charset, the converter writing the body (String converter, Thymeleaf, JSP, Jackson), Servlet response encoding, and HTML/browser interpretation. `force-response=true` applies only in context and before the response is committed; it cannot fix bytes already written incorrectly by other code.

## 12. Common Errors and How to Find the Root Cause

| Symptom | Likely Cause | How to Verify |
| --- | --- | --- |
| `Phở` becomes garbled characters | `CharacterEncodingFilter` ran too late, wrong force policy, or mismatched request headers/bytes | Log charset before `getParameter` and inspect raw body bytes with a real client |
| POST form reads fine, PUT form-urlencoded misses `@RequestParam` | `FormContentFilter` missing or wrong media type | Check `spring.mvc.formcontent.filter.enabled` and content type |
| POST `_method=DELETE` returns 405 | Hidden filter disabled, field missing/misnamed, URL unmapped, or method not allowed | Enable property for your Boot version, test with real request |
| POST hidden DELETE hits `@PostMapping` by mistake | Method wrapper did not run before MVC | Check registration order and chain |
| POST `_method=PATCH` returns 415 | PATCH handler `consumes` does not match request body media type | Verify `Content-Type` is form-urlencoded and check route |
| Multipart hidden method fails | `_method` param not available when filter runs | Check multipart resolution before hidden filter and container |
| Same filter runs twice | Both auto-registration and manual registration active | Inspect registrations and bean names |
| Security blocks request unexpectedly | Security saw method in a different phase than MVC, or missing auth/CSRF | Check order, method-based matchers, and CSRF |
| Body lost after logging filter | A filter read `ServletInputStream` before the primary consumer | Design a controlled caching wrapper |
| Form data garbled despite UTF-8 charset | HTML/client actually sent another encoding or decoded too early | Check raw bytes/headers and request charset |
| Fails only on WAR deployment | Filter ordering/config differs from embedded container | Inspect `web.xml`/actual Servlet registrations |
| MockMvc tests pass, production fails | Test did not replicate container filter registration | Add `RANDOM_PORT` integration tests |
| Hidden GET/HEAD does not change method | `HiddenHttpMethodFilter` inspects POST only | Use native methods or redesign API |
| `_method=TRACE` fails to select TRACE handler | Filter supports only PUT/DELETE/PATCH | Do not rely on overriding arbitrary methods |

**Follow this diagnostic order:** raw HTTP request → filter registrations/URL/dispatcher mappings → encoding/filter order → wrapped method/params → Spring MVC handler mapping → binding/validation → response body/media type.

For sensitive data such as passwords, tokens, session IDs, and personal information, never turn on raw form body logging just to debug.

## 13. Choosing Filter Scope and Operational Cost

These three filters extend `OncePerRequestFilter`, yet “once” does not mean strictly once across the entire application lifecycle or across all async/error dispatches. Each Servlet request/dispatch has its own handling. When a filter maps multiple dispatcher types, account for the base class's async/error skipping rules rather than assuming every dispatch re-parses bodies or overrides methods.

Under concurrency:

- Servlet filters are typically **singleton instances** in the container serving many requests across many threads.
- Never store mutable request-specific data in fields of the filter instance.
- If using request attributes/ThreadLocal/MDC to observe methods before/after override, clean up in `finally` to prevent leaking data to subsequent requests.
- Never mutate encoding mid-request at runtime via shared mutable filter config.
- Avoid reading/buffering form bodies multiple times; enforce request size limits at the Servlet/container level and protect file uploads separately.

Regarding performance: encoding and method overrides are generally lightweight, whereas form body parsing requires reading and processing data. For apps handling large payloads, distinguish form bodies from raw JSON, set size limits, and measure impact instead of enabling broad custom wrappers.

## 14. Boot 2, Boot 3, and Boot 4: Avoid Wrong Packages/Properties

| Platform | Servlet Imports | Spring Filters | Configuration to Check |
| --- | --- | --- | --- |
| Spring Framework 5.x + Boot 2.x | `javax.servlet.*` | `CharacterEncodingFilter`, `FormContentFilter`, `HiddenHttpMethodFilter` in `org.springframework.web.filter` | Properties for the exact Boot 2 version; many versions use `server.servlet.encoding.*` and `spring.mvc.*.filter.enabled` |
| Spring Framework 6.x + Boot 3.x | **`jakarta.servlet.*`** | Core filter classes in the same Spring package; Boot 3.5 auto-configures as in Section 6 | `server.servlet.encoding.*`, `spring.mvc.formcontent.filter.enabled`, `spring.mvc.hiddenmethod.filter.enabled` |
| Spring Framework 7.x + Boot 4.x | **`jakarta.servlet.*`** | Servlet Filters remain the right web layer, though Boot 4 auto-config modules/registrations change | Encoding moved to **`spring.servlet.encoding.*`**; check webmvc auto-config metadata when looking up form/hidden properties |

**Note an actual Boot 4 change:** `server.servlet.encoding.mapping.*` may still apply to the **embedded Servlet container's** locale-to-charset mapping, but the properties configuring `CharacterEncodingFilter` moved to `spring.servlet.encoding.charset` / `spring.servlet.encoding.force-*`. Therefore, read the **Boot 4** “Common Application Properties” reference directly; do not copy `server.servlet.encoding.charset` verbatim from Boot 3 and assume the new encoding setting took effect.

**Boot 4** example illustrating only the encoding namespace:

```properties
spring.servlet.encoding.charset=UTF-8
spring.servlet.encoding.force-request=true
```

This is **not** a complete Boot 4 configuration for the demo project; webmvc starters, tests, and other auto-configs must follow the Spring Boot 4 BOM. Do not mix `javax.servlet.*` imports from old tutorials into Boot 3/4.

### When Running on an External Servlet Container

For external WAR deployments, filters may be registered via `web.xml`, Servlet annotations, `WebApplicationInitializer`, or container-specific config. Registration order and dispatcher mappings may differ from embedded Boot. Verify empirically rather than assuming Boot properties or `FilterRegistrationBean#setOrder` are always the sole source controlling every Servlet filter.

## 15. Practice Checklist

- [ ] Confirmed whether requests are form-urlencoded, multipart, or JSON; avoided applying a filter to the wrong data type.
- [ ] `CharacterEncodingFilter` runs before the first component that reads/parses form parameters.
- [ ] Client/server charsets align; UTF-8 is not forced if the contract legitimately allows other encodings.
- [ ] `FormContentFilter` enabled if `@RequestParam`/`@ModelAttribute` must bind from PUT/PATCH/DELETE form bodies.
- [ ] `HiddenHttpMethodFilter` enabled only when clients use HTML POST + `_method`; values restricted to PUT/PATCH/DELETE.
- [ ] For multipart POST, `_method` is readable before the MVC handler; tested on the target container.
- [ ] No duplicate filter registrations via Boot auto-config plus `FilterRegistrationBean`/`@Component`/`web.xml`.
- [ ] Filter registration order, URL patterns, and dispatcher types verified via startup logs.
- [ ] Spring Security authorization/CSRF sees the right method and still protects state-changing requests.
- [ ] `HiddenHttpMethodFilter` is not used to bypass reverse proxy restrictions or HTTP method policies uncontrollably.
- [ ] Body is not read twice when filter, logger, and controller all need the stream.
- [ ] HTTP integration tests on a real container cover Unicode, PUT/PATCH form-urlencoded, and hidden DELETE.
- [ ] Negative tests cover hidden filter disabled, wrong media type, missing required fields, and unauthorized requests.
- [ ] Never log bodies/hidden fields containing secrets; request sizes are bounded.
- [ ] When upgrading Boot versions, review property namespaces, imports, and filter registrations rather than relying on examples from older major versions.

## 16. Self-Check Exercises

1. A form-urlencoded POST containing `name=Ph%E1%BB%9F` decodes into garbled text, while JSON with the same data succeeds. Analyze the difference between Servlet form parameters and the JSON message converter, as well as `CharacterEncodingFilter`'s position.
2. Why might `@RequestParam String name` in `@PutMapping` have no value on a Servlet container when `FormContentFilter` is disabled, even though the raw body has `name=An`?
3. When an HTML form submits POST with `_method=DELETE`, which HTTP method does the reverse proxy see? Which method does downstream MVC see when `HiddenHttpMethodFilter` is enabled?
4. Given the three filters Encoding, FormContent, and Hidden, why is setting order alone insufficient without also checking URL mappings and dispatcher types?
5. `spring.mvc.hiddenmethod.filter.enabled=true` is set in Boot 3.5, yet POST `_method=DELETE` still returns 405. List at least five causes other than a property typo.
6. If a custom security matcher protects all DELETEs while allowing POST, and the hidden-method filter runs **after** Security, what is the risk? Inspect filter order and redesign.
7. A browser uploads a file via `multipart/form-data` with field `_method=PATCH`. Why might `HiddenHttpMethodFilter` fail to read the field if multipart parsing has not run yet? At which layer should you test?
8. Sending `PUT Content-Type: application/json` to an endpoint with `@RequestBody`. Why is `FormContentFilter` not the solution for JSON parsing errors?
9. In Spring Boot 4, Boot 3's `server.servlet.encoding.charset` is no longer the primary configuration namespace for `CharacterEncodingFilter`. Find the corresponding property and verify it with a Vietnamese text test.
10. Running a controller unit test with MockMvc yields `DELETE:7`, yet an integration test against an embedded container fails. Which differences in filter registration/URL mapping/dispatcher type should you inspect?
11. Design a PATCH test using Java 17 `HttpClient` instead of a request factory lacking PATCH support; prove a real request reaches the controller with a form-urlencoded body.
12. In an app serving only an SPA sending JSON via native PUT/DELETE, which filters are genuinely needed? Explain why unused configuration should be minimized.

## 17. Official References

- [Spring Framework 6.2 — Servlet Filters](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/filters.html): role of filters; Form Data section explains `FormContentFilter` on PUT/PATCH/DELETE.
- [Spring Framework 6.2 — CharacterEncodingFilter API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/filter/CharacterEncodingFilter.html): request/response encoding, force options.
- [Spring Framework 6.2 — FormContentFilter API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/filter/FormContentFilter.html): parsing form-urlencoded bodies and `getParameter*` wrapper.
- [Spring Framework 6.2 — HiddenHttpMethodFilter API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/filter/HiddenHttpMethodFilter.html): `_method`, PUT/PATCH/DELETE, and multipart notes.
- [Spring Framework 6.2 — OncePerRequestFilter API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html): limits of “once” across async/error/nested dispatches.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): defaults for `spring.mvc.formcontent.filter.enabled` and `spring.mvc.hiddenmethod.filter.enabled`, encoding properties.
- [Spring Boot 3.5 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): auto-registration/order and character encoding.
- [Spring Boot 4.0 — Common Application Properties](https://docs.spring.io/spring-boot/4.0/appendix/application-properties/index.html): `spring.servlet.encoding.*` namespace and Boot 4 properties.
- [Spring Framework — MultipartFilter API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/multipart/support/MultipartFilter.html): filter-based multipart resolution and interaction with `HiddenHttpMethodFilter`.
- [Jakarta Servlet Specification 6.0](https://jakarta.ee/specifications/servlet/6.0/): Servlet request parameters, filters, dispatcher types, and form processing.
