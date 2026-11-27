# Document, fields, `_id`, and `_source`

In Elasticsearch, data is stored as **JSON documents** inside an **index**. Each document has fields describing the object, an `_id` identifier managed by Elasticsearch, and a `_source` body that can be returned during reads or searches. Spring Data Elasticsearch maps these concepts from Java classes using `@Document`, `@Id`, and `@Field`.

Clearly understanding documents, `_id`, and `_source` helps you design proper mappings, choose the right field types for queries, and avoid confusing document identifiers with business data.

## 1. What is a document?

A **document** is the basic unit of data that Elasticsearch indexes and searches. A document typically represents a business object, such as a product, customer, order, or article. Document content is sent as JSON.

Example of a product document:

~~~json
{
  "name": "Mechanical Keyboard",
  "sku": "KB-001",
  "priceInCents": 129900,
  "active": true,
  "tags": ["keyboard", "mechanical"],
  "brand": {
    "name": "Example Tech"
  },
  "createdAt": "2026-11-13T09:30:00Z"
}
~~~

In this example, `name`, `sku`, `priceInCents`, `active`, `tags`, `brand`, and `createdAt` are fields. A field's value can be a string, number, boolean, array, or nested object.

Common concepts:

| Concept | Meaning |
| --- | --- |
| Index | A collection of documents with the same storage purpose and mapping definitions. Conceptually similar to a database table, though its organization and querying differ from relational databases. |
| Document | A JSON object stored in an index. |
| Field | An attribute inside a document, similar to an object property or data column. |
| Mapping | Defines the data type and how Elasticsearch indexes each field. |

Documents are not required to have the exact same JSON structure as every other document. However, documents in the same index should generally follow a consistent mapping so querying, sorting, and aggregations produce predictable results.

## 2. Fields and mapping

### 2.1. A field is an attribute of a document

Each name-value pair in JSON forms a field. A field can contain:

- A single value: `name`, `priceInCents`, `active`.
- Multiple values: `tags` is an array of strings.
- An object: `brand` contains a sub-field `name`.
- An array of objects: `variants` can contain multiple product variants.

Elasticsearch does not have a dedicated mapping type named `array`. Any field can accept a single value or multiple values of the same type. For example, `tags` can be `"keyboard"` or `["keyboard", "mechanical"]`; the mapping remains `keyword`.

### 2.2. Mapping determines how Elasticsearch understands fields

A mapping declares the data type of a field and certain indexing behaviors. Commonly used types include:

| Mapping type | Common usage |
| --- | --- |
| `text` | Content that needs to be analyzed into tokens for full-text search, such as product names or descriptions. |
| `keyword` | Strings requiring exact matching, filtering, grouping, or sorting, such as SKUs, statuses, or country codes. |
| `long`, `integer`, `double`, `float` | Numeric values used for range filtering, sorting, or calculations. |
| `boolean` | True or false values. |
| `date` | Date and time; Elasticsearch converts the value into a time representation for range queries. |
| `object` | A JSON object containing sub-fields. |
| `nested` | An array of objects that needs to preserve relationships between fields within the same element. |
| `geo_point` | Geographic coordinates used for geospatial queries. |

Distinguishing between `text` and `keyword` is especially important:

- `text` is typically split into tokens by an analyzer. A `match` query is suited for content search, such as finding products whose names contain words related to `mechanical keyboard`.
- `keyword` keeps the value as a single unit for exact matching. A `term` query is suited for an SKU like `KB-001` or status `ACTIVE`.

Examples of two queries:

~~~json
{
  "query": {
    "match": {
      "name": "mechanical keyboard"
    }
  }
}
~~~

~~~json
{
  "query": {
    "term": {
      "sku": "KB-001"
    }
  }
}
~~~

You should not use `term` for arbitrary searches on a `text` field, because the value has already been processed by an analyzer. Conversely, `match` is not the default choice for identifiers or statuses that require exact matching.

### 2.3. Object and nested

For a single object like `brand`, an `object` mapping is usually sufficient. Elasticsearch indexes the sub-fields by path, such as `brand.name`.

Arrays of objects require closer consideration. Suppose a product has two variants:

~~~json
{
  "variants": [
    { "color": "black", "stock": 0 },
    { "color": "white", "stock": 5 }
  ]
}
~~~

With the default `object` mapping, Elasticsearch flattens sub-field values when indexing. A query combining `color = black` and `stock > 0` could match values from two different elements and return this document, even though the black variant is actually out of stock.

If query conditions must apply to the **same element** in an array of objects, declare the field as `nested` and use a nested query. For example:

~~~json
{
  "query": {
    "nested": {
      "path": "variants",
      "query": {
        "bool": {
          "must": [
            { "term": { "variants.color": "black" } },
            { "range": { "variants.stock": { "gt": 0 } } }
          ]
        }
      }
    }
  }
}
~~~

`nested` has higher storage and query costs than `object` because Elasticsearch handles each nested element as a separate internal document. Only use it when you need to preserve relationships between fields within the same element.

### 2.4. Dynamic mapping and explicit mapping

Elasticsearch can automatically create mappings for new fields when receiving documents if dynamic mapping is enabled. The type is inferred from the first value Elasticsearch observes. This is convenient for experimentation, but it can produce types unsuitable for long-term query needs.

For example, a date string might be detected as `date`, or a code string might be mapped in a way unsuitable for exact filtering. When subsequent documents send values incompatible with the created mapping, write operations can fail or require conversion handling.

For stable business data, you should declare explicit mappings before writing important data. Changing the type of an existing field usually requires creating a new index with the desired mapping and reindexing data into it; you cannot arbitrarily change `text` directly to `keyword` on an already created field.

## 3. `_id` — the document identifier

`_id` is a metadata field Elasticsearch uses to identify a document within an index. Every document in the same index must have a unique `_id`. Two different indices can have documents with the same `_id` because uniqueness is scoped per index.

There are two common ways to obtain `_id`:

- **Auto-generated:** the application sends a document without specifying an ID; Elasticsearch generates an ID and returns it in the response.
- **Application-specified:** the application passes the ID in the request path or via Spring Data mapping. This is useful when you need stable document addresses, repeated writes to the same key, or direct document lookups.

Example REST API call specifying an ID:

~~~http
PUT /products/_doc/KB-001
Content-Type: application/json

{
  "name": "Mechanical Keyboard",
  "sku": "KB-001",
  "active": true
}
~~~

Reading a document by ID:

~~~http
GET /products/_doc/KB-001
~~~

When using `PUT` with the same index and the same `_id`, Elasticsearch writes the document at that address; the previous content may be replaced by the new content. Therefore, application-chosen IDs should be stable and accurately reflect business identification rules.

`_id` is metadata, not an ordinary business field in the mapping. You can use the ID to fetch a document directly or use an `ids` query. If you need to search, filter, sort, or aggregate by a business code, store that code as a separate `keyword` field, such as `sku` or `externalId`.

### 3.1. Mapping `_id` with `@Id` in Spring Data Elasticsearch

Spring Data Elasticsearch uses the `@Id` annotation to mark the Java property used as the Elasticsearch `_id`. This annotation comes from `org.springframework.data.annotation.Id`.

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    private String name;

    // Constructors, getters, and setters
}
~~~

When Spring Data writes a `Product`, the `id` value is used as the `_id` metadata. When reading a document, Spring Data uses `_id` to populate the entity's `id` property.

In Spring Data Elasticsearch's default mapping mechanism, the property annotated with `@Id` is used as `_id` and is not written as a regular field inside `_source`. If the application needs to search by a business code, declare an additional property, such as `sku`, and map it as `keyword`.

## 4. `_source` — the JSON content of the document

`_source` is the JSON body sent when indexing a document and stored by Elasticsearch so the original content can be returned. This is the data Spring Data typically reads to convert search results back into Java entities.

Example of a condensed response when fetching a document by ID:

~~~json
{
  "_index": "products",
  "_id": "KB-001",
  "_version": 1,
  "_source": {
    "name": "Mechanical Keyboard",
    "sku": "KB-001",
    "active": true
  }
}
~~~

In this result:

- `_index` indicates the index containing the document.
- `_id` is the identifier managed by Elasticsearch.
- `_version` is the internal version information of the document.
- `_source` contains the JSON fields of the document.

`_source` is not a regular field that the application declares under `properties` in the mapping. Nor is it where Elasticsearch performs full-text search. Searching relies on index structures built from the mapping; `_source` primarily serves to retrieve the document's content.

### 4.1. Filtering `_source` content when searching

When only a few fields are needed, source filtering can be used to reduce the amount of returned data:

~~~json
{
  "_source": ["name", "sku"],
  "query": {
    "term": {
      "sku": "KB-001"
    }
  }
}
~~~

The result still includes the `_id` metadata, while `_source` contains only the requested fields. Source filtering helps reduce network payload and deserialization overhead when documents have many fields.

### 4.2. How `_source` differs from field `store`

By default, applications usually retrieve fields from `_source`. A mapping also allows marking specific fields with `store: true` so Elasticsearch stores that field separately and returns it when `stored_fields` is requested.

The two mechanisms serve different purposes:

- `_source` stores the document's JSON content so the document can be reconstructed.
- `store: true` separately stores the value of a selected field; the application must request stored fields when reading.

There is no need to enable `store: true` just to read a field from `_source`. Only configure stored fields when there is a specific reason related to data retrieval patterns.

### 4.3. Disabling `_source`

An index can be configured not to store `_source`, but this decision removes the ability to retrieve the original JSON in the standard way. Operations that depend on source, such as returning full documents or performing partial updates, will be restricted. For Spring Data applications that need to map search results into entities, keep `_source` enabled unless you have explicitly designed an alternative retrieval mechanism.

## 5. Declaring documents and fields with Spring Data Elasticsearch

Spring Data Elasticsearch maps Java entities to Elasticsearch documents. Key annotations in the example:

- `@Document(indexName = "products")`: declares the target index for the entity.
- `@Id`: marks the property used as `_id`.
- `@Field`: declares the mapping type and field options.

Entity example:

~~~java
import java.time.Instant;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text, analyzer = "standard")
    private String name;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Long)
    private Long priceInCents;

    @Field(type = FieldType.Boolean)
    private Boolean active;

    @Field(type = FieldType.Date)
    private Instant createdAt;

    @Field(type = FieldType.Object)
    private Brand brand;

    @Field(type = FieldType.Nested)
    private List<Variant> variants;

    // Constructors, getters, and setters
}
~~~

The `Brand` and `Variant` classes can be declared as follows:

~~~java
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

public class Brand {

    @Field(type = FieldType.Keyword)
    private String name;

    // Getters and setters
}

public class Variant {

    @Field(type = FieldType.Keyword)
    private String color;

    @Field(type = FieldType.Integer)
    private Integer stock;

    // Getters and setters
}
~~~

For the entity above, the corresponding mapping can conceptually be represented in JSON as follows:

~~~json
{
  "mappings": {
    "properties": {
      "name": { "type": "text", "analyzer": "standard" },
      "sku": { "type": "keyword" },
      "priceInCents": { "type": "long" },
      "active": { "type": "boolean" },
      "createdAt": { "type": "date" },
      "brand": {
        "properties": {
          "name": { "type": "keyword" }
        }
      },
      "variants": {
        "type": "nested",
        "properties": {
          "color": { "type": "keyword" },
          "stock": { "type": "integer" }
        }
      }
    }
  }
}
~~~

The JSON mapping does not declare `id` under `properties`, because the entity's `id` is already used as `_id` metadata. If you need a business field for querying by code, add a separate property such as `sku`.

When Spring Data is configured to create indices from entity metadata, `@Document` and `@Field` annotations provide the information to create the index and mapping. If the index already exists, simply modifying annotations in Java does not automatically alter the running mapping. You need to manage mapping lifecycles and index creation according to your application's process.

### 5.1. Writing and reading documents via a repository

A repository can be declared with `String` as the ID type:

~~~java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
~~~

Usage example:

~~~java
Product product = new Product();
product.setId("KB-001");
product.setName("Mechanical Keyboard");
product.setSku("KB-001");
product.setActive(true);

productRepository.save(product);

var result = productRepository.findById("KB-001");
~~~

`save` writes the entity to the index declared on `@Document`; `findById` looks it up by `_id` metadata. Queries on properties such as `sku` rely on the corresponding field mapping and the query construction of the repository or `ElasticsearchOperations`.

## 6. Data flow from Java to Elasticsearch

You can visualize the write and read process in the following steps:

~~~mermaid
flowchart TD
    A["Java entity Product"] --> B["Spring Data mapping metadata"]
    B --> C["JSON document + _id metadata"]
    C --> D["Elasticsearch checks mapping"]
    D --> E["Index fields"]
    D --> F["Store _source content"]
    E --> G["Search by field"]
    F --> H["Return document content"]
    G --> I["Search hit: _id + _source"]
    H --> I
    I --> J["Spring Data converts to Product"]
~~~

On the write path, Spring Data reads metadata from the entity, takes the `@Id` value as `_id`, and converts the remaining properties to JSON according to mapping rules. Elasticsearch uses the mapping to analyze and index fields while storing `_source` if configuration permits.

On the read path, Elasticsearch returns metadata such as `_id` along with `_source` (if requested and enabled). Spring Data uses that information to reconstruct the Java entity, including assigning `_id` to the `@Id` property.

## 7. Common design mistakes

| Error-prone approach | Appropriate solution |
| --- | --- |
| Using a `text` field for SKU and querying with `term`. | Use `keyword` for codes requiring exact matching. |
| Using `keyword` for long descriptions needing word-based search. | Use `text` with an appropriate analyzer. |
| Treating `@Id` as a business field that always appears in `_source`. | Treat `@Id` as mapping to `_id` metadata; create a separate field if you need the business code stored in source. |
| Using `object` for an array of objects while expecting query conditions to always match on the same element. | Use `nested` and a nested query when relationships between fields within each element must be preserved. |
| Letting dynamic mapping choose types for all important fields. | Declare explicit mappings for fields with clear query requirements. |
| Assuming editing `@Field` automatically updates the mapping of an existing index. | Create a new mapping/index and reindex when you need to change a field's type. |
| Disabling `_source` while still needing to reconstruct full entities from search results. | Keep `_source` or explicitly design an alternative storage and retrieval mechanism. |

## 8. How to design a document

When designing a Spring Data Elasticsearch entity, start from how the application will search the data:

1. Identify which business object each document represents and which index contains it.
2. Choose a stable ID if the application needs to read back or overwrite the document by the same identifier; mark that property with `@Id`.
3. For each field, determine the search requirement: full-text (`text`), exact match (`keyword`), numeric, date/time, boolean, or geospatial data.
4. Choose `object` for ordinary nested objects; choose `nested` when queries must combine conditions on the same element of an object array.
5. Keep `_source` if the application needs to return documents or convert search results into Java entities.
6. Create and verify the mapping before ingesting significant data into the index.

When these choices are clear, Java classes, Elasticsearch mappings, and application queries will stay more consistent. The document describes the data, the mapping defines how the data is understood and indexed, `_id` identifies the document, and `_source` holds the JSON content so the application can read it back.
