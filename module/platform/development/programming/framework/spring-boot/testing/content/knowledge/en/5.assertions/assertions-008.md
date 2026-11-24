# JSON Assertions, JSONPath, and Structural Comparison in Spring Boot Testing

## Objectives

A REST endpoint can return HTTP 200 and still deliver wrong data: missing fields, wrong numeric types, wrong element counts, wrong transaction ordering, or accidentally exposed internal fields. Therefore, API tests must **verify JSON contents** against the contract alongside HTTP status.

After this lesson, you will be able to:

- Distinguish checking **a single value** via JSONPath from checking **the entire JSON structure**.
- Write assertions for nested objects, arrays, indexed elements, filters, `null`, and absent fields.
- Use `MockMvc` with `jsonPath(...)` and `content().json(...)` at the Spring Boot controller layer.
- Understand **strict** vs. **lenient** JSON comparison and when to choose each; compare JSON trees with Jackson `JsonNode`.
- Design tests that avoid brittle coupling to field order, whitespace, or unguaranteed array order; separate the HTTP contract from Java internals.
- Run a Spring Boot/Java 17 example with Gradle and inspect JUnit results.

This article focuses on **JSON assertions in Spring Boot API tests**. JSONPath is a query syntax; an assertion is an expectation check; structural comparison matches objects/arrays. The three concepts are related but answer different questions.

## 1. Returned JSON and what needs verification

Suppose `GET /api/orders/42` returns:

~~~json
{
  "id": 42,
  "status": "CONFIRMED",
  "customer": {
    "code": "C01",
    "name": "Lan"
  },
  "items": [
    { "sku": "BOOK", "quantity": 2, "unitPrice": 120 },
    { "sku": "PEN", "quantity": 1, "unitPrice": 10 }
  ],
  "total": 250,
  "paid": true
}
~~~

To write a high-value test, turn the contract into checks capable of catching bugs:

| Rule / contract | What to assert | Option |
| --- | --- | --- |
| API returns a valid order | HTTP 200 and JSON media type | `status().isOk()`, `contentTypeCompatibleWith` |
| Exact ID and status | `id=42`, `status=CONFIRMED` | `jsonPath("$.id")`, `jsonPath("$.status")` |
| Right customer | `customer.code=C01` | Nested JSONPath |
| Exactly two items | `items` has 2 elements | JSONPath + Hamcrest `hasSize(2)` |
| Item ordering is part of the contract | SKUs are `BOOK` then `PEN` | Array JSONPath + `contains` |
| Response must not add internal fields | Only published fields appear | **Strict** structural comparison |
| Only a subset of fields is required | Specific fields match; new fields allowed | **Lenient** comparison or selective JSONPath |

**HTTP status alone does not prove JSON is right.** Conversely, a JSON assertion can fail because the response was an HTML error page or malformed JSON, so controller tests should check status and content type first to keep failures readable.

### Three common inspection approaches

1. **JSONPath:** extracts a value or set of values by path and compares against expected. Suitable when the contract targets specific fields.
2. **Structural JSON comparison:** compares an expected JSON document with the response as an object/array tree, ignoring formatting whitespace and object key order; strict vs. lenient controls extra fields and array ordering.
3. **Jackson `JsonNode`:** parses expected and actual into node trees and runs JUnit assertions. Suitable when checking entire responses, traversing nodes, or running custom checks.

Do not use raw string equality between two JSON texts when the real requirement is **semantic equivalence**. Two strings differing in whitespace or key order are still equivalent JSON objects.

## 2. What is JSONPath?

JSONPath expresses a traversal path through a JSON document. Common syntax:

| Expression | Meaning on the example JSON |
| --- | --- |
| `$` | Entire JSON document |
| `$.status` | String `"CONFIRMED"` |
| `$.customer.code` | String `"C01"` |
| `$['customer']['name']` | Alternative notation returning `"Lan"` |
| `$.items` | Items array |
| `$.items[0].sku` | SKU of the first item: `"BOOK"` |
| `$.items[*].sku` | List of SKUs: `["BOOK","PEN"]` |
| `$.items[?(@.sku == 'BOOK')].quantity` | List of quantities for matching items, here `[2]` |

`$` is the root. `.` selects a field; `[0]` selects a 0-based array index; `[*]` selects all elements; `[?()]` filters elements by predicate. `@` inside a filter expression refers to the current element. Note that **filter expressions usually return a list**, even when only one element matches.

**JSONPath does not have one identical semantics across every library.** In Spring MVC Test, `jsonPath` uses the JSONPath evaluator provided by Spring Test/Jayway. Some operators and error messages vary by library version; test your expressions against your project's dependency versions.

### JSONPath in `MockMvc`

Example assertion style (illustrative snippet requiring configured `mockMvc` and controller):

~~~java
mockMvc.perform(get("/api/orders/42"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.status").value("CONFIRMED"))
        .andExpect(jsonPath("$.items[0].sku").value("BOOK"))
        .andExpect(jsonPath("$.items[*].sku")
                .value(contains("BOOK", "PEN")));
~~~

`jsonPath(...).value(...)` extracts the value and matches it. Hamcrest's `contains(...)` verifies **exact elements in order**; if array order is not required, choose an order-independent matcher such as `containsInAnyOrder(...)` paired with an appropriate size check.

Use JSONPath for **externally exposed** values, not internal implementation details like how many times a controller calls a service unless that interaction itself is under test.

## 3. Assertions for values, types, arrays, and absent fields

Useful `MockMvcResultMatchers.jsonPath` matchers:

| Assertion | Meaning |
| --- | --- |
| `jsonPath("$.id").value(42)` | Numeric value must equal 42 |
| `jsonPath("$.status").value("CONFIRMED")` | String value must match expected |
| `jsonPath("$.paid").value(true)` | Boolean value must match |
| `jsonPath("$.items").isArray()` | Node is an array |
| `jsonPath("$.customer").isMap()` | Node is a JSON object represented as a map |
| `jsonPath("$.items").value(hasSize(2))` | Array has exactly two elements |
| `jsonPath("$.items[*].sku").value(contains("BOOK","PEN"))` | SKU sequence matches content and order |
| `jsonPath("$.status").isString()` | Value is a string |
| `jsonPath("$.total").isNumber()` | Value is a number |
| `jsonPath("$.internalFlag").doesNotHaveJsonPath()` | No field exists at that path |

`hasSize`, `contains`, `containsInAnyOrder`, and `hasItem` are Hamcrest matchers passed into `value(Matcher)`. For JSONPaths returning collections, pick **collection** matchers rather than matching a single scalar.

### Distinguishing absent fields, `null`, and empty strings

These three JSON documents represent different contracts:

~~~json
{"customer": {}}
~~~

~~~json
{"customer": {"nickname": null}}
~~~

~~~json
{"customer": {"nickname": ""}}
~~~

- **Absent:** there is no `nickname` property. When the property must not appear at all, use `jsonPath("$.customer.nickname").doesNotHaveJsonPath()`.
- **Present with `null`:** the property exists with value `null`. Use `jsonPath("$.customer.nickname").hasJsonPath()` to confirm **the path exists even when its value is null**; combine with a null check by reading `JsonNode` and checking `isNull()`.
- **Empty string:** the property has value `""`, a valid zero-length string; `jsonPath("$.customer.nickname").value("")` checks this exact meaning.

An easily confused pair: `exists()` requires a **non-null** value, whereas `hasJsonPath()` accepts `null` as long as the path is present. Likewise, `doesNotExist()` negates a non-null value, whereas `doesNotHaveJsonPath()` requires the path **not to exist at all**, disallowing even `null`. Picking the wrong one can let unwanted fields slip through.

With Jackson, `node.path("nickname")` returns `MissingNode` when absent, whereas `node.get("nickname")` returns Java `null` when missing and a `NullNode` for JSON `null`. Therefore, never write `node.get(...) == null` to treat an absent field and JSON `null` as identical.

### Numbers in JSON and type concerns

JSON has a single **number** type, while Java parsers may decode `42`, `42.0`, and `0.1` as `Integer`, `Long`, `Double`, or `BigDecimal` depending on configuration. Overly strict type matching can fail tests despite equivalent business values; overly loose matching can miss contract bugs.

- If the API requires an integer, assert `isNumber()` and the expected integer value, or check `isIntegralNumber()` on a Jackson node.
- For money, specify representation explicitly (**number vs. string, currency unit, scale/rounding**); avoid strict `double` equality when unnecessary.
- If the API mandates `"250"` as a string, assert a string instead of accepting number `250`.
- Do not assume `1` and `1.0` are treated identically across all JSON comparison libraries; numeric equality depends on the comparator/node type.

## 4. Two structural comparison modes: strict and lenient

Spring MVC Test provides:

~~~java
.andExpect(content().json(expectedJson, true))   // strict
.andExpect(content().json(expectedJson, false))  // lenient
~~~

These are **chaining expressions for `MockMvc`**, not standalone Java programs. `expectedJson` is a valid JSON string, and `content().json` delegates to a JSON comparator (typically JSONassert in Spring Test) rather than raw string equality.

### Strict comparison

Strict mode fits when the contract defines **the full structure**:

- Objects in actual must not omit required fields or add fields absent from expected.
- Values must match.
- Array elements must match in **both content and order**.
- Key order **inside a JSON object** does not matter; a JSON object is an unordered map of properties, not a sequence.

Example expected JSON:

~~~json
{
  "id": 42,
  "items": [
    {"sku": "BOOK"},
    {"sku": "PEN"}
  ]
}
~~~

If actual adds `"status"` to the root object or `"quantity"` inside items, strict mode reports a structural mismatch. If actual swaps the two items, strict mode fails too. Thus, to use strict mode on a real response, `expected` must list **every field in the contract**.

### Lenient comparison

Lenient mode fits when `expected` states a **minimum set of required fields**:

~~~json
{
  "id": 42,
  "status": "CONFIRMED"
}
~~~

Actual may include additional `customer`, `items`, `total`, and `paid` fields and still pass as long as the listed values match. Lenient mode normally also **does not require arrays to preserve strict order**, though it still checks expected elements rather than ignoring all array differences. Never rely on lenient mode to prove no sensitive fields were leaked.

| Criterion | Strict (`true`) | Lenient (`false`) |
| --- | --- | --- |
| Required fields in expected | Must exist | Must exist |
| Extra fields in actual outside expected | Typically fails | Accepted |
| Object key ordering | Ignored | Ignored |
| Array element ordering | Enforced | Not strictly enforced like strict mode |
| Value checks on fields present in expected | Yes | Yes |
| Best fit | Fixed API/schema needing extra-field protection | Verifying core fields when response may evolve |

With JSON arrays containing duplicates or complex nested objects, lenient array matching can be subtle to reason about; JSONPath assertions on targeted properties or business-key comparisons are often clearer.

### When does strict comparison produce brittle tests?

If responses contain per-request fields such as `generatedAt`, `traceId`, random IDs, or unguaranteed element order, strict comparison over the whole response fails on details **outside the contract**. Assert dynamic fields by type/format and compare stable parts via JSONPath, or normalize data before structural comparison when rules permit.

Conversely, on sensitive endpoints allowed to return **only a fixed set of fields**, strict mode helps catch accidental exposure of unintended fields.

## 5. Comparing JSON trees with Jackson `JsonNode`

Jackson's `ObjectMapper.readTree(String)` parses JSON into a tree of nodes—`ObjectNode` for objects, `ArrayNode` for arrays, `TextNode`, `NumericNode`, `NullNode` for values. Once parsed, whitespace and object key order do not affect equality; **array order and node types/values** still matter.

~~~java
JsonNode expectedTree = objectMapper.readTree(expectedJson);
JsonNode actualTree = objectMapper.readTree(actualJson);

assertEquals(expectedTree, actualTree);
~~~

This is an illustrative snippet assuming `objectMapper`, `expectedJson`, `actualJson`, and imports are set up. Extra fields, mismatched node values, or reordered array elements cause tree comparison to fail. Unlike `content().json(..., false)`, `JsonNode.equals` has no built-in mode to ignore extra object fields.

### Choosing `get` vs. `path` when inspecting

~~~java
JsonNode customer = actualTree.path("customer");
String code = customer.path("code").asText();

assertEquals("C01", code);
assertEquals(2, actualTree.path("items").size());
~~~

While convenient, `path(...).asText()` on a missing node returns an empty string, which can hide bugs if expected is also empty. When the contract requires a node to be present, check `has(...)`, `isMissingNode()`, `isNull()`, or node type before reading values:

~~~java
assertEquals(true, actualTree.has("customer"));
assertEquals(true, actualTree.path("customer").isObject());
assertEquals("C01",
        actualTree.path("customer").path("code").asText());
~~~

When distinguishing `null` from missing fields, combine `has("field")` with `isNull()` and `hasNonNull("field")` accurately. `has` returns `true` even when the field holds JSON `null`; `hasNonNull` returns `true` only when the field has a non-null value.

### Jackson trees and numeric type comparison

`JsonNode.equals` does not merely compare raw text; it compares node types and values. For instance, integral and floating-point numeric nodes can differ even when displaying similar values, and `BigDecimal` nodes follow type/scale rules. If the contract cares about numeric value rather than JSON representation, normalize types or assert via `decimalValue()`/`compareTo` per specification instead of assuming all numbers compare identically.

**Never parse JSON manually by splitting strings on commas or using regex.** JSON strings can contain commas, escaped characters, and nested objects/arrays; a real parser handles all of these properly.

## 6. Runnable Spring Boot / Java 17 example

This example builds a simple Spring Boot MVC controller and **five** `MockMvc` tests. `@WebMvcTest` starts a Spring MVC slice without binding a real HTTP port. The goal is observing the JSON a client receives after Jackson and MVC serialization. The code uses no database, external services, or random time, so outcomes are deterministic.

### 6.1. File layout

~~~text
json-assertions-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
└── src/
    ├── main/java/com/example/testing/DemoApplication.java
    ├── main/java/com/example/testing/OrderController.java
    └── test/java/com/example/testing/OrderControllerTest.java
~~~

A Gradle Wrapper is needed in the project. Use the repository's existing wrapper scripts or generate them from a compatible Gradle installation; do not hand-write `gradle-wrapper.jar`.

**`settings.gradle`**

~~~groovy
rootProject.name = 'json-assertions-demo'
~~~

**`build.gradle`** — pins a specific Spring Boot 3.3.x version for reproducibility in this example, without implying an existing project must change versions:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-test` includes Spring MVC Test, JUnit Jupiter, Jackson support via the app, and standard assertions/matchers. `content().json(...)` relies on the JSON comparison library included with those test dependencies. In projects with custom exclusions, verify the actual test runtime classpath. The Java toolchain requires a matching JDK 17.

**`src/main/java/com/example/testing/DemoApplication.java`**

~~~java
package com.example.testing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Having `@SpringBootApplication` in the root package lets Spring Boot Test locate application configuration automatically. The `main` method does not need to be invoked manually when running `@WebMvcTest`.

**`src/main/java/com/example/testing/OrderController.java`**

~~~java
package com.example.testing;

import java.util.List;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping("/{id}")
    public ResponseEntity<OrderResponse> find(@PathVariable long id) {
        if (id != 42L) {
            return ResponseEntity.notFound().build();
        }

        OrderResponse order = new OrderResponse(
                42L,
                "CONFIRMED",
                new Customer("C01", "Lan"),
                List.of(
                        new Line("BOOK", 2, 120),
                        new Line("PEN", 1, 10)
                ),
                250,
                true
        );
        return ResponseEntity.ok(order);
    }

    public record OrderResponse(
            long id,
            String status,
            Customer customer,
            List<Line> items,
            int total,
            boolean paid
    ) {}

    public record Customer(String code, String name) {}

    public record Line(String sku, int quantity, int unitPrice) {}
}
~~~

The response uses DTO records serialized by Jackson using component names. `total=250` matches the example: `2 × 120 + 1 × 10 = 250`. For any ID other than 42, the controller returns HTTP 404 with an empty body.

### 6.2. Writing JSONPath, structural comparison, and JsonNode tests

**`src/test/java/com/example/testing/OrderControllerTest.java`**

~~~java
package com.example.testing;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.contains;
import static org.hamcrest.Matchers.hasSize;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    private static String expectedFullJson() {
        return """
                {
                  "id": 42,
                  "status": "CONFIRMED",
                  "customer": {
                    "code": "C01",
                    "name": "Lan"
                  },
                  "items": [
                    {"sku": "BOOK", "quantity": 2, "unitPrice": 120},
                    {"sku": "PEN", "quantity": 1, "unitPrice": 10}
                  ],
                  "total": 250,
                  "paid": true
                }
                """;
    }

    @Test
    void jsonPathChecksImportantFields() throws Exception {
        mockMvc.perform(get("/api/orders/42"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.status").value("CONFIRMED"))
                .andExpect(jsonPath("$.customer.code").value("C01"))
                .andExpect(jsonPath("$.customer.name").value("Lan"))
                .andExpect(jsonPath("$.items").isArray())
                .andExpect(jsonPath("$.items").value(hasSize(2)))
                .andExpect(jsonPath("$.items[*].sku")
                        .value(contains("BOOK", "PEN")))
                .andExpect(jsonPath("$.items[0].quantity").value(2))
                .andExpect(jsonPath("$.total").value(250))
                .andExpect(jsonPath("$.paid").value(true))
                .andExpect(jsonPath("$.discountCode")
                        .doesNotHaveJsonPath());
    }

    @Test
    void lenientJsonAllowsAdditionalFields() throws Exception {
        String requiredFields = """
                {
                  "id": 42,
                  "status": "CONFIRMED",
                  "customer": {"code": "C01"}
                }
                """;

        mockMvc.perform(get("/api/orders/42"))
                .andExpect(status().isOk())
                .andExpect(content().json(requiredFields, false));
    }

    @Test
    void strictJsonMatchesEntireResponse() throws Exception {
        mockMvc.perform(get("/api/orders/42"))
                .andExpect(status().isOk())
                .andExpect(content().json(expectedFullJson(), true));
    }

    @Test
    void jacksonJsonTreeMatchesEntireResponse() throws Exception {
        String actualJson = mockMvc.perform(get("/api/orders/42"))
                .andExpect(status().isOk())
                .andReturn()
                .getResponse()
                .getContentAsString();

        JsonNode actual = objectMapper.readTree(actualJson);
        JsonNode expected = objectMapper.readTree(expectedFullJson());

        assertEquals(expected, actual);
    }

    @Test
    void missingOrderReturns404WithoutBody() throws Exception {
        mockMvc.perform(get("/api/orders/999"))
                .andExpect(status().isNotFound())
                .andExpect(content().string(""));
    }
}
~~~

This code contains all imports, controller, Spring Boot config, and tests for the demo project. To run it, place the files at **the exact paths** shown above with a valid Gradle Wrapper. With the dependencies in `build.gradle`, no extra services or mocks are needed because the controller only depends on Spring MVC/Jackson.

### 6.3. Running the tests

On Linux/macOS, from the project root:

~~~bash
./gradlew test
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

If no wrapper exists yet, a common way to bootstrap it from an installed Gradle is `gradle wrapper --gradle-version 8.5` in the demo project; Gradle 8.5 is a compatible example for this configuration and Java 17. In real repositories, always use the project's existing wrapper and version.

Once successful, the demo test suite has **5 `@Test` methods**, each executing once; expect **5 passing tests**. `expectedFullJson` is a helper method, not a test. There is no `System.out.println`, so **no business stdout** appears. Gradle may report `BUILD SUCCESSFUL` and `UP-TO-DATE` if cached results are reused; check actual test counts in `build/reports/tests/test/index.html` or `build/test-results/test/`. To force re-execution, run `./gradlew test --rerun-tasks`.

### 6.4. Reading each test to see why it is right

**`jsonPathChecksImportantFields`:** checks HTTP status, content type, and behavior-defining fields. `contains` requires the SKU array to keep order; `doesNotHaveJsonPath` guards against returning `discountCode`. It does not forbid every unmentioned new field: if the response adds `internalNote` besides `discountCode`, this test will not automatically catch it.

**`lenientJsonAllowsAdditionalFields`:** compares only a small required subset. A full response containing extra `items`/`total`/`paid` fields still passes. This fits APIs that allow extending responses without breaking consumers or updating every test.

**`strictJsonMatchesEntireResponse`:** verifies the whole object and arrays. If the controller accidentally adds `passwordHash`, alters `status`, reorders two items, or drops a field, this test catches the structural mismatch. It deliberately depends on a fixed response contract.

**`jacksonJsonTreeMatchesEntireResponse`:** parses actual and expected JSON into trees and calls `assertEquals`. Reformatting line breaks or object key positions does not fail because it compares trees, whereas reordering array elements fails. Useful when you also need to inspect `JsonNode` programmatically.

**`missingOrderReturns404WithoutBody`:** verifies the not-found case. Do not call `jsonPath` on responses with no JSON body; separate HTTP status contracts from JSON body contracts. If a real app defines a JSON error body, update the test to match that error contract instead of assuming an empty body.

## 7. Advanced JSONPath: array filtering and unstable order

With `items`, the question may be "Does the list contain SKU `BOOK` with `quantity=2`?" regardless of index. A JSONPath filter returns a collection:

~~~java
mockMvc.perform(get("/api/orders/42"))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
                "$.items[?(@.sku == 'BOOK')].quantity")
                .value(hasItem(2)));
~~~

This is an **illustrative snippet**; if added to the test class, import `org.hamcrest.Matchers.hasItem`. When multiple items match, `hasItem(2)` only checks that at least one matched item has quantity 2. To guarantee **exactly one** `BOOK` item, also check the result size or deserialize/collect into a list and assert element count. When array ordering is a business requirement, use an order-preserving matcher instead of a filter.

When JSONPath traverses optional fields that may be absent, write safe assertions rather than assuming `[0]` exists. For an empty array, `$.items[0].sku` has no value; that may be valid in an "empty order" scenario, which belongs in its own dedicated test.

### Avoid overly weak "contains" assertions

If the requirement is "only `BOOK` and `PEN`, no other SKUs", the following assertion is too weak:

~~~java
// At least one SKU is BOOK, but does not ensure there are only two SKUs.
jsonPath("$.items[*].sku").value(hasItem("BOOK"));
~~~

Replace it with `contains("BOOK", "PEN")` if **order is fixed**, or combine `hasSize(2)` with `containsInAnyOrder("BOOK", "PEN")` if **order does not matter**. These snippets use matching Hamcrest matchers and require imports; they are not standalone Java programs.

## 8. Key differences when comparing JSON

| Difference between actual and expected | Single-field JSONPath | Lenient structural | Strict structural | Jackson tree |
| --- | --- | --- | --- | --- |
| Whitespace / line break changes in JSON text | Unaffected | Unaffected | Unaffected | Unaffected |
| Reordered object keys | Unaffected | Unaffected | Unaffected | Unaffected |
| Added `extra` field absent from expected | Caught only if explicitly forbidden | Usually accepted | Fails | Fails |
| Omitted an asserted field | Fails | Fails | Fails | Fails |
| Reordered array elements | Depends on path/matcher | Usually accepted | Fails | Fails |
| Changed field value | Fails if field is asserted | Fails | Fails | Fails |
| `null` instead of absent field | Depends on `exists`/`hasJsonPath` | Depends on expected/comparator | Distinguishes structurally | Distinguishes null vs. missing node |
| Integer replaced by string | Fails when numeric expected is checked | Fails numeric expectation | Fails numeric expectation | Node type differs |

This table summarizes **typical comparison behavior** and does not replace checking how your specific comparator/library configuration handles floats, `null`, and nested arrays.

### Choosing assertions by contract

- **Contract cares about a few fields:** JSONPath; verify exact types and expected values without pinning unrelated fields.
- **Contract forbids unlisted fields:** strict structural comparison or JSON tree equality; add explicit assertions forbidding sensitive fields if needed.
- **Contract allows evolution:** lenient structural or selective JSONPath, while still verifying all mandatory fields.
- **Contract allows arrays in any order:** pick order-independent matchers; avoid full-response `JsonNode` tree equality if array order is not guaranteed.
- **Response includes dynamic timestamps/IDs:** assert format, type, or bounds (e.g., timestamp within valid window) while checking stable fields; avoid hardcoding nondeterministic values.

A test suite can combine tools: JSONPath for business fields, strict comparison for highly stable responses, and Jackson for complex structural rules. You do not need all three on every endpoint.

## 9. Common errors and troubleshooting

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| Test with status 200 passes despite wrong body | Asserted only status | Add JSONPath or structural assertions per contract |
| `No value at JSON path` | Misspelled field, wrong path, missing element, or non-JSON response | Inspect/print actual response body, check path and test inputs |
| Hamcrest matcher fails between `Integer` and `Long` | Parsed numeric type differs from expected | Use matching matcher/value type and clarify numeric contract |
| `hasItem` passes despite extra items in response | Matcher only requires at least one match | Check array size and full contents if required |
| Strict structural fails when API adds a valid field | Expected pins the entire structure | Switch to lenient or JSONPath if contract permits evolution |
| Lenient passes even though API leaks unwanted field | Comparator allows extra fields | Use strict mode or explicitly forbid the sensitive field |
| Test fails when array order changes | Matcher/strict/tree enforces ordering | Check whether order is in contract; use order-independent matchers if not |
| Test fails on key order or whitespace | Raw string comparison on body | Parse JSON or use `content().json` |
| A `null` field is treated as absent | Misused `exists()`/`doesNotExist()` | Use `hasJsonPath()`/`doesNotHaveJsonPath()` or Jackson node checks |
| `@WebMvcTest` fails to initialize context | Missing `@SpringBootConfiguration`, security filter, or controller/mapper bean | Inspect context error, place bootstrap class properly, mock/import needed beans |
| `MockMvc` assertion fails with unauthorized/redirect | Spring Security filter is active in tests | Configure mock user/security test setup per contract; do not disable security arbitrarily |
| Status matches but Content-Type differs | Controller returns text/HTML or wrong converter | Check API serialization and Jackson/MVC configuration |
| Test records expected JSON from current code output | Test "copied" bugs from SUT | Author expected values independently from contract and business rules |

**Practical diagnostic tip:** when a JSONPath fails, inspect the response body in logs or temporarily add `andDo(print())` in `MockMvc` to see the payload. Never leave secrets logged in CI. When structural comparison fails, read the diff path and determine whether the difference is a contract violation or a valid change.

## 10. Practice exercises

**Exercise A – fields and types:** Add assertions for `$.customer.name`, `$.items[1].unitPrice`, and `$.total`. Use matchers confirming `items` is an array and `paid` is a boolean; expected values for the sample response are `"Lan"`, `10`, `250`, and `true`.

**Exercise B – absent vs. null:** Add an optional `note` field to the DTO; test returning `null`, empty string `""`, and omitting the field completely (which may require Jackson omit-null configuration). Write tests distinguishing all three via `hasJsonPath()/doesNotHaveJsonPath()` and `JsonNode.has/isNull`. Do not treat the three as equivalent if the API contract separates them.

**Exercise C – strict vs. lenient:** With an expected JSON containing only `id` and `status`, observe lenient passing and strict failing when the response has extra fields. Then use `expectedFullJson()` to make strict pass. Swap the order of the two items in the response and observe strict and tree comparisons failing when order is part of the contract.

**Exercise D – catching extra fields:** Temporarily add `privateToken` to the response DTO. JSONPath checking only key fields may still pass; strict structural comparison and Jackson tree equality must fail. Revert the experimental change and rerun to verify your tests guard the structure.

**Exercise E – dynamic API data:** Simulate an endpoint returning a fresh `createdAt` per call. Propose assertions checking ISO-8601 format or timestamp parsing while matching stable fields with JSONPath; avoid hardcoded expected timestamps that make tests flaky.

## 11. Checklist when writing JSON assertions

1. **Clarify the contract:** which fields are required, what types, can they be `null`, which fields must not leak, and must arrays keep order?
2. **Choose the right check level:** JSONPath for targeted fields; strict/lenient structural for objects; `JsonNode` when traversing/comparing full trees programmatically.
3. **Set clear request preconditions:** inputs, path, query params, authentication, and test profile must be deterministic.
4. **Assert status and media type** before JSON body checks; HTTP error tests differ from success JSON tests.
5. **Derive expected independently from the SUT**, especially "golden" expected JSON and totals/money; never serialize the actual object to create expected.
6. **Express array expectations clearly:** element count, contents, and whether order is required.
7. **Distinguish absent fields, null, and empty strings**, as well as integers/floats/strings; do not let serializer defaults dictate your contract.
8. **Run tests via the Wrapper and inspect reports**; introduce a small deliberate bug to verify relevant assertions fail, then revert.

**Remember:** JSONPath answers "what value does this field have?", structural comparison answers "does the overall response shape match?", and Jackson `JsonNode` lets you inspect and compare JSON trees in Java code. Choose assertions based on **the API's external contract**, so tests fail when behavior breaks and stay stable when unimportant implementation details change.
