# Round-Trip Testing of Data After Writing and Reading

In Spring Data Elasticsearch, a Java object is not stored as-is inside Elasticsearch. Spring Data converts the object into a JSON document based on mapping metadata, the HTTP client sends the document to the cluster, Elasticsearch indexes the fields, and when reading data back, Spring Data converts the returned document into a Java object.

A **round-trip** test verifies that this entire path works end to end:

~~~text
Java Object
    |
    v
Spring Data mapping / custom converters
    |
    v
JSON Document
    |
    v
Elasticsearch index
    |
    v
JSON Document read back
    |
    v
Spring Data mapping / custom converters
    |
    v
Java Object after reading
~~~

This kind of testing catches issues that ordinary unit tests cannot reveal, such as mismatched field names, data types incompatible with mappings, misconverted enums, lost date-time precision, improperly mapped collections, or custom converters that only work in one direction.

## 1. What Does a Round-Trip Test Verify?

Suppose an application saves a product:

~~~java
Product input = new Product(
    "P-1001",
    "SKU-1001",
    "Wireless Mouse",
    259900L,
    true,
    List.of("accessory", "wireless"),
    Instant.parse("2026-11-13T10:15:30.123Z")
);
~~~

After writing, the application reads the document by ID:

~~~java
operations.save(input);

Product actual = operations.get(
    input.getId(),
    Product.class
);
~~~

If data is mapped properly, the read-back object must retain all expected business values.

A round-trip test should verify multiple layers:

| Layer to Verify | Content |
|---|---|
| Identity | Document ID is written accurately and read back accurately. |
| Field names | Java properties map to the expected Elasticsearch fields. |
| Data types | Numbers, booleans, dates/times, enums, and collections convert properly. |
| Nested structures | Child objects, lists, and nested fields retain proper structure. |
| Edge values | Nulls, empty strings, Unicode, large numbers, timestamps, and empty collections. |
| Custom conversions | Writing and reading converters operate properly in both directions. |
| Actual mapping | The running index has settings and mappings compatible with the entity. |
| Queries | Documents can be retrieved by ID or business queries. |

Do not merely check the object returned by the save() call itself. Some APIs return the input object or an object with an assigned ID, which does not prove the document was written to and read back from Elasticsearch successfully. Always perform a separate read operation after writing.

## 2. Distinguishing Unit Tests and Integration Tests

The two test types serve different purposes.

**Unit tests** are suited for testing pure Java logic, document creation rules, or custom converters when converters can be invoked directly. Unit tests run fast and do not require Elasticsearch.

**Integration tests** require a real Elasticsearch instance to verify HTTP requests, indices, mappings, serialization, document storage, and retrieval. Testcontainers can be used to spin up a dedicated Elasticsearch instance for tests.

| Criterion | Unit Test | Integration Test |
|---|---|---|
| Requires running Elasticsearch | No | Yes |
| Verifies mapping on cluster | Incomplete | Yes |
| Verifies actual write/read | No | Yes |
| Speed | Fast | Slower |
| Detects server/client config errors | Limited | Better |
| Used for | Logic, converters, validators | Round-trip, repositories, queries, and mappings |

A sensible organization is keeping unit tests for small conversion rules and using integration tests for critical flows. You do not need to boot Elasticsearch for every test in the application.

## 3. Preparing Elasticsearch for Integration Tests

Do not rely on an Elasticsearch instance running on a developer's machine or a shared cluster. Tests need an environment that can be created fresh, version-pinned, and cleaned up after execution.

Testcontainers can start Elasticsearch inside Docker. With Gradle, typical dependencies are:

~~~groovy
dependencies {
    testImplementation "org.testcontainers:junit-jupiter"
    testImplementation "org.testcontainers:elasticsearch"
}
~~~

Manage Testcontainers versions via a BOM so modules share a compatible version set.

Example container configuration with Elasticsearch 8.x:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.StringQuery;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.elasticsearch.ElasticsearchContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@SpringBootTest
class ProductRoundTripIT {

    @Container
    static final ElasticsearchContainer elasticsearch =
        new ElasticsearchContainer(
            DockerImageName.parse(
                "docker.elastic.co/elasticsearch/elasticsearch:8.13.4"
            )
        )
        .withEnv("discovery.type", "single-node")
        .withEnv("xpack.security.enabled", "false");

    @DynamicPropertySource
    static void elasticsearchProperties(
            DynamicPropertyRegistry registry) {
        registry.add(
            "spring.elasticsearch.uris",
            elasticsearch::getHttpHostAddress
        );
    }
}
~~~

This is an illustrative configuration. Choose an image whose Elasticsearch version is compatible with the Elasticsearch client and Spring Data Elasticsearch used by your application. Some container or client setups across versions may require different authentication/TLS configurations. If running Elasticsearch with security enabled, pass credentials and proper SSL configuration rather than disabling security.

@DynamicPropertySource supplies the container-generated URI to Spring Boot before the application context initializes the client. As a result, tests target the exact Elasticsearch container started for that run.

To run this example, the host machine or CI runner must have Docker running. If the test environment lacks Docker, you can point to a dedicated test Elasticsearch service, provided indices and data are isolated across test runs.

The container declaration above and the test methods below belong to the same `ProductRoundTripIT` class. Combine the fields, container configuration method, and test methods into one class.

## 4. Declaring the Entity Used in the Test

Example entity with multiple data types to test:

~~~java
import java.time.Instant;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.DateFormat;

@Document(indexName = "products-roundtrip")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Long)
    private Long priceInCents;

    @Field(type = FieldType.Boolean)
    private Boolean active;

    @Field(type = FieldType.Keyword)
    private List<String> tags;

    @Field(type = FieldType.Date, format = DateFormat.date_time)
    private Instant createdAt;

    protected Product() {
    }

    public Product(
            String id,
            String sku,
            String name,
            Long priceInCents,
            Boolean active,
            List<String> tags,
            Instant createdAt) {
        this.id = id;
        this.sku = sku;
        this.name = name;
        this.priceInCents = priceInCents;
        this.active = active;
        this.tags = tags;
        this.createdAt = createdAt;
    }

    public String getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }

    public Long getPriceInCents() {
        return priceInCents;
    }

    public Boolean getActive() {
        return active;
    }

    public List<String> getTags() {
        return tags;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
~~~

The field types are chosen deliberately:

- id is annotated with @Id to serve as the document identifier.
- sku is keyword for exact filtering.
- name is text for full-text search.
- priceInCents is an integer representing price in minor units, avoiding binary floating-point rounding errors for money.
- active is boolean.
- tags is a list of keyword values.
- createdAt is a timestamp of type Instant.

Spring Data needs an appropriate constructor or access mechanism to instantiate objects when reading. The example uses a no-arg constructor and getters; setters can be added if your application's mapping strategy requires them.

If the real entity contains nested objects, enums, custom value objects, or custom converters, include those fields in the test. A test that only checks a few simple fields does not prove that every domain data type round-trips accurately.

## 5. Explicitly Creating Index and Mapping in Tests

Integration tests should explicitly establish the target index and required mapping. Do not rely completely on dynamic mapping generated automatically by Elasticsearch when the first document is written.

With ElasticsearchOperations, you can use IndexOperations:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;
import org.springframework.data.elasticsearch.core.document.Document;

IndexOperations indexOperations =
    operations.indexOps(Product.class);

if (indexOperations.exists()) {
    indexOperations.delete();
}

indexOperations.create();

Document mapping = indexOperations.createMapping();
indexOperations.putMapping(mapping);
~~~

In tests, this recreates the index and applies the mapping generated from entity metadata. If the entity has custom settings such as analyzers or normalizers, supply those settings during index creation via the configuration API matching your Spring Data version.

Place index preparation inside @BeforeEach if you want each test to have isolated data. If index creation is slow and tests can safely share an index, create it once in @BeforeAll, then use unique IDs and clean up data per test.

Never run write/delete tests against production indices or shared clusters. Use an index name with a test suffix or an isolated container.

## 6. Round-Trip Testing with ElasticsearchOperations

The following test writes an entity and then performs a separate read by ID:

Imports were shown in the entity and container setup sections; the snippet below is the body added to the `ProductRoundTripIT` class above.

~~~java
    @Autowired
    ElasticsearchOperations operations;

    private IndexOperations indexOperations;

    @BeforeEach
    void prepareIndex() {
        indexOperations = operations.indexOps(Product.class);

        if (indexOperations.exists()) {
            indexOperations.delete();
        }

        indexOperations.create();
        indexOperations.putMapping(indexOperations.createMapping());
    }

    @Test
    void shouldWriteAndReadProduct() {
        Instant createdAt = Instant.parse(
            "2026-11-13T10:15:30.123Z"
        );

        Product expected = new Product(
            "P-1001",
            "SKU-1001",
            "Wireless Mouse",
            259900L,
            true,
            List.of("accessory", "wireless"),
            createdAt
        );

        operations.save(expected);

        Product actual = operations.get(
            expected.getId(),
            Product.class
        );

        assertNotNull(actual);
        assertEquals(expected.getId(), actual.getId());
        assertEquals(expected.getSku(), actual.getSku());
        assertEquals(expected.getName(), actual.getName());
        assertEquals(
            expected.getPriceInCents(),
            actual.getPriceInCents()
        );
        assertEquals(expected.getActive(), actual.getActive());
        assertEquals(expected.getTags(), actual.getTags());
        assertEquals(expected.getCreatedAt(), actual.getCreatedAt());
    }
~~~

Crucially, the test calls operations.get(...) after operations.save(...). This is a separate read from Elasticsearch, verifying both the write step and document-to-object conversion.

ElasticsearchOperations.get uses the get-by-ID operation. Elasticsearch's Get API is real-time for successfully written documents, so you do not need to refresh the index just to read back by ID as in the example above.

If your Spring Data version has different API signatures, adjust to match your project's version. The testing principle remains saving the object, performing an independent read, and comparing every critical value.

## 7. Verifying Through a Repository

If the application uses repositories, include at least one integration test confirming the repository works with the real mapping:

~~~java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
~~~

Test:

~~~java
@Autowired
ProductRepository productRepository;

@Test
void shouldRoundTripThroughRepository() {
    Product expected = new Product(
        "P-2001",
        "SKU-2001",
        "Mechanical Keyboard",
        1899000L,
        true,
        List.of("keyboard", "mechanical"),
        Instant.parse("2026-11-13T11:00:00.000Z")
    );

    productRepository.save(expected);

    Product actual = productRepository.findById("P-2001")
        .orElseThrow();

    assertEquals(expected.getSku(), actual.getSku());
    assertEquals(expected.getName(), actual.getName());
    assertEquals(
        expected.getPriceInCents(),
        actual.getPriceInCents()
    );
    assertEquals(expected.getTags(), actual.getTags());
}
~~~

Repository tests confirm the wiring among the repository, mapping context, and Elasticsearch client. If the application uses ElasticsearchOperations directly inside a service, test that service at the appropriate layer too.

Do not repeat the exact same set of assertions across dozens of repository tests. Pick representative cases to verify the behavior of the abstractions your application actually uses.

## 8. Distinguishing Get API and Search API When Testing

A common mistake is writing a document, immediately running a search, and assuming an empty result means the write failed.

Elasticsearch is near-real-time for search. A newly indexed document may not appear in the Search API until the next refresh cycle. In contrast, the Get API by ID can read a newly written document immediately.

Therefore:

- Use operations.get(id, ...) for round-trip checks by ID.
- When testing search queries, refresh the index in the test before searching.
- Do not force a refresh after every write in production just to get instant search visibility.

Example:

~~~java
operations.save(expected);

indexOperations.refresh();

SearchHits<Product> hits = operations.search(
    new StringQuery("""
        {"term":{"sku":"SKU-1001"}}
        """),
    Product.class
);

assertEquals(1, hits.getTotalHits());
assertEquals("P-1001", hits.getSearchHit(0).getContent().getId());
~~~

IndexOperations.refresh() asks Elasticsearch to make indexed changes visible to search. This is a clean way for integration tests to verify the Search API. When running tests in parallel or sharing one index across multiple tests, isolate data using unique IDs and prevent refreshes or cleanups from interfering with one another.

## 9. Inspecting the Actual JSON Document

If a round-trip test fails, determine whether the bug is in the write step or the read step. You can inspect the document directly via the Elasticsearch REST API:

~~~http
GET /products-roundtrip/_doc/P-1001
~~~

Response looks like:

~~~json
{
  "_index": "products-roundtrip",
  "_id": "P-1001",
  "found": true,
  "_source": {
    "sku": "SKU-1001",
    "name": "Wireless Mouse",
    "priceInCents": 259900,
    "active": true,
    "tags": [
      "accessory",
      "wireless"
    ],
    "createdAt": "2026-11-13T10:15:30.123Z"
  }
}
~~~

Compare _source with the input object:

- If _source is wrong, inspect mapping metadata, writing converters, field names, and serialization data types.
- If _source is right but the read-back object is wrong, inspect reading converters, constructors, property access, and Java types.
- If the document does not exist, inspect the ID, target index, write permissions, and the save operation response.

_source is the stored JSON content used to retrieve the document. It does not reveal all analyzed or normalized terms in the inverted index. If you need to verify analyzers/normalizers, use the Analyze API and inspect mappings.

## 10. Data Types Requiring Thorough Testing

### 10.1. Dates, times, and precision

Elasticsearch dates are typically stored as epoch milliseconds or date strings matching the mapping format. The common precision for date is milliseconds.

If a Java object uses Instant with nanoseconds, read-back data may not preserve the full nanosecond fraction. Example:

~~~java
Instant value = Instant.parse(
    "2026-11-13T10:15:30.123456789Z"
);
~~~

When round-tripping through a millisecond-precision date field, do not assume the result will exactly equal the original nanosecond value. You can normalize input data:

~~~java
Instant normalized = value.truncatedTo(
    ChronoUnit.MILLIS
);
~~~

Or in tests, assert to the precision promised by the system. The key is explicitly defining formats, timezones, and precision for business timestamps.

### 10.2. Integers and floating-point numbers

Types like long, integer, double, and float have different representation limits. Tests should cover:

- Small values and large values near Java type boundaries.
- Negative values if allowed by business logic.
- Nulls if the field is nullable.
- Decimal values if mapped as float/double.

For monetary amounts, it is usually best to store integers in minor units (such as cents) or use a scaled_float strategy with an explicitly designed scaling factor. Avoid equality assertions on floating-point numbers if conversions can introduce rounding errors.

### 10.3. Enums

If a Java field is an enum, check how it is written to _source and read back. Normally Spring Data converts enums to string names, but if the application uses custom converters, confirm the specific rules.

Example enum:

~~~java
public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
~~~

Tests should confirm PAID is written and read back as the proper enum constant. If storing codes other than enum names, test bidirectional converters and compatibility when enum constants are renamed.

### 10.4. Collections and nested objects

For a List<String> field, check element order if order matters at the application layer. Elasticsearch stores arrays in _source, though array search semantics do not preserve ordered list semantics in all queries.

For nested objects, distinguish object from nested mappings. If you need to query properties belonging to the same element inside an object array, nested has dedicated semantics. Round-trip tests should verify both read-back data structures and queries on nested fields if used by the application.

### 10.5. Nulls, missing fields, and defaults

A null Java property may not be serialized into _source depending on mapping/converter configuration. When reading back, the property may stay null or receive a default value from a constructor.

Distinguish between:

- A field with a null value.
- A field absent from JSON.
- A field initialized with a default value in Java.
- A field excluded by source filtering or converter configuration.

If business logic distinguishes "no data" from "empty value", tests must verify these semantics.

### 10.6. Unicode and special characters

Test strings containing Vietnamese diacritics, emoji characters, quotation marks, escape characters, whitespace, and long strings. These cases catch encoding bugs or custom converters mishandling Unicode.

Do not merely assert that the object is non-null. Assert exact string equality whenever content must be preserved verbatim.

## 11. Testing Custom Converters Bidirectionally

Spring Data Elasticsearch allows registering custom conversions to convert domain types into storable Elasticsearch representations and back when reading.

Example domain value object:

~~~java
public record Money(long amountInCents, String currency) {
}
~~~

If the application has converters transforming Money to a string or custom document structure, test both directions:

~~~text
Money in Java
      |
      v
Writing Converter
      |
      v
JSON form / value stored in Elasticsearch
      |
      v
Reading Converter
      |
      v
Money in Java
~~~

Cases to verify:

- Writing converter produces the expected representation.
- Reading converter restores the exact value.
- Currency, scale, and monetary units are not lost.
- Null values are handled consistently.
- Legacy data remains readable if the representation evolves across versions.

You can write unit tests directly against converters for fast logic checks, followed by at least one round-trip integration test confirming Spring Data actually registers and invokes those converters in the mapping context. A converter that passes when invoked manually is not guaranteed to be registered on the client used by repositories.

## 12. Testing Mappings and Queries Alongside Round-Trip

Round-tripping by ID proves data can be read back, but is not enough to prove business queries work.

Suppose an entity has:

- sku as keyword.
- name as text.
- active as boolean.

You can test two distinct query types:

~~~http
GET /products-roundtrip/_search
{
  "query": {
    "term": {
      "sku": "SKU-1001"
    }
  }
}
~~~

and:

~~~http
GET /products-roundtrip/_search
{
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  }
}
~~~

Tests should confirm mappings match the queries being executed. For example, running term on an analyzed text field does not share the semantics of match; conversely, match on a keyword field does not tokenize words like text.

If the application uses normalizers, analyzers, nested queries, aliases, or multi-fields, add tests for those setups. Object round-trip success does not automatically guarantee all queries return expected results.

## 13. Isolating Data Between Tests

Repeated test runs must yield stable results. Common isolation techniques:

**Recreating the index before each test.** Simple and well suited for small test suites. Index creation overhead grows as test count increases.

**Using unique IDs per test.** Use UUIDs or test-case suffixes to avoid overwriting documents from other tests.

**Using dedicated indices per test class or worker.** Useful when running tests in parallel. Index names must follow Elasticsearch's lowercase and allowed-character rules.

**Deleting data after tests.** Delete documents by ID or delete test indices. Ensure cleanup never runs accidentally against another environment.

When sharing a container across a class, avoid making tests depend on execution order. One test should not rely on data created by an earlier test unless it is an intentional scenario.

When running tests in parallel, never share the same index and fixed IDs if tests can write or delete over one another. Give each class or test worker its own namespace.

## 14. Recommended Round-Trip Test Matrix

A practical test suite can be organized into these groups:

| Group | Input Data | What to Verify |
|---|---|---|
| Basic values | ID, strings, numbers, booleans | Every field writes and reads accurately |
| Collections | Empty lists, multi-element lists | Structure and values are preserved |
| Date/time | Instant with millis, timezones | Format and precision are accurate |
| Null/default | Null properties, missing fields | Null/default semantics are accurate |
| Unicode | Vietnamese diacritics, emoji, special characters | Encoding and content remain intact |
| Enum | Every business status | Representation and conversion are accurate |
| Nested | Objects and lists of objects | Structure and nested queries work properly |
| Custom converter | Custom value objects | Both write and read directions |
| Mapping/query | Keyword, text, normalizers | Business queries return expected documents |
| Update | Initial write, field updates | New values read back, unrelated fields are not lost |

Not every group has to be a separate test method. Parameterized tests work well for boundary inputs, while complex scenarios can live in dedicated test methods for clearer failure messages.

## 15. Diagnosing Round-Trip Test Failures

When an assertion fails, do not rush to change the mapping. Pinpoint which stage corrupted the data.

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Document not found | Wrong ID, index, or write failure | Inspect write response, check index and Get API directly |
| Field is null after reading | Wrong field name, constructor mapping, or converter | Inspect _source, mapping, and object mapping metadata |
| Read-back number differs from written | Incompatible numeric type or precision | Inspect JSON, field type, and conversion logic |
| Date/time is shifted | Format/timezone mismatch or millisecond precision | Inspect _source, mapping format, and timezone |
| Collection is empty or loses elements | Wrong mapping/converter or JSON representation | Inspect _source and property type |
| Enum cannot be read | Stored value does not match enum or converter failed | Inspect string in _source and reading converter |
| Get succeeds but Search misses | Missing refresh or wrong query | Refresh index in test, check mapping/query |
| Wrong mapping | Index created before desired settings/annotations applied | Inspect _mapping, _settings; recreate test index |
| Passes alone, fails in suite | Shared data or shared index | Isolate index/IDs, check cleanup and parallel execution |

A useful investigation flow:

1. Check exceptions or responses from the write operation.
2. Use Get API by ID to confirm the document exists.
3. Inspect _source to confirm the written JSON.
4. Inspect mapping to confirm field types and field names.
5. Read back via Spring Data to check Java-side deserialization.
6. If testing search queries, refresh the index and inspect queries and analyzers/normalizers.
7. Check custom conversions and constructors if only specific properties fail.

If _source is already wrong right after writing, focus on serialization and mapping. If _source is right while the read-back object is wrong, focus on deserialization and converters. Separating the two narrows down the root cause quickly.

## 16. Notes on Refresh, Retries, and Test Repeatability

Do not call refresh mechanically after every write. For Get API tests by ID, refresh is usually unnecessary. For Search API tests, refresh makes newly indexed documents visible.

Do not spin-retry assertions repeatedly to mask timing issues. If search needs a refresh, issue an explicit refresh or configure an appropriate refresh policy for the test environment. If a write operation throws an error, read the underlying exception before retrying.

Round-trip tests should be repeatable:

- Use deterministic data.
- Use isolated indices.
- Create explicit mappings.
- Avoid test order dependencies.
- Do not rely on leftover data from previous runs.
- Scope cleanup precisely.
- Pin an Elasticsearch version compatible with the client.

In production, avoid forcing a refresh after every write just to read immediately via search. Tests can proactively trigger refresh to verify search behavior, whereas real applications should pick a refresh policy balancing freshness requirements and performance.

## 17. Checklist Before Concluding Round-Trip Is Correct

A round-trip test is valuable when it genuinely exercises Elasticsearch and verifies critical domain fields. Before signing off, confirm:

- Tests connect to a dedicated test Elasticsearch instance with a compatible version.
- The index is created with the intended settings and mappings.
- Input objects are written using the same Spring Data API used by the application.
- Tests read documents via a separate operation after writing.
- IDs and key business fields are compared.
- Dates/times, numbers, enums, collections, nulls, and nested fields are tested as required.
- Custom converters are tested in both write and read directions.
- If testing search, the index is refreshed and queries match the mapping.
- _source can be inspected to separate serialization bugs from deserialization bugs.
- Tests isolate data, run independently, and never touch shared clusters.

Round-trip testing after writing and reading verifies that Spring Data Elasticsearch converts objects accurately through mappings, persists documents into the index, and reconstructs data into Java objects. Use unit tests for pure conversion logic, integration tests against real Elasticsearch for round-tripping, perform a separate read after writing, compare business values, and inspect _source whenever discrepancies appear.
