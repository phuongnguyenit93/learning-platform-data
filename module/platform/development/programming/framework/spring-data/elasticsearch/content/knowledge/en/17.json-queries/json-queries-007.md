# Organizing JSON Queries in Testable Configuration Resources

When an application uses many Elasticsearch queries, placing all Query DSL inside annotations or concatenating JSON strings directly inside services makes code hard to read and hard to test. A better way to organize them is to store stable Query DSL in JSON files on the classpath, load them through a dedicated component, and pass them to Spring Data Elasticsearch for execution.

This approach separates three responsibilities: **JSON resources describe the query structure**, **Java supplies parameters and orchestrates execution**, and **tests verify both structure and behavior of the queries**. As a result, the team can review query changes just like source code changes, validate JSON independently, and run integration tests against Elasticsearch.

This article focuses on JSON queries managed as configuration resources. The examples use `StringQuery` and `ElasticsearchOperations` to execute Query DSL. For queries that need type-safe builders, advanced sorting, or newer Elasticsearch Java API Client features, you can choose `NativeQuery` or a client API compatible with your project version.

## 1. Why Separate Query DSL from Services?

### 1.1. Inline Queries Are Quick but Hard to Maintain

A simple query can be written inline:

~~~java
Query query = new StringQuery("""
{
  "bool": {
    "must": [
      { "match": { "name": "wireless keyboard" } }
    ],
    "filter": [
      { "term": { "category": "ACCESSORY" } }
    ]
  }
}
""");
~~~

For a small query, this is easy to follow. As a query grows with more `must`, `should`, `filter`, `range`, `nested`, `highlight`, or optional conditions, the service can end up holding a massive JSON block.

Common problems quickly appear:

- Business logic and Query DSL structure are tangled in the same method.
- It is hard to review query changes when surrounding Java code also changes heavily.
- Reusing a query structure across multiple services is difficult.
- String concatenation or editing braces easily introduces malformed JSON.
- Unit tests have to verify both service logic and JSON string details.
- Similar queries get copy-pasted and drift out of sync over time.

### 1.2. JSON Resources Help Manage Query Structure

Queries can be placed under `src/main/resources`:

~~~text
src/
  main/
    java/
      com/example/search/
        ProductSearchService.java
        SearchQueryCatalog.java
    resources/
      elasticsearch/
        queries/
          products-by-name.json
          products-by-category.json
          products-in-price-range.json
~~~

Each file serves a clear purpose. File names can indicate the entity, action, and version if queries need separate lifecycle management.

JSON structure can be reviewed independently. Java is responsible for loading resources, placing parameters into the right positions, and invoking the search API.

### 1.3. Separating Query Structure from Runtime Parameters

A query typically has two parts:

- **Stable structure**: query types, bool branches, searched fields, and how filters combine.
- **Runtime values**: user-entered keywords, selected categories, price ranges, or date ranges.

The JSON resource should describe the stable structure. Java injects runtime values into the JSON tree via a typed API and then serializes it to valid JSON.

Do not use manual string replacement to substitute values into JSON. String splicing easily breaks escaping when values contain double quotes, slashes, or Unicode characters.

## 2. Choosing Resource Format and Location

### 2.1. Placing Files on the Classpath

Example file:

`src/main/resources/elasticsearch/queries/products-by-name.json`

Contents:

~~~json
{
  "bool": {
    "must": [
      {
        "match": {
          "name": {
            "query": "wireless keyboard"
          }
        }
      }
    ],
    "filter": [
      {
        "term": {
          "available": true
        }
      }
    ]
  }
}
~~~

This is the Query DSL section, not the full Search API request body. When using `StringQuery`, the supplied string describes the query clause. Spring Data combines this query with other options such as pageable and sort to build the search request.

If calling the Elasticsearch Validate Query API directly, this query clause goes inside the `query` field of the request body. Distinguish these two forms to avoid wrapping `query` twice.

### 2.2. One File per Query Purpose

Do not dump every application query into one giant JSON file. Split files by domain or use case:

| Resource Name | Purpose |
|---|---|
| `products-by-name.json` | Search products by name content |
| `products-by-category.json` | Filter products by category |
| `products-in-price-range.json` | Filter products by price range |
| `articles-by-text.json` | Search articles by content |
| `orders-by-status.json` | Look up orders by status |

If a query has minor variants sharing the same structure, you can use one template with runtime parameters. If two query structures differ significantly, two separate resources are usually easier to understand and test.

### 2.3. Never Put Secrets in Query Resources

Query files should contain only search structure. Do not store sensitive details such as:

- Elasticsearch username or password.
- API keys or bearer tokens.
- URLs containing credentials.
- Production environment secrets.

Connection details belong in the application's security configuration or secret manager. Query resources are normally packaged inside artifacts and can appear in repositories or build archives.

## 3. Loading JSON Resources in Spring

### 3.1. Using ResourceLoader

Spring `ResourceLoader` lets you read resources from locations such as `classpath:`:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.stereotype.Component;
import org.springframework.util.StreamUtils;

@Component
public class SearchQueryResourceLoader {

    private final ResourceLoader resourceLoader;

    public SearchQueryResourceLoader(ResourceLoader resourceLoader) {
        this.resourceLoader = resourceLoader;
    }

    public String load(String location) {
        Resource resource = resourceLoader.getResource(location);

        try (InputStream input = resource.getInputStream()) {
            return StreamUtils.copyToString(
                input,
                StandardCharsets.UTF_8
            );
        } catch (IOException exception) {
            throw new IllegalStateException(
                "Cannot load Elasticsearch query resource: " + location,
                exception
            );
        }
    }
}
~~~

This works well when queries are packaged inside a JAR and loaded from the classpath. `ResourceLoader` also supports other resource location types, though for queries managed alongside the application, `classpath:` is usually easiest to deploy and test.

### 3.2. Using ObjectMapper to Parse JSON

Reading JSON into a data tree lets Java modify values in a type-safe manner without string concatenation:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Component;

@Component
public class SearchQueryJsonReader {

    private final SearchQueryResourceLoader resourceLoader;
    private final ObjectMapper objectMapper;

    public SearchQueryJsonReader(
            SearchQueryResourceLoader resourceLoader,
            ObjectMapper objectMapper) {
        this.resourceLoader = resourceLoader;
        this.objectMapper = objectMapper;
    }

    public JsonNode read(String location) {
        String json = resourceLoader.load(location);

        try {
            return objectMapper.readTree(json);
        } catch (IOException exception) {
            throw new IllegalStateException(
                "Invalid Elasticsearch query JSON: " + location,
                exception
            );
        }
    }
}
~~~

`JsonNode` represents the JSON data tree. When you need to modify values, create a mutable copy via `deepCopy()` and manipulate it through `ObjectNode` or `ArrayNode`.

Parsing JSON immediately when loading helps catch syntax errors earlier than waiting until a user triggers a search.

### 3.3. Using a Catalog Instead of Having Services Read Files Directly

Services should not have to know file paths, character encodings, stream opening, or JSON parsing details. Create a dedicated catalog:

~~~java
@Component
public class SearchQueryCatalog {

    private final SearchQueryJsonReader reader;

    public SearchQueryCatalog(SearchQueryJsonReader reader) {
        this.reader = reader;
    }

    public JsonNode productByNameTemplate() {
        return reader.read(
            "classpath:elasticsearch/queries/products-by-name.json"
        );
    }
}
~~~

A catalog centralizes resource names and provides a single place to control loading, caching, or query versioning. As the number of queries grows, you can organize catalogs by domain such as Product, Article, or Order.

## 4. Inserting Parameters into JSON Safely

### 4.1. Avoid String Replacement with replace

An error-prone approach looks like:

~~~java
String json = template.replace(
    "__KEYWORD__",
    userInput
);
~~~

If `userInput` contains double quotes or escape characters, the JSON can break. If data is injected into a syntactic position rather than a value position, query structure can be altered.

String replacement is also error-prone when a placeholder appears in multiple locations or collides with real content.

Parse JSON into a tree and use Jackson to write values. Jackson automatically handles string escaping, numeric types, booleans, and nulls in JSON format.

### 4.2. Creating Templates with Clear Parameter Positions

The `products-by-name.json` resource can hold default placeholder values at substitution positions:

~~~json
{
  "bool": {
    "must": [
      {
        "match": {
          "name": {
            "query": ""
          }
        }
      }
    ],
    "filter": []
  }
}
~~~

Java updates the exact node:

~~~java
ObjectNode root = (ObjectNode) template.deepCopy();

ObjectNode matchName = (ObjectNode) root.at(
    "/bool/must/0/match/name"
);

matchName.put("query", keyword);
~~~

`at()` uses JSON Pointer to locate the node. If the resource structure changes and the path no longer exists, catch the mismatch rather than silently building a query missing conditions.

You can write a helper to verify required nodes:

~~~java
private ObjectNode requireObject(
        JsonNode root,
        String pointer) {

    JsonNode node = root.at(pointer);

    if (!(node instanceof ObjectNode objectNode)) {
        throw new IllegalStateException(
            "Expected JSON object at " + pointer
        );
    }

    return objectNode;
}
~~~

Then:

~~~java
ObjectNode matchName = requireObject(
    root,
    "/bool/must/0/match/name"
);
matchName.put("query", keyword);
~~~

### 4.3. Writing Numeric and Boolean Values with Proper Types

For a price range filter, write numbers as JSON numbers:

~~~java
ObjectNode range = requireObject(
    root,
    "/bool/filter/1/range/price"
);

range.put("gte", minimumPrice);
range.put("lte", maximumPrice);
~~~

If `minimumPrice` and `maximumPrice` are `BigDecimal`, Jackson writes them as JSON numbers. Do not convert them with `toString()` and wrap them in double quotes unless the mapping explicitly requires a keyword field.

For booleans:

~~~java
ObjectNode availability = requireObject(
    root,
    "/bool/filter/0/term"
);

availability.put("available", true);
~~~

The value `true` is a JSON boolean, not the string `"true"`.

### 4.4. Adding Optional Filters with ArrayNode

Not every filter is provided on every request. If category is optional, add the clause only when a value is present:

~~~java
ArrayNode filters = (ArrayNode) root.at("/bool/filter");

if (category != null && !category.isBlank()) {
    ObjectNode termBody = objectMapper.createObjectNode();
    termBody.put("category", category);

    ObjectNode termQuery = objectMapper.createObjectNode();
    termQuery.set("term", termBody);

    filters.add(termQuery);
}
~~~

This keeps JSON valid and makes it explicit which filters are included. With many optional filters, you can extract helpers for term, range, and exists queries so the service avoids verbose JSON tree manipulation.

### 4.5. Validating Parameters Before Building Queries

Jackson guarantees valid JSON serialization, not business validity of the query. The service must still validate:

- Keywords are non-empty when the query requires one.
- Price ranges satisfy `minimumPrice <= maximumPrice`.
- Categories belong to the permitted set if business rules require it.
- Start dates are not after end dates.
- Filter counts and input sizes stay within limits.

Never accept arbitrary field names, indices, or DSL fragments from public requests. Restrict selections to controlled configuration lists.

## 5. Creating StringQuery from JSON Resources

### 5.1. Serializing the JSON Tree into a Query String

After updating the JSON tree, serialize it to a string with `ObjectMapper`:

~~~java
String queryJson = objectMapper.writeValueAsString(root);
Query query = new StringQuery(queryJson);
~~~

`StringQuery` takes Query DSL as a JSON string. This JSON is the query clause—such as `bool`, `match`, `term`, or `range`—not the full search request body with an outer `query` key.

### 5.2. Builder Example for Product Queries

Suppose the resource file contains:

~~~json
{
  "bool": {
    "must": [
      {
        "match": {
          "name": {
            "query": ""
          }
        }
      }
    ],
    "filter": []
  }
}
~~~

You can create a dedicated query factory component:

~~~java
@Component
public class ProductQueryFactory {

    private final SearchQueryCatalog catalog;
    private final ObjectMapper objectMapper;

    public ProductQueryFactory(
            SearchQueryCatalog catalog,
            ObjectMapper objectMapper) {
        this.catalog = catalog;
        this.objectMapper = objectMapper;
    }

    public Query byName(String keyword, String category) {
        ObjectNode root = (ObjectNode)
            catalog.productByNameTemplate().deepCopy();

        ObjectNode matchName = requireObject(
            root,
            "/bool/must/0/match/name"
        );
        matchName.put("query", keyword);

        ArrayNode filters = (ArrayNode) root.at("/bool/filter");

        if (category != null && !category.isBlank()) {
            ObjectNode termBody = objectMapper.createObjectNode();
            termBody.put("category", category);

            ObjectNode termQuery = objectMapper.createObjectNode();
            termQuery.set("term", termBody);

            filters.add(termQuery);
        }

        try {
            return new StringQuery(
                objectMapper.writeValueAsString(root)
            );
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException(
                "Cannot serialize product query",
                exception
            );
        }
    }

    private ObjectNode requireObject(
            JsonNode root,
            String pointer) {

        JsonNode node = root.at(pointer);

        if (!(node instanceof ObjectNode objectNode)) {
            throw new IllegalStateException(
                "Expected JSON object at " + pointer
            );
        }

        return objectNode;
    }
}
~~~

This illustrates separation of responsibilities. In a real project, you can extract JSON tree helpers into a shared utility component and keep factories domain-focused.

### 5.3. Executing with ElasticsearchOperations

The service calls the factory and executes the query:

~~~java
@Service
public class ProductSearchService {

    private final ProductQueryFactory queryFactory;
    private final ElasticsearchOperations operations;

    public ProductSearchService(
            ProductQueryFactory queryFactory,
            ElasticsearchOperations operations) {
        this.queryFactory = queryFactory;
        this.operations = operations;
    }

    public SearchHits<ProductDocument> search(
            String keyword,
            String category) {

        Query query = queryFactory.byName(keyword, category);

        return operations.search(
            query,
            ProductDocument.class
        );
    }
}
~~~

The service stays focused on business orchestration. File reading and JSON updates live in the catalog/factory; request execution lives in `ElasticsearchOperations`.

### 5.4. Adding Pagination and Sorting

`StringQuery` is an implementation of Spring Data `Query`, so pagination and sorting options can be attached to the query object:

~~~java
Query query = queryFactory.byName(keyword, category);

query.setPageable(
    PageRequest.of(
        0,
        20,
        Sort.by(Sort.Order.desc("createdAt"))
    )
);

SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class);
~~~

The sort field must have a mapping that supports sorting. If `createdAt` is mapped under a different name or is a text field, use the actual field name and mapping type present in the index.

If a query needs Elasticsearch-specific options like nested sort, script sort, or complex request settings, `NativeQuery` may be a better fit. Do not try to stuff an entire search request into a JSON string for `StringQuery`, because `StringQuery` represents the Query DSL clause inside Spring Data's abstraction.

## 6. Organizing Multiple Query Resources

### 6.1. Splitting by Domain and Purpose

A scalable layout:

~~~text
src/main/resources/
  elasticsearch/
    queries/
      product/
        search-by-name.json
        filter-by-category.json
        price-range.json
      article/
        search-content.json
        search-title.json
      order/
        filter-by-status.json
~~~

File names should reflect the query purpose rather than generic technical names like `query1.json` or `search.json`.

### 6.2. Naming and Versioning Queries

When a query change can noticeably alter results, you can version the resources:

~~~text
product/
  search-by-name-v1.json
  search-by-name-v2.json
~~~

Versioning helps during controlled rollouts or when comparing behavior between two configurations. Do not create a new version for every tiny tweak; use versions when contract or result behavior changes need separate tracking.

### 6.3. Using Configuration to Select Resources, Never Client Paths

If you need to select queries per environment or feature flag, configure resource names in application properties:

~~~yaml
search:
  queries:
    product-by-name: classpath:elasticsearch/queries/product/search-by-name-v1.json
~~~

Java binds the configuration into `@ConfigurationProperties` or injects `Environment`. Resource names must come strictly from trusted configuration.

Never accept paths like `classpath:...` directly from API callers. Letting clients choose arbitrary resource paths can expose unintended resources or run unvetted queries.

### 6.4. When Should Query Templates Be Cached?

If resource files are packaged with the application and never change at runtime, you can load and parse them once and retain templates in memory. Each request must make its own copy before editing:

~~~java
ObjectNode requestQuery = cachedTemplate.deepCopy();
~~~

Never mutate a shared `ObjectNode` across requests. If two concurrent requests update the same query node, one request's parameters can overwrite the other's.

If resources are read from files outside the classpath and can change while the application is running, design explicit cache invalidation or reloading. Do not assume Spring `Resource` automatically watches all file changes.

## 7. Testing JSON Structure Independently

### 7.1. Verifying That Resources Exist and Parse

A unit test should catch missing files or malformed JSON:

~~~java
@SpringBootTest
class SearchQueryResourceTest {

    @Autowired
    private SearchQueryCatalog catalog;

    @Test
    void productQueryTemplateCanBeLoaded() {
        JsonNode template = catalog.productByNameTemplate();

        assertTrue(template.has("bool"));
        assertTrue(template.at("/bool/must").isArray());
        assertTrue(template.at("/bool/filter").isArray());
    }
}
~~~

This test does not require Elasticsearch. It verifies that the resource is packaged and matches the minimal structure expected by the factory.

You can also test without starting a full Spring context by instantiating `ResourceLoader` and `ObjectMapper` directly when testing the catalog in a narrower scope.

### 7.2. Verifying That Values Are Inserted into the Right Nodes

Factory tests should confirm the generated query holds the right data:

~~~java
@Test
void insertsKeywordAndCategoryAsJsonValues() throws Exception {
    Query query = queryFactory.byName(
        "wireless \"keyboard\"",
        "ACCESSORY"
    );

    StringQuery stringQuery = (StringQuery) query;
    JsonNode json = objectMapper.readTree(stringQuery.getSource());

    assertEquals(
        "wireless \"keyboard\"",
        json.at("/bool/must/0/match/name/query").asText()
    );

    assertEquals(
        "ACCESSORY",
        json.at("/bool/filter/0/term/category").asText()
    );
}
~~~

The source getter name and castability may depend on your Spring Data Elasticsearch version's API. If your version does not expose the source via that getter, extract JSON serialization into its own method returning `JsonNode` or a string so you can test it without reaching into `StringQuery` internals.

Testing with embedded double quotes proves Jackson keeps the data as a valid JSON string rather than breaking the query structure.

### 7.3. Testing Optional Filters

If category can be omitted, tests should confirm:

- No category filter is present when the value is null or blank.
- Exactly one category filter is present when a valid value is supplied.
- Fixed filters from the template remain intact.
- No duplicate filters leak across consecutive calls.

Each query build must edit a fresh copy of the template. If a mutated node is accidentally reused, tests invoking the factory repeatedly will catch stale filters lingering across calls.

### 7.4. Comparing JSON Structurally

Do not compare whole JSON payloads as raw strings when key order is insignificant. Parse them into `JsonNode` and compare trees structurally:

~~~java
JsonNode actual = objectMapper.readTree(actualJson);
JsonNode expected = objectMapper.readTree(expectedJson);

assertEquals(expected, actual);
~~~

This ignores insignificant whitespace and object field ordering differences while still catching changes in values, array ordering, and node structure.

## 8. Testing Queries Against Elasticsearch

### 8.1. Validate Query API

Elasticsearch provides the Validate Query API to check whether a query is valid against an index and its mapping:

~~~http
POST /products/_validate/query?explain=true
Content-Type: application/json

{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": {
              "query": "wireless keyboard"
            }
          }
        }
      ],
      "filter": [
        {
          "term": {
            "category": "ACCESSORY"
          }
        }
      ]
    }
  }
}
~~~

The Validate Query API catches invalid queries or mapping-related errors. It does not prove the query returns the right business result set or performs well on production data.

When using a query-clause resource with `StringQuery`, wrap the clause inside a `query` field when calling the Validate Query API directly.

### 8.2. Integration Testing with Real Elasticsearch or Testcontainers

To verify actual search results, run integration tests against an Elasticsearch version compatible with your project.

A baseline scenario:

1. Start a test Elasticsearch instance.
2. Create the index with the required mappings and analyzers.
3. Index a representative set of documents.
4. Call the factory to build a query from the JSON resource.
5. Execute it with `ElasticsearchOperations.search`.
6. Assert returned IDs and document contents.
7. Test values with special characters, Vietnamese diacritics, or boundary values.
8. Test queries with optional filters toggled on and off.
9. Clean up the test index or test data afterward.

JSON unit tests do not replace integration tests. JSON can parse cleanly yet reference non-existent fields, wrong field types, or incompatible analyzers.

### 8.3. Testing Empty-Result Queries and Overly Broad Queries

Tests should cover:

- Queries returning expected results.
- Queries returning zero results.
- Queries with empty or whitespace-only strings.
- Queries with special characters.
- Queries missing mandatory filters.
- Queries at price range boundaries.
- Queries across both text and keyword fields.
- Queries using nested fields if the resource relies on nested mappings.

If a query can generate heavy load, benchmark it on production-scale data. A syntactically valid query can still be far too slow.

## 9. Validating Query Structure and Contracts

### 9.1. Verifying Required Field Paths

The factory relies on JSON Pointers such as:

`/bool/must/0/match/name`

If someone edits the resource to switch `match` to `multi_match` or alters the bool layout, the factory may fail to find the node.

There are two ways to manage this:

- Keep the JSON structure stable and test required paths.
- Make the factory more flexible by locating nodes by name or assembling separate query fragments from multiple resources.

Never let path errors surface only on production requests. Validate structure at startup or in unit tests.

### 9.2. Checking Data Types

Some errors are not JSON syntax errors:

- Using `term` on a text field instead of a keyword field.
- Using `range` on a non-numeric/non-date field.
- Using the wrong `path` in a `nested` query.
- Using `match` for codes that require exact matching.
- Sorting on a field without suitable doc values.

These issues must be checked against actual mappings or integration tests. JSON Schema can validate basic document structure, but it does not replace validation against Elasticsearch mappings.

### 9.3. Managing Query Changes Like Contract Changes

If query resources are critical to your product, review changes just like code:

- State the purpose of the change.
- Review affected fields and analyzers.
- Update structural tests.
- Update integration tests for expected results.
- Measure performance if the query broadens scope or changes operators.
- Document result differences if ranking or filtering behavior shifts.

Do not edit JSON directly on a production cluster without updating the application's source-of-truth resources. If queries diverge in the cluster, other environments will struggle to reproduce the same behavior.

## 10. Separating Query Resources from Sorting and Pagination

### 10.1. Keeping Only Search Conditions in Query JSON

When using `StringQuery`, resources normally hold only the query clause. Sort and pageable can be attached separately on the Spring Data `Query`:

~~~java
Query query = new StringQuery(queryJson);

query.setPageable(
    PageRequest.of(
        0,
        20,
        Sort.by(Sort.Order.desc("createdAt"))
    )
);
~~~

This keeps search conditions inside the JSON file and presentation parameters in Java. It also lets a single query resource be reused across different page sizes or sort orders.

### 10.2. When the Entire Search DSL Belongs in One Resource

A search request may include many elements beyond query:

- `sort`
- `from` and `size`
- `highlight`
- `_source`
- `aggs`
- `track_total_hits`
- `rescore` or other options

If your goal is to manage the entire search request in JSON, `StringQuery` may not be the right abstraction because it represents only the query clause. In that case, consider the Elasticsearch Java API Client or a dedicated adapter translating request JSON into client requests using APIs supported by your version.

Never pass a full search body containing a `query` field into `StringQuery` if the abstraction expects a query clause. Define clear data boundaries for each API.

## 11. Security and Operations

### 11.1. Never Allow Users to Submit Arbitrary DSL

Never accept a complete JSON Query DSL string from a client and forward it straight to Elasticsearch. Doing so can let clients request:

- Overly broad queries.
- Disallowed scripts or regexps.
- Access to internal fields.
- Expensive sorts or aggregations.
- Queries against out-of-scope indices if target index selection is also exposed.

Public APIs should accept strongly typed business parameters. The server chooses the query resource and writes only validated parameters into the target nodes.

### 11.2. Bounding Query Cost

Depending on business needs, consider bounding:

- Keyword length.
- Number of filters.
- Maximum page size.
- Date or price span widths.
- Number of values in `terms` filters.
- Allowed query types.

Query resources do not replace service-layer limits. A valid template can still produce an expensive request if runtime parameters are unconstrained.

### 11.3. Controlled Logging

Logging helps debug queries, but avoid logging sensitive data or unbounded query inputs.

Safe items to log:

- Query resource name or query ID.
- Execution duration.
- Target index or alias chosen from trusted configuration.
- Page size and hit count.
- Error type and correlation ID.

If you need to log DSL, consider masking sensitive values and bounding log payload size. Never log credentials or secrets.

## 12. Common Mistakes

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Resource not found | Wrong classpath location or file not packaged | Check the path and build artifact contents |
| JSON parsing fails | Bad comma, brace, or data type | Parse resources in unit tests |
| Factory cannot find JSON Pointer | Resource structure changed without updating code | Validate required paths and update tests |
| Query fails because field does not exist | JSON field name disagrees with mapping | Check the mapping API and entity metadata |
| Query returns empty results | Incompatible field type, analyzer, or filter value | Inspect `_analyze`, mapping, and Query DSL |
| Quoted string breaks JSON | Substituting placeholders with string concatenation | Use a Jackson tree and serialize |
| Stale filters leak into later requests | Mutating the shared template directly | Call `deepCopy()` per request |
| Numbers treated as text | Writing numbers as strings | Use `ObjectNode.put` with the proper numeric type |
| Valid JSON query rejected by Elasticsearch | DSL incompatible with mapping or version | Use the Validate Query API and integration tests |
| Tests pass but production queries are slow | Dataset size, shard layout, or load differs from tests | Benchmark queries on production-like data and config |
| Query resources differ across environments | Resources modified outside source of truth | Version resources and deploy with the artifact |
| StringQuery receives wrong structure | Full search body passed instead of query clause | Separate query clause from request-level options |

## 13. Recommended Implementation Workflow

A practical workflow consists of:

1. Define the business purpose and required query types.
2. Write the query clause JSON in a classpath resource.
3. Parse the resource with Jackson and verify minimal structure.
4. Build a factory to insert typed parameters into the JSON tree.
5. Serialize to JSON and instantiate `StringQuery`.
6. Attach sort, pageable, or needed Spring Data options.
7. Execute through `ElasticsearchOperations`.
8. Unit test resource loading, parsing, and query construction.
9. Validate the query against Elasticsearch mappings.
10. Integration test results, edge cases, and performance.
11. Review and version resources alongside code changes.
12. Package and deploy with the application artifact.

For simple queries, keeping them inline with `@Query` or `StringQuery` works well. When queries grow large, are reused, or require independent review, JSON resources paired with tested factories are usually much easier to maintain.

## 14. Key Takeaways

- Storing Query DSL in `src/main/resources` separates query structure from service code.
- `StringQuery` accepts a Query DSL clause; distinguish it from the full search request body.
- Use `ResourceLoader` to load resources and `ObjectMapper` to parse JSON.
- Call `deepCopy()` before editing a template so concurrent requests do not overwrite each other's data.
- Update parameters via `ObjectNode`/`ArrayNode`, never manual JSON string concatenation.
- Preserve proper types: string, number, boolean, array, and object.
- Keep query conditions separate from sort/pageable when using Spring Data's `Query` abstraction.
- Unit tests verify resources and structure; integration tests verify mappings and Elasticsearch behavior.
- The Validate Query API catches DSL mistakes but does not replace relevance or performance testing.
- Never accept arbitrary Query DSL, index paths, or resource paths from clients.
- Manage query resources in source control and deploy them with the application so environments reproduce identical behavior.

Organizing JSON queries this way turns Query DSL into reviewable, testable, and versionable resources. Java focuses on placing business parameters into the right slots and executing queries, while integration tests verify that queries truly work with your project's mappings and Elasticsearch cluster.
