# HTTP Methods, URI Templates, and Path Variables

## 1. How Does MockMvc Send an HTTP Request?

In Spring MVC, an endpoint is typically identified by multiple factors: the HTTP method, the URI path, additional conditions such as `Content-Type` or `Accept`, and the request data. When testing a controller with MockMvc, we need to build a request with those exact elements so that Spring selects the right handler method and binds the data into Java parameters.

`MockMvcRequestBuilders` provides request-building functions corresponding to HTTP methods:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;

mockMvc.perform(get("/api/orders"));
mockMvc.perform(post("/api/orders"));
mockMvc.perform(put("/api/orders/{id}", 42));
mockMvc.perform(patch("/api/orders/{id}", 42));
mockMvc.perform(delete("/api/orders/{id}", 42));
```

Each builder creates a mock request for MockMvc to pass through the Spring MVC processing chain. The request does not need to be sent over the network to a real HTTP port. Even so, mapping resolution, argument resolvers, data binding, validation, controller advice, and message converters can still be tested under the active MockMvc configuration.

A basic request can be read according to the structure:

```text
HTTP method + URI + headers + parameters + body
```

For example:

```text
GET /api/orders/42
Accept: application/json
```

Here, `GET` is the HTTP method, `/api/orders/42` is the concrete URI, and `42` is a path segment that can be bound into a `@PathVariable`.

## 2. HTTP Methods and Controller Mapping

Spring MVC uses mapping annotations to connect a request to a Java method. The HTTP method is part of the mapping condition.

```java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping
    public List<OrderResponse> findAll() {
        // ...
    }

    @GetMapping("/{orderId}")
    public OrderResponse findById(@PathVariable("orderId") UUID orderId) {
        // ...
    }

    @PostMapping
    public OrderResponse create(@RequestBody CreateOrderRequest request) {
        // ...
    }

    @PutMapping("/{orderId}")
    public OrderResponse replace(
            @PathVariable("orderId") UUID orderId,
            @RequestBody ReplaceOrderRequest request) {
        // ...
    }

    @PatchMapping("/{orderId}")
    public OrderResponse updatePartially(
            @PathVariable("orderId") UUID orderId,
            @RequestBody UpdateOrderRequest request) {
        // ...
    }

    @DeleteMapping("/{orderId}")
    public void delete(@PathVariable("orderId") UUID orderId) {
        // ...
    }
}
```

Commonly used methods in testing:

| HTTP method | Common meaning | MockMvc builder |
|---|---|---|
| `GET` | Read a resource or data | `get(uriTemplate, uriVariables...)` |
| `POST` | Create a resource or perform an action | `post(uriTemplate, uriVariables...)` |
| `PUT` | Replace or update a resource according to the API contract | `put(uriTemplate, uriVariables...)` |
| `PATCH` | Partially update a resource | `patch(uriTemplate, uriVariables...)` |
| `DELETE` | Delete a resource | `delete(uriTemplate, uriVariables...)` |
| `HEAD` | Request headers similar to `GET`, without retrieving a response body | `head(uriTemplate, uriVariables...)` |
| `OPTIONS` | Query supported methods or options | `options(uriTemplate, uriVariables...)` |

The `get`, `post`, `put`, `patch`, `delete`, `head`, and `options` builders help tests clearly express the method being verified. When the method needs to be chosen dynamically, the general-purpose builder can be used:

```java
import org.springframework.http.HttpMethod;

mockMvc.perform(request(HttpMethod.GET, "/api/orders/{orderId}", orderId));
```

`request(HttpMethod, ...)` is useful when the method comes from test data or when writing a shared helper. For typical tests, dedicated builders are usually easier to read.

### 2.1. Testing the Right Method

Suppose the controller has `@GetMapping("/{orderId}")`. The test should send `GET` to the corresponding URI:

```java
mockMvc.perform(get("/api/orders/{orderId}", orderId))
        .andExpect(status().isOk());
```

If `POST` is sent to the same path when only a `GET` mapping exists, Spring MVC typically returns `405 Method Not Allowed` because the path matches but the HTTP method is not supported:

```java
mockMvc.perform(post("/api/orders/{orderId}", orderId))
        .andExpect(status().isMethodNotAllowed());
```

If no mapping matches the URI, the result is usually `404 Not Found`. Therefore, when testing errors, distinguish the wrong-method case from the wrong-path case. Security filters can also reject the request before it reaches handler mapping; in that case, the response may be `401` or `403` depending on the configuration.

## 3. What Is a URI Template?

A URI template is a URI containing placeholders that represent values to be substituted when constructing the request. Placeholders are typically written inside curly braces `{}`:

```text
/api/orders/{orderId}
/api/customers/{customerId}/orders/{orderId}
/api/products/{category}/{productCode}
```

In the controller, the placeholders correspond to path variables:

```java
@GetMapping("/api/orders/{orderId}")
public OrderResponse find(@PathVariable("orderId") UUID orderId) {
    // ...
}
```

In MockMvc, pass the URI variable values right after the template string:

```java
UUID orderId = UUID.fromString("8a2d1a4e-7a5d-4c0f-9c1a-8e0a0f7c1122");

mockMvc.perform(get("/api/orders/{orderId}", orderId));
```

MockMvc expands the template and creates the corresponding concrete URI. The request is sent to Spring MVC with a path where placeholders have been replaced by values:

```text
Template: /api/orders/{orderId}
Value:    8a2d1a4e-7a5d-4c0f-9c1a-8e0a0f7c1122
Request:  /api/orders/8a2d1a4e-7a5d-4c0f-9c1a-8e0a0f7c1122
```

Using templates helps tests state clearly which part is the fixed route and which part is input data. It also avoids manual string concatenation to build paths.

### 3.1. Templates with Multiple Path Variables

Suppose an endpoint has two variables:

```java
@GetMapping("/api/customers/{customerId}/orders/{orderId}")
public OrderResponse findCustomerOrder(
        @PathVariable("customerId") UUID customerId,
        @PathVariable("orderId") UUID orderId) {
    // ...
}
```

The test passes values in the order the placeholders appear in the URI template:

```java
mockMvc.perform(get(
        "/api/customers/{customerId}/orders/{orderId}",
        customerId,
        orderId));
```

The first value is bound into `{customerId}`, and the second value is bound into `{orderId}`. If passed in reverse order, the request may still be created, but each value will end up in an unintended position; Spring then binds by the placeholder name in the mapping. Keep the argument order aligned with the variable order in the template.

For long templates, wrap lines and use clear variable names so readers can cross-check them easily:

```java
mockMvc.perform(get(
        "/api/warehouses/{warehouseId}/bins/{binId}/items/{itemId}",
        warehouseId,
        binId,
        itemId));
```

### 3.2. Passing Values of Different Data Types

The final URI is a string, but URI variable arguments can be Java types such as `UUID`, `Long`, `Integer`, or `String`:

```java
mockMvc.perform(get("/api/orders/{orderId}", 42L));
mockMvc.perform(get("/api/orders/{orderId}", orderId));
mockMvc.perform(get("/api/products/{code}", "BK-2026-01"));
```

Values are rendered as URI data. When the request reaches the controller, Spring MVC converts the path variable string to the Java parameter type using the configured conversion service and converters.

For example, the route `/api/orders/42` can bind into a `Long` parameter, while a valid UUID can bind into a `UUID`. If the string in the path cannot be converted to the target type, Spring MVC typically returns `400 Bad Request` due to an argument conversion error.

## 4. Where Does `@PathVariable` Get Its Data?

`@PathVariable` extracts data from a variable declared in the mapping's path pattern. The variable name in the annotation must match the route placeholder, unless the name is inferred according to the application's Java parameter-name rules.

Explicit declaration is usually easier to read and depends less on compilation settings:

```java
@GetMapping("/api/orders/{orderId}")
public OrderResponse find(@PathVariable("orderId") UUID orderId) {
    // ...
}
```

It can also be written as:

```java
@GetMapping("/api/orders/{orderId}")
public OrderResponse find(@PathVariable UUID orderId) {
    // ...
}
```

In the second form, Spring needs to resolve the parameter name as `orderId`. Declaring the name in the annotation makes the link between the route and the parameter clearer, especially when renaming Java variables or when compilation settings do not retain parameter-name metadata.

With multiple path variables:

```java
@GetMapping("/api/customers/{customerId}/orders/{orderId}")
public OrderResponse find(
        @PathVariable("customerId") UUID customerId,
        @PathVariable("orderId") UUID orderId) {
    // ...
}
```

Spring locates each value in the matched URI and then converts it to the parameter's declared type. The controller receives the bound values without having to split the URI string manually.

### 4.1. Required Path Variables and Unmatched Routes

A path variable is part of the path structure. If a mapping requires `/api/orders/{orderId}`, the request `/api/orders` lacks the `orderId` segment and therefore does not match that mapping. This is typically a `404` scenario, not a request with an empty path variable.

If the route matches but the value is invalid for the Java type—for example, `orderId` is declared as `UUID` but the request contains `not-a-uuid`—Spring cannot convert the value and typically returns `400`.

The two cases need to be tested separately:

```java
// Missing path segment: does not match /{orderId}.
mockMvc.perform(get("/api/orders"))
        .andExpect(status().isNotFound());

// Has segment, but cannot be converted to UUID.
mockMvc.perform(get("/api/orders/{orderId}", "not-a-uuid"))
        .andExpect(status().isBadRequest());
```

The exact outcome is still affected by other mappings and the application's exception handlers. For example, `/api/orders` might be a separate valid `GET` route, or `@ControllerAdvice` might customize the error response.

## 5. How Does a Path Variable Differ from a Query Parameter?

Both path variables and query parameters pass data from the client to the controller, but they belong to different parts of the URI and have different corresponding annotations.

| Data type | URI example | Controller-side annotation | How to build in MockMvc |
|---|---|---|---|
| Path variable | `/api/orders/42` | `@PathVariable` | `get("/api/orders/{id}", 42)` |
| Query parameter | `/api/orders?page=2` | `@RequestParam` | `get("/api/orders").queryParam("page", "2")` |
| Form/request parameter | Request form data | `@RequestParam` | `.param("name", "value")` |
| Request body | JSON in the body | `@RequestBody` | `.contentType(...).content(...)` |

Example of a controller receiving both a path variable and query parameters:

```java
@GetMapping("/api/customers/{customerId}/orders")
public List<OrderResponse> findCustomerOrders(
        @PathVariable("customerId") UUID customerId,
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size) {
    // ...
}
```

A test can build the URI path with a template and the query string with `queryParam`:

```java
mockMvc.perform(get("/api/customers/{customerId}/orders", customerId)
                .queryParam("page", "2")
                .queryParam("size", "10"))
        .andExpect(status().isOk());
```

`queryParam(...)` clearly expresses that data is added to the query string. `.param(...)` sets a request parameter directly on the mock request and is commonly used when testing general request parameters or form data:

```java
mockMvc.perform(get("/api/orders")
                .param("status", "PAID")
                .param("page", "0"))
        .andExpect(status().isOk());
```

Do not use `.param("orderId", "42")` as a substitute for the path variable in the route `/api/orders/{orderId}`. A request parameter named `orderId` does not create the missing segment in the path. If the controller declares `@PathVariable`, pass the value via the URI template.

## 6. Using URI Templates with Different HTTP Methods

URI variables are not limited to `GET`. The other builders can accept a URI template and a list of values in a similar way.

### 6.1. GET a Resource

Controller:

```java
@GetMapping("/api/orders/{orderId}")
public OrderResponse findById(@PathVariable("orderId") UUID orderId) {
    return orderService.findById(orderId);
}
```

Test:

```java
mockMvc.perform(get("/api/orders/{orderId}", orderId)
                .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.id").value(orderId.toString()));
```

`accept(...)` sets the `Accept` header to describe the response type the client expects. It does not replace the HTTP method or URI variables.

### 6.2. POST to Create a Resource

POST typically sends new data in the request body. The URI template can still contain a path variable if the API designs a resource-creation endpoint under a parent resource:

```java
@PostMapping("/api/customers/{customerId}/orders")
public OrderResponse create(
        @PathVariable("customerId") UUID customerId,
        @RequestBody CreateOrderRequest request) {
    // ...
}
```

Test:

```java
String body = """
        {
          "productCode": "BK-2026-01",
          "quantity": 2
        }
        """;

mockMvc.perform(post("/api/customers/{customerId}/orders", customerId)
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content(body))
        .andExpect(status().isCreated());
```

Here `customerId` belongs to the path, while `productCode` and `quantity` belong to the JSON body. Do not put all request data in the URI if the API contract defines it as the body.

### 6.3. PUT and PATCH to Update a Resource

PUT and PATCH usually identify the target resource using a path variable:

```java
mockMvc.perform(put("/api/orders/{orderId}", orderId)
                .contentType(MediaType.APPLICATION_JSON)
                .content(replacementJson))
        .andExpect(status().isOk());

mockMvc.perform(patch("/api/orders/{orderId}", orderId)
                .contentType(MediaType.APPLICATION_JSON)
                .content(patchJson))
        .andExpect(status().isOk());
```

The test must use the exact method declared by the controller. If the endpoint is `@PatchMapping`, sending `PUT` to the same path is not an equivalent substitute.

### 6.4. DELETE to Remove a Resource

```java
mockMvc.perform(delete("/api/orders/{orderId}", orderId))
        .andExpect(status().isNoContent());
```

DELETE typically does not require a request body when the resource identifier is already in the path. However, follow the actual API contract; if the endpoint has a body or additional query parameters, the test must construct that data accurately.

## 7. URI Variables and Encoding

When building a URI from a template, passing values as URI variable arguments lets Spring Test handle template expansion and URI data encoding. This approach is clearer than string concatenation:

```java
// Prefer using a URI template.
mockMvc.perform(get("/api/products/{productCode}", productCode));

// Avoid manual string concatenation to build the path.
mockMvc.perform(get("/api/products/" + productCode));
```

Encoding is especially important when values contain spaces or URI reserved characters. Do not assume every character in a value can appear verbatim in the path. Use URI variables, then test the request with boundary values that match the API contract.

A few notes:

- A path variable represents a segment or part of a path according to the mapping; it is not a way to pass an arbitrary complete URL.
- The `/` character separates segments. If data contains `/`, clarify whether the API allows that data inside a path variable or whether a query parameter or request body should be used instead.
- Do not pre-encode a value and then pass it through a template if that causes the data to be double-encoded.
- If you need to test Unicode characters, spaces, or reserved characters, write tests that show both the input URI and the value received by the controller.

For example, a test might verify a product code with hyphens:

```java
mockMvc.perform(get("/api/products/{productCode}", "BK-2026-01"))
        .andExpect(status().isOk());
```

For more complex data, determine the expected encoding from the API contract and how the servlet container handles paths. Do not rely on manual string concatenation to infer encoding behavior.

## 8. Path Pattern Constraints and Adjacent Mappings

Spring MVC can declare routes with multiple variables or pattern conditions. For example:

```java
@GetMapping("/api/products/{category}/{productCode}")
public ProductResponse find(
        @PathVariable("category") String category,
        @PathVariable("productCode") String productCode) {
    // ...
}
```

The test must supply all segments:

```java
mockMvc.perform(get(
        "/api/products/{category}/{productCode}",
        "books",
        "BK-2026-01"))
        .andExpect(status().isOk());
```

If a mapping uses a regular-expression pattern:

```java
@GetMapping("/api/orders/{orderId:[0-9]+}")
public OrderResponse find(@PathVariable("orderId") long orderId) {
    // ...
}
```

then only path segments matching the expression match the route. You can test both a valid value and an invalid value:

```java
mockMvc.perform(get("/api/orders/{orderId}", 42))
        .andExpect(status().isOk());

mockMvc.perform(get("/api/orders/{orderId}", "ABC"))
        .andExpect(status().isNotFound());
```

In the second example, `ABC` does not match the path pattern, so that handler is not selected. This differs from a route without a regex where the Java parameter cannot be converted: that case usually proceeds to the binding step and returns `400`.

When multiple mappings are similar, test both path and method. For example, `GET /api/orders/{id}` and `DELETE /api/orders/{id}` share the same path pattern but differ in HTTP method; `GET` and `DELETE` are two distinct requests during handler selection.

## 9. Verifying the Selected Handler

Status codes indicate the HTTP outcome, but sometimes a test needs to confirm that Spring selected the right controller method. Result matchers from `MockMvcResultMatchers` can be used:

```java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

mockMvc.perform(get("/api/orders/{orderId}", orderId))
        .andExpect(status().isOk())
        .andExpect(handler().handlerType(OrderController.class))
        .andExpect(handler().methodName("findById"));
```

These assertions are useful when multiple mappings have similar paths or when a test wants to verify that an HTTP method routed to the expected handler. They also help distinguish mapping errors from errors occurring inside controller logic.

You can check the request method in the result if needed:

```java
mockMvc.perform(delete("/api/orders/{orderId}", orderId))
        .andExpect(request().method("DELETE"));
```

Usually, using the right builder such as `get(...)` or `delete(...)` already expresses the method clearly enough. Additional assertions are only needed when they clarify a specific testing requirement.

## 10. A Complete Controller Test

The following example combines `@WebMvcTest`, MockMvc, URI templates, path variables, and JSON response verification. Suppose the controller accepts a UUID and calls a service to look up an order.

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private OrderService orderService;

    @Test
    void findsOrderById() throws Exception {
        UUID orderId = UUID.fromString(
                "8a2d1a4e-7a5d-4c0f-9c1a-8e0a0f7c1122");
        OrderResponse response = new OrderResponse(orderId, "CREATED");

        given(orderService.findById(orderId)).willReturn(response);

        mockMvc.perform(get("/api/orders/{orderId}", orderId)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").value(orderId.toString()))
                .andExpect(jsonPath("$.status").value("CREATED"));

        then(orderService).should().findById(orderId);
    }
}
```

Common static imports used in this test:

```java
import static org.mockito.BDDMockito.given;
import static org.mockito.BDDMockito.then;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
```

With Spring Boot 3.3, `@MockBean` is a common way to replace a service with a mock in a slice test. Newer Spring Boot versions may provide replacement annotations; use the annotation appropriate for your project's version.

What matters in the test is that the value passed to the service matches the exact UUID expanded from the URI template. If path variable binding is wrong or conversion fails, the service invocation might not happen; the mock assertion helps catch that.

## 11. Common Mistakes When Building Requests

| Symptom | Common cause | How to fix |
|---|---|---|
| Controller returns `404` | Missing URI segment, wrong prefix, or wrong path pattern | Compare the URI template with `@RequestMapping` on the class and method |
| Controller returns `405` | Path matches, but the HTTP method is not supported by the mapping | Use the right builder: `get`, `post`, `put`, `patch`, or `delete` |
| `@PathVariable` does not receive the expected value | Wrong order of URI variables or placeholder name does not match the annotation | Match each placeholder with its argument and `@PathVariable("...")` |
| Test uses `.param(...)` but the path variable is still missing | Request parameters do not create path segments | Use a URI template and pass URI variables |
| Request returns `400` | Path variable cannot be converted to the Java type, or validation/binding fails | Check parameter type, path value, and error response |
| Endpoint receives a default query parameter even though the test did not pass it | Controller has `defaultValue` or the parameter is optional | Clarify whether the test is checking the default or a supplied value |
| Request gets `401` or `403` before reaching the controller | Security filter rejects the request | Set up appropriate authentication/authorization for the test; for state-changing requests, also check CSRF if required by configuration |
| Path value with special characters behaves unexpectedly | Manual string concatenation or incorrect data encoding | Use a URI template and verify encoding against the API contract |

When diagnosing, check in order: method, path after template expansion, controller mapping, path variable name and type, and finally the service invoked. This sequence helps pinpoint whether the request was rejected during handler selection, data binding, or business logic.

## 12. Checklist When Writing MockMvc Requests

- Choose the builder matching the HTTP method declared by the endpoint.
- Use URI templates for dynamic path segments.
- Pass URI variables in the exact order the placeholders appear.
- Ensure the name in `@PathVariable` matches the mapping variable name.
- Use appropriate Java types and supply convertible values.
- Use `queryParam(...)` or `param(...)` for request parameters; do not use them to substitute for path variables.
- Use `contentType(...)` and `content(...)` when the endpoint expects a request body.
- Use `accept(...)` when testing content negotiation.
- Distinguish `404` from an unmatched path, `405` from an unsupported method, and `400` from binding/conversion failures.
- When routing needs confirmation, verify the handler type or handler method.

In MockMvc, the HTTP method determines the request type, the URI template defines the path structure, and `@PathVariable` receives values from the path placeholders. When these three parts are declared consistently, tests can accurately simulate how clients call the endpoint and catch route, method, or binding errors early before deploying the application.
