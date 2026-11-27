# Distinguishing `_source`, Stored Fields, and Docvalue Fields

When Elasticsearch returns search results, the application may need the document's full JSON content, a few separately stored fields, or values optimized for sorting and aggregations. Elasticsearch provides three common mechanisms: `_source`, stored fields, and doc values. They serve different purposes and are not interchangeable in all situations.

- **`_source`** holds the JSON content sent when indexing the document. This is typically the data Spring Data Elasticsearch uses to reconstruct Java entities.
- **Stored fields** separately store fields declared with `store: true` in the mapping, which can then be requested via `stored_fields`.
- **Doc values** store values in a columnar format, optimized for sorting, aggregations, scripting, and retrieving field values for supported data types. They can be requested via `docvalue_fields`.

Understanding these three mechanisms helps design appropriate mappings, reduce response payloads, and avoid errors when the application needs to construct entities or perform analytics.

## 1. Three Storage and Retrieval Mechanisms

| Mechanism | How is data stored? | How to request in Search API | Primary purpose |
| --- | --- | --- | --- |
| `_source` | JSON content of the document. | `_source`, `_source: { includes, excludes }`. | Reading documents and reconstructing Java objects. |
| Stored fields | Separate stored copy of each field with `store: true`. | `stored_fields`. | Retrieving selected fields stored separately. |
| Doc values | Columnar structure per field, if supported by field type. | `docvalue_fields`. | Sorting, aggregations, scripts, and reading supported field values. |

These mechanisms can coexist. For instance, a `keyword` field `sku` can appear in `_source`, be stored separately via `store: true`, and have doc values for sorting/aggregations. That does not mean all three should be enabled: each mechanism should be chosen based on actual needs.

## 2. `_source`: The Original JSON Content

`_source` is the JSON payload sent when creating or updating a document. It preserves object structures, arrays, null values, and field contents as sent by the application, subject to the index's source storage configuration.

Example document:

~~~json
{
  "sku": "KB-001",
  "name": "Mechanical Keyboard",
  "category": "Accessories",
  "price": 129900,
  "tags": ["wireless", "office"],
  "supplier": {
    "name": "Acme",
    "country": "VN"
  }
}
~~~

When searching, a hit typically contains `_source` as follows:

~~~json
{
  "_index": "products",
  "_id": "KB-001",
  "_score": 1.42,
  "_source": {
    "sku": "KB-001",
    "name": "Mechanical Keyboard",
    "category": "Accessories",
    "price": 129900,
    "tags": ["wireless", "office"],
    "supplier": {
      "name": "Acme",
      "country": "VN"
    }
  }
}
~~~

Because `_source` preserves JSON structure, it is suitable when the application needs to:

- Reconstruct entities or DTOs containing nested objects and collections.
- Return multiple fields at once to an API.
- Read fields that are not indexed.
- Reindex or update documents based on source content.

`_source` is not an inverted index. A field can be unindexed for search yet still exist in `_source` and be returned.

### 2.1. Filtering Fields in `_source`

Not every response needs the full document. The Search API allows retrieving only selected fields using source filtering:

~~~http
GET /products/_search
Content-Type: application/json

{
  "_source": ["sku", "name", "price"],
  "query": {
    "term": {
      "category": "Accessories"
    }
  }
}
~~~

`includes` and `excludes` can be used for finer control:

~~~json
{
  "_source": {
    "includes": ["sku", "name", "supplier.name"],
    "excludes": ["internalNotes"]
  },
  "query": {
    "match_all": {}
  }
}
~~~

Source filtering reduces the returned payload size and client-side deserialization work. It does not remove fields from the stored document and does not alter mappings or query capabilities of fields.

### 2.2. Disabling `_source`

Elasticsearch allows disabling `_source` at the index level. In that case, hits do not return the original JSON content in the standard way. This can save source storage costs in certain scenarios, but forfeits an essential mechanism of the system.

Operations that may be restricted without `_source` include:

- Constructing full entities from search hits in Spring Data.
- Reindexing data via the standard Reindex API, which needs to read document source.
- Updating documents in ways that require reading and modifying source content.
- Application workflows that rely on the original JSON object or fields not stored separately.

Consider disabling `_source` only when an alternative storage and reconstruction strategy has been explicitly designed. For typical Spring Data Elasticsearch applications, keep `_source` enabled.

## 3. Stored Fields: Storing Fields Separately with `store: true`

By default, field mappings usually have `store: false`. Values can still appear in `_source`, but Elasticsearch does not store those fields separately as stored fields.

When declaring `store: true`, Elasticsearch additionally stores the field value so it can be returned via `stored_fields`. Example:

~~~json
{
  "mappings": {
    "properties": {
      "sku": {
        "type": "keyword",
        "store": true
      },
      "name": {
        "type": "text"
      },
      "price": {
        "type": "long"
      }
    }
  }
}
~~~

Requesting stored fields in the Search API:

~~~http
GET /products/_search
Content-Type: application/json

{
  "_source": false,
  "stored_fields": ["sku"],
  "query": {
    "term": {
      "sku": "KB-001"
    }
  }
}
~~~

The hit response section looks like:

~~~json
{
  "_index": "products",
  "_id": "KB-001",
  "fields": {
    "sku": ["KB-001"]
  }
}
~~~

Stored fields are typically represented inside the `fields` object as lists of values. Even when a field has only a single value, the response can still represent it as an array.

### 3.1. Prerequisite for Retrieving Stored Fields

For `stored_fields` to return a field, the mapping must declare `store: true` for that field. Otherwise, a request cannot retrieve the field as a stored field merely because it exists in `_source` or has an inverted index.

`stored_fields` does not automatically read from `_source`. If a field is not stored separately, the usual options are:

- Fetch the field via `_source` or source filtering.
- Create a new mapping with `store: true` if there is a valid reason for stored fields, then reindex the data.

You cannot enable `store: true` on an existing field and expect old documents to retroactively gain the new stored field. Field mapping changes generally require a new index and reindexing.

### 3.2. When Should Stored Fields Be Used?

You can consider `store: true` if the application frequently needs to fetch a few distinct fields and has a clear reason to retrieve them independently of `_source`.

However, stored fields are not inherently faster than source filtering. Elasticsearch stores `_source` in an optimized manner; when reading a few fields from `_source`, actual cost depends on document size, codec, number of fields fetched, and data access patterns. Measure on real data before choosing stored fields as a performance optimization.

Do not enable `store: true` on every field simply to read values back. If `_source` already meets the need, storing an extra copy can increase disk usage and write overhead.

## 4. Doc Values: Columnar Storage

Doc values are a columnar storage structure optimized by Elasticsearch for reading a field's values across many documents. They are commonly used for:

- Sorting results by field.
- Aggregations such as `terms`, `min`, `max`, `sum`, or `avg` depending on data type.
- Retrieving fields via `docvalue_fields`.
- Certain script operations accessing field values.

For many supported field types, `doc_values` is enabled by default. Common types include `keyword`, numeric types, `date`, `boolean`, and several other scalar types. `text` does not support standard doc values.

Example mapping:

~~~json
{
  "mappings": {
    "properties": {
      "category": {
        "type": "keyword",
        "doc_values": true
      },
      "price": {
        "type": "long",
        "doc_values": true
      },
      "createdAt": {
        "type": "date",
        "doc_values": true
      }
    }
  }
}
~~~

### 4.1. Sort and Aggregations Use Doc Values

Example sorting products by price:

~~~json
{
  "sort": [
    { "price": { "order": "asc" } }
  ],
  "query": {
    "match_all": {}
  }
}
~~~

Example counting products by category:

~~~json
{
  "aggs": {
    "categories": {
      "terms": {
        "field": "category"
      }
    }
  }
}
~~~

These operations generally rely on doc values. This is why `keyword`, numeric, and date fields usually have doc values enabled by default.

### 4.2. Retrieving Doc Values via `docvalue_fields`

You can request doc values in a search response:

~~~http
GET /products/_search
Content-Type: application/json

{
  "_source": false,
  "docvalue_fields": ["category", "price"],
  "query": {
    "term": {
      "category": "Accessories"
    }
  }
}
~~~

A hit may contain:

~~~json
{
  "_index": "products",
  "_id": "KB-001",
  "fields": {
    "category": ["Accessories"],
    "price": [129900]
  }
}
~~~

`docvalue_fields` returns data under `fields` without reconstructing the entire JSON structure. You can specify a format for certain types like `date`:

~~~json
{
  "_source": false,
  "docvalue_fields": [
    {
      "field": "createdAt",
      "format": "strict_date_time"
    }
  ],
  "query": {
    "match_all": {}
  }
}
~~~

Format determines how the value is represented in the response; it does not alter the document's original data.

### 4.3. Limitations of Doc Values

Doc values only exist on field types that support this mechanism. Key points to remember:

- `text` does not have standard doc values. If sorting or aggregating on text content is required, typically create a `keyword` subfield.
- `object` and `nested` do not have doc values as a single scalar field; child fields have their own mappings and doc values according to their data types.
- `doc_values: false` disables doc-value usage for corresponding sorts/aggregations/retrievals, even though the field may still be indexed.
- For multi-valued fields, the order of values returned from doc values is not guaranteed to match the array order in `_source`.

Do not treat doc values as an exact copy of the original JSON. They are optimized for per-field operations, not for preserving ordering, object structures, or the original representation of the full document.

## 5. Comparing Responses of the Three Mechanisms

You can request all three types of data in the same request if the mapping supports them:

~~~http
GET /products/_search
Content-Type: application/json

{
  "_source": ["name"],
  "stored_fields": ["sku"],
  "docvalue_fields": ["price", "category"],
  "query": {
    "term": {
      "category": "Accessories"
    }
  },
  "sort": [
    { "price": "asc" }
  ]
}
~~~

Illustrative response:

~~~json
{
  "hits": {
    "hits": [
      {
        "_index": "products",
        "_id": "KB-001",
        "_score": null,
        "_source": {
          "name": "Mechanical Keyboard"
        },
        "fields": {
          "sku": ["KB-001"],
          "price": [129900],
          "category": ["Accessories"]
        },
        "sort": [129900]
      }
    ]
  }
}
~~~

In this example:

- `name` comes from `_source`.
- `sku` comes from stored fields because the mapping has `store: true`.
- `price` and `category` come from doc values.
- `sort` holds the value used to sort the hit.

Do not fetch the same field through multiple mechanisms unless the application genuinely uses different representations. Requesting redundant data complicates responses and increases transfer overhead.

## 6. Comparison Table by Use Case

| Application need | Appropriate mechanism | Reason |
| --- | --- | --- |
| Reconstruct entity with objects and collections | `_source` | Preserves full JSON structure. |
| Return a few fields for a DTO | `_source` filtering | No need to store individual fields separately. |
| Read a field declared `store: true` without fetching source | `stored_fields` | Retrieves the field's separate stored copy. |
| Sort by price or creation date | Doc values | Optimized for columnar access. |
| Aggregate by category or status | Doc values | Suitable for summarizing across many documents. |
| Script reading scalar values | Doc values if supported by type | Provides columnar field access. |
| Read unindexed field still present in JSON | `_source` | No inverted index needed to retrieve source. |
| Reconstruct document after source is disabled | No general replacement | Stored fields and doc values do not reconstruct full JSON. |

## 7. Mappings and Choices for Each Field Type

Different field types support different mechanisms. The table below summarizes common cases; check the mapping reference of your running Elasticsearch version when using specialized types.

| Field type | `_source` | Stored fields | Doc values | Notes |
| --- | --- | --- | --- | --- |
| `text` | Yes if source enabled | Can enable `store: true` | No standard doc values | Uses inverted index for full-text; usually uses a `keyword` multi-field for sort/aggregations. |
| `keyword` | Yes if source enabled | Can enable `store: true` | Yes, typically enabled by default | Exact match, sorting, and terms aggregations. |
| `long`, `integer`, `double`, `float` | Yes if source enabled | Can enable `store: true` | Yes, typically enabled by default | Range, sorting, aggregations. |
| `date` | Yes if source enabled | Can enable `store: true` | Yes, typically enabled by default | Can be formatted when retrieved via docvalue fields. |
| `boolean` | Yes if source enabled | Can enable `store: true` | Yes | Filtering, sorting, and aggregations as supported by field. |
| `ip` | Yes if source enabled | Can enable `store: true` | Yes | Querying and statistics by IP address. |
| `object` | Preserves JSON structure if source enabled | Does not store entire object as a scalar field | No doc values for overall object | Child fields have their own mappings. |
| `nested` | Preserves object array if source enabled | Does not store entire nested object as a scalar field | Child fields have separate doc values if supported | Uses nested queries/aggregations per nested semantics. |

`_source` is a document-level JSON storage mechanism; the stored fields and doc values columns describe how individual fields are retrieved. An object can be preserved intact in `_source` even when its child fields have separate mappings and query capabilities.

## 8. Integrating Mappings in Spring Data Elasticsearch

Spring Data Elasticsearch declares `store` and `docValues` attributes on `@Field`. Example:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword, store = true)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword, docValues = true)
    private String category;

    @Field(type = FieldType.Long, docValues = true)
    private Long price;

    // Constructor, getters, and setters
}
~~~

Conceptually corresponding mapping:

~~~json
{
  "properties": {
    "sku": {
      "type": "keyword",
      "store": true
    },
    "name": {
      "type": "text"
    },
    "category": {
      "type": "keyword",
      "doc_values": true
    },
    "price": {
      "type": "long",
      "doc_values": true
    }
  }
}
~~~

`store = true` instructs Elasticsearch to store the `sku` field separately. `docValues = true` retains the doc values structure for supported fields. `keyword`, numeric, and date types typically already enable doc values by default, so explicit declaration primarily documents mapping intent.

### 8.1. Mapping Annotations Do Not Update Existing Indices

Changing an annotation does not automatically modify the mapping of an index created earlier. If `sku` previously had `store: false` and is changed to `store: true`, existing documents do not automatically receive the new stored field.

When mapping changes cannot be applied directly, create a new index with the desired mapping, reindex data, and switch the alias after verification. Remember that the Reindex API reads `_source`; if source was disabled, standard reindexing cannot copy complete documents.

## 9. Reading Results via Spring Data Elasticsearch

When using a repository or `ElasticsearchOperations`, Spring Data typically uses `_source` to convert hits into domain objects. Example:

~~~java
SearchHits<ProductDocument> searchHits =
        operations.search(query, ProductDocument.class);

for (SearchHit<ProductDocument> hit : searchHits) {
    ProductDocument product = hit.getContent();
    String id = hit.getId();
    float score = hit.getScore();
}
~~~

`getContent()` is the object built by the converter from source using mapping metadata. If a request disables `_source` and returns only stored fields or docvalue fields, do not expect `getContent()` to be populated like a regular complete document.

Fields returned separately in the response can be read from `SearchHit`/`SearchDocument` metadata through the field map API of the Spring Data version in use. Response structures typically store values by field name in `fields`; verify actual return types and convert carefully into DTOs.

Illustrative example of reading field metadata (exact API may differ by version):

~~~java
for (SearchHit<ProductDocument> hit : searchHits) {
    Map<String, List<Object>> fields = hit.getFields();
    List<Object> storedSku = fields.get("sku");
    List<Object> priceValues = fields.get("price");
}
~~~

Do not cast directly without checking for null, value count, and returned data types. Stored fields and docvalue fields are usually represented as lists because a field can contain multiple values.

### 9.1. Source Filtering in Spring Data Queries

When only a subset of entity properties is needed, you can configure a source filter on the query instead of requesting stored fields. Corresponding REST API example:

~~~json
{
  "_source": {
    "includes": ["sku", "name", "price"]
  },
  "query": {
    "match_all": {}
  }
}
~~~

Spring Data Elasticsearch provides source filtering APIs on its query types; exact method names and filter types depend on the version. Use the API of your dependency and verify that the generated request contains `_source.includes` as intended.

## 10. Distinguishing `fields` from `stored_fields` and `docvalue_fields`

The Search API also has a `fields` parameter. This is an API for retrieving field values according to mapping and can draw from doc values or `_source` depending on the field and data type. It is not synonymous with `stored_fields`, nor should it be treated as an alias for `docvalue_fields`.

| Request option | Meaning |
| --- | --- |
| `_source` | Returns original JSON content, filterable via includes/excludes. |
| `stored_fields` | Fetches only fields separately stored via `store: true` in mapping. |
| `docvalue_fields` | Fetches values from doc values of supported fields. |
| `fields` | Higher-level API to retrieve field values per mapping; data source depends on the field. |

When explicit control over the data source is needed, use the exact corresponding option. In particular, do not assume `fields` always returns the original `_source` structure or that `stored_fields` can fetch every field.

## 11. Multi-Valued Fields and Data Structures

Elasticsearch allows a field to hold one or more values of the same type. The three mechanisms can represent them differently:

- `_source` preserves arrays in their submitted JSON structure and order.
- Stored fields return field values in the `fields` response section; do not use this retrieval mode to reconstruct complex JSON objects.
- Doc values are optimized for per-field processing; with multiple values, the returned order may differ from the original array order.

Example source:

~~~json
{
  "tags": ["wireless", "office", "compact"]
}
~~~

If reading `tags` from `_source`, the application receives the JSON array in the order above. If using doc values, treat the values as a set of field values serving search/aggregation operations; do not rely on original ordering for display or data reconstruction.

For nested objects or nested arrays, `_source` is the proper way to preserve full structure. Stored fields and doc values retrieve individual fields and do not replace full object/array relationships.

## 12. Impact on Query, Sort, and Aggregation

Searching, sorting, aggregating, and retrieving values are separate concerns:

| Mapping and mechanism | Query | Sort / aggregation | Reading values |
| --- | --- | --- | --- |
| `index: true`, doc values enabled | Queryable per field semantics. | Yes if field type supports doc values. | `_source`, stored fields, or docvalue fields if configured. |
| `index: false`, doc values enabled | Not queryable via standard inverted index. | Sortable/aggregatable if field type supports doc values. | `_source` or docvalue fields; stored fields if enabled. |
| `index: true`, `doc_values: false` | Queries still work. | Doc-value-based sort/aggregation unavailable normally. | `_source` or stored fields if enabled. |
| `store: true` | Does not automatically make field queryable. | Does not automatically provide doc values. | Retrieved via `stored_fields`. |

`store` does not enable querying; `doc_values` does not replace the inverted index; `_source` does not make a field searchable. Verify each application requirement separately.

## 13. Cost and Performance Choices

Each mechanism has distinct goals and costs:

- `_source` stores the original JSON and is usually the simplest option for constructing documents. Source filtering reduces payloads when full fields are unnecessary.
- Stored fields store extra separate values. They are useful in certain read models, but increase storage and are not inherently faster than `_source`.
- Doc values require separate storage, yet optimize sorting, aggregations, and columnar field access. Disabling them can save disk space, but breaks dependent operations.
- The inverted index is a search structure; it does not replace source or doc values when reconstructing values is required.

Do not optimize by disabling `_source`, `store`, or `doc_values` based solely on assumptions. Measure index size, response payload, query latency, and cluster load with representative data.

## 14. Common Pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `stored_fields` returns no values | Field is not mapped with `store: true`. | Read from `_source` or create a new index with stored fields and reindex. |
| `docvalue_fields` returns no values | Field does not support doc values or `doc_values` was disabled. | Check field type and mapping. |
| Sort/aggregation on text fails | `text` lacks standard doc values. | Use a `keyword` subfield or an appropriate field. |
| Search hit cannot construct full entity | `_source` is disabled or request excluded needed fields. | Keep `_source` or deliberately use DTOs/field retrieval. |
| Reindex fails or copies incomplete data | Source index has no available `_source`. | Review source design and alternative export/restore strategy before migration. |
| Array order differs when read via doc values | Doc values do not preserve original array order. | Use `_source` if ordering is business-critical data. |
| Mapping annotation changed but response did not change | Old index already exists with previous mapping. | Create a new index and reindex when changes cannot apply directly. |
| Stored field returned as a list | Search response represents fields inside `fields` as arrays. | Read the list and handle empty or multi-value cases. |

## 15. Workflow for Selecting a Retrieval Mechanism

When designing a search endpoint, determine:

1. Does the endpoint need the full entity or only a few fields?
2. Must nested objects, collections, and array ordering be preserved?
3. Which fields need querying, and which need sorting or aggregations?
4. Do the field mapping types support doc values?
5. Is there a genuine reason to store a field separately with `store: true`?
6. Does source filtering already satisfy payload reduction needs?
7. Does Spring Data need `_source` so the converter builds `SearchHit.getContent()`, or will the endpoint construct DTOs from field metadata?
8. Are there reindex/update operations depending on `_source`?
9. If changing mappings, how will a new index be created and data reindexed?

For most Spring Data Elasticsearch applications, keeping `_source` is a sensible default. Use source filtering when reducing payloads; enable `store: true` only for fields with a clear separate-retrieval requirement; keep doc values for fields needing sorting, aggregations, or columnar reads.

## 16. References

- [Elasticsearch — Retrieve selected fields](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-fields.html)
- [Elasticsearch — The `_source` field](https://www.elastic.co/guide/en/elasticsearch/reference/current/mapping-source-field.html)
- [Elasticsearch — Stored fields](https://www.elastic.co/guide/en/elasticsearch/reference/current/mapping-store.html)
- [Elasticsearch — Doc values](https://www.elastic.co/guide/en/elasticsearch/reference/current/doc-values.html)
- [Spring Data Elasticsearch — Search result types and operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)

`_source` holds the original JSON and is the primary data source Spring Data uses to build entities. Stored fields return only fields with `store: true` enabled. Doc values store columnar data suitable for sorting, aggregations, and retrieving supported field values. Choosing mechanisms based on read, search, and analytical needs keeps responses lean while maintaining document operability and conversion.
