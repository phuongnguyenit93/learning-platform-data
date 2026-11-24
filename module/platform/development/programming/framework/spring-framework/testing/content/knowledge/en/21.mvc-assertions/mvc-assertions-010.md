# Selected Handler and Resolved Exception

When testing Spring MVC with `MockMvc`, asserting only the HTTP status and response body is sometimes not enough to confirm that a request went through the right controller. One URL can match multiple mappings, a handler can throw an exception, and Spring MVC can hand that exception off to another component to handle.

Spring MVC Test provides matchers to verify the selected handler. `MvcResult` also lets you inspect the actual handler and the exception resolved by Spring MVC. Combining both pieces of information lets a test answer two separate questions:

- Was the request mapped to the right handler method?
- If the handler threw an exception, did Spring MVC resolve that exception and produce the expected response?

An important point is that the initially selected handler remains the controller method that received the request. An `@ExceptionHandler` or `HandlerExceptionResolver` handling the exception afterward does not replace the original handler value in `MvcResult`.

## 1. Request Processing Flow in Spring MVC

In a typical synchronous request, `DispatcherServlet` coordinates the main components in this general sequence:

1. Receives the request from the Servlet API.
2. Queries `HandlerMapping` instances to find a handler matching the URL, HTTP method, and other mapping conditions.
3. Obtains a `HandlerExecutionChain`, containing the handler and relevant interceptors.
4. Selects an appropriate `HandlerAdapter` to invoke the handler.
5. Executes the controller method and processes the return value.
6. If the controller throws an exception, passes the exception through the `HandlerExceptionResolver` chain.
7. Writes the response or renders the view.

Example controller:

```java
@RestController
public class ProductController {

    @GetMapping("/products/{id}")
    public Map<String, Object> findById(@PathVariable long id) {
        return Collections.singletonMap("id", id);
    }
}
```

For request `GET /products/12`, `RequestMappingHandlerMapping` can select the method `ProductController.findById(long)`. Spring MVC Test records the selected handler in `MvcResult` so tests can verify routing.

## 2. Asserting the Handler with MockMvc Result Matchers

Spring MVC Test provides `handler()` in `MockMvcResultMatchers`. Commonly used matchers include:

- `handler().handlerType(ProductController.class)` asserts the controller class containing the handler method.
- `handler().methodName("findById")` asserts the name of the selected method.
- `handler().methodCall(...)` can assert the handler invocation via a method-call expression when appropriate for the Spring version in use.

Example:

```java
@WebMvcTest(ProductController.class)
class ProductControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void selectsProductHandler() throws Exception {
        mockMvc.perform(get("/products/{id}", 12))
                .andExpect(status().isOk())
                .andExpect(handler().handlerType(ProductController.class))
                .andExpect(handler().methodName("findById"))
                .andExpect(jsonPath("$.id").value(12));
    }
}
```

In this test, status and body verify the HTTP outcome; the two `handler()` matchers verify that Spring MVC selected the intended controller and method. If another mapping accidentally intercepts the request, handler assertions catch the problem even if the response happens to return status 200.

### Conditions That Can Affect Which Handler Is Selected

Spring MVC selects handlers based on mapping conditions, not just the path:

- Path and path variables, such as `/products/{id}`.
- HTTP method such as GET, POST, or DELETE.
- Request parameters declared in the mapping.
- Headers, including `headers` conditions.
- Media types in `consumes` and `produces`.
- Custom mapping conditions defined by the application.

Example of two methods sharing a path with different conditions:

```java
@RestController
@RequestMapping("/reports")
public class ReportController {

    @GetMapping(params = "format=summary")
    public String summary() {
        return "summary";
    }

    @GetMapping(params = "format=detail")
    public String detail() {
        return "detail";
    }
}
```

Tests can verify both the result and the selected method:

```java
mockMvc.perform(get("/reports").param("format", "summary"))
        .andExpect(handler().handlerType(ReportController.class))
        .andExpect(handler().methodName("summary"))
        .andExpect(content().string("summary"));

mockMvc.perform(get("/reports").param("format", "detail"))
        .andExpect(handler().handlerType(ReportController.class))
        .andExpect(handler().methodName("detail"))
        .andExpect(content().string("detail"));
```

These assertions are especially helpful when multiple methods share a path or when an API has mappings conditioned on headers, query parameters, or content types.

## 3. Reading the Handler Directly from MvcResult

If you need to inspect more details beyond built-in matchers, retrieve `MvcResult` using `.andReturn()`:

```java
MvcResult result = mockMvc.perform(get("/products/{id}", 12))
        .andExpect(status().isOk())
        .andReturn();

Object selectedHandler = result.getHandler();
assertThat(selectedHandler).isInstanceOf(HandlerMethod.class);

HandlerMethod handlerMethod = (HandlerMethod) selectedHandler;
assertThat(handlerMethod.getBeanType()).isEqualTo(ProductController.class);
assertThat(handlerMethod.getMethod().getName()).isEqualTo("findById");
```

For annotated controllers such as those using `@GetMapping`, the handler is typically a `HandlerMethod`. This object exposes the bean type, method, and method metadata. However, `MvcResult.getHandler()` returns the general type `Object`: other handler types such as resource handlers may not be `HandlerMethod`.

Therefore, cast to `HandlerMethod` only after checking the object's type. If a test could encounter a resource handler or another handler type, check the type first or use a matcher suited to the expected handler.

`MvcResult` also provides other details such as the request, response, model and view, interceptors, and resolved exception. It is useful when a test needs to analyze multiple facets of a dispatch.

## 4. Selected Handler and Resolved Exception Are Separate Facts

Suppose the controller looks up a product and does not find data:

```java
public class ProductNotFoundException extends RuntimeException {

    public ProductNotFoundException(long id) {
        super("Product " + id + " was not found");
    }
}

@RestController
public class ProductController {

    @GetMapping("/products/{id}")
    public Map<String, Object> findById(@PathVariable long id) {
        if (id == 404L) {
            throw new ProductNotFoundException(id);
        }
        return Collections.<String, Object>singletonMap("id", id);
    }
}
```

A `@RestControllerAdvice` handles the exception:

```java
@RestControllerAdvice
public class ProductExceptionHandler {

    @ExceptionHandler(ProductNotFoundException.class)
    public ResponseEntity<Map<String, String>> handleNotFound(
            ProductNotFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(Collections.singletonMap("message", exception.getMessage()));
    }
}
```

When `GET /products/404` is processed, `ProductController.findById` is still the handler that received the request. That method throws `ProductNotFoundException`; Spring MVC then locates an exception resolver that can handle it. `ProductExceptionHandler.handleNotFound` produces the 404 response and JSON body.

Thus:

- `handler().methodName("findById")` verifies the original controller method that was selected.
- `MvcResult.getResolvedException()` tells you which exception Spring MVC resolved.
- `status().isNotFound()` and body assertions verify the exception-handling outcome sent to the client.

`handler()` does not assert which `@ExceptionHandler` method was invoked. The exception handler runs during exception resolution after the original controller handler was already selected.

## 5. Verifying the Resolved Exception

Complete test example:

```java
@WebMvcTest(ProductController.class)
@Import(ProductExceptionHandler.class)
class ProductControllerExceptionTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void resolvesProductNotFoundException() throws Exception {
        MvcResult result = mockMvc.perform(get("/products/{id}", 404))
                .andExpect(handler().handlerType(ProductController.class))
                .andExpect(handler().methodName("findById"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.message")
                        .value("Product 404 was not found"))
                .andReturn();

        assertThat(result.getResolvedException())
                .isInstanceOf(ProductNotFoundException.class);
    }
}
```

This test verifies all three aspects: the request was routed to the right controller method, the expected exception was resolved, and the client received the corresponding status and body.

### What Does `getResolvedException()` Tell You?

`MvcResult.getResolvedException()` returns the exception encountered and resolved during dispatch, or `null` if no exception was recorded as resolved. This is the original exception raised during handler execution, not an object representing the response body.

An exception handled by `@ExceptionHandler` still appears in `getResolvedException()`. This does not mean the exception escaped unhandled; it indicates that Spring MVC caught that exception and handled it in the exception resolution flow.

Do not rely solely on `getResolvedException()` to conclude the client received the right response. An exception may have been resolved while still producing the wrong status or body. Combine exception assertions with status, header, and response body checks.

## 6. How Does Spring MVC Resolve Exceptions?

`DispatcherServlet` uses a chain of `HandlerExceptionResolver` implementations to handle exceptions thrown during handler invocation. Common resolvers include:

| Resolver | Typical Role |
| --- | --- |
| `ExceptionHandlerExceptionResolver` | Finds and invokes `@ExceptionHandler` methods in controllers or `@ControllerAdvice` |
| `ResponseStatusExceptionResolver` | Handles `@ResponseStatus`-annotated exceptions and `ResponseStatusException` |
| `DefaultHandlerExceptionResolver` | Maps standard Spring MVC exceptions to appropriate HTTP statuses |
| Custom resolver | Handles exceptions according to application-registered rules |

Resolvers are invoked in configured order. A resolver can return a `ModelAndView` to indicate the exception was handled, return an empty result per the resolver contract, or leave it to subsequent resolvers. If no resolver handles the exception, it can escape `DispatcherServlet` to be handled by the Servlet container.

### `@ExceptionHandler` in a Controller or `@ControllerAdvice`

`@ExceptionHandler` can be declared directly inside a controller:

```java
@RestController
public class ProductController {

    @GetMapping("/products/{id}")
    public Map<String, Object> findById(@PathVariable long id) {
        throw new ProductNotFoundException(id);
    }

    @ExceptionHandler(ProductNotFoundException.class)
    ResponseEntity<Map<String, String>> handleNotFound(
            ProductNotFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(Collections.singletonMap("message", exception.getMessage()));
    }
}
```

Or declared application-wide using `@ControllerAdvice`/`@RestControllerAdvice`, as in the earlier example. Using advice allows multiple controllers to share error-handling rules.

Spring selects exception handler methods based on matching exception types and exception handler mapping conditions. Local controller handlers and global advice follow Spring's precedence rules. When multiple handlers could match the same exception, write tests to confirm the actual response under the active configuration.

### `ResponseStatusException` and `@ResponseStatus`

Besides `@ExceptionHandler`, an application can use `ResponseStatusException`:

```java
@GetMapping("/legacy-products/{id}")
public Map<String, Object> findLegacy(@PathVariable long id) {
    throw new ResponseStatusException(
            HttpStatus.GONE, "This product endpoint is no longer available");
}
```

Or annotate an exception with `@ResponseStatus`:

```java
@ResponseStatus(HttpStatus.NOT_FOUND)
public class CustomerNotFoundException extends RuntimeException {
    public CustomerNotFoundException(String customerId) {
        super("Customer " + customerId + " was not found");
    }
}
```

Tests should verify the status and any response details the application commits to. Body contents may depend on error response configuration, `ErrorAttributes`, controller advice, or the Spring Boot version; do not assume every exception mechanism generates the same body.

## 7. Distinguishing Resolved Exceptions from Unresolved Exceptions

If a `HandlerExceptionResolver` handles the exception, Spring MVC can complete the dispatch and return a response. Tests typically obtain an `MvcResult` and can inspect `getResolvedException()`, status, and body.

If no resolver handles the exception, it can be thrown out of the dispatch process. In that case, `mockMvc.perform(...)` may throw an exception instead of returning a result for `.andReturn()`. Here, a test can use `assertThatThrownBy` or `assertThrows` to assert that the exception propagates, depending on the wrapper exception used by your Spring/framework version.

Example checking an unhandled exception:

```java
assertThatThrownBy(() -> mockMvc.perform(get("/unhandled-error")))
        .hasRootCauseInstanceOf(IllegalStateException.class);
```

This example illustrates the idea of asserting an exception escaping MockMvc. The specific wrapper type and cause chain depend on where the exception originated and the Spring version. When possible, check the root exception type without coupling to internal wrapper messages.

Another case is when no handler is found at all. Depending on configuration, the request may fall back to a resource handler, be converted to a 404, or throw an exception like `NoHandlerFoundException`/`NoResourceFoundException`. Consequently, not every 404 status means a controller method ran and threw an exception.

## 8. Errors That Do Not Pass Through HandlerExceptionResolver

`HandlerExceptionResolver` belongs to `DispatcherServlet`'s dispatch flow. Errors occurring before the request reaches `DispatcherServlet` may fall outside this flow.

For instance, the Spring Security filter chain can reject a request before a controller is called. In that situation:

- No controller handler may have been selected.
- `MvcResult.getResolvedException()` is generally not where to look for the authorization denial reason.
- A 401, 403, or redirect response is typically produced by security components such as `AuthenticationEntryPoint` or `AccessDeniedHandler`.

For errors in custom filters, the Servlet container, or connectors, determine whether the failure happened before or inside `DispatcherServlet`. Do not expect every application exception to show up in `getResolvedException()`.

When testing Spring Security, make sure the filter chain participates in MockMvc and assert statuses/redirects per your security configuration. When testing controller advice, ensure the request clears the filter chain and reaches the MVC handler.

## 9. Verifying Both Handler and Exception in Realistic Scenarios

### Right Mapping, Handler Throws an Exception

This is a common case: the URL matches the controller, the controller runs, yet the data does not exist. Tests should confirm both the original handler and the exception resolution outcome:

```java
MvcResult result = mockMvc.perform(get("/products/404"))
        .andExpect(handler().handlerType(ProductController.class))
        .andExpect(handler().methodName("findById"))
        .andExpect(status().isNotFound())
        .andReturn();

assertThat(result.getResolvedException())
        .isInstanceOf(ProductNotFoundException.class);
```

### Wrong HTTP Method

If a mapping only supports GET and the test sends POST, the GET handler method is not selected. Spring can return 405 Method Not Allowed when the path exists but the HTTP method does not match. The test should assert the status and not assert that the GET handler method was invoked:

```java
mockMvc.perform(post("/products/12"))
        .andExpect(status().isMethodNotAllowed());
```

Depending on resource handler configuration and mappings, dispatch details can vary; write assertions matching the defined API behavior.

### Unsatisfied params, headers, or Media Type Conditions

If a request fails to satisfy `params`, `headers`, `consumes`, or `produces`, Spring may return 400, 406, or 415 depending on the case. These errors are commonly mapped by default resolvers or custom advice. When testing conditional mappings, assert both the selected handler method for valid requests and the status/error response for invalid requests.

### Checking Views and Models

For controllers returning views instead of JSON, you can use `view()` and `model()` matchers:

```java
mockMvc.perform(get("/products"))
        .andExpect(handler().handlerType(ProductPageController.class))
        .andExpect(handler().methodName("list"))
        .andExpect(view().name("products/list"))
        .andExpect(model().attributeExists("products"));
```

These matchers verify the handler and Spring MVC's logical rendering outcome; they do not prove the template renders properly in a browser. If you need to test final HTML or template engine integration, add tests tailored to the view technology.

## 10. Asynchronous Requests and Exceptions

For controllers returning `Callable`, `DeferredResult`, or other async result types, the initial `perform` call may only verify that asynchronous processing started. To verify the final outcome, capture `MvcResult`, wait for async completion per test mechanics, and invoke `asyncDispatch`:

```java
MvcResult initialResult = mockMvc.perform(get("/async-products/12"))
        .andExpect(request().asyncStarted())
        .andReturn();

mockMvc.perform(asyncDispatch(initialResult))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value(12));
```

If an async task throws an exception, exception resolution may happen during the async dispatch. Assert the final response after `asyncDispatch`, and inspect the `MvcResult` from that final dispatch if you need to check the resolved exception.

Do not assume the handler finished completely from the initial `MvcResult` alone. For async requests, tests must distinguish the async-started state from the response after dispatching the result.

## 11. Writing Clear Assertions

A well-structured MVC test typically orders assertions so readers can follow where the request went and what came back:

1. Assert handler type and method when routing is being verified.
2. Assert HTTP status.
3. Assert content type, headers, or response body.
4. If an exception is involved, assert the exception type via `getResolvedException()`.
5. When testing views, assert the view name and model attributes.

Combined example:

```java
MvcResult result = mockMvc.perform(get("/products/404")
                .accept(MediaType.APPLICATION_JSON))
        .andExpect(handler().handlerType(ProductController.class))
        .andExpect(handler().methodName("findById"))
        .andExpect(status().isNotFound())
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.message").value("Product 404 was not found"))
        .andReturn();

assertThat(result.getResolvedException())
        .isInstanceOf(ProductNotFoundException.class);
```

You do not need to repeat every assertion in every test. If a test focuses purely on the response contract, status and body may suffice. If a test targets routing or exception resolution, add handler matchers and resolved-exception checks to clarify what is being verified.

## 12. Quick Reference Table for Matchers and MvcResult Data

| What to Verify | Commonly Used API | Meaning |
| --- | --- | --- |
| Selected controller class | `handler().handlerType(...)` | Bean type containing the handler |
| Selected handler method | `handler().methodName(...)` | Name of the method that received the request |
| Actual handler object | `MvcResult.getHandler()` | Selected handler instance |
| Annotated controller method info | `HandlerMethod` | Bean type, method, and metadata |
| Exception resolved by MVC | `MvcResult.getResolvedException()` | Original exception recorded during resolution |
| HTTP status | `status()` | Status sent back to the client |
| Response body | `content()`, `jsonPath()` | Returned payload |
| View name | `view().name(...)` | View selected for rendering |
| Model attribute | `model().attribute(...)` | Data placed in the model |
| Async request | `request().asyncStarted()`, `asyncDispatch(...)` | Async processing state and final dispatch outcome |

Remember that `getHandler()` and `getResolvedException()` answer two different questions. One tells you where the request was routed; the other tells you which exception was handled during dispatch.

## 13. Conclusion

MockMvc's handler matchers verify that Spring MVC picked the expected controller type and handler method for a request. `MvcResult.getHandler()` lets you inspect the selected handler in more depth, while `getResolvedException()` reveals the exception resolved during dispatch.

When a controller throws an exception, the initial handler remains the controller method. `@ExceptionHandler`, `@ControllerAdvice`, or default resolvers handle the exception and build the response afterward. Combine assertions for handler, exception, status, and body to verify all behavior under test. For errors occurring outside `DispatcherServlet`, such as requests blocked by Spring Security filters before reaching a controller, verify them at the corresponding filter/security layer instead of relying on `getResolvedException()`.
