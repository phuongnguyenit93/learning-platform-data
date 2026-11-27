# Source Filtering with Lists of Included or Excluded Fields

When searching in Elasticsearch, each hit typically returns both metadata and the document's content in `_source`. A document may contain many fields, while a screen or API only needs a few values. Source filtering lets you specify which fields are included in the response `_source` or which fields should be excluded from the response.

For example, a product document has `sku`, `name`, `price`, `description`, `internalNotes`, and `auditTrail`. A listing page only needs `sku`, `name`, and `price`. Instead of fetching the entire source and dropping fields in Java, the search request can instruct Elasticsearch to return only the three needed fields.

Source filtering is a feature of the Search API. It controls the `_source` section returned for each hit; it does not alter stored documents, modify mappings, change query conditions, or replace data authorization mechanisms.

## 1. `_source` in the Search Response

Elasticsearch stores document content in `_source` as JSON. A typical search response has the following simplified structure:

```json
{
  "hits": {
    "total": {
      "value": 1,
      "relation": "eq"
    },
    "hits": [
      {
        "_index": "products",
        "_id": "product-1001",
        "_score": 1.2,
        "_source": {
          "sku": "SKU-1001",
          "name": "Mechanical Keyboard",
          "price": 185000,
          "description": "Wireless mechanical keyboard",
          "internalNotes": "Supplier discount",
          "auditTrail": ["created", "reviewed"]
        }
      }
    ]
  }
}
```

Where:

- `_index` is the index containing the document.
- `_id` is the document identifier within the index.
- `_score` is the relevance score if the query involves scoring.
- `_source` is the returned JSON content of the document.

Without source filtering configured, the Search API usually returns the entire `_source` (unless source is disabled in the mapping or configured otherwise in the request). For large documents, returning every field can bloat the response and increase network transfer volume.

## 2. Two Ways to Specify Fields: includes and excludes

Elasticsearch supports two main lists:

- **includes**: fields or patterns allowed to be retrieved in the response `_source`.
- **excludes**: fields or patterns to exclude from the response `_source`.

You can use either list alone or combine both.

### 2.1 Fetching Only a List of Fields

The following request returns only `sku`, `name`, and `price`:

```http
GET /products/_search
{
  "query": {
    "match_all": {}
  },
  "_source": ["sku", "name", "price"]
}
```

This short array form is equivalent to configuring `includes`:

```json
"_source": {
  "includes": ["sku", "name", "price"]
}
```

The `_source` of each hit in the response contains only the selected fields:

```json
{
  "_index": "products",
  "_id": "product-1001",
  "_source": {
    "sku": "SKU-1001",
    "name": "Mechanical Keyboard",
    "price": 185000
  }
}
```

Other fields still exist in the stored document. They are simply omitted from `_source` in this response.

### 2.2 Excluding Certain Fields and Keeping the Rest

If you only want to exclude `internalNotes` and `auditTrail`, use `excludes`:

```http
GET /products/_search
{
  "query": {
    "match_all": {}
  },
  "_source": {
    "excludes": ["internalNotes", "auditTrail"]
  }
}
```

When only `excludes` is specified, Elasticsearch returns the remaining fields in the source, except those matching the exclusion list.

This approach is suitable when a document has many fields and the application wants to keep nearly the whole source, omitting only a few large or unneeded fields for the current response.

### 2.3 Combining includes and excludes

Both lists can be specified together:

```http
GET /products/_search
{
  "query": {
    "match_all": {}
  },
  "_source": {
    "includes": ["sku", "name", "price", "description"],
    "excludes": ["description"]
  }
}
```

Elasticsearch selects fields according to `includes`, then applies `excludes` to remove unwanted fields. Therefore, in this example `description` is excluded even though it appears in the includes list.

When combining both lists, write them clearly and avoid confusing overlapping patterns. If you simply need an exact list of fields, using `includes` is simpler.

### 2.4 When to Use includes, When to Use excludes?

| Scenario | Suitable approach |
|---|---|
| API needs only 3 fields out of a document with dozens of fields | Use `includes` |
| Most fields need to be returned, omitting only 1–2 large fields | Use `excludes` |
| Need to select a group of fields and omit specific fields within that group | Combine both |
| Only metadata needed, no JSON source needed | `_source: false` |

## 3. Nested Field Paths

Source filtering supports nested field paths using dot notation.

Document:

```json
{
  "name": "Mechanical Keyboard",
  "manufacturer": {
    "name": "Northwind",
    "country": "VN",
    "contact": {
      "email": "support@example.test",
      "phone": "0000000000"
    }
  }
}
```

Retrieve only product name and manufacturer name/country:

```http
GET /products/_search
{
  "query": {
    "match_all": {}
  },
  "_source": {
    "includes": [
      "name",
      "manufacturer.name",
      "manufacturer.country"
    ]
  }
}
```

The response preserves the nested object structure while containing only the selected fields:

```json
{
  "name": "Mechanical Keyboard",
  "manufacturer": {
    "name": "Northwind",
    "country": "VN"
  }
}
```

If you include only `manufacturer`, the entire child object can be returned. If you include only a sub-path, other parts of the object are not included in the source response.

### 3.1 Wildcard Patterns

Includes and excludes can use wildcards to select groups of fields:

```http
GET /products/_search
{
  "query": {
    "match_all": {}
  },
  "_source": {
    "includes": ["sku", "name", "attributes.*"],
    "excludes": ["attributes.internal*"]
  }
}
```

In the example:

- `attributes.*` selects child fields of `attributes`.
- `attributes.internal*` excludes child fields whose names start with `internal`.

Wildcards are useful when an object has many extensible fields or changing metadata structures. However, broad patterns can inadvertently include newly added fields in the future. For public APIs with fixed response contracts, explicit `includes` lists are easier to control.

### 3.2 Object Arrays

Suppose a document contains:

```json
{
  "name": "Jacket",
  "variants": [
    {
      "sku": "JACKET-RED-M",
      "color": "red",
      "size": "M",
      "internalCost": 120000
    },
    {
      "sku": "JACKET-BLUE-L",
      "color": "blue",
      "size": "L",
      "internalCost": 125000
    }
  ]
}
```

You can retrieve only SKU, color, and size of each element:

```json
"_source": {
  "includes": [
    "name",
    "variants.sku",
    "variants.color",
    "variants.size"
  ]
}
```

Source filtering only adjusts the returned JSON structure. It does not filter array elements by query conditions and does not replace `nested query` or `inner_hits`. If a query matches a specific variant while the source filter selects `variants.*`, the source response can still contain information from other variants according to the document structure.

## 4. Disabling `_source` in the Response

If a request only needs hit metadata, aggregations, or data obtained through another mechanism, you can omit `_source`:

```http
GET /products/_search
{
  "query": {
    "match": {
      "name": "keyboard"
    }
  },
  "_source": false
}
```

The response can still contain `_index`, `_id`, `_score`, `sort`, `highlight`, or other metadata depending on the request, but without `_source` content.

Request-level `_source: false` differs from disabling `_source` storage in the mapping. The request-level setting only asks not to return source for the current search. If the index mapping sets `_source.enabled: false`, source data is not stored in the usual manner and a request cannot re-enable it.

### 4.1 When Not to Disable Source?

Do not disable `_source` if the application needs to map results into full entities, display document content, use source data for further processing, or run operations that depend on `_source` in other flows.

If you disable source without configuring `fields`, stored fields, or another data-retrieval mechanism, Java results may lack content to populate entities. Determine exactly what the response needs before disabling it.

## 5. Source Filtering Does Not Alter the Query

Source filtering applies only when retrieving hit content. It does not affect how Elasticsearch selects matching documents.

Example query filtering active products priced at or below 500,000, while returning only `sku` and `name`:

```http
GET /products/_search
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "active": true } },
        { "range": { "price": { "lte": 500000 } } }
      ]
    }
  },
  "_source": {
    "includes": ["sku", "name"]
  }
}
```

Elasticsearch still uses `active` and `price` to filter documents even though those two fields are not returned in `_source`. Query conditions and source projection are independent.

Similarly, source filtering does not alter:

- Query scoring or relevance order.
- Fields used for sorting.
- Fields used in aggregations.
- Mappings or analyzers.
- Documents stored in the index.

If a query needs a field that the response does not need, you can still use that field in the query and exclude it from `_source`.

## 6. Highlighting Is Independent of Source Filtering

Highlights are separate metadata in a search hit, not original fields from `_source`. A field can be used for highlighting even when it is not included in the source response, provided the query and highlighter support that field.

Example:

```http
GET /products/_search
{
  "query": {
    "match": {
      "description": "wireless keyboard"
    }
  },
  "_source": {
    "includes": ["sku", "name", "price"]
  },
  "highlight": {
    "fields": {
      "description": {}
    }
  }
}
```

The response may omit `description` from `_source`, yet still include `highlight.description` containing highlighted fragments. This is useful when the UI needs only relevant snippets rather than the entire field content.

In Spring Data, read highlights from `SearchHit.getHighlightFields()`. Do not look for fragments inside the entity when the source field has been excluded from the response.

## 7. Using Source Filtering in Spring Data Elasticsearch

Spring Data Elasticsearch provides `FetchSourceFilter` to represent `includes` and `excludes` lists. You can attach a source filter to `NativeQuery` when building a search request.

Entity example:

```java
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

    @Field(type = FieldType.Double)
    private Double price;

    @Field(type = FieldType.Text)
    private String description;

    @Field(type = FieldType.Text)
    private String internalNotes;

    protected Product() {
    }

    // Constructors and accessors omitted for brevity.
}
```

### 7.1 Fetching Only Required Fields

```java
import org.springframework.data.elasticsearch.core.query.FetchSourceFilter;

FetchSourceFilter sourceFilter = new FetchSourceFilter(
    new String[] {"sku", "name", "price"},
    null
);
```

The first parameter is `includes`; the second parameter is `excludes`. Pass `null` for an unused list.

### 7.2 Excluding Unneeded Fields

```java
FetchSourceFilter sourceFilter = new FetchSourceFilter(
    null,
    new String[] {"internalNotes", "auditTrail"}
);
```

When only `excludes` is passed, other fields are kept in the source response.

### 7.3 Combining includes and excludes

```java
FetchSourceFilter sourceFilter = new FetchSourceFilter(
    new String[] {"sku", "name", "price", "description"},
    new String[] {"description"}
);
```

The `excludes` list removes `description` from the selected field group.

### 7.4 Attaching the Filter to NativeQuery

The example below uses the Spring Data Elasticsearch 5.x API style with the Elasticsearch Java Client:

```java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.data.elasticsearch.core.query.FetchSourceFilter;

FetchSourceFilter sourceFilter = new FetchSourceFilter(
    new String[] {"sku", "name", "price"},
    new String[] {"internalNotes"}
);

Query query = NativeQuery.builder()
    .withQuery(q -> q.match(m -> m
        .field("name")
        .query("wireless keyboard")
    ))
    .withSourceFilter(sourceFilter)
    .build();
```

Execute via `ElasticsearchOperations`:

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;

SearchHits<Product> hits = operations.search(query, Product.class);
```

`FetchSourceFilter` is translated into source filtering in the Search API. Method and builder names may differ across Spring Data Elasticsearch lines; consult the Javadoc of your project's dependency if using another version. The semantics of `includes`/`excludes` still correspond to `_source` in the REST API.

### 7.5 Complete Service Example

```java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.FetchSourceFilter;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<Product> searchForListPage(String text) {
        FetchSourceFilter sourceFilter = new FetchSourceFilter(
            new String[] {"sku", "name", "price"},
            new String[] {"internalNotes", "auditTrail"}
        );

        Query query = NativeQuery.builder()
            .withQuery(q -> q.match(m -> m
                .field("name")
                .query(text)
            ))
            .withSourceFilter(sourceFilter)
            .build();

        return operations.search(query, Product.class);
    }
}
```

Search results here have source only for `sku`, `name`, and `price`. Other properties in the `Product` class may remain unpopulated. Treat the result as trimmed read-only data, not a full entity for saving back.

### 7.6 Disabling Source via FetchSourceFilter

`FetchSourceFilter` provides a constructor allowing you to specify whether to fetch source in supported versions:

```java
FetchSourceFilter sourceFilter = new FetchSourceFilter(
    false,
    null,
    null
);
```

This is the equivalent representation of the `_source: false` request. Use it only when the application does not need `_source` to construct a full entity. If the constructor or API differs in your project's version, use the corresponding source-filter API provided by that version.

## 8. Entities Mapped from Filtered Source

This requires special attention when using source filtering with Spring Data. If a query returns `Product` while including only `sku`, `name`, and `price`, the mapping converter receives only those fields from `_source`.

For example, the full entity has:

```java
private String sku;
private String name;
private Double price;
private String description;
private String internalNotes;
```

After source filtering, `description` and `internalNotes` may be `null` or default values in the resulting object. This does not mean the data in Elasticsearch was deleted.

### 8.1 Do Not Save Partial Entities Back

Do not do the following:

```java
Product product = hits.getSearchHit(0).getContent();
product.setPrice(199000.0);
productRepository.save(product);
```

An entity read with source filtering can be missing many fields. Calling `save` may write a new document containing only the populated fields and lose fields missing from the object.

If a partial update is required, use the Elasticsearch Update API via `ElasticsearchOperations.update(...)` with `UpdateQuery`. If writing the full document, read the complete source or load canonical data from an appropriate source before saving.

### 8.2 Use DTOs/Projections for Trimmed Results

A search result serving only a product list should have its own data type:

```java
public record ProductListItem(
    String sku,
    String name,
    Double price
) {
}
```

You can map the results from the partial entity to the DTO:

```java
List<ProductListItem> items = hits.getSearchHits().stream()
    .map(hit -> hit.getContent())
    .map(product -> new ProductListItem(
        product.getSku(),
        product.getName(),
        product.getPrice()
    ))
    .toList();
```

For APIs needing deep projections or wanting to avoid instantiating entities with missing-field states, you can use DTOs/projections or read native responses as supported by the version. The key is making it explicit that this is a partial read.

## 9. Source Filtering and Performance

Source filtering typically reduces response size and the amount of data transferred from Elasticsearch to the application. It also reduces deserialization/mapping work for unneeded fields on the client side.

However, understand its limits accurately:

- Elasticsearch still has to find documents matching the query.
- Fields used in queries, filters, sorts, or aggregations are still processed according to the mapping, even when not returned in `_source`.
- Source filtering does not shrink the index and does not remove fields from stored documents.
- Depending on how `_source` is stored and index configuration, Elasticsearch may still need to read/decompress the source document before filtering fields; therefore, do not assume including a single field reduces server-side I/O proportionally.
- The clearest benefit is usually reduced network payload and client-side source processing, especially for large documents.

### 9.1 Selecting Fields by Use Case

Not every endpoint needs the same source filter. For example:

| Use case | Fields to return |
|---|---|
| Listing page | `sku`, `name`, `price`, `thumbnail` |
| Detail page | Full display fields of the product |
| Autocomplete | `name`, `sku`, or minimal suggestion fields |
| Search snippet | `name`, `sku`, and highlight fragments |
| Reporting | Fields needed for calculations or exports |

Designing source filters around response contracts avoids sending surplus data and reduces coupling between APIs and internal document structures.

### 9.2 Avoid Overly Broad Wildcards When Unneeded

Patterns such as `*` or `metadata.*` are convenient when structures change, but can unintentionally include newly added fields in responses after a mapping update. For public endpoints, explicit `includes` lists are more predictable.

### 9.3 Source Filtering Does Not Replace Pagination

Reducing the number of fields per hit does not reduce the number of hits. If a query returns tens of thousands of documents, the response can still be large even if each document contains only two fields. Combine source filtering with `size`, `Pageable`, `search_after`, or an appropriate pagination strategy.

## 10. Distinguishing Source Filtering from fields and stored_fields

Elasticsearch offers several mechanisms to return fields in a search response. They serve different purposes.

| Mechanism | Content | Suitable when |
|---|---|---|
| `_source` | Stored JSON document | Full document content in original structure is needed |
| `_source.includes/excludes` | Subset of JSON source | Simple projection from the document is needed |
| `fields` | Field values according to mapping and field retrieval API | Values processed by field type/runtime fields are needed |
| `stored_fields` | Fields configured with `store: true` | Specific fields are deliberately stored separately for retrieval |
| `docvalue_fields` | Values from doc values | Retrieving keyword, numeric, or date values that have doc values |

### 10.1 `_source` Filtering

Example:

```json
"_source": {
  "includes": ["sku", "name"]
}
```

Returns part of the JSON source. This is usually the simplest choice when the application wants to reduce fields in the document response.

### 10.2 `fields`

Example:

```json
"fields": ["sku", "price", "createdAt"]
```

`fields` has its own semantics and responses typically represent values as arrays per field. It can support runtime fields or field formatting depending on mapping/API. Do not swap `_source` includes for `fields` without adjusting response parsing.

### 10.3 `stored_fields`

A field must be declared with `store: true` in the mapping to be retrieved via stored fields. Example:

```json
"name": {
  "type": "text",
  "store": true
}
```

Stored fields are a mechanism for storing field values separately in Lucene. They are not enabled automatically for all fields and can increase index size. Do not enable `store: true` merely to filter `_source` responses.

### 10.4 `docvalue_fields`

Doc values are a columnar structure serving sorting, aggregations, and certain field retrieval operations. Example of retrieving a formatted date:

```json
"docvalue_fields": [
  {
    "field": "createdAt",
    "format": "strict_date_time"
  }
]
```

Not all field types have doc values; `text` usually does not have doc values by default. Check actual mappings and requirements before choosing this mechanism.

## 11. Source Filtering and Data Security

Source filtering is not an authorization mechanism. If a user has permission to call the Search API, they can send another request including fields that the application previously excluded, unless Elasticsearch-layer permissions prevent it.

For example, an internal API might send:

```json
"_source": {
  "excludes": ["salary", "personalNotes"]
}
```

This only restricts the response of that specific request. It does not stop a user from modifying the request to:

```json
"_source": true
```

If sensitive fields must not be accessed, enforce authorization at the application layer, Elasticsearch field-level/document-level security, or segregate data across appropriate security boundaries.

At the API layer, construct source filters on the server side based on user permissions. Do not accept arbitrary `includes` lists from clients allowing them to pick sensitive fields. Even if the API returns only a restricted DTO, ensure backend queries and Elasticsearch permissions do not open unintended access paths.

## 12. Verifying Source Filtering via the REST API

When the source response does not match expectations, inspect it directly using the Search API.

### 12.1 Include Only Specific Fields

```http
GET /products/_search
{
  "size": 5,
  "query": {
    "match_all": {}
  },
  "_source": {
    "includes": ["sku", "name", "price"]
  }
}
```

### 12.2 Exclude Large Fields

```http
GET /products/_search
{
  "size": 5,
  "query": {
    "match_all": {}
  },
  "_source": {
    "excludes": ["description", "auditTrail"]
  }
}
```

### 12.3 Check Nested Fields

```http
GET /products/_search
{
  "query": {
    "match_all": {}
  },
  "_source": {
    "includes": ["name", "manufacturer.name", "variants.sku"]
  }
}
```

Inspect `hits.hits[*]._source` to verify returned fields. Do not check only `_source` from a document GET request if source filtering is sent via `_search`; the two requests can have different fetch configurations.

## 13. Common Pitfalls

### 13.1 Confusing Source Filtering with Deleting Fields

A field absent from the response does not mean it was deleted from the document. Source filtering only changes the response projection.

### 13.2 Using Only excludes While Documents Gain New Fields

When excluding only a few fields, every other field can still be returned, including fields added in the future. For APIs needing a stable contract, consider explicit `includes`.

### 13.3 Overly Broad Wildcards

Broad patterns can retrieve unintended data. Use specific paths when controlling responses.

### 13.4 Entity Has Null Fields After Search

If a source filter omits a field, the mapping converter receives no value to populate. This is normal behavior for partial projections, not necessarily lost data.

### 13.5 Saving a Partially Read Entity Back

An entity missing fields due to source filtering can overwrite the complete document if passed to `save`. Use DTOs/projections for reading and the Update API for partial changes.

### 13.6 Using Source Filter as Security

Callers can modify requests. Use authorization/field-level security for sensitive data.

### 13.7 Confusing `_source: false` with Mapping `_source.enabled: false`

One only disables source in a request's response; the other affects how the index stores source and has long-term consequences for reindexing, updates, and data retrievability.

### 13.8 Assuming Source Filtering Always Makes Queries Faster

It reduces payload and client-side mapping, but does not reduce query conditions, shard count, or scoring work. Measure to verify actual benefits.

## 14. Source Filter Design Checklist

Before applying source filtering to an endpoint, determine:

1. Which fields the response needs and which fields can be omitted.
2. Whether to use explicit `includes` or `excludes`.
3. Whether there are nested fields or object arrays to select by path.
4. Whether any wildcard could accidentally pull in future fields.
5. Whether the returned entity is partial and needs a dedicated DTO/projection.
6. Whether any flow saves the partial entity back; if so, switch to the Update API or load full data.
7. Which highlights or metadata need to be returned separately outside `_source`.
8. Whether there are field security requirements; if so, is a source filter sufficient (it is not authorization).
9. Whether before/after response size and network/client impact have been measured.
10. Whether appropriate pagination is in place to limit hit count.

## 15. Summary

Source filtering controls which fields are returned in `_source` for each search hit. Use `includes` to pick needed fields, `excludes` to drop unneeded fields, and wildcards/dotted paths to handle nested structures. If document content is not needed, `_source: false` can be set at the request level; this differs from disabling `_source` storage in the mapping.

In Spring Data Elasticsearch, `FetchSourceFilter` represents `includes`/`excludes` lists and can be attached to `NativeQuery` before calling `ElasticsearchOperations.search(...)`. When source is filtered, mapped entities may lack fields; treat them as partial reads, use DTOs/projections, and avoid saving such entities back as complete documents. Source filtering reduces payloads, but does not alter queries/mappings, delete data, or act as a security mechanism. For sensitive fields, enforce authorization or field-level security at the appropriate layer.

## References

- [Elasticsearch — Retrieve selected fields](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-fields.html)
- [Elasticsearch — Search API](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-search.html)
- [Elasticsearch — `_source` field](https://www.elastic.co/guide/en/elasticsearch/reference/current/mapping-source-field.html)
- [Spring Data Elasticsearch Reference — Search Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
