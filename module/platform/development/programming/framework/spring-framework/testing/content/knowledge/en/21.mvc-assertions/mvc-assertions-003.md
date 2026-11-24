# JSONPath for Asserting Fields and Collections

When testing a Spring MVC endpoint that returns JSON with MockMvc, verifying only the HTTP status is not enough. A response can return 200 OK while still missing fields, having wrong values, using the wrong object structure, or containing an incorrect collection. JSONPath lets you target specific parts of a JSON document to accurately verify those fields and collections.

Spring provides JSONPath matchers via `MockMvcResultMatchers.jsonPath(...)`. You can combine them with `andExpect(...)` to assert field values, data types, path existence, array sizes, or elements matching specific conditions.

## 1. What Is JSONPath?

JSONPath is an expression language for querying data inside a JSON structure. You can think of JSONPath like using CSS selectors to pick elements in HTML, except the queried targets here are JSON objects and arrays.

Consider the sample response:

~~~json
{
  "orderId": 101,
  "status": "CONFIRMED",
  "customer": {
    "name": "Nguyễn An",
    "vip": true
  },
  "items": [
    {
      "sku": "BOOK-01",
      "name": "Spring Guide",
      "quantity": 2,
      "unitPrice": 120000
    },
    {
      "sku": "PEN-02",
      "name": "Notebook Pen",
      "quantity": 1,
      "unitPrice": 20000
    }
  ],
  "tags": ["new", "priority"],
  "total": 260000,
  "note": null
}
~~~

Commonly used JSONPath expressions:

| Expression | Meaning | Result in Sample JSON |
|---|---|---|
| `$` | Root, i.e., the entire JSON document. | The entire order object. |
| `$.orderId` | The orderId field at the root. | `101`. |
| `$.customer.name` | The name field inside customer. | `"Nguyễn An"`. |
| `$['orderId']` | Access field using bracket syntax. | `101`. |
| `$.items[0]` | First element of the items array. | The BOOK-01 object. |
| `$.items[0].sku` | sku of the first element. | `"BOOK-01"`. |
| `$.items[*].sku` | The sku field of every element in the array. | List of BOOK-01, PEN-02. |
| `$.tags[1]` | Element at index 1. | `"priority"`. |
| `$.items[?(@.quantity > 1)]` | Elements with quantity greater than 1. | The BOOK-01 object. |

In JSONPath, array indices start at 0. The `@` symbol in filter expressions represents the current element being evaluated. Expressions can be chained to traverse from the root object into nested objects, and then to a field or array element.

## 2. Using JSONPath in MockMvc

Common static imports:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
~~~

A basic test can verify status, Content-Type, and a JSON field:

~~~java
mockMvc.perform(get("/orders/101"))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
    .andExpect(jsonPath("$.orderId").value(101))
    .andExpect(jsonPath("$.status").value("CONFIRMED"));
~~~

`jsonPath(expression)` creates a `ResultMatcher`. When MockMvc executes the response, the matcher parses the JSON content and evaluates the given expression. If the expression finds no data or the value does not match, the test fails immediately at that assertion.

Assert status and Content-Type before data fields so failures are easy to interpret: did the request hit the right endpoint, did the response have the right content type, and only then check the JSON structure.

## 3. Asserting Root and Nested Object Fields

For JSON objects, use dot notation to traverse properties:

~~~java
mockMvc.perform(get("/orders/101"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.orderId").value(101))
    .andExpect(jsonPath("$.status").value("CONFIRMED"))
    .andExpect(jsonPath("$.customer.name").value("Nguyễn An"))
    .andExpect(jsonPath("$.customer.vip").value(true));
~~~

For example:

- `$.orderId` reads the orderId field at the root.
- `$.customer.name` traverses into the customer object and reads name.
- `$.customer.vip` reads a boolean value.

If property names contain hyphens, spaces, or characters inconvenient for dot notation, use bracket notation:

~~~json
{
  "order-id": "ORD-101",
  "metadata": {
    "source-system": "web-store"
  }
}
~~~

~~~java
mockMvc.perform(get("/orders/101"))
    .andExpect(jsonPath("$['order-id']").value("ORD-101"))
    .andExpect(jsonPath("$.metadata['source-system']").value("web-store"));
~~~

Bracket notation is also useful when field names are dynamic or collide with special characters. In a JSONPath expression, key names must match the serialized JSON response, not necessarily the Java field names if the application uses Jackson annotations to rename them.

## 4. Asserting Elements in an Array

JSON arrays are accessed by index:

~~~java
mockMvc.perform(get("/orders/101"))
    .andExpect(jsonPath("$.items[0].sku").value("BOOK-01"))
    .andExpect(jsonPath("$.items[0].quantity").value(2))
    .andExpect(jsonPath("$.items[1].sku").value("PEN-02"));
~~~

Indexing is appropriate when element order is part of the API contract. If order is not guaranteed, hard-coding `[0]` and `[1]` couples the test to an unstable detail. In that case, assert the whole collection using wildcards and matchers.

### Wildcard to Extract a Field from Every Element

The `[*]` notation selects all elements of an array:

~~~java
import static org.hamcrest.Matchers.contains;

mockMvc.perform(get("/orders/101"))
    .andExpect(jsonPath("$.items[*].sku",
        contains("BOOK-01", "PEN-02")));
~~~

The expression `$.items[*].sku` returns the collection of sku values. The `contains` matcher asserts both values and order. If you only care that the values appear regardless of order, use `containsInAnyOrder`:

~~~java
import static org.hamcrest.Matchers.containsInAnyOrder;

mockMvc.perform(get("/orders/101"))
    .andExpect(jsonPath("$.items[*].sku",
        containsInAnyOrder("PEN-02", "BOOK-01")));
~~~

### Checking Collection Size

You can assert that an array has an exact number of elements:

~~~java
import static org.hamcrest.Matchers.hasSize;

mockMvc.perform(get("/orders/101"))
    .andExpect(jsonPath("$.items").isArray())
    .andExpect(jsonPath("$.items").value(hasSize(2)))
    .andExpect(jsonPath("$.tags").value(hasSize(2)));
~~~

Other commonly used matchers:

~~~java
import static org.hamcrest.Matchers.hasItem;
import static org.hamcrest.Matchers.everyItem;
import static org.hamcrest.Matchers.anyOf;
import static org.hamcrest.Matchers.startsWith;

mockMvc.perform(get("/orders/101"))
    .andExpect(jsonPath("$.tags", hasItem("priority")))
    .andExpect(jsonPath("$.items[*].sku",
        everyItem(anyOf(startsWith("BOOK-"), startsWith("PEN-")))));
~~~

The example above demonstrates verifying membership in a collection and asserting a rule across every element. When combining matchers, choose conditions tailored to the endpoint's actual data; avoid overly broad rules that let tests pass even when the response contains invalid data.

## 5. Using Filters to Select Elements by Condition

Filters select elements matching a predicate instead of relying on their position. Common syntax:

~~~text
$.arrayName[?(@.field == 'value')]
~~~

Where:

- `$.arrayName` selects the array to query.
- `?` starts a filter expression.
- `@` represents each element being evaluated.
- `@.field` accesses a field of that element.

Example selecting only items with quantity greater than 1:

~~~java
import static org.hamcrest.Matchers.contains;

mockMvc.perform(get("/orders/101"))
    .andExpect(jsonPath(
        "$.items[?(@.quantity > 1)].sku",
        contains("BOOK-01")
    ));
~~~

You can look up an element by SKU and assert its related fields:

~~~java
mockMvc.perform(get("/orders/101"))
    .andExpect(jsonPath(
        "$.items[?(@.sku == 'PEN-02')].quantity",
        contains(1)
    ));
~~~

Common operators used in filters:

| Operator | Meaning | Example |
|---|---|---|
| `==` | Equal to | `@.status == 'ACTIVE'` |
| `!=` | Not equal to | `@.status != 'CANCELLED'` |
| `>` | Greater than | `@.quantity > 1` |
| `>=` | Greater than or equal to | `@.price >= 100` |
| `<` | Less than | `@.quantity < 10` |
| `<=` | Less than or equal to | `@.price <= 500` |
| `&&` | Both conditions satisfied | `@.active == true && @.quantity > 0` |
| `||` | At least one condition satisfied | `@.status == 'NEW' || @.status == 'PAID'` |

Example combining two conditions:

~~~java
mockMvc.perform(get("/orders/101"))
    .andExpect(jsonPath(
        "$.items[?(@.quantity > 0 && @.unitPrice >= 100000)].sku",
        contains("BOOK-01")
    ));
~~~

Filters are especially useful for collections whose order is not guaranteed. They let tests express business criteria for elements, such as finding the line item with a specific SKU or finding all elements in the ACTIVE state.

Note: JSONPath in Spring MockMvc is based on the Jayway JsonPath library. Advanced expressions may depend on the library version and JSON provider in use. Prefer basic, readable syntax; for complex filters, keep tests small and verify that expressions work with your project's dependency versions.

## 6. Asserting Empty Collections, Missing Elements, and Null Values

These three situations are distinct:

1. The field is absent from the JSON.
2. The field is present in the JSON with the value `null`.
3. The field is present in the JSON as an empty collection `[]`.

Example:

~~~json
{
  "note": null,
  "tags": [],
  "status": "PENDING"
}
~~~

Spring provides different matchers to check paths:

| Matcher | Meaning |
|---|---|
| `exists()` | The path has a non-null value. |
| `hasJsonPath()` | The path exists, even if its value is null. |
| `doesNotExist()` | No non-null value at the path; satisfied by both a missing field and null. |
| `doesNotHaveJsonPath()` | The path does not exist at all, including when the value is null. |

Example:

~~~java
mockMvc.perform(get("/orders/101"))
    .andExpect(jsonPath("$.status").exists())
    .andExpect(jsonPath("$.note").hasJsonPath())
    .andExpect(jsonPath("$.note").doesNotExist())
    .andExpect(jsonPath("$.missingField").doesNotHaveJsonPath())
    .andExpect(jsonPath("$.tags").isArray())
    .andExpect(jsonPath("$.tags").value(hasSize(0)));
~~~

In this example, `note` is present in the JSON with a null value. Therefore `hasJsonPath()` passes, `exists()` fails, and `doesNotExist()` passes. The `missingField` key does not appear, so `doesNotHaveJsonPath()` passes.

If business logic requires distinguishing null from a missing field, use `hasJsonPath()` and `doesNotHaveJsonPath()` accordingly. Do not use `doesNotExist()` to prove a key is completely absent, because that matcher also accepts null values.

For an empty collection, the field still exists and its value is an array. You can combine `isArray()` with `hasSize(0)` to assert both the data type and element count.

## 7. Asserting Data Types

JSON has object, array, string, number, boolean, and null types. Spring provides data type matchers for JSONPath:

~~~java
mockMvc.perform(get("/orders/101"))
    .andExpect(jsonPath("$.orderId").isNumber())
    .andExpect(jsonPath("$.status").isString())
    .andExpect(jsonPath("$.customer").isMap())
    .andExpect(jsonPath("$.customer.vip").isBoolean())
    .andExpect(jsonPath("$.items").isArray());
~~~

These matchers are useful when the API contract specifies exact data types. For instance, a quantity field must be a JSON number; if the backend accidentally serializes it as the string `"2"`, loose value checks might not clearly surface the type mismatch.

You can combine type and value assertions:

~~~java
mockMvc.perform(get("/orders/101"))
    .andExpect(jsonPath("$.customer.vip").isBoolean())
    .andExpect(jsonPath("$.customer.vip").value(true))
    .andExpect(jsonPath("$.total").isNumber())
    .andExpect(jsonPath("$.total").value(260000));
~~~

Values like `false`, `0`, and empty strings are still existing values. Do not confuse them with missing or null fields:

~~~java
mockMvc.perform(get("/settings"))
    .andExpect(jsonPath("$.enabled").exists())
    .andExpect(jsonPath("$.enabled").value(false))
    .andExpect(jsonPath("$.retryCount").exists())
    .andExpect(jsonPath("$.retryCount").value(0))
    .andExpect(jsonPath("$.description").exists())
    .andExpect(jsonPath("$.description").value(""));
~~~

## 8. Asserting Root Arrays and Nested Collections

Not every JSON response starts with an object. An endpoint may return an array directly:

~~~json
[
  {"id": 1, "name": "An"},
  {"id": 2, "name": "Bình"}
]
~~~

When the root is an array, use `$[index]` or `$[*]`:

~~~java
mockMvc.perform(get("/customers"))
    .andExpect(jsonPath("$").isArray())
    .andExpect(jsonPath("$").value(hasSize(2)))
    .andExpect(jsonPath("$[0].id").value(1))
    .andExpect(jsonPath("$[*].name",
        contains("An", "Bình")));
~~~

For nested collections, chain array and object levels:

~~~json
{
  "groups": [
    {
      "name": "A",
      "members": [
        {"id": 10, "active": true},
        {"id": 11, "active": false}
      ]
    },
    {
      "name": "B",
      "members": [
        {"id": 20, "active": true}
      ]
    }
  ]
}
~~~

~~~java
mockMvc.perform(get("/groups"))
    .andExpect(jsonPath("$.groups[0].members[0].id").value(10))
    .andExpect(jsonPath("$.groups[*].name",
        contains("A", "B")))
    .andExpect(jsonPath("$.groups[1].members").value(hasSize(1)));
~~~

Indexed paths are appropriate for fixed structures or meaningful ordering. Wildcards are appropriate when verifying a property across all elements of a collection.

## 9. Combining JSONPath with Hamcrest

MockMvc allows passing Hamcrest matchers into JSONPath for more flexible checks than single-value equality.

Useful matchers:

| Matcher | Purpose |
|---|---|
| `is(value)` | Compare value. |
| `not(value)` | Assert value differs from a specific value. |
| `notNullValue()` | Assert non-null. |
| `hasSize(n)` | Assert collection size. |
| `hasItem(value)` | Assert collection contains element. |
| `contains(a, b)` | Assert elements in exact order. |
| `containsInAnyOrder(a, b)` | Assert elements regardless of order. |
| `greaterThan(n)` | Assert number is greater than threshold. |
| `lessThan(n)` | Assert number is less than threshold. |
| `startsWith(text)` | Assert string starts with prefix. |
| `everyItem(matcher)` | Assert every element satisfies matcher. |

Example:

~~~java
import static org.hamcrest.Matchers.greaterThan;
import static org.hamcrest.Matchers.hasItem;
import static org.hamcrest.Matchers.not;
import static org.hamcrest.Matchers.notNullValue;
import static org.hamcrest.Matchers.startsWith;

mockMvc.perform(get("/orders/101"))
    .andExpect(jsonPath("$.status", not("CANCELLED")))
    .andExpect(jsonPath("$.customer.name", notNullValue()))
    .andExpect(jsonPath("$.total", greaterThan(0)))
    .andExpect(jsonPath("$.items[*].sku", hasItem(startsWith("BOOK-"))));
~~~

With collection matchers, remember that JSONPath wildcards typically produce a list of results. Therefore, the matcher applies to the list of selected values, not to each root object individually. If you want to inspect individual objects, select the appropriate field or use a filter expression.

## 10. Asserting Numbers and Java Types

JSON numbers may be mapped to different Java types depending on the JSON provider and specific value. For example, small integers are often read as Integer, while decimals may become Double. Numeric assertions should therefore clearly state what is being verified:

~~~java
mockMvc.perform(get("/orders/101"))
    .andExpect(jsonPath("$.total").value(260000))
    .andExpect(jsonPath("$.items[0].unitPrice").value(120000));
~~~

When asserting floating-point numbers within a tolerance, use a numeric matcher:

~~~java
import static org.hamcrest.Matchers.closeTo;

mockMvc.perform(get("/products/1"))
    .andExpect(jsonPath("$.rating", closeTo(4.5, 0.01)));
~~~

If you need to coerce to a specific Java type before the matcher compares values, Spring provides an overload accepting a target type:

~~~java
import java.math.BigDecimal;
import static org.hamcrest.Matchers.comparesEqualTo;

mockMvc.perform(get("/products/1"))
    .andExpect(jsonPath(
        "$.price",
        comparesEqualTo(new BigDecimal("125000.00")),
        BigDecimal.class
    ));
~~~

The target-type overload converts the JSONPath result to the desired type before applying the matcher. This is useful when exact BigDecimal comparisons are needed or when the JSON provider's default numeric type differs from the type expected in the test.

Do not use string comparisons for every numeric value, such as comparing `"260000"` against a JSON number `260000`. JSON strings and JSON numbers are different types; tests should enforce the exact types of the API contract.

## 11. JSONPath vs. Full JSON Comparison

JSONPath is suitable when you only need to assert certain fields or parts of a collection. If you need to assert the entire response structure, MockMvc also provides `content().json(...)`.

Example:

~~~java
mockMvc.perform(get("/health"))
    .andExpect(status().isOk())
    .andExpect(content().json("""
        {
          "status": "UP",
          "database": "UP"
        }
        """));
~~~

Full JSON comparison works well when the response is small and the contract requires specific fields and structure. JSONPath works better when the response is large, contains dynamic fields, or only a few attributes matter to the test.

Both approaches can be combined:

~~~java
mockMvc.perform(get("/orders/101"))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
    .andExpect(jsonPath("$.orderId").value(101))
    .andExpect(jsonPath("$.items").isArray())
    .andExpect(jsonPath("$.items").value(hasSize(2)));
~~~

Avoid repeating every field with JSONPath if the real goal is to verify the entire response. Conversely, avoid snapshotting the entire JSON if the test only needs to verify a few behaviors and the response includes metadata that changes over time.

## 12. A Comprehensive Test Example

Suppose the endpoint `GET /orders/{id}` returns an order object like the sample JSON at the start of this guide. A test can verify status, nested fields, data types, arrays, filters, and null values:

~~~java
import static org.hamcrest.Matchers.contains;
import static org.hamcrest.Matchers.hasSize;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

class OrderControllerTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void returnsOrderWithExpectedFieldsAndItems() throws Exception {
        mockMvc.perform(get("/orders/{id}", 101))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.orderId").value(101))
            .andExpect(jsonPath("$.status").value("CONFIRMED"))
            .andExpect(jsonPath("$.customer.name").value("Nguyễn An"))
            .andExpect(jsonPath("$.customer.vip").value(true))
            .andExpect(jsonPath("$.items").isArray())
            .andExpect(jsonPath("$.items").value(hasSize(2)))
            .andExpect(jsonPath("$.items[*].sku",
                contains("BOOK-01", "PEN-02")))
            .andExpect(jsonPath(
                "$.items[?(@.quantity > 1)].sku",
                contains("BOOK-01")
            ))
            .andExpect(jsonPath("$.total").value(260000))
            .andExpect(jsonPath("$.note").hasJsonPath())
            .andExpect(jsonPath("$.note").doesNotExist());
    }
}
~~~

This test illustrates multiple assertion types on a single response. In a real project, the test class needs to be configured to provide MockMvc, such as using `@WebMvcTest(OrderController.class)` or a MockMvc setup suitable for the test type. When using `@WebMvcTest`, the controller's service dependencies must be mocked or imported per the application's configuration.

## 13. Common Mistakes When Writing JSONPath Assertions

### Forgetting the Root Symbol `$`

Expressions normally start from the root:

~~~java
jsonPath("$.customer.name")
~~~

If the root is omitted or the path is mistyped, the matcher may fail to find the data.

### Mistakenly Using 1-Based Indexing

JSON arrays are 0-indexed. `$.items[0]` is the first element, and `$.items[1]` is the second element.

### Using Indices When Order Is Not Part of the Contract

If the API does not guarantee collection order, asserting `[0]` and `[1]` creates flaky tests when data is ordered differently. Use wildcards, filters, or order-independent matchers instead.

### Confusing a Null Field with a Missing Field

`doesNotExist()` accepts both absent fields and fields with null values. To prove a field is absent, use `doesNotHaveJsonPath()`. To assert a field is present even if null, use `hasJsonPath()`.

### Checking Only Count Without Checking Content

`hasSize(2)` only confirms there are two elements. It does not prove they are the right two elements. When the contract specifies particular items, combine size checks with `contains`, `containsInAnyOrder`, `hasItem`, or filters.

### Checking Only Values While Ignoring Types

JSON numbers and JSON strings are distinct. If the API requires a number, add `isNumber()` or an appropriate type assertion; if it requires a boolean, verify with `isBoolean()`.

### Writing Overly Complex JSONPath Expressions

A long expression combining multiple filters can be hard to read and hard to diagnose when it fails. Split it into smaller assertions or verify elements with simpler expressions. Each assertion should express a meaningful condition of the API contract.

### Confusing JSONPath Keys with Java Property Names

JSONPath queries the JSON after serialization. If Jackson renames a field with `@JsonProperty`, the expression must use the key name appearing in the JSON response, not the Java field name.

## 14. Choosing the Right Assertion

When asserting MVC results, start from the actual JSON structure and the question the test needs to answer:

1. Use `$.field` to assert root-level fields.
2. Use `$.parent.child` or bracket notation to access nested objects and special keys.
3. Use `$[0]` or `$.items[0]` when array position is part of the contract.
4. Use `[*]` and Hamcrest matchers when checking an entire collection.
5. Use filters `[?(@.field == value)]` to locate elements by condition.
6. Use `exists()`, `hasJsonPath()`, `doesNotExist()`, and `doesNotHaveJsonPath()` to distinguish non-null values, null values, and missing paths.
7. Use `isArray()`, `isMap()`, `isString()`, `isNumber()`, and `isBoolean()` to verify data types.
8. Use `content().json(...)` when you need to assert an entire small, stable JSON response.

JSONPath keeps MockMvc tests focused on the data the client actually receives after Spring MVC processes and serializes the response. Choosing the right paths, matchers, and level of strictness enables tests to catch defects in values, structure, data types, and collection contents.
