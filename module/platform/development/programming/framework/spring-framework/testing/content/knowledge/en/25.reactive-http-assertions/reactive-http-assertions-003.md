# JSONPath, JSON Comparison, and Empty Body Checks

When testing Spring MVC responses, there are three common needs: reading part of the JSON data by path, comparing the entire response against expected JSON, and verifying that the response has no body. Each check fits a different type of contract. JSONPath fits when only certain fields matter; JSON comparison fits when response structure and data must be verified together; empty body checks fit responses such as `204 No Content`, `HEAD`, or endpoints that only confirm an operation.

MockMvc provides these matchers through `MockMvcResultMatchers.jsonPath(...)` and `MockMvcResultMatchers.content()`. The test sends the request as a simulated servlet request, then verifies the status, headers, and body produced by Spring MVC.

## Preparing MockMvc and dependencies

With Spring Boot, `@WebMvcTest` can be used to load the web layer and inject `MockMvc`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;
}
```

With plain Spring MVC or a full application context, MockMvc can be built with `MockMvcBuilders.webAppContextSetup(webApplicationContext)`. The examples below focus on assertions, so they assume `mockMvc` is already initialized and the controller returns JSON matching the illustrated contract.

The JSONPath matcher requires the Jayway JSONPath library (`com.jayway.jsonpath:json-path`) on the test classpath. JSON comparison via `content().json(...)` requires JSONassert (`org.skyscreamer:jsonassert`). Spring Boot test starters typically manage these common testing libraries; for plain Spring projects, declare the corresponding test dependencies and let the project's dependency management handle compatible versions.

## What is JSONPath?

JSONPath is a syntax for querying an element or set of elements within a JSON document. It is similar to how XPath queries XML, but designed for JSON. In Spring MockMvc, `jsonPath(expression)` creates a `ResultMatcher` used to read values by expression and compare them against expected results.

Commonly used syntax:

| Syntax | Meaning | Example |
|---|---|---|
| `$` | Root JSON document | `$` |
| `.property` | Property of an object | `$.customer.name` |
| `['property']` | Property via bracket notation | `$['customer']['name']` |
| `[0]` | First element of an array | `$.items[0]` |
| `[*]` | All elements in an array | `$.items[*].id` |
| `..property` | Search for property across descendant levels | `$..id` |
| `[?(...)]` | Filter elements by condition | `$.items[?(@.active == true)]` |

Suppose an endpoint returns this response:

```json
{
  "id": 42,
  "status": "PAID",
  "total": 125.50,
  "customer": {
    "name": "Mai Nguyen",
    "email": "mai@example.test"
  },
  "items": [
    { "sku": "KB-01", "quantity": 1, "active": true },
    { "sku": "MS-02", "quantity": 2, "active": true }
  ]
}
```

A simple field can be checked as follows:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(get("/api/orders/{id}", 42L))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value(42))
        .andExpect(jsonPath("$.status").value("PAID"))
        .andExpect(jsonPath("$.customer.name").value("Mai Nguyen"));
```

A single request can have multiple `andExpect(jsonPath(...))` calls. Each matcher focuses on one part of the contract, so when it fails, the error message usually pinpoints which path had an incorrect value.

## Checking nested objects and arrays

For nested objects, chain property names with dots:

```java
mockMvc.perform(get("/api/orders/{id}", 42L))
        .andExpect(jsonPath("$.customer.email")
                .value("mai@example.test"));
```

For arrays, use an index if position is part of the contract:

```java
mockMvc.perform(get("/api/orders/{id}", 42L))
        .andExpect(jsonPath("$.items[0].sku").value("KB-01"))
        .andExpect(jsonPath("$.items[1].quantity").value(2));
```

If element order does not matter, query all values with a wildcard and use a Hamcrest matcher:

```java
import static org.hamcrest.Matchers.containsInAnyOrder;

mockMvc.perform(get("/api/orders/{id}", 42L))
        .andExpect(jsonPath("$.items[*].sku")
                .value(containsInAnyOrder("KB-01", "MS-02")));
```

When order is part of the API contract, use an ordered matcher:

```java
import static org.hamcrest.Matchers.contains;

mockMvc.perform(get("/api/orders/{id}", 42L))
        .andExpect(jsonPath("$.items[*].sku")
                .value(contains("KB-01", "MS-02")));
```

Wildcards return a collection of values matching the expression. Using `containsInAnyOrder` keeps the test independent of array order; using `contains` simultaneously verifies order.

You can check the number of elements using JSONPath's `length()` function:

```java
mockMvc.perform(get("/api/orders/{id}", 42L))
        .andExpect(jsonPath("$.items.length()").value(2));
```

To verify that an element meets a condition, use a filter:

```java
mockMvc.perform(get("/api/orders/{id}", 42L))
        .andExpect(jsonPath("$.items[?(@.sku == 'MS-02')].quantity")
                .value(contains(2)));
```

Filters are especially useful when the response is a list whose order may change, yet the test needs to verify an element by business key. Do not rely on fixed indices if the API does not guarantee order.

## Checking data types

JSON distinguishes between string, number, boolean, object, array, and null. Do not just check values that look the same when printed; for instance, the number `42` differs from the string `"42"`.

Spring provides data type matchers:

```java
mockMvc.perform(get("/api/orders/{id}", 42L))
        .andExpect(jsonPath("$.id").isNumber())
        .andExpect(jsonPath("$.status").isString())
        .andExpect(jsonPath("$.items").isArray())
        .andExpect(jsonPath("$.customer").isMap());
```

For booleans:

```java
mockMvc.perform(get("/api/orders/{id}", 42L))
        .andExpect(jsonPath("$.items[0].active").isBoolean())
        .andExpect(jsonPath("$.items[0].active").value(true));
```

For floating-point numbers, a tolerance matcher avoids relying on exact floating-point representation:

```java
import static org.hamcrest.Matchers.closeTo;

mockMvc.perform(get("/api/orders/{id}", 42L))
        .andExpect(jsonPath("$.total").value(closeTo(125.50, 0.001)));
```

If numeric values are serialized as `BigDecimal`, `Double`, or another `Number` type, the matcher needs to accept the corresponding numeric type. When explicit target type coercion is needed, Spring provides `value(expectedValue, targetType)` or `value(matcher, targetType)` overloads on JSONPath matchers in supported versions. Only use explicit coercion when the test needs to verify a specific conversion type; normally checking the value and `isNumber()` is sufficient.

## Distinguishing missing fields, null fields, and empty fields

These three states have different meanings in JSON:

```json
{
  "nickname": null,
  "tags": [],
  "metadata": {}
}
```

- Missing field: the response does not contain that key.
- Field with `null` value: the key exists but has no JSON value.
- Empty field: the key exists and holds an empty string, empty array, or empty object.

The JSONPath matcher has dedicated checks:

```java
mockMvc.perform(get("/api/profile"))
        .andExpect(jsonPath("$.nickname").hasJsonPath())
        .andExpect(jsonPath("$.nickname").value(nullValue()))
        .andExpect(jsonPath("$.legacyCode").doesNotHaveJsonPath())
        .andExpect(jsonPath("$.tags").isArray())
        .andExpect(jsonPath("$.tags").isEmpty())
        .andExpect(jsonPath("$.metadata").isMap())
        .andExpect(jsonPath("$.metadata").isEmpty());
```

The `exists()` and `doesNotExist()` matchers are commonly used to verify presence/absence of a matching value. When you need to clearly distinguish a key that exists with a `null` value from a key that does not exist at all, use `hasJsonPath()`/`doesNotHaveJsonPath()` combined with `value(nullValue())` for the null case.

For an empty string, check directly:

```java
mockMvc.perform(get("/api/profile"))
        .andExpect(jsonPath("$.nicknameLabel").value(""));
```

Do not use `doesNotExist()` to check an empty array or empty string. The path still exists; its value is simply empty.

## Checking JSON with content().json()

JSONPath is suitable when only a few properties need to be verified. When you need to verify both structure and multiple values in a response, you can compare the response JSON against a sample JSON document:

```java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;

String expectedJson = """
        {
          "id": 42,
          "status": "PAID",
          "customer": {
            "name": "Mai Nguyen",
            "email": "mai@example.test"
          }
        }
        """;

mockMvc.perform(get("/api/orders/{id}", 42L))
        .andExpect(content().json(expectedJson));
```

`content().json(...)` parses both JSON documents and compares structure and values. It does not compare JSON strings character-by-character, so differences in whitespace, line breaks, or key order within an object do not fail the test.

### Strict and lenient comparison

Spring MockMvc supports strict or lenient comparison modes:

```java
// Strict: requires structure and array order to match.
mockMvc.perform(get("/api/orders/{id}", 42L))
        .andExpect(content().json(expectedJson, true));

// Lenient: allows extra fields and does not enforce array order.
mockMvc.perform(get("/api/orders/{id}", 42L))
        .andExpect(content().json(expectedJson, false));
```

`strict = true` mode requires the response to have no extra fields beyond the sample JSON and array element order to match. `strict = false` mode allows extra fields in objects and does not enforce array order; fields and values specified in the sample JSON must still exist in the response.

Choose the mode based on the API contract:

| Case | Suitable mode |
|---|---|
| Response has a fixed schema, no out-of-contract fields allowed | Strict |
| API may add backwards-compatible fields | Lenient |
| Array order is specified and important | Strict or verify separately with ordered JSONPath |
| Array order is not guaranteed | Lenient or JSONPath with `containsInAnyOrder` |
| Only a few fields matter | JSONPath is usually easier to read |

If your Spring Test version supports `JsonCompareMode`, you can use the enum overload instead of the boolean to express intent more clearly. The boolean overload common in earlier Spring versions is still widely used in existing tests.

### When the sample JSON contains arrays

Strict comparison makes array order part of the assertion:

```java
String expected = """
        {
          "items": [
            {"sku": "KB-01"},
            {"sku": "MS-02"}
          ]
        }
        """;

mockMvc.perform(get("/api/orders/{id}", 42L))
        .andExpect(content().json(expected, true));
```

If the API does not guarantee order, lenient comparison may be more appropriate. However, lenient comparison still compares object contents; it does not mean ignoring all differences.

## Combining JSONPath and JSON comparison

The two checks can complement each other. Use `content().json(...)` to verify overall structure, then use JSONPath for important business rules or fields requiring type checks:

```java
mockMvc.perform(get("/api/orders/{id}", 42L))
        .andExpect(content().json(expectedJson, false))
        .andExpect(jsonPath("$.status").value("PAID"))
        .andExpect(jsonPath("$.total").isNumber())
        .andExpect(jsonPath("$.items").isNotEmpty());
```

Do not repeat every field in both the sample JSON and JSONPath. Use JSON comparison for overall structure, and JSONPath for conditions needing clear error messages or having distinct business meaning.

If the JSON response has timestamps, UUIDs, or dynamically generated values, comparing the whole JSON may couple the test to unrelated data. In that case, JSONPath for stable fields is easier to maintain; or fix the clock/ID in the test to produce a deterministic response.

## Checking an empty response body

Some valid endpoints return a status without response content. For example:

- `204 No Content` after a successful deletion.
- `HEAD` returning headers matching GET without a body.
- An endpoint returning `202 Accepted` without sending a payload.
- `304 Not Modified` in a conditional request flow.

With MockMvc, an empty body can be verified with `content().string("")`:

```java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(delete("/api/orders/{id}", 42L))
        .andExpect(status().isNoContent())
        .andExpect(content().string(""));
```

If you want to check at the byte level, use `content().bytes(new byte[0])`:

```java
mockMvc.perform(delete("/api/orders/{id}", 42L))
        .andExpect(status().isNoContent())
        .andExpect(content().bytes(new byte[0]));
```

Both approaches verify that the body contains no characters or bytes. If the response contains a single space or newline character, the body is no longer empty and the assertion will fail. Do not use `trim()` in tests if the contract requires the response to genuinely have zero bytes.

### Empty body differs from JSON null and empty JSON

The following responses are not equivalent:

| Body | Actual content | Is it an empty body? |
|---|---|---|
| Zero bytes | `""` | Yes |
| JSON null | `null` | No |
| Empty JSON object | `{}` | No |
| Empty JSON array | `[]` | No |
| Empty JSON string | `""` (two double quotes in the body) | No |
| Whitespace only | ` ` or newline | No |

If an endpoint returns an empty JSON object, use `content().json("{}")` or an appropriate JSONPath. If an endpoint returns JSON `null`, verify the body with `content().string("null")`. Only use `content().string("")` when the contract actually requires no response body.

Do not call `jsonPath(...)` or `content().json(...)` on an empty response body. Those matchers require a valid JSON document to parse; for empty bodies, check directly with string or byte matchers.

## Checking empty bodies for HEAD and special statuses

A `HEAD` endpoint returns no response body. Tests can verify the status and certain headers:

```java
mockMvc.perform(head("/api/orders/{id}", 42L))
        .andExpect(status().isOk())
        .andExpect(header().exists("ETag"))
        .andExpect(content().string(""));
```

With `204 No Content`, the status is part of the contract; tests should verify both the status and the empty body. Do not assert only an empty body because a broken controller could return `200 OK` with no content and still pass that assertion.

With `304 Not Modified`, no response body is sent either. If a test checks conditional GET, verify that the request sends the appropriate `If-None-Match` or `If-Modified-Since`, receives status `304`, and has an empty body. Headers may still include metadata needed for caching.

## A complete example for all three assertion types

Suppose an API has three endpoints:

```java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{id}")
    OrderResponse get(@PathVariable long id) {
        return orderService.get(id);
    }

    @GetMapping
    List<OrderSummary> list() {
        return orderService.list();
    }

    @DeleteMapping("/{id}")
    ResponseEntity<Void> delete(@PathVariable long id) {
        orderService.delete(id);
        return ResponseEntity.noContent().build();
    }
}
```

JSONPath test for a few fields:

```java
mockMvc.perform(get("/api/orders/{id}", 42L))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value(42))
        .andExpect(jsonPath("$.status").value("PAID"))
        .andExpect(jsonPath("$.customer.email")
                .value("mai@example.test"));
```

Full JSON comparison test:

```java
String expected = """
        [
          {"id": 42, "status": "PAID"},
          {"id": 43, "status": "SHIPPED"}
        ]
        """;

mockMvc.perform(get("/api/orders"))
        .andExpect(status().isOk())
        .andExpect(content().json(expected, true));
```

Empty body test:

```java
mockMvc.perform(delete("/api/orders/{id}", 42L))
        .andExpect(status().isNoContent())
        .andExpect(content().string(""));
```

Each test verifies a different contract: specific values inside JSON, the structure of the entire JSON response, and the complete absence of a body.

## Common mistakes when writing assertions

| Symptom | Possible cause | How to fix |
|---|---|---|
| JSONPath reports path not found | Wrong field name, wrong object level, or response is not JSON | Check response body and ensure expression starts from `$` |
| Field looks identical yet assertion fails | JSON number confused with string or different numeric type | Use `isNumber()`, numeric matchers, or explicit coercion when needed |
| `doesNotExist()` fails on empty array | Path exists and its value is `[]` | Use `isEmpty()` or compare against empty array |
| Cannot distinguish null from missing field | Using a matcher that only checks value | Combine `hasJsonPath()` with `value(nullValue())` or use `doesNotHaveJsonPath()` |
| JSON comparison fails due to extra fields | Using strict mode | Use lenient mode if the API allows extensible fields |
| JSON comparison fails due to array order | Strict mode requires matching order | Use lenient mode or JSONPath with `containsInAnyOrder` if order is not contracted |
| `content().json(...)` fails to parse | Missing JSONassert or body is not valid JSON | Add dependency and inspect actual response body |
| JSONPath matcher fails to run | Missing Jayway JSONPath on test classpath | Add `json-path` dependency |
| Empty body test still fails | Response contains whitespace or newline | Inspect actual bytes/string and verify whether contract demands strictly zero bytes |
| Empty body test passes despite wrong endpoint | Asserting only body without asserting status | Verify status and headers alongside body |

## Choosing the right verification approach

| Goal | Verification approach |
|---|---|
| One field or nested property | `jsonPath("$.customer.email").value(...)` |
| Field has correct JSON type | `isString()`, `isNumber()`, `isBoolean()`, `isArray()`, `isMap()` |
| Element in an array | Index, wildcard, or filter expression |
| Array independent of order | `containsInAnyOrder(...)` or lenient JSON comparison |
| Complete JSON contract | `content().json(expected, true)` |
| JSON allowing extra fields | `content().json(expected, false)` |
| Null field vs. missing field | `hasJsonPath()`/`doesNotHaveJsonPath()` and null matcher |
| Body with zero bytes | `content().string("")` or `content().bytes(new byte[0])` |

JSONPath keeps tests focused on business-meaningful values. JSON comparison protects response structure against a clear template. Empty body assertions confirm that an endpoint truly sends no payload. Combining these three approaches accurately tests Spring MVC responses without coupling tests to JSON formatting details outside the API contract.
