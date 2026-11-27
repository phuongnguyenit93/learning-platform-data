# Choosing the Right Mapping and doc_values Before Optimizing Queries

Query performance in Elasticsearch depends heavily on how documents are indexed. A query can be concise and syntactically valid yet still be slow if a field uses the wrong type, has an inappropriate analyzer, requires loading fielddata into heap for sorting/aggregations, or has a mapping that creates unnecessary structures.

In Spring Data Elasticsearch, mappings are commonly declared with annotations on entities or created explicitly via IndexOperations. Decisions such as `text` versus `keyword`, enabling `index` or `doc_values`, and whether to create multi-fields directly affect how Elasticsearch stores and accesses data.

The key principle is to design mappings around how each field will be used: full-text search, exact filtering, sorting, aggregations, scripting, or solely returned in the response. Do not start by turning on more caching or increasing heap before confirming that fields have appropriate representations.

This article explains inverted indexes, doc values, and `_source`; how to choose field types; the trade-offs between `index` and `doc_values`; mappings in Spring Data Elasticsearch; how to inspect costs; and a safe process for changing mappings.

## 1. Mapping determines how Elasticsearch stores fields

A mapping describes the structure and how Elasticsearch processes each field in a document. It is not merely a schema for validating JSON. Mapping dictates whether a field is analyzed into tokens, indexed for searching, stored in a columnar structure for sorting/aggregations, or kept only in `_source`.

Example product document:

~~~json
{
  "sku": "SKU-1001",
  "name": "Wireless Ergonomic Mouse",
  "description": "Bluetooth mouse with rechargeable battery",
  "category": "Accessories",
  "priceInCents": 259900,
  "stock": 42,
  "active": true,
  "createdAt": "2026-11-13T08:00:00Z"
}
~~~

A product search page might need to:

- Search keywords in `name` and `description`.
- Filter exactly on `category`, `active`, and `sku`.
- Filter price ranges on `priceInCents`.
- Sort by `priceInCents` or `createdAt`.
- Run aggregations counting products by `category`.
- Return `name`, `description`, and other fields to the user.

Not every field needs the same structure. `name` fits `text` for full-text search; `category` fits `keyword` for filtering and grouping; `priceInCents` fits `long` for range queries and sorting; `createdAt` fits `date`.

A well-designed mapping allows Elasticsearch to perform the exact operations queries request without building expensive structures at query time.

## 2. Three storage representations to distinguish: inverted index, doc values, and _source

Elasticsearch uses different storage structures for a field. Three concepts that are often confused are inverted index, doc values, and `_source`.

### 2.1. Inverted index

An inverted index maps terms to the list of documents containing them. It is the primary structure for search queries.

For numeric and certain specialized fields, Elasticsearch may use index structures such as BKD trees to serve range queries rather than representing every value as a term in a traditional inverted index. The `index` mapping property is broader than any single underlying storage structure.

Example of a `text` field `name` after analyzer processing:

~~~text
"Wireless Ergonomic Mouse"
        |
        v
["wireless", "ergonomic", "mouse"]
~~~

The inverted index lets Elasticsearch find documents containing the term `mouse` or combine multiple terms according to the query.

With `keyword`, the value is usually indexed as a single intact term, suitable for `term` queries, exact filters, and exact lookup operations.

### 2.2. Doc values

Doc values are a document-to-value storage structure, often called column-oriented or columnar. Instead of going from a term to documents, Elasticsearch can read a field's value across a set of documents to serve:

- Sorting.
- Aggregations.
- Accessing fields in scripts via doc values.
- Certain internal operations that need per-document field values.

For example, doc values on `category` allow aggregations to group documents by category value. Doc values on `priceInCents` enable sorting by price and computing min/max/avg.

Doc values are typically stored on disk in a format optimized for columnar access and can leverage the filesystem cache. They are not equivalent to keeping a full copy of the field in Java heap.

### 2.3. _source

`_source` is the stored JSON of the document so the original content can be returned or reprocessed. It is usually enabled by default.

`_source` is useful for:

- Returning documents to the application.
- Reindexing.
- Update API.
- Reading fields in certain scripts or fetch operations.
- Inspecting written data.

`_source` is neither an inverted index nor doc values. Having a field present in `_source` does not mean it can be sorted or aggregated efficiently.

| Structure | Primary access direction | Typical purpose |
|---|---|---|
| Inverted index | Term → document | Search, term/match/range queries depending on field |
| Doc values | Document → field value | Sorting, aggregations, scripts |
| _source | Document → original JSON | Fetch, update, reindex, display |

A field can have both an inverted index and doc values at the same time. For example, `keyword` and numeric fields typically support both by default.

## 3. Choosing field types based on query usage

Do not choose field types solely based on Java types. Look at how the field is queried.

| Requirement | Usually suitable field type |
|---|---|
| Natural language search, token analysis | text |
| Exact match, filter, sort, terms aggregation | keyword |
| Prices, quantities, scores | integer, long, float, double, or scaled_float |
| Timestamps | date or date_nanos |
| true/false | boolean |
| IP addresses | ip |
| Geographic locations | geo_point or geo_shape |
| Structured objects | object |
| Objects requiring independent element-level querying | nested |
| Dynamic key/value pairs without creating mappings per key | flattened where appropriate |

Choose field types based on query patterns and data semantics. Converting a numeric value into `keyword` just for exact match can make range queries and numeric sorting unsuitable. Conversely, using `text` for an identifier can cause exact filters to behave unexpectedly.

## 4. text and keyword: the most important distinction

### 4.1. text is for full-text search

`text` fields are processed by an analyzer before indexing. Analyzers typically consist of character filters, a tokenizer, and token filters.

Example:

~~~json
{
  "name": {
    "type": "text",
    "analyzer": "standard"
  }
}
~~~

With a `text` field, a `match` query searches against the analyzed tokens. This field normally does not have doc values by default because its main purpose is full-text search.

`text` is suitable for:

- Product names.
- Descriptions.
- Article contents.
- Log messages.
- Text that needs word or phrase matching.

`text` is not the default choice for sorting or terms aggregations. To sort or group by the intact value, a `keyword` sub-field is normally added.

### 4.2. keyword is for exact values

`keyword` does not tokenize strings into words the way `text` does. It stores the value as a single term, suitable for exact matching and bucket aggregations.

~~~json
{
  "category": {
    "type": "keyword"
  }
}
~~~

Example query:

~~~json
{
  "term": {
    "category": "Accessories"
  }
}
~~~

`keyword` is usually suitable for:

- SKUs and identifiers.
- Statuses.
- Categories.
- Country codes.
- Emails or usernames when exact matching is needed.
- Fields used for sorting or terms aggregations.

If case normalization is needed while preserving exact semantics, a `keyword` normalizer can be used:

~~~json
{
  "sku": {
    "type": "keyword",
    "normalizer": "lowercase_normalizer"
  }
}
~~~

Normalizers are defined in the index analysis settings. Ensure the application and queries send values matching the chosen normalization rules.

### 4.3. Multi-fields: both full-text and exact

A field can have multiple representations via multi-fields. For example, `name` has a primary `text` field and a `keyword` sub-field:

~~~json
{
  "name": {
    "type": "text",
    "analyzer": "standard",
    "fields": {
      "keyword": {
        "type": "keyword",
        "ignore_above": 256
      }
    }
  }
}
~~~

Then:

- Full-text queries use `name`.
- Exact filters use `name.keyword`.
- Sorting uses `name.keyword`.
- Terms aggregations use `name.keyword`.

Example:

~~~json
{
  "sort": [
    {
      "name.keyword": {
        "order": "asc"
      }
    }
  ]
}
~~~

Not every `text` field needs a `keyword` sub-field. Only create one when there is an exact/sort/aggregation use case. If a field can be arbitrarily long, consider `ignore_above` and how the application handles values exceeding the threshold.

`ignore_above` prevents values longer than the limit from being indexed into the `keyword` sub-field; the value can still remain in `_source`. In that case, the document can still be found via the `text` field, but has no corresponding `keyword` term or doc value for sorting or aggregating on that value.

## 5. How do doc values work?

Doc values organize data by field so Elasticsearch can read field values across many documents without loading the entire field into heap like `text` fielddata.

Example aggregation:

~~~json
{
  "aggs": {
    "products_by_category": {
      "terms": {
        "field": "category"
      }
    }
  }
}
~~~

Elasticsearch needs to read `category` across matching documents and group them. Doc values provide an appropriate representation for that work.

Example sort:

~~~json
{
  "sort": [
    {
      "priceInCents": {
        "order": "asc"
      }
    }
  ]
}
~~~

Doc values allow retrieving `priceInCents` values to compare and sort hits.

### 5.1. Which field types have doc values?

Doc values are supported by many field types commonly used for sorting and aggregations, such as `keyword`, numeric, `date`, `boolean`, and several other types.

`text` does not have doc values in the standard way. Certain field types have specific support rules or do not support doc values. Check the mapping documentation for the exact field type and Elasticsearch version before configuring.

For supported fields, `doc_values` is usually enabled by default. There is no need to declare `doc_values: true` on every field when it is already the default. Declare it explicitly when you want to disable it and have confirmed no query pattern needs it.

### 5.2. Doc values are not an in-RAM cache

Doc values are normally stored on disk and read via columnar access mechanisms. The filesystem cache can keep frequently accessed pages in memory, but that does not mean the entire field is loaded into Java heap.

This differs from `text` fielddata, which can consume substantial heap. However, doc values are not free: they take disk space, add indexing/merge cost, and sorting/aggregations still consume CPU and memory for buckets or sort state.

Do not assume that enabling doc values makes every aggregation instantly fast. Performance also depends on document count, cardinality, bucket count, shard count, filter selectivity, and caches.

## 6. index and doc_values are two independent choices

Two parameters are often confused:

- `index`: whether the field is indexed for queries.
- `doc_values`: whether the field has a columnar representation for operations like sorting/aggregations.

For field types that support both, they can be configured for different needs:

| index | doc_values | Typical meaning |
|---|---|---|
| true | true | Can be searched and used for sorting/aggregations |
| true | false | Has inverted index, no doc values |
| false | true | No inverted index for normal search, but doc values can be used for supported sorting/aggregations/scripts |
| false | false | Kept only in source if configured, neither structure exists for the field |

Check exact capabilities per field type. Setting `index: false` does not make a field term-queryable solely via doc values. Setting `doc_values: false` does not disable the inverted index if `index` remains true.

### 6.1. When to disable index?

If a field is only needed for sorting/aggregations and never queried directly, consider `index: false` while keeping doc values if the field type supports it.

For example, a field `internalRank` used only for sorting:

~~~json
{
  "internalRank": {
    "type": "long",
    "index": false,
    "doc_values": true
  }
}
~~~

Before choosing this approach, inspect all actual queries. If you later need a range filter or term query on the field, the current configuration may not support it.

### 6.2. When to disable doc_values?

If a field only needs to be searched via the inverted index and is never sorted, aggregated, or accessed via doc values, consider disabling doc values for field types that support that option.

~~~json
{
  "externalReference": {
    "type": "keyword",
    "index": true,
    "doc_values": false
  }
}
~~~

Disabling it can reduce storage/indexing costs, but removes the ability to use the field for doc-values-based sorting and aggregations. Do not disable it if current queries, scripts, or dashboards need it.

### 6.3. Storing only in _source

If a field is only returned to clients and does not need search, sorting, aggregations, or script access, consider neither indexing it nor creating doc values:

~~~json
{
  "longDescription": {
    "type": "text",
    "index": false
  }
}
~~~

With `text`, doc values are already unsupported by default. The field can still remain in `_source` to be returned if `_source` is enabled.

Distinguish source-only fields from `store: true`. Stored fields are a separate storage mechanism; there is no need to enable `store` just to return a field when `_source` already meets the requirement.

## 7. Why shouldn't fielddata be enabled arbitrarily on text?

Elasticsearch has a `fielddata` option for `text` fields to support sorting/aggregations on text. When enabled, fielddata is built from the inverted index and can consume substantial heap.

Example:

~~~json
{
  "description": {
    "type": "text",
    "fielddata": true
  }
}
~~~

This is rarely the first choice. If exact sorting or terms aggregations are needed, creating a `keyword` multi-field is usually more appropriate:

~~~json
{
  "description": {
    "type": "text",
    "fields": {
      "keyword": {
        "type": "keyword",
        "ignore_above": 256
      }
    }
  }
}
~~~

Fielddata on `text` may be necessary for special use cases, such as aggregating on analyzed tokens. However, you must evaluate heap, cardinality, shard count, and the fielddata cache.

Before enabling fielddata, answer:

- Do you truly need to aggregate tokens rather than intact values?
- Can you use a `keyword` multi-field instead?
- What is the field's cardinality?
- Is there enough heap headroom?
- Can you restrict queries or apply filters to reduce participating documents?

Do not enable fielddata just to make an error like "Fielddata is disabled on text fields" disappear. That error usually indicates the query is using the wrong field representation.

## 8. Choosing mappings for numeric and date fields

Numeric fields should use numeric types matching their value range and precision.

| Type | Common use cases |
|---|---|
| byte, short, integer, long | Integers with appropriate value ranges |
| unsigned_long | Non-negative integers with a large range, when supported |
| half_float, float, double | Floating-point numbers |
| scaled_float | Fixed-scale decimals, e.g., monetary values in minor units |

Money example:

~~~json
{
  "priceInCents": {
    "type": "long"
  }
}
~~~

Storing money as an integer in minor units usually avoids floating-point rounding errors. If using `scaled_float`, choose a `scaling_factor` matching business precision.

Numeric fields usually have index structures optimized for numeric queries, such as range queries, along with doc values by default. Doc values are useful for sorting, aggregations, and scripts.

Date field:

~~~json
{
  "createdAt": {
    "type": "date",
    "format": "strict_date_optional_time||epoch_millis"
  }
}
~~~

Dates are typically stored internally as numeric timestamps and support sorting/aggregations via doc values. Choose formats matching your write and query data. Do not turn timestamps into `keyword` if you need time-range queries.

## 9. Mappings for boolean, IP, and specialized fields

Boolean fits status flags:

~~~json
{
  "active": {
    "type": "boolean"
  }
}
~~~

IP fits IPv4/IPv6 addresses and supports specialized IP queries:

~~~json
{
  "clientIp": {
    "type": "ip"
  }
}
~~~

Geo fields need the right type, such as `geo_point` for point coordinates. Specialized field types have their own sorting, aggregation, or doc values capabilities; do not apply `keyword`/numeric rules universally to all types.

If a field is solely for display, it may not need indexing. If you need prefix, range, or geo distance searches, choose the appropriate type and query from the start.

## 10. Object, nested, and flattened also affect queries

Regular objects are flattened into field paths. For object arrays, queries across fields can cross-match between different array elements when using standard object mapping.

Example:

~~~json
{
  "offers": [
    { "seller": "A", "price": 100 },
    { "seller": "B", "price": 500 }
  ]
}
~~~

If you must ensure `seller` and `price` belong to the same element, you may need `nested` mapping and `nested` queries. Nested has higher storage and query costs than regular objects, so only use it when semantics require it.

`flattened` fits objects with many dynamic keys when you do not want to create a separate mapping field per key. It has trade-offs in data types and query capabilities; it does not replace `object`/`nested` in all cases.

Choosing among `object`/`nested`/`flattened` is a critical mapping decision before optimizing queries, because changing the structure later usually requires reindexing.

## 11. Spring Data Elasticsearch: declaring mappings with annotations

Spring Data Elasticsearch lets you declare mappings on entity classes.

Example:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.InnerField;
import org.springframework.data.elasticsearch.annotations.MultiField;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @MultiField(
        mainField = @Field(
            type = FieldType.Text,
            analyzer = "standard"
        ),
        otherFields = {
            @InnerField(
                suffix = "keyword",
                type = FieldType.Keyword,
                ignoreAbove = 256
            )
        }
    )
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Long)
    private Long priceInCents;

    @Field(type = FieldType.Boolean)
    private Boolean active;

    @Field(type = FieldType.Date)
    private Instant createdAt;
}
~~~

In this example:

- `sku` is `keyword` for exact filters.
- `name` is `text` for full-text search and `name.keyword` for exact/sort.
- `category` is `keyword` for filters/aggregations.
- `priceInCents` is `long` for ranges/sorts/aggregations.
- `active` is `boolean`.
- `createdAt` is `date`.

Annotations support different mapping attributes depending on the version. Check `@Field`, `@MultiField`, and `@InnerField` in your actual dependency. For fields needing `docValues = false` or `index = false`, use the annotation attributes if your version supports them and verify the generated mapping via the API.

### 11.1. Example disabling doc values for keyword

If a `keyword` field only needs exact queries and does not need sorting/aggregations/script doc-value access, you can declare it according to your API support:

~~~java
@Field(
    type = FieldType.Keyword,
    index = true,
    docValues = false
)
private String externalReference;
~~~

This decision impacts query capabilities. If a dashboard later needs a terms aggregation on `externalReference`, this mapping cannot serve it via doc values.

### 11.2. Example using doc values only

For a numeric field that only needs sorting or aggregations and no search queries on the field, you can configure:

~~~java
@Field(
    type = FieldType.Long,
    index = false,
    docValues = true
)
private Long internalRank;
~~~

Confirm that your field type and version support this configuration. Test actual queries to ensure no filter/range queries depend on the inverted index.

## 12. Creating mappings explicitly with IndexOperations

Annotations fit well when the schema is tightly coupled to the domain class. For index versioning, aliases, analyzers, or complex mappings, you can create indexes and mappings explicitly via `IndexOperations`.

Example mapping JSON:

~~~json
{
  "properties": {
    "sku": {
      "type": "keyword"
    },
    "name": {
      "type": "text",
      "analyzer": "standard",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    },
    "category": {
      "type": "keyword"
    },
    "priceInCents": {
      "type": "long"
    },
    "active": {
      "type": "boolean"
    },
    "createdAt": {
      "type": "date"
    },
    "internalRank": {
      "type": "long",
      "index": false,
      "doc_values": true
    }
  }
}
~~~

Spring Data can derive mappings from entity metadata:

~~~java
IndexOperations indexOperations =
    operations.indexOps(Product.class);

indexOperations.create();
indexOperations.putMapping(
    indexOperations.createMapping()
);
~~~

Method names and mapping creation approaches may vary by version. Create the index with appropriate settings before applying mappings, especially if custom analyzers are used.

For self-managed JSON mappings, use `IndexOperations.putMapping(...)` or a version-appropriate client API. Keep mappings in source control so changes can be reviewed and deployed reproducibly.

## 13. Dynamic mapping and dynamic templates

If no mapping is declared for a new field, Elasticsearch can automatically infer its type via dynamic mapping. This is convenient for prototyping, but can produce unintended schemas:

- Strings are mapped as `text` with a `keyword` sub-field by the default dynamic template.
- Date strings may be recognized via date detection.
- Numbers are mapped to numeric types based on the first value seen.
- Arbitrary fields can cause mappings to grow rapidly.

Dynamic templates let you define rules based on the name or type of new fields. For example, every field ending in `Code` can be mapped as `keyword`:

~~~json
{
  "dynamic_templates": [
    {
      "code_fields": {
        "match": "*Code",
        "mapping": {
          "type": "keyword"
        }
      }
    }
  ]
}
~~~

You can set `dynamic` to `false` to avoid adding new fields to the mapping, or `strict` to reject documents containing undeclared fields, depending on your goal.

For systems with stable schemas, explicit mappings or dynamic templates are usually easier to control than letting Elasticsearch guess every field.

## 14. Choosing doc_values for each query pattern

A practical decision table:

| Query pattern | Mapping to consider |
|---|---|
| Full-text match on name | text + suitable analyzer |
| Exact filter on SKU | keyword, index true |
| Sort by exact intact name | name.keyword with doc values |
| Terms aggregation by category | keyword with doc values |
| Range filter on price | numeric with index true |
| Sort by price | numeric with doc values |
| Min/max/avg price | numeric with doc values |
| Sort by time | date with doc values |
| Display long description only | source-only if not searched |
| Exact query without sort/aggregation | keyword; consider doc_values false if certain |
| Sort/aggregation only, no search | doc_values true and index false if field type supports it |
| Full-text search and sort/aggregation | text + keyword multi-field |

Do not disable doc values just to save a few percent of disk space without checking every query, dashboard, export, and script using that field.

## 15. Scripts and doc values

Painless can read fields via doc values in supported script contexts:

~~~json
{
  "script_fields": {
    "priceWithTax": {
      "script": {
        "source": "doc['priceInCents'].value * params.factor",
        "params": {
          "factor": 1.1
        }
      }
    }
  }
}
~~~

Reading via `doc['field']` is usually preferable when the field has doc values and the script needs indexed values.

A few notes:

- A field may be missing on some documents; check `doc['field'].size()` before accessing `.value`.
- Multi-valued fields can contain multiple values; `.value` retrieves a single value according to doc values semantics.
- Not all field types support doc values.
- Different script contexts expose different variables and access permissions.
- Reading `_source` has different costs from doc values and is not supported identically across all contexts.

Example checking if a field has a value:

~~~painless
if (doc['priceInCents'].size() == 0) {
    return 0;
}
return doc['priceInCents'].value;
~~~

Do not use scripts to replace a native query or sort that can be expressed directly. Scripts can reduce optimization opportunities and increase CPU usage.

## 16. Sorting and aggregations: what doc values help with and what they don't

Doc values are the field-access foundation for sorting and many aggregations, but they do not eliminate the cost of the operation itself.

### 16.1. Sorting

Sorting on numeric/date/keyword fields typically uses doc values. Costs also depend on:

- Number of hits and shards examined.
- Sorting by one or multiple fields.
- Tie-breakers.
- Missing values.
- Multi-valued sort mode.
- Deep pagination and `search_after`.
- Shard-level top-N merging.

If sorting by text, a `keyword` multi-field is usually required. Enabling fielddata on `text` can create heavy heap pressure.

### 16.2. Aggregations

Terms aggregations on `keyword` use doc values to read values. However, high-cardinality aggregations can still consume significant memory because Elasticsearch has to manage many buckets.

Factors include:

- Number of distinct values.
- Size of the document set after filtering.
- Number of shards.
- `size`, `shard_size`, and execution hints where applicable.
- Sub-aggregations.
- Cardinality precision.
- Response size.

If an aggregation is slow, check cardinality and bucket count, not only `doc_values`.

### 16.3. Fielddata cache and heap

The fielddata cache primarily relates to fielddata built for `text` fields and certain related structures. Doc values are not the same as the fielddata cache.

You can inspect fielddata statistics using node stats or the appropriate CAT API. If fielddata heap grows sharply, find which queries are aggregating/sorting on `text` fields and switch to `keyword` sub-fields if semantics fit.

## 17. How far can mappings be modified?

Elasticsearch allows adding new fields to an existing mapping, but many properties of already-created fields cannot be modified arbitrarily.

Usually you cannot directly change:

- A field's type from `text` to `keyword` or `long`.
- The analyzer of an already-indexed field in a way that alters tokenization.
- Enabling/disabling `index` or `doc_values` on an already-created field if the change is unsupported.
- Certain mapping parameters that affect how already-indexed data is represented.

When structural changes are needed, the safe approach is usually:

1. Create a new index with the desired mapping/settings.
2. Reindex data from the old index into the new index.
3. Verify document counts and query behavior.
4. Switch the alias or application to the new index.
5. Monitor and keep a rollback path according to policy.

### 17.1. Adding a multi-field does not auto-populate old data

You can add a multi-field to an existing mapping, such as adding `name.keyword`. The new mapping applies to documents indexed afterward. Existing documents are not automatically re-analyzed to generate new `keyword` terms/doc values.

If sorting/aggregations on the new sub-field are needed across all existing data, you must reindex or re-update the documents so the field is indexed under the new mapping.

### 17.2. Index versioning

A commonly used pattern:

~~~text
products-v1  -> current data and mapping
products-v2  -> new mapping
products     -> read/write alias
~~~

Once migration finishes, switch the alias to `v2` through a controlled process. The application can continue using a stable alias while the schema is upgraded.

## 18. Checking mappings and capabilities before optimizing queries

Do not just read Java annotations and assume the actual mapping is correct. Check directly on the cluster.

Fetch the mapping:

~~~http
GET products/_mapping
~~~

Check field capabilities across one or more indexes:

~~~http
POST products/_field_caps?fields=name,name.keyword,category,priceInCents,createdAt
~~~

Field capabilities are useful when multiple indexes under an alias have different mappings. If the same field is `keyword` in one index and `text` in another, queries or aggregations may fail or behave inconsistently.

Check fielddata:

~~~http
GET _cat/fielddata?v
~~~

Or node stats:

~~~http
GET _nodes/stats/indices/fielddata
~~~

Check index stats:

~~~http
GET products/_stats
~~~

Use the Profile API to understand query execution when needed:

~~~json
{
  "profile": true,
  "query": {
    "bool": {
      "filter": [
        { "term": { "category": "Accessories" } },
        { "range": { "priceInCents": { "gte": 100000, "lte": 500000 } } }
      ]
    }
  }
}
~~~

Profile helps observe query execution, but it carries overhead and does not fully reflect production end-to-end latency. Also measure network, queues, fetch phase, serialization, and cluster load.

## 19. Complete mapping example for a catalog

A mapping suitable for the query patterns discussed:

~~~http
PUT products-v2
{
  "mappings": {
    "dynamic": "strict",
    "properties": {
      "sku": {
        "type": "keyword"
      },
      "name": {
        "type": "text",
        "analyzer": "standard",
        "fields": {
          "keyword": {
            "type": "keyword",
            "ignore_above": 256
          }
        }
      },
      "description": {
        "type": "text",
        "analyzer": "standard"
      },
      "category": {
        "type": "keyword"
      },
      "priceInCents": {
        "type": "long"
      },
      "stock": {
        "type": "integer"
      },
      "active": {
        "type": "boolean"
      },
      "createdAt": {
        "type": "date"
      },
      "internalRank": {
        "type": "long",
        "index": false,
        "doc_values": true
      },
      "externalPayload": {
        "type": "object",
        "enabled": false
      }
    }
  }
}
~~~

This design is intentional:

- `sku` exact filter.
- `name` full-text and exact sort via `name.keyword`.
- `description` full-text without creating a long `keyword` sub-field.
- `category` filter and terms aggregation.
- `priceInCents`/`stock` numeric queries and sorting.
- `active` boolean filter.
- `createdAt` date range/sort.
- `internalRank` used only for sorting/aggregations under the assumed use case, not searched.
- `externalPayload` kept in `_source` without parsing/indexing child fields via `enabled: false`.

`dynamic: strict` helps catch out-of-schema fields, but can cause ingest failures if producers send new fields. Choose `strict` only when the data contract is controlled and the application handles errors appropriately.

## 20. Common mapping mistakes

| Symptom | Common cause | How to fix |
|---|---|---|
| Terms aggregation fails on text | Text has no doc values by default | Use a keyword multi-field or consider controlled fielddata |
| Sorting by name fails | Sort is targeting the text field | Sort on name.keyword |
| Keyword field misses results for long values | ignore_above excludes values from keyword sub-field | Adjust the limit or design another field |
| Numeric range query behaves wrongly | Field mapped as keyword or data has wrong type | Use numeric mapping and check source |
| Aggregation consumes excessive heap | Fielddata on text or high bucket cardinality | Switch to keyword where appropriate, control cardinality |
| Script reports field has no doc values | doc_values disabled or field type unsupported | Use an appropriate mapping or access source per context |
| Disabling doc_values breaks sorting/aggregations | Queries depend on doc values | Enable in a new index and reindex |
| Added keyword sub-field but old docs lack values | New sub-field not indexed on old data | Reindex or update documents |
| Mapping conflict across indexes in alias | Field has differing types | Standardize schema and reindex inconsistent indexes |
| Mapping explosion | Too many dynamic fields | Use explicit mappings, dynamic templates, or flattened |
| Query is correct yet still slow | Wrong field type, high cardinality, too many shards, or fetch cost | Check mappings, profile, and end-to-end metrics |
| index: false prevents filters from matching | Field lacks inverted index for that query | Enable index in a new index if queries need it |
| Data exists only in _source | Field is neither indexed nor has doc values | Define query requirements and reindex |

## 21. Process for choosing mappings before optimizing queries

For each field, document:

1. Does the field need full-text search?
2. Does it need exact filtering?
3. Does it need range queries?
4. Does it need sorting?
5. Does it need aggregations?
6. Do scripts need to access the field via doc values?
7. Does the field have low or high cardinality?
8. Can it contain long values or multiple values in a single document?
9. Does the field only need to be returned from `_source` or does it need indexing?
10. Which queries use the field and at what frequency?

Then choose:

- `text` for full-text search.
- `keyword` for exact matching, sorting, and terms aggregations.
- numeric/date/boolean/ip/geo types according to semantics.
- multi-field if a value needs multiple access patterns.
- `doc_values` enabled for fields needing sorting/aggregations/scripts when supported by the field type.
- `index` enabled when queries need the inverted index.
- disable `index` or `doc_values` only after proving the use case does not require that structure.

Finally, create a test index, index representative data, run real queries, and measure. Do not optimize merely by reading mappings or looking at a single query.

## 22. Quick reference table

| Concept | Used for |
|---|---|
| Inverted index | Finding terms and matching documents |
| Doc values | Sorting, aggregations, and field access in scripts |
| _source | Storing JSON for fetch, update, and reindex |
| text | Full-text search via analyzers |
| keyword | Exact filters, sorting, and terms aggregations |
| Multi-field | Having both text and keyword representations on one field |
| fielddata | Supporting certain operations on text, can consume heap |
| index | Enabling/disabling the inverted index for a field |
| doc_values | Enabling/disabling column-oriented field values |
| ignore_above | Skipping long values from keyword indexing/doc values |
| normalizer | Normalizing keyword values without tokenizing |
| dynamic templates | Applying mapping rules to new fields |
| index: false, doc_values: true | Can fit sorting/aggregations without needing search |
| index: true, doc_values: false | Search without doc values for sorting/aggregations |
| Reindex | Moving data to an index with a new mapping |

Mappings and doc values should be chosen based on each field's query patterns. The inverted index serves search, doc values serve columnar access for sorting/aggregations and scripts, and `_source` preserves JSON for fetching or reindexing. Use `text` for full-text, `keyword` for exact filters and aggregations, and numeric/date for ranges and sorting; create multi-fields when one value requires multiple access patterns. Keep `doc_values` for fields that need sorting/aggregations, and only disable `index` or `doc_values` after verifying the query contract does not need them. Because many mapping parameters cannot be changed on existing fields and new multi-fields do not auto-populate old documents, version indexes and reindex when structural changes are needed.
