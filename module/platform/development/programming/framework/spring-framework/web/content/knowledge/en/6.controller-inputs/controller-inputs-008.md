# HttpServletRequest, HttpServletResponse, Principal, and Locale in Spring MVC Method Signatures

> **Context:** Servlet-based Spring Web MVC with Java 17+ and Spring Boot 3.x. This lesson focuses on **controller method arguments**: receiving the request object, response object, authenticated user identity, and active language/region directly. The examples use `jakarta.servlet.*` packages compatible with Spring Framework 6+; Spring 5 and earlier projects use `javax.servlet.*`.

## 1. Why place these four types in controller parameters?

Spring MVC lets a handler retrieve request data at two levels:

- **Declarative level:** `@PathVariable`, `@RequestParam`, `@RequestHeader`, `@CookieValue`, `@RequestBody`, etc. Spring passes only the exact data the method needs.
- **Request/response context level:** Spring can pass `HttpServletRequest`, `HttpServletResponse`, `Principal`, and `Locale` directly into the **method signature** so the method can access broader capabilities or contextual information.

Core syntax example:

```java
@GetMapping("/context")
public String context(
        HttpServletRequest request,
        HttpServletResponse response,
        Principal principal,
        Locale locale) {
    response.setHeader("X-Handler", "context");
    String user = principal == null ? "anonymous" : principal.getName();
    return request.getMethod() + " / " + user
            + " / " + locale.toLanguageTag();
}
```

This is an **illustrative method snippet** to place inside a controller with proper imports. Spring resolves the data sources automatically and supplies the corresponding arguments when invoking the handler; **you do not need `@RequestParam`, `@Autowired`, or `new` to instantiate these objects**.

| Parameter type | Java import | Primary role | Where value/object comes from |
| --- | --- | --- | --- |
| `HttpServletRequest` | `jakarta.servlet.http.HttpServletRequest` | Inspect method, URI, headers, cookies, parameters, attributes, and session for the HTTP request | Servlet container and request processing chain |
| `HttpServletResponse` | `jakarta.servlet.http.HttpServletResponse` | Control HTTP response status, headers, content type, cookies, and output | Servlet container |
| `Principal` | `java.security.Principal` | Identity of the user verified by an authentication mechanism | Request principal supplied by container/security filter |
| `Locale` | `java.util.Locale` | Language/region resolved for the request | Spring MVC's `LocaleResolver`/`LocaleContextResolver` |

**Distinction:** `HttpServletRequest` and `HttpServletResponse` are mutable objects tied to HTTP I/O; `Principal` and `Locale` are contextual data determined by infrastructure. Use these parameters in standard synchronous controllers; do not store request/response references for reuse across multiple requests.

## 2. `HttpServletRequest`: reading the current HTTP context

`HttpServletRequest` extends `ServletRequest`, providing a lower-level API than data-binding annotations. Common methods:

| Method | Meaning | Example |
| --- | --- | --- |
| `getMethod()` | HTTP method | `GET`, `POST` |
| `getRequestURI()` | URI path per Servlet container, typically including context path, excluding query string | `/shop/api/orders/42` |
| `getContextPath()` | Application context path | `/shop` or empty string |
| `getQueryString()` | Part after `?`, or `null` | `sort=asc&page=2` |
| `getHeader("X-Request-Id")` | Read header, or `null` if absent | `abc-123` |
| `getParameter("page")` | Single request parameter, typically from query/form data | `2` |
| `getCookies()` | Cookies sent by client, may be `null` | `Cookie[]` |
| `getAttribute("key")` | Attribute placed on request by filter/interceptor/servlet | `Object` or `null` |
| `getSession(false)` | Existing session if present, **does not create a new session** | `HttpSession` or `null` |
| `getUserPrincipal()` | Principal per Servlet contract | `Principal` or `null` |
| `getRemoteAddr()` | Address of peer connected to container | May be a proxy, not necessarily end-user's IP |

Example reading header and query:

```java
@GetMapping("/inspect")
public String inspect(HttpServletRequest request) {
    String requestId = request.getHeader("X-Request-Id");
    String page = request.getParameter("page");

    return "method=" + request.getMethod()
            + ", uri=" + request.getRequestURI()
            + ", page=" + page
            + ", requestId=" + requestId;
}
```

With `GET /inspect?page=2` and header `X-Request-Id: abc-123`, the body is `method=GET, uri=/inspect, page=2, requestId=abc-123` (assuming the app runs at an empty context path).

### 2.1. When to use `HttpServletRequest`, when to use annotations?

If you only need a single value, declare it narrowly:

```java
@GetMapping("/products")
public String list(
        @RequestParam(defaultValue = "1") int page,
        @RequestHeader(name = "X-Request-Id", required = false)
        String requestId) {
    return "page=" + page + ", requestId=" + requestId;
}
```

The declaration above automatically converts `page` to `int` and clearly documents input requirements. `HttpServletRequest` is appropriate when you need multiple Servlet properties, request details not conveniently covered by annotations, request attributes set by filters, or Servlet API integration.

Stream note: `getInputStream()` and `getReader()` read the **raw body**. Do not read the body via `HttpServletRequest` and expect `@RequestBody` to read it again; streams are normally single-read unless wrapped appropriately. Likewise, `getSession()` can create a new session, whereas `getSession(false)` does not. Never store `HttpServletRequest` in a singleton field or retain it beyond the request lifecycle.

### 2.2. Headers, client address, and trustworthiness

Header, query, cookie, and path data can all be influenced by clients or proxies. For instance, `X-Forwarded-For` is a header that **can be spoofed** if reverse proxies are not configured to validate and normalize it properly; `getRemoteAddr()` may return the proxy's IP. Never use either alone as the sole basis for access control. Validate/bound input sizes, and avoid injecting arbitrary header content into HTML, sensitive logs, or filenames.

## 3. `HttpServletResponse`: controlling the response

Spring normally generates HTTP responses via `@ResponseBody`, `@RestController`, `ResponseEntity`, or view rendering. When a controller accepts `HttpServletResponse`, it can manipulate the response directly:

```java
@GetMapping("/custom")
public void custom(HttpServletResponse response) throws IOException {
    response.setStatus(HttpServletResponse.SC_ACCEPTED); // 202
    response.setContentType("text/plain;charset=UTF-8");
    response.setHeader("Cache-Control", "no-store");
    response.getWriter().write("accepted\n");
}
```

This example is a **`void`-returning handler**: the method writes the body itself. When the HTTP response is not altered by middleware, the expected response has status 202, `Content-Type: text/plain;charset=UTF-8`, `Cache-Control: no-store`, and body `accepted` followed by a newline. Import `java.io.IOException` and `jakarta.servlet.http.HttpServletResponse`.

Common operation groups:

| API | Meaning | Notes |
| --- | --- | --- |
| `setStatus(201)` | Set HTTP status | Sets code only; does not write a body |
| `setHeader("X-Test", "1")` | Set/replace header value | `addHeader` adds another value for the same name |
| `setContentType("application/json")` | Response content type | Set charset before obtaining writer if needed |
| `setCharacterEncoding("UTF-8")` | Charset for text content | Should be called before `getWriter()` |
| `addCookie(cookie)` | Send `Set-Cookie` | Choose `HttpOnly`, `Secure`, `SameSite` suitable for the app |
| `getWriter()` | Write character content | For text; manually written JSON must be properly formatted/escaped |
| `getOutputStream()` | Write bytes, e.g., files | Do not mix with `getWriter()` on the same response |
| `sendError(404)` | Send error via container mechanism | May trigger container error handling |
| `sendRedirect("/login")` | Redirect response | Be careful with client-supplied URLs |
| `isCommitted()` | Check whether response is committed | After commit, status/headers usually cannot be changed |

**Order matters greatly:** set status, content type, charset, and headers **before** writing the body or flushing the buffer. Once a response is committed, header/status changes may have no effect. Do not both call `response.getWriter().write(...)` directly and return a body for Spring to convert via `HttpMessageConverter` in the same handler; doing so risks double writes, converter conflicts, or content-type mismatches.

### 3.1. When should you use `ResponseEntity`?

For typical REST APIs, `ResponseEntity` is cleaner and easier to test:

```java
@GetMapping("/created")
public ResponseEntity<String> created() {
    return ResponseEntity.status(201)
            .header("X-Source", "mvc")
            .contentType(MediaType.TEXT_PLAIN)
            .body("created");
}
```

The example above imports `org.springframework.http.ResponseEntity` and `org.springframework.http.MediaType`; it returns status 201, header `X-Source: mvc`, and text body `created`. When you **do not strictly need the Servlet API**, this is usually the right choice for returning status/headers/body. `HttpServletResponse` remains valuable for streaming, cookies, Servlet library integration, or low-level HTTP control.

## 4. `Principal`: receiving the authenticated identity

`java.security.Principal` is a simple interface with `String getName()`. Spring MVC resolves an argument of this type from the request principal (`HttpServletRequest#getUserPrincipal()`). `Principal` reflects the identity provided by the authentication layer; it **does not trigger login**, verify passwords, or prove that the user is authorized to access every resource.

```java
@GetMapping("/me")
public String me(Principal principal) {
    return principal == null
            ? "No authenticated principal"
            : "Hello, " + principal.getName();
}
```

On requests **without an authenticated principal**, the argument may be `null`; the method above handles that safely. When the container or Spring Security provides a request principal, `principal.getName()` retrieves that identity's name. Never assume every request always has a `Principal`, especially on public endpoints.

### 4.1. `Principal` vs Spring Security `Authentication` / `@AuthenticationPrincipal`

- `Principal` is a standard Java interface, guaranteeing only `getName()`.
- With Spring Security, `Authentication` implements `Principal` and adds authorities/credentials/details/authentication state. The concrete object attached to the request depends on security integration.
- `@AuthenticationPrincipal` is a Spring Security-specific annotation that extracts **`Authentication.getPrincipal()`**, typically a `UserDetails` or custom principal; this differs from declaring a plain `Principal` argument.

Illustrative example for **an application with Spring Security installed and configured**:

```java
// Standalone method example, only use when Spring Security is integrated.
@GetMapping("/username")
public String username(@AuthenticationPrincipal UserDetails currentUser) {
    return currentUser == null ? "anonymous" : currentUser.getUsername();
}
```

Requires importing `org.springframework.security.core.annotation.AuthenticationPrincipal` and `org.springframework.security.core.userdetails.UserDetails`. This example only works when the principal is genuinely a `UserDetails`; with JWT/OAuth2/other custom principals, declare the matching type. Do not assume `Principal`, `Authentication`, and `UserDetails` are always the same object.

**Security:** the username in `Principal` is only an identifier. Enforce access control through security policies (request authorization/method security, ownership checks), not by comparing strings taken from a caller-supplied `X-User` header or query parameter.

## 5. `Locale`: request language and region

`java.util.Locale` describes **language and country/region** conventions for a request, such as `vi-VN`, `en-US`, or `fr-FR`. Spring MVC resolves `Locale` using the configured `LocaleResolver` or `LocaleContextResolver`. The default resolver typically inspects the HTTP `Accept-Language` header; however, applications can configure cookie, session, or custom resolvers, so the result **does not strictly have to match the header**.

```java
@GetMapping("/language")
public String language(Locale locale) {
    return "locale=" + locale.toLanguageTag();
}
```

With an `Accept-Language`-based configuration and header `Accept-Language: vi-VN,vi;q=0.9`, the body is typically `locale=vi-VN`.

Important distinctions:

| Concept | Example | Meaning |
| --- | --- | --- |
| `Locale` | `vi-VN` | Language/region for formatting numbers, dates, and text |
| `TimeZone` / `ZoneId` | `Asia/Ho_Chi_Minh` | Time zone rules, daylight saving time, and local time calculation |
| `Accept-Language` | `vi-VN,vi;q=0.9,en;q=0.7` | Language preference sent by client, not proof of geography |

**Locale is not TimeZone.** Do not infer time zone or physical location solely from `vi-VN`. For multilingual text, use `MessageSource` and message bundles; for numbers/dates, use appropriate formatting APIs with the resolved locale. For timestamps, use an independent `ZoneId` determined by application policy or user preference.

If using `AcceptHeaderLocaleResolver`, do not expect changing locale via `LocaleChangeInterceptor` to work: that resolver reads the HTTP header and generally does not support `setLocale` to mutate locale server-side. To switch locale via cookie or session, configure a resolver capable of persisting locale choices accordingly.

## 6. Complete runnable example: using all four parameters

Create a Spring Boot **3.x**, Java **17+** project with the **Spring Web** dependency using [Spring Initializr](https://start.spring.io/). This example **does not install Spring Security**, since the goal is to demonstrate a public request with an absent `Principal`. Replace `src/main/java/com/example/demo/DemoApplication.java` with:

```java
package com.example.demo;

import java.io.IOException;
import java.security.Principal;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@RestController
@RequestMapping("/api/context")
class ContextController {

    @GetMapping("/inspect")
    public Map<String, String> inspect(
            HttpServletRequest request,
            Principal principal,
            Locale locale) {

        Map<String, String> result = new LinkedHashMap<>();
        result.put("method", request.getMethod());
        result.put("uri", request.getRequestURI());
        result.put("locale", locale.toLanguageTag());
        result.put("user", principal == null
                ? "anonymous"
                : principal.getName());
        return result;
    }

    @GetMapping("/manual")
    public void manual(
            HttpServletRequest request,
            HttpServletResponse response,
            Principal principal,
            Locale locale) throws IOException {

        String user = principal == null
                ? "anonymous"
                : principal.getName();

        response.setStatus(HttpServletResponse.SC_OK);
        response.setContentType("text/plain;charset=UTF-8");
        response.setHeader("Cache-Control", "no-store");

        response.getWriter().write(
                "method=" + request.getMethod() + "\n"
                + "locale=" + locale.toLanguageTag() + "\n"
                + "user=" + user + "\n");
    }

    @GetMapping("/entity")
    public ResponseEntity<String> entity(Locale locale) {
        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .header("X-Language", locale.getLanguage())
                .body("locale=" + locale.toLanguageTag());
    }
}
```

Role of each endpoint:

- `GET /api/context/inspect` accepts request + principal + locale and **lets Spring automatically serialize `Map` to JSON**.
- `GET /api/context/manual` includes **all four parameter types**; the handler sets status/headers itself and writes text directly via `HttpServletResponse`, so the method returns `void`.
- `GET /api/context/entity` provides a contrast: using `ResponseEntity` to describe a response without touching `HttpServletResponse`.

Run from the project directory:

```bash
# Linux / macOS
./mvnw spring-boot:run

# Windows PowerShell / Command Prompt
mvnw.cmd spring-boot:run
```

Use cURL to test. The `-i` flag displays HTTP status/headers too. In the first command, `-s` only suppresses the progress bar:

```bash
curl -s -H 'Accept-Language: vi-VN,vi;q=0.9' \
  http://localhost:8080/api/context/inspect
```

With Spring Web without security and the request-header-based locale resolver, the expected JSON body (fields in insertion order) is:

```json
{"method":"GET","uri":"/api/context/inspect","locale":"vi-VN","user":"anonymous"}
```

Next:

```bash
curl -i -H 'Accept-Language: vi-VN' \
  http://localhost:8080/api/context/manual
```

The response includes HTTP status `200 OK`, header `Cache-Control: no-store`, `Content-Type: text/plain;charset=UTF-8`, and the **exact body**:

```text
method=GET
locale=vi-VN
user=anonymous
```

There is a trailing newline in the body due to `"\n"`. Other headers (such as `Date`, `Connection`) depend on the container. The command above uses POSIX-style line continuation; in PowerShell you can write the entire cURL command on one line with `curl.exe -i -H "Accept-Language: vi-VN" "http://localhost:8080/api/context/manual"`.

Finally:

```bash
curl -i -H 'Accept-Language: en-US' \
  http://localhost:8080/api/context/entity
```

Expected body is `locale=en-US`, header `X-Language: en`. If uncustomized Spring Security is added, endpoints may require login and the `Principal` result will also depend on security configuration; in that case do not expect `anonymous` as a guaranteed output.

## 7. By what mechanism does Spring resolve these arguments?

1. The Servlet container creates `HttpServletRequest`/`HttpServletResponse` for the HTTP request; the filter chain may wrap, attach attributes, or authenticate the request.
2. `DispatcherServlet` invokes the handler mapping system to select the matching controller method.
3. `RequestMappingHandlerAdapter` coordinates `HandlerMethodArgumentResolver`s to resolve parameters based on **type or annotation**.
4. The Servlet request/response resolver supplies the Servlet objects; the `Principal` resolver retrieves the identity associated with the request; the `Locale` resolver retrieves the active locale from the configured resolver.
5. The controller method is invoked. If it returns a regular Java object from `@RestController`, Spring may use a message converter to build the body. If the method writes directly to `HttpServletResponse` and returns `void`, the HTTP response is written directly.

Key takeaway: **Spring injects values per HTTP request at handler invocation time**. You do not put `@Autowired` on method parameters. The `Principal` argument can be empty when unauthenticated; `HttpServletRequest` and `HttpServletResponse` are current-request objects, not shared singletons across all requests.

### 7.1. Do the four parameters need to be declared in a specific order?

No. Each argument is resolved independently by its type/annotation, provided the method signature is valid. Both signatures below express the exact same intent:

```java
public String show(HttpServletRequest request, Locale locale, Principal principal) { /* ... */ }

public String show(Locale locale, Principal principal, HttpServletRequest request) { /* ... */ }
```

**These two lines are only a signature comparison example, not two complete methods to copy into the same controller**; parameter position does not change the underlying source. However, keep a consistent, readable order and avoid passing entire request/response objects when you only need a single field.

## 8. Common errors and how to fix them

| Symptom | Cause | How to fix |
| --- | --- | --- |
| `package javax.servlet.http does not exist` on Spring Boot 3.x | Spring Framework 6 uses the Jakarta namespace | Change imports to `jakarta.servlet.http.*` |
| `NullPointerException` at `principal.getName()` | Anonymous endpoint or missing principal | Handle `principal == null`; configure authentication if API requires a user |
| `Locale` does not change with query `?lang=fr` | Default locale resolver does not read that query parameter | Configure an appropriate resolver/interceptor or send `Accept-Language` |
| `Accept-Language: vi-VN` but different locale returned | App has a custom resolver, supported locale list, or fallback | Check `LocaleResolver`, supported locales config, and the actual received request |
| Unexpected response headers/status returned | Response already committed or modified by filter/container | Set status/headers before writing/flushing; inspect filters |
| `IllegalStateException` when writing body | Calling both `getWriter()` and `getOutputStream()` on one response | Choose exactly one way to write the body |
| Encoding corruption in JSON/text | Setting charset after obtaining writer/writing body | Set `Content-Type` and encoding before `getWriter()` |
| Double output or corrupted response | Writing directly to response while also returning a body for converters | Pick one strategy: `void` + direct write, or `ResponseEntity`/body converter |
| Incorrect client IP | App sits behind a reverse proxy | Rely on trusted proxy configuration; avoid trusting self-declared headers |
| Controller reads body but `@RequestBody` is empty | Request stream was already consumed | Read body only once or use a caching wrapper properly |

### 8.1. Avoiding ambiguity when mixing mechanisms

- `@RequestHeader("Accept-Language") String raw` returns the raw header string sent by the client; `Locale locale` returns the object resolved by the locale resolver. The two values are not synonymous.
- `@RequestParam("user") String user` is client-supplied input; `Principal principal` is established by the authentication mechanism. Never substitute a request parameter for `Principal` in security decisions.
- `HttpServletRequest#getUserPrincipal()` is the manual Servlet API equivalent of obtaining the principal. Declaring `Principal` directly in the signature expresses intent more clearly when you only need the username.
- `HttpServletResponse#setStatus(404)` only sets the status; `ResponseEntity.notFound().build()` is the standard REST way to declare a response; `sendError(404)` can trigger container error handling. Choose according to intent.
- `Locale` is for display conventions and internationalization, not an authorization or user-identification mechanism.

## 9. Self-check questions

**Question 1.** Why does a controller not need `@Autowired` for `HttpServletRequest`?

**Answer:** In Spring MVC, the `HandlerMethodArgumentResolver` system has built-in support for supplying the request object as a handler method argument.

**Question 2.** An unauthenticated request reaches a controller with `Principal principal`. Should you call `principal.getName()` immediately?

**Answer:** No. `Principal` can be `null`; check first and protect the route with security if login is required.

**Question 3.** Does `Accept-Language: fr-FR` always guarantee `locale.toLanguageTag()` returns `fr-FR`?

**Answer:** No. The application's resolver, supported locales list, and fallback rules determine the locale; the header is only one input source.

**Question 4.** To return status 201 + a `Location` header + a JSON body, what should you use in a REST API?

**Answer:** Usually choose `ResponseEntity` to return status, headers, and body clearly with minimal direct manipulation of the Servlet response.

**Question 5.** Why should you call `response.setContentType("text/plain;charset=UTF-8")` before `getWriter()`?

**Answer:** The Servlet response needs to determine content type and character encoding before opening the writer or writing the body, avoiding unexpected charsets or inability to modify headers after commit.

## 10. Official references

- [Spring Framework — MVC Method Arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html): list of supported arguments, including `ServletRequest`, `ServletResponse`, `Principal`, and `Locale`.
- [Spring Framework — Return Values](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/return-types.html): `void`, `ResponseEntity`, and how Spring handles method return values.
- [Spring Framework — Locale Resolution](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/localeresolver.html): `LocaleResolver`, `AcceptHeaderLocaleResolver`, and other resolvers.
- [Spring Framework — ResponseEntity](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html): controlling status/headers/body in Spring MVC.
- [Spring Security — Spring MVC Integration](https://docs.spring.io/spring-security/reference/servlet/integrations/mvc.html): distinguishing `Principal` and `@AuthenticationPrincipal`.
- [Jakarta Servlet — HttpServletRequest / HttpServletResponse](https://jakarta.ee/specifications/servlet/): container-level HTTP request/response APIs.

**Key takeaway:** `HttpServletRequest` reads request context; `HttpServletResponse` gives direct response control; `Principal` provides the authenticated identity if present; `Locale` represents the request's language/region conventions. Spring MVC resolves all four parameters in handler methods automatically, while access control and language selection depend on their respective configurations.
