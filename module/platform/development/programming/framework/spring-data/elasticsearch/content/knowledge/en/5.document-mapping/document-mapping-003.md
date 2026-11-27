# `@Field`, Java Field Names, and Elasticsearch Field Names

In Spring Data Elasticsearch, a property name in a Java class can differ from the field name stored in an Elasticsearch document. For example, Java uses `firstName` following camelCase conventions, while the index might store the JSON field as `first_name` following snake_case conventions.

The `@Field` annotation lets you declare the name and mapping metadata of a property. Spring Data uses this mapping metadata when converting Java objects into documents and when reading documents back into objects. As a result, Java code can keep readable property names while the document structure adheres to Elasticsearch's data contract.

```text
Java property                 Elasticsearch document
-------------                 ----------------------
firstName          ------->   first_name
email              ------->   email_address
createdAt          ------->   created_at
lineItems          ------->   line_items
```

The important point is to distinguish **Java property name**, **Elasticsearch field name**, and **field mapping type**. These three concepts are related, not identical.

## 1. Java Property Names and Elasticsearch Field Names

Suppose an application has the class:

```java
public class CustomerDocument {
    private String firstName;
    private String email;
}
```

`firstName` and `email` are the property names used by Java code. When Spring Data generates a mapping by default, the corresponding field names are usually taken from the Java property names unless a renaming configuration is present.

The Elasticsearch document may look like this:

```json
{
  "firstName": "An",
  "email": "an@example.com"
}
```

The Elasticsearch field name is the name appearing in `_source` and the index mapping. This name is used when writing Query DSL directly, inspecting mappings, or interacting with the Java API Client at a low level.

If the data contract requires snake_case, you can rename the fields in Elasticsearch while keeping the Java property names unchanged:

```java
public class CustomerDocument {

    @Field(name = "first_name", type = FieldType.Text)
    private String firstName;

    @Field(name = "email_address", type = FieldType.Keyword)
    private String email;
}
```

The stored document will have the form:

```json
{
  "first_name": "An",
  "email_address": "an@example.com"
}
```

In Java services, you still access `customer.getFirstName()` and `customer.getEmail()`. The annotation specifies the field name at the Elasticsearch layer; it does not change property names, getters, setters, or variables in the Java source code.

## 2. Structure and Meaning of `@Field`

`@Field` belongs to the package:

```java
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
```

This annotation describes how a property is mapped to an Elasticsearch field. The two most commonly used attributes are:

- `name`: the field name in Elasticsearch. If omitted, Spring Data uses the property name according to default mapping rules.
- `type`: the Elasticsearch field type, such as `Text`, `Keyword`, `Long`, `Integer`, `Date`, `Boolean`, `Object`, or `Nested`.

Example:

```java
@Field(name = "product_name", type = FieldType.Text)
private String productName;

@Field(name = "sku", type = FieldType.Keyword)
private String sku;

@Field(name = "quantity", type = FieldType.Integer)
private Integer quantity;
```

`name` addresses naming. `type` determines how Elasticsearch interprets and indexes the value. Changing only `name` does not automatically change the mapping type; changing only `type` does not change the field name.

### Some Common Mapping Types

| Spring Data Type | Elasticsearch Type | Common Use Case |
|---|---|---|
| `FieldType.Text` | `text` | Text content that needs analysis for full-text search. |
| `FieldType.Keyword` | `keyword` | Codes, statuses, emails, or values requiring exact matching or aggregations. |
| `FieldType.Integer` | `integer` | Integers within the 32-bit range. |
| `FieldType.Long` | `long` | Integers with a larger range. |
| `FieldType.Double` | `double` | Double-precision floating-point numbers. |
| `FieldType.Boolean` | `boolean` | True/false values. |
| `FieldType.Date` | `date` | Dates and times in configured formats. |
| `FieldType.Object` | `object` | Regular JSON objects. |
| `FieldType.Nested` | `nested` | Arrays of objects where relationships between fields within the same element must be preserved. |

Do not choose a type based solely on the Java type. For example, `String` can be mapped to `text` or `keyword` depending on usage. A product name needing full-text search can be `text`; a product code is typically suited to `keyword`.

## 3. Complete Example: Java camelCase, Elasticsearch snake_case

Suppose the `customers` index requires fields in snake_case. The entity can be written as follows:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "customers")
public class CustomerDocument {

    @Id
    private String id;

    @Field(name = "customer_code", type = FieldType.Keyword)
    private String customerCode;

    @Field(name = "first_name", type = FieldType.Text)
    private String firstName;

    @Field(name = "last_name", type = FieldType.Text)
    private String lastName;

    @Field(name = "email_address", type = FieldType.Keyword)
    private String email;

    @Field(name = "is_active", type = FieldType.Boolean)
    private Boolean active;

    // constructors, getters, setters
}
```

When saving an object, `_source` may contain:

```json
{
  "customer_code": "CUS-001",
  "first_name": "An",
  "last_name": "Nguyen",
  "email_address": "an@example.com",
  "is_active": true
}
```

Here:

- Java code uses `customerCode`, `firstName`, `lastName`, `email`, `active`.
- The Elasticsearch document uses `customer_code`, `first_name`, `last_name`, `email_address`, `is_active`.
- The mapping type is declared individually for each field.

When Spring Data reads the document, the converter relies on mapping metadata to assign `first_name` to the `firstName` property, `email_address` to `email`, and so on. The application does not need to write manual name-conversion code on every save or read.

## 4. `@Id` Differs from `@Field`

`@Id` marks the Java property used as the Elasticsearch document ID. The document ID is stored in `_id` metadata, not as a regular field inside `_source`.

Example:

```java
@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(name = "product_name", type = FieldType.Text)
    private String name;
}
```

The document may have metadata:

```text
_index: products
_id:    P-100
```

and `_source`:

```json
{
  "product_name": "Java Fundamentals"
}
```

Do not expect the `id` property to automatically appear as a JSON field `id`. If business logic needs an identifier stored inside `_source` as well for querying or displaying like a regular field, declare a separate property, such as `productCode`, and map it with `@Field`.

## 5. Field Names in Nested Objects

`@Field(name = ...)` also applies to properties inside nested objects. Example:

```java
public class Address {

    @Field(name = "street_name", type = FieldType.Text)
    private String street;

    @Field(name = "city_name", type = FieldType.Keyword)
    private String city;
}

@Document(indexName = "customers")
public class CustomerDocument {

    @Id
    private String id;

    @Field(name = "full_name", type = FieldType.Text)
    private String fullName;

    private Address address;
}
```

Corresponding document:

```json
{
  "full_name": "An Nguyen",
  "address": {
    "street_name": "12 Le Loi",
    "city_name": "Ho Chi Minh City"
  }
}
```

The field path in Elasticsearch is `address.city_name`, not `address.city`. When working with raw Query DSL, you must use the exact field name from the Elasticsearch mapping.

For arrays of objects, distinguish between `object` and `nested`. Regular `object` mapping can flatten values during indexing; if you need to preserve relationships between fields of each array element in queries, declare `FieldType.Nested` and use a nested query.

Example:

```java
public class OrderLine {

    @Field(name = "product_code", type = FieldType.Keyword)
    private String productCode;

    @Field(name = "unit_price", type = FieldType.Double)
    private Double unitPrice;
}

@Document(indexName = "orders")
public class OrderDocument {

    @Id
    private String id;

    @Field(name = "line_items", type = FieldType.Nested)
    private List<OrderLine> lineItems;
}
```

The corresponding field paths are `line_items.product_code` and `line_items.unit_price`. Using `Nested` requires pairing with a nested query when querying conditions that must match on the same element.

## 6. Where Are Property Names Used vs. Elasticsearch Field Names?

This is an easy point of confusion when a Java class uses `firstName` while the mapping stores `first_name`.

### Repository Methods Rely on Java Properties

For query methods derived by Spring Data from method names, the property names are typically the entity's Java property names:

```java
public interface CustomerRepository
        extends ElasticsearchRepository<CustomerDocument, String> {

    List<CustomerDocument> findByFirstName(String firstName);

    Optional<CustomerDocument> findByEmail(String email);
}
```

Here `FirstName` and `Email` reference the Java properties `firstName` and `email`. Spring Data uses mapping metadata to translate the conditions to the corresponding fields in Elasticsearch, such as `first_name` or `email_address`.

### Raw Query JSON Uses Elasticsearch Field Names

With `@Query`, the JSON content is Query DSL sent to Elasticsearch. Therefore, fields in the JSON must use the names from the Elasticsearch mapping:

```java
@Query("{\"term\": {\"email_address\": \"?0\"}}")
List<CustomerDocument> searchByEmailAddress(String email);
```

If you write `email` in the JSON when the actual mapping is `email_address`, the query will search the wrong field and usually fail to return expected results.

### Direct Java API Client Calls Use Elasticsearch Field Names

When calling the Elasticsearch Java API Client at a low level, field names are also the names in the mapping:

```java
SearchResponse<CustomerDocument> response = client.search(s -> s
        .index("customers")
        .query(q -> q
                .term(t -> t
                        .field("email_address")
                        .value(v -> v.stringValue("an@example.com"))
                )
        ), CustomerDocument.class);
```

The Java API Client does not automatically infer that `email_address` corresponds to the `email` property in a Spring Data class. The application is writing Query DSL directly, so it must use Elasticsearch names.

For higher-level Spring Data query APIs, how fields are specified depends on the specific abstraction: some APIs accept property paths and map them through metadata; APIs accepting raw field names or Query DSL require Elasticsearch names. When unsure, check the contract of the API you are using and the actual mapping rather than assuming every field name string is translated automatically.

## 7. `@Field` Is Not Only for Renaming

Beyond `name` and `type`, `@Field` has attributes controlling how Elasticsearch indexes and searches the field. Some common attributes:

| Attribute | Meaning |
|---|---|
| `index` | Whether to index the field for searching. `false` prevents the field from being indexed in the usual way. |
| `store` | Whether to store the field value separately for retrieval via stored fields; different from storing in `_source`. |
| `analyzer` | Analyzer used when indexing a `text` field. |
| `searchAnalyzer` | Analyzer used when analyzing queries for the field. |
| `normalizer` | Normalizer for `keyword` fields when value normalization is needed. |
| `format` / `pattern` | Accepted date/time formats for `date` fields. |
| `ignoreAbove` | Length limit for `keyword` values indexed according to the corresponding setting. |
| `coerce` | Controls whether Elasticsearch converts certain input values to the field type. |

Example of a field stored only in `_source` for display, without needing search:

```java
@Field(name = "internal_note", type = FieldType.Text, index = false)
private String internalNote;
```

The value can still reside in `_source`, but it cannot be used as an indexed field for regular term/full-text queries. `index = false` does not mean `store = true`.

Example of a date configuration:

```java
@Field(name = "created_at", type = FieldType.Date)
private Instant createdAt;
```

When using date/time types, ensure the written data format is compatible with the index's date mapping. If the system has a custom format contract, declare `format`/`pattern` suitable for the Spring Data and Elasticsearch versions in use, and verify the actual mapping.

## 8. Multi-fields: One Property, Multiple Ways to Search

Sometimes the same value needs to support both full-text search and exact filtering/sorting. Elasticsearch supports multi-fields: a primary field can have subfields with different mapping types.

For example, a product name can be analyzed as `text` while also having a `keyword` subfield for sorting or aggregations. Spring Data Elasticsearch provides `@MultiField` and `@InnerField` to describe this structure:

```java
@MultiField(
    mainField = @Field(type = FieldType.Text),
    otherFields = {
        @InnerField(suffix = "keyword", type = FieldType.Keyword)
    }
)
private String productName;
```

The mapping can have a main field `productName` of type `text` and a subfield `productName.keyword` of type `keyword` (the main field name can be changed using the `name` attribute if needed). A subfield is not a second Java property; it is part of the mapping of the same property.

When querying with raw DSL or using the Java API Client, reference the exact field/subfield path from the Elasticsearch mapping, such as `productName.keyword`.

## 9. Verifying Actual Field Names on Elasticsearch

Do not conclude what mapping an index has solely by looking at annotations. The index may have been created previously, created by a template, or managed by another process.

Read the mapping:

```http
GET /customers/_mapping
```

Read a document and `_source`:

```http
GET /customers/_doc/CUS-001
```

Inspect the indexed fields and data types via the mapping response. If `first_name` is the declared field, the mapping will display this name under `properties`.

Abbreviated mapping example:

```json
{
  "customers": {
    "mappings": {
      "properties": {
        "first_name": { "type": "text" },
        "email_address": { "type": "keyword" },
        "is_active": { "type": "boolean" }
      }
    }
  }
}
```

If a document contains data but a query finds nothing, check all of the following together:

1. The field name in `_source`.
2. The field name and type in the mapping.
3. The field name actually sent in Query DSL.
4. The analyzer/normalizer and query type being used.
5. Whether the document has been refreshed so search can see it.

## 10. Renaming Fields When an Index Already Exists

`@Field(name = "first_name")` describes the mapping Spring Data wants to use. Editing an annotation in source code does not automatically rename fields on an existing index or migrate old data.

Suppose an old index has a `firstName` field, and the entity later changes to:

```java
@Field(name = "first_name", type = FieldType.Text)
private String firstName;
```

If the old mapping is still `firstName`, old documents still store data under the old structure. Queries searching for `first_name` will not automatically find values sitting in `firstName`. Changing the mapping type of the same field path can also cause a mapping conflict.

A safe renaming workflow typically includes:

1. Create a new index with the right mapping, such as `customers_v2`.
2. Reindex data from the old index and transform field names if needed.
3. Verify document counts, mapping, queries, and sample data.
4. Switch read/write aliases to the new index according to the deployment plan.
5. Delete the old index only after confirming the transition and rollback capability.

Do not delete a production index just to make a new annotation take effect. For data that must be preserved, design a migration and backup before switching.

## 11. Common Mistakes

| Symptom | Common Cause | How to Check |
|---|---|---|
| Query returns no results after renaming a Java property | Raw query still uses the old name or the mapping name differs from the property name. | Inspect `_mapping`, `_source`, and the actual Query DSL request. |
| Query method works but `@Query` does not | Query method uses property metadata, while JSON in `@Query` uses the wrong field name. | Change JSON to use Elasticsearch field names. |
| Saving a document reports a mapping conflict | The index already has a field with the same name but a different type from the new mapping. | Read the mapping and check index/template creation history. |
| Java property receives null after reading | Field name in document does not match mapping metadata or data was written under an old schema. | Check `_source`, annotations, and converter mapping. |
| Field exists in `_source` but query cannot find it | Field may have `index = false`, or the query/analyzer is unsuitable. | Inspect the mapping and query type. |
| Sorting/aggregation on a text field fails | `text` fields are unsuitable for regular sorting/aggregation. | Use a `keyword` field or an appropriate multi-field. |

## 12. Naming Conventions to Apply

A clear convention helps reduce errors between Java code, mappings, and Query DSL:

- Java properties use camelCase, such as `firstName`, `createdAt`, `lineItems`.
- Elasticsearch fields use a uniform convention per the data contract, such as snake_case (`first_name`, `created_at`, `line_items`) or camelCase if the system has adopted that style.
- Use `@Field(name = "...")` explicitly when the field name must differ from the Java property.
- Use `@Field(type = ...)` when the mapping type must be explicitly specified, especially for `text`, `keyword`, `date`, `nested`, and numeric types.
- Do not map two Java properties to the same Elasticsearch field name without an intentional mapping design.
- For nested objects, keep path names consistent and avoid arbitrarily putting dots in field names to mimic object structure.
- Query DSL written directly must use exact field names from the mapping.
- Treat the Elasticsearch mapping as a deployed data contract; changing field names or types requires a migration.

## 13. Key Points to Remember

- Java property names and Elasticsearch field names can differ.
- Without declaring `name`, Spring Data usually uses the property name according to default mapping rules.
- `@Field(name = "first_name")` maps the Java property `firstName` to the Elasticsearch field `first_name`.
- `@Field(type = ...)` declares the mapping type; choose `text`, `keyword`, `date`, or `nested` based on query needs.
- `@Id` maps a Java property to `_id` metadata, unlike regular fields in `_source`.
- Repository query methods rely on Java properties; raw Query DSL and the Java API Client directly use Elasticsearch field names.
- `index`, `store`, analyzers, and other attributes control mapping behavior, not property renaming.
- Editing annotations does not automatically fix mappings and data in existing indexes; migration/reindexing is required when changing schemas.

Understanding the relationship between Java properties and Elasticsearch fields allows Spring Data models to retain readable names while documents comply with the system's storage and search conventions. When troubleshooting, compare the entity, actual mapping, `_source`, and Query DSL to pinpoint which layer is using the wrong field name.
