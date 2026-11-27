# Sorting by Keyword, Numeric, Date, and Multiple Fields

Elasticsearch sorts documents based on the field's mapping type and the values stored in the index. A sort request can use `keyword` strings, numbers, dates/times, or combine multiple fields in priority order. In Spring Data Elasticsearch, you can declare a fixed sort in a repository method, pass a `Sort`, or include sorting in a `Pageable`; for advanced options such as missing values, multi-value modes, or nested sorts, finer control over Query DSL is required.

Crucially, the field must have an appropriate mapping and a structure that supports sorting. A `text` field used for full-text search usually cannot be sorted directly; `keyword`, numeric, and date fields typically have doc values so Elasticsearch can read values efficiently.

## 1. How Elasticsearch Sorts Results

Sorting is declared in the `sort` section of the Search API. Elasticsearch evaluates criteria from left to right: the first criterion determines the primary order; subsequent criteria are only used when documents tie on the preceding criteria.

Example of sorting by price ascending:

~~~http
GET /products/_search
Content-Type: application/json

{
  "query": { "match_all": {} },
  "sort": [
    { "price": { "order": "asc" } }
  ]
}
~~~

`asc` is ascending and `desc` is descending. For numeric fields, ascending means smaller numbers come first. For date fields, ascending means earlier timestamps come first. For `keyword`, the order is based on term values, typically lexicographical/byte order of the normalized terms.

Sorting is different from relevance ranking. If no explicit sort is declared, full-text queries normally sort by `_score` descending. When sorting by a field is declared, results are ordered by that field; `_score` is only used if added as a sort criterion.

## 2. Mapping Requirements for Sorting

Elasticsearch typically uses **doc values** to sort by a field. Doc values are a columnar data structure optimized for reading field values across many documents.

Commonly used field types for sorting:

| Field type | Standard sorting | Usage examples |
| --- | --- | --- |
| `keyword` | Yes; doc values are enabled by default unless disabled. | SKU, status, category, normalized name. |
| `long`, `integer`, `short`, `byte` | Yes; sorted by numeric value. | Quantity, price in cents, priority order. |
| `float`, `double`, `scaled_float` | Yes; sorted by numeric value. | Score, ratio, measured value. |
| `date`, `date_nanos` | Yes; sorted by timestamp. | Creation date, publish date, deadline. |
| `boolean` | Yes, according to Elasticsearch boolean value ordering. | Active or published flags. |
| `text` | No doc values by default, so cannot be sorted directly in the standard way. | Use a `keyword` subfield for string sorting. |

If a field has `doc_values: false`, doc-values-based sorting is unavailable. For `text`, Elasticsearch offers `fielddata`, but enabling fielddata can consume significant heap; the standard design is adding a `keyword` multi-field rather than enabling fielddata solely for sorting.

## 3. Sorting by `keyword`

A `keyword` field stores values as intact terms, making it suitable for exact match, aggregations, and sorting. It is a common choice for identifiers, statuses, categories, normalized names, or values that require string sorting.

Example mapping:

~~~json
{
  "mappings": {
    "properties": {
      "sku": { "type": "keyword" },
      "status": { "type": "keyword" },
      "category": { "type": "keyword" }
    }
  }
}
~~~

Sort by SKU ascending:

~~~json
{
  "sort": [{ "sku": { "order": "asc" } }]
}
~~~

Sort by status descending:

~~~json
{
  "sort": [{ "status": { "order": "desc" } }]
}
~~~

### 3.1. String Order Is Not Numeric Order

`keyword` sorts as strings without parsing content as numbers. If you store `"2"`, `"10"`, and `"100"` in a keyword field, string order can differ from the numeric order users expect.

| Value | Illustrative string order | Numeric order if converted to numbers |
| --- | ---: | ---: |
| `"10"` | Before `"2"` | After `2` |
| `"100"` | Before `"2"` | After `10` |
| `"2"` | After `"100"` in standard lexicographical order | Before `10` and `100` |

If the data has numeric meaning, map it to a numeric type rather than `keyword`. Do not fix numeric sorting by zero-padding strings if the field actually needs range queries or arithmetic.

### 3.2. Letter Case and Normalizers

Default keyword sorting does not automatically understand natural language alphabet rules. Values like `Acme`, `ACME`, and `acme` can be treated as distinct terms and ordered differently from UI expectations.

You can use a normalizer to standardize values before indexing. Example lowercase normalizer:

~~~json
{
  "settings": {
    "analysis": {
      "normalizer": {
        "folded_keyword": {
          "type": "custom",
          "filter": ["lowercase", "asciifolding"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "brand": {
        "type": "keyword",
        "normalizer": "folded_keyword"
      }
    }
  }
}
~~~

Normalizing changes how terms are stored for search and sorting. Verify the impact on exact match and aggregations. If language-specific collation rules are needed—such as Vietnamese diacritic ordering—lowercase/asciifolding is insufficient to mimic locale dictionary order. You may need the ICU analysis plugin and a dedicated sort field configured with the appropriate collation.

## 4. Sorting by Display Strings Using a Multi-Field

A Java `String` property often needs both full-text search and whole-string sorting. The mapping should use a primary `text` field and a `keyword` subfield:

~~~json
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "analyzer": "standard",
        "fields": {
          "sort": {
            "type": "keyword",
            "normalizer": "folded_keyword",
            "ignore_above": 256
          }
        }
      }
    }
  }
}
~~~

The primary `name` field is used for `match` queries. The `name.sort` subfield is used for sorting, exact match, or aggregations. A single value in `_source` is indexed both ways without adding a second Java property.

Example sorting by name:

~~~json
{
  "sort": [{ "name.sort": { "order": "asc" } }]
}
~~~

`ignore_above` limits the string length indexed in the keyword subfield. If a value exceeds the limit, the primary field can still be stored in `_source` and searched as `text`, but `name.sort` may have no value for sorting. Choose the limit based on real data and define how missing values should be handled.

### 4.1. Declaring a Multi-Field in Spring Data

You can describe a multi-field using `@MultiField` and `@InnerField`:

~~~java
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.InnerField;
import org.springframework.data.elasticsearch.annotations.MultiField;

@MultiField(
    mainField = @Field(type = FieldType.Text, analyzer = "standard"),
    otherFields = {
        @InnerField(suffix = "sort", type = FieldType.Keyword)
    }
)
private String name;
~~~

These annotations describe a mapping corresponding to `name` as text and `name.sort` as keyword. If a normalizer is required, configure it on the inner field using the attribute supported by your project's Spring Data Elasticsearch version or declare the mapping via a JSON file. Verify the actual mapping after the index is created.

Do not enable `fielddata: true` on `text` solely for sorting in typical cases. Fielddata can load large amounts of data into the heap; a keyword multi-field is generally more suitable.

## 5. Sorting by Numbers

When a field is mapped to a numeric type, Elasticsearch compares actual numeric values rather than string representations.

Example mapping:

~~~json
{
  "mappings": {
    "properties": {
      "priceInCents": { "type": "long" },
      "quantity": { "type": "integer" },
      "rating": { "type": "float" }
    }
  }
}
~~~

Sort by price ascending:

~~~json
{
  "sort": [{ "priceInCents": { "order": "asc" } }]
}
~~~

Sort by rating descending:

~~~json
{
  "sort": [{ "rating": { "order": "desc" } }]
}
~~~

### 5.1. Choosing the Right Numeric Type

| Type | When to use |
| --- | --- |
| `byte`, `short`, `integer`, `long` | Integer values, quantities, monetary amounts stored in the smallest currency unit. |
| `float`, `double` | Decimal values where approximate floating-point comparison is appropriate. |
| `scaled_float` | Decimal values stored using a configured scaling factor. |

For currency, it is usually best to store integers in the smallest unit (e.g., cents) to avoid floating-point precision errors. If multiple currencies are needed, determine the currency and comparison rules before sorting; amounts in different currencies cannot be compared directly as if they share the same unit.

Do not map a numeric field as `keyword` just because incoming input is currently sent as strings. Convert and validate data types at the application boundary before indexing.

### 5.2. Sorting by Computed Values

If the sort value is calculated from multiple fields, consider:

- Computing and storing a derived field when writing the document, if the formula is stable and used frequently.
- Using a `script` sort when the logic genuinely must be evaluated at query time.

Script sorting is flexible but typically more expensive than sorting on a pre-existing field and may limit optimizations. If the formula is stable, storing a derived value is usually easier to operate.

## 6. Sorting by Date and Time

Date/time fields should be mapped as `date` or `date_nanos`, not `keyword`, so Elasticsearch understands values chronologically and supports date range queries, sorting, and aggregations.

Example mapping:

~~~json
{
  "mappings": {
    "properties": {
      "createdAt": { "type": "date" },
      "publishedAt": { "type": "date" }
    }
  }
}
~~~

Newest products first:

~~~json
{
  "sort": [{ "createdAt": { "order": "desc" } }]
}
~~~

Oldest products first:

~~~json
{
  "sort": [{ "createdAt": { "order": "asc" } }]
}
~~~

Elasticsearch stores and compares dates using normalized timestamps. ISO-8601 values with explicit offset/timezone prevent timestamp ambiguity. If the application sends local date-times without a timezone, standardize on a timezone when converting to Instant or epoch values.

### 6.1. Date Formats

Multiple accepted date formats can be declared in the mapping:

~~~json
{
  "properties": {
    "createdAt": {
      "type": "date",
      "format": "strict_date_optional_time||epoch_millis"
    }
  }
}
~~~

The mapping format defines how Elasticsearch parses values during indexing and querying. It does not change sort semantics: documents are compared chronologically, not by the character order of date strings.

### 6.2. Sorting by Date While Returning a Different Format

You can request a format in the sort response if you need to display the sort value:

~~~json
{
  "sort": [{
    "createdAt": {
      "order": "desc",
      "format": "strict_date_time"
    }
  }]
}
~~~

Format only controls the representation of the returned sort value. It does not alter comparison order or stored data.

## 7. Sorting by Multiple Fields

When sorting by multiple fields, Elasticsearch processes them in the declared order. The first field is the primary criterion; subsequent fields act as tie-breakers when preceding fields are equal.

Example product list:

1. Price ascending.
2. If prices are equal, newer products come first.
3. If price and timestamp are equal, SKU ascending.

Query DSL:

~~~json
{
  "sort": [
    { "priceInCents": { "order": "asc" } },
    { "createdAt": { "order": "desc" } },
    { "sku": { "order": "asc" } }
  ]
}
~~~

This is multi-criteria sorting in priority order. Do not reverse the order of objects in the sort array, as doing so changes the results.

### 7.1. Spring Data `Sort`

A repository method can accept `Sort` so callers choose multiple criteria:

~~~java
import java.util.List;
import org.springframework.data.domain.Sort;

List<ProductDocument> findByCategory(String category, Sort sort);
~~~

Calling the repository:

~~~java
Sort sort = Sort.by(
        Sort.Order.asc("priceInCents"),
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("sku"));

List<ProductDocument> products =
        productRepository.findByCategory("ACCESSORIES", sort);
~~~

The order of `Sort.Order` instances is preserved as priority order. In the example, price is evaluated first, creation date is the second criterion, and SKU is the final criterion.

### 7.2. Fixed Sort in Repository Method Names

When business logic always uses the same order, you can declare `OrderBy` in a derived query:

~~~java
List<ProductDocument> findByCategoryOrderByPriceInCentsAscCreatedAtDescSkuAsc(
        String category);
~~~

This method is equivalent to sorting by `priceInCents ASC`, `createdAt DESC`, `sku ASC`. `OrderBy` suits fixed rules; `Sort` suits cases where the caller needs to choose the order at runtime.

### 7.3. Combining Sort with Pageable

`Pageable` can carry page number, page size, and sort together:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
                Sort.Order.asc("priceInCents"),
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("sku")));

Page<ProductDocument> page =
        productRepository.findByCategory("ACCESSORIES", pageable);
~~~

The returned result is the first page containing up to 20 documents in the declared order. `Page` also provides metadata such as `getTotalElements()`, `getTotalPages()`, and `hasNext()`.

## 8. Using Sort in NativeQuery

When building a query with `NativeQuery`, you can specify sort alongside the query and pageable:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.term(t -> t
                .field("category")
                .value("ACCESSORIES")))
        .withSort(Sort.by(
                Sort.Order.asc("priceInCents"),
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("sku")))
        .withPageable(PageRequest.of(0, 20))
        .build();
~~~

This example illustrates basic sorting via Spring Data `Sort`. Builder APIs may vary across Spring Data Elasticsearch versions; use your project's actual dependency and inspect the generated request. For advanced Elasticsearch options such as `mode`, `missing`, `nested`, or `unmapped_type`, you may need native sort options from the Elasticsearch Java API Client or the corresponding request DSL.

## 9. Missing Values: Documents Without a Sort Value

Some documents may omit the field used for sorting or have a null value. Elasticsearch lets you control the placement of missing values with the `missing` option.

Example placing documents missing a price at the end:

~~~json
{
  "sort": [{
    "priceInCents": {
      "order": "asc",
      "missing": "_last"
    }
  }]
}
~~~

You can use `"_first"` to place missing values first or `"_last"` to place them last. Some sort types also support a custom replacement value compatible with the field type.

For multi-field sorting, each criterion can have its own missing policy. Define clear behavior for legacy data, incomplete documents, or optional fields.

Do not use a replacement value that could collide with valid data if it alters business ordering. If a field is mandatory, it is better to validate data on write and run a backfill process for older documents.

## 10. Multi-Valued Fields and Sort Mode

Elasticsearch allows a scalar field to hold multiple values of the same type. For example:

~~~json
{
  "productId": "P-100",
  "prices": [120, 150, 180]
}
~~~

When sorting by a multi-valued field, Elasticsearch must pick a representative value. The `mode` parameter controls how it is selected:

| Mode | How the value is chosen |
| --- | --- |
| `min` | Smallest value. |
| `max` | Largest value. |
| `sum` | Sum of values. |
| `avg` | Average of values. |
| `median` | Median of values. |

Example sorting by the lowest price in the array:

~~~json
{
  "sort": [{
    "prices": {
      "order": "asc",
      "mode": "min"
    }
  }]
}
~~~

Example sorting by the highest price:

~~~json
{
  "sort": [{
    "prices": {
      "order": "desc",
      "mode": "max"
    }
  }]
}
~~~

With ascending sort, the default is typically `min`; with descending sort, the default is typically `max`. If the business semantics must be explicit, declare `mode` explicitly.

`mode` does not alter data in `_source`; it only determines the value used for comparison during sorting. With multi-valued fields, do not assume array element order determines sort order.

## 11. Sorting by Fields Inside Nested Objects

When a field resides in an object array mapped as `nested`, sorting needs to know the nested path and how to select relevant elements. A simple dot path may not suffice.

Example document:

~~~json
{
  "name": "Keyboard",
  "offers": [
    { "seller": "A", "price": 150 },
    { "seller": "B", "price": 120 }
  ]
}
~~~

Mapping:

~~~json
{
  "properties": {
    "offers": {
      "type": "nested",
      "properties": {
        "seller": { "type": "keyword" },
        "price": { "type": "long" }
      }
    }
  }
}
~~~

Sort by lowest offer price:

~~~json
{
  "sort": [{
    "offers.price": {
      "order": "asc",
      "mode": "min",
      "nested": { "path": "offers" }
    }
  }]
}
~~~

You can add `nested.filter` to consider only offers meeting a condition, such as sellers on an allowed list or active offers. Without declaring the proper nested path, Elasticsearch may reject the query or fail to sort by the intended elements.

For standard `object` arrays, Elasticsearch flattens child field values and does not preserve independent per-object semantics like `nested`. Only use nested sort when the field mapping is actually `nested` and business logic needs values selected from nested elements.

Spring Data `Sort` is suitable for simple field sorting. For nested sorts with path, filter, and mode, use query APIs / native sort options supporting full configuration; do not assume `Sort.by("offers.price")` infers nested semantics.

## 12. Sorting Across an Alias Pointing to Multiple Indices

An alias can point to multiple indices during migrations or when reading multi-version data. If a field has different mappings or does not exist in one index, sorting may fail.

Elasticsearch allows declaring `unmapped_type` in the sort clause to handle an index lacking that field's mapping:

~~~json
{
  "sort": [{
    "createdAt": {
      "order": "desc",
      "unmapped_type": "date",
      "missing": "_last"
    }
  }]
}
~~~

`unmapped_type` tells Elasticsearch which type to assume when the field is unmapped in an index. It does not fix mappings or convert an existing field with an incompatible type. If one index maps `price` as keyword and another maps it as long, you must resolve the schema inconsistency or create a compatible sort field before querying via the alias.

In a versioned-index workflow, keep mappings consistent for fields sorted through aliases. `unmapped_type` is only a fallback mechanism when a field genuinely does not exist, not a substitute for schema management.

## 13. Sorting by `_score` and Combining with Fields

In full-text search, Elasticsearch defaults to ranking by `_score` descending. If you want to prioritize relevance first and then sort by timestamp or price, you can declare multiple criteria:

~~~json
{
  "query": {
    "match": { "name": "wireless keyboard" }
  },
  "sort": [
    { "_score": { "order": "desc" } },
    { "createdAt": { "order": "desc" } },
    { "sku": { "order": "asc" } }
  ]
}
~~~

In this example, score is the first criterion. Creation date only determines order among documents with equal scores; SKU is the final tie-breaker.

If you sort by price before `_score`, relevance is no longer the primary priority. Arrange the criteria in the exact priority order required by the user experience.

## 14. Stable Ordering During Pagination

Multi-field sorting does not just format data presentation; it also keeps pagination results stable. If you only sort by `createdAt`, multiple documents may share the exact same timestamp. In that case, the order among them is not defined by business rules.

You should add a unique field whose mapping supports sorting as a tie-breaker:

~~~java
Sort sort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("sku"));
~~~

For example, only use SKU as a tie-breaker if SKU is genuinely unique within the queried index/tenant scope. If SKU is only unique per tenant, combine it with tenant or use a globally unique sort key ID.

Do not default to using `_id` as a sort field. `_id` has special limitations and lacks doc values like a regular keyword field. Store a unique field dedicated to sorting if the use case needs a stable tie-breaker.

When data changes between page fetches, offset pagination can still encounter duplicate or skipped documents even with a tie-breaker. For large datasets or continuously changing data, consider `search_after` combined with Point in Time (PIT), which preserves sort order throughout the traversal session.

## 15. Controlling Sort Fields from the API

If the UI lets users choose sorting, do not pass raw client-supplied field names directly into `Sort.by`. Map public choices to allowed fields:

~~~java
import org.springframework.data.domain.Sort;

public Sort toProductSort(String sortKey, String direction) {
    Sort.Direction order = "desc".equalsIgnoreCase(direction)
            ? Sort.Direction.DESC
            : Sort.Direction.ASC;

    String property = switch (sortKey) {
        case "price" -> "priceInCents";
        case "newest" -> "createdAt";
        case "name" -> "name.sort";
        case "sku" -> "sku";
        default -> "createdAt";
    };

    return Sort.by(new Sort.Order(order, property));
}
~~~

This is a sort field whitelist. In a real application, confirm that `name.sort` is handled properly by the mapping metadata and Spring Data version. If a subfield or native field path is not resolved as desired, use NativeQuery / Elasticsearch Java API Client to specify the exact sort field and inspect the actual request.

Also cap both the page size and the number of allowed sort criteria. An endpoint does not need to support every field in the index; only expose meaningful choices backed by suitable mappings.

## 16. Complete Entity and Repository Example

Entity:

~~~java
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.InnerField;
import org.springframework.data.elasticsearch.annotations.MultiField;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @MultiField(
        mainField = @Field(type = FieldType.Text, analyzer = "standard"),
        otherFields = {
            @InnerField(suffix = "sort", type = FieldType.Keyword)
        }
    )
    private String name;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Long)
    private Long priceInCents;

    @Field(type = FieldType.Date)
    private Instant createdAt;

    @Field(type = FieldType.Keyword)
    private String category;

    // Constructor, getters, and setters
}
~~~

Repository:

~~~java
import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    List<ProductDocument> findByCategoryOrderByPriceInCentsAscCreatedAtDesc(
            String category);

    List<ProductDocument> findByCategory(String category, Sort sort);

    Page<ProductDocument> findByCategory(String category, Pageable pageable);
}
~~~

Service:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

public Page<ProductDocument> findProducts(String category, int pageNumber) {
    Sort sort = Sort.by(
            Sort.Order.asc("priceInCents"),
            Sort.Order.desc("createdAt"),
            Sort.Order.asc("sku"));

    return productRepository.findByCategory(
            category, PageRequest.of(pageNumber, 20, sort));
}
~~~

This example demonstrates three different field types: `name.sort` as a keyword subfield, `priceInCents` as an integer, and `createdAt` as a date. The repository accepts `Sort` or `Pageable`, while `OrderBy` is used when the order is fixed.

## 17. Changing Sort Mappings After an Index Exists

Field type mappings and doc values affect the index structure. If the `name` field is currently only `text` and you want to add the `name.sort` subfield, editing annotations in code does not automatically reindex values for existing documents.

Typical workflow:

1. Create a new index with a mapping containing the keyword multi-field and required normalizer.
2. Reindex data from the old index to the new index so the new subfield is populated for existing documents.
3. Verify sorting on representative values, including uppercase/lowercase, diacritics, long strings, and missing values.
4. Switch the alias to the new index after verification.

Adding a multi-field to a mapping may be accepted by Elasticsearch in some cases, but old documents must be updated/reindexed for the new subfield to have values. Do not assume that merely adding a mapping makes historical data immediately sortable.

## 18. Common Pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Name sort throws fielddata or unsupported error | Sorting directly on `text`. | Create a `keyword` subfield and sort on the subfield. |
| Price `"100"` appears before `"20"` unexpectedly | Price is mapped as `keyword`. | Use an appropriate numeric type such as `long` or `scaled_float`. |
| Confusing uppercase/lowercase ordering | Keyword lacks a normalizer or requires locale collation. | Normalize with a normalizer or use an ICU collation field. |
| Documents missing values appear at the wrong end | `missing` is not configured. | Set `missing: "_first"` or `"_last"` as required. |
| Sorting a price array gives wrong semantics | Appropriate `mode` was not chosen. | Use `min`, `max`, `avg`, `sum`, or `median` per business logic. |
| Incorrect nested sort | Missing nested path or nested filter. | Declare full nested sort and confirm mapping is `nested`. |
| Sorting across a multi-index alias fails | Field is unmapped in one index or mapped to a different type. | Standardize schema; use `unmapped_type` only when a field genuinely does not exist. |
| Paginated results contain duplicates or gaps | Sort lacks a unique tie-breaker or data changes between requests. | Add a unique sort key; consider PIT + `search_after`. |
| Subfield sort via Spring `Sort` fails to resolve | Property path does not match how mapping metadata handles multi-fields. | Inspect generated request or use native sort options. |

## 19. Workflow for Choosing Sorting in a Use Case

When designing sorting, determine in order:

1. Does the user need to sort by string, number, date, or relevance score?
2. Does the field have the right mapping type and doc values enabled?
3. For strings, is exact keyword sorting or locale collation needed?
4. If the field is text, is there a dedicated keyword subfield for sorting?
5. Should missing values appear first or last?
6. Can the field contain multiple values; if so, which `mode` is needed?
7. Is the field inside a nested object; if so, have nested path/filter been declared?
8. Are multiple criteria and a unique tie-breaker needed for stable pagination?
9. Does an alias point to multiple indices with compatible mappings?
10. Can `OrderBy`, `Sort`, or `Pageable` be used, or is NativeQuery needed for advanced options?
11. Inspect the generated sort request and test with representative data before release.

## 20. References

- [Elasticsearch — Sort search results](https://www.elastic.co/guide/en/elasticsearch/reference/current/sort-search-results.html)
- [Elasticsearch — Keyword field type](https://www.elastic.co/guide/en/elasticsearch/reference/current/keyword.html)
- [Elasticsearch — Numeric field types](https://www.elastic.co/guide/en/elasticsearch/reference/current/number.html)
- [Elasticsearch — Date field type](https://www.elastic.co/guide/en/elasticsearch/reference/current/date.html)
- [Elasticsearch — Doc values](https://www.elastic.co/guide/en/elasticsearch/reference/current/doc-values.html)
- [Spring Data Elasticsearch — Query methods and sorting](https://docs.spring.io/spring-data/elasticsearch/reference/repositories/query-methods-details.html)
- [Spring Data Elasticsearch — Mapping annotations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)

Sorting by `keyword` uses string order; sorting by numbers and dates uses their respective typed values. When both full-text search and string sorting are required, create a `keyword` multi-field for the `text` field. Multiple criteria are evaluated in the declared order; `missing`, `mode`, and nested sort handle special cases. In Spring Data Elasticsearch, `OrderBy`, `Sort`, and `Pageable` cover common needs, while NativeQuery gives control over advanced sort options.
