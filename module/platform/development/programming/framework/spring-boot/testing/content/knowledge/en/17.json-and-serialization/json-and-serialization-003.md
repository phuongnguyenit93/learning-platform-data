# Testing JSON Output by Structure and Key Properties in Spring Boot

## 1. Why must JSON be tested structurally?

When writing a Spring Boot REST API, a response looks like this:

```json
{
  "sku": "SKU-001",
  "title": "Spring Testing",
  "price": {
    "amount": 19.90,
    "currency": "USD"
  },
  "available": true
}
```

What clients actually depend on is the **structure** and the **values/semantics of key properties**: `sku` is an identifier string, `price` is an object with a numeric `amount` and `currency`, and `available` is a boolean. Object key order or the amount of whitespace is usually **not** part of the API contract.

Testing the response with raw string comparison is brittle:

```java
assertEquals(
    "{\"sku\":\"SKU-001\",\"title\":\"Spring Testing\",...}",
    responseBody);
```

If Jackson merely changes field ordering or whitespace formatting, this string check can fail even though clients can still read the exact right JSON. Conversely, checking only HTTP 200 can **miss** wrong field types, missing data, incorrect prices, wrong returned lists, or accidentally leaked sensitive data.

This lesson teaches **choosing the right assertion level**:

1. Check **response contract**: HTTP status, Content-Type, JSON object/array root.
2. Check **required properties**: path exists, right type, and right value/semantics.
3. Check **nested structures**: objects, arrays, relationships between fields, cardinality.
4. Check **negative contract**: fields must be absent, no leaking of `passwordHash`/`internalCost`/`secretToken`.
5. Choose **strict/lenient** for full-JSON comparisons when required by the contract.
6. Use JSON Schema or snapshot/golden files only when they address a real risk.
7. Write reliable tests with Spring Boot 3.5, JUnit Jupiter, `MockMvc`, `MockMvcTester`, `@JsonTest`/`JacksonTester`, `ObjectMapper`/`JsonNode`, and `WebTestClient` when using WebFlux.

**Principle:** Tests should be **strict about the public contract and flexible about non-contract details**. "Checking fewer fields so tests don't fail" is insufficient if required fields are skipped or sensitive data leaks.

## 2. JSON is a value tree, not a formatted string

### 2.1. Node types in JSON

JSON has six value types: **object**, **array**, **string**, **number**, **boolean**, **null**. There are no formal JSON types named `BigDecimal`, `LocalDateTime`, or `UUID`; those meanings are defined by the API contract over a JSON number/string and serialization rules.

```json
{
  "id": "p-17",
  "total": 19.9,
  "active": true,
  "tags": ["spring", "testing"],
  "shipping": {
    "city": "Hanoi",
    "fee": 0
  },
  "discount": null
}
```

JSON paths:

| JSONPath | Expected type | Meaning |
| --- | --- | --- |
| `$.id` | string | Product identifier |
| `$.total` | number | Numeric value, not string `"19.9"` |
| `$.active` | boolean | `true`, not `"true"` |
| `$.tags` | array | Tag list |
| `$.tags[0]` | string | First element if ordering is contracted |
| `$.shipping` | object | Nested object |
| `$.shipping.city` | string | Location |
| `$.discount` | null | Field exists but value is null |

### 2.2. Two different JSON strings can be equivalent

The following two objects normally carry the same meaning:

```json
{"sku":"SKU-001","available":true,"price":{"amount":19.90,"currency":"USD"}}
```

```json
{
  "price": {"currency": "USD", "amount": 19.90},
  "available": true,
  "sku": "SKU-001"
}
```

In JSON, clients should not rely on the order of **object members** unless the contract states otherwise. However, **element order inside an array** is meaningful and can be part of the contract, such as `items` sorted chronologically.

Do not conflate these two statements:
- "We don't care about **key order inside objects**."
- "We don't care about **element order inside arrays**."

The second is only true when the list is a set without a committed order.

### 2.3. Missing, null, empty, and false are four distinct meanings

Compare:

```json
{}
```

```json
{"discount":null}
```

```json
{"discount":0}
```

```json
{"discount":false}
```

```json
{"discount":[]}
```

In an API, an absent `discount` may mean "property not supported," `null` means "unknown/not applicable," `0` is a zero discount, and `false`/`[]` belong to other types. They are not interchangeable just because a UI happens to display a default value.

Distinguish them in Spring MVC:

```java
jsonPath("$.discount").exists();            // only when there is a non-null value
jsonPath("$.discount").hasJsonPath();       // even when the field exists with null
jsonPath("$.discount").doesNotExist();      // no non-null value present
jsonPath("$.discount").doesNotHaveJsonPath();// field is completely absent, including null
```

These are **illustrative matcher expressions**, used from `MockMvcResultMatchers.jsonPath` inside an `andExpect(...)`. The hands-on section will use `doesNotHaveJsonPath()` to enforce **absolute absence** of sensitive fields. If `doesNotExist()` is used for a sensitive field, a response containing `"passwordHash":null` could still pass the test even if policy forbids that key from ever appearing.

## 3. Choosing an assertion strategy by risk

| What to prove | Appropriate check | Do not rely solely on |
| --- | --- | --- |
| API succeeds | `status().isOk()` and Content-Type | Checking only body text |
| Root is an object | Parse with `JsonNode.isObject()` or JSONPath type | Looking for the first `{` character |
| Required field has a value | `jsonPath("$.sku").value(...)` | `contains("SKU-001")` in raw text |
| Field is properly numeric | `jsonPath("$.price.amount").isNumber()` | Comparing `String` `"19.90"` |
| Boolean field has proper type | `jsonPath("$.available").isBoolean()` | Comparing text `"true"` |
| Sensitive field completely absent | `doesNotHaveJsonPath()` or `JsonNode.has()==false` | `doesNotExist()` (null can still pass) |
| Array has exact item count | `jsonPath("$.items", hasSize(2))` | Checking only `items[0]` |
| Uncommitted-order list | `containsInAnyOrder` + cardinality | `items[0]` must be product A |
| Committed-order list | `containsExactly`/JSON compare STRICT | LENIENT ignoring order |
| Whole JSON object must match | `content().json(expected, JsonCompareMode.STRICT)` | Raw string equality |
| Only a subset of fields is contracted | JSONPath/selective `JsonNode` assertions | Strict full-response snapshot |
| DTO serialization | `@JsonTest` + `JacksonTester` | Full server test just for a small Jackson annotation |
| Full MVC wiring | `@SpringBootTest + @AutoConfigureMockMvc` | Plain Java object unit test |
| WebFlux response | `@WebFluxTest` + `WebTestClient` | `MockMvc` (different servlet stack) |
| Formal contract for large payloads | JSON Schema and contract tests | Unreviewed snapshots |

**Combine thoughtfully**: one test can check status + media type + key fields + no sensitive leaks; a separate test checks **strict full response** when an endpoint has a rigid contract. Do not cram all assertions into one overly long method.

## 4. Spring MVC: checking JSON via MockMvc and jsonPath

### 4.1. MockMvc does not run a real HTTP server

`MockMvc` dispatches mock servlet requests to `DispatcherServlet`, controllers, message converters, and filters present in the test context. It is well suited for testing routing, JSON serialization, status codes, and controller behavior without opening a TCP port.

With Spring Boot 3.5 and JUnit Jupiter:

```java
@WebMvcTest(ProductController.class)
class ProductControllerJsonContractTest {
    @Autowired
    MockMvc mvc;

    @MockitoBean
    ProductService service;
}
```

`@WebMvcTest` is an MVC slice. It does not scan every `@Service`/repository in the app; `@MockitoBean` supplies the controller's exact collaborator while the test still exercises the **real controller and Jackson HTTP layer**.

### 4.2. High-value assertions

```java
mvc.perform(get("/api/products/{sku}", "SKU-001")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_JSON))
    .andExpect(jsonPath("$.sku").value("SKU-001"))
    .andExpect(jsonPath("$.price").isMap())
    .andExpect(jsonPath("$.price.amount").isNumber())
    .andExpect(jsonPath("$.price.currency").value("USD"))
    .andExpect(jsonPath("$.available").isBoolean())
    .andExpect(jsonPath("$.internalCost").doesNotHaveJsonPath());
```

This is an example inside a JUnit test with `mvc`, a stubbed service, and the corresponding static imports. `isMap` checks an object at the path, and `isNumber` checks the JSON number type without depending on object field order. Asserting `internalCost` is completely absent protects against leaking internal fields.

**Do not treat `jsonPath("$.price.amount").isNumber()` as a monetary value check.** It only proves the type; add separate value/semantic assertions when price is part of the business contract.

### 4.3. Definite vs indefinite JSONPath

Paths like `$.items[0].sku` identify a single concrete element. Path `$.items[*].sku` uses a wildcard and returns a collection. You can use Hamcrest:

```java
.andExpect(jsonPath("$.items[*].sku",
        containsInAnyOrder("SKU-001", "SKU-002")))
```

With wildcards, check the **list size** at the parent path to avoid missing duplicate or unexpected items. `containsInAnyOrder` asserts the returned value set per the matcher without enforcing order; use it when the API does not commit to sorting.

### 4.4. Arrays: content, size, and order

If `items` has two elements, check:

```java
.andExpect(jsonPath("$.items").isArray())
.andExpect(jsonPath("$.items", hasSize(2)))
.andExpect(jsonPath("$.items[*].sku",
        containsInAnyOrder("SKU-001", "SKU-002")))
```

If the API accepts `sort=price,asc` and the contract guarantees ordering, check:

```java
.andExpect(jsonPath("$.items[*].sku",
        contains("SKU-002", "SKU-001")))
```

The `contains(...)` snippet is **illustrative** for an endpoint sorted ascending by price. Do not apply that order matcher to the sample project lacking a sort parameter. When exact sorting matters, define a tie-breaker such as `sku` to avoid flaky tests when two prices are equal.

### 4.5. Checking optional and sensitive fields

```java
.andExpect(jsonPath("$.internalCost").doesNotHaveJsonPath())
.andExpect(jsonPath("$.secretToken").doesNotHaveJsonPath())
.andExpect(jsonPath("$.passwordHash").doesNotHaveJsonPath())
```

If the DTO already excludes sensitive fields from serialization, these assertions guard against refactoring accidentally adding a new getter/field. Check nested paths as well when applicable:

```java
.andExpect(jsonPath("$.customer.passwordHash").doesNotHaveJsonPath())
```

However, if the `customer` property itself is absent, a nested path matcher also passes. When the contract requires the `customer` object to exist, add `jsonPath("$.customer").isMap()` and `jsonPath("$.customer.id").isString()` to avoid "passing because the required parent object was dropped."

### 4.6. Status and Content-Type are part of the contract

An API returning 200 with a proxy HTML error body does not satisfy a JSON contract. Asserting only `contains("SKU")` can miss this. Combine:

```java
.andExpect(status().isOk())
.andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON))
```

`contentTypeCompatibleWith` allows compatible media types, such as `application/json` with charset variations. If the contract requires `application/problem+json` for errors, check that exact media type in error tests; do not force every endpoint to return `application/json`.

## 5. Comparing full JSON with JSONAssert: STRICT and LENIENT

Spring Framework 6.2 provides `org.springframework.test.json.JsonCompareMode`; `MockMvcResultMatchers.content().json(expected, mode)` uses a JSON comparator, typically JSONAssert when the corresponding dependency is present.

### 5.1. STRICT

```java
import org.springframework.test.json.JsonCompareMode;

mvc.perform(get("/api/products/SKU-001"))
        .andExpect(status().isOk())
        .andExpect(content().json("""
                {
                  "sku": "SKU-001",
                  "title": "Spring Testing",
                  "price": {
                    "amount": 19.90,
                    "currency": "USD"
                  },
                  "available": true
                }
                """, JsonCompareMode.STRICT));
```

**STRICT** compares JSON structurally, independent of object key order or whitespace, while forbidding extra members and preserving array element order. It is a good choice when the DTO itself is the contract under test and every field is significant.

### 5.2. LENIENT

```java
mvc.perform(get("/api/products/SKU-001"))
        .andExpect(status().isOk())
        .andExpect(content().json("""
                {"sku":"SKU-001","available":true}
                """, JsonCompareMode.LENIENT));
```

**LENIENT** allows objects to have additional fields and compares arrays without requiring the same order per JSONAssert semantics. It fits when only part of an object is contracted and you do not want harmless new fields to break tests.

However, **do not use LENIENT as a substitute for security checks**. Because extra properties are allowed, a response accidentally containing `"secretToken":"..."` can still match a lenient expected payload listing only `sku` and `available`. Always include `doesNotHaveJsonPath()` negative assertions or proper schema/allowlist checks.

### 5.3. Comparison table

| Change in actual vs expected | STRICT | LENIENT | Is it a bug? |
| --- | --- | --- | --- |
| Object keys reordered | Usually PASS | PASS | No, if contract does not specify order |
| New field added to object | FAIL | Can PASS | Depends on compatibility/security policy |
| Missing expected field | FAIL | FAIL | Usually a contract bug |
| Different value for expected field | FAIL | FAIL | Bug if expected is right |
| Array elements reordered | FAIL | Can PASS | Depends on whether API commits to order |
| New element added to array | FAIL | FAIL or varies by comparator | Must verify pagination/cardinality |
| String `"19.90"` instead of number `19.90` | Not equivalent per type contract | Should not be allowed through | Schema/type error |
| Null field instead of absent | Can FAIL | Depends on expected/compare mode | Requires explicit presence assertion |

Do not pick a mode just because "STRICT turns many tests red" or "LENIENT passes easily." Choose from **OpenAPI/JSON Schema and consumer expectations**; when rules differ per path, combine JSONPath/JsonNode/custom comparators instead of applying one global mode blindly.

### 5.4. Why not compare raw JSON strings?

```java
assertThat(body).isEqualTo("""
        {"sku":"SKU-001","available":true}
        """);
```

This checks both whitespace and JSON object property order. It may suit byte-for-byte wire formats or signed payloads, but is **not appropriate by default** for HTTP JSON business APIs. Parse JSON or use JSON-aware matchers.

### 5.5. Version note

Spring Framework 6.2 added the overload taking `JsonCompareMode`. The older `content().json(expected, booleanStrict)` overload still exists in some 6.2 releases but is deprecated; when the sample uses 6.2, prefer the enum. With Boot 3.3 / Framework 6.1, use the API available in that version or upgrade the dependency BOM consistently.

## 6. Jackson JsonNode: structural checks with fine-grained control

JSONPath is convenient in MVC tests. Yet sometimes you need to check **multiple conditional paths, exact numeric math, or clearly distinguish missing from null**. Then parse once using Jackson:

```java
JsonNode root = objectMapper.readTree(responseBody);
```

`ObjectMapper` from Spring Boot can be `@Autowired` in a full-context test, or instantiated with the mapper config under test. You are not required to use `ObjectMapper` for every response test.

### 6.1. isObject, isArray, isTextual, isNumber, isBoolean

```java
assertThat(root.isObject()).isTrue();
assertThat(root.path("sku").isTextual()).isTrue();
assertThat(root.path("price").isObject()).isTrue();
assertThat(root.path("price").path("amount").isNumber()).isTrue();
assertThat(root.path("available").isBoolean()).isTrue();
```

`path(...)` returns a **MissingNode** instead of throwing an exception when a field is not found; that is convenient for nested checks but can hide missing fields if you only call `asText()` without asserting presence/type.

### 6.2. get, path, has, hasNonNull

| Jackson API | When field is absent | When field is JSON null |
| --- | --- | --- |
| `root.get("field")` | Returns Java `null` | Returns `NullNode` |
| `root.path("field")` | Returns `MissingNode` | Returns `NullNode` |
| `root.has("field")` | `false` | `true` |
| `root.hasNonNull("field")` | `false` | `false` |
| `root.path("field").isMissingNode()` | `true` | `false` |
| `root.path("field").isNull()` | `false` | `true` |

If the requirement is "this field must not appear," use `assertThat(root.has("secretToken")).isFalse()`, not `hasNonNull`, because the key could appear with `null` and still pass.

### 6.3. JSON Pointer

Jackson `JsonNode.at(...)` uses JSON Pointer (RFC 6901), which differs from JSONPath:

```java
JsonNode amount = root.at("/price/amount");
JsonNode firstSku = root.at("/items/0/sku");
```

`/items/0/sku` selects the first array element; if the API does not commit to order, iterate/look up by `sku` rather than assuming index 0. `~` and `/` in field names must be escaped per JSON Pointer (`~0` and `~1`).

### 6.4. Currency: checking values with BigDecimal

`BigDecimal("19.90").equals(new BigDecimal("19.9"))` returns false due to different scale; `compareTo` returns 0 for equal numeric values. In JSON, `19.90` and `19.9` are both JSON numbers; decide whether **scale is part of the contract**.

```java
JsonNode amountNode = root.at("/price/amount");

assertThat(amountNode.isNumber()).isTrue();

BigDecimal actual = amountNode.decimalValue();
assertThat(actual.compareTo(new BigDecimal("19.90"))).isZero();
```

If the API requires displaying exactly two decimal places, you can use a **string** `"19.90"` per the contract definition, or custom serialization/formatting tested separately. Do not assert `BigDecimal.equals` when scale is not guaranteed, yet do not ignore precision/rounding when financial logic requires it.

### 6.5. Large numbers and floating point

JSON has a number type without specifying internal precision. Some parsers convert numbers into `Integer`, `Long`, `Double`, or `BigDecimal` depending on input/configuration. When comparing money or large identifiers:
- Do not coerce 64-bit IDs into JavaScript Numbers if precision can be lost.
- Use `isNumber` to check the type, then `decimalValue()`/`bigIntegerValue()` or typed conversion to check values.
- For floating-point measurements, use explicit tolerances rather than arbitrary exact equality.
- For money, prefer decimal/exact types and domain rounding rules.

## 7. Runnable hands-on project: Spring Boot 3.5, Java 17

This demo illustrates both the **HTTP JSON contract** and the **serialization contract** with Java records, nested JSON, arrays, booleans, and `BigDecimal` prices. No DB, Kafka, Docker, or external HTTP is used.

### 7.1. Structure

```text
json-structure-lab/
├── pom.xml
├── src/main/java/com/example/jsoncontract/
│   ├── JsonContractApplication.java
│   ├── PriceView.java
│   ├── ProductView.java
│   ├── CatalogPage.java
│   ├── ProductService.java
│   └── ProductController.java
└── src/test/java/com/example/jsoncontract/
    ├── ProductFixtures.java
    ├── ProductControllerJsonContractTest.java
    ├── ProductViewJsonTest.java
    └── ProductJsonTreeIntegrationTest.java
```

Every Java file is in package `com.example.jsoncontract`. All test classes are discovered by Maven Surefire because they end in `Test`.

### 7.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>json-structure-lab</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
```

`spring-boot-starter-web` includes Spring MVC/Jackson; `spring-boot-starter-test` includes JUnit Jupiter, Mockito, AssertJ, and the needed test helpers. The Spring Boot parent manages versions; do not pin `spring-test` or a Jackson module at a mismatched version alone. `@MockitoBean` belongs to Spring Framework 6.2, available through Boot 3.5's BOM.

### 7.3. Main application

`src/main/java/com/example/jsoncontract/JsonContractApplication.java`:

```java
package com.example.jsoncontract;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonContractApplication {
    public static void main(String[] args) {
        SpringApplication.run(JsonContractApplication.class, args);
    }
}
```

### 7.4. Nested DTO: PriceView

`src/main/java/com/example/jsoncontract/PriceView.java`:

```java
package com.example.jsoncontract;

import java.math.BigDecimal;

public record PriceView(BigDecimal amount, String currency) {}
```

Jackson serializes `BigDecimal` as a JSON number, not text, under Boot's default configuration. The API contract in this example is that `price.amount` is a number and `price.currency` is a currency code string.

### 7.5. ProductView

`src/main/java/com/example/jsoncontract/ProductView.java`:

```java
package com.example.jsoncontract;

public record ProductView(
        String sku,
        String title,
        PriceView price,
        boolean available) {}
```

The public DTO **only** contains four components. It does not contain `internalCost`, `supplierPassword`, or `secretToken`. Tests will verify the absence of sensitive fields to catch unintended changes in the serialization layer.

### 7.6. CatalogPage

`src/main/java/com/example/jsoncontract/CatalogPage.java`:

```java
package com.example.jsoncontract;

import java.util.List;

public record CatalogPage(
        List<ProductView> items,
        int total,
        String requestId) {}
```

`total` is the total count of items in this illustrative page (2). In real pagination APIs, distinguish `totalElements` across the entire dataset from `items.size()` on the current page, `pageSize`, and `hasNext`; tests must not conflate those meanings.

### 7.7. ProductService

`src/main/java/com/example/jsoncontract/ProductService.java`:

```java
package com.example.jsoncontract;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class ProductService {

    public Optional<ProductView> find(String sku) {
        return "SKU-001".equals(sku)
                ? Optional.of(first())
                : Optional.empty();
    }

    public CatalogPage page() {
        return new CatalogPage(
                List.of(first(), second()),
                2,
                "req-123");
    }

    private ProductView first() {
        return new ProductView(
                "SKU-001",
                "Spring Testing",
                new PriceView(new BigDecimal("19.90"), "USD"),
                true);
    }

    private ProductView second() {
        return new ProductView(
                "SKU-002",
                "JUnit Patterns",
                new PriceView(new BigDecimal("8.00"), "USD"),
                false);
    }
}
```

Fixed data makes test outcomes predictable. Production code would fetch data from a repository or external API, with authorization and error handling; do not pull those dependencies into an example focused on JSON structure.

### 7.8. ProductController

`src/main/java/com/example/jsoncontract/ProductController.java`:

```java
package com.example.jsoncontract;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @GetMapping("/{sku}")
    public ResponseEntity<ProductView> bySku(
            @PathVariable String sku) {
        return service.find(sku)
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @GetMapping
    public CatalogPage page() {
        return service.page();
    }
}
```

Two endpoints:
- `GET /api/products/SKU-001`: HTTP 200, JSON object `ProductView`.
- `GET /api/products/NOT-FOUND`: HTTP 404, body may be empty.
- `GET /api/products`: HTTP 200, JSON object `CatalogPage` with `items` array, `total` number, and `requestId` string.

Do not expect status 201 for GET, and do not expect a 404 response to have a JSON body if the controller does not build an error DTO.

### 7.9. Shared test fixtures

`src/test/java/com/example/jsoncontract/ProductFixtures.java`:

```java
package com.example.jsoncontract;

import java.math.BigDecimal;
import java.util.List;

final class ProductFixtures {

    private ProductFixtures() {}

    static ProductView first() {
        return new ProductView(
                "SKU-001",
                "Spring Testing",
                new PriceView(new BigDecimal("19.90"), "USD"),
                true);
    }

    static ProductView second() {
        return new ProductView(
                "SKU-002",
                "JUnit Patterns",
                new PriceView(new BigDecimal("8.00"), "USD"),
                false);
    }

    static CatalogPage page() {
        return new CatalogPage(
                List.of(first(), second()),
                2,
                "req-123");
    }
}
```

`ProductFixtures` resides only in the test source set, not as a production bean. Slice tests use the fixture to stub `ProductService`; the full integration test uses the real service producing matching results.

### 7.10. ProductControllerJsonContractTest: MVC slice checking key structure

`src/test/java/com/example/jsoncontract/ProductControllerJsonContractTest.java`:

```java
package com.example.jsoncontract;

import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.json.JsonCompareMode;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsInAnyOrder;
import static org.hamcrest.Matchers.hasSize;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ProductController.class)
class ProductControllerJsonContractTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    ProductService service;

    @Test
    void checksRequiredPropertiesAndTypes() throws Exception {
        when(service.find("SKU-001"))
                .thenReturn(Optional.of(ProductFixtures.first()));

        mvc.perform(get("/api/products/{sku}", "SKU-001")
                .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$").isMap())
                .andExpect(jsonPath("$.sku").value("SKU-001"))
                .andExpect(jsonPath("$.title").value("Spring Testing"))
                .andExpect(jsonPath("$.price").isMap())
                .andExpect(jsonPath("$.price.amount").isNumber())
                .andExpect(jsonPath("$.price.currency").value("USD"))
                .andExpect(jsonPath("$.available").isBoolean())
                .andExpect(jsonPath("$.available").value(true))
                .andExpect(jsonPath("$.internalCost")
                        .doesNotHaveJsonPath())
                .andExpect(jsonPath("$.secretToken")
                        .doesNotHaveJsonPath());

        verify(service).find("SKU-001");
    }

    @Test
    void checksCollectionShapeWithoutAssumingOrder() throws Exception {
        when(service.page()).thenReturn(ProductFixtures.page());

        mvc.perform(get("/api/products")
                .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$").isMap())
                .andExpect(jsonPath("$.items").isArray())
                .andExpect(jsonPath("$.items", hasSize(2)))
                .andExpect(jsonPath("$.items[*].sku",
                        containsInAnyOrder("SKU-001", "SKU-002")))
                .andExpect(jsonPath("$.total").isNumber())
                .andExpect(jsonPath("$.total").value(2))
                .andExpect(jsonPath("$.requestId").isString())
                .andExpect(jsonPath("$.requestId").value("req-123"));

        verify(service).page();
    }

    @Test
    void strictComparisonProtectsCompletePublicDto() throws Exception {
        when(service.find("SKU-001"))
                .thenReturn(Optional.of(ProductFixtures.first()));

        mvc.perform(get("/api/products/SKU-001"))
                .andExpect(status().isOk())
                .andExpect(content().json("""
                        {
                          "sku": "SKU-001",
                          "title": "Spring Testing",
                          "price": {
                            "amount": 19.90,
                            "currency": "USD"
                          },
                          "available": true
                        }
                        """, JsonCompareMode.STRICT));
    }

    @Test
    void lenientComparisonCanCheckStableSubset() throws Exception {
        when(service.find("SKU-001"))
                .thenReturn(Optional.of(ProductFixtures.first()));

        mvc.perform(get("/api/products/SKU-001"))
                .andExpect(status().isOk())
                .andExpect(content().json("""
                        {
                          "sku": "SKU-001",
                          "available": true
                        }
                        """, JsonCompareMode.LENIENT))
                .andExpect(jsonPath("$.secretToken")
                        .doesNotHaveJsonPath());
    }

    @Test
    void missingProductHas404WithoutExpectingJsonBody()
            throws Exception {
        when(service.find("UNKNOWN"))
                .thenReturn(Optional.empty());

        mvc.perform(get("/api/products/UNKNOWN"))
                .andExpect(status().isNotFound());

        verify(service).find("UNKNOWN");
    }
}
```

**Risks protected against:**

1. `checksRequiredPropertiesAndTypes` checks values, JSON types, object nesting, MediaType, and the absence of two sensitive fields.
2. `checksCollectionShapeWithoutAssumingOrder` checks that the array has two items, both expected SKUs, numeric `total`, and `requestId`, without relying on element order when the contract does not specify it.
3. `strictComparisonProtectsCompletePublicDto` checks the entire public DTO strictly by JSON structure, not raw string.
4. `lenientComparisonCanCheckStableSubset` checks a stable subset, adding a negative assertion because LENIENT permits extra fields.
5. `missingProductHas404WithoutExpectingJsonBody` separates error status from body: the test does not assume the controller always returns a JSON error object.

All tests use `@MockitoBean` because `@WebMvcTest` does not scan services like a full context. This is an **HTTP serialization contract test of the controller**, not proof of the real service's repository query logic.

### 7.11. ProductViewJsonTest: @JsonTest checking Jackson independently of HTTP

`src/test/java/com/example/jsoncontract/ProductViewJsonTest.java`:

```java
package com.example.jsoncontract;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.json.JsonTest;
import org.springframework.boot.test.json.JacksonTester;

import static org.assertj.core.api.Assertions.assertThat;

@JsonTest
class ProductViewJsonTest {

    @Autowired
    JacksonTester<ProductView> json;

    @Test
    void writesPublicProductStructure() throws Exception {
        ProductView product = ProductFixtures.first();

        assertThat(json.write(product)).isEqualToJson("""
                {
                  "sku": "SKU-001",
                  "title": "Spring Testing",
                  "price": {
                    "amount": 19.90,
                    "currency": "USD"
                  },
                  "available": true
                }
                """);

        assertThat(json.write(product))
                .extractingJsonPathStringValue("@.sku")
                .isEqualTo("SKU-001");

        assertThat(json.write(product))
                .extractingJsonPathNumberValue("@.price.amount")
                .satisfies(value -> assertThat(
                        value.doubleValue()).isEqualTo(19.9));
    }

    @Test
    void readsDtoFromJson() throws Exception {
        String body = """
                {
                  "sku": "SKU-001",
                  "title": "Spring Testing",
                  "price": {
                    "amount": 19.90,
                    "currency": "USD"
                  },
                  "available": true
                }
                """;

        ProductView parsed = json.parseObject(body);

        assertThat(parsed.sku()).isEqualTo("SKU-001");
        assertThat(parsed.title()).isEqualTo("Spring Testing");
        assertThat(parsed.price().amount())
                .isEqualByComparingTo("19.90");
        assertThat(parsed.price().currency()).isEqualTo("USD");
        assertThat(parsed.available()).isTrue();
    }
}
```

`@JsonTest` loads only JSON serialization support and JSON helpers, without running servlets/HTTP. With `JacksonTester`, `assertThat(json.write(...)).isEqualToJson(...)` uses JSON-aware comparison; `extractingJsonPathStringValue`/`NumberValue` checks specific properties. `json.parseObject(...)` tests deserialization.

**Number note:** the test uses `19.9`, which is sufficiently accurate for this fixture, but this is not a pattern for measuring money in production. For `BigDecimal`, `isEqualByComparingTo` is more appropriate to avoid scale dependency. For floating-point numbers computed across multiple operations, use an explicit tolerance instead of exact equality.

### 7.12. ProductJsonTreeIntegrationTest: real context and JsonNode

`src/test/java/com/example/jsoncontract/ProductJsonTreeIntegrationTest.java`:

```java
package com.example.jsoncontract;

import java.math.BigDecimal;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProductJsonTreeIntegrationTest {

    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;

    @Test
    void checksNestedAmountSemantically() throws Exception {
        String body = mvc.perform(get("/api/products/SKU-001")
                .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andReturn()
                .getResponse()
                .getContentAsString();

        JsonNode root = mapper.readTree(body);

        assertThat(root.isObject()).isTrue();
        assertThat(root.path("sku").asText()).isEqualTo("SKU-001");
        assertThat(root.path("price").isObject()).isTrue();

        JsonNode amount = root.at("/price/amount");
        assertThat(amount.isNumber()).isTrue();

        BigDecimal money = amount.decimalValue();
        assertThat(money.compareTo(new BigDecimal("19.90")))
                .isZero();

        assertThat(root.path("available").isBoolean()).isTrue();
        assertThat(root.path("available").booleanValue()).isTrue();

        assertThat(root.has("internalCost")).isFalse();
        assertThat(root.has("secretToken")).isFalse();
    }

    @Test
    void checksPageMembersAndItemBusinessInvariant()
            throws Exception {
        String body = mvc.perform(get("/api/products"))
                .andExpect(status().isOk())
                .andReturn()
                .getResponse()
                .getContentAsString();

        JsonNode root = mapper.readTree(body);
        JsonNode items = root.path("items");

        assertThat(root.isObject()).isTrue();
        assertThat(items.isArray()).isTrue();
        assertThat(items.size()).isEqualTo(2);
        assertThat(root.path("total").isInt()).isTrue();
        assertThat(root.path("total").intValue()).isEqualTo(2);
        assertThat(root.path("requestId").asText())
                .matches("req-[0-9]+");

        int availableItems = 0;
        for (JsonNode item : items) {
            assertThat(item.path("sku").isTextual()).isTrue();
            assertThat(item.path("price").path("amount").isNumber())
                    .isTrue();
            assertThat(item.path("price").path("currency").asText())
                    .isEqualTo("USD");
            if (item.path("available").asBoolean()) {
                availableItems++;
            }
        }
        assertThat(availableItems).isEqualTo(1);
    }
}
```

Unlike the MVC slice, this test uses the real `ProductService` and real Boot/Jackson HTTP components, while still mocking servlet requests without opening an HTTP socket. It verifies nested numeric semantics, the `requestId` regex, and a list invariant, while protecting the absence of internal fields.

`JsonNode.path(...).asText()` returns an empty string for a missing node, so when a field is critical, also check `isTextual()`/`has(...)` before verifying its value. For `requestId` here, the regex rejects an empty string; when the contract requires a string type, add `isTextual()` as well.

### 7.13. Running the tests

Inside the `json-structure-lab` directory, with JDK 17+, Maven, and access to the dependency repository:

```bash
mvn -q clean test

mvn -q -Dtest=ProductControllerJsonContractTest test
mvn -q -Dtest=ProductViewJsonTest test
mvn -q -Dtest=ProductJsonTreeIntegrationTest test
```

All three classes are designed to PASS on Spring Boot 3.5.16. Successful Maven execution returns exit code **0**; log volume and runtime depend on the environment. Report files live in `target/surefire-reports`. The Maven tests are designed with matching imports and paths, though actual runtime results must be verified by running the build in your project environment.

Running the real application:

```bash
mvn spring-boot:run
```

Then in another terminal:

```bash
curl "http://localhost:8080/api/products/SKU-001"
curl "http://localhost:8080/api/products"
```

The first response has `sku="SKU-001"`, `title="Spring Testing"`, `price.amount=19.90`, `available=true`. The second response contains two items, `total=2`, and `requestId="req-123"`. JSON object key ordering and whitespace formatting are not guaranteed.

## 8. MockMvcTester (Spring Framework 6.2+) as an AssertJ-friendly option

With Spring Boot 3.4+/Framework 6.2+, `MockMvcTester` offers a convenient AssertJ API:

```java
import org.springframework.test.web.servlet.assertj.MockMvcTester;
import static org.assertj.core.api.Assertions.assertThat;

// Inside @WebMvcTest with @Autowired MockMvcTester tester
assertThat(tester.get().uri("/api/products/SKU-001"))
        .hasStatusOk()
        .hasContentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .bodyJson()
        .extractingPath("$.sku")
        .asString()
        .isEqualTo("SKU-001");
```

This is a **snippet**, not a standalone test file: it requires a stubbed service inside `@WebMvcTest`. In Spring Boot 3.5, when AssertJ is present, `@WebMvcTest` auto-configures the tester; `@SpringBootTest` requires `@AutoConfigureMockMvc`.

### 8.1. Comparing full JSON

```java
assertThat(tester.get().uri("/api/products/SKU-001"))
        .hasStatusOk()
        .bodyJson()
        .isStrictlyEqualTo("""
                {
                  "sku": "SKU-001",
                  "title": "Spring Testing",
                  "price": {
                    "amount": 19.90,
                    "currency": "USD"
                  },
                  "available": true
                }
                """);
```

`bodyJson().isStrictlyEqualTo` compares JSON structurally, not by raw string. When checking only a subset, use `isLenientlyEqualTo` or `extractingPath`. Do not use a strict golden file for volatile fields like timestamps or UUIDs if the business contract only requires format/uniqueness.

### 8.2. One request, multiple assertions

```java
MvcTestResult result = tester.get()
        .uri("/api/products/SKU-001")
        .exchange();

assertThat(result).hasStatusOk();

assertThat(result).bodyJson()
        .extractingPath("$.price.currency")
        .asString()
        .isEqualTo("USD");
```

For a request with side effects, capturing `MvcTestResult` and applying multiple assertions avoids accidentally executing the request multiple times.

## 9. WebFlux: same mindset, different client API

Spring WebFlux applications use `WebTestClient` (not `MockMvc`). The **illustrative** example below assumes a WebFlux controller/`@WebFluxTest` with `WebTestClient client` and endpoint `/api/products`:

```java
client.get()
        .uri("/api/products")
        .exchange()
        .expectStatus().isOk()
        .expectHeader()
        .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody()
        .jsonPath("$.items").isArray()
        .jsonPath("$.items[0].sku").isEqualTo("SKU-001")
        .jsonPath("$.total").isNumber();
```

If the real endpoint does not guarantee order, do not rely on index 0. You can retrieve the body as `byte[]`, parse it with Jackson `JsonNode`, and check membership regardless of order, or use matchers on JSONPath arrays:

```java
client.get().uri("/api/products")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .json("""
                {"total":2}
                """, JsonCompareMode.LENIENT);
```

Spring Framework 6.2 includes `WebTestClient.BodyContentSpec.json(expected, JsonCompareMode)`. With a WebFlux slice, service collaborators must be mocked if the slice does not scan services, similar to the MVC slice but using reactive service types.

Do **not** add both `spring-boot-starter-web` and `spring-boot-starter-webflux` to the Maven project in section 7 just to run both examples in the same context; Boot typically selects MVC when both stacks are present. Pick the right web application type and test client for your module.

## 10. Schema validation: when structures are large and formally contracted

### 10.1. What does JSON Schema solve?

JSONPath assertions suit a few critical fields. For large payloads used by many consumers, **JSON Schema** can enforce:

- Root object/array type.
- Required properties.
- Type, pattern, min/max, minimum/maximum.
- Array item types and cardinality.
- Nested object properties.
- Disallowing undeclared properties via `additionalProperties: false`.
- Conditional fields via `oneOf`/`anyOf`/`if/then/else` when truly needed.

A minimal **Draft 2020-12** JSON Schema for `ProductView` (this is a schema document, not code to add to the sample project):

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["sku", "title", "price", "available"],
  "properties": {
    "sku": {
      "type": "string",
      "pattern": "^SKU-[0-9]{3}$"
    },
    "title": {
      "type": "string",
      "minLength": 1
    },
    "price": {
      "type": "object",
      "required": ["amount", "currency"],
      "properties": {
        "amount": {"type": "number", "minimum": 0},
        "currency": {"type": "string", "pattern": "^[A-Z]{3}$"}
      },
      "additionalProperties": false
    },
    "available": {"type": "boolean"}
  },
  "additionalProperties": false
}
```

This schema protects structure, types, required conditions, and forbids extra fields. However, it does **not** prove the business rule "SKU-001 costs 19.90" since the schema allows any non-negative amount. Combine with concrete example assertions/business contract tests.

### 10.2. A JSON Schema validator does not come automatically from Spring Boot test

`spring-boot-starter-test` is **not** a full JSON Schema Draft 2020-12 validator by default. To test schemas, add a JSON Schema validator library compatible with the draft and JDK version (for example, a current implementation chosen by the project), then write tests asserting the schema-validation result. Do not copy imports for a library missing from the POM and expect the file to compile.

If the API is described with OpenAPI, you can use OpenAPI schema validators/contract tests at the appropriate boundary, while still specifying **which properties are required, nullable, readOnly, additionalProperties, and versioned**. Different schema-generation tools may treat null/optional/defaults differently; verify against your exact version.

### 10.3. Closed schema vs backward compatibility

`additionalProperties: false` ensures no unlisted fields appear, which is valuable for sensitive payloads. Yet it also breaks consumers/tests when the server adds a new field even if clients do not use it. Weigh the trade-offs:
- Sensitive responses: allowlist/closed schemas have high value.
- Public APIs needing additive evolution: you may accept extra fields for backwards compatibility alongside **negative assertions** for sensitive fields.
- Request input: sometimes you need to reject unknown fields to prevent mass assignment; that is a separate API policy and should not be inferred from response tests.

Either an overly rigid or overly loose schema carries risk. Make the choice through an explicit contract between producer and consumer.

## 11. JSON output with volatile fields: check format, do not hard-code values

### 11.1. UUID, requestId, and correlationId

If the API generates a fresh `requestId` per request, do not assert a fixed UUID unless the test injects an ID generator. You can use:

```java
JsonNode root = mapper.readTree(body);
String requestId = root.path("requestId").asText();

assertThat(root.path("requestId").isTextual()).isTrue();
assertThat(requestId).matches("[a-f0-9-]{36}");
```

The regex here is a **relatively loose shape check**, not proof of a valid UUID; when the contract truly requires a UUID, use `UUID.fromString(requestId)` and check version/variant or a strict UUID regex. If you want deterministic assertions, inject a replaceable `IdGenerator`/`Clock` in tests.

### 11.2. Timestamps and timezones

ISO-8601 strings can have different offsets/timezones while representing the same instant. Instead of comparing raw text:

```java
String text = root.path("createdAt").asText();

Instant actualInstant = Instant.parse(text);
assertThat(actualInstant).isEqualTo(expectedInstant);
```

This is an **illustrative** snippet when the endpoint has `createdAt` in UTC `Z` format and the test has `expectedInstant`. If the API allows other offsets, use `OffsetDateTime.parse(text).toInstant()`. When a test needs a fixed clock time, inject `Clock.fixed(...)` so it does not depend on execution time. Also check format/precision if the contract specifies milliseconds or a particular timezone.

### 11.3. Enum values

A Java enum can serialize as `"ACTIVE"`, `"active"`, an object, or an alias depending on `@JsonValue`/`@JsonFormat`/custom serializers. Do not assert only "is string" when consumers require exactly `ACTIVE`:

```java
.andExpect(jsonPath("$.status").isString())
.andExpect(jsonPath("$.status").value("ACTIVE"))
```

This is an illustrative snippet for an endpoint with `status`, not a file in the sample project (the `ProductView` project has boolean `available`). If the API renames an enum, the test must fail or the versioning contract must be updated.

### 11.4. Optional and null policy

Jackson can omit null fields when configured with `@JsonInclude(JsonInclude.Include.NON_NULL)` or a Boot `ObjectMapper` setting. When tests require a property never to appear if null, assert `doesNotHaveJsonPath()`; when the property must appear with JSON null, assert `hasJsonPath()` and check null via `JsonNode`. Do not use `exists()` to check a property where the contract permits JSON null—that matcher requires a non-null value.

## 12. Checking relationships between fields and invariants

A payload can have the right types for every field yet **wrong relationships**.

### 12.1. total and items

```json
{
  "items": [
    {"sku":"SKU-001"},
    {"sku":"SKU-002"}
  ],
  "total": 5000
}
```

This is not necessarily a bug: in pagination, `total` may mean "total count across the entire dataset," not `items.size()`. Read the contract:
- `count` of the current page → may equal `items.size()`.
- `totalElements` across the system → may exceed `items.size()`.
- `pageSize` is the requested limit, differing from actual size on the last page.
- `hasNext`/`nextCursor` may relate to pagination windows/cursors.

Do not write false invariants just because two numbers have similar names. In the sample project, `total=2` intentionally matches the two items, though real APIs may differ.

### 12.2. available and stock

If the API guarantees `available == (stock > 0)`, tests should assert that relationship, not just presence. With `JsonNode`:

```java
int stock = root.path("stock").intValue();
boolean available = root.path("available").booleanValue();

assertThat(available).isEqualTo(stock > 0);
```

This is a snippet for a real endpoint with a numeric `stock`, unlike the sample project. Check `isIntegralNumber()`/`isBoolean()` before `intValue()`/`booleanValue()` to avoid turning missing fields into default numbers/booleans and causing false positives.

### 12.3. Identifying records in an array

If the API does not guarantee order, key by an identifying property:

```java
Map<String, JsonNode> bySku = new HashMap<>();
for (JsonNode item : root.path("items")) {
    String sku = item.path("sku").asText();
    assertThat(bySku.put(sku, item)).isNull();
}

assertThat(bySku.keySet())
        .containsExactlyInAnyOrder("SKU-001", "SKU-002");
assertThat(bySku.get("SKU-001")
        .path("price").path("currency").asText())
        .isEqualTo("USD");
```

This requires imports for `Map`, `HashMap`, `JsonNode`, and AssertJ inside a test with a valid `root`. Asserting that `put(...)` returns null catches duplicate SKUs. Checking arrays via index 0 easily breaks when ordering changes outside the contract or hides duplicate items.

## 13. Common anti-patterns

### 13.1. Asserting only HTTP status

`status().isOk()` does not prove the JSON body is right. An endpoint could return 200 with `{}` or a dangerous structural change. At minimum, verify identifying fields and primary properties.

### 13.2. Comparing raw JSON strings

JSON object key order and whitespace have no business meaning in most REST contracts. Use JSON compare/JSONPath/`JsonNode` instead of `String.equals`, unless byte-level representation is contracted.

### 13.3. Using lenient everywhere so tests stay green

LENIENT allows extra fields and non-strict array order. If consumers require sorting or security requires absent fields, add explicit assertions or STRICT/schema checks where appropriate.

### 13.4. Checking sensitive fields with doesNotExist()

`doesNotExist()` only ensures no non-null value exists at the path, so a field present with null can still pass. When a field **must never appear**, use `doesNotHaveJsonPath()`.

### 13.5. Calling asText() without checking type/presence

`JsonNode.path("missing").asText()` returns an empty string. Do not treat that as a valid string when the contract requires the field. Assert `has`/`isTextual` first.

### 13.6. Asserting array indices on arbitrary order

If the DB has no `ORDER BY` or the collection is a set, JSON array order can be unstable. Assert membership/cardinality or require the API to provide stable sorting. Only assert indices when order is contracted.

### 13.7. Comparing money with double or blindly using BigDecimal.equals

For monetary amounts, `19.90` and `19.9` have the same value, yet `BigDecimal.equals` distinguishes scale. Use `compareTo` for numeric values; add scale/format assertions if the contract requires them. Avoid float/double arithmetic for money.

### 13.8. Mocking the object doing the serialization

If you mock `ObjectMapper` inside `@WebMvcTest` while testing JSON serialization, the test no longer proves real mapping. Keep Jackson HTTP infrastructure real; mock only service/repository collaborators at the boundary.

### 13.9. Putting the entire expected JSON in one unreadable test

A golden JSON file of thousands of lines can be very brittle. Split tests:
- Critical fields/structure.
- Security-negative fields.
- Schema compatibility.
- Snapshot/strict complete payload when needed.

Golden files remain useful for large stable representations, provided diffs are actually reviewed; never blindly "update snapshots" whenever tests fail.

### 13.10. Ignoring Content-Type and error status

A JSON-like body could be sent with `text/plain`, causing clients to parse unexpectedly; error payloads might require `application/problem+json`. Check status + media type at the boundary, not only content.

### 13.11. Trusting DTO equality to prove the wire contract

`assertEquals(expectedDto, actualDto)` in Java can PASS even if Jackson changes `@JsonProperty` from `sku` to `productCode`. Serialization tests must inspect the **generated JSON/response**. `@JsonTest` is good for Jackson config; MVC tests verify the HTTP contract.

### 13.12. Using full @SpringBootTest for every JSON assertion

A full context can load unrelated DBs, messaging, and external clients. For controller responses, `@WebMvcTest` is faster/more isolated; for DTO serialization, `@JsonTest` is lighter. Use a full context when cross-layer integration is the risk under test.

### 13.13. Testing only the happy path

Include appropriate negative scenarios:
- Non-existent ID → status 404, do not assume a JSON body.
- Insufficient permissions → status 403 and no leaked data.
- Null/empty/optional data → serialization matches contract.
- Empty arrays → `[]` vs null vs absent.
- Very large numbers, Unicode, timestamps, enums, and nested objects.

Do not turn every edge case into a full integration test when the concern belongs to a specific serializer.

## 14. Error HTTP responses, ProblemDetail, and security

### 14.1. 4xx/5xx responses also have a JSON contract

An API may return:

```json
{
  "type": "https://example.test/problems/invalid-input",
  "title": "Invalid input",
  "status": 400,
  "detail": "sku is required"
}
```

If using Spring `ProblemDetail` or an error DTO, tests should check status and required properties without hard-coding full stack traces/timestamps/machine hostnames. Media type may be `application/problem+json`; verify against the endpoint's exact contract.

**Illustrative snippet** for an endpoint with a matching error handler:

```java
mvc.perform(get("/api/products/").accept(MediaType.APPLICATION_JSON))
        .andExpect(status().is4xxClientError())
        .andExpect(jsonPath("$.status").isNumber())
        .andExpect(jsonPath("$.title").isString());
```

This is not an assertion runnable on every application: a path missing a segment might return 404, and Boot might not emit `ProblemDetail` automatically in all configurations. Use your project's specific error endpoint and inspect the actual handler response.

### 14.2. Never leak secrets even on errors

For unhandled exceptions, responses must not serialize stack traces, SQL queries containing secrets, or JWTs/tokens. Test against the real contract:

```java
.andExpect(jsonPath("$.stackTrace").doesNotHaveJsonPath())
.andExpect(jsonPath("$.password").doesNotHaveJsonPath())
.andExpect(jsonPath("$.accessToken").doesNotHaveJsonPath())
```

However, root-level assertions do not prove there are no secrets inside a nested `debug` object or a `detail` string. For sensitive data, consider schema allowlists and targeted scanning, and avoid logging entire real responses from CI to public places.

### 14.3. 401/403 and security test setup

If `@WebMvcTest` includes Spring Security, unauthenticated requests may receive 401, 403, or a redirect without reaching the controller. JSON body tests behave differently when the security filter intercepts requests. Use `spring-security-test` with principals/CSRF per policy. Do not disable the filter chain just to get status 200 when the goal includes security verification.

## 15. Spring @JsonTest vs MVC and full-context

| Setup | What loads? | Primary verification | Does not prove |
| --- | --- | --- | --- |
| Plain JUnit + ObjectMapper | Test-created Jackson | Serialization for that mapper | Boot mapper config if different |
| `@JsonTest` + JacksonTester | Relevant JSON mapper/modules/components | DTO serialize/deserialize | Controller routes/status/security |
| `@WebMvcTest` + MockMvc | MVC slice, Jackson HTTP layer, controller, mocked collaborators | Controller HTTP status/body/contract | Business/persistence of mocked services |
| `@SpringBootTest + @AutoConfigureMockMvc` | Full Spring app context, mock MVC requests | Real bean graph and HTTP serialization | Network/embedded server sockets |
| `@SpringBootTest(RANDOM_PORT)` + client | Real embedded HTTP server | HTTP transport and app wiring in test env | Production gateway/TLS/deployment if unconfigured |
| `@WebFluxTest + WebTestClient` | Reactive web slice | WebFlux request/response contract | Service/DB if collaborators mocked |

If the goal is "Does Jackson name fields properly?", `@JsonTest` is closest. If the goal is "Do clients calling GET receive the right JSON fields?", use `@WebMvcTest`. If the goal is "Does the real service produce the right data and pass through the controller?", use full context or combine unit/integration tests. Never extrapolate passing tests at one boundary as proof of another boundary.

## 16. Errors and how to diagnose them

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| `jsonPath("$.sku")` fails | Field missing, renamed, at another path, or body is not JSON | Print test response, parse `JsonNode`, inspect DTO/mapper |
| `$.price.amount` treated as string | Serializer turns `BigDecimal` into text; custom converter | Check Jackson config, `@JsonFormat`, and schema |
| `$.available` fails `isBoolean` | API returns string `"true"` instead of boolean | Check DTO type and serializer |
| `$.items[0]` is flaky | Order not guaranteed by contract | `containsInAnyOrder` + size, or add sorting |
| `doesNotExist` PASSES even though key has null | Matcher checks only non-null | `doesNotHaveJsonPath` |
| JSON STRICT fails due to new field | Strict forbids extra properties | Determine if extra field is breaking/security or additive |
| JSON LENIENT PASSES despite new sensitive field | Lenient allows extra properties | Negative assertions / schema allowlist |
| `@JsonTest` PASSES but MVC fails | MVC context uses different config, response wrapping/advice | Run MVC contract test and inspect Jackson beans |
| Context fails in `@WebMvcTest` | Controller collaborator missing in slice | `@MockitoBean`/`@Import` at right boundary |
| HTTP 401/403 instead of 200 | Security/filters/CSRF | Configure authentication and policy |
| `JsonNode.asText()` is empty | Field missing/null/wrong type | Check `has/isTextual` first |
| `BigDecimal` fails despite 19.90 and 19.9 | Different scale in `equals` | `compareTo` or `isEqualByComparingTo` |
| JSON date format differs across machines | Uncontrolled timezone/locale/Clock | Fix Clock/zone, parse ISO-8601 |
| Snapshot fails after UUID changes | Fixed expected on dynamic field | Regex/parser, inject deterministic generator |
| JSON Schema validator does not compile | Validator dependency not declared | Add compatible library + version/draft |
| MockMvc passes but production returns HTML | Proxy/ingress/real server differs from mock context | Add running-server/deployment test |

When debugging, record the **test boundary**, status, content type, actual JSON, differing paths, and expected contract. Distinguish:
- **Failed to load ApplicationContext**: dependency/config/slice failed before the test body.
- **AssertionFailedError**: test reached assertions, but output did not match.
- **Controller exception**: business/runtime error mapped to a status or propagated to MockMvc.
- **JSON parse error**: response is not valid JSON, or test input data is invalid.

Do not read a stack trace and immediately edit expected values to match actual just to turn it "green"; determine the contract first.

## 17. Checklist for reviewing JSON output tests

- [ ] Is the response root an object or an array? Is it checked?
- [ ] Are status and Content-Type asserted, especially on 4xx/5xx?
- [ ] Do all required fields exist with the right **JSON type**?
- [ ] Are key fields checked for value/semantics, not just presence?
- [ ] For nested objects, are parent object presence and child paths checked?
- [ ] For arrays, are cardinality and membership checked; is order contracted?
- [ ] Are missing and null distinguished? Is `doesNotHaveJsonPath` used when fields must be completely absent?
- [ ] Are sensitive fields (`passwordHash`/`internalCost`/`secretToken`) protected?
- [ ] Was STRICT/LENIENT mode chosen intentionally?
- [ ] Are currency, decimal precision, timezone, and enum casing checked per business rules?
- [ ] Do generated timestamps/UUIDs use deterministic fixtures or suitable format assertions?
- [ ] Are cross-field relationships/invariants checked when required by the contract?
- [ ] Are `@JsonTest`/`@WebMvcTest`/`@SpringBootTest` scoped appropriately?
- [ ] Are collaborator mocks registered as Spring beans via `@MockitoBean` when needed?
- [ ] Are JSON serializer tests separated from service business tests where appropriate?
- [ ] Are negative/error/empty/null cases covered, not just the happy path?
- [ ] Are raw string equality and unreviewed automatic snapshot updates avoided?
- [ ] If JSON Schema is used, is a draft-compatible validator dependency included?
- [ ] Do tests run on Maven/Gradle with the same dependency management as CI?
- [ ] When a test fails, is it checked against OpenAPI/consumer contracts before editing?

**Conclusion:** Quality JSON output testing is not about screenshotting a long JSON string, but **verifying structural contracts, types, key data, cross-field relationships, and the absence of disallowed data**. Use JSONPath for focal paths, JSON-aware STRICT/LENIENT when comparing full objects, `JsonNode` for flexible semantic checks, `@JsonTest` for Jackson, and MVC/WebFlux tests for HTTP boundaries. Stay strict on fields consumers depend on, and avoid brittle assertions on key order, whitespace, and randomly generated values.

## 18. Official Reference Documentation

- Spring Boot 3.5 — Auto-configured JSON Tests / JacksonTester: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Framework 6.2 — MockMvc Hamcrest expectations: https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/hamcrest/expectations.html
- Spring Framework 6.2 — MockMvc AssertJ / MockMvcTester JSON support: https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/assertj/assertions.html
- Spring Framework 6.2 — JsonCompareMode API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/json/JsonCompareMode.html
- Spring Framework 6.2 — ContentResultMatchers.json API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/web/servlet/result/ContentResultMatchers.html
- Spring Framework 6.2 — JsonPathResultMatchers API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/web/servlet/result/JsonPathResultMatchers.html
- Spring Framework 6.2 — WebTestClient JSON assertions: https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html
- Jackson Databind — JsonNode / ObjectMapper documentation: https://github.com/FasterXML/jackson-databind
- JSON Schema — Draft 2020-12: https://json-schema.org/draft/2020-12
- JSON Specification — RFC 8259: https://www.rfc-editor.org/rfc/rfc8259
