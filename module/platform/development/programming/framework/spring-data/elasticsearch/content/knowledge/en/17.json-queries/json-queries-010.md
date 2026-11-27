# Testing JSON Structure and Parameterized Queries After Binding

When using `@Query` in Spring Data Elasticsearch, queries are written as JSON strings and can contain placeholders such as `?0` and `?1` to accept parameters from repository methods. Because the query is a string, errors can occur across several layers: invalid JSON syntax, malformed Query DSL structure, field names disagreeing with mappings, parameters placed with the wrong type, or bound values producing unexpected results.

Testing should therefore distinguish two tasks. First, verify the JSON structure and Query DSL declared by the developer. Second, execute the query through Spring Data with real parameters against Elasticsearch to verify binding, data types, and results. Checking only the initial JSON string is not enough to prove the bound query works properly.

## 1. Layers That Require Testing

A parameterized JSON query typically flows through these steps:

```text
@Query JSON template
       |
       v
Spring Data repository method
       |
       |  bind ?0, ?1, ?2 ...
       v
Bound JSON query
       |
       |  send via Elasticsearch client
       v
Elasticsearch Query DSL parser
       |
       v
Execute on index and mapping
       |
       v
Document / aggregation results
```

You can test across the following layers:

| Layer | What to Verify | Example Bug |
|---|---|---|
| JSON syntax | String after substituting sample placeholders is valid JSON | Missing brace, trailing comma, single quotes |
| Query DSL structure | Nodes like `bool`, `term`, `range`, `match`, `sort` sit at the right level | `filter` placed at the wrong level or misspelled query name |
| Parameter binding | Parameters sit in the right position, have the right type, and are encoded safely | Quoted value breaks JSON or parameter order is swapped |
| Mapping | Fields exist and have types compatible with the query | Using `term` on a `text` field when exact matching is needed |
| Semantics | Results are accurate for boundary and negative cases | Confusing `gte` with `gt`, dropping a filter condition |
| Operations | Query runs against the deployed Elasticsearch/client version | API or query type unsupported by the server |

## 2. Declaring `@Query` with Placeholders

Spring Data Elasticsearch supports positional placeholders in JSON queries. `?0` is the first parameter, `?1` is the second parameter, continuing sequentially from 0.

Example searching products by status and price range:

```java
import java.util.List;

import org.springframework.data.elasticsearch.annotations.Query;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    @Query("""
    {
      "bool": {
        "filter": [
          { "term": { "status": "?0" } },
          {
            "range": {
              "priceMinorUnits": {
                "gte": ?1,
                "lt": ?2
              }
            }
          }
        ]
      }
    }
    """)
    List<ProductDocument> findByStatusAndPriceRange(
            String status,
            Long minPrice,
            Long maxPrice);
}
```

In this example:

- `?0` receives `status` and sits inside a JSON string because status is a string.
- `?1` receives `minPrice` and sits at a JSON number position without quotes.
- `?2` receives `maxPrice` and is also a JSON number.

With arguments `("PUBLISHED", 100000L, 500000L)`, the query meaning after binding is:

```json
{
  "bool": {
    "filter": [
      { "term": { "status": "PUBLISHED" } },
      {
        "range": {
          "priceMinorUnits": {
            "gte": 100000,
            "lt": 500000
          }
        }
      }
    ]
  }
}
```

This JSON illustrates the result for that argument set. At runtime, Spring Data performs binding according to the active version's mechanism. Never concatenate JSON strings with `+` to substitute parameters; let the repository binder handle placeholders.

## 3. Placing Placeholders with the Right JSON Types

Placeholders must sit in positions matching the JSON types expected by the query.

| Parameter Type | Typical Placeholder Position | Example |
|---|---|---|
| String | Inside double quotes | `"status": "?0"` |
| Integer/decimal number | Unquoted | `"gte": ?1` |
| Boolean | Unquoted | `"available": ?2` |
| Date/time string | Inside double quotes | `"gte": "?3"` |
| Array/collection | At the value position of a JSON array/`terms` as supported by binding | `"terms": {"category": ?4}` |

These positional examples illustrate the desired JSON types. Verify binding support for specific data types in your project's Spring Data Elasticsearch version, especially for collections, objects, and date/time types.

### Strings Must Be Bound as JSON Values

Suppose the parameter is:

```text
PUBLISHED "VIP"
```

If manually concatenated into JSON, the inner double quotes break syntax. With placeholders, pass the value as a repository method argument so Spring Data handles it through its binding mechanism.

Do not write:

```java
String json = "{\"term\":{\"status\":\"" + status + "\"}}";
```

Concatenation like this easily causes escaping bugs and lets input data be interpreted as part of the query structure. Use `@Query` placeholders or query builder APIs to separate data from query structure.

### Do Not Misplace Quotes Around Numbers and Booleans

This is a JSON number:

```json
{ "gte": 100 }
```

This is a JSON string:

```json
{ "gte": "100" }
```

The two forms are not equivalent. If the mapping is `long`, bind the number as a JSON number. Likewise, Booleans must be unquoted `true`/`false`, while dates/times are typically ISO-8601 strings parsed by a `date` mapping.

## 4. Validating JSON Templates Before Calling Elasticsearch

A JSON template with string placeholders such as `"?0"` can still parse as JSON before binding because `?0` sits inside a JSON string. However, an unquoted numeric placeholder written as `?1` means the template is not yet complete JSON.

Therefore, when verifying JSON structure, build a sample instance using JSON-encoded sample values and parse it with a JSON library. This verifies syntax and node locations, though it does not replace integration tests against Spring Data's actual binder.

Example with Jackson:

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper();

String template = """
{
  "bool": {
    "filter": [
      { "term": { "status": "?0" } },
      { "range": { "priceMinorUnits": { "gte": ?1, "lt": ?2 } } }
    ]
  }
}
""";

String sampleJson = template
    .replace("\"?0\"", mapper.writeValueAsString("PUBLISHED"))
    .replace("?1", mapper.writeValueAsString(100000L))
    .replace("?2", mapper.writeValueAsString(500000L));

JsonNode root = mapper.readTree(sampleJson);
```

This test uses sample values to produce valid JSON. In real projects, avoid writing a generic placeholder-replacer based on simple `String.replace` calls if templates might contain strings colliding with `?1` or placeholders in varied contexts. Keep templates small, restrict such helpers strictly to test fixtures, or verify structure via integration tests. Never use such a helper in production code to replace Spring Data's binding mechanism.

### Verifying Structure with JSON Pointer

After parsing, you can assert that key nodes exist and have the right types:

```java
import static org.assertj.core.api.Assertions.assertThat;

assertThat(root.at("/bool/filter").isArray()).isTrue();
assertThat(root.at("/bool/filter/0/term/status").asText())
    .isEqualTo("PUBLISHED");
assertThat(root.at("/bool/filter/1/range/priceMinorUnits/gte").isNumber())
    .isTrue();
assertThat(root.at("/bool/filter/1/range/priceMinorUnits/lt").asLong())
    .isEqualTo(500000L);
```

Path-based assertions catch fields placed at the wrong nesting level or numbers accidentally turned into strings. For larger queries, also verify `must`, `must_not`, `should`, `sort`, `aggs`, and `minimum_should_match`.

## 5. Verifying the Corresponding Mapping

A valid JSON query can still fail when fields are missing or have incompatible types. For instance, `term` is typically used for `keyword` fields, Booleans, or exact numeric values; `range` is used with numbers and dates.

Sample document:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Long)
    private Long priceMinorUnits;

    @Field(type = FieldType.Boolean)
    private Boolean available;

    // Constructors, getters and setters
}
```

The corresponding mapping requires:

```json
{
  "properties": {
    "status": { "type": "keyword" },
    "priceMinorUnits": { "type": "long" },
    "available": { "type": "boolean" }
  }
}
```

You can inspect the live mapping via:

```http
GET /products/_mapping
```

Do not inspect only Java annotations. An index may have been created by an older version of the application or managed externally; the live Elasticsearch mapping is what the query actually runs against.

## 6. Testing Repositories Against Real Elasticsearch

Integration testing is the most direct way to confirm that Spring Data binds parameters properly, sends valid queries, and gets expected results from Elasticsearch. Use a dedicated test Elasticsearch instance, such as a container pinned to a version compatible with your project's Spring Data and client versions.

Example repository:

```java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    @Query("""
    {
      "bool": {
        "filter": [
          { "term": { "status": "?0" } },
          {
            "range": {
              "priceMinorUnits": {
                "gte": ?1,
                "lt": ?2
              }
            }
          }
        ]
      }
    }
    """)
    List<ProductDocument> findByStatusAndPriceRange(
            String status,
            Long minPrice,
            Long maxPrice);
}
```

Tests should prepare documents both inside and outside range boundaries:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;

@SpringBootTest
class ProductRepositoryQueryTest {

    @Autowired
    ProductRepository repository;

    @Autowired
    ElasticsearchOperations operations;

    @BeforeEach
    void setUp() {
        IndexOperations index = operations.indexOps(ProductDocument.class);
        if (index.exists()) {
            index.delete();
        }
        index.createWithMapping();

        repository.saveAll(List.of(
            product("p-1", "PUBLISHED", 100L),
            product("p-2", "PUBLISHED", 499L),
            product("p-3", "PUBLISHED", 500L),
            product("p-4", "DRAFT", 250L)
        ));

        index.refresh();
    }

    @Test
    void bindsStringAndNumericParameters() {
        List<ProductDocument> result =
            repository.findByStatusAndPriceRange("PUBLISHED", 100L, 500L);

        assertThat(result)
            .extracting(ProductDocument::getId)
            .containsExactlyInAnyOrder("p-1", "p-2");
    }

    private ProductDocument product(String id, String status, long price) {
        ProductDocument document = new ProductDocument();
        document.setId(id);
        document.setStatus(status);
        document.setPriceMinorUnits(price);
        return document;
    }
}
```

The example calls `index.refresh()` after loading fixtures so searches see documents immediately in tests. In production, avoid manual refreshes after every write because they can reduce indexing throughput. Tests must run against a real Elasticsearch server or compatible container rather than only mocking the repository, since mocks do not verify Query DSL or server-side mappings.

## 7. Testing Parameters with Special Characters

An important test is passing strings containing double quotes, backslashes, Unicode, or valid control characters. The goal is to confirm the value is bound as a JSON string without altering query structure.

Example indexing a document whose status contains quotes:

```java
@Test
void bindsStringContainingQuotesAsAValue() {
    String unusualStatus = "PUBLISHED \"VIP\"";

    ProductDocument document = product("p-quote", unusualStatus, 200L);
    repository.save(document);
    operations.indexOps(ProductDocument.class).refresh();

    List<ProductDocument> result =
        repository.findByStatusAndPriceRange(unusualStatus, 100L, 300L);

    assertThat(result)
        .extracting(ProductDocument::getId)
        .contains("p-quote");
}
```

This test confirms string parameters are handled properly when data contains special characters. You can also add Unicode strings such as `Đà Nẵng`, decomposed Vietnamese diacritics, or `\\` characters if such values appear in real data.

Do not verify solely by asserting that the JSON string contains a substring. The same substring can appear in the wrong position or with the wrong type. Parse the JSON and assert nodes by path, then verify results with integration tests.

## 8. Testing Range Parameters and Boundaries

Range queries commonly suffer from confusing `gt`/`gte` or `lt`/`lte`. Prepare data right on both boundaries and immediately inside/outside the interval.

Given the query:

```json
{
  "range": {
    "priceMinorUnits": {
      "gte": 100,
      "lt": 500
    }
  }
}
```

Expected results:

| Value | Returned? | Reason |
|---:|---|---|
| 99 | No | Less than lower bound |
| 100 | Yes | `gte` includes lower bound |
| 499 | Yes | Within range |
| 500 | No | `lt` excludes upper bound |
| 501 | No | Greater than upper bound |

For dates and times, similarly test half-open intervals `[from, to)`. Create documents right at `from`, immediately before `to`, and right at `to` to catch time zone or boundary bugs.

## 9. Testing Lists and Empty Parameters

If a query uses `terms` or collection parameters, test:

- A single-element list.
- A multi-element list.
- An empty list.
- A list with duplicate elements.
- A list containing null elements if DTOs can produce that case.

Never assume an empty list means “skip the filter”. If the API defines an empty list as no filtering, omit the condition before calling the repository. If an empty list means no results are permitted, return an empty list immediately or construct an explicit non-matching condition.

For `null` parameters, clarify whether null is a valid value, an omitted condition, or a validation error. Placeholders do not automatically strip a query branch just because an argument is null. With many optional filters, a custom repository or dynamic Criteria/NativeQuery is usually better suited than a static `@Query` with many placeholders.

## 10. Testing Placeholder Order and Positions

Placeholders start at `?0`, not `?1`. If a method has three parameters, verify:

| Placeholder | Parameter |
|---|---|
| `?0` | First parameter |
| `?1` | Second parameter |
| `?2` | Third parameter |

For example, given:

```java
List<ProductDocument> search(String status, Long minPrice, Long maxPrice);
```

`?0` must be status, `?1` minimum price, and `?2` maximum price. Reordering method parameters without updating the template can create a syntactically valid query with broken semantics.

Give parameters descriptive names, write tests using distinct, easily recognizable values, and assert the returned ID set. Avoid using identical numeric test values because swapped placeholders could go unnoticed.

## 11. Inspecting Bound Queries at the HTTP Level

When you need to see the exact request body the application sends to Elasticsearch, you can observe HTTP requests in test environments. Several approaches:

- Use an HTTP mock server or test proxy to receive requests and record bodies.
- Use HTTP client logging in development environments if the client version supports suitable request logging.
- Use an Elasticsearch test container and verify actual behavior through query results.

When capturing requests, parse the body as JSON and inspect bound values. Do not compare raw strings alone because field order inside JSON objects is insignificant and can vary across client versions.

If using a mock server, configure the exact transport used by Spring Data. Spring Data Elasticsearch via the Elasticsearch Java API Client and older lines using `RestHighLevelClient` use different HTTP stacks; a mock wired for the old client may miss requests from the new client.

Never enable logging of sensitive request bodies or headers in production. Queries can contain personal data, identifiers, tokens, or internal data; when diagnostic logging is necessary, restrict environments, access permissions, and retention time.

## 12. Syntactically Invalid JSON vs. Semantically Invalid Query DSL

These two failure modes should be distinguished:

### Syntactically Invalid JSON

Example error:

```json
{
  'term': {
    'status': 'PUBLISHED',
  }
}
```

JSON requires double quotes for field names and strings and forbids trailing commas after the last item. Use Jackson `readTree` or another JSON parser to catch syntax errors.

### Valid JSON with Invalid Query DSL

Example:

```json
{
  "bool": {
    "filters": [
      { "term": { "status": "PUBLISHED" } }
    ]
  }
}
```

This JSON parses cleanly, yet the proper property on a bool query is `filter`, not `filters`. Only Elasticsearch's Query DSL parser fully verifies query structure and supported query types.

### Valid Query DSL with Unsuitable Mapping

For instance, a `term` query on a `text` field is valid Query DSL, yet it may fail to match as expected because the field is analyzed. Cross-check against the mapping and indexed data.

## 13. Bound Queries Can Be Valid Yet Still Return Wrong Results

A query that parses without errors does not guarantee correct business results. Common cases:

- `gte` and `gt` confused.
- `must_not` unexpectedly matching documents missing the field.
- `should` without `minimum_should_match` inside a bool query that also has filter/must, making the OR branch only boost scores rather than acting as a requirement.
- Query targeting a `text` field when exact matching was intended.
- Date ranges computed in UTC when users expect local calendar days.
- Swapped parameter positions, such as min and max reversed.
- Empty lists or nulls interpreted differently from business rules.

Therefore, tests should assert returned results by ID or key fields, not merely assert that the repository threw no exception.

## 14. Organizing the Test Suite

Tests can be divided into layers:

| Test Type | Scope | Purpose |
|---|---|---|
| JSON structure test | Templates and sample placeholders | Catch syntax errors, misplaced nodes, or wrong JSON types |
| Repository integration test | Repository + Elasticsearch test server | Verify real binding, mappings, and Query DSL |
| Boundary test | Values right at numeric/date edges | Verify `gt`, `gte`, `lt`, `lte` |
| Special-character test | Strings with quotes, backslashes, Unicode | Verify string binding and encoding |
| Negative test | Missing fields, nulls, empty lists, non-matching states | Verify exclusion conditions and edge cases |
| Compatibility test | Deployed server/client versions | Catch API and Query DSL differences |

You do not need a separate test class for every row. Group them by repository or use case while keeping each test focused on a single clear behavior.

## 15. Complete Repository Test Suite Example

A minimal test suite should include:

```java
@Test
void returnsOnlyDocumentsMatchingStatusAndHalfOpenPriceRange() {
    List<ProductDocument> result =
        repository.findByStatusAndPriceRange("PUBLISHED", 100L, 500L);

    assertThat(result)
        .extracting(ProductDocument::getId)
        .containsExactlyInAnyOrder("p-1", "p-2");
}

@Test
void returnsNoDocumentsWhenStatusDoesNotMatch() {
    List<ProductDocument> result =
        repository.findByStatusAndPriceRange("ARCHIVED", 100L, 500L);

    assertThat(result).isEmpty();
}

@Test
void excludesUpperRangeBoundary() {
    List<ProductDocument> result =
        repository.findByStatusAndPriceRange("PUBLISHED", 100L, 500L);

    assertThat(result)
        .extracting(ProductDocument::getId)
        .doesNotContain("p-3");
}
```

These tests assume fixtures have been loaded and refreshed as shown earlier. They verify placeholders, status filtering, range bounds, and upper-bound exclusion together.

## 16. Common Mistakes

### JSON Template Parses, Yet Bound Query Breaks

A template can parse when a placeholder sits inside a string, yet the bound value contains quotes or escape characters. Verify special characters with integration tests using the real binder.

### Putting Numbers Inside Quotes

Values become JSON strings while the mapping is numeric. Put numeric placeholders in unquoted positions and pass appropriate Java numeric types.

### Misaligned Placeholder Order

Changing a method signature while forgetting to update `?0`, `?1` leaves the query valid but filters incorrectly. Use distinct test values and assert IDs.

### Using Manual String Concatenation

Splicing input straight into JSON breaks escaping and mixes data with query structure. Use placeholders or a query builder.

### Testing Only with Mocked Repositories

Mocks only verify that code calls a method; they do not check binding, mappings, or Query DSL. Run integration tests against a compatible Elasticsearch instance.

### Checking Only That Requests Succeed Without Errors

A query can run successfully yet return the wrong set of documents. Prepare positive, negative, and boundary fixtures and assert specific results.

### Forgetting to Refresh Test Fixtures

Searches may not see newly written documents due to the refresh interval. In tests, refresh the index after loading fixtures or use an appropriate refresh policy.

## 17. Recommended Testing Workflow

When adding or editing a parameterized `@Query`, follow this sequence:

1. Draft a sample Query DSL with clear field names and bool structure.
2. Identify each parameter type and placeholder position starting at `?0`.
3. Place string, numeric, Boolean, and date/time placeholders with the right JSON types.
4. Parse a representative bound JSON sample to catch structural mistakes.
5. Cross-check field names and data types against the actual mapping.
6. Run repository integration tests against a compatible Elasticsearch version.
7. Test strings with special characters, nulls/empty lists, and out-of-bounds parameters.
8. Assert the returned document set rather than merely checking that the call succeeded.
9. When diagnosing issues, capture the HTTP body in a test environment and parse it as JSON to inspect bound values.
10. Keep tests running in CI against a version-pinned Elasticsearch image.

## 18. Conclusion

With `@Query`, verify both the JSON template and the query after Spring Data binds parameters. Placeholders `?0`, `?1` are 0-indexed and must sit in positions matching their JSON types: strings inside quotes, numbers and Booleans unquoted, and dates/times formatted according to the mapping. Never concatenate user input directly into JSON.

JSON parsers catch syntax mistakes and structural tests confirm nodes are in the right places. However, only integration tests against Elasticsearch verify real binding, mappings, Query DSL, and results. Test boundary values, special strings, nulls, empty lists, and parameter order; when you need to inspect the final request, capture the HTTP body in a test environment and parse it as JSON rather than comparing raw strings. This multi-layered testing catches both syntax errors and valid queries with broken semantics.
