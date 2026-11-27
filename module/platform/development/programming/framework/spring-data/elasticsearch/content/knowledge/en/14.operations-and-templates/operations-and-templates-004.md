# Saving, Retrieving, Checking Existence, and Deleting Documents via Operations

Spring Data Elasticsearch provides **ElasticsearchOperations** to work directly with documents without declaring a repository method for every action. Through Operations, an application can save a document, retrieve a document by ID, check whether an ID exists, and delete a document by ID or entity.

These operations are suitable when a service needs explicit control over the target index, processes data according to business flows, or combines CRUD with other search APIs. Repositories remain useful for queries with clear method names; **ElasticsearchOperations** complements them with a more flexible API at the service layer.

This lesson uses the **products** index and the **Product** document class. Examples focus on four basic operations—**save**, **get**, **exists**, and **delete**—while explaining how to select an index with **IndexCoordinates**, handle missing documents, and safely perform partial updates.

## 1. What is ElasticsearchOperations?

**ElasticsearchOperations** is a high-level abstraction in Spring Data Elasticsearch. It provides APIs for working with documents, queries, and certain index-related operations. Spring Boot typically configures the implementation and connection components based on dependencies and application configuration.

In a service, inject **ElasticsearchOperations** via the constructor:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.stereotype.Service;

@Service
public class ProductService {

    private final ElasticsearchOperations operations;

    public ProductService(ElasticsearchOperations operations) {
        this.operations = operations;
    }
}
~~~

There is no need to manually create an Elasticsearch client with the **new** operator in each service. Constructor injection lets business classes share the Spring-managed connection configuration and makes it easy to substitute dependencies when writing tests.

Common CRUD operations:

| Need | Operations Method | Meaning |
|---|---|---|
| Save a document | **save(entity)** | Write the document according to the entity's metadata |
| Save to a specified index | **save(entity, index)** | Write the document to the specified index or alias |
| Retrieve by ID | **get(id, entityClass)** | Read the document by identifier |
| Check existence | **exists(id, index)** | Check whether a document with the ID exists in the index |
| Delete by ID | **delete(id, index)** | Delete the document with the corresponding identifier |
| Delete entity | **delete(entity)** | Delete the document based on the entity's ID |

Exact overload names and signatures may vary depending on the Spring Data Elasticsearch version. The examples below pass **IndexCoordinates** explicitly in operations that need to specify a target index.

## 2. Declaring the Product Document Class

Before performing operations, you need a Java class mapped to the Elasticsearch document. The **@Document** annotation specifies the default index, **@Id** marks the identifier, and **@Field** describes the data types of the fields.

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products", createIndex = false)
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private Double price;

    public Product() {
    }

    public Product(String id, String sku, String name,
                   String category, Double price) {
        this.id = id;
        this.sku = sku;
        this.name = name;
        this.category = category;
        this.price = price;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getSku() {
        return sku;
    }

    public void setSku(String sku) {
        this.sku = sku;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getCategory() {
        return category;
    }

    public void setCategory(String category) {
        this.category = category;
    }

    public Double getPrice() {
        return price;
    }

    public void setPrice(Double price) {
        this.price = price;
    }
}
~~~

In this example:

- **@Document(indexName = "products")** links the Product class to the products index.
- **createIndex = false** indicates that the application should not automatically create the index from the annotation when initializing metadata/repositories. The index should be created by a defined administrative or migration process.
- **@Id** maps the **id** property to Elasticsearch's **_id** identifier field.
- **sku** and **category** are **Keyword**, suitable for exact matching.
- **name** is **Text**, suitable for full-text search.
- **price** is a numeric field.

The index and mapping must exist before the application writes documents. You can create the index using **IndexOperations**, **@Setting**/**@Mapping** configuration, or a separate migration process. **ElasticsearchOperations.save(...)** does not replace proper mapping design.

## 3. Specifying an Index with IndexCoordinates

When using Operations, you can derive the index from the document class metadata or pass the index explicitly using **IndexCoordinates**.

~~~java
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

private static final IndexCoordinates PRODUCTS =
        IndexCoordinates.of("products");
~~~

Then use **PRODUCTS** in Operations methods:

~~~java
operations.save(product, PRODUCTS);
operations.get(productId, Product.class, PRODUCTS);
operations.exists(productId, PRODUCTS);
operations.delete(productId, PRODUCTS);
~~~

Passing the index explicitly is useful when:

- An entity may be stored in different indices.
- The application uses an alias instead of a physical index name.
- Indices are versioned, such as **products-v1**, **products-v2**.
- A service needs to operate on an archive index or a tenant-specific index.

If an entity has **@Document(indexName = "products")**, overloads based on entity metadata can determine the index automatically. However, when clarity about the operation target is needed, passing **IndexCoordinates** makes the index used immediately visible at the call site.

**IndexCoordinates** only describes the target of the operation. It does not create the index, validate the mapping, or guarantee that the index already exists.

## 4. Saving a Document with save()

The **save(...)** method converts a Java object into a JSON document and sends a write operation to Elasticsearch.

Example saving a product:

~~~java
Product product = new Product(
        "p-1001",
        "KB-1001",
        "Mechanical Keyboard",
        "accessories",
        89.50
);

Product saved = operations.save(product, PRODUCTS);
~~~

In this example, **PRODUCTS** is the IndexCoordinates constant declared earlier. Spring Data uses Product's metadata to convert the object into a document.

The corresponding document might look like:

~~~json
{
  "id": "p-1001",
  "sku": "KB-1001",
  "name": "Mechanical Keyboard",
  "category": "accessories",
  "price": 89.5
}
~~~

Elasticsearch uses the **@Id** value as the document identifier. If the application assigns IDs manually, ensure IDs are unique according to business rules. If letting Elasticsearch generate IDs, use the ID value returned by the save operation according to your version's API contract.

### save Can Create or Overwrite a Document

**save** writes a document by ID:

- If the ID does not exist yet, Elasticsearch creates a new document.
- If the ID already exists, the document contents are rewritten according to the object passed in.

Example saving an object with the same ID again:

~~~java
Product product = new Product(
        "p-1001",
        "KB-1001",
        "Mechanical Keyboard Pro",
        "accessories",
        109.00
);

operations.save(product, PRODUCTS);
~~~

The document with ID **p-1001** is written with the new contents. Therefore, if an object only contains an ID and one changed field, the remaining fields may be lost from the document after writing.

If you only need to update a few fields, read the existing document, modify its properties, and save it back, or use a partial update API.

## 5. Saving Multiple Documents

Operations also supports saving a collection of entities. This is useful when importing data or processing a batch of documents in a service.

~~~java
List<Product> products = List.of(
        new Product("p-1001", "KB-1001",
                "Mechanical Keyboard", "accessories", 89.50),
        new Product("p-1002", "MS-1002",
                "Wireless Mouse", "accessories", 29.00),
        new Product("p-1003", "HD-1003",
                "External SSD", "storage", 119.00)
);

Iterable<Product> savedProducts = operations.save(products, PRODUCTS);
~~~

Batch saving avoids calling individual save operations from application code. However, the batch size must be appropriate for available resources and document sizes. Do not send an excessively large batch if it can be split into moderate chunks.

When importing data, define a clear ID strategy. If IDs are stable, re-running the same batch will rewrite documents with the same IDs. If every import generates new IDs, data may be duplicated.

## 6. Retrieving a Document by ID with get()

The **get(...)** method reads a document by identifier and converts the JSON source into a Java object.

~~~java
Product product = operations.get(
        "p-1001",
        Product.class,
        PRODUCTS
);
~~~

If the document is found, the result is a Product object. If not found, the standard get API returns **null**. Therefore, check for null before using it:

~~~java
Product product = operations.get(
        productId,
        Product.class,
        PRODUCTS
);

if (product == null) {
    System.out.println("Product not found");
} else {
    System.out.println(product.getName());
}
~~~

This is a notable difference compared to the repository method **findById(...)**, which returns **Optional<Product>**. When using Operations, callers must handle the null contract of the get method.

You can encapsulate a required read in a service:

~~~java
public Product getRequired(String id) {
    Product product = operations.get(id, Product.class, PRODUCTS);

    if (product == null) {
        throw new ProductNotFoundException(id);
    }

    return product;
}
~~~

Business exception:

~~~java
public class ProductNotFoundException extends RuntimeException {

    public ProductNotFoundException(String id) {
        super("Product not found: " + id);
    }
}
~~~

This encapsulation keeps controllers and other services from repeating null checks.

### How Does Reading by ID Differ from Searching?

Reading directly by ID fetches a single document whose identifier is known. It does not need to build a query on fields such as name or category.

Searching by criteria requires a query API, such as **search(...)** or a repository method. Do not call **get(...)** if you only know the SKU or product name and not the ID.

Elasticsearch supports reading a document by ID using the Get API's default realtime behavior. Searching on the inverted index is near real-time and may have to wait for a refresh after writing. Thus, getting by ID and searching immediately after a save may have different visibility timings.

## 7. Checking Document Existence with exists()

If you only need to know whether an ID has a corresponding document, use **exists(...)** instead of loading the entire Product:

~~~java
boolean exists = operations.exists("p-1001", PRODUCTS);

if (exists) {
    System.out.println("Product already exists");
} else {
    System.out.println("Product does not exist yet");
}
~~~

This method returns a boolean:

- **true**: a document with the given ID exists in the target index.
- **false**: no matching document was found.

Use **exists** when business logic only needs a yes/no answer. If you need the document content, call **get** and check for null.

### Avoid Calling exists Before Every get

A common pattern looks like:

~~~java
if (operations.exists(productId, PRODUCTS)) {
    Product product = operations.get(
            productId,
            Product.class,
            PRODUCTS
    );
}
~~~

This snippet can be useful if the application only needs to check existence and then perform some other action. But if the goal is to retrieve the document, calling **exists** then **get** makes two requests when **get** already tells you whether the document exists.

You can write it directly:

~~~java
Product product = operations.get(
        productId,
        Product.class,
        PRODUCTS
);

if (product == null) {
    // Handle the not-found case.
}
~~~

In addition, the result of exists can become stale immediately after returning because another process may delete the document. Do not use exists as a locking mechanism or guarantee that the document will still exist in the next operation.

## 8. Deleting a Document by ID with delete()

When the ID is known, use **delete(...)** to remove the document from the index:

~~~java
operations.delete("p-1001", PRODUCTS);
~~~

This operation targets a single document by identifier. The application does not need to load the entity before deleting.

If you already have the entity, you can use the entity-deletion overload:

~~~java
Product product = operations.get(
        "p-1002",
        Product.class,
        PRODUCTS
);

if (product != null) {
    operations.delete(product, PRODUCTS);
}
~~~

Deleting by ID is usually better when only the identifier is needed. Deleting by entity is useful when the service already has the object and wants to use that object's ID.

Behavior for a non-existent ID and the return type of delete may depend on the overload or library version. If business logic needs to report clearly whether a document was deleted, check the contract of the API in use and handle the response accordingly; do not assume every delete call proves a document existed beforehand.

### Deleting and Checking Existence

If business logic requires distinguishing whether the document existed before deletion:

~~~java
public boolean deleteIfExists(String id) {
    if (!operations.exists(id, PRODUCTS)) {
        return false;
    }

    operations.delete(id, PRODUCTS);
    return true;
}
~~~

This example illustrates a business contract. In an environment with multiple concurrent processes, between the exists and delete steps the document could be deleted or modified. Therefore, a **true** result here only means the check saw the document and the service sent the delete command; it is not an atomic transaction locking the document across two requests.

If you do not need to distinguish the non-existent case, calling delete directly is simpler and avoids an extra exists request.

## 9. Updating a Document via get Then save

A simple update workflow is:

1. Read the document by ID.
2. Handle the not-found case.
3. Modify the properties that need updating.
4. Call save to write the document back.

Example updating the price:

~~~java
public Product updatePrice(String id, Double newPrice) {
    Product product = operations.get(id, Product.class, PRODUCTS);

    if (product == null) {
        throw new ProductNotFoundException(id);
    }

    product.setPrice(newPrice);

    return operations.save(product, PRODUCTS);
}
~~~

This approach preserves other fields because the service modifies the loaded object. However, if another process updates the same document between get and save, the later save may overwrite the other process's changes.

For data with concurrent updates, consider optimistic concurrency mechanisms, versioning, or partial update APIs supported by Spring Data Elasticsearch and Elasticsearch. The choice depends on business requirements and client version.

### Why Shouldn't You save an Entity with Only One Field?

Suppose the current document is:

~~~json
{
  "id": "p-1001",
  "sku": "KB-1001",
  "name": "Mechanical Keyboard",
  "category": "accessories",
  "price": 89.5
}
~~~

If you create a new object with only ID and price:

~~~java
Product partial = new Product();
partial.setId("p-1001");
partial.setPrice(79.90);

operations.save(partial, PRODUCTS);
~~~

The save command writes the document from the converted object. Fields missing from the object may no longer remain in the source after writing. To update a single field, read first and modify or use an appropriate update API.

## 10. Grouping CRUD into One Service

The following example demonstrates save, get, exists check, update, and delete operations in a single service:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.stereotype.Service;

@Service
public class ProductOperationsService {

    private static final IndexCoordinates PRODUCTS =
            IndexCoordinates.of("products");

    private final ElasticsearchOperations operations;

    public ProductOperationsService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public Product save(Product product) {
        return operations.save(product, PRODUCTS);
    }

    public List<Product> saveAll(List<Product> products) {
        List<Product> saved = new ArrayList<>();
        operations.save(products, PRODUCTS).forEach(saved::add);
        return saved;
    }

    public Product findById(String id) {
        return operations.get(id, Product.class, PRODUCTS);
    }

    public boolean existsById(String id) {
        return operations.exists(id, PRODUCTS);
    }

    public Product updatePrice(String id, Double newPrice) {
        Product product = findById(id);

        if (product == null) {
            throw new ProductNotFoundException(id);
        }

        product.setPrice(newPrice);
        return save(product);
    }

    public void deleteById(String id) {
        operations.delete(id, PRODUCTS);
    }

    public void delete(Product product) {
        operations.delete(product, PRODUCTS);
    }
}
~~~

This service keeps the index name in a single place. Business methods do not have to construct IndexCoordinates on every call.

In a real project, you can separate exceptions, input validation, and Elasticsearch error handling. Do not let controllers call Operations directly if business logic needs to be reused.

## 11. Using Operations Through an Alias

An application can operate through an alias instead of a physical index name. For example, the alias **products-current** points to the active index.

~~~java
private static final IndexCoordinates PRODUCTS =
        IndexCoordinates.of("products-current");
~~~

CRUD operations remain unchanged:

~~~java
operations.save(product, PRODUCTS);

Product product = operations.get(
        productId,
        Product.class,
        PRODUCTS
);

boolean exists = operations.exists(productId, PRODUCTS);

operations.delete(productId, PRODUCTS);
~~~

Elasticsearch routes requests through the alias. If the alias points to multiple indices, a write index must be clearly designated for write operations. A read alias can point to multiple indices, but a write alias must have an unambiguous write routing rule.

Using an alias allows the application to keep the same access name when the physical index is versioned. Creating a new index, reindexing, and switching the alias belong to the index management process, not the save/get/exists/delete commands.

## 12. Comparing Operations and Repository in CRUD

Both **ElasticsearchOperations** and **ElasticsearchRepository** can perform CRUD, but the code organization differs.

| Criterion | Repository | ElasticsearchOperations |
|---|---|---|
| Usage | Declare interface extending repository | Inject API into service |
| Save document | **save(entity)** | **save(entity, index)** |
| Read by ID | **findById(id)** returns Optional | **get(id, class, index)** typically returns entity or null |
| Check existence | **existsById(id)** | **exists(id, index)** |
| Delete by ID | **deleteById(id)** | **delete(id, index)** |
| Query by property | Derived query or @Query | CriteriaQuery, NativeQuery, and search API |
| Index selection | Usually from entity metadata | Can specify IndexCoordinates |
| Search metadata | Depends on repository return type | Can receive SearchHits and detailed metadata |

Use repositories for CRUD and queries with stable structure and clear method names. Use Operations when a service needs to control the target index, build dynamic queries, combine multiple operations, or work with search metadata.

Both approaches can coexist. There is no need to convert all repositories to Operations just because a few cases need lower-level APIs.

## 13. Common Errors in CRUD Operations via Operations

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Save fails with index not found | Index not created yet or wrong index name | Check **@Document**, IndexCoordinates, and index creation process |
| Save fails with mapping error | Java type does not match live mapping | Compare mapping, annotations, and sent values |
| Get returns null | ID does not exist in the specified index | Handle the missing document case |
| Exists returns false | ID does not exist or checking the wrong index/alias | Check ID and IndexCoordinates |
| Delete does not remove expected document | Wrong index selected or wrong ID passed | Check operation target and identifier |
| Save loses other fields | Overwrote with an entity containing partial data | Get before editing then save, or use partial update |
| Get cannot find after saving | Wrong index, ID, or conversion metadata | Check returned ID, IndexCoordinates, and mapping |
| Search does not see newly saved document | Index not refreshed yet | Understand difference between get by ID and near real-time search |
| Connection or auth error | Wrong URI, TLS, credentials, or permissions | Check client configuration and index privileges |
| Write alias operation fails | Alias covers multiple indices without a write index | Set an appropriate write index |

When diagnosing, inspect the underlying exception and Elasticsearch response. Do not catch all exceptions and return null or false, as that can turn a connection failure into a false report that the document does not exist.

## 14. Principles for Using Operations in Services

When implementing CRUD operations, you can apply the following principles:

1. Inject **ElasticsearchOperations** via constructor.
2. Declare **IndexCoordinates** explicitly when control over the target index or alias is needed.
3. Use **save** to create or overwrite a document by ID.
4. Use **get** when you need document content; handle null results if not found.
5. Use **exists** when you only need a yes/no answer.
6. Use **delete(id, index)** when the ID is known and a single document needs to be deleted.
7. Use **delete(entity, index)** when you already have the entity to delete.
8. Read the document before save if you only want to change a few properties.
9. Do not treat exists followed by get/delete as an atomic transaction; data can change between requests.
10. Distinguish not-found cases from connection, permission, or mapping errors.
11. Ensure the index and mapping are ready before writing.
12. Use a stable alias if the application needs to change index versions without changing access code.

**ElasticsearchOperations** provides a direct way to save, retrieve, check, and delete documents in Spring Data Elasticsearch. **save** writes documents by ID; **get** retrieves documents and requires handling null; **exists** answers existence questions; **delete** removes by ID or entity. When combining these methods with **IndexCoordinates**, services can explicitly control the target index or alias and organize CRUD rules according to application business logic.
