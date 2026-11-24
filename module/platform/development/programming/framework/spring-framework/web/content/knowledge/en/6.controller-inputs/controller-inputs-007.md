# @RequestAttribute, @SessionAttribute, and Pre-Populated Context Data in Spring MVC

## 1. Why can a controller receive data even when the client did not send it directly?

An HTTP request passes through multiple components before executing a controller method: the web server/Servlet container, Servlet Filters, `DispatcherServlet`, `HandlerInterceptor`s, and finally Spring MVC's handler selection and invocation. In steps prior to the controller, the application may have created internal data such as a trace ID, resolved tenant, request metadata, or an object loaded from the session.

Two annotations in **Spring MVC (Servlet stack)** let a controller receive values that **already exist** in the corresponding scope:

- `@RequestAttribute`: reads an attribute from the **current Servlet request**; usually placed earlier via `HttpServletRequest#setAttribute` by a filter, interceptor, or another component.
- `@SessionAttribute`: reads an attribute from the **HTTP session associated with the client**, usually placed via `HttpSession#setAttribute` in a previous request or by session-management logic.

Both are **controller method parameter** annotations; they do not automatically create values, read query parameters, or parse a JSON body. If an attribute is not present yet, missing cases must be handled via `required`.

Example:

```text
Client
  GET /api/context/request
       |
       v
Servlet Filter                request.setAttribute("traceId", "demo-42")
       |
       v
DispatcherServlet
       |
       v
HandlerInterceptor (if any)  may set additional request attributes
       |
       v
@RequestAttribute("traceId") String traceId
       |
       v
Controller: "traceId=demo-42"
```

In another flow, a session may store a `language=vi` preference from a previous request. A new request sends the session-identifying cookie, the server looks up the attribute, and `@SessionAttribute("language")` reads that value. Request attributes and session attributes are independent: **the same key name** does not mean the same value.

## 2. Distinguishing input data sources

| Source | Controller reads via | Where does the value come from? | Typical lifecycle |
| --- | --- | --- | --- |
| Query/form parameter | `@RequestParam("q")` | URL `?q=java` or matching form body | Per request |
| Path variable | `@PathVariable("id")` | Segment captured by URL mapping, e.g., `/users/7` | Per request |
| Header | `@RequestHeader("X-Trace-Id")` | HTTP header sent by client/proxy | Per request |
| Cookie | `@CookieValue("theme")` | Cookie in request | Per request/client |
| JSON body | `@RequestBody Dto` | Payload read by `HttpMessageConverter` | Per request |
| Request attribute | `@RequestAttribute("traceId")` | Object in `ServletRequest#setAttribute`, usually set by server-side component | Per request |
| Session attribute | `@SessionAttribute("language")` | Object in `HttpSession#setAttribute` | Across multiple requests of the same session |
| Model attribute | `@ModelAttribute`, `Model` | Spring MVC model; may be initialized/bound from request | Per MVC flow, depending on model/session setup |
| Servlet context attribute | `ServletContext#getAttribute` | Web application-level state set by server code | Shared at ServletContext level |
| Security principal | `Principal`, `Authentication`, or `@AuthenticationPrincipal` with Spring Security | Identity authenticated by security mechanism | Per established security context |

**Common point of confusion:** `request.getParameter("traceId")` and `request.getAttribute("traceId")` query **two different stores**. Sending `?traceId=evil` does not automatically create a `request` attribute named `traceId`, and a JSON field `{"language":"vi"}` does not automatically become a `session` attribute.

## 3. `@RequestAttribute`: reading attributes of the current request

Syntax:

```java
@GetMapping("/example")
public String handle(
        @RequestAttribute("traceId") String traceId,
        @RequestAttribute(name = "tenant", required = false) String tenant) {
    return traceId + ":" + (tenant == null ? "unknown" : tenant);
}
```

Key parts:

- `value` and `name` are aliases. You should **explicitly specify the name** to avoid depending on compiler configuration retaining parameter names (e.g., `-parameters`).
- `required` defaults to `true`. If no matching attribute exists, Spring throws an exception during parameter resolution, and the controller method is not called. The final HTTP status code depends on the exception handler (typically a binding error becomes 400).
- `required = false` allows absence, usually passing `null` for reference types; `Optional<T>` can also be used.
- The annotation **does not have `defaultValue`** like `@RequestParam`. If a fallback is needed, compute it in the controller or the providing component.
- The attribute name matches the exact name placed on the request; `@RequestAttribute("tenant")` does not read `tenantId` just because the data type matches.
- The retrieved object must match the parameter type or have an appropriate type conversion mechanism. The annotation does not turn JSON or a Map into an arbitrary domain object.

Common places where attributes are set:

```java
// Servlet Filter:
request.setAttribute("traceId", traceId);

// HandlerInterceptor#preHandle:
request.setAttribute("tenant", resolvedTenant);

// Any server-side component sharing the same ServletRequest:
String traceId = (String) request.getAttribute("traceId");
request.removeAttribute("traceId");
```

An attribute can be modified or removed during request processing. It **does not automatically persist** to the next HTTP request. A forward within the Servlet container can share the same request; a redirect creates a new request, so old request attributes do not carry over.

**Do not confuse request attributes with Spring `@RequestScope`:** both relate to request scope, but `@RequestScope` manages Spring bean lifecycles, whereas `@RequestAttribute` reads attributes stored under a key by the Servlet API. Spring does not automatically expose every request-scoped bean as a request attribute of the same name.

## 4. `@SessionAttribute`: reading data stored across requests

Syntax:

```java
@GetMapping("/preferences")
public String preferences(
        @SessionAttribute(name = "language", required = false) String language) {
    return "language=" + (language == null ? "none" : language);
}
```

- `@SessionAttribute("language")` looks up the attribute in the **HTTP session**. It does not read a `language` cookie directly; typically a `JSESSIONID` cookie or another session ID mechanism lets the server identify the session.
- `required` defaults to `true`: a missing session or missing key causes a parameter resolution error. Use `required=false` when the value may not have been set yet.
- `value` and `name` are aliases; declare the name explicitly. There is no `defaultValue` on this annotation.
- `@SessionAttribute` is suited for **reading** session state managed by other components. To **write/remove**, use `HttpSession`, `WebRequest`, or an appropriate session management service.
- Lifespan depends on timeout, invalidation, cookie/session ID, and session backend. It is not durable storage and does not always survive server restarts.
- If two concurrent requests mutate the same object in the session, race conditions can arise; sessions do not inherently guarantee thread safety for mutable objects.

Direct management example:

```java
@PostMapping("/set-language")
public String setLanguage(@RequestParam("language") String language,
                          HttpSession session) {
    session.setAttribute("language", language);
    return "saved";
}

@PostMapping("/clear-language")
public String clearLanguage(HttpSession session) {
    session.removeAttribute("language");
    return "removed";
}
```

These are **illustrative methods** placed in a Spring MVC-configured `@RestController`; they are not a standalone runnable Java program. When a method requests an `HttpSession` argument, the Servlet container may create a session if one does not exist yet. If you only want to check an existing session without creating a new one:

```java
HttpSession existing = request.getSession(false);
if (existing != null) {
    existing.removeAttribute("language");
}
```

The snippet above assumes an `HttpServletRequest request` variable is available. `getSession(false)` returns `null` if the request has no session yet.

## 5. Spring Boot 3.x + Java 17+ application example

The example below demonstrates both a **request attribute supplied by a Filter** and a **session attribute written/read by controllers**. Use a Spring Boot Servlet/MVC project with the `spring-boot-starter-web` dependency. For the tests later, add `spring-boot-starter-test`.

Spring Boot 3.x uses the `jakarta.servlet.*` namespace; if you are on Boot 2.x you will encounter `javax.servlet.*` and must adjust imports for that version.

Create **`src/main/java/demo/web/ContextAttributesApplication.java`**:

```java
package demo.web;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;
import java.io.IOException;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.SessionAttribute;
import org.springframework.web.filter.OncePerRequestFilter;

@SpringBootApplication
public class ContextAttributesApplication {

    public static void main(String[] args) {
        SpringApplication.run(ContextAttributesApplication.class, args);
    }

    @Bean
    OncePerRequestFilter traceAttributeFilter() {
        return new OncePerRequestFilter() {
            @Override
            protected void doFilterInternal(
                    HttpServletRequest request,
                    HttpServletResponse response,
                    FilterChain chain)
                    throws ServletException, IOException {

                String traceId = request.getHeader("X-Trace-Id");
                if (traceId == null || traceId.isBlank()) {
                    traceId = "generated-demo";
                }

                request.setAttribute("traceId", traceId);
                try {
                    chain.doFilter(request, response);
                } finally {
                    request.removeAttribute("traceId");
                }
            }
        };
    }
}

@RestController
class ContextController {

    @GetMapping("/api/context/request")
    String requestContext(@RequestAttribute("traceId") String traceId) {
        return "traceId=" + traceId;
    }

    @GetMapping("/api/context/optional")
    String optionalRequestContext(
            @RequestAttribute(name = "feature", required = false) String feature) {
        return "feature=" + (feature == null ? "none" : feature);
    }

    @PostMapping("/api/context/session")
    String rememberLanguage(@RequestParam("language") String language,
                            HttpSession session) {
        session.setAttribute("language", language);
        return "stored=" + language;
    }

    @GetMapping("/api/context/session")
    String readLanguage(
            @SessionAttribute(name = "language", required = false)
            String language) {
        return "language=" + (language == null ? "none" : language);
    }

    @GetMapping("/api/context/session-required")
    String readRequiredLanguage(@SessionAttribute("language") String language) {
        return "language=" + language;
    }

    @PostMapping("/api/context/session/remove")
    String removeLanguage(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        if (session != null) {
            session.removeAttribute("language");
        }
        return "removed";
    }
}
```

**How it works:**

1. Spring Boot registers the `OncePerRequestFilter` bean into the Servlet filter chain via autoconfiguration; each request dispatch is handled according to filter semantics.
2. The filter reads the `X-Trace-Id` header or uses the sample value `generated-demo`, then sets `request.setAttribute("traceId", ...)`. It calls `chain.doFilter` to continue to Spring MVC.
3. When MVC encounters `@RequestAttribute("traceId")`, Spring retrieves the attribute the filter just set. The controller does not need to read the Servlet API itself.
4. The `finally` block cleans up the attribute after downstream processing completes. This cleanup **does not affect** the value the controller already received when executing earlier.
5. The session POST saves `language`; another GET only reads it back when the client sends the matching session ID. The GET using `required=false` returns `none` when no choice exists yet.
6. `/api/context/session-required` differs from the optional endpoint: if the attribute is missing, argument resolution fails before the method body runs.

The filter above uses a client-supplied header **purely to demonstrate trace data**. Never treat self-declared headers as proof of tenant, user ID, or access permissions. In real systems, IDs issued by trusted infrastructure require clear source controls and logging.

In a Spring Boot 3.x project using Gradle/Groovy, the minimal relevant dependencies (when the project already has the Boot plugin, dependency management, and repositories):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Launch the project via `./gradlew bootRun` (or `./mvnw spring-boot:run` when using Maven). This dependency block is a **build configuration snippet**, not a complete standalone `build.gradle` file.

### Observing with an HTTP client

After starting the application on `localhost:8080`, run in a Bash shell (standard `curl` commands):

```bash
curl -sS -H 'X-Trace-Id: demo-42' http://localhost:8080/api/context/request
curl -sS http://localhost:8080/api/context/request
curl -sS http://localhost:8080/api/context/optional
curl -sS http://localhost:8080/api/context/session
curl -sS -c cookies.txt -X POST -d 'language=vi' http://localhost:8080/api/context/session
curl -sS -b cookies.txt http://localhost:8080/api/context/session
curl -sS -b cookies.txt -X POST http://localhost:8080/api/context/session/remove
curl -sS -b cookies.txt http://localhost:8080/api/context/session
```

Corresponding response bodies, **assuming endpoints are not intercepted by other filters/security**:

```text
traceId=demo-42
traceId=generated-demo
feature=none
language=none
stored=vi
language=vi
removed
language=none
```

`-c cookies.txt` writes cookies from the POST response, and `-b cookies.txt` sends that cookie back so the server identifies the same session. If a subsequent GET is called **without sending the session cookie**, there is no guarantee of reading `language=vi` back. These are illustrative response bodies, not `javac` stdout. Do not commit `cookies.txt` to your repository.

In clients that follow redirects automatically or applications with authentication middleware, use `curl -i` to inspect HTTP status, `Set-Cookie` headers, and returned cookies.

## 6. Setting request attributes with `HandlerInterceptor`

When you need to add data **after Spring MVC has selected a handler** but before the method runs, `HandlerInterceptor#preHandle` is an appropriate extension point. Condensed example:

```java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.servlet.HandlerInterceptor;

class TenantInterceptor implements HandlerInterceptor {
    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {

        String resolvedTenant = "tenant-demo"; // Replace with a trustworthy resolver.
        request.setAttribute("tenant", resolvedTenant);
        return true;
    }
}
```

Register the interceptor in MVC configuration (below is a **configuration class fragment**):

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class MvcInterceptors implements WebMvcConfigurer {
    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new TenantInterceptor())
                .addPathPatterns("/api/tenant/**");
    }
}
```

A controller supported by the interceptor can declare:

```java
@GetMapping("/api/tenant/info")
public String tenantInfo(@RequestAttribute("tenant") String tenant) {
    return "tenant=" + tenant;
}
```

If you assemble these three fragments properly into a project, `GET /api/tenant/info` will receive `tenant-demo`. In real applications, the tenant value must be determined from a trusted source (such as an authenticated principal or verified context); this snippet only illustrates where attributes are set.

Important distinctions:

- **Filter** participates in the Servlet chain and can run before Spring MVC selects a handler; it can apply to unmatched requests, static content, and specific dispatch types depending on configuration.
- **Interceptor** is a Spring MVC component running around the selected handler; it is not equivalent to a Servlet-chain protection layer.
- **MethodArgumentResolver** is the Spring mechanism for injecting values into controller parameters, which both annotations in this lesson rely on via their respective resolvers. If you only need to pass values already stored in request/session, you normally **do not need** to write a custom resolver.

Never place mandatory security logic solely inside an interceptor and assume it protects every URL. Requests that do not pass through the expected MVC handler may bypass that interceptor.

## 7. `@SessionAttribute` vs `@SessionAttributes` (with an "s")

These two similarly named annotations serve very different roles:

| `@SessionAttribute` | `@SessionAttributes` |
| --- | --- |
| Placed on a **method parameter** | Placed on a **controller class** |
| **Reads** an existing HTTP session attribute | Manages **model attributes** of a controller workflow and temporarily stores them in the session |
| Does not create/update attributes itself | Can "promote" matching model attributes into the session |
| `required = true/false` | Configured by `names`/`types`, has no equivalent `required` |
| Suitable for reading user preferences and context lasting beyond one request | Suitable for multi-step forms/workflows |
| Removed manually via `HttpSession#removeAttribute` or management API | Ends the model/session conversation via `SessionStatus#setComplete()` |

Illustrative model/session workflow example (snippets belong in the same controller):

```java
@Controller
@SessionAttributes("draft")
class DraftController {

    @ModelAttribute("draft")
    public Draft draft() {
        return new Draft();
    }

    @PostMapping("/draft/finish")
    public String finish(@ModelAttribute("draft") Draft draft,
                         SessionStatus status) {
        // Process the valid draft and complete the workflow.
        status.setComplete();
        return "redirect:/done";
    }
}
```

Here `Draft` is an application-defined domain type; the example only illustrates MVC flow and is **not a standalone compilable source file**. With `@SessionAttributes`, the actual session storage key may be managed by the framework under controller-model rules, so other code should not depend on that internal key name. `SessionStatus#setComplete()` **does not invalidate the entire HTTP session** and does not erase all other user attributes.

If the requirement is simply to read a key placed into the session by a filter or controller, choose `@SessionAttribute`. If the goal is to carry a model across multiple form steps with a clear lifecycle, `@SessionAttributes` and `SessionStatus` are more appropriate.

## 8. `required`, `Optional`, missing attributes, and common errors

Example declarations:

```java
// Required: missing attribute -> exception when resolving parameter.
@RequestAttribute("correlationId") String id

// Optional: missing -> null.
@RequestAttribute(name = "correlationId", required = false) String id

// Optional as an object wrapper:
@RequestAttribute("correlationId") Optional<String> id

// No HTTP session or missing key -> null allowed:
@SessionAttribute(name = "language", required = false) String language
```

The lines above are **parameter signatures** for comparison, not a valid standalone Java method. For `Optional<String>`, import `java.util.Optional`.

Common issues that arise:

1. **Key mismatch**: the filter sets `request.setAttribute("traceId", ...)` while the controller asks for `@RequestAttribute("requestId")`.
2. **Set too late**: the attribute is added after the controller has already been invoked or only along one interceptor branch.
3. **Wrong scope**: stored in `request` but read from `session`, or stored in session on request A while request B omits the session ID.
4. **Wrong data type**: a domain object or `Integer` was stored, yet the parameter declares an incompatible type; JSON is not implicitly converted into objects.
5. **Missing value with a primitive type**: use a reference type or `Optional<T>` for nullable cases.
6. **Assuming a hardcoded status code**: missing required attributes are typically handled by Spring MVC as binding errors returning 400, but `@ControllerAdvice`, exception resolvers, and security filters can alter the HTTP result. Verify in your application tests.
7. **Data leakage across users**: storing per-user context in a singleton field or static variable while mistaking it for request-scoped. Controllers are singletons by default; per-request data must stay in method arguments/request scope, and session and shared resources must be protected from contention.
8. **Assuming `@RequestAttribute` is client-sent data**: HTTP headers/parameters are not automatically converted into corresponding request attributes by Spring.

## 9. Pre-populated context: when and how to access it?

Spring MVC supports injecting familiar Servlet/Spring types directly into methods, for example:

```java
@GetMapping("/context/details")
public String details(HttpServletRequest request, HttpSession session) {
    Object currentTrace = request.getAttribute("traceId");
    Object language = session.getAttribute("language");
    return String.valueOf(currentTrace) + "/" + String.valueOf(language);
}
```

This is **an illustrative method** inside a controller. Note that an `HttpSession session` parameter can create a session even when your intent is read-only; if you do not want to create one, use `HttpServletRequest request` and call `request.getSession(false)`.

Use explicit parameter annotations (`@RequestAttribute`, `@SessionAttribute`) when only one or two values are needed, because the method signature documents dependencies and is easy to test. Use `HttpServletRequest`, `HttpSession`, or `WebRequest` when you need to read/write multiple attributes, check existence, remove entries, or manage lifecycles.

Several related mechanisms to distinguish:

- `RequestContextHolder` holds `RequestAttributes` bound to the request-executing thread per Spring's mechanism. It is convenient for code deep in the web call stack, but increases hidden coupling; avoid relying on it in services when values can be passed explicitly.
- When offloading work to another thread (e.g., `@Async`, `CompletableFuture`, or an executor), thread-bound context **is not automatically propagated**; avoid reading request/session arbitrarily from worker threads—design proper context propagation and pass only needed data.
- `@RequestScope` and `@SessionScope` manage **scoped Spring beans**, distinct from direct Servlet attribute maps despite sharing similar lifecycle concepts.
- `ServletContext#getAttribute` holds application-level shared data, not per-request or per-user session data; consider concurrency and lifecycle when updating it.
- `SecurityContextHolder` and `@AuthenticationPrincipal` belong to Spring Security when configured; never assume a plain request/session attribute has been authenticated.

Easy-to-remember lifecycle diagram:

```text
Request A ----------------------------------X       (request attribute goes out of scope)
     Session S ===================================X  (exists until timeout/invalidate)
Request B -----------X                           |
Request C -----------------X                     |
ServletContext ====================================== (application-level)
```

These timeline shapes only express **lifecycle relationships**, not specific timeouts. A session can expire between two requests; in multi-node deployments, session storage must be consistent or use an appropriate mechanism (sticky sessions, shared store, or Spring Session when needed).

## 10. Security and correctness in real applications

Request/session attributes make context passing convenient, but are **not automatically trusted sources**:

- Values copied directly from `X-User-Id`, `X-Tenant`, or query parameters without validation can be spoofed. If an attribute governs authorization, first verify the source and bind it to a principal confirmed by Spring Security.
- Do not store passwords, raw tokens, unnecessary PII, or large objects in the session; consider lifetime, serialization, and security policies. Session IDs must be protected; in practice use HTTPS, appropriate `HttpOnly`/`Secure`/`SameSite` cookies, and session fixation protection.
- Do not place a mutable Java map/object in the session and assume concurrent requests can modify it safely. Design immutable values, apply proper synchronization, or update through a consistent storage layer.
- After logout or revocation, clear related state; session invalidation or the authentication/session management system must handle this. Clearing `@SessionAttributes` for a workflow does not equal logging out.
- Do not use request attributes as durable storage or across HTTP redirects; use URLs, flash attributes, sessions, or dedicated stores according to your goal.
- Do not expose stack traces or internal attribute names in production API responses; handle errors under a clear HTTP/API contract.

## 11. Testing with `MockMvc`

In a project with Spring Boot test support, create **`src/test/java/demo/web/ContextAttributesApplicationTests.java`**:

```java
package demo.web;

import jakarta.servlet.http.HttpSession;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ContextAttributesApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void filterProvidesRequestAttribute() throws Exception {
        mvc.perform(get("/api/context/request")
                        .header("X-Trace-Id", "abc-123"))
                .andExpect(status().isOk())
                .andExpect(content().string("traceId=abc-123"));

        mvc.perform(get("/api/context/request")
                        .param("traceId", "value-from-query"))
                .andExpect(status().isOk())
                .andExpect(content().string("traceId=generated-demo"));
    }

    @Test
    void sessionAttributeNeedsTheSameSession() throws Exception {
        MvcResult saved = mvc.perform(post("/api/context/session")
                        .param("language", "vi"))
                .andExpect(status().isOk())
                .andExpect(content().string("stored=vi"))
                .andReturn();

        HttpSession servletSession = saved.getRequest().getSession(false);
        assertNotNull(servletSession);
        MockHttpSession session = (MockHttpSession) servletSession;

        mvc.perform(get("/api/context/session").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("language=vi"));

        mvc.perform(get("/api/context/session"))
                .andExpect(status().isOk())
                .andExpect(content().string("language=none"));

        mvc.perform(post("/api/context/session/remove").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("removed"));

        mvc.perform(get("/api/context/session").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("language=none"));
    }
}
```

Run `./gradlew test` or `./mvnw test`. When the sample app has only Spring MVC and the starters listed above, **both tests are expected to pass**. The first test proves that query parameter `traceId` does not overwrite the request attribute set by the filter. The second test proves that the session persists across requests **when reusing the same `MockHttpSession`**, and that state is cleared when calling the remove endpoint.

**Limitations:** `MockMvc` integration tests use the Spring test environment and do not fully simulate proxies, networks, browser cookie policies, or multi-node clusters. If the project adds Spring Security, CSRF, custom filters, or custom error handling, tests must configure authentication, CSRF, and the filter chain to match the real system.

You can test missing request attributes independently using `MockMvcBuilders.standaloneSetup(new ContextController())` **without registering the filter** and calling `GET /api/context/request`; if `required=true`, the controller will not run. When testing required session attributes, call `/api/context/session-required` with a fresh session or no session and verify the application's HTTP status/error contract.

## 12. Workflow for choosing annotations in a project

1. **Client-supplied data source?** Use `@RequestParam`, `@PathVariable`, `@RequestHeader`, `@CookieValue`, or `@RequestBody` according to the format; do not use `@RequestAttribute` expecting Spring to read HTTP inputs automatically.
2. **Object created earlier by a filter/interceptor in the same request?** Set it with `request.setAttribute` before the controller and read with `@RequestAttribute`; decide clearly whether the attribute is required or optional.
3. **Need preferences/state across multiple requests of the same HTTP session?** Write/remove via `HttpSession` or your chosen session mechanism, and read via `@SessionAttribute`.
4. **Building a multi-step form with a Spring MVC model?** Consider `@SessionAttributes` on the controller and `SessionStatus#setComplete()`.
5. **Need an authenticated user or access permissions?** Use Spring Security and a verified principal; arbitrary attributes are not sufficient for authorization decisions.
6. **Working asynchronously or across services?** Package needed context as explicit arguments or use proper propagation mechanisms; never assume request-bound `ThreadLocal` or HTTP sessions cross threads/processes automatically.

## 13. Self-check exercises

- **Scenario 1:** A filter sets `request.setAttribute("region", "apac")`. The controller declares `@RequestParam("region")`; the request has no query parameter. What happens? Fix the controller with the right annotation and write a test.
- **Scenario 2:** A client POSTs `language=en`, and the next GET has no session cookie. Why can `@SessionAttribute(name="language", required=false)` return `null`?
- **Scenario 3:** A controller declares a required `@RequestAttribute("tenant")`, but the interceptor only sets the attribute for `/api/admin/**`. What behavior occurs for requests hitting endpoints outside that pattern? Design a test and align the pattern.
- **Scenario 4:** A multi-step draft creation form uses `@SessionAttributes("draft")`. Upon completion, does calling `status.setComplete()` also remove the `language` attribute currently in the session? Explain.
- **Scenario 5:** An `@Async` service needs a trace ID. Compare passing `String traceId` as a parameter versus reading `RequestContextHolder` from the worker thread. Point out when the data might not exist.

## Official references

- [Spring MVC — `@RequestAttribute`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestattrib.html)
- [Spring MVC — `@SessionAttribute`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/sessionattribute.html)
- [Spring MVC — `@SessionAttributes`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/sessionattributes.html)
- [Spring MVC — Handler Method Arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html)
- [Spring MVC — Interception](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/interceptors.html)
- [Spring Framework Javadoc — `@RequestAttribute`](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/bind/annotation/RequestAttribute.html)
- [Spring Framework Javadoc — `@SessionAttribute`](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/bind/annotation/SessionAttribute.html)
