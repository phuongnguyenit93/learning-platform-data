# expectAll to Aggregate Multiple Assertions

When testing HTTP with Spring MockMvc, a request often has multiple conditions to verify at the same time: status, content type, headers, response body, selected handler, and other properties. If you chain multiple `andExpect(...)` calls, the test normally stops immediately at the first failing assertion. That causes each test run to reveal only one issue, even though the response may be wrong in multiple places.

Spring Framework 5.3 added `ResultActions.andExpectAll(...)` to execute multiple `ResultMatcher` instances against the same request result. This method continues running matchers after an assertion fails, then reports the collected failures. As a result, a single test run can point out multiple mismatches in the same response.

`andExpectAll` is especially useful when verifying an HTTP contract made up of multiple independent parts. It does not issue extra requests, does not run matchers in parallel, and does not make the test pass when an assertion fails. It only changes how Spring MVC Test executes and reports a group of assertions.

## 1. Why aggregate multiple assertions?

Suppose an endpoint returns order information. The response contract requires:

- HTTP status is 200.
- Content type is JSON.
- Header `X-Api-Version` has value `v1`.
- JSON has the expected `id` and `status`.
- The request is mapped to the right controller method.

With the traditional style:

```java
mockMvc.perform(get("/api/orders/{id}", 42)
                .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
        .andExpect(header().string("X-Api-Version", "v1"))
        .andExpect(jsonPath("$.id").value(42))
        .andExpect(jsonPath("$.status").value("READY"));
```

`andExpect(...)` calls are executed in order. When a matcher throws `AssertionError`, the assertion chain stops there. For example, if the status is right but a header is wrong, the subsequent JSON assertions might not run.

With `andExpectAll(...)`, you can group the matchers into a single call:

```java
mockMvc.perform(get("/api/orders/{id}", 42)
                .accept(MediaType.APPLICATION_JSON))
        .andExpectAll(
                status().isOk(),
                content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON),
                header().string("X-Api-Version", "v1"),
                jsonPath("$.id").value(42),
                jsonPath("$.status").value("READY")
        );
```

If one or more matchers fail, the remaining matchers are still executed. Afterwards, Spring reports the aggregated assertion error so the test runner marks the test as failed.

## 2. Which API does andExpectAll belong to and since which version?

`andExpectAll(...)` is a method on `org.springframework.test.web.servlet.ResultActions`, the object returned by `mockMvc.perform(...)`.

The method signature is:

```java
ResultActions andExpectAll(ResultMatcher... resultMatchers) throws Exception;
```

Key points to remember:

- Available since Spring Framework 5.3.
- Accepts one or more `ResultMatcher` instances via varargs.
- Each matcher is applied to the same `MvcResult` of the request just executed.
- Assertion failures are collected; if there are multiple failures, the first failure is thrown and subsequent failures are attached as suppressed exceptions.
- If all matchers succeed, the method returns `ResultActions` so further operations can be chained as appropriate.

Commonly used import example:

```java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
```

If a project uses Spring Framework before 5.3, `ResultActions` does not have `andExpectAll` yet. In that case, you can use separate `andExpect(...)` calls or build an appropriate assertion collection mechanism yourself. Adding AssertJ alone does not add this method; a supporting `spring-test` version is required.

## 3. How andExpectAll works

`MockMvc.perform(...)` creates and executes a mock request, then returns `ResultActions` bound to that result. Each `ResultMatcher` receives the same `MvcResult` to inspect one aspect of the request/response.

With `andExpectAll`, Spring invokes each matcher in the list sequentially. If a matcher throws `AssertionError`, Spring records that error and continues to the next matcher. Once all have finished:

- No errors: the call completes normally and returns `ResultActions`.
- One error: that assertion error is thrown.
- Multiple errors: the first assertion error is thrown, and the remaining errors are attached as suppressed exceptions.

High-level execution flow:

```text
mockMvc.perform(request)
          |
          v
      MvcResult
          |
          v
    andExpectAll(...)
          |
          +--> matcher 1 ----> pass / collect failure
          |
          +--> matcher 2 ----> pass / collect failure
          |
          +--> matcher 3 ----> pass / collect failure
          |
          +--> matcher n ----> pass / collect failure
          |
          v
  All matchers completed
          |
          +--> no failures: continue
          |
          +--> failures: throw first AssertionError
               with remaining failures suppressed
```

Matchers still execute sequentially. `andExpectAll` does not create a thread per matcher and does not resend the request to the controller.

### Why is collecting failures helpful?

When a response fails to meet its contract, a fail-fast assertion normally forces the test author to fix one error and rerun to see the next one. `andExpectAll` surfaces multiple independent issues in a single pass, reducing iteration cycles when dealing with multi-field responses.

However, aggregated results are only useful when the matchers verify independent conditions that can be evaluated against the same response. If a later matcher depends on the result of an earlier one, separate the logic or write a dedicated matcher with a clear message.

## 4. Example verifying a JSON response contract

Suppose a controller returns a DTO:

```java
public class OrderResponse {

    private final long id;
    private final String status;
    private final String customer;

    public OrderResponse(long id, String status, String customer) {
        this.id = id;
        this.status = status;
        this.customer = customer;
    }

    public long getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }

    public String getCustomer() {
        return customer;
    }
}
```

Controller:

```java
@RestController
public class OrderController {

    @GetMapping("/api/orders/{id}")
    public ResponseEntity<OrderResponse> getOrder(@PathVariable long id) {
        OrderResponse body = new OrderResponse(id, "READY", "alice");

        return ResponseEntity.ok()
                .header("X-Api-Version", "v1")
                .body(body);
    }
}
```

Test:

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void returnsExpectedOrderResponse() throws Exception {
        mockMvc.perform(get("/api/orders/{id}", 42)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpectAll(
                        status().isOk(),
                        content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON),
                        header().string("X-Api-Version", "v1"),
                        jsonPath("$.id").value(42),
                        jsonPath("$.status").value("READY"),
                        jsonPath("$.customer").value("alice")
                );
    }
}
```

Matchers are evaluated independently on the response. If the status is right but `customer` is wrong, the test still runs the header, id, and status matchers before reporting the aggregated failure.

## 5. Using andExpectAll for error responses

Error responses often have multiple parts to verify: status, content type, error code, message, and field validation details.

Example validation error response:

```json
{
  "code": "VALIDATION_ERROR",
  "message": "Request contains invalid fields",
  "fieldErrors": [
    {
      "field": "email",
      "message": "must be a well-formed email address"
    }
  ]
}
```

The test can verify multiple parts at once:

```java
mockMvc.perform(post("/api/users")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"email":"invalid-email"}
                        """))
        .andExpectAll(
                status().isBadRequest(),
                content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON),
                jsonPath("$.code").value("VALIDATION_ERROR"),
                jsonPath("$.message").isNotEmpty(),
                jsonPath("$.fieldErrors[0].field").value("email"),
                jsonPath("$.fieldErrors[0].message").isNotEmpty()
        );
```

This example assumes the endpoint has validation and exception advice producing the JSON structure above. If the application returns a different status or error structure, matchers must reflect the actual contract.

For error responses, avoid checking only the status. Two responses can both be 400 while one omits the error code or has the wrong field name. `andExpectAll` verifies the entire error contract in one execution.

## 6. Combining multiple matcher categories

`andExpectAll` accepts any compatible `ResultMatcher`, so matchers from different categories can be combined.

| Category | Common matchers | What is verified |
| --- | --- | --- |
| Status | `status().isOk()`, `isCreated()`, `isBadRequest()` | HTTP status code |
| Header | `header().exists(...)`, `string(...)`, `longValue(...)` | Response headers |
| Content | `content().contentType(...)`, `string(...)`, `bytes(...)` | Response type and content |
| JSONPath | `jsonPath(...).value(...)`, `exists()`, `isArray()` | JSON fields and structure |
| Handler | `handler().handlerType(...)`, `methodName(...)` | Selected controller/handler |
| Cookie | `cookie().exists(...)`, `value(...)` | Response cookies |
| Model | `model().attribute(...)`, `attributeExists(...)` | MVC model attributes |
| View | `view().name(...)` | Selected view |
| Request | `request().asyncStarted()`, `asyncResult(...)` | Request state and async result |

Example verifying both handler and response:

```java
mockMvc.perform(get("/api/orders/{id}", 42))
        .andExpectAll(
                handler().handlerType(OrderController.class),
                handler().methodName("getOrder"),
                status().isOk(),
                header().string("X-Api-Version", "v1"),
                jsonPath("$.id").value(42)
        );
```

When a test aims to verify routing, handler matchers catch cases where a different controller accidentally handles the request while still returning a seemingly valid response.

## 7. Comparing andExpect and andExpectAll

| Criterion | `andExpect(...)` | `andExpectAll(...)` |
| --- | --- | --- |
| Matchers per call | One matcher | One or more matchers |
| Execution behavior | Runs current matcher | Runs all matchers sequentially |
| When a matcher fails | Throws assertion error and stops current chain | Records error and continues to later matchers |
| Reporting multiple errors | Subsequent runs reveal later errors | Aggregates assertion failures in the same run |
| Outcome on failure | Test fails | Test still fails after all matchers complete |
| Version | Available since older Spring MVC Test releases | Available since Spring Framework 5.3 |

Fail-fast example:

```java
mockMvc.perform(get("/api/orders/42"))
        .andExpect(status().isOk())
        .andExpect(header().string("X-Api-Version", "v1"))
        .andExpect(jsonPath("$.status").value("READY"));
```

If the status is wrong, the header and JSON matchers may not run.

Aggregated example:

```java
mockMvc.perform(get("/api/orders/42"))
        .andExpectAll(
                status().isOk(),
                header().string("X-Api-Version", "v1"),
                jsonPath("$.status").value("READY")
        );
```

With the second approach, all three conditions are evaluated. Use `andExpectAll` when you want multiple errors reported at once; use `andExpect` when you need fail-fast behavior or when a later check only makes sense after an earlier condition holds.

## 8. Writing a custom ResultMatcher

When multiple tests need to check the same rule, you can create a custom `ResultMatcher` and pass it into `andExpectAll`. `ResultMatcher` is a functional interface that accepts `MvcResult` and can throw an exception if the result is incorrect.

Example checking a correlation ID header:

```java
public final class ApiResultMatchers {

    private ApiResultMatchers() {
    }

    public static ResultMatcher hasCorrelationId() {
        return result -> {
            String value = result.getResponse()
                    .getHeader("X-Correlation-Id");

            assertThat(value)
                    .as("X-Correlation-Id response header")
                    .isNotBlank();
        };
    }
}
```

Usage:

```java
mockMvc.perform(get("/api/orders/42"))
        .andExpectAll(
                status().isOk(),
                ApiResultMatchers.hasCorrelationId(),
                jsonPath("$.id").value(42)
        );
```

Custom matchers centralize shared response rules and avoid duplicating logic across tests. Give AssertJ assertions descriptive labels or craft clear failure messages so readers know which condition failed.

A custom matcher should verify one meaningful behavior. Avoid creating overly large matchers that check status, headers, JSON, database state, and side effects all at once, as that makes it hard to tell which condition failed and reduces reusability.

## 9. Caveats when using andExpectAll

### All matchers inspect the same MvcResult

`andExpectAll` does not re-execute the request for each matcher. Every matcher receives the result of the same `mockMvc.perform(...)` call. If you need to test two different requests, you must call `perform(...)` twice.

### Matcher order still matters

Matchers are executed in the order provided. Although assertion failures are collected without stopping the group, a matcher could depend on data prepared or modified by an earlier matcher. Avoid side effects inside matchers; design each matcher to read the result independently.

### Not every error is an AssertionError

The purpose of `andExpectAll` is to aggregate assertion failures. An abnormal execution error such as an exception while reading data or a matcher configuration error may not be treated like an assertion mismatch. Do not use `andExpectAll` to mask unexpected exceptions.

### Matchers must match the actual response

For example, `jsonPath(...)` requires a response body that can be read as JSON. If the response is not JSON, the matcher may report a parse error. If you want to verify both that the response is JSON and its internal fields, placing the content type matcher before JSONPath can make error messages clearer; `andExpectAll` still continues running the other matchers if one fails.

### Do not overcomplicate tests just to bundle everything

A test should verify one clear behavior or contract. If you pack too many unrelated conditions into one `andExpectAll`, failure reports become long and harder to diagnose. Split tests by scenario or endpoint when behaviors do not share the same objective.

## 10. Diagnosing multiple assertion failures

When `andExpectAll` detects multiple failures, the first assertion error is thrown and the remaining assertion errors are attached as suppressed exceptions. Exact display depends on the test runner and IDE; some UIs collapse suppressed exceptions.

To make diagnosis convenient:

- Use matchers with clear failure messages, especially for custom matchers.
- Group assertions around a related response contract.
- Use `andDo(print())` before `andExpectAll(...)` if you need to print the request/response even when later assertions fail.
- Or configure `alwaysDo(print())` on the MockMvc builder to print results for every request in the test scope.
- Inspect suppressed exceptions when a report only displays the first assertion error.

Example printing results before assertions:

```java
mockMvc.perform(get("/api/orders/42"))
        .andDo(print())
        .andExpectAll(
                status().isOk(),
                header().string("X-Api-Version", "v1"),
                jsonPath("$.id").value(42),
                jsonPath("$.status").value("READY")
        );
```

Placing `andDo(print())` before `andExpectAll` ensures printing runs before the assertion group can throw an aggregated error. If placed after `andExpectAll`, when assertions fail the trailing print action may not run.

## 11. Using expectAll in practical MVC tests

Some fitting use cases:

### Successful data-returning APIs

Verify status, content type, cache headers, handler, and required JSON fields.

### Validation error APIs

Verify status 400, error code, message, field names, and error list structure.

### Resource creation APIs

Verify status 201, `Location` header, content type, and the ID of the newly created resource.

### Authenticated APIs

Verify status 401/403 or configured redirects, along with headers and error response body.

### View-returning controllers

Combine handler, status, view name, and model attribute matchers to verify that MVC selected the right handler and prepared rendering data.

Resource creation API example:

```java
mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"customer":"alice"}
                        """))
        .andExpectAll(
                status().isCreated(),
                content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON),
                header().exists("Location"),
                jsonPath("$.id").isNumber(),
                jsonPath("$.customer").value("alice"),
                jsonPath("$.status").value("NEW")
        );
```

The matchers in this example collectively describe the contract of an order creation operation. If a field is missing or the `Location` header is not generated, the test can still report any other discrepancies in the same run.

## 12. andExpectAll and MockMvcTester

`andExpectAll(...)` belongs to the traditional MockMvc `ResultActions` API. `MockMvcTester` is a newer AssertJ API with its own assertion style such as `hasStatusOk()`, `bodyText()`, and `bodyJson()`.

Do not confuse the two mechanisms:

```java
// MockMvc ResultActions
mockMvc.perform(get("/api/orders/42"))
        .andExpectAll(
                status().isOk(),
                jsonPath("$.id").value(42),
                jsonPath("$.status").value("READY")
        );

// MockMvcTester with AssertJ
assertThat(mvcTester.get().uri("/api/orders/42"))
        .hasStatusOk()
        .bodyJson()
        .extractingPath("$.id")
        .isEqualTo(42);
```

MockMvcTester fits when you want to write AssertJ-style assertions. `andExpectAll` fits when you need to run multiple `ResultMatcher` instances and aggregate assertion failures. Both are built on the Spring MVC Test infrastructure and can be chosen based on your project's testing style.

## 13. Conclusion

`ResultActions.andExpectAll(...)` allows verifying multiple aspects of the same response in a single request. Since Spring Framework 5.3, this method executes all `ResultMatcher` instances sequentially, collects assertion failures, and reports an aggregated failure once the matcher group finishes.

Use `andExpectAll` to verify HTTP contracts with multiple independent conditions such as status, headers, content type, JSON body, and handler. Use individual `andExpect` calls when you need fail-fast behavior or when a subsequent step depends on a prior condition. When scoped appropriately, `andExpectAll` gives more diagnostic information in a single test run while keeping assertions tied to one specific request.
