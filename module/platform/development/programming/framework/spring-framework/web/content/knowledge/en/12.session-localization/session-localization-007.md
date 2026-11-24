# RequestContextHolder, LocaleContextHolder, and ThreadLocal Limitations in Spring MVC

## 1. Objectives and Context

Within an HTTP request, multiple components need access to the **current context**: request attributes, locale information, time zone, message translation language, or a correlation ID. Spring MVC binds part of this context to the **Java thread processing the request**. Two commonly encountered APIs are:

- `org.springframework.web.context.request.RequestContextHolder`: retrieves the `RequestAttributes` of the request bound to the current thread.
- `org.springframework.context.i18n.LocaleContextHolder`: retrieves the `LocaleContext`, `Locale`, and sometimes `TimeZone` bound to the current thread.

These holders are convenient, yet **they are not a global state store, not a session, not an API that propagates context across arbitrary executors**, and not a replacement for explicit dependencies in business logic.

After this lesson, you will:

1. Distinguish request attributes, servlet request, locale, time zone, and HTTP session.
2. Use `getRequestAttributes()`, `currentRequestAttributes()`, `ServletRequestAttributes`, and `LocaleContextHolder.getLocale()` in the right places.
3. Understand how `DispatcherServlet`, `RequestContextFilter`, and `RequestContextListener` bind and clear context.
4. Distinguish `ThreadLocal`, `InheritableThreadLocal`, `@Async`, `CompletableFuture`, servlet async `Callable`, and completed requests.
5. Know when to **pass required data explicitly** instead of trying to copy `HttpServletRequest`/`RequestAttributes` onto worker threads.
6. Read language from `Accept-Language`, understand `LocaleResolver` and `MessageSource`, and avoid confusing locale with time zone.
7. Practice **Java 17+, Spring MVC/Spring Boot 3.x** code, `curl`, and MockMvc; diagnose missing-context errors and prevent cross-request leaks.

This lesson focuses on **Spring MVC on the Servlet stack**, Spring Framework 6.x. Spring WebFlux uses Reactor Context; do not rely on these two ThreadLocal holders to propagate context in reactive pipelines. Some APIs change between Spring Boot 3 and 4; check the documentation for your exact running version.

## 2. Picture of an HTTP Request and Thread-Bound Context

```text
Browser/API client
      |
      | GET /context/info
      | Accept-Language: vi-VN
      v
Servlet container
      |
      v
Servlet Filter chain
      |
      v
DispatcherServlet
      |  - binds RequestAttributes to RequestContextHolder
      |  - binds LocaleContext to LocaleContextHolder
      |  - resolves controller
      v
Controller / Service (on the bound request thread)
      |  - RequestContextHolder.getRequestAttributes()
      |  - LocaleContextHolder.getLocale()
      v
MessageSource / response DTO / view
      |
      v
DispatcherServlet completes dispatch
      |  - restores/clears thread-bound context
      v
Filter chain -> container -> client
```

This is the **normal synchronous thread** model. With servlet async, forward/error dispatches, executors, or custom filters, the bind/cleanup lifecycle can differ. `DispatcherServlet` and framework components manage request context over the request/dispatch lifecycle rather than letting it persist arbitrarily across requests.

A Servlet application normally uses a **thread pool**: a thread that processed request A may later process request B. Therefore the framework must restore/clear thread-bound state at the right time. If you bind a `ThreadLocal` manually and forget `remove()` or `finally`, request B can observe stale data from request A — both a bug and a potential data-leakage incident.

## 3. What Is `RequestContextHolder`?

`RequestContextHolder` is a static Spring Web holder storing one `RequestAttributes` instance per thread. `RequestAttributes` is an abstraction with scope/attribute operations; for servlet web requests, the common implementation is `ServletRequestAttributes`.

Key methods:

| API | Behavior |
| --- | --- |
| `RequestContextHolder.getRequestAttributes()` | Returns the bound `RequestAttributes` or **null** when absent |
| `RequestContextHolder.currentRequestAttributes()` | Returns the bound context; if absent, may fall back to JSF context (if present), then throws `IllegalStateException` when truly missing |
| `RequestContextHolder.setRequestAttributes(attrs)` | Binds context to the **current thread**, not inherited by child threads |
| `setRequestAttributes(attrs, true)` | Binds via `InheritableThreadLocal`; carries significant risks with thread pools |
| `resetRequestAttributes()` | Clears request attributes on the current thread |

Spring maintains two internal holders: a regular `ThreadLocal` and an `InheritableThreadLocal` for the inheritable option. Calling `setRequestAttributes(attrs, false)` uses non-inheritable binding and clears the other mode's binding on that thread.

### 3.1. Using It in a Controller

```java
@GetMapping("/info")
public String info() {
    RequestAttributes attrs =
            RequestContextHolder.currentRequestAttributes();
    return attrs.getClass().getSimpleName();
}
```

This is an **illustrative method** to place inside a `@RestController` with imports. In a normal Spring MVC Servlet request, `attrs` is typically `ServletRequestAttributes`. However, **do not cast unconditionally in shared library code**: in tests, JSF, or other environments, the implementation may not be Servlet-based.

### 3.2. Accessing `HttpServletRequest` When Truly Needed

```java
RequestAttributes attrs = RequestContextHolder.getRequestAttributes();

if (attrs instanceof ServletRequestAttributes servletAttrs) {
    HttpServletRequest request = servletAttrs.getRequest();
    String uri = request.getRequestURI();
}
```

This is an **in-method** illustrative snippet with imports `jakarta.servlet.http.HttpServletRequest`, `RequestAttributes`, `RequestContextHolder`, and `ServletRequestAttributes`; not a standalone Java file.

If code genuinely needs the request in a controller, a more transparent and testable way is usually **declaring a method parameter**:

```java
@GetMapping("/path")
public String path(HttpServletRequest request) {
    return request.getRequestURI();
}
```

Spring MVC can inject `HttpServletRequest` as an argument. There is no need to route through a static holder when a dependency can be passed directly. Similarly, a service that only needs a request ID or user ID should accept **that value** as a parameter rather than the entire servlet request.

### 3.3. `RequestAttributes` Is Not a Session

`RequestAttributes.SCOPE_REQUEST` represents request-scoped attributes; `SCOPE_SESSION` relates to the HTTP session if one exists. Do not confuse a thread-bound holder with session data outliving the request.

```java
attrs.setAttribute(
    "requestId", "R-123", RequestAttributes.SCOPE_REQUEST);
Object id = attrs.getAttribute(
    "requestId", RequestAttributes.SCOPE_REQUEST);
```

These two lines illustrate operating within a request. Request-scoped values normally live for the **request lifecycle** and cannot be safely held for jobs running after the response. Session attributes have their own lifecycle and concurrency rules; using the holder does not create a session ID or replace session management.

### 3.4. `currentRequestAttributes` vs `getRequestAttributes`

If a helper may be invoked both inside requests and in unit tests/scheduled jobs, prefer:

```java
RequestAttributes attributes =
        RequestContextHolder.getRequestAttributes();

if (attributes == null) {
    // No request context. Choose an intentional fallback behavior.
}
```

`currentRequestAttributes()` fits when **request context is a hard precondition**, and you want to fail fast if invoked in the wrong lifecycle. It normally throws `IllegalStateException` stating there is no thread-bound request. Catching `IllegalStateException` and pretending an empty request exists masks architectural bugs.

Never call `RequestContextHolder.currentRequestAttributes()` inside a singleton bean's constructor at startup; no HTTP request is being processed then.

## 4. Who Binds the Request Context: `DispatcherServlet`, Filter, or Listener?

In Spring MVC, `DispatcherServlet`/`FrameworkServlet` already exposes request attributes during handling; **you do not have to register an extra filter just to use `RequestContextHolder`**.

Three common options:

| Component | When useful | Notes |
| --- | --- | --- |
| `DispatcherServlet` | Controllers/handlers dispatched by Spring MVC | Normally already exposes context |
| `RequestContextFilter` | Context needed in layers **outside `DispatcherServlet`**, such as other filters or servlets | Requires proper mapping/order/dispatcher-type config |
| `RequestContextListener` | Servlet listener binding request thread context outside `DispatcherServlet` | Use only when the environment needs it; review lifecycle |

If a filter runs **before** `DispatcherServlet` and calls `RequestContextHolder.getRequestAttributes()`, you cannot assume `DispatcherServlet`'s context is already bound: it has not run yet. If `RequestContextFilter` is registered in the proper order, request/locale context can be exposed along that filter path. Still, do not stack multiple mechanisms "just in case": identify which component actually provides context to the code needing it.

`RequestContextFilter` has `setThreadContextInheritable(boolean)`, **false by default** to avoid thread-pool hazards. In Spring 6.x, the filter also accounts for async and error dispatches to establish context on those dispatches; exact behavior depends on servlet filter registration.

## 5. `LocaleContextHolder`: Thread-Bound Language and Time Zone

`LocaleContextHolder` stores a thread-bound `LocaleContext`, which can contain a `Locale` and, when supported, a `TimeZone`. `DispatcherServlet` automatically exposes the locale resolved by MVC.

Key APIs:

| API | Behavior |
| --- | --- |
| `LocaleContextHolder.getLocaleContext()` | Returns the bound context or **null** |
| `LocaleContextHolder.getLocale()` | Returns the context's locale; if absent, falls back to Spring default / JVM default |
| `LocaleContextHolder.getTimeZone()` | Returns the context's time zone; if absent, falls back to Spring default / JVM default |
| `LocaleContextHolder.setLocale(locale)` | Binds locale to current thread, non-inheritable by default |
| `LocaleContextHolder.setLocaleContext(ctx)` | Binds context, optionally with time zone; non-inheritable by default |
| `LocaleContextHolder.resetLocaleContext()` | Clears context on current thread |
| `setLocale(locale, true)` / `setLocaleContext(ctx, true)` | Allows inheritance via `InheritableThreadLocal` |
| `setDefaultLocale(...)` / `setDefaultTimeZone(...)` | Sets the holder's **shared default**; not a per-user locale |

### 5.1. Does Non-Null `getLocale()` Prove There Is a Request?

**No.** Even when no locale context is bound, `getLocale()` normally returns the Spring/JVM default locale; similarly `getTimeZone()` has a default time zone. To check whether a context is bound to the thread, check `getLocaleContext() != null`.

```java
Locale locale = LocaleContextHolder.getLocale();
LocaleContext ctx = LocaleContextHolder.getLocaleContext();

boolean explicitlyBound = (ctx != null);
```

This snippet requires imports `java.util.Locale` and `org.springframework.context.i18n.LocaleContext`. `explicitlyBound` indicates a thread-bound `LocaleContext` exists, **not** that an HTTP request or `Accept-Language` header exists; a test or application code might have set it manually.

### 5.2. Locale Differs from Time Zone

`Locale.forLanguageTag("vi-VN")` describes language/region; it does not mean the time zone is `Asia/Ho_Chi_Minh`. `Accept-Language: vi-VN` does not transmit a valid time zone. Use an IANA zone like `Asia/Ho_Chi_Minh` via user profile/preference or a dedicated mechanism, and pass `ZoneId` explicitly in business logic when converting instants.

Example:

```java
Locale locale = Locale.forLanguageTag("vi-VN");
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

String language = locale.toLanguageTag(); // "vi-VN"
String zoneText = zone.getId();            // "Asia/Ho_Chi_Minh"
```

`LocaleContextHolder.getTimeZone()` falls back to the default if the context provides no time zone; do not use it to infer the physical location of a user, account, or request.

## 6. `Accept-Language`, `LocaleResolver`, and `MessageSource`

A browser may send:

```http
GET /context/info HTTP/1.1
Accept-Language: vi-VN, en;q=0.8
```

A standard Spring MVC setup uses `AcceptHeaderLocaleResolver` to resolve the locale from the header and any configured supported/default locales. `DispatcherServlet` places the resolved locale into `LocaleContextHolder` for the request. Exact behavior depends on the resolver and options.

**Distinguish:**

- `Accept-Language` = client's language preference.
- `LocaleResolver` / `LocaleContextResolver` = application's locale selection policy for the request.
- `LocaleContextHolder` = place to **read the current thread-bound context**; does not write cookies or persist choices.
- `MessageSource` = looks up localized strings for a `Locale`.
- `TimeZone` / `ZoneId` = time-zone rules, separate from language.

Example:

```java
String title = messageSource.getMessage(
        "greeting",
        null,
        LocaleContextHolder.getLocale());
```

This is a snippet inside a bean with an injected `MessageSource messageSource`. If resource bundles contain:

```properties
# messages_vi.properties
greeting=Xin chào
```

```properties
# messages_en.properties
greeting=Hello
```

When the locale is Vietnamese/English and `MessageSource` finds the key, the matching string is returned. Do not tightly couple business layers to static thread holders when the locale is already known in the method signature; passing `Locale` into services makes code easier to test.

### Should You Call `setLocale` to Change Language for the Whole Session?

`LocaleContextHolder.setLocale(locale)` changes only the **current thread binding**; it neither rewrites `Accept-Language` nor saves to session/cookies. If an app lets users choose a language in the UI, you need a writable `LocaleResolver` strategy and can use `LocaleChangeInterceptor` or a well-designed preference endpoint.

`AcceptHeaderLocaleResolver` does not support `setLocale` as an arbitrary preference store; if you need to switch locale via query/session/cookie, consider `SessionLocaleResolver`/`CookieLocaleResolver` with proper configuration. Never call `setLocale` in one request and assume the user's next request will automatically have the same locale.

## 7. Why Does `ThreadLocal` Have Limitations?

Java's `ThreadLocal<T>` maintains a separate slot **per thread**. It does not synchronize or copy automatically across threads. A value set on the request thread exists only on that thread until `remove()`/reset.

### 7.1. Plain Java Example, Run with `javac`

File `ThreadLocalDemo.java`:

```java
public class ThreadLocalDemo {
    private static final ThreadLocal<String> LANGUAGE =
            new ThreadLocal<>();

    public static void main(String[] args) throws InterruptedException {
        LANGUAGE.set("vi-VN");
        try {
            System.out.println("main=" + LANGUAGE.get());

            Thread child = new Thread(
                    () -> System.out.println(
                            "child=" + LANGUAGE.get()));
            child.start();
            child.join();
        } finally {
            LANGUAGE.remove();
        }

        System.out.println("mainAfter=" + LANGUAGE.get());
    }
}
```

Commands:

```bash
javac ThreadLocalDemo.java
java ThreadLocalDemo
```

Exact stdout:

```text
main=vi-VN
child=null
mainAfter=null
```

Standard `ThreadLocal` does not automatically copy `"vi-VN"` to the child thread. This is plain Java requiring no Spring or web server.

### 7.2. `InheritableThreadLocal` Does Not Solve Thread Pools

`InheritableThreadLocal` can copy references from the parent when a **new thread is created**. It does not update values every time a pooled worker executes a task. In `ExecutorService`/`ThreadPoolExecutor`:

- Worker threads may have been created before request A started.
- A worker created while request A is active may inherit A's context.
- That worker is later **reused** for request B while old inherited values were never cleared.
- If the context holds `HttpServletRequest`/`ServletRequestAttributes`, it may reference **expired lifecycle** data or another user's info.

Spring's `RequestContextFilter` Javadoc warns against enabling inheritance with pools that create threads on demand. Therefore **do not set `threadContextInheritable=true` as a general fix for `@Async` or executors**.

A child thread living strictly within a request's scope may inherit context if intentionally designed; even then, cleanup/lifecycle management is required, and you should consider whether passing a few immutable values is better than passing the whole request.

## 8. `@Async`, `CompletableFuture`, and `ExecutorService`

The following situations are **not guaranteed** to see the original request's `RequestContextHolder`/`LocaleContextHolder`:

```java
CompletableFuture.supplyAsync(
        () -> LocaleContextHolder.getLocale());

executorService.submit(
        () -> RequestContextHolder.getRequestAttributes());

@Async
public void doWork() {
    // Runs on another executor thread; does not automatically have request context.
}
```

These are **three independent snippets**, not a complete Java program. `getLocale()` can still return the JVM default without ever receiving the request locale; thus "not null" does not prove propagation succeeded. `getRequestAttributes()` on pooled threads is typically null; `currentRequestAttributes()` can throw `IllegalStateException`.

### Recommended Pattern: Snapshot Needed Data, Then Pass Parameters

In the controller:

```java
@GetMapping("/enqueue")
public String enqueue(
        Locale locale,
        @RequestHeader(name = "X-Request-Id", required = false)
        String requestId) {

    String id = (requestId == null) ? "none" : requestId;
    jobService.enqueue(locale.toLanguageTag(), id);
    return "QUEUED";
}
```

This is an **illustrative method** inside a `@RestController` with a `jobService` bean; not a standalone compilable file. `jobService.enqueue` can construct a job command with two immutable `String` values. The job needs neither `HttpServletRequest`, `ServletRequestAttributes`, nor a live thread-bound context.

If the job requires user identity, pass only the **ID/permissions to re-verify** per security design; never treat client-supplied request headers as trusted identity. When the job executes later, re-authorize per policy rather than dragging full security/session/request contexts past their lifecycle.

### When Does `TaskDecorator` Make Sense?

Spring's `TaskDecorator` can propagate **certain permitted contexts** into executor tasks while restoring the prior context in `finally`. It can be used for `LocaleContext` or logging correlation IDs when tasks are short-lived and do not hold closed request resources. However, propagating raw request attributes across a pool is risky.

Safer example for locale, without carrying the servlet request:

```java
package com.example.demo;

import org.springframework.context.i18n.LocaleContext;
import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.core.task.TaskDecorator;

public class LocaleTaskDecorator implements TaskDecorator {
    @Override
    public Runnable decorate(Runnable task) {
        // Capture locale context when submitting/decorating the task.
        LocaleContext captured = LocaleContextHolder.getLocaleContext();

        return () -> {
            LocaleContext previous =
                    LocaleContextHolder.getLocaleContext();
            try {
                LocaleContextHolder.setLocaleContext(captured);
                task.run();
            } finally {
                LocaleContextHolder.setLocaleContext(previous);
            }
        };
    }
}
```

Use with `ThreadPoolTaskExecutor.setTaskDecorator(new LocaleTaskDecorator())` in executor configuration. This snippet is a **standalone Java class in a Spring project with dependencies**, and does not start a web server by itself. It copies `LocaleContext`, not `RequestAttributes`. When the original context is null, `setLocaleContext(null)` resets thread-bound locale on the worker; `finally` restores prior state. Logging MDC, security contexts, and trace contexts have their own propagation and cleanup mechanisms; never assume copying locale copies everything.

Note on `@Async`: the framework may wrap tasks/futures; `TaskDecorator` intercepts the runnable executed by the executor, not necessarily the exact boundary a developer expects. Test in practice and avoid relying on static holders as a long-term job contract.

## 9. Spring MVC-Managed Servlet Async Differs from Self-Spawned Tasks

Spring MVC supports controllers returning `Callable<T>` or `WebAsyncTask<T>`; the framework coordinates Servlet async processing. Spring has mechanisms to bind request/locale context during appropriate phases of MVC-managed async execution and can dispatch back into the Servlet container.

**Do not infer from this that every `CompletableFuture.supplyAsync` or background job will automatically receive the right context.** Arbitrary thread pools running outside the MVC async lifecycle are a different matter.

Example controller returning `Callable` safely with a data snapshot:

```java
@GetMapping("/async-safe")
public Callable<LanguageResponse> asyncSafe(Locale locale) {
    final String tag = locale.toLanguageTag();
    return () -> new LanguageResponse(tag);
}
```

This method **does not depend on a worker `ThreadLocal` locale**; `tag` is captured while the controller is in a valid request context. An MVC-managed `Callable` has its own async dispatch lifecycle, yet the code remains explicit and easy to test.

If you run asynchronous streaming or send `SseEmitter` events after the response commits, the request may no longer be alive. Never retain `ServletRequestAttributes` for callbacks running minutes later. With virtual threads (Java 21+), each task may get its own thread, yet **`ThreadLocal` remains thread-scoped** and does not alter request lifetime or propagation semantics; this Java 17 demo does not use virtual threads.

## 10. Runnable Sample Code: Spring Boot 3 / Spring MVC

This example demonstrates three ways of reading context:

- `GET /context/info`: reads request and locale from both holders during MVC dispatch, while also accepting `Locale` and `HttpServletRequest` directly for comparison.
- `GET /context/async-safe`: uses `Callable` and **snapshots the locale tag** from the request before the async task starts.
- `GET /context/messages`: fetches a message from `MessageSource` using the MVC-resolved `Locale`.

Maven project from Spring Initializr with Java 17+, `spring-boot-starter-web`, `spring-boot-starter-test`. For `Locale`/`MessageSource`, add the messages files below; no database and no separate `RequestContextFilter` are needed because the controller runs inside `DispatcherServlet`.

### 10.1. `src/main/java/com/example/demo/DemoApplication.java`

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 10.2. `src/main/java/com/example/demo/ContextController.java`

```java
package com.example.demo;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.context.MessageSource;
import org.springframework.context.i18n.LocaleContext;
import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.RequestAttributes;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

import java.util.Locale;
import java.util.concurrent.Callable;

@RestController
public class ContextController {

    private final MessageSource messages;

    public ContextController(MessageSource messages) {
        this.messages = messages;
    }

    @GetMapping("/context/info")
    public ContextResponse info(
            HttpServletRequest request,
            Locale locale) {

        RequestAttributes attrs =
                RequestContextHolder.getRequestAttributes();
        LocaleContext localeContext =
                LocaleContextHolder.getLocaleContext();

        boolean servletBound =
                attrs instanceof ServletRequestAttributes;
        boolean localeBound = localeContext != null;

        String path = request.getRequestURI();
        String tag = locale.toLanguageTag();
        String holderTag = LocaleContextHolder.getLocale()
                .toLanguageTag();

        return new ContextResponse(
                path, tag, holderTag, servletBound, localeBound);
    }

    @GetMapping("/context/async-safe")
    public Callable<LanguageResponse> asyncSafe(Locale locale) {
        String captured = locale.toLanguageTag();

        // Callable is handled by Spring MVC as servlet async.
        return () -> new LanguageResponse(captured);
    }

    @GetMapping("/context/messages")
    public MessageResponse messages(Locale locale) {
        String resolved = messages.getMessage(
                "greeting", null, locale);
        return new MessageResponse(
                locale.toLanguageTag(), resolved);
    }

    public record ContextResponse(
            String path,
            String locale,
            String holderLocale,
            boolean requestBound,
            boolean localeBound) {}

    public record LanguageResponse(String locale) {}

    public record MessageResponse(
            String locale, String greeting) {}
}
```

Because the code sits in a `@RestController`, Spring MVC resolves `HttpServletRequest`/`Locale` via method arguments, and Jackson serializes the record DTOs. `ServletRequestAttributes` is checked via `instanceof` instead of a blind cast. No static field holding the request is needed; controller beans are singletons by default, whereas requests are resources with their own lifecycle.

**Key part of the demo:** `info()` receives `Locale` as a parameter while also reading `LocaleContextHolder.getLocale()`. Both normally match during MVC dispatch. `requestBound` and `localeBound` are verifiable booleans, without claiming every request must carry a time zone.

### 10.3. `src/main/resources/messages_vi.properties`

```properties
greeting=Xin chào
```

### 10.4. `src/main/resources/messages_en.properties`

```properties
greeting=Hello
```

You can add `src/main/resources/messages.properties` as a fallback:

```properties
greeting=Hello
```

These are three separate files; message bundles are auto-configured by Spring Boot when placed in the right resource path with fallback `messages.properties`. There is no need to call `LocaleContextHolder.setLocale` to translate because the handler already receives the request's `Locale`.

### 10.5. Running the Application

```bash
./mvnw spring-boot:run
```

PowerShell:

```powershell
.\mvnw.cmd spring-boot:run
```

Default port is normally 8080 unless `server.port` is changed. These sources cannot compile with `javac ContextController.java` without Spring Boot dependencies; use the Maven project generated from Spring Initializr.

## 11. Verifying HTTP Behavior with `curl`

### Request Context and Locale

```bash
curl -s -H "Accept-Language: vi-VN" \
  http://localhost:8080/context/info
```

With a standard locale resolver reading `Accept-Language`, the expected JSON contains:

```json
{
  "path": "/context/info",
  "locale": "vi-VN",
  "holderLocale": "vi-VN",
  "requestBound": true,
  "localeBound": true
}
```

JSON key order may differ; do not assert raw JSON string snapshots. If the app configures a custom `LocaleResolver`, `defaultLocale`, `supportedLocales`, or a gateway modifying headers, the locale may differ: adjust tests to match the contract.

### `MessageSource` by Language

```bash
curl -s -H "Accept-Language: vi-VN" \
  http://localhost:8080/context/messages
```

Expected `greeting` = `"Xin chào"`, `locale` = `"vi-VN"`. With:

```bash
curl -s -H "Accept-Language: en-US" \
  http://localhost:8080/context/messages
```

Expected `greeting` = `"Hello"` from the English bundle. This lesson looks up key `greeting` without depending on a database or request session.

### Safe Servlet Async

```bash
curl -s -H "Accept-Language: vi-VN" \
  http://localhost:8080/context/async-safe
```

The expected response after async dispatch contains `{"locale":"vi-VN"}`. The locale tag is snapshotted **before** the `Callable` runs, without relying on a worker reading `ThreadLocal`.

## 12. MockMvc: Testing Bound Context, Locale, and Async

Create `src/test/java/com/example/demo/ContextControllerTest.java`, depending on `spring-boot-starter-test`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.util.Locale;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ContextControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void requestAndLocaleContextAreBoundInsideMvc() throws Exception {
        mvc.perform(get("/context/info")
                .locale(Locale.forLanguageTag("vi-VN")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.path").value("/context/info"))
            .andExpect(jsonPath("$.locale").value("vi-VN"))
            .andExpect(jsonPath("$.holderLocale").value("vi-VN"))
            .andExpect(jsonPath("$.requestBound").value(true))
            .andExpect(jsonPath("$.localeBound").value(true));
    }

    @Test
    void messageSourceUsesResolvedLocale() throws Exception {
        mvc.perform(get("/context/messages")
                .locale(Locale.forLanguageTag("vi-VN")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.greeting").value("Xin chào"));
    }

    @Test
    void asyncResponseUsesCapturedValue() throws Exception {
        MvcResult initial = mvc.perform(get("/context/async-safe")
                .locale(Locale.forLanguageTag("vi-VN")))
            .andExpect(request().asyncStarted())
            .andReturn();

        mvc.perform(asyncDispatch(initial))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.locale").value("vi-VN"));
    }
}
```

Run:

```bash
./mvnw test
```

Windows:

```powershell
.\mvnw.cmd test
```

This is a **runnable test template for a Boot 3 project with the declared dependencies**; not an actual execution result from a specific repository. If Spring Security, custom locale resolvers, or filters are enabled, tests may need mock users, allowlists, and matching locale config.

**Why does the async test not read `ThreadLocal` on the worker?** The goal is to prove stable snapshot passing, not to assume every worker always holds an HTTP request context. To test MVC async binding mechanics specifically, write controlled tests matching your Spring Framework version and lifecycle rather than treating incidental `ExecutorService` behavior as a contract.

## 13. Unit Testing Missing Request Context

In unit tests outside MVC, `RequestContextHolder.getRequestAttributes()` can be null. You can verify this explicitly without a web server:

```java
import org.junit.jupiter.api.Test;
import org.springframework.web.context.request.RequestContextHolder;

import static org.junit.jupiter.api.Assertions.*;

class NoRequestContextTest {

    @Test
    void noRequestContextOnOrdinaryTestThread() {
        RequestContextHolder.resetRequestAttributes();

        assertNull(RequestContextHolder.getRequestAttributes());
        assertThrows(IllegalStateException.class,
                RequestContextHolder::currentRequestAttributes);
    }
}
```

This is a **standalone test class in the test sources of a Spring project with JUnit**; add an appropriate package if required by your project. In JSF environments with an active `FacesContext`, `currentRequestAttributes()` may fall back instead of throwing; the test above assumes an ordinary Java unit test with no JSF `FacesContext`.

When writing tests for `LocaleContextHolder`, remember `getLocale()` falls back to the default, so **do not assert null**. Use `LocaleContextHolder.getLocaleContext()` to check whether a context is bound to the thread. Unit tests calling `setLocaleContext`/`setRequestAttributes` manually must clean up in `finally` or teardown to avoid leaking state between tests on the same worker.

## 14. When You Truly Need to Bind Context Manually

In custom code, if you must temporarily bind a `LocaleContext`, **restore the previous state** rather than unconditionally resetting a framework-owned context.

```java
LocaleContext old = LocaleContextHolder.getLocaleContext();
try {
    LocaleContextHolder.setLocale(Locale.forLanguageTag("vi-VN"));
    doSomethingThatNeedsLocale();
} finally {
    LocaleContextHolder.setLocaleContext(old);
}
```

This is an in-method snippet assuming imports for `Locale`/`LocaleContext` and a `doSomethingThatNeedsLocale()` method. It does not implement user sessions/cookies and should not be used in a controller hoping to change the app's locale across requests.

With `RequestContextHolder`, creating `ServletRequestAttributes` manually and binding it to a custom thread can only make sense while the request is **still active**, with proper cleanup and without violating lifecycle rules. Never use `new ServletRequestAttributes(mockRequest)` in production just to silence `IllegalStateException`, and never pass request attributes from request A to a background job of request B.

If a task needs caller ID or language, pass immutable data and authorize properly. Context-propagation frameworks should only supplement cross-cutting concerns whose lifecycle you understand.

## 15. Pitfalls and Troubleshooting

1. **Reading context in a singleton constructor:** constructors run at startup with no request, causing `IllegalStateException`.
2. **Using `currentRequestAttributes` outside web threads:** in `@Scheduled`, `@Async`, or pooled workers, this can throw an exception.
3. **Assuming non-null `getLocale()` means request propagation worked:** false; it falls back to Spring/JVM defaults.
4. **Enabling `inheritable=true` for thread pools:** can leak context from an old request into pooled workers.
5. **Storing `ServletRequestAttributes` in static maps/caches:** causes memory leaks and references expired requests.
6. **Forgetting `ThreadLocal` cleanup in manual code:** pooled workers retain stale data when reused.
7. **Reading `userId` from a request header and treating it as trusted identity:** headers are client-controlled; authenticate and authorize properly.
8. **Calling `LocaleContextHolder.setLocale` expecting the session to remember it:** it only mutates thread-bound context; use an appropriate resolver/preference store.
9. **Confusing `Accept-Language` with time zone:** language/region does not determine the user's real time zone.
10. **Reading `RequestContextHolder` in a filter running before `DispatcherServlet`:** the holder may not be bound yet; check filter/listener ordering.
11. **Passing `HttpServletRequest` into `CompletableFuture`:** the request may already have finished; snapshot only needed fields.
12. **`TaskDecorator` setting locale without `finally` restoration:** pooled workers may carry another user's locale.
13. **Propagating the entire `SecurityContext` unconditionally:** use proper security propagation and lifecycle controls rather than blindly copying credentials.
14. **Relying on `ThreadLocal` to carry business transactions across threads:** transactions and persistence contexts have their own mechanisms and do not cross worker threads automatically.
15. **Using `Locale.getDefault()` to infer client locale:** that is the JVM default, not `Accept-Language`.
16. **Hitting HTTP 500 when no request exists and slapping `RequestContextFilter` everywhere:** if the call site is a scheduled job, filters do not run there; fix the job's dependencies.
17. **Binding context without distinguishing REQUEST/ERROR/ASYNC dispatches:** threads and dispatches can differ; inspect the actual lifecycle.
18. **Missing message keys:** `MessageSource` can throw `NoSuchMessageException` when no default matches—not a `ThreadLocal` bug.
19. **Using static holders as business APIs:** hard to test, hides dependencies, and blocks reuse from CLI, batch, or messaging.
20. **Concluding propagation works from tests that "pass sometimes":** executor thread reuse and timing create flakiness; test with explicit snapshotted values.
21. **Reading the request after the response completes:** request scope has ended; having a reference does not make it safe.
22. **Confusing `SessionLocaleResolver` with `AcceptHeaderLocaleResolver`:** locale persistence policies differ; design the language-switching interface clearly.
23. **Skipping multithreaded isolation tests:** cross-request leaks often stay hidden in happy-path tests.
24. **Mixing thread-bound context with Reactor Context in WebFlux:** different programming model; use reactive stack APIs instead.

## 16. Debugging Workflow When Locale or Request Context "Vanishes"

1. Identify **which thread** the code is executing on; log thread name/correlation ID carefully without logging sensitive data.
2. Determine whether it runs in a synchronous MVC controller/service, servlet filter, `@Async`, `Callable`, `CompletableFuture`, or scheduled task.
3. If `RequestContextHolder.getRequestAttributes() == null`, check whether `DispatcherServlet` was reached or if the filter/listener is registered.
4. If `currentRequestAttributes()` throws `IllegalStateException` in a background job, do not blindly add a Filter: switch to snapshotted inputs or explicit parameter passing.
5. If `LocaleContextHolder.getLocale()` returns the default locale, inspect `getLocaleContext()` to distinguish missing context from a default-resolved locale.
6. Check the `LocaleResolver` and actual `Accept-Language` header; clients, gateways, or tests may override locale.
7. Inspect the task executor/thread pool and inheritable flags; avoid patching with `setThreadContextInheritable(true)`.
8. Verify `finally` cleanup in any code setting `ThreadLocal` manually, even when tasks throw exceptions.
9. If failures occur during async responses, inspect the Servlet async lifecycle, ERROR/ASYNC dispatches, and when the response commits.
10. Test separately with request-less unit tests, in-request MockMvc tests, and real executor integration tests; do not conflate all three into one case.
11. If results depend on request ID or time zone, pass both as immutable values to workers instead of the request object.
12. Verify user/tenant, session/cookie, and authorization policies separately; a thread-bound locale never proves authentication.

## 17. Safe Design Checklist

- [ ] Can the controller accept `HttpServletRequest`, `Locale`, or principal directly as method arguments when needed?
- [ ] Do services accept required data as explicit parameters instead of accessing static holders?
- [ ] Is `currentRequestAttributes()` called only when definitely inside a request lifecycle?
- [ ] Does code handle `getRequestAttributes() == null` with proper fallback behavior?
- [ ] Are `ServletRequestAttributes`/`HttpServletRequest` never stored in background queues, caches, or static fields?
- [ ] Is inheritable context disabled for pooled executors?
- [ ] Is every manually set `ThreadLocal` restored/cleared in a `finally` block?
- [ ] Does the locale resolver match the `Accept-Language`/session/cookie contract?
- [ ] Are locale and time zone kept distinct, with time zone coming from its own valid source?
- [ ] Are i18n messages looked up with an explicit locale or a verified context?
- [ ] Are Servlet async and worker-thread paths tested separately?
- [ ] Do tests verify isolation against leaks across different tasks/users when using custom decorators?
- [ ] Is request-specific business data authorized rather than trusting client-selected headers?
- [ ] Do HTTP/error responses avoid exposing internal request context or personal data?
- [ ] Can code run from batch/events/CLI without depending on an HTTP thread when the use case requires it?

## 18. Self-Check Questions

**1.** How do `RequestContextHolder.currentRequestAttributes()` and `getRequestAttributes()` differ?

**Answer:** `getRequestAttributes()` returns null if no thread-bound context exists. `currentRequestAttributes()` requires a context, may fall back to JSF, and throws `IllegalStateException` if still absent.

**2.** Why is `LocaleContextHolder.getLocale()` not a reliable check for whether a request is bound?

**Answer:** It falls back to Spring/JVM defaults even when no context is bound. Use `getLocaleContext()` to check whether a locale context is bound to the thread.

**3.** Does `Locale.forLanguageTag("vi-VN")` mean time zone = `Asia/Ho_Chi_Minh`?

**Answer:** No. Locale/region and time zone are two separate pieces of information.

**4.** Does every synchronous Spring MVC controller need `RequestContextFilter` added to read `RequestContextHolder`?

**Answer:** No. `DispatcherServlet` already exposes the request context during standard MVC processing.

**5.** Why should you avoid `setThreadContextInheritable(true)` on thread pools?

**Answer:** Pooled workers created while request A is active can be reused for request B while retaining A's context or expired references, causing data leaks and bugs.

**6.** Can you automatically get the request locale inside `CompletableFuture.supplyAsync`?

**Answer:** Never assume so. Executor threads differ; snapshot the locale and pass it explicitly, or use a dedicated decorator with cleanup if truly needed.

**7.** Does `@Async` keep `HttpServletRequest` alive past the response?

**Answer:** No. Background tasks have their own lifecycle; do not hold request attributes after the request finishes.

**8.** Does `LocaleContextHolder.setLocale` set a cookie for the next request?

**Answer:** No. It only updates the current thread's context. Persisting language choices requires an appropriate resolver/session/cookie/preference mechanism.

**9.** When is `TaskDecorator` appropriate?

**Answer:** When propagating small, safe context (like locale or trace metadata) into managed tasks with `try/finally` restoration. Do not copy raw `ServletRequestAttributes` into long-running jobs.

**10.** What is the simplest way to keep services independent of `RequestContextHolder`?

**Answer:** Have the controller obtain `Locale`/request ID/user ID from the framework, build an immutable input DTO/snapshot, and pass it to the service via parameters.

## 19. References

- Spring Framework — `RequestContextHolder` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/web/context/request/RequestContextHolder.html
- Spring Framework — `LocaleContextHolder` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/context/i18n/LocaleContextHolder.html
- Spring Framework — `RequestContextFilter` and inheritable context: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/web/filter/RequestContextFilter.html
- Spring Framework — `RequestContextListener`: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/web/context/request/RequestContextListener.html
- Spring Framework — `LocaleResolver` / `LocaleContextResolver`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/localeresolver.html
- Spring Framework — MVC Method Arguments: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html
- Spring Framework — MVC Async Requests: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Framework — `TaskDecorator` API: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/core/task/TaskDecorator.html
- Java 17 — `ThreadLocal` Javadoc: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html
- Java 17 — `InheritableThreadLocal` Javadoc: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/InheritableThreadLocal.html
- Jakarta Servlet specification: https://jakarta.ee/specifications/servlet/
