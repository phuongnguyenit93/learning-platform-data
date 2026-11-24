# Async Requests, asyncDispatch, and Asynchronous Response Handling in Spring MVC

A Spring MVC controller can immediately return an object representing a future result instead of completing all business work on the Servlet request thread. Spring MVC uses **Servlet asynchronous request processing** to release the initial request thread, wait for the task/callback to complete, and then perform an **ASYNC dispatch** to render the final HTTP response. Key return types include **Callable**, **DeferredResult**, **CompletionStage**, **CompletableFuture**, and **WebAsyncTask**.

The main testing challenge is distinguishing an **intermediate asynchronous result** from the **final HTTP status, headers, and body**. With plain **MockMvc**, a single **perform(get(...))** call does not replay the servlet container's follow-up dispatch. Tests should verify **request().asyncStarted()**, inspect the async result via **request().asyncResult(...)** or **MvcResult.getAsyncResult(...)**, and then call **mockMvc.perform(asyncDispatch(mvcResult))** to assert the final response. That is the core focus of this lesson.

The hands-on example uses Java 17, Spring Boot 3.4.5, JUnit Jupiter, and Gradle. To keep tests deterministic, we control exactly when futures finish via **complete** or **completeExceptionally** instead of using `Thread.sleep`.

## 1. Two-Phase Model of a Servlet Async Request

When an endpoint returns a `Callable`, the lifecycle looks like this:

~~~text
HTTP client sends GET /api/quotes/callable?region=HN
    |
    v
Servlet container thread A
  DispatcherServlet invokes controller
  controller returns Callable<Quote>
  Spring MVC calls startAsync() and registers async processing
  thread A exits the request; connection/response stays open
    |
    v
AsyncTaskExecutor runs Callable on worker thread B
  produces Quote or throws exception
    |
    v
Servlet container performs ASYNC dispatch
    |
    v
DispatcherServlet re-processes the async result
  HttpMessageConverter -> JSON on success
  HandlerExceptionResolver -> error response on exception
    |
    v
Client receives HTTP status + headers + body
~~~

With `DeferredResult`, Spring MVC registers an async request but **does not spawn a worker itself to produce the result**: an application event source or callback must call **setResult(value)** or **setErrorResult(error)**. With `CompletableFuture`, Spring MVC receives a notification when the future completes; whether work actually ran on another thread depends on where the future was created and how it completes.

Two phases to keep distinct:

| Phase | What Is Certain? | What Is Not Proven Yet? |
| --- | --- | --- |
| Async started | Request enabled Servlet async, handler returned a compatible async holder | That the value was produced accurately, serialized cleanly, or final status is fixed |
| Async result ready | Task/callback produced a value or error | That HTTP body/headers rendered as the client will receive them |
| Async dispatch | Spring MVC processed the result, mapped exceptions, and rendered the response | Real networking, real timeouts, or production load |
| Client receives response | Transport completed in a real-server test | All other error paths or concurrency edge cases |

**Having "async" in a method name does not make a request asynchronous.** If a controller returns a synchronous `Quote`, there is no basis to assert `asyncStarted`. Conversely, an already-completed `CompletableFuture` has an async return type, yet proves no background execution occurred.

## 2. Choosing the Right Return Type

| Type | How Result Arrives | When Appropriate | Pitfall |
| --- | --- | --- | --- |
| `Callable<T>` | Spring MVC executes the callable on `AsyncTaskExecutor` | Offloading work to an MVC-managed worker | Blocking code still blocks the worker thread |
| `DeferredResult<T>` | App completes it explicitly from callbacks/events | Event-driven or delayed service callbacks | Forgetting `setResult` leaves it hanging until timeout |
| `CompletableFuture<T>` | `CompletionStage` completed by a framework/library/executor | Dependencies already returning futures | `completedFuture` merely wraps an existing value |
| `WebAsyncTask<T>` | `Callable` with per-endpoint timeout, executor, and callbacks | Individual endpoints needing custom async settings | Servlet timeout differs from test wait timeout |
| `ResponseBodyEmitter` / `SseEmitter` | Emits multiple chunks/events | SSE or HTTP streaming | Must also manage flush, disconnect, order, resource cleanup |
| `StreamingResponseBody` | Writes directly to `OutputStream` on worker | Large streaming payloads | Requires explicit backpressure and I/O error handling |

Three syntactically standalone illustrative handlers:

~~~java
@GetMapping("/callable")
public Callable<String> callable() {
    return () -> "ready";
}

@GetMapping("/future")
public CompletableFuture<String> future() {
    return CompletableFuture.completedFuture("ready");
}

@GetMapping("/deferred")
public DeferredResult<String> deferred() {
    DeferredResult<String> result = new DeferredResult<>(5_000L);
    result.setResult("ready");
    return result;
}
~~~

These are **snippets only**; they need a controller class and imports and do not represent a genuinely waiting task. In production, `DeferredResult` is typically completed from another thread or callback; completing immediately upon creation merely illustrates the API. The full project below lets tests keep a future pending and then complete it under full control.

## 3. Standard MockMvc Testing Flow: Start, Wait, Dispatch

Spring Framework guides testing async controllers in two passes:

~~~java
MvcResult first = mockMvc.perform(
                get("/api/quotes/callable").param("region", "HN"))
        .andExpect(request().asyncStarted())
        .andExpect(request().asyncResult(new Quote("HN", 25_000)))
        .andReturn();

mockMvc.perform(asyncDispatch(first))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.region").value("HN"))
        .andExpect(jsonPath("$.fee").value(25_000));
~~~

This is a **snippet** relying on the `Quote` class defined in Section 5. Note what each step does:

- **request().asyncStarted()**: confirms async processing started for the request.
- **request().asyncResult(expected)**: waits for the async result and asserts the intermediate value; for the `Quote` record, `equals` compares components by value.
- **andReturn()**: captures `MvcResult` to pass into dispatch.
- **asyncDispatch(first)**: instructs MockMvc to execute the **ASYNC dispatch** pass in place of a real container.
- **status(), content(), jsonPath() after dispatch**: verifies final HTTP status, content type, and JSON.

**Do not assert only `asyncResult` and conclude the HTTP contract is valid.** A valid Java `Quote` can still fail serialization or mishandle exception resolution. Conversely, asserting JSON right after the first `perform` checks an incomplete phase.

If the result lacks stable equality, you can use **`first.getAsyncResult(5_000L)`** to retrieve and inspect the produced object, and then still dispatch to verify the HTTP response. The `5_000` figure here is strictly **how long the MockMvc test waits**, not proof of Servlet container timeout or HTTP 504.

## 4. Business Contract Used Throughout the Example

The project named `spring-mvc-async-guide` has three endpoints:

- **GET /api/quotes/callable?region=HN** returns `Callable<Quote>`.
- **GET /api/quotes/future?region=HCM** returns `CompletableFuture<Quote>`.
- **GET /api/quotes/deferred?region=HN** returns `DeferredResult<Quote>` bridged to a `CompletableFuture`.

Service rules: `HN` has fee `25_000`; other valid regions have fee `18_000`. Region `FAIL` throws `QuoteUnavailableException` with message **pricing service unavailable**. Spring REST advice maps this exception to **HTTP 503** with JSON containing **code=QUOTE_UNAVAILABLE** and the exception message. Missing the `region` query parameter is an MVC binding error expecting **HTTP 400** before the controller enters async processing.

The project is purely in-memory, needing no database or external HTTP services. Unit/web MVC tests can stub the service. Full-context tests use the real service to verify wiring and exception handling.

## 5. Buildable, Runnable Java 17+ / Spring Boot 3.4.5 Project

Layout:

~~~text
settings.gradle
build.gradle
src/main/java/com/example/mvcasync/AsyncDemoApplication.java
src/main/java/com/example/mvcasync/Quote.java
src/main/java/com/example/mvcasync/QuoteUnavailableException.java
src/main/java/com/example/mvcasync/QuoteService.java
src/main/java/com/example/mvcasync/QuoteController.java
src/main/java/com/example/mvcasync/ApiErrorHandler.java
src/test/java/com/example/mvcasync/QuoteControllerWebMvcTest.java
src/test/java/com/example/mvcasync/QuoteFullContextTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'spring-mvc-async-guide'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.5'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Use a Gradle Wrapper compatible with Java 17 and Boot 3.4.x. Spring MVC is supplied by `spring-boot-starter-web`. Spring Boot 3.4.x manages Spring Framework 6.2, so **`@MockitoBean`** works in tests; Boot 3.3 / Framework 6.1 lacks this annotation and requires the version-appropriate mocking mechanism rather than mixing newer Spring Test APIs into an older project.

### 5.1. Application, Model, and Exception

**src/main/java/com/example/mvcasync/AsyncDemoApplication.java**

~~~java
package com.example.mvcasync;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AsyncDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AsyncDemoApplication.class, args);
    }
}
~~~

**src/main/java/com/example/mvcasync/Quote.java**

~~~java
package com.example.mvcasync;

public record Quote(String region, int fee) {
}
~~~

**src/main/java/com/example/mvcasync/QuoteUnavailableException.java**

~~~java
package com.example.mvcasync;

public class QuoteUnavailableException extends RuntimeException {
    public QuoteUnavailableException(String message) {
        super(message);
    }
}
~~~

`Quote` is a Java 17 record with value-based `equals`/`hashCode`, making assertions via **`request().asyncResult(new Quote(...))`** clear and reliable. The exception is a custom domain exception; its HTTP status does not default to 503—it is mapped by the advice below.

### 5.2. Real Service: Distinguishing Synchronous Values from Completed Futures

**src/main/java/com/example/mvcasync/QuoteService.java**

~~~java
package com.example.mvcasync;

import java.util.concurrent.CompletableFuture;
import org.springframework.stereotype.Service;

@Service
public class QuoteService {
    public Quote quote(String region) {
        if (region == null || region.isBlank()) {
            throw new IllegalArgumentException("region must not be blank");
        }
        if ("FAIL".equals(region)) {
            throw new QuoteUnavailableException(
                    "pricing service unavailable");
        }
        return new Quote(
                region,
                "HN".equals(region) ? 25_000 : 18_000);
    }

    public CompletableFuture<Quote> quoteAsync(String region) {
        // Illustrates future return type without spawning a background thread.
        return CompletableFuture.completedFuture(quote(region));
    }
}
~~~

Here **`quoteAsync`** computes the price synchronously first and then returns **`completedFuture`**. That does not spawn background work. We designed it this way so the runnable example stays simple, while in the web MVC slice test, Mockito supplies a **pending** future to test true delayed completion. In real applications using an async HTTP client, event listener, or dedicated executor, `quoteAsync` can return an incomplete future while preserving the exact same contract.

### 5.3. Controller with Callable, CompletableFuture, and DeferredResult

**src/main/java/com/example/mvcasync/QuoteController.java**

~~~java
package com.example.mvcasync;

import java.util.concurrent.Callable;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.async.DeferredResult;

@RestController
@RequestMapping("/api/quotes")
public class QuoteController {
    private final QuoteService service;

    public QuoteController(QuoteService service) {
        this.service = service;
    }

    @GetMapping("/callable")
    public Callable<Quote> callable(@RequestParam String region) {
        return () -> service.quote(region);
    }

    @GetMapping("/future")
    public CompletableFuture<Quote> future(@RequestParam String region) {
        return service.quoteAsync(region);
    }

    @GetMapping("/deferred")
    public DeferredResult<Quote> deferred(@RequestParam String region) {
        DeferredResult<Quote> result = new DeferredResult<>(5_000L);

        service.quoteAsync(region).whenComplete((quote, failure) -> {
            if (failure == null) {
                result.setResult(quote);
            } else {
                Throwable cause = failure instanceof CompletionException
                        && failure.getCause() != null
                        ? failure.getCause()
                        : failure;
                result.setErrorResult(cause);
            }
        });
        return result;
    }
}
~~~

**Explanation:**

- Endpoint **/callable** does not compute the quote when constructing the lambda; Spring MVC uses `AsyncTaskExecutor` to run the `Callable` after the controller returns it.
- Endpoint **/future** hands the service's future directly to MVC's return-value handler. Even though `quoteAsync` computes synchronously in the demo, MVC handles the return type with async semantics.
- Endpoint **/deferred** creates a `DeferredResult` with a 5-second timeout and attaches a callback to the future. On success, it calls `setResult`; on failure, it calls `setErrorResult` so MVC resolves the exception.
- The error branch unwraps one `CompletionException` layer because future APIs often wrap exceptions that way. Never assume every future error has only one wrapper layer; if your contract inspects deeper causes, walk the cause chain properly.
- If `quoteAsync` **throws synchronously before returning a `CompletableFuture`**, `/deferred` never returns a `DeferredResult` and the exception goes through synchronous error handling; async error tests must clarify whether errors happen before or after `asyncStarted`.

Never call **`join()`** on the request thread to wait for results, as that turns an async endpoint right back into a blocking endpoint. Never spin a busy-wait polling loop on `DeferredResult` inside a controller.

### 5.4. Advice Mapping Exceptions to HTTP Contracts

**src/main/java/com/example/mvcasync/ApiErrorHandler.java**

~~~java
package com.example.mvcasync;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrorHandler {
    @ExceptionHandler(QuoteUnavailableException.class)
    @ResponseStatus(HttpStatus.SERVICE_UNAVAILABLE)
    public ApiError unavailable(QuoteUnavailableException exception) {
        return new ApiError(
                "QUOTE_UNAVAILABLE", exception.getMessage());
    }

    public record ApiError(String code, String message) {
    }
}
~~~

When a `Callable` throws `QuoteUnavailableException` or `DeferredResult` receives it via `setErrorResult`, Spring MVC routes it through `HandlerExceptionResolver` and the advice to produce status **503** and `ApiError` JSON during the **final dispatch**. Exceptions from other sources or unhandled types will not necessarily match this shape.

## 6. WebMvcTest: MockMvc Tests Controlling the Future

This class keeps the real controller and Spring MVC while **using `@MockitoBean` for `QuoteService`**, fitting the web slice. Using an incomplete future and completing it directly from the test avoids thread races and eliminates `Thread.sleep`.

**src/test/java/com/example/mvcasync/QuoteControllerWebMvcTest.java**

~~~java
package com.example.mvcasync;

import java.util.concurrent.CompletableFuture;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(QuoteController.class)
class QuoteControllerWebMvcTest {
    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private QuoteService service;

    @Test
    void callableProducesJsonAfterAsyncDispatch() throws Exception {
        when(service.quote("HN")).thenReturn(new Quote("HN", 25_000));

        MvcResult first = mockMvc.perform(
                        get("/api/quotes/callable")
                                .param("region", "HN"))
                .andExpect(request().asyncStarted())
                .andExpect(request().asyncResult(
                        new Quote("HN", 25_000)))
                .andReturn();

        mockMvc.perform(asyncDispatch(first))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.region").value("HN"))
                .andExpect(jsonPath("$.fee").value(25_000));

        verify(service).quote("HN");
    }

    @Test
    void futureFinishesAtTimeControlledByTest() throws Exception {
        CompletableFuture<Quote> pending = new CompletableFuture<>();
        when(service.quoteAsync("HCM")).thenReturn(pending);

        MvcResult first = mockMvc.perform(
                        get("/api/quotes/future")
                                .param("region", "HCM"))
                .andExpect(request().asyncStarted())
                .andReturn();

        assertFalse(pending.isDone());
        assertTrue(pending.complete(new Quote("HCM", 18_000)));

        mockMvc.perform(asyncDispatch(first))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.region").value("HCM"))
                .andExpect(jsonPath("$.fee").value(18_000));

        verify(service).quoteAsync("HCM");
    }

    @Test
    void deferredHandlesAsyncSuccess() throws Exception {
        CompletableFuture<Quote> pending = new CompletableFuture<>();
        when(service.quoteAsync("HN")).thenReturn(pending);

        MvcResult first = mockMvc.perform(
                        get("/api/quotes/deferred")
                                .param("region", "HN"))
                .andExpect(request().asyncStarted())
                .andReturn();

        assertTrue(pending.complete(new Quote("HN", 25_000)));

        mockMvc.perform(asyncDispatch(first))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.region").value("HN"))
                .andExpect(jsonPath("$.fee").value(25_000));
    }

    @Test
    void deferredErrorIsMappedToHttp503() throws Exception {
        CompletableFuture<Quote> pending = new CompletableFuture<>();
        when(service.quoteAsync("FAIL")).thenReturn(pending);

        MvcResult first = mockMvc.perform(
                        get("/api/quotes/deferred")
                                .param("region", "FAIL"))
                .andExpect(request().asyncStarted())
                .andReturn();

        assertTrue(pending.completeExceptionally(
                new QuoteUnavailableException(
                        "pricing service unavailable")));

        mockMvc.perform(asyncDispatch(first))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.code")
                        .value("QUOTE_UNAVAILABLE"))
                .andExpect(jsonPath("$.message")
                        .value("pricing service unavailable"));
    }

    @Test
    void missingParameterFailsBeforeAsyncBegins() throws Exception {
        mockMvc.perform(get("/api/quotes/callable"))
                .andExpect(status().isBadRequest())
                .andExpect(request().asyncNotStarted());
    }
}
~~~

Independent pieces of evidence:

1. **callableProducesJsonAfterAsyncDispatch**: `Callable` runs; `asyncResult` yields the expected `Quote`; JSON and content type are verified on the second dispatch.
2. **futureFinishesAtTimeControlledByTest**: the future remains pending after the first pass and is explicitly completed by the test—zero timing assumptions. Final status/body are asserted after dispatch.
3. **deferredHandlesAsyncSuccess**: callback forwards the future's result to `DeferredResult.setResult`, and MVC renders the final response.
4. **deferredErrorIsMappedToHttp503**: callback forwards the future's failure via `setErrorResult`, and advice emits 503 JSON on the second dispatch. This is **not a timeout test**.
5. **missingParameterFailsBeforeAsyncBegins**: missing `@RequestParam` is handled synchronously by MVC before the controller returns an async holder; asserting `asyncNotStarted` is accurate here.

In the MVC slice, `QuoteService` is mocked, so these tests **do not** prove real pricing logic or real service dependencies work. `@MockitoBean` is used instead of plain `@Mock` because the controller requires a **Spring bean** for constructor injection.

## 7. Full Context Test: Real Service, Still Two-Phase MockMvc

**src/test/java/com/example/mvcasync/QuoteFullContextTest.java**

~~~java
package com.example.mvcasync;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class QuoteFullContextTest {
    @Autowired
    private MockMvc mockMvc;

    @Test
    void callableUsesRealService() throws Exception {
        MvcResult first = mockMvc.perform(
                        get("/api/quotes/callable")
                                .param("region", "HN"))
                .andExpect(request().asyncStarted())
                .andExpect(request().asyncResult(
                        new Quote("HN", 25_000)))
                .andReturn();

        mockMvc.perform(asyncDispatch(first))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.region").value("HN"))
                .andExpect(jsonPath("$.fee").value(25_000));
    }

    @Test
    void callableExceptionBecomes503() throws Exception {
        MvcResult first = mockMvc.perform(
                        get("/api/quotes/callable")
                                .param("region", "FAIL"))
                .andExpect(request().asyncStarted())
                .andReturn();

        mockMvc.perform(asyncDispatch(first))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.code")
                        .value("QUOTE_UNAVAILABLE"));
    }
}
~~~

Compared to `@WebMvcTest`, this class loads the real service and real controller inside the same application context. It verifies fee calculation and exception mapping along MVC → service, yet still uses **MockMvc simulated requests**. There is no TCP socket, real browser, or container-level timeout test. To observe real HTTP transport and real timeouts, use `SpringBootTest(webEnvironment = RANDOM_PORT)` with an HTTP client and matching executor/servlet container settings.

## 8. Run Commands and Expected Results

Once the project has a Gradle Wrapper compatible with Spring Boot 3.4.5:

~~~bash
./gradlew clean test
./gradlew test --tests com.example.mvcasync.QuoteControllerWebMvcTest
./gradlew test --tests com.example.mvcasync.QuoteFullContextTest
./gradlew bootRun
~~~

On Windows, replace `./gradlew` with `gradlew.bat`. After `bootRun` starts on the default port, you can try:

~~~bash
curl -i "http://localhost:8080/api/quotes/callable?region=HN"
curl -i "http://localhost:8080/api/quotes/future?region=HCM"
curl -i "http://localhost:8080/api/quotes/deferred?region=HN"
curl -i "http://localhost:8080/api/quotes/callable?region=FAIL"
~~~

Tests are expected to **PASS** when code and environment match the setup; this is an **expectation derived from inspecting the code**, not observed build stdout. Success responses for `HN` should carry `region=HN` and `fee=25000`; `HCM` has `fee=18000`; `FAIL` requests return HTTP 503 with code `QUOTE_UNAVAILABLE`. Jackson does not promise JSON key ordering as a test contract, so assert individual fields with `jsonPath` rather than raw text equality.

## 9. Servlet Timeouts Differ from MockMvc Wait Timeouts

This is the single most common source of confusion:

| Mechanism | Example | Who Triggers It? | What It Proves |
| --- | --- | --- | --- |
| Async request timeout | `new DeferredResult<>(5000L)` | Servlet container / async request machinery | Request expires under real container configuration |
| Test wait for result | `first.getAsyncResult(5000L)` | MockMvc / JUnit test | Maximum duration the test will wait |
| Intentional async error | `pending.completeExceptionally(error)` | Test code or library | Exception mapping when the async result reports a failure |
| Timeout fallback | `DeferredResult.onTimeout(...)` | Request timeout lifecycle | Fallback logic if a real timeout occurs |
| Executor queue saturation | Rejection when pool/queue is full | Thread pool / task submission | Responsiveness under configured load |

If a test creates a pending future, **never completes it**, and calls `getAsyncResult(100L)`, the test fails due to **test wait timeout**. It **does not prove** real clients receive HTTP 504, nor does it guarantee `DeferredResult.onTimeout` ran. In MockMvc, there is no real Servlet container running timers and triggering automatic `ASYNC` dispatches like production.

Illustrative snippet for a timeout fallback (**not part of the runnable project**):

~~~java
DeferredResult<ResponseEntity<String>> result =
        new DeferredResult<>(2_000L);

result.onTimeout(() -> result.setResult(
        ResponseEntity.status(504).body("gateway timeout")));

result.onCompletion(() -> {
    // Release per-request listener or registration.
});
~~~

Callbacks matter only when real timeout events fire. A genuine timeout test needs an embedded Servlet container + HTTP client or test infrastructure simulating that exact lifecycle. Never write `Thread.sleep(2000)` and treat it as standard timeout testing.

### WebAsyncTask and Custom Timeouts

`WebAsyncTask<T>` wraps `Callable<T>` and can configure a per-endpoint timeout, executor, and callbacks. For example, conceptually:

~~~java
@GetMapping("/slow")
public WebAsyncTask<String> slow() {
    return new WebAsyncTask<>(2_000L, () -> slowService.fetch());
}
~~~

There is no `slowService` class in the sample project; this is a **snippet** representing a real service. It does not guarantee the `Callable` finishes in 2 seconds. Define your timeout handler/error response explicitly and test it at the appropriate layer.

## 10. Executors, Servlet Async Support, and Concurrency

Spring MVC uses `AsyncTaskExecutor` to run `Callable`s. MVC's default executor is usually unsuitable for production workloads with blocking calls; production systems should configure bounded thread pools/queues, timeouts, metrics, and explicit rejection policies.

Illustrative configuration snippet (requires Spring configuration / Web MVC imports; not part of the runnable project):

~~~java
@Configuration(proxyBeanMethods = false)
class AsyncMvcConfiguration implements WebMvcConfigurer {
    private final AsyncTaskExecutor executor;

    AsyncMvcConfiguration(
            @Qualifier("mvcTaskExecutor") AsyncTaskExecutor executor) {
        this.executor = executor;
    }

    @Override
    public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
        configurer.setTaskExecutor(executor);
        configurer.setDefaultTimeout(5_000L);
    }

    @Bean("mvcTaskExecutor")
    static ThreadPoolTaskExecutor mvcTaskExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(4);
        pool.setMaxPoolSize(8);
        pool.setQueueCapacity(100);
        pool.setThreadNamePrefix("mvc-async-");
        return pool;
    }
}
~~~

`ThreadPoolTaskExecutor` is a Spring-managed bean whose initialization/shutdown lifecycle is handled by the container. The pool sizes above merely illustrate configuration, not universal performance tuning. Size pools according to traffic, CPU/IO ratio, and backpressure; if workers perform blocking JDBC or HTTP calls, the Servlet thread is freed yet **worker threads remain tied up**.

Servlets and filters must enable `asyncSupported`, and filter mappings may need `DispatcherType.ASYNC`. In typical Spring Boot embedded containers, Spring MVC async works out of the box; if your app customizes servlet/filter registrations or deploys as a WAR, verify those flags and test on the target container.

### ThreadLocal, Security, and Transactions

MDC logging, `SecurityContext`, `RequestAttributes`, and transactions are often thread-bound. Never assume every `ThreadLocal` on the original request thread propagates automatically to the `Callable`/`CompletableFuture` worker thread. Spring Security provides dedicated propagation utilities, while custom MDC or contexts require explicit propagation.

Similarly, `@Transactional` on a request/controller thread does not span worker threads automatically. Place transaction boundaries on the service executed inside the worker when DB work needs a transaction, and back it with integration tests. Seeing 200 in MockMvc proves nothing about transaction isolation, security context propagation, or cancellation.

## 11. Error Handling, Late Completion, and Client Disconnects

`DeferredResult.setResult` and `setErrorResult` return a `boolean` indicating whether setting the outcome succeeded. If an async request already timed out or completed, a late callback can no longer change the response. With `CompletableFuture`, **`complete`** and **`completeExceptionally`** succeed only once while incomplete; tests can check that boolean return value to detect duplicate or late completions.

Client disconnects do not automatically cancel in-flight background work. Real applications need explicit cancellation/cleanup policies for HTTP clients, event listeners, DB queries, or streams. In Servlet async processing, error, timeout, and completion callbacks can race; never assume setting a result guarantees the client received it.

For async exceptions, distinguish:

- **Errors before `asyncStarted`:** binding failures, missing `@RequestParam`, or exceptions thrown before returning the async holder. These resolve synchronously as 400/500 and must not be passed to `asyncDispatch`.
- **Errors inside `Callable`:** occur on the worker, are captured by MVC as the async result, and resolve during dispatch.
- **Errors from exceptional future completion:** callbacks may see a `CompletionException` wrapper; unwrap the cause and pass it to `setErrorResult`.
- **Servlet timeouts:** occur only when the async lifecycle genuinely expires; a different mechanism from `completeExceptionally`.
- **Response serialization errors:** the async result may succeed yet JSON serialization fails after dispatch; that is why tests must assert the final body and status.

For `StreamingResponseBody`, `SseEmitter`, or `ResponseBodyEmitter`, chunked writes, flushing, event ordering, `text/event-stream` media type, heartbeats, and client disconnects require separate tests. Single-value JSON tests using `asyncDispatch` do not cover streaming behavior.

## 12. Comparing Spring MVC Async, @Async, and WebFlux

**Spring MVC async** handles an HTTP request under the Servlet asynchronous contract, keeping the response open and re-dispatching to finish. **`@Async`**, by contrast, runs methods asynchronously via Spring AOP and an executor: an `@Async` service can return `CompletableFuture`, yet if the controller immediately calls `join()`, the HTTP request thread still blocks. Conversely, returning `Callable` from an MVC controller does not require `@EnableAsync`.

**Spring WebFlux** runs on a reactive web runtime with different I/O and backpressure semantics. MVC can adapt certain reactive return types, which does not turn MVC into WebFlux. When picking test tools, verify whether the app runs Servlet MVC, reactive WebFlux, or mixes libraries for legacy reasons.

MockMvc requires explicit `asyncDispatch`. When using `WebTestClient` bound to MockMvc or on a reactive stack, the test client can automate follow-up handling where supported; do not copy MockMvc calls verbatim into `WebTestClient`.

## 13. Common Pitfalls and Diagnostics Table

| Symptom | Possible Cause | Right Fix |
| --- | --- | --- |
| `jsonPath` fails on the first `perform` | Final HTTP response has not run through async dispatch | Assert `asyncStarted`, call `asyncDispatch`, then assert JSON |
| `asyncDispatch` reports async not started | Controller returned synchronously or failed before returning async holder | Test the synchronous path; inspect `request().asyncStarted()` |
| Test times out in `getAsyncResult` | Future/`DeferredResult` never completed | Use controlled completion, reasonable wait timeout, avoid `sleep` |
| Passes at `asyncResult` yet JSON is wrong | Skipped message converter or exception resolver | Assert after `asyncDispatch` |
| Future finishes too fast to prove worker execution | Used `completedFuture` after synchronous computation | Test executor/concurrency separately |
| `WebMvcTest` passes yet production service fails | `QuoteService` was mocked with `@MockitoBean` | Add unit and full-context tests |
| 503 test mistaken for real timeout test | Used `completeExceptionally` / `setErrorResult` | Distinguish async failures from Servlet timeouts |
| Servlet async filter skipped on dispatch | Filter mapping lacks `ASYNC` dispatcher type | Check `asyncSupported` and `DispatcherType.ASYNC` |
| Context/security lost on worker | `ThreadLocal` does not propagate automatically | Use supported propagation utilities |
| Thread pool exhausted under load | Blocking tasks saturate threads/queue | Bound pools/queues, run load tests, monitor metrics |
| Work continues after client disconnects | Missing cancellation and cleanup | Design timeouts, cancellation, and resource lifecycles |
| Tests flaky due to `sleep` or timing | Varying CPU scheduling locally vs. CI | Use `Future`, latches, callbacks, controlled completion |

## 14. Testing Strategy and Self-Check Exercises

A well-balanced suite typically includes:

1. **Service unit tests** verifying business rules, inputs, and Java exceptions.
2. **`@WebMvcTest` with controlled futures** verifying `asyncStarted`, `asyncDispatch`, JSON, exception handling, and request validation.
3. **`@SpringBootTest @AutoConfigureMockMvc`** verifying real bean wiring with Spring MVC without starting a server.
4. **`@SpringBootTest(webEnvironment = RANDOM_PORT)`** when verifying the Servlet container, HTTP/networking, async timeouts, filter dispatches, cancellation, and real security context propagation.
5. **Load/concurrency tests** when risks involve executor saturation, latency, throughput, or backpressure.

**A.** A controller returns `Callable`, and the test asserts JSON right on the first `perform`. Is that enough? **No**; you need `asyncDispatch` to verify the final response.

**B.** `request().asyncResult(expectedQuote)` passes. Does that prove final content-type, JSON, and HTTP status are right? **No**; it checks only the intermediate async value.

**C.** A service returns `CompletableFuture.completedFuture(quote())`. Does that guarantee computation ran on a worker thread? **No**; `quote()` executed before constructing the completed future.

**D.** `DeferredResult` receives `setErrorResult(Throwable)` and dispatch returns HTTP 503. Does that prove Servlet timeout works? **No**; that tests async error handling, not the timeout lifecycle.

**E.** `getAsyncResult(100L)` times out. Will real HTTP clients definitely get 504? **No**; the test's wait limit is a separate mechanism.

**F.** Using MockMvc with a `@MockitoBean` service—does it prove the real repository, database, or remote client? **No**, only the controller/MVC layer against a stub.

**G.** Missing a request parameter returns HTTP 400 before the controller runs. Should you expect `asyncStarted`? **No**, this request never enters async processing.

**H.** Servlet async frees the request thread while waiting—does all blocking work disappear? **No**, blocking moves onto workers; executors still need sizing and management.

### Checklist Before Finalizing Async Tests

- Does the return type actually support async, and does the controller reach that branch with the tested inputs?
- Did the first pass assert `asyncStarted`, and is it clear when the async result becomes ready?
- Are futures awaited/completed deterministically without relying on `Thread.sleep`?
- Did you invoke `asyncDispatch` and assert the **final HTTP status, content-type, and body**?
- Do tests cover success, error after `asyncStarted`, and synchronous error before `asyncStarted`?
- When advice exists, is exception mapping verified after dispatch?
- Are MockMvc wait timeouts distinguished from real Servlet container timeouts?
- Are executors and `ThreadLocal`/security/transaction contexts designed for real traffic?
- Are async cancellation, client disconnects, and resource cleanup tested at the proper layer?
- Are mock-service web slices distinguished from real-service full-context tests?
- Are tests independent without leaving pending futures or leaked threads across cases?

**Conclusion:** Testing asynchronous responses in Spring MVC requires understanding **async start → result completion → ASYNC dispatch → HTTP response**. In plain MockMvc, `request().asyncStarted()` and `request().asyncResult(...)` verify the first phase, while `mockMvc.perform(asyncDispatch(result))` verifies the final status and body. Controlled `CompletableFuture` instances keep tests deterministic; real timeouts, networking, threading, and cancellation must be verified with dedicated integration tests when required.

## Official References

- Spring Framework 6.2 — MockMvc Async Requests: https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/hamcrest/async-requests.html
- Spring Framework 6.2 — Asynchronous Requests in Spring MVC: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html
- Spring Framework — MockMvc asyncDispatch API: https://docs.spring.io/spring-framework/docs/6.2.4/javadoc-api/org/springframework/test/web/servlet/request/MockMvcRequestBuilders.html
- Spring Boot 3.4 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.4/reference/testing/spring-boot-applications.html