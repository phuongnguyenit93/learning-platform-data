# asyncDispatch to Assert Results After Completion

## Why Is asyncDispatch Needed in MVC Testing?

Spring MVC allows controllers to handle requests asynchronously using return types such as **Callable**, **DeferredResult**, **WebAsyncTask**, and **CompletionStage**. With these types, a controller can kick off work and return control to the Servlet container before the result is ready. Once the work finishes, Spring MVC resumes processing the result and builds the HTTP response.

When testing with `MockMvc`, an asynchronous request has two observable phases:

1. The initial request passes through `DispatcherServlet` and the controller. Spring starts async processing, and the initial dispatch ends before the final result has been written to the response.
2. Once the asynchronous result is ready, the test performs an async dispatch so Spring MVC continues processing the result, runs return value handlers, and completes the response.

**asyncDispatch(mvcResult)** supports the second phase. It uses the `MvcResult` obtained from the initial request to trigger a follow-up dispatch within the same `MockMvc` execution flow. This lets the test verify the final HTTP status, headers, and body after the async work completes.

The key point is that **request().asyncStarted()** and **asyncDispatch(...)** serve two different purposes:

- **request().asyncStarted()** verifies that the request switched to asynchronous processing mode.
- **asyncDispatch(mvcResult)** continues processing the completed result to produce the final response.

Merely verifying that async started does not prove the controller returns the right response. To test the MVC result after completion, the test must perform an async dispatch and place response assertions on that dispatch.

## Testing Flow with MockMvc

Basic sequence:

~~~text
mockMvc.perform(initial request)
        |
        v
DispatcherServlet invokes controller
        |
        v
Controller returns Callable / DeferredResult / other async type
        |
        v
Spring starts async processing
        |
        v
MvcResult records async state
        |
        v
Async result is supplied
        |
        v
mockMvc.perform(asyncDispatch(mvcResult))
        |
        v
Spring MVC processes result and completes response
        |
        v
Assert status, headers, content type, and body
~~~

In code, **asyncDispatch** is statically imported from `MockMvcRequestBuilders`; the **asyncStarted()** matcher lives on `MockMvcResultMatchers.request()`:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
~~~

Always retain the `MvcResult` from the first request. That object holds the state `MockMvc` needs to continue dispatching the same request that entered async mode.

## Testing a Controller Returning Callable

`Callable<T>` is the most straightforward case: Spring MVC runs the callable on an async task executor, captures the return value, and dispatches the result to complete the response.

Example controller returning a string:

~~~java
import java.util.concurrent.Callable;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ReportController {

    @GetMapping("/api/report")
    Callable<String> report() {
        return () -> "report-ready";
    }
}
~~~

The test needs two `perform` calls:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class ReportControllerTests {

    // Assume mockMvc is configured with ReportController.

    @Test
    void returnsTheCompletedCallableResult() throws Exception {
        MvcResult mvcResult = mockMvc.perform(get("/api/report"))
                .andExpect(request().asyncStarted())
                .andReturn();

        mockMvc.perform(asyncDispatch(mvcResult))
                .andExpect(status().isOk())
                .andExpect(content().string("report-ready"));
    }
}
~~~

On the first `perform`, the test only asserts that the request started async processing and captures `MvcResult`. On the second `perform`, `asyncDispatch(mvcResult)` feeds the callable's result through the rest of Spring MVC's processing. Therefore, status and body are asserted on the second dispatch.

Do not place final body assertions on the first request and assume `asyncStarted()` means the response is already complete. At that point, the request has only entered async mode; the result may not be ready and the final response has not been built yet.

## Testing DeferredResult When the Test Explicitly Completes the Result

`DeferredResult<T>` fits when the result is supplied by another component, such as a callback, message listener, or task-managing service. The controller returns the `DeferredResult` immediately, while the result producer calls `setResult(...)` or `setErrorResult(...)` when work finishes.

Example controller delegating report generation to a service:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.async.DeferredResult;

@RestController
class DeferredReportController {

    private final ReportService reportService;

    DeferredReportController(ReportService reportService) {
        this.reportService = reportService;
    }

    @GetMapping("/api/report/deferred")
    DeferredResult<String> report() {
        return reportService.generate();
    }
}
~~~

In the test, create a test-controlled `DeferredResult`. After the initial request returns and `asyncStarted()` is verified, the test completes the deferred result and performs async dispatch:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.web.context.request.async.DeferredResult;

import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class DeferredReportControllerTests {

    // reportService is a mock; mockMvc is configured with this controller.

    @Test
    void dispatchesAfterDeferredResultIsCompleted() throws Exception {
        DeferredResult<String> deferredResult = new DeferredResult<>();
        given(reportService.generate()).willReturn(deferredResult);

        MvcResult mvcResult = mockMvc.perform(get("/api/report/deferred"))
                .andExpect(request().asyncStarted())
                .andReturn();

        deferredResult.setResult("deferred-report-ready");

        mockMvc.perform(asyncDispatch(mvcResult))
                .andExpect(status().isOk())
                .andExpect(content().string("deferred-report-ready"));
    }
}
~~~

The test does not need to wait with an arbitrary sleep. It explicitly supplies the result via `setResult(...)` and then tells `MockMvc` to continue dispatching. This gives precise control over completion timing and avoids depending on the speed of an external system.

In real applications, tests might complete the `DeferredResult` via a callback or service API instead of calling `setResult` directly. What must be ensured is that the result has been set before performing async dispatch.

## Inspecting the Raw Async Value Before Dispatching

`MvcResult` also allows reading the concurrent result produced by asynchronous processing. The **request().asyncResult(...)** matcher can verify that value before continuing with the dispatch:

~~~java
MvcResult mvcResult = mockMvc.perform(get("/api/report"))
        .andExpect(request().asyncStarted())
        .andExpect(request().asyncResult("report-ready"))
        .andReturn();

mockMvc.perform(asyncDispatch(mvcResult))
        .andExpect(status().isOk())
        .andExpect(content().string("report-ready"));
~~~

The `asyncResult(...)` assertion checks the value returned by the async process. Assertions after `asyncDispatch(...)` check the HTTP response constructed by Spring MVC from that value. These two assertions verify different layers:

- Raw async value: the result from `Callable`, `DeferredResult`, or an equivalent async type.
- Final MVC outcome: status, headers, content type, and body after Spring processes the return value.

With `DeferredResult`, only use the `asyncResult(...)` matcher after the producer has called `setResult(...)` or `setErrorResult(...)`. If not yet completed, the matcher must wait for the result and may time out.

You do not have to assert both layers in every test. If the target is the HTTP contract, assertions on the async dispatch are usually the most important part. Inspecting the raw async result is helpful when separating failures in the background task from failures in converting the result to a response.

## Asserting JSON Responses After Async Dispatch

If a controller returns a DTO or `ResponseEntity`, Spring MVC still uses `HttpMessageConverter`s to build the response once the async result is dispatched. You can assert JSON using standard matchers on the second dispatch:

~~~java
MvcResult mvcResult = mockMvc.perform(get("/api/report/summary"))
        .andExpect(request().asyncStarted())
        .andReturn();

mockMvc.perform(asyncDispatch(mvcResult))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
        .andExpect(content().json("""
                {
                  "reportId": 42,
                  "state": "READY"
                }
                """, true));
~~~

No separate matcher suite is needed for async responses. Once async dispatch runs, tests use `status()`, `header()`, `content()`, and `jsonPath()` just like regular MVC responses.

## Handling Errors and Timeouts in Async Requests

An asynchronous result can be an error instead of a success value. For example, a `Callable` throws an exception or a `DeferredResult` is completed with `setErrorResult(...)`. When async dispatch resumes, Spring MVC processes the exception through the active exception resolvers, `@ExceptionHandler`, or `@ControllerAdvice`.

Example where a service returns a `DeferredResult` and the test completes it with an error:

~~~java
DeferredResult<String> deferredResult = new DeferredResult<>();
given(reportService.generate()).willReturn(deferredResult);

MvcResult mvcResult = mockMvc.perform(get("/api/report/deferred"))
        .andExpect(request().asyncStarted())
        .andReturn();

deferredResult.setErrorResult(new IllegalStateException("Report failed"));

mockMvc.perform(asyncDispatch(mvcResult))
        .andExpect(status().isInternalServerError())
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.code").value("REPORT_FAILED"));
~~~

The status and JSON in the example above depend on the application's `@ControllerAdvice` mapping `IllegalStateException` to that error response. If the application uses a different exception mapping, assertions must reflect that contract. The goal is to verify the response after the exception is handled during the follow-up dispatch.

Async requests can also time out. `DeferredResult` can be created with a timeout and a timeout callback; `WebAsyncTask` also supports its own timeout. If you need to test timeouts, control the timeout via explicit configuration or callbacks, then verify the final response via async dispatch. Do not rely on `Thread.sleep(...)` to guess when a timeout happens.

`MockMvc` can configure the async request wait timeout using `setAsyncRequestTimeout(...)` on the builder, for example:

~~~java
MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(controller)
        .setAsyncRequestTimeout(5_000L)
        .build();
~~~

This wait time sets a limit for how long `MockMvc` waits for an async result in the test. It does not replace the business timeout of `DeferredResult` or `WebAsyncTask`; the two timeouts serve different purposes. When a test fails because no result arrived, determine whether the task never completed, the task timed out, or the test's wait limit expired.

## Key Points to Watch When Using asyncDispatch

### Capture MvcResult from a Request That Started Async

`asyncDispatch(...)` requires the `MvcResult` from the initial request. If the request did not switch to async processing, calling async dispatch is invalid and will fail. The `request().asyncStarted()` matcher catches early whether the controller actually initiated async processing.

### Do Not Re-Call the Endpoint to Fetch the Result

The second dispatch must use `asyncDispatch(mvcResult)`, not `get("/api/report")` again. Calling the endpoint again creates a brand new request, may kick off a new task, and does not test the outcome of the original request.

### Place Response Assertions on the Final Dispatch

The first call verifies async started and captures `MvcResult`. The second call verifies the final response. Separating the two phases helps tests pinpoint whether a failure occurred during async initialization or final MVC processing.

### Ensure the Result Actually Completes

With `Callable`, Spring manages execution and provides the concurrent result. With `DeferredResult`, the application or test must call `setResult(...)` or `setErrorResult(...)`. If no result arrives before the wait limit, async dispatch can time out or fail.

### Do Not Use Thread.sleep to Synchronize Tests

`Thread.sleep(...)` only delays the test thread; it does not prove a background task finished. Prefer controlling `DeferredResult`, `CompletableFuture`, a latch, or an observable completion signal. When testing a genuinely background task, wait for completion with a bounded timeout so the test never hangs indefinitely.

### Distinguish MVC Processing from Real Servlet Container Behavior

`MockMvc` tests Spring MVC integration in a simulated Servlet environment. It is ideal for verifying that `Callable` or `DeferredResult` is dispatched and converted into the right response. However, this test does not replace testing on a real embedded server if you need to verify container-specific behavior, sockets, connectors, thread pools, or async filter execution in a real runtime environment.

## Complete Async Testing Workflow

1. Send the initial request using `mockMvc.perform(...)`.
2. Verify the request started async with `request().asyncStarted()`.
3. Save `MvcResult` using `andReturn()`.
4. Ensure the async work has produced a result. With `DeferredResult`, the test or callback calls `setResult(...)` / `setErrorResult(...)`.
5. If you need to separate the task's output from the MVC response, also inspect `request().asyncResult(...)` or `mvcResult.getAsyncResult(...)` with an appropriate timeout.
6. Call `mockMvc.perform(asyncDispatch(mvcResult))`.
7. Assert the final status, headers, content type, and body using regular MVC matchers.

`asyncDispatch` is the bridge between an asynchronous result and the final Spring MVC response. When a test cleanly separates the initial request, completion timing, and the follow-up dispatch, it can accurately verify both the async state and the HTTP contract the client actually receives.
