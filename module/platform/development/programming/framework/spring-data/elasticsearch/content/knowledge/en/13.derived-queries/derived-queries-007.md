# Distinguishing Missing Fields, Empty Strings, and the `IsEmpty` Condition

When building name-based queries in Spring Data Elasticsearch, it is essential to distinguish three frequently confused concepts: a field absent from a document, a field holding an empty string `""`, and the `IsEmpty` condition in a Repository method name. They do not inherently mean the same thing.

Elasticsearch stores JSON documents and indexes values according to mappings. A field can exist in `_source` without having a searchable value; conversely, an empty string is still a valid JSON value. Spring Data Repositories also have their own method-name parsing rules, so you should not assume the word `Empty` in a method name always translates to querying for an empty string or a missing field.

Example with four documents:

```json
{ "id": "1", "name": "Spring" }
{ "id": "2", "name": "" }
{ "id": "3", "name": null }
{ "id": "4" }
```

Meaning at the JSON layer:

- Document `1`: `name` has content `Spring`.
- Document `2`: `name` is present and holds an empty string.
- Document `3`: `name` is present with value `null`.
- Document `4`: key `name` is absent from the document.

With standard mappings, an empty string is a non-null value; explicit `null` and a missing field typically produce no indexed value. Thus, an `exists` query can match documents `1` and `2`, while missing `3` and `4`. To distinguish explicit null from a missing field in queries, you need to store additional metadata or use an appropriate mapping mechanism; `exists` alone is insufficient.

## 1. Missing fields and empty strings in Elasticsearch

### Missing fields

A missing field means the key does not appear in JSON `_source`:

```json
{
  "id": "C-100",
  "email": "an@example.com"
}
```

This document has no `name` key. Under standard mappings, Elasticsearch has no `name` value to index. An `exists` query on `name` will not match this document.

### Empty strings

An empty string is a string value of length 0:

```json
{
  "id": "C-101",
  "name": ""
}
```

On a `keyword` field, an empty string can be indexed as an exact value and matched with a `term` query. It is also treated as a present value by an `exists` query.

On a `text` field, an analyzer may produce zero tokens from an empty string. Therefore, full-text queries on `text` are not a reliable way to check for empty strings. If exact string-value filtering is needed, use a `keyword` field or a `keyword` multi-field.

### Explicit null

A document may contain:

```json
{
  "id": "C-102",
  "name": null
}
```

By default, `null` is not indexed as a normal value. For `exists` queries, null usually behaves identically to a missing field. However, if `_source` is stored, reading the document can distinguish JSON `null` from an absent key.

### Comparison table

| Data in JSON | Key present in `_source`? | Indexed value under standard mapping? | `exists` typically matches? |
|---|---:|---:|---:|
| `"name": "Spring"` | Yes | Yes | Yes |
| `"name": ""` | Yes | Yes on keyword fields; text fields may produce no searchable tokens | Yes |
| `"name": null` | Yes | No | No |
| Key `name` absent | No | No | No |
| `"name": []` | Yes | No elements | No |
| `"name": [null, "Spring"]` | Yes | Has value `Spring` | Yes |

Exact outcomes still depend on mappings, `null_value`, analyzers, doc values, and how the serializer builds JSON. The table above describes common Elasticsearch behavior without special settings.

## 2. Declaring mappings to query exact names

If both full-text search and exact matching are required, you can use a multi-field:

```json
PUT /customers
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "fields": {
          "keyword": {
            "type": "keyword"
          }
        }
      }
    }
  }
}
```

Field `name` serves full-text search; subfield `name.keyword` serves exact matching, sorting, or aggregations. If you only need the name as an identifier value without full-text search, you can declare `name` directly as `keyword`.

With this mapping, documents with empty names can still be matched accurately using `name.keyword`:

```json
GET /customers/_search
{
  "query": {
    "term": {
      "name.keyword": ""
    }
  }
}
```

If `name` is mapped directly as `keyword`, the query targets `name` instead of `name.keyword`.

Do not use a `match` query for exact empty-string comparison. A `match` query analyzes text through the analyzer; with empty input, the analyzer may produce zero tokens and the query will not express the equality condition the application expects.

## 3. Using `exists` to find fields with an indexed value

An `exists` query checks whether a field has an indexed value. It does not simply check whether a key appears in JSON `_source`.

Find documents that have `name`:

```json
GET /customers/_search
{
  "query": {
    "exists": {
      "field": "name"
    }
  }
}
```

Under standard mappings, results may include both non-empty names and empty strings, while excluding nulls and missing fields.

Find documents with no indexed value for `name`:

```json
GET /customers/_search
{
  "query": {
    "bool": {
      "must_not": [
        {
          "exists": {
            "field": "name"
          }
        }
      ]
    }
  }
}
```

This query typically matches documents with `name: null` and documents missing `name`. If the mapping configures `null_value`, explicit nulls may be indexed using a sentinel and `exists` will then match explicit-null documents.

### Why `exists` is insufficient to distinguish missing fields from null

At the index layer, both null and missing may produce no searchable value. Elasticsearch cannot infer from the inverted index whether a key was sent as `null` or omitted altogether from the JSON.

If business logic must distinguish the two states, you can:

- Read `_source` and check whether the key is present.
- Store an extra state field, such as `name_provided` or `name_state`.
- Use `null_value` if explicit nulls should have a dedicated sentinel in the index.
- Normalize data in the application or an ingest pipeline before indexing.

## 4. Distinguishing `IsEmpty` in Repository method names

Spring Data parses repository method names into condition parts based on property names and keywords. Keywords such as `IsNull`, `IsNotNull`, `Exists`, `IsTrue`, `IsFalse`, `IsEmpty`, and `IsNotEmpty` each have specific meanings in query derivation.

Key point to remember: `IsEmpty` is typically used to express emptiness of a collection/array in Spring Data abstractions that support it. Do not assume `findByNameIsEmpty()` will always be translated into `name = ""`, or into `must_not exists`, across all Spring Data Elasticsearch versions.

Examples of method names that are easy to confuse:

```java
public interface CustomerRepository
        extends ElasticsearchRepository<CustomerDocument, String> {

    List<CustomerDocument> findByName(String name);

    List<CustomerDocument> findByNameIsNull();

    List<CustomerDocument> findByNameIsNotNull();

    List<CustomerDocument> findByNameIsEmpty();

    List<CustomerDocument> findByNameIsNotEmpty();
}
```

These methods only illustrate method-name syntax. Whether a keyword is supported for a specific property type and how it is converted to Query DSL depend on the Spring Data Elasticsearch version and query creator in use. In particular, do not treat `IsEmpty` as a portable way to search for empty strings in `String` fields.

### Querying for empty strings explicitly

If the goal is finding names equal to the empty string, use a `term` query on a `keyword` field:

```java
@Query("{\"term\": {\"name.keyword\": \"\"}}")
List<CustomerDocument> findCustomersWithEmptyName();
```

Field names inside raw Query DSL must match the actual names in the Elasticsearch mapping. If the field is declared directly as `keyword`, use `name` instead of `name.keyword`.

Another option is using `ElasticsearchOperations` or the Java API Client to build an explicit `TermQuery`. This avoids ambiguity between the `IsEmpty` keyword and empty string values.

### Querying for fields with no value

If the goal is finding documents with no indexed value, use `must_not exists`:

```java
@Query("{\"bool\": {\"must_not\": [{\"exists\": {\"field\": \"name\"}}]}}")
List<CustomerDocument> findCustomersWithoutIndexedName();
```

Method names should describe the actual meaning, such as `findCustomersWithoutIndexedName`, rather than using `IsEmpty` when the real condition is missing/null at the index layer.

## 5. `IsNull`, `IsNotNull`, `IsEmpty`, and empty strings

The following concepts should not be treated as interchangeable:

| Desired condition | Common Elasticsearch query | Notes |
|---|---|---|
| Field has an indexed value | `exists` | Empty strings may still count as having a value. |
| Field has no indexed value | `must_not exists` | May include both explicit null and missing fields. |
| Name equals empty string | `term` on `keyword` with `""` | Equality against a concrete value. |
| Name equals a specific string | `term` on `keyword` or suitable query | Pick field and query per mapping. |
| Java property is null | Depends on converter and query derivation | Does not guarantee payload had explicit JSON null. |
| Collection has no elements | Appropriate keyword/query for collection and mapping | `IsEmpty` typically relates to collections; check version support. |

With `null_value`, explicit null can be indexed as a sentinel. Then `exists` can match explicit null while missing fields still do not match. `IsNull` in query derivation is not automatically equivalent to matching that sentinel; verify the generated query and actual mapping.

## 6. Integration in Spring Data Elasticsearch

Sample entity:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "customers", createIndex = false)
public class CustomerDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(name = "name_exact", type = FieldType.Keyword)
    private String nameExact;

    // getters, setters, constructors
}
```

In this example, the application can use `name` for full-text search and `nameExact` for exact equality. If you want to use a `name.keyword` multi-field, declare the corresponding multi-field mapping on the index; avoid declaring a separate Java property for a subfield unless separate modeling is required.

Repository:

```java
public interface CustomerRepository
        extends ElasticsearchRepository<CustomerDocument, String> {

    List<CustomerDocument> findByName(String name);

    List<CustomerDocument> findByNameExact(String name);
}
```

`findByNameExact("")` expresses an equality condition on the `nameExact` property more clearly if the query creator in your version supports this method according to the mapping. If exact raw Query DSL is needed, use `@Query` or `ElasticsearchOperations` with a `term` query.

For query methods derived from properties, Spring Data uses Java property names to locate fields. For raw JSON in `@Query`, use the Elasticsearch field name from the mapping, such as `name_exact` or `name.keyword`.

## 7. Serialization can turn null into a missing field

A Java entity with property `name = null` does not guarantee Elasticsearch receives JSON:

```json
{
  "name": null
}
```

Converters or serializers may strip null properties before sending the request. If the field is omitted from the payload, Elasticsearch sees a missing field; `null_value` is not triggered because it only applies to explicit nulls.

Java example:

```java
CustomerDocument customer = new CustomerDocument();
customer.setId("C-200");
customer.setName(null);
```

To understand actual behavior, check:

1. The converter/serializer configuration in use.
2. The actual JSON request sent to Elasticsearch.
3. `_source` after saving.
4. The mapping of field `name`, including `null_value`, `index`, and analyzer.

If business logic distinguishes "client omitted field" from "client sent null", preserve that state explicitly. A single nullable Java property may not suffice to represent both states after request deserialization.

## 8. Modeling states explicitly in the application

In some domains, these three states have distinct meanings:

- Name has not been provided yet.
- User intentionally cleared the name or set it to null.
- User entered an empty string.

You can represent this explicitly with a dedicated state field:

```json
{
  "name": null,
  "name_state": "EXPLICIT_NULL"
}
```

Or:

```json
{
  "name": "",
  "name_state": "EMPTY"
}
```

And a document without `name` can carry `name_state: "NOT_PROVIDED"` if that state must be queried without scanning all `_source` payloads.

In Spring, you can use an enum:

```java
public enum NameState {
    PRESENT,
    EMPTY,
    EXPLICIT_NULL,
    NOT_PROVIDED
}
```

Storing an explicit state clarifies the data contract, though fields must be kept consistent on updates. Normalize state in a service or ingest pipeline rather than letting each caller set it ad hoc.

## 9. Example queries per state

Suppose `name_exact` is a `keyword` field:

### Find empty names

```json
GET /customers/_search
{
  "query": {
    "term": {
      "name_exact": ""
    }
  }
}
```

### Find names with any non-empty content

```json
GET /customers/_search
{
  "query": {
    "bool": {
      "filter": [
        { "exists": { "field": "name_exact" } }
      ],
      "must_not": [
        { "term": { "name_exact": "" } }
      ]
    }
  }
}
```

This query excludes empty strings and keeps only documents with an indexed `name_exact` value. If data contains whitespace such as `"   "`, that value still differs from an empty string; normalize in the application if whitespace-only strings should count as empty.

### Find missing or null fields without a sentinel

```json
GET /customers/_search
{
  "query": {
    "bool": {
      "must_not": [
        { "exists": { "field": "name_exact" } }
      ]
    }
  }
}
```

This query does not distinguish explicit null from missing. If `null_value` is configured, explicit null may be indexed with a sentinel and will no longer appear in these results.

### Find a specific state

If `name_state` is stored as `keyword`, you can query directly:

```json
GET /customers/_search
{
  "query": {
    "term": {
      "name_state": "EXPLICIT_NULL"
    }
  }
}
```

This is clean when null/missing states carry business meaning and are queried frequently.

## 10. Testing `IsEmpty` and actual queries

Do not infer the query sent to Elasticsearch solely from the method name. Test on your exact Spring Data Elasticsearch version and project mappings.

An integration test should create representative documents:

```json
{ "id": "1", "name": "Spring", "name_exact": "Spring" }
{ "id": "2", "name": "", "name_exact": "" }
{ "id": "3", "name": null, "name_state": "EXPLICIT_NULL" }
{ "id": "4", "name_state": "NOT_PROVIDED" }
```

Then verify:

1. `exists(name_exact)` returns documents with `Spring` and empty string.
2. `term(name_exact, "")` returns only the document with empty string.
3. `must_not exists(name_exact)` returns documents with no indexed value.
4. Raw queries in `@Query` use exact mapping field names.
5. Any `IsEmpty` query method used has semantics appropriate for the property type and library version.
6. The serializer does not silently turn explicit null into missing unintentionally.

You can inspect actual Query DSL requests via appropriate test logging or use the Elasticsearch Java API Client to construct explicit queries. Also inspect `_mapping` and `_source` to verify differences between JSON data and searchable data.

## 11. Common errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| `findByNameIsEmpty()` does not find empty strings | `IsEmpty` follows collection semantics or is not supported for String as expected by the query creator. | Use an explicit equality query on a `keyword` field; check version docs. |
| `exists` matches documents with empty names | Empty string is still a value, unlike null/missing. | Use `term` with `""` to filter empty strings separately. |
| `exists` fails to match documents with `name: null` | Null is not indexed by default. | Use `null_value`, a state field, or read `_source` if differentiation is required. |
| `must_not exists` returns both null and missing | Neither produces an indexed value. | Store separate explicit null/missing state if distinct queries are required. |
| Empty-string query on text field returns nothing | Analyzer produces no tokens for empty strings. | Use a `keyword` field or multi-field for equality. |
| `name = null` in Java but Elasticsearch treats it as missing | Converter/serializer omits null properties. | Inspect JSON payload and serialization settings. |
| Whitespace-only strings are not treated as empty | Whitespace differs from `""`. | Trim/normalize and validate before indexing. |
| Raw `@Query` fails to find field | JSON uses Java property name instead of Elasticsearch field name. | Use exact field name from mapping. |

## 12. Design rules

- Use `keyword` or a `keyword` multi-field when exact name matching is needed, including empty strings.
- Use `text` for full-text search; do not use `match` to check empty-string equality.
- Use `exists` to check for an indexed value, not as a check for a key in `_source`.
- Use `must_not exists` to find documents without an indexed value; recognize it can match both null and missing.
- Use `term` on a keyword field with `""` when searching for empty strings.
- Do not assume `IsEmpty` in a derived query means `name = ""`; verify property-type semantics and Spring Data Elasticsearch version behavior.
- Use `IsEmpty`/`IsNotEmpty` only according to data type and query derivation support, typically related to collections/arrays.
- Use `null_value` or a dedicated state field when explicit nulls must be queried.
- Check converters/serializers to ensure explicit nulls are not unintentionally dropped as missing fields.
- Normalize whitespace at the application layer if business logic treats whitespace-only strings as empty.

## 13. Key takeaways

- Missing fields, explicit nulls, and empty strings are distinct JSON states.
- An empty string is a valid value; on `keyword`, it can be matched with a `term` query.
- `exists` checks for indexed values, not simply key presence in `_source`.
- `must_not exists` normally returns both null and missing fields when `null_value` is unset.
- `IsEmpty` is a Spring Data query derivation keyword; do not assume it equals empty string or missing field.
- For `String`, use explicit equality/term queries on keyword fields to find `""`.
- For collections, confirm `IsEmpty` support for your repository/query creator and field type version.
- Raw Query DSL in `@Query` requires Elasticsearch field names; query methods normally reference Java properties.
- If explicit null and missing must be distinguished in queries, store a separate state or use an intentional sentinel.

Understanding missing fields, empty strings, and `IsEmpty` keeps name-based queries in Spring Data Elasticsearch semantically clear. Identify the target state at the JSON layer, pick suitable mappings, use explicit queries for empty strings, and inspect the actual queries generated by your running Spring Data version.
