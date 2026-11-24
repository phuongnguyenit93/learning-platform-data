# Asserting Errors or Asynchronous Results

`MockMvcTester` provides an AssertJ API for inspecting Spring MVC requests and responses. For successful requests, tests typically assert status and body. For failing requests or asynchronous processing, you need to understand how the request concluded: whether an exception was resolved by Spring MVC into an HTTP response, an exception escaped the dispatch process, or the request only started async processing and does not yet have a final response.

`MockMvcTester` still runs on the MockMvc infrastructure. It does not alter the processing flow of `DispatcherServlet`, `HandlerExceptionResolver`, or Spring MVC's async mechanism. When you need to inspect async lifecycle details, you can obtain the underlying `MvcResult` and use MockMvc's `asyncDispatch(...)`.

## 1. Three Types of Outcomes to Distinguish

In an MVC test, a "failing request" can refer to different situations:

1. **Resolved exception:** the controller throws an exception, and then `@ExceptionHandler`, `@ControllerAdvice`, or a default resolver translates it into an HTTP response. The test receives a status and body to assert on.
2. **Unresolved exception:** no resolver handles the exception, so the error may escape the dispatch process. MockMvc records an execution failure rather than a normal, completed response.
3. **Async request:** the controller returns `Callable`, `DeferredResult`, `CompletableFuture`, or another async type. The initial dispatch may finish before background work completes; the test must dispatch the async result to inspect the final response.

These three situations cannot be tested with the same assertion. A 500 status, for example, might be a response intentionally created by the application, whereas an unresolved exception can cause the MockMvc call to record a failure.

## 2. Verifying Exceptions Resolved into HTTP Responses

This is the most common situation when a controller uses `@ExceptionHandler` or `@RestControllerAdvice`. The controller throws an exception, but Spring MVC catches and forwards it to the appropriate resolver. `MockMvcTester` receives the HTTP result for AssertJ assertions.

Exception example:

```java
public class OrderNotFoundException extends RuntimeException {

    public OrderNotFoundException(long id) {
        super("Order " + id + " was not found");
    }
}
```

Controller:

```java
@RestController
public class OrderController {

    @GetMapping("/orders/{id}")
    public Map<String, Object> find(@PathVariable long id) {
        if (id == 77L) {
            throw new OrderNotFoundException(id);
        }
        return Collections.<String, Object>singletonMap("id", id);
    }
}
```

Exception handler:

```java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<Map<String, String>> handleNotFound(
            OrderNotFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(Collections.singletonMap("error", exception.getMessage()));
    }
}
```

Test using MockMvcTester:

```java
@WebMvcTest(OrderController.class)
@Import(ApiExceptionHandler.class)
class OrderControllerTest {

    @Autowired
    private MockMvcTester mvc;

    @Test
    void returnsNotFoundWhenOrderDoesNotExist() {
        assertThat(mvc.get().uri("/orders/{id}", 77))
                .hasStatus(HttpStatus.NOT_FOUND)
                .bodyJson()
                .extractingPath("$.error")
                .isEqualTo("Order 77 was not found");
    }
}
```

The test verifies the response received by the client: HTTP 404 and JSON containing the `error` field. Because the exception was resolved, the test does not need to catch it with `assertThrows`.

You can also assert on content type or headers if they are part of the API contract. For validation, authentication, or authorization errors, load the appropriate configuration so the response is produced according to the application's policy.

## 3. Reading the Exception Resolved by Spring MVC

When you need to confirm the original exception type, you can obtain `MvcTestResult` and read the underlying `MvcResult`. `MvcTestResult` represents the execution result of a MockMvcTester request; for a successfully dispatched request, `getMvcResult()` provides the detailed MVC result.

```java
MvcTestResult testResult = mvc.get().uri("/orders/{id}", 77);

assertThat(testResult.getMvcResult().getResolvedException())
        .isInstanceOf(OrderNotFoundException.class);
```

`getResolvedException()` returns the exception recorded during exception resolution, or `null` if no exception was resolved. The exception can appear here even when `@RestControllerAdvice` handled it and a 404 response was successfully produced.

To verify behavior thoroughly, combine exception checks with status and body assertions:

```java
MvcTestResult testResult = mvc.get().uri("/orders/{id}", 77);

assertThat(testResult)
        .hasStatus(HttpStatus.NOT_FOUND)
        .bodyJson()
        .extractingPath("$.error")
        .isEqualTo("Order 77 was not found");

assertThat(testResult.getMvcResult().getResolvedException())
        .isInstanceOf(OrderNotFoundException.class);
```

Assertions on status/body show the observable outcome; the assertion on `getResolvedException()` shows the underlying cause that MVC handled. Do not rely on the exception alone to conclude that the response contract is correct.

## 4. Verifying Unresolved Exceptions

If a controller throws an exception and no `HandlerExceptionResolver` handles it, the exception can escape `DispatcherServlet`. Unlike an exception mapped to a response, this is a request execution failure.

Example endpoint intentionally throwing an unhandled error:

```java
@RestController
public class DiagnosticController {

    @GetMapping("/diagnostics/failure")
    public String fail() {
        throw new IllegalStateException("Unexpected diagnostic failure");
    }
}
```

MockMvcTester retains execution failure details in `MvcTestResult`. You can inspect the failure and its cause with AssertJ:

```java
MvcTestResult testResult = mvc.get().uri("/diagnostics/failure");

assertThat(testResult.getFailure())
        .isNotNull()
        .hasRootCauseInstanceOf(IllegalStateException.class);
```

`getFailure()` is the execution failure recorded by MockMvcTester when the request does not produce a normal dispatch result. Depending on where it occurred, the exception may be wrapped in another exception; therefore, `hasRootCauseInstanceOf(...)` is often more useful than relying on a specific wrapper class.

If the application already has a global exception handler converting `IllegalStateException` into HTTP 500, the request will be resolved and the test should verify the 500 response and body. In that case, do not expect `getFailure()` to contain an unhandled exception.

### Do Not Confuse Error Responses with Test Failures

| Scenario | What the Test Receives | How to Assert |
| --- | --- | --- |
| `@ExceptionHandler` produces HTTP 404 | Normal HTTP result | `hasStatus(HttpStatus.NOT_FOUND)` and inspect body |
| Default resolver maps exception to status | Normal HTTP result | Check status, headers, and body per configuration |
| Exception escapes dispatch | Failure in `MvcTestResult` | Inspect `getFailure()` and root cause |
| Request rejected by Spring Security before controller | Security response such as 401, 403, or redirect | Check status/redirect and filter chain configuration |

An intentionally produced 500 response is still an HTTP response; it is not necessarily a MockMvcTester failure. Conversely, an unresolved exception may require the test to assert on the failure rather than a status.

## 5. Asynchronous Requests in Spring MVC

Controllers can return async results so they do not hold a request thread while waiting for work to finish. Spring MVC supports several return types such as:

- `Callable<T>`: Spring MVC runs the task in an executor and handles the result when the callable completes.
- `DeferredResult<T>`: another component can complete the result later, such as a callback from a service or an event.
- `CompletionStage<T>`/`CompletableFuture<T>`: the result is provided when the future completes.
- `WebAsyncTask<T>`: allows configuring timeout, executor, and callbacks for the async task.

In MockMvc, an async request has two main phases:

1. The initial dispatch invokes the controller and detects that the result is not yet ready. The request enters async mode.
2. When the result completes, the test uses `asyncDispatch(...)` to resume processing the result through `DispatcherServlet` and obtain the final response.

Diagram:

```text
MockMvc request
      |
      v
Initial DispatcherServlet dispatch
      |
      v
Controller returns Callable / DeferredResult / Future
      |
      v
Async started; initial MvcResult returned
      |
      v
Background work completes
      |
      v
asyncDispatch(initialMvcResult)
      |
      v
Final MVC dispatch and response
      |
      v
Assert final status, headers and body
```

`MockMvcTester` can execute the initial request and provide `MvcTestResult`. To explicitly control both phases and use `asyncDispatch`, obtain the underlying `MvcResult` and use MockMvc accordingly.

## 6. Verifying Async Started and Checking the Final Result

Example controller returning `Callable`:

```java
@RestController
public class AsyncOrderController {

    @GetMapping("/async-orders/{id}")
    public Callable<Map<String, Object>> findAsync(@PathVariable long id) {
        return () -> Collections.<String, Object>singletonMap("id", id);
    }
}
```

The test can use MockMvcTester for the initial request, then use MockMvc to dispatch the async result:

```java
@SpringBootTest
@AutoConfigureMockMvc
class AsyncOrderControllerTest {

    @Autowired
    private MockMvcTester mvcTester;

    @Autowired
    private MockMvc mockMvc;

    @Test
    void returnsCompletedAsyncResult() throws Exception {
        MvcTestResult initialResult =
                mvcTester.get().uri("/async-orders/{id}", 12);

        MvcResult initialMvcResult = initialResult.getMvcResult();
        assertThat(initialMvcResult.getRequest().isAsyncStarted()).isTrue();

        mockMvc.perform(asyncDispatch(initialMvcResult))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(12));
    }
}
```

The first execution only confirms that the request switched to async mode. Asserting `isAsyncStarted()` shows that Spring MVC started asynchronous processing; it does not verify that the final response has been written. `asyncDispatch(...)` feeds the completed result back into the dispatch flow so the test can check the final status and JSON.

In this example, `Callable` finishes quickly so the async result is typically ready when `asyncDispatch` is called. With `DeferredResult` or tasks depending on an external callback, the test must complete the deferred result in a controlled way before dispatching. You can use a latch, a test callback, or a fake collaborator to avoid depending on wall-clock time.

### Why Use Both MockMvcTester and MockMvc?

MockMvcTester is convenient for requests and AssertJ-style assertions. MockMvc's async API already has an explicit `asyncDispatch(MvcResult)` mechanism, which is suitable when dispatch lifecycle control is needed. You can use the tester for the initial request, then unwrap `MvcResult` to use the existing async mechanism.

If a test needs many low-level operations such as `asyncDispatch`, `MvcResult`, `request().asyncResult(...)`, or interceptor results, using traditional MockMvc for that part remains reasonable. MockMvcTester does not force every operation into a single assertion chain.

## 7. Verifying Returned Async Values

With a `Callable` returning a value, the final result is processed like a normal MVC response. After async dispatch, you can assert JSON or text using MockMvc matchers:

```java
MvcResult initial = mockMvc.perform(get("/async-orders/12"))
        .andExpect(request().asyncStarted())
        .andReturn();

mockMvc.perform(asyncDispatch(initial))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.id").value(12));
```

If you want to use AssertJ to verify data after async dispatch, retrieve the final `MvcResult` and check the response content or deserialize the body into the desired type:

```java
MvcResult completed = mockMvc.perform(asyncDispatch(initial))
        .andExpect(status().isOk())
        .andReturn();

assertThat(completed.getResponse().getContentAsString())
        .contains("\"id\":12");
```

In a project with `ObjectMapper`, you can deserialize the JSON body into a DTO and assert its properties. This avoids depending on whitespace or field order in JSON.

## 8. Handling Errors in Async Tasks

Async tasks can also fail. For example, a `Callable` throws an exception:

```java
@GetMapping("/async-orders/failure")
public Callable<String> failAsync() {
    return () -> {
        throw new IllegalStateException("Async order lookup failed");
    };
}
```

If a matching `@ExceptionHandler` exists, Spring MVC can resolve the exception during the final async dispatch and produce an HTTP response. The test needs to dispatch the async result and then assert on status/body:

```java
MvcResult initial = mockMvc.perform(get("/async-orders/failure"))
        .andExpect(request().asyncStarted())
        .andReturn();

mockMvc.perform(asyncDispatch(initial))
        .andExpect(status().isInternalServerError())
        .andExpect(jsonPath("$.error").value("Async order lookup failed"));
```

The example assumes the application has exception advice converting `IllegalStateException` into a 500 JSON response with an `error` field. If no suitable resolver exists, async dispatch may throw an exception instead of returning a 500 response. Clarify whether the test is meant to verify a handled error response or an unhandled failure.

With `DeferredResult`, the application can set an exception via `setErrorResult(exception)`. This result goes through Spring MVC's exception handling mechanism during async dispatch. Therefore, test both the successful completion case and the error completion case if both are important business branches.

## 9. Timeouts and Stability of Async Tests

Async tests can become flaky if they depend on real execution timing. Several principles help keep tests controllable:

- Do not use `Thread.sleep(...)` to guess when a task has finished.
- Use `CountDownLatch`, a controllable `CompletableFuture`, or a fake collaborator to synchronize the test with the task.
- Configure an appropriate timeout for the async request if the task can take time.
- Verify that the request actually started async processing before calling `asyncDispatch`.
- Do not call `asyncDispatch` when the request is not yet in async state.
- Check the final response after dispatch, not just the intermediate result.

For example, with `DeferredResult`, the test can hold a reference and complete it after confirming the request has started. In the real application, the value is typically completed by a callback from a service; the test can use a fake service to trigger the callback deterministically.

## 10. Combining MockMvcTester with Exceptions and Async Results

When an async endpoint produces an error result, you can break the test into steps:

1. Use `MockMvcTester` to send the initial request.
2. Retrieve `MvcResult` from `MvcTestResult`.
3. Verify the request started async processing.
4. Complete the async task in the test if callback control is needed.
5. Use `asyncDispatch(initialMvcResult)` to run the final dispatch.
6. Verify the final status and response body.
7. If the exception is resolved, check `getResolvedException()` on the final `MvcResult` when confirming the exception type.

Structure example:

```java
MvcTestResult initialTestResult = mvcTester.get().uri("/async-orders/failure");
MvcResult initialMvcResult = initialTestResult.getMvcResult();

assertThat(initialMvcResult.getRequest().isAsyncStarted()).isTrue();

MvcResult finalResult = mockMvc.perform(asyncDispatch(initialMvcResult))
        .andExpect(status().isInternalServerError())
        .andReturn();

assertThat(finalResult.getResolvedException())
        .isInstanceOf(IllegalStateException.class);
```

The example assumes the async error is resolved by a `HandlerExceptionResolver` into HTTP 500. If the error is unresolved, async dispatch may throw an exception and the test must assert on the failure instead of expecting a final `MvcResult`.

## 11. Choosing Assertions by Outcome Type

| Goal | Recommended API | What Is Verified |
| --- | --- | --- |
| Exception converted by advice to 404 | `hasStatus(HttpStatus.NOT_FOUND)` and `bodyJson()` | Error response received by the client |
| Exception resolved by MVC | `getMvcResult().getResolvedException()` | Exception type recorded during exception resolution |
| Exception escaping dispatch | `getFailure()` | Request execution failure without a normal dispatch response |
| Async request started | `getMvcResult().getRequest().isAsyncStarted()` | Initial dispatch switched into async mode |
| Async result completed | `asyncDispatch(initialMvcResult)` | Final result after async processing |
| Async exception handled by advice | `asyncDispatch(...)` then inspect status/body and resolved exception | Final error response |
| Unhandled async exception | Assert on exception/failure during async dispatch | Error escaping the final dispatch flow |

## 12. Conclusion

With `MockMvcTester`, resolved exceptions are usually tested like normal HTTP responses: verify status, body, and if needed, read `MvcResult.getResolvedException()`. Unresolved exceptions are represented as request failures and can be inspected via `MvcTestResult.getFailure()`.

Asynchronous requests require two phases: the initial dispatch and dispatching the result via `asyncDispatch(...)`. `MockMvcTester` can build the initial request in AssertJ style; when async lifecycle control is required, obtain the underlying `MvcResult` and use MockMvc to complete the dispatch. Always verify the final response and clearly distinguish errors handled by Spring MVC from exceptions that escape the dispatch process.
