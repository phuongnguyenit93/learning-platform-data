# Null Values, Missing Fields, Empty Strings, and `null_value`

When storing JSON documents in Elasticsearch, a property can exist in several distinct states: absent from the document, present with a `null` value, holding an empty string `""`, or holding a concrete value. These states are easily treated as equivalent in Java code, yet they carry different meanings during storage, indexing, and querying.

Elasticsearch also provides the `null_value` mapping parameter to substitute an explicit `null` value with a representative value at index time. This mechanism lets you query documents where a field was sent as `null`, without turning `null_value` into a default value in `_source` and without handling missing fields automatically.

For example, consider four documents:

```json
{ "id": "1", "nickname": "An" }
{ "id": "2", "nickname": null }
{ "id": "3", "nickname": "" }
{ "id": "4" }
```

Meanings:

- Document `1`: `nickname` has the string value `An`.
- Document `2`: the field is present in JSON, but its value is `null`.
- Document `3`: the field is present and its value is an empty string.
- Document `4`: the `nickname` field is absent.

These differences affect `exists` queries, `term` queries, aggregations, sorting, validation in Spring, and how the application serializes entities into JSON.

## 1. Distinguishing the Four Data States

| State | JSON | Meaning |
|---|---|---|
| Has value | `"nickname": "An"` | Field is present and has a concrete value. |
| Null value | `"nickname": null` | Field is present in JSON but has no value. |
| Empty string | `"nickname": ""` | Field is present with a zero-length string. |
| Missing field | No `nickname` key | Document does not provide that field. |

These are JSON-level states. At index time, Elasticsearch has its own rules to decide which fields produce searchable values. Not every state present in `_source` generates a value in the inverted index or doc values.

### Null Fields and Missing Fields

With standard mappings, a `null` value is not indexed as a searchable value. A missing field also has no value to index. Consequently, an `exists` query generally treats both cases as non-existent.

However, if `_source` is enabled and preserves input data, reading `_source` can still distinguish:

```json
{ "nickname": null }
```

from:

```json
{}
```

The ability to distinguish them in `_source` depends on the actual document sent and the `_source` storage configuration. A custom converter or serializer on the application side may strip null properties before sending the request, leaving Elasticsearch with a document that lacks the field entirely.

### Empty Strings Differ from Null

The string `""` is a string value, not JSON null. For a `keyword` field, an empty string can be indexed as an exact value and matched using a `term` query.

For a `text` field, an empty string may produce no text tokens after analysis, yet the field can still be considered populated for `exists` depending on Elasticsearch semantics. If business logic must distinguish empty strings, verify the actual field type and analyzer.

Whitespace-only strings like `"   "` are also not automatically equivalent to `null`. The application should trim/normalize and validate data according to business rules before indexing if whitespace carries no meaning.

## 2. How Does the `exists` Query View Null, Missing, and Empty Strings?

The `exists` query finds documents that have an indexed value for a field. It is not a check for whether a key appears in JSON `_source`.

With a standard mapping that does not declare `null_value`, the common behavior is:

| Input value | `exists` query |
|---|---|
| `"An"` | Matches |
| `null` | Does not match |
| `""` | Matches |
| Missing field | Does not match |
| `[]` | Does not match |
| `[null]` | Does not match unless `null_value` applies |
| `[null, "An"]` | Matches because it contains value `An` |

Example query finding documents with a nickname:

```json
GET /customers/_search
{
  "query": {
    "exists": {
      "field": "nickname"
    }
  }
}
```

Finding documents with no indexed nickname value:

```json
GET /customers/_search
{
  "query": {
    "bool": {
      "must_not": [
        {
          "exists": {
            "field": "nickname"
          }
        }
      ]
    }
  }
}
```

The results of the second query can include both documents with `nickname: null` and documents missing `nickname`. If you must separate those two cases, inspect `_source` or store a dedicated status field; `exists` cannot tell them apart when neither creates an indexed value.

### Why Is `exists` Not a JSON Key Check?

A field can appear in `_source` yet not be searchable, for example:

- The value is `null` without `null_value`.
- The value is an empty array `[]`.
- The field has `index: false` and no doc values.
- The value is not indexed due to mapping configuration or data processing.

Conversely, an empty string in an indexed field can count as having a value. Therefore, if the business question is "Does the JSON contain this key?", `exists` does not necessarily answer that question accurately.

## 3. How Does `null_value` Work?

The `null_value` mapping parameter allows replacing an explicit JSON `null` value with a representative value when Elasticsearch indexes the field. The original value in `_source` is not replaced.

Mapping example:

```json
PUT /customers
{
  "mappings": {
    "properties": {
      "nickname": {
        "type": "keyword",
        "null_value": "__NULL__"
      },
      "age": {
        "type": "integer",
        "null_value": -1
      }
    }
  }
}
```

Index a document:

```json
POST /customers/_doc/1
{
  "nickname": null,
  "age": null
}
```

At index time, Elasticsearch indexes `__NULL__` for `nickname` and `-1` for `age`. You can query the document using the sentinel value:

```json
GET /customers/_search
{
  "query": {
    "term": {
      "nickname": "__NULL__"
    }
  }
}
```

And an `exists` query on `nickname` can match this document because `null_value` supplied a value to index.

### `null_value` Does Not Modify `_source`

After indexing the document above, fetch the document back:

```http
GET /customers/_doc/1
```

The `_source` section still shows the original input values:

```json
{
  "nickname": null,
  "age": null
}
```

`null_value` only changes how Elasticsearch indexes null values; it does not overwrite original data in `_source` and does not turn null into a default value on Java objects.

### `null_value` Applies Only to Explicit Nulls

Distinguish the following cases:

| Input | Is `null_value` used? |
|---|---|
| `"nickname": null` | Yes, if the field type and substitute value are valid. |
| Missing `nickname` key | No. |
| `"nickname": ""` | No; this is an empty string. |
| `"nickname": []` | No elements to substitute. |
| `"nickname": [null, "An"]` | The null element in the array can be replaced by the sentinel per mapping, while `An` remains another value. |

Do not use `null_value` as a default value for every document missing a field. If a field should always have a default value, the application or an ingest pipeline must proactively populate it when the field is omitted.

## 4. Choosing a Sentinel Value for `null_value`

The `null_value` is a sentinel representing null. Choose a value such that:

- It is valid for the field's mapping type.
- It cannot be confused with real business values.
- It is easy to recognize in queries, aggregations, or data processing.
- It does not distort sorting, range queries, or statistics.

Examples:

| Field type | Illustrative sentinel | Notes |
|---|---|---|
| `keyword` | `"__NULL__"` | Pick a string that cannot be a valid domain value. |
| `integer` | `-1` | Only appropriate if negative numbers are never valid values. |
| `long` | `-1` | Check domain and range queries. |
| `boolean` | `false` | Usually unsuitable if `false` has distinct business meaning. |
| `date` | A conventional date | Avoid colliding with valid dates and standardize format. |

Not every field type supports every kind of sentinel. The `null_value` must be compatible with the mapping type and Elasticsearch version constraints. For instance, an `integer` field cannot use the string `"UNKNOWN"` as its sentinel.

### Risks of Using `-1` for Numbers

Suppose `age` uses `null_value: -1`. When aggregating or sorting, `-1` is treated as a real indexed numeric value. If the application does not filter out the sentinel, statistical results can be skewed.

Aggregation example:

```json
GET /customers/_search
{
  "size": 0,
  "aggs": {
    "average_age": {
      "avg": {
        "field": "age",
        "missing": 0
      }
    }
  }
}
```

Here `missing` in the aggregation means using a fallback value for documents that have no indexed value in `age`. It does not remove or ignore the `-1` sentinel already indexed by `null_value`. If you want to exclude sentinel documents from calculations, filter them out in the query/filter aggregation or design a dedicated status field.

Do not confuse `null_value` in mappings with the `missing` parameter in aggregations. One substitutes null values at index time; the other supplies a fallback for documents lacking field values at aggregation time.

## 5. Nulls in Arrays and Nested Objects

Elasticsearch processes multi-valued fields according to the values in the array. An empty array provides no values for the field. An array containing only null may be treated as having no values unless `null_value` is configured.

Examples:

```json
{ "tags": [] }
{ "tags": [null] }
{ "tags": ["spring", "elasticsearch"] }
{ "tags": [null, "spring"] }
```

With `tags` as `keyword` and no `null_value`, the first two documents have no values for `exists` to match; the latter two have at least one string value. If the mapping defines `null_value`, explicit null elements can be substituted with the sentinel during indexing.

Example:

```json
PUT /articles
{
  "mappings": {
    "properties": {
      "tags": {
        "type": "keyword",
        "null_value": "__NULL_TAG__"
      }
    }
  }
}
```

The document `{"tags": [null, "spring"]}` can be queried by both `__NULL_TAG__` and `spring`. `_source` retains the original array structure if stored.

For nested objects, each property has its own mapping. `null_value` must be declared on the specific child field to handle, not on the enclosing object:

```json
PUT /customers
{
  "mappings": {
    "properties": {
      "address": {
        "properties": {
          "city": {
            "type": "keyword",
            "null_value": "__NO_CITY__"
          }
        }
      }
    }
  }
}
```

Document:

```json
{
  "address": {
    "city": null
  }
}
```

The field to query is `address.city`. If `address` itself is missing or `null`, there is no `address.city` value to substitute. If `address` is an object missing `city`, `city`'s `null_value` will not auto-populate a value either.

## 6. `null_value` and Dynamic Mapping

Dynamic mapping can infer a field type when Elasticsearch receives a value capable of identifying a type. A `null` value does not provide enough information to infer a field's data type.

First document example:

```json
POST /dynamic-customers/_doc/1
{
  "nickname": null
}
```

Elasticsearch cannot deduce whether `nickname` should be `keyword`, `text`, `integer`, or another type from `null` alone. If a later document sends `nickname` as a string, dynamic mapping can create the mapping based on that string value.

If `null_value` is needed, declare the mapping explicitly before indexing data:

```json
PUT /dynamic-customers
{
  "mappings": {
    "properties": {
      "nickname": {
        "type": "keyword",
        "null_value": "__NULL__"
      }
    }
  }
}
```

Do not expect dynamic mapping to auto-generate `null_value` or guess null rules based on business logic.

## 7. Mapping Nulls in Spring Data Elasticsearch

In Java, distinguish primitive types from wrapper types:

| Java type | Can represent null? | Meaning when reading missing data |
|---|---|---|
| `boolean` | No | Java's default is `false`, easily losing the "not provided" state. |
| `Boolean` | Yes | Can represent `true`, `false`, or `null`. |
| `int` | No | Default value is `0`. |
| `Integer` | Yes | Can distinguish `0` from `null`. |
| `long` | No | Default value is `0L`. |
| `Long` | Yes | Can distinguish `0L` from `null`. |
| `String` | Yes | Can be `null`, `""`, or a populated string. |

For fields that may be missing or null, wrapper types are generally better than primitives because they preserve the unknown/unprovided state.

Example entity:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "customers", createIndex = false)
public class CustomerDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword, nullValue = "__NULL__")
    private String nickname;

    @Field(type = FieldType.Integer, nullValue = "-1")
    private Integer age;

    private Boolean active;

    // constructors, getters, setters
}
```

In Spring Data Elasticsearch versions that support the `nullValue` attribute on `@Field`, the annotation can describe the field's sentinel. Check syntax and value types against your exact library version; the actual JSON mapping on Elasticsearch remains the final source of truth.

If your version or mapping type does not support declaring it via annotation as desired, manage mappings via a settings/mapping resource or `IndexOperations` when creating the index. Do not assume `@Field` automatically alters an existing index's mapping.

### Are Java Nulls Sent as JSON Nulls?

Do not assume Elasticsearch received a JSON `null` solely by looking at Java property values. The outcome depends on your application's converters and serialization configuration. Spring Data Elasticsearch uses a mapping converter to convert entities to documents; an application might also have custom converters or custom request construction.

Example entity:

```java
CustomerDocument customer = new CustomerDocument();
customer.setId("C-100");
customer.setNickname(null);
customer.setAge(null);
```

Before relying on `null_value`, verify the actual serialized payload or read `_source` back after saving. If null fields are stripped before sending, Elasticsearch receives a missing field and `null_value` is never triggered.

### Validation at the Application Layer

Mappings are not a tool for enforcing that a field appears in every document. If business rules require `nickname` to have content, validate at the application layer using Bean Validation or domain validation:

```java
public class CustomerRequest {

    @NotBlank
    private String nickname;

    @NotNull
    private Boolean active;
}
```

`@NotNull` only requires the value to be non-null; an empty string still passes that constraint. `@NotBlank` requires a non-null string with at least one non-whitespace character. Choose constraints matching business rules; never use `null_value` as a substitute for validation.

## 8. Queries to Distinguish Null, Missing, and Empty Strings

### Finding Documents with a Field Value

```json
GET /customers/_search
{
  "query": {
    "exists": {
      "field": "nickname"
    }
  }
}
```

### Finding Documents with No Indexed Value

```json
GET /customers/_search
{
  "query": {
    "bool": {
      "must_not": [
        {
          "exists": {
            "field": "nickname"
          }
        }
      ]
    }
  }
}
```

Without `null_value`, this query typically matches both explicit nulls and missing fields.

### Finding Documents with an Empty String

For a `keyword` field:

```json
GET /customers/_search
{
  "query": {
    "term": {
      "nickname": ""
    }
  }
}
```

### Finding Documents with Explicit Null Replaced by a Sentinel

```json
GET /customers/_search
{
  "query": {
    "term": {
      "nickname": "__NULL__"
    }
  }
}
```

This query matches documents whose explicit null was indexed via `null_value`. It does not match missing fields.

### Finding Missing-Field Documents, Excluding Sentinel-Replaced Nulls

When a mapping defines `null_value`, explicit-null documents receive the sentinel value and match `exists`. Thus, a `must_not exists` query returns only documents lacking any indexed value, such as missing fields or empty arrays:

```json
GET /customers/_search
{
  "query": {
    "bool": {
      "must_not": [
        {
          "exists": {
            "field": "nickname"
          }
        }
      ]
    }
  }
}
```

If you need to separate explicit null from missing in results, inspect `_source` for key presence or store an additional status field like `nickname_provided`.

## 9. Distinguishing `null_value`, Default Values, and Aggregation `missing`

Three mechanisms are often confused:

| Mechanism | When it runs | Effect |
|---|---|---|
| `null_value` mapping | When Elasticsearch indexes an explicit null value. | Replaces null with a sentinel in the index; `_source` still keeps null. |
| Application-level default value | Before sending the document. | Writes a real value into the document if the application chooses to supply a default. |
| `missing` in aggregation | When running an aggregation over documents lacking an indexed value for the field. | Uses a substitute value solely within that aggregation computation. |

Example setting an application default:

```java
if (customer.getActive() == null) {
    customer.setActive(true);
}
```

In this case, the document is written with `active: true`; that becomes the document's real value. `null_value`, by contrast, only creates a sentinel for indexing while `_source` retains null.

Aggregation `missing` affects only the calculation:

```json
GET /customers/_search
{
  "size": 0,
  "aggs": {
    "age_distribution": {
      "terms": {
        "field": "age",
        "missing": -1
      }
    }
  }
}
```

Documents lacking an `age` value are grouped into the `-1` bucket during this aggregation. This does not update `_source`, change mappings, or cause documents to appear to have an age value in other queries.

## 10. Changing `null_value` on an Existing Index

The mapping created for a live index is the data contract of that index. If a field was already declared without `null_value`, adding a sentinel later does not automatically reindex old documents.

When changing null handling for an existing field, check mapping update capabilities for your Elasticsearch version. For mapping parameter changes that cannot be updated in place or must apply consistently to historical data, the safe workflow is usually:

1. Create a new index with the mapping containing `null_value`.
2. Reindex documents from the old index into the new index.
3. Verify `_source`, mappings, and query results across null, missing, and empty string cases.
4. Synchronize changes arriving during reindexing.
5. Switch the alias to the new index.
6. Retain the old index for a rollback window.

Reindexing can only apply the sentinel to documents where `_source` still retains explicit `null`. If old data had nulls stripped by a serializer into missing fields, Elasticsearch cannot infer from the old index that the key had ever been sent as null. In that case, restore the information from the source system or apply migration rules.

## 11. Common Mistakes

| Symptom | Possible cause | Resolution |
|---|---|---|
| `exists` misses documents with `field: null` | Null creates no indexed value without `null_value`. | Inspect `_source` to distinguish, or configure a sentinel for new data/reindex. |
| `exists` matches fields with `""` | An empty string is a non-null value. | Validate/normalize empty strings in the application if business rules reject them. |
| `null_value` is not applied | Serializer stripped null fields, or the field was actually omitted. | Inspect payload and `_source`; ensure explicit JSON `null` is sent. |
| Documents missing the field still lack the sentinel | `null_value` does not apply to missing fields. | Populate defaults in the application or an ingest pipeline if needed. |
| Aggregation shows an unexpected `-1` bucket | The `null_value` sentinel is treated as a real indexed numeric value. | Filter out sentinels or use a separate status field; consider a different sentinel. |
| Dynamic mapping creates no field after a first null document | Null carries insufficient type information to infer a type. | Declare explicit mappings before indexing. |
| Java primitives return `false`/`0` despite missing data | Primitives have default values and cannot represent null. | Use wrapper types `Boolean`, `Integer`, `Long` when an unknown state is needed. |
| Changed annotations without changing the old index | Annotations do not auto-migrate existing mappings. | Create a new index/reindex or run an appropriate mapping migration. |

## 12. Data Design Rules

- Use `null` when a field is known to have no value yet or is not applicable, per business rules.
- Omit the field when representing an unprovided state or an attribute that does not belong to the document.
- Use an empty string only when it is genuinely meaningful; otherwise, normalize to null or drop the field at the application layer.
- Choose wrapper types in Java when needing to distinguish `false` from unknown, or `0` from unprovided.
- Use `null_value` when explicit nulls must be queried as a sentinel value.
- Never choose a sentinel that can collide with valid data.
- Never treat `null_value` as a default value, validation rule, or required-field constraint.
- Inspect converters/serializers to verify whether nulls are emitted as JSON `null` or omitted.
- Store a dedicated status field if queries must strictly separate "null was sent" from "field was not sent".
- Inspect actual mappings and `_source` rather than relying solely on Java annotations.

## 13. Key Takeaways

- Missing fields, explicit `null`, and empty strings are three distinct JSON states.
- `exists` checks for indexed values, not simply key presence in `_source`.
- Without `null_value`, both explicit nulls and missing fields typically fail `exists`.
- Empty strings can count as having a value; for `keyword`, they can be matched with a `term` query.
- `null_value` replaces explicit null with a sentinel during indexing; it does not alter `_source`.
- `null_value` does not populate values for missing fields or empty arrays.
- `null_value` allows the sentinel to participate in `exists`, term queries, sorting, and aggregations like any indexed value.
- Dynamic mapping cannot infer field types from null alone; declare mappings explicitly when null handling is required.
- In Java, wrapper types preserve null whereas primitives take default values.
- `null_value`, application defaults, and aggregation `missing` are three distinct mechanisms.
- When changing mappings for historical data, evaluate reindexing and whether explicit nulls remain recoverable from `_source`.

Understanding the differences between null, missing fields, and empty strings helps Spring Data Elasticsearch applications avoid query bugs and data skew. Define the business meaning of each state, configure appropriate mappings, inspect actual JSON payloads, and use `null_value` intentionally as a sentinel rather than treating it as an automatic default-value mechanism.
