# `@Id` and Document Identifier Mapping

In Elasticsearch, every document has a unique identifier called a **document ID**, stored in the `_id` metadata field. Spring Data Elasticsearch provides the `@Id` annotation to map a Java property to this identifier.

`@Id` plays a crucial role when saving, reading, updating, and deleting documents. It tells Spring Data which property value on the entity represents the document ID so it can invoke the appropriate Elasticsearch APIs.

Three concepts need to be distinguished:

- **Document ID (`_id`)**: metadata identifier managed by Elasticsearch for each document within an index.
- **Entity ID property**: Java property annotated with `@Id`, used to exchange the document ID value with Spring Data.
- **Business ID**: business identifier such as an SKU, customer code, or order number. A business ID may match the document ID by design, though it does not have to.

## 1. What Is `_id` in Elasticsearch?

Each document stored in an index needs an identifier so Elasticsearch can locate the document when reading, overwriting, updating, or deleting it.

For example, a product document can be stored in the `products` index with the ID `product-1001`:

~~~http
PUT /products/_doc/product-1001
Content-Type: application/json

{
  "name": "Mechanical Keyboard",
  "sku": "KB-1001",
  "price": 129.99
}
~~~

In this request:

- `products` is the index.
- `_doc` is the document API endpoint.
- `product-1001` is the document ID.
- The JSON body is the document content, typically stored in `_source`.

A document can be read directly by ID:

~~~http
GET /products/_doc/product-1001
~~~

Or deleted by ID:

~~~http
DELETE /products/_doc/product-1001
~~~

`_id` is a metadata field managed by Elasticsearch, not a regular field to be declared in mapping `properties`. The mapping can describe data properties such as `name`, `sku`, and `price`, but does not declare `_id` as a business field.

Example mapping:

~~~json
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text"
      },
      "sku": {
        "type": "keyword"
      },
      "price": {
        "type": "double"
      }
    }
  }
}
~~~

Document IDs are used by Elasticsearch to identify documents. They do not automatically become a property usable for all operations such as sorting or aggregations. If you need to filter, aggregate, or sort by a business code, store that code as an appropriate field, typically `keyword`.

## 2. `@Id` in Spring Data Elasticsearch

Spring Data Elasticsearch uses the `@Id` annotation to mark the Java property mapped to the `_id` document ID.

The annotation must be imported from Spring Data's package:

~~~java
import org.springframework.data.annotation.Id;
~~~

Example entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Double)
    private Double price;

    public Product() {
    }

    public Product(String id, String name, String sku, Double price) {
        this.id = id;
        this.name = name;
        this.sku = sku;
        this.price = price;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    // Remaining getters and setters
}
~~~

In the example:

- `@Document(indexName = "products")` specifies the index that the entity represents.
- `@Id` marks `id` as the document ID.
- `@Field` describes the mapping of data properties such as name, SKU, and price.
- `String` is the common Java type for representing document IDs because Elasticsearch accepts IDs as strings.

Spring Data also has a convention for recognizing a property named `id` when an entity does not declare the `@Id` annotation. However, using `@Id` makes the mapping intent clearer, especially when the Java property is named `productId`, `documentKey`, or something else.

### Choosing the Right Annotation

`@Id` in the example is:

~~~java
import org.springframework.data.annotation.Id;
~~~

Do not confuse it with the annotation of the same name in JPA:

~~~java
import jakarta.persistence.Id;
~~~

`jakarta.persistence.Id` serves JPA primary key mapping. When describing a Spring Data Elasticsearch entity, use Spring Data's `@Id` annotation to ensure mapping metadata is interpreted correctly by Spring Data Elasticsearch.

## 3. How Does an `@Id` Property Differ from a Regular Field?

`@Id` maps the Java property value to the `_id` document ID metadata. It is not a way to declare a `keyword` field inside `_source`.

Example entity:

~~~java
@Document(indexName = "customers")
public class Customer {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String customerCode;

    @Field(type = FieldType.Text)
    private String fullName;
}
~~~

This can be understood as:

| Property | Role |
|---|---|
| `id` | Document ID, mapped to `_id` metadata |
| `customerCode` | Business code, a data field of type `keyword` |
| `fullName` | Customer name data, a `text` field |

If you need to search, filter, sort, or aggregate by `customerCode`, query the `customerCode` field. Do not rely on `_id` as a regular data field.

`_id` can be used in identification operations or `ids` queries. However, Elasticsearch restricts operations on this metadata field; for instance, do not use `_id` for aggregations or sorting like a regular `keyword` field.

## 4. ID Data Types in Entities and Repositories

Elasticsearch document IDs are represented as strings. In Spring Data Elasticsearch, `String` is the simplest and most common choice.

The repository must declare an ID type matching the entity's ID property:

~~~java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
~~~

The first generic parameter is the entity; the second is the Java type of the ID.

| Entity | Repository |
|---|---|
| `Product` with `String id` | `ElasticsearchRepository<Product, String>` |
| `Customer` with `Long id` | `ElasticsearchRepository<Customer, Long>` |
| `Order` with `UUID id` | `ElasticsearchRepository<Order, UUID>` if that type is supported by mapping/conversion in the version used |

Regardless of the Java type used, the final document ID value is still converted to a string when communicating with Elasticsearch. Ensure the ID type in the repository matches the entity's ID property and a conversion supported by Spring Data.

In new applications, using `String` or a `UUID` explicitly converted to a string usually makes the identification model easier to understand and integrate.

## 5. Assigning IDs from the Application

An application can generate the ID before saving a document. This approach is useful when the system already has a stable business identifier or needs to control the ID to retry an operation safely.

Example generating an ID with UUID:

~~~java
import java.util.UUID;

Product product = new Product(
        UUID.randomUUID().toString(),
        "Mechanical Keyboard",
        "KB-1001",
        129.99
);

Product saved = productRepository.save(product);
~~~

When saving the entity, Spring Data uses the `id` value as the document ID.

Some cases where you should assign the ID yourself:

- The data has a stable ID from a source system.
- You want to reuse the same ID when re-syncing data.
- You need to avoid creating duplicate documents when a request is retried.
- You want to reference the document before saving it.

### Using a Business Key as the Document ID

Suppose the SKU is unique and stable within the index scope:

~~~java
Product product = new Product(
        "KB-1001",
        "Mechanical Keyboard",
        "KB-1001",
        129.99
);
~~~

In this design, the document ID and SKU share the same value, yet still serve two roles:

- `id` is used to identify the document.
- `sku` is a business field for searching and filtering.

Keeping `sku` as a `keyword` field allows the application to query, aggregate, or display the SKU without depending on `_id` metadata.

Do not use a business key as the document ID if its value may change frequently. Changing an ID means the document is identified under a different key; you would need to handle creating the new document and deleting or replacing the old one.

## 6. Letting Elasticsearch Generate the ID

Elasticsearch can automatically generate a document ID when an index request does not provide one. This is suitable when the application does not need to control the identifier prior to saving.

Example entity without an ID yet:

~~~java
Product product = new Product(
        null,
        "Mechanical Keyboard",
        "KB-1001",
        129.99
);

Product saved = productRepository.save(product);
~~~

When no ID is provided, the save operation can let Elasticsearch generate the ID. Spring Data Elasticsearch receives the ID from the save response and maps it onto the entity according to the mechanism of the version in use.

If you need to use the ID after saving, retrieve it from the returned entity or inspect the entity state after the save operation:

~~~java
Product saved = productRepository.save(product);
String generatedId = saved.getId();
~~~

Do not assume an ID already exists before calling `save`. If the business logic needs a stable ID for retries or referencing before saving, generate the ID in the application layer.

## 7. Using IDs with ElasticsearchRepository

Once the ID is properly declared, repository CRUD methods operate based on the document ID.

~~~java
import java.util.Optional;

Optional<Product> product = productRepository.findById("KB-1001");

boolean exists = productRepository.existsById("KB-1001");

productRepository.deleteById("KB-1001");
~~~

Corresponding operations:

| Method | Meaning |
|---|---|
| `save(entity)` | Saves the document by the entity's ID; if the ID already exists in the index, the document with that ID is rewritten |
| `findById(id)` | Reads a document by ID |
| `existsById(id)` | Checks whether a document exists by ID |
| `deleteById(id)` | Deletes a document by ID |
| `findAllById(ids)` | Reads multiple documents by a list of IDs |

Example service:

~~~java
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class ProductService {

    private final ProductRepository productRepository;

    public Product create(Product product) {
        return productRepository.save(product);
    }

    public Product getRequired(String id) {
        return productRepository.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException("Product not found: " + id));
    }

    public void delete(String id) {
        productRepository.deleteById(id);
    }
}
~~~

The ID type in repository calls must match the declared generic ID. With `ProductRepository` above, the ID passed in is `String`.

## 8. Using IDs with ElasticsearchOperations

In addition to repositories, Spring Data provides `ElasticsearchOperations` to work directly with entities and documents.

~~~java
import lombok.RequiredArgsConstructor;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class ProductDocumentService {

    private final ElasticsearchOperations operations;

    public Product findById(String id) {
        return operations.get(id, Product.class);
    }

    public void deleteById(String id) {
        operations.delete(id, Product.class);
    }
}
~~~

`operations.get(id, Product.class)` reads the document by ID and converts the result into a `Product` entity.

`operations.delete(id, Product.class)` deletes the document by ID in the index corresponding to the entity's metadata.

Repositories suit CRUD operations and queries through the repository abstraction. `ElasticsearchOperations` suits situations needing finer control over searching, mapping, or document operations.

## 9. Querying Documents by ID via the Elasticsearch API

Elasticsearch provides an API to retrieve a document directly:

~~~http
GET /products/_doc/KB-1001
~~~

When needing to find multiple documents by ID in a single search query, you can use an `ids` query:

~~~json
{
  "query": {
    "ids": {
      "values": ["KB-1001", "KB-1002", "KB-1003"]
    }
  }
}
~~~

The `ids` query checks document IDs. It does not search by the value of the `sku` field inside `_source`.

If you want to search by SKU, use `term` on the `sku` field:

~~~json
{
  "query": {
    "term": {
      "sku": "KB-1001"
    }
  }
}
~~~

Both queries may return the same document if the application chose SKU as the document ID while also storing SKU as a field. However, the meaning of the two queries differs:

- `ids`: searches by document ID metadata.
- `term`: searches by field value in the mapping.

## 10. What Happens When Saving Multiple Times with the Same ID?

In Elasticsearch, the document ID identifies a document within an index. When an index operation is sent with the same ID, the existing document is replaced by the new document content according to Index API semantics.

Example first save:

~~~http
PUT /products/_doc/KB-1001
Content-Type: application/json

{
  "name": "Mechanical Keyboard",
  "sku": "KB-1001",
  "price": 129.99
}
~~~

Subsequent save using the same ID:

~~~http
PUT /products/_doc/KB-1001
Content-Type: application/json

{
  "name": "Mechanical Keyboard Pro",
  "sku": "KB-1001",
  "price": 159.99
}
~~~

The document at ID `KB-1001` is rewritten with the new content. Fields omitted from the new document may no longer remain in `_source` after the index operation.

Therefore:

- Only use `save` when you want to persist the full state of the entity.
- If you need to update a few fields while keeping the rest intact, use an appropriate update/partial update API.
- Ensure IDs are stable and do not accidentally share the same ID between two different entities.

Document IDs are only unique within the scope of a single index. Two different indexes can contain documents with the same ID without conflict.

## 11. Notes on `_id` Limitations

`_id` is very useful for identification, but it should not replace every business field.

### Do Not Use `_id` for Aggregations or Sorting

Elasticsearch supports querying documents by ID, but `_id` is not designed to act as a regular analytical field. Do not rely on `_id` to:

- Group documents using a terms aggregation.
- Sort results by ID value.
- Perform analytics that require doc values.

If you need these operations, store a separate business field with an appropriate data type, typically `keyword`.

### Do Not Change IDs Arbitrarily

If an entity has already been saved with ID `A`, changing the ID to `B` and saving will create or write a document under ID `B`. The old document under ID `A` does not disappear automatically just because the entity's ID changed.

To change an ID, the application must define a clear workflow: read the old document, create a new document with the new ID, confirm the save succeeded, and then delete the old document if needed.

### IDs Must Be Stable and Unique Within an Index

If two different entities share the same ID in one index, a later save operation can overwrite the earlier document. Choose an appropriate identification strategy:

- Application-generated UUID.
- Stable ID from a source system.
- Business key only when uniqueness and stability are guaranteed.

### Distinguish Document IDs from Relational Primary Keys

Elasticsearch is not a relational database. `@Id` does not create foreign keys, does not enforce referential integrity between documents, and does not provide multi-document transactions like a relational database.

If one document contains the ID of another document, that is application-managed reference data. Existence checks, synchronization, and cascading deletes must be designed separately.

## 12. Entity ID Design Workflow

When designing a Spring Data Elasticsearch entity, you can follow these steps:

1. Determine whether the document requires a stable application-provided ID or can use an auto-generated ID.
2. Choose the Java property representing the ID and mark it with `@Id`.
3. Choose an appropriate Java type, usually `String`.
4. Declare the generic ID type of `ElasticsearchRepository` to match the property type.
5. Determine whether the business key needs to be stored as a separate field for searching, filtering, or aggregation.
6. Verify the behavior of saving multiple times with the same ID and any ID-change workflow.
7. Test reading, existence checking, and deleting by ID against an actual index.

Quick decision table:

| Requirement | Strategy |
|---|---|
| Need an ID before saving | Application generates a UUID or stable ID |
| Want Elasticsearch to auto-generate the ID | Leave ID null on document creation and read the ID after saving |
| Need retries without creating duplicate documents | Use a stable, predetermined ID |
| Need to search by business code | Also store the business key as a `keyword` field |
| Need sorting/aggregation by code | Use a separate `keyword` field |
| Need to change an identifier | Execute a workflow to create the new document and handle the old document |

## Conclusion

`@Id` marks the Java property mapped to Elasticsearch's `_id` document ID. Spring Data uses this value for saving, reading, checking existence, and deleting documents. The document ID is identification metadata, whereas a business key is business data that may need to be stored as a separate field. Choose stable IDs, declare consistent ID types between entities and repositories, and use `_id` solely for document identification.
