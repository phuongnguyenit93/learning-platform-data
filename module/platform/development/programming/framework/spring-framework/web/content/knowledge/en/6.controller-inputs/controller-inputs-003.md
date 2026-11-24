# @RequestHeader and @CookieValue in Spring MVC

## Lesson objectives

After this lesson, you will be able to read and convert HTTP request headers using `@RequestHeader`; read cookies from a request using `@CookieValue`; handle missing values, default values, and type conversion errors; choose the right way to read one or multiple headers; and write and test Spring MVC controllers without confusing headers/cookies with query parameters or the request body.

Scope: **Spring MVC (Servlet stack)**, Java 17+, examples use Spring Boot 3.x and the `jakarta.servlet` package. Spring WebFlux also has these two annotations, but its request-handling mechanism belongs to the reactive stack and is not the focus here.

## 1. Where do headers and cookies appear in HTTP?

A request can carry metadata in **headers**, cookies in the special `Cookie` header, URL data in the query string, and submitted payload data in the body:

~~~http
GET /api/inspect?source=mobile HTTP/1.1
Host: localhost:8080
X-Request-Id: req-42
X-Retry-Count: 3
Accept-Language: vi-VN
Cookie: theme=dark; visitCount=7
~~~

- `@RequestHeader("X-Request-Id")` reads the `X-Request-Id` header (value `req-42`).
- `@CookieValue("theme")` reads the **cookie named `theme`** (value `dark`) from the request.
- `@RequestParam("source")` reads the query parameter `source=mobile`; that is a different mechanism.
- `@RequestBody` reads the body and is not used to read headers or cookies.

**Key distinction:** `Cookie` is the HTTP header containing the list of cookies, whereas `@CookieValue` parses it to extract a **cookie by name**. The `Set-Cookie` header belongs to the **response** when the server asks the browser to store a cookie; it is not how `@CookieValue` reads cookies from a request.

| Criterion | `@RequestHeader` | `@CookieValue` |
| --- | --- | --- |
| Reads from | HTTP request headers | HTTP request cookies |
| Selected by | Header name, e.g., `X-Request-Id` | Cookie name, e.g., `theme` |
| Common types | `String`, `Integer`, `List<String>`, `HttpHeaders` | `String`, `Integer`, `Cookie` |
| Required by default | Yes (`required=true`) | Yes (`required=true`) |
| If missing and no default | Typically returns HTTP 400 | Typically returns HTTP 400 |
| If `defaultValue` is set | Fallback value; no longer required | Fallback value; no longer required |

According to the HTTP protocol, **header names are case-insensitive**; cookie names should use the exact name that was set (avoid arbitrarily changing letter case). Both headers and cookies are client-supplied data and are **not automatically trustworthy**.

## 2. Syntax and binding mechanism

Both annotations are declared on **handler method parameters** (`@GetMapping`, `@PostMapping`, etc.):

~~~java
@GetMapping("/example")
public String example(
        @RequestHeader("X-Request-Id") String requestId,
        @CookieValue("theme") String theme) {
    return requestId + ":" + theme;
}
~~~

Spring MVC resolves the handler by URL and HTTP method, after which argument resolvers read the corresponding header or cookie and bind it to the parameter. If the parameter is `Integer`, `Long`, an enum, or another type supported by the conversion system, Spring applies **type conversion**. This is not JSON deserialization: reading these two annotations does not require an `HttpMessageConverter` or `@RequestBody`.

The main attributes apply to **both**:

~~~java
@RequestHeader(name = "X-Request-Id", required = false)
@RequestHeader(value = "X-Request-Id", defaultValue = "unknown")
@CookieValue(name = "theme", required = false)
@CookieValue(value = "theme", defaultValue = "light")
~~~

- `name` and `value` are two ways to specify the same name; the shorthand `@RequestHeader("X-Request-Id")` is equivalent to `value = "X-Request-Id"`.
- `required = true` is the default: if the request is missing required data, Spring MVC raises a binding error and typically returns **400 Bad Request**.
- `required = false` allows omission. For reference types such as `String`, `Integer`, or `Cookie`, the result is usually `null`; you can use `Optional<T>` when appropriate.
- `defaultValue = "light"` provides a fallback when missing **or empty**, and implicitly sets `required = false`. The default string must also be convertible to the target type when type conversion applies.
- For optional values, avoid primitive types like `int` if `null` could be returned; prefer `Integer`, `Optional<Integer>`, or set a `defaultValue`.

## 3. Runnable Spring Boot MVC example

Create a project using Spring Initializr with **Java 17+**, **Maven**, Spring Boot **3.x**, and the **Spring Web** dependency (which brings in `spring-boot-starter-web`). Use the two files below; if you want to run the tests, add the **Spring Boot Starter Test** dependency.

**`src/main/java/com/example/demo/DemoApplication.java`**

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/demo/HeaderCookieController.java`**

~~~java
package com.example.demo;

import jakarta.servlet.http.Cookie;
import java.util.List;
import org.springframework.http.HttpHeaders;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class HeaderCookieController {

    @GetMapping("/inspect")
    public RequestSnapshot inspect(
            @RequestHeader(name = "X-Request-Id", defaultValue = "anonymous")
            String requestId,
            @RequestHeader(name = "X-Retry-Count", required = false)
            Integer retryCount,
            @CookieValue(name = "theme", defaultValue = "light")
            String theme,
            @CookieValue(name = "visitCount", required = false)
            Integer visitCount) {

        return new RequestSnapshot(requestId, retryCount, theme, visitCount);
    }

    // Required parameters: requests missing the header or cookie will be rejected.
    @GetMapping("/mandatory")
    public String mandatory(
            @RequestHeader("X-Request-Id") String requestId,
            @CookieValue("consent") String consent) {
        return requestId + ":" + consent;
    }

    // Read all headers; getFirst returns only the first value for a name.
    @GetMapping("/trace")
    public String trace(@RequestHeader HttpHeaders headers) {
        String traceId = headers.getFirst("X-Trace-Id");
        return traceId == null ? "none" : traceId;
    }

    // Spring can convert comma-separated header lists.
    @GetMapping("/accept")
    public List<String> accept(
            @RequestHeader(name = "Accept", required = false)
            List<String> acceptedTypes) {
        return acceptedTypes == null ? List.of() : acceptedTypes;
    }

    // When Servlet Cookie object properties are needed, you can accept Cookie.
    @GetMapping("/raw-cookie")
    public String rawCookie(
            @CookieValue(name = "theme", required = false) Cookie cookie) {
        return cookie == null ? "missing" : cookie.getName() + "=" + cookie.getValue();
    }

    public record RequestSnapshot(
            String requestId,
            Integer retryCount,
            String theme,
            Integer visitCount) {}
}
~~~

**How it works:** `/inspect` returns a record that Spring MVC serializes to JSON. `X-Retry-Count` and `visitCount` are converted from HTTP strings to `Integer`; both optional parameters can be `null`. `/mandatory` demonstrates required arguments; `/trace` uses `HttpHeaders`; `/raw-cookie` uses `jakarta.servlet.http.Cookie`.

Run in the project directory:

~~~bash
./mvnw spring-boot:run
~~~

On Windows, you can use `mvnw.cmd spring-boot:run`; if there is no Maven Wrapper, use `mvn spring-boot:run` when Maven is installed.

Send a request with both headers and cookies:

~~~bash
curl -s -H "X-Request-Id: req-42" -H "X-Retry-Count: 3" --cookie "theme=dark; visitCount=7" http://localhost:8080/api/inspect
~~~

**Expected JSON content** (JSON property order does not matter):

~~~json
{"requestId":"req-42","retryCount":3,"theme":"dark","visitCount":7}
~~~

Try omitting all custom headers/cookies defined in the example:

~~~bash
curl -s http://localhost:8080/api/inspect
~~~

With Spring Boot 3's default JSON configuration, the result is equivalent to:

~~~json
{"requestId":"anonymous","retryCount":null,"theme":"light","visitCount":null}
~~~

Two other scenarios to observe:

~~~bash
curl -i http://localhost:8080/api/mandatory
curl -i -H "X-Request-Id: req-42" -H "X-Retry-Count: abc" http://localhost:8080/api/inspect
~~~

The first request is missing required data; the second request cannot convert `abc` to `Integer`. By default, Spring MVC typically returns **HTTP 400** for both. The error JSON body varies by application configuration, so **do not rely on a fixed error body**.

> If using PowerShell on Windows, invoke `curl.exe` for consistent `curl` CLI syntax; in some environments `curl` is a PowerShell alias.

## 4. Reading one header, multiple values, and all headers

### Single header name

~~~java
@GetMapping("/language")
public String language(
        @RequestHeader(name = "Accept-Language", required = false)
        String acceptLanguage) {
    return acceptLanguage == null ? "not specified" : acceptLanguage;
}
~~~

For example, `Accept-Language: vi-VN, en;q=0.8` is read as a string. If your goal is to select a locale via Spring's language negotiation mechanism, `Locale` or `LocaleResolver` is usually more suitable than manually splitting the `Accept-Language` string.

### A header with multiple values

A header can have multiple lines with the same name or represent a comma-separated list. Spring supports `String[]` and `List<String>` when convertible; for example, the `/api/accept` endpoint above can receive:

~~~bash
curl -s -H "Accept: application/json, text/plain" http://localhost:8080/api/accept
~~~

Illustrative list result:

~~~json
["application/json","text/plain"]
~~~

However, **not every HTTP header may be joined or split simply by commas**; individual header syntax can include quotes, parameters, or special rules. For data that needs accurate parsing, use dedicated APIs like `HttpHeaders.getAccept()` instead of manually splitting strings.

### Reading all headers

~~~java
@GetMapping("/header-count")
public int headerCount(@RequestHeader HttpHeaders headers) {
    return headers.size();
}
~~~

With an unnamed `@RequestHeader` parameter, Spring can bind the entire set of headers into `HttpHeaders`, `Map<String, String>`, or `MultiValueMap<String, String>`:

- `Map<String, String>`: represents a single value per name; can lose information if a header has multiple values.
- `MultiValueMap<String, String>`: preserves a list of values per name.
- `HttpHeaders`: a specialized HTTP API providing methods like `getFirst`, `getAccept`, and `getContentType`; usually the clearest choice when multiple headers are needed.

Reading all headers does not mean you should **return or log the entire set**: headers like `Authorization` or `Cookie` can contain secrets.

## 5. Reading cookies and understanding what the server actually receives

For example, the browser sends:

~~~http
Cookie: theme=dark; visitCount=7
~~~

Then `@CookieValue("theme") String theme` reads `dark`, and `@CookieValue("visitCount") Integer visits` reads the number `7`. In Servlet-based Spring MVC, you can also declare a parameter of type `jakarta.servlet.http.Cookie` to read `getName()`, `getValue()`, `getPath()`, etc. However, only attributes actually present in the **request cookie** are reliable to inspect; configuration attributes set when the server sends `Set-Cookie` (such as `HttpOnly`, `Secure`, `SameSite`) **are not sent back in the request's `Cookie` header**.

The server typically issues cookies via the response, for example:

~~~http
HTTP/1.1 200 OK
Set-Cookie: theme=dark; Path=/; HttpOnly; Secure; SameSite=Lax
~~~

On subsequent eligible requests, the client only sends name–value pairs such as `Cookie: theme=dark`. `Secure` requires sending the cookie over a secure connection per browser rules; `HttpOnly` restricts access from JavaScript; `SameSite` affects cookie attachment in cross-site contexts. These attributes must be designed **when setting the cookie**, not configured via `@CookieValue`.

A cookie may be absent because it was never set, has expired, does not match `Domain`/`Path`, was blocked by `SameSite` policy, or lacked browser credentials settings. Do not conclude "Spring failed to read it" before checking the browser's Network tab to verify whether the request actually contains the `Cookie` header.

## 6. Choosing `required`, `defaultValue`, and handling errors

| Scenario | Appropriate declaration | Result |
| --- | --- | --- |
| Required header | `@RequestHeader("X-Request-Id") String id` | Missing → typically 400 |
| Optional header | `@RequestHeader(name="X-Retry-Count", required=false) Integer count` | Missing → `null` |
| Header with fallback | `@RequestHeader(name="X-Source", defaultValue="web") String source` | Missing/empty → `web` |
| Required cookie | `@CookieValue("consent") String consent` | Missing → typically 400 |
| Optional cookie | `@CookieValue(name="theme", required=false) String theme` | Missing → `null` |
| Cookie with fallback | `@CookieValue(name="theme", defaultValue="light") String theme` | Missing/empty → `light` |
| Unconvertible value | `@CookieValue("visitCount") Integer n` receives `abc` | Typically 400 due to conversion error |

Common exceptions in Spring MVC: `MissingRequestHeaderException` and `MissingRequestCookieException` when required data is absent; conversion errors like `MethodArgumentTypeMismatchException` when a string is invalid. You can use `@ControllerAdvice`/`@ExceptionHandler` if the API requires a custom error structure. **Do not turn the default 400 into 200 just to hide client errors.**

If you want a numeric default value, configure `defaultValue = "0"` directly; Spring will convert the string `"0"` to `Integer`. Do not use `required=false int count` because `int` cannot accept `null`.

## 7. Testing with MockMvc

With the `spring-boot-starter-test` dependency in a Spring Boot 3.x project, add **`src/test/java/com/example/demo/HeaderCookieControllerTest.java`**:

~~~java
package com.example.demo;

import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(HeaderCookieController.class)
class HeaderCookieControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void readsHeaderAndCookies() throws Exception {
        mockMvc.perform(get("/api/inspect")
                        .header("X-Request-Id", "req-42")
                        .header("X-Retry-Count", "3")
                        .cookie(new Cookie("theme", "dark"),
                                new Cookie("visitCount", "7")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.requestId").value("req-42"))
                .andExpect(jsonPath("$.retryCount").value(3))
                .andExpect(jsonPath("$.theme").value("dark"))
                .andExpect(jsonPath("$.visitCount").value(7));
    }

    @Test
    void appliesDefaultsWhenMissing() throws Exception {
        mockMvc.perform(get("/api/inspect"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.requestId").value("anonymous"))
                .andExpect(jsonPath("$.theme").value("light"));
    }

    @Test
    void rejectsMissingRequiredValues() throws Exception {
        mockMvc.perform(get("/api/mandatory"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsInvalidNumber() throws Exception {
        mockMvc.perform(get("/api/inspect")
                        .header("X-Retry-Count", "abc"))
                .andExpect(status().isBadRequest());
    }
}
~~~

Run with:

~~~bash
./mvnw test
~~~

`MockMvc` builds simulated requests with headers/cookies and asserts HTTP status and JSON values without starting a real server. Test cases with present values, missing optional values, missing required values, and type conversion failures to avoid confusing **fallback** with **bad request**.

## 8. Security and common implementation mistakes

1. **Do not trust headers/cookies as proof of identity.** Clients can send `X-User-Id` themselves or tamper with a `role=admin` cookie. For authentication/authorization, use Spring Security and `Principal`/`Authentication`; session IDs or tokens must be verified server-side.
2. **Do not log sensitive data.** `Authorization`, session cookies, access tokens, and identifying details should not be printed to logs or returned in real-world responses. Cookies holding sensitive values should consider `HttpOnly`, `Secure`, `SameSite`, and appropriate expiration; `HttpOnly` alone does not eliminate CSRF.
3. **Distinguish incoming cookies from outgoing cookies.** `@CookieValue` reads the request. To set a cookie, use the response `Set-Cookie` (e.g., `ResponseCookie`/HTTP response header), controlling `Path`, `Domain`, `Max-Age`, `Secure`, `HttpOnly`, and `SameSite`.
4. **Do not assume optional headers are always present.** Dereferencing `null` when using `required=false` can cause a `NullPointerException`. Choose appropriate wrappers/`Optional`/defaults.
5. **Do not split every header by commas manually.** Complex headers require standards-compliant parsers; when multi-value support is needed, use `HttpHeaders` or `MultiValueMap` and dedicated APIs.
6. **Do not confuse missing data with malformed data.** `required=false` handles absence; it does not mean `"abc"` is valid for `Integer`. Depending on API requirements, keep 400 and provide clear error messages.
7. **Do not rely on arbitrary reverse proxy headers.** Headers such as `X-Forwarded-For` should only be trusted according to trusted proxy configuration and system policy; they are not inherently the caller's real IP address.
8. **Do not force browsers to send cookies when policy blocks them.** Check HTTPS, domain/path, SameSite, and credentials settings for frontend requests. Inspect the actual request before modifying the controller.

## 9. Quick application checklist

- If you need **HTTP metadata**, use `@RequestHeader`; if you need a **cookie sent by the client**, use `@CookieValue`.
- Specify the exact name, target Java type, whether it is required, and whether a fallback is needed.
- For multiple headers, choose `HttpHeaders` or `MultiValueMap`; do not drop repeated values.
- Test valid, missing, and unconvertible inputs; never use unverified headers/cookies to make authorization decisions.

## Official references

- [Spring Framework — `@RequestHeader`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestheader.html)
- [Spring Framework — `@CookieValue`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/cookievalue.html)
- [Spring Framework — Controller Method Arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html)
