# True, False, Exists, IsNull, and IsNotNull

Spring Data Elasticsearch supports many keywords for deriving queries from repository method names. Within name-based queries, `True`, `False`, `Exists`, `IsNull`, and `IsNotNull` let you check boolean states or the presence of a field.

These keywords look similar but carry distinct meanings:

- `True` and `False` check boolean values.
- `Exists` checks whether a field has an indexed value.
- `IsNull` finds documents where a field has no indexed value.
- `IsNotNull` finds documents where a field has an indexed value.

To use them correctly, you need to understand how Spring Data parses method names, how Elasticsearch handles null values, and the difference between a field existing and a document existing.

## 1. Preparing the entity and repository

Suppose an application manages products. A product can be active or paused; in addition, some attributes such as description or internal notes might not be provided yet.

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Boolean)
    private Boolean available;

    @Field(type = FieldType.Keyword)
    private String name;

    @Field(type = FieldType.Text)
    private String description;

    @Field(type = FieldType.Keyword)
    private String internalNote;

    // Constructors, getters and setters
}
~~~

Choose `Boolean` instead of `boolean` when an attribute may be unset. The wrapper type `Boolean` has three states in Java:

- `true`: confirmed active.
- `false`: confirmed inactive.
- `null`: no value yet or unset.

With primitive `boolean`, the property only holds `true` or `false`; Java cannot represent a null state.

Repository:

~~~java
import java.util.List;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    List<ProductDocument> findByAvailableTrue();

    List<ProductDocument> findByAvailableFalse();

    List<ProductDocument> findByInternalNoteExists();

    List<ProductDocument> findByInternalNoteIsNull();

    List<ProductDocument> findByInternalNoteIsNotNull();
}
~~~

Spring Data parses the method name after `By` into conditions. These methods take no parameters because the condition is already encoded directly in the method name.

## 2. True and IsTrue: finding boolean true values

`True` and `IsTrue` are two equivalent forms in query derivation.

Examples:

~~~java
List<ProductDocument> findByAvailableTrue();

List<ProductDocument> findByAvailableIsTrue();
~~~

Both methods find documents whose `available` field holds the boolean value `true`.

Similarly, with direct Query DSL:

~~~json
{
  "query": {
    "term": {
      "available": true
    }
  }
}
~~~

One note on how Spring Data Elasticsearch generates queries: the current query method documentation illustrates `findByAvailableTrue` using `query_string` with value `"true"` on field `available`. When writing Query DSL manually, you can use `term` with a boolean value as shown above.

### When to use True?

Use `True` when you want documents confirmed to be enabled, valid, or allowed:

~~~java
List<ProductDocument> findByAvailableTrue();
~~~

Business examples:

- Products currently on sale.
- Active accounts.
- Enabled features.
- Records confirmed as valid.

Do not interpret `True` as "the field exists". A boolean field can exist while holding `false`, in which case it does not satisfy `True`.

## 3. False and IsFalse: finding boolean false values

`False` and `IsFalse` are also equivalent forms:

~~~java
List<ProductDocument> findByAvailableFalse();

List<ProductDocument> findByAvailableIsFalse();
~~~

Corresponding Query DSL:

~~~json
{
  "query": {
    "term": {
      "available": false
    }
  }
}
~~~

This method finds documents with boolean value `false`. It does not find documents missing the `available` field or having a null value.

### Distinguishing false and null

Suppose there are three documents:

~~~json
[
  {
    "_id": "p1",
    "available": true
  },
  {
    "_id": "p2",
    "available": false
  },
  {
    "_id": "p3",
    "name": "Keyboard"
  }
]
~~~

Results:

| Document | available value | `findByAvailableTrue()` | `findByAvailableFalse()` |
|---|---|---|---|
| p1 | `true` | Yes | No |
| p2 | `false` | No | Yes |
| p3 | Field absent | No | No |

`false` is a concrete boolean value. A field without a value is not automatically treated as `false`.

If business logic needs to include records whose status has not been set yet, use an appropriate null/exists check.

## 4. Exists: checking whether a field has an indexed value

`Exists` is a predicate keyword for checking the existence of a value in a field.

Example:

~~~java
List<ProductDocument> findByInternalNoteExists();
~~~

This method finds documents where the `internalNote` field contains a value indexed by Elasticsearch.

Corresponding Query DSL:

~~~json
{
  "query": {
    "exists": {
      "field": "internalNote"
    }
  }
}
~~~

`Exists` does not mean the document itself exists. It checks whether the specified field inside the document has an indexed value.

For example, if a product has `name` but lacks `internalNote`, the document exists in the index, yet it will not satisfy `findByInternalNoteExists()`.

### Exists does not merely check keys in _source

Elasticsearch evaluates exists queries against searchable values in the index. As a result, the outcome can differ from merely checking whether JSON contains a property name.

Typically:

- A field with string `""` (empty string): considered to have a value.
- A field with value `null`: has no indexed value by default.
- A field with empty array `[]`: considered to have no value.
- A field absent from the document: has no indexed value.

Settings such as `null_value`, `ignore_above`, or `ignore_malformed` can affect exists results. Check the actual mapping to explain outcomes accurately.

## 5. IsNull and Null: finding fields without a value

`IsNull` and `Null` are equivalent forms:

~~~java
List<ProductDocument> findByInternalNoteIsNull();

List<ProductDocument> findByInternalNoteNull();
~~~

In Elasticsearch, Spring Data generates a negated exists query:

~~~json
{
  "query": {
    "bool": {
      "must_not": [
        {
          "exists": {
            "field": "internalNote"
          }
        }
      ]
    }
  }
}
~~~

This condition returns documents where the `internalNote` field has no indexed value.

Key point: `IsNull` generally covers both cases:

1. Documents containing the property `internalNote: null`.
2. Documents completely lacking the property `internalNote`.

In addition, a field present in `_source` that is not indexed due to mapping or value-ignoring rules can also be treated as absent by an exists query.

Therefore, do not interpret `IsNull` as an exact check for "JSON has this key with value null".

## 6. IsNotNull and NotNull: finding fields with a value

`IsNotNull` and `NotNull` are equivalent forms:

~~~java
List<ProductDocument> findByInternalNoteIsNotNull();

List<ProductDocument> findByInternalNoteNotNull();
~~~

Spring Data Elasticsearch translates this condition into an exists query:

~~~json
{
  "query": {
    "exists": {
      "field": "internalNote"
    }
  }
}
~~~

`IsNotNull` finds documents that have an indexed value in the `internalNote` field.

Examples:

| Data in document | Exists / IsNotNull | IsNull |
|---|---|---|
| `"internalNote": "Checked"` | Yes | No |
| `"internalNote": ""` | Yes | No |
| `"internalNote": null` | No (default) | Yes |
| No `internalNote` | No | Yes |
| `"internalNote": []` | No | Yes |

`IsNotNull` does not mean the string is non-empty. An empty string is still an indexed value in typical setups.

If you want to verify that a string has actual content, use an appropriate condition for the field type, such as combining exists with a wildcard or storing an additional normalized state.

## 7. Comparing the five keywords

| Keyword | Meaning | Elasticsearch query typically generated |
|---|---|---|
| `True` / `IsTrue` | Boolean value true | `query_string` with `"true"` in current query method docs |
| `False` / `IsFalse` | Boolean value false | `query_string` with `"false"` in current query method docs |
| `Exists` | Field has an indexed value | `exists` |
| `IsNull` / `Null` | Field has no indexed value | `must_not exists` |
| `IsNotNull` / `NotNull` | Field has an indexed value | `exists` |

The keyword names belong to Spring Data's query derivation syntax. Do not confuse `Exists` with `existsBy...` at the start of a repository method name; the two serve different roles.

## 8. Distinguishing the Exists predicate from the existsBy projection

This is one of the easiest points to confuse when naming repository methods.

### Exists predicate: findByFieldExists

~~~java
List<ProductDocument> findByInternalNoteExists();
~~~

This method returns documents where the `internalNote` field exists in the sense of an Elasticsearch exists query.

It corresponds to the condition:

~~~json
{
  "query": {
    "exists": {
      "field": "internalNote"
    }
  }
}
~~~

### Exists projection: existsBy...

~~~java
boolean existsBySku(String sku);
~~~

This is a repository method with the subject keyword `exists...By`. It returns a `boolean` indicating whether any document satisfies `sku = passed value`.

It is not a check on whether the `sku` field exists in individual documents.

Example:

~~~java
boolean existsBySku("KB-1001");
~~~

Means checking whether any product has SKU `KB-1001`.

Whereas:

~~~java
List<ProductDocument> findBySkuExists();
~~~

Means fetching products whose `sku` field has an indexed value.

### ExistsById is a separate CRUD method

`existsById(id)` is a predefined method in `CrudRepository`. It checks whether a document with the given ID exists:

~~~java
boolean exists = productRepository.existsById("p1001");
~~~

This checks document existence by identifier, not the `Exists` query predicate on an arbitrary field.

## 9. Combining conditions

Predicates can be combined with `And`, `Or`, and other conditions.

Example fetching active products that have a note:

~~~java
List<ProductDocument> findByAvailableTrueAndInternalNoteExists();
~~~

Example fetching disabled products or products without a status yet:

~~~java
List<ProductDocument> findByAvailableFalseOrAvailableIsNull();
~~~

Example finding active products that do not have a note yet:

~~~java
List<ProductDocument> findByAvailableTrueAndInternalNoteIsNull();
~~~

Spring Data translates `And` into conditions that must all hold; `Or` creates alternative condition branches.

If method names become long or hard to read, consider using `@Query`, `CriteriaQuery`, or `NativeQuery` to express the query more clearly.

## 10. Controlling null_value in Elasticsearch mappings

By default, Elasticsearch does not index JSON `null` values. If you need to treat explicit nulls as queryable values, several field types support the `null_value` mapping parameter.

Example on a keyword field:

~~~json
{
  "mappings": {
    "properties": {
      "internalNote": {
        "type": "keyword",
        "null_value": "__NULL__"
      }
    }
  }
}
~~~

With this mapping, an explicit null value can be replaced by `"__NULL__"` at index time. That field will then be considered present in exists queries.

Example document:

~~~json
{
  "internalNote": null
}
~~~

You can search for the replacement value using a term query:

~~~json
{
  "query": {
    "term": {
      "internalNote": "__NULL__"
    }
  }
}
~~~

Notes:

- `null_value` substitutes the null value at index time; it does not alter the original content in `_source`.
- Ignored fields or documents omitting the field still do not receive the sentinel automatically.
- When `null_value` is used, `IsNotNull` can match explicit null values because Elasticsearch indexed the sentinel for the field.
- Choose a sentinel that cannot be confused with normal business data.

If business logic must distinguish "field not sent", "sent null", and "sent empty string", you may need an extra status field or a more explicit data representation in the document.

## 11. Notes on text, keyword, and ignored fields

Exists queries check whether a searchable value exists in the index. They do not simply inspect the source JSON.

A few cases to keep in mind:

### Text fields

Text fields are processed by an analyzer. An empty string is still considered present by Elasticsearch under standard exists semantics, even though the analyzer may not produce searchable word tokens.

### Keyword fields and ignore_above

Example mapping:

~~~json
{
  "mappings": {
    "properties": {
      "internalNote": {
        "type": "keyword",
        "ignore_above": 20
      }
    }
  }
}
~~~

If a string exceeds the `ignore_above` limit, the value may still remain in `_source` while not being indexed for that keyword field. In that case, an exists query may fail to match.

### ignore_malformed

For typed fields, invalid values may be ignored if `ignore_malformed` permits it. Ignored values produce no indexed value for that field and can cause exists queries not to match.

### index and doc_values

If a field is neither indexed nor has doc values enabled, Elasticsearch may have no data to evaluate an exists query for that field. Check mappings and field settings before relying on `Exists` or `IsNull`.

## 12. Complete repository example

A repository can declare methods such as:

~~~java
import java.util.List;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    // Boolean values
    List<ProductDocument> findByAvailableTrue();

    List<ProductDocument> findByAvailableFalse();

    // Field has or lacks an indexed value
    List<ProductDocument> findByInternalNoteExists();

    List<ProductDocument> findByInternalNoteIsNull();

    List<ProductDocument> findByInternalNoteIsNotNull();

    // Combined conditions
    List<ProductDocument> findByAvailableTrueAndInternalNoteExists();

    List<ProductDocument> findByAvailableFalseOrInternalNoteIsNull();

    // Check whether any document matches a condition
    boolean existsBySku(String sku);

    // CRUD repository method checking by document ID
    boolean existsById(String id);
}
~~~

These methods illustrate three groups of purposes:

1. Boolean predicates to filter by `true`/`false`.
2. Field presence predicates to filter by `exists`/`null`.
3. Projection `existsBy...` to return a boolean result for a search condition.

## 13. Common errors

### Treating false as null

`findByAvailableFalse()` only finds `false` values. Missing or null fields are not treated as false.

### Treating IsNull as checking for a JSON key's presence

`findByInternalNoteIsNull()` relies on a negated exists query. It can match fields omitted from the document, explicit nulls, and any cases lacking an indexed value.

### Treating Exists as document existence

`findByInternalNoteExists()` checks the `internalNote` field. To check document existence by ID, use `existsById(id)`.

### Confusing findByNameExists with existsByName

`findByNameExists()` returns documents where the name field exists. `existsByName("Keyboard")` returns a boolean indicating whether any document matches name equal to the passed value.

### Assuming an empty string is null

The string `""` is a value; exists queries normally treat that field as present. If empty strings must be excluded, add a dedicated condition.

### Not checking null_value mapping

If a field uses `null_value`, explicit nulls are indexed as the sentinel. Consequently, `Exists`, `IsNull`, and `IsNotNull` results can differ from default mapping behavior.

### Using method keywords unsupported by your version

Spring Data Commons lists common keywords, but individual datastore modules can vary in support. Cross-check query method documentation for your exact Spring Data Elasticsearch version.

## 14. Keyword selection workflow

When writing a repository method, clarify your goal:

1. Want to find boolean true values? Use `findByAvailableTrue()`.
2. Want to find boolean false values? Use `findByAvailableFalse()`.
3. Want to find fields with an indexed value? Use `findByFieldExists()`.
4. Want to find fields without an indexed value? Use `findByFieldIsNull()`.
5. Want to find fields with an indexed value? Use `findByFieldIsNotNull()`.
6. Want to know whether any document matches a condition? Use `existsBy...` returning boolean.
7. Want to check document existence by ID? Use `existsById(id)`.
8. Need to distinguish explicit null from missing fields? Design a dedicated mapping or status field rather than relying solely on `IsNull`.

## Conclusion

`True` and `False` filter for concrete boolean values. `Exists` checks whether a field has an indexed value; `IsNull` and `IsNotNull` are the negated and positive forms of the exists query, respectively. In Elasticsearch, explicit nulls and missing fields are normally both treated as having no indexed value unless a setting such as `null_value` alters that behavior. Distinguish the predicate `findByFieldExists()`, the projection `existsByField(...)`, and the CRUD method `existsById(...)` to pick the right API.

## References

- [Spring Data Elasticsearch — Query methods](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories/elasticsearch-repository-queries.html)
- [Spring Data Elasticsearch — Repository query keywords](https://docs.spring.io/spring-data/elasticsearch/reference/repositories/query-keywords-reference.html)
- [Elasticsearch — Exists query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-exists-query.html)
- [Elasticsearch — null_value mapping parameter](https://www.elastic.co/guide/en/elasticsearch/reference/current/null-value.html)
