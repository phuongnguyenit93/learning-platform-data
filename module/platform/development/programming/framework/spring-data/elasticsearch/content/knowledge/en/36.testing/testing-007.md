# Testing Analyzers, Converters, and a Write-Read Round-Trip

A Spring Data Elasticsearch application can run without throwing errors while still saving or searching data incorrectly. An analyzer may tokenize text differently than expected; a converter may serialize a Java type into a value that cannot be read back; a mapping may miss a field or declare the wrong type; a save-then-get round-trip may lose data due to asymmetric conversion.

Therefore, integration tests should verify three parts working together:

1. **Analyzer and mapping:** Elasticsearch analyzes text according to the field configuration.
2. **Converter:** Spring Data converts an entity into a Document and reads the Document back into the expected Java type.
3. **A real write-read round-trip:** the entity is saved to Elasticsearch, then read back while preserving business data intact.

These tests complement service unit tests. They require a real Elasticsearch instance compatible with the project's Spring Data version, typically launched with Testcontainers during test execution. Mocking `ElasticsearchOperations` cannot prove that analyzers, mappings, serialization, and queries actually work on a cluster.

## 1. The Three Layers to Test

Analyzers, converters, and mappings have distinct responsibilities:

| Component | Responsibility | Test question |
|---|---|---|
| Mapping | Declares field types, analyzers, formats, and index attributes | Does Elasticsearch accept the right mapping? |
| Analyzer | Converts text into tokens for indexing or searching | Which tokens does the input text produce? |
| Converter | Converts Java types to Document and back | Are values serialized and deserialized properly? |
| Write/read integration | Combines mapping, converter, client, and cluster | After saving and reading back, is the data still intact? |

Do not use a single assertion to conclude every layer is correct. For instance, reading a document back by ID does not prove the analyzer tokenizes text properly. Conversely, `_analyze` returning the right tokens does not prove a custom converter persists the entity.

Overall test flow:

~~~text
        Java Entity
             |
             v
    Spring Data Converter
             |
             v
       Elasticsearch Document
             |
             v
       Index + Mapping
             |
             v
       Analyzer at index time
             |
             v
       Lucene inverted index
             |
             v
       Search / Analyze API
             |
             v
      SearchHit / Document
             |
             v
    Spring Data Converter
             |
             v
        Java Entity
~~~

## 2. Using Real Elasticsearch in Integration Tests

Analyzers and mappings are executed by Elasticsearch. Therefore, analyzer tests require a real Elasticsearch node. Testcontainers helps create and destroy a node within the test lifecycle, avoiding reliance on a shared cluster on developer machines.

With Maven, projects typically need the corresponding test dependencies:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>elasticsearch</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
~~~

The Testcontainers version must be compatible with the JDK, Spring Boot, and the project's dependency management. Do not upgrade Testcontainers or the Elasticsearch image independently to another major version without checking the compatibility matrix.

### 2.1. Launching the Container

Example with JUnit 5 and Testcontainers:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.elasticsearch.ElasticsearchContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@SpringBootTest
class ProductElasticsearchIntegrationTest {

    @Container
    static final ElasticsearchContainer elasticsearch =
            new ElasticsearchContainer(
                    DockerImageName.parse(
                            "docker.elastic.co/elasticsearch/elasticsearch:8.15.5"
                    )
            ).withPassword("test-password");

    @DynamicPropertySource
    static void elasticsearchProperties(
            DynamicPropertyRegistry registry
    ) {
        registry.add(
                "spring.elasticsearch.uris",
                elasticsearch::getHttpHostAddress
        );
        registry.add(
                "spring.elasticsearch.username",
                () -> "elastic"
        );
        registry.add(
                "spring.elasticsearch.password",
                elasticsearch::getPassword
        );
    }
}
~~~

This is an illustrative structure for Testcontainers 1.x and Spring Boot 3.x. Container APIs, security setup, and property names may vary by version. Use an Elasticsearch image matching the major/minor range supported by your application's client; if your project already has a dedicated container setup, keep that mechanism and add only the needed tests.

Testcontainers requires a running Docker daemon. If Docker is unavailable, tests cannot start the node; that is a test environment error, not proof of an analyzer or converter bug.

### 2.2. Do Not Use Shared Clusters for Write Tests

A test writing documents into a fixed index can interfere with other tests or developer data. You should:

- Use an index dedicated to integration tests.
- Delete and recreate the index before each test that needs a clean state.
- Never point tests at production or shared clusters.
- Clean up the index after tests if it is not automatically destroyed with the container.
- Avoid running multiple tests in parallel that write to the same fixed index without an isolation mechanism.

For parallel tests, use a separate index name per test or per test class. Index names must be lowercase per Elasticsearch rules.

## 3. Declaring Test Mappings and Analyzers

Suppose the `name` field needs to handle letter casing and Vietnamese or Latin diacritics. We define a custom analyzer consisting of:

- Standard tokenizer to split tokens on word boundaries.
- Lowercase filter to normalize to lowercase.
- Asciifolding filter to convert certain accented characters into their ASCII equivalents.

Example settings file:

`src/test/resources/settings/products-settings.json`

~~~json
{
  "analysis": {
    "analyzer": {
      "product_text": {
        "type": "custom",
        "tokenizer": "standard",
        "filter": [
          "lowercase",
          "asciifolding"
        ]
      }
    }
  }
}
~~~

Mapping:

`src/test/resources/mappings/products-mapping.json`

~~~json
{
  "properties": {
    "name": {
      "type": "text",
      "analyzer": "product_text",
      "search_analyzer": "product_text"
    },
    "status": {
      "type": "keyword"
    },
    "price": {
      "type": "keyword"
    },
    "createdAt": {
      "type": "date"
    }
  }
}
~~~

In this example `price` is mapped as `keyword` because a later section uses a custom converter turning a value object into a fixed-format string. If you need numeric filtering or sorting by amount, design an appropriate numeric mapping instead of storing all monetary values as `keyword`.

### 3.1. Attaching Settings and Mapping to a Test Entity

Spring Data Elasticsearch can load settings and mapping files from the classpath via annotations:

~~~java
@Document(indexName = "products-it")
@Setting(settingPath = "/settings/products-settings.json")
@Mapping(mappingPath = "/mappings/products-mapping.json")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text, analyzer = "product_text")
    private String name;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Keyword)
    private Money price;

    @Field(type = FieldType.Date)
    private Instant createdAt;
}
~~~

Annotations and attributes must exist in your project's Spring Data Elasticsearch release train. If the application manages mappings using separate JSON files or index templates, create the index using the exact mechanism production uses so tests do not drift in configuration.

Do not inspect only annotations on the entity. What matters is the actual mapping installed on the index. A valid annotation will not automatically alter existing field mappings on an index that already exists.

## 4. Testing the Actual Mapping

After creating the index, read the mapping back from Elasticsearch to confirm fields have the expected types and analyzers:

~~~java
@Autowired
ElasticsearchOperations operations;

@Test
void createsIndexWithExpectedMapping() {
    IndexOperations indexOperations =
            operations.indexOps(ProductDocument.class);

    if (indexOperations.exists()) {
        indexOperations.delete();
    }

    assertThat(indexOperations.createWithMapping()).isTrue();

    Map<String, Object> mapping = indexOperations.getMapping();
    assertThat(mapping).isNotEmpty();
}
~~~

The test above illustrates creating an index from entity metadata and reading the mapping. For detailed checks, you can use the Elasticsearch Java Client's `indices().getMapping(...)` or the REST Get Mapping API and inspect `properties.name.type`, `properties.name.analyzer`, and related fields.

Example API call:

~~~http
GET /products-it/_mapping
~~~

Mappings should be verified after index creation. If a test only calls `createWithMapping()` without asserting or inspecting the actual mapping, it has not yet proven fields were configured as expected.

### 4.1. Mappings Cannot Be Arbitrarily Changed Once an Index Has Data

Certain mapping changes—especially changing a field type—cannot be applied directly to an existing field. If a mapping is wrong, you must create a new index with the right mapping and reindex data through an appropriate process.

Hence, each integration test should start with a fresh index or delete/recreate it. Reusing an old index risks testing a mapping left over from a previous run.

## 5. Testing Analyzers with the Analyze API

The Analyze API lets you send text and observe the tokens generated by an analyzer. This is a direct way to verify tokenizers and token filters.

Example testing the `name` field:

~~~java
import co.elastic.clients.elasticsearch.indices.AnalyzeResponse;

AnalyzeResponse response = elasticsearchClient.indices().analyze(
        request -> request
                .index("products-it")
                .field("name")
                .text("Café KEYBOARD")
);

List<String> tokens = response.tokens().stream()
        .map(token -> token.token())
        .toList();

assertThat(tokens).containsExactly("cafe", "keyboard");
~~~

Using `field` instead of only naming the analyzer tests the analyzer attached to the field mapping. If the field mapping is missing or the analyzer was not installed, the test detects the configuration error.

You can also call the REST API directly to investigate:

~~~http
POST /products-it/_analyze
Content-Type: application/json

{
  "field": "name",
  "text": "Café KEYBOARD"
}
~~~

The expected tokens in this example are `cafe` and `keyboard`. When working with Vietnamese text, pick accented words and define explicit expectations for diacritics, casing, punctuation, compound words, and tokenization. Asciifolding is not a dedicated Vietnamese word segmenter; it only performs character folding according to supported filter rules.

### 5.1. Testing Index-Time and Search-Time Analyzers

A mapping can declare different analyzers for indexing and searching. Test both if the application configures them separately:

- `analyzer`: tokenizes content at index time.
- `search_analyzer`: tokenizes query text at search time.

The Analyze API can specify an analyzer or a field. Testing the field shows the analyzer bound to the field; testing by explicit analyzer name is useful to pinpoint each configuration individually.

If the search analyzer differs from the index analyzer, test both inputs to ensure they produce compatible tokens. A good index analyzer paired with an incompatible search analyzer can prevent user keywords from matching documents.

### 5.2. Testing Edge-Case Text Inputs

Do not test only one simple English string. Define a representative input suite:

| Input | What to observe |
|---|---|
| `Café KEYBOARD` | Lowercasing and folding |
| `WIRELESS mouse` | Uppercase-to-lowercase conversion |
| `wireless-mouse` | Token boundaries produced by the tokenizer |
| String with punctuation | How the tokenizer handles punctuation |
| Empty string | No unexpected tokens produced |
| Whitespace only | No tokens produced |
| Non-Latin Unicode characters | Actual tokenizer/filter behavior |

Expected tokens must reflect the real analyzer and product data language. Never assume all Vietnamese diacritics or all Unicode characters are handled identically by asciifolding.

## 6. Custom Converters in Spring Data Elasticsearch

Converters are responsible for turning Java types into Document structures stored by Elasticsearch and reading those structures back into Java types.

For example, suppose the domain has a `Money` value object:

~~~java
public record Money(long minorUnits, String currency) {
}
~~~

The application wants to store `Money(1299, "USD")` as the string `USD:1299`. When reading back, the converter must parse the string and reconstruct the value object.

### 6.1. Writing Converter

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class MoneyToStringConverter
        implements Converter<Money, String> {

    @Override
    public String convert(Money source) {
        return source.currency() + ":" + source.minorUnits();
    }
}
~~~

### 6.2. Reading Converter

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class StringToMoneyConverter
        implements Converter<String, Money> {

    @Override
    public Money convert(String source) {
        String[] parts = source.split(":", 2);
        if (parts.length != 2) {
            throw new IllegalArgumentException(
                    "Invalid money representation"
            );
        }

        return new Money(
                Long.parseLong(parts[1]),
                parts[0]
        );
    }
}
~~~

Annotating conversion direction with `@WritingConverter` and `@ReadingConverter` helps Spring Data distinguish converters used on write vs read, especially when both source and target are simple types.

The string format is a data contract. Explicitly define currency, scale, separator, locale, and legacy data handling. Do not arbitrarily use `toString()` if it lacks a stable format.

### 6.3. Registering Custom Conversions

Register converters with `ElasticsearchCustomConversions` in Spring Data Elasticsearch configuration:

~~~java
@Bean
ElasticsearchCustomConversions elasticsearchCustomConversions() {
    return new ElasticsearchCustomConversions(
            List.of(
                    new MoneyToStringConverter(),
                    new StringToMoneyConverter()
            )
    );
}
~~~

In configurations extending `AbstractElasticsearchConfiguration`, you can override the method providing custom conversions according to your version's API. With Spring Boot auto-configuration, verify that the custom conversions bean is actually used by `ElasticsearchConverter`. Do not just define standalone converter beans without registering them with the mapping converter.

If the application has multiple converter configurations, inspect the registered conversion list and avoid two conflicting converters for the same type pair.

## 7. Independent Unit Tests for Converters

Before starting Elasticsearch, you can independently test converting entities to Documents and reading Documents back using `ElasticsearchConverter`.

Example:

~~~java
@Autowired
ElasticsearchConverter converter;

@Test
void convertsMoneyToDocumentAndBack() {
    ProductDocument product = new ProductDocument();
    product.setId("product-42");
    product.setName("Keyboard");
    product.setPrice(new Money(1299, "USD"));

    Document document = Document.create();
    converter.write(product, document);

    assertThat(document.get("price")).isEqualTo("USD:1299");

    ProductDocument restored =
            converter.read(ProductDocument.class, document);

    assertThat(restored.getPrice())
            .isEqualTo(new Money(1299, "USD"));
}
~~~

This test verifies that the mapping converter uses the right converter pair in both directions. It needs no network or Elasticsearch node, though it needs a Spring context providing an `ElasticsearchConverter` with custom conversions registered.

To write pure unit tests for converters, you can invoke `MoneyToStringConverter` and `StringToMoneyConverter` directly. However, testing converters directly does not prove Spring Data registered and invokes them during entity mapping. Testing via `ElasticsearchConverter` additionally covers registration and mapping.

### 7.1. Testing Malformed Data

A reading converter should handle explicitly:

- Null or empty strings.
- Missing currency.
- Missing amount.
- Non-numeric amount.
- Invalid currency.
- Legacy data with a different format.

Depending on the domain contract, the converter may throw a clear exception or intentionally support a legacy format. Do not silently coerce corrupt data into default values, as that hides persistence errors.

## 8. A Write-Read Round-Trip Through Real Elasticsearch

Converter unit tests do not prove the entire write-read path. Integration tests should save the entity via `ElasticsearchOperations`, let the converter build the document, let Elasticsearch index it, and read it back through the same mapping converter.

Example entity:

~~~java
@Document(indexName = "products-it")
@Setting(settingPath = "/settings/products-settings.json")
@Mapping(mappingPath = "/mappings/products-mapping.json")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text, analyzer = "product_text")
    private String name;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Keyword)
    private Money price;

    @Field(type = FieldType.Date)
    private Instant createdAt;

    // getters and setters
}
~~~

Integration test:

~~~java
@Autowired
ElasticsearchOperations operations;

@Test
void writesAndReadsProductWithCustomMoneyConversion() {
    IndexOperations indexOperations =
            operations.indexOps(ProductDocument.class);

    if (indexOperations.exists()) {
        indexOperations.delete();
    }
    assertThat(indexOperations.createWithMapping()).isTrue();

    ProductDocument product = new ProductDocument();
    product.setId("product-42");
    product.setName("Café Keyboard");
    product.setStatus("ACTIVE");
    product.setPrice(new Money(1299, "USD"));
    product.setCreatedAt(Instant.parse("2026-11-13T08:00:00Z"));

    ProductDocument saved = operations.save(product);

    ProductDocument loaded = operations.get(
            saved.getId(),
            ProductDocument.class
    );

    assertThat(loaded).isNotNull();
    assertThat(loaded.getName()).isEqualTo("Café Keyboard");
    assertThat(loaded.getStatus()).isEqualTo("ACTIVE");
    assertThat(loaded.getPrice())
            .isEqualTo(new Money(1299, "USD"));
    assertThat(loaded.getCreatedAt())
            .isEqualTo(Instant.parse("2026-11-13T08:00:00Z"));
}
~~~

This example uses `get` by document ID. The Get API by ID is real-time by default, so it can read the newly indexed document without waiting for a refresh. If the test's goal is the Search API, refresh the index before searching.

### 8.1. Verifying Search Visibility

After saving:

~~~java
indexOperations.refresh();

Query query = NativeQuery.builder()
        .withQuery(q -> q.term(t -> t
                .field("status")
                .value("ACTIVE")
        ))
        .build();

SearchHits<ProductDocument> hits =
        operations.search(query, ProductDocument.class);

assertThat(hits.getSearchHits())
        .extracting(hit -> hit.getContent().getId())
        .contains("product-42");
~~~

Refresh here serves Search visibility. It is not a prerequisite for the converter writing properly or for the Get API by ID reading the new document.

### 8.2. Checking What Format Was Actually Stored

To verify the converter wrote the string `USD:1299` into `_source`, you can read the raw document via the Elasticsearch Java Client or a Get API call returning the source. This distinguishes:

- Does the write converter produce the right representation?
- Does the Elasticsearch mapping accept that representation?
- Does the read converter restore the right Java type?

A successful `save`-then-`get` round-trip proves the bidirectional path works for the tested value. Inspecting raw `_source` helps diagnose failures: the bug could be in serialization or in reading conversion.

## 9. Testing Analyzers Combined with the Write-Read Round-Trip

After indexing a product named `Café Keyboard`, you can use a match query to verify the actual analyzer finds it using a normalized string:

~~~java
Query query = NativeQuery.builder()
        .withQuery(q -> q.match(m -> m
                .field("name")
                .query("cafe keyboard")
        ))
        .build();

SearchHits<ProductDocument> hits =
        operations.search(query, ProductDocument.class);

assertThat(hits.getSearchHits())
        .extracting(hit -> hit.getContent().getId())
        .contains("product-42");
~~~

This test verifies that the analyzer participates in actual search behavior. It complements `_analyze` tests:

- `_analyze` confirms which tokens are generated.
- Match queries confirm the document was indexed and search finds it using the configured analyzer.

If `_analyze` passes while the match query finds nothing, inspect the index mapping at the time the document was indexed, whether the field is indexed, the search analyzer, the query field, and the actual data.

## 10. Testing Asymmetric Converters

A converter can write correctly yet read incorrectly, or vice versa. For example:

- Writing converter writes `USD:1299`.
- Reading converter interprets amount as major units instead of minor units.
- Currency gets lowercased.
- Strings are parsed using the test machine's locale.
- Negative values or large numbers overflow.

Therefore, round-trip tests should cover multiple values:

| Java input | Expected representation | Java output |
|---|---|---|
| `Money(1299, "USD")` | `USD:1299` | `Money(1299, "USD")` |
| `Money(0, "VND")` | `VND:0` | `Money(0, "VND")` |
| `Money(-500, "USD")` | `USD:-500` | `Money(-500, "USD")` |
| Large value within allowed domain | Stable integer string | Amount preserved intact |

If the domain forbids negative amounts, the converter can reject them and business validation should check before writing. What matters is defining the contract clearly and testing both allowed boundary values and rejected inputs.

## 11. Testing Mappings and Analyzers When an Index Already Exists

A common mistake is having a test pass on the first run while subsequent runs reuse an index with an old mapping. `createWithMapping()` does not mean every field mapping will be overwritten on an existing index.

Testing strategy:

1. Create a fresh index with a test-dedicated name.
2. Install settings and mappings.
3. Verify the actual mapping.
4. Run `_analyze` on mapped fields.
5. Write documents.
6. Read documents and verify converters.
7. Run Search API queries to verify index/search analyzers.
8. Delete the index after the test or let a disposable container destroy all data.

If the application uses index templates or component templates in production, integration tests should install templates and create indices using the same mechanism. Testing entity annotations alone will miss production templates overriding settings or mappings.

## 12. Testing with Aliases and Versioned Indices

In production, an application may write through an alias like `products` pointing to a versioned index `products-v3`. Tests should verify:

- The alias points to the right index.
- Mappings/analyzers exist on the target index.
- Saving through the alias works with real permissions and routing.
- Searching through the alias uses the expected analyzer.
- Switching aliases does not leave tests bound to an old index.

If `@Document` specifies a fixed index name, you can pass `IndexCoordinates` to operations to target a specific index. When doing so, ensure the mapping is created on the exact index coordinates used by save/search operations.

## 13. Testing Converters Against Legacy Data

Converters often have to read documents written by earlier versions of the application. When changing formats:

- Reading converters may need to support the old format during migration.
- Writing converters should emit the new format only after all readers are compatible.
- Handle missing fields or null fields.
- If a format change is incompatible, plan a reindex or data transformation.

For example, if the old format is `1299|USD` and the new format is `USD:1299`, the reading converter can accept both during transition while the writing converter writes only the new canonical format. Test each format so you do not accidentally break legacy documents.

Do not turn converters into the home for full migration logic. Converters should transform representations; large migrations need a controlled job with error logging and resumability.

## 14. Distinguishing Analyzer, Converter, and Mapping Errors

When a test fails, identify the failing layer before fixing:

| Symptom | Where to check |
|---|---|
| `_analyze` does not return expected tokens | Analyzer definition, tokenizer, filters, field mapping |
| Field missing from mapping | Entity annotations, mapping JSON, index template, index creation order |
| Save throws mapping error | Field type, converter output, data incompatible with mapping |
| Raw `_source` has wrong representation | Writing converter or mapping serialization |
| Raw `_source` is right but Java object is wrong | Reading converter or entity mapping |
| Get succeeds but Search misses document | Refresh visibility, field index setting, analyzer, query |
| Match query misses synonyms/accented forms | Index/search analyzer and token compatibility |
| Test passes alone, fails in suite | Shared index, parallel tests, cleanup, or container lifecycle |

Do not tweak an analyzer just to mask a converter bug. Nor should you change a converter to work around a wrongly typed field mapping. Each layer has its own responsibility and deserves its own test.

## 15. Test Isolation and Data Cleanup

A stable integration test must have deterministic initial state:

- Use a dedicated container per test suite or class.
- Create a fresh index before the test.
- Prevent documents from earlier tests from affecting queries.
- Delete the index after the test if needed.
- Wait for the container to be ready before the Spring context creates clients.
- Disable parallel execution for tests sharing an index, or use unique index names.

Cleanup example:

~~~java
@AfterEach
void deleteTestIndex() {
    IndexOperations indexOperations =
            operations.indexOps(ProductDocument.class);

    if (indexOperations.exists()) {
        indexOperations.delete();
    }
}
~~~

If each test deletes and creates the index before running, post-test cleanup provides an extra safeguard. Avoid having two tests delete the same index while another is still writing.

## 16. Test Slices, Spring Context, and What Tests Really Need

Not every test needs to start a full Spring Boot context:

- Pure converter unit tests can run without a Spring context.
- `ElasticsearchConverter` tests need custom conversions registered.
- Analyzer tests need a real Elasticsearch node.
- Save/read round-trip tests need Spring Data mapping, client, and an Elasticsearch node.
- Controller tests can mock the repository if the goal is solely the HTTP contract.

Pick the smallest scope that still proves the behavior. `@SpringBootTest` tests real wiring, though it starts more slowly. A test slice is appropriate only when that slice actually loads the Elasticsearch beans and converters the test requires.

Never mock `ElasticsearchOperations` in a test intended to prove analyzer or mapping behavior. Mocks only verify application calls; they do not execute Elasticsearch DSL.

## 17. Recommended Test Suite

A suite can be divided as follows:

| Test | Type | What it verifies |
|---|---|---|
| Money converter write | Unit | Java value object turns into stable representation |
| Money converter read | Unit | Representation parses into Java value object |
| `ElasticsearchConverter` round-trip | Mapping test | Spring Data registers and invokes converters properly |
| Index mapping test | Integration | Index has expected field types/analyzers |
| Analyze API test | Integration | Analyzer produces expected tokens |
| Save/get test | Integration | Write-read round-trip preserves fields and types |
| Save/refresh/search test | Integration | Analyzer and mapping work during search |
| Legacy format test | Unit/integration | Reader handles legacy documents per contract |

These tests can live in the same test class or be split by speed and responsibility. You do not need to restart a container for every single test when a class-scoped container can be used safely; however, each test must still isolate index and document state.

## 18. Checklist Before Trusting a Write-Read Round-Trip

- [ ] Elasticsearch test version is compatible with the client and Spring Data.
- [ ] Tests use a real node, not mocks, for analyzer/mapping behavior.
- [ ] Index is created fresh with expected settings and mappings.
- [ ] Actual mapping is read back and asserted.
- [ ] `_analyze` tests specify a mapped field or explicit analyzer.
- [ ] Inputs cover uppercase, diacritics, punctuation, and empty cases appropriate to the domain.
- [ ] Custom writing converter is registered.
- [ ] Custom reading converter is registered.
- [ ] Converter round-trip preserves values and Java types.
- [ ] Entity is saved via `ElasticsearchOperations` or repository.
- [ ] Get by ID confirms persisted data and reading conversion.
- [ ] Refresh before Search assertions if testing Search visibility.
- [ ] Match query confirms the analyzer works on indexed documents.
- [ ] Tests clean up and do not share indices with other environments.
- [ ] Legacy data/formats are tested if migration is involved.

## 19. Conclusion

Testing analyzers, converters, and a write-read round-trip requires verifying each responsibility separately and then combining them in integration tests. Mapping governs field types and analyzers; the Analyze API verifies which tokens tokenizers/filters produce; custom converters define how Java types are represented in a Document; save/get round-trips confirm all pieces work together with real Elasticsearch.

Use a compatible Elasticsearch Testcontainers setup to create a clean index, install settings/mappings, inspect the real mapping, and invoke `_analyze` on fields. Test converters bidirectionally via `ElasticsearchConverter`, then save entities with Spring Data and read them back by ID. When testing Search, refresh the index before querying because Get by ID and Search have different visibility semantics.

A single passing round-trip is good evidence for the chosen sample data, but it does not replace analyzer, mapping, and edge-case tests. When tests are separated by responsibility and share production's index configuration, conversion or search bugs are caught much closer to where they arise.
