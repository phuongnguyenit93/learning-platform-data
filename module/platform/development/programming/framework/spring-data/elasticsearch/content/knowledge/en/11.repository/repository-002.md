# Declaring Document Types and Identifier Types

In Spring Data Elasticsearch, a Java class must be described as a document stored in Elasticsearch, and one property must be designated as the document's identifier key. The two essential annotations for this are `@Document` and `@Id`.

`@Document` marks a domain class mapped to an Elasticsearch index. This annotation provides metadata such as the index name and index creation policy. `@Id` marks the Java property mapped to the document's `_id` metadata. When combined with a repository, the ID property type must match the ID parameter in the repository declaration, for example `ElasticsearchRepository<Product, String>` if the entity uses `String` as its ID.

These two annotations do not turn Elasticsearch into a relational database. An index stores and searches documents; `_id` is the unique identifier of a document within an index; and business attributes such as SKU, customer code, or order number can be stored as separate fields inside `_source` for searching, filtering, or aggregations with appropriate mappings.

## 1. From Java Class to Elasticsearch Document

Suppose an application manages products. A product has an identifier, an SKU, a name, and a price. On the Java side, we model the data with a `Product` class:

```java
public class Product {
    private String id;
    private String sku;
    private String name;
    private Double price;
}
```

Elasticsearch stores documents as JSON inside an index, for example the `products` index:

```json
{
  "sku": "SKU-1001",
  "name": "Mechanical Keyboard",
  "price": 185000
}
```

A document also has metadata managed by Elasticsearch, where `_index` identifies the index containing the document and `_id` identifies the document within that index. When reading a document, the response may look like:

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

`_id` is Elasticsearch's identifier metadata. It is not synonymous with a JSON field named `id` inside `_source`. Spring Data maps the property annotated with `@Id` to `_id`, while other business properties are mapped into the document body.

General relationship:

```mermaid
flowchart TD
    A[Java class Product] --> B[@Document indexName=products]
    A --> C[@Id property]
    B --> D[Index products]
    C --> E[Elasticsearch metadata _id]
    A --> F[Other mapped properties]
    F --> G[Document _source]
    D --> H[Stored document]
    E --> H
    G --> H
```

## 2. Declaring `@Document`

`@Document` belongs to the `org.springframework.data.elasticsearch.annotations` package. This annotation is placed on the Java class representing the document and tells Spring Data the target index when saving or querying the entity.

Basic example:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    private String sku;
    private String name;
    private Double price;
}
```

In this example, the `Product` entity maps to the `products` index. When Spring Data performs save or search operations for `Product`, `@Document` metadata is used to determine the target index.

### 2.1 `indexName`

`indexName` is the name of the index or alias used by the entity. Elasticsearch index names must follow Elasticsearch naming rules; typically, use lowercase letters, hyphens, and clear index versioning conventions.

Example:

```java
@Document(indexName = "products")
public class Product {
    // fields
}
```

With a versioned index:

```java
@Document(indexName = "products-v2")
public class Product {
    // fields
}
```

In systems that require migrations, applications should usually reference a stable alias such as `products` instead of hardcoding physical names like `products-v1` or `products-v2`. The alias can be switched from the old index to the new index once migration completes, while repository code continues using the same logical name.

Example:

```java
@Document(indexName = "products")
public class Product {
    // fields
}
```

On the cluster, the `products` alias can point to the physical index `products-v2`. When switching the alias to another index, the repository still accesses it through `products`.

### 2.2 `createIndex`

`@Document` has a `createIndex` attribute to control whether Spring Data creates the index during mapping/repository initialization. The default value in modern Spring Data Elasticsearch versions is typically `true`.

Example:

```java
@Document(
    indexName = "products",
    createIndex = false
)
public class Product {
    // fields
}
```

`createIndex = false` is suitable when indices are created and managed by a separate deployment process, such as index templates, migrations, or infrastructure management tools. In that case, the application should not create indices on startup.

When `createIndex = true`, Spring Data can create the index and mapping from entity metadata if the index does not yet exist, depending on configuration and version. This is convenient in development environments or small applications. In production, indices with custom analyzers, special settings, aliases, and versioning workflows should usually be managed via controlled migrations.

`createIndex` does not mean Spring Data will automatically alter every existing mapping to match updated annotations. If an index already exists with incompatible field types, changing the entity does not migrate data or change field types on the cluster.

### 2.3 `@Document` is not JPA's `@Entity`

Spring Data Elasticsearch uses `@Document`, whereas JPA uses `@Entity` and `@Table`. The two systems have different storage models:

| Annotation | System | Meaning |
|---|---|---|
| `@Document` | Spring Data Elasticsearch | Maps a Java class to an Elasticsearch index |
| `@Entity` | JPA | Marks a persistent entity class in a relational model |
| `@Table` | JPA | Specifies a relational table |
| `@Id` | Spring Data | Marks the ID property for Spring Data mapping |

Do not add JPA annotations simply because their names are familiar. If a class needs to be stored in both a relational database and Elasticsearch, design mappings for each persistence technology explicitly and avoid mixing up annotations or lifecycles.

## 3. Declaring `@Id`

`@Id` marks the Java property that maps to the document's `_id` identifier. The Spring Data annotation lives in `org.springframework.data.annotation.Id`.

```java
import org.springframework.data.annotation.Id;

public class Product {

    @Id
    private String id;

    private String name;
}
```

When writing a document, the value of `id` is used as `_id`. When reading a document, Spring Data retrieves `_id` and assigns it back to the property annotated with `@Id`.

### 3.1 The Java property name does not have to be `id`

The ID property can have a more business-meaningful name:

```java
@Id
private String productId;
```

Spring Data recognizes the identifier based on the annotation, not the property name. The `productId` value is still mapped to Elasticsearch's `_id` metadata.

However, if `@Id` is omitted, do not assume a property named `id` or `productId` automatically becomes `_id`. Mark it explicitly so mapping does not rely on field-name inference.

### 3.2 `_id` differs from business fields in `_source`

Suppose an entity has:

```java
@Id
private String id;

private String sku;
```

A document may have metadata:

```json
{
  "_id": "product-1001",
  "_source": {
    "sku": "SKU-1001"
  }
}
```

Here:

- `_id` is the Elasticsearch identifier.
- `sku` is a business field in `_source`.
- The two values can be identical, but do not have to be.

If the application needs to search, filter, sort, or aggregate by SKU, store SKU as a separate field with an appropriate mapping, usually `keyword` when exact matching is needed. Do not treat `_id` as a general-purpose business field for all query or aggregation types.

### 3.3 A document has only one `_id`

Each document in an index has a single `_id` identifier. An entity may have multiple business identifier attributes, but only one property serves as the document ID in Spring Data mapping.

For example, a product has `id`, `sku`, `barcode`, and `externalReference`. Only `id` is annotated with `@Id`; the remaining values are regular fields in `_source` if they need to be stored and queried.

```java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Keyword)
    private String barcode;

    @Field(type = FieldType.Keyword)
    private String externalReference;
}
```

Do not annotate multiple properties with `@Id` in the same entity. If you need a composite key, build a unique identifier value on the application side—for instance, by concatenating components with clear escaping and separators, or by using a UUID.

## 4. Choosing a Data Type for ID

In many applications, `String` is a simple and flexible choice for Elasticsearch IDs. It can hold a UUID, an application-generated identifier, or another stable string.

Example:

```java
@Id
private String id;
```

Elasticsearch represents `_id` as a string at the API level. Using `String` therefore avoids tying the ID to a specific data source's numeric type and simplifies integration across systems.

### 4.1 Application-assigned IDs

The application can generate the ID before saving:

```java
Product product = new Product(
    "product-1001",
    "SKU-1001",
    "Mechanical Keyboard",
    185000.0
);

repository.save(product);
```

When the ID is known, write operations target the exact document. Saving with the same ID typically writes the document under the same identifier and replaces its contents according to the semantics of the operation used.

Application-assigned IDs are well suited when you need to:

- Synchronize data from a source system.
- Retry write operations more idempotently.
- Reference documents from APIs or events.
- Ensure a business entity always maps to the same document.
- Populate a target index / reindex while preserving original identifiers.

If the ID is a business key such as SKU, evaluate its stability and uniqueness. If an SKU can change, using SKU as `_id` can cause an SKU update to create a new document and require deleting the old one. A stable internal ID is usually better, while SKU is stored as a separate field.

### 4.2 Elasticsearch-generated IDs

Elasticsearch can auto-generate `_id` when an index operation does not supply an ID. This is useful when the application does not need to determine the ID upfront and simply stores new documents.

However, for workflows requiring retries, synchronization, or duplicate prevention, auto-generated IDs can cause problems: if the server persists the document but the response is lost, a retry may create a duplicate document with a different ID. With application-assigned IDs, retrying with the same ID is usually easier to control.

Specific behavior when the ID is null also depends on the write API and Spring Data Elasticsearch version. Verify how your repository/operations handle empty IDs, and if you need the ID returned by Elasticsearch, use the return value of the write operation per the API rather than assuming the input object is always mutated identically across versions.

### 4.3 UUID as ID

UUIDs are commonly used when unique identifiers are needed without relying on a central database:

```java
import java.util.UUID;

String id = UUID.randomUUID().toString();
```

String-formatted UUIDs fit `_id` well. If the application uses UUIDs, standardize the representation (lowercase/uppercase, with or without hyphens) so the same logical value is never formatted into two different strings.

### 4.4 Numeric IDs and repository types

You may encounter domain models using numeric types as IDs. Even though `_id` in Elasticsearch is represented as a string, Spring Data can convert IDs through the conversion service for supported types. Still, if using an ID type other than `String`, verify the converter and read/write behavior of the version in use.

Crucially, the ID type in the entity and the ID type in the repository must match. For example:

```java
public interface ProductRepository
        extends ElasticsearchRepository<Product, Long> {
}
```

only makes sense when `Product`'s `@Id` property has type `Long` and the corresponding conversion works properly. Do not declare the repository with `String` while the entity uses `Long` just because Elasticsearch `_id` is a string; choose one consistent domain type.

## 5. Declaring a Repository with the Matching ID Type

Spring Data Elasticsearch provides `ElasticsearchRepository<T, ID>`. The first parameter is the entity type; the second parameter is the ID property type.

```java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
```

With this declaration:

- `Product` is the managed entity.
- `String` is the identifier type.
- `findById` accepts `String`.
- `deleteById` accepts `String`.
- `save` accepts and returns `Product` per the repository contract.

Usage example:

```java
import java.util.Optional;

import org.springframework.stereotype.Service;

@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public Product save(Product product) {
        return repository.save(product);
    }

    public Optional<Product> findById(String id) {
        return repository.findById(id);
    }

    public void delete(String id) {
        repository.deleteById(id);
    }
}
```

If the repository declares the wrong ID type, the code may fail to compile when calling methods with mismatched parameter types, or trigger unintended conversions if manual casting is involved. Let the generic type accurately reflect the domain type.

## 6. Complete Entity Example

An entity typically combines `@Document`, `@Id`, and `@Field` to describe the index, identifier, and remaining fields.

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(
    indexName = "products",
    createIndex = false
)
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Double)
    private Double price;

    protected Product() {
    }

    public Product(String id, String sku, String name, Double price) {
        this.id = id;
        this.sku = sku;
        this.name = name;
        this.price = price;
    }

    public String getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }

    public Double getPrice() {
        return price;
    }
}
```

Here `createIndex = false` indicates the index is managed outside the application. If you want Spring Data to create the index from metadata in development, you can omit this attribute or set `createIndex = true` as needed.

Expected mapping:

```json
PUT /products
{
  "mappings": {
    "properties": {
      "sku": { "type": "keyword" },
      "name": { "type": "text" },
      "price": { "type": "double" }
    }
  }
}
```

Note that `id` is used as `_id` metadata. The mapping above does not need to declare a regular `id` property inside `_source` unless the application needs to store an additional separate ID field.

## 7. Distinguishing Elasticsearch IDs from Business Keys

An application may have several key concepts:

- Elasticsearch document ID (`_id`): identifies the document within an index.
- Relational database primary key: identifies a row in a source table.
- Business key: business code such as SKU, contract number, or order number.
- External reference: ID assigned by an external system.

These values can be the same, but do not have to be. Choosing a business key as `_id` only makes sense if it is unique within the index, stable, and aligned with the document lifecycle.

Example:

```java
@Document(indexName = "orders")
public class OrderDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String orderNumber;

    @Field(type = FieldType.Keyword)
    private String customerId;
}
```

`id` may be the document's internal UUID; `orderNumber` is the order number displayed to users; `customerId` is the customer reference. If you need to filter by order number or customer, these business attributes must have appropriate mappings in `_source`.

### 7.1 IDs are unique within an index scope

Elasticsearch requires `_id` to be unique within a single index. Two different indices can contain documents with the same `_id` without conflict.

Example:

```text
products-v1 / _id = product-1001
products-v2 / _id = product-1001
```

This is useful when reindexing or switching index versions: the new index can keep the source document's `_id`. However, if the application queries through an alias pointing to multiple indices, understand how results are combined and avoid unintended duplicate IDs across indices sharing the same alias.

### 7.2 Do not use IDs as an automatic relationship mechanism

Elasticsearch does not automatically create foreign keys or cascade relationships like a relational database just because two documents share a field containing the same ID. If an order document has `customerId`, the application must manage fetching customer details, denormalizing data, or running appropriate queries itself.

`@Id` only identifies the current document. It does not define relationships between other entities.

## 8. `@Document` and Index Aliases / Versioning

In production, indices are often versioned to make mapping changes safely. The application uses a stable alias:

```text
products          -> stable alias
products-v1       -> old physical index
products-v2       -> new physical index
```

The entity keeps:

```java
@Document(indexName = "products")
public class Product {
    // fields
}
```

When `products-v2` is created, the system can reindex data from `products-v1`, verify mappings/queries, and then switch the `products` alias to the new index. The repository does not need to know the physical index name.

This decouples logical names in the application from physical index names. It also makes rollback possible by switching the alias back, though only safely if writes occurring after cutover are handled. Aliases do not automatically sync data between indices.

If an alias points to multiple indices for reads, configure the write index explicitly when the application writes. Avoid writing through a multi-target alias without specifying which index receives writes.

## 9. Creating an Index from Entity Metadata

Spring Data Elasticsearch can use metadata from `@Document` and `@Field` to create mappings. With `ElasticsearchOperations`, you can obtain the `IndexOperations` corresponding to an entity:

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;

public class ProductIndexInitializer {

    private final ElasticsearchOperations operations;

    public ProductIndexInitializer(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void createIndexIfMissing() {
        IndexOperations indexOps = operations.indexOps(Product.class);

        if (!indexOps.exists()) {
            indexOps.create();
            indexOps.putMapping(indexOps.createMapping());
        }
    }
}
```

This is a basic example illustrating how entity metadata can create an index and mapping. In practice, clearly determine who manages settings, analyzers, aliases, templates, and migrations. For an already existing index, `createIndexIfMissing()` does not convert old mappings to match a new class.

### 9.1 Inspecting the actual mapping

After creating the index, use the API:

```http
GET /products/_mapping
GET /products/_settings
```

The actual mapping on the cluster determines how Elasticsearch indexes and queries data. Do not rely solely on code annotations when investigating data-type errors or search results.

### 9.2 Index names must match between entity and infrastructure

If the entity declares `indexName = "products"` while infrastructure only created the index `product`, the repository may fail to find the target index or write to a different index name if permissions and settings allow auto-creation. Align index/alias names across the application, migrations, and cluster configuration.

## 10. Common Misconceptions

### 10.1 Mistakenly using `jakarta.persistence.Id`

In Spring Data Elasticsearch, use:

```java
import org.springframework.data.annotation.Id;
```

Do not substitute `jakarta.persistence.Id` just because the project also uses JPA. The two annotations belong to different persistence models; Elasticsearch mapping requires the metadata annotation that Spring Data Elasticsearch recognizes.

### 10.2 Assuming a field named `id` automatically becomes `_id`

Use `@Id` to explicitly mark the identifier property. The Java property name can be `id`, `productId`, or something else; the annotation is what drives mapping.

### 10.3 Assuming `_id` is a normal field in `_source`

`_id` is Elasticsearch metadata. If you need an ID field that can be queried, sorted, or aggregated using standard mappings, store a separate property inside `_source`.

### 10.4 Using SKU as `_id` even though SKU can change

If SKU changes, the document may be written under a new ID and the old document must be handled separately. Choose an ID that is stable across the entity's lifecycle and store SKU as a business field when needed.

### 10.5 Declaring the wrong repository ID generic

If the entity uses `String` while the repository declares `Long`, the repository API does not reflect the domain model accurately. The second generic type must match the type of the `@Id` property.

### 10.6 Thinking `createIndex = true` always updates mappings

This attribute controls index creation from metadata when the index does not yet exist. It does not allow arbitrarily changing already-indexed field types and is not a migration engine.

### 10.7 Using physical index names everywhere in code

Hardcoding `products-v1` in the entity ties application code to an index version. A stable alias separates logical names from physical indices during migrations.

## 11. Diagnosing When a Repository Cannot Find a Document

When `findById` returns `Optional.empty()` or `save` does not write to the expected index, check in order:

1. Check the entity's `@Document(indexName = ...)`.
2. Check whether the repository generic ID type matches the `@Id` property.
3. Verify the exact ID value passed in, including casing and whitespace if any.
4. Check which physical index the index/alias currently points to.
5. Use `GET /index/_doc/<id>` to inspect the document directly.
6. Use `GET /_cat/indices?v` or `GET /_alias` to confirm the index/alias exists.
7. Check access permissions, endpoints, and client configuration.
8. Inspect `_source` data and mappings if the entity can be read but fields are missing or have the wrong type.

Example:

```http
GET /products/_doc/product-1001
GET /_alias/products
GET /_cat/indices/products*?v
```

If the direct API finds the document while the repository does not, check the index name the entity actually uses, the ID type, and the mapping converter. If even the direct API cannot find it, check which index and ID the document was actually written under.

## 12. Selection Principles

When declaring documents and identifiers, decide clearly:

- Which Java class represents the document and which logical index/alias holds it.
- Whether the index is created by Spring Data or managed by migrations/infrastructure.
- Which property is `_id`, what the Java ID type is, and whether the repository generic matches.
- Whether IDs are application-assigned or Elasticsearch-generated; whether business rules require idempotency or synchronization.
- Which business keys need to be stored as separate fields for search/filtering.
- Whether the index uses versioning/aliases for safe mapping changes.
- Whether actual cluster mappings match entity metadata.

Clear configuration makes repository code easy to understand, gives save/delete/find-by-ID operations consistent semantics, and keeps index migration workflows decoupled from physical names.

## 13. Summary

`@Document` declares that a Java class maps to an Elasticsearch index or alias via `indexName`. The `createIndex` attribute controls creating the index from metadata when it does not exist, though it is not an automatic mapping migration tool. `@Id` marks the property used as the document's `_id` metadata; the Java property name does not have to be `id`, and `_id` is not equivalent to a business field inside `_source`.

When using `ElasticsearchRepository<T, ID>`, the `ID` type must align with the type of the property annotated with `@Id`. Prefer stable IDs, consider application-assigned IDs when retries and synchronization are required, and store business keys like SKU as separate fields when searching or filtering is needed. In production, stable aliases and versioned index management decouple application code from physical index names and support safe migrations.

## References

- [Spring Data Elasticsearch Reference — Object Mapping](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)
- [Spring Data Elasticsearch Reference — Repositories](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories.html)
- [Elasticsearch — Document metadata fields](https://www.elastic.co/guide/en/elasticsearch/reference/current/mapping-fields.html)
- [Elasticsearch — Index aliases](https://www.elastic.co/guide/en/elasticsearch/reference/current/aliases.html)
