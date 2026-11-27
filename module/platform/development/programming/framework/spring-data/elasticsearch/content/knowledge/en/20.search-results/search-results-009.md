# Handling Empty Results, Multiple Results, and Conversion Errors

When querying Elasticsearch with Spring Data Elasticsearch, an application must handle three common situations: a query finds no documents, a query returns more documents than expected, and data from Elasticsearch fails to convert into Java objects. Without a well-defined result contract, a service may encounter **NullPointerException**, result-size errors, or return incomplete data to an API.

Handling depends on the API style being used. Repositories typically represent a single result with **Optional<T>**, collections with **List<T>** or **Iterable<T>**, and paginated results with **Page<T>** or **Slice<T>**. **ElasticsearchOperations.get(...)** usually returns an entity or **null**, while **search(...)** returns **SearchHits<T>**, even when there are no hits. When data is mapped from JSON to Java, **MappingElasticsearchConverter** and Spring Data converters are responsible for value conversion; mismatched types or formats can cause reading to fail.

This article uses the **products** index, the **Product** document class, and fields for SKU, name, category, price, status, and creation date. The focus is on determining result cardinality, handling empty results, distinguishing business cases from technical errors, and diagnosing conversion failures.

## 1. Three Result Situations to Distinguish

A query can lead to the following situations:

1. **No matching documents.** Elasticsearch executes the query successfully but finds zero hits.
2. **One or more documents.** The result is valid and must be processed according to the return type.
3. **Unable to read or convert results.** The request may succeed on Elasticsearch, yet Spring Data fails to map source into Java types; or Elasticsearch itself rejects the request due to mapping, query, or connection errors.

You should not treat all three situations as “data not found.” An empty collection is a valid result. A conversion error is a technical error that must be logged and handled separately.

| Situation | Example | Common representation |
|---|---|---|
| Single document not found | No product with ID p-9999 | `Optional.empty()` or `null`, depending on API |
| No documents found in multi-result query | No products in category `unknown` | Empty collection, `Page`, or `SearchHits` |
| Exactly one document found | One matching SKU | Present `Optional` or entity |
| Multiple documents found | Multiple products in same category | `List`, `Iterable`, `Page`, `Slice`, or `SearchHits` |
| Single-result query returns multiple documents | `findByCategory` declares `Optional` but category has multiple products | May throw `IncorrectResultSizeDataAccessException` |
| Data cannot be mapped | Invalid date format or numeric field contains invalid string | Conversion/mapping exception |
| Elasticsearch rejects write | Value violates strict mapping | Error from Elasticsearch, often containing `mapper_parsing_exception` |

## 2. Repository Result Contracts

Repository methods should declare return types matching the number of documents the query can find.

Example:

~~~java
import java.util.List;
import java.util.Optional;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    Optional<Product> findBySku(String sku);

    List<Product> findByCategory(String category);

    Page<Product> findByStatus(String status, Pageable pageable);
}
~~~

These contracts carry different meanings:

- **Optional<Product>** represents zero or one `Product`.
- **List<Product>** represents zero or more `Product` instances; when none exist, an empty list.
- **Page<Product>** represents one page of results along with pagination metadata.

Do not declare a method returning a single entity if the query condition can match multiple documents. If SKU is used as a unique business key, the application must ensure data does not create multiple documents with the same SKU. Elasticsearch does not enforce unique constraints on a standard `keyword` field automatically.

## 3. Handling Optional When Finding a Single Document

CRUD methods such as **findById(id)** on a repository return **Optional<T>**. If the document does not exist, the result is **Optional.empty()**.

~~~java
Optional<Product> result = productRepository.findById("p-1001");

if (result.isPresent()) {
    Product product = result.get();
    System.out.println(product.getName());
} else {
    System.out.println("Product not found");
}
~~~

It can be written more concisely with **orElseThrow**:

~~~java
Product product = productRepository.findById("p-1001")
        .orElseThrow(() -> new ProductNotFoundException("p-1001"));
~~~

Or use **ifPresent** when no return value is needed:

~~~java
productRepository.findById("p-1001")
        .ifPresent(product -> sendNotification(product));
~~~

### Do Not Call Optional.get() Without Checking

The following snippet can throw **NoSuchElementException** if the `Optional` is empty:

~~~java
Product product = productRepository.findById(id).get();
~~~

Call `get()` only after proving the `Optional` holds a value. In business code, **orElseThrow**, **map**, **ifPresent**, or checking **isPresent()** usually expresses intent more clearly.

### Query Methods Returning a Single Entity

A derived query can be declared to return `Product` directly:

~~~java
Product findBySku(String sku);
~~~

With a single-entity return type, “no result” is typically represented as **null**. This forces callers to check for null. Therefore, if “SKU not found” is a normal outcome, **Optional<Product>** is usually a safer and clearer contract:

~~~java
Optional<Product> findBySku(String sku);
~~~

Distinguish custom query methods from inherited CRUD methods. For example, **findById** has an `Optional` contract defined by the repository API; do not assume every entity-returning method shares the exact same contract.

## 4. When a Single-Result Query Matches Multiple Documents

A query method returning `Product` or `Optional<Product>` can represent at most one result. If the query actually matches multiple documents, Spring Data may throw **IncorrectResultSizeDataAccessException**.

Example of an unsuitable declaration:

~~~java
Optional<Product> findByCategory(String category);
~~~

If the `accessories` category has 30 products, `Optional` cannot hold all 30 documents. Change the return type:

~~~java
List<Product> findByCategory(String category);
~~~

If business logic needs only the first product by an explicit rule, limit the result and specify the order:

~~~java
Optional<Product> findFirstByCategoryOrderByPriceAsc(String category);
~~~

Derived query naming and support for **First**, **Top**, or **OrderBy** depend on the Spring Data Elasticsearch version. When clearer control is needed, pass a `Pageable` of size 1 or build a query with sorting.

Do not rely on Elasticsearch's default ordering to pick “an arbitrary document.” Results can shift with scores, shards, segments, or updated data. If business logic requires the cheapest, newest, or highest-priority product, declare the corresponding sort explicitly.

## 5. Handling Empty Collections When Finding Multiple Documents

For multi-result queries, use **List<T>** or **Iterable<T>**. If there are no hits, an empty collection is returned.

~~~java
List<Product> products =
        productRepository.findByCategory("unknown");

if (products.isEmpty()) {
    System.out.println("Category has no products yet");
} else {
    products.forEach(product ->
            System.out.println(product.getName()));
}
~~~

Do not return `null` instead of an empty collection. An empty collection lets callers invoke **isEmpty()**, iterate in loops, or serialize to JSON without null checks.

Example service returning an empty list:

~~~java
public List<Product> findByCategory(String category) {
    return productRepository.findByCategory(category);
}
~~~

When there are no products, the controller can return HTTP 200 with an empty JSON array, if that is the chosen API contract:

~~~json
[]
~~~

This is usually appropriate for list endpoints. A list query returning zero items does not mean the endpoint resource itself does not exist.

### findAllById and Missing IDs

**findAllById(ids)** returns the entities found. Non-existent IDs do not produce `null` elements in the collection.

~~~java
List<String> requestedIds =
        List.of("p-1001", "p-1002", "p-9999");

List<Product> found = new ArrayList<>();
productRepository.findAllById(requestedIds).forEach(found::add);
~~~

If you need to identify which IDs are missing, compare the input ID list with the IDs of the results:

~~~java
Set<String> foundIds = found.stream()
        .map(Product::getId)
        .collect(Collectors.toSet());

List<String> missingIds = requestedIds.stream()
        .filter(id -> !foundIds.contains(id))
        .toList();
~~~

The order of entities in the result does not necessarily match the input ID order. If input ordering matters, reconstruct the result according to the original ID list.

## 6. Handling Empty Page and Slice

When a query needs pagination, a repository can return **Page<T>**:

~~~java
Page<Product> findByStatus(String status, Pageable pageable);
~~~

Invoking the query:

~~~java
Page<Product> page = productRepository.findByStatus(
        "ACTIVE",
        PageRequest.of(0, 20)
);

if (page.isEmpty()) {
    System.out.println("No ACTIVE products");
} else {
    System.out.println("Product count: " + page.getTotalElements());
}
~~~

An empty `Page` is still a valid `Page` object. You can call **getContent()**, **getTotalElements()**, **getTotalPages()**, and **hasNext()** without checking for null.

**Slice<T>** is suitable when the UI only needs to know whether a next page exists, without needing total elements:

~~~java
Slice<Product> slice = productRepository.findByStatus(
        "ACTIVE",
        PageRequest.of(0, 20)
);

if (slice.isEmpty()) {
    // No elements in the current slice.
}

if (slice.hasNext()) {
    Pageable nextPage = slice.nextPageable();
    // Load the next slice of results.
}
~~~

`Page` usually needs total element information to provide full metadata. `Slice` focuses on the current content and whether more data remains. Support for specific return types depends on the version and query method type.

## 7. Handling Empty SearchHits When Using ElasticsearchOperations

When using **ElasticsearchOperations.search(...)**, the result is typically **SearchHits<T>**. `SearchHits` is still returned when no documents match; its inner hit list is simply empty.

~~~java
Query query = new CriteriaQuery(
        Criteria.where("category").is("unknown")
);

SearchHits<Product> searchHits = operations.search(
        query,
        Product.class,
        IndexCoordinates.of("products")
);

if (searchHits.getSearchHits().isEmpty()) {
    System.out.println("No products found");
}
~~~

To extract entities from each hit:

~~~java
List<Product> products = searchHits.getSearchHits().stream()
        .map(SearchHit::getContent)
        .toList();
~~~

`SearchHits` also retains search metadata such as ID, score, source index, and highlights per hit. If you convert directly to `List<Product>`, that metadata is no longer included in the entity list.

Example reading scores:

~~~java
for (SearchHit<Product> hit : searchHits) {
    Product product = hit.getContent();

    System.out.println(
            product.getName() + " - score: " + hit.getScore()
    );
}
~~~

If you need to distinguish zero hits from a failed request, handle exceptions separately. Empty `SearchHits` means the request completed and returned zero hits; connection, query, or conversion errors are thrown as exceptions.

## 8. Distinguishing get, exists, and search When Documents Are Absent

Operations APIs have different contracts:

| API | When not found |
|---|---|
| **operations.get(id, Product.class, index)** | Typically returns `null` |
| **operations.exists(id, index)** | Returns `false` |
| **operations.search(query, Product.class, index)** | Returns `SearchHits` with an empty hit list |
| **repository.findById(id)** | Returns `Optional.empty()` |
| **repository.findAllById(ids)** | Returns collection containing only found entities |
| **repository.findByCategory(category)** | Returns empty collection if zero hits |

Example reading with Operations:

~~~java
Product product = operations.get(
        "p-9999",
        Product.class,
        IndexCoordinates.of("products")
);

if (product == null) {
    // No document with this ID.
}
~~~

If you only need to know whether a document exists:

~~~java
boolean exists = operations.exists(
        "p-9999",
        IndexCoordinates.of("products")
);
~~~

Do not call `exists()` followed by `get()` if the ultimate goal is fetching the entity. `get()` already tells you whether the document exists via a `null` result. Making two separate requests also opens a window in which the document could be deleted or changed between the check and the read.

## 9. Do Not Confuse Empty Results with Technical Errors

One serious design flaw is catching every exception and returning an empty collection or `Optional.empty()`. That causes the application to report “no data found” even when Elasticsearch is unreachable or mappings are broken.

Distinguish the categories:

| Category | Example | How to handle |
|---|---|---|
| Empty business result | No matching products | Return empty `Optional`, empty collection, or 404 per contract |
| Query error | Malformed Query DSL or unsuitable field | Fix query, mapping, or input data |
| Conversion error | Unable to convert JSON source to Java type | Check field, type, date format, and converter |
| Write error | Value violates mapping | Fix data or mapping |
| Connection error | Elasticsearch unreachable | Controlled retry, report infrastructure error |
| Auth/permission error | Account lacks read permission on index | Fix credential configuration or permissions |
| Overload/timeout error | Cluster cannot process request in time | Check load, timeouts, and query design |

An incorrect way to handle this:

~~~java
public List<Product> search(String category) {
    try {
        return productRepository.findByCategory(category);
    } catch (Exception exception) {
        return List.of();
    }
}
~~~

This code hides every technical failure. Callers cannot tell whether the category truly has no products or Elasticsearch is experiencing an outage.

Let technical errors propagate to an appropriate layer, log them with relevant context, and map them to the proper API error response.

## 10. Data Conversion Flow from Elasticsearch to Java

When Spring Data Elasticsearch reads a document, the JSON source must be converted into a Java object. **MappingElasticsearchConverter** uses entity metadata, annotations, and registered converters to perform this process.

Overview flow:

~~~text
Elasticsearch document (_source)
          |
          v
MappingElasticsearchConverter
          |
          +--> Entity metadata
          |
          +--> @Id / @Field / type information
          |
          +--> Custom conversions
          |
          v
Java object (Product)
          |
          v
Service / Repository caller
~~~

Example source:

~~~json
{
  "sku": "KB-1001",
  "name": "Mechanical Keyboard",
  "category": "accessories",
  "price": 89.5,
  "createdAt": "2026-10-20T09:30:00Z"
}
~~~

Corresponding entity:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private Double price;

    @Field(type = FieldType.Date)
    private Instant createdAt;

    // Constructor, getters, and setters.
}
~~~

Spring Data reads the source data, identifies matching fields, and converts values into Java types. If field names or data types mismatch, the object may lack values or conversion may throw an exception.

## 11. Field Name and Field Mapping Errors

A frequent cause is the JSON field name differing from the Java property name.

For example, source contains:

~~~json
{
  "created_at": "2026-10-20T09:30:00Z"
}
~~~

In Java, the property is named **createdAt**. Declare the field name explicitly:

~~~java
@Field(name = "created_at", type = FieldType.Date)
private Instant createdAt;
~~~

Without an appropriate naming rule, the converter may fail to locate the value by the Java property name, leaving the field `null` or at its default value.

Check:

- The actual name in **_source**.
- The Java property name.
- The **name** attribute on **@Field**.
- The application's naming strategy rules.
- The existing mapping on the index.

Do not inspect only the annotations in source code. The actual index mapping may be older than the entity because the index was created before code changes.

## 12. Data Type Mismatch Errors

Data in **_source** may be incompatible with the Java type.

For example, the entity declares:

~~~java
@Field(type = FieldType.Double)
private Double price;
~~~

Yet an older document has source:

~~~json
{
  "price": "eighty-nine"
}
~~~

A string value cannot be converted into `Double` by the default converter. Depending on where the failure occurs and the version, the application may receive **ConversionException**, **MappingException**, or an exception wrapped in the data access layer.

Several common cases:

| Source JSON | Expected Java type | Risk |
|---|---|---|
| `price` is string `"89.5"` | `Double` | May convert in some contexts, but numbers should be stored as proper JSON numbers |
| `price` is string `"unknown"` | `Double` | Cannot convert to number |
| `quantity` is `12.5` | `Integer` | May lose decimal fraction or fail conversion depending on converter |
| `active` is string `"yes"` | `Boolean` | String is not a standard boolean representation |
| `createdAt` is `"20/10/2026"` | `Instant` | Does not match expected date-time format |
| `tags` is `"keyboard"` | `List<String>` | Source is scalar while Java expects a collection |
| `address` is a JSON object | `String` | JSON object does not automatically become a string across all converters |

Standardize the data schema from the start. If the index already contains older documents in different formats, run a migration or write explicit custom converters for backward-compatible reading.

## 13. Date-Time and Date Format Errors

Dates and times are a common source of conversion failures. Elasticsearch mappings can accept certain formats, while Java types must also be compatible.

Example using `Instant`:

~~~java
@Field(type = FieldType.Date)
private Instant createdAt;
~~~

Source should use a clear ISO-8601 format:

~~~json
{
  "createdAt": "2026-10-20T09:30:00Z"
}
~~~

If legacy data uses a custom format, declare an appropriate format in the mapping and verify how the converter reads that value. With Spring Data annotations, you can specify the format:

~~~java
@Field(type = FieldType.Date, format = DateFormat.date_time)
private Instant createdAt;
~~~

Format names and temporal type support depend on the version. Elasticsearch mapping and Java converters must agree. Elasticsearch accepting a value on write does not automatically guarantee the Java converter can map it into every temporal type.

Do not use `String` for every date-time field just to bypass conversion errors if the application needs comparisons, range queries, or timezone handling. Choose appropriate temporal types and standardize input formats.

## 14. Enums and Custom Data Types

Enums are typically stored as name strings or representations configured by a converter. Example:

~~~java
public enum ProductStatus {
    ACTIVE,
    INACTIVE,
    DISCONTINUED
}
~~~

Entity:

~~~java
@Field(type = FieldType.Keyword)
private ProductStatus status;
~~~

Corresponding source:

~~~json
{
  "status": "ACTIVE"
}
~~~

If source contains a value absent from the enum, such as `ARCHIVED` before the enum defines `ARCHIVED`, the converter may throw an error on read. Plan enum changes carefully: update the enum, migrate old data, or use an intermediate type if multi-version compatibility is needed.

For custom types such as `Money`, `Address`, or value-object identifiers, register custom converters to define how they are written and read.

## 15. Using Custom Converters for Custom Data Types

Suppose the application has a `Money` type holding an amount and currency:

~~~java
public class Money {

    private final double amount;
    private final String currency;

    public Money(double amount, String currency) {
        this.amount = amount;
        this.currency = currency;
    }

    public double getAmount() {
        return amount;
    }

    public String getCurrency() {
        return currency;
    }
}
~~~

To store `Money` as a formatted string **89.50 USD**, write a reading converter:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class StringToMoneyConverter
        implements Converter<String, Money> {

    @Override
    public Money convert(String source) {
        String[] parts = source.trim().split("\\s+");

        if (parts.length != 2) {
            throw new IllegalArgumentException(
                    "Money value must be formatted as '<amount> <currency>'"
            );
        }

        double amount = Double.parseDouble(parts[0]);
        return new Money(amount, parts[1]);
    }
}
~~~

Writing converter:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class MoneyToStringConverter
        implements Converter<Money, String> {

    @Override
    public String convert(Money source) {
        return source.getAmount() + " " + source.getCurrency();
    }
}
~~~

Register the converters via **ElasticsearchCustomConversions** in your project's Spring Data Elasticsearch configuration:

~~~java
new ElasticsearchCustomConversions(
        List.of(
                new StringToMoneyConverter(),
                new MoneyToStringConverter()
        )
);
~~~

This creates the conversions object; the application must pass that object into the custom conversions configuration extension point of the Spring Data Elasticsearch version in use. How beans are declared or configurations overridden depends on your Spring Boot setup and library version. Do not just create converter classes and forget to register them, as `MappingElasticsearchConverter` will not know to use them.

Custom converters should validate data and throw informative errors for diagnostics. Do not silently coerce invalid values to 0 or a default value, as that can corrupt business data.

## 16. Distinguishing Read Conversion Errors from Write Mapping Errors

The two error groups occur at different moments:

**Read conversion errors**

- Elasticsearch returns source.
- Spring Data attempts to map source to the entity.
- A field has an incompatible type or format.
- The converter throws an exception.

**Write mapping errors**

- The application sends a document to Elasticsearch.
- Elasticsearch checks the index mapping.
- A value violates the field type or the mapping specifies **dynamic: strict**.
- Elasticsearch rejects the document and returns an error such as **mapper_parsing_exception**.

Example strict mapping:

~~~json
{
  "dynamic": "strict",
  "properties": {
    "sku": {
      "type": "keyword"
    },
    "price": {
      "type": "double"
    }
  }
}
~~~

If the application sends an undeclared field, Elasticsearch can reject the document due to strict dynamic mapping. This is an Elasticsearch-side write error, not a read-time source-to-Java conversion error.

Inspect the root exception and timing to distinguish the two groups. Fixing a converter will not resolve a strict mapping rejecting a new field; updating a mapping will not automatically fix malformed date strings in legacy source documents.

## 17. Inspecting Source and Mapping When Errors Occur

When a document fails to map, inspect the actual data first.

Read the mapping:

~~~http
GET /products/_mapping
~~~

Read the document by ID:

~~~http
GET /products/_doc/p-1001
~~~

Check several points:

- Does the field exist in **_source**?
- Is the value a string, number, boolean, array, or object?
- Does the field name match **@Field(name=...)**?
- Does the mapping have the right data type?
- Does the date format accept the value?
- Does the entity use a compatible Java type?
- Are custom converters registered?
- Was the document written by an older application version with a different schema?

If the mapping is correct but a few legacy documents have inconsistent data, you may need to repair data, run a migration, or build a compatible converter. Do not weaken Java types to mask the issue if doing so sacrifices data validation.

## 18. Disabled or Filtered `_source`

Spring Data typically needs **_source** to convert documents into entities. If an index was created with `_source` disabled, or a request fetches only part of source, the entity may not be fully populated.

Example mapping disabling source:

~~~json
{
  "mappings": {
    "_source": {
      "enabled": false
    },
    "properties": {
      "sku": {
        "type": "keyword"
      }
    }
  }
}
~~~

When `_source` is not stored, Elasticsearch cannot return the original JSON normally. Operations requiring conversion of source into `Product` will be limited or unable to restore entity properties as expected.

Source filtering in a search request can also return only certain fields:

~~~http
POST /products/_search
{
  "_source": [
    "sku",
    "name"
  ],
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
~~~

If `Product` also has `price` and `category`, those fields may remain unpopulated in the results because the request did not ask for them. This is not necessarily a converter error; the source data was restricted by the request.

When full entity mapping is needed, ensure requests return all required source fields or use a DTO matching the selected subset of fields.

## 19. Building Services That Handle Results and Errors Clearly

A service can encapsulate not-found rules while preserving technical errors:

~~~java
import java.util.List;
import java.util.Optional;

import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    private final ProductRepository repository;

    public ProductSearchService(ProductRepository repository) {
        this.repository = repository;
    }

    public Product getRequiredById(String id) {
        return repository.findById(id)
                .orElseThrow(() -> new ProductNotFoundException(id));
    }

    public Optional<Product> findById(String id) {
        return repository.findById(id);
    }

    public List<Product> findByCategory(String category) {
        return repository.findByCategory(category);
    }

    public Optional<Product> findBySku(String sku) {
        return repository.findBySku(sku);
    }
}
~~~

The service does not need to catch `DataAccessException` solely to return an empty collection. Data access errors should be handled where they can be logged, tagged with a correlation ID, and translated into an appropriate response.

If extra context must be attached to an error, catch a specific exception and rethrow a business/infrastructure exception preserving the cause:

~~~java
try {
    return repository.findByCategory(category);
} catch (DataAccessException exception) {
    throw new ProductSearchException(
            "Unable to search products by category " + category,
            exception
    );
}
~~~

Do not catch generic `Exception` and discard the cause. The cause contains the information needed to identify connection, query, mapping, or converter errors.

## 20. Mapping Results to HTTP Responses

APIs should reflect the data contract accurately.

Common conventions:

| Case | Typically appropriate HTTP response |
|---|---|
| GET a resource by ID and it does not exist | `404 Not Found` |
| Search a list and there are zero elements | `200 OK` with `[]` |
| Find a single resource by condition and there is no result | `404` or `204`, depending on endpoint contract |
| Invalid input query | `400 Bad Request` |
| Elasticsearch unreachable | `503 Service Unavailable` or appropriate gateway error |
| Unexpected mapping/conversion error | `500 Internal Server Error` |
| Successful request with data | `200 OK` |

Example controller fetching a single product:

~~~java
@GetMapping("/products/{id}")
public ResponseEntity<Product> getById(@PathVariable String id) {
    Product product = service.getRequiredById(id);
    return ResponseEntity.ok(product);
}
~~~

Exception handler:

~~~java
@RestControllerAdvice
public class ProductApiExceptionHandler {

    @ExceptionHandler(ProductNotFoundException.class)
    public ResponseEntity<String> handleNotFound(
            ProductNotFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(exception.getMessage());
    }
}
~~~

For a list endpoint:

~~~java
@GetMapping("/products")
public ResponseEntity<List<Product>> findByCategory(
        @RequestParam String category) {
    return ResponseEntity.ok(service.findByCategory(category));
}
~~~

If there are no products, the response body is an empty array. Do not turn converter errors into HTTP 404, because the document may exist while the application failed to read it.

Do not return stack traces, connection details, or internal Elasticsearch details to clients. Log on the server with a request ID and exception cause; return messages conforming to the API contract.

## 21. Verifying Results in Tests

Tests can cover three main groups: empty results, multiple results, and conversion errors.

### Testing Empty Optional

~~~java
@Test
void findByIdReturnsEmptyWhenProductDoesNotExist() {
    when(productRepository.findById("missing"))
            .thenReturn(Optional.empty());

    assertTrue(productService.findById("missing").isEmpty());
}
~~~

### Testing Empty Collection

~~~java
@Test
void findByCategoryReturnsEmptyListWhenNoProductMatches() {
    when(productRepository.findByCategory("unknown"))
            .thenReturn(List.of());

    assertTrue(productService.findByCategory("unknown").isEmpty());
}
~~~

### Testing Multiple Results

~~~java
@Test
void findByCategoryReturnsAllMatchingProducts() {
    List<Product> products = List.of(
            new Product("p-1", "KB-1", "Keyboard", "accessories", 80.0),
            new Product("p-2", "MS-2", "Mouse", "accessories", 25.0)
    );

    when(productRepository.findByCategory("accessories"))
            .thenReturn(products);

    assertEquals(
            2,
            productService.findByCategory("accessories").size()
    );
}
~~~

### Testing That Errors Are Not Turned into Empty Results

~~~java
@Test
void searchFailureIsNotReturnedAsEmptyList() {
    when(productRepository.findByCategory("accessories"))
            .thenThrow(new DataAccessResourceFailureException(
                    "Elasticsearch unavailable"
            ));

    assertThrows(
            DataAccessException.class,
            () -> productService.findByCategory("accessories")
    );
}
~~~

The tests above illustrate service contracts using mocks. To test real converters and mappings, write integration tests against a compatible Elasticsearch instance, create indices with expected mappings, and read/write documents with representative data.

## 22. Workflow for Diagnosing Conversion Errors

When a query reports an error while reading results, investigate in this sequence:

1. **Determine whether the request succeeded.** Distinguish HTTP/Elasticsearch errors from errors occurring after receiving the response.
2. **Read the root exception.** Look for `ConversionException`, `MappingException`, `ConverterNotFoundException`, or client error details.
3. **Identify the failing document and field.** Inspect ID, index, field name, and source value.
4. **Cross-check the entity.** Check `@Id`, `@Field`, Java types, and nested object structures.
5. **Inspect the actual mapping.** Do not assume mappings in code have been applied to the running index.
6. **Inspect dates, enums, and collections.** These types often have inconsistent data across application versions.
7. **Inspect custom conversions.** Confirm converters are registered and provide both read and write directions when needed.
8. **Inspect `_source`.** Confirm source is stored and the request returns all fields required for mapping.
9. **Create a test with the failing source.** Reproduce in a development environment to pinpoint the cause.
10. **Fix data or schema systematically.** Do not silently ignore invalid fields if they carry business meaning.

Exact exception names may vary across versions of Spring Data Elasticsearch, Spring Data Commons, and the Elasticsearch Java Client. Inspect the cause chain rather than relying solely on the outermost exception class.

## 23. Common Pitfalls

| Symptom | Possible cause | Resolution |
|---|---|---|
| `NullPointerException` when using `get` result | `operations.get(...)` returns `null` when ID does not exist | Check for null or wrap in a business exception |
| `NoSuchElementException` | Calling `Optional.get()` on an empty `Optional` | Use `orElseThrow`, `map`, or check `isPresent()` |
| `IncorrectResultSizeDataAccessException` | Single-entity/`Optional` query matches multiple documents | Change to `List`/`Page` or apply explicit limit and sort |
| Empty collection | Query succeeded with zero hits | Handle empty collection as a valid result |
| Empty page | No documents in page or query condition did not match | Check `isEmpty()` and `Pageable` parameters |
| Empty `SearchHits` | Search had no matching hits | Check `getSearchHits().isEmpty()` |
| `ConversionException` or `MappingException` | Source incompatible with entity type | Inspect source, mapping, and converters |
| Cannot read dates | Date format differs from expected Java type | Standardize ISO-8601 or configure consistent date formats |
| Enum causes error | Source contains value missing from enum | Synchronize enum and legacy data or use a converter |
| Java property is always null | Source field name differs from property name or source is filtered | Check `@Field(name=...)` and `_source` |
| Document write reports `mapper_parsing_exception` | Value violates mapping or `dynamic: strict` | Fix data, entity, or mapping |
| Search hits connection error yet service returns empty list | Exception caught too broadly | Preserve technical errors and handle them separately |

## 24. Result Contract Design Principles

When building repositories and services, apply these principles:

- Use **Optional<T>** when a query expects at most one document and non-existence is valid.
- Use **List<T>** or **Iterable<T>** when a query can return multiple documents.
- Use **Page<T>** or **Slice<T>** when pagination is needed.
- Use **SearchHits<T>** when score, highlights, or per-hit metadata are needed.
- Check for null with **ElasticsearchOperations.get(...)**.
- Treat empty collections, `Page`, and `SearchHits` as normal outcomes.
- Do not declare single-result return types for conditions that can match multiple documents.
- Do not turn query, connection, or converter errors into empty results.
- Keep Elasticsearch mappings and Java types compatible.
- Standardize dates, enums, collections, and value objects.
- Register custom converters when data types require custom conversion rules.
- Inspect `_source` and actual mappings when entity fields are missing.

Good search result handling starts with the return-type contract. **Optional** represents zero or one document; collections, `Page`, and `SearchHits` represent potentially empty result sets; single-result queries matching multiple documents must be redesigned or explicitly bounded. Conversion errors happen at a different layer: Spring Data cannot map source to entities using current metadata and converters. Separating empty results, cardinality mismatches, and conversion failures lets the application produce accurate responses while making Elasticsearch troubleshooting much clearer.
