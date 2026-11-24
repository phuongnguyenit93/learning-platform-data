# asyncStarted with Callable or DeferredResult

Spring MVC supports asynchronous request processing to release the Servlet request thread while the application waits for work to finish. Controllers can return `Callable<T>` or `DeferredResult<T>`. When they do, the request goes through an initial processing phase, switches to async mode, and is dispatched again once the result is ready.

When testing with `MockMvc`, simply calling `perform(...)` and asserting the response immediately like a synchronous request is not enough. You must verify that the request started async processing with `request().asyncStarted()`, capture the `MvcResult` from the initial dispatch, wait for or explicitly complete the result, and then use `asyncDispatch(...)` to simulate the subsequent dispatch and assert the final response.

## 1. Why Does Spring MVC Have Asynchronous Processing?

In the synchronous Servlet model, a request is typically handled on a single Servlet request thread:

1. The container receives an HTTP request and assigns a thread to process it.
2. `DispatcherServlet` invokes the controller.
3. The controller performs its work and returns a result.
4. Spring writes the response.
5. The thread finishes processing the request.

If the controller must wait for a slow task—such as calling an external service or waiting for a result produced on another thread—the request thread may remain occupied while waiting.

Spring MVC asynchronous processing allows a controller to return an asynchronous result type. `DispatcherServlet` initiates async processing via the Servlet API and ends the initial dispatch. Once the result completes, the Servlet request is dispatched again so Spring can process the result and produce the response.

High-level flow:

~~~text
HTTP request
    |
    v
DispatcherServlet / Controller
    |
    | Controller returns Callable or DeferredResult
    v
Spring starts async processing
    |
    +---- Initial dispatch ends
    |
    v
Async task completes
    |
    v
Second async dispatch
    |
    v
Spring processes result / exception
    |
    v
HTTP response
~~~

Async processing does not mean the request completes immediately. It means the initial dispatch yielded control so the result can be completed later. The final response is only produced when the async result is dispatched back through the MVC processing pipeline.

## 2. How Do Callable and DeferredResult Differ?

Both return types enable Spring MVC to process requests asynchronously, but control over completing the result differs:

| Criterion | `Callable<T>` | `DeferredResult<T>` |
|---|---|---|
| Who supplies the result? | Spring runs the `Callable` on an async task executor and takes the return value. | Application code or an external component calls `setResult(...)` when the result is ready. |
| How the controller returns | Returns a `Callable` containing the work to execute. | Creates and returns a `DeferredResult` immediately, then completes it at another time. |
| Best suited for | A task that can be executed by Spring's executor. | Results coming from callbacks, messages, events, long polling, or an application-managed async source. |
| Completion | The `Callable` returns a value or throws an exception. | Call `setResult` or `setErrorResult`. |
| Timeout/callbacks | Can be configured via async support or `WebAsyncTask` when per-task control is needed. | Timeout and callbacks can be set directly on `DeferredResult`. |

Do not think of `Callable` as a response data type. It is a unit of work that Spring will execute. Similarly, `DeferredResult` is a holder representing a result to be supplied later; the controller returns that holder before the final value exists.

## 3. Callable in a Controller

Example controller returning a `Callable`:

~~~java
import java.util.concurrent.Callable;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class GreetingController {

    @GetMapping("/greeting/callable")
    Callable<Greeting> greeting() {
        return () -> new Greeting("Hello from Callable");
    }
}

record Greeting(String message) {}
~~~

Upon receiving the request, Spring MVC accepts the `Callable` and hands execution to the async task executor. When the `Callable` returns a `Greeting`, Spring stores the result and triggers an async dispatch to continue processing the response.

Additional work can be performed inside the `Callable`:

~~~java
@GetMapping("/reports/{id}")
Callable<Report> report(@PathVariable long id) {
    return () -> reportService.generate(id);
}
~~~

In this example, `reportService.generate(id)` runs inside the `Callable` executed by the async executor. Do not place work intended to run asynchronously before the `return` statement, because then the controller performs that work on the request thread before returning.

The following example still executes synchronously in the controller:

~~~java
@GetMapping("/reports/{id}")
Callable<Report> report(@PathVariable long id) {
    Report report = reportService.generate(id);
    return () -> report;
}
~~~

Here, `generate(id)` already ran before the `Callable` was returned. The `Callable` merely returns an already-computed result, so the expensive work is not offloaded to the async executor.

## 4. DeferredResult in a Controller

`DeferredResult<T>` fits when the controller does not directly compute the result inside a `Callable`. The controller returns the `DeferredResult` first, and another component completes it later.

Example service interface returning a `DeferredResult`:

~~~java
import org.springframework.web.context.request.async.DeferredResult;

interface GreetingService {
    DeferredResult<Greeting> loadGreeting();
}
~~~

Controller forwarding the `DeferredResult`:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.async.DeferredResult;

@RestController
class GreetingController {

    private final GreetingService greetingService;

    GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/greeting/deferred")
    DeferredResult<Greeting> greeting() {
        return greetingService.loadGreeting();
    }
}
~~~

An implementation may complete the result from a callback or executor:

~~~java
DeferredResult<Greeting> result = new DeferredResult<>(5_000L);

executor.execute(() -> {
    try {
        Greeting greeting = greetingClient.fetch();
        result.setResult(greeting);
    } catch (Exception exception) {
        result.setErrorResult(exception);
    }
});

return result;
~~~

In this example, the controller or service creates a `DeferredResult` with a 5-second timeout and submits work to an executor. On success, `setResult` supplies the value. On failure, `setErrorResult` passes the exception or error object into Spring MVC's async processing flow.

Important completion and lifecycle methods:

| Method | Meaning |
|---|---|
| `setResult(value)` | Completes the `DeferredResult` with a success value. |
| `setErrorResult(error)` | Completes with an error or exception for Spring to handle. |
| `onTimeout(callback)` | Registers a callback when the `DeferredResult` times out. |
| `onError(callback)` | Registers a callback when the async request encounters an error. |
| `onCompletion(callback)` | Registers a callback when the async request completes. |
| `isSetOrExpired()` | Checks whether the result has been set or the request has expired. |

Do not call `setResult` multiple times expecting every call to overwrite the result. `DeferredResult` accepts only one completion result; once set or expired, subsequent completion calls cannot replace the earlier outcome.

## 5. What Does asyncStarted() Assert?

In `MockMvc`, `request().asyncStarted()` is a matcher asserting that the Servlet request switched to async processing during the execution of the request under test.

Static import:

~~~java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
~~~

Minimal example:

~~~java
mockMvc.perform(get("/greeting/callable"))
    .andExpect(request().asyncStarted());
~~~

This matcher asserts an event in the initial request phase: async processing was started. It does not verify that the final response has the right status, JSON, or body. To verify those, perform an async dispatch and run assertions on the final result.

Spring also provides `request().asyncNotStarted()` to assert that a request did not enter async mode:

~~~java
mockMvc.perform(get("/greeting/synchronous"))
    .andExpect(request().asyncNotStarted())
    .andExpect(status().isOk());
~~~

This is useful when an endpoint is expected to run synchronously or when verifying a branch does not inadvertently switch to async.

One subtle point: a `Callable` may finish very quickly on the executor, even before the test evaluates the next assertion. The request still started async processing. Thus, `asyncStarted()` does not mean the background task is guaranteed to still be running at the exact moment of the assertion.

## 6. Workflow for Testing Async with MockMvc

For an async controller, a test typically involves two `MockMvc` calls:

1. Call the endpoint with `perform(...)` as usual.
2. Assert that the request started async processing with `request().asyncStarted()`.
3. Capture `MvcResult` from the initial dispatch.
4. Wait for or explicitly complete the async result.
5. Call `asyncDispatch(mvcResult)` to simulate the subsequent dispatch.
6. Assert the final status, headers, and response body.

General pattern:

~~~java
MvcResult mvcResult = mockMvc.perform(get("/some-async-endpoint"))
    .andExpect(request().asyncStarted())
    .andReturn();

mockMvc.perform(asyncDispatch(mvcResult))
    .andExpect(status().isOk());
~~~

Required imports:

~~~java
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
~~~

`asyncDispatch(mvcResult)` uses the async result attached to `MvcResult` to perform the next dispatch. If the async result is not yet ready, `MockMvc` waits up to the configured timeout for the request. If the result does not complete within the wait window, the test can fail with a timeout.

Do not call `asyncDispatch` with an `MvcResult` from a synchronous request. Before dispatching, assert `asyncStarted()` so the test explicitly shows that the endpoint uses async processing.

## 7. Complete Callable Test

With `Callable`, the work is executed automatically by Spring via the async executor. Tests do not call `setResult` manually; they simply capture `MvcResult` and dispatch once the `Callable` finishes.

Suppose the controller is:

~~~java
import java.util.concurrent.Callable;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CallableController {

    @GetMapping("/callable")
    Callable<Greeting> greeting() {
        return () -> new Greeting("Hello from Callable");
    }
}

record Greeting(String message) {}
~~~

Test:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class CallableControllerTests {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders
            .standaloneSetup(new CallableController())
            .build();
    }

    @Test
    void dispatchesCallableResult() throws Exception {
        MvcResult initialResult = mockMvc.perform(get("/callable"))
            .andExpect(request().asyncStarted())
            .andReturn();

        mockMvc.perform(asyncDispatch(initialResult))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.message").value("Hello from Callable"));
    }
}
~~~

This test has two separate assertion stages:

- The initial dispatch verifies that the request switched to async processing.
- The subsequent dispatch verifies that Spring converted the `Callable` result into a JSON response.

Writing only:

~~~java
mockMvc.perform(get("/callable"))
    .andExpect(status().isOk());
~~~

does not accurately describe the async flow. The status of the initial dispatch is not the right place to assert the final response of a `Callable`. Capture `MvcResult` and perform async dispatch.

## 8. Testing DeferredResult in a Controlled Way

With `DeferredResult`, tests can explicitly control when the result completes. This makes tests deterministic and independent of how fast or slow a background thread runs.

Controller:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.async.DeferredResult;

@RestController
class DeferredGreetingController {

    private final GreetingService greetingService;

    DeferredGreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/deferred")
    DeferredResult<Greeting> greeting() {
        return greetingService.loadGreeting();
    }
}

interface GreetingService {
    DeferredResult<Greeting> loadGreeting();
}
~~~

Test using Mockito to supply a test-controlled `DeferredResult`:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.request.async.DeferredResult;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class DeferredGreetingControllerTests {

    private GreetingService greetingService;
    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        greetingService = mock(GreetingService.class);
        mockMvc = MockMvcBuilders
            .standaloneSetup(new DeferredGreetingController(greetingService))
            .build();
    }

    @Test
    void dispatchesDeferredResultAfterItIsCompleted() throws Exception {
        DeferredResult<Greeting> pendingResult = new DeferredResult<>();
        when(greetingService.loadGreeting()).thenReturn(pendingResult);

        MvcResult initialResult = mockMvc.perform(get("/deferred"))
            .andExpect(request().asyncStarted())
            .andReturn();

        pendingResult.setResult(new Greeting("Hello from DeferredResult"));

        mockMvc.perform(asyncDispatch(initialResult))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message")
                .value("Hello from DeferredResult"));
    }
}
~~~

The key point is that the test only calls `asyncDispatch` after calling `pendingResult.setResult(...)`. Dispatching before the `DeferredResult` completes forces `MockMvc` to wait and may time out. Holding onto the `DeferredResult` in the test gives exact control over when the result becomes ready.

In a real application, `setResult` is typically called by a callback from an async client, a message listener, or another component. Tests do not necessarily need to spin up that entire external system when the goal is to verify how the controller integrates with `DeferredResult`.

## 9. Inspecting the Async Result Before the Second Dispatch

Beyond asserting the final response, you can assert the generated async result value. `MockMvc` provides the `request().asyncResult(...)` matcher:

~~~java
mockMvc.perform(get("/callable"))
    .andExpect(request().asyncStarted())
    .andExpect(request().asyncResult(
        new Greeting("Hello from Callable")
    ));
~~~

Or read the result directly from `MvcResult`:

~~~java
MvcResult initialResult = mockMvc.perform(get("/callable"))
    .andExpect(request().asyncStarted())
    .andReturn();

Object asyncValue = initialResult.getAsyncResult(5_000L);
~~~

`getAsyncResult(timeout)` waits up to the specified milliseconds to retrieve the async result. If the result is not available within that window, the method can throw a timeout error. Pass an explicit timeout when you want a clear wait bound in the test.

If you only need to verify the response without inspecting the intermediate object, `asyncDispatch` is usually sufficient. If you want to verify the exact object produced by the `Callable` or `DeferredResult` before Spring serializes it, inspect the async result directly.

## 10. asyncStarted Does Not Mean the Async Result Has Completed

Distinguish these four states:

| State | Meaning |
|---|---|
| Async started | The request switched to async mode; the initial dispatch ended. |
| Async result ready | The `Callable` returned or the `DeferredResult` had its result/error set. |
| Async dispatch occurred | The request was re-processed so Spring could create the final response. |
| Request completed | The final response was created and the async lifecycle ended. |

With a very fast `Callable`, the async result may be ready almost immediately. With `DeferredResult`, the request may wait longer until an application component calls `setResult`. Both still make `asyncStarted()` succeed.

Therefore, tests should assert the right phase:

- `asyncStarted()`: asserts the request switched to async.
- `getAsyncResult(timeout)` or async result matchers: assert the intermediate value is ready.
- `asyncDispatch(...)`: sends the result back through the MVC pipeline.
- `status()`, `jsonPath()`, `content()`: assert the final response.

## 11. Testing Timeouts and Errors on DeferredResult

`DeferredResult` can be initialized with a timeout. When the time elapses without a result, Spring MVC handles the async timeout. The application can register a callback to record it or set an error result:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.context.request.async.DeferredResult;

DeferredResult<Greeting> result = new DeferredResult<>(5_000L);

result.onTimeout(() -> result.setErrorResult(
    new ResponseStatusException(
        HttpStatus.SERVICE_UNAVAILABLE,
        "Greeting service timed out"
    )
));
~~~

When the async result fails, Spring continues processing the exception during async dispatch. Mechanisms like `@ExceptionHandler`, `@ControllerAdvice`, and `HandlerExceptionResolver` can still participate in producing the error response.

You can complete a `DeferredResult` with an application error:

~~~java
result.setErrorResult(
    new ResponseStatusException(
        HttpStatus.BAD_GATEWAY,
        "Upstream service failed"
    )
);
~~~

In tests, prefer driving the error result directly rather than waiting for a real timeout:

~~~java
DeferredResult<Greeting> pendingResult = new DeferredResult<>();
when(greetingService.loadGreeting()).thenReturn(pendingResult);

MvcResult initialResult = mockMvc.perform(get("/deferred"))
    .andExpect(request().asyncStarted())
    .andReturn();

pendingResult.setErrorResult(
    new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE)
);

mockMvc.perform(asyncDispatch(initialResult))
    .andExpect(status().isServiceUnavailable());
~~~

This example assumes the application is configured to handle `ResponseStatusException` appropriately. If the application has a `@ControllerAdvice` converting errors to a custom response envelope, write assertions matching the application's actual error contract.

Do not write timeout tests by sleeping for a fixed duration hoping a timeout fires on schedule. That easily causes flaky tests due to machine speed and thread scheduling. Control result completion directly or use an intentionally short timeout paired with proper synchronization.

## 12. DeferredResult Callbacks

`DeferredResult` provides callbacks for observing its lifecycle:

~~~java
DeferredResult<Greeting> result = new DeferredResult<>(5_000L);

result.onTimeout(() -> {
    // Log timeout or complete with an appropriate error.
});

result.onError(error -> {
    // Log error during async processing.
});

result.onCompletion(() -> {
    // Clean up resources attached to the async request.
});
~~~

The callbacks serve different purposes:

- `onTimeout` is invoked when the async request times out.
- `onError` is invoked when async processing encounters an error.
- `onCompletion` is invoked when the async request completes, including normal completion or termination due to error/timeout.

Do not put core business logic inside `onCompletion`, as this callback represents the technical request lifecycle. When you need to verify business success, rely on the result or domain events instead.

In tests, you can verify a callback ran using a spy or latch, but do so only when the callback itself is the behavior under test. For basic controller tests, asserting `asyncStarted` and the final response is usually enough.

## 13. Configuring Timeouts and Executors

Spring MVC uses an async task executor to run `Callable` instances. Executor configuration affects concurrency capacity, task queuing, and how the application behaves under load.

In Spring MVC Java configuration, async support can be configured as follows:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class WebAsyncConfiguration implements WebMvcConfigurer {

    @Bean
    ThreadPoolTaskExecutor mvcAsyncExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("mvc-async-");
        return executor;
    }

    @Override
    public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
        configurer.setTaskExecutor(mvcAsyncExecutor());
        configurer.setDefaultTimeout(10_000L);
    }
}
~~~

This example illustrates configuring an executor and default timeout; in a real application, the executor should be managed as a Spring bean so Spring manages its lifecycle and shutdown. When configuring a custom executor, carefully size threads, queue capacity, and rejection policies for the application's load.

`MockMvc` can configure a default async request timeout:

~~~java
MockMvc mockMvc = MockMvcBuilders
    .standaloneSetup(controller)
    .setAsyncRequestTimeout(5_000L)
    .build();
~~~

This timeout affects how long `MockMvc` waits for an async result during a test. It does not replace business client timeouts, `DeferredResult` timeouts, or Servlet container timeout settings. These timeouts live at different layers and must be designed consistently.

## 14. Common Mistakes When Testing Async

### Asserting Status Only on the First Dispatch

An async request has not produced its final response on the initial dispatch. Capture `MvcResult`, then use `asyncDispatch` to assert the final status and body.

### Forgetting to Assert asyncStarted

If an endpoint accidentally reverts to synchronous execution, a test might miss the behavioral regression. Add `request().asyncStarted()` when async processing is part of the contract under test.

### Calling asyncDispatch on a Synchronous Request

`asyncDispatch` requires an `MvcResult` from a request that started async processing. If a request is synchronous, assert the response directly on the first `perform` call and use `asyncNotStarted()` if you want to enforce that fact.

### Leaving DeferredResult Uncompleted

If a test holds a `DeferredResult` without calling `setResult` or `setErrorResult`, async dispatch has to wait until it times out. Keep a reference to the `DeferredResult` in the test and complete it explicitly before dispatching.

### Assuming Callable Always Finishes Before Assertions

`Callable` runs on an async executor. Completion timing depends on the executor and workload. Use `asyncDispatch` or `getAsyncResult(timeout)` for bounded waiting instead of relying on incidental execution speed.

### Using Sleep to Synchronize Tests

Sleeping does not guarantee a task has finished. With `DeferredResult`, call `setResult` directly. With `Callable`, let `MockMvc` wait for the async result up to its timeout or use a latch if coordinating an external task.

### Confusing asyncStarted with Response Streaming

Async processing of `Callable`/`DeferredResult` allows a response to be created after work finishes. That does not automatically mean the server is streaming response chunks. Streaming mechanisms like `ResponseBodyEmitter` or `SseEmitter` have their own lifecycles and testing approaches.

### Confusing Async Requests with @Async

`@Async` is a mechanism for running methods on a Spring executor. Async requests in Spring MVC are a Servlet request lifecycle mechanism allowing a request to be dispatched again once a result is ready. The two can be used together, but they are not synonymous. Putting `@Async` on a service method does not automatically switch an MVC request into async mode; the controller must return a type supported by Spring MVC for async processing or integrate the result appropriately.

## 15. Choosing Assertions by Test Goal

| Goal | How to verify |
|---|---|
| Verify controller actually starts async | `request().asyncStarted()` |
| Verify endpoint remains synchronous | `request().asyncNotStarted()` |
| Verify Callable/DeferredResult value is ready | `MvcResult.getAsyncResult(timeout)` or async result matcher |
| Simulate dispatch after async completes | `asyncDispatch(mvcResult)` |
| Verify success response | `status().isOk()`, `content()`, `jsonPath()` after `asyncDispatch` |
| Verify error result | Complete `DeferredResult` with `setErrorResult`, then assert error response after `asyncDispatch` |
| Verify timeout | Configure an explicit timeout and test corresponding error handling; avoid arbitrary sleeps |

When testing `Callable`, Spring takes responsibility for executing the work and feeding the result to async dispatch. When testing `DeferredResult`, the test can usually control when the result is supplied. In both cases, `asyncStarted()` verifies the first stage of the request, while `asyncDispatch(...)` sends the result through MVC to generate the final response.

Understanding these two stages helps `MockMvc` tests accurately model the asynchronous request lifecycle, catch controllers accidentally executing synchronously, and reliably assert success or error responses once the background work finishes.
