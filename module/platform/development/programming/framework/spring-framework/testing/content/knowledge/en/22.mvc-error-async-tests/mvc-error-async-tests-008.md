# Timeouts and Exceptions in Asynchronous Processing

## 1. The Asynchronous Lifecycle in Spring MVC

Spring MVC supports controllers returning asynchronous types such as `Callable`, `DeferredResult`, and `WebAsyncTask`. When encountering one of these types, Spring initiates Servlet asynchronous processing, allowing the container thread to finish initial handling while the result is still being produced.

Once the result is ready, Spring MVC performs a follow-up dispatch to complete response processing through MVC components such as return value handlers, message converters, and exception resolvers. Thus, asynchronous processing remains within the HTTP request lifecycle; it simply decouples when the result is produced from the initial thread.

High-level flow:

```text
HTTP request
    |
    v
DispatcherServlet invokes controller
    |
    v
Controller returns Callable / DeferredResult / WebAsyncTask
    |
    v
Spring starts Servlet async and releases initial thread
    |
    +-------------------------------+
    |                               |
    v                               v
Result arrives before timeout   Timeout or error occurs
    |                               |
    v                               v
Store async result              Produce timeout/error result
    |                               |
    +---------------+---------------+
                    |
                    v
          Async dispatch into MVC
                    |
                    v
          Produce final HTTP response
```

Timeouts determine how long a request is permitted to remain in the async state. Exceptions determine how MVC translates an error during processing into a response. The two issues are related but distinct: a request can time out without any business exception, and a task can throw an exception before the timeout expires.

## 2. Sources of Timeouts to Distinguish

Multiple time limits can coexist within a single asynchronous request:

| Timeout type | Scope | Meaning |
|---|---|---|
| MVC async request timeout | Servlet async lifecycle managed by Spring MVC | Limits how long to wait for the result of a `Callable`, `DeferredResult`, or other async type. |
| Per-request timeout | `DeferredResult` or `WebAsyncTask` | Overrides or defines a dedicated timeout for a single execution. |
| Container timeout | Servlet container | Async request limit at the container layer; default depends on server/container configuration. |
| Business deadline | Application logic or downstream services | Business time limit, e.g., waiting for an external service for at most a few seconds. |
| Client timeout | HTTP client, gateway, or reverse proxy | Caller-side wait limit for the response; may be shorter than the server-side timeout. |

These timeouts can all act on the same request. For example, a gateway might stop waiting after 3 seconds while the server is still running a task with a 5-second deadline. When designing, align timeouts across the entire call chain and leave room for the server to handle errors, finalize responses, and write logs.

Never assume every timeout automatically cancels running work. An HTTP response timing out does not guarantee database queries, service calls, or background tasks have stopped. If work must be stopped, the application needs an explicit cancellation or deadline mechanism, and the task must cooperate with it.

## 3. Configuring a Default Timeout for Spring MVC

You can set a default timeout for async requests via `WebMvcConfigurer` and `AsyncSupportConfigurer`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class MvcAsyncConfiguration implements WebMvcConfigurer {

    @Override
    public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
        configurer.setDefaultTimeout(10_000L);
    }
}
```

The value is in milliseconds; the example above sets a default timeout of 10 seconds. If unconfigured, the timeout may depend on Servlet container defaults and runtime configuration. Therefore, applications should declare the desired timeout explicitly rather than relying on an uncontrolled default.

`AsyncSupportConfigurer` also lets you configure an `AsyncTaskExecutor` for `Callable` tasks. The executor needs thread and queue bounds suited to expected load. An unbounded executor can exhaust resources when many requests wait concurrently; an executor that is too small or has an overly long queue can cause tasks to spend most of the timeout waiting before they even start.

The default timeout is a global policy. For an endpoint with different processing characteristics, consider a per-request timeout that reflects that endpoint's requirements.

## 4. Per-Request Timeouts with `DeferredResult`

`DeferredResult<T>` works well when the result is completed by another component, such as a callback from a message broker, event listener, or asynchronous service. The controller returns `DeferredResult` immediately, and the application calls `setResult(...)` when data arrives.

You can specify a timeout via the constructor and register a timeout callback:

```java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.async.DeferredResult;

@RestController
class JobController {

    private final JobService jobService;

    JobController(JobService jobService) {
        this.jobService = jobService;
    }

    @GetMapping("/jobs/latest")
    DeferredResult<ResponseEntity<JobView>> latestJob() {
        DeferredResult<ResponseEntity<JobView>> result =
                new DeferredResult<>(3_000L);

        result.onTimeout(() -> result.setErrorResult(
                new JobWaitTimeoutException("No job result arrived in time")));

        jobService.findLatestAsync(
                job -> result.setResult(ResponseEntity.ok(job)),
                error -> result.setErrorResult(error));

        return result;
    }
}
```

`JobService` in the example represents an application component that can invoke a success callback or error callback when work completes. `JobView` is the application's response data type. `JobWaitTimeoutException` is an application-defined business exception.

The `onTimeout` callback is invoked when the async request times out. The callback can supply a fallback result with `setResult(...)` or switch to the error handling path with `setErrorResult(...)`. The example chooses the second option so an exception resolver determines the error response.

`setResult(...)` and `setErrorResult(...)` return a boolean indicating whether the result was accepted. This is useful when completion callbacks and timeout callbacks can fire nearly simultaneously. Only one outcome is accepted; the application should handle late-arriving results according to its policy rather than assuming every call succeeds.

If no timeout callback is registered, or the callback sets no result, Spring MVC continues handling the timeout via its default mechanism, typically through `AsyncRequestTimeoutException` and the `HandlerExceptionResolver` chain.

## 5. Per-Request Timeouts with `WebAsyncTask`

`WebAsyncTask<T>` wraps a `Callable<T>` and lets you declare a timeout alongside callbacks for timeout, error, and completion. It is a good choice when the controller wants to specify the timeout and fallback behavior for a `Callable` task itself.

```java
import java.util.concurrent.Callable;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.async.WebAsyncTask;

@RestController
class ReportController {

    private final ReportService reportService;

    ReportController(ReportService reportService) {
        this.reportService = reportService;
    }

    @GetMapping("/reports/summary")
    WebAsyncTask<ResponseEntity<String>> summary() {
        Callable<ResponseEntity<String>> work =
                () -> ResponseEntity.ok(reportService.buildSummary());

        WebAsyncTask<ResponseEntity<String>> task =
                new WebAsyncTask<>(2_000L, work);

        task.onTimeout(() -> ResponseEntity
                .status(HttpStatus.GATEWAY_TIMEOUT)
                .body("Report generation timed out"));

        task.onError(() -> ResponseEntity
                .status(HttpStatus.SERVICE_UNAVAILABLE)
                .body("Report generation failed"));

        return task;
    }
}
```

In the example, the timeout callback returns a fallback response with status `504`. The error callback returns a `503` response. This is an illustrative API policy; applications should choose statuses and bodies matching their domain semantics and HTTP contract. If the timeout callback supplies no fallback result, Spring MVC handles the timeout via the normal exception path.

`WebAsyncTask` can also take the name of a registered executor to run the `Callable`. When using a custom executor, inspect the executor configuration and capacity under load; a request timeout is no substitute for thread pool management.

## 6. Handling Exceptions from `Callable` and `DeferredResult`

With `Callable`, exceptions thrown inside the task are captured by Spring MVC as the async result. When async dispatch resumes, the exception passes through MVC error resolution. Therefore, you can use `@ExceptionHandler` or `@ControllerAdvice` just as in synchronous processing.

With `DeferredResult`, the application callback must forward errors via `setErrorResult(exception)`. Exceptions thrown on an event listener or another thread are not automatically thrown onto the original request-processing thread. If an exception simply escapes a callback on a background thread, MVC may have no idea the waiting request needs to return an error.

Example declaring centralized exception handlers:

```java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

record ApiError(String code, String message) {
}

@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(JobWaitTimeoutException.class)
    ResponseEntity<ApiError> handleJobTimeout(JobWaitTimeoutException ex) {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(new ApiError("JOB_WAIT_TIMEOUT", ex.getMessage()));
    }

    @ExceptionHandler(ReportUnavailableException.class)
    ResponseEntity<ApiError> handleReportUnavailable(ReportUnavailableException ex) {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(new ApiError("REPORT_UNAVAILABLE", "Report is temporarily unavailable"));
    }
}
```

`JobWaitTimeoutException` and `ReportUnavailableException` are application-defined exception types. Handlers can return `ResponseEntity`, an error DTO, or other response data types. Spring MVC processes that result during the dispatch that completes the async request.

If you want to handle the default timeout exception produced by Spring MVC, declare a handler for `AsyncRequestTimeoutException`:

```java
import org.springframework.web.context.request.async.AsyncRequestTimeoutException;

@ExceptionHandler(AsyncRequestTimeoutException.class)
ResponseEntity<ApiError> handleMvcTimeout(AsyncRequestTimeoutException ex) {
    return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
            .body(new ApiError("ASYNC_REQUEST_TIMEOUT", "The request timed out"));
}
```

This handler should be placed in `@RestControllerAdvice` alongside other appropriate handlers. Which HTTP status to map timeouts to is an API design decision; keep it consistent with timeout semantics that clients can handle.

## 7. Lifecycle Callbacks and Error Handling

`DeferredResult` provides callbacks so the application can observe the async lifecycle:

| Callback | When invoked | Purpose |
|---|---|---|
| `onTimeout(...)` | Async request times out | Set a fallback result or call `setErrorResult(...)`. |
| `onError(...)` | An error occurs during Servlet-layer async processing | Record or react to errors from async processing. |
| `onCompletion(...)` | Async request has completed | Release resources or record end of processing. |

These callbacks do not replace exception handlers. Callbacks manage lifecycle and bridge with asynchronous work; `@ExceptionHandler` is responsible for turning exceptions into responses per MVC policy.

Example registering completion callbacks:

```java
DeferredResult<String> result = new DeferredResult<>(5_000L);

result.onTimeout(() -> result.setErrorResult(
        new JobWaitTimeoutException("The operation took too long")));

result.onError(error -> logger.warn("Async request failed", error));

result.onCompletion(() -> logger.debug("Async request completed"));
```

The snippet assumes `logger` is declared in the class. Do not hold onto resources like locks, connections, or request contexts until the completion callback if those resources can be released earlier. Every branch—success, error, timeout, and cancellation—needs an appropriate cleanup strategy.

## 8. Testing Async Results with MockMvc

For asynchronous requests, `MockMvc.perform(...)` typically returns before the final response is created. The test must verify the request started async, wait for the result to complete, and then perform `asyncDispatch(...)` to assert the final response.

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.mockito.Mockito.when;

@WebMvcTest(ReportController.class)
class ReportControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private ReportService reportService;

    @Test
    void completesAsyncRequest() throws Exception {
        when(reportService.buildSummary()).thenReturn("ready");

        MvcResult result = mockMvc.perform(get("/reports/summary"))
                .andExpect(request().asyncStarted())
                .andReturn();

        result.getAsyncResult(5_000L);

        mockMvc.perform(asyncDispatch(result))
                .andExpect(status().isOk())
                .andExpect(content().string("ready"));
    }
}
```

The `/reports/summary` endpoint in the example returns `WebAsyncTask<ResponseEntity<String>>`; the mocked `ReportService` produces `"ready"`. `getAsyncResult(5_000L)` waits up to 5 seconds to obtain the async result; if no result arrives within that limit, the test fails instead of hanging forever. `asyncDispatch(result)` resumes processing the result through Spring MVC so status and content matchers assert the final response.

Exceptions can be tested similarly: an endpoint returns a `Callable` that throws a business exception, the test verifies `asyncStarted()`, waits for the async result, then calls `asyncDispatch(...)` and asserts the status and body produced by `@RestControllerAdvice`.

For real timeouts, distinguish two things to test:

- Application timeout logic: the timeout callback sets the right error result or fallback response. Callbacks or coordinator units can be tested directly using controllable time or a fake scheduler if the application separates that logic into a replaceable component.
- Servlet container timeout behavior: the request actually expires and the response completes per runtime configuration. Include integration tests running against an embedded Servlet container or a production-equivalent environment, because mock async contexts do not fully emulate every container's timeout scheduling.

Avoid short `Thread.sleep(...)` calls to synchronize tests. That depends on machine load and creates flaky tests. Use `getAsyncResult(timeout)` with a generous wait bound, a latch, or time-control tools suited to your test structure.

## 9. Common Mistakes

| Symptom | Common cause | Fix |
|---|---|---|
| Test checks body right after `perform(...)` and body is not ready | Request entered async mode and has not had a completion dispatch yet. | Assert `asyncStarted()`, wait for `getAsyncResult(...)`, then call `asyncDispatch(...)`. |
| Request times out even though the task eventually finishes | Result arrived after the request timeout limit. | Adjust deadline, optimize task, or return timeout status per API contract. |
| Exception from background thread is not converted to an error response | Async callback did not call `DeferredResult.setErrorResult(...)`. | Pass the exception into `DeferredResult` so MVC continues via exception resolvers. |
| Timeout response does not stop background work | Timeout ends HTTP waiting, but background work may still be running. | Design cancellation/deadlines for tasks and release resources when results are no longer needed. |
| Many async requests slow down under load | Executor lacks threads, queue is too long, or tasks block threads too long. | Configure bounded pools, monitor queues/rejections, and set appropriate concurrency limits. |
| Timeout handler is not invoked as expected | Timeout handled by a separate callback, response already completed, or a different exception type occurred. | Identify which timeout branch applies: `onTimeout` callback, `WebAsyncTask` callback, or `AsyncRequestTimeoutException`. |
| Timeout tests are flaky | Relying on `sleep`, overly tight timeouts, or mock containers not simulating real timeout scheduling. | Control time in unit tests and use an embedded container for real timeout behavior. |

A response can only be created or replaced while processing still permits writing the response. If the response is already committed or the client disconnected, an exception handler cannot guarantee sending a complete error response. Therefore, background task logs and metrics remain essential even when the client can no longer receive the outcome.

## 10. Design Principles for Timeouts and Exceptions

- Set a default timeout in MVC configuration for a baseline policy, and override per request only when business requirements genuinely differ.
- Set deadlines on external dependency calls shorter than or compatible with the overall request deadline, leaving the application time to process results and errors.
- Use `DeferredResult.setErrorResult(...)` when exceptions occur in callbacks or threads other than the initial request-processing thread.
- Use `@ControllerAdvice` to keep error formats consistent between synchronous and asynchronous handling.
- Distinguish timeouts, business errors, infrastructure errors, and client disconnects; each may require different logs, metrics, and HTTP statuses.
- Do not treat HTTP timeouts as a task cancellation mechanism. Design explicit cancellation, deadlines, and cleanup for work that may outlive the request.
- Test async results with `asyncDispatch(...)`; test container timeout scheduling in an environment with a real Servlet container.

## 11. Conclusion

Spring MVC allows configuring a global timeout via `AsyncSupportConfigurer` and per-request timeouts via `DeferredResult` or `WebAsyncTask`. When results arrive late, timeout callbacks can provide fallback results or forward errors via `setErrorResult(...)`. Exceptions from `Callable` and exceptions passed into `DeferredResult` continue through MVC error handling, so `@ControllerAdvice` can standardize responses. When testing, wait for the async result and call `asyncDispatch(...)`; Servlet container timeout behavior should be verified with appropriate integration tests.
