# `index`, `store`, `doc_values`, and Retrieval Limits per Field Type

Elasticsearch provides multiple storage and indexing mechanisms for a field. The `index`, `store`, and `doc_values` options determine how a field can be searched, retrieved, or used for sorting and aggregations. In addition, `_source` stores the document's JSON content so the application can read back the original data.

These three options address different goals:

- `index`: builds structures for querying on the field.
- `store`: stores the field's value separately so Elasticsearch can return it via `stored_fields`.
- `doc_values`: stores data in columnar format to support sorting, aggregations, and certain script/field-retrieval operations.

Do not enable all three out of habit. Choose based on how the application searches and reads data, while keeping in mind that `_source` is a separate mechanism.

## 1. Four Mechanisms to Distinguish

| Mechanism | Primary purpose | How to retrieve or use |
| --- | --- | --- |
| Inverted index / search structures | Find documents by field content or values. | Queries such as `match`, `term`, `range` depending on field type and mapping. |
| `store: true` | Store the field value separately to return on request. | `stored_fields` in Get/Search APIs. |
| `doc_values: true` | Store columnar data for sorting, aggregations, and scripts. | `sort`, `aggs`, `docvalue_fields`, and certain scripts. |
| `_source` | Store the document's JSON content to reconstruct data. | Returned by default in hits; supports source filtering. |

These mechanisms can coexist on a single field. For instance, a `keyword` field can be indexed, have doc values, and also appear in `_source`. That does not mean these three storage paths substitute for one another.

## 2. `index` — Indexing for Search

`index` controls whether Elasticsearch creates search indexing structures for the field to serve queries. For many data types, the default is `true`.

### 2.1. Fields with `index: true`

When a field is indexed, Elasticsearch can match documents based on that field according to its data type semantics:

- `text` fields are processed by an analyzer to produce tokens for full-text search.
- `keyword` fields are indexed as intact values for exact matching.
- Numeric and date-time fields use indexing structures suitable for value queries, ranges, and typed sorting/querying.

Mapping example:

~~~json
{
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "index": true
      },
      "status": {
        "type": "keyword",
        "index": true
      },
      "price": {
        "type": "long",
        "index": true
      }
    }
  }
}
~~~

You can search `title` with `match`, filter `status` with `term`, and filter `price` with `range`.

### 2.2. Fields with `index: false`

When `index: false` is set, Elasticsearch does not build standard search indexing structures for the field. The value can still reside in `_source`, and if the field type supports doc values, doc values may still remain enabled.

Example:

~~~json
{
  "mappings": {
    "properties": {
      "debugLabel": {
        "type": "keyword",
        "index": false
      }
    }
  }
}
~~~

The application can read `debugLabel` from `_source`, but cannot use it as an indexed field for standard `term` queries. If the field has doc values, it can still be used for doc-values-backed operations such as sorting or aggregations.

`index: false` is helpful when a field does not need filtering or searching yet still needs to be stored for display, sorting, or aggregation. It can lower indexing overhead, though it does not automatically exclude the field from the document or `_source`.

### 2.3. `index` Is Not the Same as `enabled`

`index: false` applies to a field with a specific mapping type. For an object, `enabled: false` has a different meaning: Elasticsearch does not parse that object's contents to index its sub-fields, although the content can still be kept in `_source`.

Do not use `index: false` on an object as a replacement for `enabled: false` if your goal is to stop Elasticsearch from processing the entire sub-field tree. Pick the right option for the field type and Elasticsearch version.

## 3. `store` — Storing Field Values Separately

By default, `store` is `false`. Elasticsearch does not store the field as an individual stored field. However, the value normally remains in `_source` if `_source` is enabled.

When `store: true` is set, Elasticsearch stores the field's value separately so it can be returned via `stored_fields` without fetching the entire `_source`.

Mapping example:

~~~json
{
  "mappings": {
    "properties": {
      "title": {
        "type": "text"
      },
      "legacyCode": {
        "type": "keyword",
        "store": true
      }
    }
  }
}
~~~

Retrieving a stored field in the Search API:

~~~http
GET /articles/_search
Content-Type: application/json

{
  "stored_fields": ["legacyCode"],
  "query": {
    "match": {
      "title": "Elasticsearch guide"
    }
  }
}
~~~

The stored field's value is returned in the `fields` section of the hit. If you also want standard JSON content, you can request `_source` alongside it or use source filtering as needed.

### 3.1. When Is `store: true` Needed?

Consider stored fields when:

- The application frequently needs only a few individual fields and wants to avoid reading the entire `_source`.
- There is a clear reason to retrieve fields via `stored_fields`.
- The field must be stored separately by data design or read API contract.

In most applications, `_source` already handles document retrieval well. Enabling `store: true` for every field typically increases storage and write overhead without significant benefit.

### 3.2. `store` Does Not Make a Field Searchable

`store: true` only controls storing the field value separately for retrieval. It does not substitute for `index: true`.

For instance, a field with `index: false, store: true` can be returned via `stored_fields`, but does not become searchable via `term` or `match` like an indexed field.

Conversely, a field with `index: true, store: false` remains normally searchable. If `_source` is enabled, the application still reads its value back from `_source`.

## 4. `doc_values` — Columnar Storage

`doc_values` is a columnar storage structure optimized for operations that read field values across many documents, such as:

- Sorting results by field value.
- Aggregations such as `terms`, `min`, `max`, `avg`, `sum` depending on data type.
- Retrieving values via `docvalue_fields`.
- Certain script operations that need to read field values.

For most field types that support doc values, `doc_values` defaults to `true`. `text` fields do not support doc values in the standard way.

### 4.1. Doc Values Example

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

Sorting by price:

~~~json
{
  "sort": [
    { "price": { "order": "asc" } }
  ]
}
~~~

Aggregating by category:

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

### 4.2. Disabling Doc Values

Setting `doc_values: false` prevents Elasticsearch from generating doc values for a field supporting that option. If the field still has `index: true`, it remains searchable, but operations relying on doc values—such as standard sorting and aggregations—will be unavailable or will not work as expected.

Example:

~~~json
{
  "mappings": {
    "properties": {
      "eventCode": {
        "type": "keyword",
        "index": true,
        "doc_values": false
      }
    }
  }
}
~~~

The `eventCode` field can still be used for exact queries, but doc values cannot be used for sorting/aggregating on this field. Only disable doc values when you are certain the application will not need those operations.

### 4.3. `index: false` with `doc_values: true`

These two options are independent. A field can skip search indexing while keeping doc values for sorting or aggregations:

~~~json
{
  "mappings": {
    "properties": {
      "reportingGroup": {
        "type": "keyword",
        "index": false,
        "doc_values": true
      }
    }
  }
}
~~~

This can be a good fit if the application only needs to group or sort by `reportingGroup` without searching for documents by that value. Test the actual operations you plan to use to verify the field type supports the desired behavior.

### 4.4. Retrieving Values with `docvalue_fields`

You can instruct Elasticsearch to return doc value entries in the `fields` section of a hit:

~~~http
GET /products/_search
Content-Type: application/json

{
  "_source": false,
  "docvalue_fields": ["price", "createdAt"],
  "query": {
    "match_all": {}
  }
}
~~~

`docvalue_fields` works only for fields with doc values and supported data types. It does not return full JSON objects, does not replace `_source`, and is not a retrieval mechanism for every field type. For dates, you can specify a format to control how date-time values are returned.

Doc values are optimized for field-oriented access across many documents, not for reconstructing original JSON intact. For multi-valued fields, the returned order or representation may differ from the order in `_source`; do not use doc values as a byte-for-byte copy of the original array.

## 5. `_source` — The Document's Original JSON Content

`_source` stores the JSON content sent when indexing the document. It is the standard data source for returning documents and converting them into Java entities in Spring Data Elasticsearch.

Hit example:

~~~json
{
  "_index": "products",
  "_id": "KB-001",
  "_source": {
    "name": "Mechanical Keyboard",
    "category": "Accessories",
    "price": 129900,
    "reportingGroup": "peripherals"
  }
}
~~~

`_source` is independent of per-field `index`, `store`, and `doc_values`:

- Fields with `index: false` can still appear in `_source`.
- Fields with `store: false` can still be read from `_source`.
- Fields with `doc_values: false` can still be read from `_source`.
- Fields with `index: true` do not require `store: true` to read back their content.

### 5.1. Source Filtering

When only a subset of fields is needed, you can filter `_source` in the request:

~~~json
{
  "_source": ["name", "category"],
  "query": {
    "term": {
      "category": "Accessories"
    }
  }
}
~~~

Source filtering reduces the amount of JSON returned over the network and the data deserialized on the client. It does not mean the remaining fields were removed from the index or are not stored in `_source`.

You can exclude fields using `excludes` syntax or combine `includes`/`excludes` per the API. This is a clean way to optimize response payloads when the application does not need the entire document.

### 5.2. When to Disable `_source`?

Elasticsearch allows disabling `_source` in certain setups, but doing so removes the ability to retrieve the original JSON through standard means. Operations that depend on source—such as reindexing, source-based document updates, or converting search hits into complete entities—can become restricted.

For Spring Data Elasticsearch applications, `_source` is usually required so the converter can reconstruct entities from search results. Only consider disabling `_source` after designing an alternative storage and retrieval mechanism and accepting the operational trade-offs.

## 6. Capabilities by Field Type

Not all field types support every option identically. The table below summarizes common cases; check documentation for your exact Elasticsearch version and field type.

| Field type | `index` | `store` | `doc_values` | Notes |
| --- | --- | --- | --- | --- |
| `text` | Yes | Yes | No standard doc values | Uses inverted index for full-text; for sorting/aggregations, typically add a `keyword` sub-field. |
| `keyword` | Yes | Yes | Yes, usually enabled by default | Well suited for exact matching, sorting, and terms aggregations. |
| `long`, `integer`, `double`, `float` | Yes | Yes | Yes, usually enabled by default | Supports numeric queries, sorting, and aggregations. |
| `date` | Yes | Yes | Yes, usually enabled by default | Can query by range and sort chronologically. |
| `boolean` | Yes | Yes | Yes | Can filter and aggregate by boolean value. |
| `ip` | Yes | Yes | Yes | Supports IP address/range filtering, sorting, and aggregations per type support. |
| `object` | Not applicable as a scalar field | Not applicable as a scalar | Not applicable as a scalar | Sub-fields carry their own mappings and options. |
| `nested` | Not applicable as a scalar field | Not applicable as a scalar | Not applicable as a scalar | Sub-fields inside nested objects carry their own options. |

For `text`, if aggregations/sorting directly on content are truly required, Elasticsearch offers `fielddata`, though it can consume large amounts of heap memory. The recommended design is usually a multi-field: one `text` field for full-text search and one `keyword` sub-field for exact matching, sorting, or aggregation.

## 7. Combining Options in the Same Mapping

Catalog mapping example:

~~~json
{
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "index": true
      },
      "category": {
        "type": "keyword",
        "index": true,
        "doc_values": true
      },
      "reportingGroup": {
        "type": "keyword",
        "index": false,
        "doc_values": true
      },
      "legacyCode": {
        "type": "keyword",
        "index": false,
        "store": true
      },
      "price": {
        "type": "long",
        "index": true,
        "doc_values": true
      },
      "description": {
        "type": "text",
        "index": true,
        "fields": {
          "raw": {
            "type": "keyword"
          }
        }
      }
    }
  }
}
~~~

With this mapping:

- `title` is used for full-text search.
- `category` is used for exact filtering, sorting, or aggregations.
- `reportingGroup` is not indexed for search queries, yet can still use doc values for sorting/aggregations.
- `legacyCode` can be returned via `stored_fields`, but is not used for inverted-index searches.
- `price` is used for range queries, sorting, and aggregations.
- `description` can be full-text searched via the main field and `description.raw` can be used for whole-string operations.

Values can still reside in `_source` if source is enabled. There is no need to set `store: true` on `title`, `category`, or `price` merely so the application can read them back.

## 8. Retrieving Data via Different Mechanisms

You can combine source filtering, stored fields, and docvalue fields in a single search request:

~~~http
GET /catalog/_search
Content-Type: application/json

{
  "_source": ["title", "category"],
  "stored_fields": ["legacyCode"],
  "docvalue_fields": ["price"],
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

A response hit may contain:

- `_source` with the selected `title` and `category` fields.
- `fields.legacyCode` for the stored field.
- `fields.price` for the doc value.
- Metadata such as `_index`, `_id`, and `_score` depending on the request type.

Do not request all three mechanisms for the same field without reason. Pick the simplest retrieval mechanism that fulfills the application's requirement.

## 9. Declaring in Spring Data Elasticsearch

Spring Data Elasticsearch exposes attributes on `@Field` to describe mappings. Example:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "catalog")
public class CatalogItem {

    @Id
    private String id;

    @Field(type = FieldType.Text, index = true)
    private String title;

    @Field(
        type = FieldType.Keyword,
        index = true,
        docValues = true
    )
    private String category;

    @Field(
        type = FieldType.Keyword,
        index = false,
        docValues = true
    )
    private String reportingGroup;

    @Field(
        type = FieldType.Keyword,
        index = false,
        store = true
    )
    private String legacyCode;

    @Field(
        type = FieldType.Long,
        index = true,
        docValues = true
    )
    private Long price;

    // Constructor, getters and setters
}
~~~

The attributes map directly to Elasticsearch mapping options:

- `index = true`: index the field for searching.
- `index = false`: do not index the field for standard queries.
- `store = true`: store the field separately for retrieval via stored fields.
- `docValues = true`: enable doc values if supported by the field type.

Annotation defaults usually reflect Elasticsearch mapping defaults, though declaring them explicitly helps when designs have special requirements. Verify annotation APIs against your project's Spring Data Elasticsearch version.

### 9.1. Using Multi-Fields for `text` and `keyword`

A Java property can be indexed in multiple ways via multi-fields. The main field is `text` for full-text search, while the `keyword` sub-field serves exact matching, sorting, and aggregations:

~~~java
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.InnerField;
import org.springframework.data.elasticsearch.annotations.MultiField;

@MultiField(
    mainField = @Field(type = FieldType.Text),
    otherFields = {
        @InnerField(suffix = "keyword", type = FieldType.Keyword)
    }
)
private String description;
~~~

The resulting mapping can contain `description` as `text` and `description.keyword` as `keyword`. Full-text search uses `description`; sorting or aggregations typically use `description.keyword`.

Multi-fields do not add a separate Java property and do not change `_source`; they create multiple indexing strategies for the same source value.

## 10. Impact on Queries, Sorting, and Aggregations

| Configuration | Query | Sort | Aggregation | Value retrieval |
| --- | --- | --- | --- | --- |
| `index: true`, doc values enabled | Supports queries per field type. | Supported on types with doc values. | Supported on types with doc values. | `_source`; plus stored/docvalue fields if configured. |
| `index: false`, doc values enabled | Cannot be used as an indexed field for standard queries. | Usable on types supporting doc values. | Usable on types supporting doc values. | `_source` or docvalue fields; stored fields if enabled. |
| `index: true`, `doc_values: false` | Still queryable via index structures. | Doc-values-based sorting unavailable in the standard way. | Doc-values-based aggregations unavailable in the standard way. | `_source`; stored fields if enabled. |
| `index: false`, `store: true`, doc values off | Cannot be queried as an indexed field. | No doc values for sorting. | No doc values for aggregations. | Retrievable via stored fields or `_source`. |

Exact capabilities also depend on the field type and query/aggregation used. This table describes common design patterns and does not replace per-field mapping documentation.

## 11. Storage Cost and Performance

Each mechanism carries its own cost:

- Inverted indices or search structures increase index size but enable efficient queries.
- Stored fields write an additional separate copy of the field value, increasing storage size and write cost.
- Doc values consume disk space yet enable efficient sorting/aggregations without loading all values onto the JVM heap.
- `_source` preserves original JSON, useful for returning documents, updates, and reindexing; its size depends on stored payload size.

Do not turn off `index` merely to save space if the application needs to search on that field. Do not turn off `doc_values` if dashboards or APIs need sorting/aggregations. Do not turn on `store` for every field if `_source` already covers retrieval.

For `text` fields needing aggregations, enabling `fielddata` can load data into heap memory and substantially raise memory pressure. A `keyword` sub-field is usually the better choice for exact matching and aggregations.

## 12. Changing Options After an Index Exists

Mapping options like `index`, `store`, and `doc_values` generally cannot be altered freely on an already-created field. In particular, changing indexing options affects existing index structures.

When mapping changes are required, the standard approach is:

1. Create a new index with a mapping specifying `index`, `store`, and `doc_values` per the new design.
2. Reindex data from the old index into the new index.
3. Verify queries, sorting, aggregations, and source/stored/doc values retrieval.
4. Switch the alias to the new index once data is verified.

Updating an existing field mapping does not automatically rebuild old indexed data. Even if only adding a new multi-field, old documents must also be updated/reindexed so the new sub-field contains searchable data.

## 13. Common Mistakes

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `term` query finds nothing on field | Field has `index: false`. | Enable indexing on a new index if queries are needed, then reindex data. |
| `stored_fields` returns no value | Field was not declared with `store: true`. | Enable `store` in a new mapping or read the field from `_source`. |
| Sort or aggregation errors/missing data | Field lacks doc values support or `doc_values: false` was set. | Use a field type supporting doc values, re-enable on a new index, or use an appropriate sub-field. |
| Cannot aggregate on `text` | `text` has no standard doc values. | Add a `keyword` sub-field and aggregate on the sub-field. |
| Disabled `store` yet application still reads field | The value is still present in `_source`. | This is normal behavior; `store` and `_source` are separate mechanisms. |
| Changed mapping but old data behaves unchanged | Existing inverted index/doc values are not automatically rebuilt. | Create a new index and reindex. |
| `docvalue_fields` does not return field | Field is unsupported or doc values are disabled. | Inspect mapping type and `doc_values`. |

## 14. How to Choose Configuration per Requirement

When designing mappings, you can apply these practical rules:

1. Fields needing full-text search: use `text` with `index: true`; add a `keyword` sub-field if sorting/aggregations are needed.
2. Fields needing exact filtering, sorting, or aggregations: use `keyword` or an appropriate scalar type, keeping `index: true` and default doc values.
3. Fields used solely for sorting or aggregations: consider `index: false` while keeping doc values if the type supports it.
4. Fields not needing search yet requiring isolated retrieval via `stored_fields`: consider `store: true`; if `_source` suffices, skip separate storage.
5. Fields only returned alongside the document: usually rely on `_source`, without enabling `store` just to read the field.
6. Fields not needing search, sorting, or aggregations: consider trimming unnecessary index structures while keeping clarity on how the application reads data.
7. Before disabling `_source`, evaluate the impact on entity conversion, updates, and reindexing.

`index`, `store`, and `doc_values` are three independent options: `index` serves search, `store` serves isolated field retrieval, and `doc_values` serves sorting/aggregations/scripts. `_source` preserves the original JSON and is usually Spring Data Elasticsearch's default data-reading mechanism. Picking the right mechanism per field balances search capabilities, retrieval patterns, index size, and performance.
