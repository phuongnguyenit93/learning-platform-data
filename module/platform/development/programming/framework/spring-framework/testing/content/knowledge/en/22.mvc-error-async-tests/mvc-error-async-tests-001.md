# ControllerAdvice and Mapping Exceptions to HTTP

In Spring MVC, errors can arise when a controller handles business logic, when Spring binds request data, or when a message converter reads the request body. If every controller writes its own `try/catch` block to turn errors into HTTP responses, error handling easily becomes duplicated and inconsistent. Spring provides `@ExceptionHandler`, `@ControllerAdvice`, and `@RestControllerAdvice` to centralize converting exceptions into HTTP responses.

When testing, you need to verify both parts: which exception is handled and what response is sent back to the client. A good test verifies the HTTP status, response body, content type, and relevant headers; merely verifying that the controller throws the right exception does not prove that the API returns the expected error contract.

## 1. Why Map Exceptions to HTTP Responses?

A Java exception describes an error inside the program. An HTTP response is how the application represents that error to the client. The two concepts are related, not identical.

For example, when looking up a nonexistent order, a service may throw `OrderNotFoundException`. The API typically translates this error into HTTP `404 Not Found` along with enough information for the client to understand which resource could not be found. When submitted data is invalid, the API typically returns `400 Bad Request`. When the current state of a resource conflicts with the operation, `409 Conflict` can be used.

| Situation | Typical HTTP status | Meaning to client |
|---|---:|---|
| Resource does not exist | `404 Not Found` | The address or identifier does not point to a findable resource |
| Malformed request or invalid data | `400 Bad Request` | The client needs to fix the request |
| Unauthenticated | `401 Unauthorized` | The client needs to provide valid authentication credentials |
| Lacks permission to perform action | `403 Forbidden` | The current identity is not allowed to perform the operation |
| Conflicting resource state | `409 Conflict` | The client needs to resolve the conflict before retrying |
| Unexpected server-side error | `500 Internal Server Error` | The server could not complete the request |

The status must accurately reflect the root cause and the API contract. Do not turn every exception into `400`, because business errors or internal server errors are not necessarily caused by the client sending an invalid request.

## 2. Handling Exceptions Directly in a Controller

`@ExceptionHandler` can be placed inside a controller. The annotated method handles the corresponding exception type raised from handler methods within that controller.

```java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    @GetMapping("/orders/{orderId}")
    OrderView findOrder(@PathVariable String orderId) {
        if ("missing".equals(orderId)) {
            throw new OrderNotFoundException(orderId);
        }
        return new OrderView(orderId, "CREATED");
    }

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ApiError> handleOrderNotFound(
            OrderNotFoundException exception) {
        ApiError body = new ApiError(
            "ORDER_NOT_FOUND",
            "Order " + exception.getOrderId() + " was not found"
        );
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(body);
    }
}

record OrderView(String orderId, String status) {
}

record ApiError(String code, String message) {
}

class OrderNotFoundException extends RuntimeException {

    private final String orderId;

    OrderNotFoundException(String orderId) {
        super("Order not found: " + orderId);
        this.orderId = orderId;
    }

    String getOrderId() {
        return orderId;
    }
}
```

`ResponseEntity` lets the handler method specify the status, headers, and body. This approach works well when an exception only makes sense within a single controller or when the response format is genuinely specific to that controller.

When multiple controllers need the same handling rules, move the handler into an advice instead of duplicating the method across controllers.

## 3. Centralizing Handling with @ControllerAdvice

`@ControllerAdvice` is a component that can provide shared exception handling methods across multiple controllers. It also supports other cross-cutting controller capabilities such as `@InitBinder` and `@ModelAttribute`, though this lesson focuses on exception handling.

For example, moving the handler from `OrderController` into a separate class:

```java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.bind.annotation.ExceptionHandler;

@ControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ApiError> handleOrderNotFound(
            OrderNotFoundException exception) {
        ApiError body = new ApiError(
            "ORDER_NOT_FOUND",
            "Order " + exception.getOrderId() + " was not found"
        );
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(body);
    }
}
```

For controllers that return views, `@ControllerAdvice` can return a `ModelAndView` or a value appropriate for view resolution. If an API needs to return data in the response body, you can put `@ResponseBody` on the handler method or use `@RestControllerAdvice`.

`@RestControllerAdvice` combines the roles of `@ControllerAdvice` and `@ResponseBody`. Consequently, the object returned from an exception handler is written to the response body via `HttpMessageConverter`s:

```java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    @ResponseStatus(HttpStatus.NOT_FOUND)
    ApiError handleOrderNotFound(OrderNotFoundException exception) {
        return new ApiError(
            "ORDER_NOT_FOUND",
            "Order " + exception.getOrderId() + " was not found"
        );
    }
}
```

Both approaches can produce a `404` response. `ResponseEntity` fits when you need to determine the status and headers dynamically inside the method; `@ResponseStatus` fits when the status for the handler is fixed.

## 4. Using ProblemDetail for a Standard Error Format

Spring Framework 6 supports `ProblemDetail` to represent HTTP errors according to the Problem Details for HTTP APIs format (RFC 7807). This is a useful choice when you want error responses to have a consistent structure across endpoints.

Common standard properties include:

- `type`: a URI identifying the problem type; the default value is `about:blank`.
- `title`: a short summary of the problem type.
- `status`: the HTTP status.
- `detail`: a specific explanation for this occurrence of the error.
- `instance`: a URI identifying the request or specific occurrence of the error.

You can add extension properties for error codes or required business data:

```java
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ProblemDetail handleOrderNotFound(OrderNotFoundException exception) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND,
            "Order " + exception.getOrderId() + " was not found"
        );
        problem.setTitle("Order not found");
        problem.setProperty("code", "ORDER_NOT_FOUND");
        return problem;
    }
}
```

When Spring MVC writes a `ProblemDetail` to the response, the content is serialized in the problem details format using the appropriate media type, typically `application/problem+json` for JSON. Tests should use `contentTypeCompatibleWith(...)` to verify the media type without depending on optional parameters if present.

Do not include stack traces, SQL, table names, tokens, passwords, or sensitive internal information in `detail`. Technical details for investigation should be written to server logs along with a correlation ID; the public response should only contain information the client needs to handle the error.

## 5. Other Ways to Map Exceptions

Beyond `@ControllerAdvice`, Spring MVC offers several common ways to express HTTP status codes.

### @ResponseStatus on an Exception

You can attach `@ResponseStatus` directly to an exception type:

```java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ResponseStatus;

@ResponseStatus(HttpStatus.NOT_FOUND)
class OrderNotFoundException extends RuntimeException {
    OrderNotFoundException(String orderId) {
        super("Order not found: " + orderId);
    }
}
```

When this exception escapes a controller, Spring can map it to status `404`. This is simple for errors with a fixed status, but less flexible than an advice when you need a unified response body or need to add headers and error data.

### ResponseStatusException

When you need to specify the status at the point where the error occurs, you can use `ResponseStatusException`:

```java
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

throw new ResponseStatusException(
    HttpStatus.CONFLICT,
    "Order cannot be cancelled in its current state"
);
```

This can be convenient for a small branch of logic. If the API uses a unified public error format, consider handling `ResponseStatusException` in an advice or using a dedicated business exception type so individual controllers do not return errors in differing structures.

### Spring MVC Default Error Handling

Spring MVC already includes exception resolvers to handle framework errors and exceptions with declared statuses. Errors such as an unsupported method, an incompatible media type, or an unreadable request body can be handled by Spring MVC's default mechanisms. If you need to change the default response, you can use `@ExceptionHandler` in an advice or extend `ResponseEntityExceptionHandler` to customize how standard MVC exceptions are handled.

Avoid hastily creating a broad catch-all handler that accidentally overrides default framework behavior. Clearly identify which exception types need standardization and test the corresponding status and body.

## 6. Advice Scope and Ordering

By default, `@ControllerAdvice` applies to controllers discovered in the application. You can narrow its scope using selectors such as `basePackages`, `basePackageClasses`, `annotations`, or `assignableTypes`.

For example, applying the advice only to controllers in the API package:

```java
@RestControllerAdvice(basePackages = "com.example.api")
class ApiExceptionHandler {
    // Shared @ExceptionHandler methods for the API.
}
```

If multiple advices handle exceptions, their ordering affects which handler is chosen. Ordering can be specified with `Ordered`, `@Order`, or `@Priority`. Higher-precedence advices are evaluated first. Within a single advice, Spring prefers a direct root exception match over a cause match; across different advices, a higher-precedence advice can win even if it matches a cause exception.

Therefore, when two handlers could match the same error, check both the advice order and the actual exception type thrown. Avoid multiple broadly scoped advices all catching `Exception.class`, because it becomes hard to predict which handler takes responsibility and can shadow specific error handlers.

## 7. Testing Exception Mapping with MockMvc

When testing exception mapping, send real requests through Spring MVC using `MockMvc`. Do not call the handler method directly as a substitute, because direct invocation bypasses `DispatcherServlet`, exception resolvers, and the response-writing pipeline.

Example controller and exception:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    @GetMapping("/orders/{orderId}")
    OrderView findOrder(@PathVariable String orderId) {
        if ("missing".equals(orderId)) {
            throw new OrderNotFoundException(orderId);
        }
        return new OrderView(orderId, "CREATED");
    }
}

record OrderView(String orderId, String status) {
}

class OrderNotFoundException extends RuntimeException {

    private final String orderId;

    OrderNotFoundException(String orderId) {
        super("Order not found: " + orderId);
        this.orderId = orderId;
    }

    String getOrderId() {
        return orderId;
    }
}
```

Advice using `ProblemDetail`:

```java
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ProblemDetail handleOrderNotFound(OrderNotFoundException exception) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND,
            "Order " + exception.getOrderId() + " was not found"
        );
        problem.setTitle("Order not found");
        problem.setProperty("code", "ORDER_NOT_FOUND");
        return problem;
    }
}
```

With Spring Boot, you can use `@WebMvcTest` to load the MVC slice and import the advice under test:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderController.class)
@Import(ApiExceptionHandler.class)
class OrderControllerExceptionTests {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void mapsMissingOrderToProblemDetailNotFound() throws Exception {
        mockMvc.perform(get("/orders/{orderId}", "missing"))
            .andExpect(status().isNotFound())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(jsonPath("$.status").value(404))
            .andExpect(jsonPath("$.title").value("Order not found"))
            .andExpect(jsonPath("$.detail")
                .value("Order missing was not found"))
            .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"));
    }
}
```

The test above verifies the entire error path: the request reaches the controller, the controller throws `OrderNotFoundException`, the advice catches the exception, Spring builds the response, and `MockMvc` observes the HTTP result. The assertions verify:

- The actual status is `404`.
- The response has a media type compatible with `application/problem+json`.
- The `status`, `title`, and `detail` fields, along with the `code` extension property, match the API contract.

If the project uses `@WebMvcTest`, make sure the advice is included in the test context. You can use `@Import` as shown in the example or configure the test slice to discover the needed advice component. If you use `@SpringBootTest` with `@AutoConfigureMockMvc`, the application typically loads a broader configuration and the advice is component-scanned as at runtime.

## 8. Testing Request Errors Produced by Spring MVC

Not every error is actively thrown by controller code. Spring MVC can detect errors before invoking the controller method, such as:

- Unreadable request body or malformed JSON: typically involves `HttpMessageNotReadableException`.
- Data failing `@Valid` validation: typically involves `MethodArgumentNotValidException`.
- No handler matching the HTTP method: can result in `405 Method Not Allowed`.
- Unsupported request media type: can result in `415 Unsupported Media Type`.
- Unacceptable response media type: can result in `406 Not Acceptable`.

Validation test example:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CustomerController {

    @PostMapping("/customers")
    ResponseEntity<Void> create(
            @Valid @RequestBody CreateCustomerRequest request) {
        return ResponseEntity.status(201).build();
    }
}

record CreateCustomerRequest(@NotBlank String name) {
}
```

When testing validation errors, send syntactically valid JSON that violates a constraint, then assert the error response:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.http.MediaType;

mockMvc.perform(post("/customers")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {"name":"   "}
            """))
    .andExpect(status().isBadRequest());
```

If an advice customizes validation responses, also assert the error structure and field error contents. A syntactically invalid JSON request tests a different branch than syntactically valid JSON that violates `@NotBlank`; write separate tests if the API commits to handling those two cases differently.

## 9. Common Mistakes When Writing Exception Handler Tests

| Symptom | Cause to check |
|---|---|
| Request returns default status instead of custom status | Advice is not loaded, package scan misses the advice, or the exception does not match the handler |
| `@ExceptionHandler` is not invoked | Exception occurs outside the MVC request, handler method is not scoped to the controller/advice, or the actual exception differs from expected |
| Right handler runs, but body is empty | `@ControllerAdvice` returns an object without `@ResponseBody` or the response is not produced as intended |
| Slice test does not see the advice | `@WebMvcTest` excludes the specific advice from the test context; check component scan or `@Import` |
| Right status, but wrong body | Assertions only checked status; inspect serializer, field names, content type, and data returned by the handler |
| General handler shadows a specific error | Multiple advices or handlers match; check `@Order`, advice scope, and exception types |
| Response leaks internal information | Handler returns the raw exception message or stack trace; expose only information needed by the client |

Another important mistake is writing a test that calls `handleOrderNotFound(...)` directly. That only tests a Java method and does not test Spring MVC's exception mapping mechanism. To verify API behavior, trigger the exception within a `MockMvc` request and assert the resulting response.

## 10. Workflow for Designing and Testing Error Mapping

1. Identify the error types and appropriate HTTP statuses according to the API contract.
2. Choose where to handle them: `@ExceptionHandler` inside a controller for local errors, or `@ControllerAdvice` / `@RestControllerAdvice` for shared rules.
3. Choose the response structure: `ResponseEntity`, `@ResponseStatus`, or `ProblemDetail`.
4. Keep the public response stable and avoid placing sensitive internal information in the body.
5. Create MVC tests with `MockMvc`, ensuring both the controller and the advice are present in the test context.
6. Send requests that trigger the exception and assert status, content type, body, and any required headers.
7. Add tests for Spring MVC-generated errors such as malformed JSON or validation failures if the API customizes them.

`@ExceptionHandler` defines how a single exception type is handled; `@ControllerAdvice` shares that rule across multiple controllers; `@RestControllerAdvice` returns the result via the response body. When testing with `MockMvc`, you verify the entire HTTP contract seen by the client, rather than only verifying that a Java method ran.
