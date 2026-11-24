# Asserting the Contract Instead of Checking Only Status 200

In Spring MVC, a request can return HTTP 200 while still violating what the client expects. The response might omit fields, return the wrong content type, lack required headers, or carry incorrect business values. Therefore, a good MVC test should verify the response contract observed by the client rather than stopping at the status code.

A response contract typically includes the status code, content type, headers, cookies, body structure, field values, and error behavior for invalid requests. For view-returning controllers, the contract can also include the view name, model attributes, redirect URL, and flash attributes. MockMvc provides `ResultMatcher` implementations to assert each of these parts.

## 1. Status 200 Verifies Only One Part

The following assertion is useful, yet insufficient on its own:

```java
mockMvc.perform(get("/api/orders/42"))
        .andExpect(status().isOk());
```

It only proves the response returned status 200. The test would still pass in any of these cases:

- The body is empty even though the client expects a JSON object.
- The response returns `text/plain` instead of `application/json`.
- The JSON contains `orderId` while the contract requires `id`.
- The `status` field has the wrong value, such as `CANCELLED` instead of `PAID`.
- Required `Location`, `ETag`, or business headers are missing.
- A resource-creation endpoint returns 200 when the contract specifies 201 Created.

Instead of checking status in isolation, describe everything the client relies on:

| Contract Element | Question to Answer | Common Matcher |
|---|---|---|
| Status | Did the request succeed, create a resource, or get rejected? | `status()` |
| Content type | Is the response JSON, HTML, or another content type? | `content()` |
| Headers and cookies | Are required metadata or cookies present? | `header()`, `cookie()` |
| Body | Are the structure and data values right? | `jsonPath()`, `content()` |
| View and model | Did MVC choose the right view and supply the right data? | `view()`, `model()` |
| Redirect and flash | After the operation, where is the user sent and with what message? | `redirectedUrl()`, `flash()` |

## 2. Asserting Status by HTTP Semantics

Choose matchers that express the exact business outcome. Common matchers include:

```java
status().isOk();                 // 200
status().isCreated();            // 201
status().isAccepted();           // 202
status().isNoContent();          // 204
status().isBadRequest();         // 400
status().isUnauthorized();       // 401
status().isForbidden();          // 403
status().isNotFound();           // 404
status().isConflict();           // 409
status().isUnprocessableEntity();// 422
```

For example, an order-creation endpoint might return 201 Created. A successful deletion might return 204 No Content if the contract specifies no body. Validation errors might return 400 or 422 depending on API conventions; what matters is that the test matches the agreed contract.

Avoid forcing every response to 200 just to keep tests simple. Status codes are part of the protocol that clients use to decide their next step.

## 3. Asserting Content Type and Headers

For JSON APIs, assert that the response declares JSON:

```java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.http.MediaType.APPLICATION_JSON;

mockMvc.perform(get("/api/orders/42").accept(APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(APPLICATION_JSON));
```

`contentTypeCompatibleWith(...)` is appropriate when charset or media type parameters may vary while remaining compatible. If the contract requires an exact media type, use `contentType(...)` with the specific value.

Asserting headers:

```java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;

mockMvc.perform(get("/api/orders/42"))
        .andExpect(header().exists("X-Request-Id"))
        .andExpect(header().string("X-Api-Version", "v1"))
        .andExpect(header().doesNotExist("X-Debug-Token"));
```

For resource-creation endpoints, the `Location` header typically points to the URL of the newly created resource:

```java
mockMvc.perform(post("/api/orders").contentType(APPLICATION_JSON)
        .content("{\"customerId\":\"C-12\"}"))
        .andExpect(status().isCreated())
        .andExpect(header().string("Location", "/api/orders/42"));
```

You can also assert cookies if they are part of the contract:

```java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.cookie;

mockMvc.perform(post("/login"))
        .andExpect(cookie().exists("SESSION"))
        .andExpect(cookie().httpOnly("SESSION", true));
```

Assert only the headers and cookies that clients or security actually depend on. For randomly generated framework values, such as session IDs or request IDs, typically assert existence and required attributes instead of comparing against a hard-coded string.

## 4. Asserting JSON Structure and Values

`jsonPath(...)` lets you query parts of a JSON response without deserializing the entire body into an object inside the test.

Example controller returning an order:

```java
import java.math.BigDecimal;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{id}")
    ResponseEntity<OrderResponse> find(@PathVariable String id) {
        OrderResponse response = new OrderResponse(
                id, "PAID", new BigDecimal("125.00"));
        return ResponseEntity.ok()
                .header("X-Api-Version", "v1")
                .body(response);
    }
}

record OrderResponse(String id, String status, BigDecimal total) {}
```

Test asserting the contract:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.http.MediaType.APPLICATION_JSON;

@Test
void returnsOrderRepresentation() throws Exception {
    mockMvc.perform(get("/api/orders/42").accept(APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(APPLICATION_JSON))
            .andExpect(header().string("X-Api-Version", "v1"))
            .andExpect(jsonPath("$.id").value("42"))
            .andExpect(jsonPath("$.status").value("PAID"))
            .andExpect(jsonPath("$.total").isNumber());
}
```

These assertions ensure the client receives JSON with the right order ID, status, and numeric total field. With only `status().isOk()`, all of these body and metadata details could be wrong while the test still passed.

### Useful JSONPath Matchers

```java
jsonPath("$.id").value("42");
jsonPath("$.total").isNumber();
jsonPath("$.paid").isBoolean();
jsonPath("$.items").isArray();
jsonPath("$.customer").isMap();
jsonPath("$.items").isNotEmpty();
jsonPath("$.debug").doesNotExist();
```

You can assert array elements:

```java
jsonPath("$.items[0].sku").value("SKU-001");
jsonPath("$.items[0].quantity").value(2);
jsonPath("$.items.length()").value(1);
```

For more complex conditions, Hamcrest matchers express intent cleanly:

```java
import static org.hamcrest.Matchers.hasSize;
import static org.hamcrest.Matchers.greaterThan;

jsonPath("$.items", hasSize(2));
jsonPath("$.total", greaterThan(0.0));
```

JSONPath keeps tests focused on the key parts of the contract. You do not need to assert every field if clients do not rely on them; however, identifiers, statuses, counts, and core business values generally deserve explicit checks.

## 5. Comparing the Full JSON Body

When a response has a small, stable structure, you can compare the body against expected JSON:

```java
mockMvc.perform(get("/api/orders/42"))
        .andExpect(content().json(
                "{\"id\":\"42\",\"status\":\"PAID\",\"total\":125.00}"));
```

JSON comparison is generally less brittle to field ordering and whitespace than raw string comparison. Be mindful of the comparison mode of the overload used: lenient mode typically allows extra fields and flexible array order; if the contract requires exact structure, choose strict mode when your Spring/JSONAssert version supports that overload, or combine specific JSONPath assertions.

Do not use `content().string(...)` to compare JSON merely because the expected string is easy to write. That can break tests on key ordering or formatting differences even when the JSON means the same thing. String comparison fits plain text, intentionally fixed HTML fragments, or bodies where exact byte/string formatting is part of the contract.

## 6. Asserting Empty Bodies and No-Content Responses

For endpoints returning 204, the contract typically requires status 204 and no body:

```java
mockMvc.perform(delete("/api/orders/42"))
        .andExpect(status().isNoContent())
        .andExpect(content().string(""));
```

Not every successful endpoint needs JSON. Assert the body according to the contract: a 204 response needs no JSON; a 201 response may include a representation of the new resource; a 202 response may return task-tracking information.

## 7. Asserting Error and Validation Contracts

Error responses are also part of the contract. Clients need to know the status, error code, and which fields are invalid. For example, an API might define validation errors in this shape:

```json
{
  "code": "VALIDATION_FAILED",
  "message": "Request is invalid",
  "fieldErrors": [
    { "field": "customerId", "message": "must not be blank" }
  ]
}
```

A test can submit an invalid request and assert both the status and error structure:

```java
mockMvc.perform(post("/api/orders")
        .contentType(APPLICATION_JSON)
        .content("{\"customerId\":\"\"}"))
        .andExpect(status().isBadRequest())
        .andExpect(content().contentTypeCompatibleWith(APPLICATION_JSON))
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.fieldErrors[0].field").value("customerId"))
        .andExpect(jsonPath("$.fieldErrors[0].message").isNotEmpty());
```

For the test to reflect the real validation pipeline, the controller must use `@Valid` or `@Validated` appropriately and the test must load validator configuration. If the application standardizes exceptions with `@RestControllerAdvice`, include that advice in the MockMvc context. With `standaloneSetup`, you can register advice using `.setControllerAdvice(...)`.

Beyond validation, verify other important contractual error cases: missing resources, unauthorized access, state conflicts, or invalid inputs. Do not assert only that the request failed; assert the error type and payload clients rely on to recover.

## 8. Asserting MVC Views, Models, and Redirects

MockMvc also supports controllers returning views instead of JSON. In that case, the controller contract may include the view name and model attributes:

```java
mockMvc.perform(get("/orders/new"))
        .andExpect(status().isOk())
        .andExpect(view().name("orders/form"))
        .andExpect(model().attributeExists("order"))
        .andExpect(model().attribute("mode", "create"));
```

For form submissions following Post/Redirect/Get, assert the redirect and flash attributes:

```java
mockMvc.perform(post("/orders")
        .param("customerId", "C-12"))
        .andExpect(status().is3xxRedirection())
        .andExpect(redirectedUrl("/orders/42"))
        .andExpect(flash().attribute("message", "Order created"));
```

These static matchers are typically imported from `MockMvcResultMatchers`: `view()`, `model()`, `redirectedUrl()`, and `flash()`. They verify the MVC outcomes that browsers or view renderers depend on.

## 9. One Test Should Describe Multiple Parts of the Same Contract

A complete test typically chains multiple `andExpect(...)` calls to express the response as a cohesive set of guarantees:

```java
@Test
void createsOrderAccordingToApiContract() throws Exception {
    mockMvc.perform(post("/api/orders")
            .contentType(APPLICATION_JSON)
            .accept(APPLICATION_JSON)
            .content("{\"customerId\":\"C-12\"}"))
            .andExpect(status().isCreated())
            .andExpect(content().contentTypeCompatibleWith(APPLICATION_JSON))
            .andExpect(header().string("Location", "/api/orders/42"))
            .andExpect(jsonPath("$.id").value("42"))
            .andExpect(jsonPath("$.customerId").value("C-12"))
            .andExpect(jsonPath("$.status").value("NEW"));
}
```

Reading the test top to bottom makes clear what the client sends and what it is guaranteed in return: resource created, resource URL returned, and representation including identifier, owner, and initial status.

## 10. Choosing the Right Level of Detail

Asserting too little lets contract bugs slip through. Asserting every internal detail makes tests brittle when implementation changes without affecting clients. Focus on properties that matter to consumers:

- Status code and its semantics.
- Content type and required headers/cookies.
- Names, types, and values of JSON fields used by clients.
- Error structure and validation details displayed by clients.
- View, model, or redirect in server-side MVC flows.

Avoid locking tests to current timestamps, randomly generated IDs, JSON object key order, non-contractual headers, or internal debug fields. When a dynamic value is part of the contract, verify its format or relationship instead of hard-coding a value that changes on every run.

For instance, rather than comparing a random request ID against a fixed string, verify that the header exists and is non-blank. For timestamps, assert ISO-8601 formatting or a reasonable range if required.

## 11. Organizing Tests for Readability and Maintainability

You can split tests by contractual behavior:

- `returnsOrderRepresentation`: verifies successful response.
- `createsOrderAndReturnsLocation`: verifies status 201, Location, and body.
- `returnsValidationErrorsForInvalidCustomer`: verifies validation status and payload.
- `returnsNotFoundWhenOrderDoesNotExist`: verifies the 404 error contract.

Each test should send one primary request and assert the relevant properties. If an endpoint has multiple important branches, write separate tests for each branch rather than cramming every scenario into one long test.

When several tests share the same request JSON or matchers, extract helpers to reduce duplication. Name helpers after the contract meaning, such as `expectOrderRepresentation(...)`, without hiding critical assertions.

When an assertion fails, `andDo(print())` prints the request and response for diagnostics:

```java
mockMvc.perform(get("/api/orders/42"))
        .andDo(print())
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value("42"));
```

`print()` only helps observe runtime output; it does not replace assertions or make a test verify more of the contract.

## 12. Common Mistakes

| Symptom | Common Cause | Resolution |
|---|---|---|
| Test passes despite broken body | Asserting only `status().isOk()` | Add content type, JSONPath, or body assertions matching the contract |
| JSONPath fails to find a field | Field name or JSON structure differs from assumption | Inspect the actual response and verify the path at the right level |
| Test fails on content type | Controller returns another media type or request omitted matching `Accept` | Check `produces`, `Accept`, and compatibility matchers |
| JSON comparison fails despite equivalent data | Raw string comparison or unnecessary strict mode | Use JSON-aware matchers and choose strictness per contract |
| Test depends on random values | Hard-coding dynamically generated IDs, timestamps, or session tokens | Check format, existence, or value relationships |
| Validation does not return expected errors | Missing `@Valid`, validator, or controller advice in test context | Load full validation and exception-handling configuration |
| Redirect test misses flash attributes | Checking response body instead of redirect/flash scope | Use `redirectedUrl()` and `flash()` |
| 204 response has unexpected body | Controller or advice is writing unintended content | Check implementation and verify the no-content contract |

## 13. Key Takeaways

HTTP 200 only states that the server treated the request as successful by status; it does not guarantee the response satisfies client needs. With MockMvc, combine `status()`, `content()`, `header()`, `cookie()`, `jsonPath()`, `view()`, `model()`, `redirectedUrl()`, and `flash()` to verify all contractual parts. Focus assertions on the status, metadata, structure, and data values that consumers rely on. That way, tests catch broken responses even when the status code is still 200.

