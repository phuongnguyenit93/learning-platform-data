# JSONPath, JSON Assertions, and Response Data

In Spring MVC, returning HTTP 200 does not prove an API works correctly. An endpoint can return the right status while having wrong field names, missing array elements, wrong currency units, leaked sensitive data, or returning `null` where the contract requires a field to be absent. Therefore, **testing returned JSON payloads** is an essential part of controller and integration tests.

With Spring MVC Test, **`MockMvc`** simulates requests passing through Spring MVC configuration without opening an HTTP server. `MockMvcResultMatchers.jsonPath(...)` checks specific parts of JSON using **JSONPath** expressions; `content().json(...)` compares an entire JSON structure. Combining these with status, headers, content type, and business assertions helps tests catch real bugs without locking onto field ordering or whitespace.

This lesson applies to **Java 17+, Spring Boot 3.5.x, Spring Framework 6.2.x, and JUnit Jupiter 5**. Examples run under `@WebMvcTest` with `@MockitoBean` for non-MVC dependencies. On Boot 3.3 and earlier, the Spring bean mocking annotation is typically `@MockBean`; update APIs appropriately when upgrading versions. On Spring Boot 4 / Spring Framework 7 branches, verify package names, dependencies, and default behaviors for that version.

**After this lesson, you will be able to:**

- Write JSONPath expressions to access fields, nested objects, array elements, wildcards, filters, and lengths.
- Distinguish `exists()`, `hasJsonPath()`, `doesNotExist()`, and `doesNotHaveJsonPath()` when fields can be `null`.
- Use Hamcrest `contains`, `containsInAnyOrder`, `hasSize`, and data-type matchers.
- Choose between `content().json(..., JsonCompareMode.STRICT)` and `LENIENT` based on the API contract.
- Verify response shapes, arrays, pagination, HTTP 404s, validation errors, Unicode, and escaping.
- Avoid false positives from out-of-scope mock data, floating-point/date formatting pitfalls, nondeterministic array ordering, or verbatim JSON string comparisons.
- Write and run a complete test suite with `MockMvc`, Spring Boot, and JSON assertions.

## 1. What Should JSON Assertions Protect?

Suppose an API returns:

```json
{
  "id": 41,
  "status": "PAID",
  "lines": [
    {"sku": "BOOK", "quantity": 2, "unitPriceVnd": 120000},
    {"sku": "PEN", "quantity": 1, "unitPriceVnd": 20000}
  ],
  "totalVnd": 260000,
  "note": null,
  "tags": ["priority", "gift"]
}
```

Key things worth checking include:

| Contract | Example Assertion | Bug Caught |
|---|---|---|
| HTTP success | `status().isOk()` | Wrong status code |
| JSON response | `content().contentTypeCompatibleWith(APPLICATION_JSON)` | Unintended HTML/text returned |
| Correct order ID | `jsonPath("$.id").value(41)` | Wrong order fetched |
| Correct status | `jsonPath("$.status").value("PAID")` | Wrong state mapping |
| Has list | `jsonPath("$.lines").isArray()` | Shape changed to object/null |
| Expected item count | `jsonPath("$.lines.length()").value(2)` | Missing or extra line items |
| Correct nested data | `jsonPath("$.lines[0].sku").value("BOOK")` | Wrong SKU mapping |
| Correct total | `jsonPath("$.totalVnd").value(260000)` | Calculation or mapping bug |
| Note present as null | `hasJsonPath()` combined with `doesNotExist()` on `$.note` | Confusing an absent field with an explicit null field |
| No internal field leaked | `jsonPath("$.internalTrace").doesNotHaveJsonPath()` | Accidentally serializing internal details |

**Do not assert everything merely because the JSON has many fields.** Identify which fields belong to the contract: IDs, totals, statuses, and absence of sensitive data are usually critical; purely display fields can be verified in dedicated tests.

A good test should answer: "If the API breaks in a way we care about, which assertion will turn red?"

## 2. Where Does MockMvc Sit in the Spring MVC Pipeline?

`MockMvc` lets you send requests and inspect responses across MVC components such as mappings, argument binding, converters, validation, controller advice, and filters registered in the test context—without opening a real HTTP socket.

```text
JUnit 5 @Test
    |
    v
MockMvc.perform(GET /api/orders/41)
    |
    v
Spring MVC infrastructure
    +--> HandlerMapping
    +--> argument binding / conversion
    +--> Controller
    +--> HttpMessageConverter (Jackson JSON)
    +--> ControllerAdvice / exception handler on error
    |
    v
MockHttpServletResponse
    |
    +--> status()
    +--> header() / contentType()
    +--> jsonPath() / content().json()
    +--> MvcResult / ObjectMapper if deeper inspection is needed
```

In `@WebMvcTest(OrderController.class)`, the real controller executes, while external business dependencies can be replaced with `@MockitoBean`. Such a test protects the **MVC contract and serialization**; it **does not by itself prove the business logic of the mocked service**. Keep separate domain/service tests to protect pricing or real state transitions.

Two common setups:

```java
@WebMvcTest(OrderController.class)
class OrderControllerJsonTest {
    // Loads only the MVC slice needed for the controller.
}
```

```java
@SpringBootTest
@AutoConfigureMockMvc
class OrderApiIntegrationTest {
    // Loads the broad Boot context, also providing MockMvc.
}
```

These two snippets illustrate annotations only, not standalone runnable files. `@WebMvcTest` fits when checking API contracts/controllers with lightweight tests. `@SpringBootTest + @AutoConfigureMockMvc` fits when coordinating multiple real beans. Neither **opens an embedded web server by default**; if testing over a real TCP port, use the appropriate web environment and HTTP client.

## 3. Basic JSONPath Syntax

JSONPath uses a path-like notation into a JSON document:

- `$`: root of the document.
- `.field`: field name inside an object.
- `['field-with-dash']`: bracket notation for fields with special characters.
- `[0]`: first element of an array; 0-based indexing.
- `[*]`: all elements of an array.
- `..field`: recursive descent for fields of that name; use cautiously.
- `[?(@.quantity >= 2)]`: filters elements matching a predicate on the current object.
- `length()`: length function supported by the JSONPath library used by MockMvc.

Given the JSON in Section 1:

| JSONPath | Expected Result |
|---|---|
| `$.id` | `41` |
| `$.status` | `"PAID"` |
| `$.lines` | Array of 2 objects |
| `$.lines[0].sku` | `"BOOK"` |
| `$.lines[1].quantity` | `1` |
| `$.lines[*].sku` | List `["BOOK","PEN"]` |
| `$.lines.length()` | `2` |
| `$.lines[?(@.quantity >= 2)]` | Array of 1 object (BOOK) |
| `$.note` | JSON `null` |
| `$.tags[0]` | `"priority"` |

Example in `MockMvc`:

```java
mvc.perform(get("/api/orders/{id}", 41L))
        .andExpectAll(
                status().isOk(),
                jsonPath("$.id").value(41),
                jsonPath("$.status").value("PAID"),
                jsonPath("$.lines[0].sku").value("BOOK"),
                jsonPath("$.lines.length()").value(2));
```

This is a **code snippet placed inside a `@Test` method**, requiring a mocked response, imports, and an `mvc` field. Section 10 provides the complete runnable file set.

### 3.1. JSONPath Is Not Java Syntax

`"$.lines[0].sku"` is **an expression string** parsed by the JSONPath library at runtime. The Java compiler does not know whether `lines` exists. A typo like `"$.line[0].sku"` typically causes the assertion to fail at runtime when the parser finds no matching path.

### 3.2. Root JSON Array vs. Root JSON Object

If an endpoint returns an array at the root:

```json
[
  {"id": 41},
  {"id": 42}
]
```

then use `$[0].id`, `$[1].id`, or `$[*].id`. If the response is an object with an `items` field:

```json
{
  "items": [{"id": 41}, {"id": 42}],
  "total": 2
}
```

then use `$.items[0].id` and `$.total`. Choose paths according to the **actual contract shape**, not guesses from controller method names.

## 4. JSONPath Matchers in Spring MVC Test

Spring provides `MockMvcResultMatchers.jsonPath(String, ...)` and `JsonPathResultMatchers`. The most useful methods include:

| Matcher | Meaning | Example |
|---|---|---|
| `value(expected)` | Equals the specified value | `jsonPath("$.id").value(41)` |
| `value(hamcrestMatcher)` | Satisfies a Hamcrest matcher | `jsonPath("$.tags", hasSize(2))` |
| `exists()` | Path has a **non-null** value; empty arrays/maps still count as existing for definite paths | `jsonPath("$.status").exists()` |
| `doesNotExist()` | No non-null value at path; missing path or explicit `null` (for definite paths) both match | `jsonPath("$.note").doesNotExist()` |
| `hasJsonPath()` | Path **is present**, even if its value is `null` | `jsonPath("$.note").hasJsonPath()` |
| `doesNotHaveJsonPath()` | Path is **completely absent**, even `null` fails | `jsonPath("$.debug").doesNotHaveJsonPath()` |
| `isArray()` | Value is a JSON array | `jsonPath("$.lines").isArray()` |
| `isMap()` | Value is a JSON object/map | `jsonPath("$").isMap()` |
| `isString()` | Value is a string | `jsonPath("$.status").isString()` |
| `isNumber()` | Value is a number | `jsonPath("$.totalVnd").isNumber()` |
| `isBoolean()` | Value is a boolean | `jsonPath("$.paid").isBoolean()` |
| `isEmpty()` / `isNotEmpty()` | Per Spring's emptiness rules for the resolved value | Use for collections or strings when contracted |

**A critical distinction:**

```json
{
  "note": null
}
```

and:

```json
{}
```

do not have the same JSON shape. For the first object:

```java
jsonPath("$.note").hasJsonPath();     // PASS: field exists, though null
jsonPath("$.note").doesNotExist();    // PASS: no non-null value
jsonPath("$.note").exists();          // FAIL: value is null
jsonPath("$.note").doesNotHaveJsonPath(); // FAIL: field is actually present
```

This is an **illustrative behavior reference**, not standalone `ResultMatcher` statements executed on their own. For the empty object, `doesNotHaveJsonPath()` matches because `note` does not appear at all.

If the requirement is **field must exist and be null**, check both `hasJsonPath()` and `doesNotExist()`, or use Jackson `JsonNode` to check `has("note")` + `get("note").isNull()`. `doesNotExist()` alone **cannot** distinguish absent from explicit null.

## 5. JSON Null, Empty String, Empty Array, and Missing Field

The following four cases carry different meanings:

```json
{
  "note": null,
  "nickname": "",
  "tags": [],
  "items": [{}]
}
```

| Value | Meaning | Recommended Assertion |
|---|---|---|
| `note: null` | Field exists in document without a value | `hasJsonPath()` + `doesNotExist()` or Jackson `isNull()` |
| `nickname: ""` | Field contains an empty string | `jsonPath("$.nickname").value("")` |
| `tags: []` | Field contains an empty array | `jsonPath("$.tags").isArray()` and `hasSize(0)` |
| `items: [{}]` | Array contains 1 empty object | `jsonPath("$.items", hasSize(1))`; check object if contracted |
| `debug` missing | Field is absent from payload | `jsonPath("$.debug").doesNotHaveJsonPath()` |

`isEmpty()` can be handy when you just want to know something is empty, but avoid using it across multiple empty forms when the API distinguishes `null`, `""`, and `[]`. Assert the **exact data type and shape** of the contract.

One Jackson note: if a DTO configures `@JsonInclude(Include.NON_NULL)`, null fields may be **omitted entirely** from the payload. Any test demanding `hasJsonPath()` will turn red. This could be a **valid contract change or a bug**, depending on the API; do not adjust the assertion to green before confirming the requirement.

## 6. Checking Collections and Array Order with Hamcrest

When JSONPath extracts an array or list of results, you can combine it with Hamcrest:

```java
import static org.hamcrest.Matchers.contains;
import static org.hamcrest.Matchers.containsInAnyOrder;
import static org.hamcrest.Matchers.hasItem;
import static org.hamcrest.Matchers.hasSize;
```

With `"tags": ["priority", "gift"]`:

```java
jsonPath("$.tags", hasSize(2));
jsonPath("$.tags", contains("priority", "gift"));
jsonPath("$.tags", containsInAnyOrder("gift", "priority"));
jsonPath("$.tags", hasItem("gift"));
```

These lines are **`ResultMatcher` patterns used inside `andExpect(...)` or `andExpectAll(...)`**, not standalone JUnit statements.

Differences among these matchers:

- **`contains("priority","gift")`** requires exactly those two elements **in that exact order**.
- **`containsInAnyOrder("gift","priority")`** requires the exact same elements regardless of order.
- **`hasItem("gift")`** requires only that at least one element matches; other elements may exist.
- **`hasSize(2)`** checks the count, but does not verify the elements' contents.

**Guideline for choosing assertions:** if the API specifies "newest first" or `sort=createdAt,desc`, order is part of the contract and `contains`/index assertions are appropriate. If the API returns a collection whose order is unspecified, `containsInAnyOrder` is better. **Never rely on accidental database ordering**; if ordering is required, the query/service must define an explicit `ORDER BY` or comparator.

For arrays of objects, you can project stable fields:

```java
jsonPath("$.lines[*].sku", contains("BOOK", "PEN"));
jsonPath("$.lines[*].quantity", contains(2, 1));
```

If you need to prove that a SKU and quantity belong to **the same element**, check `$.lines[0].sku` alongside `$.lines[0].quantity` or use predicate/object comparisons. Checking two separate projected lists alone may miss swapped pairs.

## 7. JSONPath with Filters, Wildcards, and Nested Data

JSONPath allows filtering object arrays by condition:

```json
{
  "items": [
    {"id": 41, "totalVnd": 260000, "status": "PAID"},
    {"id": 42, "totalVnd": 20000, "status": "PAID"},
    {"id": 43, "totalVnd": 500000, "status": "NEW"}
  ]
}
```

Example queries:

```text
$.items[*].id                       -> [41, 42, 43]
$.items[?(@.totalVnd > 200000)]     -> [object 41, object 43]
$.items[?(@.status == 'PAID')].id    -> [41, 42]
$..status                           -> all nested status fields in document
```

Checking the number of matching items:

```java
jsonPath("$.items[?(@.totalVnd > 200000)]", hasSize(2));
```

**This is a snippet**, requiring a test context and static import `hasSize`.

Prefer **explicit** JSONPath expressions. Recursive `$..status` is handy during investigation, yet adding another nested object that also happens to have a `status` field can break tests or mask mismatches. For stable API contracts, `$.items[*].status` is usually clearer.

Likewise, filtering `?(@.totalVnd > 200000)` is useful when checking a subset, whereas if the requirement states "the first item must be order 41", direct indexing is the right assertion.

## 8. `content().json(...)`: Structural Whole-JSON Comparison

JSON is a structured data format; two responses can be equivalent despite differences in whitespace and key ordering:

```json
{"id":41,"status":"PAID"}
```

and:

```json
{
  "status": "PAID",
  "id": 41
}
```

Exact byte/string comparison via `content().string(...)` treats them as different. When the contract only requires equivalent JSON values, use **`content().json(...)`** instead of comparing formatting.

Spring Framework 6.2 provides overloads:

```java
content().json(expectedJson, JsonCompareMode.STRICT);
content().json(expectedJson, JsonCompareMode.LENIENT);
```

Import:

```java
import org.springframework.test.json.JsonCompareMode;
```

**Semantics:**

| Mode | Allows Extra Fields Beyond Expected? | JSON Array Ordering | When to Use |
|---|---|---|---|
| `STRICT` | Forbids extra fields beyond expected under strict comparison | Enforces order | Response schema must be exact; prevent leaked fields or shape drift |
| `LENIENT` | Allows extra fields | Does not require identical array order per mode | Only a subset matters and the contract permits extra fields |

In both modes, **object key order is not array order** and is normally ignored. `STRICT` does not mean byte-for-byte comparison.

Example:

```java
mvc.perform(get("/api/orders/{id}", 41L))
        .andExpect(status().isOk())
        .andExpect(content().json("""
                {
                  "id": 41,
                  "status": "PAID",
                  "lines": [],
                  "totalVnd": 0,
                  "note": null,
                  "tags": []
                }
                """, JsonCompareMode.STRICT));
```

This is an illustrative snippet; for it to pass, the endpoint must return JSON with those **exact** fields and values. The runnable test uses a different payload in Sections 10–11.

### 8.1. Why Not Default to LENIENT Everywhere?

If an API accidentally emits `passwordHash` or `internalTrace`, a `LENIENT` test checking only a few expected fields will **still pass**. Whenever the list of returned fields is an important security or quality contract, use `STRICT` or explicitly assert the absence of sensitive fields.

Conversely, if the API allows adding metadata and a test only cares about two core fields, `LENIENT` or targeted JSONPath assertions are less brittle. **The mode is a contract decision**, not "STRICT is always better."

### 8.2. JSONAssert and Dependencies

`content().json(...)` in Spring Framework 6.2 integrates JSON comparison; the common overload requires the **JSONassert** library on the test classpath. With Spring Boot 3.5 and `spring-boot-starter-test`, the test dependency set normally includes it. If a test fails due to a missing JSONassert class, inspect your dependency graph rather than writing a custom string comparator.

## 9. What Actually Runs in the Example

The main example protects **HTTP mapping, serialization, and JSON responses**:

- Endpoint `GET /api/orders/{id}`: returns an order or 404.
- Endpoint `GET /api/orders`: accepts `status`, `page`, `size`, wrapping the list in an object with pagination metadata.
- When `page` or `size` is invalid, returns HTTP 400 with a defined JSON error.
- DTOs use Java records; Spring Boot's Jackson serializes them to JSON.
- `OrderLookup` is the business interface, **mocked at the MVC slice boundary**. This lesson does not claim that database lookup logic or total calculation inside a service was tested.
- Unit/service tests and repository integration tests must still exist separately in a real application.

**Example note:** monetary amounts use integer VND so they do not depend on binary floating-point representation. Mocked SKUs/prices merely illustrate the JSON contract; data is controlled by test stubs.

## 10. Runnable Project: Java 17+, Spring Boot 3.5.x

### 10.1. File Layout

```text
src/main/java/com/example/orderapi/
    OrderApiApplication.java
    OrderLineView.java
    OrderView.java
    OrderPage.java
    ApiError.java
    OrderLookup.java
    OrderController.java

src/test/java/com/example/orderapi/
    OrderControllerJsonTest.java
```

Use package `com.example.orderapi` in every file. The files below **compile in a Gradle/Maven Spring Boot 3.5 project with the web and test starters**.

### 10.2. Spring Boot Application Root

**`src/main/java/com/example/orderapi/OrderApiApplication.java`**

```java
package com.example.orderapi;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApiApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApiApplication.class, args);
    }
}
```

Place the application class in the root package so Boot discovers it from the test package. `@WebMvcTest` uses an MVC slice and does not automatically instantiate all application services or repositories.

### 10.3. DTOs for Line Items, Orders, Result Pages, and Errors

**`src/main/java/com/example/orderapi/OrderLineView.java`**

```java
package com.example.orderapi;

public record OrderLineView(
        String sku,
        int quantity,
        long unitPriceVnd) {
}
```

**`src/main/java/com/example/orderapi/OrderView.java`**

```java
package com.example.orderapi;

import java.util.List;

public record OrderView(
        long id,
        String status,
        List<OrderLineView> lines,
        long totalVnd,
        String note,
        List<String> tags) {
}
```

**`src/main/java/com/example/orderapi/OrderPage.java`**

```java
package com.example.orderapi;

import java.util.List;

public record OrderPage(
        List<OrderView> items,
        int total,
        int page,
        int size) {
}
```

**`src/main/java/com/example/orderapi/ApiError.java`**

```java
package com.example.orderapi;

public record ApiError(
        String code,
        String message) {
}
```

Records provide accessors `id()`, `status()`, etc., plus `equals` and `hashCode` based on components. Jackson in Spring Boot 3.5 with `starter-web` serializes records into JSON objects using the component names.

**Intentional boundary:** the DTOs do not add Jackson naming strategies, `@JsonInclude`, or custom serializers, so serialization follows the example's default configuration. If your project changes the global `ObjectMapper`, actual output may differ; tests should reflect your project's contract, not only this sample.

### 10.4. Service Port as Controller Collaborator

**`src/main/java/com/example/orderapi/OrderLookup.java`**

```java
package com.example.orderapi;

import java.util.List;
import java.util.Optional;

public interface OrderLookup {
    Optional<OrderView> findById(long id);
    List<OrderView> findByStatus(String status);
}
```

There is no production implementation in the example because the focus is the MVC slice. `@MockitoBean` in the test provides a mock bean so the controller can be instantiated. In a real application, a real `OrderLookup` implementation is required and verified via separate unit/integration tests.

### 10.5. Real Controller: HTTP 200, 404, Pagination, and 400 Error

**`src/main/java/com/example/orderapi/OrderController.java`**

```java
package com.example.orderapi;

import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderLookup lookup;

    public OrderController(OrderLookup lookup) {
        this.lookup = lookup;
    }

    @GetMapping("/{id}")
    public ResponseEntity<OrderView> findOne(@PathVariable long id) {
        return lookup.findById(id)
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @GetMapping
    public OrderPage search(
            @RequestParam(defaultValue = "ALL") String status,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        if (page < 0) {
            throw new IllegalArgumentException("page must be >= 0");
        }
        if (size < 1 || size > 100) {
            throw new IllegalArgumentException(
                    "size must be between 1 and 100");
        }

        List<OrderView> all = lookup.findByStatus(status);
        long offset = (long) page * size;
        int from = (int) Math.min(offset, all.size());
        int to = (int) Math.min((long) from + size, all.size());

        return new OrderPage(
                all.subList(from, to), all.size(), page, size);
    }

    @ExceptionHandler(IllegalArgumentException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public ApiError invalidArgument(IllegalArgumentException cause) {
        return new ApiError("INVALID_REQUEST", cause.getMessage());
    }
}
```

The controller performs **simple pagination over the list returned by the collaborator**. In a real system with large datasets, paginate at the repository/query layer with deterministic ordering rather than loading the entire DB and calling `subList`. The goal here is generating a JSON response with nested arrays and metadata to test.

The `invalidArgument` handler illustrates JSON error formatting for an exception explicitly thrown in code. It **does not replace the entire validation framework** and does not guarantee that all deserialization/`@Valid` errors share the same shape. In production APIs, unify the error contract via `@ControllerAdvice` or `ProblemDetail` where appropriate.

## 11. Complete Test Suite Using `@WebMvcTest`

**`src/test/java/com/example/orderapi/OrderControllerJsonTest.java`**

```java
package com.example.orderapi;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.json.JsonCompareMode;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.contains;
import static org.hamcrest.Matchers.containsInAnyOrder;
import static org.hamcrest.Matchers.hasSize;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderController.class)
class OrderControllerJsonTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @MockitoBean
    OrderLookup lookup;

    private static OrderView firstOrder() {
        return new OrderView(
                41L, "PAID",
                List.of(
                        new OrderLineView("BOOK", 2, 120_000L),
                        new OrderLineView("PEN", 1, 20_000L)),
                260_000L,
                null,
                List.of("priority", "gift"));
    }

    private static OrderView secondOrder() {
        return new OrderView(
                42L, "PAID",
                List.of(new OrderLineView("PEN", 1, 20_000L)),
                20_000L,
                "Ready",
                List.of());
    }

    @Test
    void checksFieldsArraysAndNullUsingJsonPath() throws Exception {
        when(lookup.findById(41L))
                .thenReturn(Optional.of(firstOrder()));

        mvc.perform(get("/api/orders/{id}", 41L)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpectAll(
                        status().isOk(),
                        content().contentTypeCompatibleWith(
                                MediaType.APPLICATION_JSON),
                        jsonPath("$.id").isNumber(),
                        jsonPath("$.id").value(41),
                        jsonPath("$.status").isString(),
                        jsonPath("$.status").value("PAID"),
                        jsonPath("$.lines").isArray(),
                        jsonPath("$.lines.length()").value(2),
                        jsonPath("$.lines[0].sku").value("BOOK"),
                        jsonPath("$.lines[1].quantity").value(1),
                        jsonPath("$.lines[*].sku",
                                contains("BOOK", "PEN")),
                        jsonPath("$.totalVnd").value(260_000),
                        jsonPath("$.note").hasJsonPath(),
                        jsonPath("$.note").doesNotExist(),
                        jsonPath("$.tags",
                                contains("priority", "gift")),
                        jsonPath("$.internalTrace")
                                .doesNotHaveJsonPath());

        verify(lookup).findById(41L);
    }

    @Test
    void comparesWholeResponseStrictly() throws Exception {
        when(lookup.findById(41L))
                .thenReturn(Optional.of(firstOrder()));

        mvc.perform(get("/api/orders/41"))
                .andExpect(status().isOk())
                .andExpect(content().json("""
                        {
                          "id": 41,
                          "status": "PAID",
                          "lines": [
                            {
                              "sku": "BOOK",
                              "quantity": 2,
                              "unitPriceVnd": 120000
                            },
                            {
                              "sku": "PEN",
                              "quantity": 1,
                              "unitPriceVnd": 20000
                            }
                          ],
                          "totalVnd": 260000,
                          "note": null,
                          "tags": ["priority", "gift"]
                        }
                        """, JsonCompareMode.STRICT));
    }

    @Test
    void checksPaginatedArrayAndFilter() throws Exception {
        when(lookup.findByStatus("PAID"))
                .thenReturn(List.of(firstOrder(), secondOrder()));

        mvc.perform(get("/api/orders")
                        .param("status", "PAID")
                        .param("page", "0")
                        .param("size", "20"))
                .andExpectAll(
                        status().isOk(),
                        jsonPath("$").isMap(),
                        jsonPath("$.items").isArray(),
                        jsonPath("$.items", hasSize(2)),
                        jsonPath("$.items[*].id",
                                containsInAnyOrder(41, 42)),
                        jsonPath("$.items[0].lines[0].sku")
                                .value("BOOK"),
                        jsonPath("$.items[?(@.totalVnd > 200000)]",
                                hasSize(1)),
                        jsonPath("$.total").value(2),
                        jsonPath("$.page").value(0),
                        jsonPath("$.size").value(20));

        verify(lookup).findByStatus("PAID");
    }

    @Test
    void missingOrderHas404AndNoJsonBody() throws Exception {
        when(lookup.findById(404L))
                .thenReturn(Optional.empty());

        mvc.perform(get("/api/orders/{id}", 404L))
                .andExpectAll(
                        status().isNotFound(),
                        content().string(""));

        verify(lookup).findById(404L);
    }

    @Test
    void invalidPageReturnsControlledJsonError() throws Exception {
        mvc.perform(get("/api/orders")
                        .param("page", "-1"))
                .andExpectAll(
                        status().isBadRequest(),
                        content().contentTypeCompatibleWith(
                                MediaType.APPLICATION_JSON),
                        jsonPath("$.code")
                                .value("INVALID_REQUEST"),
                        jsonPath("$.message")
                                .value("page must be >= 0"),
                        jsonPath("$.stackTrace")
                                .doesNotHaveJsonPath());

        verifyNoInteractions(lookup);
    }

    @Test
    void distinguishesExplicitNullFromMissingField()
            throws Exception {
        when(lookup.findById(41L))
                .thenReturn(Optional.of(firstOrder()));

        MvcResult result =
                mvc.perform(get("/api/orders/{id}", 41L))
                        .andExpect(status().isOk())
                        .andReturn();

        JsonNode root = mapper.readTree(
                result.getResponse().getContentAsByteArray());

        assertTrue(root.has("note"));
        assertTrue(root.get("note").isNull());
        assertFalse(root.has("internalTrace"));
    }

    @Test
    void preservesUnicodeQuotesAndNewlines() throws Exception {
        String note = "Dòng 1: \"Mai\"\nDòng 2";
        OrderView view = new OrderView(
                43L, "NEW", List.of(), 0L,
                note, List.of());

        when(lookup.findById(43L))
                .thenReturn(Optional.of(view));

        mvc.perform(get("/api/orders/{id}", 43L))
                .andExpectAll(
                        status().isOk(),
                        jsonPath("$.id").value(43),
                        jsonPath("$.note").value(note));
    }
}
```

### 11.1. Interpreting Each Assertion Correctly

There are **7 test methods**, each protecting a distinct contract:

1. `checksFieldsArraysAndNullUsingJsonPath`: JSONPath for primitives, nested arrays, null `note`, and ensuring sensitive fields are absent.
2. `comparesWholeResponseStrictly`: the entire JSON object must match, including two line items in order and no unexpected fields.
3. `checksPaginatedArrayAndFilter`: root object contains an `items` array, both orders, and a JSONPath filter matching the one order above 200,000.
4. `missingOrderHas404AndNoJsonBody`: HTTP 404 with an empty body. **Do not parse JSON on an empty body.**
5. `invalidPageReturnsControlledJsonError`: HTTP 400 with a handler-controlled error payload, no stack trace leaked, and `lookup` never called.
6. `distinguishesExplicitNullFromMissingField`: Jackson `JsonNode` confirms `note` is present with value null, while `internalTrace` is absent.
7. `preservesUnicodeQuotesAndNewlines`: JSON serialization escapes properly and parsing back yields the **exact original Unicode string**.

Each test has its own stubs and does not depend on execution order. `@MockitoBean` provides a Spring mock bean for `OrderLookup` in the MVC slice. The controller runs for real; real service query logic is not verified in this suite.

### 11.2. Why Compare Using `JsonNode` in the Sixth Test?

`JsonNode.has("note")` returns true even when `note` is null, `get("note").isNull()` distinguishes explicit JSON null, and `has("internalTrace")` checks field presence. This is a clear option when verifying **subtle shape details** where JSONPath alone is easy to misread.

We use `getContentAsByteArray()` to feed raw JSON bytes into Jackson, avoiding charset conversion quirks from reading the body as a string.

### 11.3. Why `@WebMvcTest` Instead of `@SpringBootTest`?

The goal is HTTP response mapping and Jackson serialization. An MVC slice loads just that infrastructure and is normally lighter than a full Boot context. When requirements shift to testing transactions, JPA queries, real authorization, or multi-bean business flows, choose the appropriate test level and mock only at the right boundaries.

## 12. Pagination: Check More Than `items.length()`

A paginated API typically has at least three contract layers:

1. **Data** inside `items` has the right elements and fields.
2. **Metadata** such as `page`, `size`, `total`, or `totalElements` is accurate.
3. **Ordering and limits** are enforced per `sort` and `size`.

Example:

```json
{
  "items": [{"id": 41}, {"id": 42}],
  "total": 7,
  "page": 0,
  "size": 2
}
```

Assertions:

```java
jsonPath("$.items", hasSize(2));
jsonPath("$.total").value(7);
jsonPath("$.page").value(0);
jsonPath("$.size").value(2);
jsonPath("$.items[*].id", contains(41, 42));
```

This is a **snippet**. It does not by itself prove there are 7 records in the DB; if metadata comes from a mock service, the test protects only serialization. To verify real pagination logic, run the service/repository against fixture data and assert page boundaries, ordering, and queries.

Some applications expose Spring Data's `Page<T>`, which can produce a rich JSON structure that varies across versions. **Do not assume a public API must expose Spring Data's internal shape.** A stable response DTO simplifies testing and avoids coupling clients to implementation details.

## 13. JSONPath and Numeric Types: Integer, Long, Double, BigDecimal

JSON has a single syntactic "number" type, yet libraries parsing JSON into Java may produce `Integer`, `Long`, `Double`, `BigDecimal`, or another numeric type depending on value and configuration.

Example JSON:

```json
{
  "count": 2,
  "totalVnd": 260000,
  "rate": 0.075,
  "largeId": 9007199254740993
}
```

Things to watch out for:

- `jsonPath("$.count").value(2)` is clear and reliable for small integers.
- `jsonPath("$.totalVnd").isNumber()` verifies numeric type; `value(260000)` verifies the exact value in this example.
- For decimals, `value(0.075)` can encounter rounding or Java type mismatches in complex comparisons; use tolerance matchers, target-type coercion, or Jackson/`BigDecimal` parsing per contract.
- For very large integers exceeding JavaScript's exact safe integer range in clients, consider representing them as strings in the API. **Do not guess JSON numeric types intuitively from the Java record.**
- Monetary values should specify currency, minor unit, and rounding contracts. In our example, `long totalVnd` is **integer VND**, not floating-point.

A matcher for floating-point numbers when appropriate:

```java
// Snippet, requires import static org.hamcrest.Matchers.closeTo;
jsonPath("$.rate").value(closeTo(0.075, 0.000001),
                         Double.class);
```

The `value(Matcher, Class)` overload coerces the result before matching. However, **never use wide tolerances to hide monetary calculation errors**. For money requiring exactness, represent values in integer minor units or use a decimal type with an explicit JSON contract.

## 14. JSON Strings and Escaping: Test Decoded Content

Strings containing double quotes or newlines are escaped in JSON:

```json
{
  "note": "Dòng 1: \"Mai\"\nDòng 2"
}
```

When the controller returns a Java string:

```java
String note = "Dòng 1: \"Mai\"\nDòng 2";
```

the in-memory value holds **literal double quotes** and a **literal newline character**. Jackson encodes it to JSON; JSONPath parses it back to the original Java string.

Therefore:

```java
jsonPath("$.note").value(note);
```

is usually a more meaningful assertion than checking individual backslashes in the serialized output. If the contract specifies exact byte-level encoding/escaping or digital signatures over payloads, write dedicated raw-byte tests rather than relying on semantic JSON comparison.

For Vietnamese characters, emoji, and other Unicode characters, compare values **after JSON parsing** rather than tying tests to whether the serializer emits literal UTF-8 characters or `\\uXXXX` escapes. Both representations encode the exact same JSON data.

## 15. Dates, Times, Timezones, and JSON Formatting

Dates and times are a common source of JSON tests misrepresenting requirements.

Contract example:

```json
{
  "createdAt": "2026-11-08T09:15:00Z"
}
```

If the application uses `Instant`, Jackson with the Java Time module normally serializes it as ISO-8601 per configuration. However, `LocalDateTime` carries no timezone and has different semantics from `Instant`. If a serializer or project configures numeric timestamps, custom patterns, or specific zones, the output will differ.

A JSON assertion could look like:

```java
jsonPath("$.createdAt")
        .value("2026-11-08T09:15:00Z");
```

This is a snippet; for deterministic tests, use a **fixed** time source, such as injecting `Clock.fixed(...)` into the service instead of calling `Instant.now()` at test time. If the API only guarantees a valid ISO instant without fixing a timestamp, parse the value into an `Instant` and assert relevant bounds.

**Do not hardcode the current wall-clock time into expected JSON and live with flaky tests.** Precision, offset, millisecond formatting, and serialization format are part of the API contract.

## 16. JSON Error Payloads: Both Status and Shape Matter

An API might return HTTP 400 without producing the contracted JSON error. Tests should check:

- HTTP status (`400`, `404`, `409`, or `422` per API convention).
- Matching `Content-Type` (standard JSON or `application/problem+json` if using Problem Details).
- Stable error code, public message, and permitted fields.
- No leaked stack traces, internal SQL, tokens, sensitive emails, or server paths.
- For multi-error validation, the error list shape, field names, and ordering (if specified).

Custom error example in the runnable project:

```json
{
  "code": "INVALID_REQUEST",
  "message": "page must be >= 0"
}
```

Assertions:

```java
status().isBadRequest();
jsonPath("$.code").value("INVALID_REQUEST");
jsonPath("$.message").value("page must be >= 0");
jsonPath("$.stackTrace").doesNotHaveJsonPath();
```

These are **matcher snippets** used inside `andExpectAll`. If an application uses Spring `ProblemDetail`, the JSON shape typically includes fields like `type`, `title`, `status`, `detail`, and `instance` depending on configuration; do not assume the custom `ApiError` example fits every project.

**Important:** status/error responses produced by security filters, Jackson parse errors, the validation framework, or controller advice can take different code paths. Testing a single custom handler does not prove every error path is safe; add tests for each real error source in your API.

## 17. Comparing JSONPath, JSONAssert, Jackson, and JsonTester

| Tool | Strengths | Caveats |
|---|---|---|
| `MockMvcResultMatchers.jsonPath` | Fast assertions on fields, nested arrays, and predicates directly on HTTP responses | Expressions are strings, easy to typo; numbers and nulls require care |
| `content().json` | Compares overall JSON structure with strict/lenient modes | Large expected strings hurt readability; wrong mode becomes too strict or too loose |
| Jackson `ObjectMapper.readTree` / `JsonNode` | Checks structure, types, present/null/missing fields; handles complex comparisons | More verbose test code; separate parsing from assertions cleanly |
| Direct JSONassert API | Compares two JSON strings outside MockMvc | Requires extracting body manually in HTTP tests; mind comparison mode |
| `@JsonTest` / `JacksonTester` | Tests DTO serialization/deserialization or custom modules independently of MVC | Does not verify routing, HTTP status, filters, or controllers |
| `WebTestClient` | Tests HTTP responses in reactive APIs or bound to servers/controllers | Different API from MockMvc; choose based on stack/web environment |

You do not need one tool for every assertion. For example:

- `status().isOk()` + `jsonPath("$.id").value(41)`: enough for a small contract.
- `content().json(expected, STRICT)`: fits when both schema and absence of extras matter.
- `JsonNode`: fits when strictly distinguishing null vs. missing or comparing dynamic collections.

## 18. Avoid Testing Output Programmed into Your Own Mock

In an MVC slice, mocking `OrderLookup` is **appropriate** for testing JSON mapping. However, if the goal is testing service pricing calculations, a test like:

```java
OrderLookup lookup = mock(OrderLookup.class);
when(lookup.findById(41L))
        .thenReturn(Optional.of(expectedOrder));
assertEquals(expectedOrder, lookup.findById(41L).orElseThrow());
```

**runs no real business service**. It only proves Mockito returns what you stubbed.

Separate scopes clearly:

1. **Domain/unit tests:** real totals, taxes, discounts, state transitions; use real objects and mock/fake outbound ports where needed.
2. **MVC slice tests:** real controller, real converters, real response JSON; mock service boundary to provide deterministic inputs for serialization.
3. **Integration tests:** multiple real beans, key repositories/transactions/adapters; assert responses and side effects across controlled boundaries.

The second does not replace the first, and the first does not protect the HTTP/JSON schema. A good suite pairs layers by risk rather than forcing one test to do everything.

## 19. Common Mistakes Making JSON Assertions Wrong or Flaky

| Symptom | Common Cause | How to Fix |
|---|---|---|
| `No value at JSON path "$.x"` | Missing field, wrong name, `@JsonIgnore` on DTO, or changed naming strategy | Inspect actual JSON safely; verify contract and serializer |
| `jsonPath("$.note").exists()` fails despite `note` in JSON | `note` is `null`; `exists()` requires non-null | Use `hasJsonPath()` for presence, or assert null explicitly |
| Test passes even when sensitive fields leak | `LENIENT` mode checking only core fields | Add `doesNotHaveJsonPath` or use `STRICT` when extras are forbidden |
| JSON string match fails on whitespace | Using `content().string(...)` on JSON objects | Use `content().json(...)` or JSONPath |
| Flaky array tests | Nondeterministic DB/HashMap ordering | Use `containsInAnyOrder` when order is uncontracted, or enforce `ORDER BY` |
| Decimal comparison failures | Java numeric type differences, rounding, or floating-point precision | Pick explicit numeric representation and matchers; avoid arbitrary tolerances |
| Path parser error | Invalid JSONPath syntax or non-JSON body | Check status, content type, body, and expression |
| JSONPath fails on HTTP 404 | Empty body or non-JSON response | Assert `status` + `content().string("")` when empty body is contracted |
| `@Autowired MockMvc` is null | Missing Spring MVC TestContext or `@AutoConfigureMockMvc` | Use `@WebMvcTest` or `@SpringBootTest + @AutoConfigureMockMvc` |
| Context missing service bean | Slice does not scan business services | Provide `@MockitoBean` or `@Import` collaborators within scope |
| Passes alone, fails in suite | Global state, shared mock/fake, profile, or DB fixture pollution | Keep fixtures/tests isolated and order-independent |
| Unexpected error response shape | Default error handling vs. `@ControllerAdvice` vs. Spring Security | Protect contracts along actual error paths for your config/version |
| Date/time fails across timezones | Reliance on system clock/default zone | Inject fixed clock, use explicit `Instant`/zone, assert format contract |
| Test misses deleted fields | `hasItem` or `LENIENT` too permissive | Pick matchers tight enough for the requirements |
| Test breaks after harmless field addition | `STRICT` locking schema when API permits extensions | Use `LENIENT`/JSONPath when additions are allowed |

**A maintainable test should fail because of a contract break, not because of how a JSON printer indents text.** At the same time, do not make it so lenient that security or critical serialization bugs slip through.

## 20. Risk-Based Assertion Strategy

A simple rule of thumb:

- **Critical fields** (IDs, monetary amounts, statuses, permissions, customer-owned data): assert exact values and verify no uncontracted fields leak.
- **Collections**: assert size, element identities, and order **if order is contracted**.
- **Optional fields**: explicitly decide absent, null, empty, or populated; avoid ambiguous matchers.
- **Error payloads**: assert status, public code, message, or reason; hide internal details.
- **Metadata** (page, total, next cursor): assert real boundary cases, not just one happy path.
- **Dates/times**: pin clocks, zones, and serialization expectations.
- **Evolving/extensible fields**: prefer semantic assertions over strict full-JSON snapshots if the API permits growth.

**Tip when adding a new test:** write out the expected JSON response first, underline the 3–7 most critical contracts, and pick matchers that catch real regressions. You do not need to turn every response into a 100-line snapshot that breaks on every harmless change.

## 21. Practice Exercises

### Exercise A — Finding the Right Path

Given JSON:

```json
{
  "customer": {
    "id": 9,
    "name": "Mai"
  },
  "orders": [
    {"id": 41, "totalVnd": 260000},
    {"id": 42, "totalVnd": 20000}
  ]
}
```

Write JSONPath expressions checking that the customer's name is `Mai`, the second order's ID is 42, the `orders` array has two elements, and one order exceeds 200,000 VND.

**Suggested solution:** `$.customer.name`, `$.orders[1].id`, `$.orders.length()`, and `$.orders[?(@.totalVnd > 200000)]` combined with `hasSize(1)`.

### Exercise B — Null or Missing?

Compare:

```json
{"note": null}
```

and:

```json
{}
```

Is `doesNotExist()` enough to distinguish these two documents? Write two assertions proving `note` exists as null, and one assertion proving `note` is completely absent.

**Answer:** For a definite JSONPath, `doesNotExist()` is not enough; combine `hasJsonPath()` with `doesNotExist()` for explicit null, and use `doesNotHaveJsonPath()` for absent.

### Exercise C — Accepting an Unordered Array

A search API returns `["BOOK", "PEN"]` or `["PEN","BOOK"]` and the contract does not specify ordering. Should you use `contains` or `containsInAnyOrder`? Why is `hasSize(2)` alone insufficient?

**Answer:** Use `containsInAnyOrder("BOOK","PEN")`; checking size alone does not guarantee the list holds those exact two SKUs.

### Exercise D — Catching Data Leaks

An API previously returned:

```json
{"id": 41, "status": "PAID"}
```

After refactoring, it returns:

```json
{"id": 41, "status": "PAID", "passwordHash": "internal"}
```

Would `content().json(expected, JsonCompareMode.LENIENT)` with the old expected payload fail? Write an assertion protecting against adding a `passwordHash` field.

**Answer:** `LENIENT` permits extra fields, so the test would stay green. Use `jsonPath("$.passwordHash").doesNotHaveJsonPath()` or `STRICT` JSON comparison when extra fields are forbidden.

### Exercise E — Checking HTTP Status on Not Found

`GET /api/orders/404` returns 404 with an **empty body**. Write the proper assertion and explain why you should not use `jsonPath("$.message")` on this response.

**Answer:** `status().isNotFound()` paired with `content().string("")`. An empty body is not a JSON object, so JSONPath does not apply.

### Exercise F — Checking Pagination

An API has 15 orders, `size=5`, `page=1`. Under zero-based pagination, which items are expected? What metadata must be checked? In Section 10's controller example, with 15 orders, page 1 size 5 slices `subList(5,10)`. Assert `page`, `size`, `total`, the list of 5 IDs, and ordering if a `sort` is contracted.

### Exercise G — Dynamic Timestamps

A test asserts `createdAt` against `Instant.now()` captured right before the HTTP request. Why can this test be flaky? Fix it by injecting a fixed clock or building fixtures with a fixed instant, and assert the properly formatted timestamp string.

### Exercise H — Scope of Service vs. Controller Tests

If a controller test using `@MockitoBean OrderLookup` returns `totalVnd=260000` and JSONPath passes, can you conclude the real service calculates totals accurately? No. Write domain/service tests with real calculations and fake/mocked outbound dependencies, and keep the MVC slice to protect serialization.

## 22. Checklist Before Finalizing JSON Tests

- [ ] I know the endpoint's exact API contract: status, content type, JSON root, and key fields.
- [ ] I chose the right test level: MVC slice, Spring Boot integration, or serialization-only test.
- [ ] `@MockitoBean` replaces only out-of-scope collaborators, never the code under test.
- [ ] JSONPath starts from the right `$` root and knows whether the root is an object or array.
- [ ] Nested fields, array indices, wildcards, and predicates match the real response shape.
- [ ] For null/missing/empty, I understand the differences among `hasJsonPath`, `exists`, `doesNotExist`, and `doesNotHaveJsonPath`.
- [ ] I do not substitute `isEmpty` for shape-specific checks when the contract distinguishes null, empty string, and empty array.
- [ ] For collections, I check both contents and size; ordering is enforced only when specified by the API.
- [ ] I intentionally selected `STRICT` or `LENIENT` rather than picking one out of habit.
- [ ] I do not compare JSON strings byte-for-byte when only semantic JSON equality is required.
- [ ] Monetary values, timestamps, and Unicode have clear representations and assertions.
- [ ] 400/404/409 errors have the right response shape; I never run JSON parsing on empty bodies.
- [ ] I verified no uncontracted sensitive fields are exposed.
- [ ] Fixtures do not rely on wall-clock time, randomness, network, or execution order of other tests.
- [ ] When a test fails, I can tell apart data mapping, serialization, status, config, and business logic bugs.
- [ ] I know MVC tests do not replace service/repository/transaction tests.

**Conclusion:** `jsonPath(...)` works well for asserting critical values and structures in HTTP responses; `content().json(...)` fits full-structure comparisons; Jackson `JsonNode` handles subtle cases like null vs. missing. Pick matchers based on the **API contract**, not merely the shortest syntax. Reliable JSON tests catch wrong data, broken shapes, and field leaks while avoiding brittle dependencies on whitespace, uncontracted ordering, or out-of-scope mock outputs.

## 23. Gradle Configuration, Running Tests, and Expected Results

In a Gradle project that already declares the Spring Boot plugin/BOM and repositories, the dependencies needed for the example code are:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is an **additional configuration snippet**, not a standalone `build.gradle` since plugins and versions are omitted. Spring Boot 3.5's `starter-test` brings Spring MVC test support, Mockito, JUnit Jupiter, and Hamcrest/JSONassert under Boot's dependency management. If your project customizes dependencies, check the actual dependency graph.

Run from the project directory containing the Gradle wrapper:

```bash
./gradlew test --tests com.example.orderapi.OrderControllerJsonTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests com.example.orderapi.OrderControllerJsonTest
```

In multi-module projects, invoke the test task on the module containing the test rather than guessing a module name. Snippets outside Section 10's file tree are illustrative only, not standalone compilable files.

**Expected result per the example code:** 7 test methods run by JUnit Jupiter; JSON responses across scenarios verify IDs 41/42/43, empty 404 body, 400 JSON error, and exact Unicode note content. When project/dependencies and code are configured correctly, Gradle reports `BUILD SUCCESSFUL`. This is an **expectation derived from inspecting the code and contract**, not a claim of having executed tests in a specific workspace; there is no fixed business stdout from the suite.

Gradle reports typically appear at `build/reports/tests/test/index.html` and result XMLs under `build/test-results/test/` of the module.

### Official References

- Spring Framework — MockMvc: https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html
- Spring Framework 6.2 — `JsonPathResultMatchers`: https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/test/web/servlet/result/JsonPathResultMatchers.html
- Spring Framework 6.2 — `JsonPathExpectationsHelper`, null and missing: https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/test/util/JsonPathExpectationsHelper.html
- Spring Framework 6.2 — `ContentResultMatchers` and `JsonCompareMode`: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/test/web/servlet/result/ContentResultMatchers.html
- Spring Boot 3.5 — Testing Spring MVC: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Jayway JsonPath — expression syntax: https://github.com/json-path/JsonPath