# Mapping Results to DTOs and Projections by Supported API

Search results from Elasticsearch are usually mapped into domain entities that the application uses to write and read documents. However, APIs returning results to users do not always need the entire entity. A listing screen might need only ID, name, and price; an admin page might additionally need status and update timestamp; a public API might need a dedicated DTO structure to avoid exposing internal fields.

Spring Data Elasticsearch offers multiple ways to handle results:

- Mapping hits into entities and then converting them into DTOs in the service.
- Asking `ElasticsearchOperations` to map results into a different target type if the API version provides an appropriate result type overload.
- Using a projection interface or projection class in repositories on query paths supported by the version.
- Retaining `SearchHit` and `SearchHits` when score, sort values, highlights, index name, or other metadata are needed.
- Using source filtering to limit the `_source` returned, combined with DTOs/projections where appropriate.

These approaches are not wholly interchangeable. You need to distinguish document source, the Java target type receiving results, and hit metadata to choose the right API.

## 1. How Do Entity, DTO, and Projection Differ?

Suppose the `Product` entity is used to store documents:

~~~java
@Document(indexName = "products")
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
    private String internalSupplierCode;

    // constructors, getters and setters
}
~~~

The product listing API needs only three values:

~~~java
public record ProductSummary(
    String id,
    String name,
    Long priceInCents
) {
}
~~~

Three concepts:

| Concept | Role |
|---|---|
| Entity/domain object | Core data model of the application, typically tied to document mapping |
| DTO (Data Transfer Object) | Data type serving a specific exchange flow or response |
| Projection | Representation of a subset of entity data as a view/interface or target type |

A DTO does not have to be an Elasticsearch entity and does not need to contain every document field. A projection usually describes a subset of fields to read. In Spring Data, a projection can be an interface or class depending on the supported mechanism and query path.

Do not expose entities directly from APIs simply because the repository returns entities. DTOs help control API contracts, field names, allowed display data, and the ability to evolve internal structures.

## 2. Search Result Mapping Flow

A search request can pass through the following steps:

~~~text
Elasticsearch index
       |
       v
Search response
       |
       +---- _source document
       |
       +---- hit metadata
       |       - _id
       |       - _score
       |       - sort values
       |       - highlights
       |       - index
       |
       v
Spring Data SearchHit / SearchHits
       |
       v
Mapping converter
       |
       v
Entity or result type
       |
       v
DTO / API response
~~~

Two groups of data should be distinguished:

**Document content** is content mapped into a Java object, typically based on `_source` and mapping metadata.

**Hit metadata** is information returned by the Search API outside `_source`, such as document ID, score, sort values, highlight fields, and index name.

If you receive only `List<Product>`, the application typically works only with content. If relevance score or highlights are needed for displaying results, retain `SearchHit<Product>` or `SearchHits<Product>` instead of discarding metadata upfront.

## 3. Simple and Stable Approach: Read Entity Then Map to DTO

The easiest approach to control is fetching entities via `ElasticsearchOperations` or a repository, then transforming each result into a DTO in the service layer.

~~~java
public record ProductSummary(
    String id,
    String name,
    Long priceInCents
) {
}
~~~

Service:

~~~java
public List<ProductSummary> searchSummaries(Query query) {
    SearchHits<Product> searchHits =
        operations.search(query, Product.class);

    return searchHits.getSearchHits().stream()
        .map(SearchHit::getContent)
        .map(product -> new ProductSummary(
            product.getId(),
            product.getName(),
            product.getPriceInCents()
        ))
        .toList();
}
~~~

Advantages:

- Easy to read and debug.
- Does not depend on projection APIs specific to a minor version.
- Allows renaming fields, combining multiple sources, or applying business rules when building DTOs.
- Avoids placing DTO types into Elasticsearch mapping metadata.
- Clearly controls which fields are exposed to the API.

The drawback is that Spring Data still maps the document into `Product` first, and then the application instantiates `ProductSummary`. If documents have many fields or result counts are large, this can allocate extra objects and transfer unnecessary data.

If only a few fields are needed from very large documents, consider source filtering or a direct result type API if supported by the version.

### 3.1. Using a Dedicated Mapper When DTOs Have Logic

When multiple services build `ProductSummary`, you can extract a mapper:

~~~java
@Component
public class ProductSummaryMapper {

    public ProductSummary toSummary(Product product) {
        return new ProductSummary(
            product.getId(),
            product.getName(),
            product.getPriceInCents()
        );
    }
}
~~~

Service:

~~~java
return searchHits.getSearchHits().stream()
    .map(SearchHit::getContent)
    .map(productSummaryMapper::toSummary)
    .toList();
~~~

Mappers fit well when there are rules such as currency formatting, converting enums to labels, computing display fields, or combining data from multiple objects. Do not put API-specific logic into entities just to serve a single response.

## 4. Mapping Directly to a Result Type with ElasticsearchOperations

Some versions of Spring Data Elasticsearch provide overloads separating:

- The class used to determine entity/domain metadata and index.
- The result type used to map returned documents.

Common API form:

~~~java
SearchHits<ProductSummary> hits =
    operations.search(
        query,
        Product.class,
        ProductSummary.class
    );
~~~

Here `Product` is the source entity type, and `ProductSummary` is the target result type. Some versions also provide an overload accepting `IndexCoordinates`:

~~~java
SearchHits<ProductSummary> hits =
    operations.search(
        query,
        Product.class,
        ProductSummary.class,
        IndexCoordinates.of("products")
    );
~~~

The benefit is asking the mapping converter to instantiate the result type directly while reading the search response, avoiding an intermediate `Product` object in the service.

**Version note:** signatures and support levels for result type overloads vary across Spring Data Elasticsearch generations. Inspect `ElasticsearchOperations` in your actual dependency via IDE/Javadoc. If the project lacks this overload, read the entity and map to a DTO, or use a projection mechanism supported by the version. Do not write a custom method of the same name to mimic a framework API.

### 4.1. DTOs Need a Structure Compatible with the Mapping Converter

Class-based DTO example:

~~~java
public class ProductSummary {

    private String id;
    private String name;
    private Long priceInCents;

    public ProductSummary() {
    }

    public ProductSummary(
            String id,
            String name,
            Long priceInCents) {
        this.id = id;
        this.name = name;
        this.priceInCents = priceInCents;
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public Long getPriceInCents() {
        return priceInCents;
    }

    public void setId(String id) {
        this.id = id;
    }

    public void setName(String name) {
        this.name = name;
    }

    public void setPriceInCents(Long priceInCents) {
        this.priceInCents = priceInCents;
    }
}
~~~

The mapping converter must know how to instantiate and populate the result type. Constructor binding, record support, property access, and parameter names depend on the mapping infrastructure and Spring Data version.

If the DTO uses a record or immutable constructor, ensure parameter names/order can be recognized by Spring Data and corresponding fields can be converted. If instantiation errors occur, try a DTO class with a no-args constructor and setters to distinguish constructor mapping issues from data issues.

### 4.2. The ID Field Must Be Handled Explicitly

The Elasticsearch document ID usually lives in `_id` metadata, not necessarily as a field inside `_source`. If the DTO requires the ID, declare an appropriate property and verify whether the result-type mapping API in your version populates the ID from hit metadata into the DTO.

When unsure, keep `SearchHit` and use `hit.getId()` to build the DTO:

~~~java
ProductSummary summary = new ProductSummary(
    hit.getId(),
    hit.getContent().getName(),
    hit.getContent().getPriceInCents()
);
~~~

This avoids assuming `_id` was stored inside `_source`.

## 5. Interface-Based Projections in Repositories

Spring Data Commons provides an interface projection mechanism. An interface declares the getters the application needs:

~~~java
public interface ProductNameView {

    String getName();

    Long getPriceInCents();
}
~~~

In a repository, you can declare a projection return type on query methods supported by your Spring Data Elasticsearch version:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<ProductNameView> findByCategory(String category);
}
~~~

The goal is receiving a view containing only needed properties instead of depending directly on the full entity.

However, do not assume every type of repository method supports projections identically. Verify against the exact version and query type in use, especially for:

- Derived query methods.
- Methods using `@Query`.
- Native queries.
- `SearchHit` or `SearchHits` wrappers.
- Dynamic projections accepting `Class<T>` as a parameter.
- Projections with nested properties or computed accessors.

If a method is unsupported or Spring cannot instantiate the projection proxy, use `ElasticsearchOperations` and map DTOs explicitly.

### 5.1. Closed Projections

A closed projection declares getters only for properties present on the domain object:

~~~java
public interface ProductCard {

    String getName();

    Long getPriceInCents();
}
~~~

Because getters match specific properties, Spring Data can know upfront what data the view requires. Whether Elasticsearch actually trims the returned data depends on the version's query implementation and source filtering behavior.

Do not assume that declaring a closed projection guarantees Elasticsearch only reads those two fields. Inspect the actual request if payload optimization is a strict requirement.

### 5.2. Open Projections

An open projection can use expressions to compute values from the target object in mechanisms supported by Spring Data Commons:

~~~java
public interface ProductLabel {

    @Value("#{target.name + ' - ' + target.priceInCents}")
    String getLabel();
}
~~~

This is an example of Spring Data Commons' projection mechanism. Support for open projections across specific Spring Data Elasticsearch repository query paths must be verified per version.

Open projections may require the entire target object to evaluate expressions, and thus typically do not provide the same field-limiting benefit as property-only projections.

If computation logic is complex or requires calling services, map to DTOs in the application layer rather than putting logic inside projection expressions.

### 5.3. Dynamic Projections

Some repository abstractions support methods taking a `Class<T>` parameter so callers choose the projection:

~~~java
<T> List<T> findByCategory(
    String category,
    Class<T> projectionType
);
~~~

Example usage:

~~~java
List<ProductNameView> names =
    productRepository.findByCategory(
        "accessories",
        ProductNameView.class
    );

List<Product> entities =
    productRepository.findByCategory(
        "accessories",
        Product.class
    );
~~~

This is Spring Data's dynamic projection pattern. Before using it with Elasticsearch repositories, check whether your version supports dynamic projections for that query type. Do not assume that because Spring Data JPA supports a method pattern, Spring Data Elasticsearch behaves identically.

## 6. Class-Based Projections and DTO Constructors

Class-based projections typically use a DTO with a constructor taking the required properties:

~~~java
public record ProductCardDto(
    String name,
    Long priceInCents
) {
}
~~~

With Spring Data Commons, constructor projections must be able to match which parameters correspond to domain properties. Records with clear component names can work with constructor mapping in supported versions.

Distinguish two cases:

1. Repository projection: a Spring Data repository query constructs the projection return type via the repository mechanism.
2. Operations result type: `ElasticsearchOperations` is instructed to read search results into a specific target class if that overload is available.

The two mechanisms may share mapping infrastructure, yet their APIs, limitations, and returned metadata differ. When in doubt, inspect API signatures and write a small integration test against the actual dependency version.

## 7. SearchHit and SearchHits: Preserving Result Metadata

If only content is needed, you can extract the list of objects from `SearchHits`. But when ranking or hit information is needed, keep the wrapper.

A `SearchHit<T>` holds content along with metadata, typically including:

- Document ID.
- Index name.
- Score.
- Sort values.
- Highlight fields.
- Explanation if requested by the query.
- Inner hits when the query uses `inner_hits`.

`SearchHits<T>` contains the set of `SearchHit` items and general information such as total hits, total-hits relation, max score, and other search metadata depending on the API.

Example:

~~~java
SearchHits<Product> searchHits =
    operations.search(query, Product.class);

for (SearchHit<Product> hit : searchHits) {
    Product product = hit.getContent();

    System.out.println("id = " + hit.getId());
    System.out.println("score = " + hit.getScore());
    System.out.println("index = " + hit.getIndex());
    System.out.println("name = " + product.getName());
}
~~~

Do not convert `SearchHits` into `List<Product>` immediately if the API layer still needs scores or highlights. Metadata does not reside inside `Product` and can be lost when extracting only content.

### 7.1. Mapping SearchHit to DTO While Preserving Score

If the API response needs both DTO fields and relevance score, create a dedicated response model:

~~~java
public record ProductSearchResult(
    String id,
    String name,
    Long priceInCents,
    float score
) {
}
~~~

Mapping:

~~~java
List<ProductSearchResult> results =
    searchHits.getSearchHits().stream()
        .map(hit -> {
            Product product = hit.getContent();

            return new ProductSearchResult(
                hit.getId(),
                product.getName(),
                product.getPriceInCents(),
                hit.getScore()
            );
        })
        .toList();
~~~

This keeps necessary metadata in the API contract without forcing the DTO to be an Elasticsearch entity.

### 7.2. Highlight Fields

If the query enables highlighting, `SearchHit` can hold highlighted snippets per field:

~~~java
for (SearchHit<Product> hit : searchHits) {
    List<String> fragments =
        hit.getHighlightField("description");

    // Map fragments into the API response.
}
~~~

Verify exact method names and return types against your API version. Highlights are hit metadata, not updated source content. Do not write highlight fragments back into the entity as if they were original data.

## 8. Pagination and SearchPage

When a repository or `Operations` returns paginated results, distinguish:

- `Page<T>`: content along with page info and total elements.
- `SearchHits<T>`: hits and search metadata.
- `SearchPage<T>`: page abstraction wrapping search hits, preserving result metadata.

Some repository query methods support returning `SearchPage` or `SearchHits` with `Pageable` depending on query type and version.

Example repository method signature:

~~~java
SearchPage<Product> findByCategory(
    String category,
    Pageable pageable
);
~~~

When using `Operations`, you can obtain `SearchHits` and convert it into a page abstraction using utilities provided by the Spring Data version, such as `SearchHitSupport` if available in your current API.

Do not calculate total pages yourself from the current hit count if the Search API returns only a single page. If the UI does not require an exact total, consider result forms that do not require a total count or cap it according to actual needs.

### 8.1. Deep Pagination

Projections or DTOs do not eliminate the cost of deep pagination. With large `from`/`size`, Elasticsearch still has to process results prior to the offset. If traversing large datasets is required, consider `search_after` with a stable sort or `scroll` for batch jobs per API semantics.

## 9. Source Filtering: Fetching Only Part of `_source`

DTOs/projections determine which Java type the application receives. Source filtering determines which parts of `_source` Elasticsearch returns.

REST DSL example:

~~~http
POST /products/_search
{
  "_source": [
    "name",
    "priceInCents"
  ],
  "query": {
    "term": {
      "category": "accessories"
    }
  }
}
~~~

The request asks for only two fields in `_source`. This can reduce payloads when documents contain large amounts of data.

Include/exclude patterns can be used:

~~~http
POST /products/_search
{
  "_source": {
    "includes": ["name", "priceInCents", "brand"],
    "excludes": ["internalNotes", "supplierSecrets"]
  },
  "query": {
    "match_all": {}
  }
}
~~~

Remember:

- Source filtering does not change the index mapping.
- It does not delete fields from stored documents.
- It does not replace authorization.
- A field excluded from the response can leave the corresponding DTO property null/default.
- Metadata such as `_id` and `_score` reside outside `_source`.

If a DTO needs the ID, confirm whether the ID is mapped from hit metadata or must be fetched explicitly from `SearchHit`.

### 9.1. Source Filtering Is Not Stored Fields

`_source` filtering picks which part of the JSON source is returned. Stored fields are a separate Elasticsearch mechanism requiring corresponding field mappings. Do not use the terms source filtering and stored fields interchangeably.

If only a few fields are needed for display, source filtering is usually the simpler approach. If finer payload control is needed or fields have special structures, check the Search API and actual mapping.

## 10. NativeQuery and Source Filters in Spring Data Elasticsearch

With Spring Data Elasticsearch 5.x, `NativeQuery` uses the Elasticsearch Java API Client. Some versions provide a builder to configure a source filter.

Illustrative example:

~~~java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.FetchSourceFilter;

NativeQuery query = NativeQuery.builder()
    .withQuery(elasticsearchQuery)
    .withSourceFilter(
        new FetchSourceFilter(
            new String[] {"name", "priceInCents"},
            new String[] {"internalNotes"}
        )
    )
    .build();
~~~

Class names, packages, and builder methods may vary by minor version. Inspect `NativeQuery.Builder` and `FetchSourceFilter` in your active dependency. If the API does not expose this configuration, use the query abstraction or Elasticsearch Java API Client corresponding to the version.

Do not set the source filter too narrowly if the mapping converter needs another field to construct the DTO or if the service still needs data to apply business rules.

## 11. Mapping DTOs from SearchHit Explicitly

A practical pattern is keeping `SearchHit` in the service and constructing API DTOs:

~~~java
public record ProductSearchResponse(
    String id,
    String name,
    Long priceInCents,
    float score,
    List<String> nameHighlights
) {
}
~~~

Service:

~~~java
public List<ProductSearchResponse> search(Query query) {
    SearchHits<Product> hits =
        operations.search(query, Product.class);

    return hits.getSearchHits().stream()
        .map(hit -> {
            Product product = hit.getContent();

            List<String> highlights =
                hit.getHighlightField("name");

            return new ProductSearchResponse(
                hit.getId(),
                product.getName(),
                product.getPriceInCents(),
                hit.getScore(),
                highlights
            );
        })
        .toList();
}
~~~

The example assumes the query configured highlighting for the `name` field. If there are no highlights, the list may be empty. Handle nullability according to your version's return type and ensure the response DTO does not depend on implementation details of `SearchHit`.

This pattern works well when the API needs to coordinate content, score, highlights, or index metadata.

## 12. Projections Do Not Automatically Replace Security and Validation

A projection only limits the properties exposed in a view. It is not an authorization mechanism.

For example, `ProductPublicView` omits `internalSupplierCode`:

~~~java
public interface ProductPublicView {
    String getName();
    Long getPriceInCents();
}
~~~

That does not mean the user is authorized to access the product data. Queries must still be scoped by tenant, access permissions, status, or required security conditions.

Similarly, source filtering removes fields from responses without replacing application-layer access control. Enforce authorization before querying and design response DTOs according to the public contract.

Do not return `SearchHit`, entities, or raw `_source` directly from an API if those structures may contain internal metadata or fields not intended for clients.

## 13. Nested DTOs and Fields Missing from Source

A DTO can have a different structure from the entity:

~~~java
public record ProductCard(
    String name,
    PriceView price
) {
}

public record PriceView(
    Long amountInCents,
    String currency
) {
}
~~~

For direct mapping to work, the source structure and mapping converter must have matching data or appropriate custom conversions. If the entity stores `amountInCents` while the DTO requires a `PriceView` object whose `currency` comes from configuration, the converter cannot know that business rule automatically unless declared.

When a DTO aggregates multiple fields or sources, manual mapping in the service is usually clearer.

If a field in the DTO does not exist in `_source`:

- The property may receive `null` or a default value.
- A required constructor may fail to instantiate the object if parameters are missing.
- A custom converter may need additional logic.
- Metadata may need to be read from `SearchHit` instead of `_source`.

Distinguish a field missing from the document from a field excluded from the response by source filtering. Both situations can produce identical Java values, yet have different root causes.

## 14. When to Use Direct DTO Mapping, Projections, or Manual Mapping?

| Approach | Suitable when | Considerations |
|---|---|---|
| Entity then map DTO | Business logic is needed or a clear, stable approach is preferred | Involves creating an intermediate entity |
| Operations result type | Version has overload taking domain type and result type; DTO maps directly | API depends on version and constructor/property mapping |
| Interface projection | Query path supports projections and a simple view suffices | Not every query type/wrapper supports it |
| Class/record projection | Immutable DTO type or specific return structure is needed | Constructor binding and property names must align |
| SearchHit + DTO | Score, highlights, sort values, or index metadata are needed | Both content and metadata must be mapped explicitly |
| Source filtering + DTO | Documents are large and only part of `_source` is needed | Missing fields can leave DTO mapping incomplete |

Practical rule:

- Start with entity-then-DTO mapping when predictable behavior is important.
- Use direct result types when supported by your `Operations` version and DTO mapping is simple.
- Use projection interfaces when the repository query path has been verified as supported.
- Keep `SearchHit` when metadata is needed.
- Add source filtering when reducing payloads and required fields are well known.

## 15. Testing DTO and Projection Mapping

Write integration tests against an Elasticsearch test instance to verify actual mapping behavior, especially when using result types or projections.

Example testing entity mapping followed by DTO conversion:

~~~java
@Test
void shouldMapSearchHitToSummary() {
    Product product = new Product(
        "P-1001",
        "SKU-1001",
        "Wireless Mouse",
        259900L,
        true,
        "SUPPLIER-SECRET"
    );

    operations.save(product);
    indexOperations.refresh();

    SearchHits<Product> hits =
        operations.search(query, Product.class);

    Product actual = hits.getSearchHit(0).getContent();

    ProductSummary summary = new ProductSummary(
        hits.getSearchHit(0).getId(),
        actual.getName(),
        actual.getPriceInCents()
    );

    assertThat(summary.id()).isEqualTo("P-1001");
    assertThat(summary.name()).isEqualTo("Wireless Mouse");
    assertThat(summary.priceInCents()).isEqualTo(259900L);
}
~~~

For direct result types or repository projections, write dedicated tests verifying:

- The DTO is instantiated properly.
- Fields hold values of the expected types.
- The ID is populated from `_id` or not.
- Fields omitted by source filtering receive expected `null`/default values.
- Projections do not unintentionally expose internal fields.
- `SearchHit` metadata is preserved if the API needs score/highlights.
- Pagination and total hits have accurate semantics.

Do not merely assert that the list is non-null. Assert key values and missing-field cases.

## 16. Common Pitfalls

| Symptom | Possible cause | How to check |
|---|---|---|
| DTO property is null | Property name does not match source or mapping converter | Check `_source` and property names |
| DTO cannot be instantiated | Constructor binding or parameter types mismatch | Try no-args constructor/setters and inspect mapping metadata |
| DTO ID is null | `_id` sits outside `_source` and wasn't mapped from hit metadata | Read ID from `SearchHit.getId()` |
| Interface projection not created | Query path/version does not support that projection | Check API version and use manual DTO mapping |
| Dynamic projection does not work | Repository method does not support `Class<T>` projection | Check Spring Data version/query derivation |
| SearchHit metadata is lost | Converting `SearchHits` to content list too early | Keep `SearchHit` until building the response |
| Empty highlights | Query did not configure highlighting or field names mismatch | Check highlight query and field names |
| DTO missing data after source filtering | Include/exclude dropped required fields | Check source filter and DTO constructor |
| Result type overload fails to compile | API lacks that overload in current dependency | Check Javadoc/IDE for `ElasticsearchOperations` |
| Projection leaks unintended data | Exposing entity or raw source directly in API | Create response DTO with explicit allowed fields |
| SearchPage loses metadata | Keeping only content instead of the wrapper | Retain `SearchHits`/`SearchPage` when total and hit metadata are needed |

## 17. Workflow for Choosing an API

When designing search results for an endpoint:

1. Decide whether the endpoint needs the full entity or only a subset of fields.
2. Decide whether score, highlights, sort values, index name, or total hits are needed.
3. If only a simple response DTO is needed, consider entity-to-DTO mapping or result-type API if available.
4. If using repository projections, verify query method and version support.
5. If documents are large, consider source filtering while keeping fields needed by the DTO.
6. If metadata is needed, keep `SearchHit`/`SearchHits` until the response is built.
7. Write integration tests for IDs, constructor mapping, null/missing fields, and source filtering.
8. Ensure DTOs do not become a substitute for authorization.

## 18. Quick Reference Table

| Need | API/implementation approach |
|---|---|
| Return simple DTO | Search entity then map DTO |
| Map directly to result type | `ElasticsearchOperations` domain-type/result-type overload if supported by version |
| View with getters only | Interface projection on a supported repository query path |
| Immutable DTO | Class/record projection if constructor mapping is supported |
| Need score and index metadata | `SearchHit<T>` / `SearchHits<T>` |
| Need highlights | `SearchHit` highlight metadata |
| Need pagination and total | `Page`/`SearchPage` or `SearchHits` with `Pageable` per API version |
| Reduce `_source` payload | Source filtering |
| Need DTO aggregated from multiple fields/sources | Map manually in service |
| Protect internal fields | Response DTOs and authorization; do not rely solely on projections |

Mapping results to DTOs and projections decouples document structure from API contracts. Distinguish content from hit metadata, use `Operations` result types or repository projections when supported by your version, and keep `SearchHit`/`SearchHits` if score, highlights, or pagination info are needed. When projection APIs are unclear or DTOs require business logic, mapping entities to DTOs in the service is the most controllable approach. Source filtering can reduce payloads, but does not replace mapping, validation, or authorization.
